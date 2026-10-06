"""不同狀態維度不可互相授予資格或誤判故障。"""

import pytest

from ui_qt.status_vocabulary import status_detail, status_label


@pytest.mark.parametrize("raw,expected", [
    ("missing", "資料缺件"), ("degraded", "品質降級"),
    ("loading", "載入中"), ("waiting_for_time", "尚未到期"),
    ("market_closed", "休市跳過"), ("failed", "執行錯誤"),
    ("skipped_non_trading_day", "休市跳過"),
    ("research_only", "正式資格未具備（研究限定）"),
    ("pending", "待確認"), ("vendor_new_code", "vendor_new_code"),
])
def test_explicit_status_meanings(raw, expected):
    assert status_label(raw) == expected
    assert raw in status_detail(raw)


def test_completion_does_not_grant_data_or_formal_qualification():
    assert status_label("completed", dimension="load") == "載入完成"
    assert status_label("completed", dimension="research") == "研究完成"
    assert status_label("completed", dimension="qualification") == "completed"
    assert status_label("completed", dimension="data") == "completed"


def test_waiting_and_closed_events_do_not_downgrade_the_whole_feed():
    from types import SimpleNamespace
    from ui_qt.views.workbench_presenter import evidence_feed_state_text
    dashboard = SimpleNamespace(background_evidence_feed=[
        SimpleNamespace(status=raw, degraded_reason="await real trading date", status_classification="waiting_for_time")
        for raw in ("waiting_for_time", "market_closed")
    ])
    text = evidence_feed_state_text(dashboard)
    assert "尚未到期" in text and "休市跳過" in text
    assert "降級" not in text


def test_actual_error_is_visible_in_mixed_feed():
    from types import SimpleNamespace
    from ui_qt.views.workbench_presenter import evidence_feed_state_text
    dashboard = SimpleNamespace(background_evidence_feed=[
        SimpleNamespace(status=raw, degraded_reason="", status_classification="machine_degraded")
        for raw in ("observed", "failed")
    ])
    assert "執行錯誤" in evidence_feed_state_text(dashboard)


def test_waiting_status_does_not_hide_concrete_source_failure():
    from types import SimpleNamespace
    from ui_qt.views.workbench_presenter import evidence_feed_state_text
    dashboard = SimpleNamespace(background_evidence_feed=[
        SimpleNamespace(status="waiting_for_time", degraded_reason="source_missing", status_classification="human_review")
    ])
    assert "降級" in evidence_feed_state_text(dashboard)


def test_console_keeps_unknown_code_exactly_including_reserved_substrings():
    from ui_qt.views.research_console_view import _status_display, _status_detail_display
    raw = "Vendor_unknown_missing_v2"
    assert _status_display(raw) == raw
    assert raw in _status_detail_display(raw)
