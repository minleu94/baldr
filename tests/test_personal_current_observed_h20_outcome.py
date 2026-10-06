"""受驗 entry／自然結果 exact join；fixture 不宣稱真成熟樣本。"""
from copy import deepcopy
from pathlib import Path

import pytest
from test_personal_current_observed_h20_capture import make_bundle, save
from app_module.recommendation.personal_current_observed_h20_capture import H20CaptureError, digest, encoded
from app_module.recommendation.personal_current_observed_h20_outcome import (
    project_personal_current_observed_h20_outcome, read_personal_current_observed_h20_outcome,
)


def prepared(tmp_path):
    bundle = make_bundle(tmp_path)
    saved = save(bundle)
    root, source, _, prediction = bundle
    input_path = tmp_path / "input.json"
    capture = {"capture_id": "original-input-1", "cycle_id": source["cycle_id"],
        "decision_date": source["decision_date"], "rows": [{"row_id": "row-2330", "symbol": "2330",
            "decision_date": source["decision_date"], "feature_as_of_date": prediction["request"]["feature_as_of_date"],
            "feature_values": [1], "feature_ids": ["x"]}], "source_contract_binding": {
                "current_observed_feature_snapshot": {"cycle_terminal_sha256": source["cycle_terminal_sha256"],
                    "snapshot_database_sha256": source["pins"]["snapshot_database_sha256"]}}}
    input_path.write_bytes(encoded(capture))
    input_pin = digest(input_path.read_bytes())
    outcome_path = tmp_path / "outcome.json"
    outcome = {"capture_id": capture["capture_id"], "capture_sha256": input_pin, "capture_path": str(input_path),
        "capture_cycle_id": source["cycle_id"], "decision_date": source["decision_date"], "horizon_sessions": 20,
        "historical_pit_eligible": False, "formal_training_allowed": False, "promotion_credit_created": False,
        "endpoint_date": "2026-11-04", "outcomes": [{"capture_row_id": "row-2330", "symbol": "2330",
            "capture_decision_date": source["decision_date"], "stock_return_bp": 100}], "pending_rows": []}
    outcome_path.write_bytes(encoded(outcome))
    arguments = dict(prediction_path=saved["path"], prediction_sha256=saved["raw_sha256"], root=root,
        source_verifier=lambda v: v, contract_verifier=lambda v: v,
        input_capture_path=input_path, input_capture_sha256=input_pin,
        input_capture_verifier=lambda p, h: deepcopy(capture), outcome_path=outcome_path,
        outcome_sha256=digest(outcome_path.read_bytes()), outcome_verifier=lambda p, h: deepcopy(outcome))
    return arguments, capture, outcome


def test_matured_join_keeps_original_prediction_and_idempotent(tmp_path):
    args, _, _ = prepared(tmp_path)
    view = project_personal_current_observed_h20_outcome(**args)
    path = Path(view["saved_join_path"])
    raw, mtime = path.read_bytes(), path.stat().st_mtime_ns
    assert view["status"] == "matured" and view["error_bp"] == 20
    assert view["predicted_gross_return_bp"] == 120
    assert project_personal_current_observed_h20_outcome(**args) == view
    assert (path.read_bytes(), path.stat().st_mtime_ns) == (raw, mtime)
    readback = read_personal_current_observed_h20_outcome(path, root=args["root"],
        source_verifier=args["source_verifier"], contract_verifier=args["contract_verifier"],
        input_capture_verifier=args["input_capture_verifier"], outcome_verifier=args["outcome_verifier"],
        expected_sha256=digest(raw))
    assert readback["sample_id"] == view["sample_id"]


def test_preclose_and_maturity_pending(tmp_path):
    args, _, _ = prepared(tmp_path)
    for key in ("input_capture_path", "input_capture_sha256", "outcome_path", "outcome_sha256"):
        args.pop(key)
    view = project_personal_current_observed_h20_outcome(**args)
    assert view["status"] == "pending" and view["realized_gross_return_bp"] is None
    assert not (Path(args["root"]) / "h20_outcome_joins").exists()


def test_selected_row_pending_does_not_receive_another_rows_return(tmp_path):
    args, _, outcome = prepared(tmp_path)
    outcome["outcomes"] = [{"capture_row_id": "other-row", "symbol": "2454",
        "capture_decision_date": outcome["decision_date"], "stock_return_bp": 999}]
    outcome["pending_rows"] = [{"capture_row_id": "row-2330", "symbol": "2330"}]
    Path(args["outcome_path"]).write_bytes(encoded(outcome))
    args["outcome_sha256"] = digest(encoded(outcome))
    view = project_personal_current_observed_h20_outcome(**args)
    assert view["status"] == "pending" and view["realized_gross_return_bp"] is None


@pytest.mark.parametrize("target,field,value", [("capture", "cycle_id", "other"),
    ("capture", "decision_date", "2000-01-01"), ("outcome", "capture_id", "other"),
    ("outcome", "capture_sha256", "sha256:" + "b" * 64),
    ("outcome", "horizon_sessions", 19), ("outcome", "formal_training_allowed", True)])
def test_wrong_join_rejected(tmp_path, target, field, value):
    args, capture, outcome = prepared(tmp_path)
    chosen = capture if target == "capture" else outcome
    chosen[field] = value
    path_key = "input_capture_path" if target == "capture" else "outcome_path"
    pin_key = "input_capture_sha256" if target == "capture" else "outcome_sha256"
    Path(args[path_key]).write_bytes(encoded(chosen))
    args[pin_key] = digest(encoded(chosen))
    with pytest.raises(H20CaptureError):
        project_personal_current_observed_h20_outcome(**args)


def test_wrong_symbol_and_missing_port(tmp_path):
    args, _, outcome = prepared(tmp_path)
    outcome["outcomes"][0]["symbol"] = "2454"
    Path(args["outcome_path"]).write_bytes(encoded(outcome))
    args["outcome_sha256"] = digest(encoded(outcome))
    with pytest.raises(H20CaptureError, match="symbol_date"):
        project_personal_current_observed_h20_outcome(**args)
    args["outcome_verifier"] = None
    with pytest.raises(H20CaptureError, match="verifier_required"):
        project_personal_current_observed_h20_outcome(**args)
