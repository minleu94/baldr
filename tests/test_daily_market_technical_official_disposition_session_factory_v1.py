"""保存 bundle 選取後，以一次 exact-read 建立真正的研究 session。"""
from __future__ import annotations

from datetime import datetime
from dataclasses import replace
from typing import Any

import pytest

from app_module import daily_market_technical_official_disposition_query_reader_v1 as reader
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
)
from test_daily_market_technical_official_disposition_bundle_v1 import (  # type: ignore[import-not-found]
    bundle_fixture,
    _tree_signature,
)


def _open(fixture: Any, **conditions: Any) -> reader.DailyMarketTechnicalOfficialDispositionReadSessionV1:
    return reader.open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        **conditions,
    )


def test_factory_derives_original_pins_opens_each_source_once_and_pages_last_segment(
    bundle_fixture: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    counts = {"bundle": 0, "technical": 0}
    original_bundle_read = reader.DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact
    original_technical_open = reader.open_daily_market_technical_universe_v4_read_session

    def bundle_read(self: Any, *args: Any, **kwargs: Any) -> Any:
        counts["bundle"] += 1
        return original_bundle_read(self, *args, **kwargs)

    def technical_open(*args: Any, **kwargs: Any) -> Any:
        counts["technical"] += 1
        return original_technical_open(*args, **kwargs)

    monkeypatch.setattr(reader.DailyMarketTechnicalOfficialDispositionBundleReaderV1, "read_exact", bundle_read)
    monkeypatch.setattr(reader, "open_daily_market_technical_universe_v4_read_session", technical_open)
    signature = _tree_signature(fixture.bundle_root)
    session = _open(fixture)
    assert counts == {"bundle": 1, "technical": 1}
    query = session.query
    assert query.decision_cutoff == datetime.fromisoformat("2026-10-07T16:00:00+08:00")
    assert query.market_assignment_pin_identity_sha256 == fixture.market_pin.identity_sha256.removeprefix("sha256:")
    assert query.official_disposal_pin_identity_sha256 == fixture.disposal_pin.identity_sha256.removeprefix("sha256:")
    assert query.technical_query.generation_identity_sha256 == fixture.generation_identity_sha256
    assert query.technical_query.decision_date.isoformat() == "2026-10-07"
    result = session.execute()
    assert result.counts.matching_count == 258
    page = result.read_page(5, 50)
    assert page.rows[-2].stock_code == fixture.included_codes[-1]
    assert page.rows[-1].stock_code == "9999"
    assert counts == {"bundle": 1, "technical": 1}
    assert _tree_signature(fixture.bundle_root) == signature

    filtered = session.with_conditions(
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        market_assignment_states=("assigned_tpex",),
    )
    assert filtered.query.query_identity_sha256 != query.query_identity_sha256
    assert filtered.bundle_reference == session.bundle_reference
    assert filtered.p01_read_session_identity_sha256 == session.p01_read_session_identity_sha256
    filtered_result = filtered.execute()
    assert filtered_result.counts.matching_count == 1
    assert filtered_result.read_page(0, 1).rows[0].stock_code == fixture.included_codes[-1]
    cleared = filtered.with_conditions(
        row_scope_filter=("included_processed", "included_pending", "excluded"),
    )
    assert cleared.query.query_identity_sha256 == query.query_identity_sha256
    assert cleared.execute().counts.matching_count == 258
    assert counts == {"bundle": 1, "technical": 1}
    assert _tree_signature(fixture.bundle_root) == signature


def test_factory_applies_global_market_filter_and_saved_sort(bundle_fixture: Any) -> None:
    fixture = bundle_fixture
    session = _open(
        fixture,
        market_assignment_states=("assigned_tpex",),
        sort_clauses=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "desc"),),
    )
    result = session.execute()
    assert result.counts.matching_count == 1
    assert result.counts.population.declared_count == 258
    assert tuple(row.stock_code for row in result.read_page(0, 1).rows) == (fixture.included_codes[-1],)


