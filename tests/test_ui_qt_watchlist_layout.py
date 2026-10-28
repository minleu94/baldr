import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QGroupBox, QLabel, QMessageBox, QProgressBar,
)

from ui_qt.widgets.info_button import InfoButton, InfoDialog
from ui_qt.views.watchlist_view import WatchlistView
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.watchlist_review_state import (
    WatchlistReviewSnapshot,
    WatchlistReviewSnapshotRow,
    WatchlistReviewSourceIdentity,
    WatchlistReviewState,
    ReviewStatus,
)


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _review_snapshot_row(
    position: int,
    stock_code: str,
    source_id: str,
    status: ReviewStatus,
    identity_char: str,
) -> WatchlistReviewSnapshotRow:
    return WatchlistReviewSnapshotRow(
        position=position,
        stock_code=stock_code,
        stock_name=f"測試 {stock_code}",
        added_at="2026-10-24T08:00:00+08:00",
        source="recommendation",
        notes="私人理由不可出現在分布卡",
        tags=(),
        source_id=source_id,
        decision_identity=DecisionIdentity(
            stock_code=stock_code, result_id=source_id,
        ),
        research_bookmark=None,
        source_identity=WatchlistReviewSourceIdentity(
            stock_code=stock_code, item_sha256=identity_char * 64,
        ),
        review_status=status,
    )


class _ReviewSnapshotService(MagicMock):
    def __init__(self, snapshot: object = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.snapshot_value: object = snapshot
        self.review_snapshot_calls: int = 0

    def get_review_snapshot(self) -> object:
        self.review_snapshot_calls += 1
        if isinstance(self.snapshot_value, BaseException):
            raise self.snapshot_value
        return self.snapshot_value


class _ManualSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self.callbacks):
            callback(*args)


class _ManualTaskWorker:
    def __init__(self, task) -> None:
        self.task = task
        self.finished = _ManualSignal()
        self.native_thread_finished = _ManualSignal()
        self.running = False
        self.cancel_calls = []

    def start(self) -> None:
        self.running = True

    def isRunning(self) -> bool:
        return self.running

    def cancel(self, *, cooperative: bool, wait: bool) -> None:
        self.cancel_calls.append((cooperative, wait))

    def deleteLater(self) -> None:
        return None


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
    distribution_group = view.findChild(QGroupBox, "watchlistReviewDistribution")
    assert distribution_group is not None
    assert candidate_panel.layout().indexOf(distribution_group) < candidate_panel.layout().indexOf(
        view.stocks_table
    )
    assert view.universe_list.height() > 150
    assert view.universe_stock_list.height() > 150
    assert view.universe_stock_list.count() == 0
    assert view.stats_label.text() == "1 筆候選列／1 檔不同代號"
    assert "已更新：1 筆" in view.status_label.text()
    assert "同版查看狀態快照" in view.review_distribution_status.text()
    service.get_stocks.assert_called_once_with()

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
    assert view.stats_label.text() == "0 筆候選列／0 檔不同代號（目前沒有候選）"
    assert "0 筆候選列／0 檔不同代號" in view.watchlist_focus_summary.conclusion_label.text()
    view.close()


def test_watchlist_load_failure_keeps_candidate_counts_unknown(monkeypatch, tmp_path: Path):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args, **_kwargs: 0)
    service = MagicMock()
    service.get_stocks.side_effect = OSError("candidate store unavailable")

    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))

    assert view.stats_label.text() == "候選列／不同代號數未知（載入失敗）"
    assert "載入失敗" in view.status_label.text()
    assert "查看狀態分布不可用" in view.review_distribution_status.text()
    assert "狀態尚未完成讀取" in view.watchlist_focus_summary.conclusion_label.text()
    assert "0 筆候選列" not in view.stats_label.text()
    view._load_selected_analysis()
    assert "狀態尚未完成讀取" in view.watchlist_focus_summary.conclusion_label.text()
    view.close()


