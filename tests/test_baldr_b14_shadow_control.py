"""B14 純 control port 工程驗證，所有來源／核准／runner 皆隔離 synthetic。"""

from dataclasses import replace
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
from typing import Any, Callable

import pytest

from app_module.rule_research_shadow_control import (
    ControlApprovalProof, ControlContext, ControlSourcePin, RuleRoute,
    ShadowControlCommand, ShadowControlIdentity, ShadowControlService,
    ShadowControlState, digest,
)
from app_module.rule_research_shadow_control_store import SyntheticShadowControlPort


NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
IDENTITY = ShadowControlIdentity("synthetic-model", "exact-r7")
RULE_BYTES = b'{"rule":"caller-approved-fixed", "version":"r3"}'
PREDICTION_BYTES = b'{"prediction_id":"original-p1", "return_prediction_bp":17}'
ROUTE = RuleRoute("fixed-rule", "r3", digest(RULE_BYTES))


class CallerCustody:
    """caller 先保存的獨立核准清單，與 port 自己的 receipt 分 root。"""

    def __init__(self) -> None:
        self.records: dict[str, tuple[str, str, str]] = {}
        self.revision_witness: tuple[int, str | None] = (0, None)
        self.hook: Callable[[], None] = lambda: None

    def approve(self, command: ShadowControlCommand) -> ControlApprovalProof:
        proof = ControlApprovalProof("caller-approval-" + command.command_id, command.identity_sha256,
                                     command.source_pins_sha256, NOW - timedelta(seconds=1),
                                     NOW + timedelta(minutes=2))
        self.records[proof.custody_id] = (proof.command_sha256, proof.source_pins_sha256, proof.identity_sha256)
        return proof

    def verify(self, command: ShadowControlCommand, proof: ControlApprovalProof) -> bool:
        self.hook()
        return self.records.get(proof.custody_id) == (command.identity_sha256, command.source_pins_sha256, proof.identity_sha256)

    def current_revision(self, namespace: str, identity: ShadowControlIdentity) -> tuple[int, str | None]:
        assert namespace.startswith("synthetic://") and identity == IDENTITY
        return self.revision_witness

    def reserve_stop_revision(self, namespace: str, command: ShadowControlCommand,
                              proof: ControlApprovalProof) -> bool:
        if not self.verify(command, proof) or self.revision_witness != (command.expected_revision, None):
            return False
        self.revision_witness = (command.expected_revision + 1, command.identity_sha256)
        return True


def command(**changes: Any) -> ShadowControlCommand:
    base = ShadowControlCommand("stop-1", "stop_restore_rule", IDENTITY, 0, ROUTE, NOW,
                                NOW + timedelta(minutes=1), (
                                    ControlSourcePin("last_rule", "caller-rule-r3", RULE_BYTES, digest(RULE_BYTES)),
                                    ControlSourcePin("prediction", "caller-p1", PREDICTION_BYTES, digest(PREDICTION_BYTES)),
                                ))
    return replace(base, **changes)


def setup(tmp_path: Path) -> tuple[SyntheticShadowControlPort, CallerCustody, ShadowControlCommand, ControlApprovalProof]:
    cmd = command()
    custody = CallerCustody()
    proof = custody.approve(cmd)
    port = SyntheticShadowControlPort.create(root=tmp_path / "new-control", namespace="synthetic://b14",
                                             command=cmd, proof=proof, verifier=custody,
                                             context=ControlContext(cmd.deadline, lambda: NOW, Event()))
    return port, custody, cmd, proof


def snapshot(port: SyntheticShadowControlPort) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in port.root.iterdir()}


