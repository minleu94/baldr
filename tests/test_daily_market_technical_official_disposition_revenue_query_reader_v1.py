from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import traceback
from typing import Any, Literal

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)

from app_module.daily_market_monthly_revenue_yoy_index_v1 import (
    DailyMarketMonthlyRevenueYoyIndexSessionV1,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleWriterV1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryReaderV1Error,
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    RowScope,
    open_daily_market_technical_official_disposition_bundle_session_v1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV1Error,
    DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
)
from data_module.daily_market_monthly_revenue_read_session_v1 import MAX_CODES_PER_BATCH
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreReader,
    DailyMarketTechnicalUniverseV4StoreWriter,
)
from tests.test_daily_market_monthly_revenue_read_session_v1 import _seed_provider
from tests.test_monthly_revenue_snapshot_harvester import MOPS_SAMPLE_HTML
import app_module.daily_market_monthly_revenue_yoy_index_v1 as monthly_index_module


_ALL_ROW_SCOPES: tuple[RowScope, ...] = (
    "included_processed", "included_pending", "excluded",
)


@dataclass(frozen=True, slots=True)
class _RevenueContext:
    session: Any
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV1
    codes: tuple[str, ...]
    cutoff: datetime


@pytest.fixture(scope="module")
def revenue_context(bundle_fixture: Any, tmp_path_factory: pytest.TempPathFactory) -> _RevenueContext:
    work_root = tmp_path_factory.mktemp("f12-revenue-reader")
    read_session = open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=bundle_fixture.bundle_root,
        bundle_identity_sha256=bundle_fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_fixture.reference.manifest_sha256,
        row_scope_filter=_ALL_ROW_SCOPES,
    )
    codes = read_session.verified_declared_stock_codes()
    html = MOPS_SAMPLE_HTML.replace("<td>2330</td>", "<td>1000</td>", 1)
    provider = _seed_provider(work_root / "provider", html=html)
    cutoff = read_session.query.decision_cutoff
    index_session = DailyMarketMonthlyRevenueYoyIndexSessionV1.open(
        provider,
        snapshot_root=work_root / "monthly-source-snapshot",
        stock_codes=codes,
        cutoff_at=cutoff,
    )
    for start in range(0, len(codes), MAX_CODES_PER_BATCH):
        index_session.load_batch(codes[start:start + MAX_CODES_PER_BATCH])
    index = index_session.finish()
    assert index.is_reader_issued is True
    assert index.declared_stock_codes == codes
    assert index.entries[0].stock_code == "1000"
    assert index.entries[0].projected_fact.state == "observed"
    assert index.entries[0].projected_fact.growth_percent == Decimal("22.006875")
    assert index.entries[-1].stock_code == "9999"
    assert index.entries[-1].projected_fact.state == "unknown"
    return _RevenueContext(
        session=read_session.with_monthly_revenue_yoy_index(index_session),
        index_session=index_session,
        codes=codes,
        cutoff=cutoff,
    )


def _sort_clauses() -> tuple[DailyMarketTechnicalOfficialDispositionMaSortClauseV1, ...]:
    return (
        DailyMarketTechnicalOfficialDispositionMaSortClauseV1(
            "monthly_revenue_yoy_percent", "desc",
        ),
        DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),
    )


def test_full_declared_browse_keeps_excluded_visible_but_not_evaluated(
    revenue_context: _RevenueContext,
) -> None:
    query = revenue_context.session.create_revenue_query_v1(
        ma_states=None,
        minimum_yoy_percent=None,
    )
    result = revenue_context.session.execute_revenue_query_v1(query)
    assert result.counts.declared_count == 258
    assert result.counts.visible_count == 258
    assert dict(result.counts.composite_truth_counts)["not_evaluated"] == 1
    assert result.counts.predicate_not_evaluated_count == 1

    last_page = result.read_page(64, 4)
    assert tuple(row.fact_row.stock_code for row in last_page.rows) == ("1256", "9999")
    excluded = last_page.rows[-1]
    assert excluded.fact_row.to_dict()["technical_status"] == "excluded"
    assert excluded.technical_row is None
    assert excluded.technical_condition_truth == "not_evaluated"
    assert excluded.ma_condition_truth == "not_evaluated"
    assert excluded.revenue_condition_truth == "not_evaluated"
    assert excluded.composite_condition_truth == "not_evaluated"
    assert excluded.included_by_unknown_policy is False


