"""SQLite producer→exact parent→來源 adapter→atomic outcome→日報/UI 重讀。"""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import pytest

from app_module.rule_research_forward_store import BoundedForwardOutcomeWriter, RUNTIME_SCHEMA, read_forward_receipt, run_forward_isolated
from app_module.rule_research_observation_acceptance import OBSERVATION_POLICY_SCHEMA, preview_or_accept_observation, read_observation_days
from app_module.rule_research_parent_capture import produce_parent_rule_samples
from tests.test_official_trading_calendar_cache import _cache
from tests.test_rule_research_parent_capture import _fixture
from tests.test_rule_research_observation_acceptance import context as observation_context
from tests.test_rule_research_daily_owner import ctx as daily_context


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    # Windows 的 fixture 測試名稱 + 多層 SHA 路徑可能超過 260；保留短隔離 root，不清理歷史。
    tmp_path = Path(tempfile.mkdtemp(prefix="u21s-"))
    args, _ = _fixture(tmp_path, monkeypatch, included=2, excluded=1)
    result = produce_parent_rule_samples(**args)
    assert result["status"] == "complete", result
    parent = args["capture_root"] / "parents" / result["parent_capture"]["receipt"]["capture_identity_sha256"] / "receipt.json"
    day = args["decision_cutoff"].date()
    with sqlite3.connect(args["db_path"]) as con:
        for offset in range(1, 36):
            for code in ("1000", "1001"):
                con.execute("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", ((day+timedelta(days=offset)).isoformat(), code, "101", "110", "100", "105", 1000))
    calendar = tmp_path / "calendar" / "cache.json"
    _cache(calendar)
    config = {"schema_version": RUNTIME_SCHEMA, "parent_receipt": str(parent), "source_db": str(args["db_path"]),
        "calendar_cache": str(calendar), "as_of_date": datetime.now(timezone.utc).date().isoformat(),
        "cost_policy": None, "benchmark": None, "outcome_root": str(tmp_path / "outcomes")}
    runtime = tmp_path / "forward-runtime.json"
    runtime.write_text(json.dumps(config), encoding="utf-8")
    policy = {"schema_version": OBSERVATION_POLICY_SCHEMA, "policy_id": "controlled", "version": "1",
        "timezone": "Asia/Taipei", "decision_cutoff_time": "16:00:00", "observation_start_time": "16:00:00",
        "observation_end_time": "23:59:59", "expected_observation_dates": [day.isoformat()],
        "universe_template_source": str(args["universe_path"]), "research_only": True}
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    acceptance = tmp_path / "acceptance"
    monkeypatch.setattr(BoundedForwardOutcomeWriter, "_free_bytes", lambda self: 1000 * 1024 ** 3)
    return args, parent, config, runtime, policy_path, acceptance


def test_end_to_end_sqlite_store_ui_daily_and_new_process(pipeline):
    args, parent, config, runtime, policy, acceptance = pipeline
    before = {p: p.read_bytes() for p in args["capture_root"].rglob("*") if p.is_file()}
    db_before = hashlib.sha256(args["db_path"].read_bytes()).hexdigest()
    result = run_forward_isolated(runtime, execute=True)
    assert result["status"] == "saved", result
    assert result["save_status"] == "published"
    p = result["projection"]
    assert p["population"]["represented_denominator"] == 3
    assert all(h["calculation_status"] == "ready_research" for m in p["members"] if m["stock_code"] == "1000" for h in m["horizons"])
    h = p["members"][0]["horizons"][0]
    assert h["target"]["gross_return"]["integer_bp_half_even"] == 396
    assert h["target"]["net_return"]["integer_bp_half_even"] is None
    assert h["comparison"]["gross_excess_return"]["integer_bp_half_even"] is None
    again = run_forward_isolated(runtime, execute=True)
    assert again["save_status"] == "duplicate", again
    assert again["identity_sha256"] == result["identity_sha256"]
    from ui_qt.rule_research_parent_receipt_dialog import read_parent_receipt_selection
    shown = read_parent_receipt_selection(str(parent), outcome_input_path=result["receipt_path"])
    assert shown["outcome"]["projection"] == p
    from app_module.rule_research_forward_store import read_parent_forward_revisions
    revisions = read_parent_forward_revisions(config["outcome_root"], parent.parent.name, evaluated_at=datetime.now(timezone.utc))
    assert revisions[0]["decision_date"] == args["decision_cutoff"].date().isoformat()
    script = "import json,sys; from app_module.rule_research_forward_store import read_forward_receipt; print(json.dumps(read_forward_receipt(*sys.argv[1:]),sort_keys=True))"
    child = subprocess.run([sys.executable, "-c", script, str(parent), result["receipt_path"]], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout)["projection"] == p
    assert before == {p: p.read_bytes() for p in args["capture_root"].rglob("*") if p.is_file()}
    assert hashlib.sha256(args["db_path"].read_bytes()).hexdigest() == db_before


