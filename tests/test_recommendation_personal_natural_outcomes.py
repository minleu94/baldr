from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest
import ml_module.recommendation_natural_outcome_service as personal_outcome_module

from app_module.recommendation.personal_prediction_capture import (
    PERSONAL_FIXED_NULL_BENCHMARK_ID,
    PERSONAL_FIXED_NULL_BENCHMARK_KIND,
    PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2,
    capture_personal_saved_result,
    read_personal_prediction_capture,
    _capture_id,
    _payload_hash,
)
from app_module.recommendation.personal_use_policy import (
    _policy_hash,
    validate_personal_use_policy_snapshot,
)
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from data_module.natural_maturity_session_resolver import NaturalMaturitySessionResolver
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from ml_module.recommendation_cost_scenario import (
    build_banktaiwan_cost_scenario,
    build_legacy_cost_scenario,
    estimate_round_trip_cost,
)
from ml_module.recommendation_inference_provenance import (
    build_inference_projection_receipt,
    persist_inference_projection_receipt,
    validate_provenance_compatibility,
)
from ml_module.recommendation_natural_outcome_service import (
    RecommendationNaturalOutcomeService,
    _estimated_personal_cost_is_complete,
    _personal_after_cost_fields,
)
from ml_module.recommendation_calibration_evidence import (
    MaturedRecommendationOutcome,
    verify_natural_maturity_session_proof,
)
from tests.test_recommendation_personal_prediction_capture import _build_case


_UTC = timezone.utc
_CAPTURE_DAY = date(2025, 5, 2)


def _complete_cost_personal_capture(tmp_path: Path) -> dict[str, Any]:
    execution, original_receipt, receipt_path, persistence, queries, old_policy = _build_case(
        tmp_path
    )
    scenario = build_legacy_cost_scenario(50)
    result_id = f"{execution.result_id}-personal-natural"

    candidate_identity = dict(original_receipt.payload["candidate_identity"])
    candidate_root = Path(str(candidate_identity["candidate_root"]))
    candidate_json_path = candidate_root / "candidate.json"
    candidate_payload = json.loads(candidate_json_path.read_text(encoding="utf-8"))
    candidate_payload["cost_scenario_hash"] = scenario.scenario_hash
    candidate_json_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    candidate_identity["cost_scenario_hash"] = scenario.scenario_hash

    inference = dict(original_receipt.payload["inference_provenance"])
    inference.update(
        {
            "cost_scenario_hash": scenario.scenario_hash,
            "cost_scenario_id": scenario.scenario_id,
            "cost_scenario_version": scenario.scenario_version,
        }
    )
    inference["provenance_hash"] = _canonical_hash(
        {key: value for key, value in inference.items() if key != "provenance_hash"}
    )
    projections = []
    for original_row in original_receipt.payload["projections"]:
        row = dict(original_row)
        row["cost_scenario_hash"] = scenario.scenario_hash
        row["cost_scenario"] = scenario.metadata()
        row["after_cost_profit_probability_bp"] = (
            8_500 if row["stock_code"] == "1101" else 1_500
        )
        projections.append(row)
    training = dict(original_receipt.payload["training_provenance"])
    compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=scenario.scenario_hash,
        expected_probability_transform_id=str(inference["probability_transform_id"]),
    )
    new_receipt = build_inference_projection_receipt(
        decision_date=str(original_receipt.payload["decision_date"]),
        result_id=result_id,
        candidate_identity=candidate_identity,
        training_provenance=training,
        inference_provenance=inference,
        compatibility=compatibility,
        projections=projections,
        selection_contract=original_receipt.payload["selection_contract"],
    )
    learning_root = receipt_path.parents[3]
    new_receipt_path = persist_inference_projection_receipt(learning_root, new_receipt)
    receipt_payload = dict(new_receipt.payload)
    projection_codes = tuple(str(row["stock_code"]) for row in receipt_payload["projections"])

    candidate_json_hash = _file_hash(candidate_json_path.read_bytes())
    policy_body = dict(old_policy)
    policy_body.pop("policy_sha256")
    policy_candidate = dict(policy_body["candidate"])
    policy_candidate["candidate_json_sha256"] = candidate_json_hash
    policy_body["candidate"] = policy_candidate
    policy_snapshot = validate_personal_use_policy_snapshot(
        {**policy_body, "policy_sha256": _policy_hash(policy_body)}
    )

    policy_event = next(
        event for event in execution.events if event.event_type == "personal_use_policy_snapshot"
    )
    receipt_event = next(
        event for event in execution.events if event.event_type == "ml_projection_receipt_capture"
    )
    policy_details = {
        **dict(policy_event.details),
        "result_id": result_id,
        "policy_snapshot": policy_snapshot,
    }
    updated_policy_event = replace(policy_event, details=policy_details)
    receipt_details = {
        **dict(receipt_event.details),
        "path": str(new_receipt_path.resolve()),
        "receipt_hash": new_receipt.receipt_hash,
        "result_id": result_id,
        "candidate_identity": candidate_identity,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_scenario_id": scenario.scenario_id,
        "projected_stock_codes": projection_codes,
        "projection_rows_sha256": receipt_payload["projection_rows_sha256"],
        "inference_source_hash": inference["inference_source_hash"],
        "inference_pit_hash": inference["inference_pit_hash"],
        "feature_rows_sha256": inference["feature_rows_sha256"],
    }
    updated_receipt_event = replace(receipt_event, details=receipt_details)

    old_binding = execution.ml_receipt_refs[0]
    new_binding = replace(
        old_binding,
        receipt_ref=replace(old_binding.receipt_ref, reference_id=str(new_receipt_path.resolve())),
        receipt_hash=new_receipt.receipt_hash,
        result_id=result_id,
        projected_stock_codes=projection_codes,
        cost_scenario_hash=scenario.scenario_hash,
    )
    new_projection_ref = replace(
        execution.ml_projection_refs[0],
        reference_id=str(receipt_payload["projection_rows_sha256"]),
    )
    new_execution = replace(
        execution,
        result_id=result_id,
        ml_receipt_refs=(new_binding,),
        ml_projection_refs=(new_projection_ref,),
        events=(updated_policy_event, updated_receipt_event),
    )
    persistence.save(
        new_execution,
        now=lambda: datetime(2025, 5, 1, 12, 2, tzinfo=_UTC),
    )
    personal_root = tmp_path / "personal-root"
    capture_receipt = capture_personal_saved_result(result_id, queries, personal_root)
    return read_personal_prediction_capture(
        capture_receipt.path,
        queries,
        personal_root,
        expected_result_id=result_id,
    )


