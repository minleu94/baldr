"""真 MainWindow 的隔離 H20 保存名單下鑽旅程。

來源、candidate、artifact、lineage 與 capture 都由合成 fixture 建立；不訓練、
不讀正式資料，也不代表正式模型資格。只替換 runner 的 verifier-port factory，
產品 reader、cohort reader、TaskWorker、MainWindow 與 Qt 點擊路徑保持真實。
"""

from __future__ import annotations

import os
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from ui_qt.main import MainWindow, _drain_qt_deferred_deletes
from ui_qt.workers.task_worker import TaskWorker


def _configure_isolated_environment(
    tmp_path: Path,
    market_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    from tests.test_ui_qt_main_fulln_bookmark_journey import _ISOLATED_ENVIRONMENT_KEYS

    output_root = tmp_path / "output"
    state_root = tmp_path / "research-state"
    h20_sqlite_read_root = tmp_path / "personal-h20-sqlite-read"
    temp_root = tmp_path / "temporary"
    local_root = tmp_path / "localapp"
    roaming_root = tmp_path / "appdata"
    active_ml_root = tmp_path / "ml-research-output"
    temp_root.mkdir(parents=True, exist_ok=True)
    h20_sqlite_read_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    environment_keys = set(_ISOLATED_ENVIRONMENT_KEYS)
    environment_keys.add("PHASE3C_CANDIDATE_DB_PATH")
    for key in environment_keys:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DATA_ROOT", str(market_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("RESEARCH_STATE_ROOT", str(state_root))
    monkeypatch.setenv("TEMP", str(temp_root))
    monkeypatch.setenv("TMP", str(temp_root))
    monkeypatch.setenv("LOCALAPPDATA", str(local_root))
    monkeypatch.setenv("APPDATA", str(roaming_root))
    monkeypatch.setenv("BALDR_CONFIG", str(tmp_path / "baldr-config.json"))
    monkeypatch.setenv("PROFILE", "prod")
    monkeypatch.setenv("PERSONAL_MODEL_POLICY_PATH", str(state_root / "personal-use-policy.json"))
    monkeypatch.setenv("PHASE3C_CANDIDATE_DB_PATH", str(tmp_path / "candidate" / "candidate.sqlite"))
    monkeypatch.setenv("OFFICIAL_CALENDAR_CACHE_PATH", str(market_root / "calendar-cache.json"))
    monkeypatch.setenv("MPLCONFIGDIR", str(output_root / "application_state" / "matplotlib"))
    monkeypatch.setenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", str(state_root / "recommendation-learning"))
    monkeypatch.setenv("PERSONAL_H20_SQLITE_READ_ROOT", str(h20_sqlite_read_root))

    storage_config = tmp_path / "ml-research-storage.json"
    storage_config.write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(active_ml_root),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BALDR_ML_RESEARCH_STORAGE_CONFIG", str(storage_config))
    return output_root, temp_root


def _install_network_deny(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def deny(*_args: object, **_kwargs: object) -> None:
        attempts.append("socket connection attempted")
        raise AssertionError("synthetic MainWindow H20 journey must not use provider network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    return attempts


def _wait_for(app: QApplication, predicate: Any, *, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    app.processEvents()
    assert predicate(), "真 MainWindow H20 保存來源旅程逾時"


def _double_click_selected_h20_row(app: QApplication, window: MainWindow, widget: Any) -> dict[str, list[Any]]:
    matches = [
        row for row in range(widget.table.rowCount())
        if widget.table.item(row, 0) is not None and widget.table.item(row, 0).text() == "2382"
    ]
    assert len(matches) == 1
    row = matches[0]
    item = widget.table.item(row, 0)
    assert item is not None
    widget.table.scrollToItem(item)
    widget.table.setCurrentItem(item)
    widget.table.selectRow(row)
    signals: dict[str, list[Any]] = {"item_double_clicked": [], "research_requested": []}
    widget.table.itemDoubleClicked.connect(
        lambda value: signals["item_double_clicked"].append(value.text())
    )
    widget.researchRequested.connect(
        lambda value: signals["research_requested"].append(value)
    )
    window.recommendation_view.result_scroll.ensureWidgetVisible(widget.table)
    app.processEvents()
    position = widget.table.visualItemRect(item).center()
    assert window.isVisible() and widget.isVisible() and widget.table.isVisible()
    assert widget.table.viewport().rect().intersects(widget.table.visualItemRect(item)), (
        f"2382 列未出現在 viewport：row={row}; rect={widget.table.visualItemRect(item)!r}; "
        f"viewport={widget.table.viewport().rect()!r}; page={widget.parentWidget()!r}"
    )
    assert widget.research_button.isEnabled()
    # Qt 的 double-click sequence 先經過真實 click，再由 QTest 送出 double-click。
    # 只觀察訊號，不直接 emit 或呼叫 MainWindow handler。
    QTest.mouseClick(widget.table.viewport(), Qt.MouseButton.LeftButton, pos=position)
    app.processEvents()
    QTest.mouseDClick(
        widget.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=position,
        delay=50,
    )
    app.processEvents()
    assert signals["item_double_clicked"] == ["2382"], (
        f"QTest 未送達表格 double-click：signals={signals!r}; "
        f"current_row={widget.table.currentRow()}; "
        f"selected_rows={[index.row() for index in widget.table.selectionModel().selectedRows()]!r}; "
        f"research_enabled={widget.research_button.isEnabled()}; "
        f"rect={widget.table.visualItemRect(item)!r}"
    )
    assert len(signals["research_requested"]) == 1, (
        f"double-click 未產生 H20 research request：signals={signals!r}; "
        f"diagnostic={widget.diagnostic_text.toPlainText()!r}"
    )
    # 目前已核 cohort 的有效選取會直接開 exact 個股來源，不再先重讀全名單。
    # 等到個股工作開始或完成，並確認沒有排入額外 cohort refresh。
    selected = signals["research_requested"][0]
    workspace = window.stock_research_workspace

    def selected_route_started() -> bool:
        origin = getattr(window, "_personal_h20_research_origin", None)
        if not isinstance(origin, tuple) or len(origin) != 3 or workspace is None:
            return False
        return (
            getattr(window, "_personal_h20_cohort_worker", None) is None
            and origin[1] == selected
            and (
                getattr(window, "_personal_h20_worker", None) is not None
                or workspace.personal_h20_saved_busy
                or workspace.personal_h20_saved_evidence is not None
            )
        )

    _wait_for(
        app,
        selected_route_started,
        timeout_seconds=10.0,
    )
    assert getattr(window, "_personal_h20_cohort_worker", None) is None, (
        f"點選已核 H20 股票不應重讀完整名單：signals={signals!r}; "
        f"status={window.statusBar().currentMessage()!r}"
    )
    origin = getattr(window, "_personal_h20_research_origin", None)
    assert isinstance(origin, tuple) and len(origin) == 3 and origin[1] == selected
    return signals


def _prepare_saved_h20_mainwindow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_mode: dict[str, Any] | None = None,
    source_entered: threading.Event | None = None,
    source_release: threading.Event | None = None,
) -> tuple[QApplication, MainWindow, dict[str, Any], list[str], threading.local]:
    import data_module.config as config_module
    import scripts.scheduled.run_personal_current_observed_h20_daily as runner
    import ui_qt.workers.task_worker as worker_module
    from tests.test_ui_qt_h20_saved_source_journey import _build_saved_h20_store

    fixture_root = tmp_path / "synthetic-h20-fixture"
    market_root = fixture_root / "FA_Data"
    _configure_isolated_environment(fixture_root, market_root, monkeypatch)
    network_attempts = _install_network_deny(monkeypatch)

    original_config_type = config_module.TWStockConfig
    saved = _build_saved_h20_store(fixture_root, monkeypatch)
    # 舊 fixture helper 暫時替換 module attribute 以建資料；真 MainWindow 恢復使用
    # repository 的 TWStockConfig，並由隔離環境變數提供所有路徑。
    monkeypatch.setattr(config_module, "TWStockConfig", original_config_type)
    monkeypatch.setenv("PERSONAL_H20_ACTIVATION_CONFIG", str(saved["activation"].config_path))

    task_context = threading.local()
    mode = source_mode if source_mode is not None else {}
    entered = source_entered if source_entered is not None else threading.Event()
    release = source_release if source_release is not None else threading.Event()
    base_source_verifier = saved["source_verifier"]
    contract_verifier = saved["contract_fixture"]["verifier"]
    snapshot_database = Path(saved["snapshot_database"])

    def read_ports(*, read_session_resolver=None, raw_snapshot_observer=None):
        def source_verifier(binding: Any) -> Any:
            task_name = getattr(task_context, "task_name", "")
            is_product_read = task_name == "read_personal_h20_product_for_stock_with_session"
            is_cohort_read = task_name == "read_personal_h20_verified_cohort_view"
            if is_product_read or is_cohort_read:
                call_number = getattr(task_context, "source_call_number", 0) + 1
                task_context.source_call_number = call_number
                should_block_before = (
                    is_product_read
                    and mode.get("block_product_first_source")
                    and getattr(task_context, "product_operation_number", 0) == 1
                    and call_number == 1
                ) or (
                    is_cohort_read
                    and mode.get("block_cohort_operation_before")
                    == getattr(task_context, "cohort_operation_number", 0)
                    and call_number == 1
                )
                if should_block_before:
                    entered.set()
                    if not release.wait(timeout=45):
                        raise RuntimeError("fixture_h20_source_barrier_timeout")
                should_drift_product = (
                    is_product_read
                    and mode.get("drift_product_finish_source")
                    and getattr(task_context, "product_operation_number", 0) == 1
                    and call_number == 2
                )
                drift_cohort_operation = mode.get("drift_cohort_operation_number", 2)
                should_drift_cohort = (
                    is_cohort_read
                    and mode.get("drift_cohort_finish_source")
                    and getattr(task_context, "cohort_operation_number", 0) == drift_cohort_operation
                    and call_number == 2
                )
                if (should_drift_product or should_drift_cohort) and not mode.get("source_mutated"):
                    snapshot_database.write_bytes(snapshot_database.read_bytes() + b" ")
                    mode["source_mutated"] = True
            verifier_options: dict[str, Any] = {}
            if read_session_resolver is not None:
                verifier_options["read_session_resolver"] = read_session_resolver
            if raw_snapshot_observer is not None:
                verifier_options["raw_snapshot_observer"] = raw_snapshot_observer
            if not verifier_options:
                result = base_source_verifier(binding)
            else:
                result = base_source_verifier(binding, **verifier_options)
            if (
                (
                    is_product_read
                    and mode.get("block_product_first_source_after")
                    and getattr(task_context, "product_operation_number", 0) == 1
                )
                or (
                    is_cohort_read
                    and mode.get("block_cohort_operation_after")
                    == getattr(task_context, "cohort_operation_number", 0)
                )
            ) and getattr(task_context, "source_call_number", 0) == 1:
                entered.set()
                if not release.wait(timeout=45):
                    raise RuntimeError("fixture_h20_source_barrier_timeout")
            return result

        return {
            "source_verifier": source_verifier,
            "contract_verifier": contract_verifier,
        }

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", read_ports)

    import scripts.scheduled.personal_h20_daily_hook as daily_hook

    original_projection = daily_hook.project_personal_h20_verified_cohort_selection_with_reference

    def observed_projection(*args: Any, **kwargs: Any) -> Any:
        projection_number = int(mode.get("_warm_projection_count", 0)) + 1
        mode["_warm_projection_count"] = projection_number
        if mode.get("block_first_warm_projection") and projection_number == 1:
            entered.set()
            if not release.wait(timeout=45):
                raise RuntimeError("fixture_h20_projection_barrier_timeout")
        return original_projection(*args, **kwargs)

    monkeypatch.setattr(
        daily_hook,
        "project_personal_h20_verified_cohort_selection_with_reference",
        observed_projection,
    )

    class OperationTaggedTaskWorker(TaskWorker):
        def run(self) -> None:
            task_name = getattr(self.task_function, "__name__", type(self.task_function).__name__)
            task_context.task_name = task_name
            task_context.source_call_number = 0
            if task_name == "read_personal_h20_verified_cohort_view":
                cohort_number = int(mode.get("_cohort_operation_count", 0)) + 1
                mode["_cohort_operation_count"] = cohort_number
                task_context.cohort_operation_number = cohort_number
            elif task_name == "read_personal_h20_product_for_stock_with_session":
                product_number = int(mode.get("_product_operation_count", 0)) + 1
                mode["_product_operation_count"] = product_number
                task_context.product_operation_number = product_number
            try:
                super().run()
            finally:
                task_context.task_name = ""

    monkeypatch.setattr(worker_module, "TaskWorker", OperationTaggedTaskWorker)

    # 主個股服務也只看到相同隔離的合成 SQLite；H20 capture 的原始來源仍是
    # fixture pin 指向的獨立 immutable snapshot。
    config = original_config_type()
    report_database = Path(config.db_file)
    report_database.parent.mkdir(parents=True, exist_ok=True)
    report_database.write_bytes(snapshot_database.read_bytes())

    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    window = MainWindow()
    assert isinstance(window, MainWindow)
    assert window.config.data_root.resolve() == Path(saved["market_root"]).resolve()
    assert window.config.output_root.resolve() == (fixture_root / "output").resolve()
    return app, window, saved, network_attempts, task_context


def _load_h20_list(app: QApplication, window: MainWindow) -> Any:
    window.left_navigation.button_for_key("recommendation").click()
    widget = window.personal_h20_research_widget
    panel = window.personal_h20_research_panel
    window.recommendation_view.result_source_tabs.setCurrentWidget(panel)
    _wait_for(
        app,
        lambda: getattr(window, "_personal_h20_cohort_worker", None) is None
        and widget._cohort is not None,
    )
    assert widget.table.rowCount() == 1
    first_item = widget.table.item(0, 0)
    assert first_item is not None and first_item.text() == "2382"
    return widget


def _close_mainwindow(app: QApplication, window: MainWindow) -> None:
    try:
        if window.isVisible():
            window.close()
            _wait_for(app, lambda: not window.isVisible(), timeout_seconds=45.0)
        _drain_qt_deferred_deletes(app, (window,))
    except RuntimeError:
        pass


def test_actual_mainwindow_h20_double_click_summary_return_recheck_and_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode: dict[str, Any] = {"drift_cohort_finish_source": False}
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path, monkeypatch, source_mode=mode
    )
    original_source_bytes = Path(saved["snapshot_database"]).read_bytes()
    mutated_source_path = Path(saved["snapshot_database"])
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        assert widget._cohort.manifest_sha256 == saved["manifest_sha256"]
        from app_module.recommendation.personal_h20_verified_cohort_view import (
            PersonalH20VerifiedCohortView,
        )
        assert type(window._personal_h20_cohort_view) is PersonalH20VerifiedCohortView
        assert mode.get("_cohort_operation_count") == 1

        double_click_signals = _double_click_selected_h20_row(app, window, widget)
        workspace = window.stock_research_workspace
        assert workspace is not None
        report_view = workspace.report_view
        _wait_for(
            app,
            lambda: getattr(report_view.context, "source_kind", None) == "personal_h20_saved_cohort"
            and getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )
        evidence = workspace.personal_h20_saved_evidence
        assert evidence is not None
        assert double_click_signals["research_requested"]
        assert evidence.stock_code == "2382"
        assert evidence.gross_return_bp == 1234
        from app_module.recommendation.personal_h20_price_chart import (
            PersonalH20PriceChartProjectionV1,
        )
        chart_projection = report_view._personal_h20_price_chart_projection
        assert type(chart_projection) is PersonalH20PriceChartProjectionV1
        assert chart_projection.status == "available"
        assert chart_projection.capture_sha256 == widget._cohort.rows[0].capture_sha256
        assert report_view.personal_h20_price_chart_group.isVisible()
        assert report_view.personal_h20_price_table.model().rowCount() > 0
        assert mode.get("_warm_projection_count") == 1
        assert mode.get("_product_operation_count", 0) == 0
        reference = getattr(window, "_personal_h20_saved_reference", None)
        assert reference is not None and reference.manifest_sha256 == saved["manifest_sha256"]
        assert "2382｜保存的個人 H20 研究預測（未扣成本）：+12.34%" in workspace.personal_h20_saved_summary.text()

        first_evidence = evidence
        assert workspace.personal_h20_saved_recheck_button.isEnabled()
        workspace.personal_h20_saved_recheck_button.click()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_worker", None) is None
            and getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and not workspace.personal_h20_saved_busy,
        )
        assert workspace.personal_h20_saved_evidence == first_evidence
        assert mode.get("_cohort_operation_count") == 2
        assert mode.get("_warm_projection_count") == 2
        assert mode.get("_product_operation_count", 0) == 0

        origin = getattr(window, "_personal_h20_research_origin", None)
        assert isinstance(origin, tuple) and len(origin) == 3
        selection = origin[1]
        report_view.return_button.click()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_return_worker", None) is None
            and getattr(window, "_personal_h20_cohort_worker", None) is None
            and widget._cohort is not None
            and bool(widget.table.selectedItems())
            and widget.isEnabled()
            and widget.research_button.isEnabled(),
        )
        selected_row = widget.table.currentRow()
        assert widget.table.item(selected_row, 0).text() == "2382"
        assert widget.table.item(selected_row, 0).data(Qt.ItemDataRole.UserRole) == selection
        assert widget.research_button.isEnabled()

        # 明確重新核驗會重讀完整 cohort；在第二次 cohort operation 的 finish
        # source verifier 前改變 synthetic snapshot bytes，整體 view 必須拒絕發布。
        mode["drift_cohort_operation_number"] = int(mode.get("_cohort_operation_count", 0)) + 1
        mode["drift_cohort_finish_source"] = True
        window.left_navigation.button_for_key("stock_research").click()
        app.processEvents()
        assert workspace.personal_h20_saved_recheck_button.isEnabled()
        workspace.personal_h20_saved_recheck_button.click()
        _wait_for(
            app,
            lambda: mode.get("source_mutated", False)
            and getattr(window, "_personal_h20_worker", None) is None
            and getattr(workspace.personal_h20_saved_evidence, "status", None) == "unavailable"
            and not workspace.personal_h20_saved_busy,
        )
        unavailable = workspace.personal_h20_saved_evidence
        assert unavailable is not None and unavailable.reason
        assert "+12.34%" not in workspace.personal_h20_saved_summary.text()
        assert network_attempts == []
    finally:
        # 只回復這個 synthetic fixture；讀取操作全程未寫正式來源。
        if mutated_source_path.exists():
            mutated_source_path.write_bytes(original_source_bytes)
        _close_mainwindow(app, window)


