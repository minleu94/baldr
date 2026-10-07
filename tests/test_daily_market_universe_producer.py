"""完整母體 producer 的 parent-writer、取消與續跑閉環。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import replace
from zoneinfo import ZoneInfo
from uuid import uuid4

import pytest

import app_module.rule_research_parent_capture as parent_module
import app_module.daily_market_universe_producer as producer_module
from app_module.daily_market_universe_producer import (
    DailyMarketUniverseProductionRequest,
    preflight_daily_market_universe_run,
    produce_daily_market_universe_run,
)
from app_module.daily_market_universe_run import (
    DailyMarketUniverseRunReader,
    verify_parent_capture_reference,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    SAFETY_RESERVE_BYTES,
)


_DECISION_DATE = date(2026, 7, 31)


def _seed_source(db_path: Path, stock_count: int) -> tuple[str, ...]:
    days = [_DECISION_DATE - timedelta(days=offset) for offset in reversed(range(65))]
    codes = tuple(f"{index + 1000:04d}" for index in range(stock_count))
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 開盤價 TEXT,
                最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER);
            CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, MA20 TEXT, MA60 TEXT);
            """
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            [
                (day.isoformat(), "BASE", "100", "105", "95", "101", 1000)
                for day in days
            ],
        )
        connection.execute(
            "INSERT INTO technical_indicators VALUES (?,?,?,?)",
            (_DECISION_DATE.isoformat(), "BASE", "99", "98"),
        )
        connection.execute("CREATE TEMP TABLE requested_codes(stock_code TEXT)")
        connection.executemany(
            "INSERT INTO requested_codes VALUES (?)", [(code,) for code in codes]
        )
        connection.execute(
            "INSERT INTO daily_prices "
            "SELECT p.日期, c.stock_code, p.開盤價, p.最高價, p.最低價, p.收盤價, p.成交股數 "
            "FROM daily_prices AS p CROSS JOIN requested_codes AS c "
            "WHERE p.證券代號='BASE'"
        )
        connection.execute(
            "INSERT INTO technical_indicators "
            "SELECT t.日期, c.stock_code, t.MA20, t.MA60 "
            "FROM technical_indicators AS t CROSS JOIN requested_codes AS c "
            "WHERE t.證券代號='BASE'"
        )
    return codes


