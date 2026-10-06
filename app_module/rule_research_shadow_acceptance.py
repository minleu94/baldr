"""UX23: pinned, research-only acceptance envelope for isolated shadow review."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app_module.rule_research_fair_comparison import build_fair_comparison
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    MAX_CAPTURE_BYTES,
    RuleSampleCaptureError,
    _read_file,
)
from ml_module.model_lifecycle_registry import ModelLifecycleEvent, _ALLOWED_TRANSITIONS


ACCEPTANCE_SCHEMA = "rule-research-shadow-acceptance.v1"
LIFECYCLE_EXPORT_SCHEMA = "rule-research-shadow-lifecycle-export.v1"
RECEIPT_SCHEMA = "rule-research-shadow-acceptance-receipt.v1"
MAX_RECEIPTS = 32
MAX_SOURCE_FILE_BYTES = 256 * 1024
MAX_SOURCE_TOTAL_BYTES = 2 * 1024 * 1024
MAX_INPUT_CONTEXT_BYTES = MAX_SOURCE_TOTAL_BYTES + 128 * 1024
_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_IDENTITY_EXCLUDED = {"capture_identity_sha256", "observed_at"}
_SAFETY_FLAGS = {
    "research_only": True,
    "shadow_enabled": False,
    "production_enabled": False,
    "formal_eligible": False,
    "production_action_allowed": False,
    "formal_rule_unchanged": True,
    "training_eligible": False,
    "historical_pit_eligible": False,
    "natural_authority": False,
    "execution_eligible": False,
    "production_blend_alpha_bp": 0,
    "selection_status": "unknown",
    "qualified_count": 0,
}
_TERMINAL_PROJECTION_STATES = {
    "disabled", "superseded", "rollback_requested", "review_required",
}
_TOP_STATUSES = {
    "shadow_engineering_executable_research_only",
    "rule_only_fallback", "stopped", "cancelled",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(report: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in report.items()
                if key not in _IDENTITY_EXCLUDED}
    return _digest(_canonical(unsigned).encode("utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_aware(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _input_path(value: object) -> str:
    if isinstance(value, (str, Path)):
        result = str(value)
        if len(result) > 1024:
            raise ValueError("shadow_receipt_path_bound")
        return result
    raise ValueError("shadow_receipt_path_invalid")


def _pin_one(path_text: str, budget: int) -> tuple[str | None, int]:
    """Hash one receipt through the shared no-link, bounded reader."""
    try:
        path = Path(path_text)
        bound = min(MAX_SOURCE_FILE_BYTES, budget)
        if bound < 0:
            return None, 0
        raw = _read_file(path, bound)
        return _digest(raw), len(raw)
    except (OSError, ValueError, RuleSampleCaptureError):
        return None, 0


def _input_pins(receipts: object) -> list[dict[str, Any]]:
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        return []
    result: list[dict[str, Any]] = []
    budget = MAX_SOURCE_TOTAL_BYTES
    for pair in receipts:
        if isinstance(pair, Sequence) and not isinstance(pair, (str, bytes)) and len(pair) == 2:
            parent_path, outcome_path = _input_path(pair[0]), _input_path(pair[1])
        else:
            parent_path = outcome_path = "<invalid-path>"
        parent_hash, parent_size = _pin_one(parent_path, budget)
        budget -= parent_size
        outcome_hash, outcome_size = _pin_one(outcome_path, budget)
        budget -= outcome_size
        result.append({
            "parent_receipt_path": parent_path,
            "parent_receipt_file_sha256": parent_hash,
            "outcome_receipt_path": outcome_path,
            "outcome_receipt_file_sha256": outcome_hash,
        })
    return result


def _copy_metrics(role: object) -> dict[str, Any] | None:
    if not isinstance(role, dict):
        return None
    pin = role.get("model_pin")
    metrics = role.get("metrics")
    if not isinstance(pin, dict):
        pin = None
    if not isinstance(metrics, dict):
        metrics = None
    return {
        "model_pin": pin,
        "prediction_count": role.get("prediction_count"),
        "common_cohort_count": role.get("common_cohort_count"),
        "metrics": metrics,
    }


def _compact_comparison(value: object, fallback_pins: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    common = value.get("common_cohort")
    source_pins = value.get("source_pins")
    if not isinstance(common, dict):
        common = {}
    if not isinstance(source_pins, list):
        source_pins = []
    if len(source_pins) > MAX_RECEIPTS:
        raise ValueError("acceptance_source_pin_bound")
    keys = (
        "report_identity_sha256", "label_readiness_identity_sha256",
        "comparison_binding_sha256", "bundle_identity_sha256",
        "comparison_policy_sha256", "label_policy_sha256", "split_policy_sha256",
        "method_id", "horizon", "measure", "metrics_policy", "top_k",
        "source_semantics", "source_denominators", "label_denominators",
        "cohort_denominators", "metric_differences", "metric_scope",
        "reason_codes", "summary_text", "metric_interpretation",
    )
    result = {key: value.get(key) for key in keys if key in value}
    result.update({
        "schema_version": value.get("schema_version"),
        "status": value.get("status", "comparison_failed"),
        "common_cohort_count": common.get("count", 0),
        "baseline": _copy_metrics(value.get("baseline")),
        "candidate": _copy_metrics(value.get("candidate")),
        "common_cohort_identity_sha256": _digest(
            _canonical(common.get("sample_ids", [])).encode("utf-8")),
        "source_pins": source_pins,
        "input_receipt_pins": fallback_pins,
    })
    return result


def _model_pin_from_comparison(comparison: dict[str, Any]) -> dict[str, Any] | None:
    candidate = comparison.get("candidate")
    if not isinstance(candidate, dict):
        return None
    pin = candidate.get("model_pin")
    return pin if isinstance(pin, dict) else None


def _validate_lifecycle(
    export: object, model_pin: dict[str, Any] | None, observed_at: str,
) -> dict[str, Any]:
    if export is None:
        return {"status": "missing", "valid": False, "reason_codes": ["lifecycle_export_missing"],
                "event_count": 0, "current_status": None, "model_pin": model_pin}
    try:
        if not isinstance(export, dict):
            raise ValueError("lifecycle_export_not_object")
        expected_keys = {"schema_version", "model_id", "dataset_id", "artifact_hash", "events", "metadata"}
        if set(export) != expected_keys or export.get("schema_version") != LIFECYCLE_EXPORT_SCHEMA:
            raise ValueError("lifecycle_export_schema_invalid")
        if model_pin is None:
            raise ValueError("candidate_model_pin_missing")
        for name in ("model_id", "dataset_id"):
            if not isinstance(export.get(name), str) or not export[name].strip():
                raise ValueError(f"lifecycle_{name}_invalid")
        if not isinstance(export.get("artifact_hash"), str) or not _SHA256.fullmatch(export["artifact_hash"]):
            raise ValueError("lifecycle_artifact_hash_invalid")
        if any(export.get(name) != model_pin.get(name) for name in ("model_id", "dataset_id", "artifact_hash")):
            raise ValueError("lifecycle_model_pin_mismatch")
        if export.get("metadata") != model_pin:
            raise ValueError("lifecycle_metadata_pin_mismatch")
        events = export.get("events")
        if not isinstance(events, list) or len(events) > 256:
            raise ValueError("lifecycle_events_invalid")
        observed = _parse_aware(observed_at, "observed_at")
        event_ids: set[str] = set()
        previous_time: datetime | None = None
        current: str | None = None
        for raw in events:
            if not isinstance(raw, dict) or set(raw) != {"event_id", "model_id", "event_type", "created_at", "reason"}:
                raise ValueError("lifecycle_event_schema_invalid")
            if any(not isinstance(raw.get(key), str) or not raw[key].strip()
                   for key in ("event_id", "model_id", "event_type", "created_at", "reason")):
                raise ValueError("lifecycle_event_text_invalid")
            if raw["model_id"] != model_pin.get("model_id") or raw["event_id"] in event_ids:
                raise ValueError("lifecycle_event_identity_mismatch")
            event_time = _parse_aware(raw["created_at"], "lifecycle_event_created_at")
            if event_time > observed or (previous_time is not None and event_time < previous_time):
                raise ValueError("lifecycle_event_time_invalid")
            event = ModelLifecycleEvent(**raw)
            if event.event_type not in _ALLOWED_TRANSITIONS[current]:
                raise ValueError("lifecycle_transition_invalid")
            current = event.event_type
            previous_time = event_time
            event_ids.add(event.event_id)
        state = "stopped" if current in _TERMINAL_PROJECTION_STATES else "validated"
        return {"status": state, "valid": True, "reason_codes": [],
                "event_count": len(events), "current_status": current, "model_pin": model_pin,
                "export_sha256": _digest(_canonical(export).encode("utf-8"))}
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "invalid", "valid": False,
                "reason_codes": [str(exc)[:160] or "lifecycle_export_invalid"],
                "event_count": 0, "current_status": None, "model_pin": model_pin}


def _summary(status: str, comparison: dict[str, Any], lifecycle: dict[str, Any], stop_reason: str | None) -> str:
    common = comparison.get("common_cohort_count", 0)
    denominators = comparison.get("cohort_denominators")
    selected = denominators.get("selected_method_horizon_members", 0) if isinstance(denominators, dict) else "未提供"
    if status == "cancelled":
        engineering = "已取消，沒有保留部分比較結果"
    elif status == "stopped":
        engineering = f"已依明示原因停止隔離研究投影（{stop_reason}）"
    elif status == "shadow_engineering_executable_research_only":
        engineering = "隔離研究流程工程可執行（僅限研究投影）"
    else:
        engineering = "工程尚未完成，保留規則路徑（研究設定、模型或狀態資料不足或不相容）"
    if status == "stopped":
        engineering = "已依明示停止原因停止隔離研究投影"
    return (f"工程軸：{engineering}。資料／效果軸：尚未合格，所選方法目標 {selected} 筆、共同比較 {common} 筆，"
            "任何指標僅屬研究觀察。啟用軸：未啟用；影子投影與正式行為保持關閉。")


def _validate_report(report: object) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("acceptance_report_not_object")
    if report.get("schema_version") != ACCEPTANCE_SCHEMA:
        raise ValueError("acceptance_schema_version_invalid")
    if not isinstance(report.get("capture_identity_sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", report["capture_identity_sha256"]):
        raise ValueError("acceptance_identity_invalid")
    if report["capture_identity_sha256"] != _identity(report):
        raise ValueError("acceptance_identity_mismatch")
    if not isinstance(report.get("case_id"), str) or not report["case_id"].strip():
        raise ValueError("acceptance_case_id_invalid")
    _parse_aware(report.get("observed_at"), "observed_at")
    if report.get("status") not in _TOP_STATUSES:
        raise ValueError("acceptance_status_invalid")
    comparison, lifecycle = report.get("comparison"), report.get("lifecycle")
    if not isinstance(comparison, dict) or not isinstance(lifecycle, dict):
        raise ValueError("acceptance_diagnostics_invalid")
    flags = report.get("safety_flags")
    if (not isinstance(flags, dict) or set(flags) != set(_SAFETY_FLAGS)
            or any(type(flags[key]) is not type(value) or flags[key] != value
                   for key, value in _SAFETY_FLAGS.items())):
        raise ValueError("acceptance_safety_flags_invalid")
    axes = {
        "data_effect_status": "not_qualified_research_only",
        "activation_status": "not_enabled",
    }
    if any(report.get(key) != value for key, value in axes.items()):
        raise ValueError("acceptance_axis_invalid")
    status = report["status"]
    engineering = report.get("engineering_status")
    diagnostics = report.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raise ValueError("acceptance_diagnostics_invalid")
    stop_reason = diagnostics.get("stop_reason")
    if status == "stopped":
        if not isinstance(stop_reason, str) or not stop_reason.strip():
            raise ValueError("acceptance_stop_reason_missing")
    elif stop_reason is not None:
        raise ValueError("acceptance_unexpected_stop_reason")
    if status != "cancelled" and (
            not isinstance(diagnostics.get("input_contract_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", diagnostics["input_contract_sha256"])):
        raise ValueError("acceptance_input_contract_pin_missing")
    candidate_pin = _model_pin_from_comparison(comparison)
    lifecycle_status = lifecycle.get("status")
    if lifecycle_status in {"validated", "stopped"}:
        current = lifecycle.get("current_status")
        event_count = lifecycle.get("event_count")
        export_hash = lifecycle.get("export_sha256")
        if (candidate_pin is None or lifecycle.get("valid") is not True
                or lifecycle.get("model_pin") != candidate_pin
                or type(event_count) is not int or not 0 <= event_count <= 256
                or not isinstance(export_hash, str) or not _SHA256.fullmatch(export_hash)):
            raise ValueError("acceptance_lifecycle_binding_invalid")
        if (current is None and event_count != 0) or (current is not None and event_count == 0):
            raise ValueError("acceptance_lifecycle_event_count_invalid")
        if lifecycle_status == "validated" and current not in {None, "activated_for_shadow"}:
            raise ValueError("acceptance_lifecycle_projection_state_invalid")
        if lifecycle_status == "stopped" and current not in _TERMINAL_PROJECTION_STATES:
            raise ValueError("acceptance_lifecycle_stop_state_invalid")
    elif lifecycle_status == "missing":
        if lifecycle.get("valid") is not False or lifecycle.get("event_count") != 0:
            raise ValueError("acceptance_lifecycle_missing_state_invalid")
    elif lifecycle_status == "invalid":
        if lifecycle.get("valid") is not False:
            raise ValueError("acceptance_lifecycle_invalid_state_invalid")
    elif lifecycle_status != "not_checked":
        raise ValueError("acceptance_lifecycle_status_invalid")
    if status == "cancelled":
        if engineering != "cancelled":
            raise ValueError("acceptance_cancelled_axis_invalid")
    elif status == "stopped":
        if engineering != "explicitly_stopped":
            raise ValueError("acceptance_stopped_axis_invalid")
    elif status == "shadow_engineering_executable_research_only":
        if (engineering != "shadow_engineering_executable" or comparison.get("status") != "research_only_comparison"
                or type(comparison.get("common_cohort_count")) is not int
                or comparison["common_cohort_count"] <= 0
                or _model_pin_from_comparison(comparison) is None
                or lifecycle.get("status") != "validated" or lifecycle.get("valid") is not True):
            raise ValueError("acceptance_executable_state_invalid")
    elif status == "rule_only_fallback":
        if engineering != "rule_only_fallback":
            raise ValueError("acceptance_fallback_axis_invalid")
        if (comparison.get("status") == "research_only_comparison"
                and type(comparison.get("common_cohort_count")) is int
                and comparison["common_cohort_count"] > 0
                and _model_pin_from_comparison(comparison) is not None
                and lifecycle.get("status") == "validated" and lifecycle.get("valid") is True):
            raise ValueError("acceptance_fallback_state_inconsistent")
    expected = _summary(status, comparison, lifecycle, stop_reason)
    if report.get("summary_text") != expected:
        raise ValueError("acceptance_summary_inconsistent")
    return report


def _seal(report: dict[str, Any]) -> dict[str, Any]:
    report["capture_identity_sha256"] = _identity(report)
    if len(_canonical(report).encode("utf-8")) > MAX_CAPTURE_BYTES:
        raise ValueError("shadow_acceptance_report_byte_bound")
    return _validate_report(report)


def _cancelled_report(case_id: str, pins: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    comparison = {"schema_version": None, "status": "cancelled", "common_cohort_count": 0,
                  "source_pins": [], "input_receipt_pins": pins, "baseline": None,
                  "candidate": None, "reason_codes": ["cancelled"]}
    lifecycle = {"status": "not_checked", "valid": False, "reason_codes": ["cancelled"],
                 "event_count": 0, "current_status": None, "model_pin": None}
    report = _base_report(case_id, "cancelled", "cancelled", comparison, lifecycle,
                          {"cancel_reason": reason})
    return _seal(report)


def _base_report(case_id: str, status: str, engineering_status: str,
                 comparison: dict[str, Any], lifecycle: dict[str, Any],
                 diagnostics: dict[str, Any]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": ACCEPTANCE_SCHEMA,
        "capture_identity_sha256": "0" * 64,
        "observed_at": _utc_now(),
        "case_id": case_id,
        "status": status,
        "engineering_status": engineering_status,
        "data_effect_status": "not_qualified_research_only",
        "activation_status": "not_enabled",
        "comparison": comparison,
        "lifecycle": lifecycle,
        "diagnostics": diagnostics,
        "safety_flags": dict(_SAFETY_FLAGS),
        "summary_text": "",
    }
    report["summary_text"] = _summary(status, comparison, lifecycle, diagnostics.get("stop_reason"))
    return report


def build_shadow_acceptance(
    receipts: Sequence[tuple[str | Path, str | Path]], *, case_id: str,
    label_policy: dict[str, Any] | None,
    split_policy: dict[str, Any] | None,
    comparison_policy: dict[str, Any] | None = None,
    bundle: dict[str, Any] | None = None,
    lifecycle_export: dict[str, Any] | None = None,
    stop_reason: str | None = None,
    cancel_callback: Callable[[], bool] | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a compact, read-only decision envelope; no eligibility is granted."""
    if not isinstance(case_id, str) or not case_id.strip() or len(case_id) > 128:
        raise ValueError("case_id_invalid")
    if stop_reason is not None and (not isinstance(stop_reason, str) or not stop_reason.strip()
                                    or len(stop_reason) > 256):
        raise ValueError("stop_reason_invalid")
    if observed_at is not None and (not isinstance(observed_at, datetime)
                                    or observed_at.tzinfo is None or observed_at.utcoffset() is None):
        raise ValueError("observed_at_timezone_missing")
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise ValueError("shadow_receipts_sequence_required")
    if not 1 <= len(receipts) <= MAX_RECEIPTS:
        raise ValueError("shadow_receipt_count_bound")
    pins = _input_pins(receipts)
    input_context = {
        "receipt_input_pins": pins,
        "label_policy": label_policy,
        "split_policy": split_policy,
        "comparison_policy": comparison_policy,
        "bundle": bundle,
        "lifecycle_export": lifecycle_export,
        "stop_reason": stop_reason,
    }
    try:
        context_raw = _canonical(input_context).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("shadow_input_context_not_json") from exc
    if len(context_raw) > MAX_INPUT_CONTEXT_BYTES:
        raise ValueError("shadow_input_context_byte_bound")
    input_contract_sha256 = _digest(context_raw)
    cancel_error: list[str] = []

    def checked_cancel() -> bool:
        if cancel_callback is None:
            return False
        try:
            return bool(cancel_callback())
        except Exception as exc:
            cancel_error.append(type(exc).__name__)
            return True

    if cancel_callback is not None:
        if checked_cancel():
            why = "cancel_callback_error:" + cancel_error[-1] if cancel_error else "cancel_requested"
            return _cancelled_report(case_id, pins, why)
    try:
        fair = build_fair_comparison(
            receipts, label_policy, split_policy, comparison_policy, bundle,
            cancel_callback=checked_cancel,
        )
        if fair.get("status") == "cancelled" or cancel_error:
            why = "cancel_callback_error:" + cancel_error[-1] if cancel_error else "comparison_cancelled"
            return _cancelled_report(case_id, pins, why)
    except Exception as exc:
        # Malformed or stale exports fail closed into the rule-only outcome.
        fair = {"schema_version": None, "status": "comparison_failed",
                "reason_codes": [f"comparison_error:{type(exc).__name__}:{str(exc)[:120]}"],
                "source_pins": [], "common_cohort": {"count": 0, "sample_ids": []},
                "baseline": None, "candidate": None}
    if cancel_callback is not None:
        if checked_cancel():
            why = "cancel_callback_error:" + cancel_error[-1] if cancel_error else "cancel_requested_after_comparison"
            return _cancelled_report(case_id, pins, why)
    comparison = _compact_comparison(fair, pins)
    # A stop request takes precedence over the projection, but never skips input validation.
    observed = _utc_now()
    candidate_pin = _model_pin_from_comparison(comparison)
    lifecycle = _validate_lifecycle(lifecycle_export, candidate_pin, observed)
    can_project = (
        comparison.get("status") == "research_only_comparison"
        and type(comparison.get("common_cohort_count")) is int
        and comparison["common_cohort_count"] > 0
        and candidate_pin is not None
        and lifecycle.get("status") == "validated" and lifecycle.get("valid") is True
    )
    if stop_reason is not None:
        status, engineering = "stopped", "explicitly_stopped"
    elif can_project:
        status, engineering = "shadow_engineering_executable_research_only", "shadow_engineering_executable"
    else:
        status, engineering = "rule_only_fallback", "rule_only_fallback"
    diagnostics = {
        "stop_reason": stop_reason,
        "input_contract_sha256": input_contract_sha256,
        "comparison_reason_codes": fair.get("reason_codes", []) if isinstance(fair, dict) else [],
        "comparison_error": fair.get("reason_codes", []) if fair.get("status") == "comparison_failed" else [],
    }
    return _seal(_base_report(case_id, status, engineering, comparison, lifecycle, diagnostics))