def test_wrong_manifest_sha_never_opens_technical_store(bundle_fixture: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_open(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("未核保存 bundle 不得開技術來源")

    monkeypatch.setattr(reader, "open_daily_market_technical_universe_v4_read_session", unexpected_open)
    with pytest.raises(reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        reader.open_daily_market_technical_official_disposition_bundle_session_v1(
            bundle_output_root=bundle_fixture.bundle_root,
            bundle_identity_sha256=bundle_fixture.reference.bundle_identity_sha256,
            expected_manifest_sha256="0" * 64,
            row_scope_filter=("included_processed",),
        )


@pytest.mark.parametrize("final_mode", ["cancel", "invalid", "raised"])
def test_factory_polls_after_session_issuance_and_never_returns_partial(
    bundle_fixture: Any, monkeypatch: pytest.MonkeyPatch, final_mode: str,
) -> None:
    mode = "normal"
    original_post = reader.DailyMarketTechnicalOfficialDispositionReadSessionV1.__post_init__

    def post(self: reader.DailyMarketTechnicalOfficialDispositionReadSessionV1) -> None:
        nonlocal mode
        original_post(self)
        mode = final_mode

    def callback() -> Any:
        if mode == "raised":
            raise RuntimeError("synthetic last poll")
        if mode == "invalid":
            return 1
        return mode == "cancel"

    monkeypatch.setattr(reader.DailyMarketTechnicalOfficialDispositionReadSessionV1, "__post_init__", post)
    with pytest.raises(reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error) as error:
        _open(bundle_fixture, cancel_callback=callback)
    if final_mode == "cancel":
        assert isinstance(error.value, reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled)
    elif final_mode == "invalid":
        assert error.value.code.endswith("cancel_callback_invalid")
    else:
        assert error.value.code.endswith("cancel_callback_failed")


def test_warm_conditions_reject_swapped_source_and_invalid_filters(bundle_fixture: Any) -> None:
    session = _open(bundle_fixture)
    query = session.query
    other_query = reader.DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=query.technical_query,
        decision_cutoff=query.decision_cutoff,
        bundle_output_root=query.bundle_output_root,
        bundle_identity_sha256=query.bundle_identity_sha256,
        expected_manifest_sha256="0" * 64,
        market_assignment_pin_identity_sha256=query.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=query.official_disposal_pin_identity_sha256,
        row_scope_filter=query.row_scope_filter,
    )
    # self identity 合格也不能借原 session 的 source 來核另一份 manifest。
    with pytest.raises(ValueError):
        replace(session, query=other_query).with_conditions(row_scope_filter=("included_processed",))
    with pytest.raises(reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
        session.with_conditions(row_scope_filter=())


@pytest.mark.parametrize("final_mode", ["cancel", "invalid", "raised"])
def test_warm_conditions_poll_after_derived_session_issuance(
    bundle_fixture: Any, monkeypatch: pytest.MonkeyPatch, final_mode: str,
) -> None:
    session = _open(bundle_fixture)
    mode = "normal"
    original_post = reader.DailyMarketTechnicalOfficialDispositionReadSessionV1.__post_init__

    def post(self: reader.DailyMarketTechnicalOfficialDispositionReadSessionV1) -> None:
        nonlocal mode
        original_post(self)
        if self is not session:
            mode = final_mode

    def callback() -> Any:
        if mode == "raised":
            raise RuntimeError("synthetic derived-session last poll")
        if mode == "invalid":
            return 1
        return mode == "cancel"

    monkeypatch.setattr(reader.DailyMarketTechnicalOfficialDispositionReadSessionV1, "__post_init__", post)
    with pytest.raises(reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error) as error:
        session.with_conditions(row_scope_filter=("included_processed",), cancel_callback=callback)
    if final_mode == "cancel":
        assert isinstance(error.value, reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled)
    elif final_mode == "invalid":
        assert error.value.code.endswith("cancel_callback_invalid")
    else:
        assert error.value.code.endswith("cancel_callback_failed")
