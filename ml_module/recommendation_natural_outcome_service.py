"""從真實 scheduled prediction capture 產生成熟 forward evidence。

這個 service 與 historical replay 分開：輸入必須是先前由 scheduled live
capture 寫出的 immutable capture；label 只在 evaluation date 已經看得到第
20 個未來收盤後才建立。它不接受 replay dataset，也不接受 caller 直接傳入
return/label，避免把歷史考試或手工數字接到 promotion authority。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from ml_module.recommendation_calibration_evidence import (
    MaturedRecommendationOutcome,
    NaturalEvidenceReceiptReference,
    NaturalForwardEvidenceBuilder,
    _brier_bp,
    _calibration_gap_bp,
    _hash_payload,
    _probability,
    _sha256_file,
    _verify_active_model_capture_payload,
    _verify_capture_payload,
    _verify_source_contract_binding,
    verify_natural_maturity_session_proof,
)
from ml_module.recommendation_calibration_training import (
    recommendation_cost_contract_hash,
    recommendation_label_registry_hash,
)
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenarioError,
    cost_scenario_from_metadata,
    estimate_round_trip_cost,
    verify_estimated_cost_observation,
)


@dataclass(frozen=True)
class RecommendationNaturalOutcomeResult:
    status: str
    reason: str
    capture_path: str
    evaluation_date: str
    matured_sample_count: int
    evidence: NaturalEvidenceReceiptReference | None = None
    diagnostics: tuple[str, ...] = ()
    capture_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-natural-outcome-result.v1",
            "status": self.status,
            "reason": self.reason,
            "capture_path": self.capture_path,
            "capture_paths": list(self.capture_paths),
            "evaluation_date": self.evaluation_date,
            "matured_sample_count": self.matured_sample_count,
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "diagnostics": list(self.diagnostics),
            "historical_replay_is_natural_evidence": False,
        }


class RecommendationNaturalOutcomeService:
    """Mature scheduled captures from the current readable market source."""

    def __init__(
        self,
        provider: MLHistoricalSnapshotProvider,
        *,
        evidence_db_path: str | Path | None = None,
        session_resolver: Any | None = None,
        evaluation_at: datetime | None = None,
    ) -> None:
        self.provider = provider
        self.evidence_db_path = (
            Path(evidence_db_path).resolve()
            if evidence_db_path is not None
            else provider.database_path
        )
        self.session_resolver = session_resolver
        if evaluation_at is not None:
            if evaluation_at.tzinfo is None or evaluation_at.utcoffset() is None:
                raise ValueError("evaluation_at must contain a timezone")
            self.evaluation_at: datetime | None = evaluation_at.astimezone(timezone.utc)
        else:
            self.evaluation_at = None

    def build_evidence(
        self,
        *,
        capture_path: str | Path,
        evaluation_date: str,
        output_path: str | Path,
        required_source_contract: Mapping[str, Any] | None = None,
        max_rows: int = 1_000,
    ) -> RecommendationNaturalOutcomeResult:
        """Build evidence for one immutable capture, using source-derived outcomes."""

        capture_file = Path(capture_path).resolve()
        payload = _read_json(capture_file)
        _verify_capture_payload(payload)
        if required_source_contract is not None:
            gate = _source_contract_gate(required_source_contract)
            if gate is not None and gate[0] is not True:
                return RecommendationNaturalOutcomeResult(
                    status="pending",
                    reason="prospective_source_contract_not_available_for_maturity",
                    capture_path=str(capture_file),
                    capture_paths=(str(capture_file),),
                    evaluation_date=_date(evaluation_date).isoformat(),
                    matured_sample_count=0,
                    diagnostics=(str(gate[1]),),
                )
            _verify_source_contract_binding(
                payload.get("source_contract_binding"),
                require_ready=True,
            )
        evaluation_day = _date(evaluation_date)
        if evaluation_day > datetime.now(ZoneInfo("Asia/Taipei")).date():
            raise ValueError("evaluation_date cannot be future-dated")
        outcomes, pending, diagnostics = self._outcomes_for_capture(
            payload,
            evaluation_day=evaluation_day,
            max_rows=max_rows,
        )
        if not outcomes:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_capture_rows_have_naturally_matured",
                capture_path=str(capture_file),
                capture_paths=(str(capture_file),),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
            )
        evidence = NaturalForwardEvidenceBuilder().build(
            capture=capture_file,
            outcomes=tuple(outcomes),
            evaluation_date=evaluation_day.isoformat(),
            evaluation_at=self.evaluation_at,
            output_path=output_path,
            source_id="scheduled_forward_outcomes_market_source",
        )
        return RecommendationNaturalOutcomeResult(
            status="matured",
            reason="matured_from_read_only_market_source",
            capture_path=str(capture_file),
            capture_paths=(str(capture_file),),
            evaluation_date=evaluation_day.isoformat(),
            matured_sample_count=len(outcomes),
            evidence=evidence,
            diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
        )

    def scan_and_build_evidence(
        self,
        *,
        output_root: str | Path,
        evaluation_date: str,
        output_path: str | Path,
        candidate_id: str | None = None,
        candidate_freeze_hash: str | None = None,
        required_source_contract: Mapping[str, Any] | None = None,
        max_captures: int = 366,
        max_rows: int = 10_000,
    ) -> RecommendationNaturalOutcomeResult:
        """Scan immutable captures for one frozen challenger and aggregate them.

        Captures are filtered by candidate identity before outcomes are
        evaluated. Exact duplicate capture IDs and duplicate
        ``(symbol, decision_date, horizon)`` keys are ignored, so retries or
        copied files cannot manufacture additional matured samples.
        """

        if max_captures <= 0 or max_rows <= 0:
            raise ValueError("scan bounds must be positive")
        evaluation_day = _date(evaluation_date)
        capture_root = Path(output_root).resolve() / "recommendation_learning" / "captures"
        source_contract_gate = _source_contract_gate(required_source_contract)
        if source_contract_gate is not None and source_contract_gate[0] is not True:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="prospective_source_contract_not_available_for_maturity",
                capture_path=str(capture_root),
                capture_paths=(),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=(str(source_contract_gate[1]),),
            )
        expected_contract_file_hash = None
        paths = tuple(sorted(capture_root.rglob("*.json"))) if capture_root.is_dir() else ()
        selected: list[Path] = []
        payloads: list[dict[str, Any]] = []
        seen_capture_ids: set[str] = set()
        diagnostics: list[str] = []
        for path in paths:
            if len(selected) >= max_captures:
                diagnostics.append("max_capture_bound_reached")
                break
            try:
                payload = _read_json(path)
                if payload.get("schema_version") not in {
                    "recommendation-prediction-capture.v2",
                    "recommendation-prediction-capture.v3",
                }:
                    continue
                _verify_capture_payload(payload)
                if candidate_id is not None and str(payload.get("candidate_id")) != candidate_id:
                    continue
                if candidate_freeze_hash is not None and str(payload.get("candidate_freeze_hash")) != candidate_freeze_hash:
                    continue
                if required_source_contract is not None:
                    _verify_source_contract_binding(
                        payload.get("source_contract_binding"),
                        require_ready=True,
                        expected_contract_file_sha256=expected_contract_file_hash,
                    )
                if _date(str(payload["capture_as_of_date"])) > evaluation_day:
                    continue
                capture_id = str(payload["capture_id"])
                if capture_id in seen_capture_ids:
                    diagnostics.append(f"duplicate_capture_ignored:{capture_id}")
                    continue
                seen_capture_ids.add(capture_id)
                selected.append(path.resolve())
                payload["capture_path"] = str(path.resolve())
                payloads.append(payload)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                diagnostics.append(f"capture_skipped:{path.name}:{type(exc).__name__}")

        if not selected:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_matching_frozen_challenger_captures",
                capture_path=str(capture_root),
                capture_paths=(),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple(diagnostics or ["capture_directory_empty"]),
            )

        outcomes: list[MaturedRecommendationOutcome] = []
        pending = 0
        seen_keys: set[tuple[str, str, str, int]] = set()
        for payload in payloads:
            remaining = max_rows - len(outcomes)
            if remaining <= 0:
                diagnostics.append("max_outcome_row_bound_reached")
                break
            rows, row_pending, row_diagnostics = self._outcomes_for_capture(
                payload,
                evaluation_day=evaluation_day,
                max_rows=remaining,
            )
            pending += row_pending
            diagnostics.extend(row_diagnostics)
            for outcome in rows:
                capture_row = next(
                    row
                    for row in payload["rows"]
                    if isinstance(row, Mapping) and str(row.get("row_id")) == outcome.capture_row_id
                )
                key = (
                    str(payload.get("cost_scenario_hash") or "legacy-fixed-round-trip-bp"),
                    str(capture_row["symbol"]),
                    str(capture_row["decision_date"]),
                    20,
                )
                if key in seen_keys:
                    diagnostics.append("duplicate_symbol_decision_horizon_ignored")
                    continue
                seen_keys.add(key)
                outcomes.append(outcome)

        if not outcomes:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_capture_rows_have_naturally_matured",
                capture_path=str(capture_root),
                capture_paths=tuple(str(item) for item in selected),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
            )
        evidence = NaturalForwardEvidenceBuilder().build_many(
            captures=tuple(selected),
            outcomes=tuple(outcomes),
            evaluation_date=evaluation_day.isoformat(),
            evaluation_at=self.evaluation_at,
            output_path=output_path,
            source_id="scheduled_forward_outcomes_market_source",
        )
        return RecommendationNaturalOutcomeResult(
            status="matured",
            reason="matured_from_read_only_market_source_capture_bundle",
            capture_path=str(capture_root),
            capture_paths=tuple(str(item) for item in selected),
            evaluation_date=evaluation_day.isoformat(),
            matured_sample_count=len(outcomes),
            evidence=evidence,
            diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
        )

    def scan_and_build_active_model_evidence(
        self,
        *,
        output_root: str | Path,
        evaluation_date: str,
        output_path: str | Path,
        active_candidate_id: str,
        active_identity_hash: str,
        active_effective_date: str,
        monitoring_window_days: int = 120,
        max_captures: int = 366,
        max_rows: int = 10_000,
    ) -> RecommendationNaturalOutcomeResult:
        """Update natural performance for one active identity only.

        This monitor is intentionally separate from the challenger gate.  It
        can reuse the same read-only market outcome source, but only accepts
        active-model captures whose complete identity and adoption-era window
        match the current pointer.  A later challenger can therefore never
        make the old champion's performance appear current by accident.
        """

        if not active_candidate_id.strip() or not active_identity_hash.strip():
            raise ValueError("active model identity is required")
        if monitoring_window_days <= 0 or max_captures <= 0 or max_rows <= 0:
            raise ValueError("active monitoring bounds must be positive")
        evaluation_day = _date(evaluation_date)
        effective_day = _date(active_effective_date)
        window_start = max(effective_day, evaluation_day - timedelta(days=monitoring_window_days))
        capture_root = Path(output_root).resolve() / "recommendation_learning" / "active_captures"
        selected: list[Path] = []
        payloads: list[dict[str, Any]] = []
        seen_capture_ids: set[str] = set()
        diagnostics: list[str] = []
        paths = tuple(sorted(capture_root.rglob("*.json"))) if capture_root.is_dir() else ()
        for path in paths:
            if len(selected) >= max_captures:
                diagnostics.append("active_monitor_max_capture_bound_reached")
                break
            try:
                payload = _read_json(path)
                _verify_active_model_capture_payload(payload)
                if str(payload.get("active_candidate_id")) != active_candidate_id:
                    continue
                if str(payload.get("active_identity_hash")) != active_identity_hash:
                    continue
                capture_day = _date(str(payload.get("capture_as_of_date")))
                if capture_day < window_start or capture_day > evaluation_day:
                    continue
                capture_id = str(payload.get("capture_id"))
                if capture_id in seen_capture_ids:
                    diagnostics.append(f"active_monitor_duplicate_capture_ignored:{capture_id}")
                    continue
                seen_capture_ids.add(capture_id)
                payload["capture_path"] = str(path.resolve())
                selected.append(path.resolve())
                payloads.append(payload)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                diagnostics.append(f"active_monitor_capture_skipped:{path.name}:{type(exc).__name__}")

        if not selected:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_matching_active_model_captures",
                capture_path=str(capture_root),
                capture_paths=(),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple(diagnostics or ["active_monitor_capture_directory_empty"]),
            )

        outcomes: list[MaturedRecommendationOutcome] = []
        pending = 0
        seen_keys: set[tuple[str, str, str, int]] = set()
        for payload in payloads:
            remaining = max_rows - len(outcomes)
            if remaining <= 0:
                diagnostics.append("active_monitor_max_outcome_row_bound_reached")
                break
            rows, row_pending, row_diagnostics = self._outcomes_for_capture(
                payload,
                evaluation_day=evaluation_day,
                max_rows=remaining,
            )
            pending += row_pending
            diagnostics.extend(f"active_monitor_{item}" for item in row_diagnostics)
            row_by_id = {
                str(row.get("row_id")): row
                for row in payload.get("rows", ())
                if isinstance(row, Mapping)
            }
            for outcome in rows:
                capture_row = row_by_id.get(outcome.capture_row_id)
                if capture_row is None:
                    continue
                key = (
                    str(payload.get("cost_scenario_hash") or "legacy-fixed-round-trip-bp"),
                    str(capture_row.get("symbol")),
                    str(capture_row.get("decision_date")),
                    20,
                )
                if key in seen_keys:
                    diagnostics.append("active_monitor_duplicate_symbol_decision_horizon_ignored")
                    continue
                seen_keys.add(key)
                outcomes.append(outcome)

        if not outcomes:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="no_active_model_rows_have_naturally_matured",
                capture_path=str(capture_root),
                capture_paths=tuple(str(item) for item in selected),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
            )

        comparison_row_by_id: dict[str, Mapping[str, Any]] = {}
        capture_by_row_id: dict[str, Mapping[str, Any]] = {}
        for payload in payloads:
            for row in payload.get("rows", ()):
                if isinstance(row, Mapping) and row.get("row_id"):
                    comparison_row_by_id[str(row["row_id"])] = row
                    capture_by_row_id[str(row["row_id"])] = payload
        comparisons: list[dict[str, Any]] = []
        for outcome in outcomes:
            row = comparison_row_by_id.get(outcome.capture_row_id)
            capture_payload = capture_by_row_id.get(outcome.capture_row_id)
            if row is None or capture_payload is None:
                continue
            try:
                scenario = cost_scenario_from_metadata(
                    capture_payload,
                    fixed_round_trip_cost_bp=(
                        int(capture_payload["fixed_round_trip_cost_bp"])
                        if capture_payload.get("fixed_round_trip_cost_bp") is not None
                        else None
                    ),
                )
            except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
                raise ValueError(f"active capture cost scenario is invalid: {exc}") from exc
            if _date(outcome.label_available_date) > evaluation_day:
                continue
            comparison: dict[str, Any] = {
                "capture_row_id": outcome.capture_row_id,
                "symbol": row.get("symbol"),
                "capture_as_of_date": row.get("decision_date"),
                "feature_as_of_date": row.get("feature_as_of_date"),
                "feature_available_date": row.get("feature_available_date"),
                "feature_values": row.get("feature_values"),
                "label_end_date": outcome.label_end_date,
                "label_available_date": outcome.label_available_date,
                "maturity_session_proof": dict(outcome.session_proof or {}),
                "stock_return_bp": outcome.stock_return_bp,
                "benchmark_return_bp": outcome.benchmark_return_bp,
                "observed_liquidity_cost_bp": outcome.observed_liquidity_cost_bp,
                "observed_liquidity_cost_source": outcome.observed_liquidity_cost_source,
                "probability_transform_id": row.get("probability_transform_id"),
                "probability_baseline_id": row.get("probability_baseline_id"),
                "probability_baseline_kind": row.get("probability_baseline_kind"),
                "probability_lineage": row.get("probability_lineage"),
                "active_probability_bp": int(row["active_probability_bp"]),
                "active_after_cost_probability_bp": row.get("active_after_cost_probability_bp"),
                "active_raw_probability_bp": row.get("active_raw_probability_bp"),
                "active_raw_after_cost_probability_bp": row.get("active_raw_after_cost_probability_bp"),
            }
            comparison["upside_label"] = int(outcome.stock_return_bp > 0)
            if scenario.is_estimated:
                comparison.update(
                    {
                        "cost_scenario_id": outcome.cost_scenario_id or scenario.scenario_id,
                        "cost_scenario_version": outcome.cost_scenario_version or scenario.scenario_version,
                        "cost_scenario_hash": outcome.cost_scenario_hash or scenario.scenario_hash,
                        "cost_basis": outcome.cost_basis or scenario.cost_basis,
                        "cost_policy_id": outcome.cost_policy_id or scenario.policy_id,
                        "cost_policy_version": outcome.cost_policy_version or scenario.policy_version,
                        "policy_estimate_date": outcome.policy_estimate_date or scenario.policy_estimate_date,
                        "market_replay_date": outcome.market_replay_date or row.get("decision_date"),
                        "research_order_amount_twd": outcome.research_order_amount_twd or (
                            str(scenario.research_order_amount_twd)
                            if scenario.research_order_amount_twd is not None
                            else None
                        ),
                        "research_order_quantity_shares": outcome.research_order_quantity_shares or scenario.research_order_quantity_shares,
                        "lot_type": outcome.lot_type or scenario.lot_type,
                        "instrument_type": outcome.instrument_type or scenario.instrument_type,
                        "buy_price_twd": outcome.buy_price_twd,
                        "sell_price_twd": outcome.sell_price_twd,
                        "estimated_buy_cost_twd": outcome.estimated_buy_cost_twd,
                        "estimated_sell_cost_twd": outcome.estimated_sell_cost_twd,
                        "estimated_round_trip_cost_twd": outcome.estimated_round_trip_cost_twd,
                        "estimated_round_trip_cost_bp": outcome.estimated_round_trip_cost_bp,
                        "gross_buy_amount_twd": outcome.gross_buy_amount_twd,
                        "gross_sell_amount_twd": outcome.gross_sell_amount_twd,
                        "net_profit_twd": outcome.net_profit_twd,
                        "cost_estimate_status": outcome.cost_estimate_status,
                        "cost_estimate_diagnostics": list(outcome.cost_estimate_diagnostics),
                    }
                )
                if comparison["cost_scenario_hash"] != scenario.scenario_hash:
                    raise ValueError("active matured outcome cost scenario mismatch")
                gross_buy = _decimal_or_none(outcome.gross_buy_amount_twd)
                gross_sell = _decimal_or_none(outcome.gross_sell_amount_twd)
                buy_cost = _decimal_or_none(outcome.estimated_buy_cost_twd)
                sell_cost = _decimal_or_none(outcome.estimated_sell_cost_twd)
                net_profit = _decimal_or_none(outcome.net_profit_twd)
                if (
                    outcome.cost_estimate_status == "estimated"
                    and gross_buy is not None
                    and gross_sell is not None
                    and buy_cost is not None
                    and sell_cost is not None
                    and net_profit is not None
                ):
                    expected_net = gross_sell - gross_buy - buy_cost - sell_cost
                    if expected_net != net_profit:
                        raise ValueError("active matured outcome exact net profit mismatch")
                    comparison["after_cost_profit_label"] = int(net_profit > 0)
                else:
                    comparison["after_cost_profit_label"] = None
            else:
                if outcome.observed_liquidity_cost_bp is None or outcome.observed_liquidity_cost_source is None:
                    comparison["after_cost_profit_label"] = None
                else:
                    comparison["after_cost_profit_label"] = int(
                        outcome.stock_return_bp
                        > int(capture_payload["fixed_round_trip_cost_bp"]) + outcome.observed_liquidity_cost_bp
                    )
            comparisons.append(comparison)
        if not comparisons:
            return RecommendationNaturalOutcomeResult(
                status="pending",
                reason="active_model_matured_rows_missing_after_filter",
                capture_path=str(capture_root),
                capture_paths=tuple(str(item) for item in selected),
                evaluation_date=evaluation_day.isoformat(),
                matured_sample_count=0,
                diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
            )

        probabilities = [int(row["active_probability_bp"]) for row in comparisons]
        labels = [int(row["upside_label"]) for row in comparisons]
        active_brier = _brier_bp(probabilities, labels)
        active_gap = _calibration_gap_bp(probabilities, labels)
        after_cost_rows = tuple(
            row
            for row in comparisons
            if row.get("after_cost_profit_label") is not None
            and row.get("active_after_cost_probability_bp") is not None
        )
        after_cost_brier: int | None = None
        after_cost_gap: int | None = None
        after_cost_prediction_hash: str | None = None
        estimated_lane = any(
            str(payload.get("cost_basis") or "") == "estimated_research_only"
            for payload in payloads
        )
        after_cost_status = (
            "estimated_fees_tax_only" if estimated_lane and after_cost_rows
            else "estimated_cost_unavailable_or_baseline" if estimated_lane
            else "missing_liquidity_or_baseline"
        )
        if after_cost_rows:
            if not estimated_lane:
                after_cost_status = "observed"
            after_probabilities = [int(row["active_after_cost_probability_bp"]) for row in after_cost_rows]
            after_labels = [int(row["after_cost_profit_label"]) for row in after_cost_rows]
            after_cost_brier = _brier_bp(after_probabilities, after_labels)
            after_cost_gap = _calibration_gap_bp(after_probabilities, after_labels)
            after_cost_prediction_hash = _hash_payload(
                {
                    "row_ids": [row["capture_row_id"] for row in after_cost_rows],
                    "probabilities_bp": after_probabilities,
                }
            )
        capture_ids = [str(payload["capture_id"]) for payload in payloads]
        capture_hashes = [str(payload["capture_hash"]) for payload in payloads]
        fingerprint_rows = [
            {
                "capture_row_id": row["capture_row_id"],
                "label_end_date": row["label_end_date"],
                "label_available_date": row["label_available_date"],
                "stock_return_bp": row["stock_return_bp"],
                "observed_liquidity_cost_bp": row["observed_liquidity_cost_bp"],
                "observed_liquidity_cost_source": row.get("observed_liquidity_cost_source"),
            }
            for row in comparisons
        ]
        if estimated_lane:
            fingerprint_rows = [
                {
                    **row,
                    "observed_liquidity_cost_bp": None,
                    "observed_liquidity_cost_source": None,
                    **{
                        key: comparison.get(key)
                        for key in (
                            "cost_scenario_hash",
                            "policy_estimate_date",
                            "market_replay_date",
                            "buy_price_twd",
                            "sell_price_twd",
                            "estimated_buy_cost_twd",
                            "estimated_sell_cost_twd",
                            "estimated_round_trip_cost_twd",
                            "estimated_round_trip_cost_bp",
                            "gross_buy_amount_twd",
                            "gross_sell_amount_twd",
                            "net_profit_twd",
                            "cost_estimate_status",
                        )
                    },
                }
                for row, comparison in zip(fingerprint_rows, comparisons)
            ]
        comparison_fingerprint = _hash_payload(
            {
                "active_identity_hash": active_identity_hash,
                "capture_ids": capture_ids,
                "rows": fingerprint_rows,
            }
        )
        prediction_hash = _hash_payload(
            {
                "row_ids": [row["capture_row_id"] for row in comparisons],
                "probabilities_bp": probabilities,
            }
        )
        identity = payloads[0].get("active_identity")
        if not isinstance(identity, Mapping):
            raise ValueError("active model identity is missing from capture")
        evidence_id = "active-evidence-" + hashlib.sha256(
            f"{active_identity_hash}|{comparison_fingerprint}|{evaluation_day.isoformat()}".encode("utf-8")
        ).hexdigest()[:24]
        if self.evaluation_at is None:
            raise ValueError("active natural evidence evaluation_at is missing")
        resolver_ids = {
            str(row["maturity_session_proof"].get("resolver_id") or "")
            for row in comparisons
            if isinstance(row.get("maturity_session_proof"), Mapping)
        }
        resolver_versions = {
            str(row["maturity_session_proof"].get("resolver_version") or "")
            for row in comparisons
            if isinstance(row.get("maturity_session_proof"), Mapping)
        }
        if len(resolver_ids) != 1 or len(resolver_versions) != 1:
            raise ValueError("active natural evidence session resolver identity is inconsistent")
        evidence_payload: dict[str, Any] = {
            "schema_version": (
                "recommendation-active-model-forward-evidence.v2"
                if estimated_lane
                else "recommendation-active-model-forward-evidence.v1"
            ),
            "evidence_id": evidence_id,
            "source_id": "scheduled_forward_outcomes_market_source",
            "source_kind": "matured_active_model_prediction_capture",
            "status": "matured",
            "as_of_date": evaluation_day.isoformat(),
            "evaluation_at": self.evaluation_at.isoformat(),
            "maturity_session_resolver_id": next(iter(resolver_ids)),
            "maturity_session_resolver_version": next(iter(resolver_versions)),
            "window_start_date": window_start.isoformat(),
            "window_end_date": evaluation_day.isoformat(),
            "active_identity": dict(identity),
            "active_identity_hash": active_identity_hash,
            "active_candidate_id": active_candidate_id,
            "active_model_id": payloads[0].get("active_model_id"),
            "active_candidate_root": payloads[0].get("active_candidate_root"),
            "active_manifest_hash": payloads[0].get("active_manifest_hash"),
            "active_artifact_hash": payloads[0].get("active_artifact_hash"),
            "active_freeze_hash": payloads[0].get("active_freeze_hash"),
            "active_pointer_version": payloads[0].get("active_pointer_version"),
            "active_effective_date": payloads[0].get("active_effective_date"),
            "feature_registry_hash": payloads[0].get("feature_registry_hash"),
            "feature_schema_hash": payloads[0].get("feature_schema_hash"),
            "feature_schema": payloads[0].get("feature_schema"),
            "label_registry_hash": payloads[0].get("label_registry_hash"),
            "cost_contract_hash": payloads[0].get("cost_contract_hash"),
            "fixed_round_trip_cost_bp": payloads[0].get("fixed_round_trip_cost_bp"),
            "maximum_probability_change_bp": payloads[0].get("maximum_probability_change_bp"),
            "policy_hash": payloads[0].get("policy_hash"),
            "probability_transform_id": payloads[0].get("probability_transform_id"),
            "probability_lineage": payloads[0].get("probability_lineage"),
            "source_capture_ids": capture_ids,
            "source_capture_hashes": capture_hashes,
            "source_capture_paths": [str(item) for item in selected],
            "matured_sample_count": len(comparisons),
            "matured_unique_decision_date_count": len(
                {str(row["capture_as_of_date"])[:10] for row in comparisons}
            ),
            "comparison_sample_fingerprint": comparison_fingerprint,
            "active_prediction_hash": prediction_hash,
            "observed_brier_bp": active_brier,
            "observed_calibration_gap_bp": active_gap,
            "after_cost_evaluation_status": after_cost_status,
            "after_cost_matured_sample_count": len(after_cost_rows),
            "observed_after_cost_brier_bp": after_cost_brier,
            "observed_after_cost_calibration_gap_bp": after_cost_gap,
            "after_cost_prediction_hash": after_cost_prediction_hash,
            "comparisons": comparisons,
        }
        if estimated_lane:
            first_payload = payloads[0]
            evidence_payload.update(
                {
                    key: first_payload.get(key)
                    for key in (
                        "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
                        "cost_basis", "cost_policy_id", "cost_policy_version",
                        "policy_estimate_date", "research_order_amount_twd",
                        "research_order_quantity_shares", "lot_type", "instrument_type",
                    )
                }
            )
            evidence_payload["cost_scenario"] = (
                dict(first_payload["cost_scenario"])
                if isinstance(first_payload.get("cost_scenario"), Mapping)
                else None
            )
            evidence_payload["liquidity_cost_role"] = (
                "diagnostic_only_not_in_fees_tax_only_label"
            )
        evidence_payload["receipt_body_hash"] = _hash_payload(evidence_payload)
        destination = Path(output_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            existing = _read_json(destination)
            if existing != evidence_payload:
                raise RuntimeError("active model evidence receipt conflict")
            temporary.unlink(missing_ok=True)
        else:
            temporary.replace(destination)
        reference = NaturalEvidenceReceiptReference(
            receipt_path=str(destination),
            receipt_hash=_sha256_file(destination),
            evidence_id=evidence_id,
        )
        return RecommendationNaturalOutcomeResult(
            status="matured",
            reason="active_model_matured_from_read_only_market_source",
            capture_path=str(capture_root),
            capture_paths=tuple(str(item) for item in selected),
            evaluation_date=evaluation_day.isoformat(),
            matured_sample_count=len(comparisons),
            evidence=reference,
            diagnostics=tuple([f"pending_rows={pending}", *diagnostics]),
        )

    def _outcomes_for_capture(
        self,
        payload: Mapping[str, Any],
        *,
        evaluation_day: date,
        max_rows: int,
    ) -> tuple[list[MaturedRecommendationOutcome], int, tuple[str, ...]]:
        capture_day = _date(str(payload["capture_as_of_date"]))
        if evaluation_day < capture_day:
            raise ValueError("evaluation_date must follow prediction capture")
        try:
            scenario = cost_scenario_from_metadata(
                payload,
                fixed_round_trip_cost_bp=(
                    int(payload["fixed_round_trip_cost_bp"])
                    if payload.get("fixed_round_trip_cost_bp") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
            raise ValueError(f"capture cost scenario is invalid: {exc}") from exc
        rows = payload.get("rows")
        if not isinstance(rows, list) or len(rows) > max_rows:
            raise ValueError("capture row count exceeds bounded outcome limit")
        symbols = tuple(sorted({str(row["symbol"]) for row in rows if isinstance(row, Mapping)}))
        if not symbols:
            raise ValueError("prediction capture has no symbols")
        session_resolution, session_reason = self._resolve_maturity_sessions(
            capture_day,
            evaluation_day,
        )
        if session_resolution is None:
            return [], len(rows), (session_reason,)
        endpoint_date, session_proof = session_resolution
        if _date(endpoint_date) > evaluation_day:
            return [], len(rows), ("natural_maturity_endpoint_after_evaluation",)
        if not self._source_database_snapshot_matches(session_proof):
            return [], len(rows), ("natural_maturity_source_database_snapshot_mismatch",)
        forward = self.provider.load_forward_price_window(
            start_date=capture_day.isoformat(),
            end_date=evaluation_day.isoformat(),
            symbols=symbols,
        )
        if not self._source_database_snapshot_matches(session_proof):
            return [], len(rows), ("natural_maturity_source_database_snapshot_changed",)
        prices_by_symbol: dict[str, list[Any]] = {}
        for row in forward.prices:
            prices_by_symbol.setdefault(row.symbol, []).append(row)
        outcomes: list[MaturedRecommendationOutcome] = []
        pending = 0
        diagnostics: list[str] = []
        for capture_row in rows:
            if not isinstance(capture_row, Mapping):
                raise ValueError("prediction capture row is invalid")
            symbol = str(capture_row.get("symbol") or "")
            end_rows = [
                row
                for row in prices_by_symbol.get(symbol, ())
                if str(row.trading_date)[:10] == endpoint_date
            ]
            if len(end_rows) != 1 or not self._positive_price(end_rows[0].close_price):
                diagnostics.append(
                    f"natural_maturity_endpoint_stock_close_invalid:{symbol}:{endpoint_date}"
                )
                pending += 1
                continue
            end_row = end_rows[0]
            start_rows = [
                row
                for row in prices_by_symbol.get(symbol, ())
                if str(row.trading_date)[:10] == capture_day.isoformat()
            ]
            if len(start_rows) != 1 or not self._positive_price(start_rows[0].close_price):
                diagnostics.append(
                    f"natural_maturity_capture_stock_close_invalid:{symbol}:{capture_day.isoformat()}"
                )
                pending += 1
                continue
            start_row = start_rows[0]
            benchmark_start = self._session_market_close(
                session_proof,
                capture_day.isoformat(),
            )
            benchmark_end = self._session_market_close(session_proof, endpoint_date)
            if benchmark_start is None or benchmark_end is None:
                diagnostics.append(
                    f"natural_maturity_verified_market_close_missing:{symbol}:{endpoint_date}"
                )
                pending += 1
                continue
            observed_liquidity_cost, liquidity_source = self._lookup_liquidity_cost(
                symbol=symbol,
                decision_date=capture_day,
                label_end_date=_date(end_row.trading_date),
            )
            if observed_liquidity_cost is None:
                diagnostics.append(
                    f"observed_liquidity_missing_diagnostic_only:{symbol}:{capture_day.isoformat()}"
                    if scenario.is_estimated
                    else f"liquidity_cost_missing:{symbol}:{capture_day.isoformat()}"
                )
            cost_estimate = estimate_round_trip_cost(
                scenario,
                market_replay_date=capture_day,
                buy_price_twd=start_row.close_price,
                sell_price_twd=end_row.close_price,
            )
            if scenario.is_estimated and not cost_estimate.available:
                diagnostics.append(
                    f"estimated_fee_tax_cost_unavailable:{symbol}:{capture_day.isoformat()}"
                )
            outcomes.append(
                MaturedRecommendationOutcome(
                    capture_row_id=str(capture_row["row_id"]),
                    label_end_date=end_row.trading_date,
                    label_available_date=end_row.trading_date,
                    stock_return_bp=_return_bp(start_row.close_price, end_row.close_price),
                    observed_liquidity_cost_bp=observed_liquidity_cost,
                    benchmark_return_bp=_return_bp(benchmark_start, benchmark_end),
                    observed_liquidity_cost_source=liquidity_source,
                    buy_price_twd=str(start_row.close_price),
                    sell_price_twd=str(end_row.close_price),
                    cost_scenario_id=cost_estimate.scenario_id,
                    cost_scenario_version=cost_estimate.scenario_version,
                    cost_scenario_hash=cost_estimate.scenario_hash,
                    cost_basis=cost_estimate.cost_basis,
                    cost_policy_id=scenario.policy_id,
                    cost_policy_version=scenario.policy_version,
                    policy_estimate_date=cost_estimate.policy_estimate_date,
                    market_replay_date=cost_estimate.market_replay_date,
                    research_order_amount_twd=cost_estimate.research_order_amount_twd,
                    research_order_quantity_shares=cost_estimate.research_order_quantity_shares,
                    lot_type=scenario.lot_type,
                    instrument_type=scenario.instrument_type,
                    estimated_buy_cost_twd=cost_estimate.estimated_buy_cost_twd,
                    estimated_sell_cost_twd=cost_estimate.estimated_sell_cost_twd,
                    estimated_round_trip_cost_twd=cost_estimate.estimated_round_trip_cost_twd,
                    estimated_round_trip_cost_bp=cost_estimate.estimated_round_trip_cost_bp,
                    gross_buy_amount_twd=cost_estimate.gross_buy_amount_twd,
                    gross_sell_amount_twd=cost_estimate.gross_sell_amount_twd,
                    net_profit_twd=cost_estimate.net_profit_twd,
                    cost_estimate_status=cost_estimate.status,
                    cost_estimate_diagnostics=cost_estimate.diagnostics,
                    session_proof=dict(session_proof),
                )
            )
        return outcomes, pending, tuple(diagnostics)

    @staticmethod
    def _positive_price(value: Any) -> bool:
        try:
            parsed = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return False
        return parsed.is_finite() and parsed > 0

    @staticmethod
    def _session_market_close(
        proof: Mapping[str, Any],
        date_text: str,
    ) -> Decimal | None:
        market = proof.get("market")
        if not isinstance(market, Mapping):
            return None
        observations = market.get("observations")
        candidates: list[Any] = []
        if isinstance(observations, list):
            candidates.extend(
                item
                for item in observations
                if isinstance(item, Mapping) and str(item.get("date") or "")[:10] == date_text
            )
        for key in ("capture_observation", "baseline_observation"):
            item = market.get(key)
            if isinstance(item, Mapping) and str(item.get("date") or "")[:10] == date_text:
                candidates.append(item)
        if len(candidates) != 1:
            return None
        value = candidates[0].get("close")
        try:
            parsed = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() and parsed > 0 else None

    def _source_database_snapshot_matches(
        self,
        proof: Mapping[str, Any],
    ) -> bool:
        """確認 resolver proof 與同一個 provider SQLite snapshot 一致。"""

        market = proof.get("market")
        if not isinstance(market, Mapping):
            return False
        source_path = market.get("source_db_path")
        source_stat = market.get("source_db_stat")
        if not isinstance(source_path, str) or not isinstance(source_stat, Mapping):
            return False
        provider_path = getattr(self.provider, "database_path", None)
        if provider_path is None:
            return False
        try:
            expected_path = Path(source_path).expanduser().resolve()
            actual_path = Path(provider_path).expanduser().resolve()
            stat = actual_path.stat()
        except (OSError, TypeError, ValueError):
            return False
        if expected_path != actual_path:
            return False
        size = source_stat.get("size")
        mtime_ns = source_stat.get("mtime_ns")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (size, mtime_ns)
        ):
            return False
        return (stat.st_size, stat.st_mtime_ns) == (size, mtime_ns)

    def _resolve_maturity_sessions(
        self,
        capture_day: date,
        evaluation_day: date | None = None,
    ) -> tuple[tuple[str, Mapping[str, Any]] | None, str]:
        """在定價前解析並保管官方交易日 horizon。"""

        if self.session_resolver is None:
            return None, "natural_maturity_session_resolver_missing"
        if self.evaluation_at is None:
            return None, "natural_maturity_evaluation_at_missing"
        if evaluation_day is None:
            evaluation_day = self.evaluation_at.astimezone(
                ZoneInfo("Asia/Taipei")
            ).date()
        if self.evaluation_at.astimezone(ZoneInfo("Asia/Taipei")).date() != evaluation_day:
            return None, "natural_maturity_evaluation_clock_mismatch"
        if self.evaluation_at > datetime.now(timezone.utc):
            return None, "natural_maturity_evaluation_at_future"
        try:
            resolution = self.session_resolver.resolve(
                capture_date=capture_day.isoformat(),
                evaluation_at=self.evaluation_at,
                horizon_sessions=20,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return None, f"natural_maturity_session_resolution_failed:{type(exc).__name__}"
        status = str(getattr(resolution, "status", "") or "")
        reason = str(getattr(resolution, "reason", "") or "")
        if status != "ready":
            return None, (
                f"natural_maturity_session_{status or 'unknown'}"
                + (f":{reason}" if reason else "")
            )
        endpoint_value = getattr(resolution, "endpoint_date", None)
        proof_value = getattr(resolution, "proof", None)
        if not endpoint_value or not isinstance(proof_value, Mapping) or not proof_value:
            return None, "natural_maturity_session_proof_missing"
        try:
            endpoint = _date(str(endpoint_value)).isoformat()
        except ValueError:
            return None, "natural_maturity_session_endpoint_invalid"
        return (endpoint, dict(proof_value)), "natural_maturity_session_ready"

    def _lookup_liquidity_cost(
        self,
        *,
        symbol: str,
        decision_date: date,
        label_end_date: date,
    ) -> tuple[int | None, str | None]:
        """Read an existing EvidenceOutcome cost without creating or changing data."""

        path = self.evidence_db_path
        if not path.is_file():
            return None, None
        try:
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not {"evidence_events", "evidence_outcomes"}.issubset(tables):
                    return None, None
                date_text = decision_date.isoformat()
                compact_date = decision_date.strftime("%Y%m%d")
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
                        date_text,
                        compact_date,
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


def verify_active_model_evidence_payload(
    payload: Mapping[str, Any],
    *,
    active_candidate_id: str,
    active_identity_hash: str,
    decision_date: str,
    expected_db_path: str | Path | None = None,
) -> None:
    """Verify monitor-receipt integrity and recompute its reported metrics."""

    required = (
        "schema_version", "evidence_id", "status", "as_of_date", "window_start_date",
        "window_end_date", "active_identity", "active_identity_hash", "active_candidate_id",
        "source_capture_ids", "source_capture_hashes", "source_capture_paths",
        "matured_sample_count", "matured_unique_decision_date_count",
        "comparison_sample_fingerprint", "active_prediction_hash", "observed_brier_bp",
        "observed_calibration_gap_bp", "comparisons", "receipt_body_hash",
        "evaluation_at", "maturity_session_resolver_id",
        "maturity_session_resolver_version",
    )
    if any(key not in payload for key in required):
        raise ValueError("active model evidence metadata is incomplete")
    if payload.get("schema_version") not in {
        "recommendation-active-model-forward-evidence.v1",
        "recommendation-active-model-forward-evidence.v2",
    }:
        raise ValueError("active model evidence schema is unsupported")
    if payload.get("status") != "matured":
        raise ValueError("active model evidence is not matured")
    if expected_db_path is None:
        raise ValueError("active model evidence source database anchor is missing")
    body = {key: value for key, value in payload.items() if key != "receipt_body_hash"}
    if _hash_payload(body) != payload.get("receipt_body_hash"):
        raise ValueError("active model evidence receipt hash mismatch")
    try:
        scenario = cost_scenario_from_metadata(
            payload,
            fixed_round_trip_cost_bp=(
                int(payload["fixed_round_trip_cost_bp"])
                if payload.get("fixed_round_trip_cost_bp") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
        raise ValueError(f"active model evidence cost scenario is invalid: {exc}") from exc
    if payload.get("schema_version") == "recommendation-active-model-forward-evidence.v2" and not scenario.is_estimated:
        raise ValueError("active model evidence v2 must use estimated cost scenario")
    if payload.get("schema_version") == "recommendation-active-model-forward-evidence.v1" and scenario.is_estimated:
        raise ValueError("active model evidence v1 cannot use estimated cost scenario")
    expected_label_hash = _expected_label_registry_hash(scenario)
    if payload.get("label_registry_hash") not in (None, expected_label_hash):
        raise ValueError("active model evidence label registry contract mismatch")
    expected_cost_hash = _expected_cost_contract_hash(scenario)
    if payload.get("cost_contract_hash") not in (None, expected_cost_hash):
        raise ValueError("active model evidence cost contract mismatch")
    if str(payload.get("active_candidate_id")) != active_candidate_id:
        raise ValueError("active model evidence candidate identity mismatch")
    if str(payload.get("active_identity_hash")) != active_identity_hash:
        raise ValueError("active model evidence active identity hash mismatch")
    evaluation_day = _date(str(payload.get("as_of_date")))
    evaluation_at = _strict_evaluation_at(str(payload.get("evaluation_at")))
    if evaluation_at.astimezone(ZoneInfo("Asia/Taipei")).date() != evaluation_day:
        raise ValueError("active model evidence evaluation clock mismatch")
    if evaluation_at > datetime.now(timezone.utc):
        raise ValueError("active model evidence evaluation clock is future-dated")
    cutoff = _date(decision_date)
    if evaluation_day > cutoff:
        raise ValueError("active model evidence is after decision cutoff")
    window_start = _date(str(payload.get("window_start_date")))
    window_end = _date(str(payload.get("window_end_date")))
    if window_start > window_end or window_end > evaluation_day:
        raise ValueError("active model evidence window is invalid")
    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise ValueError("active model evidence comparisons are missing")
    capture_ids = payload.get("source_capture_ids")
    capture_hashes = payload.get("source_capture_hashes")
    capture_paths = payload.get("source_capture_paths")
    if not (
        isinstance(capture_ids, list)
        and isinstance(capture_hashes, list)
        and isinstance(capture_paths, list)
        and len(capture_ids) == len(capture_hashes) == len(capture_paths) > 0
    ):
        raise ValueError("active model evidence source capture index is invalid")
    source_rows: dict[str, Mapping[str, Any]] = {}
    for capture_id, capture_hash, capture_path in zip(capture_ids, capture_hashes, capture_paths):
        path = Path(str(capture_path)).resolve()
        capture_payload = _read_json(path)
        _verify_active_model_capture_payload(capture_payload)
        if str(capture_payload.get("capture_id")) != str(capture_id):
            raise ValueError("active model evidence source capture identity mismatch")
        if str(capture_payload.get("capture_hash")) != str(capture_hash):
            raise ValueError("active model evidence source capture hash mismatch")
        if str(capture_payload.get("active_identity_hash")) != active_identity_hash:
            raise ValueError("active model evidence source active identity mismatch")
        if str(capture_payload.get("cost_scenario_hash") or scenario.scenario_hash) != scenario.scenario_hash:
            raise ValueError("active model evidence source cost scenario mismatch")
        for row in capture_payload.get("rows", ()):
            if isinstance(row, Mapping) and row.get("row_id"):
                source_rows[str(row["row_id"])] = row
    row_ids = [str(row.get("capture_row_id") or "") for row in comparisons if isinstance(row, Mapping)]
    if len(row_ids) != len(comparisons) or len(row_ids) != len(set(row_ids)):
        raise ValueError("active model evidence comparison row ids are invalid")
    normalized_rows: list[dict[str, Any]] = []
    probabilities: list[int] = []
    labels: list[int] = []
    after_cost_rows: list[Mapping[str, Any]] = []
    for comparison in comparisons:
        if not isinstance(comparison, Mapping):
            raise ValueError("active model evidence comparison is invalid")
        source_row = source_rows.get(str(comparison["capture_row_id"]))
        if source_row is None:
            raise ValueError("active model evidence comparison source row is missing")
        if comparison.get("active_probability_bp") != source_row.get("active_probability_bp"):
            raise ValueError("active model evidence probability differs from source capture")
        if comparison.get("symbol") != source_row.get("symbol"):
            raise ValueError("active model evidence symbol differs from source capture")
        session_proof = comparison.get("maturity_session_proof")
        if not isinstance(session_proof, Mapping):
            raise ValueError("active model evidence official session proof is missing")
        try:
            verified_proof = verify_natural_maturity_session_proof(
                session_proof,
                capture_date=str(comparison.get("capture_as_of_date") or ""),
                label_end_date=str(comparison.get("label_end_date") or ""),
                evaluation_at=evaluation_at,
                expected_db_path=expected_db_path,
            )
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ValueError("active model evidence official session proof is invalid") from exc
        if (
            verified_proof.get("resolver_id") != payload.get("maturity_session_resolver_id")
            or verified_proof.get("resolver_version")
            != payload.get("maturity_session_resolver_version")
        ):
            raise ValueError("active model evidence session resolver identity mismatch")
        probability = int(comparison["active_probability_bp"])
        label = int(comparison["upside_label"])
        _probability(probability, "active_probability_bp")
        if label not in {0, 1}:
            raise ValueError("active model evidence label is invalid")
        probabilities.append(probability)
        labels.append(label)
        if scenario.is_estimated:
            verify_estimated_cost_observation(
                scenario,
                comparison,
                expected_market_replay_date=str(comparison.get("capture_as_of_date")),
            )
        if (
            comparison.get("after_cost_profit_label") is not None
            and comparison.get("active_after_cost_probability_bp") is not None
        ):
            after_cost_rows.append(comparison)
        normalized_row = {
                "capture_row_id": comparison["capture_row_id"],
                "label_end_date": comparison["label_end_date"],
                "label_available_date": comparison["label_available_date"],
                "stock_return_bp": comparison["stock_return_bp"],
                "observed_liquidity_cost_bp": comparison["observed_liquidity_cost_bp"],
                "observed_liquidity_cost_source": comparison.get("observed_liquidity_cost_source"),
            }
        if scenario.is_estimated:
            normalized_row.update(
                {
                    key: comparison.get(key)
                    for key in (
                        "cost_scenario_hash", "policy_estimate_date", "market_replay_date",
                        "estimated_buy_cost_twd", "estimated_sell_cost_twd",
                        "estimated_round_trip_cost_twd", "estimated_round_trip_cost_bp",
                        "gross_buy_amount_twd", "gross_sell_amount_twd", "net_profit_twd",
                        "cost_estimate_status",
                    )
                }
            )
            normalized_row["observed_liquidity_cost_bp"] = None
            normalized_row["observed_liquidity_cost_source"] = None
        normalized_rows.append(normalized_row)
    unique_dates = {str(row.get("capture_as_of_date"))[:10] for row in comparisons}
    expected_fingerprint = _hash_payload(
        {
            "active_identity_hash": active_identity_hash,
            "capture_ids": [str(value) for value in capture_ids],
            "rows": normalized_rows,
        }
    )
    if expected_fingerprint != payload.get("comparison_sample_fingerprint"):
        raise ValueError("active model evidence comparison fingerprint mismatch")
    expected_prediction_hash = _hash_payload(
        {"row_ids": row_ids, "probabilities_bp": probabilities}
    )
    if expected_prediction_hash != payload.get("active_prediction_hash"):
        raise ValueError("active model evidence prediction hash mismatch")
    if int(payload.get("matured_sample_count", -1)) != len(comparisons):
        raise ValueError("active model evidence sample count mismatch")
    if int(payload.get("matured_unique_decision_date_count", -1)) != len(unique_dates):
        raise ValueError("active model evidence decision-date count mismatch")
    if int(payload.get("observed_brier_bp", -1)) != _brier_bp(probabilities, labels):
        raise ValueError("active model evidence Brier metric mismatch")
    if int(payload.get("observed_calibration_gap_bp", -1)) != _calibration_gap_bp(probabilities, labels):
        raise ValueError("active model evidence calibration gap mismatch")
    if after_cost_rows:
        after_probabilities = [int(row["active_after_cost_probability_bp"]) for row in after_cost_rows]
        after_labels = [int(row["after_cost_profit_label"]) for row in after_cost_rows]
        if int(payload.get("observed_after_cost_brier_bp", -1)) != _brier_bp(after_probabilities, after_labels):
            raise ValueError("active model evidence after-cost Brier metric mismatch")
        if int(payload.get("observed_after_cost_calibration_gap_bp", -1)) != _calibration_gap_bp(
            after_probabilities, after_labels
        ):
            raise ValueError("active model evidence after-cost calibration gap mismatch")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prediction capture must be a JSON object")
    return payload


def _expected_label_registry_hash(scenario: Any) -> str:
    return recommendation_label_registry_hash(
        cost_scenario=scenario if getattr(scenario, "is_estimated", False) else None
    )


def _expected_cost_contract_hash(scenario: Any) -> str:
    return recommendation_cost_contract_hash(
        getattr(scenario, "fixed_round_trip_cost_bp", None),
        cost_scenario=scenario if getattr(scenario, "is_estimated", False) else None,
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _return_bp(start: Any, end: Any) -> int:
    from decimal import Decimal, ROUND_HALF_EVEN

    start_decimal = start if isinstance(start, Decimal) else Decimal(str(start))
    end_decimal = end if isinstance(end, Decimal) else Decimal(str(end))
    return int(((end_decimal / start_decimal - Decimal(1)) * Decimal(10_000)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def _strict_evaluation_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("session-bound evaluation_at must contain a timezone")
    return parsed.astimezone(timezone.utc)


def _date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _source_contract_gate(
    audit: Mapping[str, Any] | None,
) -> tuple[bool, str] | None:
    """Signal that scheduled maturity must require a capture source binding.

    The binding is evaluated at prediction time and remains immutable.  A new
    day's source-contract receipt must not retroactively replace yesterday's
    cutoff, so this helper deliberately does not compare captures to today's
    contract hash.
    """

    if audit is None:
        return None
    if not isinstance(audit.get("source_contract"), Mapping):
        return False, "prospective_source_contract_audit_missing"
    receipt = audit.get("source_contract_receipt")
    if not isinstance(receipt, Mapping) or not str(receipt.get("contract_path") or ""):
        return False, "prospective_source_contract_receipt_missing"
    return True, ""
