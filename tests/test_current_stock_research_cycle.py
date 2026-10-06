from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import gzip
from pathlib import Path
import subprocess
import sys
import sqlite3
import tempfile
from typing import Any

import pytest

from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    release_heavy_chain_reservation,
)
from data_module.ml_daily_price_revision_gate import load_verified_current_restated_source_context
from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from ml_module import current_restated_research_bridge as research_bridge
from scripts.scheduled import current_stock_research_cycle as cycle
from tests.ml_research_test_support import install_test_revision_gate, write_snapshot_context_receipt


def _child_result(
    *, returncode: int, stdout: bytes = b"", stderr: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(["fit"], returncode, stdout, stderr)


def _parse_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[bytes]
) -> cycle._ChildJsonObject:
    monkeypatch.setattr(cycle, "_run_child", lambda *args, **kwargs: result)
    return cycle._completed_child_json(
        ["python", "fit.py"],
        repository_root=tmp_path,
        reservation=object(),  # injected child runner bypasses OS handoff
        timeout_seconds=1,
        child_runner=lambda *args, **kwargs: result,
        label="test fit",
    )


def test_child_failure_keeps_exact_stdout_and_stderr_before_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout = b"annual raw diagnostic\r\n"
    stderr = b'{"error_type":"ChildError","message":"failed safely"}\n'
    result = _child_result(returncode=2, stdout=stdout, stderr=stderr)
    cycle_root = tmp_path / "cycle"
    cycle_root.mkdir()
    state: dict[str, object] = {"stage_results": {}}
    monkeypatch.setattr(cycle, "_run_child", lambda *args, **kwargs: result)

    def observe(child_result: subprocess.CompletedProcess[bytes]) -> None:
        cycle._record_child_result(
            state=state,  # type: ignore[arg-type]
            cycle_root=cycle_root,
            stage="raw_publication",
            child_name="annual_raw",
            command=["python", "build_ml_pit_year_shards.py", "--current-restated-research"],
            result=child_result,
        )

    with pytest.raises(cycle.CurrentStockResearchCycleError, match="failed safely"):
        cycle._completed_child_json(
            ["python", "build_ml_pit_year_shards.py"],
            repository_root=tmp_path,
            reservation=object(),  # injected runner bypasses OS handoff
            timeout_seconds=1,
            child_runner=lambda *args, **kwargs: result,
            label="annual raw producer",
            result_observer=observe,
        )

    captured = state["stage_results"]["raw_publication"]["annual_raw"]  # type: ignore[index]
    assert captured["returncode"] == 2
    assert captured["stdout"]["sha256"] == "sha256:" + hashlib.sha256(stdout).hexdigest()
    assert captured["stderr"]["sha256"] == "sha256:" + hashlib.sha256(stderr).hexdigest()
    assert Path(captured["stdout"]["path"]).read_bytes() == stdout
    assert Path(captured["stderr"]["path"]).read_bytes() == stderr


def test_cycle_storage_key_keeps_all_deep_outputs_within_windows_path_budget() -> None:
    raw_run_id = "raw-pit-20261004T034826267316Z-28984-9c2b1ebf9dcf411a8a741c6c50e83e3a"
    storage_key = cycle._cycle_storage_key(raw_run_id)
    production_cycle_root = (
        cycle.REPOSITORY_ROOT
        / "output"
        / "ml_research"
        / "current_stock_cycles"
        / "2026-10-02"
        / storage_key
    )
    assert len(storage_key) == 32
    assert storage_key == hashlib.sha256(raw_run_id.encode("utf-8")).hexdigest()[:32]
    assert storage_key != raw_run_id

    old_cycle_root = (
        cycle.REPOSITORY_ROOT
        / "output"
        / "ml_research"
        / "current_stock_cycles"
        / "2026-10-02"
        / raw_run_id
    )
    old_shard = (
        old_cycle_root
        / "raw_publication"
        / "runs"
        / ("current-restated-" + "a" * 24)
        / "core_long_history"
        / "year=2026.jsonl.gz"
    )
    assert len(str(old_shard)) >= 260

    raw_run_dir = production_cycle_root / "raw_publication" / "runs" / (
        "current-restated-" + "a" * 24
    )
    outcome_run_dir = production_cycle_root / "outcome_artifacts" / "runs" / (
        "current-restated-outcome-" + "a" * 24
    )
    sidecar_run_id = "20261004T123456789012Z-" + "a" * 12
    cycle_paths = {
        "raw dataset manifest": raw_run_dir / "core_long_history" / "manifest.json",
        "raw year shard": raw_run_dir / "core_long_history" / "year=2026.jsonl.gz",
        "outcome manifest": outcome_run_dir / "manifest.json",
        "outcome observations": outcome_run_dir / "observations.jsonl",
        "model manifest": production_cycle_root / "model" / "manifest.json",
        "model vector": production_cycle_root / "model" / "current_vectors" / "9999.json",
        "fit receipt": production_cycle_root / "model" / "fit_receipt.json",
        "sidecar receipt": production_cycle_root / "source_row_research" / "legacy" / sidecar_run_id / "receipt.json",
        "sidecar failure": production_cycle_root / "source_row_research" / "legacy" / sidecar_run_id / "failed_receipt.json",
        "child stderr": production_cycle_root / "child_evidence" / "raw_publication_annual_raw.stderr.bin",
        "cycle terminal": production_cycle_root / "terminal_receipt.json",
        "source context": production_cycle_root / "context" / "source_context.json",
        "source snapshot": production_cycle_root / "snapshot" / "source_snapshot.sqlite3",
    }
    assert max(map(lambda path: len(str(path)), cycle_paths.values())) < 260

    # Probe the real repository output hierarchy, not a short pytest temp root.
    # The extra random probe suffix makes these paths slightly longer than the
    # eventual production directory while exercising Windows create/stat/resolve.
    cycle_parent = production_cycle_root.parent
    cycle_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=storage_key + "-path-probe-", dir=str(cycle_parent)
    ) as probe_name:
        probe_root = Path(probe_name)
        candidates = {
            name: probe_root / path.relative_to(production_cycle_root)
            for name, path in cycle_paths.items()
        }
        for name, path in candidates.items():
            assert len(str(path)) < 260, f"{name} exceeds classic Windows MAX_PATH"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"windows-path-probe")
            resolved = path.resolve(strict=True)
            assert resolved.stat().st_size == len(b"windows-path-probe"), name
            assert resolved.read_bytes() == b"windows-path-probe", name

    registry_root = (
        cycle.REPOSITORY_ROOT
        / "output"
        / "ml_research"
        / "current_stock_research_registry"
    )
    registry_run = registry_root / "runs" / ("20261002-" + "a" * 24)
    registry_record = registry_run / "record.json"
    registry_parent = registry_root.parent
    registry_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="current-stock-registry-path-probe-", dir=str(registry_parent)
    ) as probe_name:
        probe_root = Path(probe_name)
        candidate = probe_root / registry_record.relative_to(registry_root)
        assert len(str(candidate)) < 260
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(b"registry-path-probe")
        assert candidate.resolve(strict=True).stat().st_size == len(b"registry-path-probe")


