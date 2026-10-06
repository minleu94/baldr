"""明示日曆／terminal／分段的離線運行邊界；不抓來源、不註冊Task。"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Protocol

from app_module.rule_research_daily_owner import load_daily_runtime
from app_module.rule_research_observation_acceptance import _QUALIFICATION, _TAIPEI, _local_time, load_observation_policy
from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter, _safe_path
from app_module.rule_research_sample_capture import _read_file
from app_module.daily_market_research_universe import _object
from app_module.research_snapshot_storage_governance import daily_writer_effective_policy


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _sha(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


@dataclass(frozen=True, slots=True)
class OfficialCalendarSnapshot:
    coverage_start: date
    coverage_end: date
    trading_dates: tuple[date, ...]
    source_identity: str
    source_sha256: str
    available_at: datetime
    formal_verified: bool = False
    provenance: str = "unknown"
    coverage_complete: bool = False


@dataclass(frozen=True, slots=True)
class UpstreamTerminal:
    job: str
    target_date: date
    status: str
    identity: str
    receipt_sha256: str
    source_binding_sha256: str
    completed_at: datetime
    provenance: str = "unknown"


@dataclass(frozen=True, slots=True)
class RuntimeSegment:
    segment_id: str
    start_date: date
    end_date: date
    runtime_path: Path
    runtime_sha256: str


@dataclass(frozen=True, slots=True)
class DailyRuntimeRequest:
    target_date: date
    decision_cutoff: datetime
    calendar: OfficialCalendarSnapshot | None
    terminals: tuple[UpstreamTerminal, ...]
    expected_jobs: tuple[str, ...]
    segments: tuple[RuntimeSegment, ...]
    coordination_root: Path
    timeout_seconds: int
    # 每個job的identity／receipt hash必須由caller明示，不信任latest。
    expected_terminal_pins: tuple[tuple[str, str, str], ...] = ()
    expected_calendar_pin: tuple[str, str] | None = None
    offline_rehearsal: bool = False


class DailyOwnerProcess(Protocol):
    def __call__(self, runtime_path: Path, target_date: date, *, execute: bool,
                 timeout_seconds: int, cancel_callback: Callable[[], bool]) -> dict[str, Any]: ...


def _owner_process(runtime_path: Path, target_date: date, *, execute: bool,
                   timeout_seconds: int, cancel_callback: Callable[[], bool]) -> dict[str, Any]:
    """每次明示啟動新子程序；stdout有界，不留下未回收的worker。"""
    script = Path(__file__).resolve().parents[1] / "scripts/scheduled/run_rule_research_daily_isolated.py"
    args = [sys.executable, str(script), "--runtime-config", str(runtime_path), "--target-date", target_date.isoformat()]
    if execute:
        args.append("--execute-isolated")
    # 暫存只承接本次stdout，不作來源／日期fallback。
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        child = subprocess.Popen(args, stdout=out, stderr=err, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic_ns() + timeout_seconds * 1_000_000_000
        terminal = None
        while child.poll() is None:
            if cancel_callback():
                terminal = "cancelled"
                break
            if time.monotonic_ns() >= deadline:
                terminal = "timeout"
                break
            if out.tell() > 2 * 1024 * 1024 or err.tell() > 64 * 1024:
                terminal = "stdout_limit"
                break
            time.sleep(0.05)
        if terminal:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        out.seek(0); err.seek(0)
        raw = out.read(2 * 1024 * 1024 + 1)
        errors = err.read(64 * 1024 + 1)
        if terminal or len(raw) > 2 * 1024 * 1024 or len(errors) > 64 * 1024:
            return {"status": terminal or "stdout_limit", "process_exit_code": child.returncode,
                    "partial_artifacts_preserved": True, "stdout_sha256": hashlib.sha256(raw).hexdigest()}
        try:
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("owner_stdout_object_required")
        except (ValueError, UnicodeError):
            return {"status": "blocked", "error_code": "owner_stdout_unverified", "process_exit_code": child.returncode}
        result["process_exit_code"] = child.returncode
        result["stdout_sha256"] = hashlib.sha256(raw).hexdigest()
        return result


def run_daily_runtime(request: DailyRuntimeRequest, *, execute: bool = False,
                      cancel_callback: Callable[[], bool] | None = None,
                      clock: Callable[[], datetime] | None = None,
                      process_runner: DailyOwnerProcess | None = None) -> dict[str, Any]:
    """預設唯讀；明示來源資格只授運行檢查，不升PIT／natural／training。"""
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    cancel = cancel_callback or (lambda: False)
    runner = process_runner or _owner_process
    result: dict[str, Any] = {"schema_version": "rule-research-daily-runtime-receipt.v1", "status": "unknown",
        "target_date": request.target_date.isoformat(), "qualification": dict(_QUALIFICATION),
        "task_registered": False, "offline_rehearsal": request.offline_rehearsal, "automatic_cleanup": False}
    def require(ok: bool, code: str) -> None:
        if not ok:
            raise ValueError(code)
    lock: Path | None = None
    owned = False
    try:
        require(_aware(now) and _aware(request.decision_cutoff), "runtime_clock_unknown")
        require(type(request.timeout_seconds) is int and 1 <= request.timeout_seconds <= 3600, "runtime_timeout_invalid")
        cal = request.calendar
        require(cal is not None, "official_calendar_unknown")
        assert cal is not None
        result["calendar_provenance"] = cal.provenance
        result["injected_sources"] = {
            "calendar": {"identity": cal.source_identity, "sha256": cal.source_sha256,
                         "available_at": cal.available_at.isoformat(), "coverage_complete": cal.coverage_complete},
            "terminals": [{"job": t.job, "identity": t.identity, "receipt_sha256": t.receipt_sha256,
                           "source_binding_sha256": t.source_binding_sha256, "target_date": t.target_date.isoformat(),
                           "completed_at": t.completed_at.isoformat(), "provenance": t.provenance} for t in request.terminals],
            "decision_cutoff": request.decision_cutoff.isoformat(),
        }
        require(cal.coverage_complete is True, "official_calendar_coverage_unknown")
        require(cal.provenance == "official_snapshot" and cal.formal_verified is True
                or request.offline_rehearsal and cal.provenance == "synthetic_offline", "official_calendar_unverified")
        require(bool(cal.source_identity) and _sha(cal.source_sha256)
                and request.expected_calendar_pin == (cal.source_identity, cal.source_sha256), "calendar_pin_mismatch")
        require(_aware(cal.available_at) and cal.available_at <= request.decision_cutoff <= now, "calendar_available_after_cutoff")
        require(cal.coverage_start <= request.target_date <= cal.coverage_end
                and len(cal.trading_dates) <= 366 and tuple(sorted(set(cal.trading_dates))) == cal.trading_dates
                and all(cal.coverage_start <= d <= cal.coverage_end for d in cal.trading_dates), "calendar_coverage_invalid")
        if request.target_date not in cal.trading_dates:
            result["status"] = "non_trading_day"
            return result
        require(1 <= len(request.expected_jobs) <= 8 and len(set(request.expected_jobs)) == len(request.expected_jobs), "upstream_jobs_invalid")
        require(len(request.terminals) == len(request.expected_jobs)
                and {t.job for t in request.terminals} == set(request.expected_jobs), "upstream_terminal_missing_or_duplicate")
        require(len(request.expected_terminal_pins) == len(request.expected_jobs)
                and {p[0] for p in request.expected_terminal_pins} == set(request.expected_jobs), "upstream_pins_missing")
        pins = {p[0]: (p[1], p[2]) for p in request.expected_terminal_pins}
        for terminal in request.terminals:
            require(terminal.target_date == request.target_date and terminal.status == "complete"
                    and bool(terminal.identity) and _sha(terminal.receipt_sha256) and _sha(terminal.source_binding_sha256)
                    and pins[terminal.job] == (terminal.identity, terminal.receipt_sha256), "upstream_terminal_date_identity_hash_mismatch")
            require(_aware(terminal.completed_at) and terminal.completed_at <= now, "upstream_terminal_future")
            require(terminal.provenance == "verified_receipt"
                    or request.offline_rehearsal and terminal.provenance == "synthetic_offline", "upstream_terminal_unverified")
        bindings = {t.source_binding_sha256 for t in request.terminals}
        require(len(bindings) == 1, "upstream_source_revision_mismatch")
        require(1 <= len(request.segments) <= 64 and len({s.segment_id for s in request.segments}) == len(request.segments), "segment_inventory_invalid")
        ordered = sorted(request.segments, key=lambda s: s.start_date)
        require(all(s.start_date <= s.end_date and bool(s.segment_id) for s in ordered)
                and all(a.end_date < b.start_date for a, b in zip(ordered, ordered[1:])), "segment_overlap")
        matches = [s for s in ordered if s.start_date <= request.target_date <= s.end_date]
        require(len(matches) == 1, "segment_unconfigured")
        segment = matches[0]
        runtime = load_daily_runtime(segment.runtime_path)
        require(_sha(segment.runtime_sha256) and runtime["source_sha256"] == segment.runtime_sha256, "segment_runtime_pin_mismatch")
        config = runtime["value"]
        result["effective_policy"] = daily_writer_effective_policy(config.get("safety_reserve_bytes"))
        result["segment_id"] = segment.segment_id
        result["runtime_source_sha256"] = runtime["source_sha256"]
        binding = next(iter(bindings))
        require(config.get("expected_source_binding_sha256") == binding, "runtime_upstream_pin_required_or_mismatch")
        policy = load_observation_policy(config["policy_config"])
        actual_cutoff = datetime.combine(request.target_date, _local_time(policy["value"]["decision_cutoff_time"]), tzinfo=_TAIPEI)
        require(actual_cutoff == request.decision_cutoff, "runtime_policy_cutoff_mismatch")
        # 所有segment共享排他root；不同segment輸出根不得互借或重用。
        coord = BoundedRuleResearchCaptureWriter(request.coordination_root).output_root
        paths: list[Path] = [coord]
        for item in ordered:
            other = load_daily_runtime(item.runtime_path)
            require(other["source_sha256"] == item.runtime_sha256, "segment_runtime_pin_mismatch")
            for role in ("snapshot_root", "capture_root", "acceptance_root", "status_root"):
                root = Path(other["value"][role]).resolve()
                require(all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in paths), "segment_roots_overlap")
                paths.append(root)
        if cancel():
            result["status"] = "cancelled"
            return result
        pre = runner(segment.runtime_path, request.target_date, execute=False,
                     timeout_seconds=request.timeout_seconds, cancel_callback=cancel)
        result["preflight"] = pre
        if pre.get("status") != "preflight_passed":
            result["status"] = pre.get("status", "blocked")
            return result
        require(pre.get("source_binding_sha256") == binding, "owner_preflight_source_pin_mismatch")
        result["status"] = "preflight_passed"
        if not execute:
            return result
        require(load_daily_runtime(segment.runtime_path) == runtime and load_observation_policy(config["policy_config"]) == policy, "runtime_changed_before_execute")
        if cancel():
            result["status"] = "cancelled"
            return result
        coord.mkdir(parents=True, exist_ok=True)
        _safe_path(coord)
        lock = coord / ".daily-runtime.lock"
        try:
            with lock.open("xb") as handle:
                handle.write(segment.segment_id.encode("utf-8"))
        except FileExistsError:
            result["status"] = "busy"
            return result
        owned = True
        child = runner(segment.runtime_path, request.target_date, execute=True,
                       timeout_seconds=request.timeout_seconds, cancel_callback=cancel)
        result["owner_result"] = child
        result["status"] = child.get("status", "blocked")
        if child.get("status") in {"observed", "already_observed"}:
            require(child.get("source_binding_sha256") == binding, "owner_terminal_source_pin_mismatch")
            require(child.get("owner_status_capture_status") in {"published", "duplicate"}, "owner_receipt_unverified")
            from app_module.rule_research_daily_owner import _OwnerStatusWriter
            receipt = child.get("owner_receipt", {}).get("receipt", {})
            identity = receipt.get("capture_identity_sha256", "")
            require(_sha(identity), "owner_receipt_identity_missing")
            saved = _OwnerStatusWriter(config["status_root"]).read(identity)["capture"]
            require(saved.get("source_binding_sha256") == binding and saved.get("status") == child["status"]
                    and saved.get("qualification") == dict(_QUALIFICATION), "owner_saved_receipt_mismatch")
            require(child.get("process_exit_code", 0) == 0, "owner_process_exit_mismatch")
        require(load_daily_runtime(segment.runtime_path) == runtime and load_observation_policy(config["policy_config"]) == policy, "runtime_changed_during_execute")
    except (ValueError, OSError, TypeError) as exc:
        result.update(status="blocked", error_code=str(exc))
    finally:
        if owned and lock is not None:
            lock.unlink()  # 僅釋放本程序合作lock；不清理segment、partial或source。
        result["receipt_identity_sha256"] = _hash(result)
    return result


def offline_task_review(request: DailyRuntimeRequest) -> dict[str, Any]:
    """只生成可審核配置；此函式不註冊、啟用或改帳號／ACL。"""
    return {"schema_version": "rule-research-offline-task-review.v1", "task_registered": False,
            "enabled": False, "execution_environment": "isolated_research",
            "request": json.loads(json.dumps(asdict(request), default=str)),
            "stdout_contract": "rule-research-daily-runtime-receipt.v1",
            "timeout_seconds": request.timeout_seconds, "account": "unconfigured", "acl": "unconfigured",
            "requires_explicit_approval": ["Task registration", "account", "ACL", "formal source/output roots"]}


def load_runtime_request(path: str | Path) -> DailyRuntimeRequest:
    """明示v1 request codec；不推斷日期、來源hash或正式資格。"""
    value = json.loads(_read_file(Path(path), 256*1024), object_pairs_hook=_object)
    if not isinstance(value, dict) or value.pop("schema_version", None) != "rule-research-daily-runtime-request.v1":
        raise ValueError("runtime_request_schema_invalid")
    required = set(DailyRuntimeRequest.__dataclass_fields__)
    if set(value) != required:
        raise ValueError("runtime_request_fields_invalid")
    for flag in ("offline_rehearsal",):
        if type(value[flag]) is not bool:
            raise ValueError("runtime_request_flag_invalid")
    raw_calendar = value["calendar"]
    calendar = None
    if raw_calendar is not None:
        if set(raw_calendar) != set(OfficialCalendarSnapshot.__dataclass_fields__) or any(type(raw_calendar[k]) is not bool for k in ("formal_verified", "coverage_complete")):
            raise ValueError("runtime_calendar_fields_invalid")
        calendar = OfficialCalendarSnapshot(**{**raw_calendar,
            "coverage_start": date.fromisoformat(raw_calendar["coverage_start"]),
            "coverage_end": date.fromisoformat(raw_calendar["coverage_end"]),
            "trading_dates": tuple(date.fromisoformat(d) for d in raw_calendar["trading_dates"]),
            "available_at": datetime.fromisoformat(raw_calendar["available_at"])})
    terminals = tuple(UpstreamTerminal(**{**t, "target_date": date.fromisoformat(t["target_date"]),
                      "completed_at": datetime.fromisoformat(t["completed_at"])}) for t in value["terminals"])
    segments = tuple(RuntimeSegment(**{**s, "start_date": date.fromisoformat(s["start_date"]),
                     "end_date": date.fromisoformat(s["end_date"]), "runtime_path": Path(s["runtime_path"])}) for s in value["segments"])
    return DailyRuntimeRequest(**{**value, "target_date": date.fromisoformat(value["target_date"]),
        "decision_cutoff": datetime.fromisoformat(value["decision_cutoff"]), "calendar": calendar,
        "terminals": terminals, "segments": segments, "coordination_root": Path(value["coordination_root"]),
        "expected_jobs": tuple(value["expected_jobs"]),
        "expected_terminal_pins": tuple(tuple(p) for p in value["expected_terminal_pins"]),
        "expected_calendar_pin": tuple(value["expected_calendar_pin"]) if value["expected_calendar_pin"] is not None else None})
