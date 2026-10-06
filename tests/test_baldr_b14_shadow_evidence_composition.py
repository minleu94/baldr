"""合成 B13 原結果→封存→唯讀成熟／監測→原 B14 control port。"""

from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
from typing import Any, Literal, cast

import pytest

from app_module.rule_research_model_input_adapter import (
    ModelInputFairDenominatorRow, ModelInputPathBar, ModelInputPolicy, ModelInputRunnerResult,
    ModelInputSample, ModelInputTimeSplit, PreparedModelInput, TrainingPreprocessingAudit,
    build_synthetic_offline_evidence, canonical_model_input_bytes, content_sha256,
    prepare_model_input, run_prepared_model_input, source_pins_sha256,
)
from app_module.rule_research_shadow_control import (
    ControlApprovalProof, ControlContext, ControlSourcePin, RuleRoute, ShadowControlCommand,
    ShadowControlIdentity, ShadowControlService, canonical, digest,
)
from app_module.rule_research_shadow_control_store import SyntheticShadowControlPort
from app_module.rule_research_shadow_evidence_composition import (
    FrozenShadowEvidence, ReadonlyResearchEvidence, ShadowMonitoringPolicy,
    apply_monitoring_control, evaluate_shadow_monitoring, freeze_shadow_evidence,
)
from app_module.rule_research_shadow_evidence_store import ShadowEvidenceStore

pytest_plugins = ["tests.test_rule_research_forward_isolated"]


NOW = datetime(2025, 1, 10, 12, tzinfo=timezone.utc)
CUTOFF = NOW + timedelta(hours=4)
MONITOR = datetime(2025, 1, 16, 12, tzinfo=timezone.utc)
IDENTITY = ShadowControlIdentity("synthetic-model", "r7")
RULE_BYTES = b'{"caller_approved_rule":"r3"}'
RULE = RuleRoute("caller-rule", "r3", digest(RULE_BYTES))


class Custody:
    def __init__(self) -> None:
        self.frozen: set[str] = set()
        self.research: set[str] = set()
        self.evidence_witness: tuple[int, str | None] = (0, None)
        self.control_witness: tuple[int, str | None] = (0, None)
        self.proofs: set[str] = set()

    def verify_frozen(self, binding_sha256: str) -> bool:
        return binding_sha256 in self.frozen

    def verify_research(self, binding_sha256: str) -> bool:
        return binding_sha256 in self.research

    def current_evidence_revision(self, namespace: str) -> tuple[int, str | None]:
        assert namespace == "synthetic://freeze"
        return self.evidence_witness

    def reserve_evidence_revision(self, namespace: str, expected_revision: int, receipt_sha256: str) -> bool:
        if self.current_evidence_revision(namespace)[0] != expected_revision:
            return False
        self.evidence_witness = (expected_revision + 1, receipt_sha256)
        return True

    def verify(self, command: ShadowControlCommand, proof: ControlApprovalProof) -> bool:
        return proof.identity_sha256 in self.proofs and proof.command_sha256 == command.identity_sha256

    def current_revision(self, namespace: str, identity: ShadowControlIdentity) -> tuple[int, str | None]:
        assert namespace == "synthetic://control" and identity == IDENTITY
        return self.control_witness

    def reserve_stop_revision(self, namespace: str, command: ShadowControlCommand, proof: ControlApprovalProof) -> bool:
        if not self.verify(command, proof) or self.current_revision(namespace, command.identity) != (0, None):
            return False
        self.control_witness = (1, command.identity_sha256)
        return True


def context(now: datetime = NOW, cancel: Event | None = None) -> ControlContext:
    return ControlContext(now + timedelta(hours=1), lambda: now, cancel if cancel is not None else Event())


def prepared() -> PreparedModelInput:
    policy = ModelInputPolicy("endpoint_gross_return_bp", 5,
                              ModelInputTimeSplit("2025-01-01", "2025-01-01", "2025-01-10", "2025-01-10",
                                                  "2025-01-08", "2025-01-16", 2, 1),
                              "gross-no-cost:v1", "none:gross-no-excess", "raw_ohlc_no_corporate_action",
                              "b13-endpoint-gross-v1", "gross_return_bp")
    schema = (("synthetic-feature", "int", "bp"),)
    registry = digest(b"synthetic-feature-registry")
    schema_sha = digest(canonical({"registry_hash": registry, "canonical_schema": [list(s) for s in schema]}))
    rows = []
    for phase, day, step, end, available in (("training", 1, 1, 6, 7), ("evaluation", 10, 2, 15, 16)):
        start = date(2025, 1, day)
        days = tuple((start + timedelta(days=i)).isoformat() for i in range(6))
        path = tuple(ModelInputPathBar(d, Decimal(100 + i * step), Decimal(100 + i * step),
                                       Decimal(100 + i * step), Decimal(100 + i * step), d, "available", "none")
                     for i, d in enumerate(days))
        rows.append(ModelInputSample(phase + "-2330", "2330", cast(Literal["training", "evaluation"], phase), start.isoformat(),
                                     (start - timedelta(days=1)).isoformat(), (start - timedelta(days=1)).isoformat(),
                                     (("synthetic-feature", 7),), days, path, 500 * step,
                                     date(2025, 1, end).isoformat(), date(2025, 1, available).isoformat()))  # type: ignore[arg-type]
    denominator = tuple(ModelInputFairDenominatorRow(r.symbol, r.decision_date, method, "represented", r.row_id, None)
                        for r in rows for method in ("rule", "candidate")) + tuple(
        ModelInputFairDenominatorRow("2331", "2025-01-10", method, "missing", None, "source_missing")
        for method in ("rule", "candidate"))
    audit = TrainingPreprocessingAudit(("training-2330",), "2024-12-31", "2025-01-08")
    evidence = build_synthetic_offline_evidence(policy, rows, fair_denominator=denominator, preprocessing_audit=audit,
                                               dataset_id="synthetic-dataset", model_id=IDENTITY.model_id,
                                               run_id="synthetic-run", source_id="synthetic-source",
                                               feature_registry_sha256=registry, feature_schema_sha256=schema_sha,
                                               feature_schema=schema,
                                               actual_session_calendar=tuple(date(2025, 1, i).isoformat() for i in range(1, 21)),
                                               model_artifact_bytes=b"synthetic opaque model bytes; never loaded")
    result = prepare_model_input(policy, rows, evidence, fair_denominator=denominator, preprocessing_audit=audit)
    assert result.status == "ready", result.blockers
    return result