@pytest.mark.parametrize("change", ["db_missing", "calendar_missing", "cost_float", "benchmark", "relative", "cancel", "capacity"])
def test_failures_never_fabricate_or_publish(pipeline, monkeypatch, change):
    _, _, config, runtime, policy, acceptance = pipeline
    if change == "db_missing": config["source_db"] += ".missing"
    elif change == "calendar_missing": config["calendar_cache"] += ".missing"
    elif change == "cost_float": config["cost_policy"] = {"version": "1", "formula_id": "proportional_entry_add_exit_deduct.v1", "target_entry_bp": 1.5, "target_exit_bp": None, "benchmark_entry_bp": None, "benchmark_exit_bp": None}
    elif change == "benchmark": config["benchmark"] = {"instrument_id": "invented"}
    elif change == "relative": config["source_db"] = "source.db"
    elif change == "capacity": monkeypatch.setattr(BoundedForwardOutcomeWriter, "_free_bytes", lambda self: 1)
    runtime.write_text(json.dumps(config), encoding="utf-8")
    result = run_forward_isolated(runtime, execute=True, cancel_callback=lambda: change == "cancel")
    assert result["status"] in {"blocked", "cancelled"}, result
    assert result["saved"] is False and not Path(config["outcome_root"]).exists()
    from app_module.rule_research_forward_store import read_parent_forward_revisions
    assert read_parent_forward_revisions(config["outcome_root"], "0"*64, evaluated_at=datetime.now(timezone.utc)) == []


def test_source_revision_missing_anchor_retains_history(pipeline):
    args, parent, config, runtime, policy, acceptance = pipeline
    first = run_forward_isolated(runtime, execute=True)
    assert first["status"] == "saved", first
    old = Path(first["receipt_path"]).parent / "capture.json"
    old_bytes = old.read_bytes()
    with sqlite3.connect(args["db_path"]) as con:
        con.execute("UPDATE daily_prices SET 收盤價='102' WHERE 證券代號='1000' AND 日期=?", (args["decision_cutoff"].date().isoformat(),))
    revised = run_forward_isolated(runtime, execute=True)
    assert revised["status"] == "saved" and revised["identity_sha256"] != first["identity_sha256"], revised
    assert "original_decision_price_revision_or_missing" in [i["reason"] for i in revised["source_contract"]["issues"]]
    assert all(h["target"]["gross_return"]["integer_bp_half_even"] is None for m in revised["projection"]["members"] if m["stock_code"] == "1000" for h in m["horizons"])
    assert old.read_bytes() == old_bytes
    assert read_forward_receipt(parent, first["receipt_path"])["projection"] == first["projection"]
    from app_module.rule_research_forward_store import read_parent_forward_revisions
    assert len(read_parent_forward_revisions(config["outcome_root"], parent.parent.name, evaluated_at=datetime.now(timezone.utc))) == 2


def test_tamper_exact_parent_and_partial_rejected(pipeline):
    _, parent, config, runtime, _, _ = pipeline
    result = run_forward_isolated(runtime, execute=True)
    assert result["status"] == "saved", result
    capture = Path(result["receipt_path"]).parent / "capture.json"
    capture.write_bytes(capture.read_bytes()+b" ")
    with pytest.raises(ValueError):
        read_forward_receipt(parent, result["receipt_path"])