def test_watchlist_navigation_has_no_candidate_hint_popup_and_info_route_still_opens(
    monkeypatch, tmp_path: Path
):
    app = _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    service = MagicMock()
    service.get_stocks.return_value = []
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))

    view.show()
    for width in (1400, 600, 1400):
        view.resize(width, 800)
        app.processEvents()
        orphan_hints = [
            widget
            for widget in app.topLevelWidgets()
            if isinstance(widget, QLabel)
            and widget.isVisible()
            and widget.text() == "研究候選池，或保存成可重用的選股清單。"
        ]
        assert orphan_hints == []

    view.hide()
    app.processEvents()
    view.show()
    app.processEvents()
    assert not [
        widget
        for widget in app.topLevelWidgets()
        if isinstance(widget, QLabel)
        and widget.isVisible()
        and widget.text() == "研究候選池，或保存成可重用的選股清單。"
    ]

    opened = []

    def fake_exec(dialog):
        opened.append(dialog)
        return 0

    monkeypatch.setattr(InfoDialog, "exec", fake_exec)
    info_button = view.findChild(InfoButton)
    assert info_button is not None
    info_button.click()
    assert [dialog.tab_key for dialog in opened] == ["watchlist"]
    view.close()


def test_candidate_table_hides_raw_identity_but_keeps_exact_source_after_sort(monkeypatch, tmp_path):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    identity = {"result_id": "original-result", "stock_code": "2330"}
    second_identity = {"result_id": "second-result", "stock_code": "2330"}
    service = MagicMock()
    service.get_stocks.return_value = [
        {"stock_code": "2330", "stock_name": "台積電", "decision_identity": identity},
        {"stock_code": "2330", "stock_name": "台積電", "decision_identity": second_identity},
        {"stock_code": "2603", "stock_name": "長榮"},
    ]
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    view._load_watchlist()
    model = view.stocks_model
    headers = [model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())]
    assert "decision_identity" not in headers
    assert "推薦來源" in headers
    model.sort(headers.index("證券代號"), Qt.AscendingOrder)
    frame = model.getDataFrame()
    assert view.stats_label.text() == "3 筆候選列／2 檔不同代號"
    assert model.rowCount() == 3
    assert len(frame[frame["證券代號"] == "2330"]) == 2
    linked_rows = frame[frame["證券代號"] == "2330"]
    assert {row["decision_identity"]["result_id"] for _, row in linked_rows.iterrows()} == {
        "original-result",
        "second-result",
    }
    assert all(row == "已連結原推薦" for row in linked_rows["推薦來源"])
    assert view._row_decision_identity(linked_rows.iloc[0], "2330").is_linked
    assert "3 筆候選列／2 檔不同代號" in view.watchlist_focus_summary.conclusion_label.text()
    assert "不是評分或買賣訊號" in view.source_link_hint.text()
    view.close()


def test_review_snapshot_loads_table_and_counts_distinct_same_stock_rows_once(
    monkeypatch, tmp_path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    rows = (
        _review_snapshot_row(0, "2330", "result-a", "confirmed", "a"),
        _review_snapshot_row(1, "2330", "result-b", "deferred", "b"),
        _review_snapshot_row(2, "2603", "result-c", "pending", "c"),
        _review_snapshot_row(3, "2317", "result-d", "unknown", "d"),
    )
    snapshot = WatchlistReviewSnapshot(status="loaded", revision=12, rows=rows)
    service = _ReviewSnapshotService(snapshot)
    service.get_stocks.side_effect = AssertionError(
        "snapshot path must not perform another Watchlist read"
    )

    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))

    assert service.review_snapshot_calls == 1
    service.get_stocks.assert_not_called()
    assert view.review_distribution_status.text() == (
        "同一讀取 revision 12；依 4 筆候選列統計。"
    )
    assert view.stocks_model.rowCount() == 4
    frame = view.stocks_model.getDataFrame()
    assert len(frame[frame["證券代號"] == "2330"]) == 2
    assert view.review_distribution_counts["pending"].text() == "1 / 4 筆"
    assert view.review_distribution_counts["confirmed"].text() == "1 / 4 筆"
    assert view.review_distribution_counts["deferred"].text() == "1 / 4 筆"
    assert view.review_distribution_counts["unknown"].text() == "1 / 4 筆"
    assert all(not bar.isHidden() and bar.value() == 1 and bar.maximum() == 4
               for bar in view.review_distribution_bars.values())
    chart_text = "\n".join(
        label.text()
        for label in view.review_distribution_group.findChildren(QLabel)
    )
    assert "私人理由不可出現在分布卡" not in chart_text
    assert view.stocks_model.getDataFrame().iloc[0]["備註"] == (
        "私人理由不可出現在分布卡"
    )
    view.close()