class Runner:
    def run(self, p: PreparedModelInput) -> ModelInputRunnerResult:
        raw = json.dumps({"schema_version": "baldr-b13-runner-result.v1", "prepared_identity_sha256": p.identity_sha256,
                          "dataset_id": p.evidence.dataset_id, "model_id": p.evidence.model_id, "run_id": p.evidence.run_id,
                          "source_pins_sha256": source_pins_sha256(p.evidence.pins), "sample_row_id": "evaluation-2330",
                          "symbol": "2330", "decision_date": "2025-01-10", "status": "available", "blockers": [],
                          "prediction": {"prediction_id": "original-p1", "symbol": "2330", "return_prediction_bp": 17,
                                         "ranking_score_bp": 9, "downside_probability_bp": 23, "uncertainty_bp": 7}},
                         indent=2).encode("utf-8")
        return ModelInputRunnerResult("available", p.identity_sha256, p.evidence.dataset_id, p.evidence.model_id,
                                       p.evidence.run_id, source_pins_sha256(p.evidence.pins), digest(raw), raw)


def frozen_fixture() -> tuple[FrozenShadowEvidence, Custody]:
    p = prepared()
    result = run_prepared_model_input(p, runner=Runner())
    assert result.status == "available", result.blockers
    custody = Custody()
    declared = FrozenShadowEvidence(p, result, IDENTITY, "candidate", NOW - timedelta(minutes=1), CUTOFF, "UTC", NOW)
    custody.frozen.add(declared.binding_sha256)
    frozen = freeze_shadow_evidence(p, result, model_identity=IDENTITY, method_id="candidate",
                                    prediction_available_at=declared.prediction_available_at, decision_cutoff=CUTOFF,
                                    decision_timezone="UTC", context=context(), custody=custody)
    return frozen, custody


def seal(report: dict[str, Any]) -> bytes:
    report = dict(report)
    report.pop("report_identity_sha256", None)
    report["report_identity_sha256"] = digest(canonical(report))
    return json.dumps(report, indent=2).encode("utf-8")


class ReadonlyPort:
    def __init__(self, evidence: ReadonlyResearchEvidence) -> None:
        self.evidence = evidence
        self.reads = 0

    def read(self, frozen: tuple[FrozenShadowEvidence, ...], policy: ShadowMonitoringPolicy,
             cutoff: datetime, ctx: ControlContext) -> ReadonlyResearchEvidence:
        self.reads += 1
        return self.evidence


