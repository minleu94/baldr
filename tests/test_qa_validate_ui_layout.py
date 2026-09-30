"""Focused safety checks for the isolated real-MainWindow layout runner."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "qa_validate_ui_layout.py"
_SPEC = importlib.util.spec_from_file_location("qa_validate_ui_layout", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
qa_layout = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = qa_layout
_SPEC.loader.exec_module(qa_layout)


@pytest.fixture
def qt_app() -> Iterator[object]:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_child_environment_pins_all_storage_and_formal_runtime_paths(
    tmp_path: Path,
) -> None:
    external_root = tmp_path / "external"
    formal_binding = tmp_path / "external-formal-binding.json"
    base = {
        "DATA_ROOT": str(external_root / "data"),
        "OUTPUT_ROOT": str(external_root / "output"),
        "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE": str(formal_binding),
        "PIT_SNAPSHOT_ROOT": str(external_root / "pit"),
        "QT_QPA_PLATFORM": "windows",
    }

    env = qa_layout._isolated_child_environment(
        base,
        "1.5",
        tmp_path / "runner" / "scale_1_5",
    )

    isolated = tmp_path / "runner" / "scale_1_5" / "_isolated_app"
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    assert env["QT_SCALE_FACTOR"] == "1.5"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PROFILE"] == "test"
    assert Path(env["DATA_ROOT"]).is_relative_to(isolated)
    assert Path(env["OUTPUT_ROOT"]).is_relative_to(isolated)
    assert "PIT_SNAPSHOT_ROOT" not in env
    pinned_binding = Path(env["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"])
    assert pinned_binding.is_relative_to(isolated)
    assert pinned_binding.name == "formal_runtime_binding_does_not_exist.json"
    assert not pinned_binding.exists()


def test_faulthandler_log_is_disabled_before_close_without_watchdog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class TrackedLog:
        closed = False

        def close(self) -> None:
            events.append("close")
            self.closed = True

    log = TrackedLog()

    def open_log(path: Path, mode: str = "r", **_kwargs: object) -> TrackedLog:
        assert path == tmp_path / "faulthandler.log"
        assert mode == "a"
        events.append("open")
        return log

    def enable_handler(*, file: TrackedLog, all_threads: bool) -> None:
        assert file is log
        assert all_threads is True
        assert log.closed is False
        events.append("enable")

    def disable_handler() -> None:
        assert log.closed is False
        events.append("disable")

    def unexpected_watchdog(*_args: object, **_kwargs: object) -> None:
        pytest.fail("runner must not schedule an in-process traceback watchdog")

    monkeypatch.setattr(Path, "open", open_log)
    monkeypatch.setattr(qa_layout.faulthandler, "enable", enable_handler)
    monkeypatch.setattr(qa_layout.faulthandler, "disable", disable_handler)
    monkeypatch.setattr(
        qa_layout.faulthandler, "dump_traceback_later", unexpected_watchdog
    )
    monkeypatch.setattr(
        qa_layout.faulthandler, "cancel_dump_traceback_later", unexpected_watchdog
    )

    stack_log = qa_layout._enable_faulthandler_log(tmp_path / "faulthandler.log")
    qa_layout._disable_and_close_faulthandler_log(stack_log)

    assert events == ["open", "enable", "disable", "close"]
    assert log.closed is True


def test_parent_process_timeout_remains_a_failed_evidence_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int | None] = []

    def timeout_child(command: list[str], **kwargs: object) -> object:
        timeout = kwargs.get("timeout")
        calls.append(timeout if isinstance(timeout, int) else None)
        raise qa_layout.subprocess.TimeoutExpired(
            command,
            timeout,
            output=b"partial child output",
            stderr=b"partial child error",
        )

    monkeypatch.setattr(qa_layout.subprocess, "run", timeout_child)
    output_dir = tmp_path / "parent-timeout"

    result_code = qa_layout.main(
        [
            "--scale",
            "1",
            "--geometry",
            "default",
            "--workspace",
            "workbench",
            "--output-dir",
            str(output_dir),
        ]
    )

    evidence = json.loads(
        (output_dir / "scale_1" / "evidence.json").read_text(encoding="utf-8")
    )
    assert result_code == 1
    assert calls == [900]
    assert evidence["status"] == "failed"
    assert any(error["code"] == "runner_timeout" for error in evidence["errors"])


def test_each_geometry_child_command_contains_only_one_window_size(
    tmp_path: Path,
) -> None:
    command = qa_layout._geometry_child_command(
        script_path=tmp_path / "runner.py",
        output_dir=tmp_path / "scale_1" / "geometry_processes" / "default",
        geometry="default",
        workspaces=("workbench", "update"),
    )

    assert command.count("--geometry") == 1
    assert command[command.index("--geometry") + 1] == "default"
    assert command.count("--workspace") == 2
    assert command[command.index("--output-dir") + 1].endswith(
        "geometry_processes\\default"
    )


def test_geometry_child_merge_preserves_each_run_and_failure_evidence(
    tmp_path: Path,
) -> None:
    def child(
        geometry: str,
        *,
        status: str,
        errors: list[dict[str, str]],
        gaps: list[dict[str, str]],
    ) -> dict[str, object]:
        return {
            "geometry": geometry,
            "evidence": {
                "status": status,
                "evidence_kind": "offscreen_real_mainwindow_geometry",
                "scale_factor_requested": 1.5,
                "scale_factor_observed": 1.5,
                "isolated_paths": {"data_root": f"isolated/{geometry}/data"},
                "isolated_file_inventory": [{"path": f"{geometry}/fixture.json"}],
                "startup_service_read_dispatches_suppressed": [
                    {"geometry": geometry, "dispatches": []}
                ],
                "geometry_runs": [{"key": geometry, "workspaces": ["nine-view"]}],
                "errors": errors,
                "coverage_gaps": gaps,
                "screenshots": [f"{geometry}/entry.png"],
            },
            "process": {
                "geometry": geometry,
                "returncode": 0,
                "output_dir": str(tmp_path / geometry),
            },
        }

    failure = {"severity": "fail", "code": "item_clip", "message": "第5列裁切"}
    gap = {"severity": "coverage_gap", "code": "unseeded", "message": "未注入"}
    merged = qa_layout._combine_geometry_child_results(
        "1.5",
        [
            child("default", status="passed", errors=[], gaps=[]),
            child("actual_max", status="failed", errors=[failure], gaps=[gap]),
        ],
    )

    assert merged["status"] == "failed"
    assert [item["key"] for item in merged["geometry_runs"]] == [
        "default",
        "actual_max",
    ]
    assert merged["errors"] == [failure]
    assert merged["coverage_gaps"] == [gap]
    assert merged["screenshots"] == ["default/entry.png", "actual_max/entry.png"]
    assert set(merged["isolated_paths_by_geometry"]) == {"default", "actual_max"}
    assert [item["geometry"] for item in merged["child_processes"]] == [
        "default",
        "actual_max",
    ]


@pytest.mark.parametrize(
    ("geometry_runs", "expected_keys"),
    [
        ([], []),
        ([{"key": "compact"}], ["compact"]),
        ([{"key": "default"}, {"key": "default"}], ["default", "default"]),
    ],
)
def test_geometry_child_receipt_requires_exactly_the_requested_geometry(
    tmp_path: Path,
    geometry_runs: list[dict[str, str]],
    expected_keys: list[str],
) -> None:
    child_dir = tmp_path / "child"
    child_dir.mkdir()
    (child_dir / "evidence.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "geometry_runs": geometry_runs,
                "errors": [],
                "coverage_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    result = qa_layout._read_geometry_child_evidence(
        scale="1",
        geometry="default",
        child_dir=child_dir,
        returncode=0,
    )

    assert result["status"] == "failed"
    assert any(
        error["code"] == "geometry_child_receipt_mismatch"
        and repr(expected_keys) in error["message"]
        for error in result["errors"]
    )


def test_failed_geometry_child_status_without_errors_is_explicit_failure(
    tmp_path: Path,
) -> None:
    child_dir = tmp_path / "child"
    child_dir.mkdir()
    (child_dir / "evidence.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "geometry_runs": [{"key": "default"}],
                "errors": [],
                "coverage_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    result = qa_layout._read_geometry_child_evidence(
        scale="1",
        geometry="default",
        child_dir=child_dir,
        returncode=0,
    )

    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "geometry_child_status_failed"


def test_failed_child_status_with_empty_error_list_cannot_be_merged_as_passed(
    tmp_path: Path,
) -> None:
    failed_child = {
        "geometry": "default",
        "evidence": {
            "status": "failed",
            "scale_factor_requested": 1,
            "geometry_runs": [{"key": "default"}],
            "errors": [],
            "coverage_gaps": [],
        },
        "process": {"geometry": "default", "returncode": 0},
    }

    merged = qa_layout._combine_geometry_child_results("1", [failed_child])

    assert merged["status"] == "failed"
    assert merged["errors"] == []

    qa_layout._write_summary(
        tmp_path,
        [merged],
        complete=True,
    )
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "failed"


def test_synthetic_fixture_blocks_selection_callbacks_and_restores_original_model(
    qt_app: object,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import QTableView

    view = QTableView()
    original = QStandardItemModel(2, 1, view)
    original.setItem(0, 0, QStandardItem("original row 1"))
    original.setItem(1, 0, QStandardItem("original row 2"))
    view.setModel(original)
    view.resize(360, 180)
    view.show()
    qt_app.processEvents()
    selection_events: list[int] = []
    model_layout_events: list[bool] = []
    try:
        with qa_layout._synthetic_view_data(view, rows=60) as fixture_info:
            fixture = view.model()
            assert fixture is not original
            assert fixture.rowCount() == 60
            selection = view.selectionModel()
            selection.currentChanged.connect(
                lambda current, _previous: selection_events.append(current.row())
            )
            fixture.layoutChanged.connect(lambda: model_layout_events.append(True))
            fixture.layoutChanged.emit()
            view.setCurrentIndex(fixture.index(0, 0))
            assert model_layout_events == [True]
            assert selection_events == []

        assert view.model() is original
        assert original.rowCount() == 2
        assert fixture_info["restoration"]["passed"] is True
        assert fixture_info["restoration"]["checks"]["model_identity"] is True
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_table_widget_fixture_restores_cells_headers_sorting_and_callbacks(
    qt_app: object,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    view = QTableWidget(12, 2)
    for column, (label, tooltip) in enumerate(
        (("名稱", "完整名稱提示"), ("數值", "完整數值提示"))
    ):
        header_item = QTableWidgetItem(label)
        header_item.setToolTip(tooltip)
        view.setHorizontalHeaderItem(column, header_item)
    for row in range(view.rowCount()):
        for column in range(view.columnCount()):
            item = QTableWidgetItem(f"原始-{row:02d}-{column}")
            item.setToolTip(f"原始提示-{row:02d}-{column}")
            view.setItem(row, column, item)
    view.setSortingEnabled(False)
    view.sortItems(0, Qt.SortOrder.DescendingOrder)
    view.setSortingEnabled(True)
    view.horizontalHeader().setSortIndicator(0, Qt.SortOrder.DescendingOrder)
    view.setCurrentCell(3, 1)
    view.resize(360, 90)
    view.show()
    qt_app.processEvents()
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

    original_model = view.model()
    original_cells = [
        [view.item(row, column) for column in range(view.columnCount())]
        for row in range(view.rowCount())
    ]
    original_headers = [
        (view.horizontalHeaderItem(column).text(), view.horizontalHeaderItem(column).toolTip())
        for column in range(view.columnCount())
    ]
    original_header_state = bytes(view.horizontalHeader().saveState())
    original_vertical_header_state = bytes(view.verticalHeader().saveState())
    original_sorting = view.isSortingEnabled()
    original_sort_indicator = (
        view.horizontalHeader().sortIndicatorSection(),
        view.horizontalHeader().sortIndicatorOrder(),
    )
    original_current_cell = (view.currentRow(), view.currentColumn())
    original_scroll = (
        view.verticalScrollBar().value(),
        view.horizontalScrollBar().value(),
    )
    original_column_count = view.columnCount()
    selection_callbacks: list[tuple[int, int]] = []
    model_callbacks: list[bool] = []
    view.currentCellChanged.connect(
        lambda row, column, _previous_row, _previous_column: selection_callbacks.append(
            (row, column)
        )
    )
    original_model.rowsInserted.connect(lambda *_args: model_callbacks.append(True))

    try:
        with qa_layout._synthetic_view_data(view, rows=60) as fixture_info:
            assert view.rowCount() == 60
            view.setCurrentCell(0, 0)
            assert model_callbacks
            assert selection_callbacks == []

        assert fixture_info["restoration"]["passed"] is True
        assert view.model() is original_model
        assert view.columnCount() == original_column_count
        assert all(
            view.item(row, column) is original_cells[row][column]
            for row in range(len(original_cells))
            for column in range(len(original_cells[row]))
        )
        assert [
            (view.horizontalHeaderItem(column).text(), view.horizontalHeaderItem(column).toolTip())
            for column in range(view.columnCount())
        ] == original_headers
        assert bytes(view.horizontalHeader().saveState()) == original_header_state
        assert bytes(view.verticalHeader().saveState()) == original_vertical_header_state
        assert view.isSortingEnabled() is original_sorting
        assert (
            view.horizontalHeader().sortIndicatorSection(),
            view.horizontalHeader().sortIndicatorOrder(),
        ) == original_sort_indicator
        assert (view.currentRow(), view.currentColumn()) == original_current_cell
        assert (
            view.verticalScrollBar().value(),
            view.horizontalScrollBar().value(),
        ) == original_scroll
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_adaptive_table_widths_restore_after_formal_qss_scrollbar_change(
    qt_app: object,
) -> None:
    """The real theme and vertical-scrollbar width change must not falsify restore QA."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem
    from ui_qt.theme.qss import build_global_stylesheet

    original_stylesheet = qt_app.styleSheet()
    try:
        qt_app.setStyleSheet(build_global_stylesheet())
        view = QTableWidget(2, 5)
        view.setHorizontalHeaderLabels(["策略", "互動欄", "固定欄", "伸展欄", "說明"])
        for row in range(view.rowCount()):
            values = (f"策略{row}", "互動", "固定", "stretch", f"說明{row}")
            for column, value in enumerate(values):
                view.setItem(row, column, QTableWidgetItem(value))
        header = view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        view.setColumnWidth(1, 77)
        view.setColumnWidth(2, 83)
        view.resize(540, 150)
        view.show()
        qt_app.processEvents()
        baseline_viewport_width = view.viewport().width()
        assert not view.verticalScrollBar().isVisible()

        try:
            with qa_layout._synthetic_view_data(view, rows=60) as fixture_info:
                qt_app.processEvents()
                assert view.verticalScrollBar().isVisible()
                assert view.viewport().width() < baseline_viewport_width
                fixture_width = view.viewport().width()
                assert view.rowCount() == 60

            restoration = fixture_info["restoration"]
            width_details = fixture_info["column_width_restore"]
            assert restoration["passed"] is True, restoration
            assert restoration["checks"]["horizontal_header_state"] is True
            assert restoration["checks"]["column_widths"] is True
            assert width_details["baseline_viewport_width"] == baseline_viewport_width
            assert width_details["fixture_viewport_width_before_restore"] == fixture_width
            assert width_details["restored_viewport_width"] == baseline_viewport_width
            assert width_details["resize_modes_restored"] is True
            assert width_details["viewport_allocation_passed"] is True
            assert width_details["natural_widths_passed"] is True
            by_column = {entry["column"]: entry for entry in width_details["per_column"]}
            assert by_column[0]["width_rule"] == "original_content_width_and_size_hint"
            assert by_column[1]["width_rule"] == "exact_user_width"
            assert by_column[2]["width_rule"] == "exact_user_width"
            assert by_column[3]["width_rule"] == "viewport_allocation"
            assert by_column[4]["width_rule"] == "original_content_width_and_size_hint"
            assert by_column[1]["restored_width"] == by_column[1]["baseline_width"] == 77
            assert by_column[2]["restored_width"] == by_column[2]["baseline_width"] == 83
            assert width_details["dynamic_restored_total_width"] == width_details[
                "dynamic_expected_total_width"
            ]
        finally:
            view.close()
            view.deleteLater()
            qt_app.processEvents()
    finally:
        qt_app.setStyleSheet(original_stylesheet)