def test_current_day_acceptance_daily_same_parent_and_pending(tmp_path, monkeypatch):
    from datetime import time
    from zoneinfo import ZoneInfo
    short = Path(tempfile.mkdtemp(prefix="u21d-"))
    args, _ = _fixture(short, monkeypatch, included=2, excluded=1)
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    shift = (today - args["decision_cutoff"].date()).days
    with sqlite3.connect(args["db_path"]) as con:
        for table in ("daily_prices", "technical_indicators"):
            con.execute(f'UPDATE {table} SET 日期=date(日期,?)', (f'{shift:+d} days',))
    universe = json.loads(args["universe_path"].read_text(encoding="utf-8"))
    universe["as_of_date"] = today.isoformat()
    args["universe_path"].write_text(json.dumps(universe), encoding="utf-8")
    args["decision_cutoff"] = datetime.combine(today, time(0), tzinfo=ZoneInfo("Asia/Taipei"))
    produced = produce_parent_rule_samples(**args)
    assert produced["status"] == "complete", produced
    parent = args["capture_root"] / "parents" / produced["parent_capture"]["receipt"]["capture_identity_sha256"] / "receipt.json"
    calendar = short / "calendar/cache.json"
    _cache(calendar)
    config = {"schema_version": RUNTIME_SCHEMA, "parent_receipt": str(parent), "source_db": str(args["db_path"]),
        "calendar_cache": str(calendar), "as_of_date": datetime.now(timezone.utc).date().isoformat(),
        "cost_policy": None, "benchmark": None, "outcome_root": str(short / "outcomes")}
    runtime = short / "runtime.json"
    runtime.write_text(json.dumps(config), encoding="utf-8")
    policy = {"schema_version": OBSERVATION_POLICY_SCHEMA, "policy_id": "today", "version": "1", "timezone": "Asia/Taipei",
        "decision_cutoff_time": "00:00:00", "observation_start_time": "00:00:00", "observation_end_time": "23:59:59",
        "expected_observation_dates": [today.isoformat()], "universe_template_source": str(args["universe_path"]), "research_only": True}
    policy_path = short / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    root = short / "acceptance"
    preview_or_accept_observation(policy_path, parent, root, accept=True, evaluated_at=datetime.now(timezone.utc))
    empty = read_observation_days(policy_path, root, evaluated_at=datetime.now(timezone.utc), outcome_root=config["outcome_root"])
    assert empty["days"][0]["records"][0]["forward_status"] == "awaiting_source_or_outcome"
    monkeypatch.setattr(BoundedForwardOutcomeWriter, "_free_bytes", lambda self: 1000 * 1024 ** 3)
    saved = run_forward_isolated(runtime, execute=True)
    assert saved["status"] == "saved", saved
    report = read_observation_days(policy_path, root, evaluated_at=datetime.now(timezone.utc), outcome_root=config["outcome_root"])
    record = report["days"][0]["records"][0]
    assert record["forward_status"] == "saved_revisions" and record["parent_identity_sha256"] == parent.parent.name
    assert record["forward_outcomes"][0]["method_horizon_status_counts"]["pending"] == 12
    assert report["days"][0]["accepted_count"] == 1


def test_cancel_after_publication_reports_preserved_receipt(pipeline, monkeypatch):
    _, _, _, runtime, _, _ = pipeline
    import app_module.rule_research_forward_store as module
    monkeypatch.setattr(module, "read_forward_receipt", lambda *a, **k: {"cancelled": True})
    result = run_forward_isolated(runtime, execute=True)
    assert result["status"] == "cancelled" and result["saved"] is True
    assert Path(result["receipt_path"]).is_file()


