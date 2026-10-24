"""研究母體固定條件三態分布的純呈現回歸。"""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app_module.daily_market_cohort_projection import DailyMarketCohortMethodCount
from ui_qt.views.daily_market_cohort_view import DailyMarketCohortView


class _SourceView(QWidget):
    snapshotAccepted = Signal(object)
    snapshotCleared = Signal()
    originalRankingAccepted = Signal(object)
    originalRankingCleared = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.service = SimpleNamespace()
        self.status_label = QLabel("來源錯誤")
        self.original_ranking_label = QLabel("原排名未提供")

    def reload_published_snapshot(self) -> None:
        pass


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _method_count(
    key: str,
    match_count: int,
    no_match_count: int,
    unknown_count: int,
    denominator: int,
) -> DailyMarketCohortMethodCount:
    return DailyMarketCohortMethodCount(
        key=key,
        method_id=f"daily_market.{key}",
        family="daily_market",
        version="1",
        parameters=(("direction", "above"),),
        match_count=match_count,
        no_match_count=no_match_count,
        unknown_count=unknown_count,
        denominator=denominator,
    )


def test_method_distribution_keeps_exact_three_state_counts_and_fixed_denominator(app):
    source = _SourceView()
    view = DailyMarketCohortView(source, lambda: None)
    view._render_method_counts((
        _method_count("close_above_ma20", 1, 1, 2, 4),
        _method_count("close_above_ma60", 1, 1, 2, 4),
    ))

    assert view.methods_table.rowCount() == 2
    assert view.methods_table.columnCount() == 5
    for row in range(2):
        assert [view.methods_table.item(row, column).text() for column in range(1, 4)] == [
            "1", "1", "2",
        ]
        distribution = view.methods_table.cellWidget(row, 4)
        assert distribution.counts == (1, 1, 2)
        assert distribution.denominator == 4
        assert distribution.track.renderable
        assert distribution.track.segment_endpoints(260) == (65, 130, 260)
        assert distribution.summary_text == "符合 1｜不符合 1｜未知 2｜母體 4"
        layout = distribution.layout()
        margins = layout.contentsMargins()
        assert distribution.content_height >= (
            distribution.track.minimumHeight()
            + distribution.counts_label.fontMetrics().lineSpacing()
            + layout.spacing()
            + margins.top()
            + margins.bottom()
        )
        assert view.methods_table.rowHeight(row) >= (
            distribution.content_height
            + max(2, view.methods_table.frameWidth() * 2)
        )
        assert "未知 2" in distribution.counts_label.accessibleDescription()
        assert "未知 2" in distribution.counts_label.toolTip()
        assert distribution.track.STATE_COLORS[2] != distribution.track.STATE_COLORS[1]

    # 刷新相同列時重建圖卡，不沿用前次人數或分母。
    view._render_method_counts((_method_count("close_above_ma20", 2, 0, 1, 3),))
    distribution = view.methods_table.cellWidget(0, 4)
    assert view.methods_table.rowCount() == 1
    assert distribution.counts == (2, 0, 1)
    assert distribution.denominator == 3
    assert distribution.track.segment_endpoints(270) == (180, 180, 270)
    assert distribution.summary_text == "符合 2｜不符合 0｜未知 1｜母體 3"

    view._render_method_counts((_method_count("close_above_ma20", 0, 0, 0, 0),))
    distribution = view.methods_table.cellWidget(0, 4)
    assert not distribution.track.renderable
    assert distribution.track.segment_endpoints(260) == ()
    assert distribution.track.accessibleDescription() == "分母或三態人數不可繪製；沒有比例條。"
    assert distribution.summary_text == "符合 0｜不符合 0｜未知 0｜母體 0"
    assert "%" not in distribution.counts_label.toolTip()

    view._render_method_counts(())
    assert view.methods_table.rowCount() == 0
    view._render_method_counts((_method_count("close_above_ma20", 1, 1, 2, 4),))
    view.clear_snapshot()
    assert view.methods_table.rowCount() == 0
    assert view.methods_table.cellWidget(0, 4) is None

    view.close()
    source.close()
