"""中央產品 mount、背景generation與exact下鑽返回；不啟真模型或資料。"""
from dataclasses import replace
from types import SimpleNamespace, MethodType

from PySide6.QtWidgets import QTabWidget, QWidget
from app_module.recommendation.personal_h20_research_cohort import (
    PersonalH20ResearchCohort, PersonalH20ResearchRow, PersonalH20ResearchSelection,
)
from ui_qt.main import MainWindow
from tests.test_ui_qt_stock_research_report import _app


class Signal:
    def __init__(self): self.callbacks = []
    def connect(self, callback): self.callbacks.append(callback)
    def emit(self, *args):
        for callback in self.callbacks: callback(*args)


class Worker:
    def __init__(self, fn, *args, **kwargs):
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.finished, self.error, self.native_thread_finished = Signal(), Signal(), Signal()
        self.progress = Signal()
    def start(self): pass
    def isRunning(self): return True
    def cancel(self, **kwargs): pass
    def deleteLater(self): pass


class WindowStub(SimpleNamespace):
    """Qt 對 bound method 接收者保存 weak reference。"""


def setup_window(tmp_path, monkeypatch):
    import ui_qt.workers.task_worker as workers
    monkeypatch.setattr(workers, "TaskWorker", Worker)
    app = _app()
    recommendation = QWidget()
    recommendation.result_source_tabs = QTabWidget(recommendation)
    messages, opened, workspaces = [], [], []
    window = WindowStub(config=SimpleNamespace(data_root=tmp_path),
        recommendation_view=recommendation, _shutdown_close_requested=False,
        statusBar=lambda: SimpleNamespace(showMessage=messages.append),
        _coerce_stock_research_context=lambda value: value,
        _open_stock_research_context=opened.append, _select_main_workspace=workspaces.append)
    for name in ("_personal_h20_configuration", "_refresh_personal_h20_cohort", "_request_personal_h20_research", "_save_personal_h20_research"):
        setattr(window, name, MethodType(getattr(MainWindow, name), window))
    MainWindow._mount_personal_h20_research(window, recommendation)
    row = PersonalH20ResearchRow("2330", "available", "", 123, "2026-10-07", "2026-10-06", "2026-10-05",
        "sample", "prediction", str(tmp_path / "capture.json"), "sha256:" + "a" * 64)
    cohort = PersonalH20ResearchCohort(str(tmp_path / "manifest.json"), "sha256:" + "b" * 64,
        "candidate", "sha256:" + "c" * 64, "cycle", row.decision_date, (row.symbol,), (row,))
    selection = PersonalH20ResearchSelection(cohort.manifest_sha256, cohort.candidate_id, cohort.contract_hash,
        cohort.cycle_id, row.symbol, row.sample_id, row.prediction_id, row.capture_sha256)
    return app, window, recommendation, cohort, selection, opened, messages


def test_main_mount_verified_cohort_exact_drilldown_and_return(tmp_path, monkeypatch):
    app, window, panel, cohort, selection, opened, messages = setup_window(tmp_path, monkeypatch)
    assert panel.result_source_tabs.tabText(0) == "個人模型選股研究（H20毛報酬）"
    window._refresh_personal_h20_cohort()
    reference = object()
    window._personal_h20_cohort_worker.finished.emit((reference, cohort))
    window._request_personal_h20_research(selection)
    assert not opened
    window._personal_h20_cohort_worker.finished.emit((reference, cohort))
    assert len(opened) == 1
    context = opened[0]
    assert context.result_id == "" and context.source_id == "prediction"
    assert context.source_snapshot_hash == cohort.manifest_sha256
    assert (context.decision_date, context.data_date) == ("2026-10-07", "2026-10-06")
    assert context.ml_scope_mode == ""
    MainWindow._return_to_research_source(window, context)
    window._personal_h20_cohort_worker.finished.emit((reference, cohort))
    assert window.personal_h20_research_widget.restore_selection(selection)
    assert not messages
    panel.close()
    app.processEvents()


