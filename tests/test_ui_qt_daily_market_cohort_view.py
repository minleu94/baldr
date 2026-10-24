"""研究母體固定條件三態分布的純呈現回歸。"""

import os
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app_module.daily_market_cohort_projection import (
    DailyMarketCohortMember,
    DailyMarketCohortMethodCount,
    DailyMarketCohortProjection,
)
from app_module.daily_market_research_screener import (
    DailyMarketResearchConditionResult,
    ResearchConditionRelation,
    ResearchConditionState,
)
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


def _condition(
    key: str,
    state: ResearchConditionState,
    relation: ResearchConditionRelation,
    reason: str,
    unknown_reason: str | None = None,
) -> DailyMarketResearchConditionResult:
    return DailyMarketResearchConditionResult(
        key=key,
        state=state,
        relation=relation,
        reason=reason,
        method_id=f"daily_market.{key}",
        family="daily_market",
        version="1",
        decision_date="2026-10-23",
        eligibility="unknown" if state == "unknown" else "eligible",
        unknown_reason=unknown_reason,
    )


def _member(
    stock_code: str,
    data_date: str | None,
    conditions: tuple[DailyMarketResearchConditionResult, ...],
) -> DailyMarketCohortMember:
    return DailyMarketCohortMember(
        stock_code=stock_code,
        data_date=data_date,
        close=Decimal("101") if data_date else None,
        ma20=Decimal("100") if data_date else None,
        ma60=Decimal("102") if data_date else None,
        conditions=conditions,
        source_refs=(("close", "saved_close"),) if data_date else (),
    )


def _projection(members: tuple[DailyMarketCohortMember, ...]) -> DailyMarketCohortProjection:
    stock_codes = tuple(member.stock_code for member in members)
    return DailyMarketCohortProjection(
        cohort_id="cohort-ui-test",
        decision_date="2026-10-23",
        manifest_schema_version="2",
        source_snapshot_id="source-id",
        source_snapshot_hash="source-hash",
        method_contracts_sha256="method-contract-hash",
        completeness="complete",
        declared_stock_codes=stock_codes,
        published_stock_codes=stock_codes,
        missing_stock_codes=(),
        published_count=len(stock_codes),
        method_counts=(),
        members=members,
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


def test_selected_member_details_show_typed_conditions_and_clear_stale_selection(app):
    source = _SourceView()
    view = DailyMarketCohortView(source, lambda: None)
    members = (
        _member(
            "2330",
            "2026-10-23",
            (
                _condition(
                    "close_above_ma20", "match", "above", "收盤價高於保存 MA20。",
                ),
                _condition(
                    "close_above_ma60", "no_match", "below", "收盤價低於保存 MA60。",
                ),
            ),
        ),
        _member(
            "2454",
            None,
            (
                _condition(
                    "close_above_ma20", "unknown", "unknown", "缺少收盤價。",
                    "snapshot_missing|close_not_observed",
                ),
                _condition(
                    "close_above_ma60", "match", "above", "原來源記錄為符合。",
                ),
            ),
        ),
    )
    view.projection = _projection(members)
    view._render_members_table()
    assert "選取一列" in view.selected_member_detail_label.text()

    view.members_table.selectRow(0)
    first_detail = view.selected_member_detail_label.text()
    assert "2330｜資料日 2026-10-23" in first_detail
    assert "固定條件觀察，非投資建議" in first_detail
    assert "收盤價高於 MA20：符合（match）｜關係：高於（above）" in first_detail
    assert "原因：收盤價高於保存 MA20。" in first_detail
    assert "收盤價高於 MA60：不符合（no_match）｜關係：低於（below）" in first_detail
    assert "原因：收盤價低於保存 MA60。" in first_detail

    view.members_table.selectRow(1)
    second_detail = view.selected_member_detail_label.text()
    assert "2454｜資料日 未知" in second_detail
    assert "收盤價高於 MA20：未知（unknown）｜關係：未知（unknown）" in second_detail
    assert "原因：缺少收盤價。" in second_detail
    assert "未知原因：snapshot_missing|close_not_observed" in second_detail
    assert "2330" not in second_detail

    view.members_table.clearSelection()
    assert "選取一列" in view.selected_member_detail_label.text()
    assert "2454" not in view.selected_member_detail_label.text()

    view.members_table.selectRow(0)
    source.snapshotCleared.emit()
    assert view.projection is None
    assert view.members_table.rowCount() == 0
    assert "選取一列" in view.selected_member_detail_label.text()
    assert "2330" not in view.selected_member_detail_label.text()

    view.close()
    source.close()