def reports(frozen: FrozenShadowEvidence, custody: Custody, *, mae: int = 983) -> tuple[ShadowMonitoringPolicy, ReadonlyPort]:
    # 明示 synthetic readonly wrapper 原輸出；沒有自然／PIT／正式核准效力。
    flags = {"formal_eligible": False, "training_eligible": False, "historical_pit_eligible": False,
             "natural_authority": False, "execution_eligible": False}
    rows = [{"sample_id": symbol + "-" + method, "stock_code": symbol, "decision_date": "2025-01-10",
             "method_id": method, "horizon": "H5", "measure": "gross", "member_state": "matched" if symbol == "2330" else "unknown",
             "value_bp": 1000 if symbol == "2330" else None, "available_date": "2025-01-16",
             "label_end_date": "2025-01-15", "availability_status": "known_research_only",
             "split_role": "evaluation_window_research_only"} for symbol in ("2330", "2331") for method in ("rule", "candidate")]
    label_sha, split_sha = digest(b"caller-gross-H5-policy"), digest(b"caller-fixed-split")
    label = seal({"schema_version": "rule-research-label-readiness.v1", "status": "research_only", **flags,
                  "label_policy": {"sha256": label_sha}, "split_policy": {"sha256": split_sha}, "label_rows": rows})
    raw = json.loads(frozen.result.result_payload or b"{}")
    prediction = raw["prediction"]
    pin = {"prediction_id": prediction["prediction_id"], "model_id": frozen.result.model_id,
           "dataset_id": frozen.result.dataset_id, "symbol": "2330", "decision_date": "2025-01-10",
           "return_prediction_bp": prediction["return_prediction_bp"], "ranking_score": prediction["ranking_score_bp"],
           "downside_probability": prediction["downside_probability_bp"], "uncertainty_bp": prediction["uncertainty_bp"],
           "available_date": frozen.prediction_available_at.date().isoformat()}
    fair = seal({"schema_version": "rule-research-fair-comparison.v1", "status": "research_only_comparison", **flags,
                 "label_readiness_identity_sha256": json.loads(label)["report_identity_sha256"], "method_id": "candidate",
                 "horizon": 5, "measure": "gross", "metrics_policy": "return_only",
                 "label_policy_sha256": label_sha, "split_policy_sha256": split_sha,
                 "common_cohort": {"sample_ids": ["2330-candidate"], "count": 1},
                 "member_ledger": [{**next(r for r in rows if r["sample_id"] == "2330-candidate"), "label_value_bp": 1000,
                                    "included_in_common_cohort": True, "candidate_prediction": pin},
                                   {**next(r for r in rows if r["sample_id"] == "2331-candidate"), "label_value_bp": None,
                                    "included_in_common_cohort": False, "candidate_prediction": None}],
                 "candidate": {"model_pin": {"model_id": frozen.result.model_id, "dataset_id": frozen.result.dataset_id,
                                              "artifact_hash": next(p.content_sha256 for p in frozen.prepared.evidence.pins if p.role == "model_artifact")},
                               "metrics": {"mae_bp": mae}}})
    policy = ShadowMonitoringPolicy("caller-monitor", "v1", IDENTITY,
                                     content_sha256(canonical_model_input_bytes(frozen.prepared.policy)),
                                     ("rule", "candidate"), "candidate", 1, 100, label_sha, split_sha)
    evidence = ReadonlyResearchEvidence(label, fair, (
        ControlSourcePin("label_report", "original-label-wrapper", label, digest(label)),
        ControlSourcePin("fair_report", "original-fair-wrapper", fair, digest(fair))), MONITOR - timedelta(minutes=1))
    custody.research.add(evidence.binding_sha256((frozen,), policy, MONITOR))
    return policy, ReadonlyPort(evidence)


def approve_control(custody: Custody, command: ShadowControlCommand) -> ControlApprovalProof:
    proof = ControlApprovalProof("independent-caller-control", command.identity_sha256, command.source_pins_sha256,
                                 MONITOR - timedelta(seconds=1), MONITOR + timedelta(hours=1))
    custody.proofs.add(proof.identity_sha256)
    return proof


