"""實際隔離daily owner全鏈、容量/漏日/retry；不註冊Task。"""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import app_module.rule_research_daily_owner as owner
from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter, SAFETY_RESERVE_BYTES
from tests.test_rule_research_observation_acceptance import context as observation_context
from scripts.scheduled.run_rule_research_daily_isolated import main


@pytest.fixture
def ctx(observation_context,monkeypatch):
    args, policy, accept_root, policy_value = observation_context
    base = policy.parent
    today = args["decision_cutoff"].date()
    old = json.loads(args["universe_path"].read_text(encoding="utf-8"))
    old["as_of_date"] = (today-timedelta(days=1)).isoformat()
    old_path = base/"yesterday.json"
    old_path.write_text(json.dumps(old),encoding="utf-8")
    runtime = {"schema_version":owner.RUNTIME_SCHEMA,"mode":"isolated_research","date_source":"explicit_policy_dates",
        "policy_config":str(policy),"source_db":str(args["db_path"]),"snapshot_root":str(args["snapshot_root"]),
        "capture_root":str(args["capture_root"]),"acceptance_root":str(accept_root),"status_root":str(base/"owner-status"),
        "per_root_quota_bytes":64*1024*1024,"max_attempts":2,"retry_delay_seconds":0,
        "parent_universe_configs":{today.isoformat():str(args["universe_path"]),(today-timedelta(days=1)).isoformat():str(old_path)}}
    path = base/"runtime.json"
    path.write_text(json.dumps(runtime),encoding="utf-8")
    monkeypatch.setattr(owner,"_free_bytes",lambda p: SAFETY_RESERVE_BYTES*4)
    return path,today,runtime,args,policy_value


def test_actual_owner_preflight_full_chain_replay_and_status(ctx):
    path,day,c,args,_ = ctx
    before = args["db_path"].read_bytes()
    pre = owner.run_daily_owner(path,day)
    assert pre["status"] == "preflight_passed"
    assert all(not Path(c[k]).exists() for k in owner._ROOTS)
    result = owner.run_daily_owner(path,day,execute=True)
    assert result["status"] == "observed", result
    assert result["owner_status_capture_status"] == "published"
    attempt = result["attempts"][0]
    assert all(b["production_status"] == "published_complete" for b in attempt["batches"])
    assert attempt["acceptance_status"] == "accepted_research_observation"
    receipt = attempt["parent_capture"]["receipt"]
    parent = json.loads((Path(c["capture_root"])/"parents"/receipt["capture_identity_sha256"]/"capture.json").read_text(encoding="utf-8"))
    assert parent["source_binding_sha256"] == result["source_binding_sha256"]
    assert parent["universe"]["value"]["as_of_date"] == day.isoformat()
    assert parent["decision_cutoff"] == result["decision_cutoff"]
    count = len(list((Path(c["capture_root"])/"parents").iterdir()))
    replay = owner.run_daily_owner(path,day,execute=True)
    assert replay["status"] == "already_observed" and replay["attempts"] == []
    assert len(list((Path(c["capture_root"])/"parents").iterdir())) == count
    assert replay["day_readiness"]["missing_observation_dates"] == [(day-timedelta(days=1)).isoformat()]
    writer = owner._OwnerStatusWriter(c["status_root"])
    assert writer.read(result["owner_receipt"]["receipt"]["capture_identity_sha256"])["capture"]["status"] == "observed"
    assert args["db_path"].read_bytes() == before
    assert result["qualification"]["source_availability"] == "unknown" and not result["qualification"]["training_eligible"]


def test_next_day_trigger_previous_target_missed_no_latest_or_write(ctx):
    path,day,c,_,_ = ctx
    late = owner.run_daily_owner(path,day-timedelta(days=1),execute=True)
    assert late["status"] == "missed_window"
    assert late["attempts"] == [] and late["day_readiness"]["missing_observation_dates"] == [(day-timedelta(days=1)).isoformat()]
    assert all(not Path(c[k]).exists() for k in owner._ROOTS)


