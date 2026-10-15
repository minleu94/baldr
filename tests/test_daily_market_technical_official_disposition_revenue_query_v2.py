from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_ma_comparison_v1",)

from app_module.daily_market_monthly_revenue_yoy_index_v2 import (
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionSortValueV1,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V2,
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error,
    DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2,
    DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2,
    sort_revenue_keys_v2,
)
from tests.test_selection_fundamental_daily_cohort_v2 import (
    _daily_cohort_environment,
)


@dataclass(frozen=True, slots=True)
class _RevenueIndexEnvironment:
    provider: Any
    cohort_reader: Any
    session: DailyMarketMonthlyRevenueYoyIndexSessionV2
    stock_codes: tuple[str, ...]


def _daily_f17_environment(root: Path):
    """Build one observed F17 member through the original parser and full daily ports."""
    import tests.test_baldr_completion_p03_sources as provider_fixture
    import tests.test_selection_fundamental_daily_cohort_v2 as daily_fixture
    original_html = daily_fixture.MOPS_SAMPLE_HTML
    twse_html = original_html.replace("<td>2330</td><td>台積電</td>", "<td>1000</td><td>合成測試公司</td>")
    assert twse_html != original_html
    original_reader = daily_fixture._daily_market_reader

    def market_reader(root, market, *, delay_availability_hour):
        # TPEx keeps the original 2330 -> 6488 fixture conversion.
        with pytest.MonkeyPatch.context() as market_patch:
            market_patch.setattr(daily_fixture, "MOPS_SAMPLE_HTML", twse_html if market == "twse" else original_html)
            return original_reader(root, market, delay_availability_hour=delay_availability_hour)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(provider_fixture, "MOPS_SAMPLE_HTML", twse_html)
        patch.setattr(daily_fixture, "_daily_market_reader", market_reader)
        return _daily_cohort_environment(root)


@pytest.fixture(scope="module")
def revenue_index_environment(tmp_path_factory: pytest.TempPathFactory, ma_context: Any) -> Any:
    root = tmp_path_factory.mktemp("revenue-query-v2")
    provider, cohort_reader, _pin, _market_readers, _market_roots = _daily_f17_environment(
        root / "daily-source",
    )
    stock_codes = ma_context.session.verified_declared_stock_codes()
    session = DailyMarketMonthlyRevenueYoyIndexSessionV2.open(
        provider,
        daily_monthly_cohort_reader=cohort_reader,
        snapshot_root=root / "monthly-yoy-snapshot",
        stock_codes=stock_codes,
        cutoff_at=ma_context.query.f17_query.decision_cutoff,
    )
    try:
        for start in range(0, len(stock_codes), 16):
            session.load_batch(stock_codes[start:start + 16])
        session.finish()
        yield _RevenueIndexEnvironment(provider, cohort_reader, session, stock_codes)
    finally:
        session.close()


def _ma_query(ma_context: Any, *, ma_states: tuple[str, ...] | None = ("unknown",)) -> Any:
    return ma_context.session.create_ma_query_v1(ma_states=ma_states)


def _query(
    ma_context: Any,
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV2,
    *,
    minimum_yoy_percent: Decimal | None = None,
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2, ...] = (),
) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
    return DailyMarketTechnicalOfficialDispositionRevenueQueryV2.create(
        _ma_query(ma_context),
        index_session,
        minimum_yoy_percent=minimum_yoy_percent,
        sort_clauses=sort_clauses,
    )


