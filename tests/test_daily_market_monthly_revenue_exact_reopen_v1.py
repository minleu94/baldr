from __future__ import annotations

from datetime import datetime
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import psutil

import pytest
import data_module.fundamental_read_snapshot as snapshot_module

from data_module.daily_market_monthly_revenue_read_session_v1 import (
    DailyMarketMonthlyRevenueFinishedCohortV1,
    DailyMarketMonthlyRevenueReadCancelled,
    DailyMarketMonthlyRevenueReadSessionError,
    DailyMarketMonthlyRevenueReadSessionV1,
    MonthlyRevenueReadFactV1,
    DailyMarketMonthlyRevenueSourceReferenceV1,
    DailyMarketMonthlyRevenueSourceReferenceV2,
)
from data_module.fundamental_read_snapshot import (
    FundamentalSnapshotSourceClock,
    FundamentalReadSnapshotError,
    FundamentalReadSnapshotCancelled,
    FundamentalReadSnapshotRawArchiveReferenceV1,
    FundamentalReadSnapshotSession,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    RecommendationCurrentFundamentalProvider,
)
from tests.test_daily_market_monthly_revenue_read_session_v1 import (
    CUTOFF,
    _seed_provider,
)


def _finish_source(
    root: Path,
    *,
    codes: tuple[str, ...] = ("1101", "2330"),
) -> tuple[
    RecommendationCurrentFundamentalProvider,
    DailyMarketMonthlyRevenueReadSessionV1,
    DailyMarketMonthlyRevenueFinishedCohortV1,
    DailyMarketMonthlyRevenueSourceReferenceV1,
]:
    provider = _seed_provider(root / "provider")
    session = DailyMarketMonthlyRevenueReadSessionV1.open(
        provider,
        snapshot_root=root / "saved_snapshots",
        stock_codes=codes,
        cutoff_at=CUTOFF,
    )
    session.load_batch(codes)
    finished = session.finish()
    source_reference = session.source_reference
    return provider, session, finished, source_reference


def _tree_signature(path: Path) -> tuple[tuple[str, int, int, int, int, str], ...]:
    root = path.absolute()
    rows: list[tuple[str, int, int, int, int, str]] = []
    paths: tuple[Path, ...]
    if root.is_file():
        paths = (root,)
    else:
        collected: list[Path] = []
        pending = [root]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
            for entry in entries:
                candidate = Path(entry.path)
                metadata = candidate.lstat()
                if candidate.is_symlink() or int(getattr(metadata, "st_file_attributes", 0)) & 0x400:
                    raise AssertionError(f"synthetic fixture unexpectedly contains reparse path: {candidate}")
                if candidate.is_dir():
                    pending.append(candidate)
                elif candidate.is_file():
                    collected.append(candidate)
                else:
                    raise AssertionError(f"synthetic fixture has non-regular path: {candidate}")
        paths = tuple(sorted(collected))
    for candidate in paths:
        metadata = candidate.lstat()
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        rows.append(
            (
                str(candidate),
                int(metadata.st_size),
                int(metadata.st_mtime_ns),
                int(metadata.st_dev),
                int(metadata.st_ino),
                digest.hexdigest(),
            )
        )
    return tuple(rows)