def test_h20_current_market_opens_separate_dialog_and_returns_to_exact_saved_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode: dict[str, Any] = {}
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path, monkeypatch, source_mode=mode
    )
    source_database = Path(saved["snapshot_database"])
    source_bytes = source_database.read_bytes()
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        _double_click_selected_h20_row(app, window, widget)
        workspace = window.stock_research_workspace
        assert workspace is not None
        report_view = workspace.report_view
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )

        original_context = report_view.context
        original_report = report_view._loaded_report
        original_evidence = workspace.personal_h20_saved_evidence
        original_view = window._personal_h20_cohort_view
        original_origin = window._personal_h20_research_origin
        assert original_context is not None and original_report is not None
        assert original_evidence is not None and original_evidence.gross_return_bp == 1234
        assert original_report.price_points == ()
        assert mode.get("_cohort_operation_count") == 1

        action = report_view.open_latest_rank_research_button
        assert action.text() == "查看目前個股行情與資料（獨立研究）"
        assert action.isEnabled()
        action.click()
        _wait_for(
            app,
            lambda: bool(window._personal_h20_current_research_dialogs)
            and next(iter(window._personal_h20_current_research_dialogs.values())).report_view._loaded_report
            is not None,
        )

        dialog = next(iter(window._personal_h20_current_research_dialogs.values()))
        current_view = dialog.report_view
        current_context = current_view.context
        current_report = current_view._loaded_report
        assert not dialog.isModal()
        assert dialog.windowTitle().startswith("目前個股行情與資料（獨立研究）｜2382")
        notice = dialog.findChild(QLabel, "stockResearchIndependentCurrentNotice")
        assert notice is not None and "原保存 H20" in notice.text()
        assert current_context is not None and current_report is not None
        assert current_context.stock_code == "2382"
        assert current_context.source_kind == "explicit_latest_stock_research"
        assert current_context.ml_scope_mode == "current_stock_research"
        assert current_context.source_workspace == "stock_research"
        for field_name in (
            "decision_date", "data_date", "result_id", "identity_status",
            "source_snapshot_id", "source_snapshot_hash", "profile_id", "profile_version",
            "source_id", "source_version", "mapping_source_id", "mapping_version",
            "mapping_observed_date",
        ):
            assert getattr(current_context, field_name) == ""
        assert current_report.price_points
        assert max(point.data_date for point in current_report.price_points) == "2026-10-05"
        assert current_report.as_of != original_evidence.decision_date
        assert current_view._personal_h20_evidence is None
        assert "12.34%" not in current_view.personal_h20_label.text()

        assert workspace.report_view is report_view
        assert report_view.context == original_context
        assert report_view._loaded_request_context == original_context
        assert report_view._loaded_report is original_report
        assert workspace.personal_h20_saved_evidence == original_evidence
        assert report_view._personal_h20_evidence == original_evidence
        assert window._personal_h20_cohort_view is original_view
        assert window._personal_h20_research_origin == original_origin
        assert mode.get("_cohort_operation_count") == 1
        assert mode.get("_warm_projection_count") == 2
        assert mode.get("_product_operation_count", 0) == 0
        assert network_attempts == []

        current_view.return_button.click()
        _wait_for(app, lambda: not window._personal_h20_current_research_dialogs)
        assert report_view.context == original_context
        assert report_view._loaded_report is original_report
        assert workspace.personal_h20_saved_evidence == original_evidence
        assert window._personal_h20_cohort_view is original_view
        assert window._personal_h20_research_origin == original_origin
        assert mode.get("_cohort_operation_count") == 1
        assert source_database.read_bytes() == source_bytes
    finally:
        _close_mainwindow(app, window)


