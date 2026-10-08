from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any
from uuid import uuid4

import pytest

import data_module.recommendation_current_fundamental_provider as provider_module
from data_module.current_fundamental_snapshots import (
    MONTHLY_YOY_COMPARATOR_ITEM_CODE,
    TABLE as CURRENT_FUNDAMENTAL_TABLE,
    ensure_current_observation_schema,
    insert_observations,
    monthly_snapshot_rows,
)
from data_module.monthly_revenue_snapshot_harvester import (
    parse_mops_monthly_revenue_snapshot_html,
    write_mops_snapshot_csv,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from data_module.selection_fact_readers import (
    FundamentalReadSessionCancelled,
    FundamentalReadSessionError,
    FundamentalReadSessionIncomplete,
    SelectionFundamentalReadSession,
)
import data_module.selection_fact_readers as read_session_module
import data_module.fundamental_read_snapshot as snapshot_module
from tests.test_monthly_revenue_snapshot_harvester import MOPS_SAMPLE_HTML


UTC = timezone.utc
CUTOFF = datetime(2026, 10, 4, 1, 0, tzinfo=UTC)
OBSERVED = datetime(2026, 10, 4, 0, 30, tzinfo=UTC)
SOURCE_AVAILABLE = datetime(2026, 10, 3, 23, 0, tzinfo=UTC)
REPORT_PERIOD = "2026-04"


def _seed_provider(
    root: Path,
    *,
    materialized_comparator: bool = True,
) -> RecommendationCurrentFundamentalProvider:
    root.mkdir(parents=True, exist_ok=True)
    database = root / "fundamentals.sqlite"
    output_root = root / "output"
    capture_root = output_root / "monthly_revenue_mops_snapshots"
    html = MOPS_SAMPLE_HTML
    raw_sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    raw_source_version = (
        f"mops-static-snapshot.v2:twse:{REPORT_PERIOD}:body_completed_at:"
        f"{SOURCE_AVAILABLE.isoformat()}:sha256:{raw_sha256}"
    )
    parsed, diagnostics = parse_mops_monthly_revenue_snapshot_html(
        html,
        market="twse",
        period=REPORT_PERIOD,
        fetched_at=SOURCE_AVAILABLE.isoformat(),
        source_version=raw_source_version,
    )
    assert diagnostics == ()
    capture_root.mkdir(parents=True, exist_ok=True)
    (capture_root / "raw_html").mkdir(exist_ok=True)
    (capture_root / "raw_html" / f"twse_{REPORT_PERIOD}.html").write_bytes(
        html.encode("utf-8")
    )
    csv_path = capture_root / "mops_monthly_revenue_snapshot_fixture.csv"
    write_mops_snapshot_csv(csv_path, parsed)
    rows = monthly_snapshot_rows(
        csv_path,
        verified_source_versions=frozenset({raw_source_version}),
    )
    if not materialized_comparator:
        rows = [
            row
            for row in rows
            if row["item_code"] != MONTHLY_YOY_COMPARATOR_ITEM_CODE
        ]
    for row in rows:
        row["observed_at"] = OBSERVED.isoformat()
    connection = sqlite3.connect(database)
    try:
        ensure_current_observation_schema(connection)
        assert insert_observations(connection, rows) == len(rows)
        connection.commit()
    finally:
        connection.close()
    return RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=output_root,
        monthly_source_root=output_root,
    )


def _open_session(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    stock_codes: tuple[str, ...] = ("1101", "2330"),
    cutoff_at: datetime = CUTOFF,
    cancel_callback: object = None,
    database_path: Path | str | None = None,
) -> SelectionFundamentalReadSession:
    attempt, reader_provider, copy_binding = _make_direct_copy_binding(
        provider,
        label="direct_session",
        cancel_callback=cancel_callback,
    )
    return SelectionFundamentalReadSession.open(
        reader_provider,
        database_path=database_path or attempt.reader_database_path,
        copy_binding=copy_binding,
        stock_codes=stock_codes,
        cutoff_at=cutoff_at,
        cancel_callback=cancel_callback,  # type: ignore[arg-type]
    )


def _make_direct_copy_binding(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    label: str,
    cancel_callback: object = None,
) -> tuple[
    snapshot_module._SnapshotAttempt,
    RecommendationCurrentFundamentalProvider,
    snapshot_module.FundamentalReadCopyBinding,
]:
    attempt = snapshot_module._capture_snapshot(
        provider,
        snapshot_root=_snapshot_output_root(label),
        cancel_callback=cancel_callback,  # type: ignore[arg-type]
    )
    reader_provider = snapshot_module._clone_provider_for_reader(
        provider,
        reader_database_path=attempt.reader_database_path,
    )
    if attempt.sqlite_journal_mode == "wal" and attempt.wal_sidecar_state == "absent":
        primer_binding = snapshot_module._make_copy_binding(
            attempt,
            cancel_callback=cancel_callback,  # type: ignore[arg-type]
        )
        snapshot_module._verify_copy_binding_for_provider(
            primer_binding,
            provider=reader_provider,
            cancel_callback=cancel_callback,  # type: ignore[arg-type]
        )
        snapshot_module._prime_reader_copy(
            attempt.reader_database_path,
            cancel_callback=cancel_callback,  # type: ignore[arg-type]
        )
    copy_binding = snapshot_module._make_copy_binding(
        attempt,
        cancel_callback=cancel_callback,  # type: ignore[arg-type]
    )
    return attempt, reader_provider, copy_binding