def test_query_codec_binds_exact_full_cohort_pins_and_keeps_hour_basis_separate(
    ma_context: Any,
    revenue_index_environment: _RevenueIndexEnvironment,
) -> None:
    index = revenue_index_environment.session.index
    nested = _ma_query(ma_context)
    threshold = Decimal("1234567890123456789012345678.0001")
    query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.create(
        nested,
        revenue_index_environment.session,
        minimum_yoy_percent=threshold,
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(
                "monthly_revenue_yoy_percent", "desc",
            ),
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("stock_code", "asc"),
        ),
    )
    reopened = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(query.to_json())

    assert reopened == query
    assert reopened.ma_query.to_json() == nested.to_json()
    assert reopened.f17_query.query_identity_sha256 == nested.f17_query.query_identity_sha256
    assert reopened.minimum_yoy_percent == threshold
    assert reopened.monthly_yoy_index_identity_sha256 == index.index_identity_sha256
    assert reopened.monthly_yoy_finished_cohort_identity_sha256 == index.finished_cohort_identity_sha256
    assert reopened.monthly_yoy_source_clock_identity_sha256 == index.source_clock.identity_sha256
    assert reopened.monthly_source_reference_external_sha256 == index.source_reference_external_sha256
    assert reopened.monthly_source_content_identity_sha256 == index.source_content_identity_sha256
    assert reopened.monthly_cohort_sha256 == index.cohort_pin.cohort_sha256
    assert reopened.monthly_availability_status == "cohort_hour_bound"
    assert index.source_scope == "current_observed_only"
    assert index.availability_status == "cohort_hour_bound"
    assert index.historical_pit_eligible is False
    assert index.formal_pit_eligible is False


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        ("missing", "query_fields_invalid"),
        ("extra", "query_fields_invalid"),
        ("bad_sha", "query_source_identity_invalid"),
        ("wrong_availability", "query_monthly_availability_invalid"),
        ("wrong_schema", "query_schema_unsupported"),
    ],
)
def test_query_codec_rejects_missing_extra_or_invalid_monthly_source_pins(
    ma_context: Any,
    revenue_index_environment: _RevenueIndexEnvironment,
    mutation: str,
    error_code: str,
) -> None:
    payload = _query(ma_context, revenue_index_environment.session).to_dict()
    if mutation == "missing":
        payload.pop("monthly_source_reference_external_sha256")
    elif mutation == "extra":
        payload["unrecognized"] = "value"
    elif mutation == "bad_sha":
        payload["monthly_cohort_sha256"] = "not-a-sha"
    elif mutation == "wrong_availability":
        payload["monthly_availability_status"] = "unknown"
    else:
        payload["schema_version"] = "daily-market-technical-official-disposition-revenue-query.v1"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error) as raised:
        DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_dict(payload)
    assert raised.value.code == error_code


def test_query_rejects_float_and_noncanonical_condition_policy(
    ma_context: Any,
    revenue_index_environment: _RevenueIndexEnvironment,
) -> None:
    nested = _ma_query(ma_context)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="minimum_yoy_percent_invalid"):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV2.create(
            nested,
            revenue_index_environment.session,
            minimum_yoy_percent=0.1,  # type: ignore[arg-type]
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="condition_policy_noncanonical"):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV2.create(
            nested,
            revenue_index_environment.session,
            condition_combine_mode="OR",
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="unknown_only_without_condition"):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV2.create(
            _ma_query(ma_context, ma_states=None),
            revenue_index_environment.session,
            unknown_policy="only",
        )


def test_query_json_rejects_duplicate_keys_noncanonical_bytes_and_identity_mutation(
    ma_context: Any,
    revenue_index_environment: _RevenueIndexEnvironment,
) -> None:
    query = _query(ma_context, revenue_index_environment.session)
    raw = query.to_json()
    duplicate = raw[:-1] + ',"monthly_availability_status":"cohort_hour_bound"}'
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="duplicate_json_key"):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(duplicate)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="json_noncanonical"):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(raw + " ")
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="query_identity_mismatch"):
        replace(query, minimum_yoy_percent=Decimal("1"))


