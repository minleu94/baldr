"""將已保存 H20 預測接到原受驗自然結果，不建立 canonical 推薦。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from app_module.recommendation.personal_current_observed_h20_capture import (
    H20CaptureError, Verifier, digest, encoded, publish, read_pinned_json,
    read_personal_current_observed_h20_capture,
)

ReceiptVerifier = Callable[[Path, str], Mapping[str, Any]]


def read_personal_current_observed_h20_outcome(path: str | Path, *, root: str | Path,
        source_verifier: Verifier, contract_verifier: Verifier,
        input_capture_verifier: ReceiptVerifier, outcome_verifier: ReceiptVerifier,
        expected_sha256: str | None = None) -> dict[str, Any]:
    """產品 consumer 重核原預測、entry 與官方自然 outcome，不只讀旁路 JSON。"""
    file = Path(path)
    if file.parent != Path(root) / "h20_outcome_joins":
        raise H20CaptureError("outcome_join_outside_personal_store")
    payload = read_pinned_json(file, expected_sha256)
    rebuilt = project_personal_current_observed_h20_outcome(
        prediction_path=payload["prediction_path"], prediction_sha256=payload["prediction_sha256"], root=root,
        source_verifier=source_verifier, contract_verifier=contract_verifier,
        input_capture_path=payload["input_capture_path"], input_capture_sha256=payload["input_capture_sha256"],
        input_capture_verifier=input_capture_verifier, outcome_path=payload["outcome_path"],
        outcome_sha256=payload["outcome_sha256"], outcome_verifier=outcome_verifier, persist=False)
    expected_name = digest(encoded({"sample_id": payload["sample_id"], "outcome_sha256": payload["outcome_sha256"]}))[7:] + ".json"
    if rebuilt != payload or file.name != expected_name:
        raise H20CaptureError("saved_outcome_join_mismatch")
    return payload


def project_personal_current_observed_h20_outcome(*, prediction_path: str | Path,
        prediction_sha256: str, root: str | Path, source_verifier: Verifier,
        contract_verifier: Verifier, input_capture_path: str | Path | None = None,
        input_capture_sha256: str | None = None, input_capture_verifier: ReceiptVerifier | None = None,
        outcome_path: str | Path | None = None, outcome_sha256: str | None = None,
        outcome_verifier: ReceiptVerifier | None = None, persist: bool = True) -> dict[str, Any]:
    """先核模型原始保存值；entry／20-session 缺件如實 pending。"""
    prediction = read_personal_current_observed_h20_capture(prediction_path, root=root,
        expected_sha256=prediction_sha256, source_verifier=source_verifier,
        contract_verifier=contract_verifier)
    view: dict[str, Any] = {"schema_version": "personal-current-observed-h20-outcome-view.v1",
        "sample_id": prediction["sample_id"], "prediction_id": prediction["prediction"]["prediction_id"],
        "prediction_path": str(prediction_path), "prediction_sha256": prediction_sha256,
        "identity": prediction["identity"], "status": "pending", "reason": "exact_entry_capture_missing",
        "predicted_gross_return_bp": prediction["prediction"]["predicted_gross_return_bp"],
        "realized_gross_return_bp": None, "error_bp": None,
        "historical_pit_eligible": False, "formal_training_allowed": False,
        "production_action_allowed": False, "promotion_credit_created": False, "research_only": True}
    if input_capture_path is None:
        if any(v is not None for v in (input_capture_sha256, outcome_path, outcome_sha256)):
            raise H20CaptureError("exact_input_capture_required_for_outcome")
        return view
    if not input_capture_sha256 or not callable(input_capture_verifier):
        raise H20CaptureError("input_capture_pin_and_verifier_required")
    capture_file = Path(input_capture_path)
    original = read_pinned_json(capture_file, input_capture_sha256)
    capture = dict(input_capture_verifier(capture_file, input_capture_sha256))
    # 原 verifier 可加 _verified_* 診斷；保存欄位仍須逐一等於原 pinned bytes。
    if any(capture.get(key) != value for key, value in original.items()):
        raise H20CaptureError("input_verifier_original_bytes_mismatch")
    source = prediction["source_binding"]
    symbol = prediction["identity"]["symbol"]
    snapshot = capture["source_contract_binding"]["current_observed_feature_snapshot"]
    if (capture["cycle_id"] != source["cycle_id"] or capture["decision_date"] != source["decision_date"]
            or snapshot["cycle_terminal_sha256"] != source["cycle_terminal_sha256"]
            or snapshot["snapshot_database_sha256"].removeprefix("sha256:") != source["pins"]["snapshot_database_sha256"].removeprefix("sha256:")):
        raise H20CaptureError("prediction_entry_cycle_source_mismatch")
    rows = [row for row in capture["rows"] if row["symbol"] == symbol]
    request = prediction["prediction"]["request"]
    if (len(rows) != 1 or rows[0]["decision_date"] != request["decision_date"]
            or rows[0]["feature_as_of_date"] != request["feature_as_of_date"]
            or rows[0]["feature_values"] != request["feature_values"]
            or rows[0]["feature_ids"] != [item[0] for item in request["feature_schema"]]):
        raise H20CaptureError("prediction_entry_feature_identity_mismatch")
    view.update(input_capture_id=capture["capture_id"], input_capture_path=str(capture_file),
                input_capture_sha256=input_capture_sha256, reason="twenty_sessions_not_yet_verified")
    if outcome_path is None:
        if outcome_sha256 is not None:
            raise H20CaptureError("outcome_path_required")
        return view
    if not outcome_sha256 or not callable(outcome_verifier):
        raise H20CaptureError("outcome_pin_and_verifier_required")
    outcome_file = Path(outcome_path)
    original_outcome = read_pinned_json(outcome_file, outcome_sha256)
    outcome = dict(outcome_verifier(outcome_file, outcome_sha256))
    if any(outcome.get(key) != value for key, value in original_outcome.items()):
        raise H20CaptureError("outcome_verifier_original_bytes_mismatch")
    if (outcome["capture_id"] != capture["capture_id"] or outcome["capture_sha256"] != input_capture_sha256
            or Path(outcome["capture_path"]) != capture_file
            or outcome["capture_cycle_id"] != source["cycle_id"]
            or outcome["decision_date"] != request["decision_date"] or outcome["horizon_sessions"] != 20
            or any(outcome.get(k) is not False for k in
                   ("historical_pit_eligible", "formal_training_allowed", "promotion_credit_created"))):
        raise H20CaptureError("natural_outcome_capture_identity_mismatch")
    matches = [row for row in outcome["outcomes"] if row["capture_row_id"] == rows[0]["row_id"]]
    view.update(outcome_path=str(outcome_file), outcome_sha256=outcome_sha256)
    if not matches:
        if not any(row["capture_row_id"] == rows[0]["row_id"] for row in outcome["pending_rows"]):
            raise H20CaptureError("outcome_missing_selected_row")
        return view
    if len(matches) != 1 or type(matches[0]["stock_return_bp"]) is not int:
        raise H20CaptureError("natural_gross_integer_row_required")
    row = matches[0]
    if row["symbol"] != symbol or row["capture_decision_date"] != request["decision_date"]:
        raise H20CaptureError("natural_outcome_symbol_date_mismatch")
    view.update(status="matured", reason="verified_current_observed_twenty_session_outcome",
                realized_gross_return_bp=row["stock_return_bp"],
                error_bp=prediction["prediction"]["predicted_gross_return_bp"] - row["stock_return_bp"],
                endpoint_date=outcome["endpoint_date"])
    view["payload_sha256"] = digest(encoded(view))
    if not persist:
        return view
    path = publish(Path(root), "h20_outcome_joins", digest(encoded(
        {"sample_id": view["sample_id"], "outcome_sha256": outcome_sha256}))[7:] + ".json", view)
    view["saved_join_path"] = str(path)
    return view
