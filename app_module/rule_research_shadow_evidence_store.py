"""隔離 append-only freeze journal；原 B13 pins／結果 bytes 與獨立 caller witness。"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterator

from app_module.rule_research_model_input_adapter import (
    ModelInputEvidence, ModelInputFairDenominatorRow, ModelInputPathBar, ModelInputPolicy,
    ModelInputRunResult, ModelInputSample, ModelInputSourcePin, ModelInputTimeSplit,
    TrainingPreprocessingAudit, prepare_model_input,
)
from app_module.rule_research_shadow_control import ControlContext, ShadowControlIdentity, canonical, digest
from app_module.rule_research_shadow_control_store import _namespace, _root, _safe
from app_module.rule_research_shadow_evidence_composition import FrozenShadowEvidence, ShadowEvidenceCustody, validate_frozen


def _encode(value: object) -> Any:
    if isinstance(value, bytes):
        return {"bytes_b64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, datetime):
        return {"aware_datetime": value.isoformat()}
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value) if not f.name.startswith("_")}
    if isinstance(value, (tuple, list)):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("freeze_codec_type")


def _unwire(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"bytes_b64"}:
            return base64.b64decode(value["bytes_b64"], validate=True)
        if set(value) == {"decimal"}:
            return Decimal(value["decimal"])
        if set(value) == {"aware_datetime"}:
            return datetime.fromisoformat(value["aware_datetime"])
        return {k: _unwire(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwire(v) for v in value]
    return value


def _decode(value: dict[str, Any]) -> FrozenShadowEvidence:
    wire = value
    data = _unwire(wire)
    p = data["prepared"]
    policy_value = dict(p["policy"])
    policy_value["split"] = None if policy_value["split"] is None else ModelInputTimeSplit(**policy_value["split"])
    policy = ModelInputPolicy(**policy_value)
    samples = []
    for row in p["samples"]:
        row = dict(row)
        row["path"] = tuple(ModelInputPathBar(**bar) for bar in row["path"])
        samples.append(ModelInputSample(**row))
    e = dict(p["evidence"])
    e["pins"] = tuple(ModelInputSourcePin(**pin) for pin in e["pins"])
    evidence = ModelInputEvidence(**e)
    denominator = tuple(ModelInputFairDenominatorRow(**row) for row in p["fair_denominator"])
    audit = None if p["preprocessing_audit"] is None else TrainingPreprocessingAudit(**p["preprocessing_audit"])
    prepared = prepare_model_input(policy, tuple(samples), evidence, fair_denominator=denominator, preprocessing_audit=audit)
    # 新程序以 public prepare 取得本程序 seal；不把舊程序私有 seal 視為 authority。
    result = ModelInputRunResult(**data["result"])
    frozen = FrozenShadowEvidence(prepared, result, ShadowControlIdentity(**data["model_identity"]),
                                  data["method_id"], data["prediction_available_at"], data["decision_cutoff"],
                                  data["decision_timezone"], data["captured_at"])
    if _encode(frozen) != wire:
        raise ValueError("freeze_codec_exact_roundtrip_mismatch")
    return frozen


class ShadowEvidenceStore:
    def __init__(self, *, root: Path, namespace: str, custody: ShadowEvidenceCustody) -> None:
        self.root = _root(root)
        _namespace(namespace)
        self.namespace, self.custody = namespace, custody
        if not self.root.is_dir():
            raise ValueError("freeze_store_missing")
        self.read_all()

    @classmethod
    def create(cls, *, root: Path, namespace: str, custody: ShadowEvidenceCustody,
               context: ControlContext) -> ShadowEvidenceStore:
        root = _root(root)
        _namespace(namespace)
        context.check()
        if root.exists() or not root.parent.is_dir():
            raise ValueError("freeze_new_root_required")
        if custody.current_evidence_revision(namespace) != (0, None):
            raise ValueError("freeze_initial_witness_mismatch")
        context.check()
        root.mkdir(exist_ok=False)
        return cls(root=root, namespace=namespace, custody=custody)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        _safe(self.root)
        path = self.root / ".freeze.lock"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            yield
        finally:
            os.close(fd)
            path.unlink()

    def read_all(self) -> tuple[FrozenShadowEvidence, ...]:
        _safe(self.root)
        entries = sorted(self.root.iterdir())
        files = [p for p in entries if re.fullmatch(r"freeze-\d{6}\.json", p.name)]
        if len(files) > 128 or any(p not in files and p.name != ".freeze.lock" for p in entries):
            raise ValueError("freeze_inventory_invalid")
        previous: str | None = None
        result: list[FrozenShadowEvidence] = []
        keys: set[tuple[str, str]] = set()
        for revision, path in enumerate(files, 1):
            if path.name != f"freeze-{revision:06d}.json":
                raise ValueError("freeze_revision_gap")
            _safe(path)
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("freeze_receipt_capacity")
            raw = path.read_bytes()
            data = json.loads(raw)
            payload = data["payload"]
            if (set(data) != {"payload", "payload_sha256"} or canonical(data) != raw
                    or set(payload) != {"schema", "namespace", "revision", "previous_sha256", "frozen"}
                    or payload["schema"] != "baldr-b14-freeze-store.v1"
                    or payload["namespace"] != self.namespace or type(payload["revision"]) is not int
                    or payload["revision"] != revision or payload["previous_sha256"] != previous
                    or digest(canonical(payload)) != data["payload_sha256"]):
                raise ValueError("freeze_receipt_identity_mismatch")
            frozen = _decode(payload["frozen"])
            validate_frozen(frozen, self.custody)
            sample = next(s for s in frozen.prepared.samples if s.phase == "evaluation")
            key = (sample.symbol, sample.decision_date)
            if key in keys:
                raise ValueError("freeze_duplicate_stock_date")
            keys.add(key)
            result.append(frozen)
            previous = digest(raw)
        witness = self.custody.current_evidence_revision(self.namespace)
        if type(witness[0]) is not int or witness != (len(result), previous):
            raise ValueError("freeze_caller_witness_mismatch")
        return tuple(result)

    def append(self, frozen: FrozenShadowEvidence, *, expected_revision: int,
               context: ControlContext, execute: bool = False) -> int:
        if type(expected_revision) is not int or expected_revision < 0 or type(execute) is not bool:
            raise ValueError("freeze_cas_execute_invalid")
        context.check()
        validate_frozen(frozen, self.custody)
        if context.check() > frozen.decision_cutoff:
            raise ValueError("late_freeze_publication")
        with self._lock():
            current = self.read_all()
            if len(current) != expected_revision or expected_revision >= 128:
                raise ValueError("freeze_cas_revision_mismatch")
            sample = next(s for s in frozen.prepared.samples if s.phase == "evaluation")
            if any((next(s for s in item.prepared.samples if s.phase == "evaluation").symbol,
                    next(s for s in item.prepared.samples if s.phase == "evaluation").decision_date)
                   == (sample.symbol, sample.decision_date) for item in current):
                raise ValueError("freeze_duplicate_stock_date")
            if not execute:
                return expected_revision
            witness = self.custody.current_evidence_revision(self.namespace)
            payload = {"schema": "baldr-b14-freeze-store.v1", "namespace": self.namespace,
                       "revision": expected_revision + 1, "previous_sha256": witness[1], "frozen": _encode(frozen)}
            raw = canonical({"payload": payload, "payload_sha256": digest(canonical(payload))})
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("freeze_receipt_capacity")
            fd, name = tempfile.mkstemp(prefix=".pending-", dir=self.root)
            staging = Path(name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                if context.check() > frozen.decision_cutoff:
                    raise ValueError("late_freeze_publication")
                if self.custody.reserve_evidence_revision(self.namespace, expected_revision, digest(raw)) is not True:
                    raise ValueError("freeze_caller_cas_rejected")
                # The caller CAS is the commit point: finish publication/readback
                # even if cancellation arrives after that irreversible reservation.
                os.link(staging, self.root / f"freeze-{expected_revision + 1:06d}.json")
            finally:
                staging.unlink()
            if self.read_all()[-1] != frozen:
                raise ValueError("freeze_readback_mismatch")
            return expected_revision + 1
