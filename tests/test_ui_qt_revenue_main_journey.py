"""保存 F12 Main 旅程與私人 Watchlist 唯讀角色證據。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import faulthandler
from pathlib import Path
import re
import sqlite3
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextvars import ContextVar
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app_module.personal_watchlist_service import (
    PersonalWatchlistSelectionError,
    PersonalWatchlistService,
)
from data_module import watchlist_repository as watchlist_repository_module
from data_module.config import TWStockConfig
from data_module.watchlist_repository import WatchlistRepository


MAIN_INITIALIZATION_DEADLINE_SECONDS = 600.0
MAIN_JOURNEY_TOTAL_DEADLINE_SECONDS = 2400.0
FRESH_CHILD_PROCESS_TIMEOUT_SECONDS = 600.0
FRESH_CHILD_QUERY_PHASE_TIMEOUT_SECONDS = 480.0
FRESH_CHILD_RECEIPT_PREFIX = "F12_FRESH_MAIN_RECEIPT:"
FRESH_CHILD_ERROR_TAIL_BYTES = 4000
F12_GUARD_DIAGNOSTIC_STACK_LIMIT = 12
F12_SYNTHETIC_ROOT_NAME = "synthetic_main_42f484b9f27b47328b7d268a866cc755"
F12_UNSET_STARTUP_ENVIRONMENT = (
    "TECHNICAL_UNIVERSE_READ_ROOT",
    "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT",
    "FUNDAMENTAL_READ_SNAPSHOT_ROOT",
    "PERSONAL_H20_SQLITE_READ_ROOT",
    "FORMAL_DAILY_RUNTIME_CONFIG",
    "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
    "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE",
    "FORMAL_DAILY_RUNTIME_ROLL_FORWARD_ROOT",
    "FORMAL_DAILY_MARKET_DB",
    "FORMAL_DAILY_RULE_BASELINE_ROOT",
    "FORMAL_DAILY_CALENDAR_CACHE_ROOT",
    "FORMAL_DAILY_PUBLICATION_ROOT",
    "FORMAL_DAILY_RULE_SOURCE_ROOT",
    "FORMAL_DAILY_PIT_PREOPEN_ARCHIVE_ROOT",
    "FORMAL_DAILY_PAPER_SNAPSHOT_DB",
    "FORMAL_DAILY_PAPER_TRADE_LEDGER_DB",
    "FORMAL_DAILY_PAPER_RECEIPT_ROOT",
    "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
    "BALDR_PYTHON",
)
F12_EMPTY_STARTUP_ENVIRONMENT = (
    "PERSONAL_JOURNAL_ROOT",
    "PERSONAL_JOURNAL_MODE",
    "PERSONAL_STORE_ROOT",
    "PERSONAL_STORE_MODE",
    "PERSONAL_MODEL_POLICY_PATH",
    "OFFICIAL_CALENDAR_CACHE_PATH",
    "PIT_SECTOR_MEMBERSHIP_PATH",
    "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
    "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
    "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
    "PIT_MEMBERSHIP_EXPECTED_CLASSIFICATION_VERSION",
    "PIT_MARKET_SCOPE",
    "PERSONAL_H20_ACTIVATION_CONFIG",
    "RESEARCH_CONSOLE_PROJECTION",
    "P0_SOURCE_CONTROL_CENTER_AUDIT",
    "P0_SOURCE_CONTROL_CENTER_DECISIONS",
    "P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE",
    "PROGRAM_READINESS_ARTIFACT",
    "MONTHLY_REVENUE_AVAILABILITY_CANDIDATE",
    "DATA_UPDATE_STATUS_ARTIFACT",
    "DATA_FRESHNESS_STATUS_ARTIFACT",
    "DATA_UPDATE_HISTORY_ARTIFACT",
    "TPEX_REFRESH_STATUS_ARTIFACT",
    "EVIDENCE_REHEARSAL_REPORT",
    "WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH",
    "PAPER_EQUAL_WEIGHT_BENCHMARK_PATH",
    "PAPER_TRADE_LEDGER_PATH",
    "MONTHLY_REVENUE_SNAPSHOT_CANDIDATE",
    "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "FINMIND_TOKEN",
)
_F12_FD_GUARD_EVENTS: list[dict[str, Any]] = []
# 只供隔離 descriptor fixture 注入 constructor 失敗；正式旅程維持 None。
_F12_FDOPEN_DUPLICATE_FAILURE_HOOK: Any | None = None
_F12_FD_GUARD_DESCRIPTOR_COUNT_GETTER: Any | None = None


def _f12_guarded_descriptor_record_count() -> int:
    """只讀取得目前 guard 記錄數，不暴露 descriptor map 或 handle。"""

    getter = _F12_FD_GUARD_DESCRIPTOR_COUNT_GETTER
    if not callable(getter):
        raise RuntimeError("F12 descriptor guard 尚未安裝唯讀 count probe")
    count = getter()
    if type(count) is not int or count < 0:
        raise AssertionError("F12 descriptor guard count probe 回傳非法值")
    return count


@pytest.fixture(scope="module")
def f12_synthetic_sources() -> dict[str, Any]:
    """只讀載入明示的 F12 全母體 F17 與 current-only 月營收來源。"""

    from app_module.daily_market_technical_official_disposition_bundle_catalog_v1 import (
        DailyMarketTechnicalOfficialDispositionBundleCatalogV1,
    )
    from data_module.daily_market_monthly_revenue_read_session_v1 import (
        DailyMarketMonthlyRevenueSourceReferenceV2,
    )

    repository_root = Path(__file__).resolve().parents[1]
    f12_root = repository_root / "output" / "qa" / "f12_resume_20261011"
    f12_root.mkdir(parents=True, exist_ok=True)

    requested_root = os.environ.get("F12_SYNTHETIC_ROOT", "").strip()
    if not requested_root:
        raise AssertionError("F12_SYNTHETIC_ROOT 必須明示指定；禁止 latest-glob 或自動替代來源")
    candidate_root = Path(requested_root).resolve(strict=False)
    if not candidate_root.is_dir():
        raise AssertionError(f"明示的 F12 synthetic root 不存在：{candidate_root}")
    if candidate_root.name != F12_SYNTHETIC_ROOT_NAME:
        raise AssertionError(f"F12 source root 未經核准：{candidate_root}")
    if candidate_root.parent != f12_root.resolve():
        raise AssertionError(f"F12 source root 不在本任務 QA 根目錄：{candidate_root}")

    prior_reference_path = candidate_root / "monthly-source-reference.json"
    prior_bundle_root = (
        candidate_root
        / "f17"
        / "technical-output"
        / "research_snapshots"
        / "daily_market_technical_official_disposition_v1"
    )
    if not prior_reference_path.is_file() or not prior_bundle_root.is_dir():
        raise AssertionError(f"明示的 F12 synthetic source 缺件：{candidate_root}")
    catalog_page = DailyMarketTechnicalOfficialDispositionBundleCatalogV1(
        prior_bundle_root.resolve()
    ).list_page(limit=10)
    entries = [entry for entry in catalog_page.entries if entry.can_attempt_exact_read]
    if (
        not catalog_page.scan_complete
        or len(entries) != 1
        or entries[0].metadata is None
        or entries[0].metadata.declared_count != 258
    ):
        raise AssertionError(f"明示的 F12 F17 catalog 不符合既有全母體 pin：{candidate_root}")
    monthly_reference = DailyMarketMonthlyRevenueSourceReferenceV2.from_json(
        prior_reference_path.read_text(encoding="utf-8")
    )
    if len(monthly_reference.declared_stock_codes) != 258:
        raise AssertionError(f"明示的 F12 月營收 reference 不完整：{candidate_root}")
    metadata = entries[0].metadata
    bundle = SimpleNamespace(
        bundle_root=prior_bundle_root.resolve(),
        reference=SimpleNamespace(
            bundle_identity_sha256=metadata.bundle_identity_sha256,
            manifest_sha256=metadata.manifest_sha256,
        ),
    )
    return {
        "root": candidate_root,
        "bundle": bundle,
        "monthly_reference": monthly_reference,
        "monthly_reference_path": prior_reference_path,
        "stock_codes": monthly_reference.declared_stock_codes,
    }


def _main_window_environment(
    run_root: Path,
    *,
    qa_root: Path | None = None,
) -> dict[str, str]:
    data_root = run_root / "market-data"
    output_root = run_root / "application-output"
    profile = "test"
    configured_output_root = output_root / "_test" if profile == "test" else output_root
    personal_root = run_root / "personal-data"
    profile_root = run_root / "user-profile"
    source_path = configured_output_root / "watchlist" / "default.json"
    local_profile = profile_root / "local"
    roaming_profile = profile_root / "roaming"
    xdg_config = profile_root / "xdg-config"
    xdg_cache = profile_root / "xdg-cache"
    xdg_data = profile_root / "xdg-data"
    qa_isolation_root = qa_root or (
        Path(__file__).resolve().parents[1]
        / "output"
        / "qa"
        / "f12_resume_20261011"
    )
    runtime_binding_sentinel = (
        qa_isolation_root / f"{run_root.name}-runtime-binding-disabled.json"
    )
    for path in (
        data_root,
        output_root,
        personal_root,
        profile_root,
        local_profile,
        roaming_profile,
        xdg_config,
        xdg_cache,
        xdg_data,
    ):
        path.mkdir(parents=True, exist_ok=True)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    if not source_path.exists():
        source_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "name": "F12 isolated synthetic source",
                    "description": "Full Main revenue bookmark journey",
                    "created_at": "2026-10-11T00:00:00+08:00",
                    "updated_at": "2026-10-11T00:00:00+08:00",
                    "items": [],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return {
        "DATA_ROOT": str(data_root),
        "OUTPUT_ROOT": str(output_root),
        "PROFILE": profile,
        "PERSONAL_DATA_ROOT": str(personal_root),
        "PERSONAL_WATCHLIST_SOURCE": str(source_path),
        "USERPROFILE": str(profile_root),
        "HOME": str(profile_root),
        "LOCALAPPDATA": str(local_profile),
        "APPDATA": str(roaming_profile),
        "XDG_CONFIG_HOME": str(xdg_config),
        "XDG_CACHE_HOME": str(xdg_cache),
        "XDG_DATA_HOME": str(xdg_data),
        "RESEARCH_STATE_ROOT": str(profile_root / "research-state"),
        "TEMP": str(run_root / "temp"),
        "TMP": str(run_root / "temp"),
        "MPLCONFIGDIR": str(run_root / "matplotlib"),
        "BALDR_CONFIG": str(profile_root / "baldr-config.json"),
        "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE": str(runtime_binding_sentinel),
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
    }


def _isolated_environment(base: dict[str, str], overrides: dict[str, str]) -> dict[str, str]:
    result = dict(base)
    for name in F12_UNSET_STARTUP_ENVIRONMENT:
        result.pop(name, None)
    result.update(overrides)
    for name in F12_EMPTY_STARTUP_ENVIRONMENT:
        result[name] = ""
    return result


def _write_json_create_only(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _f12_guard_target_scope(
    raw_path: object,
    *,
    qa_root: Path,
    run_root: Path,
    synthetic_root: Path,
) -> dict[str, Any]:
    """回報拒寫目標的角色相對位置或不可逆識別，不改變寫入授權。"""

    if not isinstance(raw_path, (str, bytes, os.PathLike)):
        return {"target_scope": "non_path_target", "target_relative": None}
    raw_text: str | None = None
    try:
        raw_text = os.fsdecode(os.fspath(raw_path))
        diagnostic_text = _f12_strip_internal_io_prefix(raw_text)
        diagnostic_unc_or_device_text = diagnostic_text.replace("/", "\\")
        if os.name == "nt" and diagnostic_unc_or_device_text.startswith("\\\\"):
            return {
                "target_scope": "external_unc_or_device_path",
                "target_relative": None,
                **_f12_unscoped_target_identity(diagnostic_unc_or_device_text),
            }
        candidate = Path(diagnostic_text)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError, TypeError, ValueError):
        return {
            "target_scope": "unresolved_target",
            "target_relative": None,
            **_f12_unscoped_target_identity(raw_text),
        }

    scoped_roots = (
        ("qa_private_write_root", qa_root),
        ("private_run_write_root", run_root),
        ("synthetic_read_only_source_root", synthetic_root),
        ("qa_evidence_scope_only", qa_root.parent),
    )
    for role, root in scoped_roots:
        if not _path_is_within(candidate, root):
            continue
        try:
            relative = candidate.relative_to(root.resolve(strict=False)).as_posix()
        except (OSError, RuntimeError, ValueError):
            return {
                "target_scope": "unresolved_target",
                "target_relative": None,
                **_f12_unscoped_target_identity(diagnostic_text),
            }
        result: dict[str, Any] = {
            "target_scope": role,
            "target_relative": relative,
        }
        return result
    return {
        "target_scope": "outside_manifest_roots",
        "target_relative": None,
        **_f12_unscoped_target_identity(diagnostic_text),
    }


def _f12_strip_internal_io_prefix(path_text: str) -> str:
    """只供診斷分類使用；不把 extended path 正規化用於寫入授權。"""

    if os.name != "nt":
        return path_text
    folded = path_text.casefold()
    unc_prefix = "\\\\?\\unc\\"
    if folded.startswith(unc_prefix):
        return "\\\\" + path_text[len(unc_prefix):]
    if folded.startswith("\\\\?\\"):
        return path_text[4:]
    return path_text


def _f12_unscoped_target_identity(path_text: str | None) -> dict[str, Any]:
    """為未知角色目標記錄 basename 與完整路徑雜湊，不保存絕對路徑。"""

    if not isinstance(path_text, str) or not path_text:
        return {"target_basename": None, "target_path_sha256": None}
    normalized = os.path.normpath(path_text)
    if os.name == "nt":
        normalized = os.path.normcase(normalized)
    return {
        "target_basename": Path(normalized).name or None,
        "target_path_sha256": hashlib.sha256(
            normalized.encode("utf-8", errors="surrogatepass")
        ).hexdigest(),
    }


def _f12_guard_callsite_stack() -> list[dict[str, Any]]:
    """保存有限的 repository-relative 呼叫點，不讀取 locals 或原始碼行。"""

    repository_root = Path(__file__).resolve().parents[1]
    repository_root_text = os.path.normcase(os.path.abspath(str(repository_root)))
    stack: list[dict[str, Any]] = []
    frame = sys._getframe(1)
    scanned = 0
    while (
        frame is not None
        and len(stack) < F12_GUARD_DIAGNOSTIC_STACK_LIMIT
        and scanned < F12_GUARD_DIAGNOSTIC_STACK_LIMIT * 8
    ):
        scanned += 1
        filename = frame.f_code.co_filename
        if isinstance(filename, str) and filename and not filename.startswith("<"):
            try:
                absolute_filename = os.path.normcase(os.path.abspath(filename))
                if os.path.commonpath(
                    (repository_root_text, absolute_filename)
                ) == repository_root_text:
                    relative_filename = os.path.relpath(
                        absolute_filename,
                        repository_root_text,
                    ).replace("\\", "/")
                    module_name = frame.f_globals.get("__name__")
                    stack.append(
                        {
                            "module": (
                                module_name[:180]
                                if isinstance(module_name, str)
                                else None
                            ),
                            "file": relative_filename,
                            "function": frame.f_code.co_name[:180],
                            "line": int(frame.f_lineno),
                        }
                    )
            except (OSError, RuntimeError, TypeError, ValueError):
                pass
        frame = frame.f_back
    return stack


def _f12_guard_rejection_event(
    *,
    reason: str,
    path_role: str,
    audit_event: str | None,
    audit_operation: str | None,
    audit_event_observed: bool | None,
    guard_operation: str,
    raw_path: object,
    error: BaseException,
    qa_root: Path,
    run_root: Path,
    synthetic_root: Path,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event": "write_path_rejected",
        "reason": reason,
        "path_role": path_role,
        "audit_event": audit_event,
        "audit_operation": audit_operation,
        "audit_event_observed": audit_event_observed,
        "guard_operation": guard_operation,
        "errno": getattr(error, "errno", None),
        "winerror": getattr(error, "winerror", None),
        "thread_id": threading.get_ident(),
        "clock_monotonic_ns": time.monotonic_ns(),
    }
    event.update(
        _f12_guard_target_scope(
            raw_path,
            qa_root=qa_root,
            run_root=run_root,
            synthetic_root=synthetic_root,
        )
    )
    event["callsite_stack"] = _f12_guard_callsite_stack()
    return event


def _f12_safe_guard_event(event: dict[str, Any]) -> dict[str, Any]:
    """只複製不含絕對檔案位置的守衛事件欄位。"""

    safe_fields = {
        "event",
        "reason",
        "path_role",
        "audit_event",
        "audit_operation",
        "audit_event_observed",
        "guard_operation",
        "errno",
        "winerror",
        "thread_id",
        "clock_monotonic_ns",
        "target_scope",
        "target_relative",
        "target_basename",
        "target_path_sha256",
        "regular_file",
        "write_capable",
        "win_identity_verified",
        "handle_link_count",
        "canonical_path_api",
        "descriptor_number",
        "os_close_succeeded",
        "tracking_removed",
        "exception_type",
        "duplicate_descriptor",
        "caller_descriptor_retained",
        "identity_rechecked",
        "source_and_duplicate_identity_match",
        "caller_descriptor",
        "stream_descriptor",
        "stream_owns_duplicate",
        "duplicate_closed",
        "duplicate_tracking_removed",
        "stale_duplicate_record_absent",
        "current_descriptor_tracking_preserved",
        "current_descriptor_matches_duplicate",
        "descriptor_number_reused",
        "replacement_descriptor_preserved",
        "cleanup_action",
    }
    safe_event = {
        key: value
        for key, value in event.items()
        if key in safe_fields
        and (value is None or isinstance(value, (str, int, bool)))
    }
    callsite_stack = event.get("callsite_stack")
    if isinstance(callsite_stack, list):
        safe_frames: list[dict[str, Any]] = []
        for frame in callsite_stack[:F12_GUARD_DIAGNOSTIC_STACK_LIMIT]:
            if not isinstance(frame, dict):
                continue
            module_name = frame.get("module")
            filename = frame.get("file")
            function = frame.get("function")
            line = frame.get("line")
            if (
                isinstance(module_name, str)
                and isinstance(filename, str)
                and isinstance(function, str)
                and type(line) is int
                and not Path(filename).is_absolute()
                and ".." not in Path(filename).parts
            ):
                safe_frames.append(
                    {
                        "module": module_name[:180],
                        "file": filename[:320],
                        "function": function[:180],
                        "line": line,
                    }
                )
        safe_event["callsite_stack"] = safe_frames
    return safe_event


def _persist_f12_query_guard_receipt(
    path: Path,
    payload: dict[str, Any],
) -> Exception | None:
    """寫診斷收據；診斷寫入失敗不得取代原本的旅程錯誤。"""

    try:
        _write_json_create_only(path, payload)
    except Exception as diagnostic_error:
        return diagnostic_error
    return None


def test_f12_guard_rejection_records_audit_label_and_role_relative_target(
    tmp_path: Path,
) -> None:
    """守衛拒絕收據保留 audit 標籤與合成 QA 根內的相對目標。"""

    qa_root = tmp_path / "qa" / "attempt"
    run_root = tmp_path / "isolated-run"
    synthetic_root = tmp_path / "synthetic-source"
    denied_target = qa_root.parent / "pytest-tmp" / "archive" / "source.sqlite"
    error = PermissionError(13, "guarded test rejection")
    event = _f12_guard_rejection_event(
        reason="outside_allowed_private_root",
        path_role="outside_manifest_roots",
        audit_event="open",
        audit_operation="python.audit:open",
        audit_event_observed=True,
        guard_operation="python.audit:open",
        raw_path=denied_target,
        error=error,
        qa_root=qa_root,
        run_root=run_root,
        synthetic_root=synthetic_root,
    )

    assert event["audit_event"] == "open"
    assert event["audit_operation"] == "python.audit:open"
    assert event["audit_event_observed"] is True
    assert event["guard_operation"] == "python.audit:open"
    assert event["target_scope"] == "qa_evidence_scope_only"
    assert event["target_relative"] == "pytest-tmp/archive/source.sqlite"
    assert event["callsite_stack"]
    assert len(event["callsite_stack"]) <= F12_GUARD_DIAGNOSTIC_STACK_LIMIT
    assert all(
        set(frame) == {"module", "file", "function", "line"}
        and not Path(frame["file"]).is_absolute()
        and ".." not in Path(frame["file"]).parts
        for frame in event["callsite_stack"]
    )
    assert "target_private_canonical_path" not in event
    safe_event = _f12_safe_guard_event(
        {
            **event,
            "target_path": str(denied_target),
            "private_detail": {"path": str(denied_target)},
        }
    )
    assert safe_event["target_relative"] == "pytest-tmp/archive/source.sqlite"
    assert safe_event["callsite_stack"] == event["callsite_stack"]
    assert "target_path" not in safe_event
    assert "private_detail" not in safe_event
    assert str(denied_target) not in json.dumps(safe_event)
    private_target = run_root / "revenue-operations" / "snapshot.sqlite"
    private_scope = _f12_guard_target_scope(
        private_target,
        qa_root=qa_root,
        run_root=run_root,
        synthetic_root=synthetic_root,
    )
    assert private_scope == {
        "target_scope": "private_run_write_root",
        "target_relative": "revenue-operations/snapshot.sqlite",
    }
    source_scope = _f12_guard_target_scope(
        synthetic_root / "monthly-source" / "snapshot.csv",
        qa_root=qa_root,
        run_root=run_root,
        synthetic_root=synthetic_root,
    )
    assert source_scope == {
        "target_scope": "synthetic_read_only_source_root",
        "target_relative": "monthly-source/snapshot.csv",
    }
    if os.name == "nt":
        extended_private_scope = _f12_guard_target_scope(
            "\\\\?\\" + str(private_target),
            qa_root=qa_root,
            run_root=run_root,
            synthetic_root=synthetic_root,
        )
        assert extended_private_scope == private_scope

    external_target = tmp_path / "outside-manifest-role" / "evidence.sqlite"
    external_scope = _f12_guard_target_scope(
        external_target,
        qa_root=qa_root,
        run_root=run_root,
        synthetic_root=synthetic_root,
    )
    assert external_scope["target_scope"] == "outside_manifest_roots"
    assert external_scope["target_relative"] is None
    assert external_scope["target_basename"] == "evidence.sqlite"
    assert re.fullmatch(r"[0-9a-f]{64}", external_scope["target_path_sha256"])
    assert str(external_target) not in json.dumps(external_scope)


def test_f12_query_guard_receipt_write_failure_preserves_primary_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """診斷收據寫失敗只附註，仍保留原本的 query AssertionError。"""

    primary = AssertionError("primary query outcome failure")

    def fail_diagnostic_write(_path: Path, _payload: dict[str, Any]) -> None:
        raise OSError("diagnostic destination unavailable")

    monkeypatch.setattr(
        sys.modules[__name__],
        "_write_json_create_only",
        fail_diagnostic_write,
    )

    with pytest.raises(AssertionError) as captured:
        try:
            raise primary
        except AssertionError as original:
            diagnostic_error = _persist_f12_query_guard_receipt(
                tmp_path / "query-diagnostics.json",
                {"schema": "f12-main-query-guard-diagnostics.v1"},
            )
            assert isinstance(diagnostic_error, OSError)
            raise

    assert captured.value is primary
    assert str(captured.value) == "primary query outcome failure"


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _validate_and_install_startup_write_guard() -> dict[str, Any]:
    """驗證子程序繼承的隔離環境，並限制 Python 可見檔案寫入根。"""

    global _F12_FD_GUARD_DESCRIPTOR_COUNT_GETTER
    _F12_FD_GUARD_DESCRIPTOR_COUNT_GETTER = None

    manifest_path = Path(os.environ["F12_RUNTIME_ISOLATION_MANIFEST"]).resolve(strict=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    qa_root = Path(manifest["qa_root"]).resolve(strict=False)
    run_root = Path(manifest["run_root"]).resolve(strict=False)
    synthetic_root = Path(manifest["synthetic_root"]).resolve(strict=False)
    if not qa_root.is_dir() or not run_root.is_dir() or not synthetic_root.is_dir():
        raise AssertionError("runtime isolation manifest 含不存在的 root")
    if synthetic_root.name != F12_SYNTHETIC_ROOT_NAME:
        raise AssertionError("runtime isolation manifest 指向未核准的 synthetic root")
    if not _path_is_within(manifest_path, qa_root):
        raise AssertionError("runtime isolation manifest 不在本次 QA 根目錄")
    if Path(os.environ["F12_SYNTHETIC_ROOT"]).resolve(strict=False) != synthetic_root:
        raise AssertionError("新程序沒有繼承完全相同的明示 synthetic root")
    if Path(os.environ["F12_MAIN_RUN_ROOT"]).resolve(strict=False) != run_root:
        raise AssertionError("新程序的私有 run root 與 manifest 不同")
    if Path(os.environ["F12_MAIN_QA_ROOT"]).resolve(strict=False) != qa_root:
        raise AssertionError("新程序的 QA root 與 manifest 不同")
    for name in manifest["unset_environment"]:
        if name in os.environ:
            raise AssertionError(f"formal/source selector 未移除：{name}")
    for name in manifest["empty_environment"]:
        if os.environ.get(name) != "":
            raise AssertionError(f"optional startup selector 非空：{name}")
    for name, expected in manifest["expected_environment"].items():
        if os.environ.get(name) != expected:
            raise AssertionError(f"startup environment 不符 manifest：{name}")
    runtime_sentinel = Path(os.environ["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"])
    if runtime_sentinel.exists():
        raise AssertionError("formal runtime binding sentinel 意外存在")
    check_path = Path(os.environ["F12_RUNTIME_ISOLATION_CHECK_PATH"]).resolve()
    if not _path_is_within(check_path, qa_root):
        raise AssertionError("runtime isolation check receipt 不在 QA 根目錄")

    allowed_write_roots = tuple(
        Path(item).resolve(strict=False) for item in manifest["allowed_write_roots"]
    )
    if set(allowed_write_roots) != {qa_root, run_root}:
        raise AssertionError("write guard 根目錄必須恰為本次 QA 與 private run root")
    read_only_source_roots = tuple(
        Path(item).resolve(strict=False)
        for item in manifest.get("read_only_source_roots", [])
    )
    if read_only_source_roots != (synthetic_root,):
        raise AssertionError("read-only source root 必須恰為核准的 synthetic root")
    expected_sqlite_uri_policy = {
        "read_only_roots": [str(root) for root in (qa_root, run_root, synthetic_root)],
        "read_only_mode": "ro",
        "read_only_query_only": True,
        "private_writer_roots": [str(root) for root in (qa_root, run_root)],
        "private_writer_mode": "rw",
        "external_writer_allowed": False,
        "query_parameters": "exactly one mode parameter; duplicates and extra parameters are rejected",
    }
    if manifest.get("sqlite_uri_policy") != expected_sqlite_uri_policy:
        raise AssertionError("SQLite URI guard policy 與 private source custody 不符")

    guard_diagnostic_context: ContextVar[dict[str, Any] | None] = ContextVar(
        "f12_guard_diagnostic_context",
        default=None,
    )

    def _with_guard_diagnostic_context(
        guard_operation: str,
        raw_path: object,
        action: Any,
        *,
        audit_event: str | None = None,
        audit_event_observed: bool | None = None,
    ) -> Any:
        current = guard_diagnostic_context.get() or {}
        selected = dict(current)
        selected["raw_path"] = raw_path
        if not selected.get("guard_operation"):
            selected["guard_operation"] = guard_operation
        if audit_event is not None:
            selected["audit_event"] = audit_event
            selected["audit_operation"] = f"python.audit:{audit_event}"
            selected["audit_event_observed"] = (
                True
                if audit_event_observed is None
                else audit_event_observed
            )
        token = guard_diagnostic_context.set(selected)
        try:
            return action()
        finally:
            guard_diagnostic_context.reset(token)

    def guarded_path(raw_path: object) -> Path:
        if not isinstance(raw_path, (str, bytes, os.PathLike)):
            raise PermissionError("寫入目標不是可驗證的檔案系統路徑")
        candidate = Path(_normalize_guard_authorization_path(raw_path))
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate.resolve(strict=False)

    def require_write_root(raw_path: object) -> None:
        _with_guard_diagnostic_context(
            "require_write_root",
            raw_path,
            lambda: _require_write_root(raw_path),
        )

    def _require_write_root(raw_path: object) -> None:
        candidate = guarded_path(raw_path)
        containing_roots = [
            root
            for root in allowed_write_roots
            if _path_is_within(candidate, root)
        ]
        if not containing_roots:
            _reject_write_path("outside_allowed_private_root", "outside_manifest_roots")
        root = max(containing_roots, key=lambda item: len(str(item)))
        lexical_path = _absolute_lexical_path(raw_path)
        if not _lexical_path_is_within(lexical_path, root):
            _reject_write_path("private_root_lexical_alias", "outside_manifest_roots")
        _reject_reparse_path_chain(lexical_path, root)

    def require_private_file_target(
        raw_path: object,
        *,
        allow_create_if_missing: bool,
    ) -> None:
        """在開檔前拒絕 alias、reparse 與非單一連結檔案。"""

        _with_guard_diagnostic_context(
            "require_private_file_target",
            raw_path,
            lambda: _require_private_file_target(
                raw_path,
                allow_create_if_missing=allow_create_if_missing,
            ),
        )

    def _require_private_file_target(
        raw_path: object,
        *,
        allow_create_if_missing: bool,
    ) -> None:
        require_write_root(raw_path)
        candidate = _absolute_lexical_path(raw_path)
        try:
            details = candidate.lstat()
        except FileNotFoundError:
            if allow_create_if_missing:
                return
            _reject_write_path("missing_private_target_without_create", "manifest_private_write_root")
            return
        except OSError:
            _reject_write_path("private_target_unverifiable_before_open", "manifest_private_write_root")
            return
        if not stat.S_ISREG(details.st_mode):
            _reject_write_path("write_target_not_regular_file", "manifest_private_write_root")
        if int(details.st_nlink) != 1:
            _reject_write_path("hardlinked_file_path", "manifest_private_write_root")

    import stat
    def _reject_write_path(reason: str, path_role: str) -> None:
        error = PermissionError(13, f"F12 write guard blocked: {reason}")
        try:
            context = guard_diagnostic_context.get() or {}
            _F12_FD_GUARD_EVENTS.append(
                _f12_guard_rejection_event(
                    reason=reason,
                    path_role=path_role,
                    audit_event=context.get("audit_event"),
                    audit_operation=context.get("audit_operation"),
                    audit_event_observed=context.get("audit_event_observed"),
                    guard_operation=(
                        context.get("guard_operation")
                        or context.get("audit_operation")
                        or "path_guard"
                    ),
                    raw_path=context.get("raw_path"),
                    error=error,
                    qa_root=qa_root,
                    run_root=run_root,
                    synthetic_root=synthetic_root,
                )
            )
        except BaseException as diagnostic_error:
            add_note = getattr(error, "add_note", None)
            if callable(add_note):
                try:
                    add_note(
                        "F12 guard rejection event capture failed: "
                        f"{type(diagnostic_error).__name__}"
                    )
                except BaseException:
                    pass
        raise error

    def _normalize_guard_authorization_path(raw_path: object) -> str:
        """只把本機 DOS extended prefix 折回同一個檔案系統路徑。"""

        if not isinstance(raw_path, (str, bytes, os.PathLike)):
            _reject_write_path("non_path_write_target", "unavailable")
        raw_text = os.fsdecode(os.fspath(raw_path))
        if os.name != "nt":
            return raw_text
        folded = raw_text.casefold()
        if folded.startswith("\\\\?\\unc\\"):
            _reject_write_path("unc_write_path_rejected", "outside_manifest_roots")
        if folded.startswith("\\\\.\\"):
            _reject_write_path(
                "unsupported_device_write_path_namespace",
                "outside_manifest_roots",
            )
        if folded.startswith("\\\\?\\"):
            is_local_dos_path = (
                len(raw_text) >= 7
                and raw_text[4].isascii()
                and raw_text[4].isalpha()
                and raw_text[5] == ":"
                and raw_text[6] in "\\/"
            )
            if not is_local_dos_path:
                _reject_write_path(
                    "unsupported_extended_write_path_namespace",
                    "outside_manifest_roots",
                )
            return raw_text[4:]
        if raw_text.startswith(("\\\\", "//")):
            _reject_write_path("unc_write_path_rejected", "outside_manifest_roots")
        return raw_text

    def _absolute_lexical_path(raw_path: object) -> Path:
        raw_text = _normalize_guard_authorization_path(raw_path)
        path = Path(raw_text)
        if ".." in path.parts:
            _reject_write_path("path_traversal_segment", "outside_manifest_roots")
        if not path.is_absolute():
            path = Path.cwd() / path
        return Path(os.path.abspath(str(path)))

    def _lexical_path_is_within(path: Path, root: Path) -> bool:
        path_key = os.path.normcase(os.path.abspath(str(path)))
        root_key = os.path.normcase(os.path.abspath(str(root)))
        try:
            return os.path.commonpath((path_key, root_key)) == root_key
        except ValueError:
            return False

    def _reject_reparse_path_chain(path: Path, root: Path) -> None:
        if not _lexical_path_is_within(path, root):
            _reject_write_path("path_outside_private_root_chain", "outside_manifest_roots")
        relative = Path(os.path.relpath(str(path), str(root)))
        components = [root]
        current = root
        if str(relative) != ".":
            for component in relative.parts:
                current = current / component
                components.append(current)
        for component in components:
            try:
                details = component.lstat()
            except FileNotFoundError:
                break
            except OSError:
                _reject_write_path("private_path_chain_unverifiable", "manifest_private_write_root")
            attributes = int(getattr(details, "st_file_attributes", 0))
            reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
            if stat.S_ISLNK(details.st_mode) or attributes & reparse_flag:
                _reject_write_path("reparse_point_in_private_path_chain", "manifest_private_write_root")

    descriptor_records: dict[int, dict[str, Any]] = {}
    descriptor_lock = threading.RLock()
    authorized_fdopen: ContextVar[int | None] = ContextVar(
        "f12_authorized_fdopen_descriptor", default=None
    )
    original_os_open = os.open
    original_os_close = os.close
    original_os_fdopen = os.fdopen
    original_os_dup = os.dup
    original_os_fstat = os.fstat
    _F12_FD_GUARD_EVENTS.clear()

    def descriptor_failure(
        reason: str,
        *,
        role: str = "unavailable",
        winerror: int | None = None,
    ) -> PermissionError:
        error = PermissionError(13, f"F12 fd write guard blocked: {reason}")
        if winerror is not None:
            try:
                error.winerror = winerror  # type: ignore[attr-defined]
            except AttributeError:
                pass
        _F12_FD_GUARD_EVENTS.append(
            {
                "event": "fdopen_rejected",
                "reason": reason,
                "path_role": role,
                "errno": error.errno,
                "winerror": (
                    winerror
                    if winerror is not None
                    else getattr(error, "winerror", None)
                ),
            }
        )
        return error

    def _descriptor_file_info(
        descriptor: int,
        *,
        require_single_link: bool = False,
    ) -> dict[str, Any]:
        if type(descriptor) is not int or descriptor < 0:
            raise descriptor_failure("invalid_descriptor_type")
        try:
            handle_stat = os.fstat(descriptor)
        except OSError as exc:
            raise descriptor_failure("closed_or_invalid_descriptor") from exc
        if not stat.S_ISREG(handle_stat.st_mode):
            return {
                "regular_file": False,
                "canonical_path": None,
                "identity": (int(handle_stat.st_dev), int(handle_stat.st_ino)),
                "os_handle": None,
                "win_identity": None,
                "handle_link_count": int(handle_stat.st_nlink),
                "canonical_path_api": None,
            }

        win_identity: dict[str, int] | None = None
        canonical_path_api: str | None = None
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            class _FileTime(ctypes.Structure):
                _fields_ = [
                    ("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD),
                ]

            class _ByHandleFileInformation(ctypes.Structure):
                _fields_ = [
                    ("dwFileAttributes", wintypes.DWORD),
                    ("ftCreationTime", _FileTime),
                    ("ftLastAccessTime", _FileTime),
                    ("ftLastWriteTime", _FileTime),
                    ("dwVolumeSerialNumber", wintypes.DWORD),
                    ("nFileSizeHigh", wintypes.DWORD),
                    ("nFileSizeLow", wintypes.DWORD),
                    ("nNumberOfLinks", wintypes.DWORD),
                    ("nFileIndexHigh", wintypes.DWORD),
                    ("nFileIndexLow", wintypes.DWORD),
                ]

            try:
                os_handle = int(msvcrt.get_osfhandle(descriptor))
            except OSError as exc:
                raise descriptor_failure("invalid_os_handle") from exc
            if os_handle < 0:
                raise descriptor_failure("invalid_os_handle")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            get_file_type = kernel32.GetFileType
            get_file_type.argtypes = [wintypes.HANDLE]
            get_file_type.restype = wintypes.DWORD
            ctypes.set_last_error(0)
            file_type = int(get_file_type(wintypes.HANDLE(os_handle)))
            if file_type != 1:
                return {
                    "regular_file": False,
                    "canonical_path": None,
                    "identity": (int(handle_stat.st_dev), int(handle_stat.st_ino)),
                    "os_handle": os_handle,
                    "win_identity": None,
                    "handle_link_count": int(handle_stat.st_nlink),
                    "canonical_path_api": None,
                }
            get_file_information = kernel32.GetFileInformationByHandle
            get_file_information.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(_ByHandleFileInformation),
            ]
            get_file_information.restype = wintypes.BOOL
            file_information = _ByHandleFileInformation()
            ctypes.set_last_error(0)
            if not get_file_information(
                wintypes.HANDLE(os_handle), ctypes.byref(file_information)
            ):
                raise descriptor_failure(
                    "handle_file_identity_unavailable",
                    winerror=int(ctypes.get_last_error()),
                )
            file_index = (
                (int(file_information.nFileIndexHigh) << 32)
                | int(file_information.nFileIndexLow)
            )
            win_identity = {
                "volume_serial": int(file_information.dwVolumeSerialNumber),
                "file_index": file_index,
                "number_of_links": int(file_information.nNumberOfLinks),
            }
            if (
                (int(handle_stat.st_dev) & 0xFFFFFFFF)
                != win_identity["volume_serial"]
                or int(handle_stat.st_ino) != win_identity["file_index"]
            ):
                raise descriptor_failure("handle_fd_identity_mismatch")
            if int(handle_stat.st_nlink) != win_identity["number_of_links"]:
                raise descriptor_failure("handle_fd_link_count_mismatch")
            get_final_path = kernel32.GetFinalPathNameByHandleW
            get_final_path.argtypes = [
                wintypes.HANDLE,
                wintypes.LPWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
            ]
            get_final_path.restype = wintypes.DWORD
            buffer = ctypes.create_unicode_buffer(32768)
            ctypes.set_last_error(0)
            length = get_final_path(
                wintypes.HANDLE(os_handle), buffer, len(buffer), 0
            )
            if length == 0 or length >= len(buffer):
                raise descriptor_failure(
                    "canonical_handle_path_unavailable",
                    winerror=int(ctypes.get_last_error()),
                )
            final_text = buffer.value
            if final_text.casefold().startswith("\\\\?\\unc\\"):
                raise descriptor_failure(
                    "unc_handle_path_rejected"
                )
            if final_text.startswith("\\\\?\\"):
                final_text = final_text[4:]
            canonical = Path(final_text)
            if not canonical.is_absolute():
                raise descriptor_failure("non_absolute_handle_path")
            canonical_path_api = "GetFinalPathNameByHandleW:NORMALIZED|DOS(0)"
        else:
            try:
                canonical = Path(f"/proc/self/fd/{descriptor}").resolve(strict=True)
            except (OSError, RuntimeError, ValueError) as exc:
                raise descriptor_failure("canonical_handle_path_unavailable") from exc
            os_handle = None
            canonical_path_api = "procfs_fd_link"

        try:
            resolved = canonical.resolve(strict=True)
            path_stat = resolved.stat()
        except (OSError, RuntimeError, ValueError) as exc:
            raise descriptor_failure("canonical_handle_path_unavailable") from exc
        identity = (int(handle_stat.st_dev), int(handle_stat.st_ino))
        path_identity = (int(path_stat.st_dev), int(path_stat.st_ino))
        if identity != path_identity:
            raise descriptor_failure("handle_path_identity_mismatch")
        if int(path_stat.st_nlink) != int(handle_stat.st_nlink):
            raise descriptor_failure("handle_path_link_count_mismatch")
        if (
            win_identity is not None
            and int(path_stat.st_nlink) != win_identity["number_of_links"]
        ):
            raise descriptor_failure("handle_path_win_link_count_mismatch")
        if require_single_link and (
            int(handle_stat.st_nlink) != 1
            or int(path_stat.st_nlink) != 1
            or (
                win_identity is not None
                and win_identity["number_of_links"] != 1
            )
        ):
            raise descriptor_failure(
                "hardlinked_file_handle",
                role=_descriptor_path_role(resolved),
            )
        return {
            "regular_file": True,
            "canonical_path": resolved,
            "identity": identity,
            "os_handle": os_handle,
            "win_identity": win_identity,
            "handle_link_count": int(handle_stat.st_nlink),
            "canonical_path_api": canonical_path_api,
        }

    def _descriptor_path_role(path: Path | None) -> str:
        if path is None:
            return "non_file_or_unavailable"
        if any(_path_is_within(path, root) for root in allowed_write_roots):
            return "manifest_private_write_root"
        if any(_path_is_within(path, root) for root in read_only_source_roots):
            return "manifest_read_only_source_root"
        return "outside_manifest_roots"

    def _current_writer_record(descriptor: object) -> dict[str, Any]:
        if type(descriptor) is not int:
            raise descriptor_failure("non_integer_descriptor")
        record = descriptor_records.get(descriptor)
        if record is None:
            raise descriptor_failure("untracked_or_closed_descriptor")
        current = _descriptor_file_info(descriptor, require_single_link=True)
        role = _descriptor_path_role(current["canonical_path"])
        if not current["regular_file"]:
            raise descriptor_failure("non_regular_file_handle", role=role)
        if (
            current["identity"] != record["identity"]
            or current["os_handle"] != record["os_handle"]
            or current["canonical_path"] != record["canonical_path"]
            or current["win_identity"] != record["win_identity"]
        ):
            raise descriptor_failure("descriptor_identity_changed", role=role)
        access_mode = int(record["flags"]) & int(getattr(os, "O_ACCMODE", 3))
        if access_mode not in {
            int(getattr(os, "O_WRONLY", 1)),
            int(getattr(os, "O_RDWR", 2)),
        }:
            raise descriptor_failure("descriptor_not_opened_for_write", role=role)
        if role != "manifest_private_write_root":
            raise descriptor_failure("handle_not_in_private_write_root", role=role)
        require_write_root(current["canonical_path"])
        return {**record, **current, "path_role": role}

    def _guarded_os_open_locked(
        path: object,
        flags: int,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        access_mode = int(flags) & int(getattr(os, "O_ACCMODE", 3))
        write_capable = access_mode in {
            int(getattr(os, "O_WRONLY", 1)),
            int(getattr(os, "O_RDWR", 2)),
        }
        if write_capable:
            require_private_file_target(
                path,
                allow_create_if_missing=bool(
                    int(flags) & int(getattr(os, "O_CREAT", 0))
                ),
            )
        descriptor = original_os_open(path, flags, *args, **kwargs)
        if type(descriptor) is int:
            try:
                if write_capable:
                    require_private_file_target(path, allow_create_if_missing=False)
                info = _descriptor_file_info(
                    descriptor,
                    require_single_link=write_capable,
                )
                role = _descriptor_path_role(info["canonical_path"])
                if write_capable and not info["regular_file"]:
                    raise descriptor_failure("non_regular_file_handle", role=role)
                if write_capable and role != "manifest_private_write_root":
                    raise descriptor_failure("handle_not_in_private_write_root", role=role)
            except PermissionError:
                if write_capable:
                    try:
                        original_os_close(descriptor)
                    except OSError:
                        pass
                    descriptor_records.pop(descriptor, None)
                    raise
                descriptor_records[descriptor] = {
                    "flags": flags,
                    "regular_file": False,
                    "canonical_path": None,
                    "identity": None,
                    "os_handle": None,
                    "win_identity": None,
                    "handle_link_count": None,
                    "canonical_path_api": None,
                }
            else:
                descriptor_records[descriptor] = {
                    "flags": flags,
                    **info,
                }
                _F12_FD_GUARD_EVENTS.append(
                    {
                        "event": "os_open_registered",
                        "path_role": _descriptor_path_role(info["canonical_path"]),
                        "regular_file": bool(info["regular_file"]),
                        "write_capable": write_capable,
                        "win_identity_verified": info["win_identity"] is not None,
                        "handle_link_count": info["handle_link_count"],
                        "canonical_path_api": info["canonical_path_api"],
                    }
                )
        return descriptor

    def guarded_os_open(
        path: object,
        flags: int,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        def _open_with_descriptor_lock() -> int:
            with descriptor_lock:
                return _guarded_os_open_locked(path, flags, *args, **kwargs)

        return _with_guard_diagnostic_context(
            "os.open",
            path,
            _open_with_descriptor_lock,
            audit_event="open",
            audit_event_observed=False,
        )

    def guarded_os_close(descriptor: int) -> None:
        with descriptor_lock:
            _guarded_os_close_locked(descriptor)

    def _guarded_os_close_locked(descriptor: int) -> None:
        record = descriptor_records.get(descriptor) if type(descriptor) is int else None
        close_succeeded = False
        try:
            original_os_close(descriptor)
            close_succeeded = True
        finally:
            if type(descriptor) is int:
                removed = descriptor_records.pop(descriptor, None)
                if record is not None:
                    _F12_FD_GUARD_EVENTS.append(
                        {
                            "event": "descriptor_closed_via_os_close",
                            "descriptor_number": descriptor,
                            "path_role": _descriptor_path_role(
                                record.get("canonical_path")
                            ),
                            "os_close_succeeded": close_succeeded,
                            "tracking_removed": removed is record,
                        }
                    )

    def _fdopen_with_owned_duplicate(
        descriptor: int,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        source_record: dict[str, Any],
    ):
        duplicate: int | None = None
        ownership_transferred = False
        duplicate_info: dict[str, Any] | None = None
        duplicate_lease = object()
        duplicate_record: dict[str, Any] | None = None
        try:
            try:
                duplicate = original_os_dup(descriptor)
            except OSError as exc:
                raise descriptor_failure(
                    "descriptor_duplicate_failed",
                    role=source_record["path_role"],
                ) from exc

            duplicate_info = _descriptor_file_info(
                duplicate,
                require_single_link=True,
            )
            duplicate_role = _descriptor_path_role(
                duplicate_info["canonical_path"]
            )
            duplicate_record = {
                "_fdopen_duplicate_lease": duplicate_lease,
                "flags": source_record["flags"],
                **duplicate_info,
            }
            descriptor_records[duplicate] = duplicate_record
            if not duplicate_info["regular_file"]:
                raise descriptor_failure(
                    "duplicate_not_regular_file",
                    role=duplicate_role,
                )
            if (
                duplicate_info["identity"] != source_record["identity"]
                or duplicate_info["canonical_path"]
                != source_record["canonical_path"]
                or duplicate_info["win_identity"]
                != source_record["win_identity"]
                or duplicate_info["handle_link_count"]
                != source_record["handle_link_count"]
                or duplicate_role != "manifest_private_write_root"
            ):
                raise descriptor_failure(
                    "duplicate_target_identity_mismatch",
                    role=duplicate_role,
                )

            validated_duplicate_record = _current_writer_record(duplicate)
            call_args = list(args)
            call_kwargs = dict(kwargs)
            if "closefd" in call_kwargs:
                call_kwargs["closefd"] = True
            elif len(call_args) > 5:
                call_args[5] = True
            else:
                call_kwargs["closefd"] = True

            failure_hook = _F12_FDOPEN_DUPLICATE_FAILURE_HOOK
            if failure_hook is not None:
                failure_hook(duplicate)

            if descriptor_records.get(duplicate) is not duplicate_record:
                raise descriptor_failure(
                    "duplicate_descriptor_lease_changed",
                    role=duplicate_role,
                )
            current_duplicate_info = _descriptor_file_info(
                duplicate,
                require_single_link=True,
            )
            if (
                current_duplicate_info["identity"]
                != duplicate_info["identity"]
                or current_duplicate_info["os_handle"]
                != duplicate_info["os_handle"]
                or current_duplicate_info["canonical_path"]
                != duplicate_info["canonical_path"]
                or current_duplicate_info["win_identity"]
                != duplicate_info["win_identity"]
            ):
                raise descriptor_failure(
                    "duplicate_descriptor_identity_changed",
                    role=duplicate_role,
                )

            token = authorized_fdopen.set(duplicate)
            try:
                stream = original_os_fdopen(
                    duplicate,
                    *call_args,
                    **call_kwargs,
                )
            except BaseException as exc:
                _F12_FD_GUARD_EVENTS.append(
                    {
                        "event": "fdopen_failed_after_duplicate_validation",
                        "path_role": validated_duplicate_record["path_role"],
                        "exception_type": type(exc).__name__,
                        "errno": getattr(exc, "errno", None),
                        "duplicate_descriptor": duplicate,
                        "caller_descriptor_retained": True,
                    }
                )
                raise
            finally:
                authorized_fdopen.reset(token)

            if descriptor_records.get(duplicate) is not duplicate_record:
                raise descriptor_failure(
                    "duplicate_descriptor_lease_changed_after_fdopen",
                    role=duplicate_role,
                )
            descriptor_records.pop(duplicate)
            ownership_transferred = True
            _F12_FD_GUARD_EVENTS.append(
                {
                    "event": "fdopen_authorized_closefd_false_via_owned_duplicate",
                    "path_role": validated_duplicate_record["path_role"],
                    "regular_file": True,
                    "write_capable": True,
                    "identity_rechecked": True,
                    "source_and_duplicate_identity_match": True,
                    "win_identity_verified": (
                        validated_duplicate_record["win_identity"] is not None
                    ),
                    "handle_link_count": validated_duplicate_record[
                        "handle_link_count"
                    ],
                    "canonical_path_api": validated_duplicate_record[
                        "canonical_path_api"
                    ],
                    "caller_descriptor": descriptor,
                    "stream_descriptor": int(stream.fileno()),
                    "caller_descriptor_retained": True,
                    "stream_owns_duplicate": True,
                }
            )
            return stream
        finally:
            if duplicate is not None and not ownership_transferred:
                try:
                    original_os_fstat(duplicate)
                except OSError:
                    descriptor_open = False
                    current_info = None
                else:
                    descriptor_open = True
                    try:
                        current_info = _descriptor_file_info(
                            duplicate,
                            require_single_link=False,
                        )
                    except Exception:
                        current_info = None

                expected_record = descriptor_records.get(duplicate)
                expected_record_matches = bool(
                    duplicate_record is not None
                    and expected_record is duplicate_record
                    and expected_record.get("_fdopen_duplicate_lease")
                    is duplicate_lease
                    and duplicate_info is not None
                    and expected_record is not None
                    and expected_record.get("identity")
                    == duplicate_info["identity"]
                    and expected_record.get("os_handle")
                    == duplicate_info["os_handle"]
                    and expected_record.get("canonical_path")
                    == duplicate_info["canonical_path"]
                    and expected_record.get("win_identity")
                    == duplicate_info["win_identity"]
                )
                same_duplicate_handle = bool(
                    duplicate_info is not None
                    and current_info is not None
                    and current_info["regular_file"]
                    and current_info["identity"] == duplicate_info["identity"]
                    and current_info["canonical_path"]
                    == duplicate_info["canonical_path"]
                    and current_info["win_identity"]
                    == duplicate_info["win_identity"]
                    and current_info["os_handle"]
                    == duplicate_info["os_handle"]
                    and current_info["handle_link_count"]
                    == duplicate_info["handle_link_count"]
                    and os.name == "nt"
                )
                cleanup_action = "preserved_unverifiable_descriptor"
                duplicate_closed = not descriptor_open
                if not descriptor_open:
                    if expected_record_matches:
                        descriptor_records.pop(duplicate, None)
                    cleanup_action = "removed_stale_tracking_for_closed_duplicate"
                elif same_duplicate_handle and expected_record_matches:
                    try:
                        original_os_close(duplicate)
                    except OSError:
                        pass
                    try:
                        original_os_fstat(duplicate)
                    except OSError:
                        duplicate_closed = True
                        if (
                            descriptor_records.get(duplicate)
                            is expected_record
                        ):
                            descriptor_records.pop(duplicate, None)
                        cleanup_action = "closed_verified_duplicate"
                    else:
                        duplicate_closed = False
                        cleanup_action = "verified_duplicate_close_failed"
                elif current_info is not None:
                    cleanup_action = "preserved_reused_or_changed_descriptor"

                caller_descriptor_open = True
                try:
                    original_os_fstat(descriptor)
                except OSError:
                    caller_descriptor_open = False
                _F12_FD_GUARD_EVENTS.append(
                    {
                        "event": "fdopen_duplicate_cleanup",
                        "path_role": (
                            _descriptor_path_role(
                                duplicate_info["canonical_path"]
                            )
                            if duplicate_info is not None
                            else source_record["path_role"]
                        ),
                        "duplicate_descriptor": duplicate,
                        "duplicate_closed": duplicate_closed,
                        "duplicate_tracking_removed": (
                            expected_record_matches
                            and duplicate not in descriptor_records
                        ),
                        "stale_duplicate_record_absent": (
                            descriptor_records.get(duplicate)
                            is not duplicate_record
                        ),
                        "current_descriptor_tracking_preserved": (
                            duplicate in descriptor_records
                        ),
                        "current_descriptor_matches_duplicate": (
                            same_duplicate_handle
                        ),
                        "descriptor_number_reused": (
                            descriptor_open
                            and duplicate_record is not None
                            and descriptor_records.get(duplicate)
                            is not duplicate_record
                        ),
                        "replacement_descriptor_preserved": (
                            descriptor_open
                            and current_info is not None
                            and duplicate_record is not None
                            and descriptor_records.get(duplicate)
                            is not duplicate_record
                            and duplicate in descriptor_records
                        ),
                        "cleanup_action": cleanup_action,
                        "caller_descriptor_retained": caller_descriptor_open,
                    }
                )

    def _guarded_fdopen_locked(descriptor: object, *args: Any, **kwargs: Any):
        mode = kwargs.get("mode", args[0] if args else "r")
        if not isinstance(mode, str):
            raise descriptor_failure("invalid_fdopen_mode")
        write_requested = any(letter in mode for letter in "wax+")
        if not write_requested:
            return original_os_fdopen(descriptor, *args, **kwargs)
        closefd = kwargs.get("closefd", args[5] if len(args) > 5 else True)
        if closefd is not True and closefd is not False:
            raise descriptor_failure("invalid_fdopen_closefd_value")
        if type(descriptor) is not int:
            raise descriptor_failure("non_integer_descriptor")
        current = _descriptor_file_info(descriptor, require_single_link=True)
        role = _descriptor_path_role(current["canonical_path"])
        if not current["regular_file"]:
            raise descriptor_failure("non_regular_file_handle", role=role)
        if descriptor not in descriptor_records:
            raise descriptor_failure(
                "untracked_or_pre_guard_descriptor",
                role=role,
            )
        record = _current_writer_record(descriptor)
        if closefd is False:
            return _fdopen_with_owned_duplicate(
                descriptor,
                args,
                kwargs,
                record,
            )
        token = authorized_fdopen.set(int(descriptor))
        try:
            stream = original_os_fdopen(descriptor, *args, **kwargs)
        except BaseException:
            _F12_FD_GUARD_EVENTS.append(
                {
                    "event": "fdopen_failed_after_handle_validation",
                    "path_role": record["path_role"],
                    "exception_type": "original_fdopen_failure",
                }
            )
            raise
        else:
            descriptor_records.pop(int(descriptor), None)
            _F12_FD_GUARD_EVENTS.append(
                {
                    "event": "fdopen_authorized",
                    "path_role": record["path_role"],
                    "regular_file": True,
                    "write_capable": True,
                    "identity_rechecked": True,
                    "win_identity_verified": record["win_identity"] is not None,
                    "handle_link_count": record["handle_link_count"],
                    "canonical_path_api": record["canonical_path_api"],
                }
            )
            return stream
        finally:
            authorized_fdopen.reset(token)

    def guarded_fdopen(descriptor: object, *args: Any, **kwargs: Any):
        with descriptor_lock:
            return _guarded_fdopen_locked(descriptor, *args, **kwargs)

    os.open = guarded_os_open  # type: ignore[assignment]
    os.close = guarded_os_close  # type: ignore[assignment]
    os.fdopen = guarded_fdopen  # type: ignore[assignment]

    def _parse_sqlite_file_uri(raw_uri: str) -> tuple[Path, str]:
        """只接受無歧義的本機檔案 URI，且 mode 必須精確為 ro 或 rw。"""

        import re
        from urllib.parse import parse_qsl, urlsplit
        from urllib.request import url2pathname

        from app_module.personal_data_paths import to_internal_sqlite_uri

        if re.search(r"%(?![0-9A-Fa-f]{2})", raw_uri):
            raise PermissionError("F12 write guard 拒絕格式錯誤的 SQLite URI escape")
        try:
            parts = urlsplit(raw_uri)
            query_pairs = parse_qsl(
                parts.query,
                keep_blank_values=True,
                strict_parsing=True,
                encoding="utf-8",
                errors="strict",
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise PermissionError("F12 write guard 拒絕無法解析的 SQLite URI") from exc
        if (
            parts.scheme != "file"
            or parts.netloc
            or parts.fragment
            or len(query_pairs) != 1
            or query_pairs[0][0] != "mode"
            or query_pairs[0][1] not in {"ro", "rw"}
            or parts.query != f"mode={query_pairs[0][1]}"
        ):
            raise PermissionError("F12 write guard 拒絕含歧義或不支援參數的 SQLite URI")

        mode = query_pairs[0][1]
        try:
            decoded_path = url2pathname(parts.path)
        except (UnicodeDecodeError, ValueError) as exc:
            raise PermissionError("F12 write guard 拒絕無法解碼的 SQLite URI 路徑") from exc
        if "\x00" in decoded_path:
            raise PermissionError("F12 write guard 拒絕含 NUL 的 SQLite URI 路徑")
        if os.name == "nt":
            folded_path = decoded_path.casefold()
            if folded_path.startswith("\\\\?\\unc\\"):
                raise PermissionError("F12 write guard 不允許 UNC SQLite URI")
            if folded_path.startswith("\\\\?\\"):
                decoded_path = decoded_path[4:]
            if decoded_path.startswith("/") and len(decoded_path) >= 3:
                if decoded_path[2] == ":" and decoded_path[1].isalpha():
                    decoded_path = decoded_path[1:].replace("/", "\\")
            normalized_segments = decoded_path.replace("\\", "/").split("/")
            if any(segment in {".", ".."} for segment in normalized_segments):
                raise PermissionError("F12 write guard 拒絕含 traversal segment 的 SQLite URI")
        candidate = Path(decoded_path)
        if not candidate.is_absolute():
            raise PermissionError("F12 write guard 拒絕相對 SQLite URI 路徑")

        # 接受專案 serializer 與 Path.as_uri() 兩種 canonical percent encoding；
        # 其他等價但拼法不同的 URI 一律拒絕，避免重複參數或別名繞過。
        try:
            canonical_forms = {
                to_internal_sqlite_uri(candidate, mode),
                f"{candidate.as_uri()}?mode={mode}",
            }
        except (OSError, ValueError) as exc:
            raise PermissionError("F12 write guard 拒絕非 canonical SQLite 路徑") from exc
        if raw_uri not in canonical_forms:
            raise PermissionError("F12 write guard 拒絕非 canonical SQLite URI")

        lexical_candidate = Path(os.path.abspath(str(candidate)))
        try:
            resolved_candidate = candidate.resolve(strict=False)
        except (OSError, RuntimeError, ValueError) as exc:
            raise PermissionError("F12 write guard 無法確認 SQLite URI 路徑") from exc
        target_roots = (
            allowed_write_roots
            if mode == "rw"
            else (*allowed_write_roots, *read_only_source_roots)
        )
        if not any(
            _path_is_within(lexical_candidate, root)
            and _path_is_within(resolved_candidate, root)
            for root in target_roots
        ):
            raise PermissionError(
                f"F12 write guard blocked SQLite mode={mode}: {resolved_candidate}"
            )
        return resolved_candidate, mode

    authorized_sqlite_uri: ContextVar[str | None] = ContextVar(
        "f12_authorized_sqlite_uri", default=None
    )
    original_sqlite_connect = sqlite3.connect

    def guarded_sqlite_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        raw_database = os.fsdecode(os.fspath(database)) if isinstance(
            database, (str, bytes, os.PathLike)
        ) else None
        if raw_database is None or not raw_database.startswith("file:"):
            return original_sqlite_connect(database, *args, **kwargs)

        positional_uri = args[6] if len(args) > 6 else False
        uri_enabled = kwargs.get("uri", positional_uri)
        if uri_enabled is not True:
            raise PermissionError("F12 write guard 要求 SQLite file URI 明確設定 uri=True")
        _, mode = _parse_sqlite_file_uri(raw_database)
        token = authorized_sqlite_uri.set(raw_database)
        try:
            connection = original_sqlite_connect(database, *args, **kwargs)
        finally:
            authorized_sqlite_uri.reset(token)
        try:
            if mode == "ro":
                connection.execute("PRAGMA query_only=ON")
                query_only = int(
                    connection.execute("PRAGMA query_only").fetchone()[0]
                )
                if query_only != 1:
                    raise PermissionError("F12 write guard 無法確認 SQLite query_only")
        except BaseException:
            connection.close()
            raise
        return connection

    # 所有 fresh-process sqlite3.connect 呼叫先經 URI 檢查；
    # audit hook 再要求 file URI 必須由這個 wrapper 授權後才可進入 C API。
    sqlite3.connect = guarded_sqlite_connect  # type: ignore[assignment]

    def audit(event: str, arguments: tuple[object, ...]) -> None:
        if event == "open" and arguments:
            mode = arguments[1] if len(arguments) > 1 else None
            flags = arguments[2] if len(arguments) > 2 else 0
            write_bits = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            write_requested = bool(
                (isinstance(mode, str) and any(letter in mode for letter in "wax+"))
                or (isinstance(flags, int) and flags & write_bits)
            )
            if write_requested:
                raw_path = arguments[0]

                def _check_audited_open() -> None:
                    if type(raw_path) is int:
                        descriptor = authorized_fdopen.get()
                        if descriptor != raw_path:
                            raise descriptor_failure(
                                "integer_open_without_fdopen_authority"
                            )
                        _current_writer_record(raw_path)
                    else:
                        allow_create = bool(
                            isinstance(flags, int)
                            and flags & int(getattr(os, "O_CREAT", 0))
                        ) or bool(isinstance(mode, str) and "x" in mode)
                        require_private_file_target(
                            raw_path,
                            allow_create_if_missing=allow_create,
                        )

                _with_guard_diagnostic_context(
                    "python.audit:open",
                    raw_path,
                    _check_audited_open,
                    audit_event=event,
                )
            return
        if event == "sqlite3.connect" and arguments:
            database = arguments[0]
            if isinstance(database, (str, bytes, os.PathLike)):
                raw_database = os.fsdecode(os.fspath(database))
                if raw_database != ":memory:":
                    if raw_database.startswith("file:"):
                        if authorized_sqlite_uri.get() != raw_database:
                            raise PermissionError(
                                "F12 write guard 拒絕未經 wrapper 授權的 SQLite URI"
                            )
                        _parse_sqlite_file_uri(raw_database)
                    else:
                        _with_guard_diagnostic_context(
                            "python.audit:sqlite3.connect",
                            raw_database,
                            lambda: require_write_root(raw_database),
                            audit_event=event,
                        )
            return
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.chown", "os.truncate", "os.utime"}:
            if arguments:
                raw_path = arguments[0]
                _with_guard_diagnostic_context(
                    f"python.audit:{event}",
                    raw_path,
                    lambda: require_write_root(raw_path),
                    audit_event=event,
                )
            return
        if event in {"os.rename", "os.replace", "os.link", "os.symlink"}:
            for raw_path in arguments[:2]:
                _with_guard_diagnostic_context(
                    f"python.audit:{event}",
                    raw_path,
                    lambda raw_path=raw_path: require_write_root(raw_path),
                    audit_event=event,
                )

    sys.addaudithook(audit)
    receipt = {
        "status": "passed",
        "pid": os.getpid(),
        "qa_root": str(qa_root),
        "run_root": str(run_root),
        "synthetic_root_read_only": str(synthetic_root),
        "inherited_environment_checked": True,
        "formal_runtime_binding_active": False,
        "formal_runtime_environment_sentinel_missing": True,
        "unset_selector_count": len(manifest["unset_environment"]),
        "empty_selector_count": len(manifest["empty_environment"]),
        "python_audit_write_guard": "installed",
        "allowed_write_roots": [str(root) for root in allowed_write_roots],
        "guard_scope": [
            "pre-open regular-file and single-link checks for os.open and builtin open writes",
            "open write/create/append/truncate path-chain and private-root containment",
            "sqlite3.connect private paths and canonical ro/rw file URIs",
            "ro file URI connections force PRAGMA query_only=ON",
            "Python os mkdir/remove/rmdir/metadata/rename/link events",
        ],
        "native_library_or_external_process_writes": "not covered by Python audit events",
    }
    _write_json_create_only(check_path, receipt)

    def descriptor_record_count_probe() -> int:
        with descriptor_lock:
            return len(descriptor_records)

    _F12_FD_GUARD_DESCRIPTOR_COUNT_GETTER = descriptor_record_count_probe
    return receipt


def _startup_isolation_manifest(
    *,
    qa_root: Path,
    run_root: Path,
    synthetic_root: Path,
    expected_environment: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": "f12-startup-runtime-isolation.v1",
        "status": "candidate_only",
        "qa_root": str(qa_root.resolve()),
        "run_root": str(run_root.resolve()),
        "synthetic_root": str(synthetic_root.resolve()),
        "synthetic_source_name": F12_SYNTHETIC_ROOT_NAME,
        "allowed_write_roots": [str(qa_root.resolve()), str(run_root.resolve())],
        "read_only_source_roots": [str(synthetic_root.resolve())],
        "unset_environment": list(F12_UNSET_STARTUP_ENVIRONMENT),
        "empty_environment": list(F12_EMPTY_STARTUP_ENVIRONMENT),
        "expected_environment": expected_environment,
        "formal_runtime": {
            "environment_binding_path": expected_environment[
                "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"
            ],
            "environment_binding_file_must_be_absent": True,
            "runtime_config_and_runtime_root_unset": True,
            "accidental_loader_use": "fails closed on missing explicit binding path",
        },
        "sqlite_uri_policy": {
            "read_only_roots": [
                str(root.resolve()) for root in (qa_root, run_root, synthetic_root)
            ],
            "read_only_mode": "ro",
            "read_only_query_only": True,
            "private_writer_roots": [str(root.resolve()) for root in (qa_root, run_root)],
            "private_writer_mode": "rw",
            "external_writer_allowed": False,
            "query_parameters": "exactly one mode parameter; duplicates and extra parameters are rejected",
        },
        "profile_isolation": {
            "profile": "test",
            "data_root": expected_environment["DATA_ROOT"],
            "output_root": expected_environment["OUTPUT_ROOT"],
            "personal_data_root": expected_environment["PERSONAL_DATA_ROOT"],
            "personal_watchlist_source": expected_environment[
                "PERSONAL_WATCHLIST_SOURCE"
            ],
            "user_profile_and_xdg_roots": [
                expected_environment[name]
                for name in (
                    "USERPROFILE",
                    "HOME",
                    "LOCALAPPDATA",
                    "APPDATA",
                    "XDG_CONFIG_HOME",
                    "XDG_CACHE_HOME",
                    "XDG_DATA_HOME",
                )
            ],
        },
        "network_access": "not disabled by this environment manifest",
    }


def test_test_profile_personal_watchlist_source_matches_resolved_output_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """核 PROFILE=test 後的來源必須仍在實際設定的 legacy root。"""

    run_root = tmp_path / "profile-test-source-probe"
    environment = _main_window_environment(run_root)
    package_root = Path(__file__).resolve().parents[1]
    environment["PERSONAL_DATA_ROOT"] = str(
        package_root.parent / f"f12-personal-config-probe-{uuid4().hex}"
    )
    for key in F12_UNSET_STARTUP_ENVIRONMENT:
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    config = TWStockConfig()
    configured_output_root = run_root / "application-output" / "_test"
    configured_source = configured_output_root / "watchlist" / "default.json"
    assert config.profile == "test"
    assert config.output_root == configured_output_root
    assert config.personal_watchlist_source == configured_source

    accepted_service = PersonalWatchlistService(config)
    accepted_status = accepted_service.get_storage_status()
    assert accepted_status.mode == "personal_source_readonly"
    assert accepted_status.upgrade_available is True
    assert accepted_service.get_stock_codes() == []

    # 保留舊 fixture 的來源位置，證明 guard 會拒絕它而不讀取內容。
    stale_source = run_root / "application-output" / "watchlist" / "default.json"
    stale_source.parent.mkdir(parents=True, exist_ok=True)
    stale_source.write_text(
        configured_source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    config.personal_watchlist_source = stale_source
    rejected_service = PersonalWatchlistService(config)
    rejected_status = rejected_service.get_storage_status()
    assert rejected_status.mode == "blocked"
    assert rejected_status.upgrade_available is False
    assert "source_outside_legacy_root" in rejected_status.message
    with pytest.raises(
        PersonalWatchlistSelectionError,
        match="personal_watchlist_source_unavailable",
    ):
        rejected_service.get_stock_codes()


def _wait_until(app: Any, predicate: Any, *, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {label}")


def _append_stage(path: Path, stage: str, **details: object) -> None:
    record = {
        "stage": stage,
        "pid": os.getpid(),
        "monotonic_ns": time.monotonic_ns(),
        **details,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _read_stage_names(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("stage"), str):
            names.add(record["stage"])
    return names


def _query_owned_job_active_processes(owned_process_tree: Any) -> int:
    """讀取本測試專屬 Job 的存活數，避免只等 venv launcher PID。"""

    if os.name != "nt":
        raise AssertionError("Windows Job active-process query 僅能在 Windows 使用")

    import ctypes
    from ctypes import wintypes

    job_handle = getattr(owned_process_tree, "_job_handle", None)
    if not job_handle:
        raise AssertionError("受控 worker 沒有可查詢的專屬 Job Object")

    class _JobBasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    information = _JobBasicAccountingInformation()
    returned_length = wintypes.DWORD()
    if not kernel32.QueryInformationJobObject(
        wintypes.HANDLE(job_handle),
        1,  # JobObjectBasicAccountingInformation
        ctypes.byref(information),
        ctypes.sizeof(information),
        ctypes.byref(returned_length),
    ):
        raise OSError(
            ctypes.get_last_error(),
            "QueryInformationJobObject failed for the owned F12 worker",
        )
    return int(information.ActiveProcesses)


def _query_owned_job_process_ids(owned_process_tree: Any) -> tuple[int, ...]:
    """讀取專屬 Job 的完整 PID 清單，供 close 後逐一驗證收束。"""

    if os.name != "nt":
        raise AssertionError("Windows Job PID 清單僅能在 Windows 使用")

    import ctypes
    from ctypes import wintypes

    job_handle = getattr(owned_process_tree, "_job_handle", None)
    if not job_handle:
        raise AssertionError("受控 worker 沒有可查詢的專屬 Job Object")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL

    pid_size = ctypes.sizeof(ctypes.c_size_t)
    capacity = 64
    maximum_capacity = 16384
    while capacity <= maximum_capacity:
        buffer = ctypes.create_string_buffer(8 + capacity * pid_size)
        returned_length = wintypes.DWORD()
        queried = kernel32.QueryInformationJobObject(
            wintypes.HANDLE(job_handle),
            3,  # JobObjectBasicProcessIdList
            ctypes.byref(buffer),
            ctypes.sizeof(buffer),
            ctypes.byref(returned_length),
        )
        assigned_count = int(ctypes.c_uint32.from_buffer(buffer, 0).value)
        returned_count = int(ctypes.c_uint32.from_buffer(buffer, 4).value)
        if queried:
            if returned_count > capacity:
                raise AssertionError(
                    "QueryInformationJobObject returned more process IDs than its buffer"
                )
            return tuple(
                int(ctypes.c_size_t.from_buffer(buffer, 8 + index * pid_size).value)
                for index in range(returned_count)
            )

        error_code = ctypes.get_last_error()
        if error_code != 234:  # ERROR_MORE_DATA
            raise OSError(
                error_code,
                "QueryInformationJobObject failed for owned process IDs",
            )
        capacity = max(capacity * 2, assigned_count)

    raise AssertionError(
        f"owned Job process list exceeds bounded capacity {maximum_capacity}"
    )


def _owned_process_tree_active_count(process: Any, owned_process_tree: Any) -> int:
    if os.name == "nt":
        return _query_owned_job_active_processes(owned_process_tree)

    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return 0
    except PermissionError:
        return 1
    return 1


def _spawn_owned_logged_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
) -> tuple[Any, Any, Any, Any]:
    """用專案 Job Object runner 啟動 child，stdout/stderr 寫入專屬檔案。"""

    from scripts import qa_run_research_journey_qt_subprocess as process_runner

    log_handle = log_path.open("xb", buffering=0)
    owned_process_tree: Any | None = None
    try:
        owned_process_tree = process_runner._OwnedProcessTree()
        process = process_runner._spawn_owned_child(
            command,
            cwd=cwd,
            env=dict(env),
            log_handle=log_handle,
            owned_process_tree=owned_process_tree,
        )
        assert owned_process_tree.attached is True
        return process_runner, process, owned_process_tree, log_handle
    except BaseException:
        if owned_process_tree is not None:
            owned_process_tree.close()
        log_handle.close()
        raise


def _stop_and_close_owned_process_tree(
    process_runner: Any,
    process: Any,
    owned_process_tree: Any,
    log_handle: Any,
    *,
    stop_root: bool,
    grace_seconds: float = 2.0,
) -> tuple[int, str]:
    """有界停止 root，關閉本次 Job／process group，並回收 root handle。"""

    actions: list[str] = []
    errors: list[str] = []
    if stop_root and process.poll() is None:
        if os.name == "nt":
            _, action = process_runner._terminate_owned_child(
                process,
                grace_seconds,
            )
            actions.append(f"root_{action}")
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                actions.append("owned_process_group_sigterm")
            except ProcessLookupError:
                actions.append("owned_process_group_already_exited")
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                actions.append("owned_process_group_sigkill")

    try:
        owned_process_tree.close()
        actions.append("owned_tree_closed")
    except Exception as exc:  # noqa: BLE001 - 保留 cleanup 故障並繼續回收 handles
        errors.append(f"owned tree close failed: {type(exc).__name__}: {exc}")

    try:
        return_code = int(process.wait(timeout=5.0))
    except subprocess.TimeoutExpired as exc:
        errors.append("owned worker root did not exit within 5 seconds after tree close")
        try:
            process.kill()
            return_code = int(process.wait(timeout=2.0))
            actions.append("owned_root_last_resort_kill")
        except Exception as kill_exc:  # noqa: BLE001 - 僅碰本次 launcher root
            errors.append(f"owned root cleanup failed: {type(kill_exc).__name__}: {kill_exc}")
            return_code = process.poll()
        if return_code is None:
            errors.append(f"owned root wait failed: {exc}")

    child_close = getattr(process, "close", None)
    if callable(child_close):
        try:
            child_close()
            actions.append("owned_root_handles_closed")
        except Exception as exc:  # noqa: BLE001 - 把 handle cleanup 記為失敗
            errors.append(f"owned root handle close failed: {type(exc).__name__}: {exc}")

    try:
        log_handle.flush()
    except Exception as exc:  # noqa: BLE001 - 原始 log 仍保留在磁碟
        errors.append(f"worker log flush failed: {type(exc).__name__}: {exc}")
    finally:
        log_handle.close()

    if errors:
        raise AssertionError("; ".join(errors))
    if return_code is None:
        raise AssertionError("owned worker root has no final return code")
    return return_code, "+".join(actions) or "natural_tree_exit"


def _wait_for_owned_tree_exit(
    process: Any,
    owned_process_tree: Any,
    *,
    timeout: float,
) -> tuple[bool, int | None, int]:
    deadline = time.monotonic() + timeout
    last_active_count = -1
    while True:
        return_code = process.poll()
        last_active_count = _owned_process_tree_active_count(
            process,
            owned_process_tree,
        )
        if return_code is not None and last_active_count == 0:
            return True, int(return_code), last_active_count
        if time.monotonic() >= deadline:
            return False, return_code, last_active_count
        time.sleep(0.05)


def _read_json_log_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _read_log_tail(path: Path, *, limit: int = 4000) -> str:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - limit), os.SEEK_SET)
        return handle.read().decode("utf-8", errors="replace")


def _read_prefixed_json_log_records(
    path: Path,
    *,
    prefix: str,
    max_line_bytes: int = 65536,
) -> list[dict[str, Any]]:
    """有界逐行讀取專屬 log 中明確標記的 JSON 收據。"""

    if not path.is_file():
        return []
    marker = prefix.encode("utf-8")
    records: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        while True:
            raw_line = handle.readline(max_line_bytes + 1)
            if not raw_line:
                break
            if len(raw_line) > max_line_bytes:
                # 拒收超長單行，繼續 drain 到下一個換行，避免單行耗盡記憶體。
                while raw_line and not raw_line.endswith(b"\n"):
                    raw_line = handle.readline(max_line_bytes + 1)
                continue
            if not raw_line.startswith(marker):
                continue
            payload = raw_line[len(marker) :].strip()
            try:
                value = json.loads(payload.decode("utf-8", errors="strict"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AssertionError(
                    f"malformed marked fresh-child receipt: {payload[:128]!r}"
                ) from exc
            if not isinstance(value, dict):
                raise AssertionError("marked fresh-child receipt must be a JSON object")
            records.append(value)
    return records


def _fresh_child_failure_message(
    *,
    return_code: int | None,
    reason: str,
    log_path: Path,
) -> str:
    tail = _read_log_tail(log_path, limit=FRESH_CHILD_ERROR_TAIL_BYTES)
    return (
        f"fresh Main child {reason}; exit={return_code}; log={log_path}\n"
        f"bounded log tail (at most {FRESH_CHILD_ERROR_TAIL_BYTES} bytes):\n{tail}"
    )


def _process_pid_is_running(process_runner: Any, pid: int) -> bool:
    if os.name == "nt":
        result = process_runner._is_process_pid_running(pid)
        if result is None:
            raise AssertionError(f"無法可靠查詢受控測試 PID {pid}")
        return result
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _run_owned_logged_child(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    timeout: float,
) -> dict[str, Any]:
    """以獨立 log 與專屬 Job Object 執行 child，timeout 後關閉整棵樹。"""

    process_runner, process, owned_process_tree, log_handle = (
        _spawn_owned_logged_process(
            command,
            cwd=cwd,
            env=env,
            log_path=log_path,
        )
    )
    completed = False
    observed_return_code: int | None = None
    active_process_count = -1
    job_process_ids_before_close: tuple[int, ...] = ()
    try:
        completed, observed_return_code, active_process_count = _wait_for_owned_tree_exit(
            process,
            owned_process_tree,
            timeout=timeout,
        )
        if os.name == "nt":
            job_process_ids_before_close = _query_owned_job_process_ids(
                owned_process_tree
            )
    except BaseException:
        _stop_and_close_owned_process_tree(
            process_runner,
            process,
            owned_process_tree,
            log_handle,
            stop_root=True,
        )
        raise

    return_code, termination_action = _stop_and_close_owned_process_tree(
        process_runner,
        process,
        owned_process_tree,
        log_handle,
        stop_root=not completed,
    )
    tracked_pids = tuple(dict.fromkeys((process.pid, *job_process_ids_before_close)))
    cleanup_deadline = time.monotonic() + 5.0
    while os.name == "nt" and time.monotonic() < cleanup_deadline and any(
        _process_pid_is_running(process_runner, pid) for pid in tracked_pids
    ):
        time.sleep(0.05)
    remaining_pids = (
        [pid for pid in tracked_pids if _process_pid_is_running(process_runner, pid)]
        if os.name == "nt"
        else []
    )
    log_bytes = log_path.stat().st_size
    return {
        "completed_before_deadline": completed,
        "return_code": return_code,
        "observed_return_code": observed_return_code,
        "active_process_count_at_exit_or_deadline": active_process_count,
        "termination_action": termination_action,
        "process_tree_management": owned_process_tree.management_mode,
        "launcher_pid": process.pid,
        "process_tree_attached": owned_process_tree.attached,
        "process_tree_closed": owned_process_tree._job_handle is None
        if os.name == "nt"
        else True,
        "root_process_handles_closed": getattr(process, "_closed", True),
        "job_process_ids_before_close": list(job_process_ids_before_close),
        "tracked_pids_after_close": list(tracked_pids),
        "remaining_pids_after_close": remaining_pids,
        "combined_output_log": str(log_path),
        "combined_output_log_size_bytes": log_bytes,
        "combined_output_log_sha256": _sha256_file(log_path),
    }


def test_owned_supervisor_writes_high_volume_output_to_exclusive_file(
    tmp_path: Path,
) -> None:
    """大量 stdout/stderr 直接進獨立檔案，不能因 pipe 未讀而卡住。"""

    log_path = tmp_path / "high-output.log"
    command = [
        sys.executable,
        "-B",
        "-u",
        "-c",
        "import os; payload=b'X'*16384+b'\\n'; "
        "[ (os.write(1, payload), os.write(2, payload)) for _ in range(96) ]; "
        "os.write(1, b'F12_HIGH_OUTPUT_COMPLETE\\n')",
    ]
    process_runner, process, owned_process_tree, log_handle = (
        _spawn_owned_logged_process(
            command,
            cwd=tmp_path,
            env=os.environ.copy(),
            log_path=log_path,
        )
    )
    naturally_exited = False
    try:
        naturally_exited, observed_return_code, active_count = _wait_for_owned_tree_exit(
            process,
            owned_process_tree,
            timeout=30.0,
        )
    finally:
        final_return_code, close_action = _stop_and_close_owned_process_tree(
            process_runner,
            process,
            owned_process_tree,
            log_handle,
            stop_root=not naturally_exited,
        )

    raw_log = log_path.read_bytes()
    assert naturally_exited, (
        f"high-output child timed out; active={active_count}, log={log_path}"
    )
    assert observed_return_code == final_return_code == 0
    assert active_count == 0
    assert len(raw_log) >= 96 * 2 * 16385
    assert b"F12_HIGH_OUTPUT_COMPLETE" in raw_log
    assert "owned_tree_closed" in close_action
    (tmp_path / "high-output-receipt.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "process_tree_management": owned_process_tree.management_mode,
                "exclusive_log_open_mode": "xb",
                "stdout_and_stderr_combined": True,
                "pipe_used": False,
                "return_code": final_return_code,
                "active_process_count_after_exit": active_count,
                "close_action": close_action,
                "log_path": str(log_path),
                "log_size_bytes": len(raw_log),
                "log_sha256": hashlib.sha256(raw_log).hexdigest(),
                "completion_marker_seen": b"F12_HIGH_OUTPUT_COMPLETE" in raw_log,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.skipif(
    os.name != "nt",
    reason="此小型 cleanup fixture 驗證 Windows 專屬 Job Object tree",
)
def test_owned_supervisor_deadline_closes_only_its_child_grandchild_tree(
    tmp_path: Path,
) -> None:
    """deadline 關閉本次 Job 後，child、grandchild 與 handles 都收束。"""

    log_path = tmp_path / "owned-tree-timeout.log"
    grandchild_code = (
        "import json, os, time; "
        "print(json.dumps({'kind':'grandchild','pid':os.getpid(),"
        "'parent_pid':os.getppid()}), flush=True); "
        "time.sleep(60)"
    )
    owner_code = "\n".join(
        (
            "import json, os, subprocess, sys, time",
            f"grandchild_code = {grandchild_code!r}",
            "grandchild = subprocess.Popen([sys.executable, '-u', '-c', grandchild_code])",
            "print(json.dumps({'kind':'owner','pid':os.getpid(),'parent_pid':os.getppid(),"
            "'grandchild_launcher_pid':grandchild.pid}), flush=True)",
            "time.sleep(60)",
        )
    )
    command = [sys.executable, "-B", "-u", "-c", owner_code]
    process_runner, process, owned_process_tree, log_handle = (
        _spawn_owned_logged_process(
            command,
            cwd=tmp_path,
            env=os.environ.copy(),
            log_path=log_path,
        )
    )
    records: list[dict[str, Any]] = []
    active_count_before_deadline = 0
    job_process_ids_before_deadline: tuple[int, ...] = ()
    naturally_exited = False
    try:
        startup_deadline = time.monotonic() + 10.0
        while time.monotonic() < startup_deadline:
            records = _read_json_log_records(log_path)
            active_count_before_deadline = _owned_process_tree_active_count(
                process,
                owned_process_tree,
            )
            if {record.get("kind") for record in records} >= {"owner", "grandchild"}:
                break
            if process.poll() is not None and active_count_before_deadline == 0:
                break
            time.sleep(0.05)

        job_process_ids_before_deadline = _query_owned_job_process_ids(
            owned_process_tree
        )

        # 以短小 deadline 觸發與 Main candidate 相同的停止及 Job close 路徑。
        naturally_exited, _return_code, active_count_before_deadline = (
            _wait_for_owned_tree_exit(
                process,
                owned_process_tree,
                timeout=0.25,
            )
        )
    finally:
        final_return_code, close_action = _stop_and_close_owned_process_tree(
            process_runner,
            process,
            owned_process_tree,
            log_handle,
            stop_root=True,
            grace_seconds=0.25,
        )

    records = _read_json_log_records(log_path)
    owner_records = [record for record in records if record.get("kind") == "owner"]
    grandchild_records = [
        record for record in records if record.get("kind") == "grandchild"
    ]
    assert not naturally_exited, "long-lived child unexpectedly exited before deadline"
    assert active_count_before_deadline >= 2
    assert len(owner_records) == len(grandchild_records) == 1
    owner_pid = owner_records[0].get("pid")
    grandchild_pid = grandchild_records[0].get("pid")
    grandchild_launcher_pid = owner_records[0].get("grandchild_launcher_pid")
    assert type(owner_pid) is int and owner_pid > 0
    assert type(grandchild_pid) is int and grandchild_pid > 0
    assert type(grandchild_launcher_pid) is int and grandchild_launcher_pid > 0
    assert grandchild_records[0].get("parent_pid") == grandchild_launcher_pid
    assert final_return_code != 0
    assert "owned_tree_closed" in close_action
    assert owned_process_tree.attached is True
    assert owned_process_tree.management_mode == "windows_job_object_kill_on_close"

    tracked_pids = tuple(
        dict.fromkeys(
            (
                process.pid,
                *job_process_ids_before_deadline,
                owner_pid,
                grandchild_launcher_pid,
                grandchild_pid,
            )
        )
    )
    exit_deadline = time.monotonic() + 5.0
    while time.monotonic() < exit_deadline and any(
        _process_pid_is_running(process_runner, pid) for pid in tracked_pids
    ):
        time.sleep(0.05)
    remaining = [
        pid for pid in tracked_pids if _process_pid_is_running(process_runner, pid)
    ]
    assert not remaining, f"Job close 後仍存活的本次 child tree PID：{remaining}"
    assert getattr(process, "_closed", True) is True
    assert len(job_process_ids_before_deadline) == active_count_before_deadline
    cleanup_receipt = {
        "status": "passed",
        "management_mode": owned_process_tree.management_mode,
        "job_closed": owned_process_tree._job_handle is None,
        "tracked_pids": list(tracked_pids),
        "job_process_ids_at_deadline": list(job_process_ids_before_deadline),
        "job_member_count_at_deadline": len(job_process_ids_before_deadline),
        "active_process_count_before_deadline": active_count_before_deadline,
        "natural_exit_before_deadline": naturally_exited,
        "root_return_code_after_cleanup": final_return_code,
        "termination_action": close_action,
        "remaining_pids_after_cleanup": remaining,
        "root_handles_closed": getattr(process, "_closed", False),
        "owned_tree_attached": owned_process_tree.attached,
    }
    (tmp_path / "owned-tree-cleanup-receipt.json").write_text(
        json.dumps(cleanup_receipt, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )


def test_owned_fresh_child_success_reads_one_exact_receipt_from_regular_log(
    tmp_path: Path,
) -> None:
    """成功 child 收據使用單一標記行，stdout/stderr 寫入專屬檔案。"""

    log_path = tmp_path / "fresh-child-success.log"
    child_code = (
        "import json, os; "
        "print('child startup noise'); "
        f"print({FRESH_CHILD_RECEIPT_PREFIX!r} + json.dumps("
        "{'status':'small_child_success','pid':os.getpid(),"
        "'parent_pid':os.getppid(),'identity':'exact'})); "
        "print('child stderr noise', file=__import__('sys').stderr)"
    )
    result = _run_owned_logged_child(
        [sys.executable, "-B", "-u", "-c", child_code],
        cwd=tmp_path,
        env=os.environ.copy(),
        log_path=log_path,
        timeout=15.0,
    )
    receipts = _read_prefixed_json_log_records(
        log_path,
        prefix=FRESH_CHILD_RECEIPT_PREFIX,
    )
    assert result["completed_before_deadline"] is True
    assert result["return_code"] == 0
    assert result["active_process_count_at_exit_or_deadline"] == 0
    assert result["process_tree_closed"] is True
    assert result["root_process_handles_closed"] is True
    assert result["remaining_pids_after_close"] == []
    assert len(receipts) == 1
    assert receipts[0]["status"] == "small_child_success"
    assert receipts[0]["parent_pid"] == result["launcher_pid"]
    assert receipts[0]["pid"] != os.getpid()
    assert receipts[0]["identity"] == "exact"
    assert "child startup noise" in _read_log_tail(log_path)
    assert "child stderr noise" in _read_log_tail(log_path)


def test_owned_fresh_child_failure_reports_only_bounded_log_tail(
    tmp_path: Path,
) -> None:
    """失敗 child 的錯誤文字只保留有界 log tail，並回收自然結束的 Job。"""

    log_path = tmp_path / "fresh-child-failure.log"
    child_code = (
        "import os, sys; "
        "os.write(1, b'BEGIN_MARKER\\n' + b'X'*300000 + b'\\nTAIL_MARKER\\n'); "
        "os.write(2, b'STDERR_TAIL_MARKER\\n'); sys.exit(17)"
    )
    result = _run_owned_logged_child(
        [sys.executable, "-B", "-u", "-c", child_code],
        cwd=tmp_path,
        env=os.environ.copy(),
        log_path=log_path,
        timeout=15.0,
    )
    message = _fresh_child_failure_message(
        return_code=result["return_code"],
        reason="small child nonzero exit",
        log_path=log_path,
    )
    assert result["completed_before_deadline"] is True
    assert result["return_code"] == 17
    assert result["active_process_count_at_exit_or_deadline"] == 0
    assert result["process_tree_closed"] is True
    assert result["root_process_handles_closed"] is True
    assert result["remaining_pids_after_close"] == []
    assert len(message.encode("utf-8")) <= FRESH_CHILD_ERROR_TAIL_BYTES + 300
    assert "TAIL_MARKER" in message
    assert "STDERR_TAIL_MARKER" in message
    assert "BEGIN_MARKER" not in message
    assert len(log_path.read_bytes()) > 300000


@pytest.mark.parametrize(
    ("total_remaining_seconds", "expected_query_budget_seconds"),
    ((600.0, 480.0), (90.0, 90.0), (0.0, 0.0), (-1.0, 0.0)),
)
def test_fresh_child_query_budget_uses_remaining_total_deadline(
    total_remaining_seconds: float,
    expected_query_budget_seconds: float,
) -> None:
    """查詢期限不得超過 fresh child 總期限扣除初始化後的剩餘時間。"""

    child_path = Path(__file__).with_name("test_ui_qt_revenue_main_journey_child.py")
    spec = importlib.util.spec_from_file_location(
        "f12_fresh_child_deadline_probe",
        child_path,
    )
    assert spec is not None and spec.loader is not None
    child_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(child_module)
    budget = child_module._remaining_query_phase_budget_seconds(
        1000.0 + total_remaining_seconds,
        now_monotonic=1000.0,
    )
    assert budget == expected_query_budget_seconds
    assert budget <= FRESH_CHILD_QUERY_PHASE_TIMEOUT_SECONDS


def test_fresh_child_inherits_explicit_runtime_isolation_and_write_guard(
    tmp_path: Path,
) -> None:
    """獨立 Python child 核對繼承環境，並拒絕私有根外的檔案寫入。"""

    repository_root = Path(__file__).resolve().parents[1]
    qa_root = tmp_path / "qa"
    run_root = tmp_path / "private-run"
    synthetic_root = (
        Path(__file__).resolve().parents[1]
        / "output"
        / "qa"
        / "f12_resume_20261011"
        / F12_SYNTHETIC_ROOT_NAME
    ).resolve(strict=False)
    assert synthetic_root.is_dir()
    for path in (qa_root, run_root):
        path.mkdir(parents=True, exist_ok=False)
    environment_overrides = _main_window_environment(run_root, qa_root=qa_root)
    child_environment = _isolated_environment(
        os.environ.copy(),
        environment_overrides,
    )
    manifest_path = qa_root / "runtime-isolation-manifest.json"
    forbidden_target = tmp_path / "outside-private-roots" / "blocked.txt"
    explicit_environment = {
        "F12_MAIN_RUN_ROOT": str(run_root),
        "F12_MAIN_QA_ROOT": str(qa_root),
        "F12_SYNTHETIC_ROOT": str(synthetic_root),
        "F12_RUNTIME_ISOLATION_MANIFEST": str(manifest_path),
        "F12_FORBIDDEN_WRITE_TARGET": str(forbidden_target),
    }
    child_environment.update(explicit_environment)
    child_environment["F12_RUNTIME_ISOLATION_CHECK_PATH"] = str(
        qa_root / "runtime-isolation-child-check.json"
    )
    expected_environment = dict(environment_overrides)
    expected_environment.update(
        {
            key: value
            for key, value in explicit_environment.items()
            if key != "F12_FORBIDDEN_WRITE_TARGET"
        }
    )
    expected_environment["F12_FORBIDDEN_WRITE_TARGET"] = str(forbidden_target)
    _write_json_create_only(
        manifest_path,
        _startup_isolation_manifest(
            qa_root=qa_root,
            run_root=run_root,
            synthetic_root=synthetic_root,
            expected_environment=expected_environment,
        ),
    )
    probe_marker = "F12_RUNTIME_ISOLATION_PROBE:"
    probe_code = """
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from app_module.personal_data_paths import to_internal_sqlite_uri
from tests.test_ui_qt_revenue_main_journey import _validate_and_install_startup_write_guard

