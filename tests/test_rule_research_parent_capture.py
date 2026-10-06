"""具名母體多批的實際隔離閉環與失敗／取消／重試。"""
from copy import deepcopy
from datetime import datetime, time
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import app_module.rule_research_parent_capture as parent_module
from app_module.rule_research_parent_capture import (
    PARENT_UNIVERSE_SCHEMA, RuleResearchParentCapture, BoundedRuleResearchParentWriter,
    load_parent_universe, produce_parent_rule_samples, read_parent_rule_sample_readiness, _parent_identity,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter, SAFETY_RESERVE_BYTES, RuleSampleCaptureError, _json, _identity,
)
from tests.test_daily_market_snapshot_consumer import _seed
from tests.test_daily_market_snapshot_producer import _capacity_probe


def _fixture(tmp_path, monkeypatch, *, included=17, excluded=2):
    db, day = _seed(tmp_path)
    codes = [str(1000+i) for i in range(included)]
    with sqlite3.connect(db) as con:
        for code in codes:
            con.execute("INSERT INTO daily_prices SELECT 日期,?,開盤價,最高價,最低價,收盤價,成交股數 FROM daily_prices WHERE 證券代號='2382'", (code,))
            con.execute("INSERT INTO technical_indicators SELECT 日期,?,MA20,MA60 FROM technical_indicators WHERE 證券代號='2382'", (code,))
    value = {"schema_version": PARENT_UNIVERSE_SCHEMA, "universe_id": "named-controlled", "version": "1.0",
        "as_of_date": day.isoformat(), "method": "daily-market-close-ma.v1", "scope": "bounded_multibatch_research_cohort",
        "included_stock_codes": codes, "excluded_stock_codes": [{"stock_code": str(9000+i), "reason": "明示排除對照"} for i in range(excluded)],
        "population_count": included+excluded, "research_only": True, "complete_fixed_cohort": True}
    path = tmp_path / "parent.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    class ControlledProducer(parent_module.DailyMarketSnapshotProducer):
        def __init__(self, root):
            super().__init__(root, capacity_probe=_capacity_probe())
    monkeypatch.setattr(parent_module, "DailyMarketSnapshotProducer", ControlledProducer)
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter, "_free_bytes", lambda _s: SAFETY_RESERVE_BYTES * 4)
    args = dict(db_path=db, snapshot_root=tmp_path / "snapshots", capture_root=tmp_path / "captures",
                universe_path=path, decision_cutoff=datetime.combine(day,time(16),tzinfo=ZoneInfo("Asia/Taipei")))
    return args, ControlledProducer


def _read(args, result):
    return read_parent_rule_sample_readiness(args["snapshot_root"], args["capture_root"],
        universe_path=args["universe_path"], identity_sha256=result["parent_capture"]["receipt"]["capture_identity_sha256"])