def _create_synthetic_junction(link: Path, target: Path) -> subprocess.CompletedProcess[str]:
    if os.name != "nt":
        raise RuntimeError("synthetic junction helper is Windows-only")
    return subprocess.run(
        [
            os.environ.get("COMSPEC", "cmd.exe"),
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
        timeout=20,
    )


def _child_source() -> str:
    return r'''
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import unquote, urlsplit

from data_module.daily_market_monthly_revenue_read_session_v1 import DailyMarketMonthlyRevenueReadSessionV1
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider

database = Path(sys.argv[1]).resolve(strict=True)
output_root = Path(sys.argv[2]).resolve(strict=True)
operation_root = Path(sys.argv[3]).absolute()
reference_text = Path(sys.argv[4]).read_text(encoding="utf-8")
real_connect = sqlite3.connect
opened_paths = []

def guarded_connect(target, *args, **kwargs):
    raw = str(target)
    candidate = raw
    if raw.startswith("file:"):
        parsed = urlsplit(raw)
        if parsed.netloc not in {"", "localhost"}:
            raise AssertionError("remote SQLite URI is forbidden")
        candidate = unquote(parsed.path)
        if os.name == "nt" and len(candidate) >= 3 and candidate[0] == "/" and candidate[2] == ":":
            candidate = candidate[1:]
    try:
        resolved = Path(candidate).resolve(strict=False)
    except (OSError, ValueError):
        resolved = Path(candidate)
    if resolved == database:
        raise AssertionError("exact reopen attempted to SQLite-open the original database")
    opened_paths.append(str(resolved))
    return real_connect(target, *args, **kwargs)

sqlite3.connect = guarded_connect
provider = RecommendationCurrentFundamentalProvider(
    db_file=database,
    output_root=output_root,
    monthly_source_root=output_root,
)
session = DailyMarketMonthlyRevenueReadSessionV1.open_exact(
    provider,
    snapshot_root=operation_root,
    source_reference=reference_text,
)
for start in range(0, len(session.declared_stock_codes), 16):
    session.load_batch(session.declared_stock_codes[start : start + 16])
finished = session.finish()
reopened_reference = session.source_reference
wal_probe_row = None
wal_binding = None
if len(sys.argv) > 5 and sys.argv[5] == "verify-wal":
    wal_attempt = session._snapshot_session._attempt
    wal_reader_uri = wal_attempt.reader_database_path.as_uri() + "?mode=ro"
    wal_probe = sqlite3.connect(wal_reader_uri, uri=True)
    try:
        wal_probe_row = wal_probe.execute(
            "SELECT stock_code FROM synthetic_wal_probe"
        ).fetchone()
    finally:
        wal_probe.close()
    wal_binding = {
        "sqlite_journal_mode": wal_attempt.sqlite_journal_mode,
        "wal_sidecar_state": wal_attempt.wal_sidecar_state,
        "captured_files": [item.to_dict() for item in wal_attempt.captured_files],
    }
print(json.dumps({
    "pid": os.getpid(),
    "parent_pid": os.getppid(),
    "session_identity_sha256": finished.session_identity_sha256,
    "finished_reader_session_id": finished.finished_reader_session_id,
    "source_clock_identity_sha256": finished.source_clock.identity_sha256,
    "source_content_identity_sha256": finished.source_clock.source_content_identity_sha256,
    "fact_identity_by_stock": [[fact.stock_code, fact.identity_sha256] for fact in finished.facts],
    "facts": [fact.to_dict() for fact in finished.facts],
    "fact_state_counts": [list(item) for item in finished.fact_state_counts],
    "availability_status": finished.source_clock.availability_status,
    "source_scope": finished.source_clock.source_scope,
    "historical_pit_eligible": finished.source_clock.historical_pit_eligible,
    "formal_pit_eligible": finished.source_clock.formal_pit_eligible,
    "closed": session.closed,
    "snapshot_id": session.snapshot_id,
    "snapshot_root": str(session._snapshot_session.snapshot_root),
    "reference_identity_sha256": reopened_reference.identity_sha256,
    "opened_sqlite_paths": opened_paths,
    "wal_probe_row": wal_probe_row,
    "wal_binding": wal_binding,
}, sort_keys=True, separators=(",", ":")))
'''


def _child_archived_source() -> str:
    return r'''
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import unquote, urlsplit

from data_module.daily_market_monthly_revenue_read_session_v1 import DailyMarketMonthlyRevenueReadSessionV1
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider

database = Path(sys.argv[1]).absolute()
output_root = Path(sys.argv[2]).absolute()
operation_root = Path(sys.argv[3]).absolute()
reference_text = Path(sys.argv[4]).read_text(encoding="utf-8")
real_connect = sqlite3.connect
opened_paths = []

def normalized_path(raw):
    candidate = raw
    if raw.startswith("file:"):
        parsed = urlsplit(raw)
        if parsed.netloc not in {"", "localhost"}:
            raise AssertionError("remote SQLite URI is forbidden")
        candidate = unquote(parsed.path)
        if os.name == "nt" and len(candidate) >= 3 and candidate[0] == "/" and candidate[2] == ":":
            candidate = candidate[1:]
    return Path(candidate).absolute()

def guarded_connect(target, *args, **kwargs):
    actual = normalized_path(str(target))
    if os.path.normcase(str(actual)) == os.path.normcase(str(database)):
        raise AssertionError("archived exact reopen attempted to open the original database")
    opened_paths.append(str(actual))
    return real_connect(target, *args, **kwargs)

sqlite3.connect = guarded_connect
provider = RecommendationCurrentFundamentalProvider(
    db_file=database,
    output_root=output_root,
    monthly_source_root=output_root,
)
session = DailyMarketMonthlyRevenueReadSessionV1.open_exact_archived(
    provider,
    snapshot_root=operation_root,
    source_reference=reference_text,
)
for start in range(0, len(session.declared_stock_codes), 16):
    session.load_batch(session.declared_stock_codes[start : start + 16])
finished = session.finish()
reference = session.source_reference
operation_reader = Path(session.reader_database_path).absolute()
print(json.dumps({
    "pid": os.getpid(),
    "parent_pid": os.getppid(),
    "session_identity_sha256": finished.session_identity_sha256,
    "finished_reader_session_id": finished.finished_reader_session_id,
    "source_clock_identity_sha256": finished.source_clock.identity_sha256,
    "source_content_identity_sha256": finished.source_clock.source_content_identity_sha256,
    "fact_identity_by_stock": [[fact.stock_code, fact.identity_sha256] for fact in finished.facts],
    "facts": [fact.to_dict() for fact in finished.facts],
    "fact_state_counts": [list(item) for item in finished.fact_state_counts],
    "availability_status": finished.source_clock.availability_status,
    "source_scope": finished.source_clock.source_scope,
    "historical_pit_eligible": finished.source_clock.historical_pit_eligible,
    "formal_pit_eligible": finished.source_clock.formal_pit_eligible,
    "closed": session.closed,
    "operation_snapshot_id": session.snapshot_id,
    "operation_reader_database_path": str(operation_reader),
    "source_reference_identity_sha256": reference.identity_sha256,
    "opened_sqlite_paths": opened_paths,
}, sort_keys=True, separators=(",", ":")))
'''


def test_fresh_process_reopens_exact_saved_source_and_reissues_operation(
    tmp_path: Path,
) -> None:
    provider, original_session, original, source_reference = _finish_source(
        tmp_path / "case"
    )
    finished_manifest_path = (
        original_session._snapshot_session.snapshot_root / "finished_source_clock.json"
    )
    manifest_bytes = finished_manifest_path.read_bytes()
    manifest_payload = json.loads(manifest_bytes)
    assert source_reference.snapshot_reference.finished_manifest_sha256 == (
        hashlib.sha256(manifest_bytes).hexdigest()
    )
    assert source_reference.snapshot_reference.finished_manifest_sha256 != (
        manifest_payload["manifest_sha256"]
    )
    reference_json = source_reference.to_json()
    decoded = DailyMarketMonthlyRevenueSourceReferenceV1.from_json(reference_json)
    assert decoded == source_reference
    original_snapshot_root = original_session._snapshot_session.snapshot_root
    database_root = provider.db_file.parent
    external_source_root = provider.monthly_source_root
    before_snapshot = _tree_signature(original_snapshot_root)
    before_database_root = _tree_signature(database_root)
    before_external_root = _tree_signature(external_source_root)
    reference_path = tmp_path / "source_reference.json"
    reference_path.write_text(reference_json, encoding="utf-8")
    operation_root = tmp_path / "fresh_operation"
    report_path = tmp_path / "child_report.json"
    child_env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PYTHONPATH"}
    }
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    child = subprocess.Popen(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            _child_source(),
            str(provider.db_file),
            str(provider.output_root),
            str(operation_root),
            str(reference_path),
        ],
        cwd=Path.cwd(),
        env=child_env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    launched_child_pid = child.pid
    try:
        try:
            child_stdout, child_stderr = child.communicate(input="", timeout=120)
        except subprocess.TimeoutExpired as timeout_error:
            child.terminate()
            try:
                child_stdout, child_stderr = child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                try:
                    child_stdout, child_stderr = child.communicate(timeout=5)
                except subprocess.TimeoutExpired as cleanup_error:
                    raise AssertionError(
                        "exact reopen child remained alive after bounded kill"
                    ) from cleanup_error
            raise AssertionError(
                "exact reopen child exceeded its 120 second deadline; "
                f"stdout={child_stdout!r}; stderr={child_stderr!r}"
            ) from timeout_error
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired as cleanup_error:
                    raise AssertionError(
                        "exact reopen child cleanup exceeded its bounded deadline"
                    ) from cleanup_error
    (tmp_path / "child_stdout.txt").write_text(child_stdout, encoding="utf-8")
    (tmp_path / "child_stderr.txt").write_text(child_stderr, encoding="utf-8")
    assert child.returncode == 0, child_stderr or child_stdout
    report_line = child_stdout.strip().splitlines()[-1]
    report = json.loads(report_line)
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")

    assert type(report["pid"]) is int
    assert report["pid"] != os.getpid()
    assert report["pid"] != launched_child_pid
    assert report["parent_pid"] == launched_child_pid
    assert report["session_identity_sha256"] != original.session_identity_sha256
    assert report["finished_reader_session_id"] != original.finished_reader_session_id
    assert (
        report["source_clock_identity_sha256"]
        != source_reference.snapshot_reference.source_clock_identity_sha256
    )
    assert report["source_content_identity_sha256"] == source_reference.source_content_identity_sha256
    assert report["fact_identity_by_stock"] == [list(item) for item in source_reference.fact_identity_by_stock]
    assert report["facts"] == [fact.to_dict() for fact in original.facts]
    assert report["fact_state_counts"] == [list(item) for item in source_reference.fact_state_counts]
    assert report["availability_status"] == "unknown"
    assert report["source_scope"] == "current_observed_only"
    assert report["historical_pit_eligible"] is False
    assert report["formal_pit_eligible"] is False
    assert report["closed"] is True
    assert report["snapshot_root"] != str(original_snapshot_root)
    assert report["snapshot_id"] != original_session.snapshot_id
    assert report["reference_identity_sha256"] != source_reference.identity_sha256
    assert Path(report["snapshot_root"]) == operation_root / report["snapshot_id"]
    assert report["opened_sqlite_paths"]
    original_database = provider.db_file.resolve(strict=True)
    opened_sqlite_paths = tuple(
        Path(path).resolve(strict=False) for path in report["opened_sqlite_paths"]
    )
    expected_reader_database = (
        Path(report["snapshot_root"]) / "reader" / provider.db_file.name
    ).resolve(strict=True)
    assert opened_sqlite_paths == (expected_reader_database,)
    assert all(path != original_database for path in opened_sqlite_paths)
    after_snapshot = _tree_signature(original_snapshot_root)
    after_database_root = _tree_signature(database_root)
    after_external_root = _tree_signature(external_source_root)
    inventory_receipt = {
        "source_reference_identity_sha256": source_reference.identity_sha256,
        "source_content_identity_sha256": source_reference.source_content_identity_sha256,
        "child_pid": report["pid"],
        "launcher_pid": launched_child_pid,
        "child_parent_pid": report["parent_pid"],
        "saved_snapshot": {
            "root": str(original_snapshot_root),
            "before": [list(row) for row in before_snapshot],
            "after": [list(row) for row in after_snapshot],
            "unchanged": before_snapshot == after_snapshot,
        },
        "original_database_root": {
            "root": str(database_root),
            "before": [list(row) for row in before_database_root],
            "after": [list(row) for row in after_database_root],
            "unchanged": before_database_root == after_database_root,
        },
        "monthly_capture_root": {
            "root": str(external_source_root),
            "before": [list(row) for row in before_external_root],
            "after": [list(row) for row in after_external_root],
            "unchanged": before_external_root == after_external_root,
        },
    }
    (tmp_path / "source_inventory_receipt.json").write_text(
        json.dumps(inventory_receipt, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    assert before_snapshot == after_snapshot
    assert before_database_root == after_database_root
    assert before_external_root == after_external_root


def test_exact_reopen_rejects_cutoff_or_declared_cohort_mismatch_before_copy(
    tmp_path: Path,
) -> None:
    provider, session, _finished, reference = _finish_source(tmp_path / "case")
    wrong_cutoff = datetime(2026, 10, 4, 2, 0, tzinfo=CUTOFF.tzinfo)
    with pytest.raises(FundamentalReadSnapshotError, match="exact_cutoff_mismatch"):
        FundamentalReadSnapshotSession.open_exact(
            provider,
            snapshot_root=tmp_path / "wrong_cutoff_operation",
            source_reference=reference.snapshot_reference,
            stock_codes=reference.declared_stock_codes,
            cutoff_at=wrong_cutoff,
        )
    with pytest.raises(FundamentalReadSnapshotError, match="exact_declared_codes_mismatch"):
        FundamentalReadSnapshotSession.open_exact(
            provider,
            snapshot_root=tmp_path / "wrong_codes_operation",
            source_reference=reference.snapshot_reference,
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
        )
    assert not (tmp_path / "wrong_cutoff_operation").exists()
    assert not (tmp_path / "wrong_codes_operation").exists()
    assert session.closed


def test_exact_reopen_rejects_mutated_saved_capture_before_sqlite_open(
    tmp_path: Path,
) -> None:
    provider, session, _finished, reference = _finish_source(tmp_path / "case")
    binding = session._snapshot_session._attempt
    captured_main = binding.snapshot_root / "captured" / provider.db_file.name
    original_bytes = captured_main.read_bytes()
    captured_main.chmod(0o600)
    captured_main.write_bytes(original_bytes[:-1] + bytes([original_bytes[-1] ^ 1]))
    with pytest.raises(FundamentalReadSnapshotError, match="captured_copy_changed|capture_manifest|source_snapshot"):
        FundamentalReadSnapshotSession.open_exact(
            provider,
            snapshot_root=tmp_path / "tampered_operation",
            source_reference=reference.snapshot_reference,
            stock_codes=reference.declared_stock_codes,
            cutoff_at=CUTOFF,
        )
    assert not (tmp_path / "tampered_operation").exists()


def test_exact_reopen_rejects_changed_raw_capture_bytes(
    tmp_path: Path,
) -> None:
    provider, _session, _finished, reference = _finish_source(tmp_path / "case")
    html_path = (
        provider.monthly_source_root
        / "monthly_revenue_mops_snapshots"
        / "raw_html"
        / "twse_2026-04.html"
    )
    original = html_path.read_bytes()
    html_path.write_bytes(original + b"\n<!-- changed -->\n")
    with pytest.raises(FundamentalReadSnapshotError, match="capture_pin_changed"):
        FundamentalReadSnapshotSession.open_exact(
            provider,
            snapshot_root=tmp_path / "changed_capture_operation",
            source_reference=reference.snapshot_reference,
            stock_codes=reference.declared_stock_codes,
            cutoff_at=CUTOFF,
        )
    assert not (tmp_path / "changed_capture_operation").exists()


def test_reference_decoder_checks_canonical_bytes_but_does_not_self_qualify(
    tmp_path: Path,
) -> None:
    provider, session, _finished, reference = _finish_source(tmp_path / "case")
    encoded = reference.to_json()
    decoded = DailyMarketMonthlyRevenueSourceReferenceV1.from_json(encoded)
    assert decoded.identity_sha256 == reference.identity_sha256
    assert session.finished
    assert decoded.snapshot_reference.identity_sha256 == reference.snapshot_reference.identity_sha256
    with pytest.raises(ValueError, match="canonical"):
        DailyMarketMonthlyRevenueSourceReferenceV1.from_json(encoded.replace(",", ", ", 1))
    forged = json.loads(encoded)
    forged["source_content_identity_sha256"] = "0" * 64
    body = dict(forged)
    body.pop("identity_sha256")
    forged["identity_sha256"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    forged_reference = DailyMarketMonthlyRevenueSourceReferenceV1.from_json(
        json.dumps(forged, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    assert forged_reference != reference
    exact_session = DailyMarketMonthlyRevenueReadSessionV1.open_exact(
        provider,
        snapshot_root=tmp_path / "forged_operation",
        source_reference=forged_reference,
    )
    for start in range(0, len(exact_session.declared_stock_codes), 16):
        exact_session.load_batch(exact_session.declared_stock_codes[start : start + 16])
    with pytest.raises(
        DailyMarketMonthlyRevenueReadSessionError,
        match="monthly_revenue_exact_reopen_fact_ledger_mismatch",
    ):
        exact_session.finish()
    assert exact_session.closed


def test_exact_reopen_reads_uncheckpointed_wal_from_private_copy_without_source_changes(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "wal_exact_reopen"
    provider = _seed_provider(case_root / "provider")
    writer = sqlite3.connect(provider.db_file)
    try:
        journal_mode = str(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        assert journal_mode == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        main_path = provider.db_file
        main_sha_before_uncheckpointed_write = hashlib.sha256(main_path.read_bytes()).hexdigest()
        writer.execute("CREATE TABLE synthetic_wal_probe(stock_code TEXT NOT NULL)")
        writer.execute(
            "INSERT INTO synthetic_wal_probe(stock_code) VALUES(?)", ("9999",)
        )
        writer.commit()
        assert hashlib.sha256(main_path.read_bytes()).hexdigest() == (
            main_sha_before_uncheckpointed_write
        )
        wal_path = Path(f"{provider.db_file}-wal")
        shm_path = Path(f"{provider.db_file}-shm")
        assert wal_path.is_file() and wal_path.stat().st_size > 32
        assert shm_path.is_file()
        assert writer.execute(
            "SELECT stock_code FROM synthetic_wal_probe"
        ).fetchone() == ("9999",)

        original_session = DailyMarketMonthlyRevenueReadSessionV1.open(
            provider,
            snapshot_root=case_root / "saved_snapshots",
            stock_codes=("1101", "2330"),
            cutoff_at=CUTOFF,
        )
        original_session.load_batch(("1101", "2330"))
        original = original_session.finish()
        source_reference = original_session.source_reference
        original_binding = original_session._snapshot_session._attempt
        assert original_binding.sqlite_journal_mode == "wal"
        assert original_binding.wal_sidecar_state == "complete"
        assert {item.role for item in original_binding.captured_files} == {
            "sqlite_main",
            "sqlite_wal",
            "sqlite_shm",
        }
        assert original_binding.source_file_pins_start == (
            original_binding.source_file_pins_after_copy
        )
        assert original.source_clock.snapshot_binding.source_file_pins_start == (
            original.source_clock.snapshot_binding.source_file_pins_finish
        )

        saved_snapshot_root = original_session._snapshot_session.snapshot_root
        before_snapshot = _tree_signature(saved_snapshot_root)
        before_database_root = _tree_signature(provider.db_file.parent)
        before_capture_root = _tree_signature(provider.monthly_source_root)
        reference_path = case_root / "source_reference.json"
        reference_path.write_text(source_reference.to_json(), encoding="utf-8")
        operation_root = case_root / "fresh_wal_operation"
        child = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                "-c",
                _child_source(),
                str(provider.db_file),
                str(provider.output_root),
                str(operation_root),
                str(reference_path),
                "verify-wal",
            ],
            cwd=Path.cwd(),
            env={
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PYTHONPATH"}
            }
            | {"PYTHONDONTWRITEBYTECODE": "1"},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        child_pid = child.pid
        try:
            try:
                stdout, stderr = child.communicate(input="", timeout=120)
            except subprocess.TimeoutExpired as timeout_error:
                child.terminate()
                try:
                    stdout, stderr = child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    stdout, stderr = child.communicate(timeout=5)
                raise AssertionError(
                    f"WAL exact reopen 超過 120 秒：stdout={stdout!r}; stderr={stderr!r}"
                ) from timeout_error
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=5)

        (case_root / "wal_child_stdout.txt").write_text(stdout, encoding="utf-8")
        (case_root / "wal_child_stderr.txt").write_text(stderr, encoding="utf-8")
        assert child.returncode == 0, stderr or stdout
        report = json.loads(stdout.strip().splitlines()[-1])
        report_path = case_root / "wal_exact_reopen_receipt.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        assert report["pid"] != os.getpid()
        assert report["parent_pid"] == child_pid
        assert report["facts"] == [fact.to_dict() for fact in original.facts]
        assert report["fact_identity_by_stock"] == [
            list(item) for item in source_reference.fact_identity_by_stock
        ]
        assert report["availability_status"] == "unknown"
        assert report["source_scope"] == "current_observed_only"
        assert report["historical_pit_eligible"] is False
        assert report["formal_pit_eligible"] is False
        assert report["wal_probe_row"] == ["9999"]
        assert report["wal_binding"]["sqlite_journal_mode"] == "wal"
        assert report["wal_binding"]["wal_sidecar_state"] == "complete"
        assert {item["role"] for item in report["wal_binding"]["captured_files"]} == {
            "sqlite_main",
            "sqlite_wal",
            "sqlite_shm",
        }
        original_role_sha = {
            item.role: item.sha256 for item in original_binding.captured_files
        }
        reopened_role_sha = {
            item["role"]: item["sha256"]
            for item in report["wal_binding"]["captured_files"]
        }
        assert reopened_role_sha == original_role_sha
        expected_reader = (
            Path(report["snapshot_root"]) / "reader" / provider.db_file.name
        ).resolve(strict=True)
        opened_paths = tuple(
            Path(value).resolve(strict=False) for value in report["opened_sqlite_paths"]
        )
        assert len(opened_paths) == 2
        assert all(path == expected_reader for path in opened_paths)
        assert all(path != provider.db_file.resolve(strict=True) for path in opened_paths)

        after_snapshot = _tree_signature(saved_snapshot_root)
        after_database_root = _tree_signature(provider.db_file.parent)
        after_capture_root = _tree_signature(provider.monthly_source_root)
        receipt = {
            "status": "passed",
            "formal_producer_invoked": False,
            "synthetic_fixture_seeded": True,
            "source_kind": "合成 SQLite 與既有 parser fixture，非正式來源",
            "child_pid": report["pid"],
            "launcher_pid": child_pid,
            "uncheckpointed_main_sha256_before_write": main_sha_before_uncheckpointed_write,
            "uncheckpointed_main_sha256_after_write": hashlib.sha256(
                main_path.read_bytes()
            ).hexdigest(),
            "original_source_pins": {
                "start": [pin.to_dict() for pin in original_binding.source_file_pins_start],
                "after_copy": [
                    pin.to_dict() for pin in original_binding.source_file_pins_after_copy
                ],
                "finish": [
                    pin.to_dict()
                    for pin in original.source_clock.snapshot_binding.source_file_pins_finish
                ],
            },
            "saved_captured_files": [item.to_dict() for item in original_binding.captured_files],
            "sqlite_probe_row": report["wal_probe_row"],
            "snapshot_wal_state": report["wal_binding"],
            "opened_sqlite_paths": list(report["opened_sqlite_paths"]),
            "saved_snapshot_inventory_before": [list(row) for row in before_snapshot],
            "saved_snapshot_inventory_after": [list(row) for row in after_snapshot],
            "original_database_inventory_before": [
                list(row) for row in before_database_root
            ],
            "original_database_inventory_after": [
                list(row) for row in after_database_root
            ],
            "raw_capture_inventory_before": [list(row) for row in before_capture_root],
            "raw_capture_inventory_after": [list(row) for row in after_capture_root],
            "saved_snapshot_unchanged": before_snapshot == after_snapshot,
            "original_database_and_sidecars_unchanged": (
                before_database_root == after_database_root
            ),
            "raw_capture_unchanged": before_capture_root == after_capture_root,
        }
        (case_root / "wal_source_inventory_receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        assert before_snapshot == after_snapshot
        assert before_database_root == after_database_root
        assert before_capture_root == after_capture_root
    finally:
        writer.close()


def _run_archived_child(
    *,
    provider: RecommendationCurrentFundamentalProvider,
    operation_root: Path,
    reference_path: Path,
    receipt_root: Path,
) -> dict[str, object]:
    receipt_root.mkdir(parents=True, exist_ok=False)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PYTHONPATH"}
    } | {"PYTHONDONTWRITEBYTECODE": "1"}
    process = subprocess.Popen(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            _child_archived_source(),
            str(provider.db_file),
            str(provider.output_root),
            str(operation_root),
            str(reference_path),
        ],
        cwd=Path.cwd(),
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    launcher_pid = process.pid
    try:
        launcher_parent_pid = psutil.Process(launcher_pid).ppid()
    except psutil.NoSuchProcess as exc:
        raise AssertionError("archived exact launcher 在啟動時即消失") from exc
    try:
        stdout, stderr = process.communicate(input="", timeout=120)
    except subprocess.TimeoutExpired as timeout_error:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        (receipt_root / "child_stdout.txt").write_text(stdout, encoding="utf-8")
        (receipt_root / "child_stderr.txt").write_text(stderr, encoding="utf-8")
        raise AssertionError(
            f"archived exact reopen 超過 120 秒：stdout={stdout!r}; stderr={stderr!r}"
        ) from timeout_error
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
    (receipt_root / "child_stdout.txt").write_text(stdout, encoding="utf-8")
    (receipt_root / "child_stderr.txt").write_text(stderr, encoding="utf-8")
    if process.returncode != 0:
        raise AssertionError(
            f"archived exact child exit={process.returncode}: {stderr or stdout}"
        )
    report = json.loads(stdout.strip().splitlines()[-1])
    report["launcher_pid"] = launcher_pid
    report["launcher_parent_pid"] = launcher_parent_pid
    (receipt_root / "child_receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return report


def test_archived_exact_reopen_survives_live_source_update_and_deletion_in_fresh_process(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "archived_exact_reopen"
    provider, original_session, original, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    saved_snapshot_root = original_session._snapshot_session.snapshot_root
    archive_parent = case_root / "raw_archives"
    archived_reference = original_session.archive_source(archive_parent)
    assert type(archived_reference) is DailyMarketMonthlyRevenueSourceReferenceV2
    encoded_reference = archived_reference.to_json()
    assert DailyMarketMonthlyRevenueSourceReferenceV2.from_json(encoded_reference) == archived_reference
    assert archived_reference.source_scope == "current_observed_only"
    assert archived_reference.availability_status == "unknown"
    assert archived_reference.historical_pit_eligible is False
    assert archived_reference.formal_pit_eligible is False
    assert archived_reference.fact_identity_by_stock == tuple(
        (fact.stock_code, fact.identity_sha256) for fact in original.facts
    )

    source_reference_path = case_root / "archived_source_reference.json"
    source_reference_path.write_text(encoded_reference, encoding="utf-8")
    archive_root = Path(archived_reference.raw_archive_reference.raw_archive_root)
    source_snapshot_before = _tree_signature(saved_snapshot_root)
    raw_archive_before = _tree_signature(archive_root)
    database_path = provider.db_file
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "CREATE TABLE synthetic_live_after_archive (marker TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO synthetic_live_after_archive(marker) VALUES(?)", ("updated",)
        )
        connection.commit()
    finally:
        connection.close()
    for archived_file in archived_reference.raw_archive_reference.files:
        Path(archived_file.historical_pin.path).unlink()

    output_root = provider.output_root
    monthly_root = provider.monthly_source_root
    source_before_updated_reopen = _tree_signature(database_path.parent)
    snapshot_before_updated_reopen = _tree_signature(saved_snapshot_root)
    archive_before_updated_reopen = _tree_signature(archive_root)
    updated_report = _run_archived_child(
        provider=provider,
        operation_root=case_root / "updated_live_operation",
        reference_path=source_reference_path,
        receipt_root=case_root / "updated_live_child",
    )
    assert _tree_signature(database_path.parent) == source_before_updated_reopen
    assert _tree_signature(saved_snapshot_root) == snapshot_before_updated_reopen
    assert _tree_signature(archive_root) == archive_before_updated_reopen

    database_path.unlink()
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{database_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()
    source_before_deleted_reopen = _tree_signature(database_path.parent)
    snapshot_before_deleted_reopen = _tree_signature(saved_snapshot_root)
    archive_before_deleted_reopen = _tree_signature(archive_root)
    deleted_provider = RecommendationCurrentFundamentalProvider(
        db_file=database_path,
        output_root=output_root,
        monthly_source_root=monthly_root,
    )
    deleted_report = _run_archived_child(
        provider=deleted_provider,
        operation_root=case_root / "deleted_live_operation",
        reference_path=source_reference_path,
        receipt_root=case_root / "deleted_live_child",
    )
    assert _tree_signature(database_path.parent) == source_before_deleted_reopen
    assert _tree_signature(saved_snapshot_root) == snapshot_before_deleted_reopen
    assert _tree_signature(archive_root) == archive_before_deleted_reopen
    assert source_snapshot_before == snapshot_before_deleted_reopen
    assert raw_archive_before == archive_before_deleted_reopen

    for report, operation_root in (
        (updated_report, case_root / "updated_live_operation"),
        (deleted_report, case_root / "deleted_live_operation"),
    ):
        assert report["pid"] != os.getpid()
        if report["pid"] == report["launcher_pid"]:
            assert report["parent_pid"] == os.getpid()
            assert report["launcher_parent_pid"] == os.getpid()
        else:
            assert report["parent_pid"] == report["launcher_pid"]
            assert report["launcher_parent_pid"] == os.getpid()
        assert report["facts"] == [fact.to_dict() for fact in original.facts]
        assert report["fact_identity_by_stock"] == [
            list(item) for item in archived_reference.fact_identity_by_stock
        ]
        assert report["source_content_identity_sha256"] == (
            archived_reference.source_content_identity_sha256
        )
        assert report["source_clock_identity_sha256"] != original.source_clock.identity_sha256
        assert report["source_reference_identity_sha256"] == archived_reference.identity_sha256
        assert report["availability_status"] == "unknown"
        assert report["source_scope"] == "current_observed_only"
        assert report["historical_pit_eligible"] is False
        assert report["formal_pit_eligible"] is False
        assert report["closed"] is True
        assert report["operation_snapshot_id"] != archived_reference.snapshot_reference.snapshot_id
        opened_paths = tuple(Path(value).absolute() for value in report["opened_sqlite_paths"])
        operation_reader = Path(str(report["operation_reader_database_path"])).absolute()
        assert opened_paths == (operation_reader,)
        operation_reader.relative_to(operation_root.absolute())
        assert operation_reader.name == database_path.name
        assert operation_reader != database_path.absolute()


def test_archived_exact_reopen_survives_missing_historical_source_ancestor(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "archived_missing_ancestor"
    provider, original_session, original, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    reference = original_session.archive_source(case_root / "archives")
    reference_path = case_root / "source_reference.json"
    reference_path.write_text(reference.to_json(), encoding="utf-8")
    historical_root = provider.db_file.parent
    detached_root = case_root / "detached_historical_root"
    snapshot_root = original_session._snapshot_session.snapshot_root
    archive_root = Path(reference.raw_archive_reference.raw_archive_root)
    assert case_root.resolve(strict=True) in historical_root.resolve(strict=True).parents
    assert not detached_root.exists()
    historical_before = _tree_signature(historical_root)
    snapshot_before = _tree_signature(snapshot_root)
    archive_before = _tree_signature(archive_root)
    historical_root.rename(detached_root)
    assert not historical_root.exists()

    report = _run_archived_child(
        provider=RecommendationCurrentFundamentalProvider(
            db_file=provider.db_file,
            output_root=case_root / "isolated_operation_output",
            monthly_source_root=case_root / "isolated_operation_monthly",
        ),
        operation_root=case_root / "operation_after_source_ancestor_removed",
        reference_path=reference_path,
        receipt_root=case_root / "child_after_source_ancestor_removed",
    )
    assert not historical_root.exists()
    assert tuple(row[1:] for row in _tree_signature(detached_root)) == tuple(
        row[1:] for row in historical_before
    )
    assert _tree_signature(snapshot_root) == snapshot_before
    assert _tree_signature(archive_root) == archive_before
    assert report["facts"] == [fact.to_dict() for fact in original.facts]
    assert report["source_content_identity_sha256"] == reference.source_content_identity_sha256
    assert report["source_reference_identity_sha256"] == reference.identity_sha256
    assert report["availability_status"] == "unknown"
    assert report["source_scope"] == "current_observed_only"
    assert report["historical_pit_eligible"] is False
    assert report["formal_pit_eligible"] is False
    opened = tuple(Path(value).absolute() for value in report["opened_sqlite_paths"])
    assert len(opened) == 1
    opened[0].relative_to((case_root / "operation_after_source_ancestor_removed").absolute())
    assert opened[0] != provider.db_file.absolute()


def test_archived_finish_does_not_resolve_or_lstat_historical_source_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_root = tmp_path / "archived_finish_historical_path_guard"
    provider, original_session, original, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    archive = original_session.archive_source(case_root / "archives")
    archive_reference = archive.raw_archive_reference
    operation_root = case_root / "operation"
    archived_session = FundamentalReadSnapshotSession.open_exact_archived(
        provider,
        snapshot_root=operation_root,
        source_reference=archive.snapshot_reference,
        raw_archive_reference=archive_reference,
        stock_codes=archive.declared_stock_codes,
        cutoff_at=CUTOFF,
    )
    archived_session.load_batch(archive.declared_stock_codes)

    historical_db = Path(provider.db_file)
    historical_db_root = historical_db.parent
    historical_capture_root = Path(archive_reference.original_monthly_source_root)
    forbidden_exact = {
        os.path.normcase(os.path.abspath(os.fspath(historical_db))),
        *(
            os.path.normcase(os.path.abspath(f"{historical_db}{suffix}"))
            for suffix in ("-wal", "-shm", "-journal")
        ),
    }
    forbidden_roots = (
        os.path.normcase(os.path.abspath(os.fspath(historical_db_root))),
        os.path.normcase(os.path.abspath(os.fspath(historical_capture_root))),
    )
    forbidden_exact.update(
        os.path.normcase(os.path.abspath(os.fspath(item.historical_pin.path)))
        for item in archive_reference.files
    )
    attempted: list[str] = []
    real_resolve = Path.resolve
    real_lstat = Path.lstat

    def is_historical(path: Path) -> bool:
        candidate = os.path.normcase(os.path.abspath(os.fspath(path)))
        if candidate in forbidden_exact:
            return True
        return any(
            candidate == root or candidate.startswith(root + os.sep)
            for root in forbidden_roots
        )

    def guarded_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if is_historical(path):
            attempted.append(f"resolve:{path}")
            raise AssertionError(f"archived finish resolved historical source path: {path}")
        return real_resolve(path, *args, **kwargs)

    def guarded_lstat(path: Path) -> os.stat_result:
        if is_historical(path):
            attempted.append(f"lstat:{path}")
            raise AssertionError(f"archived finish inspected historical source path: {path}")
        return real_lstat(path)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "resolve", guarded_resolve)
        scoped.setattr(Path, "lstat", guarded_lstat)
        for source_root in (historical_db_root, historical_capture_root):
            for protected_root in (
                archive.snapshot_reference.snapshot_root,
                archive_reference.raw_archive_root,
                str(operation_root),
            ):
                source_path = Path(os.path.abspath(source_root))
                protected_path = Path(os.path.abspath(protected_root))
                assert source_path != protected_path
                assert source_path not in protected_path.parents
                assert protected_path not in source_path.parents
        with pytest.raises(AssertionError, match="resolved historical source"):
            historical_db.resolve()
        with pytest.raises(AssertionError, match="inspected historical source"):
            historical_db.lstat()
        assert len(attempted) == 2
        attempted.clear()
        finished = archived_session.finish()

    assert attempted == []
    assert archived_session.closed is True
    assert (
        finished.source_clock.source_content_identity_sha256
        == original.source_clock.source_content_identity_sha256
    )
    assert finished.processed_stock_codes == original.processed_stock_codes


def test_archived_exact_open_cancelled_before_open_does_not_create_operation_or_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_root = tmp_path / "archived_cancel_before_open"
    provider, original_session, original, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    archive = original_session.archive_source(case_root / "archives")
    operation_root = case_root / "cancelled_operation"
    saved_snapshot_root = original_session._snapshot_session.snapshot_root
    archive_root = Path(archive.raw_archive_reference.raw_archive_root)
    source_before = _tree_signature(provider.db_file.parent)
    snapshot_before = _tree_signature(saved_snapshot_root)
    archive_before = _tree_signature(archive_root)
    attempted_sqlite_opens: list[object] = []

    def reject_sqlite_open(target: object, *args: object, **kwargs: object) -> None:
        attempted_sqlite_opens.append(target)
        raise AssertionError("預取消的 archived open 不得建立 SQLite 連線")

    monkeypatch.setattr(snapshot_module.sqlite3, "connect", reject_sqlite_open)
    with pytest.raises(
        DailyMarketMonthlyRevenueReadCancelled,
        match="monthly_revenue_read_cancelled_before_archived_exact_open",
    ):
        DailyMarketMonthlyRevenueReadSessionV1.open_exact_archived(
            provider,
            snapshot_root=operation_root,
            source_reference=archive,
            cancel_callback=lambda: True,
        )

    assert attempted_sqlite_opens == []
    assert not operation_root.exists()
    assert _tree_signature(provider.db_file.parent) == source_before
    assert _tree_signature(saved_snapshot_root) == snapshot_before
    assert _tree_signature(archive_root) == archive_before
    assert original_session.finished is True


def test_archived_revenue_finish_cancelled_after_snapshot_finish_closes_without_publishing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_root = tmp_path / "archived_cancel_during_finish"
    provider, original_session, _original, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    archive = original_session.archive_source(case_root / "archives")
    saved_snapshot_root = original_session._snapshot_session.snapshot_root
    archive_root = Path(archive.raw_archive_reference.raw_archive_root)
    source_before = _tree_signature(provider.db_file.parent)
    snapshot_before = _tree_signature(saved_snapshot_root)
    archive_before = _tree_signature(archive_root)
    operation_root = case_root / "cancelled_operation"
    cancel_state = {"requested": False}
    session = DailyMarketMonthlyRevenueReadSessionV1.open_exact_archived(
        provider,
        snapshot_root=operation_root,
        source_reference=archive,
        cancel_callback=lambda: cancel_state["requested"],
    )
    session.load_batch(session.declared_stock_codes)
    assert session.finished is False
    assert session.closed is False

    original_build_facts = DailyMarketMonthlyRevenueReadSessionV1._build_finished_facts

    def cancel_after_fact_projection(
        current_session: DailyMarketMonthlyRevenueReadSessionV1,
        results: tuple[CurrentMonthlyRevenueReadResult, ...],
        source_clock: FundamentalSnapshotSourceClock,
    ) -> tuple[MonthlyRevenueReadFactV1, ...]:
        facts = original_build_facts(current_session, results, source_clock)
        if current_session is session:
            cancel_state["requested"] = True
        return facts

    monkeypatch.setattr(
        DailyMarketMonthlyRevenueReadSessionV1,
        "_build_finished_facts",
        cancel_after_fact_projection,
    )
    with pytest.raises(
        DailyMarketMonthlyRevenueReadCancelled,
        match="monthly_revenue_read_cancelled",
    ):
        session.finish()

    assert cancel_state["requested"] is True
    assert session.finished is False
    assert session.closed is True
    assert session._snapshot_session.closed is True
    assert session._snapshot_session.source_reference is not None
    assert _tree_signature(provider.db_file.parent) == source_before
    assert _tree_signature(saved_snapshot_root) == snapshot_before
    assert _tree_signature(archive_root) == archive_before
    with pytest.raises(
        DailyMarketMonthlyRevenueReadSessionError,
        match="source_reference_requires_finished_session",
    ):
        _ = session.source_reference


def test_archived_snapshot_finish_cancelled_after_archive_verify_closes_without_issuing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_root = tmp_path / "archived_snapshot_finish_cancel_after_verify"
    provider, original_session, _original, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    archive = original_session.archive_source(case_root / "archives")
    saved_snapshot_root = original_session._snapshot_session.snapshot_root
    archive_root = Path(archive.raw_archive_reference.raw_archive_root)
    source_before = _tree_signature(provider.db_file.parent)
    snapshot_before = _tree_signature(saved_snapshot_root)
    archive_before = _tree_signature(archive_root)
    operation_root = case_root / "cancelled_operation"
    cancel_state = {"requested": False}
    session = DailyMarketMonthlyRevenueReadSessionV1.open_exact_archived(
        provider,
        snapshot_root=operation_root,
        source_reference=archive,
        cancel_callback=lambda: cancel_state["requested"],
    )
    session.load_batch(session.declared_stock_codes)
    assert session.finished is False
    assert session.closed is False

    original_verify = snapshot_module._verify_raw_archive_reference
    verified_calls: list[str] = []

    def cancel_after_archive_verification(*args: object, **kwargs: object) -> object:
        result = original_verify(*args, **kwargs)
        verified_calls.append("finish_archive_verification_returned")
        cancel_state["requested"] = True
        return result

    monkeypatch.setattr(
        snapshot_module,
        "_verify_raw_archive_reference",
        cancel_after_archive_verification,
    )
    with pytest.raises(
        FundamentalReadSnapshotCancelled,
        match="fundamental_snapshot_cancelled",
    ):
        session.finish()

    assert verified_calls == ["finish_archive_verification_returned"]
    assert cancel_state["requested"] is True
    assert session.finished is False
    assert session.closed is True
    assert session._snapshot_session.closed is True
    with pytest.raises(
        FundamentalReadSnapshotError,
        match="fundamental_snapshot_reference_requires_finished_session",
    ):
        _ = session._snapshot_session.source_reference
    with pytest.raises(
        DailyMarketMonthlyRevenueReadSessionError,
        match="source_reference_requires_finished_session",
    ):
        _ = session.source_reference
    assert _tree_signature(provider.db_file.parent) == source_before
    assert _tree_signature(saved_snapshot_root) == snapshot_before
    assert _tree_signature(archive_root) == archive_before


@pytest.mark.parametrize(
    ("role", "expected_marker"),
    (
        ("sqlite_wal", "raw_archive_source_changed_before_issue"),
        ("sqlite_shm", "raw_archive_source_changed_before_issue"),
        ("sqlite_rollback_journal", "raw_archive_source_changed_before_issue"),
        ("monthly_html", "raw_archive_capture_pin_changed"),
    ),
)
def test_raw_archive_rejects_late_source_mutation_before_reference_issue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    expected_marker: str,
) -> None:
    case_root = tmp_path / f"late_archive_mutation_{role}"
    provider, session, finished, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    source_clock = finished.source_clock
    if role == "monthly_html":
        target = Path(
            next(pin.path for pin in source_clock.capture_file_pins_start if pin.role == role)
        )
    else:
        suffix = {
            "sqlite_wal": "-wal",
            "sqlite_shm": "-shm",
            "sqlite_rollback_journal": "-journal",
        }[role]
        target = Path(f"{provider.db_file}{suffix}")
        assert not target.exists()

    real_write = snapshot_module._write_create_only_bytes
    injected = False

    def mutate_after_manifest(path: Path, payload: bytes) -> None:
        nonlocal injected
        real_write(path, payload)
        if path.name != "raw_source_archive.json" or injected:
            return
        if role == "monthly_html":
            target.write_bytes(target.read_bytes() + b"\nlate synthetic raw mutation\n")
        else:
            target.write_bytes(b"late synthetic sidecar appearance")
        injected = True

    monkeypatch.setattr(snapshot_module, "_write_create_only_bytes", mutate_after_manifest)
    with pytest.raises(DailyMarketMonthlyRevenueReadSessionError, match=expected_marker):
        session.archive_source(case_root / "archives")

    assert injected is True
    assert session.archived_source_reference is None


def test_archived_exact_reopen_survives_historical_source_ancestor_junction_retarget(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("此案例驗證 Windows junction 的 historical path 隔離")
    case_root = tmp_path / "archived_junction_ancestor"
    provider, original_session, original, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    reference = original_session.archive_source(case_root / "archives")
    reference_path = case_root / "source_reference.json"
    reference_path.write_text(reference.to_json(), encoding="utf-8")
    historical_root = provider.db_file.parent
    detached_root = case_root / "detached_historical_root"
    decoy_root = case_root / "retargeted_decoy_root"
    snapshot_root = original_session._snapshot_session.snapshot_root
    archive_root = Path(reference.raw_archive_reference.raw_archive_root)
    alternate_output = case_root / "isolated_operation_output"
    alternate_monthly = case_root / "isolated_operation_monthly"
    assert case_root.resolve(strict=True) in historical_root.resolve(strict=True).parents
    assert not detached_root.exists()
    assert not decoy_root.exists()
    historical_before = _tree_signature(historical_root)
    snapshot_before = _tree_signature(snapshot_root)
    archive_before = _tree_signature(archive_root)
    historical_root.rename(detached_root)
    decoy_root.mkdir(parents=True)
    (decoy_root / "decoy_marker.txt").write_text("synthetic decoy", encoding="utf-8")
    link_result = _create_synthetic_junction(historical_root, decoy_root)
    if link_result.returncode != 0:
        pytest.skip(
            "此 Windows 執行環境無法建立 synthetic junction："
            f"{link_result.stderr.strip() or link_result.stdout.strip()}"
        )
    try:
        junction_metadata = historical_root.lstat()
        assert int(getattr(junction_metadata, "st_file_attributes", 0)) & 0x400
        alternate_provider = RecommendationCurrentFundamentalProvider(
            db_file=provider.db_file,
            output_root=alternate_output,
            monthly_source_root=alternate_monthly,
        )
        report = _run_archived_child(
            provider=alternate_provider,
            operation_root=case_root / "operation_after_junction_retarget",
            reference_path=reference_path,
            receipt_root=case_root / "child_after_junction_retarget",
        )
        assert historical_root.resolve(strict=True) == decoy_root.resolve(strict=True)
        assert tuple(row[1:] for row in _tree_signature(detached_root)) == tuple(
            row[1:] for row in historical_before
        )
        assert _tree_signature(decoy_root) == (
            (str(decoy_root / "decoy_marker.txt"), len("synthetic decoy"),
             (decoy_root / "decoy_marker.txt").stat().st_mtime_ns,
             (decoy_root / "decoy_marker.txt").stat().st_dev,
             (decoy_root / "decoy_marker.txt").stat().st_ino,
             hashlib.sha256(b"synthetic decoy").hexdigest()),
        )
        assert _tree_signature(snapshot_root) == snapshot_before
        assert _tree_signature(archive_root) == archive_before
        assert report["facts"] == [fact.to_dict() for fact in original.facts]
        assert report["source_content_identity_sha256"] == reference.source_content_identity_sha256
        assert report["source_reference_identity_sha256"] == reference.identity_sha256
        assert report["availability_status"] == "unknown"
        assert report["source_scope"] == "current_observed_only"
        assert report["historical_pit_eligible"] is False
        assert report["formal_pit_eligible"] is False
        opened = tuple(Path(value).absolute() for value in report["opened_sqlite_paths"])
        assert len(opened) == 1
        opened[0].relative_to((case_root / "operation_after_junction_retarget").absolute())
        assert opened[0] != provider.db_file.absolute()
    finally:
        historical_root.rmdir()


def test_archived_exact_reopen_rejects_archive_root_junction_before_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("此案例驗證 Windows archive-root junction")
    case_root = tmp_path / "archive_root_junction"
    provider, original_session, _finished, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    reference = original_session.archive_source(case_root / "archives")
    archive_root = Path(reference.raw_archive_reference.raw_archive_root)
    moved_archive_root = case_root / "moved_archive_for_junction"
    assert case_root.resolve(strict=True) in archive_root.resolve(strict=True).parents
    assert not moved_archive_root.exists()
    archive_before = _tree_signature(archive_root)
    archive_root.rename(moved_archive_root)
    link_result = _create_synthetic_junction(archive_root, moved_archive_root)
    if link_result.returncode != 0:
        moved_archive_root.rename(archive_root)
        pytest.skip(
            "此 Windows 執行環境無法建立 synthetic archive junction："
            f"{link_result.stderr.strip() or link_result.stdout.strip()}"
        )
    connected: list[str] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connected.append(str(target))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    try:
        junction_metadata = archive_root.lstat()
        assert int(getattr(junction_metadata, "st_file_attributes", 0)) & 0x400
        with pytest.raises(FundamentalReadSnapshotError, match="reparse|junction"):
            FundamentalReadSnapshotSession.open_exact_archived(
                provider,
                snapshot_root=case_root / "operation_rejected_archive_junction",
                source_reference=reference.snapshot_reference,
                raw_archive_reference=reference.raw_archive_reference,
                stock_codes=reference.declared_stock_codes,
                cutoff_at=CUTOFF,
            )
        assert connected == []
        assert not (case_root / "operation_rejected_archive_junction").exists()
        assert tuple(row[1:] for row in _tree_signature(moved_archive_root)) == tuple(
            row[1:] for row in archive_before
        )
    finally:
        archive_root.rmdir()
        moved_archive_root.rename(archive_root)


def test_archived_exact_reopen_rejects_operation_root_junction_before_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("此案例驗證 Windows operation-root junction")
    case_root = tmp_path / "operation_root_junction"
    provider, original_session, _finished, _legacy_reference = _finish_source(
        case_root / "provider_case"
    )
    reference = original_session.archive_source(case_root / "archives")
    operation_target = case_root / "operation_target"
    operation_target.mkdir()
    operation_root = case_root / "operation_junction"
    assert case_root.resolve(strict=True) == operation_root.parent.resolve(strict=True)
    link_result = _create_synthetic_junction(operation_root, operation_target)
    if link_result.returncode != 0:
        pytest.skip(
            "此 Windows 執行環境無法建立 synthetic operation junction："
            f"{link_result.stderr.strip() or link_result.stdout.strip()}"
        )
    connected: list[str] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connected.append(str(target))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    try:
        junction_metadata = operation_root.lstat()
        assert int(getattr(junction_metadata, "st_file_attributes", 0)) & 0x400
        with pytest.raises(FundamentalReadSnapshotError, match="reparse|junction"):
            FundamentalReadSnapshotSession.open_exact_archived(
                provider,
                snapshot_root=operation_root,
                source_reference=reference.snapshot_reference,
                raw_archive_reference=reference.raw_archive_reference,
                stock_codes=reference.declared_stock_codes,
                cutoff_at=CUTOFF,
            )
        assert connected == []
        assert _tree_signature(operation_target) == ()
    finally:
        operation_root.rmdir()


def test_archived_exact_reopen_rejects_archive_tampering_before_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, original_session, _finished, _legacy_reference = _finish_source(
        tmp_path / "case"
    )
    reference = original_session.archive_source(tmp_path / "archives")
    archive_root = Path(reference.raw_archive_reference.raw_archive_root)
    archived_file = Path(reference.raw_archive_reference.files[0].relative_path)
    archived_file = Path(reference.raw_archive_reference.archived_monthly_source_root) / archived_file
    original_bytes = archived_file.read_bytes()
    original_mode = stat.S_IMODE(archived_file.stat().st_mode)
    archived_file.chmod(0o600)
    archived_file.write_bytes(original_bytes + b"\n tampered\n")
    connected: list[str] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connected.append(str(target))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    with pytest.raises(FundamentalReadSnapshotError, match="raw_archive_capture_bytes_changed"):
        FundamentalReadSnapshotSession.open_exact_archived(
            provider,
            snapshot_root=tmp_path / "rejected_operation",
            source_reference=reference.snapshot_reference,
            raw_archive_reference=reference.raw_archive_reference,
            stock_codes=reference.declared_stock_codes,
            cutoff_at=CUTOFF,
        )
    assert connected == []
    assert not (tmp_path / "rejected_operation").exists()
    archived_file.chmod(0o600)
    archived_file.write_bytes(original_bytes)
    archived_file.chmod(original_mode)

    manifest_path = archive_root / "raw_source_archive.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest_mode = stat.S_IMODE(manifest_path.stat().st_mode)
    manifest_path.chmod(0o600)
    manifest_path.write_bytes(manifest_bytes + b" ")
    with pytest.raises(FundamentalReadSnapshotError, match="raw_archive_manifest_mismatch"):
        FundamentalReadSnapshotSession.open_exact_archived(
            provider,
            snapshot_root=tmp_path / "rejected_manifest_operation",
            source_reference=reference.snapshot_reference,
            raw_archive_reference=reference.raw_archive_reference,
            stock_codes=reference.declared_stock_codes,
            cutoff_at=CUTOFF,
        )
    assert connected == []
    assert not (tmp_path / "rejected_manifest_operation").exists()
    manifest_path.chmod(0o600)
    manifest_path.write_bytes(manifest_bytes)
    manifest_path.chmod(manifest_mode)


def test_archived_exact_reopen_rejects_missing_manifest_or_capture_before_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, original_session, _finished, _legacy_reference = _finish_source(
        tmp_path / "case"
    )
    reference = original_session.archive_source(tmp_path / "archives")
    archive_root = Path(reference.raw_archive_reference.raw_archive_root)
    manifest_path = archive_root / "raw_source_archive.json"
    capture_path = (
        Path(reference.raw_archive_reference.archived_monthly_source_root)
        / reference.raw_archive_reference.files[0].relative_path
    )
    manifest_backup = manifest_path.with_name("raw_source_archive.saved")
    capture_backup = capture_path.with_name(capture_path.name + ".saved")
    real_connect = sqlite3.connect
    connected: list[str] = []

    def tracked_connect(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connected.append(str(target))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    manifest_path.replace(manifest_backup)
    try:
        with pytest.raises(
            FundamentalReadSnapshotError,
            match="raw_archive_manifest|path_component_missing",
        ):
            FundamentalReadSnapshotSession.open_exact_archived(
                provider,
                snapshot_root=tmp_path / "missing_manifest_operation",
                source_reference=reference.snapshot_reference,
                raw_archive_reference=reference.raw_archive_reference,
                stock_codes=reference.declared_stock_codes,
                cutoff_at=CUTOFF,
            )
        assert connected == []
        assert not (tmp_path / "missing_manifest_operation").exists()
    finally:
        manifest_backup.replace(manifest_path)

    capture_path.replace(capture_backup)
    try:
        with pytest.raises(
            FundamentalReadSnapshotError,
            match="raw_archive_capture|path_component_missing",
        ):
            FundamentalReadSnapshotSession.open_exact_archived(
                provider,
                snapshot_root=tmp_path / "missing_capture_operation",
                source_reference=reference.snapshot_reference,
                raw_archive_reference=reference.raw_archive_reference,
                stock_codes=reference.declared_stock_codes,
                cutoff_at=CUTOFF,
            )
        assert connected == []
        assert not (tmp_path / "missing_capture_operation").exists()
    finally:
        capture_backup.replace(capture_path)


def test_archived_exact_reopen_rejects_self_consistent_wrong_archive_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, original_session, _finished, _legacy_reference = _finish_source(
        tmp_path / "case"
    )
    reference = original_session.archive_source(tmp_path / "archives")
    original_payload = reference.raw_archive_reference.to_dict()
    wrong_id = "0" * 32
    wrong_root = tmp_path / "archives" / wrong_id
    original_payload["raw_archive_root"] = str(wrong_root)
    original_payload["archived_monthly_source_root"] = str(wrong_root / "monthly_source")
    original_payload["archive_id"] = wrong_id
    original_payload.pop("identity_sha256")
    original_payload.pop("archive_identity_sha256")
    original_payload.pop("manifest_sha256")
    archive_identity = hashlib.sha256(
        json.dumps(
            original_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    original_payload["archive_identity_sha256"] = archive_identity
    identity_payload = dict(original_payload)
    identity_payload["manifest_sha256"] = reference.raw_archive_reference.manifest_sha256
    identity_payload["archive_identity_sha256"] = archive_identity
    original_payload["manifest_sha256"] = reference.raw_archive_reference.manifest_sha256
    original_payload["identity_sha256"] = hashlib.sha256(
        json.dumps(
            identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    wrong_archive_reference = FundamentalReadSnapshotRawArchiveReferenceV1.from_json(
        json.dumps(
            original_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    forged_reference = replace(
        reference,
        raw_archive_reference=wrong_archive_reference,
    )
    assert DailyMarketMonthlyRevenueSourceReferenceV2.from_json(
        forged_reference.to_json()
    ) == forged_reference
    connected: list[str] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connected.append(str(target))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    with pytest.raises(
        FundamentalReadSnapshotError,
        match="raw_archive|reparse|inventory|path_component_missing",
    ):
        FundamentalReadSnapshotSession.open_exact_archived(
            provider,
            snapshot_root=tmp_path / "wrong_root_operation",
            source_reference=forged_reference.snapshot_reference,
            raw_archive_reference=forged_reference.raw_archive_reference,
            stock_codes=forged_reference.declared_stock_codes,
            cutoff_at=CUTOFF,
        )
    assert connected == []
    assert not (tmp_path / "wrong_root_operation").exists()


def test_archived_exact_reopen_rejects_mixed_snapshot_and_archive_versions_before_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_a, session_a, _finished_a, reference_a = _finish_source(
        tmp_path / "source_a"
    )
    _provider_b, session_b, _finished_b, reference_b = _finish_source(
        tmp_path / "source_b"
    )
    session_a.archive_source(tmp_path / "archives_a")
    archive_b = session_b.archive_source(tmp_path / "archives_b")
    connected: list[str] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connected.append(str(target))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    operation_root = tmp_path / "mixed_archive_operation"
    with pytest.raises(
        FundamentalReadSnapshotError,
        match="fundamental_snapshot_archived_reference_mismatch",
    ):
        FundamentalReadSnapshotSession.open_exact_archived(
            provider_a,
            snapshot_root=operation_root,
            source_reference=reference_a.snapshot_reference,
            raw_archive_reference=archive_b.raw_archive_reference,
            stock_codes=reference_a.declared_stock_codes,
            cutoff_at=CUTOFF,
        )
    assert connected == []
    assert not operation_root.exists()


def test_archived_exact_reopen_rejects_hardlinked_archive_file_before_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, original_session, _finished, _legacy_reference = _finish_source(
        tmp_path / "case"
    )
    reference = original_session.archive_source(tmp_path / "archives")
    archive_root = Path(reference.raw_archive_reference.raw_archive_root)
    source_file = (
        Path(reference.raw_archive_reference.archived_monthly_source_root)
        / reference.raw_archive_reference.files[0].relative_path
    )
    source_mode = stat.S_IMODE(source_file.stat().st_mode)
    hardlink = archive_root / "hardlink_probe"
    try:
        os.link(source_file, hardlink)
    except OSError as exc:
        pytest.skip(f"此 Windows 執行環境不可建立合成 hardlink：{type(exc).__name__}")
    connected: list[str] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connected.append(str(target))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    try:
        with pytest.raises(FundamentalReadSnapshotError, match="hardlink|inventory"):
            FundamentalReadSnapshotSession.open_exact_archived(
                provider,
                snapshot_root=tmp_path / "hardlink_operation",
                source_reference=reference.snapshot_reference,
                raw_archive_reference=reference.raw_archive_reference,
                stock_codes=reference.declared_stock_codes,
                cutoff_at=CUTOFF,
            )
        assert connected == []
        assert not (tmp_path / "hardlink_operation").exists()
    finally:
        if hardlink.exists():
            # Windows 會把唯讀屬性套用到同 inode 的 hardlink；暫時允許移除
            # 測試建立的連結，並立即還原來源封存檔的模式。
            source_file.chmod(source_mode | stat.S_IWUSR)
            hardlink.unlink()
            source_file.chmod(source_mode)


def test_archived_exact_reopen_rejects_symlinked_archive_file_before_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, original_session, _finished, _legacy_reference = _finish_source(
        tmp_path / "case"
    )
    reference = original_session.archive_source(tmp_path / "archives")
    archive_root = Path(reference.raw_archive_reference.raw_archive_root)
    source_file = (
        Path(reference.raw_archive_reference.archived_monthly_source_root)
        / reference.raw_archive_reference.files[0].relative_path
    )
    symlink = archive_root / "symlink_probe"
    try:
        os.symlink(source_file, symlink)
    except OSError as exc:
        pytest.skip(f"此 Windows 執行環境無法建立合成 symlink：{type(exc).__name__}")
    connected: list[str] = []
    real_connect = sqlite3.connect

    def tracked_connect(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connected.append(str(target))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    try:
        with pytest.raises(
            FundamentalReadSnapshotError,
            match="reparse|symlink|inventory|path_component",
        ):
            FundamentalReadSnapshotSession.open_exact_archived(
                provider,
                snapshot_root=tmp_path / "symlink_operation",
                source_reference=reference.snapshot_reference,
                raw_archive_reference=reference.raw_archive_reference,
                stock_codes=reference.declared_stock_codes,
                cutoff_at=CUTOFF,
            )
        assert connected == []
        assert not (tmp_path / "symlink_operation").exists()
    finally:
        symlink.unlink(missing_ok=True)
