"""驗證個股研究摘要不把缺件或警訊呈現成正向結論。"""

from __future__ import annotations

from decimal import Decimal

from app_module.stock_research_report_dtos import (
    StockEvidenceEventDTO,
    StockPricePointDTO,
    StockResearchReportDTO,
)
from ui_qt.views.stock_research_report_view import _report_conclusion


def test_missing_latest_price_attention_uses_insufficient_data_wording() -> None:
    report = StockResearchReportDTO(
        stock_code="9999",
        attention_reasons=("缺少最新可用價格",),
    )

    conclusion = _report_conclusion(report)

    assert conclusion == "資料不足，需核對：缺少最新可用價格"
    assert "值得看" not in conclusion


def test_missing_latest_close_attention_uses_insufficient_data_wording() -> None:
    report = StockResearchReportDTO(
        stock_code="9999",
        attention_reasons=("最新價格 row 沒有收盤價",),
        price_points=(
            StockPricePointDTO(
                data_date="2026-10-02",
                close_price=None,
            ),
        ),
    )

    conclusion = _report_conclusion(report)

    assert conclusion == "資料不足，需核對：最新價格 row 沒有收盤價"
    assert "值得看" not in conclusion


def test_unknown_or_warning_attention_is_neutral_when_price_is_present() -> None:
    report = StockResearchReportDTO(
        stock_code="2330",
        attention_reasons=("來源狀態未知，需確認資料品質",),
        price_points=(
            StockPricePointDTO(
                data_date="2026-10-02",
                close_price=Decimal("2500"),
            ),
        ),
    )

    conclusion = _report_conclusion(report)

    assert conclusion == "需核對資料：來源狀態未知，需確認資料品質"
    assert "值得看" not in conclusion


def test_rule_reason_keeps_existing_positive_rule_wording() -> None:
    report = StockResearchReportDTO(
        stock_code="2330",
        rule_reasons=("已保存的規則理由",),
    )

    assert _report_conclusion(report) == "值得深入核對：已保存的規則理由"


def test_historical_portfolio_alert_does_not_replace_current_missing_data_copy() -> None:
    report = StockResearchReportDTO(
        stock_code="2330",
        attention_reasons=("缺少最新可用價格",),
        events=(
            StockEvidenceEventDTO(
                event_id="evt-historical-1",
                event_date="2026-09-30",
                decision_date="2026-09-30",
                event_type="portfolio_alert:warning",
                event_family="portfolio_alert",
                source_type="portfolio_alert",
                reasons=("當時保存的持倉警示",),
            ),
        ),
    )

    conclusion = _report_conclusion(report)

    assert conclusion == "資料不足，需核對：缺少最新可用價格"
    assert "歷史持倉警示" not in conclusion
    assert "值得看" not in conclusion
