"""月營收比較的缺月、前史與晚到資料反例；只使用合成正規化輸入。"""
from dataclasses import replace
from datetime import date
from decimal import Decimal
import pytest

from data_module.fundamental_data import MonthlyRevenueRecord
from decision_module.factors.factor_dtos import FactorQuality
from decision_module.factors.factor_gate import FactorGate
from decision_module.factors.fundamental_adapters import build_revenue_factor_pack


def record(period: str, value: str, available: date) -> MonthlyRevenueRecord:
    year, month = map(int, period.split("-"))
    return MonthlyRevenueRecord("2330", period, date(year, month, 28), available,
        available, available, Decimal(value), "synthetic.monthly", "synthetic-source.v1",
        legacy_quality_wire_value="observed")


def factors(rows, period="2026-05"):
    return build_revenue_factor_pack(tuple(rows), stock_code="2330", decision_period=period)


def test_gap_months_are_not_a_three_calendar_month_trend():
    result = factors((record("2026-01", "100", date(2026, 2, 10)),
        record("2026-03", "110", date(2026, 4, 10)), record("2026-05", "120", date(2026, 6, 10))))
    trend = next(row for row in result.records if row.factor_name == "fundamental.revenue_3m_trend")
    assert trend.value == "insufficient" and trend.quality is FactorQuality.MISSING
    assert any(item.code == "fundamental_revenue.calendar_months_missing" for item in result.diagnostics)
    gate = FactorGate().validate_for_decision(result.records, decision_date=date(2026, 6, 15))
    assert trend in gate.skipped and trend not in gate.accepted


def test_a_single_observation_is_not_a_new_high():
    result = factors((record("2026-05", "120", date(2026, 6, 10)),))
    high = next(row for row in result.records if row.factor_name == "fundamental.revenue_new_high")
    assert high.value is None and high.quality is FactorQuality.MISSING
    assert any(item.code == "fundamental_revenue.prior_history_missing" for item in result.diagnostics)
    assert FactorGate().validate_for_decision(result.records, decision_date=date(2026, 6, 15)).accepted == ()


def test_late_comparison_rows_cannot_use_the_current_rows_earlier_clock():
    result = factors((record("2026-03", "100", date(2026, 7, 10)),
        record("2026-04", "110", date(2026, 6, 20)), record("2026-05", "120", date(2026, 6, 10))))
    by_name = {row.factor_name: row for row in result.records}
    assert by_name["fundamental.revenue_3m_trend"].available_date == date(2026, 7, 10)
    assert by_name["fundamental.revenue_new_high"].available_date == date(2026, 7, 10)
    assert by_name["fundamental.revenue_mom"].available_date == date(2026, 6, 20)
    assert FactorGate().validate_for_decision(result.records, decision_date=date(2026, 6, 15)).accepted == ()


def test_ambiguous_current_period_is_rejected_instead_of_selecting_first():
    first = record("2026-05", "120", date(2026, 6, 10))
    second = replace(first, revenue=Decimal("90"), source_version="synthetic-source.v2")
    one = factors((first, second))
    two = factors((second, first))
    assert one.records == two.records == ()
    assert any(item.code == "fundamental_revenue.current_period_conflict" for item in one.diagnostics)


def test_cross_year_window_has_explicit_method_and_consumed_periods():
    result = factors((record("2025-12", "100", date(2026, 1, 10)),
        record("2026-01", "110", date(2026, 2, 10)), record("2026-02", "120", date(2026, 3, 10))), "2026-02")
    trend = next(row for row in result.records if row.factor_name == "fundamental.revenue_3m_trend")
    assert trend.value == "up"
    assert trend.metadata["method_version"] == "fundamental-revenue-pack.v2"
    assert tuple(item["period"] for item in trend.metadata["inputs"]) == ("2025-12", "2026-01", "2026-02")
    high = next(row for row in result.records if row.factor_name == "fundamental.revenue_new_high")
    assert high.metadata["comparison_scope"] == "provided_prior_months"
    assert high.value == 1 and high.source_version == "synthetic-source.v1"


def test_future_period_append_and_input_order_do_not_change_old_factors():
    rows = (record("2025-05", "90", date(2025, 6, 10)), record("2026-03", "100", date(2026, 4, 10)),
        record("2026-04", "110", date(2026, 5, 10)), record("2026-05", "120", date(2026, 6, 10)))
    before = tuple(item.to_dict() for item in factors(rows).records)
    future = record("2026-06", "99999999999999999999.99", date(2026, 7, 10))
    after = tuple(item.to_dict() for item in factors(tuple(reversed(rows)) + (future,)).records)
    assert before == after
    assert rows[-1].revenue == Decimal("120")


@pytest.mark.parametrize("quality", ["missing", "neutral"])
def test_unusable_prior_quality_does_not_become_observed_from_current(quality):
    rows = (replace(record("2026-03", "100", date(2026, 4, 10)), legacy_quality_wire_value=quality),
        record("2026-04", "110", date(2026, 5, 10)), record("2026-05", "120", date(2026, 6, 10)))
    result = factors(rows)
    by_name = {item.factor_name: item for item in result.records}
    assert by_name["fundamental.revenue_3m_trend"].value == "insufficient"
    assert by_name["fundamental.revenue_new_high"].value is None
    gate = FactorGate().validate_for_decision(result.records, decision_date=date(2026, 6, 15))
    assert tuple(item.factor_name for item in gate.accepted) == ("fundamental.revenue_mom",)


def test_contributing_estimate_quality_and_original_inputs_are_preserved():
    rows = (record("2026-03", "100", date(2026, 4, 10)),
        replace(record("2026-04", "110", date(2026, 5, 10)), legacy_quality_wire_value="estimated"),
        record("2026-05", "120", date(2026, 6, 10)))
    assert all(item.quality is FactorQuality.ESTIMATED for item in factors(rows).records)
    assert rows[-1].legacy_quality_wire_value == "observed"


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_current_revenue_never_produces_a_factor(invalid):
    result = factors((record("2026-05", invalid, date(2026, 6, 10)),))
    assert result.records == ()
    assert result.diagnostics[0].code == "fundamental_revenue.current_value_invalid"


def test_ambiguous_prior_does_not_choose_a_yoy_or_momentum_baseline():
    prior = record("2026-04", "100", date(2026, 5, 10))
    result = factors((prior, replace(prior, revenue=Decimal("105")), record("2026-05", "120", date(2026, 6, 10))))
    assert result.records == ()
    assert result.diagnostics[0].code == "fundamental_revenue.comparison_period_conflict"


def test_bad_period_and_unknown_comparison_clock_fail_closed():
    current = record("2026-05", "120", date(2026, 6, 10))
    assert factors((replace(current, period="2026-5"),)).diagnostics[0].code == "fundamental_revenue.invalid_period"
    prior = replace(record("2026-04", "100", date(2026, 5, 10)), available_date=None)
    result = factors((prior, current))
    assert result.records == ()
    assert result.diagnostics[0].code == "fundamental_revenue.comparison_available_date_missing"
