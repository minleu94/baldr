from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.recommendation_calibration_authority import (
    RecommendationCalibrationPromotionAuthority,
    RecommendationPromotionPolicy,
)
from ml_module.recommendation_calibration_evidence import (
    RecommendationPredictionCaptureInput,
    RecommendationPredictionCaptureService,
    _hash_payload,
    _verify_capture_document,
)
from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    RecommendationCalibrationTrainingService,
    recommendation_cost_contract_hash,
    sample_payload,
)
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenarioError,
    build_banktaiwan_cost_scenario,
    build_legacy_cost_scenario,
    estimate_round_trip_cost,
    verify_estimated_cost_observation,
)
from ml_module.recommendation_historical_replay import (
    RecommendationHistoricalReplayConfig,
    RecommendationHistoricalReplayService,
)
from ml_module.recommendation_natural_outcome_service import RecommendationNaturalOutcomeService
from scripts.scheduled import run_daily_recommendation_learning as daily_learning


FEATURE_NAMES = ("momentum_bp", "volume_ratio_bp")
FEATURE_SCHEMA = (("momentum_bp", "int", "bp"), ("volume_ratio_bp", "int", "bp"))
FEATURE_REGISTRY_HASH = "sha256:" + "3" * 64
LEGACY_COST_CONTRACT_HASH = "sha256:8d05ee367ecec23c5b4d9951fd44221ad2758d314563d655ca7aeb9c2a3e33c2"
LEGACY_CANDIDATE = Path(
    "D:/Min/Python/Project/FA_Data_Shadow/recommendation_learning/runs/2026-09-14/"
    "scheduled-snapshot-5f4de77ffb404af2-eff4d2a/candidates/"
    "rec-cal-29c1b6129396a3885a89d080/candidate.json"
)
LEGACY_CAPTURE = Path(
    "D:/Min/Python/Project/FA_Data_Shadow/recommendation_learning/captures/2026-09-14/"
    "scheduled-capture-5f4de77ffb404af2/"
    "rec-cal-29c1b6129396a3885a89d080-850760d54413e019199be668.json"
)


def _return_bp(start: Decimal, end: Decimal) -> int:
    return int(((end / start - Decimal("1")) * Decimal("10000")).to_integral_value())


def _make_replay_database(path: Path, *, days: int = 180) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE daily_prices (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            成交股數 INTEGER,
            成交金額 INTEGER,
            開盤價 TEXT,
            最高價 TEXT,
            最低價 TEXT,
            收盤價 TEXT
        );
        CREATE TABLE technical_indicators (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            RSI TEXT,
            MACD TEXT,
            ADX TEXT
        );
        CREATE TABLE market_indices (
            日期 TEXT NOT NULL,
            收盤指數 TEXT,
            收盤價 TEXT
        );
        CREATE TABLE industry_indices (
            日期 TEXT NOT NULL,
            指數名稱 TEXT,
            收盤指數 TEXT
        );
        """
    )
    start = date(2026, 1, 1)
    for offset in range(days):
        current = (start + timedelta(days=offset)).isoformat()
        market = Decimal("10000") + Decimal(offset)
        connection.execute(
            "INSERT INTO market_indices VALUES (?, ?, ?)",
            (current.replace("-", ""), str(market), str(market)),
        )
        for symbol_index, symbol in enumerate(("1101", "2330")):
            if symbol_index == 0:
                close = Decimal("100") + Decimal(offset % 40)
            else:
                close = Decimal("160") + Decimal((offset * 5) % 70)
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    current.replace("-", ""),
                    symbol,
                    100_000 + offset,
                    int(close * 1_000),
                    str(close),
                    str(close + Decimal("1")),
                    str(close - Decimal("1")),
                    str(close),
                ),
            )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
                (current.replace("-", ""), symbol, "55", "1.5", "20"),
            )
    connection.commit()
    connection.close()


def _make_cli_database(path: Path, *, days: int = 360) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE daily_prices (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            成交股數 INTEGER,
            成交金額 INTEGER,
            開盤價 TEXT,
            最高價 TEXT,
            最低價 TEXT,
            收盤價 TEXT
        );
        CREATE TABLE technical_indicators (
            日期 TEXT NOT NULL,
            證券代號 TEXT NOT NULL,
            RSI TEXT,
            MACD TEXT,
            ADX TEXT
        );
        CREATE TABLE market_indices (
            日期 TEXT NOT NULL,
            收盤指數 TEXT,
            收盤價 TEXT
        );
        CREATE TABLE industry_indices (
            日期 TEXT NOT NULL,
            指數名稱 TEXT,
            收盤指數 TEXT
        );
        """
    )
    start = date(2014, 1, 1)
    for offset in range(days):
        current = (start + timedelta(days=offset)).isoformat().replace("-", "")
        market = 10_000 + offset
        connection.execute(
            "INSERT INTO market_indices VALUES (?, ?, ?)",
            (current, str(market), str(market)),
        )
        prices = {
            "1101": Decimal("100") + Decimal(offset % 40),
            "2330": Decimal("160") + Decimal((offset * 5) % 70),
        }
        for symbol, close in prices.items():
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    current,
                    symbol,
                    100_000 + offset,
                    int(close * 1_000),
                    str(close),
                    str(close + Decimal("1")),
                    str(close - Decimal("1")),
                    str(close),
                ),
            )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
                (current, symbol, "55", "1.5", "20"),
            )
    connection.commit()
    connection.close()