def test_full_freeze_maturity_monitor_default_preview_control_fresh_process(tmp_path: Path) -> None:
    frozen, custody = frozen_fixture()
    source = tmp_path / "original-result.json"
    source.write_bytes(frozen.result.result_payload or b"")
    original = source.read_bytes(), source.stat().st_mtime_ns
    store = ShadowEvidenceStore.create(root=tmp_path / "freeze", namespace="synthetic://freeze", custody=custody, context=context())
    assert store.append(frozen, expected_revision=0, context=context()) == 0
    assert store.read_all() == ()
    assert store.append(frozen, expected_revision=0, context=context(), execute=True) == 1
    assert store.read_all()[0].result.result_payload == original[0]
    policy, readonly = reports(frozen, custody)
    decision = evaluate_shadow_monitoring(store.read_all(), policy=policy, cutoff=MONITOR, source_port=readonly,
                                          custody=custody, context=context(MONITOR))
    assert decision.status == "review_required" and decision.mature_count == 1 and decision.full_denominator_count == 4
    assert decision.production_action_allowed is False
    command = ShadowControlCommand("caller-approved-stop", "stop_restore_rule", IDENTITY, 0, RULE, MONITOR,
                                    MONITOR + timedelta(minutes=30), (
        ControlSourcePin("last_rule", "caller-approved-r3", RULE_BYTES, digest(RULE_BYTES)),
        ControlSourcePin("monitoring", "exact-monitor", decision.report_payload, decision.identity_sha256),
        ControlSourcePin("prediction", "original-result", original[0], digest(original[0]))))
    proof = approve_control(custody, command)
    port = SyntheticShadowControlPort.create(root=tmp_path / "control", namespace="synthetic://control", command=command,
                                             proof=proof, verifier=custody, context=context(MONITOR))
    service = ShadowControlService(port=port, verifier=custody, clock=lambda: MONITOR)
    calls: list[str] = []
    def model(raw: bytes) -> bytes:
        calls.append("model")
        return raw
    def rule(route: RuleRoute, artifact: bytes, raw: bytes) -> bytes:
        assert route == RULE and artifact == RULE_BYTES
        calls.append("rule")
        return raw
    port.dispatch(IDENTITY, b"q", model_runner=model, rule_runner=rule)
    kwargs: dict[str, Any] = dict(policy=policy, cutoff=MONITOR, source_port=readonly, custody=custody, context=context(MONITOR),
                  command=command, proof=proof, control_service=service)
    assert apply_monitoring_control(decision, (frozen,), **kwargs).status == "preview"
    assert port.readback(IDENTITY).revision == 0
    assert apply_monitoring_control(decision, (frozen,), execute=True, **kwargs).status == "completed"
    port.dispatch(IDENTITY, b"q", model_runner=model, rule_runner=rule)
    assert calls == ["model", "rule"]
    caller_file = tmp_path / "independent-caller.json"
    label_file, fair_file = tmp_path / "original-label-report.json", tmp_path / "original-fair-report.json"
    label_file.write_bytes(readonly.evidence.label_report or b"")
    fair_file.write_bytes(readonly.evidence.fair_report or b"")
    caller_file.write_text(json.dumps({"frozen": list(custody.frozen), "evidence": custody.evidence_witness,
                                      "proofs": list(custody.proofs), "control": custody.control_witness,
                                      "research": list(custody.research), "policy": asdict(policy),
                                      "cutoff": MONITOR.isoformat(), "available_at": (MONITOR - timedelta(minutes=1)).isoformat(),
                                      "monitoring_identity": decision.identity_sha256}), encoding="utf-8")
    script = '''
import json,sys
from pathlib import Path
from app_module.rule_research_shadow_evidence_store import ShadowEvidenceStore
from app_module.rule_research_shadow_control import ShadowControlIdentity,digest
from app_module.rule_research_shadow_control_store import SyntheticShadowControlPort
from app_module.rule_research_shadow_control import ControlContext,ControlSourcePin
from app_module.rule_research_shadow_evidence_composition import ShadowMonitoringPolicy,ReadonlyResearchEvidence,evaluate_shadow_monitoring
from datetime import datetime
from threading import Event
saved=json.loads(Path(sys.argv[3]).read_text())
class Custody:
 def verify_frozen(self,b): return b in saved['frozen']
 def current_evidence_revision(self,n): return tuple(saved['evidence'])
 def verify(self,c,p): return p.identity_sha256 in saved['proofs'] and p.command_sha256==c.identity_sha256
 def current_revision(self,n,i): return tuple(saved['control'])
 def verify_research(self,b): return b in saved['research']
c=Custody()
f=ShadowEvidenceStore(root=Path(sys.argv[1]),namespace='synthetic://freeze',custody=c).read_all()[0]
assert f.result.result_payload==Path(sys.argv[4]).read_bytes()
policy_data=saved['policy']
policy_data['model_identity']=ShadowControlIdentity(**policy_data['model_identity'])
policy=ShadowMonitoringPolicy(**policy_data)
labels,fair=Path(sys.argv[5]).read_bytes(),Path(sys.argv[6]).read_bytes()
e=ReadonlyResearchEvidence(labels,fair,(ControlSourcePin('label_report','original-label-wrapper',labels,digest(labels)),ControlSourcePin('fair_report','original-fair-wrapper',fair,digest(fair))),datetime.fromisoformat(saved['available_at']))
class Source:
 def read(self,f,p,cutoff,ctx): return e
cutoff=datetime.fromisoformat(saved['cutoff'])
ctx=ControlContext(cutoff.replace(hour=13),lambda:cutoff,Event())
decision=evaluate_shadow_monitoring((f,),policy=policy,cutoff=cutoff,source_port=Source(),custody=c,context=ctx)
assert decision.identity_sha256==saved['monitoring_identity'] and decision.status=='review_required'
port=SyntheticShadowControlPort(root=Path(sys.argv[2]),namespace='synthetic://control',verifier=c)
i=ShadowControlIdentity('synthetic-model','r7')
def model(q): raise AssertionError('stopped model called')
def rule(r,a,q):
 assert r.artifact_sha256==digest(a)
 return q
assert port.dispatch(i,b'fresh',model_runner=model,rule_runner=rule)==b'fresh'
print(json.dumps({'result_hash':f.result.result_identity_sha256,'status':port.readback(i).status,'rulehash':port.readback(i).rule.artifact_sha256}))
'''
    run = subprocess.run([sys.executable, "-B", "-c", script, str(store.root), str(port.root), str(caller_file), str(source), str(label_file), str(fair_file)],
                         cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert run.returncode == 0, run.stderr
    (tmp_path / "freshprocess.stdout.json").write_text(run.stdout, encoding="utf-8")
    (tmp_path / "source-byte-hashes.json").write_bytes(canonical({
        "fixture_kind": "explicit synthetic known clocks; not original-wrapper availability",
        "original_result": digest(original[0]), "label_report": digest(label_file.read_bytes()),
        "fair_report": digest(fair_file.read_bytes()), "rule_artifact": digest(RULE_BYTES),
        "b13_original_pins": {pin.role: pin.content_sha256 for pin in frozen.prepared.evidence.pins}}))
    assert json.loads(run.stdout) == {"result_hash": frozen.result.result_identity_sha256, "status": "stopped_rule", "rulehash": RULE.artifact_sha256}
    assert (source.read_bytes(), source.stat().st_mtime_ns) == original


@pytest.mark.parametrize("case", ["late", "wrong_result", "wrong_model", "wrong_method", "no_custody", "forged_prepared", "naive"])
def test_freeze_negative_preserves_original_bytes(case: str) -> None:
    frozen, custody = frozen_fixture()
    raw = frozen.result.result_payload
    p, result, identity, method, available, cutoff = frozen.prepared, frozen.result, IDENTITY, "candidate", frozen.prediction_available_at, CUTOFF
    if case == "late": cutoff = NOW - timedelta(seconds=1)
    elif case == "wrong_result": result = replace(result, result_identity_sha256=digest(b"wrong"))
    elif case == "wrong_model": identity = ShadowControlIdentity("other-model", "r7")
    elif case == "wrong_method": method = "unknown"
    elif case == "no_custody": custody.frozen.clear()
    elif case == "forged_prepared": p = replace(p, _seal="forged")
    elif case == "naive": available = available.replace(tzinfo=None)
    with pytest.raises(ValueError):
        freeze_shadow_evidence(p, result, model_identity=identity, method_id=method,
                               prediction_available_at=available, decision_cutoff=cutoff, decision_timezone="UTC",
                               context=context(), custody=custody)
    assert frozen.result.result_payload == raw


@pytest.mark.parametrize("case", ["no_policy", "no_source", "source_clock", "source_late", "label_future", "availability_unknown", "too_few"])
def test_monitor_waiting_never_produces_control(case: str) -> None:
    frozen, custody = frozen_fixture()
    policy, port = reports(frozen, custody)
    selected: ShadowMonitoringPolicy | None = policy
    source: ReadonlyPort | None = port
    if case == "no_policy": selected = None
    elif case == "no_source": source = None
    elif case == "source_clock": port.evidence = replace(port.evidence, available_at=None)
    elif case == "source_late": port.evidence = replace(port.evidence, available_at=MONITOR + timedelta(seconds=1))
    elif case == "too_few": selected = replace(policy, min_mature_samples=2)
    else:
        label = json.loads(port.evidence.label_report or b"{}")
        for row in label["label_rows"]:
            if case == "label_future": row["available_date"] = "2025-01-17"
            else: row["availability_status"] = "unknown"
        update_label(port, label)
    if selected is not None:
        custody.research.add(port.evidence.binding_sha256((frozen,), selected, MONITOR))
    result = evaluate_shadow_monitoring((frozen,), policy=selected, cutoff=MONITOR, source_port=source, custody=custody, context=context(MONITOR))
    assert result.status == "waiting" and result.production_action_allowed is False


def update_label(port: ReadonlyPort, label: dict[str, Any]) -> None:
    raw = seal(label)
    pins = tuple(ControlSourcePin(p.role, p.source_id, raw, digest(raw)) if p.role == "label_report" else p for p in port.evidence.source_pins)
    fair = json.loads(port.evidence.fair_report or b"{}")
    fair["label_readiness_identity_sha256"] = json.loads(raw)["report_identity_sha256"]
    fair_raw = seal(fair)
    pins = tuple(ControlSourcePin(p.role, p.source_id, fair_raw, digest(fair_raw)) if p.role == "fair_report" else p for p in pins)
    port.evidence = replace(port.evidence, label_report=raw, fair_report=fair_raw, source_pins=pins)


@pytest.mark.parametrize("case", ["label_duplicate", "label_missing", "wrong_horizon", "wrong_label", "wrong_target", "wrong_model", "wrong_prediction", "future_common", "missing_ledger", "float_metric", "self_custody"])
def test_monitor_mismatch_rejected(case: str) -> None:
    frozen, custody = frozen_fixture()
    policy, port = reports(frozen, custody)
    if case in ("label_duplicate", "label_missing", "wrong_horizon", "wrong_label"):
        label = json.loads(port.evidence.label_report or b"{}")
        if case == "label_duplicate": label["label_rows"].append(label["label_rows"][0])
        elif case == "label_missing": label["label_rows"].pop()
        elif case == "wrong_horizon": label["label_rows"][0]["horizon"] = "H20"
        else: label["label_rows"][0]["value_bp"] = 0
        update_label(port, label)
    elif case == "wrong_target": policy = replace(policy, target_policy_sha256=digest(b"other-target"))
    elif case == "wrong_model": policy = replace(policy, model_identity=ShadowControlIdentity("other", "r7"))
    elif case == "self_custody": custody.research.clear()
    else:
        fair = json.loads(port.evidence.fair_report or b"{}")
        if case == "wrong_prediction": fair["member_ledger"][0]["candidate_prediction"]["return_prediction_bp"] = 999
        elif case == "future_common": fair["common_cohort"] = {"sample_ids": ["2331-candidate"], "count": 1}
        elif case == "missing_ledger": fair["member_ledger"].pop()
        elif case == "float_metric": fair["candidate"]["metrics"]["mae_bp"] = "983.0"
        raw = seal(fair)
        port.evidence = replace(port.evidence, fair_report=raw, source_pins=tuple(
            ControlSourcePin(p.role, p.source_id, raw, digest(raw)) if p.role == "fair_report" else p for p in port.evidence.source_pins))
    if case != "self_custody": custody.research.add(port.evidence.binding_sha256((frozen,), policy, MONITOR))
    with pytest.raises(ValueError):
        evaluate_shadow_monitoring((frozen,), policy=policy, cutoff=MONITOR, source_port=port, custody=custody, context=context(MONITOR))


def test_stable_duplicate_and_cancel() -> None:
    frozen, custody = frozen_fixture()
    policy, port = reports(frozen, custody)
    policy = replace(policy, max_mae_bp=1000)
    custody.research.add(port.evidence.binding_sha256((frozen,), policy, MONITOR))
    assert evaluate_shadow_monitoring((frozen,), policy=policy, cutoff=MONITOR, source_port=port, custody=custody, context=context(MONITOR)).status == "stable"
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_shadow_monitoring((frozen, frozen), policy=policy, cutoff=MONITOR, source_port=port, custody=custody, context=context(MONITOR))
    cancel = Event()
    cancel.set()
    with pytest.raises(ValueError, match="cancelled"):
        evaluate_shadow_monitoring((frozen,), policy=policy, cutoff=MONITOR, source_port=port, custody=custody, context=context(MONITOR, cancel))


@pytest.mark.parametrize("case", ["duplicate", "stale", "late", "cancel", "truncate", "corrupt"])
def test_store_failures(case: str, tmp_path: Path) -> None:
    frozen, custody = frozen_fixture()
    store = ShadowEvidenceStore.create(root=tmp_path / "freeze", namespace="synthetic://freeze", custody=custody, context=context())
    if case in ("duplicate", "stale", "truncate", "corrupt"):
        store.append(frozen, expected_revision=0, context=context(), execute=True)
    original = {p.name: p.read_bytes() for p in store.root.iterdir()}
    if case == "truncate":
        (store.root / "freeze-000001.json").unlink()
        with pytest.raises(ValueError, match="witness"): store.read_all()
    elif case == "corrupt":
        (store.root / "freeze-000001.json").write_bytes(b"{}")
        with pytest.raises((ValueError, KeyError)): store.read_all()
    else:
        cancel = Event()
        if case == "cancel": cancel.set()
        ctx = context(CUTOFF + timedelta(seconds=1) if case == "late" else NOW, cancel)
        with pytest.raises(ValueError):
            store.append(frozen, expected_revision=1 if case == "duplicate" else 0, context=ctx, execute=True)
        assert {p.name: p.read_bytes() for p in store.root.iterdir()} == original


def test_existing_readonly_wrappers_missing_policy_stays_waiting(pipeline: Any) -> None:
    from app_module.rule_research_label_readiness import build_label_readiness_batch
    from app_module.rule_research_fair_comparison import build_fair_comparison
    from app_module.rule_research_forward_store import run_forward_isolated
    _args, parent_value, _config, runtime, *_rest = pipeline
    saved = run_forward_isolated(runtime, execute=True)
    assert saved["status"] == "saved", saved
    parent, outcome = Path(parent_value), Path(saved["receipt_path"])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (parent, outcome)}
    frozen, custody = frozen_fixture()
    policy, _unused = reports(frozen, custody)
    labels = canonical(build_label_readiness_batch(((parent, outcome),), None, None))
    fair = canonical(build_fair_comparison(((parent, outcome),), None, None))
    original = ReadonlyResearchEvidence(labels, fair, (
        ControlSourcePin("label_report", "original-readonly-wrapper", labels, digest(labels)),
        ControlSourcePin("fair_report", "original-readonly-wrapper", fair, digest(fair))), MONITOR)
    custody.research.add(original.binding_sha256((frozen,), policy, MONITOR))
    port = ReadonlyPort(original)
    decision = evaluate_shadow_monitoring((frozen,), policy=policy, cutoff=MONITOR, source_port=port,
                                          custody=custody, context=context(MONITOR))
    assert decision.status == "waiting" and decision.blockers == ("readonly_reports_not_ready",)
    assert port.reads == 1
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (parent, outcome)} == before


