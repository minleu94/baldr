"""執行固定 repository scope 的研究用 Paper EOD replay。

這個入口是唯一可由 ``baldr-paper-execution-eod-replay-daily`` 使用的
scheduled adapter。官方 recommendation 與行情 SQLite 固定從既有資料根目錄
以 ``mode=ro`` 讀取；盤前 adapter 先將 D 槽 Paper snapshot 以一致 backup
seed 到 repository state，EOD 只讀該 repository state。candidate、operational
receipt 與 append-only Paper ledger 固定寫入 repository 的隔離目錄。它不接受環境變數
覆寫路徑，也不把隔離 ledger 當成 Formal input。
官方 TWSE annual holidaySchedule cache 也固定從 operation root 讀取並逐次重驗
raw bytes、完整年度與 freshness；cache 不會改寫任何 D 或市場資料。
每輪另以 bounded 官方 newsList/newsDetail 探測臨時全面休市公告，將 list/detail
custody 綁定的 sidecar 寫入同一 operation root；公告清單或明細不可得時只回傳
observable discovery blocker，不把失敗視為休市或正式 credit。
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid


ROOT = Path(os.path.abspath(__file__)).parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.paper_daily_execution_producer import (  # noqa: E402
    PAPER_EXECUTION_PRODUCER_VERSION,
    PAPER_EXECUTION_SCHEMA_VERSION,
    TAIPEI,
    PaperExecutionPaths,
    ensure_paper_ledger_schema,
    persist_operational_receipt,
    run_paper_execution_daily_from_queue,
)
from data_module.paper_event_source_capture import (  # noqa: E402
    PaperEventSourceCaptureError,
    bind_paper_candidate_file_to_capture,
    resolve_persisted_twse_event_source_capture_for_recommendation,
)
from data_module.formal_runtime_config import (  # noqa: E402
    FORMAL_RUNTIME_CONFIG_ENV,
    FormalRuntimeConfigError,
    load_optional_formal_runtime_config,
)
from data_module.official_trading_calendar import OfficialTradingCalendar  # noqa: E402
from data_module.official_trading_calendar_cache import (  # noqa: E402
    OfficialCalendarCacheError,
    refresh_twse_calendar_cache,
    refresh_twse_temporary_closure_events,
)
from scripts.scheduled.paper_portfolio_state_isolation import (  # noqa: E402
    verify_repo_state_seed,
)
from runtime.repository_output import (  # noqa: E402
    RepositoryOutputBoundaryError,
    is_repository_output_path,
    resolve_repository_output_path,
    validate_repository_root,
)


DEFAULT_DATA_ROOT = Path(r"F:\Min\Python\Project\FA_Data")
OPERATIONAL_ROOT = ROOT / "output" / "paper_execution_eod_replay"
CANDIDATE_ROOT = OPERATIONAL_ROOT / "candidates"
RECEIPT_ROOT = OPERATIONAL_ROOT / "receipts"
LEDGER_DB = OPERATIONAL_ROOT / "paper_trade_ledger.sqlite"
SOURCE_STATE_DB = (
    DEFAULT_DATA_ROOT / "output" / "paper_portfolio" / "paper_portfolio.sqlite"
)
PAPER_STATE_ROOT = OPERATIONAL_ROOT / "paper_portfolio"
STATE_DB = PAPER_STATE_ROOT / "paper_portfolio.sqlite"
STATE_SEED_MANIFEST = PAPER_STATE_ROOT / "state_seed_manifest.json"
MARKET_DB = DEFAULT_DATA_ROOT / "sqlite" / "twstock.db"
RECOMMENDATION_ROOT = DEFAULT_DATA_ROOT / "output" / "recommendation" / "runs"
EVENT_CAPTURE_ROOT = OPERATIONAL_ROOT / "event_captures"
# v2 是既有 immutable scope 的歷史來源；v3 另建 append-only manifest，
# 不覆寫 v2 bytes。v3 的 scope_manifest 欄位必須自洽指向 v3 檔案。
SCOPE_MANIFEST = OPERATIONAL_ROOT / "scope_manifest_v3.json"
SCOPE_SCHEMA_VERSION = "paper-execution-isolated-scope.v3"
LEGACY_SCOPE_SCHEMA_VERSION = "paper-execution-isolated-scope.v2"
SCOPE_MIGRATION_RECEIPT_SCHEMA_VERSION = "paper-execution-scope-migration-receipt.v1"
SCOPE_FAILURE_RECEIPT_SCHEMA_VERSION = "paper-execution-scope-validation-failure.v1"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _resolved(value: Path) -> Path:
    candidate = Path(os.path.abspath(value.expanduser()))
    try:
        if candidate == ROOT:
            return validate_repository_root(candidate)
        if is_repository_output_path(candidate, repository_root=ROOT):
            return resolve_repository_output_path(
                candidate,
                repository_root=ROOT,
            )
    except RepositoryOutputBoundaryError as error:
        raise RuntimeError(f"repository output boundary rejected path: {error}") from error
    return candidate.resolve()


def _legacy_scope_manifest_path() -> Path:
    """回傳固定 v2 歷史 manifest 路徑；它只可被讀取與驗證。"""

    return OPERATIONAL_ROOT / "scope_manifest_v2.json"


def _scope_migration_receipt_path() -> Path:
    """回傳 v2→v3 migration receipt 的 repository output 路徑。"""

    return OPERATIONAL_ROOT / "scope_manifest_v3_migration_receipt.json"


def _scope_failure_receipt_root() -> Path:
    """回傳不依賴可疑 writer scope 的固定錯誤報告根目錄。"""

    repository_root = _resolved(ROOT)
    return repository_root / "output" / "paper_execution_eod_replay" / "scope_validation_failures"


def _calendar_cache_root() -> Path:
    """回傳固定 repository output 下的官方日曆 cache 根目錄。"""

    return OPERATIONAL_ROOT / "calendar_cache"


def _refresh_calendar_cache(observed: datetime) -> dict[str, object]:
    """在已通過 scope 驗證後，最多重試兩次官方年度 cache。"""

    cache_root = _resolved(_calendar_cache_root())
    operation_root = _resolved(OPERATIONAL_ROOT)
    try:
        result = refresh_twse_calendar_cache(
            calendar_year=observed.astimezone(TAIPEI).year,
            cache_root=cache_root,
            allowed_root=operation_root,
            observed_at=observed,
        )
    except (OSError, RuntimeError, ValueError, OfficialCalendarCacheError) as error:
        return {
            "status": "refresh_blocked",
            "calendar_year": observed.astimezone(TAIPEI).year,
            "refresh_attempted": False,
            "network_attempts": 0,
            "reason": (
                "official_calendar_cache_refresh_scope_failed:"
                f"{type(error).__name__}:{error}"
            ),
        }
    return result


def _refresh_temporary_closure_events(observed: datetime) -> dict[str, object]:
    """在同一 operational run 以 bounded 官方公告清單更新臨時休市 sidecar。"""

    cache_root = _resolved(_calendar_cache_root())
    operation_root = _resolved(OPERATIONAL_ROOT)
    try:
        result = refresh_twse_temporary_closure_events(
            calendar_year=observed.astimezone(TAIPEI).year,
            cache_root=cache_root,
            allowed_root=operation_root,
            observed_at=observed,
        )
    except (OSError, RuntimeError, ValueError, OfficialCalendarCacheError) as error:
        return {
            "status": "temporary_closure_discovery_blocked",
            "calendar_year": observed.astimezone(TAIPEI).year,
            "network_attempts": 0,
            "detail_requests": 0,
            "reason": (
                "official_temporary_closure_refresh_scope_failed:"
                f"{type(error).__name__}:{error}"
            ),
            "events": [],
        }
    return result


def _write_calendar_refresh_receipt(
    result: Mapping[str, object],
    *,
    observed: datetime,
) -> Path:
    """保存每次 cache freshness／refresh 決定的 immutable operational receipt。"""

    receipt_root = _resolved(RECEIPT_ROOT)
    operation_root = _resolved(OPERATIONAL_ROOT)
    if not _is_under(receipt_root, operation_root) or receipt_root == operation_root:
        raise RuntimeError("calendar refresh receipt escaped operation root")
    receipt_root.mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {
        "schema_version": "twse-calendar-refresh-receipt.v1",
        "recorded_at": observed.astimezone(timezone.utc).isoformat(),
        "result": dict(result),
        "candidate_only": True,
        "formal_credit": False,
        "formal_clock_created": False,
        "market_db_written": False,
        "paper_ledger_written": False,
        "broker_order_allowed": False,
    }
    body["content_sha256"] = _payload_hash(body)
    stamp = observed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for suffix in range(100):
        token = "" if suffix == 0 else f"_{suffix}"
        path = receipt_root / f"calendar_refresh_{stamp}{token}.json"
        try:
            with path.open("xb") as stream:
                stream.write((_canonical_json(body) + "\n").encode("utf-8"))
                stream.flush()
                import os

                os.fsync(stream.fileno())
        except FileExistsError:
            continue
        return path
    raise RuntimeError("calendar refresh receipt filename collision")


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _new_candidate_root() -> Path:
    """回傳 repository candidates 下的未建立 run 目錄。"""

    CANDIDATE_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(20):
        run_root = CANDIDATE_ROOT / f"run_{uuid.uuid4().hex}"
        if not run_root.exists():
            return run_root
    raise RuntimeError("isolated Paper candidate run id collision")


def _scope_body(
    *,
    schema_version: str,
    scope_manifest_path: Path,
    include_event_capture_root: bool,
) -> dict[str, object]:
    writable: dict[str, object] = {
        "repository_output_root": str(_resolved(ROOT / "output")),
        "operation_root": str(_resolved(OPERATIONAL_ROOT)),
        "candidate_root": str(_resolved(CANDIDATE_ROOT)),
        "receipt_root": str(_resolved(RECEIPT_ROOT)),
        "ledger_db": str(_resolved(LEDGER_DB)),
        "scope_manifest": str(_resolved(scope_manifest_path)),
        "ledger_mode": "append_only_research_paper_only",
    }
    if include_event_capture_root:
        writable["event_capture_root"] = str(_resolved(EVENT_CAPTURE_ROOT))
    return {
        "schema_version": schema_version,
        "scope_id": "research-paper-eod-replay-repository-isolated-v1",
        "source": {
            "data_root": str(_resolved(DEFAULT_DATA_ROOT)),
            "recommendation_root": str(_resolved(RECOMMENDATION_ROOT)),
            "source_state_db": str(_resolved(SOURCE_STATE_DB)),
            "state_db": str(_resolved(STATE_DB)),
            "market_db": str(_resolved(MARKET_DB)),
            "state_read_mode": "sqlite_uri_mode_ro_and_query_only",
            "source_state_read_mode": "盤前 seed 專用；EOD 不回讀 D",
            "environment_path_overrides": "ignored",
        },
        "writable": writable,
        "read_only": {
            "repository_state_db": str(_resolved(STATE_DB)),
            "state_seed_manifest": str(_resolved(STATE_SEED_MANIFEST)),
            "state_read_mode": "sqlite_uri_mode_ro_and_query_only",
        },
        "safety": {
            "research_only": True,
            "formal_credit": False,
            "writes_formal_controlled_paths": False,
            "writes_market_database": False,
            "broker_order_allowed": False,
            "broker_execution": False,
            "training_started": False,
            "historical_backfill_claimed": False,
            "clock_override": False,
        },
    }


def _expected_scope() -> dict[str, object]:
    return _scope_body(
        schema_version=SCOPE_SCHEMA_VERSION,
        scope_manifest_path=SCOPE_MANIFEST,
        include_event_capture_root=True,
    )


def _expected_legacy_scope(*, include_event_capture_root: bool) -> dict[str, object]:
    return _scope_body(
        schema_version=LEGACY_SCOPE_SCHEMA_VERSION,
        scope_manifest_path=_legacy_scope_manifest_path(),
        include_event_capture_root=include_event_capture_root,
    )


def _validate_write_scope() -> dict[str, Path]:
    """確認所有 writer 目標仍在 repository output 且不在來源根目錄。"""

    repository_root = _resolved(ROOT)
    repository_output = _resolved(ROOT / "output")
    data_root = _resolved(DEFAULT_DATA_ROOT)
    operation = _resolved(OPERATIONAL_ROOT)
    candidate = _resolved(CANDIDATE_ROOT)
    receipt = _resolved(RECEIPT_ROOT)
    ledger = _resolved(LEDGER_DB)
    scope_manifest = _resolved(SCOPE_MANIFEST)
    legacy_scope_manifest = _resolved(_legacy_scope_manifest_path())
    migration_receipt = _resolved(_scope_migration_receipt_path())
    event_capture = _resolved(EVENT_CAPTURE_ROOT)
    state = _resolved(STATE_DB)
    state_root = _resolved(PAPER_STATE_ROOT)

    if repository_output == repository_root:
        raise RuntimeError(
            "isolated Paper repository output root cannot equal repository root"
        )
    if not _is_under(operation, repository_output) or operation == repository_output:
        raise RuntimeError(
            "isolated Paper operation root must be a repository output child"
        )

    for name, manifest_candidate in {
        "scope_manifest": SCOPE_MANIFEST,
        "legacy_scope_manifest": _legacy_scope_manifest_path(),
        "scope_migration_receipt": _scope_migration_receipt_path(),
    }.items():
        if manifest_candidate.expanduser().is_symlink():
            raise RuntimeError(f"isolated Paper scope path is a reparse point:{name}")

    for name, target in {
        "legacy_scope_manifest": legacy_scope_manifest,
    }.items():
        if not _is_under(target, operation):
            raise RuntimeError(
                f"isolated Paper scope source escaped operation root:{name}"
            )
        if not _is_under(target, repository_output) or _is_under(target, data_root):
            raise RuntimeError(
                f"isolated Paper scope source escaped repository scope:{name}"
            )

    for name, target in {
        "paper_state_root": state_root,
        "state_db": state,
        "state_seed_manifest": _resolved(STATE_SEED_MANIFEST),
    }.items():
        if not _is_under(target, operation):
            raise RuntimeError(
                f"isolated Paper repository state escaped operation root:{name}"
            )
        if not _is_under(target, repository_output) or _is_under(target, data_root):
            raise RuntimeError(
                f"isolated Paper repository state escaped repository scope:{name}"
            )

    write_targets = {
        "operation_root": operation,
        "candidate_root": candidate,
        "receipt_root": receipt,
        "ledger_db": ledger,
        "scope_manifest": scope_manifest,
        "scope_migration_receipt": migration_receipt,
        "event_capture_root": event_capture,
    }
    for name, target in write_targets.items():
        if not _is_under(target, operation):
            raise RuntimeError(
                f"isolated Paper write target escaped operation root:{name}"
            )
        if not _is_under(target, repository_output):
            raise RuntimeError(
                f"isolated Paper write target escaped repository output:{name}"
            )
        if _is_under(target, data_root):
            raise RuntimeError(
                f"isolated Paper write target overlaps source data root:{name}"
            )
    return {
        "repository_output_root": repository_output,
        "data_root": data_root,
        "paper_state_root": state_root,
        "state_db": state,
        "state_seed_manifest": _resolved(STATE_SEED_MANIFEST),
        "legacy_scope_manifest": legacy_scope_manifest,
        **write_targets,
    }


def _write_create_only_bytes(path: Path, raw: bytes, role: str) -> str:
    """以 create-only + fsync 寫入，既有 bytes 不一致時拒絕覆寫。"""

    if path.expanduser().is_symlink():
        raise RuntimeError(f"{role} is a reparse point")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == raw:
            return _bytes_hash(existing)
        raise RuntimeError(f"{role} existing bytes differ")
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            import os

            os.fsync(stream.fileno())
    except FileExistsError:
        existing = path.read_bytes()
        if existing != raw:
            raise RuntimeError(f"{role} concurrent bytes differ")
    return _bytes_hash(raw)


def _read_scope_manifest(path: Path, *, role: str) -> tuple[dict[str, object], str, str]:
    """讀取並驗證 scope manifest 的 body hash、file hash 與固定檔案型態。"""

    candidate = path.expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise RuntimeError(f"{role} missing or is a reparse point")
    raw = candidate.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{role} JSON invalid") from error
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{role} is not an object")
    body = dict(payload)
    declared = body.pop("content_sha256", None)
    if not isinstance(declared, str) or declared != _payload_hash(body):
        raise RuntimeError(f"{role} content hash mismatch")
    return body, declared, _bytes_hash(raw)


def _scope_diff_paths(before: object, after: object, prefix: str = "") -> list[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        keys = sorted(set(before) | set(after), key=str)
        for key in keys:
            name = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                paths.append(name)
            else:
                paths.extend(_scope_diff_paths(before[key], after[key], name))
        return paths
    return [] if before == after else [prefix]


def _scope_manifest_migration_plan(
    *,
    legacy_body: Mapping[str, object],
    legacy_content_hash: str,
    legacy_file_hash: str,
    target_body: Mapping[str, object],
    target_raw: bytes,
) -> dict[str, object]:
    """產生不寫檔的 v2→v3 planned diff 與保留/receipt 計畫。"""

    return {
        "schema_version": "paper-execution-scope-migration-plan.v1",
        "status": "planned",
        "migration": "paper_execution_scope_v2_to_v3",
        "append_only": True,
        "changed_fields": _scope_diff_paths(legacy_body, target_body),
        "source": {
            "path": str(_resolved(_legacy_scope_manifest_path())),
            "schema_version": legacy_body.get("schema_version"),
            "content_sha256": legacy_content_hash,
            "file_sha256": legacy_file_hash,
            "bytes_preserved": True,
        },
        "target": {
            "path": str(_resolved(SCOPE_MANIFEST)),
            "schema_version": target_body.get("schema_version"),
            "content_sha256": _payload_hash(target_body),
            "file_sha256": _bytes_hash(target_raw),
            "create_only": True,
        },
        "backup": {
            "mode": "source_bytes_preserved_no_overwrite",
            "required": False,
            "source_path": str(_resolved(_legacy_scope_manifest_path())),
            "source_file_sha256": legacy_file_hash,
        },
        "receipt": {
            "path": str(_resolved(_scope_migration_receipt_path())),
            "create_only": True,
            "schema_version": SCOPE_MIGRATION_RECEIPT_SCHEMA_VERSION,
        },
    }


def _read_exact_legacy_scope(
    path: Path,
) -> tuple[dict[str, object], str, str]:
    """讀取 v2 並只接受兩種已知、canonical 的歷史 body。"""

    body, content_hash, file_hash = _read_scope_manifest(
        path,
        role="isolated Paper v2 scope manifest",
    )
    accepted = (
        _expected_legacy_scope(include_event_capture_root=False),
        _expected_legacy_scope(include_event_capture_root=True),
    )
    if not any(body == expected for expected in accepted):
        raise RuntimeError("isolated Paper v2 scope manifest changed")
    return body, content_hash, file_hash


def _write_or_verify_migration_receipt(
    *,
    plan: Mapping[str, object],
    legacy_file_hash: str,
    target_file_hash: str,
) -> Path:
    receipt_candidate = _scope_migration_receipt_path()
    receipt_path = _resolved(receipt_candidate)
    body: dict[str, object] = {
        "schema_version": SCOPE_MIGRATION_RECEIPT_SCHEMA_VERSION,
        "status": "completed",
        "migration": "paper_execution_scope_v2_to_v3",
        "append_only": True,
        "formal_credit": False,
        "broker_execution": False,
        "writes_market_database": False,
        "source_file_sha256": legacy_file_hash,
        "target_file_sha256": target_file_hash,
        "source_bytes_preserved": True,
        "planned_diff": dict(plan),
    }
    if receipt_candidate.exists():
        existing_body, _, _ = _read_scope_manifest(
            receipt_candidate,
            role="scope migration receipt",
        )
        recorded_at = existing_body.get("recorded_at")
        if not isinstance(recorded_at, str) or not recorded_at.strip():
            raise RuntimeError("scope migration receipt recorded_at missing")
        try:
            parsed_recorded_at = datetime.fromisoformat(recorded_at)
        except ValueError as error:
            raise RuntimeError("scope migration receipt recorded_at invalid") from error
        if parsed_recorded_at.tzinfo is None:
            raise RuntimeError("scope migration receipt recorded_at must be timezone aware")
    else:
        # 遷移完成時間必須取實際執行時間，不得用歷史排程觀測時間追認。
        recorded_at = datetime.now(timezone.utc).isoformat()
    body["recorded_at"] = recorded_at
    body["content_sha256"] = _payload_hash(body)
    raw = (_canonical_json(body) + "\n").encode("utf-8")
    _write_create_only_bytes(receipt_candidate, raw, "scope migration receipt")
    existing_body, _, _ = _read_scope_manifest(
        receipt_candidate,
        role="scope migration receipt",
    )
    expected_body = dict(body)
    expected_body.pop("content_sha256", None)
    if existing_body != expected_body:
        raise RuntimeError("scope migration receipt changed")
    return receipt_path


def _write_or_verify_scope_manifest() -> tuple[Path, str]:
    """建立/驗證 v3 scope；只接受精確合法 v2 作為 append-only migration source。"""

    _validate_write_scope()
    body = _expected_scope()
    payload = {**body, "content_sha256": _payload_hash(body)}
    encoded = (_canonical_json(payload) + "\n").encode("utf-8")
    manifest_path = _resolved(SCOPE_MANIFEST)
    legacy_candidate = _legacy_scope_manifest_path()
    legacy_path = _resolved(legacy_candidate)
    legacy_exists = legacy_path != manifest_path and legacy_candidate.exists()
    legacy_info: tuple[dict[str, object], str, str] | None = None
    if legacy_exists:
        legacy_info = _read_exact_legacy_scope(legacy_candidate)

    if manifest_path.exists():
        existing_body, _, existing_file_hash = _read_scope_manifest(
            SCOPE_MANIFEST,
            role="isolated Paper v3 scope manifest",
        )
        if existing_body != body:
            raise RuntimeError("isolated Paper v3 scope manifest changed")
        target_file_hash = existing_file_hash
    else:
        target_file_hash = _write_create_only_bytes(
            SCOPE_MANIFEST,
            encoded,
            "isolated Paper v3 scope manifest",
        )
    if legacy_info is not None:
        legacy_body, legacy_content_hash, legacy_file_hash = legacy_info
        plan = _scope_manifest_migration_plan(
            legacy_body=legacy_body,
            legacy_content_hash=legacy_content_hash,
            legacy_file_hash=legacy_file_hash,
            target_body=body,
            target_raw=encoded,
        )
        if _file_hash(legacy_path) != legacy_file_hash:
            raise RuntimeError("isolated Paper v2 scope manifest changed during migration")
        _write_or_verify_migration_receipt(
            plan=plan,
            legacy_file_hash=legacy_file_hash,
            target_file_hash=target_file_hash,
        )
        if _file_hash(legacy_path) != legacy_file_hash:
            raise RuntimeError("isolated Paper v2 scope manifest changed during migration")
    return manifest_path, _file_hash(manifest_path)


def _write_scope_validation_failure_receipt(
    *,
    error: BaseException,
    observed: datetime,
) -> Path:
    """在固定 repository 報告根目錄保存 scope 驗證失敗。"""

    repository_root = _resolved(ROOT)
    report_root = _resolved(_scope_failure_receipt_root())
    data_root = _resolved(DEFAULT_DATA_ROOT)
    if report_root == repository_root or not _is_under(report_root, repository_root):
        raise RuntimeError("scope validation failure report escaped repository root")
    if _is_under(report_root, data_root) or _is_under(data_root, report_root):
        raise RuntimeError("scope validation failure report overlaps source data root")
    report_root.mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {
        "schema_version": SCOPE_FAILURE_RECEIPT_SCHEMA_VERSION,
        "status": "failed",
        "terminal": True,
        "scope_validation_failed": True,
        "recorded_at": observed.astimezone(timezone.utc).isoformat(),
        "error_type": type(error).__name__,
        "error": str(error),
        "scope_writer_targets_verified": False,
        "safe_report_root": str(report_root),
        "manifest_paths_observed": {
            "legacy_v2": str(_legacy_scope_manifest_path()),
            "target_v3": str(SCOPE_MANIFEST),
        },
        "formal_credit": False,
        "broker_execution": False,
        "writes_market_database": False,
    }
    body["content_sha256"] = _payload_hash(body)
    raw = (_canonical_json(body) + "\n").encode("utf-8")
    stamp = observed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for suffix in range(100):
        suffix_text = "" if suffix == 0 else f"_{suffix}"
        path = report_root / f"scope_validation_failed_{stamp}{suffix_text}.json"
        try:
            _write_create_only_bytes(path, raw, "scope validation failure receipt")
        except RuntimeError as write_error:
            if "existing bytes differ" in str(write_error) or "concurrent bytes differ" in str(write_error):
                continue
            raise
        return path
    raise RuntimeError("scope validation failure receipt filename collision")


def _scope_validation_failure_result(
    *,
    error: BaseException,
    observed: datetime,
) -> dict[str, object]:
    """將 scope 失敗轉成 terminal result，避免 scheduler 收到未處理例外。"""

    result: dict[str, object] = {
        "schema_version": PAPER_EXECUTION_SCHEMA_VERSION,
        "producer": "scripts.scheduled.run_paper_execution_daily_isolated",
        "observed_at": observed.isoformat(),
        "status": "failed",
        "terminal": True,
        "scope_validation_failed": True,
        "blockers": [
            "isolated_scope_manifest_validation_failed:"
            f"{type(error).__name__}:{error}"
        ],
        "candidate_only": True,
        "formal_ready": False,
        "formal_credit": False,
        "broker_execution": False,
        "writes_market_database": False,
        "scope_writer_targets_verified": False,
    }
    try:
        receipt_path = _write_scope_validation_failure_receipt(
            error=error,
            observed=observed,
        )
    except Exception as receipt_error:  # noqa: BLE001 - 失敗邊界不得向外冒泡
        result["receipt_write_error"] = (
            f"{type(receipt_error).__name__}:{receipt_error}"
        )
    else:
        result["terminal_failure_receipt_path"] = str(receipt_path)
    return result


def _sqlite_source_observation(
    path: Path,
    *,
    required_tables: set[str],
) -> dict[str, object]:
    """以 SQLite URI ``mode=ro`` 觀察來源，並確認讀取前後檔案 signature 不變。"""

    if path.expanduser().is_symlink():
        raise RuntimeError(f"isolated Paper source must not be a symlink:{path}")
    resolved = _resolved(path)
    if not resolved.is_file():
        raise RuntimeError(f"isolated Paper source is missing:{resolved}")
    before = _file_signature(resolved)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"file:{resolved.as_posix()}?mode=ro",
            uri=True,
        )
        connection.execute("PRAGMA query_only=ON")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(required_tables - tables)
        if missing:
            raise RuntimeError(
                f"isolated Paper source tables missing:{resolved}:{','.join(missing)}"
            )
    except sqlite3.Error as error:
        raise RuntimeError(
            f"isolated Paper source read failed:{resolved}:{type(error).__name__}"
        ) from error
    finally:
        if connection is not None:
            connection.close()
    after = _file_signature(resolved)
    if before != after:
        raise RuntimeError(f"isolated Paper source changed during read:{resolved}")
    return {
        "path": str(resolved),
        "mode": "ro/query_only",
        "file_signature": before,
        "required_tables": sorted(required_tables),
    }


def _scope_preflight() -> dict[str, object]:
    """驗證 source／target 路徑，且拒絕 D ledger 作為 writer target。"""

    write_scope = _validate_write_scope()
    candidate_root = write_scope["candidate_root"]
    receipt_root = write_scope["receipt_root"]
    ledger = write_scope["ledger_db"]
    state = _resolved(STATE_DB)
    market = _resolved(MARKET_DB)
    recommendation_root = _resolved(RECOMMENDATION_ROOT)
    calendar_cache_root = _resolved(_calendar_cache_root())
    if not _is_under(calendar_cache_root, _resolved(write_scope["operation_root"])):
        raise RuntimeError("isolated Paper calendar cache escaped operation root")
    if _is_under(calendar_cache_root, _resolved(DEFAULT_DATA_ROOT)):
        raise RuntimeError("isolated Paper calendar cache overlaps source data root")
    if calendar_cache_root.exists() and not calendar_cache_root.is_dir():
        raise RuntimeError("isolated Paper calendar cache root is not a directory")
    if ledger == _resolved(
        DEFAULT_DATA_ROOT / "output" / "paper_portfolio" / "paper_trade_ledger.sqlite"
    ):
        raise RuntimeError("isolated Paper ledger cannot target D source output")
    if ledger.exists() and not ledger.is_file():
        raise RuntimeError("isolated Paper ledger target is not a file")
    if not recommendation_root.is_dir():
        raise RuntimeError(f"isolated Paper recommendation root is missing:{recommendation_root}")
    state_seed = verify_repo_state_seed(
        target=state,
        manifest_path=_resolved(STATE_SEED_MANIFEST),
        source=_resolved(SOURCE_STATE_DB),
    )
    state_observation = _sqlite_source_observation(
        state,
        required_tables={"paper_portfolio_snapshots", "paper_portfolio_positions"},
    )
    market_observation = _sqlite_source_observation(
        market,
        required_tables={"daily_prices"},
    )
    cache_files: list[dict[str, object]] = []
    if calendar_cache_root.is_dir():
        for cache_file in sorted(calendar_cache_root.glob("*.json")):
            if not cache_file.is_file():
                raise RuntimeError(
                    f"isolated Paper calendar cache entry is not a file:{cache_file}"
                )
            resolved_cache_file = _resolved(cache_file)
            if not _is_under(resolved_cache_file, calendar_cache_root):
                raise RuntimeError(
                    f"isolated Paper calendar cache entry escaped root:{cache_file}"
                )
            if _is_under(resolved_cache_file, _resolved(DEFAULT_DATA_ROOT)):
                raise RuntimeError(
                    f"isolated Paper calendar cache entry overlaps source:{cache_file}"
                )
            cache_files.append(
                {
                    "path": str(resolved_cache_file),
                    "file_sha256": _file_hash(resolved_cache_file),
                }
            )
    return {
        "state": state_observation,
        "state_seed": state_seed,
        "market": market_observation,
        "recommendation_root": {
            "path": str(recommendation_root),
            "mode": "read_only_file_scan_by_queue_resolver",
        },
        "calendar_cache": {
            "path": str(calendar_cache_root),
            "mode": "hash_bound_official_annual_cache_read_only",
            "files": cache_files,
            "missing": not calendar_cache_root.exists(),
        },
        "ledger_target": {
            "path": str(ledger),
            "existing": ledger.is_file(),
            "mode": "append_only_research_paper_only",
        },
        "candidate_root": str(candidate_root),
        "receipt_root": str(receipt_root),
        "operation_root": str(write_scope["operation_root"]),
        "repository_output_root": str(write_scope["repository_output_root"]),
    }


def _pit_archive_root() -> Path:
    """Return the repository-owned durable PIT archive root.

    The scheduler resolves one exact manifest below this root and passes its
    path plus file hash to the Paper producer.  The ML archive consumer still
    receives the exact manifest; this helper never asks it to choose a latest
    entry on behalf of the producer.
    """

    return _resolved(ROOT / "output" / "formal_daily_publications" / "pit_candidate_archive")


def _resolve_pit_sector_manifest(
    observed: datetime,
) -> tuple[Path | None, str | None, dict[str, object]]:
    """Select one custody-verified PIT archive for the pending EOD queue.

    Selection is bounded to the durable archive's natural-day entries and is
    based on the archive consumer's final readback, including ``available_at``.
    The returned path and manifest hash are frozen inputs for the subsequent
    queue/producer call; no archive file is copied or rewritten.
    """

    root = _pit_archive_root()
    projection: dict[str, object] = {
        "root": str(root),
        "mode": "durable_pit_archive_exact_manifest_resolution",
        "observed_at": observed.isoformat(),
        "selected": False,
        "attempts": [],
    }

    if not root.is_dir() or root.is_symlink():
        projection["status"] = "archive_root_missing"
        return None, None, projection
    local_date = observed.astimezone(TAIPEI).date()
    try:
        manifests = sorted(root.glob("*/*/archive_manifest.json"))
    except OSError as error:
        projection["status"] = "archive_root_unreadable"
        projection["reason"] = f"{type(error).__name__}:{error}"
        return None, None, projection
    verified: list[tuple[date, datetime, datetime, Path, str, dict[str, object]]] = []
    for manifest in manifests:
        attempt: dict[str, object] = {
            "manifest_path": str(manifest),
            "selected": False,
        }
        try:
            relative = manifest.resolve().relative_to(root)
            if (
                len(relative.parts) != 3
                or relative.name != "archive_manifest.json"
                or date.fromisoformat(relative.parts[0]).isoformat() != relative.parts[0]
            ):
                raise ValueError("manifest path is outside natural-day archive shape")
            raw = manifest.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("archive manifest is not an object")
            effective = date.fromisoformat(str(payload.get("effective_from")))
            if effective > local_date:
                raise ValueError("archive effective_from is after observed Taipei date")
            # Let the ML consumer validate every archive role, current-code
            # attestation and immutable raw custody.  The scheduler only
            # records its returned availability and freezes the exact path.
            from ml_module.pit_archive_consumer import (  # noqa: PLC0415
                consume_pit_candidate_archive,
            )

            file_hash = _file_hash(manifest)
            consumed = consume_pit_candidate_archive(
                archive_root=root,
                manifest_path=manifest,
                expected_manifest_file_hash=file_hash,
                decision_at=observed,
                now=observed,
            )
            available_text = consumed.get("available_at")
            captured_text = consumed.get("captured_at")
            archived_text = consumed.get("archived_at")
            if (
                not isinstance(available_text, str)
                or not isinstance(captured_text, str)
                or not isinstance(archived_text, str)
            ):
                raise ValueError("archive consumer did not return complete clocks")
            available_at = datetime.fromisoformat(available_text)
            captured_at = datetime.fromisoformat(captured_text)
            archived_at = datetime.fromisoformat(archived_text)
            if available_at.tzinfo is None or captured_at.tzinfo is None or archived_at.tzinfo is None:
                raise ValueError("archive clocks must be timezone aware")
            available_at = available_at.astimezone(timezone.utc)
            captured_at = captured_at.astimezone(timezone.utc)
            archived_at = archived_at.astimezone(timezone.utc)
            attempt.update(
                {
                    "status": consumed.get("status"),
                    "effective_from": effective.isoformat(),
                    "available_at": available_at.isoformat(),
                    "captured_at": captured_at.isoformat(),
                    "archived_at": archived_at.isoformat(),
                    "manifest_file_hash": file_hash,
                    "archive_manifest_hash": consumed.get("archive_manifest_hash"),
                    "current_code_hash_match": consumed.get(
                        "current_code_hash_match"
                    ),
                    "code_hash_compatibility": consumed.get(
                        "code_hash_compatibility"
                    ),
                    "legacy_code_hash_compatibility_verified": consumed.get(
                        "legacy_code_hash_compatibility_verified"
                    ),
                }
            )
            verified.append(
                (
                    effective,
                    available_at,
                    captured_at,
                    manifest.resolve(),
                    file_hash,
                    consumed,
                )
            )
        except Exception as error:  # noqa: BLE001 - one bad archive cannot mask another
            attempt["status"] = "rejected"
            attempt["reason"] = f"{type(error).__name__}:{str(error).splitlines()[0][:220]}"
        attempts = projection["attempts"]
        if isinstance(attempts, list):
            attempts.append(attempt)
    if not verified:
        projection["status"] = "no_verified_archive"
        return None, None, projection
    selected = max(verified, key=lambda item: (item[0], item[1], item[2], str(item[3])))
    selected_date, selected_available, selected_captured, selected_path, selected_hash, consumed = selected
    projection.update(
        {
            "status": "selected",
            "selected": True,
            "manifest_path": str(selected_path),
            "manifest_file_hash": selected_hash,
            "archive_manifest_hash": consumed.get("archive_manifest_hash"),
            "archive_id": consumed.get("archive_id"),
            "current_code_hash_match": consumed.get("current_code_hash_match"),
            "code_hash_compatibility": consumed.get("code_hash_compatibility"),
            "legacy_code_hash_compatibility_verified": consumed.get(
                "legacy_code_hash_compatibility_verified"
            ),
            "effective_from": selected_date.isoformat(),
            "available_at": selected_available.isoformat(),
            "captured_at": selected_captured.isoformat(),
            "archived_at": consumed.get("archived_at"),
            "row_count": consumed.get("row_count"),
            "source_ids": consumed.get("source_ids"),
        }
    )
    return selected_path, selected_hash, projection


def _validate_runtime_paper_paths(
    runtime_config: Mapping[str, object] | None,
) -> None:
    """確認 active runtime config 與本 wrapper 的 canonical Paper state 相同。"""

    if runtime_config is None:
        return
    publication_value = runtime_config.get("publication_paths")
    if not isinstance(publication_value, Mapping):
        raise RuntimeError("runtime_config publication_paths missing")
    expected = {
        "paper_snapshot": _resolved(STATE_DB),
        "paper_fill_ledger": _resolved(LEDGER_DB),
    }
    for field, expected_path in expected.items():
        configured = publication_value.get(field)
        if not isinstance(configured, str) or not configured.strip():
            raise RuntimeError(f"runtime_config {field} path missing")
        if _resolved(Path(configured)) != expected_path:
            raise RuntimeError(
                f"runtime_config {field} does not match canonical Paper path"
            )


def _paper_event_source_blocked(
    result: Mapping[str, object],
    *,
    execution_date: str,
    reason: str,
) -> dict[str, object]:
    """保留 Paper ledger 結果，但阻止未綁 source 進 Formal。"""

    blocked = dict(result)
    blocker_value = result.get("blockers")
    blockers = (
        [item for item in blocker_value if isinstance(item, str)]
        if isinstance(blocker_value, list)
        else []
    )
    blockers.append(reason)
    blocked.update(
        {
            "status": "blocked",
            "blockers": blockers,
            "retryable": False,
            "execution_date": execution_date,
            "execution_event_time_proven": False,
            "formal_eligible": False,
            "formal_ready": False,
            "formal_consumer_compatible": False,
            "formal_credit": False,
            "candidate_only": True,
            "research_only": True,
            "paper_event_source_binding": {
                "status": "blocked",
                "required": True,
                "formal_eligible": False,
                "reason": reason,
            },
        }
    )
    return blocked


def _bind_paper_result_to_event_capture(
    result: Mapping[str, object],
    *,
    observed: datetime,
) -> dict[str, object]:
    """由 EOD writer 消費同一 recommendation 的 durable event capture。"""

    if result.get("status") == "blocked":
        # 政策／來源已拒絕的候選沒有 fills；保留原原因，不授事件綁定或成交資格。
        return dict(result)

    candidate_value = result.get("candidate_path")
    recommendation_value = result.get("recommendation")
    execution_value = result.get("execution_date")
    if (
        not isinstance(candidate_value, str)
        or not candidate_value.strip()
        or not isinstance(recommendation_value, Mapping)
        or not isinstance(execution_value, str)
    ):
        # Queue waiting/skipped records do not contain a frozen candidate; the
        # queue receipt remains the source of truth for that state.
        return dict(result)
    try:
        execution_date = date.fromisoformat(execution_value)
        candidate_path = Path(candidate_value).expanduser().resolve()
        if not _is_under(candidate_path, _resolved(CANDIDATE_ROOT)):
            raise PaperEventSourceCaptureError(
                "Paper candidate path escaped controlled candidate root"
            )
        recommendation_path_value = recommendation_value.get("path")
        if not isinstance(recommendation_path_value, str) or not recommendation_path_value.strip():
            raise PaperEventSourceCaptureError(
                "Paper recommendation path missing"
            )
        capture = resolve_persisted_twse_event_source_capture_for_recommendation(
            recommendation_path=Path(recommendation_path_value),
            execution_date=execution_date,
            durable_root=EVENT_CAPTURE_ROOT,
            observed=observed,
            allowed_durable_root=OPERATIONAL_ROOT,
        )
    except (
        PaperEventSourceCaptureError,
        OSError,
        TypeError,
        ValueError,
        KeyError,
    ) as error:
        return _paper_event_source_blocked(
            result,
            execution_date=execution_value,
            reason=(
                "paper_event_source_capture_invalid:"
                f"{type(error).__name__}:{error}"
            ),
        )
    if capture is None:
        return _paper_event_source_blocked(
            result,
            execution_date=execution_value,
            reason="paper_event_source_capture_missing_durable_manifest",
        )
    manifest_value = capture.get("manifest_path")
    if not isinstance(manifest_value, str) or not manifest_value.strip():
        return _paper_event_source_blocked(
            result,
            execution_date=execution_value,
            reason="paper_event_source_capture_manifest_path_missing",
        )
    bound_path = candidate_path.with_name("paper_execution_candidate_bound.json")
    try:
        bound = bind_paper_candidate_file_to_capture(
            candidate_path,
            capture_manifest_path=Path(manifest_value),
            output_path=bound_path,
            allowed_output_root=_resolved(ROOT / "output"),
        )
    except (PaperEventSourceCaptureError, OSError, TypeError, ValueError) as error:
        return _paper_event_source_blocked(
            result,
            execution_date=execution_value,
            reason=(
                "paper_event_source_binding_failed:"
                f"{type(error).__name__}:{error}"
            ),
        )
    merged = {**dict(result), **bound}
    merged["paper_event_source_binding"] = {
        "status": "bound",
        "required": True,
        "formal_eligible": False,
        "capture_manifest_path": manifest_value,
        "capture_manifest_file_hash": capture.get("manifest_file_hash"),
        "capture_raw_response_hash": capture.get("raw_response_hash"),
        "recommendation_file_hash": recommendation_value.get("file_hash"),
        "execution_date": execution_value,
        "readback_verified": bound.get("bound_candidate_readback_verified") is True,
        "credit_policy": "formal_credit_remains_false_until_three_source_handoff",
    }
    # The binding helper sets formal_consumer_compatible only after rows and
    # prices are rebuilt from durable raw bytes. Formal credit remains false.
    merged["formal_credit"] = False
    merged["formal_ready"] = False
    return merged


def _paths(
    observed: datetime | None = None,
    *,
    sector_resolution: tuple[Path | None, str | None, dict[str, object]] | None = None,
) -> PaperExecutionPaths:
    selected = sector_resolution
    if selected is None:
        selected = _resolve_pit_sector_manifest(
            observed or datetime.now(timezone.utc)
        )
    return PaperExecutionPaths(
        recommendation_json=RECOMMENDATION_ROOT / "__queue_selection__.json",
        state_db=STATE_DB,
        market_db=MARKET_DB,
        output_root=_new_candidate_root(),
        ledger_db=LEDGER_DB,
        controlled_output_root=CANDIDATE_ROOT,
        sector_membership_path=selected[0],
        sector_membership_file_hash=selected[1],
    )


def _write_scope_blocked_result(
    *,
    paths: PaperExecutionPaths,
    observed: datetime,
    blockers: list[str],
    scope_manifest_path: Path,
    scope_manifest_file_hash: str,
) -> dict[str, object]:
    """把 scope preflight 失敗保存為 candidate／receipt，維持可觀測性。"""

    output_root = paths.output_root
    output_root.mkdir(parents=True, exist_ok=False)
    body: dict[str, object] = {
        "schema_version": PAPER_EXECUTION_SCHEMA_VERSION,
        "producer": "scripts.scheduled.run_paper_execution_daily_isolated",
        "producer_version": PAPER_EXECUTION_PRODUCER_VERSION,
        "observed_at": observed.isoformat(),
        "status": "blocked",
        "blockers": blockers,
        "candidate_only": True,
        "formal_ready": False,
        "formal_consumer_compatible": False,
        "formal_credit": False,
        "research_only": True,
        "broker_order_allowed": False,
        "broker_execution": False,
        "writes_formal_controlled_paths": False,
        "writes_market_database": False,
        "training_started": False,
        "historical_backfill_claimed": False,
        "append_requested": True,
        "scope_manifest_path": str(scope_manifest_path),
        "scope_manifest_file_hash": scope_manifest_file_hash,
        "repository_state": {
            "path": str(_resolved(STATE_DB)),
            "read_mode": "sqlite_uri_mode_ro_and_query_only",
            "seed_manifest_path": str(_resolved(STATE_SEED_MANIFEST)),
        },
        "ledger": {
            "path": str(_resolved(LEDGER_DB)),
            "append_requested": True,
            "appended": False,
            "readback_verified": False,
        },
    }
    body["content_sha256"] = _payload_hash(body)
    candidate_path = output_root / "paper_execution_candidate.json"
    encoded = (_canonical_json(body) + "\n").encode("utf-8")
    with candidate_path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        import os

        os.fsync(stream.fileno())
    result = {
        **body,
        "candidate_path": str(candidate_path),
        "candidate_file_hash": _file_hash(candidate_path),
    }
    return persist_operational_receipt(
        result,
        RECEIPT_ROOT,
        observed=observed,
    )


def run_isolated(*, now: datetime | None = None) -> dict[str, object]:
    """執行一次完整 EOD writer；``now`` 僅供隔離測試固定觀測時刻。"""

    observed = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    runtime_config: dict[str, object] | None = None
    try:
        runtime_config = load_optional_formal_runtime_config(
            role="paper_eod_wrapper",
            observed=observed,
        )
    except FormalRuntimeConfigError as error:
        return {
            "schema_version": PAPER_EXECUTION_SCHEMA_VERSION,
            "producer": "scripts.scheduled.run_paper_execution_daily_isolated",
            "observed_at": observed.isoformat(),
            "status": "blocked",
            "blockers": [f"runtime_config_invalid:{error}"],
            "runtime_config": {
                "status": "invalid",
                "environment_variable": FORMAL_RUNTIME_CONFIG_ENV,
            },
            "candidate_only": True,
            "formal_ready": False,
            "formal_credit": False,
            "broker_execution": False,
            "writes_market_database": False,
        }
    if runtime_config is not None and runtime_config.get("activation_status") != "active":
        return {
            "schema_version": PAPER_EXECUTION_SCHEMA_VERSION,
            "producer": "scripts.scheduled.run_paper_execution_daily_isolated",
            "observed_at": observed.isoformat(),
            "status": "waiting_for_runtime_config",
            "blockers": [
                "runtime_config_waiting_for_activation:"
                f"{runtime_config.get('activation_trading_day')}"
            ],
            "runtime_config": runtime_config,
            "candidate_only": True,
            "formal_ready": False,
            "formal_credit": False,
            "broker_execution": False,
            "writes_market_database": False,
        }
    try:
        _validate_runtime_paper_paths(runtime_config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        return {
            "schema_version": PAPER_EXECUTION_SCHEMA_VERSION,
            "producer": "scripts.scheduled.run_paper_execution_daily_isolated",
            "observed_at": observed.isoformat(),
            "status": "blocked",
            "blockers": [
                f"runtime_config_canonical_paper_path_failed:{type(error).__name__}:{error}"
            ],
            "runtime_config": runtime_config,
            "candidate_only": True,
            "formal_ready": False,
            "formal_consumer_compatible": False,
            "formal_credit": False,
            "broker_execution": False,
            "writes_market_database": False,
        }
    try:
        scope_manifest_path, scope_manifest_file_hash = _write_or_verify_scope_manifest()
    except Exception as error:  # noqa: BLE001 - scope 失敗必須轉成 terminal receipt
        return _scope_validation_failure_result(
            error=error,
            observed=observed,
        )
    sector_resolution: tuple[Path | None, str | None, dict[str, object]] = (
        None, None, {"status": "pending_frozen_queue_selection"}
    )
    paths = _paths(observed, sector_resolution=sector_resolution)
    try:
        source_observation = _scope_preflight()
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        return _write_scope_blocked_result(
            paths=paths,
            observed=observed,
            blockers=[f"isolated_scope_preflight_failed:{type(error).__name__}:{error}"],
            scope_manifest_path=scope_manifest_path,
            scope_manifest_file_hash=scope_manifest_file_hash,
        )
    try:
        if paths.ledger_db is None:  # pragma: no cover - 隔離路徑固定存在
            raise RuntimeError("isolated Paper ledger path is missing")
        ledger_schema = ensure_paper_ledger_schema(paths.ledger_db)
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
        return _write_scope_blocked_result(
            paths=paths,
            observed=observed,
            blockers=[
                "isolated_paper_ledger_schema_initialization_failed:"
                f"{type(error).__name__}:{error}"
            ],
            scope_manifest_path=scope_manifest_path,
            scope_manifest_file_hash=scope_manifest_file_hash,
        )
    source_observation["sector_membership_source"] = sector_resolution[2]
    source_observation["paper_ledger_schema"] = ledger_schema
    calendar_refresh = _refresh_calendar_cache(observed)
    temporary_closure_refresh = _refresh_temporary_closure_events(observed)
    refresh_receipt_path = _write_calendar_refresh_receipt(
        {
            "annual_calendar": calendar_refresh,
            "temporary_closure_events": temporary_closure_refresh,
        },
        observed=observed,
    )
    source_observation["calendar_refresh"] = calendar_refresh
    source_observation["temporary_closure_refresh"] = temporary_closure_refresh
    source_observation["calendar_refresh_receipt"] = {
        "path": str(refresh_receipt_path),
        "file_sha256": _file_hash(refresh_receipt_path),
    }
    source_observation["formal_runtime_config"] = (
        runtime_config
        if runtime_config is not None
        else {
            "status": "absent",
            "environment_variable": FORMAL_RUNTIME_CONFIG_ENV,
        }
    )
    calendar = OfficialTradingCalendar(
        db_path=MARKET_DB,
        calendar_cache_path=_calendar_cache_root(),
        temporary_closure_path=_calendar_cache_root(),
    )
    def resolve_frozen_sector(identity: Mapping[str, str]) -> tuple[Path | None, str | None]:
        freeze = datetime.fromisoformat(identity["created_at"])
        if freeze.tzinfo is None or freeze > observed:
            raise ValueError("Paper frozen recommendation clock invalid")
        selected_sector = _resolve_pit_sector_manifest(freeze)
        source_observation["sector_membership_source"] = selected_sector[2]
        return selected_sector[0], selected_sector[1]

    result = run_paper_execution_daily_from_queue(
        paths,
        recommendation_root=RECOMMENDATION_ROOT,
        receipt_root=RECEIPT_ROOT,
        now=observed,
        calendar=calendar,
        confirm_append=True,
        persist_receipt=False,
        recommendation_pattern="paper_frozen_*.json",
        sector_source_resolver=resolve_frozen_sector,
    )
    result = _bind_paper_result_to_event_capture(result, observed=observed)
    persisted_result = persist_operational_receipt(
        result,
        RECEIPT_ROOT,
        observed=observed,
    )
    return {
        **persisted_result,
        "runtime_config": runtime_config,
        "isolated_scope": {
            "scope_manifest_path": str(scope_manifest_path),
            "scope_manifest_file_hash": scope_manifest_file_hash,
            "source_observation": source_observation,
            "append_target": str(_resolved(LEDGER_DB)),
            "append_target_is_d_source": False,
            "repository_state_db": str(_resolved(STATE_DB)),
            "source_state_db": str(_resolved(SOURCE_STATE_DB)),
            "event_capture_root": str(_resolved(EVENT_CAPTURE_ROOT)),
            "repository_state_read_mode": "sqlite_uri_mode_ro_and_query_only",
            "environment_path_overrides_ignored": True,
            "formal_credit": False,
            "broker_execution": False,
            "writes_market_database": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="執行固定 repository scope 的研究用 Paper EOD replay。"
    ).parse_args(argv)
    try:
        result = run_isolated()
    except Exception as error:  # noqa: BLE001 - scheduled boundary is fail-closed
        result = {
            "schema_version": SCOPE_SCHEMA_VERSION,
            "producer": "scripts.scheduled.run_paper_execution_daily_isolated",
            "status": "blocked",
            "blockers": [
                f"isolated_paper_execution_failed:{type(error).__name__}:{error}"
            ],
            "candidate_only": True,
            "formal_ready": False,
            "formal_credit": False,
            "broker_execution": False,
            "writes_market_database": False,
        }
    _print_json(result)
    return 0 if str(result.get("status")) in {
        "machine_verified_candidate",
        "no_trade_required_candidate",
        "skipped_non_trading_day",
        "skipped_no_pending_recommendation",
        "waiting_for_execution_session",
        "waiting_for_execution_source",
    } else 2


def _print_json(value: Mapping[str, object]) -> None:
    """在 Windows 非 UTF-8 console 仍輸出完整的中文 custody 結果。"""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    try:
        sys.stdout.write(encoded.decode())
    except UnicodeEncodeError:
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is None:
            sys.stdout.write(encoded.decode("utf-8"))
        else:
            buffer.write(encoded)
            buffer.flush()


if __name__ == "__main__":
    raise SystemExit(main())
