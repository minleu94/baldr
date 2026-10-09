"""F06 三群 canonical query 的純 DTO、predicate 與未核排序契約測試。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

import app_module.daily_market_technical_official_disposition_volatility_query_v1 as volatility_query_module
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
    DailyMarketTechnicalUniverseV4Query,
)
from app_module.daily_market_technical_volatility_evidence_v1 import (
    ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
    ATR14_SMA_METHOD_ID_V1,
    ATR14_SMA_METHOD_VERSION_V1,
    ATR14_SMA_REQUIRED_RAW_ROWS_V1,
    BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
    BOLLINGER_BANDWIDTH_METHOD_ID_V1,
    BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
    BOLLINGER_BANDWIDTH_WINDOW_V1,
    DailyMarketTechnicalVolatilityMeasureV1,
    VOLATILITY_EVIDENCE_SCHEMA_V1,
)


_DECISION = date(2026, 10, 7)
_CUTOFF = datetime.fromisoformat("2026-10-07T16:00:00+08:00")
_SOURCE_CLOCK = "1" * 64
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
        "source_clock_identity_sha256": _SOURCE_CLOCK,
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


def _f17_query(*, rules: bool = True) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    rule_filters: tuple[dict[str, object], ...]
    if rules:
        rule_filters = ({"rule_key": "r1", "states": ["match"]},)
    else:
        rule_filters = ()
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=_p01_query(rule_filters=rule_filters),
        decision_cutoff=_CUTOFF,
        bundle_output_root=Path(r"C:\synthetic\f17-bundle"),
        bundle_identity_sha256="3" * 64,
        expected_manifest_sha256="4" * 64,
        market_assignment_pin_identity_sha256="5" * 64,
        official_disposal_pin_identity_sha256="6" * 64,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
    )


def _ma_source_query(
    *,
    rules: bool = True,
    states: list[str] | None = None,
    combine: str = "AND",
    policy: str = "include",
    sorts: list[dict[str, str]] | None = None,
) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
    rule_filters = ({"rule_key": "r1", "states": ["match"]},) if rules else ()
    body: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
        "f17_query_json": _f17_query(rules=rules).to_json(),
        "ma_alignment_read_session_identity_sha256": "7" * 64,
        "ma_alignment_index_identity_sha256": "8" * 64,
        "ma_source_request_identity_sha256": "9" * 64,
        "ma_method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "ma_method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "ma_states": states,
        "condition_combine_mode": combine,
        "unknown_policy": policy,
        "sort_clauses": sorts or [{"field": "stock_code", "direction": "asc"}],
    }
    active_count = int(rules) + int(states is not None)
    body["condition_combine_mode"] = combine if active_count == 2 else "AND"
    body["unknown_policy"] = policy if active_count else "include"
    return DailyMarketTechnicalOfficialDispositionMaQueryV1.from_dict({
        **body,
        "query_identity_sha256": _sha(body),
    })


def _query(
    *,
    rules: bool = True,
    ma_states: tuple[str, ...] | None = None,
    bandwidth_min: Decimal | None = None,
    bandwidth_max: Decimal | None = None,
    atr_min: Decimal | None = None,
    atr_max: Decimal | None = None,
    combine: str = "AND",
    policy: str = "include",
    sorts: tuple[volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1, ...] = (),
    source_clock: str = _SOURCE_CLOCK,
) -> volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
    return volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.create(
        _ma_source_query(rules=rules),
        volatility_read_session_identity_sha256="a" * 64,
        volatility_index_identity_sha256="b" * 64,
        volatility_source_request_identity_sha256="c" * 64,
        volatility_source_clock_identity_sha256=source_clock,
        ma_states=ma_states,  # type: ignore[arg-type]
        bandwidth_min_pct=bandwidth_min,
        bandwidth_max_pct=bandwidth_max,
        atr14_min_pct=atr_min,
        atr14_max_pct=atr_max,
        condition_combine_mode=combine,  # type: ignore[arg-type]
        unknown_policy=policy,  # type: ignore[arg-type]
        sort_clauses=sorts,
    )


def _measure(*, method: str, value: Decimal | None, normalized: Decimal | None = None, state: str = "observed") -> DailyMarketTechnicalVolatilityMeasureV1:
    if method == "bandwidth":
        method_id = BOLLINGER_BANDWIDTH_METHOD_ID_V1
        method_version = BOLLINGER_BANDWIDTH_METHOD_VERSION_V1
        method_identity = BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1
        unit = "percent"
        normalized_unit = None
        required_rows = BOLLINGER_BANDWIDTH_WINDOW_V1
        warmup_required = BOLLINGER_BANDWIDTH_WINDOW_V1
    else:
        method_id = ATR14_SMA_METHOD_ID_V1
        method_version = ATR14_SMA_METHOD_VERSION_V1
        method_identity = ATR14_SMA_METHOD_IDENTITY_SHA256_V1
        unit = "TWD/share"
        normalized_unit = "percent"
        required_rows = ATR14_SMA_REQUIRED_RAW_ROWS_V1
        warmup_required = 14
    dates = tuple(_DECISION - timedelta(days=required_rows - index - 1) for index in range(required_rows)) if state == "observed" else ()
    fingerprints = tuple(hashlib.sha256(f"{method}-{index}".encode()).hexdigest() for index in range(len(dates)))
    window_identity = _sha({
        "schema": "daily-market-technical-volatility-window.v1",
        "method_identity_sha256": method_identity,
        "feature_dates": [item.isoformat() for item in dates],
        "source_row_fingerprints_sha256": list(fingerprints),
    })
    return DailyMarketTechnicalVolatilityMeasureV1(
        method_id=method_id,
        method_version=method_version,
        method_identity_sha256=method_identity,
        state=state,  # type: ignore[arg-type]
        value=value,
        unit=unit,  # type: ignore[arg-type]
        normalized_value=normalized,
        normalized_unit=normalized_unit,  # type: ignore[arg-type]
        reason_codes=("warmup_insufficient",) if state == "unknown" else (),
        input_feature_dates=dates,
        input_row_fingerprints_sha256=fingerprints,
        input_rows_required=required_rows,
        warmup_observations_required=warmup_required,
        warmup_observations_observed=warmup_required if state == "observed" else 0,
        window_observations_contiguous=state == "observed",
        window_identity_sha256=window_identity,
    )


def _finish_query_body(query_dict: dict[str, object]) -> dict[str, object]:
    query_dict.pop("query_identity_sha256", None)
    return {**query_dict, "query_identity_sha256": _sha(query_dict)}


def test_query_canonical_roundtrip_binds_methods_source_clock_and_pit_limits() -> None:
    query = _query(ma_states=("match", "unknown"), bandwidth_min=Decimal("1.00"), atr_max=Decimal("5.0"))
    loaded = volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json(query.to_json())
    assert loaded == query
    assert loaded.bandwidth_min_pct == Decimal("1")
    assert loaded.atr14_max_pct == Decimal("5")
    assert loaded.query_identity_sha256 == query.query_identity_sha256
    assert loaded.reader_qualified is False
    payload = loaded.to_dict()
    assert payload["bandwidth_method_identity_sha256"] == BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1
    assert payload["atr14_method_identity_sha256"] == ATR14_SMA_METHOD_IDENTITY_SHA256_V1
    assert payload["availability_status"] == "unknown"
    assert payload["source_available_at"] is None
    assert payload["historical_pit_eligible"] is False
    assert payload["qualification_status"] == "request_only"
    assert _query(bandwidth_min=Decimal("1")).query_identity_sha256 == _query(bandwidth_min=Decimal("1.0000")).query_identity_sha256
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="source_clock_mismatch"):
        _query(source_clock="2" * 64)


def test_query_requires_exact_neutral_nested_ma_source_contract() -> None:
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="nested_ma_source_query_not_neutral"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.create(
            _ma_source_query(states=["match"]),
            volatility_read_session_identity_sha256="a" * 64,
            volatility_index_identity_sha256="b" * 64,
            volatility_source_request_identity_sha256="c" * 64,
            volatility_source_clock_identity_sha256=_SOURCE_CLOCK,
        )
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="nested_ma_source_query_not_neutral"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.create(
            _ma_source_query(sorts=[{"field": "ma_alignment_state", "direction": "desc"}]),
            volatility_read_session_identity_sha256="a" * 64,
            volatility_index_identity_sha256="b" * 64,
            volatility_source_request_identity_sha256="c" * 64,
            volatility_source_clock_identity_sha256=_SOURCE_CLOCK,
        )


def test_three_group_activation_and_policy_normalization_are_canonical() -> None:
    no_groups_and = _query(rules=False, combine="AND", policy="include")
    no_groups_noncanonical_input = _query(rules=False, combine="OR", policy="exclude")
    assert no_groups_and.to_json() == no_groups_noncanonical_input.to_json()
    assert no_groups_and.active_groups == (False, False, False)
    assert no_groups_and.condition_combine_mode == "AND"
    assert no_groups_and.unknown_policy == "include"

    technical_only = _query(combine="OR", policy="exclude")
    assert technical_only.active_groups == (True, False, False)
    assert technical_only.condition_combine_mode == "AND"
    assert technical_only.unknown_policy == "exclude"

    ma_only = _query(rules=False, ma_states=("match",), combine="OR")
    assert ma_only.active_groups == (False, True, False)
    assert ma_only.condition_combine_mode == "AND"

    volatility_only = _query(rules=False, bandwidth_min=Decimal(0), policy="only")
    assert volatility_only.active_groups == (False, False, True)
    assert volatility_only.unknown_policy == "only"

    three_and = _query(ma_states=("match",), bandwidth_min=Decimal(0), combine="AND")
    three_or = _query(ma_states=("match",), bandwidth_min=Decimal(0), combine="OR")
    assert three_and.active_groups == (True, True, True)
    assert three_and.query_identity_sha256 != three_or.query_identity_sha256
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="unknown_only_without_condition"):
        _query(rules=False, policy="only")


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"bandwidth_min": Decimal("2"), "bandwidth_max": Decimal("1")}, "range_order_invalid"),
        ({"atr_min": Decimal("NaN")}, "decimal_invalid"),
        ({"atr_max": Decimal("Infinity")}, "decimal_invalid"),
        ({"bandwidth_min": Decimal("-0.01")}, "range_negative"),
        ({"bandwidth_min": 1.0}, "decimal_invalid"),
        ({"atr_min": True}, "decimal_invalid"),
        ({"bandwidth_min": Decimal("1E+101")}, "decimal_bounds_invalid"),
    ],
)
def test_invalid_numeric_ranges_are_rejected(kwargs: dict[str, object], code: str) -> None:
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match=code):
        _query(**kwargs)  # type: ignore[arg-type]


def test_query_decoder_rejects_method_identity_and_cutoff_tampering() -> None:
    query = _query(bandwidth_min=Decimal("1"))
    payload = query.to_dict()
    payload["bandwidth_method_identity_sha256"] = "d" * 64
    payload = _finish_query_body(payload)
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="method_identity_mismatch"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_dict(payload)

    payload = query.to_dict()
    payload["decision_cutoff"] = "2026-10-06T08:00:00+00:00"
    payload = _finish_query_body(payload)
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="source_cutoff_or_clock_mismatch"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_dict(payload)


def test_page_request_is_typed_bounded_and_does_not_change_global_query_identity() -> None:
    query = _query(bandwidth_min=Decimal("0"))
    first = volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1.create(
        query, page_index=0, page_size=256,
    )
    later = volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1.create(
        query, page_index=1, page_size=256,
    )
    assert first.query.query_identity_sha256 == later.query.query_identity_sha256 == query.query_identity_sha256
    assert first.request_identity_sha256 != later.request_identity_sha256
    assert volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1.from_json(later.to_json()) == later
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="page_index_invalid"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1.create(query, page_index=True, page_size=10)  # type: ignore[arg-type]
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="page_size_invalid"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1.create(query, page_index=0, page_size=True)  # type: ignore[arg-type]
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="page_size_invalid"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1.create(query, page_index=0, page_size=257)


def test_json_parser_rejects_duplicate_keys_float_depth_and_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    query = _query()
    raw = query.to_json()
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="json_duplicate_key"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json('{"x":1,"x":2}')
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="float_forbidden"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json('{"x":1.5}')
    deep = "[" * 40 + "0" + "]" * 40
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="json_depth_limit"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json(deep)
    monkeypatch.setattr(volatility_query_module, "VOLATILITY_QUERY_MAX_BYTES_V1", len(raw.encode("utf-8")) - 1)
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="json_byte_limit"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json(raw)


def test_volatility_ranges_are_inclusive_and_unknowns_follow_fixed_inner_and() -> None:
    query = _query(bandwidth_min=Decimal("40"), bandwidth_max=Decimal("40"), atr_min=Decimal("8"))
    exact = _measure(method="bandwidth", value=Decimal("40"))
    atr_unknown = _measure(method="atr", value=None, normalized=None, state="unknown")
    assert volatility_query_module.evaluate_volatility_group_v1(query, bandwidth=exact, atr14_sma=atr_unknown) == "unknown"

    below = _measure(method="bandwidth", value=Decimal("39.999"))
    assert volatility_query_module.evaluate_volatility_group_v1(query, bandwidth=below, atr14_sma=atr_unknown) == "no_match"

    bandwidth_only = _query(bandwidth_min=Decimal("40"), bandwidth_max=Decimal("40"))
    assert volatility_query_module.evaluate_volatility_group_v1(bandwidth_only, bandwidth=exact, atr14_sma=atr_unknown) == "match"
    disabled = _query()
    assert volatility_query_module.evaluate_volatility_group_v1(disabled, bandwidth=None, atr14_sma=None) == "not_applicable"


@pytest.mark.parametrize(
    ("policy", "included"),
    [("include", True), ("exclude", False), ("only", True)],
)
def test_three_group_truth_unknown_policy_and_outer_hard_gate_are_separate(policy: str, included: bool) -> None:
    query = _query(ma_states=("match",), bandwidth_min=Decimal("10"), combine="AND", policy=policy)
    bandwidth_unknown = _measure(method="bandwidth", value=None, state="unknown")
    evaluation = volatility_query_module.evaluate_composite_predicate_v1(
        query,
        technical_truth="match",
        ma_truth="match",
        bandwidth=bandwidth_unknown,
        atr14_sma=None,
        hard_eligible=True,
        audit_visible=True,
    )
    assert evaluation.volatility_truth == "unknown"
    assert evaluation.composite_truth == "unknown"
    assert evaluation.included_by_unknown_policy is included
    assert evaluation.predicate_match is False
    assert evaluation.audit_visible is True

    excluded_audit = volatility_query_module.evaluate_composite_predicate_v1(
        query,
        technical_truth="match",
        ma_truth="match",
        bandwidth=_measure(method="bandwidth", value=Decimal("10")),
        atr14_sma=None,
        hard_eligible=False,
        audit_visible=True,
    )
    assert excluded_audit.composite_truth == "not_evaluated"
    assert excluded_audit.technical_truth == "not_evaluated"
    assert excluded_audit.ma_truth == "not_evaluated"
    assert excluded_audit.volatility_truth == "not_evaluated"
    assert excluded_audit.included_by_unknown_policy is False
    assert excluded_audit.predicate_match is False
    assert excluded_audit.audit_visible is True


def test_and_or_combine_only_active_groups_and_disabled_is_not_true() -> None:
    and_query = _query(ma_states=("match",), bandwidth_min=Decimal("10"), combine="AND")
    or_query = _query(ma_states=("match",), bandwidth_min=Decimal("10"), combine="OR")
    unknown = _measure(method="bandwidth", value=None, state="unknown")
    and_result = volatility_query_module.evaluate_composite_predicate_v1(
        and_query, technical_truth="no_match", ma_truth="match", bandwidth=unknown,
        atr14_sma=None, hard_eligible=True, audit_visible=False,
    )
    or_result = volatility_query_module.evaluate_composite_predicate_v1(
        or_query, technical_truth="no_match", ma_truth="match", bandwidth=unknown,
        atr14_sma=None, hard_eligible=True, audit_visible=False,
    )
    assert and_result.composite_truth == "no_match"
    assert or_result.composite_truth == "match"
    assert or_result.audit_visible is False

    one_group = _query(rules=False, bandwidth_min=Decimal("10"), combine="OR")
    one_result = volatility_query_module.evaluate_composite_predicate_v1(
        one_group, technical_truth="not_applicable", ma_truth="not_applicable",
        bandwidth=_measure(method="bandwidth", value=Decimal("10")), atr14_sma=None,
        hard_eligible=True, audit_visible=True,
    )
    assert one_result.composite_truth == "match"

    browse = _query(rules=False)
    browse_result = volatility_query_module.evaluate_composite_predicate_v1(
        browse, technical_truth="not_applicable", ma_truth="not_applicable",
        bandwidth=None, atr14_sma=None, hard_eligible=True, audit_visible=True,
    )
    assert browse_result.composite_truth == "not_applicable"
    assert browse_result.included_by_unknown_policy is True
    assert browse_result.predicate_match is False


def _sort_key(query: volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1, code: str, bandwidth: Decimal | None) -> volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1:
    return volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1(
        query_identity_sha256=query.query_identity_sha256,
        stock_code=code,
        values=(
            volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1("bollinger_bandwidth_pct", bandwidth),
            volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1("stock_code", code),
        ),
    )


def test_global_sort_helper_is_unqualified_null_last_in_both_directions_and_code_tied() -> None:
    clauses = (
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("bollinger_bandwidth_pct", "desc"),
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("stock_code", "asc"),
    )
    query = _query(bandwidth_min=Decimal("0"), sorts=clauses)
    keys = (
        _sort_key(query, "1002", Decimal("10")),
        _sort_key(query, "1001", Decimal("10")),
        _sort_key(query, "1003", None),
        _sort_key(query, "1004", Decimal("5")),
    )
    sorted_keys = volatility_query_module.sort_unqualified_volatility_keys_v1(query, keys)
    assert tuple(item.stock_code for item in sorted_keys) == ("1001", "1002", "1004", "1003")
    assert not hasattr(sorted_keys[0], "reader_qualified")

    ascending = _query(
        bandwidth_min=Decimal("0"),
        sorts=(
            volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("bollinger_bandwidth_pct", "asc"),
            volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("stock_code", "asc"),
        ),
    )
    asc_keys = tuple(_sort_key(ascending, key.stock_code, cast(Decimal | None, key.values[0].value)) for key in keys)
    assert tuple(item.stock_code for item in volatility_query_module.sort_unqualified_volatility_keys_v1(ascending, asc_keys)) == ("1004", "1001", "1002", "1003")


def test_sort_contract_rejects_floats_duplicate_codes_wrong_query_and_cancel() -> None:
    clauses = (
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("bollinger_bandwidth_pct", "desc"),
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("stock_code", "asc"),
    )
    query = _query(bandwidth_min=Decimal("0"), sorts=clauses)
    good = _sort_key(query, "1001", Decimal("3"))
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="sort_value_type_invalid"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1("bollinger_bandwidth_pct", 1.5)  # type: ignore[arg-type]
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="sort_value_type_invalid"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1("bollinger_bandwidth_pct", True)  # type: ignore[arg-type]
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="query_or_duplicate_code_invalid"):
        volatility_query_module.sort_unqualified_volatility_keys_v1(query, (good, good))
    other = _query(rules=False, bandwidth_min=Decimal("0"), sorts=clauses)
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="query_or_duplicate_code_invalid"):
        volatility_query_module.sort_unqualified_volatility_keys_v1(other, (good,))
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="cancelled"):
        volatility_query_module.sort_unqualified_volatility_keys_v1(query, (good,), cancel_callback=lambda: True)
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="cancel_callback_invalid"):
        volatility_query_module.sort_unqualified_volatility_keys_v1(query, (good,), cancel_callback=lambda: 1)


def test_sort_field_types_projection_budget_and_large_integer_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    clauses = (
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("bollinger_bandwidth_pct", "asc"),
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("stock_code", "asc"),
    )
    query = _query(bandwidth_min=Decimal("0"), sorts=clauses)
    wrong_type = volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1(
        query_identity_sha256=query.query_identity_sha256,
        stock_code="1001",
        values=(
            volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1("bollinger_bandwidth_pct", "10"),  # type: ignore[arg-type]
            volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1("stock_code", "1001"),
        ),
    )
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="sort_key_field_type_mismatch"):
        volatility_query_module.sort_unqualified_volatility_keys_v1(query, (wrong_type,))

    good = _sort_key(query, "1001", Decimal("10"))
    monkeypatch.setattr(volatility_query_module, "VOLATILITY_QUERY_MAX_SORT_PROJECTION_BYTES_V1", 1)
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="sort_projection_byte_limit"):
        volatility_query_module.sort_unqualified_volatility_keys_v1(query, (good,))

    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="sort_value_integer_limit"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1("raw_row_count", 10 ** 5000)  # type: ignore[arg-type]


def test_sort_and_page_bounds_are_strict_and_stock_code_tie_is_ascending() -> None:
    sort_type = volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="stock_code_tiebreak_invalid"):
        _query(
            bandwidth_min=Decimal("0"),
            sorts=(sort_type("stock_code", "desc"),),
        )
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="sort_clauses_invalid"):
        _query(
            bandwidth_min=Decimal("0"),
            sorts=tuple(sort_type("stock_code", "asc") for _ in range(34)),
        )

    query = _query(bandwidth_min=Decimal("0"))
    page_type = volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="page_index_invalid"):
        page_type.create(query, page_index=1_000_001, page_size=1)
    with pytest.raises(volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error, match="json_invalid"):
        volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json(object())  # type: ignore[arg-type]


def test_self_consistent_query_hash_is_still_request_only() -> None:
    query = _query(bandwidth_min=Decimal("0"))
    payload = query.to_dict()
    payload["volatility_index_identity_sha256"] = "f" * 64
    forged_request = volatility_query_module.DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_dict(
        _finish_query_body(payload)
    )
    assert forged_request.reader_qualified is False
    assert forged_request.volatility_index_identity_sha256 == "f" * 64

