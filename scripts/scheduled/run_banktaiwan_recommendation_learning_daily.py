"""每日臺銀成本研究 lane 的受控排程接線。

此入口只重用已由既有 05:10 recommendation snapshot 與 05:45 source
custody 建立的唯讀輸入，並把 calibration learning child 寫入獨立的
BankTaiwan shadow root。它不重跑 technical／official／snapshot producer，
不寫正式 SQLite、Recommendation、Portfolio、Formal 或 broker state。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from typing import Any, Callable, Literal, Mapping
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.recommendation_learning_paths import (
    DEFAULT_DATA_ROOT,
    resolve_recommendation_learning_output_root,
)
from data_module.official_trading_calendar import OfficialTradingCalendar
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    build_banktaiwan_cost_scenario,
)


TAIPEI = ZoneInfo("Asia/Taipei")
TASK_NAME = "baldr-recommendation-calibration-learning-banktaiwan-shadow-daily"
SCHEDULER_LOCAL_TIME = "05:50"
SCHEDULER_TIMEZONE = "Pacific Standard Time"
DEFAULT_LANE_DIRNAME = "FA_Data_Shadow_BankTaiwan"
DEFAULT_SOURCE_DIRNAME = "FA_Data_Shadow"
DEFAULT_RESEARCH_ORDER_QUANTITY_SHARES = 1000
DEFAULT_POLICY_ESTIMATE_DATE = "2026-01-01"
DEFAULT_CALENDAR_CACHE_ROOT = (
    ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
)
OPERATION_SCHEMA_VERSION = "banktaiwan-recommendation-learning-operational.v1"
_MAX_SNAPSHOT_STATUS_BYTES = 8 * 1024 * 1024

_REUSABLE_TERMINAL_STATUSES = frozenset(
    {
        "completed_shadow",
        "completed_waiting_natural_maturity",
        "completed_with_advisories",
        "skipped_non_trading_day",
    }
)


class OperationalLaneError(ValueError):
    """操作 lane 的 path／輸入契約錯誤。"""


class OperationalOverlapError(RuntimeError):
    """另一個相同 lane 的 process 已持有執行鎖。"""


@dataclass(frozen=True)
class OperationalPaths:
    """每日 task 的所有輸出與唯讀輸入路徑。"""

    data_root: Path
    lane_output_root: Path
    lane_learning_root: Path
    operational_root: Path
    latest_status_path: Path
    runs_root: Path
    logs_root: Path
    lock_path: Path
    snapshot_output_root: Path
    source_artifact_root: Path
    source_db: Path


@dataclass(frozen=True)
class SnapshotSummary:
    """已驗證同次 canonical snapshot 與 pipeline invocation 的唯讀摘要。"""

    path: Path
    payload: Mapping[str, Any]
    symbols: tuple[str, ...]
    cohort: Mapping[str, Any]
    file_sha256: str
    status_path: Path
    status_payload: Mapping[str, Any]
    pipeline_run_id: str
    pipeline_status_path: Path
    pipeline_status_payload: Mapping[str, Any]
    result_id: str
    payload_hash: str
    canonical_artifact_sha256: str
    schema_version: str
    schema_revision: int
    integrity_basis: str
    decision_date: str
    data_as_of_date: str
    decision_at: str
    available_at: str | None
    cohort_hash: str
    invocation_output_path: Path
    invocation_output_sha256: str
    invocation_output_size: int


def _official_calendar(source_db: Path) -> OfficialTradingCalendar:
    configured = os.environ.get("FORMAL_DAILY_CALENDAR_CACHE_ROOT")
    cache_root = (
        Path(configured).expanduser().resolve()
        if isinstance(configured, str) and configured.strip()
        else DEFAULT_CALENDAR_CACHE_ROOT.resolve()
    )
    return OfficialTradingCalendar(
        db_path=source_db,
        calendar_cache_path=cache_root,
        temporary_closure_path=cache_root,
    )


ChildRunner = Callable[
    [OperationalPaths, date, RecommendationCostScenario, argparse.Namespace],
    Mapping[str, Any],
]


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_bounded_snapshot_status(
    path: Path,
    *,
    root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """只從錨定輸出根讀取小型、穩定且非連結的狀態 JSON。"""

    from app_module.recommendation.queries import (
        ExecutionArtifactIntegrityError,
        _read_regular_file_no_follow,
    )

    try:
        path.lstat()
    except FileNotFoundError:
        return None, "missing_or_invalid"
    except OSError:
        return None, "unreadable_or_unsafe"
    try:
        raw = _read_regular_file_no_follow(
            path,
            root,
            max_bytes=_MAX_SNAPSHOT_STATUS_BYTES,
        )
    except (ExecutionArtifactIntegrityError, OSError):
        return None, "unreadable_or_unsafe"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None, "missing_or_invalid"
    if not isinstance(payload, dict):
        return None, "missing_or_invalid"
    return payload, None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _hash_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _hash_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return "sha256:" + digest.hexdigest()


def _tail(value: object, limit: int = 8000) -> str:
    text = str(value or "")
    return text[-limit:] if len(text) > limit else text


def _subprocess_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _default_data_root() -> Path:
    return Path(os.environ.get("DATA_ROOT", str(DEFAULT_DATA_ROOT))).expanduser().resolve()


def resolve_operational_paths(
    *,
    data_root: str | Path | None = None,
    lane_output_root: str | Path | None = None,
    snapshot_output_root: str | Path | None = None,
    source_artifact_root: str | Path | None = None,
    source_db: str | Path | None = None,
) -> OperationalPaths:
    """解析隔離 lane，並拒絕與 formal／legacy root 重疊。"""

    formal_root = Path(data_root or _default_data_root()).expanduser().resolve()
    raw_lane = lane_output_root or os.environ.get(
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT"
    )
    lane_root = Path(raw_lane).expanduser().resolve() if raw_lane else (
        formal_root.parent / DEFAULT_LANE_DIRNAME
    ).resolve()
    try:
        lane_root = resolve_recommendation_learning_output_root(
            data_root=formal_root,
            explicit_output_root=lane_root,
        )
    except ValueError as exc:
        raise OperationalLaneError(str(exc)) from exc

    raw_source = source_artifact_root or os.environ.get(
        "BANKTAIWAN_SOURCE_ARTIFACT_ROOT"
    )
    if raw_source:
        source_root = Path(raw_source).expanduser().resolve()
    else:
        # This is the resolver's canonical sibling legacy root, not a
        # hard-coded machine path.  The caller still requires it to exist.
        source_root = (
            formal_root.parent / DEFAULT_SOURCE_DIRNAME
        ).resolve()
    if (
        source_root == lane_root
        or source_root in lane_root.parents
        or lane_root in source_root.parents
    ):
        raise OperationalLaneError(
            "BankTaiwan source artifact root and lane output root must be disjoint; "
            f"source={source_root}; lane={lane_root}"
        )

    snapshot_root = Path(
        snapshot_output_root
        or os.environ.get("BANKTAIWAN_SNAPSHOT_OUTPUT_ROOT")
        or os.environ.get("OUTPUT_ROOT")
        or formal_root / "output"
    ).expanduser().resolve()
    database = Path(
        source_db
        or os.environ.get("BANKTAIWAN_SOURCE_DB")
        or os.environ.get("DB_PATH")
        or formal_root / "sqlite" / "twstock.db"
    ).expanduser().resolve()
    learning_root = lane_root / "recommendation_learning"
    operational_root = lane_root / "scheduled" / "recommendation_learning_banktaiwan"
    return OperationalPaths(
        data_root=formal_root,
        lane_output_root=lane_root,
        lane_learning_root=learning_root,
        operational_root=operational_root,
        latest_status_path=operational_root / "latest_status.json",
        runs_root=operational_root / "runs",
        logs_root=operational_root / "logs",
        lock_path=operational_root / "run.lock",
        snapshot_output_root=snapshot_root,
        source_artifact_root=source_root,
        source_db=database,
    )


def load_same_day_snapshot(
    *,
    output_root: str | Path,
    decision_date: date,
) -> tuple[SnapshotSummary | None, str | None]:
    """以兩個 latest-status 指標精確讀取同次 canonical snapshot。"""

    root = Path(output_root).expanduser().resolve()
    status_path = root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    status_payload, status_read_error = _read_bounded_snapshot_status(
        status_path,
        root=root,
    )
    if status_payload is None:
        suffix = status_read_error or "missing_or_invalid"
        return None, f"recommendation_snapshot_status_{suffix}"
    acceptable_statuses = {"passed", "passed_with_warnings", "warning", "degraded"}
    if status_payload.get("task") != "baldr-recommendation-snapshot-daily":
        return None, "recommendation_snapshot_status_task_mismatch"
    if type(status_payload.get("status")) is not str or status_payload.get(
        "status"
    ) not in acceptable_statuses:
        return None, "recommendation_snapshot_status_not_eligible"
    expected_date = decision_date.isoformat()
    if status_payload.get("decision_date") != expected_date:
        return None, "recommendation_snapshot_status_decision_date_mismatch"
    if not _same_resolved_path(status_payload.get("output_root"), root):
        return None, "recommendation_snapshot_status_output_root_mismatch"
    result_id = status_payload.get("result_id")
    if type(result_id) is not str or not result_id or result_id.strip() != result_id:
        return None, "recommendation_snapshot_status_result_id_missing_or_invalid"
    status_cohort_value = status_payload.get("snapshot_cohort")
    if not isinstance(status_cohort_value, Mapping):
        return None, "recommendation_snapshot_status_cohort_missing_or_invalid"
    status_cohort = dict(status_cohort_value)
    cohort_hash = status_cohort.get("cohort_hash")
    if not isinstance(cohort_hash, str) or not _is_sha256_text(cohort_hash):
        return None, "recommendation_snapshot_status_cohort_hash_missing_or_invalid"

    pipeline_status_path = (
        root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_status.json"
    )
    pipeline_status_payload, pipeline_status_read_error = (
        _read_bounded_snapshot_status(pipeline_status_path, root=root)
    )
    if pipeline_status_payload is None:
        suffix = pipeline_status_read_error or "missing_or_invalid"
        return None, f"recommendation_pipeline_status_{suffix}"
    if pipeline_status_payload.get("task") != "baldr-recommendation-calibration-learning-daily":
        return None, "recommendation_pipeline_status_task_mismatch"
    if pipeline_status_payload.get("decision_date") != expected_date:
        return None, "recommendation_pipeline_status_decision_date_mismatch"
    if not _same_resolved_path(pipeline_status_payload.get("output_root"), root):
        return None, "recommendation_pipeline_status_output_root_mismatch"
    pipeline_run_id = pipeline_status_payload.get("run_id")
    if (
        type(pipeline_run_id) is not str
        or not pipeline_run_id
        or pipeline_run_id in {".", ".."}
        or Path(pipeline_run_id).name != pipeline_run_id
        or any(separator in pipeline_run_id for separator in ("/", "\\"))
    ):
        return None, "recommendation_pipeline_run_id_missing_or_invalid"
    steps_value = pipeline_status_payload.get("steps")
    steps = steps_value if isinstance(steps_value, Mapping) else {}
    snapshot_step_value = steps.get("recommendation_snapshot")
    if not isinstance(snapshot_step_value, Mapping):
        return None, "recommendation_pipeline_snapshot_step_missing_or_invalid"
    snapshot_step = snapshot_step_value
    if (
        type(snapshot_step.get("status")) is not str
        or snapshot_step.get("status") not in acceptable_statuses
        or type(snapshot_step.get("returncode")) is not int
        or snapshot_step.get("returncode") != 0
        or snapshot_step.get("child_receipt_error") is not None
    ):
        return None, "recommendation_pipeline_snapshot_step_not_successful"
    invocation_payload_value = snapshot_step.get("child_status")
    if not isinstance(invocation_payload_value, Mapping):
        return None, "recommendation_pipeline_snapshot_child_status_missing_or_invalid"
    invocation_payload = dict(invocation_payload_value)
    if (
        type(invocation_payload.get("status")) is not str
        or invocation_payload.get("status") not in acceptable_statuses
        or invocation_payload.get("decision_date") != expected_date
        or not _same_resolved_path(invocation_payload.get("output_root"), root)
        or invocation_payload.get("result_id") != result_id
        or invocation_payload.get("snapshot_cohort") != status_cohort
    ):
        return None, "recommendation_pipeline_snapshot_identity_mismatch"

    invocation_output_path_value = snapshot_step.get("child_stdout_artifact_path")
    invocation_output_sha256 = snapshot_step.get("child_stdout_sha256")
    invocation_output_size = snapshot_step.get("child_stdout_artifact_size")
    if (
        type(invocation_output_path_value) is not str
        or not invocation_output_path_value.strip()
        or not isinstance(invocation_output_sha256, str)
        or not _is_sha256_text(invocation_output_sha256)
        or type(invocation_output_size) is not int
        or invocation_output_size <= 0
    ):
        return None, "recommendation_pipeline_snapshot_stdout_binding_missing_or_invalid"
    invocation_output_path = Path(invocation_output_path_value).expanduser()
    expected_invocation_output_path = (
        root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
        / pipeline_run_id
        / "recommendation_snapshot.stdout.bin"
    )
    if not _same_resolved_path(invocation_output_path_value, expected_invocation_output_path):
        return None, "recommendation_pipeline_snapshot_stdout_path_mismatch"

    try:
        # 重用 learning CLI 的嚴格同次綁定，讓原始 stdout、canonical index、
        # artifact bytes、typed execution、cohort 與日期沿用同一套 fail-closed 契約。
        from scripts.scheduled.run_daily_recommendation_learning import (
            _resolve_same_run_snapshot_input,
        )

        symbols, canonical_cohort, binding = _resolve_same_run_snapshot_input(
            output_root=root,
            decision_date=decision_date,
            result_id=result_id,
            expected_cohort_hash=cohort_hash,
            expected_invocation_output_sha256=invocation_output_sha256,
            invocation_output_path=str(invocation_output_path),
        )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        return None, f"recommendation_snapshot_canonical_readback_failed:{type(exc).__name__}:{exc}"

    if (
        canonical_cohort != status_cohort
        or binding.get("result_id") != result_id
        or binding.get("cohort_hash") != cohort_hash
        or binding.get("invocation_output_size") != invocation_output_size
        or binding.get("invocation_output_sha256") != invocation_output_sha256
    ):
        return None, "recommendation_snapshot_status_canonical_binding_mismatch"
    raw_artifact_sha256 = binding.get("raw_artifact_sha256")
    payload_hash = binding.get("payload_hash")
    schema_version = binding.get("schema_version")
    schema_revision = binding.get("schema_revision")
    integrity_basis = binding.get("integrity_basis")
    data_as_of_date = binding.get("data_as_of_date")
    decision_at = binding.get("decision_at")
    available_at = binding.get("available_at")
    if (
        not isinstance(raw_artifact_sha256, str)
        or not _is_sha256_text(raw_artifact_sha256)
        or not isinstance(payload_hash, str)
        or not _is_sha256_text(payload_hash)
        or type(schema_version) is not str
        or type(schema_revision) is not int
        or integrity_basis != "canonical_payload_and_index_verified"
        or type(data_as_of_date) is not str
        or type(decision_at) is not str
        or (available_at is not None and type(available_at) is not str)
    ):
        return None, "recommendation_snapshot_canonical_binding_incomplete"
    try:
        actual_size = invocation_output_path.stat().st_size
    except OSError:
        return None, "recommendation_pipeline_snapshot_stdout_unreadable"
    if actual_size != invocation_output_size:
        return None, "recommendation_pipeline_snapshot_stdout_size_mismatch"

    return (
        SnapshotSummary(
            path=invocation_output_path.resolve(),
            payload=invocation_payload,
            symbols=symbols,
            cohort=canonical_cohort,
            file_sha256=invocation_output_sha256,
            status_path=status_path.resolve(),
            status_payload=status_payload,
            pipeline_run_id=pipeline_run_id,
            pipeline_status_path=pipeline_status_path.resolve(),
            pipeline_status_payload=pipeline_status_payload,
            result_id=result_id,
            payload_hash=payload_hash,
            canonical_artifact_sha256=raw_artifact_sha256,
            schema_version=schema_version,
            schema_revision=schema_revision,
            integrity_basis=integrity_basis,
            decision_date=expected_date,
            data_as_of_date=data_as_of_date,
            decision_at=decision_at,
            available_at=available_at,
            cohort_hash=cohort_hash,
            invocation_output_path=invocation_output_path.resolve(),
            invocation_output_sha256=invocation_output_sha256,
            invocation_output_size=invocation_output_size,
        ),
        None,
    )


def _is_sha256_text(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _same_resolved_path(value: object, expected: Path) -> bool:
    if type(value) is not str or not value.strip():
        return False
    try:
        return Path(value).expanduser().resolve() == expected.expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def _file_marker(path: Path, *, hash_small_file: bool = True) -> dict[str, Any]:
    marker: dict[str, Any] = {"path": str(path.resolve()), "exists": path.is_file()}
    if not path.is_file():
        return marker
    try:
        stat = path.stat()
    except OSError:
        marker["stat_readable"] = False
        return marker
    marker.update(
        {
            "stat_readable": True,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    )
    if hash_small_file and stat.st_size <= 10 * 1024 * 1024:
        marker["sha256"] = _hash_file(path)
    return marker


def _source_markers(paths: OperationalPaths) -> list[dict[str, Any]]:
    candidates = [
        paths.source_artifact_root / "scheduled" / "official_market_events" / "latest_status.json",
        paths.source_artifact_root / "release_v4" / "official_market_events" / "prospective_latest_manifest.json",
        paths.source_artifact_root / "release_v4" / "official_market_events" / "latest_manifest.json",
        paths.source_artifact_root / "release_v4" / "corporate_action_adjustments" / "latest_manifest.json",
        paths.data_root / "output" / "scheduled" / "data_update_quick" / "latest_status.json",
    ]
    technical_root = paths.data_root / "output" / "scheduled" / "technical_indicator_publication"
    if technical_root.is_dir():
        candidates.extend(sorted(technical_root.glob("**/receipt.json"))[-2:])
    return [_file_marker(path) for path in candidates]


def build_input_fingerprint(
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    snapshot: SnapshotSummary | None,
) -> str:
    """以 immutable input identity 判斷同日重跑是否可安全 reuse。"""

    return _hash_payload(
        {
            "schema_version": "banktaiwan-operational-input-fingerprint.v2",
            "decision_date": decision_date.isoformat(),
            "decision_timezone": "Asia/Taipei",
            "snapshot": (
                {
                    "result_id": snapshot.result_id,
                    "path": str(snapshot.path),
                    "canonical_artifact_sha256": snapshot.canonical_artifact_sha256,
                    "payload_hash": snapshot.payload_hash,
                    "schema_version": snapshot.schema_version,
                    "schema_revision": snapshot.schema_revision,
                    "integrity_basis": snapshot.integrity_basis,
                    "decision_date": snapshot.decision_date,
                    "data_as_of_date": snapshot.data_as_of_date,
                    "decision_at": snapshot.decision_at,
                    "available_at": snapshot.available_at,
                    "symbols": list(snapshot.symbols),
                    "cohort": dict(snapshot.cohort),
                    "cohort_hash": snapshot.cohort_hash,
                    "pipeline_run_id": snapshot.pipeline_run_id,
                    "pipeline_status_path": str(snapshot.pipeline_status_path),
                    "invocation_output_path": str(snapshot.invocation_output_path),
                    "invocation_output_sha256": snapshot.invocation_output_sha256,
                    "invocation_output_size": snapshot.invocation_output_size,
                }
                if snapshot is not None
                else None
            ),
            "source_artifact_root": str(paths.source_artifact_root),
            "source_markers": _source_markers(paths),
            "source_db": _file_marker(paths.source_db, hash_small_file=False),
            "cost_scenario": scenario.metadata(),
        }
    )


ProcessState = Literal["running", "dead", "unknown"]


def _windows_process_state(pid: int) -> ProcessState:
    """以 Windows query-only API 判斷 PID；不送 signal、不終止 process。"""

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        process_query_limited_information = 0x1000
        still_active = 259
        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            wintypes.DWORD(pid),
        )
        if not handle:
            error_code = ctypes.get_last_error()
            # OpenProcess uses ERROR_INVALID_PARAMETER for a valid PID that
            # no longer exists on this host.  The explicit not-found codes
            # are safe stale-lock evidence; AccessDenied/protected-process
            # and every other query error remain unknown.
            if error_code in {2, 87, 1168}:
                return "dead"
            return "unknown"
        exit_code = wintypes.DWORD()
        try:
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return "unknown"
        finally:
            kernel32.CloseHandle(handle)
        return "running" if exit_code.value == still_active else "dead"
    except (AttributeError, OSError, TypeError, ValueError):
        return "unknown"


def _process_state(pid: object) -> ProcessState:
    """回傳 running/dead/unknown；不確定時永不回收 lock。"""

    if (
        isinstance(pid, bool)
        or not isinstance(pid, int)
        or pid <= 0
        or pid > 0xFFFFFFFF
    ):
        return "unknown"
    if os.name == "nt":
        return _windows_process_state(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "unknown"
    except OSError:
        return "unknown"
    return "running"


def _pid_running(pid: object) -> bool:
    """相容性 helper；只有明確 running 才回傳 True。"""

    return _process_state(pid) == "running"


class OperationalRunLock:
    """跨 process 的 create-only lock；crash 後只回收確認已死亡的 PID。"""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.token = secrets.token_hex(16)
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "schema_version": "banktaiwan-operational-lock.v1",
            "pid": os.getpid(),
            "token": self.token,
            "started_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        }
        for _ in range(2):
            try:
                descriptor = os.open(
                    str(self.path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                try:
                    os.write(
                        descriptor,
                        (json.dumps(metadata, ensure_ascii=False) + "\n").encode("utf-8"),
                    )
                finally:
                    os.close(descriptor)
                self.acquired = True
                return
            except FileExistsError as exc:
                existing = _read_json(self.path)
                process_state = (
                    _process_state(existing.get("pid"))
                    if isinstance(existing, Mapping)
                    else "unknown"
                )
                if existing is None or process_state in {"running", "unknown"}:
                    raise OperationalOverlapError(
                        f"operational lock is held: {self.path}"
                    ) from exc
                try:
                    self.path.unlink()
                except OSError as unlink_error:
                    raise OperationalOverlapError(
                        f"stale operational lock cannot be reclaimed: {self.path}"
                    ) from unlink_error
        raise OperationalOverlapError(f"operational lock is held: {self.path}")

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            existing = _read_json(self.path)
            if isinstance(existing, Mapping) and existing.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        finally:
            self.acquired = False

    def __enter__(self) -> "OperationalRunLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.release()


def _scenario_payload(scenario: RecommendationCostScenario) -> dict[str, Any]:
    return {
        **scenario.metadata(),
        "research_sizing_basis": "configured_reference_order_not_user_position",
        "research_sizing_is_not_actual_fill": True,
        "formal_order_allowed": False,
        "shadow_only": True,
    }


def _base_payload(
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    input_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "task": TASK_NAME,
        "scheduler": {
            "task_name": TASK_NAME,
            "local_time": SCHEDULER_LOCAL_TIME,
            "host_timezone": SCHEDULER_TIMEZONE,
            "multiple_instances": "IgnoreNew",
        },
        "decision_date": decision_date.isoformat(),
        "decision_timezone": "Asia/Taipei",
        "paths": {
            "data_root": str(paths.data_root),
            "lane_output_root": str(paths.lane_output_root),
            "lane_learning_root": str(paths.lane_learning_root),
            "operational_root": str(paths.operational_root),
            "latest_status_path": str(paths.latest_status_path),
            "runs_root": str(paths.runs_root),
            "logs_root": str(paths.logs_root),
            "lock_path": str(paths.lock_path),
            "snapshot_output_root": str(paths.snapshot_output_root),
            "source_artifact_root": str(paths.source_artifact_root),
            "source_db": str(paths.source_db),
        },
        "cost_scenario": _scenario_payload(scenario),
        "cost_policy_identity": {
            "policy_id": scenario.policy_id,
            "policy_version": scenario.policy_version,
            "policy_estimate_date": scenario.policy_estimate_date,
        },
        "input_fingerprint": input_fingerprint,
        "source_read_policy": {
            "source_db_mode": "sqlite_mode_ro_query_only",
            "source_artifacts_are_read_only": True,
            "snapshot_reused_from_existing_scheduler": True,
            "technical_refresh_in_this_task": False,
            "official_refresh_in_this_task": False,
        },
        "formal_order_allowed": False,
        "shadow_only": True,
        "broker_action": False,
    }


def _next_attempt_number(runs_root: Path, decision_date: date) -> int:
    prefix = f"{decision_date.isoformat()}-attempt-"
    numbers: list[int] = []
    for path in runs_root.glob(f"{prefix}*.json"):
        match = re.search(r"-attempt-(\d+)(?:-[0-9a-f]+)?\.json$", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _run_id(decision_date: date, input_fingerprint: str, attempt: int) -> str:
    return f"{decision_date.isoformat()}-attempt-{attempt:03d}-{input_fingerprint.split(':', 1)[-1][:12]}"


def _extract_child_json(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _child_command(
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    args: argparse.Namespace,
    snapshot: SnapshotSummary,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "scheduled" / "run_daily_recommendation_learning.py"),
        "--data-root",
        str(paths.data_root),
        "--output-root",
        str(paths.lane_output_root),
        "--snapshot-output-root",
        str(paths.snapshot_output_root),
        "--source-artifact-root",
        str(paths.source_artifact_root),
        "--source-db",
        str(paths.source_db),
        "--history-start-date",
        str(args.history_start_date),
        "--fixed-round-trip-cost-bp",
        "50",
        "--max-decision-dates",
        str(args.max_decision_dates),
        "--replay-selection-policy",
        "latest_eligible_dates",
        "--decision-date",
        decision_date.isoformat(),
        "--training-as-of",
        decision_date.isoformat(),
        "--cost-scenario",
        "banktaiwan_estimated_research",
        "--cost-policy-estimate-date",
        str(scenario.policy_estimate_date),
        "--research-order-quantity-shares",
        str(scenario.research_order_quantity_shares),
        "--research-order-lot-type",
        str(scenario.lot_type),
        "--research-instrument-type",
        str(scenario.instrument_type),
        "--capture-current",
    ]
    command.extend(
        [
            "--snapshot-result-id",
            snapshot.result_id,
            "--snapshot-cohort-hash",
            snapshot.cohort_hash,
            "--snapshot-invocation-output-sha256",
            snapshot.invocation_output_sha256,
            "--snapshot-invocation-output-path",
            str(snapshot.invocation_output_path),
        ]
    )
    return command


def _run_child_subprocess(
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    args: argparse.Namespace,
    snapshot: SnapshotSummary,
) -> Mapping[str, Any]:
    command = _child_command(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        args=args,
        snapshot=snapshot,
    )
    environment = os.environ.copy()
    environment.update(
        {
            "OUTPUT_ROOT": str(paths.snapshot_output_root),
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(paths.lane_output_root),
            "DB_PATH": str(paths.source_db),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    log_path = paths.logs_root / f"{decision_date.strftime('%Y%m%d')}_banktaiwan_learning.log"
    paths.logs_root.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=int(args.child_timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        combined = _tail(_subprocess_text(exc.stdout) + _subprocess_text(exc.stderr))
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n===== CHILD TIMEOUT =====\n{combined}\n")
        return {
            "command": command,
            "returncode": None,
            "status": "timed_out",
            "reason": "child_timeout",
            "stdout_stderr_tail": combined,
        }
    combined = ((completed.stdout or "") + (completed.stderr or "")).strip()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n===== CHILD =====\n{combined}\n")
    child_payload = _extract_child_json(completed.stdout or "")
    if child_payload is None:
        child_payload = _read_json(paths.lane_learning_root / "latest_status.json")
    return {
        "command": command,
        "returncode": completed.returncode,
        "status": "completed_process",
        "child_payload": child_payload,
        "stdout_stderr_tail": _tail(combined),
    }


def _child_classification(child_result: Mapping[str, Any]) -> tuple[str, str, bool]:
    returncode = child_result.get("returncode")
    if returncode is None:
        return "failed_dependency", "child_timeout", True
    if isinstance(returncode, int) and returncode != 0:
        return "failed_dependency", f"child_exit_code:{returncode}", True
    child = child_result.get("child_payload")
    child = child if isinstance(child, Mapping) else {}
    live_capture_value = child.get("live_capture")
    live_capture = live_capture_value if isinstance(live_capture_value, Mapping) else {}
    capture_status = str(live_capture.get("status") or "").strip().lower()
    capture_reason = str(live_capture.get("reason") or "").strip()
    if capture_status in {"blocked", "failed"}:
        return "failed_dependency", f"live_capture_{capture_status}:{capture_reason}", True
    if capture_status == "skipped" and (
        "non_trading_day" in capture_reason
        or "official_calendar" in capture_reason
    ):
        return "skipped_non_trading_day", capture_reason or "non_trading_day_official_calendar", False
    run_value = child.get("run")
    run = run_value if isinstance(run_value, Mapping) else {}
    decision_reason = str(
        run.get("decision_reason")
        or child.get("decision_reason")
        or ""
    ).strip()
    if "natural" in decision_reason or "matur" in decision_reason:
        return "completed_waiting_natural_maturity", decision_reason or "natural_maturity_pending", False
    dependencies_value = child.get("dependencies")
    dependencies = dependencies_value if isinstance(dependencies_value, Mapping) else {}
    diagnostics = dependencies.get("diagnostics")
    if isinstance(diagnostics, list) and any(
        "source" in str(item).lower() and "failed" in str(item).lower()
        for item in diagnostics
    ):
        return "completed_with_advisories", decision_reason or "source_advisory_preserved", False
    return "completed_shadow", decision_reason or "shadow_learning_completed", False


def _projection_for_idempotent_replay(
    existing: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(existing)
    payload["idempotent_replay"] = True
    payload["reused_run_id"] = existing.get("run_id")
    payload["reused_receipt_path"] = existing.get("receipt_path")
    payload["last_observed_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    return payload


def _persist_terminal(
    *,
    paths: OperationalPaths,
    payload: Mapping[str, Any],
    run_id: str,
) -> dict[str, Any]:
    run_path = paths.runs_root / f"{run_id}.json"
    run_payload = dict(payload)
    run_payload["run_id"] = run_id
    run_payload["receipt_path"] = str(run_path)
    run_payload["finalized"] = True
    run_payload["completed_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    _write_json(run_path, run_payload)
    latest_payload = dict(run_payload)
    latest_payload["latest_status_path"] = str(paths.latest_status_path)
    _write_json(paths.latest_status_path, latest_payload)
    return latest_payload


def _build_scenario(args: argparse.Namespace) -> RecommendationCostScenario:
    quantity = (
        DEFAULT_RESEARCH_ORDER_QUANTITY_SHARES
        if args.research_order_quantity_shares is None
        else args.research_order_quantity_shares
    )
    return build_banktaiwan_cost_scenario(
        policy_estimate_date=str(args.cost_policy_estimate_date),
        research_order_amount_twd=args.research_order_amount_twd,
        research_order_quantity_shares=quantity,
        lot_type=str(args.research_order_lot_type),
        instrument_type=str(args.research_instrument_type),
    )


def _common_args(args: argparse.Namespace) -> tuple[OperationalPaths, date, RecommendationCostScenario]:
    paths = resolve_operational_paths(
        data_root=args.data_root,
        lane_output_root=args.output_root,
        snapshot_output_root=args.snapshot_output_root,
        source_artifact_root=args.source_artifact_root,
        source_db=args.source_db,
    )
    decision_date = (
        date.fromisoformat(str(args.decision_date)[:10])
        if args.decision_date
        else datetime.now(TAIPEI).date()
    )
    scenario = _build_scenario(args)
    return paths, decision_date, scenario


def _dry_run(args: argparse.Namespace) -> int:
    try:
        paths, decision_date, scenario = _common_args(args)
        official_day, calendar_reason = _official_calendar(
            paths.source_db
        ).is_official_trading_day(decision_date, allow_online_probe=False)
        if official_day is True:
            snapshot, snapshot_reason = load_same_day_snapshot(
                output_root=paths.snapshot_output_root,
                decision_date=decision_date,
            )
        else:
            snapshot = None
            snapshot_reason = (
                "not_applicable_non_trading_day"
                if official_day is False
                else "not_checked_calendar_unresolved"
            )
        planned = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "dry_run",
            "task": TASK_NAME,
            "decision_date": decision_date.isoformat(),
            "decision_timezone": "Asia/Taipei",
            "scheduler": {
                "task_name": TASK_NAME,
                "local_time": SCHEDULER_LOCAL_TIME,
                "host_timezone": SCHEDULER_TIMEZONE,
                "multiple_instances": "IgnoreNew",
            },
            "paths": {
                "lane_output_root": str(paths.lane_output_root),
                "snapshot_output_root": str(paths.snapshot_output_root),
                "source_artifact_root": str(paths.source_artifact_root),
                "source_db": str(paths.source_db),
                "latest_status_path": str(paths.latest_status_path),
                "lock_path": str(paths.lock_path),
            },
            "cost_scenario": _scenario_payload(scenario),
            "calendar": {
                "timezone": "Asia/Taipei",
                "is_official_trading_day": official_day,
                "reason": calendar_reason,
            },
            "snapshot": {
                "status": (
                    "verified"
                    if snapshot is not None
                    else "not_applicable"
                    if official_day is False
                    else "not_checked"
                    if official_day is None
                    else "blocked"
                ),
                "reason": snapshot_reason,
                "path": str(snapshot.path) if snapshot is not None else None,
                "file_sha256": snapshot.file_sha256 if snapshot is not None else None,
                "canonical_artifact_sha256": (
                    snapshot.canonical_artifact_sha256 if snapshot is not None else None
                ),
                "symbols": list(snapshot.symbols) if snapshot is not None else [],
                "result_id": snapshot.result_id if snapshot is not None else None,
                "payload_hash": snapshot.payload_hash if snapshot is not None else None,
                "schema_version": snapshot.schema_version if snapshot is not None else None,
                "schema_revision": snapshot.schema_revision if snapshot is not None else None,
                "integrity_basis": snapshot.integrity_basis if snapshot is not None else None,
                "cohort_hash": snapshot.cohort_hash if snapshot is not None else None,
                "invocation_output_path": (
                    str(snapshot.invocation_output_path) if snapshot is not None else None
                ),
                "invocation_output_sha256": (
                    snapshot.invocation_output_sha256 if snapshot is not None else None
                ),
            },
            "child_invocation": "not_run",
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
    except (OperationalLaneError, OSError, TypeError, ValueError) as exc:
        planned = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "dry_run_blocked",
            "task": TASK_NAME,
            "reason": f"{type(exc).__name__}:{exc}",
            "formal_order_allowed": False,
            "shadow_only": True,
        }
        print(json.dumps(planned, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(planned, ensure_ascii=False, sort_keys=True))
    return 0


def _run_locked(
    *,
    paths: OperationalPaths,
    decision_date: date,
    scenario: RecommendationCostScenario,
    args: argparse.Namespace,
    child_runner: ChildRunner | None,
) -> tuple[int, dict[str, Any]]:
    official_day: bool | None = None
    calendar_reason = "not_checked"
    if paths.source_db.is_file():
        try:
            official_day, calendar_reason = _official_calendar(
                paths.source_db
            ).is_official_trading_day(decision_date, allow_online_probe=False)
        except (OSError, RuntimeError, TypeError, ValueError):
            official_day, calendar_reason = None, "official_calendar_read_failed"
    else:
        calendar_reason = "source_db_missing"
    if official_day is True:
        snapshot, snapshot_reason = load_same_day_snapshot(
            output_root=paths.snapshot_output_root,
            decision_date=decision_date,
        )
    else:
        snapshot = None
        snapshot_reason = (
            "not_applicable_non_trading_day"
            if official_day is False
            else "not_checked_calendar_unresolved"
        )
    fingerprint = build_input_fingerprint(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        snapshot=snapshot,
    )
    existing = _read_json(paths.latest_status_path)
    if (
        isinstance(existing, Mapping)
        and existing.get("decision_date") == decision_date.isoformat()
        and existing.get("input_fingerprint") == fingerprint
        and existing.get("status") in _REUSABLE_TERMINAL_STATUSES
    ):
        projection = _projection_for_idempotent_replay(existing)
        _write_json(paths.latest_status_path, projection)
        return 0, projection

    attempt = _next_attempt_number(paths.runs_root, decision_date)
    run_id = _run_id(decision_date, fingerprint, attempt)
    base = _base_payload(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        input_fingerprint=fingerprint,
    )
    base.update(
        {
            "run_id": run_id,
            "attempt_number": attempt,
            "started_at": datetime.now(TAIPEI).isoformat(timespec="seconds"),
            "retry": {
                "attempt_number": attempt,
                "previous_status": existing.get("status") if isinstance(existing, Mapping) else None,
                "previous_run_id": existing.get("run_id") if isinstance(existing, Mapping) else None,
                "retryable_after_failure": True,
            },
            "snapshot": {
                "status": (
                    "verified"
                    if snapshot is not None
                    else "not_applicable"
                    if official_day is False
                    else "not_checked"
                    if official_day is None
                    else "blocked"
                ),
                "reason": snapshot_reason,
                "path": str(snapshot.path) if snapshot is not None else None,
                "file_sha256": snapshot.file_sha256 if snapshot is not None else None,
                "canonical_artifact_sha256": (
                    snapshot.canonical_artifact_sha256 if snapshot is not None else None
                ),
                "status_path": str(snapshot.status_path) if snapshot is not None else str(paths.snapshot_output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"),
                "symbols": list(snapshot.symbols) if snapshot is not None else [],
                "cohort": dict(snapshot.cohort) if snapshot is not None else {},
                "result_id": snapshot.result_id if snapshot is not None else None,
                "payload_hash": snapshot.payload_hash if snapshot is not None else None,
                "schema_version": snapshot.schema_version if snapshot is not None else None,
                "schema_revision": snapshot.schema_revision if snapshot is not None else None,
                "integrity_basis": snapshot.integrity_basis if snapshot is not None else None,
                "decision_date": snapshot.decision_date if snapshot is not None else None,
                "data_as_of_date": snapshot.data_as_of_date if snapshot is not None else None,
                "decision_at": snapshot.decision_at if snapshot is not None else None,
                "available_at": snapshot.available_at if snapshot is not None else None,
                "cohort_hash": snapshot.cohort_hash if snapshot is not None else None,
                "pipeline_run_id": snapshot.pipeline_run_id if snapshot is not None else None,
                "pipeline_status_path": (
                    str(snapshot.pipeline_status_path) if snapshot is not None else None
                ),
                "invocation_output_path": (
                    str(snapshot.invocation_output_path) if snapshot is not None else None
                ),
                "invocation_output_sha256": (
                    snapshot.invocation_output_sha256 if snapshot is not None else None
                ),
                "invocation_output_size": (
                    snapshot.invocation_output_size if snapshot is not None else None
                ),
            },
        }
    )
    base["calendar"] = {
        "timezone": "Asia/Taipei",
        "is_official_trading_day": official_day,
        "reason": calendar_reason,
    }

    if official_day is False:
        base.update(
            {
                "status": "skipped_non_trading_day",
                "reason": calendar_reason,
                "recoverable": False,
                "child_invocation": "not_required_non_trading_day",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 0, result

    if official_day is None:
        base.update(
            {
                "status": "failed_dependency",
                "reason": f"official_calendar_unresolved:{calendar_reason}",
                "recoverable": True,
                "child_invocation": "not_started",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 2, result

    if not paths.source_db.is_file():
        base.update(
            {
                "status": "failed_dependency",
                "reason": "source_db_missing",
                "recoverable": True,
                "child_invocation": "not_started",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 2, result
    if not paths.source_artifact_root.is_dir():
        base.update(
            {
                "status": "failed_dependency",
                "reason": "source_artifact_root_missing",
                "recoverable": True,
                "child_invocation": "not_started",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 2, result
    if snapshot is None:
        base.update(
            {
                "status": "failed_dependency",
                "reason": snapshot_reason or "same_day_scheduled_recommendation_snapshot_missing",
                "recoverable": True,
                "child_invocation": "not_started",
            }
        )
        result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
        return 2, result

    child_result = (
        dict(child_runner(paths, decision_date, scenario, args))
        if child_runner is not None
        else dict(_run_child_subprocess(paths, decision_date, scenario, args, snapshot))
    )
    status, reason, recoverable = _child_classification(child_result)
    child_payload = child_result.get("child_payload")
    child_payload = child_payload if isinstance(child_payload, Mapping) else {}
    run_value = child_payload.get("run")
    run = dict(run_value) if isinstance(run_value, Mapping) else {}
    base.update(
        {
            "status": status,
            "reason": reason,
            "recoverable": recoverable,
            "child_invocation": {
                "status": child_result.get("status"),
                "returncode": child_result.get("returncode"),
                "command": list(child_result.get("command") or []),
                "stdout_stderr_tail": child_result.get("stdout_stderr_tail", ""),
                "status_path": str(paths.lane_learning_root / "latest_status.json"),
            },
            "child_result": dict(child_payload),
            "outcome_evaluation": {
                "decision": run.get("decision") or child_payload.get("decision"),
                "decision_reason": run.get("decision_reason") or child_payload.get("decision_reason"),
                "candidate_id": run.get("candidate_id"),
                "candidate_root": run.get("candidate_root"),
                "active_pointer": child_payload.get("active_pointer"),
                "challenger": child_payload.get("challenger"),
                "natural_evidence": child_payload.get("natural_evidence"),
                "active_model_natural_evidence": child_payload.get("active_model_natural_evidence"),
            },
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
    )
    result = _persist_terminal(paths=paths, payload=base, run_id=run_id)
    return (0 if status in _REUSABLE_TERMINAL_STATUSES else 2), result


def run_once(
    args: argparse.Namespace,
    *,
    child_runner: ChildRunner | None = None,
) -> tuple[int, dict[str, Any]]:
    """執行一次具 lock、retry、receipt 與 non-trading 分類的每日 attempt。"""

    try:
        paths, decision_date, scenario = _common_args(args)
    except (OperationalLaneError, OSError, TypeError, ValueError) as exc:
        payload = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "failed_dependency",
            "task": TASK_NAME,
            "reason": f"configuration_invalid:{type(exc).__name__}:{exc}",
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
        return 2, payload
    lock = OperationalRunLock(paths.lock_path)
    try:
        lock.acquire()
    except OperationalOverlapError as exc:
        payload = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "status": "skipped_overlap",
            "task": TASK_NAME,
            "decision_date": decision_date.isoformat(),
            "decision_timezone": "Asia/Taipei",
            "reason": str(exc),
            "lock_path": str(paths.lock_path),
            "recoverable": True,
            "formal_order_allowed": False,
            "shadow_only": True,
            "broker_action": False,
        }
        return 0, payload
    try:
        return _run_locked(
            paths=paths,
            decision_date=decision_date,
            scenario=scenario,
            args=args,
            child_runner=child_runner,
        )
    finally:
        lock.release()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--snapshot-output-root", type=Path, default=None)
    parser.add_argument("--source-artifact-root", type=Path, default=None)
    parser.add_argument("--source-db", type=Path, default=None)
    parser.add_argument("--decision-date", default=None)
    parser.add_argument("--history-start-date", default="2014-01-01")
    parser.add_argument("--max-decision-dates", type=int, default=100)
    parser.add_argument("--cost-policy-estimate-date", default=DEFAULT_POLICY_ESTIMATE_DATE)
    sizing = parser.add_mutually_exclusive_group()
    sizing.add_argument("--research-order-amount-twd", default=None)
    sizing.add_argument(
        "--research-order-quantity-shares",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--research-order-lot-type",
        choices=("full_lot", "odd_lot"),
        default="full_lot",
    )
    parser.add_argument(
        "--research-instrument-type",
        choices=("ordinary_stock", "equity_etf"),
        default="ordinary_stock",
    )
    parser.add_argument("--child-timeout-seconds", type=int, default=7200)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.dry_run:
        return _dry_run(args)
    code, payload = run_once(args)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