def test_adaptive_header_state_accepts_only_adaptive_width_serialization_delta(
    qt_app: object,
) -> None:
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

    view = QTableWidget(2, 3)
    view.setHorizontalHeaderLabels(["欄一", "欄二", "最末伸展欄"])
    for row in range(view.rowCount()):
        for column in range(view.columnCount()):
            view.setItem(row, column, QTableWidgetItem(f"原始-{row}-{column}"))
    header = view.horizontalHeader()
    header.setStretchLastSection(True)
    for column in range(view.columnCount()):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    view.resize(520, 160)
    view.show()
    qt_app.processEvents()
    original_state = bytes(header.saveState())
    baseline_viewport_width = view.viewport().width()
    baseline_last_width = view.columnWidth(2)

    try:
        with qa_layout._synthetic_view_data(view, rows=60) as fixture_info:
            qt_app.processEvents()
            assert view.verticalScrollBar().isVisible()
            view.resize(view.width() + 10, view.height())
            qt_app.processEvents()
            assert view.viewport().width() < baseline_viewport_width

        header_readback = fixture_info["horizontal_header_state_readback"]
        width_readback = fixture_info["column_width_restore"]
        assert fixture_info["restoration"]["passed"] is True
        assert bytes(header.saveState()) != original_state
        assert header_readback["restore_state_accepted"] is True
        assert header_readback["serialized_equal"] is False
        assert header_readback["semantic_contract"]["passed"] is True
        assert header_readback["changed_width_sections"] == [2]
        assert header_readback["adaptive_width_sections"] == [2]
        assert header_readback["serialization_difference_explained_by_adaptive_width"] is True
        assert width_readback["baseline_viewport_width"] == baseline_viewport_width
        assert width_readback["restored_viewport_width"] == baseline_viewport_width + 10
        assert width_readback["restored_widths"][2] == baseline_last_width + 10
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_stretch_last_section_preserves_its_original_width_floor_when_overfull(
    qt_app: object,
) -> None:
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

    original_widths = [281, 137, 75, 195, 175, 410, 117, 156, 100]
    view = QTableWidget(2, len(original_widths))
    for column, width in enumerate(original_widths):
        view.setHorizontalHeaderItem(column, QTableWidgetItem(f"欄位 {column}"))
        for row in range(view.rowCount()):
            view.setItem(row, column, QTableWidgetItem(f"{row}-{column}"))
        view.horizontalHeader().setSectionResizeMode(
            column, QHeaderView.ResizeMode.Interactive
        )
        view.setColumnWidth(column, width)
    header = view.horizontalHeader()
    header.setStretchLastSection(True)
    view.resize(1585, 300)
    view.show()
    qt_app.processEvents()

    try:
        assert [view.columnWidth(column) for column in range(9)] == original_widths
        viewport_width = header.viewport().width()
        assert sum(original_widths[:-1]) < viewport_width
        assert viewport_width - sum(original_widths[:-1]) < original_widths[-1]
        with qa_layout._synthetic_view_data(view, rows=60) as fixture_info:
            qt_app.processEvents()

        width_readback = fixture_info["column_width_restore"]
        assert fixture_info["restoration"]["passed"] is True
        assert width_readback["restored_widths"] == original_widths
        assert width_readback["dynamic_columns"] == [8]
        assert width_readback["dynamic_section_width_floors"] == {8: 100}
        assert width_readback["dynamic_expected_total_width"] == 100
        assert width_readback["dynamic_restored_total_width"] == 100
        assert width_readback["viewport_allocation_passed"] is True
        header_readback = fixture_info["horizontal_header_state_readback"]
        assert header_readback["serialized_equal"] is True
        assert header_readback["semantic_contract"]["passed"] is True
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_empty_table_stale_auto_sizes_are_settled_without_changing_user_widths(
    qt_app: object,
) -> None:
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

    view = QTableWidget(2, 4)
    view.setHorizontalHeaderLabels(["短標題 A", "固定欄", "互動欄", "末欄"])
    header = view.horizontalHeader()
    modes = (
        QHeaderView.ResizeMode.ResizeToContents,
        QHeaderView.ResizeMode.Fixed,
        QHeaderView.ResizeMode.Interactive,
        QHeaderView.ResizeMode.ResizeToContents,
    )
    for column, mode in enumerate(modes):
        header.setSectionResizeMode(column, mode)
    header.setStretchLastSection(True)
    view.setColumnWidth(1, 137)
    view.setColumnWidth(2, 75)
    for row in range(view.rowCount()):
        for column, length in enumerate((34, 12, 4, 25)):
            view.setItem(
                row,
                column,
                QTableWidgetItem(f"projection-{row}-{column}-" + "x" * length),
            )
    view.resize(800, 260)
    view.show()
    qt_app.processEvents()
    view.resizeColumnsToContents()
    view.setColumnWidth(1, 137)
    view.setColumnWidth(2, 75)
    qt_app.processEvents()
    populated_widths = [view.columnWidth(column) for column in range(4)]
    assert populated_widths[1:3] == [137, 75]

    model = view.model()
    was_blocked = model.blockSignals(True)
    try:
        view.clearContents()
        view.setRowCount(0)
    finally:
        model.blockSignals(was_blocked)
    qt_app.processEvents()
    stale_empty_widths = [view.columnWidth(column) for column in range(4)]
    assert view.rowCount() == 0
    assert stale_empty_widths[0] > view.sizeHintForColumn(0)

    try:
        with qa_layout._synthetic_view_data(view, rows=60) as fixture_info:
            assert view.rowCount() == 60

        settle = fixture_info["baseline_header_settle"]
        width_readback = fixture_info["column_width_restore"]
        assert fixture_info["restoration"]["passed"] is True
        assert settle["before_widths"] == stale_empty_widths
        assert settle["after_widths"][0] < settle["before_widths"][0]
        assert settle["after_widths"][1:3] == [137, 75]
        assert settle["fixed_interactive_widths_preserved"] is True
        assert settle["resize_modes_preserved"] is True
        assert width_readback["baseline_widths"] == settle["after_widths"]
        assert width_readback["restored_widths"][0] == settle["after_widths"][0]
        assert width_readback["restored_widths"][1:3] == [137, 75]
        assert width_readback["dynamic_columns"] == [3]
        assert width_readback["dynamic_restored_total_width"] == width_readback[
            "dynamic_expected_total_width"
        ]
        assert width_readback["fixed_widths_passed"] is True
        assert width_readback["natural_widths_passed"] is True
        assert fixture_info["horizontal_header_state_readback"]["semantic_contract"][
            "passed"
        ] is True
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