def test_actual_dispatch_stop_rule_and_fresh_process(tmp_path: Path) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    source = tmp_path / "source-rule.json"
    prediction = tmp_path / "source-prediction.json"
    source.write_bytes(RULE_BYTES)
    prediction.write_bytes(PREDICTION_BYTES)
    source_stats = [(p.read_bytes(), p.stat().st_mtime_ns) for p in (source, prediction)]
    calls: list[str] = []

    def model(raw: bytes) -> bytes:
        calls.append("model-r7")
        return b"synthetic-model-result:" + raw

    def rule(route: RuleRoute, artifact: bytes, raw: bytes) -> bytes:
        assert route == ROUTE and artifact == source.read_bytes()
        calls.append("rule-r3")
        return b"caller-rule-result:" + raw

    assert port.dispatch(IDENTITY, b"input", model_runner=model, rule_runner=rule).startswith(b"synthetic-model")
    original = snapshot(port)
    result = ShadowControlService(port=port, verifier=custody, clock=lambda: NOW).apply(cmd, proof=proof, execute=True)
    assert result.status == "completed" and result.production_action_allowed is False
    assert result.state is not None and result.state.revision == 1 and result.state.rule == ROUTE
    saved = json.loads((port.root / "receipt-000001.json").read_bytes())["payload"]["command"]["source_pins"]
    assert [base64.b64decode(p["content_b64"]) for p in saved] == [RULE_BYTES, PREDICTION_BYTES]
    assert snapshot(port)["receipt-000000.json"] == original["receipt-000000.json"]
    assert port.dispatch(IDENTITY, b"input", model_runner=model, rule_runner=rule) == b"caller-rule-result:input"
    assert calls == ["model-r7", "rule-r3"]
    custody_file = tmp_path / "independent-caller-custody.json"
    custody_file.write_text(json.dumps({"records": custody.records, "witness": custody.revision_witness}), encoding="utf-8")
    script = '''
import json, sys
from pathlib import Path
from app_module.rule_research_shadow_control import ShadowControlIdentity, digest
from app_module.rule_research_shadow_control_store import SyntheticShadowControlPort
custody=json.loads(Path(sys.argv[2]).read_text())
class Custody:
 def verify(self,c,p):
  return custody["records"].get(p.custody_id)==[c.identity_sha256,c.source_pins_sha256,p.identity_sha256]
 def current_revision(self,namespace,identity):
  assert namespace=="synthetic://b14" and identity==ShadowControlIdentity("synthetic-model","exact-r7")
  return tuple(custody["witness"])
 def reserve_stop_revision(self,namespace,c,p):
  raise AssertionError("fresh readback must not write custody")
port=SyntheticShadowControlPort(root=Path(sys.argv[1]),namespace="synthetic://b14",verifier=Custody())
identity=ShadowControlIdentity("synthetic-model","exact-r7")
def forbidden(raw):
 raise AssertionError("stopped model was called")
def rule(route,artifact,raw):
 assert route.artifact_sha256==digest(artifact)
 return b"fresh-rule:"+raw
assert port.dispatch(identity,b"fresh",model_runner=forbidden,rule_runner=rule)==b"fresh-rule:fresh"
s=port.readback(identity)
print(json.dumps({"revision":s.revision,"status":s.status,"rulehash":s.rule.artifact_sha256}))
'''
    run = subprocess.run([sys.executable, "-B", "-c", script, str(port.root), str(custody_file)],
                         cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                         timeout=20, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {"revision": 1, "status": "stopped_rule", "rulehash": ROUTE.artifact_sha256}
    assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in (source, prediction)] == source_stats


def test_default_preview_and_missing_port_no_write(tmp_path: Path) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    before = snapshot(port)
    assert ShadowControlService().apply(cmd).status == "unavailable"
    service = ShadowControlService(port=port, verifier=custody, clock=lambda: NOW)
    assert service.apply(cmd, proof=proof).status == "preview"
    assert service.apply(cmd, proof=proof, execute="yes").status == "rejected"  # type: ignore[arg-type]
    assert snapshot(port) == before


@pytest.mark.parametrize("case", ["cancel", "timeout", "future", "wrong_model", "wrong_model_revision",
                                    "stale_revision", "unknown_rule", "wrong_rulehash", "no_proof", "no_verifier",
                                    "self_hash", "wrong_proof", "expired_proof", "future_approval", "resume"])
