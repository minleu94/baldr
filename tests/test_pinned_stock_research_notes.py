from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkV1Error,
    create_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY,
)
from app_module.dtos.decision_continuity_dtos import IDENTITY_STATUS_UNKNOWN
from app_module.journal_service import JournalService
from app_module.personal_data_paths import to_internal_io_path
from app_module.personal_journal_paths import resolve_personal_journal_paths
from app_module.pinned_stock_research_notes import (
    PinnedStockResearchNoteConflict,
    PinnedStockResearchNoteError,
    PinnedStockResearchNoteNotFound,
    PinnedStockResearchNoteService,
    PinnedStockResearchSource,
    verify_pinned_stock_research_source,
)
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)
import app_module.pinned_stock_research_notes as notes_module


def _journal_service(tmp_path: Path) -> tuple[JournalService, Any]:
    data_root = tmp_path / "FA_Data"
    paths = resolve_personal_journal_paths(
        data_root,
        personal_root=data_root / "personal",
    )
    config = SimpleNamespace(output_root=paths.personal_paths.legacy_output_root)
    return JournalService(config, journal_paths=paths), paths


def _bookmark_for(
    store: dict[str, Any],
    stock_code: str,
    *,
    scroll_position: int = 0,
):
    session = _open_session(store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    return create_daily_market_technical_universe_price_bookmark_v1(
        query,
        page,
        stock_code,
        scroll_position=scroll_position,
    )


def _reopen_journal(paths: Any) -> JournalService:
    journal_paths = paths
    return JournalService(
        SimpleNamespace(output_root=journal_paths.personal_paths.legacy_output_root),
        journal_paths=journal_paths,
    )


def test_saved_note_reopens_with_exact_f07_bookmark_identity_and_clock(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = verify_pinned_stock_research_source(bookmark)
    note_text = " 觀察原價格與規則版本\n下次再核對 "

    saved = service.save(source, note_text, revision_id="price-note-1")
    assert saved.source == source
    assert saved.text == note_text
    assert saved.source.stock_code == bookmark.selected.stock_code
    assert saved.source.identity_sha256 == bookmark.bookmark_identity_sha256
    assert saved.source.data_date == (bookmark.selected.observation_date or "")
    assert saved.source.research_date == bookmark.selected.query.source.decision_date.isoformat()
    assert saved.source.snapshot_identity_sha256 == bookmark.selected.snapshot_identity_sha256
    assert service.save(source, note_text, revision_id="price-note-1") == saved

    revision = journal.list_decision_revisions()[0]
    bookmark_hash = sha256(bookmark.to_json().encode("utf-8")).hexdigest()
    identity = revision.decision_identity
    assert identity.stock_code == "S0001"
    assert identity.result_id == ""
    assert identity.decision_date == ""
    assert identity.identity_status == IDENTITY_STATUS_UNKNOWN
    assert identity.source_snapshot_id == bookmark.bookmark_identity_sha256
    assert identity.source_snapshot_hash == bookmark_hash
    assert revision.payload["source_type"] == "technical_price_research_note.v1"
    assert revision.payload["source_id"] == bookmark.bookmark_identity_sha256
    assert revision.payload["source_snapshot_id"] == bookmark.bookmark_identity_sha256
    assert revision.payload["source_snapshot_hash"] == bookmark_hash
    assert revision.payload["linked_type"] == "technical_price_research_bookmark"
    assert revision.payload["linked_id"] == bookmark.bookmark_identity_sha256
    assert tuple(revision.payload["tags"]) == (
        "technical_price_research_bookmark:" + bookmark.to_json(),
        "technical_price_research_data_date:" + (bookmark.selected.observation_date or ""),
        "technical_price_research_date:" + bookmark.selected.query.source.decision_date.isoformat(),
    )
    assert saved.recorded_at == revision.created_at
    assert not list(tmp_path.rglob("trades.jsonl"))

    reopened = PinnedStockResearchNoteService(_reopen_journal(paths))
    assert reopened.get_note(saved.revision_id) == saved
    assert reopened.list_notes() == (saved,)
    assert reopened.verify_source(saved).bookmark.to_json() == bookmark.to_json()


def test_direct_revision_and_independent_note_roots_reopen_from_new_journal(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(_bookmark_for(exact_price_store, "S0001"))

    first = service.save(source, "第一篇原始判斷", revision_id="price-note-a1")
    first_revision = service.save(
        source,
        "第一篇直接修訂",
        revision_id="price-note-a2",
        revision_of=first.revision_id,
    )
    second = service.save(source, "第二篇獨立判斷", revision_id="price-note-b1")

    revisions_by_id = {item.revision_id: item for item in journal.list_decision_revisions()}
    first_root = revisions_by_id[first.revision_id].entity_id
    second_root = revisions_by_id[second.revision_id].entity_id
    assert first_root != second_root
    assert revisions_by_id[first_revision.revision_id].entity_id == first_root
    assert revisions_by_id[first_revision.revision_id].revision_of == first.revision_id
    assert service.get_note(first.revision_id).text == "第一篇原始判斷"
    assert service.get_note(first_revision.revision_id).text == "第一篇直接修訂"

    reopened = PinnedStockResearchNoteService(_reopen_journal(paths))
    reopened_notes = {note.revision_id: note for note in reopened.list_notes()}
    assert reopened_notes == {
        note.revision_id: note for note in (first, first_revision, second)
    }
    assert reopened.get_note(first.revision_id).source.bookmark_json == source.bookmark_json
    assert reopened.get_note(first_revision.revision_id).revision_of == first.revision_id


def test_reusing_revision_id_with_different_content_is_rejected_without_write(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
) -> None:
    journal, _paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(
        _bookmark_for(exact_price_store, "S0001")
    )
    saved = service.save(source, "原始判斷", revision_id="price-note-idempotency")
    before = tuple(journal.list_journal_history())

    with pytest.raises(PinnedStockResearchNoteConflict, match="different saved content"):
        service.save(
            source,
            "不同內容不得覆寫",
            revision_id=saved.revision_id,
        )

    assert tuple(journal.list_journal_history()) == before
    assert service.get_note(saved.revision_id).text == "原始判斷"


def test_parent_must_be_the_same_exact_bookmark_and_stock(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    first_bookmark = _bookmark_for(exact_price_store, "S0001")
    same_stock_other_bookmark = _bookmark_for(
        exact_price_store, "S0001", scroll_position=1
    )
    other_stock_bookmark = _bookmark_for(exact_price_store, "S0002")
    first_source = verify_pinned_stock_research_source(first_bookmark)
    first = service.save(first_source, "原始判斷", revision_id="price-note-parent")
    before = tuple(journal.list_journal_history())

    with pytest.raises(PinnedStockResearchNoteConflict, match="another exact price bookmark"):
        service.save(
            verify_pinned_stock_research_source(same_stock_other_bookmark),
            "收藏錨點不同，不沿用父版",
            revision_id="price-note-other-bookmark",
            revision_of=first.revision_id,
        )
    with pytest.raises(PinnedStockResearchNoteConflict, match="another exact price bookmark"):
        service.save(
            verify_pinned_stock_research_source(other_stock_bookmark),
            "不得跨股修訂",
            revision_id="price-note-other-stock",
            revision_of=first.revision_id,
        )

    assert tuple(journal.list_journal_history()) == before
    assert service.get_note(first.revision_id).text == "原始判斷"
    assert service.list_notes(stock_code="S0001") == (first,)
    assert service.list_notes(stock_code="S0002") == ()
    with pytest.raises(PinnedStockResearchNoteNotFound):
        service.get_note("missing-price-note")
    assert _reopen_journal(paths).list_decision_revisions()


def test_missing_original_bookmark_keeps_saved_text_readable_but_blocks_verify_and_revision(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(_bookmark_for(exact_price_store, "S0001"))
    note = service.save(source, "保留可讀原文", revision_id="price-note-kept")
    history_before = tuple(journal.list_journal_history())
    original_reader = notes_module.read_daily_market_technical_universe_price_bookmark_v1

    def missing_source(bookmark, *, cancel_callback=None):
        raise DailyMarketTechnicalUniversePriceBookmarkV1Error(
            "technical_universe_price_bookmark_read_failed",
            "fixture exact source is unavailable",
        )

    monkeypatch.setattr(
        notes_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        missing_source,
    )
    assert service.get_note(note.revision_id).text == "保留可讀原文"
    assert service.list_notes() == (note,)
    with pytest.raises(PinnedStockResearchNoteError, match="fixture exact source is unavailable") as error:
        service.verify_source(note)
    assert error.value.code == "technical_universe_price_bookmark_read_failed"
    with pytest.raises(PinnedStockResearchNoteError):
        service.save(
            source,
            "來源失效時不可追加",
            revision_id="price-note-blocked-revision",
            revision_of=note.revision_id,
        )
    assert tuple(journal.list_journal_history()) == history_before

    monkeypatch.setattr(
        notes_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        original_reader,
    )
    assert service.verify_source(note).bookmark.to_json() == source.bookmark_json
    assert paths.journal_file.exists()


def test_real_f07_plan_removal_blocks_source_use_but_keeps_saved_note_readable(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = verify_pinned_stock_research_source(bookmark)
    note = service.save(source, "原件缺少時仍保留這段判斷", revision_id="price-note-missing-plan")

    plan_path = (
        Path(to_internal_io_path(exact_price_store["store_root"]))
        / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY
        / "generations"
        / exact_price_store["plan"].generation_identity_sha256
        / "plan.json"
    )
    original_plan_bytes = plan_path.read_bytes()
    original_journal_bytes = paths.journal_file.read_bytes()
    try:
        plan_path.unlink()

        with pytest.raises(PinnedStockResearchNoteError) as verify_error:
            service.verify_source(note)
        assert verify_error.value.code
        with pytest.raises(PinnedStockResearchNoteError):
            service.save(
                source,
                "原件缺少時不可追加",
                revision_id="price-note-missing-plan-revision",
                revision_of=note.revision_id,
            )

        assert service.get_note(note.revision_id).text == "原件缺少時仍保留這段判斷"
        assert paths.journal_file.read_bytes() == original_journal_bytes
    finally:
        plan_path.write_bytes(original_plan_bytes)

    assert plan_path.read_bytes() == original_plan_bytes
    assert paths.journal_file.read_bytes() == original_journal_bytes


def test_stale_parent_cannot_append_after_a_newer_revision(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(_bookmark_for(exact_price_store, "S0001"))
    first = service.save(source, "第一版判斷", revision_id="price-note-head-1")
    latest = service.save(
        source,
        "第二版判斷",
        revision_id="price-note-head-2",
        revision_of=first.revision_id,
    )
    original_journal_bytes = paths.journal_file.read_bytes()

    with pytest.raises(PinnedStockResearchNoteConflict, match="journal append conflict"):
        service.save(
            source,
            "不得沿過時父版分岔",
            revision_id="price-note-stale-head",
            revision_of=first.revision_id,
        )

    assert paths.journal_file.read_bytes() == original_journal_bytes
    assert service.list_notes() == (first, latest)
    with pytest.raises(PinnedStockResearchNoteNotFound):
        service.get_note("price-note-stale-head")


def test_tampered_bookmark_and_invalid_text_never_write_journal(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    bookmark = _bookmark_for(exact_price_store, "S0001")
    before = paths.journal_file.read_bytes() if paths.journal_file.exists() else None
    changed = bookmark.to_json().replace('"scroll_position":0', '"scroll_position":1')
    assert changed != bookmark.to_json()
    with pytest.raises(PinnedStockResearchNoteError):
        PinnedStockResearchSource(changed)

    source = verify_pinned_stock_research_source(bookmark)
    for text in (" \t ", "x" * 8001):
        with pytest.raises(PinnedStockResearchNoteError):
            service.save(source, text, revision_id="invalid-price-note")
    after = paths.journal_file.read_bytes() if paths.journal_file.exists() else None
    assert after == before
    assert journal.list_decision_revisions() == []


def test_competing_journal_write_rejects_stale_pinned_note_without_overwrite(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, _paths = _journal_service(tmp_path)
    competing_journal, _ = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    competing = PinnedStockResearchNoteService(competing_journal)
    source = verify_pinned_stock_research_source(_bookmark_for(exact_price_store, "S0001"))
    original_append = journal.record_research_action

    def append_after_competing_write(*args, **kwargs):
        competing.save(source, "先完成的筆記", revision_id="price-note-winner")
        return original_append(*args, **kwargs)

    monkeypatch.setattr(journal, "record_research_action", append_after_competing_write)
    with pytest.raises(PinnedStockResearchNoteConflict, match="journal append conflict"):
        service.save(source, "過時 Journal 快照不得覆蓋", revision_id="price-note-stale")

    assert [note.revision_id for note in competing.list_notes()] == ["price-note-winner"]
    with pytest.raises(PinnedStockResearchNoteNotFound):
        competing.get_note("price-note-stale")


def test_precancelled_source_verification_does_not_read_source_or_write_journal(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = verify_pinned_stock_research_source(bookmark)
    note = service.save(source, "保留預取消前已保存的內容", revision_id="price-note-precancel")
    journal_before = paths.journal_file.read_bytes()
    reader_calls: list[object] = []

    def forbidden_reader(bookmark, *, cancel_callback=None):
        reader_calls.append((bookmark, cancel_callback))
        raise AssertionError("pre-cancelled verification must not open the exact source")

    monkeypatch.setattr(
        notes_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        forbidden_reader,
    )
    cancel_checks: list[bool] = []

    def cancelled() -> bool:
        cancel_checks.append(True)
        return True

    with pytest.raises(InterruptedError):
        verify_pinned_stock_research_source(bookmark, cancel_callback=cancelled)
    with pytest.raises(InterruptedError):
        service.verify_source(note, cancel_callback=cancelled)

    assert len(cancel_checks) >= 2
    assert reader_calls == []
    assert paths.journal_file.read_bytes() == journal_before


def test_verify_source_forwards_cancel_callback_and_preserves_reader_cancellation(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = verify_pinned_stock_research_source(bookmark)
    note = service.save(source, "閱讀時取消不可改寫 Journal", revision_id="price-note-reader-cancel")
    journal_before = paths.journal_file.read_bytes()
    cancel_callback = lambda: False
    reader_calls: list[tuple[object, object]] = []

    def cancelling_reader(bookmark, *, cancel_callback=None):
        reader_calls.append((bookmark, cancel_callback))
        raise InterruptedError("simulated cancellation during exact read")

    monkeypatch.setattr(
        notes_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        cancelling_reader,
    )

    with pytest.raises(InterruptedError, match="simulated cancellation during exact read"):
        service.verify_source(note, cancel_callback=cancel_callback)

    assert len(reader_calls) == 1
    assert reader_calls[0][1] is cancel_callback
    assert paths.journal_file.read_bytes() == journal_before


def test_uncancelled_verify_uses_real_exact_source_and_rejects_different_bookmark(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = verify_pinned_stock_research_source(bookmark)
    note = service.save(source, "未取消時仍精確核對來源", revision_id="price-note-verified-source")
    journal_before = paths.journal_file.read_bytes()
    cancel_callback = lambda: False
    original_reader = notes_module.read_daily_market_technical_universe_price_bookmark_v1
    reader_callbacks: list[object] = []

    def tracked_reader(bookmark, *, cancel_callback=None):
        reader_callbacks.append(cancel_callback)
        return original_reader(bookmark, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        notes_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        tracked_reader,
    )

    state = service.verify_source(note, cancel_callback=cancel_callback)

    assert state.bookmark.to_json() == note.source.bookmark_json
    assert state.bookmark.selected.stock_code == note.source.stock_code == "S0001"
    assert (
        state.bookmark.selected.snapshot_identity_sha256
        == note.source.snapshot_identity_sha256
    )
    assert reader_callbacks and all(item is cancel_callback for item in reader_callbacks)
    assert paths.journal_file.read_bytes() == journal_before

    other_bookmark = _bookmark_for(exact_price_store, "S0001", scroll_position=1)

    def mismatched_reader(bookmark, *, cancel_callback=None):
        reader_callbacks.append(cancel_callback)
        return original_reader(other_bookmark, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        notes_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        mismatched_reader,
    )
    with pytest.raises(PinnedStockResearchNoteConflict, match="different bookmark"):
        service.verify_source(note, cancel_callback=cancel_callback)

    assert reader_callbacks[-1] is cancel_callback
    assert paths.journal_file.read_bytes() == journal_before

@pytest.mark.parametrize(
    ("code", "callback_supplied", "requested", "cancelled"),
    [
        ("technical_parent_v4_read_cancelled", True, True, True),
        ("technical_parent_v4_read_cancelled", True, False, False),
        ("technical_parent_v4_read_cancelled", False, True, False),
        ("technical_universe_v4_technical_parent_v4_read_cancelled", True, True, True),
        ("technical_universe_v4_technical_parent_v4_read_cancelled", True, False, False),
        ("technical_universe_v4_read_cancelled", True, True, True),
        ("technical_snapshot_v4_file_type_rejected", True, True, False),
    ],
)
def test_only_explicit_typed_cancellation_with_requested_callback_is_translated(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    callback_supplied: bool,
    requested: bool,
    cancelled: bool,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(_bookmark_for(exact_price_store, "S0001"))
    note = service.save(source, "取消不能掩蓋其他來源錯誤", revision_id="typed-cancel")
    before = paths.journal_file.read_bytes()
    cancel_state = [False]
    reader_error = DailyMarketTechnicalUniversePriceBookmarkV1Error(code, code)

    def typed_failure(bookmark, *, cancel_callback=None):
        cancel_state[0] = requested
        raise reader_error

    monkeypatch.setattr(
        notes_module, "read_daily_market_technical_universe_price_bookmark_v1", typed_failure
    )
    callback = (lambda: cancel_state[0]) if callback_supplied else None
    if cancelled:
        with pytest.raises(InterruptedError) as error:
            service.verify_source(note, cancel_callback=callback)
        assert error.value.__cause__ is reader_error
    else:
        with pytest.raises(PinnedStockResearchNoteError) as source_error:
            service.verify_source(note, cancel_callback=callback)
        assert source_error.value.code == code
        assert source_error.value.__cause__ is reader_error
    assert paths.journal_file.read_bytes() == before