def _structural_v2_capture_fixture(payload: dict[str, Any]) -> dict[str, Any]:
    """只為 Stage B parser 測試升版；不作 app canonical provenance 證據。"""

    upgraded = json.loads(json.dumps(payload, ensure_ascii=False))
    receipt = upgraded["receipt_binding"]
    codes = list(receipt["projected_stock_codes"])
    baseline_body = {
        "schema_version": "recommendation-personal-probability-baseline-snapshot.v1",
        "result_id": upgraded["result_id"],
        "decision_at": upgraded["decision_at"],
        "decision_date": receipt["decision_date"],
        "receipt_hash": receipt["receipt_hash"],
        "projection_rows_sha256": receipt["projection_rows_sha256"],
        "cost_scenario_hash": receipt["cost_scenario_hash"],
        "projected_stock_codes": codes,
        "upside_baseline_kind": PERSONAL_FIXED_NULL_BENCHMARK_KIND,
        "upside_baseline_id": PERSONAL_FIXED_NULL_BENCHMARK_ID,
        "upside_probability_bp_by_symbol": {code: 5_000 for code in codes},
        "after_cost_baseline_status": "unavailable",
        "after_cost_baseline_id": None,
        "after_cost_probability_bp_by_symbol": {code: None for code in codes},
    }
    upgraded["schema_version"] = PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2
    upgraded["probability_baseline_snapshot"] = {
        **baseline_body,
        "snapshot_sha256": _canonical_hash(baseline_body),
    }
    upgraded["capture_id"] = _capture_id(upgraded)
    upgraded["payload_sha256"] = _payload_hash(upgraded)
    return upgraded


