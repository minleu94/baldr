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
from scripts.qa_wp5_daily_chain_preflight import main


OBSERVED_AT = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
SCHEMA_SHA256 = "a" * 64


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _seed_fixture(tmp_path: Path) -> tuple[preflight.PreflightConfig, dict[str, str]]:
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
    db_hash = _sha256(db_path)

    snapshot_dir = qa_parent / "snapshot" / "formal_source_snapshot_v2"
    snapshot_db = snapshot_dir / "twstock.db"
    snapshot_db.parent.mkdir(parents=True)
    shutil.copyfile(db_path, snapshot_db)
    assert _sha256(snapshot_db) == db_hash
    snapshot_receipt_path = snapshot_dir / "snapshot_receipt.json"
    _write_json(
        snapshot_receipt_path,
        {
            "schema_version": preflight.UPSTREAM_SNAPSHOT_SCHEMA,
            "completed_at": "2026-09-28T08:20:43.348100+00:00",
            "snapshot_path": str(snapshot_db),
            "snapshot_sha256": db_hash,
            "snapshot_integrity_check": ["ok"],
            "snapshot_journal_mode": "delete",
            "snapshot_data_version_stable": True,
            "snapshot_schema": {"schema_sha256": SCHEMA_SHA256},
        },
    )
    snapshot_receipt_hash = _sha256(snapshot_receipt_path)

    bootstrap_path = qa_root / "bootstrap_receipt.json"
    _write_json(
        bootstrap_path,
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
                "source_snapshot_receipt": str(snapshot_receipt_path),
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
    bootstrap_hash = _sha256(bootstrap_path)
    env = {
        "PROFILE": "prod",
        "DATA_ROOT": str(data_root),
        "OUTPUT_ROOT": str(output_root),
        "DB_PATH": str(db_path),
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(output_root),
    }
    config = preflight.PreflightConfig(
        qa_root=qa_root,
        decision_date=date(2026, 9, 29),
        observed_at=OBSERVED_AT,
        expected_bootstrap_receipt_sha256=bootstrap_hash,
        expected_working_db_sha256=db_hash,
        expected_snapshot_receipt_sha256=snapshot_receipt_hash,
        skip_candidate_update=True,
        repo_root=repo,
    )
    return config, env


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "_utc_now", lambda: OBSERVED_AT)


def test_seed_integrity_and_isolation_are_separate_from_day_readiness(
    tmp_path: Path,
) -> None:
    config, env = _seed_fixture(tmp_path)
    db_path = config.qa_root / "data" / "sqlite" / "twstock.db"
    before = _sha256(db_path)
    before_files = sorted(
        str(path.relative_to(config.qa_root))
        for path in config.qa_root.rglob("*")
        if path.is_file()
    )

    result = preflight.run_read_only_preflight(config, environ=env)

    assert result["seed_integrity"]["status"] == "verified"
    assert result["seed_integrity"]["sqlite"]["open_mode"] == "ro"
    assert result["seed_integrity"]["sqlite"]["query_only"] == 1
    assert result["seed_integrity"]["bootstrap_claims"][
        "ready_for_daily_pipeline"
    ] is False
    assert result["isolation"]["status"] == "bounded_verified"
    assert result["day_execution_readiness"]["status"] == "blocked"
    codes = {item["code"] for item in result["day_execution_readiness"]["blockers"]}
    assert {
        "annual_calendar_cache_missing",
        "temporary_closure_event_receipt_missing",
        "official_source_time_receipt_missing",
    } <= codes
    assert _sha256(db_path) == before
    after_files = sorted(
        str(path.relative_to(config.qa_root))
        for path in config.qa_root.rglob("*")
        if path.is_file()
    )
    assert after_files == before_files
    assert not any(Path(str(db_path) + suffix).exists() for suffix in preflight.SQLITE_SIDECAR_SUFFIXES)


def test_environment_must_be_prod_and_every_writable_path_must_match_qa_root(
    tmp_path: Path,
) -> None:
    config, env = _seed_fixture(tmp_path)
    env["PROFILE"] = "test"
    external_data = tmp_path / "outside-data"
    external_data.mkdir()
    env["DATA_ROOT"] = str(external_data)

    result = preflight.run_read_only_preflight(config, environ=env)

    codes = {item["code"] for item in result["isolation"]["blockers"]}
    assert "profile_must_be_prod" in codes
    assert "data_root_does_not_match_qa_root" in codes
    assert result["status"] == "blocked"


