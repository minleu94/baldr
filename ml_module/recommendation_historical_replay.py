"""有界、point-in-time 的推薦 calibration 歷史 replay。

本模組只建立 shadow/research dataset，不會改寫正式資料庫，也不會把 replay
結果當成自然時間 forward evidence。每一筆樣本的時間線固定為：

* 決策日 ``T`` 只使用 ``MLHistoricalSnapshotProvider`` 讀出的 ``T-1``
  feature prefix；
* label 使用該股票在 ``T`` 之後第 20 個可觀測收盤，label availability
  等於該 forward close 日期；
* benchmark 只作同日 evaluation context，不是任何 label target；
* 無法證明 technical publication time、corporate action adjustment 或
  observed liquidity cost 時，保留樣本作研究用途，但明確把 formal
  candidate gate 關閉；固定 caller symbol cohort 不宣稱 PIT universe。

資料讀取由既有唯讀 SQLite provider 負責；本服務只接受呼叫端明確提供的
symbol universe，絕不從未來 survivorship list 反推歷史成分股。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from data_module.ml_historical_snapshot_provider import (
    HistoricalForwardPriceWindow,
    HistoricalPriceObservation,
    MLHistoricalSnapshotProvider,
)
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.recommendation_calibration_training import (
    AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
    AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
    RECOMMENDATION_HORIZON_TRADING_DAYS,
    RecommendationCalibrationSample,
    sample_payload,
)
from ml_module.recommendation_probability_transform import NULL_BENCHMARK_BASELINE_ID
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    estimate_round_trip_cost,
    normalize_cost_scenario,
)


_BP = Decimal("10000")
_REPLAY_SCHEMA_VERSION = "recommendation-historical-replay-dataset.v1"
_SOURCE_TABLES = (
    "daily_prices",
    "technical_indicators",
    "market_indices",
    "industry_indices",
)
_SOURCE_CONTRACT_TABLE = "recommendation_source_contract"
_SOURCE_CONTRACT_REQUIRED_COLUMNS = frozenset(
    {
        "component",
        "source_id",
        "source_table",
        "status",
        "coverage_start",
        "coverage_end",
        "available_at",
        "evidence_hash",
        "source_columns_json",
        "publication_time_verified",
        "corporate_action_adjustment_verified",
    }
)
_SOURCE_CONTRACT_ACCEPTED_STATUSES = frozenset({"accepted", "verified", "ready"})
_TECHNICAL_SOURCE_COLUMNS = frozenset(
    {"日期", "證券代號", "RSI", "MACD", "ADX", "available_at"}
)
_CORPORATE_ACTION_SOURCE_COLUMNS = frozenset(
    {"symbol", "event_date", "available_at", "effective_from", "adjustment_factor"}
)
_TECHNICAL_SOURCE_CONTENT_COLUMNS = (
    "日期",
    "證券代號",
    "RSI",
    "MACD",
    "ADX",
    "available_at",
)
_CORPORATE_ACTION_SOURCE_CONTENT_COLUMNS = (
    "symbol",
    "event_date",
    "available_at",
    "effective_from",
    "adjustment_factor",
)


@dataclass(frozen=True)
class RecommendationHistoricalReplayConfig:
    """Replay 的明確邊界；所有數值成本以整數 bp 儲存。"""

    history_start_date: str
    replay_start_date: str
    replay_end_date: str
    symbols: tuple[str, ...]
    fixed_round_trip_cost_bp: int | None
    cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None
    max_decision_dates: int = 100
    horizon_trading_days: int = RECOMMENDATION_HORIZON_TRADING_DAYS
    industry_index_name_by_symbol: Mapping[str, str] = field(default_factory=dict)
    rule_probability_bp: int = 5_000
    rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID
    selection_policy: str = "chronological_first_eligible_date"

    def __post_init__(self) -> None:
        history_start = _date(self.history_start_date)
        replay_start = _date(self.replay_start_date)
        replay_end = _date(self.replay_end_date)
        if history_start > replay_start:
            raise ValueError("history_start_date must not follow replay_start_date")
        if replay_start > replay_end:
            raise ValueError("replay_start_date must not follow replay_end_date")
        if not self.symbols or not any(str(symbol).strip() for symbol in self.symbols):
            raise ValueError("symbols must be explicitly supplied")
        normalized = tuple(sorted({str(symbol).strip() for symbol in self.symbols if str(symbol).strip()}))
        object.__setattr__(self, "symbols", normalized)
        if self.fixed_round_trip_cost_bp is not None and (
            isinstance(self.fixed_round_trip_cost_bp, bool)
            or not isinstance(self.fixed_round_trip_cost_bp, int)
            or self.fixed_round_trip_cost_bp < 0
        ):
            raise ValueError("fixed_round_trip_cost_bp must be a non-negative integer or None")
        try:
            scenario = normalize_cost_scenario(
                self.cost_scenario,
                fixed_round_trip_cost_bp=self.fixed_round_trip_cost_bp,
            )
        except RecommendationCostScenarioError as exc:
            raise ValueError(str(exc)) from exc
        if scenario.is_estimated and self.fixed_round_trip_cost_bp is not None:
            raise ValueError("estimated replay config must not carry a fixed cost")
        object.__setattr__(self, "cost_scenario", scenario)
        if isinstance(self.max_decision_dates, bool) or self.max_decision_dates <= 0:
            raise ValueError("max_decision_dates must be positive")
        if self.horizon_trading_days != RECOMMENDATION_HORIZON_TRADING_DAYS:
            raise ValueError("recommendation calibration horizon is locked to 20 trading days")
        if not 0 <= self.rule_probability_bp <= 10_000:
            raise ValueError("rule_probability_bp must be within 0..10000")
        if not self.rule_baseline_id.strip():
            raise ValueError("rule_baseline_id is required")
        if self.selection_policy not in {
            "chronological_first_eligible_date",
            "latest_eligible_dates",
            "time_stratified_eligible_dates",
        }:
            raise ValueError("selection_policy is unsupported")
        industry_mapping = self.industry_index_name_by_symbol
        if not isinstance(industry_mapping, Mapping):
            industry_mapping = {}
        object.__setattr__(
            self,
            "industry_index_name_by_symbol",
            {
                str(symbol).strip(): str(index).strip()
                for symbol, index in industry_mapping.items()
                if str(symbol).strip() and str(index).strip()
            },
        )


@dataclass(frozen=True)
class RecommendationHistoricalReplayResult:
    """Replay dataset plus its quality and formal-eligibility disclosures."""

    dataset_id: str
    dataset_hash: str
    samples: tuple[RecommendationCalibrationSample, ...]
    decision_dates: tuple[str, ...]
    source_fingerprint: str
    diagnostics: tuple[str, ...]
    coverage: Mapping[str, Any]
    source_disclosures: Mapping[str, Any]
    lookahead_checks: Mapping[str, Any]
    training_data_eligible: bool
    forward_evidence_eligible: bool
    formal_candidate_eligible: bool
    candidate_blockers: tuple[str, ...]
    manifest_path: str | None = None

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _REPLAY_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "sample_count": len(self.samples),
            "decision_dates": list(self.decision_dates),
            "source_fingerprint": self.source_fingerprint,
            "samples": [sample_payload(sample) for sample in self.samples],
            "diagnostics": list(self.diagnostics),
            "coverage": dict(self.coverage),
            "source_disclosures": dict(self.source_disclosures),
            "lookahead_checks": dict(self.lookahead_checks),
            "training_data_eligible": self.training_data_eligible,
            "forward_evidence_eligible": self.forward_evidence_eligible,
            "formal_candidate_eligible": self.formal_candidate_eligible,
            "candidate_blockers": list(self.candidate_blockers),
            "shadow_only": True,
            "production_action_allowed": False,
        }

    def persist(self, output_root: str | Path) -> Path:
        """Create an immutable dataset directory and return its manifest path."""

        root = Path(output_root).resolve() / "recommendation_learning" / "datasets" / self.dataset_id
        root.mkdir(parents=True, exist_ok=True)
        manifest_path = root / "dataset.json"
        payload = self.to_dict()
        if manifest_path.is_file():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            normalized_payload = json.loads(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
            )
            if existing != normalized_payload:
                raise RuntimeError("immutable historical replay dataset conflict")
        else:
            manifest_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        object.__setattr__(self, "manifest_path", str(manifest_path))
        return manifest_path


class RecommendationHistoricalReplayService:
    """Build a bounded dataset from explicitly selected historical symbols."""

    def __init__(
        self,
        provider: MLHistoricalSnapshotProvider,
        *,
        feature_builder: HistoricalFeatureBuilder | None = None,
    ) -> None:
        self.provider = provider
        self.feature_builder = feature_builder or HistoricalFeatureBuilder(
            CORE_LONG_HISTORY_FEATURE_REGISTRY
        )

    def build(self, config: RecommendationHistoricalReplayConfig) -> RecommendationHistoricalReplayResult:
        scenario = config.cost_scenario
        if not isinstance(scenario, RecommendationCostScenario):
            raise ValueError("replay cost scenario was not normalized")
        trading_dates = self.provider.list_trading_dates(
            start_date=config.replay_start_date,
            end_date=config.replay_end_date,
            symbols=config.symbols,
        )
        if not trading_dates:
            return self._empty_result(config, "no_explicit_universe_trading_dates")

        # Keep the date bound deterministic and explicit.  The scheduled path
        # normally selects the latest eligible window so a new trading day can
        # change the training dataset.  A bounded bootstrap fallback may use a
        # date-only, time-stratified window when a recent slice cannot produce
        # causal OOF calibration; it never inspects labels while selecting
        # dates and it never changes the explicit symbol cohort.
        all_decision_candidates = tuple(
            item
            for item in trading_dates
            if _date(item) >= _date(config.replay_start_date)
            and _date(item) <= _date(config.replay_end_date)
        )
        diagnostics: list[str] = []
        if config.selection_policy == "latest_eligible_dates":
            decision_candidates = all_decision_candidates[-config.max_decision_dates :]
        elif config.selection_policy == "time_stratified_eligible_dates":
            decision_candidates = _time_stratified_eligible_dates(
                all_decision_candidates,
                max_decision_dates=config.max_decision_dates,
                horizon_trading_days=config.horizon_trading_days,
            )
            diagnostics.append(
                "time_stratified_date_selection:"
                f"pool={max(0, len(all_decision_candidates) - config.horizon_trading_days)}:"
                f"selected={len(decision_candidates)}:"
                f"max_decision_dates={config.max_decision_dates}"
            )
        else:
            decision_candidates = all_decision_candidates[: config.max_decision_dates]
        samples: list[RecommendationCalibrationSample] = []
        selected_dates: list[str] = []
        source_fingerprints: set[str] = set()
        feature_rows_seen = 0
        labels_built = 0
        rows_skipped_missing_price = 0
        rows_skipped_missing_benchmark = 0
        rows_skipped_missing_feature = 0
        rows_with_observed_liquidity_cost = 0
        rows_with_estimated_cost = 0
        rows_with_unavailable_estimated_cost = 0
        technical_cutoffs: list[str] = []
        technical_usage: list[dict[str, str]] = []

        for decision_text in decision_candidates:
            if len(selected_dates) >= config.max_decision_dates:
                diagnostics.append("max_decision_dates_bound_reached")
                break
            decision = _date(decision_text)
            try:
                snapshot = self.provider.load(
                    decision_date=decision.isoformat(),
                    history_start_date=config.history_start_date,
                    symbols=config.symbols,
                    industry_index_names=tuple(
                        sorted(set(config.industry_index_name_by_symbol.values()))
                    ),
                )
                forward = self.provider.load_forward_price_window(
                    start_date=decision.isoformat(),
                    end_date=config.replay_end_date,
                    symbols=config.symbols,
                )
            except (OSError, RuntimeError, ValueError) as exc:
                diagnostics.append(
                    f"decision_date_skipped:{decision.isoformat()}:{type(exc).__name__}:{exc}"
                )
                continue
            source_fingerprints.add(snapshot.source_fingerprint)
            source_fingerprints.add(forward.source_fingerprint)
            if _has_future_snapshot_rows(snapshot, decision):
                raise RuntimeError("historical feature snapshot contains post-decision rows")
            technical_cutoffs.extend(
                row.trading_date for row in snapshot.technicals if row.trading_date <= snapshot.feature_as_of_date
            )
            feature_rows = self.feature_builder.compute(
                snapshot,
                industry_index_name_by_symbol=config.industry_index_name_by_symbol,
            )
            technical_by_symbol: dict[str, list[Any]] = {}
            for observation in snapshot.technicals:
                if observation.trading_date <= snapshot.feature_as_of_date:
                    technical_by_symbol.setdefault(observation.symbol, []).append(observation)
            for feature_row in feature_rows:
                candidates = technical_by_symbol.get(feature_row.symbol, [])
                if candidates:
                    latest_technical = max(candidates, key=lambda row: row.trading_date)
                    technical_usage.append(
                        {
                            "decision_date": decision.isoformat(),
                            "symbol": feature_row.symbol,
                            "trading_date": latest_technical.trading_date,
                        }
                    )
            feature_by_symbol = {row.symbol: row for row in feature_rows}
            feature_rows_seen += len(feature_rows)
            prices_by_symbol = _prices_by_symbol(forward.prices)
            market_by_date = {
                row.trading_date: row.close_value
                for row in forward.market
                if row.close_value is not None
            }
            date_samples: list[RecommendationCalibrationSample] = []
            for symbol in config.symbols:
                feature = feature_by_symbol.get(symbol)
                if feature is None:
                    rows_skipped_missing_feature += 1
                    continue
                if _date(feature.feature_as_of_date) >= decision or _date(feature.available_date) > decision:
                    raise RuntimeError("historical feature row violates decision-time availability")
                observed_prices = sorted(
                    (
                        row
                        for row in prices_by_symbol.get(symbol, ())
                        if _date(row.trading_date) > decision
                        and row.close_price is not None
                    ),
                    key=lambda row: row.trading_date,
                )
                start_price = _exact_close(prices_by_symbol.get(symbol, ()), decision.isoformat())
                if start_price is None or len(observed_prices) < config.horizon_trading_days:
                    rows_skipped_missing_price += 1
                    continue
                label_row = observed_prices[config.horizon_trading_days - 1]
                if label_row.close_price is None or start_price == 0:
                    rows_skipped_missing_price += 1
                    continue
                benchmark_start = market_by_date.get(decision.isoformat())
                benchmark_end = market_by_date.get(label_row.trading_date)
                if benchmark_start is None or benchmark_end is None or benchmark_start == 0:
                    rows_skipped_missing_benchmark += 1
                    continue
                stock_return_bp = _return_bp(start_price, label_row.close_price)
                benchmark_return_bp = _return_bp(benchmark_start, benchmark_end)
                observed_liquidity_cost_bp, observed_liquidity_cost_source = _lookup_observed_liquidity_cost(
                    self.provider.database_path,
                    symbol=symbol,
                    decision_date=decision,
                    label_end_date=_date(label_row.trading_date),
                )
                if observed_liquidity_cost_bp is not None:
                    rows_with_observed_liquidity_cost += 1
                cost_estimate = estimate_round_trip_cost(
                    scenario,
                    market_replay_date=decision.isoformat(),
                    buy_price_twd=start_price,
                    sell_price_twd=label_row.close_price,
                )
                if scenario.is_estimated:
                    if cost_estimate.available:
                        rows_with_estimated_cost += 1
                    else:
                        rows_with_unavailable_estimated_cost += 1
                        diagnostics.append(
                            "estimated_cost_unavailable:"
                            f"{decision.isoformat()}:{symbol}:"
                            + ",".join(cost_estimate.diagnostics)
                        )
                sample = RecommendationCalibrationSample.from_forward_return(
                    row_id=f"historical-replay:{decision.isoformat()}:{symbol}",
                    symbol=symbol,
                    decision_date=decision.isoformat(),
                    feature_as_of_date=feature.feature_as_of_date,
                    feature_available_date=feature.available_date,
                    label_end_date=label_row.trading_date,
                    label_available_date=label_row.trading_date,
                    feature_values=tuple(value for _, value in feature.values),
                    stock_return_bp=stock_return_bp,
                    benchmark_return_bp=benchmark_return_bp,
                    fixed_round_trip_cost_bp=config.fixed_round_trip_cost_bp,
                    observed_liquidity_cost_bp=observed_liquidity_cost_bp,
                    rule_probability_bp=config.rule_probability_bp,
                    rule_after_cost_probability_bp=(
                        AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
                        if observed_liquidity_cost_bp is not None
                        else None
                    ),
                    rule_after_cost_baseline_id=(
                        AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                        if observed_liquidity_cost_bp is not None
                        else None
                    ),
                    rule_baseline_id=config.rule_baseline_id,
                    source_quality="research",
                    cost_scenario=scenario,
                    cost_estimate=cost_estimate,
                )
                date_samples.append(sample)
            if date_samples:
                selected_dates.append(decision.isoformat())
                labels_built += len(date_samples)
                samples.extend(date_samples)

        if not samples:
            diagnostics.append("no_replay_samples_with_complete_feature_price_benchmark_chain")
        if not technical_cutoffs:
            diagnostics.append("technical_history_missing_or_empty")
        source_contract = _read_source_contract(
            self.provider.database_path,
            config=config,
            technical_usage=tuple(technical_usage),
            label_windows=tuple(
                {
                    "symbol": row.symbol,
                    "decision_date": row.decision_date,
                    "label_end_date": row.label_end_date,
                }
                for row in samples
            ),
        )
        excluded_label_windows = {
            (str(item[0]), str(item[1]), str(item[2]))
            for item in source_contract.pop("_unadjusted_label_window_keys", ())
            if isinstance(item, (list, tuple)) and len(item) == 3
        }
        if excluded_label_windows:
            samples = [
                row
                for row in samples
                if (row.symbol, row.decision_date, row.label_end_date) not in excluded_label_windows
            ]
            diagnostics.append(
                "corporate_action_unadjusted_label_windows_excluded:"
                + str(len(excluded_label_windows))
            )
            selected_dates = sorted({row.decision_date for row in samples})
            labels_built = len(samples)
            rows_with_observed_liquidity_cost = sum(
                row.observed_liquidity_cost_bp is not None for row in samples
            )
        source_fingerprint = str(source_contract["fingerprint"])
        source_fingerprints.add(source_fingerprint)
        dataset_payload = {
            "schema_version": _REPLAY_SCHEMA_VERSION,
            "config": _config_payload(config),
            "source_fingerprints": sorted(source_fingerprints),
            "decision_dates": selected_dates,
            "samples": [sample_payload(sample) for sample in samples],
        }
        dataset_hash = _hash_payload(dataset_payload)
        dataset_id = "recommendation-dataset-" + dataset_hash[7:23]
        source_fingerprint = _hash_payload(
            {
                "provider": str(self.provider.database_path),
                "source_fingerprints": sorted(source_fingerprints),
            }
        )
        source_disclosures = _source_disclosures(
            config,
            source_contract=source_contract,
            rows_built=labels_built,
            rows_with_observed_liquidity_cost=rows_with_observed_liquidity_cost,
            rows_with_estimated_cost=rows_with_estimated_cost,
            rows_with_unavailable_estimated_cost=rows_with_unavailable_estimated_cost,
        )
        lookahead_checks = {
            "feature_snapshot_rows_strictly_before_decision": True,
            "feature_available_date_not_after_decision": True,
            "future_label_dates_strictly_after_decision": True,
            "label_available_date_not_before_label_end": True,
            "benchmark_is_context_only_not_target": True,
            "explicit_universe_only": True,
            "technical_publication_time_verified": bool(
                source_contract["technical"]["verified"]
            ),
            "corporate_action_adjustment_verified": bool(
                source_contract["corporate_actions"]["verified"]
            ),
            "fixed_explicit_universe_does_not_claim_pit_constituent_history": True,
            "cost_policy_estimate_date_separate_from_market_replay_date": True,
            "cost_scenario_scope_key_excludes_market_replay_date": True,
        }
        blocker_list = ["historical_replay_is_not_natural_forward_evidence"]
        if not source_contract["technical"]["verified"]:
            blocker_list.append("technical_publication_time_unverified")
        if not source_contract["corporate_actions"]["verified"]:
            blocker_list.append("corporate_action_source_or_adjustment_unverified")
        if not scenario.is_estimated:
            if rows_with_observed_liquidity_cost <= 0:
                blocker_list.append("observed_liquidity_cost_missing_after_cost_target_unavailable")
            elif rows_with_observed_liquidity_cost < labels_built:
                blocker_list.append("observed_liquidity_cost_partial_after_cost_target_unavailable")
        if scenario.is_estimated and rows_with_unavailable_estimated_cost > 0:
            blocker_list.append("estimated_fee_tax_cost_missing_after_cost_target_partial")
        blockers = tuple(blocker_list)
        coverage = {
            "requested_symbols": list(config.symbols),
            "requested_decision_date_count": len(all_decision_candidates),
            "selection_pool_decision_date_count": (
                max(0, len(all_decision_candidates) - config.horizon_trading_days)
                if config.selection_policy == "time_stratified_eligible_dates"
                else len(all_decision_candidates)
            ),
            "selected_decision_date_count": len(selected_dates),
            "max_decision_dates": config.max_decision_dates,
            "selection_policy": config.selection_policy,
            "feature_rows_seen": feature_rows_seen,
            "samples_built": labels_built,
            "rows_skipped_missing_feature": rows_skipped_missing_feature,
            "rows_skipped_missing_price_or_horizon": rows_skipped_missing_price,
            "rows_skipped_missing_benchmark": rows_skipped_missing_benchmark,
            "technical_input_cutoff_max": max(technical_cutoffs) if technical_cutoffs else None,
            "liquidity_cost_coverage": (
                "observed" if rows_with_observed_liquidity_cost else "missing"
            ),
            "after_cost_label_coverage": (
                "fees_tax_only_estimated"
                if scenario.is_estimated and rows_with_estimated_cost
                else "observed" if rows_with_observed_liquidity_cost else "missing"
            ),
            "cost_scenario_id": scenario.scenario_id,
            "cost_scenario_version": scenario.scenario_version,
            "cost_scenario_hash": scenario.scenario_hash,
            "cost_basis": scenario.cost_basis,
            "estimated_cost_rows": rows_with_estimated_cost,
            "estimated_cost_unavailable_rows": rows_with_unavailable_estimated_cost,
            "market_replay_dates_are_observation_lineage_only": True,
            "source_contract": dict(source_contract["summary"]),
        }
        return RecommendationHistoricalReplayResult(
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            samples=tuple(samples),
            decision_dates=tuple(selected_dates),
            source_fingerprint=source_fingerprint,
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            coverage=coverage,
            source_disclosures=source_disclosures,
            lookahead_checks=lookahead_checks,
            training_data_eligible=True,
            forward_evidence_eligible=False,
            formal_candidate_eligible=False,
            candidate_blockers=blockers,
        )

    def _empty_result(
        self,
        config: RecommendationHistoricalReplayConfig,
        reason: str,
    ) -> RecommendationHistoricalReplayResult:
        scenario = normalize_cost_scenario(
            config.cost_scenario,
            fixed_round_trip_cost_bp=config.fixed_round_trip_cost_bp,
        )
        dataset_payload = {
            "schema_version": _REPLAY_SCHEMA_VERSION,
            "config": _config_payload(config),
            "source_fingerprints": [],
            "decision_dates": [],
            "samples": [],
        }
        dataset_hash = _hash_payload(dataset_payload)
        empty_coverage: dict[str, Any] = {
            "requested_symbols": list(config.symbols),
            "requested_decision_date_count": 0,
            "selected_decision_date_count": 0,
            "max_decision_dates": config.max_decision_dates,
            "selection_policy": config.selection_policy,
            "samples_built": 0,
            "liquidity_cost_coverage": "missing",
            "after_cost_label_coverage": "missing",
            "cost_scenario_id": scenario.scenario_id,
            "cost_scenario_version": scenario.scenario_version,
            "cost_scenario_hash": scenario.scenario_hash,
            "cost_basis": scenario.cost_basis,
            "estimated_cost_rows": 0,
            "estimated_cost_unavailable_rows": 0,
        }
        empty_blockers = [
            "no_historical_rows",
            "historical_replay_is_not_natural_forward_evidence",
            "technical_publication_time_unverified",
            "corporate_action_source_or_adjustment_unverified",
        ]
        if not scenario.is_estimated:
            empty_blockers.append(
                "observed_liquidity_cost_missing_after_cost_target_unavailable"
            )
        return RecommendationHistoricalReplayResult(
            dataset_id="recommendation-dataset-" + dataset_hash[7:23],
            dataset_hash=dataset_hash,
            samples=(),
            decision_dates=(),
            source_fingerprint=_hash_payload({"provider": str(self.provider.database_path), "source_fingerprints": []}),
            diagnostics=(reason,),
            coverage=empty_coverage,
            source_disclosures=_source_disclosures(config),
            lookahead_checks={
                "feature_snapshot_rows_strictly_before_decision": True,
                "future_label_dates_strictly_after_decision": True,
                "benchmark_is_context_only_not_target": True,
                "explicit_universe_only": True,
                "cost_policy_estimate_date_separate_from_market_replay_date": True,
                "cost_scenario_scope_key_excludes_market_replay_date": True,
            },
            training_data_eligible=False,
            forward_evidence_eligible=False,
            formal_candidate_eligible=False,
            candidate_blockers=tuple(empty_blockers),
        )


def _prices_by_symbol(
    rows: Sequence[HistoricalPriceObservation],
) -> dict[str, tuple[HistoricalPriceObservation, ...]]:
    grouped: dict[str, list[HistoricalPriceObservation]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)
    return {
        symbol: tuple(sorted(values, key=lambda item: item.trading_date))
        for symbol, values in grouped.items()
    }


def _exact_close(
    rows: Sequence[HistoricalPriceObservation], trading_date: str
) -> Decimal | None:
    for row in rows:
        if row.trading_date == trading_date:
            return row.close_price
    return None


def _return_bp(start: Decimal, end: Decimal) -> int:
    if start == 0:
        raise ValueError("return start price cannot be zero")
    return int(((end / start - Decimal(1)) * _BP).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def _has_future_snapshot_rows(snapshot: Any, decision: date) -> bool:
    for collection in (snapshot.prices, snapshot.technicals, snapshot.market, snapshot.industries):
        if any(_date(row.trading_date) >= decision for row in collection):
            return True
    return False


def _source_disclosures(
    config: RecommendationHistoricalReplayConfig,
    *,
    source_contract: Mapping[str, Any] | None = None,
    rows_built: int = 0,
    rows_with_observed_liquidity_cost: int = 0,
    rows_with_estimated_cost: int = 0,
    rows_with_unavailable_estimated_cost: int = 0,
) -> dict[str, Any]:
    contract = source_contract or _unknown_source_contract(config)
    technical = dict(contract["technical"])
    corporate_actions = dict(contract["corporate_actions"])
    explicit_universe = bool(config.symbols)
    cost_coverage = (
        "observed_complete"
        if rows_built > 0 and rows_with_observed_liquidity_cost == rows_built
        else "observed_partial"
        if rows_with_observed_liquidity_cost > 0
        else "missing"
    )
    return {
        "price_volume": {
            "source_tables": ["daily_prices"],
            "fields": ["開盤價", "最高價", "最低價", "收盤價", "成交股數", "成交金額"],
            "availability": "row date <= feature cutoff for features; forward rows are read only after decision date for labels",
            "adjustment_policy": "raw_close_no_corporate_action_adjustment_verified",
        },
        "technical": {
            "source_tables": ["technical_indicators"],
            "availability": "technical row date <= feature_as_of_date",
            "publication_time_verified": bool(technical.get("verified")),
            "use": (
                "source_contract_verified"
                if technical.get("verified")
                else "research_only; formal candidate blocked until publication availability mapping exists"
            ),
            "source_contract": technical,
        },
        "constituents": {
            "source": "caller_supplied_explicit_symbols",
            "point_in_time_history_provided": False,
            "point_in_time_history_required": False if explicit_universe else True,
            "universe_mode": "explicit_fixed_symbol_cohort" if explicit_universe else "unresolved",
            "survivorship_policy": (
                "no universe discovery; fixed caller-supplied cohort; no broad-universe claim"
                if explicit_universe
                else "universe is not explicit; point-in-time membership is required"
            ),
        },
        "corporate_actions": {
            "source_tables": (
                [str(corporate_actions.get("source_table"))]
                if corporate_actions.get("source_table")
                else []
            ),
            "source_available": bool(corporate_actions.get("source_available")),
            "adjustment_verified": bool(corporate_actions.get("verified")),
            "source_contract": corporate_actions,
            "policy": (
                "source contract verified for the requested range"
                if corporate_actions.get("verified")
                else "raw close retained for research; no formal promotion"
            ),
        },
        "benchmark": {
            "source_tables": ["market_indices"],
            "role": "same-date evaluation context only; not a target",
            "selection": "exact decision date close to exact label-end close",
        },
        "cost": {
            "fixed_round_trip_cost_bp": config.fixed_round_trip_cost_bp,
            "cost_scenario_id": (
                config.cost_scenario.scenario_id
                if isinstance(config.cost_scenario, RecommendationCostScenario)
                else None
            ),
            "cost_scenario_version": (
                config.cost_scenario.scenario_version
                if isinstance(config.cost_scenario, RecommendationCostScenario)
                else None
            ),
            "cost_scenario_hash": (
                config.cost_scenario.scenario_hash
                if isinstance(config.cost_scenario, RecommendationCostScenario)
                else None
            ),
            "cost_basis": (
                config.cost_scenario.cost_basis
                if isinstance(config.cost_scenario, RecommendationCostScenario)
                else None
            ),
            "policy_estimate_date": (
                config.cost_scenario.policy_estimate_date
                if isinstance(config.cost_scenario, RecommendationCostScenario)
                else None
            ),
            "market_replay_date_role": "per_row_observation_lineage_not_scope_key",
            "estimated_fee_tax_cost_rows": rows_with_estimated_cost,
            "estimated_fee_tax_cost_unavailable_rows": rows_with_unavailable_estimated_cost,
            "observed_liquidity_cost_source": (
                "evidence_outcomes.liquidity_cost_bp"
                if rows_with_observed_liquidity_cost
                else None
            ),
            "observed_liquidity_cost_rows": rows_with_observed_liquidity_cost,
            "rows_built": rows_built,
            "coverage": cost_coverage,
            "after_cost_target": (
                "fees_tax_only_exact_decimal_net_profit_for_banktaiwan_estimated_scenario"
                if isinstance(config.cost_scenario, RecommendationCostScenario)
                and config.cost_scenario.is_estimated
                else "absolute_return_after_fixed_and_observed_cost"
                if rows_with_observed_liquidity_cost
                else "missing because observed liquidity cost is unavailable"
            ),
            "after_cost_baseline_id": (
                AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                if rows_with_observed_liquidity_cost
                else None
            ),
        },
        "excluded_feature_families": ["fundamental", "broker"],
        "read_mode": "SQLite mode=ro with PRAGMA query_only=ON",
        "source_table_whitelist": list(_SOURCE_TABLES),
        "source_contract": dict(contract["summary"]),
    }


def _unknown_source_contract(config: RecommendationHistoricalReplayConfig) -> dict[str, Any]:
    """Return an explicit unknown contract; unknown is never promoted to ready."""

    technical = {
        "verified": False,
        "source_available": False,
        "status": "unverified",
        "reason": "recommendation_source_contract_missing",
        "source_table": "technical_indicators",
        "coverage_start": None,
        "coverage_end": None,
        "available_at": None,
        "evidence_hash": None,
        "source_columns": [],
    }
    corporate_actions = {
        "verified": False,
        "source_available": False,
        "status": "unverified",
        "reason": "recommendation_source_contract_missing",
        "source_table": None,
        "coverage_start": None,
        "coverage_end": None,
        "available_at": None,
        "evidence_hash": None,
        "source_columns": [],
    }
    summary = {
        "contract_table": _SOURCE_CONTRACT_TABLE,
        "history_start_date": _date(config.history_start_date).isoformat(),
        "replay_start_date": _date(config.replay_start_date).isoformat(),
        "replay_end_date": _date(config.replay_end_date).isoformat(),
        "technical": {key: value for key, value in technical.items() if key != "source_columns"},
        "corporate_actions": {
            key: value for key, value in corporate_actions.items() if key != "source_columns"
        },
        "read_mode": "SQLite mode=ro with PRAGMA query_only=ON",
    }
    return {
        "technical": technical,
        "corporate_actions": corporate_actions,
        "summary": summary,
        "fingerprint": _hash_payload(summary),
    }


def _read_source_contract(
    database_path: str | Path,
    *,
    config: RecommendationHistoricalReplayConfig,
    technical_usage: Sequence[Mapping[str, str]] = (),
    label_windows: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    """Read and validate an optional, hash-bound source contract in read-only mode.

    The four historical provider tables predate this recommendation-specific
    contract and do not carry publication or corporate-action lineage.  Their
    presence alone must therefore not be interpreted as acceptance.  A source
    may opt in by publishing one row per component in the append-only
    ``recommendation_source_contract`` table.  This function checks the table
    schema, source table columns, actual symbol-scoped content digest, covered
    source rows, component-specific verification flag, and the decision-time
    availability of technical rows actually used by the feature builder.  A
    non-unit corporate action inside a raw label window is conservatively
    excluded rather than treated as adjusted.  Missing or malformed contracts
    stay explicitly unverified, which preserves the production fail-closed path.
    """

    contract = _unknown_source_contract(config)
    path = Path(database_path).resolve()
    diagnostics: list[str] = []
    rows: dict[str, Mapping[str, Any]] = {}
    try:
        if not path.is_file():
            diagnostics.append("source_database_missing")
            contract["summary"]["diagnostics"] = diagnostics
            contract["fingerprint"] = _hash_payload(contract["summary"])
            return contract
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            tables = {
                str(item[0])
                for item in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if _SOURCE_CONTRACT_TABLE not in tables:
                diagnostics.append("source_contract_table_missing")
            else:
                columns = {
                    str(item[1])
                    for item in connection.execute(
                        f'PRAGMA table_info("{_SOURCE_CONTRACT_TABLE}")'
                    ).fetchall()
                }
                missing_columns = _SOURCE_CONTRACT_REQUIRED_COLUMNS - columns
                if missing_columns:
                    diagnostics.append(
                        "source_contract_columns_missing:" + ",".join(sorted(missing_columns))
                    )
                else:
                    selected = connection.execute(
                        f'SELECT "component", "source_id", "source_table", "status", '
                        f'"coverage_start", "coverage_end", "available_at", "evidence_hash", '
                        f'"source_columns_json", "publication_time_verified", '
                        f'"corporate_action_adjustment_verified" '
                        f'FROM "{_SOURCE_CONTRACT_TABLE}"'
                    ).fetchall()
                    for row in selected:
                        component = str(row[0] or "").strip()
                        if component in rows:
                            diagnostics.append(f"source_contract_duplicate_component:{component}")
                            continue
                        rows[component] = {
                            "component": component,
                            "source_id": str(row[1] or "").strip(),
                            "source_table": str(row[2] or "").strip(),
                            "status": str(row[3] or "").strip().lower(),
                            "coverage_start": str(row[4] or "").strip(),
                            "coverage_end": str(row[5] or "").strip(),
                            "available_at": str(row[6] or "").strip(),
                            "evidence_hash": str(row[7] or "").strip(),
                            "source_columns_json": str(row[8] or "").strip(),
                            "publication_time_verified": row[9],
                            "corporate_action_adjustment_verified": row[10],
                        }
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        diagnostics.append(f"source_contract_read_failed:{type(exc).__name__}")

    unadjusted_label_window_keys: set[tuple[str, str, str]] = set()
    for component, expected_columns, verification_field in (
        (
            "technical",
            _TECHNICAL_SOURCE_COLUMNS,
            "publication_time_verified",
        ),
        (
            "corporate_actions",
            _CORPORATE_ACTION_SOURCE_COLUMNS,
            "corporate_action_adjustment_verified",
        ),
    ):
        item = rows.get(component)
        if item is None:
            diagnostics.append(f"source_contract_component_missing:{component}")
            continue
        result = contract[component]
        result.update(
            {
                "source_available": True,
                "source_id": item["source_id"],
                "source_table": item["source_table"],
                "status": item["status"],
                "coverage_start": item["coverage_start"] or None,
                "coverage_end": item["coverage_end"] or None,
                "available_at": item["available_at"] or None,
                "evidence_hash": item["evidence_hash"] or None,
                "source_columns": [],
            }
        )
        reasons: list[str] = []
        if item["status"] not in _SOURCE_CONTRACT_ACCEPTED_STATUSES:
            reasons.append("status_not_accepted")
        if not item["source_id"]:
            reasons.append("source_id_missing")
        if not item["source_table"]:
            reasons.append("source_table_missing")
        if not _is_sha256(item["evidence_hash"]):
            reasons.append("evidence_hash_invalid")
        try:
            source_columns = json.loads(item["source_columns_json"])
            if not isinstance(source_columns, list) or not all(
                isinstance(value, str) and value.strip() for value in source_columns
            ):
                raise ValueError
            normalized_columns = {str(value).strip() for value in source_columns}
            result["source_columns"] = sorted(normalized_columns)
            if not expected_columns.issubset(normalized_columns):
                reasons.append("declared_source_columns_incomplete")
        except (TypeError, ValueError, json.JSONDecodeError):
            reasons.append("source_columns_json_invalid")
            normalized_columns = set()
        try:
            coverage_start = _date(item["coverage_start"])
            coverage_end = _date(item["coverage_end"])
            contract_available = _date(item["available_at"])
            if coverage_start > _date(config.history_start_date):
                reasons.append("coverage_starts_after_history_start")
            if coverage_end < _date(config.replay_end_date):
                reasons.append("coverage_ends_before_replay_end")
            # A contract discovered after the first replay decision cannot
            # retroactively prove that decision-time source availability.
            if contract_available > _date(config.replay_start_date):
                reasons.append("contract_available_after_replay_start")
        except (TypeError, ValueError):
            reasons.append("coverage_or_available_date_invalid")

        try:
            verification_value = int(item[verification_field])
        except (TypeError, ValueError):
            verification_value = 0
        if verification_value != 1:
            reasons.append(f"{verification_field}_not_verified")

        try:
            content = _read_source_content_snapshot(
                path,
                component=component,
                source_table=str(item["source_table"]),
                symbols=config.symbols,
                history_start=_date(config.history_start_date),
                replay_end=_date(config.replay_end_date),
            )
            result.update(
                {
                    "content_digest": content["digest"],
                    "content_row_count": len(content["rows"]),
                    "covered_symbols": list(content["covered_symbols"]),
                    "actual_content_range_start": content["range_start"],
                    "actual_content_range_end": content["range_end"],
                }
            )
            if content["digest"] != item["evidence_hash"]:
                reasons.append("source_content_hash_mismatch")
            if not content["rows"]:
                reasons.append("source_content_rows_empty")
            missing_symbols = sorted(set(config.symbols) - set(content["covered_symbols"]))
            if missing_symbols:
                reasons.append("source_content_symbol_coverage_missing:" + ",".join(missing_symbols))
            if component == "technical":
                reasons.extend(
                    _validate_technical_usage(
                        content["rows"],
                        technical_usage,
                    )
                )
            else:
                corporate_reasons, affected_windows = _validate_corporate_action_windows(
                    content["rows"],
                    label_windows,
                )
                reasons.extend(corporate_reasons)
                unadjusted_label_window_keys.update(affected_windows)
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            reasons.append(f"source_content_read_failed:{type(exc).__name__}")

        try:
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                source_table = str(item["source_table"])
                if source_table not in tables:
                    reasons.append("source_table_missing")
                else:
                    quoted_table = source_table.replace('"', '""')
                    actual_columns = {
                        str(row[1])
                        for row in connection.execute(
                            f'PRAGMA table_info("{quoted_table}")'
                        ).fetchall()
                    }
                    if not expected_columns.issubset(actual_columns):
                        reasons.append("source_table_columns_incomplete")
                    if not normalized_columns.issubset(actual_columns):
                        reasons.append("declared_source_columns_not_in_source_table")
        except (OSError, sqlite3.Error, TypeError, ValueError):
            reasons.append("source_table_schema_unreadable")

        if not reasons:
            result["verified"] = True
            result["reason"] = "source_contract_verified_for_requested_range"
        else:
            result["reason"] = ";".join(dict.fromkeys(reasons))
        contract["summary"][component] = {
            key: value for key, value in result.items() if key != "source_columns"
        }
        contract["summary"][component]["source_columns"] = list(result["source_columns"])

    contract["summary"]["diagnostics"] = diagnostics
    contract["_unadjusted_label_window_keys"] = sorted(unadjusted_label_window_keys)
    contract["fingerprint"] = _hash_payload(contract["summary"])
    return contract


def _read_source_content_snapshot(
    database_path: Path,
    *,
    component: str,
    source_table: str,
    symbols: Sequence[str],
    history_start: date,
    replay_end: date,
) -> dict[str, Any]:
    """Read the exact symbol-scoped source records bound by a contract hash."""

    columns: tuple[str, ...]
    symbol_column: str
    date_columns: tuple[str, ...]
    if component == "technical":
        columns = _TECHNICAL_SOURCE_CONTENT_COLUMNS
        symbol_column = "證券代號"
        date_columns = ("日期",)
    elif component == "corporate_actions":
        columns = _CORPORATE_ACTION_SOURCE_CONTENT_COLUMNS
        symbol_column = "symbol"
        date_columns = ("event_date", "effective_from")
    else:
        raise ValueError(f"unsupported source contract component: {component}")
    quoted_table = source_table.replace('"', '""')
    quoted_columns = ", ".join(f'"{column.replace(chr(34), chr(34) * 2)}"' for column in columns)
    placeholders = ",".join("?" for _ in symbols)
    if not placeholders:
        raise ValueError("source contract requires explicit symbols")
    rows: list[dict[str, Any]] = []
    in_range_rows: list[dict[str, Any]] = []
    with sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        for raw in connection.execute(
            f'SELECT {quoted_columns} FROM "{quoted_table}" '
            f'WHERE "{symbol_column}" IN ({placeholders})',
            tuple(str(symbol) for symbol in symbols),
        ):
            record = {
                column: _canonical_contract_value(value, column=column)
                for column, value in zip(columns, raw)
            }
            symbol = str(record.get(symbol_column) or "").strip()
            if not symbol:
                continue
            parsed_dates = [
                _contract_date(value)
                for column in date_columns
                for value in (record.get(column),)
                if value not in (None, "")
            ]
            if not parsed_dates:
                continue
            rows.append(record)
            if any(history_start <= value <= replay_end for value in parsed_dates):
                in_range_rows.append(record)
    rows.sort(key=lambda row: tuple("" if row.get(column) is None else str(row.get(column)) for column in columns))
    in_range_rows.sort(
        key=lambda row: tuple("" if row.get(column) is None else str(row.get(column)) for column in columns)
    )
    covered_symbols = tuple(sorted({str(row[symbol_column]) for row in in_range_rows if row.get(symbol_column)}))
    content_dates = [
        _contract_date(row.get(column))
        for row in in_range_rows
        for column in date_columns
        if row.get(column) not in (None, "")
    ]
    digest = _hash_payload(
        {
            "component": component,
            "source_table": source_table,
            "columns": list(columns),
            "symbols": sorted(str(symbol) for symbol in symbols),
            "rows": [[row.get(column) for column in columns] for row in rows],
        }
    )
    return {
        "rows": tuple(rows),
        "digest": digest,
        "covered_symbols": covered_symbols,
        "range_start": min(content_dates).isoformat() if content_dates else None,
        "range_end": max(content_dates).isoformat() if content_dates else None,
    }


def _validate_technical_usage(
    rows: Sequence[Mapping[str, Any]],
    technical_usage: Sequence[Mapping[str, str]],
) -> list[str]:
    by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("證券代號") or "").strip(), _contract_date_text(row.get("日期")))
        by_key.setdefault(key, []).append(row)
    reasons: list[str] = []
    for usage in technical_usage:
        symbol = str(usage.get("symbol") or "").strip()
        trading_date = _contract_date_text(usage.get("trading_date"))
        decision_date = _contract_date(usage.get("decision_date"))
        candidates = by_key.get((symbol, trading_date), [])
        if not candidates:
            reasons.append(f"technical_usage_row_missing:{symbol}:{trading_date}")
            continue
        if len(candidates) != 1:
            reasons.append(f"technical_usage_row_duplicate:{symbol}:{trading_date}")
        for candidate in candidates:
            available_at = candidate.get("available_at")
            try:
                if _contract_date(available_at) > decision_date:
                    reasons.append(f"technical_usage_available_after_decision:{symbol}:{trading_date}")
            except (TypeError, ValueError):
                reasons.append(f"technical_usage_available_at_invalid:{symbol}:{trading_date}")
    return list(dict.fromkeys(reasons))


def _validate_corporate_action_windows(
    rows: Sequence[Mapping[str, Any]],
    label_windows: Sequence[Mapping[str, str]],
) -> tuple[list[str], set[tuple[str, str, str]]]:
    reasons: list[str] = []
    affected: set[tuple[str, str, str]] = set()
    actions: list[tuple[str, date, date, Decimal]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        try:
            event_date = _contract_date(row.get("event_date"))
            effective_from = _contract_date(row.get("effective_from"))
            factor = Decimal(str(row.get("adjustment_factor")))
            available_at = _contract_date(row.get("available_at"))
            if factor <= 0:
                raise ValueError("adjustment_factor_not_positive")
            if available_at > effective_from:
                reasons.append(f"corporate_action_available_after_effective:{symbol}:{effective_from}")
            if not symbol:
                raise ValueError("symbol_missing")
        except (InvalidOperation, TypeError, ValueError):
            reasons.append("corporate_action_record_invalid")
            continue
        actions.append((symbol, event_date, effective_from, factor))
    for window in label_windows:
        symbol = str(window.get("symbol") or "").strip()
        decision_date = _contract_date(window.get("decision_date"))
        label_end_date = _contract_date(window.get("label_end_date"))
        key = (symbol, decision_date.isoformat(), label_end_date.isoformat())
        for action_symbol, event_date, effective_from, factor in actions:
            if action_symbol != symbol or factor == Decimal(1):
                continue
            if (
                effective_from >= decision_date
                and effective_from <= label_end_date
                and event_date <= label_end_date
            ):
                affected.add(key)
                reasons.append(
                    "corporate_action_unadjusted_label_window:"
                    f"{symbol}:{decision_date.isoformat()}:{effective_from.isoformat()}"
                )
                break
    return list(dict.fromkeys(reasons)), affected


def _canonical_contract_value(value: Any, *, column: str) -> Any:
    if value is None:
        return None
    if column in {"日期", "event_date", "effective_from"}:
        try:
            return _contract_date(value).isoformat()
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _contract_date_text(value: Any) -> str:
    return _contract_date(value).isoformat()


def _contract_date(value: Any) -> date:
    text = str(value or "").strip()
    if len(text) >= 8 and text[:8].isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return date.fromisoformat(text[:10])


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdefABCDEF" for character in value[7:])
    )


def _lookup_observed_liquidity_cost(
    database_path: str | Path,
    *,
    symbol: str,
    decision_date: date,
    label_end_date: date,
) -> tuple[int | None, str | None]:
    """Read an already matured cost row without writing or fabricating zero."""

    path = Path(database_path).resolve()
    if not path.is_file():
        return None, None
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not {"evidence_events", "evidence_outcomes"}.issubset(tables):
                return None, None
            row = connection.execute(
                """
                SELECT o.liquidity_cost_bp
                FROM evidence_events AS e
                JOIN evidence_outcomes AS o ON o.event_id = e.event_id
                WHERE e.symbol = ?
                  AND e.decision_date IN (?, ?)
                  AND o.window_days = 20
                  AND o.outcome_status = 'ready'
                  AND o.outcome_price_date IN (?, ?)
                  AND o.liquidity_cost_bp IS NOT NULL
                ORDER BY o.calculated_at DESC, o.outcome_id DESC
                LIMIT 1
                """,
                (
                    symbol,
                    decision_date.isoformat(),
                    decision_date.strftime("%Y%m%d"),
                    label_end_date.isoformat(),
                    label_end_date.strftime("%Y%m%d"),
                ),
            ).fetchone()
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return None, None
    if row is None or row[0] is None:
        return None, None
    try:
        cost = int(row[0])
    except (TypeError, ValueError):
        return None, None
    if cost < 0:
        return None, None
    return cost, "evidence_outcomes.liquidity_cost_bp"


def _config_payload(config: RecommendationHistoricalReplayConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "history_start_date": _date(config.history_start_date).isoformat(),
        "replay_start_date": _date(config.replay_start_date).isoformat(),
        "replay_end_date": _date(config.replay_end_date).isoformat(),
        "symbols": list(config.symbols),
        "fixed_round_trip_cost_bp": config.fixed_round_trip_cost_bp,
        "max_decision_dates": config.max_decision_dates,
        "horizon_trading_days": config.horizon_trading_days,
        "industry_index_name_by_symbol": dict(config.industry_index_name_by_symbol),
        "rule_probability_bp": config.rule_probability_bp,
        "rule_baseline_id": config.rule_baseline_id,
        "selection_policy": config.selection_policy,
    }
    if isinstance(config.cost_scenario, RecommendationCostScenario) and config.cost_scenario.is_estimated:
        payload["cost_scenario"] = config.cost_scenario.to_dict()
        payload["cost_scenario_hash"] = config.cost_scenario.scenario_hash
    return payload


def _date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _time_stratified_eligible_dates(
    candidates: Sequence[str],
    *,
    max_decision_dates: int,
    horizon_trading_days: int,
) -> tuple[str, ...]:
    """Select bounded dates across the available history without reading labels.

    The final ``horizon_trading_days`` trading dates are excluded because they
    cannot have a complete forward label inside the replay boundary.  The
    remaining date-only pool is sampled with evenly spaced integer indices;
    this keeps the fallback reproducible and preserves causal time ordering.
    """

    maturable = tuple(candidates[:-horizon_trading_days]) if len(candidates) > horizon_trading_days else ()
    if len(maturable) <= max_decision_dates:
        return maturable
    if max_decision_dates <= 1:
        return maturable[:1]
    indices = sorted(
        {
            (index * (len(maturable) - 1)) // (max_decision_dates - 1)
            for index in range(max_decision_dates)
        }
    )
    return tuple(maturable[index] for index in indices)


def _hash_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
