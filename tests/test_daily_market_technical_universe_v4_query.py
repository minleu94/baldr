"""full-N v4 query 的真實跨段來源、全域排序與固定重開契約。"""

from __future__ import annotations

from collections import Counter
from contextvars import copy_context
from dataclasses import replace as dataclass_replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from threading import Thread
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_parent_v4_query as parent_query_module
import app_module.daily_market_technical_snapshot_v4_repository as snapshot_repository_module
import app_module.daily_market_technical_universe_v4_query as universe_query_module
import app_module.personal_data_paths as personal_data_paths_module
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalSnapshotV4Repository,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCOPE,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4QueryError,
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
    open_daily_market_technical_universe_v4_read_session,
    read_daily_market_technical_universe_v4_page,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY,
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4StoreReader,
    DailyMarketTechnicalUniverseV4StoreWriter,
    daily_market_technical_source_clock_v4_from_dict,
)
from app_module.daily_market_technical_parent_v4_producer import (
    produce_daily_market_technical_parent_v4,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalCohortV4,
    read_daily_market_technical_parent_capture_v4,
)
from app_module.daily_market_technical_universe_v4_stock import (
    DailyMarketTechnicalUniverseV4StockError,
    read_daily_market_technical_universe_v4_stock,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)
_START_DATE = _DECISION_DATE - timedelta(days=39)
_RATIO_KEY = "volume_ratio_20_including_current.ratio"
_INCLUDED = tuple(f"S{index:04d}" for index in range(257))
_EXCLUDED = ("X9999",)


@pytest.fixture(scope="module")
def synthetic_full_store() -> Any:
    """以真 SQLite、兩個 parent 與固定 receipt chain 建立 257 股 store。"""

    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix="uv4query-", dir=temporary_root)).resolve(strict=True)
    try:
        database = root / "synthetic-prices.sqlite"
        _write_source(database, (*_INCLUDED, *_EXCLUDED), missing_code="S0000")
        configured_root = _long_configured_root(root)
        scope = ResearchCaptureWriteScope(configured_root, database)
        segment_cohorts = _segment_cohorts(_full_cohort())
        parent_references: list[DailyMarketTechnicalUniverseV4ParentReceiptReference] = []
        parent_packages: list[dict[str, Any]] = []
        for segment_index, segment_cohort in enumerate(segment_cohorts):
            parent_root = scope.root / "parents" / f"segment-{segment_index + 1:06d}"
            child_root = scope.root / "children" / f"segment-{segment_index + 1:06d}"
            result = produce_daily_market_technical_parent_v4(
                source_database=database,
                cohort=segment_cohort,
                decision_cutoff=datetime.combine(
                    _DECISION_DATE, time(16, 0), tzinfo=_TAIPEI
                ),
                child_output_root=child_root,
                parent_root=parent_root,
                research_scope=scope,
            )
            assert result.status == "complete", result.error_code
            assert result.plan is not None and result.receipt is not None
            reference = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
                parent_root,
                parent_plan_identity_sha256=result.plan.identity_sha256,
                parent_plan_sha256=result.plan.content_sha256,
                parent_receipt_identity_sha256=result.receipt.identity_sha256,
                parent_receipt_sha256=result.receipt.content_sha256,
            )
            parent_references.append(reference)
            parent_packages.append({"plan": result.plan.to_dict(), "receipt": result.receipt.to_dict()})

        source_clock_payload = parent_packages[0]["plan"]["source_clock"]
        assert all(
            package["plan"]["source_clock"] == source_clock_payload
            for package in parent_packages
        )
        cohort = _full_cohort()
        plan = DailyMarketTechnicalUniverseV4Plan.build(
            cohort,
            source_clock=daily_market_technical_source_clock_v4_from_dict(source_clock_payload),
        )
        assert tuple(
            (
                len(plan.segment_cohort(index).included_stock_codes),
                len(plan.segment_cohort(index).excluded_stock_codes),
            )
            for index in range(len(plan.segments))
        ) == ((256, 1), (1, 0))

        store_output_root = scope.root / "full-store"
        writer = DailyMarketTechnicalUniverseV4StoreWriter(
            store_output_root,
            research_scope=scope,
        )
        initial = writer.start(plan)
        plan_sha256 = hashlib.sha256(plan.to_json().encode("utf-8")).hexdigest()
        first_progress = writer.record_segment_parent(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            initial.identity_sha256,
            expected_previous_receipt_sha256=initial.content_sha256,
            segment_index=0,
            parent_reference=parent_references[0],
        )
        partial_pin = {
            "receipt_identity_sha256": first_progress.identity_sha256,
            "receipt_sha256": first_progress.content_sha256,
        }
        cancelled = writer.mark_terminal(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            first_progress.identity_sha256,
            expected_previous_receipt_sha256=first_progress.content_sha256,
            status="cancelled",
            error_code="synthetic_cancel_after_segment_one",
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
            parent_reference=parent_references[1],
        )
        complete = writer.complete(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            second_progress.identity_sha256,
            expected_previous_receipt_sha256=second_progress.content_sha256,
        )
        assert complete.status == "complete"
        database.unlink()
        yield {
            "temporary_root": root,
            "database": database,
            "scope": scope,
            "plan": plan,
            "store_output_root": store_output_root,
            "plan_sha256": plan_sha256,
            "partial_pin": partial_pin,
            "complete": complete,
            "writer": writer,
        }
    finally:
        if root.parent != temporary_root:
            raise AssertionError("technical_universe_v4_fixture_path_escape")
        cleanup_path = str(root)
        if sys.platform == "win32":
            cleanup_path = "\\\\?\\" + cleanup_path
        shutil.rmtree(cleanup_path)


