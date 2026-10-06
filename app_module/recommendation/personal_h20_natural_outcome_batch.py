"""原保存完整 H20 cohort 的自然結果 caller；不推論、不建立推薦身份。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from app_module.recommendation.personal_current_observed_h20_capture import (
    H20CaptureError, Verifier, plain, read_pinned_json, require_digest,
)
from app_module.recommendation.personal_current_observed_h20_outcome import (
    ReceiptVerifier, project_personal_current_observed_h20_outcome,
)
from app_module.recommendation.personal_h20_product_evidence import read_personal_h20_daily_manifest


def run_personal_h20_natural_outcome_batch(*, manifest_path: str | Path,
        manifest_sha256: str, root: str | Path,
        input_capture_path: str | Path | None = None, input_capture_sha256: str | None = None,
        outcome_path: str | Path | None = None, outcome_sha256: str | None = None,
        prediction_reader: Callable[..., Mapping[str, Any]], source_verifier: Verifier,
        contract_verifier: Verifier, input_capture_verifier: ReceiptVerifier,
        outcome_verifier: ReceiptVerifier, cancelled: Callable[[], bool] | None = None) -> Mapping[str, Any]:
    """重核全部原 pins，再逐列交原 projector 保存成熟 join；取消保留精確進度。"""
    store = Path(root)
    plain(store)
    package = Path(__file__).resolve().parents[2]
    if store == package or package in store.parents or store in package.parents:
        raise H20CaptureError("personal_root_must_be_outside_package")
    require_digest(manifest_sha256)
    if not all(callable(port) for port in
            (prediction_reader, source_verifier, contract_verifier, input_capture_verifier, outcome_verifier)):
        raise H20CaptureError("natural_batch_public_ports_required")
    for path, pin in ((input_capture_path, input_capture_sha256), (outcome_path, outcome_sha256)):
        if (path is None) != (pin is None):
            raise H20CaptureError("natural_batch_exact_path_pin_pair_required")
        if pin is not None:
            require_digest(pin)
    if outcome_path is not None and input_capture_path is None:
        raise H20CaptureError("exact_input_capture_required_for_outcome")

    def check_cancelled() -> None:
        if cancelled is not None and cancelled():
            raise InterruptedError("natural_batch_cancelled")

    def reader(path: str | Path, **kwargs: Any) -> Mapping[str, Any]:
        check_cancelled()
        return prediction_reader(path, **kwargs)

    # 完整 public reader 驗證，不以 selected_stock 跳過 cohort 成員。
    check_cancelled()
    read_pinned_json(Path(manifest_path), manifest_sha256)
    manifest = read_personal_h20_daily_manifest(manifest_path, root=store,
        expected_sha256=manifest_sha256, prediction_reader=reader)
    result: dict[str, Any] = {"schema_version": "personal-h20-natural-outcome-batch.v1",
        "status": "completed", "manifest_path": str(manifest_path), "manifest_sha256": manifest_sha256,
        "candidate_id": manifest["candidate_id"], "contract_hash": manifest["contract_hash"],
        "cycle_id": manifest["cycle_id"], "decision_date": manifest["decision_date"],
        "symbols": list(manifest["symbols"]), "rows": [], "processed_symbols": [],
        "historical_pit_eligible": False, "formal_training_allowed": False,
        "production_action_allowed": False, "promotion_credit_created": False, "research_only": True}
    def project(pin: Mapping[str, Any], *, persist: bool) -> dict[str, Any]:
        return project_personal_current_observed_h20_outcome(
            prediction_path=pin["path"], prediction_sha256=pin["raw_sha256"], root=store,
            source_verifier=source_verifier, contract_verifier=contract_verifier,
            input_capture_path=input_capture_path, input_capture_sha256=input_capture_sha256,
            input_capture_verifier=input_capture_verifier, outcome_path=outcome_path,
            outcome_sha256=outcome_sha256, outcome_verifier=outcome_verifier, persist=persist)
    previews: list[dict[str, Any]] = []
    try:
        # 先驗所有列：錯配、缺成員或 verifier 拒絕時完全不發布 join。
        for pin in manifest["captures"]:
            check_cancelled()
            previews.append(project(pin, persist=False))
        check_cancelled()
        if read_personal_h20_daily_manifest(manifest_path, root=store,
                expected_sha256=manifest_sha256, prediction_reader=reader) != manifest:
            raise H20CaptureError("natural_batch_manifest_changed")
        for pin, preview in zip(manifest["captures"], previews):
            check_cancelled()
            # 每次原 projector 重驗 source/contract/entry/outcome；保存沿原 create-only publisher。
            view = project(pin, persist=True)
            if {k: v for k, v in view.items() if k != "saved_join_path"} != preview:
                raise H20CaptureError("natural_batch_projection_changed")
            result["rows"].append(view)
            result["processed_symbols"].append(pin["symbol"])
    except InterruptedError as exc:
        result.update(status="cancelled", reason=str(exc))
    result["remaining_symbols"] = [s for s in result["symbols"] if s not in result["processed_symbols"]]
    result["matured_count"] = sum(row["status"] == "matured" for row in result["rows"])
    result["pending_count"] = sum(row["status"] == "pending" for row in result["rows"])
    return result
