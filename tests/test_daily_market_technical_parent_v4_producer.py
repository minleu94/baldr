"""驗證 v4 parent orchestration 的真實來源、子批產製與明示續跑。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
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
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalCohortV4,
    read_daily_market_technical_parent_capture_v4,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)
_START_DATE = _DECISION_DATE - timedelta(days=39)


@pytest.fixture
def short_temp() -> Any:
    base = Path(tempfile.gettempdir()).resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix="orv4-", dir=base)).resolve(strict=True)
    try:
        yield directory
    finally:
        if directory.parent != base:
            raise AssertionError("parent_v4_producer_fixture_path_escape")
        cleanup_path = str(directory)
        if sys.platform == "win32":
            cleanup_path = "\\\\?\\" + cleanup_path
        shutil.rmtree(cleanup_path)


def _write_source(path: Path, stock_codes: tuple[str, ...]) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            for stock_code in stock_codes:
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


def _scope_roots(
    directory: Path,
    database: Path,
) -> tuple[ResearchCaptureWriteScope, Path, Path]:
    scope = ResearchCaptureWriteScope(directory / "configured", database)
    return scope, scope.root / "parent", scope.root / "children"


def _cohort(
    included: tuple[str, ...],
    *,
    excluded: tuple[str, ...] = (),
) -> DailyMarketTechnicalCohortV4:
    return DailyMarketTechnicalCohortV4.create(
        universe_id="synthetic-parent-producer-v4",
        population_version="fixture-2026-10-06",
        decision_date=_DECISION_DATE,
        included_stock_codes=included,
        excluded_stock_codes=excluded,
        exclusion_reasons={code: "合成母體明示排除" for code in excluded},
    )


def _cutoff() -> datetime:
    return datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)


def _receipt_count(parent_root: Path) -> int:
    store = parent_root / "technical_parents_v4" / "plans"
    if not store.exists():
        return 0
    return sum(len(list(path.glob("*.json"))) for path in store.glob("*/receipts"))


def test_real_17_stock_orchestration_cancels_then_explicitly_resumes_and_reopens(
    short_temp: Path,
) -> None:
    codes = tuple(f"S{index:04d}" for index in range(17))
    database = short_temp / "prices.sqlite"
    _write_source(database, codes)
    source_before = database.read_bytes()
    scope, parent_root, child_root = _scope_roots(short_temp, database)

    def cancel_after_first_batch_receipt() -> bool:
        return _receipt_count(parent_root) >= 2

    cancelled = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=_cohort(codes),
        decision_cutoff=_cutoff(),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope,
        cancel_callback=cancel_after_first_batch_receipt,
    )
    assert cancelled.status == "cancelled"
    assert cancelled.plan is not None and cancelled.receipt is not None
    assert cancelled.receipt.status == "cancelled"
    assert [len(batch["expected_stock_codes"]) for batch in cancelled.plan.to_dict()["batches"]] == [16, 1]
    assert [item["batch_id"] for item in cancelled.receipt.to_dict()["batch_artifacts"]] == ["batch-01"]

    completed = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=_cohort(codes),
        decision_cutoff=_cutoff(),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope,
        resume_receipt_identity_sha256=cancelled.receipt_identity_sha256,
        expected_resume_receipt_sha256=cancelled.receipt_content_sha256,
    )
    assert completed.status == "complete"
    assert completed.resumed is True
    assert completed.plan_identity_sha256 == cancelled.plan_identity_sha256
    assert completed.receipt is not None and completed.receipt.status == "complete"
    children = completed.receipt.to_dict()["batch_artifacts"]
    assert [item["batch_id"] for item in children] == ["batch-01", "batch-02"]
    assert [len(item["expected_stock_codes"]) for item in children] == [16, 1]
    assert database.read_bytes() == source_before

    database.unlink()
    package = read_daily_market_technical_parent_capture_v4(
        parent_root,
        completed.plan_identity_sha256 or "",
        completed.receipt_identity_sha256 or "",
        expected_receipt_sha256=completed.receipt_content_sha256 or "",
    )
    assert package["receipt"]["status"] == "complete"
    script = (
        "from app_module.rule_research_technical_parent_capture_v4 import "
        "read_daily_market_technical_parent_capture_v4; import sys; "
        "p=read_daily_market_technical_parent_capture_v4(sys.argv[1],sys.argv[2],sys.argv[3],"
        "expected_receipt_sha256=sys.argv[4]); print(p['receipt']['status'])"
    )
    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(parent_root),
            completed.plan_identity_sha256 or "",
            completed.receipt_identity_sha256 or "",
            completed.receipt_content_sha256 or "",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert reopened.stdout.strip() == "complete"


def test_all_excluded_writes_explicit_empty_child_completion(short_temp: Path) -> None:
    database = short_temp / "excluded.sqlite"
    _write_source(database, ())
    scope, parent_root, child_root = _scope_roots(short_temp, database)
    result = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=_cohort((), excluded=("X0001",)),
        decision_cutoff=_cutoff(),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope,
    )
    assert result.status == "complete"
    assert result.plan is not None
    assert result.plan.to_dict()["population_state"] == "all_excluded"
    assert result.plan.to_dict()["batches"] == []
    assert result.receipt is not None and result.receipt.status == "complete"
    assert result.receipt.to_dict()["batch_artifacts"] == []
    assert result.receipt.to_dict()["repository_output_root"] is None
    assert not child_root.exists()


def test_pre_finish_cancellation_does_not_create_plan_or_receipt(short_temp: Path) -> None:
    codes = ("2382",)
    database = short_temp / "cancel.sqlite"
    _write_source(database, codes)
    scope, parent_root, child_root = _scope_roots(short_temp, database)
    result = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=_cohort(codes),
        decision_cutoff=_cutoff(),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope,
        cancel_callback=lambda: True,
    )
    assert result.status == "cancelled"
    assert result.plan is None and result.receipt is None
    assert not parent_root.exists()
    assert not child_root.exists()


def test_explicit_resume_rejects_a_different_source_clock(short_temp: Path) -> None:
    codes = ("2382",)
    database_one = short_temp / "source-one.sqlite"
    database_two = short_temp / "source-two.sqlite"
    _write_source(database_one, codes)
    _write_source(database_two, codes)
    scope_one, parent_root, child_root = _scope_roots(short_temp, database_one)

    def cancel_after_batch() -> bool:
        return _receipt_count(parent_root) >= 2

    first = produce_daily_market_technical_parent_v4(
        source_database=database_one,
        cohort=_cohort(codes),
        decision_cutoff=_cutoff(),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope_one,
        cancel_callback=cancel_after_batch,
    )
    assert first.status == "cancelled" and first.receipt is not None

    scope_two = ResearchCaptureWriteScope(scope_one.configured_output_root, database_two)
    rejected = produce_daily_market_technical_parent_v4(
        source_database=database_two,
        cohort=_cohort(codes),
        decision_cutoff=_cutoff(),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope_two,
        resume_receipt_identity_sha256=first.receipt_identity_sha256,
        expected_resume_receipt_sha256=first.receipt_content_sha256,
    )
    assert rejected.status == "failed"
    assert rejected.error_code == "technical_parent_v4_resume_receipt_unavailable_for_current_plan"
    assert rejected.plan is not None and rejected.plan_identity_sha256 != first.plan_identity_sha256
    assert rejected.receipt is None


def test_source_pin_change_after_child_publish_prevents_parent_completion(
    short_temp: Path,
) -> None:
    codes = ("2382",)
    database = short_temp / "changing-source.sqlite"
    _write_source(database, codes)
    scope, parent_root, child_root = _scope_roots(short_temp, database)
    changed = False

    def change_source_after_first_child() -> bool:
        nonlocal changed
        if not changed and _receipt_count(parent_root) >= 2:
            connection = sqlite3.connect(database)
            try:
                with connection:
                    connection.execute(
                        "UPDATE daily_prices SET 成交股數=? WHERE 證券代號=?",
                        (9999, codes[0]),
                    )
            finally:
                connection.close()
            changed = True
        return False

    result = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=_cohort(codes),
        decision_cutoff=_cutoff(),
        child_output_root=child_root,
        parent_root=parent_root,
        research_scope=scope,
        cancel_callback=change_source_after_first_child,
    )
    assert changed is True
    assert result.status == "failed"
    assert result.error_code == "technical_parent_v4_source_pin_changed_after_finish"
    assert result.receipt is not None and result.receipt.status == "failed"
    assert len(result.receipt.to_dict()["batch_artifacts"]) == 1
