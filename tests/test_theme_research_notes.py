from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.dtos.decision_continuity_dtos import IDENTITY_STATUS_UNKNOWN
from app_module.journal_service import JournalService
from app_module.personal_journal_paths import resolve_personal_journal_paths
from app_module.theme_daily_service import ThemeDailyReport
from app_module.theme_research_notes import (
    ThemeResearchNoteConflict,
    ThemeResearchNoteError,
    ThemeResearchNoteNotFound,
    ThemeResearchNoteService,
)
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow


def _journal_service(tmp_path: Path) -> tuple[JournalService, object]:
    data_root = tmp_path / "FA_Data"
    paths = resolve_personal_journal_paths(
        data_root,
        personal_root=data_root / "personal",
    )
    config = SimpleNamespace(output_root=paths.personal_paths.legacy_output_root)
    return JournalService(config, journal_paths=paths), paths


def _snapshot(
    identity: str = "a" * 64,
    data_date: date | None = date(2026, 10, 17),
    *,
    historical_pit_eligible: bool = False,
) -> ThemeResearchSnapshot:
    report = ThemeDailyReport(
        data_date=data_date,  # type: ignore[arg-type]
        known_at=datetime(2026, 10, 18, 1, tzinfo=timezone.utc),
        mapping_snapshot_date="2026-10-17",
        mapping_available_date="2026-10-17",
        status="current_research",
        rows=(),
        warnings=(),
        historical_pit_eligible=historical_pit_eligible,
    )
    mapping = ThemeMappingRow(
        snapshot_date="2026-10-17",
        available_date="2026-10-17",
        stock_id="2330",
        stock_name="台積電",
        market_type="TWSE",
        l1_industry_category="半導體",
        chain_name="半導體",
        chain_tier="fixture",
        theme_name="先進製程",
        is_primary=True,
        assignment_method="fixture",
        source_name="synthetic_test_fixture",
        source_tier="fixture",
        pit_mode="snapshot_aligned",
        evidence_note="合成測試來源",
    )
    return ThemeResearchSnapshot(identity, report, (mapping,))


def test_saved_note_reopens_with_exact_source_identity_and_original_date(tmp_path: Path) -> None:
    journal, paths = _journal_service(tmp_path)
    note_service = ThemeResearchNoteService(journal)
    snapshot = _snapshot()

    saved = note_service.save(snapshot, "供下次研究比對", revision_id="theme-note-1")
    reopened_journal = JournalService(
        SimpleNamespace(output_root=paths.personal_paths.legacy_output_root),
        journal_paths=paths,
    )
    reopened = ThemeResearchNoteService(reopened_journal)

    assert saved == reopened.get_note("theme-note-1")
    assert saved.snapshot_identity_sha256 == snapshot.identity_sha256
    assert saved.data_date == "2026-10-17"
    assert saved.text == "供下次研究比對"
    assert reopened.list_notes() == (saved,)

    revision = reopened_journal.list_decision_revisions()[0]
    assert revision.decision_identity.source_snapshot_id == snapshot.identity_sha256
    assert revision.decision_identity.source_snapshot_hash == snapshot.identity_sha256
    assert revision.decision_identity.decision_date == ""
    assert "theme_research_data_date:2026-10-17" in revision.payload["tags"]
    assert saved.recorded_at == revision.created_at == reopened.get_note("theme-note-1").recorded_at
    assert revision.decision_identity.stock_code == ""
    assert revision.decision_identity.result_id == ""
    assert revision.decision_identity.identity_status == IDENTITY_STATUS_UNKNOWN
    assert revision.payload["source_id"] == snapshot.identity_sha256
    assert revision.payload["source_snapshot_id"] == snapshot.identity_sha256
    assert revision.payload["source_snapshot_hash"] == snapshot.identity_sha256
    assert revision.payload["source_type"] == "theme_research_note.v1"
    assert revision.payload["stock_code"] == ""
    assert "personalization_action" not in revision.payload
    assert not list(tmp_path.rglob("trades.jsonl"))


