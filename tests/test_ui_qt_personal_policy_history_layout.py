"""個人推薦模式歷史版本列的真實 Qt 幾何與鍵盤可達性。"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout

from app_module.dtos import RegimeResultDTO
from ui_qt.main import apply_app_theme
from ui_qt.views.recommendation_view import RecommendationView


class _RecommendationService:
    """不連接正式來源的空服務。"""


class _RegimeService:
    def detect_regime(self):
        return RegimeResultDTO(
            regime="Trend",
            confidence=0.5,
            regime_name_cn="趨勢追蹤",
            details={"source": "history_layout_fixture", "as_of_date": "2026-10-06"},
        )

    def get_strategy_config(self, regime):
        return {"regime": regime}


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    apply_app_theme(instance)
    return instance


def _new_view() -> RecommendationView:
    return RecommendationView(
        recommendation_service=_RecommendationService(),
        regime_service=_RegimeService(),
        config=None,
    )


def test_history_controls_initialize_without_cross_window_tab_order_warning() -> None:
    app = _app()
    messages: list[str] = []
    previous = qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))
    view = None
    try:
        view = _new_view()
        app.processEvents()
        assert view.personal_policy_history_combo.window() is view
        assert view.personal_policy_history_refresh_button.window() is view
        assert view.personal_policy_rollback_button.window() is view
    finally:
        if view is not None:
            view.close()
            view.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        qInstallMessageHandler(previous)
    assert not [message for message in messages if "setTabOrder" in message]


def _assert_history_controls_fit(view: RecommendationView) -> None:
    controls = (
        view.personal_policy_history_label,
        view.personal_policy_history_combo,
        view.personal_policy_history_refresh_button,
        view.personal_policy_rollback_button,
    )
    for control in controls:
        assert control.isVisible()
        assert control.height() >= control.sizeHint().height()

    for button in (
        view.personal_policy_history_refresh_button,
        view.personal_policy_rollback_button,
    ):
        assert button.width() >= button.sizeHint().width()
        assert button.text() in button.accessibleName()

    assert view.personal_policy_history_combo.width() >= (
        view.personal_policy_history_combo.minimumSizeHint().width()
    )


def test_personal_policy_history_row_responds_to_its_result_pane_geometry() -> None:
    app = _app()
    view = _new_view()
    full_version_label = (
        "版本 12｜確認 2026-10-07 15:31:42 PDT｜規則模式｜候選 2330"
    )
    view.personal_policy_history_combo.addItem(full_version_label)
    view.personal_policy_history_combo.setEnabled(True)
    view.personal_policy_history_refresh_button.setEnabled(True)
    view.personal_policy_rollback_button.setEnabled(True)
    view.resize(1920, 1080)
    view.show()

    try:
        app.processEvents()
        assert view.result_scroll.isAncestorOf(view.personal_policy_group)
        view.main_splitter.setSizes([1400, 420])
        view._apply_responsive_layout(force=True)
        app.processEvents()
        view.result_scroll.ensureWidgetVisible(view.personal_policy_history_combo)
        app.processEvents()

        # 歷史控制項位於右側；左側很寬時仍須按自己的窄 viewport 排列。
        assert view.config_scroll.viewport().width() >= 900
        assert view.result_scroll.viewport().width() < 560
        assert view.personal_policy_history_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        assert view.personal_policy_history_selector_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        assert view.personal_policy_history_actions_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        _assert_history_controls_fit(view)

        refresh_rect = view.personal_policy_history_refresh_button.geometry()
        rollback_rect = view.personal_policy_rollback_button.geometry()
        assert refresh_rect.bottom() < rollback_rect.top()
        assert not refresh_rect.intersects(rollback_rect)
        # mapTo 的目標須為各控制項的共同祖先，不能使用 selector 的兄弟 host。
        history_parent = view.personal_policy_group
        label_top = view.personal_policy_history_label.mapTo(
            history_parent, QPoint(0, 0)
        ).y()
        combo_top = view.personal_policy_history_combo.mapTo(
            history_parent, QPoint(0, 0)
        ).y()
        refresh_top = view.personal_policy_history_refresh_button.mapTo(
            history_parent, QPoint(0, 0)
        ).y()
        assert label_top < combo_top < refresh_top

        combo = view.personal_policy_history_combo
        assert combo.accessibleName() == "已保存版本"
        assert full_version_label in combo.accessibleDescription()
        assert combo.toolTip() == full_version_label
        assert view.personal_policy_history_label.buddy() is combo

        combo.setFocus()
        app.processEvents()
        QTest.keyClick(combo, Qt.Key.Key_Tab)
        assert app.focusWidget() is view.personal_policy_history_refresh_button
        QTest.keyClick(view.personal_policy_history_refresh_button, Qt.Key.Key_Tab)
        assert app.focusWidget() is view.personal_policy_rollback_button

        # 使用者拖寬結果欄後恢復同行配置，左側維持窄版以驗證來源正確。
        view.main_splitter.setSizes([420, 1400])
        view._apply_responsive_layout(force=True)
        app.processEvents()
        assert view.result_scroll.viewport().width() >= 900
        assert view.config_scroll.viewport().width() < 560
        assert view.personal_policy_history_row.direction() == (
            QBoxLayout.Direction.LeftToRight
        )
        assert view.personal_policy_history_selector_row.direction() == (
            QBoxLayout.Direction.LeftToRight
        )
        assert view.personal_policy_history_actions_row.direction() == (
            QBoxLayout.Direction.LeftToRight
        )
        _assert_history_controls_fit(view)
        wide_tops = {
            widget.mapTo(history_parent, QPoint(0, 0)).y()
            for widget in (
                view.personal_policy_history_label,
                view.personal_policy_history_combo,
                view.personal_policy_history_refresh_button,
                view.personal_policy_rollback_button,
            )
        }
        assert max(wide_tops) - min(wide_tops) < 12

        view.resize(390, 844)
        app.processEvents()
        view.result_scroll.ensureWidgetVisible(view.personal_policy_history_combo)
        app.processEvents()
        assert view.personal_policy_history_row.direction() == (
            QBoxLayout.Direction.TopToBottom
        )
        _assert_history_controls_fit(view)
    finally:
        view.close()
        app.processEvents()
