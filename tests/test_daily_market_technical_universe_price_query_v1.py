"""F07 價格查詢只依賴同次 exact v4 snapshot 的真實合成來源。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import sqlite3
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_parent_v4_producer import (
    produce_daily_market_technical_parent_v4,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePricePageV1,
    DailyMarketTechnicalUniversePriceQueryV1,
    DailyMarketTechnicalUniversePriceQueryV1Error,
    DailyMarketTechnicalUniversePriceReadSessionV1,
    DailyMarketTechnicalUniversePriceResultV1,
    open_daily_market_technical_universe_price_read_session_v1,
    open_daily_market_technical_universe_price_session_for_query_v1,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4StoreWriter,
    daily_market_technical_source_clock_v4_from_dict,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalCohortV4,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)
_CODES = ("S0001", "S0002", "S0003", "S0004")
_EXCLUDED = ("X9999",)
_HIGH_PRECISION_PRICE = Decimal("100.0000000000000000000001")
_LARGE_CODES = tuple(f"S{index:04d}" for index in range(257))
_LARGE_MISSING = ("S0000",)
_LARGE_EXCLUDED = ("X9999",)


@pytest.fixture(scope="module")
def exact_price_store(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """建立真 parent/store；讀取時 SQLite 原件已移除，確保不重查來源。"""

    root = tmp_path_factory.mktemp("price-v1-").resolve(strict=True)
    database = root / "synthetic-daily-prices.sqlite"
    _write_prices(database)
    scope_root = _long_configured_root(root)
    scope = ResearchCaptureWriteScope(scope_root, database)
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-price-range-v1",
        population_version="fixture-2026-10-06-price-v1",
        decision_date=_DECISION_DATE,
        raw_stock_codes=(*_CODES, *_EXCLUDED),
        excluded_stock_codes=_EXCLUDED,
        exclusion_reasons={"X9999": "合成來源明示排除"},
    )
    segment = DailyMarketTechnicalCohortV4.create(
        universe_id=cohort.universe_id,
        population_version=cohort.population_version,
        decision_date=cohort.decision_date,
        included_stock_codes=cohort.included_stock_codes,
        excluded_stock_codes=cohort.excluded_stock_codes,
        exclusion_reasons=dict(cohort.exclusion_reasons),
    )
    parent_root = scope.root / "parents" / "segment-000001"
    child_root = scope.root / "children" / "segment-000001"
    parent_result = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=segment,
        decision_cutoff=datetime.combine(
            _DECISION_DATE, time(16, 0), tzinfo=_TAIPEI
        ),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope,
    )
    assert parent_result.status == "complete", parent_result.error_code
    assert parent_result.plan is not None and parent_result.receipt is not None
    source_clock_payload = parent_result.plan.to_dict()["source_clock"]
    plan = DailyMarketTechnicalUniverseV4Plan.build(
        cohort,
        source_clock=daily_market_technical_source_clock_v4_from_dict(
            source_clock_payload
        ),
    )
    assert len(plan.segments) == 1
    parent_reference = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
        parent_root,
        parent_plan_identity_sha256=parent_result.plan.identity_sha256,
        parent_plan_sha256=parent_result.plan.content_sha256,
        parent_receipt_identity_sha256=parent_result.receipt.identity_sha256,
        parent_receipt_sha256=parent_result.receipt.content_sha256,
    )
    store_root = scope.root / "price-store"
    writer = DailyMarketTechnicalUniverseV4StoreWriter(
        store_root,
        research_scope=scope,
    )
    initial = writer.start(plan)
    progress = writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        initial.identity_sha256,
        expected_previous_receipt_sha256=initial.content_sha256,
        segment_index=0,
        parent_reference=parent_reference,
    )
    complete = writer.complete(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        progress.identity_sha256,
        expected_previous_receipt_sha256=progress.content_sha256,
    )
    assert complete.status == "complete"
    plan_sha256 = hashlib.sha256(plan.to_json().encode("utf-8")).hexdigest()
    database_io = Path(to_internal_io_path(database))
    if database_io.exists():
        database_io.unlink()
    yield {
        "root": root,
        "database": database,
        "store_root": store_root,
        "plan": plan,
        "plan_sha256": plan_sha256,
        "receipt": complete,
    }


@pytest.fixture(scope="module")
def exact_257_price_store(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """真實兩段 producer/store；同一 generation 保留取消版與完成版收據。"""

    root = tmp_path_factory.mktemp("price-v1-257-").resolve(strict=True)
    database = root / "synthetic-daily-prices-257.sqlite"
    _write_prices(
        database,
        stock_codes=(*_LARGE_CODES, *_LARGE_EXCLUDED),
        missing_codes=set(_LARGE_MISSING) | set(_LARGE_EXCLUDED),
        price_overrides={"S0256": Decimal("2")},
    )
    scope = ResearchCaptureWriteScope(_long_configured_root(root), database)
    reasons = {"X9999": "合成來源明示排除，保留於完整母體分母"}
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-price-range-257-v1",
        population_version="fixture-2026-10-06-price-257-v1",
        decision_date=_DECISION_DATE,
        raw_stock_codes=(*_LARGE_CODES, *_LARGE_EXCLUDED),
        excluded_stock_codes=_LARGE_EXCLUDED,
        exclusion_reasons=reasons,
    )
    first_segment = DailyMarketTechnicalCohortV4.create(
        universe_id=cohort.universe_id,
        population_version=cohort.population_version,
        decision_date=cohort.decision_date,
        included_stock_codes=_LARGE_CODES[:256],
        excluded_stock_codes=_LARGE_EXCLUDED,
        exclusion_reasons=reasons,
    )
    first_parent_root = scope.root / "parents" / "segment-000001"
    first_result = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=first_segment,
        decision_cutoff=datetime.combine(
            _DECISION_DATE, time(16, 0), tzinfo=_TAIPEI
        ),
        child_output_root=scope.root / "children" / "segment-000001",
        parent_root=first_parent_root,
        research_scope=scope,
    )
    assert first_result.status == "complete", first_result.error_code
    assert first_result.plan is not None and first_result.receipt is not None
    clock = daily_market_technical_source_clock_v4_from_dict(
        first_result.plan.to_dict()["source_clock"]
    )
    plan = DailyMarketTechnicalUniverseV4Plan.build(cohort, source_clock=clock)
    assert len(plan.segments) == 2
    assert plan.segment_cohort(0).to_dict() == first_segment.to_dict()
    second_segment = plan.segment_cohort(1)
    assert second_segment.included_stock_codes == ("S0256",)
    assert second_segment.excluded_stock_codes == ()

    first_reference = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
        first_parent_root,
        parent_plan_identity_sha256=first_result.plan.identity_sha256,
        parent_plan_sha256=first_result.plan.content_sha256,
        parent_receipt_identity_sha256=first_result.receipt.identity_sha256,
        parent_receipt_sha256=first_result.receipt.content_sha256,
    )
    second_parent_root = scope.root / "parents" / "segment-000002"
    second_result = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=second_segment,
        decision_cutoff=datetime.combine(
            _DECISION_DATE, time(16, 0), tzinfo=_TAIPEI
        ),
        child_output_root=scope.root / "children" / "segment-000002",
        parent_root=second_parent_root,
        research_scope=scope,
    )
    assert second_result.status == "complete", second_result.error_code
    assert second_result.plan is not None and second_result.receipt is not None
    assert second_result.plan.to_dict()["source_clock"] == plan.to_dict()["source_clock"]
    second_reference = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
        second_parent_root,
        parent_plan_identity_sha256=second_result.plan.identity_sha256,
        parent_plan_sha256=second_result.plan.content_sha256,
        parent_receipt_identity_sha256=second_result.receipt.identity_sha256,
        parent_receipt_sha256=second_result.receipt.content_sha256,
    )

    writer = DailyMarketTechnicalUniverseV4StoreWriter(
        scope.root / "price-store-257",
        research_scope=scope,
    )
    initial = writer.start(plan)
    first_progress = writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        initial.identity_sha256,
        expected_previous_receipt_sha256=initial.content_sha256,
        segment_index=0,
        parent_reference=first_reference,
    )
    cancelled = writer.mark_terminal(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        first_progress.identity_sha256,
        expected_previous_receipt_sha256=first_progress.content_sha256,
        status="cancelled",
        error_code="synthetic_cancel_after_first_segment",
    )
    resumed = writer.resume(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        cancelled.identity_sha256,
        expected_previous_receipt_sha256=cancelled.content_sha256,
    )
    second_progress = writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        resumed.identity_sha256,
        expected_previous_receipt_sha256=resumed.content_sha256,
        segment_index=1,
        parent_reference=second_reference,
    )
    complete = writer.complete(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        second_progress.identity_sha256,
        expected_previous_receipt_sha256=second_progress.content_sha256,
    )
    assert complete.status == "complete"
    plan_sha256 = hashlib.sha256(plan.to_json().encode("utf-8")).hexdigest()
    database_io = Path(to_internal_io_path(database))
    if database_io.exists():
        database_io.unlink()
    yield {
        "root": root,
        "database": database,
        "store_root": scope.root / "price-store-257",
        "plan": plan,
        "plan_sha256": plan_sha256,
        "receipt": complete,
        "cancelled_receipt": cancelled,
        "included_codes": _LARGE_CODES,
        "missing_codes": _LARGE_MISSING,
        "excluded_codes": _LARGE_EXCLUDED,
    }


def _write_prices(
    path: Path,
    *,
    stock_codes: tuple[str, ...] | None = None,
    missing_codes: set[str] | None = None,
    price_overrides: dict[str, Decimal] | None = None,
) -> None:
    connection = sqlite3.connect(to_internal_io_path(path))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            first_date = _DECISION_DATE - timedelta(days=39)
            effective_codes = (
                (*_CODES, *_EXCLUDED) if stock_codes is None else stock_codes
            )
            effective_missing = (
                {"S0003", "X9999"} if missing_codes is None else missing_codes
            )
            last_prices = {
                "S0001": _HIGH_PRECISION_PRICE,
                "S0002": Decimal("200"),
                "S0004": _HIGH_PRECISION_PRICE,
            }
            last_prices.update(price_overrides or {})
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            for stock_code in effective_codes:
                if stock_code in effective_missing:
                    continue
                for offset in range(40):
                    close = (
                        last_prices.get(stock_code, Decimal(100 + int(stock_code[1:])))
                        if offset == 39
                        else Decimal(60 + offset)
                    )
                    rows.append((
                        (first_date + timedelta(days=offset)).isoformat(),
                        stock_code,
                        format(close, "f"),
                        format(close + Decimal(1), "f"),
                        format(close - Decimal(1), "f"),
                        format(close, "f"),
                        100,
                    ))
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        connection.close()


def _long_configured_root(root: Path) -> Path:
    component = "price-research-root-" + ("x" * 58)
    return root / component / component / component


def _open_session(fixture: dict[str, Any]) -> DailyMarketTechnicalUniversePriceReadSessionV1:
    plan = fixture["plan"]
    receipt = fixture["receipt"]
    return open_daily_market_technical_universe_price_read_session_v1(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )


def _codes(page: Any) -> tuple[str, ...]:
    return tuple(row.technical_row.stock_code for row in page.rows)


def test_true_exact_price_query_global_decimal_sort_unknown_tail_and_drill(
    exact_price_store: dict[str, Any],
) -> None:
    fixture = exact_price_store
    assert not Path(to_internal_io_path(fixture["database"])).exists()
    session = _open_session(fixture)
    assert session.source_counts.declared_count == 5
    assert session.source_counts.included_count == 4
    assert session.source_counts.excluded_count == 1
    assert session.source_counts.processed_count == 4
    assert session.source_counts.pending_count == 0
    assert session.source_counts.missing_data_count == 1
    assert session.exclusion_reasons == (("X9999", "合成來源明示排除"),)
    assert session.source.current_only is True
    assert session.source.full_market_claim is False
    assert session.source.source_available_at is None
    assert session.source.historical_pit_eligible is False

    query = session.create_query(
        min_close_price=Decimal("99"),
        max_close_price=Decimal("201"),
        unknown_price_policy="include",
        descending=True,
    )
    assert DailyMarketTechnicalUniversePriceQueryV1.from_json(query.to_json()) == query
    result = session.execute(query)
    assert isinstance(result, DailyMarketTechnicalUniversePriceResultV1)
    assert result.price_counts.base_matching_count == 4
    assert result.price_counts.pass_count == 3
    assert result.price_counts.fail_count == 0
    assert result.price_counts.unknown_count == 1
    assert result.price_counts.matching_count == 4
    assert result.full_population_complete is True

    request = result.create_page_request(0, page_size=4)
    page = result.read_page(request)
    assert _codes(page) == ("S0002", "S0001", "S0004", "S0003")
    assert page.rows[1].price_fact.close_price == _HIGH_PRECISION_PRICE
    assert page.rows[1].price_fact.observation_date == _DECISION_DATE
    assert page.rows[-1].price_state == "unknown"
    assert page.to_dict()["historical_pit_eligible"] is False

    stock = result.read_stock_snapshot(request, "S0001")
    assert stock.row.to_dict() == page.rows[1].to_dict()
    assert stock.snapshot.snapshot_identity_sha256 == page.rows[1].price_fact.snapshot_identity_sha256
    assert stock.parent_reference.to_dict()["parent_receipt_sha256"]
    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as outside_page:
        result.read_stock_snapshot(request, "X9999")
    assert outside_page.value.code == "technical_universe_price_stock_not_in_origin_page"

    reopened, reopened_query = open_daily_market_technical_universe_price_session_for_query_v1(
        query.to_json()
    )
    assert reopened_query.query_identity_sha256 == query.query_identity_sha256
    assert reopened.read_session_identity_sha256 == session.read_session_identity_sha256
    reopened_page = reopened.execute(reopened_query).read_page(request)
    assert reopened_page.to_dict() == page.to_dict()


def test_true_257_two_segment_sort_drill_and_partial_population_counts(
    exact_257_price_store: dict[str, Any],
) -> None:
    fixture = exact_257_price_store
    assert not Path(to_internal_io_path(fixture["database"])).exists()

    session = _open_session(fixture)
    assert session.source.segment_count == 2
    assert session.source_counts.declared_count == 258
    assert session.source_counts.included_count == 257
    assert session.source_counts.excluded_count == 1
    assert session.source_counts.processed_count == 257
    assert session.source_counts.pending_count == 0
    assert session.source_counts.missing_data_count == 1
    assert session.source_counts.missing_data_pending_count == 0
    assert session.excluded_stock_codes == _LARGE_EXCLUDED
    assert session.exclusion_reasons == (
        ("X9999", "合成來源明示排除，保留於完整母體分母"),
    )

    ascending = session.execute(session.create_query(unknown_price_policy="include"))
    assert ascending.price_counts.base_matching_count == 257
    assert ascending.price_counts.pass_count == 256
    assert ascending.price_counts.unknown_count == 1
    assert ascending.matching_count == 257
    assert ascending.full_population_complete is True
    first_request = ascending.create_page_request(0, page_size=2)
    first_page = ascending.read_page(first_request)
    assert _codes(first_page) == ("S0256", "S0001")
    assert first_page.rows[0].price_fact.close_price == Decimal("2")
    last_segment_stock = ascending.read_stock_snapshot(first_request, "S0256")
    assert last_segment_stock.segment_index == 1
    assert last_segment_stock.snapshot.stock_code == "S0256"
    assert last_segment_stock.row.to_dict() == first_page.rows[0].to_dict()

    descending = session.execute(session.create_query(
        unknown_price_policy="include",
        descending=True,
    ))
    descending_first = descending.read_page(
        descending.create_page_request(0, page_size=1)
    )
    assert _codes(descending_first) == ("S0255",)
    descending_tail = descending.read_page(
        descending.create_page_request(1, page_size=256)
    )
    assert _codes(descending_tail)[-1] == "S0000"
    assert descending_tail.rows[-1].price_state == "unknown"

    cancelled_receipt_fixture = {
        **fixture,
        "receipt": fixture["cancelled_receipt"],
    }
    partial_session = _open_session(cancelled_receipt_fixture)
    assert partial_session.source.receipt_status == "cancelled"
    assert partial_session.source_counts.declared_count == 258
    assert partial_session.source_counts.included_count == 257
    assert partial_session.source_counts.excluded_count == 1
    assert partial_session.source_counts.processed_count == 256
    assert partial_session.source_counts.pending_count == 1
    assert partial_session.source_counts.missing_data_count == 1
    assert partial_session.source_counts.missing_data_pending_count == 1
    assert partial_session.pending_stock_codes == ("S0256",)
    assert partial_session.missing_data_stock_codes == _LARGE_MISSING
    assert partial_session.excluded_stock_codes == _LARGE_EXCLUDED
    assert partial_session.exclusion_reasons == session.exclusion_reasons

    partial_result = partial_session.execute(
        partial_session.create_query(unknown_price_policy="include")
    )
    assert partial_result.full_population_complete is False
    assert partial_result.price_counts.base_matching_count == 256
    assert partial_result.price_counts.pass_count == 255
    assert partial_result.price_counts.unknown_count == 1
    assert partial_result.matching_count == 256
    assert partial_result.pending_stock_codes == ("S0256",)
    assert partial_result.exclusion_reasons == session.exclusion_reasons


def test_price_unknown_policies_inclusive_bounds_and_empty_exclusive_interval(
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    include = session.execute(session.create_query(unknown_price_policy="include"))
    exclude = session.execute(session.create_query(unknown_price_policy="exclude"))
    only = session.execute(session.create_query(unknown_price_policy="only"))
    assert (include.price_counts.pass_count, include.price_counts.unknown_count) == (3, 1)
    include_page = include.read_page(include.create_page_request(0, page_size=4))
    assert _codes(include_page)[-1] == "S0003"
    assert exclude.matching_count == 3
    assert only.matching_count == 1
    assert _codes(only.read_page(only.create_page_request(0, page_size=4))) == ("S0003",)

    exact = session.execute(session.create_query(
        min_close_price=_HIGH_PRECISION_PRICE,
        max_close_price=_HIGH_PRECISION_PRICE,
        min_inclusive=True,
        max_inclusive=True,
        unknown_price_policy="exclude",
    ))
    assert _codes(exact.read_page(exact.create_page_request(0, page_size=4))) == ("S0001", "S0004")
    empty = session.execute(session.create_query(
        min_close_price=_HIGH_PRECISION_PRICE,
        max_close_price=_HIGH_PRECISION_PRICE,
        min_inclusive=False,
        max_inclusive=True,
        unknown_price_policy="exclude",
    ))
    assert empty.matching_count == 0
    assert empty.create_page_request(0, page_size=10).page_index == 0
    assert empty.read_page(empty.create_page_request(0, page_size=10)).rows == ()

    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as reversed_bounds:
        session.create_query(
            min_close_price=Decimal("201"),
            max_close_price=Decimal("100"),
        )
    assert reversed_bounds.value.code == "technical_universe_price_range_invalid"

    explicit_empty = session.execute(session.create_query(eligible_stock_codes=()))
    assert explicit_empty.price_counts.base_matching_count == 0
    assert explicit_empty.matching_count == 0
    disjoint_filters = session.execute(session.create_query(
        technical_stock_filter=("S0001", "S0002"),
        eligible_stock_codes=("S0003", "S0004"),
    ))
    assert disjoint_filters.matching_count == 0


def test_technical_and_or_filters_are_composed_before_price_page(
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    unfiltered = session.execute(session.create_query(unknown_price_policy="include"))
    unfiltered_page = unfiltered.read_page(unfiltered.create_page_request(0, page_size=4))
    sample = next(row.technical_row for row in unfiltered_page.rows if row.technical_row.stock_code == "S0001")
    first, second = session.source.method_rule_keys[:2]
    first_state = sample.rule(first).state
    second_state = sample.rule(second).state
    filters = (
        DailyMarketTechnicalRuleStateFilterV4.create(first, (first_state,)),
        DailyMarketTechnicalRuleStateFilterV4.create(second, (second_state,)),
    )
    and_result = session.execute(session.create_query(
        rule_state_filters=filters,
        combine_mode="AND",
        unknown_price_policy="include",
    ))
    or_result = session.execute(session.create_query(
        rule_state_filters=filters,
        combine_mode="OR",
        unknown_price_policy="include",
    ))
    assert "S0001" in _codes(and_result.read_page(and_result.create_page_request(0, page_size=4)))
    assert "S0001" in _codes(or_result.read_page(or_result.create_page_request(0, page_size=4)))
    assert and_result.price_counts.base_matching_count <= or_result.price_counts.base_matching_count


def test_price_query_exact_pins_canonical_parser_and_reader_issued_replace_guards(
    exact_price_store: dict[str, Any],
) -> None:
    session = _open_session(exact_price_store)
    wide_decimal = Decimal("123456789012345678901234567890.12345678901234567890")
    query = session.create_query(
        min_close_price=wide_decimal,
        unknown_price_policy="include",
    )
    roundtrip = DailyMarketTechnicalUniversePriceQueryV1.from_json(query.to_json())
    assert roundtrip.query_identity_sha256 == query.query_identity_sha256
    assert roundtrip.min_close_price == wide_decimal
    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as duplicate_key:
        DailyMarketTechnicalUniversePriceQueryV1.from_json(query.to_json().replace(
            '"descending":false', '"descending":false,"descending":false', 1
        ))
    assert duplicate_key.value.code == "technical_universe_price_json_duplicate_key"

    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as query_identity:
        replace(query, min_close_price=Decimal("100"))
    assert query_identity.value.code == "technical_universe_price_query_identity_mismatch"

    result = session.execute(session.create_query(unknown_price_policy="include"))
    request = result.create_page_request(0, page_size=2)
    page = result.read_page(request)
    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error):
        replace(result, _ordered_candidates=tuple(reversed(result._ordered_candidates)))
    # 公開證據欄位即使仍是合法SHA，也不能借原reader的發行錨點。
    changed_base = "0" * 64 if result.base_query_identity_sha256 != "0" * 64 else "1" * 64
    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as base_proof_error:
        replace(result, base_query_identity_sha256=changed_base)
    assert base_proof_error.value.code == "technical_universe_price_result_not_reader_issued"
    changed_classification = "0" * 64 if result.classification_identity_sha256 != "0" * 64 else "1" * 64
    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as classification_proof_error:
        replace(result, classification_identity_sha256=changed_classification)
    assert classification_proof_error.value.code == "technical_universe_price_result_not_reader_issued"
    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error):
        replace(page, rows=tuple(reversed(page.rows)))
    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as wrong_generation:
        open_pins = query.source.open_kwargs()
        open_daily_market_technical_universe_price_read_session_v1(
            store_output_root=cast(str | Path, open_pins["store_output_root"]),
            generation_identity_sha256=cast(str, open_pins["generation_identity_sha256"]),
            plan_identity_sha256="f" * 64,
            plan_sha256=cast(str, open_pins["plan_sha256"]),
            receipt_identity_sha256=cast(str, open_pins["receipt_identity_sha256"]),
            receipt_sha256=cast(str, open_pins["receipt_sha256"]),
            cancel_callback=None,
        )
    assert wrong_generation.value.code.endswith("plan_path_identity_mismatch") or (
        wrong_generation.value.code == "technical_universe_v4_generation_path_identity_mismatch"
    )


def test_cancel_callback_is_strict_and_late_page_cancel_does_not_publish(
    exact_price_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    for callback, expected_code in (
        (lambda: 1, "technical_universe_price_cancel_callback_invalid"),
        (lambda: (_ for _ in ()).throw(RuntimeError("synthetic")), "technical_universe_price_cancel_check_failed"),
        (lambda: True, "technical_universe_price_cancelled"),
    ):
        with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as error:
            session.execute(query, cancel_callback=callback)
        assert error.value.code == expected_code

    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    cancellation = {"value": False}
    original_post_init = DailyMarketTechnicalUniversePricePageV1.__post_init__

    def construct_then_cancel(page: DailyMarketTechnicalUniversePricePageV1) -> None:
        original_post_init(page)
        cancellation["value"] = True

    monkeypatch.setattr(
        "app_module.daily_market_technical_universe_price_query_v1.DailyMarketTechnicalUniversePricePageV1.__post_init__",
        construct_then_cancel,
    )
    with pytest.raises(DailyMarketTechnicalUniversePriceQueryV1Error) as late_cancel:
        result.read_page(request, cancel_callback=lambda: cancellation["value"])
    assert late_cancel.value.code == "technical_universe_price_cancelled"