def _snapshot_output_root(label: str) -> Path:
    """使用 repo QA 隔離區保存每個 synthetic snapshot attempt。"""

    return (
        Path(__file__).resolve().parents[1]
        / "output"
        / "qa"
        / f"p03_snapshot_{label}_{uuid4().hex}"
    )


def _open_snapshot_session(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    label: str,
    stock_codes: tuple[str, ...] = ("1101", "2330"),
    cancel_callback: object = None,
) -> snapshot_module.FundamentalReadSnapshotSession:
    return snapshot_module.FundamentalReadSnapshotSession.open(
        provider,
        snapshot_root=_snapshot_output_root(label),
        stock_codes=stock_codes,
        cutoff_at=CUTOFF,
        cancel_callback=cancel_callback,  # type: ignore[arg-type]
    )


def _open_wal_writer_with_uncheckpointed_observation(
    provider: RecommendationCurrentFundamentalProvider,
    *,
    stock_code: str = "9999",
) -> sqlite3.Connection:
    connection = sqlite3.connect(provider.db_file)
    mode = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
    assert mode == "wal"
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE synthetic_wal_probe(stock_code TEXT NOT NULL)")
    connection.execute("INSERT INTO synthetic_wal_probe(stock_code) VALUES(?)", (stock_code,))
    connection.commit()
    return connection


def _source_file_bytes_and_mtimes(
    database_path: Path,
) -> tuple[tuple[str, bytes | None, int | None], ...]:
    items: list[tuple[str, bytes | None, int | None]] = []
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = Path(f"{database_path}{suffix}")
        if path.exists():
            items.append((suffix or "main", path.read_bytes(), path.stat().st_mtime_ns))
        else:
            items.append((suffix or "main", None, None))
    return tuple(items)


def _source_file_physical_state(
    database_path: Path,
) -> tuple[tuple[str, tuple[int, int, int, int, int] | None], ...]:
    states: list[tuple[str, tuple[int, int, int, int, int] | None]] = []
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = database_path if not suffix else Path(f"{database_path}{suffix}")
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            states.append((suffix or "main", None))
            continue
        states.append(
            (
                suffix or "main",
                (
                    int(metadata.st_dev),
                    int(metadata.st_ino),
                    int(metadata.st_nlink),
                    int(metadata.st_size),
                    int(metadata.st_mtime_ns),
                ),
            )
        )
    return tuple(states)


def test_direct_session_requires_copy_binding_before_any_database_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    wal_writer = sqlite3.connect(provider.db_file)
    try:
        assert str(wal_writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower() == "wal"
        wal_writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        wal_writer.close()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{provider.db_file}{suffix}")
        if sidecar.exists():
            sidecar.unlink()
    assert not Path(f"{provider.db_file}-wal").exists()
    assert not Path(f"{provider.db_file}-shm").exists()
    before = _source_file_bytes_and_mtimes(provider.db_file)
    connect_calls: list[tuple[object, ...]] = []
    original_connect = sqlite3.connect

    def counted_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connect_calls.append(args)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(read_session_module.sqlite3, "connect", counted_connect)
    with pytest.raises(TypeError, match="copy_binding"):
        SelectionFundamentalReadSession.open(
            provider,
            database_path=provider.db_file,
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
        )

    assert connect_calls == []
    assert _source_file_bytes_and_mtimes(provider.db_file) == before
    assert not Path(f"{provider.db_file}-wal").exists()
    assert not Path(f"{provider.db_file}-shm").exists()


@pytest.mark.parametrize("tamper_target", ["manifest", "reader_main"])
def test_direct_session_revalidates_copy_manifest_and_bytes_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_target: str,
) -> None:
    provider = _seed_provider(tmp_path)
    attempt, reader_provider, copy_binding = _make_direct_copy_binding(
        provider,
        label=f"binding_tamper_{tamper_target}",
    )
    source_before = _source_file_bytes_and_mtimes(provider.db_file)
    target = (
        attempt.snapshot_root / "snapshot_capture.json"
        if tamper_target == "manifest"
        else attempt.reader_database_path
    )
    os.chmod(target, target.stat().st_mode | stat.S_IWRITE)
    with target.open("ab") as stream:
        stream.write(b"synthetic-copy-binding-tamper")
        stream.flush()
        os.fsync(stream.fileno())

    connect_calls: list[tuple[object, ...]] = []
    original_connect = sqlite3.connect

    def counted_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connect_calls.append(args)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(read_session_module.sqlite3, "connect", counted_connect)
    with pytest.raises(FundamentalReadSessionError, match="copy binding invalid"):
        SelectionFundamentalReadSession.open(
            reader_provider,
            database_path=attempt.reader_database_path,
            copy_binding=copy_binding,
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
        )

    assert connect_calls == []
    assert _source_file_bytes_and_mtimes(provider.db_file) == source_before


