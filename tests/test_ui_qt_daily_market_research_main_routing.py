"""日常研究快照在既有Main路由與session中不得丟失身分。"""
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMainWindow

from app_module.research_session import ResearchSessionStore, ResearchStockContextDTO
from ui_qt.main import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


class RouteHarness(MainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.research_session_store = ResearchSessionStore()
        self.selected_workspace = ""

    def _select_main_workspace(self, workspace):
        self.selected_workspace = workspace


def _context():
    return ResearchStockContextDTO(
        stock_code="2382", decision_date="2026-10-05", data_date="2026-10-02",
        source_kind="daily_market_research_snapshot", source_workspace="recommendation",
        source_snapshot_id="a" * 64, source_snapshot_hash="b" * 64,
        daily_snapshot_root="C:/isolated/research", daily_snapshot_cohort_id="two-stocks",
        daily_snapshot_condition_keys="close_above_ma20,close_above_ma60",
        daily_snapshot_combine_mode="OR",
    )


def test_mapping_context_keeps_pinned_research_fields():
    _app()
    window = RouteHarness()
    context = _context()
    payload = {name: getattr(context, name) for name in context.__dataclass_fields__}
    assert window._coerce_stock_research_context(payload) == context
    window.deleteLater()


def test_main_drilldown_preserves_real_session_and_source_stock_list():
    _app()
    window = RouteHarness()
    calls = []
    window.recommendation_view = SimpleNamespace(research_snapshot_stock_codes=lambda: ("2382", "1477"))
    window.stock_research_report_service = object()
    window.stock_research_workspace = SimpleNamespace(set_context=lambda context, **kwargs: calls.append((context, kwargs)))
    context = _context()
    window._open_stock_research_context(context)
    assert window.selected_workspace == "stock_research"
    assert calls == [(context, {"stock_codes": ("2382", "1477")})]
    assert window.research_session_store.get_snapshot().stock_context == context
    window.deleteLater()


@pytest.mark.parametrize("same_manifest", [True, False])
def test_main_return_requires_original_manifest_without_using_saved_recommendation(same_manifest):
    _app()
    window = RouteHarness()
    calls = []

    def restore(code, *, manifest_sha256=None):
        calls.append((code, manifest_sha256))
        return same_manifest

    def wrong_saved_selector(*_args):
        raise AssertionError("研究快照不能返回另一份保存推薦")

    window.recommendation_view = SimpleNamespace(restore_research_snapshot_stock=restore, select_stock=wrong_saved_selector)
    window._return_to_research_source(_context())
    assert window.selected_workspace == "recommendation"
    assert calls == [("2382", "b" * 64)]
    if not same_manifest:
        assert "原每日研究快照已變動" in window.statusBar().currentMessage()
    window.deleteLater()
