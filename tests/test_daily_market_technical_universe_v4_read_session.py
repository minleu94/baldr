"""驗證 full-N read session 的固定來源、全域查詢與精確重開契約。"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import replace as dataclass_replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app_module import daily_market_technical_universe_v4_query as query_module
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_parent_v4_producer import (
    produce_daily_market_technical_parent_v4,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalSnapshotV4Repository,
)
from app_module.daily_market_technical_universe_v4_bookmark import (
    DailyMarketTechnicalUniverseV4BookmarkError,
    create_daily_market_technical_universe_v4_bookmark_fresh,
    read_daily_market_technical_universe_v4_bookmark,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4QueryError,
    DailyMarketTechnicalUniverseV4ReadSession,
    open_daily_market_technical_universe_v4_read_session,
    read_daily_market_technical_universe_v4_page,
)
from app_module.daily_market_technical_universe_v4_stock import (
    DailyMarketTechnicalUniverseV4StockError,
    read_daily_market_technical_universe_v4_page_and_stock_from_session,
    read_daily_market_technical_universe_v4_stock_from_selection,
    read_daily_market_technical_universe_v4_stock_from_session,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4StoreReader,
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
_START_DATE = _DECISION_DATE - timedelta(days=39)
_STOCK_CODES = tuple(f"S{index:04d}" for index in range(17))
_EXCLUDED_CODES = ("X9999",)
_MAIN_EXCLUDED_CODES = tuple(f"X{index:04d}" for index in range(257))
_RATIO_SORT = "volume_ratio_20_including_current.ratio"


@pytest.fixture(scope="module")
def synthetic_read_session_source(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[dict[str, Any], None, None]:
    """只產製一次 17 股真 parent、真 child artifact 與完整 store。"""

    root = tmp_path_factory.mktemp("uv4-read-session").resolve(strict=True)
    database = root / "synthetic-prices.sqlite"
    _write_source(database, (*_STOCK_CODES, *_MAIN_EXCLUDED_CODES, *_EXCLUDED_CODES))
    scope = ResearchCaptureWriteScope(_long_research_root(root), database)
    store_root = scope.root / "store-output"
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-read-session-v4",
        population_version="fixture-2026-10-06",
        decision_date=_DECISION_DATE,
        raw_stock_codes=(*_STOCK_CODES, *_MAIN_EXCLUDED_CODES),
        excluded_stock_codes=_MAIN_EXCLUDED_CODES,
        exclusion_reasons={code: "隔離 fixture 的固定排除列" for code in _MAIN_EXCLUDED_CODES},
    )
    parent_results = []
    parent_references = []
    for segment_index, segment in enumerate(_segment_cohorts(cohort)):
        parent_root = scope.root / "parents" / f"segment-{segment_index + 1:06d}"
        child_root = scope.root / "children" / f"segment-{segment_index + 1:06d}"
        parent_result = produce_daily_market_technical_parent_v4(
            source_database=database,
            cohort=segment,
            decision_cutoff=datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI),
            child_output_root=child_root,
            parent_root=parent_root,
            research_scope=scope,
        )
        assert parent_result.status == "complete", parent_result.error_code
        assert parent_result.plan is not None and parent_result.receipt is not None
        parent_results.append(parent_result)
        parent_references.append(DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
            parent_root,
            parent_plan_identity_sha256=parent_result.plan.identity_sha256,
            parent_plan_sha256=parent_result.plan.content_sha256,
            parent_receipt_identity_sha256=parent_result.receipt.identity_sha256,
            parent_receipt_sha256=parent_result.receipt.content_sha256,
        ))
    first_parent_plan = parent_results[0].plan
    assert first_parent_plan is not None
    assert all(
        result.plan is not None
        and result.plan.to_dict()["source_clock"] == first_parent_plan.to_dict()["source_clock"]
        for result in parent_results
    )
    plan = DailyMarketTechnicalUniverseV4Plan.build(
        cohort,
        source_clock=daily_market_technical_source_clock_v4_from_dict(
            first_parent_plan.to_dict()["source_clock"]
        ),
    )
    assert len(plan.segments) == 2
    assert tuple(
        (len(plan.segment_cohort(index).included_stock_codes),
         len(plan.segment_cohort(index).excluded_stock_codes))
        for index in range(2)
    ) == ((17, 256), (0, 1))
    writer = DailyMarketTechnicalUniverseV4StoreWriter(store_root, research_scope=scope)
    initial = writer.start(plan)
    progress = initial
    for segment_index, parent_reference in enumerate(parent_references):
        progress = writer.record_segment_parent(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            progress.identity_sha256,
            expected_previous_receipt_sha256=progress.content_sha256,
            segment_index=segment_index,
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

    excluded_only = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-excluded-read-session-v4",
        population_version="fixture-excluded-2026-10-06",
        decision_date=_DECISION_DATE,
        raw_stock_codes=_EXCLUDED_CODES,
        excluded_stock_codes=_EXCLUDED_CODES,
        exclusion_reasons={"X9999": "明示排除的完整母體成員"},
    )
    excluded_segment = DailyMarketTechnicalCohortV4.create(
        universe_id=excluded_only.universe_id,
        population_version=excluded_only.population_version,
        decision_date=excluded_only.decision_date,
        included_stock_codes=excluded_only.included_stock_codes,
        excluded_stock_codes=excluded_only.excluded_stock_codes,
        exclusion_reasons=dict(excluded_only.exclusion_reasons),
    )
    excluded_parent = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=excluded_segment,
        decision_cutoff=datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI),
        child_output_root=scope.root / "children" / "excluded-only",
        parent_root=scope.root / "parents" / "excluded-only",
        research_scope=scope,
    )
    assert excluded_parent.status == "complete", excluded_parent.error_code
    assert excluded_parent.plan is not None and excluded_parent.receipt is not None
    excluded_plan = DailyMarketTechnicalUniverseV4Plan.build(
        excluded_only,
        source_clock=daily_market_technical_source_clock_v4_from_dict(
            excluded_parent.plan.to_dict()["source_clock"]
        ),
    )
    excluded_ref = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
        scope.root / "parents" / "excluded-only",
        parent_plan_identity_sha256=excluded_parent.plan.identity_sha256,
        parent_plan_sha256=excluded_parent.plan.content_sha256,
        parent_receipt_identity_sha256=excluded_parent.receipt.identity_sha256,
        parent_receipt_sha256=excluded_parent.receipt.content_sha256,
    )
    excluded_store_root = scope.root / "excluded-only-store"
    excluded_writer = DailyMarketTechnicalUniverseV4StoreWriter(
        excluded_store_root, research_scope=scope
    )
    excluded_initial = excluded_writer.start(excluded_plan)
    excluded_progress = excluded_writer.record_segment_parent(
        excluded_plan.generation_identity_sha256,
        excluded_plan.identity_sha256,
        excluded_initial.identity_sha256,
        expected_previous_receipt_sha256=excluded_initial.content_sha256,
        segment_index=0,
        parent_reference=excluded_ref,
    )
    excluded_complete = excluded_writer.complete(
        excluded_plan.generation_identity_sha256,
        excluded_plan.identity_sha256,
        excluded_progress.identity_sha256,
        expected_previous_receipt_sha256=excluded_progress.content_sha256,
    )
    assert excluded_complete.status == "complete"
    excluded_plan_sha256 = hashlib.sha256(excluded_plan.to_json().encode("utf-8")).hexdigest()

    empty_cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-empty-read-session-v4",
        population_version="fixture-empty-2026-10-06",
        decision_date=_DECISION_DATE,
        raw_stock_codes=(),
    )
    empty_plan = DailyMarketTechnicalUniverseV4Plan.build(
        empty_cohort,
        source_clock=daily_market_technical_source_clock_v4_from_dict(
            first_parent_plan.to_dict()["source_clock"]
        ),
    )
    assert not empty_plan.segments
    empty_store_root = scope.root / "empty-store"
    empty_writer = DailyMarketTechnicalUniverseV4StoreWriter(
        empty_store_root, research_scope=scope
    )
    empty_initial = empty_writer.start(empty_plan)
    empty_complete = empty_writer.complete(
        empty_plan.generation_identity_sha256,
        empty_plan.identity_sha256,
        empty_initial.identity_sha256,
        expected_previous_receipt_sha256=empty_initial.content_sha256,
    )
    assert empty_complete.status == "complete"
    empty_plan_sha256 = hashlib.sha256(empty_plan.to_json().encode("utf-8")).hexdigest()

    partial_store_root = scope.root / "partial-store"
    partial_writer = DailyMarketTechnicalUniverseV4StoreWriter(
        partial_store_root, research_scope=scope
    )
    partial_initial = partial_writer.start(plan)
    partial_progress = partial_writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        partial_initial.identity_sha256,
        expected_previous_receipt_sha256=partial_initial.content_sha256,
        segment_index=0,
        parent_reference=parent_references[0],
    )
    partial_cancelled = partial_writer.mark_terminal(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        partial_progress.identity_sha256,
        expected_previous_receipt_sha256=partial_progress.content_sha256,
        status="cancelled",
        error_code="synthetic_cancel_after_first_segment",
    )
    database.unlink()
    yield {
        "root": root,
        "database": database,
        "store_root": store_root,
        "scope": scope,
        "plan": plan,
        "plan_sha256": plan_sha256,
        "complete": complete,
        "writer": writer,
        "parent_references": tuple(parent_references),
        "excluded_only": {
            "store_root": excluded_store_root,
            "plan": excluded_plan,
            "plan_sha256": excluded_plan_sha256,
            "complete": excluded_complete,
        },
        "empty": {
            "store_root": empty_store_root,
            "plan": empty_plan,
            "plan_sha256": empty_plan_sha256,
            "complete": empty_complete,
        },
        "partial": {
            "store_root": partial_store_root,
            "plan": plan,
            "plan_sha256": plan_sha256,
            "cancelled": partial_cancelled,
        },
    }


@pytest.fixture(scope="module")
def read_session(synthetic_read_session_source: dict[str, Any]) -> DailyMarketTechnicalUniverseV4ReadSession:
    """建立一次 reader-issued session，讓所有案例共用同一個 pinned read。"""

    fixture = synthetic_read_session_source
    plan = fixture["plan"]
    receipt = fixture["complete"]
    return open_daily_market_technical_universe_v4_read_session(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )


def _write_source(path: Path, stock_codes: tuple[str, ...]) -> None:
    connection = sqlite3.connect(to_internal_io_path(path))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str | None, int]] = []
            for stock_code in stock_codes:
                if stock_code == "S0000" or stock_code.startswith("X"):
                    continue
                for offset in range(40):
                    close: str | None = str(100 + offset)
                    if stock_code == "S0002" and offset == 39:
                        close = None
                    volume = 100
                    if offset == 39 and stock_code == "S0001":
                        volume = 9000
                    elif offset == 39 and stock_code == "S0016":
                        volume = 9
                    rows.append((
                        (_START_DATE + timedelta(days=offset)).isoformat(),
                        stock_code,
                        str(100 + offset),
                        str(101 + offset),
                        str(99 + offset),
                        close,
                        volume,
                    ))
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        connection.close()


def _long_research_root(root: Path) -> Path:
    segment = "strict-session-" + ("q" * 56)
    return root / segment / segment / segment


def _segment_cohorts(
    cohort: DailyMarketTechnicalUniverseV4Cohort,
) -> tuple[DailyMarketTechnicalCohortV4, ...]:
    count = max(
        (len(cohort.included_stock_codes) + 255) // 256,
        (len(cohort.excluded_stock_codes) + 255) // 256,
    )
    reasons = dict(cohort.exclusion_reasons)
    result: list[DailyMarketTechnicalCohortV4] = []
    for index in range(count):
        included = cohort.included_stock_codes[index * 256:(index + 1) * 256]
        excluded = cohort.excluded_stock_codes[index * 256:(index + 1) * 256]
        result.append(DailyMarketTechnicalCohortV4.create(
            universe_id=cohort.universe_id,
            population_version=cohort.population_version,
            decision_date=cohort.decision_date,
            included_stock_codes=included,
            excluded_stock_codes=excluded,
            exclusion_reasons={code: reasons[code] for code in excluded},
        ))
    return tuple(result)


def _session_query(
    session: DailyMarketTechnicalUniverseV4ReadSession,
    **conditions: Any,
) -> DailyMarketTechnicalUniverseV4Query:
    return session.create_query(**conditions)


def _open_session(fixture: dict[str, Any]) -> DailyMarketTechnicalUniverseV4ReadSession:
    plan = fixture["plan"]
    receipt = fixture["complete"]
    return open_daily_market_technical_universe_v4_read_session(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )


def _open_case_session(case: dict[str, Any]) -> DailyMarketTechnicalUniverseV4ReadSession:
    plan = case["plan"]
    receipt = case.get("complete", case.get("cancelled"))
    if receipt is None:
        raise AssertionError("read_session_case_receipt_missing")
    return open_daily_market_technical_universe_v4_read_session(
        store_output_root=case["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=case["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )


def _resign_query(payload: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in payload.items() if key != "query_identity_sha256"}
    payload["query_identity_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return payload


def _copy_tree_with_extended_paths(source: Path, destination: Path) -> None:
    """複製長路徑測試 store，逐檔轉換 Windows OS I/O 路徑。"""

    source_io = to_internal_io_path(source)
    for current, directories, files in os.walk(source_io):
        relative = os.path.relpath(current, source_io)
        target_root = destination if relative == "." else destination / relative
        os.makedirs(to_internal_io_path(target_root), exist_ok=True)
        for directory in directories:
            os.makedirs(to_internal_io_path(target_root / directory), exist_ok=True)
        for filename in files:
            shutil.copyfile(
                os.path.join(current, filename),
                to_internal_io_path(target_root / filename),
            )


def test_session_full_index_matches_strict_filter_sort_and_global_paging(
    synthetic_read_session_source: dict[str, Any],
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
) -> None:
    fixture = synthetic_read_session_source
    assert read_session.index_stock_count == 17
    assert 0 < read_session.index_bytes <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES
    assert read_session.read_session_identity_sha256

    filters = (
        DailyMarketTechnicalRuleStateFilterV4.create(
            "volume_ratio_20_including_current", ("match", "unknown")
        ),
        DailyMarketTechnicalRuleStateFilterV4.create(
            "ma5_20_golden_cross", ("match",)
        ),
    )
    queries = (
        _session_query(
            read_session,
            rule_state_filters=filters,
            combine_mode="AND",
            sort_key=_RATIO_SORT,
            descending=True,
            page_index=0,
            page_size=4,
        ),
        _session_query(
            read_session,
            rule_state_filters=filters,
            combine_mode="OR",
            stock_filter=("S0001", "S0002", "S0016"),
            sort_key=_RATIO_SORT,
            descending=False,
            page_index=0,
            page_size=2,
        ),
        _session_query(
            read_session,
            sort_key="latest_feature_date",
            descending=True,
            page_index=1,
            page_size=5,
        ),
    )
    for warm_query in queries:
        strict_query = DailyMarketTechnicalUniverseV4Query.create(
            store_output_root=fixture["store_root"],
            generation_identity_sha256=fixture["plan"].generation_identity_sha256,
            plan_identity_sha256=fixture["plan"].identity_sha256,
            plan_sha256=fixture["plan_sha256"],
            receipt_identity_sha256=fixture["complete"].identity_sha256,
            receipt_sha256=fixture["complete"].content_sha256,
            rule_state_filters=warm_query.rule_state_filters,
            combine_mode=warm_query.combine_mode,
            stock_filter=warm_query.stock_filter,
            sort_key=warm_query.sort_key,
            descending=warm_query.descending,
            page_index=warm_query.page_index,
            page_size=warm_query.page_size,
        )
        assert strict_query == warm_query
        assert read_session.read_page(warm_query).to_dict() == read_daily_market_technical_universe_v4_page(
            strict_query
        ).to_dict()


def test_all_supported_sort_keys_preserve_decimal_and_stable_null_ordering(
    synthetic_read_session_source: dict[str, Any],
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
) -> None:
    fixture = synthetic_read_session_source
    rule_keys = read_session.create_query().method_rule_keys
    sort_keys = (
        "stock_code",
        "decision_date",
        "latest_feature_date",
        "raw_row_count",
        *(f"{key}.{field}" for key in rule_keys for field in ("ratio", "numerator", "denominator")),
    )
    for index, sort_key in enumerate(sort_keys):
        warm_query = read_session.create_query(
            sort_key=sort_key,
            descending=index % 2 == 1,
            page_index=0,
            page_size=17,
        )
        strict_query = DailyMarketTechnicalUniverseV4Query.create(
            store_output_root=fixture["store_root"],
            generation_identity_sha256=fixture["plan"].generation_identity_sha256,
            plan_identity_sha256=fixture["plan"].identity_sha256,
            plan_sha256=fixture["plan_sha256"],
            receipt_identity_sha256=fixture["complete"].identity_sha256,
            receipt_sha256=fixture["complete"].content_sha256,
            sort_key=sort_key,
            descending=index % 2 == 1,
            page_index=0,
            page_size=17,
        )
        strict_page = read_daily_market_technical_universe_v4_page(strict_query)
        assert read_session.read_page(warm_query).to_dict() == strict_page.to_dict(), sort_key
        selection = read_session.select_stock_codes(warm_query)
        assert selection.stock_codes == tuple(row.stock_code for row in strict_page.rows), sort_key

    tie_query = read_session.create_query(
        sort_key="decision_date", descending=True, page_size=17
    )
    tie_page = read_session.read_page(tie_query)
    assert tuple(row.stock_code for row in tie_page.rows) == tuple(sorted(_STOCK_CODES))
    null_query = read_session.create_query(
        sort_key="latest_feature_date", descending=True, page_size=17
    )
    null_page = read_session.read_page(null_query)
    null_codes = tuple(
        row.stock_code for row in null_page.rows if row.latest_feature_date is None
    )
    assert null_codes == ("S0000", "S0002")
    assert null_page.rows[-1].stock_code == "S0002"


def test_reader_issued_selection_distinguishes_unrestricted_and_explicit_empty(
    synthetic_read_session_source: dict[str, Any],
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_read_session_source
    filters = (
        DailyMarketTechnicalRuleStateFilterV4.create(
            "volume_ratio_20_including_current", ("match", "unknown")
        ),
    )
    first_query = read_session.create_query(
        rule_state_filters=filters,
        combine_mode="OR",
        sort_key=_RATIO_SORT,
        descending=True,
        page_index=0,
        page_size=4,
    )
    second_page_query = read_session.create_query(
        rule_state_filters=filters,
        combine_mode="OR",
        sort_key=_RATIO_SORT,
        descending=True,
        page_index=2,
        page_size=3,
    )
    unrestricted = read_session.select_stock_codes(first_query)
    same_selection = read_session.select_stock_codes(second_page_query)
    assert unrestricted.stock_codes == same_selection.stock_codes
    assert unrestricted.selection_identity_sha256 == same_selection.selection_identity_sha256
    assert unrestricted.matching_count == len(unrestricted.stock_codes)
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as mutated:
        dataclass_replace(
            unrestricted,
            _candidate_indexes=tuple(reversed(unrestricted._candidate_indexes)),
        )
    assert mutated.value.code == "technical_universe_v4_read_selection_invalid"
    foreign_session = _open_case_session(fixture["excluded_only"])
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as foreign:
        foreign_session.read_selection_page(
            unrestricted, page_index=0, page_size=4
        )
    assert foreign.value.code == "technical_universe_v4_read_selection_source_mismatch"

    def unexpected_sort(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("明示空資格不應掃描或排序候選")

    monkeypatch.setattr(query_module, "_read_index_sort_value", unexpected_sort)
    explicit_empty = read_session.select_stock_codes(first_query, eligible_stock_codes=())
    assert explicit_empty.stock_codes == ()
    assert explicit_empty.has_explicit_empty_eligibility
    assert explicit_empty.selection_identity_sha256 != unrestricted.selection_identity_sha256
    empty_page = read_session.read_selection_page(
        explicit_empty, page_index=0, page_size=4
    )
    assert empty_page.is_explicit_empty
    assert empty_page.page is None
    assert empty_page.rows == ()
    assert empty_page.matching_count == empty_page.page_count == 0
    monkeypatch.undo()

    constrained_query = read_session.create_query(
        stock_filter=("S0001", "S0002", "S0016"),
        sort_key="stock_code",
        page_size=17,
    )
    intersection = read_session.select_stock_codes(
        constrained_query,
        eligible_stock_codes=("S0016", "S9999", "S0002"),
    )
    assert intersection.stock_codes == ("S0002", "S0016")
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as duplicate:
        read_session.select_stock_codes(
            constrained_query,
            eligible_stock_codes=("S0001", "S0001"),
        )
    assert duplicate.value.code == "technical_universe_v4_read_selection_eligibility_invalid"


def test_selection_creation_honors_cancel_while_normalizing_eligibility(
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
) -> None:
    query = read_session.create_query(sort_key="stock_code", page_size=17)
    checks = 0

    def cancel_while_normalizing() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 5

    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as interrupted:
        read_session.select_stock_codes(
            query,
            eligible_stock_codes=tuple(f"S{index:04d}" for index in range(17)),
            cancel_callback=cancel_while_normalizing,
        )
    assert interrupted.value.code == "technical_universe_v4_query_cancelled"


def test_selection_creation_honors_cancel_after_identity_is_built(
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = read_session.create_query(sort_key="stock_code", page_size=17)
    cancelled = False
    original_identity = query_module._read_selection_identity

    def cancel_after_identity(selection: Any) -> str:
        nonlocal cancelled
        identity = original_identity(selection)
        cancelled = True
        return identity

    monkeypatch.setattr(query_module, "_read_selection_identity", cancel_after_identity)
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as interrupted:
        read_session.select_stock_codes(
            query, cancel_callback=lambda: cancelled
        )
    assert interrupted.value.code == "technical_universe_v4_query_cancelled"


def test_explicit_empty_selection_page_honors_cancel_after_page_construction(
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = read_session.create_query(sort_key="stock_code", page_size=17)
    selection = read_session.select_stock_codes(query, eligible_stock_codes=())
    cancelled = False
    page_type = query_module.DailyMarketTechnicalUniverseV4ReadSelectionPage

    def cancel_after_page_construction(**kwargs: Any) -> Any:
        nonlocal cancelled
        page = page_type(**kwargs)
        cancelled = True
        return page

    monkeypatch.setattr(
        query_module,
        "DailyMarketTechnicalUniverseV4ReadSelectionPage",
        cancel_after_page_construction,
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as interrupted:
        read_session.read_selection_page(
            selection,
            page_index=0,
            page_size=17,
            cancel_callback=lambda: cancelled,
        )
    assert interrupted.value.code == "technical_universe_v4_query_cancelled"


def test_selection_pages_slice_one_global_sort_and_keep_exact_page_pins(
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = read_session.create_query(
        sort_key=_RATIO_SORT,
        descending=True,
        page_index=0,
        page_size=17,
    )
    selection = read_session.select_stock_codes(query)
    expected = tuple(row.stock_code for row in read_session.read_page(query).rows)
    assert selection.stock_codes == expected

    original_sort_value = query_module._read_index_sort_value
    sort_value_calls = 0

    def count_sort_value(*args: Any, **kwargs: Any) -> Any:
        nonlocal sort_value_calls
        sort_value_calls += 1
        return original_sort_value(*args, **kwargs)

    monkeypatch.setattr(query_module, "_read_index_sort_value", count_sort_value)
    page_codes: list[str] = []
    selection_ids: set[str] = set()
    query_ids: set[str] = set()
    for page_index in range(5):
        result = read_session.read_selection_page(
            selection, page_index=page_index, page_size=4
        )
        assert result.page is not None
        assert result.matching_count == 17
        assert result.page_count == 5
        assert result.page.query.page_index == page_index
        assert result.page.query.page_size == 4
        page_codes.extend(row.stock_code for row in result.rows)
        selection_ids.add(result.selection_identity_sha256)
        query_ids.add(result.page.query.query_identity_sha256)
    assert tuple(page_codes) == expected
    assert len(selection_ids) == 1
    assert len(query_ids) == 5
    # materialization只重驗本頁 rows 的排序值，沒有每頁重掃/重排 full-N。
    assert sort_value_calls == len(selection.stock_codes)


def test_selection_stock_reads_each_page_artifact_once_and_checks_membership(
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = read_session.create_query(
        sort_key=_RATIO_SORT, descending=True, page_index=0, page_size=17
    )
    selection = read_session.select_stock_codes(query)
    target_code = selection.stock_codes[0]
    original_read = query_module._read_session_child_artifact
    observed_paths: list[Path] = []

    def count_artifact_reads(reference: Any, cancel_callback: Any) -> Any:
        observed_paths.append(reference.manifest_path)
        return original_read(reference, cancel_callback)

    monkeypatch.setattr(query_module, "_read_session_child_artifact", count_artifact_reads)
    page, stock = read_daily_market_technical_universe_v4_page_and_stock_from_session(
        query, target_code, read_session
    )
    selected_row = next(row for row in page.rows if row.stock_code == target_code)
    assert stock.snapshot.snapshot_identity_sha256 == selected_row.snapshot_identity_sha256
    assert stock.snapshot.source_identity == selected_row.source_identity
    assert len(observed_paths) == len(set(observed_paths))

    observed_paths.clear()
    selected_stock = read_daily_market_technical_universe_v4_stock_from_selection(
        selection,
        target_code,
        read_session,
        page_index=0,
        page_size=4,
    )
    assert selected_stock.origin_query.page_size == 4
    assert selected_stock.snapshot.stock_code == target_code
    assert len(observed_paths) == 1
    with pytest.raises(DailyMarketTechnicalUniverseV4StockError) as not_in_page:
        read_daily_market_technical_universe_v4_stock_from_selection(
            selection,
            selection.stock_codes[-1],
            read_session,
            page_index=0,
            page_size=4,
        )
    assert not_in_page.value.code == "technical_universe_v4_stock_not_in_origin_page"


def test_selection_cancel_during_materialization_returns_no_partial_page(
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = read_session.create_query(sort_key="stock_code", page_size=17)
    selection = read_session.select_stock_codes(query)
    cancelled = False
    original_read = DailyMarketTechnicalSnapshotV4Repository.read_exact

    def cancel_after_exact_child(self: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal cancelled
        result = original_read(self, *args, **kwargs)
        cancelled = True
        return result

    monkeypatch.setattr(
        DailyMarketTechnicalSnapshotV4Repository, "read_exact", cancel_after_exact_child
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as interrupted:
        read_session.read_selection_page(
            selection,
            page_index=0,
            page_size=17,
            cancel_callback=lambda: cancelled,
        )
    assert interrupted.value.code == "technical_universe_v4_query_cancelled"


def test_session_selected_stock_reopens_exact_snapshot_and_cutoff(
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
) -> None:
    query = _session_query(read_session, sort_key="stock_code", page_size=8)
    stock = read_daily_market_technical_universe_v4_stock_from_session(
        query, "S0001", read_session
    )
    assert stock.snapshot.stock_code == "S0001"
    assert stock.snapshot.decision_date == _DECISION_DATE
    assert stock.snapshot.decision_cutoff == datetime.combine(
        _DECISION_DATE, time(16, 0), tzinfo=_TAIPEI
    )
    assert all(
        rule.decision_cutoff == stock.snapshot.decision_cutoff
        and (rule.feature_date is None or rule.feature_date <= _DECISION_DATE)
        for rule in stock.snapshot.rules
    )
    assert stock.snapshot.availability_status == "unknown"


def test_empty_excluded_and_partial_receipts_keep_their_exact_denominators(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    fixture = synthetic_read_session_source
    empty = _open_case_session(fixture["empty"])
    empty_page = empty.read_page(empty.create_query())
    assert empty.index_stock_count == 0
    assert empty_page.is_complete
    assert empty_page.query.declared_count == 0
    assert empty_page.query.segment_count == 0
    assert empty_page.rows == ()

    excluded = _open_case_session(fixture["excluded_only"])
    excluded_page = excluded.read_page(excluded.create_query())
    assert excluded.index_stock_count == 0
    assert excluded_page.is_complete
    assert excluded_page.query.declared_count == 1
    assert excluded_page.query.included_count == 0
    assert excluded_page.query.excluded_count == 1
    assert excluded_page.processed_segment_count == 1
    assert excluded_page.exclusion_reasons == (("X9999", "明示排除的完整母體成員"),)

    partial = _open_case_session(fixture["partial"])
    partial_page = partial.read_page(partial.create_query())
    assert partial_page.is_complete is False
    assert partial_page.query.receipt_status == "cancelled"
    assert partial_page.query.segment_count == 2
    assert partial_page.processed_segment_count == 1
    assert partial_page.counts.processed_count == len(_STOCK_CODES)
    assert partial_page.counts.pending_count == 0
    assert partial_page.pending_stock_codes == ()
    assert tuple(row.stock_code for row in partial_page.rows) == _STOCK_CODES[:50]


def test_session_rejects_source_mismatch_overflow_and_cancel_inside_parent_read(
    synthetic_read_session_source: dict[str, Any],
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = synthetic_read_session_source
    query = _session_query(read_session)
    payload = query.to_dict()
    payload["plan_sha256"] = "f" * 64
    mismatched = DailyMarketTechnicalUniverseV4Query.from_dict(_resign_query(payload))
    assert read_session.matches_source(query)
    assert not read_session.matches_source(mismatched)
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as mismatch:
        read_session.read_page(mismatched)
    assert mismatch.value.code == "technical_universe_v4_read_session_source_mismatch"

    copied_root = tmp_path / "same-bytes-different-root"
    _copy_tree_with_extended_paths(fixture["store_root"], copied_root)
    copied_payload = query.to_dict()
    copied_payload["store_output_root"] = str(copied_root)
    copied_query = DailyMarketTechnicalUniverseV4Query.from_dict(
        _resign_query(copied_payload)
    )
    assert not read_session.matches_source(copied_query)
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as root_mismatch:
        read_session.read_page(copied_query)
    assert root_mismatch.value.code == "technical_universe_v4_read_session_source_mismatch"

    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as overflow:
        open_daily_market_technical_universe_v4_read_session(
            store_output_root=fixture["store_root"],
            generation_identity_sha256=fixture["plan"].generation_identity_sha256,
            plan_identity_sha256=fixture["plan"].identity_sha256,
            plan_sha256=fixture["plan_sha256"],
            receipt_identity_sha256=fixture["complete"].identity_sha256,
            receipt_sha256=fixture["complete"].content_sha256,
            max_index_bytes=1,
        )
    assert overflow.value.code == "technical_universe_v4_read_session_index_limit"

    cancelled = False
    original_read = DailyMarketTechnicalSnapshotV4Repository.read_exact
    observed_reads = 0

    def cancel_after_verified_child(self: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal cancelled, observed_reads
        result = original_read(self, *args, **kwargs)
        observed_reads += 1
        if observed_reads == 1:
            cancelled = True
        return result

    monkeypatch.setattr(
        DailyMarketTechnicalSnapshotV4Repository, "read_exact", cancel_after_verified_child
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as cancel_error:
        open_daily_market_technical_universe_v4_read_session(
            store_output_root=fixture["store_root"],
            generation_identity_sha256=fixture["plan"].generation_identity_sha256,
            plan_identity_sha256=fixture["plan"].identity_sha256,
            plan_sha256=fixture["plan_sha256"],
            receipt_identity_sha256=fixture["complete"].identity_sha256,
            receipt_sha256=fixture["complete"].content_sha256,
            cancel_callback=lambda: cancelled,
        )
    assert cancelled and observed_reads >= 1
    assert "cancel" in cancel_error.value.code


def test_session_and_fresh_bookmark_read_reject_child_tamper(
    synthetic_read_session_source: dict[str, Any],
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
) -> None:
    fixture = synthetic_read_session_source
    query = _session_query(read_session, page_size=17)
    reference = read_session._artifact_references[0]
    manifest_path = to_internal_io_path(reference.manifest_path)
    original = Path(manifest_path).read_bytes()
    try:
        Path(manifest_path).write_bytes(b'{"schema_version":"tampered"}')
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError):
            read_session.read_page(query)
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError):
            _open_session(fixture)
        with pytest.raises(DailyMarketTechnicalUniverseV4BookmarkError):
            create_daily_market_technical_universe_v4_bookmark_fresh(
                query, "S0001", scroll_position=0
            )
    finally:
        Path(manifest_path).write_bytes(original)


def test_fresh_bookmark_revalidates_once_then_new_process_restores_strictly(
    synthetic_read_session_source: dict[str, Any],
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_read_session_source
    query = _session_query(read_session, sort_key=_RATIO_SORT, descending=True, page_size=17)
    selections = ((query, "S0001"), (query, "S0016"))
    original_reader = DailyMarketTechnicalUniverseV4StoreReader.read_exact_with_verified_parent_callback
    strict_revalidations = 0
    original_child_reader = query_module._read_session_child_artifact
    child_manifest_reads: list[Path] = []

    def count_fresh_reads(self: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal strict_revalidations
        strict_revalidations += 1
        return original_reader(self, *args, **kwargs)

    def count_child_reads(reference: Any, cancel_callback: Any) -> Any:
        child_manifest_reads.append(reference.manifest_path)
        return original_child_reader(reference, cancel_callback)

    monkeypatch.setattr(
        DailyMarketTechnicalUniverseV4StoreReader,
        "read_exact_with_verified_parent_callback",
        count_fresh_reads,
    )
    monkeypatch.setattr(query_module, "_read_session_child_artifact", count_child_reads)
    bookmark = create_daily_market_technical_universe_v4_bookmark_fresh(
        query,
        "S0001",
        scroll_position=23,
        comparison_selections=selections,
    )
    assert strict_revalidations == 1
    assert len(child_manifest_reads) == len(set(child_manifest_reads))
    assert bookmark.stock_code == "S0001"
    assert bookmark.source == "technical_universe_research_bookmark"
    assert len(bookmark.comparison_selections) == 2
    assert not Path(fixture["database"]).exists()

    saved = tmp_path / "saved-bookmark.json"
    saved.write_text(bookmark.to_json(), encoding="utf-8")
    script = (
        "import json,sys; "
        "from pathlib import Path; "
        "from app_module.daily_market_technical_universe_v4_bookmark import "
        "read_daily_market_technical_universe_v4_bookmark; "
        "state=read_daily_market_technical_universe_v4_bookmark(Path(sys.argv[1]).read_text(encoding='utf-8')); "
        "print(json.dumps({'stock':state.selected_stock.snapshot.stock_code,'comparisons':len(state.bookmark.comparison_selections),'complete':state.origin_page.is_complete},sort_keys=True))"
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    repo_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(repo_root)
    completed = subprocess.run(
        [sys.executable, "-c", script, str(saved)],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "stock": "S0001",
        "comparisons": 2,
        "complete": True,
    }
