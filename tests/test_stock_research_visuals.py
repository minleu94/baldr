"""原值視覺投影不可混來源、單位、日期或把缺值當零。"""

from dataclasses import replace
from decimal import Decimal

from app_module.stock_research_report_dtos import (
    StockFlowObservationDTO, StockFundamentalObservationDTO, StockMetricDTO,
    StockResearchReportDTO, StockFundamentalComparisonDTO,
)
from ui_qt.stock_research_visuals import fundamental_visuals, metric_visuals, flow_visuals
from ui_qt.stock_research_visuals import shareholding_tier_visuals
import json


def test_fundamental_groups_keep_original_values_missing_periods_and_source_boundaries():
    original = StockFundamentalObservationDTO(
        kind="monthly_revenue", label="月營收", metric_name="revenue",
        source_id="official", source_version="v1", unit="千元",
        period="2026-01", value=Decimal("-10.25"),
        period_basis="single_month", basis_verified=True,
    )
    rows = (original, replace(original, period="2026-03", value=None),
            replace(original, source_version="v2", value=Decimal(0)),
            replace(original, unit="unknown"), replace(original, basis_verified=False))
    report = StockResearchReportDTO(stock_code="2330", fundamentals=rows)
    groups = fundamental_visuals(report)
    assert len(groups) == 2
    groups = tuple(sorted(groups, key=lambda group: "單一期間" in group.note))
    assert [point.label for point in groups[0].points] == ["2026-01", "2026-03"]
    assert [point.value for point in groups[0].points] == [Decimal("-10.25"), None]
    assert groups[1].points[0].value == 0
    assert "單一期間" in groups[1].note
    assert report.fundamentals == rows


def test_ambiguous_duplicate_period_does_not_pick_a_revision():
    item = StockFundamentalObservationDTO(
        kind="valuation", label="估值", metric_name="pe", source_id="s", unit="倍",
        period="2026-01", value=Decimal(10), period_basis="point", basis_verified=True,
    )
    report = StockResearchReportDTO(stock_code="2330", fundamentals=(item, replace(item, value=Decimal(20))))
    assert fundamental_visuals(report) == ()


def test_ownership_separates_days_units_sources_and_keeps_missing_zero():
    item = StockMetricDTO(key="foreign_investor_net", label="淨買賣", value=Decimal(0),
                          unit="股", data_as_of="2026-10-21", source_id="official")
    groups = metric_visuals("法人", (item, replace(item, key="dealer_net", value=None),
        replace(item, data_as_of="2026-10-20"), replace(item, source_id="other"),
        replace(item, unit="張"), replace(item, unit="unknown")))
    assert len(groups) == 4
    assert groups[0].points[0].value == Decimal(0)
    assert groups[0].points[1].value is None
    assert all("單日" in group.note for group in groups)


def test_branch_preview_retains_original_order_and_denominator_without_summing():
    rows = tuple(StockFlowObservationDTO("2026-10-21", f"分點{i}", net_shares=i - 6, source_id="s")
                 for i in range(15))
    groups = flow_visuals(rows)
    assert len(groups) == 1
    assert len(groups[0].points) == 12
    assert groups[0].points[0].value == -6
    assert "12／15" in groups[0].note
    assert rows[0].net_shares == -6


def test_credit_turnover_and_balance_never_share_one_axis():
    items = tuple(StockMetricDTO(key=key, label=key, value=Decimal(1), unit="交易單位",
                     data_as_of="2026-10-21", source_id="s")
                  for key in ("margin_purchase", "margin_balance", "short_sale"))
    assert len(metric_visuals("信用", items)) == 3


def test_shareholding_tiers_exclude_total_adjustment_and_preserve_zero_missing():
    metric = StockMetricDTO("shareholding_tiers", "持股級距", source_id="tdcc",
        data_as_of="2026-10-16", value_text=json.dumps([
            {"tier": 1, "holding_ratio_bp": 0}, {"tier": 2},
            {"tier": 16, "holding_ratio_bp": 100}, {"tier": 17, "holding_ratio_bp": 10000}]))
    group, = shareholding_tier_visuals((metric,))
    assert [point.value for point in group.points] == [Decimal(0), None]
    assert "快照" in group.note


def test_comparison_chart_uses_original_current_prior_without_recomputing_change():
    comparison = StockFundamentalComparisonDTO(
        stock_code="2330", metric_name="margin", label="毛利率",
        current_period="2026-H1", prior_period="2025-H1",
        current_value=Decimal("55.25"), prior_value=Decimal("54.15"),
        value_unit="percent", change_value=Decimal("1.10"), change_unit="percentage_point",
        current_source_id="current", current_source_version="v1", source_id="comparison",
        source_version="c1", source_snapshot_hash="a" * 64, available_at="2026-10-21T08:00:00+08:00",
    )
    current = StockFundamentalObservationDTO(
        kind="statement_item", label="毛利率", metric_name="margin", period="2026-H1",
        value=Decimal("55.25"), unit="percent", source_id="current", source_version="v1",
    )
    group, = fundamental_visuals(StockResearchReportDTO(stock_code="2330", fundamentals=(current,), fundamental_comparisons=(comparison,)))
    assert [point.value for point in group.points] == [Decimal("54.15"), Decimal("55.25")]
    assert group.unit == "percent"
    assert comparison.change_value == Decimal("1.10")