receipt = _validate_and_install_startup_write_guard()
qa_root = Path(os.environ["F12_MAIN_QA_ROOT"])
synthetic_root = Path(os.environ["F12_SYNTHETIC_ROOT"])
private_database = qa_root / "guard private #% database.sqlite"
outside_database = Path(os.environ["F12_FORBIDDEN_WRITE_TARGET"]).parent / "outside.sqlite"

with sqlite3.connect(private_database) as connection:
    connection.execute("CREATE TABLE guard_probe (value INTEGER NOT NULL)")
    connection.execute("INSERT INTO guard_probe(value) VALUES (11)")
    connection.commit()
with sqlite3.connect(private_database) as connection:
    receipt["normal_private_database_read"] = connection.execute(
        "SELECT value FROM guard_probe"
    ).fetchone()[0] == 11

uri_forms = {
    "project_serializer": to_internal_sqlite_uri(private_database, "ro"),
    "canonical_path_uri": f"{private_database.as_uri()}?mode=ro",
}
for uri_name, uri in uri_forms.items():
    with sqlite3.connect(uri, uri=True) as connection:
        query_only = int(connection.execute("PRAGMA query_only").fetchone()[0])
        value = connection.execute("SELECT value FROM guard_probe").fetchone()[0]
        try:
            connection.execute("INSERT INTO guard_probe(value) VALUES (12)")
        except sqlite3.OperationalError:
            write_blocked = True
        else:
            write_blocked = False
    receipt[f"{uri_name}_query_only"] = query_only == 1
    receipt[f"{uri_name}_write_blocked"] = write_blocked
    receipt[f"{uri_name}_read_value"] = value