def test_active_or_query_is_global_hard_gated_and_pages_cross_segments(
    revenue_context: _RevenueContext,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    conditioned = revenue_context.session.with_conditions(
        row_scope_filter=_ALL_ROW_SCOPES,
        market_assignment_states=("assigned_twse",),
    )
    query = conditioned.create_revenue_query_v1(
        ma_states=("unknown",),
        minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR",
        unknown_policy="include",
        sort_clauses=_sort_clauses(),
    )
    parsed = DailyMarketTechnicalOfficialDispositionRevenueQueryV1.from_json(query.to_json())
    assert parsed == query

    monthly_index = revenue_context.index_session.index
    monthly_index_type = type(monthly_index)
    monthly_index_identity = monthly_index.index_identity_sha256
    monthly_source_clock_identity = monthly_index.source_clock.identity_sha256
    monthly_source_clock_payload = monthly_index.source_clock.to_dict()
    assert monthly_source_clock_payload["database_file_pins_start"] == monthly_source_clock_payload[
        "database_file_pins_finish"
    ]
    assert monthly_source_clock_payload["capture_file_pins_start"] == monthly_source_clock_payload[
        "capture_file_pins_finish"
    ]
    assert monthly_source_clock_payload["historical_pit_eligible"] is False
    assert monthly_source_clock_payload["formal_pit_eligible"] is False
    checked_index_identities: list[str] = []
    checked_index_call_sites: list[str] = []
    original_index_identity = monthly_index_module._index_identity

    def count_index_validation(index: object) -> str:
        identity = original_index_identity(index)  # type: ignore[arg-type]
        checked_index_identities.append(identity)
        frames = traceback.extract_stack(limit=8)
        checked_index_call_sites.append(" <- ".join(frame.name for frame in frames[-5:-1]))
        return identity

    def reject_per_code_full_validation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("full-N reader must not validate the whole index once per row")

    monkeypatch.setattr(monthly_index_module, "_index_identity", count_index_validation)
    monkeypatch.setattr(
        monthly_index_type, "entry_for", reject_per_code_full_validation,
    )
    result = conditioned.execute_revenue_query_v1(query)
    assert isinstance(result, DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1)
    # 全母體 execute 在入口與發佈前各核一次 index；每頁另做一次，不能逐列重掃整個 index。
    assert len(checked_index_identities) == 2
    assert len(set(checked_index_identities)) == 1
    counts = result.counts
    assert counts.declared_count == 258
    assert counts.hard_eligible_count == 256
    assert counts.visible_count == 256
    assert dict(counts.composite_truth_counts) == {
        "match": 1,
        "no_match": 0,
        "unknown": 256,
        "not_evaluated": 1,
        "not_applicable": 0,
    }
    assert counts.predicate_not_evaluated_count == 0

    raw_ma_cutoff = revenue_context.session.ma_alignment_session.source_request.decision_cutoff
    raw_monthly_cutoff = revenue_context.index_session.decision_cutoff.isoformat()
    utc_cutoff = revenue_context.session.query.decision_cutoff.astimezone(timezone.utc)
    assert raw_ma_cutoff != utc_cutoff.isoformat()
    assert raw_monthly_cutoff == utc_cutoff.isoformat()
    assert datetime.fromisoformat(raw_ma_cutoff).astimezone(timezone.utc) == utc_cutoff
    assert datetime.fromisoformat(raw_monthly_cutoff) == utc_cutoff
    result_pins = dict(result.source_pins)
    assert result_pins["decision_cutoff"] == utc_cutoff.isoformat()
    assert result_pins["monthly_yoy_cutoff"] == utc_cutoff.isoformat()
    cutoff_receipt = {
        "schema": "f12-revenue-query-cutoff-normalization-evidence.v1",
        "raw_ma_source_cutoff": raw_ma_cutoff,
        "raw_monthly_session_cutoff": raw_monthly_cutoff,
        "canonical_query_cutoff_utc": utc_cutoff.isoformat(),
        "result_decision_cutoff_utc": result_pins["decision_cutoff"],
        "result_monthly_cutoff_utc": result_pins["monthly_yoy_cutoff"],
        "bundle_identity_sha256": revenue_context.session.bundle_reference.bundle_identity_sha256,
        "bundle_manifest_sha256": revenue_context.session.bundle_reference.manifest_sha256,
        "monthly_index_identity_sha256": monthly_index_identity,
        "monthly_source_clock_identity_sha256": monthly_source_clock_identity,
        "monthly_source_clock": monthly_source_clock_payload,
        "result_source_pins_before_page": [list(pin) for pin in result.source_pins],
        "index_identity_validation_count_after_execute": len(checked_index_identities),
        "index_identity_validation_call_sites_after_execute": list(checked_index_call_sites),
    }
    (tmp_path / "f12_cutoff_normalization_receipt.json").write_text(
        json.dumps(cutoff_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    first_page = result.read_page(0, 4)
    assert len(checked_index_identities) == 3
    assert tuple(result.source_pins) == tuple(tuple(pin) for pin in cutoff_receipt["result_source_pins_before_page"])
    cutoff_receipt["index_identity_validation_count_after_first_page"] = len(checked_index_identities)
    cutoff_receipt["index_identity_validation_call_sites_after_first_page"] = list(
        checked_index_call_sites
    )
    cutoff_receipt["result_source_pins_after_page"] = [list(pin) for pin in result.source_pins]
    (tmp_path / "f12_cutoff_normalization_receipt.json").write_text(
        json.dumps(cutoff_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    assert tuple(row.fact_row.stock_code for row in first_page.rows) == ("1000", "1001", "1002", "1003")
    first = first_page.rows[0]
    assert first.monthly_entry.projected_fact.growth_percent == Decimal("22.006875")
    current_input = first.monthly_entry.source_fact.current
    assert current_input is not None
    assert current_input.source_available_at is not None
    assert first.technical_condition_truth == "not_applicable"
    assert first.ma_condition_truth == "unknown"
    assert first.revenue_condition_truth == "match"
    assert first.composite_condition_truth == "match"
    assert first_page.to_dict()["monthly_official_available_at"] is None
    assert "monthly_source_available_at" not in first.to_dict()
    row_payload = first.to_dict()
    monthly_payload = row_payload["monthly_entry"]
    assert isinstance(monthly_payload, dict)
    source_payload = monthly_payload["source_fact"]
    assert isinstance(source_payload, dict)
    current_payload = source_payload["current"]
    assert isinstance(current_payload, dict)
    assert current_payload["source_available_at"] is not None

    last_page = result.read_page(63, 4)
    assert tuple(row.fact_row.stock_code for row in last_page.rows) == ("1252", "1253", "1254", "1255")
    assert "1256" not in {row.stock_code for row in result.ordered_sort_keys}
    assert "9999" not in {row.stock_code for row in result.ordered_sort_keys}


def test_excluded_row_cannot_be_rescued_by_an_active_or_group(
    revenue_context: _RevenueContext,
) -> None:
    excluded_session = revenue_context.session.with_conditions(
        row_scope_filter=_ALL_ROW_SCOPES,
        outer_stock_filter_mode="explicit_codes",
        outer_stock_codes=("9999",),
    )
    query = excluded_session.create_revenue_query_v1(
        ma_states=("unknown",),
        minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR",
        unknown_policy="include",
    )
    result = excluded_session.execute_revenue_query_v1(query)
    assert result.counts.declared_count == 258
    assert result.counts.visible_count == 0
    assert result.counts.predicate_not_evaluated_count == 1
    assert dict(result.counts.composite_truth_counts)["not_evaluated"] == 1
    assert result.read_page(0, 8).rows == ()


def test_three_active_groups_and_or_apply_unknown_policy_after_hard_eligibility(
    revenue_context: _RevenueContext,
) -> None:
    rule_key = revenue_context.session.query.technical_query.method_rule_keys[0]
    rule_filter_with_known_states = DailyMarketTechnicalRuleStateFilterV4.create(
        rule_key, ("match", "no_match"),
    )
    and_session = revenue_context.session.with_conditions(
        row_scope_filter=_ALL_ROW_SCOPES,
        rule_state_filters=(rule_filter_with_known_states,),
        market_assignment_states=("assigned_twse",),
    )

    def execute(
        session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
        *,
        combine: Literal["AND", "OR"],
        policy: Literal["include", "exclude", "only"],
        minimum_yoy_percent: Decimal = Decimal("0"),
    ) -> DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1:
        query = session.create_revenue_query_v1(
            ma_states=("unknown",),
            minimum_yoy_percent=minimum_yoy_percent,
            condition_combine_mode=combine,
            unknown_policy=policy,
            sort_clauses=_sort_clauses(),
        )
        return session.execute_revenue_query_v1(query)

    include_result = execute(and_session, combine="AND", policy="include")
    exclude_result = execute(and_session, combine="AND", policy="exclude")
    and_only_result = execute(and_session, combine="AND", policy="only")

    # AND：MA 全 unknown 且營收只有 1000 可判 match，因此所有 hard-eligible
    # 列的合取 truth 都是 unknown；include/only 可見，exclude 不可見。
    assert include_result.counts.hard_eligible_count == 256
    assert include_result.counts.visible_count == 256
    assert include_result.counts.eligible_truth_counts == (
        ("match", 0), ("no_match", 0), ("unknown", 256),
        ("not_evaluated", 0), ("not_applicable", 0),
    )
    assert exclude_result.counts.hard_eligible_count == 256
    assert exclude_result.counts.visible_count == 0
    assert dict(exclude_result.counts.composite_truth_counts)["not_evaluated"] == 1
    assert and_only_result.counts.hard_eligible_count == 256
    assert and_only_result.counts.visible_count == 256
    assert dict(and_only_result.counts.eligible_truth_counts)["unknown"] == 256

    # OR：技術條件只接受來源 state=unknown；對已知 state 是 no_match。
    # MA 全 unknown、營收 1000 match／其餘 unknown，故 eligible 為 1 match + 255 unknown。
    unknown_rule_session = revenue_context.session.with_conditions(
        row_scope_filter=_ALL_ROW_SCOPES,
        rule_state_filters=(DailyMarketTechnicalRuleStateFilterV4.create(rule_key, ("unknown",)),),
        market_assignment_states=("assigned_twse",),
    )
    or_include_result = execute(unknown_rule_session, combine="OR", policy="include")
    or_exclude_result = execute(unknown_rule_session, combine="OR", policy="exclude")
    only_result = execute(unknown_rule_session, combine="OR", policy="only")
    eligible_truths = dict(only_result.counts.eligible_truth_counts)
    assert eligible_truths["match"] == 1
    assert eligible_truths["unknown"] == 255
    assert only_result.counts.hard_eligible_count == 256
    assert only_result.counts.visible_count == 255
    assert only_result.counts.unknown_policy_included_count == 255
    assert only_result.counts.unknown_policy_excluded_count == 0
    assert or_include_result.counts.visible_count == 256
    assert or_exclude_result.counts.visible_count == 1
    assert dict(or_include_result.counts.eligible_truth_counts) == eligible_truths
    assert dict(or_exclude_result.counts.eligible_truth_counts) == eligible_truths
    assert dict(or_exclude_result.counts.eligible_truth_counts)["no_match"] == 0
    assert tuple(key.stock_code for key in or_exclude_result.ordered_sort_keys) == ("1000",)
    assert tuple(key.stock_code for key in only_result.ordered_sort_keys[:3]) == (
        "1001", "1002", "1003",
    )

    # 以同一份已核 22.006875% 原始事實套 25% 門檻：AND 中 1000 的營收 no_match
    # 壓過 MA unknown；OR 則由該股票技術組的明確 match 使整體 match。
    strict_and = execute(
        and_session, combine="AND", policy="include", minimum_yoy_percent=Decimal("25"),
    )
    assert dict(strict_and.counts.eligible_truth_counts)["no_match"] == 1
    assert dict(strict_and.counts.eligible_truth_counts)["unknown"] == 255
    assert "1000" not in {key.stock_code for key in strict_and.ordered_sort_keys}

    strict_or = execute(
        and_session, combine="OR", policy="exclude", minimum_yoy_percent=Decimal("25"),
    )
    strict_or_page = strict_or.read_page(0, 4)
    row_1000 = next(row for row in strict_or_page.rows if row.fact_row.stock_code == "1000")
    assert row_1000.technical_condition_truth == "match"
    assert row_1000.ma_condition_truth == "unknown"
    assert row_1000.revenue_condition_truth == "no_match"
    assert row_1000.composite_condition_truth == "match"
    assert dict(strict_or.counts.eligible_truth_counts)["match"] == 256
    assert dict(strict_or.counts.eligible_truth_counts)["no_match"] == 0


def test_monthly_index_cutoff_mismatch_is_rejected_on_same_exact_session(
    revenue_context: _RevenueContext,
    tmp_path: Path,
) -> None:
    provider = _seed_provider(tmp_path / "cutoff-mismatch-provider")
    mismatched_index_session = DailyMarketMonthlyRevenueYoyIndexSessionV1.open(
        provider,
        snapshot_root=tmp_path / "cutoff-mismatch-snapshot",
        stock_codes=("1000",),
        cutoff_at=revenue_context.cutoff + timedelta(minutes=1),
    )
    mismatched_index_session.load_batch(("1000",))
    mismatched_index_session.finish()

    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionQueryReaderV1Error,
        match="monthly_revenue_index_scope_mismatch",
    ):
        revenue_context.session.with_monthly_revenue_yoy_index(mismatched_index_session)


def test_pending_rows_require_incomplete_store_and_cannot_become_qualified_bundle(
    bundle_fixture: Any,
) -> None:
    fixture = bundle_fixture
    store_state = DailyMarketTechnicalUniverseV4StoreReader(fixture.store_root).read_exact(
        fixture.generation_identity_sha256,
        fixture.plan_identity_sha256,
        fixture.receipt_identity_sha256,
        expected_receipt_sha256=fixture.expected_receipt_sha256,
        expected_plan_sha256=fixture.expected_plan_sha256,
    )
    plan = store_state.plan
    partial_store_root = fixture.scope.root / "f12-pending-probe-store"
    store_writer = DailyMarketTechnicalUniverseV4StoreWriter(
        partial_store_root,
        research_scope=fixture.scope,
    )
    initial_receipt = store_writer.start(plan)
    segment_index, parent_reference = store_state.segment_parent_references[0]
    assert segment_index == 0
    partial_receipt = store_writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        initial_receipt.identity_sha256,
        expected_previous_receipt_sha256=initial_receipt.content_sha256,
        segment_index=segment_index,
        parent_reference=parent_reference,
    )
    partial_state = DailyMarketTechnicalUniverseV4StoreReader(partial_store_root).read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        partial_receipt.identity_sha256,
        expected_receipt_sha256=partial_receipt.content_sha256,
        expected_plan_sha256=fixture.expected_plan_sha256,
    )
    assert partial_state.receipt.status == "partial"
    assert partial_state.counts.pending_count == 1

    # 只用原 exact source 的第一段 parent 建出真的 incomplete receipt；沒有改寫原 store。
    # Bundle 可保存 diagnostic row，但正常 exact query opener 必須拒絕 partial receipt。

    partial_bundle_root = fixture.scope.root / "f12-pending-probe-bundle"
    partial_reference = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        partial_bundle_root,
        research_scope=fixture.scope,
    ).create_from_pins(
        store_output_root=partial_store_root,
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        expected_plan_sha256=fixture.expected_plan_sha256,
        receipt_identity_sha256=partial_receipt.identity_sha256,
        expected_receipt_sha256=partial_receipt.content_sha256,
        market_assignment_source_pin=fixture.market_pin,
        official_disposal_source_pin=fixture.disposal_pin,
    )
    assert partial_reference.technical_receipt_status == "partial"
    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionQueryReaderV1Error,
        match="bundle_exact_read_failed:manifest_metadata_technical_receipt_not_complete",
    ):
        open_daily_market_technical_official_disposition_bundle_session_v1(
            bundle_output_root=partial_reference.output_root,
            bundle_identity_sha256=partial_reference.bundle_identity_sha256,
            expected_manifest_sha256=partial_reference.manifest_sha256,
            row_scope_filter=_ALL_ROW_SCOPES,
        )


def test_rehashed_query_cannot_replace_the_attached_monthly_source(
    revenue_context: _RevenueContext,
) -> None:
    query = revenue_context.session.create_revenue_query_v1(
        ma_states=("unknown",), minimum_yoy_percent=Decimal("0"),
    )
    payload = json.loads(query.to_json())
    payload["monthly_yoy_index_identity_sha256"] = "f" * 64
    body = {key: value for key, value in payload.items() if key != "query_identity_sha256"}
    payload["query_identity_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    internally_consistent = DailyMarketTechnicalOfficialDispositionRevenueQueryV1.from_dict(payload)
    assert internally_consistent.to_json() == json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        revenue_context.session.execute_revenue_query_v1(internally_consistent)


def test_cancelled_query_does_not_issue_a_partial_result(
    revenue_context: _RevenueContext,
) -> None:
    query = revenue_context.session.create_revenue_query_v1(
        ma_states=("unknown",), minimum_yoy_percent=Decimal("0"),
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error, match="cancelled"):
        revenue_context.session.execute_revenue_query_v1(query, cancel_callback=lambda: True)