@pytest.mark.parametrize("case", ["cancel", "timeout"])
def test_freeze_fsync_late_cancel_has_no_published_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    frozen, custody = frozen_fixture()
    store = ShadowEvidenceStore.create(root=tmp_path / "freeze", namespace="synthetic://freeze", custody=custody, context=context())
    cancel, clock = Event(), [NOW]
    ctx = ControlContext(NOW + timedelta(minutes=1), lambda: clock[0], cancel)
    original = os.fsync
    def slow_fsync(fd: int) -> None:
        original(fd)
        if case == "cancel": cancel.set()
        else: clock[0] = ctx.deadline
    monkeypatch.setattr(os, "fsync", slow_fsync)
    with pytest.raises(ValueError, match="cancelled|timeout"):
        store.append(frozen, expected_revision=0, context=ctx, execute=True)
    assert store.read_all() == () and custody.evidence_witness == (0, None)


def test_monitor_future_cutoff_rejected() -> None:
    frozen, custody = frozen_fixture()
    policy, port = reports(frozen, custody)
    with pytest.raises(ValueError, match="cutoff_in_future"):
        evaluate_shadow_monitoring((frozen,), policy=policy, cutoff=MONITOR + timedelta(days=1), source_port=port,
                                    custody=custody, context=context(MONITOR))


