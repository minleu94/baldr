"""既有日常流程的原 entry→manifest pins 登記與自然結果 caller。"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app_module.recommendation.personal_h20_activation import read_personal_h20_activation
from app_module.recommendation.personal_current_observed_h20_capture import publish, read_pinned_json, require_digest
from app_module.recommendation.personal_h20_natural_outcome_batch import run_personal_h20_natural_outcome_batch
from app_module.recommendation.personal_h20_product_evidence import read_personal_h20_daily_manifest


def _ports() -> dict[str, Callable[..., Any]]:
    from scripts.scheduled.personal_h20_daily_hook import read_personal_h20_prediction
    from scripts.scheduled.run_personal_current_observed_h20_daily import personal_current_observed_h20_read_ports
    return {**personal_current_observed_h20_read_ports(), "prediction_reader": read_personal_h20_prediction}


def register_personal_h20_natural_entry(config_path: Path | None, *, daily: Mapping[str, Any] | None,
    entry: Mapping[str, Any], ports: Mapping[str, Callable[..., Any]] | None = None) -> Mapping[str, Any]:
    """先由原 caller 核全員 exact entry，再保存僅含指標的 create-only 綁定。"""
    if config_path is None or daily is None or daily.get("effective_model_run") is not True:
        return {"status": "not_configured"}
    try:
        activation = read_personal_h20_activation(config_path)
        if not activation.enabled:
            return {"status": "disabled"}
        if (daily.get("candidate_id") != activation.candidate_id
                or daily.get("contract_hash") != activation.model_contract_hash):
            raise ValueError("personal_h20_natural_activation_model_mismatch")
        root = Path(activation.personal_root)
        selected: dict[str, Any] = dict(ports or _ports())
        request = {"manifest_path": daily["receipt_path"], "manifest_sha256": daily["receipt_sha256"], "root": root}
        captured = (entry.get("status") == "captured" and entry.get("cycle_id") == daily.get("cycle_id")
            and entry.get("decision_date") == daily.get("decision_date"))
        if captured:
            request.update(input_capture_path=entry["capture_path"], input_capture_sha256=entry["capture_sha256"])
        result = dict(run_personal_h20_natural_outcome_batch(**request, **selected))
        if captured and result["status"] == "completed":
            pin = require_digest(entry["capture_sha256"])
            body = {"schema_version": "personal-h20-natural-entry-binding.v1",
                "manifest_path": str(daily["receipt_path"]), "manifest_sha256": daily["receipt_sha256"],
                "input_capture_path": str(entry["capture_path"]), "input_capture_sha256": pin,
                "cycle_id": result["cycle_id"], "decision_date": result["decision_date"],
                "candidate_id": result["candidate_id"], "contract_hash": result["contract_hash"]}
            if read_personal_h20_activation(config_path) != activation:
                raise ValueError("personal_h20_natural_activation_changed")
            result["entry_binding_path"] = str(publish(root, "h20_natural_entry_bindings", pin[7:] + ".json", body))
        return result
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc)[:400], "promotion_credit_created": False}


def consume_personal_h20_natural_outcome(config_path: Path | None, *, pins: Mapping[str, Any],
    ports: Mapping[str, Callable[..., Any]] | None = None) -> Mapping[str, Any]:
    """用原 capture raw SHA 定址已登記的 manifest；不掃 latest/glob、不跨日期借樣本。"""
    if config_path is None:
        return {"status": "not_configured"}
    try:
        activation = read_personal_h20_activation(config_path)
        if not activation.enabled:
            return {"status": "disabled"}
        root = Path(activation.personal_root)
        pin = require_digest(pins["capture_sha256"])
        path = root / "h20_natural_entry_bindings" / (pin[7:] + ".json")
        try:
            binding = read_pinned_json(path)
        except FileNotFoundError:
            return {"status": "pending", "reason": "exact_registered_manifest_missing",
                "input_capture_sha256": pin, "promotion_credit_created": False}
        if (binding["schema_version"] != "personal-h20-natural-entry-binding.v1"
                or binding["input_capture_sha256"] != pin
                or Path(binding["input_capture_path"]) != Path(pins["capture_path"])):
            raise ValueError("personal_h20_natural_registered_entry_mismatch")
        selected: dict[str, Any] = dict(ports or _ports())
        manifest = read_personal_h20_daily_manifest(binding["manifest_path"], root=root,
            expected_sha256=binding["manifest_sha256"], prediction_reader=selected["prediction_reader"])
        if any(manifest[key] != binding[key] for key in ("cycle_id", "decision_date", "candidate_id", "contract_hash")):
            raise ValueError("personal_h20_natural_registered_manifest_mismatch")
        result = dict(run_personal_h20_natural_outcome_batch(
            manifest_path=binding["manifest_path"], manifest_sha256=binding["manifest_sha256"], root=root,
            input_capture_path=pins["capture_path"], input_capture_sha256=pin,
            outcome_path=pins["outcome_path"], outcome_sha256=pins["outcome_sha256"], **selected))
        if any(result[key] != binding[key] for key in ("cycle_id", "decision_date", "candidate_id", "contract_hash")):
            raise ValueError("personal_h20_natural_registered_manifest_mismatch")
        return result
    except Exception as exc:
        return {"status": "blocked", "reason": str(exc)[:400], "promotion_credit_created": False}