def _structural_v3_capture_fixture(
    payload: dict[str, Any],
    *,
    active_codes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """建立 Stage B 專用、可由 ML verifier 重驗的 v3 分區樣本。

    此 helper 僅測 Stage B 結構與自然結果聚合；改寫的 synthetic receipt
    不構成 app canonical execution 或真實個人模型端到端證據。
    """

    upgraded = _structural_v2_capture_fixture(payload)
    _verified, original_receipt, scenario = (
        personal_outcome_module._verify_personal_capture_mapping(
            upgraded,
            max_rows=500,
        )
    )
    if scenario is None:
        raise AssertionError("structural v3 fixture requires an explicit cost scenario")
    delivered_rows = json.loads(json.dumps(upgraded["delivered_rows"], ensure_ascii=False))
    codes = tuple(str(row["stock_code"]) for row in delivered_rows)
    selected_active = active_codes or codes
    if not selected_active or not set(selected_active).issubset(codes):
        raise ValueError("structural v3 active partition is invalid")
    fallback_codes = tuple(code for code in codes if code not in set(selected_active))
    if not fallback_codes:
        raise ValueError("this structural helper is for mixed active/fallback fixtures")

    projections: list[dict[str, Any]] = []
    row_by_code = {str(row["stock_code"]): row for row in delivered_rows}
    scenario_payload = scenario.to_dict(include_hash=True)
    for original_projection in original_receipt["projections"]:
        projection = dict(original_projection)
        code = str(projection["stock_code"])
        projection.update(
            {
                "cost_scenario_id": scenario.scenario_id,
                "cost_scenario_version": scenario.scenario_version,
                "cost_scenario_hash": scenario.scenario_hash,
                "cost_basis": scenario.cost_basis,
                "cost_basis_bp": scenario.fixed_round_trip_cost_bp,
                "cost_policy_id": scenario.policy_id,
                "cost_policy_version": scenario.policy_version,
                "policy_estimate_date": scenario.policy_estimate_date,
                "research_order_amount_twd": scenario_payload[
                    "research_order_amount_twd"
                ],
                "research_order_quantity_shares": scenario.research_order_quantity_shares,
                "lot_type": scenario.lot_type,
                "instrument_type": scenario.instrument_type,
                "cost_scenario": scenario_payload,
            }
        )
        if code in fallback_codes:
            projection.update(
                {
                    "status": "rule_only",
                    "calibrated_probability_status": "unavailable",
                    "calibrated_probability_bp": None,
                    "after_cost_profit_probability_bp": None,
                    "model_version": None,
                }
            )
        row_by_code[code]["projection"] = projection
        projections.append(projection)

    new_receipt = build_inference_projection_receipt(
        decision_date=str(original_receipt["decision_date"]),
        result_id=str(upgraded["result_id"]),
        candidate_identity=dict(original_receipt["candidate_identity"]),
        training_provenance=dict(original_receipt["training_provenance"]),
        inference_provenance=dict(original_receipt["inference_provenance"]),
        compatibility=dict(original_receipt["provenance_compatibility"]),
        projections=projections,
        selection_contract=dict(original_receipt["selection_contract"]),
    )
    receipt_path = persist_inference_projection_receipt(
        upgraded["receipt_binding"]["learning_root"],
        new_receipt,
    )
    receipt_binding = upgraded["receipt_binding"]
    receipt_binding.update(
        {
            "path": str(receipt_path.resolve()),
            "receipt_hash": new_receipt.receipt_hash,
            "projection_rows_sha256": new_receipt.payload[
                "projection_rows_sha256"
            ],
            "projected_stock_codes": list(codes),
        }
    )
    upgraded["delivered_rows"] = delivered_rows
    upgraded["schema_version"] = "recommendation-personal-prediction-capture.v3"
    baseline = upgraded["probability_baseline_snapshot"]
    baseline_body = {
        key: value for key, value in baseline.items() if key != "snapshot_sha256"
    }
    baseline_body.update(
        {
            "schema_version": "recommendation-personal-probability-baseline-snapshot.v2",
            "receipt_hash": new_receipt.receipt_hash,
            "projection_rows_sha256": new_receipt.payload[
                "projection_rows_sha256"
            ],
            "projected_stock_codes": list(codes),
            "upside_probability_bp_by_symbol": {
                code: 5_000 for code in selected_active
            },
            "after_cost_probability_bp_by_symbol": {
                code: None for code in selected_active
            },
            "delivered_stock_codes": list(codes),
            "model_active_stock_codes": list(selected_active),
            "rule_only_fallback_stock_codes": list(fallback_codes),
            "delivered_count": len(codes),
            "model_active_count": len(selected_active),
            "fallback_count": len(fallback_codes),
            "model_coverage_bp": len(selected_active) * 10_000 // len(codes),
            "cost_scenario": scenario.to_dict(include_hash=True),
        }
    )
    baseline_body["snapshot_sha256"] = _canonical_hash(baseline_body)
    upgraded["probability_baseline_snapshot"] = baseline_body
    upgraded["capture_id"] = _capture_id(upgraded)
    upgraded["payload_sha256"] = _payload_hash(upgraded)
    personal_outcome_module._verify_personal_capture_mapping(upgraded, max_rows=500)
    return upgraded


def _structural_v2_source_time_capture_fixture(
    payload: dict[str, Any],
    *,
    tmp_path: Path,
    active_codes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """在 Stage B 結構樣本中加入完整 V2 source-time event，不作 app ingress 證據。"""

    upgraded = _structural_v3_capture_fixture(payload, active_codes=active_codes)
    event = upgraded["policy_event"]
    old_policy = event["policy_snapshot"]
    policy_body = {
        key: value for key, value in old_policy.items() if key != "policy_sha256"
    }
    candidate = dict(policy_body["candidate"])
    confirmed_at = str(policy_body["confirmed_at"])
    source_path = str((tmp_path / "explicit-research-source.sqlite").resolve())
    source_time_trust = {
        "schema_version": "personal-user-declared-source-time-trust.v1",
        "basis": "user_declared_source_time",
        "confirmed_at": confirmed_at,
        "source_database_path": source_path,
        "file_identity": {"device": 1, "inode": 2},
        "source_database_size_bytes": 4096,
        "source_slice_sha256": "sha256:" + "a" * 64,
        "candidate": candidate,
        "replay_scope": {
            "dataset_ids": ["fixture-dataset"],
            "decision_dates": ["2025-01-02"],
            "symbols": ["1101"],
            "sample_count": 1,
        },
        "research_only": True,
        "official_historical_pit_verified": False,
    }
    policy_body.update(
        {
            "schema_version": "recommendation-personal-use-policy.v2",
            "policy_version": 2,
            "source_time_trust": source_time_trust,
        }
    )
    policy_body["policy_sha256"] = _policy_hash(policy_body)
    event.update(
        {
            "schema_version": "recommendation-personal-use-policy-snapshot.v2",
            "policy_snapshot": policy_body,
            "source_time_basis": "user_declared_source_time",
            "research_only": True,
            "official_historical_pit_verified": False,
        }
    )
    upgraded["capture_id"] = _capture_id(upgraded)
    upgraded["payload_sha256"] = _payload_hash(
        {key: value for key, value in upgraded.items() if key != "payload_sha256"}
    )
    personal_outcome_module._verify_personal_capture_mapping(upgraded, max_rows=500)
    return upgraded


def _write_natural_source(
    root: Path,
    *,
    capture_day: date = _CAPTURE_DAY,
    stock_endpoint_offset: int = 20,
    include_stock_endpoints: bool = True,
    include_taiex_baseline: bool = True,
    include_calendar: bool = True,
    include_liquidity_costs: bool = False,
) -> tuple[MLHistoricalSnapshotProvider, NaturalMaturitySessionResolver, tuple[str, ...]]:
    database = root / "data" / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    sessions = _next_twenty_weekdays(capture_day)
    market_dates = (capture_day, *sessions)
    if not 1 <= stock_endpoint_offset <= 20:
        raise ValueError("stock_endpoint_offset must be between 1 and 20")
    endpoint = sessions[stock_endpoint_offset - 1]
    with sqlite3.connect(database) as connection:
        connection.executescript(
            '''
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL, 證券代號 TEXT NOT NULL, 成交股數 INTEGER,
                成交金額 INTEGER, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT
            );
            CREATE TABLE technical_indicators (
                日期 TEXT NOT NULL, 證券代號 TEXT NOT NULL, RSI TEXT, MACD TEXT, ADX TEXT
            );
            CREATE TABLE market_indices (
                日期 TEXT NOT NULL, 指數名稱 TEXT, 收盤指數 TEXT, 收盤價 TEXT
            );
            CREATE TABLE industry_indices (
                日期 TEXT NOT NULL, 指數名稱 TEXT, 收盤指數 TEXT
            );
            '''
        )
        if include_liquidity_costs:
            connection.executescript(
                """
                CREATE TABLE evidence_events (
                    event_id TEXT NOT NULL, symbol TEXT NOT NULL, decision_date TEXT NOT NULL
                );
                CREATE TABLE evidence_outcomes (
                    outcome_id TEXT NOT NULL, event_id TEXT NOT NULL, window_days INTEGER NOT NULL,
                    outcome_status TEXT NOT NULL, outcome_price_date TEXT NOT NULL,
                    liquidity_cost_bp INTEGER NOT NULL, calculated_at TEXT NOT NULL
                );
                """
            )
        for index, day in enumerate(market_dates, start=1):
            if day == capture_day and not include_taiex_baseline:
                continue
            compact = day.strftime("%Y%m%d")
            close = str(20_000 + index)
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?, ?)",
                (compact, "TAIEX", close, close),
            )
        closes = {"1101": "110", "2330": "90"}
        for symbol in ("1101", "2330"):
            price_rows = [(capture_day, "100")]
            if include_stock_endpoints:
                price_rows.append((endpoint, closes[symbol]))
            for day, close in price_rows:
                compact = day.strftime("%Y%m%d")
                connection.execute(
                    "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (compact, symbol, 100_000, 10_000_000, close, close, close, close),
                )
            if include_liquidity_costs:
                event_id = f"liquidity-{symbol}"
                connection.execute(
                    "INSERT INTO evidence_events VALUES (?, ?, ?)",
                    (event_id, symbol, capture_day.isoformat()),
                )
                connection.execute(
                    "INSERT INTO evidence_outcomes VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"outcome-{symbol}",
                        event_id,
                        20,
                        "ready",
                        endpoint.isoformat(),
                        10,
                        datetime.now(_UTC).isoformat(),
                    ),
                )

    resolver_root = root / "calendar"
    resolver_root.mkdir(parents=True, exist_ok=True)
    evaluation_at = datetime.now(_UTC)
    if include_calendar:
        holiday = date(capture_day.year, 1, 1)
        weekdays = ("一", "二", "三", "四", "五", "六", "日")
        raw = json.dumps(
            [
                {
                    "Name": "測試年度休市",
                    "Date": f"{capture_day.year - 1911:03d}0101",
                    "Weekday": weekdays[holiday.weekday()],
                    "Description": "測試用官方年度休市紀錄。",
                }
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        cache = build_twse_calendar_cache(
            calendar_year=capture_day.year,
            raw_response=raw,
            requested_at=evaluation_at - timedelta(days=1, seconds=1),
            captured_at=evaluation_at - timedelta(days=1),
            response_status=200,
            response_headers={"ETag": '"personal-outcome-calendar-v1"'},
            max_age=timedelta(days=31),
        )
        write_twse_calendar_cache(
            resolver_root / f"twse_holiday_schedule_{capture_day.year}_personal_test.json",
            cache,
            allowed_root=resolver_root,
        )
    provider = MLHistoricalSnapshotProvider(database)
    resolver = NaturalMaturitySessionResolver(database, resolver_root)
    return provider, resolver, tuple(day.isoformat() for day in sessions)


def _next_twenty_weekdays(start: date) -> tuple[date, ...]:
    result: list[date] = []
    current = start + timedelta(days=1)
    while len(result) < 20:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return tuple(result)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def test_personal_natural_outcome_uses_verified_receipt_official_twenty_sessions_and_decimal_prices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
        include_liquidity_costs=True,
    )
    forward_windows: list[tuple[str, str, tuple[str, ...]]] = []
    original_load_forward = provider.load_forward_price_window

    def record_forward_window(
        *,
        start_date: str,
        end_date: str,
        symbols: tuple[str, ...],
    ) -> Any:
        forward_windows.append((start_date, end_date, symbols))
        return original_load_forward(
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
        )

    monkeypatch.setattr(provider, "load_forward_price_window", record_forward_window)
    evaluation_at = datetime.now(_UTC)
    service = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    )

    result = service.project_personal_prediction_outcomes(
        capture,
        evaluation_at=evaluation_at,
    )

    assert result.status == "matured", result.to_dict()
    assert result.reason == "personal_capture_official_20_session_outcomes_verified"
    assert result.endpoint_date == sessions[-1]
    assert result.evaluation_date > result.endpoint_date
    assert forward_windows == [
        (
            decision_date.isoformat(),
            sessions[-1],
            ("1101", "2330"),
        )
    ]
    assert result.matured_sample_count == 2
    assert result.pending_sample_count == 0
    assert result.metrics == {
        "sample_count": 2,
        "brier_bp": 3_204,
        "calibration_gap_bp": 1_850,
        "after_cost_sample_count": 2,
        "after_cost_brier_bp": 225,
        "after_cost_calibration_gap_bp": 0,
    }
    assert [row["label"] for row in result.outcomes] == [1, 0]
    assert all(row["cost_estimate_status"] == "fixed_assumption" for row in result.outcomes)
    assert all(row["estimated_round_trip_cost_bp"] == 50 for row in result.outcomes)
    assert [row["after_cost_profit_label"] for row in result.outcomes] == [1, 0]
    assert [row["after_cost_profit_bp"] for row in result.outcomes] == [940, -1_060]
    assert all(row["after_cost_status"] == "fixed_plus_observed_liquidity" for row in result.outcomes)
    assert result.after_cost_status == "matured_with_after_cost_probability"
    assert all(row["session_proof_hash"] for row in result.outcomes)
    payload = result.to_dict()
    assert payload["global_natural_evidence_created"] is False
    assert payload["promotion_credit_created"] is False