@pytest.mark.parametrize("case", ["proof_missing", "wrong_command_model", "forged_decision", "wrong_monitor_pin", "wrong_prediction_pin", "control_clock"])
def test_composition_control_negative_never_stops(case: str, tmp_path: Path) -> None:
    frozen, custody = frozen_fixture()
    policy, source = reports(frozen, custody)
    decision = evaluate_shadow_monitoring((frozen,), policy=policy, cutoff=MONITOR, source_port=source,
                                          custody=custody, context=context(MONITOR))
    command = ShadowControlCommand("stop", "stop_restore_rule", IDENTITY, 0, RULE, MONITOR,
                                    MONITOR + timedelta(minutes=10), (
        ControlSourcePin("last_rule", "original-rule", RULE_BYTES, digest(RULE_BYTES)),
        ControlSourcePin("monitoring", "monitor", decision.report_payload, decision.identity_sha256),
        ControlSourcePin("prediction", "original-result", frozen.result.result_payload or b"", frozen.result.result_identity_sha256 or "")))
    proof: ControlApprovalProof | None = approve_control(custody, command)
    assert proof is not None
    port = SyntheticShadowControlPort.create(root=tmp_path / "control", namespace="synthetic://control",
                                             command=command, proof=proof, verifier=custody, context=context(MONITOR))
    if case == "proof_missing": proof = None
    elif case == "wrong_command_model": command = replace(command, identity=ShadowControlIdentity("other", "r7"))
    elif case == "forged_decision": decision = replace(decision, mature_count=999)
    elif case == "control_clock": command = replace(command, issued_at=MONITOR - timedelta(seconds=1))
    else:
        role = "monitoring" if case == "wrong_monitor_pin" else "prediction"
        command = replace(command, source_pins=tuple(ControlSourcePin(p.role, p.source_id, b"wrong", digest(b"wrong"))
                                                     if p.role == role else p for p in command.source_pins))
    result = apply_monitoring_control(decision, (frozen,), policy=policy, cutoff=MONITOR, source_port=source, custody=custody,
                                      context=context(MONITOR), command=command, proof=proof,
                                      control_service=ShadowControlService(port=port, verifier=custody, clock=lambda: MONITOR), execute=True)
    assert result.status == "rejected" and port.readback(IDENTITY).revision == 0


