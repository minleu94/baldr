from __future__ import annotations

from pathlib import Path
from threading import Thread

import pytest

from data_module.fundamental_read_snapshot import (
    FundamentalReadSnapshotError,
    FundamentalReadSnapshotSession,
)
from tests.test_daily_market_monthly_revenue_read_session_v1 import CUTOFF, _seed_provider


def _open_snapshot(
    provider_root: Path,
    snapshot_root: Path,
    *,
    codes: tuple[str, ...] = ("1101", "2330"),
) -> FundamentalReadSnapshotSession:
    provider = _seed_provider(provider_root)
    return FundamentalReadSnapshotSession.open(
        provider,
        snapshot_root=snapshot_root,
        stock_codes=codes,
        cutoff_at=CUTOFF,
    )


def test_idle_cancel_is_signal_only_and_owner_close_closes_real_sqlite_reader(
    tmp_path: Path,
) -> None:
    session = _open_snapshot(
        tmp_path / "provider",
        tmp_path / "snapshot_root",
        codes=("2330",),
    )
    outcome: list[object] = []

    def cancel_from_worker() -> None:
        outcome.append(session.cancel())
        outcome.append(session.closed)
        try:
            session.close()
        except BaseException as exc:
            outcome.append(type(exc).__name__)

    worker = Thread(target=cancel_from_worker)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert outcome == [True, False, "FundamentalReadSnapshotError"]
    assert session.closed is False

    session.close()
    assert session.closed is True
    assert (session.snapshot_root / "finished_source_clock.json").exists() is False


def test_normal_finish_closes_sqlite_reader_and_keeps_finished_token_after_close(
    tmp_path: Path,
) -> None:
    session = _open_snapshot(
        tmp_path / "provider",
        tmp_path / "snapshot_root",
    )
    session.load_batch(("1101", "2330"))

    finished = session.finish()
    assert finished.complete is True
    assert session.closed is True
    assert session.finish().identity_sha256 == finished.identity_sha256

    session.close()
    assert session.closed is True
    assert session.finish().identity_sha256 == finished.identity_sha256


def test_incomplete_finish_closes_reader_without_complete_manifest(
    tmp_path: Path,
) -> None:
    session = _open_snapshot(
        tmp_path / "provider",
        tmp_path / "snapshot_root",
    )
    session.load_batch(("1101",))

    with pytest.raises(Exception, match="missing 1 declared stock"):
        session.finish()

    assert session.closed is True
    assert (session.snapshot_root / "finished_source_clock.json").exists() is False


def test_context_cleanup_preserves_body_and_close_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_snapshot(
        tmp_path / "provider",
        tmp_path / "snapshot_root",
        codes=("2330",),
    )
    reader = session._read_session
    original_close = reader.close
    primary = RuntimeError("context body failure")
    cleanup = OSError("synthetic close failure")

    def fail_close() -> None:
        raise cleanup

    monkeypatch.setattr(reader, "close", fail_close)
    with pytest.raises(
        FundamentalReadSnapshotError,
        match="context_exit_cleanup_failed",
    ) as caught:
        session.__exit__(RuntimeError, primary, None)

    group = caught.value.__cause__
    assert isinstance(group, BaseExceptionGroup)
    assert primary in group.exceptions
    assert cleanup in group.exceptions
    assert session.closed is False

    monkeypatch.setattr(reader, "close", original_close)
    session.close()
    assert session.closed is True


def test_owner_thread_rejects_cross_thread_database_close(tmp_path: Path) -> None:
    session = _open_snapshot(
        tmp_path / "provider",
        tmp_path / "snapshot_root",
        codes=("2330",),
    )
    outcome: list[str] = []

    def close_from_worker() -> None:
        try:
            session.close()
        except BaseException as exc:
            outcome.append(str(exc))

    worker = Thread(target=close_from_worker)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert outcome == ["fundamental_snapshot_session_thread_affinity_violation"]
    assert session.closed is False

    session.close()
    assert session.closed is True
