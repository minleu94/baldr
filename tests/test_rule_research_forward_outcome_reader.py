"""保存收據→研究輸入→唯讀 consumer 的實際隔離驗收。"""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import subprocess
import sys

import pytest

from app_module.rule_research_forward_outcome_reader import read_saved_parent_forward_outcome, INPUT_SCHEMA
from app_module.rule_research_parent_capture import produce_parent_rule_samples
from tests.test_rule_research_parent_capture import _fixture
from tests.test_rule_research_forward_outcome import _market, _costs


@pytest.fixture
def forward_saved(tmp_path, monkeypatch):
    args, _ = _fixture(tmp_path, monkeypatch)
    result = produce_parent_rule_samples(**args)
    identity = result["parent_capture"]["receipt"]["capture_identity_sha256"]
    receipt = args["capture_root"] / "parents" / identity / "receipt.json"
    day = json.loads(args["universe_path"].read_text(encoding="utf-8"))["as_of_date"]
    codes = tuple(str(1000 + i) for i in range(17))
    calendar, points, benchmark = _market(date.fromisoformat(day), codes)
    value = {"schema_version": INPUT_SCHEMA, "parent_identity_sha256": identity,
             "decision_date": day, "as_of_date": datetime.now(timezone.utc).date().isoformat(),
             "calendar": calendar.to_payload(), "prices": [p.to_payload() for p in points],
             "benchmark": benchmark.to_payload(), "cost_policy": _costs(target_entry=15, target_exit=30, benchmark_entry=5, benchmark_exit=10).to_payload()}
    source = tmp_path / "forward.json"
    source.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return args, receipt, source, value


def test_actual_readonly_denominator_cost_and_new_process(forward_saved, monkeypatch):
    args, receipt, source, _ = forward_saved
    before = {p: p.read_bytes() for p in receipt.parents[2].parent.rglob("*") if p.is_file()}
    import app_module.rule_research_parent_capture as parent
    monkeypatch.setattr(parent, "SQLiteDailyMarketSnapshotSource", lambda *a, **k: pytest.fail("opened DB"))
    result = read_saved_parent_forward_outcome(str(receipt), str(source))
    p = result["projection"]
    assert p["population"]["represented_denominator"] == 19
    assert len(p["members"]) == 38 and p["population"]["selected_count"] is None
    h = next(m for m in p["members"] if m["stock_code"] == "1000")["horizons"][0]
    assert h["target"]["gross_return"]["integer_bp_half_even"] == 500
    assert h["target"]["net_return"]["integer_bp_half_even"] is not None
    assert h["comparison"]["net_excess_return"]["integer_bp_half_even"] is not None
    assert all(not p[k] for k in ("historical_pit_eligible", "formal_eligible", "training_eligible", "execution_eligible"))
    script = "import json,sys; from app_module.rule_research_forward_outcome_reader import read_saved_parent_forward_outcome; print(json.dumps(read_saved_parent_forward_outcome(*sys.argv[1:]),sort_keys=True))"
    child = subprocess.run([sys.executable, "-c", script, str(receipt), str(source)], capture_output=True, text=True, encoding="utf-8", timeout=25)
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout) == result
    assert before == {p: p.read_bytes() for p in receipt.parents[2].parent.rglob("*") if p.is_file()}


def test_explicit_input_named_receipt_remains_supported(forward_saved):
    _, parent, source, _ = forward_saved
    selected = source.with_name("receipt.json")
    selected.write_bytes(source.read_bytes())
    assert read_saved_parent_forward_outcome(str(parent), str(selected))["projection"] == read_saved_parent_forward_outcome(str(parent), str(source))["projection"]


@pytest.mark.parametrize("change,error", [
    ("parent", "parent_mismatch"), ("price_number", "decimal_text"), ("cost_float", "target_entry_bp_invalid"),
    ("future", "as_of_in_future"), ("extra", "schema_invalid"), ("duplicate", "duplicate_key"),
])
def test_input_rejections(forward_saved, change, error):
    _, receipt, source, original = forward_saved
    value = deepcopy(original)
    if change == "parent": value["parent_identity_sha256"] = "0" * 64
    elif change == "price_number": value["prices"][0]["price"] = 100
    elif change == "cost_float": value["cost_policy"]["target_entry_bp"] = 1.5
    elif change == "future": value["as_of_date"] = "2099-01-01"
    elif change == "extra": value["use_latest"] = True
    raw = json.dumps(value)
    if change == "duplicate": raw = raw[:-1] + ',"schema_version":"x"}'
    source.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        read_saved_parent_forward_outcome(str(receipt), str(source))


