"""個股研究頁的 append-only 研究動作控制項。"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QDateTimeEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app_module.decision_continuity_controller import (
    DecisionContinuityCommandResult,
    DecisionContinuityController,
    DecisionContinuityState,
)
from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_NOTE,
    ACTION_REVIEW_SCHEDULED,
    ACTION_SKIPPED,
    DecisionIdentity,
)
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.layout_helpers import ensure_visible_rows


class DecisionContinuityControlsWidget(QWidget):
    """讓研究者保存 candidate 狀態；不暴露任何交易或 Advice 採用動作。"""

    stateChanged = Signal(object)
    actionCompleted = Signal(object)

    def __init__(
        self,
        controller: DecisionContinuityController,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.identity: DecisionIdentity | None = None
        self.state: DecisionContinuityState | None = None
        self._pending_retry: dict[str, str] | None = None
        self._setup_ui()
        self._render_blocked("需要帶有 exact result_id + stock_code 的研究上下文。")

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        group = QGroupBox("研究動作（不採用 Advice／不下單）")
        group.setObjectName("decisionContinuityControls")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(10, 10, 10, 10)
        group_layout.setSpacing(6)

        self.status_label = QLabel("研究動作尚未載入。")
        self.status_label.setObjectName("decisionContinuityStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        group_layout.addWidget(self.status_label)

        self.note_summary_label = QLabel("筆記：尚無此 candidate 的研究筆記。")
        self.note_summary_label.setObjectName("decisionContinuityNoteSummary")
        self.note_summary_label.setWordWrap(True)
        self.note_summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        group_layout.addWidget(self.note_summary_label)

        action_layout = QHBoxLayout()
        self.action_layout = action_layout
        action_layout.setSpacing(6)
        self.accept_button = self._button(
            "納入研究", "將此 exact candidate 標記為已納入研究；不會採用 Advice。"
        )
        self.accept_button.clicked.connect(
            lambda: self._submit(ACTION_ACCEPTED)
        )
        action_layout.addWidget(self.accept_button)

        self.skip_button = self._button(
            "略過", "將此 exact candidate 標記為研究上略過；不會下單。"
        )
        self.skip_button.clicked.connect(lambda: self._submit(ACTION_SKIPPED))
        action_layout.addWidget(self.skip_button)

        self.note_button = self._button("記筆記", "為此 exact candidate 建立獨立研究筆記。")
        self.note_button.clicked.connect(self._ask_note)
        action_layout.addWidget(self.note_button)

        self.review_button = self._button(
            "設定下次檢視", "為此 exact candidate 保存下次人工檢視時間。"
        )
        self.review_button.clicked.connect(self._ask_review)
        action_layout.addWidget(self.review_button)
        group_layout.addLayout(action_layout)

        # Retry is an operational recovery action, so keep it in the visible
        # content area; technical IDs and the full history remain collapsible.
        self.retry_button = self._button(
            "重試上一個失敗動作", "沿用相同 request id 重試；不會把失敗顯示為成功。"
        )
        self.retry_button.clicked.connect(self._retry)
        self.retry_button.setVisible(False)
        group_layout.addWidget(self.retry_button, 0, Qt.AlignLeft)

        review_row = QHBoxLayout()
        review_row.setSpacing(6)
        review_row.addWidget(QLabel("下次檢視時間："))
        self.review_datetime = QDateTimeEdit(self._initial_taipei_datetime())
        self.review_datetime.setObjectName("decisionContinuityReviewDateTime")
        self.review_datetime.setAccessibleName("下次檢視日期時間")
        self.review_datetime.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.review_datetime.setCalendarPopup(True)
        self.review_datetime.setToolTip("以台北時間選擇日期與時間；無效日期不會保存。")
        self.review_datetime.setMinimumWidth(0)
        review_row.addWidget(self.review_datetime, 1)
        self.review_timezone_label = QLabel("台北時間")
        self.review_timezone_label.setWordWrap(True)
        review_row.addWidget(self.review_timezone_label)
        self.review_row = review_row
        group_layout.addLayout(review_row)

        self.technical_toggle = QPushButton("顯示技術詳情")
        self.technical_toggle.setObjectName("decisionContinuityTechnicalToggle")
        self.technical_toggle.setProperty("variant", "secondary")
        self.technical_toggle.setAccessibleName("展開或收合研究動作技術詳情")
        self.technical_toggle.clicked.connect(self._toggle_technical_details)
        group_layout.addWidget(self.technical_toggle, 0, Qt.AlignLeft)

        self.technical_details = QWidget()
        self.technical_details.setObjectName("decisionContinuityTechnicalDetails")
        technical_layout = QVBoxLayout(self.technical_details)
        technical_layout.setContentsMargins(0, 0, 0, 0)
        technical_layout.setSpacing(4)
        self.identity_label = QLabel("身份：尚未連結")
        self.identity_label.setObjectName("decisionContinuityIdentity")
        self.identity_label.setWordWrap(True)
        self.identity_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        technical_layout.addWidget(self.identity_label)
        history_heading = QLabel("此 candidate 的 append-only 歷史")
        history_heading.setProperty("role", "muted")
        technical_layout.addWidget(history_heading)
        self.history_list = QListWidget()
        self.history_list.setObjectName("decisionContinuityHistory")
        self.history_list.setAccessibleName("研究動作歷史")
        self.history_list.setSelectionMode(QListWidget.NoSelection)
        self.history_list.setFocusPolicy(Qt.NoFocus)
        self.history_list.setWordWrap(True)
        self.history_list.setUniformItemSizes(False)
        self.history_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ensure_visible_rows(self.history_list, 5)
        technical_layout.addWidget(self.history_list)
        self.technical_details.setVisible(False)
        group_layout.addWidget(self.technical_details)
        root.addWidget(group)
        self._apply_responsive_layouts()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_responsive_layouts()

    def _apply_responsive_layouts(self) -> None:
        direction = (
            QBoxLayout.Direction.TopToBottom
            if self.width() < 680
            else QBoxLayout.Direction.LeftToRight
        )
        self.action_layout.setDirection(direction)
        self.review_row.setDirection(direction)

    @staticmethod
    def _initial_taipei_datetime() -> QDateTime:
        now = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Taipei"))
        return QDateTime.fromString(
            now.strftime("%Y-%m-%d %H:%M:%S"),
            "yyyy-MM-dd HH:mm:ss",
        )

    def _toggle_technical_details(self) -> None:
        visible = not self.technical_details.isVisible()
        self.technical_details.setVisible(visible)
        self.technical_toggle.setText("隱藏技術詳情" if visible else "顯示技術詳情")

    @staticmethod
    def _button(text: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("variant", "secondary")
        button.setMinimumHeight(30)
        button.setToolTip(tooltip)
        button.setAccessibleName(text)
        return button

    def set_context(self, context: object | None) -> None:
        """從研究 context 建立 typed identity 並重新讀回狀態。"""

        try:
            identity = self.controller.identity_from_context(context)
        except (TypeError, ValueError) as exc:
            self.identity = None
            self.state = None
            self._pending_retry = None
            self._render_blocked(f"研究 identity 無法解析：{exc}")
            return
        self.set_identity(identity)

    def set_blocked(
        self,
        message: str,
        *,
        identity: DecisionIdentity | None = None,
    ) -> None:
        """停用研究動作，直到呼叫端重新驗證 exact candidate。"""

        self.identity = identity
        self.state = None
        self._pending_retry = None
        self._render_blocked(message, identity=identity)

    def set_identity(self, identity: DecisionIdentity | None) -> None:
        self.identity = identity
        self._pending_retry = None
        if identity is None:
            self.state = None
            self._render_blocked("需要帶有 exact result_id + stock_code 的研究上下文。")
            return
        self.refresh_state()

    def refresh_state(self) -> None:
        if self.identity is None:
            self.state = None
            self._render_blocked("需要帶有 exact result_id + stock_code 的研究上下文。")
            return
        self.state = self.controller.read_state(self.identity)
        self._render_state(self.state)
        self.stateChanged.emit(self.state)

    def _render_blocked(
        self,
        message: str,
        *,
        identity: DecisionIdentity | None = None,
    ) -> None:
        if identity is None:
            self.identity_label.setText("身份：未連結")
        else:
            self.identity_label.setText(
                "身份："
                f"result_id={identity.result_id or '未知'}｜"
                f"stock_code={identity.stock_code or '未知'}｜"
                f"identity_status={identity.identity_status}"
            )
        self.status_label.setText(f"操作已停用：{message}")
        self.status_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        self.note_summary_label.setText("筆記：未讀取。")
        self.history_list.clear()
        self._set_action_enabled(False)
        self.retry_button.setVisible(False)
        self.retry_button.setEnabled(False)

    def _render_state(self, state: DecisionContinuityState) -> None:
        identity = state.identity
        self.identity_label.setText(
            "身份："
            f"result_id={identity.result_id or '未知'}｜"
            f"stock_code={identity.stock_code or '未知'}｜"
            f"identity_status={identity.identity_status}"
        )
        if not state.can_write:
            self._render_blocked(state.blocked_reason, identity=identity)
            return

        decision_text = {
            "unrecorded": "尚未記錄",
            "accepted": "已納入研究",
            "skipped": "已略過",
        }.get(state.decision_status, state.decision_status)
        review_text = state.next_review_at or "未設定"
        self.status_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary};")
        self.status_label.setText(
            f"研究狀態：{decision_text}｜Journal 紀錄：{state.active_note_count} 筆｜"
            f"下次檢視：{review_text}｜歷史：{len(state.history)} 筆"
        )
        note_rows = tuple(
            item
            for item in state.history
            if item.action == ACTION_NOTE and item.note
        )
        self.note_summary_label.setText(
            "最近筆記："
            + (note_rows[-1].note if note_rows else "尚無此 candidate 的研究筆記。")
        )
        self._set_action_enabled(True)
        self.retry_button.setVisible(self._pending_retry is not None)
        self.retry_button.setEnabled(self._pending_retry is not None)
        self._render_history(state)

    def _render_history(self, state: DecisionContinuityState) -> None:
        self.history_list.clear()
        for revision in state.history:
            detail = revision.note or revision.next_review_at or ""
            text = (
                f"{revision.created_at or '時間未知'}｜{self._action_text(revision.action)}｜"
                f"revision={revision.revision_id}"
            )
            if detail:
                text += f"｜{detail}"
            item = self.history_list.addItem(text)
            del item
        if not state.history:
            self.history_list.addItem("尚無此 candidate 的研究動作；可使用上方按鈕建立。")

    def _set_action_enabled(self, enabled: bool) -> None:
        for button in (
            self.accept_button,
            self.skip_button,
            self.note_button,
            self.review_button,
        ):
            button.setEnabled(enabled)

    def _ask_note(self) -> None:
        if self.identity is None or self.state is None or not self.state.can_write:
            return
        value, accepted = QInputDialog.getMultiLineText(
            self,
            "記錄研究筆記",
            "筆記內容（會獨立連回目前 candidate）：",
        )
        if accepted and value.strip():
            self._submit(ACTION_NOTE, note=value.strip())

    def _ask_review(self) -> None:
        if self.identity is None or self.state is None or not self.state.can_write:
            return
        selected = self.review_datetime.dateTime()
        if not selected.isValid():
            self.status_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
            self.status_label.setText("下次檢視日期無效，未保存；請重新選擇日期。")
            return
        # QDateTimeEdit 的值以使用者看到的台北牆上時間保存，明確補上
        # Asia/Taipei offset；controller 仍會再次驗證與正規化。
        value = selected.toString("yyyy-MM-dd'T'HH:mm:ss") + "+08:00"
        self._submit(ACTION_REVIEW_SCHEDULED, next_review_at=value)

    @staticmethod
    def _action_text(action: str) -> str:
        return {
            ACTION_ACCEPTED: "納入研究",
            ACTION_SKIPPED: "略過",
            ACTION_NOTE: "記筆記",
            ACTION_REVIEW_SCHEDULED: "設定下次檢視",
        }.get(action, action)

    def _submit(
        self,
        action: str,
        *,
        note: str = "",
        next_review_at: str = "",
        request_id: str | None = None,
    ) -> None:
        if self.identity is None:
            return
        try:
            result = self.controller.apply(
                action,
                self.identity,
                note=note,
                next_review_at=next_review_at,
                request_id=request_id,
            )
        except Exception as exc:
            self._render_blocked(f"研究動作未送出：{exc}")
            return
        self._handle_result(
            result,
            action=action,
            note=note,
            next_review_at=next_review_at,
        )

    def _handle_result(
        self,
        result: DecisionContinuityCommandResult,
        *,
        action: str,
        note: str,
        next_review_at: str,
    ) -> None:
        self.state = result.state
        if result.success and result.readback_verified:
            self._pending_retry = None
            self._render_state(result.state)
            self.status_label.setText(result.message)
        elif result.success:
            # write 已完成但 readback 失敗時，不顯示成已驗證的狀態；保留
            # retry button 以便使用者重新讀取／重送同一 request。
            self._pending_retry = {
                "action": action,
                "note": note,
                "next_review_at": next_review_at,
                "request_id": result.request_id,
            }
            self._render_blocked(result.message)
            self.retry_button.setVisible(True)
            self.retry_button.setEnabled(True)
        elif result.retryable:
            self._pending_retry = {
                "action": action,
                "note": note,
                "next_review_at": next_review_at,
                "request_id": result.request_id,
            }
            self._render_state(result.state)
            self.status_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.danger};")
            self.status_label.setText(result.message)
            self.retry_button.setEnabled(True)
        else:
            self._pending_retry = None
            self._render_state(result.state)
            self.status_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
            self.status_label.setText(result.message)
        self.actionCompleted.emit(result)

    def _retry(self) -> None:
        pending = self._pending_retry
        if pending is None:
            return
        self._submit(
            pending["action"],
            note=pending["note"],
            next_review_at=pending["next_review_at"],
            request_id=pending["request_id"],
        )


__all__ = ["DecisionContinuityControlsWidget"]


class PersonalRecommendationChoiceControlsWidget(QWidget):
    """對已保存推薦記錄個人選擇；不代表 Advice 採用或交易。"""

    choiceRequested = Signal(str)
    retryRequested = Signal()

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_personal_choice_ui()
        self.set_context_available(
            False,
            "先保存並驗證推薦結果，再選取一檔股票記錄個人決定。",
        )

    def _setup_personal_choice_ui(self) -> None:
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        group = QGroupBox("個人決定（研究紀錄，不下單）")
        group.setObjectName("personalRecommendationChoiceControls")
        layout = QVBoxLayout(group)
        self.status_label = QLabel("尚未選取已保存推薦。")
        self.status_label.setObjectName("personalRecommendationChoiceStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        actions = QBoxLayout(QBoxLayout.LeftToRight)
        actions.setSpacing(6)
        self._choice_actions_layout = actions
        self.adopt_button = QPushButton("個人採用")
        self.adopt_button.setObjectName("personalRecommendationAdopt")
        self.adopt_button.setToolTip("記錄你對此已保存推薦的個人採用決定；不會送出委託。")
        self.adopt_button.clicked.connect(lambda: self.choiceRequested.emit("adopt"))
        actions.addWidget(self.adopt_button)

        self.reject_button = QPushButton("個人拒絕")
        self.reject_button.setObjectName("personalRecommendationReject")
        self.reject_button.setToolTip("記錄你對此已保存推薦的個人拒絕決定；不會改寫推薦結果。")
        self.reject_button.clicked.connect(lambda: self.choiceRequested.emit("reject"))
        actions.addWidget(self.reject_button)

        self.override_button = QPushButton("推翻並記原因")
        self.override_button.setObjectName("personalRecommendationOverride")
        self.override_button.setToolTip("以結構化原因記錄與推薦不同的個人決定；不會送出委託。")
        self.override_button.clicked.connect(lambda: self.choiceRequested.emit("override"))
        actions.addWidget(self.override_button)

        self.retry_button = QPushButton("重試讀回")
        self.retry_button.setObjectName("personalRecommendationChoiceRetry")
        self.retry_button.clicked.connect(self.retryRequested.emit)
        self.retry_button.setVisible(False)
        actions.addWidget(self.retry_button)
        layout.addLayout(actions)
        root.addWidget(group)
        self._apply_choice_action_layout()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._apply_choice_action_layout()

    def _apply_choice_action_layout(self) -> None:
        """窄版將個人決定按鈕直排，避免縮成難以辨識的窄欄。"""

        direction = (
            QBoxLayout.TopToBottom
            if self.width() < 660
            else QBoxLayout.LeftToRight
        )
        if self._choice_actions_layout.direction() != direction:
            self._choice_actions_layout.setDirection(direction)

    def set_context_available(self, available: bool, message: str) -> None:
        self.status_label.setText(message)
        self.adopt_button.setEnabled(available)
        self.reject_button.setEnabled(available)
        self.override_button.setEnabled(available)

    def show_retry(self, message: str) -> None:
        self.set_context_available(False, message)
        self.retry_button.setVisible(True)
        self.retry_button.setEnabled(True)

    def clear_retry(self) -> None:
        self.retry_button.setVisible(False)
        self.retry_button.setEnabled(False)


__all__.append("PersonalRecommendationChoiceControlsWidget")
