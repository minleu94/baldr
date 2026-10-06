"""完整 cohort 合成驗證；不授真自然 credit。"""
from copy import deepcopy
from functools import partial
import json
from pathlib import Path
import subprocess
import sys

import pytest
from test_personal_current_observed_h20_capture import make_bundle
from app_module.recommendation.personal_current_observed_h20_capture import (
    H20CaptureError, capture_personal_current_observed_h20_prediction, digest, encoded,
    read_personal_current_observed_h20_capture, read_pinned_json,
)
from app_module.recommendation.personal_current_observed_h20_outcome import read_personal_current_observed_h20_outcome
from app_module.recommendation.personal_h20_natural_outcome_batch import run_personal_h20_natural_outcome_batch


def cohort(tmp_path):
    root, source, contract, prediction = make_bundle(tmp_path)
    symbols = ["2330", "2454"]
    source["pins"]["cycle_source_date"] = source["decision_date"]
    source["feature_rows_by_symbol"]["2454"] = deepcopy(source["feature_rows_by_symbol"]["2330"])
    pins = []
    for symbol in symbols:
        output = deepcopy(prediction)
        output["request"]["symbol"] = symbol
        output["prediction_id"] = "personal-h20:" + digest(json.dumps(output["request"],
            sort_keys=True, separators=(",", ":")).encode())[7:]
        saved = capture_personal_current_observed_h20_prediction(root=root, source_binding=source,
            contract_binding=contract, symbol=symbol, source_verifier=lambda v: v,
            contract_verifier=lambda v: v, predictor=lambda: output)
        pins.append({"symbol": symbol, "path": saved["path"], "raw_sha256": saved["raw_sha256"],
            "sample_id": saved["sample_id"], "prediction_id": output["prediction_id"]})
    body = {"schema_version": "personal-h20-daily-manifest.v1", "status": "completed",
        "candidate_id": contract["candidate_id"], "contract_hash": contract["contract_hash"],
        "cycle_id": source["cycle_id"], "decision_date": source["decision_date"], "symbols": symbols,
        "captures": pins, "historical_pit_eligible": False, "formal_training_allowed": False,
        "production_action_allowed": False}
    directory = root / "h20_daily_receipts"
    directory.mkdir()
    manifest = directory / (digest(encoded(body))[7:] + ".json")
    manifest.write_bytes(encoded(body))
    args = dict(manifest_path=manifest, manifest_sha256=digest(encoded(body)), root=root,
        prediction_reader=partial(read_personal_current_observed_h20_capture,
            source_verifier=lambda v: v, contract_verifier=lambda v: v),
        source_verifier=lambda v: v, contract_verifier=lambda v: v,
        input_capture_verifier=lambda p, h: read_pinned_json(p, h),
        outcome_verifier=lambda p, h: read_pinned_json(p, h))
    entry = {"capture_id": "entry", "cycle_id": source["cycle_id"], "decision_date": source["decision_date"],
        "source_contract_binding": {"current_observed_feature_snapshot": {
            "cycle_terminal_sha256": source["cycle_terminal_sha256"],
            "snapshot_database_sha256": source["pins"]["snapshot_database_sha256"]}},
        "rows": [{"row_id": "row-" + s, "symbol": s, "decision_date": source["decision_date"],
            "feature_as_of_date": prediction["request"]["feature_as_of_date"],
            "feature_values": [1], "feature_ids": ["x"]} for s in symbols]}
    input_path = tmp_path / "entry.json"
    input_path.write_bytes(encoded(entry))
    outcome = {"capture_id": "entry", "capture_sha256": digest(encoded(entry)), "capture_path": str(input_path),
        "capture_cycle_id": source["cycle_id"], "decision_date": source["decision_date"], "horizon_sessions": 20,
        "historical_pit_eligible": False, "formal_training_allowed": False, "promotion_credit_created": False,
        "endpoint_date": "2026-11-04", "outcomes": [{"capture_row_id": "row-" + s, "symbol": s,
            "capture_decision_date": source["decision_date"], "stock_return_bp": 100} for s in symbols],
        "pending_rows": []}
    return args, body, entry, outcome


def attach(args, entry, outcome):
    file = Path(args["root"]).parent / "entry.json"
    file.write_bytes(encoded(entry))
    args.update(input_capture_path=file, input_capture_sha256=digest(encoded(entry)))
    outcome.update(capture_sha256=args["input_capture_sha256"])
    file = file.with_name("outcome.json")
    file.write_bytes(encoded(outcome))
    args.update(outcome_path=file, outcome_sha256=digest(encoded(outcome)))


