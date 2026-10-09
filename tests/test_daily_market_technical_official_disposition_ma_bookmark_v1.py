"""MA 複合研究收藏以真保存 bundle 驗證 exact 重開與原子拒絕。"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any, cast

import pytest

from app_module.daily_market_technical_official_disposition_ma_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_BYTES,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_SCHEMA,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE,
    DailyMarketTechnicalOfficialDispositionMaBookmarkV1,
    DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error,
    read_daily_market_technical_official_disposition_ma_bookmark_context_v1,
    read_daily_market_technical_official_disposition_ma_bookmark_v1,
)
from app_module.daily_market_technical_official_disposition_ma_comparison_v1 import (
    DailyMarketTechnicalOfficialDispositionMaComparisonV1,
    DailyMarketTechnicalOfficialDispositionMaComparisonV1Error,
    DailyMarketTechnicalOfficialDispositionMaSelectionV1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES,
    DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
    DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader_module
from test_daily_market_technical_official_disposition_ma_comparison_v1 import (  # type: ignore[import-not-found]
    _MaContext,
    ma_context,
)


def _bookmark(context: _MaContext) -> DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
    selected = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        context.page_zero, "1000",
    )
    second_page_selection = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        context.page_one, "1004",
    )
    return DailyMarketTechnicalOfficialDispositionMaBookmarkV1.create(
        query=context.query,
        page=context.page_zero,
        stock_code="1000",
        scroll_position=321,
        comparison_selections=(selected, second_page_selection),
    )


def test_bookmark_roundtrip_reopens_exact_query_pages_and_unknown_facts(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _bookmark(ma_context)
    restored = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json(
        bookmark.to_json()
    )
    assert restored == bookmark
    assert restored.bookmark_id == restored.bookmark_identity_sha256
    assert restored.stock_code == "1000"
    assert restored.source == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE
    assert restored.schema_version == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_SCHEMA
    assert restored.query.query_identity_sha256 == ma_context.query.query_identity_sha256
    assert restored.scroll_position == 321
    assert tuple(item.stock_code for item in restored.comparison_selections) == ("1000", "1004")
    assert tuple(item.page_index for item in restored.comparison_selections) == (0, 1)

    exact_open_calls: list[tuple[object, ...]] = []
    original_open = reader_module.open_daily_market_technical_official_disposition_read_session_v1

    def tracked_open(*args: object, **kwargs: object) -> Any:
        exact_open_calls.append(args)
        return original_open(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        reader_module,
        "open_daily_market_technical_official_disposition_read_session_v1",
        tracked_open,
    )
    state = read_daily_market_technical_official_disposition_ma_bookmark_v1(
        restored.to_json()
    )
    assert len(exact_open_calls) == 1
    assert state.bookmark.bookmark_id == restored.bookmark_id
    assert state.selected.row.stock_code == "1000"
    assert tuple(item.row.stock_code for item in state.comparison_selections) == ("1000", "1004")
    assert tuple(item.selection.page_index for item in state.comparison_selections) == (0, 1)
    assert state.selected.row.to_dict() == ma_context.page_zero.rows[0].to_dict()
    assert state.comparison_selections[1].row.to_dict() == ma_context.page_one.rows[0].to_dict()
    assert state.selected.row.ma_entry is not None
    assert state.selected.row.ma_entry.ma_state == "unknown"
    assert state.selected.row.ma_entry.ma_reason_codes
    assert state.selected.row.ma_entry.raw_row_count < 60
    assert state.scope == "current_only"
    assert state.source_available_at is None
    assert state.availability_status == "unknown"
    assert state.historical_pit_eligible is False

    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="state_invalid"):
        replace(state, scope="not-current-only")


@pytest.mark.parametrize("comparison_count", (1, 6))
def test_bookmark_rejects_invalid_comparison_count_atomically(
    ma_context: _MaContext,
    comparison_count: int,
) -> None:
    selection = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )
    other = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_one, "1004",
    )
    values: tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...]
    if comparison_count == 1:
        values = (selection,)
    else:
        from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
            DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
        )

        page_two = ma_context.result.read_page_request(
            DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
                ma_context.query, page_index=2, page_size=4,
            )
        )
        values = (
            selection,
            other,
            *(
                DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
                    ma_context.page_one, code,
                )
                for code in ("1005", "1006", "1007")
            ),
            DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
                page_two, "1008",
            ),
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error):
        DailyMarketTechnicalOfficialDispositionMaBookmarkV1.create(
            query=ma_context.query,
            page=ma_context.page_zero,
            stock_code="1000",
            scroll_position=0,
            comparison_selections=values,
        )


def test_bookmark_rejects_duplicate_stock_and_mixed_query_selections(
    ma_context: _MaContext,
) -> None:
    selection = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="comparison_duplicate_stock"):
        DailyMarketTechnicalOfficialDispositionMaBookmarkV1.create(
            query=ma_context.query,
            page=ma_context.page_zero,
            stock_code="1000",
            scroll_position=0,
            comparison_selections=(selection, selection),
        )

    second_page = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_one, "1004",
    )
    altered_payload = second_page.to_dict()
    altered_payload["query_identity_sha256"] = "0" * 64
    altered_body = {
        key: value for key, value in altered_payload.items()
        if key != "selection_identity_sha256"
    }
    altered_payload["selection_identity_sha256"] = hashlib.sha256(
        json.dumps(
            altered_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    altered_selection = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_dict(
        altered_payload
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error):
        DailyMarketTechnicalOfficialDispositionMaBookmarkV1.create(
            query=ma_context.query,
            page=ma_context.page_zero,
            stock_code="1000",
            scroll_position=0,
            comparison_selections=(altered_selection, second_page),
        )


def test_exact_reader_rejects_a_rehashed_source_pin_without_publishing_state(
    ma_context: _MaContext,
) -> None:
    bookmark = _bookmark(ma_context)
    payload = bookmark.to_dict()
    selected = payload["selected"]
    comparisons = payload["comparison_selections"]
    assert isinstance(selected, dict) and isinstance(comparisons, list)
    all_selections = (selected, *comparisons)
    for item in all_selections:
        assert isinstance(item, dict)
        pins = item["source_pins"]
        assert isinstance(pins, list)
        for pair in pins:
            if pair[0] == "p01_receipt_sha256":
                pair[1] = "f" * 64
        body = {key: value for key, value in item.items() if key != "selection_identity_sha256"}
        item["selection_identity_sha256"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    changed_pins = selected["source_pins"]
    assert isinstance(changed_pins, list)
    payload["source_pins"] = changed_pins
    body = {key: value for key, value in payload.items() if key != "bookmark_identity_sha256"}
    payload["bookmark_identity_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    forged_transport = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_dict(payload)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="reopened_result_mismatch"):
        read_daily_market_technical_official_disposition_ma_bookmark_v1(forged_transport)


def test_cancel_and_callback_errors_never_return_or_open_a_bookmark_state(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _bookmark(ma_context)

    def forbidden_open(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("取消前不應開啟任何來源")

    monkeypatch.setattr(
        reader_module,
        "open_daily_market_technical_official_disposition_read_session_v1",
        forbidden_open,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="cancelled"):
        read_daily_market_technical_official_disposition_ma_bookmark_v1(
            bookmark, cancel_callback=lambda: True,
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="cancel_callback_invalid"):
        read_daily_market_technical_official_disposition_ma_bookmark_v1(
            bookmark, cancel_callback=lambda: 1,
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="cancel_check_failed"):
        read_daily_market_technical_official_disposition_ma_bookmark_v1(
            bookmark, cancel_callback=lambda: (_ for _ in ()).throw(RuntimeError("test")),
        )


def test_bookmark_json_has_separate_bounded_namespace_and_rejects_bad_encoding(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _bookmark(ma_context)
    encoded = bookmark.to_json()
    assert len(encoded.encode("utf-8")) <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_BYTES
    assert DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_BYTES == 64 * 1024 * 1024
    assert DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES == 32 * 1024 * 1024
    assert bookmark.schema_version != "daily-market-technical-official-disposition-bookmark.v1"
    assert DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE.startswith(
        "technical_official_disposition_ma_"
    )

    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="duplicate_json_key"):
        DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json('{"x":0,"x":0}')
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="float_forbidden"):
        DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json('{"x":1.25}')
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="json_depth_limit"):
        DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json("[" * 40 + "0" + "]" * 40)

    monkeypatch.setattr(
        "app_module.daily_market_technical_official_disposition_ma_bookmark_v1.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_BYTES",
        16,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="byte_limit"):
        DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json(" " * 17)


def test_selection_requires_parent_query_context_for_exact_restore(ma_context: _MaContext) -> None:
    selected = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )
    assert not hasattr(selected, "reopen")
    assert selected.query_identity_sha256 == ma_context.query.query_identity_sha256


def test_restore_context_reuses_one_exact_result_for_other_pages_and_returns_to_selection(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _bookmark(ma_context)
    exact_open_calls: list[tuple[object, ...]] = []
    execute_calls: list[str] = []
    original_open = reader_module.open_daily_market_technical_official_disposition_read_session_v1
    session_type = reader_module.DailyMarketTechnicalOfficialDispositionReadSessionV1
    original_execute = session_type.execute_ma_query_v1

    def tracked_open(*args: object, **kwargs: object) -> Any:
        exact_open_calls.append(args)
        return original_open(*args, **kwargs)  # type: ignore[arg-type]

    def tracked_execute(self: object, query: object, **kwargs: object) -> Any:
        query_identity = getattr(query, "query_identity_sha256", None)
        assert isinstance(query_identity, str)
        execute_calls.append(query_identity)
        return original_execute(self, query, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        reader_module,
        "open_daily_market_technical_official_disposition_read_session_v1",
        tracked_open,
    )
    monkeypatch.setattr(session_type, "execute_ma_query_v1", tracked_execute)

    context = read_daily_market_technical_official_disposition_ma_bookmark_context_v1(
        bookmark.to_json(),
    )
    assert len(exact_open_calls) == 1
    assert execute_calls == [bookmark.query.query_identity_sha256]
    assert context.query.to_json() == bookmark.query_json
    assert context.state.bookmark.bookmark_id == bookmark.bookmark_id
    assert context.state.selected.row.stock_code == "1000"
    assert not hasattr(context, "session")
    assert not hasattr(context, "result")

    later_request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        context.query,
        page_index=2,
        page_size=4,
    )
    later_page = context.read_page_request(later_request)
    assert tuple(row.stock_code for row in later_page.rows) == ("1008", "1009", "1010", "1011")
    assert later_page.operation_identity_sha256 == context.state.selected.selection.result_identity_sha256
    assert later_page.source_pins == context.state.selected.selection.source_pins

    returned_page = context.read_page_request(
        DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            context.query,
            page_index=context.state.selected.selection.page_index,
            page_size=context.state.selected.selection.page_size,
        )
    )
    assert returned_page.page_identity_sha256 == context.state.selected.page.page_identity_sha256
    later_selection = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        later_page,
        "1008",
    )
    comparison = DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(
        context.query,
        (context.state.selected.selection, later_selection),
    )
    assert tuple(item.page_index for item in comparison.selections) == (0, 2)
    assert len(exact_open_calls) == 1
    assert execute_calls == [bookmark.query.query_identity_sha256]


def test_restore_context_requeries_changed_conditions_on_same_exact_session(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _bookmark(ma_context)
    exact_open_calls: list[tuple[object, ...]] = []
    original_open = reader_module.open_daily_market_technical_official_disposition_read_session_v1
    session_type = reader_module.DailyMarketTechnicalOfficialDispositionReadSessionV1
    original_execute = session_type.execute_ma_query_v1
    executed_queries: list[Any] = []

    def tracked_open(*args: object, **kwargs: object) -> Any:
        exact_open_calls.append(args)
        return original_open(*args, **kwargs)  # type: ignore[arg-type]

    def tracked_execute(self: object, query: object, **kwargs: object) -> Any:
        executed_queries.append(query)
        return original_execute(self, query, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        reader_module,
        "open_daily_market_technical_official_disposition_read_session_v1",
        tracked_open,
    )
    monkeypatch.setattr(session_type, "execute_ma_query_v1", tracked_execute)
    context = read_daily_market_technical_official_disposition_ma_bookmark_context_v1(
        bookmark,
    )
    assert len(exact_open_calls) == 1
    assert len(executed_queries) == 1
    original_query_json = context.query.to_json()
    original_operation_identity = context._anchor.result.operation_identity_sha256
    original_source_pins = context._anchor.result.source_pins
    original_ma_session_identity = context.query.ma_alignment_read_session_identity_sha256
    saved_1001 = next(row for row in ma_context.page_zero.rows if row.stock_code == "1001")
    assert saved_1001.technical_row is not None
    assert saved_1001.technical_row.rule("ma5_20_golden_cross").state == "no_match"
    assert saved_1001.ma_entry is not None and saved_1001.ma_entry.ma_state == "unknown"

    result = context.execute_query_conditions(
        row_scope_filter=("included_processed",),
        rule_state_filters=(
            DailyMarketTechnicalRuleStateFilterV4.create(
                "ma5_20_golden_cross", ("no_match",),
            ),
        ),
        combine_mode="AND",
        market_assignment_states=(),
        official_disposal_states=(),
        outer_stock_filter_mode="explicit_codes",
        outer_stock_codes=("1001",),
        f17_sort_clauses=(
            DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),
        ),
        ma_states=("unknown",),
        condition_combine_mode="AND",
        unknown_policy="include",
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1("ma_alignment_state", "desc"),
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),
        ),
    )

    assert len(exact_open_calls) == 1
    assert len(executed_queries) == 2
    new_query = result.query
    assert new_query.query_identity_sha256 != context.query.query_identity_sha256
    assert new_query.f17_query.outer_stock_filter_mode == "explicit_codes"
    assert new_query.f17_query.outer_stock_codes == ("1001",)
    assert new_query.f17_query.technical_query.rule_state_filters[0].rule_key == "ma5_20_golden_cross"
    assert new_query.f17_query.technical_query.rule_state_filters[0].states == ("no_match",)
    assert executed_queries[1].query_identity_sha256 == new_query.query_identity_sha256
    assert result.source_pins == original_source_pins
    assert new_query.ma_alignment_read_session_identity_sha256 == original_ma_session_identity
    assert result.operation_identity_sha256 != original_operation_identity
    assert result.counts.visible_count == 1
    page = result.read_page_request(
        DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            new_query,
            page_index=0,
            page_size=4,
        )
    )
    assert tuple(row.stock_code for row in page.rows) == ("1001",)
    assert page.rows[0].technical_row is not None
    assert page.rows[0].technical_row.rule("ma5_20_golden_cross").state == "no_match"
    assert page.rows[0].ma_entry is not None and page.rows[0].ma_entry.ma_state == "unknown"
    assert page.operation_identity_sha256 == result.operation_identity_sha256
    assert dict(result.counts.eligible_truth_counts)["unknown"] == 1

    rejected_by_saved_truth = context.execute_query_conditions(
        row_scope_filter=("included_processed",),
        rule_state_filters=(
            DailyMarketTechnicalRuleStateFilterV4.create(
                "ma5_20_golden_cross", ("match",),
            ),
        ),
        combine_mode="AND",
        market_assignment_states=(),
        official_disposal_states=(),
        outer_stock_filter_mode="explicit_codes",
        outer_stock_codes=("1001",),
        f17_sort_clauses=(
            DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),
        ),
        ma_states=("unknown",),
        condition_combine_mode="AND",
        unknown_policy="include",
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1("ma_alignment_state", "desc"),
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),
        ),
    )
    assert len(exact_open_calls) == 1
    assert len(executed_queries) == 3
    assert rejected_by_saved_truth.query.f17_query.outer_stock_codes == ("1001",)
    assert rejected_by_saved_truth.source_pins == original_source_pins
    assert rejected_by_saved_truth.counts.hard_eligible_count == 1
    assert rejected_by_saved_truth.counts.visible_count == 0
    assert dict(rejected_by_saved_truth.counts.ma_truth_counts)["unknown"] == dict(
        ma_context.result.counts.ma_truth_counts
    )["unknown"]
    assert dict(rejected_by_saved_truth.counts.eligible_truth_counts)["no_match"] == 1
    rejected_page = rejected_by_saved_truth.read_page_request(
        DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            rejected_by_saved_truth.query,
            page_index=0,
            page_size=4,
        )
    )
    assert rejected_page.rows == ()
    assert rejected_page.operation_identity_sha256 == rejected_by_saved_truth.operation_identity_sha256
    assert context.query.to_json() == original_query_json
    assert context.state.bookmark.query_json == original_query_json
    assert context._anchor.result.operation_identity_sha256 == original_operation_identity


def test_restore_context_conditions_reject_invalid_state_and_cancel_before_requery(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _bookmark(ma_context)
    context = read_daily_market_technical_official_disposition_ma_bookmark_context_v1(
        bookmark,
    )
    session_type = reader_module.DailyMarketTechnicalOfficialDispositionReadSessionV1
    original_with_conditions = session_type.with_conditions
    calls: list[str] = []

    def tracked_with_conditions(self: object, **kwargs: object) -> Any:
        calls.append("with_conditions")
        return original_with_conditions(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(session_type, "with_conditions", tracked_with_conditions)

    def execute_test_case(*, ma_states: Any, cancel_callback: Any = None) -> Any:
        return context.execute_query_conditions(
            row_scope_filter=("included_processed",),
            rule_state_filters=(),
            combine_mode="AND",
            market_assignment_states=(),
            official_disposal_states=(),
            outer_stock_filter_mode="all",
            outer_stock_codes=(),
            f17_sort_clauses=(
                DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),
            ),
            ma_states=ma_states,
            condition_combine_mode="AND",
            unknown_policy="include",
            sort_clauses=(
                DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),
            ),
            cancel_callback=cancel_callback,
        )

    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="restore_conditions_ma_states_invalid"):
        execute_test_case(ma_states=object())
    assert calls == []

    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="cancelled"):
        execute_test_case(ma_states=None, cancel_callback=lambda: True)
    assert calls == []
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="cancel_callback_invalid"):
        execute_test_case(ma_states=None, cancel_callback=lambda: 1)
    assert calls == []


def test_restore_context_requery_rejects_descending_stock_code_tiebreak(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _bookmark(ma_context)
    context = read_daily_market_technical_official_disposition_ma_bookmark_context_v1(bookmark)
    session_type = reader_module.DailyMarketTechnicalOfficialDispositionReadSessionV1
    calls: list[str] = []
    original_with_conditions = session_type.with_conditions
    original_create_query = session_type.create_ma_query_v1
    original_execute_query = session_type.execute_ma_query_v1

    def tracked_with_conditions(self: object, **kwargs: object) -> Any:
        calls.append("with_conditions")
        return original_with_conditions(self, **kwargs)  # type: ignore[arg-type]

    def tracked_create_query(self: object, **kwargs: object) -> Any:
        calls.append("create_ma_query")
        return original_create_query(self, **kwargs)  # type: ignore[arg-type]

    def tracked_execute_query(self: object, *args: object, **kwargs: object) -> Any:
        calls.append("execute_ma_query")
        return original_execute_query(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(session_type, "with_conditions", tracked_with_conditions)
    monkeypatch.setattr(session_type, "create_ma_query_v1", tracked_create_query)
    monkeypatch.setattr(session_type, "execute_ma_query_v1", tracked_execute_query)

    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error,
        match="restore_conditions_failed",
    ):
        context.execute_query_conditions(
            row_scope_filter=("included_processed",),
            rule_state_filters=(),
            combine_mode="AND",
            market_assignment_states=(),
            official_disposal_states=(),
            outer_stock_filter_mode="all",
            outer_stock_codes=(),
            f17_sort_clauses=(
                DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),
            ),
            ma_states=None,
            condition_combine_mode="AND",
            unknown_policy="include",
            sort_clauses=(
                DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "desc"),
            ),
        )

    assert calls == ["with_conditions", "create_ma_query"]


def test_restore_context_seals_state_result_query_and_cancelled_page_reads(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bookmark = _bookmark(ma_context)
    context = read_daily_market_technical_official_disposition_ma_bookmark_context_v1(bookmark)
    request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        context.query,
        page_index=2,
        page_size=4,
    )

    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="restore_context_not_reader_issued"):
        replace(context)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="restore_context_not_reader_issued"):
        replace(context, state=context.state)
    with pytest.raises(ValueError):
        replace(context._anchor.result, operation_identity_sha256="f" * 64)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="state_invalid"):
        replace(context.state)

    other_query = ma_context.session.create_ma_query_v1(
        ma_states=("match",),
        condition_combine_mode="AND",
        unknown_policy="include",
    )
    other_request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        other_query,
        page_index=0,
        page_size=4,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="restore_page_request_query_mismatch"):
        context.read_page_request(other_request)

    result_type = type(context._anchor.result)
    original_read = result_type.read_page_request
    calls: list[str] = []

    def tracked_read(self: object, *args: object, **kwargs: object) -> Any:
        calls.append("read")
        return original_read(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(result_type, "read_page_request", tracked_read)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="cancelled"):
        context.read_page_request(request, cancel_callback=lambda: True)
    assert calls == []

    cancelled = False

    def cancel_after_real_page(self: object, *args: object, **kwargs: object) -> Any:
        nonlocal cancelled
        page = original_read(self, *args, **kwargs)  # type: ignore[arg-type]
        cancelled = True
        return page

    monkeypatch.setattr(result_type, "read_page_request", cancel_after_real_page)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error, match="cancelled"):
        context.read_page_request(request, cancel_callback=lambda: cancelled)