def _estimated_samples(
    scenario,
    *,
    date_count: int = 90,
) -> tuple[RecommendationCalibrationSample, ...]:
    rows: list[RecommendationCalibrationSample] = []
    start = date(2025, 8, 1)
    for day_index in range(date_count):
        decision = start + timedelta(days=day_index)
        for symbol_index, symbol in enumerate(("1101", "2330")):
            buy_price = Decimal("100") + Decimal(day_index % 20) + Decimal(symbol_index * 10)
            direction = (
                Decimal("2.00")
                if (day_index + symbol_index) % 20 < 11
                else Decimal("-2.00")
            )
            sell_price = buy_price + direction
            estimate = estimate_round_trip_cost(
                scenario,
                market_replay_date=decision.isoformat(),
                buy_price_twd=buy_price,
                sell_price_twd=sell_price,
            )
            assert estimate.status in {"estimated", "unavailable"}
            rows.append(
                RecommendationCalibrationSample.from_forward_return(
                    row_id=f"estimated:{decision.isoformat()}:{symbol}",
                    symbol=symbol,
                    decision_date=decision.isoformat(),
                    feature_as_of_date=(decision - timedelta(days=1)).isoformat(),
                    feature_available_date=(decision - timedelta(days=1)).isoformat(),
                    label_end_date=(decision + timedelta(days=20)).isoformat(),
                    label_available_date=(decision + timedelta(days=20)).isoformat(),
                    feature_values=(
                        (day_index - 30) * 100 + symbol_index * 30,
                        1_000 + (day_index % 7) * 100,
                    ),
                    stock_return_bp=_return_bp(buy_price, sell_price),
                    benchmark_return_bp=100,
                    fixed_round_trip_cost_bp=None,
                    # This intentionally extreme value proves that the new
                    # fees/tax-only label does not consume observed liquidity.
                    observed_liquidity_cost_bp=9_999,
                    rule_probability_bp=5_000,
                    rule_after_cost_probability_bp=5_000,
                    cost_scenario=scenario,
                    cost_estimate=estimate,
                )
            )
    return tuple(rows)


