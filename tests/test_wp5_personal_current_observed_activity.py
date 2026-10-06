from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3

import pytest

from data_module import wp5_daily_chain_preflight as preflight
from data_module.wp5_official_daily_capture_validator import (
    TPEX_FIELDS,
    TWSE_FIELDS,
)


DECISION_DATE = date(2026, 9, 29)
OBSERVED_AT = datetime(2026, 9, 29, 15, 30, tzinfo=timezone.utc)
SCHEMA_SHA256 = "a" * 64


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _build_seed(tmp_path: Path) -> tuple[preflight.PreflightConfig, dict[str, str]]:
    repo = tmp_path / "repo"
    qa_parent = repo / "output" / "qa"
    qa_root = qa_parent / "seed"
    data_root = qa_root / "data"
    output_root = qa_root / "output"
    technical_root = data_root / "output"
    db_path = data_root / "sqlite" / "twstock.db"
    technical_root.mkdir(parents=True)
    output_root.mkdir(parents=True)
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO smoke(value) VALUES ('seed')")
    db_hash = _sha256_file(db_path)

    snapshot_dir = qa_parent / "snapshot" / "formal_source_snapshot_v2"
    snapshot_db = snapshot_dir / "twstock.db"
    snapshot_db.parent.mkdir(parents=True)
    shutil.copyfile(db_path, snapshot_db)
    snapshot_receipt = snapshot_dir / "snapshot_receipt.json"
    _write_json(
        snapshot_receipt,
        {
            "schema_version": preflight.UPSTREAM_SNAPSHOT_SCHEMA,
            "completed_at": "2026-09-29T08:20:43.348100+00:00",
            "snapshot_path": str(snapshot_db),
            "snapshot_sha256": db_hash,
            "snapshot_integrity_check": ["ok"],
            "snapshot_journal_mode": "delete",
            "snapshot_data_version_stable": True,
            "snapshot_schema": {"schema_sha256": SCHEMA_SHA256},
        },
    )
    snapshot_receipt_hash = _sha256_file(snapshot_receipt)

    bootstrap_receipt = qa_root / "bootstrap_receipt.json"
    _write_json(
        bootstrap_receipt,
        {
            "schema_version": preflight.BOOTSTRAP_SCHEMA,
            "status": "database_seed_created",
            "created_at_utc": "2026-09-29T08:08:21.362726+00:00",
            "ready_for_daily_pipeline": False,
            "daily_chain_preflight_complete": False,
            "official_point_in_time_eligibility": "not_established",
            "research_use_only": True,
            "paths": {
                "qa_root": str(qa_root),
                "data_root": str(data_root),
                "output_root": str(output_root),
                "technical_output_root": str(technical_root),
                "working_db": str(db_path),
                "source_snapshot_db": str(snapshot_db),
                "source_snapshot_receipt": str(snapshot_receipt),
            },
            "lineage": {
                "copy_source_sha256": db_hash,
                "working_copy_sha256": db_hash,
                "snapshot_sha256": db_hash,
                "schema_sha256": SCHEMA_SHA256,
                "upstream_receipt_sha256": snapshot_receipt_hash,
            },
            "destination": {
                "copy": {
                    "destination_sha256_readback": db_hash,
                    "source_sha256_during_copy": db_hash,
                }
            },
        },
    )
    config = preflight.PreflightConfig(
        qa_root=qa_root,
        decision_date=DECISION_DATE,
        observed_at=OBSERVED_AT,
        expected_bootstrap_receipt_sha256=_sha256_file(bootstrap_receipt),
        expected_working_db_sha256=db_hash,
        expected_snapshot_receipt_sha256=snapshot_receipt_hash,
        skip_candidate_update=True,
        repo_root=repo,
    )
    env = {
        "PROFILE": "prod",
        "DATA_ROOT": str(data_root),
        "OUTPUT_ROOT": str(output_root),
        "DB_PATH": str(db_path),
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(output_root),
    }
    return config, env


