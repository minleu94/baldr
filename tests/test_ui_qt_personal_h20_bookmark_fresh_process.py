"""真 MainWindow 跨程序重開合成 H20 收藏；不訓練或載入模型 pickle。"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from typing import Any, Callable, Mapping
from urllib.parse import unquote

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.recommendation.personal_h20_research_bookmark import (
    PersonalH20ResearchBookmark,
)
from app_module.watchlist_service import WatchlistService
from tests.test_ui_qt_personal_h20_bookmark_reopen_journey import _save_and_find
from tests.test_ui_qt_personal_h20_mainwindow_saved_journey import (
    _close_mainwindow,
    _prepare_saved_h20_mainwindow,
    _wait_for,
)


_RECEIPT_PREFIX = "PERSONAL_H20_FRESH_PROCESS_RECEIPT="


def _file_pin(path: Path) -> dict[str, Any]:
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    before_stat = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    after_stat = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if before_stat != after_stat:
        raise AssertionError(f"synthetic source changed while pinning: {path}")
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "stat": list(after_stat),
    }


def _source_inventory(
    saved: Mapping[str, Any],
    fixture_root: Path,
    *,
    extra_paths: tuple[Path, ...] = (),
) -> list[dict[str, Any]]:
    """只列 immutable H20/source原件；排除可寫的應用與 Watchlist 狀態。"""

    paths: set[Path] = {
        Path(saved["snapshot_database"]),
        Path(saved["manifest_path"]),
        Path(saved["activation"].config_path),
        Path(saved["contract_fixture"]["marker_path"]),
        *extra_paths,
    }
    captures = saved["manifest"].get("captures")
    assert isinstance(captures, list) and len(captures) == 1
    capture_path = Path(captures[0]["path"])
    paths.add(capture_path)
    source_pins = saved["source_binding"]["pins"]
    for key, value in source_pins.items():
        if key.endswith("_path") and isinstance(value, str):
            path = Path(value)
            assert path.is_file(), f"合成來源 pin 檔不存在：{key}={path}"
            paths.add(path)

    contract = saved["contract_fixture"]["contract"]
    artifact_root = Path(contract.artifact_root)
    paths.update(
        {
            artifact_root / "manifest.json",
            artifact_root / "candidate.json",
            artifact_root / "model.joblib",
            Path(contract.lineage_path),
        }
    )
    resolved_root = fixture_root.resolve()
    result = []
    for path in sorted((item.resolve() for item in paths), key=str):
        assert path.is_relative_to(resolved_root), f"source fixture escaped case root: {path}"
        assert path.is_file(), f"source fixture pin is missing: {path}"
        result.append(_file_pin(path))
    return result


def _inventory_changes(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_by_path = {item["path"]: item for item in before}
    after_by_path = {item["path"]: item for item in after}
    changed_paths = sorted(set(before_by_path) | set(after_by_path))
    return [
        {
            "path": path,
            "before": before_by_path.get(path),
            "after": after_by_path.get(path),
        }
        for path in changed_paths
        if before_by_path.get(path) != after_by_path.get(path)
    ]


def _contract_fixture_descriptor(saved: Mapping[str, Any]) -> dict[str, Any]:
    fixture = saved["contract_fixture"]
    contract = fixture["contract"]
    contract_fields: dict[str, Any] = {}
    for field in dataclasses.fields(contract):
        value = getattr(contract, field.name)
        if field.name == "feature_schema":
            value = [list(row) for row in value]
        elif field.name == "installed_library_versions":
            value = dict(value)
        contract_fields[field.name] = value
    return {
        "contract_fields": contract_fields,
        "contract_binding": dict(fixture["binding"]),
        "marker_path": str(Path(fixture["marker_path"]).resolve()),
        "marker_sha256": fixture["marker_hash"],
        "artifact_root": str(Path(contract.artifact_root).resolve()),
        "lineage_path": str(Path(contract.lineage_path).resolve()),
    }


def _write_descriptor(
    *,
    path: Path,
    parent_pid: int,
    bookmark: PersonalH20ResearchBookmark,
    saved: Mapping[str, Any],
    fixture_root: Path,
    observed_at: str,
    stage_trace_path: Path,
    ml_research_storage_config: Path,
) -> None:
    payload = {
        "schema_version": "personal-h20-fresh-process-test.v1",
        "parent_pid": parent_pid,
        "bookmark_id": bookmark.bookmark_id,
        "bookmark": bookmark.to_dict(),
        "observed_at": observed_at,
        "stage_trace_path": str(stage_trace_path.resolve()),
        "source_inventory": _source_inventory(
            saved, fixture_root, extra_paths=(ml_research_storage_config,)
        ),
        "source_database": str(Path(saved["snapshot_database"]).resolve()),
        "market_root": str(Path(saved["market_root"]).resolve()),
        "research_output_root": str(
            Path(saved["source_binding"]["pins"]["research_output_root"]).resolve()
        ),
        "ml_research_storage_config": str(ml_research_storage_config.resolve()),
        "contract": _contract_fixture_descriptor(saved),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)


def _verify_contract_from_pins(descriptor: Mapping[str, Any]):
    """以原合成文件 pins 與 public lineage reader 重建唯讀 verifier。"""

    from ml_module.model_artifact_manifest import ModelArtifactManifest
    from ml_module.personal_h20_gross_model_contract import H20GrossModelContract
    from ml_module.recommendation_training_lineage import read_recommendation_training_lineage

    contract_data = dict(descriptor["contract_fields"])
    contract_data["feature_schema"] = tuple(
        tuple(row) for row in contract_data["feature_schema"]
    )
    contract_data["installed_library_versions"] = dict(
        contract_data["installed_library_versions"]
    )
    contract = H20GrossModelContract(**contract_data)
    binding = dict(descriptor["contract_binding"])
    marker_path = Path(descriptor["marker_path"])
    artifact_root = Path(descriptor["artifact_root"])
    lineage_path = Path(descriptor["lineage_path"])
    manifest_path = artifact_root / "manifest.json"
    candidate_path = artifact_root / "candidate.json"

    def verify(value: Mapping[str, Any]) -> Mapping[str, Any]:
        if dict(value) != binding:
            raise ValueError("fresh_process_contract_binding_mismatch")
        expected = {
            marker_path: str(descriptor["marker_sha256"]),
            artifact_root / "model.joblib": contract.artifact_hash,
            manifest_path: contract.manifest_raw_sha256,
            candidate_path: contract.candidate_raw_sha256,
            lineage_path: contract.lineage_raw_sha256,
        }
        for file_path, pin in expected.items():
            actual = "sha256:" + hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual != pin:
                raise ValueError("fresh_process_contract_source_pin_mismatch")

        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if (
            marker.get("schema") != "synthetic-h20-ui-contract-fixture.v1"
            or marker.get("fit_performed") is not False
            or marker.get("production_activation") is not False
        ):
            raise ValueError("fresh_process_synthetic_marker_invalid")

        manifest_body = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ModelArtifactManifest.from_dict(manifest_body)
        if (
            manifest.manifest_hash != contract.manifest_hash
            or manifest.artifact_hash != contract.artifact_hash
            or manifest.model_id != contract.model_id
            or manifest.dataset_id != contract.dataset_id
            or manifest.feature_schema != contract.feature_schema
        ):
            raise ValueError("fresh_process_artifact_manifest_identity_mismatch")

        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        if (
            candidate.get("candidate_id") != contract.candidate_id
            or candidate.get("model_id") != contract.model_id
            or candidate.get("manifest_hash") != contract.manifest_hash
            or candidate.get("artifact_hash") != contract.artifact_hash
            or candidate.get("lineage_hash") != contract.lineage_hash
            or candidate.get("training_source_hash") != contract.training_source_hash
            or candidate.get("training_pit_hash") != contract.training_pit_hash
            or candidate.get("fit_performed") is not False
        ):
            raise ValueError("fresh_process_candidate_identity_mismatch")

        lineage = read_recommendation_training_lineage(
            lineage_path,
            expected_manifest_hash=contract.lineage_hash,
            expected_dataset_hash=contract.dataset_hash,
            expected_candidate_id=contract.candidate_id,
        )
        if (
            lineage.manifest_hash != contract.lineage_hash
            or lineage.payload.get("training_source_hash") != contract.training_source_hash
            or lineage.payload.get("training_pit_hash") != contract.training_pit_hash
        ):
            raise ValueError("fresh_process_lineage_identity_mismatch")
        if contract.contract_hash != binding.get("contract_hash"):
            raise ValueError("fresh_process_contract_hash_mismatch")

        verified = {
            "candidate_id": contract.candidate_id,
            "contract_hash": contract.contract_hash,
            "artifact_hash": contract.artifact_hash,
            "lineage_hash": contract.lineage_hash,
            "fit_receipt_sha256": binding["fit_receipt_sha256"],
            "model_id": contract.model_id,
            "model_version": contract.model_version,
            "fit_receipt_path": binding["fit_receipt_path"],
            "artifact_root": contract.artifact_root,
            "feature_schema": [list(row) for row in contract.feature_schema],
        }
        if verified != binding:
            raise ValueError("fresh_process_verified_contract_binding_mismatch")
        return verified

    return verify


def _deny_network_and_source_sql_writes(
    source_database: Path,
) -> tuple[Callable[[], None], Callable[..., Any], dict[str, int]]:
    """阻擋網路，並強制原 snapshot SQLite 只能以 read-only/query-only 開啟。"""

    original_connect = sqlite3.connect
    original_socket_connect = socket.socket.connect
    original_socket_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    counts = {"source_readonly_connections": 0, "network_attempts": 0}
    target = os.path.normcase(str(source_database.resolve()))

    def deny_network(*_args: object, **_kwargs: object) -> Any:
        counts["network_attempts"] += 1
        raise AssertionError("synthetic H20 fresh-process journey attempted network access")

    def source_path(database: object) -> tuple[Path | None, str]:
        if not isinstance(database, (str, os.PathLike)):
            return None, ""
        rendered = os.fspath(database)
        if not isinstance(rendered, str) or not rendered.startswith("file:"):
            try:
                return Path(rendered).resolve(), ""
            except (OSError, ValueError):
                return None, ""
        payload = rendered[5:]
        path_text, _, query = payload.partition("?")
        path_text = unquote(path_text)
        if len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
            path_text = path_text[1:]
        try:
            return Path(path_text).resolve(), query.casefold()
        except (OSError, ValueError):
            return None, query.casefold()

    write_actions = {
        getattr(sqlite3, name)
        for name in (
            "SQLITE_INSERT", "SQLITE_UPDATE", "SQLITE_DELETE", "SQLITE_CREATE_INDEX",
            "SQLITE_CREATE_TABLE", "SQLITE_CREATE_TEMP_INDEX", "SQLITE_CREATE_TEMP_TABLE",
            "SQLITE_CREATE_TEMP_TRIGGER", "SQLITE_CREATE_TEMP_VIEW", "SQLITE_CREATE_TRIGGER",
            "SQLITE_CREATE_VIEW", "SQLITE_DROP_INDEX", "SQLITE_DROP_TABLE",
            "SQLITE_DROP_TEMP_INDEX", "SQLITE_DROP_TEMP_TABLE", "SQLITE_DROP_TEMP_TRIGGER",
            "SQLITE_DROP_TEMP_VIEW", "SQLITE_DROP_TRIGGER", "SQLITE_DROP_VIEW",
            "SQLITE_ALTER_TABLE", "SQLITE_REINDEX", "SQLITE_ANALYZE", "SQLITE_ATTACH",
            "SQLITE_DETACH",
        )
        if hasattr(sqlite3, name)
    }

    def guarded_connect(database: Any, *args: Any, **kwargs: Any):
        resolved, query = source_path(database)
        is_source = resolved is not None and os.path.normcase(str(resolved)) == target
        if not is_source:
            return original_connect(database, *args, **kwargs)
        if "mode=ro" not in query or kwargs.get("uri") is not True:
            raise AssertionError("original H20 source SQLite must be opened with URI mode=ro")
        connection = original_connect(database, *args, **kwargs)
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute("PRAGMA query_only").fetchone()
        if row != (1,):
            connection.close()
            raise AssertionError("original H20 source SQLite query_only could not be enabled")

        def deny_sql_write(action: int, *_args: object) -> int:
            if action in write_actions:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(deny_sql_write)
        counts["source_readonly_connections"] += 1
        return connection

    setattr(socket.socket, "connect", deny_network)
    setattr(socket.socket, "connect_ex", deny_network)
    setattr(socket, "create_connection", deny_network)
    setattr(sqlite3, "connect", guarded_connect)

    def restore() -> None:
        setattr(sqlite3, "connect", original_connect)
        setattr(socket.socket, "connect", original_socket_connect)
        setattr(socket.socket, "connect_ex", original_socket_connect_ex)
        setattr(socket, "create_connection", original_create_connection)

    return restore, deny_network, counts


def _fresh_process_reopen(descriptor_path: str) -> None:
    lifecycle: dict[str, Any] = {}
    try:
        _fresh_process_reopen_impl(descriptor_path, lifecycle)
    finally:
        cleanup = lifecycle.get("cleanup_window")
        if callable(cleanup):
            cleanup("child_process_finalizer")
        restore = lifecycle.get("restore_guards")
        if callable(restore):
            restore()


def _fresh_process_reopen_impl(descriptor_path: str, lifecycle: dict[str, Any]) -> None:
    """子程序入口：由新 MainWindow 與真 WatchlistControls exact 重開。"""

    from scripts.scheduled import run_personal_current_observed_h20_daily as runner
    from ui_qt.main import MainWindow, _drain_qt_deferred_deletes
    from ui_qt.workers.task_worker import TaskWorker

    descriptor_file = Path(descriptor_path)
    descriptor = json.loads(descriptor_file.read_text(encoding="utf-8"))
    stage_trace_path = Path(descriptor["stage_trace_path"])
    process_started = time.monotonic()

    def trace(stage: str, detail: str = "") -> None:
        event = {
            "elapsed_seconds": round(time.monotonic() - process_started, 6),
            "pid": os.getpid(),
            "stage": stage,
            "detail": detail[:2000],
        }
        with stage_trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()

    def wait_stage(stage: str, predicate: Any, *, timeout_seconds: float = 90.0) -> None:
        trace(stage + "_started")
        try:
            _wait_for(app, predicate, timeout_seconds=timeout_seconds)
        except BaseException as exc:
            trace(stage + "_failed", f"{type(exc).__name__}: {exc}")
            cleanup_window(stage + "_failed")
            raise
        trace(stage + "_completed")

    app: QApplication | None = None
    window: MainWindow | None = None
    cleanup_started = False

    def cleanup_window(reason: str) -> None:
        nonlocal cleanup_started
        if cleanup_started or app is None or window is None:
            return
        cleanup_started = True
        trace("mainwindow_failure_shutdown_started", reason)
        try:
            _close_mainwindow(app, window)
            trace("mainwindow_failure_shutdown_completed")
        except BaseException as exc:
            trace("mainwindow_failure_shutdown_failed", f"{type(exc).__name__}: {exc}")

    lifecycle["cleanup_window"] = cleanup_window

    if descriptor.get("schema_version") != "personal-h20-fresh-process-test.v1":
        raise AssertionError("fresh-process descriptor schema mismatch")
    parent_pid = descriptor.get("parent_pid")
    child_pid = os.getpid()
    if type(parent_pid) is not int or child_pid == parent_pid:
        raise AssertionError("fresh-process PID identity invalid")
    expected_inventory = descriptor["source_inventory"]
    trace("source_inventory_before_started")
    initial_inventory = [_file_pin(Path(item["path"])) for item in expected_inventory]
    if initial_inventory != expected_inventory:
        raise AssertionError("source inventory differs before child read")
    trace("source_inventory_before_completed", f"files={len(initial_inventory)}")

    source_database = Path(descriptor["source_database"])
    storage_config = Path(descriptor["ml_research_storage_config"])
    if os.environ.get("BALDR_ML_RESEARCH_STORAGE_CONFIG") != str(storage_config):
        raise AssertionError("child ML research storage config env does not pin this fixture")
    storage_config_body = json.loads(storage_config.read_text(encoding="utf-8"))
    if (
        storage_config_body.get("schema_version") != "ml-research-storage.v1"
        or storage_config_body.get("active_root") != descriptor["research_output_root"]
    ):
        raise AssertionError("child ML research storage config does not select exact fixture root")
    restore_guards, _deny_network, guard_counts = _deny_network_and_source_sql_writes(source_database)
    lifecycle["restore_guards"] = restore_guards
    actual_source_port = runner._source_port

    def source_verifier(binding: Mapping[str, Any]) -> Mapping[str, Any]:
        trace(
            "source_verifier_started",
            json.dumps(
                {
                    "cycle_id": binding.get("cycle_id"),
                    "data_root": binding.get("data_root"),
                    "decision_date": binding.get("decision_date"),
                    "symbols": binding.get("symbols"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        try:
            result = actual_source_port(binding)
        except BaseException as exc:
            trace("source_verifier_failed", f"{type(exc).__name__}: {exc!r}")
            raise
        trace("source_verifier_completed", "public runner._source_port returned its binding")
        return result

    contract_verifier = _verify_contract_from_pins(descriptor["contract"])

    def observed_contract_verifier(binding: Mapping[str, Any]) -> Mapping[str, Any]:
        trace("contract_verifier_started", str(binding.get("candidate_id", "")))
        try:
            result = contract_verifier(binding)
        except BaseException as exc:
            trace("contract_verifier_failed", f"{type(exc).__name__}: {exc!r}")
            raise
        trace("contract_verifier_completed")
        return result

    runner.personal_current_observed_h20_read_ports = lambda: {
        "source_verifier": source_verifier,
        "contract_verifier": observed_contract_verifier,
    }

    import app_module.recommendation.personal_h20_product_evidence as product_evidence_module

    latest_reference_calls: list[str] = []

    def deny_latest_reference(*_args: Any, **_kwargs: Any) -> Any:
        latest_reference_calls.append("read_personal_h20_product_reference")
        raise AssertionError("bookmark route must not read the current H20 product pointer")

    product_evidence_module.read_personal_h20_product_reference = deny_latest_reference

    import scripts.scheduled.personal_h20_bookmark_read_session as bookmark_session_module
    original_bookmark_reader = bookmark_session_module.read_personal_h20_research_bookmark

    def observed_bookmark_reader(*args: Any, **kwargs: Any) -> Any:
        result = original_bookmark_reader(*args, **kwargs)
        trace(
            "bookmark_pass_state",
            json.dumps(
                {
                    "selected_row": {
                        "symbol": result.selected_row.symbol,
                        "status": result.selected_row.status,
                        "reason": result.selected_row.reason,
                        "observed_at": result.selected_row.observed_at,
                        "capture_sha256": result.selected_row.capture_sha256,
                    },
                    "manifest_sha256": result.cohort.manifest_sha256,
                    "rows": [
                        {"symbol": row.symbol, "status": row.status, "reason": row.reason}
                        for row in result.cohort.rows
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        return result

    bookmark_session_module.read_personal_h20_research_bookmark = observed_bookmark_reader

    original_bookmark_session_reader = (
        bookmark_session_module.read_personal_h20_research_bookmark_with_session
    )

    def observed_bookmark_session_reader(*args: Any, **kwargs: Any) -> Any:
        trace("bookmark_session_started")
        outer_progress = kwargs.pop("progress_callback", None)

        def report_progress(message: str) -> None:
            trace("bookmark_session_progress", message)
            if callable(outer_progress):
                outer_progress(message)

        try:
            result = original_bookmark_session_reader(
                *args, **kwargs, progress_callback=report_progress
            )
        except BaseException as exc:
            trace("bookmark_session_failed", f"{type(exc).__name__}: {exc}")
            raise
        trace("bookmark_session_completed")
        return result

    bookmark_session_module.read_personal_h20_research_bookmark_with_session = (
        observed_bookmark_session_reader
    )

    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    trace("mainwindow_construct_started")
    window = MainWindow()
    lifecycle["app"] = app
    lifecycle["window"] = window
    trace("mainwindow_construct_completed")
    window.show()
    app.processEvents()
    window.left_navigation.button_for_key("watchlist").click()
    controls = window.watchlist_view.personal_h20_bookmark_controls
    if controls is None:
        raise AssertionError("real MainWindow did not configure H20 bookmark controls")

    bookmark_id = str(descriptor["bookmark_id"])
    expected_bookmark = dict(descriptor["bookmark"])
    wait_stage(
        "watchlist_h20_bookmarks_refresh",
        lambda: controls._worker is None
        and controls.bookmarks.count() == 1
        and controls._has_loaded_list,
        timeout_seconds=90.0,
    )
    if controls.restore_selection(bookmark_id) != "selected":
        raise AssertionError(
            f"fresh process could not select exact bookmark: {controls.status_label.text()}"
        )
    item = controls.bookmarks.currentItem()
    entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
    if entry is None or entry.bookmark is None or entry.bookmark.to_dict() != expected_bookmark:
        raise AssertionError("fresh Watchlist row does not match the exact saved bookmark")

    trace("bookmark_open_button_clicked", bookmark_id)
    controls.open_button.click()
    workspace = window.stock_research_workspace

    def bookmark_summary_settled() -> bool:
        evidence = workspace.personal_h20_saved_evidence
        if evidence is None or workspace.personal_h20_saved_busy:
            return False
        status = getattr(evidence, "status", None)
        if status != "available":
            trace(
                "bookmark_summary_unavailable",
                f"status={status}; reason={getattr(evidence, 'reason', '')}",
            )
            return True
        return (
            getattr(workspace.report_view.context, "source_kind", None)
            == "personal_h20_research_bookmark"
            and "+12.34%" in workspace.personal_h20_saved_summary.text()
        )

    wait_stage(
        "bookmark_summary_available",
        bookmark_summary_settled,
        timeout_seconds=120.0,
    )
    evidence = workspace.personal_h20_saved_evidence
    if evidence is None or getattr(evidence, "status", None) != "available":
        reason = "missing" if evidence is None else getattr(evidence, "reason", "")
        cleanup_window("bookmark_summary_unavailable")
        raise AssertionError(f"exact saved bookmark could not be reopened: {reason}")
    trace("bookmark_summary_text", workspace.personal_h20_saved_summary.text())
    state = window._personal_h20_bookmark_origin[1]
    if (
        state.bookmark.to_dict() != expected_bookmark
        or state.bookmark.bookmark_id != bookmark_id
        or state.bookmark.stock_code != "2382"
        or state.bookmark.sort_descending is not True
        or state.bookmark.scroll_position != 0
        or state.selected_row.symbol != "2382"
        or state.selected_row.gross_return_bp != 1234
        or state.selected_row.status != "available"
        or state.selected_row.observed_at != descriptor["observed_at"]
        or state.selected_row.capture_sha256 != expected_bookmark["selected_row"]["capture_sha256"]
        or state.cohort.manifest_sha256 != expected_bookmark["manifest_sha256"]
    ):
        raise AssertionError("fresh MainWindow reopened a different H20 bookmark/source row")
    if not workspace.personal_h20_saved_summary.toolTip() or descriptor["observed_at"] not in workspace.personal_h20_saved_summary.toolTip():
        raise AssertionError("saved summary tooltip lost the original observed_at value")
    if latest_reference_calls:
        raise AssertionError(f"bookmark route consulted the current pointer: {latest_reference_calls!r}")
    if guard_counts["source_readonly_connections"] < 1:
        raise AssertionError("the real H20 source verifier did not open the pinned SQLite read-only")
    if guard_counts["network_attempts"] != 0:
        raise AssertionError("network access was attempted")

    exact_context_id = workspace.report_view.context.source_id
    if exact_context_id != bookmark_id:
        raise AssertionError("MainWindow research context lost the original bookmark ID")
    trace("return_button_clicked", bookmark_id)
    workspace.report_view.return_button.click()
    wait_stage(
        "watchlist_return_exact_bookmark",
        lambda: controls._worker is None
        and controls.bookmarks.count() == 1
        and controls._current_entry() is not None
        and controls._current_entry().bookmark_id == bookmark_id,
        timeout_seconds=90.0,
    )
    trace("watchlist_returned_exact_bookmark", bookmark_id)
    if window.left_navigation.current_key() != "watchlist":
        raise AssertionError("return route did not restore the original Watchlist workspace")
    service = window.watchlist_service
    if not isinstance(service, WatchlistService):
        raise AssertionError("fresh MainWindow WatchlistService is unavailable")
    reopened = service.get_research_bookmark(bookmark_id)
    if not isinstance(reopened, PersonalH20ResearchBookmark) or reopened.to_dict() != expected_bookmark:
        raise AssertionError("Watchlist COW store changed during read-only reopen")

    final_inventory = [_file_pin(Path(item["path"])) for item in expected_inventory]
    if final_inventory != expected_inventory:
        raise AssertionError("source inventory changed during fresh-process read")
    receipt = {
        "schema_version": "personal-h20-fresh-process-receipt.v1",
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "bookmark_id": bookmark_id,
        "stock_code": state.selected_row.symbol,
        "gross_return_bp": state.selected_row.gross_return_bp,
        "manifest_sha256": state.cohort.manifest_sha256,
        "capture_sha256": state.selected_row.capture_sha256,
        "observed_at": state.selected_row.observed_at,
        "sort_descending": state.bookmark.sort_descending,
        "scroll_position": state.bookmark.scroll_position,
        "source_readonly_connections": guard_counts["source_readonly_connections"],
        "network_attempts": guard_counts["network_attempts"],
        "current_reference_reads": latest_reference_calls,
        "source_inventory_unchanged": True,
        "cow_bookmark_unchanged": True,
        "route": "real MainWindow -> Watchlist H20 open_button -> summary -> return exact ID",
        "elapsed_until_return_seconds": round(time.monotonic() - process_started, 6),
        "stage_trace_path": str(stage_trace_path),
    }
    trace("mainwindow_shutdown_started")
    window.close()
    _wait_for(app, lambda: not window.isVisible(), timeout_seconds=45.0)
    _drain_qt_deferred_deletes(app, (window,))
    trace("mainwindow_shutdown_completed")
    receipt["elapsed_seconds"] = round(time.monotonic() - process_started, 6)
    cleanup_started = True
    restore_guards()
    print(_RECEIPT_PREFIX + json.dumps(receipt, ensure_ascii=False, sort_keys=True))


def test_saved_h20_bookmark_reopens_in_new_mainwindow_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """程序間只傳 exact bookmark 與 fixture pins；兩個 MainWindow 都是真實實作。"""

    import json as json_module

    from tests.test_ui_qt_h20_saved_source_journey import _sha256_file

    parent_started = time.monotonic()
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path, monkeypatch
    )
    assert network_attempts == []
    fixture_root = tmp_path / "synthetic-h20-fixture"
    research_output_root = Path(saved["source_binding"]["pins"]["research_output_root"]).resolve()
    child_storage_config = fixture_root / "ml-research-storage-fresh-process.json"
    assert not child_storage_config.exists(), "fresh-process config path must be new in this attempt"
    child_storage_config_body = {
        "schema_version": "ml-research-storage.v1",
        "active_root": str(research_output_root),
    }
    with child_storage_config.open("xb") as config_handle:
        config_handle.write(
            json_module.dumps(
                child_storage_config_body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        config_handle.flush()
        os.fsync(config_handle.fileno())
    inventory_before = _source_inventory(
        saved, fixture_root, extra_paths=(child_storage_config,)
    )
    child_stdout = tmp_path / "fresh-process-stdout.log"
    child_stderr = tmp_path / "fresh-process-stderr.log"
    child_receipt_path = tmp_path / "fresh-process-receipt.json"
    descriptor_path = tmp_path / "fresh-process-input.json"
    stage_trace_path = tmp_path / "stage-trace.jsonl"
    stage_trace_path.touch()

    def parent_trace(stage: str, detail: str = "") -> None:
        event = {
            "elapsed_seconds": round(time.monotonic() - parent_started, 6),
            "pid": os.getpid(),
            "stage": stage,
            "detail": detail[:400],
        }
        with stage_trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json_module.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()

    parent_trace("parent_main_constructor_and_fixture_completed")
    parent_pid = os.getpid()
    child_pid: int | None = None
    try:
        window.show()
        parent_trace("parent_h20_save_started")
        service, controls, bookmark_id = _save_and_find(app, window)
        parent_trace("parent_h20_save_and_watchlist_refresh_completed", bookmark_id)
        parent_inventory = _source_inventory(
            saved, fixture_root, extra_paths=(child_storage_config,)
        )
        parent_changes = _inventory_changes(inventory_before, parent_inventory)
        parent_trace(
            "parent_source_inventory_after_save",
            json_module.dumps(parent_changes, ensure_ascii=False, sort_keys=True),
        )
        assert not parent_changes, (
            "original H20 source/contract files changed during parent save/read: "
            f"{json_module.dumps(parent_changes, ensure_ascii=False, sort_keys=True)}"
        )
        bookmark = service.get_research_bookmark(bookmark_id)
        assert isinstance(bookmark, PersonalH20ResearchBookmark)
        assert bookmark.stock_code == "2382"
        assert bookmark.sort_descending is (window.personal_h20_research_widget.sort_combo.currentIndex() == 0)
        assert bookmark.scroll_position == window.personal_h20_research_widget.table.verticalScrollBar().value()
        assert bookmark.scroll_position == 0

        capture_pin = saved["manifest"]["captures"][0]
        capture_body = json_module.loads(Path(capture_pin["path"]).read_text(encoding="utf-8"))
        assert "observed_at" in capture_body
        parent_trace("source_inventory_before_child", f"files={len(inventory_before)}")
        _write_descriptor(
            path=descriptor_path,
            parent_pid=parent_pid,
            bookmark=bookmark,
            saved=saved,
            fixture_root=fixture_root,
            observed_at=capture_body["observed_at"],
            stage_trace_path=stage_trace_path,
            ml_research_storage_config=child_storage_config,
        )
        assert _source_inventory(
            saved, fixture_root, extra_paths=(child_storage_config,)
        ) == inventory_before
        assert service.get_research_bookmark(bookmark_id).to_dict() == bookmark.to_dict()
        assert controls._current_entry() is not None
        assert controls._current_entry().bookmark_id == bookmark_id

        _close_mainwindow(app, window)
        parent_trace("parent_mainwindow_closed")
        for name in (
            "_personal_h20_cohort_worker",
            "_personal_h20_bookmark_worker",
            "_personal_h20_worker",
        ):
            worker = getattr(window, name, None)
            if worker is not None:
                try:
                    assert not worker.isRunning(), f"parent MainWindow still has worker {name}"
                except RuntimeError:
                    pass  # Qt 已銷毀的 worker 不能再執行。

        child_code = (
            "import sys; "
            "from tests.test_ui_qt_personal_h20_bookmark_fresh_process import "
            "_fresh_process_reopen; "
            "_fresh_process_reopen(sys.argv[1])"
        )
        child_environment = os.environ.copy()
        child_environment["PYTHONUTF8"] = "1"
        child_environment["PYTHONIOENCODING"] = "utf-8"
        child_environment["PYTHONUNBUFFERED"] = "1"
        child_environment["BALDR_ML_RESEARCH_STORAGE_CONFIG"] = str(
            child_storage_config.resolve()
        )
        parent_trace("fresh_process_spawn_started")
        timed_out = False
        with child_stdout.open("wb") as stdout_handle, child_stderr.open("wb") as stderr_handle:
            process = subprocess.Popen(
                [sys.executable, "-c", child_code, str(descriptor_path)],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=child_environment,
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
            try:
                return_code = process.wait(timeout=240)
            except subprocess.TimeoutExpired:
                timed_out = True
                parent_trace("fresh_process_timeout", f"pid={process.pid}; timeout_seconds=240")
                process.terminate()
                try:
                    return_code = process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    return_code = process.wait(timeout=15)
        stdout_text = child_stdout.read_text(encoding="utf-8", errors="replace")
        stderr_text = child_stderr.read_text(encoding="utf-8", errors="replace")
        parent_trace("fresh_process_exited", f"pid={process.pid}; return_code={return_code}")
        completed = subprocess.CompletedProcess(
            args=process.args,
            returncode=return_code,
            stdout=stdout_text,
            stderr=stderr_text,
        )
        receipt_line = next(
            (line for line in completed.stdout.splitlines() if line.startswith(_RECEIPT_PREFIX)),
            None,
        )
        if receipt_line is not None:
            receipt = json_module.loads(receipt_line[len(_RECEIPT_PREFIX):])
            child_receipt_path.write_text(
                json_module.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            child_pid = receipt.get("child_pid")
        assert not timed_out, (
            f"fresh-process child exceeded the existing 240-second bound; "
            f"stdout={child_stdout}; stderr={child_stderr}; stage_trace={stage_trace_path}"
        )
        assert completed.returncode == 0, (
            f"fresh-process child failed with exit {completed.returncode}; "
            f"stdout={child_stdout}; stderr={child_stderr}; "
            f"stdout_tail={completed.stdout[-2500:]!r}; stderr_tail={completed.stderr[-4000:]!r}; "
            f"stage_trace={stage_trace_path}"
        )
        assert receipt_line is not None, (
            f"fresh-process receipt missing; stdout={child_stdout}; stderr={child_stderr}"
        )
        receipt = json_module.loads(receipt_line[len(_RECEIPT_PREFIX):])
        assert receipt["parent_pid"] == parent_pid
        assert type(receipt["child_pid"]) is int and receipt["child_pid"] != parent_pid
        assert receipt["bookmark_id"] == bookmark_id
        assert (receipt["stock_code"], receipt["gross_return_bp"]) == ("2382", 1234)
        assert receipt["manifest_sha256"] == bookmark.manifest_sha256
        assert receipt["capture_sha256"] == bookmark.selected_row.capture_sha256
        assert receipt["observed_at"] == capture_body["observed_at"]
        assert receipt["sort_descending"] is bookmark.sort_descending
        assert receipt["scroll_position"] == bookmark.scroll_position
        assert receipt["source_readonly_connections"] >= 1
        assert receipt["network_attempts"] == 0
        assert receipt["current_reference_reads"] == []
        assert receipt["source_inventory_unchanged"] is True
        assert receipt["cow_bookmark_unchanged"] is True
        child_events = [
            json_module.loads(line)
            for line in stage_trace_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        stage_starts: dict[str, list[float]] = {}
        stage_elapsed: dict[str, list[float]] = {}
        for event in child_events:
            if event["pid"] != receipt["child_pid"]:
                continue
            if event["stage"].endswith("_started"):
                stage_starts.setdefault(event["stage"][:-8], []).append(
                    event["elapsed_seconds"]
                )
            elif event["stage"].endswith("_completed"):
                stage_name = event["stage"][:-10]
                pending_starts = stage_starts.get(stage_name, [])
                if pending_starts:
                    started_at = pending_starts.pop(0)
                    stage_elapsed.setdefault(stage_name, []).append(
                        max(0.0, event["elapsed_seconds"] - started_at)
                    )
        stage_durations = {
            name: round(sum(durations), 6)
            for name, durations in stage_elapsed.items()
        }
        receipt["stage_elapsed_seconds"] = stage_durations
        receipt["stage_duration_counts"] = {
            name: len(durations) for name, durations in stage_elapsed.items()
        }
        receipt["stage_duration_samples_seconds"] = {
            name: [round(duration, 6) for duration in durations]
            for name, durations in stage_elapsed.items()
        }
        required_timing_stages = {
            "mainwindow_construct",
            "watchlist_h20_bookmarks_refresh",
            "bookmark_session",
            "bookmark_summary_available",
            "source_verifier",
            "watchlist_return_exact_bookmark",
            "mainwindow_shutdown",
        }
        assert required_timing_stages <= set(receipt["stage_elapsed_seconds"])
        assert receipt["stage_duration_counts"]["source_verifier"] == 2
        assert receipt["stage_duration_counts"]["contract_verifier"] == 2
        child_receipt_path.write_text(
            json_module.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        assert _source_inventory(
            saved, fixture_root, extra_paths=(child_storage_config,)
        ) == inventory_before
        assert network_attempts == []
        assert _sha256_file(Path(saved["snapshot_database"])) == "sha256:" + next(
            item["sha256"] for item in inventory_before
            if item["path"] == str(Path(saved["snapshot_database"]).resolve())
        )
    finally:
        _close_mainwindow(app, window)