private_rw_uri = to_internal_sqlite_uri(private_database, "rw")
with sqlite3.connect(private_rw_uri, uri=True) as connection:
    connection.execute("INSERT INTO guard_probe(value) VALUES (13)")
    connection.commit()
    receipt["private_rw_uri_allowed"] = int(
        connection.execute("PRAGMA query_only").fetchone()[0]
    ) == 0

source_database = synthetic_root / "f17" / "synthetic_prices.sqlite"
source_digest_before = hashlib.sha256(source_database.read_bytes()).hexdigest()
source_ro_uri = to_internal_sqlite_uri(source_database, "ro")
with sqlite3.connect(source_ro_uri, uri=True) as connection:
    receipt["approved_synthetic_ro_query_only"] = int(
        connection.execute("PRAGMA query_only").fetchone()[0]
    ) == 1
    receipt["approved_synthetic_sqlite_master_count"] = int(
        connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
    )
source_digest_after = hashlib.sha256(source_database.read_bytes()).hexdigest()
receipt["approved_synthetic_source_sha_unchanged"] = (
    source_digest_before == source_digest_after
)

denied_uris = {
    "external_ro_uri": f"{outside_database.as_uri()}?mode=ro",
    "external_rw_uri": f"{outside_database.as_uri()}?mode=rw",
    "private_create_uri": f"{private_database.as_uri()}?mode=rwc",
    "ambiguous_duplicate_mode_uri": f"{private_database.as_uri()}?mode=ro&mode=rw",
    "unwrapped_file_uri": uri_forms["project_serializer"],
    "synthetic_rw_uri": to_internal_sqlite_uri(source_database, "rw"),
}
for name, uri in denied_uris.items():
    try:
        if name == "unwrapped_file_uri":
            sqlite3.connect(uri)
        else:
            sqlite3.connect(uri, uri=True)
    except PermissionError:
        receipt[f"{name}_blocked"] = True
    else:
        receipt[f"{name}_blocked"] = False