@pytest.mark.parametrize(
    ("link_target", "link_role"),
    [
        ("source", "main"),
        ("source", "shm"),
        ("captured", "main"),
    ],
)
def test_direct_session_rejects_hardlinked_copy_before_connect_without_source_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    link_target: str,
    link_role: str,
) -> None:
    provider = _seed_provider(tmp_path)
    writer: sqlite3.Connection | None = None
    if link_role == "shm":
        writer = _open_wal_writer_with_uncheckpointed_observation(provider)
    attempt, reader_provider, _ = _make_direct_copy_binding(
        provider,
        label=f"hardlink_{link_target}_{link_role}",
    )
    suffix = "" if link_role == "main" else f"-{link_role}"
    reader_path = Path(f"{attempt.reader_database_path}{suffix}")
    linked_path = (
        provider.db_file
        if link_target == "source"
        else attempt.snapshot_root / "captured" / provider.db_file.name
    )
    reader_path.chmod(reader_path.stat().st_mode | stat.S_IWRITE)
    reader_path.unlink()
    os.link(linked_path, reader_path)
    assert reader_path.stat().st_ino == linked_path.stat().st_ino
    assert reader_path.stat().st_nlink >= 2
    copy_binding = snapshot_module._make_copy_binding(
        attempt,
        cancel_callback=None,
    )
    source_bytes_before = _source_file_bytes_and_mtimes(provider.db_file)
    source_state_before = _source_file_physical_state(provider.db_file)

    connect_calls: list[tuple[object, ...]] = []
    original_connect = sqlite3.connect

    def counted_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connect_calls.append(args)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(read_session_module.sqlite3, "connect", counted_connect)
    try:
        with pytest.raises(
            FundamentalReadSessionError,
            match="copy binding invalid: copy file must have exactly one hard link",
        ):
            SelectionFundamentalReadSession.open(
                reader_provider,
                database_path=attempt.reader_database_path,
                copy_binding=copy_binding,
                stock_codes=("2330",),
                cutoff_at=CUTOFF,
            )

        assert connect_calls == []
        assert _source_file_bytes_and_mtimes(provider.db_file) == source_bytes_before
        assert _source_file_physical_state(provider.db_file) == source_state_before
    finally:
        if writer is not None:
            writer.close()


def test_shared_session_uses_one_read_transaction_and_finishes_source_pins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    connect_calls: list[tuple[object, ...]] = []
    original_connect = provider_module.sqlite3.connect

    def counted_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connect_calls.append(args)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(provider_module.sqlite3, "connect", counted_connect)
    session = _open_session(provider)
    batch = session.load_batch(("1101", "2330"))

    assert connect_calls == [(f"{session._database_path.as_uri()}?mode=ro",)]
    assert batch.batch_index == 0
    assert [result.status for result in batch.results] == ["missing", "ready"]
    assert batch.results[1].comparison_baseline is not None
    assert batch.results[1].comparison_baseline.period == "2025-04"

    finished = session.finish()

    assert finished.complete is True
    assert finished.processed_stock_codes == ("1101", "2330")
    assert finished.result_identity_by_stock == tuple(
        zip(batch.stock_codes, batch.result_identity_sha256, strict=True)
    )
    assert finished.source_clock.database_path == str(session._database_path)
    assert finished.source_clock.source_scope == "current_observed_only"
    assert finished.source_clock.availability_status == "unknown"
    assert finished.source_clock.historical_pit_eligible is False
    assert finished.source_clock.formal_pit_eligible is False
    assert finished.source_clock.schema_identity_sha256
    pins_start = {pin.role: pin for pin in finished.source_clock.database_file_pins_start}
    pins_finish = {pin.role: pin for pin in finished.source_clock.database_file_pins_finish}
    for stable_role in ("sqlite_main", "sqlite_wal", "sqlite_rollback_journal"):
        assert pins_start[stable_role] == pins_finish[stable_role]
    assert pins_start["sqlite_shm"].present == pins_finish["sqlite_shm"].present
    assert len(finished.source_clock.database_file_pins_start) == 4
    assert finished.source_clock.database_file_pins_start[0].sha256 == hashlib.sha256(
        session._database_path.read_bytes()
    ).hexdigest()
    assert finished.source_clock.capture_file_pins_start
    assert finished.source_clock.capture_file_pins_start == (
        finished.source_clock.capture_file_pins_finish
    )
    payload = finished.source_clock.to_dict()
    assert payload["source_pin_sha256"] == finished.source_clock.identity_sha256
    assert json.loads(json.dumps(payload, ensure_ascii=False))["source_scope"] == (
        "current_observed_only"
    )
    assert len(connect_calls) == 1
    assert session.cancel() is False


