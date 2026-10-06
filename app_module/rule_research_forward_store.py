"""UX21 隔離 outcome 保存／唯讀重讀；沿用 atomic、hash、容量與 revision 契約。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
import json
import base64
import zlib
from pathlib import Path
from typing import Any, Callable

from app_module.rule_research_forward_outcome import CostPolicy, ForwardOutcomeProjection
from app_module.rule_research_forward_source import ADAPTER_VERSION, build_current_observed_forward
from app_module.rule_research_observation_acceptance import _parent
from app_module.rule_research_sample_capture import (
    MAX_CAPTURES, MAX_CAPTURE_BYTES, MAX_RETAINED_BYTES, SAFETY_RESERVE_BYTES,
    BoundedRuleResearchCaptureWriter, _clock, _digest, _identity, _json, _read_file, _require, _safe_path,
)

STORE_SCHEMA = "rule-research-forward-saved.v1"
RUNTIME_SCHEMA = "rule-research-forward-isolated-runtime.v1"
QUALIFICATION = {"research_only": True, "historical_pit_eligible": False, "formal_eligible": False,
                 "training_eligible": False, "natural_authority": False, "execution_eligible": False,
                 "selection_status": "unknown", "source_mode": "current_observed"}
MAX_PROJECTION_BYTES = 2 * 1024 * 1024


def _projection(body: dict[str, Any]) -> dict[str, Any]:
    value = body["projection"]
    if value.get("encoding") == "zlib-json.v1":
        _require(set(value) == {"encoding", "raw_bytes", "sha256", "data_base64"}
            and type(value["raw_bytes"]) is int and 0 < value["raw_bytes"] <= MAX_PROJECTION_BYTES,
            "forward_projection_bound")
        encoded = base64.b64decode(value["data_base64"], validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(encoded, MAX_PROJECTION_BYTES + 1)
        _require(len(raw) == value["raw_bytes"] and len(raw) <= MAX_PROJECTION_BYTES
            and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
            and _digest(raw) == value["sha256"], "forward_projection_compression_invalid")
        return ForwardOutcomeProjection(raw.decode("utf-8")).to_dict()
    return ForwardOutcomeProjection(_json(value)).to_dict()


def _pack_projection(value: dict[str, Any]) -> dict[str, Any]:
    raw = _json(value).encode("utf-8")
    _require(len(raw) <= MAX_PROJECTION_BYTES, "forward_projection_bound")
    return {"encoding": "zlib-json.v1", "raw_bytes": len(raw), "sha256": _digest(raw),
            "data_base64": base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")}


@dataclass(frozen=True, slots=True)
class SavedForwardOutcome:
    body_json: str

    def to_dict(self) -> dict[str, Any]:
        b = json.loads(self.body_json)
        _require(len(self.body_json.encode("utf-8")) <= MAX_CAPTURE_BYTES and _json(b) == self.body_json,
                 "forward_saved_byte_or_canonical_bound")
        _require(set(b) == {"schema_version", "capture_identity_sha256", "observed_at", "adapter_version",
            "qualification", "runtime_pin", "parent_pin", "source_contract", "projection"}
            and b["schema_version"] == STORE_SCHEMA and b["adapter_version"] == ADAPTER_VERSION
            and b["qualification"] == QUALIFICATION and b["capture_identity_sha256"] == _identity(b),
            "forward_saved_envelope_invalid")
        p = _projection(b)
        _require(p["parent_identity_sha256"] == b["parent_pin"]["parent_identity_sha256"], "forward_saved_parent_mismatch")
        _require(b["source_contract"]["source_mode"] == "current_observed"
            and b["source_contract"]["source_availability"] == "unknown"
            and b["source_contract"]["calendar_scope"] == "planned_annual_closures_only"
            and b["source_contract"]["temporary_closure_status"] == "unknown"
            and p["benchmark"] is None, "forward_saved_source_scope_invalid")
        observed = datetime.fromisoformat(b["observed_at"])
        _clock(observed)
        _require(observed <= datetime.now(timezone.utc), "forward_saved_future_clock")
        return b

    @property
    def identity_sha256(self) -> str:
        return str(self.to_dict()["capture_identity_sha256"])


class BoundedForwardOutcomeWriter(BoundedRuleResearchCaptureWriter):
    def _free_bytes(self) -> int:
        import shutil
        probe = self.output_root
        while not probe.exists():
            probe = probe.parent
        return shutil.disk_usage(probe).free

    def _decode_capture(self, raw: bytes) -> dict[str, Any]:
        return SavedForwardOutcome(raw.decode("utf-8")).to_dict()

    def _make_receipt(self, body: dict[str, Any], raw: bytes) -> dict[str, Any]:
        p = _projection(body)
        return {"schema_version": "rule-research-forward-receipt.v1", "status": "complete",
            "capture_identity_sha256": body["capture_identity_sha256"], "capture_sha256": _digest(raw),
            "observed_at": body["observed_at"], "research_only": True,
            "parent_identity_sha256": body["parent_pin"]["parent_identity_sha256"],
            "result_identity_sha256": p["result_identity_sha256"],
            "decision_date": p["decision_date"], "as_of_date": p["as_of_date"]}


def read_forward_receipt(parent_receipt: str | Path, outcome_receipt: str | Path,
        *, cancel_callback: Callable[[], bool] | None = None) -> dict[str, Any]:
    cancel = cancel_callback or (lambda: False)
    if cancel():
        return {"cancelled": True}
    path = Path(outcome_receipt).absolute()
    _require(path.name == "receipt.json", "forward_saved_receipt_required")
    writer = BoundedForwardOutcomeWriter(path.parent.parent)
    package = writer.read(path.parent.name)
    b = package["capture"]
    _require(_parent(parent_receipt)[2] == b["parent_pin"], "forward_saved_parent_pin_changed")
    if cancel():
        return {"cancelled": True}
    _require(writer.read(path.parent.name) == package, "forward_saved_changed_during_read")
    # 重讀 sealed 版本不再查 current DB，市場後續 revision 不會改寫舊保存結果。
    return {"cancelled": False, "projection": _projection(b), "input_source": str(path),
            "input_sha256": package["receipt"]["capture_sha256"], "saved_identity_sha256": path.parent.name,
            "source_contract": b["source_contract"], "qualification": b["qualification"]}


def run_forward_isolated(runtime_path: str | Path, *, execute: bool = False,
        cancel_callback: Callable[[], bool] | None = None) -> dict[str, Any]:
    """明示 exact parent／來源／clock／cost；預設 preflight，不建 Task。"""
    publication: dict[str, Any] | None = None
    try:
        path = Path(runtime_path).absolute()
        raw = _read_file(path, 64 * 1024)
        from app_module.rule_research_forward_outcome_reader import _pairs
        config = json.loads(raw, object_pairs_hook=_pairs)
        _require(isinstance(config, dict) and set(config) == {"schema_version", "parent_receipt", "source_db",
            "calendar_cache", "as_of_date", "cost_policy", "benchmark", "outcome_root"}
            and config["schema_version"] == RUNTIME_SCHEMA and config["benchmark"] is None,
            "forward_runtime_scope_invalid")
        for key in ("parent_receipt", "source_db", "calendar_cache", "outcome_root"):
            _require(isinstance(config[key], str) and Path(config[key]).is_absolute(), "forward_runtime_absolute_paths_required")
        cost = None if config["cost_policy"] is None else CostPolicy(**config["cost_policy"])
        writer = BoundedForwardOutcomeWriter(config["outcome_root"])
        parent, _, _ = _parent(config["parent_receipt"])
        for source in (Path(parent["capture_root"]), Path(parent["snapshot_root"])):
            _require(not source.resolve().is_relative_to(writer.output_root)
                and not writer.output_root.is_relative_to(source.resolve()), "forward_source_output_overlap")
        for source in (path, Path(config["source_db"]), Path(config["calendar_cache"]), Path(parent["universe"]["source_ref"])):
            _require(not source.resolve().is_relative_to(writer.output_root), "forward_source_output_overlap")
        # 在 mkdir／lock 前做真實容量與保留上限檢查；不清除歷史，也不降低 200 GiB 保留。
        _safe_path(writer.output_root)
        if writer.output_root.exists():
            _require(not (writer.output_root / ".writer.lock").exists(), "writer_busy")
            count, retained = writer._inventory()
        else:
            count, retained = 0, 0
        _require(writer._free_bytes() >= SAFETY_RESERVE_BYTES + 2 * (MAX_CAPTURE_BYTES + 4096), "capacity_reserve")
        runtime_pin = {"source_ref": str(path.resolve()), "source_sha256": _digest(raw), "value": config}
        observed = datetime.now(timezone.utc).isoformat()
        def build() -> SavedForwardOutcome:
            _require(_read_file(path, 64 * 1024) == raw, "forward_runtime_changed")
            result = build_current_observed_forward(config["parent_receipt"], config["source_db"],
                config["calendar_cache"], as_of_date=config["as_of_date"], cost_policy=cost,
                cancel_callback=cancel_callback)
            result["projection"] = _pack_projection(result["projection"])
            body = {"schema_version": STORE_SCHEMA, "adapter_version": ADAPTER_VERSION,
                "qualification": dict(QUALIFICATION), "observed_at": observed, "runtime_pin": runtime_pin, **result}
            body["capture_identity_sha256"] = _identity(body)
            saved = SavedForwardOutcome(_json(body))
            saved.to_dict()
            return saved
        candidate = build()
        duplicate = (writer.output_root / candidate.identity_sha256).exists()
        _require(duplicate or (count < MAX_CAPTURES and retained + len(candidate.body_json.encode("utf-8")) + 4096 <= MAX_RETAINED_BYTES), "forward_retention_limit")
        result: dict[str, Any] = {"status": "preflight_passed", "qualification": dict(QUALIFICATION),
            "identity_sha256": candidate.identity_sha256, "projection": _projection(candidate.to_dict()),
            "source_contract": candidate.to_dict()["source_contract"], "saved": False}
        if execute:
            receipt = writer.write(candidate, revalidate=build)
            publication = receipt
            saved_path = Path(receipt["directory"]) / "receipt.json"
            reread = read_forward_receipt(config["parent_receipt"], saved_path, cancel_callback=cancel_callback)
            _require(not reread.get("cancelled"), "forward_cancelled")
            result.update(status="saved", saved=True, save_status=receipt["status"], receipt_path=str(saved_path), receipt=receipt)
        return result
    except Exception as exc:
        return {"status": "cancelled" if str(exc) == "forward_cancelled" else "blocked",
                "error_code": str(exc), "qualification": dict(QUALIFICATION), "saved": publication is not None,
                **({"receipt": publication, "receipt_path": str(Path(publication["directory"]) / "receipt.json")}
                   if publication is not None else {})}


def read_forward_revision_index(outcome_root: str | Path,
        *, evaluated_at: datetime) -> dict[str, list[dict[str, Any]]]:
    """每次日報只掃有界 store 一次，按 exact parent 分組；不選 latest。"""
    writer = BoundedForwardOutcomeWriter(outcome_root)
    _safe_path(writer.output_root)
    if not writer.output_root.exists():
        return {}
    _require(not (writer.output_root / ".writer.lock").exists(), "writer_busy")
    writer._inventory()
    def inventory() -> list[tuple[str, int, int]]:
        entries = list(islice(writer.output_root.iterdir(), MAX_CAPTURES + 1))
        _require(len(entries) <= MAX_CAPTURES, "retention_entry_limit")
        return sorted((p.name, p.stat().st_ino, p.stat().st_mtime_ns) for p in entries)
    before = inventory()
    results: dict[str, list[dict[str, Any]]] = {}
    for name, _, _ in before:
        package = writer.read(name)
        b = package["capture"]
        parent_identity = b["parent_pin"]["parent_identity_sha256"]
        visible = datetime.fromisoformat(b["observed_at"]) <= evaluated_at
        p = _projection(b)
        status: dict[str, int] = {}
        for member in p["members"]:
            for horizon in member["horizons"]:
                key = horizon["calculation_status"]
                status[key] = status.get(key, 0) + 1
        results.setdefault(parent_identity, []).append({"identity_sha256": name, "receipt_path": str(writer.output_root / name / "receipt.json"),
            "result_identity_sha256": p["result_identity_sha256"], "decision_date": p["decision_date"],
            "as_of_date": p["as_of_date"], "visible_at_evaluation": visible,
            "population": p["population"], "method_horizon_status_counts": status,
            "source_contract": b["source_contract"], "cost_policy": p["cost_policy"], "qualification": b["qualification"]})
    _require(inventory() == before, "forward_inventory_changed")
    return results


def read_parent_forward_revisions(outcome_root: str | Path, parent_identity: str,
        *, evaluated_at: datetime) -> list[dict[str, Any]]:
    return read_forward_revision_index(outcome_root, evaluated_at=evaluated_at).get(parent_identity, [])
