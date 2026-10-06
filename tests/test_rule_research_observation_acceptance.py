"""固定觀測日的隔離實際parent→接受記錄→日覆蓋；無正式DB/Task。"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone, time
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import app_module.rule_research_observation_acceptance as module
from app_module.rule_research_parent_capture import produce_parent_rule_samples
from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter, RuleSampleCaptureError, _identity, _json
from tests.test_rule_research_parent_capture import _fixture
from scripts.accept_rule_research_observation import main


@pytest.fixture
def context(tmp_path, monkeypatch):
    args, _ = _fixture(tmp_path, monkeypatch)
    today = datetime.now(module._TAIPEI).date()
    shift = (today - args["decision_cutoff"].date()).days
    with sqlite3.connect(args["db_path"]) as con:
        for table in ("daily_prices", "technical_indicators"):
            con.execute(f'UPDATE {table} SET 日期=date(日期,?)', (f'{shift:+d} days',))
    universe = json.loads(args["universe_path"].read_text(encoding="utf-8"))
    universe["as_of_date"] = today.isoformat()
    args["universe_path"].write_text(json.dumps(universe, ensure_ascii=False), encoding="utf-8")
    args["decision_cutoff"] = datetime.combine(today, time(0), tzinfo=module._TAIPEI)
    policy = {"schema_version": module.OBSERVATION_POLICY_SCHEMA, "policy_id": "controlled-daily", "version": "1",
              "timezone": "Asia/Taipei", "decision_cutoff_time": "00:00:00",
              "observation_start_time": "00:00:00", "observation_end_time": "23:59:59",
              "expected_observation_dates": [(today-timedelta(days=1)).isoformat(), today.isoformat()],
              "universe_template_source": str(args["universe_path"]), "research_only": True}
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    return args, policy_path, tmp_path / "acceptances", policy


def _produce(args):
    result = produce_parent_rule_samples(**args)
    identity = result["parent_capture"]["receipt"]["capture_identity_sha256"]
    return args["capture_root"] / "parents" / identity / "receipt.json", result


def _accept(context, path, *, accept=True):
    _, policy, root, _ = context
    return module.preview_or_accept_observation(policy, path, root, accept=accept, evaluated_at=datetime.now(timezone.utc))


def test_actual_preview_accept_duplicate_missing_day_and_new_process(context):
    args, policy, root, _ = context
    path, _ = _produce(args)
    before = args["db_path"].read_bytes()
    preview = _accept(context, path, accept=False)
    assert preview["status"] == "preview" and not preview["acceptance_saved"] and not root.exists()
    assert preview["candidate"]["as_of"] == json.loads(path.with_name("capture.json").read_text(encoding="utf-8"))["as_of"]
    first = _accept(context, path)
    again = _accept(context, path)
    assert first["acceptance_capture_status"] == "published"
    assert again["acceptance_capture_status"] == "duplicate"
    assert first["acceptance"]["receipt"] == again["acceptance"]["receipt"]
    report = again["day_readiness"]
    assert report["days"][0]["status"] == "missing_complete_observation"
    assert report["days"][1]["status"] == "observed" and report["days"][1]["accepted_count"] == 1
    assert report["qualification"]["market_calendar"] == "unknown" and not report["qualification"]["training_eligible"]
    script = "from app_module.rule_research_observation_acceptance import read_observation_days; from datetime import datetime; import sys,json; print(json.dumps(read_observation_days(sys.argv[1],sys.argv[2],evaluated_at=datetime.fromisoformat(sys.argv[3]))))"
    run = subprocess.run([sys.executable,"-c",script,str(policy),str(root),datetime.now(timezone.utc).isoformat()],capture_output=True,text=True,timeout=20)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["days"][1]["status"] == "observed"
    assert args["db_path"].read_bytes() == before


def test_same_day_revisions_keep_both_and_same_pin_repeat_idempotent(context):
    args, _, root, _ = context
    first, _ = _produce(args)
    _accept(context, first)
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    with sqlite3.connect(args["db_path"]) as con:
        con.execute("UPDATE daily_prices SET 收盤價='103' WHERE 證券代號='1000' AND 日期=?", (args["decision_cutoff"].date().isoformat(),))
    second, _ = _produce(args)
    assert second != first
    result = _accept(context, second)
    day = result["day_readiness"]["days"][1]
    assert day["status"] == "observed_multiple_revision_pins" and day["revision_pin_count"] == 2
    assert day["accepted_count"] == 2
    assert before == {p: p.read_bytes() for p in before}
    assert _accept(context, first)["acceptance_capture_status"] == "duplicate"
    assert len(list(root.iterdir())) == 2


def test_missing_exact_data_day_does_not_borrow_latest(context):
    args, _, _, _ = context
    with sqlite3.connect(args["db_path"]) as con:
        for table in ("daily_prices", "technical_indicators"):
            con.execute(f"DELETE FROM {table} WHERE 日期=?", (args["decision_cutoff"].date().isoformat(),))
    path, producer = _produce(args)
    # 原parent只保證控制組/包齊全；接受policy不能把較早資料日算完成。
    assert producer["sample_readiness"]["source_completeness"] == "complete_declared_cohort"
    result = _accept(context, path)
    assert result["candidate"]["acceptance_status"] == "recorded_incomplete_observation"
    assert result["candidate"]["target_data_day_status"] == "insufficient_or_stale"
    assert len(result["candidate"]["missing_target_data_members"]) == 17
    assert result["day_readiness"]["days"][1]["accepted_count"] == 0
    assert result["day_readiness"]["days"][0]["status"] == "missing_complete_observation"


@pytest.mark.parametrize("mutation", ["wrong_day", "wrong_cutoff", "window", "members", "timezone", "duplicate_days", "bound"])
def test_policy_refusals_do_not_create_acceptance(context, mutation):
    args, policy_path, root, policy = context
    path, _ = _produce(args)
    if mutation == "wrong_day":
        policy["expected_observation_dates"] = [policy["expected_observation_dates"][0]]
    elif mutation == "wrong_cutoff":
        policy["decision_cutoff_time"] = policy["observation_start_time"] = "00:00:01"
    elif mutation == "window":
        policy["observation_end_time"] = "00:00:00"
    elif mutation == "members":
        template = json.loads(args["universe_path"].read_text(encoding="utf-8"))
        template["included_stock_codes"][0] = "8888"
        other = policy_path.parent / "other-template.json"
        other.write_text(json.dumps(template), encoding="utf-8")
        policy["universe_template_source"] = str(other)
    elif mutation == "timezone":
        policy["timezone"] = "UTC"
    elif mutation == "duplicate_days":
        policy["expected_observation_dates"] *= 2
    else:
        policy["expected_observation_dates"] = [(args["decision_cutoff"].date()+timedelta(days=i)).isoformat() for i in range(32)]
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises((ValueError, RuleSampleCaptureError)):
        _accept(context, path)
    assert not root.exists()


def test_capacity_failure_retry_preserves_parent(context, monkeypatch):
    args, _, root, _ = context
    path, _ = _produce(args)
    before = path.read_bytes()
    original = BoundedRuleResearchCaptureWriter._free_bytes
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"_free_bytes",lambda s: 0)
    with pytest.raises(RuleSampleCaptureError, match="capacity_reserve"):
        _accept(context, path)
    assert root.exists() and not list(root.iterdir())
    assert path.read_bytes() == before
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"_free_bytes",original)
    assert _accept(context, path)["acceptance_capture_status"] == "published"


def test_saved_parent_tamper_report_refuses_qualification_and_does_not_delete(context):
    args, policy, root, _ = context
    path, _ = _produce(args)
    _accept(context, path)
    child = next((args["capture_root"] / "samples").rglob("capture.json"))
    child.write_text("{}",encoding="utf-8")
    report = module.read_observation_days(policy,root,evaluated_at=datetime.now(timezone.utc))
    day = report["days"][1]
    assert day["accepted_count"] == 0 and not day["records"][0]["saved_verified"]
    assert day["records"][0]["error_code"]
    assert len(list(root.iterdir())) == 1


def test_envelope_rehash_false_acceptance_and_wrong_parent_pin(context):
    args, _, _, _ = context
    path, _ = _produce(args)
    capture = _accept(context,path,accept=False)["candidate"]
    bad = deepcopy(capture)
    bad["source_completeness"] = "partial_research"
    bad["capture_identity_sha256"] = _identity(bad)
    with pytest.raises(RuleSampleCaptureError,match="false_acceptance"):
        module.RuleResearchObservationAcceptance(_json(bad)).to_dict()
    bad = deepcopy(capture)
    bad["parent_pin"]["parent_capture_sha256"] = "a"*64
    bad["capture_identity_sha256"] = _identity(bad)
    writer = module.BoundedRuleResearchObservationWriter(context[2])
    # 重hash外殼能保存只表示語法；readiness必須重新核對原parent，不能授資格。
    obj = module.RuleResearchObservationAcceptance(_json(bad))
    writer.write(obj,revalidate=lambda: obj)
    report = module.read_observation_days(context[1],context[2],evaluated_at=datetime.now(timezone.utc))
    assert report["days"][1]["accepted_count"] == 0


def test_future_evaluation_and_source_output_overlap_refused(context):
    args, policy, root, _ = context
    path, _ = _produce(args)
    with pytest.raises(RuleSampleCaptureError,match="future_evaluation"):
        module.preview_or_accept_observation(policy,path,root,accept=True,evaluated_at=datetime.now(timezone.utc)+timedelta(days=1))
    assert not root.exists()
    with pytest.raises(RuleSampleCaptureError,match="source_output_overlap"):
        module.preview_or_accept_observation(policy,path,args["capture_root"]/"acceptance",accept=True,evaluated_at=datetime.now(timezone.utc))


def test_success_saved_but_report_failure_is_retained_and_retry(context, monkeypatch):
    args, _, _, _ = context
    path, _ = _produce(args)
    original = module.read_observation_days
    monkeypatch.setattr(module,"read_observation_days",lambda *a,**kw: (_ for _ in ()).throw(ValueError("controlled report failure")))
    result = _accept(context,path)
    assert result["acceptance_saved"] and result["acceptance_capture_status"] == "published"
    assert result["day_readiness_status"] == "rejected" and result["acceptance"]["receipt"]
    monkeypatch.setattr(module,"read_observation_days",original)
    assert _accept(context,path)["acceptance_capture_status"] == "duplicate"


def test_cli_default_preview_explicit_accept_and_readonly_no_db(context,capsys,monkeypatch):
    args, policy, root, _ = context
    path, _ = _produce(args)
    flags = ["--policy-config",str(policy),"--acceptance-root",str(root),"--evaluated-at",datetime.now(timezone.utc).isoformat()]
    assert main(flags+["--parent-receipt",str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["acceptance_capture_status"] == "not_written" and not root.exists()
    assert main(flags+["--parent-receipt",str(path),"--accept"]) == 0
    assert json.loads(capsys.readouterr().out)["acceptance_saved"]
    import app_module.rule_research_parent_capture as parent
    monkeypatch.setattr(parent,"SQLiteDailyMarketSnapshotSource",lambda *a,**kw: pytest.fail("opened DB"))
    assert main(flags) == 0
    assert json.loads(capsys.readouterr().out)["days"][1]["status"] == "observed"
    assert main(flags+["--accept"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "rejected"


def test_failed_parent_capture_retry_keeps_incomplete_attempt(context, monkeypatch):
    args, _, _, _ = context
    original = BoundedRuleResearchCaptureWriter.capture_pinned
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"capture_pinned",lambda *a,**kw: (_ for _ in ()).throw(ValueError("controlled capture refusal")))
    first, result = _produce(args)
    assert result["status"] == "incomplete"
    accepted = _accept(context,first)
    assert accepted["candidate"]["acceptance_status"] == "recorded_incomplete_observation"
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter,"capture_pinned",original)
    args["as_of"] = datetime.fromisoformat(accepted["candidate"]["as_of"])
    second, result = _produce(args)
    assert result["status"] == "complete"
    day = _accept(context,second)["day_readiness"]["days"][1]
    assert day["accepted_count"] == 1 and day["revision_pin_count"] == 1 and len(day["records"]) == 2
    assert first.exists() and second.exists()


def test_acceptance_atomic_fault_preserved_and_fresh_root_retry(context,monkeypatch):
    args, policy, root, _ = context
    path, _ = _produce(args)
    import app_module.rule_research_sample_capture as shared
    original = shared._write_file
    calls = []
    def fault(*a,**kw):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("controlled receipt write failure")
        return original(*a,**kw)
    monkeypatch.setattr(shared,"_write_file",fault)
    with pytest.raises(OSError):
        _accept(context,path)
    partial = next(root.glob(".partial-*"))
    assert partial.exists()
    monkeypatch.setattr(shared,"_write_file",original)
    with pytest.raises(RuleSampleCaptureError,match="unknown_or_partial"):
        _accept(context,path)
    fresh = root.with_name("fresh-acceptances")
    result = module.preview_or_accept_observation(policy,path,fresh,accept=True,evaluated_at=datetime.now(timezone.utc))
    assert result["acceptance_saved"] and partial.exists()


def test_evaluation_does_not_borrow_later_asof_and_other_policy_not_counted(context):
    args, policy, root, value = context
    path, _ = _produce(args)
    result = _accept(context,path)
    as_of = datetime.fromisoformat(result["candidate"]["as_of"])
    old = module.read_observation_days(policy,root,evaluated_at=as_of-timedelta(microseconds=1))
    assert old["days"][1]["accepted_count"] == 0
    assert not old["days"][1]["records"][0]["visible_at_evaluation"]
    value["version"] = "2"
    policy.write_text(json.dumps(value),encoding="utf-8")
    changed = module.read_observation_days(policy,root,evaluated_at=datetime.now(timezone.utc))
    assert changed["days"][1]["accepted_count"] == 0 and changed["other_policy_record_count"] == 1


def test_report_inventory_race_fails_closed(context,monkeypatch):
    args, policy, root, _ = context
    path, _ = _produce(args)
    _accept(context,path)
    original = module.build_observation_acceptance
    def mutate(*a,**kw):
        result = original(*a,**kw)
        (root/"controlled-unexpected-entry").write_text("changed",encoding="utf-8")
        return result
    monkeypatch.setattr(module,"build_observation_acceptance",mutate)
    with pytest.raises(RuleSampleCaptureError,match="inventory_changed"):
        module.read_observation_days(policy,root,evaluated_at=datetime.now(timezone.utc))


@pytest.mark.parametrize("wrong_clock", ["future", "before_parent"])
def test_rehashed_clock_cannot_predate_parent_or_claim_future_acceptance(context,wrong_clock):
    args, _, _, _ = context
    path, _ = _produce(args)
    body = _accept(context,path,accept=False)["candidate"]
    if wrong_clock == "future":
        body["observed_at"] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    else:
        body["observed_at"] = body["as_of"]
    body["capture_identity_sha256"] = _identity(body)
    with pytest.raises(RuleSampleCaptureError,match="clock_mismatch"):
        module.RuleResearchObservationAcceptance(_json(body)).to_dict()


def test_future_expected_day_not_due_and_no_read_creates_store(context):
    args, policy, root, value = context
    today = args["decision_cutoff"].date()
    value["expected_observation_dates"].append((today+timedelta(days=1)).isoformat())
    policy.write_text(json.dumps(value),encoding="utf-8")
    report = module.read_observation_days(policy,root,evaluated_at=datetime.now(timezone.utc))
    assert report["days"][0]["status"] == "missing_complete_observation"
    assert report["days"][1]["status"] == "awaiting_complete_observation"
    assert report["days"][2]["status"] == "not_due"
    assert report["missing_observation_dates"] == [(today-timedelta(days=1)).isoformat()]
    assert not root.exists()
