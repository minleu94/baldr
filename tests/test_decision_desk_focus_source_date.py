from __future__ import annotations

import os
import sys
from dataclasses import replace
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtWidgets import QApplication

from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    DecisionDeskStockCard,
    DecisionDeskStockFocus,
)
from app_module.decision_presentation import DecisionPresentationService
from app_module.relative_strength_liquidity_service import RelativeStrengthLiquidityService
from ui_qt.views.decision_desk_view import DecisionDeskView


class _StaticPriceProvider:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetch(self, as_of_date: date) -> pd.DataFrame:
        del as_of_date
        return pd.DataFrame(self.rows)


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _effective_source_summary():
    rows = [
        {
            "日期": (date(2026, 9, 12) + timedelta(days=offset)).isoformat(),
            "證券代號": "2330",
            "收盤價": str(100 + offset),
            "成交股數": 1_000_000,
        }
        for offset in range(21)
    ]
    summary = RelativeStrengthLiquidityService(_StaticPriceProvider(rows)).build_snapshot(
        date(2026, 10, 3)
    )
    assert summary.as_of_date == date(2026, 10, 2)
    assert summary.meta is not None
    assert summary.meta["source"] == "relative_strength_liquidity_service"
    return summary


def _card(source: str) -> DecisionDeskStockCard:
    return DecisionDeskStockCard(
        stock_code="2330",
        stock_name="台積電",
        role="priority",
        reason="研究焦點",
        source=source,
        quality=DecisionDeskQuality.DEGRADED,
    )


def _view() -> DecisionDeskView:
    _app()
    return DecisionDeskView(
        object(),
        as_of_date=date(2026, 10, 3),
        auto_refresh=False,
        async_refresh=False,
    )


def test_focus_click_keeps_analysis_date_separate_from_effective_source_date() -> None:
    view = _view()
    view._last_snapshot = type(
        "Snapshot",
        (),
        {
            "as_of_date": date(2026, 10, 3),
            "relative_strength_liquidity": _effective_source_summary(),
        },
    )()
    view._stock_focus_research_card = _card("relative_strength")
    captured = []
    view.stockResearchRequested.connect(captured.append)

    view._open_stock_focus_research()

    assert len(captured) == 1
    assert captured[0].decision_date == "2026-10-03"
    assert captured[0].data_date == "2026-10-02"
    view.close()


def test_market_focus_presentation_uses_same_source_date_as_click_through() -> None:
    view = _view()
    card = _card("relative_strength")
    snapshot = type(
        "Snapshot",
        (),
        {
            "as_of_date": date(2026, 10, 3),
            "relative_strength_liquidity": _effective_source_summary(),
            "stock_focus": DecisionDeskStockFocus(priority_stocks=(card,)),
        },
    )()
    view.presentation_service = DecisionPresentationService()

    view._render_presentation_contract(snapshot)

    text = view.presentation_contract_label.text()
    assert "資料日：2026-10-02" in text
    assert "資料日：2026-10-03" not in text
    view.close()


def test_market_focus_presentation_does_not_use_analysis_date_for_other_sources() -> None:
    view = _view()
    card = _card("portfolio_watchlist")
    snapshot = type(
        "Snapshot",
        (),
        {
            "as_of_date": date(2026, 10, 3),
            "relative_strength_liquidity": _effective_source_summary(),
            "stock_focus": DecisionDeskStockFocus(priority_stocks=(card,)),
        },
    )()
    view.presentation_service = DecisionPresentationService()

    view._render_presentation_contract(snapshot)

    text = view.presentation_contract_label.text()
    assert "資料日：2026-10-03" not in text
    assert "資料日：2026-10-02" not in text
    view.close()


def test_unproven_or_unrelated_focus_source_keeps_data_date_unknown() -> None:
    view = _view()
    source_summary = _effective_source_summary()
    captured = []
    view.stockResearchRequested.connect(captured.append)

    for source, summary in (
        ("portfolio_watchlist", source_summary),
        (
            "relative_strength",
            type(source_summary)(
                as_of_date=source_summary.as_of_date,
                quality=source_summary.quality,
                warnings=source_summary.warnings,
                top_strength_codes=source_summary.top_strength_codes,
            ),
        ),
    ):
        view._last_snapshot = type(
            "Snapshot",
            (),
            {
                "as_of_date": date(2026, 10, 3),
                "relative_strength_liquidity": summary,
            },
        )()
        view._stock_focus_research_card = _card(source)
        view._open_stock_focus_research()

    assert [item.decision_date for item in captured] == ["2026-10-03", "2026-10-03"]
    assert [item.data_date for item in captured] == ["", ""]
    view.close()


def test_weak_relative_strength_card_uses_same_source_and_rejects_future_or_mismatched_rows() -> None:
    view = _view()
    source_summary = _effective_source_summary()
    captured = []
    view.stockResearchRequested.connect(captured.append)

    view._last_snapshot = type(
        "Snapshot",
        (),
        {
            "as_of_date": date(2026, 10, 3),
            "relative_strength_liquidity": replace(
                source_summary,
                weak_strength_codes=("2330",),
            ),
        },
    )()
    view._stock_focus_research_card = _card("relative_strength_liquidity")
    view._open_stock_focus_research()

    view._last_snapshot = type(
        "Snapshot",
        (),
        {
            "as_of_date": date(2026, 10, 3),
            "relative_strength_liquidity": replace(
                source_summary,
                as_of_date=date(2026, 10, 4),
            ),
        },
    )()
    view._stock_focus_research_card = _card("relative_strength")
    view._open_stock_focus_research()

    view._last_snapshot = type(
        "Snapshot",
        (),
        {
            "as_of_date": date(2026, 10, 3),
            "relative_strength_liquidity": source_summary,
        },
    )()
    view._stock_focus_research_card = DecisionDeskStockCard(
        stock_code="9999",
        stock_name="未匹配股票",
        role="priority",
        reason="不應借用其他股票來源日期",
        source="relative_strength",
    )
    view._open_stock_focus_research()

    assert [item.data_date for item in captured] == ["2026-10-02", "", ""]
    view.close()
