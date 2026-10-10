"""以既有 40-session 真實來源驗證 volatility OR rescue；尚未執行。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
from typing import Literal

import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite


_REPOSITORY_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "app_module").is_dir() and (parent / "tests").is_dir()
)
_TESTS_ROOT = str(_REPOSITORY_ROOT / "tests")
if _TESTS_ROOT not in sys.path:
    sys.path.insert(0, _TESTS_ROOT)

from test_daily_market_technical_official_disposition_composite_reader_v1 import _FullOwner

# 重用通過中的真 257 母體、public F17 opener 與 40-session 合成來源 fixture。
pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_reader_v1",
)


def _query_for_bandwidth(
    owner: _FullOwner,
    value: Decimal,
    *,
    combine: Literal["AND", "OR"],
) -> composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
    return composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        bandwidth_min_pct=value,
        bandwidth_max_pct=value,
        condition_combine_mode=combine,
        unknown_policy="exclude",
    )


def _assert_full_source_counts(
    result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> None:
    counts = result.counts
    population = counts.base_f17_counts.population
    assert (
        population.declared_count,
        population.included_count,
        population.processed_count,
        population.excluded_count,
        population.pending_count,
    ) == (258, 257, 257, 1, 0)
    assert counts.base_f17_counts.matching_count == 0
    assert sum(dict(counts.technical_truth_counts).values()) == 258
    assert dict(counts.technical_truth_counts) == {
        "match": 0,
        "no_match": 257,
        "unknown": 0,
        "not_applicable": 0,
        "not_evaluated": 1,
    }
    assert sum(dict(counts.volatility_truth_counts).values()) == 258
    for name in (
        "ma_state_counts",
        "kdj_state_counts",
        "bandwidth_state_counts",
        "atr14_state_counts",
    ):
        assert sum(dict(getattr(counts, name)).values()) == 257


def test_full257_observed_bandwidth_rescues_p01_no_match_only_under_or(
    bundle_fixture,
    full257_no_match_owner,
) -> None:
    owner = full257_no_match_owner
    included_codes = owner.session._selection.stock_codes
    volatility_by_code = {
        entry.stock_code: entry for entry in owner.group.volatility_entries
    }
    target_code = next(
        code
        for code in included_codes
        if type(volatility_by_code[code].evidence.bandwidth.value) is Decimal
        and volatility_by_code[code].evidence.bandwidth.value.is_finite()
    )
    observed_bandwidth = volatility_by_code[target_code].evidence.bandwidth.value
    assert type(observed_bandwidth) is Decimal
    assert observed_bandwidth.is_finite()
    assert target_code in bundle_fixture.included_codes

    or_query = _query_for_bandwidth(owner, observed_bandwidth, combine="OR")
    and_query = _query_for_bandwidth(owner, observed_bandwidth, combine="AND")
    assert or_query.active_groups == and_query.active_groups == (
        True,
        False,
        False,
        True,
    )

    or_result = owner.session.execute_composite_query_v1(or_query)
    and_result = owner.session.execute_composite_query_v1(and_query)
    _assert_full_source_counts(or_result)
    _assert_full_source_counts(and_result)

    # 條件只改全域 OR/AND；母體與所有來源 projection counts 應完全相同。
    assert or_result.counts.base_f17_counts.to_dict() == and_result.counts.base_f17_counts.to_dict()
    for name in (
        "ma_state_counts",
        "kdj_state_counts",
        "bandwidth_state_counts",
        "atr14_state_counts",
        "technical_truth_counts",
        "ma_truth_counts",
        "kdj_truth_counts",
        "volatility_truth_counts",
    ):
        assert getattr(or_result.counts, name) == getattr(and_result.counts, name)
    assert or_result.source_pins == and_result.source_pins

    assert or_result.visible_count >= 1
    target_row = next(
        row
        for page_index in range((or_result.visible_count + 255) // 256)
        for row in or_result.read_page(page_index, 256).rows
        if row.fact_row.stock_code == target_code
    )
    assert target_row.evaluation.technical_truth == "no_match"
    assert target_row.evaluation.volatility_truth == "match"
    assert target_row.volatility_entry.evidence.bandwidth.value == observed_bandwidth
    assert target_row.evaluation.composite_truth == "match"
    assert target_row.evaluation.visible is True

    # 實際 AND 全母體結果無入選列；同一真 row 的 component truths 在 AND context
    # 合併後必為 no_match 且不可見。
    assert and_result.visible_count == 0
    assert dict(and_result.counts.composite_truth_counts) == {
        "match": 0,
        "no_match": 257,
        "unknown": 0,
        "not_applicable": 0,
        "not_evaluated": 1,
    }
    and_context = composite.prepare_composite_evaluation_context_v1(and_query)
    and_target_evaluation = composite.evaluate_composite_predicate_v1(
        and_context,
        technical_truth=target_row.evaluation.technical_truth,
        ma_truth=target_row.evaluation.ma_truth,
        kdj_truth=target_row.evaluation.kdj_truth,
        volatility_truth=target_row.evaluation.volatility_truth,
        technical_status=composite._fact_technical_status(target_row.fact_row),
        hard_eligible=target_row.evaluation.hard_eligible,
    )
    assert and_target_evaluation.technical_truth == "no_match"
    assert and_target_evaluation.volatility_truth == "match"
    assert and_target_evaluation.composite_truth == "no_match"
    assert and_target_evaluation.visible is False
