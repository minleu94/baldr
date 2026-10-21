from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app_module.research_evidence_comparison_service as comparison_module
from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    create_daily_market_technical_universe_price_bookmark_v1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.pinned_stock_research_notes import PinnedStockResearchNote, PinnedStockResearchSource
from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.research_timeline_dtos import ResearchTimelineEntry
from app_module.stock_research_report_dtos import (
    StockPricePointDTO,
    StockResearchReportDTO,
    StockReportSectionDTO,
    StockReportSourceDTO,
)
from app_module.stock_research_report_notes import StockResearchReportNote
from app_module.stock_research_report_snapshot_codec import create_stock_research_report_projection_snapshot
from app_module.theme_daily_service import ThemeDailyReport
from app_module.theme_research_notes import ThemeResearchNote
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from app_module.theme_snapshot_catalog import (
    ThemeSnapshotCatalogEntry,
    ThemeSnapshotCatalogResult,
)
from tests.test_daily_market_technical_universe_price_query_v1 import _open_session, exact_price_store


class _Timeline:
    def __init__(self, baseline: object, state: object | None = None, error: Exception | None = None):
        self.baseline = baseline
        self.state = state
        self.error = error
        self.calls = 0

    def read_evidence_baseline(self, entry, cancel_callback=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.baseline, self.state


class _Reports:
    def __init__(self, report: object | None = None, error: Exception | None = None):
        self.report = report
        self.error = error
        self.calls: list[tuple[str, object, object]] = []

    def read_report(self, stock_code, *, context=None, cancel_callback=None):
        self.calls.append((stock_code, context, cancel_callback))
        if self.error is not None:
            raise self.error
        return self.report


def _report(code: str = "2330", *, as_of: str = "2026-10-20") -> StockResearchReportDTO:
    report, _context = _report_fixture()
    price = StockPricePointDTO(
        data_date="2026-10-19", close_price=Decimal("1200"), source_id="sqlite.daily_prices",
        source_snapshot_hash="a" * 64,
    )
    source = StockReportSourceDTO(
        source_id="sqlite.daily_prices", source_label="每日價格", data_as_of="2026-10-19",
        version="pin-1", status="available", historical_pit_eligible=False,
    )
    section = StockReportSectionDTO(
        section_id="price", label="價量", status="available", data_as_of="2026-10-19",
        summary="有保存行情列",
    )
    return replace(report, stock_code=code, as_of=as_of, price_points=(price,), sources=(source,),
                   sections=(section,), limitations=(),
                   portfolio_scenario=None if code != report.stock_code else report.portfolio_scenario,
                   fundamental_comparisons=() if code != report.stock_code else report.fundamental_comparisons)


def _report_fixture():
    from tests.test_stock_research_report_snapshot_codec import _report as make_report
    return make_report()


def _report_note(report: StockResearchReportDTO, *, context: ResearchStockContextDTO | None = None):
    if context is None:
        context = ResearchStockContextDTO(stock_code=report.stock_code, data_date="2026-09-23")
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    return StockResearchReportNote(
        revision_id="report-revision", snapshot=snapshot, text="原保存判斷",
        recorded_at="2026-10-19T12:00:00+00:00",
    )


def _entry(kind: str, note: object, stock_code: str = "2330") -> ResearchTimelineEntry:
    return ResearchTimelineEntry(
        kind=kind, record_id="record-1", recorded_at="2026-10-19T12:00:00+00:00",
        text=getattr(note, "text", ""), reference=note, stock_code=stock_code,
        data_date="2026-09-23", source_identity="saved-identity",
    )


def test_report_comparison_clears_saved_context_and_keeps_missing_distinct() -> None:
    original_report = _report(as_of="2026-09-23")
    original_context = ResearchStockContextDTO(
        stock_code="2330", decision_date="2026-09-23", data_date="2026-09-23",
        result_id="saved-result", source_snapshot_id="old-id", source_snapshot_hash="old-hash",
        source_id="old-source", source_version="old-version", source_kind="daily_market_research_snapshot",
        source_workspace="recommendation",
    )
    note = _report_note(original_report, context=original_context)
    entry = _entry("report", note)
    current_report = replace(_report(as_of="2026-10-20"), price_points=(), limitations=("最新行情未提供",))
    reports = _Reports(current_report)
    service = comparison_module.ResearchEvidenceComparisonService(
        _Timeline(note), reports, clock=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc),
    )

    result = service.read(entry)

    assert result.original.status == "available"
    assert result.current.status == "limited"
    assert dict(result.original.fields)["資料日"] == "2026-10-19"
    assert dict(result.current.fields)["資料日"] == "原件未提供"
    assert "收盤價" not in dict(result.current.fields) or dict(result.current.fields)["收盤價"] == "原件未提供"
    assert result.current.limitations == ("最新行情未提供",)
    code, context, _callback = reports.calls[0]
    assert code == "2330"
    assert type(context) is ResearchStockContextDTO
    assert context == ResearchStockContextDTO(
        stock_code="2330", source_kind="explicit_latest_stock_research", source_workspace="research_timeline",
    )
    assert result.compared_at == "2026-10-21T00:00:00+00:00"


def test_manual_note_discloses_that_market_data_was_not_archived() -> None:
    manual = JournalEntryDTO(
        journal_id="manual-1", portfolio_id="default", body="人工紀錄原文", stock_code="2330",
        source_type="manual_decision", created_at="2026-10-19T10:00:00+00:00",
        revision_id="manual-1", decision_identity=DecisionIdentity(
            stock_code="2330", decision_date="2026-10-19", source_snapshot_id="manual-source",
        ),
    )
    service = comparison_module.ResearchEvidenceComparisonService(
        _Timeline(manual), _Reports(_report()), clock=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc),
    )

    result = service.read(_entry("manual", manual))

    original = dict(result.original.fields)
    assert original["原文"] == "人工紀錄原文"
    assert original["行情資料"] == "原紀錄未封存行情；無法比較"
    assert result.current.status in {"available", "limited"}


