from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
)
from app_module.pinned_stock_research_notes import (
    PinnedStockResearchNote,
    PinnedStockResearchNoteConflict,
    PinnedStockResearchNoteError,
    PinnedStockResearchNoteSaveReadback,
    PinnedStockResearchNoteService,
    verify_pinned_stock_research_source,
)
from tests.test_daily_market_technical_universe_price_query_v1 import exact_price_store
from tests.test_pinned_stock_research_notes import _bookmark_for, _journal_service
import app_module.pinned_stock_research_notes as notes_module


def test_save_with_readback_returns_same_action_state_and_exact_journal_history(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, _paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    bookmark = _bookmark_for(exact_price_store, "S0001")
    source = verify_pinned_stock_research_source(bookmark)
    original_reader = (
        notes_module.read_daily_market_technical_universe_price_bookmark_v1
    )
    fresh_reads: list[str] = []

    def tracked_reader(bookmark, *, cancel_callback=None):
        fresh_reads.append(bookmark.to_json())
        return original_reader(bookmark, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        notes_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        tracked_reader,
    )

    first = service.save_with_readback(
        source,
        "第一筆原始判斷",
        revision_id="price-note-readback-1",
    )
    second = service.save_with_readback(
        source,
        "第二筆原始判斷",
        revision_id="price-note-readback-2",
        revision_of=first.note.revision_id,
    )

    assert type(first) is PinnedStockResearchNoteSaveReadback
    assert type(first.note) is PinnedStockResearchNote
    assert (
        type(first.source_state)
        is DailyMarketTechnicalUniversePriceBookmarkStateV1
    )
    assert first.source_state.bookmark.to_json() == source.bookmark_json
    assert first.notes == (first.note,)
    assert first.note.text == "第一筆原始判斷"
    assert first.note.revision_of is None
    assert first.note.recorded_at

    assert (
        type(second.source_state)
        is DailyMarketTechnicalUniversePriceBookmarkStateV1
    )
    assert second.source_state.bookmark.to_json() == source.bookmark_json
    assert second.notes == service.list_notes(stock_code=source.stock_code)
    assert tuple(note.revision_id for note in second.notes) == (
        "price-note-readback-1",
        "price-note-readback-2",
    )
    assert second.note == next(
        note
        for note in second.notes
        if note.revision_id == "price-note-readback-2"
    )
    assert second.note.recorded_at == next(
        note.recorded_at
        for note in second.notes
        if note.revision_id == "price-note-readback-2"
    )
    assert second.note.text == "第二筆原始判斷"
    assert second.note.source.bookmark_json == source.bookmark_json
    assert second.note.revision_of == first.note.revision_id
    assert fresh_reads == [source.bookmark_json, source.bookmark_json]


def test_source_read_failure_rejects_before_journal_write(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(
        _bookmark_for(exact_price_store, "S0001")
    )
    before = paths.journal_file.read_bytes() if paths.journal_file.exists() else None

    def fail_reader(_bookmark, *, cancel_callback=None):
        raise RuntimeError("exact source unavailable")

    monkeypatch.setattr(
        notes_module,
        "read_daily_market_technical_universe_price_bookmark_v1",
        fail_reader,
    )

    with pytest.raises(
        PinnedStockResearchNoteError,
        match="exact source unavailable",
    ):
        service.save_with_readback(
            source,
            "不得在來源失敗時保存",
            revision_id="price-note-source-failed",
        )

    after = paths.journal_file.read_bytes() if paths.journal_file.exists() else None
    assert after == before
    assert journal.list_decision_revisions() == []


@pytest.mark.parametrize("bad_state_kind", ("untyped", "different_bookmark"))
def test_noncanonical_or_untyped_source_state_rejects_before_journal_write(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    bad_state_kind: str,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(
        _bookmark_for(exact_price_store, "S0001")
    )
    before = paths.journal_file.read_bytes() if paths.journal_file.exists() else None
    if bad_state_kind == "untyped":
        bad_state = object()
    else:
        other_source = verify_pinned_stock_research_source(
            _bookmark_for(exact_price_store, "S0001", scroll_position=1)
        )
        bad_state = notes_module._read_exact_source(other_source)

    monkeypatch.setattr(notes_module, "_read_exact_source", lambda _source: bad_state)

    with pytest.raises(
        PinnedStockResearchNoteConflict,
        match="source readback differs",
    ):
        service.save_with_readback(
            source,
            "不得保存錯誤來源狀態",
            revision_id=f"price-note-bad-state-{bad_state_kind}",
        )

    after = paths.journal_file.read_bytes() if paths.journal_file.exists() else None
    assert after == before
    assert journal.list_decision_revisions() == []


def test_save_with_readback_keeps_journal_compare_and_swap_guard(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, _paths = _journal_service(tmp_path)
    competing_journal, _ = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    competing = PinnedStockResearchNoteService(competing_journal)
    source = verify_pinned_stock_research_source(
        _bookmark_for(exact_price_store, "S0001")
    )
    original_append = journal.record_research_action

    def append_after_competing_write(*args, **kwargs):
        competing.save(
            source,
            "先完成的 Journal 修訂",
            revision_id="price-note-readback-cas-winner",
        )
        return original_append(*args, **kwargs)

    monkeypatch.setattr(
        journal,
        "record_research_action",
        append_after_competing_write,
    )

    with pytest.raises(PinnedStockResearchNoteConflict, match="journal append conflict"):
        service.save_with_readback(
            source,
            "不得沿過時 history token 寫入",
            revision_id="price-note-readback-cas-loser",
        )

    notes = competing.list_notes(stock_code=source.stock_code)
    assert tuple(note.revision_id for note in notes) == (
        "price-note-readback-cas-winner",
    )


@pytest.mark.parametrize("readback_kind", ("missing", "different_content"))
def test_journal_readback_missing_or_different_content_is_rejected(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    readback_kind: str,
) -> None:
    journal, _paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(
        _bookmark_for(exact_price_store, "S0001")
    )
    original_list_notes = service.list_notes
    revision_id = f"price-note-journal-{readback_kind}"

    def altered_readback(*, stock_code: str = ""):
        notes = original_list_notes(stock_code=stock_code)
        if readback_kind == "missing":
            return tuple(note for note in notes if note.revision_id != revision_id)
        return tuple(
            replace(note, text="不一致原文")
            if note.revision_id == revision_id
            else note
            for note in notes
        )

    monkeypatch.setattr(service, "list_notes", altered_readback)

    with pytest.raises(
        PinnedStockResearchNoteConflict,
        match="journal readback differs",
    ):
        service.save_with_readback(
            source,
            "保存後必須精確讀回",
            revision_id=revision_id,
        )

    actual = original_list_notes(stock_code=source.stock_code)
    assert any(note.revision_id == revision_id for note in actual)
    if readback_kind == "different_content":
        assert (
            next(note.text for note in actual if note.revision_id == revision_id)
            == "保存後必須精確讀回"
        )


def test_existing_save_keeps_note_return_type_and_does_not_use_new_readback(
    tmp_path: Path,
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, _paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = verify_pinned_stock_research_source(
        _bookmark_for(exact_price_store, "S0001")
    )

    def unexpected_readback(**_kwargs):
        raise AssertionError("legacy save must not invoke save_with_readback")

    monkeypatch.setattr(service, "list_notes", unexpected_readback)

    saved = service.save(
        source,
        "舊 save API 保持原回傳型別",
        revision_id="price-note-legacy-save",
    )

    assert type(saved) is PinnedStockResearchNote
    assert saved.text == "舊 save API 保持原回傳型別"