@pytest.mark.parametrize("removed",["policy_config","date_source","source_db","snapshot_root","per_root_quota_bytes","max_attempts"])
def test_missing_runtime_field_unconfigured_no_production(ctx,removed):
    path,day,c,_,_ = ctx
    del c[removed]
    path.write_text(json.dumps(c),encoding="utf-8")
    result = owner.run_daily_owner(path,day,execute=True)
    assert result["status"] == "unconfigured" and removed in result["error_code"]
    assert result["attempts"] == []


def test_no_config_target_and_formal_source_refusal(ctx):
    path,day,c,_,_ = ctx
    assert owner.run_daily_owner(None,None)["status"] == "unconfigured"
    c["source_db"] = "D:/Min/Python/Project/FA_Data/sqlite/twstock.db"
    path.write_text(json.dumps(c),encoding="utf-8")
    result = owner.run_daily_owner(path,day,execute=True)
    assert result["status"] == "blocked" and "isolated_output" in result["error_code"]
    assert result["attempts"] == []


def test_capacity_preflight_stops_all_writes_then_retry(ctx,monkeypatch):
    path,day,c,_,_ = ctx
    monkeypatch.setattr(owner,"_free_bytes",lambda p: 0)
    result = owner.run_daily_owner(path,day,execute=True)
    assert result["status"] == "capacity_blocked" and not result["attempts"]
    assert all(not Path(c[k]).exists() for k in owner._ROOTS)
    monkeypatch.setattr(owner,"_free_bytes",lambda p: SAFETY_RESERVE_BYTES*4)
    assert owner.run_daily_owner(path,day,execute=True)["status"] == "observed"


def test_capture_refusal_producer_published_then_bounded_retry(ctx,monkeypatch):
    path,day,_,_,_ = ctx
    original = BoundedRuleResearchCaptureWriter.capture_pinned
    calls = []
    def reject_first(*a,**kw):
        calls.append(1)
        if len(calls)==1:
            raise ValueError("controlled sample refusal")
        return original(*a,**kw)
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"capture_pinned",reject_first)
    result = owner.run_daily_owner(path,day,execute=True)
    assert result["status"] == "observed",result
    assert len(result["attempts"]) == 2
    first,second = result["attempts"]
    assert first["production_status"] == "incomplete"
    assert any(b["production_status"] == "published_complete" for b in first["batches"])
    assert any(b["sample_capture_status"] == "rejected" for b in first["batches"])
    assert first["acceptance_status"] == "recorded_incomplete_observation"
    assert second["acceptance_status"] == "accepted_research_observation"


def test_retry_limit_missing_target_data_preserves_unknown(ctx):
    path,day,c,args,_ = ctx
    with sqlite3.connect(args["db_path"]) as con:
        con.execute("DELETE FROM daily_prices WHERE 日期=?",(day.isoformat(),))
    result = owner.run_daily_owner(path,day,execute=True)
    assert result["status"] == "incomplete",result
    assert len(result["attempts"]) == c["max_attempts"]
    assert all(a["acceptance_status"] == "recorded_incomplete_observation" for a in result["attempts"])
    assert result["day_readiness"]["days"][1]["accepted_count"] == 0


