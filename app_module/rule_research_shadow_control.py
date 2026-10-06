"""隔離 shadow 控制契約；核准由 caller 的獨立 custody verifier 提供。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from threading import Event
from typing import Callable, Literal, Protocol


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware_clock_required")
    return value.astimezone(timezone.utc)


def text_identity(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("identity_invalid")


def hash_identity(value: str) -> None:
    if len(value) != 71 or not value.startswith("sha256:") or any(c not in "0123456789abcdef" for c in value[7:]):
        raise ValueError("sha256_invalid")


@dataclass(frozen=True, slots=True)
class ShadowControlIdentity:
    model_id: str
    model_revision: str

    def __post_init__(self) -> None:
        text_identity(self.model_id)
        text_identity(self.model_revision)


@dataclass(frozen=True, slots=True)
class RuleRoute:
    rule_id: str
    rule_revision: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        text_identity(self.rule_id)
        text_identity(self.rule_revision)
        hash_identity(self.artifact_sha256)


@dataclass(frozen=True, slots=True)
class ControlSourcePin:
    role: str
    source_id: str
    content: bytes
    custody_sha256: str

    def __post_init__(self) -> None:
        text_identity(self.role)
        text_identity(self.source_id)
        object.__setattr__(self, "content", bytes(self.content))
        hash_identity(self.custody_sha256)
        if len(self.content) > 65536 or digest(self.content) != self.custody_sha256:
            raise ValueError("source_pin_mismatch_or_bound")


@dataclass(frozen=True, slots=True)
class ShadowControlCommand:
    command_id: str
    action: Literal["stop_restore_rule", "resume"]
    identity: ShadowControlIdentity
    expected_revision: int
    last_rule: RuleRoute
    issued_at: datetime
    deadline: datetime
    source_pins: tuple[ControlSourcePin, ...]

    def __post_init__(self) -> None:
        text_identity(self.command_id)
        if self.action not in ("stop_restore_rule", "resume"):
            raise ValueError("action_invalid")
        if type(self.expected_revision) is not int or self.expected_revision < 0:
            raise ValueError("revision_invalid")
        object.__setattr__(self, "issued_at", aware(self.issued_at))
        object.__setattr__(self, "deadline", aware(self.deadline))
        object.__setattr__(self, "source_pins", tuple(self.source_pins))
        if self.deadline <= self.issued_at:
            raise ValueError("deadline_invalid")
        if not self.source_pins or len(self.source_pins) > 16 or sum(len(p.content) for p in self.source_pins) > 262144:
            raise ValueError("source_pin_bound")
        if len({p.role for p in self.source_pins}) != len(self.source_pins):
            raise ValueError("duplicate_source_role")
        rules = [p for p in self.source_pins if p.role == "last_rule"]
        if len(rules) != 1 or rules[0].custody_sha256 != self.last_rule.artifact_sha256:
            raise ValueError("last_rule_pin_required")

    @property
    def source_pins_sha256(self) -> str:
        return digest(canonical([(p.role, p.source_id, p.custody_sha256) for p in self.source_pins]))

    @property
    def identity_sha256(self) -> str:
        return digest(canonical({
            "command_id": self.command_id, "action": self.action,
            "identity": asdict(self.identity), "expected_revision": self.expected_revision,
            "last_rule": asdict(self.last_rule), "issued_at": self.issued_at.isoformat(),
            "deadline": self.deadline.isoformat(), "source_pins_sha256": self.source_pins_sha256,
        }))


@dataclass(frozen=True, slots=True)
class ControlApprovalProof:
    custody_id: str
    command_sha256: str
    source_pins_sha256: str
    approved_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        text_identity(self.custody_id)
        hash_identity(self.command_sha256)
        hash_identity(self.source_pins_sha256)
        object.__setattr__(self, "approved_at", aware(self.approved_at))
        object.__setattr__(self, "expires_at", aware(self.expires_at))
        if self.expires_at <= self.approved_at:
            raise ValueError("approval_clock_invalid")

    @property
    def identity_sha256(self) -> str:
        return digest(canonical({"custody_id": self.custody_id, "command_sha256": self.command_sha256,
                                 "source_pins_sha256": self.source_pins_sha256,
                                 "approved_at": self.approved_at.isoformat(), "expires_at": self.expires_at.isoformat()}))


class ControlApprovalVerifier(Protocol):
    def verify(self, command: ShadowControlCommand, proof: ControlApprovalProof) -> bool:
        """逐欄核對 caller 原核准（包含 approved_at/expires_at），不從 observed hash 推定核准。"""
        ...


class ControlStateCustody(ControlApprovalVerifier, Protocol):
    """caller 獨立持久的單調 revision witness，不與控制 receipts 共 root。"""

    def current_revision(self, namespace: str, identity: ShadowControlIdentity) -> tuple[int, str | None]: ...

    def reserve_stop_revision(self, namespace: str, command: ShadowControlCommand,
                              proof: ControlApprovalProof) -> bool:
        """獨立 CAS expected→expected+1，保存 exact command hash；成功後不可退回。"""
        ...


@dataclass(frozen=True, slots=True)
class ShadowControlState:
    namespace: str
    identity: ShadowControlIdentity
    revision: int
    status: Literal["shadow_available", "stopped_rule"]
    rule: RuleRoute
    command_sha256: str | None
    source_pins_sha256: str | None


class ControlCancelled(ValueError):
    pass


class ControlContext:
    """合作式取消；port 必須在原子提交前再檢查，不啟動背景控制工作。"""

    def __init__(self, deadline: datetime, clock: Callable[[], datetime], cancel: Event) -> None:
        self.deadline = aware(deadline)
        self.clock = clock
        self.cancel = cancel

    def check(self) -> datetime:
        now = aware(self.clock())
        if self.cancel.is_set():
            raise ControlCancelled("cancelled")
        if now >= self.deadline:
            raise ControlCancelled("timeout")
        return now


class ControlPort(Protocol):
    def readback(self, identity: ShadowControlIdentity) -> ShadowControlState: ...

    def stop_and_restore_rule(self, command: ShadowControlCommand, proof: ControlApprovalProof,
                              context: ControlContext) -> ShadowControlState:
        """原子 CAS 停 exact revision 並選定明示規則；取消／過期不得晚到提交。"""
        ...


@dataclass(frozen=True, slots=True)
class ShadowControlResult:
    status: Literal["preview", "unavailable", "rejected", "cancelled", "timeout", "completed"]
    command_sha256: str
    blockers: tuple[str, ...]
    state: ShadowControlState | None = None
    production_action_allowed: bool = False


def verify_approval(command: ShadowControlCommand, proof: ControlApprovalProof | None,
                    verifier: ControlApprovalVerifier | None, now: datetime) -> None:
    now = aware(now)
    if command.action != "stop_restore_rule":
        raise ValueError("resume_requires_separate_approved_adapter")
    if not command.issued_at <= now < command.deadline:
        raise ValueError("command_late_or_future")
    if proof is None or verifier is None:
        raise ValueError("independent_approval_required")
    if (proof.command_sha256 != command.identity_sha256
            or proof.source_pins_sha256 != command.source_pins_sha256
            or not proof.approved_at <= command.issued_at <= now < proof.expires_at):
        raise ValueError("approval_mismatch_or_expired")
    if verifier.verify(command, proof) is not True:
        raise ValueError("caller_custody_rejected")


class ShadowControlService:
    def __init__(self, *, port: ControlPort | None = None,
                 verifier: ControlApprovalVerifier | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.port = port
        self.verifier = verifier
        self.clock = clock

    def apply(self, command: ShadowControlCommand, *, proof: ControlApprovalProof | None = None,
              execute: bool = False, cancel: Event | None = None) -> ShadowControlResult:
        sha = command.identity_sha256
        if type(execute) is not bool:
            return ShadowControlResult("rejected", sha, ("execute_must_be_bool",))
        if self.port is None:
            return ShadowControlResult("unavailable", sha, ("control_port_missing",))
        context = ControlContext(command.deadline, self.clock, cancel if cancel is not None else Event())
        try:
            now = context.check()
            verify_approval(command, proof, self.verifier, now)
            before = self.port.readback(command.identity)
            if (before.identity != command.identity or type(before.revision) is not int
                    or before.revision != command.expected_revision
                    or before.rule != command.last_rule or before.status != "shadow_available"):
                raise ValueError("readback_identity_revision_rule_status_mismatch")
            context.check()
            if not execute:
                return ShadowControlResult("preview", sha, (), before)
            assert proof is not None
            context.check()
            applied = self.port.stop_and_restore_rule(command, proof, context)
            # port 提交為線性化點；提交後取消不冒充未執行，仍須取得真實 readback。
            readback = self.port.readback(command.identity)
            if (applied != readback or readback.identity != command.identity or type(readback.revision) is not int
                    or readback.revision != command.expected_revision + 1
                    or readback.status != "stopped_rule" or readback.rule != command.last_rule
                    or readback.command_sha256 != sha
                    or readback.source_pins_sha256 != command.source_pins_sha256
                    or readback.namespace != before.namespace):
                raise ValueError("control_readback_mismatch")
            return ShadowControlResult("completed", sha, (), readback)
        except ControlCancelled as exc:
            status: Literal["cancelled", "timeout"] = "cancelled" if str(exc) == "cancelled" else "timeout"
            return ShadowControlResult(status, sha, (str(exc),))
        except ValueError as exc:
            return ShadowControlResult("rejected", sha, (str(exc),))
        except Exception:
            return ShadowControlResult("unavailable", sha, ("port_failure_state_unconfirmed",))
