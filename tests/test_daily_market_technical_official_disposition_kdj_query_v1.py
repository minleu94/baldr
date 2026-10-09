"""F03 KDJ composite request/query leaf 的純契約測試，不代表 full-N 資格。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_official_disposition_kdj_query_v1 as query_module
from app_module.daily_market_technical_kdj_evidence_v1 import (
    KDJ_METHOD_IDENTITY_SHA256_V1,
    KDJ_METHOD_ID_V1,
    KDJ_METHOD_VERSION_V1,
    DailyMarketTechnicalKDJDayV1,
    DailyMarketTechnicalKDJEvidenceV1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
)
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DailyMarketTechnicalUniverseKDJCompactEntryV1,
    DailyMarketTechnicalUniverseKDJSourceRequestV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
    DailyMarketTechnicalUniverseV4Query,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION = date(2026, 10, 8)
_CUTOFF = datetime.combine(_DECISION, time(16, 0), tzinfo=_TAIPEI)
_RULE_KEYS = ("r1", "r2", "r3", "r4", "r5")


def _sha(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_body(payload: dict[str, object], identity_key: str) -> str:
    return _sha({key: value for key, value in payload.items() if key != identity_key})


def _ma_source_request(root: Path) -> DailyMarketTechnicalMaAlignmentSourceRequestV1:
    return DailyMarketTechnicalMaAlignmentSourceRequestV1(
        bundle_output_root=str(root),
        bundle_identity_sha256=_sha("bundle"),
        manifest_relative_path=f"manifests/{_sha('bundle')}.json",
        expected_manifest_sha256=_sha("manifest"),
        technical_store_output_root=str(root / "technical"),
        generation_identity_sha256=_sha("generation"),
        plan_identity_sha256=_sha("plan-identity"),
        plan_sha256=_sha("plan-bytes"),
        receipt_identity_sha256=_sha("receipt-identity"),
        receipt_sha256=_sha("receipt-bytes"),
        cohort_identity_sha256=_sha("cohort"),
        source_clock_identity_sha256=_sha("source-clock"),
        method_contracts_sha256=_sha("method-contracts"),
        market_assignment_pin_identity_sha256=_sha("market-pin"),
        official_disposal_pin_identity_sha256=_sha("disposal-pin"),
        decision_date=_DECISION,
        decision_cutoff=_CUTOFF.isoformat(),
        declared_count=3,
        included_count=2,
        excluded_count=1,
        source_coverage_status="complete",
        source_coverage_incomplete_reason_count=0,
        technical_receipt_status="complete",
    )


def _f17_query(*, technical_active: bool = False) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    state_filters: list[dict[str, object]] = (
        [{"rule_key": "r1", "states": ["match"]}] if technical_active else []
    )
    technical_body: dict[str, Any] = {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
        "store_output_root": r"C:\synthetic\f17-bundle\technical",
        "generation_identity_sha256": _sha("generation"),
        "plan_identity_sha256": _sha("plan-identity"),
        "plan_sha256": _sha("plan-bytes"),
        "receipt_identity_sha256": _sha("receipt-identity"),
        "receipt_sha256": _sha("receipt-bytes"),
        "receipt_status": "complete",
        "cohort_identity_sha256": _sha("cohort"),
        "source_clock_identity_sha256": _sha("source-clock"),
        "method_contracts_sha256": _sha("method-contracts"),
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
        "state_filters": state_filters,
        "combine_mode": "AND",
        "stock_filter": [],
        "sort_key": "stock_code",
        "descending": False,
        "page_index": 0,
        "page_size": 1,
    }
    technical_body["query_identity_sha256"] = _hash_body(technical_body, "query_identity_sha256")
    technical_query = DailyMarketTechnicalUniverseV4Query.from_dict(technical_body)
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=technical_query,
        decision_cutoff=_CUTOFF,
        bundle_output_root=Path(r"C:\synthetic\f17-bundle"),
        bundle_identity_sha256=_sha("bundle"),
        expected_manifest_sha256=_sha("manifest"),
        market_assignment_pin_identity_sha256=_sha("market-pin"),
        official_disposal_pin_identity_sha256=_sha("disposal-pin"),
        row_scope_filter=("included_processed", "included_pending", "excluded"),
    )


def _ma_query(
    *,
    technical_active: bool = False,
    nested_ma_states: list[str] | None = None,
) -> tuple[DailyMarketTechnicalOfficialDispositionMaQueryV1, DailyMarketTechnicalMaAlignmentSourceRequestV1]:
    root = Path(r"C:\synthetic\f17-bundle")
    source = _ma_source_request(root)
    f17 = _f17_query(technical_active=technical_active)
    body: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
        "f17_query_json": f17.to_json(),
        "ma_alignment_read_session_identity_sha256": _sha("ma-read"),
        "ma_alignment_index_identity_sha256": _sha("ma-index"),
        "ma_source_request_identity_sha256": source.request_identity_sha256,
        "ma_method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "ma_method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "ma_states": nested_ma_states,
        "condition_combine_mode": "AND",
        "unknown_policy": "include",
        "sort_clauses": [{"field": "stock_code", "direction": "asc"}],
    }
    body["query_identity_sha256"] = _hash_body(body, "query_identity_sha256")
    return DailyMarketTechnicalOfficialDispositionMaQueryV1.from_dict(body), source


def _query(
    *,
    technical_active: bool = False,
    ma_states: tuple[str, ...] | None = None,
    kdj_states: tuple[str, ...] | None = None,
    combine: str = "AND",
    unknown_policy: str = "include",
    sort: tuple[query_module.DailyMarketTechnicalOfficialDispositionKDJSortClauseV1, ...] = (),
) -> query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1:
    ma_query, ma_source = _ma_query(technical_active=technical_active)
    kdj_source = DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(ma_source)
    return query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1.create(
        ma_query,
        kdj_source,
        kdj_read_session_identity_sha256=_sha("kdj-read"),
        kdj_index_identity_sha256=_sha("kdj-index"),
        kdj_source_clock_identity_sha256=ma_source.source_clock_identity_sha256,
        ma_states=ma_states,
        kdj_states=kdj_states,
        condition_combine_mode=cast(query_module.CombineMode, combine),
        unknown_policy=cast(query_module.UnknownPolicy, unknown_policy),
        sort_clauses=sort,
    )


def _known_kdj_entry(*, state: str = "match", stock_code: str = "2382") -> DailyMarketTechnicalUniverseKDJCompactEntryV1:
    previous_date = _DECISION - timedelta(days=1)
    previous = DailyMarketTechnicalKDJDayV1(
        feature_date=previous_date,
        source_row_fingerprint_sha256=_sha("row-previous"),
        rsv=Decimal("40"), k=Decimal("30"), d=Decimal("20"), j=Decimal("50"),
    )
    current = DailyMarketTechnicalKDJDayV1(
        feature_date=_DECISION,
        source_row_fingerprint_sha256=_sha("row-current"),
        rsv=Decimal("60"), k=Decimal("45"), d=Decimal("35"), j=Decimal("65"),
    )
    evidence = DailyMarketTechnicalKDJEvidenceV1(
        stock_code=stock_code,
        decision_date=_DECISION,
        decision_cutoff=_CUTOFF,
        source_id="synthetic-kdj-source",
        source_identity="synthetic-source-identity",
        source_clock_sha256=_sha("source-clock"),
        source_pin_sha256=_sha("source-pin"),
        raw_source_window_fingerprint_sha256=_sha("raw-window"),
        snapshot_identity_sha256=_sha("snapshot"),
        state=cast(Any, state),
        reason_codes=(),
        previous=previous,
        current=current,
        input_feature_dates=tuple(_DECISION - timedelta(days=13 - index) for index in range(14)),
        input_row_fingerprints_sha256=tuple(_sha(f"window-{index}") for index in range(14)),
        warmup_required_sessions=14,
        warmup_observed_sessions=14,
        warmup_contiguous=True,
        observed_prefix_contiguous=True,
        method_id=KDJ_METHOD_ID_V1,
        method_version=KDJ_METHOD_VERSION_V1,
    )
    return DailyMarketTechnicalUniverseKDJCompactEntryV1.from_unqualified_evidence(0, evidence)


def _unknown_kdj_entry(*, stock_code: str = "2382") -> DailyMarketTechnicalUniverseKDJCompactEntryV1:
    evidence = DailyMarketTechnicalKDJEvidenceV1(
        stock_code=stock_code,
        decision_date=_DECISION,
        decision_cutoff=_CUTOFF,
        source_id="synthetic-kdj-source",
        source_identity="synthetic-source-identity",
        source_clock_sha256=_sha("source-clock"),
        source_pin_sha256=_sha("source-pin"),
        raw_source_window_fingerprint_sha256=_sha("raw-window"),
        snapshot_identity_sha256=_sha("snapshot"),
        state="unknown",
        reason_codes=("insufficient_observed_window",),
        previous=None,
        current=None,
        input_feature_dates=(),
        input_row_fingerprints_sha256=(),
        warmup_required_sessions=14,
        warmup_observed_sessions=0,
        warmup_contiguous=False,
        observed_prefix_contiguous=True,
        method_id=KDJ_METHOD_ID_V1,
        method_version=KDJ_METHOD_VERSION_V1,
    )
    return DailyMarketTechnicalUniverseKDJCompactEntryV1.from_unqualified_evidence(0, evidence)


def _expect_code(code: str, action: object) -> None:
    assert callable(action)
    with pytest.raises(query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1Error) as raised:
        cast(Any, action)()
    assert raised.value.code == code


def test_canonical_query_and_page_request_keep_page_out_of_global_identity() -> None:
    query = _query(ma_states=("match", "unknown"), kdj_states=("match",))
    reordered_input = _query(ma_states=("unknown", "match"), kdj_states=("match",))
    assert reordered_input.query_identity_sha256 == query.query_identity_sha256
    loaded = query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1.from_json(query.to_json())
    assert loaded == query
    payload = query.to_dict()
    assert payload["verification_status"] == "request_only"
    assert payload["source_available_at"] is None
    assert payload["availability_status"] == "unknown"
    assert payload["historical_pit_eligible"] is False
    assert payload["reader_qualified"] is False
    assert payload["kdj_method_id"] == KDJ_METHOD_ID_V1
    assert payload["kdj_method_version"] == KDJ_METHOD_VERSION_V1
    assert payload["kdj_method_identity_sha256"] == KDJ_METHOD_IDENTITY_SHA256_V1

    first = query_module.DailyMarketTechnicalOfficialDispositionKDJPageRequestV1.create(
        query, page_index=0, page_size=128,
    )
    later = query_module.DailyMarketTechnicalOfficialDispositionKDJPageRequestV1.create(
        query, page_index=1, page_size=128,
    )
    assert first.query.query_identity_sha256 == later.query.query_identity_sha256 == query.query_identity_sha256
    assert first.request_identity_sha256 != later.request_identity_sha256
    assert query_module.DailyMarketTechnicalOfficialDispositionKDJPageRequestV1.from_json(later.to_json()) == later


def test_nested_ma_source_must_be_neutral_and_source_pins_must_match() -> None:
    nonneutral, source = _ma_query(nested_ma_states=["match"])
    kdj_source = DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(source)
    _expect_code("nested_ma_query_not_neutral", lambda: query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1.create(
        nonneutral, kdj_source,
        kdj_read_session_identity_sha256=_sha("read"),
        kdj_index_identity_sha256=_sha("index"),
        kdj_source_clock_identity_sha256=source.source_clock_identity_sha256,
    ))

    ma_query, source = _ma_query()
    kdj_source = DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(source)
    _expect_code("source_clock_mismatch", lambda: query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1.create(
        ma_query, kdj_source,
        kdj_read_session_identity_sha256=_sha("read"),
        kdj_index_identity_sha256=_sha("index"),
        kdj_source_clock_identity_sha256=_sha("wrong-source-clock"),
    ))

    altered_source = replace(source, expected_manifest_sha256=_sha("other-manifest"))
    altered_kdj_source = DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(altered_source)
    _expect_code("source_scope_mismatch", lambda: query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1.create(
        ma_query, altered_kdj_source,
        kdj_read_session_identity_sha256=_sha("read"),
        kdj_index_identity_sha256=_sha("index"),
        kdj_source_clock_identity_sha256=source.source_clock_identity_sha256,
    ))


def test_direct_construction_revalidates_rehashed_semantics() -> None:
    query = _query(kdj_states=("match",))

    bad_states = query.to_dict()
    bad_states["kdj_states"] = ["invented"]
    bad_states["query_identity_sha256"] = _hash_body(bad_states, "query_identity_sha256")
    _expect_code("kdj_states_invalid", lambda: query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1.from_dict(bad_states))
    _expect_code("kdj_states_invalid", lambda: replace(
        query,
        kdj_states=("invented",),
        query_identity_sha256=cast(str, bad_states["query_identity_sha256"]),
    ))

    ordered_query = _query(kdj_states=("match", "unknown"))
    reordered = ordered_query.to_dict()
    reordered["kdj_states"] = ["unknown", "match"]
    reordered["query_identity_sha256"] = _hash_body(reordered, "query_identity_sha256")
    _expect_code("kdj_states_noncanonical", lambda: replace(
        ordered_query,
        kdj_states=("unknown", "match"),
        query_identity_sha256=cast(str, reordered["query_identity_sha256"]),
    ))

    bad_combine = query.to_dict()
    bad_combine["condition_combine_mode"] = "OR"
    bad_combine["query_identity_sha256"] = _hash_body(bad_combine, "query_identity_sha256")
    _expect_code("condition_combine_mode_not_canonical", lambda: replace(
        query,
        condition_combine_mode="OR",
        query_identity_sha256=cast(str, bad_combine["query_identity_sha256"]),
    ))

    bad_clock = query.to_dict()
    bad_clock["kdj_source_clock_identity_sha256"] = _sha("other-clock")
    bad_clock["query_identity_sha256"] = _hash_body(bad_clock, "query_identity_sha256")
    _expect_code("source_clock_mismatch", lambda: replace(
        query,
        kdj_source_clock_identity_sha256=cast(str, bad_clock["kdj_source_clock_identity_sha256"]),
        query_identity_sha256=cast(str, bad_clock["query_identity_sha256"]),
    ))

    unsupported_clause = query_module.DailyMarketTechnicalOfficialDispositionKDJSortClauseV1(
        "arbitrary_private_field", "asc",
    )
    bad_sort = query.to_dict()
    bad_sort["sort_clauses"] = [unsupported_clause.to_dict()]
    bad_sort["query_identity_sha256"] = _hash_body(bad_sort, "query_identity_sha256")
    _expect_code("sort_field_unsupported", lambda: replace(
        query,
        sort_clauses=(unsupported_clause,),
        query_identity_sha256=cast(str, bad_sort["query_identity_sha256"]),
    ))


def test_active_group_canonicalization_and_unknown_only_requires_a_group() -> None:
    browse = _query(combine="OR", unknown_policy="include")
    assert browse.active_group_count == 0
    assert browse.condition_combine_mode == "AND"
    assert browse.unknown_policy == "include"
    one_group = _query(kdj_states=("match",), combine="OR")
    assert one_group.active_group_count == 1
    assert one_group.condition_combine_mode == "AND"
    technical_only = _query(technical_active=True, combine="OR")
    assert technical_only.active_group_count == 1
    assert technical_only.condition_combine_mode == "AND"
    _expect_code("unknown_only_without_condition", lambda: _query(unknown_policy="only"))

    three_groups = _query(
        technical_active=True,
        ma_states=("match",),
        kdj_states=("unknown",),
        combine="OR",
        unknown_policy="only",
    )
    assert three_groups.active_group_count == 3
    assert three_groups.condition_combine_mode == "OR"
    assert three_groups.unknown_policy == "only"


def test_kdj_predicate_uses_typed_evidence_and_rejects_cross_source_facts() -> None:
    query = _query(kdj_states=("match",))
    entry = _known_kdj_entry(state="match")
    assert query_module.evaluate_kdj_group_v1(
        query, entry, stock_code="2382", expected_snapshot_identity_sha256=_sha("snapshot"),
    ) == "match"

    no_match_query = _query(kdj_states=("no_match",))
    assert query_module.evaluate_kdj_group_v1(
        no_match_query, entry, stock_code="2382", expected_snapshot_identity_sha256=_sha("snapshot"),
    ) == "no_match"
    unknown_query = _query(kdj_states=("match",))
    unknown = _unknown_kdj_entry()
    assert query_module.evaluate_kdj_group_v1(
        unknown_query, unknown, stock_code="2382", expected_snapshot_identity_sha256=_sha("snapshot"),
    ) == "unknown"

    _expect_code("predicate_source_or_cutoff_mismatch", lambda: query_module.evaluate_kdj_group_v1(
        query, entry, stock_code="2330", expected_snapshot_identity_sha256=_sha("snapshot"),
    ))
    _expect_code("predicate_source_or_cutoff_mismatch", lambda: query_module.evaluate_kdj_group_v1(
        query, entry, stock_code="2382", expected_snapshot_identity_sha256=_sha("other-snapshot"),
    ))


def test_composite_truth_keeps_hard_gate_and_audit_visibility_separate() -> None:
    or_query = _query(
        technical_active=True,
        ma_states=("match",),
        kdj_states=("match",),
        combine="OR",
    )
    rescued_unknown = query_module.evaluate_composite_v1(
        or_query,
        technical_truth="no_match",
        ma_truth="no_match",
        kdj_truth="match",
        hard_eligible=True,
        audit_visible=True,
    )
    assert rescued_unknown.composite_truth == "match"
    assert rescued_unknown.predicate_candidate is True
    assert rescued_unknown.visible is True

    hard_excluded = query_module.evaluate_composite_v1(
        or_query,
        technical_truth="match",
        ma_truth="no_match",
        kdj_truth="match",
        hard_eligible=False,
        audit_visible=True,
    )
    assert hard_excluded.composite_truth == "not_evaluated"
    assert hard_excluded.policy_included is False
    assert hard_excluded.predicate_candidate is False
    assert hard_excluded.visible is False

    browse = _query()
    audit_row = query_module.evaluate_composite_v1(
        browse,
        technical_truth="not_applicable",
        ma_truth="not_applicable",
        kdj_truth="not_applicable",
        hard_eligible=False,
        audit_visible=True,
    )
    assert audit_row.composite_truth == "not_applicable"
    assert audit_row.visible is True
    assert audit_row.predicate_candidate is False


@pytest.mark.parametrize(
    ("policy", "truth", "expected"),
    [
        ("include", "match", True),
        ("include", "unknown", True),
        ("exclude", "match", True),
        ("exclude", "unknown", False),
        ("only", "match", False),
        ("only", "unknown", True),
    ],
)
def test_unknown_policy_applies_only_to_active_eligible_truth(
    policy: str, truth: str, expected: bool,
) -> None:
    query = _query(kdj_states=("match",), unknown_policy=policy)
    result = query_module.evaluate_composite_v1(
        query,
        technical_truth="not_applicable",
        ma_truth="not_applicable",
        kdj_truth=cast(query_module.KDJTruth, truth),
        hard_eligible=True,
        audit_visible=True,
    )
    assert result.policy_included is expected
    assert result.visible is expected


def test_page_request_rejects_bool_and_out_of_range_paging() -> None:
    query = _query()
    for page_index, page_size in ((True, 10), (0, True), (-1, 10), (0, 257)):
        _expect_code("page_bounds_invalid", lambda page_index=page_index, page_size=page_size:
            query_module.DailyMarketTechnicalOfficialDispositionKDJPageRequestV1.create(
                query, page_index=cast(int, page_index), page_size=cast(int, page_size),
            ))


def _sort_key(
    query: query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1,
    stock_code: str,
    value: Decimal | None,
) -> query_module.DailyMarketTechnicalOfficialDispositionKDJSortKeyV1:
    return query_module.DailyMarketTechnicalOfficialDispositionKDJSortKeyV1(
        query_identity_sha256=query.query_identity_sha256,
        stock_code=stock_code,
        sort_values=(query_module.DailyMarketTechnicalOfficialDispositionKDJSortValueV1(
            "kdj_current.j", "desc", value,
        ), query_module.DailyMarketTechnicalOfficialDispositionKDJSortValueV1(
            "stock_code", "asc", stock_code,
        )),
        fact_row_sha256=_sha(f"row-{stock_code}"),
        technical_snapshot_identity_sha256=_sha(f"snapshot-{stock_code}"),
        ma_evidence_identity_sha256=_sha(f"ma-{stock_code}"),
        kdj_compact_identity_sha256=_sha(f"kdj-{stock_code}"),
    )


def test_global_sort_is_stable_with_nulls_last_in_both_directions() -> None:
    clauses = (
        query_module.DailyMarketTechnicalOfficialDispositionKDJSortClauseV1("kdj_current.j", "desc"),
        query_module.DailyMarketTechnicalOfficialDispositionKDJSortClauseV1("stock_code", "asc"),
    )
    query = _query(kdj_states=("match",), sort=clauses)
    keys = (
        _sort_key(query, "2382", Decimal("80")),
        _sort_key(query, "2330", None),
        _sort_key(query, "2317", Decimal("80")),
        _sort_key(query, "2454", Decimal("65")),
    )
    ordered = query_module.sort_composite_keys_v1(query, keys)
    assert tuple(item.stock_code for item in ordered) == ("2317", "2382", "2454", "2330")


def test_sort_rejects_field_type_duplicate_and_budget_before_ordering(monkeypatch: pytest.MonkeyPatch) -> None:
    clauses = (
        query_module.DailyMarketTechnicalOfficialDispositionKDJSortClauseV1("kdj_current.j", "desc"),
        query_module.DailyMarketTechnicalOfficialDispositionKDJSortClauseV1("stock_code", "asc"),
    )
    query = _query(kdj_states=("match",), sort=clauses)
    wrong_type = query_module.DailyMarketTechnicalOfficialDispositionKDJSortKeyV1(
        query_identity_sha256=query.query_identity_sha256,
        stock_code="2382",
        sort_values=(query_module.DailyMarketTechnicalOfficialDispositionKDJSortValueV1(
            "kdj_current.j", "desc", "80",
        ), query_module.DailyMarketTechnicalOfficialDispositionKDJSortValueV1(
            "stock_code", "asc", "2382",
        )),
        fact_row_sha256=_sha("fact"),
        technical_snapshot_identity_sha256=None,
        ma_evidence_identity_sha256=None,
        kdj_compact_identity_sha256=None,
    )
    _expect_code("sort_value_field_type_invalid", lambda: query_module.sort_composite_keys_v1(query, (wrong_type,)))
    duplicate = _sort_key(query, "2382", Decimal("80"))
    _expect_code("sort_duplicate_stock", lambda: query_module.sort_composite_keys_v1(query, (duplicate, duplicate)))

    monkeypatch.setattr(query_module, "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_SORT_PROJECTION_BYTES", 1)
    _expect_code("sort_projection_byte_limit", lambda: query_module.sort_composite_keys_v1(
        query, (_sort_key(query, "2382", Decimal("80")),),
    ))


def test_sort_cancellation_and_invalid_scalars_fail_closed() -> None:
    query = _query(kdj_states=("match",))
    _expect_code("sort_value_scalar_invalid", lambda: query_module.DailyMarketTechnicalOfficialDispositionKDJSortValueV1(
        "kdj_current.j", "asc", cast(Any, 1.0),
    ))
    _expect_code("sort_value_integer_bounds_invalid", lambda: query_module.DailyMarketTechnicalOfficialDispositionKDJSortValueV1(
        "raw_row_count", "asc", 1 << 128,
    ))
    _expect_code("sort_value_text_limit", lambda: query_module.DailyMarketTechnicalOfficialDispositionKDJSortValueV1(
        "stock_code", "asc", "X" * 257,
    ))
    _expect_code("cancelled", lambda: query_module.sort_composite_keys_v1(
        query, (), cancel_callback=lambda: True,
    ))


def test_json_parser_rejects_duplicate_float_deep_and_oversized_integer_tokens() -> None:
    parser = query_module.DailyMarketTechnicalOfficialDispositionKDJQueryV1.from_json
    _expect_code("duplicate_json_key", lambda: parser('{"x":1,"x":1}'))
    _expect_code("float_forbidden", lambda: parser('{"x":1.25}'))
    _expect_code("json_depth_limit", lambda: parser("[" * 33 + "0" + "]" * 33))
    _expect_code("integer_bounds_invalid", lambda: parser('{"x":' + "9" * 39 + '}'))


def test_query_total_budget_includes_nested_json_escaping_and_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    query = _query(kdj_states=("match",))
    canonical = query.to_json().encode("utf-8")
    assert b'\\"schema_version\\"' in canonical
    monkeypatch.setattr(
        query_module,
        "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES",
        len(canonical) - 1,
    )
    _expect_code("query_byte_limit", query.to_json)
