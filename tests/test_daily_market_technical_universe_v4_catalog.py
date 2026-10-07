"""full-N v4 catalog 的真實保存、metadata 分頁與 exact read 測試。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_universe_v4_catalog as catalog_module
from app_module.daily_market_technical_parent_v4_producer import (
    produce_daily_market_technical_parent_v4,
)
from app_module.daily_market_technical_universe_v4_catalog import (
    DailyMarketTechnicalUniverseV4Catalog,
    DailyMarketTechnicalUniverseV4CatalogError,
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
_START_DATE = _DECISION_DATE - timedelta(days=39)


@pytest.fixture
def short_temp() -> Any:
    base = Path(tempfile.gettempdir()).resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix="uv4catalog-", dir=base)).resolve(strict=True)
    try:
        yield directory
    finally:
        if directory.parent != base:
            raise AssertionError("technical_universe_v4_catalog_fixture_path_escape")
        cleanup_path = str(directory)
        if sys.platform == "win32":
            cleanup_path = "\\\\?\\" + cleanup_path
        shutil.rmtree(cleanup_path)


def _write_source(path: Path) -> None:
    connection = sqlite3.connect(to_internal_io_path(path))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows = []
            for offset in range(40):
                close = 80 + offset
                day = _START_DATE + timedelta(days=offset)
                rows.append((day.isoformat(), "A1234", str(close), str(close + 1), str(close - 1), str(close), 2000 + offset))
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        connection.close()


def _long_configured_root(base: Path) -> Path:
    part = "catalog-research-" + "r" * 64
    return base / part / part / part


def _cohort(population_version: str, *, included: tuple[str, ...] = (), excluded: tuple[str, ...] = ()) -> DailyMarketTechnicalUniverseV4Cohort:
    return DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="catalog-fixture-v4",
        population_version=population_version,
        decision_date=_DECISION_DATE,
        raw_stock_codes=(*included, *excluded),
        excluded_stock_codes=excluded,
        exclusion_reasons={code: "測試母體明示排除" for code in excluded},
    )


def _parent_cohort(full: DailyMarketTechnicalUniverseV4Cohort) -> DailyMarketTechnicalCohortV4:
    reasons = dict(full.exclusion_reasons)
    return DailyMarketTechnicalCohortV4.create(
        universe_id=full.universe_id,
        population_version=full.population_version,
        decision_date=full.decision_date,
        included_stock_codes=full.included_stock_codes,
        excluded_stock_codes=full.excluded_stock_codes,
        exclusion_reasons=reasons,
    )


def _save_parent(
    *,
    database: Path,
    scope: ResearchCaptureWriteScope,
    cohort: DailyMarketTechnicalCohortV4,
    name: str,
) -> tuple[DailyMarketTechnicalUniverseV4ParentReceiptReference, dict[str, object]]:
    result = produce_daily_market_technical_parent_v4(
        source_database=database,
        cohort=cohort,
        decision_cutoff=datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI),
        child_output_root=scope.root / "children" / name,
        parent_root=scope.root / "parents" / name,
        research_scope=scope,
    )
    assert result.status == "complete", result.error_code
    assert result.plan is not None and result.receipt is not None
    reference = DailyMarketTechnicalUniverseV4ParentReceiptReference.create(
        scope.root / "parents" / name,
        parent_plan_identity_sha256=result.plan.identity_sha256,
        parent_plan_sha256=result.plan.content_sha256,
        parent_receipt_identity_sha256=result.receipt.identity_sha256,
        parent_receipt_sha256=result.receipt.content_sha256,
    )
    return reference, result.plan.to_dict()


def _save_full_store_version(
    *,
    store_root: Path,
    scope: ResearchCaptureWriteScope,
    full: DailyMarketTechnicalUniverseV4Cohort,
    source_clock_payload: dict[str, object],
    parent_reference: DailyMarketTechnicalUniverseV4ParentReceiptReference | None,
    terminal: str = "complete",
) -> tuple[DailyMarketTechnicalUniverseV4Plan, str, str]:
    source_clock = daily_market_technical_source_clock_v4_from_dict(source_clock_payload)
    plan = DailyMarketTechnicalUniverseV4Plan.build(full, source_clock=source_clock)
    writer = DailyMarketTechnicalUniverseV4StoreWriter(store_root, research_scope=scope)
    receipt = writer.start(plan)
    if terminal == "cancelled":
        receipt = writer.mark_terminal(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            receipt.identity_sha256,
            expected_previous_receipt_sha256=receipt.content_sha256,
            status="cancelled",
            error_code="catalog_fixture_cancelled",
        )
    else:
        if parent_reference is not None:
            receipt = writer.record_segment_parent(
                plan.generation_identity_sha256,
                plan.identity_sha256,
                receipt.identity_sha256,
                expected_previous_receipt_sha256=receipt.content_sha256,
                segment_index=0,
                parent_reference=parent_reference,
            )
        receipt = writer.complete(
            plan.generation_identity_sha256,
            plan.identity_sha256,
            receipt.identity_sha256,
            expected_previous_receipt_sha256=receipt.content_sha256,
        )
    return plan, receipt.identity_sha256, receipt.content_sha256


def _build_catalog_fixture(base: Path) -> tuple[Path, Path, tuple[str, ...]]:
    database = base / "catalog-source.sqlite"
    _write_source(database)
    scope = ResearchCaptureWriteScope(_long_configured_root(base), database)
    store_root = scope.root / ("catalog-store-" + "s" * 82)
    assert len(str(store_root / "daily_market_technical_universe_v4")) > 260

    primary = _cohort("complete-stock", included=("A1234",))
    primary_parent, primary_plan = _save_parent(
        database=database,
        scope=scope,
        cohort=_parent_cohort(primary),
        name="catalog-primary",
    )
    source_clock_payload = primary_plan["source_clock"]
    assert isinstance(source_clock_payload, dict)
    complete_plan, complete_receipt_id, complete_receipt_sha = _save_full_store_version(
        store_root=store_root,
        scope=scope,
        full=primary,
        source_clock_payload=source_clock_payload,
        parent_reference=primary_parent,
    )

    cancelled = _cohort("cancelled-stock", included=("A1234",))
    cancelled_plan, cancelled_receipt_id, _cancelled_receipt_sha = _save_full_store_version(
        store_root=store_root,
        scope=scope,
        full=cancelled,
        source_clock_payload=source_clock_payload,
        parent_reference=None,
        terminal="cancelled",
    )

    excluded = _cohort("all-excluded-stock", excluded=("X0001",))
    excluded_parent, _excluded_parent_plan = _save_parent(
        database=database,
        scope=scope,
        cohort=_parent_cohort(excluded),
        name="catalog-excluded",
    )
    excluded_plan, excluded_receipt_id, _excluded_receipt_sha = _save_full_store_version(
        store_root=store_root,
        scope=scope,
        full=excluded,
        source_clock_payload=source_clock_payload,
        parent_reference=excluded_parent,
    )

    empty = _cohort("empty-cohort")
    empty_plan, empty_receipt_id, _empty_receipt_sha = _save_full_store_version(
        store_root=store_root,
        scope=scope,
        full=empty,
        source_clock_payload=source_clock_payload,
        parent_reference=None,
    )

    # 非 canonical receipt 仍須有具名 diagnostics，不能遮住其他保存版本。
    corrupt_receipt = (
        store_root
        / "daily_market_technical_universe_v4"
        / "generations"
        / excluded_plan.generation_identity_sha256
        / "receipts"
        / (("f" * 64) + ".json")
    )
    with open(to_internal_io_path(corrupt_receipt), "xb") as handle:
        handle.write(b"{\"corrupt\":true}")
    return store_root, database, (
        complete_plan.generation_identity_sha256,
        complete_plan.identity_sha256,
        complete_receipt_id,
        complete_receipt_sha,
        cancelled_plan.generation_identity_sha256,
        cancelled_plan.identity_sha256,
        cancelled_receipt_id,
        excluded_plan.generation_identity_sha256,
        excluded_plan.identity_sha256,
        excluded_receipt_id,
        empty_plan.generation_identity_sha256,
        empty_plan.identity_sha256,
        empty_receipt_id,
    )


def test_catalog_lists_real_versions_corruption_and_strictly_reopens_after_source_db_removed(
    short_temp: Path,
) -> None:
    store_root, database, pins = _build_catalog_fixture(short_temp)
    database.unlink()

    catalog = DailyMarketTechnicalUniverseV4Catalog(store_root)
    page = catalog.list_page(limit=100)
    assert page.scan_complete is True
    assert page.has_more is False
    assert page.next_cursor is None
    assert "最多 100,000" in page.scan_cost_notice
    records = [row for row in page.rows if row.metadata_state == "metadata_unverified"]
    diagnostics = [row for row in page.rows if row.metadata_state == "diagnostic"]
    assert len(records) == 4
    assert len(diagnostics) == 1
    assert diagnostics[0].diagnostic_code is not None
    assert diagnostics[0].relative_path.endswith("f" * 64 + ".json")
    assert all(row.is_selectable for row in records)
    assert all(row.metadata_state == "metadata_unverified" for row in records)
    assert {row.source_status for row in records} == {"complete", "cancelled"}

    by_receipt = {row.receipt_identity_sha256: row for row in records}
    assert by_receipt[pins[2]].population_state == "included"
    assert by_receipt[pins[6]].source_status == "cancelled"
    assert by_receipt[pins[9]].population_state == "all_excluded"
    assert by_receipt[pins[12]].population_state == "empty"
    assert by_receipt[pins[9]].counts is not None
    assert by_receipt[pins[9]].counts.declared_count == 1
    assert by_receipt[pins[9]].counts.included_count == 0
    assert by_receipt[pins[12]].counts is not None
    assert by_receipt[pins[12]].counts.declared_count == 0

    # Metadata listing is not the selection gate; selecting an entry invokes the strict reader.
    verified = catalog.read_exact(by_receipt[pins[2]])
    assert verified.receipt.status == "complete"
    assert verified.counts.processed_count == 1
    assert not database.exists()

    script = (
        "from app_module.daily_market_technical_universe_v4_catalog import "
        "DailyMarketTechnicalUniverseV4Catalog; import sys; "
        "c=DailyMarketTechnicalUniverseV4Catalog(sys.argv[1]); "
        "p=c.list_page(limit=100); "
        "e=next(x for x in p.rows if x.receipt_identity_sha256==sys.argv[2]); "
        "s=c.read_exact(e); print(s.receipt.status+':'+str(s.counts.processed_count))"
    )
    reopened = subprocess.run(
        [sys.executable, "-c", script, str(store_root), pins[2]],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert reopened.stdout.strip() == "complete:1"


def test_catalog_cursor_pages_all_rows_and_rejects_stale_inventory(
    short_temp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_root, _database, _pins = _build_catalog_fixture(short_temp)
    catalog = DailyMarketTechnicalUniverseV4Catalog(store_root)
    rows = []
    page = catalog.list_page(limit=1)
    assert page.scan_complete is True
    assert page.has_more is True
    assert page.next_cursor is not None
    rows.extend(page.rows)
    cursor = page.next_cursor
    while cursor is not None:
        page = catalog.list_page(limit=1, cursor=cursor)
        assert page.scan_complete is True
        rows.extend(page.rows)
        cursor = page.next_cursor
    assert len(rows) == 5
    assert any(row.metadata_state == "diagnostic" for row in rows)
    assert page.has_more is False

    def stable_stat_without_timestamps(info: os.stat_result | None) -> tuple[int, int, int, int, int, int, int, int]:
        if info is None:
            return (0, 0, 0, 0, 0, 0, 0, 0)
        return (
            int(info.st_mode), int(info.st_dev), int(info.st_ino), int(info.st_size),
            0, 0, int(info.st_nlink), int(getattr(info, "st_file_attributes", 0)),
        )

    # 即使測試暫時忽略 stat 時間欄位，bytes fingerprint 仍須抓到同長度置換。
    monkeypatch.setattr(catalog_module, "_stat_signature", stable_stat_without_timestamps)
    stale_cursor = catalog.list_page(limit=1).next_cursor
    assert stale_cursor is not None
    receipt_path = (
        store_root
        / "daily_market_technical_universe_v4"
        / "generations"
        / _pins[0]
        / "receipts"
        / f"{_pins[2]}.json"
    )
    before_info = os.stat(to_internal_io_path(receipt_path))
    with open(to_internal_io_path(receipt_path), "r+b") as handle:
        original = handle.read()
        changed = original.replace(b'"status":"complete"', b'"status":"Complete"', 1)
        assert len(changed) == len(original) and changed != original
        handle.seek(0)
        handle.write(changed)
        handle.truncate()
    os.utime(
        to_internal_io_path(receipt_path),
        ns=(before_info.st_atime_ns, before_info.st_mtime_ns),
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4CatalogError) as error:
        catalog.list_page(limit=1, cursor=stale_cursor)
    assert error.value.code == "technical_universe_v4_catalog_stale_cursor"

def test_catalog_marks_budget_truncation_unknown_instead_of_claiming_full_results(
    short_temp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_root, _database, _pins = _build_catalog_fixture(short_temp)
    monkeypatch.setattr(
        catalog_module,
        "DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES",
        2,
    )
    page = DailyMarketTechnicalUniverseV4Catalog(store_root).list_page(limit=1)
    assert page.scan_complete is False
    assert page.continuation_required is True
    assert page.has_more is None
    assert page.next_cursor is None
    assert page.scanned_entry_count == 2
    assert any(row.diagnostic_code == "catalog_inventory_entry_budget_exceeded" for row in page.rows)


def test_catalog_distinguishes_no_saved_generation_from_zero_member_generation(
    short_temp: Path,
) -> None:
    empty_root = short_temp / "not-created-output-root"
    empty_page = DailyMarketTechnicalUniverseV4Catalog(empty_root).list_page()
    assert empty_page.rows == ()
    assert empty_page.source_inventory_state == "no_saved_generations"
    assert not empty_root.exists()

    store_root, _database, pins = _build_catalog_fixture(short_temp)
    page = DailyMarketTechnicalUniverseV4Catalog(store_root).list_page(limit=100)
    zero_member = next(row for row in page.rows if row.receipt_identity_sha256 == pins[12])
    assert page.source_inventory_state == "saved_generations_present"
    assert zero_member.population_state == "empty"
    assert zero_member.counts is not None and zero_member.counts.declared_count == 0
