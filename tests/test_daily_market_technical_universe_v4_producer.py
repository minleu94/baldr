"""驗證完整技術母體協調器的來源 pin、續跑與新程序唯讀重開。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app_module import daily_market_technical_source
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionError,
    DailyMarketTechnicalUniverseV4ProductionRequest,
    preflight_daily_market_technical_universe_v4,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY,
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4StoreReader,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import (
    read_daily_market_technical_parent_capture_v4,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)
_SOURCE_DATE = _DECISION_DATE - timedelta(days=1)


@pytest.fixture
def isolated_root() -> Any:
    """在忽略追蹤的 QA 輸出建立本測試專用根並保留診斷資料。"""

    base = (Path(__file__).resolve().parents[1] / "output" / "qa" / "fn4").resolve()
    base.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(dir=base))
    yield directory.resolve()


def _write_source(
    path: Path,
    stock_codes: tuple[str, ...],
    *,
    missing_code: str | None = None,
    keep_wal_connection: bool = False,
) -> sqlite3.Connection | None:
    connection = sqlite3.connect(to_internal_io_path(path))
    if keep_wal_connection:
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
        assert journal_mode is not None and str(journal_mode[0]).lower() == "wal"
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows = [
                (
                    _SOURCE_DATE.isoformat(),
                    code,
                    "99",
                    "101",
                    "98",
                    "100",
                    1200,
                )
                for code in stock_codes
                if code != missing_code
            ]
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    except BaseException:
        connection.close()
        raise
    if keep_wal_connection:
        return connection
    connection.close()
    return None


def _scope_and_store_root(
    directory: Path,
    database: Path,
    *,
    name: str = "full-store",
) -> tuple[ResearchCaptureWriteScope, Path]:
    scope = ResearchCaptureWriteScope(directory / "out", database)
    return scope, scope.root / name


def _cohort(
    included: tuple[str, ...],
    *,
    excluded: tuple[str, ...] = (),
    universe_id: str = "synthetic-full-technical-v4",
) -> DailyMarketTechnicalUniverseV4Cohort:
    return DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id=universe_id,
        population_version="fixture-2026-10-06",
        decision_date=_DECISION_DATE,
        raw_stock_codes=(*included, *excluded),
        excluded_stock_codes=excluded,
        exclusion_reasons={code: "合成母體明示排除" for code in excluded},
    )


def _request(
    database: Path,
    cohort: DailyMarketTechnicalUniverseV4Cohort,
    store_root: Path,
    scope: ResearchCaptureWriteScope,
    *,
    cancel_callback: Any = None,
    resume_receipt_identity_sha256: str | None = None,
    expected_resume_receipt_sha256: str | None = None,
    decision_cutoff: datetime | None = None,
) -> DailyMarketTechnicalUniverseV4ProductionRequest:
    return DailyMarketTechnicalUniverseV4ProductionRequest(
        source_database=database,
        cohort=cohort,
        decision_cutoff=(
            decision_cutoff
            if decision_cutoff is not None
            else datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)
        ),
        store_output_root=store_root,
        research_scope=scope,
        cancel_callback=cancel_callback,
        resume_receipt_identity_sha256=resume_receipt_identity_sha256,
        expected_resume_receipt_sha256=expected_resume_receipt_sha256,
    )


def _source_signature(database: Path) -> tuple[tuple[bytes, int] | None, tuple[bytes, int] | None]:
    def signature(path: Path) -> tuple[bytes, int] | None:
        try:
            stat_result = path.stat()
            return path.read_bytes(), stat_result.st_mtime_ns
        except FileNotFoundError:
            return None

    return signature(database), signature(Path(f"{database}-wal"))


def _full_store_receipt_count(store_root: Path, generation_id: str) -> int:
    receipts = (
        store_root
        / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY
        / "generations"
        / generation_id
        / "receipts"
    )
    receipt_path = to_internal_io_path(receipts)
    if not os.path.isdir(receipt_path):
        return 0
    with os.scandir(receipt_path) as entries:
        return sum(
            1
            for entry in entries
            if entry.name.endswith(".json") and entry.is_file(follow_symlinks=False)
        )


def test_real_257_member_full_run_cancels_resumes_and_reopens_in_a_new_process(
    isolated_root: Path,
) -> None:
    included = tuple(f"S{index:04d}" for index in range(257))
    excluded = ("X9999",)
    cohort = _cohort(included, excluded=excluded)
    assert len(cohort.included_stock_codes) == 257
    assert cohort.excluded_stock_codes == excluded
    assert cohort.raw_stock_code_count == 258

    database = isolated_root / "prices.sqlite"
    _write_source(database, included, missing_code=included[0])
    source_before = _source_signature(database)
    scope, store_root = _scope_and_store_root(isolated_root, database)
    request = _request(database, cohort, store_root, scope)

    preflight = preflight_daily_market_technical_universe_v4(request)
    assert [
        (
            len(preflight.plan.segment_cohort(index).included_stock_codes),
            len(preflight.plan.segment_cohort(index).excluded_stock_codes),
        )
        for index in range(len(preflight.plan.segments))
    ] == [(256, 1), (1, 0)]
    assert not store_root.exists()
    assert not preflight.segment_output_root.exists()
    assert source_before == _source_signature(database)

    def cancel_after_first_full_segment() -> bool:
        return _full_store_receipt_count(
            store_root,
            preflight.plan.generation_identity_sha256,
        ) >= 2

    cancelled = produce_daily_market_technical_universe_v4(
        _request(
            database,
            cohort,
            store_root,
            scope,
            cancel_callback=cancel_after_first_full_segment,
        )
    )
    assert cancelled.status == "cancelled"
    assert cancelled.plan is not None and cancelled.receipt is not None
    assert cancelled.receipt.status == "cancelled"
    assert cancelled.completed_segment_indices == (0,)
    assert cancelled.receipt.to_dict()["counts"] == {
        "declared_count": 258,
        "included_count": 257,
        "excluded_count": 1,
        "processed_count": 256,
        "pending_count": 1,
        "missing_data_count": 1,
        "missing_data_pending_count": 1,
    }

    cancelled_state = DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
        cancelled.generation_identity_sha256 or "",
        cancelled.plan_identity_sha256 or "",
        cancelled.receipt_identity_sha256 or "",
        expected_receipt_sha256=cancelled.receipt_content_sha256 or "",
        expected_plan_sha256=cancelled.plan_sha256,
    )
    assert (
        cancelled_state.calculation_identity_sha256
        == preflight.calculation_identity_sha256
    )
    first_parent_reference = cancelled_state.segment_parent_references[0][1]
    first_parent_signature = _source_signature(database)
    completed_parent_before = read_daily_market_technical_parent_capture_v4(
        first_parent_reference.parent_root,
        first_parent_reference.parent_plan_identity_sha256,
        first_parent_reference.parent_receipt_identity_sha256,
        expected_receipt_sha256=first_parent_reference.parent_receipt_sha256,
        expected_plan_sha256=first_parent_reference.parent_plan_sha256,
    )
    assert completed_parent_before["receipt"]["status"] == "complete"

    changed_cohort = _cohort(included, excluded=excluded, universe_id="different-cohort")
    changed_resume = _request(
        database,
        changed_cohort,
        store_root,
        scope,
        resume_receipt_identity_sha256=cancelled.receipt_identity_sha256,
        expected_resume_receipt_sha256=cancelled.receipt_content_sha256,
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4ProductionError):
        preflight_daily_market_technical_universe_v4(changed_resume)
    assert _full_store_receipt_count(
        store_root,
        cancelled.generation_identity_sha256 or "",
    ) == 3

    completed = produce_daily_market_technical_universe_v4(
        _request(
            database,
            cohort,
            store_root,
            scope,
            resume_receipt_identity_sha256=cancelled.receipt_identity_sha256,
            expected_resume_receipt_sha256=cancelled.receipt_content_sha256,
        )
    )
    assert completed.status == "complete"
    assert completed.resumed is True
    assert completed.completed_segment_indices == (0, 1)
    assert completed.receipt is not None and completed.receipt.status == "complete"
    assert completed.receipt.to_dict()["counts"] == {
        "declared_count": 258,
        "included_count": 257,
        "excluded_count": 1,
        "processed_count": 257,
        "pending_count": 0,
        "missing_data_count": 1,
        "missing_data_pending_count": 0,
    }
    assert completed.missing_data_stock_codes == (included[0],)
    assert source_before == _source_signature(database)
    assert first_parent_signature == _source_signature(database)

    verified = DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
        completed.generation_identity_sha256 or "",
        completed.plan_identity_sha256 or "",
        completed.receipt_identity_sha256 or "",
        expected_receipt_sha256=completed.receipt_content_sha256 or "",
        expected_plan_sha256=completed.plan_sha256,
    )
    assert verified.receipt.status == "complete"
    assert verified.counts.processed_count == 257
    assert verified.counts.missing_data_count == 1
    assert verified.missing_data_stock_codes == (included[0],)
    assert verified.plan.to_dict()["source_clock"]["availability_status"] == "unknown"
    assert verified.plan.to_dict()["source_clock"]["historical_pit_eligible"] is False
    assert verified.segment_parent_references[0][1] == first_parent_reference

    script = (
        "from app_module.daily_market_technical_universe_v4_store import "
        "DailyMarketTechnicalUniverseV4StoreReader; import sys; "
        "state=DailyMarketTechnicalUniverseV4StoreReader(sys.argv[1]).read_exact("
        "sys.argv[2],sys.argv[3],sys.argv[4],expected_receipt_sha256=sys.argv[5],"
        "expected_plan_sha256=sys.argv[6]); "
        "print('|'.join((state.receipt.status,str(state.counts.declared_count),"
        "str(state.counts.processed_count),str(state.counts.missing_data_count),"
        "str(len(state.segment_parent_references)))))"
    )
    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(store_root),
            completed.generation_identity_sha256 or "",
            completed.plan_identity_sha256 or "",
            completed.receipt_identity_sha256 or "",
            completed.receipt_content_sha256 or "",
            completed.plan_sha256 or "",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert reopened.stdout.strip() == "complete|258|257|1|2"
    assert source_before == _source_signature(database)


def test_wal_change_after_a_saved_segment_fails_and_cannot_resume_on_new_clock(
    isolated_root: Path,
) -> None:
    included = ("S0001", "S0002")
    excluded = tuple(f"X{index:04d}" for index in range(257))
    cohort = _cohort(included, excluded=excluded, universe_id="wal-change")
    database = isolated_root / "wal-source.sqlite"
    writer_connection = _write_source(
        database,
        included,
        keep_wal_connection=True,
    )
    assert writer_connection is not None
    source_before = _source_signature(database)
    assert source_before[1] is not None
    scope, store_root = _scope_and_store_root(isolated_root, database, name="wal-store")
    request = _request(database, cohort, store_root, scope)
    preflight = preflight_daily_market_technical_universe_v4(request)
    changed = False

    def change_wal_after_first_segment() -> bool:
        nonlocal changed
        if (
            not changed
            and _full_store_receipt_count(
                store_root,
                preflight.plan.generation_identity_sha256,
            )
            >= 2
        ):
            writer_connection.execute(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                (_SOURCE_DATE.isoformat(), "WAL1", "99", "101", "98", "100", 500),
            )
            writer_connection.commit()
            changed = True
        return False

    result = produce_daily_market_technical_universe_v4(
        _request(
            database,
            cohort,
            store_root,
            scope,
            cancel_callback=change_wal_after_first_segment,
        )
    )
    assert changed is True
    assert result.status == "failed"
    assert result.error_code == "technical_universe_v4_source_clock_changed"
    assert result.receipt is not None and result.receipt.status == "failed"
    assert result.completed_segment_indices == (0,)
    assert result.receipt.to_dict()["counts"]["declared_count"] == 259
    assert result.receipt.to_dict()["counts"]["processed_count"] == 2
    source_after = _source_signature(database)
    assert source_after[0] == source_before[0]
    assert source_after[1] != source_before[1]

    with pytest.raises(DailyMarketTechnicalUniverseV4ProductionError):
        preflight_daily_market_technical_universe_v4(
            _request(
                database,
                cohort,
                store_root,
                scope,
                resume_receipt_identity_sha256=result.receipt_identity_sha256,
                expected_resume_receipt_sha256=result.receipt_content_sha256,
            )
        )
    assert _full_store_receipt_count(
        store_root,
        result.generation_identity_sha256 or "",
    ) == result.receipt.to_dict()["sequence"]
    writer_connection.close()


def test_calculation_identity_change_between_segments_is_rejected(
    isolated_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    included = ("S0001", "S0002")
    excluded = tuple(f"X{index:04d}" for index in range(257))
    cohort = _cohort(included, excluded=excluded, universe_id="calculation-change")
    database = isolated_root / "calculation-source.sqlite"
    _write_source(database, included)
    scope, store_root = _scope_and_store_root(
        isolated_root,
        database,
        name="calculation-store",
    )
    preflight = preflight_daily_market_technical_universe_v4(
        _request(database, cohort, store_root, scope)
    )
    original_identity = daily_market_technical_source._calculation_identity
    changed = False

    def change_calculation_identity_after_first_segment() -> bool:
        nonlocal changed
        if (
            not changed
            and _full_store_receipt_count(
                store_root,
                preflight.plan.generation_identity_sha256,
            )
            >= 2
        ):
            monkeypatch.setattr(
                daily_market_technical_source,
                "_calculation_identity",
                lambda: ("f" * 64, "synthetic-version-change", "synthetic-talib"),
            )
            changed = True
        return False

    result = produce_daily_market_technical_universe_v4(
        _request(
            database,
            cohort,
            store_root,
            scope,
            cancel_callback=change_calculation_identity_after_first_segment,
        )
    )
    assert changed is True
    assert result.status == "failed"
    assert result.error_code == "technical_universe_v4_calculation_identity_changed"
    assert result.receipt is not None and result.receipt.status == "failed"
    assert result.completed_segment_indices == (0,)
    assert original_identity()[0] == preflight.calculation_identity_sha256


def test_exclusion_only_has_zero_child_batches_and_empty_population_has_zero_segments(
    isolated_root: Path,
) -> None:
    database = isolated_root / "empty-prices.sqlite"
    _write_source(database, ())
    scope, excluded_store_root = _scope_and_store_root(
        isolated_root,
        database,
        name="excluded-store",
    )
    excluded_cohort = _cohort((), excluded=("X0001",), universe_id="all-excluded")
    excluded = produce_daily_market_technical_universe_v4(
        _request(database, excluded_cohort, excluded_store_root, scope)
    )
    assert excluded.status == "complete", excluded.to_dict()
    assert excluded.completed_segment_indices == (0,)
    assert excluded.receipt is not None and excluded.receipt.status == "complete"
    assert excluded.receipt.to_dict()["counts"] == {
        "declared_count": 1,
        "included_count": 0,
        "excluded_count": 1,
        "processed_count": 0,
        "pending_count": 0,
        "missing_data_count": 0,
        "missing_data_pending_count": 0,
    }
    excluded_summary = excluded.to_dict()
    assert excluded_summary["population_state"] == "all_excluded"
    assert excluded_summary["zero_child_batches"] is True
    assert "parent metadata receipt" in str(excluded_summary["zero_child_batch_note"])
    excluded_state = DailyMarketTechnicalUniverseV4StoreReader(
        excluded_store_root
    ).read_exact(
        excluded.generation_identity_sha256 or "",
        excluded.plan_identity_sha256 or "",
        excluded.receipt_identity_sha256 or "",
        expected_receipt_sha256=excluded.receipt_content_sha256 or "",
        expected_plan_sha256=excluded.plan_sha256,
    )
    excluded_reference = excluded_state.segment_parent_references[0][1]
    excluded_parent = read_daily_market_technical_parent_capture_v4(
        excluded_reference.parent_root,
        excluded_reference.parent_plan_identity_sha256,
        excluded_reference.parent_receipt_identity_sha256,
        expected_receipt_sha256=excluded_reference.parent_receipt_sha256,
        expected_plan_sha256=excluded_reference.parent_plan_sha256,
    )
    assert excluded_parent["receipt"]["status"] == "complete"
    assert excluded_parent["receipt"]["batch_artifacts"] == []
    assert excluded_parent["plan"]["source_stock_evidence"] == []

    empty_store_root = scope.root / "empty-store"
    empty_cohort = _cohort((), universe_id="empty-full-cohort")
    empty = produce_daily_market_technical_universe_v4(
        _request(database, empty_cohort, empty_store_root, scope)
    )
    assert empty.status == "complete"
    assert empty.plan is not None and empty.plan.segments == ()
    assert empty.completed_segment_indices == ()
    assert empty.receipt is not None and empty.receipt.status == "complete"
    assert empty.to_dict()["population_state"] == "empty"
    assert empty.to_dict()["parent_segment_count"] == 0
    assert empty.to_dict()["zero_child_batches"] is True
    assert "沒有 segment、parent 或 child batch" in str(
        empty.to_dict()["zero_child_batch_note"]
    )


def test_original_after_close_cutoff_guard_fails_before_any_output_is_created(
    isolated_root: Path,
) -> None:
    database = isolated_root / "cutoff.sqlite"
    _write_source(database, ("S0001",))
    scope, store_root = _scope_and_store_root(
        isolated_root,
        database,
        name="cutoff-store",
    )
    before = _source_signature(database)
    request = _request(
        database,
        _cohort(("S0001",), universe_id="cutoff-guard"),
        store_root,
        scope,
        decision_cutoff=datetime.combine(
            _DECISION_DATE,
            time(15, 59),
            tzinfo=_TAIPEI,
        ),
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4ProductionError) as error:
        preflight_daily_market_technical_universe_v4(request)
    assert error.value.code == "daily_technical_requires_after_close_cutoff"
    assert not store_root.exists()
    assert not store_root.with_name(f"{store_root.name}_segments").exists()
    assert before == _source_signature(database)