def test_personal_v2_natural_outcome_reports_fixed_null_benchmark_and_unknown_after_cost(
    tmp_path: Path,
) -> None:
    # 此 fixture 只驗 ML 投影器的 v2 結構/指標處理；canonical 來源仍由 app readback 測試驗證。
    capture = _structural_v2_capture_fixture(_complete_cost_personal_capture(tmp_path))
    verified, _policy, _proof = personal_outcome_module._verify_personal_capture_mapping(
        capture,
        max_rows=500,
    )
    assert verified["schema_version"] == PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2

    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, _sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
        include_liquidity_costs=True,
    )
    result = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    ).project_personal_prediction_outcomes(
        capture,
        evaluation_at=datetime.now(_UTC),
    )

    assert result.status == "matured", result.to_dict()
    assert result.metrics is not None
    assert result.metrics["fixed_null_benchmark_sample_count"] == 2
    assert result.metrics["fixed_null_benchmark_brier_bp"] == 2_500
    assert result.metrics["fixed_null_benchmark_calibration_gap_bp"] == 0
    # Upside null benchmark 沒有 after-cost 語意，不能拿 5,000bp 代替。
    assert result.metrics["after_cost_baseline_sample_count"] == 0
    assert result.metrics["after_cost_baseline_brier_bp"] is None
    assert result.metrics["after_cost_baseline_calibration_gap_bp"] is None
    assert all(
        row["upside_baseline_kind"] == PERSONAL_FIXED_NULL_BENCHMARK_KIND
        and row["upside_baseline_id"] == PERSONAL_FIXED_NULL_BENCHMARK_ID
        and row["upside_baseline_probability_bp"] == 5_000
        and row["after_cost_baseline_status"] == "unavailable"
        and row["after_cost_baseline_id"] is None
        and row["after_cost_baseline_probability_bp"] is None
        for row in result.outcomes
    )