@dataclass(frozen=True, slots=True)
class _AcceptanceCapture:
    body_json: str

    @property
    def identity_sha256(self) -> str:
        return str(self.to_dict()["capture_identity_sha256"])

    def to_dict(self) -> dict[str, Any]:
        if not isinstance(self.body_json, str) or len(self.body_json.encode("utf-8")) > MAX_CAPTURE_BYTES:
            raise RuleSampleCaptureError("capture_byte_limit")
        try:
            body = json.loads(self.body_json)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuleSampleCaptureError("capture_json_invalid") from exc
        if not isinstance(body, dict) or _canonical(body) != self.body_json:
            raise RuleSampleCaptureError("capture_noncanonical")
        return _validate_report(body)


class _AcceptanceCaptureWriter(BoundedRuleResearchCaptureWriter):
    def _decode_capture(self, raw: bytes) -> dict[str, Any]:
        try:
            return _AcceptanceCapture(raw.decode("utf-8")).to_dict()
        except (UnicodeDecodeError, ValueError, TypeError, KeyError) as exc:
            raise RuleSampleCaptureError("capture_acceptance_invalid") from exc

    def _make_receipt(self, body: dict[str, Any], raw: bytes) -> dict[str, Any]:
        return {
            "schema_version": RECEIPT_SCHEMA,
            "status": "complete",
            "capture_identity_sha256": body["capture_identity_sha256"],
            "capture_sha256": _digest(raw),
            "observed_at": body["observed_at"],
            "research_only": True,
        }


def _capture_for(report: dict[str, Any]) -> _AcceptanceCapture:
    checked = _validate_report(report)
    return _AcceptanceCapture(_canonical(checked))


def save_shadow_acceptance(
    report: dict[str, Any], output_root: str | Path, *, revalidate: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Persist one immutable UX23 envelope through the existing bounded writer."""
    checked = _validate_report(report)
    if checked["status"] == "cancelled":
        raise RuleSampleCaptureError("cancelled_report_not_publishable")
    if not callable(revalidate):
        raise ValueError("revalidate_callback_required")

    def fresh_capture() -> _AcceptanceCapture:
        fresh = revalidate()
        if not isinstance(fresh, dict) or fresh.get("status") == "cancelled":
            raise RuleSampleCaptureError("source_revision_during_capture")
        return _capture_for(fresh)

    return _AcceptanceCaptureWriter(output_root).write(_capture_for(checked), revalidate=fresh_capture)


def read_shadow_acceptance(output_root: str | Path, identity_sha256: str) -> dict[str, Any]:
    """Read one exact immutable acceptance receipt; never select a latest item."""
    return _AcceptanceCaptureWriter(output_root).read(identity_sha256)
