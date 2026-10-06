import os
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.decision_desk_dtos import DecisionDeskQuality
from ui_qt.views.decision_desk_view import DecisionDeskView
from ui_qt.views.portfolio_view import (
    PortfolioView,
    _paper_status_text,
)


@pytest.fixture(scope="module")
def qapp():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


class _TextControl:
    def __init__(self) -> None:
        self.value = ""

    def setText(self, value: str) -> None:  # noqa: N802 - Qt-shaped fixture
        self.value = value

    def setStyleSheet(self, value: str) -> None:  # noqa: N802 - Qt-shaped fixture
        self.style = value


def _portfolio_summary(model) -> str:
    formatter = SimpleNamespace(
        _position_health_blocked_row_count=PortfolioView._position_health_blocked_row_count,
        _format_portfolio_timestamp=PortfolioView._format_portfolio_timestamp,
    )
    return PortfolioView._format_portfolio_position_health_summary(formatter, model)


def test_market_status_keeps_usable_research_separate_from_missing_sections(qapp):
    decision_date = date(2026, 10, 5)
    view = DecisionDeskView(
        as_of_date=decision_date,
        auto_refresh=False,
        async_refresh=False,
    )

    view._set_section_quality(
        view.market_regime_status,
        DecisionDeskQuality.OBSERVED,
        decision_date,
    )
    view._set_section_quality(
        view.market_breadth_status,
        DecisionDeskQuality.MISSING,
        decision_date,
    )

    usable_badge = view._status_badges[view.market_regime_status]
    missing_badge = view._status_badges[view.market_breadth_status]
    assert usable_badge.text() == "可供研究判讀"
    assert missing_badge.text() == "資料缺件"
    assert "2026-10-05" in usable_badge.toolTip()
    assert "observed" in usable_badge.toolTip()
    assert "missing" in missing_badge.toolTip()
    view.close()


def test_position_health_missing_data_does_not_relabel_stock_risk():
    position = SimpleNamespace(source_status="missing", review_required=True)
    model = SimpleNamespace(
        status="blocked",
        source_status="missing",
        quality="missing",
        positions=(position,),
        blockers=("condition_result_missing",),
        decision_date="2026-10-05",
        available_at="2026-10-05T09:00:00",
    )
    summary = _portfolio_summary(model)

    assert "資料缺件" in summary
    assert "2026-10-05" in summary

    health = SimpleNamespace(
        action_suitability="EXIT_CANDIDATE",
        source_status="missing",
        position_id="paper:2330",
        cohort_key="paper-main",
        condition_status="critical",
        thesis_status="missing",
        metrics_status="blocked",
        decision_date="2026-10-05",
        available_at="2026-10-05T09:00:00",
        quality="missing",
        entry_lineage_status="unverified",
        review_required=True,
        why="已觸發持倉條件",
        why_not=("condition_result_missing",),
    )
    lifecycle_view = SimpleNamespace(
        lbl_lifecycle_status=_TextControl(),
        lbl_lifecycle_source=_TextControl(),
        lbl_lifecycle_execution=_TextControl(),
        lbl_lifecycle_signal=_TextControl(),
        lbl_lifecycle_market=_TextControl(),
        lbl_lifecycle_data_quality=_TextControl(),
        lbl_lifecycle_tokens=_TextControl(),
    )
    PortfolioView._render_position_health_lifecycle(lifecycle_view, health)

    assert lifecycle_view.lbl_lifecycle_status.value == "退出候選（EXIT_CANDIDATE）"
    assert "source=missing" in lifecycle_view.lbl_lifecycle_source.value


def test_status_view_fallback_preserves_unknown_codes_and_known_paper_event():
    assert DecisionDeskView._quality_label("provider_quality_v9") == "provider_quality_v9"
    assert DecisionDeskView._visibility_quality_label("provider_quality_v9") == "provider_quality_v9"
    assert _paper_status_text("skipped_non_trading_day") == "休市跳過（skipped_non_trading_day）"
    assert _paper_status_text("skipped") == "skipped（skipped）"

    model = SimpleNamespace(
        status="future_health_state",
        source_status="future_source_state",
        quality="future_quality_state",
        positions=(SimpleNamespace(source_status="future_source_state", review_required=False),),
        blockers=(),
        decision_date="2026-10-05",
        available_at=None,
    )
    summary = _portfolio_summary(model)
    assert "future_health_state" in summary
    assert "future_source_state" in summary
    assert "future_quality_state" in summary
