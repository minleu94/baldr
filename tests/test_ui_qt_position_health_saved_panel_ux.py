"""已保存部位健康評估面板的可見文案回歸檢查。"""

from __future__ import annotations

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal
from PySide6.QtWidgets import QApplication
from types import SimpleNamespace

from ui_qt.widgets import position_health_saved_panel
from ui_qt.widgets.position_health_saved_panel import PositionHealthSavedPanel, _format_opened_status


@pytest.fixture
def application() -> QApplication:
    current = QApplication.instance()
    if current is not None:
        return current
    return QApplication(["position-health-saved-panel-ux"])


def test_saved_panel_uses_localized_identity_and_guides_empty_state(
    application: QApplication,
) -> None:
    panel = PositionHealthSavedPanel(
        reader=object(),
        scope_factory=object(),
        selection_store=object(),
    )
    try:
        assert panel.title() == "已保存健康評估（Paper 主帳戶快照精確核對）"
        assert "部位識別" in panel.saved_detail_label.text()
        assert "position identity" not in panel.saved_detail_label.text()
        assert "最新評估" in panel.saved_status_label.text()

        # 空清單只呈現引導文案，不嘗試開啟或選取任何評估。
        panel._on_finished(0, "list_candidates", ())
        assert panel.saved_receipt_selector.count() == 0
        assert panel.saved_receipt_selector.currentIndex() == -1
        assert "目前沒有可選的已保存評估" in panel.saved_status_label.text()
        assert "完成並保存一份健康評估" in panel.saved_status_label.text()
        assert "載入已保存評估" in panel.saved_status_label.text()
        assert "不會自動改用最新評估" in panel.saved_status_label.text()

        # 回訪以部位識別為準，缺少原列時明示不會退回股票代號。
        panel._select_saved_position("saved-position-identity")
        assert "部位識別" in panel.saved_detail_label.text()
        assert "未以股票代號替代" in panel.saved_detail_label.text()
    finally:
        panel.begin_shutdown()
        panel.close()


def test_opened_status_uses_paper_account_label_and_preserves_id() -> None:
    record = SimpleNamespace(
        decision_date="2026-10-08", portfolio_id="paper-main",
        source_observed_at="2026-10-08T09:05:00+08:00",
        source_available_at="2026-10-08T09:05:00+08:00",
    )
    model = SimpleNamespace(
        status="passed", observed_at="2026-10-08T09:06:00+08:00",
        health_source_available_at="2026-10-08T09:05:00+08:00",
        baseline_saved_available_at="2026-10-08T09:04:00+08:00",
        saved_receipt_available_at="2026-10-08T09:07:00+08:00",
    )
    opened = SimpleNamespace(read_model=model, source=SimpleNamespace(available_at="2026-10-08T09:07:00+08:00"))

    text = _format_opened_status(opened, record)

    assert "帳戶：Paper 主帳戶（paper-main）；附加命名空間：無。" in text
    assert "namespace：" not in text
    assert "來源觀察：2026-10-08T09:05:00+08:00" in text


def test_late_worker_signals_are_safe_after_panel_destruction(
    application: QApplication, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeferredWorker(QObject):
        finished = Signal(object)
        error = Signal(str)
        cancelled = Signal()
        native_thread_finished = Signal()

        def cancel(self, *, cooperative: bool, wait: bool) -> None:
            del cooperative, wait

        def start(self) -> None:
            pass

    worker_holder: list[DeferredWorker] = []

    def make_worker(*args: object) -> DeferredWorker:
        del args
        worker = DeferredWorker()
        worker_holder.append(worker)
        return worker

    monkeypatch.setattr(position_health_saved_panel, "TaskWorker", make_worker)
    panel = PositionHealthSavedPanel(
        reader=object(),
        scope_factory=object(),
        selection_store=object(),
    )

    panel.load_candidates()
    relay = panel._worker_events
    panel.begin_shutdown()
    panel.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not shiboken6.isValid(panel)
    assert shiboken6.isValid(relay)

    worker = worker_holder[0]
    worker.finished.emit(())
    worker.error.emit("late-error")
    worker.cancelled.emit()
    worker.native_thread_finished.emit()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    application.processEvents()
