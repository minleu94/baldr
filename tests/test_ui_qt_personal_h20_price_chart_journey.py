"""真 MainWindow 的 H20 價格圖表與通用報告分域旅程。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from tests.test_ui_qt_personal_h20_mainwindow_saved_journey import (
    _close_mainwindow,
    _double_click_selected_h20_row,
    _load_h20_list,
    _prepare_saved_h20_mainwindow,
    _wait_for,
)


def test_true_main_h20_price_chart_is_visible_while_generic_report_waits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generic_entered = threading.Event()
    generic_release = threading.Event()
    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
    )
    source_path = Path(saved["snapshot_database"])
    source_before = source_path.read_bytes()
    try:
        window.show()
        app.processEvents()
        widget = _load_h20_list(app, window)
        report_service = window.stock_research_report_service
        original_read = report_service.read_report

        def delayed_generic_report(
            stock_code: str,
            *,
            as_of_date: Any = None,
            context: Any = None,
            cancel_callback: Any = None,
        ) -> Any:
            generic_entered.set()
            while not generic_release.wait(0.01):
                if callable(cancel_callback) and cancel_callback():
                    raise InterruptedError("synthetic_generic_report_cancelled")
            return original_read(
                stock_code,
                as_of_date=as_of_date,
                context=context,
                cancel_callback=cancel_callback,
            )

        monkeypatch.setattr(report_service, "read_report", delayed_generic_report)
        _double_click_selected_h20_row(app, window, widget)
        workspace = window.stock_research_workspace
        assert workspace is not None
        report_view = workspace.report_view
        _wait_for(app, generic_entered.is_set)
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy,
        )

        from app_module.recommendation.personal_h20_price_chart import (
            PersonalH20PriceChartProjectionV1,
        )

        projection = report_view._personal_h20_price_chart_projection
        assert type(projection) is PersonalH20PriceChartProjectionV1
        assert projection.status == "available"
        assert projection.stock_code == "2382"
        assert projection.capture_sha256 == widget._cohort.rows[0].capture_sha256
        assert report_view._loaded_report is None
        assert report_view.personal_h20_price_chart_group.isVisible()
        assert report_view.personal_h20_price_table.model().rowCount() > 0

        generic_release.set()
        _wait_for(app, lambda: report_view._loaded_report is not None)
        assert report_view._personal_h20_price_chart_projection is projection
        assert report_view.personal_h20_price_chart_group.isVisible()
        assert report_view.personal_h20_price_table.model().rowCount() > 0
        assert network_attempts == []
    finally:
        generic_release.set()
        _close_mainwindow(app, window)
    assert source_path.read_bytes() == source_before


def test_true_main_bookmark_recheck_uses_exact_saved_price_chart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_ui_qt_personal_h20_bookmark_reopen_journey import _save_and_find

    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
    )
    source_path = Path(saved["snapshot_database"])
    source_before = source_path.read_bytes()
    try:
        window.show()
        service, controls, bookmark_id = _save_and_find(app, window)
        bookmark = service.get_research_bookmark(bookmark_id)
        assert bookmark.stock_code == "2382"
        controls.open_button.click()
        workspace = window.stock_research_workspace
        assert workspace is not None
        _wait_for(
            app,
            lambda: getattr(workspace.personal_h20_saved_evidence, "status", None) == "available"
            and getattr(workspace.report_view.context, "source_kind", None)
            == "personal_h20_research_bookmark",
        )
        # 收藏列表先精確重開原 H20 evidence；明確重新核驗按鈕再簽發同次來源圖。
        workspace.personal_h20_saved_recheck_button.click()
        _wait_for(
            app,
            lambda: getattr(window, "_personal_h20_worker", None) is None
            and not workspace.personal_h20_saved_busy
            and workspace.report_view._personal_h20_price_chart_projection is not None,
        )

        projection = workspace.report_view._personal_h20_price_chart_projection
        assert projection.status == "available"
        assert projection.origin_kind == "personal_h20_research_bookmark"
        assert projection.origin_identity_sha256 == bookmark.bookmark_identity_sha256
        assert projection.capture_sha256 == bookmark.selected_row.capture_sha256
        assert workspace.report_view.personal_h20_price_chart_group.isVisible()
        assert workspace.report_view.personal_h20_price_table.model().rowCount() > 0
        assert getattr(workspace.personal_h20_saved_evidence, "gross_return_bp", None) == 1234
        assert network_attempts == []
    finally:
        _close_mainwindow(app, window)
    assert source_path.read_bytes() == source_before


@pytest.mark.parametrize("failure_stage", ["constructor", "set_points"])
def test_true_main_h20_chart_native_failure_keeps_exact_table_and_summary(
    failure_stage: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ui_qt.views import stock_research_report_view as report_view_module

    app, window, saved, network_attempts, _task_context = _prepare_saved_h20_mainwindow(
        tmp_path,
        monkeypatch,
    )
    source_path = Path(saved["snapshot_database"])
    source_before = source_path.read_bytes()
    try:
        window.show()
        widget = _load_h20_list(app, window)
        chart_type = report_view_module.StockPriceChartWidget
        if failure_stage == "constructor":
            def fail_constructor(*_args, **_kwargs):
                raise RuntimeError("synthetic H20 chart constructor failure")

            monkeypatch.setattr(report_view_module, "StockPriceChartWidget", fail_constructor)
        else:
            def fail_set_points(_self, _points) -> None:
                raise RuntimeError("synthetic H20 chart set_points failure")

            monkeypatch.setattr(chart_type, "set_points", fail_set_points)

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

        assert workspace.personal_h20_saved_evidence.gross_return_bp == 1234
        assert "+12.34%" in report_view.personal_h20_label.text()
        assert report_view._personal_h20_price_chart_projection.status == "available"
        assert report_view.personal_h20_price_chart_group.isVisible()
        assert report_view.personal_h20_price_chart_widget is None
        assert report_view.personal_h20_price_table.model().rowCount() > 0
        assert "原生圖表無法呈現" in report_view.personal_h20_price_chart_status.text()
        assert f"synthetic H20 chart {failure_stage}" in report_view.personal_h20_price_chart_status.toolTip()
        assert network_attempts == []
    finally:
        _close_mainwindow(app, window)
    assert source_path.read_bytes() == source_before