def test_large_outcome_manifest_uses_exact_pinned_producer_summary_without_raising_receipt_cap(
    tmp_path: Path,
) -> None:
    run_id = "current-restated-outcome-" + "a" * 24
    run_dir = tmp_path / "outcome" / "runs" / run_id
    run_dir.mkdir(parents=True)
    manifest_path = run_dir / "manifest.json"
    # The real outcome manifest is 39,245,761 bytes because 40 walk-forward
    # folds carry their exact train/test sample IDs. Keep a compact fixture
    # that crosses the generic metadata cap without storing a huge test blob.
    manifest_bytes = (
        b'{"fold_policy":"'
        + b"x" * (cycle.MAX_RECEIPT_BYTES + 1)
        + b'"}'
    )
    manifest_path.write_bytes(manifest_bytes)
    raw_publication_sha = "sha256:" + "1" * 64
    raw_dataset_sha = "sha256:" + "2" * 64
    summary = {
        "schema_version": "portfolio-ml-current-restated-outcome-cli.v1",
        "status": "completed_research_only",
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "full_teacher_qualified": False,
        "run_id": run_id,
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "raw_publication_manifest_sha256": raw_publication_sha,
        "raw_dataset_manifest_sha256": raw_dataset_sha,
        "feature_registry_sha256": "sha256:" + "3" * 64,
        "observation_count": 30_861,
        "feature_count": 49,
        "fold_count": 40,
        "artifact_available_at": "2026-10-04T04:31:06.955707+00:00",
    }

    pinned = cycle._pin_outcome_cli_summary(
        summary,
        output_root=run_dir.parent.parent,
        symbols=("1225", "1256", "1465", "1477", "1560", "1714", "1721", "2382", "3207", "9935"),
        raw_publication_manifest_sha256=raw_publication_sha,
        raw_dataset_manifest_sha256=raw_dataset_sha,
    )

    assert pinned["manifest_path"] == str(manifest_path.resolve())
    assert pinned["manifest_pin"]["bytes"] > cycle.MAX_RECEIPT_BYTES
    assert pinned["manifest_sha256"] == "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
    assert pinned["observation_count"] == 30_861
    assert pinned["feature_count"] == 49
    assert pinned["fold_count"] == 40
    with pytest.raises(cycle._InvalidEvidence, match="metadata byte limit"):
        cycle._parse_json_object(manifest_bytes, "ordinary metadata fixture")

    manifest_path.write_bytes(manifest_bytes + b" ")
    with pytest.raises(cycle._InvalidEvidence, match="manifest bytes differ"):
        cycle._pin_outcome_cli_summary(
            summary,
            output_root=run_dir.parent.parent,
            symbols=("1225", "1256", "1465", "1477", "1560", "1714", "1721", "2382", "3207", "9935"),
            raw_publication_manifest_sha256=raw_publication_sha,
            raw_dataset_manifest_sha256=raw_dataset_sha,
        )


def test_fit_child_retains_hash_of_exact_stdout_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = b'{"status":"verified_base_outcome_only"}\r\n'
    result = _parse_child(tmp_path, monkeypatch, _child_result(returncode=0, stdout=raw))

    assert result["status"] == "verified_base_outcome_only"
    assert result.stdout_sha256 == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert result.stdout_sha256 != cycle._canonical_sha256(dict(result))


def test_fit_child_accepts_whole_multiline_receipt_and_keeps_root_object() -> None:
    receipt = {
        "schema_version": "current-restated-core19-fit-receipt.v1",
        "status": "verified_base_outcome_only",
        "training_performed": True,
        "folds": [{"fold": 1, "metrics": {"rows": 29_927, "ready": True}}],
    }
    raw = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
    parsed = cycle._output_json_object(raw, label="bounded fit", stream_name="stdout")

    assert parsed == receipt
    assert parsed is not None
    child = cycle._ChildJsonObject(parsed, stdout_sha256="sha256:" + hashlib.sha256(raw).hexdigest())
    assert cycle._require_core19_fit_receipt(child)["status"] == "verified_base_outcome_only"


def test_child_json_parser_accepts_one_log_plus_receipt_but_rejects_ambiguous_objects() -> None:
    one_receipt = b'fit started\n{"schema_version":"v1","status":"ok"}\n'
    parsed = cycle._output_json_object(one_receipt, label="fit", stream_name="stdout")
    assert parsed == {"schema_version": "v1", "status": "ok"}

    ambiguous = b'{"status":"progress"}\n{"status":"complete"}\n'
    assert cycle._output_json_object(ambiguous, label="fit", stream_name="stdout") is None


def test_child_json_parser_never_mines_a_receipt_from_nonobject_or_broken_root() -> None:
    receipt = {"schema_version": "v1", "status": "ok"}
    root_array = json.dumps([receipt], separators=(",", ":")).encode("utf-8")
    assert cycle._output_json_object(root_array, label="fit", stream_name="stdout") is None

    broken_outer = (
        b"fit started\n{\n  \"wrapper\":\n"
        b'{"schema_version":"v1","status":"ok"}\n}\n'
    )
    assert cycle._output_json_object(broken_outer, label="fit", stream_name="stdout") is None


