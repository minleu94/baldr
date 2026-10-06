"""明示配置的隔離每日MA owner；重用producer/parent/接受，無正式Task。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import json
import shutil
import time
from typing import Any, Callable
from data_module.ml_storage_capacity import resolve_heavy_chain_safety_reserve

from app_module.daily_market_research_universe import _object
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
from app_module.daily_market_snapshot_producer import _MAX_NEW_BYTES_PER_RUN
from app_module.rule_research_parent_capture import (
    MAX_PARENT_SOURCE_BYTES, _check_source_budget, _source_binding, _layout,
    load_parent_universe, produce_parent_rule_samples,
)
from app_module.rule_research_observation_acceptance import (
    _QUALIFICATION, _TAIPEI, _local_time, _parent, _universe_definition,
    load_observation_policy, preview_or_accept_observation, read_observation_days,
)
from app_module.rule_research_sample_capture import (
    MAX_CAPTURE_BYTES, SAFETY_RESERVE_BYTES, BoundedRuleResearchCaptureWriter,
    _digest, _identity, _json, _read_file, _require, _safe_path,
)

RUNTIME_SCHEMA = "rule-research-daily-owner-runtime.v1"
_FIELDS = {"schema_version", "mode", "date_source", "policy_config", "source_db", "snapshot_root",
           "capture_root", "acceptance_root", "status_root", "per_root_quota_bytes",
           "max_attempts", "retry_delay_seconds", "parent_universe_configs"}
_ROOTS = ("snapshot_root", "capture_root", "acceptance_root", "status_root")
_OPTIONAL_FIELDS = {"safety_reserve_bytes", "expected_source_binding_sha256", "timeout_seconds"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _free_bytes(path: Path) -> int:
    ancestor = path
    while not ancestor.exists():
        ancestor = ancestor.parent
    return shutil.disk_usage(ancestor).free


def load_daily_runtime(path: str | Path) -> dict[str, Any]:
    source = Path(path).absolute()
    raw = _read_file(source, 64 * 1024)
    value = json.loads(raw, object_pairs_hook=_object)
    _require(isinstance(value, dict), "daily_runtime_object_required")
    missing = sorted(_FIELDS - value.keys())
    _require(not missing, "daily_runtime_unconfigured:" + ",".join(missing))
    _require(not (set(value) - _FIELDS - _OPTIONAL_FIELDS) and value["schema_version"] == RUNTIME_SCHEMA
             and value["mode"] == "isolated_research" and value["date_source"] == "explicit_policy_dates",
             "daily_runtime_scope_invalid")
    if "safety_reserve_bytes" in value:
        resolve_heavy_chain_safety_reserve(value["safety_reserve_bytes"])
    if "expected_source_binding_sha256" in value:
        pin = value["expected_source_binding_sha256"]
        _require(isinstance(pin, str) and len(pin) == 64 and all(x in "0123456789abcdef" for x in pin), "daily_upstream_pin_invalid")
    if "timeout_seconds" in value:
        _require(type(value["timeout_seconds"]) is int and 1 <= value["timeout_seconds"] <= 3600, "daily_timeout_invalid")
    for key in (*_ROOTS, "policy_config", "source_db"):
        _require(isinstance(value[key], str) and Path(value[key]).is_absolute(), "daily_runtime_unconfigured:" + key)
        _safe_path(Path(value[key]))
    _require(type(value["per_root_quota_bytes"]) is int and 1 <= value["per_root_quota_bytes"] <= MAX_PARENT_SOURCE_BYTES,
             "daily_quota_unconfigured_or_invalid")
    _require(type(value["max_attempts"]) is int and 1 <= value["max_attempts"] <= 3
             and type(value["retry_delay_seconds"]) is int and 0 <= value["retry_delay_seconds"] <= 5, "daily_retry_unconfigured_or_invalid")
    mapping = value["parent_universe_configs"]
    _require(isinstance(mapping, dict) and 1 <= len(mapping) <= 31
             and all(isinstance(d, str) and date.fromisoformat(d).isoformat() == d
                     and isinstance(p, str) and Path(p).is_absolute() for d,p in mapping.items()), "daily_date_sources_unconfigured")
    roots = [BoundedRuleResearchCaptureWriter(value[k]).output_root for k in _ROOTS]
    for i, root in enumerate(roots):
        _require(all(not root.is_relative_to(other) and not other.is_relative_to(root) for other in roots[i+1:]), "daily_roots_overlap")
    # 執行限定小型隔離source；不接受正式市場DB或依DATA_ROOT自動選值。
    BoundedRuleResearchCaptureWriter(Path(value["source_db"]).parent / "guard")
    sources = [source, Path(value["source_db"]), Path(value["policy_config"]), *map(Path,mapping.values())]
    policy_fields = json.loads(_read_file(Path(value["policy_config"]),64*1024),object_pairs_hook=_object)
    required_policy_fields = ("decision_cutoff_time","observation_start_time","observation_end_time","expected_observation_dates")
    _require(isinstance(policy_fields,dict),"daily_runtime_unconfigured:policy")
    missing_policy = [k for k in required_policy_fields if not policy_fields.get(k)]
    _require(not missing_policy,"daily_runtime_unconfigured:policy."+",".join(missing_policy))
    template = load_observation_policy(value["policy_config"])["universe_template"]["source_ref"]
    sources.append(Path(template))
    for p in sources:
        _safe_path(p)
        _require(all(not p.resolve().is_relative_to(r) for r in roots), "daily_source_output_overlap")
    return {"value": value, "source_ref": str(source.resolve()), "source_sha256": _digest(raw)}


def _capacity(config: dict[str, Any], batches: int) -> dict[str, Any]:
    quota = config["per_root_quota_bytes"]
    budgets = []
    # 保守地合計四根的最大新留存與工作空間，即使跨volume仍不放寬reserve。
    effective = max(SAFETY_RESERVE_BYTES, resolve_heavy_chain_safety_reserve(config.get("safety_reserve_bytes")))
    required = effective + 2 * quota * len(_ROOTS)
    projected = {"snapshot_root": batches * _MAX_NEW_BYTES_PER_RUN + (MAX_CAPTURE_BYTES if batches else 0),
                 "capture_root": (batches+1)*2*MAX_CAPTURE_BYTES if batches else 0,
                 "acceptance_root": 2*MAX_CAPTURE_BYTES if batches else 0,
                 "status_root": 2*MAX_CAPTURE_BYTES}
    for name in _ROOTS:
        root = BoundedRuleResearchCaptureWriter(config[name]).output_root
        _check_source_budget(root)
        retained = 0
        if root.exists():
            retained = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        _require(retained + projected[name] <= quota, "daily_quota_exhausted:" + name)
        free = _free_bytes(root)
        _require(type(free) is int and free >= 0, "daily_capacity_unknown:" + name)
        _require(free >= required, "daily_capacity_reserve:" + name)
        budgets.append({"root_role": name, "free_bytes": free, "retained_bytes": retained, "quota_bytes": quota,
                        "projected_new_bytes": projected[name]})
    return {"status": "passed", "effective_reserve_bytes": effective, "required_free_bytes": required, "roots": budgets}


@dataclass(frozen=True, slots=True)
class _OwnerStatus:
    body_json: str

    def to_dict(self) -> dict[str, Any]:
        body = json.loads(self.body_json)
        _require(len(self.body_json.encode("utf-8")) <= MAX_CAPTURE_BYTES
                 and _json(body) == self.body_json and body.get("schema_version") == "rule-research-daily-owner-status.v1"
                 and body.get("qualification") == _QUALIFICATION and len(body.get("attempts", [])) <= 3
                 and body.get("capture_identity_sha256") == _identity(body), "daily_status_invalid")
        return body

    @property
    def identity_sha256(self) -> str:
        return str(self.to_dict()["capture_identity_sha256"])


class _OwnerStatusWriter(BoundedRuleResearchCaptureWriter):
    def _decode_capture(self, raw: bytes) -> dict[str, Any]:
        return _OwnerStatus(raw.decode("utf-8")).to_dict()

    def _make_receipt(self, body: dict[str, Any], raw: bytes) -> dict[str, Any]:
        return {"schema_version": "rule-research-daily-owner-receipt.v1", "status": "complete",
                "capture_identity_sha256": body["capture_identity_sha256"], "capture_sha256": _digest(raw),
                "observed_at": body["observed_at"], "research_only": True, "owner_status": body["status"]}


def run_daily_owner(runtime_path: str | Path | None, target_date: date | None, *, execute: bool = False,
                    cancel_callback: Callable[[], bool] | None = None) -> dict[str, Any]:
    user_cancel = cancel_callback or (lambda: False)
    deadline: int | None = None
    def cancel() -> bool:
        return user_cancel() or (deadline is not None and time.monotonic_ns() >= deadline)
    result: dict[str, Any] = {"schema_version": "rule-research-daily-owner-status.v1", "status": "unconfigured",
        "target_date": target_date.isoformat() if target_date else None, "attempts": [], "qualification": dict(_QUALIFICATION),
        "observed_at": _now().isoformat(), "owner_status_capture_status": "not_written"}
    if runtime_path is None or target_date is None:
        result["error_code"] = "runtime_config_and_explicit_target_date_required"
        return result
    runtime = None
    lock = None
    owned_lock = False
    try:
        runtime = load_daily_runtime(runtime_path)
        c = runtime["value"]
        if "timeout_seconds" in c:
            deadline = time.monotonic_ns() + c["timeout_seconds"] * 1_000_000_000
        from app_module.research_snapshot_storage_governance import daily_writer_effective_policy
        result["effective_policy"] = daily_writer_effective_policy(c.get("safety_reserve_bytes"))
        result["runtime_source_sha256"] = runtime["source_sha256"]
        policy = load_observation_policy(c["policy_config"])
        config = policy["value"]
        day = target_date.isoformat()
        _require(day in config["expected_observation_dates"], "daily_target_not_expected")
        _require(day in c["parent_universe_configs"], "daily_runtime_unconfigured:target_parent_source")
        universe_path = c["parent_universe_configs"][day]
        universe = load_parent_universe(universe_path)
        batch_count = len(_layout(universe["value"]))
        _require(universe["value"]["as_of_date"] == day
                 and _universe_definition(universe["value"]) == _universe_definition(policy["universe_template"]["value"]), "daily_target_universe_mismatch")
        current = _now()
        start = datetime.combine(target_date,_local_time(config["observation_start_time"]),tzinfo=_TAIPEI)
        end = datetime.combine(target_date,_local_time(config["observation_end_time"]),tzinfo=_TAIPEI)
        cutoff = datetime.combine(target_date,_local_time(config["decision_cutoff_time"]),tzinfo=_TAIPEI)
        result["decision_cutoff"] = cutoff.isoformat()
        result["day_readiness"] = read_observation_days(c["policy_config"],c["acceptance_root"],evaluated_at=current)
        if current < start or current > end:
            result["status"] = "not_due" if current < start else "missed_window"
            return result
        result["capacity_preflight"] = _capacity(c,batch_count)
        _require(load_daily_runtime(runtime_path) == runtime, "daily_runtime_changed")
        _require(load_observation_policy(c["policy_config"]) == policy, "daily_policy_changed")
        # 只查指定日與來源revision，不借scheduled_today/Pacific或latest。
        with SQLiteDailyMarketSnapshotSource(c["source_db"], target_date) as source:
            binding = _source_binding(source)
            source.validate_source_stable()
        result["source_binding_sha256"] = _digest(_json(binding).encode("utf-8"))
        _require(c.get("expected_source_binding_sha256", result["source_binding_sha256"]) == result["source_binding_sha256"], "daily_upstream_source_binding_mismatch")
        if not execute:
            result["status"] = "preflight_passed"
            return result
        status_root = Path(c["status_root"])
        status_root.mkdir(parents=True,exist_ok=True)
        _safe_path(status_root)
        lock = status_root / ".owner.lock"
        try:
            handle = lock.open("xb")
        except FileExistsError:
            result.update(status="busy",error_code="daily_owner_busy")
            return result
        owned_lock = True
        handle.close()
        for attempt in range(1,c["max_attempts"]+1):
            if cancel():
                result["status"] = "cancelled"
                break
            _require(start <= _now() <= end, "daily_window_closed_during_retry")
            _require(load_daily_runtime(runtime_path) == runtime and load_observation_policy(c["policy_config"]) == policy,
                     "daily_config_changed")
            result["capacity_preflight"] = _capacity(c,batch_count)
            with SQLiteDailyMarketSnapshotSource(c["source_db"],target_date) as source:
                binding_sha = _digest(_json(_source_binding(source)).encode("utf-8"))
                source.validate_source_stable()
            _require(binding_sha == result["source_binding_sha256"], "daily_source_revision_changed")
            prior = read_observation_days(c["policy_config"],c["acceptance_root"],evaluated_at=_now())
            candidates = []
            for d in prior["days"]:
                if d["decision_date"] != day:
                    continue
                for record in d["records"]:
                    if not record["saved_verified"] or not record["visible_at_evaluation"] or record["source_binding_sha256"] != binding_sha:
                        continue
                    path = Path(c["capture_root"]) / "parents" / record["parent_identity_sha256"] / "receipt.json"
                    if not path.exists():
                        continue
                    body, _, _ = _parent(path)
                    if body["snapshot_root"] == str(Path(c["snapshot_root"]).resolve()) and body["universe"]["source_ref"] == str(Path(universe_path).resolve()):
                        candidates.append((record,path,body))
            accepted = [x for x in candidates if x[0]["acceptance_status"] == "accepted_research_observation"]
            _require(len(accepted) <= 1, "daily_saved_observation_ambiguous")
            if accepted:
                with SQLiteDailyMarketSnapshotSource(c["source_db"],target_date) as source:
                    _require(_digest(_json(_source_binding(source)).encode("utf-8")) == binding_sha, "daily_source_revision_changed_during_reuse")
                    source.validate_source_stable()
                result.update(status="already_observed",day_readiness=prior,execution_disposition="reused_exact_source_receipt")
                break
            fixed_as_of = None
            _require(len(candidates) <= 1, "daily_retry_receipt_ambiguous")
            if candidates:
                fixed_as_of = datetime.fromisoformat(candidates[0][2]["as_of"])
            summary: dict[str, Any] = {"attempt": attempt, "production_status": "not_started",
                                       "sample_capture_status": "not_started", "acceptance_capture_status": "not_started"}
            result["attempts"].append(summary)
            try:
                produced = produce_parent_rule_samples(db_path=c["source_db"],snapshot_root=c["snapshot_root"],
                    capture_root=c["capture_root"],universe_path=universe_path,decision_cutoff=cutoff,
                    as_of=fixed_as_of,cancel_callback=cancel)
                summary.update(production_status=produced["status"], sample_capture_status=produced["sample_capture_status"],
                    batches=produced["production"], parent_capture=produced.get("parent_capture"), error_code=produced.get("error_code",""))
                package = produced.get("parent_capture")
                if package and package.get("receipt"):
                    path = Path(c["capture_root"])/"parents"/package["receipt"]["capture_identity_sha256"]/"receipt.json"
                    pinned_parent, _, _ = _parent(path)
                    _require(pinned_parent["universe"] == universe, "daily_parent_universe_changed")
                    _require(load_daily_runtime(runtime_path) == runtime and load_observation_policy(c["policy_config"]) == policy,
                             "daily_config_changed_before_acceptance")
                    _require(pinned_parent["source_binding_sha256"] == binding_sha, "daily_producer_revision_mismatch")
                    with SQLiteDailyMarketSnapshotSource(c["source_db"],target_date) as source:
                        _require(_digest(_json(_source_binding(source)).encode("utf-8")) == binding_sha, "daily_source_revision_changed")
                        source.validate_source_stable()
                    accepted_result = preview_or_accept_observation(c["policy_config"],path,c["acceptance_root"],accept=True,evaluated_at=_now())
                    summary.update(acceptance_capture_status=accepted_result["acceptance_capture_status"],
                        acceptance=accepted_result.get("acceptance"), acceptance_status=accepted_result["candidate"]["acceptance_status"],
                        day_readiness_status=accepted_result["day_readiness_status"])
                    if accepted_result.get("day_readiness"):
                        result["day_readiness"] = accepted_result["day_readiness"]
                    if accepted_result["candidate"]["acceptance_status"] == "accepted_research_observation" and accepted_result["day_readiness_status"] == "verified":
                        with SQLiteDailyMarketSnapshotSource(c["source_db"],target_date) as source:
                            _require(_digest(_json(_source_binding(source)).encode("utf-8")) == binding_sha, "daily_source_revision_changed_after_acceptance")
                            source.validate_source_stable()
                        result["status"] = "observed"
                        break
                result["status"] = "cancelled" if cancel() else "incomplete"
            except Exception as exc:
                summary["error_code"] = str(exc)
                summary["acceptance_capture_status"] = "rejected_or_unverified"
                result["status"] = "failed"
            if cancel():
                result["status"] = "cancelled"
                break
            if attempt < c["max_attempts"]:
                # 有界合作式退避，不清理partial、不掩蓋新revision。
                for _ in range(c["retry_delay_seconds"]*10):
                    if cancel():
                        break
                    time.sleep(0.1)
        _require(load_daily_runtime(runtime_path) == runtime and load_observation_policy(c["policy_config"]) == policy
                 and load_parent_universe(universe_path) == universe, "daily_config_changed")
    except Exception as exc:
        code = str(exc)
        result.update(status="unconfigured" if "unconfigured" in code else "capacity_blocked" if "capacity" in code or "quota" in code else "blocked",error_code=code)
    finally:
        if owned_lock and lock is not None:
            lock.unlink()  # 僅本次持有的合作lock；不刪任何收據或partial。
    if deadline is not None and time.monotonic_ns() >= deadline:
        result.update(status="timeout", error_code="daily_owner_timeout", partial_artifacts_preserved=True)
    if execute and runtime is not None and result["status"] not in {"capacity_blocked","unconfigured","busy"}:
        try:
            c = runtime["value"]
            _capacity(c,0)
            body = {**result,"owner_status_capture_status":"saved","observed_at":_now().isoformat()}
            body["capture_identity_sha256"] = _identity(body)
            capture = _OwnerStatus(_json(body))
            saved = _OwnerStatusWriter(c["status_root"]).write(capture,revalidate=lambda: capture)
            result.update(owner_status_capture_status=saved["status"],owner_receipt=saved)
        except Exception as exc:
            result.update(owner_status_capture_status="rejected_or_unverified",owner_status_error=str(exc))
    return result
