"""明示設定→actual source→保存→唯讀讀回；隔離fixtures不代替公開資料驗證。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app_module.rule_research_benchmark_settings import SETTINGS_SCHEMA
from app_module.rule_research_forward_store import (
    BENCHMARK_RUNTIME_SCHEMA, SavedForwardOutcome, read_forward_receipt, run_forward_isolated,
)
from app_module.rule_research_sample_capture import _identity, _json
from tests.test_rule_research_forward_isolated import pipeline


def _prepare(pipeline):
    args, parent, config, runtime, *_ = pipeline
    baseline = run_forward_isolated(runtime)
    assert baseline["status"] == "preflight_passed", baseline
    dates = sorted({point["trade_date"] for point in baseline["projection"]["price_points"]})
    database = runtime.parent / "explicit-index.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE market_indices (index_name TEXT, date TEXT, close_index TEXT)")
        connection.executemany("INSERT INTO market_indices VALUES (?,?,?)", [("fixture-index", day, "100" if i == 0 else "102") for i, day in enumerate(dates)])
    settings = {"schema_version": SETTINGS_SCHEMA, "version": "fixture-v1", "database_path": str(database),
                "source_identity": "fixture-public-market-table.v1", "benchmark_name": "fixture-index",
                "currency": "TWD", "unit": "index", "price_basis": "unadjusted_close",
                "corporate_action_basis": "unadjusted-research-basis", "availability_by_date": {day: day for day in dates},
                "target_currency": "TWD", "target_price_basis": "unadjusted_close", "target_corporate_action_basis": "unadjusted-research-basis",
                "expected_rowset_sha256": None, "expected_decision_row_sha256": None, "target_source_pin_sha256": None}
    config.update(schema_version=BENCHMARK_RUNTIME_SCHEMA, benchmark=settings,
                  cost_policy={"version": "fixture-cost-v2", "formula_id": "proportional_entry_add_exit_deduct.v1",
                               "target_entry_bp": 10, "target_exit_bp": 20, "benchmark_entry_bp": 0, "benchmark_exit_bp": 0})
    runtime.write_text(json.dumps(config), encoding="utf-8")
    preview = run_forward_isolated(runtime)
    assert preview["status"] == "preflight_passed", preview
    result = preview["source_contract"]["benchmark_result"]
    assert result["status"] == "unknown" and preview["projection"]["benchmark"] is None
    settings.update(expected_rowset_sha256=result["observed_rowset_sha256"],
                    expected_decision_row_sha256=result["observed_decision_row_sha256"],
                    target_source_pin_sha256=preview["source_contract"]["target_source_pin_sha256"])
    runtime.write_text(json.dumps(config), encoding="utf-8")
    return args, parent, config, runtime, database


def test_qualified_source_cost_store_new_process_and_old_null_compat(pipeline):
    args, parent, config, runtime, benchmark_db = _prepare(pipeline)
    pins = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (args["db_path"], benchmark_db)}
    result = run_forward_isolated(runtime, execute=True)
    assert result["status"] == "saved", result
    assert result["source_contract"]["benchmark_result"]["status"] == "qualified_research"
    assert result["projection"]["benchmark"]["instrument_id"] == "market_indices.fixture-index"
    horizon = next(m for m in result["projection"]["members"] if m["stock_code"] == "1000")["horizons"][0]
    assert horizon["comparison"]["basis_comparable"] is True
    assert horizon["comparison"]["gross_excess_return"]["integer_bp_half_even"] == 196
    assert horizon["comparison"]["net_excess_return"]["integer_bp_half_even"] is not None
    assert result["projection"]["cost_policy"]["version"] == "fixture-cost-v2"
    assert result["qualification"]["historical_pit_eligible"] is False
    assert run_forward_isolated(runtime, execute=True)["save_status"] == "duplicate"
    script = "import json,sys; from app_module.rule_research_forward_store import read_forward_receipt; print(json.dumps(read_forward_receipt(*sys.argv[1:])))"
    child = subprocess.run([sys.executable, "-c", script, str(parent), result["receipt_path"]], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(child.stdout)["projection"] == result["projection"]
    assert pins == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in pins}
    config.update(benchmark=None, schema_version="rule-research-forward-isolated-runtime.v1")
    runtime.write_text(json.dumps(config), encoding="utf-8")
    legacy = run_forward_isolated(runtime, execute=True)
    assert legacy["status"] == "saved" and legacy["projection"]["benchmark"] is None
    assert read_forward_receipt(parent, legacy["receipt_path"])["projection"]["benchmark"] is None
    assert read_forward_receipt(parent, result["receipt_path"])["projection"] == result["projection"]


@pytest.mark.parametrize("change", ["other_source", "row_revision", "missing_day", "unknown_availability", "target_pin", "incompatible_basis", "cancel"])
def test_source_mix_missing_unknown_and_cancel_do_not_fabricate_excess(pipeline, change):
    args, parent, config, runtime, benchmark_db = _prepare(pipeline)
    settings = config["benchmark"]
    if change == "other_source":
        other = benchmark_db.with_name("other.sqlite")
        other.write_bytes(benchmark_db.read_bytes())
        settings["database_path"] = str(other)
    elif change in {"row_revision", "missing_day"}:
        with sqlite3.connect(benchmark_db) as connection:
            if change == "row_revision": connection.execute("UPDATE market_indices SET close_index='110'")
            else: connection.execute("DELETE FROM market_indices WHERE date=(SELECT max(date) FROM market_indices)")
    elif change == "unknown_availability": settings["availability_by_date"] = {}
    elif change == "target_pin": settings["target_source_pin_sha256"] = "f" * 64
    elif change == "incompatible_basis": settings["corporate_action_basis"] = "adjusted-total-return"
    runtime.write_text(json.dumps(config), encoding="utf-8")
    result = run_forward_isolated(runtime, cancel_callback=lambda: change == "cancel")
    assert not result["saved"]
    if result["status"] == "preflight_passed":
        assert result["projection"]["benchmark"] is None
        assert result["source_contract"]["benchmark_result"]["status"] in {"unknown", "rejected"}
        assert all(h["comparison"]["gross_excess_return"]["integer_bp_half_even"] is None for m in result["projection"]["members"] for h in m["horizons"])
    else:
        assert result["status"] in {"blocked", "cancelled"}, result


def test_saved_revision_and_benchmark_source_substitution_rejected(pipeline):
    _, parent, config, runtime, benchmark_db = _prepare(pipeline)
    first = run_forward_isolated(runtime, execute=True)
    assert first["status"] == "saved", first
    body_path = Path(first["receipt_path"]).parent / "capture.json"
    old = body_path.read_bytes()
    with sqlite3.connect(benchmark_db) as connection:
        connection.execute("UPDATE market_indices SET close_index='103' WHERE date=(SELECT max(date) FROM market_indices)")
    settings = config["benchmark"]
    settings.update(expected_rowset_sha256=None, expected_decision_row_sha256=None)
    runtime.write_text(json.dumps(config), encoding="utf-8")
    preview = run_forward_isolated(runtime)
    settings.update(expected_rowset_sha256=preview["source_contract"]["benchmark_result"]["observed_rowset_sha256"],
                    expected_decision_row_sha256=preview["source_contract"]["benchmark_result"]["observed_decision_row_sha256"])
    runtime.write_text(json.dumps(config), encoding="utf-8")
    second = run_forward_isolated(runtime, execute=True)
    assert second["status"] == "saved" and second["identity_sha256"] != first["identity_sha256"], second
    assert body_path.read_bytes() == old
    assert read_forward_receipt(parent, first["receipt_path"])["projection"] == first["projection"]
    forged = json.loads(old)
    forged["source_contract"]["benchmark_result"]["prices"][0]["source_identity"] = "other-source"
    forged["capture_identity_sha256"] = _identity(forged)
    with pytest.raises(ValueError, match="benchmark_points_mismatch"):
        SavedForwardOutcome(_json(forged)).to_dict()


def test_cli_explicit_settings_selection_is_sealed_and_null_is_explicit(pipeline):
    _, parent, config, runtime, _ = _prepare(pipeline)
    selected = runtime.parent / "chosen-benchmark.json"
    selected.write_text(json.dumps(config["benchmark"]), encoding="utf-8")
    config.update(benchmark=None, schema_version="rule-research-forward-isolated-runtime.v1")
    runtime.write_text(json.dumps(config), encoding="utf-8")
    result = run_forward_isolated(runtime, execute=True, benchmark_settings_path=selected)
    assert result["status"] == "saved", result
    capture = json.loads((Path(result["receipt_path"]).parent / "capture.json").read_bytes())
    assert capture["runtime_pin"]["selected_benchmark_settings"]["source_sha256"] == hashlib.sha256(selected.read_bytes()).hexdigest()
    assert capture["runtime_pin"]["original_value"]["benchmark"] is None
    assert run_forward_isolated(runtime, benchmark_unconfigured=True)["projection"]["benchmark"] is None
    assert run_forward_isolated(runtime, benchmark_settings_path=selected, benchmark_unconfigured=True)["status"] == "blocked"
    config["schema_version"] = "future-runtime.v99"
    runtime.write_text(json.dumps(config), encoding="utf-8")
    assert run_forward_isolated(runtime, benchmark_settings_path=selected)["status"] == "blocked"


def test_cancel_after_benchmark_query_then_retry_does_not_publish_partial(pipeline, monkeypatch):
    import app_module.rule_research_forward_source as source
    _, _, _, runtime, _ = _prepare(pipeline)
    original = source.load_explicit_market_benchmark
    cancelled = [False]
    def after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        cancelled[0] = True
        return result
    monkeypatch.setattr(source, "load_explicit_market_benchmark", after_read)
    result = run_forward_isolated(runtime, execute=True, cancel_callback=lambda: cancelled[0])
    assert result["status"] == "cancelled" and result["saved"] is False
    cancelled[0] = False
    monkeypatch.setattr(source, "load_explicit_market_benchmark", original)
    retry = run_forward_isolated(runtime, execute=True, cancel_callback=lambda: cancelled[0])
    assert retry["status"] == "saved", retry


def test_selected_settings_changed_during_read_are_rejected_before_publication(pipeline, monkeypatch):
    import app_module.rule_research_forward_source as source
    _, _, config, runtime, _ = _prepare(pipeline)
    selected = runtime.parent / "changing-settings.json"
    selected.write_text(json.dumps(config["benchmark"]), encoding="utf-8")
    original = source.load_explicit_market_benchmark
    def revision(*args, **kwargs):
        result = original(*args, **kwargs)
        selected.write_text(selected.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return result
    monkeypatch.setattr(source, "load_explicit_market_benchmark", revision)
    result = run_forward_isolated(runtime, execute=True, benchmark_settings_path=selected)
    assert result["status"] == "blocked" and not result["saved"]
    assert result["error_code"] == "forward_benchmark_settings_changed"
