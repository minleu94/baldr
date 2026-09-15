"""Increment B：研究動作控制層的 identity、重試與讀回契約。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_NOTE,
    ACTION_REVIEW_SCHEDULED,
    ACTION_SKIPPED,
    DecisionIdentity,
)
from app_module.journal_service import JournalService


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=root / "output",
        resolve_output_path=lambda name: root / "output" / name,
    )


def _identity(
    *,
    result_id: str = "result-001",
    stock_code: str = "2330",
    snapshot_hash: str = "sha256:one",
) -> DecisionIdentity:
    return DecisionIdentity(
        result_id=result_id,
        stock_code=stock_code,
        source_snapshot_id="snapshot-001",
        source_snapshot_hash=snapshot_hash,
        decision_date="2026-09-14",
    )


def test_candidate_history_is_exact_result_and_stock_and_has_no_trade(tmp_path: Path) -> None:
    journal = JournalService(_config(tmp_path))
    controller = DecisionContinuityController(journal)

    first = controller.accept(_identity(), request_id="accept-2330")
    other_stock = controller.skip(
        _identity(stock_code="2317"), request_id="skip-2317"
    )
    other_result = controller.accept(
        _identity(result_id="result-002"), request_id="accept-other-result"
    )

    assert first.success and other_stock.success and other_result.success
    assert controller.read_state(_identity()).decision_status == "accepted"
    assert [item.revision_id for item in controller.read_state(_identity()).history] == [
        "accept-2330"
    ]
    assert controller.read_state(_identity(stock_code="2317")).decision_status == "skipped"
    assert controller.read_state(_identity(result_id="result-002")).decision_status == "accepted"
    assert not journal.store.trades_file.exists()


def test_accept_review_note_reopen_preserves_intent_and_review(tmp_path: Path) -> None:
    journal = JournalService(_config(tmp_path))
    controller = DecisionContinuityController(journal)
    identity = _identity()

    accepted = controller.accept(identity, request_id="accept-1")
    reviewed = controller.schedule_review(
        identity,
        next_review_at="2026-09-20T10:30:00+08:00",
        request_id="review-1",
    )
    noted = controller.note(identity, note="確認營收與風險", request_id="note-1")

    assert accepted.success and reviewed.success and noted.success
    reopened = DecisionContinuityController(JournalService(_config(tmp_path)))
    state = reopened.read_state(identity)
    assert state.decision_status == "accepted"
    assert state.next_review_at == "2026-09-20T10:30:00+08:00"
    assert state.active_note_count == 1
    assert [item.action for item in state.history] == [
        ACTION_ACCEPTED,
        ACTION_REVIEW_SCHEDULED,
        ACTION_NOTE,
    ]

    skipped = reopened.skip(identity, request_id="skip-1")
    assert skipped.success
    assert reopened.read_state(identity).decision_status == "skipped"


def test_same_request_is_idempotent_after_new_action_and_snapshot_mismatch_rejected(
    tmp_path: Path,
) -> None:
    journal = JournalService(_config(tmp_path))
    controller = DecisionContinuityController(journal)
    identity = _identity()

    original = controller.accept(identity, request_id="same-request")
    assert original.success
    assert original.revision is not None
    later = controller.skip(identity, request_id="later-request")
    assert later.success

    redelivered = controller.accept(identity, request_id="same-request")
    assert redelivered.success
    assert redelivered.revision == original.revision
    assert redelivered.revision is not None
    assert redelivered.revision.revision_of == original.revision.revision_of
    assert [item.revision_id for item in journal.list_decision_revisions()] == [
        "same-request",
        "later-request",
    ]

    changed_snapshot = controller.accept(
        _identity(snapshot_hash="sha256:changed"),
        request_id="same-request",
    )
    assert not changed_snapshot.success
    assert changed_snapshot.error_code == "journal_revision_event_conflict"
    assert len(journal.list_decision_revisions()) == 2


def test_unknown_conflict_and_invalid_review_are_not_writable(tmp_path: Path) -> None:
    journal = JournalService(_config(tmp_path))
    controller = DecisionContinuityController(journal)

    unknown = controller.accept(
        DecisionIdentity(
            result_id="result-unknown",
            stock_code="2330",
            identity_status="unknown",
        ),
        request_id="unknown",
    )
    conflict = controller.accept(
        DecisionIdentity(
            result_id="result-conflict",
            stock_code="2330",
            identity_status="conflict",
        ),
        request_id="conflict",
    )
    invalid_review = controller.schedule_review(
        _identity(), next_review_at="not-a-date", request_id="bad-review"
    )

    assert not unknown.success and not unknown.state.can_write
    assert not conflict.success and not conflict.state.can_write
    assert not invalid_review.success
    assert invalid_review.error_code == "invalid_next_review_at"
    assert not invalid_review.readback_verified
    assert journal.list_decision_revisions() == []


def test_write_success_with_readback_failure_is_explicit_and_retry_does_not_duplicate(
    tmp_path: Path,
) -> None:
    class FlakyJournal:
        def __init__(self, delegate: JournalService) -> None:
            self.delegate = delegate
            self.fail_reads = False

        def record_research_action(self, *args, **kwargs):
            result = self.delegate.record_research_action(*args, **kwargs)
            self.fail_reads = True
            return result

        def list_decision_revisions(self):
            if self.fail_reads:
                raise RuntimeError("readback temporarily unavailable")
            return self.delegate.list_decision_revisions()

    delegate = JournalService(_config(tmp_path))
    flaky = FlakyJournal(delegate)
    controller = DecisionContinuityController(flaky)  # type: ignore[arg-type]
    identity = _identity()

    written = controller.accept(identity, request_id="readback-1")
    assert written.success
    assert not written.readback_verified
    assert "讀回失敗" in written.message

    flaky.fail_reads = False
    redelivered = controller.accept(identity, request_id="readback-1")
    assert redelivered.success and redelivered.readback_verified
    assert len(delegate.list_decision_revisions()) == 1
