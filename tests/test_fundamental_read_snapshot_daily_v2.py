"""真 typed cohort、SQLite隔離copy、V2完成附件與exact重開的反例。"""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Thread

import pytest

import data_module.fundamental_read_snapshot_daily_v2 as daily_module
import data_module.fundamental_read_snapshot as core_module
from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortError, DailyMonthlyRevenueCohortReader
from data_module.daily_source_snapshot import DailySourceSnapshotError
from data_module.fundamental_read_snapshot import (
    FundamentalReadSnapshotCancelled, FundamentalReadSnapshotError, FundamentalReadSnapshotSession,
    _load_finished_snapshot_manifest,
)
from data_module.fundamental_read_snapshot_cohort_v2 import (
    FinishedFundamentalSnapshotReadCohortV2, FundamentalReadSnapshotReferenceV2,
    FundamentalSnapshotSourceClockV2, encode_snapshot_reference_v2,
)
from data_module.fundamental_read_snapshot_daily_v2 import FundamentalReadSnapshotSessionV2
from data_module.selection_fact_readers import FundamentalReadBatchCandidateV2
from tests.test_selection_fundamental_daily_cohort_v2 import _daily_cohort_environment, _source_db_state
from tests.test_baldr_completion_p03_sources import CUTOFF


_CODES = ("1101", "2330")


def _open(tmp_path: Path):
    provider, reader, pin, _, market_roots = _daily_cohort_environment(tmp_path)
    source_state = _source_db_state(provider.db_file)
    session = FundamentalReadSnapshotSessionV2.open(
        provider, snapshot_root=tmp_path / "snapshots", stock_codes=_CODES,
        cutoff_at=CUTOFF, daily_monthly_cohort_reader=reader,
    )
    return provider, reader, pin, market_roots, source_state, session


def _complete(tmp_path: Path):
    provider, reader, pin, roots, source_state, session = _open(tmp_path)
    batch = session.load_batch(_CODES)
    finished = session.finish()
    return provider, reader, pin, roots, source_state, session, batch, finished


def test_saved_v2_snapshot_preserves_full_pin_and_exact_reopens_original_ledger(tmp_path: Path) -> None:
    provider, reader, pin, _, source_state, session, batch, finished = _complete(tmp_path)
    assert type(batch) is FundamentalReadBatchCandidateV2
    assert type(finished) is FinishedFundamentalSnapshotReadCohortV2
    assert type(finished.source_clock) is FundamentalSnapshotSourceClockV2
    assert finished.source_clock.cohort_pin == pin
    assert finished.source_clock.availability_status == "cohort_hour_bound"
    assert finished.source_clock.formal_pit_eligible is False
    assert finished.source_clock.historical_pit_eligible is False
    assert finished.processed_stock_codes == _CODES
    assert session.closed and session.finished
    manifest_path = session.snapshot_root / "finished_source_clock.json"
    original_manifest = manifest_path.read_bytes()
    assert finished.finished_manifest_sha256 == sha256(original_manifest).hexdigest()
    manifest = json.loads(original_manifest)
    assert manifest["schema_version"] == "selection-fundamental-read-snapshot.v2"
    assert manifest["cohort_pin_sha256"] == pin.cohort_sha256
    assert manifest["source_clock"]["cohort_pin"] == pin.to_dict()
    reference = session.source_reference
    assert type(reference) is FundamentalReadSnapshotReferenceV2
    raw = encode_snapshot_reference_v2(reference)
    reopened = FundamentalReadSnapshotSessionV2.open_exact(
        provider, snapshot_root=tmp_path / "exact-reopen", source_reference=raw,
        expected_reference_sha256=sha256(raw).hexdigest(), stock_codes=_CODES,
        cutoff_at=CUTOFF, daily_monthly_cohort_reader=reader,
    )
    with reopened:
        fresh_batch = reopened.load_batch(_CODES)
        fresh = reopened.finish()
        assert fresh_batch.result_identity_sha256 == batch.result_identity_sha256
        assert fresh.result_identity_by_stock == finished.result_identity_by_stock
        assert fresh.result_status_counts == finished.result_status_counts
        assert fresh.source_clock.cohort_pin == pin
        assert fresh.source_clock.source_content_identity_sha256 == finished.source_clock.source_content_identity_sha256
        assert fresh.source_clock.identity_sha256 != finished.source_clock.identity_sha256
        assert fresh.session_id != finished.session_id
        assert reopened.source_reference.daily_cohort_sha256 == pin.cohort_sha256
    assert reopened.closed
    assert manifest_path.read_bytes() == original_manifest
    assert _source_db_state(provider.db_file) == source_state


