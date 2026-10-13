from __future__ import annotations

import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import subprocess
import tempfile

import pytest

from data_module.paper_daily_execution_producer import (
    PaperExecutionProducerError,
    _prepare_output_root,
)
from scripts.scheduled import run_paper_execution_daily_isolated as isolated
from scripts.scheduled.paper_portfolio_state_isolation import (
    ensure_repo_state_from_readonly_source,
)


def _make_directory_junction(link: Path, target: Path) -> None:
    """在 Windows 建立真正 junction；其他平台使用目錄 symlink。"""

    if os.name != "nt":
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"directory reparse point unavailable: {error}")
        return
    completed = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(link),
            str(target),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode == 0:
        return
    output = f"{completed.stdout}\n{completed.stderr}".casefold()
    if any(
        marker in output
        for marker in (
            "access is denied",
            "privilege",
            "not supported",
            "requires elevation",
        )
    ):
        pytest.skip(f"directory junction unavailable: {output.strip()}")
    pytest.fail(f"directory junction command failed: {output.strip()}")


def _patch_scope_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path]:
    """將 Paper scope writer 全部導向 temp repository，避免碰正式 output。"""

    repo = tmp_path / "repo"
    operation_root = repo / "output" / "paper_execution_eod_replay"
    data_root = tmp_path / "source"
    state_root = operation_root / "paper_portfolio"
    constants = {
        "ROOT": repo,
        "DEFAULT_DATA_ROOT": data_root,
        "OPERATIONAL_ROOT": operation_root,
        "CANDIDATE_ROOT": operation_root / "candidates",
        "RECEIPT_ROOT": operation_root / "receipts",
        "LEDGER_DB": operation_root / "paper_trade_ledger.sqlite",
        "SOURCE_STATE_DB": data_root
        / "output"
        / "paper_portfolio"
        / "paper_portfolio.sqlite",
        "PAPER_STATE_ROOT": state_root,
        "STATE_DB": state_root / "paper_portfolio.sqlite",
        "STATE_SEED_MANIFEST": state_root / "state_seed_manifest.json",
        "MARKET_DB": data_root / "sqlite" / "twstock.db",
        "RECOMMENDATION_ROOT": data_root / "output" / "recommendation" / "runs",
        "EVENT_CAPTURE_ROOT": operation_root / "event_captures",
        "SCOPE_MANIFEST": operation_root / "scope_manifest_v3.json",
    }
    for name, value in constants.items():
        monkeypatch.setattr(isolated, name, value)
    operation_root.mkdir(parents=True)
    (repo / "output").mkdir(parents=True, exist_ok=True)
    return repo, operation_root


def _write_scope_payload(path: Path, body: dict[str, object]) -> bytes:
    payload = {**body, "content_sha256": isolated._payload_hash(body)}
    raw = (isolated._canonical_json(payload) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


@pytest.mark.parametrize("include_event_capture_root", (False, True))
def test_scope_manifest_migrates_only_exact_v2_and_preserves_source_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    include_event_capture_root: bool,
) -> None:
    _repo, operation_root = _patch_scope_paths(monkeypatch, tmp_path)
    legacy_path = isolated._legacy_scope_manifest_path()
    legacy_raw = _write_scope_payload(
        legacy_path,
        isolated._expected_legacy_scope(
            include_event_capture_root=include_event_capture_root
        ),
    )

    target_path, target_hash = isolated._write_or_verify_scope_manifest()

    assert target_path == operation_root / "scope_manifest_v3.json"
    assert target_hash == isolated._file_hash(target_path)
    assert legacy_path.read_bytes() == legacy_raw
    assert json.loads(target_path.read_text(encoding="utf-8"))["schema_version"] == (
        "paper-execution-isolated-scope.v3"
    )
    migration_receipt = isolated._scope_migration_receipt_path()
    receipt = json.loads(migration_receipt.read_text(encoding="utf-8"))
    assert receipt["source_file_sha256"] == isolated._bytes_hash(legacy_raw)
    assert receipt["target_file_sha256"] == target_hash
    assert receipt["source_bytes_preserved"] is True
    assert receipt["planned_diff"]["append_only"] is True
    expected_changed_fields = {
        "schema_version",
        "writable.scope_manifest",
    }
    if not include_event_capture_root:
        expected_changed_fields.add("writable.event_capture_root")
    assert set(receipt["planned_diff"]["changed_fields"]) == expected_changed_fields
    assert isinstance(receipt["recorded_at"], str)

    target_raw = target_path.read_bytes()
    receipt_raw = migration_receipt.read_bytes()
    recorded_at = receipt["recorded_at"]
    isolated._write_or_verify_scope_manifest()
    assert target_path.read_bytes() == target_raw
    assert migration_receipt.read_bytes() == receipt_raw
    assert legacy_path.read_bytes() == legacy_raw
    assert json.loads(migration_receipt.read_text(encoding="utf-8"))["recorded_at"] == (
        recorded_at
    )