def _fit_estimated_candidate(
    tmp_path: Path,
    *,
    scenario=None,
):
    scenario = scenario or build_banktaiwan_cost_scenario(
        research_order_quantity_shares=1_000
    )
    result = RecommendationCalibrationTrainingService().fit(
        dataset_id="estimated-dataset-v1",
        dataset_hash="sha256:" + "a" * 64,
        samples=_estimated_samples(scenario),
        feature_names=FEATURE_NAMES,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        training_as_of="2026-01-01",
        fixed_round_trip_cost_bp=None,
        cost_scenario=scenario,
        dataset_quality={"formal_candidate_eligible": True},
        created_at="2026-01-01T00:00:00+00:00",
        config=RecommendationCalibrationTrainingConfig(
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )
    candidate_root = tmp_path / "candidate"
    result.persist(candidate_root)
    metadata = json.loads((candidate_root / "candidate.json").read_text(encoding="utf-8"))
    return scenario, result, candidate_root, metadata


def _persist_estimated_captures(
    tmp_path: Path,
    *,
    scenario,
    candidate_root: Path,
    policy_hash: str,
    capture_days: tuple[date, ...],
) -> tuple[Path, ...]:
    service = RecommendationPredictionCaptureService()
    paths: list[Path] = []
    for index, capture_day in enumerate(capture_days):
        day_text = capture_day.isoformat()
        capture = service.capture(
            candidate_root=candidate_root,
            feature_schema=FEATURE_SCHEMA,
            feature_registry_hash=FEATURE_REGISTRY_HASH,
            policy_hash=policy_hash,
            decision_date=day_text,
            captured_at=f"{day_text}T09:00:00+00:00",
            inputs=(
                RecommendationPredictionCaptureInput(
                    row_id=f"forward-estimated-{day_text}-1101",
                    symbol="1101",
                    decision_date=day_text,
                    feature_as_of_date=(capture_day - timedelta(days=1)).isoformat(),
                    feature_available_date=(capture_day - timedelta(days=1)).isoformat(),
                    feature_values=(100, 1_000),
                    rule_probability_bp=5_000,
                    rule_after_cost_probability_bp=5_000,
                ),
            ),
            fixed_round_trip_cost_bp=None,
            cost_scenario=scenario,
        )
        path = (
            tmp_path
            / "recommendation_learning"
            / "captures"
            / day_text
            / f"capture-{index:02d}.json"
        )
        capture.persist(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        _verify_capture_document(payload)
        paths.append(path)
    return tuple(paths)


def _estimated_evidence_fingerprint(payload: dict[str, object]) -> str:
    comparisons = payload.get("comparisons")
    assert isinstance(comparisons, list)
    fingerprint_rows = [
        {
            "capture_row_id": row["capture_row_id"],
            "label_end_date": row["label_end_date"],
            "label_available_date": row["label_available_date"],
            "stock_return_bp": row["stock_return_bp"],
            "observed_liquidity_cost_bp": None,
            "observed_liquidity_cost_source": None,
            **{
                key: row.get(key)
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
        for row in comparisons
        if isinstance(row, dict)
    ]
    return _hash_payload(
        {"capture_id": payload["capture_id"], "rows": fingerprint_rows}
    )


def test_banktaiwan_estimate_is_versioned_exact_and_missing_is_not_zero() -> None:
    scenario = build_banktaiwan_cost_scenario(research_order_quantity_shares=1_000)
    estimate = estimate_round_trip_cost(
        scenario,
        market_replay_date="2024-01-02",
        buy_price_twd="100",
        sell_price_twd="100.40",
    )
    assert estimate.status == "estimated"
    assert estimate.policy_estimate_date == "2026-01-01"
    assert estimate.market_replay_date == "2024-01-02"
    assert "policy_date_is_explicit_counterfactual_for_market_replay" in estimate.diagnostics
    assert estimate.estimated_buy_cost_twd == "49"
    assert estimate.estimated_sell_cost_twd == "350"
    assert estimate.estimated_round_trip_cost_twd == "399"
    assert estimate.net_profit_twd == "1.00"
    assert estimate.net_profit_label == 1
    assert estimate.sell_estimate is not None
    assert estimate.sell_estimate["sell_tax"] == "301"

    odd_lot = build_banktaiwan_cost_scenario(
        research_order_quantity_shares=10,
        lot_type="odd_lot",
    )
    odd_lot_estimate = estimate_round_trip_cost(
        odd_lot,
        market_replay_date="2024-01-02",
        buy_price_twd="100",
        sell_price_twd="100.40",
    )
    assert odd_lot_estimate.estimated_buy_cost_twd == "1"
    assert odd_lot_estimate.estimated_sell_cost_twd == "4"
    assert odd_lot_estimate.net_profit_label == 0

    unavailable = estimate_round_trip_cost(
        build_banktaiwan_cost_scenario(
            research_order_amount_twd="100",
            lot_type="full_lot",
        ),
        market_replay_date="2024-01-02",
        buy_price_twd="100",
        sell_price_twd="100.40",
    )
    assert unavailable.status == "unavailable"
    assert unavailable.estimated_round_trip_cost_twd is None
    assert unavailable.net_profit_twd is None
    assert unavailable.net_profit_label is None

    with pytest.raises(RecommendationCostScenarioError):
        build_banktaiwan_cost_scenario(
            policy_estimate_date="2027-01-01",
            research_order_quantity_shares=1_000,
        )


def test_estimated_label_uses_exact_net_not_gross_bp_or_liquidity() -> None:
    scenario = build_banktaiwan_cost_scenario(research_order_quantity_shares=1_000)
    estimate = estimate_round_trip_cost(
        scenario,
        market_replay_date="2024-01-02",
        buy_price_twd="100",
        sell_price_twd="100.40",
    )
    row = RecommendationCalibrationSample.from_forward_return(
        row_id="exact-net-row",
        symbol="1101",
        decision_date="2024-01-02",
        feature_as_of_date="2024-01-01",
        feature_available_date="2024-01-01",
        label_end_date="2024-01-22",
        label_available_date="2024-01-22",
        feature_values=(1, 2),
        stock_return_bp=40,
        benchmark_return_bp=10,
        fixed_round_trip_cost_bp=None,
        observed_liquidity_cost_bp=99_999,
        rule_probability_bp=5_000,
        rule_after_cost_probability_bp=5_000,
        cost_scenario=scenario,
        cost_estimate=estimate,
    )
    assert row.after_cost_profit_label == 1
    assert row.net_profit_twd == "1.00"
    assert row.effective_cost_threshold_bp == estimate.estimated_round_trip_cost_bp
    with pytest.raises(ValueError, match="estimated net profit"):
        RecommendationCalibrationSample.from_forward_return(
            row_id="tampered-net-row",
            symbol="1101",
            decision_date="2024-01-02",
            feature_as_of_date="2024-01-01",
            feature_available_date="2024-01-01",
            label_end_date="2024-01-22",
            label_available_date="2024-01-22",
            feature_values=(1, 2),
            stock_return_bp=40,
            benchmark_return_bp=10,
            fixed_round_trip_cost_bp=None,
            observed_liquidity_cost_bp=99_999,
            rule_probability_bp=5_000,
            rule_after_cost_probability_bp=5_000,
            cost_scenario=scenario,
            cost_estimate=estimate,
            net_profit_twd="2.00",
        )


def test_legitimate_unavailable_cost_stays_unknown_for_price_only_gate(tmp_path: Path) -> None:
    low_amount_scenario = build_banktaiwan_cost_scenario(
        research_order_amount_twd="100",
        lot_type="full_lot",
    )
    estimate = estimate_round_trip_cost(
        low_amount_scenario,
        market_replay_date="2024-01-02",
        buy_price_twd="100",
        sell_price_twd="100.40",
    )
    assert estimate.status == "unavailable"
    assert estimate.buy_price_twd == "100"
    assert estimate.sell_price_twd == "100.40"
    assert estimate.estimated_round_trip_cost_twd is None
    assert estimate.net_profit_twd is None
    assert estimate.net_profit_label is None
    observation = {
        **{
            "cost_scenario_id": low_amount_scenario.scenario_id,
            "cost_scenario_version": low_amount_scenario.scenario_version,
            "cost_scenario_hash": low_amount_scenario.scenario_hash,
            "cost_basis": low_amount_scenario.cost_basis,
            "cost_policy_id": low_amount_scenario.policy_id,
            "cost_policy_version": low_amount_scenario.policy_version,
            "policy_estimate_date": low_amount_scenario.policy_estimate_date,
            "research_order_amount_twd": str(low_amount_scenario.research_order_amount_twd),
            "research_order_quantity_shares": None,
            "lot_type": low_amount_scenario.lot_type,
            "instrument_type": low_amount_scenario.instrument_type,
        },
        "market_replay_date": "2024-01-02",
        "buy_price_twd": estimate.buy_price_twd,
        "sell_price_twd": estimate.sell_price_twd,
        "estimated_buy_cost_twd": None,
        "estimated_sell_cost_twd": None,
        "estimated_round_trip_cost_twd": None,
        "estimated_round_trip_cost_bp": None,
        "gross_buy_amount_twd": None,
        "gross_sell_amount_twd": None,
        "net_profit_twd": None,
        "cost_estimate_status": "unavailable",
        "after_cost_profit_label": None,
    }
    verified = verify_estimated_cost_observation(
        low_amount_scenario,
        observation,
        expected_market_replay_date="2024-01-02",
    )
    assert verified.available is False
    assert verified.status == "unavailable"

    # Exercise the same unavailable branch through a complete natural-evidence
    # path.  The price-up gate may still process the cohort, while after-cost
    # coverage remains explicitly unknown rather than becoming a loss label.
    scenario, _, candidate_root, metadata = _fit_estimated_candidate(
        tmp_path,
        scenario=low_amount_scenario,
    )
    database = tmp_path / "market.db"
    _make_replay_database(database)
    capture_days = tuple(
        (date(2026, 1, 1) + timedelta(days=index) for index in range(13))
    ) + tuple(date(2026, 1, 21) + timedelta(days=index) for index in range(7))
    _persist_estimated_captures(
        tmp_path,
        scenario=scenario,
        candidate_root=candidate_root,
        policy_hash=RecommendationPromotionPolicy().policy_hash,
        capture_days=capture_days,
    )
    outcome = RecommendationNaturalOutcomeService(
        MLHistoricalSnapshotProvider(database),
        evidence_db_path=database,
    ).scan_and_build_evidence(
        output_root=tmp_path,
        evaluation_date="2026-02-20",
        output_path=tmp_path / "unavailable-evidence.json",
        candidate_id=str(metadata["candidate_id"]),
        candidate_freeze_hash=str(metadata["candidate_freeze_hash"]),
    )
    assert outcome.status == "matured"
    assert outcome.evidence is not None
    evidence_payload = json.loads(Path(outcome.evidence.receipt_path).read_text(encoding="utf-8"))
    assert evidence_payload["after_cost_evaluation_status"] == "estimated_cost_unavailable_or_baseline"
    assert evidence_payload["after_cost_matured_sample_count"] == 0
    assert all(
        row["after_cost_profit_label"] is None
        and row["cost_estimate_status"] == "unavailable"
        and row["estimated_round_trip_cost_twd"] is None
        for row in evidence_payload["comparisons"]
    )
    authority = RecommendationCalibrationPromotionAuthority(tmp_path / "unavailable-authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-02-20",
        candidate_id=str(metadata["candidate_id"]),
        candidate_root=candidate_root,
        candidate_metadata=metadata,
        natural_evidence=outcome.evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.reason not in {
        "natural_evidence_comparison_label_invalid",
        "natural_evidence_after_cost_metrics_recalculation_mismatch",
    }


def test_replay_keeps_three_market_dates_in_one_cost_cohort(tmp_path: Path) -> None:
    database = tmp_path / "replay.db"
    _make_replay_database(database)
    scenario = build_banktaiwan_cost_scenario(research_order_quantity_shares=1_000)
    service = RecommendationHistoricalReplayService(
        MLHistoricalSnapshotProvider(database),
        feature_builder=HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY),
    )
    result = service.build(
        RecommendationHistoricalReplayConfig(
            history_start_date="2026-01-01",
            replay_start_date="2026-02-15",
            replay_end_date="2026-05-15",
            symbols=("1101", "2330"),
            fixed_round_trip_cost_bp=None,
            cost_scenario=scenario,
            max_decision_dates=3,
        )
    )
    assert len(result.decision_dates) == 3
    assert result.sample_count == 6
    assert {row.cost_scenario_hash for row in result.samples} == {scenario.scenario_hash}
    assert {row.policy_estimate_date for row in result.samples} == {"2026-01-01"}
    assert {row.market_replay_date for row in result.samples} == set(result.decision_dates)
    assert result.coverage["after_cost_label_coverage"] == "fees_tax_only_estimated"
    assert result.coverage["estimated_cost_rows"] == result.sample_count
    assert "observed_liquidity_cost_missing_after_cost_target_unavailable" not in result.candidate_blockers
    assert result.formal_candidate_eligible is False
    assert result.lookahead_checks["cost_policy_estimate_date_separate_from_market_replay_date"] is True


def test_cost_sizing_or_policy_date_changes_experiment_scope() -> None:
    quantity_scenario = build_banktaiwan_cost_scenario(research_order_quantity_shares=1_000)
    larger_scenario = build_banktaiwan_cost_scenario(research_order_quantity_shares=2_000)
    later_policy_scenario = build_banktaiwan_cost_scenario(
        policy_estimate_date="2026-06-01",
        research_order_quantity_shares=1_000,
    )
    base_scope = daily_learning._scheduled_experiment_scope(
        fixed_round_trip_cost_bp=None,
        cost_scenario=quantity_scenario,
    )
    assert base_scope == daily_learning._scheduled_experiment_scope(
        fixed_round_trip_cost_bp=None,
        cost_scenario=quantity_scenario,
    )
    assert base_scope != daily_learning._scheduled_experiment_scope(
        fixed_round_trip_cost_bp=None,
        cost_scenario=larger_scenario,
    )
    assert base_scope != daily_learning._scheduled_experiment_scope(
        fixed_round_trip_cost_bp=None,
        cost_scenario=later_policy_scenario,
    )
    assert daily_learning._scheduled_experiment_scope(fixed_round_trip_cost_bp=50) == daily_learning._scheduled_experiment_scope(
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
    )


def test_three_live_estimated_captures_aggregate_one_evidence_cohort(tmp_path: Path) -> None:
    scenario, _, candidate_root, metadata = _fit_estimated_candidate(tmp_path)
    database = tmp_path / "market.db"
    _make_replay_database(database)
    capture_days = (date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3))
    capture_paths = _persist_estimated_captures(
        tmp_path,
        scenario=scenario,
        candidate_root=candidate_root,
        policy_hash=RecommendationPromotionPolicy().policy_hash,
        capture_days=capture_days,
    )

    outcome = RecommendationNaturalOutcomeService(
        MLHistoricalSnapshotProvider(database),
        evidence_db_path=database,
    ).scan_and_build_evidence(
        output_root=tmp_path,
        evaluation_date="2026-02-01",
        output_path=tmp_path / "three-day-evidence.json",
        candidate_id=str(metadata["candidate_id"]),
        candidate_freeze_hash=str(metadata["candidate_freeze_hash"]),
    )
    assert outcome.status == "matured"
    assert outcome.matured_sample_count == 3
    assert tuple(Path(item) for item in outcome.capture_paths) == capture_paths
    assert outcome.evidence is not None
    evidence_payload = json.loads(Path(outcome.evidence.receipt_path).read_text(encoding="utf-8"))
    assert evidence_payload["schema_version"] == "recommendation-natural-forward-evidence.v3"
    assert evidence_payload["same_date_same_cost"] is True
    assert len(evidence_payload["source_capture_ids"]) == 3
    assert len(evidence_payload["source_capture_hashes"]) == 3
    assert {
        str(row["capture_as_of_date"])[:10]
        for row in evidence_payload["comparisons"]
    } == {item.isoformat() for item in capture_days}
    assert {
        row["cost_scenario_hash"] for row in evidence_payload["comparisons"]
    } == {scenario.scenario_hash}
    assert {
        row["policy_estimate_date"] for row in evidence_payload["comparisons"]
    } == {scenario.policy_estimate_date}
    assert all(row["observed_liquidity_cost_bp"] is None for row in evidence_payload["comparisons"])


def test_estimated_capture_outcome_authority_consumer_and_tamper_guard(tmp_path: Path) -> None:
    scenario, result, candidate_root, metadata = _fit_estimated_candidate(tmp_path)
    database = tmp_path / "market.db"
    _make_replay_database(database)
    promotion_policy = RecommendationPromotionPolicy()
    # 13 positive and 7 negative naturally matured dates make the fitted
    # challenger demonstrably better than the 50% null benchmark while still
    # satisfying the immutable default promotion policy.
    capture_days = tuple(
        (date(2026, 1, 1) + timedelta(days=index) for index in range(13))
    ) + tuple(date(2026, 1, 21) + timedelta(days=index) for index in range(7))
    capture_paths = _persist_estimated_captures(
        tmp_path,
        scenario=scenario,
        candidate_root=candidate_root,
        policy_hash=promotion_policy.policy_hash,
        capture_days=capture_days,
    )
    capture_bytes_before = tuple(path.read_bytes() for path in capture_paths)

    outcome = RecommendationNaturalOutcomeService(
        MLHistoricalSnapshotProvider(database),
        evidence_db_path=database,
    ).scan_and_build_evidence(
        output_root=tmp_path,
        evaluation_date="2026-02-20",
        output_path=tmp_path / "evidence.json",
        candidate_id=str(metadata["candidate_id"]),
        candidate_freeze_hash=str(metadata["candidate_freeze_hash"]),
    )
    assert outcome.status == "matured"
    assert outcome.matured_sample_count == 20
    assert len(outcome.capture_paths) == 20
    assert outcome.evidence is not None
    evidence_payload = json.loads(Path(outcome.evidence.receipt_path).read_text(encoding="utf-8"))
    assert evidence_payload["schema_version"] == "recommendation-natural-forward-evidence.v3"
    assert evidence_payload["matured_sample_count"] == 20
    assert {
        str(row["capture_as_of_date"])[:10]
        for row in evidence_payload["comparisons"]
    } == {item.isoformat() for item in capture_days}
    assert {
        row["cost_scenario_hash"] for row in evidence_payload["comparisons"]
    } == {scenario.scenario_hash}
    assert evidence_payload["after_cost_evaluation_status"] == "estimated_fees_tax_only"
    comparison = evidence_payload["comparisons"][0]
    assert comparison["cost_scenario_hash"] == scenario.scenario_hash
    assert comparison["cost_estimate_status"] == "estimated"
    assert comparison["after_cost_profit_label"] in (0, 1)
    expected_net = (
        Decimal(str(comparison["gross_sell_amount_twd"]))
        - Decimal(str(comparison["gross_buy_amount_twd"]))
        - Decimal(str(comparison["estimated_buy_cost_twd"]))
        - Decimal(str(comparison["estimated_sell_cost_twd"]))
    )
    assert Decimal(str(comparison["net_profit_twd"])) == expected_net
    assert comparison["observed_liquidity_cost_bp"] is None

    authority = RecommendationCalibrationPromotionAuthority(
        tmp_path / "authority",
        policy=promotion_policy,
    )
    decision = authority.evaluate_and_apply(
        decision_date="2026-02-20",
        candidate_id=str(metadata["candidate_id"]),
        candidate_root=candidate_root,
        candidate_metadata=metadata,
        natural_evidence=outcome.evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt", decision.reason
    pointer = json.loads(authority.pointer_path.read_text(encoding="utf-8"))
    assert pointer["cost_scenario_hash"] == scenario.scenario_hash
    assert pointer["formal_order_allowed"] is False

    consumer = RecommendationCalibrationConsumer(
        pointer_path=authority.pointer_path,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=tmp_path / "data-root",
    )
    assert consumer.reload(decision_date="2026-02-20") == "active", consumer._blocker
    projection = consumer.project(
        stock_code="1101",
        feature_values=(100, 1_000),
        rule_probability_bp=5_000,
        after_cost_rule_probability_bp=5_000,
        decision_date="2026-02-20",
    )
    assert projection.status == "active_candidate"
    assert projection.cost_scenario_hash == scenario.scenario_hash
    assert projection.cost_basis_bp is None
    assert projection.cost_estimate_source == "banktaiwan_policy_estimate_research_only"
    assert "fees_tax_only" in projection.cost_basis

    tampered = dict(evidence_payload)
    tampered_comparisons = [dict(item) for item in evidence_payload["comparisons"]]
    tampered_comparisons[0]["net_profit_twd"] = "999999.00"
    tampered["comparisons"] = tampered_comparisons
    tampered_path = tmp_path / "tampered-evidence.json"
    tampered["receipt_body_hash"] = _hash_payload(
        {
            key: value
            for key, value in tampered.items()
            if key not in {"receipt_body_hash", "receipt_hash", "receipt_path"}
        }
    )
    tampered_path.write_text(
        json.dumps(tampered, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    tampered_authority = RecommendationCalibrationPromotionAuthority(
        tmp_path / "tampered-authority",
        policy=authority.policy,
    )
    tampered_decision = tampered_authority.evaluate_and_apply(
        decision_date="2026-02-20",
        candidate_id=str(metadata["candidate_id"]),
        candidate_root=candidate_root,
        candidate_metadata=metadata,
        natural_evidence={
            "receipt_path": str(tampered_path),
            "receipt_hash": "sha256:" + hashlib.sha256(tampered_path.read_bytes()).hexdigest(),
        },
        data_status="ready",
        drift_status="clean",
    )
    assert tampered_decision.decision == "retain_current"
    assert tampered_decision.reason == "natural_evidence_comparison_label_invalid"

    # A self-consistent but undercharged receipt must still fail: changing
    # both fee fields and net/label, then recomputing the receipt hashes, is
    # not permission to bypass the versioned BankTaiwan policy.
    undercharged = dict(evidence_payload)
    undercharged_comparisons = [dict(item) for item in evidence_payload["comparisons"]]
    target_index = next(
        index
        for index, row in enumerate(undercharged_comparisons)
        if Decimal(str(row["gross_sell_amount_twd"]))
        > Decimal(str(row["gross_buy_amount_twd"]))
        + Decimal(str(row["estimated_round_trip_cost_twd"]))
    )
    undercharged_row = undercharged_comparisons[target_index]
    original_label = undercharged_row["after_cost_profit_label"]
    undercharged_gross_delta = (
        Decimal(str(undercharged_row["gross_sell_amount_twd"]))
        - Decimal(str(undercharged_row["gross_buy_amount_twd"]))
    )
    assert original_label == int(undercharged_gross_delta > 0)
    undercharged_row.update(
        {
            "estimated_buy_cost_twd": "0",
            "estimated_sell_cost_twd": "0",
            "estimated_round_trip_cost_twd": "0",
            "estimated_round_trip_cost_bp": 0,
            "net_profit_twd": str(undercharged_gross_delta),
            "after_cost_profit_label": int(undercharged_gross_delta > 0),
        }
    )
    undercharged["comparisons"] = undercharged_comparisons
    undercharged["comparison_sample_fingerprint"] = _estimated_evidence_fingerprint(
        undercharged
    )
    undercharged["receipt_body_hash"] = _hash_payload(
        {
            key: value
            for key, value in undercharged.items()
            if key not in {"receipt_body_hash", "receipt_hash", "receipt_path"}
        }
    )
    undercharged_path = tmp_path / "undercharged-evidence.json"
    undercharged_path.write_text(
        json.dumps(undercharged, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    undercharged_authority = RecommendationCalibrationPromotionAuthority(
        tmp_path / "undercharged-authority",
        policy=authority.policy,
    )
    undercharged_decision = undercharged_authority.evaluate_and_apply(
        decision_date="2026-02-20",
        candidate_id=str(metadata["candidate_id"]),
        candidate_root=candidate_root,
        candidate_metadata=metadata,
        natural_evidence={
            "receipt_path": str(undercharged_path),
            "receipt_hash": "sha256:" + hashlib.sha256(undercharged_path.read_bytes()).hexdigest(),
        },
        data_status="ready",
        drift_status="clean",
    )
    assert undercharged_decision.decision == "retain_current"
    assert undercharged_decision.reason == "natural_evidence_comparison_label_invalid"
    assert tuple(path.read_bytes() for path in capture_paths) == capture_bytes_before
    assert result.cost_scenario_hash == scenario.scenario_hash


def test_existing_legacy_candidate_and_capture_are_readonly_compatible(tmp_path: Path) -> None:
    if not LEGACY_CANDIDATE.is_file() or not LEGACY_CAPTURE.is_file():
        pytest.skip("本機沒有既有 legacy candidate/capture artifact")
    from app_module.daily_recommendation_learning_runner import DailyRecommendationLearningRunner
    from scripts.scheduled.run_daily_recommendation_learning import (
        _load_frozen_challenger,
        _read_verified_candidate_capture,
    )

    candidate_bytes_before = LEGACY_CANDIDATE.read_bytes()
    capture_bytes_before = LEGACY_CAPTURE.read_bytes()
    candidate = json.loads(candidate_bytes_before.decode("utf-8"))
    capture = json.loads(capture_bytes_before.decode("utf-8"))
    assert candidate["fixed_round_trip_cost_bp"] == 50
    assert candidate["cost_contract_hash"] == LEGACY_COST_CONTRACT_HASH
    assert candidate.get("cost_basis") is None
    assert capture["schema_version"] == "recommendation-prediction-capture.v2"
    assert capture["fixed_round_trip_cost_bp"] == 50
    _verify_capture_document(capture)
    assert recommendation_cost_contract_hash(50) == LEGACY_COST_CONTRACT_HASH
    isolated_candidate = tmp_path / "isolated-candidate"
    shutil.copytree(LEGACY_CANDIDATE.parent, isolated_candidate)
    isolated_capture = tmp_path / "isolated-output" / "captures" / LEGACY_CAPTURE.name
    isolated_capture.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEGACY_CAPTURE, isolated_capture)
    loaded_capture, load_error = _read_verified_candidate_capture(isolated_capture)
    assert load_error is None
    assert loaded_capture is not None
    assert loaded_capture["capture_hash"] == capture["capture_hash"]
    assert isolated_capture.read_bytes() == capture_bytes_before
    assert (isolated_candidate / "candidate.json").read_bytes() == candidate_bytes_before

    runner_output = tmp_path / "frozen-runner-output"
    challenger_pointer = runner_output / "recommendation_learning" / "challenger" / "current.json"
    challenger_pointer.parent.mkdir(parents=True, exist_ok=True)
    challenger_pointer.write_text(
        json.dumps(
            {
                "status": "pending",
                "candidate_id": candidate["candidate_id"],
                "candidate_root": str(isolated_candidate),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    assert _load_frozen_challenger(runner_output) == isolated_candidate.resolve()

    manifest = json.loads(
        (isolated_candidate / "manifest.json").read_text(encoding="utf-8")
    )
    feature_schema = tuple(tuple(item) for item in manifest["feature_schema"])
    runner = DailyRecommendationLearningRunner(
        output_root=runner_output,
        feature_names=tuple(item[0] for item in feature_schema),
        feature_schema=feature_schema,
        feature_registry_hash=str(manifest["feature_registry_hash"]),
        fixed_round_trip_cost_bp=50,
    )
    frozen_run = runner.run(
        decision_date="2026-09-14",
        run_scope="legacy-readonly-compatibility",
        samples=(),
        natural_evidence=None,
        data_dependency_status="ready",
        outcome_dependency_status="ready",
        drift_status="not_checked",
        frozen_candidate_root=isolated_candidate,
    )
    assert frozen_run.status == "completed"
    assert frozen_run.candidate_id == candidate["candidate_id"]
    assert frozen_run.candidate_root == str(isolated_candidate.resolve())
    frozen_receipt = json.loads(Path(frozen_run.receipt_path).read_text(encoding="utf-8"))
    assert frozen_receipt["steps"]["candidate_training"] == "reused_frozen_challenger"
    assert (isolated_candidate / "candidate.json").read_bytes() == candidate_bytes_before

    # Build the smallest valid active pointer/decision receipt around the
    # copied legacy artifact so the current consumer exercises its immutable
    # loader without retraining or modifying the historical files.
    consumer_root = tmp_path / "consumer"
    consumer_root.mkdir(parents=True, exist_ok=True)
    decision_id = "legacy-readonly-consumer-load"
    pointer = {
        "schema_version": "recommendation-calibration-active-pointer.v2",
        "pointer_version": 1,
        "status": "active",
        "effective_date": "2026-09-14",
        "decision_id": decision_id,
        "candidate_id": candidate["candidate_id"],
        "candidate_root": str(isolated_candidate.resolve()),
        "candidate_manifest_hash": candidate["manifest_hash"],
        "candidate_artifact_hash": candidate["artifact_hash"],
        "candidate_freeze_hash": candidate["candidate_freeze_hash"],
        "dataset_hash": candidate["dataset_hash"],
        "fixed_round_trip_cost_bp": 50,
        "cost_contract_hash": LEGACY_COST_CONTRACT_HASH,
        "label_registry_hash": candidate["label_registry_hash"],
        "maximum_probability_change_bp": 1_000,
        "policy_hash": RecommendationPromotionPolicy().policy_hash,
        "formal_order_allowed": False,
        "natural_evidence_receipt_hash": None,
        "authority_family": "baldr-ml-promotion-authority-daily",
        "authority_scope": "recommendation_calibration_adapter",
    }
    decision_receipt = {
        "schema_version": "recommendation-calibration-decision-receipt.v2",
        "decision_id": decision_id,
        "pointer_content_hash": _hash_payload(pointer),
    }
    decision_receipt_path = consumer_root / "decision.json"
    decision_receipt_path.write_text(
        json.dumps(decision_receipt, sort_keys=True),
        encoding="utf-8",
    )
    pointer["decision_receipt_path"] = str(decision_receipt_path.resolve())
    pointer["decision_receipt_hash"] = "sha256:" + hashlib.sha256(
        decision_receipt_path.read_bytes()
    ).hexdigest()
    pointer_path = consumer_root / "active-pointer.json"
    pointer_path.write_text(json.dumps(pointer, sort_keys=True), encoding="utf-8")
    consumer = RecommendationCalibrationConsumer(
        pointer_path=pointer_path,
        feature_schema=feature_schema,
        feature_registry_hash=str(manifest["feature_registry_hash"]),
        # The loader rejects artifacts below data_root; keep the copied
        # shadow artifact beside, rather than below, this formal-data root.
        data_root=tmp_path / "formal-data-root",
    )
    assert consumer.reload(decision_date="2026-09-14") == "active", consumer._blocker
    assert consumer.active_identity(decision_date="2026-09-14")["candidate_id"] == candidate["candidate_id"]
    assert (isolated_candidate / "candidate.json").read_bytes() == candidate_bytes_before
    assert isolated_capture.read_bytes() == capture_bytes_before
    legacy = build_legacy_cost_scenario(50)
    legacy_payload = sample_payload(
        RecommendationCalibrationSample.from_forward_return(
            row_id="legacy-golden-row",
            symbol="1101",
            decision_date="2026-01-02",
            feature_as_of_date="2026-01-01",
            feature_available_date="2026-01-01",
            label_end_date="2026-01-22",
            label_available_date="2026-01-22",
            feature_values=(1, 2),
            stock_return_bp=100,
            benchmark_return_bp=10,
            fixed_round_trip_cost_bp=50,
            observed_liquidity_cost_bp=20,
            rule_probability_bp=5_000,
            rule_after_cost_probability_bp=5_000,
            cost_scenario=legacy,
        )
    )
    assert "cost_scenario_hash" not in legacy_payload
    assert LEGACY_CANDIDATE.read_bytes() == candidate_bytes_before
    assert LEGACY_CAPTURE.read_bytes() == capture_bytes_before


def test_new_lane_daily_cli_runs_bounded_shadow_cycle(tmp_path: Path, capsys) -> None:
    data_root = tmp_path / "data-root"
    output_root = tmp_path / "shadow-root"
    data_root.mkdir()
    source_db = data_root / "fixture.db"
    _make_cli_database(source_db)
    result = daily_learning.main(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--source-db",
            str(source_db),
            "--symbols",
            "1101,2330",
            "--decision-date",
            "2014-12-15",
            "--replay-start-date",
            "2014-02-01",
            "--replay-end-date",
            "2014-12-15",
            "--training-as-of",
            "2014-12-15",
            "--max-decision-dates",
            "100",
            "--cost-scenario",
            "banktaiwan_estimated_research",
            "--research-order-quantity-shares",
            "1000",
            "--skip-capture-current",
        ]
    )
    assert result == 0
    output = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(output[-1])
    assert payload["cost_basis"] == "estimated_research_only"
    assert payload["cost_scenario_id"] == "banktaiwan-electronic-estimate"
    assert payload["research_order_quantity_shares"] == 1_000
    assert payload["formal_order_allowed"] is False
    assert payload["shadow_only"] is True
    assert payload["run"]["status"] == "completed"
    assert payload["replay"]["coverage"]["after_cost_label_coverage"] == "fees_tax_only_estimated"
    assert payload["replay"]["coverage"]["estimated_cost_rows"] > 0
    assert payload["replay"]["coverage"]["cost_scenario_hash"] == payload["cost_scenario_hash"]
    assert payload["replay"]["lookahead_checks"]["cost_policy_estimate_date_separate_from_market_replay_date"] is True
    receipt_path = Path(payload["run"]["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["cost_scenario_hash"] == payload["cost_scenario_hash"]
    assert receipt["formal_order_allowed"] is False
    assert receipt["shadow_only"] is True


def test_same_output_root_rejects_second_cost_lane_and_preserves_legacy_state(
    tmp_path: Path,
    capsys,
) -> None:
    data_root = tmp_path / "data-root"
    shared_root = tmp_path / "shared-shadow-root"
    isolated_estimated_root = tmp_path / "estimated-shadow-root"
    data_root.mkdir()
    source_db = data_root / "fixture.db"
    _make_cli_database(source_db)
    common = [
        "--data-root",
        str(data_root),
        "--source-db",
        str(source_db),
        "--symbols",
        "1101,2330",
        "--decision-date",
        "2014-12-15",
        "--replay-start-date",
        "2014-02-01",
        "--replay-end-date",
        "2014-12-15",
        "--training-as-of",
        "2014-12-15",
        "--max-decision-dates",
        "100",
        "--skip-capture-current",
    ]
    legacy_args = [
        *common,
        "--output-root",
        str(shared_root),
        "--cost-scenario",
        "legacy_fixed_bp",
        "--fixed-round-trip-cost-bp",
        "50",
    ]
    assert daily_learning.main(legacy_args) == 0
    legacy_payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert legacy_payload["run"]["status"] == "completed"
    challenger_pointer_path = shared_root / "recommendation_learning" / "challenger" / "current.json"
    legacy_latest_path = shared_root / "recommendation_learning" / "latest_status.json"
    legacy_receipt_path = Path(legacy_payload["run"]["receipt_path"])
    shared_state_paths = tuple(
        path
        for path in (challenger_pointer_path, legacy_latest_path, legacy_receipt_path)
        if path.is_file()
    )
    assert shared_state_paths
    shared_state_before = {path: path.read_bytes() for path in shared_state_paths}

    estimated_args = [
        *common,
        "--output-root",
        str(shared_root),
        "--cost-scenario",
        "banktaiwan_estimated_research",
        "--research-order-quantity-shares",
        "1000",
    ]
    assert daily_learning.main(estimated_args) == 2
    conflict_payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert conflict_payload["decision_reason"] == "cost_scenario_root_conflict"
    assert "different --output-root" in conflict_payload["error"]
    assert {path: path.read_bytes() for path in shared_state_paths} == shared_state_before

    isolated_args = [
        *common,
        "--output-root",
        str(isolated_estimated_root),
        "--cost-scenario",
        "banktaiwan_estimated_research",
        "--research-order-quantity-shares",
        "1000",
    ]
    assert daily_learning.main(isolated_args) == 0
    isolated_payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert isolated_payload["cost_basis"] == "estimated_research_only"
    assert isolated_payload["cost_scenario_hash"] == conflict_payload["cost_scenario_hash"]
    assert {path: path.read_bytes() for path in shared_state_paths} == shared_state_before