@pytest.mark.parametrize(
    ("mutation", "expected_field"),
    [
        ("visual_order", "visual_order"),
        ("resize_mode", "resize_modes"),
        ("hidden_section", "hidden_sections"),
        ("sections_movable", "sections_movable"),
        ("sections_clickable", "sections_clickable"),
        ("highlight_sections", "highlight_sections"),
        ("stretch_last_section", "stretch_last_section"),
        ("minimum_section_size", "minimum_section_size"),
        ("maximum_section_size", "maximum_section_size"),
        ("default_section_size", "default_section_size"),
        ("sort_indicator", "sort_indicator_section"),
        ("sort_indicator_shown", "sort_indicator_shown"),
        ("cascading_resizes", "cascading_section_resizes"),
        ("resize_contents_precision", "resize_contents_precision"),
        ("default_alignment", "default_alignment"),
        ("text_elide_mode", "text_elide_mode"),
        ("focus_policy", "focus_policy"),
        ("context_menu_policy", "context_menu_policy"),
        ("sort_indicator_clearable", "sort_indicator_clearable"),
        ("first_section_movable", "first_section_movable"),
    ],
)
def test_header_state_contract_rejects_changed_semantics(
    qt_app: object,
    mutation: str,
    expected_field: str,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHeaderView, QTableWidget

    view = QTableWidget(1, 3)
    header = view.horizontalHeader()
    original_state = header.saveState()
    original_contract = qa_layout._header_state_contract(header)
    original_widths = [view.columnWidth(column) for column in range(view.columnCount())]
    mutation_actions = {
        "visual_order": lambda: header.moveSection(header.visualIndex(0), 1),
        "resize_mode": lambda: header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed),
        "hidden_section": lambda: header.setSectionHidden(1, True),
        "sections_movable": lambda: header.setSectionsMovable(not header.sectionsMovable()),
        "sections_clickable": lambda: header.setSectionsClickable(not header.sectionsClickable()),
        "highlight_sections": lambda: header.setHighlightSections(not header.highlightSections()),
        "stretch_last_section": lambda: header.setStretchLastSection(not header.stretchLastSection()),
        "minimum_section_size": lambda: header.setMinimumSectionSize(header.minimumSectionSize() + 1),
        "maximum_section_size": lambda: header.setMaximumSectionSize(header.maximumSectionSize() - 1),
        "default_section_size": lambda: header.setDefaultSectionSize(header.defaultSectionSize() + 1),
        "sort_indicator": lambda: header.setSortIndicator(1, Qt.SortOrder.DescendingOrder),
        "sort_indicator_shown": lambda: header.setSortIndicatorShown(not header.isSortIndicatorShown()),
        "cascading_resizes": lambda: header.setCascadingSectionResizes(not header.cascadingSectionResizes()),
        "resize_contents_precision": lambda: header.setResizeContentsPrecision(header.resizeContentsPrecision() + 1),
        "default_alignment": lambda: header.setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
        "text_elide_mode": lambda: header.setTextElideMode(Qt.TextElideMode.ElideMiddle),
        "focus_policy": lambda: header.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
            if header.focusPolicy() != Qt.FocusPolicy.NoFocus
            else Qt.FocusPolicy.StrongFocus
        ),
        "context_menu_policy": lambda: header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu),
        "sort_indicator_clearable": lambda: header.setSortIndicatorClearable(not header.isSortIndicatorClearable()),
        "first_section_movable": lambda: header.setFirstSectionMovable(not header.isFirstSectionMovable()),
    }
    mutation_actions[mutation]()
    current_contract = qa_layout._header_state_contract(header)
    comparison = qa_layout._compare_header_state_contract(original_contract, current_contract)
    readback = qa_layout._header_state_readback(
        header,
        original_state=original_state,
        original_contract=original_contract,
        restore_state_accepted=True,
        column_width_readback={
            "baseline_widths": original_widths,
            "restored_widths": [view.columnWidth(column) for column in range(view.columnCount())],
            "dynamic_columns": [],
            "passed": True,
        },
    )
    assert comparison["passed"] is False
    assert expected_field in comparison["failed_fields"]
    assert readback["passed"] is False


