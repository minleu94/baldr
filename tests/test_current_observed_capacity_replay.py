from __future__ import annotations

import base64
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

import test_current_observed_capacity_eligibility as capacity_fixtures
import test_current_observed_learning_capture as learning_fixtures
import scripts.scheduled.run_daily_recommendation_learning as daily_learning
from ml_module.recommendation_calibration_evidence import verify_current_observed_input_capture
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_DATE = date(2026, 10, 5)
DECISION_DATE_TEXT = DECISION_DATE.isoformat()
OBSERVED_AT = datetime(2026, 10, 5, 20, 0, tzinfo=TAIPEI)
CAPTURED_AT = datetime(2026, 10, 5, 20, 1, tzinfo=TAIPEI)


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _populate_frozen_snapshot(database: Path) -> None:
    """Build a small four-table snapshot that the real feature provider can reread."""

    start = date(2026, 6, 1)
    market_days: list[date] = []
    cursor = start
    while cursor <= DECISION_DATE:
        if cursor.weekday() < 5:
            market_days.append(cursor)
        cursor += timedelta(days=1)
    assert len(market_days) >= 60

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            'CREATE TABLE daily_prices '
            '("日期" TEXT, "證券代號" TEXT, "成交股數" INTEGER, "成交金額" NUMERIC, '
            '"開盤價" NUMERIC, "最高價" NUMERIC, "最低價" NUMERIC, "收盤價" NUMERIC)'
        )
        connection.execute(
            'CREATE TABLE technical_indicators '
            '("日期" TEXT, "證券代號" TEXT, "RSI" NUMERIC, "MACD" NUMERIC, "ADX" NUMERIC)'
        )
        connection.execute(
            'CREATE TABLE market_indices ("日期" TEXT, "收盤指數" NUMERIC, "收盤價" NUMERIC)'
        )
        connection.execute(
            'CREATE TABLE industry_indices ("日期" TEXT, "指數名稱" TEXT, "收盤指數" NUMERIC)'
        )
        stock_rows = []
        market_rows = []
        industry_rows = []
        for index, trading_day in enumerate(market_days, start=1):
            compact = trading_day.strftime("%Y%m%d")
            close = 100 + index
            stock_rows.append((compact, "1477", 100_000 + index, 10_000_000 + index, close - 1, close + 1, close - 2, close))
            market_rows.append((compact, 10_000 + index, None))
            industry_rows.append((compact, "fixture-industry", 1_000 + index))
        connection.executemany('INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)', stock_rows)
        connection.executemany('INSERT INTO market_indices VALUES (?, ?, ?)', market_rows)
        connection.executemany('INSERT INTO industry_indices VALUES (?, ?, ?)', industry_rows)
        connection.executemany(
            'INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)',
            [(trading_day.strftime("%Y%m%d"), "1477", 55, 1, 25) for trading_day in market_days],
        )
        connection.commit()
    finally:
        connection.close()


