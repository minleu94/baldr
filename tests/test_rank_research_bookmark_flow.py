from __future__ import annotations

from dataclasses import replace
from datetime import datetime, date
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.stock_research_report_dtos import (
    StockOriginalRankingReportDTO,
    StockResearchReportDTO,
)
from app_module.stock_research_report_service import StockResearchReportReadService
from tests.test_rank_research_bookmark import _rank_bookmark
from ui_qt.main import MainWindow
from ui_qt.views.stock_research_report_view import StockResearchReportView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _rank_context() -> ResearchStockContextDTO:
    return _rank_bookmark().context


def _available_report(context: ResearchStockContextDTO) -> StockResearchReportDTO:
    rank = context.rank_context
    assert rank is not None
    original = StockOriginalRankingReportDTO(
        status="available",
        rank_kind=rank.rank_kind,
        period=rank.period,
        direction=rank.direction,
        direction_label="Top" if rank.direction == "strong" else "Bottom",
        native_score_label="Top 100%" if rank.direction == "strong" else "Bottom 33%",
        rank=rank.selected_rank,
        decision_date=rank.decision_date,
        comparison_date=rank.comparison_date,
        latest_date=rank.latest_date,
        comparison_window_dates=rank.comparison_window_dates,
        comparison_window_rule=rank.comparison_window_rule,
        eligible_stock_codes=rank.eligible_stock_codes,
        declared_stock_codes=rank.declared_stock_codes,
        research_universe_json=rank.research_universe_json,
        research_universe_sha256=rank.research_universe_sha256,
        method_name=rank.method_name,
        method_version=rank.method_version,
        method_contract_sha256=rank.method_contract_sha256,
        engine_file_sha256=rank.engine_file_sha256,
        engine_parameters_json=rank.engine_parameters_json,
        engine_parameters_sha256=rank.engine_parameters_sha256,
        source_schema_sha256=rank.source_schema_sha256,
        selected_input_fingerprint_sha256=rank.selected_input_fingerprint_sha256,
        rank_manifest_identity_sha256=rank.rank_snapshot_id,
        rank_manifest_sha256=rank.source_hash,
        parent_snapshot_identity_sha256=rank.parent_snapshot_id,
        parent_snapshot_sha256=rank.parent_snapshot_hash,
        parent_cohort_id=rank.parent_cohort_id,
    )
    return StockResearchReportDTO(
        stock_code=context.stock_code,
        stock_name=context.stock_name,
        as_of=rank.decision_date,
        original_ranking=original,
    )


def test_report_actions_keep_native_rank_label_and_offer_latest_separately() -> None:
    _app()
    context = _rank_context()
    view = StockResearchReportView(SimpleNamespace())
    view.context = context
    view._active_code = context.stock_code
    view._loaded_report = _available_report(context)
    view._sync_original_rank_actions()
    favorite_events: list[object] = []
    latest_events: list[object] = []
    view.rankBookmarkRequested.connect(favorite_events.append)
    view.latestResearchRequested.connect(latest_events.append)

    assert view.favorite_original_ranking_button.isEnabled()
    assert not view.favorite_original_ranking_button.isHidden()
    assert "Top 100%" in view.original_ranking_label.text()
    view.favorite_original_ranking_button.click()
    view.open_latest_rank_research_button.click()
    assert favorite_events == [context]
    assert latest_events == [context]

    week_context = replace(
        context,
        rank_context=replace(
            context.rank_context,
            period="day",
            rank_snapshot_id="f" * 64,
            source_hash="e" * 64,
        ),
    )
    assert view._context_identity(context, context.stock_code) != view._context_identity(
        week_context, context.stock_code
    )

    unknown = replace(
        _available_report(context).original_ranking,
        status="unknown",
        reason="ranking_manifest_hash_mismatch",
        rank=None,
        native_score_label="",
    )
    view._loaded_report = replace(_available_report(context), original_ranking=unknown)
    view._sync_original_rank_actions()
    assert not view.favorite_original_ranking_button.isEnabled()
    assert view.open_latest_rank_research_button.isEnabled()
    assert "ranking_manifest_hash_mismatch" in view.original_ranking_label.text()
    view.close()
    _app().processEvents()


class _MainHarness(MainWindow):
    """以 offscreen MainWindow 驗證 production signals，不建立使用者視窗。"""


