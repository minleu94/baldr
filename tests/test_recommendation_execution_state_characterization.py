"""R013 Qt recommendation execution 的 sealed-result regression tests。"""

from __future__ import annotations

import os
import threading
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionStatus,
    RecommendationExecution,
    Request,
    ReferenceKind,
    VersionReference,
)
from app_module.recommendation.personal_use_policy import (
    RecommendationPersonalUsePolicyV1,
)
from decision_module.recommendation.contracts import RecommendationItem
from ui_qt.views.recommendation import execution_coordinator
from ui_qt.views.recommendation.execution_coordinator import (
    RecommendationExecutionRequest,
)
from ui_qt.views.recommendation_view import RecommendationView
from ui_qt.workers.task_worker import (
    ProgressTaskWorker,
    TaskWorker,
    running_task_workers,
)


def _config(*, run_id: str = "default", patterns=None, indicators=None):
    return {
        "run_id": run_id,
        "patterns": {"selected": ["W底"] if patterns is None else patterns},
        "signals": {
            "technical_indicators": ["trend"] if indicators is None else indicators
        },
        "filters": {"price_change_min": "2.50"},
        "profile_id": "momentum",
        "profile_version": "2.1",
        "regime": "Trend",
    }


def _execution(
    result_id: str,
    *,
    stock_code: str = "2330",
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    empty: bool = False,
) -> RecommendationExecution:
    request_config = RecommendationExecutionRequest(_config()).config_snapshot
    request = Request(
        config_snapshot=request_config,
        profile_ref=VersionReference(ReferenceKind.PROFILE, "momentum", "2.1"),
        max_stocks=200,
        top_n=50,
    )
    items = () if empty else (
        RecommendationItem(
            stock_code=stock_code,
            stock_name="台積電" if stock_code == "2330" else stock_code,
            close_price=900,
            price_change=15,
            rule_score=85,
            indicator_score=80,
            pattern_score=90,
            volume_score=85,
            reason_text="量能放大；均線多頭",
            industry="半導體",
            regime_match=True,
            rank=1,
        ),
    )
    completed = status is ExecutionStatus.COMPLETED
    return RecommendationExecution(
        result_id=result_id,
        request=request,
        context=Context(
            as_of_date=date(2026, 9, 23),
            created_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
            available_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
            decision_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        ),
        status=status,
        decision=DecisionBatch(items=items, regime="Trend") if completed else None,
        failure_reason=None if completed else "cancelled by test",
    )


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _wait_worker(worker: TaskWorker | ProgressTaskWorker) -> None:
    assert worker.wait(5_000) is True
    _app().processEvents()


def test_worker_returns_the_same_typed_execution(monkeypatch):
    execution = _execution("rec-worker")
    calls = []

    def execute(_service, config, **kwargs):
        calls.append((config, kwargs))
        return execution

    monkeypatch.setattr(execution_coordinator, "execute_recommendation", execute)
    request = RecommendationExecutionRequest(_config(run_id="worker"))
    worker = TaskWorker(request.execute, object())
    returned: list[object] = []
    errors: list[str] = []
    worker.finished.connect(returned.append)
    worker.error.connect(errors.append)
    worker.start()
    _wait_worker(worker)

    assert returned == [execution]
    assert returned[0] is execution
    assert errors == []
    assert calls[0][0]["run_id"] == "worker"
    assert "manual_qt_snapshot" not in calls[0][0]
    assert '"manual_qt_snapshot":true' in request.config_snapshot.raw_config_json
    worker.deleteLater()
    _app().processEvents()


def test_prestart_cancellation_returns_named_execution_not_empty_list():
    progress: list[tuple[str, int]] = []
    request = RecommendationExecutionRequest(_config(run_id="pre-start-cancel"))

    result = request.execute(
        object(),
        progress_callback=lambda message, percentage: progress.append(
            (message, percentage)
        ),
        cancellation_callback=lambda: True,
        detailed_progress=True,
    )

    assert result.status is ExecutionStatus.CANCELLED
    assert result.decision is None
    assert result.failure_reason == "cancelled_before_start"
    assert progress[0] == ("讀取股票數據...", 10)
    assert any("取消" in message for message, _percentage in progress)


def test_invalid_request_fails_preflight_without_starting_worker(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        "ui_qt.views.recommendation_view.QMessageBox.warning",
        lambda *args: warnings.append(args[1:]),
    )
    service = MagicMock()
    view = SimpleNamespace(
        _collect_config=lambda: _config(patterns=[]),
        is_beginner_mode=False,
        recommendation_service=service,
    )

    RecommendationView._execute_recommendation(view)

    assert warnings == [("配置錯誤", "請至少選擇一個圖形模式")]
    assert not hasattr(view, "worker")
    service.assert_not_called()