def test_fit_receipt_parser_rejects_an_unexpected_schema() -> None:
    raw = b'{"schema_version":"other.v1","status":"verified_base_outcome_only"}\n'
    parsed = cycle._output_json_object(raw, label="fit", stream_name="stdout")
    assert parsed is not None
    child = cycle._ChildJsonObject(parsed, stdout_sha256="sha256:" + hashlib.sha256(raw).hexdigest())
    with pytest.raises(cycle._InvalidEvidence, match="unsupported receipt schema"):
        cycle._require_core19_fit_receipt(child)


def test_fit_output_leaf_is_create_only_and_controller_does_not_precreate_it(
    tmp_path: Path,
) -> None:
    cycle_root = tmp_path / "cycle"
    cycle_root.mkdir()

    fit_output = cycle._new_fit_output_path(cycle_root)
    assert fit_output == cycle_root / "model"
    assert not fit_output.exists()

    fit_output.mkdir(exist_ok=False)
    with pytest.raises(cycle._InvalidEvidence, match="fit model output already exists"):
        cycle._new_fit_output_path(cycle_root)
    assert list(fit_output.iterdir()) == []

    # Match the real CLI writer contract: the writer creates the leaf itself
    # with exist_ok=False. An empty or partial pre-existing leaf is occupied.
    pinned_partial = fit_output / "writer-started.bin"
    pinned_partial.write_bytes(b"create-only-writer-bytes")
    before = {
        path.relative_to(fit_output): path.read_bytes()
        for path in fit_output.rglob("*")
        if path.is_file()
    }
    with pytest.raises(cycle._InvalidEvidence, match="fit model output already exists"):
        cycle._new_fit_output_path(cycle_root)
    assert {
        path.relative_to(fit_output): path.read_bytes()
        for path in fit_output.rglob("*")
        if path.is_file()
    } == before


def test_fit_child_classifies_only_explicit_maturity_receipt_as_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = {
        "schema_version": "current-restated-core19-fit-receipt.v1",
        "status": "blocked_or_failed",
        "reason": "InsufficientMatureCurrentRestatedHistoryError: fewer than four real folds",
    }
    with pytest.raises(cycle._WaitingForSource):
        _parse_child(
            tmp_path,
            monkeypatch,
            _child_result(returncode=2, stderr=json.dumps(receipt).encode("utf-8")),
        )


@pytest.mark.parametrize(
    "reason",
    [
        "CurrentRestatedResearchError: model fold hash mismatch",
        "CurrentRestatedResearchError: immature schema invalid",
    ],
)
def test_fit_child_does_not_hide_engineering_errors_as_maturity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    receipt = {
        "schema_version": "current-restated-core19-fit-receipt.v1",
        "status": "blocked_or_failed",
        "reason": reason,
    }
    with pytest.raises(cycle.CurrentStockResearchCycleError) as raised:
        _parse_child(
            tmp_path,
            monkeypatch,
            _child_result(returncode=2, stderr=json.dumps(receipt).encode("utf-8")),
        )
    assert type(raised.value) is cycle.CurrentStockResearchCycleError


def test_current_cycle_borrows_parent_lock_without_releasing_it(tmp_path: Path) -> None:
    lock_path = tmp_path / "release_v4" / "heavy.lock"
    parent_reservation = acquire_heavy_chain_reservation(lock_path)
    assert parent_reservation is not None
    try:
        borrowed, owned = cycle._borrow_or_acquire_reservation(
            lock_path, parent_reservation
        )
        assert borrowed is parent_reservation
        assert owned is False
        assert acquire_heavy_chain_reservation(lock_path) is None
        assert parent_reservation._released is False
    finally:
        release_heavy_chain_reservation(parent_reservation)
    recovered = acquire_heavy_chain_reservation(lock_path)
    assert recovered is not None
    release_heavy_chain_reservation(recovered)