def _install_pinned_context_and_capacity(
    *,
    fixture: Mapping[str, object],
    research_root: Path,
    formal_root: Path,
    raw_run_id: str,
    source_date: str,
    terminal_path: Path,
    inherited_terminal: Mapping[str, Any] | None = None,
) -> str:
    """Update the fixture chain after adding real source tables, preserving every hash pin."""

    snapshot_db = Path(str(fixture["frozen_snapshot_database"]))
    receipt_path = Path(str(fixture["snapshot_receipt"]))
    context_path = Path(str(fixture["context_envelope"]))
    helper_terminal_path = Path(str(fixture["cycle_terminal"]))
    _populate_frozen_snapshot(snapshot_db)
    snapshot_sha = _sha256_file(snapshot_db)

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["snapshot"].update(
        {
            "path": str(snapshot_db.resolve()),
            "sha256": snapshot_sha.removeprefix("sha256:"),
            "bytes": snapshot_db.stat().st_size,
            "mtime_ns": snapshot_db.stat().st_mtime_ns,
        }
    )
    receipt_sha = _write_json(receipt_path, receipt)

    envelope = json.loads(context_path.read_text(encoding="utf-8"))
    context = envelope["source_context"]
    context.update(
        {
            "snapshot_database_path": str(snapshot_db.resolve()),
            "snapshot_database_sha256": snapshot_sha,
            "snapshot_receipt_path": str(receipt_path.resolve()),
            "snapshot_receipt_sha256": receipt_sha,
        }
    )
    context_sha = _write_json(context_path, envelope)

    terminal = dict(inherited_terminal or json.loads(helper_terminal_path.read_text(encoding="utf-8")))
    old_pins = terminal.get("same_run_pins")
    pins = dict(old_pins) if isinstance(old_pins, Mapping) else {}
    pins.update(
        {
            "research_output_root": str(research_root.resolve()),
            "snapshot_database_path": str(snapshot_db.resolve()),
            "snapshot_database_sha256": snapshot_sha,
            "snapshot_receipt_path": str(receipt_path.resolve()),
            "snapshot_receipt_sha256": receipt_sha,
            "source_context_envelope_path": str(context_path.resolve()),
            "source_context_envelope_sha256": context_sha,
            "snapshot_completed_at": "2026-10-05T05:30:00+00:00",
            "revision_dependencies_verified_at": "2026-10-05T05:31:00+00:00",
            "current_restated_training_as_of": "2026-10-05T05:31:00+00:00",
        }
    )
    terminal.update(
        {
            "schema_version": "current-stock-research-cycle-terminal.v1",
            "status": "completed",
            "raw_run_id": raw_run_id,
            "cycle_id": raw_run_id,
            "source_date": source_date,
            "current_symbols": ["1477"],
            "cycle_output_root": str(terminal_path.parent.resolve()),
            "research_only": True,
            "historical_pit_eligible": False,
            "formal_training_eligible": False,
            "formal_oos_allowed": False,
            "formal_credit": False,
            "production_action_allowed": False,
            "same_run_pins": pins,
            "capacity": capacity_fixtures._current_cycle_terminal(
                research_root,
                formal_root,
                raw_run_id=raw_run_id,
                source_date=source_date,
            )["capacity"],
        }
    )
    return _write_json(terminal_path, terminal)


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reuse: bool,
) -> tuple[Path, str, Path, dict[str, Any], Path, Path]:
    """Produce and persist a genuine current-observed capture against a capacity block."""

    repo_fixture_root = tmp_path / "repo"
    research_root = repo_fixture_root / "output" / "ml_research"
    formal_root = tmp_path / "FA_Data" / "output"
    canonical_root = formal_root.resolve()

    reuse_path: Path | None = None
    reuse_sha: str | None = None
    inherited_original: Mapping[str, Any] | None = None
    original_terminal_path: Path
    original_run_id = "raw-run-20261005" if not reuse else "raw-original"
    if reuse:
        reuse_path, _, _registry_path = learning_fixtures._reuse_cycle_fixture(
            repo_fixture_root,
            monkeypatch,
        )
        original_terminal_path = research_root / "current_stock_cycles" / "2026-10-05" / "cycle-storage-key" / "terminal_receipt.json"
        inherited_original = json.loads(
            (research_root / "current_stock_cycles" / "original" / "terminal_receipt.json").read_text(encoding="utf-8")
        )
        original_run_id = "raw-original"
    else:
        original_terminal_path = research_root / "current_stock_cycles" / "2026-10-05" / "cycle-storage-key" / "terminal_receipt.json"

    pinned = learning_fixtures._write_pinned_context_fixture(tmp_path, monkeypatch)
    # Ensure both fixture builders resolve the same isolated legacy research root.
    assert Path(str(pinned["cycle_terminal"])).resolve().is_relative_to(research_root.resolve())
    original_terminal_sha = _install_pinned_context_and_capacity(
        fixture=pinned,
        research_root=research_root,
        formal_root=formal_root,
        raw_run_id=original_run_id,
        source_date=DECISION_DATE_TEXT,
        terminal_path=original_terminal_path,
        inherited_terminal=inherited_original,
    )
    if reuse:
        assert reuse_path is not None
        reuse_payload = json.loads(reuse_path.read_text(encoding="utf-8"))
        reuse_payload["reused_from"]["terminal_receipt_path"] = str(original_terminal_path.resolve())
        reuse_payload["reused_from"]["terminal_receipt_sha256"] = original_terminal_sha
        reuse_sha = _write_json(reuse_path, reuse_payload)

    raw_run_id = "raw-reuse" if reuse else original_run_id
    child_status = "skipped_same_inputs" if reuse else "completed"
    outer_terminal_path = reuse_path if reuse else original_terminal_path
    outer_terminal_sha = reuse_sha if reuse else original_terminal_sha
    assert outer_terminal_path is not None and outer_terminal_sha is not None

    raw_status = capacity_fixtures._formal_capacity_block(tmp_path, child_status=child_status)
    raw_status["output_root"] = str(canonical_root)
    raw_status["raw_output_root"] = str(canonical_root / "release_v4" / "ml_pit_year_shards")
    raw_status["run_id"] = raw_run_id
    raw_status["latest_core_date"] = DECISION_DATE_TEXT
    raw_status["source_date"] = DECISION_DATE_TEXT
    child = raw_status["current_stock_research_cycle"]
    child.update(
        {
            "raw_run_id": raw_run_id,
            "cycle_id": raw_run_id,
            "source_date": DECISION_DATE_TEXT,
            "terminal_receipt_path": str(outer_terminal_path.resolve()),
            "terminal_receipt_sha256": outer_terminal_sha,
        }
    )
    status_path = canonical_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"
    _write_json(status_path, raw_status)

    calendar_path = tmp_path / "official" / "calendar"
    learning_fixtures._open_session_evidence(DECISION_DATE, tmp_path)
    monkeypatch.setattr(daily_learning, "_natural_maturity_calendar_paths", lambda **_: (calendar_path, None))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            value = OBSERVED_AT
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(daily_learning, "datetime", FrozenDateTime)
    monkeypatch.setattr(daily_learning, "get_ml_research_root", lambda **_: research_root.resolve())
    monkeypatch.setattr(
        daily_learning,
        "resolve_ml_research_output_path",
        lambda path, **_: Path(path).expanduser().resolve(),
    )
    # The evidence verifier derives its repository root from the checked-in
    # module; map only the temp repository's approved fixture roots through the
    # same path normalizer so this test never writes into the real output tree.
    import ml_module.recommendation_calibration_evidence as evidence_module

    monkeypatch.setattr(
        evidence_module,
        "resolve_ml_research_output_path",
        lambda path, **_: Path(path).expanduser().resolve(),
    )

    feature_snapshot = daily_learning._current_observed_feature_snapshot_for_learning(
        canonical_output_root=canonical_root,
        config=type("FixtureConfig", (), {"db_file": tmp_path / "calendar-source.sqlite"})(),
        decision_date=DECISION_DATE,
        history_start_date="2026-06-01",
        symbols=("1477",),
        observed_at=OBSERVED_AT,
        expected_raw_run_id=raw_run_id,
        expected_cycle_terminal_path=outer_terminal_path,
        expected_cycle_terminal_sha256=outer_terminal_sha,
    )
    assert feature_snapshot.get("status") == "captured", feature_snapshot
    if reuse:
        assert feature_snapshot.get("discovery_cycle_terminal_status") == "skipped_same_inputs"
        assert feature_snapshot.get("reuse_source_identity", {}).get("original_capacity_verified") is True

    contract_path = tmp_path / "source-contract" / f"{raw_run_id}.json"
    contract_body: dict[str, Any] = {
        "schema_version": "recommendation-calibration-source-contract.v1",
        "decision_date": DECISION_DATE_TEXT,
        "symbols": ["1477"],
        "technical": {"current_observed_feature_snapshot": feature_snapshot},
    }
    contract_hash = daily_learning._source_contract_hash_payload(contract_body)
    contract = {
        **contract_body,
        "contract_sha256": contract_hash,
        "checked_at": CAPTURED_AT.isoformat(),
    }
    contract_file_sha = _write_json(contract_path, contract)
    audit = {
        "source_contract": contract,
        "source_contract_receipt": {
            "contract_path": str(contract_path.resolve()),
            "contract_content_sha256": contract_hash,
            "contract_file_sha256": contract_file_sha,
        },
    }
    learning_output_root = tmp_path.parent / f"l-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}"
    persisted = daily_learning._persist_current_observed_input_capture(
        output_root=learning_output_root,
        source_contract_audit=audit,
        decision_date=DECISION_DATE,
        captured_at=CAPTURED_AT,
        cost_scenario=build_legacy_cost_scenario(80),
        fixed_round_trip_cost_bp=80,
    )
    assert persisted.get("status") == "captured", str(persisted.get("diagnostic") or persisted)
    capture_path = Path(str(persisted["capture_path"]))
    captured = dict(
        verify_current_observed_input_capture(
            capture_path,
            expected_sha256=str(persisted["capture_sha256"]),
        )
    )
    return capture_path, str(persisted["capture_sha256"]), contract_path, captured, status_path, original_terminal_path