def test_reject_without_mutating_state(tmp_path: Path, case: str) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    before = snapshot(port)
    clock = lambda: NOW
    cancel = Event()
    verifier: CallerCustody | None = custody
    supplied: ControlApprovalProof | None = proof
    if case == "cancel":
        cancel.set()
    elif case == "timeout":
        clock = lambda: cmd.deadline
    elif case == "future":
        clock = lambda: NOW - timedelta(seconds=1)
    elif case == "wrong_model":
        cmd = replace(cmd, identity=ShadowControlIdentity("wrong-model", "exact-r7"))
    elif case == "wrong_model_revision":
        cmd = replace(cmd, identity=ShadowControlIdentity("synthetic-model", "r8"))
    elif case == "stale_revision":
        cmd = replace(cmd, expected_revision=1)
    elif case == "unknown_rule":
        cmd = replace(cmd, last_rule=replace(ROUTE, rule_revision="unknown-last-rule"))
    elif case == "wrong_rulehash":
        pin = ControlSourcePin("last_rule", "wrong-rule", b"other-rule", digest(b"other-rule"))
        cmd = replace(cmd, last_rule=replace(ROUTE, artifact_sha256=pin.custody_sha256), source_pins=(pin,))
    elif case == "no_proof":
        supplied = None
    elif case == "no_verifier":
        verifier = None
    elif case == "self_hash":
        supplied = replace(proof, custody_id="self-observed-hash-is-not-approval")
    elif case == "wrong_proof":
        supplied = replace(proof, command_sha256=digest(b"wrong"))
    elif case == "expired_proof":
        supplied = replace(proof, expires_at=NOW)
    elif case == "future_approval":
        supplied = replace(proof, approved_at=NOW + timedelta(seconds=1))
    elif case == "resume":
        cmd = replace(cmd, action="resume")
    if case in {"wrong_model", "wrong_model_revision", "stale_revision", "unknown_rule", "wrong_rulehash", "resume"}:
        supplied = custody.approve(cmd)
    result = ShadowControlService(port=port, verifier=verifier, clock=clock).apply(cmd, proof=supplied,
                                                                               execute=True, cancel=cancel)
    assert result.status in ("rejected", "cancelled", "timeout")
    assert snapshot(port) == before


@pytest.mark.parametrize("case", ["cancel", "timeout"])
def test_no_late_commit_after_slow_custody(tmp_path: Path, case: str) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    before = snapshot(port)
    cancel = Event()
    now = [NOW]
    def late() -> None:
        if case == "cancel":
            cancel.set()
        else:
            now[0] = cmd.deadline
    custody.hook = late
    result = ShadowControlService(port=port, verifier=custody, clock=lambda: now[0]).apply(
        cmd, proof=proof, execute=True, cancel=cancel)
    assert result.status == ("cancelled" if case == "cancel" else "timeout")
    assert snapshot(port) == before


def test_cas_duplicate_and_direct_port_cancellation(tmp_path: Path) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    ctx = ControlContext(cmd.deadline, lambda: NOW, Event())
    assert port.stop_and_restore_rule(cmd, proof, ctx).revision == 1
    before = snapshot(port)
    with pytest.raises(ValueError, match="cas_"):
        port.stop_and_restore_rule(cmd, proof, ctx)
    assert snapshot(port) == before
    assert ShadowControlService(port=port, verifier=custody, clock=lambda: NOW).apply(
        cmd, proof=proof, execute=True).status == "rejected"


def test_dispatch_lock_prevents_inflight_and_wrong_model(tmp_path: Path) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    before = snapshot(port)
    def inflight(raw: bytes) -> bytes:
        result = ShadowControlService(port=port, verifier=custody, clock=lambda: NOW).apply(cmd, proof=proof, execute=True)
        assert result.status == "unavailable"
        return raw
    assert port.dispatch(IDENTITY, b"inflight", model_runner=inflight, rule_runner=lambda r, a, q: q) == b"inflight"
    with pytest.raises(ValueError, match="wrong_model"):
        port.dispatch(ShadowControlIdentity("other", "r7"), b"q", model_runner=inflight, rule_runner=lambda r, a, q: q)
    assert snapshot(port) == before


@pytest.mark.parametrize("mode", ["corrupt", "gap", "unknown", "custody_revoked", "tail_truncated"])
def test_saved_invalid_state_never_falls_back_to_model(tmp_path: Path, mode: str) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    assert ShadowControlService(port=port, verifier=custody, clock=lambda: NOW).apply(cmd, proof=proof, execute=True).status == "completed"
    if mode == "corrupt":
        (port.root / "receipt-000001.json").write_bytes(b"interrupted")
    elif mode == "gap":
        (port.root / "receipt-000001.json").rename(port.root / "receipt-000002.json")
    elif mode == "unknown":
        (port.root / "unexpected.json").write_bytes(b"{}")
    elif mode == "custody_revoked":
        custody.records.clear()
    else:
        (port.root / "receipt-000001.json").unlink()
    calls: list[str] = []
    def model(q: bytes) -> bytes:
        calls.append("model")
        return q
    def rule(r: RuleRoute, a: bytes, q: bytes) -> bytes:
        calls.append("rule")
        return q
    with pytest.raises((ValueError, KeyError)):
        port.dispatch(IDENTITY, b"q", model_runner=model, rule_runner=rule)
    assert calls == []


