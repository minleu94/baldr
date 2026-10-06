"""B14 synthetic 預測封存／成熟／監測接線；只消費 B13 與注入的唯讀報告。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from typing import Literal, Protocol, cast
from zoneinfo import ZoneInfo

from app_module.rule_research_model_input_adapter import (
    ModelInputRunResult, ModelInputRunnerResult, PreparedModelInput,
    canonical_model_input_bytes, content_sha256, run_prepared_model_input,
)
from app_module.rule_research_shadow_control import (
    ControlApprovalProof, ControlContext, ControlSourcePin, ShadowControlCommand,
    ShadowControlIdentity, ShadowControlResult, ShadowControlService, aware,
    canonical, digest, hash_identity, text_identity,
)


class ShadowEvidenceCustody(Protocol):
    def verify_frozen(self, binding_sha256: str) -> bool: ...
    def verify_research(self, binding_sha256: str) -> bool: ...
    def current_evidence_revision(self, namespace: str) -> tuple[int, str | None]: ...
    def reserve_evidence_revision(self, namespace: str, expected_revision: int, receipt_sha256: str) -> bool: ...


class _OriginalResultReplay:
    """只回送 caller 原 bytes，讓 B13 重驗；不做推論／fit 或造新 Prediction DTO。"""

    def __init__(self, result: ModelInputRunResult) -> None:
        self.result = result

    def run(self, prepared: PreparedModelInput) -> ModelInputRunnerResult:
        result = self.result
        if result.status not in ("available", "unavailable") or result.result_payload is None or result.result_identity_sha256 is None:
            raise ValueError("original_result_unavailable")
        return ModelInputRunnerResult(cast(Literal["available", "unavailable"], result.status),
                                      result.prepared_identity_sha256, result.dataset_id, result.model_id,
                                      result.run_id, result.source_pins_sha256, result.result_identity_sha256,
                                      result.result_payload, result.blockers)


def revalidate_original_result(prepared: PreparedModelInput, result: ModelInputRunResult) -> None:
    verified = run_prepared_model_input(prepared, runner=_OriginalResultReplay(result))
    if verified != result or verified.status != "available":
        raise ValueError("b13_original_result_revalidation_failed:" + ",".join(verified.blockers))


@dataclass(frozen=True, slots=True)
class FrozenShadowEvidence:
    prepared: PreparedModelInput
    result: ModelInputRunResult
    model_identity: ShadowControlIdentity
    method_id: str
    prediction_available_at: datetime
    decision_cutoff: datetime
    decision_timezone: str
    captured_at: datetime

    @property
    def binding_sha256(self) -> str:
        return digest(canonical({
            "schema": "baldr-b14-frozen-binding.v1", "prepared": self.prepared.identity_sha256,
            "result": self.result.result_identity_sha256, "source_pins": self.result.source_pins_sha256,
            "model": asdict(self.model_identity), "method": self.method_id,
            "available": aware(self.prediction_available_at).isoformat(),
            "cutoff": aware(self.decision_cutoff).isoformat(), "timezone": self.decision_timezone,
            "captured": aware(self.captured_at).isoformat(),
        }))

    @property
    def production_action_allowed(self) -> bool:
        return False


def validate_frozen(frozen: FrozenShadowEvidence, custody: ShadowEvidenceCustody) -> None:
    revalidate_original_result(frozen.prepared, frozen.result)
    text_identity(frozen.method_id)
    evaluation = next(row for row in frozen.prepared.samples if row.phase == "evaluation")
    cutoff, available, captured = map(aware, (frozen.decision_cutoff, frozen.prediction_available_at, frozen.captured_at))
    if not available <= captured <= cutoff:
        raise ValueError("prediction_late_or_clock_mismatch")
    if cutoff.astimezone(ZoneInfo(frozen.decision_timezone)).date().isoformat() != evaluation.decision_date:
        raise ValueError("decision_date_cutoff_mismatch")
    if frozen.model_identity.model_id != frozen.result.model_id:
        raise ValueError("frozen_wrong_model")
    if frozen.method_id not in {row.method_id for row in frozen.prepared.fair_denominator}:
        raise ValueError("frozen_unknown_method")
    if custody.verify_frozen(frozen.binding_sha256) is not True:
        raise ValueError("independent_frozen_custody_required")


def freeze_shadow_evidence(prepared: PreparedModelInput, result: ModelInputRunResult, *,
                           model_identity: ShadowControlIdentity, method_id: str,
                           prediction_available_at: datetime, decision_cutoff: datetime,
                           decision_timezone: str, context: ControlContext,
                           custody: ShadowEvidenceCustody) -> FrozenShadowEvidence:
    now = context.check()
    frozen = FrozenShadowEvidence(prepared, result, model_identity, method_id, aware(prediction_available_at),
                                  aware(decision_cutoff), decision_timezone, now)
    validate_frozen(frozen, custody)
    context.check()
    return frozen


@dataclass(frozen=True, slots=True)
class ShadowMonitoringPolicy:
    policy_id: str
    version: str
    model_identity: ShadowControlIdentity
    target_policy_sha256: str
    method_ids: tuple[str, ...]
    monitored_method_id: str
    min_mature_samples: int
    max_mae_bp: int
    label_policy_sha256: str
    split_policy_sha256: str

    def __post_init__(self) -> None:
        text_identity(self.policy_id)
        text_identity(self.version)
        object.__setattr__(self, "method_ids", tuple(self.method_ids))
        if not self.method_ids or len(self.method_ids) > 16 or len(set(self.method_ids)) != len(self.method_ids):
            raise ValueError("monitoring_methods_invalid")
        for method in self.method_ids:
            text_identity(method)
        if self.monitored_method_id not in self.method_ids:
            raise ValueError("monitored_method_missing")
        if type(self.min_mature_samples) is not int or self.min_mature_samples <= 0:
            raise ValueError("minimum_mature_samples_invalid")
        if type(self.max_mae_bp) is not int or self.max_mae_bp < 0:
            raise ValueError("mae_threshold_invalid")
        for sha in (self.target_policy_sha256, self.label_policy_sha256, self.split_policy_sha256):
            hash_identity(sha)

    @property
    def identity_sha256(self) -> str:
        return digest(canonical(asdict(self)))


@dataclass(frozen=True, slots=True)
class ReadonlyResearchEvidence:
    label_report: bytes | None
    fair_report: bytes | None
    source_pins: tuple[ControlSourcePin, ...]
    available_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_pins", tuple(self.source_pins))
        if self.label_report is not None:
            object.__setattr__(self, "label_report", bytes(self.label_report))
        if self.fair_report is not None:
            object.__setattr__(self, "fair_report", bytes(self.fair_report))

    def binding_sha256(self, frozen: tuple[FrozenShadowEvidence, ...], policy: ShadowMonitoringPolicy, cutoff: datetime) -> str:
        return digest(canonical({"frozen": [f.binding_sha256 for f in frozen], "policy": policy.identity_sha256,
                                 "cutoff": aware(cutoff).isoformat(),
                                 "available_at": None if self.available_at is None else aware(self.available_at).isoformat(),
                                 "labels": None if self.label_report is None else digest(self.label_report),
                                 "fair": None if self.fair_report is None else digest(self.fair_report),
                                 "pins": [(p.role, p.source_id, p.custody_sha256) for p in self.source_pins]}))


class ReadonlyResearchPort(Protocol):
    def read(self, frozen: tuple[FrozenShadowEvidence, ...], policy: ShadowMonitoringPolicy,
             cutoff: datetime, context: ControlContext) -> ReadonlyResearchEvidence:
        """沿既有 rule label/fair readonly wrapper，返回 original report bytes 及 caller pins。"""
        ...


@dataclass(frozen=True, slots=True)
class ShadowMonitoringDecision:
    status: Literal["waiting", "stable", "review_required"]
    blockers: tuple[str, ...]
    model_identity: ShadowControlIdentity | None
    policy_sha256: str | None
    evidence_sha256: str | None
    mature_count: int
    full_denominator_count: int
    report_payload: bytes

    @property
    def identity_sha256(self) -> str:
        return digest(self.report_payload)

    @property
    def production_action_allowed(self) -> bool:
        return False


def _report(raw: bytes, schema: str) -> dict[str, object]:
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("readonly_report_capacity")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        raise ValueError("readonly_report_schema")
    sha = value.get("report_identity_sha256")
    unsigned = {k: v for k, v in value.items() if k != "report_identity_sha256"}
    if not isinstance(sha, str) or sha.removeprefix("sha256:") != digest(canonical(unsigned))[7:]:
        raise ValueError("readonly_report_identity_mismatch")
    if any(value.get(k) is not False for k in ("formal_eligible", "training_eligible", "historical_pit_eligible", "natural_authority", "execution_eligible")):
        raise ValueError("readonly_report_qualification_mismatch")
    return value


def _decision(status: Literal["waiting", "stable", "review_required"], blockers: tuple[str, ...],
              policy: ShadowMonitoringPolicy | None, evidence_sha: str | None,
              mature: int, denominators: list[dict[str, object]], cutoff: datetime) -> ShadowMonitoringDecision:
    raw = canonical({"schema_version": "baldr-b14-monitoring.v1", "status": status, "blockers": blockers,
                     "model_identity": None if policy is None else asdict(policy.model_identity),
                     "policy_sha256": None if policy is None else policy.identity_sha256,
                     "evidence_sha256": evidence_sha, "cutoff": aware(cutoff).isoformat(),
                     "mature_count": mature, "denominators": denominators,
                     "formal_eligible": False, "training_eligible": False, "historical_pit_eligible": False,
                     "natural_authority": False, "execution_eligible": False, "production_action_allowed": False})
    return ShadowMonitoringDecision(status, blockers, None if policy is None else policy.model_identity,
                                    None if policy is None else policy.identity_sha256, evidence_sha,
                                    mature, len(denominators), raw)


def evaluate_shadow_monitoring(frozen: tuple[FrozenShadowEvidence, ...], *, policy: ShadowMonitoringPolicy | None,
                                cutoff: datetime, source_port: ReadonlyResearchPort | None,
                                custody: ShadowEvidenceCustody, context: ControlContext) -> ShadowMonitoringDecision:
    frozen = tuple(frozen)
    cutoff = aware(cutoff)
    if cutoff > context.check():
        raise ValueError("monitoring_cutoff_in_future")
    if len(frozen) > 128:
        raise ValueError("monitoring_prediction_capacity")
    base_rows: dict[tuple[str, str, str], dict[str, object]] = {}
    for base_item in frozen:
        validate_frozen(base_item, custody)
        base_sample = next(r for r in base_item.prepared.samples if r.phase == "evaluation")
        for base in base_item.prepared.fair_denominator:
            if base.decision_date == base_sample.decision_date:
                base_rows[(base.symbol, base.decision_date, base.method_id)] = {
                    "symbol": base.symbol, "decision_date": base.decision_date, "method_id": base.method_id,
                    "state": "waiting", "source_state": base.status, "source_reason": base.reason}
    base_denominators = [base_rows[k] for k in sorted(base_rows)]
    if policy is None or source_port is None or not frozen:
        return _decision("waiting", ("monitoring_policy_source_or_predictions_missing",), policy, None, 0, base_denominators, cutoff)
    expected: set[tuple[str, str, str]] = set()
    predictions: dict[tuple[str, str], FrozenShadowEvidence] = {}
    for frozen_item in frozen:
        validate_frozen(frozen_item, custody)
        if frozen_item.model_identity != policy.model_identity or frozen_item.method_id != policy.monitored_method_id:
            raise ValueError("monitoring_model_or_method_mismatch")
        if content_sha256(canonical_model_input_bytes(frozen_item.prepared.policy)) != policy.target_policy_sha256:
            raise ValueError("monitoring_target_policy_mismatch")
        sample = next(r for r in frozen_item.prepared.samples if r.phase == "evaluation")
        prediction_key = (sample.symbol, sample.decision_date)
        if prediction_key in predictions:
            raise ValueError("duplicate_stock_decision_date")
        if frozen_item.decision_cutoff > cutoff:
            raise ValueError("monitoring_before_prediction_cutoff")
        predictions[prediction_key] = frozen_item
        methods = {r.method_id for r in frozen_item.prepared.fair_denominator}
        if methods != set(policy.method_ids):
            raise ValueError("monitoring_method_denominator_mismatch")
        expected.update((r.symbol, r.decision_date, r.method_id) for r in frozen_item.prepared.fair_denominator
                        if r.decision_date == sample.decision_date)
    model_versions = {(f.result.dataset_id, f.result.run_id,
                       next(p.content_sha256 for p in f.prepared.evidence.pins if p.role == "model_artifact")) for f in frozen}
    if len(model_versions) != 1:
        raise ValueError("monitoring_exact_model_artifact_run_mismatch")
    evidence = source_port.read(frozen, policy, cutoff, context)
    context.check()
    if evidence.available_at is None or evidence.label_report is None or evidence.fair_report is None:
        return _decision("waiting", ("readonly_source_or_clock_unknown",), policy, None, 0, base_denominators, cutoff)
    if aware(evidence.available_at) > cutoff:
        return _decision("waiting", ("readonly_source_after_cutoff",), policy, None, 0, base_denominators, cutoff)
    evidence_sha = evidence.binding_sha256(frozen, policy, cutoff)
    if custody.verify_research(evidence_sha) is not True:
        raise ValueError("independent_research_custody_required")
    pins = {p.role: p for p in evidence.source_pins}
    if len(pins) != len(evidence.source_pins) or not evidence.source_pins:
        raise ValueError("readonly_source_pin_inventory")
    for role, raw in (("label_report", evidence.label_report), ("fair_report", evidence.fair_report)):
        if role not in pins or pins[role].content != raw:
            raise ValueError("readonly_original_report_pin_mismatch")
    labels = _report(evidence.label_report, "rule-research-label-readiness.v1")
    fair = _report(evidence.fair_report, "rule-research-fair-comparison.v1")
    if labels.get("status") != "research_only" or fair.get("status") != "research_only_comparison":
        return _decision("waiting", ("readonly_reports_not_ready",), policy, evidence_sha, 0, base_denominators, cutoff)
    if (str(cast(dict[str, object], labels["label_policy"]).get("sha256")).removeprefix("sha256:") != policy.label_policy_sha256[7:]
            or str(cast(dict[str, object], labels["split_policy"]).get("sha256")).removeprefix("sha256:") != policy.split_policy_sha256[7:]
            or str(fair.get("label_readiness_identity_sha256")).removeprefix("sha256:") != str(labels["report_identity_sha256"]).removeprefix("sha256:")
            or fair.get("method_id") != policy.monitored_method_id):
        raise ValueError("readonly_policy_or_report_binding_mismatch")
    target = frozen[0].prepared.policy
    if (fair.get("horizon") != target.horizon_sessions or fair.get("measure") != "gross"
            or fair.get("metrics_policy") != "return_only"
            or str(fair.get("label_policy_sha256")).removeprefix("sha256:") != policy.label_policy_sha256[7:]
            or str(fair.get("split_policy_sha256")).removeprefix("sha256:") != policy.split_policy_sha256[7:]):
        raise ValueError("fair_target_policy_mismatch")
    rows = cast(list[dict[str, object]], labels["label_rows"])
    if not isinstance(rows, list) or len(rows) > 8192:
        raise ValueError("label_denominator_capacity")
    seen: set[tuple[str, str, str]] = set()
    mature_ids: set[str] = set()
    mature_keys: set[tuple[str, str]] = set()
    denominators: list[dict[str, object]] = []
    row_by_id: dict[str, dict[str, object]] = {}
    for row in rows:
        key = (str(row["stock_code"]), str(row["decision_date"]), str(row["method_id"]))
        if key in seen or key not in expected:
            raise ValueError("label_duplicate_or_wrong_universe")
        seen.add(key)
        if row.get("horizon") != f"H{target.horizon_sessions}" or row.get("measure") != "gross":
            raise ValueError("label_target_horizon_mismatch")
        sample_id = str(row["sample_id"])
        if sample_id in row_by_id:
            raise ValueError("label_duplicate_sample_id")
        row_by_id[sample_id] = row
        item = predictions.get(key[:2])
        state = "missing_prediction" if item is None else "waiting"
        if item is not None:
            sample = next(r for r in item.prepared.samples if r.phase == "evaluation")
            if row.get("horizon") != f"H{item.prepared.policy.horizon_sessions}" or row.get("measure") != "gross":
                raise ValueError("label_target_horizon_mismatch")
            available_date = row.get("available_date")
            mature = (row.get("availability_status") == "known_research_only" and isinstance(available_date, str)
                      and date.fromisoformat(available_date) <= cutoff.astimezone(ZoneInfo(item.decision_timezone)).date()
                      and row.get("label_end_date") == sample.horizon_end_date
                      and date.fromisoformat(sample.horizon_end_date) <= date.fromisoformat(available_date)
                      and row.get("split_role") == "evaluation_window_research_only"
                      and row.get("member_state") in ("matched", "notmatched") and type(row.get("value_bp")) is int)
            if mature and row["value_bp"] != sample.target_value_bp:
                raise ValueError("label_original_b13_path_value_mismatch")
            if mature and key[2] == policy.monitored_method_id:
                mature_ids.add(sample_id)
                mature_keys.add(key[:2])
                state = "mature_synthetic"
        denominators.append({"symbol": key[0], "decision_date": key[1], "method_id": key[2], "state": state,
                             "source_state": row.get("member_state"), "sample_id": sample_id})
    if seen != expected:
        raise ValueError("label_full_method_date_denominator_missing")
    denominators.sort(key=lambda d: (str(d["decision_date"]), str(d["symbol"]), str(d["method_id"])))
    if len(mature_keys) < policy.min_mature_samples:
        return _decision("waiting", ("insufficient_cutoff_mature_samples",), policy, evidence_sha, len(mature_keys), denominators, cutoff)
    common = cast(dict[str, object], fair["common_cohort"])
    common_ids = cast(list[str], common["sample_ids"])
    if (set(common_ids) != mature_ids or len(common_ids) != len(mature_ids)
            or type(common["count"]) is not int or common["count"] != len(mature_ids)):
        raise ValueError("fair_common_cohort_not_exact_cutoff_mature")
    ledger = cast(list[dict[str, object]], fair["member_ledger"])
    ledger_ids = {str(row["sample_id"]) for row in ledger}
    expected_ledger = {sample_id for sample_id, row in row_by_id.items() if row["method_id"] == policy.monitored_method_id}
    if len(ledger_ids) != len(ledger) or ledger_ids != expected_ledger:
        raise ValueError("fair_member_full_denominator_missing")
    for row in ledger:
        if row.get("included_in_common_cohort") is not (str(row["sample_id"]) in mature_ids):
            raise ValueError("fair_member_maturity_mismatch")
        label = row_by_id[str(row["sample_id"])]
        for label_field, ledger_field in (("stock_code", "stock_code"), ("decision_date", "decision_date"),
                                          ("method_id", "method_id"), ("horizon", "horizon"), ("measure", "measure"),
                                          ("value_bp", "label_value_bp"), ("label_end_date", "label_end_date"),
                                          ("available_date", "available_date"), ("availability_status", "availability_status")):
            if row.get(ledger_field) != label.get(label_field):
                raise ValueError("fair_member_original_label_mismatch")
        if str(row["sample_id"]) not in mature_ids:
            continue
        item = predictions[(str(label["stock_code"]), str(label["decision_date"]))]
        original = json.loads(cast(bytes, item.result.result_payload))["prediction"]
        pin = cast(dict[str, object], row["candidate_prediction"])
        for name, expected_value in {"prediction_id": original["prediction_id"], "model_id": item.result.model_id,
                                     "dataset_id": item.result.dataset_id, "symbol": original["symbol"],
                                     "decision_date": label["decision_date"], "return_prediction_bp": original["return_prediction_bp"],
                                     "ranking_score": original["ranking_score_bp"],
                                     "downside_probability": original["downside_probability_bp"],
                                     "uncertainty_bp": original["uncertainty_bp"],
                                     "available_date": item.prediction_available_at.astimezone(ZoneInfo(item.decision_timezone)).date().isoformat()}.items():
            if pin.get(name) != expected_value:
                raise ValueError("fair_candidate_original_prediction_mismatch")
    candidate = cast(dict[str, object], fair["candidate"])
    model_pin = cast(dict[str, object], candidate["model_pin"])
    if model_pin.get("model_id") != policy.model_identity.model_id or model_pin.get("dataset_id") != frozen[0].result.dataset_id:
        raise ValueError("fair_model_dataset_mismatch")
    artifact_sha = next(pin.content_sha256 for pin in frozen[0].prepared.evidence.pins if pin.role == "model_artifact")
    if str(model_pin.get("artifact_hash")).removeprefix("sha256:") != artifact_sha[7:]:
        raise ValueError("fair_model_artifact_mismatch")
    mae = cast(dict[str, object], candidate["metrics"]).get("mae_bp")
    if type(mae) is not int or mae < 0:
        raise ValueError("fair_mae_integer_required")
    context.check()
    return _decision("review_required" if mae > policy.max_mae_bp else "stable", (), policy, evidence_sha,
                     len(mature_keys), denominators, cutoff)


def apply_monitoring_control(decision: ShadowMonitoringDecision, frozen: tuple[FrozenShadowEvidence, ...], *,
                             policy: ShadowMonitoringPolicy, cutoff: datetime, source_port: ReadonlyResearchPort,
                             custody: ShadowEvidenceCustody, context: ControlContext,
                             command: ShadowControlCommand, proof: ControlApprovalProof | None,
                             control_service: ShadowControlService, execute: bool = False) -> ShadowControlResult:
    verified = evaluate_shadow_monitoring(frozen, policy=policy, cutoff=cutoff, source_port=source_port,
                                          custody=custody, context=context)
    if (decision != verified or decision.status != "review_required" or command.identity != decision.model_identity
            or command.issued_at < aware(cutoff)):
        return ShadowControlResult("rejected", command.identity_sha256, ("monitoring_control_binding_mismatch",))
    monitoring = [p for p in command.source_pins if p.role == "monitoring"]
    predictions = [p for p in command.source_pins if p.role == "prediction" or p.role.startswith("prediction:")]
    if (len(monitoring) != 1 or monitoring[0].content != decision.report_payload
            or len(predictions) != len(frozen)
            or sorted(p.content for p in predictions) != sorted(cast(bytes, f.result.result_payload) for f in frozen)):
        return ShadowControlResult("rejected", command.identity_sha256, ("control_original_evidence_pins_required",))
    context.check()
    return control_service.apply(command, proof=proof, execute=execute, cancel=context.cancel)