def test_actual_multibatch_complete_duplicate_and_new_process_readonly(tmp_path, monkeypatch):
    args, _ = _fixture(tmp_path, monkeypatch)
    db = args["db_path"]
    before = (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    result = produce_parent_rule_samples(**args)
    assert result["status"] == "complete", result
    ready = _read(args, result)
    assert ready["included_denominator"] == 17 and ready["represented_denominator"] == 19
    assert ready["captured_member_count"] == 19 and ready["uncaptured_member_count"] == 0
    assert ready["batches_count"] == 2 and all(len(b["included_stock_codes"]) <= 16 for b in ready["batches"])
    assert all(c["matched"]+c["notmatched"]+c["unknown"]+c["excluded"]+c["uncaptured"] == 19 for c in ready["method_counts"])
    assert ready["source_availability"] == ready["market_calendar"] == ready["outcome_maturity"] == "unknown"
    assert ready["selected_count"] == 0 and not ready["training_eligible"]
    args["as_of"] = datetime.fromisoformat(ready["as_of"])
    again = produce_parent_rule_samples(**args)
    assert again["parent_capture"]["status"] == "duplicate", again
    assert again["sample_readiness"]["parent_identity_sha256"] == ready["parent_identity_sha256"]
    assert before == (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    script = "from app_module.rule_research_parent_capture import read_parent_rule_sample_readiness; import json,sys; print(json.dumps(read_parent_rule_sample_readiness(sys.argv[1],sys.argv[2],universe_path=sys.argv[3],identity_sha256=sys.argv[4]),sort_keys=True))"
    completed = subprocess.run([sys.executable,"-c",script,str(args["snapshot_root"]),str(args["capture_root"]),str(args["universe_path"]),ready["parent_identity_sha256"]],capture_output=True,text=True,encoding="utf-8",timeout=20,env={**os.environ,"PYTHONIOENCODING":"utf-8"})
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["captured_member_count"] == 19


def test_cancel_after_publication_preserves_manifest_and_safe_retry(tmp_path, monkeypatch):
    args, base = _fixture(tmp_path, monkeypatch)
    cancelled = [False]
    class CancelAfterOne(base):
        def produce(self, **kwargs):
            result = super().produce(**kwargs)
            cancelled[0] = True
            return result
    monkeypatch.setattr(parent_module,"DailyMarketSnapshotProducer",CancelAfterOne)
    result = produce_parent_rule_samples(**args,cancel_callback=lambda:cancelled[0])
    assert result["status"] == "cancelled", result
    assert result["production"][0]["manifest_sha256"]
    assert result["production"][0]["production_status"] == "published_complete"
    assert result["production"][0]["sample_capture_status"] == "rejected"
    assert _read(args,result)["status"] == "saved_incomplete"
    cancelled[0] = False
    monkeypatch.setattr(parent_module,"DailyMarketSnapshotProducer",base)
    retry = produce_parent_rule_samples(**args)
    assert retry["status"] == "complete", retry
    assert retry["production"][0]["production_status"] == "unchanged"
    assert len(list((args["capture_root"] / "parents").glob("*/receipt.json"))) == 2


@pytest.mark.parametrize("failure",["second_batch","source_changed","method_changed","capture_rejected"])
def test_mid_failure_never_claims_complete_and_preserves_producer(tmp_path,monkeypatch,failure):
    args, base = _fixture(tmp_path,monkeypatch)
    calls = [0]
    class FaultProducer(base):
        def produce(self,**kwargs):
            calls[0] += 1
            if failure == "second_batch" and calls[0] == 2:
                raise OSError("controlled stop")
            result = super().produce(**kwargs)
            if calls[0] == 1 and failure == "source_changed":
                info=args["db_path"].stat();os.utime(args["db_path"],ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
            if calls[0] == 1 and failure == "method_changed":
                monkeypatch.setattr(parent_module,"method_contracts_sha256",lambda:"a"*64)
            return result
    monkeypatch.setattr(parent_module,"DailyMarketSnapshotProducer",FaultProducer)
    if failure == "capture_rejected":
        original=BoundedRuleResearchCaptureWriter.capture_pinned
        def reject(self,*a,**kw):
            raise RuleSampleCaptureError("controlled_capture_rejected")
        monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"capture_pinned",reject)
    result=produce_parent_rule_samples(**args)
    assert result["status"] != "complete",result
    assert result["production"][0]["manifest_sha256"] and result["production"][0]["production_status"] == "published_complete"
    if failure == "capture_rejected":
        assert result["production"][0]["sample_capture_status"] == "rejected"
        monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"capture_pinned",original)
        retry=produce_parent_rule_samples(**args)
        assert retry["status"] == "complete",retry
        assert all(b["production_status"]=="unchanged" for b in retry["production"])
    elif failure=="source_changed":
        assert result["sample_readiness"]["source_status"] == "changed"
    elif failure=="method_changed":
        assert result["error_code"]=="parent_method_changed"
        assert result.get("parent_capture") and result["sample_readiness_status"]=="rejected"
    else:
        assert result["production"][1]["production_status"] == "interrupted_unknown"
        assert _read(args,result)["uncaptured_member_count"]==19


@pytest.mark.parametrize("damage",["duplicate","missing_batch","member","method","false_complete"])
def test_parent_semantic_tamper_rejected(tmp_path,monkeypatch,damage):
    args,_=_fixture(tmp_path,monkeypatch)
    result=produce_parent_rule_samples(**args)
    body=BoundedRuleResearchParentWriter(args["capture_root"] / "parents").read(result["parent_capture"]["receipt"]["capture_identity_sha256"])["capture"]
    if damage=="duplicate":body["batches"][1]["included_stock_codes"][0]=body["batches"][0]["included_stock_codes"][0]
    elif damage=="missing_batch":body["batches"].pop()
    elif damage=="member":body["batches"][0]["included_stock_codes"][0]="8888"
    elif damage=="method":body["method_contracts_sha256"]="a"*64
    else:body["batches"][0]["status"]="pending";body["batches"][0]["capture_identity_sha256"]=None
    body["capture_identity_sha256"]=_parent_identity(body)
    with pytest.raises(ValueError):RuleResearchParentCapture(_json(body)).to_dict()


def test_large_universe_bounds_duplicates_rejected(tmp_path,monkeypatch):
    args,_=_fixture(tmp_path,monkeypatch,included=257)
    with pytest.raises(ValueError):load_parent_universe(args["universe_path"])
    value=json.loads(args["universe_path"].read_text(encoding="utf-8"));value["included_stock_codes"]=value["included_stock_codes"][:17];value["included_stock_codes"].append(value["included_stock_codes"][0]);value["population_count"]=20
    args["universe_path"].write_text(json.dumps(value),encoding="utf-8")
    with pytest.raises(RuleSampleCaptureError,match="duplicate"):load_parent_universe(args["universe_path"])


def test_partial_child_writer_preserved_and_retry_uses_explicit_fresh_store(tmp_path,monkeypatch):
    import app_module.rule_research_sample_capture as capture_module
    args,_=_fixture(tmp_path,monkeypatch)
    original=capture_module._write_file
    faulted=[False]
    def fail_once(path,raw):
        if path.name=="receipt.json" and not faulted[0]:
            faulted[0]=True
            raise OSError("controlled child receipt interruption")
        original(path,raw)
    monkeypatch.setattr(capture_module,"_write_file",fail_once)
    result=produce_parent_rule_samples(**args)
    assert result["status"]=="incomplete",result
    assert all(b["manifest_sha256"] and b["production_status"]=="published_complete" for b in result["production"])
    partials=list((args["capture_root"] / "samples").glob("*/.partial-*"))
    assert len(partials)==1 and list(partials[0].iterdir())
    before=[(p.name,p.read_bytes()) for p in partials[0].iterdir()]
    retry=produce_parent_rule_samples(**args)
    assert retry["status"]=="incomplete" and retry["production"][0]["error_code"]=="store_unknown_or_partial_entry"
    assert before==[(p.name,p.read_bytes()) for p in partials[0].iterdir()]
    args["capture_root"]=tmp_path / "fresh-captures"
    fresh=produce_parent_rule_samples(**args)
    assert fresh["status"]=="complete",fresh
    assert before==[(p.name,p.read_bytes()) for p in partials[0].iterdir()]


def test_cli_parent_readiness_new_read_mode_does_not_open_db(tmp_path,monkeypatch,capsys):
    import scripts.produce_daily_market_research_snapshot as cli
    args,_=_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(cli,"_isolated_output",lambda _p:args["snapshot_root"])
    argv=["--db-path",str(args["db_path"]),"--output-root",str(args["snapshot_root"]),
          "--decision-cutoff",args["decision_cutoff"].isoformat(),"--parent-universe-config",str(args["universe_path"]),
          "--capture-root",str(args["capture_root"]),"--capture-as-of","observed-now"]
    assert cli.main(argv)==0
    first=json.loads(capsys.readouterr().out)
    pin=first["sample_readiness"]["parent_identity_sha256"]
    argv[1]=str(tmp_path / "missing.db")
    argv[-1]=first["sample_readiness"]["as_of"]
    argv += ["--read-parent-identity",pin]
    def forbidden(*_a,**_k):raise AssertionError("readonly mode不得開 DB")
    monkeypatch.setattr(parent_module,"SQLiteDailyMarketSnapshotSource",forbidden)
    assert cli.main(argv)==0
    ready=json.loads(capsys.readouterr().out)
    assert ready["status"]=="readonly" and ready["sample_readiness"]["captured_member_count"]==19
    argv[5]="2026-09-02T16:00:00+08:00"
    assert cli.main(argv)==2
    assert "parent_decision_cutoff_mismatch" in capsys.readouterr().out


def test_max_layout_and_global_budget_remain_bounded(tmp_path,monkeypatch):
    args,_=_fixture(tmp_path,monkeypatch,included=256,excluded=256)
    value=load_parent_universe(args["universe_path"])["value"]
    layout=parent_module._layout(value)
    assert len(layout)==16 and all(len(b["included_stock_codes"])==16 and len(b["excluded_stock_codes"])==16 for b in layout)
    monkeypatch.setattr(parent_module,"MAX_PARENT_SOURCE_BYTES",1024)
    result=produce_parent_rule_samples(**args)
    assert result["status"]=="incomplete" and result["sample_capture_status"]=="rejected"
    assert not list(args["snapshot_root"].glob("batches/*"))


def test_cancel_after_first_capture_retains_control_coverage_and_retry_dedup(tmp_path,monkeypatch):
    args,_=_fixture(tmp_path,monkeypatch)
    cancelled=[False]
    original=BoundedRuleResearchCaptureWriter.capture_pinned
    def cancel_after(self,*a,**kw):
        result=original(self,*a,**kw)
        cancelled[0]=True
        return result
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"capture_pinned",cancel_after)
    result=produce_parent_rule_samples(**args,cancel_callback=lambda:cancelled[0])
    assert result["status"]=="cancelled",result
    ready=_read(args,result)
    assert ready["captured_member_count"]==11 and ready["uncaptured_member_count"]==8
    assert all(sum(c[s] for s in ("matched","notmatched","unknown","excluded","uncaptured"))==19 for c in ready["method_counts"])
    args["as_of"]=datetime.fromisoformat(ready["as_of"])
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"capture_pinned",original)
    retry=produce_parent_rule_samples(**args)
    assert retry["status"]=="complete",retry
    assert retry["production"][0]["sample_capture_status"]=="duplicate"
    assert retry["production"][1]["sample_capture_status"]=="published"


