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
import time
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


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _validate_and_install_startup_write_guard() -> dict[str, Any]:
    """驗證子程序繼承的隔離環境，並限制 Python 可見檔案寫入根。"""

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

    def guarded_path(raw_path: object) -> Path:
        if not isinstance(raw_path, (str, bytes, os.PathLike)):
            raise PermissionError("寫入目標不是可驗證的檔案系統路徑")
        candidate = Path(os.fsdecode(os.fspath(raw_path)))
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate.resolve(strict=False)

    def require_write_root(raw_path: object) -> None:
        candidate = guarded_path(raw_path)
        if not any(_path_is_within(candidate, root) for root in allowed_write_roots):
            raise PermissionError(f"F12 private write guard blocked: {candidate}")

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

    from contextvars import ContextVar

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
                require_write_root(arguments[0])
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
                        require_write_root(raw_database)
            return
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.chown", "os.truncate", "os.utime"}:
            if arguments:
                require_write_root(arguments[0])
            return
        if event in {"os.rename", "os.replace", "os.link", "os.symlink"}:
            for raw_path in arguments[:2]:
                require_write_root(raw_path)

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
            "open write/create/append/truncate",
            "sqlite3.connect private paths and canonical ro/rw file URIs",
            "ro file URI connections force PRAGMA query_only=ON",
            "Python os mkdir/remove/rmdir/metadata/rename/link events",
        ],
        "native_library_or_external_process_writes": "not covered by Python audit events",
    }
    _write_json_create_only(check_path, receipt)
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
        assert modal_counts["information"] + modal_counts["warning"] == 1
        assert repository_active is True, (
            "真 UI click 未啟用私人 repository；已保存 UI、COW 角色與儲存驗證收據："
            f"{ui_receipt['final']!r}; causes={cow_preflight_causes!r}"
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
    activated_status = service.get_storage_status()
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
                "modal_counts": modal_counts,
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
    revenue_view.open_candidate_button.click()
    _wait_until(
        app,
        lambda: len(outcomes) >= 2,
        timeout=480,
        label="Main full-N revenue query",
    )
    assert outcomes[-1] == ("核驗雙來源並執行全母體查詢", True), revenue_view.status_label.text()
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
    assert (
        bookmark.saved_recipe.f17_query.bundle_identity_sha256
        == result.query.ma_query.f17_query.bundle_identity_sha256
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
            "F12_EXPECTED_BUNDLE_IDENTITY": (
                bookmark.saved_recipe.f17_query.bundle_identity_sha256
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
    assert child_receipt["query_identity"] == bookmark.selected_query_identity_sha256
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
        "query_identity": bookmark.selected_query_identity_sha256,
        "bundle_identity": bookmark.saved_recipe.f17_query.bundle_identity_sha256,
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
