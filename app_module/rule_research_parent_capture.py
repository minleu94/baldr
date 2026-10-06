"""既有 MA producer/capture 的有界多批協調；同一 readonly transaction 母體。"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app_module.daily_market_method_contract import method_contracts_payload, method_contracts_sha256
from app_module.daily_market_research_universe import (
    RESEARCH_UNIVERSE_SCHEMA, load_research_universe_spec, _object, _text,
)
from app_module.daily_market_snapshot_producer import DailyMarketSnapshotInput, DailyMarketSnapshotProducer
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource, _source_pin
from app_module.rule_research_sample_capture import (
    MAX_CAPTURE_BYTES, BoundedRuleResearchCaptureWriter, RuleSampleCaptureError,
    _clock, _digest, _identity, _json, _read_file, _require, _safe_path, _write_file,
)
from app_module.rule_research_sample_readiness import read_saved_rule_sample_readiness

PARENT_UNIVERSE_SCHEMA = "daily-market-research-parent-universe.v1"
PARENT_SCHEMA = "rule-research-parent-capture.v1"
PARENT_RECEIPT_SCHEMA = "rule-research-parent-receipt.v1"
MAX_BATCHES = 16
MAX_PARENT_SOURCE_BYTES = 64 * 1024 * 1024
_POLICY = {"research_only": True, "historical_pit_eligible": False,
           "natural_authority": False, "formal_eligible": False, "training_eligible": False,
           "selection_status": "unknown", "selected_count": 0}
_STATES = {"pending", "snapshot_ready", "captured", "failed", "cancelled"}


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _parent_identity(body: dict[str, Any]) -> str:
    # published/unchanged/duplicate 是本次操作收據，不是不同研究結果身份。
    stable = {**body, "batches": [{k: v for k, v in b.items()
              if k not in {"production_status", "sample_capture_status"}} for b in body["batches"]]}
    return _identity(stable)


def _layout(value: dict[str, Any]) -> list[dict[str, Any]]:
    """唯一 deterministic 分批；不重複 included 來容納排除列。"""
    included, excluded = value["included_stock_codes"], value["excluded_stock_codes"]
    n = max((len(included) + 15) // 16, (len(excluded) + 15) // 16)
    _require(1 <= n <= min(len(included), MAX_BATCHES), "parent_batch_bound")
    batches = []
    for i in range(n):
        codes = included[i::n]
        exclusions = excluded[i * 16:(i + 1) * 16]
        batches.append({"batch_id": f"batch-{i+1:02d}",
                        "included_stock_codes": codes, "excluded_stock_codes": exclusions})
    return batches


def _validate_universe(value: Any) -> None:
    keys = {"schema_version", "universe_id", "version", "as_of_date", "method", "scope",
            "included_stock_codes", "excluded_stock_codes", "population_count",
            "research_only", "complete_fixed_cohort"}
    _require(isinstance(value, dict) and set(value) == keys, "parent_universe_schema_invalid")
    _require(value["schema_version"] == PARENT_UNIVERSE_SCHEMA
             and value["method"] == "daily-market-close-ma.v1"
             and value["scope"] == "bounded_multibatch_research_cohort"
             and value["research_only"] is True and value["complete_fixed_cohort"] is True,
             "parent_universe_policy_invalid")
    _text(value["universe_id"], "universe_id", 96)
    _text(value["version"], "version")
    _require(date.fromisoformat(value["as_of_date"]).isoformat() == value["as_of_date"], "parent_date_invalid")
    included, excluded = value["included_stock_codes"], value["excluded_stock_codes"]
    _require(isinstance(included, list) and 1 <= len(included) <= 16 * MAX_BATCHES
             and isinstance(excluded, list) and len(excluded) <= 16 * MAX_BATCHES,
             "parent_member_bound")
    for code in included:
        _text(code, "stock_code", 32)
    for e in excluded:
        _require(isinstance(e, dict) and set(e) == {"stock_code", "reason"}, "parent_exclusion_invalid")
        _text(e["stock_code"], "stock_code", 32)
        _text(e["reason"], "reason", 512)
    codes = included + [e["stock_code"] for e in excluded]
    _require(len(set(codes)) == len(codes), "parent_duplicate_member")
    _require(type(value["population_count"]) is int and value["population_count"] == len(codes),
             "parent_population_mismatch")
    _require(included == sorted(included) and excluded == sorted(excluded, key=lambda e: e["stock_code"]),
             "parent_members_not_canonical")
    _layout(value)


def load_parent_universe(path: str | Path) -> dict[str, Any]:
    raw_path = Path(path).absolute()
    _safe_path(raw_path)
    raw = _read_file(raw_path, MAX_CAPTURE_BYTES)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    # 設定次序不影響身份；來源 bytes hash 仍完整保留。
    if isinstance(value, dict) and isinstance(value.get("included_stock_codes"), list):
        value["included_stock_codes"] = sorted(value["included_stock_codes"])
    if isinstance(value, dict) and isinstance(value.get("excluded_stock_codes"), list):
        value["excluded_stock_codes"] = sorted(value["excluded_stock_codes"], key=lambda e: e["stock_code"])
    _validate_universe(value)
    return {"value": value, "source_ref": str(raw_path.resolve()), "source_sha256": _digest(raw)}


@dataclass(frozen=True, slots=True)
class RuleResearchParentCapture:
    body_json: str

    def to_dict(self) -> dict[str, Any]:
        _require(len(self.body_json.encode("utf-8")) <= MAX_CAPTURE_BYTES, "parent_byte_bound")
        body = json.loads(self.body_json)
        _require(isinstance(body, dict) and _json(body) == self.body_json
                 and body.get("schema_version") == PARENT_SCHEMA and body.get("policy") == _POLICY,
                 "parent_schema_invalid")
        _require(body.get("capture_identity_sha256") == _parent_identity(body), "parent_identity_mismatch")
        _validate_universe(body["universe"]["value"])
        _require(_sha(body["universe"].get("source_sha256")), "parent_universe_pin_invalid")
        _require(body.get("method_contracts_sha256") == _digest(_json(body["method_contracts"]).encode("utf-8")),
                 "parent_method_pin_invalid")
        clocks = [datetime.fromisoformat(body[k]) for k in ("decision_cutoff", "as_of", "observed_at")]
        for c in clocks:
            _clock(c)
        _require(clocks == sorted(clocks) and clocks[0].date().isoformat() == body["universe"]["value"]["as_of_date"],
                 "parent_clock_invalid")
        _require(_sha(body.get("plan_sha256")), "parent_plan_invalid")
        expected = _layout(body["universe"]["value"])
        batches = body.get("batches")
        _require(isinstance(batches, list) and len(batches) == len(expected), "parent_batches_missing")
        for b, e in zip(batches, expected):
            _require(isinstance(b, dict) and all(b.get(k) == v for k, v in e.items())
                     and b.get("status") in _STATES, "parent_batch_members_mismatch")
            _require(b.get("cohort_id") == f"{body['universe']['value']['universe_id']}:{b['batch_id']}:{body['plan_sha256'][:12]}",
                     "parent_batch_cohort_mismatch")
            if b["status"] in {"snapshot_ready", "captured"}:
                _require(_sha(b.get("manifest_sha256")), "parent_batch_pin_missing")
                _require(b.get("production_status") in {"published_complete", "published_partial", "unchanged"},
                         "parent_producer_status_invalid")
            if b["status"] == "captured":
                _require(_sha(b.get("capture_identity_sha256")), "parent_capture_pin_missing")
                _require(b.get("sample_capture_status") in {"published", "duplicate"}, "parent_sample_status_invalid")
            else:
                _require(b.get("capture_identity_sha256") is None, "parent_partial_capture_pin")
        completed = all(b["status"] == "captured" for b in batches)
        _require(body.get("status") in {"complete", "incomplete", "cancelled"}
                 and (body["status"] != "complete" or completed), "parent_false_complete")
        if body["status"] == "complete":
            _require(body.get("source_status") == "validated_transaction" and isinstance(body.get("source_binding"), dict),
                     "parent_source_unverified")
        source = body.get("source_binding")
        if source is not None:
            _require(isinstance(source, dict) and set(source) == {"mode", "database", "schema_identity_sha256", "revision_pin"}
                     and source["mode"] == "query_only_transaction_main_wal_stat_pin"
                     and isinstance(source["database"], str) and Path(source["database"]).is_absolute()
                     and _sha(source["schema_identity_sha256"]), "parent_source_binding_invalid")
            pins = source["revision_pin"]
            _require(isinstance(pins, list) and len(pins) == 2
                     and all(isinstance(p, list) and len(p) in {1, 5} for p in pins)
                     and pins[0][0] == source["database"] and pins[1][0] == source["database"] + "-wal"
                     and len(pins[0]) == 5
                     and all(type(v) is int and v >= 0 for p in pins for v in p[1:]), "parent_source_revision_invalid")
        _require(body.get("source_binding_sha256") == (_digest(_json(source).encode("utf-8")) if source is not None else None),
                 "parent_source_pin_invalid")
        plan = {"universe": body["universe"], "decision_cutoff": body["decision_cutoff"],
                "method_contracts_sha256": body["method_contracts_sha256"], "source_binding": source}
        _require(body["plan_sha256"] == _digest(_json(plan).encode("utf-8")), "parent_plan_mismatch")
        return body

    @property
    def identity_sha256(self) -> str:
        return str(self.to_dict()["capture_identity_sha256"])


class BoundedRuleResearchParentWriter(BoundedRuleResearchCaptureWriter):
    """沿用同一容量／lock／atomic envelope，僅替换 schema 與 receipt 驗證。"""
    def _decode_capture(self, raw: bytes) -> dict[str, Any]:
        return RuleResearchParentCapture(raw.decode("utf-8")).to_dict()

    def _make_receipt(self, body: dict[str, Any], raw: bytes) -> dict[str, Any]:
        return {"schema_version": PARENT_RECEIPT_SCHEMA, "status": "complete",
                "capture_identity_sha256": body["capture_identity_sha256"], "capture_sha256": _digest(raw),
                "observed_at": body["observed_at"], "research_only": True,
                "cohort_status": body["status"], "batches_count": len(body["batches"])}


def _source_binding(source: SQLiteDailyMarketSnapshotSource) -> dict[str, Any]:
    source.validate_source_stable()
    return {"mode": "query_only_transaction_main_wal_stat_pin", "database": str(source.db_path),
            "schema_identity_sha256": source.schema_identity, "revision_pin": _source_pin(source.db_path)}


def _check_source_budget(root: Path, reserve_bytes: int = 0, reserve_entries: int = 0) -> None:
    """只掃明示隔離產物；不刪除，超限拒絕下一批。"""
    _safe_path(root)
    _require(reserve_bytes <= MAX_PARENT_SOURCE_BYTES, "parent_retention_byte_limit")
    _require(reserve_entries <= 4096, "parent_retention_entry_limit")
    if not root.exists():
        return
    total = count = 0
    for path in root.rglob("*"):
        _safe_path(path)
        count += 1
        _require(count + reserve_entries <= 4096, "parent_retention_entry_limit")
        if path.is_file():
            total += path.stat().st_size
            _require(total + reserve_bytes <= MAX_PARENT_SOURCE_BYTES, "parent_retention_byte_limit")
    _require(total + reserve_bytes <= MAX_PARENT_SOURCE_BYTES, "parent_retention_byte_limit")


def _child_spec(universe: dict[str, Any], batch: dict[str, Any]) -> dict[str, Any]:
    return {**universe, "schema_version": RESEARCH_UNIVERSE_SCHEMA,
            "scope": "bounded_research_cohort", "universe_id": batch["cohort_id"],
            "included_stock_codes": batch["included_stock_codes"], "excluded_stock_codes": batch["excluded_stock_codes"],
            "population_count": len(batch["included_stock_codes"]) + len(batch["excluded_stock_codes"])}


def _plan(universe: dict[str, Any], cutoff: str, method_sha: str, source: Any) -> str:
    return _digest(_json({"universe": universe, "decision_cutoff": cutoff,
                         "method_contracts_sha256": method_sha, "source_binding": source}).encode("utf-8"))


def _batches(universe: dict[str, Any], plan: str) -> list[dict[str, Any]]:
    return [{**b, "cohort_id": f"{universe['universe_id']}:{b['batch_id']}:{plan[:12]}",
             "status": "pending", "manifest_sha256": None,
             "capture_identity_sha256": None, "production_status": "not_started",
             "sample_capture_status": "not_started", "error_code": ""} for b in _layout(universe)]


def _snapshot_repository(root: Path, body: dict[str, Any], batch: dict[str, Any]) -> DailyMarketSnapshotRepository:
    return DailyMarketSnapshotRepository(root / "batches" / body["plan_sha256"] / batch["batch_id"])


def read_parent_rule_sample_readiness(snapshot_root: str | Path, capture_root: str | Path, *, universe_path: str | Path,
                                     identity_sha256: str) -> dict[str, Any]:
    """新程序只讀 parent→receipt→完整 child pins；不開原 DB 或 latest。"""
    parent_writer = BoundedRuleResearchParentWriter(Path(capture_root) / "parents")
    package = parent_writer.read(identity_sha256)
    body = package["capture"]
    root = Path(snapshot_root).absolute()
    _safe_path(root)
    _require(str(root.resolve()) == body["snapshot_root"]
             and str(Path(capture_root).absolute().resolve()) == body["capture_root"], "parent_root_binding_mismatch")
    explicit_universe = Path(universe_path).absolute()
    _safe_path(explicit_universe)
    _require(str(explicit_universe.resolve()) == body["universe"]["source_ref"], "parent_universe_path_mismatch")
    _require(load_parent_universe(explicit_universe) == body["universe"], "parent_universe_changed")
    _require(body["method_contracts"] == method_contracts_payload()
             and body["method_contracts_sha256"] == method_contracts_sha256(), "parent_method_changed")
    child_writer = BoundedRuleResearchCaptureWriter(Path(capture_root) / "samples" / body["plan_sha256"])
    tallies: dict[str, Counter[str]] = {c["method_id"]: Counter() for c in body["method_contracts"].values()}
    covered = 0
    partial_artifact = False
    for b in body["batches"]:
        if b["status"] != "captured":
            continue
        repo = _snapshot_repository(root, body, b)
        readiness = read_saved_rule_sample_readiness(child_writer, repo,
            identity_sha256=b["capture_identity_sha256"], manifest_sha256=b["manifest_sha256"],
            cohort_id=b["cohort_id"], decision_date=date.fromisoformat(body["universe"]["value"]["as_of_date"]),
            as_of=datetime.fromisoformat(body["as_of"]))
        capture = child_writer.read(b["capture_identity_sha256"])["capture"]
        expected = _child_spec(body["universe"]["value"], b)
        actual = capture["universe"]
        _require(all(actual.get(k) == v for k, v in expected.items() if k != "schema_version"),
                 "parent_child_universe_mismatch")
        _require(capture["decision_cutoff"] == body["decision_cutoff"], "parent_child_clock_mismatch")
        source = body["source_binding"]
        expected_refs = {"database": source["database"], "schema_identity_sha256": source["schema_identity_sha256"],
                         "price": source["database"] + "#daily_prices",
                         "technical": source["database"] + "#technical_indicators"}
        _require(all(r["source_refs"] == expected_refs for r in capture["source_refs"]), "parent_child_source_mismatch")
        _require(readiness["represented_denominator"] == len(b["included_stock_codes"]) + len(b["excluded_stock_codes"]),
                 "parent_child_denominator_mismatch")
        covered += readiness["represented_denominator"]
        partial_artifact |= readiness["completeness"] != "complete_declared_cohort"
        for count in readiness["method_counts"]:
            tallies[count["method_id"]].update({k: count[k] for k in ("matched", "notmatched", "unknown", "excluded")})
    total = body["universe"]["value"]["population_count"]
    missing = total - covered
    _require(body["status"] != "complete" or missing == 0, "parent_missing_controls")
    return {"status": "saved_verified_complete" if body["status"] == "complete" else "saved_incomplete",
            "cohort_status": body["status"], "parent_identity_sha256": identity_sha256,
            "universe_id": body["universe"]["value"]["universe_id"], "version": body["universe"]["value"]["version"],
            "decision_date": body["universe"]["value"]["as_of_date"], "as_of": body["as_of"],
            "decision_cutoff": body["decision_cutoff"],
            "included_denominator": len(body["universe"]["value"]["included_stock_codes"]),
            "represented_denominator": total, "captured_member_count": covered, "uncaptured_member_count": missing,
            "population_count": total, "population_status": "declared_fixed_parent_cohort",
            "batches_count": len(body["batches"]), "batches": body["batches"],
            "method_counts": [{"method_id": m, **{s: t[s] for s in ("matched", "notmatched", "unknown", "excluded")},
                               "uncaptured": missing} for m, t in tallies.items()],
            "source_completeness": "partial_research" if partial_artifact or missing else "complete_declared_cohort",
            "source_status": body["source_status"], "error_code": body["error_code"],
            "batch_status": "bounded_parent_manifest", "max_included_per_batch": 16,
            "source_availability": "unknown", "market_calendar": "unknown", "outcome_maturity": "unknown",
            "mature_outcomes": None, **body["policy"], "receipt": package["receipt"]}


def produce_parent_rule_samples(*, db_path: str | Path, snapshot_root: str | Path,
        capture_root: str | Path, universe_path: str | Path, decision_cutoff: datetime,
        as_of: datetime | None = None, cancel_callback: Callable[[], bool] | None = None) -> dict[str, Any]:
    """明示隔離小母體，一次只處理一批；不部署排程或寫正式 DB。"""
    cancel = cancel_callback or (lambda: False)
    _clock(decision_cutoff)
    cutoff = decision_cutoff.astimezone(ZoneInfo("Asia/Taipei"))
    _require(cutoff <= datetime.now(timezone.utc), "parent_future_cutoff")
    if as_of is not None:
        _clock(as_of)
        _require(cutoff <= as_of <= datetime.now(timezone.utc), "parent_as_of_invalid")
    universe = load_parent_universe(universe_path)
    _require(universe["value"]["as_of_date"] == cutoff.date().isoformat(), "parent_date_mismatch")
    methods, method_sha = method_contracts_payload(), method_contracts_sha256()
    cutoff_text = cutoff.isoformat()
    source_binding = None
    plan = _plan(universe, cutoff_text, method_sha, source_binding)
    batches = _batches(universe["value"], plan)
    # 共用 writer 的既有隔離路徑政策；不建立 guard 目錄。
    BoundedRuleResearchCaptureWriter(Path(snapshot_root) / "guard")
    parent_writer = BoundedRuleResearchParentWriter(Path(capture_root) / "parents")
    root = Path(snapshot_root).absolute().resolve()
    capture_path = Path(capture_root).absolute().resolve()
    _require(not root.is_relative_to(capture_path) and not capture_path.is_relative_to(root), "source_output_overlap")
    _check_source_budget(root)
    _check_source_budget(capture_path)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".parent.lock"
    try:
        lock_handle = lock.open("xb")
    except FileExistsError as exc:
        raise RuleSampleCaptureError("parent_busy") from exc
    status, source_status, error = "incomplete", "unverified", ""
    active: dict[str, Any] | None = None
    try:
        with lock_handle:
            try:
                with SQLiteDailyMarketSnapshotSource(db_path, cutoff.date(), cancel_callback=cancel) as source:
                    source_binding = _source_binding(source)
                    plan = _plan(universe, cutoff_text, method_sha, source_binding)
                    batches = _batches(universe["value"], plan)
                    child_writer = BoundedRuleResearchCaptureWriter(capture_path / "samples" / plan)
                    def check() -> None:
                        _require(not cancel(), "parent_cancelled")
                        _require(load_parent_universe(universe_path) == universe, "parent_universe_changed")
                        _require(method_contracts_sha256() == method_sha and method_contracts_payload() == methods,
                                 "parent_method_changed")
                        _require(_json(_source_binding(source)) == _json(source_binding), "parent_source_changed")
                    for b in batches:
                        active = b
                        check()
                        _check_source_budget(root, 8 * 1024 * 1024 + 32 * 1024, 256)
                        path = root / "universes" / plan / (b["batch_id"] + ".json")
                        raw = _json(_child_spec(universe["value"], b)).encode("utf-8")
                        _safe_path(path)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        if path.exists():
                            _require(_read_file(path, MAX_CAPTURE_BYTES) == raw, "parent_child_config_changed")
                        else:
                            _write_file(path, raw)
                        spec = load_research_universe_spec(path)
                        def load(code: str, day: date) -> DailyMarketSnapshotInput:
                            _require(day == cutoff.date(), "parent_date_mismatch")
                            check()
                            points, technical, scope, refs = source.load(code)
                            return DailyMarketSnapshotInput(code, scope, points, technical, refs)
                        produced = DailyMarketSnapshotProducer(root / "batches" / plan / b["batch_id"]).produce(
                            cohort_id=b["cohort_id"], decision_cutoff=cutoff,
                            stock_codes=tuple(b["included_stock_codes"]), source_loader=load,
                            research_universe=spec, before_publish=check)
                        b["production_status"] = produced.status
                        b["manifest_sha256"] = produced.manifest_sha256 or None
                        if produced.status not in {"published_complete", "published_partial", "unchanged"}:
                            check()
                        _require(produced.status in {"published_complete", "published_partial", "unchanged"},
                                 produced.error_code or produced.status)
                        b["manifest_sha256"], b["status"] = produced.manifest_sha256, "snapshot_ready"
                        check()
                    actual_as_of = as_of or datetime.now(timezone.utc)
                    as_of = actual_as_of
                    for b in batches:
                        active = b
                        check()
                        _check_source_budget(capture_path, 2 * MAX_CAPTURE_BYTES)
                        repo = DailyMarketSnapshotRepository(root / "batches" / plan / b["batch_id"])
                        captured = child_writer.capture_pinned(repo, manifest_sha256=b["manifest_sha256"],
                            cohort_id=b["cohort_id"], decision_date=cutoff.date(), as_of=actual_as_of)
                        b["capture_identity_sha256"] = captured["receipt"]["capture_identity_sha256"]
                        b["sample_capture_status"] = captured["status"]
                        b["status"] = "captured"
                        check()
                    check()
                    _check_source_budget(root)
                    _check_source_budget(capture_path)
                    source_status, status = "validated_transaction", "complete"
                    as_of = actual_as_of
            except (Exception, KeyboardInterrupt) as exc:
                error = str(getattr(exc, "code", "") or ("parent_cancelled" if isinstance(exc, KeyboardInterrupt) or cancel() else type(exc).__name__))[:256]
                if "changed" in str(exc):
                    error = str(getattr(exc, "code", "") or "parent_source_changed")
                status = "cancelled" if error == "parent_cancelled" else "incomplete"
                source_status = "changed" if "changed" in error else "unverified"
                pending = active if active is not None and active["status"] != "captured" else next(
                    (b for b in batches if b["status"] != "captured"), None)
                if pending is not None:
                    if pending["production_status"] == "not_started":
                        pending["production_status"] = "interrupted_unknown"
                    if pending["manifest_sha256"] is not None:
                        pending["sample_capture_status"] = "rejected"
                    pending["status"] = "cancelled" if status == "cancelled" else "failed"
                    pending["error_code"] = error
            observed = datetime.now(timezone.utc)
            actual_as_of = as_of or observed
            body = {"schema_version": PARENT_SCHEMA, "universe": universe,
                    "method_contracts": methods, "method_contracts_sha256": method_sha,
                    "source_binding": source_binding,
                    "source_binding_sha256": _digest(_json(source_binding).encode("utf-8")) if source_binding is not None else None,
                    "plan_sha256": plan, "snapshot_root": str(root), "capture_root": str(capture_path),
                    "decision_cutoff": cutoff_text, "as_of": _clock(actual_as_of), "observed_at": _clock(observed),
                    "batches": batches, "status": status, "source_status": source_status,
                    "error_code": error, "policy": _POLICY}
            body["capture_identity_sha256"] = _parent_identity(body)
            parent = RuleResearchParentCapture(_json(body))
            def revalidate() -> RuleResearchParentCapture:
                if status == "complete":
                    _require(load_parent_universe(universe_path) == universe, "parent_universe_changed")
                    assert source_binding is not None
                    _require(not cancel(), "parent_cancelled")
                    _require(method_contracts_sha256() == method_sha, "parent_method_changed")
                    _require(_json(_source_pin(Path(source_binding["database"]))) == _json(source_binding["revision_pin"]),
                             "parent_source_changed")
                    # 每個已完成 child 的 source/receipt 再核對才發布 parent。
                    for b in batches:
                        read_saved_rule_sample_readiness(child_writer,
                            DailyMarketSnapshotRepository(root / "batches" / plan / b["batch_id"]),
                            identity_sha256=b["capture_identity_sha256"], manifest_sha256=b["manifest_sha256"],
                            cohort_id=b["cohort_id"], decision_date=cutoff.date(), as_of=actual_as_of)
                return parent
            try:
                _check_source_budget(capture_path, 2 * MAX_CAPTURE_BYTES)
                saved = parent_writer.write(parent, revalidate=revalidate)
                ready = read_parent_rule_sample_readiness(root, capture_path, universe_path=universe_path,
                                                         identity_sha256=parent.identity_sha256)
                return {"status": status, "production": batches, "parent_capture": saved,
                        "sample_capture_status": saved["status"], "sample_readiness_status": "verified", "sample_readiness": ready}
            except (Exception, KeyboardInterrupt) as exc:
                result = {"status": "incomplete", "cohort_attempt_status": status, "production": batches,
                          "sample_capture_status": "rejected", "sample_readiness_status": "rejected",
                          "error_code": str(getattr(exc, "code", "") or ("parent_cancelled" if isinstance(exc, KeyboardInterrupt) else type(exc).__name__)),
                          "parent_candidate": parent.to_dict(), "saved_verified": False}
                if "saved" in locals():
                    result["parent_capture"] = saved
                    result["sample_capture_status"] = saved["status"]
                return result
    finally:
        lock.unlink()
