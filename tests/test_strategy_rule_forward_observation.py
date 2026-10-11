"""在短暫來源 DB 上走真 v4 source→writer→public reader→正式觀察 API。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Context, Inexact, localcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app_module.daily_market_technical_read_session import DailyMarketTechnicalReadSession
from app_module.daily_market_technical_snapshot_v4_producer import (
    write_daily_market_technical_snapshot_v4_batch,
)
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import (
    BoundedDailyMarketTechnicalParentCaptureWriterV4,
    DailyMarketTechnicalCohortV4,
    build_daily_market_technical_parent_plan_v4,
    read_daily_market_technical_parent_capture_v4,
)
from app_module.strategy_rule_forward_observation import (
    StrategySignalObservationError,
    read_exact_forward_signal_observation,
    write_forward_signal_observation_from_exact_parent,
)


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_DATE = date(2026, 10, 6)
START_DATE = DECISION_DATE - timedelta(days=39)


@pytest.fixture
def short_temp() -> Any:
    base = REPO / ".t"
    base.mkdir(parents=True, exist_ok=True)
    base = base.resolve(strict=True)
    directory = Path(__import__("tempfile").mkdtemp(prefix="p8formal-", dir=base)).resolve(strict=True)
    try:
        yield directory
    finally:
        if directory.parent != base:
            raise AssertionError("p08_forward_fixture_path_escape")
        cleanup = "\\\\?\\" + str(directory) if os.name == "nt" else str(directory)
        shutil.rmtree(cleanup)


def _write_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            for stock_code in ("2382", "2330"):
                for offset in range(40):
                    close = 120 if stock_code == "2382" and offset == 39 else 100
                    day = START_DATE + timedelta(days=offset)
                    rows.append((day.isoformat(), stock_code, str(close), str(close + 1),
                                 str(close - 1), str(close), 1000 + offset))
            # 2330 有 source row，但 39 筆低於最高 row；以新鮮、足量 unknown
            # 的缺件案例改為整股 40 筆均為 SQL NULL OHLCV，由既有 validator 留 unknown。
            rows = [
                (day, code, ("" if code == "2330" else op),
                 ("" if code == "2330" else high), ("" if code == "2330" else low),
                 ("" if code == "2330" else close), volume)
                for day, code, op, high, low, close, volume in rows
            ]
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        connection.close()


def _make_parent(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    database = root / "prices.sqlite"
    _write_source(database)
    codes = ("2330", "2382")
    cutoff = datetime.combine(DECISION_DATE, time(16, 0), tzinfo=TAIPEI)
    with DailyMarketTechnicalReadSession(database, cutoff) as session:
        clock = session.clock
        session.load_batch(codes)
        windows = session.finish()
    cohort = DailyMarketTechnicalCohortV4.create(
        universe_id="p08-forward-fixture",
        population_version="fixture-2026-10-06-v1",
        decision_date=DECISION_DATE,
        included_stock_codes=codes,
    )
    plan = build_daily_market_technical_parent_plan_v4(
        cohort, source_clock=clock, finished_windows=windows
    )
    scope = ResearchCaptureWriteScope(root / "configured", database)
    parent_root = scope.root / "parent"
    snapshot_root = scope.root / "snapshots"
    writer = BoundedDailyMarketTechnicalParentCaptureWriterV4(
        parent_root, research_scope=scope
    )
    started = writer.start(plan)
    result = write_daily_market_technical_snapshot_v4_batch(
        output_root=snapshot_root,
        cohort=cohort,
        source_clock=clock,
        finished_windows=windows,
        research_scope=scope,
    )
    assert result.status == "complete" and result.artifact is not None
    recorded = writer.record_verified_batch(
        plan.identity_sha256,
        started.identity_sha256,
        expected_previous_receipt_sha256=started.content_sha256,
        artifact=result.artifact,
    )
    completed = writer.complete(
        plan.identity_sha256,
        recorded.identity_sha256,
        expected_previous_receipt_sha256=recorded.content_sha256,
    )
    assert completed.status == "complete"
    expected = read_daily_market_technical_parent_capture_v4(
        parent_root,
        plan.identity_sha256,
        completed.identity_sha256,
        expected_plan_sha256=plan.content_sha256,
        expected_receipt_sha256=completed.content_sha256,
    )
    states = expected["plan"]["source_stock_evidence"]
    assert [item["stock_code"] for item in states] == list(codes)
    assert states[0]["rule_states"]["ma5_20_golden_cross"] == "unknown"
    assert states[1]["rule_states"]["ma5_20_golden_cross"] == "match"
    return {
        "database": database,
        "parent_root": parent_root,
        "plan_identity": plan.identity_sha256,
        "plan_sha": plan.content_sha256,
        "receipt_identity": completed.identity_sha256,
        "receipt_sha": completed.content_sha256,
        "output_root": root / "signals",
        "universe_id": cohort.universe_id,
        "population_version": cohort.population_version,
        "source_package": expected,
    }


def _capture(parent: dict[str, Any]) -> Any:
    return write_forward_signal_observation_from_exact_parent(
        parent_output_root=parent["parent_root"],
        plan_identity_sha256=parent["plan_identity"],
        expected_plan_sha256=parent["plan_sha"],
        receipt_identity_sha256=parent["receipt_identity"],
        expected_receipt_sha256=parent["receipt_sha"],
        rule_key="ma5_20_golden_cross",
        output_root=parent["output_root"],
    )


def _read(parent: dict[str, Any], written: Any, *, cutoff: datetime | None = None) -> Any:
    return read_exact_forward_signal_observation(
        output_root=parent["output_root"],
        capture_identity_sha256=written.capture_identity_sha256,
        expected_receipt_sha256=written.receipt_sha256,
        rule_key="ma5_20_golden_cross",
        decision_cutoff=cutoff or datetime.fromisoformat(written.available_at),
        expected_universe_id=parent["universe_id"],
        expected_population_version=parent["population_version"],
    )


def _write_rehashed_mutation(parent: dict[str, Any], written: Any, *, mutate: Any) -> tuple[str, str, datetime]:
    original_dir = parent["output_root"] / "observations" / written.capture_identity_sha256
    artifact = json.loads((original_dir / "observation.json").read_bytes())
    saved_receipt = json.loads((original_dir / "saved.json").read_bytes())
    receipt = json.loads((original_dir / "receipt.json").read_bytes())
    mutate(artifact)
    artifact.pop("capture_identity_sha256")
    artifact["capture_identity_sha256"] = hashlib.sha256(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    artifact_raw = json.dumps(artifact, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode("utf-8")
    saved_receipt["capture_identity_sha256"] = artifact["capture_identity_sha256"]
    saved_receipt["artifact_sha256"] = hashlib.sha256(artifact_raw).hexdigest()
    saved_raw = json.dumps(saved_receipt, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    receipt["capture_identity_sha256"] = artifact["capture_identity_sha256"]
    receipt["artifact_sha256"] = hashlib.sha256(artifact_raw).hexdigest()
    receipt["saved_receipt_sha256"] = hashlib.sha256(saved_raw).hexdigest()
    receipt["saved_at"] = saved_receipt["saved_at"]
    receipt_raw = json.dumps(receipt, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    new_dir = original_dir.parent / artifact["capture_identity_sha256"]
    new_dir.mkdir()
    (new_dir / "observation.json").write_bytes(artifact_raw)
    (new_dir / "saved.json").write_bytes(saved_raw)
    (new_dir / "receipt.json").write_bytes(receipt_raw)
    return (artifact["capture_identity_sha256"], hashlib.sha256(receipt_raw).hexdigest(),
            datetime.fromisoformat(receipt["available_at"]))


def test_real_source_parent_writes_forward_enum_preserves_unknown_and_reopens_in_fresh_pid(short_temp: Path) -> None:
    parent = _make_parent(short_temp)
    source_before = hashlib.sha256(parent["database"].read_bytes()).hexdigest()
    written = _capture(parent)
    observed = _read(parent, written)
    assert observed.rule_key == "ma5_20_golden_cross"
    assert observed.method_id and observed.rule_version
    assert observed.qualification == "research_only"
    assert [(row["stock_code"], row["state"]) for row in observed.signals] == [
        ("2330", "unknown"), ("2382", "match")
    ]
    assert written.signal_count == 2
    assert datetime.fromisoformat(written.available_at) >= datetime.fromisoformat(written.saved_at)
    assert hashlib.sha256(parent["database"].read_bytes()).hexdigest() == source_before

    script = (
        "import json,sys; sys.path.insert(0,sys.argv[1]); "
        "from app_module.strategy_rule_forward_observation import read_exact_forward_signal_observation; "
        "from datetime import datetime; "
        "x=read_exact_forward_signal_observation(output_root=sys.argv[2], "
        "capture_identity_sha256=sys.argv[3], expected_receipt_sha256=sys.argv[4], "
        "rule_key=sys.argv[5], decision_cutoff=datetime.fromisoformat(sys.argv[6]), "
        "expected_universe_id=sys.argv[7], expected_population_version=sys.argv[8]); "
        "print(json.dumps(x.to_dict(),sort_keys=True))"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(REPO), str(parent["output_root"]),
         written.capture_identity_sha256, written.receipt_sha256, "ma5_20_golden_cross",
         written.available_at, parent["universe_id"], parent["population_version"]],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert child.pid != os.getpid()
    try:
        child_stdout, child_stderr = child.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        child.kill()
        child_stdout, child_stderr = child.communicate(timeout=10)
        pytest.fail(f"fresh_reader_timeout: pid={child.pid}; stderr={child_stderr}")
    assert child.returncode == 0, child_stderr
    reopened = json.loads(child_stdout)
    assert reopened["capture_identity_sha256"] == written.capture_identity_sha256
    assert reopened["signals"] == list(observed.signals)
    source_after = hashlib.sha256(parent["database"].read_bytes()).hexdigest()
    assert source_after == source_before
    qa_receipt = {
        "schema_version": "p08-forward-source-reader-qa-receipt.v1",
        "child_pid": child.pid,
        "child_returncode": child.returncode,
        "source_database_sha256_before": source_before,
        "source_database_sha256_after": source_after,
        "source_database_unchanged": True,
        "parent_plan_identity_sha256": parent["plan_identity"],
        "parent_plan_sha256": parent["plan_sha"],
        "parent_receipt_identity_sha256": parent["receipt_identity"],
        "parent_receipt_sha256": parent["receipt_sha"],
        "observation_identity_sha256": written.capture_identity_sha256,
        "observation_artifact_sha256": written.artifact_sha256,
        "observation_receipt_sha256": written.receipt_sha256,
        "observation_available_at": written.available_at,
        "reopened_signal_states": [
            {"stock_code": row["stock_code"], "state": row["state"]}
            for row in observed.signals
        ],
    }
    qa_receipt_root = REPO / "output/qa/strategy_rule_forward_observation"
    qa_receipt_root.mkdir(parents=True, exist_ok=True)
    qa_receipt_path = (
        qa_receipt_root
        / f"fresh_source_reader_receipt_{os.getpid()}_{child.pid}.json"
    )
    with qa_receipt_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(qa_receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def test_late_naive_foreign_and_no_caller_score_authority_are_rejected(short_temp: Path) -> None:
    parent = _make_parent(short_temp)
    written = _capture(parent)
    available = datetime.fromisoformat(written.available_at)
    with pytest.raises(StrategySignalObservationError, match="not_available_at_decision"):
        _read(parent, written, cutoff=available - timedelta(microseconds=1))
    with pytest.raises(StrategySignalObservationError, match="decision_cutoff_naive"):
        _read(parent, written, cutoff=datetime.now())
    with pytest.raises(StrategySignalObservationError, match="foreign_universe"):
        read_exact_forward_signal_observation(
            output_root=parent["output_root"],
            capture_identity_sha256=written.capture_identity_sha256,
            expected_receipt_sha256=written.receipt_sha256,
            rule_key="ma5_20_golden_cross",
            decision_cutoff=available,
            expected_universe_id="foreign-universe",
            expected_population_version=parent["population_version"],
        )
    with pytest.raises(StrategySignalObservationError, match="rule_unknown_or_duplicate"):
        read_exact_forward_signal_observation(
            output_root=parent["output_root"],
            capture_identity_sha256=written.capture_identity_sha256,
            expected_receipt_sha256=written.receipt_sha256,
            rule_key="unknown_rule",
            decision_cutoff=available,
        )
    with pytest.raises(TypeError):
        write_forward_signal_observation_from_exact_parent(
            parent_output_root=parent["parent_root"],
            plan_identity_sha256=parent["plan_identity"],
            expected_plan_sha256=parent["plan_sha"],
            receipt_identity_sha256=parent["receipt_identity"],
            expected_receipt_sha256=parent["receipt_sha"],
            rule_key="ma5_20_golden_cross",
            output_root=parent["output_root"],
            scores={"2382": 100},
        )


def test_rehashed_signal_tamper_and_duplicate_signal_rows_fail_exact_parent_recompute(short_temp: Path) -> None:
    parent = _make_parent(short_temp)
    written = _capture(parent)
    tampered_id, tampered_receipt_sha, tampered_cutoff = _write_rehashed_mutation(
        parent, written,
        mutate=lambda body: body["signals"][1].update(state="no_match"),
    )
    with pytest.raises(StrategySignalObservationError, match="signal_source_mismatch"):
        read_exact_forward_signal_observation(
            output_root=parent["output_root"],
            capture_identity_sha256=tampered_id,
            expected_receipt_sha256=tampered_receipt_sha,
            rule_key="ma5_20_golden_cross",
            decision_cutoff=tampered_cutoff,
        )

    # 另注入重複成員並重封 artifact/receipt，public reader仍須拒絕。
    parent2 = _make_parent(short_temp / "second")
    written2 = _capture(parent2)
    duplicate_id, duplicate_receipt_sha, duplicate_cutoff = _write_rehashed_mutation(
        parent2, written2,
        mutate=lambda body: body["signals"].append(dict(body["signals"][0])),
    )
    with pytest.raises(StrategySignalObservationError, match="duplicate_or_order"):
        read_exact_forward_signal_observation(
            output_root=parent2["output_root"],
            capture_identity_sha256=duplicate_id,
            expected_receipt_sha256=duplicate_receipt_sha,
            rule_key="ma5_20_golden_cross",
            decision_cutoff=duplicate_cutoff,
        )


def test_rehashed_source_clock_and_capture_before_true_parent_are_rejected(short_temp: Path) -> None:
    parent = _make_parent(short_temp)
    written = _capture(parent)
    false_source_clock_id, false_source_receipt_sha, false_source_cutoff = _write_rehashed_mutation(
        parent,
        written,
        mutate=lambda body: body["clock"].update(
            source_decision_cutoff=(
                datetime.fromisoformat(body["clock"]["source_decision_cutoff"])
                + timedelta(microseconds=1)
            ).isoformat()
        ),
    )
    with pytest.raises(StrategySignalObservationError, match="source_clock_binding_mismatch"):
        read_exact_forward_signal_observation(
            output_root=parent["output_root"],
            capture_identity_sha256=false_source_clock_id,
            expected_receipt_sha256=false_source_receipt_sha,
            rule_key="ma5_20_golden_cross",
            decision_cutoff=false_source_cutoff,
        )

    parent2 = _make_parent(short_temp / "early")
    written2 = _capture(parent2)
    true_parent_completed = datetime.fromisoformat(
        parent2["source_package"]["receipt"]["observed_at"]
    )
    early_id, early_receipt_sha, early_cutoff = _write_rehashed_mutation(
        parent2,
        written2,
        mutate=lambda body: body["clock"].update(
            captured_at=(true_parent_completed - timedelta(microseconds=1)).isoformat()
        ),
    )
    with pytest.raises(StrategySignalObservationError, match="clock_order_invalid"):
        read_exact_forward_signal_observation(
            output_root=parent2["output_root"],
            capture_identity_sha256=early_id,
            expected_receipt_sha256=early_receipt_sha,
            rule_key="ma5_20_golden_cross",
            decision_cutoff=early_cutoff,
        )


def test_reparse_intermediate_alias_is_rejected(short_temp: Path) -> None:
    parent = _make_parent(short_temp)
    written = _capture(parent)
    alias_root = short_temp / "alias-root"
    alias_root.mkdir()
    alias_path = alias_root / "observations"
    if os.name == "nt":
        junction = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(alias_path),
             str(parent["output_root"] / "observations")],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction.returncode != 0:
            pytest.skip("directory junction creation is unavailable in this environment")
    else:
        try:
            os.symlink(parent["output_root"] / "observations", alias_path, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("directory symlink/reparse creation is unavailable in this environment")
    with pytest.raises(StrategySignalObservationError, match="capture_path_invalid"):
        read_exact_forward_signal_observation(
            output_root=alias_root,
            capture_identity_sha256=written.capture_identity_sha256,
            expected_receipt_sha256=written.receipt_sha256,
            rule_key="ma5_20_golden_cross",
            decision_cutoff=datetime.fromisoformat(written.available_at),
        )
    if os.name == "nt":
        os.rmdir(alias_path)


def test_hardlink_and_oversized_capture_are_rejected(short_temp: Path) -> None:
    parent = _make_parent(short_temp)
    written = _capture(parent)
    artifact_path = (
        parent["output_root"] / "observations" / written.capture_identity_sha256 / "observation.json"
    )
    try:
        os.link(artifact_path, short_temp / "artifact-hardlink.json")
    except OSError:
        pytest.skip("hardlink creation is unavailable in this environment")
    with pytest.raises(StrategySignalObservationError, match="capture_path_invalid"):
        _read(parent, written)
    (short_temp / "artifact-hardlink.json").unlink()

    # 以 sparse truncate 建立超限檔，讀取端必須在讀取內容前拒絕。
    with artifact_path.open("wb") as handle:
        handle.truncate(2 * 1024 * 1024 + 1)
    with pytest.raises(StrategySignalObservationError, match="capture_byte_limit"):
        _read(parent, written)


def test_hostile_decimal_context_does_not_change_source_enum_or_writer_clock(short_temp: Path) -> None:
    parent = _make_parent(short_temp)
    hostile = Context(prec=1, Emax=1, Emin=-1, traps=[Inexact])
    with localcontext(hostile):
        written = _capture(parent)
        observed = _read(parent, written)
    assert [row["state"] for row in observed.signals] == ["unknown", "match"]


def test_duplicate_capture_and_receipt_hash_tamper_are_rejected(short_temp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app_module.strategy_rule_forward_observation as candidate

    parent = _make_parent(short_temp)
    fixed_clock = datetime.now(timezone.utc)
    monkeypatch.setattr(candidate, "_utc_now", lambda: fixed_clock)
    written = _capture(parent)
    with pytest.raises(StrategySignalObservationError, match="duplicate_capture"):
        _capture(parent)
    with pytest.raises(StrategySignalObservationError, match="receipt_hash_mismatch"):
        read_exact_forward_signal_observation(
            output_root=parent["output_root"],
            capture_identity_sha256=written.capture_identity_sha256,
            expected_receipt_sha256="0" * 64,
            rule_key="ma5_20_golden_cross",
            decision_cutoff=datetime.fromisoformat(written.available_at),
        )
