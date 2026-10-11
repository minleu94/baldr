from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

import app_module.position_health_daily_refresh_service as _daily_refresh_module

from app_module.position_health_market_source_producer import (
    PositionHealthMarketSourceError,
    PositionHealthMarketSourceProducer,
)
from app_module.position_health_source_providers import (
    DecimalMetricSourceProvider,
    PITConditionSourceProvider,
)
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from scripts import run_position_health_market_sources


DECISION = "2026-09-08"
CUTOFF = datetime(2026, 9, 8, 13, 5, tzinfo=timezone.utc)
OBSERVED = datetime(2026, 9, 8, 13, 5, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_weekend_calendar_cache(tmp_path: Path) -> tuple[Path, Path]:
    """建立於決策前可用、在本次固定 QA 日期仍未過期的年度日曆。"""

    captured_at = datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc)
    raw_response = json.dumps(
        [
            {
                "Name": "測試年度休市",
                "Date": "1150101",
                "Weekday": "四",
                "Description": "依規定放假1日。",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw_response,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        max_age=timedelta(days=31),
    )
    cache_path = (
        tmp_path
        / "isolated-calendar-cache"
        / "twse_holiday_schedule_2026_fixture.json"
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    write_twse_calendar_cache(cache_path, cache, allowed_root=tmp_path)
    return cache_path.parent, cache_path


def _make_market_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE technical_indicators (
            日期 TEXT, 證券代號 TEXT, RSI REAL, MACD REAL, MACD_signal REAL,
            MACD_hist REAL, MA5 REAL, MA10 REAL, MA20 REAL, MA60 REAL,
            ATR REAL, ADX REAL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE daily_prices (
            日期 TEXT, 證券代號 TEXT, 收盤價 REAL, 開盤價 REAL,
            最高價 REAL, 最低價 REAL, 成交股數 INTEGER
        )
        """
    )
    connection.execute(
        "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (DECISION.replace("-", ""), "2330", 48.5, -0.2, -0.1, -0.1, 900, 901, 902, 903, 12.5, 18.0),
    )
    connection.execute(
        "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?)",
        (DECISION.replace("-", ""), "2330", 910.0, 905.0, 915.0, 900.0, 123456),
    )
    connection.commit()
    connection.close()


def _make_inputs(tmp_path: Path, *, with_identity: bool = True) -> tuple[Path, Path, Path, Path, Path]:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": "position-health-daily-refresh.v1",
                "decision_date": DECISION,
                "as_of_date": DECISION,
                "status": "fresh",
                "source_type": "paper_snapshot_read_only",
                "source_read_mode": "sqlite_uri_mode_ro_and_query_only",
                "research_only": True,
                "writes_positions_db": False,
                "auto_action_allowed": False,
                "broker_execution": False,
                "formal_credit": False,
                "source_snapshot_id": "paper-main-20260908",
                "source_snapshot_date": DECISION,
                "source_snapshot_rows_sha256": "sha256:" + "a" * 64,
                "positions": [
                    {
                        "stock_code": "2330",
                        "paper_shares": 1000,
                        "position_id": "paper:2330:entry-a" if with_identity else None,
                        "entry_lineage_id": "paper:2330:entry-a" if with_identity else None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    quick = tmp_path / "quick.json"
    _write_json(
        quick,
        {
            "status": "passed",
            "writes_market_data_db": True,
            "errors": [],
            "warnings": [],
            "end_date": DECISION,
            "completed_at": "2026-09-08T12:32:45+00:00",
        },
    )
    freshness = tmp_path / "freshness.json"
    _write_json(
        freshness,
        {
            "status": "passed",
            "checked_at": "2026-09-08T13:00:01+00:00",
            "checks": {
                "daily_prices_latest_date_key": "20260908",
                "technical_indicators_latest_date": "20260908",
            },
        },
    )
    market = tmp_path / "market.sqlite"
    _make_market_db(market)
    return baseline, quick, freshness, market, tmp_path / "sources"


def test_producer_writes_hash_bound_sources_from_verified_daily_rows(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: OBSERVED,
    ).produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )

    assert result["status"] == "passed"
    assert result["position_snapshot_observation"]["source_snapshot_id"] == "paper-main-20260908"
    assert result["position_snapshot_observation"]["same_day_paper_producer_success_proven"] is False
    assert result["condition_row_count"] == 1
    assert result["metric_row_count"] >= 10
    positions = [{
        "position_id": "paper:2330:entry-a",
        "entry_lineage_id": "paper:2330:entry-a",
        "stock_code": "2330",
    }]
    condition = PITConditionSourceProvider(result["condition_source_path"]).read_for_positions(
        positions,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )
    assert condition.blockers == ()
    observation = condition.values["paper:2330:entry-a"]
    assert observation.result is not None
    assert observation.result.status == "warning"
    assert observation.result.details["paper_position_snapshot_date"] == DECISION
    assert observation.result.details["paper_position_snapshot_id"] == "paper-main-20260908"
    assert observation.current_snapshot is not None
    assert str(observation.current_snapshot.current_price) == "910.0"
    metrics = DecimalMetricSourceProvider(result["metrics_source_path"]).read_for_positions(
        positions,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )
    assert metrics.blockers == ()
    assert metrics.values["paper:2330:entry-a"]
    assert all(type(item.value).__name__ == "Decimal" for item in metrics.values["paper:2330:entry-a"])


def test_source_snapshot_hash_is_stable_across_receipt_recapture(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    first = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: OBSERVED,
    ).produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )
    recaptured_at = OBSERVED + timedelta(minutes=1)
    second = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: recaptured_at,
    ).produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=recaptured_at,
        observed_at=recaptured_at,
    )

    assert second["source_snapshot_hash"] == first["source_snapshot_hash"]
    assert second["available_at"] != first["available_at"]
    assert second["condition_source_path"] != first["condition_source_path"]


def test_producer_accepts_only_candidate_warning_projection_for_market_lane(
    tmp_path: Path,
) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    candidate_message = "Phase 3C candidate source has retryable rows"
    quick_payload = json.loads(quick.read_text(encoding="utf-8"))
    quick_payload.update(
        {
            "status": "passed_with_warnings",
            "warnings": [candidate_message],
            "steps": [
                {
                    "name": name,
                    "status": "skipped" if name == "calculate_technical_indicators" else "passed",
                    "result": {"success": True},
                }
                for name in (
                    "update_twse_daily_prices",
                    "update_tpex_daily_prices",
                    "sync_daily_prices_to_sqlite",
                    "calculate_technical_indicators",
                )
            ]
            + [
                {
                    "name": "update_phase3c_candidate_sources",
                    "status": "warning",
                    "message": candidate_message,
                    "result": {"success": False, "candidate_only": True},
                }
            ],
        }
    )
    _write_json(quick, quick_payload)
    freshness_payload = json.loads(freshness.read_text(encoding="utf-8"))
    freshness_payload.update(
        {
            "status": "degraded",
            "errors": [],
            "warnings": [
                "monthly_revenue_expected_period_not_available",
                "source_freshness_degraded:fundamental.current_monthly_observations",
            ],
            "source_statuses": [
                {"source_id": source_id, "freshness_status": "current"}
                for source_id in (
                    "twse.daily_prices.raw",
                    "tpex.daily_prices.raw",
                    "sqlite.daily_prices",
                    "sqlite.technical_indicators",
                )
            ],
        }
    )
    _write_json(freshness, freshness_payload)

    result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: OBSERVED,
    ).produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )

    assert result["status"] == "degraded"
    assert result["condition_row_count"] == 1
    assert candidate_message in result["warnings"]


def test_producer_rejects_unclassified_quick_warning(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    quick_payload = json.loads(quick.read_text(encoding="utf-8"))
    quick_payload.update(
        {
            "status": "passed_with_warnings",
            "warnings": ["daily price reconciliation unknown"],
            "steps": [],
        }
    )
    _write_json(quick, quick_payload)

    with pytest.raises(PositionHealthMarketSourceError, match="quick_status_not_passed"):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


def test_producer_rejects_baseline_from_different_decision_date(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
    baseline_payload["decision_date"] = "2026-09-07"
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")

    with pytest.raises(PositionHealthMarketSourceError, match="health_baseline_date_mismatch"):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


def test_daily_refresh_baseline_uses_as_of_date_for_holdings_observation_only(
    tmp_path: Path,
) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
    baseline_payload.update(
        {
            "decision_date": "2026-09-07",
            "source_snapshot_date": "2026-09-07",
            "source_snapshot_id": "paper-main-20260907",
            "as_of_date": DECISION,
        }
    )
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")

    result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: OBSERVED,
    ).produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )

    assert result["status"] == "degraded"
    assert result["decision_date"] == DECISION
    assert result["position_snapshot_observation"] == {
        "schema_version": "position-health-daily-refresh.v1",
        "source_snapshot_id": "paper-main-20260907",
        "source_snapshot_date": "2026-09-07",
        "source_snapshot_rows_sha256": "sha256:" + "a" * 64,
        "decision_date": "2026-09-07",
        "as_of_date": DECISION,
        "observation_semantics": "paper_holdings_snapshot_observation_only",
        "same_day_paper_producer_success_proven": False,
        "is_stale_as_of": True,
    }
    assert "paper_holdings_snapshot_older_than_health_as_of:2026-09-07" in result[
        "warnings"
    ]
    condition_payload = json.loads(
        Path(result["condition_source_path"]).read_text(encoding="utf-8")
    )
    assert condition_payload["as_of_date"] == DECISION
    assert condition_payload["positions"][0]["result"]["details"][
        "paper_position_snapshot_date"
    ] == "2026-09-07"


def test_daily_refresh_baseline_rejects_snapshot_after_health_as_of(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
    baseline_payload.update(
        {
            "decision_date": "2026-09-09",
            "source_snapshot_date": "2026-09-09",
            "as_of_date": DECISION,
        }
    )
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")

    with pytest.raises(PositionHealthMarketSourceError, match="health_baseline_date_mismatch"):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


def test_daily_refresh_baseline_rejects_as_of_different_from_requested_date(
    tmp_path: Path,
) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
    baseline_payload["as_of_date"] = "2026-09-07"
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")

    with pytest.raises(PositionHealthMarketSourceError, match="health_baseline_date_mismatch"):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


def test_daily_refresh_baseline_requires_snapshot_identity_provenance(
    tmp_path: Path,
) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
    baseline_payload["decision_date"] = "2026-09-07"
    baseline_payload["source_snapshot_date"] = "2026-09-07"
    baseline_payload.pop("source_snapshot_rows_sha256")
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")

    with pytest.raises(
        PositionHealthMarketSourceError,
        match="health_baseline_snapshot_identity_invalid",
    ):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


@pytest.mark.parametrize(
    ("field", "unsafe_value", "error_code"),
    [
        ("status", "degraded", "health_baseline_source_contract_invalid"),
        ("source_type", "manual_json", "health_baseline_source_contract_invalid"),
        ("source_read_mode", "sqlite_rw", "health_baseline_source_contract_invalid"),
        ("research_only", False, "health_baseline_boundary_invalid"),
        ("writes_positions_db", True, "health_baseline_boundary_invalid"),
        ("auto_action_allowed", True, "health_baseline_boundary_invalid"),
        ("broker_execution", True, "health_baseline_boundary_invalid"),
        ("formal_credit", True, "health_baseline_boundary_invalid"),
    ],
)
def test_stale_daily_refresh_requires_read_only_research_contract(
    tmp_path: Path,
    field: str,
    unsafe_value: object,
    error_code: str,
) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
    baseline_payload.update(
        {
            "decision_date": "2026-09-07",
            "source_snapshot_date": "2026-09-07",
            "source_snapshot_id": "paper-main-20260907",
            "as_of_date": DECISION,
            field: unsafe_value,
        }
    )
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")

    with pytest.raises(PositionHealthMarketSourceError, match=error_code):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


def test_legacy_baseline_does_not_gain_daily_refresh_as_of_fallback(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    baseline_payload = json.loads(baseline.read_text(encoding="utf-8"))
    baseline_payload["schema_version"] = "position-health-legacy.v1"
    baseline_payload["decision_date"] = "2026-09-07"
    baseline_payload["as_of_date"] = DECISION
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")

    with pytest.raises(PositionHealthMarketSourceError, match="health_baseline_date_mismatch"):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


def test_producer_keeps_unresolved_identity_out_of_source_rows(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path, with_identity=False)
    result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: OBSERVED,
    ).produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )
    assert result["status"] == "degraded"
    assert result["condition_row_count"] == 0
    assert result["metric_row_count"] == 0
    assert result["unresolved_identity_codes"] == ["2330"]
    payload = json.loads(Path(result["condition_source_path"]).read_text(encoding="utf-8"))
    assert payload["positions"] == []


def test_producer_rejects_source_receipt_after_health_cutoff(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    payload = json.loads(quick.read_text(encoding="utf-8"))
    payload["completed_at"] = "2026-09-08T13:06:00+00:00"
    quick.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PositionHealthMarketSourceError, match="quick_status_completed_at_future"):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


def test_producer_rejects_current_capture_for_an_earlier_cutoff(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    with pytest.raises(
        PositionHealthMarketSourceError,
        match="market_capture_started_after_decision_cutoff",
    ):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: OBSERVED,
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=datetime(2026, 9, 8, 13, 4, tzinfo=timezone.utc),
            observed_at=OBSERVED,
        )


def test_derived_payload_is_create_only_when_inputs_change(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    producer = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: OBSERVED,
    )
    first = producer.produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )
    first_bytes = Path(first["condition_source_path"]).read_bytes()
    changed = json.loads(baseline.read_text(encoding="utf-8"))
    changed["positions"][0]["paper_shares"] = 999
    baseline.write_text(json.dumps(changed), encoding="utf-8")
    second = producer.produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )
    assert Path(first["condition_source_path"]).read_bytes() == first_bytes
    assert second["condition_source_path"] != first["condition_source_path"]
    assert Path(second["condition_source_path"]).is_file()


def test_receipt_binds_market_capture_after_upstream_receipts(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: OBSERVED,
    ).produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )
    payload = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert payload["market_capture_started_at"] == OBSERVED.isoformat()
    assert payload["market_capture_completed_at"] == OBSERVED.isoformat()
    assert payload["available_at"] == OBSERVED.isoformat()
    assert payload["upstream_receipt_available_at"] < payload["available_at"]


def test_slow_market_read_cannot_publish_after_explicit_cutoff(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    clock_values = iter(
        (
            datetime(2026, 9, 8, 13, 4, 58, tzinfo=timezone.utc),
            datetime(2026, 9, 8, 13, 4, 59, tzinfo=timezone.utc),
            datetime(2026, 9, 8, 13, 5, 1, tzinfo=timezone.utc),
        )
    )
    with pytest.raises(
        PositionHealthMarketSourceError,
        match="market_capture_completed_after_decision_cutoff",
    ):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: next(clock_values),
        ).produce(
            baseline_path=baseline,
            output_dir=output,
            decision_date=DECISION,
            decision_at=CUTOFF,
            observed_at=OBSERVED,
        )


def test_natural_capture_uses_real_start_and_completion_as_cutoff(tmp_path: Path) -> None:
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    start = datetime(2026, 9, 8, 13, 4, 58, tzinfo=timezone.utc)
    capture_start = datetime(2026, 9, 8, 13, 4, 59, tzinfo=timezone.utc)
    capture_end = datetime(2026, 9, 8, 13, 5, 2, tzinfo=timezone.utc)
    clock_values = iter((start, capture_start, capture_end))
    result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: next(clock_values),
    ).produce(
        baseline_path=baseline,
        output_dir=output,
        decision_date=DECISION,
    )
    assert result["market_capture_started_at"] == capture_start.isoformat()
    assert result["market_capture_completed_at"] == capture_end.isoformat()
    assert result["available_at"] == capture_end.isoformat()
    assert result["decision_cutoff_at"] == capture_end.isoformat()
    assert result["observed_at"] == capture_end.isoformat()


def test_cli_leaves_capture_clock_with_producer(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeProducer:
        def __init__(self, **kwargs: object) -> None:
            captured["init"] = kwargs

        def produce(self, **kwargs: object) -> dict[str, object]:
            captured["produce"] = kwargs
            return {"status": "degraded", "warnings": [], "blockers": []}

    monkeypatch.setattr(
        run_position_health_market_sources,
        "PositionHealthMarketSourceProducer",
        FakeProducer,
    )
    exit_code = run_position_health_market_sources.main(
        [
            "--baseline",
            str(tmp_path / "baseline.json"),
            "--market-db",
            str(tmp_path / "market.sqlite"),
            "--quick-status",
            str(tmp_path / "quick.json"),
            "--freshness-status",
            str(tmp_path / "freshness.json"),
            "--output-dir",
            str(tmp_path / "sources"),
            "--decision-date",
            DECISION,
        ]
    )
    assert exit_code == 0
    assert isinstance(captured["init"], dict)
    assert "now_provider" not in captured["init"]
    assert isinstance(captured["produce"], dict)
    assert captured["produce"]["decision_at"] is None
    assert captured["produce"]["observed_at"] is None


@pytest.mark.parametrize("scenario", ["valid_weekend", "intervening_trade", "future", "calendar_missing"])
def test_health_market_day_requires_verified_calendar_gap(tmp_path, scenario):
    baseline, quick, freshness, market, output = _make_inputs(tmp_path)
    now = datetime(2026,9,13,1,0,tzinfo=timezone.utc)
    payload = json.loads(baseline.read_text(encoding="utf-8")); payload["as_of_date"] = "2026-09-13"
    _write_json(baseline, payload)
    payload = json.loads(quick.read_text(encoding="utf-8"));payload.update(end_date="2026-09-12",completed_at="2026-09-12T12:00:00+00:00")
    _write_json(quick,payload)
    market_day = "20260910" if scenario == "intervening_trade" else ("20260914" if scenario == "future" else "20260911")
    payload = json.loads(freshness.read_text(encoding="utf-8"));payload["checked_at"] = "2026-09-13T00:00:00+00:00"
    payload["checks"].update(expected_official_session=market_day,daily_prices_latest_date_key=market_day,technical_indicators_latest_date=market_day)
    _write_json(freshness,payload)
    with sqlite3.connect(market) as conn:
        conn.execute("UPDATE technical_indicators SET 日期=?",(market_day,))
        conn.execute("UPDATE daily_prices SET 日期=?",(market_day,))
    if scenario == "calendar_missing":
        cache = None
        cache_file = None
    else:
        cache, cache_file = _write_weekend_calendar_cache(tmp_path)
    producer = PositionHealthMarketSourceProducer(market_db_path=market,quick_status_path=quick,freshness_status_path=freshness,calendar_cache_path=cache,now_provider=lambda:now)
    if scenario != "valid_weekend":
        with pytest.raises(PositionHealthMarketSourceError):
            producer.produce(baseline_path=baseline,output_dir=output,decision_date="2026-09-13",decision_at=now,observed_at=now)
        assert not output.exists()
    else:
        inputs_before = {
            path: path.read_bytes()
            for path in (baseline, quick, freshness, market, cache_file)
            if path is not None
        }
        market_stat_before = market.stat()
        cache_stat_before = cache_file.stat()
        result = producer.produce(baseline_path=baseline,output_dir=output,decision_date="2026-09-13",decision_at=now,observed_at=now)
        assert result["decision_date"] == "2026-09-13"
        assert result["market_data_date"] == "2026-09-11"
        assert result["market_calendar"]["status"] == "verified"
        assert result["market_calendar"]["start_date"] == "2026-09-11"
        assert result["market_calendar"]["end_date"] == "2026-09-13"
        assert result["market_calendar"]["trading_dates_count"] == 1
        assert result["market_calendar"]["years"][2026]["available_at"] == (
            "2026-09-12T13:00:00+00:00"
        )
        assert result["available_at"] == now.isoformat()
        assert result["decision_cutoff_at"] == now.isoformat()
        assert result["observed_at"] == now.isoformat()
        assert result["condition_row_count"] == 1
        condition = json.loads(Path(result["condition_source_path"]).read_text(encoding="utf-8"))
        assert condition["as_of_date"] == "2026-09-13" and condition["market_data_date"] == "2026-09-11"
        assert all(path.read_bytes() == raw for path, raw in inputs_before.items())
        market_stat_after = market.stat()
        cache_stat_after = cache_file.stat()
        assert (market_stat_after.st_size, market_stat_after.st_mtime_ns) == (
            market_stat_before.st_size,
            market_stat_before.st_mtime_ns,
        )
        assert (cache_stat_after.st_size, cache_stat_after.st_mtime_ns) == (
            cache_stat_before.st_size,
            cache_stat_before.st_mtime_ns,
        )


def _create_real_v2_health_baseline(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    state_db = tmp_path / "paper" / "paper.sqlite"
    state_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(state_db) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_portfolio_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                source_result_id TEXT NOT NULL,
                cash TEXT NOT NULL,
                total_value TEXT NOT NULL
            );
            CREATE TABLE paper_portfolio_positions (
                snapshot_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                weight_bp INTEGER NOT NULL,
                PRIMARY KEY (snapshot_id, stock_code)
            );
            """
        )
        connection.execute(
            "INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            ("paper-main-20260908", "paper-main", "2026-09-08", "paper-eod-20260908", "100000", "200000"),
        )
        connection.execute(
            "INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?)",
            ("paper-main-20260908", "2330", 100, 5000),
        )
    status_path = tmp_path / "paper" / "latest_status.json"
    _write_json(
        status_path,
        {
            "schema_version": "paper-portfolio-daily-status.v1",
            "producer": "scripts.scheduled.run_paper_portfolio_daily_isolated",
            "status": "passed",
            "decision_date": "2026-09-08",
            "decision_at": "2026-09-08T08:30:00+08:00",
            "snapshot_id": "paper-main-20260908",
            "portfolio_id": "paper-main",
            "state_db": str(state_db.resolve()),
            "paper_ledger_db": str((state_db.parent.parent / "paper_trade_ledger.sqlite").resolve()),
            "snapshot_appended": True,
            "paper_ledger_transitions_applied": 0,
            "trading_calendar_validated": True,
            "writes_market_db": False,
            "auto_rebalance_allowed": False,
            "changes_advice": False,
            "broker_execution": False,
        },
    )
    output = tmp_path / "health"
    receipt = _daily_refresh_module.PositionHealthDailyRefreshService(
        state_db_path=state_db,
        status_path=status_path,
    ).refresh(
        as_of_date=date(2026, 9, 8),
        output_dir=output,
        observed_at=datetime.now(timezone.utc),
    )
    assert receipt["status"] == "passed"
    baseline_path = Path(str(receipt["baseline_path"]))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["schema_version"] == "position-health-daily-refresh.v2"
    return baseline_path, baseline


def test_real_daily_refresh_v2_keeps_exact_schema_and_unresolved_identity_degraded(
    tmp_path: Path,
) -> None:
    _baseline_v1, quick, freshness, market, _legacy_output = _make_inputs(tmp_path)
    baseline_path, baseline = _create_real_v2_health_baseline(tmp_path)
    now = datetime.now(timezone.utc) + timedelta(seconds=2)
    output = tmp_path / "market-v2"
    result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: now,
    ).produce(
        baseline_path=baseline_path,
        output_dir=output,
        decision_date=DECISION,
        decision_at=now,
        observed_at=now,
    )

    observation = result["position_snapshot_observation"]
    assert observation["schema_version"] == "position-health-daily-refresh.v2"
    assert observation["producer"] == "app_module.position_health_daily_refresh_service"
    assert observation["portfolio_id"] == "paper-main"
    assert observation["source_result_id"] == "paper-eod-20260908"
    assert observation["source_snapshot_id"] == "paper-main-20260908"
    assert observation["source_snapshot_rows_sha256"] == baseline[
        "source_snapshot_rows_sha256"
    ]
    assert observation["source_decision_boundary"] == "paper-main-preopen"
    assert observation["same_day_paper_producer_success_proven"] is False
    assert result["status"] == "degraded"
    assert result["unresolved_identity_codes"] == ["2330"]
    assert result["condition_row_count"] == 0
    assert result["writes_paper_state"] is False
    assert result["writes_formal_state"] is False
    assert result["broker_execution"] is False

    unqualified = dict(baseline)
    unqualified["source_decision_boundary"] = None
    unqualified["source_decision_at"] = None
    unqualified_path = tmp_path / "unqualified-boundary.json"
    _write_json(unqualified_path, unqualified)
    unqualified_result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: now,
    ).produce(
        baseline_path=unqualified_path,
        output_dir=tmp_path / "market-unqualified-boundary",
        decision_date=DECISION,
        decision_at=now,
        observed_at=now,
    )
    assert unqualified_result["status"] == "degraded"
    assert unqualified_result["unresolved_identity_codes"] == ["2330"]
    assert unqualified_result["condition_row_count"] == 0
    assert (
        unqualified_result["position_snapshot_observation"]["source_decision_boundary"]
        is None
    )

    invalid_cases = (
        (
            "future-source-clock",
            {"source_available_at": "2099-01-01T00:00:00Z"},
            "health_baseline_source_available_after_observed",
        ),
        (
            "source-observed-after-cutoff",
            {"source_observed_at": "2099-01-01T00:00:00Z"},
            "health_baseline_source_observed_after_cutoff",
        ),
        (
            "snapshot-date-mismatch",
            {"source_snapshot_date": "2026-09-07"},
            "health_baseline_date_mismatch",
        ),
        (
            "partial-snapshot-identity",
            {"source_snapshot_rows_sha256": None},
            "health_baseline_snapshot_rows_hash_invalid",
        ),
        (
            "wrong-portfolio",
            {"portfolio_id": "paper-other"},
            "health_baseline_portfolio_invalid",
        ),
        (
            "late-preopen-clock",
            {"source_decision_at": "2026-09-08T09:00:00+08:00"},
            "health_baseline_preopen_clock_invalid",
        ),
    )
    for name, updates, error in invalid_cases:
        invalid = dict(baseline)
        invalid.update(updates)
        invalid_path = tmp_path / f"{name}.json"
        _write_json(invalid_path, invalid)
        with pytest.raises(PositionHealthMarketSourceError) as raised:
            PositionHealthMarketSourceProducer(
                market_db_path=market,
                quick_status_path=quick,
                freshness_status_path=freshness,
                now_provider=lambda: now,
            ).produce(
                baseline_path=invalid_path,
                output_dir=tmp_path / f"market-{name}",
                decision_date=DECISION,
                decision_at=now,
                observed_at=now,
            )
        assert str(raised.value) == error

    future_identity_source = dict(baseline)
    future_identity_source["position_identity_source"] = {
        "schema_version": "paper-position-identity-source.v1",
        "provider": "PaperPositionIdentityProvider",
        "portfolio_id": "paper-main",
        "requested_snapshot_id": baseline["source_snapshot_id"],
        "requested_snapshot_date": baseline["source_snapshot_date"],
        "observed_at": "2099-01-01T00:00:00Z",
        "status": "degraded",
        "resolved_codes": [],
        "identity_count": 0,
    }
    future_identity_source_path = tmp_path / "future-identity-source.json"
    _write_json(future_identity_source_path, future_identity_source)
    with pytest.raises(
        PositionHealthMarketSourceError,
        match="health_baseline_identity_source_observed_after_cutoff",
    ):
        PositionHealthMarketSourceProducer(
            market_db_path=market,
            quick_status_path=quick,
            freshness_status_path=freshness,
            now_provider=lambda: now,
        ).produce(
            baseline_path=future_identity_source_path,
            output_dir=tmp_path / "market-future-identity-source",
            decision_date=DECISION,
            decision_at=now,
            observed_at=now,
        )

    for name, entry_date, identity_available_at, error in (
        (
            "identity-entry-not-preopen",
            baseline["source_snapshot_date"],
            baseline["source_observed_at"],
            "health_baseline_identity_entry_not_preopen",
        ),
        (
            "identity-clock-after-source",
            "2026-09-07",
            "2099-01-01T00:00:00Z",
            "health_baseline_identity_available_after_observed",
        ),
    ):
        invalid_identity = dict(baseline)
        invalid_positions = [dict(item) for item in baseline["positions"]]
        invalid_row = invalid_positions[0]
        invalid_row["position_id"] = "paper:paper-main:2330"
        invalid_row["entry_lineage_id"] = "entry:2330"
        invalid_row["position_identity_source"] = {
            "status": "same_snapshot_verified",
            "stock_code": "2330",
            "position_id": invalid_row["position_id"],
            "entry_lineage_id": invalid_row["entry_lineage_id"],
            "current_snapshot_id": baseline["source_snapshot_id"],
            "current_snapshot_date": baseline["source_snapshot_date"],
            "entry_date": entry_date,
            "available_at": identity_available_at,
        }
        invalid_identity["position_identity_source"] = {
            "schema_version": "paper-position-identity-source.v1",
            "provider": "PaperPositionIdentityProvider",
            "portfolio_id": "paper-main",
            "requested_snapshot_id": baseline["source_snapshot_id"],
            "requested_snapshot_date": baseline["source_snapshot_date"],
            "observed_at": baseline["source_observed_at"],
            "status": "verified",
            "resolved_codes": ["2330"],
            "identity_count": 1,
        }
        invalid_identity["positions"] = invalid_positions
        invalid_path = tmp_path / f"{name}.json"
        _write_json(invalid_path, invalid_identity)
        with pytest.raises(PositionHealthMarketSourceError) as raised:
            PositionHealthMarketSourceProducer(
                market_db_path=market,
                quick_status_path=quick,
                freshness_status_path=freshness,
                now_provider=lambda: now,
            ).produce(
                baseline_path=invalid_path,
                output_dir=tmp_path / f"market-{name}",
                decision_date=DECISION,
                decision_at=now,
                observed_at=now,
            )
        assert str(raised.value) == error


def test_unknown_daily_refresh_schema_keeps_legacy_observation_contract(
    tmp_path: Path,
) -> None:
    baseline_path, quick, freshness, market, output = _make_inputs(tmp_path)
    unknown = json.loads(baseline_path.read_text(encoding="utf-8"))
    unknown["schema_version"] = "position-health-daily-refresh.v99"
    unknown.pop("producer", None)
    unknown.pop("source_type", None)
    unknown.pop("source_read_mode", None)
    unknown_path = tmp_path / "unknown-schema.json"
    _write_json(unknown_path, unknown)

    result = PositionHealthMarketSourceProducer(
        market_db_path=market,
        quick_status_path=quick,
        freshness_status_path=freshness,
        now_provider=lambda: OBSERVED,
    ).produce(
        baseline_path=unknown_path,
        output_dir=output,
        decision_date=DECISION,
        decision_at=CUTOFF,
        observed_at=OBSERVED,
    )

    observation = result["position_snapshot_observation"]
    assert observation["schema_version"] == "position-health-daily-refresh.v99"
    assert observation["observation_semantics"] == "legacy_baseline_decision_date_match"
    assert "source_snapshot_rows_sha256" not in observation
