"""B12 synthetic／offline：固定clock與exact日來源，不授正式資格。"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import app_module.rule_research_daily_owner as owner
import app_module.rule_research_daily_runtime_adapter as adapter
from app_module.research_snapshot_storage_governance import daily_writer_effective_policy
from app_module.rule_research_sample_capture import SAFETY_RESERVE_BYTES
from tests.test_rule_research_daily_owner import ctx
from tests.test_rule_research_observation_acceptance import context as observation_context


@pytest.fixture
def request_fixture(ctx):
    path, day, config, args, _ = ctx
    pre = owner.run_daily_owner(path, day)
    assert pre["status"] == "preflight_passed", pre
    config["expected_source_binding_sha256"] = pre["source_binding_sha256"]
    config["timeout_seconds"] = 30
    path.write_text(json.dumps(config), encoding="utf-8")
    cutoff = args["decision_cutoff"]
    now = cutoff + timedelta(hours=12)
    calendar = adapter.OfficialCalendarSnapshot(day-timedelta(days=1), day, (day,), "synthetic-calendar", "a"*64,
                                                cutoff-timedelta(days=1), provenance="synthetic_offline", coverage_complete=True)
    terminal = adapter.UpstreamTerminal("quick", day, "complete", "synthetic-quick", "b"*64,
                                        pre["source_binding_sha256"], now-timedelta(hours=1), "synthetic_offline")
    segment = adapter.RuntimeSegment("first", day, day, path, hashlib.sha256(path.read_bytes()).hexdigest())
    req = adapter.DailyRuntimeRequest(day, cutoff, calendar, (terminal,), ("quick",), (segment,),
            path.parent/"coord", 30, (("quick", terminal.identity, terminal.receipt_sha256),),
            (calendar.source_identity, calendar.source_sha256), True)
    return req, now, ctx


def _local_runner(path, day, *, execute, timeout_seconds, cancel_callback):
    return {**owner.run_daily_owner(path, day, execute=execute, cancel_callback=cancel_callback), "process_exit_code": 0}


def _run(fixture, **kwargs):
    req, now, _ = fixture
    return adapter.run_daily_runtime(req, clock=lambda: now, process_runner=_local_runner, **kwargs)


def test_full_offline_parent_acceptance_and_pins(request_fixture):
    req, now, (_, _, config, args, _) = request_fixture
    before = args["db_path"].read_bytes()
    pre = _run(request_fixture)
    assert pre["status"] == "preflight_passed", pre
    assert not req.coordination_root.exists()
    saved = _run(request_fixture, execute=True)
    assert saved["status"] == "observed", saved
    assert saved["owner_result"]["owner_receipt"]["receipt"]
    assert not saved["qualification"]["training_eligible"]
    assert saved["qualification"]["market_calendar"] == "unknown"
    assert args["db_path"].read_bytes() == before
    old = {p: p.read_bytes() for p in Path(config["capture_root"]).rglob("*.json")}
    again = _run(request_fixture, execute=True)
    assert again["status"] == "already_observed"
    assert old == {p: p.read_bytes() for p in old}
    assert not (req.coordination_root/".daily-runtime.lock").exists()


@pytest.mark.parametrize("mutation", ["calendar_missing", "calendar_unverified", "calendar_pin", "calendar_late", "calendar_coverage",
    "terminal_missing", "terminal_date", "terminal_pin", "terminal_future", "terminal_unverified", "source_pin", "cutoff", "segment_overlap"])
def test_invalid_inputs_stop_before_process(request_fixture, mutation):
    req, now, _ = request_fixture
    cal = req.calendar
    t = req.terminals[0]
    if mutation == "calendar_missing": req = replace(req, calendar=None)
    elif mutation == "calendar_unverified": req = replace(req, offline_rehearsal=False)
    elif mutation == "calendar_pin": req = replace(req, expected_calendar_pin=("wrong", "a"*64))
    elif mutation == "calendar_late": req = replace(req, calendar=replace(cal, available_at=now))
    elif mutation == "calendar_coverage": req = replace(req, calendar=replace(cal, coverage_end=req.target_date-timedelta(days=1)))
    elif mutation == "terminal_missing": req = replace(req, terminals=())
    elif mutation == "terminal_date": req = replace(req, terminals=(replace(t, target_date=t.target_date-timedelta(days=1)),))
    elif mutation == "terminal_pin": req = replace(req, terminals=(replace(t, receipt_sha256="c"*64),))
    elif mutation == "terminal_future": req = replace(req, terminals=(replace(t, completed_at=now+timedelta(days=1)),))
    elif mutation == "terminal_unverified": req = replace(req, terminals=(replace(t, provenance="unknown"),))
    elif mutation == "source_pin": req = replace(req, terminals=(replace(t, source_binding_sha256="c"*64),))
    elif mutation == "cutoff": req = replace(req, decision_cutoff=req.decision_cutoff+timedelta(seconds=1))
    else: req = replace(req, segments=(req.segments[0], replace(req.segments[0], segment_id="second")))
    def forbidden(*a, **k): raise AssertionError("不得啟動owner")
    result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=forbidden)
    assert result["status"] == "blocked", result
    assert not req.coordination_root.exists()


def test_non_trading_day_and_unknown_never_start_owner(request_fixture):
    req, now, _ = request_fixture
    req = replace(req, calendar=replace(req.calendar, trading_dates=()))
    result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now,
                                     process_runner=lambda *a, **k: pytest.fail("非交易日不可啟動"))
    assert result["status"] == "non_trading_day"
    assert result["receipt_identity_sha256"]


def test_mockclock_missed_day_without_fallback(request_fixture, monkeypatch):
    req, now, _ = request_fixture
    yesterday = req.target_date-timedelta(days=1)
    terminal = replace(req.terminals[0], target_date=yesterday)
    req = replace(req, target_date=yesterday, decision_cutoff=req.decision_cutoff-timedelta(days=1),
        calendar=replace(req.calendar, trading_dates=(yesterday, req.target_date), available_at=req.calendar.available_at-timedelta(days=1)),
        terminals=(terminal,), segments=(replace(req.segments[0], start_date=yesterday),))
    monkeypatch.setattr(owner, "_now", lambda: now)
    result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=_local_runner)
    assert result["status"] == "missed_window"
    assert not req.coordination_root.exists()


def test_capacity_unknown_and_high_override(request_fixture, monkeypatch):
    req, now, (path, day, config, _, _) = request_fixture
    monkeypatch.setattr(owner, "_free_bytes", lambda p: None)
    result = _run(request_fixture, execute=True)
    assert result["status"] == "capacity_blocked"
    assert result["effective_policy"]["writers"]["capture"]["effective_reserve_bytes"] == SAFETY_RESERVE_BYTES
    assert not req.coordination_root.exists()
    config["safety_reserve_bytes"] = 300*1024**3
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(owner, "_free_bytes", lambda p: 250*1024**3)
    result = owner.run_daily_owner(path, day, execute=True)
    assert result["status"] == "capacity_blocked"
    assert result["effective_policy"]["writers"]["capture"]["effective_reserve_bytes"] == 300*1024**3


@pytest.mark.parametrize("override", [None, 20*1024**3, 100*1024**3, 300*1024**3])
def test_effective_reserve_never_lowers_capture(override):
    policy = daily_writer_effective_policy(override)
    assert policy["writers"]["capture"]["existing_reserve_bytes"] == SAFETY_RESERVE_BYTES
    assert policy["writers"]["capture"]["effective_reserve_bytes"] == max(SAFETY_RESERVE_BYTES, override or 0)
    assert policy["writers"]["snapshot"]["existing_reserve_bytes"] == 20*1024**3


def test_below_central_reserve_rejected():
    with pytest.raises(ValueError): daily_writer_effective_policy(19*1024**3)


def test_common_writer_lock_cancel_and_retry(request_fixture):
    req, now, _ = request_fixture
    req.coordination_root.mkdir()
    lock = req.coordination_root/".daily-runtime.lock"
    lock.write_text("other-writer")
    assert _run(request_fixture, execute=True)["status"] == "busy"
    assert lock.read_text() == "other-writer"
    assert _run(request_fixture, execute=True, cancel_callback=lambda: True)["status"] == "cancelled"
    # 僅移除測試建立的合作lock，不刪收據。
    lock.unlink()
    assert _run(request_fixture, execute=True)["status"] == "observed"


def test_source_revision_blocks_stale_terminal_before_write(request_fixture):
    req, now, (_, day, config, args, _) = request_fixture
    before = {p: p.read_bytes() for p in req.segments[0].runtime_path.parent.glob("*.json")}
    with sqlite3.connect(args["db_path"]) as connection:
        connection.execute("UPDATE daily_prices SET 收盤價='105' WHERE 日期=?", (day.isoformat(),))
    result = _run(request_fixture, execute=True)
    assert result["status"] == "blocked"
    assert "source_binding_mismatch" in result["preflight"]["error_code"]
    assert before == {p: p.read_bytes() for p in before}
    assert not Path(config["snapshot_root"]).exists()


def test_offline_review_task_disabled(request_fixture):
    review = adapter.offline_task_review(request_fixture[0])
    assert not review["enabled"] and not review["task_registered"]
    assert review["account"] == "unconfigured" and review["acl"] == "unconfigured"


def test_rollover_new_process_preflight_preserves_previous_segment(request_fixture):
    req, now, (path, day, config, args, _) = request_fixture
    yesterday = day-timedelta(days=1)
    old_config = {**config, **{role: str(path.parent/("prior-"+role)) for role in owner._ROOTS}}
    old_path = path.parent/"prior-runtime.json"
    old_path.write_text(json.dumps(old_config), encoding="utf-8")
    old_segment = adapter.RuntimeSegment("prior", yesterday, yesterday, old_path, hashlib.sha256(old_path.read_bytes()).hexdigest())
    prior_root = Path(old_config["capture_root"])
    prior_root.mkdir()
    sentinel = prior_root/"preserved-partial.json"
    sentinel.write_bytes(b'{"synthetic_offline":"unverified partial"}')
    pins = {p: p.read_bytes() for p in [sentinel, old_path, path, args["db_path"], args["universe_path"]]}
    req = replace(req, segments=(old_segment, req.segments[0]), calendar=replace(req.calendar, trading_dates=(yesterday, day),
                  available_at=req.calendar.available_at-timedelta(days=1)))
    pids = []
    def child_runner(runtime_path, target_date, *, execute, timeout_seconds, cancel_callback):
        script = """import os,json,sys
