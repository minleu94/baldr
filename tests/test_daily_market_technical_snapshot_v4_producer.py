"""驗證 v4 技術快照 producer 的真 SQLite 保存路徑。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import os
import sqlite3
import stat
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_snapshot_v4_producer as producer_module
from app_module.daily_market_technical_read_session import (
    DailyMarketTechnicalReadSession,
    DailyMarketTechnicalSourceClockV4,
)
from app_module.daily_market_technical_source import DailyMarketTechnicalSourceWindow
from app_module.daily_market_technical_snapshot_v4_producer import (
    DailyMarketTechnicalSnapshotV4ProducerError,
    write_daily_market_technical_snapshot_v4_batch,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_ARTIFACT_BYTES,
    DailyMarketTechnicalSnapshotV4Repository,
    canonical_v4_json_bytes,
    sha256_bytes,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope


_TAIPEI = ZoneInfo("Asia/Taipei")
_START_DATE = date(2026, 7, 1)


def _read_bytes(path: Path) -> bytes:
    with open(to_internal_io_path(path), "rb") as handle:
        return handle.read()


def _find_named_files(root: Path, filename: str) -> list[Path]:
    found: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(to_internal_io_path(current)) as entries:
            for entry in entries:
                child = current / entry.name
                mode = os.stat(to_internal_io_path(child), follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    stack.append(child)
                elif entry.name == filename and stat.S_ISREG(mode):
                    found.append(child)
    return found


def _write_source(path: Path, stock_codes: tuple[str, ...], *, rows_per_stock: int = 40) -> None:
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
                for offset in range(rows_per_stock):
                    close = 100 + offset
                    day = _START_DATE + timedelta(days=offset)
                    rows.append((
                        day.isoformat(),
                        stock_code,
                        str(close),
                        str(close + 1),
                        str(close - 1),
                        str(close),
                        1000 + offset,
                    ))
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                rows,
            )
    finally:
        connection.close()


def _cohort(
    included: tuple[str, ...],
    excluded: tuple[str, ...] = (),
    *,
    decision_date: date | None = None,
) -> dict[str, object]:
    included_codes = tuple(sorted(included))
    excluded_codes = tuple(sorted(excluded))
    core: dict[str, object] = {
        "schema_version": "daily-market-technical-cohort.v4",
        "universe_id": "test-universe",
        "population_version": "population.v1",
        "decision_date": (decision_date or (_START_DATE + timedelta(days=39))).isoformat(),
        "included_stock_codes": list(included_codes),
        "excluded_stock_codes": list(excluded_codes),
        "exclusion_reasons": {code: "明示排除測試" for code in excluded_codes},
        "declared_count": len(included_codes) + len(excluded_codes),
    }
    return {
        **core,
        "cohort_identity_sha256": sha256_bytes(canonical_v4_json_bytes(core)),
    }


def _finished_windows(
    database: Path,
    stock_codes: tuple[str, ...],
) -> tuple[DailyMarketTechnicalSourceClockV4, tuple[DailyMarketTechnicalSourceWindow, ...]]:
    cutoff = datetime.combine(
        _START_DATE + timedelta(days=39),
        time(16, 0),
        tzinfo=_TAIPEI,
    )
    with DailyMarketTechnicalReadSession(database, cutoff) as session:
        clock = session.clock
        for start in range(0, len(stock_codes), 16):
            session.load_batch(stock_codes[start : start + 16])
        windows = session.finish()
    return clock, windows


def _fixture_paths(
    tmp_path: Path,
    stock_count: int = 16,
) -> tuple[
    Path,
    Path,
    tuple[str, ...],
    DailyMarketTechnicalSourceClockV4,
    tuple[DailyMarketTechnicalSourceWindow, ...],
]:
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    source_dir.mkdir()
    output_dir.mkdir()
    stock_codes = tuple(f"S{index:04d}" for index in range(stock_count))
    database = source_dir / "prices.sqlite"
    _write_source(database, stock_codes)
    clock, windows = _finished_windows(database, stock_codes)
    return database, output_dir / "run", stock_codes, clock, windows


def test_real_sixteen_stock_finished_session_roundtrips_with_full_cohort(
    tmp_path: Path,
) -> None:
    _database, output_root, codes, clock, windows = _fixture_paths(tmp_path)
    excluded = ("S9999",)
    cohort = _cohort(codes, excluded)

    result = write_daily_market_technical_snapshot_v4_batch(
        output_root=output_root,
        cohort=cohort,
        source_clock=clock,  # type: ignore[arg-type]
        finished_windows=windows,  # type: ignore[arg-type]
    )

    assert result.status == "complete"
    assert result.error_code is None
    assert result.reused_existing is False
    assert result.artifact is not None
    artifact = result.artifact
    assert artifact.repository_output_root == output_root
    assert artifact.manifest_path.name == "manifest.json"
    assert artifact.included_stock_codes == codes
    assert artifact.excluded_stock_codes == excluded
    assert artifact.exclusion_reasons == (("S9999", "明示排除測試"),)
    assert artifact.expected_stock_codes == codes
    assert artifact.source_clock.identity_sha256 == clock.identity_sha256
    assert len(artifact.snapshots) == 16
    assert all(snapshot.stock_code == code for snapshot, code in zip(artifact.snapshots, codes))
    assert all(len(snapshot.rows) == 40 for snapshot in artifact.snapshots)
    assert all(snapshot.availability_status == "unknown" for snapshot in artifact.snapshots)
    assert all(snapshot.method_contracts_sha256 == artifact.method_contract_sha256 for snapshot in artifact.snapshots)
    assert sum(ref.byte_size for ref in artifact.artifact_refs) <= DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_ARTIFACT_BYTES

    reread = DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(
        artifact.manifest_path,
        expected_manifest_sha256=artifact.manifest_sha256,
        expected_cohort_identity_sha256=artifact.cohort_identity_sha256,
        expected_source_clock_sha256=artifact.source_clock_identity_sha256,
        expected_method_contract_sha256=artifact.method_contract_sha256,
        expected_decision_date=artifact.decision_date,
    )
    assert reread == artifact


def test_identical_completed_batch_is_reused_without_overwriting_history(
    tmp_path: Path,
) -> None:
    _database, output_root, codes, clock, windows = _fixture_paths(tmp_path)
    cohort = _cohort(codes)
    first = write_daily_market_technical_snapshot_v4_batch(
        output_root=output_root,
        cohort=cohort,
        source_clock=clock,
        finished_windows=windows,
    )
    assert first.artifact is not None
    manifest_before = _read_bytes(first.artifact.manifest_path)
    artifact_before = tuple(
        (ref.relative_path, _read_bytes(first.artifact.manifest_path.parent / ref.relative_path))
        for ref in first.artifact.artifact_refs
    )

    retry = write_daily_market_technical_snapshot_v4_batch(
        output_root=output_root,
        cohort=cohort,
        source_clock=clock,
        finished_windows=windows,
    )

    assert retry.status == "complete"
    assert retry.reused_existing is True
    assert retry.artifact == first.artifact
    assert _read_bytes(first.artifact.manifest_path) == manifest_before
    assert tuple(
        (ref.relative_path, _read_bytes(first.artifact.manifest_path.parent / ref.relative_path))
        for ref in first.artifact.artifact_refs
    ) == artifact_before


def test_seventeen_finished_windows_are_rejected_by_child_batch_cap(tmp_path: Path) -> None:
    _database, output_root, codes, clock, windows = _fixture_paths(tmp_path, stock_count=17)
    with pytest.raises(DailyMarketTechnicalSnapshotV4ProducerError) as error_info:
        write_daily_market_technical_snapshot_v4_batch(
            output_root=output_root,
            cohort=_cohort(codes),
            source_clock=clock,
            finished_windows=windows,
        )
    assert error_info.value.code == "technical_snapshot_v4_batch_stock_limit"
    assert not output_root.exists()


def test_cancel_before_first_write_leaves_no_output_tree(tmp_path: Path) -> None:
    _database, output_root, codes, clock, windows = _fixture_paths(tmp_path)
    result = write_daily_market_technical_snapshot_v4_batch(
        output_root=output_root,
        cohort=_cohort(codes),
        source_clock=clock,
        finished_windows=windows,
        cancel_callback=lambda: True,
    )
    assert result.status == "cancelled"
    assert result.artifact is None
    assert not output_root.exists()


def test_late_cancel_after_manifest_temp_is_never_published(tmp_path: Path) -> None:
    _database, output_root, codes, clock, windows = _fixture_paths(tmp_path)

    def cancel_after_manifest_stage() -> bool:
        if not output_root.exists():
            return False
        return bool(_find_named_files(output_root, "manifest.json.tmp"))

    result = write_daily_market_technical_snapshot_v4_batch(
        output_root=output_root,
        cohort=_cohort(codes),
        source_clock=clock,
        finished_windows=windows,
        cancel_callback=cancel_after_manifest_stage,
    )
    assert result.status == "cancelled"
    assert result.artifact is None
    assert _find_named_files(output_root, "manifest.json") == []
    assert len(_find_named_files(output_root, "manifest.json.tmp")) == 1


def test_artifact_capacity_is_preflighted_before_creating_any_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _database, output_root, codes, clock, windows = _fixture_paths(tmp_path)
    monkeypatch.setattr(
        producer_module,
        "DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_BATCH_ARTIFACT_BYTES",
        1,
    )
    with pytest.raises(DailyMarketTechnicalSnapshotV4ProducerError) as error_info:
        write_daily_market_technical_snapshot_v4_batch(
            output_root=output_root,
            cohort=_cohort(codes),
        source_clock=clock,
        finished_windows=windows,
        )
    assert error_info.value.code == "technical_snapshot_v4_batch_artifact_limit"
    assert not output_root.exists()


def test_wrong_date_or_source_clock_is_rejected_before_writing(tmp_path: Path) -> None:
    database, output_root, codes, clock, windows = _fixture_paths(tmp_path)
    bad_date = _cohort(codes, decision_date=_START_DATE + timedelta(days=38))
    with pytest.raises(DailyMarketTechnicalSnapshotV4ProducerError) as date_error:
        write_daily_market_technical_snapshot_v4_batch(
            output_root=output_root,
            cohort=bad_date,
            source_clock=clock,
            finished_windows=windows,
        )
    assert date_error.value.code == "technical_snapshot_v4_decision_date_mismatch"
    assert not output_root.exists()

    other_db = tmp_path / "other-source.sqlite"
    _write_source(other_db, (codes[0],))
    other_clock, _other_windows = _finished_windows(other_db, (codes[0],))
    with pytest.raises(DailyMarketTechnicalSnapshotV4ProducerError) as source_error:
        write_daily_market_technical_snapshot_v4_batch(
            output_root=output_root,
            cohort=_cohort(codes),
            source_clock=other_clock,
            finished_windows=windows,
        )
    assert source_error.value.code == "technical_snapshot_v4_window_clock_mismatch"
    assert not output_root.exists()
    assert database.exists()


def test_capacity_failure_is_reported_without_publishing_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _database, output_root, codes, clock, windows = _fixture_paths(tmp_path)
    monkeypatch.setattr(producer_module, "_available_bytes", lambda _path: 0)
    with pytest.raises(DailyMarketTechnicalSnapshotV4ProducerError) as error_info:
        write_daily_market_technical_snapshot_v4_batch(
            output_root=output_root,
            cohort=_cohort(codes),
        source_clock=clock,
        finished_windows=windows,
        )
    assert error_info.value.code == "technical_snapshot_v4_capacity_insufficient"
    assert not output_root.exists()


def test_retention_limit_is_preflighted_before_creating_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _database, output_root, codes, clock, windows = _fixture_paths(tmp_path)
    monkeypatch.setattr(
        producer_module,
        "_scan_tree_size",
        lambda _root, *, limit: limit,
    )
    with pytest.raises(DailyMarketTechnicalSnapshotV4ProducerError) as error_info:
        write_daily_market_technical_snapshot_v4_batch(
            output_root=output_root,
            cohort=_cohort(codes),
            source_clock=clock,
            finished_windows=windows,
        )
    assert error_info.value.code == "technical_snapshot_v4_retention_limit"
    assert not output_root.exists()


def test_scope_bound_to_another_database_is_rejected_before_writing(
    tmp_path: Path,
) -> None:
    database, _output_root, codes, clock, windows = _fixture_paths(tmp_path)
    other_database = tmp_path / "different-source.sqlite"
    _write_source(other_database, ("OTHER",))
    scope = ResearchCaptureWriteScope(tmp_path / "configured-output", other_database)
    scoped_output = scope.root / "daily-technical"

    with pytest.raises(DailyMarketTechnicalSnapshotV4ProducerError) as error_info:
        write_daily_market_technical_snapshot_v4_batch(
            output_root=scoped_output,
            cohort=_cohort(codes),
            source_clock=clock,
            finished_windows=windows,
            research_scope=scope,
        )

    assert error_info.value.code == "technical_snapshot_v4_research_scope_source_mismatch"
    assert database.exists()
    assert not scoped_output.exists()


def test_long_output_root_uses_internal_io_paths_and_keeps_canonical_identity(
    tmp_path: Path,
) -> None:
    _database, _output_root, codes, clock, windows = _fixture_paths(tmp_path, stock_count=1)
    long_root = tmp_path
    for index in range(5):
        long_root = long_root / (f"研究輸出{index}-" + "x" * 38)
    long_root = long_root / "run"

    result = write_daily_market_technical_snapshot_v4_batch(
        output_root=long_root,
        cohort=_cohort(codes),
        source_clock=clock,
        finished_windows=windows,
    )

    assert result.status == "complete"
    assert result.artifact is not None
    assert len(str(result.artifact.manifest_path)) > 260
    assert result.artifact.repository_output_root == long_root
    reread = DailyMarketTechnicalSnapshotV4Repository(long_root).read_exact(
        result.artifact.manifest_path,
        expected_manifest_sha256=result.artifact.manifest_sha256,
    )
    assert reread == result.artifact