def test_keyboard_interrupt_preserves_already_published_batch(tmp_path,monkeypatch):
    args,base=_fixture(tmp_path,monkeypatch)
    calls=[0]
    class Interrupt(base):
        def produce(self,**kw):
            calls[0]+=1
            if calls[0]==2:raise KeyboardInterrupt()
            return super().produce(**kw)
    monkeypatch.setattr(parent_module,"DailyMarketSnapshotProducer",Interrupt)
    result=produce_parent_rule_samples(**args)
    assert result["status"]=="cancelled" and _read(args,result)["status"]=="saved_incomplete"
    assert result["production"][0]["manifest_sha256"]
    assert not (args["snapshot_root"] / ".parent.lock").exists()


def test_rehashed_parent_with_wrong_child_pin_is_rejected_by_consumer(tmp_path,monkeypatch):
    args,_=_fixture(tmp_path,monkeypatch)
    result=produce_parent_rule_samples(**args)
    writer=BoundedRuleResearchParentWriter(args["capture_root"] / "parents")
    body=writer.read(result["parent_capture"]["receipt"]["capture_identity_sha256"])["capture"]
    body["batches"][0]["capture_identity_sha256"],body["batches"][1]["capture_identity_sha256"]=body["batches"][1]["capture_identity_sha256"],body["batches"][0]["capture_identity_sha256"]
    body["capture_identity_sha256"]=_parent_identity(body)
    damaged=RuleResearchParentCapture(_json(body))
    writer.write(damaged,revalidate=lambda:damaged)
    with pytest.raises(ValueError):
        read_parent_rule_sample_readiness(args["snapshot_root"],args["capture_root"],universe_path=args["universe_path"],identity_sha256=damaged.identity_sha256)