def test_price_note_uses_freshly_verified_bookmark_facts(exact_price_store) -> None:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    bookmark = create_daily_market_technical_universe_price_bookmark_v1(
        query, page, "S0001", scroll_position=0,
    )
    state = read_daily_market_technical_universe_price_bookmark_v1(bookmark)
    note = PinnedStockResearchNote(
        revision_id="price-revision", source=PinnedStockResearchSource(bookmark.to_json()),
        text="固定價格判斷", recorded_at="2026-10-19T12:00:00+00:00",
    )
    service = comparison_module.ResearchEvidenceComparisonService(
        _Timeline(note, state), _Reports(_report("S0001")),
        clock=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc),
    )

    result = service.read(_entry("price", note, "S0001"))

    values = dict(result.original.fields)
    assert values["原股票"] == "S0001"
    assert values["原來源可用性"] == "unknown；依原收藏核驗狀態"
    assert values["歷史 PIT"] == "false；收藏不授予歷史資格"


def test_theme_note_has_no_fabricated_baseline_values_and_catalog_is_bounded(monkeypatch, tmp_path) -> None:
    note = ThemeResearchNote(
        revision_id="theme-revision", snapshot_identity_sha256="b" * 64,
        text="題材筆記", data_date="2026-10-16", recorded_at="2026-10-19T12:00:00+00:00",
    )
    daily = ThemeDailyReport(
        date(2026, 10, 20), datetime(2026, 10, 21, tzinfo=timezone.utc),
        "2026-10-01", "2026-10-02", "current_research", (), (), False,
    )
    snapshot = ThemeResearchSnapshot("c" * 64, daily, ())
    selected = ThemeSnapshotCatalogEntry(
        tmp_path / "manifest.json", "baldr.theme_research_snapshot.v1", date(2026, 10, 20),
        datetime(2026, 10, 20, tzinfo=timezone.utc), "c" * 64, snapshot,
    )
    catalog = ThemeSnapshotCatalogResult((selected,), (), 1, 1, 0, False, None)
    calls = []

    def resolve(root, *, known_at, schema, cancel_callback):
        calls.append((root, known_at, schema))
        return catalog

    monkeypatch.setattr(comparison_module, "resolve_latest_theme_research_snapshot", resolve)
    service = comparison_module.ResearchEvidenceComparisonService(
        _Timeline(note), _Reports(), clock=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc),
    )
    result = service.read(_entry("theme", note, ""), theme_catalog_root=tmp_path)

    assert dict(result.original.fields)["封存行情／成分值"] == "原筆記未封存；不以現況回填保存版本"
    assert result.current.status == "limited"
    assert dict(result.current.fields)["題材資料日"] == "2026-10-20"
    assert dict(result.current.fields)["來源格式"] == "baldr.theme_research_snapshot.v1"
    assert any("僅讀 price-v1" in item for item in result.current.limitations)
    assert dict(result.original.fields)["版本身份"] == "b" * 64
    assert dict(result.current.fields)["版本身份"] == "c" * 64
    assert calls == [(tmp_path, datetime(2026, 10, 21, tzinfo=timezone.utc), "price-v1")]
    assert len(result.current.fields) <= 48


@pytest.mark.parametrize(
    ("catalog", "expected_status"),
    (
        (ThemeSnapshotCatalogResult((), (), 0, 0, 0, False, None), "unavailable"),
        (ThemeSnapshotCatalogResult((), (), 128, 0, 128, True, "目錄預算到達"), "limited"),
    ),
)
def test_theme_missing_or_limited_catalog_is_not_reported_as_latest(
    monkeypatch, tmp_path, catalog, expected_status,
) -> None:
    note = ThemeResearchNote("theme-revision", "b" * 64, "題材筆記", "2026-10-16")
    monkeypatch.setattr(comparison_module, "resolve_latest_theme_research_snapshot", lambda *a, **k: catalog)
    service = comparison_module.ResearchEvidenceComparisonService(
        _Timeline(note), _Reports(), clock=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc),
    )
    result = service.read(_entry("theme", note, ""), theme_catalog_root=tmp_path)
    assert result.current.status == expected_status
    assert result.current.title != "最新題材資料"


def test_baseline_tamper_and_cancellation_prevent_current_read() -> None:
    note = _report_note(_report())
    reports = _Reports(_report())
    tampered = comparison_module.ResearchEvidenceComparisonService(
        _Timeline(note, error=ValueError("原件已變更")), reports,
    )
    with pytest.raises(ValueError, match="原件已變更"):
        tampered.read(_entry("report", note))
    assert reports.calls == []

    cancelled = comparison_module.ResearchEvidenceComparisonService(
        _Timeline(note), reports,
    )
    with pytest.raises(InterruptedError):
        cancelled.read(_entry("report", note), cancel_callback=lambda: True)
    assert reports.calls == []


def test_theme_without_configured_root_is_unavailable_without_catalog_scan() -> None:
    note = ThemeResearchNote("theme-revision", "b" * 64, "題材筆記", "2026-10-16")
    service = comparison_module.ResearchEvidenceComparisonService(_Timeline(note), _Reports())
    result = service.read(_entry("theme", note, ""))
    assert result.current.status == "unavailable"
    assert "未設定題材來源目錄。" in result.current.limitations