@pytest.fixture
def synthetic_small_full_store() -> Any:
    """建立 17 股真實 parent/store，覆蓋兩個 child artifact 的小型查詢。"""

    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix="uv4query-small-", dir=temporary_root)).resolve(strict=True)
    stock_codes = tuple(f"S{index:04d}" for index in range(17))
    excluded_codes = ("X9999",)
    try:
        database = root / "synthetic-prices.sqlite"
        _write_source(database, (*stock_codes, *excluded_codes), missing_code="S0000")
        scope = ResearchCaptureWriteScope(_long_configured_root(root), database)
        cohort = DailyMarketTechnicalUniverseV4Cohort.create(
            universe_id="synthetic-small-query-v4",
            population_version="fixture-small-2026-10-06",
            decision_date=_DECISION_DATE,
            raw_stock_codes=(*stock_codes, *excluded_codes),
            excluded_stock_codes=excluded_codes,
            exclusion_reasons={"X9999": "隔離 fixture 的排除測試"},
        )
        segment_cohort = _segment_cohorts(cohort)[0]
        parent_root = scope.root / "parents" / "segment-000001"
        child_root = scope.root / "children" / "segment-000001"
        parent_result = produce_daily_market_technical_parent_v4(
            source_database=database,
            cohort=segment_cohort,
            decision_cutoff=datetime.combine(
                _DECISION_DATE, time(16, 0), tzinfo=_TAIPEI
            ),
            child_output_root=child_root,
            parent_root=parent_root,
            research_scope=scope,
        )
        assert parent_result.status == "complete", parent_result.error_code
        assert parent_result.plan is not None and parent_result.receipt is not None
        plan = DailyMarketTechnicalUniverseV4Plan.build(
            cohort,
            source_clock=daily_market_technical_source_clock_v4_from_dict(
                parent_result.plan.to_dict()["source_clock"]
            ),
        )
        assert len(plan.segments) == 1
        store_output_root = scope.root / "small-full-store"
        writer = DailyMarketTechnicalUniverseV4StoreWriter(
            store_output_root,
            research_scope=scope,
        )
        initial = writer.start(plan)
        reference = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
            parent_root,
            parent_plan_identity_sha256=parent_result.plan.identity_sha256,
            parent_plan_sha256=parent_result.plan.content_sha256,
            parent_receipt_identity_sha256=parent_result.receipt.identity_sha256,
            parent_receipt_sha256=parent_result.receipt.content_sha256,
        )
        progress = writer.record_segment_parent(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            initial.identity_sha256,
            expected_previous_receipt_sha256=initial.content_sha256,
            segment_index=0,
            parent_reference=reference,
        )
        complete = writer.complete(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            progress.identity_sha256,
            expected_previous_receipt_sha256=progress.content_sha256,
        )
        assert complete.status == "complete"
        plan_sha256 = hashlib.sha256(plan.to_json().encode("utf-8")).hexdigest()
        database.unlink()
        yield {
            "temporary_root": root,
            "database": database,
            "scope": scope,
            "plan": plan,
            "store_output_root": store_output_root,
            "plan_sha256": plan_sha256,
            "complete": complete,
            "writer": writer,
        }
    finally:
        if root.parent != temporary_root:
            raise AssertionError("technical_universe_v4_small_fixture_path_escape")
        cleanup_path = str(root)
        if sys.platform == "win32":
            cleanup_path = "\\\\?\\" + cleanup_path
        shutil.rmtree(cleanup_path)


def _write_source(path: Path, stock_codes: tuple[str, ...], *, missing_code: str) -> None:
    connection = sqlite3.connect(to_internal_io_path(path))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str | None, str | None, int]] = []
            for stock_code in stock_codes:
                if stock_code == missing_code:
                    continue
                for offset in range(40):
                    close: str | None = str(100 + offset)
                    if stock_code == "S0002" and offset == 39:
                        close = None
                    high = str(101 + offset)
                    low = str(99 + offset)
                    volume = 100
                    if offset == 39:
                        if stock_code == "S0001":
                            volume = 9000
                        elif stock_code == "S0256":
                            volume = 9
                    rows.append((
                        (_START_DATE + timedelta(days=offset)).isoformat(),
                        stock_code,
                        str(100 + offset),
                        high,
                        low,
                        close,
                        volume,
                    ))
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        connection.close()


def _long_configured_root(temporary_root: Path) -> Path:
    component = "research-root-" + ("x" * 66)
    return temporary_root / component / component / component


def _full_cohort() -> DailyMarketTechnicalUniverseV4Cohort:
    return DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-full-query-v4",
        population_version="fixture-2026-10-06",
        decision_date=_DECISION_DATE,
        raw_stock_codes=(*_INCLUDED, *_EXCLUDED, _INCLUDED[0].lower()),
        excluded_stock_codes=_EXCLUDED,
        exclusion_reasons={"X9999": "全母體查詢保留的原始排除理由"},
    )


def _segment_cohorts(
    cohort: DailyMarketTechnicalUniverseV4Cohort,
) -> tuple[DailyMarketTechnicalCohortV4, ...]:
    count = max(
        (len(cohort.included_stock_codes) + 255) // 256,
        (len(cohort.excluded_stock_codes) + 255) // 256,
    )
    reasons = dict(cohort.exclusion_reasons)
    segments: list[DailyMarketTechnicalCohortV4] = []
    for segment_index in range(count):
        included_start = min(len(cohort.included_stock_codes), segment_index * 256)
        excluded_start = min(len(cohort.excluded_stock_codes), segment_index * 256)
        included = cohort.included_stock_codes[included_start:included_start + 256]
        excluded = cohort.excluded_stock_codes[excluded_start:excluded_start + 256]
        segments.append(DailyMarketTechnicalCohortV4.create(
            universe_id=cohort.universe_id,
            population_version=cohort.population_version,
            decision_date=cohort.decision_date,
            included_stock_codes=included,
            excluded_stock_codes=excluded,
            exclusion_reasons={code: reasons[code] for code in excluded},
        ))
    return tuple(segments)