def test_scope_manifest_v2_root_drift_is_rejected_without_new_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, operation_root = _patch_scope_paths(monkeypatch, tmp_path)
    legacy_path = isolated._legacy_scope_manifest_path()
    legacy_body = isolated._expected_legacy_scope(include_event_capture_root=False)
    source = legacy_body["source"]
    assert isinstance(source, dict)
    source["market_db"] = str(tmp_path / "outside" / "market.sqlite")
    legacy_raw = _write_scope_payload(legacy_path, legacy_body)

    with pytest.raises(RuntimeError, match="scope manifest changed"):
        isolated._write_or_verify_scope_manifest()

    assert legacy_path.read_bytes() == legacy_raw
    assert not (operation_root / "scope_manifest_v3.json").exists()
    assert not isolated._scope_migration_receipt_path().exists()


def test_scope_validation_exception_writes_only_safe_terminal_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, operation_root = _patch_scope_paths(monkeypatch, tmp_path)
    legacy_path = isolated._legacy_scope_manifest_path()
    legacy_body = isolated._expected_legacy_scope(include_event_capture_root=False)
    source = legacy_body["source"]
    assert isinstance(source, dict)
    source["market_db"] = str(tmp_path / "outside" / "market.sqlite")
    _write_scope_payload(legacy_path, legacy_body)
    monkeypatch.setattr(isolated, "load_optional_formal_runtime_config", lambda **_: None)

    result = isolated.run_isolated(
        now=datetime(2026, 9, 21, 13, 0, 3, tzinfo=timezone.utc)
    )

    assert result["status"] == "failed"
    assert result["terminal"] is True
    assert result["scope_validation_failed"] is True
    receipt_path = Path(str(result["terminal_failure_receipt_path"]))
    assert receipt_path.is_file()
    assert receipt_path.parent == (
        repo / "output" / "paper_execution_eod_replay" / "scope_validation_failures"
    ).resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["scope_writer_targets_verified"] is False
    assert receipt["status"] == "failed"
    assert not (operation_root / "scope_manifest_v3.json").exists()
    assert not (operation_root / "scope_manifest_v3_migration_receipt.json").exists()
    assert not (operation_root / "receipts").exists()
    assert not (operation_root / "candidates").exists()


def test_paper_output_requires_explicit_controlled_root_for_non_temp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "other-temp"))
    with pytest.raises(PaperExecutionProducerError, match="under OS TEMP"):
        _prepare_output_root(tmp_path / "unscoped")

    controlled = tmp_path / "controlled"
    run_root = controlled / "run-1"
    prepared = _prepare_output_root(run_root, controlled_root=controlled)
    assert prepared == run_root.resolve()
    assert prepared.is_dir()

    with pytest.raises(PaperExecutionProducerError, match="direct child"):
        _prepare_output_root(
            controlled / "nested" / "run-2",
            controlled_root=controlled,
        )


def test_operation_root_junction_outside_repo_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repository_output = repo / "output"
    repository_output.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    operation_link = repository_output / "paper_execution_eod_replay"
    _make_directory_junction(operation_link, outside)

    source_root = tmp_path / "source"
    monkeypatch.setattr(isolated, "ROOT", repo)
    monkeypatch.setattr(isolated, "DEFAULT_DATA_ROOT", source_root)
    monkeypatch.setattr(isolated, "OPERATIONAL_ROOT", operation_link)
    monkeypatch.setattr(isolated, "CANDIDATE_ROOT", operation_link / "candidates")
    monkeypatch.setattr(isolated, "RECEIPT_ROOT", operation_link / "receipts")
    monkeypatch.setattr(isolated, "LEDGER_DB", operation_link / "paper_trade_ledger.sqlite")
    monkeypatch.setattr(isolated, "SCOPE_MANIFEST", operation_link / "scope_manifest.json")

    with pytest.raises(RuntimeError, match="operation root"):
        isolated._validate_write_scope()