def test_snapshot_session_reads_uncheckpointed_wal_row_without_opening_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    writer = _open_wal_writer_with_uncheckpointed_observation(provider)
    wal_path = Path(f"{provider.db_file}-wal")
    shm_path = Path(f"{provider.db_file}-shm")
    assert wal_path.is_file() and wal_path.stat().st_size > 32
    assert shm_path.is_file()
    before = _source_file_bytes_and_mtimes(provider.db_file)

    connect_calls: list[tuple[object, ...]] = []
    original_connect = sqlite3.connect

    def counted_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connect_calls.append(args)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(snapshot_module.sqlite3, "connect", counted_connect)
    session = _open_snapshot_session(provider, label="wal_complete", stock_codes=("2330",))
    batch = session.load_batch(("2330",))
    assert batch.results[0].observations
    reader_uri = f"{session.reader_database_path.as_uri()}?mode=ro"
    copied_db = sqlite3.connect(reader_uri, uri=True)
    try:
        assert copied_db.execute(
            "SELECT stock_code FROM synthetic_wal_probe"
        ).fetchone() == ("9999",)
    finally:
        copied_db.close()
    finished = session.finish()

    assert len(connect_calls) == 2
    assert all(
        str(arg[0]).startswith(session.reader_database_path.as_uri())
        for arg in connect_calls
    )
    assert finished.complete is True
    assert finished.source_clock.database_path == str(provider.db_file)
    assert finished.source_clock.schema_version == (
        snapshot_module.FUNDAMENTAL_SNAPSHOT_SOURCE_CLOCK_SCHEMA
    )
    binding = finished.source_clock.snapshot_binding
    assert binding.source_database_path == str(provider.db_file)
    assert binding.reader_database_path == str(session.reader_database_path)
    assert binding.sqlite_journal_mode == "wal"
    assert binding.wal_sidecar_state == "complete"
    assert binding.source_file_pins_start == binding.source_file_pins_after_copy
    assert binding.source_file_pins_start == binding.source_file_pins_finish
    assert {pin.role for pin in binding.source_file_pins_start} == {
        "sqlite_main",
        "sqlite_wal",
        "sqlite_shm",
        "sqlite_rollback_journal",
    }
    assert binding.duplicated_disk_bytes == binding.source_copy_bytes * 2
    captured_main = session.snapshot_root / "captured" / provider.db_file.name
    reader_main = session.reader_database_path
    assert not captured_main.samefile(reader_main)
    assert {item.role for item in binding.captured_files} == {
        "sqlite_main",
        "sqlite_wal",
        "sqlite_shm",
    }
    captured_by_role = {item.role: item for item in binding.captured_files}
    reader_by_role = {item.role: item for item in binding.reader_files}
    source_pins_by_role = {pin.role: pin for pin in binding.source_file_pins_start}
    for role in ("sqlite_main", "sqlite_wal", "sqlite_shm"):
        captured_path = session.snapshot_root / Path(captured_by_role[role].relative_path)
        reader_path = session.snapshot_root / Path(reader_by_role[role].relative_path)
        assert not captured_path.samefile(reader_path)
        assert captured_by_role[role].sha256 == source_pins_by_role[role].sha256
        assert reader_by_role[role].sha256 == source_pins_by_role[role].sha256
    assert _source_file_bytes_and_mtimes(provider.db_file) == before
    status = json.loads((session.snapshot_root / "attempt_status.json").read_text("utf-8"))
    assert status["status"] == "complete"
    final_manifest = json.loads(
        (session.snapshot_root / "finished_source_clock.json").read_text("utf-8")
    )
    assert final_manifest["source_clock"]["database_path"] == str(provider.db_file)
    assert final_manifest["manifest_state"] == "complete"
    assert session.cancel() is False
    writer.close()


def test_snapshot_main_only_wal_reads_copy_and_does_not_create_source_sidecars(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path)
    writer = sqlite3.connect(provider.db_file)
    assert str(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower() == "wal"
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    writer.close()
    wal_path = Path(f"{provider.db_file}-wal")
    shm_path = Path(f"{provider.db_file}-shm")
    if wal_path.exists():
        wal_path.unlink()
    if shm_path.exists():
        shm_path.unlink()
    assert not wal_path.exists() and not shm_path.exists()
    before = _source_file_bytes_and_mtimes(provider.db_file)

    session = _open_snapshot_session(provider, label="wal_main_only", stock_codes=("2330",))
    batch = session.load_batch(("2330",))
    assert batch.results[0].observations
    finished = session.finish()

    binding = finished.source_clock.snapshot_binding
    assert binding.sqlite_journal_mode == "wal"
    assert binding.wal_sidecar_state == "absent"
    assert _source_file_bytes_and_mtimes(provider.db_file) == before
    assert not wal_path.exists() and not shm_path.exists()
    assert Path(f"{session.reader_database_path}-wal").exists()


def test_snapshot_rejects_source_drift_during_capture_and_preserves_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    output_root = _snapshot_output_root("drift")
    original_copy = snapshot_module._copy_file_bounded
    changed = False

    def copy_then_drift(
        source: Path,
        destination: Path,
        *,
        max_bytes: int,
        cancel_callback: Any,
    ) -> tuple[int, str]:
        nonlocal changed
        result = original_copy(
            source,
            destination,
            max_bytes=max_bytes,
            cancel_callback=cancel_callback,
        )
        if not changed and destination.parent.name == "captured":
            with provider.db_file.open("ab") as stream:
                stream.write(b"synthetic-source-drift")
                stream.flush()
                os.fsync(stream.fileno())
            changed = True
        return result

    monkeypatch.setattr(snapshot_module, "_copy_file_bounded", copy_then_drift)
    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match="original_source_changed_during_copy",
    ):
        snapshot_module.FundamentalReadSnapshotSession.open(
            provider,
            snapshot_root=output_root,
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
        )

    attempts = list(output_root.iterdir())
    assert len(attempts) == 1
    assert json.loads((attempts[0] / "attempt_status.json").read_text("utf-8"))["status"] == "failed"
    assert (attempts[0] / "captured" / provider.db_file.name).is_file()