def snapshot(args):
    return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(args["root"]).parent.rglob("*") if p.is_file()}


def test_full_pending_without_entry_and_no_writes(tmp_path):
    args, _, _, _ = cohort(tmp_path)
    before = snapshot(args)
    result = run_personal_h20_natural_outcome_batch(**args)
    assert result["status"] == "completed" and result["pending_count"] == 2
    assert result["processed_symbols"] == result["symbols"] and result["remaining_symbols"] == []
    assert all(r["reason"] == "exact_entry_capture_missing" for r in result["rows"])
    assert before == snapshot(args)


@pytest.mark.parametrize("mature", [0, 1, 2])
def test_full_mixed_and_mature_original_bp_idempotent_readback(tmp_path, mature):
    args, body, entry, outcome = cohort(tmp_path)
    outcome["pending_rows"] = [{"capture_row_id": row["capture_row_id"]} for row in outcome["outcomes"][mature:]]
    outcome["outcomes"] = outcome["outcomes"][:mature]
    attach(args, entry, outcome)
    before = snapshot(args)
    result = run_personal_h20_natural_outcome_batch(**args)
    assert result["matured_count"] == mature and result["pending_count"] == 2 - mature
    assert len(result["rows"]) == 2
    after = snapshot(args)
    assert all(after[p] == state for p, state in before.items())
    assert run_personal_h20_natural_outcome_batch(**args) == result
    assert snapshot(args) == after
    for row in result["rows"][:mature]:
        assert row["realized_gross_return_bp"] == 100 and row["error_bp"] == 20
        original = read_personal_current_observed_h20_outcome(row["saved_join_path"], root=args["root"],
            **{k: args[k] for k in ("source_verifier", "contract_verifier", "input_capture_verifier", "outcome_verifier")})
        assert original["sample_id"] == row["sample_id"]
    assert [r["sample_id"] for r in result["rows"]] == [p["sample_id"] for p in body["captures"]]


@pytest.mark.parametrize("target,key,value", [("entry", "decision_date", "2026-10-06"),
    ("entry", "cycle_id", "another"), ("outcome", "capture_id", "another"),
    ("outcome", "horizon_sessions", 19)])
def test_wrong_exact_join_fails_before_any_save(tmp_path, target, key, value):
    args, _, entry, outcome = cohort(tmp_path)
    if key == "decision_date":
        value = "2000-01-01"
    (entry if target == "entry" else outcome)[key] = value
    attach(args, entry, outcome)
    with pytest.raises(H20CaptureError):
        run_personal_h20_natural_outcome_batch(**args)
    assert not (Path(args["root"]) / "h20_outcome_joins").exists()


def test_tail_feature_mismatch_prevents_first_mature_save(tmp_path):
    args, _, entry, outcome = cohort(tmp_path)
    entry["rows"][1]["feature_values"] = [2]
    attach(args, entry, outcome)
    with pytest.raises(H20CaptureError, match="feature_identity"):
        run_personal_h20_natural_outcome_batch(**args)
    assert not (Path(args["root"]) / "h20_outcome_joins").exists()


@pytest.mark.parametrize("field", ["candidate_id", "contract_hash", "cycle_id", "decision_date"])
def test_manifest_scope_mismatch_rejected(tmp_path, field):
    args, body, _, _ = cohort(tmp_path)
    body[field] = "2000-01-01" if field == "decision_date" else "wrong"
    raw = encoded(body)
    file = Path(args["manifest_path"]).with_name(digest(raw)[7:] + ".json")
    file.write_bytes(raw)
    args.update(manifest_path=file, manifest_sha256=digest(raw))
    with pytest.raises(ValueError):
        run_personal_h20_natural_outcome_batch(**args)


def test_pin_tamper_missing_member_and_cancel(tmp_path):
    args, body, _, _ = cohort(tmp_path)
    with pytest.raises(InterruptedError):
        run_personal_h20_natural_outcome_batch(**args, cancelled=lambda: True)
    with pytest.raises(H20CaptureError, match="raw_pin"):
        run_personal_h20_natural_outcome_batch(**(args | {"manifest_sha256": "sha256:" + "b" * 64}))
    Path(body["captures"][1]["path"]).unlink()
    with pytest.raises(FileNotFoundError):
        run_personal_h20_natural_outcome_batch(**args)


