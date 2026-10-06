"""BBP01：三方法具名完整多批母體、原 v2 相容與新程序唯讀證據。"""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import inspect
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import app_module.rule_research_parent_capture as parent
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION as V2,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER as V3,
    feature_contract_for_version,
)
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter, RuleSampleCaptureError, SAFETY_RESERVE_BYTES, _digest, _json,
)
from tests.test_rule_research_parent_capture import _fixture

BB = "daily_market.close_above_bbands30_upper"


def _bb_fixture(tmp_path, monkeypatch, *, included=17, excluded=2):
    args, producer = _fixture(tmp_path, monkeypatch, included=included, excluded=excluded)
    with sqlite3.connect(args["db_path"]) as con:
        con.execute("ALTER TABLE technical_indicators ADD COLUMN BB_Upper TEXT")
        con.execute("UPDATE technical_indicators SET BB_Upper='100'")
        con.execute("UPDATE technical_indicators SET BB_Upper='101' WHERE 證券代號='1001'")
        con.execute("UPDATE technical_indicators SET BB_Upper='102' WHERE 證券代號='1002'")
        con.execute("UPDATE technical_indicators SET BB_Upper=NULL WHERE 證券代號='1003'")
        # 既有 65 筆縮至末段 29 筆，不補暖機資料。
        con.execute("DELETE FROM daily_prices WHERE 證券代號='1004' AND 日期 < (SELECT 日期 FROM daily_prices WHERE 證券代號='1004' ORDER BY 日期 DESC LIMIT 1 OFFSET 28)")
    args["contract_version"] = V3
    return args, producer


def _ready(args, result, *, version=None):
    return parent.read_parent_rule_sample_readiness(args["snapshot_root"], args["capture_root"],
        universe_path=args["universe_path"],
        identity_sha256=result["parent_capture"]["receipt"]["capture_identity_sha256"],
        contract_version=version)