def test_stretch_last_section_uses_visual_not_logical_order(qt_app: object) -> None:
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

    view = QTableWidget(2, 3)
    view.setHorizontalHeaderLabels(["互動 A", "固定 B", "互動 C"])
    for row in range(view.rowCount()):
        for column in range(view.columnCount()):
            view.setItem(row, column, QTableWidgetItem(f"{row}-{column}"))
    header = view.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
    view.setColumnWidth(0, 77)
    view.setColumnWidth(1, 91)
    view.setColumnWidth(2, 83)
    header.setStretchLastSection(True)
    header.moveSection(header.visualIndex(2), 0)
    view.resize(420, 150)
    view.show()
    qt_app.processEvents()
    assert [header.logicalIndex(i) for i in range(3)] == [2, 0, 1]

    try:
        with qa_layout._synthetic_view_data(view, rows=60) as fixture_info:
            qt_app.processEvents()
            assert view.verticalScrollBar().isVisible()

        restoration = fixture_info["restoration"]
        width_details = fixture_info["column_width_restore"]
        assert restoration["passed"] is True, restoration
        assert width_details["last_visible_column_logical_index"] == 1
        assert width_details["last_visible_column_visual_index"] == 2
        assert width_details["dynamic_columns"] == [1]
        by_column = {entry["column"]: entry for entry in width_details["per_column"]}
        assert by_column[0]["width_rule"] == "exact_user_width"
        assert by_column[1]["width_rule"] == "viewport_allocation"
        assert by_column[1]["stretch_last_section_override"] is True
        assert by_column[2]["width_rule"] == "exact_user_width"
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_scenario_focus_capture_scrolls_target_and_saves_window_image(
    qt_app: object,
    tmp_path: Path,
) -> None:
    from PySide6.QtWidgets import QGroupBox, QLabel, QMainWindow, QScrollArea, QVBoxLayout, QWidget

    window = QMainWindow()
    workspace = QWidget()
    workspace_layout = QVBoxLayout(workspace)
    area = QScrollArea(workspace)
    area.setWidgetResizable(True)
    workspace.result_scroll = area
    workspace_layout.addWidget(area)
    content = QWidget()
    content_layout = QVBoxLayout(content)
    for index in range(12):
        label = QLabel(f"長內容 {index}")
        label.setMinimumHeight(24)
        content_layout.addWidget(label)
    target = QGroupBox("個人模型評估", content)
    target.setObjectName("personalModelAssessmentControls")
    target_layout = QVBoxLayout(target)
    for index in range(3):
        target_layout.addWidget(QLabel(f"評估欄位 {index}"))
    content_layout.addWidget(target)
    area.setWidget(content)
    window.setCentralWidget(workspace)
    window.resize(360, 220)
    window.show()
    qt_app.processEvents()
    evidence: dict[str, object] = {"screenshots": []}
    geometry_evidence: dict[str, object] = {}
    scenario: dict[str, object] = {}
    geometry_dir = tmp_path / "screenshots" / "scale_1_5" / "default"

    try:
        qa_layout._capture_scenario_focus_screenshot(
            spec={
                "key": "advanced_personal_calibration",
                "focus_scroll_area_attribute": "result_scroll",
                "focus_target_object_name": "personalModelAssessmentControls",
                "focus_screenshot_slug": "recommendation_personal_model_assessment",
            },
            workspace=workspace,
            window=window,
            app=qt_app,
            geometry_key="default",
            geometry_dir=geometry_dir,
            evidence=evidence,
            geometry_evidence=geometry_evidence,
            workspace_key="recommendation",
            scenario=scenario,
        )

        capture = scenario["focus_screenshot"]
        assert area.verticalScrollBar().value() > 0
        assert capture["path"] == str(
            geometry_dir / "recommendation_personal_model_assessment.png"
        )
        assert Path(capture["path"]).is_file()
        assert capture["visible_intersection"]["height"] > 0
        assert evidence["screenshots"] == [capture["path"]]
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_list_widget_fixture_restores_items_and_skips_custom_item_widgets(
    qt_app: object,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem

    view = QListWidget()
    for row in range(12):
        item = QListWidgetItem(f"原始清單-{row:02d}")
        item.setToolTip(f"原始清單完整提示-{row:02d}")
        view.addItem(item)
    view.setSortingEnabled(True)
    view.sortItems(Qt.SortOrder.DescendingOrder)
    view.setCurrentRow(3)
    view.resize(280, 80)
    view.show()
    qt_app.processEvents()
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

    original_model = view.model()
    original_items = [view.item(row) for row in range(view.count())]
    original_content = [(item.text(), item.toolTip()) for item in original_items]
    original_current_row = view.currentRow()
    original_sorting = view.isSortingEnabled()
    original_scroll = (
        view.verticalScrollBar().value(),
        view.horizontalScrollBar().value(),
    )
    service_selection_callbacks: list[int] = []
    model_callbacks: list[bool] = []
    view.currentRowChanged.connect(service_selection_callbacks.append)
    original_model.rowsInserted.connect(lambda *_args: model_callbacks.append(True))

    try:
        with qa_layout._synthetic_view_data(view, rows=60) as fixture_info:
            assert view.count() == 60
            view.setCurrentRow(0)
            view.addItem(QListWidgetItem("模型回呼測試列"))
            assert model_callbacks
            assert service_selection_callbacks == []

        assert fixture_info["restoration"]["passed"] is True
        assert view.model() is original_model
        assert view.count() == len(original_items)
        assert all(view.item(row) is original_items[row] for row in range(len(original_items)))
        assert [(view.item(row).text(), view.item(row).toolTip()) for row in range(view.count())] == original_content
        assert view.currentRow() == original_current_row
        assert view.isSortingEnabled() is original_sorting
        assert (
            view.verticalScrollBar().value(),
            view.horizontalScrollBar().value(),
        ) == original_scroll
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()

    custom_view = QListWidget()
    custom_item = QListWidgetItem("帶有自訂 QWidget 的列")
    custom_view.addItem(custom_item)
    custom_widget = QLabel("清單 item widget")
    custom_view.setItemWidget(custom_item, custom_widget)
    try:
        with pytest.raises(qa_layout._FixtureCoverageGap, match="itemWidget"):
            with qa_layout._synthetic_view_data(custom_view, rows=8):
                pytest.fail("含 itemWidget 的清單不得進入破壞性 fixture")
        assert custom_view.count() == 1
        assert custom_view.item(0) is custom_item
        assert custom_view.itemWidget(custom_item) is custom_widget
    finally:
        custom_view.close()
        custom_view.deleteLater()
        qt_app.processEvents()


def test_fixture_restoration_failure_is_written_to_runner_errors() -> None:
    evidence: dict[str, object] = {"errors": []}
    geometry_evidence: dict[str, object] = {"errors": []}
    fixture_info: dict[str, object] = {
        "restoration": {
            "passed": False,
            "checks": {"model_identity": False},
            "failed_checks": ["model_identity"],
            "restore_exception": None,
        }
    }

    qa_layout._record_fixture_restoration_failure(
        fixture_info,
        evidence,
        geometry_evidence,
        workspace="qa",
        page="qa/fixture",
        widget="QTableView",
    )

    errors = evidence["errors"]
    assert isinstance(errors, list)
    assert errors[0]["code"] == "synthetic_fixture_restore_failed"
    assert "model_identity" in errors[0]["message"]


def test_horizontal_fixture_stress_restores_section_state(qt_app: object) -> None:
    import pandas as pd

    from PySide6.QtWidgets import QTableView
    from ui_qt.models.pandas_table_model import PandasTableModel

    view = QTableView()
    view.setModel(
        PandasTableModel(
            pd.DataFrame(
                [[f"row {row}", f"欄 {column}"] for row in range(12) for column in [1]],
                columns=["名稱", "欄位"],
            )
        )
    )
    view.resize(320, 180)
    view.show()
    qt_app.processEvents()
    header = view.horizontalHeader()
    original_widths = [view.columnWidth(column) for column in range(2)]
    original_modes = [header.sectionResizeMode(column) for column in range(2)]
    errors: list[dict[str, object]] = []
    evidence = {"errors": errors}
    geometry = {"errors": []}

    try:
        result = qa_layout._stress_horizontal_scroll(
            view,
            view.model(),
            "qa",
            "qa/table",
            evidence,
            geometry,
        )

        assert result["applicable"] is True
        assert result["section_widths_restored"] is True
        assert result["section_resize_modes_restored"] is True
        assert [view.columnWidth(column) for column in range(2)] == original_widths
        assert [header.sectionResizeMode(column) for column in range(2)] == original_modes
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_stock_research_fixture_has_rows_for_each_report_family() -> None:
    report = qa_layout._synthetic_stock_research_report()

    assert report.read_only is True
    assert len(report.sources) >= 5
    assert len(report.price_points) >= 8
    assert len(report.technical.indicators) >= 5
    assert len(report.fundamentals) >= 8
    assert len(report.flows) >= 8
    assert len(report.events) >= 8
    assert report.position is not None
    assert report.position.stock_code == report.stock_code


def test_qt_slot_exception_capture_restores_original_excepthook() -> None:
    original_hook = sys.excepthook

    with qa_layout._capture_qt_slot_exceptions() as captured:
        try:
            raise ValueError("synthetic slot failure")
        except ValueError:
            sys.excepthook(*sys.exc_info())

    assert sys.excepthook is original_hook
    assert len(captured) == 1
    assert captured[0]["message"] == "ValueError: synthetic slot failure"
    assert "synthetic slot failure" in captured[0]["traceback"]


def test_rich_text_label_uses_rendered_width_and_still_flags_real_clipping(
    qt_app: object,
) -> None:
    from PySide6.QtWidgets import QLabel, QWidget

    page_widget = QWidget()
    label = QLabel(
        "<span style='font-size:12px; color:#eef3f8; font-weight:bold;'>三大法人數據</span>",
        page_widget,
    )
    label.setWordWrap(False)
    label.setGeometry(0, 0, label.sizeHint().width(), label.sizeHint().height())
    page_widget.resize(label.width() + 16, label.height() + 16)
    page_widget.show()
    qt_app.processEvents()
    try:
        evidence: dict[str, object] = {"errors": []}
        geometry: dict[str, object] = {"errors": []}
        page: dict[str, object] = {"text_controls": []}
        qa_layout._audit_page_text_controls(
            page_widget,
            "qa/rich_text",
            "qa",
            page,
            evidence,
            geometry,
        )
        fitting_metric = page["text_controls"][0]
        assert fitting_metric["width_measurement_method"] == "QLabel.sizeHint.rich_text"
        assert fitting_metric["estimated_text_width"] == label.sizeHint().width()
        assert evidence["errors"] == []

        label.resize(max(1, label.sizeHint().width() - 8), label.height())
        qt_app.processEvents()
        page["text_controls"] = []
        qa_layout._audit_page_text_controls(
            page_widget,
            "qa/rich_text",
            "qa",
            page,
            evidence,
            geometry,
        )
        assert any(
            error["code"] == "long_label_clipped_without_wrap_or_tooltip"
            for error in evidence["errors"]
        )
    finally:
        page_widget.close()
        page_widget.deleteLater()
        qt_app.processEvents()


def test_list_fixture_tooltip_and_wrapped_fifth_row_are_measured(qt_app: object) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidget
    from ui_qt.widgets.layout_helpers import ensure_visible_rows

    view = QListWidget()
    view.setWordWrap(True)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.resize(360, 180)
    view.show()
    qt_app.processEvents()
    try:
        with qa_layout._synthetic_view_data(view, rows=8):
            qa_layout._wait_layout(view)
            ensure_visible_rows(view, rows=5)
            view.resize(view.width(), view.minimumHeight())
            qa_layout._wait_layout(view)

            tooltip = qa_layout._fixture_tooltip_evidence(view.model(), view=view)
            rows = qa_layout._item_view_rows_metrics(view, view.count())
            helper = qa_layout._visible_rows_helper_metrics(view)

            assert tooltip["available"] is True
            assert tooltip["source"] == "QListWidgetItem"
            assert tooltip["full_cell_text_available"] is True
            assert tooltip["header_applicable"] is False
            assert helper["attached"] is True
            assert rows["first_five_all_fully_visible"] is True
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_markdown_report_lists_page_scroll_fixture_and_control_metrics(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.md"
    page = {
        "path": "recommendation/profile",
        "widget_class": "RecommendationView",
        "visible": True,
        "geometry_logical": {"width": 900, "height": 700},
        "tables_and_lists": [
            {
                "object_name": "resultTable",
                "class": "QTableView",
                "viewport_size_logical": {"width": 800, "height": 240},
                "baseline_model": {"rows": 6, "columns": 4},
                "first_five_rows": {"first_five_fully_visible_count": 5},
                "visible_rows_helper": {"attached": True},
                "fixture_stress": {
                    "rows": 60,
                    "columns": 4,
                    "viewport_size_logical": {"width": 800, "height": 240},
                    "fifth_row_fully_visible": True,
                    "first_five_rows": {"first_five_fully_visible_count": 5},
                    "lower_row_reachable": True,
                    "vertical_scroll_maximum": 2400,
                    "horizontal_scroll": {
                        "applicable": True,
                        "horizontal_scroll_policy": "AsNeeded",
                        "scroll_range_maximum": 400,
                        "last_column_reachable": True,
                    },
                    "tooltip": {"full_cell_text_available": True},
                },
            }
        ],
        "scroll_areas": [
            {
                "object_name": "profileScrollArea",
                "viewport_size_logical": {"width": 900, "height": 600},
                "content_size_logical": {"width": 900, "height": 1200},
                "vertical_scroll_policy": "AsNeeded",
                "vertical_scroll_maximum": 600,
                "vertical_bottom_reached": True,
                "horizontal_scroll_policy": "AsNeeded",
                "horizontal_scroll_maximum": 0,
                "horizontal_right_reached": True,
            }
        ],
        "text_controls": [
            {
                "object_name": "profileNote",
                "class": "QLabel",
                "text_length": 76,
                "text_preview": "完整個人化評估說明",
                "geometry_logical": {"width": 800, "height": 72},
                "tooltip_length": 0,
                "word_wrap": True,
                "height_for_width": 72,
                "width_measurement_method": "QLabel.sizeHint.rich_text",
            }
        ],
        "errors": [],
        "coverage_gaps": [],
        "fixture_screenshot": "fixture.png",
    }
    evidence = {
        "scale_factor_requested": "1",
        "status": "passed",
        "errors": [],
        "coverage_gaps": [],
        "geometry_runs": [
            {
                "key": "default",
                "label": "預設視窗",
                "requested_size_logical": {"width": 1400, "height": 800},
                "observed_main_window_size_logical": {"width": 1400, "height": 800},
                "shell": {
                    "left_navigation": {"width": 184},
                    "navigation_fits_central": True,
                    "workspace_fits_central": True,
                },
                "workspaces": [
                    {
                        "key": "recommendation",
                        "label": "推薦分析",
                        "visible": True,
                        "pages": [page],
                        "scenarios": [
                            {
                                "key": "advanced",
                                "label": "進階個人校準",
                                "description": "合成 UI 情境",
                                "pages": [page],
                                "main_window_size_unchanged": True,
                            }
                        ],
                        "screenshot": "initial.png",
                        "scrollbottom_screenshots": [{"path": "bottom.png"}],
                    }
                ],
            }
        ],
    }

    qa_layout._write_markdown(report, [evidence], complete=True)
    rendered = report.read_text(encoding="utf-8")

    assert "recommendation/profile" in rendered
    assert "baseline 6×4" in rendered
    assert "第5列完整可見=True" in rendered
    assert "最後一列可達=True" in rendered
    assert "最右欄可達=True" in rendered
    assert "vertical policy/range/bottom=AsNeeded/600/True" in rendered
    assert "寬度量測=QLabel.sizeHint.rich_text" in rendered
    assert "bottom.png" in rendered
