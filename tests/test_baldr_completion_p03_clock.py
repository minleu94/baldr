from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from data_module.current_fundamental_snapshots import (
    MONTHLY_SNAPSHOT_SOURCE,
    _derived_monthly_source_version,
    _derived_monthly_yoy_comparator_version,
)
from data_module.recommendation_current_fundamental_provider import (
    CurrentMonthlyRevenueReadResult,
    CurrentObservedMonthlyRevenueInput,
)
from decision_module.factors.selection_fundamental_chip_rules import (
    SelectionMonthlyRevenueYoYFact,
    evaluate_monthly_revenue_yoy_min,
    project_selection_monthly_revenue_yoy,
    sort_selection_monthly_revenue_yoy,
)


UTC = timezone.utc
TAIPEI = ZoneInfo("Asia/Taipei")
CUTOFF = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
CURRENT_PERIOD = "2026-08"
BASELINE_PERIOD = "2025-08"
RAW_BYTES = b"synthetic MOPS revenue HTML fixture"
RAW_SHA256 = hashlib.sha256(RAW_BYTES).hexdigest()


def _result(
    *,
    stock_code: str = "2330",
    current_revenue: Decimal = Decimal("1234500"),
    baseline_revenue: Decimal = Decimal("1000000"),
    cutoff: datetime = CUTOFF,
    source_available_at: datetime | None = CUTOFF - timedelta(hours=1),
    current_market: str = "twse",
    baseline_market: str | None = None,
    current_period: str = CURRENT_PERIOD,
    baseline_period: str = BASELINE_PERIOD,
    current_unit: str = "TWD",
    baseline_unit: str = "TWD",
    current_basis: str = "monthly_flow",
    baseline_basis: str = "monthly_flow",
    current_availability_basis: str | None = None,
    baseline_availability_basis: str | None = None,
    raw_sha256: str = RAW_SHA256,
    comparison_snapshot_sha256: str | None = None,
    status: str = "ready",
    latest_period: str | None = None,
) -> CurrentMonthlyRevenueReadResult:
    market_for_raw = current_market if current_market in {"twse", "tpex"} else "twse"
    raw_hash = raw_sha256 if len(raw_sha256) == 64 else RAW_SHA256
    capture_text = (
        source_available_at.astimezone(UTC).isoformat()
        if source_available_at is not None
        else None
    )
    if capture_text is None:
        raw_version = f"mops-static-{market_for_raw}-{current_period}-sha256-{raw_hash}"
    else:
        raw_version = (
            f"mops-static-snapshot.v2:{market_for_raw}:{current_period}:"
            f"body_completed_at:{capture_text}:sha256:{raw_hash}"
        )
    current_observed_at = cutoff - timedelta(minutes=20)
    comparator_observed_at = cutoff - timedelta(minutes=10)
    current_source_version = _derived_monthly_source_version(
        raw_version,
        stock_code=stock_code,
        period=current_period,
        value=str(current_revenue),
        unit=current_unit,
        source_available_at=capture_text or "",
    )
    current = CurrentObservedMonthlyRevenueInput(
        stock_code=stock_code,
        period=current_period,
        revenue=current_revenue,
        observed_at=current_observed_at,
        source_available_at=source_available_at,
        available_at=max(
            current_observed_at,
            source_available_at or current_observed_at,
        ),
        source=MONTHLY_SNAPSHOT_SOURCE,
        source_version=current_source_version,
        market=current_market,
        raw_source_version=raw_version,
        raw_source_sha256=raw_sha256,
        unit=current_unit,
        period_basis=current_basis,
        basis_verified=True,
        aggregate_feature_eligible=False,
        formal_pit_eligible=False,
        availability_basis=current_availability_basis
        or (
            "official_body_capture"
            if source_available_at is not None
            else "local_verified_observation"
        ),
        input_role="reported_period_value",
    )

    comparator_market = baseline_market or current_market
    expected_comparator_period = (
        f"{int(current_period[:4]) - 1:04d}-{current_period[5:]}"
    )
    comparator_source_version = _derived_monthly_yoy_comparator_version(
        raw_version,
        stock_code=stock_code,
        source_period=current_period,
        comparator_period=expected_comparator_period,
        value=str(baseline_revenue),
        unit=baseline_unit,
        source_available_at=capture_text or "",
    )
    if comparison_snapshot_sha256 is not None:
        comparator_source_version += (
            f":verified-csv-sha256:{comparison_snapshot_sha256}"
        )
    comparator = CurrentObservedMonthlyRevenueInput(
        stock_code=stock_code,
        period=baseline_period,
        revenue=baseline_revenue,
        observed_at=comparator_observed_at,
        source_available_at=source_available_at,
        available_at=max(
            comparator_observed_at,
            source_available_at or comparator_observed_at,
        ),
        source=MONTHLY_SNAPSHOT_SOURCE,
        source_version=comparator_source_version,
        market=comparator_market,
        raw_source_version=raw_version,
        raw_source_sha256=raw_sha256,
        unit=baseline_unit,
        period_basis=baseline_basis,
        basis_verified=True,
        aggregate_feature_eligible=False,
        formal_pit_eligible=False,
        availability_basis=baseline_availability_basis
        or (
            "official_body_capture"
            if source_available_at is not None
            else "local_verified_observation"
        ),
        input_role="same_report_prior_year_comparison_baseline",
        parent_report_period=current_period,
    )
    return CurrentMonthlyRevenueReadResult(
        status=status,
        stock_code=stock_code,
        cutoff_at=cutoff,
        latest_period=latest_period or current_period,
        observations=(current,),
        comparison_baseline=comparator,
        comparison_snapshot_sha256=comparison_snapshot_sha256,
    )