def test_unknown_cost_calendar_and_missing_endpoint(forward_saved):
    _, receipt, source, value = forward_saved
    value["cost_policy"] = None
    value["prices"] = [p for p in value["prices"] if not (p["instrument_id"] == "1000" and p["trade_date"] == value["calendar"]["trading_dates"][5])]
    source.write_text(json.dumps(value), encoding="utf-8")
    projection = read_saved_parent_forward_outcome(str(receipt), str(source))["projection"]
    rows = [m for m in projection["members"] if m["stock_code"] in ("1000", "1001")]
    assert {r["horizons"][0]["calculation_status"] for r in rows} == {"unavailable", "ready_research"}
    assert all(r["horizons"][0]["target"]["net_return"]["decimal"] is None for r in rows)
    value["calendar"] = {"known": False, "complete": False, "trading_dates": [], "coverage_start": None,
                         "coverage_end": None, "source_identity": None, "available_date": None}
    source.write_text(json.dumps(value), encoding="utf-8")
    projection = read_saved_parent_forward_outcome(str(receipt), str(source))["projection"]
    assert next(m for m in projection["members"] if m["stock_code"] == "1000")["horizons"][0]["calculation_status"] == "unknown"


def test_cancel_and_input_revision_during_read(forward_saved, monkeypatch):
    _, receipt, source, _ = forward_saved
    assert read_saved_parent_forward_outcome(str(receipt), str(source), cancel_callback=lambda: True) == {"cancelled": True}
    import app_module.rule_research_forward_outcome_reader as reader
    original = reader.build_parent_rule_research_forward_outcome
    def changed(*a, **kw):
        result = original(*a, **kw)
        source.write_bytes(source.read_bytes() + b" ")
        return result
    monkeypatch.setattr(reader, "build_parent_rule_research_forward_outcome", changed)
    with pytest.raises(ValueError, match="source_changed_during_read"):
        read_saved_parent_forward_outcome(str(receipt), str(source))


def test_child_tamper_rejected(forward_saved):
    args, receipt, source, _ = forward_saved
    next((args["capture_root"] / "samples").rglob("capture.json")).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        read_saved_parent_forward_outcome(str(receipt), str(source))


def test_incomplete_parent_keeps_all_uncaptured_denominator(tmp_path, monkeypatch):
    args, producer = _fixture(tmp_path, monkeypatch)
    original = producer.produce
    calls = []
    def fail_second(self, *a, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("controlled second batch failure")
        return original(self, *a, **kw)
    monkeypatch.setattr(producer, "produce", fail_second)
    result = produce_parent_rule_samples(**args)
    identity = result["parent_capture"]["receipt"]["capture_identity_sha256"]
    source = tmp_path / "unknown.json"
    universe = json.loads(args["universe_path"].read_text(encoding="utf-8"))
    value = {"schema_version": INPUT_SCHEMA, "parent_identity_sha256": identity,
             "decision_date": universe["as_of_date"], "as_of_date": datetime.now(timezone.utc).date().isoformat(),
             "calendar": {"known": False, "complete": False, "trading_dates": [], "coverage_start": None,
                          "coverage_end": None, "source_identity": None, "available_date": None},
             "prices": [], "benchmark": None, "cost_policy": None}
    source.write_text(json.dumps(value), encoding="utf-8")
    receipt = args["capture_root"] / "parents" / identity / "receipt.json"
    projection = read_saved_parent_forward_outcome(str(receipt), str(source))["projection"]
    assert projection["cohort_status"] == "incomplete"
    assert len(projection["members"]) == 38
    assert all(counts["uncaptured"] == 19 for counts in projection["population"]["method_state_counts"].values())
    assert all(m["horizons"][0]["calculation_status"] == "uncaptured" for m in projection["members"])
