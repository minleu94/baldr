"""收藏來源不得由同股或最新來源替代，切股須重新解析 exact bookmark。"""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMainWindow

from app_module.research_session.session_dtos import ResearchStockContextDTO
from ui_qt.main import MainWindow
from ui_qt.views.stock_research_report_view import StockResearchReportView


class Harness(MainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.selected_workspace = ""

    def _select_main_workspace(self, key):
        self.selected_workspace = key


def context(code="2382", bookmark="bookmark-one"):
    return ResearchStockContextDTO(
        stock_code=code, source_id=bookmark, source_workspace="watchlist",
        source_kind="daily_market_research_snapshot", source_snapshot_hash="a" * 64,
        source_snapshot_id="b" * 64, decision_date="2026-10-05",
        daily_snapshot_cohort_id="same-cohort", daily_snapshot_condition_keys="close_above_ma20",
        daily_snapshot_combine_mode="AND",
    )


def test_exact_return_and_switch_group_do_not_use_generic_same_code():
    app = QApplication.instance() or QApplication([])
    window = Harness()
    received = []
    window.watchlist_view = SimpleNamespace(
        restore_research_bookmark_stock=lambda value: received.append(value) or False,
        research_bookmark_stock_codes=lambda value: ("2382", "1477"),
        select_stock=lambda *_args: pytest.fail("不應走同股 fallback"),
    )
    value = context()
    assert window._stock_codes_for_research_context(value) == ("2382", "1477")
    window._return_to_research_source(value)
    assert received == [value]
    assert window.selected_workspace == "watchlist"
    assert "不能用同股" in window.statusBar().currentMessage()
    window.close()
    app.processEvents()


def test_bookmark_switch_resolves_new_identity_before_reader(monkeypatch):
    app = QApplication.instance() or QApplication([])
    view = StockResearchReportView(SimpleNamespace())
    original = context()
    view.context = original
    view._load_stock("1477")
    assert view.context == original
    assert view._request_id == 0
    assert not view._workers
    target = context("1477", "bookmark-two")
    view.research_bookmark_context_resolver = lambda current, code: target
    seen = []
    monkeypatch.setattr(view, "_set_loading_state", lambda code: seen.append((code, view.context)))
    # 停在載入前，驗證 reader 使用的是另一張書籤，而非舊身份 replace code。
    monkeypatch.setattr(view, "_context_identity", lambda *_args: (_ for _ in ()).throw(RuntimeError("stop-before-reader")))
    with pytest.raises(RuntimeError, match="stop-before-reader"):
        view._load_stock("1477")
    assert view.context.source_id == "bookmark-two"
    assert view.context.stock_code == "1477"
    assert view.context.source_snapshot_hash == original.source_snapshot_hash
    view.close()
    app.processEvents()
