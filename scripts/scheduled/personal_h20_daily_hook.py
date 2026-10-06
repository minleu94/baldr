"""既有每日 invocation 的個人 H20 接線；不依賴 entry capture 或新訓練。"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
import importlib
from pathlib import Path
from typing import Any

from app_module.recommendation.personal_h20_activation import read_personal_h20_activation

SOURCE_PIN_KEYS = (
    "cycle_id", "raw_run_id", "cycle_source_date",
    "cycle_terminal_path", "cycle_terminal_sha256",
    "snapshot_database_path", "snapshot_database_sha256",
    "snapshot_receipt_path", "snapshot_receipt_sha256",
    "source_context_envelope_path", "source_context_envelope_sha256",
)


def read_personal_h20_prediction(path: str | Path, *, root: Path, expected_sha256: str) -> Mapping[str, Any]:
    """公開CLI composition接原App reader；App/Qt不用import ML。"""
    module = importlib.import_module("scripts.scheduled.run_personal_current_observed_h20_daily")
    ports = getattr(module, "personal_current_observed_h20_read_ports")()
    capture_module = importlib.import_module("app_module.recommendation.personal_current_observed_h20_capture")
    return getattr(capture_module, "read_personal_current_observed_h20_capture")(
        path, root=root, expected_sha256=expected_sha256,
        source_verifier=ports["source_verifier"], contract_verifier=ports["contract_verifier"])


def read_personal_h20_daily_receipt(path: str | Path, *, root: Path, expected_sha256: str,
                                   selected_stock: str | None = None) -> Mapping[str, Any]:
    from app_module.recommendation.personal_h20_product_evidence import read_personal_h20_daily_manifest

    return read_personal_h20_daily_manifest(path, root=root, expected_sha256=expected_sha256,
        selected_stock=selected_stock, prediction_reader=read_personal_h20_prediction)


def read_personal_h20_product_cohort(config_path: Path, *, market_root: Path,
    cancel_callback: Callable[[], bool] | None = None) -> tuple[Any, Any]:
    """背景載入原完整母體；設定／指標在讀取中變更即拒絕。"""
    from app_module.recommendation.personal_h20_product_evidence import read_personal_h20_product_reference
    from app_module.recommendation.personal_h20_research_cohort import read_personal_h20_research_cohort

    reference = read_personal_h20_product_reference(config_path, market_root=market_root)
    def reader(path: str | Path, *, root: Path, expected_sha256: str) -> Mapping[str, Any]:
        if cancel_callback is not None and cancel_callback():
            raise InterruptedError("personal_h20_cohort_cancelled")
        return read_personal_h20_prediction(path, root=root, expected_sha256=expected_sha256)
    cohort = read_personal_h20_research_cohort(reference.manifest_path,
        root=Path(reference.activation.personal_root), expected_sha256=reference.manifest_sha256,
        prediction_reader=reader)
    if (cohort.candidate_id != reference.activation.candidate_id
            or cohort.contract_hash != reference.activation.model_contract_hash
            or cohort.cycle_id != reference.cycle_id or cohort.decision_date != reference.decision_date
            or read_personal_h20_product_reference(config_path, market_root=market_root) != reference
            or (cancel_callback is not None and cancel_callback())):
        raise ValueError("personal_h20_cohort_reference_changed")
    return reference, cohort


def run_personal_h20_for_current_cycle(
    config_path: Path | None, source_binding: Mapping[str, Any] | None, *,
    market_root: Path,
    expected_raw_run_id: str | None,
    runner: Callable[..., Any] | None = None,
    contract_verifier: Callable[..., Any] | None = None,
    daily_reader: Callable[..., Any] | None = None,
    prediction_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """只在明示 enabled 時呼叫受驗 daily runner；它重驗原 terminal bytes。"""
    if config_path is None:
        return {"status": "not_configured", "effective_model_run": False}
    try:
        activation = read_personal_h20_activation(config_path)
        if not activation.enabled:
            return {"status": "disabled", "revision": activation.revision, "effective_model_run": False}
        if Path(activation.market_root) != market_root:
            raise ValueError("personal_h20_market_root_mismatch")
        if source_binding is None or source_binding.get("binding_mode") != "current_observed":
            return {"status": "pending_current_cycle", "effective_model_run": False}
        if not expected_raw_run_id or source_binding.get("raw_run_id") != expected_raw_run_id:
            raise ValueError("personal_h20_exact_raw_run_required")
        pins = {key: source_binding.get(key) for key in SOURCE_PIN_KEYS}
        if any(type(value) is not str or not value for value in pins.values()):
            raise ValueError("personal_h20_complete_source_pins_required")
        snapshot = source_binding.get("current_observed_feature_snapshot")
        if not isinstance(snapshot, Mapping):
            raise ValueError("personal_h20_feature_scope_required")
        symbols = snapshot.get("symbols")
        if (not isinstance(symbols, list) or not symbols
                or any(type(symbol) is not str or not symbol for symbol in symbols)
                or len(set(symbols)) != len(symbols)):
            raise ValueError("personal_h20_unique_feature_scope_required")
        if sorted(symbols) != sorted(source_binding.get("symbols", [])):
            raise ValueError("personal_h20_complete_feature_scope_required")
        feature_date = source_binding.get("feature_as_of_date")
        decision_date = source_binding.get("decision_date")
        if (type(feature_date) is not str or type(decision_date) is not str
                or date.fromisoformat(feature_date) >= date.fromisoformat(decision_date)):
            raise ValueError("personal_h20_feature_not_before_decision")
        if contract_verifier is None:
            from scripts.qa_prepare_personal_h20_gross_contract import prepare_contract

            contract_verifier = prepare_contract
        prepared = contract_verifier(Path(activation.fit_receipt), expected_fit_receipt_sha256=activation.fit_receipt_sha256)
        if (prepared["contract_hash"] != activation.model_contract_hash
                or prepared["contract"]["candidate_id"] != activation.candidate_id
                or prepared["contract"]["model_id"] != activation.model_id):
            raise ValueError("personal_h20_activation_contract_mismatch")
        request = {
            "schema_version": "personal-current-observed-h20-daily-request.v1",
            "data_root": activation.market_root, "source_pins": pins,
            "symbols": sorted(symbols), "history_start_date": activation.history_start_date,
            "expected_feature_as_of_date": feature_date,
        }
        if runner is None:
            module = importlib.import_module("scripts.scheduled.run_personal_current_observed_h20_daily")
            candidate = getattr(module, "run_personal_current_observed_h20_daily")
            if not callable(candidate):
                raise ValueError("personal_h20_runner_required")
            runner = candidate
        result = runner(request=request, receipt_root=Path(activation.personal_root),
                        gross_fit_receipt=Path(activation.fit_receipt),
                        expected_fit_receipt_sha256=activation.fit_receipt_sha256)
        if not isinstance(result, dict):
            raise ValueError("personal_h20_runner_receipt_required")
        result = dict(result)
        if result.get("status") == "completed":
            from app_module.recommendation.personal_h20_product_evidence import (
                publish_personal_h20_product_reference, save_personal_h20_daily_manifest,
            )

            receipt_path, receipt_pin, daily = save_personal_h20_daily_manifest(activation, result,
                expected_symbols=sorted(symbols), prediction_reader=prediction_reader or read_personal_h20_prediction)
            if daily_reader is None:
                daily_reader = read_personal_h20_daily_receipt
            daily = daily_reader(receipt_path, root=Path(activation.personal_root), expected_sha256=receipt_pin)
            if (daily["status"] != "completed" or daily["candidate_id"] != activation.candidate_id
                    or daily["contract_hash"] != activation.model_contract_hash
                    or daily["cycle_id"] != pins["cycle_id"]
                    or sorted(pin["symbol"] for pin in daily["captures"]) != sorted(symbols)):
                raise ValueError("personal_h20_completed_public_receipt_mismatch")
            publish_personal_h20_product_reference(activation, receipt_path=str(receipt_path),
                receipt_sha256=receipt_pin, decision_date=daily["decision_date"], cycle_id=daily["cycle_id"])
            result.update(receipt_path=str(receipt_path), receipt_sha256=receipt_pin)
            result["effective_model_run"] = True
        result.update(activation_revision=activation.revision, personal_scope_id=activation.scope_id,
                      expected_model_contract_hash=activation.model_contract_hash)
        return result
    except Exception as exc:
        # 不吞成成功，不提升原 formal/global 狀態；錯誤獨立留在 invocation 收據。
        return {"status": "blocked", "reason": str(exc)[:400], "effective_model_run": False}