def test_main_report_signals_confirm_cancel_duplicate_and_latest_are_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app()
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))
    Path(tmp_path / "data").mkdir(parents=True, exist_ok=True)
    Path(tmp_path / "output").mkdir(parents=True, exist_ok=True)
    window = _MainHarness()

    class WatchlistSpy:
        def __init__(self) -> None:
            self.added: list[object] = []
            self.statuses = ["added", "already_present"]

        def add_rank_research_bookmark(self, bookmark: object) -> object:
            self.added.append(bookmark)
            return SimpleNamespace(
                status=self.statuses.pop(0),
                source_id=getattr(bookmark, "bookmark_id", "rank-bookmark"),
                bookmark_id=getattr(bookmark, "bookmark_id", "rank-bookmark"),
            )

    watchlist = WatchlistSpy()
    window.watchlist_service = watchlist
    refreshes: list[bool] = []
    window.watchlist_view = SimpleNamespace(
        _load_watchlist=lambda: refreshes.append(True)
    )
    confirmations = [QMessageBox.StandardButton.No]
    monkeypatch.setattr(
        "ui_qt.main.QMessageBox.question",
        lambda *_args, **_kwargs: confirmations[0],
    )

    class BookmarkStub:
        bookmark_id = "rank-source-exact-id"

    bookmark_stub = BookmarkStub()

    factory_contexts: list[object] = []

    def make_bookmark(context, **_kwargs):
        factory_contexts.append(context)
        return bookmark_stub

    monkeypatch.setattr(
        "app_module.daily_market_research_bookmark.create_original_stock_ranking_bookmark_from_context",
        make_bookmark,
    )

    report_view = window.stock_research_workspace.report_view
    context = _rank_context()
    report_view.rankBookmarkRequested.emit(context)
    assert factory_contexts == [context]
    assert watchlist.added == []
    assert "已取消" in window.statusBar().currentMessage()

    confirmations[0] = QMessageBox.StandardButton.Yes
    report_view.rankBookmarkRequested.emit(context)
    report_view.rankBookmarkRequested.emit(context)
    assert len(watchlist.added) == 2
    assert watchlist.added == [bookmark_stub, bookmark_stub]
    assert len(refreshes) == 2
    assert "此原排名已收藏" in window.statusBar().currentMessage()

    latest_contexts: list[ResearchStockContextDTO] = []
    latest_workspaces: list[str] = []
    monkeypatch.setattr(
        window,
        "_open_stock_research_context",
        lambda value: latest_contexts.append(value),
    )
    monkeypatch.setattr(
        window,
        "_select_main_workspace",
        lambda value: latest_workspaces.append(value),
    )
    report_view.latestResearchRequested.emit(context)
    assert len(latest_contexts) == 1
    assert latest_contexts[0].source_kind == "explicit_latest_stock_research"
    assert latest_contexts[0].rank_context is None
    assert latest_contexts[0].stock_code == context.stock_code
    assert latest_workspaces == ["stock_research"]
    assert context.rank_context is not None
    assert context.source_kind == "original_stock_ranking_bookmark"
    window.close()
    app.processEvents()


def test_publisher_rank_navigation_rebuilds_from_pinned_cohort_or_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _app()
    context = replace(
        _rank_context(),
        source_kind="original_stock_ranking",
        source_workspace="recommendation",
        source_id="",
    )
    rank = context.rank_context
    assert rank is not None
    service = SimpleNamespace(config=SimpleNamespace(db_file=tmp_path / "readonly.sqlite"))
    snapshot = SimpleNamespace(stock_snapshots={})
    ranking = SimpleNamespace(rows=())

    from app_module import original_stock_ranking

    monkeypatch.setattr(
        original_stock_ranking,
        "load_original_stock_ranking_from_context",
        lambda _rank, *, db_path: (snapshot, ranking),
    )

    def build_context(_snapshot, _ranking, *, stock_code, inherited_context, **_kwargs):
        selected = stock_code if stock_code in rank.eligible_stock_codes else context.stock_code
        selected_rank = 2 if selected != context.stock_code else rank.selected_rank
        return replace(
            inherited_context,
            stock_code=stock_code,
            rank_context=replace(
                rank,
                selected_stock_code=selected,
                selected_rank=selected_rank,
            ),
        )

    monkeypatch.setattr(
        original_stock_ranking,
        "research_context_for_original_stock_ranking",
        build_context,
    )

    valid_view = StockResearchReportView(service)
    valid_view.context = context
    valid_view.set_stock_codes(rank.eligible_stock_codes)
    monkeypatch.setattr(
        valid_view,
        "_context_identity",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("resolved-before-reader")),
    )
    with pytest.raises(RuntimeError, match="resolved-before-reader"):
        valid_view._load_stock("2317")
    assert valid_view.context is not None
    assert valid_view.context.stock_code == "2317"
    assert valid_view.context.rank_context is not None
    assert valid_view.context.rank_context.selected_stock_code == "2317"
    assert valid_view.context.rank_context.selected_rank == 2
    assert valid_view.context.rank_context.source_hash == rank.source_hash
    valid_view.close()

    refused_view = StockResearchReportView(service)
    refused_view.context = context
    refused_view.set_stock_codes((*rank.eligible_stock_codes, "9999"))
    refused_view._load_stock("9999")
    assert refused_view.context is context
    assert refused_view._request_id == 0
    assert "pinned" in refused_view.status_label.text().lower()
    refused_view.close()
    _app().processEvents()