def test_cancel_before_publish_preserves_full_denominator(tmp_path):
    args, _, entry, outcome = cohort(tmp_path)
    attach(args, entry, outcome)
    calls = 0
    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 5
    result = run_personal_h20_natural_outcome_batch(**args, cancelled=cancelled)
    assert result["status"] == "cancelled" and result["symbols"] == ["2330", "2454"]
    assert result["processed_symbols"] == [] and result["remaining_symbols"] == result["symbols"]
    assert not (Path(args["root"]) / "h20_outcome_joins").exists()


def test_new_process_same_original_cohort(tmp_path):
    args, _, entry, outcome = cohort(tmp_path)
    attach(args, entry, outcome)
    first = run_personal_h20_natural_outcome_batch(**args)
    request = {k: str(v) for k, v in args.items() if k.endswith("path") or k.endswith("sha256") or k == "root"}
    file = tmp_path / "args.json"
    file.write_bytes(encoded(request))
    code = '''import json,sys
from pathlib import Path
from functools import partial
from app_module.recommendation.personal_current_observed_h20_capture import read_pinned_json,read_personal_current_observed_h20_capture
from app_module.recommendation.personal_h20_natural_outcome_batch import run_personal_h20_natural_outcome_batch
args=json.loads(Path(sys.argv[1]).read_bytes())
args.update(source_verifier=lambda v:v,contract_verifier=lambda v:v,input_capture_verifier=read_pinned_json,outcome_verifier=read_pinned_json,prediction_reader=partial(read_personal_current_observed_h20_capture,source_verifier=lambda v:v,contract_verifier=lambda v:v))
print(json.dumps(run_personal_h20_natural_outcome_batch(**args),sort_keys=True))'''
    before = snapshot(args)
    completed = subprocess.run([sys.executable, "-c", code, str(file)], capture_output=True, text=True, check=True)
    assert json.loads(completed.stdout) == first and before == snapshot(args)


@pytest.mark.parametrize("field", ["cycle_terminal_sha256", "snapshot_database_sha256"])
def test_entry_source_pin_mismatch_is_not_credit(tmp_path, field):
    args, _, entry, outcome = cohort(tmp_path)
    entry["source_contract_binding"]["current_observed_feature_snapshot"][field] = "sha256:" + "c" * 64
    attach(args, entry, outcome)
    with pytest.raises(H20CaptureError, match="cycle_source"):
        run_personal_h20_natural_outcome_batch(**args)
    assert not (Path(args["root"]) / "h20_outcome_joins").exists()


def test_original_official_verifier_rejection_propagates(tmp_path):
    args, _, entry, outcome = cohort(tmp_path)
    attach(args, entry, outcome)
    def reject(path, pin):
        raise H20CaptureError("original_twenty_official_sessions_unverified")
    args["outcome_verifier"] = reject
    with pytest.raises(H20CaptureError, match="official_sessions_unverified"):
        run_personal_h20_natural_outcome_batch(**args)
    assert not (Path(args["root"]) / "h20_outcome_joins").exists()


def test_cancel_after_first_join_reports_exact_partial_scope(tmp_path):
    args, _, entry, outcome = cohort(tmp_path)
    attach(args, entry, outcome)
    def cancel():
        directory = Path(args["root"]) / "h20_outcome_joins"
        return directory.exists() and any(directory.iterdir())
    result = run_personal_h20_natural_outcome_batch(**args, cancelled=cancel)
    assert result["status"] == "cancelled" and len(result["rows"]) == 1
    assert result["processed_symbols"] == ["2330"] and result["remaining_symbols"] == ["2454"]
    again = run_personal_h20_natural_outcome_batch(**args)
    assert again["matured_count"] == 2 and again["rows"][0] == result["rows"][0]


def test_scope_limit_and_duplicate_symbols_fail_closed(tmp_path):
    args, body, _, _ = cohort(tmp_path)
    for symbols in (["2330", "2330"], [str(i) for i in range(51)]):
        body["symbols"] = symbols
        raw = encoded(body)
        file = Path(args["manifest_path"]).with_name(digest(raw)[7:] + ".json")
        file.write_bytes(raw)
        with pytest.raises(ValueError):
            run_personal_h20_natural_outcome_batch(**(args | {"manifest_path": file, "manifest_sha256": digest(raw)}))


def test_missing_public_port_rejected_before_source_io(tmp_path):
    args, _, _, _ = cohort(tmp_path)
    args["prediction_reader"] = None
    with pytest.raises(H20CaptureError, match="public_ports_required"):
        run_personal_h20_natural_outcome_batch(**args)
