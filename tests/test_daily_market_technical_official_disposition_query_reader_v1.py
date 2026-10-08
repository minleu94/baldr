"""F17 full-N reader 以真 synthetic store 與 exact source bundle 驗收。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, cast

import pytest

from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionPageRequestV1,
    DailyMarketTechnicalOfficialDispositionQueryPageV1,
    DailyMarketTechnicalOfficialDispositionQueryReaderV1Error,
    DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled,
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1,
    _check_source_error_cancelled,
    open_daily_market_technical_official_disposition_read_session_v1,
    read_daily_market_technical_official_disposition_page_v1,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4QueryError,
    open_daily_market_technical_universe_v4_read_session,
)

from test_daily_market_technical_official_disposition_bundle_v1 import (  # type: ignore[import-not-found]
    bundle_fixture,
    _tree_signature,
)
from test_daily_market_technical_official_disposition_query_v1 import (  # type: ignore[import-not-found]
    _query as _pure_query,
)


_CUTOFF = datetime.fromisoformat("2026-10-07T16:00:00+08:00")


def test_page_request_roundtrip_is_canonical_and_query_bound() -> None:
    request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
        _pure_query(),
        page_index=2,
        page_size=25,
    )
    assert DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
        request.to_json()
    ) == request
    payload = json.loads(request.to_json())
    payload["page_index"] = 3
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )


@pytest.mark.parametrize(
    ("source_code", "cancelled"),
    (
        ("technical_universe_v4_query_cancelled", True),
        ("technical_universe_v4_query_cancel_callback_invalid", False),
        ("technical_universe_v4_query_cancel_callback_failed", False),
        ("technical_universe_v4_read_hash_mismatch", False),
    ),
)
def test_only_named_source_cancel_errors_are_normalized(
    source_code: str,
    cancelled: bool,
) -> None:
    source_error = DailyMarketTechnicalUniverseV4QueryError(source_code)
    if cancelled:
        with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled):
            _check_source_error_cancelled(source_error)
    else:
        _check_source_error_cancelled(source_error)


@pytest.fixture(scope="module")
def exact_query(bundle_fixture: Any) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    fixture = bundle_fixture
    technical_session = open_daily_market_technical_universe_v4_read_session(
        store_output_root=fixture.store_root,
        generation_identity_sha256=fixture.generation_identity_sha256,
        plan_identity_sha256=fixture.plan_identity_sha256,
        plan_sha256=fixture.expected_plan_sha256,
        receipt_identity_sha256=fixture.receipt_identity_sha256,
        receipt_sha256=fixture.expected_receipt_sha256,
    )
    technical_query = technical_session.create_query(
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=1,
    )
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=technical_query,
        decision_cutoff=_CUTOFF,
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        market_assignment_pin_identity_sha256=fixture.market_pin.identity_sha256,
        official_disposal_pin_identity_sha256=fixture.disposal_pin.identity_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
    )


@pytest.fixture(scope="module")
def exact_read_session(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
    return open_daily_market_technical_official_disposition_read_session_v1(exact_query)


def test_real_257_cross_segment_join_sort_and_page_uses_exact_rows_materializer(
    bundle_fixture: Any,
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    fixture = bundle_fixture
    query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=exact_query.technical_query,
        decision_cutoff=exact_query.decision_cutoff,
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        market_assignment_pin_identity_sha256=fixture.market_pin.identity_sha256,
        official_disposal_pin_identity_sha256=fixture.disposal_pin.identity_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        sort_clauses=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "desc"),),
    )
    session = open_daily_market_technical_official_disposition_read_session_v1(query)
    result = session.execute()

    counts = result.counts
    assert counts.population.declared_count == 258
    assert counts.population.included_count == 257
    assert counts.population.excluded_count == 1
    assert counts.population.processed_count == 257
    assert counts.population.pending_count == 0
    assert counts.matching_count == 258
    assert dict(counts.market_state_counts) == {
        "assigned_twse": 256,
        "assigned_tpex": 1,
        "unknown": 1,
    }
    assert dict(counts.disposal_state_counts) == {
        "reported_upcoming": 1,
        "reported_active": 1,
        "reported_elapsed_only": 0,
        "unknown": 256,
    }

    request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
        query,
        page_index=0,
        page_size=20,
    )
    reopened_request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
        request.to_json()
    )
    page = result.read_page_request(reopened_request)
    expected_codes = (fixture.excluded_code, *reversed(fixture.included_codes[-19:]))
    assert tuple(row.stock_code for row in page.rows) == expected_codes
    assert page.page_count == 13
    assert page.result_status == "partial"
    assert page.technical_processing_status == "complete"
    assert page.official_source_coverage_status == "partial"
    assert page.scope == "current_only"
    assert page.official_available_at is None
    assert page.historical_pit_eligible is False
    assert page.full_market_claim is False
    assert page.rows[0].fact_row.to_dict()["exclusion_reason"] == "合成母體明示排除，保留於 declared 分母"
    assert page.rows[0].technical_row is None
    assert all(row.technical_row is not None for row in page.rows[1:])
    assert fixture.original_signatures == tuple(
        (path, _tree_signature(Path(path))) for path, _ in fixture.original_signatures
    )


def test_warm_page_reads_only_selected_bundle_rows_without_legacy_prefix_scan(
    bundle_fixture: Any,
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=exact_query.technical_query,
        decision_cutoff=exact_query.decision_cutoff,
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        market_assignment_pin_identity_sha256=fixture.market_pin.identity_sha256,
        official_disposal_pin_identity_sha256=fixture.disposal_pin.identity_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        sort_clauses=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "desc"),),
    )
    result = open_daily_market_technical_official_disposition_read_session_v1(query).execute()
    selected_calls: list[tuple[str, ...]] = []
    legacy_iterator_calls = 0
    original_selected = DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1.read_selected_rows
    original_iterator = DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1.iter_verified_rows

    def tracked_selected(
        state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        codes: Any,
        *,
        cancel_callback: Any = None,
    ) -> Any:
        selected_calls.append(tuple(codes))
        return original_selected(state, codes, cancel_callback=cancel_callback)

    def tracked_iterator(
        state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        *,
        cancel_callback: Any = None,
    ) -> Any:
        nonlocal legacy_iterator_calls
        legacy_iterator_calls += 1
        yield from original_iterator(state, cancel_callback=cancel_callback)

    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        "read_selected_rows",
        tracked_selected,
    )
    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        "iter_verified_rows",
        tracked_iterator,
    )
    page = result.read_page(0, 20)
    expected_codes = (fixture.excluded_code, *reversed(fixture.included_codes[-19:]))

    assert tuple(row.stock_code for row in page.rows) == expected_codes
    assert selected_calls == [expected_codes]
    assert legacy_iterator_calls == 0


def test_query_result_replace_cannot_reorder_verified_keys_even_with_rehashed_public_ids(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader_module

    result = open_daily_market_technical_official_disposition_read_session_v1(
        exact_query
    ).execute()
    assert type(result) is DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1
    reordered_keys = tuple(reversed(result._ordered_sort_keys))
    ordered_codes_sha256 = reader_module._sha256_json(
        [key.stock_code for key in reordered_keys]
    )
    operation_identity = reader_module._query_operation_identity(
        query=result.query,
        bundle_reference=result.bundle_reference,
        p01_read_session_identity_sha256=result.p01_read_session_identity_sha256,
        p01_selection_identity_sha256=result.p01_selection_identity_sha256,
        p01_query_spec_identity_sha256=result.p01_query_spec_identity_sha256,
        counts=result.counts,
        ordered_codes_sha256=ordered_codes_sha256,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        replace(
            result,
            _ordered_sort_keys=reordered_keys,
            ordered_codes_sha256=ordered_codes_sha256,
            operation_identity_sha256=operation_identity,
        )

    changed_unknown_count = (
        result.counts.unknown_rule_stock_count - 1
        if result.counts.unknown_rule_stock_count == result.counts.population.processed_count
        else result.counts.unknown_rule_stock_count + 1
    )
    changed_counts = replace(result.counts, unknown_rule_stock_count=changed_unknown_count)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        replace(result, counts=changed_counts)
    second_session = open_daily_market_technical_official_disposition_read_session_v1(exact_query)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        replace(result, _read_session=second_session)


def test_query_page_replace_binds_full_rows_counts_and_request(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader_module

    result = open_daily_market_technical_official_disposition_read_session_v1(
        exact_query
    ).execute()
    page = result.read_page(0, 20)
    assert type(page) is DailyMarketTechnicalOfficialDispositionQueryPageV1
    reversed_rows = tuple(reversed(page.rows))
    page_identity = reader_module._query_page_identity(
        operation_identity_sha256=page.operation_identity_sha256,
        request_identity_sha256=page.request_identity_sha256,
        page_index=page.page_index,
        page_size=page.page_size,
        stock_codes=tuple(row.stock_code for row in reversed_rows),
        rows=reversed_rows,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        replace(page, rows=reversed_rows, page_identity_sha256=page_identity)
    changed_unknown_count = (
        page.counts.unknown_rule_stock_count - 1
        if page.counts.unknown_rule_stock_count == page.counts.population.processed_count
        else page.counts.unknown_rule_stock_count + 1
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        replace(page, counts=replace(page.counts, unknown_rule_stock_count=changed_unknown_count))
    next_page_index = page.page_index + 1
    request_identity = reader_module.DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
        page.query,
        page_index=next_page_index,
        page_size=page.page_size,
    ).request_identity_sha256
    next_page_identity = reader_module._query_page_identity(
        operation_identity_sha256=page.operation_identity_sha256,
        request_identity_sha256=request_identity,
        page_index=next_page_index,
        page_size=page.page_size,
        stock_codes=tuple(row.stock_code for row in page.rows),
        rows=page.rows,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        replace(
            page,
            page_index=next_page_index,
            request_identity_sha256=request_identity,
            page_identity_sha256=next_page_identity,
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        replace(page, bundle_reference=replace(page.bundle_reference, output_root="C:/changed/root"))


@pytest.mark.parametrize("entrypoint", ("open", "execute", "page", "public_read"))
@pytest.mark.parametrize("final_mode", ("cancel", "invalid", "failed"))
def test_final_return_gate_polls_after_reader_dto_construction(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    exact_read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
    final_mode: str,
) -> None:
    mode = {"value": "normal"}
    operation: Callable[[], object]

    def callback() -> object:
        current = mode["value"]
        if current == "normal":
            return False
        if current == "cancel":
            return True
        if current == "invalid":
            return 1
        raise RuntimeError("synthetic final callback failure")

    if entrypoint == "open":
        original_session_post = DailyMarketTechnicalOfficialDispositionReadSessionV1.__post_init__

        def post_session(self: DailyMarketTechnicalOfficialDispositionReadSessionV1) -> None:
            original_session_post(self)
            mode["value"] = final_mode

        monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionReadSessionV1, "__post_init__", post_session)
        operation = lambda: open_daily_market_technical_official_disposition_read_session_v1(
            exact_query,
            cancel_callback=callback,
        )
    elif entrypoint == "execute":
        original_result_post = DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1.__post_init__

        def post_result(self: DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1) -> None:
            original_result_post(self)
            mode["value"] = final_mode

        monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1, "__post_init__", post_result)
        operation = lambda: exact_read_session.execute(cancel_callback=callback)
    elif entrypoint == "page":
        result = exact_read_session.execute()
        original_page_post = DailyMarketTechnicalOfficialDispositionQueryPageV1.__post_init__

        def post_page(self: DailyMarketTechnicalOfficialDispositionQueryPageV1) -> None:
            original_page_post(self)
            mode["value"] = final_mode

        monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionQueryPageV1, "__post_init__", post_page)
        operation = lambda: result.read_page(0, 20, cancel_callback=callback)
    else:
        request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
            exact_query,
            page_index=0,
            page_size=20,
        )
        original_read_page = DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1.read_page_request

        def read_page_then_change_mode(
            self: DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1,
            page_request: Any,
            *,
            cancel_callback: Any = None,
        ) -> DailyMarketTechnicalOfficialDispositionQueryPageV1:
            page = original_read_page(self, page_request, cancel_callback=cancel_callback)
            mode["value"] = final_mode
            return page

        monkeypatch.setattr(
            DailyMarketTechnicalOfficialDispositionVerifiedQueryResultV1,
            "read_page_request",
            read_page_then_change_mode,
        )
        operation = lambda: read_daily_market_technical_official_disposition_page_v1(
            request,
            cancel_callback=callback,
        )

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error) as error:
        operation()
    if final_mode == "cancel":
        assert isinstance(error.value, DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled)
    elif final_mode == "invalid":
        assert error.value.code == "technical_official_query_reader_v1_cancel_callback_invalid"
    else:
        assert error.value.code == "technical_official_query_reader_v1_cancel_callback_failed"


def test_market_filter_runs_before_global_page_and_keeps_truth_separate_from_membership(
    bundle_fixture: Any,
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    fixture = bundle_fixture
    query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=exact_query.technical_query,
        decision_cutoff=exact_query.decision_cutoff,
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        market_assignment_pin_identity_sha256=fixture.market_pin.identity_sha256,
        official_disposal_pin_identity_sha256=fixture.disposal_pin.identity_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        market_assignment_states=("assigned_tpex",),
        sort_clauses=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),),
    )
    result = open_daily_market_technical_official_disposition_read_session_v1(query).execute()
    assert result.counts.matching_count == 1
    page = result.read_page(0, 1)
    assert tuple(row.stock_code for row in page.rows) == (fixture.included_codes[-1],)
    assert page.rows[0].filter_evaluation.market_assignment_truth == "match"
    assert page.rows[0].overall_match is True
    assert page.counts.population.declared_count == 258
    assert page.counts.membership("combined").matched == 1


def test_fresh_process_reopens_exact_request_without_latest_selection(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=exact_query.technical_query,
        decision_cutoff=exact_query.decision_cutoff,
        bundle_output_root=exact_query.bundle_output_root,
        bundle_identity_sha256=exact_query.bundle_identity_sha256,
        expected_manifest_sha256=exact_query.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=exact_query.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=exact_query.official_disposal_pin_identity_sha256,
        row_scope_filter=exact_query.row_scope_filter,
        sort_clauses=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "desc"),),
    )
    request = DailyMarketTechnicalOfficialDispositionPageRequestV1.create(
        query,
        page_index=0,
        page_size=20,
    )
    script = r"""