def test_port_readback_false_success_rejected(tmp_path: Path) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    class LyingPort:
        def readback(self, identity: ShadowControlIdentity) -> ShadowControlState:
            return port.readback(identity)
        def stop_and_restore_rule(self, c: ShadowControlCommand, p: ControlApprovalProof,
                                  context: ControlContext) -> ShadowControlState:
            return replace(port.readback(c.identity), status="stopped_rule", revision=1)
    result = ShadowControlService(port=LyingPort(), verifier=custody, clock=lambda: NOW).apply(cmd, proof=proof, execute=True)
    assert result.status == "rejected" and result.blockers == ("control_readback_mismatch",)
    assert len(snapshot(port)) == 1


def test_clock_pins_new_root_and_namespace_guard(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="aware"):
        command(issued_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="source_pin"):
        ControlSourcePin("prediction", "p", PREDICTION_BYTES, digest(b"changed"))
    port, custody, cmd, proof = setup(tmp_path)
    with pytest.raises(ValueError, match="new_root"):
        SyntheticShadowControlPort.create(root=port.root, namespace="synthetic://b14", command=cmd, proof=proof,
                                          verifier=custody, context=ControlContext(cmd.deadline, lambda: NOW, Event()))
    with pytest.raises(ValueError, match="namespace"):
        SyntheticShadowControlPort(root=port.root, namespace="production", verifier=custody)
    with pytest.raises(ValueError, match="absolute"):
        SyntheticShadowControlPort(root=Path("relative"), namespace="synthetic://b14", verifier=custody)


@pytest.mark.parametrize("case", ["cancel", "timeout"])
def test_direct_port_rechecks_cancel_before_publication(tmp_path: Path, case: str) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    before = snapshot(port)
    cancel = Event()
    now = [NOW]
    def late() -> None:
        if case == "cancel":
            cancel.set()
        else:
            now[0] = cmd.deadline
    custody.hook = late
    with pytest.raises(ValueError, match="cancelled" if case == "cancel" else "timeout"):
        port.stop_and_restore_rule(cmd, proof, ControlContext(cmd.deadline, lambda: now[0], cancel))
    assert snapshot(port) == before


@pytest.mark.parametrize("case", ["cancel", "timeout"])
def test_cancellation_after_commit_reports_actual_committed_state(tmp_path: Path, case: str) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    cancel = Event()
    now = [NOW]
    class ReturningPort:
        def readback(self, identity: ShadowControlIdentity) -> ShadowControlState:
            return port.readback(identity)
        def stop_and_restore_rule(self, c: ShadowControlCommand, p: ControlApprovalProof,
                                  context: ControlContext) -> ShadowControlState:
            state = port.stop_and_restore_rule(c, p, context)
            if case == "cancel":
                cancel.set()
            else:
                now[0] = cmd.deadline
            return state
    result = ShadowControlService(port=ReturningPort(), verifier=custody, clock=lambda: now[0]).apply(
        cmd, proof=proof, execute=True, cancel=cancel)
    assert result.status == "completed" and result.state == port.readback(IDENTITY)


def test_caller_full_proof_rejects_expiry_extension(tmp_path: Path) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    original = replace(proof, expires_at=NOW + timedelta(seconds=10))
    custody.records[proof.custody_id] = (cmd.identity_sha256, cmd.source_pins_sha256, original.identity_sha256)
    extended = replace(original, expires_at=NOW + timedelta(minutes=1))
    result = ShadowControlService(port=port, verifier=custody, clock=lambda: NOW + timedelta(seconds=20)).apply(
        cmd, proof=extended, execute=True)
    assert result.status == "rejected" and result.blockers == ("caller_custody_rejected",)


def test_publication_failure_after_reservation_cannot_restore_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    def failed_link(source: object, target: object) -> None:
        raise OSError("synthetic publication failure")
    monkeypatch.setattr(os, "link", failed_link)
    result = ShadowControlService(port=port, verifier=custody, clock=lambda: NOW).apply(cmd, proof=proof, execute=True)
    assert result.status == "unavailable"
    assert custody.revision_witness == (1, cmd.identity_sha256)
    with pytest.raises(ValueError, match="witness"):
        port.dispatch(IDENTITY, b"q", model_runner=lambda q: pytest.fail("model resumed"), rule_runner=lambda r, a, q: q)


