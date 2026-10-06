"""真實 parent captures 到可重啟 full-population run 的保存閉環。"""

from __future__ import annotations

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
import tempfile
import threading
from zoneinfo import ZoneInfo

import pytest

import app_module.rule_research_parent_capture as parent_module
from app_module.daily_market_universe_run import (
    DailyMarketParentCaptureReference,
    DailyMarketUniverseRunCancelled,
    DailyMarketUniverseRunError,
    DailyMarketUniverseRunReader,
    create_daily_market_universe_run_writer,
    list_completed_runs,
    parent_source_clock_from_reference,
    plan_daily_market_universe_run,
    _required_relpath,
    _resolve_generation_child,
)
from app_module.rule_research_parent_capture import (
    PARENT_UNIVERSE_SCHEMA,
    produce_parent_rule_samples,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    SAFETY_RESERVE_BYTES,
)


def _seed_source(tmp_path: Path) -> tuple[Path, date]:
    db = tmp_path / "universe-source.db"
    days = [date(2026, 7, 1) + timedelta(days=offset) for offset in range(65)]
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 開盤價 TEXT,
                最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER);
            CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, MA20 TEXT, MA60 TEXT);
            """
        )
        for code in ("2382", "1477"):
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                [
                    (day.isoformat(), code, "100", "105", "95", "101", 1000)
                    for day in days
                ],
            )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?,?,?,?)",
                (days[-1].isoformat(), code, "99", "102"),
            )
    return db, days[-1]


def _capacity_probe():
    def probe(path: Path) -> dict[str, int | str]:
        return {
            "probe_path": str(path),
            "total_bytes": 10**12,
            "used_bytes": 0,
            "free_bytes": 10**12,
        }

    return probe


def _write_universe(
    path: Path,
    *,
    stock_codes: tuple[str, ...],
    decision_date: date,
    version: str = "population-r1",
) -> Path:
    payload = {
        "schema_version": PARENT_UNIVERSE_SCHEMA,
        "universe_id": "baldr-full-population-fixture",
        "version": version,
        "as_of_date": decision_date.isoformat(),
        "method": "daily-market-close-ma.v1",
        "scope": "bounded_multibatch_research_cohort",
        "included_stock_codes": list(stock_codes),
        "excluded_stock_codes": [],
        "population_count": len(stock_codes),
        "research_only": True,
        "complete_fixed_cohort": True,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _produce_parent(
    *,
    db: Path,
    snapshot_root: Path,
    capture_root: Path,
    universe_path: Path,
    stock_codes: tuple[str, ...],
    decision_date: date,
    version: str = "population-r1",
) -> DailyMarketParentCaptureReference:
    _write_universe(
        universe_path,
        stock_codes=stock_codes,
        decision_date=decision_date,
        version=version,
    )
    result = produce_parent_rule_samples(
        db_path=db,
        snapshot_root=snapshot_root,
        capture_root=capture_root,
        universe_path=universe_path,
        decision_cutoff=datetime.combine(
            decision_date, time(16), tzinfo=ZoneInfo("Asia/Taipei")
        ),
    )
    assert result["status"] == "complete", {
        "status": result.get("status"),
        "error_code": result.get("error_code"),
        "batch_errors": [
            {
                "batch_id": item.get("batch_id"),
                "status": item.get("status"),
                "error_code": item.get("error_code"),
                "production_status": item.get("production_status"),
                "sample_capture_status": item.get("sample_capture_status"),
            }
            for item in result.get("production", [])
            if item.get("error_code")
        ],
        "sample_status": result.get("sample_readiness_status"),
    }
    identity = result["parent_capture"]["receipt"]["capture_identity_sha256"]
    return DailyMarketParentCaptureReference(
        snapshot_root,
        capture_root,
        universe_path,
        identity,
    )


def _all_pages(reader: DailyMarketUniverseRunReader, *, sort_key: str, descending: bool = False):
    return tuple(
        row
        for page in range(3)
        for row in reader.query(
            sort_key=sort_key,
            descending=descending,
            page=page,
            page_size=200,
        ).rows
    )


@pytest.mark.parametrize(
    "value",
    (
        "D:outside.json",
        "D:/outside.json",
        "segments\\outside.json",
        "//server/share/outside.json",
        "segments/../outside.json",
    ),
)
def test_manifest_relative_paths_reject_windows_and_escape_syntax(
    tmp_path: Path, value: str
) -> None:
    with pytest.raises(DailyMarketUniverseRunError, match="projection_relpath_invalid"):
        _required_relpath(value, "projection_relpath")

    generation_root = tmp_path / "generation"
    generation_root.mkdir()
    safe_relative = "segments/segment-000001-projection.json"
    resolved = _resolve_generation_child(
        generation_root, safe_relative, "projection_relpath"
    )
    assert resolved == generation_root.resolve() / "segments" / "segment-000001-projection.json"
    assert resolved.is_relative_to(generation_root.resolve())
    assert _required_relpath(safe_relative, "projection_relpath") == safe_relative


def test_full_universe_cross_segment_save_cancel_retry_and_fresh_process_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    db, decision_date = _seed_source(tmp_path)
    codes = tuple(str(1000 + index) for index in range(257))
    missing_evidence_code = codes[-2]
    with sqlite3.connect(db) as connection:
        for code in codes:
            connection.execute(
                "INSERT INTO daily_prices "
                "SELECT 日期,?,開盤價,最高價,最低價,收盤價,成交股數 "
                "FROM daily_prices WHERE 證券代號='2382'",
                (code,),
            )
            if code != missing_evidence_code:
                connection.execute(
                    "INSERT INTO technical_indicators "
                    "SELECT 日期,?,MA20,MA60 FROM technical_indicators "
                    "WHERE 證券代號='2382'",
                    (code,),
                )
        special_prices = {codes[0]: ("9", "8", "10"), codes[-1]: ("100", "99", "101"), codes[111]: ("1000", "900", "1100")}
        for code, (close, ma20, ma60) in special_prices.items():
            connection.execute(
                "UPDATE daily_prices SET 開盤價=?,最高價=?,最低價=?,收盤價=? "
                "WHERE 證券代號=? AND 日期=?",
                (close, close, close, close, code, decision_date.isoformat()),
            )
            connection.execute(
                "UPDATE technical_indicators SET MA20=?,MA60=? "
                "WHERE 證券代號=? AND 日期=?",
                (ma20, ma60, code, decision_date.isoformat()),
            )

    class ControlledProducer(parent_module.DailyMarketSnapshotProducer):
        def __init__(self, root):
            super().__init__(root, capacity_probe=_capacity_probe())

    monkeypatch.setattr(parent_module, "DailyMarketSnapshotProducer", ControlledProducer)
    monkeypatch.setattr(
        BoundedRuleResearchCaptureWriter,
        "_free_bytes",
        lambda _self: SAFETY_RESERVE_BYTES * 4,
    )

    source_hash_before = hashlib.sha256(db.read_bytes()).hexdigest()
    source_stat_before = db.stat().st_mtime_ns
    short_parent_root = Path(tempfile.mkdtemp(prefix="baldr_universe_"))
    request.addfinalizer(lambda: shutil.rmtree(short_parent_root, ignore_errors=True))
    snapshot_root = short_parent_root / "snapshots"
    capture_root = short_parent_root / "captures"
    parent_zero = _produce_parent(
        db=db,
        snapshot_root=snapshot_root,
        capture_root=capture_root,
        universe_path=tmp_path / "universe-segment-0.json",
        stock_codes=codes[:256],
        decision_date=decision_date,
    )
    parent_one = _produce_parent(
        db=db,
        snapshot_root=snapshot_root,
        capture_root=capture_root,
        universe_path=tmp_path / "universe-segment-1.json",
        stock_codes=codes[256:],
        decision_date=decision_date,
    )
    source_clock = parent_source_clock_from_reference(parent_zero)
    assert parent_source_clock_from_reference(parent_one) == source_clock

    exclusions = {f"X{index:04d}": "fixture exclusion" for index in range(300)}
    raw_codes = [*codes, *exclusions, codes[0], "X0000"]
    cutoff = datetime.combine(
        decision_date, time(16), tzinfo=ZoneInfo("Asia/Taipei")
    )
    plan = plan_daily_market_universe_run(
        universe_id="baldr-full-population-fixture",
        population_version="population-r1",
        raw_stock_codes=raw_codes,
        excluded_stock_codes=exclusions,
        decision_date=decision_date,
        decision_cutoff=cutoff,
        strategy_version="strategy-v1",
        source_clock=source_clock,
    )
    assert [len(segment.declared_stock_codes) for segment in plan.segments] == [256, 256, 45]
    assert [len(segment.included_stock_codes) for segment in plan.segments] == [256, 1, 0]
    assert [len(segment.excluded_stock_codes) for segment in plan.segments] == [0, 255, 45]
    assert len(plan.excluded_stock_codes) == 300
    assert plan.duplicate_stock_codes == (("1000", 2), ("X0000", 2))

    wrong_version = _produce_parent(
        db=db,
        snapshot_root=snapshot_root,
        capture_root=capture_root,
        universe_path=tmp_path / "universe-wrong-version.json",
        stock_codes=(codes[-1],),
        decision_date=decision_date,
        version="population-r2",
    )
    wrong_date = _produce_parent(
        db=db,
        snapshot_root=snapshot_root,
        capture_root=capture_root,
        universe_path=tmp_path / "universe-wrong-date.json",
        stock_codes=(codes[-1],),
        decision_date=decision_date - timedelta(days=1),
    )
    other_db = tmp_path / "other-source.db"
    shutil.copy2(db, other_db)
    wrong_source = _produce_parent(
        db=other_db,
        snapshot_root=snapshot_root,
        capture_root=capture_root,
        universe_path=tmp_path / "universe-wrong-source.json",
        stock_codes=(codes[-1],),
        decision_date=decision_date,
    )

    output_root = short_parent_root / "runs"
    arrival_state = {"calls": 0}

    def cancel_after_projected_parent_arrives() -> bool:
        arrival_state["calls"] += 1
        return arrival_state["calls"] >= 3

    with create_daily_market_universe_run_writer(
        output_root, plan, cancel_callback=cancel_after_projected_parent_arrives
    ) as arrival_writer:
        with pytest.raises(DailyMarketUniverseRunCancelled, match="run_cancelled"):
            arrival_writer.append_parent_segment(0, parent_zero)
        assert arrival_writer.progress["counts"]["processed_count"] == 0
    assert not list((output_root / ".incomplete" / plan.generation_identity_sha256).glob("segments/*.json"))

    cancel_state = {"armed": False, "calls": 0, "cancel_on": 4}

    def cancel_after_receipt_is_staged() -> bool:
        if not cancel_state["armed"]:
            return False
        cancel_state["calls"] += 1
        return cancel_state["calls"] >= cancel_state["cancel_on"]

    with create_daily_market_universe_run_writer(
        output_root, plan, cancel_callback=cancel_after_receipt_is_staged
    ) as writer:
        with pytest.raises(DailyMarketUniverseRunError, match="parent_population_version_mismatch"):
            writer.append_parent_segment(1, wrong_version)
        with pytest.raises(DailyMarketUniverseRunError, match="parent_decision_date_mismatch"):
            writer.append_parent_segment(1, wrong_date)
        with pytest.raises(DailyMarketUniverseRunError, match="parent_source_clock_mismatch"):
            writer.append_parent_segment(1, wrong_source)
        with pytest.raises(DailyMarketUniverseRunError, match="parent_segment_membership_mismatch"):
            writer.append_parent_segment(1, parent_zero)
        writer.append_parent_segment(0, parent_zero)
        writer.append_parent_segment(1, parent_one)
        cancel_state["armed"] = True
        with pytest.raises(DailyMarketUniverseRunCancelled, match="run_cancelled"):
            writer.finalize()

    staging_root = output_root / ".incomplete" / plan.generation_identity_sha256
    assert (staging_root / "index.sqlite").is_file()
    assert (staging_root / "manifest.json").is_file()
    assert (staging_root / "complete.json").is_file()
    assert not (output_root / "generations" / plan.generation_identity_sha256).exists()

    publication_root = output_root / "generations" / plan.generation_identity_sha256
    with create_daily_market_universe_run_writer(output_root, plan) as gate_writer:
        final_check_reached = threading.Event()
        resume_finalize = threading.Event()
        original_check_cancelled = gate_writer._check_cancelled
        final_check_calls = {"count": 0}

        def pause_at_publication_check() -> None:
            final_check_calls["count"] += 1
            original_check_cancelled()
            if final_check_calls["count"] == 4:
                final_check_reached.set()
                if not resume_finalize.wait(timeout=30):
                    raise AssertionError("test did not release finalize publication check")

        monkeypatch.setattr(gate_writer, "_check_cancelled", pause_at_publication_check)
        finalize_errors = []
        cancel_errors = []

        def finalize_in_thread() -> None:
            try:
                gate_writer.finalize()
            except BaseException as exc:  # capture worker-thread assertion below
                finalize_errors.append(exc)

        def cancel_in_thread() -> None:
            try:
                gate_writer.cancel()
            except BaseException as exc:  # capture worker-thread assertion below
                cancel_errors.append(exc)

        finalizer = threading.Thread(target=finalize_in_thread, name="universe-finalize")
        finalizer.start()
        assert final_check_reached.wait(timeout=30)
        canceller = threading.Thread(target=cancel_in_thread, name="universe-cancel")
        canceller.start()
        try:
            # cancel sets the event under the publication gate before it waits
            # on the writer mutex held by finalize.
            assert gate_writer._cancel_event.wait(timeout=10)
        finally:
            resume_finalize.set()
            finalizer.join(timeout=30)
            canceller.join(timeout=30)
        assert not finalizer.is_alive()
        assert not canceller.is_alive()
        assert len(finalize_errors) == 1
        assert isinstance(finalize_errors[0], DailyMarketUniverseRunCancelled)
        assert cancel_errors == []
        assert not publication_root.exists()

    with create_daily_market_universe_run_writer(output_root, plan) as retry:
        descriptor = retry.finalize()
        with pytest.raises(DailyMarketUniverseRunError, match="generation_already_published"):
            retry.cancel()
        assert not retry._cancel_event.is_set()
    assert descriptor.status == "complete"
    assert descriptor.feature_contract_version == source_clock.feature_contract_version
    assert descriptor.strategy_version == "strategy-v1"
    assert db.stat().st_mtime_ns == source_stat_before
    assert hashlib.sha256(db.read_bytes()).hexdigest() == source_hash_before

    listing = list_completed_runs(output_root, limit=8)
    assert not listing.has_more
    assert len(listing.items) == 1
    assert listing.items[0].status == "complete"
    assert listing.items[0].generation_identity_sha256 == plan.generation_identity_sha256
    listed_counts = listing.items[0].counts or {}
    assert listed_counts["excluded_count"] == 300
    assert listed_counts["duplicate_stock_count"] == 2

    with DailyMarketUniverseRunReader.open(output_root, plan.generation_identity_sha256) as reader:
        assert reader.counts["declared_unique_count"] == 557
        assert reader.counts["raw_stock_code_count"] == 559
        assert reader.counts["duplicate_stock_count"] == 2
        assert reader.counts["duplicate_occurrence_count"] == 2
        assert reader.counts["included_count"] == 257
        assert reader.counts["excluded_count"] == 300
        assert reader.counts["processed_count"] == 257
        assert reader.counts["pending_count"] == 0
        assert reader.counts["unknown_evidence_stock_count"] >= 1
        assert reader.counts["missing_data_stock_count"] >= 1
        assert reader.manifest["data_completeness"] == "partial_research"

        codes_by_stock = _all_pages(reader, sort_key="stock_code")
        assert tuple(row["stock_code"] for row in codes_by_stock) == plan.declared_stock_codes
        assert sum(row["included"] is False for row in codes_by_stock) == 300
        missing_row = next(row for row in codes_by_stock if row["stock_code"] == missing_evidence_code)
        assert missing_row["snapshot_missing"] is False
        assert missing_row["conditions"]["close_above_ma20"]["state"] == "unknown"
        assert {
            "stock_code", "data_date", "close", "ma20", "ma60", "bbands30_upper",
            "conditions", "combined_state", "why", "why_not", "source_refs",
            "snapshot_missing", "source_snapshot_id", "source_snapshot_sha256",
            "parent_capture_identity_sha256", "included", "excluded_reason", "processed",
        } <= set(missing_row)
        descriptor_source = reader.source_descriptor
        assert descriptor_source["generation_identity_sha256"] == plan.generation_identity_sha256
        source_clock_descriptor = descriptor_source["source_clock"]
        assert source_clock_descriptor["decision_cutoff"] == cutoff.isoformat()
        assert source_clock_descriptor["source_binding"]["database"] == str(db.resolve())
        assert source_clock_descriptor["source_binding"]["schema_identity_sha256"]
        assert source_clock_descriptor["source_binding"]["revision_pin"]

        for descending in (False, True):
            sorted_rows = _all_pages(reader, sort_key="close", descending=descending)
            known = [row for row in sorted_rows if row["close"] is not None]
            null_rows = [row for row in sorted_rows if row["close"] is None]
            numbers = [Decimal(row["close"]) for row in known]
            assert numbers == sorted(numbers, reverse=descending)
            assert [row["stock_code"] for row in null_rows] == sorted(
                row["stock_code"] for row in null_rows
            )
            for value in {Decimal(row["close"]) for row in known}:
                tied_codes = [
                    row["stock_code"] for row in known if Decimal(row["close"]) == value
                ]
                assert tied_codes == sorted(tied_codes)
        ascending = _all_pages(reader, sort_key="close")
        assert [ascending[index]["stock_code"] for index in (0, 1, 2)] == [
            codes[0], codes[-1], "1001"
        ]

    script = (
        "from app_module.daily_market_universe_run import DailyMarketUniverseRunReader; "
        "import json,os,sys; "
        "r=DailyMarketUniverseRunReader.open(sys.argv[1],sys.argv[2]); "
        "p=r.query(sort_key='close',page=0,page_size=3); "
        "print(json.dumps({'pid':os.getpid(),'counts':dict(r.counts),'rows':list(p.rows)},ensure_ascii=False)); "
        "r.close()"
    )
    fresh = subprocess.run(
        [sys.executable, "-c", script, str(output_root), plan.generation_identity_sha256],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert fresh.returncode == 0, fresh.stderr
    fresh_payload = json.loads(fresh.stdout)
    assert fresh_payload["pid"] != os.getpid()
    assert fresh_payload["counts"]["declared_unique_count"] == 557
    assert [row["stock_code"] for row in fresh_payload["rows"]] == [
        codes[0], codes[-1], "1001"
    ]

    manifest = json.loads((descriptor.output_path / "manifest.json").read_text(encoding="utf-8"))
    projection_item = next(item for item in manifest["segments"] if item["status"] == "processed")
    projection_path = descriptor.output_path / projection_item["projection_relpath"]
    saved_projection = projection_path.read_bytes()
    projection_path.write_bytes(saved_projection + b" ")
    try:
        with pytest.raises(DailyMarketUniverseRunError, match="segment_projection_hash_mismatch"):
            DailyMarketUniverseRunReader.open(output_root, plan.generation_identity_sha256)
    finally:
        projection_path.write_bytes(saved_projection)