def test_review_snapshot_empty_missing_and_unavailable_clear_counts_fail_closed(
    monkeypatch, tmp_path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    loaded = WatchlistReviewSnapshot(
        status="loaded",
        revision=8,
        rows=(_review_snapshot_row(0, "2330", "one", "confirmed", "e"),),
    )
    service = _ReviewSnapshotService(loaded)
    service.get_stocks.side_effect = AssertionError(
        "typed snapshot path must not call get_stocks"
    )
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    assert not view.review_distribution_bars["confirmed"].isHidden()

    service.snapshot_value = WatchlistReviewSnapshot(
        status="loaded", revision=9, rows=(),
    )
    view._load_watchlist()
    assert view.stocks_model.rowCount() == 0
    assert view.review_distribution_status.text() == (
        "同一讀取 revision 9；依 0 筆候選列統計。"
    )
    assert all(
        label.text() == "0 / 0 筆"
        for label in view.review_distribution_counts.values()
    )
    assert all(bar.isHidden() for bar in view.review_distribution_bars.values())

    service.snapshot_value = WatchlistReviewSnapshot(
        status="missing", revision=None,
    )
    view._load_watchlist()
    assert view.stats_label.text() == "候選列／不同代號數未知（清單不存在）"
    assert "尚無已保存清單" in view.review_distribution_status.text()
    assert all(label.text() == "—" for label in view.review_distribution_counts.values())
    assert all(bar.isHidden() for bar in view.review_distribution_bars.values())
    assert not view.remove_btn.isEnabled()
    assert not view.clear_btn.isEnabled()
    assert not view.save_to_universe_btn.isEnabled()
    assert not view.send_to_research_lab_btn.isEnabled()

    service.snapshot_value = WatchlistReviewSnapshot(
        status="unavailable", revision=None, error_code="OSError",
    )
    view._load_watchlist()
    assert view.stats_label.text() == "候選列／不同代號數未知（載入失敗）"
    assert "快照不可用" in view.review_distribution_status.text()
    assert all(label.text() == "—" for label in view.review_distribution_counts.values())
    assert all(bar.isHidden() for bar in view.review_distribution_bars.values())
    service.get_stocks.assert_not_called()
    view.close()


def test_declared_review_snapshot_failure_never_falls_back_to_get_stocks(
    monkeypatch, tmp_path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    for invalid_snapshot in (object(), OSError("storage detail")):
        service = _ReviewSnapshotService(invalid_snapshot)
        service.get_stocks.return_value = [
            {"stock_code": "2330", "stock_name": "不應沿用"}
        ]
        view = WatchlistView(
            service, config=SimpleNamespace(output_root=tmp_path)
        )
        assert service.review_snapshot_calls == 1
        service.get_stocks.assert_not_called()
        assert view.stats_label.text() == "候選列／不同代號數未知（載入失敗）"
        assert "快照不可用" in view.review_distribution_status.text()
        assert all(bar.isHidden() for bar in view.review_distribution_bars.values())
        view.close()


def test_candidate_search_filters_loaded_rows_without_changing_source_identity(
    monkeypatch, tmp_path: Path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    snapshot = WatchlistReviewSnapshot(
        status="loaded",
        revision=42,
        rows=(
            _review_snapshot_row(0, "2330", "result-a", "pending", "f"),
            _review_snapshot_row(1, "2317", "result-c", "confirmed", "g"),
            _review_snapshot_row(2, "2330", "result-b", "deferred", "h"),
            _review_snapshot_row(3, "2603", "result-d", "unknown", "i"),
        ),
    )
    service = _ReviewSnapshotService(snapshot)
    service.query_stock_names.return_value = {
        "2330": "台積電",
        "2317": "鴻海",
        "2603": "長榮",
    }
    service.get_stocks.side_effect = AssertionError(
        "local candidate search must not perform another Watchlist read"
    )
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))

    assert view.stocks_model is not None
    assert view.stocks_model.rowCount() == 4
    assert view.stats_label.text() == "4 筆候選列／3 檔不同代號"
    assert "顯示全部 4 筆候選列" in view.candidate_search_summary.text()
    assert all(not view.stocks_table.isRowHidden(index) for index in range(4))
    assert service.review_snapshot_calls == 1
    service.query_stock_names.assert_called_once_with(["2330", "2317", "2330", "2603"])
    service.get_stocks.assert_not_called()

    view.candidate_search_input.setText("2330")
    frame = view.stocks_model.getDataFrame()
    visible_sources = {
        str(frame.iloc[index]["source_id"])
        for index in range(len(frame))
        if not view.stocks_table.isRowHidden(index)
    }
    assert visible_sources == {"result-a", "result-b"}
    assert "目前搜尋「2330」｜符合 2／4 筆候選列" in (
        view.candidate_search_summary.text()
    )

    second_source_index = int(
        frame.index[frame["source_id"] == "result-b"][0]
    )
    view.stocks_table.selectRow(second_source_index)
    selected = view._selected_watchlist_row()
    assert selected is not None
    assert selected[0]["source_id"] == "result-b"

    view.candidate_search_input.setText("鴻海")
    frame = view.stocks_model.getDataFrame()
    assert [
        str(frame.iloc[index]["證券代號"])
        for index in range(len(frame))
        if not view.stocks_table.isRowHidden(index)
    ] == ["2317"]
    assert "符合 1／4 筆候選列" in view.candidate_search_summary.text()
    assert view._selected_watchlist_row() is None

    view.candidate_search_input.setText("不存在")
    assert all(view.stocks_table.isRowHidden(index) for index in range(4))
    assert "符合 0／4 筆候選列" in view.candidate_search_summary.text()

    view.candidate_search_input.setText("2330")
    view.stocks_model.sort(0, Qt.DescendingOrder)
    frame = view.stocks_model.getDataFrame()
    visible_rows = [
        frame.iloc[index]
        for index in range(len(frame))
        if not view.stocks_table.isRowHidden(index)
    ]
    assert len(visible_rows) == 2
    assert {str(row["證券代號"]) for row in visible_rows} == {"2330"}
    assert {str(row["source_id"]) for row in visible_rows} == {
        "result-a", "result-b",
    }

    view.candidate_search_input.clear()
    assert all(not view.stocks_table.isRowHidden(index) for index in range(4))
    assert "顯示全部 4 筆候選列" in view.candidate_search_summary.text()
    assert view.stats_label.text() == "4 筆候選列／3 檔不同代號"
    assert service.review_snapshot_calls == 1
    service.query_stock_names.assert_called_once()
    service.get_stocks.assert_not_called()
    view.close()


def test_candidate_search_count_stays_unknown_until_watchlist_load_finishes(
    monkeypatch, tmp_path: Path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    service = _ReviewSnapshotService(
        WatchlistReviewSnapshot(status="loaded", revision=43, rows=())
    )
    workers = []

    def worker_factory(task):
        worker = _ManualTaskWorker(task)
        workers.append(worker)
        return worker

    monkeypatch.setattr("ui_qt.views.watchlist_view.TaskWorker", worker_factory)
    view = WatchlistView(
        service,
        config=SimpleNamespace(output_root=tmp_path),
        async_initial_load=True,
    )

    assert "載入中" in view.candidate_search_summary.text()
    view.candidate_search_input.setText("2330")
    assert "載入中" in view.candidate_search_summary.text()
    assert "未知" in view.candidate_search_summary.text()

    result = workers[0].task()
    workers[0].finished.emit(result)
    assert view.candidate_search_summary.text() == (
        "目前搜尋「2330」｜符合 0／0 筆候選列（已載入空清單）"
    )
    assert view.stats_label.text() == "0 筆候選列／0 檔不同代號（目前沒有候選）"

    service.snapshot_value = WatchlistReviewSnapshot(
        status="missing", revision=None,
    )
    view._load_watchlist()
    assert "未知" in view.candidate_search_summary.text()
    assert "符合 0／0" not in view.candidate_search_summary.text()

    service.snapshot_value = WatchlistReviewSnapshot(
        status="unavailable", revision=None, error_code="OSError",
    )
    view._load_watchlist()
    assert "未知" in view.candidate_search_summary.text()
    assert "符合 0／0" not in view.candidate_search_summary.text()

    workers[0].running = False
    workers[0].native_thread_finished.emit()
    view.close()


def test_async_initial_watchlist_load_returns_before_read_and_applies_on_completion(
    monkeypatch, tmp_path: Path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    snapshot = WatchlistReviewSnapshot(
        status="loaded",
        revision=17,
        rows=(_review_snapshot_row(0, "2330", "async-result", "pending", "a"),),
    )
    service = _ReviewSnapshotService(snapshot)
    service.query_stock_names.side_effect = RuntimeError("name source unavailable")
    service.get_stocks.side_effect = AssertionError(
        "typed snapshot path must not perform another Watchlist read"
    )
    workers = []

    def worker_factory(task):
        worker = _ManualTaskWorker(task)
        workers.append(worker)
        return worker

    monkeypatch.setattr("ui_qt.views.watchlist_view.TaskWorker", worker_factory)
    view = WatchlistView(
        service,
        config=SimpleNamespace(output_root=tmp_path),
        async_initial_load=True,
    )

    assert service.review_snapshot_calls == 0
    assert workers and workers[0].running
    assert view.stocks_model is None
    assert "載入中" in view.status_label.text()

    result = workers[0].task()
    assert service.review_snapshot_calls == 1
    assert view.stocks_model is None
    workers[0].finished.emit(result)

    assert view.stocks_model is not None
    assert view.stocks_model.rowCount() == 1
    assert view.stocks_model.getDataFrame().iloc[0]["證券名稱"] == "測試 2330"
    assert view.review_distribution_status.text() == (
        "同一讀取 revision 17；依 1 筆候選列統計。"
    )
    assert "已更新：1 筆" in view.status_label.text()
    workers[0].running = False
    workers[0].native_thread_finished.emit()
    view.close()


def test_async_initial_watchlist_failure_is_fail_closed_and_old_generation_is_ignored(
    monkeypatch, tmp_path: Path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    critical_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: critical_calls.append((args, kwargs)),
    )
    old_snapshot = WatchlistReviewSnapshot(
        status="loaded",
        revision=1,
        rows=(_review_snapshot_row(0, "2330", "old-result", "pending", "b"),),
    )
    new_snapshot = WatchlistReviewSnapshot(
        status="loaded",
        revision=2,
        rows=(_review_snapshot_row(0, "2317", "new-result", "confirmed", "c"),),
    )
    service = _ReviewSnapshotService(old_snapshot)
    workers = []

    def worker_factory(task):
        worker = _ManualTaskWorker(task)
        workers.append(worker)
        return worker

    monkeypatch.setattr("ui_qt.views.watchlist_view.TaskWorker", worker_factory)
    view = WatchlistView(
        service,
        config=SimpleNamespace(output_root=tmp_path),
        async_initial_load=True,
    )
    old_result = workers[0].task()

    service.snapshot_value = new_snapshot
    view._load_watchlist()
    assert view.stocks_model.getDataFrame().iloc[0]["證券代號"] == "2317"
    assert workers[0].cancel_calls == [(True, False)]

    workers[0].finished.emit(old_result)
    assert view.stocks_model.getDataFrame().iloc[0]["證券代號"] == "2317"

    class FailingFallbackService:
        def get_stocks(self):
            raise RuntimeError("read failed")

    failed_service = FailingFallbackService()
    failed_view = WatchlistView(
        failed_service,
        config=SimpleNamespace(output_root=tmp_path),
        async_initial_load=True,
    )
    failed_worker = workers[-1]
    assert failed_view.stocks_model is None

    failure_result = failed_worker.task()
    failed_worker.finished.emit(failure_result)
    assert failed_view.stocks_model is not None
    assert failed_view.stocks_model.rowCount() == 0
    assert "載入失敗" in failed_view.status_label.text()
    assert "未知（載入失敗）" in failed_view.stats_label.text()
    assert critical_calls == []

    synchronous_failure_view = WatchlistView(
        FailingFallbackService(),
        config=SimpleNamespace(output_root=tmp_path),
    )
    assert critical_calls
    assert "載入失敗" in synchronous_failure_view.status_label.text()

    view.close()
    assert workers[0].cancel_calls[-1] == (True, False)
    workers[0].running = False
    workers[0].native_thread_finished.emit()
    failed_view.close()
    assert failed_worker.cancel_calls[-1] == (True, False)
    failed_worker.running = False
    failed_worker.native_thread_finished.emit()
    synchronous_failure_view.close()


def test_async_initial_watchlist_read_runs_off_gui_thread_and_applies_via_qt_signal(
    tmp_path: Path,
):
    _app()
    gui_thread_id = threading.get_ident()
    read_started = threading.Event()
    release_read = threading.Event()
    service_thread_ids = []
    snapshot = WatchlistReviewSnapshot(
        status="loaded",
        revision=23,
        rows=(_review_snapshot_row(0, "2603", "thread-result", "pending", "d"),),
    )

    class ThreadRecordingService:
        def get_review_snapshot(self):
            service_thread_ids.append(threading.get_ident())
            read_started.set()
            if not release_read.wait(timeout=5):
                raise TimeoutError("test did not release the background read")
            return snapshot

        def query_stock_names(self, stock_codes):
            service_thread_ids.append(threading.get_ident())
            return {}

    view = WatchlistView(
        ThreadRecordingService(),
        async_initial_load=True,
    )
    worker = view._watchlist_load_worker
    assert worker is not None
    assert read_started.wait(timeout=2)
    assert view.stocks_model is None

    loop = QEventLoop()
    applied_thread_ids = []

    def on_loaded():
        applied_thread_ids.append(threading.get_ident())
        loop.quit()

    view.watchlistLoaded.connect(on_loaded)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(5000)
    release_read.set()
    loop.exec()
    timeout.stop()

    assert service_thread_ids
    assert all(thread_id != gui_thread_id for thread_id in service_thread_ids)
    assert applied_thread_ids == [gui_thread_id]
    assert view.stocks_model is not None
    assert view.stocks_model.rowCount() == 1
    assert worker.wait(2000)
    _app().processEvents()
    view.close()


def test_selected_review_revision_mismatch_blocks_save_and_legacy_is_annotated(
    monkeypatch, tmp_path,
):
    _app()
    monkeypatch.setattr(
        "ui_qt.views.watchlist_view.UniverseService",
        lambda _config: SimpleNamespace(list_watchlists=lambda: []),
    )
    row = _review_snapshot_row(0, "2330", "result-a", "confirmed", "f")
    assert row.source_identity is not None
    service = _ReviewSnapshotService(
        WatchlistReviewSnapshot(status="loaded", revision=12, rows=(row,))
    )
    service.get_review_state.return_value = WatchlistReviewState(
        source_identity=row.source_identity,
        reason="單列私人理由",
        state="confirmed",
        revision=13,
        writable=True,
    )
    view = WatchlistView(service, config=SimpleNamespace(output_root=tmp_path))
    selected = view.stocks_model.getDataFrame().iloc[0]
    view._render_observation(selected)
    assert "單列狀態 revision 13" in view.observation_state_label.text()
    assert "候選摘要 revision 12" in view.observation_state_label.text()
    assert view._observation_review is None
    assert not view.confirm_observation_button.isEnabled()
    view._set_observation_state("deferred")
    service.save_review_state.assert_not_called()
    view.close()

    legacy_row = _review_snapshot_row(0, "2317", "legacy", "pending", "1")
    assert legacy_row.source_identity is not None
    legacy_service = _ReviewSnapshotService(
        WatchlistReviewSnapshot(status="loaded", revision=None, rows=(legacy_row,))
    )
    legacy_service.get_review_state.return_value = WatchlistReviewState(
        source_identity=legacy_row.source_identity,
        reason="legacy reason",
        state="pending",
        revision=3,
        writable=True,
    )
    legacy_view = WatchlistView(
        legacy_service, config=SimpleNamespace(output_root=tmp_path)
    )
    legacy_view._render_observation(
        legacy_view.stocks_model.getDataFrame().iloc[0]
    )
    assert "revision 未提供" in legacy_view.review_distribution_status.text()
    assert "可能較新" in legacy_view.observation_state_label.text()
    legacy_view.close()