def _build_annual_cache(
    config: preflight.PreflightConfig,
    *,
    is_open: bool = True,
    captured_at: datetime = OBSERVED_AT - timedelta(hours=1),
) -> Path:
    from data_module.official_trading_calendar_cache import (
        build_twse_calendar_cache,
        write_twse_calendar_cache,
    )

    cache_root = config.repo_root / "output" / "qa" / "official-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "Name": "中華民國開國紀念日",
            "Date": "1150101",
            "Weekday": "四",
            "Description": "依規定放假1日。",
        }
    ]
    if not is_open:
        rows.append(
            {
                "Name": "測試休市",
                "Date": "1150929",
                "Weekday": "二",
                "Description": "依規定休市1日。",
            }
        )
    raw = _json_bytes(rows)
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
    )
    cache_mode = "open" if is_open else "closed"
    path = cache_root / (
        f"twse_holiday_schedule_2026_{cache_mode}_{captured_at:%Y%m%dT%H%M%S}.json"
    )
    write_twse_calendar_cache(path, cache, allowed_root=cache_root.parent)
    return path


def _build_closure_event(
    config: preflight.PreflightConfig,
    *,
    closure_date: date,
) -> Path:
    from data_module.official_trading_calendar_cache import (
        build_twse_temporary_closure_cache,
        write_twse_temporary_closure_cache,
    )

    cache_root = config.repo_root / "output" / "qa" / "official-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    captured_at = OBSERVED_AT - timedelta(minutes=30)
    url = "https://www.twse.com.tw/zh/announcement/announcement/detail.html?id=qa-test"
    roc_date = f"{closure_date.year - 1911:03d}年{closure_date.month}月{closure_date.day}日"
    raw = f"臺灣證券交易所集中交易市場於{roc_date}全日休市一天，因颱風影響。".encode()
    cache = build_twse_temporary_closure_cache(
        closure_date=closure_date,
        raw_response=raw,
        source_url=url,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_url=url,
    )
    path = cache_root / f"twse_temporary_closure_{closure_date:%Y%m%d}.json"
    write_twse_temporary_closure_cache(path, cache, allowed_root=cache_root.parent)
    return path


def _twse_row(code: str, shares: str, close: str = "2475.00") -> list[str]:
    return [
        code,
        "測試證券",
        shares,
        "1",
        "100000",
        "2470.00",
        "2480.00",
        "2460.00",
        close,
        "",
        "0.00",
        "2470.00",
        "1",
        "2480.00",
        "1",
        "10.00",
    ]


def _tpex_row(code: str, shares: str, close: str = "125.50") -> list[str]:
    return [
        code,
        "測試上櫃",
        close,
        "0.50",
        "125.00",
        "126.00",
        "124.50",
        "125.20",
        shares,
        "100000",
        "10",
        "125.00",
        "1",
        "125.50",
        "1",
        "1000000",
        "125.50",
        "138.00",
        "113.00",
    ]