def test_h20_current_market_dialog_refuses_stale_market_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path, monkeypatch
    )
    source_database = Path(saved["snapshot_database"])
    source_bytes = source_database.read_bytes()
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        _double_click_selected_h20_row(app, window, widget)
        workspace = window.stock_research_workspace
        assert workspace is not None
        report_view = workspace.report_view
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(window, "_personal_h20_worker", None) is None,
        )
        original_report = report_view._loaded_report
        original_evidence = workspace.personal_h20_saved_evidence
        original_configuration = window._personal_h20_configuration
        monkeypatch.setattr(
            window,
            "_personal_h20_configuration",
            lambda: (Path(saved["market_root"]) / "stale-root", original_configuration()[1]),
        )

        action = report_view.open_latest_rank_research_button
        assert action.isEnabled()
        action.click()
        app.processEvents()

        assert window._personal_h20_current_research_dialogs == {}
        assert "來源設定已變更" in window.statusBar().currentMessage()
        assert report_view._loaded_report is original_report
        assert workspace.personal_h20_saved_evidence == original_evidence
        assert report_view._personal_h20_evidence == original_evidence
        assert network_attempts == []
    finally:
        _close_mainwindow(app, window)
    assert source_database.read_bytes() == source_bytes


def test_main_shutdown_cancels_and_waits_for_h20_current_research_dialog_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.stock_research_report_service import StockResearchReportCancelled

    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path, monkeypatch
    )
    source_bytes = Path(saved["snapshot_database"]).read_bytes()
    entered = threading.Event()
    release = threading.Event()
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        _double_click_selected_h20_row(app, window, widget)
        workspace = window.stock_research_workspace
        assert workspace is not None
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(window, "_personal_h20_worker", None) is None,
        )

        service = window.stock_research_report_service
        original_read = service.read_report

        def held_read(
            stock_code: str,
            *,
            as_of_date: Any = None,
            context: Any = None,
            cancel_callback: Any = None,
        ) -> Any:
            entered.set()
            while True:
                if callable(cancel_callback) and cancel_callback():
                    raise StockResearchReportCancelled("synthetic_current_report_cancelled")
                if release.wait(0.01):
                    break
            return original_read(
                stock_code,
                as_of_date=as_of_date,
                context=context,
                cancel_callback=cancel_callback,
            )

        monkeypatch.setattr(service, "read_report", held_read)
        workspace.report_view.open_latest_rank_research_button.click()
        _wait_for(app, entered.is_set)
        dialog = next(iter(window._personal_h20_current_research_dialogs.values()))
        worker = dialog.report_view._active_worker
        assert worker is not None and worker.isRunning()
        worker_finished = threading.Event()
        worker.native_thread_finished.connect(lambda: worker_finished.set())

        window.close()
        _wait_for(app, worker.is_cancel_requested)
        assert window.isVisible()
        assert dialog.report_view._closing
        release.set()
        _wait_for(app, lambda: not window.isVisible(), timeout_seconds=45.0)
        assert worker_finished.is_set()
        assert network_attempts == []
    finally:
        release.set()
        _close_mainwindow(app, window)
    assert Path(saved["snapshot_database"]).read_bytes() == source_bytes