def test_pit_sector_manifest_resolver_freezes_exact_hash_and_available_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    archive_root = (
        repo
        / "output"
        / "formal_daily_publications"
        / "pit_candidate_archive"
    )
    for entry, effective in (("old", "2026-09-07"), ("new", "2026-09-08")):
        manifest = archive_root / effective / entry / "archive_manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"effective_from": effective}) + "\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(isolated, "ROOT", repo)

    import ml_module.pit_archive_consumer as archive_consumer

    def fake_consume(**kwargs: object) -> dict[str, object]:
        manifest_path = kwargs["manifest_path"]
        assert isinstance(manifest_path, Path)
        effective = manifest_path.parents[1].name
        return {
            "status": "machine_verified_archive_candidate",
            "archive_manifest_hash": "sha256:" + effective[-1] * 64,
            "archive_id": "pit-candidate:" + effective,
            "effective_from": effective,
            "captured_at": effective + "T08:30:00+08:00",
            "available_at": effective + "T08:31:00+08:00",
            "archived_at": effective + "T08:32:00+08:00",
            "row_count": 1984,
            "source_ids": ["official:twse:t187ap03_L"],
        }

    monkeypatch.setattr(
        archive_consumer,
        "consume_pit_candidate_archive",
        fake_consume,
    )
    path, file_hash, projection = isolated._resolve_pit_sector_manifest(
        datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    )

    assert path == (
        archive_root / "2026-09-08" / "new" / "archive_manifest.json"
    ).resolve()
    assert file_hash == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert projection["status"] == "selected"
    assert projection["effective_from"] == "2026-09-08"
    assert projection["available_at"] == "2026-09-08T00:31:00+00:00"

    prior_path, _, prior_projection = isolated._resolve_pit_sector_manifest(
        datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    )
    assert prior_path == (archive_root / "2026-09-07" / "old" / "archive_manifest.json").resolve()
    assert prior_projection["effective_from"] == "2026-09-07"


def test_policy_blocked_candidate_does_not_attempt_fill_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_capture(**kwargs: object) -> None:
        pytest.fail("被拒絕候選不可嘗試成交綁定")

    monkeypatch.setattr(isolated, "resolve_persisted_twse_event_source_capture_for_recommendation", unexpected_capture)
    result = {"status": "blocked", "blockers": ["paper policy sector archive rejected:fixture"], "retryable": False}
    assert isolated._bind_paper_result_to_event_capture(result, observed=datetime.now(timezone.utc)) == result