def _short_output_root(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Path:
    qa_root = Path(__file__).resolve().parents[1] / "output" / "qa"
    scratch = qa_root / ("u" + uuid4().hex[:6])
    scratch.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    output_root = scratch / "d"
    jobs_root = scratch / "universe_jobs"
    generations_root = output_root / "generations"
    incomplete_root = output_root / ".incomplete"
    locks_root = output_root / ".locks"
    baseline_jobs = {item.name for item in jobs_root.iterdir()} if jobs_root.is_dir() else set()
    baseline_generations = (
        {item.name for item in generations_root.iterdir()}
        if generations_root.is_dir()
        else set()
    )
    baseline_incomplete = (
        {item.name for item in incomplete_root.iterdir()}
        if incomplete_root.is_dir()
        else set()
    )
    baseline_locks = {item.name for item in locks_root.iterdir()} if locks_root.is_dir() else set()

    def cleanup() -> None:
        for parent, baseline in (
            (jobs_root, baseline_jobs),
            (generations_root, baseline_generations),
            (incomplete_root, baseline_incomplete),
        ):
            if parent.is_dir():
                for item in parent.iterdir():
                    if item.name not in baseline:
                        shutil.rmtree(item, ignore_errors=True)
                try:
                    parent.rmdir()
                except OSError:
                    pass
        if locks_root.is_dir():
            for item in locks_root.iterdir():
                if item.name not in baseline_locks:
                    item.unlink(missing_ok=True)
            try:
                locks_root.rmdir()
            except OSError:
                pass
        for item in (output_root / "progress.json", output_root / ".locks"):
            if item.is_file():
                item.unlink(missing_ok=True)
        try:
            output_root.rmdir()
        except OSError:
            pass
        try:
            scratch.rmdir()
        except OSError:
            pass
    request.addfinalizer(cleanup)
    return output_root


def _request(
    db_path: Path,
    output_root: Path,
    codes: tuple[str, ...] | list[str],
    *,
    exclusions: dict[str, str] | None = None,
    cancel_callback=None,
) -> DailyMarketUniverseProductionRequest:
    return DailyMarketUniverseProductionRequest(
        db_path=db_path,
        universe_id="producer-integration-fixture",
        population_version="population-r1",
        raw_stock_codes=codes,
        excluded_stock_codes=exclusions or {},
        decision_date=_DECISION_DATE,
        decision_cutoff=datetime.combine(
            _DECISION_DATE, time(16), tzinfo=ZoneInfo("Asia/Taipei")
        ),
        contract_version="daily-market-feature-snapshot.v2",
        strategy_version="baldr-producer-test.v1",
        output_root=output_root,
        cancel_callback=cancel_callback,
    )


def _enable_real_parent_writers(
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    producer_failures: list[str] = []
    def capacity_probe(path: Path) -> dict[str, int | str]:
        return {
            "probe_path": str(path),
            "total_bytes": 10**12,
            "used_bytes": 0,
            "free_bytes": 10**12,
        }

    class ControlledSnapshotProducer(parent_module.DailyMarketSnapshotProducer):
        def __init__(self, root: Path):
            super().__init__(root, capacity_probe=capacity_probe)

        def produce(self, **kwargs):
            result = super().produce(**kwargs)
            if result.status not in {"published_complete", "published_partial", "unchanged"}:
                producer_failures.append(
                    f"{result.status}:{result.error_code}:{result.error_message}:"
                    f"{dict(result.source_errors)}"
                )
            return result

    monkeypatch.setattr(
        parent_module, "DailyMarketSnapshotProducer", ControlledSnapshotProducer
    )
    monkeypatch.setattr(
        BoundedRuleResearchCaptureWriter,
        "_free_bytes",
        lambda _self: SAFETY_RESERVE_BYTES * 4,
    )
    return producer_failures


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.mark.parametrize("population_size", (17, 257, 1000))
def test_real_parent_writer_produces_17_257_and_1000_member_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    population_size: int,
) -> None:
    producer_failures = _enable_real_parent_writers(monkeypatch)
    db_path = tmp_path / f"source-{population_size}.db"
    codes = _seed_source(db_path, population_size)
    output_root = _short_output_root(request, monkeypatch)
    source_hash_before = _sha256_file(db_path)
    source_mtime_before = db_path.stat().st_mtime_ns

    excluded: dict[str, str] = {}
    raw_codes: list[str] = list(codes)
    if population_size == 257:
        excluded = {f"X{index:04d}": "fixture exclusion" for index in range(300)}
        raw_codes.extend(excluded)
        raw_codes.extend((codes[0], "X0000"))
    run_request = _request(db_path, output_root, raw_codes, exclusions=excluded)

    result = produce_daily_market_universe_run(run_request)

    assert producer_failures == [], producer_failures
    assert result.status == "complete", (result.error_code, result.cause_code, result)
    assert result.error_code == ""
    assert result.manifest_path is not None and result.manifest_path.is_file()
    assert result.generation_identity_sha256 is not None
    expected_segments = (population_size + 255) // 256
    assert len(result.parent_references) == expected_segments
    assert result.counts["included_count"] == population_size
    assert result.counts["processed_count"] == population_size
    assert result.counts["pending_count"] == 0
    if population_size == 257:
        assert result.counts["excluded_count"] == 300
        assert result.counts["duplicate_stock_count"] == 2
        assert result.counts["duplicate_occurrence_count"] == 2
        assert result.counts["raw_stock_code_count"] == 559
    for reference in result.parent_references:
        descriptor = verify_parent_capture_reference(reference)
        assert descriptor["status"] == "complete"
        assert descriptor["readiness"]["status"] == "saved_verified_complete"
        assert len(descriptor["included_stock_codes"]) <= 256
        assert descriptor["readiness"]["batches_count"] <= 16

    with DailyMarketUniverseRunReader.open(
        output_root, result.generation_identity_sha256
    ) as reader:
        assert reader.counts["included_count"] == population_size
        assert reader.counts["processed_count"] == population_size
        assert reader.counts["excluded_count"] == len(excluded)
        assert reader.plan.strategy_version == "baldr-producer-test.v1"
        assert reader.plan.source_clock is not None
        assert reader.plan.source_clock.feature_contract_version == "daily-market-feature-snapshot.v2"
        assert reader.manifest["policy"]["source_availability"] == "unknown"
        page = reader.query(sort_key="stock_code", page=0, page_size=25)
        assert len(page.rows) == min(population_size + len(excluded), 25)
        assert page.total_count == population_size + len(excluded)

    assert db_path.stat().st_mtime_ns == source_mtime_before
    assert _sha256_file(db_path) == source_hash_before


def test_exclusion_only_population_publishes_without_parent_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    db_path = tmp_path / "source-exclusion-only.db"
    _seed_source(db_path, 0)
    output_root = _short_output_root(request, monkeypatch)
    exclusions = {f"X{index:04d}": "not in supported source" for index in range(300)}
    run_request = _request(db_path, output_root, list(exclusions), exclusions=exclusions)

    result = produce_daily_market_universe_run(run_request)

    assert result.status == "complete", (result.error_code, result.cause_code, result)
    assert result.parent_references == ()
    assert result.counts["included_count"] == 0
    assert result.counts["excluded_count"] == 300
    assert result.counts["processed_count"] == 0
    assert result.manifest_path is not None
    with DailyMarketUniverseRunReader.open(
        output_root, result.generation_identity_sha256 or ""
    ) as reader:
        assert reader.counts["excluded_count"] == 300
        assert reader.counts["processed_count"] == 0


def test_cancel_before_first_segment_saves_frozen_job_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    db_path = tmp_path / "source-cancel-before.db"
    codes = _seed_source(db_path, 17)
    output_root = _short_output_root(request, monkeypatch)
    run_request = _request(
        db_path, output_root, codes, cancel_callback=lambda: True
    )

    result = produce_daily_market_universe_run(run_request)

    assert result.status == "cancelled", (result.error_code, result.cause_code, result)
    assert result.error_code == "cancelled_before_first_segment"
    assert result.processed_segments == 0
    assert result.parent_references == ()
    assert result.manifest_path is None
    assert result.job_root is not None
    assert (result.job_root / "plan.json").is_file()
    assert (result.job_root / "progress.json").is_file()
    assert not (output_root / "generations" / (result.generation_identity_sha256 or "")).exists()


def test_mid_run_cancel_resumes_from_fresh_process_after_parent_is_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    _enable_real_parent_writers(monkeypatch)
    db_path = tmp_path / "source-fresh-process.db"
    codes = _seed_source(db_path, 17)
    output_root = _short_output_root(request, monkeypatch)
    cancel_state = {"requested": False}

    def progress(payload):
        if payload.get("event") == "segment_saved":
            cancel_state["requested"] = True

    run_request = _request(
        db_path,
        output_root,
        codes,
        cancel_callback=lambda: cancel_state["requested"],
    )
    first = produce_daily_market_universe_run(
        run_request, progress_callback=progress
    )
    assert first.status == "cancelled", first
    assert first.error_code in {"producer_cancelled", "run_cancelled"}
    assert first.processed_segments == 1
    assert len(first.parent_references) == 1
    assert first.manifest_path is None
    assert first.job_root is not None

    request_json = tmp_path / "fresh-process-request.json"
    request_json.write_text(
        json.dumps(
            {
                "db_path": str(db_path),
                "output_root": str(output_root),
                "universe_id": run_request.universe_id,
                "population_version": run_request.population_version,
                "raw_stock_codes": list(codes),
                "excluded_stock_codes": {},
                "decision_date": _DECISION_DATE.isoformat(),
                "decision_cutoff": run_request.decision_cutoff.isoformat(),
                "contract_version": run_request.contract_version,
                "strategy_version": run_request.strategy_version,
            }
        ),
        encoding="utf-8",
    )
    script = r'''
import json, sys
from datetime import date, datetime
from pathlib import Path
from app_module.daily_market_universe_producer import DailyMarketUniverseProductionRequest, resume_daily_market_universe_run
p = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
r = DailyMarketUniverseProductionRequest(
    db_path=p["db_path"], output_root=p["output_root"], universe_id=p["universe_id"],
    population_version=p["population_version"], raw_stock_codes=tuple(p["raw_stock_codes"]),
    excluded_stock_codes=p["excluded_stock_codes"], decision_date=date.fromisoformat(p["decision_date"]),
    decision_cutoff=datetime.fromisoformat(p["decision_cutoff"]), contract_version=p["contract_version"],
    strategy_version=p["strategy_version"])
result = resume_daily_market_universe_run(r)
print(json.dumps({"status": result.status, "error_code": result.error_code,
    "generation_identity_sha256": result.generation_identity_sha256,
    "manifest_path": str(result.manifest_path) if result.manifest_path else None,
    "processed_count": result.counts.get("processed_count", -1)}))
'''
    process = subprocess.run(
        [sys.executable, "-c", script, str(request_json)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert process.returncode == 0, process.stderr
    resumed = json.loads(process.stdout.strip().splitlines()[-1])
    assert resumed["status"] == "complete", resumed
    assert resumed["error_code"] == ""
    assert resumed["generation_identity_sha256"] == first.generation_identity_sha256
    assert resumed["processed_count"] == 17
    assert resumed["manifest_path"] is not None


def test_source_pin_drift_after_first_parent_leaves_incomplete_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    _enable_real_parent_writers(monkeypatch)
    db_path = tmp_path / "source-drift.db"
    codes = _seed_source(db_path, 257)
    output_root = _short_output_root(request, monkeypatch)
    mutated = {"done": False}

    def progress(payload):
        if payload.get("event") == "segment_saved" and not mutated["done"]:
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    "UPDATE daily_prices SET 收盤價='102' "
                    "WHERE 證券代號='BASE' AND 日期=?",
                    (_DECISION_DATE.isoformat(),),
                )
            mutated["done"] = True

    result = produce_daily_market_universe_run(
        _request(db_path, output_root, codes), progress_callback=progress
    )

    assert mutated["done"]
    assert result.status == "incomplete"
    assert result.error_code == "source_changed"
    assert result.counts["processed_count"] == 256
    assert result.manifest_path is None
    assert result.generation_identity_sha256 is not None
    assert not (
        output_root / "generations" / result.generation_identity_sha256
    ).exists()
    assert (output_root / ".incomplete" / result.generation_identity_sha256).is_dir()


def test_root_preflight_rejects_output_outside_existing_writer_guard(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "source-root-guard.db"
    codes = _seed_source(db_path, 1)
    unsupported = Path(__file__).resolve().parents[1] / "output" / "research_snapshots" / "daily_universe"
    run_request = _request(db_path, unsupported, codes)

    result = produce_daily_market_universe_run(run_request)

    assert result.status == "incomplete"
    assert result.step == "root_preflight"
    assert result.error_code == "root_preflight_failed"
    assert result.cause_code == "isolated_output_required"
    assert result.job_root is None
    assert not unsupported.exists()


def test_preflight_is_readonly_and_binds_db_revision_into_job_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    db_path = tmp_path / "source-preflight.db"
    codes = _seed_source(db_path, 1)
    output_root = _short_output_root(request, monkeypatch)
    before = (_sha256_file(db_path), db_path.stat().st_mtime_ns)

    preflight = preflight_daily_market_universe_run(
        _request(db_path, output_root, codes)
    )

    assert preflight.source_clock.source_binding["database"] == str(db_path.resolve())
    assert preflight.source_clock.source_binding["schema_identity_sha256"]
    assert len(preflight.input_identity_sha256) == 64
    assert preflight.job_root.name == preflight.input_identity_sha256[:24]
    assert not preflight.job_root.exists()
    assert (_sha256_file(db_path), db_path.stat().st_mtime_ns) == before


def test_short_job_directory_prefix_collision_fails_closed_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    db_path = tmp_path / "source-prefix-collision.db"
    codes = _seed_source(db_path, 1)
    output_root = _short_output_root(request, monkeypatch)
    monkeypatch.setattr(
        producer_module, "_job_directory_key", lambda _identity: "a" * 24
    )
    first_request = _request(
        db_path, output_root, codes, cancel_callback=lambda: True
    )
    first_preflight = preflight_daily_market_universe_run(first_request)
    first = produce_daily_market_universe_run(first_request)
    assert first.status == "cancelled"
    assert first.job_root is not None
    plan_path = first.job_root / "plan.json"
    original_plan = plan_path.read_bytes()

    colliding_request = replace(
        first_request, population_version="population-r2"
    )
    colliding_preflight = preflight_daily_market_universe_run(colliding_request)
    assert colliding_preflight.input_identity_sha256 != first_preflight.input_identity_sha256
    second = produce_daily_market_universe_run(colliding_request)

    assert second.status == "incomplete"
    assert second.error_code == "job_plan_invalid"
    assert second.job_root == first.job_root
    assert plan_path.read_bytes() == original_plan
    payload = json.loads(original_plan.decode("utf-8"))["payload"]
    assert payload["input_identity_sha256"] == first_preflight.input_identity_sha256
    assert payload["generation_identity_sha256"] == first.generation_identity_sha256
