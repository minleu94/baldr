"""日曆阻擋的失敗畫面提供原因，保留原結果與完整技術錯誤。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ui_qt.views import recommendation_view as module


@pytest.mark.parametrize("reason", [
    "RecommendationMarketSessionBlocked: natural_market_official_calendar_unverified:"
    "official_calendar_blocked:ValueError:official_calendar_unknown:2026-09-16",
    "RecommendationMarketSessionBlocked: natural_market_official_calendar_unavailable",
    "ValueError: missing market price",
])
def test_error_callback_describes_calendar_only_when_it_is_the_blocker(monkeypatch, reason):
    dialog = MagicMock()
    monkeypatch.setattr(module, "QMessageBox", MagicMock(return_value=dialog))
    previous_result = object()
    view = SimpleNamespace(
        _signal_generation_is_current=lambda generation: generation == 7,
        _complete_personal_policy_one_shot=MagicMock(),
        _finish_execution_status=MagicMock(),
        execute_btn=MagicMock(), cancel_execution_btn=MagicMock(),
        progress_bar=MagicMock(), progress_label=MagicMock(),
        result_status_label=MagicMock(), _current_items=lambda: (previous_result,),
        current_execution=previous_result,
    )
    module.RecommendationView._on_recommendation_error(view, reason, generation=7)
    assert view.current_execution is previous_result
    dialog.setDetailedText.assert_called_once_with(reason)
    dialog.exec.assert_called_once()
    status = view.result_status_label.setText.call_args.args[0]
    body = dialog.setText.call_args.args[0]
    guidance = dialog.setInformativeText.call_args.args[0]
    assert "沒有套用部分結果" in status and "沒有套用部分結果" in body
    if "natural_market_official_calendar" in reason:
        assert "官方交易日曆無法核驗" in status and "官方交易日曆無法核驗" in body
        assert "三個預設策略共用交易日曆" in guidance
        assert "放寬選股條件不會解除" in guidance
    else:
        assert "官方交易日曆" not in status + body + guidance
        assert reason in body


def test_stale_error_does_not_open_dialog_or_replace_current_result(monkeypatch):
    dialog_factory = MagicMock()
    monkeypatch.setattr(module, "QMessageBox", dialog_factory)
    view = SimpleNamespace(_signal_generation_is_current=lambda generation: False)
    module.RecommendationView._on_recommendation_error(view,
        "natural_market_official_calendar_unverified", generation=6)
    dialog_factory.assert_not_called()
