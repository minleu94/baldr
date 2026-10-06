"""研究預測保存／重讀／取消測試；fixture 不授予自然資格。"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest
import app_module.recommendation.personal_current_observed_h20_capture as capture_module

from app_module.recommendation.personal_current_observed_h20_capture import (
    H20CaptureError, capture_personal_current_observed_h20_prediction, digest, encoded,
    read_personal_current_observed_h20_capture, read_pinned_json,
)


def make_bundle(tmp_path):
    root = tmp_path / "private"
    root.mkdir()
    observed = datetime.now(timezone.utc) - timedelta(seconds=2)
    decision = observed.astimezone(ZoneInfo("Asia/Taipei")).date()
    pin = "sha256:" + "a" * 64
    source = {"cycle_id": "cycle-1", "cycle_terminal_sha256": pin,
        "decision_date": decision.isoformat(), "data_root": str(tmp_path / "data"),
        "pins": {"snapshot_database_path": str(tmp_path / "source" / "snapshot.db"),
                 "snapshot_database_sha256": pin, "observed_at": observed.isoformat()},
        "source_fingerprint": pin, "feature_rows_by_symbol": {"2330": {
            "row_sha256": pin, "feature_as_of_date": (decision - timedelta(days=1)).isoformat(),
            "local_current_observed_at": observed.isoformat(), "values": [["x", 1]]}}}
    contract = {"candidate_id": "candidate-1", "contract_hash": pin, "artifact_hash": pin,
        "lineage_hash": pin, "fit_receipt_sha256": pin, "model_id": "model-1", "model_version": "v1",
        "fit_receipt_path": str(tmp_path / "fit.json"), "artifact_root": str(tmp_path / "artifact"),
        "feature_schema": [["x", "integer", "v1"]]}
    request = {"symbol": "2330", "decision_date": decision.isoformat(),
        "feature_as_of_date": source["feature_rows_by_symbol"]["2330"]["feature_as_of_date"],
        "feature_available_date": decision.isoformat(), "feature_schema": contract["feature_schema"],
        "feature_values": [1], "feature_snapshot_hash": pin, "feature_source_hash": pin,
        "model_contract_hash": pin}
    prediction = {"request": request, "status": "h20_gross_available", "predicted_gross_return_bp": 120,
        "model_id": "model-1", "model_version": "v1", "model_contract_hash": pin,
        "artifact_hash": pin, "lineage_hash": pin, "blockers": [],
        "target": "absolute_forward_stock_return_bp", "horizon_trading_days": 20,
        "price_basis": "close_to_close_event_date", "cost_basis": "no_cost_gross",
        "contract_version": "personal-h20-gross.v1",
        "formal_eligible": False, "natural_evidence_eligible": False, "production_action_allowed": False,
        "prediction_id": "personal-h20:" + digest(json.dumps(request, sort_keys=True, separators=(",", ":")).encode())[7:]}
    return root, source, contract, prediction


def save(bundle, **overrides):
    root, source, contract, prediction = bundle
    arguments = dict(root=root, source_binding=source, contract_binding=contract, symbol="2330",
        source_verifier=lambda value: deepcopy(value), contract_verifier=lambda value: deepcopy(value),
        predictor=lambda: deepcopy(prediction))
    return capture_personal_current_observed_h20_prediction(**(arguments | overrides))


def test_create_only_retry_never_calls_predictor(tmp_path):
    bundle = make_bundle(tmp_path)
    first = save(bundle)
    path = Path(first["path"])
    raw, mtime = path.read_bytes(), path.stat().st_mtime_ns
    def forbidden():
        raise AssertionError("重試不得推論")
    bundle[1]["pins"]["observed_at"] = datetime.now(timezone.utc).isoformat()
    again = save(bundle, predictor=forbidden)
    assert again["idempotent"] and first["sample_id"] == again["sample_id"]
    assert (raw, mtime) == (path.read_bytes(), path.stat().st_mtime_ns)
    assert "result_id" not in json.loads(raw)


def test_midnight_retry_reuses_first_date_without_recomputation(tmp_path, monkeypatch):
    bundle = make_bundle(tmp_path)
    original = save(bundle)
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    class NextDayClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return tomorrow if tz is not None else tomorrow.replace(tzinfo=None)
    monkeypatch.setattr(capture_module, "datetime", NextDayClock)
    bundle[1]["decision_date"] = tomorrow.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()
    bundle[1]["pins"]["observed_at"] = tomorrow.isoformat()
    def forbidden():
        raise AssertionError("跨日重試不得造新自然樣本")
    again = save(bundle, predictor=forbidden)
    assert again["sample_id"] == original["sample_id"] and again["idempotent"]
    assert len(list((bundle[0] / "h20_predictions").glob("*.json"))) == 1


def test_legacy_filename_reference_preserves_prediction_bytes(tmp_path):
    bundle = make_bundle(tmp_path)
    saved = save(bundle)
    path = Path(saved["path"])
    legacy = path.with_name(saved["sample_id"].split(":", 1)[1] + ".json")
    path.rename(legacy)
    before = legacy.read_bytes(), legacy.stat().st_mtime_ns
    again = save(bundle, predictor=lambda: (_ for _ in ()).throw(AssertionError("no inference")))
    assert Path(again["path"]) == legacy and again["idempotent"]
    assert before == (legacy.read_bytes(), legacy.stat().st_mtime_ns)
    assert len(list((bundle[0] / "h20_prediction_refs").glob("*.json"))) == 1


@pytest.mark.parametrize("field,value", [("predicted_gross_return_bp", None),
    ("predicted_gross_return_bp", True), ("natural_evidence_eligible", True),
    ("artifact_hash", "sha256:" + "b" * 64), ("prediction_id", "fabricated")])
def test_original_prediction_pin_or_qualification_rejected(tmp_path, field, value):
    bundle = make_bundle(tmp_path)
    bundle[3][field] = value
    with pytest.raises(H20CaptureError):
        save(bundle)
    assert not (bundle[0] / "h20_predictions").exists()


def test_verifier_is_required_and_no_io(tmp_path):
    bundle = make_bundle(tmp_path)
    with pytest.raises(H20CaptureError, match="ports_required"):
        save(bundle, source_verifier=None)
    assert list(bundle[0].iterdir()) == []


def test_cancel_before_prediction(tmp_path):
    bundle = make_bundle(tmp_path)
    with pytest.raises(InterruptedError):
        save(bundle, cancelled=lambda: True)
    assert list(bundle[0].iterdir()) == []


def test_saved_raw_tamper_is_rejected(tmp_path):
    bundle = make_bundle(tmp_path)
    receipt = save(bundle)
    path = Path(receipt["path"])
    payload = json.loads(path.read_bytes())
    payload["prediction"]["predicted_gross_return_bp"] = 999
    path.write_bytes(encoded(payload))
    with pytest.raises(H20CaptureError):
        read_personal_current_observed_h20_capture(path, root=bundle[0], expected_sha256=receipt["raw_sha256"],
            source_verifier=lambda v: v, contract_verifier=lambda v: v)


def test_feature_after_prediction_rejected(tmp_path):
    bundle = make_bundle(tmp_path)
    bundle[1]["feature_rows_by_symbol"]["2330"]["local_current_observed_at"] = (
        datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    with pytest.raises(H20CaptureError):
        save(bundle)


def test_source_overlap_rejected(tmp_path):
    bundle = make_bundle(tmp_path)
    bundle[1]["data_root"] = str(bundle[0])
    with pytest.raises(H20CaptureError, match="disjoint"):
        save(bundle)


def test_hardlink_raw_request_rejected(tmp_path):
    path = tmp_path / "raw.json"
    path.write_bytes(b"{}")
    os.link(path, tmp_path / "alias.json")
    with pytest.raises(H20CaptureError, match="single_link"):
        read_pinned_json(path)


def test_public_reader_fresh_process(tmp_path):
    bundle = make_bundle(tmp_path)
    receipt = save(bundle)
    code = """import sys,json
from app_module.recommendation.personal_current_observed_h20_capture import read_personal_current_observed_h20_capture
p=read_personal_current_observed_h20_capture(sys.argv[1],root=sys.argv[2],expected_sha256=sys.argv[3],source_verifier=lambda v:v,contract_verifier=lambda v:v)
print(json.dumps({'sample_id':p['sample_id'],'value':p['prediction']['predicted_gross_return_bp']}))
"""
    process = subprocess.run([sys.executable, "-c", code, receipt["path"], str(bundle[0]), receipt["raw_sha256"]],
        capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(process.stdout) == {"sample_id": receipt["sample_id"], "value": 120}
