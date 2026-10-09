"""以完整 MainWindow 驗證四均線研究收藏與隔離啟動。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import tempfile
import threading
import time
from typing import Any, cast
from urllib.parse import urlsplit
from urllib.request import url2pathname

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
)
from app_module.daily_market_technical_official_disposition_ma_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE,
    DailyMarketTechnicalOfficialDispositionMaBookmarkV1,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.watchlist_service import decode_daily_market_research_bookmark
from ui_qt.main import MainWindow, _drain_qt_deferred_deletes, apply_app_theme
from ui_qt.views.daily_market_technical_official_disposition_ma_view import (
    DailyMarketTechnicalOfficialDispositionMaView,
)
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.workers.task_worker import running_task_workers


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_QA_ROOT = _REPOSITORY_ROOT / "output" / "qa" / "ma_bookmark_main_startup_20261008_a"
_SOURCE_ENV_KEYS = (
    "MA_SAVED_SOURCE_BUNDLE_ROOT",
    "MA_SAVED_SOURCE_BUNDLE_IDENTITY_SHA256",
    "MA_SAVED_SOURCE_MANIFEST_SHA256",
    "MA_SAVED_SOURCE_TREE_SHA256",
)
_SOURCE_INVENTORY_KEYS = {
    "technical_database",
    "technical_store_root",
    "technical_parent_roots",
    "market_assignment_root",
    "official_disposal_root",
}
_TOTAL_DEADLINE_SECONDS = 300.0
_OPERATION_DEADLINE_SECONDS = 180.0
_CLEANUP_DEADLINE_SECONDS = 20.0
_JOURNEY_DEADLINE_SECONDS = _TOTAL_DEADLINE_SECONDS - _CLEANUP_DEADLINE_SECONDS

_ISOLATED_ENVIRONMENT_KEYS = frozenset(
    {
        "APPDATA",
        "BALDR_CONFIG",
        "BALDR_ML_RESEARCH_STORAGE_CONFIG",
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
        "DATA_FRESHNESS_STATUS_ARTIFACT",
        "DATA_UPDATE_HISTORY_ARTIFACT",
        "DATA_UPDATE_STATUS_ARTIFACT",
        "EVIDENCE_REHEARSAL_REPORT",
        "FINMIND_TOKEN",
        "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
        "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE",
        "FORMAL_DAILY_RUNTIME_CONFIG",
        "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
        "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE",
        "FUNDAMENTAL_READ_SNAPSHOT_ROOT",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "LOCALAPPDATA",
        "MONTHLY_REVENUE_AVAILABILITY_CANDIDATE",
        "MONTHLY_REVENUE_SNAPSHOT_CANDIDATE",
        "MPLCONFIGDIR",
        "OFFICIAL_CALENDAR_CACHE_PATH",
        "PERSONAL_DATA_ROOT",
        "PERSONAL_H20_ACTIVATION_CONFIG",
        "PERSONAL_H20_SQLITE_READ_ROOT",
        "PERSONAL_JOURNAL_MODE",
        "PERSONAL_JOURNAL_ROOT",
        "PERSONAL_MODEL_POLICY_PATH",
        "PERSONAL_STORE_MODE",
        "PERSONAL_STORE_ROOT",
        "PERSONAL_WATCHLIST_SOURCE",
        "PHASE3C_CANDIDATE_DB_PATH",
        "PIT_MEMBERSHIP_EXPECTED_CLASSIFICATION_VERSION",
        "PIT_MARKET_SCOPE",
        "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
        "PIT_SECTOR_MEMBERSHIP_PATH",
        "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
        "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
        "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
        "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
        "P0_SOURCE_CONTROL_CENTER_AUDIT",
        "P0_SOURCE_CONTROL_CENTER_DECISIONS",
        "P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE",
        "PAPER_EQUAL_WEIGHT_BENCHMARK_PATH",
        "PAPER_TRADE_LEDGER_PATH",
        "PROFILE",
        "PROGRAM_READINESS_ARTIFACT",
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT",
        "RESEARCH_CONSOLE_PROJECTION",
        "RESEARCH_STATE_ROOT",
        "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT",
        "TECHNICAL_UNIVERSE_READ_ROOT",
        "TPEX_REFRESH_STATUS_ARTIFACT",
        "TEMP",
        "TMP",
        "WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH",
    }
)


@dataclass(frozen=True, slots=True)
class _BundleSource:
    root: Path
    identity_sha256: str
    manifest_sha256: str
    expected_tree_sha256: str | None
    synthetic_root: Path
    source_roots: tuple[Path, ...]
    origin: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(to_internal_io_path(path), "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _source_from_request(request: pytest.FixtureRequest) -> _BundleSource:
    supplied = {name: os.environ.get(name) for name in _SOURCE_ENV_KEYS}
    present = tuple(value is not None for value in supplied.values())
    if any(present):
        if not all(present):
            raise ValueError("ma_full_main_source_bundle_environment_incomplete")
        root_text = cast(str, supplied[_SOURCE_ENV_KEYS[0]])
        identity = cast(str, supplied[_SOURCE_ENV_KEYS[1]])
        manifest_sha256 = cast(str, supplied[_SOURCE_ENV_KEYS[2]])
        tree_sha256 = cast(str, supplied[_SOURCE_ENV_KEYS[3]])
        if not Path(root_text).is_absolute():
            raise ValueError("ma_full_main_bundle_root_not_absolute")
        for label, value in (
            ("identity", identity),
            ("manifest", manifest_sha256),
            ("tree", tree_sha256),
        ):
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ValueError(f"ma_full_main_invalid_{label}_sha256")
        root = Path(root_text)
        synthetic_root = root.parents[2]
        source_roots = _source_roots_from_manifest(root, identity, synthetic_root)
        return _BundleSource(
            root,
            identity,
            manifest_sha256,
            tree_sha256,
            synthetic_root,
            source_roots,
            "explicit_saved_bundle",
        )

    fixture = request.getfixturevalue("bundle_fixture")
    root = Path(fixture.bundle_root)
    return _BundleSource(
        root=root,
        identity_sha256=str(fixture.reference.bundle_identity_sha256),
        manifest_sha256=str(fixture.reference.manifest_sha256),
        expected_tree_sha256=None,
        synthetic_root=Path(fixture.qa_root),
        source_roots=(Path(fixture.database), *tuple(Path(item) for item in fixture.source_roots), root),
        origin="fresh_unique_bundle_fixture",
    )


def _source_roots_from_manifest(
    root: Path,
    identity_sha256: str,
    synthetic_root: Path,
) -> tuple[Path, ...]:
    manifest_path = root / "manifests" / f"{identity_sha256}.json"
    with open(to_internal_io_path(manifest_path), "r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    inventory = manifest.get("source_inventory")
    if not isinstance(inventory, dict) or set(inventory) != _SOURCE_INVENTORY_KEYS:
        raise ValueError("ma_full_main_source_inventory_invalid")
    parents = inventory.get("technical_parent_roots")
    if not isinstance(parents, list) or not parents or any(not isinstance(item, str) for item in parents):
        raise ValueError("ma_full_main_parent_roots_invalid")
    raw_roots = (
        inventory.get("technical_database"),
        inventory.get("technical_store_root"),
        *parents,
        inventory.get("market_assignment_root"),
        inventory.get("official_disposal_root"),
        str(root),
    )
    roots: list[Path] = []
    canonical_synthetic = synthetic_root.resolve(strict=True)
    for raw in raw_roots:
        if not isinstance(raw, str):
            raise ValueError("ma_full_main_source_root_invalid")
        lexical_path = Path(raw)
        if not lexical_path.is_absolute() or ".." in lexical_path.parts:
            raise ValueError("ma_full_main_source_root_not_canonical_absolute")
        # 保留一般路徑身分，實際存在性與各層 reparse 檢查走支援長路徑的 I/O 形式。
        path = Path(os.path.normpath(str(lexical_path)))
        try:
            path.relative_to(canonical_synthetic)
        except ValueError as exc:
            raise ValueError("ma_full_main_source_outside_isolated_fixture") from exc
        current = path
        while True:
            try:
                info = os.lstat(to_internal_io_path(current))
            except OSError as exc:
                raise ValueError("ma_full_main_source_path_unavailable") from exc
            if _is_reparse(info):
                raise ValueError("ma_full_main_source_reparse")
            if current == current.parent:
                break
            current = current.parent
        if path not in roots:
            roots.append(path)
    return tuple(roots)


def _tree_signature(path: Path) -> tuple[tuple[str, int, int, str], ...]:
    info = os.lstat(to_internal_io_path(path))
    if _is_reparse(info):
        raise ValueError("ma_full_main_inventory_reparse")
    if stat.S_ISREG(info.st_mode):
        return ((path.name, info.st_size, info.st_mtime_ns, _sha256_file(path)),)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("ma_full_main_inventory_root_type")
    entries: list[tuple[str, int, int, str]] = []
    total_bytes = 0
    io_root = to_internal_io_path(path)
    for directory, directory_names, file_names in os.walk(io_root, followlinks=False):
        for name in tuple(directory_names):
            child = os.path.join(directory, name)
            child_info = os.lstat(child)
            if _is_reparse(child_info) or not stat.S_ISDIR(child_info.st_mode):
                raise ValueError("ma_full_main_inventory_directory_invalid")
        for name in file_names:
            child = os.path.join(directory, name)
            child_info = os.lstat(child)
            if _is_reparse(child_info) or not stat.S_ISREG(child_info.st_mode):
                raise ValueError("ma_full_main_inventory_file_invalid")
            digest = hashlib.sha256()
            with open(child, "rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            entries.append(
                (
                    os.path.relpath(child, io_root).replace("\\", "/"),
                    child_info.st_size,
                    child_info.st_mtime_ns,
                    digest.hexdigest(),
                )
            )
            total_bytes += child_info.st_size
            if len(entries) > 100_000 or total_bytes > 64 * 1024 * 1024:
                raise ValueError("ma_full_main_inventory_budget_exceeded")
    return tuple(sorted(entries))


def _tree_inventory(roots: tuple[Path, ...]) -> tuple[list[dict[str, object]], str]:
    records: list[dict[str, object]] = []
    total_bytes = 0
    for root in roots:
        signature = _tree_signature(root)
        root_bytes = sum(item[1] for item in signature)
        total_bytes += root_bytes
        records.append(
            {
                "root": str(root),
                "file_count": len(signature),
                "total_bytes": root_bytes,
                "files_sha256": hashlib.sha256(
                    json.dumps(
                        signature,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest(),
            }
        )
    if total_bytes > 64 * 1024 * 1024:
        raise ValueError("ma_full_main_inventory_total_budget_exceeded")
    encoded = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return records, hashlib.sha256(encoded).hexdigest()


def _new_attempt() -> Path:
    _QA_ROOT.mkdir(parents=True, exist_ok=True)
    attempt = _QA_ROOT / f"attempt_{time.time_ns()}_{os.getpid()}"
    os.mkdir(to_internal_io_path(attempt))
    return attempt


def _write_json(path: Path, value: object) -> None:
    with open(to_internal_io_path(path), "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def _set_isolated_environment(
    attempt: Path,
    source: _BundleSource,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    temporary_parent = Path(tempfile.gettempdir()).resolve(strict=True)
    application_root = Path(
        tempfile.mkdtemp(prefix="ma-bookmark-full-mainwindow-")
    ).resolve(strict=True)
    try:
        application_root.relative_to(_REPOSITORY_ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise ValueError("ma_full_main_application_root_inside_repository")
    data_root = application_root / "data"
    output_root = application_root / "output"
    research_state_root = application_root / "research-state"
    temporary_root = application_root / "temporary"
    local_app_root = application_root / "localapp"
    roaming_root = application_root / "appdata"
    ml_research_root = application_root / "ml-research"
    personal_h20_root = application_root / "personal-h20-read"
    storage_config_path = application_root / "ml-research-storage.json"
    for path in (temporary_root, personal_h20_root):
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temporary_root))
    for name in _ISOLATED_ENVIRONMENT_KEYS | frozenset(_SOURCE_ENV_KEYS):
        monkeypatch.delenv(name, raising=False)

    values = {
        "DATA_ROOT": data_root,
        "OUTPUT_ROOT": output_root,
        "RESEARCH_STATE_ROOT": research_state_root,
        "TEMP": temporary_root,
        "TMP": temporary_root,
        "MPLCONFIGDIR": output_root / "application_state" / "matplotlib",
        "LOCALAPPDATA": local_app_root,
        "APPDATA": roaming_root,
        "BALDR_CONFIG": application_root / "baldr-config.json",
        "PERSONAL_MODEL_POLICY_PATH": research_state_root / "personal-use-policy.json",
        "PERSONAL_H20_ACTIVATION_CONFIG": data_root / "personal" / "recommendation_h20" / "activation.json",
        "PERSONAL_H20_SQLITE_READ_ROOT": personal_h20_root,
        "OFFICIAL_CALENDAR_CACHE_PATH": data_root / "official-calendar-cache.json",
        "PHASE3C_CANDIDATE_DB_PATH": application_root / "candidate" / "candidate.sqlite",
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT": research_state_root / "recommendation-learning",
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT": research_state_root / "bank-taiwan-recommendation-learning",
        "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT": source.root,
    }
    for name, path in values.items():
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv("PROFILE", "prod")
    storage_config_path.parent.mkdir(parents=True, exist_ok=True)
    storage_config_path.write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(ml_research_root),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BALDR_ML_RESEARCH_STORAGE_CONFIG", str(storage_config_path))
    return {
        "application_root": application_root,
        "application_temp_parent": temporary_parent,
        "data_root": data_root,
        "output_root": output_root,
        "research_state_root": research_state_root,
        "temporary_root": temporary_root,
        "local_app_root": local_app_root,
        "roaming_root": roaming_root,
        "ml_research_root": ml_research_root,
        "personal_h20_root": personal_h20_root,
        "storage_config_path": storage_config_path,
    }


def _install_network_and_sqlite_guards(
    monkeypatch: pytest.MonkeyPatch,
    application_root: Path,
) -> tuple[list[str], list[str]]:
    network_attempts: list[str] = []
    sqlite_paths: list[str] = []

    def network_blocker(operation: str) -> Any:
        def deny_network(*_args: object, **_kwargs: object) -> None:
            network_attempts.append(f"{operation} attempted")
            raise AssertionError("隔離 MainWindow 旅程不得連接網路或查詢外部 DNS")

        return deny_network

    monkeypatch.setattr(socket.socket, "connect", network_blocker("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", network_blocker("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", network_blocker("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", network_blocker("socket.getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", network_blocker("socket.gethostbyname"))
    monkeypatch.setattr(socket, "gethostbyname_ex", network_blocker("socket.gethostbyname_ex"))
    monkeypatch.setattr(socket, "getnameinfo", network_blocker("socket.getnameinfo"))
    original_connect = sqlite3.connect

    def guarded_sqlite_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        text = os.fspath(database) if isinstance(database, os.PathLike) else str(database)
        if text in {":memory:", "file::memory:"}:
            sqlite_paths.append(text)
            return original_connect(database, *args, **kwargs)
        raw_path = text
        if raw_path.startswith("file:"):
            try:
                parsed = urlsplit(raw_path)
            except ValueError as exc:
                sqlite_paths.append(raw_path)
                raise AssertionError("SQLite file URI 格式無效") from exc
            if parsed.scheme.lower() != "file" or parsed.netloc or parsed.fragment:
                sqlite_paths.append(raw_path)
                raise AssertionError("SQLite URI 必須是無遠端 authority 的本機 file URI")
            if parsed.path == ":memory:":
                sqlite_paths.append(text)
                return original_connect(database, *args, **kwargs)
            raw_path = url2pathname(parsed.path)
        path = Path(raw_path).expanduser().resolve(strict=False)
        try:
            path.relative_to(application_root.resolve(strict=True))
        except ValueError as exc:
            sqlite_paths.append(str(path))
            raise AssertionError("SQLite 僅可開啟本次隔離應用根內的資料庫") from exc
        sqlite_paths.append(str(path))
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_sqlite_connect)
    return network_attempts, sqlite_paths


def _wait_for(
    app: QApplication,
    predicate: Any,
    *,
    deadline: float,
    failure: str,
) -> None:
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return
        time.sleep(0.01)
    app.processEvents()
    raise TimeoutError(failure)


def _wait_view_operation(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
    events: list[tuple[str, bool]],
    action: Any,
    expected_kind: str,
    total_deadline: float,
) -> None:
    start_index = len(events)
    action()
    deadline = min(total_deadline, time.monotonic() + _OPERATION_DEADLINE_SECONDS)
    while time.monotonic() < deadline:
        app.processEvents()
        if len(events) > start_index:
            kind, success = events[start_index]
            if kind != expected_kind or not success:
                raise AssertionError(
                    f"MA 主視窗操作失敗：{kind}:{success}:{view.status_label.text()}"
                )
            break
        time.sleep(0.01)
    else:
        raise TimeoutError(f"MA 主視窗操作逾時：{expected_kind}")
    _wait_for(
        app,
        lambda: view.active_worker is None and not view._has_running_worker(),
        deadline=deadline,
        failure=f"MA 主視窗原生工作逾時：{expected_kind}",
    )


def _click_stock(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
    stock_code: str,
) -> None:
    index = view.results_model.index_for_stock(stock_code)
    if not index.isValid():
        raise AssertionError(f"股票不在目前可見頁：{stock_code}")
    rectangle = view.results_table.visualRect(index)
    if not rectangle.isValid() or rectangle.isEmpty():
        raise AssertionError(f"股票列未呈現在畫面：{stock_code}")
    QTest.mouseClick(
        view.results_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rectangle.center(),
    )
    app.processEvents()
    current = view.results_table.currentIndex()
    row = view.results_model.row_at(current.row()) if current.isValid() else None
    if row is None or row.stock_code != stock_code:
        raise AssertionError(f"股票選取不符：{stock_code}")


def _close_mainwindow(app: QApplication, window: MainWindow, deadline: float) -> bool:
    try:
        if window.isVisible():
            window.close()
        _wait_for(
            app,
            lambda: not window.isVisible()
            and bool(getattr(window, "_shutdown_close_finalizing", False)),
            deadline=deadline,
            failure="MainWindow 合作式關閉逾時",
        )
        _drain_qt_deferred_deletes(app, (window,))
        return not running_task_workers()
    except RuntimeError:
        return False
    except TimeoutError:
        return False


def _bookmark_row(
    watchlist: WatchlistView,
    bookmark_id: str,
) -> int:
    if watchlist.stocks_model is None:
        raise AssertionError("Watchlist 尚未建立資料模型")
    frame = watchlist.stocks_model.getDataFrame()
    matches = [
        int(index)
        for index, row in frame.iterrows()
        if str(row.get("source_id", "")) == bookmark_id
    ]
    if len(matches) != 1:
        raise AssertionError(f"Watchlist 原研究收藏列數不符：{len(matches)}")
    row = frame.loc[matches[0]]
    decoded = decode_daily_market_research_bookmark(row.get("research_bookmark"))
    if (
        row.get("source") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE
        or type(decoded) is not DailyMarketTechnicalOfficialDispositionMaBookmarkV1
        or decoded.bookmark_id != bookmark_id
    ):
        raise AssertionError("Watchlist 未保留四均線專屬收藏種類")
    return matches[0]


def test_isolation_guards_reject_dns_and_remote_sqlite_uri_but_decode_local_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """確認網路/DNS封鎖與本機 SQLite file URI 路徑正規化。"""

    application_root = tmp_path / "隔離 應用"
    application_root.mkdir()
    network_attempts, sqlite_paths = _install_network_and_sqlite_guards(
        monkeypatch,
        application_root,
    )
    with pytest.raises(AssertionError, match="不得連接網路"):
        socket.getaddrinfo("example.invalid", 443)
    assert network_attempts == ["socket.getaddrinfo attempted"]

    remote_uri = "file://remote.example/share/escape.sqlite?mode=ro"
    with pytest.raises(AssertionError, match="無遠端 authority"):
        sqlite3.connect(remote_uri, uri=True)
    assert sqlite_paths == [remote_uri]

    local_database = application_root / "encoded name.sqlite"
    local_uri = local_database.as_uri() + "?mode=rwc"
    connection = sqlite3.connect(local_uri, uri=True)
    try:
        connection.execute("CREATE TABLE guard_probe (value INTEGER)")
    finally:
        connection.close()
    assert sqlite_paths[-1] == str(local_database.resolve())


def test_full_mainwindow_isolated_ma_bookmark_startup_route_and_shutdown(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """驗證完整主視窗初始化、四均線收藏重開與合作式關閉。"""

    source = _source_from_request(request)
    attempt = _new_attempt()
    receipt_path = attempt / "main_startup_receipt.json"
    started = time.monotonic()
    total_deadline = started + _TOTAL_DEADLINE_SECONDS
    journey_deadline = started + _JOURNEY_DEADLINE_SECONDS
    receipt: dict[str, object] = {
        "schema": "ma-bookmark-full-mainwindow-startup.v1",
        "status": "running",
        "acceptance_scope": "完整 MainWindow constructor／MA 收藏／Watchlist typed route／shutdown；合成隔離驗證",
        "source_origin": source.origin,
        "bundle_root": str(source.root),
        "bundle_identity_sha256": source.identity_sha256,
        "manifest_sha256_expected": source.manifest_sha256,
        "source_fixture_producer_invoked_by_test_after_resolution": False,
        "source_tree_sha256_before": None,
        "source_tree_sha256_after": None,
        "exact_read_calls": [],
        "phases": [],
        "attempt_root": str(attempt),
        "test_preimage": "absent_before_this_attempt; rollback=remove_this_new_test_file_and_its_attempt_outputs_only",
    }
    _write_json(receipt_path, receipt)
    app: QApplication | None = None
    window: MainWindow | None = None
    view: DailyMarketTechnicalOfficialDispositionMaView | None = None
    failed: BaseException | None = None
    cleanup_ok = False
    network_attempts: list[str] = []
    sqlite_paths: list[str] = []
    read_calls: list[dict[str, object]] = []
    phases: list[str] = []
    receipt["phases"] = phases
    read_lock = threading.Lock()
    before_inventory: list[dict[str, object]] = []
    before_tree_sha: str | None = None
    source_manifest = source.root / "manifests" / f"{source.identity_sha256}.json"
    watchlist_primary: Path | None = None
    bookmark_json_sha: str | None = None

    try:
        receipt["phase"] = "source_preflight"
        if _sha256_file(source_manifest) != source.manifest_sha256:
            raise AssertionError("固定來源 manifest SHA 不符")
        before_inventory, before_tree_sha = _tree_inventory(source.source_roots)
        receipt["source_tree_sha256_before"] = before_tree_sha
        receipt["source_inventory_before"] = before_inventory
        if source.expected_tree_sha256 is not None and before_tree_sha != source.expected_tree_sha256:
            raise AssertionError("固定來源樹 SHA 不符")

        receipt["phase"] = "isolate_application_configuration"
        paths = _set_isolated_environment(attempt, source, monkeypatch)
        if paths["application_root"].resolve(strict=True).is_relative_to(_REPOSITORY_ROOT.resolve(strict=True)):
            raise AssertionError("應用隔離根不可位於 repository 內")
        source_root = source.root.resolve(strict=True)
        for key in ("data_root", "output_root", "research_state_root", "temporary_root", "local_app_root", "roaming_root"):
            isolated_path = paths[key].resolve(strict=False)
            if isolated_path == source_root or isolated_path.is_relative_to(source_root) or source_root.is_relative_to(isolated_path):
                raise AssertionError(f"隔離設定與保存來源重疊：{key}")
        network_attempts, sqlite_paths = _install_network_and_sqlite_guards(
            monkeypatch,
            paths["application_root"],
        )
        app = cast(QApplication, QApplication.instance() or QApplication([]))
        apply_app_theme(app)

        receipt["phase"] = "construct_full_mainwindow"
        receipt["configured_roots"] = {
            name: str(path)
            for name, path in paths.items()
        }
        window = MainWindow(
            policy_config_path=paths["research_state_root"] / "personal-use-policy.json"
        )
        if type(window) is not MainWindow:
            raise AssertionError("未使用完整 MainWindow 類別")
        app.processEvents()
        config_roots = {
            "data_root": str(window.config.data_root),
            "output_root": str(window.config.output_root),
            "application_data_root": window.application_settings.environment["DATA_ROOT"],
            "application_output_root": window.application_settings.environment["OUTPUT_ROOT"],
            "runtime_state_root": str(window.application_settings.runtime_state_root),
            "ml_registry_repository_root": str(window.application_settings.ml_registry_repository_root),
            "official_read_root": str(window.config.technical_official_disposition_read_root),
            "application_temp_parent": str(paths["application_temp_parent"]),
        }
        if (
            Path(config_roots["data_root"]).resolve() != paths["data_root"].resolve()
            or Path(config_roots["output_root"]).resolve() != paths["output_root"].resolve()
            or Path(config_roots["application_data_root"]).resolve() != paths["data_root"].resolve()
            or Path(config_roots["application_output_root"]).resolve() != paths["output_root"].resolve()
            or Path(config_roots["runtime_state_root"]).resolve() != (paths["output_root"] / "application_state").resolve()
            or Path(config_roots["ml_registry_repository_root"]).resolve() != paths["research_state_root"].resolve()
            or Path(config_roots["official_read_root"]).resolve() != source_root
        ):
            raise AssertionError("MainWindow 實際設定未與明示隔離根一致")
        if window.watchlist_service is None or not isinstance(window.watchlist_view, WatchlistView):
            raise AssertionError("完整 MainWindow 未建立真 Watchlist service/view")
        if not isinstance(window.technical_official_ma_research_view, DailyMarketTechnicalOfficialDispositionMaView):
            raise AssertionError("完整 MainWindow 未掛載四均線研究頁")
        if window.watchlist_service.default_watchlist_file.resolve() != (
            paths["output_root"] / "watchlist" / "default.json"
        ).resolve():
            raise AssertionError("Watchlist writer 未落在隔離 OUTPUT_ROOT")
        watchlist_primary = window.watchlist_service.default_watchlist_file
        receipt["main_config_roots"] = config_roots
        receipt["watchlist_primary_path"] = str(watchlist_primary)
        receipt["startup_elapsed_seconds"] = round(time.monotonic() - started, 3)
        if time.monotonic() >= journey_deadline:
            raise TimeoutError("完整 MainWindow 啟動超過 280 秒旅程期限")

        original_read_exact = DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact

        def counted_read_exact(
            self: DailyMarketTechnicalOfficialDispositionBundleReaderV1,
            bundle_identity_sha256: str,
            *,
            expected_manifest_sha256: str,
            cancel_callback: Any = None,
            technical_read_session_builder: Any = None,
        ):
            with read_lock:
                read_calls.append(
                    {
                        "output_root": str(self.output_root),
                        "bundle_identity_sha256": bundle_identity_sha256,
                        "expected_manifest_sha256": expected_manifest_sha256,
                    }
                )
            return original_read_exact(
                self,
                bundle_identity_sha256,
                expected_manifest_sha256=expected_manifest_sha256,
                cancel_callback=cancel_callback,
                technical_read_session_builder=technical_read_session_builder,
            )

        monkeypatch.setattr(
            DailyMarketTechnicalOfficialDispositionBundleReaderV1,
            "read_exact",
            counted_read_exact,
        )

        receipt["phase"] = "show_and_navigate_to_real_ma_tab"
        window.show()
        app.processEvents()
        window.left_navigation.button_for_key("recommendation").click()
        app.processEvents()
        view = window.technical_official_ma_research_view
        source_tabs = window.recommendation_view.result_source_tabs
        tab_index = source_tabs.indexOf(view)
        if tab_index < 0 or not source_tabs.isVisible():
            raise AssertionError("完整 MainWindow 四均線真 tab 不可見")
        tab_rect = source_tabs.tabBar().tabRect(tab_index)
        if tab_rect.isEmpty():
            raise AssertionError("完整 MainWindow 四均線 tab 沒有可操作區域")
        QTest.mouseClick(source_tabs.tabBar(), Qt.MouseButton.LeftButton, pos=tab_rect.center())
        app.processEvents()
        if source_tabs.currentWidget() is not view:
            raise AssertionError("真 tab 點擊未切換至四均線研究頁")

        receipt["phase"] = "catalog_and_initial_exact_open"
        events: list[tuple[str, bool]] = []
        view.operationSettled.connect(lambda kind, ok: events.append((str(kind), bool(ok))))
        _wait_view_operation(
            app,
            view,
            events,
            view.refresh_catalog_button.click,
            "盤點保存來源清單",
            journey_deadline,
        )
        if len(view._catalog_entries) != 1:
            raise AssertionError(f"固定來源候選數不符：{len(view._catalog_entries)}")
        catalog_item = view.catalog_list.item(0)
        catalog_rect = view.catalog_list.visualItemRect(catalog_item)
        if catalog_rect.isEmpty():
            raise AssertionError("來源候選未顯示於真 MainWindow")
        QTest.mouseClick(view.catalog_list.viewport(), Qt.MouseButton.LeftButton, pos=catalog_rect.center())
        for scope, checkbox in view.scope_checks.items():
            checkbox.setChecked(scope == "included_processed")
        view.page_size_box.setValue(100)
        _wait_view_operation(
            app,
            view,
            events,
            view.open_candidate_button.click,
            "核驗並執行全母體查詢",
            journey_deadline,
        )
        query = view.current_query
        initial_page = view.current_page
        if query is None or initial_page is None or view.current_result is None:
            raise AssertionError("初次 exact-open 未建立完整 MA result/page")
        if (
            query.f17_query.bundle_identity_sha256 != source.identity_sha256
            or view.current_result.counts.declared_count != 258
            or len(read_calls) != 1
        ):
            raise AssertionError("初次 exact-open source/count/read-call 不符")

        receipt["phase"] = "cross_page_select_and_compare_basket"
        _click_stock(app, view, "1000")
        view.add_comparison_button.click()
        app.processEvents()
        if tuple(item.stock_code for item in view.comparison_basket) != ("1000",):
            raise AssertionError("第一股未加入 MA 比較籃")
        _wait_view_operation(
            app,
            view,
            events,
            view.next_page_button.click,
            "讀取全域排序中的指定頁",
            journey_deadline,
        )
        second_page = view.current_page
        if second_page is None or second_page.page_index != 1:
            raise AssertionError("完整 MainWindow 未載入第二頁")
        _click_stock(app, view, "1100")
        view.add_comparison_button.click()
        app.processEvents()
        if tuple((item.stock_code, item.page_index) for item in view.comparison_basket) != (
            ("1000", 0), ("1100", 1),
        ):
            raise AssertionError("完整 MainWindow 跨頁比較籃不符")

        receipt["phase"] = "prepare_and_save_ma_bookmark"
        prepared: list[DailyMarketTechnicalOfficialDispositionMaBookmarkV1] = []

        def capture_bookmark(value: object) -> None:
            if type(value) is not DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
                raise AssertionError("MainWindow bookmarkPrepared 未提供 MA typed DTO")
            prepared.append(cast(DailyMarketTechnicalOfficialDispositionMaBookmarkV1, value))

        view.bookmarkPrepared.connect(capture_bookmark)
        selected_page_identity = view.current_page.page_identity_sha256
        selected_query_identity = view.current_query.query_identity_sha256
        view.bookmark_button.click()
        app.processEvents()
        if len(prepared) != 1:
            raise AssertionError("完整 MainWindow 沒收到 MA bookmarkPrepared")
        bookmark = prepared[0]
        if (
            bookmark.query.query_identity_sha256 != selected_query_identity
            or bookmark.selected.stock_code != "1100"
            or bookmark.selected.page_identity_sha256 != selected_page_identity
            or tuple((item.stock_code, item.page_index) for item in bookmark.comparison_selections)
            != (("1000", 0), ("1100", 1))
        ):
            raise AssertionError("bookmark 未保存原 query／頁／跨頁比較籃")
        bookmark_bytes = bookmark.to_json().encode("utf-8")
        bookmark_path = attempt / "saved_ma_bookmark.json"
        with open(to_internal_io_path(bookmark_path), "wb") as stream:
            stream.write(bookmark_bytes)
        bookmark_json_sha = hashlib.sha256(bookmark_bytes).hexdigest()
        watchlist_view = cast(WatchlistView, window.watchlist_view)
        _wait_for(
            app,
            lambda: not cast(set[object], getattr(window, "_technical_official_bookmark_workers", set()))
            and watchlist_view.stocks_model is not None
            and any(
                str(row.get("source_id", "")) == bookmark.bookmark_id
                for _, row in watchlist_view.stocks_model.getDataFrame().iterrows()
            ),
            deadline=min(journey_deadline, time.monotonic() + _OPERATION_DEADLINE_SECONDS),
            failure="Watchlist 收藏 worker／更新清單逾時",
        )
        stored = window.watchlist_service.get_research_bookmark(bookmark.bookmark_id)
        if type(stored) is not DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
            raise AssertionError("MainWindow Watchlist 未保存 typed MA bookmark")
        if stored.to_json() != bookmark.to_json():
            raise AssertionError("Watchlist 保存 bytes 與原 MA bookmark 不一致")
        row_index = _bookmark_row(watchlist_view, bookmark.bookmark_id)
        if watchlist_primary is None or not watchlist_primary.is_file():
            raise AssertionError("隔離 Watchlist primary 未建立")
        watchlist_sha_after_save = _sha256_file(watchlist_primary)
        receipt["watchlist_primary_sha256_after_save"] = watchlist_sha_after_save
        receipt["bookmark_identity_sha256"] = bookmark.bookmark_id
        receipt["bookmark_json_sha256"] = bookmark_json_sha
        receipt["bookmark_bytes"] = len(bookmark_bytes)
        receipt["exact_read_calls_after_initial_open"] = len(read_calls)
        if len(read_calls) != 1:
            raise AssertionError("bookmark save 意外重開來源")

        receipt["phase"] = "real_watchlist_signal_fresh_restore"
        generic_routes: list[str] = []
        watchlist_view.stockAnalysisRequested.connect(
            lambda *_args: generic_routes.append("stockAnalysisRequested")
        )
        watchlist_view.stockResearchRequested.connect(
            lambda *_args: generic_routes.append("stockResearchRequested")
        )
        watchlist_view.latestResearchRequested.connect(
            lambda *_args: generic_routes.append("latestResearchRequested")
        )
        events_before_restore = len(events)
        watchlist_model = watchlist_view.stocks_model
        if watchlist_model is None:
            raise AssertionError("Watchlist model 在保存後遺失")
        table_index = watchlist_model.index(row_index, 0)
        watchlist_view.stocks_table.scrollTo(table_index)
        app.processEvents()
        row_rect = watchlist_view.stocks_table.visualRect(table_index)
        if row_rect.isEmpty():
            raise AssertionError("剛保存的 MA bookmark 未出現在真 Watchlist 可見列")
        QTest.mouseClick(
            watchlist_view.stocks_table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=row_rect.center(),
        )
        app.processEvents()
        if not watchlist_view.stock_analysis_btn.isEnabled():
            raise AssertionError("Watchlist typed open control 未啟用")
        watchlist_view.stock_analysis_btn.click()
        restore_deadline = min(journey_deadline, time.monotonic() + _OPERATION_DEADLINE_SECONDS)
        _wait_for(
            app,
            lambda: len(events) > events_before_restore
            and view.active_worker is None
            and not view._has_running_worker(),
            deadline=restore_deadline,
            failure="Watchlist signal 未完成 MA fresh restore",
        )
        if len(read_calls) != 2:
            raise AssertionError(f"expected one initial plus one restore exact-open, got {len(read_calls)}")
        restored_query = view.current_query
        restored_page = view.current_page
        current = view.results_table.currentIndex()
        restored_row = view.results_model.row_at(current.row()) if current.isValid() else None
        if (
            generic_routes
            or restored_query is None
            or restored_page is None
            or restored_query.to_json() != bookmark.query.to_json()
            or restored_page.page_index != bookmark.selected.page_index
            or restored_page.request_identity_sha256 != bookmark.selected.page_request_identity_sha256
            or restored_row is None
            or restored_row.stock_code != bookmark.selected.stock_code
            or tuple((item.stock_code, item.page_index) for item in view.comparison_basket)
            != (("1000", 0), ("1100", 1))
            or window.recommendation_view.result_source_tabs.currentWidget() is not view
            or window.left_navigation.current_key() != "recommendation"
        ):
            raise AssertionError("MainWindow MA fresh restore 未原子還原 query/page/selection/basket")
        if _sha256_file(watchlist_primary) != watchlist_sha_after_save:
            raise AssertionError("Watchlist restore 改寫了保存 primary")
        receipt["restored_query_identity_sha256"] = restored_query.query_identity_sha256
        receipt["restored_page_identity_sha256"] = restored_page.page_identity_sha256
        receipt["restored_selected_stock_code"] = restored_row.stock_code
        receipt["restored_comparison_codes"] = [item.stock_code for item in view.comparison_basket]
        receipt["generic_fallback_events"] = generic_routes
        receipt["exact_read_calls_before_close"] = len(read_calls)

        if network_attempts:
            raise AssertionError(f"隔離 journey 嘗試連網：{network_attempts}")
        if any(
            not Path(item).is_relative_to(paths["application_root"].resolve())
            for item in sqlite_paths
            if item not in {":memory:", "file::memory:"}
        ):
            raise AssertionError("SQLite 連線紀錄含隔離根以外的路徑")
        receipt["sqlite_connect_paths"] = sqlite_paths
        receipt["network_attempts"] = network_attempts
        phases.append("startup/open/save/typed-watchlist-fresh-restore-passed")
    except BaseException as exc:
        failed = exc
        receipt["status"] = "failed"
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)[:2000]
        _write_json(receipt_path, receipt)
        raise
    finally:
        if window is not None and app is not None:
            receipt["phase"] = "normal_mainwindow_shutdown"
            cleanup_ok = _close_mainwindow(
                app,
                window,
                min(total_deadline, time.monotonic() + _CLEANUP_DEADLINE_SECONDS),
            )
            receipt["shutdown_close_requested"] = bool(getattr(window, "_shutdown_close_requested", False))
            receipt["shutdown_finalizing"] = bool(getattr(window, "_shutdown_close_finalizing", False))
            receipt["running_task_workers_after_close"] = len(running_task_workers())
        try:
            after_inventory, after_tree_sha = _tree_inventory(source.source_roots)
            after_manifest_sha = _sha256_file(source_manifest)
            receipt["source_inventory_after"] = after_inventory
            receipt["source_tree_sha256_after"] = after_tree_sha
            receipt["manifest_sha256_after"] = after_manifest_sha
            receipt["source_unchanged"] = (
                after_tree_sha == before_tree_sha
                and after_manifest_sha == source.manifest_sha256
            )
        except BaseException as post_exc:
            receipt["post_inventory_error"] = f"{type(post_exc).__name__}:{str(post_exc)[:1000]}"
            receipt["source_unchanged"] = False
            cleanup_ok = False
        receipt["exact_read_calls"] = read_calls
        receipt["network_attempts"] = network_attempts
        receipt["sqlite_connect_paths"] = sqlite_paths
        receipt["watchlist_primary_path"] = str(watchlist_primary) if watchlist_primary else None
        receipt["bookmark_json_sha256"] = bookmark_json_sha
        receipt["cleanup_native_workers_terminal"] = cleanup_ok
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if time.monotonic() > total_deadline:
            receipt["total_deadline_exceeded"] = True
            cleanup_ok = False
        if failed is None and cleanup_ok and receipt.get("source_unchanged") is True:
            receipt["status"] = "passed"
            receipt["phase"] = "complete"
        else:
            receipt["status"] = "failed"
        _write_json(receipt_path, receipt)
        if failed is None and receipt["status"] != "passed":
            raise AssertionError("MainWindow 正常關閉、來源不變或總期限驗證失敗")
    print(f"MA full MainWindow startup receipt: {receipt_path}")
