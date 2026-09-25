from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import cast

from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from scripts.scheduled.paper_execution_dependency_gate import (
    _paper_eod_freshness_projection,
    inspect_dependency,
)


TARGET = "20260908"
OBSERVED = datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_calendar_cache(
    root: Path,
    *,
    year: int,
    closed_date: date,
    captured_at: datetime,
    max_age: timedelta = timedelta(days=7),
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    raw_response = json.dumps(
        [
            {
                "Name": "測試年度休市",
                "Date": f"{closed_date.year - 1911:03d}{closed_date:%m%d}",
                "Weekday": str(closed_date.weekday()),
                "Description": "isolated official closed-day fixture",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=year,
        raw_response=raw_response,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"ETag": f'"paper-gate-fixture-{year}"'},
        max_age=max_age,
    )
    path = root / f"twse_holiday_schedule_{year}_paper_gate_fixture.json"
    write_twse_calendar_cache(path, cache, allowed_root=root)
    return path


def _seed_ready_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    db_path = data_root / "sqlite" / "twstock.db"
    (data_root / "daily_price").mkdir(parents=True)
    (data_root / "daily_price_tpex").mkdir(parents=True)
    (data_root / "daily_price" / f"{TARGET}.csv").write_text(
        "證券代號,開盤價\n2330,100.0\n",
        encoding="utf-8",
    )
    (data_root / "daily_price_tpex" / f"{TARGET}.csv").write_text(
        "日期,證券代號,開盤價\n20260908,2330,100.0\n",
        encoding="utf-8",
    )

    db_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(db_path)
    connection.execute('CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "開盤價" REAL)')
    connection.execute(
        'INSERT INTO daily_prices ("日期", "證券代號", "開盤價") VALUES (?, ?, ?)',
        (TARGET, "2330", 100.0),
    )
    connection.commit()
    connection.close()

    quick_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    _write_json(
        quick_path,
        {
            "status": "passed",
            "end_date": "2026-09-08",
            "checked_at": "2026-09-08T20:00:00+08:00",
            "steps": [
                {"name": "update_twse_daily_prices", "status": "passed", "result": {}},
                {"name": "sync_daily_prices_to_sqlite", "status": "passed", "result": {}},
            ],
        },
    )
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    _write_json(
        freshness_path,
        {
            "status": "passed",
            "checked_at": "2026-09-08T20:05:00+08:00",
            "checks": {
                "daily_prices_latest_date": TARGET,
                "data_update_quick_checked_date": "2026-09-08",
            },
        },
    )
    return data_root, output_root, db_path


def _set_degraded_non_eod_freshness(output_root: Path) -> None:
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness.update(
        {
            "status": "degraded",
            "errors": [],
            "warnings": [
                "monthly_revenue_expected_period_not_available",
                "quarterly_statement_expected_period_not_available",
                "source_freshness_degraded:fundamental.current_monthly_observations",
                "source_freshness_degraded:fundamental.current_statement_observations",
                "source_freshness_degraded:institutional_flows",
                "source_freshness_degraded:credit_transactions",
            ],
            "source_statuses": [
                {
                    "source_id": source_id,
                    "freshness_status": "current",
                    "actual_period": TARGET,
                    "expected_period": TARGET,
                }
                for source_id in (
                    "twse.daily_prices.raw",
                    "tpex.daily_prices.raw",
                    "sqlite.daily_prices",
                )
            ]
            + [
                {
                    "source_id": "fundamental.monthly_revenues",
                    "freshness_status": "stale",
                    "actual_period": "2026-06",
                    "expected_period": "2026-08",
                    "candidate_only": True,
                },
                {
                    "source_id": "fundamental.quarterly_statements",
                    "freshness_status": "stale",
                    "actual_period": "2024-Q1",
                    "expected_period": "2026-Q2",
                    "candidate_only": True,
                },
                {
                    "source_id": "fundamental.current_monthly_observations",
                    "freshness_status": "partial",
                    "actual_period": "2026-08",
                    "expected_period": "2026-08",
                },
                {
                    "source_id": "fundamental.current_statement_observations",
                    "freshness_status": "partial",
                    "actual_period": "2026-Q2",
                    "expected_period": "2026-Q2",
                },
                {
                    "source_id": "institutional_flows",
                    "freshness_status": "stale",
                    "actual_period": "20260908",
                    "expected_period": "20260915",
                },
                {
                    "source_id": "credit_transactions",
                    "freshness_status": "stale",
                    "actual_period": "20260908",
                    "expected_period": "20260915",
                    "candidate_only": True,
                    "frequency": "daily candidate source",
                    "downstream": ["candidate research only"],
                    "update_entry": "UpdateService.update_phase3c_candidate_range",
                    "reason": "latest candidate observation is behind the expected official session",
                },
            ],
        }
    )
    _write_json(freshness_path, freshness)


def test_dependency_gate_requires_same_date_receipts_source_hash_and_db_rows(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "ready"
    assert result["ready"] is True
    assert result["target_date"] == "2026-09-08"
    assert str(result["source_hash"]).startswith("sha256:")
    assert result["market_observation"]["mode"] == "ro/query_only"  # type: ignore[index]
    assert result["source_db_written"] is False
    assert result["source_files_written"] is False
    assert result["source_db_readback"]["twse"]["matched_rows"] == 1  # type: ignore[index]
    assert result["source_db_readback"]["tpex"]["matched_rows"] == 1  # type: ignore[index]


def test_dependency_gate_allows_explicit_non_eod_degraded_freshness_with_projection(
    tmp_path: Path,
) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "ready_with_warnings"
    assert result["ready"] is True
    assert result["freshness_status"] == "degraded"
    projection = result["freshness_lane"]
    assert projection["aggregate_status"] == "degraded"  # type: ignore[index]
    assert projection["status"] == "ready_with_warnings"  # type: ignore[index]
    assert projection["gate_eligible"] is True  # type: ignore[index]
    assert "freshness_status_not_passed:degraded" not in result["blockers"]  # type: ignore[operator]
    assert any(
        str(item).startswith("paper_eod_ignored_non_eod_freshness:")
        for item in cast(list[object], result["warnings"])
    )


def test_dependency_gate_blocks_unknown_degraded_warning(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["warnings"].append("source_freshness_degraded:unregistered_lane")
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "blocked"
    assert result["ready"] is False
    assert "freshness_lane_warning_unclassified:source_freshness_degraded:unregistered_lane" in result[
        "blockers"
    ]  # type: ignore[operator]


def test_dependency_gate_blocks_degraded_errors_and_required_source_partial(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["errors"] = ["sqlite read error"]
    for source in freshness["source_statuses"]:
        if source["source_id"] == "sqlite.daily_prices":
            source["freshness_status"] = "partial"
            break
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    blockers = cast(list[object], result["blockers"])
    assert result["status"] == "blocked"
    assert "freshness_lane_errors_present" in blockers  # type: ignore[operator]
    assert "freshness_required_source_not_current:sqlite.daily_prices:partial" in blockers  # type: ignore[operator]
    assert "freshness_status_not_passed:degraded" in blockers  # type: ignore[operator]


def test_dependency_gate_rejects_missing_or_malformed_freshness_lane_schema(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["source_statuses"] = [
        source
        for source in freshness["source_statuses"]
        if source["source_id"] != "tpex.daily_prices.raw"
    ]
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    missing = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )
    assert "freshness_required_source_missing:tpex.daily_prices.raw" in missing["blockers"]  # type: ignore[operator]

    freshness["source_statuses"] = "malformed"
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")
    malformed = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )
    assert "freshness_lane_source_statuses_malformed" in malformed["blockers"]  # type: ignore[operator]


def test_dependency_gate_rejects_failed_non_eod_source_even_when_warning_is_named(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    for source in freshness["source_statuses"]:
        if source["source_id"] == "institutional_flows":
            source["freshness_status"] = "failed"
            break
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert "freshness_non_eod_source_status_not_degraded:institutional_flows:failed" in result[
        "blockers"
    ]  # type: ignore[operator]


def test_dependency_gate_rejects_unattributed_noncurrent_source_status(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["source_statuses"].extend(
        [
            {"source_id": "sqlite.market_indices", "freshness_status": "stale"},
            {"source_id": "unregistered_unknown_source", "freshness_status": "unknown"},
        ]
    )
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    blockers = cast(list[object], result["blockers"])
    assert "freshness_lane_noncurrent_source_unattributed:sqlite.market_indices:stale" in blockers
    assert "freshness_lane_source_status_unknown:unregistered_unknown_source" in blockers


def test_dependency_gate_classifies_only_two_non_eod_unknown_sources(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["source_statuses"].extend(
        [
            {
                "source_id": "tdcc_shareholding",
                "freshness_status": "unknown",
                "reason": "official rows ingested; per-market coverage and availability must be checked before declaring complete",
                "actual_period": "20260904",
                "expected_period": None,
                "candidate_only": False,
                "available_at": None,
                "coverage": {"table_exists": True, "db_row_count": 4047},
            },
            {
                "source_id": "fundamental.statement_availability_map",
                "freshness_status": "unknown",
                "reason": "file_missing",
                "actual_period": None,
                "expected_period": None,
                "candidate_only": False,
                "available_at": None,
                "coverage": {"file_exists": False, "bytes": None},
            },
        ]
    )
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "ready_with_warnings"
    assert result["ready"] is True
    projection = cast(dict[str, object], result["freshness_lane"])
    excluded = cast(dict[str, dict[str, object]], projection["not_required_for_paper_eod"])
    assert set(excluded) == {
        "credit_transactions",
        "tdcc_shareholding",
        "fundamental.statement_availability_map",
    }
    assert excluded["tdcc_shareholding"]["reason_code"] == (
        "weekly_candidate_completeness_not_proven"
    )
    assert excluded["fundamental.statement_availability_map"]["reason_code"] == (
        "fundamental_pit_mapping_missing"
    )
    tdcc_diagnostic = cast(dict[str, object], excluded["tdcc_shareholding"]["source_diagnostic"])
    statement_diagnostic = cast(
        dict[str, object], excluded["fundamental.statement_availability_map"]["source_diagnostic"]
    )
    assert tdcc_diagnostic["reason"] == (
        "official rows ingested; per-market coverage and availability must be checked before declaring complete"
    )
    assert statement_diagnostic["reason"] == "file_missing"
    assert "freshness_lane_source_status_unknown:tdcc_shareholding" not in result["blockers"]  # type: ignore[operator]
    assert (
        "freshness_lane_source_status_unknown:fundamental.statement_availability_map"
        not in result["blockers"]  # type: ignore[operator]
    )


def test_dependency_gate_keeps_explicit_unknown_source_failed_closed(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["source_statuses"].append(
        {"source_id": "tdcc_shareholding", "freshness_status": "failed"}
    )
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["ready"] is False
    assert "freshness_lane_noncurrent_source_blocked:tdcc_shareholding:failed" in result[
        "blockers"
    ]  # type: ignore[operator]


def _set_candidate_credit_stale_without_warning(
    output_root: Path,
    *,
    status: str = "stale",
) -> None:
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["warnings"] = [
        warning
        for warning in freshness["warnings"]
        if warning != "source_freshness_degraded:credit_transactions"
    ]
    for source in freshness["source_statuses"]:
        if source["source_id"] == "credit_transactions":
            source.update(
                {
                    "freshness_status": status,
                    "actual_period": "2026-09-21",
                    "expected_period": "2026-09-22",
                    "missing_periods": ["2026-09-22"],
                    "candidate_only": True,
                    "frequency": "daily candidate source",
                    "downstream": ["candidate research only"],
                    "update_entry": "UpdateService.update_phase3c_candidate_range",
                    "reason": "latest candidate observation is behind the expected official session",
                    "reason_code": "candidate_latest_period_behind_expected",
                }
            )
            break
    _write_json(freshness_path, freshness)


def test_dependency_gate_projects_named_candidate_credit_stale_as_not_required(
    tmp_path: Path,
) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    _set_candidate_credit_stale_without_warning(output_root)

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "ready_with_warnings"
    assert result["ready"] is True
    projection = cast(dict[str, object], result["freshness_lane"])
    excluded = cast(dict[str, dict[str, object]], projection["not_required_for_paper_eod"])
    credit = excluded["credit_transactions"]
    assert credit["policy_version"] == "paper-eod-candidate-non-required.v1"
    assert credit["reason_code"] == "p0_candidate_source_not_paper_eod_input"
    assert credit["consumer_boundary"] == "p0_candidate_shadow"
    diagnostic = cast(dict[str, object], credit["source_diagnostic"])
    assert diagnostic["candidate_only"] is True
    assert diagnostic["missing_periods"] == ["2026-09-22"]
    assert diagnostic["downstream"] == ["candidate research only"]
    assert credit["freshness_status"] == "stale"
    assert credit["reason"] == "latest candidate observation is behind the expected official session"
    assert "freshness_lane_noncurrent_source_unattributed:credit_transactions:stale" not in result[
        "blockers"
    ]  # type: ignore[operator]


def test_dependency_gate_projects_named_candidate_credit_partial_as_not_required(
    tmp_path: Path,
) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    _set_candidate_credit_stale_without_warning(output_root, status="partial")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "ready_with_warnings"
    assert result["ready"] is True
    projection = cast(dict[str, object], result["freshness_lane"])
    excluded = cast(dict[str, dict[str, object]], projection["not_required_for_paper_eod"])
    assert excluded["credit_transactions"]["freshness_status"] == "partial"


def test_dependency_gate_candidate_credit_policy_mismatch_stays_blocked(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    _set_candidate_credit_stale_without_warning(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    for source in freshness["source_statuses"]:
        if source["source_id"] == "credit_transactions":
            source["downstream"] = ["paper eod"]
            break
    _write_json(freshness_path, freshness)

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "blocked"
    assert result["ready"] is False
    assert "freshness_lane_noncurrent_source_unattributed:credit_transactions:stale" in result[
        "blockers"
    ]  # type: ignore[operator]


def test_dependency_gate_candidate_credit_warning_policy_mismatch_stays_blocked(
    tmp_path: Path,
) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    for source in freshness["source_statuses"]:
        if source["source_id"] == "credit_transactions":
            source["update_entry"] = "unexpected.update"
            break
    _write_json(freshness_path, freshness)

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "blocked"
    assert result["ready"] is False
    assert "freshness_lane_noncurrent_source_unattributed:credit_transactions:stale" in result[
        "blockers"
    ]  # type: ignore[operator]


def test_dependency_gate_candidate_credit_warning_without_reason_stays_blocked(
    tmp_path: Path,
) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    for source in freshness["source_statuses"]:
        if source["source_id"] == "credit_transactions":
            source["reason"] = ""
            break
    _write_json(freshness_path, freshness)

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "blocked"
    assert result["ready"] is False
    assert "freshness_lane_noncurrent_source_unattributed:credit_transactions:stale" in result[
        "blockers"
    ]  # type: ignore[operator]


def test_dependency_gate_candidate_credit_non_candidate_stays_blocked(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    _set_degraded_non_eod_freshness(output_root)
    _set_candidate_credit_stale_without_warning(output_root)
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    for source in freshness["source_statuses"]:
        if source["source_id"] == "credit_transactions":
            source["candidate_only"] = False
            break
    _write_json(freshness_path, freshness)

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "blocked"
    assert result["ready"] is False
    assert "freshness_lane_noncurrent_source_unattributed:credit_transactions:stale" in result[
        "blockers"
    ]  # type: ignore[operator]


def test_dependency_gate_candidate_credit_failed_or_unknown_stays_blocked(tmp_path: Path) -> None:
    for status in ("failed", "expected_wait", "unknown"):
        data_root, output_root, db_path = _seed_ready_inputs(tmp_path / status)
        _set_degraded_non_eod_freshness(output_root)
        _set_candidate_credit_stale_without_warning(output_root)
        freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
        freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
        for source in freshness["source_statuses"]:
            if source["source_id"] == "credit_transactions":
                source["freshness_status"] = status
                break
        _write_json(freshness_path, freshness)

        result = inspect_dependency(
            data_root=data_root,
            output_root=output_root,
            db_path=db_path,
            observed_at=OBSERVED,
        )

        assert result["status"] == "blocked"
        assert result["ready"] is False


def _historical_degraded_payload(target: str) -> dict[str, object]:
    """以正式 9/15--9/17 payload 的欄位和值建立可攜式 projection fixture。"""

    return {
        "status": "degraded",
        "errors": [],
        "warnings": [
            "monthly_revenue_expected_period_not_available",
            "quarterly_statement_expected_period_not_available",
            "source_freshness_degraded:fundamental.current_monthly_observations",
            "source_freshness_degraded:fundamental.current_statement_observations",
            "source_freshness_degraded:institutional_flows",
            "source_freshness_degraded:credit_transactions",
        ],
        "source_statuses": [
            {
                "source_id": source_id,
                "freshness_status": "current",
                "actual_period": target,
                "expected_period": target,
            }
            for source_id in (
                "twse.daily_prices.raw",
                "tpex.daily_prices.raw",
                "sqlite.daily_prices",
            )
        ]
        + [
            {
                "source_id": "fundamental.monthly_revenues",
                "freshness_status": "stale",
                "actual_period": "2026-06",
                "expected_period": "2026-08",
                "candidate_only": True,
            },
            {
                "source_id": "fundamental.quarterly_statements",
                "freshness_status": "stale",
                "actual_period": "2024-Q1",
                "expected_period": "2026-Q2",
                "candidate_only": True,
            },
            {
                "source_id": "fundamental.current_monthly_observations",
                "freshness_status": "partial",
                "actual_period": "2026-08",
                "expected_period": "2026-08",
            },
            {
                "source_id": "fundamental.current_statement_observations",
                "freshness_status": "partial",
                "actual_period": "2026-Q2",
                "expected_period": "2026-Q2",
            },
            {
                "source_id": "institutional_flows",
                "freshness_status": "stale",
                "actual_period": "20260908",
                "expected_period": target,
            },
            {
                "source_id": "credit_transactions",
                "freshness_status": "stale",
                "actual_period": "20260908",
                "expected_period": target,
                "candidate_only": True,
                "frequency": "daily candidate source",
                "downstream": ["candidate research only"],
                "update_entry": "UpdateService.update_phase3c_candidate_range",
                "reason": "latest candidate observation is behind the expected official session",
            },
            {
                "source_id": "tdcc_shareholding",
                "freshness_status": "unknown",
                "reason": "official rows ingested; per-market coverage and availability must be checked before declaring complete",
                "actual_period": "20260904",
                "expected_period": None,
                "candidate_only": False,
                "available_at": None,
                "coverage": {"table_exists": True, "db_row_count": 4047},
            },
            {
                "source_id": "fundamental.statement_availability_map",
                "freshness_status": "unknown",
                "reason": "file_missing",
                "actual_period": None,
                "expected_period": None,
                "candidate_only": False,
                "available_at": None,
                "coverage": {"file_exists": False, "bytes": None},
            },
        ],
    }


def _today_candidate_projection_payload() -> dict[str, object]:
    """以 2026-09-22 的 candidate row contract 建立隔離 projection fixture。"""

    payload = _historical_degraded_payload("20260922")
    payload["warnings"] = [
        "monthly_revenue_expected_period_not_available",
        "quarterly_statement_expected_period_not_available",
    ]
    source_statuses = payload["source_statuses"]
    assert isinstance(source_statuses, list)
    source_statuses[:] = [
        source
        for source in source_statuses
        if source["source_id"]
        not in {
            "institutional_flows",
            "credit_transactions",
            "fundamental.current_monthly_observations",
            "fundamental.current_statement_observations",
        }
    ]
    source_statuses.append(
        {
            "source_id": "credit_transactions",
            "authority": "TWSE + TPEx margin official endpoints",
            "frequency": "daily candidate source",
            "actual_period": "20260921",
            "published_at": None,
            "available_at": "2026-09-21T19:19:14.671044+00:00",
            "expected_period": "20260922",
            "coverage": {
                "candidate_db_exists": True,
                "table_exists": True,
                "db_row_count": 126,
                "latest_session_row_count": 81,
                "expected_source_versions": [
                    "twse-official-MI_MARGN",
                    "tpex-official-margin_bal",
                ],
                "observed_source_versions": [
                    "twse-official-MI_MARGN",
                    "tpex-official-margin_bal",
                ],
                "source_version_coverage_complete": True,
            },
            "missing_periods": ["20260922"],
            "duplicate_key_count": 0,
            "freshness_status": "stale",
            "reason": "latest candidate observation is behind the expected official session",
            "update_entry": "UpdateService.update_phase3c_candidate_range",
            "scheduled_task": "baldr-data-update-quick-daily",
            "owner": "Data Engineering + P0 source owners",
            "downstream": ["candidate research only"],
            "candidate_only": True,
        }
    )
    return payload


def _today_credit_projection_row(payload: dict[str, object]) -> dict[str, object]:
    source_statuses = payload["source_statuses"]
    assert isinstance(source_statuses, list)
    row = next(item for item in source_statuses if item["source_id"] == "credit_transactions")
    assert isinstance(row, dict)
    return row


def test_projection_accepts_today_credit_contract_and_preserves_diagnostic() -> None:
    payload = _today_candidate_projection_payload()
    credit_row = _today_credit_projection_row(payload)

    projection, blockers, _ignored = _paper_eod_freshness_projection(
        payload,
        target=date(2026, 9, 22),
    )

    assert blockers == []
    assert projection["status"] == "degraded_non_eod_only"
    excluded = cast(dict[str, dict[str, object]], projection["not_required_for_paper_eod"])
    credit = excluded["credit_transactions"]
    assert credit["freshness_status"] == "stale"
    assert credit["candidate_only"] is True
    assert credit["reason"] == credit_row["reason"]
    assert credit["source_diagnostic"] == credit_row


def test_projection_blocks_credit_frequency_mismatch_and_required_source_partial() -> None:
    payload = _today_candidate_projection_payload()
    _today_credit_projection_row(payload)["frequency"] = "daily official session"
    source_statuses = payload["source_statuses"]
    assert isinstance(source_statuses, list)
    required = next(item for item in source_statuses if item["source_id"] == "sqlite.daily_prices")
    assert isinstance(required, dict)
    required["freshness_status"] = "partial"

    projection, blockers, _ignored = _paper_eod_freshness_projection(
        payload,
        target=date(2026, 9, 22),
    )

    assert projection["status"] == "blocked"
    assert "freshness_lane_noncurrent_source_unattributed:credit_transactions:stale" in blockers
    assert "freshness_required_source_not_current:sqlite.daily_prices:partial" in blockers


def test_historical_payload_shape_fixture_classifies_two_non_eod_unknown_sources() -> None:
    for target_key in ("20260915", "20260916", "20260917"):
        target = datetime.strptime(target_key, "%Y%m%d").date()
        payload = _historical_degraded_payload(target_key)
        projection, blockers, _ = _paper_eod_freshness_projection(payload, target=target)

        assert blockers == []
        assert projection["status"] == "degraded_non_eod_only"
        excluded = cast(dict[str, dict[str, object]], projection["not_required_for_paper_eod"])
        assert set(excluded) == {
            "credit_transactions",
            "tdcc_shareholding",
            "fundamental.statement_availability_map",
        }
        tdcc_diagnostic = cast(
            dict[str, object], excluded["tdcc_shareholding"]["source_diagnostic"]
        )
        statement_diagnostic = cast(
            dict[str, object],
            excluded["fundamental.statement_availability_map"]["source_diagnostic"],
        )
        assert tdcc_diagnostic["freshness_status"] == "unknown"
        assert statement_diagnostic["reason"] == "file_missing"


def test_dependency_gate_blocks_stale_receipt_and_missing_target_source(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    quick_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    payload = json.loads(quick_path.read_text(encoding="utf-8"))
    payload["end_date"] = "2026-09-07"
    quick_path.write_text(json.dumps(payload), encoding="utf-8")
    (data_root / "daily_price_tpex" / f"{TARGET}.csv").unlink()

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "blocked"
    assert result["ready"] is False
    blockers = cast(list[object], result["blockers"])
    assert "quick_update_receipt_data_date_not_target" in blockers  # type: ignore[operator]
    assert any(str(item).startswith("source_file_missing:") for item in blockers)


def test_dependency_gate_rejects_future_receipt_dates(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    quick_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    payload = json.loads(quick_path.read_text(encoding="utf-8"))
    payload["end_date"] = "2026-09-09"
    payload["checked_at"] = "2026-09-09T01:00:00+08:00"
    quick_path.write_text(json.dumps(payload), encoding="utf-8")
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"
    freshness = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness["checks"]["daily_prices_latest_date"] = "20260909"
    freshness["checks"]["data_update_quick_checked_date"] = "2026-09-09"
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["status"] == "blocked"
    assert "quick_update_receipt_data_date_not_target" in result["blockers"]  # type: ignore[operator]
    assert "quick_update_receipt_checked_date_not_target" in result["blockers"]  # type: ignore[operator]
    assert "freshness_receipt_daily_prices_not_target" in result["blockers"]  # type: ignore[operator]
    assert "freshness_receipt_update_date_not_target" in result["blockers"]  # type: ignore[operator]


def test_dependency_gate_rejects_future_checked_at_even_when_dates_match(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    quick_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    payload = json.loads(quick_path.read_text(encoding="utf-8"))
    payload["checked_at"] = "2026-09-08T22:00:00+08:00"
    quick_path.write_text(json.dumps(payload), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    assert result["ready"] is False
    assert "quick_update_receipt_checked_at_after_observed" in result["blockers"]  # type: ignore[operator]


def test_dependency_gate_rejects_naive_or_malformed_receipt_timestamps(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    quick_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    freshness_path = output_root / "scheduled" / "data_freshness" / "latest_status.json"

    quick_payload = json.loads(quick_path.read_text(encoding="utf-8"))
    quick_payload["checked_at"] = "2026-09-08T20:00:00"
    quick_path.write_text(json.dumps(quick_payload), encoding="utf-8")
    freshness_payload = json.loads(freshness_path.read_text(encoding="utf-8"))
    freshness_payload["checked_at"] = "not-a-timestamp"
    freshness_path.write_text(json.dumps(freshness_payload), encoding="utf-8")

    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )

    blockers = cast(list[object], result["blockers"])
    assert "quick_update_receipt_checked_at_invalid:naive" in blockers  # type: ignore[operator]
    assert "freshness_receipt_checked_at_invalid:malformed" in blockers  # type: ignore[operator]


def test_dependency_gate_rejects_replaced_or_empty_csv_and_stale_db_values(tmp_path: Path) -> None:
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    twse_path = data_root / "daily_price" / f"{TARGET}.csv"
    twse_path.write_text("證券代號,開盤價\n2330,999.0\n", encoding="utf-8")

    replaced = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )
    assert any(
        str(item).startswith("source_db_readback_mismatch:twse:2330")
        for item in cast(list[object], replaced["blockers"])
    )

    twse_path.write_text("證券代號,開盤價\n", encoding="utf-8")
    empty = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )
    assert any(
        str(item).startswith("source_rows_empty_or_open_missing:")
        for item in cast(list[object], empty["blockers"])
    )

    twse_path.write_text("證券代號,開盤價\n2330,100.0\n", encoding="utf-8")
    connection = sqlite3.connect(db_path)
    connection.execute('UPDATE daily_prices SET "開盤價"=? WHERE "證券代號"=?', (101.0, "2330"))
    connection.commit()
    connection.close()
    stale_db = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        observed_at=OBSERVED,
    )
    assert any(
        str(item).startswith("source_db_readback_mismatch:twse:2330")
        for item in cast(list[object], stale_db["blockers"])
    )


def test_dependency_gate_treats_weekend_as_calendar_delegation(tmp_path: Path) -> None:
    result = inspect_dependency(
        data_root=tmp_path / "missing-data",
        output_root=tmp_path / "missing-output",
        db_path=tmp_path / "missing.db",
        observed_at=datetime(2026, 9, 12, 1, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "not_trading_day"
    assert result["ready"] is True
    assert result["reason"] == "taipei_weekend"


def test_dependency_gate_classifies_verified_weekday_holiday_before_upstream_failure(
    tmp_path: Path,
) -> None:
    observed = datetime(2026, 9, 25, 13, 0, tzinfo=timezone.utc)
    calendar_root = tmp_path / "calendar"
    cache_path = _write_calendar_cache(
        calendar_root,
        year=2026,
        closed_date=date(2026, 9, 25),
        captured_at=observed - timedelta(hours=1),
    )
    data_root, output_root, db_path = _seed_ready_inputs(tmp_path)
    quick_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    quick_payload = json.loads(quick_path.read_text(encoding="utf-8"))
    quick_payload["status"] = "failed"
    quick_payload["errors"] = ["upstream technical failure retained"]
    quick_path.write_text(json.dumps(quick_payload), encoding="utf-8")

    # quick 仍是 failed，但 verified exact closed-day 只讓 Paper adapter no-op；
    # gate 將 upstream status/hash 保留在 receipt，不能把它報成 passed。
    result = inspect_dependency(
        data_root=data_root,
        output_root=output_root,
        db_path=db_path,
        calendar_cache_path=calendar_root,
        observed_at=observed,
    )

    assert result["status"] == "not_trading_day"
    assert result["ready"] is True
    assert result["reason"] == "twse_holiday_schedule_cache_closed"
    assert result["adapter_noop"] is True
    assert result["quick_update_status"] == "failed"
    assert result["quick_update_error_count"] == 1
    assert result["upstream_quick_update_status_preserved"] is True
    assert result["blockers"] == []
    evidence = cast(dict[str, object], result["calendar_evidence"])
    assert evidence["target_date"] == "2026-09-25"
    assert evidence["is_trading_day"] is False
    assert evidence["reason_code"] == "twse_holiday_schedule_cache_closed"
    assert evidence["path"] == str(cache_path.resolve())
    assert evidence["mode"] == "hash_bound_official_calendar_cache"
    assert evidence["available_at"] == "2026-09-25T12:00:00+00:00"


def test_dependency_gate_keeps_open_or_unverified_calendar_on_original_blockers(
    tmp_path: Path,
) -> None:
    observed = OBSERVED
    for mode in ("open", "missing", "expired", "tampered"):
        case_root = tmp_path / mode
        data_root, output_root, db_path = _seed_ready_inputs(case_root)
        quick_path = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
        quick_payload = json.loads(quick_path.read_text(encoding="utf-8"))
        quick_payload["status"] = "failed"
        quick_path.write_text(json.dumps(quick_payload), encoding="utf-8")

        calendar_root = case_root / "calendar"
        if mode != "missing":
            cache_path = _write_calendar_cache(
                calendar_root,
                year=2026,
                closed_date=date(2026, 9, 1),
                captured_at=observed - timedelta(hours=1),
                max_age=timedelta(days=1) if mode == "expired" else timedelta(days=7),
            )
            if mode == "tampered":
                cache_path.write_text("{}", encoding="utf-8")

        result = inspect_dependency(
            data_root=data_root,
            output_root=output_root,
            db_path=db_path,
            calendar_cache_path=calendar_root,
            observed_at=observed,
        )

        assert result["status"] == "blocked", mode
        assert result["ready"] is False, mode
        assert "quick_update_status_not_success:failed" in result["blockers"], mode  # type: ignore[operator]
        assert "calendar_evidence" not in result, mode