def test_query_requires_exact_finished_v2_session_and_matching_cutoff(
    ma_context: Any,
    revenue_index_environment: _RevenueIndexEnvironment,
    tmp_path: Path,
) -> None:
    nested = _ma_query(ma_context)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="monthly_index_session_not_reader_issued"):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV2.create(nested, object())  # type: ignore[arg-type]

    unfinished = DailyMarketMonthlyRevenueYoyIndexSessionV2.open(
        revenue_index_environment.provider,
        daily_monthly_cohort_reader=revenue_index_environment.cohort_reader,
        snapshot_root=tmp_path / "unfinished-v2-index",
        stock_codes=revenue_index_environment.stock_codes,
        cutoff_at=ma_context.query.f17_query.decision_cutoff,
    )
    try:
        with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="monthly_index_not_reader_issued"):
            DailyMarketTechnicalOfficialDispositionRevenueQueryV2.create(nested, unfinished)
    finally:
        unfinished.close()

    provider, cohort_reader, _pin, _readers, _roots = _daily_cohort_environment(
        tmp_path / "wrong-cutoff-source",
    )
    wrong_cutoff = ma_context.query.f17_query.decision_cutoff + timedelta(hours=1)
    other = DailyMarketMonthlyRevenueYoyIndexSessionV2.open(
        provider,
        daily_monthly_cohort_reader=cohort_reader,
        snapshot_root=tmp_path / "wrong-cutoff-index",
        stock_codes=revenue_index_environment.stock_codes,
        cutoff_at=wrong_cutoff,
    )
    try:
        for start in range(0, len(revenue_index_environment.stock_codes), 16):
            other.load_batch(revenue_index_environment.stock_codes[start:start + 16])
        other.finish()
        with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="monthly_cutoff_source_mismatch"):
            DailyMarketTechnicalOfficialDispositionRevenueQueryV2.create(nested, other)
    finally:
        other.close()


def test_page_request_is_canonical_bounded_and_tied_to_the_query(
    ma_context: Any,
    revenue_index_environment: _RevenueIndexEnvironment,
) -> None:
    query = _query(ma_context, revenue_index_environment.session)
    request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
        query, page_index=1, page_size=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V2,
    )
    assert DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(
        request.to_json(),
    ) == request
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="page_index_invalid"):
        replace(request, page_index=-1).to_dict()
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="page_size_invalid"):
        DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
            query, page_index=0, page_size=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V2 + 1,
        )


def test_global_sort_v2_keeps_unknown_revenue_last_and_rejects_duplicate_members(
    ma_context: Any,
    revenue_index_environment: _RevenueIndexEnvironment,
) -> None:
    query = _query(
        ma_context,
        revenue_index_environment.session,
        minimum_yoy_percent=Decimal("0"),
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(
                "monthly_revenue_yoy_percent", "desc",
            ),
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("stock_code", "asc"),
        ),
    )
    codes_and_growth = (("1000", Decimal("2")), ("1001", None), ("1002", Decimal("1")))
    keys = tuple(
        DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2(
            query_identity_sha256=query.query_identity_sha256,
            stock_code=code,
            sort_values=(
                DailyMarketTechnicalOfficialDispositionSortValueV1(
                    "monthly_revenue_yoy_percent", "desc", growth,
                ),
                DailyMarketTechnicalOfficialDispositionSortValueV1("stock_code", "asc", code),
            ),
            fact_row_sha256=str(index + 1) * 64,
            technical_snapshot_identity_sha256=None,
            technical_source_identity=None,
            ma_evidence_identity_sha256=None,
            monthly_result_identity_sha256=str(index + 2) * 64,
            monthly_fact_identity_sha256=str(index + 3) * 64,
        )
        for index, (code, growth) in enumerate(codes_and_growth)
    )
    ordered = sort_revenue_keys_v2(query, keys)
    assert tuple(item.stock_code for item in ordered) == ("1000", "1002", "1001")
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="sort_key_mismatch"):
        sort_revenue_keys_v2(query, (keys[0], keys[0]))