def test_personal_v3_mixed_rows_ignore_foreign_evidence_liquidity_and_keep_gross_label(
    tmp_path: Path,
) -> None:
    # 這是可重驗 capture/receipt 的 Stage B 結構測試；不是 app canonical/full-stack 證據。
    capture = _structural_v3_capture_fixture(
        _complete_cost_personal_capture(tmp_path),
        active_codes=("1101",),
    )
    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, _sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
        include_liquidity_costs=True,
    )
    result = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    ).project_personal_prediction_outcomes(
        capture,
        evaluation_at=datetime.now(_UTC),
    )

    assert result.status == "matured", (result.reason, result.diagnostics, result.outcomes)
    assert result.matured_sample_count == 1
    assert result.pending_sample_count == 0
    assert result.metrics is not None
    assert result.metrics["delivered_universe_count"] == 2
    assert result.metrics["model_active_count"] == 1
    assert result.metrics["rule_only_fallback_count"] == 1
    assert result.metrics["model_coverage_bp"] == 5_000
    assert [row["stock_code"] for row in result.outcomes] == ["1101"]
    outcome = result.outcomes[0]
    assert outcome["label"] == 1
    assert outcome["upside_baseline_probability_bp"] == 5_000
    # SQLite 含同股、同日、同視窗的 foreign EvidenceOutcome；v3 不可套用它。
    assert outcome["observed_liquidity_cost_bp"] is None
    assert outcome["observed_liquidity_cost_source"] is None
    assert outcome["after_cost_profit_label"] is None
    assert outcome["after_cost_status"] == "unknown_missing_liquidity_cost"
    assert any(
        item.startswith("personal_v3_unbound_liquidity_evidence_not_used:1101:")
        for item in result.diagnostics
    )
    assert any("rule_only_fallback_excluded_from_model_outcomes:1" in item for item in result.diagnostics)


def test_personal_v3_estimated_scenario_matures_without_foreign_liquidity_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 此結構測試只替換已驗證 mapping 的輸入場景；真實候選准入/同次 canonical
    # event 綁定仍由 full-stack app 測試負責，這裡只驗 Stage B 的成本分支。
    capture = _structural_v3_capture_fixture(
        _complete_cost_personal_capture(tmp_path),
        active_codes=("1101",),
    )
    # 臺銀研究費率自 2026-01-01 生效；將本結構測試輸入置於有效交易日，
    # 不把早於政策生效日的價格套用新費率。
    cost_replay_day = date(2026, 1, 5)
    scenario = build_banktaiwan_cost_scenario(
        policy_estimate_date=cost_replay_day.isoformat(),
        research_order_quantity_shares=1_000,
    )
    structural = json.loads(json.dumps(capture, ensure_ascii=False))
    binding = structural["receipt_binding"]
    binding["cost_scenario_hash"] = scenario.scenario_hash
    binding["decision_date"] = cost_replay_day.isoformat()
    baseline = structural["probability_baseline_snapshot"]
    baseline["cost_scenario_hash"] = scenario.scenario_hash
    baseline["cost_scenario"] = scenario.to_dict(include_hash=True)
    for row in structural["delivered_rows"]:
        projection = row["projection"]
        if row["stock_code"] == "1101":
            scenario_payload = scenario.to_dict(include_hash=True)
            projection.update(
                {
                    "cost_scenario_id": scenario.scenario_id,
                    "cost_scenario_version": scenario.scenario_version,
                    "cost_scenario_hash": scenario.scenario_hash,
                    "cost_basis": scenario.cost_basis,
                    "cost_basis_bp": scenario.fixed_round_trip_cost_bp,
                    "cost_policy_id": scenario.policy_id,
                    "cost_policy_version": scenario.policy_version,
                    "policy_estimate_date": scenario.policy_estimate_date,
                    "research_order_amount_twd": scenario_payload[
                        "research_order_amount_twd"
                    ],
                    "research_order_quantity_shares": scenario.research_order_quantity_shares,
                    "lot_type": scenario.lot_type,
                    "instrument_type": scenario.instrument_type,
                    "after_cost_profit_probability_bp": 8_500,
                }
            )
    monkeypatch.setattr(
        personal_outcome_module,
        "_verify_personal_capture_mapping",
        lambda _payload, *, max_rows: (structural, {}, scenario),
    )
    provider, resolver, _sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=cost_replay_day,
        include_liquidity_costs=True,
    )
    result = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    ).project_personal_prediction_outcomes(
        structural,
        evaluation_at=datetime.now(_UTC),
    )

    assert result.status == "matured", (result.reason, result.diagnostics, result.outcomes)
    assert result.matured_sample_count == 1
    outcome = result.outcomes[0]
    assert outcome["cost_scenario_hash"] == scenario.scenario_hash
    assert outcome["cost_estimate_status"] == "estimated"
    assert outcome["observed_liquidity_cost_bp"] is None
    assert outcome["observed_liquidity_cost_source"] is None
    assert outcome["after_cost_status"] == "estimated_fees_tax_only"
    assert outcome["after_cost_profit_label"] == 1
    assert outcome["after_cost_profit_twd"] is not None
    assert result.metrics is not None
    assert result.metrics["after_cost_sample_count"] == 1


def test_personal_v2_natural_outcome_rejects_unrehashed_baseline_tamper(
    tmp_path: Path,
) -> None:
    capture = _structural_v2_capture_fixture(_complete_cost_personal_capture(tmp_path))
    baseline = capture["probability_baseline_snapshot"]
    baseline["snapshot_sha256"] = "sha256:" + "b" * 64
    capture["capture_id"] = _capture_id(capture)
    capture["payload_sha256"] = _payload_hash(capture)

    with pytest.raises(ValueError, match="baseline snapshot hash mismatch"):
        personal_outcome_module._verify_personal_capture_mapping(capture, max_rows=500)


def test_personal_v3_v2_source_time_policy_is_accepted_for_active_subset(
    tmp_path: Path,
) -> None:
    capture = _structural_v2_source_time_capture_fixture(
        _complete_cost_personal_capture(tmp_path),
        tmp_path=tmp_path,
        active_codes=("1101",),
    )
    verified, policy, _scenario = personal_outcome_module._verify_personal_capture_mapping(
        capture,
        max_rows=500,
    )

    assert capture["schema_version"] == "recommendation-personal-prediction-capture.v3"
    assert verified["policy_event"]["schema_version"] == (
        "recommendation-personal-use-policy-snapshot.v2"
    )
    saved_policy = verified["policy_event"]["policy_snapshot"]
    assert saved_policy["schema_version"] == "recommendation-personal-use-policy.v2"
    assert saved_policy["source_time_trust"]["basis"] == "user_declared_source_time"
    assert saved_policy["source_time_trust"]["candidate"] == saved_policy["candidate"]
    assert verified["probability_baseline_snapshot"]["model_active_stock_codes"] == [
        "1101"
    ]
    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, _sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
    )
    result = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    ).project_personal_prediction_outcomes(
        capture,
        evaluation_at=datetime.now(_UTC),
    )
    assert result.status == "matured", (result.reason, result.diagnostics, result.outcomes)
    assert result.matured_sample_count == 1
    assert result.metrics is not None
    assert result.metrics["model_active_count"] == 1
    assert result.metrics["rule_only_fallback_count"] == 1