def test_snapshot_copy_cancellation_is_chunked_and_never_completes(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path)
    connection = sqlite3.connect(provider.db_file)
    try:
        connection.execute("CREATE TABLE synthetic_copy_padding(value BLOB NOT NULL)")
        connection.execute(
            "INSERT INTO synthetic_copy_padding(value) VALUES(zeroblob(?))",
            (3 * 1024 * 1024,),
        )
        connection.commit()
    finally:
        connection.close()
    output_root = _snapshot_output_root("copy_cancel")

    def cancel_after_first_copy_chunk() -> bool:
        for copied in output_root.glob("*/captured/*"):
            if copied.is_file() and copied.stat().st_size >= snapshot_module.SNAPSHOT_COPY_CHUNK_BYTES:
                return True
        return False

    with pytest.raises(snapshot_module.FundamentalReadSnapshotCancelled):
        snapshot_module.FundamentalReadSnapshotSession.open(
            provider,
            snapshot_root=output_root,
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
            cancel_callback=cancel_after_first_copy_chunk,
        )

    attempts = list(output_root.iterdir())
    assert len(attempts) == 1
    status = json.loads((attempts[0] / "attempt_status.json").read_text("utf-8"))
    assert status["status"] == "cancelled"
    assert not list(attempts[0].glob("finished_source_clock.json"))


def test_snapshot_finish_rejects_original_database_drift_after_batch_read(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path)
    session = _open_snapshot_session(provider, label="finish_drift", stock_codes=("2330",))
    batch = session.load_batch(("2330",))
    assert batch.results[0].observations
    with provider.db_file.open("ab") as stream:
        stream.write(b"synthetic-finish-drift")
        stream.flush()
        os.fsync(stream.fileno())

    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match="original_source_changed_before_finish",
    ):
        session.finish()
    assert session.closed is True
    status = json.loads((session.snapshot_root / "attempt_status.json").read_text("utf-8"))
    assert status["status"] == "failed"


def test_snapshot_final_cancel_after_source_pin_hash_blocks_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    callback_cancelled = False
    source_pin_calls = 0
    original_pin_set = snapshot_module._pin_source_file_set

    def cancel_after_final_source_hash(
        database_path: Path,
        *,
        cancel_callback: Any,
    ) -> tuple[snapshot_module.FundamentalFilePin, ...]:
        nonlocal callback_cancelled, source_pin_calls
        result = original_pin_set(
            database_path,
            cancel_callback=cancel_callback,
        )
        if database_path == provider.db_file:
            source_pin_calls += 1
            if source_pin_calls == 3:
                callback_cancelled = True
        return result

    monkeypatch.setattr(snapshot_module, "_pin_source_file_set", cancel_after_final_source_hash)
    session = _open_snapshot_session(
        provider,
        label="cancel_after_hash",
        stock_codes=("2330",),
        cancel_callback=lambda: callback_cancelled,
    )
    session.load_batch(("2330",))
    with pytest.raises(snapshot_module.FundamentalReadSnapshotCancelled):
        session.finish()

    assert source_pin_calls == 3
    assert callback_cancelled is True
    assert session.closed is True
    status = json.loads((session.snapshot_root / "attempt_status.json").read_text("utf-8"))
    assert status["status"] == "cancelled"


def test_snapshot_final_publication_gate_rechecks_external_cancel_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    callback_cancelled = False
    original_write = snapshot_module._write_atomic_json

    def write_candidate_then_cancel(path: Path, payload: dict[str, object]) -> None:
        nonlocal callback_cancelled
        original_write(path, payload)
        if (
            path.name == "finished_source_clock.json"
            and payload.get("manifest_state") == "candidate_pending_publication"
        ):
            callback_cancelled = True

    monkeypatch.setattr(snapshot_module, "_write_atomic_json", write_candidate_then_cancel)
    session = _open_snapshot_session(
        provider,
        label="cancel_at_publication_gate",
        stock_codes=("2330",),
        cancel_callback=lambda: callback_cancelled,
    )
    session.load_batch(("2330",))

    with pytest.raises(snapshot_module.FundamentalReadSnapshotCancelled):
        session.finish()

    assert callback_cancelled is True
    assert session.closed is True
    manifest = json.loads(
        (session.snapshot_root / "finished_source_clock.json").read_text("utf-8")
    )
    assert manifest["manifest_state"] == "candidate_pending_publication"
    status = json.loads((session.snapshot_root / "attempt_status.json").read_text("utf-8"))
    assert status["status"] == "cancelled"


@pytest.mark.parametrize(
    ("evidence_kind", "expected_error"),
    (
        ("captured_file", "captured_file_changed_before_finish"),
        ("capture_manifest", "capture_manifest_bytes_mismatch"),
    ),
)
def test_snapshot_finish_rejects_tampered_captured_evidence(
    tmp_path: Path,
    evidence_kind: str,
    expected_error: str,
) -> None:
    provider = _seed_provider(tmp_path)
    session = _open_snapshot_session(
        provider,
        label=f"tampered_{evidence_kind}",
        stock_codes=("2330",),
    )
    session.load_batch(("2330",))
    if evidence_kind == "captured_file":
        reference = session._attempt.captured_files[0]
        evidence_path = session.snapshot_root / Path(reference.relative_path)
    else:
        evidence_path = session.snapshot_root / "snapshot_capture.json"
    os.chmod(evidence_path, evidence_path.stat().st_mode | stat.S_IWRITE)
    with evidence_path.open("ab") as stream:
        stream.write(b"synthetic-evidence-tamper")
        stream.flush()
        os.fsync(stream.fileno())

    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match=expected_error,
    ):
        session.finish()

    assert session.closed is True
    status = json.loads((session.snapshot_root / "attempt_status.json").read_text("utf-8"))
    assert status["status"] == "failed"