try:
    sqlite3.connect(outside_database)
except PermissionError:
    receipt["external_plain_path_blocked"] = True
else:
    receipt["external_plain_path_blocked"] = False

try:
    Path(os.environ["F12_FORBIDDEN_WRITE_TARGET"]).write_text(
        "blocked", encoding="utf-8"
    )
except PermissionError:
    receipt["outside_write_blocked"] = True
else:
    receipt["outside_write_blocked"] = False

print("F12_RUNTIME_ISOLATION_PROBE:" + json.dumps(receipt, sort_keys=True))
"""
    log_path = qa_root / "runtime-isolation-probe.log"
    result = _run_owned_logged_child(
        [sys.executable, "-B", "-u", "-c", probe_code],
        cwd=repository_root,
        env=child_environment,
        log_path=log_path,
        timeout=20.0,
    )
    probe_records = _read_prefixed_json_log_records(log_path, prefix=probe_marker)
    assert result["completed_before_deadline"] is True
    assert result["return_code"] == 0
    assert len(probe_records) == 1
    assert probe_records[0]["inherited_environment_checked"] is True
    assert probe_records[0]["formal_runtime_binding_active"] is False
    assert probe_records[0]["python_audit_write_guard"] == "installed"
    assert probe_records[0]["outside_write_blocked"] is True
    assert probe_records[0]["normal_private_database_read"] is True
    assert probe_records[0]["project_serializer_query_only"] is True
    assert probe_records[0]["project_serializer_write_blocked"] is True
    assert probe_records[0]["project_serializer_read_value"] == 11
    assert probe_records[0]["canonical_path_uri_query_only"] is True
    assert probe_records[0]["canonical_path_uri_write_blocked"] is True
    assert probe_records[0]["canonical_path_uri_read_value"] == 11
    assert probe_records[0]["private_rw_uri_allowed"] is True
    assert probe_records[0]["approved_synthetic_ro_query_only"] is True
    assert probe_records[0]["approved_synthetic_sqlite_master_count"] >= 0
    assert probe_records[0]["approved_synthetic_source_sha_unchanged"] is True
    assert probe_records[0]["external_ro_uri_blocked"] is True
    assert probe_records[0]["external_rw_uri_blocked"] is True
    assert probe_records[0]["private_create_uri_blocked"] is True
    assert probe_records[0]["ambiguous_duplicate_mode_uri_blocked"] is True
    assert probe_records[0]["unwrapped_file_uri_blocked"] is True
    assert probe_records[0]["synthetic_rw_uri_blocked"] is True
    assert probe_records[0]["external_plain_path_blocked"] is True
    assert not forbidden_target.exists()
    assert Path(child_environment["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"]).is_relative_to(
        qa_root
    )
    assert not Path(child_environment["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"]).exists()


def _supervise_main_journey_worker(
    f12_synthetic_sources: dict[str, Any],
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    qa_root = repository_root / "output" / "qa" / "f12_resume_20261011" / (
        f"main_candidate_{uuid4().hex}"
    )
    qa_root.mkdir(parents=True, exist_ok=False)
    run_root = Path(tempfile.gettempdir()) / f"f12_mainjourney_20261011_{uuid4().hex}"
    if run_root.exists():
        raise AssertionError(f"isolated run root already exists: {run_root}")
    environment = _main_window_environment(run_root, qa_root=qa_root)
    stage_log = qa_root / "initialization-stages.jsonl"
    stack_trace = qa_root / "initialization-stack.txt"
    isolation_manifest_path = qa_root / "startup-runtime-isolation.json"
    startup_environment = {
        "F12_MAIN_JOURNEY_WORKER": "1",
        "F12_MAIN_RUN_ROOT": str(run_root),
        "F12_MAIN_QA_ROOT": str(qa_root),
        "F12_STAGE_LOG": str(stage_log),
        "F12_STACK_TRACE": str(stack_trace),
        "F12_SYNTHETIC_ROOT": str(f12_synthetic_sources["root"]),
        "F12_RUNTIME_ISOLATION_MANIFEST": str(isolation_manifest_path),
        "F12_RUNTIME_ISOLATION_CHECK_PATH": str(
            qa_root / "startup-runtime-isolation-parent-check.json"
        ),
    }
    worker_environment = _isolated_environment(os.environ.copy(), environment)
    worker_environment.update(startup_environment)
    manifest_expected_environment = dict(environment)
    manifest_expected_environment.update(
        {
            key: value
            for key, value in startup_environment.items()
            if key != "F12_RUNTIME_ISOLATION_CHECK_PATH"
        }
    )
    _write_json_create_only(
        isolation_manifest_path,
        _startup_isolation_manifest(
            qa_root=qa_root,
            run_root=run_root,
            synthetic_root=f12_synthetic_sources["root"],
            expected_environment=manifest_expected_environment,
        ),
    )
    worker_pytest_root = run_root / "worker-pytest"
    command = [
        sys.executable,
        "-B",
        "-u",
        "-m",
        "pytest",
        f"{Path(__file__).resolve()}::test_normal_main_save_close_and_fresh_process_exact_revenue_journey",
        "-q",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        f"--basetemp={worker_pytest_root}",
    ]
    worker_log = qa_root / "worker-output.log"
    process_runner, process, owned_process_tree, log_handle = _spawn_owned_logged_process(
        command,
        cwd=repository_root,
        env=worker_environment,
        log_path=worker_log,
    )
    process_started = time.monotonic()
    initialization_started: float | None = None
    initialization_complete = False
    termination_reason: str | None = None
    last_active_process_count = 0
    try:
        while True:
            stages = _read_stage_names(stage_log)
            now = time.monotonic()
            if "initialization_started" in stages and initialization_started is None:
                initialization_started = now
            if "initialization_complete" in stages:
                initialization_complete = True
            worker_return_code = process.poll()
            last_active_process_count = _owned_process_tree_active_count(
                process,
                owned_process_tree,
            )
            if worker_return_code is not None and last_active_process_count == 0:
                break
            if (
                initialization_started is not None
                and not initialization_complete
                and now - initialization_started
                > MAIN_INITIALIZATION_DEADLINE_SECONDS + 2.0
            ):
                termination_reason = "main_initialization_deadline_exceeded"
                break
            if now - process_started > MAIN_JOURNEY_TOTAL_DEADLINE_SECONDS:
                termination_reason = "main_journey_total_deadline_exceeded"
                break
            time.sleep(0.2)
    except BaseException:
        _stop_and_close_owned_process_tree(
            process_runner,
            process,
            owned_process_tree,
            log_handle,
            stop_root=True,
        )
        raise

    return_code, termination_action = _stop_and_close_owned_process_tree(
        process_runner,
        process,
        owned_process_tree,
        log_handle,
        stop_root=termination_reason is not None,
    )
    worker_output = _read_log_tail(worker_log)
    worker_output_size = worker_log.stat().st_size
    worker_receipt = run_root / "durable_main_journey_receipt.json"
    receipt_copy = qa_root / "journey-receipt.json"
    if worker_receipt.is_file():
        receipt_copy.write_text(worker_receipt.read_text(encoding="utf-8"), encoding="utf-8")
    supervisor_receipt = {
        "status": "passed" if return_code == 0 else "failed",
        "exit_code": return_code,
        "termination_reason": termination_reason,
        "termination_action": termination_action,
        "initialization_deadline_seconds": MAIN_INITIALIZATION_DEADLINE_SECONDS,
        "journey_total_deadline_seconds": MAIN_JOURNEY_TOTAL_DEADLINE_SECONDS,
        "initialization_stages": sorted(_read_stage_names(stage_log)),
        "process_tree_management": owned_process_tree.management_mode,
        "process_tree_attached": owned_process_tree.attached,
        "process_tree_closed": owned_process_tree._job_handle is None
        if os.name == "nt"
        else True,
        "launcher_pid": process.pid,
        "active_process_count_at_last_poll": last_active_process_count,
        "combined_output_log": str(worker_log),
        "combined_output_log_size_bytes": worker_output_size,
        "isolated_run_root": str(run_root),
        "worker_pytest_root": str(worker_pytest_root),
    }
    (qa_root / "supervisor-receipt.json").write_text(
        json.dumps(supervisor_receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    assert return_code == 0 and termination_reason is None, (
        f"F12 Main worker failed: {supervisor_receipt!r}\n"
        f"combined worker output tail:\n{worker_output}\n"
        f"initialization stack: {stack_trace}"
    )


def _redact_watchlist_ui_diagnostic(
    value: str,
    *,
    private_paths: tuple[Path, ...],
) -> str:
    """移除 UI 例外文字內本次 QA 私人路徑後保留短診斷。"""

    sanitized = value
    for private_path in private_paths:
        spellings = {
            str(private_path),
            str(private_path).replace("/", "\\"),
            str(private_path).replace("\\", "/"),
        }
        for spelling in spellings:
            sanitized = re.sub(re.escape(spelling), "<private-path>", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(
        r"(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n\"']+",
        "<redacted-path>",
        sanitized,
    )
    return sanitized[:1000]


def _watchlist_widget_geometry(widget: Any) -> list[int]:
    geometry = widget.geometry()
    return [int(geometry.x()), int(geometry.y()), int(geometry.width()), int(geometry.height())]


def _watchlist_path_error_scope(
    raw_path: object,
    *,
    role_paths: dict[str, Path],
    private_roots: tuple[Path, ...],
    read_only_source_roots: tuple[Path, ...],
) -> dict[str, Any]:
    """只記錄 COW 例外檔案角色與 manifest 範圍，不保存絕對路徑。"""

    if not isinstance(raw_path, (str, bytes, os.PathLike)):
        return {
            "filename_role": "unavailable",
            "within_manifest_private_scope": False,
            "within_manifest_read_only_source_scope": False,
        }
    candidate = Path(os.path.abspath(os.fsdecode(os.fspath(raw_path))))

    def key(path: Path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))

    candidate_key = key(candidate)

    def is_inside(root: Path) -> bool:
        root_key = key(root)
        try:
            return os.path.commonpath((candidate_key, root_key)) == root_key
        except ValueError:
            return False

    filename_role = "outside_manifest_roots"
    for role, role_path in role_paths.items():
        if candidate_key == key(role_path):
            filename_role = role
            break
    else:
        target = role_paths.get("private_sqlite_target")
        if target is not None and candidate.parent == target.parent:
            if candidate.name.casefold().startswith(target.name.casefold() + "-"):
                filename_role = "private_sqlite_target_sidecar"
        if filename_role == "outside_manifest_roots":
            if any(is_inside(root) for root in private_roots):
                personal_root = role_paths.get("personal_root")
                if personal_root is not None and is_inside(personal_root):
                    filename_role = "personal_store_path"
                elif any(is_inside(root) for root in role_paths.values()):
                    filename_role = "declared_private_path"
                else:
                    filename_role = "private_run_or_qa_path"
            elif any(is_inside(root) for root in read_only_source_roots):
                filename_role = "synthetic_read_only_source_path"

    return {
        "filename_role": filename_role,
        "within_manifest_private_scope": any(
            is_inside(root) for root in private_roots
        ),
        "within_manifest_read_only_source_scope": any(
            is_inside(root) for root in read_only_source_roots
        ),
    }


def _close_watchlist_view_and_drain_workers(view: Any, app: Any) -> dict[str, Any]:
    """關閉小型探針視窗並合作式排空受管 worker。"""

    from ui_qt.workers.task_worker import (
        request_cooperative_task_worker_shutdown,
        running_task_workers,
    )

    started_ns = time.monotonic_ns()
    close_error_type: str | None = None
    try:
        if view.isVisible():
            view.close()
    except Exception as exc:
        close_error_type = type(exc).__name__
    finally:
        app.processEvents()
    request_cooperative_task_worker_shutdown()
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        app.processEvents()
        if not running_task_workers():
            break
        time.sleep(0.01)
    remaining = running_task_workers()
    return {
        "schema": "f12-watchlist-worker-drain.v1",
        "close_requested": True,
        "close_error_type": close_error_type,
        "cooperative_shutdown_requested": True,
        "worker_registry_zero": not remaining,
        "remaining_worker_count": len(remaining),
        "elapsed_ns": max(0, time.monotonic_ns() - started_ns),
    }


def _install_watchlist_upgrade_observers(
    service: PersonalWatchlistService,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_root: Path,
    qa_root: Path,
) -> dict[str, list[dict[str, Any]]]:
    """觀察真實升級與 backup 函式的回傳或例外，不替換其實作。"""

    from data_module import watchlist_json_cow

    control_paths = service.control_paths
    target_path = service.canonical_repository_path
    role_paths = {
        "legacy_source_file": control_paths.source_path,
        "legacy_source_directory": control_paths.source_path.parent,
        "private_sqlite_target": target_path,
        "cow_activation_marker": control_paths.marker_path,
        "cow_conversion_receipt": control_paths.receipt_path,
        "legacy_source_backup": control_paths.source_backup_path,
        "personal_root": service.personal_paths.personal_root,
    }
    private_roots = (qa_root, run_root)
    read_only_roots = (Path(os.environ["F12_SYNTHETIC_ROOT"]),)
    observed = {"upgrade_outcomes": [], "backup_attempts": []}
    original_upgrade = service.upgrade_to_repository
    original_write_source_backup = watchlist_json_cow._write_source_backup

    def observe_upgrade() -> Any:
        try:
            status = original_upgrade()
        except BaseException as exc:
            cause = exc.__cause__ or exc
            observed["upgrade_outcomes"].append(
                {
                    "outcome": "raised",
                    "exception_type": type(exc).__name__,
                    "error_code": str(getattr(exc, "code", "")) or None,
                    "cause_type": type(cause).__name__,
                    "errno": getattr(cause, "errno", None),
                    "winerror": getattr(cause, "winerror", None),
                    "message": _redact_watchlist_ui_diagnostic(
                        str(exc),
                        private_paths=tuple(role_paths.values())
                        + (run_root, qa_root),
                    ),
                }
            )
            raise
        observed["upgrade_outcomes"].append(
            {
                "outcome": "returned",
                "service_mode": getattr(status, "mode", None),
                "service_is_repository": bool(
                    getattr(status, "is_repository", False)
                ),
                "service_upgrade_available": bool(
                    getattr(status, "upgrade_available", False)
                ),
            }
        )
        return status

    def observe_source_backup(*args: Any, **kwargs: Any) -> Any:
        active_control_paths = args[0] if args else control_paths
        backup_path = active_control_paths.source_backup_path
        first_guard_event = len(_F12_FD_GUARD_EVENTS)
        try:
            result = original_write_source_backup(*args, **kwargs)
        except BaseException as exc:
            cause = exc.__cause__ or exc
            guard_events = _F12_FD_GUARD_EVENTS[first_guard_event:]
            filename = getattr(cause, "filename", None)
            cause_record: dict[str, Any] = {
                "outcome": "raised",
                "operation_path_role": "legacy_source_backup",
                "operation_path_roles": [
                    "legacy_source_file",
                    "legacy_source_backup",
                    "cow_activation_marker",
                    "cow_conversion_receipt",
                    "private_sqlite_target",
                ],
                "exception_type": type(exc).__name__,
                "error_code": str(getattr(exc, "code", "")) or None,
                "cause_type": type(cause).__name__,
                "errno": getattr(cause, "errno", None),
                "winerror": getattr(cause, "winerror", None),
                "cause_filename_available": filename is not None,
                "message": _redact_watchlist_ui_diagnostic(
                    str(cause),
                    private_paths=(
                        run_root,
                        qa_root,
                        active_control_paths.source_path,
                        backup_path,
                        target_path,
                    ),
                ),
            }
            cause_record.update(
                _watchlist_path_error_scope(
                    filename,
                    role_paths=role_paths,
                    private_roots=private_roots,
                    read_only_source_roots=read_only_roots,
                )
            )
            cause_record["guard_event_count_during_backup"] = len(guard_events)
            guard_event = next(
                (
                    event
                    for event in reversed(guard_events)
                    if event.get("event") in {
                        "fdopen_rejected",
                        "fdopen_authorized",
                        "fdopen_authorized_closefd_false_via_owned_duplicate",
                        "fdopen_failed_after_handle_validation",
                        "fdopen_failed_after_duplicate_validation",
                        "fdopen_duplicate_cleanup",
                        "write_path_rejected",
                    }
                ),
                None,
            )
            if guard_event is not None:
                cause_record["descriptor_guard_event"] = dict(guard_event)
                cause_record["guard_errno"] = guard_event.get("errno")
                cause_record["guard_winerror"] = guard_event.get("winerror")
            observed["backup_attempts"].append(cause_record)
            raise
        observed["backup_attempts"].append(
            {
                "outcome": "returned",
                "operation_path_role": "legacy_source_backup",
                "return_path_role": "legacy_source_backup",
                "backup_sha256": str(result[1]),
                "guard_event_count_during_backup": len(
                    _F12_FD_GUARD_EVENTS[first_guard_event:]
                ),
            }
        )
        return result

    monkeypatch.setattr(service, "upgrade_to_repository", observe_upgrade)
    monkeypatch.setattr(
        watchlist_json_cow,
        "_write_source_backup",
        observe_source_backup,
    )
    return observed


def _assert_watchlist_upgrade_modal_branch(
    upgrade_outcomes: list[dict[str, Any]],
    modal_counts: dict[str, int],
) -> None:
    """按真實 upgrade 回傳、回傳失敗或拋例外分支核對 modal 次數。"""

    assert len(upgrade_outcomes) == 1, upgrade_outcomes
    outcome = upgrade_outcomes[0]
    information = modal_counts["information"]
    warning = modal_counts["warning"]
    assert modal_counts["question"] == 1, (outcome, modal_counts)
    if outcome["outcome"] == "raised":
        assert information == 0 and warning == 0, (outcome, modal_counts)
    elif outcome["outcome"] == "returned" and outcome["service_is_repository"]:
        assert information == 1 and warning == 0, (outcome, modal_counts)
    elif outcome["outcome"] == "returned":
        assert information == 0 and warning == 1, (outcome, modal_counts)
    else:
        raise AssertionError(f"unknown watchlist upgrade outcome: {outcome!r}")


def test_watchlist_upgrade_modal_branch_oracle() -> None:
    """驗證真實升級的回傳成功、回傳阻擋與例外三種 modal 分支。"""

    valid_cases = (
        (
            {"outcome": "returned", "service_is_repository": True},
            {"question": 1, "information": 1, "warning": 0},
        ),
        (
            {"outcome": "returned", "service_is_repository": False},
            {"question": 1, "information": 0, "warning": 1},
        ),
        (
            {"outcome": "raised", "exception_type": "PermissionError"},
            {"question": 1, "information": 0, "warning": 0},
        ),
    )
    for outcome, counts in valid_cases:
        _assert_watchlist_upgrade_modal_branch([outcome], counts)

    invalid_cases = (
        (
            {"outcome": "raised", "exception_type": "PermissionError"},
            {"question": 1, "information": 1, "warning": 0},
        ),
        (
            {"outcome": "returned", "service_is_repository": True},
            {"question": 1, "information": 0, "warning": 1},
        ),
        (
            {"outcome": "returned", "service_is_repository": False},
            {"question": 0, "information": 0, "warning": 1},
        ),
    )
    for outcome, counts in invalid_cases:
        with pytest.raises(AssertionError):
            _assert_watchlist_upgrade_modal_branch([outcome], counts)


def test_watchlist_backup_failure_observer_records_safe_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用受控例外核對 backup observer 的角色、錯誤碼與路徑遮罩。"""

    from data_module import watchlist_json_cow

    qa_root = tmp_path / "qa-root"
    run_root = tmp_path / "private-run-root"
    synthetic_root = tmp_path / "approved-synthetic-source"
    source_path = qa_root / "source" / "default.json"
    backup_path = run_root / "watchlist" / "default.json.source-backup"
    target_path = run_root / "personal" / "repository.sqlite"
    control_paths = SimpleNamespace(
        source_path=source_path,
        source_backup_path=backup_path,
        marker_path=run_root / "watchlist" / "conversion.marker",
        receipt_path=run_root / "watchlist" / "conversion.receipt.json",
    )
    service = SimpleNamespace(
        control_paths=control_paths,
        canonical_repository_path=target_path,
        personal_paths=SimpleNamespace(personal_root=run_root / "personal"),
    )

    def fail_source_backup(*_args: Any, **_kwargs: Any) -> Any:
        _F12_FD_GUARD_EVENTS.append(
            {
                "event": "fdopen_rejected",
                "reason": "canonical_handle_path_unavailable",
                "path_role": "manifest_private_write_root",
                "errno": 13,
                "winerror": 5,
            }
        )
        raise PermissionError(13, "controlled backup denial", str(backup_path))

    def run_upgrade():
        return watchlist_json_cow._write_source_backup(control_paths)

    service.upgrade_to_repository = run_upgrade
    monkeypatch.setattr(
        watchlist_json_cow,
        "_write_source_backup",
        fail_source_backup,
    )
    monkeypatch.setenv("F12_SYNTHETIC_ROOT", str(synthetic_root))
    prior_events = list(_F12_FD_GUARD_EVENTS)
    _F12_FD_GUARD_EVENTS[:] = [
        {
            "event": "fdopen_rejected",
            "reason": "stale_event_before_backup",
            "path_role": "outside_manifest_roots",
            "errno": 13,
            "winerror": None,
        }
    ]
    try:
        observed = _install_watchlist_upgrade_observers(
            service,  # type: ignore[arg-type]
            monkeypatch,
            run_root=run_root,
            qa_root=qa_root,
        )
        with pytest.raises(PermissionError):
            service.upgrade_to_repository()
    finally:
        _F12_FD_GUARD_EVENTS[:] = prior_events

    assert observed["upgrade_outcomes"][0]["outcome"] == "raised"
    assert observed["upgrade_outcomes"][0]["cause_type"] == "PermissionError"
    assert observed["upgrade_outcomes"][0]["errno"] == 13
    backup_attempt = observed["backup_attempts"][0]
    assert backup_attempt["operation_path_role"] == "legacy_source_backup"
    assert backup_attempt["filename_role"] == "legacy_source_backup"
    assert backup_attempt["within_manifest_private_scope"] is True
    assert backup_attempt["cause_type"] == "PermissionError"
    assert backup_attempt["errno"] == 13
    assert backup_attempt["guard_winerror"] == 5
    assert backup_attempt["guard_event_count_during_backup"] == 1
    assert backup_attempt["descriptor_guard_event"]["reason"] == (
        "canonical_handle_path_unavailable"
    )
    assert str(tmp_path) not in json.dumps(observed)


