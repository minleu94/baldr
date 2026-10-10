"""正式 presenter 變更的候選測試；尚未加入正式測試目錄。"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sqlite3
from typing import cast

import pytest

import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite
from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositeResultRowV1,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
    DailyMarketTechnicalOfficialDispositionBundleWriterV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    open_daily_market_technical_official_disposition_projection_group_session_v2,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_CANONICAL_PAGE_SIZE,
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_query import (
    open_daily_market_technical_universe_v4_read_session,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4StoreReader,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from data_module.selection_market_assignments import CurrentMarketAssignmentReader
from data_module.selection_official_events import CurrentOfficialDisposalReader
from test_daily_market_technical_official_disposition_bundle_v1 import (
    _CUTOFF,
    _DECISION_DATE,
    _FrozenDateTime,
    _PUBLISHED_AT,
    _capture_disposal_sources,
    _capture_market_sources,
    capture_module,
)
from test_daily_market_technical_official_disposition_composite_reader_v1 import (
    _AuditOwner,
)
from ui_qt.technical_official_composite_research_presenter import (
    format_composite_row_v1,
)


pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_reader_v1",
)

_STOCK_CODE = "2468"
_COMPOSITE_PAGE_SIZE = 256


def _write_29_valid_price_rows(database: Path, stock_code: str) -> None:
    """只在 pytest 的 tmp_path 內建立隔離的短歷史來源。"""
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(to_internal_io_path(database))
    first_date = _DECISION_DATE - timedelta(days=28)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows = [
                (
                    (first_date + timedelta(days=offset)).isoformat(),
                    stock_code,
                    "100",
                    "101",
                    "99",
                    "100",
                    1000,
                )
                for offset in range(29)
            ]
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows
            )
    finally:
        connection.close()


@pytest.fixture
def one_stock_29_row_f17_session(
    tmp_path: Path,
) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
    """建立一股、實際經過 P02/store/F17 並由公開 reader 發行的來源。"""
    qa_root = tmp_path / "f06-one-stock-short-history"
    database = qa_root / "synthetic_prices.sqlite"
    _write_29_valid_price_rows(database, _STOCK_CODE)
    with sqlite3.connect(to_internal_io_path(database)) as connection:
        count_row = connection.execute(
            'SELECT COUNT(*) FROM "daily_prices" WHERE "證券代號" = ?',
            (_STOCK_CODE,),
        ).fetchone()
    assert count_row == (29,)

    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="qa-f06-one-stock-short-history",
        population_version="synthetic-2026-10-07-29-rows-v1",
        decision_date=_DECISION_DATE,
        raw_stock_codes=(_STOCK_CODE,),
    )
    scope = ResearchCaptureWriteScope(qa_root / "technical-output", database)
    store_root = scope.root / "full-technical-store"
    technical_result = produce_daily_market_technical_universe_v4(
        DailyMarketTechnicalUniverseV4ProductionRequest(
            source_database=database,
            cohort=cohort,
            decision_cutoff=_CUTOFF,
            store_output_root=store_root,
            research_scope=scope,
        )
    )
    assert technical_result.status == "complete", technical_result.error_code
    assert technical_result.plan is not None
    assert technical_result.receipt is not None
    assert technical_result.receipt.status == "complete"
    assert technical_result.plan.cohort.declared_stock_codes == (_STOCK_CODE,)
    assert len(technical_result.plan.segments) == 1

    generation_identity = cast(str, technical_result.generation_identity_sha256)
    plan_identity = cast(str, technical_result.plan_identity_sha256)
    plan_sha256 = cast(str, technical_result.plan_sha256)
    receipt_identity = cast(str, technical_result.receipt_identity_sha256)
    receipt_sha256 = cast(str, technical_result.receipt_content_sha256)
    store_state = DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
        generation_identity,
        plan_identity,
        receipt_identity,
        expected_receipt_sha256=receipt_sha256,
        expected_plan_sha256=plan_sha256,
    )
    assert store_state.counts.declared_count == 1
    assert store_state.counts.included_count == 1
    assert store_state.counts.processed_count == 1

    market_root = qa_root / "market-capture"
    disposal_root = qa_root / "disposal-capture"
    previous_fixed_now = _FrozenDateTime.fixed_now
    capture_patch = pytest.MonkeyPatch()
    try:
        _FrozenDateTime.fixed_now = _PUBLISHED_AT
        capture_patch.setattr(capture_module, "datetime", _FrozenDateTime)
        market_pointer = _capture_market_sources(market_root, (), _STOCK_CODE)
        disposal_pointer = _capture_disposal_sources(
            disposal_root,
            "9998",
            _STOCK_CODE,
        )
    finally:
        capture_patch.undo()
        _FrozenDateTime.fixed_now = previous_fixed_now

    market_pin = CurrentMarketAssignmentReader.from_pointer(
        market_pointer,
        cutoff_at=_CUTOFF,
    ).source_pin
    disposal_pin = CurrentOfficialDisposalReader.from_pointer(
        disposal_pointer,
        cutoff_at=_CUTOFF,
    ).source_pin

    bundle_root = scope.root / "daily_market_technical_official_disposition_v1"
    bundle_writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        bundle_root,
        research_scope=scope,
    )
    bundle_reference = bundle_writer.create_from_pins(
        store_output_root=store_root,
        generation_identity_sha256=generation_identity,
        plan_identity_sha256=plan_identity,
        expected_plan_sha256=plan_sha256,
        receipt_identity_sha256=receipt_identity,
        expected_receipt_sha256=receipt_sha256,
        market_assignment_source_pin=market_pin,
        official_disposal_source_pin=disposal_pin,
    )
    verified_bundle = DailyMarketTechnicalOfficialDispositionBundleReaderV1(
        bundle_root
    ).read_exact(
        bundle_reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_reference.manifest_sha256,
    )
    verified_facts = tuple(verified_bundle.iter_verified_rows())
    assert len(verified_facts) == 1
    assert verified_facts[0].stock_code == _STOCK_CODE

    p01 = open_daily_market_technical_universe_v4_read_session(
        store_output_root=store_root,
        generation_identity_sha256=generation_identity,
        plan_identity_sha256=plan_identity,
        plan_sha256=plan_sha256,
        receipt_identity_sha256=receipt_identity,
        receipt_sha256=receipt_sha256,
    )
    technical_query = p01.create_query(
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_CANONICAL_PAGE_SIZE,
    )
    f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=technical_query,
        decision_cutoff=_CUTOFF,
        bundle_output_root=bundle_root,
        bundle_identity_sha256=bundle_reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_reference.manifest_sha256,
        market_assignment_pin_identity_sha256=market_pin.identity_sha256,
        official_disposal_pin_identity_sha256=disposal_pin.identity_sha256,
        row_scope_filter=(
            "included_processed",
            "included_pending",
            "excluded",
        ),
    )
    read_session = open_daily_market_technical_official_disposition_projection_group_session_v2(
        f17_query
    )
    assert read_session.projection_group_session is not None
    return read_session


def _composite_row_for_stock(
    session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
    stock_code: str,
) -> DailyMarketTechnicalOfficialDispositionCompositeResultRowV1:
    group = session.projection_group_session
    assert group is not None
    query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        session.query,
        projection_group_session_identity_sha256=group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="exclude",
    )
    result = session.execute_composite_query_v1(query)
    matching = tuple(
        row
        for page_index in range(
            (result.visible_count + _COMPOSITE_PAGE_SIZE - 1) // _COMPOSITE_PAGE_SIZE
        )
        for row in result.read_page(page_index, _COMPOSITE_PAGE_SIZE).rows
        if row.stock_code == stock_code
    )
    assert len(matching) == 1
    row = matching[0]
    assert type(row) is DailyMarketTechnicalOfficialDispositionCompositeResultRowV1
    return row


def test_observed_volatility_description_uses_named_full257_fixture(
    full257_audit_owner: _AuditOwner,
) -> None:
    """使用既有具名 fixture，不讀取凍結的 output/qa bundle 路徑。"""
    owner = full257_audit_owner
    query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="include",
    )
    result = owner.session.execute_composite_query_v1(query)
    rows = tuple(
        row
        for page_index in range(
            (result.visible_count + _COMPOSITE_PAGE_SIZE - 1) // _COMPOSITE_PAGE_SIZE
        )
        for row in result.read_page(page_index, _COMPOSITE_PAGE_SIZE).rows
    )
    row = next(
        candidate
        for candidate in rows
        if candidate.volatility_entry is not None
        and candidate.volatility_entry.evidence.bandwidth.state == "observed"
        and candidate.volatility_entry.evidence.atr14_sma.state == "observed"
    )
    assert type(row) is DailyMarketTechnicalOfficialDispositionCompositeResultRowV1
    assert row.volatility_entry is not None
    evidence = row.volatility_entry.evidence
    text = format_composite_row_v1(row)
    methods = (
        (
            "BB30 布林帶寬（母體標準差 2σ）",
            evidence.bandwidth,
        ),
        (
            "ATR14 真實波幅移動平均（SMA）",
            evidence.atr14_sma,
        ),
    )
    for method_label, measure in methods:
        dates = measure.input_feature_dates
        assert measure.state == "observed"
        assert dates and all(item is not None for item in dates)
        assert f"方法 {method_label}（版本 {measure.method_version}）" in text
        assert (
            f"計算窗口 {dates[0].isoformat()} 至 {dates[-1].isoformat()}"
            f"（日期列 {len(dates)}；方法需求列 {measure.input_rows_required}）"
        ) in text
        assert (
            f"暖機已觀測 {measure.warmup_observations_observed}"
            f"／所需 {measure.warmup_observations_required}"
        ) in text
        assert "來源列連續：是" in text
        assert measure.method_id not in text
        assert measure.method_identity_sha256 not in text


def test_short_history_unknown_reason_is_presented_from_reader_issued_row(
    one_stock_29_row_f17_session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
) -> None:
    row = _composite_row_for_stock(one_stock_29_row_f17_session, _STOCK_CODE)
    assert row.volatility_entry is not None
    evidence = row.volatility_entry.evidence
    bandwidth = evidence.bandwidth
    atr14 = evidence.atr14_sma

    assert bandwidth.state == "unknown"
    assert bandwidth.value is None
    assert "warmup_insufficient" in bandwidth.reason_codes
    assert bandwidth.input_rows_required == 30
    assert bandwidth.warmup_observations_required == 30
    assert bandwidth.warmup_observations_observed == 29
    assert len(bandwidth.input_feature_dates) == 29
    assert bandwidth.window_observations_contiguous is True
    assert atr14.state == "observed"
    assert atr14.input_rows_required == 15
    assert atr14.warmup_observations_observed == 14

    dates = tuple(
        item.isoformat()
        for item in bandwidth.input_feature_dates
        if item is not None
    )
    assert len(dates) == 29
    text = format_composite_row_v1(row)
    assert "方法 BB30 布林帶寬（母體標準差 2σ）" in text
    assert f"計算窗口 {dates[0]} 至 {dates[-1]}（日期列 29；方法需求列 30）" in text
    assert "暖機已觀測 29／所需 30" in text
    assert "來源列連續：是" in text
    assert "原因 warmup_insufficient" in text
    assert "BB30 布林帶寬：未知 未提供" in text
    assert bandwidth.method_id not in text
    assert bandwidth.method_identity_sha256 not in text
