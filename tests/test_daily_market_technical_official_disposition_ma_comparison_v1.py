"""F17／MA 比較契約以真保存 bundle 驗證跨頁 exact 重開。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
from typing import Any, Callable

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)

from app_module.daily_market_technical_official_disposition_ma_comparison_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_BYTES,
    DailyMarketTechnicalOfficialDispositionMaComparisonV1,
    DailyMarketTechnicalOfficialDispositionMaComparisonV1Error,
    DailyMarketTechnicalOfficialDispositionMaSelectionV1,
    read_daily_market_technical_official_disposition_ma_comparison_v1,
    read_daily_market_technical_official_disposition_ma_selections_v1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    open_daily_market_technical_official_disposition_bundle_session_v1,
)
import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader_module
_CUTOFF = datetime.fromisoformat("2026-10-07T16:00:00+08:00")


@dataclass(frozen=True, slots=True)
class _MaContext:
    session: Any
    query: Any
    result: Any
    page_zero: Any
    page_one: Any


@pytest.fixture(scope="module")
def ma_context(bundle_fixture: Any) -> _MaContext:
    fixture = bundle_fixture
    session = open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        row_scope_filter=("included_processed",),
    )
    query = session.create_ma_query_v1(
        ma_states=("unknown",),
        condition_combine_mode="AND",
        unknown_policy="include",
    )
    result = session.execute_ma_query_v1(query)
    request_zero = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=0, page_size=4,
    )
    request_one = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=1, page_size=4,
    )
    page_zero = result.read_page_request(request_zero)
    page_one = result.read_page_request(request_one)
    assert tuple(row.stock_code for row in page_zero.rows) == ("1000", "1001", "1002", "1003")
    assert tuple(row.stock_code for row in page_one.rows) == ("1004", "1005", "1006", "1007")
    assert page_zero.rows[0].ma_entry is not None
    assert page_zero.rows[0].ma_entry.ma_state == "unknown"
    assert page_zero.historical_pit_eligible is False
    return _MaContext(session, query, result, page_zero, page_one)


def _rehashed_selection_payload(
    selection: DailyMarketTechnicalOfficialDispositionMaSelectionV1,
    *,
    mutate: Callable[[dict[str, object]], None],
) -> dict[str, object]:
    payload = selection.to_dict()
    mutate(payload)
    body = {key: value for key, value in payload.items() if key != "selection_identity_sha256"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["selection_identity_sha256"] = hashlib.sha256(encoded).hexdigest()
    return payload


def test_selection_is_bound_to_real_page_and_preserves_unknown_evidence(
    ma_context: _MaContext,
) -> None:
    selected = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )
    restored = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_dict(
        selected.to_dict()
    )
    payload = json.loads(selected.row_json)
    assert restored == selected
    assert selected.query_identity_sha256 == ma_context.query.query_identity_sha256
    assert selected.page_index == 0
    assert selected.stock_code == "1000"
    assert payload["ma_entry"]["ma_state"] == "unknown"
    assert payload["ma_entry"]["ma_reason_codes"]
    assert payload["ma_entry"]["raw_row_count"] < 60
    assert dict(selected.source_pins)["decision_cutoff"] == _CUTOFF.isoformat()
    assert dict(selected.source_pins)["ma_read_session_identity_sha256"] == selected.ma_alignment_read_session_identity_sha256
    assert dict(selected.source_pins)["ma_index_identity_sha256"] == selected.ma_alignment_index_identity_sha256


def test_selection_requires_a_stock_on_the_issued_page(ma_context: _MaContext) -> None:
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="selection_stock_not_in_page"):
        DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
            ma_context.page_zero, "1004",
        )


def test_comparison_roundtrip_supports_cross_page_selection_and_rejects_duplicates(
    ma_context: _MaContext,
) -> None:
    first = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )
    second = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_one, "1004",
    )
    comparison = DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(
        ma_context.query, (first, second),
    )
    restored = DailyMarketTechnicalOfficialDispositionMaComparisonV1.from_json(
        comparison.to_json()
    )
    assert restored == comparison
    assert tuple(item.page_index for item in restored.selections) == (0, 1)
    assert restored.to_dict()["scope"] == "current_only"
    assert restored.to_dict()["availability_status"] == "unknown"
    assert restored.to_dict()["historical_pit_eligible"] is False
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error):
        DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(
            ma_context.query, (first,),
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error):
        DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(
            ma_context.query, (first, first),
        )
    different_query = ma_context.session.create_ma_query_v1(
        ma_states=("unknown",), unknown_policy="exclude",
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error):
        DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(
            different_query, (first, second),
        )

    def change_market_pin(payload: dict[str, object]) -> None:
        pins = payload["source_pins"]
        assert isinstance(pins, list)
        for pair in pins:
            if pair[0] == "market_assignment_pin_identity_sha256":
                pair[1] = "e" * 64

    altered_pin = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_dict(
        _rehashed_selection_payload(first, mutate=change_market_pin)
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error):
        DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(
            ma_context.query, (first, altered_pin),
        )


def test_exact_comparison_reopen_reads_one_source_and_checks_actual_pages(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )
    second = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_one, "1004",
    )
    comparison = DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(
        ma_context.query, (first, second),
    )
    calls: list[tuple[object, ...]] = []
    original_open = reader_module.open_daily_market_technical_official_disposition_read_session_v1

    def tracked_open(*args: object, **kwargs: object) -> object:
        calls.append(args)
        return original_open(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        reader_module,
        "open_daily_market_technical_official_disposition_read_session_v1",
        tracked_open,
    )
    verified = read_daily_market_technical_official_disposition_ma_comparison_v1(
        comparison.to_json()
    )
    assert len(calls) == 1
    assert verified.comparison_identity_sha256 == comparison.comparison_identity_sha256
    assert tuple(column.row.stock_code for column in verified.columns) == ("1000", "1004")
    assert tuple(column.selection.page_index for column in verified.columns) == (0, 1)
    assert all(
        column.row.ma_entry is not None and column.row.ma_entry.ma_state == "unknown"
        for column in verified.columns
    )
    assert verified.scope == "current_only"
    assert verified.official_available_at is None
    assert verified.availability_status == "unknown"
    assert verified.historical_pit_eligible is False
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="verified_selection_invalid"):
        replace(verified.columns[0])
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="verified_comparison_invalid"):
        replace(verified)


def test_self_consistent_source_pin_or_row_tamper_is_rejected_by_fresh_reader(
    ma_context: _MaContext,
) -> None:
    selection = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )

    def wrong_receipt(payload: dict[str, object]) -> None:
        pins = payload["source_pins"]
        assert isinstance(pins, list)
        for pair in pins:
            if pair[0] == "p01_receipt_sha256":
                pair[1] = "f" * 64

    altered_pin = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_dict(
        _rehashed_selection_payload(selection, mutate=wrong_receipt)
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="reopened_result_mismatch"):
        read_daily_market_technical_official_disposition_ma_selections_v1(
            ma_context.query, (altered_pin,),
        )

    def wrong_reason(payload: dict[str, object]) -> None:
        raw_row_json = payload["row_json"]
        assert isinstance(raw_row_json, str)
        row_json = json.loads(raw_row_json)
        row_json["ma_entry"]["ma_reason_codes"][0] = "ma_alignment_forged_reason"
        payload["row_json"] = json.dumps(
            row_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )

    altered_row = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_dict(
        _rehashed_selection_payload(selection, mutate=wrong_reason)
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="reopened_row_mismatch"):
        read_daily_market_technical_official_disposition_ma_selections_v1(
            ma_context.query, (altered_row,),
        )


def test_cancel_after_first_real_page_never_returns_partial_selection(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )
    second = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_one, "1004",
    )
    cancelled = False
    original_read = type(ma_context.result).read_page_request

    def cancel_after_real_page(self: object, *args: object, **kwargs: object) -> object:
        nonlocal cancelled
        page = original_read(self, *args, **kwargs)  # type: ignore[arg-type]
        cancelled = True
        return page

    monkeypatch.setattr(type(ma_context.result), "read_page_request", cancel_after_real_page)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="cancelled"):
        read_daily_market_technical_official_disposition_ma_selections_v1(
            ma_context.query, (first, second), cancel_callback=lambda: cancelled,
        )


def test_comparison_json_is_bounded_canonical_and_float_free(
    ma_context: _MaContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_zero, "1000",
    )
    second = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        ma_context.page_one, "1004",
    )
    comparison = DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(
        ma_context.query, (first, second),
    )
    assert DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_BYTES == 64 * 1024 * 1024
    monkeypatch.setattr(
        "app_module.daily_market_technical_official_disposition_ma_comparison_v1.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_BYTES",
        32,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="byte_limit"):
        comparison.to_json()
    with pytest.raises(DailyMarketTechnicalOfficialDispositionMaComparisonV1Error, match="byte_limit"):
        DailyMarketTechnicalOfficialDispositionMaComparisonV1.from_json(" " * 33)
