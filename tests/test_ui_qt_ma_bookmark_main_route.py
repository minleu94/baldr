"""以固定合成保存來源驗證 MA 收藏的 Main／觀察清單路由。

此測試呼叫 MainWindow 的實際保存與重開方法，但以最小 QMainWindow shell
承載它們；不代表完整 MainWindow 啟動驗收，也不呼叫 producer 或 latest。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from types import SimpleNamespace
from typing import Callable, Protocol, cast

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
)
from app_module.daily_market_technical_official_disposition_ma_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE,
    DailyMarketTechnicalOfficialDispositionMaBookmarkV1,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.watchlist_service import WatchlistService, decode_daily_market_research_bookmark
from ui_qt.main import MainWindow, apply_app_theme
from ui_qt.views.daily_market_technical_official_disposition_ma_view import (
    DailyMarketTechnicalOfficialDispositionMaView,
)
from ui_qt.views.watchlist_view import WatchlistView


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_QA_ROOT = _REPOSITORY_ROOT / "output" / "qa" / "ma_bookmark_main_route_20261008_a"
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
_TOTAL_DEADLINE_SECONDS = 300
_OPERATION_DEADLINE_SECONDS = 180


@dataclass(frozen=True, slots=True)
class _BundleSource:
    root: Path
    identity_sha256: str
    manifest_sha256: str
    expected_tree_sha256: str | None
    origin: str


class _FixtureReference(Protocol):
    bundle_identity_sha256: str
    manifest_sha256: str


class _BundleFixture(Protocol):
    qa_root: Path
    bundle_root: Path
    reference: _FixtureReference


class _MainRouteHost(MainWindow):
    """不啟動 MainWindow constructor、僅承載其真 route methods 的最小 shell。"""

    watchlist_service: WatchlistService
    watchlist_view: WatchlistView
    technical_official_ma_research_view: DailyMarketTechnicalOfficialDispositionMaView
    recommendation_view: SimpleNamespace
    _shutdown_close_requested: bool
    _technical_official_bookmark_workers: set[object]

    def __init__(self) -> None:
        # 僅執行 Qt 基底建構；刻意不呼叫會建立正式服務的 MainWindow.__init__。
        QMainWindow.__init__(self)

    def closeEvent(self, event) -> None:
        QMainWindow.closeEvent(self, event)


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


def _bundle_source(request: pytest.FixtureRequest) -> _BundleSource:
    configured = {key: os.environ.get(key) for key in _SOURCE_ENV_KEYS}
    present = tuple(value is not None for value in configured.values())
    if any(present):
        if not all(present):
            raise ValueError("ma_bookmark_route_incomplete_saved_bundle_environment")
        root_text = cast(str, configured[_SOURCE_ENV_KEYS[0]])
        if not Path(root_text).is_absolute():
            raise ValueError("ma_bookmark_route_bundle_root_must_be_absolute")
        identity = cast(str, configured[_SOURCE_ENV_KEYS[1]])
        manifest = cast(str, configured[_SOURCE_ENV_KEYS[2]])
        tree = cast(str, configured[_SOURCE_ENV_KEYS[3]])
        for label, value in (("identity", identity), ("manifest", manifest), ("tree", tree)):
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ValueError(f"ma_bookmark_route_invalid_{label}_sha256")
        return _BundleSource(Path(root_text), identity, manifest, tree, "explicit_saved_bundle")

    # 一般 CI 沒有本機保存來源時沿用既有真 bundle fixture；固定封套 QA 則必須
    # 傳入四個 pins，避免無意間重建來源。
    fixture = cast(_BundleFixture, request.getfixturevalue("bundle_fixture"))
    return _BundleSource(
        fixture.bundle_root,
        fixture.reference.bundle_identity_sha256,
        fixture.reference.manifest_sha256,
        None,
        "bundle_fixture_fallback",
    )


def _source_roots(source: _BundleSource) -> tuple[Path, ...]:
    manifest_path = source.root / "manifests" / f"{source.identity_sha256}.json"
    with open(to_internal_io_path(manifest_path), "r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    inventory = manifest.get("source_inventory")
    if not isinstance(inventory, dict) or set(inventory) != _SOURCE_INVENTORY_KEYS:
        raise ValueError("ma_bookmark_route_source_inventory_invalid")
    parents = inventory.get("technical_parent_roots")
    if not isinstance(parents, list) or not parents or any(not isinstance(item, str) for item in parents):
        raise ValueError("ma_bookmark_route_parent_roots_invalid")
    if len(source.root.parents) < 3:
        raise ValueError("ma_bookmark_route_bundle_root_shape_invalid")
    synthetic_root = Path(os.path.abspath(str(source.root.parents[2])))
    raw_roots = (
        inventory.get("technical_database"),
        inventory.get("technical_store_root"),
        *parents,
        inventory.get("market_assignment_root"),
        inventory.get("official_disposal_root"),
        str(source.root),
    )
    roots: list[Path] = []
    for raw in raw_roots:
        if not isinstance(raw, str):
            raise ValueError("ma_bookmark_route_source_root_invalid")
        path = Path(os.path.abspath(raw))
        try:
            path.relative_to(synthetic_root)
        except ValueError as exc:
            raise ValueError("ma_bookmark_route_source_outside_synthetic_root") from exc
        if not os.path.lexists(to_internal_io_path(path)):
            raise FileNotFoundError("ma_bookmark_route_source_root_missing")
        current = path
        while True:
            info = os.lstat(to_internal_io_path(current))
            if _is_reparse(info):
                raise ValueError("ma_bookmark_route_source_reparse")
            if current == current.parent:
                break
            current = current.parent
        if path not in roots:
            roots.append(path)
    if "synthetic" not in synthetic_root.name.casefold():
        raise ValueError("ma_bookmark_route_source_root_not_marked_synthetic")
    return tuple(roots)


def _tree_signature(path: Path) -> tuple[tuple[str, int, int, str], ...]:
    io_root = to_internal_io_path(path)
    info = os.lstat(io_root)
    if _is_reparse(info):
        raise ValueError("ma_bookmark_route_inventory_reparse")
    if stat.S_ISREG(info.st_mode):
        return ((path.name, info.st_size, info.st_mtime_ns, _sha256_file(path)),)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("ma_bookmark_route_inventory_root_type")
    entries: list[tuple[str, int, int, str]] = []
    total_bytes = 0
    for directory, directory_names, file_names in os.walk(io_root, followlinks=False):
        for name in tuple(directory_names):
            child = os.path.join(directory, name)
            child_info = os.lstat(child)
            if _is_reparse(child_info) or not stat.S_ISDIR(child_info.st_mode):
                raise ValueError("ma_bookmark_route_inventory_directory")
        for name in file_names:
            child = os.path.join(directory, name)
            child_info = os.lstat(child)
            if _is_reparse(child_info) or not stat.S_ISREG(child_info.st_mode):
                raise ValueError("ma_bookmark_route_inventory_file")
            digest = hashlib.sha256()
            with open(child, "rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            relative = os.path.relpath(child, io_root).replace("\\", "/")
            entries.append((relative, child_info.st_size, child_info.st_mtime_ns, digest.hexdigest()))
            total_bytes += child_info.st_size
            if len(entries) > 100_000 or total_bytes > 64 * 1024 * 1024:
                raise ValueError("ma_bookmark_route_inventory_budget")
    return tuple(sorted(entries))


def _tree_inventory(roots: tuple[Path, ...]) -> tuple[list[dict[str, object]], str]:
    records: list[dict[str, object]] = []
    total_bytes = 0
    for root in roots:
        signature = _tree_signature(root)
        total_bytes += sum(item[1] for item in signature)
        root_bytes = sum(item[1] for item in signature)
        records.append({
            "root": str(root),
            "file_count": len(signature),
            "total_bytes": root_bytes,
            "files_sha256": hashlib.sha256(
                json.dumps(signature, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        })
    if total_bytes > 64 * 1024 * 1024:
        raise ValueError("ma_bookmark_route_inventory_total_byte_budget")
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return records, hashlib.sha256(encoded).hexdigest()


def _new_attempt() -> Path:
    _QA_ROOT.mkdir(parents=True, exist_ok=True)
    attempt = _QA_ROOT / f"attempt_{time.time_ns()}_{os.getpid()}"
    os.mkdir(to_internal_io_path(attempt))
    return attempt


def _write_json(path: Path, payload: object) -> None:
    with open(to_internal_io_path(path), "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    apply_app_theme(instance)
    return instance


def _wait_view_operation(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
    events: list[tuple[str, bool]],
    action: Callable[[], object],
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
                    f"ma_bookmark_route_operation_failed:{kind}:{success}:{view.status_label.text()}"
                )
            break
        time.sleep(0.01)
    else:
        raise TimeoutError(f"ma_bookmark_route_operation_timeout:{expected_kind}")
    while time.monotonic() < deadline:
        app.processEvents()
        if view.active_worker is None and not view._has_running_worker():
            return
        time.sleep(0.01)
    raise TimeoutError(f"ma_bookmark_route_native_worker_timeout:{expected_kind}")


def _click_ma_code(app: QApplication, view: DailyMarketTechnicalOfficialDispositionMaView, code: str) -> None:
    index = view.results_model.index_for_stock(code)
    if not index.isValid():
        raise AssertionError(f"ma_bookmark_route_stock_not_on_page:{code}")
    rect = view.results_table.visualRect(index)
    if not rect.isValid() or rect.isEmpty():
        raise AssertionError(f"ma_bookmark_route_stock_not_visible:{code}")
    QTest.mouseClick(view.results_table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    app.processEvents()
    current = view.results_table.currentIndex()
    row = view.results_model.row_at(current.row()) if current.isValid() else None
    if row is None or row.stock_code != code:
        raise AssertionError(f"ma_bookmark_route_stock_selection_mismatch:{code}")


def _wait_watchlist_save(
    app: QApplication,
    host: QMainWindow,
    watchlist: WatchlistView,
    bookmark_id: str,
    deadline: float,
) -> None:
    while time.monotonic() < deadline:
        app.processEvents()
        workers = cast(set[object], getattr(host, "_technical_official_bookmark_workers", set()))
        if not workers:
            saved = watchlist.watchlist_service.get_research_bookmark(bookmark_id)
            if saved is not None and watchlist.stocks_model is not None:
                frame = watchlist.stocks_model.getDataFrame()
                if "source_id" in frame.columns and any(
                    str(value) == bookmark_id for value in frame["source_id"].tolist()
                ):
                    return
        time.sleep(0.01)
    raise TimeoutError("ma_bookmark_route_watchlist_save_timeout")


def test_real_main_methods_save_and_reopen_typed_ma_watchlist_route(
    app: QApplication,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """經真 typed Main／Watchlist 路徑保存並 fresh 重開，不做完整 Main startup 驗收。"""

    source = _bundle_source(request)
    attempt = _new_attempt()
    receipt_path = attempt / "route_receipt.json"
    bookmark_path = attempt / "saved_ma_bookmark.json"
    bundle_root = source.root
    manifest_path = bundle_root / "manifests" / f"{source.identity_sha256}.json"
    receipt: dict[str, object] = {
        "schema": "ma-bookmark-main-route-receipt.v1",
        "status": "running",
        "acceptance_scope": "actual MainWindow methods in minimal QMainWindow shell; not full MainWindow startup",
        "bundle_origin": source.origin,
        "bundle_fixture_factory_used": source.origin == "bundle_fixture_fallback",
        "producer_invoked_by_test_after_source_resolution": False,
        "source_generation_note": (
            "explicit saved bundle pins; no producer invoked"
            if source.origin == "explicit_saved_bundle"
            else "standard CI fallback may create its existing isolated synthetic bundle fixture"
        ),
        "bundle_root": str(bundle_root),
        "bundle_identity_sha256": source.identity_sha256,
        "exact_read_calls": 0,
        "bookmark_json_path": str(bookmark_path),
        "phase": "preflight",
        "phases": [],
    }
    _write_json(receipt_path, receipt)
    try:
        before_manifest = _sha256_file(manifest_path)
        if before_manifest != source.manifest_sha256:
            raise AssertionError("ma_bookmark_route_manifest_pin_mismatch")
        source_roots = _source_roots(source)
        before_inventory, before_tree_sha = _tree_inventory(source_roots)
        receipt["manifest_sha256_before"] = before_manifest
        receipt["source_tree_sha256_before"] = before_tree_sha
        receipt["source_inventory_before"] = before_inventory
        _write_json(receipt_path, receipt)
        if source.expected_tree_sha256 is not None and before_tree_sha != source.expected_tree_sha256:
            raise AssertionError("ma_bookmark_route_source_tree_pin_mismatch")
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)[:2000]
        _write_json(receipt_path, receipt)
        raise
    _write_json(receipt_path, receipt)

    exact_read_calls = 0
    original_read_exact = DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact

    def counted_read_exact(self, *args, **kwargs):
        nonlocal exact_read_calls
        exact_read_calls += 1
        receipt["exact_read_calls"] = exact_read_calls
        _write_json(receipt_path, receipt)
        return original_read_exact(self, *args, **kwargs)

    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        "read_exact",
        counted_read_exact,
    )

    initial: DailyMarketTechnicalOfficialDispositionMaView | None = None
    destination: DailyMarketTechnicalOfficialDispositionMaView | None = None
    watchlist_view: WatchlistView | None = None
    host: QMainWindow | None = None
    failed: BaseException | None = None
    started = time.monotonic()
    total_deadline = started + _TOTAL_DEADLINE_SECONDS
    try:
        initial = DailyMarketTechnicalOfficialDispositionMaView(bundle_root)
        destination = DailyMarketTechnicalOfficialDispositionMaView()
        tabs = QTabWidget()
        tabs.addTab(initial, "原始研究")
        tabs.addTab(destination, "收藏重開")
        route_host = _MainRouteHost()
        host = route_host
        route_host.setCentralWidget(tabs)
        route_host._shutdown_close_requested = False
        route_host._technical_official_bookmark_workers = set()
        route_host.technical_official_ma_research_view = initial
        route_host.recommendation_view = SimpleNamespace(result_source_tabs=tabs)

        output_root = attempt / "isolated_watchlist_output"
        service = WatchlistService(SimpleNamespace(
            output_root=output_root,
            resolve_output_path=lambda name: output_root / name,
        ))
        watchlist_view = WatchlistView(service, config=None)
        route_host.watchlist_service = service
        route_host.watchlist_view = watchlist_view
        initial.resize(1000, 900)
        destination.resize(1000, 900)
        host.resize(1000, 900)
        watchlist_view.resize(900, 650)
        host.show()
        watchlist_view.show()
        app.processEvents()

        events: list[tuple[str, bool]] = []
        initial.operationSettled.connect(lambda kind, ok: events.append((str(kind), bool(ok))))
        receipt["phase"] = "catalog"
        _wait_view_operation(
            app, initial, events, initial.refresh_catalog_button.click,
            "盤點保存來源清單", total_deadline,
        )
        if len(initial._catalog_entries) != 1:
            raise AssertionError(f"ma_bookmark_route_expected_one_catalog_entry:{len(initial._catalog_entries)}")
        candidate = initial.catalog_list.item(0)
        rect = initial.catalog_list.visualItemRect(candidate)
        if not rect.isValid() or rect.isEmpty():
            raise AssertionError("ma_bookmark_route_catalog_candidate_not_visible")
        QTest.mouseClick(initial.catalog_list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        for scope, checkbox in initial.scope_checks.items():
            checkbox.setChecked(scope == "included_processed")
        initial.page_size_box.setValue(100)
        app.processEvents()
        receipt["phase"] = "initial_exact_open"
        _wait_view_operation(
            app, initial, events, initial.open_candidate_button.click,
            "核驗並執行全母體查詢", total_deadline,
        )
        query = initial.current_query
        page_zero = initial.current_page
        if query is None or page_zero is None or initial.current_result is None:
            raise AssertionError("ma_bookmark_route_initial_exact_result_missing")
        if query.f17_query.bundle_identity_sha256 != source.identity_sha256:
            raise AssertionError("ma_bookmark_route_initial_bundle_identity_mismatch")
        if exact_read_calls != 1:
            raise AssertionError(f"ma_bookmark_route_initial_exact_open_count:{exact_read_calls}")
        _click_ma_code(app, initial, "1000")
        initial.add_comparison_button.click()
        app.processEvents()
        if tuple(item.stock_code for item in initial.comparison_basket) != ("1000",):
            raise AssertionError("ma_bookmark_route_first_comparison_not_added")
        receipt["phase"] = "second_page"
        _wait_view_operation(
            app, initial, events, initial.next_page_button.click,
            "讀取全域排序中的指定頁", total_deadline,
        )
        page_one = initial.current_page
        if page_one is None or page_one.page_index != 1:
            raise AssertionError("ma_bookmark_route_second_page_missing")
        _click_ma_code(app, initial, "1100")
        initial.add_comparison_button.click()
        app.processEvents()
        if tuple((item.stock_code, item.page_index) for item in initial.comparison_basket) != (
            ("1000", 0), ("1100", 1),
        ):
            raise AssertionError("ma_bookmark_route_cross_page_comparison_mismatch")

        prepared: list[DailyMarketTechnicalOfficialDispositionMaBookmarkV1] = []
        save_slot_errors: list[BaseException] = []

        def persist_then_call_main(value: object) -> None:
            try:
                if type(value) is not DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
                    raise AssertionError("ma_bookmark_route_main_save_input_not_typed")
                bookmark_value = cast(DailyMarketTechnicalOfficialDispositionMaBookmarkV1, value)
                bookmark_bytes = bookmark_value.to_json().encode("utf-8")
                with open(to_internal_io_path(bookmark_path), "wb") as stream:
                    stream.write(bookmark_bytes)
                prepared.append(bookmark_value)
                receipt["bookmark_json_sha256"] = hashlib.sha256(bookmark_bytes).hexdigest()
                receipt["bookmark_identity_sha256"] = bookmark_value.bookmark_id
                receipt["bookmark_bytes"] = len(bookmark_bytes)
                receipt["phase"] = "bookmark_json_saved_before_main_service"
                _write_json(receipt_path, receipt)
                # JSON 與 source/query pins 先落 QA，再由真 Main 方法啟動保存 worker。
                route_host._save_technical_official_bookmark(bookmark_value)
            except BaseException as exc:
                save_slot_errors.append(exc)

        initial.bookmarkPrepared.connect(persist_then_call_main)
        initial.bookmark_button.click()
        app.processEvents()
        if save_slot_errors:
            raise save_slot_errors[0]
        if not prepared:
            raise AssertionError("ma_bookmark_route_bookmark_signal_missing")
        bookmark = prepared[-1]
        bookmark_json = bookmark.to_json()
        persisted_bookmark = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json(
            bookmark_path.read_bytes()
        )
        if (
            persisted_bookmark.bookmark_id != bookmark.bookmark_id
            or persisted_bookmark.query.query_identity_sha256 != query.query_identity_sha256
            or persisted_bookmark.selected.stock_code != "1100"
            or tuple((item.stock_code, item.page_index) for item in persisted_bookmark.comparison_selections)
            != (("1000", 0), ("1100", 1))
        ):
            raise AssertionError("ma_bookmark_route_saved_json_did_not_preserve_origin")
        receipt["initial_query_identity_sha256"] = query.query_identity_sha256
        receipt["initial_page_identity_sha256"] = page_one.page_identity_sha256
        receipt["initial_comparison_codes"] = [item.stock_code for item in initial.comparison_basket]
        receipt["phase"] = "bookmark_json_saved_and_main_save_started"
        _write_json(receipt_path, receipt)

        # 上方 bookmarkPrepared slot 已呼叫實際 MainWindow method 並啟動真 worker。
        _wait_watchlist_save(app, route_host, watchlist_view, bookmark.bookmark_id, total_deadline)
        saved = service.get_research_bookmark(bookmark.bookmark_id)
        if type(saved) is not DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
            raise AssertionError("ma_bookmark_route_watchlist_did_not_store_typed_bookmark")
        if saved.to_json() != bookmark_json:
            raise AssertionError("ma_bookmark_route_watchlist_bytes_changed_bookmark")
        primary = service.default_watchlist_file
        watchlist_primary_sha256 = _sha256_file(primary)
        receipt["watchlist_primary_path"] = str(primary)
        receipt["watchlist_primary_sha256_after_save"] = watchlist_primary_sha256
        receipt["exact_reads_before_restore"] = exact_read_calls
        receipt["phase"] = "watchlist_saved_and_refreshed"
        _write_json(receipt_path, receipt)

        if watchlist_view.stocks_model is None:
            raise AssertionError("ma_bookmark_route_watchlist_model_missing")
        frame = watchlist_view.stocks_model.getDataFrame()
        matching = [
            index for index, row in frame.iterrows()
            if str(row.get("source_id", "")) == bookmark.bookmark_id
        ]
        if len(matching) != 1:
            raise AssertionError(f"ma_bookmark_route_watchlist_exact_row_count:{len(matching)}")
        saved_row = frame.loc[matching[0]]
        decoded_row_bookmark = decode_daily_market_research_bookmark(
            saved_row.get("research_bookmark")
        )
        if (
            saved_row.get("source") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE
            or type(decoded_row_bookmark) is not DailyMarketTechnicalOfficialDispositionMaBookmarkV1
            or decoded_row_bookmark.bookmark_id != bookmark.bookmark_id
        ):
            raise AssertionError("ma_bookmark_route_watchlist_row_not_in_typed_namespace")
        table = watchlist_view.stocks_table
        index = watchlist_view.stocks_model.index(int(matching[0]), 0)
        table.scrollTo(index)
        app.processEvents()
        row_rect = table.visualRect(index)
        if not row_rect.isValid() or row_rect.isEmpty():
            raise AssertionError("ma_bookmark_route_watchlist_row_not_visible")
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=row_rect.center())
        app.processEvents()
        if not watchlist_view.stock_analysis_btn.isEnabled():
            raise AssertionError("ma_bookmark_route_watchlist_open_button_disabled")

        generic_routes: list[str] = []
        watchlist_view.stockAnalysisRequested.connect(lambda *_args: generic_routes.append("stockAnalysisRequested"))
        watchlist_view.stockResearchRequested.connect(lambda *_args: generic_routes.append("stockResearchRequested"))
        watchlist_view.latestResearchRequested.connect(lambda *_args: generic_routes.append("latestResearchRequested"))
        watchlist_view.technicalOfficialBookmarkReady.connect(
            lambda *_args: generic_routes.append("technicalOfficialBookmarkReady")
        )
        watchlist_view.technicalBookmarkStateReady.connect(
            lambda *_args: generic_routes.append("technicalBookmarkStateReady")
        )
        watchlist_view.technicalPriceBookmarkStateReady.connect(
            lambda *_args: generic_routes.append("technicalPriceBookmarkStateReady")
        )
        routed_bookmarks: list[object] = []
        restored_events: list[tuple[str, bool]] = []
        destination.operationSettled.connect(
            lambda kind, ok: restored_events.append((str(kind), bool(ok)))
        )
        route_host.technical_official_ma_research_view = destination
        tabs.setCurrentWidget(destination)
        watchlist_view.technicalOfficialMaBookmarkReady.connect(
            route_host._open_technical_official_ma_bookmark
        )
        watchlist_view.technicalOfficialMaBookmarkReady.connect(routed_bookmarks.append)
        receipt["phase"] = "watchlist_special_route_and_fresh_restore"
        before_restore_reads = exact_read_calls
        _wait_view_operation(
            app, destination, restored_events,
            watchlist_view.stock_analysis_btn.click,
            "重開四均線研究收藏", total_deadline,
        )
        if len(routed_bookmarks) != 1 or type(routed_bookmarks[-1]) is not DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
            raise AssertionError("ma_bookmark_route_special_signal_not_typed")
        routed = cast(DailyMarketTechnicalOfficialDispositionMaBookmarkV1, routed_bookmarks[-1])
        restored_query = destination.current_query
        restored_page = destination.current_page
        current = destination.results_table.currentIndex()
        selected = destination.results_model.row_at(current.row()) if current.isValid() else None
        restored_basket = destination.comparison_basket
        if (
            generic_routes
            or routed.bookmark_id != bookmark.bookmark_id
            or restored_query is None
            or restored_query.to_json() != bookmark.query.to_json()
            or restored_page is None
            or restored_page.page_index != bookmark.selected.page_index
            or restored_page.request_identity_sha256 != bookmark.selected.page_request_identity_sha256
            or selected is None
            or selected.stock_code != bookmark.selected.stock_code
            or tuple(item.to_dict() for item in restored_basket)
            != tuple(item.to_dict() for item in bookmark.comparison_selections)
            or before_restore_reads != 1
            or exact_read_calls != before_restore_reads + 1
            or tabs.currentWidget() is not destination
        ):
            raise AssertionError("ma_bookmark_route_fresh_restore_did_not_preserve_exact_state")
        receipt["restore_exact_read_calls"] = exact_read_calls - before_restore_reads
        receipt["restored_query_identity_sha256"] = restored_query.query_identity_sha256
        receipt["restored_page_identity_sha256"] = restored_page.page_identity_sha256
        receipt["restored_selected_code"] = selected.stock_code
        receipt["restored_comparison_codes"] = [item.stock_code for item in restored_basket]
        receipt["generic_fallback_events"] = list(generic_routes)
        receipt["phase"] = "route_assertions_passed"
        _write_json(receipt_path, receipt)
    except BaseException as exc:
        failed = exc
        receipt["status"] = "failed"
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)[:2000]
        _write_json(receipt_path, receipt)
        raise
    finally:
        cleanup_ok = True
        for view in (initial, destination):
            if view is None:
                continue
            try:
                view.cancel_current_operation()
                cleanup_deadline = time.monotonic() + 20
                while time.monotonic() < cleanup_deadline:
                    app.processEvents()
                    if view.begin_shutdown():
                        view.close()
                        break
                    time.sleep(0.01)
                else:
                    cleanup_ok = False
            except BaseException:
                cleanup_ok = False
        if watchlist_view is not None:
            try:
                if not watchlist_view.begin_shutdown():
                    cleanup_ok = False
                watchlist_view.close()
            except BaseException:
                cleanup_ok = False
        if host is not None:
            try:
                workers = cast(set[object], getattr(host, "_technical_official_bookmark_workers", set()))
                if any(bool(getattr(worker, "isRunning")()) for worker in workers):
                    cleanup_ok = False
                host.close()
                app.processEvents()
            except BaseException:
                cleanup_ok = False
        try:
            after_manifest = _sha256_file(manifest_path)
            after_inventory, after_tree_sha = _tree_inventory(source_roots)
            receipt["manifest_sha256_after"] = after_manifest
            receipt["source_tree_sha256_after"] = after_tree_sha
            receipt["source_inventory_after"] = after_inventory
            receipt["source_unchanged"] = (
                after_manifest == source.manifest_sha256 and after_tree_sha == before_tree_sha
            )
        except BaseException as post_exc:
            cleanup_ok = False
            receipt["post_inventory_error"] = f"{type(post_exc).__name__}:{str(post_exc)[:1000]}"
            receipt["source_unchanged"] = False
        receipt["cleanup_native_workers_terminal"] = cleanup_ok
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if failed is None and cleanup_ok and receipt.get("source_unchanged") is True:
            receipt["status"] = "passed"
        else:
            receipt["status"] = "failed"
        _write_json(receipt_path, receipt)
        if failed is None and receipt["status"] != "passed":
            raise AssertionError("ma_bookmark_route_cleanup_or_source_postflight_failed")
    print(f"MA bookmark Main route receipt: {receipt_path}")