def test_personal_v3_v2_source_time_event_markers_must_match_trust(
    tmp_path: Path,
) -> None:
    capture = _structural_v2_source_time_capture_fixture(
        _complete_cost_personal_capture(tmp_path),
        tmp_path=tmp_path,
        active_codes=("1101",),
    )
    capture["policy_event"]["official_historical_pit_verified"] = True
    capture["payload_sha256"] = _payload_hash(
        {key: value for key, value in capture.items() if key != "payload_sha256"}
    )

    with pytest.raises(ValueError, match="source-time event markers mismatch"):
        personal_outcome_module._verify_personal_capture_mapping(capture, max_rows=500)


def test_personal_v3_v2_snapshot_cannot_hide_behind_v1_event(
    tmp_path: Path,
) -> None:
    capture = _structural_v2_source_time_capture_fixture(
        _complete_cost_personal_capture(tmp_path),
        tmp_path=tmp_path,
        active_codes=("1101",),
    )
    event = capture["policy_event"]
    event["schema_version"] = "recommendation-personal-use-policy-snapshot.v1"
    for key in (
        "source_time_basis",
        "research_only",
        "official_historical_pit_verified",
    ):
        event.pop(key)
    capture["payload_sha256"] = _payload_hash(
        {key: value for key, value in capture.items() if key != "payload_sha256"}
    )

    with pytest.raises(ValueError, match="event and snapshot versions differ"):
        personal_outcome_module._verify_personal_capture_mapping(capture, max_rows=500)


def test_personal_v3_v2_source_time_trust_candidate_pins_must_match_snapshot(
    tmp_path: Path,
) -> None:
    capture = _structural_v2_source_time_capture_fixture(
        _complete_cost_personal_capture(tmp_path),
        tmp_path=tmp_path,
        active_codes=("1101",),
    )
    policy_event = capture["policy_event"]
    policy = policy_event["policy_snapshot"]
    policy_body = {key: value for key, value in policy.items() if key != "policy_sha256"}
    policy_body["source_time_trust"]["candidate"]["dataset_hash"] = (
        "sha256:" + "c" * 64
    )
    policy_body["policy_sha256"] = _policy_hash(policy_body)
    policy_event["policy_snapshot"] = policy_body
    capture["capture_id"] = _capture_id(capture)
    capture["payload_sha256"] = _payload_hash(
        {key: value for key, value in capture.items() if key != "payload_sha256"}
    )

    with pytest.raises(ValueError, match="candidate pins mismatch policy candidate"):
        personal_outcome_module._verify_personal_capture_mapping(capture, max_rows=500)


def test_personal_v3_baseline_delivery_order_matches_canonical_rows_not_receipt_order(
    tmp_path: Path,
) -> None:
    capture = _structural_v3_capture_fixture(
        _complete_cost_personal_capture(tmp_path),
        active_codes=("1101",),
    )
    baseline = capture["probability_baseline_snapshot"]
    baseline_body = {
        key: value for key, value in baseline.items() if key != "snapshot_sha256"
    }
    baseline_body["delivered_stock_codes"] = list(
        reversed(baseline_body["delivered_stock_codes"])
    )
    capture["probability_baseline_snapshot"] = {
        **baseline_body,
        "snapshot_sha256": _canonical_hash(baseline_body),
    }
    capture["capture_id"] = _capture_id(capture)
    capture["payload_sha256"] = _payload_hash(
        {key: value for key, value in capture.items() if key != "payload_sha256"}
    )

    with pytest.raises(ValueError, match="delivered rank order differs"):
        personal_outcome_module._verify_personal_capture_mapping(capture, max_rows=500)


def test_personal_v2_natural_outcome_rejects_rehashed_receipt_crosslink_mismatch(
    tmp_path: Path,
) -> None:
    capture = _structural_v2_capture_fixture(_complete_cost_personal_capture(tmp_path))
    baseline = capture["probability_baseline_snapshot"]
    baseline_body = {
        key: value for key, value in baseline.items() if key != "snapshot_sha256"
    }
    baseline_body["cost_scenario_hash"] = "sha256:" + "a" * 64
    capture["probability_baseline_snapshot"] = {
        **baseline_body,
        "snapshot_sha256": _canonical_hash(baseline_body),
    }
    capture["capture_id"] = _capture_id(capture)
    capture["payload_sha256"] = _payload_hash(capture)

    with pytest.raises(ValueError, match="baseline receipt binding mismatch"):
        personal_outcome_module._verify_personal_capture_mapping(capture, max_rows=500)


def test_personal_natural_outcome_keeps_after_cost_unknown_without_liquidity_source(
    tmp_path: Path,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, _sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
        include_liquidity_costs=False,
    )
    result = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    ).project_personal_prediction_outcomes(
        capture,
        evaluation_at=datetime.now(_UTC),
    )

    assert result.status == "matured"
    assert result.after_cost_status == "pending_cost_or_liquidity_evidence"
    assert all(row["after_cost_profit_label"] is None for row in result.outcomes)
    assert all(row["after_cost_profit_bp"] is None for row in result.outcomes)
    assert result.metrics is not None
    assert result.metrics["after_cost_sample_count"] == 0
    assert result.metrics["after_cost_brier_bp"] is None
    assert result.metrics["after_cost_calibration_gap_bp"] is None


