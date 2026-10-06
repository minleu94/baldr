"""僅 synthetic 隔離 root 的持久控制 port 與受同一鎖保護的推論 dispatcher。"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable, Iterator, cast

from app_module.rule_research_shadow_control import (
    ControlApprovalProof, ControlContext, ControlSourcePin, ControlStateCustody,
    RuleRoute, ShadowControlCommand, ShadowControlIdentity, ShadowControlState,
    canonical, digest, verify_approval,
)


def _safe(path: Path) -> None:
    for item in (path, *path.parents):
        if item.exists():
            stat = item.lstat()
            if item.is_symlink() or getattr(stat, "st_file_attributes", 0) & 1024:
                raise ValueError("link_or_reparse_refused")
            if item.is_file() and stat.st_nlink != 1:
                raise ValueError("hardlink_refused")


def _root(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("absolute_isolation_root_required")
    _safe(path)
    resolved = path.resolve()
    repo_output = Path(__file__).resolve().parents[1] / "output"
    parents = (Path(tempfile.gettempdir()).resolve(), repo_output.resolve())
    if not any(resolved != parent and resolved.is_relative_to(parent) for parent in parents):
        raise ValueError("synthetic_root_outside_temp_or_repo_output")
    return resolved


def _namespace(value: str) -> None:
    if not re.fullmatch(r"synthetic://[A-Za-z0-9_-]{1,80}", value):
        raise ValueError("explicit_synthetic_namespace_required")


def _command_payload(command: ShadowControlCommand, proof: ControlApprovalProof) -> dict[str, object]:
    return {
        "command_id": command.command_id, "action": command.action,
        "identity": asdict(command.identity), "expected_revision": command.expected_revision,
        "last_rule": asdict(command.last_rule), "issued_at": command.issued_at.isoformat(),
        "deadline": command.deadline.isoformat(),
        "source_pins": [{"role": p.role, "source_id": p.source_id,
                         "content_b64": base64.b64encode(p.content).decode("ascii"),
                         "custody_sha256": p.custody_sha256} for p in command.source_pins],
        "proof": {"custody_id": proof.custody_id, "command_sha256": proof.command_sha256,
                  "source_pins_sha256": proof.source_pins_sha256,
                  "approved_at": proof.approved_at.isoformat(), "expires_at": proof.expires_at.isoformat()},
    }


def _decode(payload: dict[str, object]) -> tuple[ShadowControlCommand, ControlApprovalProof]:
    # 嚴格 roundtrip 排除未知／缺欄位，不接受 hash 正確但語義錯誤的 receipt。
    identity = ShadowControlIdentity(**cast(dict[str, str], payload["identity"]))
    route = RuleRoute(**cast(dict[str, str], payload["last_rule"]))
    pins = tuple(ControlSourcePin(str(p["role"]), str(p["source_id"]),
                                 base64.b64decode(str(p["content_b64"]), validate=True),
                                 str(p["custody_sha256"]))
                 for p in cast(list[dict[str, object]], payload["source_pins"]))
    p = cast(dict[str, str], payload["proof"])
    proof = ControlApprovalProof(p["custody_id"], p["command_sha256"], p["source_pins_sha256"],
                                 datetime.fromisoformat(p["approved_at"]), datetime.fromisoformat(p["expires_at"]))
    command = ShadowControlCommand(str(payload["command_id"]), "stop_restore_rule", identity,
                                   cast(int, payload["expected_revision"]), route,
                                   datetime.fromisoformat(str(payload["issued_at"])),
                                   datetime.fromisoformat(str(payload["deadline"])), pins)
    if _command_payload(command, proof) != payload:
        raise ValueError("receipt_command_codec_mismatch")
    if proof.command_sha256 != command.identity_sha256 or proof.source_pins_sha256 != command.source_pins_sha256:
        raise ValueError("receipt_proof_binding_mismatch")
    if not proof.approved_at <= command.issued_at < proof.expires_at:
        raise ValueError("receipt_approval_clock_mismatch")
    return command, proof


class SyntheticShadowControlPort:
    """禁止自建核准；每次讀回均向 caller custody 驗證原保存 proof。"""

    def __init__(self, *, root: Path, namespace: str, verifier: ControlStateCustody) -> None:
        self.root = _root(root)
        _namespace(namespace)
        self.namespace = namespace
        self.verifier = verifier
        if not self.root.is_dir():
            raise ValueError("synthetic_store_missing")
        self._load()

    @classmethod
    def create(cls, *, root: Path, namespace: str, command: ShadowControlCommand,
               proof: ControlApprovalProof, verifier: ControlStateCustody,
               context: ControlContext) -> SyntheticShadowControlPort:
        root = _root(root)
        _namespace(namespace)
        if root.exists() or not root.parent.is_dir():
            raise ValueError("new_root_with_existing_parent_required")
        verify_approval(command, proof, verifier, context.check())
        if command.expected_revision != 0:
            raise ValueError("bootstrap_revision_must_be_zero")
        if verifier.current_revision(namespace, command.identity) != (0, None):
            raise ValueError("bootstrap_caller_revision_mismatch")
        context.check()
        root.mkdir(exist_ok=False)
        port = object.__new__(cls)
        port.root, port.namespace, port.verifier = root, namespace, verifier
        with port._lock():
            context.check()
            port._append(0, "shadow_available", command, proof, None, context)
        return cls(root=root, namespace=namespace, verifier=verifier)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        _safe(self.root)
        path = self.root / ".control.lock"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            yield
        finally:
            os.close(fd)
            path.unlink()

    def _append(self, revision: int, status: str, command: ShadowControlCommand,
                proof: ControlApprovalProof, previous: str | None, context: ControlContext) -> None:
        payload = {"schema_version": "baldr-b14-control.v1", "namespace": self.namespace,
                   "revision": revision, "status": status, "previous_sha256": previous,
                   "command": _command_payload(command, proof)}
        raw = canonical({"payload": payload, "payload_sha256": digest(canonical(payload))})
        if len(raw) > 1048576 or revision >= 256:
            raise ValueError("control_receipt_capacity")
        # 先 fsync 自有 staging，再核 deadline/cancel，exclusive 原子發布新 revision。
        # 中斷留下 staging／多連結時讀回拒絕，不回退到可用模型。
        path = self.root / f"receipt-{revision:06d}.json"
        _safe(path)
        fd, staging_name = tempfile.mkstemp(prefix=".pending-", dir=self.root)
        staging = Path(staging_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            context.check()
            if revision:
                if self.verifier.reserve_stop_revision(self.namespace, command, proof) is not True:
                    raise ValueError("caller_revision_cas_rejected")
            else:
                if self.verifier.current_revision(self.namespace, command.identity) != (0, None):
                    raise ValueError("bootstrap_caller_revision_mismatch")
            now = context.check()
            if not command.issued_at <= now < proof.expires_at:
                raise ValueError("publication_clock_or_approval_expired")
            os.link(staging, path)
        finally:
            staging.unlink()

    def _load(self) -> tuple[ShadowControlState, ShadowControlCommand, str]:
        _safe(self.root)
        entries = sorted(self.root.iterdir())
        files = [p for p in entries if re.fullmatch(r"receipt-\d{6}\.json", p.name)]
        if not files or len(files) > 256 or any(p.name != ".control.lock" and p not in files for p in entries):
            raise ValueError("control_store_inventory_invalid")
        previous: str | None = None
        initial: ShadowControlCommand | None = None
        command: ShadowControlCommand | None = None
        state: ShadowControlState | None = None
        for revision, path in enumerate(files):
            if path.name != f"receipt-{revision:06d}.json":
                raise ValueError("control_revision_gap")
            _safe(path)
            if path.stat().st_size > 1048576:
                raise ValueError("control_receipt_capacity")
            raw = path.read_bytes()
            envelope = json.loads(raw)
            payload = envelope["payload"]
            if canonical(envelope) != raw or set(envelope) != {"payload", "payload_sha256"}:
                raise ValueError("control_envelope_invalid")
            if (set(payload) != {"schema_version", "namespace", "revision", "status", "previous_sha256", "command"}
                    or payload["schema_version"] != "baldr-b14-control.v1"
                    or payload["namespace"] != self.namespace or type(payload["revision"]) is not int
                    or payload["revision"] != revision or payload["previous_sha256"] != previous
                    or digest(canonical(payload)) != envelope["payload_sha256"]):
                raise ValueError("control_receipt_chain_mismatch")
            command, proof = _decode(payload["command"])
            if self.verifier.verify(command, proof) is not True:
                raise ValueError("persisted_caller_custody_rejected")
            if revision == 0:
                initial = command
                if command.expected_revision != 0 or payload["status"] != "shadow_available":
                    raise ValueError("bootstrap_state_invalid")
            else:
                assert initial is not None
                if (revision != 1 or command.expected_revision != revision - 1
                        or command.identity != initial.identity or command.last_rule != initial.last_rule
                        or payload["status"] != "stopped_rule"):
                    raise ValueError("control_transition_invalid")
            state = ShadowControlState(self.namespace, command.identity, revision, payload["status"],
                                       command.last_rule,
                                       command.identity_sha256 if revision else None,
                                       command.source_pins_sha256 if revision else None)
            previous = digest(raw)
        assert state is not None and command is not None and previous is not None
        witness = self.verifier.current_revision(self.namespace, state.identity)
        if (type(witness[0]) is not int or witness != (state.revision, state.command_sha256)):
            raise ValueError("caller_revision_witness_mismatch")
        return state, command, previous

    def readback(self, identity: ShadowControlIdentity) -> ShadowControlState:
        state, _, _ = self._load()
        if state.identity != identity:
            raise ValueError("wrong_model_revision")
        return state

    def stop_and_restore_rule(self, command: ShadowControlCommand, proof: ControlApprovalProof,
                              context: ControlContext) -> ShadowControlState:
        with self._lock():
            verify_approval(command, proof, self.verifier, context.check())
            state, _, previous = self._load()
            if (state.identity != command.identity or state.revision != command.expected_revision
                    or state.status != "shadow_available" or state.rule != command.last_rule):
                raise ValueError("cas_identity_revision_rule_status_mismatch")
            # verifier／IO 都可能耗時，因此提交前再次核 aware deadline 與取消。
            verify_approval(command, proof, self.verifier, context.check())
            context.check()
            self._append(state.revision + 1, "stopped_rule", command, proof, previous, context)
            return self.readback(command.identity)

    def dispatch(self, identity: ShadowControlIdentity, request: bytes, *,
                 model_runner: Callable[[bytes], bytes],
                 rule_runner: Callable[[RuleRoute, bytes, bytes], bytes]) -> bytes:
        """same-lock 序列化正在執行的 synthetic 推論與 stop；停用後不呼 model_runner。"""
        with self._lock():
            state, command, _ = self._load()
            if state.identity != identity:
                raise ValueError("wrong_model_revision")
            if state.status == "shadow_available":
                return model_runner(bytes(request))
            if state.status == "stopped_rule":
                pin = next(p for p in command.source_pins if p.role == "last_rule")
                return rule_runner(state.rule, pin.content, bytes(request))
            raise ValueError("unknown_dispatch_state")