def test_main_discards_stale_changed_config_closing_and_failed_selection(tmp_path, monkeypatch):
    app, window, panel, cohort, selection, opened, messages = setup_window(tmp_path, monkeypatch)
    window._refresh_personal_h20_cohort()
    first = window._personal_h20_cohort_worker
    window._refresh_personal_h20_cohort()
    first.finished.emit((object(), cohort))
    assert window.personal_h20_research_widget._cohort is None
    current = window._personal_h20_cohort_worker
    monkeypatch.setenv("PERSONAL_H20_ACTIVATION_CONFIG", str(tmp_path / "other.json"))
    current.finished.emit((object(), cohort))
    assert window.personal_h20_research_widget._cohort is None
    monkeypatch.delenv("PERSONAL_H20_ACTIVATION_CONFIG")
    window._refresh_personal_h20_cohort(selection, open_research=True)
    window._personal_h20_cohort_worker.finished.emit((object(), replace(cohort, cycle_id="different")))
    assert not opened and messages
    window._refresh_personal_h20_cohort()
    window._shutdown_close_requested = True
    window._personal_h20_cohort_worker.finished.emit((object(), cohort))
    assert window.personal_h20_research_widget._cohort is None
    panel.close()
    app.processEvents()


def test_loading_status_and_cancel_preserve_unpublished_cohort(tmp_path, monkeypatch):
    app, window, panel, cohort, selection, opened, messages = setup_window(tmp_path, monkeypatch)
    window._refresh_personal_h20_cohort()
    worker = window._personal_h20_cohort_worker
    assert window._personal_h20_loading_timer.isActive()
    assert "尚未完成" in window._personal_h20_loading_label.text()
    window._personal_h20_read_started_at -= 8
    window._personal_h20_loading_timer.timeout.emit()
    assert "8 秒" in window._personal_h20_loading_label.text()
    worker.progress.emit("來源組 1：重核共同來源", 0)
    assert "來源組 1" in window._personal_h20_loading_label.text()
    window._personal_h20_cancel_read_button.click()
    assert not window._personal_h20_loading_timer.isActive()
    assert "已要求取消" in window._personal_h20_loading_label.text()
    worker.progress.emit("晚到來源訊息", 0)
    assert "晚到" not in window._personal_h20_loading_label.text()
    worker.finished.emit((object(), cohort))
    assert window.personal_h20_research_widget._cohort is None
    assert not opened
    window._refresh_personal_h20_cohort()
    window._personal_h20_cohort_worker.finished.emit((object(), cohort))
    assert "已核驗" in window._personal_h20_loading_label.text()
    assert not window._personal_h20_loading_timer.isActive()
    assert window.personal_h20_research_widget._cohort == cohort
    panel.close()
    app.processEvents()


def test_return_from_other_result_tab_starts_one_exact_cohort_read(tmp_path, monkeypatch):
    """返回的真 Qt tab signal 不應另排未帶原 selection 的完整重讀。"""
    app, window, panel, cohort, selection, opened, messages = setup_window(tmp_path, monkeypatch)
    window._refresh_personal_h20_cohort()
    reference = object()
    window._personal_h20_cohort_worker.finished.emit((reference, cohort))
    window._request_personal_h20_research(selection)
    window._personal_h20_cohort_worker.finished.emit((reference, cohort))
    context = opened[0]
    other_panel = QWidget()
    panel.result_source_tabs.addTab(other_panel, "推薦結果")
    panel.result_source_tabs.setCurrentWidget(other_panel)
    generation_before = window._personal_h20_cohort_generation

    MainWindow._return_to_research_source(window, context)

    assert panel.result_source_tabs.currentWidget() is window.personal_h20_research_panel
    assert window._personal_h20_cohort_generation == generation_before + 1
    window._personal_h20_cohort_worker.finished.emit((reference, cohort))
    assert window.personal_h20_research_widget.restore_selection(selection)
    assert window.personal_h20_research_widget._cohort == cohort
    assert not messages
    # 一般使用者切換回H20仍保留原自動核驗入口。
    panel.result_source_tabs.setCurrentWidget(other_panel)
    before_user_switch = window._personal_h20_cohort_generation
    panel.result_source_tabs.setCurrentWidget(window.personal_h20_research_panel)
    assert window._personal_h20_cohort_generation == before_user_switch + 1
    panel.close()
    app.processEvents()