def test_pit_env_outside_qa_fails_closed_and_candidate_skip_avoids_resolution(
    tmp_path: Path,
) -> None:
    config, env = _seed_fixture(tmp_path)
    outside = tmp_path / "external-pit.json"
    outside.write_text("{}", encoding="utf-8")
    env["PIT_SECTOR_MEMBERSHIP_PATH"] = str(outside)
    env["PHASE3C_CANDIDATE_DB_PATH"] = str(tmp_path / "external-candidate.sqlite")

    result = preflight.run_read_only_preflight(config, environ=env)

    codes = {item["code"] for item in result["isolation"]["blockers"]}
    assert "pit_sector_membership_path_unsafe" in codes
    assert result["isolation"]["checks"]["candidate_update"] == {
        "explicit_skip": True,
        "candidate_db_environment_read": False,
        "windows_registry_read": False,
    }


def test_reparse_component_is_rejected_without_opening_seed_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, env = _seed_fixture(tmp_path)
    protected = config.qa_root / "data"
    original = preflight._is_reparse_point
    monkeypatch.setattr(
        preflight,
        "_is_reparse_point",
        lambda path: Path(path) == protected or original(Path(path)),
    )

    result = preflight.run_read_only_preflight(config, environ=env)

    assert any(
        "reparse_component" in item["code"] or "reparse_component" in item["detail"]
        for item in result["isolation"]["blockers"]
    )
    assert result["seed_integrity"]["status"] == "blocked"


def test_receipt_pin_mismatch_blocks_seed_integrity(tmp_path: Path) -> None:
    config, env = _seed_fixture(tmp_path)
    changed = preflight.PreflightConfig(
        **{
            **config.__dict__,
            "expected_working_db_sha256": "0" * 64,
        }
    )

    result = preflight.run_read_only_preflight(changed, environ=env)

    assert result["seed_integrity"]["status"] == "blocked"
    assert any(
        item["code"] == "lineage_copy_source_sha256_does_not_match_db_pin"
        for item in result["seed_integrity"]["blockers"]
    )