def test_revision_appends_and_keeps_the_original_note_unchanged(tmp_path: Path) -> None:
    journal, _ = _journal_service(tmp_path)
    note_service = ThemeResearchNoteService(journal)
    snapshot = _snapshot()

    first = note_service.save(snapshot, "第一版觀察", revision_id="theme-note-1")
    second = note_service.save(
        snapshot,
        "補充資料日為原報告日期",
        revision_id="theme-note-2",
        revision_of=first.revision_id,
    )

    assert second.revision_of == first.revision_id
    assert note_service.get_note(first.revision_id) == first
    assert note_service.get_note(second.revision_id) == second
    assert note_service.list_notes() == (first, second)
    revisions = journal.list_decision_revisions()
    assert [item.revision_id for item in revisions] == [first.revision_id, second.revision_id]
    assert revisions[1].revision_of == first.revision_id


def test_same_snapshot_notes_keep_independent_revision_roots_and_reopen(
    tmp_path: Path,
) -> None:
    journal, paths = _journal_service(tmp_path)
    note_service = ThemeResearchNoteService(journal)
    snapshot = _snapshot()

    first = note_service.save(snapshot, "第一篇原始判斷", revision_id="theme-note-a1")
    first_revision = note_service.save(
        snapshot,
        "第一篇追加修訂",
        revision_id="theme-note-a2",
        revision_of=first.revision_id,
    )
    second = note_service.save(snapshot, "第二篇原始判斷", revision_id="theme-note-b1")
    second_revision = note_service.save(
        snapshot,
        "第二篇追加修訂",
        revision_id="theme-note-b2",
        revision_of=second.revision_id,
    )

    revisions_by_id = {
        item.revision_id: item for item in journal.list_decision_revisions()
    }
    first_root = revisions_by_id[first.revision_id].entity_id
    second_root = revisions_by_id[second.revision_id].entity_id
    assert first_root != second_root
    assert revisions_by_id[first_revision.revision_id].entity_id == first_root
    assert revisions_by_id[second_revision.revision_id].entity_id == second_root
    assert revisions_by_id[first_revision.revision_id].revision_of == first.revision_id
    assert revisions_by_id[second_revision.revision_id].revision_of == second.revision_id

    for note in (first, first_revision, second, second_revision):
        assert note.snapshot_identity_sha256 == snapshot.identity_sha256
        assert note.data_date == "2026-10-17"
    assert first.revision_of is None
    assert second.revision_of is None
    assert first_revision.revision_of == first.revision_id
    assert second_revision.revision_of == second.revision_id
    assert note_service.get_note(first.revision_id).text == "第一篇原始判斷"
    assert note_service.get_note(second.revision_id).text == "第二篇原始判斷"

    reopened_journal = JournalService(
        SimpleNamespace(output_root=paths.personal_paths.legacy_output_root),
        journal_paths=paths,
    )
    reopened = ThemeResearchNoteService(reopened_journal)
    reopened_by_id = {note.revision_id: note for note in reopened.list_notes()}
    assert reopened_by_id == {
        note.revision_id: note for note in (first, first_revision, second, second_revision)
    }
    assert reopened.get_note(first.revision_id).text == "第一篇原始判斷"
    assert reopened.get_note(first_revision.revision_id).text == "第一篇追加修訂"
    assert reopened.get_note(second.revision_id).text == "第二篇原始判斷"
    assert reopened.get_note(second_revision.revision_id).text == "第二篇追加修訂"


def test_stale_ancestor_revision_is_rejected_without_changing_saved_notes(
    tmp_path: Path,
) -> None:
    journal, paths = _journal_service(tmp_path)
    note_service = ThemeResearchNoteService(journal)
    snapshot = _snapshot()
    original = note_service.save(snapshot, "原始判斷", revision_id="theme-note-root")
    latest = note_service.save(
        snapshot,
        "沿目前版本追加",
        revision_id="theme-note-latest",
        revision_of=original.revision_id,
    )
    bytes_before = paths.journal_file.read_bytes()
    history_before = tuple(journal.list_journal_history())

    with pytest.raises(ValueError, match="journal_revision_chain_conflict"):
        note_service.save(
            snapshot,
            "從舊祖先分岔的修訂",
            revision_id="theme-note-stale-branch",
            revision_of=original.revision_id,
        )

    assert paths.journal_file.read_bytes() == bytes_before
    assert tuple(journal.list_journal_history()) == history_before
    assert note_service.get_note(original.revision_id).text == "原始判斷"
    assert note_service.get_note(latest.revision_id).text == "沿目前版本追加"
    with pytest.raises(ThemeResearchNoteNotFound):
        note_service.get_note("theme-note-stale-branch")


