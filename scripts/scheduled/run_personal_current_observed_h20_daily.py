"""以原 frozen 模型、已完成 raw cycle 保存每日 H20 真實研究預測。"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.recommendation.personal_current_observed_h20_capture import (
    H20CaptureError, Verifier, capture_personal_current_observed_h20_prediction,
    digest, encoded, plain, read_pinned_json, read_personal_current_observed_h20_capture,
)
from app_module.recommendation.personal_current_observed_h20_outcome import (
    project_personal_current_observed_h20_outcome,
)


def _contract_port(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    from scripts.qa_prepare_personal_h20_gross_contract import prepare_contract
    read_pinned_json(Path(binding["fit_receipt_path"]), binding["fit_receipt_sha256"])
    prepared = prepare_contract(Path(binding["fit_receipt_path"]),
        expected_fit_receipt_sha256=binding["fit_receipt_sha256"])
    return json.loads(encoded({**prepared["contract"], "contract_hash": prepared["contract_hash"],
            "fit_receipt_path": binding["fit_receipt_path"], "fit_receipt_sha256": binding["fit_receipt_sha256"]}))


def _source_port(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    from ml_module.recommendation_calibration_evidence import load_current_observed_context_from_pinned_snapshot
    from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
    from ml_module.historical_feature_builder import HistoricalFeatureBuilder
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from data_module.config import TWStockConfig
    import os
    if os.path.normcase(os.path.abspath(binding["data_root"])) != os.path.normcase(os.path.abspath(TWStockConfig().data_root)):
        raise H20CaptureError("configured_data_root_mismatch")
    pins = dict(binding["pins"])
    observation = datetime.fromisoformat(pins["observed_at"])
    if observation.tzinfo is None or observation.utcoffset() is None or observation > datetime.now(timezone.utc):
        raise H20CaptureError("source_aware_real_clock_required")
    terminal = read_pinned_json(Path(pins["cycle_terminal_path"]), pins["cycle_terminal_sha256"])
    if (terminal.get("status") != "completed" or terminal.get("cycle_id") != pins["cycle_id"]
            or terminal.get("source_date") != pins.get("cycle_source_date")
            or date.fromisoformat(pins["cycle_source_date"]) > date.fromisoformat(binding["decision_date"])
            or sorted(terminal.get("current_symbols", [])) != binding["symbols"]):
        raise H20CaptureError("exact_completed_nonfuture_cohort_required")
    # 原 public loader 核 cycle completion、snapshot／envelope 與 terminal 相同 run。
    context = load_current_observed_context_from_pinned_snapshot(pins)
    if not terminal or observation.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat() != binding["decision_date"]:
        raise H20CaptureError("same_day_real_observation_required")
    raw = MLHistoricalSnapshotProvider(Path(context.snapshot_database_path)).load_current_observed(
        decision_date=binding["decision_date"], history_start_date=binding["history_start_date"],
        symbols=tuple(binding["symbols"]), source_context=context,
        local_current_observed_at=observation, expected_feature_as_of_date=binding["feature_as_of_date"],
        cycle_id=pins["cycle_id"], cycle_terminal_path=pins["cycle_terminal_path"],
        cycle_terminal_sha256=pins["cycle_terminal_sha256"],
        source_context_envelope_path=pins["source_context_envelope_path"],
        source_context_envelope_sha256="sha256:" + pins["source_context_envelope_sha256"].removeprefix("sha256:"))
    rows = HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY).compute_current_observed(
        raw, industry_index_name_by_symbol={})
    if sorted(row.symbol for row in rows) != binding["symbols"]:
        raise H20CaptureError("feature_cohort_incomplete")
    result = {**binding, "source_fingerprint": raw.source_fingerprint,
        "feature_rows_by_symbol": {row.symbol: {**asdict(row), "row_sha256": row.row_sha256,
            "local_current_observed_at": row.local_current_observed_at.isoformat()} for row in rows}}
    return json.loads(encoded(result))


def _predictor(contract_binding: Mapping[str, Any], source: Mapping[str, Any]) -> Callable[[str], Mapping[str, Any]]:
    from ml_module.personal_h20_gross_model_contract import H20GrossModelContract, H20GrossInferenceRequest
    from ml_module.personal_h20_gross_inference import PersonalH20GrossInference, PinnedH20GrossArtifactLoader
    from ml_module.recommendation_training_lineage import read_recommendation_training_lineage
    body = {k: v for k, v in contract_binding.items() if k not in {"contract_hash", "fit_receipt_path", "fit_receipt_sha256"}}
    body["feature_schema"] = tuple(tuple(row) for row in body["feature_schema"])
    contract = H20GrossModelContract(**body)
    service = PersonalH20GrossInference(contract, lineage_reader=read_recommendation_training_lineage,
        artifact_loader=PinnedH20GrossArtifactLoader(contract, data_root=Path(source["data_root"])))
    def predict(symbol: str) -> Mapping[str, Any]:
        row = source["feature_rows_by_symbol"][symbol]
        if row["feature_registry_hash"] != contract.feature_registry_hash:
            raise H20CaptureError("feature_registry_model_mismatch")
        request = H20GrossInferenceRequest(symbol, source["decision_date"], row["feature_as_of_date"],
            source["decision_date"], contract.feature_schema, tuple(value for _, value in row["values"]),
            row["row_sha256"], source["source_fingerprint"], contract.contract_hash)
        return service.predict(request).to_dict()
    return predict


def _input_port(path: Path, pin: str) -> Mapping[str, Any]:
    from ml_module.recommendation_calibration_evidence import verify_current_observed_input_capture
    from app_module.recommendation.scheduled_snapshot_source_custody import verify_scheduled_snapshot_source_binding_artifacts
    return verify_current_observed_input_capture(path, expected_sha256=pin,
        source_binding_verifier=verify_scheduled_snapshot_source_binding_artifacts)


def _outcome_port(path: Path, pin: str) -> Mapping[str, Any]:
    from ml_module.recommendation_natural_outcome_service import verify_current_observed_outcome_receipt
    from app_module.recommendation.scheduled_snapshot_source_custody import verify_scheduled_snapshot_source_binding_artifacts
    return verify_current_observed_outcome_receipt(path, expected_sha256=pin,
        source_binding_verifier=verify_scheduled_snapshot_source_binding_artifacts)


def personal_current_observed_h20_read_ports() -> dict[str, Callable[..., Any]]:
    """中央 composition 注入產品 reader 的原驗證 ports；App 不匯入 ML。"""
    return {"source_verifier": _source_port, "contract_verifier": _contract_port,
            "input_capture_verifier": _input_port, "outcome_verifier": _outcome_port}


def run_personal_current_observed_h20_daily(*, request: Mapping[str, Any], receipt_root: str | Path,
        gross_fit_receipt: str | Path, expected_fit_receipt_sha256: str,
        cancelled: Callable[[], bool] | None = None, source_verifier: Verifier | None = None,
        contract_verifier: Verifier | None = None,
        predictor_factory: Callable[[Mapping[str, Any], Mapping[str, Any]], Callable[[str], Mapping[str, Any]]] | None = None) -> dict[str, Any]:
    """保存每列後即讀回；失敗／取消回傳部分收據，下次沿同 identity 重試。"""
    root = Path(receipt_root)
    plain(root)
    if root == ROOT or ROOT in root.parents or root in ROOT.parents:
        raise H20CaptureError("personal_root_must_be_outside_package")
    if request.get("schema_version") != "personal-current-observed-h20-daily-request.v1":
        raise H20CaptureError("daily_request_schema_required")
    if any(k in request for k in ("observed_at", "decision_date", "result_id", "predictions")):
        raise H20CaptureError("caller_cannot_backdate_or_supply_predictions")
    symbols = request["symbols"]
    if (not isinstance(symbols, list) or not 1 <= len(symbols) <= 50
            or any(not isinstance(s, str) or not s.strip() for s in symbols) or symbols != sorted(set(symbols))):
        raise H20CaptureError("bounded_sorted_exact_symbols_required")
    observed = datetime.now(timezone.utc)
    pins = dict(request["source_pins"])
    if "observed_at" in pins:
        raise H20CaptureError("caller_cannot_backdate_pins")
    pins["observed_at"] = observed.isoformat()
    source_port = source_verifier or _source_port
    contract_port = contract_verifier or _contract_port
    contract = dict(contract_port({"fit_receipt_path": str(gross_fit_receipt),
        "fit_receipt_sha256": expected_fit_receipt_sha256}))
    source = dict(source_port({"cycle_id": pins["cycle_id"],
        "cycle_terminal_sha256": pins["cycle_terminal_sha256"], "pins": pins,
        "decision_date": observed.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat(),
        "data_root": request["data_root"], "history_start_date": request["history_start_date"],
        "feature_as_of_date": request["expected_feature_as_of_date"], "symbols": symbols}))
    predict = (predictor_factory or _predictor)(contract, source)
    result: dict[str, Any] = {"schema_version": "personal-current-observed-h20-daily-receipt.v1",
        "status": "completed", "captures": [], "outcomes": [], "cycle_id": pins["cycle_id"],
        "candidate_id": contract["candidate_id"], "contract_hash": contract["contract_hash"],
        "observed_at": observed.isoformat(), "fit_performed": False, "task_changed": False,
        "decision_date": source["decision_date"], "cycle_source_date": pins.get("cycle_source_date"),
        "feature_as_of_date": source["feature_as_of_date"],
        "historical_pit_eligible": False, "formal_training_allowed": False, "production_action_allowed": False}
    try:
        for symbol in symbols:
            if cancelled is not None and cancelled():
                raise InterruptedError("cancelled_between_saved_rows")
            def original_prediction() -> Mapping[str, Any]:
                return predict(symbol)
            saved = capture_personal_current_observed_h20_prediction(root=root, source_binding=source,
                contract_binding=contract, symbol=symbol, source_verifier=source_port,
                contract_verifier=contract_port, predictor=original_prediction, cancelled=cancelled)
            result["captures"].append(saved)
            selection = dict(request.get("natural_outcome", {}))
            result["outcomes"].append(project_personal_current_observed_h20_outcome(
                prediction_path=saved["path"], prediction_sha256=saved["raw_sha256"], root=root,
                source_verifier=source_port, contract_verifier=contract_port,
                input_capture_path=selection.get("input_capture_path"),
                input_capture_sha256=selection.get("input_capture_sha256"), input_capture_verifier=_input_port,
                outcome_path=selection.get("outcome_path"), outcome_sha256=selection.get("outcome_sha256"),
                outcome_verifier=_outcome_port))
    except (KeyboardInterrupt, InterruptedError) as exc:
        result.update(status="cancelled", reason=str(exc))
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__, reason=str(exc))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("request-json", "request-sha256", "receipt-root", "gross-fit-receipt", "gross-fit-receipt-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        request = read_pinned_json(Path(args.request_json), args.request_sha256)
        result = run_personal_current_observed_h20_daily(request=request, receipt_root=args.receipt_root,
            gross_fit_receipt=args.gross_fit_receipt, expected_fit_receipt_sha256=args.gross_fit_receipt_sha256)
    except KeyboardInterrupt:
        result = {"status": "cancelled"}
    except Exception as exc:
        result = {"status": "failed", "error_type": type(exc).__name__, "reason": str(exc)}
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "completed" else 130 if result["status"] == "cancelled" else 2


if __name__ == "__main__":
    raise SystemExit(main())
