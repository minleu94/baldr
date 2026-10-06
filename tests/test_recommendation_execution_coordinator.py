from datetime import datetime, timezone
from unittest.mock import MagicMock

from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionStatus,
    RecommendationExecution,
    Request,
)

from ui_qt.views.recommendation.execution_coordinator import (
    RecommendationExecutionRequest,
)


def _config(patterns=None, indicators=None):
    return {
        "patterns": {"selected": ["W底"] if patterns is None else patterns},
        "signals": {
            "technical_indicators": ["trend"] if indicators is None else indicators
        },
        "filters": {"price_change_min": "2.50"},
        "regime": "Trend",
    }


def test_recommendation_request_validates_required_pattern_and_indicator() -> None:
    assert RecommendationExecutionRequest(_config(patterns=[])).validation_error() == (
        "請至少選擇一個圖形模式"
    )
    assert RecommendationExecutionRequest(_config(indicators=[])).validation_error() == (
        "請至少選擇一個技術指標"
    )
    assert RecommendationExecutionRequest(_config()).validation_error() is None


def _execution(request_snapshot, status=ExecutionStatus.COMPLETED):
    request = Request(
        config_snapshot=request_snapshot,
        max_stocks=200,
        top_n=50,
    )
    return RecommendationExecution(
        result_id="rec_qt_execution_001",
        request=request,
        context=Context(
            created_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
            available_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
            decision_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        ),
        status=status,
        decision=DecisionBatch() if status is ExecutionStatus.COMPLETED else None,
        failure_reason=None if status is ExecutionStatus.COMPLETED else "cancelled_before_start",
    )


def test_recommendation_request_uses_frozen_config_and_returns_same_execution(monkeypatch) -> None:
    from ui_qt.views.recommendation import execution_coordinator as module

    caller_config = _config()
    request = RecommendationExecutionRequest(caller_config)
    caller_config["filters"]["price_change_min"] = "mutated-caller"
    request.config["filters"]["price_change_min"] = "mutated-request"
    sealed = _execution(request.config_snapshot)
    captured = {}

    def execute(service, runtime_config, **kwargs):
        captured.update(service=service, config=runtime_config, kwargs=kwargs)
        kwargs["progress"]("recommendation_started", 10)
        kwargs["progress"]("recommendation_execution_finished", 100)
        return sealed

    monkeypatch.setattr(module, "execute_recommendation", execute)
    service = MagicMock()
    progress = []

    result = request.execute(
        service,
        progress_callback=lambda message, pct: progress.append((message, pct)),
    )

    assert result is sealed
    assert captured["service"] is service
    assert captured["config"]["filters"]["price_change_min"] == "2.50"
    assert captured["kwargs"]["request_config_snapshot"] is request.config_snapshot
    assert captured["kwargs"]["max_stocks"] == 200
    assert captured["kwargs"]["top_n"] == 50
    assert progress == [("讀取股票數據...", 10), ("分析完成", 100)]
    assert "manual_qt_snapshot" not in captured["config"]
    assert '"manual_qt_snapshot":true' in request.config_snapshot.raw_config_json
    service.run_recommendation.assert_not_called()


def test_recommendation_request_preserves_cancelled_execution(monkeypatch) -> None:
    from ui_qt.views.recommendation import execution_coordinator as module

    request = RecommendationExecutionRequest(_config())
    cancelled = _execution(request.config_snapshot, ExecutionStatus.CANCELLED)
    captured = {}

    def execute(service, runtime_config, **kwargs):
        captured.update(kwargs)
        kwargs["progress"]("recommendation_cancelled", 100)
        return cancelled

    monkeypatch.setattr(module, "execute_recommendation", execute)
    cancel = lambda: True
    progress = []

    result = request.execute(
        object(),
        progress_callback=lambda message, pct: progress.append((message, pct)),
        cancellation_callback=cancel,
        detailed_progress=True,
    )

    assert result is cancelled
    assert captured["cancel"] is cancel
    assert progress == [("分析已取消", 100)]
