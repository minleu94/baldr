"""完整個股研究 UI gallery 專用的合成 DTO；不讀取正式來源或執行服務。"""

from __future__ import annotations

import json
from decimal import Decimal

from app_module.stock_research_report_dtos import (
    StockFlowObservationDTO,
    StockFundamentalComparisonDTO,
    StockFundamentalObservationDTO,
    StockMetricDTO,
    StockPricePointDTO,
    StockPositionSnapshotDTO,
    StockReportSectionDTO,
    StockReportSourceDTO,
    StockResearchReportDTO,
)


_AS_OF = "2026-10-22"
_MARKET_DATE = "2026-10-21"
_AVAILABLE_AT = "2026-10-22T08:30:00+08:00"
_QA_LIMITATION = "QA 合成展示資料，非正式市場資料；不得用於研究判斷、回測或金融資格。"


def _metric(
    key: str,
    label: str,
    value: str,
    *,
    unit: str,
    source_id: str,
    data_as_of: str = _MARKET_DATE,
) -> StockMetricDTO:
    return StockMetricDTO(
        key=key,
        label=label,
        value=Decimal(value),
        unit=unit,
        data_as_of=data_as_of,
        available_at=_AVAILABLE_AT,
        source_id=source_id,
        quality="observed",
    )


def full_research_report() -> StockResearchReportDTO:
    """建立涵蓋圖表、缺月、四面向與完整原表的純 DTO 示意報告。"""
    price_source = "qa.fixture.price"
    price_values = (
        ("2026-10-12", "1000", "1008", "995", "1002", "2", 1_000_000),
        ("2026-10-14", "1002", "1018", "999", "1014", "12", 1_100_000),
        ("2026-10-16", "1014", "1018", "1005", "1010", "-4", 900_000),
        ("2026-10-19", "1010", "1030", "1008", "1027", "17", 1_500_000),
        ("2026-10-21", "1027", "1031", "1018", "1027", "0", 1_300_000),
    )
    price_points = tuple(
        StockPricePointDTO(
            data_date=data_date,
            open_price=Decimal(open_price),
            high_price=Decimal(high_price),
            low_price=Decimal(low_price),
            close_price=Decimal(close_price),
            volume=volume,
            change=Decimal(change),
            available_at=_AVAILABLE_AT,
            source_id=price_source,
            source_snapshot_hash="6" * 64,
            quality="observed",
        )
        for data_date, open_price, high_price, low_price, close_price, change, volume in price_values
    )

    revenue_source = "qa.fixture.monthly_revenue"
    fundamentals = [
        StockFundamentalObservationDTO(
            kind="monthly_revenue",
            label="月營收（QA示意）",
            metric_name="monthly_revenue",
            market="TWSE",
            period=period,
            as_of_date=as_of_date,
            announced_date=as_of_date,
            available_at=_AVAILABLE_AT,
            observed_at=_AVAILABLE_AT,
            value=Decimal(value),
            value_text="QA 原值示意；缺少月份刻意保留，不插補。",
            unit="百萬元",
            source_id=revenue_source,
            source_version="qa-monthly-v1",
            source_snapshot_hash="1" * 64,
            quality="observed",
            period_basis="calendar_month",
            basis_verified=True,
            aggregate_feature_eligible=False,
            formal_pit_eligible=False,
        )
        for period, as_of_date, value in (
            ("2026-05", "2026-06-10", "1200"),
            ("2026-07", "2026-08-10", "1325"),
            ("2026-09", "2026-10-12", "1410"),
        )
    ]
    comparison_source = "qa.fixture.financial_comparison"
    current_fundamental = StockFundamentalObservationDTO(
        kind="statement_item",
        label="營收（比較當期 QA示意）",
        metric_name="revenue_comparison",
        market="TWSE",
        period="2026Q2",
        as_of_date="2026-08-10",
        announced_date="2026-08-10",
        available_at=_AVAILABLE_AT,
        observed_at=_AVAILABLE_AT,
        value=Decimal("125"),
        value_text="與比較投影當期完全相同的 QA 原值。",
        unit="TWD",
        source_id=comparison_source,
        source_version="qa-financial-v1",
        source_snapshot_hash="2" * 64,
        quality="observed",
        period_basis="quarter",
        basis_verified=True,
        aggregate_feature_eligible=False,
        formal_pit_eligible=False,
    )
    fundamentals.append(current_fundamental)
    comparison = StockFundamentalComparisonDTO(
        stock_code="2330",
        metric_name="revenue_comparison",
        label="營收比較（QA示意）",
        current_period="2026Q2",
        prior_period="2026Q1",
        current_value=Decimal("125"),
        prior_value=Decimal("100"),
        value_unit="TWD",
        change_value=Decimal("25"),
        change_unit="percent",
        current_source_id=comparison_source,
        current_source_version="qa-financial-v1",
        source_id=comparison_source,
        source_version="qa-financial-v1",
        source_snapshot_hash="3" * 64,
        available_at=_AVAILABLE_AT,
        note="QA 原比較投影示意；不代表正式同比或金融資格。",
    )

    institutional_source = "qa.fixture.institutional"
    institutional_specs = (
        ("foreign_investor_net", "外資買賣超", "1200"),
        ("foreign_investor_buy", "外資買進", "3000"),
        ("foreign_investor_sell", "外資賣出", "1800"),
        ("investment_trust_net", "投信買賣超", "-450"),
        ("investment_trust_buy", "投信買進", "750"),
        ("investment_trust_sell", "投信賣出", "1200"),
        ("dealer_net", "自營商買賣超", "0"),
        ("dealer_buy", "自營商買進", "500"),
        ("dealer_sell", "自營商賣出", "500"),
    )
    institutional = tuple(
        _metric(key, label, value, unit="股", source_id=institutional_source)
        for key, label, value in institutional_specs
    )

    credit_source = "qa.fixture.credit"
    credit_specs = (
        ("margin_purchase", "融資買進", "120", "張"),
        ("margin_repayment", "融資償還", "80", "張"),
        ("margin_balance", "融資餘額", "15000", "張"),
        ("short_sale", "融券賣出", "-20", "張"),
        ("short_cover", "融券買進", "20", "張"),
        ("short_balance", "融券餘額", "0", "張"),
    )
    credit = tuple(
        _metric(key, label, value, unit=unit, source_id=credit_source)
        for key, label, value, unit in credit_specs
    )

    tdcc_source = "qa.fixture.tdcc"
    shareholding_summary = (
        _metric("large_holder_ratio_bp", "大額持有人比例（原基點）", "4200", unit="基點", source_id=tdcc_source),
        _metric("retail_holder_ratio_bp", "小額持有人比例（原基點）", "1800", unit="基點", source_id=tdcc_source),
        _metric("dispersion_index_bp", "分散指標（原基點）", "6000", unit="基點", source_id=tdcc_source),
    )
    tier_rows = [
        {
            "tier": tier,
            "holder_count": tier * 10,
            "shares": tier * 100_000,
            "holding_ratio_bp": 0 if tier == 1 else 500,
        }
        for tier in range(1, 16)
    ]
    tier_rows.extend(
        (
            {"tier": 16, "holder_count": None, "shares": 0, "holding_ratio_bp": 3000},
            {"tier": 17, "holder_count": None, "shares": 12_000_000, "holding_ratio_bp": 10000},
        )
    )
    shareholding_tiers = StockMetricDTO(
        key="shareholding_tiers",
        label="TDCC 持股級距（QA示意）",
        value_text=json.dumps(tier_rows, ensure_ascii=False, separators=(",", ":")),
        data_as_of=_MARKET_DATE,
        available_at=_AVAILABLE_AT,
        source_id=tdcc_source,
        quality="observed",
    )

    flow_source = "qa.fixture.broker_flows"
    flows = tuple(
        StockFlowObservationDTO(
            data_date=_MARKET_DATE,
            branch_name=f"QA分點示意 {index + 1:02d}",
            buy_shares=(20_000 if index % 3 == 0 else 10_000),
            sell_shares=(10_000 if index % 3 == 0 else 20_000) if index % 3 == 1 else 10_000,
            net_shares=(10_000 if index % 3 == 0 else -10_000) if index % 3 != 2 else 0,
            buy_amount_thousand=Decimal("2500"),
            sell_amount_thousand=Decimal("2500"),
            net_amount_thousand=Decimal("0"),
            trade_type="QA合成原始順序",
            available_at=_AVAILABLE_AT,
            source_id=flow_source,
            quality="observed",
        )
        for index in range(15)
    )

    position_source = "qa.fixture.position"
    position = StockPositionSnapshotDTO(
        is_holding=True,
        position_id="qa-position-2330",
        portfolio_id="qa-portfolio",
        position_as_of=_MARKET_DATE,
        quote_data_date=_MARKET_DATE,
        quote_available_at=_AVAILABLE_AT,
        quantity=Decimal("1000"),
        average_cost=Decimal("1200"),
        invested_amount=Decimal("1200000"),
        current_price=Decimal("1100"),
        unrealized_pnl=Decimal("-100000"),
        unrealized_pnl_pct=Decimal("-8.3333333333"),
        exposure_bp=1000,
        source_type="qa_fixture",
        source_id=position_source,
        source_snapshot_hash="4" * 64,
        quote_source_snapshot_hash="5" * 64,
        health_status="warning",
        health_label="QA示意：持倉下跌",
        health_reasons=("合成 QA 負損益展示值；非真實帳戶或計算結果。",),
        exit_status="unavailable",
        exit_reasons=("QA fixture 不提供交易處置。",),
        exit_source_id=position_source,
        exit_available_at=_AVAILABLE_AT,
        exit_research_only=True,
        exit_auto_action_allowed=False,
        limitations=(_QA_LIMITATION,),
    )

    source_specs = (
        (price_source, "[QA示意] 價量原值", len(price_points), _MARKET_DATE),
        (revenue_source, "[QA示意] 月營收原值（5／7／9月）", 3, "2026-09"),
        (comparison_source, "[QA示意] 財報比較原值", 1, "2026-08-10"),
        (institutional_source, "[QA示意] 法人原值", len(institutional), _MARKET_DATE),
        (credit_source, "[QA示意] 信用原值", len(credit), _MARKET_DATE),
        (tdcc_source, "[QA示意] TDCC 原值", len(shareholding_summary) + 1, _MARKET_DATE),
        (flow_source, "[QA示意] 分點原值（原順序）", len(flows), _MARKET_DATE),
        (position_source, "[QA示意] 持倉與負損益原值", 1, _MARKET_DATE),
    )
    sources = tuple(
        StockReportSourceDTO(
            source_id=source_id,
            source_label=label,
            status="available",
            quality="observed",
            data_as_of=data_as_of,
            available_at=_AVAILABLE_AT,
            freshness="unknown",
            version="qa-fixture-v1",
            row_count=row_count,
            limitations=(_QA_LIMITATION,),
            candidate_only=True,
            current_observed_only=False,
            historical_pit_eligible=False,
        )
        for source_id, label, row_count, data_as_of in source_specs
    )
    sections = tuple(
        StockReportSectionDTO(
            section_id=section_id,
            label=f"[QA示意] {label}",
            status="available",
            summary=f"QA 合成示意；非正式資料。{summary}",
            data_as_of=data_as_of,
            available_at=_AVAILABLE_AT,
            freshness="unknown",
            source_ids=source_ids,
            limitations=(_QA_LIMITATION,),
        )
        for section_id, label, source_ids, data_as_of, summary in (
            ("price", "價格與技術", (price_source,), _MARKET_DATE, "含多日 OHLC、成交量及正負零漲跌。"),
            ("fundamental", "營收與財報", (revenue_source, comparison_source), "2026-09", "月營收刻意只含 5、7、9 月；另有來源綁定的財報比較。"),
            ("flows", "法人、信用、集保與分點", (institutional_source, credit_source, tdcc_source, flow_source), _MARKET_DATE, "信用、TDCC、分點原列皆為具名 QA 來源。"),
            ("position", "持倉與風險", (position_source,), _MARKET_DATE, "持有狀態與負損益只為合成 UI 展示。"),
        )
    )

    return StockResearchReportDTO(
        stock_code="2330",
        stock_name="QA完整研究示意（非正式資料）",
        market="台股（QA示意）",
        industry="QA示意產業",
        as_of=_AS_OF,
        generated_at=_AVAILABLE_AT,
        sources=sources,
        sections=sections,
        available_modules=("price", "fundamental", "flows", "position"),
        attention_reasons=("QA示意欄位展示，不代表個股訊號。",),
        key_risks=("所有數值均為合成 UI fixture，不可作為投資或金融依據。",),
        limitations=(_QA_LIMITATION,),
        price_points=price_points,
        fundamentals=tuple(fundamentals),
        flows=flows,
        institutional=institutional,
        credit=credit,
        shareholding=(*shareholding_summary, shareholding_tiers),
        position=position,
        fundamental_comparisons=(comparison,),
        read_only=True,
    )