def test_snapshot_rejects_invalid_sqlite_schema_on_copy_without_opening_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    connection = sqlite3.connect(provider.db_file)
    try:
        connection.execute(f"DROP TABLE {CURRENT_FUNDAMENTAL_TABLE}")
        connection.commit()
    finally:
        connection.close()
    connect_calls: list[tuple[object, ...]] = []
    original_connect = sqlite3.connect

    def counted_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connect_calls.append(args)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(snapshot_module.sqlite3, "connect", counted_connect)
    output_root = _snapshot_output_root("invalid_schema")
    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match="reader_copy_invalid",
    ):
        snapshot_module.FundamentalReadSnapshotSession.open(
            provider,
            snapshot_root=output_root,
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
        )
    assert len(connect_calls) == 1
    assert str(connect_calls[0][0]).startswith("file:///")
    assert str(provider.db_file) not in str(connect_calls[0][0])
    attempt = next(output_root.iterdir())
    assert json.loads((attempt / "attempt_status.json").read_text("utf-8"))["status"] == "failed"


def test_snapshot_rejects_bad_wal_and_rollback_journal_before_any_sqlite_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    writer = _open_wal_writer_with_uncheckpointed_observation(provider)
    wal_path = Path(f"{provider.db_file}-wal")
    with wal_path.open("r+b") as stream:
        stream.write(b"BAD!")
        stream.flush()
        os.fsync(stream.fileno())
    rollback_provider = _seed_provider(tmp_path / "rollback")
    journal = Path(f"{rollback_provider.db_file}-journal")
    journal.write_bytes(b"synthetic rollback journal")
    wal_source_provider = _seed_provider(tmp_path / "wal_missing_shm_source")
    incomplete_wal_writer = _open_wal_writer_with_uncheckpointed_observation(
        wal_source_provider
    )
    incomplete_wal_provider = _seed_provider(tmp_path / "wal_missing_shm")
    incomplete_wal_provider.db_file.write_bytes(wal_source_provider.db_file.read_bytes())
    Path(f"{incomplete_wal_provider.db_file}-wal").write_bytes(
        Path(f"{wal_source_provider.db_file}-wal").read_bytes()
    )
    incomplete_shm = Path(f"{incomplete_wal_provider.db_file}-shm")
    assert not incomplete_shm.exists()
    checksum_provider = _seed_provider(tmp_path / "wal_bad_checksum")
    checksum_writer = _open_wal_writer_with_uncheckpointed_observation(checksum_provider)
    checksum_wal = Path(f"{checksum_provider.db_file}-wal")
    with checksum_wal.open("r+b") as stream:
        stream.seek(32 + 24)
        first_page_byte = stream.read(1)
        stream.seek(32 + 24)
        stream.write(bytes([first_page_byte[0] ^ 0x01]))
        stream.flush()
        os.fsync(stream.fileno())
    invalid_header_provider = _seed_provider(tmp_path / "bad_sqlite_header")
    with invalid_header_provider.db_file.open("r+b") as stream:
        stream.seek(0)
        stream.write(b"not a sqlite db!")
        stream.flush()
        os.fsync(stream.fileno())
    connect_calls: list[tuple[object, ...]] = []
    original_connect = sqlite3.connect

    def counted_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connect_calls.append(args)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(snapshot_module.sqlite3, "connect", counted_connect)
    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match="wal_header_invalid",
    ):
        snapshot_module.FundamentalReadSnapshotSession.open(
            provider,
            snapshot_root=_snapshot_output_root("bad_wal"),
            stock_codes=("9999",),
            cutoff_at=CUTOFF,
        )
    assert connect_calls == []
    writer.close()

    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match="wal_checksum_mismatch",
    ):
        snapshot_module.FundamentalReadSnapshotSession.open(
            checksum_provider,
            snapshot_root=_snapshot_output_root("bad_wal_checksum"),
            stock_codes=("9999",),
            cutoff_at=CUTOFF,
        )
    assert connect_calls == []
    checksum_writer.close()

    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match="rollback_journal_present_refused_without_replay",
    ):
        snapshot_module.FundamentalReadSnapshotSession.open(
            rollback_provider,
            snapshot_root=_snapshot_output_root("rollback_journal"),
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
        )
    assert connect_calls == []
    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match="wal_sidecar_shm_missing",
    ):
        snapshot_module.FundamentalReadSnapshotSession.open(
            incomplete_wal_provider,
            snapshot_root=_snapshot_output_root("wal_missing_shm"),
            stock_codes=("9999",),
            cutoff_at=CUTOFF,
        )
    assert connect_calls == []
    incomplete_wal_writer.close()

    with pytest.raises(
        snapshot_module.FundamentalReadSnapshotError,
        match="invalid_sqlite_header",
    ):
        snapshot_module.FundamentalReadSnapshotSession.open(
            invalid_header_provider,
            snapshot_root=_snapshot_output_root("bad_sqlite_header"),
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
        )
    assert connect_calls == []


def test_snapshot_provider_clone_keeps_wrong_database_guard(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path)
    attempt = snapshot_module._capture_snapshot(
        provider,
        snapshot_root=_snapshot_output_root("wrong_db"),
        cancel_callback=None,
    )
    clone = snapshot_module._clone_provider_for_reader(
        provider,
        reader_database_path=attempt.reader_database_path,
    )
    binding = snapshot_module._make_copy_binding(attempt, cancel_callback=None)
    with pytest.raises(FundamentalReadSessionError, match="does not match provider database"):
        SelectionFundamentalReadSession.open(
            clone,
            database_path=provider.db_file,
            copy_binding=binding,
            stock_codes=("2330",),
            cutoff_at=CUTOFF,
        )