def test_bootstrap_cancel_after_mkdir_leaves_unusable_new_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cmd = command()
    custody = CallerCustody()
    proof = custody.approve(cmd)
    cancel = Event()
    root = tmp_path / "cancelled-bootstrap"
    original_mkdir = Path.mkdir
    def cancel_after_mkdir(path: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)
        if path == root:
            cancel.set()
    monkeypatch.setattr(Path, "mkdir", cancel_after_mkdir)
    with pytest.raises(ValueError, match="cancelled"):
        SyntheticShadowControlPort.create(root=root, namespace="synthetic://b14", command=cmd, proof=proof,
                                          verifier=custody, context=ControlContext(cmd.deadline, lambda: NOW, cancel))
    assert root.is_dir() and list(root.iterdir()) == []
    assert custody.revision_witness == (0, None)
    with pytest.raises(ValueError, match="inventory"):
        SyntheticShadowControlPort(root=root, namespace="synthetic://b14", verifier=custody)


@pytest.mark.parametrize("field", ["identity", "revision", "status", "rule", "command_sha256", "source_pins_sha256", "namespace"])
def test_exact_readback_every_binding(tmp_path: Path, field: str) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    class MismatchPort:
        stopped = False
        def readback(self, identity: ShadowControlIdentity) -> ShadowControlState:
            state = port.readback(identity)
            if not self.stopped:
                return state
            state = replace(state, status="stopped_rule", revision=1,
                            command_sha256=cmd.identity_sha256, source_pins_sha256=cmd.source_pins_sha256)
            changes: dict[str, Any] = {
                "identity": ShadowControlIdentity("other-model", "exact-r7"),
                "revision": True, "status": "shadow_available", "rule": replace(ROUTE, rule_revision="wrong-rule"),
                "command_sha256": digest(b"wrong-command"), "source_pins_sha256": digest(b"wrong-pins"),
                "namespace": "synthetic://wrong-namespace",
            }
            return replace(state, **{field: changes[field]})
        def stop_and_restore_rule(self, c: ShadowControlCommand, p: ControlApprovalProof,
                                  context: ControlContext) -> ShadowControlState:
            self.stopped = True
            return self.readback(c.identity)
    result = ShadowControlService(port=MismatchPort(), verifier=custody, clock=lambda: NOW).apply(cmd, proof=proof, execute=True)
    assert result.status == "rejected" and len(snapshot(port)) == 1


def test_detached_pins_defensive_copy() -> None:
    raw = bytearray(RULE_BYTES)
    pin = ControlSourcePin("last_rule", "rule", raw, digest(bytes(raw)))  # type: ignore[arg-type]
    raw[:] = b"mutated"
    assert pin.content == RULE_BYTES
    pins = [pin]
    cmd = command(source_pins=pins)
    pins.clear()
    assert cmd.source_pins == (pin,)


def test_no_custody_on_bootstrap_no_root_created(tmp_path: Path) -> None:
    cmd = command()
    custody = CallerCustody()
    proof = ControlApprovalProof("unknown", cmd.identity_sha256, cmd.source_pins_sha256,
                                 NOW - timedelta(seconds=1), NOW + timedelta(minutes=2))
    root = tmp_path / "not-created"
    with pytest.raises(ValueError, match="custody"):
        SyntheticShadowControlPort.create(root=root, namespace="synthetic://test", command=cmd, proof=proof,
                                          verifier=custody, context=ControlContext(cmd.deadline, lambda: NOW, Event()))
    assert not root.exists()


def test_hardlink_receipt_refused(tmp_path: Path) -> None:
    port, _, _, _ = setup(tmp_path)
    os.link(port.root / "receipt-000000.json", tmp_path / "receipt-copy.json")
    calls: list[str] = []
    def model(q: bytes) -> bytes:
        calls.append("model")
        return q
    def rule(r: RuleRoute, a: bytes, q: bytes) -> bytes:
        calls.append("rule")
        return q
    with pytest.raises(ValueError, match="hardlink"):
        port.dispatch(IDENTITY, b"q", model_runner=model, rule_runner=rule)
    assert calls == []


@pytest.mark.parametrize("case", ["cancel", "timeout"])
def test_staging_io_cannot_publish_late(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    port, custody, cmd, proof = setup(tmp_path)
    before = snapshot(port)
    cancel = Event()
    now = [NOW]
    original_fsync = os.fsync
    def slow_fsync(fd: int) -> None:
        original_fsync(fd)
        if case == "cancel":
            cancel.set()
        else:
            now[0] = cmd.deadline
    monkeypatch.setattr(os, "fsync", slow_fsync)
    result = ShadowControlService(port=port, verifier=custody, clock=lambda: now[0]).apply(
        cmd, proof=proof, execute=True, cancel=cancel)
    assert result.status == ("cancelled" if case == "cancel" else "timeout")
    assert snapshot(port) == before
