"""full-N technical v4 store 的真 parent 保存與唯讀重開驗證。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
import hashlib
import importlib
import importlib.util
import inspect
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_parent_v4_producer import (
    produce_daily_market_technical_parent_v4,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_PLAN_SCHEMA,
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4Plan,
    DailyMarketTechnicalUniverseV4Receipt,
    DailyMarketTechnicalUniverseV4StoreError,
    DailyMarketTechnicalUniverseV4StoreReader,
    DailyMarketTechnicalUniverseV4StoreWriter,
    _counts_for,
    _make_receipt,
    _sha256_json,
    _validate_transition,
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


@pytest.fixture
def short_temp() -> Any:
    base = Path(tempfile.gettempdir()).resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix="uv4store-", dir=base)).resolve(strict=True)
    try:
        yield directory
    finally:
        if directory.parent != base:
            raise AssertionError("technical_universe_v4_fixture_path_escape")
        cleanup_path = str(directory)
        if sys.platform == "win32":
            cleanup_path = "\\\\?\\" + cleanup_path
        shutil.rmtree(cleanup_path)


def _long_configured_root(short_temp: Path) -> Path:
    component = "research-root-" + ("x" * 66)
    return short_temp / component / component / component


def _write_source(path: Path, stock_codes: tuple[str, ...], *, missing_code: str | None = None) -> None:
    connection = sqlite3.connect(to_internal_io_path(path))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            for stock_code in stock_codes:
                if stock_code == missing_code:
                    continue
                for offset in range(40):
                    close = 100 + offset
                    day = _START_DATE + timedelta(days=offset)
                    rows.append((
                        day.isoformat(), stock_code, str(close), str(close + 1),
                        str(close - 1), str(close), 1000 + offset,
                    ))
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        connection.close()


def _full_cohort(
    included: tuple[str, ...],
    *,
    excluded: tuple[str, ...] = (),
    duplicate_first: bool = False,
) -> DailyMarketTechnicalUniverseV4Cohort:
    raw_codes = (*included, *excluded)
    if duplicate_first and included:
        raw_codes = (*raw_codes, included[0].lower())
    return DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-full-technical-v4",
        population_version="fixture-2026-10-06",
        decision_date=_DECISION_DATE,
        raw_stock_codes=raw_codes,
        excluded_stock_codes=excluded,
        exclusion_reasons={code: "合成母體明示排除" for code in excluded},
    )


def _segment_cohorts(
    cohort: DailyMarketTechnicalUniverseV4Cohort,
) -> tuple[DailyMarketTechnicalCohortV4, ...]:
    chunk_size = 256
    count = max(
        (len(cohort.included_stock_codes) + chunk_size - 1) // chunk_size,
        (len(cohort.excluded_stock_codes) + chunk_size - 1) // chunk_size,
    )
    reasons = dict(cohort.exclusion_reasons)
    result: list[DailyMarketTechnicalCohortV4] = []
    for index in range(count):
        include_start = min(len(cohort.included_stock_codes), index * chunk_size)
        include_stop = min(len(cohort.included_stock_codes), include_start + chunk_size)
        exclude_start = min(len(cohort.excluded_stock_codes), index * chunk_size)
        exclude_stop = min(len(cohort.excluded_stock_codes), exclude_start + chunk_size)
        excluded = cohort.excluded_stock_codes[exclude_start:exclude_stop]
        result.append(DailyMarketTechnicalCohortV4.create(
            universe_id=cohort.universe_id,
            population_version=cohort.population_version,
            decision_date=cohort.decision_date,
            included_stock_codes=cohort.included_stock_codes[include_start:include_stop],
            excluded_stock_codes=excluded,
            exclusion_reasons={code: reasons[code] for code in excluded},
        ))
    return tuple(result)


def _produce_parents(
    short_temp: Path,
    configured_root: Path,
    database: Path,
    cohorts: tuple[DailyMarketTechnicalCohortV4, ...],
    *,
    segment_offset: int = 0,
) -> tuple[ResearchCaptureWriteScope, tuple[DailyMarketTechnicalUniverseV4ParentReceiptReference, ...], tuple[dict[str, Any], ...]]:
    scope = ResearchCaptureWriteScope(configured_root, database)
    refs: list[DailyMarketTechnicalUniverseV4ParentReceiptReference] = []
    packages: list[dict[str, Any]] = []
    for index, cohort in enumerate(cohorts):
        segment_number = index + segment_offset + 1
        parent_root = scope.root / "parents" / f"segment-{segment_number:06d}"
        child_root = scope.root / "children" / f"segment-{segment_number:06d}"
        result = produce_daily_market_technical_parent_v4(
            source_database=database,
            cohort=cohort,
            decision_cutoff=datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI),
            child_output_root=child_root,
            parent_root=parent_root,
            research_scope=scope,
        )
        assert result.status == "complete", result.error_code
        assert result.plan is not None and result.receipt is not None
        assert result.receipt.status == "complete"
        reference = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
            parent_root,
            parent_plan_identity_sha256=result.plan.identity_sha256,
            parent_plan_sha256=result.plan.content_sha256,
            parent_receipt_identity_sha256=result.receipt.identity_sha256,
            parent_receipt_sha256=result.receipt.content_sha256,
        )
        refs.append(reference)
        packages.append({"plan": result.plan.to_dict(), "receipt": result.receipt.to_dict()})
    return scope, tuple(refs), tuple(packages)


@contextmanager
def _alternate_kernel_source(short_temp: Path) -> Any:
    """以隔離副本載入同一計算程式，僅加註來源註解以形成不同 kernel SHA。"""

    module_name = "analysis_module.technical_analysis.technical_indicators"
    package_name = "analysis_module.technical_analysis"
    package = importlib.import_module(package_name)
    original_module = importlib.import_module(module_name)
    original_attribute = getattr(package, "technical_indicators", original_module)
    source_path = Path(inspect.getfile(original_module.calculate_causal_indicators))
    alternate_directory = short_temp / "alternate-kernel-source"
    alternate_directory.mkdir()
    alternate_path = alternate_directory / source_path.name
    shutil.copy2(source_path, alternate_path)
    shutil.copy2(source_path.with_name("indicator_kernels.py"), alternate_directory / "indicator_kernels.py")
    with open(alternate_path, "a", encoding="utf-8") as handle:
        handle.write("\n# 隔離測試：不同來源版本，計算程式內容保持相同。\n")

    spec = importlib.util.spec_from_file_location(module_name, alternate_path)
    if spec is None or spec.loader is None:
        raise AssertionError("alternate_kernel_module_spec_missing")
    alternate_module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = alternate_module
    setattr(package, "technical_indicators", alternate_module)
    try:
        spec.loader.exec_module(alternate_module)
        if Path(inspect.getfile(alternate_module.calculate_causal_indicators)) != alternate_path:
            raise AssertionError("alternate_kernel_source_not_loaded")
        yield
    finally:
        sys.modules[module_name] = original_module
        setattr(package, "technical_indicators", original_attribute)


def _expected_plan_sha(plan: DailyMarketTechnicalUniverseV4Plan) -> str:
    return hashlib.sha256(plan.to_json().encode("utf-8")).hexdigest()


def _append_receipt_bytes(
    store_root: Path,
    plan: DailyMarketTechnicalUniverseV4Plan,
    receipt: DailyMarketTechnicalUniverseV4Receipt,
) -> None:
    receipt_path = (
        store_root
        / "daily_market_technical_universe_v4"
        / "generations"
        / plan.generation_identity_sha256
        / "receipts"
        / f"{receipt.identity_sha256}.json"
    )
    with open(to_internal_io_path(receipt_path), "xb") as handle:
        handle.write(receipt.to_json().encode("utf-8"))


def _receipt_directory_bytes(store_root: Path, plan: DailyMarketTechnicalUniverseV4Plan) -> tuple[tuple[str, bytes], ...]:
    receipt_root = (
        store_root
        / "daily_market_technical_universe_v4"
        / "generations"
        / plan.generation_identity_sha256
        / "receipts"
    )
    result: list[tuple[str, bytes]] = []
    with os.scandir(to_internal_io_path(receipt_root)) as entries:
        for entry in entries:
            if entry.name.endswith(".json"):
                with open(entry.path, "rb") as handle:
                    result.append((entry.name, handle.read()))
    return tuple(sorted(result))


def test_real_257_included_parent_segments_roundtrip_cancel_resume_missing_and_fresh_process(
    short_temp: Path,
) -> None:
    included = tuple(f"S{index:04d}" for index in range(257))
    excluded = ("X9999",)
    cohort = _full_cohort(included, excluded=excluded, duplicate_first=True)
    assert len(cohort.included_stock_codes) == 257
    assert cohort.excluded_stock_codes == excluded
    assert cohort.raw_stock_code_count == 259
    assert cohort.duplicate_stock_codes == ((included[0], 2),)

    database = short_temp / "full-n-source.sqlite"
    _write_source(database, (*included, *excluded), missing_code=included[0])
    configured_root = _long_configured_root(short_temp)
    assert len(str(configured_root / "research_snapshots" / "full-store" / "daily_market_technical_universe_v4")) > 260
    scope, parent_refs, parent_packages = _produce_parents(
        short_temp,
        configured_root,
        database,
        _segment_cohorts(cohort),
    )
    source_clock_payload = parent_packages[0]["plan"]["source_clock"]
    assert all(package["plan"]["source_clock"] == source_clock_payload for package in parent_packages)
    source_clock = daily_market_technical_source_clock_v4_from_dict(source_clock_payload)
    plan = DailyMarketTechnicalUniverseV4Plan.build(cohort, source_clock=source_clock)
    assert [
        (
            len(plan.segment_cohort(index).included_stock_codes),
            len(plan.segment_cohort(index).excluded_stock_codes),
        )
        for index in range(len(plan.segments))
    ] == [(256, 1), (1, 0)]
    assert [item.cohort_identity_sha256 for item in plan.segments] == [
        parent["plan"]["cohort"]["cohort_identity_sha256"] for parent in parent_packages
    ]

    store_root = scope.root / "full-store"
    writer = DailyMarketTechnicalUniverseV4StoreWriter(store_root, research_scope=scope)
    first = writer.start(plan)
    plan_sha = _expected_plan_sha(plan)
    state = writer.read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        first.identity_sha256,
        expected_receipt_sha256=first.content_sha256,
        expected_plan_sha256=plan_sha,
    )
    assert state.receipt.status == "partial"
    assert state.counts.to_dict() == {
        "declared_count": 258,
        "included_count": 257,
        "excluded_count": 1,
        "processed_count": 0,
        "pending_count": 257,
        "missing_data_count": 0,
        "missing_data_pending_count": 257,
    }

    first_progress = writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        first.identity_sha256,
        expected_previous_receipt_sha256=first.content_sha256,
        segment_index=0,
        parent_reference=parent_refs[0],
    )
    assert first_progress.status == "partial"
    assert first_progress.to_dict()["counts"]["processed_count"] == 256
    assert first_progress.to_dict()["counts"]["missing_data_count"] == 1
    cancelled = writer.mark_terminal(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        first_progress.identity_sha256,
        expected_previous_receipt_sha256=first_progress.content_sha256,
        status="cancelled",
        error_code="fixture_cancelled_after_first_segment",
    )
    assert cancelled.status == "cancelled"
    cancelled_state = writer.read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        cancelled.identity_sha256,
        expected_receipt_sha256=cancelled.content_sha256,
        expected_plan_sha256=plan_sha,
    )
    assert cancelled_state.counts.pending_count == 1
    assert cancelled_state.counts.missing_data_pending_count == 1

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
        parent_reference=parent_refs[1],
    )
    complete = writer.complete(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        second_progress.identity_sha256,
        expected_previous_receipt_sha256=second_progress.content_sha256,
    )
    assert complete.status == "complete"
    assert complete.to_dict()["counts"] == {
        "declared_count": 258,
        "included_count": 257,
        "excluded_count": 1,
        "processed_count": 257,
        "pending_count": 0,
        "missing_data_count": 1,
        "missing_data_pending_count": 0,
    }

    # full-store 與 parent exact readers 都只核保存時的 pins；來源 DB 不必存在。
    database.unlink()
    verified = DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        complete.identity_sha256,
        expected_receipt_sha256=complete.content_sha256,
        expected_plan_sha256=plan_sha,
    )
    assert verified.receipt.status == "complete"
    assert verified.missing_data_stock_codes == (included[0],)
    assert len(verified.segment_parent_references) == 2

    script = (
        "from app_module.daily_market_technical_universe_v4_store import "
        "DailyMarketTechnicalUniverseV4StoreReader; import sys; "
        "s=DailyMarketTechnicalUniverseV4StoreReader(sys.argv[1]).read_exact("
        "sys.argv[2],sys.argv[3],sys.argv[4],expected_receipt_sha256=sys.argv[5],"
        "expected_plan_sha256=sys.argv[6]); "
        "print(s.receipt.status+':'+str(s.counts.processed_count)+':'+str(s.counts.missing_data_count))"
    )
    reopened = subprocess.run(
        [
            sys.executable, "-c", script, str(store_root),
            plan.generation_identity_sha256, plan.identity_sha256,
            complete.identity_sha256, complete.content_sha256, plan_sha,
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert reopened.stdout.strip() == "complete:257:1"

    reader = DailyMarketTechnicalUniverseV4StoreReader(store_root)
    future_parent_root = Path(parent_refs[1].parent_root)
    future_child_root = scope.root / "children" / "segment-000002"

    def assert_old_pin_survives_missing_future_artifact(
        artifact_root: Path,
        *,
        expected_complete_error: str,
    ) -> None:
        hidden_root = artifact_root.with_name(artifact_root.name + ".history-pin-hidden")
        os.replace(
            to_internal_io_path(artifact_root),
            to_internal_io_path(hidden_root),
        )
        try:
            old_pins = (
                (first_progress, first_progress.to_dict()["counts"]),
                (cancelled, cancelled_state.counts.to_dict()),
            )
            for old_pin, expected_counts in old_pins:
                old_state = reader.read_exact(
                    plan.generation_identity_sha256,
                    plan.identity_sha256,
                    old_pin.identity_sha256,
                    expected_receipt_sha256=old_pin.content_sha256,
                    expected_plan_sha256=plan_sha,
                )
                assert old_state.receipt.status == old_pin.status
                assert old_state.counts.to_dict() == expected_counts
                assert old_state.segment_parent_references == ((0, parent_refs[0]),)
            with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as incomplete_future:
                reader.read_exact(
                    plan.generation_identity_sha256,
                    plan.identity_sha256,
                    complete.identity_sha256,
                    expected_receipt_sha256=complete.content_sha256,
                    expected_plan_sha256=plan_sha,
                )
            assert incomplete_future.value.code == expected_complete_error
        finally:
            os.replace(
                to_internal_io_path(hidden_root),
                to_internal_io_path(artifact_root),
            )

    assert_old_pin_survives_missing_future_artifact(
        future_child_root,
        expected_complete_error="technical_universe_v4_technical_snapshot_v4_repository_root_missing",
    )
    assert_old_pin_survives_missing_future_artifact(
        future_parent_root,
        expected_complete_error="technical_universe_v4_technical_universe_v4_parent_reference_invalid",
    )

    plan_path = store_root / "daily_market_technical_universe_v4" / "generations" / plan.generation_identity_sha256 / "plan.json"
    with open(to_internal_io_path(plan_path), "ab") as handle:
        handle.write(b" ")
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError):
        DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            complete.identity_sha256,
            expected_receipt_sha256=complete.content_sha256,
        )


def test_exclusion_only_parent_is_required_and_empty_full_cohort_is_truthful(
    short_temp: Path,
) -> None:
    database = short_temp / "empty-source.sqlite"
    _write_source(database, ())
    excluded_cohort = _full_cohort((), excluded=("X0001",))
    configured_root = _long_configured_root(short_temp)
    scope, references, packages = _produce_parents(
        short_temp,
        configured_root,
        database,
        _segment_cohorts(excluded_cohort),
    )
    source_clock = daily_market_technical_source_clock_v4_from_dict(packages[0]["plan"]["source_clock"])
    plan = DailyMarketTechnicalUniverseV4Plan.build(excluded_cohort, source_clock=source_clock)
    assert len(plan.segments) == 1
    assert plan.segment_cohort(0).included_stock_codes == ()
    assert plan.segment_cohort(0).excluded_stock_codes == ("X0001",)
    assert packages[0]["receipt"]["status"] == "complete"
    assert packages[0]["receipt"]["batch_artifacts"] == []

    writer = DailyMarketTechnicalUniverseV4StoreWriter(scope.root / "excluded-store", research_scope=scope)
    start = writer.start(plan)
    progress = writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        start.identity_sha256,
        expected_previous_receipt_sha256=start.content_sha256,
        segment_index=0,
        parent_reference=references[0],
    )
    completed = writer.complete(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        progress.identity_sha256,
        expected_previous_receipt_sha256=progress.content_sha256,
    )
    state = writer.read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        completed.identity_sha256,
        expected_receipt_sha256=completed.content_sha256,
    )
    assert state.receipt.status == "complete"
    assert state.counts.to_dict() == {
        "declared_count": 1,
        "included_count": 0,
        "excluded_count": 1,
        "processed_count": 0,
        "pending_count": 0,
        "missing_data_count": 0,
        "missing_data_pending_count": 0,
    }

    empty_cohort = _full_cohort(())
    empty_plan = DailyMarketTechnicalUniverseV4Plan.build(empty_cohort, source_clock=source_clock)
    assert empty_plan.segments == ()
    empty_writer = DailyMarketTechnicalUniverseV4StoreWriter(scope.root / "empty-store", research_scope=scope)
    initial = empty_writer.start(empty_plan)
    empty_complete = empty_writer.complete(
        empty_plan.generation_identity_sha256,
        empty_plan.identity_sha256,
        initial.identity_sha256,
        expected_previous_receipt_sha256=initial.content_sha256,
    )
    assert empty_complete.status == "complete"
    assert empty_complete.to_dict()["counts"] == {
        "declared_count": 0,
        "included_count": 0,
        "excluded_count": 0,
        "processed_count": 0,
        "pending_count": 0,
        "missing_data_count": 0,
        "missing_data_pending_count": 0,
    }


def test_exact_history_pins_keep_their_prefix_and_reject_future_forks(
    short_temp: Path,
) -> None:
    included = ("H0001",)
    cohort = _full_cohort(included)
    database = short_temp / "history-source.sqlite"
    _write_source(database, included)
    configured_root = _long_configured_root(short_temp)
    scope, parent_refs, parent_packages = _produce_parents(
        short_temp,
        configured_root,
        database,
        _segment_cohorts(cohort),
    )
    source_clock = daily_market_technical_source_clock_v4_from_dict(
        parent_packages[0]["plan"]["source_clock"]
    )
    plan = DailyMarketTechnicalUniverseV4Plan.build(
        cohort,
        source_clock=source_clock,
    )
    plan_sha = _expected_plan_sha(plan)

    store_root = scope.root / "history-store"
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
        parent_reference=parent_refs[0],
    )
    cancelled = writer.mark_terminal(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        progress.identity_sha256,
        expected_previous_receipt_sha256=progress.content_sha256,
        status="cancelled",
        error_code="fixture_cancelled_after_parent",
    )
    cancelled_before_resume = DailyMarketTechnicalUniverseV4StoreReader(
        store_root
    ).read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        cancelled.identity_sha256,
        expected_receipt_sha256=cancelled.content_sha256,
        expected_plan_sha256=plan_sha,
    )
    assert cancelled_before_resume.receipt.status == "cancelled"
    assert cancelled_before_resume.counts.processed_count == 1
    assert len(cancelled_before_resume.segment_parent_references) == 1

    resumed = writer.resume(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        cancelled.identity_sha256,
        expected_previous_receipt_sha256=cancelled.content_sha256,
    )
    complete = writer.complete(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        resumed.identity_sha256,
        expected_previous_receipt_sha256=resumed.content_sha256,
    )
    assert complete.status == "complete"

    expected_pins = (
        (initial, "partial", 0, ()),
        (progress, "partial", 1, ((0, parent_refs[0]),)),
        (cancelled, "cancelled", 1, ((0, parent_refs[0]),)),
        (resumed, "partial", 1, ((0, parent_refs[0]),)),
        (complete, "complete", 1, ((0, parent_refs[0]),)),
    )
    for pin, status, processed, references in expected_pins:
        state = DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            pin.identity_sha256,
            expected_receipt_sha256=pin.content_sha256,
            expected_plan_sha256=plan_sha,
        )
        assert state.receipt.status == status
        assert state.counts.processed_count == processed
        assert state.counts.pending_count == 1 - processed
        assert state.segment_parent_references == references

    original_bytes = _receipt_directory_bytes(store_root, plan)
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as stale_resume:
        writer.resume(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            cancelled.identity_sha256,
            expected_previous_receipt_sha256=cancelled.content_sha256,
        )
    assert stale_resume.value.code == "technical_universe_v4_append_previous_receipt_not_history_head"
    assert _receipt_directory_bytes(store_root, plan) == original_bytes
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as stale_record:
        writer.record_segment_parent(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            progress.identity_sha256,
            expected_previous_receipt_sha256=progress.content_sha256,
            segment_index=0,
            parent_reference=parent_refs[0],
        )
    assert stale_record.value.code == "technical_universe_v4_append_previous_receipt_not_history_head"
    assert _receipt_directory_bytes(store_root, plan) == original_bytes

    fork_store_root = scope.root / "fork-store"
    fork_writer = DailyMarketTechnicalUniverseV4StoreWriter(
        fork_store_root,
        research_scope=scope,
    )
    fork_initial = fork_writer.start(plan)
    fork_progress = fork_writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        fork_initial.identity_sha256,
        expected_previous_receipt_sha256=fork_initial.content_sha256,
        segment_index=0,
        parent_reference=parent_refs[0],
    )
    fork_cancelled = fork_writer.mark_terminal(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        fork_progress.identity_sha256,
        expected_previous_receipt_sha256=fork_progress.content_sha256,
        status="cancelled",
        error_code="first_legal_future_branch",
    )
    alternate_branch = _make_receipt(
        plan=plan,
        sequence=fork_cancelled.to_dict()["sequence"],
        previous=fork_progress,
        status="failed",
        counts=_counts_for(plan, ((0, parent_refs[0]),), ()),
        last_parent_reference=parent_refs[0],
        error_code="second_legal_future_branch",
    )
    _validate_transition(fork_progress.to_dict(), alternate_branch.to_dict())
    assert alternate_branch.identity_sha256 != fork_cancelled.identity_sha256
    _append_receipt_bytes(fork_store_root, plan, alternate_branch)
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as fork_error:
        DailyMarketTechnicalUniverseV4StoreReader(fork_store_root).read_exact(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            fork_progress.identity_sha256,
            expected_receipt_sha256=fork_progress.content_sha256,
            expected_plan_sha256=plan_sha,
        )
    assert fork_error.value.code == "technical_universe_v4_receipt_history_fork_or_orphan"

    wrong_link_store_root = scope.root / "wrong-link-store"
    wrong_link_writer = DailyMarketTechnicalUniverseV4StoreWriter(
        wrong_link_store_root,
        research_scope=scope,
    )
    wrong_link_initial = wrong_link_writer.start(plan)
    legal_future = _make_receipt(
        plan=plan,
        sequence=2,
        previous=wrong_link_initial,
        status="cancelled",
        counts=_counts_for(plan, (), ()),
        error_code="fixture_future_cancelled",
    )
    wrong_link_payload = legal_future.to_dict()
    wrong_link_payload["previous_receipt_sha256"] = (
        "0" * 64
        if wrong_link_initial.content_sha256 != "0" * 64
        else "1" * 64
    )
    wrong_link_payload.pop("receipt_identity_sha256")
    wrong_link_payload["receipt_identity_sha256"] = _sha256_json(wrong_link_payload)
    wrong_link = DailyMarketTechnicalUniverseV4Receipt.from_dict(wrong_link_payload)
    assert wrong_link.identity_sha256 != legal_future.identity_sha256
    _append_receipt_bytes(wrong_link_store_root, plan, wrong_link)
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as link_error:
        DailyMarketTechnicalUniverseV4StoreReader(wrong_link_store_root).read_exact(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            wrong_link_initial.identity_sha256,
            expected_receipt_sha256=wrong_link_initial.content_sha256,
            expected_plan_sha256=plan_sha,
        )
    assert link_error.value.code == "technical_universe_v4_previous_receipt_sha_mismatch"


def test_rejects_parent_root_and_source_clock_mismatch_without_mutating_progress(
    short_temp: Path,
) -> None:
    codes = ("S0001",)
    database_one = short_temp / "source-one.sqlite"
    database_two = short_temp / "source-two.sqlite"
    _write_source(database_one, codes)
    _write_source(database_two, codes)
    configured_one = _long_configured_root(short_temp) / "one"
    scope_one, refs_one, packages_one = _produce_parents(
        short_temp, configured_one, database_one, (_segment_cohorts(_full_cohort(codes))[0],)
    )
    configured_two = _long_configured_root(short_temp) / "two"
    scope_two, refs_two, packages_two = _produce_parents(
        short_temp, configured_two, database_two, (_segment_cohorts(_full_cohort(codes))[0],)
    )
    assert scope_one.root != scope_two.root
    full_cohort = _full_cohort(codes)
    source_clock = daily_market_technical_source_clock_v4_from_dict(packages_one[0]["plan"]["source_clock"])
    plan = DailyMarketTechnicalUniverseV4Plan.build(full_cohort, source_clock=source_clock)
    writer = DailyMarketTechnicalUniverseV4StoreWriter(scope_one.root / "mismatch-store", research_scope=scope_one)
    initial = writer.start(plan)

    wrong_root = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
        scope_one.root / "children" / "segment-000001",
        parent_plan_identity_sha256=refs_one[0].parent_plan_identity_sha256,
        parent_plan_sha256=refs_one[0].parent_plan_sha256,
        parent_receipt_identity_sha256=refs_one[0].parent_receipt_identity_sha256,
        parent_receipt_sha256=refs_one[0].parent_receipt_sha256,
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError):
        writer.record_segment_parent(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            initial.identity_sha256,
            expected_previous_receipt_sha256=initial.content_sha256,
            segment_index=0,
            parent_reference=wrong_root,
        )

    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError, match="parent_source_clock_mismatch"):
        writer.record_segment_parent(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            initial.identity_sha256,
            expected_previous_receipt_sha256=initial.content_sha256,
            segment_index=0,
            parent_reference=refs_two[0],
        )

    # 被拒的來源/根引用沒有前進收據；真正同時計 parent 仍可按原 pin 保存。
    accepted = writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        initial.identity_sha256,
        expected_previous_receipt_sha256=initial.content_sha256,
        segment_index=0,
        parent_reference=refs_one[0],
    )
    complete = writer.complete(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        accepted.identity_sha256,
        expected_previous_receipt_sha256=accepted.content_sha256,
    )
    assert complete.status == "complete"


def test_full_store_rejects_mixed_calculation_identity_across_real_parent_segments(
    short_temp: Path,
) -> None:
    included = tuple(f"C{index:04d}" for index in range(257))
    cohort = _full_cohort(included)
    database = short_temp / "calculation-identity-source.sqlite"
    # 空資料仍產生真實來源窗口和計算身份，同時避免測試用大量重複指標計算。
    _write_source(database, ())
    configured_root = _long_configured_root(short_temp)
    segment_cohorts = _segment_cohorts(cohort)
    scope, first_refs, first_packages = _produce_parents(
        short_temp, configured_root, database, segment_cohorts[:1]
    )
    with _alternate_kernel_source(short_temp):
        _scope_second, second_refs, second_packages = _produce_parents(
            short_temp,
            configured_root,
            database,
            segment_cohorts[1:],
            segment_offset=1,
        )

    references = (*first_refs, *second_refs)
    packages = (*first_packages, *second_packages)
    assert len(references) == 2
    assert packages[0]["plan"]["source_clock"] == packages[1]["plan"]["source_clock"]
    first_calculation_identity = packages[0]["plan"]["source_stock_evidence"][0]["calculation_identity_sha256"]
    second_calculation_identity = packages[1]["plan"]["source_stock_evidence"][0]["calculation_identity_sha256"]
    assert first_calculation_identity != second_calculation_identity

    source_clock = daily_market_technical_source_clock_v4_from_dict(packages[0]["plan"]["source_clock"])
    plan = DailyMarketTechnicalUniverseV4Plan.build(cohort, source_clock=source_clock)
    store_root = scope.root / "calculation-identity-store"
    writer = DailyMarketTechnicalUniverseV4StoreWriter(store_root, research_scope=scope)
    initial = writer.start(plan)
    first_progress = writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        initial.identity_sha256,
        expected_previous_receipt_sha256=initial.content_sha256,
        segment_index=0,
        parent_reference=references[0],
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as writer_error:
        writer.record_segment_parent(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            first_progress.identity_sha256,
            expected_previous_receipt_sha256=first_progress.content_sha256,
            segment_index=1,
            parent_reference=references[1],
        )
    assert writer_error.value.code == "technical_universe_v4_parent_calculation_identity_mismatch"
    unchanged = writer.read_exact(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        first_progress.identity_sha256,
        expected_receipt_sha256=first_progress.content_sha256,
    )
    assert len(unchanged.segment_parent_references) == 1
    assert unchanged.calculation_identity_sha256 == first_calculation_identity

    # 架出 hash/link 全合法、但跨段計算身份不一致的 append receipt，證明唯讀 reader 自己拒絕。
    reader_store_root = scope.root / "calculation-identity-reader-store"
    reader_writer = DailyMarketTechnicalUniverseV4StoreWriter(reader_store_root, research_scope=scope)
    reader_initial = reader_writer.start(plan)
    reader_first = reader_writer.record_segment_parent(
        plan.generation_identity_sha256,
        plan.identity_sha256,
        reader_initial.identity_sha256,
        expected_previous_receipt_sha256=reader_initial.content_sha256,
        segment_index=0,
        parent_reference=references[0],
    )
    all_missing = tuple(included)
    bad_counts = _counts_for(
        plan,
        ((0, references[0]), (1, references[1])),
        all_missing,
    )
    invalid_receipt = _make_receipt(
        plan=plan,
        sequence=3,
        previous=reader_first,
        status="partial",
        counts=bad_counts,
        segment_index=1,
        parent_reference=references[1],
        last_parent_reference=references[1],
    )
    receipt_path = (
        reader_store_root
        / "daily_market_technical_universe_v4"
        / "generations"
        / plan.generation_identity_sha256
        / "receipts"
        / f"{invalid_receipt.identity_sha256}.json"
    )
    with open(to_internal_io_path(receipt_path), "xb") as handle:
        handle.write(invalid_receipt.to_json().encode("utf-8"))
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as reader_error:
        DailyMarketTechnicalUniverseV4StoreReader(reader_store_root).read_exact(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            invalid_receipt.identity_sha256,
            expected_receipt_sha256=invalid_receipt.content_sha256,
            expected_plan_sha256=_expected_plan_sha(plan),
        )
    assert reader_error.value.code == "technical_universe_v4_parent_calculation_identity_mismatch"


def test_full_plan_rejects_changed_method_contract_and_json_float_or_duplicate_keys(
    short_temp: Path,
) -> None:
    database = short_temp / "method-source.sqlite"
    _write_source(database, ("S0001",))
    configured_root = _long_configured_root(short_temp)
    _scope, _references, packages = _produce_parents(
        short_temp,
        configured_root,
        database,
        (_segment_cohorts(_full_cohort(("S0001",)))[0],),
    )
    source_clock = daily_market_technical_source_clock_v4_from_dict(packages[0]["plan"]["source_clock"])
    plan = DailyMarketTechnicalUniverseV4Plan.build(_full_cohort(("S0001",)), source_clock=source_clock)
    payload = plan.to_dict()
    payload["method_contracts"]["contract_version"] = "unsupported-method"
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError, match="method_contract_invalid"):
        DailyMarketTechnicalUniverseV4Plan.from_dict(payload)
    assert payload["schema_version"] == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_PLAN_SCHEMA

    duplicate_key_json = b'{"schema_version":"x","schema_version":"y"}'
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError, match="duplicate_json_key"):
        DailyMarketTechnicalUniverseV4Plan.from_json(duplicate_key_json)
    float_json = b'{"value":1.5}'
    with pytest.raises(DailyMarketTechnicalUniverseV4StoreError) as float_error:
        DailyMarketTechnicalUniverseV4Plan.from_json(float_json)
    assert float_error.value.code == "technical_universe_v4_float_forbidden"