def test_session_fallback_bypasses_provider_instance_capture_cache(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path, materialized_comparator=False)
    raw_sha256 = hashlib.sha256(MOPS_SAMPLE_HTML.encode("utf-8")).hexdigest()
    raw_source_version = (
        f"mops-static-snapshot.v2:twse:{REPORT_PERIOD}:body_completed_at:"
        f"{SOURCE_AVAILABLE.isoformat()}:sha256:{raw_sha256}"
    )
    session = _open_session(provider, stock_codes=("2330",))
    session._provider._verified_monthly_capture_cache[
        ("twse", REPORT_PERIOD, raw_source_version)
    ] = (
        {
            "2330": {
                "current_month_revenue": "195211000",
                "previous_year_month_revenue": "1",
            }
        },
        "0" * 64,
        (),
    )

    batch = session.load_batch(("2330",))
    result = batch.results[0]
    assert result.comparison_baseline is not None
    assert result.comparison_baseline.revenue == Decimal("160000000000")
    expected_csv_sha256 = hashlib.sha256(
        (
            provider.monthly_source_root
            / "monthly_revenue_mops_snapshots"
            / "mops_monthly_revenue_snapshot_fixture.csv"
        ).read_bytes()
    ).hexdigest()
    assert result.comparison_snapshot_sha256 == expected_csv_sha256
    assert result.comparison_baseline.source_version.endswith(
        f":verified-csv-sha256:{expected_csv_sha256}"
    )
    finished = session.finish()
    assert finished.complete is True


def test_batches_are_ordered_bounded_and_finish_requires_every_declared_code(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path)
    session = _open_session(provider)
    with pytest.raises(ValueError, match="declared"):
        session.load_batch(("2330",))
    first = session.load_batch(("1101",))
    assert first.batch_index == 0
    with pytest.raises(FundamentalReadSessionIncomplete):
        session.finish()


def test_cancel_after_provider_row_discards_batch_and_prevents_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    cancel_requested = False
    session = _open_session(
        provider,
        stock_codes=("2330",),
        cancel_callback=lambda: cancel_requested,
    )
    original = session._provider.load_monthly_revenues

    def load_then_cancel(**kwargs: object):
        nonlocal cancel_requested
        result = original(**kwargs)  # type: ignore[arg-type]
        cancel_requested = True
        return result

    monkeypatch.setattr(session._provider, "load_monthly_revenues", load_then_cancel)

    with pytest.raises(FundamentalReadSessionCancelled):
        session.load_batch(("2330",))
    with pytest.raises(FundamentalReadSessionError):
        session.finish()


def test_cancel_after_one_stock_does_not_read_the_next_declared_stock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    cancel_requested = False
    loaded_codes: list[str] = []
    session = _open_session(
        provider,
        stock_codes=("1101", "2330"),
        cancel_callback=lambda: cancel_requested,
    )
    original = session._provider.load_monthly_revenues

    def load_then_cancel_first(**kwargs: Any):
        nonlocal cancel_requested
        code = str(kwargs["stock_code"])
        loaded_codes.append(code)
        result = original(**kwargs)
        if code == "1101":
            cancel_requested = True
        return result

    monkeypatch.setattr(session._provider, "load_monthly_revenues", load_then_cancel_first)

    with pytest.raises(FundamentalReadSessionCancelled):
        session.load_batch(("1101", "2330"))

    assert loaded_codes == ["1101"]
    assert session.closed is True
    assert session.finished is False


def test_cutoff_is_frozen_and_wrong_provider_result_cutoff_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)
    session = _open_session(provider, stock_codes=("2330",))
    original = session._provider.load_monthly_revenues

    def return_wrong_cutoff(**kwargs: object):
        result = original(**kwargs)  # type: ignore[arg-type]
        return replace(result, cutoff_at=CUTOFF.replace(hour=0))

    monkeypatch.setattr(session._provider, "load_monthly_revenues", return_wrong_cutoff)
    with pytest.raises(FundamentalReadSessionError, match="cutoff mismatch"):
        session.load_batch(("2330",))


def test_injected_provider_connection_must_be_same_database_and_query_only(
    tmp_path: Path,
) -> None:
    first = _seed_provider(tmp_path / "first")
    second = _seed_provider(tmp_path / "second")
    with pytest.raises(FundamentalReadSessionError, match="does not match provider"):
        _open_session(first, stock_codes=("2330",), database_path=second.db_file)
    session = _open_session(first, stock_codes=("2330",))
    other_uri = f"{second.db_file.as_uri()}?mode=ro"
    other = sqlite3.connect(other_uri, uri=True)
    try:
        other.execute("PRAGMA query_only=ON")
        other.execute("BEGIN")
        with pytest.raises(ValueError, match="database does not match"):
            first.load_monthly_revenues(
                stock_code="2330",
                cutoff_at=CUTOFF,
                read_session_connection=other,
            )
    finally:
        other.close()
        session.close()


def test_database_stat_or_bytes_drift_rejects_finished_cohort(tmp_path: Path) -> None:
    provider = _seed_provider(tmp_path)
    session = _open_session(provider, stock_codes=("1101",))
    session.load_batch(("1101",))
    before = session._database_path.stat()
    os.utime(
        session._database_path,
        ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000),
    )

    with pytest.raises(FundamentalReadSessionError, match="DB/WAL source pin changed"):
        session.finish()


