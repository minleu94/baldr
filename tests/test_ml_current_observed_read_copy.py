from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3

import pytest

from data_module.ml_daily_price_revision_gate import VerifiedCurrentRestatedSourceContext
from data_module.ml_historical_snapshot_provider import (
    CurrentObservedRawSnapshot,
    MLHistoricalSnapshotProvider,
)
from data_module.pinned_sqlite_read_session import (
    PinnedSQLiteReadSession,
    PinnedSQLiteReadSessionCancelled,
    PinnedSQLiteReadSessionError,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_snapshot(path: Path, *, close_wal: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        '''
        CREATE TABLE daily_prices (
            "日期" TEXT, "證券代號" TEXT, "成交股數" INTEGER, "成交金額" INTEGER,
            "開盤價" NUMERIC, "最高價" NUMERIC, "最低價" NUMERIC, "收盤價" NUMERIC
        );
        CREATE TABLE technical_indicators (
            "日期" TEXT, "證券代號" TEXT, "RSI" NUMERIC, "MACD" NUMERIC, "ADX" NUMERIC
        );
        CREATE TABLE market_indices ("日期" TEXT, "收盤指數" NUMERIC, "收盤價" NUMERIC);
        CREATE TABLE industry_indices ("日期" TEXT, "指數名稱" TEXT, "收盤指數" NUMERIC);
        INSERT INTO daily_prices VALUES
            ('20261005', '2382', 100000, 10000000, 90, 92, 89, 91),
            ('20261006', '2382', 120000, 12000000, 91, 94, 90, 93);
        INSERT INTO technical_indicators VALUES
            ('20261006', '2382', 55.5, 1.25, 24.5);
        INSERT INTO market_indices VALUES ('20261006', 23000, 23000);
        INSERT INTO industry_indices VALUES ('20261006', '電子類', 1200);
        '''
    )
    connection.commit()
    if close_wal:
        connection.close()
    else:
        # Fixture 用來驗證開啟中的來源 WAL 由低層按既有政策處理。
        connection.execute("PRAGMA journal_mode=WAL")
        connection.close()


def _context(path: Path, *, digest: str | None = None) -> VerifiedCurrentRestatedSourceContext:
    sha = digest or _sha256(path)
    placeholder = "sha256:" + "a" * 64
    observed_at = datetime.fromisoformat("2026-10-07T12:00:00+08:00")
    return VerifiedCurrentRestatedSourceContext(
        source_database_path=str(path.resolve()),
        source_database_sha256="sha256:" + "b" * 64,
        source_wal_path=str(path.with_name(path.name + "-wal").resolve()),
        source_wal_sha256=None,
        snapshot_database_path=str(path.resolve()),
        snapshot_database_sha256="sha256:" + sha,
        snapshot_receipt_path=str(path.parent / "receipt.json"),
        snapshot_receipt_sha256=placeholder,
        decision_at=datetime.fromisoformat("2026-10-07T03:00:00+00:00"),
        training_as_of=datetime.fromisoformat("2026-10-07T03:30:00+00:00"),
        source_observed_at=observed_at,
        source_generation=1,
        revision_namespace_files=(),
        revision_namespace_bundle_sha256=placeholder,
        source_revision_evidence_schema_version="validated-source-evidence.v1",
        source_revision_evidence_scope_id="synthetic-fixture",
        source_revision_evidence_cutoff_date="2026-10-06",
        source_revision_evidence_sha256=placeholder,
        source_revision_evidence_namespaces=(),
        source_revision_evidence_files=(),
        revision_dependencies_verified_at=datetime.fromisoformat(
            "2026-10-07T03:30:00+00:00"
        ),
        revision_dependency_files=(),
        revision_dependency_bundle_sha256=placeholder,
        current_restated=True,
        historical_pit_eligible=False,
        source_wal_present=False,
    )


def _load(
    database_path: Path,
    source_context: VerifiedCurrentRestatedSourceContext,
    *,
    read_session: PinnedSQLiteReadSession | None = None,
) -> CurrentObservedRawSnapshot:
    result = MLHistoricalSnapshotProvider(database_path).load_current_observed(
        decision_date="2026-10-07",
        history_start_date="2026-10-01",
        symbols=("2382",),
        source_context=source_context,
        local_current_observed_at=datetime.fromisoformat("2026-10-07T12:00:00+08:00"),
        expected_feature_as_of_date="2026-10-06",
        cycle_id="synthetic-cycle",
        cycle_terminal_path=database_path.parent / "terminal.json",
        cycle_terminal_sha256="sha256:" + "c" * 64,
        source_context_envelope_path=database_path.parent / "context.json",
        source_context_envelope_sha256="sha256:" + "d" * 64,
        industry_index_names=("電子類",),
        read_session=read_session,
    )
    assert type(result) is CurrentObservedRawSnapshot
    return result


def _source_file_group_state(path: Path) -> tuple[tuple[str, bool, int | None, int | None, int | None, int | None, str | None], ...]:
    result: list[
        tuple[str, bool, int | None, int | None, int | None, int | None, str | None]
    ] = []
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(str(path) + suffix)
        try:
            stat = candidate.lstat()
        except FileNotFoundError:
            result.append((suffix, False, None, None, None, None, None))
        else:
            result.append(
                (
                    suffix,
                    True,
                    stat.st_size,
                    stat.st_mtime_ns,
                    stat.st_ctime_ns,
                    stat.st_nlink,
                    _sha256(candidate) if candidate.is_file() else None,
                )
            )
    return tuple(result)


@pytest.mark.parametrize("empty_wal", [False, True], ids=["wal-absent", "wal-empty"])
def test_session_provider_reuses_verified_transaction_and_preserves_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    empty_wal: bool,
) -> None:
    source = tmp_path / "source" / "snapshot.sqlite"
    _create_snapshot(source)
    if empty_wal:
        Path(str(source) + "-wal").write_bytes(b"")
    context = _context(source)
    baseline = _load(source, context)
    before = _source_file_group_state(source)
    private_root = tmp_path / "isolated-reader"
    private_root.mkdir()
    session = PinnedSQLiteReadSession.open_copy(
        source,
        expected_main_sha256=_sha256(source),
        private_root=private_root,
        max_copy_bytes=16 * 1024 * 1024,
    )
    connection = session.connection
    assert connection.in_transaction

    def forbidden_original_or_extra_connection(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise AssertionError("provider attempted an additional SQLite connection")

    def forbidden_original_hash(path: Path) -> str:
        raise AssertionError(f"provider attempted to hash the original database: {path}")

    monkeypatch.setattr(sqlite3, "connect", forbidden_original_or_extra_connection)
    monkeypatch.setattr(
        "data_module.ml_historical_snapshot_provider._sha256_path",
        forbidden_original_hash,
    )
    actual = _load(source, context, read_session=session)

    assert actual == baseline
    assert actual.source_fingerprint == baseline.source_fingerprint
    assert actual.source_rows_sha256_by_table == baseline.source_rows_sha256_by_table
    assert connection.in_transaction
    session.finish()
    assert _source_file_group_state(source) == before


def test_session_rejects_wrong_source_binding_without_opening_provider_connection(
    tmp_path: Path,
) -> None:
    first = tmp_path / "source-a" / "snapshot.sqlite"
    second = tmp_path / "source-b" / "snapshot.sqlite"
    _create_snapshot(first)
    _create_snapshot(second)
    private_root = tmp_path / "isolated-reader"
    private_root.mkdir()
    session = PinnedSQLiteReadSession.open_copy(
        first,
        expected_main_sha256=_sha256(first),
        private_root=private_root,
        max_copy_bytes=16 * 1024 * 1024,
    )
    with pytest.raises(ValueError, match="path differs"):
        _load(second, _context(second), read_session=session)
    session.finish()

    wrong_hash_session = PinnedSQLiteReadSession.open_copy(
        first,
        expected_main_sha256=_sha256(first),
        private_root=private_root,
        max_copy_bytes=16 * 1024 * 1024,
    )
    wrong_hash_context = replace(
        _context(first), snapshot_database_sha256="sha256:" + "0" * 64
    )
    with pytest.raises(ValueError, match="bytes differ"):
        _load(first, wrong_hash_context, read_session=wrong_hash_session)
    wrong_hash_session.finish()


def test_session_provider_rejects_closed_and_cancelled_sessions(tmp_path: Path) -> None:
    source = tmp_path / "source" / "snapshot.sqlite"
    _create_snapshot(source)
    context = _context(source)
    private_root = tmp_path / "isolated-reader"
    private_root.mkdir()

    closed = PinnedSQLiteReadSession.open_copy(
        source,
        expected_main_sha256=_sha256(source),
        private_root=private_root,
        max_copy_bytes=16 * 1024 * 1024,
    )
    closed.close()
    with pytest.raises(PinnedSQLiteReadSessionError):
        _load(source, context, read_session=closed)

    cancellation = {"requested": False}
    cancelled = PinnedSQLiteReadSession.open_copy(
        source,
        expected_main_sha256=_sha256(source),
        private_root=private_root,
        max_copy_bytes=16 * 1024 * 1024,
        cancel_callback=lambda: cancellation["requested"],
    )
    cancellation["requested"] = True
    with pytest.raises(PinnedSQLiteReadSessionCancelled):
        cancelled.finish()
    with pytest.raises(PinnedSQLiteReadSessionError):
        _load(source, context, read_session=cancelled)
