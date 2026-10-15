"""真實 public provider 的小時時鐘與 Decimal／來源守衛反例。"""
from dataclasses import replace
from datetime import timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from data_module.daily_market_monthly_revenue_cohort_v2 import DailyMarketMonthlyRevenueFactV2
from data_module.selection_fact_readers import _result_identity_sha256_v2
from data_module.current_fundamental_snapshots import _derived_monthly_source_version, _derived_monthly_yoy_comparator_version
from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortPin
from decision_module.factors.selection_fundamental_chip_rules import project_selection_monthly_revenue_yoy
from decision_module.factors.selection_monthly_revenue_yoy_v2 import (
    project_selection_monthly_revenue_yoy_v2, evaluate_monthly_revenue_yoy_min_v2,
)
from tests.test_recommendation_monthly_revenue_cohort import _fixture


def _source(pin, result):
    return DailyMarketMonthlyRevenueFactV2(result, _result_identity_sha256_v2(result, cohort_pin=pin), pin)


def _ready(tmp_path):
    provider, pin, _, _, config, _ = _fixture(tmp_path)
    result = provider.load_monthly_revenues(stock_code="2330", cutoff_at=pin.available_hour, pinned_daily_cohort=pin)
    assert result.status == "ready" and result.comparison_baseline is not None
    return pin, result, config


def test_hour_policy_is_observed_without_rewriting_old_evidence_or_formula(tmp_path):
    pin, result, _ = _ready(tmp_path)
    source = _source(pin, result)
    fact = project_selection_monthly_revenue_yoy_v2(source)
    old = project_selection_monthly_revenue_yoy(result)
    assert old.state == "unknown" and any("availability_basis" in reason for reason in old.reason_codes)
    assert fact.state == "observed" and fact.availability == "verified" and fact.reason_codes == ()
    assert fact.current.available_at == result.observations[0].available_at == pin.available_hour
    assert fact.current.observed_at == result.observations[0].observed_at < pin.available_hour
    assert fact.current.availability_snapshot_batch_id == pin.for_market("twse").batch_id
    assert fact.current.availability_first_persisted_at == pin.for_market("twse").first_persisted_at
    assert fact.growth_ratio == Decimal("0.25") and fact.growth_percent == Decimal("25.00")
    assert fact.method_version == old.method_version == "current-observed-decimal.v1"
    assert fact.source_fact_identity_sha256 == source.identity_sha256 and fact.cohort_pin is pin
    assert fact.to_dict()["cohort_pin"] == pin.to_dict()
    assert fact.historical_pit_eligible is False and fact.formal_pit_eligible is False
    assert evaluate_monthly_revenue_yoy_min_v2(fact, minimum_yoy_percent=Decimal("25")) == "match"
    assert evaluate_monthly_revenue_yoy_min_v2(fact, minimum_yoy_percent=Decimal("25.0000000001")) == "no_match"


def test_original_28_digit_context_does_not_depend_on_callers_context(tmp_path):
    pin, result, _ = _ready(tmp_path)
    with localcontext() as context:
        context.prec = 2
        fact = project_selection_monthly_revenue_yoy_v2(_source(pin, result))
    assert fact.growth_percent == Decimal("25.00")


def test_missing_comparator_preserves_unknown_and_no_threshold_default(tmp_path):
    pin, result, _ = _ready(tmp_path)
    result = replace(result, comparison_baseline=None, comparison_snapshot_sha256=None)
    fact = project_selection_monthly_revenue_yoy_v2(_source(pin, result))
    assert fact.state == "unknown" and fact.growth_percent is None
    assert "same_report_yoy_comparator_missing" in fact.reason_codes
    assert evaluate_monthly_revenue_yoy_min_v2(fact, minimum_yoy_percent=Decimal("-100")) == "unknown"


def test_derived_version_mismatch_keeps_original_source_guard(tmp_path):
    pin, result, _ = _ready(tmp_path)
    current = replace(result.observations[0], source_version="wrong-version")
    result = replace(result, observations=(current,))
    fact = project_selection_monthly_revenue_yoy_v2(_source(pin, result))
    assert fact.state == "unknown" and fact.growth_ratio is None
    assert "current_derived_source_version_invalid" in fact.reason_codes