@pytest.mark.parametrize(
    "runner_status",
    ("waiting_for_execution_session", "no_trade_required_candidate"),
)
def test_isolated_adapter_initializes_ledger_before_queue_or_no_fill_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner_status: str,
) -> None:
    data_root = tmp_path / "source"
    source_state_db = data_root / "output" / "paper_portfolio" / "paper_portfolio.sqlite"
    market_db = data_root / "sqlite" / "twstock.db"
    recommendation_root = data_root / "output" / "recommendation" / "runs"
    source_state_db.parent.mkdir(parents=True)
    market_db.parent.mkdir(parents=True)
    recommendation_root.mkdir(parents=True)
    with sqlite3.connect(source_state_db) as connection:
        connection.execute(
            "CREATE TABLE paper_portfolio_snapshots (snapshot_id TEXT)"
        )
        connection.execute(
            "CREATE TABLE paper_portfolio_positions (snapshot_id TEXT)"
        )
    with sqlite3.connect(market_db) as connection:
        connection.execute("CREATE TABLE daily_prices (日期 TEXT)")

    repo = tmp_path / "repo"
    repo_output = repo / "output"
    repo_output.mkdir(parents=True)
    operation_root = repo_output / "operation"
    candidate_root = operation_root / "candidates"
    receipt_root = operation_root / "receipts"
    ledger_db = operation_root / "paper_trade_ledger.sqlite"
    state_db = operation_root / "paper_portfolio" / "paper_portfolio.sqlite"
    scope_manifest = operation_root / "scope_manifest.json"
    for name, value in {
        "DEFAULT_DATA_ROOT": data_root,
        "OPERATIONAL_ROOT": operation_root,
        "CANDIDATE_ROOT": candidate_root,
        "RECEIPT_ROOT": receipt_root,
        "LEDGER_DB": ledger_db,
        "SOURCE_STATE_DB": source_state_db,
        "PAPER_STATE_ROOT": state_db.parent,
        "STATE_SEED_MANIFEST": state_db.parent / "state_seed_manifest.json",
        "STATE_DB": state_db,
        "MARKET_DB": market_db,
        "RECOMMENDATION_ROOT": recommendation_root,
        "EVENT_CAPTURE_ROOT": operation_root / "event_captures",
        "SCOPE_MANIFEST": scope_manifest,
        }.items():
            monkeypatch.setattr(isolated, name, value)
    monkeypatch.setattr(isolated, "ROOT", repo)
    ensure_repo_state_from_readonly_source(
        source=source_state_db,
        target=state_db,
        manifest_path=state_db.parent / "state_seed_manifest.json",
        observed_at=datetime.now(timezone.utc),
    )
    monkeypatch.setenv("PAPER_EXECUTION_LEDGER_DB", r"D:\unsafe\ledger.sqlite")
    monkeypatch.setenv("PAPER_EXECUTION_OUTPUT_ROOT", r"D:\unsafe\output")
    sector_manifest = (
        repo_output
        / "formal_daily_publications"
        / "pit_candidate_archive"
        / "2026-09-08"
        / "capture-1"
        / "archive_manifest.json"
    )
    sector_manifest.parent.mkdir(parents=True)
    sector_manifest.write_text("{}", encoding="utf-8")
    sector_hash = "sha256:" + "a" * 64
    monkeypatch.setattr(
        isolated,
        "_resolve_pit_sector_manifest",
        lambda observed: (
            sector_manifest,
            sector_hash,
            {
                "status": "selected",
                "manifest_path": str(sector_manifest),
                "manifest_file_hash": sector_hash,
            },
        ),
    )
    monkeypatch.setattr(
        isolated,
        "_refresh_calendar_cache",
        lambda observed: {
            "status": "cache_valid",
            "calendar_year": 2026,
            "refresh_attempted": False,
            "network_attempts": 0,
        },
    )
    monkeypatch.setattr(
        isolated,
        "_refresh_temporary_closure_events",
        lambda observed: {
            "status": "temporary_closure_discovery_blocked",
            "calendar_year": 2026,
            "network_attempts": 0,
            "detail_requests": 0,
            "reason": "test_no_network",
            "events": [],
        },
    )

    observed: dict[str, object] = {}

    def fake_runner(paths: object, **kwargs: object) -> dict[str, object]:
        assert isinstance(paths, isolated.PaperExecutionPaths)
        with sqlite3.connect(
            paths.ledger_db.as_uri() + "?mode=ro", uri=True
        ) as connection:
            connection.execute("PRAGMA query_only=ON")
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert tables == {
            "paper_trade_ledger",
            "paper_trade_transitions",
            "paper_trade_daily_operations",
        }
        observed["paths"] = paths
        observed.update(kwargs)
        return {
            "status": runner_status,
            "formal_credit": False,
        }

    monkeypatch.setattr(isolated, "run_paper_execution_daily_from_queue", fake_runner)
    result = isolated.run_isolated()

    paths = observed["paths"]
    assert isinstance(paths, isolated.PaperExecutionPaths)
    assert paths.state_db == state_db
    assert paths.market_db == market_db
    assert paths.ledger_db == ledger_db
    assert paths.sector_membership_path is None
    assert paths.sector_membership_file_hash is None
    resolver = observed["sector_source_resolver"]
    assert callable(resolver)
    assert resolver({"created_at": "2026-09-08T12:00:00+00:00"}) == (sector_manifest, sector_hash)
    assert paths.controlled_output_root == candidate_root
    assert paths.output_root.parent == candidate_root
    assert observed["recommendation_root"] == recommendation_root
    assert observed["receipt_root"] == receipt_root
    assert observed["persist_receipt"] is False
    calendar = observed["calendar"]
    assert isinstance(calendar, isolated.OfficialTradingCalendar)
    assert calendar.calendar_cache_path == operation_root / "calendar_cache"
    assert calendar.temporary_closure_path == operation_root / "calendar_cache"
    assert observed["confirm_append"] is True
    assert result["status"] == runner_status
    scope = result["isolated_scope"]
    assert isinstance(scope, dict)
    assert scope["append_target"] == str(ledger_db.resolve())
    assert scope["append_target_is_d_source"] is False
    assert scope["environment_path_overrides_ignored"] is True
    source_observation = scope["source_observation"]
    assert isinstance(source_observation, dict)
    sector_source = source_observation["sector_membership_source"]
    assert isinstance(sector_source, dict)
    assert sector_source["status"] == "selected"
    assert source_observation["calendar_refresh"]["status"] == "cache_valid"  # type: ignore[index]
    assert source_observation["temporary_closure_refresh"]["status"] == (  # type: ignore[index]
        "temporary_closure_discovery_blocked"
    )
    refresh_receipt = source_observation["calendar_refresh_receipt"]  # type: ignore[index]
    assert isinstance(refresh_receipt, dict)
    assert Path(str(refresh_receipt["path"])).is_file()
    assert ledger_db.exists() is True
    ledger_schema = source_observation["paper_ledger_schema"]
    assert isinstance(ledger_schema, dict)
    assert ledger_schema["readback_verified"] is True
    assert ledger_schema["row_counts"] == {
        "paper_trade_ledger": 0,
        "paper_trade_transitions": 0,
    }
    assert ledger_schema["historical_transition_evidence_inferred"] is False
    manifest = json.loads(scope_manifest.read_text(encoding="utf-8"))
    assert manifest["safety"]["formal_credit"] is False
    assert manifest["writable"]["ledger_db"] == str(ledger_db.resolve())