def _pins(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def _db_pin(path):
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def test_v3_complete_17_members_all_three_denominators_retry_and_fresh_readonly(tmp_path, monkeypatch):
    args, _ = _bb_fixture(tmp_path, monkeypatch)
    before = _db_pin(args["db_path"])
    result = parent.produce_parent_rule_samples(**args)
    assert result["status"] == "complete", result
    ready = _ready(args, result)
    assert ready == _ready(args, result, version=V3)
    assert ready["feature_contract_version"] == V3
    assert ready["included_denominator"] == 17 and ready["represented_denominator"] == 19
    assert ready["captured_member_count"] == 19 and ready["uncaptured_member_count"] == 0
    assert ready["batches_count"] == 2
    assert all(len(b["included_stock_codes"]) <= 16 for b in ready["batches"])
    counts = {c["method_id"]: c for c in ready["method_counts"]}
    assert len(counts) == 3
    assert counts[BB] == {"method_id": BB, "matched": 13, "notmatched": 2, "unknown": 2, "excluded": 2, "uncaptured": 0}
    assert all(sum(c[s] for s in ("matched", "notmatched", "unknown", "excluded", "uncaptured")) == 19 for c in counts.values())
    assert ready["source_availability"] == ready["market_calendar"] == ready["outcome_maturity"] == "unknown"
    assert not ready["historical_pit_eligible"] and not ready["training_eligible"] and not ready["formal_eligible"]
    body = parent.BoundedRuleResearchParentWriter(args["capture_root"] / "parents").read(ready["parent_identity_sha256"])["capture"]
    assert body["feature_contract_version"] == V3
    plan = {"universe": body["universe"], "decision_cutoff": body["decision_cutoff"],
        "method_contracts_sha256": body["method_contracts_sha256"], "source_binding": body["source_binding"],
        "feature_contract_version": V3}
    assert body["plan_sha256"] == _digest(_json(plan).encode())
    contract = feature_contract_for_version(V3)
    writer = BoundedRuleResearchCaptureWriter(args["capture_root"] / "samples" / body["plan_sha256"])
    for b in body["batches"]:
        child = writer.read(b["capture_identity_sha256"])["capture"]
        manifest = DailyMarketSnapshotRepository(args["snapshot_root"] / "batches" / body["plan_sha256"] / b["batch_id"]).load_manifest(
            b["manifest_sha256"], b["cohort_id"], args["decision_cutoff"].date()).manifest
        assert child["feature_contract_version"] == manifest["feature_contract_version"] == V3
        assert child["method_contracts_sha256"] == manifest["method_contracts_sha256"] == contract.method_contracts_sha256
        members = set(b["included_stock_codes"]) | {e["stock_code"] for e in b["excluded_stock_codes"]}
        for method in contract.method_contracts.values():
            rows = [r for r in child["rows"] if r["method_id"] == method["method_id"]]
            assert {r["stock_code"] for r in rows} == members
    snapshot_pins, capture_pins = _pins(args["snapshot_root"]), _pins(args["capture_root"])
    args["as_of"] = datetime.fromisoformat(ready["as_of"])
    again = parent.produce_parent_rule_samples(**args)
    assert again["status"] == "complete", again
    assert again["sample_capture_status"] == "duplicate"
    assert again["sample_readiness"]["parent_identity_sha256"] == ready["parent_identity_sha256"]
    assert snapshot_pins == _pins(args["snapshot_root"])
    assert capture_pins == _pins(args["capture_root"])
    script = '''import json,sys
import app_module.rule_research_parent_capture as p
import app_module.daily_market_snapshot_source as source
import app_module.daily_market_snapshot_producer as producer
import sqlite3
def forbidden(*a,**k): raise AssertionError("唯讀不可開 DB/producer/loader")
p.SQLiteDailyMarketSnapshotSource = forbidden
p.DailyMarketSnapshotProducer = forbidden
p.produce_parent_rule_samples = forbidden
source.SQLiteDailyMarketSnapshotSource.load_input = forbidden
producer.DailyMarketSnapshotProducer.produce = forbidden
sqlite3.connect = forbidden
result=p.read_parent_rule_sample_readiness(sys.argv[1],sys.argv[2],universe_path=sys.argv[3],identity_sha256=sys.argv[4])
print(json.dumps(result,sort_keys=True))
'''
    process = subprocess.run([sys.executable, "-c", script, str(args["snapshot_root"]), str(args["capture_root"]),
        str(args["universe_path"]), ready["parent_identity_sha256"]], capture_output=True, text=True,
        encoding="utf-8", timeout=30, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == ready
    assert before == _db_pin(args["db_path"])
    assert snapshot_pins == _pins(args["snapshot_root"]) and capture_pins == _pins(args["capture_root"])


def test_cli_parent_v3_publication_and_inferred_or_expected_readonly(tmp_path, monkeypatch, capsys):
    import scripts.produce_daily_market_research_snapshot as cli
    args, _ = _bb_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_isolated_output", lambda _: args["snapshot_root"])
    argv = ["--db-path", str(args["db_path"]), "--output-root", str(args["snapshot_root"]),
        "--decision-cutoff", args["decision_cutoff"].isoformat(), "--parent-universe-config", str(args["universe_path"]),
        "--capture-root", str(args["capture_root"]), "--capture-as-of", "observed-now", "--include-bbands30-upper"]
    assert cli.main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    assert len(first["sample_readiness"]["method_counts"]) == 3
    argv[1] = str(tmp_path / "absent.db")
    argv[11] = first["sample_readiness"]["as_of"]
    argv += ["--read-parent-identity", first["sample_readiness"]["parent_identity_sha256"]]
    def forbidden(*a, **kw):
        raise AssertionError("唯讀不可開 DB 或 producer")
    monkeypatch.setattr(parent, "produce_parent_rule_samples", forbidden)
    monkeypatch.setattr(parent, "SQLiteDailyMarketSnapshotSource", forbidden)
    monkeypatch.setattr(cli, "SQLiteDailyMarketSnapshotSource", forbidden)
    for flag in (True, False):
        actual = argv if flag else [v for v in argv if v != "--include-bbands30-upper"]
        assert cli.main(actual) == 0
        assert json.loads(capsys.readouterr().out)["sample_readiness"] == first["sample_readiness"]


@pytest.mark.parametrize("version", [V2, "", "unsupported", False, 3])
def test_explicit_wrong_read_version_rejected(tmp_path, monkeypatch, version):
    args, _ = _bb_fixture(tmp_path, monkeypatch)
    result = parent.produce_parent_rule_samples(**args)
    assert result["status"] == "complete", result
    with pytest.raises(ValueError):
        _ready(args, result, version=version)


@pytest.mark.parametrize("version", ["", "unsupported", False, 3])
def test_invalid_production_version_rejected_before_io(tmp_path, monkeypatch, version):
    args, _ = _bb_fixture(tmp_path, monkeypatch)
    args["contract_version"] = version
    def forbidden(*a, **kw):
        raise AssertionError("非法版號不可讀來源")
    monkeypatch.setattr(parent, "SQLiteDailyMarketSnapshotSource", forbidden)
    with pytest.raises(ValueError):
        parent.produce_parent_rule_samples(**args)
    assert not args["snapshot_root"].exists() and not args["capture_root"].exists()


@pytest.mark.parametrize("fault", ["mixed_version", "missing_batch", "source_revision", "cancel"])
def test_v3_incomplete_never_reports_full_controls_and_safe_retry(tmp_path, monkeypatch, fault):
    args, base = _bb_fixture(tmp_path, monkeypatch)
    calls, cancelled = [0], [False]
    class FaultProducer(base):
        def produce(self, **kw):
            calls[0] += 1
            if calls[0] == 2 and fault == "missing_batch":
                raise OSError("第二批未發布")
            if calls[0] == 2 and fault == "mixed_version":
                kw["contract_version"] = V2
            result = super().produce(**kw)
            if calls[0] == 1 and fault == "source_revision":
                info = args["db_path"].stat()
                os.utime(args["db_path"], ns=(info.st_atime_ns, info.st_mtime_ns + 1000000))
            if calls[0] == 1 and fault == "cancel":
                cancelled[0] = True
            return result
    monkeypatch.setattr(parent, "DailyMarketSnapshotProducer", FaultProducer)
    result = parent.produce_parent_rule_samples(**args, cancel_callback=lambda: cancelled[0])
    assert result["status"] in {"incomplete", "cancelled"}, result
    ready = _ready(args, result)
    assert ready["status"] == "saved_incomplete"
    assert ready["uncaptured_member_count"] > 0 and len(ready["method_counts"]) == 3
    assert all(sum(c[s] for s in ("matched", "notmatched", "unknown", "excluded", "uncaptured")) == 19 for c in ready["method_counts"])
    if fault == "mixed_version":
        assert result["production"][1]["error_code"] == "parent_child_feature_version_mismatch"
        assert ready["captured_member_count"] == 11
    if fault == "cancel":
        monkeypatch.setattr(parent, "DailyMarketSnapshotProducer", base)
        retry = parent.produce_parent_rule_samples(**args)
        assert retry["status"] == "complete", retry
        assert retry["production"][0]["production_status"] == "unchanged"


@pytest.mark.parametrize("damage", ["method", "missing_batch", "version", "null_version"])
def test_rehashed_v3_parent_damage_is_rejected(tmp_path, monkeypatch, damage):
    args, _ = _bb_fixture(tmp_path, monkeypatch)
    result = parent.produce_parent_rule_samples(**args)
    writer = parent.BoundedRuleResearchParentWriter(args["capture_root"] / "parents")
    body = deepcopy(writer.read(result["sample_readiness"]["parent_identity_sha256"])["capture"])
    if damage == "method":
        body["method_contracts"]["close_above_bbands30_upper"]["parameters"]["timeperiod"] = 31
        body["method_contracts_sha256"] = _digest(_json(body["method_contracts"]).encode())
        body["plan_sha256"] = parent._plan(body["universe"], body["decision_cutoff"], body["method_contracts_sha256"], body["source_binding"], V3)
        for b in body["batches"]:
            b["cohort_id"] = f"{body['universe']['value']['universe_id']}:{b['batch_id']}:{body['plan_sha256'][:12]}"
    elif damage == "missing_batch":
        body["batches"].pop()
    else:
        body["feature_contract_version"] = V2 if damage == "version" else None
    body["capture_identity_sha256"] = parent._parent_identity(body)
    artifact = parent.RuleResearchParentCapture(_json(body))
    if damage == "method":
        writer.write(artifact, revalidate=lambda: artifact)
        with pytest.raises(RuleSampleCaptureError, match="parent_method_changed"):
            parent.read_parent_rule_sample_readiness(args["snapshot_root"], args["capture_root"],
                universe_path=args["universe_path"], identity_sha256=artifact.identity_sha256)
    else:
        with pytest.raises(ValueError):
            artifact.to_dict()


def test_v2_parent_body_plan_and_original_artifacts_unchanged_when_v3_added(tmp_path, monkeypatch):
    args, _ = _bb_fixture(tmp_path, monkeypatch)
    args["contract_version"] = None
    legacy = parent.produce_parent_rule_samples(**args)
    assert legacy["status"] == "complete", legacy
    ready = _ready(args, legacy, version=V2)
    assert "feature_contract_version" not in ready and len(ready["method_counts"]) == 2
    body = parent.BoundedRuleResearchParentWriter(args["capture_root"] / "parents").read(ready["parent_identity_sha256"])["capture"]
    assert set(body) == {"schema_version", "universe", "method_contracts", "method_contracts_sha256", "source_binding",
        "source_binding_sha256", "plan_sha256", "snapshot_root", "capture_root", "decision_cutoff", "as_of",
        "observed_at", "batches", "status", "source_status", "error_code", "policy", "capture_identity_sha256"}
    assert body["method_contracts_sha256"] == "029bcb5ada592619d9748d327eef509db0642a1c6904b652b31f186027025dc5"
    old_plan = {"universe": body["universe"], "decision_cutoff": body["decision_cutoff"],
        "method_contracts_sha256": body["method_contracts_sha256"], "source_binding": body["source_binding"]}
    assert body["plan_sha256"] == _digest(_json(old_plan).encode())
    before_snapshots, before_captures = _pins(args["snapshot_root"]), _pins(args["capture_root"])
    before_db = _db_pin(args["db_path"])
    args["contract_version"] = V3
    new = parent.produce_parent_rule_samples(**args)
    assert new["status"] == "complete", new
    after_snapshots, after_captures = _pins(args["snapshot_root"]), _pins(args["capture_root"])
    assert all(after_snapshots[k] == v for k, v in before_snapshots.items())
    assert all(after_captures[k] == v for k, v in before_captures.items())
    assert before_db == _db_pin(args["db_path"])
    assert new["sample_readiness"]["parent_identity_sha256"] != ready["parent_identity_sha256"]
    assert _ready(args, legacy) == ready
    with pytest.raises(ValueError, match="parent_feature_version_mismatch"):
        _ready(args, legacy, version=V3)


def test_contract_keywords_limits_and_safety_reserve_stay_exact(tmp_path, monkeypatch):
    for function in (parent.produce_parent_rule_samples, parent.read_parent_rule_sample_readiness):
        parameter = inspect.signature(function).parameters["contract_version"]
        assert parameter.kind == inspect.Parameter.KEYWORD_ONLY and parameter.default is None
    assert parent.MAX_BATCHES == 16 and parent.MAX_PARENT_SOURCE_BYTES == 64 * 1024 * 1024
    assert SAFETY_RESERVE_BYTES == 200 * 1024**3
    args, _ = _bb_fixture(tmp_path, monkeypatch, included=257)
    with pytest.raises(ValueError):
        parent.produce_parent_rule_samples(**args)
    assert not args["snapshot_root"].exists()


def test_future_price_and_band_do_not_change_cutoff_features_or_tallies(tmp_path, monkeypatch):
    args, _ = _bb_fixture(tmp_path, monkeypatch)
    original = parent.produce_parent_rule_samples(**args)
    assert original["status"] == "complete", original
    def stocks(result):
        ready = result["sample_readiness"]
        body = parent.BoundedRuleResearchParentWriter(args["capture_root"] / "parents").read(ready["parent_identity_sha256"])["capture"]
        records = {}
        for b in body["batches"]:
            snapshot = DailyMarketSnapshotRepository(args["snapshot_root"] / "batches" / body["plan_sha256"] / b["batch_id"]).load_manifest(
                b["manifest_sha256"], b["cohort_id"], args["decision_cutoff"].date())
            for code, payload in snapshot.stock_snapshots.items():
                records[code] = (payload["input_fingerprint_sha256"], payload["features"], payload["conditions"])
        return records
    before = stocks(original)
    future = (args["decision_cutoff"].date() + timedelta(days=1)).isoformat()
    with sqlite3.connect(args["db_path"]) as con:
        for code in before:
            con.execute("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", (future, code, "10000", "20000", "1", "19000", 999999))
            con.execute("INSERT INTO technical_indicators VALUES (?,?,?,?,?)", (future, code, "19000", "19000", "20000"))
    after = parent.produce_parent_rule_samples(**args)
    assert after["status"] == "complete", after
    assert stocks(after) == before
    assert after["sample_readiness"]["method_counts"] == original["sample_readiness"]["method_counts"]
    assert _ready(args, original) == original["sample_readiness"]