def test_personal_estimated_after_cost_uses_exact_fee_tax_net_without_liquidity_as_zero() -> None:
    scenario = build_banktaiwan_cost_scenario(research_order_quantity_shares=1_000)
    estimate = estimate_round_trip_cost(
        scenario,
        market_replay_date="2025-05-02",
        buy_price_twd="100",
        sell_price_twd="110",
    )
    assert estimate.status == "estimated"
    assert estimate.available
    outcome = MaturedRecommendationOutcome(
        capture_row_id="personal-estimated-row",
        label_end_date="2025-05-30",
        label_available_date="2025-05-30",
        stock_return_bp=1_000,
        observed_liquidity_cost_bp=None,
        observed_liquidity_cost_source=None,
        cost_estimate_status=estimate.status,
        estimated_round_trip_cost_bp=estimate.estimated_round_trip_cost_bp,
        cost_scenario_hash=estimate.scenario_hash,
        gross_buy_amount_twd=estimate.gross_buy_amount_twd,
        gross_sell_amount_twd=estimate.gross_sell_amount_twd,
        estimated_buy_cost_twd=estimate.estimated_buy_cost_twd,
        estimated_sell_cost_twd=estimate.estimated_sell_cost_twd,
        estimated_round_trip_cost_twd=estimate.estimated_round_trip_cost_twd,
        net_profit_twd=estimate.net_profit_twd,
    )

    assert _estimated_personal_cost_is_complete(outcome, scenario)
    fields = _personal_after_cost_fields(outcome, scenario)
    assert fields["after_cost_profit_label"] == int(Decimal(str(estimate.net_profit_twd)) > 0)
    assert fields["after_cost_profit_twd"] == estimate.net_profit_twd
    assert fields["after_cost_profit_bp"] is None
    assert fields["after_cost_status"] == "estimated_fees_tax_only"

    incomplete = replace(outcome, estimated_sell_cost_twd=None)
    assert not _estimated_personal_cost_is_complete(incomplete, scenario)
    assert _personal_after_cost_fields(incomplete, scenario) == {
        "after_cost_profit_label": None,
        "after_cost_profit_bp": None,
        "after_cost_profit_twd": None,
        "after_cost_status": "unknown_estimated_cost_inputs",
    }


def test_personal_candidate_json_cap_plus_one_is_rejected_before_hash_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    candidate_root = Path(str(capture["policy_event"]["policy_snapshot"]["candidate"]["candidate_root"]))
    candidate_json = candidate_root / "candidate.json"
    candidate_raw = candidate_json.read_bytes()
    monkeypatch.setattr(
        personal_outcome_module,
        "_PERSONAL_CANDIDATE_JSON_MAX_BYTES",
        len(candidate_raw),
    )
    candidate_json.write_bytes(candidate_raw + b" ")
    service = RecommendationNaturalOutcomeService(
        SimpleNamespace(database_path=tmp_path / "unused.db")  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="exceeds the bounded read limit"):
        service.project_personal_prediction_outcomes(
            capture,
            evaluation_at=datetime.now(_UTC),
        )


def test_personal_candidate_json_growth_between_check_and_open_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    candidate_root = Path(str(capture["policy_event"]["policy_snapshot"]["candidate"]["candidate_root"]))
    candidate_json = candidate_root / "candidate.json"
    open_candidate = personal_outcome_module._open_nofollow_candidate_json

    def grow_before_open(path: Path) -> int:
        if path == candidate_json:
            with path.open("ab") as stream:
                stream.write(b" ")
        return open_candidate(path)

    monkeypatch.setattr(
        personal_outcome_module,
        "_open_nofollow_candidate_json",
        grow_before_open,
    )
    service = RecommendationNaturalOutcomeService(
        SimpleNamespace(database_path=tmp_path / "unused.db")  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="changed between check and open"):
        service.project_personal_prediction_outcomes(
            capture,
            evaluation_at=datetime.now(_UTC),
        )


def test_personal_candidate_json_symlink_swap_before_open_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    candidate_root = Path(str(capture["policy_event"]["policy_snapshot"]["candidate"]["candidate_root"]))
    candidate_json = candidate_root / "candidate.json"
    outside_json = tmp_path / "outside-candidate.json"
    outside_json.write_bytes(candidate_json.read_bytes())
    symlink_probe = tmp_path / "candidate-symlink-probe.json"
    try:
        symlink_probe.symlink_to(outside_json)
    except (NotImplementedError, OSError):
        if os.name != "nt":
            pytest.skip("此執行環境不能建立測試 symlink 負控")
        temporary_target = candidate_root.with_name(candidate_root.name + ".junction-target")
        resolved_tmp = tmp_path.resolve()
        if resolved_tmp not in candidate_root.resolve().parents or temporary_target.exists():
            pytest.fail("junction 負控路徑不在隔離 pytest 暫存目錄內")
        candidate_root.replace(temporary_target)
        junction_result = subprocess.run(
            [
                os.environ.get("COMSPEC", "cmd.exe"),
                "/c",
                "mklink",
                "/J",
                str(candidate_root),
                str(temporary_target),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        junction_created = junction_result.returncode == 0
        try:
            if not junction_created:
                pytest.skip(
                    "此執行環境不能建立測試 junction 負控："
                    f"{junction_result.stderr.strip() or junction_result.stdout.strip()}"
                )
            service = RecommendationNaturalOutcomeService(
                SimpleNamespace(database_path=tmp_path / "unused.db")  # type: ignore[arg-type]
            )
            with pytest.raises(ValueError, match="linked or reparse|plain directory"):
                service.project_personal_prediction_outcomes(
                    capture,
                    evaluation_at=datetime.now(_UTC),
                )
        finally:
            if junction_created:
                os.rmdir(candidate_root)
            if temporary_target.exists() and not candidate_root.exists():
                temporary_target.replace(candidate_root)
        return
    else:
        symlink_probe.unlink()
    saved_json = candidate_root / "candidate.saved.json"
    open_candidate = personal_outcome_module._open_nofollow_candidate_json

    def swap_to_symlink_before_open(path: Path) -> int:
        if path == candidate_json:
            path.replace(saved_json)
            try:
                path.symlink_to(outside_json)
            except OSError:
                saved_json.replace(path)
                pytest.skip("此 Windows 環境不允許建立符號連結負控")
            try:
                return open_candidate(path)
            finally:
                path.unlink(missing_ok=True)
                saved_json.replace(path)
        return open_candidate(path)

    monkeypatch.setattr(
        personal_outcome_module,
        "_open_nofollow_candidate_json",
        swap_to_symlink_before_open,
    )
    service = RecommendationNaturalOutcomeService(
        SimpleNamespace(database_path=tmp_path / "unused.db")  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="without following links|regular file|linked|changed"):
        service.project_personal_prediction_outcomes(
            capture,
            evaluation_at=datetime.now(_UTC),
        )


def test_personal_natural_outcome_keeps_missing_cost_details_pending_not_defaulted(
    tmp_path: Path,
) -> None:
    execution, _receipt, _receipt_path, _persistence, queries, _policy = _build_case(tmp_path)
    personal_root = tmp_path / "personal-root"
    capture_receipt = capture_personal_saved_result(execution.result_id, queries, personal_root)
    capture = read_personal_prediction_capture(
        capture_receipt.path,
        queries,
        personal_root,
        expected_result_id=execution.result_id,
    )
    service = RecommendationNaturalOutcomeService(
        SimpleNamespace(database_path=tmp_path / "unused.db")  # type: ignore[arg-type]
    )

    result = service.project_personal_prediction_outcomes(
        capture,
        evaluation_at=datetime.now(_UTC),
    )

    assert result.status == "pending"
    assert result.reason == "personal_outcome_cost_scenario_details_missing"
    assert result.matured_sample_count == 0
    assert result.pending_sample_count == 2
    assert result.outcomes == ()
    assert "cost_scenario_hash_verified_but_parameters_unavailable" in result.diagnostics


def test_personal_natural_outcome_waits_until_capture_is_written(
    tmp_path: Path,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    decision_at = datetime.fromisoformat(capture["decision_at"].replace("Z", "+00:00"))
    service = RecommendationNaturalOutcomeService(
        SimpleNamespace(database_path=tmp_path / "unused.db")  # type: ignore[arg-type]
    )

    result = service.project_personal_prediction_outcomes(
        capture,
        evaluation_at=decision_at + timedelta(seconds=1),
    )

    assert result.status == "pending"
    assert result.reason == "personal_outcome_capture_not_yet_available"
    assert result.matured_sample_count == 0
    assert result.pending_sample_count == len(capture["delivered_rows"])
    assert result.outcomes == ()
    assert result.metrics is None


def test_personal_natural_outcome_keeps_missing_official_calendar_pending(
    tmp_path: Path,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, _sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
        include_calendar=False,
    )
    service = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    )

    result = service.project_personal_prediction_outcomes(
        capture,
        evaluation_at=datetime.now(_UTC),
    )

    assert result.status == "pending"
    assert result.matured_sample_count == 0
    assert result.pending_sample_count == 2
    assert any(
        "natural_maturity_session_waiting_for_calendar" in item
        for item in result.diagnostics
    ), result.diagnostics
    assert result.metrics is None


def test_personal_natural_outcome_keeps_missing_taiex_anchor_pending(
    tmp_path: Path,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, _sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
        include_taiex_baseline=False,
    )
    service = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    )

    result = service.project_personal_prediction_outcomes(
        capture,
        evaluation_at=datetime.now(_UTC),
    )

    assert result.status == "pending"
    assert result.matured_sample_count == 0
    assert result.pending_sample_count == 2
    assert any("missing_taiex_baseline_observation" in item for item in result.diagnostics)
    assert result.metrics is None


def test_personal_natural_outcome_keeps_missing_stock_source_pending(
    tmp_path: Path,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, _sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
        include_stock_endpoints=False,
    )
    service = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=resolver,
    )

    result = service.project_personal_prediction_outcomes(
        capture,
        evaluation_at=datetime.now(_UTC),
    )

    assert result.status == "pending"
    assert result.matured_sample_count == 0
    assert result.pending_sample_count == 2
    assert any("endpoint_stock_close_invalid" in item for item in result.diagnostics)
    assert result.metrics is None