def test_normal_read_session_executes_full_n_v2_and_pins_both_state_denominators(
    ma_context: Any,
    revenue_index_environment: _RevenueIndexEnvironment,
) -> None:
    bound = ma_context.session.with_monthly_revenue_yoy_index_v2(
        revenue_index_environment.session,
    )
    query = bound.create_revenue_query_v2(
        ma_states=("unknown",),
        minimum_yoy_percent=Decimal("0"),
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(
                "monthly_revenue_yoy_percent", "desc",
            ),
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("stock_code", "asc"),
        ),
    )
    result = bound.execute_revenue_query_v2(query)
    monthly_index = revenue_index_environment.session.index
    pins = dict(result.source_pins)

    assert result.scope == "current_only"
    assert result.availability_status == "unknown"
    assert result.monthly_official_available_at is None
    assert result.historical_pit_eligible is False
    assert pins["monthly_source_reference_external_sha256"] == monthly_index.source_reference_external_sha256
    assert pins["monthly_source_content_identity_sha256"] == monthly_index.source_content_identity_sha256
    assert pins["monthly_cohort_sha256"] == monthly_index.cohort_pin.cohort_sha256
    assert pins["monthly_availability_status"] == "cohort_hour_bound"
    assert result.counts.declared_count == len(revenue_index_environment.stock_codes)
    assert dict(result.counts.monthly_source_state_counts) == dict(monthly_index.fact_state_counts)
    assert dict(result.counts.monthly_projected_state_counts) == dict(monthly_index.projected_state_counts)
    assert dict(monthly_index.fact_state_counts) == {"blocked": 0, "observed": 1, "unknown": 257}
    assert dict(monthly_index.projected_state_counts) == {"observed": 1, "unknown": 257}
    assert monthly_index.entry_for("1000").projected_fact.growth_percent == Decimal("22.006875")
    assert monthly_index.entry_for("9999").projected_fact.state == "unknown"
    assert sum(dict(result.counts.monthly_source_state_counts)[key] for key in ("blocked", "observed", "unknown")) == len(revenue_index_environment.stock_codes)
    assert sum(dict(result.counts.monthly_projected_state_counts)[key] for key in ("observed", "unknown")) == len(revenue_index_environment.stock_codes)

    request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
        query, page_index=0, page_size=4,
    )
    page = result.read_page_request(request)
    assert page.rows[0].stock_code == "1000"
    assert page.rows[0].monthly_entry.projected_fact.growth_percent == Decimal("22.006875")
    assert page.source_pins == result.source_pins
    assert tuple(row.stock_code for row in page.rows) == tuple(
        key.stock_code for key in result.ordered_sort_keys[:4]
    )
    assert page.to_dict()["availability_status"] == "unknown"

    changed_status = "partial" if result.result_status == "complete" else "complete"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="result_not_reader_issued"):
        replace(result, result_status=changed_status)  # type: ignore[arg-type]
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="page_not_reader_issued"):
        replace(page, result_status=changed_status)  # type: ignore[arg-type]
    original_page_index = page.page_index
    object.__setattr__(page, "page_index", original_page_index + 1)
    try:
        with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="page_not_reader_issued"):
            page.__post_init__()
    finally:
        object.__setattr__(page, "page_index", original_page_index)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error, match="result_not_reader_issued"):
        replace(result, scope="historical")  # type: ignore[arg-type]


def test_mixed_v2_monthly_truth_keeps_and_or_separate_and_cannot_rescue_hard_exclusions(
    ma_context: Any, revenue_index_environment: _RevenueIndexEnvironment,
) -> None:
    bound = ma_context.session.with_monthly_revenue_yoy_index_v2(revenue_index_environment.session)
    and_query = bound.create_revenue_query_v2(ma_states=("match",), minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="AND", unknown_policy="exclude")
    or_query = bound.create_revenue_query_v2(ma_states=("match",), minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR", unknown_policy="exclude")
    assert bound.execute_revenue_query_v2(and_query).visible_count == 0
    or_result = bound.execute_revenue_query_v2(or_query)
    assert tuple(key.stock_code for key in or_result.ordered_sort_keys) == ("1000",)
    hard_filtered = bound.with_conditions(row_scope_filter=("included_processed",),
        outer_stock_filter_mode="explicit_codes", outer_stock_codes=("1001",))
    blocked_query = hard_filtered.create_revenue_query_v2(ma_states=("match",),
        minimum_yoy_percent=Decimal("0"), condition_combine_mode="OR", unknown_policy="exclude")
    blocked_result = hard_filtered.execute_revenue_query_v2(blocked_query)
    assert blocked_result.counts.declared_count == 258
    assert blocked_result.visible_count == 0
    assert dict(blocked_result.counts.monthly_source_state_counts)["observed"] == 1