def test_new_request_keeps_last_good_result_and_selection_while_worker_starts(
    monkeypatch,
):
    execution = _execution("rec-last-good")
    table_model = object()
    policy = RecommendationPersonalUsePolicyV1.default_rule_only("state-test")
    invocation_service = object()
    service = MagicMock()
    service.with_personal_use_policy.return_value = invocation_service
    starts: list[tuple[object, object, str]] = []
    view = SimpleNamespace()

    class SignalProbe:
        def connect(self, _callback):
            pass

    class ControlledWorker:
        def __init__(self, _task_function):
            self.progress = SignalProbe()
            self.finished = SignalProbe()
            self.error = SignalProbe()
            self.cancelled = SignalProbe()

        def start(self):
            starts.append(
                (
                    view.current_execution,
                    view.results_table.model,
                    view.result_status_label.setText.call_args.args[0],
                )
            )

    monkeypatch.setattr(
        "ui_qt.views.recommendation_view.ProgressTaskWorker", ControlledWorker
    )
    view._collect_config = lambda: _config(run_id="replacement")
    view._personal_policy_for_invocation = lambda: policy
    view.is_beginner_mode = False
    view.recommendation_service = service
    view.current_execution = execution
    view.current_read_model = None
    view.current_result_id = ""
    view.results_table = SimpleNamespace(model=table_model)
    view.execute_btn = MagicMock()
    view.result_status_label = MagicMock()
    view.progress_bar = MagicMock()
    view.progress_label = MagicMock()
    view._begin_execution_status = MagicMock()
    view._on_progress = MagicMock()
    view._on_recommendation_finished = MagicMock()
    view._on_recommendation_error = MagicMock()
    view._on_recommendation_cancelled = MagicMock()

    RecommendationView._execute_recommendation(view)

    assert len(starts) == 1
    assert starts[0][0] is execution
    assert starts[0][1] is table_model
    assert "rec-last-good" in starts[0][2]
    service.with_personal_use_policy.assert_called_once_with(policy)


def test_cancelled_and_stale_generation_callbacks_do_not_replace_last_good():
    last_good = _execution("rec-good")
    cancelled = _execution("rec-cancelled", status=ExecutionStatus.CANCELLED)
    stale_view = SimpleNamespace(
        _execution_generation=4,
        current_execution=last_good,
        recommendations_model="last-good-model",
        _signal_generation_is_current=lambda generation=None: generation == 4,
        _complete_personal_policy_one_shot=lambda: None,
    )
    RecommendationView._on_recommendation_finished(
        stale_view, _execution("rec-stale"), generation=3
    )
    assert stale_view.current_execution is last_good
    assert stale_view.recommendations_model == "last-good-model"

    view = SimpleNamespace(
        _execution_generation=4,
        current_execution=last_good,
        _execution_cancel_requested=False,
        _finish_execution_status=MagicMock(),
        execute_btn=MagicMock(),
        progress_bar=MagicMock(),
        progress_label=MagicMock(),
        result_status_label=MagicMock(),
        research_actions_toggle=MagicMock(),
        research_actions_widget=MagicMock(),
        recommendations_model="last-good-model",
        _signal_generation_is_current=lambda generation=None: generation == 4,
        _complete_personal_policy_one_shot=lambda: None,
    )
    view._current_items = lambda: last_good.items
    view._on_recommendation_cancelled = lambda generation=None: (
        RecommendationView._on_recommendation_cancelled(view, generation)
    )
    RecommendationView._on_recommendation_finished(view, cancelled, generation=4)

    assert view.current_execution is last_good
    assert view.recommendations_model == "last-good-model"
    assert "沒有套用部分結果" in view.result_status_label.setText.call_args.args[0]


def test_progress_events_are_ui_projection_of_typed_execution(monkeypatch):
    execution = _execution("rec-progress")

    def execute(_service, _config, **kwargs):
        progress = kwargs["progress"]
        progress("recommendation_started", 10)
        progress("recommendation_body_started", 35)
        progress("recommendation_body_finished", 90)
        progress("recommendation_execution_finished", 100)
        return execution

    monkeypatch.setattr(execution_coordinator, "execute_recommendation", execute)
    progress_events: list[tuple[str, int]] = []
    request = RecommendationExecutionRequest(_config(run_id="progress"))

    result = request.execute(
        object(),
        progress_callback=lambda message, value: progress_events.append(
            (message, value)
        ),
        detailed_progress=True,
    )

    assert result is execution
    assert progress_events == [
        ("讀取股票數據...", 10),
        ("建立分析範圍...", 25),
        ("執行推薦規則...", 35),
        ("整理推薦結果...", 90),
        ("分析完成", 100),
    ]


def test_delete_later_waits_for_native_thread_completion_and_registry_cleanup():
    app = _app()
    import ui_qt.workers.task_worker as task_worker_module

    entered = threading.Event()
    release = threading.Event()
    native_finished = threading.Event()
    destroyed = threading.Event()
    result_events: list[str] = []

    def task():
        entered.set()
        if not release.wait(5):
            raise TimeoutError("worker lifecycle barrier 未釋放")
        return "done"

    worker = TaskWorker(task)
    worker.finished.connect(lambda _value: result_events.append("result"))
    worker.native_thread_finished.connect(
        lambda: (result_events.append("native_finished"), native_finished.set())
    )
    worker.destroyed.connect(lambda *_args: destroyed.set())
    worker.start()
    assert entered.wait(5)
    assert worker in task_worker_module._MANAGED_TASK_WORKERS
    assert worker in running_task_workers()

    worker.deleteLater()
    assert worker._delete_later_requested is True
    assert worker in task_worker_module._MANAGED_TASK_WORKERS

    release.set()
    try:
        assert worker.wait(5_000) is True
        app.processEvents()
    finally:
        release.set()

    assert native_finished.wait(5)
    app.processEvents()
    assert result_events == ["result", "native_finished"]
    assert worker not in task_worker_module._MANAGED_TASK_WORKERS
    assert worker not in task_worker_module._LIVE_TASK_WORKERS
    assert destroyed.is_set()
