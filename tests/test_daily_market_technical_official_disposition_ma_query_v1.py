"""F17 與 MA 同母體查詢的 canonical、三值組合及發行錨點測試。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

import app_module.daily_market_technical_official_disposition_ma_query_v1 as ma_module
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionFactRowV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionMembershipCountsV1,
    DailyMarketTechnicalOfficialDispositionQueryCountsV1,
    DailyMarketTechnicalOfficialDispositionRuleStateCountsV1,
    DailyMarketTechnicalOfficialDispositionTruthCountsV1,
)
import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader_module
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
    DailyMarketTechnicalOfficialDispositionSortValueV1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
    DailyMarketTechnicalUniverseV4Counts,
    DailyMarketTechnicalUniverseV4Query,
)


_DECISION = date(2026, 10, 7)
_CUTOFF = datetime.fromisoformat("2026-10-07T16:00:00+08:00")
_RULE_KEYS = ("r1", "r2", "r3", "r4", "r5")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _p01_query(*, rule_filters: tuple[dict[str, object], ...] = ()) -> DailyMarketTechnicalUniverseV4Query:
    body: dict[str, Any] = {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
        "store_output_root": r"C:\synthetic\technical-store",
        "generation_identity_sha256": "a" * 64,
        "plan_identity_sha256": "b" * 64,
        "plan_sha256": "c" * 64,
        "receipt_identity_sha256": "d" * 64,
        "receipt_sha256": "e" * 64,
        "receipt_status": "complete",
        "cohort_identity_sha256": "f" * 64,
        "source_clock_identity_sha256": "1" * 64,
        "method_contracts_sha256": "2" * 64,
        "universe_id": "synthetic-universe",
        "population_version": "fixture-v1",
        "decision_date": _DECISION.isoformat(),
        "declared_count": 3,
        "included_count": 2,
        "excluded_count": 1,
        "segment_count": 1,
        "counts": {
            "declared_count": 3,
            "included_count": 2,
            "excluded_count": 1,
            "processed_count": 2,
            "pending_count": 0,
            "missing_data_count": 0,
            "missing_data_pending_count": 0,
        },
        "method_rule_keys": list(_RULE_KEYS),
        "state_filters": list(rule_filters),
        "combine_mode": "AND",
        "stock_filter": [],
        "sort_key": "stock_code",
        "descending": False,
        "page_index": 0,
        "page_size": 1,
    }
    body["query_identity_sha256"] = _sha(body)
    return DailyMarketTechnicalUniverseV4Query.from_dict(body)


def _f17_query(
    *,
    rule_filters: tuple[dict[str, object], ...] = (),
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...] = (),
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=_p01_query(rule_filters=rule_filters),
        decision_cutoff=_CUTOFF,
        bundle_output_root=Path(r"C:\synthetic\f17-bundle"),
        bundle_identity_sha256="3" * 64,
        expected_manifest_sha256="4" * 64,
        market_assignment_pin_identity_sha256="5" * 64,
        official_disposal_pin_identity_sha256="6" * 64,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        sort_clauses=sort_clauses,
    )


def _ma_query(
    *,
    rule_filters: tuple[dict[str, object], ...] = (),
    states: list[str] | None = None,
    combine: str = "AND",
    unknown_policy: str = "include",
    sorts: list[dict[str, str]] | None = None,
) -> ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1:
    active_group_count = int(bool(rule_filters)) + int(states is not None)
    normalized_combine = combine if active_group_count == 2 else "AND"
    normalized_unknown_policy = "include" if active_group_count == 0 else unknown_policy
    body: dict[str, object] = {
        "schema_version": ma_module.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
        "f17_query_json": _f17_query(rule_filters=rule_filters).to_json(),
        "ma_alignment_read_session_identity_sha256": "7" * 64,
        "ma_alignment_index_identity_sha256": "8" * 64,
        "ma_source_request_identity_sha256": "9" * 64,
        "ma_method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "ma_method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "ma_states": states,
        "condition_combine_mode": normalized_combine,
        "unknown_policy": normalized_unknown_policy,
        "sort_clauses": sorts or [{"field": "stock_code", "direction": "asc"}],
    }
    return ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1.from_dict({
        **body,
        "query_identity_sha256": _sha(body),
    })


def test_query_and_page_request_keep_global_identity_separate() -> None:
    query = _ma_query(states=["match", "unknown"])
    loaded = ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(query.to_json())
    assert loaded == query

    first = ma_module.DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=0, page_size=128,
    )
    later = ma_module.DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=1, page_size=128,
    )
    assert first.query.query_identity_sha256 == later.query.query_identity_sha256 == query.query_identity_sha256
    assert first.request_identity_sha256 != later.request_identity_sha256
    assert ma_module.DailyMarketTechnicalOfficialDispositionMaPageRequestV1.from_json(
        later.to_json()
    ) == later


@pytest.mark.parametrize(
    ("states", "policy", "expected_code"),
    [
        ([], "include", "ma_states_invalid"),
        (None, "only", "unknown_only_without_condition"),
    ],
)
def test_query_decoder_rejects_empty_state_or_unknown_only_without_conditions(
    states: list[str] | None,
    policy: str,
    expected_code: str,
) -> None:
    body: dict[str, object] = {
        "schema_version": ma_module.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
        "f17_query_json": _f17_query().to_json(),
        "ma_alignment_read_session_identity_sha256": "7" * 64,
        "ma_alignment_index_identity_sha256": "8" * 64,
        "ma_source_request_identity_sha256": "9" * 64,
        "ma_method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "ma_method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "ma_states": states,
        "condition_combine_mode": "OR",
        "unknown_policy": policy,
        "sort_clauses": [{"field": "stock_code", "direction": "asc"}],
    }
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match=expected_code):
        ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1.from_dict({
            **body,
            "query_identity_sha256": _sha(body),
        })


def test_inactive_combine_and_unknown_options_have_one_canonical_identity() -> None:
    browse_and = _ma_query(combine="AND", unknown_policy="include")
    browse_or = _ma_query(combine="OR", unknown_policy="exclude")
    assert browse_and.to_json() == browse_or.to_json()
    assert browse_or.condition_combine_mode == "AND"
    assert browse_or.unknown_policy == "include"

    ma_only_and = _ma_query(states=["match"], combine="AND")
    ma_only_or = _ma_query(states=["match"], combine="OR")
    assert ma_only_and.query_identity_sha256 == ma_only_or.query_identity_sha256

    rules: tuple[dict[str, object], ...] = ({"rule_key": "r1", "states": ["match"]},)
    technical_only_and = _ma_query(rule_filters=rules, combine="AND")
    technical_only_or = _ma_query(rule_filters=rules, combine="OR")
    assert technical_only_and.query_identity_sha256 == technical_only_or.query_identity_sha256

    both_and = _ma_query(rule_filters=rules, states=["match"], combine="AND")
    both_or = _ma_query(rule_filters=rules, states=["match"], combine="OR")
    assert both_and.query_identity_sha256 != both_or.query_identity_sha256

    noncanonical = ma_only_and.to_dict()
    noncanonical["condition_combine_mode"] = "OR"
    noncanonical.pop("query_identity_sha256")
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="condition_combine_mode_not_canonical"):
        ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1.from_dict({
            **noncanonical,
            "query_identity_sha256": _sha(noncanonical),
        })


def test_query_rejects_nested_f17_page_or_sort_that_would_be_ignored() -> None:
    nested = _f17_query()
    nonneutral = _f17_query(sort_clauses=(
        DailyMarketTechnicalOfficialDispositionSortClauseV1("raw_row_count", "desc"),
    ))
    assert nested.query_identity_sha256 != nonneutral.query_identity_sha256
    body = ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(
        _ma_query().to_json()
    ).to_dict()
    body["f17_query_json"] = nonneutral.to_json()
    body.pop("query_identity_sha256")
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="nested_f17_sort_or_page_not_neutral"):
        ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1.from_dict({
            **body,
            "query_identity_sha256": _sha(body),
        })


def test_kleene_groups_do_not_treat_an_inactive_group_as_true_for_or() -> None:
    empty = _ma_query(combine="OR")
    processed = _FakeFact("processed")
    assert _composite_truth(empty, processed, object(), "match", "match") == "not_applicable"

    ma_only = _ma_query(states=["match"], combine="OR")
    assert _composite_truth(ma_only, processed, object(), "not_applicable", "no_match") == "no_match"

    rules: tuple[dict[str, object], ...] = ({"rule_key": "r1", "states": ["match"]},)
    both_or = _ma_query(rule_filters=rules, states=["match"], combine="OR")
    both_and = _ma_query(rule_filters=rules, states=["match"], combine="AND")
    assert _composite_truth(both_or, processed, object(), "no_match", "unknown") == "unknown"
    assert _composite_truth(both_or, processed, object(), "match", "no_match") == "match"
    assert _composite_truth(both_and, processed, object(), "unknown", "no_match") == "no_match"
    assert _composite_truth(
        both_or, _FakeFact("pending"), None, "match", "match",
    ) == "not_evaluated"


def test_pending_or_excluded_is_not_evaluated_even_when_groups_are_disabled() -> None:
    query = _ma_query()
    pending = _FakeFact("pending")
    excluded = _FakeFact("excluded")
    for fact in (pending, excluded):
        assert reader_module._ma_rule_group_truth(
            query.f17_query, cast(Any, fact), None,
        ) == "not_evaluated"
        assert reader_module._ma_condition_truth(
            query, cast(Any, fact), None,
        ) == "not_evaluated"
        assert _composite_truth(
            query, fact, None, "not_evaluated", "not_evaluated",
        ) == "not_evaluated"
        # 無條件查詢可瀏覽 hard-eligible row，但不可將它算成 predicate match。
        assert reader_module._ma_policy_includes(
            query, "not_evaluated",
        )


def test_visible_rows_are_separate_from_predicate_truth_counts() -> None:
    base = _counts()
    counts = replace(
        base,
        technical_truth_counts=tuple(
            (key, 2 if key == "not_applicable" else 1 if key == "not_evaluated" else 0)
            for key in ma_module._TRUTH_ORDER
        ),
        ma_truth_counts=tuple(
            (key, 2 if key == "unknown" else 1 if key == "not_evaluated" else 0)
            for key in ma_module._TRUTH_ORDER
        ),
        composite_truth_counts=tuple(
            (key, 2 if key == "unknown" else 1 if key == "not_evaluated" else 0)
            for key in ma_module._TRUTH_ORDER
        ),
        eligible_truth_counts=tuple(
            (key, 2 if key == "unknown" else 1 if key == "not_evaluated" else 0)
            for key in ma_module._TRUTH_ORDER
        ),
        hard_eligible_count=3,
        visible_count=3,
        unknown_policy_included_count=0,
        unknown_policy_excluded_count=0,
    )
    assert counts.visible_count == 3
    assert counts.matching_count == 3  # 舊欄位相容別名，語義是可見筆數。
    assert counts.predicate_match_count == 0
    assert counts.predicate_unknown_count == 2
    assert counts.predicate_not_evaluated_count == 1
    assert counts.to_dict()["visible_count"] == 3
    assert counts.to_dict()["predicate_not_evaluated_count"] == 1


def test_unknown_policy_only_never_includes_not_evaluated() -> None:
    query = _ma_query(states=["unknown"], unknown_policy="only")
    assert reader_module._ma_policy_includes(query, "unknown")
    assert not reader_module._ma_policy_includes(query, "match")
    assert not reader_module._ma_policy_includes(query, "not_evaluated")

    browse = _ma_query()
    assert reader_module._ma_policy_includes(browse, "not_evaluated")


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_global_compact_sort_keeps_unknown_last_and_stock_code_ties(direction: str) -> None:
    query = _ma_query(sorts=[
        {"field": "raw_row_count", "direction": direction},
    ])
    keys = (
        _sort_key(query, "1101", 5),
        _sort_key(query, "1102", 5),
        _sort_key(query, "1103", None),
        _sort_key(query, "1104", 2),
    )
    ordered = ma_module.sort_composite_keys_v1(query, keys)
    known = [item for item in ordered if item.sort_values[0].value is not None]
    unknown = [item for item in ordered if item.sort_values[0].value is None]
    assert [item.stock_code for item in ordered] == [item.stock_code for item in known + unknown]
    assert [item.stock_code for item in unknown] == ["1103"]
    tied = [item.stock_code for item in known if item.sort_values[0].value == 5]
    assert tied == ["1101", "1102"]


def test_decimal_sort_is_numeric_and_stock_code_clause_is_only_final_ascending_tiebreak() -> None:
    query = _ma_query(sorts=[{"field": "r1.ratio", "direction": "asc"}])
    keys = (
        _sort_key(query, "1101", Decimal("100")),
        _sort_key(query, "1102", Decimal("9")),
    )
    assert [item.stock_code for item in ma_module.sort_composite_keys_v1(query, keys)] == ["1102", "1101"]

    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="stock_code_tiebreak_invalid"):
        _ma_query(sorts=[{"field": "stock_code", "direction": "desc"}])
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="stock_code_tiebreak_invalid"):
        _ma_query(sorts=[
            {"field": "stock_code", "direction": "asc"},
            {"field": "raw_row_count", "direction": "desc"},
        ])


def test_global_sort_rejects_scalar_type_and_stock_code_value_mismatch() -> None:
    query = _ma_query(sorts=[{"field": "raw_row_count", "direction": "asc"}])
    bad_type = _sort_key(query, "1101", Decimal("9"))
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="sort_key_scalar_invalid"):
        ma_module.sort_composite_keys_v1(query, (bad_type,))

    code_query = _ma_query(sorts=[{"field": "stock_code", "direction": "asc"}])
    wrong_code = _sort_key(code_query, "1101", "9999", stock_code_scalar="9999")
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="sort_key_stock_code_value_mismatch"):
        ma_module.sort_composite_keys_v1(code_query, (wrong_code,))


def test_global_sort_cancel_callback_is_strict_and_cooperative() -> None:
    query = _ma_query()
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="cancel_callback_invalid"):
        ma_module.sort_composite_keys_v1(query, (), cancel_callback=lambda: 1)
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="cancelled"):
        ma_module.sort_composite_keys_v1(query, (), cancel_callback=lambda: True)


def test_global_sort_polls_each_column_partition_and_sort_boundary() -> None:
    query = _ma_query(sorts=[
        {"field": "raw_row_count", "direction": "desc"},
        {"field": "stock_code", "direction": "asc"},
    ])
    keys = tuple(
        _sort_key(query, f"{1000 + index:04d}", index % 17)
        for index in range(600)
    )
    calls = 0

    def never_cancel() -> bool:
        nonlocal calls
        calls += 1
        return False

    ordered = ma_module.sort_composite_keys_v1(query, keys, cancel_callback=never_cancel)
    assert len(ordered) == len(keys)
    # 起始、三個輸入區段、股票碼排序前後、每欄三個分區輪詢與排序前後、終態。
    assert calls == 17

    for cancel_at in (8, 10, 11, 13, 15, 16):
        polled = 0

        def cancel_during_sort() -> bool:
            nonlocal polled
            polled += 1
            return polled == cancel_at

        with pytest.raises(
            ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error,
            match="cancelled",
        ):
            ma_module.sort_composite_keys_v1(query, keys, cancel_callback=cancel_during_sort)
        assert polled == cancel_at


def test_page_entrypoints_check_cancellation_before_request_or_result_access() -> None:
    uninitialized_result = cast(Any, object())
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="cancelled"):
        ma_module.DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1.read_page(
            uninitialized_result,
            0,
            1,
            cancel_callback=lambda: True,
        )
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="cancelled"):
        ma_module.DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1.read_page_request(
            uninitialized_result,
            b"not-json",
            cancel_callback=lambda: True,
        )

    with pytest.raises(
        ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error,
        match="cancel_callback_invalid",
    ):
        ma_module.DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1.read_page(
            uninitialized_result,
            0,
            1,
            cancel_callback=lambda: 1,
        )

    def broken_callback() -> bool:
        raise RuntimeError("synthetic cancellation callback failure")

    with pytest.raises(
        ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error,
        match="cancel_check_failed",
    ):
        ma_module.DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1.read_page_request(
            uninitialized_result,
            b"not-json",
            cancel_callback=broken_callback,
        )


def test_reader_issued_result_and_page_reject_dataclasses_replace_rehash() -> None:
    query = _ma_query(states=["unknown"])
    counts = _counts()
    key = _sort_key(query, "1101", "1101")
    second_key = _sort_key(query, "1102", "1102")
    pins = _source_pins(query)
    result = ma_module._issue_result_v1(
        query=query,
        counts=counts,
        source_pins=pins,
        ordered_keys=(key, second_key),
        result_status="partial",
        official_source_coverage_status="partial",
        read_session=object(),
    )
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="result_not_reader_issued"):
        replace(result)

    changed_key = replace(key, stock_code="1102", sort_values=(
        DailyMarketTechnicalOfficialDispositionSortValueV1("stock_code", "asc", "1102"),
    ))
    changed_keys = (changed_key,)
    changed_operation = ma_module._result_identity(
        query=query,
        source_pins=pins,
        counts=counts,
        ordered_keys=changed_keys,
        result_status="partial",
        official_coverage_status="partial",
    )
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="result_not_reader_issued"):
        replace(
            result,
            ordered_sort_keys=changed_keys,
            ordered_codes_sha256=_sha(["1102"]),
            operation_identity_sha256=changed_operation,
        )

    changed_eligible_truth = tuple(
        (key_name, 1 if key_name in {"no_match", "unknown"} else 0)
        for key_name in ma_module._TRUTH_ORDER
    )
    changed_composite_truth = tuple(
        (key_name, 1 if key_name in {"no_match", "unknown", "not_evaluated"} else 0)
        for key_name in ma_module._TRUTH_ORDER
    )
    changed_counts = replace(
        counts,
        ma_state_counts=(("match", 1), ("no_match", 0), ("unknown", 1)),
        ma_truth_counts=changed_composite_truth,
        composite_truth_counts=changed_composite_truth,
        eligible_truth_counts=changed_eligible_truth,
        visible_count=1,
        unknown_policy_included_count=1,
    )
    changed_counts_operation = ma_module._result_identity(
        query=query,
        source_pins=pins,
        counts=changed_counts,
        ordered_keys=(key,),
        result_status="partial",
        official_coverage_status="partial",
    )
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="result_not_reader_issued"):
        replace(result, counts=changed_counts, operation_identity_sha256=changed_counts_operation)

    changed_pins = tuple(
        (name, "0" * 64 if name == "p01_read_session_identity_sha256" else value)
        for name, value in pins
    )
    changed_pin_operation = ma_module._result_identity(
        query=query,
        source_pins=changed_pins,
        counts=counts,
        ordered_keys=(key, second_key),
        result_status="partial",
        official_coverage_status="partial",
    )
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="result_not_reader_issued"):
        replace(result, source_pins=changed_pins, operation_identity_sha256=changed_pin_operation)

    request = ma_module.DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=0, page_size=1,
    )
    ma_module._validate_page_request_for_result_v1(result, request)
    other_query = _ma_query(states=["match"])
    other_request = ma_module.DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        other_query, page_index=0, page_size=1,
    )
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="page_request_query_mismatch"):
        ma_module._validate_page_request_for_result_v1(result, other_request)
    out_of_range = ma_module.DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=2, page_size=1,
    )
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="page_request_out_of_range"):
        ma_module._validate_page_request_for_result_v1(result, out_of_range)
    row = _result_row("1101")
    page = ma_module._issue_page_v1(result=result, request=request, rows=(row,))
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="page_not_reader_issued"):
        replace(page)
    changed_row = _result_row("1102")
    changed_rows = (changed_row,)
    changed_page_identity = ma_module._page_identity(
        result=result, request=request, rows=changed_rows,
    )
    with pytest.raises(ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1Error, match="page_not_reader_issued"):
        replace(page, rows=changed_rows, page_identity_sha256=changed_page_identity)

    with pytest.raises(TypeError):
        replace(cast(Any, result._anchor), keys_sha256="b" * 64)
    with pytest.raises(TypeError):
        replace(cast(Any, page._anchor), rows_sha256="c" * 64)


def test_page_materializer_checks_cancel_before_reader_state_and_keeps_error_codes() -> None:
    method = reader_module.DailyMarketTechnicalOfficialDispositionReadSessionV1._materialize_ma_query_page_v1
    with pytest.raises(reader_module.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error, match="cancelled"):
        method(cast(Any, object()), cast(Any, object()), cast(Any, object()), lambda: True)
    with pytest.raises(reader_module.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error, match="cancel_callback_invalid"):
        method(cast(Any, object()), cast(Any, object()), cast(Any, object()), lambda: 1)

    def broken_callback() -> bool:
        raise RuntimeError("synthetic callback failure")

    with pytest.raises(reader_module.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error, match="cancel_callback_failed"):
        method(cast(Any, object()), cast(Any, object()), cast(Any, object()), broken_callback)


class _FakeFact:
    def __init__(self, technical_status: str) -> None:
        self._technical_status = technical_status

    def to_dict(self) -> dict[str, str]:
        return {"technical_status": self._technical_status}


def _composite_truth(
    query: ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1,
    fact: object,
    row: object | None,
    technical_truth: str,
    ma_truth: str,
) -> str:
    return cast(str, reader_module._ma_composite_truth(
        query,
        cast(Any, fact),
        cast(Any, row),
        cast(Any, technical_truth),
        cast(Any, ma_truth),
    ))


def _sort_key(
    query: ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1,
    code: str,
    value: object,
    *,
    stock_code_scalar: str | None = None,
) -> ma_module.DailyMarketTechnicalOfficialDispositionMaSortKeyV1:
    values: list[DailyMarketTechnicalOfficialDispositionSortValueV1] = []
    for clause in query.sort_clauses:
        scalar = (
            (stock_code_scalar or code)
            if clause.field == "stock_code"
            else value
        )
        if clause.field == "ma_alignment_state" and scalar == "unknown":
            scalar = None
        values.append(DailyMarketTechnicalOfficialDispositionSortValueV1(
            clause.field, clause.direction, cast(Any, scalar),
        ))
    return ma_module.DailyMarketTechnicalOfficialDispositionMaSortKeyV1(
        query_identity_sha256=query.query_identity_sha256,
        stock_code=code,
        sort_values=tuple(values),
        fact_row_sha256="a" * 64,
        ma_evidence_identity_sha256="b" * 64,
        technical_snapshot_identity_sha256="c" * 64,
        technical_source_identity="sqlite.daily_prices",
    )


def _counts() -> ma_module.DailyMarketTechnicalOfficialDispositionMaCountsV1:
    population = DailyMarketTechnicalUniverseV4Counts(3, 2, 1, 2, 0, 0, 0)
    base = DailyMarketTechnicalOfficialDispositionQueryCountsV1(
        population=population,
        unknown_rule_stock_count=0,
        rule_state_counts=tuple(
            DailyMarketTechnicalOfficialDispositionRuleStateCountsV1(key, 2, 0, 0)
            for key in _RULE_KEYS
        ),
        market_state_counts=(("assigned_twse", 2), ("unknown", 1)),
        disposal_state_counts=(("reported_active", 2), ("unknown", 1)),
        truth_counts=(),
        membership_counts=(),
        matching_count=1,
    )
    return ma_module.DailyMarketTechnicalOfficialDispositionMaCountsV1(
        base_f17_counts=base,
        ma_state_counts=(("match", 0), ("no_match", 0), ("unknown", 2)),
        technical_truth_counts=tuple((key, 2 if key == "not_applicable" else 1 if key == "not_evaluated" else 0) for key in ma_module._TRUTH_ORDER),
        ma_truth_counts=tuple((key, 2 if key == "unknown" else 1 if key == "not_evaluated" else 0) for key in ma_module._TRUTH_ORDER),
        composite_truth_counts=tuple((key, 2 if key == "unknown" else 1 if key == "not_evaluated" else 0) for key in ma_module._TRUTH_ORDER),
        eligible_truth_counts=tuple((key, 2 if key == "unknown" else 0) for key in ma_module._TRUTH_ORDER),
        hard_eligible_count=2,
        visible_count=2,
        unknown_policy_included_count=2,
        unknown_policy_excluded_count=0,
    )


def _source_pins(
    query: ma_module.DailyMarketTechnicalOfficialDispositionMaQueryV1,
) -> tuple[tuple[str, str], ...]:
    f17 = query.f17_query
    values = {
        "bundle_output_root": f17.bundle_output_root,
        "bundle_identity_sha256": f17.bundle_identity_sha256,
        "bundle_manifest_sha256": f17.expected_manifest_sha256,
        "p01_read_session_identity_sha256": "a" * 64,
        "p01_selection_identity_sha256": "b" * 64,
        "p01_query_spec_identity_sha256": "c" * 64,
        "p01_generation_identity_sha256": "d" * 64,
        "p01_plan_identity_sha256": "e" * 64,
        "p01_plan_sha256": "f" * 64,
        "p01_receipt_identity_sha256": "1" * 64,
        "p01_receipt_sha256": "2" * 64,
        "p01_cohort_identity_sha256": "3" * 64,
        "p01_source_clock_identity_sha256": "4" * 64,
        "p01_method_contracts_sha256": "5" * 64,
        "ma_read_session_identity_sha256": query.ma_alignment_read_session_identity_sha256,
        "ma_index_identity_sha256": query.ma_alignment_index_identity_sha256,
        "ma_source_request_identity_sha256": query.ma_source_request_identity_sha256,
        "ma_index_source_clock_identity_sha256": "6" * 64,
        "market_assignment_pin_identity_sha256": f17.market_assignment_pin_identity_sha256,
        "official_disposal_pin_identity_sha256": f17.official_disposal_pin_identity_sha256,
        "decision_date": f17.decision_date.isoformat(),
        "decision_cutoff": f17.decision_cutoff.isoformat(),
        "ma_method_id": query.ma_method_id,
        "ma_method_version": query.ma_method_version,
    }
    return tuple((key, values[key]) for key in ma_module._SOURCE_PIN_KEYS)


def _result_row(code: str) -> ma_module.DailyMarketTechnicalOfficialDispositionMaResultRowV1:
    fact = DailyMarketTechnicalOfficialDispositionFactRowV1(
        body_json=_canonical({"stock_code": code}),
        stock_code=code,
        cohort_role="included",
    )
    evaluation = DailyMarketTechnicalOfficialDispositionFilterEvaluationV1(
        stock_code=code,
        row_scope="included_processed",
        row_scope_match=True,
        stock_filter_match=True,
        market_assignment_match=True,
        market_assignment_truth="match",
        official_disposal_match=True,
        official_disposal_truth="match",
    )
    return ma_module.DailyMarketTechnicalOfficialDispositionMaResultRowV1(
        fact_row=fact,
        technical_row=None,
        ma_entry=None,
        filter_evaluation=evaluation,
        technical_condition_truth="match",
        ma_condition_truth="not_applicable",
        composite_condition_truth="match",
        hard_filter_match=True,
        included_by_unknown_policy=True,
        row_identity_sha256="d" * 64,
    )
