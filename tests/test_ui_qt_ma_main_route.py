"""主視窗 MA 入口與合作式關閉的最小接線驗證。"""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

from ui_qt.main import MainWindow


class _MountHarness(QMainWindow):
    _mount_technical_official_research = MainWindow._mount_technical_official_research
    _freeze_child_refresh_sources = MainWindow._freeze_child_refresh_sources

    def __init__(self):
        super().__init__()
        self.config = SimpleNamespace(technical_official_disposition_read_root=None)
        self.messages = []

    def _save_technical_official_bookmark(self, value):
        self.messages.append(value)

    def _show_technical_official_comparison(self, value):
        self.messages.append(value)

    def _record_shutdown_message(self, value):
        self.messages.append(value)


def test_ma_and_revenue_mount_have_independent_tabs_and_shutdown_without_source_reads():
    app = QApplication.instance() or QApplication([])
    window = _MountHarness()
    recommendation = QWidget(window)
    recommendation.result_source_tabs = QTabWidget(recommendation)
    window._mount_technical_official_research(recommendation)
    ma_view = window.technical_official_ma_research_view
    revenue_view = window.technical_official_revenue_research_view
    try:
        tabs = recommendation.result_source_tabs
        assert tabs.count() == 3
        assert tabs.tabText(tabs.indexOf(ma_view)) == "四均線／官方對照研究"
        assert tabs.tabText(tabs.indexOf(revenue_view)) == "均線／月營收／官方對照研究"
        assert tabs.indexOf(ma_view) != tabs.indexOf(revenue_view)
        assert revenue_view.current_result is None
        assert revenue_view.active_worker is None
        assert revenue_view.bundle_output_root is None
        assert revenue_view.monthly_reference_path is None
        assert revenue_view.operation_root_parent is None
        assert ma_view.current_result is None
        assert ma_view.active_worker is None
        assert ma_view.bundle_output_root is None
        window._freeze_child_refresh_sources()
        assert ma_view._closing
        assert revenue_view._closing
        assert ma_view.active_worker is None
        assert revenue_view.active_worker is None
        assert window.messages == []
    finally:
        ma_view.begin_shutdown()
        revenue_view.begin_shutdown()
        window.technical_official_research_view.begin_shutdown()
        recommendation.close()
        window.close()
        app.processEvents()
