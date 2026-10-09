"""推薦分析頁版面幾何回歸。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout, QHBoxLayout, QWidget

from app_module.dtos import RegimeResultDTO
from data_module.contracts.market import SourceRef
from decision_module.recommendation.contracts import FactorContribution, RecommendationItem
from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.main import apply_app_theme
from ui_qt.views.recommendation.presenter import recommendation_item_to_view_row
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

    # queued responsive resize 可能再改變 viewport；完成幾何更新後才捲到底。
    for _ in range(5):
        app.processEvents()
        table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())
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


def _personal_panel_controls(view: RecommendationView) -> tuple[QWidget, ...]:
    """回傳展開後需要逐一可捲達的個人研究控制項。"""

    return (
        view.personal_research_toggle,
        view.personal_prediction_capture_status_label,
        view.personal_prediction_capture_retry_button,
        view.personal_model_assessment_intro_label,
        view.personal_model_assessment_capture_path,
        view.personal_model_assessment_capture_button,
        view.personal_model_assessment_summary_path,
        view.personal_model_assessment_summary_button,
        view.personal_model_assessment_read_button,
        view.personal_model_assessment_status_label,
        view.personal_model_assessment_details,
        view.personal_model_assessment_safety_label,
        view.personal_policy_mode_combo,
        view.personal_policy_confirm_button,
        view.personal_policy_status_label,
        view.personal_policy_history_label,
        view.personal_policy_history_combo,
        view.personal_policy_history_refresh_button,
        view.personal_policy_rollback_button,
        view.personal_policy_history_status_label,
        view.personal_source_database_label,
        view.personal_source_database_input,
        view.personal_source_database_browse_button,
        view.personal_source_time_check_button,
        view.personal_source_time_trust_checkbox,
        view.personal_source_time_trust_note,
        view.personal_source_time_status_label,
        view.personal_candidate_combo,
        view.personal_candidate_refresh_button,
        view.personal_candidate_status_label,
    )


def _assert_personal_controls_scroll_reachable(
    view: RecommendationView, app: QApplication
) -> None:
    assert view.personal_research_toggle.isChecked()
    assert not view.personal_capture_widget.isHidden()
    assert not view.personal_assessment_group.isHidden()
    assert not view.personal_policy_group.isHidden()
    assert view.result_scroll.verticalScrollBar().maximum() > 0

    for widget in _personal_panel_controls(view):
        if widget.isHidden():
            continue
        view.result_scroll.ensureWidgetVisible(widget)
        app.processEvents()
        for axis_name, scrollbar, start_attr, extent_attr, viewport_extent in (
            (
                "vertical",
                view.result_scroll.verticalScrollBar(),
                "top",
                "height",
                view.result_scroll.viewport().height(),
            ),
            (
                "horizontal",
                view.result_scroll.horizontalScrollBar(),
                "left",
                "width",
                view.result_scroll.viewport().width(),
            ),
        ):
            top_left = widget.mapTo(view.result_scroll.viewport(), QPoint(0, 0))
            widget_rect = QRect(top_left, widget.size())
            start = getattr(widget_rect, start_attr)()
            target_extent = getattr(widget_rect, extent_attr)()
            end = start + target_extent
            if target_extent <= viewport_extent:
                delta = start if start < 0 else end - viewport_extent if end > viewport_extent else 0
                if delta:
                    scrollbar.setValue(scrollbar.value() + delta)
                    app.processEvents()
                top_left = widget.mapTo(view.result_scroll.viewport(), QPoint(0, 0))
                widget_rect = QRect(top_left, widget.size())
                start = getattr(widget_rect, start_attr)()
                end = start + target_extent
                assert start >= 0 and end <= viewport_extent, (
                    widget.objectName() or widget.accessibleName(),
                    axis_name,
                    widget_rect,
                    view.result_scroll.viewport().rect(),
                    scrollbar.value(),
                    scrollbar.maximum(),
                )
                continue

            # 寬於 viewport 的區塊以捲動兩端證明全文可逐段讀取。
            scrollbar.setValue(scrollbar.value() + start)
            app.processEvents()
            top_left = widget.mapTo(view.result_scroll.viewport(), QPoint(0, 0))
            widget_rect = QRect(top_left, widget.size())
            leading = getattr(widget_rect, start_attr)()
            assert 0 <= leading < viewport_extent, (
                widget.objectName() or widget.accessibleName(),
                axis_name,
                "leading",
                widget_rect,
                view.result_scroll.viewport().rect(),
                scrollbar.value(),
                scrollbar.maximum(),
            )

            trailing_end = leading + getattr(widget_rect, extent_attr)()
            scrollbar.setValue(scrollbar.value() + trailing_end - viewport_extent)
            app.processEvents()
            top_left = widget.mapTo(view.result_scroll.viewport(), QPoint(0, 0))
            widget_rect = QRect(top_left, widget.size())
            leading = getattr(widget_rect, start_attr)()
            trailing_end = leading + getattr(widget_rect, extent_attr)()
            assert leading < viewport_extent and trailing_end <= viewport_extent, (
                widget.objectName() or widget.accessibleName(),
                axis_name,
                "trailing",
                widget_rect,
                view.result_scroll.viewport().rect(),
                scrollbar.value(),
                scrollbar.maximum(),
            )
        required_height = (
            widget.heightForWidth(widget.width())
            if widget.hasHeightForWidth()
            else widget.sizeHint().height()
        )
        assert required_height <= 0 or widget.height() >= required_height, (
            widget.objectName() or widget.accessibleName(),
            widget.size(),
            widget.sizeHint(),
            required_height,
        )


def _assert_layout_widgets_do_not_overlap(view: RecommendationView, layout) -> None:
    visible_widgets = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if widget is None or widget.isHidden() or widget.width() <= 0 or widget.height() <= 0:
            continue
        rect = QRect(widget.mapTo(view, QPoint(0, 0)), widget.size())
        visible_widgets.append((widget, rect))
    for index, (previous, previous_rect) in enumerate(visible_widgets):
        for following, following_rect in visible_widgets[index + 1 :]:
            assert not previous_rect.intersects(following_rect), (
                previous.objectName()
                or previous.accessibleName()
                or getattr(previous, "text", lambda: "")(),
                following.objectName()
                or following.accessibleName()
                or getattr(following, "text", lambda: "")(),
                previous_rect,
                following_rect,
            )


def _assert_personal_layouts_do_not_overlap(view: RecommendationView) -> None:
    for layout in (
        view.personal_capture_row,
        view.assessment_capture_path_row,
        view.assessment_summary_path_row,
        view.assessment_action_row,
        view.personal_policy_row,
        view.personal_policy_history_row,
        view.personal_policy_history_selector_row,
        view.personal_policy_history_actions_row,
        view.personal_source_path_row,
        view.personal_candidate_row,
    ):
        _assert_layout_widgets_do_not_overlap(view, layout)


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
        view.result_scroll.ensureWidgetVisible(view.personal_policy_history_combo)
        for _ in range(5):
            app.processEvents()
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


def test_selected_recommendation_view_shows_full_saved_reasons_and_table_summary() -> None:
    app = _app()
    view = _new_view()
    item = RecommendationItem(
        stock_code="2330",
        stock_name="台積電",
        reason_text="理由甲+、理由乙-、理由丙、理由丁+、理由戊",
        reasons=("理由甲", "理由乙", "理由丙", "理由丁", "理由戊"),
        factor_contributions=(
            FactorContribution(
                factor_id="保存動能",
                value=Decimal("12.5000"),
                unit="rule-score",
                version="saved-v1",
                source_refs=(SourceRef("saved-rule", "rev-1", "snapshot-1"),),
            ),
        ),
        rank=4,
        eligible_universe_date=date(2026, 5, 20),
    )
    view.current_execution = SimpleNamespace(items=(item,))
    view.current_config = None
    # 此測試驗證選列展示保存內容，不需要建立額外研究上下文來源。
    view.research_context_label = None
    view.recommendations_model = PandasTableModel(
        pd.DataFrame(
            [recommendation_item_to_view_row(item, ml_status="not_requested")]
        )
    )
    view.results_table.setModel(view.recommendations_model)
    view.show()

    try:
        view.results_table.selectRow(0)
        view._update_detail_text()
        app.processEvents()

        detail = view.detail_text.toPlainText()
        assert "保存的推薦理由文字" in detail
        for saved_reason in ("理由甲+", "理由乙-", "理由丙", "理由丁+", "理由戊"):
            assert saved_reason in detail
        assert "保存動能：12.5000 rule-score" in detail
        assert "排名：4" in detail
        assert "合格母體日期：2026-05-20" in detail
        assert "表格摘要：" in detail
        assert "理由甲+、理由乙-、理由丙" in detail
        assert "理由丁+、理由戊" not in detail.split("表格摘要：", 1)[1]
    finally:
        view.close()
        app.processEvents()


def test_screening_row_explains_volume_threshold_and_preserves_original_evidence() -> None:
    """用使用者回報的未入選值核對真正選列展示，不只測純文字 helper。"""
    app = _app()
    view = _new_view()
    view.current_execution = SimpleNamespace(items=())
    view.current_config = None
    view.research_context_label = None
    view.recommendations_model = PandasTableModel(pd.DataFrame([{
        "紀錄類型": "篩選紀錄／未入選", "證券代號": "2382", "證券名稱": "廣達",
        "決策日": "2026-10-08", "階段": "strategy_evaluation",
        "原篩選狀態": "skipped", "原因代碼": "liquidity_volume_ratio_below_min",
        "觀測值": "-31.22936518258622391666432545", "要求值": "50",
        "證據品質": "degraded", "備註": "合成重現，非重新分析原始資料",
    }]))
    view.results_table.setModel(view.recommendations_model)
    try:
        view.resize(800, 700)
        view.show()
        view.results_table.selectRow(0)
        view._update_detail_text()
        app.processEvents()
        detail = view.detail_text.toPlainText()
        assert "觀測變化為 -31.23%" in detail
        assert "至少 50.00%" in detail
        assert "負值表示量縮" in detail
        assert "本次未產生推薦分數或排名" in detail
        assert "個人模型選股研究" in detail
        assert "觀測值／要求值：-31.22936518258622391666432545／50" in detail
        assert "liquidity_volume_ratio_below_min" in detail
        assert "證據品質：degraded" in detail
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


def test_personal_research_controls_are_scroll_reachable_at_390x844() -> None:
    app = _app()
    view = _new_view()
    _attach_layout_fixture(view)
    view.resize(390, 844)
    view.personal_research_toggle.setChecked(True)
    view.show()

    try:
        for _ in range(5):
            app.processEvents()
        assert view.width() == 390
        assert view.main_splitter.orientation() == Qt.Orientation.Vertical
        assert view.personal_policy_history_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        assert view.assessment_capture_path_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        assert view.personal_source_path_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        _assert_personal_controls_fit(view)
        _assert_personal_layouts_do_not_overlap(view)
        _assert_personal_controls_scroll_reachable(view, app)
    finally:
        view.close()
        app.processEvents()


def test_personal_research_controls_are_scroll_reachable_with_narrow_navigation() -> None:
    app = _app()
    shell = QWidget()
    shell.setObjectName("recommendationNarrowNavigationShellFixture")
    shell_layout = QHBoxLayout(shell)
    shell_layout.setContentsMargins(0, 0, 0, 0)
    shell_layout.setSpacing(0)
    navigation = QWidget(shell)
    navigation.setObjectName("narrowNavigationWidthFixture")
    navigation.setFixedWidth(184)
    shell_layout.addWidget(navigation)

    view = _new_view()
    _attach_layout_fixture(view)
    shell_layout.addWidget(view, 1)
    view.personal_research_toggle.setChecked(True)
    shell.resize(390, 844)
    shell.show()

    try:
        for _ in range(5):
            app.processEvents()
        assert navigation.width() == 184
        assert view.width() == 206
        assert view.main_splitter.orientation() == Qt.Orientation.Vertical
        assert view.personal_policy_history_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        assert view.assessment_capture_path_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        assert view.personal_source_path_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        _assert_personal_controls_fit(view)
        _assert_personal_layouts_do_not_overlap(view)
        _assert_personal_controls_scroll_reachable(view, app)
    finally:
        shell.close()
        app.processEvents()


def test_personal_research_controls_fit_shells_with_standard_navigation() -> None:
    app = _app()
    shell = QWidget()
    shell.setObjectName("recommendationStandardNavigationShellFixture")
    shell_layout = QHBoxLayout(shell)
    shell_layout.setContentsMargins(0, 0, 0, 0)
    shell_layout.setSpacing(0)
    navigation = QWidget(shell)
    navigation.setObjectName("standardNavigationWidthFixture")
    navigation.setFixedWidth(184)
    shell_layout.addWidget(navigation)

    view = _new_view()
    _attach_layout_fixture(view)
    shell_layout.addWidget(view, 1)
    view.personal_research_toggle.setChecked(True)
    shell.show()

    try:
        for shell_width in (760, 900):
            shell.resize(shell_width, 900)
            for _ in range(5):
                app.processEvents()
            assert navigation.width() == 184
            assert view.width() == shell_width - 184
            assert view.personal_policy_history_row.direction() == (
                QBoxLayout.Direction.TopToBottom
            )
            _assert_personal_controls_fit(view)
            _assert_personal_layouts_do_not_overlap(view)
            _assert_personal_controls_scroll_reachable(view, app)
    finally:
        shell.close()
        app.processEvents()

def test_recommendation_reason_expansion_preserves_content() -> None:
    app = _app()
    view = RecommendationView(_RecommendationService(), _RegimeService())
    try:
        view.resize(800, 700)
        view.show()
        app.processEvents()
        content = "保存的推薦理由與限制\n" * 30
        view.detail_text.setPlainText(content)
        view.detail_expand_button.click()
        app.processEvents()
        assert view.detail_text.height() >= 520
        assert view.detail_text.toPlainText() == content
        assert view.result_title_label.text() == "推薦結果與風險判讀"
        view.detail_expand_button.click()
        app.processEvents()
        assert view.detail_text.toPlainText() == content
        assert not view.detail_expand_button.isChecked()
        view.personal_policy_history_status_label.setText(
            "檢查 0 個封存項目，驗證 0 個較早版本。目前沒有可驗證的較早版本。"
        )
        view.personal_source_time_status_label.setText(
            "預設不信任任何資料庫來源，個人校準保持停用；請明確檢查來源後再另行確認。"
        )
        view.result_scroll.ensureWidgetVisible(view.personal_policy_history_combo)
        app.processEvents()
        _assert_personal_controls_fit(view)
        controls = (
            view.personal_policy_history_combo,
            view.personal_policy_history_refresh_button,
            view.personal_policy_rollback_button,
            view.personal_source_database_input,
            view.personal_source_database_browse_button,
            view.personal_source_time_check_button,
            view.personal_candidate_combo,
            view.personal_candidate_refresh_button,
        )
        for control in controls:
            assert control.height() >= control.sizeHint().height()
        for previous, following in zip(controls, controls[1:]):
            previous_rect = QRect(previous.mapTo(view, QPoint(0, 0)), previous.size())
            following_rect = QRect(following.mapTo(view, QPoint(0, 0)), following.size())
            assert not previous_rect.intersects(following_rect), (previous.objectName(), following.objectName())
        view.result_scroll.ensureWidgetVisible(view.personal_policy_history_combo)
        for _ in range(5):
            app.processEvents()
        _capture_if_requested(view, "recommendation_800x700_personal_history.png")
    finally:
        view.close()
        app.processEvents()


def test_expanded_reason_shows_complete_score_table_and_document_end() -> None:
    app = _app()
    view = _new_view()
    recommendation = SimpleNamespace(
        rule_score="30", total_score="30", indicator_score="20",
        pattern_score="25", volume_score="35", threshold_mode="fixed",
        ranking_method="ordinal", score_percentile_bp=7500,
        eligible_universe_size=257, price_change="-4", regime_match=False,
    )
    html = view._generate_explain_panel(recommendation)
    html += "<p>完整理由與來源限制。</p>" * 90 + "<p>文件最後一行：不可省略。</p>"
    html += view._generate_why_not(
        recommendation, {"filters": {"price_change_min": "1", "price_change_max": "8"}},
    )
    try:
        view.resize(800, 700)
        view.show()
        view.detail_text.setHtml(html)
        view.detail_expand_button.click()
        for _ in range(6):
            app.processEvents()
        assert "分數拆解" in view.detail_text.toPlainText()
        assert "排名門檻" in view.detail_text.toPlainText()
        assert "可能影響排名的因素" in view.detail_text.toPlainText()
        assert "總分較低，可能排名較後" in view.detail_text.toPlainText()
        assert view.detail_text.height() >= view.detail_text.document().size().height()
        assert view.detail_text.verticalScrollBar().maximum() == 0
        cursor = view.detail_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        assert view.detail_text.viewport().rect().contains(view.detail_text.cursorRect(cursor))
        assert view.result_scroll.verticalScrollBar().maximum() > 0
        saved_text = view.detail_text.toPlainText()
        view.resize(460, 700)
        for _ in range(6):
            app.processEvents()
        assert view.detail_text.height() >= view.detail_text.document().size().height()
        assert view.detail_text.toPlainText() == saved_text
        top = view.detail_text.mapTo(view.result_source_tabs, QPoint(0, 0)).y()
        view.result_scroll.verticalScrollBar().setValue(top)
        app.processEvents()
        _capture_if_requested(view, "recommendation_full_document_460x700.png")
        last_rect = view.detail_text.cursorRect(cursor)
        last_top = view.detail_text.viewport().mapTo(view.result_source_tabs, last_rect.topLeft()).y()
        view.result_scroll.verticalScrollBar().setValue(last_top)
        app.processEvents()
        last_visible = QRect(
            view.detail_text.viewport().mapTo(view.result_scroll.viewport(), last_rect.topLeft()),
            last_rect.size(),
        )
        assert view.result_scroll.viewport().rect().contains(last_visible)
        _capture_if_requested(view, "recommendation_full_document_end_460x700.png")
    finally:
        view.close()
        app.processEvents()


def test_expanded_reason_keyboard_reaches_document_end_in_narrow_view() -> None:
    app = _app()
    view = _new_view()
    recommendation = SimpleNamespace(
        rule_score="30", total_score="30", indicator_score="20",
        pattern_score="25", volume_score="35", threshold_mode="fixed",
        ranking_method="ordinal", score_percentile_bp=7500,
        eligible_universe_size=257, price_change="-4", regime_match=False,
    )
    html = view._generate_explain_panel(recommendation)
    html += "<p>完整理由與來源限制。</p>" * 90
    html += view._generate_why_not(
        recommendation, {"filters": {"price_change_min": "1", "price_change_max": "8"}},
    )
    html += "<p>可複製的理由文字。</p><p>鍵盤驗收最後一行：不可省略。</p>"
    try:
        view.resize(460, 700)
        view.show()
        view.detail_text.setHtml(html)
        view.detail_expand_button.click()
        for _ in range(6):
            app.processEvents()

        outer_bar = view.result_scroll.verticalScrollBar()
        inner_bar = view.detail_text.verticalScrollBar()
        assert outer_bar.maximum() > outer_bar.minimum()
        assert inner_bar.maximum() == 0
        assert outer_bar.value() == outer_bar.minimum()

        # 讓唯讀理由區取得真實鍵盤焦點；鍵盤事件不得困在展開的文字元件內。
        view.detail_text.setFocus(Qt.FocusReason.OtherFocusReason)
        assert view.detail_text.hasFocus()
        start_value = outer_bar.value()
        QTest.keyClick(view.detail_text, Qt.Key.Key_PageDown)
        app.processEvents()
        page_down_value = outer_bar.value()
        QTest.keyClick(view.detail_text, Qt.Key.Key_PageUp)
        app.processEvents()
        page_up_value = outer_bar.value()
        QTest.keyClick(view.detail_text, Qt.Key.Key_End)
        app.processEvents()
        end_key_value = outer_bar.value()
        QTest.keyClick(view.detail_text, Qt.Key.Key_Home)
        app.processEvents()
        home_key_value = outer_bar.value()
        QTest.keyClick(
            view.detail_text,
            Qt.Key.Key_End,
            Qt.KeyboardModifier.ControlModifier,
        )
        app.processEvents()
        ctrl_end_value = outer_bar.value()
        QTest.keyClick(view.detail_text, Qt.Key.Key_Home)
        app.processEvents()
        home_after_ctrl_end = outer_bar.value()

        end_cursor = QTextCursor(view.detail_text.document())
        end_cursor.movePosition(QTextCursor.MoveOperation.End)
        end_in_outer = QRect()
        page_down_to_visible: list[int] = []
        for _ in range(24):
            QTest.keyClick(view.detail_text, Qt.Key.Key_PageDown)
            app.processEvents()
            page_down_to_visible.append(outer_bar.value())
            end_rect = view.detail_text.cursorRect(end_cursor)
            end_in_outer = QRect(
                view.detail_text.viewport().mapTo(
                    view.result_scroll.viewport(), end_rect.topLeft()
                ),
                end_rect.size(),
            )
            if view.result_scroll.viewport().rect().contains(end_in_outer):
                break

        text = view.detail_text.toPlainText()
        copied_phrase = "可複製的理由文字。"
        copied_start = text.index(copied_phrase)
        selection = QTextCursor(view.detail_text.document())
        selection.setPosition(copied_start)
        selection.setPosition(
            copied_start + len(copied_phrase),
            QTextCursor.MoveMode.KeepAnchor,
        )
        view.detail_text.setTextCursor(selection)
        clipboard = app.clipboard()
        previous_clipboard = clipboard.text()
        try:
            QTest.keyClick(
                view.detail_text,
                Qt.Key.Key_C,
                Qt.KeyboardModifier.ControlModifier,
            )
            copied_text = clipboard.text()
        finally:
            clipboard.setText(previous_clipboard)

        diagnostics = (
            f"focus={view.detail_text.hasFocus()}; "
            f"outer={outer_bar.minimum()}..{outer_bar.maximum()}; "
            f"inner={inner_bar.minimum()}..{inner_bar.maximum()}; "
            f"start={start_value}; page_down={page_down_value}; "
            f"page_up={page_up_value}; end={end_key_value}; "
            f"home={home_key_value}; ctrl_end={ctrl_end_value}; "
            f"home_after_ctrl_end={home_after_ctrl_end}; "
            f"page_down_to_visible={page_down_to_visible}; "
            f"end_rect={end_in_outer}; "
            f"outer_viewport={view.result_scroll.viewport().rect()}"
        )
        assert page_down_value > start_value, diagnostics
        assert page_up_value == start_value, diagnostics
        assert end_key_value == outer_bar.maximum(), diagnostics
        assert home_key_value == outer_bar.minimum(), diagnostics
        assert ctrl_end_value == outer_bar.maximum(), diagnostics
        assert home_after_ctrl_end == outer_bar.minimum(), diagnostics
        assert page_down_to_visible, diagnostics
        assert copied_text == copied_phrase, diagnostics
        assert view.result_scroll.viewport().rect().contains(end_in_outer), diagnostics
    finally:
        view.close()
        app.processEvents()


def test_collapsed_reason_keeps_internal_keyboard_scrolling() -> None:
    app = _app()
    view = _new_view()
    try:
        view.resize(460, 700)
        view.show()
        view.detail_text.setPlainText("收合理由內容。\n" * 80)
        app.processEvents()

        inner_bar = view.detail_text.verticalScrollBar()
        outer_bar = view.result_scroll.verticalScrollBar()
        assert inner_bar.maximum() > inner_bar.minimum()
        outer_start = outer_bar.value()
        inner_start = inner_bar.value()
        view.detail_text.setFocus(Qt.FocusReason.OtherFocusReason)
        assert view.detail_text.hasFocus()

        QTest.keyClick(view.detail_text, Qt.Key.Key_PageDown)
        app.processEvents()

        assert inner_bar.value() > inner_start
        assert outer_bar.value() == outer_start
    finally:
        view.close()
        app.processEvents()
