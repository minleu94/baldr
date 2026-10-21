from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.pinned_stock_research_notes import PinnedStockResearchNote
from app_module.research_timeline_service import ResearchTimelineService
from app_module.stock_research_report_notes import StockResearchReportNote
from app_module.stock_research_report_snapshot_codec import create_stock_research_report_projection_snapshot
from app_module.theme_research_notes import ThemeResearchNote
from tests.test_stock_research_report_snapshot_codec import _report


@dataclass
class _Journal:
    records: tuple[JournalEntryDTO, ...]

    def list_journal_entries(self):
        return list(self.records)


class _Notes:
    def __init__(
        self,
        notes=(),
        error: Exception | None = None,
        *,
        fresh_notes=None,
        source_state=None,
    ):
        self.notes = tuple(notes)
        self.error = error
        self.fresh_notes = dict(fresh_notes or {})
        self.source_state = source_state
        self.get_calls = []
        self.verify_calls = []

    def list_notes(self):
        if self.error is not None:
            raise self.error
        return self.notes

    def get_note(self, revision_id):
        self.get_calls.append(revision_id)
        if revision_id in self.fresh_notes:
            return self.fresh_notes[revision_id]
        return next(note for note in self.notes if note.revision_id == revision_id)

    def verify_source(self, note, *, cancel_callback=None):
        self.verify_calls.append(note.revision_id)
        return self.source_state


def _service(*, manual=(), price=(), reports=(), themes=(), price_error=None):
    return ResearchTimelineService(
        _Journal(tuple(manual)),
        price_note_service=_Notes(price, price_error),
        report_note_service=_Notes(reports),
        theme_note_service=_Notes(themes),
    )


def _report_note(*, recorded_at="2026-10-19T14:00:00+00:00", text="報告判斷原文"):
    report_data, report_context = _report()
    report_context = replace(
        report_context,
        result_id="result-report",
        data_date="2026-10-17",
    )
    report_snapshot = create_stock_research_report_projection_snapshot(
        report_data, report_context
    )
    return StockResearchReportNote(
        revision_id="report-1",
        snapshot=report_snapshot,
        text=text,
        revision_of="report-root",
        recorded_at=recorded_at,
    )


def _theme_note(*, recorded_at="2026-10-19T15:00:00+00:00", text="題材原文"):
    return ThemeResearchNote(
        revision_id="theme-1",
        snapshot_identity_sha256="theme-source",
        text=text,
        data_date="2026-10-16",
        revision_of="theme-root",
        recorded_at=recorded_at,
    )


def _price_note(*, recorded_at="2026-10-19T13:00:00+00:00", text="價格筆記原文"):
    return PinnedStockResearchNote(
        revision_id="price-1",
        source=SimpleNamespace(
            bookmark_json='{"canonical":"bookmark"}',
            stock_code="2330",
            data_date="2026-10-18",
            identity_sha256="price-source",
        ),
        text=text,
        revision_of="price-root",
        recorded_at=recorded_at,
    )


def _price_state(*, bookmark_json='{"canonical":"bookmark"}', identity="price-source", stock_code="2330"):
    return SimpleNamespace(
        bookmark=SimpleNamespace(
            to_json=lambda: bookmark_json,
            bookmark_identity_sha256=identity,
            stock_code=stock_code,
        )
    )


def _manual(record_id: str, *, recorded_at: str, result_id: str = "") -> JournalEntryDTO:
    return JournalEntryDTO(
        journal_id=record_id,
        portfolio_id="default",
        body=f"原文 {record_id}",
        stock_code="2330",
        source_type="manual_decision",
        created_at=recorded_at,
        revision_id=record_id,
        decision_identity=DecisionIdentity(
            result_id=result_id,
            stock_code="2330",
            decision_date="2026-10-19",
            source_snapshot_id="manual-source",
        ),
    )


