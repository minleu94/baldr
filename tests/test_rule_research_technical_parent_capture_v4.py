"""驗證 v4 parent cohort、跨批 immutable receipts 與嚴格讀回。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_read_session import DailyMarketTechnicalReadSession
from app_module.daily_market_technical_snapshot_v4_producer import (
    write_daily_market_technical_snapshot_v4_batch,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalSnapshotV4Repository,
    DailyMarketTechnicalSnapshotV4RepositoryError,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalCohortV4,
    DailyMarketTechnicalParentPlanV4,
    DailyMarketTechnicalParentCaptureV4VerifiedRead,
    BoundedDailyMarketTechnicalParentCaptureWriterV4,
    TechnicalParentCaptureV4Error,
    build_daily_market_technical_parent_plan_v4,
    read_daily_market_technical_parent_capture_v4,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)
_START_DATE = _DECISION_DATE - timedelta(days=39)


@pytest.fixture
def short_temp() -> Any:
    base = Path(r"C:\t").resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix="p4-", dir=base)).resolve(strict=True)
    try:
        yield directory
    finally:
        # Producer cancellation intentionally retains unpublished attempt files.
        # Prefix only this verified fixture path for Windows cleanup; durable
        # application paths and identities remain canonical and unprefixed.
        if directory.parent != base:
            raise AssertionError("parent_v4_fixture_path_escape")
        cleanup_path = str(directory)
        if sys.platform == "win32":
            cleanup_path = "\\\\?\\" + cleanup_path
        shutil.rmtree(cleanup_path)


def _write_source(path: Path, stock_codes: tuple[str, ...], *, omit: str | None = None) -> None:
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
                if stock_code == omit:
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


def _finished_session(
    database: Path,
    stock_codes: tuple[str, ...],
) -> tuple[Any, tuple[Any, ...]]:
    cutoff = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)
    with DailyMarketTechnicalReadSession(database, cutoff) as session:
        clock = session.clock
        for start in range(0, len(stock_codes), 16):
            session.load_batch(stock_codes[start:start + 16])
        windows = session.finish()
    return clock, windows


def _scope_and_roots(root: Path, database: Path) -> tuple[ResearchCaptureWriteScope, Path, Path]:
    scope = ResearchCaptureWriteScope(root / "configured", database)
    return scope, scope.root / "parent", scope.root / "snapshots"


def _cohort(codes: tuple[str, ...]) -> DailyMarketTechnicalCohortV4:
    return DailyMarketTechnicalCohortV4.create(
        universe_id="synthetic-tech-cohort",
        population_version="fixture-2026-10-06",
        decision_date=_DECISION_DATE,
        included_stock_codes=codes,
    )


def _make_batch(
    *,
    output_root: Path,
    research_scope: ResearchCaptureWriteScope,
    cohort: DailyMarketTechnicalCohortV4,
    source_clock: Any,
    windows: tuple[Any, ...],
    cancel_callback: Any = None,
) -> Any:
    result = write_daily_market_technical_snapshot_v4_batch(
        output_root=output_root,
        cohort=cohort,
        source_clock=source_clock,
        finished_windows=windows,
        cancel_callback=cancel_callback,
        research_scope=research_scope,
    )
    return result


def test_17_stock_parent_uses_one_finished_source_session_16_plus_1_and_resumes_exactly(
    short_temp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes = tuple(f"S{index:04d}" for index in range(17))
    database = short_temp / "prices.sqlite"
    _write_source(database, codes, omit=codes[-1])
    before_source = database.read_bytes()
    clock, windows = _finished_session(database, codes)
    assert len(windows) == 17
    assert windows[-1].stock_code == codes[-1]
    assert windows[-1].rows == ()
    assert all(windows[-1].evaluate()[i].state == "unknown" for i in range(5))
    assert database.read_bytes() == before_source

    cohort = _cohort(codes)
    plan = build_daily_market_technical_parent_plan_v4(
        cohort, source_clock=clock, finished_windows=windows
    )
    plan_body = plan.to_dict()
    assert [len(batch["expected_stock_codes"]) for batch in plan_body["batches"]] == [16, 1]
    missing_evidence = plan_body["source_stock_evidence"][-1]
    assert missing_evidence["stock_code"] == codes[-1]
    assert missing_evidence["row_count"] == 0
    assert set(missing_evidence["rule_states"].values()) == {"unknown"}

    scope, parent_root, snapshot_root = _scope_and_roots(short_temp, database)
    writer = BoundedDailyMarketTechnicalParentCaptureWriterV4(
        parent_root, research_scope=scope
    )
    receipt = writer.start(plan)
    first = _make_batch(
        output_root=snapshot_root,
        research_scope=scope,
        cohort=cohort,
        source_clock=clock,
        windows=windows[:16],
    )
    assert first.status == "complete" and first.artifact is not None
    receipt = writer.record_verified_batch(
        plan.identity_sha256,
        receipt.identity_sha256,
        expected_previous_receipt_sha256=receipt.content_sha256,
        artifact=first.artifact,
    )
    assert receipt.status == "partial"
    assert [item["batch_id"] for item in receipt.to_dict()["batch_artifacts"]] == ["batch-01"]

    cancel_checks = 0

    def cancel_after_artifact_write() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        # The real producer checks once after writing the batch artifact and
        # before publishing the manifest; cancellation here leaves an
        # unpublished attempt that must not enter the parent receipt.
        return cancel_checks >= 7

    cancelled = _make_batch(
        output_root=snapshot_root,
        research_scope=scope,
        cohort=cohort,
        source_clock=clock,
        windows=windows[16:],
        cancel_callback=cancel_after_artifact_write,
    )
    assert cancelled.status == "cancelled" and cancelled.artifact is None
    assert cancel_checks == 7
    terminal = writer.mark_terminal(
        plan.identity_sha256,
        receipt.identity_sha256,
        expected_previous_receipt_sha256=receipt.content_sha256,
        status="cancelled",
        error_code=cancelled.error_code or "technical_snapshot_v4_cancelled",
    )
    assert terminal.status == "cancelled"
    prior_child = terminal.to_dict()["batch_artifacts"][0]

    resumed = writer.resume(
        plan.identity_sha256,
        terminal.identity_sha256,
        expected_receipt_sha256=terminal.content_sha256,
    )
    assert resumed.status == "partial"
    assert resumed.to_dict()["batch_artifacts"] == [prior_child]
    second = _make_batch(
        output_root=snapshot_root,
        research_scope=scope,
        cohort=cohort,
        source_clock=clock,
        windows=windows[16:],
    )
    assert second.status == "complete" and second.artifact is not None
    resumed = writer.record_verified_batch(
        plan.identity_sha256,
        resumed.identity_sha256,
        expected_previous_receipt_sha256=resumed.content_sha256,
        artifact=second.artifact,
    )
    completed = writer.complete(
        plan.identity_sha256,
        resumed.identity_sha256,
        expected_previous_receipt_sha256=resumed.content_sha256,
    )
    assert completed.status == "complete"
    assert len(completed.to_dict()["batch_artifacts"]) == 2
    assert completed.to_dict()["batch_artifacts"][0] == prior_child

    # 只刪除本測試建出的來源檔，證明新程序按 receipt 重開不依賴目前 DB。
    database.unlink()
    read_root = BoundedDailyMarketTechnicalParentCaptureWriterV4(parent_root, read_only=True)
    package = read_root.read(
        plan.identity_sha256,
        completed.identity_sha256,
        expected_receipt_sha256=completed.content_sha256,
    )
    assert package["receipt"]["status"] == "complete"

    original_read_exact = DailyMarketTechnicalSnapshotV4Repository.read_exact
    read_exact_paths: list[Path] = []

    def tracked_read_exact(
        repository: DailyMarketTechnicalSnapshotV4Repository,
        manifest_path: str | Path,
        **kwargs: Any,
    ) -> Any:
        read_exact_paths.append(Path(manifest_path))
        return original_read_exact(repository, manifest_path, **kwargs)

    monkeypatch.setattr(
        DailyMarketTechnicalSnapshotV4Repository,
        "read_exact",
        tracked_read_exact,
    )
    verified = read_root.read_verified(
        plan.identity_sha256,
        completed.identity_sha256,
        expected_receipt_sha256=completed.content_sha256,
        expected_plan_sha256=plan.content_sha256,
    )
    assert isinstance(verified, DailyMarketTechnicalParentCaptureV4VerifiedRead)
    assert verified.package == package
    assert set(verified.package) == {
        "plan", "plan_sha256", "receipt", "receipt_sha256"
    }
    assert tuple(len(batch.snapshots) for batch in verified.verified_batches) == (16, 1)
    assert tuple(
        snapshot.stock_code
        for batch in verified.verified_batches
        for snapshot in batch.snapshots
    ) == codes
    assert read_exact_paths == [
        Path(item["manifest_path"]) for item in completed.to_dict()["batch_artifacts"]
    ]

    # 舊 API 仍回傳原 dict 並自行完成所有核驗，不經 read_verified 留住批次。
    old_api_package = read_root.read(
        plan.identity_sha256,
        completed.identity_sha256,
        expected_receipt_sha256=completed.content_sha256,
        expected_plan_sha256=plan.content_sha256,
    )
    assert old_api_package == verified.package
    assert len(read_exact_paths) == 4

    cancel_checks = 0

    def cancel_before_first_batch() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancel_checks == 2

    with pytest.raises(TechnicalParentCaptureV4Error, match="technical_parent_v4_read_cancelled"):
        read_root.read_verified(
            plan.identity_sha256,
            completed.identity_sha256,
            expected_receipt_sha256=completed.content_sha256,
            cancel_callback=cancel_before_first_batch,
        )
    assert cancel_checks == 2
    assert len(read_exact_paths) == 4

    cancel_checks = 0

    def cancel_after_first_batch() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancel_checks == 3

    with pytest.raises(TechnicalParentCaptureV4Error, match="technical_parent_v4_read_cancelled"):
        read_root.read_verified(
            plan.identity_sha256,
            completed.identity_sha256,
            expected_receipt_sha256=completed.content_sha256,
            cancel_callback=cancel_after_first_batch,
        )
    assert cancel_checks == 3
    assert len(read_exact_paths) == 5

    script = (
        "from app_module.rule_research_technical_parent_capture_v4 import "
        "read_daily_market_technical_parent_capture_v4; import sys; "
        "p=read_daily_market_technical_parent_capture_v4(sys.argv[1],sys.argv[2],sys.argv[3],"
        "expected_receipt_sha256=sys.argv[4]); print(p['receipt']['status'])"
    )
    reopened = subprocess.run(
        [sys.executable, "-c", script, str(parent_root), plan.identity_sha256,
         completed.identity_sha256, completed.content_sha256],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert reopened.stdout.strip() == "complete"

    first_batch = verified.verified_batches[0]
    manifest_io_path = to_internal_io_path(first_batch.manifest_path)
    with open(manifest_io_path, "rb") as manifest_reader:
        manifest_bytes = manifest_reader.read()
    with open(manifest_io_path, "wb") as manifest_writer:
        manifest_writer.write(manifest_bytes + b" ")
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as error:
        read_root.read_verified(
            plan.identity_sha256,
            completed.identity_sha256,
            expected_receipt_sha256=completed.content_sha256,
        )
    assert error.value.code == "technical_snapshot_v4_manifest_sha_mismatch"


@pytest.mark.parametrize(
    ("included", "excluded", "expected_state"),
    (((), ("X0001",), "all_excluded"), ((), (), "empty")),
)
def test_zero_included_has_explicit_complete_state_without_child_or_no_match(
    short_temp: Path,
    included: tuple[str, ...],
    excluded: tuple[str, ...],
    expected_state: str,
) -> None:
    database = short_temp / f"empty-{expected_state}.sqlite"
    _write_source(database, ())
    cutoff = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)
    with DailyMarketTechnicalReadSession(database, cutoff) as session:
        clock = session.clock
        session.load_batch(())
        windows = session.finish()
    cohort = DailyMarketTechnicalCohortV4.create(
        universe_id=f"empty-{expected_state}",
        population_version="fixture-v1",
        decision_date=_DECISION_DATE,
        included_stock_codes=included,
        excluded_stock_codes=excluded,
        exclusion_reasons={code: "原始母體明示排除" for code in excluded},
    )
    plan = build_daily_market_technical_parent_plan_v4(
        cohort, source_clock=clock, finished_windows=windows
    )
    assert plan.to_dict()["population_state"] == expected_state
    assert plan.to_dict()["batches"] == []

    scope, parent_root, _snapshot_root = _scope_and_roots(short_temp, database)
    writer = BoundedDailyMarketTechnicalParentCaptureWriterV4(
        parent_root, research_scope=scope
    )
    started = writer.start(plan)
    completed = writer.complete(
        plan.identity_sha256,
        started.identity_sha256,
        expected_previous_receipt_sha256=started.content_sha256,
    )
    assert completed.status == "complete"
    assert completed.to_dict()["batch_artifacts"] == []
    assert completed.to_dict()["repository_output_root"] is None
    # 公開跨程序讀回入口也須接受真零child parent，不可建立None root的repository。
    source_sha = hashlib.sha256(database.read_bytes()).hexdigest()
    reopened = read_daily_market_technical_parent_capture_v4(
        parent_root,
        plan.identity_sha256,
        completed.identity_sha256,
        expected_plan_sha256=plan.content_sha256,
        expected_receipt_sha256=completed.content_sha256,
    )
    assert reopened["plan"]["population_state"] == expected_state
    assert reopened["plan"]["cohort"]["excluded_stock_codes"] == list(excluded)
    assert reopened["receipt"]["status"] == "complete"
    assert reopened["receipt"]["batch_artifacts"] == []
    assert reopened["receipt"]["repository_output_root"] is None
    verified = BoundedDailyMarketTechnicalParentCaptureWriterV4(
        parent_root, read_only=True
    ).read_verified(
        plan.identity_sha256,
        completed.identity_sha256,
        expected_plan_sha256=plan.content_sha256,
        expected_receipt_sha256=completed.content_sha256,
    )
    assert verified.package == reopened
    assert verified.verified_batches == ()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == source_sha


def test_cohort_and_plan_reject_duplicate_wrong_date_mixed_clock_and_rehashed_tamper(
    short_temp: Path,
) -> None:
    with pytest.raises(TechnicalParentCaptureV4Error, match="included_codes"):
        DailyMarketTechnicalCohortV4.create(
            universe_id="duplicate",
            population_version="v1",
            decision_date=_DECISION_DATE,
            included_stock_codes=("2382", "2382"),
        )

    codes = ("2382",)
    database_one = short_temp / "one.sqlite"
    database_two = short_temp / "two.sqlite"
    _write_source(database_one, codes)
    _write_source(database_two, codes)
    clock_one, windows_one = _finished_session(database_one, codes)
    clock_two, windows_two = _finished_session(database_two, codes)
    cohort = _cohort(codes)
    with pytest.raises(TechnicalParentCaptureV4Error, match="date_mismatch"):
        wrong_date_cohort = DailyMarketTechnicalCohortV4.create(
            universe_id="wrong-date",
            population_version="v1",
            decision_date=_DECISION_DATE - timedelta(days=1),
            included_stock_codes=codes,
        )
        build_daily_market_technical_parent_plan_v4(
            wrong_date_cohort, source_clock=clock_one, finished_windows=windows_one
        )
    with pytest.raises(TechnicalParentCaptureV4Error, match="window_source_clock_mismatch"):
        build_daily_market_technical_parent_plan_v4(
            cohort, source_clock=clock_one, finished_windows=windows_two
        )
    with pytest.raises(TechnicalParentCaptureV4Error, match="finished_window_count_mismatch"):
        build_daily_market_technical_parent_plan_v4(
            cohort, source_clock=clock_one, finished_windows=windows_one + windows_two
        )

    plan = build_daily_market_technical_parent_plan_v4(
        cohort, source_clock=clock_one, finished_windows=windows_one
    )
    payload = plan.to_dict()
    payload["source_stock_evidence"][0]["rule_states"]["ma5_20_golden_cross"] = "match"
    payload["parent_plan_identity_sha256"] = "0" * 64
    with pytest.raises(TechnicalParentCaptureV4Error, match="plan_identity_mismatch"):
        DailyMarketTechnicalParentPlanV4.from_dict(payload)
    with pytest.raises(TechnicalParentCaptureV4Error, match="duplicate_json_key"):
        DailyMarketTechnicalParentPlanV4.from_json('{"a":1,"a":2}')
    with pytest.raises(TechnicalParentCaptureV4Error, match="float_forbidden"):
        DailyMarketTechnicalParentPlanV4.from_dict({**payload, "forbidden": 0.5})