def _supervise_watchlist_view_upgrade_probe() -> None:
    """在相同 startup guard 與 owned Job 內執行小型真 WatchlistView 探針。"""

    repository_root = Path(__file__).resolve().parents[1]
    qa_root = repository_root / "output" / "qa" / "f12_resume_20261011" / (
        f"watchlist_view_probe_{uuid4().hex}"
    )
    qa_root.mkdir(parents=True, exist_ok=False)
    run_root = Path(tempfile.gettempdir()) / f"f12_watchlist_view_20261011_{uuid4().hex}"
    if run_root.exists():
        raise AssertionError(f"isolated watchlist probe root already exists: {run_root}")
    requested_synthetic_root = os.environ.get("F12_SYNTHETIC_ROOT", "").strip()
    if not requested_synthetic_root:
        raise AssertionError("F12_SYNTHETIC_ROOT 必須明示指定；禁止自動替代來源")
    synthetic_root = Path(requested_synthetic_root).resolve(strict=False)
    if (
        synthetic_root.name != F12_SYNTHETIC_ROOT_NAME
        or synthetic_root.parent
        != (repository_root / "output" / "qa" / "f12_resume_20261011").resolve()
        or not synthetic_root.is_dir()
    ):
        raise AssertionError(f"小型 WatchlistView 探針的 synthetic root 不符：{synthetic_root}")
    environment = _main_window_environment(run_root, qa_root=qa_root)
    isolation_manifest_path = qa_root / "startup-runtime-isolation.json"
    startup_environment = {
        "F12_WATCHLIST_VIEW_PROBE": "1",
        "F12_MAIN_RUN_ROOT": str(run_root),
        "F12_MAIN_QA_ROOT": str(qa_root),
        "F12_SYNTHETIC_ROOT": str(synthetic_root),
        "F12_RUNTIME_ISOLATION_MANIFEST": str(isolation_manifest_path),
        "F12_RUNTIME_ISOLATION_CHECK_PATH": str(
            qa_root / "startup-runtime-isolation-child-check.json"
        ),
    }
    worker_environment = _isolated_environment(os.environ.copy(), environment)
    worker_environment.update(startup_environment)
    manifest_expected_environment = dict(environment)
    manifest_expected_environment.update(
        {
            key: value
            for key, value in startup_environment.items()
            if key != "F12_RUNTIME_ISOLATION_CHECK_PATH"
        }
    )
    _write_json_create_only(
        isolation_manifest_path,
        _startup_isolation_manifest(
            qa_root=qa_root,
            run_root=run_root,
            synthetic_root=synthetic_root,
            expected_environment=manifest_expected_environment,
        ),
    )
    command = [
        sys.executable,
        "-B",
        "-u",
        "-m",
        "pytest",
        f"{Path(__file__).resolve()}::test_watchlist_view_upgrade_click_reports_private_storage_result",
        "-q",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        f"--basetemp={run_root / 'worker-pytest'}",
    ]
    worker_log = qa_root / "watchlist-view-worker.log"
    result = _run_owned_logged_child(
        command,
        cwd=repository_root,
        env=worker_environment,
        log_path=worker_log,
        timeout=120.0,
    )
    receipt_path = qa_root / "watchlist-upgrade-ui-receipt.json"
    supervisor_receipt = {
        "schema": "f12-watchlist-view-upgrade-supervisor.v1",
        "status": "passed" if result["return_code"] == 0 else "failed",
        "worker_result": result,
        "ui_receipt": str(receipt_path),
    }
    _write_json_create_only(qa_root / "supervisor-receipt.json", supervisor_receipt)
    worker_output = _read_log_tail(worker_log)
    assert result["return_code"] == 0, (
        f"小型 WatchlistView COW UI 探針失敗：{supervisor_receipt!r}\n"
        f"worker log 尾端：\n{worker_output}"
    )
    assert receipt_path.is_file(), f"UI 探針缺少 receipt：{receipt_path}"


def _supervise_fdopen_descriptor_guard_probe() -> None:
    """以同一啟動守衛隔離檢查 os.open → os.fdopen 的 descriptor 行為。"""

    repository_root = Path(__file__).resolve().parents[1]
    qa_root = repository_root / "output" / "qa" / "f12_resume_20261011" / (
        f"fdopen_guard_probe_{uuid4().hex}"
    )
    qa_root.mkdir(parents=True, exist_ok=False)
    run_root = Path(tempfile.gettempdir()) / f"f12_fdopen_guard_20261011_{uuid4().hex}"
    if run_root.exists():
        raise AssertionError("fdopen guard private run root unexpectedly exists")
    requested_synthetic_root = os.environ.get("F12_SYNTHETIC_ROOT", "").strip()
    if not requested_synthetic_root:
        raise AssertionError("F12_SYNTHETIC_ROOT 必須明示指定；禁止自動替代來源")
    synthetic_root = Path(requested_synthetic_root).resolve(strict=False)
    if (
        synthetic_root.name != F12_SYNTHETIC_ROOT_NAME
        or synthetic_root.parent
        != (repository_root / "output" / "qa" / "f12_resume_20261011").resolve()
        or not synthetic_root.is_dir()
    ):
        raise AssertionError("fdopen guard probe 的 synthetic root 不符")
    environment = _main_window_environment(run_root, qa_root=qa_root)
    outside_path = qa_root.parent / f"{qa_root.name}-outside" / "external-fd.bin"
    startup_environment = {
        "F12_FD_GUARD_PROBE": "1",
        "F12_MAIN_RUN_ROOT": str(run_root),
        "F12_MAIN_QA_ROOT": str(qa_root),
        "F12_SYNTHETIC_ROOT": str(synthetic_root),
        "F12_FD_GUARD_EXTERNAL_PATH": str(outside_path),
        "F12_RUNTIME_ISOLATION_MANIFEST": str(
            qa_root / "startup-runtime-isolation.json"
        ),
        "F12_RUNTIME_ISOLATION_CHECK_PATH": str(
            qa_root / "startup-runtime-isolation-child-check.json"
        ),
    }
    worker_environment = _isolated_environment(os.environ.copy(), environment)
    worker_environment.update(startup_environment)
    manifest_expected_environment = dict(environment)
    manifest_expected_environment.update(
        {
            key: value
            for key, value in startup_environment.items()
            if key != "F12_RUNTIME_ISOLATION_CHECK_PATH"
        }
    )
    _write_json_create_only(
        Path(startup_environment["F12_RUNTIME_ISOLATION_MANIFEST"]),
        _startup_isolation_manifest(
            qa_root=qa_root,
            run_root=run_root,
            synthetic_root=synthetic_root,
            expected_environment=manifest_expected_environment,
        ),
    )
    command = [
        sys.executable,
        "-B",
        "-u",
        "-m",
        "pytest",
        f"{Path(__file__).resolve()}::test_startup_write_guard_fdopen_descriptor_roles",
        "-q",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        f"--basetemp={run_root / 'worker-pytest'}",
    ]
    worker_log = qa_root / "fdopen-guard-worker.log"
    result = _run_owned_logged_child(
        command,
        cwd=repository_root,
        env=worker_environment,
        log_path=worker_log,
        timeout=60.0,
    )
    receipt_path = qa_root / "fdopen-guard-role-receipt.json"
    supervisor_receipt = {
        "schema": "f12-fdopen-guard-supervisor.v1",
        "status": "passed" if result["return_code"] == 0 else "failed",
        "worker_result": result,
        "role_receipt": str(receipt_path),
    }
    _write_json_create_only(qa_root / "supervisor-receipt.json", supervisor_receipt)
    assert result["return_code"] == 0, (
        f"fdopen descriptor guard probe 失敗：{supervisor_receipt!r}\n"
        f"worker log 尾端：\n{_read_log_tail(worker_log)}"
    )
    assert receipt_path.is_file(), f"fdopen guard probe 缺少 receipt：{receipt_path}"


