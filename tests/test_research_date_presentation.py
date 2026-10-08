"""資料日不可由判讀日、主機時區或非正規來源補成已知。"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from ui_qt.research_date_presentation import source_data_date_text
from ui_qt.views.decision_desk_view import _market_regime_source_data_date


@pytest.mark.parametrize("value", [None, "", "2026-6-13", "20260613", 20260613,
    "2026-02-30", "2026-06-13T00:00:00+08:00", "<b>2026-06-13</b>",
    datetime(2026, 6, 13, tzinfo=timezone.utc)])
def test_invalid_or_timestamp_source_date_stays_unknown(value: object) -> None:
    assert source_data_date_text(value) == "未知"


def test_source_date_preserves_weekend_and_separate_cutoff() -> None:
    assert source_data_date_text("2026-06-13", cutoff=date(2026, 6, 15)) == "2026-06-13"
    assert source_data_date_text(date(2026, 6, 13)) == "2026-06-13"
    assert source_data_date_text("2026-06-16", cutoff=date(2026, 6, 15)) == "未知"
    assert source_data_date_text("2026-06-13", cutoff=datetime(2026, 6, 15)) == "未知"


def test_decision_desk_invalid_cutoff_does_not_raise_or_relabel_source() -> None:
    section = SimpleNamespace(meta={"source_data_date": "2026-06-13"},
        as_of_date=datetime(2026, 6, 15))
    assert _market_regime_source_data_date(section) == "未知"
    section.as_of_date = date(2026, 6, 15)
    assert _market_regime_source_data_date(section) == "2026-06-13"