def test_v1_decoder_and_public_finish_cannot_accept_v2(tmp_path: Path) -> None:
    _, _, _, _, _, session, _, _ = _complete(tmp_path)
    with pytest.raises(FundamentalReadSnapshotError):
        _load_finished_snapshot_manifest(session.snapshot_root)
    with pytest.raises(FundamentalReadSnapshotError, match="v1_refuses_v2"):
        session._core.finish()
    with pytest.raises(FundamentalReadSnapshotError, match="v1_refuses_v2"):
        _ = session._core.source_reference


def test_reader_identity_is_rejected_before_copy_or_sqlite_open(tmp_path: Path, monkeypatch) -> None:
    provider, reader, pin, market_readers, _ = _daily_cohort_environment(tmp_path)
    wrong = DailyMonthlyRevenueCohortReader(pin=pin, market_readers=market_readers, expected_cohort_sha256=pin.cohort_sha256)
    def forbidden_copy(*args, **kwargs):
        raise AssertionError("錯reader不得產生copy")
    monkeypatch.setattr(daily_module, "_capture_snapshot", forbidden_copy)
    with pytest.raises(FundamentalReadSnapshotError, match="reader_identity"):
        FundamentalReadSnapshotSessionV2.open(provider, snapshot_root=tmp_path / "no-copy",
                                             stock_codes=_CODES, cutoff_at=CUTOFF,
                                             daily_monthly_cohort_reader=wrong)
    assert provider.daily_source_snapshot_reader is reader
    assert not (tmp_path / "no-copy").exists()


def test_future_cohort_is_rejected_before_copy_even_for_missing_stock(tmp_path: Path, monkeypatch) -> None:
    provider, reader, pin, _, _ = _daily_cohort_environment(tmp_path)
    original_state = _source_db_state(provider.db_file)
    def forbidden_copy(*args, **kwargs):
        raise AssertionError("未到批次可用小時不可開copy，即使該股沒有列")
    monkeypatch.setattr(daily_module, "_capture_snapshot", forbidden_copy)
    with pytest.raises(FundamentalReadSnapshotError, match="cohort_after_decision_cutoff"):
        FundamentalReadSnapshotSessionV2.open(
            provider, snapshot_root=tmp_path / "future-no-copy", stock_codes=("1101",),
            cutoff_at=pin.available_hour - timedelta(microseconds=1), daily_monthly_cohort_reader=reader,
        )
    assert not (tmp_path / "future-no-copy").exists()
    assert _source_db_state(provider.db_file) == original_state


def test_wrong_external_reference_digest_is_rejected_before_new_copy(tmp_path: Path) -> None:
    provider, reader, _, _, _, session, _, _ = _complete(tmp_path)
    with pytest.raises(ValueError):
        FundamentalReadSnapshotSessionV2.open_exact(
            provider, snapshot_root=tmp_path / "no-copy", source_reference=session.source_reference,
            expected_reference_sha256="0" * 64, stock_codes=_CODES, cutoff_at=CUTOFF,
            daily_monthly_cohort_reader=reader,
        )
    assert not (tmp_path / "no-copy").exists()


def test_final_root_publication_revalidation_rejects_second_market_change(tmp_path: Path, monkeypatch) -> None:
    _, reader, _, roots, _, session = _open(tmp_path)
    session.load_batch(_CODES)
    original = DailyMonthlyRevenueCohortReader.verify_cohort

    def mutate_at_final_publication(self):
        pending = session.snapshot_root / "finished_source_clock.json"
        if self is reader and pending.exists():
            receipt = next(roots["tpex"].rglob("receipt.json"))
            receipt.write_bytes(b"{}")
        return original(self)

    monkeypatch.setattr(DailyMonthlyRevenueCohortReader, "verify_cohort", mutate_at_final_publication)
    with pytest.raises((DailySourceSnapshotError, DailyMonthlyRevenueCohortError)):
        session.finish()
    assert session.closed and not session.finished
    assert json.loads((session.snapshot_root / "attempt_status.json").read_bytes())["status"] == "failed"
    assert json.loads((session.snapshot_root / "finished_source_clock.json").read_bytes())["manifest_state"] == "candidate_pending_publication"


def test_cancel_during_final_revalidation_closes_without_completed_manifest(tmp_path: Path, monkeypatch) -> None:
    provider, reader, _, _, _ = _daily_cohort_environment(tmp_path)
    cancelled = False
    session = FundamentalReadSnapshotSessionV2.open(
        provider, snapshot_root=tmp_path / "snapshots", stock_codes=_CODES, cutoff_at=CUTOFF,
        daily_monthly_cohort_reader=reader, cancel_callback=lambda: cancelled,
    )
    session.load_batch(_CODES)
    original = DailyMonthlyRevenueCohortReader.verify_cohort

    def cancel_at_publication(self):
        nonlocal cancelled
        result = original(self)
        if self is reader and (session.snapshot_root / "finished_source_clock.json").exists():
            cancelled = True
        return result

    monkeypatch.setattr(DailyMonthlyRevenueCohortReader, "verify_cohort", cancel_at_publication)
    with pytest.raises(FundamentalReadSnapshotCancelled):
        session.finish()
    assert session.closed and not session.finished
    assert json.loads((session.snapshot_root / "finished_source_clock.json").read_bytes())["manifest_state"] == "candidate_pending_publication"


