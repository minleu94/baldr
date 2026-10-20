"""價格筆記刪除沿追加式歷史，保留其他筆記與原價格來源。"""
from dataclasses import replace

import pytest

from app_module.dtos.decision_continuity_dtos import ACTION_REMOVED
from app_module.pinned_stock_research_notes import (
    PinnedStockResearchNoteConflict, PinnedStockResearchNoteNotFound,
    PinnedStockResearchNoteService, PinnedStockResearchSource,
)
from tests.test_pinned_stock_research_notes import _bookmark_for, _journal_service, _reopen_journal, exact_price_store


def test_delete_family_keeps_history_other_note_and_survives_reopen(tmp_path, exact_price_store):
    journal, paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = PinnedStockResearchSource(_bookmark_for(exact_price_store, "S0001").to_json())
    original = service.save(source, "第一版", revision_id="root-one")
    service.save(source, "修訂版", revision_id="child-one", revision_of="root-one")
    other = service.save(source, "另一篇保留", revision_id="root-other")
    before = journal.list_journal_history()
    removed = service.delete_note_family(original, removal_revision_id="delete-one")
    assert removed == ("root-one", "child-one")
    after = journal.list_journal_history()
    assert after[:-1] == before and len(after) == len(before) + 1
    assert journal.list_decision_revisions()[-1].action == ACTION_REMOVED
    assert service.list_notes() == (other,)
    reopened = PinnedStockResearchNoteService(_reopen_journal(paths))
    assert reopened.list_notes() == (other,)
    with pytest.raises(PinnedStockResearchNoteNotFound):
        reopened.get_note("root-one")
    with pytest.raises(PinnedStockResearchNoteNotFound):
        reopened.save(source, "第一版", revision_id="root-one")
    with pytest.raises(PinnedStockResearchNoteConflict):
        reopened.save(source, "不能接回舊鏈", revision_id="resurrection", revision_of="child-one")
    assert reopened.delete_note_family(original, removal_revision_id="delete-one") == removed
    assert journal.list_journal_history() == after


def test_delete_rejects_wrong_content_event_collision_and_concurrent_head(tmp_path, exact_price_store, monkeypatch):
    journal, _paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = PinnedStockResearchSource(_bookmark_for(exact_price_store, "S0001").to_json())
    original = service.save(source, "原文", revision_id="root-one")
    before = journal.list_journal_history()
    with pytest.raises(PinnedStockResearchNoteConflict):
        service.delete_note_family(replace(original, text="偽造文字"), removal_revision_id="delete-one")
    with pytest.raises(PinnedStockResearchNoteConflict):
        service.delete_note_family(original, removal_revision_id="root-one")
    assert journal.list_journal_history() == before
    delete = journal.delete_journal_entry
    def raced(*args, **kwargs):
        service.save(source, "另一視窗的新修訂", revision_id="concurrent-child", revision_of="root-one")
        return delete(*args, **kwargs)
    monkeypatch.setattr(journal, "delete_journal_entry", raced)
    with pytest.raises(PinnedStockResearchNoteConflict, match="Journal已改變"):
        service.delete_note_family(original, removal_revision_id="delete-one")
    assert {note.revision_id for note in service.list_notes()} == {"root-one", "concurrent-child"}
    assert all(item.action != ACTION_REMOVED for item in journal.list_decision_revisions())


@pytest.mark.parametrize("mutation", ["foreign_entity", "missing_source", "wrong_body"])
def test_tombstone_corruption_never_reports_success_or_resurrects_family(tmp_path, exact_price_store, monkeypatch, mutation):
    journal, _paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = PinnedStockResearchSource(_bookmark_for(exact_price_store, "S0001").to_json())
    original = service.save(source, "原文", revision_id="root-one")
    service.delete_note_family(original, removal_revision_id="delete-one")
    revisions = journal.list_decision_revisions()
    removal = revisions[-1]
    if mutation == "foreign_entity":
        bad = replace(removal, entity_type="decision")
    else:
        payload = dict(removal.payload)
        if mutation == "missing_source":
            payload.pop("source_type")
        else:
            payload["body"] = "遭修改的原文"
        bad = replace(removal, payload=payload)
    monkeypatch.setattr(journal, "list_decision_revisions", lambda: revisions[:-1] + [bad])
    with pytest.raises(PinnedStockResearchNoteConflict):
        service.list_notes()
    with pytest.raises(PinnedStockResearchNoteConflict):
        service.delete_note_family(original, removal_revision_id="delete-one")


def test_journal_retry_keeps_exact_expected_head(tmp_path, exact_price_store):
    journal, _paths = _journal_service(tmp_path)
    service = PinnedStockResearchNoteService(journal)
    source = PinnedStockResearchSource(_bookmark_for(exact_price_store, "S0001").to_json())
    original = service.save(source, "原文", revision_id="root-one")
    service.delete_note_family(original, removal_revision_id="delete-one")
    removal = journal.list_decision_revisions()[-1]
    before = journal.list_journal_history()
    with pytest.raises(RuntimeError, match="conflict"):
        journal.delete_journal_entry(removal.entity_id, revision_id="delete-one", expected_current_revision_id="different-head")
    assert journal.delete_journal_entry(removal.entity_id, revision_id="delete-one", expected_current_revision_id="root-one")
    assert journal.list_journal_history() == before