def test_typed_lanes_keep_original_identity_and_do_not_duplicate_manual_mirrors():
    manual = _manual("manual-1", recorded_at="2026-10-19T12:00:00+00:00", result_id="result-manual")
    manual.revision_of = "manual-root"
    mirrored = JournalEntryDTO(
        journal_id="price-1",
        portfolio_id="default",
        body="價格筆記原文",
        stock_code="2330",
        source_type="technical_price_research_note.v1",
        created_at="2026-10-19T13:00:00+00:00",
        revision_id="price-1",
    )
    price_note = PinnedStockResearchNote(
        revision_id="price-1",
        source=SimpleNamespace(
            stock_code="2330", data_date="2026-10-18", identity_sha256="price-source"
        ),
        text="價格筆記原文",
        revision_of="price-root",
        recorded_at="2026-10-19T13:00:00+00:00",
    )
    report_data, report_context = _report()
    report_context = replace(
        report_context,
        result_id="result-report",
        data_date="2026-10-17",
    )
    report_snapshot = create_stock_research_report_projection_snapshot(
        report_data, report_context
    )
    report_note = StockResearchReportNote(
        revision_id="report-1",
        snapshot=report_snapshot,
        text="報告判斷原文",
        revision_of="report-root",
        recorded_at="2026-10-19T14:00:00+00:00",
    )
    theme_note = ThemeResearchNote(
        revision_id="theme-1",
        snapshot_identity_sha256="theme-source",
        text="題材原文",
        data_date="2026-10-16",
        revision_of="",
        recorded_at="2026-10-19T15:00:00+00:00",
    )

    result = _service(
        manual=(manual, mirrored),
        price=(price_note,),
        reports=(report_note,),
        themes=(theme_note,),
    ).read()

    by_kind = {entry.kind: entry for entry in result.entries}
    assert set(by_kind) == {"manual", "price", "report", "theme"}
    assert len(result.entries) == 4
    assert by_kind["manual"].reference is manual
    assert by_kind["manual"].recorded_at == manual.created_at
    assert by_kind["manual"].revision_of == "manual-root"
    assert by_kind["manual"].result_id == "result-manual"
    assert by_kind["price"].text == "價格筆記原文"
    assert by_kind["price"].revision_of == "price-root"
    assert by_kind["price"].result_id == ""
    assert by_kind["report"].result_id == "result-report"
    assert by_kind["report"].source_identity == report_snapshot.identity_sha256
    assert by_kind["theme"].result_id == ""
    assert by_kind["theme"].data_date == "2026-10-16"
    assert result.warnings == ()


def test_unparseable_or_naive_times_sort_last_without_rewriting_source_strings():
    latest = _manual("latest", recorded_at="2026-10-20T08:00:00+00:00")
    naive = _manual("naive", recorded_at="2026-10-21T08:00:00")
    invalid = _manual("invalid", recorded_at="not-a-date")

    result = _service(manual=(invalid, latest, naive)).read()

    assert [item.record_id for item in result.entries] == ["latest", "invalid", "naive"]
    assert {item.record_id: item.recorded_at for item in result.entries}["invalid"] == "not-a-date"
    assert {item.record_id: item.recorded_at for item in result.entries}["naive"] == "2026-10-21T08:00:00"


def test_lane_error_keeps_other_lanes_and_reports_partial_result():
    manual = _manual("manual-1", recorded_at="2026-10-19T12:00:00+00:00")
    theme = ThemeResearchNote(
        revision_id="theme-1",
        snapshot_identity_sha256="theme-source",
        text="題材原文",
        data_date="2026-10-16",
        recorded_at="2026-10-19T13:00:00+00:00",
    )

    result = _service(manual=(manual,), price_error=OSError("reader unavailable"), themes=(theme,)).read()

    assert {item.kind for item in result.entries} == {"manual", "theme"}
    assert result.warnings and "price lane" in result.warnings[0]


