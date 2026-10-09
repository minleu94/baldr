"""驗證取消與關閉後，真背景工作遲到結果不覆蓋研究。"""

from __future__ import annotations

import os
from threading import Event
import time
from typing import Callable, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from ui_qt.views.daily_market_technical_official_disposition_revenue_view import (
    DailyMarketTechnicalOfficialDispositionRevenueView,
)


def _pump_until(app: QApplication, predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


@pytest.mark.parametrize("action", ("cancel", "shutdown"))
def test_late_worker_result_never_applies_after_cancel_or_shutdown(action: str) -> None:
    app = cast(QApplication, QApplication.instance() or QApplication([]))
    view = DailyMarketTechnicalOfficialDispositionRevenueView()
    entered, release = Event(), Event()
    applied: list[object] = []
    settled: list[tuple[str, bool]] = []
    view.operationSettled.connect(lambda kind, success: settled.append((kind, success)))
    view.summary_label.setText("原研究保留")

    def task(cancel_callback: Callable[[], object] | None = None) -> object:
        entered.set()
        if not release.wait(5):
            raise RuntimeError("測試未釋放背景工作")
        return "遲到研究"

    try:
        view._start_task("延遲驗證", task, applied.append)
        _pump_until(app, entered.is_set)
        worker = view.active_worker
        assert worker is not None and worker.isRunning()
        token = view._busy_token
        if action == "cancel":
            view.cancel_current_operation()
        else:
            assert view.begin_shutdown() is False
        # 即使已排入 GUI queue 的成功訊號遲到，也不能套用。
        view._task_finished(token, "已排程遲到結果")
        assert applied == []
        assert view.summary_label.text() == "原研究保留"
        release.set()
        _pump_until(app, lambda: not view._has_running_worker())
        app.processEvents()
        assert applied == []
        assert settled and all(not success for _, success in settled)
        assert view.summary_label.text() == "原研究保留"
        assert view.begin_shutdown()
    finally:
        release.set()
        _pump_until(app, lambda: view.begin_shutdown())
        view.close()
        app.processEvents()