def test_working_db_hardlink_is_rejected_before_hash_or_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, env = _seed_fixture(tmp_path)
    db_path = config.qa_root / "data" / "sqlite" / "twstock.db"
    hardlink = config.qa_root / "data" / "sqlite" / "formal-alias.db"
    os.link(db_path, hardlink)
    assert db_path.stat().st_nlink == 2

    original_hash = preflight._sha256_file

    def hash_spy(path: Path, **kwargs: object) -> tuple[str, int, int]:
        if Path(path) == db_path:
            pytest.fail("working DB must be rejected before full hashing")
        return original_hash(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(preflight, "_sha256_file", hash_spy)
    monkeypatch.setattr(
        preflight.sqlite3,
        "connect",
        lambda *_args, **_kwargs: pytest.fail(
            "hardlinked working DB must be rejected before SQLite open"
        ),
    )

    result = preflight.run_read_only_preflight(config, environ=env)

    assert result["seed_integrity"]["status"] == "blocked"
    assert any(
        item["code"] == "working_db_link_count_not_one:2"
        for item in result["seed_integrity"]["blockers"]
    )


def test_missing_candidate_skip_is_itself_a_blocker(tmp_path: Path) -> None:
    config, env = _seed_fixture(tmp_path)
    changed = preflight.PreflightConfig(**{**config.__dict__, "skip_candidate_update": False})

    result = preflight.run_read_only_preflight(changed, environ=env)

    assert any(
        item["code"] == "candidate_update_must_be_explicitly_skipped_for_qa_preflight"
        for item in result["isolation"]["blockers"]
    )


def test_future_observed_cutoff_stops_before_reading_qa_inputs(tmp_path: Path) -> None:
    config, _env = _seed_fixture(tmp_path)
    changed = preflight.PreflightConfig(
        **{
            **config.__dict__,
            "observed_at": datetime(2026, 9, 29, 9, 1, tzinfo=timezone.utc),
        }
    )

    result = preflight.run_read_only_preflight(changed, environ={})

    assert result["seed_integrity"]["status"] == "not_run"
    assert result["day_execution_readiness"]["status"] == "not_run"
    assert result["blockers"][0]["code"] == "observed_at_is_in_the_future"


def test_stale_observed_cutoff_stops_before_reading_qa_inputs(tmp_path: Path) -> None:
    config, _env = _seed_fixture(tmp_path)
    changed = preflight.PreflightConfig(
        **{
            **config.__dict__,
            "observed_at": datetime(2026, 9, 29, 8, 54, tzinfo=timezone.utc),
        }
    )

    result = preflight.run_read_only_preflight(changed, environ={})

    assert result["seed_integrity"]["status"] == "not_run"
    assert result["blockers"][0]["code"] == "observed_at_is_stale"


def test_valid_annual_open_and_event_only_sidecar_still_block_day_readiness(
    tmp_path: Path,
) -> None:
    config, env = _seed_fixture(tmp_path)
    from data_module.official_trading_calendar_cache import (
        build_twse_calendar_cache,
        build_twse_temporary_closure_cache,
        write_twse_calendar_cache,
        write_twse_temporary_closure_cache,
    )

    cache_root = config.repo_root / "output" / "qa" / "official-cache"
    cache_root.mkdir(parents=True)
    captured = OBSERVED_AT - timedelta(hours=1)
    raw_calendar = json.dumps(
        [
            {
                "Name": "中華民國開國紀念日",
                "Date": "1150101",
                "Weekday": "四",
                "Description": "依規定放假1日。",
            },
            {
                "Name": "國曆新年開始交易日",
                "Date": "1150102",
                "Weekday": "五",
                "Description": "國曆新年開始交易。",
            },
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    annual_path = cache_root / "twse_holiday_schedule_2026.json"
    annual_cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw_calendar,
        requested_at=captured - timedelta(seconds=1),
        captured_at=captured,
        response_status=200,
    )
    write_twse_calendar_cache(annual_path, annual_cache, allowed_root=cache_root.parent)

    closure_at = datetime(2026, 7, 9, 1, 0, tzinfo=timezone.utc)
    closure_url = "https://www.twse.com.tw/zh/announcement/announcement/detail.html?id=test"
    closure_cache = build_twse_temporary_closure_cache(
        closure_date=date(2026, 7, 10),
        raw_response=(
            "<html>臺灣證券交易所集中交易市場於115年7月10日全日休市一天，因颱風影響。</html>"
        ).encode("utf-8"),
        source_url=closure_url,
        requested_at=closure_at - timedelta(seconds=1),
        captured_at=closure_at,
        response_status=200,
        response_url=closure_url,
    )
    closure_path = cache_root / "twse_temporary_closure_20260710.json"
    write_twse_temporary_closure_cache(
        closure_path,
        closure_cache,
        allowed_root=cache_root.parent,
    )
    source_time_path = config.qa_root / "source-time.json"
    _write_json(source_time_path, {"schema_version": "unapproved.experimental.v1"})
    changed = preflight.PreflightConfig(
        **{
            **config.__dict__,
            "calendar_cache_path": annual_path,
            "temporary_closure_path": closure_path,
            "source_time_receipt_path": source_time_path,
        }
    )

    result = preflight.run_read_only_preflight(changed, environ=env)

    assert result["day_execution_readiness"]["calendar"]["status"] == "verified"
    assert result["day_execution_readiness"]["calendar"]["planned_open"] is True
    assert result["day_execution_readiness"]["temporary_closure"]["status"] == "verified_event_only"
    assert result["day_execution_readiness"]["temporary_closure"][
        "negative_coverage_for_decision_date"
    ] is False
    codes = {item["code"] for item in result["day_execution_readiness"]["blockers"]}
    assert "temporary_closure_event_does_not_prove_no_closure_on_decision_date" in codes
    assert "official_source_time_receipt_schema_unimplemented" in codes


def test_cli_emits_json_only_and_does_not_create_status_or_logs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, env = _seed_fixture(tmp_path)
    before = sorted(path.relative_to(config.qa_root).as_posix() for path in config.qa_root.rglob("*"))
    old_environ = dict(__import__("os").environ)
    try:
        __import__("os").environ.clear()
        __import__("os").environ.update(env)
        exit_code = main(
            [
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
            ]
        )
    finally:
        __import__("os").environ.clear()
        __import__("os").environ.update(old_environ)

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert captured.err == ""
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "blocked"
    assert exit_code == 2
    after = sorted(path.relative_to(config.qa_root).as_posix() for path in config.qa_root.rglob("*"))
    assert after == before