def test_monthly_revenue_yoy_preserves_decimal_units_and_full_current_only_evidence() -> None:
    fact = project_selection_monthly_revenue_yoy(_result())

    assert fact.state == "observed"
    assert fact.growth_ratio == Decimal("0.2345")
    assert fact.growth_ratio_unit == "ratio"
    assert fact.growth_percent == Decimal("23.4500")
    assert fact.growth_percent_unit == "percent"
    assert fact.current is not None
    assert fact.current.revenue == Decimal("1234500")
    assert fact.current.unit == "TWD"
    assert fact.current.period_basis == "monthly_flow"
    assert fact.current.period_end is not None
    assert fact.current.period_end.isoformat() == "2026-08-31"
    assert fact.comparator is not None
    assert fact.comparator.period == "2025-08"
    assert fact.comparator.parent_report_period == "2026-08"
    assert fact.comparator.raw_source_sha256 == fact.current.raw_source_sha256 == RAW_SHA256
    assert fact.source_scope == "current_observed_only"
    assert fact.historical_pit_eligible is False
    assert fact.formal_pit_eligible is False

    payload = json.loads(fact.to_json())
    assert payload["growth_ratio"] == "0.2345"
    assert payload["growth_ratio_unit"] == "ratio"
    assert payload["growth_percent"] == "23.4500"
    assert payload["growth_percent_unit"] == "percent"
    assert fact.identity_sha256 == project_selection_monthly_revenue_yoy(_result()).identity_sha256


def test_explicit_existing_yoy_percent_threshold_has_no_implicit_default() -> None:
    fact = project_selection_monthly_revenue_yoy(_result())

    assert evaluate_monthly_revenue_yoy_min(
        fact, minimum_yoy_percent=Decimal("23.45")
    ) == "match"
    assert evaluate_monthly_revenue_yoy_min(
        fact, minimum_yoy_percent=Decimal("23.4501")
    ) == "no_match"
    assert evaluate_monthly_revenue_yoy_min(
        project_selection_monthly_revenue_yoy(
            _result(baseline_revenue=Decimal("0"))
        ),
        minimum_yoy_percent=Decimal("0"),
    ) == "unknown"


def test_local_observation_clock_is_current_only_and_not_a_publication_claim() -> None:
    fact = project_selection_monthly_revenue_yoy(
        _result(source_available_at=None)
    )

    assert fact.state == "observed"
    assert fact.availability == "verified"
    assert fact.current is not None
    assert fact.current.source_available_at is None
    assert fact.current.availability_basis == "local_verified_observation"
    assert fact.current.available_at == fact.current.observed_at
    assert fact.formal_pit_eligible is False
    assert fact.historical_pit_eligible is False


@pytest.mark.parametrize(
    ("changes", "expected_reason"),
    (
        ({"cutoff": datetime(2026, 10, 7, 9, 0)}, "decision_cutoff_not_aware"),
        ({"status": "missing"}, "monthly_revenue_source_missing"),
        ({"current_market": "nasdaq"}, "current_market_unknown"),
        ({"baseline_market": "tpex"}, "same_report_yoy_comparator_market_mismatch"),
        ({"current_unit": "thousand_TWD"}, "current_unit_mismatch"),
        ({"baseline_basis": "unknown"}, "comparator_period_basis_mismatch"),
        ({"baseline_period": "2025-07"}, "same_report_yoy_comparator_period_mismatch"),
        ({"baseline_revenue": Decimal("0")}, "comparison_baseline_not_positive_finite_decimal"),
        ({"raw_sha256": "not-a-sha"}, "current_raw_source_identity_invalid"),
    ),
)
def test_missing_or_inconsistent_source_evidence_is_unknown(
    changes: dict[str, object], expected_reason: str
) -> None:
    result = _result()
    if "cutoff" in changes:
        result = replace(result, cutoff_at=changes["cutoff"])  # type: ignore[arg-type]
    else:
        result = _result(**changes)  # type: ignore[arg-type]
    fact = project_selection_monthly_revenue_yoy(result)

    assert fact.state == "unknown"
    assert fact.growth_ratio is None
    assert fact.growth_percent is None
    assert expected_reason in fact.reason_codes


def test_cutoff_rejects_body_capture_after_decision_freeze() -> None:
    late_capture = CUTOFF + timedelta(seconds=1)
    result = _result(source_available_at=late_capture)

    fact = project_selection_monthly_revenue_yoy(result)

    assert fact.state == "unknown"
    assert "current_source_available_after_cutoff" in fact.reason_codes
    assert fact.current is not None
    assert fact.current.source_available_at == late_capture