def test_current_cycle_blocks_when_another_process_holds_parent_lock(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "release_v4" / "heavy.lock"
    worker = r'''
import sys
from pathlib import Path
from data_module.ml_storage_capacity import acquire_heavy_chain_reservation
reservation = acquire_heavy_chain_reservation(Path(sys.argv[1]))
print("locked" if reservation is not None else "blocked", flush=True)
sys.stdin.readline()
if reservation is not None:
    reservation.release()
'''
    holder = subprocess.Popen(
        [sys.executable, "-c", worker, str(lock_path)],
        cwd=cycle.REPOSITORY_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        reservation, owned = cycle._borrow_or_acquire_reservation(lock_path, None)
        assert reservation is None
        assert owned is False
    finally:
        if holder.poll() is None:
            assert holder.stdin is not None
            holder.stdin.write("release\n")
            holder.stdin.flush()
            holder.wait(timeout=10)


def test_current_holdings_reads_canonical_string_key_trade_ledger(tmp_path: Path) -> None:
    canonical_output_root = tmp_path / "canonical-output"
    trades_path = canonical_output_root / "portfolio" / "trades.jsonl"
    trades_path.parent.mkdir(parents=True)
    trade = {
        "trade_id": "trade-3207-1",
        "portfolio_id": "default",
        "stock_code": "3207",
        "stock_name": "YFY Inc.",
        "side": "buy",
        "quantity": 1000,
        "price": 100,
        "trade_date": "2026-10-02",
    }
    trades_path.write_text(
        json.dumps(trade, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    current_symbols, source_pins = cycle._read_current_holdings_from_trade_ledger(
        canonical_output_root
    )

    assert current_symbols == {"3207"}
    assert source_pins[0]["path"] == str(trades_path.resolve())
    assert source_pins[0]["bytes"] == trades_path.stat().st_size
    assert len(source_pins[0]["sha256"]) == 64


def test_absent_wal_snapshot_records_real_wal_mode_without_creating_sidecars(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.db"
    connection = sqlite3.connect(source)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
    connection.execute("CREATE TABLE sample (value INTEGER NOT NULL)")
    connection.execute("INSERT INTO sample VALUES (1)")
    connection.commit()
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.close()
    wal_path = source.with_name(source.name + "-wal")
    shm_path = source.with_name(source.name + "-shm")
    assert not wal_path.exists()
    assert not shm_path.exists()

    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    result = cycle._create_consistent_snapshot(
        source_database=source,
        snapshot_database=snapshot_root / "copy.db",
        receipt_path=snapshot_root / "receipt.json",
    )
    receipt = json.loads(Path(result["snapshot_receipt_path"]).read_text(encoding="utf-8"))

    assert receipt["schema_version"] == "integration-consistent-sqlite-snapshot.v2"
    assert receipt["source_journal_mode_before"] == "wal"
    assert receipt["source_journal_mode_after"] == "wal"
    assert receipt["source_journal_mode_reader"] == "sqlite_file_header_read_write_version.v1"
    assert receipt["source_observation"]["wal"] == {
        "status": "absent",
        "present": False,
        "path": str(wal_path.resolve()),
    }
    assert result["source_observation"]["wal"]["present"] is False
    assert not wal_path.exists()
    assert not shm_path.exists()


def test_context_fit_freeze_is_after_revision_verification_and_envelope_reloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    research_root = repository / "output" / "ml_research"
    research_root.mkdir(parents=True)

    def test_resolver(path: Path, **kwargs: Any) -> Path:
        kwargs.setdefault("repository_root", repository)
        return resolve_ml_research_output_path(path, **kwargs)

    monkeypatch.setattr(research_bridge, "resolve_ml_research_output_path", test_resolver)
    install_test_revision_gate(monkeypatch)
    snapshot_path = research_root / "cycle" / "snapshot.sqlite"
    snapshot_path.parent.mkdir()
    snapshot_path.write_bytes(b"verified snapshot bytes")
    receipt_path, receipt_sha = write_snapshot_context_receipt(
        snapshot_path,
        tmp_path,
        completed_at="2026-10-03T00:23:25.887429+00:00",
    )
    snapshot_completed = datetime.fromisoformat("2026-10-03T00:23:25.887429+00:00")
    source_database = tmp_path / "source_context" / "original_source.sqlite"
    context = load_verified_current_restated_source_context(
        snapshot_path,
        receipt_path,
        expected_snapshot_database_sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        expected_snapshot_receipt_sha256=receipt_sha,
        original_database_path=source_database,
        decision_at=snapshot_completed,
        training_as_of=snapshot_completed,
    )

    fit_freeze = cycle._context_fit_freeze(
        snapshot_completed,
        context.revision_dependencies_verified_at,
    )
    assert fit_freeze >= context.revision_dependencies_verified_at
    context = replace(context, training_as_of=fit_freeze)
    envelope_dir = research_root / "cycle" / "context"
    envelope_dir.mkdir()
    envelope_path, envelope_sha = research_bridge.save_verified_current_restated_context_file(
        context,
        output_path=envelope_dir / "source_context.json",
        fit_cutoff=fit_freeze.isoformat(),
    )
    loaded = research_bridge.load_verified_current_restated_context_file(
        envelope_path,
        expected_context_sha256=envelope_sha,
    )

    assert loaded.sha256 == envelope_sha
    assert loaded.saved_payload["decision_at"] == snapshot_completed.isoformat()
    assert loaded.saved_payload["training_as_of"] == fit_freeze.isoformat()
    assert datetime.fromisoformat(loaded.saved_payload["training_as_of"]) >= datetime.fromisoformat(
        loaded.saved_payload["revision_dependencies_verified_at"]
    )


def _write_b_semantic_fixture(
    root: Path,
    *,
    captured_at: str,
    close_scale: int = 2,
    close_value_int: int = 12345,
    missing_feature_ids: tuple[str, ...] = (),
) -> tuple[Path, dict[str, object]]:
    repository = root / "repo"
    research_root = repository / "output" / "ml_research"
    run_root = research_root / "b" / captured_at.replace(":", "-")
    store_root = run_root / "store"
    store_root.mkdir(parents=True)
    registry = [
        {
            "feature_id": feature_id,
            "table_name": "daily_prices",
            "source_id": "daily_prices",
            "family": "daily_prices",
            "scale": scale,
            "unit": unit,
            "value_type": "scaled_integer",
            "staleness_days": 10,
            "record_hash": "sha256:" + hashlib.sha256(source_id.encode("utf-8")).hexdigest(),
        }
        for feature_id, source_id, scale, unit in (
            ("daily_prices.開盤價", "daily_prices.open", 2, "TWD/share"),
            ("daily_prices.最高價", "daily_prices.high", 2, "TWD/share"),
            ("daily_prices.最低價", "daily_prices.low", 2, "TWD/share"),
            ("daily_prices.收盤價", "daily_prices.close", close_scale, "TWD/share"),
            ("daily_prices.成交股數", "daily_prices.volume", 0, "share"),
            ("daily_prices.成交金額", "daily_prices.amount", 0, "TWD"),
            ("daily_prices.成交筆數", "daily_prices.trade_count", 0, "trade"),
        )
    ]
    registry_path = store_root / "feature_registry.json"
    registry_raw = cycle._canonical_json_bytes(registry)
    registry_path.write_bytes(registry_raw)
    registry_sha = cycle._canonical_sha256(registry)
    values = []
    numeric_values = {
        "daily_prices.開盤價": 12000,
        "daily_prices.最高價": 12400,
        "daily_prices.最低價": 11900,
        "daily_prices.收盤價": close_value_int,
        "daily_prices.成交股數": 1000,
        "daily_prices.成交金額": 12345000,
        "daily_prices.成交筆數": 123,
    }
    for feature in registry:
        feature_id = str(feature["feature_id"])
        if feature_id in missing_feature_ids:
            continue
        values.append(
            {
                "feature_id": feature_id,
                "value_int": numeric_values[feature_id],
                "scale": feature["scale"],
                "unit": feature["unit"],
                "formal_training_eligible": False,
                "source_value_hash": "sha256:" + hashlib.sha256(captured_at.encode()).hexdigest(),
            }
        )
    row = {
        "schema_version": "ml-pit-observation.v1",
        "dataset_id": "all_field_enriched",
        "symbol": "2330",
        "event_date": "2026-10-03",
        "available_at": captured_at,
        "current_restated": True,
        "historical_pit_eligible": False,
        "source_table": "daily_prices",
        "source_id": "daily_prices",
        "family": "daily_prices",
        "values": values,
        "missing_mask": list(missing_feature_ids),
        "quality_blocked_mask": [],
        "staleness_mask": [],
        "source_projection_row_identity_hash": "sha256:" + hashlib.sha256(captured_at.encode()).hexdigest(),
    }
    uncompressed = cycle._canonical_json_bytes(row) + b"\n"
    compressed = gzip.compress(uncompressed, mtime=0)
    shard_path = store_root / "2026-10-03.jsonl.gz"
    shard_path.write_bytes(compressed)
    adapted_path = run_root / "adapted_manifest.json"
    adapted_body = {
        "schema_version": "ml-research-adapted-raw-manifest.v1",
        "stage": "verified_numeric_observations",
        "dataset_id": "all_field_enriched",
        "format": "gzip_jsonl",
        "candidate_schema_version": "ml-daily-source-row-research-projection.v1",
        "row_schema": "ml-pit-observation.v1",
        "training_as_of": captured_at,
        "created_at": captured_at,
        "current_observation_freeze": {"available_at_or_before": captured_at, "identity": "sha256:run-clock"},
        "temporal_semantics": {
            "event_date_distinct_from_available_at": True,
            "current_restated": True,
            "historical_pit_eligible": False,
            "source_revision_qualification": "unverified_requires_separate_strict_inspection",
        },
        "source_revision_qualification": "unverified_requires_separate_strict_inspection",
        "feature_registry_sha256": registry_sha,
        "features": registry,
    }
    adapted_body["manifest_hash"] = cycle._canonical_sha256(adapted_body)
    adapted_raw = cycle._canonical_json_bytes(adapted_body)
    adapted_path.write_bytes(adapted_raw)
    terminal = {
        "feature_registry_path": str(registry_path.resolve()),
        "feature_registry_sha256": registry_sha,
        "feature_registry_bytes_sha256": "sha256:" + hashlib.sha256(registry_raw).hexdigest(),
        "adapted_manifest_path": str(adapted_path.resolve()),
        "adapted_manifest_sha256": "sha256:" + hashlib.sha256(adapted_raw).hexdigest(),
        "adapted_manifest_canonical_sha256": adapted_body["manifest_hash"],
        "stored_shards": [
            {
                "path": str(shard_path.resolve()),
                "bytes_sha256": "sha256:" + hashlib.sha256(compressed).hexdigest(),
                "compressed_sha256": "sha256:" + hashlib.sha256(compressed).hexdigest(),
                "uncompressed_sha256": "sha256:" + hashlib.sha256(uncompressed).hexdigest(),
                "row_count": 1,
            }
        ],
    }
    return repository, terminal


def test_b_semantic_reuse_accepts_new_capture_clock_but_rejects_mapping_drift(
    tmp_path: Path,
) -> None:
    repo_a, old_b = _write_b_semantic_fixture(
        tmp_path / "old", captured_at="2026-10-03T08:00:00+00:00"
    )
    repo_b, current_same_b = _write_b_semantic_fixture(
        tmp_path / "new", captured_at="2026-10-03T08:01:00+00:00"
    )
    repo_c, current_drifted_b = _write_b_semantic_fixture(
        tmp_path / "drift", captured_at="2026-10-03T08:02:00+00:00", close_scale=3, close_value_int=123450
    )
    old_identity = cycle._current_b_semantic_identity(
        b_terminal=old_b,
        symbols=("2330",),
        source_date="2026-10-03",
        repository_root=repo_a,
    )
    same_identity = cycle._current_b_semantic_identity(
        b_terminal=current_same_b,
        symbols=("2330",),
        source_date="2026-10-03",
        repository_root=repo_b,
    )
    drifted_identity = cycle._current_b_semantic_identity(
        b_terminal=current_drifted_b,
        symbols=("2330",),
        source_date="2026-10-03",
        repository_root=repo_c,
    )
    assert old_identity == same_identity
    assert old_identity != drifted_identity
    assert cycle._verify_reusable_b_semantics(
        old_b_terminal=old_b,
        old_b_terminal_pins={"b_semantic_identity": old_identity},
        expected_current_b_semantic_identity=same_identity,
        symbols=("2330",),
        source_date="2026-10-03",
        repository_root=repo_a,
    ) == old_identity
    with pytest.raises(cycle._InvalidEvidence, match="semantic identity differs"):
        cycle._verify_reusable_b_semantics(
            old_b_terminal=old_b,
            old_b_terminal_pins={"b_semantic_identity": old_identity},
            expected_current_b_semantic_identity=drifted_identity,
            symbols=("2330",),
            source_date="2026-10-03",
            repository_root=repo_a,
        )

    shared_key_inputs = {
        "source_date": "2026-10-03",
        "scope": {
            "current_symbols": ["2330"],
            "watchlist_symbols": ["2330"],
            "holding_symbols": [],
            "watchlist_input_pins": [
                {
                    "path": "C:/fixture/watchlists.db",
                    "bytes": 128,
                    "mtime_ns": 100,
                    "sha256": "e" * 64,
                }
            ],
            "position_input_pins": [
                {
                    "path": "D:/fixture/trades.jsonl",
                    "bytes": 256,
                    "mtime_ns": 200,
                    "sha256": "f" * 64,
                }
            ],
        },
        "source_observation": {"database": {"path": "source.db", "bytes": 100, "sha256": "a" * 64}},
        "price_fingerprints": {"2330": "b" * 64},
        "official_raw_input_identity": {"source_date": "2026-10-03", "official_raw_response_sha256_by_venue": {"twse": "c" * 64}},
    }
    assert cycle._current_cycle_reuse_key(
        **shared_key_inputs, b_semantic_identity=old_identity
    ) == cycle._current_cycle_reuse_key(
        **shared_key_inputs, b_semantic_identity=same_identity
    )
    assert cycle._current_cycle_reuse_key(
        **shared_key_inputs, b_semantic_identity=old_identity
    ) != cycle._current_cycle_reuse_key(
        **shared_key_inputs, b_semantic_identity=drifted_identity
    )
    touched_watchlist_inputs = {
        **shared_key_inputs,
        "scope": {
            **shared_key_inputs["scope"],
            "watchlist_input_pins": [
                {
                    **shared_key_inputs["scope"]["watchlist_input_pins"][0],
                    "mtime_ns": 101,
                }
            ],
        },
    }
    assert cycle._current_cycle_reuse_key(
        **shared_key_inputs, b_semantic_identity=old_identity
    ) != cycle._current_cycle_reuse_key(
        **touched_watchlist_inputs, b_semantic_identity=old_identity
    )
    changed_position_inputs = {
        **shared_key_inputs,
        "scope": {
            **shared_key_inputs["scope"],
            "position_input_pins": [
                {
                    **shared_key_inputs["scope"]["position_input_pins"][0],
                    "bytes": 257,
                    "sha256": "1" * 64,
                }
            ],
        },
    }
    assert cycle._current_cycle_reuse_key(
        **shared_key_inputs, b_semantic_identity=old_identity
    ) != cycle._current_cycle_reuse_key(
        **changed_position_inputs, b_semantic_identity=old_identity
    )
    post_g5_inputs = {
        **shared_key_inputs,
        "source_observation": {
            "database": {"path": "source.db", "bytes": 101, "sha256": "d" * 64}
        },
    }
    assert cycle._current_cycle_reuse_key(
        **shared_key_inputs, b_semantic_identity=old_identity
    ) != cycle._current_cycle_reuse_key(
        **post_g5_inputs, b_semantic_identity=old_identity
    )


@pytest.mark.parametrize("required_name", ("volume", "amount"))
def test_b_semantic_identity_rejects_missing_required_ohlcv_turnover(
    tmp_path: Path,
    required_name: str,
) -> None:
    feature_id = cycle.B_DAILY_FEATURE_IDS[required_name]
    repository, terminal = _write_b_semantic_fixture(
        tmp_path / required_name,
        captured_at="2026-10-03T08:00:00+00:00",
        missing_feature_ids=(feature_id,),
    )

    with pytest.raises(cycle._InvalidEvidence, match="OHLCV/turnover"):
        cycle._current_b_semantic_identity(
            b_terminal=terminal,
            symbols=("2330",),
            source_date="2026-10-03",
            repository_root=repository,
        )


def _write_public_registry_fixture(
    root: Path,
    *,
    entry_overrides: dict[str, object] | None = None,
    record_run_id: str = "cycle-1",
    record_sha_override: str | None = None,
) -> tuple[Path, Path, str]:
    repository = root / "repo"
    registry_root = repository / "output" / "ml_research" / "current_stock_research_registry"
    record_path = registry_root / "runs" / "cycle-1" / "record.json"
    record_path.parent.mkdir(parents=True)
    record = {
        "schema_version": "current-restated-stock-research-registry.v1",
        "run_id": record_run_id,
        "status": "verified_research_sidecar",
        "historical_pit_eligible": False,
        "formal_calibration_performed": False,
        "formal_qualified": False,
        "production_action_allowed": False,
    }
    record_bytes = cycle._canonical_json_bytes(record)
    record_path.write_bytes(record_bytes)
    record_sha = hashlib.sha256(record_bytes).hexdigest()
    entry: dict[str, object] = {
        "schema_version": "current-restated-stock-research-registry-index.v1",
        "run_id": "cycle-1",
        "record_path": "runs/cycle-1/record.json",
        "record_sha256": record_sha if record_sha_override is None else record_sha_override,
    }
    entry.update(entry_overrides or {})
    index_path = registry_root / "run_index.jsonl"
    index_path.write_bytes(cycle._canonical_json_bytes(entry) + b"\n")
    return repository, record_path, record_sha


def _verify_public_registry_fixture(repository: Path, record_path: Path, record_sha: str) -> str:
    index_path = repository / "output" / "ml_research" / "current_stock_research_registry" / "run_index.jsonl"
    return cycle._verify_public_ml_registry_index_binding(
        index_path,
        repository_root=repository,
        expected_run_id="cycle-1",
        expected_record_path=record_path,
        expected_record_sha256=record_sha,
    )


def test_reuse_registry_verifier_accepts_public_reader_contract(
    tmp_path: Path,
) -> None:
    repository, record_path, record_sha = _write_public_registry_fixture(tmp_path)

    index_sha = _verify_public_registry_fixture(repository, record_path, record_sha)
    assert index_sha.startswith("sha256:")


def test_reuse_registry_verifier_reads_exact_legacy_index_with_active_root_configured(
    tmp_path: Path,
) -> None:
    repository, record_path, record_sha = _write_public_registry_fixture(tmp_path)
    active_research_root = tmp_path / "FA_ML_Research"
    active_research_root.mkdir()
    config_path = repository / "output" / "ml_research_storage.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(active_research_root),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    index_sha = _verify_public_registry_fixture(repository, record_path, record_sha)

    assert index_sha.startswith("sha256:")


@pytest.mark.parametrize(
    ("entry_overrides", "record_run_id", "record_sha_override", "match"),
    (
        ({"schema_version": "wrong.v1"}, "cycle-1", None, "schema or required fields"),
        ({"record_path": "../outside.json"}, "cycle-1", None, "unsafe record path"),
        ({}, "another-run", None, "record cycle-1 violates"),
        ({}, "cycle-1", "0" * 64, "does not match its indexed hash"),
    ),
)
def test_reuse_registry_verifier_rejects_invalid_index_or_record_pins(
    tmp_path: Path,
    entry_overrides: dict[str, object],
    record_run_id: str,
    record_sha_override: str | None,
    match: str,
) -> None:
    repository, record_path, record_sha = _write_public_registry_fixture(
        tmp_path,
        entry_overrides=entry_overrides,
        record_run_id=record_run_id,
        record_sha_override=record_sha_override,
    )

    with pytest.raises(cycle._InvalidEvidence, match=match):
        _verify_public_registry_fixture(repository, record_path, record_sha)


def test_reuse_registry_verifier_rejects_corrupt_unrelated_index_entry(
    tmp_path: Path,
) -> None:
    repository, record_path, record_sha = _write_public_registry_fixture(tmp_path)
    index_path = repository / "output" / "ml_research" / "current_stock_research_registry" / "run_index.jsonl"
    broken = {
        "schema_version": "wrong.v1",
        "run_id": "other-cycle",
        "record_path": "runs/other-cycle/record.json",
        "record_sha256": "f" * 64,
    }
    with index_path.open("ab") as stream:
        stream.write(cycle._canonical_json_bytes(broken) + b"\n")

    with pytest.raises(cycle._InvalidEvidence, match="schema or required fields"):
        _verify_public_registry_fixture(repository, record_path, record_sha)


@pytest.mark.parametrize(
    ("candidate_run_id", "candidate_cycle_id", "match"),
    (
        ("cycle-1", "cycle-1", None),
        ("other-run", "cycle-1", "cannot select the exact reusable run"),
        ("cycle-1", "other-cycle", "cannot select the exact reusable run"),
    ),
)
def test_reuse_requires_the_public_reader_to_select_the_exact_run(
    monkeypatch: pytest.MonkeyPatch,
    candidate_run_id: str,
    candidate_cycle_id: str,
    match: str | None,
) -> None:
    from app_module import stock_research_report_provider_adapters

    fingerprints = {"2330": "a" * 64}

    class FakeRegistry:
        def __init__(self, *, repository_root: Path, now_provider: object) -> None:
            self.repository_root = repository_root
            self.now_provider = now_provider

        def __call__(self, stock_code: str, cutoff: object, *, context: object) -> dict[str, str]:
            assert stock_code == "2330"
            return {
                "run_id": candidate_run_id,
                "cycle_id": candidate_cycle_id,
                "event_date": "2026-10-03",
                "current_price_row_fingerprint_sha256": fingerprints[stock_code],
                "model_manifest_sha256": "b" * 64,
                "model_bundle_sha256": "c" * 64,
            }

    monkeypatch.setattr(
        stock_research_report_provider_adapters,
        "CurrentRestatedMLRunRegistry",
        FakeRegistry,
    )
    kwargs = {
        "repository_root": Path("C:/repo"),
        "run_id": "cycle-1",
        "cycle_id": "cycle-1",
        "source_date": "2026-10-03",
        "symbols": ("2330",),
        "price_fingerprints": fingerprints,
        "model_manifest_sha256": "b" * 64,
        "model_bundle_sha256": "c" * 64,
    }
    if match is None:
        cycle._verify_public_registry_selects_reusable_run(**kwargs)
    else:
        with pytest.raises(cycle._InvalidEvidence, match=match):
            cycle._verify_public_registry_selects_reusable_run(**kwargs)


def test_real_registry_publisher_record_passes_cycle_and_public_reader_checks(
    tmp_path: Path,
) -> None:
    from zoneinfo import ZoneInfo

    from app_module.stock_research_report_provider_adapters import (
        CurrentRestatedMLRunRegistry,
        stock_price_row_fingerprint_sha256,
    )

    research_root = tmp_path.parent / f"{tmp_path.name}_FA_ML_Research"
    research_root.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "ml_research_storage.json").write_text(
        json.dumps(
            {"schema_version": "ml-research-storage.v1", "active_root": str(research_root)},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    manifest_dir = research_root / "model"
    sidecar_dir = research_root / "fit"
    projection_dir = research_root / "b_projection"
    for directory in (manifest_dir, sidecar_dir, projection_dir):
        directory.mkdir()

    bundle_bytes = b"verified-current-stock-research-test-model"
    (manifest_dir / "model.bundle").write_bytes(bundle_bytes)
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
    model_key = "final|CORE19|h5|ridge_logistic"
    manifest = {
        "schema_version": "ml-current-restated-base-outcome-model.v1",
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "production_action_allowed": False,
        "model_available_at": "2026-10-04T04:00:00+00:00",
        "target_contract": {"target_metric": "benchmark_excess_after_standard_80bp_cost"},
        "model_bundle": {
            "sha256": bundle_sha,
            "filename": "model.bundle",
            "model_keys": [model_key],
        },
    }
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    symbol = "1477"
    other_symbol = "1225"
    symbols = (other_symbol, symbol)
    event_date = "2026-10-02"
    context_sha = "c" * 64
    price_fingerprints = {
        code: stock_price_row_fingerprint_sha256(
            stock_code=code,
            data_date=event_date,
            open_price="100",
            high_price="103",
            low_price="99",
            close_price="102",
            volume=1000,
            turnover="102000",
        )
        for code in symbols
    }
    vector_hashes = {other_symbol: "e" * 64, symbol: "d" * 64}
    vector_sha = vector_hashes[symbol]
    immature_h5 = {
        "status": "not_mature",
        "horizon": 5,
        "gross_stock_return_bp": None,
        "gross_benchmark_return_bp": None,
        "benchmark_excess_after_standard_80bp_cost": None,
        "after_lane_cost_stock_return_bp": None,
        "next_entry_date": None,
        "horizon_end_date": None,
        "round_trip_cost": None,
        "price_inputs": None,
    }
    sidecar = {
        "schema_version": "current-restated-source-row-learning-terminal.v1",
        "status": "verified_research_sidecar",
        "terminal": True,
        "mode": "source_row_outcome_research",
        "historical_pit_eligible": False,
        "formal_calibration_performed": False,
        "formal_order_allowed": False,
        "production_action_allowed": False,
        "model_training_performed": False,
        "verified_model_reused": True,
        "lane": "legacy",
        "generated_at": "2026-10-04T05:01:00+00:00",
        "inference_at": "2026-10-04T05:00:00+00:00",
        "input_binding": {
            "current_event_date": event_date,
            "current_symbols": list(symbols),
            "source_context_sha256": context_sha,
            "model_manifest_sha256": manifest_sha,
            "model_bundle_sha256": bundle_sha,
        },
        "source_pins": {
            "source_context_sha256": context_sha,
            "model_manifest_sha256": manifest_sha,
            "model_bundle_sha256": bundle_sha,
            "direct_manifest_sha256": "f" * 64,
        },
        "core19_numeric_vector_sha256_by_symbol": vector_hashes,
        "predictions": [
            {
                "symbol": symbol,
                "event_date": event_date,
                "core19_numeric_vector_sha256": vector_sha,
                "model_prediction": {
                    "schema_version": "ml-current-restated-outcome-prediction.v1",
                    "status": "research_prediction_only",
                    "symbol": symbol,
                    "event_date": event_date,
                    "model_manifest_sha256": manifest_sha,
                    "historical_pit": False,
                    "decision_time_eligible": False,
                    "production_action_allowed": False,
                    "target_metric": "benchmark_excess_after_standard_80bp_cost",
                    "model_available_at": "2026-10-04T04:00:00+00:00",
                    "inference_at": "2026-10-04T05:00:00+00:00",
                    "input_quality_summary": {
                        "usable_feature_count": 19,
                        "registry_feature_count": 19,
                    },
                    "predicted_benchmark_excess_return_bp": {model_key: 125},
                },
                "gross_outcome_and_cost": dict(immature_h5),
            }
        ],
        "sample_cohort_sha256": "a" * 64,
    }
    other_prediction = json.loads(json.dumps(sidecar["predictions"][0]))
    other_prediction["symbol"] = other_symbol
    other_prediction["core19_numeric_vector_sha256"] = vector_hashes[other_symbol]
    other_prediction["model_prediction"]["symbol"] = other_symbol
    sidecar["predictions"].append(other_prediction)
    sidecar_bytes = json.dumps(
        sidecar, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    sidecar_path = sidecar_dir / "receipt.json"
    sidecar_path.write_bytes(sidecar_bytes)
    projection_bytes = b'{"event_date":"2026-10-02","schema_version":"fixture"}\n'
    projection_path = projection_dir / "projection_observations.jsonl"
    projection_path.write_bytes(projection_bytes)
    projection_sha = hashlib.sha256(projection_bytes).hexdigest()

    now = datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc)
    raw_run_id = "raw-pit-20261004T060000000000Z-1-test"
    publisher_and_reader = CurrentRestatedMLRunRegistry(
        repository_root=tmp_path,
        now_provider=lambda: now,
        model_loader=lambda *args, **kwargs: None,
    )
    published = publisher_and_reader.publish_sidecar(
        sidecar_receipt_path=sidecar_path,
        expected_sidecar_receipt_sha256="sha256:" + hashlib.sha256(sidecar_bytes).hexdigest(),
        model_manifest_path=manifest_path,
        expected_model_manifest_sha256="sha256:" + manifest_sha,
        expected_model_bundle_sha256="sha256:" + bundle_sha,
        cycle_id=raw_run_id,
        current_price_row_fingerprint_sha256_by_symbol=price_fingerprints,
        current_price_rows_source_path=projection_path,
        expected_current_price_rows_source_sha256="sha256:" + projection_sha,
    )
    assert published.indexed is True
    record_path = published.record_path.resolve(strict=True)
    record = json.loads(record_path.read_text(encoding="utf-8"))

    cycle._verify_published_current_stock_registry_record(
        record,
        raw_run_id=raw_run_id,
        published_run_id=published.run_id,
        source_date=event_date,
        symbols=symbols,
        source_context_sha256="sha256:" + context_sha,
        sidecar_receipt_sha256="sha256:" + hashlib.sha256(sidecar_bytes).hexdigest(),
        model_manifest_sha256="sha256:" + manifest_sha,
        model_bundle_sha256="sha256:" + bundle_sha,
        current_price_fingerprints=price_fingerprints,
        current_price_rows_source_path=projection_path.resolve(strict=True),
        current_price_rows_source_sha256="sha256:" + projection_sha,
    )
    index_sha = cycle._verify_public_ml_registry_index_binding(
        published.index_path,
        repository_root=tmp_path,
        expected_run_id=published.run_id,
        expected_record_path=record_path,
        expected_record_sha256=published.record_sha256,
    )
    assert index_sha.startswith("sha256:")

    public = publisher_and_reader(
        symbol,
        now.astimezone(ZoneInfo("Asia/Taipei")).date(),
        {
            "stock_code": symbol,
            "ml_scope_mode": "current_stock_research",
            "current_event_date": event_date,
            "current_price_row_fingerprint_sha256": price_fingerprints[symbol],
        },
    )
    assert public is not None
    assert public["run_id"] == published.run_id
    assert public["cycle_id"] == raw_run_id
    assert public["model_manifest_sha256"] == manifest_sha
    assert public["model_bundle_sha256"] == bundle_sha
    assert public["current_price_row_fingerprint_sha256"] == price_fingerprints[symbol]
    assert public["research_only"] is True
    assert public["historical_pit_eligible"] is False

    with pytest.raises(cycle._InvalidEvidence, match="not bound"):
        cycle._verify_published_current_stock_registry_record(
            record,
            raw_run_id="different-raw-run",
            published_run_id=published.run_id,
            source_date=event_date,
            symbols=symbols,
            source_context_sha256="sha256:" + context_sha,
            sidecar_receipt_sha256="sha256:" + hashlib.sha256(sidecar_bytes).hexdigest(),
            model_manifest_sha256="sha256:" + manifest_sha,
            model_bundle_sha256="sha256:" + bundle_sha,
            current_price_fingerprints=price_fingerprints,
            current_price_rows_source_path=projection_path.resolve(strict=True),
            current_price_rows_source_sha256="sha256:" + projection_sha,
        )
    with pytest.raises(cycle._InvalidEvidence, match="fingerprints differ"):
        cycle._verify_published_current_stock_registry_record(
            record,
            raw_run_id=raw_run_id,
            published_run_id=published.run_id,
            source_date=event_date,
            symbols=symbols,
            source_context_sha256="sha256:" + context_sha,
            sidecar_receipt_sha256="sha256:" + hashlib.sha256(sidecar_bytes).hexdigest(),
            model_manifest_sha256="sha256:" + manifest_sha,
            model_bundle_sha256="sha256:" + bundle_sha,
            current_price_fingerprints={**price_fingerprints, symbol: "0" * 64},
            current_price_rows_source_path=projection_path.resolve(strict=True),
            current_price_rows_source_sha256="sha256:" + projection_sha,
        )


def test_cycle_publisher_injects_exact_existing_model_loader() -> None:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(cycle.run_current_stock_research_cycle))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)
             and node.func.id == "publish_current_restated_stock_research_run"]
    assert len(calls) == 1
    loaders = [item.value for item in calls[0].keywords if item.arg == "model_loader"]
    assert len(loaders) == 1
    assert isinstance(loaders[0], ast.Name)
    assert loaders[0].id == "load_current_restated_outcome_model"
    bindings = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                and node.module == "ml_module.current_restated_research_bridge"
                and any(item.name == "load_current_restated_outcome_model" and item.asname is None
                        for item in node.names)]
    assert len(bindings) == 1
    assert bindings[0].lineno < calls[0].lineno