def test_startup_write_guard_fdopen_descriptor_roles() -> None:
    """驗證 guard 對 os.fdopen 整數 descriptor 的正負例。"""

    if os.environ.get("F12_FD_GUARD_PROBE") != "1":
        _supervise_fdopen_descriptor_guard_probe()
        return

    run_root = Path(os.environ["F12_MAIN_RUN_ROOT"])
    qa_root = Path(os.environ["F12_MAIN_QA_ROOT"])
    environment = _main_window_environment(run_root, qa_root=qa_root)
    for name in F12_UNSET_STARTUP_ENVIRONMENT:
        os.environ.pop(name, None)
    os.environ.update(environment)
    for name in F12_EMPTY_STARTUP_ENVIRONMENT:
        os.environ[name] = ""

    import stat

    external_path = Path(os.environ["F12_FD_GUARD_EXTERNAL_PATH"])
    external_path.parent.mkdir(parents=True, exist_ok=True)
    external_fd = os.open(
        external_path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    external_closefd_false_fd = os.open(external_path, os.O_WRONLY)
    private_path = run_root / "personal-data" / "fdopen-private.bin"
    private_path.parent.mkdir(parents=True, exist_ok=True)
    hardlink_source_path = external_path.parent / "external-hardlink-source.bin"
    hardlink_alias_path = run_root / "personal-data" / "pre-guard-hardlink-alias.bin"
    hardlink_source_path.write_bytes(b"external hardlink source must stay unchanged\n")
    os.link(hardlink_source_path, hardlink_alias_path)
    hardlink_source_sha_before = _sha256_file(hardlink_source_path)
    hardlink_alias_sha_before = _sha256_file(hardlink_alias_path)
    hardlink_count_before = int(hardlink_alias_path.stat().st_nlink)
    hardlink_pre_guard_fd = os.open(hardlink_alias_path, os.O_WRONLY)
    hardlink_closefd_false_fd = os.open(hardlink_alias_path, os.O_WRONLY)
    startup_guard_receipt = _validate_and_install_startup_write_guard()

    def extended_dos_path(path: Path) -> str:
        """為本機路徑建立明確的 DOS extended-length 表示。"""

        if os.name != "nt":
            raise AssertionError("extended DOS path probe requires Windows")
        raw_text = os.path.abspath(str(path))
        if raw_text.casefold().startswith("\\\\?\\"):
            raw_text = raw_text[4:]
        drive, tail = os.path.splitdrive(raw_text)
        if (
            len(drive) != 2
            or drive[1] != ":"
            or not drive[0].isascii()
            or not drive[0].isalpha()
            or not tail.startswith(("\\", "/"))
        ):
            raise AssertionError("probe path is not an absolute local DOS path")
        return "\\\\?\\" + raw_text

    def attempt_extended_os_open(
        case_name: str,
        raw_path: str,
        flags: int,
        *,
        payload: bytes | None = None,
    ) -> dict[str, Any]:
        event_start = len(_F12_FD_GUARD_EVENTS)
        descriptor: int | None = None
        result: dict[str, Any]
        try:
            descriptor = os.open(raw_path, flags, 0o600)
            if payload is not None:
                os.write(descriptor, payload)
            result = {
                "case": case_name,
                "accepted": True,
                "error_type": None,
                "errno": None,
                "winerror": None,
            }
        except Exception as exc:
            result = {
                "case": case_name,
                "accepted": False,
                "error_type": type(exc).__name__,
                "errno": getattr(exc, "errno", None),
                "winerror": getattr(exc, "winerror", None),
            }
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError as close_error:
                    result["close_error_type"] = type(close_error).__name__
                    result["close_error_errno"] = getattr(
                        close_error, "errno", None
                    )
        result["guard_events"] = [
            {
                key: event.get(key)
                for key in (
                    "event",
                    "reason",
                    "path_role",
                    "target_scope",
                    "target_relative",
                    "errno",
                    "winerror",
                    "write_capable",
                    "regular_file",
                    "win_identity_verified",
                    "handle_link_count",
                    "canonical_path_api",
                )
                if key in event
            }
            for event in _F12_FD_GUARD_EVENTS[event_start:]
        ]
        return result

    def seal_fd_guard_event_window(
        name: str,
        start_index: int,
        descriptor_number: int | None,
    ) -> dict[str, Any]:
        end_index = len(_F12_FD_GUARD_EVENTS)
        return {
            "name": name,
            "descriptor_number": descriptor_number,
            "start_index": start_index,
            "end_index": end_index,
            "events": [
                dict(event)
                for event in _F12_FD_GUARD_EVENTS[start_index:end_index]
            ],
        }

    private_fd: int | None = None
    private_result: dict[str, Any]
    try:
        private_fd = os.open(
            private_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(private_fd, "wb") as stream:
            stream.write(b"f12 fdopen descriptor role probe\n")
        private_result = {"accepted": True, "error_type": None}
    except Exception as exc:
        private_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
        }
    finally:
        if private_fd is not None:
            try:
                os.close(private_fd)
            except OSError:
                pass

    closefd_false_path = (
        run_root / "personal-data" / "closefd-false-caller-retained.bin"
    )
    closefd_false_fd: int | None = None
    closefd_false_stream: Any | None = None
    closefd_false_caller_fd_number: int | None = None
    closefd_false_result: dict[str, Any]
    closefd_false_fdopen_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        closefd_false_fd = os.open(
            closefd_false_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        closefd_false_caller_fd_number = closefd_false_fd
        closefd_false_stream = os.fdopen(
            closefd_false_fd,
            "wb",
            closefd=False,
        )
        closefd_false_stream_fd = int(closefd_false_stream.fileno())
        closefd_false_stream.write(b"stream-before-caller:")
        closefd_false_stream.flush()
        os.fsync(closefd_false_stream_fd)
        closefd_false_stream.close()
        closefd_false_stream_closed = closefd_false_stream.closed
        try:
            os.fstat(closefd_false_fd)
            caller_fd_retained_after_stream_close = True
        except OSError:
            caller_fd_retained_after_stream_close = False
        os.fsync(closefd_false_fd)
        caller_write_count = os.write(
            closefd_false_fd,
            b"caller-after-stream-close",
        )
        os.fsync(closefd_false_fd)
        os.close(closefd_false_fd)
        closefd_false_fd = None
        closefd_false_result = {
            "accepted": True,
            "error_type": None,
            "caller_descriptor_number": closefd_false_caller_fd_number,
            "stream_descriptor_number": closefd_false_stream_fd,
            "stream_fd_differs_from_caller_fd": (
                closefd_false_stream_fd != closefd_false_caller_fd_number
            ),
            "stream_closed_before_caller_write": closefd_false_stream_closed,
            "caller_fd_retained_after_stream_close": (
                caller_fd_retained_after_stream_close
            ),
            "caller_write_count": caller_write_count,
            "caller_descriptor_closed_by_caller": True,
            "bytes_exact": (
                closefd_false_path.read_bytes()
                == b"stream-before-caller:caller-after-stream-close"
            ),
        }
    except Exception as exc:
        closefd_false_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
        }
    finally:
        if closefd_false_stream is not None and not closefd_false_stream.closed:
            try:
                closefd_false_stream.close()
            except OSError:
                pass
        if closefd_false_fd is not None:
            try:
                os.close(closefd_false_fd)
            except OSError:
                pass
    closefd_false_fdopen_event_window = seal_fd_guard_event_window(
        "closefd_false_private_writer",
        closefd_false_fdopen_event_start,
        closefd_false_caller_fd_number,
    )

    closefd_false_reuse_source_path = (
        run_root / "personal-data" / "closefd-false-reuse-source.bin"
    )
    closefd_false_reuse_target_path = (
        run_root / "personal-data" / "closefd-false-reuse-target.bin"
    )
    closefd_false_reuse_fd: int | None = None
    closefd_false_reuse_stream: Any | None = None
    closefd_false_reuse_target_fd: int | None = None
    closefd_false_reuse_original_descriptor_number: int | None = None
    closefd_false_reuse_result: dict[str, Any]
    closefd_false_reuse_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        closefd_false_reuse_fd = os.open(
            closefd_false_reuse_source_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        closefd_false_reuse_original_descriptor_number = closefd_false_reuse_fd
        closefd_false_reuse_stream = os.fdopen(
            closefd_false_reuse_fd,
            "wb",
            closefd=False,
        )
        closefd_false_reuse_stream_fd = int(
            closefd_false_reuse_stream.fileno()
        )
        closefd_false_reuse_stream.write(b"before-number-reuse:")
        closefd_false_reuse_stream.flush()
        os.close(closefd_false_reuse_fd)
        original_reuse_number = closefd_false_reuse_fd
        closefd_false_reuse_fd = None
        closefd_false_reuse_target_fd = os.open(
            closefd_false_reuse_target_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        reused_number_matches = (
            closefd_false_reuse_target_fd == original_reuse_number
        )
        reused_target_number = closefd_false_reuse_target_fd
        closefd_false_reuse_stream.write(b"after-number-reuse")
        closefd_false_reuse_stream.flush()
        os.fsync(closefd_false_reuse_stream_fd)
        closefd_false_reuse_stream.close()
        closefd_false_reuse_stream_closed = closefd_false_reuse_stream.closed
        target_control_write_count = os.write(
            closefd_false_reuse_target_fd,
            b"target-descriptor-control",
        )
        os.fsync(closefd_false_reuse_target_fd)
        os.close(closefd_false_reuse_target_fd)
        closefd_false_reuse_target_fd = None
        closefd_false_reuse_result = {
            "accepted": True,
            "error_type": None,
            "original_caller_descriptor_number": original_reuse_number,
            "stream_descriptor_number": closefd_false_reuse_stream_fd,
            "reused_descriptor_number": reused_target_number,
            "stream_fd_differs_from_caller_fd": (
                closefd_false_reuse_stream_fd != original_reuse_number
            ),
            "caller_descriptor_number_reused": reused_number_matches,
            "stream_fd_differs_from_reused_descriptor": (
                closefd_false_reuse_stream_fd != reused_target_number
            ),
            "stream_closed_after_reuse_write": closefd_false_reuse_stream_closed,
            "target_control_write_count": target_control_write_count,
            "source_bytes_exact": (
                closefd_false_reuse_source_path.read_bytes()
                == b"before-number-reuse:after-number-reuse"
            ),
            "reused_target_bytes_exact": (
                closefd_false_reuse_target_path.read_bytes()
                == b"target-descriptor-control"
            ),
        }
    except Exception as exc:
        closefd_false_reuse_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
        }
    finally:
        if (
            closefd_false_reuse_stream is not None
            and not closefd_false_reuse_stream.closed
        ):
            try:
                closefd_false_reuse_stream.close()
            except OSError:
                pass
        if closefd_false_reuse_fd is not None:
            try:
                os.close(closefd_false_reuse_fd)
            except OSError:
                pass
        if closefd_false_reuse_target_fd is not None:
            try:
                os.close(closefd_false_reuse_target_fd)
            except OSError:
                pass
    closefd_false_reuse_event_window = seal_fd_guard_event_window(
        "closefd_false_number_reuse",
        closefd_false_reuse_event_start,
        closefd_false_reuse_original_descriptor_number,
    )

    closefd_false_constructor_path = (
        run_root / "personal-data" / "closefd-false-constructor-failure.bin"
    )
    closefd_false_constructor_fd: int | None = None
    constructor_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        closefd_false_constructor_fd = os.open(
            closefd_false_constructor_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        os.fdopen(
            closefd_false_constructor_fd,
            "wb",
            closefd=False,
            f12_unknown_constructor_argument=True,
        )
        closefd_false_constructor_result = {
            "raised_native_type_error": False,
            "error_type": None,
        }
    except TypeError as exc:
        try:
            os.fstat(closefd_false_constructor_fd)
            caller_fd_retained_after_failure = True
        except OSError:
            caller_fd_retained_after_failure = False
        cleanup_events = [
            event
            for event in _F12_FD_GUARD_EVENTS[constructor_event_start:]
            if event.get("event") == "fdopen_duplicate_cleanup"
        ]
        failure_events = [
            event
            for event in _F12_FD_GUARD_EVENTS[constructor_event_start:]
            if event.get("event") == "fdopen_failed_after_duplicate_validation"
        ]
        closefd_false_constructor_result = {
            "raised_native_type_error": True,
            "error_type": type(exc).__name__,
            "caller_fd_retained_after_failure": caller_fd_retained_after_failure,
            "native_constructor_failure_event": failure_events[-1]
            if failure_events
            else None,
            "duplicate_cleanup_event": cleanup_events[-1]
            if cleanup_events
            else None,
        }
    except Exception as exc:
        closefd_false_constructor_result = {
            "raised_native_type_error": False,
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
        }
    finally:
        if closefd_false_constructor_fd is not None:
            try:
                os.close(closefd_false_constructor_fd)
            except OSError:
                pass
    closefd_false_constructor_event_window = seal_fd_guard_event_window(
        "closefd_false_constructor_failure",
        constructor_event_start,
        closefd_false_constructor_fd,
    )
    constructor_window_cleanup_events = [
        event
        for event in closefd_false_constructor_event_window["events"]
        if event.get("event") == "fdopen_duplicate_cleanup"
    ]
    constructor_window_failure_events = [
        event
        for event in closefd_false_constructor_event_window["events"]
        if event.get("event") == "fdopen_failed_after_duplicate_validation"
    ]
    closefd_false_constructor_result["duplicate_cleanup_event"] = (
        constructor_window_cleanup_events[-1]
        if constructor_window_cleanup_events
        else None
    )
    closefd_false_constructor_result["native_constructor_failure_event"] = (
        constructor_window_failure_events[-1]
        if constructor_window_failure_events
        else None
    )

    duplicate_closefd_path = (
        run_root / "personal-data" / "closefd-false-duplicate-kwargs.bin"
    )
    duplicate_closefd_fd: int | None = None
    duplicate_closefd_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        duplicate_closefd_fd = os.open(
            duplicate_closefd_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        os.fdopen(
            duplicate_closefd_fd,
            "wb",
            -1,
            None,
            None,
            None,
            False,
            closefd=False,
        )
        duplicate_closefd_result = {
            "raised_native_type_error": False,
            "error_type": None,
        }
    except TypeError as exc:
        try:
            os.fstat(duplicate_closefd_fd)
            duplicate_closefd_caller_retained = True
        except OSError:
            duplicate_closefd_caller_retained = False
        cleanup_events = [
            event
            for event in _F12_FD_GUARD_EVENTS[duplicate_closefd_event_start:]
            if event.get("event") == "fdopen_duplicate_cleanup"
        ]
        failure_events = [
            event
            for event in _F12_FD_GUARD_EVENTS[duplicate_closefd_event_start:]
            if event.get("event") == "fdopen_failed_after_duplicate_validation"
        ]
        duplicate_closefd_result = {
            "raised_native_type_error": True,
            "error_type": type(exc).__name__,
            "caller_fd_retained_after_failure": duplicate_closefd_caller_retained,
            "native_constructor_failure_event": failure_events[-1]
            if failure_events
            else None,
            "duplicate_cleanup_event": cleanup_events[-1]
            if cleanup_events
            else None,
        }
    except Exception as exc:
        duplicate_closefd_result = {
            "raised_native_type_error": False,
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
        }
    finally:
        if duplicate_closefd_fd is not None:
            try:
                os.close(duplicate_closefd_fd)
            except OSError:
                pass
    duplicate_closefd_event_window = seal_fd_guard_event_window(
        "closefd_false_duplicate_closefd_kwargs_failure",
        duplicate_closefd_event_start,
        duplicate_closefd_fd,
    )
    duplicate_closefd_window_cleanup_events = [
        event
        for event in duplicate_closefd_event_window["events"]
        if event.get("event") == "fdopen_duplicate_cleanup"
    ]
    duplicate_closefd_window_failure_events = [
        event
        for event in duplicate_closefd_event_window["events"]
        if event.get("event") == "fdopen_failed_after_duplicate_validation"
    ]
    duplicate_closefd_result["duplicate_cleanup_event"] = (
        duplicate_closefd_window_cleanup_events[-1]
        if duplicate_closefd_window_cleanup_events
        else None
    )
    duplicate_closefd_result["native_constructor_failure_event"] = (
        duplicate_closefd_window_failure_events[-1]
        if duplicate_closefd_window_failure_events
        else None
    )

    closefd_false_reuse_failure_path = (
        run_root / "personal-data" / "closefd-false-reused-duplicate-target.bin"
    )
    closefd_false_reuse_failure_source_path = (
        run_root / "personal-data" / "closefd-false-reused-duplicate-source.bin"
    )
    closefd_false_reuse_failure_source_fd: int | None = None
    reuse_failure_hook_state: dict[str, Any] = {}
    reuse_failure_event_start = len(_F12_FD_GUARD_EVENTS)

    def close_duplicate_reuse_number_then_raise(duplicate_number: int) -> None:
        os.close(duplicate_number)
        replacement_descriptor = os.open(
            closefd_false_reuse_failure_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        reuse_failure_hook_state.update(
            {
                "duplicate_number": duplicate_number,
                "replacement_descriptor": replacement_descriptor,
                "same_descriptor_number": (
                    replacement_descriptor == duplicate_number
                ),
            }
        )
        raise TypeError("controlled constructor failure after fd reuse")

    previous_failure_hook = _F12_FDOPEN_DUPLICATE_FAILURE_HOOK
    try:
        closefd_false_reuse_failure_source_fd = os.open(
            closefd_false_reuse_failure_source_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        globals()["_F12_FDOPEN_DUPLICATE_FAILURE_HOOK"] = (
            close_duplicate_reuse_number_then_raise
        )
        try:
            os.fdopen(
                closefd_false_reuse_failure_source_fd,
                "wb",
                closefd=False,
            )
            reuse_failure_constructor_result = {
                "raised_type_error": False,
                "error_type": None,
            }
        except TypeError as exc:
            try:
                os.fstat(closefd_false_reuse_failure_source_fd)
                caller_retained = True
            except OSError:
                caller_retained = False
            replacement_descriptor = reuse_failure_hook_state.get(
                "replacement_descriptor"
            )
            try:
                if type(replacement_descriptor) is not int:
                    raise OSError("replacement descriptor was not created")
                os.fstat(replacement_descriptor)
                replacement_retained = True
                replacement_write_count = os.write(
                    replacement_descriptor,
                    b"replacement-target-control",
                )
                os.fsync(replacement_descriptor)
            except OSError:
                replacement_retained = False
                replacement_write_count = 0
            try:
                caller_write_count = os.write(
                    closefd_false_reuse_failure_source_fd,
                    b"caller-source-control",
                )
                os.fsync(closefd_false_reuse_failure_source_fd)
            except OSError:
                caller_write_count = 0
            cleanup_events = [
                event
                for event in _F12_FD_GUARD_EVENTS[reuse_failure_event_start:]
                if event.get("event") == "fdopen_duplicate_cleanup"
            ]
            reuse_failure_constructor_result = {
                "raised_type_error": True,
                "error_type": type(exc).__name__,
                "caller_descriptor_retained": caller_retained,
                "caller_write_count": caller_write_count,
                "replacement_descriptor_retained": replacement_retained,
                "replacement_write_count": replacement_write_count,
                "replacement_descriptor_number_reused": reuse_failure_hook_state.get(
                    "same_descriptor_number"
                ),
                "original_duplicate_descriptor_number": reuse_failure_hook_state.get(
                    "duplicate_number"
                ),
                "replacement_descriptor_number": replacement_descriptor,
                "duplicate_cleanup_event": cleanup_events[-1]
                if cleanup_events
                else None,
            }
    except Exception as exc:
        reuse_failure_constructor_result = {
            "raised_type_error": False,
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
        }
    finally:
        globals()["_F12_FDOPEN_DUPLICATE_FAILURE_HOOK"] = previous_failure_hook
        if closefd_false_reuse_failure_source_fd is not None:
            try:
                os.close(closefd_false_reuse_failure_source_fd)
            except OSError:
                pass
        replacement_descriptor = reuse_failure_hook_state.get("replacement_descriptor")
        if type(replacement_descriptor) is int:
            try:
                os.close(replacement_descriptor)
            except OSError:
                pass
    reuse_failure_event_window = seal_fd_guard_event_window(
        "closefd_false_reused_duplicate_cleanup_failure",
        reuse_failure_event_start,
        closefd_false_reuse_failure_source_fd,
    )
    reuse_failure_window_cleanup_events = [
        event
        for event in reuse_failure_event_window["events"]
        if event.get("event") == "fdopen_duplicate_cleanup"
    ]
    reuse_failure_constructor_result["duplicate_cleanup_event"] = (
        reuse_failure_window_cleanup_events[-1]
        if reuse_failure_window_cleanup_events
        else None
    )

    external_result: dict[str, Any]
    try:
        with os.fdopen(external_fd, "wb") as stream:
            stream.write(b"must remain empty\n")
        external_result = {"accepted": True, "error_type": None}
    except Exception as exc:
        external_result = {"accepted": False, "error_type": type(exc).__name__}
        try:
            os.close(external_fd)
        except OSError:
            pass

    external_closefd_false_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        external_closefd_false_stream = os.fdopen(
            external_closefd_false_fd,
            "wb",
            closefd=False,
        )
    except Exception as exc:
        try:
            os.fstat(external_closefd_false_fd)
            external_closefd_false_caller_retained = True
        except OSError:
            external_closefd_false_caller_retained = False
        external_closefd_false_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
            "caller_descriptor_retained": external_closefd_false_caller_retained,
        }
    else:
        external_closefd_false_stream.close()
        try:
            os.fstat(external_closefd_false_fd)
            external_closefd_false_caller_retained = True
        except OSError:
            external_closefd_false_caller_retained = False
        external_closefd_false_result = {
            "accepted": True,
            "error_type": None,
            "caller_descriptor_retained": external_closefd_false_caller_retained,
        }
    finally:
        try:
            os.close(external_closefd_false_fd)
        except OSError:
            pass
    external_closefd_false_event_window = seal_fd_guard_event_window(
        "external_closefd_false_rejection",
        external_closefd_false_event_start,
        external_closefd_false_fd,
    )

    hardlink_handle_result: dict[str, Any]
    try:
        with os.fdopen(hardlink_pre_guard_fd, "wb") as stream:
            stream.write(b"must be blocked through external hardlink")
        hardlink_handle_result = {"accepted": True, "error_type": None}
    except Exception as exc:
        hardlink_handle_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
        }
    finally:
        try:
            os.close(hardlink_pre_guard_fd)
        except OSError:
            pass

    hardlink_closefd_false_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        hardlink_closefd_false_stream = os.fdopen(
            hardlink_closefd_false_fd,
            "wb",
            closefd=False,
        )
    except Exception as exc:
        try:
            os.fstat(hardlink_closefd_false_fd)
            hardlink_closefd_false_caller_retained = True
        except OSError:
            hardlink_closefd_false_caller_retained = False
        hardlink_closefd_false_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
            "caller_descriptor_retained": hardlink_closefd_false_caller_retained,
        }
    else:
        hardlink_closefd_false_stream.close()
        try:
            os.fstat(hardlink_closefd_false_fd)
            hardlink_closefd_false_caller_retained = True
        except OSError:
            hardlink_closefd_false_caller_retained = False
        hardlink_closefd_false_result = {
            "accepted": True,
            "error_type": None,
            "caller_descriptor_retained": hardlink_closefd_false_caller_retained,
        }
    finally:
        try:
            os.close(hardlink_closefd_false_fd)
        except OSError:
            pass
    hardlink_closefd_false_event_window = seal_fd_guard_event_window(
        "hardlink_closefd_false_rejection",
        hardlink_closefd_false_event_start,
        hardlink_closefd_false_fd,
    )

    hardlink_open_result: dict[str, Any]
    try:
        hardlink_open_fd = os.open(
            hardlink_alias_path,
            os.O_WRONLY | os.O_TRUNC,
        )
        os.close(hardlink_open_fd)
        hardlink_open_result = {"accepted": True, "error_type": None}
    except Exception as exc:
        hardlink_open_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
        }
    hardlink_sha_after_os_trunc_attempt = _sha256_file(hardlink_source_path)

    hardlink_builtin_open_result: dict[str, Any]
    try:
        with open(hardlink_alias_path, "wb") as stream:
            stream.write(b"must be blocked before builtin open truncates")
        hardlink_builtin_open_result = {"accepted": True, "error_type": None}
    except Exception as exc:
        hardlink_builtin_open_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
        }
    hardlink_sha_after_builtin_trunc_attempt = _sha256_file(hardlink_source_path)

    reparse_target_dir = run_root / "personal-data" / "junction-target"
    reparse_alias_dir = run_root / "personal-data" / "junction-alias"
    reparse_target_path = reparse_target_dir / "private-junction-target.bin"
    reparse_target_dir.mkdir(parents=True, exist_ok=False)
    reparse_target_fd = os.open(
        reparse_target_path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    with os.fdopen(reparse_target_fd, "wb") as stream:
        stream.write(b"private junction target must remain unchanged\n")
    reparse_target_sha_before = _sha256_file(reparse_target_path)
    command_interpreter = os.environ.get("COMSPEC") or str(
        Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    )
    command_repo_root = Path(__file__).resolve().parents[1]
    cmd_unsafe_characters = set(' \t"&|<>^%!()')
    junction_alias_absent_before = not os.path.lexists(reparse_alias_dir)
    cmd_paths_are_safe = all(
        not any(character in str(path) for character in cmd_unsafe_characters)
        for path in (reparse_alias_dir, reparse_target_dir)
    )

    def run_junction_command(operation: str) -> dict[str, Any]:
        if not Path(command_interpreter).is_file():
            raise FileNotFoundError("Windows command interpreter is unavailable")
        if not cmd_paths_are_safe:
            raise PermissionError("junction paths contain unsafe cmd metacharacters")
        if operation == "create":
            if not junction_alias_absent_before:
                raise FileExistsError(
                    "junction alias path already exists before this probe"
                )
            command_text = f"mklink /J {reparse_alias_dir} {reparse_target_dir}"
        elif operation == "remove":
            if not junction_alias_created_by_probe:
                raise PermissionError(
                    "refusing to remove an alias not created by this probe"
                )
            current_details = reparse_alias_dir.lstat()
            current_attributes = int(
                getattr(current_details, "st_file_attributes", 0)
            )
            current_reparse_flag = int(
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )
            if not current_attributes & current_reparse_flag:
                raise PermissionError("junction alias lost its reparse attribute")
            if reparse_alias_dir.resolve(strict=True) != reparse_target_dir.resolve(
                strict=True
            ):
                raise PermissionError("junction alias no longer resolves to its target")
            command_text = f"rmdir {reparse_alias_dir}"
        else:
            raise ValueError("unsupported private junction operation")
        return _run_owned_logged_child(
            [command_interpreter, "/d", "/c", command_text],
            cwd=command_repo_root,
            env=dict(os.environ),
            log_path=qa_root / f"private-junction-{operation}.log",
            timeout=30.0,
        )

    junction_create_job: dict[str, Any] | None = None
    try:
        junction_create_job = run_junction_command("create")
        junction_create_error: dict[str, Any] | None = None
    except Exception as exc:
        junction_create_error = {
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
        }
    reparse_creation: dict[str, Any] = {
        "created": bool(
            junction_create_job is not None
            and junction_create_job["return_code"] == 0
            and junction_create_job["completed_before_deadline"] is True
            and junction_create_job["active_process_count_at_exit_or_deadline"] == 0
            and junction_create_job["process_tree_closed"] is True
            and junction_create_job["root_process_handles_closed"] is True
            and junction_create_job["remaining_pids_after_close"] == []
        ),
        "error": junction_create_error,
        "job": junction_create_job,
    }
    junction_is_reparse_point = False
    junction_resolves_to_target = False
    junction_inspection_error: dict[str, Any] | None = None
    if os.path.lexists(reparse_alias_dir):
        try:
            junction_details = reparse_alias_dir.lstat()
            junction_attributes = int(
                getattr(junction_details, "st_file_attributes", 0)
            )
            junction_reparse_flag = int(
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            )
            junction_is_reparse_point = bool(
                junction_attributes & junction_reparse_flag
            )
            junction_resolves_to_target = (
                reparse_alias_dir.resolve(strict=True)
                == reparse_target_dir.resolve(strict=True)
            )
        except Exception as exc:
            junction_inspection_error = {
                "error_type": type(exc).__name__,
                "errno": getattr(exc, "errno", None),
                "winerror": getattr(exc, "winerror", None),
            }

    reparse_open_result: dict[str, Any]
    if junction_is_reparse_point and junction_resolves_to_target:
        try:
            reparse_fd = os.open(
                reparse_alias_dir / reparse_target_path.name,
                os.O_WRONLY | os.O_TRUNC,
            )
            os.close(reparse_fd)
            reparse_open_result = {"accepted": True, "error_type": None}
        except Exception as exc:
            reparse_open_result = {
                "accepted": False,
                "error_type": type(exc).__name__,
                "errno": getattr(exc, "errno", None),
                "winerror": getattr(exc, "winerror", None),
            }
    else:
        reparse_open_result = {
            "accepted": False,
            "error_type": "not_attempted_junction_unavailable",
        }

    extended_private_path = (
        private_path.parent / "extended-prefix-private-writer.bin"
    )
    extended_private_result = attempt_extended_os_open(
        "private_run_root",
        extended_dos_path(extended_private_path),
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
        payload=b"extended DOS private write allowed\n",
    )
    extended_private_bytes_exact = (
        extended_private_path.read_bytes() == b"extended DOS private write allowed\n"
        if extended_private_path.is_file()
        else False
    )

    external_sha_before_extended = _sha256_file(external_path)
    extended_external_result = attempt_extended_os_open(
        "outside_private_roots",
        extended_dos_path(external_path),
        os.O_WRONLY,
    )
    external_sha_after_extended = _sha256_file(external_path)

    extended_private_sha_before_alias_attempt = _sha256_file(
        extended_private_path
    )
    extended_lexical_alias = (
        extended_dos_path(run_root)
        + "\\personal-data\\..\\personal-data\\extended-prefix-private-writer.bin"
    )
    extended_lexical_alias_result = attempt_extended_os_open(
        "lexical_dot_segment_alias",
        extended_lexical_alias,
        os.O_WRONLY,
    )
    extended_private_sha_after_alias_attempt = (
        _sha256_file(extended_private_path)
        if extended_private_path.is_file()
        else None
    )

    hardlink_source_sha_before_extended = _sha256_file(hardlink_source_path)
    hardlink_alias_sha_before_extended = _sha256_file(hardlink_alias_path)
    extended_hardlink_result = attempt_extended_os_open(
        "external_hardlink_alias",
        extended_dos_path(hardlink_alias_path),
        os.O_WRONLY | os.O_TRUNC,
    )
    hardlink_source_sha_after_extended = _sha256_file(hardlink_source_path)
    hardlink_alias_sha_after_extended = _sha256_file(hardlink_alias_path)

    source_root = Path(os.environ["F12_SYNTHETIC_ROOT"])
    readonly_source_path = source_root / "monthly-source-reference.json"
    readonly_source_sha_before_extended = _sha256_file(readonly_source_path)
    extended_readonly_source_result = attempt_extended_os_open(
        "approved_synthetic_read_only_source",
        extended_dos_path(readonly_source_path),
        os.O_WRONLY,
    )
    readonly_source_sha_after_extended = _sha256_file(readonly_source_path)

    extended_bad_unc_result = attempt_extended_os_open(
        "unc_namespace",
        "\\\\?\\UNC\\f12-invalid-host\\blocked-share\\probe.bin",
        os.O_WRONLY,
    )
    extended_unsupported_namespace_result = attempt_extended_os_open(
        "unsupported_extended_namespace",
        "\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy1\\f12-probe.bin",
        os.O_WRONLY,
    )

    if junction_is_reparse_point and junction_resolves_to_target:
        extended_reparse_result = attempt_extended_os_open(
            "private_junction_alias",
            extended_dos_path(reparse_alias_dir / reparse_target_path.name),
            os.O_WRONLY | os.O_TRUNC,
        )
    else:
        extended_reparse_result = {
            "case": "private_junction_alias",
            "accepted": False,
            "error_type": "not_attempted_junction_unavailable",
            "errno": None,
            "winerror": None,
            "guard_events": [],
        }
    reparse_target_sha_after_extended_attempt = (
        _sha256_file(reparse_target_path) if reparse_target_path.is_file() else None
    )

    def extended_path_rejected_before_open(
        result: dict[str, Any],
        expected_reason: str,
    ) -> bool:
        return (
            result.get("accepted") is False
            and result.get("error_type") == "PermissionError"
            and result.get("errno") == 13
            and expected_reason
            in {
                event.get("reason")
                for event in result.get("guard_events", [])
            }
        )

    extended_path_matrix = {
        "private_run_root": extended_private_result,
        "outside_private_roots": extended_external_result,
        "lexical_dot_segment_alias": extended_lexical_alias_result,
        "private_junction_alias": extended_reparse_result,
        "external_hardlink_alias": extended_hardlink_result,
        "approved_synthetic_read_only_source": extended_readonly_source_result,
        "unc_namespace": extended_bad_unc_result,
        "unsupported_extended_namespace": extended_unsupported_namespace_result,
        "private_payload_exact": extended_private_bytes_exact,
        "outside_file_sha_unchanged": (
            external_sha_before_extended == external_sha_after_extended
        ),
        "private_target_sha_unchanged_after_alias_attempt": (
            extended_private_sha_before_alias_attempt
            == extended_private_sha_after_alias_attempt
            if extended_private_path.is_file()
            else False
        ),
        "hardlink_source_sha_unchanged": (
            hardlink_source_sha_before_extended
            == hardlink_source_sha_after_extended
        ),
        "hardlink_alias_sha_unchanged": (
            hardlink_alias_sha_before_extended
            == hardlink_alias_sha_after_extended
        ),
        "read_only_source_sha_unchanged": (
            readonly_source_sha_before_extended
            == readonly_source_sha_after_extended
        ),
        "junction_target_sha_unchanged": (
            reparse_target_sha_after_extended_attempt == reparse_target_sha_before
        ),
    }
    junction_alias_created_by_probe = bool(
        reparse_creation["created"] is True
        and junction_alias_absent_before
        and junction_is_reparse_point
        and junction_resolves_to_target
    )
    reparse_target_sha_after_attempt = (
        _sha256_file(reparse_target_path) if reparse_target_path.is_file() else None
    )

    junction_cleanup_job: dict[str, Any] | None = None
    junction_cleanup_error: dict[str, Any] | None = None
    if junction_alias_created_by_probe:
        try:
            junction_cleanup_job = run_junction_command("remove")
        except Exception as exc:
            junction_cleanup_error = {
                "error_type": type(exc).__name__,
                "errno": getattr(exc, "errno", None),
                "winerror": getattr(exc, "winerror", None),
            }
    junction_alias_inspection_error: dict[str, Any] | None = None
    try:
        junction_alias_removed = not os.path.lexists(reparse_alias_dir)
    except OSError as exc:
        junction_alias_removed = False
        junction_alias_inspection_error = {
            "error_type": type(exc).__name__,
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
        }
    reparse_target_sha_after_cleanup = (
        _sha256_file(reparse_target_path) if reparse_target_path.is_file() else None
    )
    reparse_target_unchanged = (
        reparse_target_sha_before is not None
        and reparse_target_sha_after_attempt == reparse_target_sha_before
        and reparse_target_path.is_file()
        and reparse_target_sha_after_cleanup == reparse_target_sha_before
        and _sha256_file(reparse_target_path) == reparse_target_sha_before
    )

    source_root = Path(os.environ["F12_SYNTHETIC_ROOT"])
    source_path = source_root / "monthly-source-reference.json"
    source_before = _sha256_file(source_path)
    source_closefd_false_fd = os.open(source_path, os.O_RDONLY)
    source_closefd_false_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        source_closefd_false_stream = os.fdopen(
            source_closefd_false_fd,
            "wb",
            closefd=False,
        )
    except Exception as exc:
        try:
            os.fstat(source_closefd_false_fd)
            source_closefd_false_caller_retained = True
        except OSError:
            source_closefd_false_caller_retained = False
        source_closefd_false_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
            "caller_descriptor_retained": source_closefd_false_caller_retained,
        }
    else:
        source_closefd_false_stream.close()
        try:
            os.fstat(source_closefd_false_fd)
            source_closefd_false_caller_retained = True
        except OSError:
            source_closefd_false_caller_retained = False
        source_closefd_false_result = {
            "accepted": True,
            "error_type": None,
            "caller_descriptor_retained": source_closefd_false_caller_retained,
        }
    finally:
        try:
            os.close(source_closefd_false_fd)
        except OSError:
            pass
    source_closefd_false_event_window = seal_fd_guard_event_window(
        "read_only_source_closefd_false_rejection",
        source_closefd_false_event_start,
        source_closefd_false_fd,
    )

    source_fd = os.open(source_path, os.O_RDONLY)
    source_readonly_result: dict[str, Any]
    try:
        with os.fdopen(source_fd, "wb") as stream:
            stream.write(b"must be blocked")
        source_readonly_result = {"accepted": True, "error_type": None}
    except Exception as exc:
        source_readonly_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
        }
        try:
            os.close(source_fd)
        except OSError:
            pass

    closed_fd = os.open(
        run_root / "personal-data" / "closed-fd.bin",
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    os.close(closed_fd)
    try:
        os.fdopen(closed_fd, "wb")
    except Exception as exc:
        closed_fd_result = {"accepted": False, "error_type": type(exc).__name__}
    else:
        closed_fd_result = {"accepted": True, "error_type": None}
    closed_fd_closefd_false_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        os.fdopen(closed_fd, "wb", closefd=False)
    except Exception as exc:
        closed_fd_closefd_false_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
        }
    else:
        closed_fd_closefd_false_result = {
            "accepted": True,
            "error_type": None,
        }
    closed_fd_closefd_false_event_window = seal_fd_guard_event_window(
        "closed_descriptor_closefd_false_rejection",
        closed_fd_closefd_false_event_start,
        closed_fd,
    )

    reused_original_fd = os.open(
        run_root / "personal-data" / "reused-fd.bin",
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    os.close(reused_original_fd)
    reused_fd = os.open(source_path, os.O_RDONLY)
    reused_fd_same_number = reused_fd == reused_original_fd
    try:
        os.fdopen(reused_original_fd, "wb")
    except Exception as exc:
        reused_fd_result = {"accepted": False, "error_type": type(exc).__name__}
    else:
        reused_fd_result = {"accepted": True, "error_type": None}
    reused_fd_closefd_false_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        os.fdopen(reused_original_fd, "wb", closefd=False)
    except Exception as exc:
        reused_fd_closefd_false_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
        }
        try:
            os.fstat(reused_fd)
            reused_readonly_fd_retained = True
        except OSError:
            reused_readonly_fd_retained = False
    else:
        reused_fd_closefd_false_result = {
            "accepted": True,
            "error_type": None,
        }
        reused_readonly_fd_retained = not reused_fd_result["accepted"]
    finally:
        try:
            os.close(reused_fd)
        except OSError:
            pass
    reused_fd_closefd_false_event_window = seal_fd_guard_event_window(
        "reused_read_only_descriptor_closefd_false_rejection",
        reused_fd_closefd_false_event_start,
        reused_original_fd,
    )

    read_fd, write_fd = os.pipe()
    try:
        os.fdopen(write_fd, "wb")
    except Exception as exc:
        non_file_result = {"accepted": False, "error_type": type(exc).__name__}
    else:
        non_file_result = {"accepted": True, "error_type": None}
    pipe_closefd_false_event_start = len(_F12_FD_GUARD_EVENTS)
    try:
        os.fdopen(write_fd, "wb", closefd=False)
    except Exception as exc:
        non_file_closefd_false_result = {
            "accepted": False,
            "error_type": type(exc).__name__,
        }
        try:
            os.fstat(write_fd)
            pipe_descriptor_retained = True
        except OSError:
            pipe_descriptor_retained = False
    else:
        non_file_closefd_false_result = {
            "accepted": True,
            "error_type": None,
        }
        pipe_descriptor_retained = False
    finally:
        for descriptor in (read_fd, write_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass
    pipe_closefd_false_event_window = seal_fd_guard_event_window(
        "pipe_descriptor_closefd_false_rejection",
        pipe_closefd_false_event_start,
        write_fd,
    )

    private_writer_bytes_exact = (
        private_path.read_bytes() == b"f12 fdopen descriptor role probe\n"
        if private_path.is_file()
        else False
    )
    source_sha_unchanged = _sha256_file(source_path) == source_before
    hardlink_source_unchanged = (
        _sha256_file(hardlink_source_path) == hardlink_source_sha_before
    )
    hardlink_alias_unchanged = (
        _sha256_file(hardlink_alias_path) == hardlink_alias_sha_before
    )
    fd_guard_event_windows = {
        "closefd_false_private_writer": closefd_false_fdopen_event_window,
        "closefd_false_number_reuse": closefd_false_reuse_event_window,
        "closefd_false_constructor_failure": closefd_false_constructor_event_window,
        "closefd_false_duplicate_closefd_kwargs_failure": duplicate_closefd_event_window,
        "closefd_false_reused_duplicate_cleanup_failure": reuse_failure_event_window,
        "external_closefd_false_rejection": external_closefd_false_event_window,
        "hardlink_closefd_false_rejection": hardlink_closefd_false_event_window,
        "read_only_source_closefd_false_rejection": source_closefd_false_event_window,
        "closed_descriptor_closefd_false_rejection": closed_fd_closefd_false_event_window,
        "reused_read_only_descriptor_closefd_false_rejection": reused_fd_closefd_false_event_window,
        "pipe_descriptor_closefd_false_rejection": pipe_closefd_false_event_window,
    }
    fd_guard_event_window_bindings = {
        "closefd_false_private_writer": closefd_false_fdopen_event_window[
            "descriptor_number"
        ]
        == closefd_false_caller_fd_number
        and type(closefd_false_fdopen_event_window["descriptor_number"]) is int,
        "closefd_false_number_reuse": closefd_false_reuse_event_window[
            "descriptor_number"
        ]
        == closefd_false_reuse_original_descriptor_number
        and type(closefd_false_reuse_event_window["descriptor_number"]) is int,
        "closefd_false_constructor_failure": closefd_false_constructor_event_window[
            "descriptor_number"
        ]
        == closefd_false_constructor_fd,
        "closefd_false_duplicate_closefd_kwargs_failure": duplicate_closefd_event_window[
            "descriptor_number"
        ]
        == duplicate_closefd_fd,
        "closefd_false_reused_duplicate_cleanup_failure": reuse_failure_event_window[
            "descriptor_number"
        ]
        == closefd_false_reuse_failure_source_fd,
        "external_closefd_false_rejection": external_closefd_false_event_window[
            "descriptor_number"
        ]
        == external_closefd_false_fd,
        "hardlink_closefd_false_rejection": hardlink_closefd_false_event_window[
            "descriptor_number"
        ]
        == hardlink_closefd_false_fd,
        "read_only_source_closefd_false_rejection": source_closefd_false_event_window[
            "descriptor_number"
        ]
        == source_closefd_false_fd,
        "closed_descriptor_closefd_false_rejection": closed_fd_closefd_false_event_window[
            "descriptor_number"
        ]
        == closed_fd,
        "reused_read_only_descriptor_closefd_false_rejection": reused_fd_closefd_false_event_window[
            "descriptor_number"
        ]
        == reused_original_fd,
        "pipe_descriptor_closefd_false_rejection": pipe_closefd_false_event_window[
            "descriptor_number"
        ]
        == write_fd,
    }
    authorized_private_event = any(
        event.get("event") == "fdopen_authorized"
        and event.get("path_role") == "manifest_private_write_root"
        and event.get("identity_rechecked") is True
        and event.get("win_identity_verified") is True
        and event.get("handle_link_count") == 1
        and event.get("canonical_path_api")
        == "GetFinalPathNameByHandleW:NORMALIZED|DOS(0)"
        for event in _F12_FD_GUARD_EVENTS
    )
    closefd_false_authorized_event = any(
        event.get("event")
        == "fdopen_authorized_closefd_false_via_owned_duplicate"
        and event.get("path_role") == "manifest_private_write_root"
        and event.get("identity_rechecked") is True
        and event.get("source_and_duplicate_identity_match") is True
        and event.get("win_identity_verified") is True
        and event.get("handle_link_count") == 1
        and event.get("canonical_path_api")
        == "GetFinalPathNameByHandleW:NORMALIZED|DOS(0)"
        and event.get("caller_descriptor_retained") is True
        and event.get("stream_owns_duplicate") is True
        and event.get("caller_descriptor")
        == closefd_false_result.get("caller_descriptor_number")
        and event.get("stream_descriptor")
        == closefd_false_result.get("stream_descriptor_number")
        and event.get("stream_descriptor") != event.get("caller_descriptor")
        for event in closefd_false_fdopen_event_window["events"]
    )
    caller_close_removed_tracking_event = any(
        event.get("event") == "descriptor_closed_via_os_close"
        and event.get("descriptor_number")
        == closefd_false_result.get("caller_descriptor_number")
        and event.get("path_role") == "manifest_private_write_root"
        and event.get("os_close_succeeded") is True
        and event.get("tracking_removed") is True
        for event in closefd_false_fdopen_event_window["events"]
    )
    external_closefd_false_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "untracked_or_pre_guard_descriptor"
        and event.get("path_role") == "outside_manifest_roots"
        for event in external_closefd_false_event_window["events"]
    )
    hardlink_closefd_false_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "hardlinked_file_handle"
        and event.get("path_role") == "manifest_private_write_root"
        for event in hardlink_closefd_false_event_window["events"]
    )
    source_closefd_false_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "descriptor_not_opened_for_write"
        and event.get("path_role") == "manifest_read_only_source_root"
        for event in source_closefd_false_event_window["events"]
    )
    closed_closefd_false_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "closed_or_invalid_descriptor"
        for event in closed_fd_closefd_false_event_window["events"]
    )
    reused_closefd_false_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "descriptor_not_opened_for_write"
        and event.get("path_role") == "manifest_read_only_source_root"
        for event in reused_fd_closefd_false_event_window["events"]
    )
    pipe_closefd_false_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "non_regular_file_handle"
        for event in pipe_closefd_false_event_window["events"]
    )
    constructor_cleanup_event = closefd_false_constructor_result.get(
        "duplicate_cleanup_event"
    )
    duplicate_closefd_cleanup_event = duplicate_closefd_result.get(
        "duplicate_cleanup_event"
    )
    constructor_failure_event = closefd_false_constructor_result.get(
        "native_constructor_failure_event"
    )
    duplicate_closefd_failure_event = duplicate_closefd_result.get(
        "native_constructor_failure_event"
    )
    reuse_failure_cleanup_event = reuse_failure_constructor_result.get(
        "duplicate_cleanup_event"
    )
    guarded_descriptor_records_at_exit = _f12_guarded_descriptor_record_count()
    external_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("path_role") == "outside_manifest_roots"
        for event in _F12_FD_GUARD_EVENTS
    )
    readonly_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("path_role") == "manifest_read_only_source_root"
        for event in _F12_FD_GUARD_EVENTS
    )
    closed_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "closed_or_invalid_descriptor"
        for event in _F12_FD_GUARD_EVENTS
    )
    pipe_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "non_regular_file_handle"
        for event in _F12_FD_GUARD_EVENTS
    )
    hardlink_rejection_event = any(
        event.get("event") == "write_path_rejected"
        and event.get("reason") == "hardlinked_file_path"
        and event.get("path_role") == "manifest_private_write_root"
        for event in _F12_FD_GUARD_EVENTS
    )
    extended_private_identity_event = any(
        event.get("event") == "os_open_registered"
        and event.get("path_role") == "manifest_private_write_root"
        and event.get("write_capable") is True
        and event.get("regular_file") is True
        and event.get("win_identity_verified") is True
        and event.get("handle_link_count") == 1
        and event.get("canonical_path_api")
        == "GetFinalPathNameByHandleW:NORMALIZED|DOS(0)"
        for event in extended_private_result["guard_events"]
    )
    hardlink_handle_rejection_event = any(
        event.get("event") == "fdopen_rejected"
        and event.get("reason") == "hardlinked_file_handle"
        and event.get("path_role") == "manifest_private_write_root"
        for event in _F12_FD_GUARD_EVENTS
    )
    reparse_rejection_event = any(
        event.get("event") == "write_path_rejected"
        and event.get("reason") == "reparse_point_in_private_path_chain"
        for event in _F12_FD_GUARD_EVENTS
    )
    assertions = {
        "private_writer_accepted": private_result["accepted"] is True,
        "private_writer_bytes_exact": private_writer_bytes_exact,
        "private_writer_regular_file": (
            private_path.is_file()
            and stat.S_ISREG(private_path.stat().st_mode)
        ),
        "extended_dos_private_writer_allowed_with_exact_handle_checks": (
            extended_private_result.get("accepted") is True
            and extended_private_result.get("close_error_type") is None
            and extended_path_matrix["private_payload_exact"] is True
            and extended_private_identity_event
            and extended_path_matrix["private_target_sha_unchanged_after_alias_attempt"]
            is True
        ),
        "extended_dos_outside_target_rejected": extended_path_rejected_before_open(
            extended_external_result,
            "outside_allowed_private_root",
        )
        and extended_path_matrix["outside_file_sha_unchanged"],
        "extended_dos_lexical_alias_rejected": extended_path_rejected_before_open(
            extended_lexical_alias_result,
            "path_traversal_segment",
        ),
        "extended_dos_reparse_alias_rejected": extended_path_rejected_before_open(
            extended_reparse_result,
            "reparse_point_in_private_path_chain",
        )
        and extended_path_matrix["junction_target_sha_unchanged"],
        "extended_dos_hardlink_rejected_before_truncate": extended_path_rejected_before_open(
            extended_hardlink_result,
            "hardlinked_file_path",
        )
        and extended_path_matrix["hardlink_source_sha_unchanged"]
        and extended_path_matrix["hardlink_alias_sha_unchanged"],
        "extended_dos_read_only_source_rejected": extended_path_rejected_before_open(
            extended_readonly_source_result,
            "outside_allowed_private_root",
        )
        and any(
            event.get("target_scope") == "synthetic_read_only_source_root"
            for event in extended_readonly_source_result["guard_events"]
        )
        and extended_path_matrix["read_only_source_sha_unchanged"],
        "extended_dos_bad_unc_rejected_before_os_lookup": (
            extended_path_rejected_before_open(
                extended_bad_unc_result,
                "unc_write_path_rejected",
            )
            and extended_bad_unc_result.get("winerror") is None
            and any(
                event.get("target_scope") == "external_unc_or_device_path"
                for event in extended_bad_unc_result["guard_events"]
            )
        ),
        "unknown_extended_namespace_rejected_before_os_lookup": (
            extended_path_rejected_before_open(
                extended_unsupported_namespace_result,
                "unsupported_extended_write_path_namespace",
            )
            and extended_unsupported_namespace_result.get("winerror") is None
        ),
        "extended_dos_probe_keeps_exact_write_roots": (
            {
                Path(item).resolve(strict=False)
                for item in startup_guard_receipt["allowed_write_roots"]
            }
            == {
                qa_root.resolve(strict=False),
                run_root.resolve(strict=False),
            }
        ),
        "extended_dos_external_and_readonly_sources_unchanged": (
            extended_path_matrix["outside_file_sha_unchanged"]
            and extended_path_matrix["read_only_source_sha_unchanged"]
        ),
        "fd_guard_event_windows_are_sealed_and_descriptor_bound": (
            all(fd_guard_event_window_bindings.values())
            and all(
                type(window["descriptor_number"]) is int
                for window in fd_guard_event_windows.values()
            )
            and all(
                window["end_index"] - window["start_index"]
                == len(window["events"])
                for window in fd_guard_event_windows.values()
            )
            and all(
                earlier["end_index"] <= later["start_index"]
                for earlier, later in zip(
                    fd_guard_event_windows.values(),
                    list(fd_guard_event_windows.values())[1:],
                )
            )
        ),
        "private_writer_authorized_with_exact_handle_identity": authorized_private_event,
        "closefd_false_private_writer_uses_owned_duplicate": (
            closefd_false_result.get("accepted") is True
            and closefd_false_result.get("stream_fd_differs_from_caller_fd") is True
            and closefd_false_result.get("stream_closed_before_caller_write") is True
            and closefd_false_result.get("caller_fd_retained_after_stream_close") is True
            and closefd_false_result.get("caller_write_count")
            == len(b"caller-after-stream-close")
            and closefd_false_result.get("bytes_exact") is True
            and closefd_false_authorized_event
            and caller_close_removed_tracking_event
        ),
        "closefd_false_stream_survives_caller_fd_number_reuse": (
            closefd_false_reuse_result.get("accepted") is True
            and closefd_false_reuse_result.get("stream_fd_differs_from_caller_fd")
            is True
            and closefd_false_reuse_result.get("caller_descriptor_number_reused")
            is True
            and closefd_false_reuse_result.get(
                "stream_fd_differs_from_reused_descriptor"
            )
            is True
            and closefd_false_reuse_result.get("stream_closed_after_reuse_write")
            is True
            and closefd_false_reuse_result.get("source_bytes_exact") is True
            and closefd_false_reuse_result.get("reused_target_bytes_exact") is True
        ),
        "closefd_false_constructor_typeerror_closes_only_owned_duplicate": (
            closefd_false_constructor_result.get("raised_native_type_error") is True
            and closefd_false_constructor_result.get("error_type") == "TypeError"
            and closefd_false_constructor_result.get(
                "caller_fd_retained_after_failure"
            )
            is True
            and isinstance(constructor_failure_event, dict)
            and constructor_failure_event.get("path_role")
            == "manifest_private_write_root"
            and constructor_failure_event.get("exception_type") == "TypeError"
            and constructor_failure_event.get("caller_descriptor_retained") is True
            and isinstance(constructor_cleanup_event, dict)
            and constructor_cleanup_event.get("path_role")
            == "manifest_private_write_root"
            and constructor_cleanup_event.get("duplicate_closed") is True
            and constructor_cleanup_event.get("duplicate_tracking_removed") is True
            and constructor_cleanup_event.get("stale_duplicate_record_absent")
            is True
            and constructor_cleanup_event.get(
                "current_descriptor_tracking_preserved"
            )
            is False
            and constructor_cleanup_event.get("caller_descriptor_retained") is True
            and constructor_cleanup_event.get("cleanup_action")
            == "closed_verified_duplicate"
        ),
        "closefd_false_duplicate_closefd_kwargs_fail_and_cleanup": (
            duplicate_closefd_result.get("raised_native_type_error") is True
            and duplicate_closefd_result.get("error_type") == "TypeError"
            and duplicate_closefd_result.get(
                "caller_fd_retained_after_failure"
            )
            is True
            and isinstance(duplicate_closefd_failure_event, dict)
            and duplicate_closefd_failure_event.get("path_role")
            == "manifest_private_write_root"
            and duplicate_closefd_failure_event.get("exception_type")
            == "TypeError"
            and duplicate_closefd_failure_event.get(
                "caller_descriptor_retained"
            )
            is True
            and isinstance(duplicate_closefd_cleanup_event, dict)
            and duplicate_closefd_cleanup_event.get("path_role")
            == "manifest_private_write_root"
            and duplicate_closefd_cleanup_event.get("duplicate_closed") is True
            and duplicate_closefd_cleanup_event.get(
                "duplicate_tracking_removed"
            )
            is True
            and duplicate_closefd_cleanup_event.get(
                "stale_duplicate_record_absent"
            )
            is True
            and duplicate_closefd_cleanup_event.get(
                "current_descriptor_tracking_preserved"
            )
            is False
            and duplicate_closefd_cleanup_event.get("caller_descriptor_retained")
            is True
            and duplicate_closefd_cleanup_event.get("cleanup_action")
            == "closed_verified_duplicate"
        ),
        "closefd_false_cleanup_preserves_reused_descriptor": (
            reuse_failure_constructor_result.get("raised_type_error") is True
            and reuse_failure_constructor_result.get("error_type") == "TypeError"
            and reuse_failure_constructor_result.get("caller_descriptor_retained")
            is True
            and reuse_failure_constructor_result.get("caller_write_count")
            == len(b"caller-source-control")
            and reuse_failure_constructor_result.get(
                "replacement_descriptor_retained"
            )
            is True
            and reuse_failure_constructor_result.get("replacement_write_count")
            == len(b"replacement-target-control")
            and reuse_failure_constructor_result.get(
                "replacement_descriptor_number_reused"
            )
            is True
            and closefd_false_reuse_failure_source_path.read_bytes()
            == b"caller-source-control"
            and closefd_false_reuse_failure_path.read_bytes()
            == b"replacement-target-control"
            and isinstance(reuse_failure_cleanup_event, dict)
            and reuse_failure_cleanup_event.get("path_role")
            == "manifest_private_write_root"
            and reuse_failure_cleanup_event.get("duplicate_closed") is False
            and reuse_failure_cleanup_event.get(
                "duplicate_tracking_removed"
            )
            is False
            and reuse_failure_cleanup_event.get(
                "stale_duplicate_record_absent"
            )
            is True
            and reuse_failure_cleanup_event.get(
                "current_descriptor_tracking_preserved"
            )
            is True
            and reuse_failure_cleanup_event.get("descriptor_number_reused") is True
            and reuse_failure_cleanup_event.get(
                "replacement_descriptor_preserved"
            )
            is True
            and reuse_failure_cleanup_event.get("cleanup_action")
            == "preserved_reused_or_changed_descriptor"
            and reuse_failure_cleanup_event.get("caller_descriptor_retained")
            is True
        ),
        "external_pre_guard_writer_rejected": (
            external_result["accepted"] is False
            and external_result["error_type"] == "PermissionError"
            and external_rejection_event
        ),
        "external_closefd_false_descriptor_rejected_and_retained": (
            external_closefd_false_result.get("accepted") is False
            and external_closefd_false_result.get("error_type") == "PermissionError"
            and external_closefd_false_result.get("caller_descriptor_retained") is True
            and external_closefd_false_rejection_event
        ),
        "external_hardlink_writer_rejected": (
            hardlink_count_before == 2
            and hardlink_handle_result["accepted"] is False
            and hardlink_handle_result["error_type"] == "PermissionError"
            and hardlink_handle_rejection_event
        ),
        "external_hardlink_closefd_false_rejected_and_retained": (
            hardlink_count_before == 2
            and hardlink_closefd_false_result.get("accepted") is False
            and hardlink_closefd_false_result.get("error_type") == "PermissionError"
            and hardlink_closefd_false_result.get("caller_descriptor_retained")
            is True
            and hardlink_closefd_false_rejection_event
        ),
        "external_hardlink_os_truncating_open_rejected_before_open": (
            hardlink_open_result["accepted"] is False
            and hardlink_open_result["error_type"] == "PermissionError"
            and hardlink_rejection_event
        ),
        "external_hardlink_builtin_truncating_open_rejected_before_open": (
            hardlink_builtin_open_result["accepted"] is False
            and hardlink_builtin_open_result["error_type"] == "PermissionError"
            and hardlink_rejection_event
        ),
        "external_hardlink_source_unchanged": hardlink_source_unchanged,
        "external_hardlink_alias_unchanged": hardlink_alias_unchanged,
        "external_hardlink_unchanged_after_os_trunc_attempt": (
            hardlink_sha_after_os_trunc_attempt == hardlink_source_sha_before
        ),
        "external_hardlink_unchanged_after_builtin_trunc_attempt": (
            hardlink_sha_after_builtin_trunc_attempt == hardlink_source_sha_before
        ),
        "private_reparse_creation_succeeded": (
            reparse_creation["created"] is True
            and junction_alias_absent_before
            and junction_is_reparse_point
            and junction_resolves_to_target
        ),
        "private_reparse_target_is_single_link_regular_file": (
            reparse_target_path.is_file()
            and stat.S_ISREG(reparse_target_path.stat().st_mode)
            and int(reparse_target_path.stat().st_nlink) == 1
        ),
        "private_reparse_writer_rejected": (
            reparse_open_result["accepted"] is False
            and reparse_open_result["error_type"] == "PermissionError"
            and reparse_rejection_event
        ),
        "private_reparse_target_unchanged": reparse_target_unchanged,
        "private_reparse_target_unchanged_after_cleanup": (
            reparse_target_sha_before is not None
            and reparse_target_sha_after_cleanup == reparse_target_sha_before
            and reparse_target_path.is_file()
            and _sha256_file(reparse_target_path) == reparse_target_sha_before
        ),
        "private_reparse_alias_removed_without_target_removal": (
            junction_alias_created_by_probe
            and junction_alias_removed
            and junction_cleanup_job is not None
            and junction_cleanup_job["return_code"] == 0
            and junction_cleanup_job["completed_before_deadline"] is True
            and junction_cleanup_job["active_process_count_at_exit_or_deadline"] == 0
            and junction_cleanup_job["process_tree_closed"] is True
            and junction_cleanup_job["root_process_handles_closed"] is True
            and junction_cleanup_job["remaining_pids_after_close"] == []
            and reparse_target_path.is_file()
            and reparse_target_sha_after_cleanup == reparse_target_sha_before
        ),
        "readonly_synthetic_source_writer_rejected": (
            source_readonly_result["accepted"] is False
            and readonly_rejection_event
        ),
        "readonly_synthetic_source_closefd_false_rejected_and_retained": (
            source_closefd_false_result.get("accepted") is False
            and source_closefd_false_result.get("error_type") == "PermissionError"
            and source_closefd_false_result.get("caller_descriptor_retained") is True
            and source_closefd_false_rejection_event
        ),
        "closed_descriptor_rejected": (
            closed_fd_result["accepted"] is False and closed_rejection_event
        ),
        "closed_descriptor_closefd_false_rejected": (
            closed_fd_closefd_false_result.get("accepted") is False
            and closed_fd_closefd_false_result.get("error_type") == "PermissionError"
            and closed_closefd_false_rejection_event
        ),
        "reused_descriptor_number_is_rejected": (
            reused_fd_same_number is True
            and reused_fd_result["accepted"] is False
        ),
        "reused_readonly_descriptor_closefd_false_rejected_and_retained": (
            reused_fd_same_number is True
            and reused_fd_closefd_false_result.get("accepted") is False
            and reused_fd_closefd_false_result.get("error_type") == "PermissionError"
            and reused_readonly_fd_retained is True
            and reused_closefd_false_rejection_event
        ),
        "non_file_pipe_descriptor_rejected": (
            non_file_result["accepted"] is False and pipe_rejection_event
        ),
        "non_file_pipe_closefd_false_rejected_and_retained": (
            non_file_closefd_false_result.get("accepted") is False
            and non_file_closefd_false_result.get("error_type") == "PermissionError"
            and pipe_descriptor_retained is True
            and pipe_closefd_false_rejection_event
        ),
        "synthetic_source_unchanged": source_sha_unchanged,
        "external_file_empty": external_path.stat().st_size == 0,
        "guarded_descriptor_records_empty_at_exit": (
            guarded_descriptor_records_at_exit == 0
        ),
    }

    receipt = {
        "schema": "f12-fdopen-guard-roles.v7",
        "status": (
            "passed_fd_role_guard"
            if all(assertions.values())
            else "failed_fd_role_guard"
        ),
        "assertions": assertions,
        "fd_guard_event_window_bindings": fd_guard_event_window_bindings,
        "fd_guard_event_windows": fd_guard_event_windows,
        "fdopen_event_integer_path_expected": True,
        "guarded_descriptor_records_at_exit_count": (
            guarded_descriptor_records_at_exit
        ),
        "private_writer": private_result,
        "extended_path_matrix": extended_path_matrix,
        "extended_private_identity_event": extended_private_identity_event,
        "closefd_false_private_writer": closefd_false_result,
        "closefd_false_number_reuse": closefd_false_reuse_result,
        "closefd_false_constructor_failure": closefd_false_constructor_result,
        "closefd_false_constructor_failure_event": constructor_failure_event,
        "closefd_false_constructor_cleanup_event": constructor_cleanup_event,
        "closefd_false_duplicate_closefd_failure": duplicate_closefd_result,
        "closefd_false_duplicate_closefd_failure_event": (
            duplicate_closefd_failure_event
        ),
        "closefd_false_duplicate_closefd_cleanup_event": (
            duplicate_closefd_cleanup_event
        ),
        "closefd_false_reuse_failure": reuse_failure_constructor_result,
        "closefd_false_reuse_failure_cleanup_event": reuse_failure_cleanup_event,
        "external_pre_guard_writer": external_result,
        "external_closefd_false_writer": external_closefd_false_result,
        "external_hardlink_alias": {
            "path_role": "private_alias_to_external_qa_file",
            "link_count_before": hardlink_count_before,
            "pre_guard_handle_rejected": not hardlink_handle_result["accepted"],
            "pre_guard_handle_result": hardlink_handle_result,
            "closefd_false_pre_guard_handle_result": hardlink_closefd_false_result,
            "os_truncating_open_rejected": not hardlink_open_result["accepted"],
            "os_truncating_open_result": hardlink_open_result,
            "builtin_truncating_open_rejected": not hardlink_builtin_open_result["accepted"],
            "builtin_truncating_open_result": hardlink_builtin_open_result,
            "source_sha256_unchanged": hardlink_source_unchanged,
            "alias_sha256_unchanged": hardlink_alias_unchanged,
            "source_sha_after_os_trunc_attempt": hardlink_sha_after_os_trunc_attempt,
            "source_sha_after_builtin_trunc_attempt": hardlink_sha_after_builtin_trunc_attempt,
        },
        "private_reparse_alias": {
            **reparse_creation,
            "junction_detected": junction_is_reparse_point,
            "resolved_target_matches": junction_resolves_to_target,
            "alias_absent_before_probe": junction_alias_absent_before,
            "alias_created_by_probe": junction_alias_created_by_probe,
            "inspection_error": junction_inspection_error,
            "paths": {
                "alias_directory": str(reparse_alias_dir),
                "target_directory": str(reparse_target_dir),
                "target_file": str(reparse_target_path),
            },
            "open_rejected": not reparse_open_result["accepted"],
            **reparse_open_result,
            "target_sha256_unchanged": reparse_target_unchanged,
            "target_sha256_before": reparse_target_sha_before,
            "target_sha256_after_attempt": reparse_target_sha_after_attempt,
            "target_sha256_after_cleanup": reparse_target_sha_after_cleanup,
            "cleanup_job": junction_cleanup_job,
            "cleanup_error": junction_cleanup_error,
            "alias_removed": junction_alias_removed,
            "alias_inspection_error": junction_alias_inspection_error,
        },
        "read_only_synthetic_source_as_writer": source_readonly_result,
        "read_only_synthetic_source_closefd_false_writer": (
            source_closefd_false_result
        ),
        "closed_descriptor": closed_fd_result,
        "closed_descriptor_closefd_false": closed_fd_closefd_false_result,
        "descriptor_reuse": {
            "same_descriptor_number": reused_fd_same_number,
            **reused_fd_result,
            "closefd_false_result": reused_fd_closefd_false_result,
            "read_only_descriptor_retained": reused_readonly_fd_retained,
        },
        "non_file_pipe_descriptor": non_file_result,
        "non_file_pipe_closefd_false": {
            **non_file_closefd_false_result,
            "descriptor_retained_after_rejection": pipe_descriptor_retained,
        },
        "source_sha256_unchanged": source_sha_unchanged,
        "private_writer_bytes_sha256": (
            _sha256_file(private_path) if private_path.is_file() else None
        ),
        "private_writer_bytes_exact": private_writer_bytes_exact,
        "closefd_false_private_writer_sha256": (
            _sha256_file(closefd_false_path)
            if closefd_false_path.is_file()
            else None
        ),
        "closefd_false_reuse_source_sha256": (
            _sha256_file(closefd_false_reuse_source_path)
            if closefd_false_reuse_source_path.is_file()
            else None
        ),
        "closefd_false_reuse_target_sha256": (
            _sha256_file(closefd_false_reuse_target_path)
            if closefd_false_reuse_target_path.is_file()
            else None
        ),
        "external_file_empty": external_path.stat().st_size == 0,
        "fd_guard_events": list(_F12_FD_GUARD_EVENTS),
        "stat_mode_regular_file": stat.S_ISREG(private_path.stat().st_mode)
        if private_path.exists()
        else False,
    }
    _write_json_create_only(qa_root / "fdopen-guard-role-receipt.json", receipt)
    assert all(assertions.values()), receipt