def _rehash_capture_source(
    capture: Mapping[str, Any],
    *,
    contract_path: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    snapshot = contract.get("technical", {}).get("current_observed_feature_snapshot")
    assert isinstance(snapshot, dict)
    snapshot_body = {key: value for key, value in snapshot.items() if key != "content_sha256"}
    snapshot["content_sha256"] = daily_learning._source_contract_hash_payload(snapshot_body)
    contract_body = {
        key: value for key, value in contract.items() if key not in {"contract_sha256", "checked_at"}
    }
    contract_hash = daily_learning._source_contract_hash_payload(contract_body)
    contract["contract_sha256"] = contract_hash
    _write_json(contract_path, contract)
    binding, reason = daily_learning._capture_source_contract_binding(
        {
            "source_contract": contract,
            "source_contract_receipt": {
                "contract_path": str(contract_path.resolve()),
                "contract_content_sha256": contract_hash,
                "contract_file_sha256": _sha256_file(contract_path),
            },
        }
    )
    assert binding is not None, reason
    updated = deepcopy(dict(capture))
    updated["source_contract_binding"] = binding
    body = {
        key: value
        for key, value in updated.items()
        if key not in {"content_sha256", "capture_id", "_verified_capture_path", "_verified_capture_sha256"}
    }
    content_hash = daily_learning._source_contract_hash_payload(body)
    updated["content_sha256"] = content_hash
    updated["capture_id"] = (
        f"current-observed:{updated['decision_date']}:{updated['cycle_id']}:{content_hash[7:]}"
    )
    return updated


@pytest.mark.parametrize("reuse", [False, True], ids=["completed", "verified-reuse"])
def test_formal_capacity_blocked_capture_replays_through_public_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reuse: bool,
) -> None:
    capture_path, capture_sha, _contract_path, capture, _status_path, _terminal_path = _fixture(
        tmp_path,
        monkeypatch,
        reuse=reuse,
    )

    replay = verify_current_observed_input_capture(capture_path, expected_sha256=capture_sha)
    assert replay["research_only"] is True
    assert replay["historical_pit_eligible"] is False
    assert replay["formal_training_allowed"] is False
    assert replay["natural_outcome_only"] is True

    source = replay["source_contract_binding"]["current_observed_feature_snapshot"]
    assert source["discovery_cycle_terminal_status"] == (
        "skipped_same_inputs" if reuse else "completed"
    )
    assert source["historical_pit_eligible"] is False
    assert source["entry_observation"]["status"] == "captured"