def test_revision_id_is_idempotent_only_for_identical_note_content(tmp_path: Path) -> None:
    journal, _ = _journal_service(tmp_path)
    note_service = ThemeResearchNoteService(journal)
    snapshot = _snapshot()

    first = note_service.save(snapshot, "固定內容", revision_id="theme-note-1")
    assert note_service.save(snapshot, "固定內容", revision_id="theme-note-1") == first
    before = tuple(journal.list_journal_history())

    with pytest.raises(ThemeResearchNoteConflict, match="different saved content"):
        note_service.save(snapshot, "不同內容", revision_id="theme-note-1")

    assert tuple(journal.list_journal_history()) == before
    assert note_service.list_notes() == (first,)


def test_revision_requires_an_existing_note_for_the_same_snapshot(tmp_path: Path) -> None:
    journal, _ = _journal_service(tmp_path)
    note_service = ThemeResearchNoteService(journal)
    original = note_service.save(_snapshot(), "原始觀察", revision_id="theme-note-1")
    before = tuple(journal.list_journal_history())

    with pytest.raises(ThemeResearchNoteConflict, match="another theme snapshot"):
        note_service.save(
            _snapshot("b" * 64),
            "跨來源修訂",
            revision_id="theme-note-2",
            revision_of=original.revision_id,
        )

    with pytest.raises(ThemeResearchNoteConflict, match="must identify one saved"):
        note_service.save(
            _snapshot(),
            "修訂不存在的筆記",
            revision_id="theme-note-3",
            revision_of="missing-revision",
        )
    assert tuple(journal.list_journal_history()) == before


def test_missing_note_stays_missing_without_rebuilding_a_snapshot(tmp_path: Path) -> None:
    journal, paths = _journal_service(tmp_path)
    note_service = ThemeResearchNoteService(journal)
    before = paths.journal_file.read_bytes() if paths.journal_file.exists() else None

    with pytest.raises(ThemeResearchNoteNotFound, match="not found"):
        note_service.get_note("missing-revision")
    assert note_service.list_notes() == ()
    after = paths.journal_file.read_bytes() if paths.journal_file.exists() else None
    assert after == before


def test_competing_journal_write_rejects_stale_theme_note_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    journal, _ = _journal_service(tmp_path)
    competing_journal, _ = _journal_service(tmp_path)
    service = ThemeResearchNoteService(journal)
    competing = ThemeResearchNoteService(competing_journal)
    original_append = journal.record_research_action

    def append_after_competing_write(*args, **kwargs):
        competing.save(_snapshot(), "另一個已成功保存的判斷", revision_id="competing-note")
        return original_append(*args, **kwargs)

    monkeypatch.setattr(journal, "record_research_action", append_after_competing_write)
    with pytest.raises(RuntimeError, match="journal_revision_stream_conflict"):
        service.save(_snapshot(), "過時快照不可覆寫", revision_id="stale-note")
    assert [note.revision_id for note in competing.list_notes()] == ["competing-note"]
    with pytest.raises(ThemeResearchNoteNotFound):
        competing.get_note("stale-note")


@pytest.mark.parametrize(
    ("snapshot", "text"),
    [
        (_snapshot(historical_pit_eligible=True), "不得標成歷史可得"),
        (_snapshot(data_date=None), "缺少資料日不得補造"),
        (_snapshot(identity="not-a-sha256"), "來源身份格式錯誤"),
        (_snapshot(), "  \t  "),
        (_snapshot(), "x" * 8001),
    ],
)
def test_save_rejects_ineligible_or_incomplete_source_and_invalid_text(
    tmp_path: Path,
    snapshot: ThemeResearchSnapshot,
    text: str,
) -> None:
    journal, _ = _journal_service(tmp_path)
    note_service = ThemeResearchNoteService(journal)

    with pytest.raises(ThemeResearchNoteError):
        note_service.save(snapshot, text, revision_id="theme-note-invalid")
    assert journal.list_decision_revisions() == []
