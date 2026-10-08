"""F17 composite criteria 與純篩選／排序的合成契約測試。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, cast

import pytest

import app_module.daily_market_technical_official_disposition_query_v1 as query_module
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalRuleEvidenceV4,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionFactRowV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_SCHEMA,
    DailyMarketTechnicalOfficialDispositionCompactSortKeyV1,
    DailyMarketTechnicalOfficialDispositionJoinedRowV1,
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionQueryV1Error,
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
    DailyMarketTechnicalOfficialDispositionSortValueV1,
    evaluate_f17_membership_v1,
    normalize_daily_market_technical_official_source_pin_identity_sha256,
    project_daily_market_technical_official_disposition_sort_key_v1,
    sort_daily_market_technical_official_disposition_sort_keys_v1,
    sort_joined_rows_v1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
    DailyMarketTechnicalUniverseV4Query,
)


_CUTOFF = datetime.fromisoformat("2026-10-07T16:00:00+08:00")
_DECISION_DATE = date(2026, 10, 7)
_RULE_KEYS = ("r1", "r2", "r3", "r4", "r5")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _technical_query(*, page_size: int = 1) -> DailyMarketTechnicalUniverseV4Query:
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
        "decision_date": _DECISION_DATE.isoformat(),
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
        "state_filters": [],
        "combine_mode": "AND",
        "stock_filter": [],
        "sort_key": "stock_code",
        "descending": False,
        "page_index": 0,
        "page_size": page_size,
    }
    body["query_identity_sha256"] = _sha(body)
    return DailyMarketTechnicalUniverseV4Query.from_dict(body)


def _query(
    *,
    technical_query: DailyMarketTechnicalUniverseV4Query | None = None,
    market_states: tuple[str, ...] = (),
    disposal_states: tuple[str, ...] = (),
    scope: tuple[str, ...] = ("included_processed", "included_pending", "excluded"),
    stock_mode: str = "all",
    stock_codes: tuple[str, ...] = (),
    sort: tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...] = (),
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=technical_query or _technical_query(),
        decision_cutoff=_CUTOFF,
        bundle_output_root=Path(r"C:\synthetic\f17-bundle"),
        bundle_identity_sha256="3" * 64,
        expected_manifest_sha256="4" * 64,
        market_assignment_pin_identity_sha256="5" * 64,
        official_disposal_pin_identity_sha256="6" * 64,
        row_scope_filter=cast(Any, scope),
        market_assignment_states=market_states,
        official_disposal_states=disposal_states,
        outer_stock_filter_mode=cast(Any, stock_mode),
        outer_stock_codes=stock_codes,
        sort_clauses=sort,
    )


def _fact_row(
    stock_code: str,
    *,
    market_state: str = "assigned_twse",
    disposal_state: str = "reported_active",
    role: str = "included",
    technical_status: str = "processed",
    snapshot_observed_at: str = "2026-10-07T15:50:00+08:00",
    pointer_published_at: str = "2026-10-07T15:55:00+08:00",
    market_cutoff_at: str = "2026-10-07T16:00:00+08:00",
    disposal_observed_at: str | None = "2026-10-07T15:50:00+08:00",
    disposal_observed_date: str | None = "2026-10-07",
    technical_missing_data: bool | None = False,
    events: list[dict[str, object]] | None = None,
    market_pin_identity: str = "5" * 64,
    disposal_pin_identity: str = "6" * 64,
) -> DailyMarketTechnicalOfficialDispositionFactRowV1:
    market = {
        "schema_version": "current-market-assignment-observation.v1",
        "symbol": stock_code,
        "state": market_state,
        "market": "twse" if market_state == "assigned_twse" else (
            "tpex" if market_state == "assigned_tpex" else None
        ),
        "reason_code": None,
        "roster_source_ids": ["twse.current_roster"],
        "roster_sha256s": ["7" * 64],
        "source_data_dates": [],
        "snapshot_observed_at": snapshot_observed_at,
        "pointer_published_at": pointer_published_at,
        "cutoff_at": market_cutoff_at,
        "termination_evidence": "not_verified",
        "source_pin_identity_sha256": market_pin_identity,
        "scope": "current_only",
        "historical_pit_eligible": False,
        "official_available_at": None,
    }
    disposal = {
        "symbol": stock_code,
        "market": market["market"],
        "state": disposal_state,
        "observed_at": disposal_observed_at,
        "observed_date": disposal_observed_date,
        "events": [] if events is None else events,
        "source_data_dates": [],
        "source_id": "twse.announcement.punish",
        "source_status": "success",
        "source_parse_status": "parsed",
        "source_raw_sha256": "8" * 64,
        "source_pin_sha256": disposal_pin_identity,
        "reason_code": None,
        "source_warnings": [],
        "partial_failure": False,
        "scope": "current_only",
        "historical_pit_eligible": False,
        "official_available_at": None,
        "source_capture_dates_by_id": [
            {
                "source_id": "twse.announcement.punish",
                "captured_at": "2026-10-07T15:52:00+08:00",
                "source_data_dates": [],
            },
        ],
    }
    payload: dict[str, object] = {
        "schema_version": "daily-market-technical-official-disposition-fact-row.v1",
        "stock_code": stock_code,
        "cohort_role": role,
        "exclusion_reason": "synthetic exclusion" if role == "excluded" else None,
        "technical_status": technical_status,
        "technical_missing_data": (
            None if role == "excluded" or technical_status == "pending" else technical_missing_data
        ),
        "market_assignment": market,
        "official_disposal": disposal,
    }
    return DailyMarketTechnicalOfficialDispositionFactRowV1(
        body_json=_canonical(payload),
        stock_code=stock_code,
        cohort_role=cast(Any, role),
    )


def _technical_row(stock_code: str, ratio: Decimal | None) -> DailyMarketTechnicalParentV4Row:
    rule_rows = tuple(
        DailyMarketTechnicalRuleEvidenceV4(
            key=rule_key,
            method_id="synthetic.method",
            version="1",
            state="match",
            parameters=(),
            supports=(),
            counterevidence=(),
            unknown_reasons=(),
            raw_fact_refs=(),
            numerator=ratio if rule_key == "r1" else Decimal("1"),
            denominator=Decimal("10"),
            ratio=ratio if rule_key == "r1" else Decimal("0.1"),
            stock_code=stock_code,
            decision_date=_DECISION_DATE,
            decision_cutoff=_CUTOFF,
            feature_date=_DECISION_DATE,
            previous_feature_date=date(2026, 10, 6),
            source_identity="synthetic-source",
            source_window_fingerprint_sha256="9" * 64,
            lookahead_check="feature_dates_within_decision_date",
            availability_result="available_at_unknown",
        )
        for rule_key in _RULE_KEYS
    )
    return DailyMarketTechnicalParentV4Row(
        stock_code=stock_code,
        decision_date=_DECISION_DATE,
        snapshot_identity_sha256="a" * 64,
        source_identity="synthetic-source",
        raw_row_count=40,
        observed_prefix_contiguous=True,
        latest_feature_date=_DECISION_DATE,
        rules=rule_rows,
    )


def _joined(fact: DailyMarketTechnicalOfficialDispositionFactRowV1, ratio: Decimal | None = Decimal("1")) -> DailyMarketTechnicalOfficialDispositionJoinedRowV1:
    technical = (
        _technical_row(fact.stock_code, ratio)
        if fact.to_dict()["technical_status"] == "processed"
        else None
    )
    return DailyMarketTechnicalOfficialDispositionJoinedRowV1(
        fact_row=fact,
        technical_row=technical,
    )


def _varied_sort_rows() -> tuple[DailyMarketTechnicalOfficialDispositionJoinedRowV1, ...]:
    rows: list[DailyMarketTechnicalOfficialDispositionJoinedRowV1] = []
    facts = (
        _fact_row(
            "0050",
            market_state="assigned_twse",
            disposal_state="reported_active",
            snapshot_observed_at="2026-10-07T15:30:00+08:00",
            disposal_observed_at="2026-10-07T15:35:00+08:00",
        ),
        _fact_row(
            "1101",
            market_state="assigned_tpex",
            disposal_state="reported_upcoming",
            snapshot_observed_at="2026-10-07T15:40:00+08:00",
            disposal_observed_at="2026-10-07T15:45:00+08:00",
            disposal_observed_date="2026-10-06",
        ),
        _fact_row(
            "2330",
            market_state="unknown",
            disposal_state="unknown",
            snapshot_observed_at="2026-10-07T15:50:00+08:00",
            disposal_observed_at=None,
            disposal_observed_date=None,
        ),
        _fact_row(
            "3000",
            technical_status="pending",
            disposal_state="reported_elapsed_only",
            snapshot_observed_at="2026-10-07T15:55:00+08:00",
            disposal_observed_at="2026-10-07T15:56:00+08:00",
        ),
        _fact_row(
            "9999",
            role="excluded",
            technical_status="excluded",
            market_state="unknown",
            disposal_state="unknown",
            snapshot_observed_at="2026-10-07T15:58:00+08:00",
            disposal_observed_at=None,
            disposal_observed_date=None,
        ),
    )
    for index, fact in enumerate(facts):
        joined = _joined(fact, Decimal(str(9 + index * 10)))
        if joined.technical_row is None:
            rows.append(joined)
            continue
        feature_date = None if index == 2 else (
            date(2026, 10, 6) if index == 1 else _DECISION_DATE
        )
        rules = tuple(
            replace(
                rule,
                numerator=Decimal(str((index + 1) * 100 + rule_index)),
                denominator=Decimal(str(10 + rule_index)),
                ratio=(
                    None if index == 2 and rule_index == 2
                    else Decimal(str((index + 1) * 10 + rule_index))
                ),
                feature_date=feature_date,
            )
            for rule_index, rule in enumerate(joined.technical_row.rules)
        )
        rows.append(replace(
            joined,
            technical_row=replace(
                joined.technical_row,
                snapshot_identity_sha256=hashlib.sha256(f"snapshot-{index}".encode()).hexdigest(),
                raw_row_count=20 + index * 10,
                latest_feature_date=feature_date,
                rules=rules,
            ),
        ))
    return tuple(rows)


def test_query_v1_canonical_roundtrip_keeps_exact_p01_query_and_pins() -> None:
    query = _query(
        market_states=("unknown", "assigned_twse"),
        disposal_states=("reported_active", "unknown"),
        stock_mode="explicit_codes",
        stock_codes=("2330", "0050"),
        sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("official_disposal.state", "asc"),),
    )

    reopened = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(query.to_json())

    assert reopened == query
    assert reopened.to_dict()["technical_query_json"] == query.technical_query.to_json()
    assert reopened.outer_stock_codes == ("0050", "2330")
    assert reopened.market_assignment_states == ("assigned_twse", "unknown")
    assert reopened.technical_query.page_index == 0
    assert reopened.technical_query.page_size == 1


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        ('{"schema_version":"a","schema_version":"b"}', "technical_official_query_v1_duplicate_json_key"),
        ('{"schema_version":"a", "extra":1}', "technical_official_query_v1_json_noncanonical"),
        ('{"schema_version":"a","extra":1.0}', "technical_official_query_v1_float_forbidden"),
        ('{"schema_version":"a","extra":NaN}', "technical_official_query_v1_json_constant_invalid"),
    ],
)
def test_query_v1_decoder_rejects_noncanonical_or_float_json(raw: str, expected_code: str) -> None:
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        DailyMarketTechnicalOfficialDispositionQueryV1.from_json(raw)
    assert raised.value.code == expected_code


def test_query_v1_decoder_rejects_tampered_identity_and_noncanonical_p01_page() -> None:
    query = _query()
    payload = query.to_dict()
    payload["query_identity_sha256"] = "0" * 64
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error, match="identity_mismatch"):
        DailyMarketTechnicalOfficialDispositionQueryV1.from_dict(payload)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        _query(technical_query=_technical_query(page_size=50))
    assert raised.value.code == "technical_official_query_v1_technical_query_page_placeholder_invalid"


def test_query_v1_accepts_explicit_empty_outer_selection_as_zero_membership() -> None:
    query = _query(stock_mode="explicit_codes", stock_codes=())
    result = evaluate_f17_membership_v1(query, _fact_row("2330"))

    assert query.outer_stock_filter_mode == "explicit_codes"
    assert query.outer_stock_codes == ()
    assert result.stock_filter_match is False
    assert result.filter_membership is False


def test_unknown_official_state_can_be_selected_while_truth_remains_unknown() -> None:
    query = _query(market_states=("unknown",), disposal_states=("unknown",))
    fact = _fact_row("2330", market_state="unknown", disposal_state="unknown", disposal_observed_at=None, disposal_observed_date=None)

    result = evaluate_f17_membership_v1(query, fact)

    assert result.market_assignment_match is True
    assert result.market_assignment_truth == "unknown"
    assert result.official_disposal_match is True
    assert result.official_disposal_truth == "unknown"
    assert result.filter_membership is True


def test_unselected_unknown_stays_unknown_but_is_not_a_filter_member() -> None:
    query = _query(market_states=("assigned_twse",))
    fact = _fact_row("2330", market_state="unknown")

    result = evaluate_f17_membership_v1(query, fact)

    assert result.market_assignment_match is False
    assert result.market_assignment_truth == "unknown"
    assert result.filter_membership is False


def test_source_pin_mismatch_is_rejected_before_official_filtering() -> None:
    fact = _fact_row("2330", market_pin_identity="f" * 64)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        evaluate_f17_membership_v1(_query(), fact)

    assert raised.value.code == "technical_official_query_v1_observation_pin_mismatch"


def test_pending_and_excluded_rows_keep_distinct_scope_membership() -> None:
    pending_query = _query(scope=("included_pending",))
    pending = _fact_row("2330", technical_status="pending")
    excluded_query = _query(scope=("excluded",))
    excluded = _fact_row("1101", role="excluded", technical_status="excluded")

    pending_result = evaluate_f17_membership_v1(pending_query, pending)
    excluded_result = evaluate_f17_membership_v1(excluded_query, excluded)

    assert pending_result.row_scope == "included_pending"
    assert pending_result.filter_membership is True
    assert excluded_result.row_scope == "excluded"
    assert excluded_result.filter_membership is True


@pytest.mark.parametrize(
    "fact",
    [
        _fact_row("2330", snapshot_observed_at="2026-10-07T16:00:01+08:00"),
        _fact_row("2330", pointer_published_at="2026-10-07T16:00:01+08:00"),
        _fact_row("2330", disposal_observed_at="2026-10-07T16:00:01+08:00"),
        _fact_row(
            "2330",
            events=[{
                "announcement_date": "2026-10-07",
                "effective_from": "2026-10-09",
                "effective_to": "2026-10-10",
                "observed_at": "2026-10-07T16:00:01+08:00",
            }],
        ),
        _fact_row(
            "2330",
            events=[{
                "announcement_date": "2026-10-08",
                "effective_from": "2026-10-10",
                "effective_to": "2026-10-12",
                "observed_at": "2026-10-07T15:55:00+08:00",
            }],
        ),
    ],
)
def test_membership_rejects_observation_or_publication_after_exact_cutoff(
    fact: DailyMarketTechnicalOfficialDispositionFactRowV1,
) -> None:
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        evaluate_f17_membership_v1(_query(), fact)
    assert "future" in raised.value.code


def test_announced_future_effective_period_is_not_lookahead() -> None:
    fact = _fact_row(
        "2330",
        disposal_state="reported_upcoming",
        events=[{
            "announcement_date": "2026-10-07",
            "effective_from": "2026-10-10",
            "effective_to": "2026-10-12",
            "observed_at": "2026-10-07T15:55:00+08:00",
        }],
    )

    result = evaluate_f17_membership_v1(_query(), fact)

    assert result.filter_membership is True


def test_sort_official_states_and_nulls_keep_unknown_last_in_both_directions() -> None:
    rows = (
        _joined(_fact_row("2330", market_state="unknown")),
        _joined(_fact_row("0050", market_state="assigned_tpex")),
        _joined(_fact_row("1101", market_state="assigned_twse")),
    )
    ascending = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("market_assignment.state", "asc"),))
    descending = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("market_assignment.state", "desc"),))

    assert tuple(row.fact_row.stock_code for row in sort_joined_rows_v1(ascending, rows)) == (
        "0050", "1101", "2330",
    )
    assert tuple(row.fact_row.stock_code for row in sort_joined_rows_v1(descending, rows)) == (
        "1101", "0050", "2330",
    )


def test_sort_aware_times_uses_instants_and_stock_code_stable_tie_break() -> None:
    rows = (
        _joined(_fact_row("0050", snapshot_observed_at="2026-10-07T15:50:00+08:00")),
        _joined(_fact_row("1101", snapshot_observed_at="2026-10-07T07:50:00+00:00")),
        _joined(_fact_row("2330", snapshot_observed_at="2026-10-07T07:45:00+00:00")),
    )
    query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("market_assignment.snapshot_observed_at", "asc"),))

    assert tuple(row.fact_row.stock_code for row in sort_joined_rows_v1(query, rows)) == (
        "2330", "0050", "1101",
    )


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_decimal_technical_sort_is_exact_and_nulls_are_always_last(direction: str) -> None:
    rows = (
        _joined(_fact_row("0100"), Decimal("9")),
        _joined(_fact_row("0200"), Decimal("100")),
        _joined(_fact_row("0300"), None),
    )
    query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", cast(Any, direction)),))

    codes = tuple(row.fact_row.stock_code for row in sort_joined_rows_v1(query, rows))

    assert codes == (("0100", "0200", "0300") if direction == "asc" else ("0200", "0100", "0300"))


@pytest.mark.parametrize(
    ("field", "expected_code"),
    [
        ("price.close_decimal", "technical_official_query_v1_sort_source_not_bound"),
        ("official_disposal.effective_from", "technical_official_query_v1_sort_key_unsupported"),
    ],
)
def test_unbound_or_ambiguous_sort_fields_fail_closed(field: str, expected_code: str) -> None:
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1(field, "asc"),))
    assert raised.value.code == expected_code


def test_duplicate_stock_in_sort_input_is_rejected() -> None:
    duplicate = _joined(_fact_row("2330"))
    query = _query()
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        sort_joined_rows_v1(query, (duplicate, duplicate))
    assert raised.value.code == "technical_official_query_v1_duplicate_stock"


def test_sort_accepts_current_only_rows_with_unknown_availability_clock() -> None:
    row = _joined(_fact_row("2330"))
    assert row.technical_row is not None
    assert row.technical_row.rules[0].availability_result == "available_at_unknown"

    assert sort_joined_rows_v1(_query(), (row,)) == (row,)


def test_sort_rejects_technical_row_from_another_decision_date() -> None:
    joined = _joined(_fact_row("2330"))
    assert joined.technical_row is not None
    wrong_date_row = replace(joined.technical_row, decision_date=date(2026, 10, 6))
    wrong_date = replace(joined, technical_row=wrong_date_row)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        sort_joined_rows_v1(_query(), (wrong_date,))
    assert raised.value.code == "technical_official_query_v1_technical_row_decision_date_mismatch"


@pytest.mark.parametrize("future_on_row", [True, False])
def test_sort_rejects_future_latest_or_rule_feature_date(future_on_row: bool) -> None:
    joined = _joined(_fact_row("2330"))
    assert joined.technical_row is not None
    if future_on_row:
        technical_row = replace(
            joined.technical_row,
            latest_feature_date=date(2026, 10, 8),
        )
        expected_code = "technical_official_query_v1_technical_row_future_feature_date"
    else:
        rules = (
            replace(joined.technical_row.rules[0], feature_date=date(2026, 10, 8)),
            *joined.technical_row.rules[1:],
        )
        technical_row = replace(joined.technical_row, rules=rules)
        expected_code = "technical_official_query_v1_technical_rule_future_feature_date"
    future = replace(joined, technical_row=technical_row)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        sort_joined_rows_v1(_query(), (future,))
    assert raised.value.code == expected_code


def test_sort_rejects_fact_missing_data_flag_that_disagrees_with_parent_row() -> None:
    fact = _fact_row("2330", technical_missing_data=True)
    joined = _joined(fact)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        sort_joined_rows_v1(_query(), (joined,))
    assert raised.value.code == "technical_official_query_v1_technical_missing_data_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda rule: replace(rule, key="unexpected"),
            "technical_official_query_v1_technical_rule_scope_mismatch",
        ),
        (
            lambda rule: replace(rule, decision_date=date(2026, 10, 6)),
            "technical_official_query_v1_technical_rule_decision_date_mismatch",
        ),
        (
            lambda rule: replace(rule, stock_code="1101"),
            "technical_official_query_v1_technical_rule_stock_scope_mismatch",
        ),
        (
            lambda rule: replace(rule, source_identity="different-source"),
            "technical_official_query_v1_technical_rule_source_scope_mismatch",
        ),
        (
            lambda rule: replace(rule, decision_cutoff=datetime.fromisoformat("2026-10-07T15:59:00+08:00")),
            "technical_official_query_v1_technical_rule_cutoff_mismatch",
        ),
    ],
)
def test_sort_rejects_rule_scope_key_stock_or_cutoff_conflict(
    mutation: Any, expected_code: str
) -> None:
    joined = _joined(_fact_row("2330"))
    assert joined.technical_row is not None
    rules = (mutation(joined.technical_row.rules[0]), *joined.technical_row.rules[1:])
    invalid = replace(joined, technical_row=replace(joined.technical_row, rules=rules))

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        sort_joined_rows_v1(_query(), (invalid,))
    assert raised.value.code == expected_code


def test_pending_and_excluded_rows_sort_without_technical_rows() -> None:
    rows = (
        _joined(_fact_row("2330", technical_status="pending")),
        _joined(_fact_row("1101", role="excluded", technical_status="excluded")),
    )

    assert tuple(row.fact_row.stock_code for row in sort_joined_rows_v1(_query(), rows)) == (
        "1101", "2330",
    )


@pytest.mark.parametrize(
    ("fact", "expected_code"),
    [
        (
            _fact_row("2330", technical_status="pending"),
            "technical_official_query_v1_technical_row_scope_invalid",
        ),
        (
            _fact_row("1101", role="excluded", technical_status="excluded"),
            "technical_official_query_v1_technical_row_scope_invalid",
        ),
    ],
)
def test_pending_or_excluded_fact_cannot_carry_technical_row(
    fact: DailyMarketTechnicalOfficialDispositionFactRowV1,
    expected_code: str,
) -> None:
    invalid = DailyMarketTechnicalOfficialDispositionJoinedRowV1(
        fact_row=fact,
        technical_row=_technical_row(fact.stock_code, Decimal("1")),
    )

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        sort_joined_rows_v1(_query(), (invalid,))
    assert raised.value.code == expected_code


def test_compact_sort_keys_match_existing_sort_for_every_supported_field_and_direction() -> None:
    rows = _varied_sort_rows()
    fields = (
        "stock_code",
        "decision_date",
        "latest_feature_date",
        "raw_row_count",
        *(
            f"{rule_key}.{metric}"
            for rule_key in _RULE_KEYS
            for metric in ("ratio", "numerator", "denominator")
        ),
        "market_assignment.state",
        "market_assignment.snapshot_observed_at",
        "official_disposal.state",
        "official_disposal.observed_at",
        "official_disposal.observed_date",
    )

    for field in fields:
        for direction in ("asc", "desc"):
            query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1(field, direction),))
            projected = tuple(
                project_daily_market_technical_official_disposition_sort_key_v1(query, row)
                for row in rows
            )
            compact_order = sort_daily_market_technical_official_disposition_sort_keys_v1(
                query, projected
            )
            expected = tuple(
                row.fact_row.stock_code
                for row in sort_joined_rows_v1(query, rows)
            )
            assert tuple(item.stock_code for item in compact_order) == expected, (field, direction)


def test_compact_sort_keys_match_multiclause_parity_and_exact_extreme_decimals() -> None:
    rows = _varied_sort_rows()
    clauses = (
        DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", "desc"),
        DailyMarketTechnicalOfficialDispositionSortClauseV1("market_assignment.state", "asc"),
        DailyMarketTechnicalOfficialDispositionSortClauseV1("official_disposal.observed_date", "desc"),
    )
    query = _query(sort=clauses)
    projected = tuple(
        project_daily_market_technical_official_disposition_sort_key_v1(query, row)
        for row in rows
    )
    compact_order = sort_daily_market_technical_official_disposition_sort_keys_v1(query, projected)

    assert tuple(item.stock_code for item in compact_order) == tuple(
        row.fact_row.stock_code for row in sort_joined_rows_v1(query, rows)
    )

    decimal_values = (
        ("0050", Decimal("1E+60")),
        ("1101", Decimal("1.0000000000000000000000000001")),
        ("2330", Decimal("-1E-60")),
        ("3000", None),
    )
    for direction, expected in (
        (cast(Literal["asc", "desc"], "asc"), ("2330", "1101", "0050", "3000")),
        (cast(Literal["asc", "desc"], "desc"), ("0050", "1101", "2330", "3000")),
    ):
        decimal_query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", direction),))
        decimal_rows: list[DailyMarketTechnicalOfficialDispositionJoinedRowV1] = []
        for code, numeric_value in decimal_values:
            joined = _joined(_fact_row(code), numeric_value)
            assert joined.technical_row is not None
            decimal_rows.append(replace(
                joined,
                technical_row=replace(
                    joined.technical_row,
                    snapshot_identity_sha256=hashlib.sha256(code.encode("ascii")).hexdigest(),
                ),
            ))
        decimal_keys = tuple(
            project_daily_market_technical_official_disposition_sort_key_v1(decimal_query, row)
            for row in decimal_rows
        )
        assert tuple(
            item.stock_code
            for item in sort_daily_market_technical_official_disposition_sort_keys_v1(
                decimal_query, decimal_keys
            )
        ) == expected


def test_compact_sort_projection_keeps_pins_and_ids_without_joined_rows_or_snapshots() -> None:
    query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", "desc"),))
    joined = _joined(_fact_row("2330"), Decimal("9"))

    key = project_daily_market_technical_official_disposition_sort_key_v1(query, joined)
    payload = key.to_dict()

    assert joined.technical_row is not None
    assert key.query_identity_sha256 == query.query_identity_sha256
    assert key.fact_row_sha256 == hashlib.sha256(joined.fact_row.body_json.encode("utf-8")).hexdigest()
    assert key.market_assignment_pin_identity_sha256 == query.market_assignment_pin_identity_sha256
    assert key.official_disposal_pin_identity_sha256 == query.official_disposal_pin_identity_sha256
    assert key.technical_snapshot_identity_sha256 == joined.technical_row.snapshot_identity_sha256
    assert key.technical_source_identity == joined.technical_row.source_identity
    assert "fact_row" not in payload and "technical_row" not in payload and "snapshot" not in payload
    assert payload["sort_values"] == [{
        "field": "r1.ratio",
        "direction": "desc",
        "sort_value": {"type": "decimal", "value": "9"},
    }]

    pending_query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", "asc"),))
    pending = _joined(_fact_row("3000", technical_status="pending"))
    pending_key = project_daily_market_technical_official_disposition_sort_key_v1(
        pending_query, pending
    )
    assert pending_key.technical_snapshot_identity_sha256 is None
    assert pending_key.technical_source_identity is None
    assert pending_key.sort_values[0].value is None


def test_compact_sort_rejects_query_clause_identity_and_duplicate_mismatch() -> None:
    first_query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", "asc"),))
    row = _joined(_fact_row("2330"))
    key = project_daily_market_technical_official_disposition_sort_key_v1(first_query, row)
    other_query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", "desc"),))

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as mismatch:
        sort_daily_market_technical_official_disposition_sort_keys_v1(other_query, (key,))
    assert mismatch.value.code == "technical_official_query_v1_compact_sort_query_mismatch"

    other_clause = replace(
        key.sort_values[0],
        field="official_disposal.state",
    )
    changed = replace(key, sort_values=(other_clause,))
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as clause_mismatch:
        sort_daily_market_technical_official_disposition_sort_keys_v1(first_query, (changed,))
    assert clause_mismatch.value.code == "technical_official_query_v1_compact_sort_clause_mismatch"

    changed_market_pin = replace(key, market_assignment_pin_identity_sha256="7" * 64)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as market_pin_mismatch:
        sort_daily_market_technical_official_disposition_sort_keys_v1(
            first_query, (changed_market_pin,)
        )
    assert market_pin_mismatch.value.code == "technical_official_query_v1_compact_sort_market_pin_mismatch"

    changed_disposal_pin = replace(key, official_disposal_pin_identity_sha256="8" * 64)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as disposal_pin_mismatch:
        sort_daily_market_technical_official_disposition_sort_keys_v1(
            first_query, (changed_disposal_pin,)
        )
    assert disposal_pin_mismatch.value.code == "technical_official_query_v1_compact_sort_disposal_pin_mismatch"

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as duplicate:
        sort_daily_market_technical_official_disposition_sort_keys_v1(first_query, (key, key))
    assert duplicate.value.code == "technical_official_query_v1_duplicate_stock"


def test_compact_sort_revalidates_query_identity_and_scalar_types() -> None:
    query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", "asc"),))
    key = project_daily_market_technical_official_disposition_sort_key_v1(
        query, _joined(_fact_row("2330"))
    )
    tampered_identity = replace(key, query_identity_sha256="0" * 64)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as mismatch:
        sort_daily_market_technical_official_disposition_sort_keys_v1(query, (tampered_identity,))
    assert mismatch.value.code == "technical_official_query_v1_compact_sort_query_mismatch"

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as invalid_type:
        DailyMarketTechnicalOfficialDispositionSortValueV1(
            field="raw_row_count",
            direction="asc",
            value=True,
        )
    assert invalid_type.value.code == "technical_official_query_v1_compact_sort_value_invalid"

    future_query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("latest_feature_date", "asc"),))
    future_key = project_daily_market_technical_official_disposition_sort_key_v1(
        future_query, _joined(_fact_row("1101"))
    )
    future_clause = replace(
        future_key.sort_values[0],
        value=date(2026, 10, 8),
    )
    future_key = replace(future_key, sort_values=(future_clause,))
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as future:
        sort_daily_market_technical_official_disposition_sort_keys_v1(future_query, (future_key,))
    assert future.value.code == "technical_official_query_v1_compact_sort_future_feature_date"


def test_compact_sort_projection_reuses_date_and_scope_guards() -> None:
    query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("r1.ratio", "asc"),))
    joined = _joined(_fact_row("2330"))
    assert joined.technical_row is not None
    wrong_date = replace(
        joined,
        technical_row=replace(joined.technical_row, decision_date=date(2026, 10, 6)),
    )

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as raised:
        project_daily_market_technical_official_disposition_sort_key_v1(query, wrong_date)
    assert raised.value.code == "technical_official_query_v1_technical_row_decision_date_mismatch"


def test_compact_sort_enforces_count_and_canonical_serialized_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),))
    rows = _varied_sort_rows()
    keys = tuple(project_daily_market_technical_official_disposition_sort_key_v1(query, row) for row in rows)

    monkeypatch.setattr(query_module, "DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS", 4)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as count_error:
        sort_daily_market_technical_official_disposition_sort_keys_v1(query, keys)
    assert count_error.value.code == "technical_official_query_v1_stock_limit"

    monkeypatch.setattr(
        query_module,
        "DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS",
        100_000,
    )
    monkeypatch.setattr(
        query_module,
        "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPACT_SORT_MAX_BYTES",
        1,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as byte_error:
        sort_daily_market_technical_official_disposition_sort_keys_v1(query, keys)
    assert byte_error.value.code == "technical_official_query_v1_compact_sort_byte_limit"


def test_compact_sort_cancel_callbacks_are_strict_and_cooperative() -> None:
    query = _query(sort=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),))
    rows = _varied_sort_rows()[:3]

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as projection_cancel:
        project_daily_market_technical_official_disposition_sort_key_v1(
            query, rows[0], cancel_callback=lambda: True
        )
    assert projection_cancel.value.code == "technical_official_query_v1_compact_sort_cancelled"

    projection_checks = 0

    def cancel_after_projection() -> bool:
        nonlocal projection_checks
        projection_checks += 1
        return projection_checks >= 2

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as late_projection_cancel:
        project_daily_market_technical_official_disposition_sort_key_v1(
            query, rows[0], cancel_callback=cancel_after_projection
        )
    assert late_projection_cancel.value.code == "technical_official_query_v1_compact_sort_cancelled"
    assert projection_checks == 2

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as bad_bool:
        project_daily_market_technical_official_disposition_sort_key_v1(
            query, rows[0], cancel_callback=lambda: 1
        )
    assert bad_bool.value.code == "technical_official_query_v1_compact_sort_cancel_callback_invalid"

    def failing_callback() -> object:
        raise RuntimeError("synthetic cancellation probe failure")

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as callback_error:
        project_daily_market_technical_official_disposition_sort_key_v1(
            query, rows[0], cancel_callback=failing_callback
        )
    assert callback_error.value.code == "technical_official_query_v1_compact_sort_cancel_callback_failed"

    keys = tuple(project_daily_market_technical_official_disposition_sort_key_v1(query, row) for row in rows)
    sort_checks = 0

    def cancel_during_sort() -> bool:
        nonlocal sort_checks
        sort_checks += 1
        return sort_checks >= 8

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as sorting_cancel:
        sort_daily_market_technical_official_disposition_sort_keys_v1(
            query, keys, cancel_callback=cancel_during_sort
        )
    assert sorting_cancel.value.code == "technical_official_query_v1_compact_sort_cancelled"
    assert sort_checks == 8

    return_checks = 0

    def cancel_before_return() -> bool:
        nonlocal return_checks
        return_checks += 1
        return return_checks >= 10

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as return_cancel:
        sort_daily_market_technical_official_disposition_sort_keys_v1(
            query, keys, cancel_callback=cancel_before_return
        )
    assert return_cancel.value.code == "technical_official_query_v1_compact_sort_cancelled"
    assert return_checks == 10


def test_create_normalizes_exact_prefixed_source_pin_and_preserves_query_identity() -> None:
    bare = _query()
    prefixed = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=bare.technical_query,
        decision_cutoff=bare.decision_cutoff,
        bundle_output_root=bare.bundle_output_root,
        bundle_identity_sha256=bare.bundle_identity_sha256,
        expected_manifest_sha256=bare.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=f"sha256:{bare.market_assignment_pin_identity_sha256}",
        official_disposal_pin_identity_sha256=f"sha256:{bare.official_disposal_pin_identity_sha256}",
        row_scope_filter=bare.row_scope_filter,
        market_assignment_states=bare.market_assignment_states,
        official_disposal_states=bare.official_disposal_states,
        outer_stock_filter_mode=bare.outer_stock_filter_mode,
        outer_stock_codes=bare.outer_stock_codes,
        sort_clauses=bare.sort_clauses,
    )
    assert prefixed.query_identity_sha256 == bare.query_identity_sha256
    assert prefixed.market_assignment_pin_identity_sha256 == bare.market_assignment_pin_identity_sha256
    assert prefixed.official_disposal_pin_identity_sha256 == bare.official_disposal_pin_identity_sha256
    assert prefixed.to_dict() == bare.to_dict()


def test_source_pin_style_fact_is_accepted_and_conflicting_alias_is_rejected() -> None:
    query = _query(
        market_states=("assigned_twse",),
        disposal_states=("reported_active",),
    )
    fact = _fact_row(
        "2330",
        market_pin_identity=f"sha256:{query.market_assignment_pin_identity_sha256}",
        disposal_pin_identity=f"sha256:{query.official_disposal_pin_identity_sha256}",
    )
    accepted = evaluate_f17_membership_v1(query, fact)
    assert accepted.market_assignment_truth == "match"
    assert accepted.official_disposal_truth == "match"

    body = fact.to_dict()
    market = cast(dict[str, object], body["market_assignment"])
    market["source_pin_sha256"] = f"sha256:{'a' * 64}"
    conflicting = DailyMarketTechnicalOfficialDispositionFactRowV1(
        body_json=_canonical(body),
        stock_code=fact.stock_code,
        cohort_role=fact.cohort_role,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as error:
        evaluate_f17_membership_v1(query, conflicting)
    assert error.value.code == "technical_official_query_v1_observation_pin_alias_conflict"


@pytest.mark.parametrize(
    "value",
    (
        "sha512:" + "a" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256: " + "a" * 64,
        "A" * 64,
        " a" * 32,
    ),
)
def test_source_pin_identity_normalizer_rejects_noncanonical_spellings(value: str) -> None:
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as error:
        normalize_daily_market_technical_official_source_pin_identity_sha256(value)
    assert error.value.code == "technical_official_query_v1_source_pin_identity_invalid"


def test_query_json_rejects_prefixed_pin_even_though_create_accepts_it() -> None:
    query = _query()
    payload = query.to_dict()
    payload["market_assignment_pin_identity_sha256"] = (
        f"sha256:{query.market_assignment_pin_identity_sha256}"
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as error:
        DailyMarketTechnicalOfficialDispositionQueryV1.from_json(_canonical(payload))
    assert error.value.code == "technical_official_query_v1_market_pin_invalid"


def test_source_fact_with_other_normalized_pin_is_rejected() -> None:
    query = _query()
    fact = _fact_row(
        "2330",
        market_pin_identity=f"sha256:{'a' * 64}",
        disposal_pin_identity=f"sha256:{query.official_disposal_pin_identity_sha256}",
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryV1Error) as error:
        evaluate_f17_membership_v1(query, fact)
    assert error.value.code == "technical_official_query_v1_observation_pin_mismatch"