def test_watchlist_view_upgrade_click_reports_private_storage_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """以真 WatchlistView click 查出私人 JSON COW 啟用結果。"""

    if os.environ.get("F12_WATCHLIST_VIEW_PROBE") != "1":
        _supervise_watchlist_view_upgrade_probe()
        return

    run_root = Path(os.environ["F12_MAIN_RUN_ROOT"])
    qa_root = Path(os.environ["F12_MAIN_QA_ROOT"])
    environment = _main_window_environment(run_root, qa_root=qa_root)
    for name in F12_UNSET_STARTUP_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    for name in F12_EMPTY_STARTUP_ENVIRONMENT:
        monkeypatch.setenv(name, "")
    _validate_and_install_startup_write_guard()

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox

    from data_module import watchlist_json_cow
    from ui_qt.views.watchlist_view import WatchlistView

    config = TWStockConfig()
    source_path = Path(os.environ["PERSONAL_WATCHLIST_SOURCE"])
    expected_source = run_root / "application-output" / "_test" / "watchlist" / "default.json"
    expected_output = run_root / "application-output" / "_test"
    assert config.profile == "test"
    assert config.output_root.resolve() == expected_output.resolve()
    assert Path(config.personal_watchlist_source).resolve() == expected_source.resolve()
    assert source_path.resolve() == expected_source.resolve()

    service = PersonalWatchlistService(config)
    assert service.control_paths.source_path.resolve() == expected_source.resolve()
    source_sha_before = _sha256_file(source_path)
    observed_operations = _install_watchlist_upgrade_observers(
        service,
        monkeypatch,
        run_root=run_root,
        qa_root=qa_root,
    )
    cow_preflight_causes: list[dict[str, Any]] = []
    original_normalize_paths = watchlist_json_cow._normalize_paths
    target = service.canonical_repository_path
    scope_roles = {
        "legacy_source_file": service.control_paths.source_path,
        "legacy_source_directory": service.control_paths.source_path.parent,
        "private_sqlite_target": target,
        "cow_activation_marker": service.control_paths.marker_path,
        "cow_conversion_receipt": service.control_paths.receipt_path,
        "legacy_source_backup": service.control_paths.source_backup_path,
        "personal_root": service.personal_paths.personal_root,
    }

    def observe_cow_preflight(*args: object, **kwargs: object):
        try:
            return original_normalize_paths(*args, **kwargs)
        except Exception as exc:
            cause = exc.__cause__
            cause_record: dict[str, Any] = {
                "exception_type": type(exc).__name__,
                "error_code": str(getattr(exc, "code", "")) or None,
                "cause_type": type(cause).__name__ if cause is not None else None,
                "errno": getattr(cause, "errno", None),
                "winerror": getattr(cause, "winerror", None),
                "cause_message": _redact_watchlist_ui_diagnostic(
                    str(cause) if cause is not None else "",
                    private_paths=(run_root, qa_root, source_path, target),
                ),
            }
            cause_record.update(
                _watchlist_path_error_scope(
                    getattr(cause, "filename", None),
                    role_paths=scope_roles,
                    private_roots=(qa_root, run_root),
                    read_only_source_roots=(
                        Path(os.environ["F12_SYNTHETIC_ROOT"]),
                    ),
                )
            )
            secondary_path = getattr(cause, "filename2", None)
            if secondary_path is not None:
                cause_record["secondary_path_scope"] = _watchlist_path_error_scope(
                    secondary_path,
                    role_paths=scope_roles,
                    private_roots=(qa_root, run_root),
                    read_only_source_roots=(
                        Path(os.environ["F12_SYNTHETIC_ROOT"]),
                    ),
                )
            cow_preflight_causes.append(cause_record)
            raise

    monkeypatch.setattr(watchlist_json_cow, "_normalize_paths", observe_cow_preflight)
    app = QApplication.instance() or QApplication(["f12-watchlist-view-upgrade-probe"])
    view = WatchlistView(watchlist_service=service, config=config)
    try:
        view.resize(1280, 800)
        view.show()
        app.processEvents()

        button = view.upgrade_storage_btn
        initial = {
            "view_visible": bool(view.isVisible()),
            "button_visible": bool(button.isVisible()),
            "button_enabled": bool(button.isEnabled()),
            "button_geometry": _watchlist_widget_geometry(button),
        }
        click_signals: list[bool] = []
        confirmation_calls: list[bool] = []
        modal_counts = {"question": 0, "information": 0, "warning": 0}
        button.clicked.connect(lambda *_args: click_signals.append(True))

        def answer_yes(*_args: object, **_kwargs: object):
            confirmation_calls.append(True)
            modal_counts["question"] += 1
            return QMessageBox.StandardButton.Yes

        def record_information(*_args: object, **_kwargs: object):
            modal_counts["information"] += 1
            return QMessageBox.StandardButton.NoButton

        def record_warning(*_args: object, **_kwargs: object):
            modal_counts["warning"] += 1
            return QMessageBox.StandardButton.NoButton

        monkeypatch.setattr(QMessageBox, "question", answer_yes)
        monkeypatch.setattr(QMessageBox, "information", record_information)
        monkeypatch.setattr(QMessageBox, "warning", record_warning)
        started_wall_ns = time.time_ns()
        started_monotonic_ns = time.monotonic_ns()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        ended_monotonic_ns = time.monotonic_ns()
        ended_wall_ns = time.time_ns()

        status = service.get_storage_status()
        target_exists = target.is_file()
        target_inside_private_root = _path_is_within(target, run_root)
        target_format = (
            WatchlistRepository(target).detect_storage_format()
            if target_exists
            else {"schema_version": None, "ready": False}
        )
        reader_query_only = False
        reader_write_blocked = False
        if target_exists and target_format.get("ready") is True:
            connection = WatchlistRepository(target)._open_read_only()
            try:
                reader_query_only = (
                    connection.execute("PRAGMA query_only").fetchone() == (1,)
                )
                try:
                    connection.execute(
                        "UPDATE watchlists SET payload_json=payload_json WHERE 1=0"
                    )
                except sqlite3.OperationalError as exc:
                    reader_write_blocked = "readonly" in str(exc).casefold()
            finally:
                connection.close()

        active_read_ok = False
        active_read_error = ""
        repository_active = bool(status.is_repository)
        if repository_active:
            try:
                active_read_ok = service.get_stock_codes() == []
            except Exception as exc:
                active_read_error = str(exc).splitlines()[0]

        private_paths = (run_root, qa_root, source_path, target)
        ui_receipt = {
            "schema": "f12-watchlist-view-upgrade-ui.v2",
            "status": "repository_active" if repository_active else "activation_failed",
            "clock": {
                "started_wall_ns": started_wall_ns,
                "ended_wall_ns": ended_wall_ns,
                "started_monotonic_ns": started_monotonic_ns,
                "ended_monotonic_ns": ended_monotonic_ns,
                "elapsed_ns": max(0, ended_monotonic_ns - started_monotonic_ns),
            },
            "initial": initial,
            "final": {
                "view_visible": bool(view.isVisible()),
                "button_visible": bool(button.isVisible()),
                "button_enabled": bool(button.isEnabled()),
                "button_geometry": _watchlist_widget_geometry(button),
                "button_click_signal_count": len(click_signals),
                "confirmation_call_count": len(confirmation_calls),
                "modal_counts": modal_counts,
                "modal_fixed_returns": {
                    "question": "Yes",
                    "information": "NoButton",
                    "warning": "NoButton",
                },
                "service_mode": status.mode,
                "service_is_repository": repository_active,
                "service_upgrade_available": bool(status.upgrade_available),
                "status_label": _redact_watchlist_ui_diagnostic(
                    view.status_label.text(), private_paths=private_paths,
                ),
                "storage_status_label": _redact_watchlist_ui_diagnostic(
                    view.storage_status_label.text(), private_paths=private_paths,
                ),
            },
        }
        _write_json_create_only(
            qa_root / "watchlist-upgrade-ui-receipt.json",
            ui_receipt,
        )
        _write_json_create_only(
            qa_root / "watchlist-cow-preflight-diagnostics.json",
            {
                "schema": "f12-watchlist-cow-preflight-diagnostics.v1",
                "causes": cow_preflight_causes,
                "backup_attempts": observed_operations["backup_attempts"],
                "fd_guard_events": list(_F12_FD_GUARD_EVENTS),
            },
        )
        storage_receipt = {
            "schema": "f12-watchlist-cow-storage-validation.v1",
            "source_sha256_unchanged": _sha256_file(source_path) == source_sha_before,
            "private_target_exists": target_exists,
            "private_target_inside_run_root": target_inside_private_root,
            "target_schema_version": target_format.get("schema_version"),
            "target_schema_ready": bool(target_format.get("ready")),
            "reader_sqlite_role": {
                "query_only": reader_query_only,
                "write_blocked": reader_write_blocked,
            },
            "active_service_read_ok": active_read_ok,
            "active_service_read_error": _redact_watchlist_ui_diagnostic(
                active_read_error, private_paths=private_paths,
            ),
        }
        _write_json_create_only(
            qa_root / "watchlist-cow-storage-validation.json",
            storage_receipt,
        )

        assert initial["view_visible"] and initial["button_visible"]
        assert initial["button_enabled"]
        assert len(click_signals) == 1
        assert len(confirmation_calls) == 1
        assert modal_counts["question"] == 1
        _assert_watchlist_upgrade_modal_branch(
            observed_operations["upgrade_outcomes"],
            modal_counts,
        )
        assert repository_active is True, (
            "真 UI click 未啟用私人 repository；已保存 UI、COW 角色與儲存驗證收據："
            f"{ui_receipt['final']!r}; "
            f"upgrade={observed_operations['upgrade_outcomes']!r}; "
            f"backup={observed_operations['backup_attempts']!r}"
        )
        assert target_exists and target_inside_private_root
        assert target_format.get("schema_version") == 3
        assert target_format.get("ready") is True
        assert _sha256_file(source_path) == source_sha_before
        assert reader_query_only and reader_write_blocked
        assert active_read_ok, storage_receipt["active_service_read_error"]
    finally:
        drain_receipt = _close_watchlist_view_and_drain_workers(view, app)
        _write_json_create_only(
            qa_root / "watchlist-worker-drain-receipt.json",
            drain_receipt,
        )
        assert drain_receipt["worker_registry_zero"] is True, (
            "WatchlistView close 後受管 worker 未排空："
            f"{drain_receipt!r}"
        )
        assert drain_receipt["close_error_type"] is None, drain_receipt