def _build_capture(
    config: preflight.PreflightConfig,
    *,
    mutate: object | None = None,
) -> tuple[Path, str, str]:
    capture_dir = config.repo_root / "output" / "qa" / "synthetic_daily_capture"
    capture_dir.mkdir(parents=True)
    twse = {
        "date": "20260929",
        "stat": "OK",
        "type": "ALL",
        "tables": [{"fields": [], "data": []} for _ in range(8)]
        + [
            {
                "fields": list(TWSE_FIELDS),
                "data": [
                    _twse_row("2330", "1000"),
                    _twse_row("2317", "2000"),
                ],
            }
        ],
    }
    tpex = {
        "date": "20260929",
        "stat": "ok",
        "tables": [
            {
                "fields": list(TPEX_FIELDS),
                "data": [_tpex_row("6488", "3000"), _tpex_row("5347", "4000")],
                "totalCount": 2,
            }
        ],
    }
    if mutate is not None:
        mutate(twse, tpex)  # type: ignore[operator]

    specs = (
        (
            "twse_mi_index",
            "twse_mi_index_20260929.json",
            "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260929&type=ALL&response=json",
            twse,
            "2026-09-29T15:18:27.1665879+00:00",
            "2026-09-29T15:18:27.8257766+00:00",
        ),
        (
            "tpex_daily_quotes",
            "tpex_daily_quotes_20260929.json",
            "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date=2026%2F09%2F29&id=&response=json",
            tpex,
            "2026-09-29T15:18:27.8800087+00:00",
            "2026-09-29T15:18:31.0739265+00:00",
        ),
    )
    captures: list[dict[str, object]] = []
    raw_files: list[dict[str, object]] = []
    for name, filename, url, payload, capture_start, capture_end in specs:
        raw = _json_bytes(payload)
        (capture_dir / filename).write_bytes(raw)
        digest = _sha256_bytes(raw)
        captures.append(
            {
                "name": name,
                "request_url": url,
                "final_url": url,
                "capture_start_utc": capture_start,
                "capture_end_utc": capture_end,
                "http_status": 200,
                "content_type": "application/json; charset=UTF-8",
                "body_file": filename,
                "body_bytes": len(raw),
                "body_sha256": digest,
                "readback_bytes": len(raw),
                "readback_sha256": digest,
                "readback_verified": True,
                "result": "captured_verified",
            }
        )
        raw_files.append(
            {
                "name": name,
                "file": filename,
                "http_status": 200,
                "bytes": len(raw),
                "sha256": digest,
                "readback_bytes": len(raw),
                "readback_sha256": digest,
                "readback_verified": True,
            }
        )
    receipt = {
        "schema_version": 1,
        "run_id": "synthetic-20260929-daily-capture",
        "run_status": "success_raw_capture_readback_verified",
        "capture_directory": str(capture_dir.resolve()),
        "started_at_utc": "2026-09-29T15:18:27.0000000+00:00",
        "finished_at_utc": "2026-09-29T15:18:31.2000000+00:00",
        "formal_pit": False,
        "captures": captures,
    }
    manifest = {
        "schema_version": 1,
        "run_id": receipt["run_id"],
        "run_status": receipt["run_status"],
        "capture_directory": str(capture_dir.resolve()),
        "receipt_file": "capture_receipt.json",
        "raw_files": raw_files,
    }
    receipt_path = capture_dir / "capture_receipt.json"
    manifest_path = capture_dir / "capture_manifest.json"
    receipt_path.write_bytes(_json_bytes(receipt))
    manifest_path.write_bytes(_json_bytes(manifest))
    return capture_dir, _sha256_file(receipt_path), _sha256_file(manifest_path)


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "_utc_now", lambda: OBSERVED_AT)


def _ready_inputs(
    tmp_path: Path,
    *,
    is_open: bool = True,
    closure_date: date | None = None,
    mutate_capture: object | None = None,
) -> tuple[preflight.PreflightConfig, dict[str, str], dict[str, object]]:
    config, env = _build_seed(tmp_path)
    calendar_path = _build_annual_cache(config, is_open=is_open)
    capture_dir, receipt_sha, manifest_sha = _build_capture(
        config, mutate=mutate_capture
    )
    changed = preflight.PreflightConfig(
        **{
            **config.__dict__,
            "calendar_cache_path": calendar_path,
            "temporary_closure_path": (
                None
                if closure_date is None
                else _build_closure_event(config, closure_date=closure_date)
            ),
        }
    )
    inputs: dict[str, object] = {
        "capture_directory": capture_dir,
        "expected_capture_receipt_sha256": receipt_sha,
        "expected_capture_manifest_sha256": manifest_sha,
        "expected_calendar_cache_sha256": _sha256_file(calendar_path),
    }
    return changed, env, inputs


def _qualify(
    config: preflight.PreflightConfig,
    env: dict[str, str],
    inputs: dict[str, object],
) -> dict[str, object]:
    return preflight.run_personal_current_observed_activity(
        config,
        **inputs,  # type: ignore[arg-type]
        environ=env,
    )


def _update_capture_metadata_pin(
    inputs: dict[str, object],
    *,
    mutate: object,
) -> None:
    capture_dir = Path(inputs["capture_directory"])  # type: ignore[arg-type]
    receipt_path = capture_dir / "capture_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    mutate(receipt)  # type: ignore[operator]
    receipt_path.write_bytes(_json_bytes(receipt))
    inputs["expected_capture_receipt_sha256"] = _sha256_file(receipt_path)


def _move_twse_body_read_to_next_taipei_date(receipt: dict[str, object]) -> None:
    captures = receipt["captures"]  # type: ignore[index]
    captures[0]["capture_end_utc"] = "2026-09-29T16:18:27.8257766+00:00"
    receipt["finished_at_utc"] = "2026-09-29T16:18:31.2000000+00:00"


