from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, time
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time as time_module
from typing import Any, Iterator
import uuid

import pytest
import psutil

import app_module.daily_market_snapshot_producer as snapshot_producer_module
from app_module.daily_market_snapshot_producer import DailyMarketSnapshotProducer
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
from app_module.original_stock_ranking import (
    OriginalStockRankingError,
    OriginalStockRankingPublisher,
    OriginalStockRankingRepository,
)
from test_original_stock_ranking import (
    COHORT_ID,
    DECISION_DATE,
    STOCK_CODES,
    TAIPEI,
    _create_database,
    _ranking_pointer,
    _revise_source,
    _universe_payload,
    _usage,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHILD_QA_DIR = _REPO_ROOT / "output" / "qa" / "ux19_storage_recovery_20261005" / "children"


def _new_child_marker(kind: str, stage: str) -> Path:
    _CHILD_QA_DIR.mkdir(parents=True, exist_ok=True)
    return _CHILD_QA_DIR / f"{kind}-{stage}-{uuid.uuid4().hex}.marker.json"


@pytest.fixture
def publication_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import app_module.daily_market_snapshot_producer as producer_module
    from app_module.daily_market_research_universe import load_research_universe_spec
    from data_module import ml_storage_capacity

    monkeypatch.setattr(producer_module, "resolve_heavy_chain_safety_reserve", lambda _value: 1)
    monkeypatch.setattr(ml_storage_capacity, "filesystem_usage", _usage)

    config_path = tmp_path / "universe.json"
    config_path.write_bytes(
        __import__("json").dumps(
            _universe_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    spec = load_research_universe_spec(config_path)
    db_path = tmp_path / "market.sqlite"
    _create_database(db_path)
    snapshot_root = tmp_path / "feature-snapshots"
    ranking_root = tmp_path / "rankings"
    case = {
        "config_path": config_path,
        "db_path": db_path,
        "snapshot_root": snapshot_root,
        "ranking_root": ranking_root,
        "spec": spec,
    }
    snapshot = _produce_snapshot(case, hour=15)
    case["snapshot"] = snapshot
    return case


def _produce_snapshot(case: dict[str, Any], *, hour: int, minute: int = 0):
    result = _run_snapshot(case, hour=hour, minute=minute)
    assert result.status in {"published_complete", "unchanged"}, result.to_dict()
    return DailyMarketSnapshotRepository(case["snapshot_root"]).load_latest(
        COHORT_ID, DECISION_DATE
    )


def _run_snapshot(
    case: dict[str, Any],
    *,
    hour: int,
    minute: int = 0,
    capacity_probe=_usage,
    failed_stock_code: str | None = None,
):
    from app_module.daily_market_research_universe import load_research_universe_spec
    from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput

    spec = load_research_universe_spec(case["config_path"])
    with SQLiteDailyMarketSnapshotSource(case["db_path"], DECISION_DATE) as source:
        inputs: dict[str, DailyMarketSnapshotInput] = {}
        for code in STOCK_CODES:
            points, technical, scope_identity, refs = source.load(code)
            inputs[code] = DailyMarketSnapshotInput(
                stock_code=code,
                scope_identity=scope_identity,
                price_points=points,
                technical=technical,
                source_refs=refs,
            )

    producer = DailyMarketSnapshotProducer(
        case["snapshot_root"],
        capacity_probe=capacity_probe,
        reserve_bytes=1,
        clock=lambda: datetime(2026, 10, 5, 16, 0, tzinfo=TAIPEI),
    )

    def load_input(code: str, _requested_date):
        if code == failed_stock_code:
            raise OSError("injected source batch failure")
        return inputs[code]

    return producer.produce(
        cohort_id=COHORT_ID,
        decision_cutoff=datetime.combine(
            DECISION_DATE, time(hour, minute), tzinfo=TAIPEI
        ),
        stock_codes=STOCK_CODES,
        source_loader=load_input,
        research_universe=spec,
    )


def test_rank_publisher_preserves_competing_pointer_after_initial_absence(
    publication_case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """重現發布者先觀察到 pointer 缺席、另一 writer 隨後提交的競爭。"""
    case = publication_case
    original_snapshot = case["snapshot"]
    competing_snapshot = _produce_snapshot(case, hour=14, minute=30)
    assert competing_snapshot.manifest_sha256 != original_snapshot.manifest_sha256
    competing = OriginalStockRankingPublisher(
        case["snapshot_root"], ranking_root=case["ranking_root"]
    ).publish(
        competing_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    )
    assert competing["status"] == "published"

    seed_root = case["ranking_root"]
    pointer_path = _ranking_pointer(case, "day", "strong")
    competing_pointer = pointer_path.read_bytes()
    race_root = seed_root.parent / "rankings-race"
    race_root.mkdir()
    for immutable_folder in ("objects", "manifests"):
        shutil.copytree(seed_root / immutable_folder, race_root / immutable_folder)
    race_case = {**case, "ranking_root": race_root}
    pointer_path = _ranking_pointer(race_case, "day", "strong")
    real_lock = snapshot_producer_module._producer_lock

    @contextmanager
    def interleave_competing_writer(root: Path) -> Iterator[bool]:
        if root.resolve() == race_root.resolve():
            pointer_path.write_bytes(competing_pointer)
            yield True
            return
        with real_lock(root) as acquired:
            yield acquired

    monkeypatch.setattr(
        snapshot_producer_module, "_producer_lock", interleave_competing_writer
    )
    stale = OriginalStockRankingPublisher(
        case["snapshot_root"], ranking_root=race_root
    ).publish(
        original_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    )

    assert stale["status"] == "unavailable"
    assert stale["code"] == "ranking_pointer_changed_during_publish"
    assert pointer_path.read_bytes() == competing_pointer


_SNAPSHOT_CHILD = textwrap.dedent(
    r"""
    from datetime import date, datetime, time
    import json
    import os
    from pathlib import Path
    import sys
    import time as time_module
    from zoneinfo import ZoneInfo

    from app_module.daily_market_research_universe import load_research_universe_spec
    import app_module.daily_market_snapshot_producer as producer_module
    from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput, DailyMarketSnapshotProducer
    from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource

    root, db_path, config_path = map(Path, sys.argv[1:4])
    stage = sys.argv[4]
    marker = Path(sys.argv[5])
    decision_date = date(2026, 10, 5)
    codes = ("1101", "2317", "2330")
    taipei = ZoneInfo("Asia/Taipei")

    def pause(boundary):
        marker.write_text(
            json.dumps({"stage": stage, "pid": os.getpid(), "boundary": boundary}),
            encoding="utf-8",
        )
        while True:
            time_module.sleep(0.05)

    original_replace = os.replace

    def controlled_replace(source, destination):
        target = Path(destination)
        kind, boundary = stage.rsplit("_", 1)
        matches = (
            (kind == "objects" and "objects" in target.parts)
            or (kind == "manifests" and "manifests" in target.parts)
            or (kind == "latest" and target == root / "latest.json")
        )
        if matches:
            if boundary == "after":
                original_replace(source, destination)
            pause(boundary)
        return original_replace(source, destination)

    producer_module.os.replace = controlled_replace
    with SQLiteDailyMarketSnapshotSource(db_path, decision_date) as source:
        inputs = {}
        for code in codes:
            points, technical, scope_identity, refs = source.load(code)
            inputs[code] = DailyMarketSnapshotInput(
                stock_code=code,
                scope_identity=scope_identity,
                price_points=points,
                technical=technical,
                source_refs=refs,
            )

    total = 600 * 1024**3
    free = 300 * 1024**3
    result = DailyMarketSnapshotProducer(
        root,
        capacity_probe=lambda path: {
            "probe_path": str(path),
            "total_bytes": total,
            "used_bytes": total - free,
            "free_bytes": free,
        },
        clock=lambda: datetime(2026, 10, 5, 16, 0, tzinfo=taipei),
    ).produce(
        cohort_id="original-rank-test-universe",
        decision_cutoff=datetime.combine(decision_date, time(15, 0), tzinfo=taipei),
        stock_codes=codes,
        source_loader=lambda code, _requested_date: inputs[code],
        research_universe=load_research_universe_spec(config_path),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False), flush=True)
    """
)


_RANKING_CHILD = textwrap.dedent(
    r"""
    from datetime import date
    import json
    import os
    from pathlib import Path
    import sys
    import time as time_module

    from data_module import ml_storage_capacity
    from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
    import app_module.original_stock_ranking as ranking_module
    from app_module.original_stock_ranking import OriginalStockRankingPublisher

    snapshot_root, ranking_root, db_path = map(Path, sys.argv[1:4])
    stage = sys.argv[4]
    marker = Path(sys.argv[5])
    decision_date = date(2026, 10, 5)
    snapshot = DailyMarketSnapshotRepository(snapshot_root).load_latest(
        "original-rank-test-universe", decision_date
    )

    def pause(boundary):
        marker.write_text(
            json.dumps({"stage": stage, "pid": os.getpid(), "boundary": boundary}),
            encoding="utf-8",
        )
        while True:
            time_module.sleep(0.05)

    original_link = os.link
    original_replace = os.replace

    def controlled_link(source, destination, *args, **kwargs):
        target = Path(destination)
        kind, boundary = stage.rsplit("_", 1)
        matches = (kind in {"objects", "manifests"} and kind in target.parts)
        if matches:
            if boundary == "after":
                original_link(source, destination, *args, **kwargs)
            pause(boundary)
        return original_link(source, destination, *args, **kwargs)

    def controlled_replace(source, destination):
        target = Path(destination)
        kind, boundary = stage.rsplit("_", 1)
        if kind == "pointer" and target == ranking_root / "latest-day-strong.json":
            if boundary == "after":
                original_replace(source, destination)
            pause(boundary)
        return original_replace(source, destination)

    ranking_module.os.link = controlled_link
    ranking_module.os.replace = controlled_replace
    total = 600 * 1024**3
    free = 300 * 1024**3
    ml_storage_capacity.filesystem_usage = lambda path: {
        "probe_path": str(path),
        "total_bytes": total,
        "used_bytes": total - free,
        "free_bytes": free,
    }
    result = OriginalStockRankingPublisher(
        snapshot_root, ranking_root=ranking_root
    ).publish(snapshot, db_path=db_path, period="day", direction="strong")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    """
)


def _start_paused_child(
    script: str, args: tuple[str, ...], marker: Path
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [sys.executable, "-c", script, *args],
        cwd=_REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time_module.monotonic() + 20
    while time_module.monotonic() < deadline:
        if marker.exists():
            return process
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"子程序未抵達故障點：exit={process.returncode}\n{stdout}\n{stderr}"
            )
        time_module.sleep(0.02)
    process.terminate()
    stdout, stderr = process.communicate(timeout=10)
    raise AssertionError(f"子程序故障點逾時\n{stdout}\n{stderr}")


def _terminate_owned_child(process: subprocess.Popen[str], marker: Path) -> dict[str, Any]:
    marker_data = json.loads(marker.read_text(encoding="utf-8"))
    child_pid = int(marker_data["pid"])
    worker = psutil.Process(child_pid)
    command_line = worker.cmdline()
    parent_pids = {parent.pid for parent in worker.parents()}
    marker_in_command = str(marker) in command_line or str(marker.resolve()) in command_line
    assert process.pid in parent_pids or marker_in_command, (
        f"marker PID {child_pid} 無法證明屬於本次 launcher PID {process.pid}"
    )

    worker.kill()
    child_returncode = worker.wait(timeout=10)
    try:
        stdout, stderr = process.communicate(timeout=10)
        launcher_termination_requested = False
    except subprocess.TimeoutExpired:
        process.terminate()
        stdout, stderr = process.communicate(timeout=10)
        launcher_termination_requested = True
    assert process.returncode is not None, f"launcher 未結束：{stdout}\n{stderr}"
    receipt_path = marker.with_name(marker.name.replace(".marker.json", ".termination.json"))
    receipt = {
        **marker_data,
        "child_pid": child_pid,
        "child_returncode": child_returncode,
        "launcher_pid": process.pid,
        "launcher_returncode": process.returncode,
        "launcher_termination_requested": launcher_termination_requested,
        "only_owned_child_terminated": True,
        "recovery_reader_pid": os.getpid(),
    }
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return receipt


@pytest.mark.parametrize(
    ("stage", "pointer_advanced"),
    [
        ("objects_after", False),
        ("manifests_after", False),
        ("latest_before", False),
        ("latest_after", True),
    ],
)
def test_snapshot_child_termination_keeps_atomic_publication_and_retry(
    publication_case: dict[str, Any],
    stage: str,
    pointer_advanced: bool,
) -> None:
    case = publication_case
    repository = DailyMarketSnapshotRepository(case["snapshot_root"])
    old_snapshot = case["snapshot"]
    old_pointer = (case["snapshot_root"] / "latest.json").read_bytes()
    _revise_source(case)
    marker = _new_child_marker("snapshot", stage)
    child = _start_paused_child(
        _SNAPSHOT_CHILD,
        (
            str(case["snapshot_root"]),
            str(case["db_path"]),
            str(case["config_path"]),
            stage,
            str(marker),
        ),
        marker,
    )
    try:
        busy = _run_snapshot(case, hour=15)
        assert busy.status == "busy"
    finally:
        termination = _terminate_owned_child(child, marker)
    assert termination["stage"] == stage
    assert termination["boundary"] == stage.rsplit("_", 1)[-1]
    assert termination["only_owned_child_terminated"] is True

    visible = repository.load_latest(COHORT_ID, DECISION_DATE)
    if pointer_advanced:
        assert visible.manifest_sha256 != old_snapshot.manifest_sha256
        assert (case["snapshot_root"] / "latest.json").read_bytes() != old_pointer
    else:
        assert visible.manifest_sha256 == old_snapshot.manifest_sha256
        assert (case["snapshot_root"] / "latest.json").read_bytes() == old_pointer

    pinned_old = repository.load_manifest(
        old_snapshot.manifest_sha256, COHORT_ID, DECISION_DATE
    )
    assert pinned_old.manifest_sha256 == old_snapshot.manifest_sha256
    retry = _run_snapshot(case, hour=15)
    assert retry.status == ("unchanged" if pointer_advanced else "published_complete")
    assert repository.load_latest(COHORT_ID, DECISION_DATE).manifest_sha256 != old_snapshot.manifest_sha256
    assert repository.load_manifest(
        old_snapshot.manifest_sha256, COHORT_ID, DECISION_DATE
    ).manifest_sha256 == old_snapshot.manifest_sha256


@pytest.mark.parametrize(
    ("stage", "pointer_advanced"),
    [
        ("objects_after", False),
        ("manifests_after", False),
        ("pointer_before", False),
        ("pointer_after", True),
    ],
)
def test_rank_child_termination_keeps_atomic_publication_and_retry(
    publication_case: dict[str, Any],
    stage: str,
    pointer_advanced: bool,
) -> None:
    case = publication_case
    old_snapshot = case["snapshot"]
    old_published = OriginalStockRankingPublisher(
        case["snapshot_root"], ranking_root=case["ranking_root"]
    ).publish(
        old_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    )
    assert old_published["status"] == "published"
    old_pointer_path = _ranking_pointer(case, "day", "strong")
    old_pointer = old_pointer_path.read_bytes()
    new_snapshot = _produce_snapshot(case, hour=14, minute=30)
    marker = _new_child_marker("ranking", stage)
    child = _start_paused_child(
        _RANKING_CHILD,
        (
            str(case["snapshot_root"]),
            str(case["ranking_root"]),
            str(case["db_path"]),
            stage,
            str(marker),
        ),
        marker,
    )
    try:
        busy = OriginalStockRankingPublisher(
            case["snapshot_root"], ranking_root=case["ranking_root"]
        ).publish(
            new_snapshot,
            db_path=case["db_path"],
            period="day",
            direction="strong",
        )
        if pointer_advanced:
            assert busy["status"] == "unchanged"
        else:
            assert busy["status"] == "unavailable"
            assert busy["code"] == "ranking_publish_busy"
    finally:
        termination = _terminate_owned_child(child, marker)
    assert termination["stage"] == stage
    assert termination["boundary"] == stage.rsplit("_", 1)[-1]
    assert termination["only_owned_child_terminated"] is True

    repository = OriginalStockRankingRepository(
        case["snapshot_root"], ranking_root=case["ranking_root"]
    )
    if pointer_advanced:
        assert old_pointer_path.read_bytes() != old_pointer
        assert repository.read(
            new_snapshot,
            db_path=case["db_path"],
            period="day",
            direction="strong",
        ).metadata["parent_manifest_sha256"] == new_snapshot.manifest_sha256
        with pytest.raises(OriginalStockRankingError):
            repository.read(
                old_snapshot,
                db_path=case["db_path"],
                period="day",
                direction="strong",
            )
    else:
        assert old_pointer_path.read_bytes() == old_pointer
        assert repository.read(
            old_snapshot,
            db_path=case["db_path"],
            period="day",
            direction="strong",
        ).metadata["parent_manifest_sha256"] == old_snapshot.manifest_sha256

    pinned_old = repository.read_pinned(
        old_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
        manifest_sha256=old_published["manifest_sha256"],
        manifest_identity_sha256=old_published["manifest_identity_sha256"],
    )
    assert pinned_old.manifest_sha256 == old_published["manifest_sha256"]
    retried = OriginalStockRankingPublisher(
        case["snapshot_root"], ranking_root=case["ranking_root"]
    ).publish(
        new_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    )
    assert retried["status"] == ("unchanged" if pointer_advanced else "published")
    assert repository.read(
        new_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    ).metadata["parent_manifest_sha256"] == new_snapshot.manifest_sha256
    assert repository.read_pinned(
        old_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
        manifest_sha256=old_published["manifest_sha256"],
        manifest_identity_sha256=old_published["manifest_identity_sha256"],
    ).manifest_sha256 == old_published["manifest_sha256"]


def test_partial_snapshot_batch_and_capacity_rejection_keep_old_pointer(
    publication_case: dict[str, Any],
) -> None:
    case = publication_case
    pointer_path = case["snapshot_root"] / "latest.json"
    original_pointer = pointer_path.read_bytes()
    failed = _run_snapshot(
        case, hour=15, failed_stock_code=STOCK_CODES[-1]
    )
    assert failed.status == "source_unavailable"
    assert pointer_path.read_bytes() == original_pointer
    assert DailyMarketSnapshotRepository(case["snapshot_root"]).load_latest(
        COHORT_ID, DECISION_DATE
    ).manifest_sha256 == case["snapshot"].manifest_sha256

    _revise_source(case)
    capacity_blocked = _run_snapshot(
        case,
        hour=15,
        capacity_probe=lambda path: _usage(path, free=0),
    )
    assert capacity_blocked.status == "capacity_blocked"
    assert pointer_path.read_bytes() == original_pointer
    assert DailyMarketSnapshotRepository(case["snapshot_root"]).load_latest(
        COHORT_ID, DECISION_DATE
    ).manifest_sha256 == case["snapshot"].manifest_sha256


def test_rank_capacity_and_engine_failure_keep_old_pointer(
    publication_case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    case = publication_case
    old_snapshot = case["snapshot"]
    publisher = OriginalStockRankingPublisher(
        case["snapshot_root"], ranking_root=case["ranking_root"]
    )
    old_result = publisher.publish(
        old_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    )
    assert old_result["status"] == "published"
    pointer_path = _ranking_pointer(case, "day", "strong")
    old_pointer = pointer_path.read_bytes()
    new_snapshot = _produce_snapshot(case, hour=14, minute=30)

    from data_module import ml_storage_capacity

    monkeypatch.setattr(
        ml_storage_capacity,
        "filesystem_usage",
        lambda path: _usage(path, free=0),
    )
    capacity_blocked = publisher.publish(
        new_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    )
    assert capacity_blocked["status"] == "unavailable"
    assert capacity_blocked["code"] == "ranking_capacity_blocked"
    assert pointer_path.read_bytes() == old_pointer

    monkeypatch.setattr(ml_storage_capacity, "filesystem_usage", _usage)
    from decision_module.stock_screener import StockScreener

    def fail_engine(*_args, **_kwargs):
        raise RuntimeError("injected partial rank batch failure")

    monkeypatch.setattr(StockScreener, "_build_stock_screen_from_frame", fail_engine)
    failed = publisher.publish(
        new_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    )
    assert failed["status"] == "unavailable"
    assert failed["code"] == "ranking_engine_failed"
    assert pointer_path.read_bytes() == old_pointer
    assert OriginalStockRankingRepository(
        case["snapshot_root"], ranking_root=case["ranking_root"]
    ).read(
        old_snapshot,
        db_path=case["db_path"],
        period="day",
        direction="strong",
    ).manifest_sha256 == old_result["manifest_sha256"]
