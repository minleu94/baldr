"""題材研究筆記 UI；保存與讀回均走既有 journal service 的背景任務。"""

from __future__ import annotations

from datetime import date
import re
from typing import Any
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_module.theme_research_notes import ThemeResearchNote, ThemeResearchNoteService
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from ui_qt.workers.task_worker import TaskWorker


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_NOTE_LENGTH = 8000


class _ThemeResearchNoteSaveWorker(TaskWorker):
    """保護已開始的 Journal 寫入，不讓全域關閉取消旗標藏掉結果。"""

    def cancel(self, cooperative: bool = True, wait: bool = False) -> None:
        return None


class ThemeResearchNotesWidget(QWidget):
    """保存綁定原題材快照的使用者筆記，不產生估計、建議或交易。"""

    openSnapshotRequested = Signal(str)

    def __init__(
        self,
        service: ThemeResearchNoteService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._service = service
        self._snapshot: ThemeResearchSnapshot | None = None
        self._draft_snapshot: ThemeResearchSnapshot | None = None
        self._draft_snapshot_identity: str | None = None
        self._draft_revision_of: str | None = None
        self._draft_source_missing = False
        self._updating_editor = False
        self._updating_revisions = False
        self._loaded_note: ThemeResearchNote | None = None
        self._notes_by_id: dict[str, ThemeResearchNote] = {}
        self._select_after_refresh: str | None = None
        self._refresh_requested = False
        self._post_refresh_status: str | None = None
        self._shutdown = False
        self._workers: dict[int, TaskWorker] = {}
        self._active_worker: TaskWorker | None = None
        self._active_job: dict[str, Any] | None = None
        self._active_outcome: tuple[str, Any] | None = None
        self._active_native_finished = False

        self._build_ui()
        self.editor.textChanged.connect(self._on_editor_changed)
        self.revisions.currentIndexChanged.connect(self._on_revision_selected)
        self.save_button.clicked.connect(self._save_current_draft)
        self.revise_button.clicked.connect(self._prepare_revision)
        self.read_button.clicked.connect(self._read_selected)
        self.open_source_button.clicked.connect(self._open_selected_source)
        self.refresh_notes()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        heading = QLabel(
            "使用者研究判斷｜保存當下題材版本與資料日，供日後核對。"
            "這是個人筆記，不是估計、策略訊號、交易指示或歷史回測證據。"
        )
        heading.setWordWrap(True)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(heading)

        self.source_label = QLabel("目前題材來源：尚未載入；可讀取已保存筆記。")
        self.source_label.setWordWrap(True)
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.source_label)

        selection_row = QHBoxLayout()
        self.revisions = QComboBox()
        selection_row.addWidget(self.revisions, 1)
        self.revisions.setObjectName("themeResearchNoteRevisions")
        layout.addLayout(selection_row)

        note_actions = QHBoxLayout()
        self.read_button = QPushButton("讀取所選修訂")
        self.read_button.setObjectName("themeResearchNoteRead")
        self.open_source_button = QPushButton("核對原來源")
        self.open_source_button.setObjectName("themeResearchNoteOpenSource")
        self.revise_button = QPushButton("以此筆記另存修訂")
        self.revise_button.setObjectName("themeResearchNoteRevise")
        note_actions.addWidget(self.read_button)
        note_actions.addWidget(self.open_source_button)
        note_actions.addWidget(self.revise_button)
        layout.addLayout(note_actions)

        compare_actions = QHBoxLayout()
        self.compare_previous_button = QPushButton("比較與前一版")
        self.compare_previous_button.setObjectName("themeResearchNoteComparePrevious")
        self.compare_previous_button.clicked.connect(self._compare_with_previous)
        compare_actions.addWidget(self.compare_previous_button)
        compare_actions.addStretch(1)
        layout.addLayout(compare_actions)

        self._build_comparison_dialog()

        saved_label = QLabel("已保存內容（唯讀）")
        saved_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(saved_label)
        self.saved_text = QPlainTextEdit()
        self.saved_text.setObjectName("themeResearchNoteSavedText")
        self.saved_text.setReadOnly(True)
        self.saved_text.setPlaceholderText("選取一筆修訂並按「讀取所選修訂」查看原文。")
        self.saved_text.setMinimumHeight(72)
        self.saved_text.setMaximumHeight(132)
        layout.addWidget(self.saved_text)

        draft_label = QLabel("新筆記／修訂草稿（最多 8,000 字）")
        draft_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(draft_label)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("themeResearchNoteEditor")
        self.editor.setPlaceholderText(
            "輸入自己的研究判斷。輸入時會固定當下已載入的題材來源；"
            "不會在切換來源後改綁。"
        )
        self.editor.setMinimumHeight(78)
        self.editor.setMaximumHeight(150)
        layout.addWidget(self.editor)

        action_row = QHBoxLayout()
        self.save_button = QPushButton("保存新筆記")
        self.save_button.setObjectName("themeResearchNoteSave")
        action_row.addWidget(self.save_button)
        layout.addLayout(action_row)

        self.status_label = QLabel("正在載入已保存筆記…")
        self.status_label.setObjectName("themeResearchNoteStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status_label)
        self._update_controls()

    def _build_comparison_dialog(self) -> None:
        self.compare_dialog = QDialog(self, Qt.WindowType.Window)
        self.compare_dialog.setObjectName("themeResearchNoteComparisonDialog")
        self.compare_dialog.setWindowTitle("題材研究筆記｜與前一版比較")
        self.compare_dialog.resize(800, 520)
        dialog_layout = QVBoxLayout(self.compare_dialog)

        explanation = QLabel(
            "使用者研究判斷的保存原文對照；不代表績效、歷史 PIT 資格或交易判斷。"
        )
        explanation.setWordWrap(True)
        explanation.setTextFormat(Qt.TextFormat.PlainText)
        dialog_layout.addWidget(explanation)

        columns = QHBoxLayout()
        previous_column = QVBoxLayout()
        self.comparison_previous_identity = QLabel("前一版：尚未載入")
        self.comparison_previous_identity.setObjectName("themeResearchNotePreviousIdentity")
        self.comparison_previous_identity.setWordWrap(True)
        self.comparison_previous_identity.setTextFormat(Qt.TextFormat.PlainText)
        previous_column.addWidget(self.comparison_previous_identity)
        self.comparison_previous_text = QPlainTextEdit()
        self.comparison_previous_text.setObjectName("themeResearchNotePreviousText")
        self.comparison_previous_text.setReadOnly(True)
        self.comparison_previous_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.comparison_previous_text.setMinimumWidth(280)
        previous_column.addWidget(self.comparison_previous_text, 1)
        columns.addLayout(previous_column, 1)

        selected_column = QVBoxLayout()
        self.comparison_selected_identity = QLabel("目前所選修訂：尚未載入")
        self.comparison_selected_identity.setObjectName("themeResearchNoteSelectedIdentity")
        self.comparison_selected_identity.setWordWrap(True)
        self.comparison_selected_identity.setTextFormat(Qt.TextFormat.PlainText)
        selected_column.addWidget(self.comparison_selected_identity)
        self.comparison_selected_text = QPlainTextEdit()
        self.comparison_selected_text.setObjectName("themeResearchNoteSelectedText")
        self.comparison_selected_text.setReadOnly(True)
        self.comparison_selected_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.comparison_selected_text.setMinimumWidth(280)
        selected_column.addWidget(self.comparison_selected_text, 1)
        columns.addLayout(selected_column, 1)
        dialog_layout.addLayout(columns, 1)
        self._clear_comparison(close_dialog=False)

    def set_snapshot(self, snapshot: ThemeResearchSnapshot | None) -> None:
        """切換目前來源，但不改綁既有草稿或已送出的保存工作。"""

        if snapshot is not None and not isinstance(snapshot, ThemeResearchSnapshot):
            raise TypeError("snapshot must be ThemeResearchSnapshot or None")
        previous_identity = _snapshot_identity(self._snapshot)
        self._snapshot = snapshot
        current_identity = _snapshot_identity(snapshot)
        if previous_identity != current_identity:
            self._clear_comparison()
        if snapshot is None:
            self.source_label.setText("目前題材來源：尚未載入；可讀取已保存筆記。")
        else:
            data_date = _snapshot_data_date(snapshot)
            identity = current_identity or "來源身份無效"
            self.source_label.setText(
                f"目前題材來源｜資料日：{data_date or '未知'}｜完整快照 SHA-256：{identity}"
            )

        job = self._active_job
        if job is not None and job.get("kind") == "save":
            if current_identity != job.get("snapshot_identity"):
                self._set_status(
                    "來源已切換；正在保存的筆記仍鎖定原來源 "
                    f"{job.get('snapshot_identity')}，不會改綁新來源。"
                )
        elif self._draft_snapshot is not None:
            if current_identity != self._draft_snapshot_identity:
                self._set_status(
                    "草稿仍鎖定輸入時的原來源 "
                    f"{self._draft_snapshot_identity}；切換來源不會替草稿改簽。"
                )
            else:
                self._set_status("草稿已綁定目前明選來源；保存會保留該來源與原資料日。")
        elif self._draft_source_missing and self.editor.toPlainText().strip():
            self._set_status("此草稿輸入時沒有來源，不能自動綁到新來源；清空後重新輸入即可。")
        elif current_identity is not None:
            self._set_status("新筆記會綁定目前明選來源；既有筆記仍保留各自原來源。")
        elif previous_identity != current_identity:
            self._set_status("目前沒有可保存的新來源；已保存筆記仍可逐筆讀取。")
        self._update_controls()

    def refresh_notes(self) -> None:
        """背景刷新已保存修訂清單；忙碌時排在目前工作之後。"""

        self._clear_comparison()
        if self._shutdown:
            return
        if self.is_busy():
            self._refresh_requested = True
            return
        self._set_status("正在讀取已保存筆記清單…")
        self._start_worker("list", self._service.list_notes)

    def is_busy(self) -> bool:
        return self._active_worker is not None

    def shutdown(self) -> None:
        """只送合作式讀取取消；保存不強制中止或終止執行緒。"""

        if self._shutdown:
            return
        self._shutdown = True
        self._clear_comparison()
        worker = self._active_worker
        job = self._active_job
        if worker is not None and job is not None:
            if job.get("kind") == "save":
                self._set_status(
                    "保存已送出且不能安全強制中止；關閉時結果未知，重開後請刷新並核對修訂。"
                )
            else:
                worker.cancel(cooperative=True, wait=False)
                self._set_status("已要求停止背景讀取；本次清單或內容不會寫入。")
        self._refresh_requested = False
        self._update_controls()

    def _on_editor_changed(self) -> None:
        if self._updating_editor or self._shutdown:
            return
        text = self.editor.toPlainText()
        if not text.strip():
            self._reset_draft_binding()
        elif self._draft_snapshot is None and not self._draft_source_missing:
            if self._snapshot is None:
                self._draft_source_missing = True
            else:
                self._draft_snapshot = self._snapshot
                self._draft_snapshot_identity = _snapshot_identity(self._snapshot)
        self._update_controls()

    def _on_revision_selected(self, *_args: Any) -> None:
        if self._updating_revisions:
            return
        self._clear_comparison()
        selected = self._selected_revision_id()
        if self._loaded_note is not None and self._loaded_note.revision_id != selected:
            self._loaded_note = None
            self.saved_text.clear()
        self._update_controls()

    def _read_selected(self) -> None:
        if self.is_busy() or self._shutdown:
            return
        revision_id = self._selected_revision_id()
        if not revision_id:
            self._set_status("請先明選一筆已保存修訂。")
            return
        self._set_status(f"正在讀取指定修訂 {revision_id}…")
        self._start_worker(
            "read",
            self._service.get_note,
            revision_id,
            job={"kind": "read", "revision_id": revision_id},
        )

    def _compare_with_previous(self) -> None:
        if self.is_busy() or self._shutdown:
            self._clear_comparison()
            self._update_controls()
            return
        pair = self._comparison_pair()
        if pair is None:
            self._clear_comparison()
            self._set_status("所選修訂沒有可核對的同來源、同資料日直接前版。")
            self._update_controls()
            return

        previous, selected = pair
        self.comparison_previous_identity.setText(_comparison_identity("前一版", previous))
        self.comparison_previous_identity.setToolTip(
            _comparison_identity_tooltip("前一版", previous)
        )
        self.comparison_selected_identity.setText(
            _comparison_identity("目前所選修訂", selected)
        )
        self.comparison_selected_identity.setToolTip(
            _comparison_identity_tooltip("目前所選修訂", selected)
        )
        self.comparison_previous_text.setPlainText(previous.text)
        self.comparison_selected_text.setPlainText(selected.text)
        self.compare_dialog.show()
        self.compare_dialog.raise_()
        self.compare_dialog.activateWindow()

    def _comparison_pair(self) -> tuple[ThemeResearchNote, ThemeResearchNote] | None:
        selected_id = self._selected_revision_id()
        selected = self._notes_by_id.get(selected_id or "")
        if not isinstance(selected, ThemeResearchNote):
            return None
        previous_id = selected.revision_of
        if (
            not isinstance(previous_id, str)
            or not previous_id
            or previous_id == selected.revision_id
        ):
            return None
        previous = self._notes_by_id.get(previous_id)
        if not isinstance(previous, ThemeResearchNote):
            return None
        source_identity = selected.snapshot_identity_sha256
        if (
            not isinstance(source_identity, str)
            or not _SHA256_RE.fullmatch(source_identity)
            or previous.snapshot_identity_sha256 != source_identity
        ):
            return None
        if (
            not isinstance(selected.data_date, str)
            or not selected.data_date
            or previous.data_date != selected.data_date
        ):
            return None
        return previous, selected

    def _clear_comparison(self, *, close_dialog: bool = True) -> None:
        if hasattr(self, "comparison_previous_text"):
            self.comparison_previous_text.clear()
            self.comparison_selected_text.clear()
            self.comparison_previous_identity.setText("前一版：尚未載入")
            self.comparison_selected_identity.setText("目前所選修訂：尚未載入")
            self.comparison_previous_identity.setToolTip("")
            self.comparison_selected_identity.setToolTip("")
        dialog = getattr(self, "compare_dialog", None)
        if close_dialog and dialog is not None and dialog.isVisible():
            dialog.close()

    def _open_selected_source(self) -> None:
        revision_id = self._selected_revision_id()
        note = self._notes_by_id.get(revision_id or "")
        if note is None:
            self._set_status("請先刷新並明選一筆已保存修訂，才能核對其原來源。")
            return
        if not _SHA256_RE.fullmatch(note.snapshot_identity_sha256):
            self._set_status("所選筆記的來源 SHA-256 格式無效，未開啟來源。")
            return
        self.openSnapshotRequested.emit(note.snapshot_identity_sha256)

    def _prepare_revision(self) -> None:
        selected_id = self._selected_revision_id()
        note = self._loaded_note
        current_identity = _snapshot_identity(self._snapshot)
        if note is None or note.revision_id != selected_id:
            self._set_status("請先讀取所選修訂；唯讀原文載入後才能另存修訂。")
            return
        if self._snapshot is None or current_identity != note.snapshot_identity_sha256:
            self._set_status("修訂只可沿用相同原快照；請先按「核對原來源」載入該版本。")
            return
        if self.editor.toPlainText().strip():
            self._set_status("目前仍有草稿；請先保存或清空，避免覆蓋未保存文字。")
            return
        self._draft_snapshot = self._snapshot
        self._draft_snapshot_identity = current_identity
        self._draft_revision_of = note.revision_id
        self._draft_source_missing = False
        self._updating_editor = True
        self.editor.setPlainText(note.text)
        self._updating_editor = False
        self._set_status(
            f"已建立修訂草稿，原文仍在唯讀區；保存會追加新 revision，沿用資料日 {note.data_date}。"
        )
        self._update_controls()

    def _save_current_draft(self) -> None:
        if self.is_busy() or self._shutdown:
            return
        text = self.editor.toPlainText()
        if not text.strip():
            self._set_status("請輸入研究筆記內容。")
            return
        if len(text) > _MAX_NOTE_LENGTH:
            self._set_status(f"筆記超過 {_MAX_NOTE_LENGTH} 字，尚未保存。")
            return
        snapshot = self._draft_snapshot
        if snapshot is None or not _snapshot_is_saveable(snapshot):
            if self._draft_source_missing:
                self._set_status("草稿建立時沒有已載入來源；清空後在明確來源下重新輸入。")
            else:
                self._set_status("沒有可驗證的原題材快照；尚未保存。")
            return
        snapshot_identity = _snapshot_identity(snapshot)
        if snapshot_identity != self._draft_snapshot_identity:
            self._set_status("草稿來源身份不一致；拒絕改綁或保存。")
            return
        revision_id = str(uuid4())
        revision_of = self._draft_revision_of
        job = {
            "kind": "save",
            "snapshot": snapshot,
            "snapshot_identity": snapshot_identity,
            "data_date": _snapshot_data_date(snapshot),
            "text": text,
            "revision_id": revision_id,
            "revision_of": revision_of,
        }
        self._set_status(f"正在追加筆記至原來源 {snapshot_identity}…")
        self._start_worker(
            "save",
            self._service.save,
            snapshot,
            text,
            revision_id=revision_id,
            revision_of=revision_of,
            job=job,
        )

    def _start_worker(
        self,
        kind: str,
        function: Any,
        *args: Any,
        job: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if self._shutdown or self.is_busy():
            return
        worker_type = _ThemeResearchNoteSaveWorker if kind == "save" else TaskWorker
        worker = worker_type(function, *args, **kwargs)
        self._active_worker = worker
        self._active_job = job or {"kind": kind}
        self._active_outcome = None
        self._active_native_finished = False
        self._workers[id(worker)] = worker
        worker.finished.connect(self._on_worker_result)
        worker.error.connect(self._on_worker_error)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.native_thread_finished.connect(self._on_worker_native_finished)
        self._update_controls()
        try:
            worker.start()
        except Exception as exc:  # noqa: BLE001 - 介面邊界
            self._workers.pop(id(worker), None)
            self._active_worker = None
            self._active_job = None
            worker.deleteLater()
            self._set_status(_friendly_error(kind, str(exc)))
            self._update_controls()

    def _on_worker_result(self, result: Any) -> None:
        if self._active_outcome is None:
            self._active_outcome = ("result", result)
        self._complete_worker_if_ready()

    def _on_worker_error(self, error: str) -> None:
        if self._active_outcome is None:
            self._active_outcome = ("error", error)
        self._complete_worker_if_ready()

    def _on_worker_cancelled(self) -> None:
        if self._active_outcome is None:
            self._active_outcome = ("cancelled", None)
        self._complete_worker_if_ready()

    def _on_worker_native_finished(self) -> None:
        self._active_native_finished = True
        self._complete_worker_if_ready()

    def _complete_worker_if_ready(self) -> None:
        worker = self._active_worker
        job = self._active_job
        outcome = self._active_outcome
        if worker is None or job is None or outcome is None or not self._active_native_finished:
            return
        self._workers.pop(id(worker), None)
        self._active_worker = None
        self._active_job = None
        self._active_outcome = None
        self._active_native_finished = False
        worker.deleteLater()
        self._update_controls()

        kind = str(job.get("kind", ""))
        outcome_kind, value = outcome
        if outcome_kind == "result":
            self._apply_worker_result(kind, value, job)
        elif outcome_kind == "error":
            if kind == "save":
                failure = _friendly_error(kind, str(value))
                if self._shutdown:
                    self._set_status(
                        f"{failure} 關閉期間沒有重試；重開後請刷新清單確認保存結果。"
                    )
                else:
                    self._post_refresh_status = (
                        f"{failure} 請核對修訂清單是否出現新修訂。"
                    )
                    self._refresh_requested = True
            else:
                self._set_status_after_refresh_failure(_friendly_error(kind, str(value)))
        else:
            if kind == "save":
                if self._shutdown:
                    self._set_status(
                        "關閉期間保存結果仍未知；重開後請刷新清單確認，原筆記不會被覆寫。"
                    )
                else:
                    self._post_refresh_status = (
                        "保存結果未知；請核對修訂清單是否出現新修訂。"
                        "原筆記不會被覆寫。"
                    )
                    self._refresh_requested = True
            else:
                self._set_status_after_refresh_failure("讀取未完成；沒有執行筆記寫入。")

        if self._refresh_requested and not self._shutdown:
            self._refresh_requested = False
            self.refresh_notes()

    def _apply_worker_result(self, kind: str, value: Any, job: dict[str, Any]) -> None:
        if kind == "list":
            self._apply_note_list(value)
            return
        if kind == "read":
            if not isinstance(value, ThemeResearchNote) or value.revision_id != job.get("revision_id"):
                self._set_status("讀回修訂身份不符；沒有把內容套用到畫面。")
                return
            self._loaded_note = value
            self.saved_text.setPlainText(value.text)
            self._set_status(
                f"已讀取唯讀修訂 {value.revision_id}｜資料日 {value.data_date}｜"
                f"保存時間 {_note_recorded_at(value)}｜"
                f"原來源 SHA-256 {value.snapshot_identity_sha256}。"
            )
            self._update_controls()
            return
        if kind == "save":
            if not _matches_save_result(value, job):
                message = (
                    "保存回傳與送出時的來源或文字不符；結果未套用。"
                    "正在刷新修訂清單，請核對原來源。"
                )
                if self._shutdown:
                    self._set_status(
                        "關閉期間保存回傳的身份不符；結果仍未確認，重開後請刷新清單。"
                    )
                else:
                    self._post_refresh_status = message
                    self._refresh_requested = True
                return
            self._loaded_note = value
            self.saved_text.setPlainText(value.text)
            self._select_after_refresh = value.revision_id
            current_identity = _snapshot_identity(self._snapshot)
            if current_identity == value.snapshot_identity_sha256:
                message = (
                    f"已保存修訂 {value.revision_id}｜資料日 {value.data_date}｜"
                    f"保存時間 {_note_recorded_at(value)}｜"
                    f"來源 SHA-256 {value.snapshot_identity_sha256}。"
                )
            else:
                message = (
                    f"已保存到原來源 {value.snapshot_identity_sha256}（資料日 {value.data_date}）；"
                    f"保存時間 {_note_recorded_at(value)}；目前畫面已切換，筆記沒有改綁新來源。"
                )
            if self._shutdown:
                self._set_status(f"{message} 保存結果已確認。")
            else:
                self._post_refresh_status = message
            if (
                self.editor.toPlainText() == job.get("text")
                and self._draft_snapshot_identity == job.get("snapshot_identity")
            ):
                self._updating_editor = True
                self.editor.clear()
                self._updating_editor = False
                self._reset_draft_binding()
            self._refresh_requested = not self._shutdown
            return
        self._set_status("背景工作回傳了未識別的結果；請重新整理後再讀取。")

    def _apply_note_list(self, value: Any) -> None:
        self._clear_comparison()
        if not isinstance(value, tuple) or any(not isinstance(item, ThemeResearchNote) for item in value):
            self._set_note_list_issue("筆記清單格式無法核對；既有內容沒有清除。")
            return
        notes: dict[str, ThemeResearchNote] = {}
        for note in value:
            if not note.revision_id or note.revision_id in notes:
                self._set_note_list_issue("筆記清單含重複或空白修訂身份；拒絕猜選。")
                return
            notes[note.revision_id] = note

        selected_before = self._selected_revision_id()
        wanted = self._select_after_refresh or selected_before
        self._select_after_refresh = None
        self._notes_by_id = notes
        self._updating_revisions = True
        self.revisions.clear()
        for note in value:
            label = f"{note.data_date}｜{note.revision_id[:12]}"
            if note.revision_of:
                label += "｜修訂"
            self.revisions.addItem(label, note.revision_id)
            self.revisions.setItemData(
                self.revisions.count() - 1,
                note.revision_id,
                Qt.ItemDataRole.UserRole,
            )
        selected_index = self.revisions.findData(wanted, Qt.ItemDataRole.UserRole) if wanted else -1
        self.revisions.setCurrentIndex(selected_index)
        self._updating_revisions = False
        if self._loaded_note is not None and self._loaded_note.revision_id != wanted:
            self._loaded_note = None
            self.saved_text.clear()
        if self._post_refresh_status is not None:
            self._set_status(f"{self._post_refresh_status}（修訂清單已刷新）")
            self._post_refresh_status = None
        else:
            self._set_status(f"已載入 {len(value)} 筆保存修訂；選擇後按讀取查看唯讀原文。")
        self._update_controls()

    def _selected_revision_id(self) -> str | None:
        value = self.revisions.currentData(Qt.ItemDataRole.UserRole)
        return value if isinstance(value, str) and value else None

    def _reset_draft_binding(self) -> None:
        self._draft_snapshot = None
        self._draft_snapshot_identity = None
        self._draft_revision_of = None
        self._draft_source_missing = False

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _set_status_after_refresh_failure(self, text: str) -> None:
        if self._post_refresh_status is None:
            self._set_status(text)
            return
        self._set_status(f"{self._post_refresh_status}；{text}")
        self._post_refresh_status = None

    def _set_note_list_issue(self, text: str) -> None:
        self._clear_comparison()
        self._set_status_after_refresh_failure(text)

    def _update_controls(self) -> None:
        busy = self.is_busy()
        selected_id = self._selected_revision_id() if hasattr(self, "revisions") else None
        selected_note = self._notes_by_id.get(selected_id or "")
        editor_text = self.editor.toPlainText() if hasattr(self, "editor") else ""
        draft_is_saveable = (
            self._draft_snapshot is not None
            and _snapshot_is_saveable(self._draft_snapshot)
            and _snapshot_identity(self._draft_snapshot) == self._draft_snapshot_identity
            and bool(editor_text.strip())
            and len(editor_text) <= _MAX_NOTE_LENGTH
        )
        self.editor.setReadOnly(
            self._shutdown
            or (
                busy
                and self._active_job is not None
                and self._active_job.get("kind") == "save"
            )
        )
        self.save_button.setEnabled(not self._shutdown and not busy and draft_is_saveable)
        self.save_button.setText("保存修訂" if self._draft_revision_of else "保存新筆記")
        self.read_button.setEnabled(not self._shutdown and not busy and selected_note is not None)
        self.open_source_button.setEnabled(not self._shutdown and selected_note is not None)
        can_revise = (
            not self._shutdown
            and not busy
            and selected_note is not None
            and self._loaded_note is not None
            and self._loaded_note.revision_id == selected_note.revision_id
            and self._snapshot is not None
            and _snapshot_identity(self._snapshot) == selected_note.snapshot_identity_sha256
            and not editor_text.strip()
        )
        self.revise_button.setEnabled(can_revise)
        self.revisions.setEnabled(not self._shutdown and not busy and bool(self._notes_by_id))
        can_compare = (
            not self._shutdown
            and not busy
            and self._comparison_pair() is not None
        )
        self.compare_previous_button.setEnabled(can_compare)
        if not can_compare:
            self._clear_comparison()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt覆寫
        self.shutdown()
        super().closeEvent(event)


def _snapshot_identity(snapshot: ThemeResearchSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    identity = getattr(snapshot, "identity_sha256", None)
    return identity if isinstance(identity, str) and _SHA256_RE.fullmatch(identity) else None


def _snapshot_data_date(snapshot: ThemeResearchSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    report = getattr(snapshot, "report", None)
    value = getattr(report, "data_date", None)
    return value.isoformat() if type(value) is date else None


def _note_recorded_at(note: ThemeResearchNote) -> str:
    value = getattr(note, "recorded_at", "")
    return value if isinstance(value, str) and value else "未知"


def _comparison_identity(label: str, note: ThemeResearchNote) -> str:
    short_identity = f"{note.snapshot_identity_sha256[:16]}…"
    return (
        f"{label}｜修訂 ID：{note.revision_id}\n"
        f"資料日：{note.data_date}｜實際保存時間：{_note_recorded_at(note)}\n"
        f"來源 SHA-256：{short_identity}"
    )


def _comparison_identity_tooltip(label: str, note: ThemeResearchNote) -> str:
    return (
        f"{label}｜修訂 ID：{note.revision_id}\n"
        f"資料日：{note.data_date}｜實際保存時間：{_note_recorded_at(note)}\n"
        f"完整來源 SHA-256：{note.snapshot_identity_sha256}"
    )


def _snapshot_is_saveable(snapshot: ThemeResearchSnapshot | None) -> bool:
    if snapshot is None or _snapshot_identity(snapshot) is None or _snapshot_data_date(snapshot) is None:
        return False
    report = getattr(snapshot, "report", None)
    return (
        getattr(report, "status", None) == "current_research"
        and getattr(report, "historical_pit_eligible", None) is False
        and bool(getattr(snapshot, "mapping", ()))
    )


def _matches_save_result(value: Any, job: dict[str, Any]) -> bool:
    return (
        isinstance(value, ThemeResearchNote)
        and value.revision_id == job.get("revision_id")
        and value.snapshot_identity_sha256 == job.get("snapshot_identity")
        and value.data_date == job.get("data_date")
        and value.text == job.get("text")
        and value.revision_of == job.get("revision_of")
    )


def _friendly_error(kind: str, raw_error: str) -> str:
    detail = raw_error.splitlines()[0].casefold()
    if "another theme snapshot" in detail or "snapshot" in detail and "source" in detail:
        reason = "修訂來源與明選快照不一致"
    elif "revision_id" in detail or "journal revision identity" in detail:
        reason = "修訂身份已存在且內容不同，未覆寫原文"
    elif "historical_pit_eligible" in detail or "current_research" in detail:
        reason = "題材版本不符合保存條件"
    elif "text" in detail or "character" in detail:
        reason = "筆記內容無效或超出長度限制"
    else:
        reason = "背景作業失敗；請刷新清單核對既有筆記"
    return f"{('保存' if kind == 'save' else '讀取')}未完成：{reason}。原保存修訂不會被覆寫。"
