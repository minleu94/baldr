import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGroupBox

from ui_qt.views.watchlist_view import WatchlistView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_watchlist_desktop_layout_keeps_both_universe_lists_visible(monkeypatch, tmp_path: Path):
    _app()

    class UniverseStub:
        def list_watchlists(self):
            return [{"name": "成長觀察", "count": 3, "watchlist_id": "growth"}]

        def load_watchlist(self, identifier):
            assert identifier == "growth"
            return SimpleNamespace(codes=["2330", "2317", "2454"])

    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: UniverseStub(),
    )
    service = MagicMock()
    service.get_stocks.return_value = [
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "added_at": "2026-09-08 09:00:00",
            "source": "manual",
            "notes": "",
        }
    ]
    config = SimpleNamespace(output_root=tmp_path)
    view = WatchlistView(service, config=config)
    view.show()
    view.resize(1400, 800)
    _app().processEvents()

    assert view.main_splitter.orientation() == Qt.Horizontal
    assert view.management_splitter.orientation() == Qt.Vertical
    candidate_panel = view.findChild(QGroupBox, "watchlistCandidatePanel")
    universe_panel = view.findChild(QGroupBox, "watchlistUniversePanel")
    assert candidate_panel is not None
    assert universe_panel is not None
    assert view.findChild(QGroupBox, "watchlistOpsGroup") is not None
    assert view.findChild(QGroupBox, "watchlistOpsGroup").parent() is candidate_panel
    assert view.universe_list.height() > 150
    assert view.universe_stock_list.height() > 150
    assert view.universe_stock_list.count() == 0
    assert view.stats_label.text() == "共 1 檔股票"
    assert "已更新：1 筆" in view.status_label.text()

    view.universe_list.setCurrentRow(0)
    assert view.universe_stock_list.count() == 3
    view.close()


def test_watchlist_narrow_layout_switches_to_vertical_without_losing_controls(monkeypatch, tmp_path: Path):
    _app()

    class UniverseStub:
        def list_watchlists(self):
            return []

    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: UniverseStub(),
    )
    service = MagicMock()
    service.get_stocks.return_value = []
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    view.show()
    view.resize(600, 800)
    _app().processEvents()

    assert view.main_splitter.orientation() == Qt.Vertical
    assert view.management_splitter.orientation() == Qt.Vertical
    assert view.findChild(QGroupBox, "watchlistCandidatePanel") is not None
    assert view.findChild(QGroupBox, "watchlistUniversePanel") is not None
    assert view.findChild(QGroupBox, "watchlistOpsGroup") is not None
    view.close()


def test_candidate_table_hides_raw_identity_but_keeps_exact_source_after_sort(monkeypatch, tmp_path):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    identity = {"result_id": "original-result", "stock_code": "2330"}
    service = MagicMock()
    service.get_stocks.return_value = [
        {"stock_code": "2330", "stock_name": "台積電", "decision_identity": identity},
        {"stock_code": "2603", "stock_name": "長榮"},
        {"stock_code": "2317", "stock_name": "鴻海", "decision_identity": identity},
    ]
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    view._load_watchlist()
    model = view.stocks_model
    headers = [model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())]
    assert "decision_identity" not in headers
    assert "推薦來源" in headers
    model.sort(headers.index("證券代號"), Qt.AscendingOrder)
    frame = model.getDataFrame()
    assert list(frame["推薦來源"]) == ["來源不一致，需核對", "已連結原推薦", "未連結原推薦"]
    assert frame.iloc[1]["decision_identity"] == identity
    assert view._row_decision_identity(frame.iloc[1], "2330").result_id == "original-result"
    assert "不是評分或買賣訊號" in view.source_link_hint.text()
    view.close()