def test_actual_mainwindow_h20_loading_is_visible_singleflight_and_reports_exact_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    mode: dict[str, Any] = {"block_cohort_operation_before": 1}
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
        source_mode=mode,
        source_entered=entered,
        source_release=release,
    )
    source_bytes = Path(saved["snapshot_database"]).read_bytes()
    try:
        window.show()
        app.processEvents()
        window.left_navigation.button_for_key("recommendation").click()
        app.processEvents()

        recommendation = window.recommendation_view
        tabs = recommendation.result_source_tabs
        panel = window.personal_h20_research_panel
        widget = window.personal_h20_research_widget
        scroll = recommendation.result_scroll
        widget.setMinimumHeight(max(widget.minimumHeight(), scroll.viewport().height() * 2))
        tabs.setCurrentIndex(0)
        app.processEvents()
        assert scroll.verticalScrollBar().maximum() > 0
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        assert scroll.verticalScrollBar().value() == scroll.verticalScrollBar().maximum()
        tab_index = tabs.indexOf(panel)
        assert tab_index >= 0
        QTest.mouseClick(
            tabs.tabBar(),
            Qt.MouseButton.LeftButton,
            pos=tabs.tabBar().tabRect(tab_index).center(),
        )

        _wait_for(app, entered.is_set)
        worker = getattr(window, "_personal_h20_cohort_worker", None)
        assert worker is not None and worker.isRunning()
        assert getattr(window, "_personal_h20_read_phase", "") != "準備原保存名單"
        assert widget._cohort is None and not widget.isEnabled()
        assert not window._personal_h20_refresh_button.isEnabled()
        assert window._personal_h20_cancel_read_button.isEnabled()

        loading_label = window._personal_h20_loading_label
        assert loading_label.isVisibleTo(window)
        label_top_left = loading_label.mapTo(scroll.viewport(), QPoint(0, 0))
        assert scroll.viewport().rect().intersects(
            loading_label.rect().translated(label_top_left)
        )
        assert "目前階段：" in loading_label.text()
        assert "尚未完成" in loading_label.text()

        # 真實重新切回 H20 會再次觸發 tab handler；它必須沿用唯一進行中的讀取。
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        assert scroll.verticalScrollBar().maximum() > 0
        tabs.setCurrentIndex(0)
        app.processEvents()
        tabs.setCurrentWidget(panel)
        app.processEvents()
        assert getattr(window, "_personal_h20_cohort_worker", None) is worker
        assert mode.get("_cohort_operation_count") == 1
        assert scroll.viewport().rect().intersects(
            loading_label.rect().translated(loading_label.mapTo(scroll.viewport(), QPoint(0, 0)))
        )
        assert not window._personal_h20_refresh_button.isEnabled()

        # 取消只送出合作式請求；在 native thread 終結前不可開始第二次讀取。
        window._personal_h20_cancel_read_button.click()
        assert worker.is_cancel_requested()
        assert not widget.isEnabled()
        assert not window._personal_h20_refresh_button.isEnabled()
        assert "已送出取消" in loading_label.text()
        assert worker.isRunning()
        release.set()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_cohort_worker", None) is None,
            timeout_seconds=45.0,
        )
        assert widget._cohort is None
        assert "名單讀取已取消" in loading_label.text()
        assert widget.isEnabled() and window._personal_h20_refresh_button.isEnabled()
        assert mode.get("_cohort_operation_count") == 1

        # 取消收尾後重新啟動一次完整公開讀取，驗證總數與狀態分列後才可下鑽。
        entered.clear()
        release.set()
        window._personal_h20_refresh_button.click()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_cohort_worker", None) is None
            and widget._cohort is not None,
        )
        assert mode.get("_cohort_operation_count") == 2
        assert "1 列；可研究 1 列、未知 0 列" in loading_label.text()
        assert "可研究 1 列｜未知 0 列" in widget.summary_label.text()
        assert widget.research_button.isEnabled() is False
        assert widget.table.rowCount() == 1

        signals = _double_click_selected_h20_row(app, window, widget)
        assert signals["research_requested"]
        workspace = window.stock_research_workspace
        assert workspace is not None
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )
        assert mode.get("_cohort_operation_count") == 2
        assert mode.get("_warm_projection_count") == 1
        assert mode.get("_product_operation_count", 0) == 0
        assert network_attempts == []
    finally:
        release.set()
        _close_mainwindow(app, window)
    assert Path(saved["snapshot_database"]).read_bytes() == source_bytes


def test_actual_mainwindow_close_cancels_saved_h20_drilldown_without_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode: dict[str, Any] = {"block_first_warm_projection": True}
    entered = threading.Event()
    release = threading.Event()
    app, window, _saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
        source_mode=mode,
        source_entered=entered,
        source_release=release,
    )
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        double_click_signals = _double_click_selected_h20_row(app, window, widget)
        assert double_click_signals["research_requested"]
        _wait_for(
            app,
            entered.is_set,
            timeout_seconds=90.0,
        )
        worker = getattr(window, "_personal_h20_worker", None)
        assert worker is not None and worker.isRunning()

        # 真 MainWindow 關閉會合作取消工作；先保持來源 verifier barrier，確認
        # worker 收到取消後才釋放，避免把「剛好已完成」誤算成取消。
        window.close()
        _wait_for(app, lambda: worker.is_cancel_requested(), timeout_seconds=10.0)
        release.set()
        _wait_for(app, lambda: not window.isVisible(), timeout_seconds=45.0)
        assert getattr(window, "_personal_h20_saved_evidence", None) is None
        assert network_attempts == []
    finally:
        release.set()
        _close_mainwindow(app, window)