def test_full_multibatch_population_fits_existing_atomic_budget(monkeypatch):
    short = Path(tempfile.mkdtemp(prefix="u21m-"))
    args, _ = _fixture(short, monkeypatch)
    produced = produce_parent_rule_samples(**args)
    assert produced["status"] == "complete", produced
    parent = args["capture_root"] / "parents" / produced["parent_capture"]["receipt"]["capture_identity_sha256"] / "receipt.json"
    calendar = short / "calendar/cache.json"
    _cache(calendar)
    config = {"schema_version": RUNTIME_SCHEMA, "parent_receipt": str(parent), "source_db": str(args["db_path"]),
        "calendar_cache": str(calendar), "as_of_date": datetime.now(timezone.utc).date().isoformat(),
        "cost_policy": None, "benchmark": None, "outcome_root": str(short / "outcomes")}
    runtime = short / "runtime.json"
    runtime.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(BoundedForwardOutcomeWriter, "_free_bytes", lambda self: 1000 * 1024 ** 3)
    result = run_forward_isolated(runtime, execute=True)
    assert result["status"] == "saved", result
    reread = read_forward_receipt(parent, result["receipt_path"])
    assert reread["projection"]["population"]["represented_denominator"] == 19
    assert len(reread["projection"]["members"]) == 38
    assert Path(result["receipt_path"]).with_name("capture.json").stat().st_size <= 256*1024


def test_explicit_integer_cost_does_not_fill_benchmark(pipeline):
    _, _, config, runtime, _, _ = pipeline
    config["cost_policy"] = {"version": "explicit-research-1", "formula_id": "proportional_entry_add_exit_deduct.v1",
        "target_entry_bp": 15, "target_exit_bp": 30, "benchmark_entry_bp": None, "benchmark_exit_bp": None}
    runtime.write_text(json.dumps(config), encoding="utf-8")
    result = run_forward_isolated(runtime, execute=True)
    assert result["status"] == "saved", result
    h = result["projection"]["members"][0]["horizons"][0]
    assert h["target"]["net_return"]["integer_bp_half_even"] is not None
    assert h["comparison"]["net_excess_return"]["integer_bp_half_even"] is None


def test_compressed_projection_decompression_bound():
    import base64, zlib
    from app_module.rule_research_forward_store import _projection, MAX_PROJECTION_BYTES
    value = {"encoding": "zlib-json.v1", "raw_bytes": 1, "sha256": "0"*64,
        "data_base64": base64.b64encode(zlib.compress(b"x"*(MAX_PROJECTION_BYTES+1))).decode("ascii")}
    with pytest.raises(ValueError, match="compression_invalid"):
        _projection({"projection": value})


def test_existing_daily_cli_readonly_outcome_overlay(daily_context, monkeypatch, capsys):
    from scripts.scheduled.run_rule_research_daily_isolated import main
    path, day, runtime, args, _ = daily_context
    outcome_root = path.parent / "forward-outcomes"
    argv = ["--runtime-config", str(path), "--target-date", day.isoformat(), "--execute-isolated", "--outcome-root", str(outcome_root)]
    assert main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    record = first["day_readiness"]["days"][-1]["records"][0]
    assert record["forward_status"] == "awaiting_source_or_outcome"
    parent = Path(runtime["capture_root"]) / "parents" / record["parent_identity_sha256"] / "receipt.json"
    calendar = path.parent / "calendar/cache.json"
    _cache(calendar)
    config = {"schema_version": RUNTIME_SCHEMA, "parent_receipt": str(parent), "source_db": str(args["db_path"]),
        "calendar_cache": str(calendar), "as_of_date": datetime.now(timezone.utc).date().isoformat(),
        "cost_policy": None, "benchmark": None, "outcome_root": str(outcome_root)}
    forward_runtime = path.parent / "forward-runtime.json"
    forward_runtime.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(BoundedForwardOutcomeWriter, "_free_bytes", lambda self: 1000 * 1024 ** 3)
    saved = run_forward_isolated(forward_runtime, execute=True)
    assert saved["status"] == "saved", saved
    assert main(argv) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["status"] == "already_observed" and again["forward_day_readiness_status"] == "verified"
    record = again["day_readiness"]["days"][-1]["records"][0]
    assert record["forward_status"] == "saved_revisions"
    assert record["forward_outcomes"][0]["result_identity_sha256"] == saved["projection"]["result_identity_sha256"]