from datetime import date
import app_module.rule_research_daily_owner as o
import app_module.rule_research_parent_capture as parent
from app_module.rule_research_sample_capture import SAFETY_RESERVE_BYTES,BoundedRuleResearchCaptureWriter
from tests.test_daily_market_snapshot_producer import _capacity_probe
base = parent.DailyMarketSnapshotProducer
class SyntheticCapacityProducer(base):
    def __init__(self,root): super().__init__(root,capacity_probe=_capacity_probe())
parent.DailyMarketSnapshotProducer=SyntheticCapacityProducer
BoundedRuleResearchCaptureWriter._free_bytes=lambda s:SAFETY_RESERVE_BYTES*4
o._free_bytes=lambda p:SAFETY_RESERVE_BYTES*4
result=o.run_daily_owner(sys.argv[1],date.fromisoformat(sys.argv[2]),execute=sys.argv[3]=='1')
result['pid']=os.getpid()
print(json.dumps(result))"""
        completed = subprocess.run([sys.executable, "-X", "utf8", "-c", script, str(runtime_path), target_date.isoformat(), "1" if execute else "0"],
            capture_output=True, text=True, encoding="utf-8", timeout=timeout_seconds)
        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)
        result["process_exit_code"] = completed.returncode
        pids.append(result.pop("pid"))
        return result
    old_request = replace(req, target_date=yesterday, decision_cutoff=req.decision_cutoff-timedelta(days=1),
                          terminals=(replace(req.terminals[0], target_date=yesterday),))
    old_result = adapter.run_daily_runtime(old_request, clock=lambda: now, process_runner=child_runner)
    assert old_result["status"] == "missed_window", old_result
    new_result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=child_runner)
    assert new_result["status"] == "observed" and new_result["segment_id"] == "first", new_result
    assert len(pids) == len(set(pids)) == 3
    assert pins == {p: p.read_bytes() for p in pins}
    assert not (req.coordination_root/".daily-runtime.lock").exists()


def test_request_codec_and_cli_offline_review(request_fixture, capsys):
    from dataclasses import asdict
    from scripts.scheduled.run_rule_research_daily_isolated import main
    req, _, (path, _, _, _, _) = request_fixture
    request_path = path.parent/"request.json"
    payload = {"schema_version": "rule-research-daily-runtime-request.v1", **asdict(req)}
    request_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    assert adapter.load_runtime_request(request_path) == req
    assert main(["--runtime-request", str(request_path), "--task-review"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["task_registered"] is False and result["enabled"] is False
    assert main(["--runtime-request", str(request_path), "--target-date", req.target_date.isoformat()]) == 2
    assert json.loads(capsys.readouterr().out)["error_code"] == "runtime_request_arguments_conflict"


def test_adapter_rejects_fabricated_success_receipt(request_fixture):
    req, now, _ = request_fixture
    binding = req.terminals[0].source_binding_sha256
    def fake_owner(*a, execute, **kw):
        return {"status": "observed" if execute else "preflight_passed", "source_binding_sha256": binding,
                "owner_status_capture_status": "published", "process_exit_code": 0}
    result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=fake_owner)
    assert result["status"] == "blocked" and result["error_code"] == "owner_receipt_identity_missing"


def test_runtime_changed_after_preflight_stops_before_execute(request_fixture):
    req, now, (path, _, config, _, _) = request_fixture
    def changes_config(*a, execute, **kw):
        assert not execute
        config["retry_delay_seconds"] = 1
        path.write_text(json.dumps(config), encoding="utf-8")
        return {"status": "preflight_passed", "source_binding_sha256": req.terminals[0].source_binding_sha256, "process_exit_code": 0}
    result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=changes_config)
    assert result["status"] == "blocked" and result["error_code"] == "runtime_changed_before_execute"
    assert not req.coordination_root.exists()


def test_cancel_after_preflight_stops_before_lock(request_fixture):
    req, now, _ = request_fixture
    stopped = [False]
    def preflight_only(*a, execute, **kw):
        assert not execute
        stopped[0] = True
        return {"status": "preflight_passed", "source_binding_sha256": req.terminals[0].source_binding_sha256, "process_exit_code": 0}
    result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=preflight_only,
                                      cancel_callback=lambda: stopped[0])
    assert result["status"] == "cancelled"
    assert not req.coordination_root.exists()


def test_process_timeout_cancel_stdout_contract(tmp_path, monkeypatch):
    class FakeChild:
        returncode = None
        def poll(self): return self.returncode
        def terminate(self): self.returncode = 7
        def wait(self, timeout): return self.returncode
    monkeypatch.setattr(adapter.subprocess, "Popen", lambda *a, **kw: FakeChild())
    ticks = iter([0, 2_000_000_000])
    monkeypatch.setattr(adapter.time, "monotonic_ns", lambda: next(ticks))
    result = adapter._owner_process(tmp_path/"runtime.json", datetime.now().date(), execute=True, timeout_seconds=1, cancel_callback=lambda: False)
    assert result["status"] == "timeout" and result["partial_artifacts_preserved"]
    monkeypatch.setattr(adapter.time, "monotonic_ns", lambda: 0)
    result = adapter._owner_process(tmp_path/"runtime.json", datetime.now().date(), execute=True, timeout_seconds=1, cancel_callback=lambda: True)
    assert result["status"] == "cancelled"


@pytest.mark.parametrize("exit_code", ["missing", 2, False, True, "0", 0.0, None],
                         ids=["missing", "nonzero", "bool-false", "bool-true", "string", "float", "null"])
def test_preflight_invalid_exit_never_calls_execute(request_fixture, exit_code):
    req, now, _ = request_fixture
    calls = []
    def runner(*a, execute, **kw):
        calls.append(execute)
        assert not execute, "非法preflight退出碼不得啟動execute"
        result = {"status": "preflight_passed", "source_binding_sha256": req.terminals[0].source_binding_sha256}
        if exit_code != "missing":
            result["process_exit_code"] = exit_code
        return result
    result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=runner)
    assert result["status"] == "blocked" and result["error_code"] == "owner_preflight_process_exit_invalid"
    assert calls == [False]
    assert not req.coordination_root.exists()


def test_preflight_explicit_integer_zero_allows_execute(request_fixture):
    req, now, _ = request_fixture
    calls = []
    def runner(*a, execute, **kw):
        calls.append(execute)
        return {"status": "cancelled" if execute else "preflight_passed",
                "source_binding_sha256": req.terminals[0].source_binding_sha256, "process_exit_code": 0}
    result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=runner)
    assert result["status"] == "cancelled" and calls == [False, True]
    assert not (req.coordination_root/".daily-runtime.lock").exists()


@pytest.mark.parametrize("status", ["observed", "already_observed"])
def test_successful_terminal_requires_exact_integer_zero_with_real_receipt(request_fixture, status):
    req, now, (_, _, _, args, _) = request_fixture
    before = args["db_path"].read_bytes()
    saved = _local_runner(req.segments[0].runtime_path, req.target_date, execute=True,
                          timeout_seconds=30, cancel_callback=lambda: False)
    if status == "already_observed":
        saved = _local_runner(req.segments[0].runtime_path, req.target_date, execute=True,
                              timeout_seconds=30, cancel_callback=lambda: False)
    assert saved["status"] == status
    for code in ("missing", 2, False, True, "0", 0.0, None, 0):
        calls = []
        def runner(*a, execute, **kw):
            calls.append(execute)
            if not execute:
                return {"status": "preflight_passed", "source_binding_sha256": req.terminals[0].source_binding_sha256,
                        "process_exit_code": 0}
            result = dict(saved)
            if code == "missing":
                result.pop("process_exit_code")
            else:
                result["process_exit_code"] = code
            return result
        result = adapter.run_daily_runtime(req, execute=True, clock=lambda: now, process_runner=runner)
        if type(code) is int and code == 0:
            assert result["status"] == status, result
        else:
            assert result["status"] == "blocked" and result["error_code"] == "owner_process_exit_mismatch", result
        assert calls == [False, True]
        assert not (req.coordination_root/".daily-runtime.lock").exists()
    assert args["db_path"].read_bytes() == before