def test_personal_natural_outcome_rejects_a_non_twenty_session_proof(
    tmp_path: Path,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    decision_date = date.fromisoformat(capture["receipt_binding"]["decision_date"])
    provider, resolver, sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=decision_date,
        stock_endpoint_offset=19,
    )
    evaluation_at = datetime.now(_UTC)
    nineteen_session_result = resolver.resolve(
        capture_date=decision_date.isoformat(),
        evaluation_at=evaluation_at,
        horizon_sessions=19,
    )
    assert nineteen_session_result.status == "ready", nineteen_session_result.reason
    assert nineteen_session_result.proof is not None
    with pytest.raises(ValueError, match="session horizon must be 20"):
        verify_natural_maturity_session_proof(
            nineteen_session_result.proof,
            capture_date=decision_date.isoformat(),
            label_end_date=str(nineteen_session_result.endpoint_date),
            evaluation_at=evaluation_at,
            expected_db_path=provider.database_path,
        )

    class NineteenSessionResolver:
        def resolve_personal_prediction_horizon(
            self,
            *,
            capture_date: str,
            evaluation_at: datetime,
        ) -> Any:
            return resolver.resolve(
                capture_date=capture_date,
                evaluation_at=evaluation_at,
                horizon_sessions=19,
            )

    service = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=provider.database_path,
        session_resolver=NineteenSessionResolver(),
    )

    result = service.project_personal_prediction_outcomes(
        capture,
        evaluation_at=evaluation_at,
    )

    assert sessions[18] < sessions[19]
    assert result.status == "pending"
    assert result.matured_sample_count == 0
    assert result.pending_sample_count == 2
    assert "natural_maturity_session_proof_invalid:ValueError" in result.diagnostics
    assert result.metrics is None


def test_personal_natural_outcome_rejects_tampered_calibrated_probability_even_with_new_outer_hash(
    tmp_path: Path,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    capture["delivered_rows"][0]["projection"]["calibrated_probability_bp"] = 10_001
    capture["payload_sha256"] = _payload_hash(
        {key: value for key, value in capture.items() if key != "payload_sha256"}
    )
    service = RecommendationNaturalOutcomeService(
        SimpleNamespace(database_path=tmp_path / "unused.db")  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="calibrated probability"):
        service.project_personal_prediction_outcomes(
            capture,
            evaluation_at=datetime.now(_UTC),
        )


def test_personal_natural_outcome_rejects_policy_confirmed_after_decision(
    tmp_path: Path,
) -> None:
    capture = _complete_cost_personal_capture(tmp_path)
    event = capture["policy_event"]
    policy = dict(event["policy_snapshot"])
    policy_body = {key: value for key, value in policy.items() if key != "policy_sha256"}
    policy_body["confirmed_at"] = "2025-05-01T12:00:01.000000Z"
    policy_body["policy_sha256"] = _policy_hash(
        {key: value for key, value in policy_body.items() if key != "policy_sha256"}
    )
    event["policy_snapshot"] = validate_personal_use_policy_snapshot(policy_body)
    capture["capture_id"] = _capture_id(capture)
    capture["payload_sha256"] = _payload_hash(
        {key: value for key, value in capture.items() if key != "payload_sha256"}
    )
    service = RecommendationNaturalOutcomeService(
        SimpleNamespace(database_path=tmp_path / "unused.db")  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="confirmed after the decision"):
        service.project_personal_prediction_outcomes(
            capture,
            evaluation_at=datetime.now(_UTC),
        )