def test_new_revision_new_job_preserves_old_and_does_not_retry_mixed_source(ctx,monkeypatch):
    path,day,c,args,_ = ctx
    original = owner.produce_parent_rule_samples
    first = owner.run_daily_owner(path,day,execute=True)
    assert first["status"] == "observed"
    before = {p:p.read_bytes() for p in (Path(c["capture_root"])/"parents").rglob("*.json")}
    with sqlite3.connect(args["db_path"]) as con:
        con.execute("UPDATE daily_prices SET 收盤價='104' WHERE 日期=?",(day.isoformat(),))
    second = owner.run_daily_owner(path,day,execute=True)
    assert second["status"] == "observed"
    assert second["day_readiness"]["days"][1]["revision_pin_count"] == 2
    assert before == {p:p.read_bytes() for p in before}
    def mutate_after_capture(*a,**kw):
        result = original(*a,**kw)
        with sqlite3.connect(args["db_path"]) as con:
            con.execute("UPDATE daily_prices SET 收盤價='106' WHERE 日期=?",(day.isoformat(),))
        return result
    with sqlite3.connect(args["db_path"]) as con:
        con.execute("UPDATE daily_prices SET 收盤價='105' WHERE 日期=?",(day.isoformat(),))
    monkeypatch.setattr(owner,"produce_parent_rule_samples",mutate_after_capture)
    mixed = owner.run_daily_owner(path,day,execute=True)
    assert mixed["status"] == "blocked" and "revision_changed" in mixed["error_code"]
    assert mixed["attempts"][0]["parent_capture"]["receipt"]
    assert mixed["attempts"][0]["acceptance_capture_status"] == "rejected_or_unverified"


def test_owner_busy_cancel_and_cli_safe_default(ctx,capsys):
    path,day,c,_,_ = ctx
    status = Path(c["status_root"])
    status.mkdir()
    lock = status/".owner.lock"
    lock.write_text("another owner",encoding="utf-8")
    assert owner.run_daily_owner(path,day,execute=True)["status"] == "busy"
    assert lock.read_text(encoding="utf-8") == "another owner"
    # 別的fresh status根測合作取消，保留前一busy lock。
    c["status_root"] = str(status.with_name("fresh-status"))
    path.write_text(json.dumps(c),encoding="utf-8")
    cancelled = owner.run_daily_owner(path,day,execute=True,cancel_callback=lambda: True)
    assert cancelled["status"] == "cancelled" and not cancelled["attempts"]
    assert main([]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "unconfigured"
    assert main(["--runtime-config",str(path),"--target-date",day.isoformat()]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "preflight_passed"


def test_new_process_cli_resumes_actual_parent_without_new_producer(ctx):
    path,day,c,_,_ = ctx
    assert owner.run_daily_owner(path,day,execute=True)["status"] == "observed"
    script = "from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter,SAFETY_RESERVE_BYTES; import app_module.rule_research_daily_owner as o; o._free_bytes=lambda p:SAFETY_RESERVE_BYTES*4; BoundedRuleResearchCaptureWriter._free_bytes=lambda s:SAFETY_RESERVE_BYTES*4; o.produce_parent_rule_samples=lambda **k:(_ for _ in ()).throw(AssertionError('producer rerun')); from scripts.scheduled.run_rule_research_daily_isolated import main; import sys; raise SystemExit(main(sys.argv[1:]))"
    child = subprocess.run([sys.executable,"-c",script,"--runtime-config",str(path),"--target-date",day.isoformat(),"--execute-isolated"],capture_output=True,text=True,timeout=20)
    assert child.returncode == 0,child.stderr+child.stdout
    assert json.loads(child.stdout)["status"] == "already_observed"


def test_explicit_quota_shortage_stops_before_any_write(ctx):
    path,day,c,_,_ = ctx
    c["per_root_quota_bytes"] = 1024*1024
    path.write_text(json.dumps(c),encoding="utf-8")
    result = owner.run_daily_owner(path,day,execute=True)
    assert result["status"] == "capacity_blocked" and "quota" in result["error_code"]
    assert all(not Path(c[k]).exists() for k in owner._ROOTS)


def test_absent_cutoff_window_is_unconfigured_not_production_defaults(ctx):
    path,day,c,_,_ = ctx
    policy = Path(c["policy_config"])
    value = json.loads(policy.read_text(encoding="utf-8"))
    del value["observation_start_time"]
    policy.write_text(json.dumps(value),encoding="utf-8")
    result = owner.run_daily_owner(path,day,execute=True)
    assert result["status"] == "unconfigured" and "observation_start_time" in result["error_code"]
    assert not result["attempts"]