@pytest.mark.parametrize("late_value", [True, "invalid-bool", "raise"])
def test_late_external_cancel_cannot_retract_published_snapshot(tmp_path: Path, monkeypatch, late_value) -> None:
    provider, reader, _, _, _ = _daily_cohort_environment(tmp_path)
    committed = False

    def cancel_callback():
        if not committed:
            return False
        if late_value == "raise":
            raise RuntimeError("完成後原 callback 已失效")
        return late_value

    session = FundamentalReadSnapshotSessionV2.open(
        provider, snapshot_root=tmp_path / "snapshots", stock_codes=_CODES, cutoff_at=CUTOFF,
        daily_monthly_cohort_reader=reader, cancel_callback=cancel_callback,
    )
    session.load_batch(_CODES)
    original = core_module._write_attempt_status

    def set_cancel_after_commit(*args, **kwargs):
        nonlocal committed
        result = original(*args, **kwargs)
        if kwargs.get("status") == "complete":
            committed = True
        return result

    monkeypatch.setattr(core_module, "_write_attempt_status", set_cancel_after_commit)
    finished = session.finish()
    assert committed and session.finished and session.closed
    assert session.cancel() is False
    assert session.finish() == finished
    assert session.source_reference.finished_manifest_sha256 == finished.finished_manifest_sha256
    assert json.loads((session.snapshot_root / "attempt_status.json").read_bytes())["status"] == "complete"


def test_finished_reference_rejects_relative_formal_root_overlap(tmp_path: Path, monkeypatch) -> None:
    _, _, _, _, _, session, _, _ = _complete(tmp_path)
    relative_root = os.path.relpath(session.snapshot_root.parent, Path.cwd())
    assert not Path(relative_root).is_absolute()
    monkeypatch.setenv("DATA_ROOT", relative_root)
    with pytest.raises(FundamentalReadSnapshotError, match="overlaps_formal_data_root"):
        _ = session.source_reference


def test_published_reference_still_rejects_mutated_second_market(tmp_path: Path) -> None:
    _, _, _, roots, _, session, _, _ = _complete(tmp_path)
    receipt = next(roots["tpex"].rglob("receipt.json"))
    receipt.write_bytes(b"{}")
    with pytest.raises((DailySourceSnapshotError, DailyMonthlyRevenueCohortError)):
        _ = session.source_reference
    assert session.finished and session.closed


def test_partial_declared_cohort_and_idle_cancel_never_issue_reference(tmp_path: Path) -> None:
    _, _, _, _, _, session = _open(tmp_path)
    session.load_batch((_CODES[0],))
    with pytest.raises(FundamentalReadSnapshotError):
        _ = session.source_reference
    assert session.cancel()
    session.close()
    assert session.closed and not session.finished
    assert not (session.snapshot_root / "finished_source_clock.json").exists()


def test_exact_reopen_rejects_original_database_drift(tmp_path: Path) -> None:
    provider, reader, _, _, _, session, _, _ = _complete(tmp_path)
    reference = session.source_reference
    raw = encode_snapshot_reference_v2(reference)
    provider.db_file.write_bytes(provider.db_file.read_bytes() + b"changed")
    with pytest.raises(FundamentalReadSnapshotError, match="original_database_changed"):
        FundamentalReadSnapshotSessionV2.open_exact(provider, snapshot_root=tmp_path / "no-reopen",
            source_reference=raw, expected_reference_sha256=sha256(raw).hexdigest(), stock_codes=_CODES,
            cutoff_at=CUTOFF, daily_monthly_cohort_reader=reader)
    assert not (tmp_path / "no-reopen").exists()


def test_foreign_thread_cancel_is_signal_only_and_owner_closes_reader(tmp_path: Path) -> None:
    _, _, _, _, _, session = _open(tmp_path)
    outcomes = []
    def cancel_foreign():
        outcomes.extend([session.cancel(), session.closed])
        try:
            session.close()
        except FundamentalReadSnapshotError:
            outcomes.append("foreign-close-refused")
    worker = Thread(target=cancel_foreign)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert outcomes == [True, False, "foreign-close-refused"]
    session.close()
    assert session.closed