def test_normal_main_save_close_and_fresh_process_exact_revenue_journey(
    f12_synthetic_sources: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """由合成來源驗證 Main、COW 收藏、關閉與新 PID exact reopen。"""

    if os.environ.get("F12_MAIN_JOURNEY_WORKER") != "1":
        _supervise_main_journey_worker(f12_synthetic_sources)
        return

    run_root = Path(os.environ["F12_MAIN_RUN_ROOT"])
    qa_root = Path(os.environ["F12_MAIN_QA_ROOT"])
    environment = _main_window_environment(run_root, qa_root=qa_root)
    watchlist_source = Path(environment["PERSONAL_WATCHLIST_SOURCE"])
    for key in F12_UNSET_STARTUP_ENVIRONMENT:
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    _validate_and_install_startup_write_guard()
    (run_root / "temp").mkdir(parents=True, exist_ok=True)
    (run_root / "matplotlib").mkdir(parents=True, exist_ok=True)

    stage_log = Path(os.environ["F12_STAGE_LOG"])
    stack_trace = Path(os.environ["F12_STACK_TRACE"])
    stack_handle = stack_trace.open("x", encoding="utf-8")
    faulthandler.enable(file=stack_handle, all_threads=True)
    initialization_started = time.monotonic()
    _append_stage(stage_log, "initialization_started")
    faulthandler.dump_traceback_later(
        MAIN_INITIALIZATION_DEADLINE_SECONDS,
        repeat=False,
        file=stack_handle,
    )

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QMessageBox

        from app_module.daily_market_technical_official_disposition_revenue_bookmark_v1 import (
            DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1,
        )
        from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
            DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
            SELECTION_REVENUE_YOY_METHOD_ID,
            SELECTION_REVENUE_YOY_METHOD_VERSION,
        )
        from app_module.daily_market_technical_official_disposition_query_v1 import (
            DailyMarketTechnicalOfficialDispositionQueryV1,
        )
        from data_module.daily_market_monthly_revenue_read_session_v1 import (
            DailyMarketMonthlyRevenueSourceReferenceV2,
        )
        from ui_qt.main import MainWindow, apply_app_theme

        _append_stage(stage_log, "imports.after")
        _append_stage(stage_log, "QApplication.before")
        app = QApplication.instance() or QApplication(["f12-main-revenue-journey"])
        _append_stage(stage_log, "QApplication.after")
        _append_stage(stage_log, "theme.before")
        apply_app_theme(app)
        _append_stage(stage_log, "theme.after")
        _append_stage(stage_log, "MainWindow.before")
        window = MainWindow(
            policy_config_path=str(run_root / "policy" / "personal_use_policy.json"),
        )
        initialization_elapsed = time.monotonic() - initialization_started
        _append_stage(
            stage_log,
            "MainWindow.after",
            elapsed_seconds=initialization_elapsed,
        )
        _append_stage(
            stage_log,
            "initialization_complete",
            elapsed_seconds=initialization_elapsed,
        )
    except BaseException as exc:
        _append_stage(stage_log, "initialization_failed", error=repr(exc))
        raise
    finally:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        stack_handle.flush()
        stack_handle.close()

    assert initialization_elapsed <= MAIN_INITIALIZATION_DEADLINE_SECONDS, (
        f"Main initialization took {initialization_elapsed:.3f}s; "
        f"deadline={MAIN_INITIALIZATION_DEADLINE_SECONDS:.3f}s"
    )
    source_sha_before = _sha256_file(watchlist_source)

    window.resize(1420, 1000)
    window.show()
    app.processEvents()
    service = window.watchlist_service
    assert isinstance(service, PersonalWatchlistService)
    observed_operations = _install_watchlist_upgrade_observers(
        service,
        monkeypatch,
        run_root=run_root,
        qa_root=qa_root,
    )
    watchlist = window.watchlist_view
    assert watchlist.watchlist_service is service
    assert service.get_storage_status().is_repository is False
    assert watchlist.upgrade_storage_btn.isEnabled()

    window._select_main_workspace("watchlist")
    app.processEvents()
    assert window.workspace_stack.currentWidget() is window.workspace_widgets["watchlist"]
    assert watchlist.isVisible()
    assert watchlist.upgrade_storage_btn.isVisible()
    assert watchlist.upgrade_storage_btn.isEnabled()

    # 保留真實按鈕訊號與處理器，只固定 modal 回答以便在 headless UI 驗證。
    click_signals: list[bool] = []
    confirmation_calls: list[bool] = []
    modal_counts = {"question": 0, "information": 0, "warning": 0}
    watchlist.upgrade_storage_btn.clicked.connect(
        lambda *_args: click_signals.append(True)
    )

    def answer_yes(*_args: object, **_kwargs: object):
        confirmation_calls.append(True)
        modal_counts["question"] += 1
        return QMessageBox.StandardButton.Yes

    def record_information(*_args: object, **_kwargs: object):
        modal_counts["information"] += 1
        return QMessageBox.StandardButton.NoButton

    def record_warning(*_args: object, **_kwargs: object):
        modal_counts["warning"] += 1
        return QMessageBox.StandardButton.NoButton

    monkeypatch.setattr(
        QMessageBox,
        "question",
        answer_yes,
    )
    monkeypatch.setattr(QMessageBox, "information", record_information)
    monkeypatch.setattr(QMessageBox, "warning", record_warning)
    button_geometry_before = _watchlist_widget_geometry(watchlist.upgrade_storage_btn)
    click_started_wall_ns = time.time_ns()
    click_started_monotonic_ns = time.monotonic_ns()
    QTest.mouseClick(watchlist.upgrade_storage_btn, Qt.MouseButton.LeftButton)
    app.processEvents()
    click_ended_monotonic_ns = time.monotonic_ns()
    click_ended_wall_ns = time.time_ns()
    upgrade_modal_counts = dict(modal_counts)
    activated_status = service.get_storage_status()
    _write_json_create_only(
        qa_root / "watchlist-cow-operation-diagnostics.json",
        {
            "schema": "f12-watchlist-cow-operation-diagnostics.v1",
            "upgrade_outcomes": observed_operations["upgrade_outcomes"],
            "backup_attempts": observed_operations["backup_attempts"],
            "fd_guard_events": list(_F12_FD_GUARD_EVENTS),
        },
    )
    if not activated_status.is_repository:
        private_paths = (
            run_root,
            qa_root,
            watchlist_source,
            service.personal_paths.personal_root,
            service.canonical_repository_path,
        )
        failure_receipt = {
            "schema": "f12-main-watchlist-upgrade-failure.v1",
            "status": activated_status.mode,
            "clock": {
                "started_wall_ns": click_started_wall_ns,
                "ended_wall_ns": click_ended_wall_ns,
                "started_monotonic_ns": click_started_monotonic_ns,
                "ended_monotonic_ns": click_ended_monotonic_ns,
                "elapsed_ns": max(0, click_ended_monotonic_ns - click_started_monotonic_ns),
            },
            "initial": {
                "workspace": "watchlist",
                "view_visible": bool(watchlist.isVisible()),
                "button_visible": bool(watchlist.upgrade_storage_btn.isVisible()),
                "button_enabled": True,
                "button_geometry": button_geometry_before,
            },
            "final": {
                "view_visible": bool(watchlist.isVisible()),
                "button_visible": bool(watchlist.upgrade_storage_btn.isVisible()),
                "button_enabled": bool(watchlist.upgrade_storage_btn.isEnabled()),
                "button_geometry": _watchlist_widget_geometry(
                    watchlist.upgrade_storage_btn
                ),
                "button_click_signal_count": len(click_signals),
                "confirmation_call_count": len(confirmation_calls),
                "modal_counts": upgrade_modal_counts,
                "modal_fixed_returns": {
                    "question": "Yes",
                    "information": "NoButton",
                    "warning": "NoButton",
                },
                "service_mode": activated_status.mode,
                "service_is_repository": bool(activated_status.is_repository),
                "service_upgrade_available": bool(activated_status.upgrade_available),
                "status_label": _redact_watchlist_ui_diagnostic(
                    watchlist.status_label.text(), private_paths=private_paths,
                ),
                "storage_status_label": _redact_watchlist_ui_diagnostic(
                    watchlist.storage_status_label.text(), private_paths=private_paths,
                ),
                "source_sha256_unchanged": _sha256_file(watchlist_source) == source_sha_before,
            },
        }
        _write_json_create_only(
            qa_root / "watchlist-upgrade-ui-failure.json",
            failure_receipt,
        )
    _assert_watchlist_upgrade_modal_branch(
        observed_operations["upgrade_outcomes"],
        upgrade_modal_counts,
    )
    activated = bool(activated_status.is_repository)
    assert activated is True, (
        "真實 watchlist workspace mouse click 未啟用私人儲存；"
        f"failure receipt={qa_root / 'watchlist-upgrade-ui-failure.json'}"
    )
    assert len(click_signals) == 1
    assert len(confirmation_calls) == 1
    private_target = service.canonical_repository_path
    assert private_target.is_file()
    target_sha_after_activation = _sha256_file(private_target)
    assert _sha256_file(watchlist_source) == source_sha_before

    revenue_view = window.technical_official_revenue_research_view
    source_ref = f12_synthetic_sources["monthly_reference"]
    assert type(source_ref) is DailyMarketMonthlyRevenueSourceReferenceV2
    operations_parent = run_root / "revenue-operations"
    operations_parent.mkdir(parents=True, exist_ok=True)
    assert revenue_view.set_bundle_output_root(
        f12_synthetic_sources["bundle"].bundle_root,
    )
    assert revenue_view.set_monthly_reference_path(
        f12_synthetic_sources["monthly_reference_path"],
    )
    assert revenue_view.set_operation_root_parent(operations_parent)
    window._select_main_workspace("recommendation")
    window.recommendation_view.result_source_tabs.setCurrentWidget(revenue_view)
    app.processEvents()

    outcomes: list[tuple[str, bool]] = []
    revenue_view.operationSettled.connect(
        lambda kind, success: outcomes.append((str(kind), bool(success)))
    )
    revenue_view.refresh_catalog_button.click()
    _wait_until(
        app,
        lambda: len(outcomes) >= 1,
        timeout=120,
        label="Main F17 saved-source catalog",
    )
    assert outcomes[-1] == ("盤點保存來源 metadata", True), revenue_view.status_label.text()
    assert revenue_view.catalog_list.count() == 1
    revenue_view.catalog_list.setCurrentRow(0)
    query_guard_event_start = len(_F12_FD_GUARD_EVENTS)
    query_started_wall_ns = time.time_ns()
    query_started_monotonic_ns = time.monotonic_ns()
    query_primary_exception: BaseException | None = None
    query_outcome: tuple[str, bool] | None = None
    try:
        revenue_view.open_candidate_button.click()
        _wait_until(
            app,
            lambda: len(outcomes) >= 2,
            timeout=480,
            label="Main full-N revenue query",
        )
        query_outcome = outcomes[-1] if outcomes else None
        assert query_outcome == ("核驗雙來源並執行全母體查詢", True), (
            revenue_view.status_label.text()
        )
    except BaseException as exc:
        query_primary_exception = exc
        raise
    finally:
        query_ended_wall_ns = time.time_ns()
        query_ended_monotonic_ns = time.monotonic_ns()
        guard_event_end = len(_F12_FD_GUARD_EVENTS)
        safe_guard_events: list[dict[str, Any]] = []
        diagnostic_capture_error: BaseException | None = None
        diagnostic_write_error: BaseException | None = None
        try:
            safe_guard_events = [
                _f12_safe_guard_event(event)
                for event in _F12_FD_GUARD_EVENTS[
                    query_guard_event_start:guard_event_end
                ]
            ]
        except BaseException as exc:
            diagnostic_capture_error = exc

        try:
            private_diagnostic_paths = (
                qa_root,
                run_root,
                f12_synthetic_sources["root"],
                f12_synthetic_sources["monthly_reference_path"],
            )
            safe_status_label = _redact_watchlist_ui_diagnostic(
                revenue_view.status_label.text(),
                private_paths=private_diagnostic_paths,
            )
            failure_chain: list[dict[str, Any]] = []
            if query_outcome is not None:
                failure_chain.append(
                    {
                        "stage": "query_operation_settled",
                        "operation": query_outcome[0],
                        "success": query_outcome[1],
                        "status_label": safe_status_label,
                    }
                )
            if query_primary_exception is not None:
                failure_chain.append(
                    {
                        "stage": "journey_assertion_or_wait",
                        "exception_type": type(query_primary_exception).__name__,
                        "message": _redact_watchlist_ui_diagnostic(
                            str(query_primary_exception),
                            private_paths=private_diagnostic_paths,
                        ),
                    }
                )
            query_receipt_payload = {
                "schema": "f12-main-query-guard-diagnostics.v1",
                "status": (
                    "failed"
                    if query_primary_exception is not None
                    else "settled"
                ),
                "operation": "核驗雙來源並執行全母體查詢",
                "clock": {
                    "started_wall_ns": query_started_wall_ns,
                    "ended_wall_ns": query_ended_wall_ns,
                    "started_monotonic_ns": query_started_monotonic_ns,
                    "ended_monotonic_ns": query_ended_monotonic_ns,
                    "elapsed_ns": max(
                        0,
                        query_ended_monotonic_ns
                        - query_started_monotonic_ns,
                    ),
                },
                "operation_outcome": (
                    None
                    if query_outcome is None
                    else {
                        "kind": query_outcome[0],
                        "success": query_outcome[1],
                    }
                ),
                "status_label": safe_status_label,
                "guard_event_window": {
                    "start_index": query_guard_event_start,
                    "end_index": guard_event_end,
                    "events": safe_guard_events,
                },
                "failure_chain": failure_chain,
                "write_authority_unchanged": True,
            }
            if diagnostic_capture_error is not None:
                query_receipt_payload["diagnostic_capture_error_type"] = type(
                    diagnostic_capture_error
                ).__name__
        except BaseException as exc:
            if diagnostic_capture_error is None:
                diagnostic_capture_error = exc
            query_receipt_payload = {
                "schema": "f12-main-query-guard-diagnostics.v1",
                "status": (
                    "failed"
                    if query_primary_exception is not None
                    else "settled"
                ),
                "operation": "核驗雙來源並執行全母體查詢",
                "clock": {
                    "started_wall_ns": query_started_wall_ns,
                    "ended_wall_ns": query_ended_wall_ns,
                    "started_monotonic_ns": query_started_monotonic_ns,
                    "ended_monotonic_ns": query_ended_monotonic_ns,
                    "elapsed_ns": max(
                        0,
                        query_ended_monotonic_ns
                        - query_started_monotonic_ns,
                    ),
                },
                "operation_outcome": (
                    None
                    if query_outcome is None
                    else {
                        "kind": query_outcome[0],
                        "success": query_outcome[1],
                    }
                ),
                "status_label": "diagnostic_capture_failed",
                "guard_event_window": {
                    "start_index": query_guard_event_start,
                    "end_index": guard_event_end,
                    "events": safe_guard_events,
                },
                "failure_chain": (
                    []
                    if query_primary_exception is None
                    else [
                        {
                            "stage": "journey_assertion_or_wait",
                            "exception_type": type(
                                query_primary_exception
                            ).__name__,
                        }
                    ]
                ),
                "diagnostic_capture_error_type": type(exc).__name__,
                "write_authority_unchanged": True,
            }

        try:
            diagnostic_write_error = _persist_f12_query_guard_receipt(
                qa_root / "monthly-revenue-query-guard-diagnostics.json",
                query_receipt_payload,
            )
        except BaseException as exc:
            diagnostic_write_error = exc

        diagnostic_errors = tuple(
            error
            for error in (diagnostic_capture_error, diagnostic_write_error)
            if error is not None
        )
        if diagnostic_errors and query_primary_exception is None:
            raise AssertionError(
                "F12 query guard diagnostic receipt capture or write failed"
            ) from diagnostic_errors[0]
        if diagnostic_errors and query_primary_exception is not None:
            add_note = getattr(query_primary_exception, "add_note", None)
            if callable(add_note):
                add_note(
                    "F12 query guard diagnostic receipt had diagnostic errors: "
                    + ",".join(type(error).__name__ for error in diagnostic_errors)
                )
    result = revenue_view.current_result
    page = revenue_view.current_page
    assert result is not None and page is not None
    assert result.counts.declared_count == 258
    assert result.counts.visible_count == 258
    assert result.scope == "current_only"
    assert result.availability_status == "unknown"
    assert result.historical_pit_eligible is False

    stock_code = page.rows[0].stock_code
    revenue_view.page_scroll.ensureWidgetVisible(revenue_view.results_table)
    app.processEvents()
    selected_index = revenue_view.table_model.index_for_stock(stock_code)
    rectangle = revenue_view.results_table.visualRect(selected_index)
    assert selected_index.isValid() and rectangle.isValid()
    QTest.mouseClick(
        revenue_view.results_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rectangle.center(),
    )
    app.processEvents()
    assert revenue_view._selected_row is not None
    assert revenue_view._selected_row.stock_code == stock_code
    revenue_view.detail_button.click()
    app.processEvents()
    assert stock_code in revenue_view.detail_text.toPlainText()
    assert "current-only" in revenue_view.detail_text.toPlainText()
    revenue_view.return_button.click()
    app.processEvents()
    assert revenue_view.current_result is result and revenue_view.current_page is page

    prepared: list[DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1] = []
    revenue_view.bookmarkPrepared.connect(prepared.append)
    revenue_view.bookmark_button.click()
    assert len(prepared) == 1
    bookmark = prepared[0]
    assert bookmark.stock_code == stock_code
    saved_recipe = bookmark.saved_recipe
    selected_page_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.from_json(
        bookmark.selected_page_request_json
    )
    assert selected_page_request.to_json() == bookmark.selected_page_request_json
    selected_query = selected_page_request.query
    assert selected_query.to_json() == result.query.to_json()
    assert selected_query.query_identity_sha256 == bookmark.selected_query_identity_sha256
    assert bookmark.selected_query_identity_sha256 == result.query.query_identity_sha256
    assert selected_page_request.request_identity_sha256 == page.request_identity_sha256
    assert revenue_view._page_request.to_json() == bookmark.selected_page_request_json
    assert selected_page_request.page_index == page.page_index == saved_recipe.page_index
    assert selected_page_request.page_size == page.page_size == saved_recipe.page_size
    saved_f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(
        saved_recipe.f17_query_json
    )
    assert saved_f17_query.to_json() == selected_query.ma_query.f17_query.to_json()
    assert saved_f17_query.to_json() == result.query.ma_query.f17_query.to_json()
    assert (
        saved_f17_query.bundle_identity_sha256
        == result.query.ma_query.f17_query.bundle_identity_sha256
    )
    assert selected_query.ma_query.ma_states == saved_recipe.ma_states
    assert selected_query.minimum_yoy_percent == saved_recipe.minimum_yoy_percent
    assert selected_query.condition_combine_mode == saved_recipe.condition_combine_mode
    assert selected_query.unknown_policy == saved_recipe.unknown_policy
    assert tuple(item.to_dict() for item in selected_query.sort_clauses) == tuple(
        item.to_dict() for item in saved_recipe.sort_clauses
    )
    _wait_until(
        app,
        lambda: not getattr(window, "_technical_official_bookmark_workers", set()),
        timeout=120,
        label="Main bookmark writer completion",
    )
    stored = service.get_research_bookmark(bookmark.bookmark_id)
    assert type(stored) is DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1
    assert stored.to_dict() == bookmark.to_dict()
    assert _sha256_file(watchlist_source) == source_sha_before
    target_sha_after_bookmark = _sha256_file(private_target)
    assert target_sha_after_bookmark != target_sha_after_activation

    window.close()
    _wait_until(
        app,
        lambda: not window.isVisible(),
        timeout=120,
        label="first Main close after worker completion",
    )
    assert window._shutdown_close_requested is True

    child_env = os.environ.copy()
    child_env.update(
        {
            "F12_OPERATION_ROOT": str(operations_parent),
            "F12_BOOKMARK_ID": bookmark.bookmark_id,
            "F12_EXPECTED_STOCK_CODE": stock_code,
            "F12_EXPECTED_QUERY_IDENTITY": bookmark.selected_query_identity_sha256,
            "F12_EXPECTED_REQUEST_IDENTITY": selected_page_request.request_identity_sha256,
            "F12_EXPECTED_BUNDLE_IDENTITY": (
                saved_f17_query.bundle_identity_sha256
            ),
            "F12_EXPECTED_MONTHLY_REFERENCE": str(
                f12_synthetic_sources["monthly_reference_path"]
            ),
            "F12_EXPECTED_COUNT": "258",
            "F12_CHILD_STAGE_LOG": str(
                Path(os.environ["F12_MAIN_QA_ROOT"]) / "fresh-child-stages.jsonl"
            ),
            "F12_CHILD_STACK_TRACE": str(
                Path(os.environ["F12_MAIN_QA_ROOT"]) / "fresh-child-initialization-stack.txt"
            ),
            "F12_RUNTIME_ISOLATION_CHECK_PATH": str(
                Path(os.environ["F12_MAIN_QA_ROOT"])
                / "startup-runtime-isolation-child-check.json"
            ),
        }
    )
    child_total_deadline = time.monotonic() + FRESH_CHILD_PROCESS_TIMEOUT_SECONDS
    child_env["F12_CHILD_TOTAL_TIMEOUT_SECONDS"] = str(
        FRESH_CHILD_PROCESS_TIMEOUT_SECONDS
    )
    child_env["F12_CHILD_TOTAL_DEADLINE_MONOTONIC"] = f"{child_total_deadline:.9f}"
    child_script = Path(__file__).with_name("test_ui_qt_revenue_main_journey_child.py")
    child_log_path = qa_root / "fresh-child-output.log"
    fresh_child_supervisor = _run_owned_logged_child(
        [sys.executable, "-B", "-u", str(child_script)],
        cwd=Path(__file__).resolve().parents[1],
        env=child_env,
        log_path=child_log_path,
        timeout=FRESH_CHILD_PROCESS_TIMEOUT_SECONDS,
    )
    child_receipts = _read_prefixed_json_log_records(
        child_log_path,
        prefix=FRESH_CHILD_RECEIPT_PREFIX,
    )
    child_supervisor_receipt = {
        "status": "passed"
        if fresh_child_supervisor["completed_before_deadline"]
        and fresh_child_supervisor["return_code"] == 0
        else "failed",
        "timeout_seconds": FRESH_CHILD_PROCESS_TIMEOUT_SECONDS,
        "receipt_prefix": FRESH_CHILD_RECEIPT_PREFIX,
        **fresh_child_supervisor,
    }
    _write_json_create_only(
        qa_root / "fresh-child-supervisor-receipt.json",
        child_supervisor_receipt,
    )
    assert fresh_child_supervisor["completed_before_deadline"] is True, (
        _fresh_child_failure_message(
            return_code=fresh_child_supervisor["return_code"],
            reason="600-second deadline exceeded",
            log_path=child_log_path,
        )
    )
    assert fresh_child_supervisor["return_code"] == 0, _fresh_child_failure_message(
        return_code=fresh_child_supervisor["return_code"],
        reason="nonzero exit",
        log_path=child_log_path,
    )
    assert fresh_child_supervisor["remaining_pids_after_close"] == []
    assert len(child_receipts) == 1, _fresh_child_failure_message(
        return_code=fresh_child_supervisor["return_code"],
        reason="missing or duplicate marked receipt",
        log_path=child_log_path,
    )
    child_receipt = child_receipts[0]
    assert child_receipt["pid"] != os.getpid()
    assert child_receipt["parent_pid"] == fresh_child_supervisor["launcher_pid"]
    assert child_receipt["bookmark_id"] == bookmark.bookmark_id
    assert child_receipt["stock_code"] == stock_code
    saved_recipe_payload = json.loads(saved_recipe.to_json())
    selected_request_json_sha256 = hashlib.sha256(
        bookmark.selected_page_request_json.encode("utf-8")
    ).hexdigest()
    saved_recipe_json_sha256 = hashlib.sha256(
        bookmark.saved_recipe_json.encode("utf-8")
    ).hexdigest()
    saved_f17_query_json_sha256 = hashlib.sha256(
        saved_recipe.f17_query_json.encode("utf-8")
    ).hexdigest()
    assert child_receipt["selected_query_identity"] == bookmark.selected_query_identity_sha256
    assert child_receipt["selected_request_identity"] == selected_page_request.request_identity_sha256
    assert child_receipt["selected_request_query_identity"] == selected_query.query_identity_sha256
    assert child_receipt["selected_page_request_json_sha256"] == selected_request_json_sha256
    assert child_receipt["selected_recipe_identity"] == saved_recipe.recipe_identity_sha256
    assert child_receipt["saved_recipe_json_sha256"] == saved_recipe_json_sha256
    assert child_receipt["saved_f17_query_identity"] == saved_f17_query.query_identity_sha256
    assert child_receipt["saved_f17_query_json_sha256"] == saved_f17_query_json_sha256
    assert child_receipt["selected_page_index"] == saved_recipe.page_index
    assert child_receipt["selected_page_size"] == saved_recipe.page_size
    assert child_receipt["reopened_recipe_identity"] == saved_recipe.recipe_identity_sha256
    assert child_receipt["reopened_recipe_json_sha256"] == saved_recipe_json_sha256
    assert child_receipt["reopened_f17_query_identity"] == saved_f17_query.query_identity_sha256
    assert child_receipt["reopened_f17_query_json_sha256"] == saved_f17_query_json_sha256
    assert child_receipt["reopened_query_identity"] != bookmark.selected_query_identity_sha256
    assert child_receipt["reopened_page_query_identity"] == child_receipt["reopened_query_identity"]
    assert child_receipt["reopened_request_query_identity"] == child_receipt["reopened_query_identity"]
    assert child_receipt["reopened_request_identity"] != selected_page_request.request_identity_sha256
    assert child_receipt["reopened_page_request_identity"] == child_receipt["reopened_request_identity"]
    assert child_receipt["reopened_request_page_index"] == saved_recipe.page_index
    assert child_receipt["reopened_request_page_size"] == saved_recipe.page_size
    assert child_receipt["reopened_page_index"] == saved_recipe.page_index
    assert child_receipt["reopened_page_size"] == saved_recipe.page_size
    assert child_receipt["reopened_query_ma_states"] == saved_recipe_payload["ma_states"]
    assert child_receipt["reopened_query_minimum_yoy_percent"] == saved_recipe_payload["minimum_yoy_percent"]
    assert child_receipt["reopened_query_condition_combine_mode"] == saved_recipe.condition_combine_mode
    assert child_receipt["reopened_query_unknown_policy"] == saved_recipe.unknown_policy
    assert child_receipt["reopened_query_sort_clauses"] == saved_recipe_payload["sort_clauses"]
    assert child_receipt["reopened_monthly_cutoff_utc"] == saved_recipe.monthly_cutoff_utc
    assert child_receipt["reopened_monthly_method_id"] == SELECTION_REVENUE_YOY_METHOD_ID
    assert child_receipt["reopened_monthly_method_version"] == SELECTION_REVENUE_YOY_METHOD_VERSION
    assert child_receipt["reopened_page_request_json_sha256"]
    assert child_receipt["declared_count"] == 258
    assert child_receipt["query_phase_budget_ceiling_seconds"] == (
        FRESH_CHILD_QUERY_PHASE_TIMEOUT_SECONDS
    )
    assert (
        0.0
        <= child_receipt["query_phase_budget_seconds"]
        <= FRESH_CHILD_QUERY_PHASE_TIMEOUT_SECONDS
    )
    assert _sha256_file(watchlist_source) == source_sha_before
    assert _sha256_file(private_target) == target_sha_after_bookmark

    run_receipt = {
        "status": "passed_fresh_main_revenue_reopen",
        "parent_pid": os.getpid(),
        "child": child_receipt,
        "bookmark_id": bookmark.bookmark_id,
        "stock_code": stock_code,
        "selected_query_identity": bookmark.selected_query_identity_sha256,
        "selected_request_identity": selected_page_request.request_identity_sha256,
        "reopened_query_identity": child_receipt["reopened_query_identity"],
        "reopened_request_identity": child_receipt["reopened_request_identity"],
        "bundle_identity": saved_f17_query.bundle_identity_sha256,
        "monthly_reference_identity": source_ref.identity_sha256,
        "declared_count": 258,
        "source_sha256_before_after": source_sha_before,
        "private_target_sha256_after_bookmark": target_sha_after_bookmark,
        "candidate_root": str(f12_synthetic_sources["root"]),
        "isolated_run_root": str(run_root),
        "fresh_child_log_sha256": fresh_child_supervisor[
            "combined_output_log_sha256"
        ],
        "fresh_child_exit_code": fresh_child_supervisor["return_code"],
        "watchlist_upgrade_modal_counts": upgrade_modal_counts,
        "watchlist_upgrade_outcome": observed_operations["upgrade_outcomes"],
        "watchlist_backup_attempts": observed_operations["backup_attempts"],
    }
    receipt_path = run_root / "durable_main_journey_receipt.json"
    receipt_path.write_text(
        json.dumps(run_receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_personal_resolver_read_role_accepts_only_exact_ro_query_only_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """覆蓋先前 T39 SQL role 所拒絕的精確 resolver read。

    連線守衛只在此測試的隔離 personal store 周圍啟用。其他 COW activation
    連線維持產品行為；repository reader 必須使用 exact target URI、``uri=True``、
    query-only 模式、read transaction，並自然關閉連線。
    """

    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    personal_root = data_root / "personal"
    source_path = output_root / "watchlist" / "default.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    data_root.mkdir()
    source_path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "Synthetic isolated source",
                "description": "F12 role probe only",
                "created_at": "2026-10-11T00:00:00+08:00",
                "updated_at": "2026-10-11T00:00:00+08:00",
                "items": [],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    source_sha_before = _sha256_file(source_path)
    config = TWStockConfig(
        data_root=data_root,
        output_root=output_root,
        profile="prod",
        personal_data_root=personal_root,
        personal_watchlist_source=source_path,
    )
    service = PersonalWatchlistService(config)
    status = service.upgrade_to_repository()
    assert status.is_repository is True
    target = service.canonical_repository_path.resolve()
    target_sha_before = _sha256_file(target)

    raw_connect = sqlite3.connect
    expected_uri = watchlist_repository_module._sqlite_uri(target, "ro")
    records: list[dict[str, Any]] = []
    rejections: list[str] = []

    def guarded_connect(database: object, *args: object, **kwargs: object):
        caller = sys._getframe(1)
        if caller.f_code is not WatchlistRepository._open_read_only.__code__:
            return raw_connect(database, *args, **kwargs)
        repository = caller.f_locals.get("self")
        actual_target = getattr(repository, "db_path", None)
        exact = (
            type(actual_target) is type(Path())
            and actual_target.resolve() == target
            and database == expected_uri
            and args == ()
            and kwargs == {"uri": True}
        )
        if not exact:
            rejections.append("unexpected_private_sqlite_uri")
            raise sqlite3.OperationalError("unexpected_private_sqlite_uri")
        connection = raw_connect(database, *args, **kwargs)
        record: dict[str, Any] = {
            "connection": connection,
            "uri": database,
            "uri_option": kwargs.get("uri"),
            "trace": [],
            "query_only": None,
            "transaction_open": None,
            "write_blocked": None,
        }
        connection.set_trace_callback(record["trace"].append)
        records.append(record)
        return connection

    original_table_names = watchlist_repository_module.item_storage.table_names

    def observe_table_names(connection: sqlite3.Connection) -> set[str]:
        record = next(
            (item for item in records if item["connection"] is connection),
            None,
        )
        if record is None:
            return original_table_names(connection)
        record["query_only"] = connection.execute("PRAGMA query_only").fetchone() == (1,)
        record["transaction_open"] = connection.in_transaction
        try:
            connection.execute("UPDATE watchlists SET payload_json=payload_json")
        except sqlite3.OperationalError as exc:
            record["write_blocked"] = "readonly" in str(exc).casefold()
        else:
            record["write_blocked"] = False
        return original_table_names(connection)

    monkeypatch.setattr(watchlist_repository_module.sqlite3, "connect", guarded_connect)
    monkeypatch.setattr(
        watchlist_repository_module.item_storage,
        "table_names",
        observe_table_names,
    )

    from app_module.watchlist_cow_activation import resolve_watchlist_sqlite_activation

    resolved = resolve_watchlist_sqlite_activation(
        source_path,
        control_paths=service.control_paths,
    )
    assert resolved["status"] == "active", (
        f"resolver returned {resolved!r}; guard rejections={rejections!r}"
    )
    assert records, "the active-marker resolver must read the exact private target"
    assert not rejections
    for record in records:
        assert record["uri"] == expected_uri
        assert record["uri_option"] is True
        assert record["query_only"] is True
        assert record["transaction_open"] is True
        assert record["write_blocked"] is True
        normalized_trace = {
            " ".join(statement.strip().rstrip(";").split()).casefold()
            for statement in record["trace"]
        }
        assert "pragma query_only=on" in normalized_trace
        assert "begin" in normalized_trace
        with pytest.raises(sqlite3.ProgrammingError):
            record["connection"].cursor()

    assert _sha256_file(source_path) == source_sha_before
    assert _sha256_file(target) == target_sha_before

    # 個人目標以外的有效 repository 也必須在 SQLite 開啟前被 exact role 拒絕。
    other_target = tmp_path / "unrelated" / "watchlists.sqlite"
    other_target.parent.mkdir()
    WatchlistRepository(
        other_target,
        capacity_preflight=lambda _request: True,
    )._initialize_schema()
    unrelated = WatchlistRepository(other_target).detect_storage_format()
    assert unrelated["ready"] is False
    assert rejections == ["unexpected_private_sqlite_uri"]
    assert _sha256_file(source_path) == source_sha_before
    assert _sha256_file(target) == target_sha_before
