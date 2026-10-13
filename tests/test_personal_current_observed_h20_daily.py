"""每日入口沿原 identity 保存部分結果與跨程序重試。"""
from copy import deepcopy
import ast
from pathlib import Path

import pytest
from test_personal_current_observed_h20_capture import make_bundle
from app_module.recommendation.personal_current_observed_h20_capture import H20CaptureError
from scripts.scheduled.run_personal_current_observed_h20_daily import run_personal_current_observed_h20_daily


def setup(tmp_path):
    root, source, contract, prediction = make_bundle(tmp_path)
    request = {"schema_version": "personal-current-observed-h20-daily-request.v1",
        "data_root": source["data_root"], "source_pins": {**source["pins"], "cycle_id": source["cycle_id"],
            "cycle_terminal_sha256": source["cycle_terminal_sha256"]},
        "symbols": ["2330"], "history_start_date": "2014-01-01",
        "expected_feature_as_of_date": source["feature_rows_by_symbol"]["2330"]["feature_as_of_date"]}
    request["source_pins"].pop("observed_at")
    def source_port(binding):
        return {**deepcopy(source), **deepcopy(binding)}
    def contract_port(binding):
        return {**deepcopy(contract), **deepcopy(binding)}
    args = dict(request=request, receipt_root=root, gross_fit_receipt=contract["fit_receipt_path"],
        expected_fit_receipt_sha256=contract["fit_receipt_sha256"], source_verifier=source_port,
        contract_verifier=contract_port, predictor_factory=lambda c, s: lambda code: deepcopy(prediction))
    return args


def test_daily_true_clock_and_pending_are_usable(tmp_path):
    args = setup(tmp_path)
    receipt = run_personal_current_observed_h20_daily(**args)
    assert receipt["status"] == "completed"
    assert len(receipt["captures"]) == 1
    assert receipt["outcomes"][0]["status"] == "pending"
    assert receipt["outcomes"][0]["predicted_gross_return_bp"] == 120
    args["predictor_factory"] = lambda c, s: lambda code: (_ for _ in ()).throw(AssertionError("no retry predict"))
    again = run_personal_current_observed_h20_daily(**args)
    assert again["status"] == "completed" and again["captures"][0]["idempotent"]


@pytest.mark.parametrize("change_at_terminal", [False, True])
def test_public_daily_groups_only_same_operation_and_rejects_terminal_source_change(tmp_path, monkeypatch, change_at_terminal):
    from scripts.scheduled import run_personal_current_observed_h20_daily as daily
    args = setup(tmp_path)
    source = args.pop("source_verifier")
    contract = args.pop("contract_verifier")
    calls = []
    def public_source(binding, **kwargs):
        calls.append(binding)
        result = source(binding)
        if change_at_terminal and len(calls) >= 3:
            result["source_fingerprint"] = "sha256:" + "b" * 64
        return result
    monkeypatch.setattr(daily, "_source_port", public_source)
    monkeypatch.setattr(daily, "_contract_port", contract)
    receipt = daily.run_personal_current_observed_h20_daily(**args)
    assert len(calls) <= 4
    if change_at_terminal:
        assert receipt["status"] == "failed"
        assert "changed_during_read" in receipt["reason"]
    else:
        assert receipt["status"] == "completed"
        assert receipt["formal_training_allowed"] is False


@pytest.mark.parametrize("field", ["observed_at", "decision_date", "result_id", "predictions"])
def test_backdate_or_fake_result_rejected(tmp_path, field):
    args = setup(tmp_path)
    args["request"][field] = "fake"
    with pytest.raises(H20CaptureError, match="backdate"):
        run_personal_current_observed_h20_daily(**args)


def test_cancel_keeps_saved_rows_and_retry(tmp_path):
    args = setup(tmp_path)
    args["request"]["symbols"] = ["2330", "2454"]
    def cancelled():
        return len(list(Path(args["receipt_root"]).glob("h20_predictions/*.json"))) == 1
    args["cancelled"] = cancelled
    receipt = run_personal_current_observed_h20_daily(**args)
    assert receipt["status"] == "cancelled" and len(receipt["captures"]) == 1
    assert len(list(Path(args["receipt_root"]).glob("h20_predictions/*.json"))) == 1
    args["request"]["symbols"] = ["2330"]
    args.pop("cancelled")
    again = run_personal_current_observed_h20_daily(**args)
    assert again["status"] == "completed" and again["captures"][0]["idempotent"]


def test_failure_after_first_saved_row_keeps_original_retry(tmp_path):
    args = setup(tmp_path)
    args["request"]["symbols"] = ["2330", "2454"]
    receipt = run_personal_current_observed_h20_daily(**args)
    assert receipt["status"] == "failed" and len(receipt["captures"]) == 1
    args["request"]["symbols"] = ["2330"]
    args["predictor_factory"] = lambda c, s: lambda code: (_ for _ in ()).throw(AssertionError("no recompute"))
    retry = run_personal_current_observed_h20_daily(**args)
    assert retry["status"] == "completed" and retry["captures"][0]["idempotent"]


def test_app_adapters_have_no_ml_imports():
    root = Path(__file__).resolve().parents[1]
    for name in ("capture", "outcome"):
        tree = ast.parse((root / "app_module/recommendation" / f"personal_current_observed_h20_{name}.py").read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.ImportFrom) and (node.module or "").startswith("ml_module")
                       for node in ast.walk(tree))