def test_fallback_comparator_csv_sha_is_preserved_and_bound_to_version() -> None:
    csv_sha = hashlib.sha256(b"verified normalized CSV").hexdigest()
    fact = project_selection_monthly_revenue_yoy(
        _result(comparison_snapshot_sha256=csv_sha)
    )

    assert fact.state == "observed"
    assert fact.comparison_snapshot_sha256 == csv_sha
    assert fact.comparator is not None
    assert fact.comparator.source_version.endswith(
        f":verified-csv-sha256:{csv_sha}"
    )


def test_global_yoy_sort_keeps_unknown_tail_and_code_tiebreak_in_both_directions() -> None:
    higher = project_selection_monthly_revenue_yoy(
        _result(stock_code="2882", current_revenue=Decimal("110"), baseline_revenue=Decimal("100"))
    )
    same_value_lower_code = project_selection_monthly_revenue_yoy(
        _result(stock_code="2330", current_revenue=Decimal("110"), baseline_revenue=Decimal("100"))
    )
    lower = project_selection_monthly_revenue_yoy(
        _result(stock_code="2603", current_revenue=Decimal("90"), baseline_revenue=Decimal("100"))
    )
    unknown = project_selection_monthly_revenue_yoy(
        _result(stock_code="6488", baseline_revenue=Decimal("0"))
    )
    all_facts = (higher, unknown, lower, same_value_lower_code)

    ascending = sort_selection_monthly_revenue_yoy(all_facts)
    descending = sort_selection_monthly_revenue_yoy(all_facts, descending=True)

    assert [item.stock_code for item in ascending] == ["2603", "2330", "2882", "6488"]
    assert [item.stock_code for item in descending] == ["2330", "2882", "2603", "6488"]


def test_large_global_yoy_sort_splits_known_and_unknown_in_linear_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = project_selection_monthly_revenue_yoy(_result())
    unknown_template = project_selection_monthly_revenue_yoy(
        _result(baseline_revenue=Decimal("0"))
    )
    facts = tuple(
        replace(
            observed if index % 2 == 0 else unknown_template,
            stock_code=f"{1000 + index:04d}",
        )
        for index in range(2_000)
    )
    original_eq = SelectionMonthlyRevenueYoYFact.__eq__
    equality_calls = 0

    def count_equality(self: SelectionMonthlyRevenueYoYFact, other: Any) -> Any:
        nonlocal equality_calls
        equality_calls += 1
        return original_eq(self, other)

    monkeypatch.setattr(SelectionMonthlyRevenueYoYFact, "__eq__", count_equality)
    sorted_facts = sort_selection_monthly_revenue_yoy(facts)

    assert len(sorted_facts) == len(facts)
    assert all(item.state == "observed" for item in sorted_facts[:1_000])
    assert all(item.state == "unknown" for item in sorted_facts[1_000:])
    assert equality_calls < len(facts) * 10


def test_fact_decision_date_uses_aware_cutoff_local_day_not_market_price_date() -> None:
    taipei_cutoff = datetime(2026, 10, 7, 16, 0, tzinfo=TAIPEI)
    result = _result(
        cutoff=taipei_cutoff,
        source_available_at=taipei_cutoff - timedelta(hours=1),
    )

    fact = project_selection_monthly_revenue_yoy(result)

    assert fact.state == "observed"
    assert fact.decision_date is not None
    assert fact.decision_date.isoformat() == "2026-10-07"
    assert fact.decision_cutoff == taipei_cutoff.astimezone(UTC)
    assert fact.current is not None
    assert fact.current.period_end is not None
    assert fact.current.period_end.isoformat() == "2026-08-31"


def test_wrong_same_report_source_sha_and_missing_baseline_both_remain_unknown() -> None:
    source_sha_mismatch = _result()
    assert source_sha_mismatch.comparison_baseline is not None
    bad_comparator = replace(
        source_sha_mismatch.comparison_baseline,
        raw_source_sha256=hashlib.sha256(b"different raw source").hexdigest(),
    )
    mismatch = project_selection_monthly_revenue_yoy(
        replace(source_sha_mismatch, comparison_baseline=bad_comparator)
    )
    missing = project_selection_monthly_revenue_yoy(
        replace(source_sha_mismatch, comparison_baseline=None)
    )

    assert mismatch.state == "unknown"
    assert "same_report_yoy_comparator_raw_source_sha256_mismatch" in mismatch.reason_codes
    assert missing.state == "unknown"
    assert "same_report_yoy_comparator_missing" in missing.reason_codes


def test_invalid_source_capture_token_fails_closed_without_raising() -> None:
    result = _result()
    assert result.observations
    corrupt_current = replace(
        result.observations[0],
        raw_source_version="mops-static-snapshot.v2:twse:2026-08:body_completed_at:not-a-date:sha256:" + RAW_SHA256,
    )
    fact = project_selection_monthly_revenue_yoy(
        replace(result, observations=(corrupt_current,))
    )

    assert fact.state == "unknown"
    assert "current_raw_source_identity_invalid" in fact.reason_codes