import json
import sys
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionPageRequestV1,
    read_daily_market_technical_official_disposition_page_v1,
)
request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(sys.argv[1])
page = read_daily_market_technical_official_disposition_page_v1(request)
print(json.dumps({
    "codes": [row.stock_code for row in page.rows],
    "declared": page.counts.population.declared_count,
    "matching": page.matching_count,
    "bundle": page.bundle_reference.bundle_identity_sha256,
    "operation": page.operation_identity_sha256,
}, ensure_ascii=False, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, request.to_json()],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=True,
        text=True,
        timeout=240,
    )
    payload = json.loads(completed.stdout.strip())
    assert payload["declared"] == 258
    assert payload["matching"] == 258
    assert payload["bundle"] == query.bundle_identity_sha256
    assert payload["codes"][0] == "9999"
    assert payload["codes"][1:] == [f"{code:04d}" for code in range(1256, 1237, -1)]
    assert len(payload["operation"]) == 64


def test_execute_cancellation_never_returns_partial_result(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    session = open_daily_market_technical_official_disposition_read_session_v1(exact_query)
    polls = 0

    def cancel_during_scan() -> bool:
        nonlocal polls
        polls += 1
        return polls > 40

    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        session.execute(cancel_callback=cancel_during_scan)
    assert polls > 40