def test_cancellation_stops_between_records_and_later_lanes():
    manual = (
        _manual("first", recorded_at="2026-10-19T12:00:00+00:00"),
        _manual("second", recorded_at="2026-10-19T11:00:00+00:00"),
    )
    theme = ThemeResearchNote(
        revision_id="theme-1",
        snapshot_identity_sha256="theme-source",
        text="題材原文",
        data_date="2026-10-16",
        recorded_at="2026-10-19T13:00:00+00:00",
    )
    calls = 0

    def cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 3

    result = _service(manual=manual, themes=(theme,)).read(cancel)

    assert [item.record_id for item in result.entries] == ["first"]
    assert any("取消" in warning for warning in result.warnings)


def test_read_is_bounded_to_500_entries_and_marks_truncation():
    records = tuple(
        _manual(f"manual-{index}", recorded_at=f"2026-10-19T12:00:{index % 60:02d}+00:00")
        for index in range(501)
    )

    result = _service(manual=records).read()

    assert len(result.entries) == 500
    assert result.limited is True


def test_read_original_fresh_reads_report_and_theme_with_exact_projection():
    report = _report_note()
    theme = _theme_note()
    report_reader = _Notes((report,))
    theme_reader = _Notes((theme,))
    service = ResearchTimelineService(
        _Journal(()),
        price_note_service=_Notes(),
        report_note_service=report_reader,
        theme_note_service=theme_reader,
    )
    entries = {entry.kind: entry for entry in service.read().entries}

    assert service.read_original(entries["report"]) == (report, None)
    assert service.read_original(entries["theme"]) == (theme, None)
    assert report_reader.get_calls == ["report-1"]
    assert theme_reader.get_calls == ["theme-1"]


def test_read_original_rejects_manual_entries_without_reading_a_typed_lane():
    manual = _manual("manual-1", recorded_at="2026-10-19T12:00:00+00:00")
    price_reader = _Notes()
    service = ResearchTimelineService(
        _Journal((manual,)),
        price_note_service=price_reader,
        report_note_service=_Notes(),
        theme_note_service=_Notes(),
    )
    entry = next(item for item in service.read().entries if item.kind == "manual")

    with pytest.raises(ValueError, match="只有價格"):
        service.read_original(entry)
    assert price_reader.get_calls == []


def test_read_original_price_returns_fresh_source_state_after_exact_bookmark_check():
    note = _price_note()
    state = _price_state()
    price_reader = _Notes((note,), source_state=state)
    service = ResearchTimelineService(
        _Journal(()),
        price_note_service=price_reader,
        report_note_service=_Notes(),
        theme_note_service=_Notes(),
    )
    entry = next(item for item in service.read().entries if item.kind == "price")

    assert service.read_original(entry) == (note, state)
    assert price_reader.get_calls == ["price-1"]
    assert price_reader.verify_calls == ["price-1"]


@pytest.mark.parametrize(
    "entry_change",
    (
        lambda entry: replace(entry, text="被竄改的顯示原文"),
        lambda entry: replace(entry, source_identity="another-source"),
        lambda entry: replace(
            entry,
            reference=replace(entry.reference, revision_id="forged-revision"),
        ),
    ),
    ids=("text", "identity", "forged-reference"),
)
def test_read_original_rejects_tampered_or_forged_entry(entry_change):
    theme = _theme_note()
    reader = _Notes((theme,))
    service = ResearchTimelineService(
        _Journal(()),
        price_note_service=_Notes(),
        report_note_service=_Notes(),
        theme_note_service=reader,
    )
    entry = next(item for item in service.read().entries if item.kind == "theme")

    with pytest.raises(ValueError):
        service.read_original(entry_change(entry))


def test_read_original_compares_recorded_at_even_when_dataclass_excludes_it():
    listed = _theme_note(recorded_at="2026-10-19T15:00:00+00:00")
    fresh = replace(listed, recorded_at="2026-10-19T16:00:00+00:00")
    reader = _Notes((listed,), fresh_notes={listed.revision_id: fresh})
    service = ResearchTimelineService(
        _Journal(()),
        price_note_service=_Notes(),
        report_note_service=_Notes(),
        theme_note_service=reader,
    )
    entry = next(item for item in service.read().entries if item.kind == "theme")

    with pytest.raises(ValueError, match="原件欄位"):
        service.read_original(entry)