def test_isolated_eod_rejects_ledger_target_outside_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    operation_root = repo / "output" / "paper_execution_eod_replay"
    monkeypatch.setattr(isolated, "ROOT", repo)
    monkeypatch.setattr(isolated, "OPERATIONAL_ROOT", operation_root)
    monkeypatch.setattr(isolated, "CANDIDATE_ROOT", operation_root / "candidates")
    monkeypatch.setattr(isolated, "RECEIPT_ROOT", operation_root / "receipts")
    state_root = operation_root / "paper_portfolio"
    monkeypatch.setattr(isolated, "PAPER_STATE_ROOT", state_root)
    monkeypatch.setattr(isolated, "STATE_DB", state_root / "paper_portfolio.sqlite")
    monkeypatch.setattr(
        isolated,
        "STATE_SEED_MANIFEST",
        state_root / "state_seed_manifest.json",
    )
    monkeypatch.setattr(
        isolated,
        "SCOPE_MANIFEST",
        operation_root / "scope_manifest.json",
    )
    monkeypatch.setattr(
        isolated,
        "EVENT_CAPTURE_ROOT",
        operation_root / "event_captures",
    )
    monkeypatch.setattr(
        isolated,
        "LEDGER_DB",
        tmp_path / "outside" / "paper_trade_ledger.sqlite",
    )

    with pytest.raises(RuntimeError, match="ledger_db"):
        isolated._validate_write_scope()
    assert not (tmp_path / "outside" / "paper_trade_ledger.sqlite").exists()


def test_calendar_refresh_uses_taipei_year_and_operation_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_root = tmp_path / "repo-output" / "paper"
    monkeypatch.setattr(isolated, "OPERATIONAL_ROOT", operation_root)
    observed = datetime(2026, 12, 31, 16, 30, tzinfo=timezone.utc)
    captured: dict[str, object] = {}

    def fake_refresh(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "status": "cache_valid",
            "calendar_year": 2027,
            "refresh_attempted": False,
            "network_attempts": 0,
        }

    monkeypatch.setattr(isolated, "refresh_twse_calendar_cache", fake_refresh)
    result = isolated._refresh_calendar_cache(observed)

    assert result["status"] == "cache_valid"
    assert captured["calendar_year"] == 2027
    assert captured["cache_root"] == operation_root / "calendar_cache"
    assert captured["allowed_root"] == operation_root.resolve()
    assert captured["observed_at"] == observed
