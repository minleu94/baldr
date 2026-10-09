"""以既有合成保存來源驗證 MA/F17 視圖的端到端 UI 路徑。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
import traceback
from typing import Callable, Protocol, cast

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
    DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from app_module.daily_market_technical_official_disposition_ma_bookmark_v1 import (
    DailyMarketTechnicalOfficialDispositionMaBookmarkV1,
)
from app_module.daily_market_technical_official_disposition_ma_comparison_v1 import (
    DailyMarketTechnicalOfficialDispositionMaSelectionV1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
)
from app_module.personal_data_paths import to_internal_io_path
from ui_qt.main import apply_app_theme
import ui_qt.views.daily_market_technical_official_disposition_ma_view as view_module
import app_module.daily_market_technical_official_disposition_query_reader_v1 as query_reader_module
from ui_qt.views.daily_market_technical_official_disposition_ma_view import (
    DailyMarketTechnicalOfficialDispositionMaView,
    DailyMarketTechnicalOfficialDispositionMaViewComparisonV1,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ENVIRONMENT_KEYS = (
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
_QA_ROOT = _REPOSITORY_ROOT / "output" / "qa" / "ma_saved_source_ui_journey_20261008_a"
_TOTAL_DEADLINE_SECONDS = 300
_OPERATION_DEADLINE_SECONDS = 180


def _exception_chain(exc: BaseException) -> list[dict[str, str]]:
    chain: list[dict[str, str]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(chain) < 12:
        seen.add(id(current))
        item = {"type": type(current).__name__, "message": str(current)[:1000]}
        for attribute in ("code", "cause_code"):
            value = getattr(current, attribute, None)
            if isinstance(value, str):
                item[attribute] = value[:200]
        chain.append(item)
        current = current.__cause__ or current.__context__
    return chain


@dataclass(frozen=True, slots=True)
class _JourneyBundleSource:
    bundle_root: Path
    bundle_identity_sha256: str
    manifest_sha256: str
    expected_source_tree_sha256: str | None
    origin: str


class _BundleFixtureReference(Protocol):
    bundle_identity_sha256: str
    manifest_sha256: str


class _BundleFixtureLike(Protocol):
    bundle_root: Path
    reference: _BundleFixtureReference


def _parse_sha256_environment_value(name: str, value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"ma_saved_journey_invalid_sha256_environment:{name}")
    return value


def _journey_bundle_source(request: pytest.FixtureRequest) -> _JourneyBundleSource:
    configured = {name: os.environ.get(name) for name in _SOURCE_ENVIRONMENT_KEYS}
    present = tuple(value is not None for value in configured.values())
    if any(present):
        if not all(present):
            raise ValueError("ma_saved_journey_incomplete_bundle_environment")
        root_text = cast(str, configured[_SOURCE_ENVIRONMENT_KEYS[0]])
        root = Path(root_text)
        if not root.is_absolute():
            raise ValueError("ma_saved_journey_bundle_root_must_be_absolute")
        return _JourneyBundleSource(
            bundle_root=root,
            bundle_identity_sha256=_parse_sha256_environment_value(
                _SOURCE_ENVIRONMENT_KEYS[1],
                cast(str, configured[_SOURCE_ENVIRONMENT_KEYS[1]]),
            ),
            manifest_sha256=_parse_sha256_environment_value(
                _SOURCE_ENVIRONMENT_KEYS[2],
                cast(str, configured[_SOURCE_ENVIRONMENT_KEYS[2]]),
            ),
            expected_source_tree_sha256=_parse_sha256_environment_value(
                _SOURCE_ENVIRONMENT_KEYS[3],
                cast(str, configured[_SOURCE_ENVIRONMENT_KEYS[3]]),
            ),
            origin="explicit_saved_bundle_environment",
        )

    fixture = cast(_BundleFixtureLike, request.getfixturevalue("bundle_fixture"))
    return _JourneyBundleSource(
        bundle_root=fixture.bundle_root,
        bundle_identity_sha256=fixture.reference.bundle_identity_sha256,
        manifest_sha256=fixture.reference.manifest_sha256,
        expected_source_tree_sha256=None,
        origin="real_bundle_fixture_factory",
    )


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    apply_app_theme(instance)
    return instance


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


def _source_roots(bundle: _JourneyBundleSource) -> tuple[Path, ...]:
    manifest_path = bundle.bundle_root / "manifests" / f"{bundle.bundle_identity_sha256}.json"
    with open(to_internal_io_path(manifest_path), "r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    inventory = manifest.get("source_inventory")
    if not isinstance(inventory, dict) or set(inventory) != _SOURCE_INVENTORY_KEYS:
        raise ValueError("ma_saved_journey_source_inventory_invalid")
    parents = inventory.get("technical_parent_roots")
    if not isinstance(parents, list) or not parents or any(not isinstance(item, str) for item in parents):
        raise ValueError("ma_saved_journey_parent_roots_invalid")
    raw_roots = (
        inventory.get("technical_database"),
        inventory.get("technical_store_root"),
        *parents,
        inventory.get("market_assignment_root"),
        inventory.get("official_disposal_root"),
        str(bundle.bundle_root),
    )
    if len(bundle.bundle_root.parents) < 3:
        raise ValueError("ma_saved_journey_bundle_root_shape_invalid")
    synthetic_root = Path(os.path.abspath(str(bundle.bundle_root.parents[2])))
    roots: list[Path] = []
    for raw in raw_roots:
        if not isinstance(raw, str):
            raise ValueError("ma_saved_journey_source_root_invalid")
        path = Path(os.path.abspath(raw))
        try:
            path.relative_to(synthetic_root)
        except ValueError as exc:
            raise ValueError("ma_saved_journey_source_outside_synthetic_root") from exc
        io_path = to_internal_io_path(path)
        if not os.path.lexists(io_path):
            raise FileNotFoundError("ma_saved_journey_source_root_missing")
        current = path
        while True:
            info = os.lstat(to_internal_io_path(current))
            if _is_reparse(info):
                raise ValueError("ma_saved_journey_source_root_reparse")
            if current == current.parent:
                break
            current = current.parent
        if path not in roots:
            roots.append(path)
    return tuple(roots)


def _tree_signature(path: Path) -> tuple[tuple[str, int, int, str], ...]:
    io_root = to_internal_io_path(path)
    root_info = os.lstat(io_root)
    if _is_reparse(root_info):
        raise ValueError("ma_saved_journey_inventory_reparse")
    if stat.S_ISREG(root_info.st_mode):
        return ((path.name, root_info.st_size, root_info.st_mtime_ns, _sha256_file(path)),)
    if not stat.S_ISDIR(root_info.st_mode):
        raise ValueError("ma_saved_journey_inventory_not_regular")
    entries: list[tuple[str, int, int, str]] = []
    for directory, directory_names, file_names in os.walk(io_root, followlinks=False):
        for name in tuple(directory_names):
            info = os.lstat(os.path.join(directory, name))
            if _is_reparse(info) or not stat.S_ISDIR(info.st_mode):
                raise ValueError("ma_saved_journey_inventory_directory_invalid")
        for name in file_names:
            io_file = os.path.join(directory, name)
            info = os.lstat(io_file)
            if _is_reparse(info) or not stat.S_ISREG(info.st_mode):
                raise ValueError("ma_saved_journey_inventory_file_invalid")
            relative = os.path.relpath(io_file, io_root).replace("\\", "/")
            digest = hashlib.sha256()
            with open(io_file, "rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            entries.append((relative, info.st_size, info.st_mtime_ns, digest.hexdigest()))
            if len(entries) > 100_000:
                raise ValueError("ma_saved_journey_inventory_entry_budget")
    return tuple(sorted(entries))


def _tree_inventory(roots: tuple[Path, ...]) -> tuple[dict[str, object], str]:
    records: list[dict[str, object]] = []
    total_bytes = 0
    for root in roots:
        signature = _tree_signature(root)
        size = sum(item[1] for item in signature)
        total_bytes += size
        records.append(
            {
                "root": str(root),
                "file_count": len(signature),
                "total_bytes": size,
                "files_sha256": hashlib.sha256(
                    json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
            }
        )
    if total_bytes > 64 * 1024 * 1024:
        raise ValueError("ma_saved_journey_inventory_byte_budget")
    encoded = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"roots": records}, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    with open(to_internal_io_path(path), "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def _attempt_directory() -> Path:
    _QA_ROOT.mkdir(parents=True, exist_ok=True)
    attempt = _QA_ROOT / f"attempt_{time.time_ns()}_{os.getpid()}"
    os.mkdir(to_internal_io_path(attempt))
    return attempt


def _wait_for_operation(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
    events: list[tuple[str, bool]],
    *,
    expected_kind: str,
    start_index: int,
    total_deadline: float,
) -> None:
    deadline = min(total_deadline, time.monotonic() + _OPERATION_DEADLINE_SECONDS)
    while time.monotonic() < deadline:
        app.processEvents()
        if len(events) > start_index:
            kind, success = events[start_index]
            if kind != expected_kind or not success:
                raise AssertionError(f"unexpected UI operation result: {kind!r}, {success!r}")
            break
        time.sleep(0.01)
    else:
        raise TimeoutError(f"ma_saved_journey_operation_timeout:{expected_kind}")

    while time.monotonic() < deadline:
        app.processEvents()
        if view.active_worker is None and not view._has_running_worker():
            return
        time.sleep(0.01)
    raise TimeoutError(f"ma_saved_journey_native_worker_timeout:{expected_kind}")


def _run_operation(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
    events: list[tuple[str, bool]],
    action: Callable[[], object],
    *,
    expected_kind: str,
    total_deadline: float,
) -> None:
    start_index = len(events)
    action()
    _wait_for_operation(
        app,
        view,
        events,
        expected_kind=expected_kind,
        start_index=start_index,
        total_deadline=total_deadline,
    )


def _click_stock_row(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
    stock_code: str,
) -> None:
    index = view.results_model.index_for_stock(stock_code)
    if not index.isValid():
        raise AssertionError(f"stock is not visible on current page: {stock_code}")
    rect = view.results_table.visualRect(index)
    if not rect.isValid() or rect.isEmpty():
        raise AssertionError(f"stock row has no visible rectangle: {stock_code}")
    QTest.mouseClick(
        view.results_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )
    app.processEvents()
    current = view.results_table.currentIndex()
    selected = view.results_model.row_at(current.row()) if current.isValid() else None
    if selected is None or selected.stock_code != stock_code:
        raise AssertionError(f"table selection did not select expected stock: {stock_code}")


def _close_view(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionMaView,
) -> bool:
    view.cancel_current_operation()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        app.processEvents()
        if view.begin_shutdown():
            view.close()
            app.processEvents()
            return True
        time.sleep(0.01)
    return False


def test_saved_source_catalog_exact_open_cross_page_detail_bookmark_restore_and_requery(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """完整 UI 路徑只重用既有 sealed 合成 bundle，不呼叫 producer。"""

    source = _journey_bundle_source(request)
    bundle_root = source.bundle_root
    bundle_identity_sha256 = source.bundle_identity_sha256
    manifest_sha256 = source.manifest_sha256
    attempt = _attempt_directory()
    receipt_path = attempt / "journey_receipt.json"
    receipt: dict[str, object] = {
        "schema": "ma-saved-source-ui-journey-receipt.v1",
        "status": "running",
        "attempt_directory": str(attempt),
        "bundle_root": str(bundle_root),
        "bundle_identity_sha256": bundle_identity_sha256,
        "bundle_source_origin": source.origin,
        "producer_invocation_scope": "not_called_by_ui_journey_after_source_resolution",
        "fixture_factory_invoked": source.origin == "real_bundle_fixture_factory",
        "formal_data_access_scope": "all_inventory_roots_are_synthetic_qa; database_is_hashed_as_bytes_only",
        "exact_open_calls": 0,
        "phase": "preflight",
        "operation_wait_strategy": "QApplication.processEvents() plus time.sleep(0.01); no QTest.qWait polling",
        "phases": [],
    }
    views: list[DailyMarketTechnicalOfficialDispositionMaView] = []
    started = time.monotonic()
    overall_deadline = started + _TOTAL_DEADLINE_SECONDS
    exact_open_calls = 0
    bundle_session_entry_calls = 0
    read_session_entry_calls = 0
    exact_read_calls_by_route: dict[str, int] = {
        "bundle_session": 0,
        "read_session": 0,
        "unknown": 0,
    }
    open_route = threading.local()
    roots: tuple[Path, ...] = ()
    before_manifest: str | None = None
    before_tree: dict[str, object] | None = None
    before_tree_sha: str | None = None
    original_open = view_module.open_daily_market_technical_official_disposition_bundle_session_v1
    original_read_session_open = (
        query_reader_module.open_daily_market_technical_official_disposition_read_session_v1
    )
    original_bundle_read_exact = DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact
    receipt_lock = threading.Lock()
    background_events: list[dict[str, object]] = []
    cancellation_stats: dict[str, object] = {
        "requests": [],
        "callback_calls": 0,
        "callback_first_true_elapsed_ms": None,
    }

    def persist_background_event(event: dict[str, object]) -> None:
        with receipt_lock:
            background_events.append(event)
            receipt["background_events"] = list(background_events)
            receipt["exact_open_calls"] = exact_open_calls
            receipt["bundle_session_entry_calls"] = bundle_session_entry_calls
            receipt["read_session_entry_calls"] = read_session_entry_calls
            receipt["exact_read_calls_by_route"] = dict(exact_read_calls_by_route)
            _write_receipt(receipt_path, receipt)

    def _observed_cancel_callback(
        callback: Callable[[], object] | None,
    ) -> Callable[[], object] | None:
        if not callable(callback):
            return None

        def observed() -> object:
            calls = cast(int, cancellation_stats["callback_calls"]) + 1
            cancellation_stats["callback_calls"] = calls
            value = callback()
            if (
                type(value) is bool
                and value
                and cancellation_stats["callback_first_true_elapsed_ms"] is None
            ):
                cancellation_stats["callback_first_true_elapsed_ms"] = int(
                    (time.monotonic() - started) * 1000
                )
            return value

        return observed

    def tracked_bundle_read_exact(
        reader: DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        bundle_identity_sha256: str,
        *,
        expected_manifest_sha256: str,
        cancel_callback: Callable[[], bool] | None = None,
        technical_read_session_builder: DailyMarketTechnicalUniverseV4ReadSessionBuilder | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1:
        nonlocal exact_open_calls
        route = cast(str, getattr(open_route, "name", "unknown"))
        opened_at = time.monotonic()
        open_thread_cpu = time.thread_time()
        with receipt_lock:
            exact_open_calls += 1
            exact_read_calls_by_route[route] = exact_read_calls_by_route.get(route, 0) + 1
            call = exact_open_calls
        persist_background_event(
            {
                "stage": "bundle_read_exact",
                "state": "started",
                "call": call,
                "route": route,
                "bundle_identity_sha256": bundle_identity_sha256,
                "elapsed_since_attempt_start_ms": int((opened_at - started) * 1000),
            }
        )
        try:
            result = original_bundle_read_exact(
                reader,
                bundle_identity_sha256,
                expected_manifest_sha256=expected_manifest_sha256,
                cancel_callback=cancel_callback,
                technical_read_session_builder=technical_read_session_builder,
            )
        except BaseException as exc:
            persist_background_event(
                {
                    "stage": "bundle_read_exact",
                    "state": "error",
                    "call": call,
                    "route": route,
                    "elapsed_ms": int((time.monotonic() - opened_at) * 1000),
                    "thread_cpu_ms": int((time.thread_time() - open_thread_cpu) * 1000),
                    "error_chain": _exception_chain(exc),
                }
            )
            raise
        persist_background_event(
            {
                "stage": "bundle_read_exact",
                "state": "complete",
                "call": call,
                "route": route,
                "elapsed_ms": int((time.monotonic() - opened_at) * 1000),
                "thread_cpu_ms": int((time.thread_time() - open_thread_cpu) * 1000),
                "bundle_identity_sha256": result.reference.bundle_identity_sha256,
                "manifest_sha256": result.reference.manifest_sha256,
                "row_count": result.reference.row_count,
            }
        )
        return result

    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        "read_exact",
        tracked_bundle_read_exact,
    )

    def tracked_open(*args: object, **kwargs: object) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
        nonlocal bundle_session_entry_calls
        bundle_session_entry_calls += 1
        entry_call = bundle_session_entry_calls
        opened_at = time.monotonic()
        open_thread_cpu = time.thread_time()
        cancel_callback = kwargs.get("cancel_callback")
        observed = _observed_cancel_callback(
            cast(Callable[[], object] | None, cancel_callback)
        )
        if observed is not None:
            kwargs["cancel_callback"] = observed
        previous_route = getattr(open_route, "name", "unknown")
        open_route.name = "bundle_session"
        persist_background_event(
            {
                "stage": "bundle_session_open",
                "state": "started",
                "entry_call": entry_call,
                "elapsed_since_attempt_start_ms": int((opened_at - started) * 1000),
            }
        )
        try:
            session = original_open(*args, **kwargs)  # type: ignore[arg-type]
        except BaseException as exc:
            persist_background_event(
                {
                    "stage": "bundle_session_open",
                    "state": "error",
                    "entry_call": entry_call,
                    "elapsed_ms": int((time.monotonic() - opened_at) * 1000),
                    "thread_cpu_ms": int((time.thread_time() - open_thread_cpu) * 1000),
                    "cancel_callback_calls": cancellation_stats["callback_calls"],
                    "cancel_callback_first_true_elapsed_ms": cancellation_stats[
                        "callback_first_true_elapsed_ms"
                    ],
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:2000],
                    "error_chain": _exception_chain(exc),
                }
            )
            raise
        finally:
            open_route.name = previous_route
        persist_background_event(
            {
                "stage": "bundle_session_open",
                "state": "complete",
                "entry_call": entry_call,
                "elapsed_ms": int((time.monotonic() - opened_at) * 1000),
                "thread_cpu_ms": int((time.thread_time() - open_thread_cpu) * 1000),
                "cancel_callback_calls": cancellation_stats["callback_calls"],
                "cancel_callback_first_true_elapsed_ms": cancellation_stats[
                    "callback_first_true_elapsed_ms"
                ],
                "query_identity_sha256": session.query.query_identity_sha256,
            }
        )
        return session

    def tracked_read_session_open(
        query: DailyMarketTechnicalOfficialDispositionQueryV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionReadSessionV1:
        nonlocal read_session_entry_calls
        read_session_entry_calls += 1
        entry_call = read_session_entry_calls
        opened_at = time.monotonic()
        open_thread_cpu = time.thread_time()
        observed = _observed_cancel_callback(cancel_callback)
        previous_route = getattr(open_route, "name", "unknown")
        open_route.name = "read_session"
        persist_background_event(
            {
                "stage": "read_session_open",
                "state": "started",
                "entry_call": entry_call,
                "elapsed_since_attempt_start_ms": int((opened_at - started) * 1000),
            }
        )
        try:
            session = original_read_session_open(
                query,
                cancel_callback=observed,
            )
        except BaseException as exc:
            persist_background_event(
                {
                    "stage": "read_session_open",
                    "state": "error",
                    "entry_call": entry_call,
                    "elapsed_ms": int((time.monotonic() - opened_at) * 1000),
                    "thread_cpu_ms": int((time.thread_time() - open_thread_cpu) * 1000),
                    "error_chain": _exception_chain(exc),
                }
            )
            raise
        finally:
            open_route.name = previous_route
        persist_background_event(
            {
                "stage": "read_session_open",
                "state": "complete",
                "entry_call": entry_call,
                "elapsed_ms": int((time.monotonic() - opened_at) * 1000),
                "thread_cpu_ms": int((time.thread_time() - open_thread_cpu) * 1000),
                "query_identity_sha256": session.query.query_identity_sha256,
            }
        )
        return session

    monkeypatch.setattr(
        view_module,
        "open_daily_market_technical_official_disposition_bundle_session_v1",
        tracked_open,
    )
    monkeypatch.setattr(
        query_reader_module,
        "open_daily_market_technical_official_disposition_read_session_v1",
        tracked_read_session_open,
    )

    failure_observations: list[dict[str, object]] = []

    def observe_operation(view: DailyMarketTechnicalOfficialDispositionMaView) -> None:
        def observe(kind: str, success: bool) -> None:
            if success:
                return
            worker = view.active_worker
            failure_observations.append(
                {
                    "kind": kind,
                    "status_label": view.status_label.text(),
                    "busy_worker_kind": view._worker_kind,
                    "active_worker_running": worker.isRunning() if worker is not None else False,
                    "has_running_worker": view._has_running_worker(),
                }
            )
            with receipt_lock:
                receipt["operation_failure_observations"] = list(failure_observations)
                _write_receipt(receipt_path, receipt)

        view.operationSettled.connect(observe)

    worker_call_diagnostics: list[dict[str, object]] = []

    def instrument_view_task(view: DailyMarketTechnicalOfficialDispositionMaView) -> None:
        original_start = view._start_task
        original_cancel = view.cancel_current_operation

        def tracked_cancel() -> None:
            worker = view.active_worker
            if worker is not None:
                request = {
                    "stage": "ui_cancel_request",
                    "elapsed_since_attempt_start_ms": int((time.monotonic() - started) * 1000),
                    "worker_kind": str(view._worker_kind)[:100],
                    "worker_running_before": bool(worker.isRunning()),
                }
                requests = cast(list[dict[str, object]], cancellation_stats["requests"])
                requests.append(request)
                persist_background_event(request)
            original_cancel()

        def tracked_start(kind: str, task: Callable[..., object], apply: Callable[[object], None]) -> None:
            def tracked_task(cancel_callback: Callable[[], object] | None = None) -> object:
                task_started = time.monotonic()
                start_event: dict[str, object] = {"task_kind": kind, "state": "started"}
                worker_call_diagnostics.append(start_event)
                persist_background_event(start_event)
                try:
                    value = task(cancel_callback)
                except BaseException as exc:
                    error_event = {
                        "task_kind": kind,
                        "state": "error",
                        "elapsed_ms": int((time.monotonic() - task_started) * 1000),
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:2000],
                        "error_chain": _exception_chain(exc),
                        "cancel_callback_first_true_elapsed_ms": cancellation_stats[
                            "callback_first_true_elapsed_ms"
                        ],
                    }
                    worker_call_diagnostics.append(error_event)
                    persist_background_event(error_event)
                    raise
                complete_event = {
                    "task_kind": kind,
                    "state": "complete",
                    "elapsed_ms": int((time.monotonic() - task_started) * 1000),
                }
                worker_call_diagnostics.append(complete_event)
                persist_background_event(complete_event)
                return value

            original_start(kind, tracked_task, apply)

        setattr(view, "_start_task", tracked_start)
        setattr(view, "cancel_current_operation", tracked_cancel)
        observe_operation(view)

    def record_operation_timeout(
        view: DailyMarketTechnicalOfficialDispositionMaView,
        kind: str,
        exc: BaseException,
    ) -> None:
        worker = view.active_worker
        diagnostic = {
            "expected_kind": kind,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_since_attempt_start_ms": int((time.monotonic() - started) * 1000),
            "status_label": view.status_label.text(),
            "busy_worker_kind": view._worker_kind,
            "active_worker_running": worker.isRunning() if worker is not None else False,
            "has_running_worker": view._has_running_worker(),
            "recent_worker_events": worker_call_diagnostics[-12:],
            "bundle_session_open_events": [
                event for event in background_events if event.get("stage") == "bundle_session_open"
            ],
            "operation_failures": failure_observations[-12:],
            "cancel_requests": cast(list[dict[str, object]], cancellation_stats["requests"])[-12:],
            "cancel_callback_calls": cancellation_stats["callback_calls"],
            "cancel_callback_first_true_elapsed_ms": cancellation_stats[
                "callback_first_true_elapsed_ms"
            ],
        }
        with receipt_lock:
            receipt["operation_timeout_diagnostic"] = diagnostic
            _write_receipt(receipt_path, receipt)

    def record_phase(name: str, **details: object) -> None:
        with receipt_lock:
            phases = cast(list[dict[str, object]], receipt["phases"])
            phases.append({"name": name, **details})
            receipt["phase"] = name
            receipt["exact_open_calls"] = exact_open_calls
            receipt["background_events"] = list(background_events)
            _write_receipt(receipt_path, receipt)

    def begin_phase(name: str) -> None:
        with receipt_lock:
            receipt["phase"] = name
            receipt["exact_open_calls"] = exact_open_calls
            _write_receipt(receipt_path, receipt)

    try:
        roots = _source_roots(source)
        before_manifest = _sha256_file(
            bundle_root / "manifests" / f"{bundle_identity_sha256}.json"
        )
        if before_manifest != manifest_sha256:
            raise AssertionError("saved bundle manifest pin changed before UI journey")
        before_tree, before_tree_sha = _tree_inventory(roots)
        if source.expected_source_tree_sha256 is not None and before_tree_sha != source.expected_source_tree_sha256:
            raise AssertionError("saved bundle source inventory differs from reviewed pin")
        metadata = DailyMarketTechnicalOfficialDispositionBundleReaderV1(
            bundle_root
        ).read_manifest_metadata(
            bundle_identity_sha256,
            expected_manifest_sha256=manifest_sha256,
        )
        if metadata.metadata_state != "metadata_unverified":
            raise AssertionError("catalog preflight unexpectedly granted qualification")
        receipt.update(
            {
                "manifest_sha256_before": before_manifest,
                "source_tree_sha256_before": before_tree_sha,
                "expected_source_tree_sha256": source.expected_source_tree_sha256,
                "source_tree_before": before_tree,
                "source_roots": [str(root) for root in roots],
            }
        )
        _write_receipt(receipt_path, receipt)

        initial = DailyMarketTechnicalOfficialDispositionMaView(bundle_root)
        views.append(initial)
        instrument_view_task(initial)
        initial_events: list[tuple[str, bool]] = []
        initial.operationSettled.connect(
            lambda kind, success, destination=initial_events: destination.append((kind, success))
        )
        initial.resize(1000, 900)
        initial.show()
        app.processEvents()

        begin_phase("catalog_scan")
        _run_operation(
            app,
            initial,
            initial_events,
            initial.refresh_catalog_button.click,
            expected_kind="盤點保存來源清單",
            total_deadline=overall_deadline,
        )
        if len(initial._catalog_entries) != 1:
            raise AssertionError(f"expected exactly one pinned manifest candidate, found {len(initial._catalog_entries)}")
        entry = initial._catalog_entries[0]
        if (
            not entry.can_attempt_exact_read
                or entry.bundle_identity_sha256 != bundle_identity_sha256
                or entry.manifest_sha256 != manifest_sha256
            or "尚未核驗" not in initial.catalog_list.item(0).text()
        ):
            raise AssertionError("catalog entry is not the pinned unverified candidate")
        record_phase(
            "catalog_metadata_only",
            candidate_count=len(initial._catalog_entries),
            candidate_relative_path=entry.relative_path,
            metadata_state=entry.metadata_state,
            bundle_identity_sha256=entry.bundle_identity_sha256,
            manifest_sha256=entry.manifest_sha256,
        )

        for scope, checkbox in initial.scope_checks.items():
            checkbox.setChecked(scope == "included_processed")
        initial.page_size_box.setValue(100)
        item = initial.catalog_list.item(0)
        item_rect = initial.catalog_list.visualItemRect(item)
        if not item_rect.isValid() or item_rect.isEmpty():
            raise AssertionError("catalog candidate is not visible for explicit selection")
        QTest.mouseClick(
            initial.catalog_list.viewport(),
            Qt.MouseButton.LeftButton,
            pos=item_rect.center(),
        )
        app.processEvents()
        if initial.catalog_list.currentRow() != 0:
            raise AssertionError("catalog candidate was not explicitly selected")
        begin_phase("first_exact_open")
        try:
            _run_operation(
                app,
                initial,
                initial_events,
                initial.open_candidate_button.click,
                expected_kind="核驗並執行全母體查詢",
                total_deadline=overall_deadline,
            )
        except BaseException as exc:
            record_operation_timeout(initial, "核驗並執行全母體查詢", exc)
            raise
        query = initial.current_query
        page_zero = initial.current_page
        result = initial.current_result
        if query is None or page_zero is None or result is None:
            raise AssertionError("exact open did not publish query, page, and result")
        if (
            exact_open_calls != 1
            or query.f17_query.bundle_identity_sha256 != bundle_identity_sha256
            or query.f17_query.expected_manifest_sha256 != manifest_sha256
            or query.f17_query.row_scope_filter != ("included_processed",)
            or page_zero.page_index != 0
            or page_zero.page_size != 100
            or page_zero.page_count != 3
            or page_zero.counts.visible_count != 257
            or tuple(row.stock_code for row in page_zero.rows)
            != tuple(f"{1000 + index:04d}" for index in range(100))
        ):
            raise AssertionError("initial UI exact result differs from the pinned full-cohort oracle")
        original_f17_json = query.f17_query.to_json()
        original_source_pins = result.source_pins
        original_ma_session_identity = query.ma_alignment_read_session_identity_sha256
        original_ma_index_identity = query.ma_alignment_index_identity_sha256
        original_ma_request_identity = query.ma_source_request_identity_sha256
        original_page_zero_rows = {row.stock_code: row.to_dict() for row in page_zero.rows}
        record_phase(
            "exact_open_and_first_global_page",
            exact_open_calls=exact_open_calls,
            operation_identity_sha256=result.operation_identity_sha256,
            query_identity_sha256=query.query_identity_sha256,
            page_identity_sha256=page_zero.page_identity_sha256,
            counts=result.counts.to_dict(),
            source_pins=dict(result.source_pins),
        )

        selected_signals: list[object] = []
        initial.stockSelected.connect(selected_signals.append)
        begin_phase("detail_and_return_page_zero")
        _click_stock_row(app, initial, "1000")
        initial.detail_button.click()
        app.processEvents()
        if (
            initial.results_stack.currentIndex() != 1
            or not selected_signals
            or getattr(selected_signals[-1], "stock_code", None) != "1000"
            or "1000" not in initial.detail_text.toPlainText()
            or "current-only" not in initial.detail_text.toPlainText()
        ):
            raise AssertionError("detail view did not show the exact selected saved row and scope")
        detail_selection = cast(DailyMarketTechnicalOfficialDispositionMaSelectionV1, selected_signals[-1])
        initial.back_button.click()
        app.processEvents()
        if (
            initial.results_stack.currentIndex() != 0
            or initial.current_page is None
            or initial.current_page.page_identity_sha256 != page_zero.page_identity_sha256
            or detail_selection.stock_code != "1000"
        ):
            raise AssertionError("detail return did not preserve the exact origin page and selection")
        initial.add_comparison_button.click()
        app.processEvents()
        if tuple(item.stock_code for item in initial.comparison_basket) != ("1000",):
            raise AssertionError("page-zero selection was not added to the comparison basket")

        begin_phase("read_second_global_page")
        _run_operation(
            app,
            initial,
            initial_events,
            initial.next_page_button.click,
            expected_kind="讀取全域排序中的指定頁",
            total_deadline=overall_deadline,
        )
        page_one = initial.current_page
        if page_one is None or page_one.page_index != 1:
            raise AssertionError("next-page UI did not load page one")
        _click_stock_row(app, initial, "1100")
        initial.detail_button.click()
        app.processEvents()
        if initial.detail_text.toPlainText().find("1100") < 0:
            raise AssertionError("page-one detail did not identify the clicked saved row")
        initial.back_button.click()
        app.processEvents()
        if initial.current_page is None or initial.current_page.page_index != 1:
            raise AssertionError("page-one detail return changed the saved page")
        initial.add_comparison_button.click()
        app.processEvents()
        basket = initial.comparison_basket
        if (
            tuple(item.stock_code for item in basket) != ("1000", "1100")
            or tuple(item.page_index for item in basket) != (0, 1)
            or any(item.query_identity_sha256 != query.query_identity_sha256 for item in basket)
        ):
            raise AssertionError("cross-page basket lost its exact query or page requests")
        record_phase(
            "cross_page_detail_and_basket",
            basket=[item.to_dict() for item in basket],
            page_one_identity_sha256=page_one.page_identity_sha256,
            exact_open_calls=exact_open_calls,
        )

        comparisons: list[object] = []
        initial.comparisonReady.connect(comparisons.append)
        begin_phase("cross_page_comparison")
        _run_operation(
            app,
            initial,
            initial_events,
            initial.compare_button.click,
            expected_kind="重讀跨頁比較列",
            total_deadline=overall_deadline,
        )
        if not comparisons or type(comparisons[-1]) is not DailyMarketTechnicalOfficialDispositionMaViewComparisonV1:
            raise AssertionError("comparison did not return typed rows from the saved query")
        comparison = cast(DailyMarketTechnicalOfficialDispositionMaViewComparisonV1, comparisons[-1])
        if (
            tuple(row.stock_code for row in comparison.rows) != ("1000", "1100")
            or comparison.rows[0].to_dict() != original_page_zero_rows["1000"]
            or comparison.rows[1].to_dict() != next(
                row.to_dict() for row in page_one.rows if row.stock_code == "1100"
            )
            or tuple(item.to_dict() for item in comparison.comparison.selections)
            != tuple(item.to_dict() for item in basket)
            or exact_open_calls != 1
        ):
            raise AssertionError("cross-page comparison changed the source, query, or saved row facts")
        for dialog in initial.findChildren(QDialog):
            dialog.close()
        app.processEvents()
        record_phase(
            "cross_page_comparison",
            comparison_identity_sha256=comparison.comparison.comparison_identity_sha256,
            row_codes=[row.stock_code for row in comparison.rows],
            exact_open_calls=exact_open_calls,
        )

        bookmark_signals: list[object] = []
        initial.bookmarkPrepared.connect(bookmark_signals.append)
        initial.bookmark_button.click()
        app.processEvents()
        if not bookmark_signals or type(bookmark_signals[-1]) is not DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
            raise AssertionError("bookmark button did not emit the typed MA/F17 bookmark")
        bookmark = cast(DailyMarketTechnicalOfficialDispositionMaBookmarkV1, bookmark_signals[-1])
        if (
            bookmark.query.query_identity_sha256 != query.query_identity_sha256
            or bookmark.selected.stock_code != "1100"
            or bookmark.selected.page_index != 1
            or bookmark.selected.page_request_identity_sha256
            != DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
                query, page_index=1, page_size=100,
            ).request_identity_sha256
            or tuple(item.stock_code for item in bookmark.comparison_selections) != ("1000", "1100")
            or tuple(item.page_index for item in bookmark.comparison_selections) != (0, 1)
            or any(item.source_pins != original_source_pins for item in bookmark.comparison_selections)
        ):
            raise AssertionError("typed bookmark did not preserve selected row and cross-page source pins")
        bookmark_json = bookmark.to_json()
        record_phase(
            "typed_bookmark_prepared",
            bookmark_identity_sha256=bookmark.bookmark_identity_sha256,
            bookmark_bytes=len(bookmark_json.encode("utf-8")),
            selected_stock_code=bookmark.selected.stock_code,
            comparison_codes=[item.stock_code for item in bookmark.comparison_selections],
        )

        restored = DailyMarketTechnicalOfficialDispositionMaView()
        views.append(restored)
        instrument_view_task(restored)
        restored_events: list[tuple[str, bool]] = []
        restored.operationSettled.connect(
            lambda kind, success, destination=restored_events: destination.append((kind, success))
        )
        restored.resize(1000, 900)
        restored.show()
        app.processEvents()
        exact_count_before_restore = exact_open_calls
        begin_phase("new_view_bookmark_restore")
        restore_start_index = len(restored_events)
        if not restored.restore_bookmark(bookmark_json):
            raise AssertionError("new view refused the exact saved bookmark")
        _wait_for_operation(
            app,
            restored,
            restored_events,
            expected_kind="重開四均線研究收藏",
            start_index=restore_start_index,
            total_deadline=overall_deadline,
        )
        restored_query = restored.current_query
        restored_page = restored.current_page
        restored_index = restored.results_table.currentIndex()
        restored_selected = restored.results_model.row_at(restored_index.row()) if restored_index.isValid() else None
        restored_basket = tuple(item.to_dict() for item in restored.comparison_basket)
        expected_basket = tuple(item.to_dict() for item in basket)
        restore_checks: dict[str, dict[str, object]] = {
            "exact_read_total": {
                "expected": exact_count_before_restore + 1,
                "actual": exact_open_calls,
                "passed": exact_open_calls == exact_count_before_restore + 1,
            },
            "bundle_session_entry_count": {
                "expected": 1,
                "actual": bundle_session_entry_calls,
                "passed": bundle_session_entry_calls == 1,
            },
            "read_session_entry_count": {
                "expected": 1,
                "actual": read_session_entry_calls,
                "passed": read_session_entry_calls == 1,
            },
            "exact_reads_by_route": {
                "expected": {"bundle_session": 1, "read_session": 1},
                "actual": {
                    "bundle_session": exact_read_calls_by_route["bundle_session"],
                    "read_session": exact_read_calls_by_route["read_session"],
                },
                "passed": exact_read_calls_by_route["bundle_session"] == 1
                and exact_read_calls_by_route["read_session"] == 1,
            },
            "query_json": {
                "expected": query.to_json(),
                "actual": restored_query.to_json() if restored_query is not None else None,
                "passed": restored_query is not None and restored_query.to_json() == query.to_json(),
            },
            "page_index": {
                "expected": 1,
                "actual": restored_page.page_index if restored_page is not None else None,
                "passed": restored_page is not None and restored_page.page_index == 1,
            },
            "page_request_identity": {
                "expected": bookmark.selected.page_request_identity_sha256,
                "actual": restored_page.request_identity_sha256 if restored_page is not None else None,
                "passed": restored_page is not None
                and restored_page.request_identity_sha256 == bookmark.selected.page_request_identity_sha256,
            },
            "selected_stock_code": {
                "expected": "1100",
                "actual": restored_selected.stock_code if restored_selected is not None else None,
                "passed": restored_selected is not None and restored_selected.stock_code == "1100",
            },
            "comparison_basket": {
                "expected_count": len(expected_basket),
                "actual_count": len(restored_basket),
                "identities_equal": restored_basket == expected_basket,
                "passed": restored_basket == expected_basket,
            },
            "current_result_is_none": {
                "expected": True,
                "actual": restored.current_result is None,
                "passed": restored.current_result is None,
            },
        }
        restore_checks_passed = all(
            item.get("passed") is True for item in restore_checks.values()
        )
        with receipt_lock:
            receipt["restore_assertions"] = restore_checks
            receipt["exact_open_calls"] = exact_open_calls
            receipt["bundle_session_entry_calls"] = bundle_session_entry_calls
            receipt["read_session_entry_calls"] = read_session_entry_calls
            receipt["exact_read_calls_by_route"] = dict(exact_read_calls_by_route)
            _write_receipt(receipt_path, receipt)
        if not restore_checks_passed:
            raise AssertionError("new view did not restore its exact-source context, page, selection, and basket")
        if restored_query is None or restored_page is None:
            raise AssertionError("restore query/page vanished after successful exact-state checks")
        restored_pins = restored_page.source_pins
        record_phase(
            "new_view_fresh_restore_context",
            exact_open_calls=exact_open_calls,
            query_identity_sha256=restored_query.query_identity_sha256,
            operation_identity_sha256=restored_page.operation_identity_sha256,
            page_identity_sha256=restored_page.page_identity_sha256,
            selected_stock_code="1100",
            restored_comparison_codes=[item.stock_code for item in restored.comparison_basket],
            source_pins=dict(restored_pins),
        )

        begin_phase("same_source_condition_requery")
        restored.ma_state_checks["unknown"].setChecked(True)
        _run_operation(
            app,
            restored,
            restored_events,
            restored.apply_query_button.click,
            expected_kind="沿原保存來源重新全域查詢",
            total_deadline=overall_deadline,
        )
        requery = restored.current_result
        requery_page = restored.current_page
        if (
            exact_open_calls != exact_count_before_restore + 1
            or requery is None
            or requery_page is None
            or requery.query.query_identity_sha256 == restored_query.query_identity_sha256
            or requery.query.ma_states != ("unknown",)
            or requery.query.f17_query.to_json() != query.f17_query.to_json()
            or requery.source_pins != original_source_pins
            or requery.query.ma_alignment_read_session_identity_sha256 != original_ma_session_identity
            or requery.query.ma_alignment_index_identity_sha256 != original_ma_index_identity
            or requery.query.ma_source_request_identity_sha256 != original_ma_request_identity
            or requery.counts.visible_count != 257
            or requery.counts.hard_eligible_count != 257
            or restored.comparison_basket
            or requery_page.page_index != 0
        ):
            raise AssertionError("same-source condition requery changed pins or lost the complete MA population")
        record_phase(
            "same_source_requery_without_second_open",
            exact_open_calls=exact_open_calls,
            query_identity_sha256=requery.query.query_identity_sha256,
            operation_identity_sha256=requery.operation_identity_sha256,
            counts=requery.counts.to_dict(),
            source_pins=dict(requery.source_pins),
        )

        receipt.update(
            {
                "status": "passed",
                "phase": "complete",
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "exact_open_calls": exact_open_calls,
                "initial_query_identity_sha256": query.query_identity_sha256,
                "restored_query_identity_sha256": restored_query.query_identity_sha256,
                "requery_identity_sha256": requery.query.query_identity_sha256,
                "operation_events": {
                    "initial": initial_events,
                    "restored": restored_events,
                },
            }
        )
    except BaseException as exc:
        receipt.update(
            {
                "status": "failed",
                "phase": cast(str, receipt.get("phase", "ui_journey")),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "exact_open_calls": exact_open_calls,
            }
        )
        raise
    finally:
        if roots and before_manifest is not None and before_tree is not None and before_tree_sha is not None:
            try:
                after_manifest = _sha256_file(
                    bundle_root / "manifests" / f"{bundle_identity_sha256}.json"
                )
                after_tree, after_tree_sha = _tree_inventory(roots)
                receipt["manifest_sha256_after"] = after_manifest
                receipt["source_tree_after"] = after_tree
                receipt["source_tree_sha256_after"] = after_tree_sha
                receipt["source_post_inventory_status"] = (
                    "unchanged"
                    if after_manifest == before_manifest
                    and after_tree_sha == before_tree_sha
                    and after_tree == before_tree
                    else "changed"
                )
            except BaseException as post_exc:
                receipt["source_post_inventory_status"] = "could_not_verify"
                receipt["source_post_inventory_error_type"] = type(post_exc).__name__
                receipt["source_post_inventory_error"] = str(post_exc)
        else:
            receipt["source_post_inventory_status"] = "not_started_preflight_failed"
        shutdown_results: list[dict[str, object]] = []
        for view in reversed(views):
            try:
                closed = _close_view(app, view)
                shutdown_results.append(
                    {"closed": closed, "active_worker": view.active_worker is not None}
                )
            except BaseException as cleanup_exc:
                shutdown_results.append({"closed": False, "error_type": type(cleanup_exc).__name__})
        receipt["view_shutdown"] = shutdown_results
        if receipt.get("status") == "passed" and any(item.get("closed") is not True for item in shutdown_results):
            receipt["status"] = "failed"
            receipt["phase"] = "view_shutdown"
            receipt["error"] = "one or more native workers did not stop before the cleanup deadline"
        if receipt.get("status") == "passed" and receipt.get("source_post_inventory_status") != "unchanged":
            receipt["status"] = "failed"
            receipt["phase"] = "postflight_source_inventory"
            receipt["error"] = "saved source inventory changed during UI journey"
        if receipt.get("status") == "running":
            receipt["status"] = "failed"
            receipt["phase"] = "incomplete"
        receipt["exact_open_calls"] = exact_open_calls
        receipt["bundle_session_entry_calls"] = bundle_session_entry_calls
        receipt["read_session_entry_calls"] = read_session_entry_calls
        receipt["exact_read_calls_by_route"] = dict(exact_read_calls_by_route)
        receipt["cancel_requests"] = cast(
            list[dict[str, object]], cancellation_stats["requests"]
        )
        receipt["cancel_callback_calls"] = cancellation_stats["callback_calls"]
        receipt["cancel_callback_first_true_elapsed_ms"] = cancellation_stats[
            "callback_first_true_elapsed_ms"
        ]
        try:
            _write_receipt(receipt_path, receipt)
        except OSError as receipt_exc:
            receipt["status"] = "failed"
            receipt["phase"] = "receipt_write"
            receipt["receipt_write_error_type"] = type(receipt_exc).__name__
            receipt["receipt_write_error"] = str(receipt_exc)

    if receipt.get("status") != "passed":
        raise AssertionError(
            "journey receipt is not passed: "
            f"status={receipt.get('status')!r}, phase={receipt.get('phase')!r}, "
            f"error={receipt.get('error')!r}"
        )