@pytest.mark.parametrize("mismatch", ("canonical", "identity", "stock"))
def test_read_original_rejects_price_state_not_matching_saved_bookmark(mismatch):
    note = _price_note()
    state = _price_state(
        bookmark_json='{"canonical":"other"}' if mismatch == "canonical" else '{"canonical":"bookmark"}',
        identity="other-source" if mismatch == "identity" else "price-source",
        stock_code="2317" if mismatch == "stock" else "2330",
    )
    reader = _Notes((note,), source_state=state)
    service = ResearchTimelineService(
        _Journal(()),
        price_note_service=reader,
        report_note_service=_Notes(),
        theme_note_service=_Notes(),
    )
    entry = next(item for item in service.read().entries if item.kind == "price")

    with pytest.raises(ValueError, match="bookmark"):
        service.read_original(entry)


def test_read_original_cancellation_before_and_after_reader_stops_without_fallback():
    theme = _theme_note()
    reader = _Notes((theme,))
    service = ResearchTimelineService(
        _Journal(()),
        price_note_service=_Notes(),
        report_note_service=_Notes(),
        theme_note_service=reader,
    )
    entry = next(item for item in service.read().entries if item.kind == "theme")

    with pytest.raises(InterruptedError):
        service.read_original(entry, lambda: True)
    assert reader.get_calls == []

    checks = 0

    def cancel_after_getter():
        nonlocal checks
        checks += 1
        return checks >= 3

    with pytest.raises(InterruptedError):
        service.read_original(entry, cancel_after_getter)
    assert reader.get_calls == ["theme-1"]


def test_read_original_cancellation_after_price_verification_is_not_swallowed():
    note = _price_note()
    reader = _Notes((note,), source_state=_price_state())
    service = ResearchTimelineService(
        _Journal(()),
        price_note_service=reader,
        report_note_service=_Notes(),
        theme_note_service=_Notes(),
    )
    entry = next(item for item in service.read().entries if item.kind == "price")
    checks = 0

    def cancel_after_verify():
        nonlocal checks
        checks += 1
        return checks >= 5

    with pytest.raises(InterruptedError):
        service.read_original(entry, cancel_after_verify)
    assert reader.get_calls == ["price-1"]
    assert reader.verify_calls == ["price-1"]


def test_evidence_baseline_rechecks_manual_body_identity_and_uniqueness():
    note = _manual("manual-baseline", recorded_at="2026-10-19T12:00:00+00:00")
    journal = _Journal((note,))
    service = ResearchTimelineService(
        journal, price_note_service=_Notes(), report_note_service=_Notes(),
        theme_note_service=_Notes(),
    )
    entry = service.read().entries[0]
    assert service.read_evidence_baseline(entry) == (note, None)
    journal.records = (replace(note, body="已變動"),)
    with pytest.raises(ValueError, match="已變更"):
        service.read_evidence_baseline(entry)
    journal.records = (note, note)
    with pytest.raises(ValueError, match="重複"):
        service.read_evidence_baseline(entry)
    journal.records = ()
    with pytest.raises(ValueError, match="不存在"):
        service.read_evidence_baseline(entry)


def test_evidence_baseline_manual_cancellation_and_report_original_verification():
    note = _manual("manual-baseline", recorded_at="2026-10-19T12:00:00+00:00")
    service = _service(manual=(note,))
    entry = service.read().entries[0]
    with pytest.raises(InterruptedError):
        service.read_evidence_baseline(entry, lambda: True)
    report = _report_note()
    reader = _Notes((report,))
    service = ResearchTimelineService(
        _Journal(()), price_note_service=_Notes(), report_note_service=reader,
        theme_note_service=_Notes(),
    )
    entry = service.read().entries[0]
    assert service.read_evidence_baseline(entry) == (report, None)
    reader.fresh_notes[report.revision_id] = replace(report, text="原件已變")
    with pytest.raises(ValueError, match="原件欄位已變更"):
        service.read_evidence_baseline(entry)