def test_public_capture_replay_rejects_resigned_bad_capacity_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_path, _capture_sha, contract_path, capture, status_path, terminal_path = _fixture(
        tmp_path,
        monkeypatch,
        reuse=False,
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    original_terminal_sha = _sha256_file(terminal_path)
    terminal["capacity"]["safety_reserve_bytes"] = 1
    new_terminal_sha = _write_json(terminal_path, terminal)
    status["current_stock_research_cycle"]["terminal_receipt_sha256"] = new_terminal_sha
    status_bytes = json.dumps(status, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    status_path.write_bytes(status_bytes)

    snapshot = contract["technical"]["current_observed_feature_snapshot"]
    snapshot["discovery_status_bytes_base64"] = base64.b64encode(status_bytes).decode("ascii")
    snapshot["discovery_status_sha256"] = "sha256:" + hashlib.sha256(status_bytes).hexdigest()
    # All same-run terminal references in the immutable feature and entry pins
    # move together; the only defect is the actual terminal's capacity proof.
    def replace_terminal_sha(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: replace_terminal_sha(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace_terminal_sha(item) for item in value]
        return new_terminal_sha if value == original_terminal_sha else value

    snapshot = replace_terminal_sha(snapshot)
    contract["technical"]["current_observed_feature_snapshot"] = snapshot
    invalid_capture = _rehash_capture_source(
        capture,
        contract_path=contract_path,
        contract=contract,
    )

    with pytest.raises(ValueError, match="G6 terminal capacity proof is invalid"):
        verify_current_observed_input_capture(invalid_capture)


def test_public_capture_replay_rejects_resigned_raw_status_and_terminal_hash_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_path, _capture_sha, contract_path, capture, status_path, _terminal_path = _fixture(
        tmp_path,
        monkeypatch,
        reuse=False,
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    snapshot = contract["technical"]["current_observed_feature_snapshot"]

    # The status body is hash-consistent but is now a non-allowlisted formal failure.
    invalid_status = json.loads(status_path.read_text(encoding="utf-8"))
    invalid_status["status"] = "failed"
    status_bytes = json.dumps(invalid_status, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    status_path.write_bytes(status_bytes)
    snapshot["discovery_status_bytes_base64"] = base64.b64encode(status_bytes).decode("ascii")
    snapshot["discovery_status_sha256"] = "sha256:" + hashlib.sha256(status_bytes).hexdigest()
    bad_status_capture = _rehash_capture_source(capture, contract_path=contract_path, contract=contract)
    with pytest.raises(ValueError, match="raw discovery identity mismatch"):
        verify_current_observed_input_capture(bad_status_capture)

    # Restore source status and then pin a different valid-looking terminal digest.
    terminal_fixture_root = tmp_path.parent / f"pin-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}"
    _capture_path, _capture_sha, contract_path, capture, status_path, _terminal_path = _fixture(
        terminal_fixture_root,
        monkeypatch,
        reuse=False,
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    forged_sha = "sha256:" + "f" * 64
    status["current_stock_research_cycle"]["terminal_receipt_sha256"] = forged_sha
    status_bytes = json.dumps(status, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    status_path.write_bytes(status_bytes)
    snapshot = contract["technical"]["current_observed_feature_snapshot"]
    snapshot["discovery_status_bytes_base64"] = base64.b64encode(status_bytes).decode("ascii")
    snapshot["discovery_status_sha256"] = "sha256:" + hashlib.sha256(status_bytes).hexdigest()
    old_terminal_sha = str(snapshot["cycle_terminal_sha256"])
    snapshot["discovery_cycle_terminal_sha256"] = forged_sha
    snapshot["cycle_terminal_sha256"] = forged_sha
    def replace_digest(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: replace_digest(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace_digest(item) for item in value]
        if value == old_terminal_sha:
            return forged_sha
        return value
    snapshot = replace_digest(snapshot)
    contract["technical"]["current_observed_feature_snapshot"] = snapshot
    bad_terminal_capture = _rehash_capture_source(
        capture,
        contract_path=contract_path,
        contract=contract,
    )
    with pytest.raises(ValueError, match="cycle terminal hash mismatch"):
        verify_current_observed_input_capture(bad_terminal_capture)