def test_missing_closure_or_other_date_event_allows_only_personal_activity_scope(
    tmp_path: Path,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    before = sorted(
        path.relative_to(config.qa_root).as_posix()
        for path in config.qa_root.rglob("*")
        if path.is_file()
    )
    db_path = config.qa_root / "data" / "sqlite" / "twstock.db"
    db_hash = _sha256_file(db_path)

    result = _qualify(config, env, inputs)
    strict = preflight.run_read_only_preflight(config, environ=env)

    assert result["status"] == "eligible_personal_research"
    assert result["mode"] == "personal_current_observed_activity"
    assert result["research_only"] is True
    assert result["formal_pit"] is False
    assert result["official_published_at"] == "unknown"
    assert result["official_published_at_utc"] == "unknown"
    assert result["temporary_closure_negative_coverage"] is False
    assert result["runner_executed"] is False
    assert result["observed_at_utc"] == "2026-09-29T15:18:31.0739265+00:00"
    assert result["decision_at_utc"] == "2026-09-29T15:30:00+00:00"
    assert result["cutoff_utc"] == result["decision_at_utc"]
    assert result["day_execution_readiness"] == strict["day_execution_readiness"]
    assert result["day_execution_readiness"]["status"] == "blocked"  # type: ignore[index]
    assert result["temporary_closure_evidence"]["status"] == "unknown"  # type: ignore[index]
    assert result["official_same_day_market_activity"]["closure_gate_passed"] is False  # type: ignore[index]
    capture_pins = result["capture_pins"]
    assert capture_pins["receipt_sha256"] == inputs["expected_capture_receipt_sha256"]  # type: ignore[index]
    assert capture_pins["manifest_sha256"] == inputs["expected_capture_manifest_sha256"]  # type: ignore[index]
    assert set(capture_pins["raw_sha256_by_market"]) == {  # type: ignore[index]
        "twse_mi_index",
        "tpex_daily_quotes",
    }
    assert "ready" not in result and "runner_ready" not in result
    assert _sha256_file(db_path) == db_hash
    after = sorted(
        path.relative_to(config.qa_root).as_posix()
        for path in config.qa_root.rglob("*")
        if path.is_file()
    )
    assert after == before
    assert not any(
        Path(str(db_path) + suffix).exists()
        for suffix in preflight.SQLITE_SIDECAR_SUFFIXES
    )

    other_config, other_env, other_inputs = _ready_inputs(
        tmp_path / "other", closure_date=date(2026, 9, 30)
    )
    other = _qualify(other_config, other_env, other_inputs)
    assert other["status"] == "eligible_personal_research"
    assert other["temporary_closure_evidence"]["status"] == "verified_other_date_event"  # type: ignore[index]
    assert other["temporary_closure_negative_coverage"] is False


def test_valid_same_day_closure_event_blocks_personal_activity(
    tmp_path: Path,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path, closure_date=DECISION_DATE)

    result = _qualify(config, env, inputs)

    assert result["status"] == "blocked"
    assert result["temporary_closure_evidence"]["decision_date_closure_event"] is True  # type: ignore[index]
    assert result["temporary_closure_negative_coverage"] is False
    assert any(
        item["code"] == "verified_temporary_closure_event_on_decision_date"
        for item in result["blockers"]  # type: ignore[union-attr]
    )
    assert result["day_execution_readiness"]["status"] == "blocked"  # type: ignore[index]


@pytest.mark.parametrize(
    ("is_open", "captured_at", "expected_code"),
    [
        (False, OBSERVED_AT - timedelta(hours=1), "annual_calendar_not_planned_open"),
        (
            True,
            OBSERVED_AT - timedelta(days=8),
            "annual_calendar_not_verified",
        ),
    ],
    ids=["annual-closed", "annual-expired"],
)
def test_closed_or_expired_annual_calendar_blocks_personal_activity(
    tmp_path: Path,
    is_open: bool,
    captured_at: datetime,
    expected_code: str,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    calendar_path = _build_annual_cache(
        config,
        is_open=is_open,
        captured_at=captured_at,
    )
    changed = preflight.PreflightConfig(
        **{**config.__dict__, "calendar_cache_path": calendar_path}
    )
    inputs["expected_calendar_cache_sha256"] = _sha256_file(calendar_path)

    result = _qualify(changed, env, inputs)

    assert result["status"] == "blocked"
    assert expected_code in {item["code"] for item in result["blockers"]}  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("mutate_capture", "expected_code"),
    [
        (
            lambda _twse, tpex: tpex.update({"date": "20260928"}),
            "tpex_date_mismatch",
        ),
        (
            lambda twse, _tpex: twse["tables"][8]["data"].clear(),
            "twse_mi_index_empty_rows",
        ),
        (
            lambda _twse, tpex: tpex["tables"][0]["data"][0].__setitem__(8, "0"),
            "tpex_daily_quotes_required_symbol_no_positive_volume",
        ),
    ],
    ids=["wrong-day", "empty-market", "required-volume-zero"],
)
def test_capture_payload_failures_block_personal_activity(
    tmp_path: Path,
    mutate_capture: object,
    expected_code: str,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path, mutate_capture=mutate_capture)

    result = _qualify(config, env, inputs)

    assert result["status"] == "blocked"
    capture = result["official_same_day_market_activity"]
    assert expected_code in {item["code"] for item in capture["blockers"]}  # type: ignore[index]


@pytest.mark.parametrize("missing", ["receipt", "manifest", "calendar"], ids=["receipt-pin", "manifest-pin", "calendar-pin"])
def test_missing_caller_pin_blocks_personal_activity(
    tmp_path: Path,
    missing: str,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    key = {
        "receipt": "expected_capture_receipt_sha256",
        "manifest": "expected_capture_manifest_sha256",
        "calendar": "expected_calendar_cache_sha256",
    }[missing]
    inputs[key] = None

    result = _qualify(config, env, inputs)

    assert result["status"] == "blocked"


@pytest.mark.parametrize(
    ("mutate_receipt", "expected_code"),
    [
        (
            lambda receipt: receipt["captures"][0].update({"http_status": 503}),
            "twse_mi_index_http_status_not_200",
        ),
        (
            lambda receipt: receipt["captures"].pop(),
            "receipt_capture_set_incomplete",
        ),
        (
            _move_twse_body_read_to_next_taipei_date,
            "twse_mi_index_after_cutoff",
        ),
    ],
    ids=["http-status", "missing-tpex-market", "cross-taipei-date-after-cutoff"],
)
def test_http_missing_market_and_cross_date_capture_fail_closed(
    tmp_path: Path,
    mutate_receipt: object,
    expected_code: str,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    _update_capture_metadata_pin(inputs, mutate=mutate_receipt)

    result = _qualify(config, env, inputs)

    assert result["status"] == "blocked"
    capture = result["official_same_day_market_activity"]
    assert expected_code in {item["code"] for item in capture["blockers"]}  # type: ignore[index]


def test_malformed_schema_and_mismatched_capture_pin_fail_closed(
    tmp_path: Path,
) -> None:
    config, env, inputs = _ready_inputs(
        tmp_path,
        mutate_capture=lambda twse, _tpex: twse["tables"][8]["fields"].__setitem__(
            0, "錯誤欄位"
        ),
    )
    invalid_schema = _qualify(config, env, inputs)
    assert invalid_schema["status"] == "blocked"
    assert "twse_daily_fields_mismatch" in {
        item["code"]
        for item in invalid_schema["official_same_day_market_activity"]["blockers"]  # type: ignore[index]
    }

    config2, env2, inputs2 = _ready_inputs(tmp_path / "wrong-pin")
    inputs2["expected_capture_manifest_sha256"] = "0" * 64
    wrong_pin = _qualify(config2, env2, inputs2)
    assert wrong_pin["status"] == "blocked"
    assert "manifest_sha256_mismatch" in {
        item["code"]
        for item in wrong_pin["official_same_day_market_activity"]["blockers"]  # type: ignore[index]
    }


def test_mismatched_annual_calendar_pin_blocks_personal_activity(
    tmp_path: Path,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    inputs["expected_calendar_cache_sha256"] = "0" * 64

    result = _qualify(config, env, inputs)

    assert result["status"] == "blocked"
    assert "annual_calendar_sha256_pin_mismatch" in {
        item["code"] for item in result["blockers"]  # type: ignore[union-attr]
    }


def test_hardlinked_annual_calendar_file_blocks_personal_activity(
    tmp_path: Path,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    calendar_path = config.calendar_cache_path
    alias = tmp_path / "second-link-to-calendar.json"
    try:
        os.link(calendar_path, alias)
    except OSError as error:
        pytest.skip(f"目前檔案系統不支援 hardlink 測試：{error}")

    result = _qualify(config, env, inputs)

    assert result["status"] == "blocked"
    assert any(
        "annual_calendar_cache_link_count_not_one:2" in item["detail"]
        for item in result["blockers"]  # type: ignore[union-attr]
    )


def test_capture_after_caller_cutoff_blocks_personal_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    earlier_cutoff = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(preflight, "_utc_now", lambda: earlier_cutoff)
    changed = preflight.PreflightConfig(
        **{**config.__dict__, "observed_at": earlier_cutoff}
    )

    result = _qualify(changed, env, inputs)

    assert result["status"] == "blocked"
    capture = result["official_same_day_market_activity"]
    assert "twse_mi_index_after_cutoff" in {
        item["code"] for item in capture["blockers"]  # type: ignore[index]
    }


@pytest.mark.parametrize(
    ("observed_at", "expected_code"),
    [
        (OBSERVED_AT + timedelta(minutes=1), "observed_at_is_in_the_future"),
        (OBSERVED_AT - timedelta(minutes=6), "observed_at_is_stale"),
    ],
    ids=["future-cutoff", "stale-cutoff"],
)
def test_future_or_stale_observed_cutoff_blocks_personal_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observed_at: datetime,
    expected_code: str,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    monkeypatch.setattr(preflight, "_utc_now", lambda: OBSERVED_AT)
    changed = preflight.PreflightConfig(
        **{**config.__dict__, "observed_at": observed_at}
    )

    result = _qualify(changed, env, inputs)

    assert result["status"] == "blocked"
    assert expected_code in {item["code"] for item in result["blockers"]}  # type: ignore[union-attr]
    assert result["official_same_day_market_activity"]["status"] == "blocked"  # type: ignore[index]


def test_untrusted_published_at_metadata_blocks_personal_activity(
    tmp_path: Path,
) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    receipt_path = Path(inputs["capture_directory"]) / "capture_receipt.json"  # type: ignore[arg-type]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["captures"][0]["published_at_utc"] = "2026-09-29T15:00:00Z"
    receipt_path.write_bytes(_json_bytes(receipt))
    inputs["expected_capture_receipt_sha256"] = _sha256_file(receipt_path)

    result = _qualify(config, env, inputs)

    assert result["status"] == "blocked"
    assert "capture_publication_time_claim_rejected" in {
        item["code"]
        for item in result["official_same_day_market_activity"]["blockers"]  # type: ignore[index]
    }


def test_raw_body_hash_mismatch_blocks_personal_activity(tmp_path: Path) -> None:
    config, env, inputs = _ready_inputs(tmp_path)
    raw_path = Path(inputs["capture_directory"]) / "twse_mi_index_20260929.json"  # type: ignore[arg-type]
    raw_path.write_bytes(raw_path.read_bytes() + b" ")

    result = _qualify(config, env, inputs)

    assert result["status"] == "blocked"
    assert "twse_mi_index_raw_readback_mismatch" in {
        item["code"]
        for item in result["official_same_day_market_activity"]["blockers"]  # type: ignore[index]
    }


def test_cli_personal_mode_is_explicit_and_stdout_json_is_ascii(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import qa_wp5_daily_chain_preflight as cli

    config, env, inputs = _ready_inputs(tmp_path)
    monkeypatch.setattr(cli, "REPO_ROOT", config.repo_root)
    monkeypatch.setattr(os, "environ", env)
    argv = [
        "--mode",
        "personal_current_observed_activity",
        "--qa-root",
        str(config.qa_root),
        "--decision-date",
        config.decision_date.isoformat(),
        "--observed-at-utc",
        config.observed_at.isoformat(),
        "--expected-bootstrap-receipt-sha256",
        config.expected_bootstrap_receipt_sha256,
        "--expected-working-db-sha256",
        config.expected_working_db_sha256,
        "--expected-snapshot-receipt-sha256",
        config.expected_snapshot_receipt_sha256,
        "--skip-candidate-update",
        "--calendar-cache-path",
        str(config.calendar_cache_path),
        "--expected-calendar-cache-sha256",
        str(inputs["expected_calendar_cache_sha256"]),
        "--capture-dir",
        str(inputs["capture_directory"]),
        "--expected-capture-receipt-sha256",
        str(inputs["expected_capture_receipt_sha256"]),
        "--expected-capture-manifest-sha256",
        str(inputs["expected_capture_manifest_sha256"]),
    ]

    exit_code = cli.main(argv)

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.isascii()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "eligible_personal_research"
    assert payload["day_execution_readiness"]["status"] == "blocked"
    assert payload["runner_executed"] is False
