"""推薦分析頁版面幾何回歸。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QBoxLayout, QHBoxLayout, QWidget

from app_module.dtos import RegimeResultDTO
from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.main import apply_app_theme
from ui_qt.views.recommendation_view import RecommendationView


class _RecommendationService:
    pass


class _RegimeService:
    def detect_regime(self):
        return RegimeResultDTO(
            regime="Trend",
            confidence=0.5,
            regime_name_cn="趨勢追蹤",
            details={"source": "layout_fixture", "as_of_date": "2026-09-29"},
        )

    def get_strategy_config(self, regime):
        return {"regime": regime}


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    apply_app_theme(instance)
    return instance


def _attach_layout_fixture(view: RecommendationView) -> None:
    rows = [
        {
            "證券代號": f"QA-{index:03d}",
            "股票名稱": f"版面測試 {index}",
            "總分": str(index * 10),
            "推薦理由": "僅供 UI 幾何檢查的合成列",
        }
        for index in range(1, 13)
    ]
    view.recommendations_model = PandasTableModel(pd.DataFrame(rows))
    view.results_table.setModel(view.recommendations_model)
    view.results_table.resizeColumnsToContents()
    view._reserve_recommendation_table_rows()


def _capture_if_requested(view: QWidget, name: str) -> None:
    capture_root = os.environ.get("UI_LAYOUT_CAPTURE_DIR")
    if not capture_root:
        return
    path = Path(capture_root)
    path.mkdir(parents=True, exist_ok=True)
    assert view.grab().save(str(path / name))


def _is_visible_in_result_scroll(view: RecommendationView, widget) -> bool:
    top_left = widget.mapTo(view.result_scroll.viewport(), QPoint(0, 0))
    widget_rect = QRect(top_left, widget.size())
    return view.result_scroll.viewport().rect().intersects(widget_rect)


def _assert_recommendation_table_geometry(view: RecommendationView, app: QApplication) -> None:
    table = view.results_table
    row_height = table.verticalHeader().defaultSectionSize()
    assert table.viewport().height() >= row_height * 5

    fifth_row = table.model().index(4, 0)
    fifth_row_rect = table.visualRect(fifth_row)
    assert fifth_row_rect.isValid()
    assert table.viewport().rect().contains(fifth_row_rect)

    table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())
    app.processEvents()
    twelfth_row = table.visualRect(table.model().index(11, 0))
    assert twelfth_row.isValid()
    assert table.viewport().rect().contains(twelfth_row)
    table.verticalScrollBar().setValue(0)
    app.processEvents()


def _assert_personal_controls_fit(view: RecommendationView) -> None:
    # 收合是預設；展開後仍需驗證既有 capture／Stage C 完整控制幾何。
    view.personal_research_toggle.setChecked(True)
    _app().processEvents()
    view.result_scroll.verticalScrollBar().setValue(view.result_scroll.verticalScrollBar().maximum())
    _app().processEvents()
    assert not view.personal_capture_widget.isHidden()
    assert not view.personal_assessment_group.isHidden()
    buttons = (
        view.personal_model_assessment_capture_button,
        view.personal_model_assessment_summary_button,
        view.personal_model_assessment_read_button,
        view.personal_source_time_check_button,
        view.personal_policy_confirm_button,
        view.personal_candidate_refresh_button,
    )
    for button in buttons:
        assert button.height() >= button.sizeHint().height()

    for line_edit in (
        view.personal_model_assessment_capture_path,
        view.personal_model_assessment_summary_path,
        view.personal_source_database_input,
    ):
        assert line_edit.height() >= line_edit.sizeHint().height()

    wrapped_labels = (
        view.personal_model_assessment_intro_label,
        view.personal_model_assessment_status_label,
        view.personal_model_assessment_safety_label,
        view.personal_policy_status_label,
        view.personal_policy_history_status_label,
        view.personal_source_database_label,
        view.personal_source_time_trust_note,
        view.personal_source_time_status_label,
        view.personal_candidate_status_label,
    )
    for label in wrapped_labels:
        expected_height = label.heightForWidth(label.width())
        if label.wordWrap() and expected_height > 0:
            assert label.height() >= expected_height


def _new_view() -> RecommendationView:
    return RecommendationView(
        recommendation_service=_RecommendationService(),
        regime_service=_RegimeService(),
        config=None,
    )


def test_recommendation_result_scroll_and_five_rows_at_desktop_viewports() -> None:
    app = _app()
    view = _new_view()
    assert QFontMetrics(app.font()).inFont("推")
    initial_row_height = view.results_table.verticalHeader().defaultSectionSize()
    assert view.results_table.minimumHeight() >= view.results_table_minimum_height
    assert view.results_table_minimum_height >= initial_row_height * 5
    expected_dpr = os.environ.get("UI_LAYOUT_EXPECTED_DPR")
    if expected_dpr:
        assert app.primaryScreen().devicePixelRatio() == float(expected_dpr)
    _attach_layout_fixture(view)
    view.show()

    try:
        for width, height, screenshot in (
            (1366, 768, "recommendation_1366x768.png"),
            (1920, 1080, "recommendation_1920x1080.png"),
            (1216, 800, "recommendation_1400x800_minus_184_nav.png"),
            (2293, 912, "recommendation_2293x912_maximized.png"),
        ):
            view.resize(width, height)
            app.processEvents()

            assert view.main_splitter.orientation() == Qt.Orientation.Horizontal
            assert view.result_scroll.verticalScrollBar().maximum() > 0
            row_height = view.results_table.verticalHeader().defaultSectionSize()
            assert view.results_table.viewport().height() >= row_height * 5
            assert view.results_table.minimumHeight() >= view.results_table_minimum_height
            assert view.results_table.horizontalScrollBarPolicy() == (
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            assert view.result_splitter.childrenCollapsible() is False
            assert view.personal_model_assessment_intro_label.wordWrap()
            _assert_recommendation_table_geometry(view, app)
            if width == 1216:
                assert view.personal_policy_history_row.direction() == (
                    QBoxLayout.Direction.TopToBottom
                )
            _capture_if_requested(view, screenshot)

        table_scroll = view.results_table.verticalScrollBar()
        table_scroll.setValue(table_scroll.maximum())
        app.processEvents()
        twelfth_row = view.results_table.visualRect(
            view.results_table.model().index(11, 0)
        )
        assert view.results_table.viewport().rect().contains(twelfth_row)
        _capture_if_requested(view, "recommendation_2293x912_table_bottom.png")
        table_scroll.setValue(0)
        app.processEvents()

        result_scroll = view.result_scroll.verticalScrollBar()
        result_scroll.setValue(result_scroll.maximum())
        app.processEvents()
        _assert_personal_controls_fit(view)
        for widget in (
            view.personal_source_database_input,
            view.personal_source_time_check_button,
            view.personal_source_time_trust_checkbox,
            view.personal_source_time_trust_note,
            view.personal_policy_confirm_button,
            view.personal_candidate_refresh_button,
        ):
            assert _is_visible_in_result_scroll(view, widget)
        _capture_if_requested(view, "recommendation_2293x912_personal_bottom.png")

        view.result_scroll.ensureWidgetVisible(view.personal_model_assessment_read_button)
        app.processEvents()
        assert _is_visible_in_result_scroll(view, view.personal_model_assessment_read_button)

        view.resize(390, 844)
        app.processEvents()
        assert view.main_splitter.orientation() == Qt.Orientation.Vertical
        assert view.assessment_capture_path_row.direction() == QBoxLayout.Direction.TopToBottom
        assert view.personal_policy_history_row.direction() == QBoxLayout.Direction.TopToBottom
        assert view.personal_source_database_label.wordWrap()
        assert view.personal_source_time_trust_note.wordWrap()
        assert view.result_scroll.verticalScrollBar().maximum() > 0
    finally:
        view.close()
        app.processEvents()


def test_recommendation_layout_in_default_shell_with_184_pixel_navigation() -> None:
    app = _app()
    shell = QWidget()
    shell.setObjectName("recommendationLayoutShellFixture")
    shell_layout = QHBoxLayout(shell)
    shell_layout.setContentsMargins(0, 0, 0, 0)
    shell_layout.setSpacing(0)
    navigation = QWidget(shell)
    navigation.setObjectName("navigationWidthFixture")
    navigation.setFixedWidth(184)
    navigation.setStyleSheet("background: #101722;")
    shell_layout.addWidget(navigation)

    view = _new_view()
    _attach_layout_fixture(view)
    shell_layout.addWidget(view, 1)
    shell.show()

    try:
        for shell_width, shell_height, screenshot in (
            (1366, 768, "recommendation_shell_1366x768.png"),
            (1400, 800, "recommendation_shell_1400x800.png"),
        ):
            shell.resize(shell_width, shell_height)
            app.processEvents()
            assert view.width() == shell_width - 184
            assert view.main_splitter.orientation() == Qt.Orientation.Horizontal
            assert view.personal_policy_history_row.direction() == (
                QBoxLayout.Direction.TopToBottom
            )
            assert view.result_scroll.verticalScrollBar().maximum() > 0
            _assert_recommendation_table_geometry(view, app)
            _assert_personal_controls_fit(view)
            _capture_if_requested(shell, screenshot)
    finally:
        shell.close()
        app.processEvents()