@pytest.mark.parametrize("case", ["artifact", "ledger_label", "immature_ledger_label", "ranking", "duplicate_common", "horizon", "measure"])
def test_exact_original_fair_bindings(case: str) -> None:
    frozen, custody = frozen_fixture()
    policy, port = reports(frozen, custody)
    fair = json.loads(port.evidence.fair_report or b"{}")
    if case == "artifact": fair["candidate"]["model_pin"]["artifact_hash"] = digest(b"other-artifact")
    elif case == "ledger_label": fair["member_ledger"][0]["label_value_bp"] = 0
    elif case == "immature_ledger_label": fair["member_ledger"][1]["stock_code"] = "forged"
    elif case == "ranking": fair["member_ledger"][0]["candidate_prediction"]["ranking_score"] = 99
    elif case == "duplicate_common": fair["common_cohort"]["sample_ids"].append("2330-candidate")
    elif case == "horizon": fair["horizon"] = 20
    else: fair["measure"] = "net"
    raw = seal(fair)
    port.evidence = replace(port.evidence, fair_report=raw, source_pins=tuple(
        ControlSourcePin(p.role, p.source_id, raw, digest(raw)) if p.role == "fair_report" else p for p in port.evidence.source_pins))
    custody.research.add(port.evidence.binding_sha256((frozen,), policy, MONITOR))
    with pytest.raises(ValueError):
        evaluate_shadow_monitoring((frozen,), policy=policy, cutoff=MONITOR, source_port=port, custody=custody, context=context(MONITOR))