@pytest.mark.parametrize("late",["cancel","source","universe"])
def test_last_capture_success_then_change_keeps_incomplete_parent(tmp_path,monkeypatch,late):
    args,_=_fixture(tmp_path,monkeypatch)
    original=BoundedRuleResearchCaptureWriter.capture_pinned
    calls=[0];cancelled=[False]
    def change_after_last(self,*a,**kw):
        result=original(self,*a,**kw);calls[0]+=1
        if calls[0]==2:
            if late=="cancel":cancelled[0]=True
            elif late=="source":
                info=args["db_path"].stat();os.utime(args["db_path"],ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
            else:
                value=json.loads(args["universe_path"].read_text(encoding="utf-8"));value["version"]="2.0"
                args["universe_path"].write_text(json.dumps(value),encoding="utf-8")
        return result
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"capture_pinned",change_after_last)
    result=produce_parent_rule_samples(**args,cancel_callback=lambda:cancelled[0])
    assert result["status"] in {"cancelled","incomplete"},result
    assert result["parent_capture"]["receipt"]["cohort_status"] != "complete"
    assert all(b["status"]=="captured" and b["manifest_sha256"] for b in result["production"])
    if late=="universe":
        assert result["sample_readiness_status"]=="rejected" and result["error_code"]=="parent_universe_changed"
    else:
        ready=_read(args,result)
        assert ready["status"]=="saved_incomplete" and ready["captured_member_count"]==19
        assert ready["uncaptured_member_count"]==0 and not ready["training_eligible"]