def test_rank_report_reads_pinned_row_and_parent_feature_then_refuses_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _rank_context()
    rank = context.rank_context
    assert rank is not None
    database = tmp_path / "readonly-fixture.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 證券名稱 TEXT, "
            "開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER, "
            "成交金額 TEXT, 漲跌價差 TEXT)"
        )
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rank.decision_date, context.stock_code, context.stock_name, "99", "102", "98", "100", 1000, "100000", "1"),
        )

    service = StockResearchReportReadService(
        SimpleNamespace(db_file=database, output_root=tmp_path / "output"),
        clock=lambda: datetime(2026, 10, 5, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )
    from app_module import original_stock_ranking

    pinned_snapshot = SimpleNamespace(
        manifest_sha256=rank.parent_snapshot_hash,
        manifest_identity_sha256=rank.parent_snapshot_id,
        cohort_id=rank.parent_cohort_id,
        decision_date=date.fromisoformat(rank.decision_date),
        stock_snapshots={
            context.stock_code: {
                "input_fingerprint_sha256": rank.selected_input_fingerprint_sha256,
                "close": "100",
                "policy": {"usage": "current_observed_research_only"},
            }
        },
    )
    calls: list[tuple[str, object]] = []

    def pinned_row(requested, *, db_path):
        calls.append(("row", requested))
        assert requested is rank
        return {
            "stock_code": context.stock_code,
            "rank": rank.selected_rank,
            "score_label": "Top 100%",
            "comparison_date": rank.comparison_date,
            "latest_date": rank.latest_date,
            "native_reasons": ("publisher reason",),
        }

    def pinned_bundle(requested, *, db_path):
        calls.append(("feature", requested))
        assert requested is rank
        assert Path(db_path) == database
        return pinned_snapshot, SimpleNamespace()

    monkeypatch.setattr(
        original_stock_ranking,
        "read_original_stock_ranking_row_from_context",
        pinned_row,
    )
    monkeypatch.setattr(
        original_stock_ranking,
        "load_original_stock_ranking_from_context",
        pinned_bundle,
    )

    report = service.read_report(context.stock_code, context=context)
    assert report.original_ranking is not None
    assert report.original_ranking.status == "available"
    assert report.original_ranking.native_score_label == "Top 100%"
    assert report.original_ranking.rank == rank.selected_rank
    assert report.shared_daily_features["readback"]["mode"] == (
        "verified_pinned_original_rank_parent_feature"
    )
    assert report.shared_daily_features["readback"]["parent_manifest_sha256"] == (
        rank.parent_snapshot_hash
    )
    assert [kind for kind, _ in calls] == ["row", "feature"]

    calls.clear()
    refused_report = service.read_report(
        context.stock_code,
        context=context,
        as_of_date="2026-10-05",
    )
    assert refused_report.original_ranking is not None
    assert refused_report.original_ranking.status == "unknown"
    assert "不一致" in refused_report.original_ranking.reason
    assert not calls

    wrong_stock_report = service.read_report("2317", context=context)
    assert wrong_stock_report.original_ranking is not None
    assert wrong_stock_report.original_ranking.status == "unknown"
    assert "股票" in wrong_stock_report.original_ranking.reason

    def refused_row(_requested, *, db_path):
        raise RuntimeError("ranking_manifest_hash_mismatch")

    monkeypatch.setattr(
        original_stock_ranking,
        "read_original_stock_ranking_row_from_context",
        refused_row,
    )
    refused_source_report = service.read_report(context.stock_code, context=context)
    assert refused_source_report.original_ranking is not None
    assert refused_source_report.original_ranking.status == "unknown"
    assert "ranking_manifest_hash_mismatch" in refused_source_report.original_ranking.reason
    assert refused_source_report.shared_daily_features["projection_status"] == "unknown"