@pytest.mark.parametrize("change", ({"unit": "USD"}, {"source": "wrong-source"}, {"formal_pit_eligible": True}, {"raw_source_sha256": "0" * 64}))
def test_source_fact_rejects_source_unit_pit_and_raw_identity(tmp_path, change):
    pin, result, _ = _ready(tmp_path)
    with pytest.raises(ValueError):
        current = replace(result.observations[0], **change)
        _source(pin, replace(result, observations=(current,)))


def test_available_after_cutoff_and_future_empty_pin_cannot_be_observed(tmp_path):
    pin, result, _ = _ready(tmp_path)
    with pytest.raises(ValueError, match="clock_after_cutoff"):
        current = replace(result.observations[0], available_at=result.cutoff_at + timedelta(microseconds=1))
        _source(pin, replace(result, observations=(current,)))
    with pytest.raises(ValueError, match="cohort_hour_after_cutoff"):
        _source(pin, replace(result, cutoff_at=pin.available_hour - timedelta(microseconds=1), observations=(), comparison_baseline=None, latest_period=None, status="missing"))


def test_frozen_source_mutation_is_revalidated_before_projection(tmp_path):
    pin, result, _ = _ready(tmp_path)
    source = _source(pin, result)
    object.__setattr__(source, "result_identity_sha256", "0" * 64)
    with pytest.raises(ValueError, match="fact_result_identity_mismatch"):
        project_selection_monthly_revenue_yoy_v2(source)


def test_materialization_later_than_cohort_is_not_moved_back_in_time(tmp_path):
    pin, result, _ = _ready(tmp_path)
    current = replace(result.observations[0], observed_at=pin.available_hour + timedelta(minutes=5), available_at=pin.available_hour)
    comparator = replace(result.comparison_baseline, observed_at=current.observed_at)
    result = replace(result, observations=(current,), comparison_baseline=comparator, cutoff_at=pin.available_hour + timedelta(hours=1))
    source = _source(pin, result)
    assert source.state == "observed"
    fact = project_selection_monthly_revenue_yoy_v2(source)
    assert fact.state == "unknown" and "current_available_at_inconsistent" in fact.reason_codes
    assert fact.current.observed_at == current.observed_at and fact.current.available_at == pin.available_hour


def test_unverified_revision_reason_cannot_become_observed_despite_ready_status(tmp_path):
    pin, result, _ = _ready(tmp_path)
    source = _source(pin, replace(result, blocked_periods=(pin.period,)))
    fact = project_selection_monthly_revenue_yoy_v2(source)
    assert fact.state == "unknown" and fact.growth_percent is None
    assert "current_monthly_revenue_period_blocked_by_unverified_revision" in fact.reason_codes


def test_period_after_decision_date_remains_unknown_with_valid_hour_evidence(tmp_path):
    pin, result, _ = _ready(tmp_path)
    market_pins = tuple(replace(item, period="2026-10") for item in pin.market_pins)
    future_period_pin = DailyMonthlyRevenueCohortPin(period="2026-10", required_markets=pin.required_markets, market_pins=market_pins, available_hour=pin.available_hour)
    current = result.observations[0]
    raw_version = current.raw_source_version.replace(":2026-09:", ":2026-10:")
    official_text = current.source_available_at.astimezone(timezone.utc).isoformat()
    current = replace(current, period="2026-10", raw_source_version=raw_version,
        source_version=_derived_monthly_source_version(raw_version, stock_code=current.stock_code, period="2026-10", value=str(current.revenue), unit=current.unit, source_available_at=official_text))
    comparator = replace(result.comparison_baseline, period="2025-10", parent_report_period="2026-10", raw_source_version=raw_version,
        source_version=_derived_monthly_yoy_comparator_version(raw_version, stock_code=current.stock_code, source_period="2026-10", comparator_period="2025-10", value=str(result.comparison_baseline.revenue), unit=current.unit, source_available_at=official_text))
    source = _source(future_period_pin, replace(result, latest_period="2026-10", observations=(current,), comparison_baseline=comparator))
    fact = project_selection_monthly_revenue_yoy_v2(source)
    assert fact.state == "unknown" and fact.growth_percent is None
    assert "current_period_after_decision_date" in fact.reason_codes
    assert not any("derived_source_version_invalid" in item for item in fact.reason_codes)