def test_source_clock_pins_existing_wal_file(tmp_path: Path) -> None:
    provider = _seed_provider(tmp_path)
    writer = sqlite3.connect(provider.db_file)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE wal_pin_fixture(value INTEGER NOT NULL)")
        writer.commit()
        wal_path = Path(f"{provider.db_file}-wal")
        assert wal_path.is_file()
        session = _open_session(provider, stock_codes=("1101",))
        session.load_batch(("1101",))
        finished = session.finish()

        wal_pin = finished.source_clock.database_file_pins_start[1]
        assert wal_pin.role == "sqlite_wal"
        assert wal_pin.present is True
        assert wal_pin.sha256 == hashlib.sha256(wal_path.read_bytes()).hexdigest()
        assert finished.source_clock.database_file_pins_finish[1] == wal_pin
    finally:
        writer.close()


def test_wal_snapshot_with_missing_sidecars_does_not_touch_source(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path)
    writer = sqlite3.connect(provider.db_file)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE wal_open_fixture(value INTEGER NOT NULL)")
        writer.commit()
    finally:
        writer.close()
    wal_path = Path(f"{provider.db_file}-wal")
    assert wal_path.exists() is False
    shm_path = Path(f"{provider.db_file}-shm")
    assert shm_path.exists() is False
    before = _source_file_bytes_and_mtimes(provider.db_file)

    session = _open_snapshot_session(provider, label="wal_sidecars_absent", stock_codes=("1101",))
    session.load_batch(("1101",))
    finished = session.finish()

    snapshot_binding = finished.source_clock.snapshot_binding
    assert snapshot_binding.wal_sidecar_state == "absent"
    source_wal_pin = next(
        pin for pin in snapshot_binding.source_file_pins_start if pin.role == "sqlite_wal"
    )
    assert source_wal_pin.present is False
    assert snapshot_binding.source_file_pins_start == snapshot_binding.source_file_pins_finish
    assert _source_file_bytes_and_mtimes(provider.db_file) == before
    assert wal_path.exists() is False
    assert shm_path.exists() is False


def test_original_capture_bytes_are_rechecked_at_finish(tmp_path: Path) -> None:
    provider = _seed_provider(tmp_path)
    session = _open_session(provider, stock_codes=("2330",))
    session.load_batch(("2330",))
    csv_path = (
        provider.monthly_source_root
        / "monthly_revenue_mops_snapshots"
        / "mops_monthly_revenue_snapshot_fixture.csv"
    )
    with csv_path.open("ab") as stream:
        stream.write(b"\n")

    with pytest.raises(FundamentalReadSessionError, match="pins changed"):
        session.finish()


def test_cancel_before_open_and_after_last_batch_never_returns_finished(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path)
    with pytest.raises(FundamentalReadSessionCancelled):
        _open_session(provider, stock_codes=("2330",), cancel_callback=lambda: True)
    with pytest.raises(FundamentalReadSessionError, match="must_return_bool|exact bool"):
        _open_session(provider, stock_codes=("2330",), cancel_callback=lambda: 1)

    session = _open_session(provider, stock_codes=("1101",))
    session.load_batch(("1101",))
    assert session.cancel() is True
    with pytest.raises(FundamentalReadSessionCancelled):
        session.finish()


def _enlarge_synthetic_database(database: Path) -> None:
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE hash_cancel_fixture(payload BLOB NOT NULL)")
        connection.execute(
            "INSERT INTO hash_cancel_fixture(payload) VALUES (zeroblob(?))",
            (3 * 1024 * 1024,),
        )
        connection.commit()
    finally:
        connection.close()


def test_cancel_during_streamed_database_hash_closes_without_finished_result(
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path)
    _enlarge_synthetic_database(provider.db_file)

    class CancelDuringHash:
        enabled = False
        calls = 0

        def __call__(self) -> bool:
            if not self.enabled:
                return False
            self.calls += 1
            return self.calls >= 6

    cancel = CancelDuringHash()
    session = _open_session(
        provider,
        stock_codes=("1101",),
        cancel_callback=cancel,
    )
    session.load_batch(("1101",))
    cancel.enabled = True

    with pytest.raises(FundamentalReadSessionCancelled):
        session.finish()

    assert cancel.calls >= 6
    assert session.closed is True
    assert session.finished is False


def test_finish_rechecks_callback_after_final_source_hash_returns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _seed_provider(tmp_path)

    class ToggleCancel:
        requested = False

        def __call__(self) -> bool:
            return self.requested

    cancel = ToggleCancel()
    session = _open_session(
        provider,
        stock_codes=("1101",),
        cancel_callback=cancel,
    )
    session.load_batch(("1101",))
    original_pin = read_session_module._pin_database_files
    pin_calls = 0

    def pin_then_request_cancel(*args: Any, **kwargs: Any) -> Any:
        nonlocal pin_calls
        result = original_pin(*args, **kwargs)
        pin_calls += 1
        if pin_calls == 1:
            cancel.requested = True
        return result

    monkeypatch.setattr(read_session_module, "_pin_database_files", pin_then_request_cancel)

    with pytest.raises(FundamentalReadSessionCancelled):
        session.finish()

    assert pin_calls == 1
    assert session.closed is True
    assert session.finished is False