def _make_query(
    fixture: dict[str, Any],
    *,
    receipt_identity_sha256: str | None = None,
    receipt_sha256: str | None = None,
    **conditions: Any,
) -> DailyMarketTechnicalUniverseV4Query:
    plan = fixture["plan"]
    complete = fixture["complete"]
    return DailyMarketTechnicalUniverseV4Query.create(
        store_output_root=fixture["store_output_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt_identity_sha256 or complete.identity_sha256,
        receipt_sha256=receipt_sha256 or complete.content_sha256,
        **conditions,
    )


def _open_small_read_session(
    fixture: dict[str, Any],
) -> Any:
    plan = fixture["plan"]
    complete = fixture["complete"]
    return open_daily_market_technical_universe_v4_read_session(
        store_output_root=fixture["store_output_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=complete.identity_sha256,
        receipt_sha256=complete.content_sha256,
    )


def _read_selection_page_payload(value: Any) -> dict[str, Any]:
    """保留 selection wrapper 身份欄位並序列化完整 inner page。"""
    page = value.page
    return {
        "selection_identity_sha256": value.selection_identity_sha256,
        "page_index": value.page_index,
        "page_size": value.page_size,
        "matching_count": value.matching_count,
        "page_count": value.page_count,
        "is_explicit_empty": value.is_explicit_empty,
        "page_query_identity_sha256": None if page is None else page.query.query_identity_sha256,
        "page": None if page is None else page.to_dict(),
    }


def _resign_query(payload: dict[str, Any]) -> dict[str, Any]:
    body = {key: item for key, item in payload.items() if key != "query_identity_sha256"}
    payload["query_identity_sha256"] = hashlib.sha256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _receipt_path(fixture: dict[str, Any], receipt_identity_sha256: str) -> Path:
    plan = fixture["plan"]
    return (
        Path(fixture["store_output_root"])
        / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY
        / "generations"
        / plan.generation_identity_sha256
        / "receipts"
        / f"{receipt_identity_sha256}.json"
    )


def test_small_query_reuses_verified_batches_and_fresh_read_rejects_artifact_tamper(
    synthetic_small_full_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_small_full_store
    query = _make_query(
        fixture,
        stock_filter=("S0016",),
        sort_key="stock_code",
        page_size=1,
    )
    original_reader = DailyMarketTechnicalSnapshotV4Repository.read_exact
    manifest_reads: list[str] = []

    def observed_child_read(self: Any, *args: Any, **kwargs: Any) -> Any:
        manifest_reads.append(str(args[0]))
        return original_reader(self, *args, **kwargs)

    monkeypatch.setattr(
        DailyMarketTechnicalSnapshotV4Repository,
        "read_exact",
        observed_child_read,
    )
    page = read_daily_market_technical_universe_v4_page(query)

    assert tuple(row.stock_code for row in page.rows) == ("S0016",)
    assert page.matching_count == 1
    assert len(set(manifest_reads)) == 2
    read_counts = Counter(manifest_reads)
    assert sorted(read_counts.values()) == [1, 2]
    selected_manifest = next(
        manifest for manifest, count in read_counts.items() if count == 2
    )
    untouched_manifest = next(
        manifest for manifest, count in read_counts.items() if count == 1
    )
    assert selected_manifest != untouched_manifest

    manifest_path = to_internal_io_path(Path(untouched_manifest))
    original_manifest = Path(manifest_path).read_bytes()
    try:
        Path(manifest_path).write_bytes(b'{"schema_version":"tampered"}')
        manifest_reads.clear()
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError):
            read_daily_market_technical_universe_v4_page(query)
        assert untouched_manifest in manifest_reads
    finally:
        Path(manifest_path).write_bytes(original_manifest)

    wrong_method_payload = query.to_dict()
    wrong_method_payload["method_contracts_sha256"] = "f" * 64
    wrong_method_query = DailyMarketTechnicalUniverseV4Query.from_dict(
        _resign_query(wrong_method_payload)
    )
    with pytest.raises(
        DailyMarketTechnicalUniverseV4QueryError,
        match="source_identity_mismatch",
    ):
        read_daily_market_technical_universe_v4_page(wrong_method_query)

    wrong_date_payload = query.to_dict()
    wrong_date_payload["decision_date"] = (_DECISION_DATE + timedelta(days=1)).isoformat()
    wrong_date_query = DailyMarketTechnicalUniverseV4Query.from_dict(
        _resign_query(wrong_date_payload)
    )
    with pytest.raises(
        DailyMarketTechnicalUniverseV4QueryError,
        match="source_identity_mismatch",
    ):
        read_daily_market_technical_universe_v4_page(wrong_date_query)


def test_typed_read_session_builder_requires_complete_same_read_callback(
    synthetic_small_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_small_full_store
    plan = fixture["plan"]
    complete = fixture["complete"]
    pins = {
        "store_output_root": fixture["store_output_root"],
        "generation_identity_sha256": plan.generation_identity_sha256,
        "plan_identity_sha256": plan.identity_sha256,
        "plan_sha256": fixture["plan_sha256"],
        "receipt_identity_sha256": complete.identity_sha256,
        "receipt_sha256": complete.content_sha256,
    }
    builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(**pins)
    reader = DailyMarketTechnicalUniverseV4StoreReader(fixture["store_output_root"])
    state = reader.read_exact_with_verified_parent_callback(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        complete.identity_sha256,
        expected_receipt_sha256=complete.content_sha256,
        expected_plan_sha256=fixture["plan_sha256"],
        parent_verified_callback=builder.consume_verified_parent,
    )
    assert isinstance(reader.output_root, Path)
    assert builder.store_output_root == str(reader.output_root)
    built_session = builder.build_verified_session(root=reader.output_root, state=state)
    public_session = open_daily_market_technical_universe_v4_read_session(**pins)

    built_query = built_session.create_query(sort_key="stock_code", page_size=32)
    public_query = public_session.create_query(sort_key="stock_code", page_size=32)
    assert built_session.read_session_identity_sha256 == public_session.read_session_identity_sha256
    assert built_session.source_counts == state.counts
    assert built_session.read_page(built_query).to_dict() == public_session.read_page(public_query).to_dict()
    assert builder.verified_session is None
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as reuse_error:
        builder.build_verified_session(root=reader.output_root, state=state)
    assert reuse_error.value.code == "technical_universe_v4_read_session_builder_already_finished"

    no_callback_builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(**pins)
    uncollected_state = reader.read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        complete.identity_sha256,
        expected_receipt_sha256=complete.content_sha256,
        expected_plan_sha256=fixture["plan_sha256"],
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as error:
        no_callback_builder.build_verified_session(root=reader.output_root, state=uncollected_state)
    assert error.value.code == "technical_universe_v4_read_session_segment_mismatch"
    assert no_callback_builder.verified_session is None

    wrong_pin_builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(
        **{**pins, "receipt_sha256": "0" * 64}
    )
    wrong_pin_state = reader.read_exact_with_verified_parent_callback(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        complete.identity_sha256,
        expected_receipt_sha256=complete.content_sha256,
        expected_plan_sha256=fixture["plan_sha256"],
        parent_verified_callback=wrong_pin_builder.consume_verified_parent,
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as pin_error:
        wrong_pin_builder.build_verified_session(root=reader.output_root, state=wrong_pin_state)
    assert pin_error.value.code == "technical_universe_v4_read_session_store_pin_mismatch"
    assert wrong_pin_builder.verified_session is None

    rebind_builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(**pins)
    rebind_builder._bind_to_verified_bundle(
        bundle_output_root=fixture["store_output_root"],
        bundle_identity_sha256="a" * 64,
        expected_manifest_sha256="b" * 64,
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as rebind_error:
        rebind_builder._bind_to_verified_bundle(
            bundle_output_root=fixture["store_output_root"],
            bundle_identity_sha256="c" * 64,
            expected_manifest_sha256="d" * 64,
        )
    assert rebind_error.value.code == "technical_universe_v4_read_session_builder_already_bound"


def test_cancelled_read_session_builder_does_not_canonicalize_or_construct_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_attempts: list[str] = []

    def reject_reader_construction(self: Any, root: str | Path) -> None:
        construction_attempts.append(str(root))
        raise AssertionError("StoreReader must not be constructed after cancellation")

    monkeypatch.setattr(
        DailyMarketTechnicalUniverseV4StoreReader,
        "__init__",
        reject_reader_construction,
    )
    missing_root = tmp_path / "root-that-does-not-exist"
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as error:
        DailyMarketTechnicalUniverseV4ReadSessionBuilder(
            store_output_root=missing_root,
            generation_identity_sha256="1" * 64,
            plan_identity_sha256="2" * 64,
            plan_sha256="3" * 64,
            receipt_identity_sha256="4" * 64,
            receipt_sha256="5" * 64,
            cancel_callback=lambda: True,
        )
    assert error.value.code == "technical_universe_v4_query_cancelled"
    assert construction_attempts == []


def test_complete_full_n_query_roundtrips_counts_and_uses_only_saved_sources(
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store
    query = _make_query(fixture, sort_key=_RATIO_KEY, page_size=256)
    reopened = DailyMarketTechnicalUniverseV4Query.from_json(query.to_json())
    assert reopened == query
    page = read_daily_market_technical_universe_v4_page(reopened)

    assert page.is_complete is True
    assert page.coverage_scope == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCOPE
    assert page.aggregation_scope == "global_full_universe"
    assert page.full_n_aggregation is True
    assert page.full_market_claim is False
    assert page.to_dict()["full_market_claim"] is False
    assert page.to_dict()["counts"] == {
        "declared_count": 258,
        "included_count": 257,
        "excluded_count": 1,
        "processed_count": 257,
        "pending_count": 0,
        "missing_data_count": 1,
        "missing_data_pending_count": 0,
        "matching_count": 257,
        "page_count": 2,
        "unknown_rule_count": 2,
        "processed_segment_count": 2,
        "segment_count": 2,
    }
    assert page.pending_stock_codes == ()
    assert page.missing_data_stock_codes == ("S0000",)
    assert page.unknown_rule_stock_codes == ("S0000", "S0002")
    assert page.exclusion_reasons == (("X9999", "全母體查詢保留的原始排除理由"),)
    assert len(page.rows) == 256
    assert page.rows[0].stock_code == "S0256"
    assert page.rows[0].raw_row_count == 40
    low_ratio = page.rows[0].rule("volume_ratio_20_including_current").ratio
    high_row = next(row for row in page.rows if row.stock_code == "S0001")
    high_ratio = high_row.rule("volume_ratio_20_including_current").ratio
    assert isinstance(low_ratio, Decimal)
    assert isinstance(high_ratio, Decimal)
    assert low_ratio < high_ratio


def test_global_decimal_order_null_tail_and_stable_stock_tiebreak(
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store
    ascending = _make_query(fixture, sort_key=_RATIO_KEY, page_size=1)
    first_ascending = read_daily_market_technical_universe_v4_page(ascending)
    assert tuple(row.stock_code for row in first_ascending.rows) == ("S0256",)
    assert first_ascending.matching_count == 257

    descending = _make_query(
        fixture,
        sort_key=_RATIO_KEY,
        descending=True,
        page_size=1,
    )
    first_descending = read_daily_market_technical_universe_v4_page(descending)
    assert tuple(row.stock_code for row in first_descending.rows) == ("S0001",)

    for reverse in (False, True):
        tail_query = _make_query(
            fixture,
            sort_key=_RATIO_KEY,
            descending=reverse,
            page_index=85,
            page_size=3,
        )
        tail = read_daily_market_technical_universe_v4_page(tail_query)
        assert tuple(row.stock_code for row in tail.rows) == ("S0000", "S0002")

    tied = _make_query(fixture, sort_key=_RATIO_KEY, page_size=256)
    tied_rows = read_daily_market_technical_universe_v4_page(tied).rows
    null_codes: list[str] = []
    seen_null = False
    for left, right in zip(tied_rows, tied_rows[1:]):
        left_value = left.rule("volume_ratio_20_including_current").ratio
        right_value = right.rule("volume_ratio_20_including_current").ratio
        if left_value is not None and left_value == right_value:
            assert left.stock_code < right.stock_code
    for row in tied_rows:
        if row.rule("volume_ratio_20_including_current").ratio is None:
            seen_null = True
            null_codes.append(row.stock_code)
        else:
            assert seen_null is False
    assert null_codes == sorted(null_codes)


def test_and_or_state_filters_and_stock_filter_apply_before_pagination(
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store
    ma_no_match = DailyMarketTechnicalRuleStateFilterV4.create(
        "ma5_20_golden_cross", ("no_match",)
    )
    ratio_no_match_or_unknown = DailyMarketTechnicalRuleStateFilterV4.create(
        "volume_ratio_20_including_current", ("no_match", "unknown")
    )
    and_query = _make_query(
        fixture,
        rule_state_filters=(ma_no_match, DailyMarketTechnicalRuleStateFilterV4.create(
            "volume_ratio_20_including_current", ("unknown",)
        )),
        combine_mode="AND",
        page_size=1,
    )
    and_page = read_daily_market_technical_universe_v4_page(and_query)
    assert and_page.matching_count == 0
    assert and_page.page_count == 0

    or_query = _make_query(
        fixture,
        rule_state_filters=(ma_no_match, ratio_no_match_or_unknown),
        combine_mode="OR",
        page_size=256,
    )
    or_page = read_daily_market_technical_universe_v4_page(or_query)
    assert or_page.matching_count == 257

    filtered = _make_query(
        fixture,
        stock_filter=("S0000", "S0001", "S0256"),
        sort_key="stock_code",
        page_index=2,
        page_size=1,
    )
    filtered_page = read_daily_market_technical_universe_v4_page(filtered)
    assert filtered_page.matching_count == 3
    assert tuple(row.stock_code for row in filtered_page.rows) == ("S0256",)


def test_partial_receipt_reopens_exactly_after_resume_without_false_completion(
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store
    partial = fixture["partial_pin"]
    query = _make_query(
        fixture,
        receipt_identity_sha256=partial["receipt_identity_sha256"],
        receipt_sha256=partial["receipt_sha256"],
        page_size=256,
    )
    reopened = DailyMarketTechnicalUniverseV4Query.from_json(query.to_json())
    page = read_daily_market_technical_universe_v4_page(reopened)
    assert reopened == query
    assert page.query.receipt_status == "partial"
    assert page.is_complete is False
    assert page.counts.processed_count == 256
    assert page.counts.pending_count == 1
    assert page.counts.missing_data_count == 1
    assert page.counts.missing_data_pending_count == 1
    assert page.pending_stock_codes == ("S0256",)
    assert page.missing_data_stock_codes == ("S0000",)


def test_query_is_fresh_process_reopenable_after_synthetic_database_removal(
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store
    query = _make_query(fixture, sort_key=_RATIO_KEY, page_size=1)
    query_path = Path(fixture["temporary_root"]) / "saved-full-query.json"
    query_path.write_text(query.to_json(), encoding="utf-8")
    assert not Path(fixture["database"]).exists()
    script = (
        "from pathlib import Path; import sys; "
        "from app_module.daily_market_technical_universe_v4_query import "
        "read_daily_market_technical_universe_v4_page; "
        "page=read_daily_market_technical_universe_v4_page(Path(sys.argv[1]).read_bytes()); "
        "print(f'{page.query.receipt_status}:{page.counts.processed_count}:"
        "{page.counts.pending_count}:{page.matching_count}:{page.rows[0].stock_code}')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(query_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert result.stdout.strip() == "complete:257:0:257:S0256"


def test_exact_receipt_missing_corrupt_and_rehashed_source_identity_are_rejected(
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store
    plan = fixture["plan"]
    complete = fixture["complete"]
    query = _make_query(fixture)

    changed_page = query.to_dict()
    changed_page["page_index"] = 1
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError, match="identity_mismatch"):
        DailyMarketTechnicalUniverseV4Query.from_dict(changed_page)

    receipt_path = _receipt_path(fixture, complete.identity_sha256)
    receipt_io_path = to_internal_io_path(receipt_path)
    original_bytes = Path(receipt_io_path).read_bytes()
    try:
        Path(receipt_io_path).unlink()
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError):
            read_daily_market_technical_universe_v4_page(query)
        Path(receipt_io_path).write_bytes(original_bytes)

        Path(receipt_io_path).write_bytes(b'{"schema_version":"corrupt"}')
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError):
            read_daily_market_technical_universe_v4_page(query)
    finally:
        Path(receipt_io_path).write_bytes(original_bytes)

    wrong_version = query.to_dict()
    wrong_version["method_contracts_sha256"] = "f" * 64
    pinned_wrong_version = DailyMarketTechnicalUniverseV4Query.from_dict(
        _resign_query(wrong_version)
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError, match="source_identity_mismatch"):
        read_daily_market_technical_universe_v4_page(pinned_wrong_version)

    wrong_date = query.to_dict()
    wrong_date["decision_date"] = (_DECISION_DATE + timedelta(days=1)).isoformat()
    pinned_wrong_date = DailyMarketTechnicalUniverseV4Query.from_dict(
        _resign_query(wrong_date)
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError, match="source_identity_mismatch"):
        read_daily_market_technical_universe_v4_page(pinned_wrong_date)


def test_cancel_stops_between_real_child_reads_within_full_n_segment(
    synthetic_full_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_full_store
    query = _make_query(fixture, page_size=1)
    original_reader = DailyMarketTechnicalSnapshotV4Repository.read_exact
    child_reads: list[object] = []

    def observed_child_read(self: Any, *args: Any, **kwargs: Any) -> Any:
        child_reads.append(args[0])
        return original_reader(self, *args, **kwargs)

    def reject_bounded_intermediate(*args: Any, **kwargs: Any) -> None:
        pytest.fail("full-N segment loader must not create/read a bounded query")

    def cancel_after_one_verified_child() -> bool:
        return bool(child_reads)

    monkeypatch.setattr(DailyMarketTechnicalSnapshotV4Repository, "read_exact", observed_child_read)
    monkeypatch.setattr(
        parent_query_module.DailyMarketTechnicalParentV4Query,
        "create",
        reject_bounded_intermediate,
    )
    monkeypatch.setattr(
        parent_query_module,
        "read_daily_market_technical_parent_v4_page",
        reject_bounded_intermediate,
    )
    with pytest.raises(
        DailyMarketTechnicalUniverseV4QueryError,
        match="technical_universe_v4_query_cancelled",
    ):
        read_daily_market_technical_universe_v4_page(
            query,
            cancel_callback=cancel_after_one_verified_child,
        )
    assert len(child_reads) == 1


def test_stock_drilldown_binds_origin_page_and_rejects_missing_tampered_or_cancelled(
    synthetic_full_store: dict[str, Any],
) -> None:
    fixture = synthetic_full_store
    query = _make_query(fixture, sort_key="stock_code", page_size=1)
    selected = read_daily_market_technical_universe_v4_stock(query, "S0000")
    assert selected.origin_query == query
    assert selected.segment_index == 0
    assert selected.snapshot.stock_code == "S0000"
    assert selected.snapshot.decision_date == _DECISION_DATE
    assert selected.snapshot.snapshot_identity_sha256
    assert selected.parent_reference.parent_receipt_sha256

    with pytest.raises(
        DailyMarketTechnicalUniverseV4StockError,
        match="technical_universe_v4_stock_not_in_origin_page",
    ):
        read_daily_market_technical_universe_v4_stock(query, "S0001")

    with pytest.raises(
        DailyMarketTechnicalUniverseV4StockError,
        match="technical_universe_v4_stock_cancelled",
    ):
        read_daily_market_technical_universe_v4_stock(
            query,
            "S0000",
            cancel_callback=lambda: True,
        )

    plan = fixture["plan"]
    complete = fixture["complete"]
    state = DailyMarketTechnicalUniverseV4StoreReader(
        fixture["store_output_root"]
    ).read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        complete.identity_sha256,
        expected_receipt_sha256=complete.content_sha256,
        expected_plan_sha256=fixture["plan_sha256"],
    )
    first_index, first_reference = state.segment_parent_references[0]
    parent_package = read_daily_market_technical_parent_capture_v4(
        first_reference.parent_root,
        first_reference.parent_plan_identity_sha256,
        first_reference.parent_receipt_identity_sha256,
        expected_plan_sha256=first_reference.parent_plan_sha256,
        expected_receipt_sha256=first_reference.parent_receipt_sha256,
    )
    assert first_index == 0
    first_child = parent_package["receipt"]["batch_artifacts"][0]
    manifest_path = to_internal_io_path(Path(first_child["manifest_path"]))
    expected_artifact = DailyMarketTechnicalSnapshotV4Repository(
        parent_package["receipt"]["repository_output_root"]
    ).read_exact(
        first_child["manifest_path"],
        expected_manifest_sha256=first_child["manifest_sha256"],
        expected_cohort_identity_sha256=state.plan.segment_cohort(first_index).cohort_identity_sha256,
        expected_source_clock_sha256=query.source_clock_identity_sha256,
        expected_method_contract_sha256=query.method_contracts_sha256,
        expected_decision_date=query.decision_date,
    )
    expected_snapshot = next(
        snapshot for snapshot in expected_artifact.snapshots
        if snapshot.stock_code == "S0000"
    )
    assert selected.parent_reference == first_reference
    assert selected.snapshot == expected_snapshot
    original_manifest = Path(manifest_path).read_bytes()
    try:
        Path(manifest_path).unlink()
        with pytest.raises(ValueError):
            read_daily_market_technical_universe_v4_stock(query, "S0000")
        Path(manifest_path).write_bytes(original_manifest)

        Path(manifest_path).write_bytes(b'{"schema_version":"tampered"}')
        with pytest.raises(ValueError):
            read_daily_market_technical_universe_v4_stock(query, "S0000")
    finally:
        Path(manifest_path).write_bytes(original_manifest)


def test_p01_page_path_render_memo_preserves_lexical_key_and_thread_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("WindowsPath 的大小寫折疊相等語義只在 Windows 驗證")

    original_render = personal_data_paths_module._render_internal_io_path
    rendered_inputs: list[str] = []

    def observed_render(path: str | Path) -> str:
        rendered_inputs.append(str(path))
        return original_render(path)

    monkeypatch.setattr(
        personal_data_paths_module, "_render_internal_io_path", observed_render
    )
    upper = Path("C:/P01-Memo/Case")
    lower = Path("c:/p01-memo/case")
    assert upper.is_absolute() and lower.is_absolute()
    assert upper == lower
    assert str(upper) != str(lower)

    worker_result: list[str] = []
    with personal_data_paths_module._p01_page_operation_path_render_scope():
        memo = personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        upper_rendered = personal_data_paths_module.to_internal_io_path(upper)
        assert personal_data_paths_module.to_internal_io_path(upper) == upper_rendered

        copied_context = copy_context()
        worker = Thread(
            target=lambda: worker_result.append(
                copied_context.run(personal_data_paths_module.to_internal_io_path, upper)
            )
        )
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive()
        assert worker_result == [upper_rendered]

        lower_rendered = personal_data_paths_module.to_internal_io_path(lower)
        assert lower_rendered == original_render(lower)
        assert personal_data_paths_module.to_internal_io_path(lower) == lower_rendered

        # 相對與 tilde Path 不進 memo；strict renderer 仍各自處理或拒絕。
        tilde_path = Path("~/p01-render-probe")
        tilde_expected = original_render(tilde_path)
        assert personal_data_paths_module.to_internal_io_path(tilde_path) == tilde_expected
        assert personal_data_paths_module.to_internal_io_path(tilde_path) == tilde_expected
        relative_path = Path("relative/p01")
        with pytest.raises(ValueError, match="absolute_path_required"):
            personal_data_paths_module.to_internal_io_path(relative_path)

        assert memo._values == {
            (type(upper), str(upper)): upper_rendered,
            (type(lower), str(lower)): lower_rendered,
        }

    assert memo._closed is True
    assert memo._values == {}
    assert rendered_inputs.count(str(upper)) == 2  # 主執行緒與複製 Context 的另一執行緒
    assert rendered_inputs.count(str(lower)) == 1
    assert rendered_inputs.count(str(tilde_path)) == 2
    assert rendered_inputs.count(str(relative_path)) == 1


def test_p01_page_path_render_memo_is_bounded_nested_and_always_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(personal_data_paths_module, "_PAGE_PATH_RENDER_MEMO_MAX_ENTRIES", 1)
    monkeypatch.setattr(
        personal_data_paths_module, "_PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES", 1024
    )
    original_render = personal_data_paths_module._render_internal_io_path
    calls: list[str] = []

    def observed_render(path: str | Path) -> str:
        calls.append(str(path))
        return original_render(path)

    monkeypatch.setattr(
        personal_data_paths_module, "_render_internal_io_path", observed_render
    )
    first = Path.cwd() / "p01-memo-first"
    second = Path.cwd() / "p01-memo-second"
    outer_memo = None
    inner_memo = None
    inner_entry_count = 0
    with personal_data_paths_module._p01_page_operation_path_render_scope():
        outer_memo = personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert outer_memo is not None
        first_rendered = personal_data_paths_module.to_internal_io_path(first)
        assert personal_data_paths_module.to_internal_io_path(first) == first_rendered

        with personal_data_paths_module._p01_page_operation_path_render_scope():
            inner_memo = personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get()
            assert inner_memo is not None and inner_memo is not outer_memo
            assert personal_data_paths_module.to_internal_io_path(first) == first_rendered
            assert personal_data_paths_module.to_internal_io_path(first) == first_rendered
            inner_entry_count = len(inner_memo._values)
        assert personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get() is outer_memo

        for _ in range(2):
            assert personal_data_paths_module.to_internal_io_path(second) == original_render(second)
        assert len(outer_memo._values) == 1
        assert inner_entry_count == 1

    assert outer_memo is not None and outer_memo._closed and outer_memo._values == {}
    assert inner_memo is not None and inner_memo._closed and inner_memo._values == {}
    assert calls.count(str(first)) == 2  # 外層與巢狀 scope 各一次
    assert calls.count(str(second)) == 2  # 滿額後 strict fallback

    monkeypatch.setattr(personal_data_paths_module, "_PAGE_PATH_RENDER_MEMO_MAX_ENTRIES", 8)
    monkeypatch.setattr(personal_data_paths_module, "_PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES", 0)
    calls.clear()
    with personal_data_paths_module._p01_page_operation_path_render_scope():
        for _ in range(2):
            personal_data_paths_module.to_internal_io_path(first)
        active = personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert active is not None and active._values == {}
    assert calls == [str(first), str(first)]


def test_p01_page_read_matches_strict_clone_and_preserves_every_fresh_io_event(
    synthetic_small_full_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_small_read_session(synthetic_small_full_store)
    query = session.create_query(
        rule_state_filters=(
            DailyMarketTechnicalRuleStateFilterV4.create(
                "ma5_20_golden_cross", ("no_match",)
            ),
            DailyMarketTechnicalRuleStateFilterV4.create(
                "volume_ratio_20_including_current", ("unknown",)
            ),
        ),
        combine_mode="OR",
        stock_filter=tuple(f"S{index:04d}" for index in range(17)),
        sort_key=_RATIO_KEY,
        descending=True,
        page_size=4,
    )
    selection = session.select_stock_codes(query)
    assert selection.matching_count > 0
    strict_clone = dataclass_replace(session)

    original_render = personal_data_paths_module._render_internal_io_path
    original_lstat = snapshot_repository_module._lstat_optional
    original_reject = snapshot_repository_module._reject_link_components
    original_read = snapshot_repository_module._read_bounded_file
    phase = ["fast"]
    render_calls: dict[str, list[str]] = {"fast": [], "strict": []}
    io_events: dict[str, list[tuple[str, str]]] = {"fast": [], "strict": []}

    def observed_render(path: str | Path) -> str:
        render_calls[phase[0]].append(str(path))
        return original_render(path)

    def observe(name: str, original: Any) -> Any:
        def wrapped(path: Path, *args: Any, **kwargs: Any) -> Any:
            io_events[phase[0]].append((name, str(path)))
            return original(path, *args, **kwargs)
        return wrapped

    monkeypatch.setattr(personal_data_paths_module, "_render_internal_io_path", observed_render)
    monkeypatch.setattr(snapshot_repository_module, "_lstat_optional", observe("lstat", original_lstat))
    monkeypatch.setattr(
        snapshot_repository_module, "_reject_link_components", observe("reparse", original_reject)
    )
    monkeypatch.setattr(
        snapshot_repository_module, "_read_bounded_file", observe("read", original_read)
    )

    fast_page = session.read_selection_page(selection, page_index=1, page_size=4)
    phase[0] = "strict"
    strict_page = strict_clone.read_selection_page(selection, page_index=1, page_size=4)

    assert fast_page.page is not None and fast_page.page.rows
    assert _read_selection_page_payload(fast_page) == _read_selection_page_payload(
        strict_page
    )
    assert io_events["fast"] == io_events["strict"]
    assert render_calls["fast"]
    assert len(render_calls["fast"]) < len(render_calls["strict"])
    assert personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get() is None


def test_p01_page_cancel_clears_memo_and_callback_strict_reads_do_not_borrow_it(
    synthetic_small_full_store: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = synthetic_small_full_store
    session = _open_small_read_session(fixture)
    query = session.create_query(
        stock_filter=("S0000", "S0001", "S0002", "S0003"),
        sort_key="stock_code",
        page_size=2,
    )
    selection = session.select_stock_codes(query)
    reference = session._artifact_references[0]
    proof = reference.semantic_proof
    assert proof is not None
    strict_repository = DailyMarketTechnicalSnapshotV4Repository(
        reference.repository_output_root
    )
    strict_code = proof.manifest.expected_stock_codes[0]
    original_render = personal_data_paths_module._render_internal_io_path
    render_contexts: list[object | None] = []
    strict_render_contexts: list[object | None] = []
    strict_active = [False]

    def observed_render(path: str | Path) -> str:
        current = personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        render_contexts.append(current)
        if strict_active[0]:
            strict_render_contexts.append(current)
        return original_render(path)

    monkeypatch.setattr(personal_data_paths_module, "_render_internal_io_path", observed_render)
    nested_once = [False]
    callback_contexts: list[object | None] = []
    nested_pages: list[Any] = []

    def reentrant_callback() -> bool:
        callback_contexts.append(personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get())
        if not nested_once[0]:
            nested_once[0] = True
            assert personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get() is None
            strict_active[0] = True
            strict_rows = strict_repository.read_selected_exact(
                proof, selected_stock_codes=(strict_code,)
            )
            strict_active[0] = False
            assert tuple(row.stock_code for row in strict_rows) == (strict_code,)
            nested_pages.append(session.read_selection_page(selection, page_index=1, page_size=2))
            assert personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get() is None
        return False

    outer_page = session.read_selection_page(
        selection,
        page_index=0,
        page_size=2,
        cancel_callback=reentrant_callback,
    )
    assert outer_page.page is not None and outer_page.page.rows
    assert nested_pages and nested_pages[0].page is not None
    assert callback_contexts and all(item is None for item in callback_contexts)
    assert strict_render_contexts and all(item is None for item in strict_render_contexts)
    assert len({id(item) for item in render_contexts if item is not None}) >= 2
    scoped_memos = {id(item): item for item in render_contexts if item is not None}
    assert scoped_memos
    assert all(
        item._closed and item._values == {} and item._components == {}
        for item in scoped_memos.values()
    )
    assert personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get() is None

    memo_type = personal_data_paths_module._PageOperationPathRenderMemo
    created_memos: list[Any] = []

    class TrackedMemo(memo_type):
        __slots__ = ()

        def __init__(self) -> None:
            super().__init__()
            created_memos.append(self)

    monkeypatch.setattr(personal_data_paths_module, "_PageOperationPathRenderMemo", TrackedMemo)
    original_bounded_read = snapshot_repository_module._read_bounded_file
    completed_reads: list[Path] = []

    def observed_bounded_read(path: Path, limit: int) -> bytes:
        raw = original_bounded_read(path, limit)
        completed_reads.append(path)
        return raw

    monkeypatch.setattr(
        snapshot_repository_module, "_read_bounded_file", observed_bounded_read
    )
    cancelled_callback_contexts: list[object | None] = []

    def cancel_after_first_read() -> bool:
        cancelled_callback_contexts.append(
            personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        )
        return bool(completed_reads)

    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as cancellation_error:
        session.read_selection_page(
            selection,
            page_index=0,
            page_size=2,
            cancel_callback=cancel_after_first_read,
        )
    assert cancellation_error.value.code == "technical_universe_v4_query_cancelled"
    assert completed_reads
    assert cancelled_callback_contexts and all(
        item is None for item in cancelled_callback_contexts
    )
    assert len(created_memos) == 1
    assert created_memos[0]._closed is True
    assert created_memos[0]._values == {}
    assert created_memos[0]._components == {}
    assert personal_data_paths_module._PAGE_OPERATION_PATH_RENDER_MEMO.get() is None


@pytest.mark.parametrize("tamper_selected", (True, False), ids=("selected", "unselected-sibling"))
def test_p01_page_rereads_selected_and_unselected_artifact_bytes_after_mtime_restore(
    synthetic_small_full_store: dict[str, Any],
    tamper_selected: bool,
) -> None:
    session = _open_small_read_session(synthetic_small_full_store)
    query = session.create_query(sort_key="stock_code", page_size=1)
    selection = session.select_stock_codes(query)
    original_page = session.read_selection_page(selection, page_index=0, page_size=1)
    assert original_page.page is not None
    assert tuple(row.stock_code for row in original_page.page.rows) == ("S0000",)

    reference = next(
        item for item in session._artifact_references
        if item.semantic_proof is not None
        and "S0000" in item.semantic_proof.manifest.expected_stock_codes
    )
    proof = reference.semantic_proof
    assert proof is not None
    selected_code = "S0000"
    artifact = next(
        item for item in proof.manifest.artifact_refs if item.stock_code == selected_code
    )
    if not tamper_selected:
        artifact = next(
            item for item in proof.manifest.artifact_refs if item.stock_code != selected_code
        )
    artifact_path = proof.manifest.manifest_path.parent.joinpath(
        *PurePosixPath(artifact.relative_path).parts
    )
    assert artifact_path.is_relative_to(synthetic_small_full_store["temporary_root"])
    artifact_io_path = to_internal_io_path(artifact_path)
    original_bytes = Path(artifact_io_path).read_bytes()
    original_stat = os.stat(artifact_io_path)
    tampered = bytes([original_bytes[0] ^ 1]) + original_bytes[1:]
    try:
        Path(artifact_io_path).write_bytes(tampered)
        os.utime(
            artifact_io_path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as error:
            session.read_selection_page(selection, page_index=0, page_size=1)
        assert error.value.code == "technical_snapshot_v4_artifact_sha_mismatch"
    finally:
        Path(artifact_io_path).write_bytes(original_bytes)
        os.utime(
            artifact_io_path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
    assert Path(artifact_io_path).read_bytes() == original_bytes


def test_p01_page_rejects_reparse_component_and_restores_synthetic_tree(
    synthetic_small_full_store: dict[str, Any],
) -> None:
    if os.name != "nt":
        pytest.skip("此負例使用 Windows junction 驗證 reparse attribute")

    fixture = synthetic_small_full_store
    session = _open_small_read_session(fixture)
    query = session.create_query(stock_filter=("S0000",), sort_key="stock_code", page_size=1)
    selection = session.select_stock_codes(query)
    assert selection.matching_count == 1
    reference = next(
        item for item in session._artifact_references
        if item.semantic_proof is not None
        and "S0000" in item.semantic_proof.manifest.expected_stock_codes
    )
    fixture_root = fixture["temporary_root"]
    batch_root = reference.manifest_path.parent
    configured_component_root = Path(fixture["scope"].root).parents[2]
    assert batch_root.is_relative_to(fixture_root)
    assert configured_component_root.parent == fixture_root
    target = fixture_root / "saved-reparse-target"
    assert configured_component_root.is_relative_to(fixture_root)
    assert not target.exists()
    moved = False
    junction_created = False
    try:
        os.rename(
            to_internal_io_path(configured_component_root),
            to_internal_io_path(target),
        )
        moved = True
        result = subprocess.run(
            [
                os.environ.get("COMSPEC", "cmd.exe"),
                "/d",
                "/c",
                "mklink",
                "/J",
                to_internal_io_path(configured_component_root),
                to_internal_io_path(target),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=20,
        )
        if result.returncode != 0:
            pytest.skip(f"隔離 fixture 無法建立 junction：{result.stderr or result.stdout}")
        junction_created = True
        info = os.lstat(to_internal_io_path(configured_component_root))
        assert getattr(info, "st_file_attributes", 0) & 0x400
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as error:
            session.read_selection_page(selection, page_index=0, page_size=1)
        assert error.value.code in {
            "technical_snapshot_v4_link_rejected",
            "technical_snapshot_v4_directory_invalid",
        }
    finally:
        component_io_path = to_internal_io_path(configured_component_root)
        target_io_path = to_internal_io_path(target)
        if junction_created and os.path.lexists(component_io_path):
            os.rmdir(component_io_path)
        if moved and os.path.lexists(target_io_path):
            os.rename(target_io_path, component_io_path)
