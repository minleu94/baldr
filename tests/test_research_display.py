"""保存時間顯示不猜未知時區，保留原值作身份與排序。"""

from ui_qt.research_display import research_saved_time


def test_saved_time_handles_day_rollover_and_unknown_timezone():
    assert research_saved_time("2026-10-21T20:10:59.123456Z") == "2026-10-22 04:10（台北）"
    assert research_saved_time("2026-10-21T20:10:59") == "2026-10-21T20:10:59（時區未提供）"
    assert research_saved_time("未知來源值") == "未知來源值"
    assert research_saved_time("") == "未知"
