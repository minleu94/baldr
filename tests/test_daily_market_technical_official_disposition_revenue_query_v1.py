from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_ma_comparison_v1",)

from app_module.daily_market_monthly_revenue_yoy_index_v1 import (
    DailyMarketMonthlyRevenueYoyIndexSessionV1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV1Error,
    DailyMarketTechnicalOfficialDispositionRevenueSortKeyV1,
    DailyMarketTechnicalOfficialDispositionSortValueV1,
    sort_revenue_keys_v1,
)
from tests.test_daily_market_monthly_revenue_read_session_v1 import _seed_provider


@pytest.fixture
def monthly_index_for_ma_context(tmp_path: Path, ma_context):
    provider = _seed_provider(tmp_path / "provider")
    session = DailyMarketMonthlyRevenueYoyIndexSessionV1.open(
        provider,
        snapshot_root=tmp_path / "isolated_monthly_snapshot",
        stock_codes=("2330",),
        cutoff_at=ma_context.session.query.decision_cutoff,
    )
    session.load_batch(("2330",))
    index = session.finish()
    return session, index


def test_query_codec_preserves_decimal_threshold_and_separates_current_availability(
    ma_context,
    monthly_index_for_ma_context,
) -> None:
    index_session, index = monthly_index_for_ma_context
    ma_query = ma_context.session.create_ma_query_v1(ma_states=("unknown",))
    query = DailyMarketTechnicalOfficialDispositionRevenueQueryV1.create(
        ma_query,
        index_session,
        minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR",
        unknown_policy="include",
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1(
                "monthly_revenue_yoy_percent", "desc",
            ),
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),
        ),
    )
    reopened = DailyMarketTechnicalOfficialDispositionRevenueQueryV1.from_json(query.to_json())

    assert reopened == query
    assert reopened.query_identity_sha256 == query.query_identity_sha256
    assert reopened.minimum_yoy_percent == Decimal("0")
    assert reopened.condition_combine_mode == "OR"
    assert reopened.monthly_yoy_index_identity_sha256 == index.index_identity_sha256
    assert index.historical_pit_eligible is False
    assert index.availability_status == "unknown"


def test_disabled_groups_do_not_supply_true_to_or_and_unknown_only_requires_a_group(
    ma_context,
    monthly_index_for_ma_context,
) -> None:
    index_session, _index = monthly_index_for_ma_context
    ma_query = ma_context.session.create_ma_query_v1(ma_states=None)
    no_conditions = DailyMarketTechnicalOfficialDispositionRevenueQueryV1.create(
        ma_query,
        index_session,
        minimum_yoy_percent=None,
        condition_combine_mode="AND",
        unknown_policy="include",
    )
    assert no_conditions.minimum_yoy_percent is None
    assert no_conditions.condition_combine_mode == "AND"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV1Error):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV1.create(
            ma_query,
            index_session,
            unknown_policy="only",
        )

    # Decimal zero is an enabled threshold, so a single-group OR is rejected as noncanonical.
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV1Error):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV1.create(
            ma_query,
            index_session,
            minimum_yoy_percent=Decimal("0"),
            condition_combine_mode="OR",
        )


def test_query_rejects_binary_float_threshold_and_non_neutral_nested_ma_query(
    ma_context,
    monthly_index_for_ma_context,
) -> None:
    index_session, _index = monthly_index_for_ma_context
    ma_query = ma_context.session.create_ma_query_v1(ma_states=("unknown",))
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV1Error):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV1.create(
            ma_query,
            index_session,
            minimum_yoy_percent=0.0,  # type: ignore[arg-type]
        )

    non_neutral = ma_context.session.create_ma_query_v1(
        ma_states=("unknown",),
        unknown_policy="exclude",
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueQueryV1Error):
        DailyMarketTechnicalOfficialDispositionRevenueQueryV1.create(
            non_neutral,
            index_session,
        )


def test_global_revenue_sort_keeps_nulls_last_in_both_directions(
    ma_context,
    monthly_index_for_ma_context,
) -> None:
    index_session, _index = monthly_index_for_ma_context
    ma_query = ma_context.session.create_ma_query_v1(ma_states=("unknown",))
    directions: tuple[tuple[Literal["asc", "desc"], tuple[str, str]], ...] = (
        ("asc", ("1002", "1000")),
        ("desc", ("1000", "1002")),
    )
    for direction, expected_known in directions:
        query = DailyMarketTechnicalOfficialDispositionRevenueQueryV1.create(
            ma_query,
            index_session,
            minimum_yoy_percent=Decimal("0"),
            sort_clauses=(
                DailyMarketTechnicalOfficialDispositionMaSortClauseV1(
                    "monthly_revenue_yoy_percent", direction,
                ),
                DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),
            ),
        )
        keys = tuple(
            DailyMarketTechnicalOfficialDispositionRevenueSortKeyV1(
                query_identity_sha256=query.query_identity_sha256,
                stock_code=code,
                sort_values=(
                    DailyMarketTechnicalOfficialDispositionSortValueV1(
                        "monthly_revenue_yoy_percent", direction, value,
                    ),
                    DailyMarketTechnicalOfficialDispositionSortValueV1(
                        "stock_code", "asc", code,
                    ),
                ),
                fact_row_sha256=(str(index + 1) * 64),
                technical_snapshot_identity_sha256=None,
                technical_source_identity=None,
                ma_evidence_identity_sha256=None,
                monthly_result_identity_sha256=(str(index + 2) * 64),
                monthly_fact_identity_sha256=(str(index + 3) * 64),
            )
            for index, (code, value) in enumerate((
                ("1000", Decimal("2")),
                ("1001", None),
                ("1002", Decimal("1")),
            ))
        )
        ordered = sort_revenue_keys_v1(query, keys)
        assert tuple(item.stock_code for item in ordered[:2]) == expected_known
        assert tuple(item.stock_code for item in ordered[2:]) == ("1001",)