@pytest.mark.parametrize("case", ["cancel", "timeout"])
def test_freeze_post_cas_committed_truth(tmp_path: Path, case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen, custody = frozen_fixture()
    store = ShadowEvidenceStore.create(root=tmp_path / "freeze", namespace="synthetic://freeze", custody=custody, context=context())
    cancel, clock = Event(), [NOW]
    ctx = ControlContext(NOW + timedelta(minutes=1), lambda: clock[0], cancel)
    original = custody.reserve_evidence_revision
    def reserve(namespace: str, revision: int, receipt_sha: str) -> bool:
        accepted = original(namespace, revision, receipt_sha)
        if case == "cancel": cancel.set()
        else: clock[0] = ctx.deadline
        return accepted
    monkeypatch.setattr(custody, "reserve_evidence_revision", reserve)
    assert store.append(frozen, expected_revision=0, context=ctx, execute=True) == 1
    assert store.read_all() == (frozen,)


def test_original_positive_readonly_wrappers_keep_unknown_availability(pipeline: Any, tmp_path: Path) -> None:
    # Existing module fixture builds sealed synthetic source receipts and original
    # immutable prediction records. No replacement report dictionary is used.
    import importlib
    helpers = importlib.import_module("tests.test_rule_research_fair_comparison")
    from app_module.rule_research_label_readiness import build_label_readiness_batch
    from app_module.rule_research_fair_comparison import build_fair_comparison
    receipts, label_policy, split_policy, comparison_policy = helpers._prepared(pipeline)
    labels = build_label_readiness_batch(receipts, label_policy, split_policy)
    bundle = helpers._bundle_for(labels, comparison_policy)
    fair = build_fair_comparison(receipts, label_policy, split_policy, comparison_policy, bundle)
    assert labels["status"] == "research_only"
    assert fair["status"] == "research_only_comparison"
    assert fair["common_cohort"]["count"] == 2
    files = [path for pair in receipts for path in pair]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files}
    for index, (path, (raw, _mtime)) in enumerate(before.items()):
        (tmp_path / f"original-source-receipt-{index}.json").write_bytes(raw)
    # Original observed labels have unknown availability. Their positive research
    # metrics must never acquire maturity or control authority through this adapter.
    assert any(row["availability_status"] != "known_research_only" for row in labels["label_rows"])
    selected = next(row for row in labels["label_rows"] if row["method_id"] == comparison_policy["method_id"]
                    and row["member_state"] == "matched")
    decision_day = date.fromisoformat(selected["decision_date"])
    delta = decision_day - date(2025, 1, 10)
    template = prepared()
    def shifted(value: str) -> str:
        return (date.fromisoformat(value) + delta).isoformat()
    samples = tuple(replace(row, symbol=selected["stock_code"], decision_date=shifted(row.decision_date),
                            feature_as_of_date=shifted(row.feature_as_of_date), feature_available_date=shifted(row.feature_available_date),
                            actual_session_dates=tuple(shifted(day) for day in row.actual_session_dates),
                            path=tuple(replace(bar, trading_date=shifted(bar.trading_date), available_date=shifted(bar.available_date or "")) for bar in row.path),
                            horizon_end_date=shifted(row.horizon_end_date), label_available_date=shifted(row.label_available_date))
                    for row in template.samples)
    split = template.policy.split
    assert split is not None
    policy_input = replace(template.policy, split=replace(split, train_start_date=shifted(split.train_start_date), train_end_date=shifted(split.train_end_date),
                          evaluation_start_date=shifted(split.evaluation_start_date), evaluation_end_date=shifted(split.evaluation_end_date),
                          training_as_of_date=shifted(split.training_as_of_date), label_as_of_date=shifted(split.label_as_of_date)))
    symbols = {row["stock_code"] for row in labels["label_rows"]}
    methods = tuple(sorted({row["method_id"] for row in labels["label_rows"]}))
    denominator = tuple(ModelInputFairDenominatorRow(symbol, sample.decision_date, method,
                        "represented" if symbol == sample.symbol else "missing", sample.row_id if symbol == sample.symbol else None,
                        None if symbol == sample.symbol else "source_missing")
                        for sample in samples for symbol in sorted(symbols) for method in methods)
    assert template.preprocessing_audit is not None
    audit = replace(template.preprocessing_audit, max_available_date=shifted(template.preprocessing_audit.max_available_date or ""),
                    fit_cutoff_date=shifted(template.preprocessing_audit.fit_cutoff_date or ""))
    source = template.evidence
    evidence = build_synthetic_offline_evidence(policy_input, samples, fair_denominator=denominator, preprocessing_audit=audit,
        dataset_id=source.dataset_id, model_id=source.model_id, run_id=source.run_id, source_id="synthetic-original-wrapper-binding",
        feature_registry_sha256=source.feature_registry_sha256, feature_schema_sha256=source.feature_schema_sha256,
        feature_schema=source.feature_schema, actual_session_calendar=tuple(shifted(day) for day in source.actual_session_calendar),
        model_artifact_bytes=next(pin.content for pin in source.pins if pin.role == "model_artifact"))
    p = prepare_model_input(policy_input, samples, evidence, fair_denominator=denominator, preprocessing_audit=audit)
    assert p.status == "ready", p.blockers
    class OriginalReplayRunner:
        def run(self, prepared_input: PreparedModelInput) -> ModelInputRunnerResult:
            raw = json.loads(Runner().run(prepared_input).result_payload)
            raw.update(symbol=selected["stock_code"], decision_date=selected["decision_date"])
            raw["prediction"]["symbol"] = selected["stock_code"]
            payload = canonical(raw)
            return ModelInputRunnerResult("available", p.identity_sha256, p.evidence.dataset_id, p.evidence.model_id,
                                          p.evidence.run_id, source_pins_sha256(p.evidence.pins), digest(payload), payload)
    result = run_prepared_model_input(p, runner=OriginalReplayRunner())
    assert result.status == "available", result.blockers
    now = NOW + delta
    cutoff = MONITOR + delta
    custody = Custody()
    frozen = FrozenShadowEvidence(p, result, IDENTITY, comparison_policy["method_id"], now - timedelta(minutes=1),
                                  CUTOFF + delta, "UTC", now)
    custody.frozen.add(frozen.binding_sha256)
    monitor_policy = ShadowMonitoringPolicy("original-wrapper-monitor", "1", IDENTITY,
        content_sha256(canonical_model_input_bytes(policy_input)), methods, comparison_policy["method_id"], 1, 100,
        "sha256:" + labels["label_policy"]["sha256"], "sha256:" + labels["split_policy"]["sha256"])
    label_raw, fair_raw = canonical(labels), canonical(fair)
    (tmp_path / "original-module-label-report.json").write_bytes(label_raw)
    (tmp_path / "original-module-fair-report.json").write_bytes(fair_raw)
    (tmp_path / "source-byte-hashes.json").write_bytes(canonical({
        "fixture_kind": "actual readonly wrappers over original sealed synthetic receipts",
        "label_report": digest(label_raw), "fair_report": digest(fair_raw),
        "source_files": {str(path): digest(raw) for path, (raw, _mtime) in before.items()}}))
    readonly = ReadonlyResearchEvidence(label_raw, fair_raw, (
        ControlSourcePin("label_report", "original-label-module", label_raw, digest(label_raw)),
        ControlSourcePin("fair_report", "original-fair-module", fair_raw, digest(fair_raw))), cutoff)
    custody.research.add(readonly.binding_sha256((frozen,), monitor_policy, cutoff))
    decision = evaluate_shadow_monitoring((frozen,), policy=monitor_policy, cutoff=cutoff, source_port=ReadonlyPort(readonly),
                                         custody=custody, context=context(cutoff))
    assert decision.status == "waiting" and decision.mature_count == 0
    assert decision.full_denominator_count == len(labels["label_rows"])
    assert decision.production_action_allowed is False
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in files} == before
