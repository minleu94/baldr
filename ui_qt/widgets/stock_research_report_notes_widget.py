"""個股報告判斷筆記；保存與讀回均走既有 Journal service 的背景任務。"""

from __future__ import annotations

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

from app_module.stock_research_report_dtos import StockResearchReportDTO
from app_module.stock_research_report_notes import (
    StockResearchReportNote,
    StockResearchReportNoteService,
)
from app_module.stock_research_report_snapshot_codec import (
    StockResearchReportSnapshotCodecError,
    StockResearchReportProjectionSnapshot,
    read_stock_research_report_projection_snapshot,
)
from ui_qt.workers.task_worker import TaskWorker


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_NOTE_LENGTH = 8000


class _StockResearchReportNoteSaveWorker(TaskWorker):
    """已送出的筆記保存不能被全域關閉取消旗標藏掉結果。"""

    def cancel(self, cooperative: bool = True, wait: bool = False) -> None:
        return None


class StockResearchReportNotesWidget(QWidget):
    """保存綁定當時個股報告投影的研究判斷與直接修訂。"""

    openSnapshotRequested = Signal(object)

    def __init__(
        self,
        service: StockResearchReportNoteService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._service = service
        self._snapshot: StockResearchReportProjectionSnapshot | None = None
        self._stock_code = ""
        self._snapshot_generation = 0
        self._draft_snapshot: StockResearchReportProjectionSnapshot | None = None
        self._draft_snapshot_identity: str | None = None
        self._draft_revision_of: str | None = None
        self._draft_source_missing = False
        self._updating_editor = False
        self._updating_revisions = False
        self._loaded_note: StockResearchReportNote | None = None
        self._notes_by_id: dict[str, StockResearchReportNote] = {}
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
        self.open_report_button.clicked.connect(self._open_selected_report)
        self.compare_previous_button.clicked.connect(self._compare_with_previous)
        self.refresh_button.clicked.connect(self.refresh_notes)
        # 初次建立畫面不讀私人 Journal；等明確開頁、查詢或刷新才讀取。
        self._update_controls()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        heading = QLabel(
            "我的判斷｜保存當時畫面上的報告副本與個人文字，供日後查閱。"
            "這不代表上游來源已獲認可，也不授予歷史 PIT 資格、績效或交易效力。"
        )
        heading.setWordWrap(True)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(heading)

        self.source_label = QLabel("目前沒有已載入報告；可讀取既有保存筆記。")
        self.source_label.setWordWrap(True)
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.source_label)

        selection_row = QHBoxLayout()
        self.revisions = QComboBox()
        self.revisions.setObjectName("stockResearchReportNoteRevisions")
        selection_row.addWidget(self.revisions, 1)
        self.refresh_button = QPushButton("刷新筆記")
        self.refresh_button.setObjectName("stockResearchReportNoteRefresh")
        selection_row.addWidget(self.refresh_button)
        layout.addLayout(selection_row)

        note_actions = QHBoxLayout()
        self.read_button = QPushButton("讀取所選判斷")
        self.read_button.setObjectName("stockResearchReportNoteRead")
        self.open_report_button = QPushButton("開啟保存時報告")
        self.open_report_button.setObjectName("stockResearchReportNoteOpenReport")
        self.revise_button = QPushButton("以此判斷另存修訂")
        self.revise_button.setObjectName("stockResearchReportNoteRevise")
        note_actions.addWidget(self.read_button)
        note_actions.addWidget(self.open_report_button)
        note_actions.addWidget(self.revise_button)
        layout.addLayout(note_actions)

        compare_row = QHBoxLayout()
        self.compare_previous_button = QPushButton("與直接前版比較")
        self.compare_previous_button.setObjectName(
            "stockResearchReportNoteComparePrevious"
        )
        compare_row.addWidget(self.compare_previous_button)
        compare_row.addStretch(1)
        layout.addLayout(compare_row)

        self._build_comparison_dialog()

        saved_label = QLabel("明選判斷的保存原文（唯讀）")
        saved_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(saved_label)
        self.saved_text = QPlainTextEdit()
        self.saved_text.setObjectName("stockResearchReportNoteSavedText")
        self.saved_text.setReadOnly(True)
        self.saved_text.setPlaceholderText("明選一筆判斷並按「讀取所選判斷」查看原文。")
        self.saved_text.setMinimumHeight(72)
        self.saved_text.setMaximumHeight(132)
        layout.addWidget(self.saved_text)

        draft_label = QLabel("我的判斷（最多 8,000 字；保存後另存修訂，不覆寫原文）")
        draft_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(draft_label)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("stockResearchReportNoteEditor")
        self.editor.setPlaceholderText(
            "輸入自己的研究判斷。開始輸入時會固定當下報告副本；"
            "切換股票或報告不會改綁既有草稿。"
        )
        self.editor.setMinimumHeight(78)
        self.editor.setMaximumHeight(150)
        layout.addWidget(self.editor)

        action_row = QHBoxLayout()
        self.save_button = QPushButton("保存此份報告與判斷")
        self.save_button.setObjectName("stockResearchReportNoteSave")
        action_row.addWidget(self.save_button)
        layout.addLayout(action_row)

        self.status_label = QLabel("正在讀取已保存筆記…")
        self.status_label.setObjectName("stockResearchReportNoteStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status_label)
        self._update_controls()

    def _build_comparison_dialog(self) -> None:
        self.compare_dialog = QDialog(self, Qt.WindowType.Window)
        self.compare_dialog.setObjectName("stockResearchReportNoteComparisonDialog")
        self.compare_dialog.setWindowTitle("個股報告判斷｜與直接前版比較")
        self.compare_dialog.resize(800, 520)
        dialog_layout = QVBoxLayout(self.compare_dialog)

        explanation = QLabel(
            "以下並列同一份保存報告副本的直接父版與目前修訂原文；"
            "比較不代表上游來源資格、歷史 PIT 或績效。"
        )
        explanation.setWordWrap(True)
        explanation.setTextFormat(Qt.TextFormat.PlainText)
        dialog_layout.addWidget(explanation)

        columns = QHBoxLayout()
        previous_column = QVBoxLayout()
        self.comparison_previous_identity = QLabel("直接前版：尚未載入")
        self.comparison_previous_identity.setObjectName(
            "stockResearchReportNotePreviousIdentity"
        )
        self.comparison_previous_identity.setWordWrap(True)
        self.comparison_previous_identity.setTextFormat(Qt.TextFormat.PlainText)
        previous_column.addWidget(self.comparison_previous_identity)
        self.comparison_previous_text = QPlainTextEdit()
        self.comparison_previous_text.setObjectName(
            "stockResearchReportNotePreviousText"
        )
        self.comparison_previous_text.setReadOnly(True)
        self.comparison_previous_text.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
        )
        previous_column.addWidget(self.comparison_previous_text, 1)
        columns.addLayout(previous_column, 1)

        selected_column = QVBoxLayout()
        self.comparison_selected_identity = QLabel("目前修訂：尚未載入")
        self.comparison_selected_identity.setObjectName(
            "stockResearchReportNoteSelectedIdentity"
        )
        self.comparison_selected_identity.setWordWrap(True)
        self.comparison_selected_identity.setTextFormat(Qt.TextFormat.PlainText)
        selected_column.addWidget(self.comparison_selected_identity)
        self.comparison_selected_text = QPlainTextEdit()
        self.comparison_selected_text.setObjectName(
            "stockResearchReportNoteSelectedText"
        )
        self.comparison_selected_text.setReadOnly(True)
        self.comparison_selected_text.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
        )
        selected_column.addWidget(self.comparison_selected_text, 1)
        columns.addLayout(selected_column, 1)
        dialog_layout.addLayout(columns, 1)
        self._clear_comparison(close_dialog=False)

    def set_snapshot(
        self,
        snapshot: StockResearchReportProjectionSnapshot | None,
        *,
        stock_code: str = "",
    ) -> None:
        """切換目前畫面報告，不改綁已開始輸入或保存的判斷。"""

        if snapshot is not None and type(snapshot) is not StockResearchReportProjectionSnapshot:
            raise TypeError("snapshot must be StockResearchReportProjectionSnapshot or None")
        if snapshot is not None:
            snapshot = _decode_trusted_snapshot(snapshot)
        if not isinstance(stock_code, str):
            raise TypeError("stock_code must be str")
        requested_stock = stock_code.strip()
        if snapshot is not None:
            if requested_stock and requested_stock != snapshot.stock_code:
                raise ValueError("stock_code does not match snapshot stock_code")
            requested_stock = snapshot.stock_code

        previous_identity = _snapshot_identity(self._snapshot)
        current_identity = _snapshot_identity(snapshot)
        previous_stock = self._stock_code
        self._snapshot = snapshot
        self._stock_code = requested_stock
        if previous_identity != current_identity or previous_stock != requested_stock:
            self._snapshot_generation += 1
            self._clear_comparison()
            self._loaded_note = None
            self.saved_text.clear()

        if snapshot is None:
            if requested_stock:
                self.source_label.setText(
                    f"目前沒有載入報告｜筆記篩選股票：{requested_stock}；仍可讀取已保存筆記。"
                )
            else:
                self.source_label.setText("目前沒有已載入報告；可讀取所有已保存筆記。")
            self.source_label.setToolTip("")
        else:
            report = snapshot.report
            identity = current_identity or "來源身份無效"
            self.source_label.setText(
                f"目前報告副本｜{snapshot.stock_code} {report.stock_name or '名稱未提供'}｜"
                f"查詢截至：{_display(report.as_of)}｜"
                f"原報告產生時間：{_display(report.generated_at)}｜"
                f"來源 SHA-256：{identity[:16]}…"
            )
            self.source_label.setToolTip(
                "當時畫面報告副本；不代表上游來源已獲認可或具歷史 PIT 資格。\n"
                f"完整報告身份 SHA-256：{identity}\n"
                f"筆記篩選股票：{requested_stock}"
            )

        if previous_stock != requested_stock:
            self._refresh_requested = True
            if not self.is_busy() and not self._shutdown:
                self._refresh_requested = False
                self.refresh_notes()
        job = self._active_job
        if job is not None and job.get("kind") == "save":
            if current_identity != job.get("snapshot_identity"):
                self._set_status(
                    "報告已切換；正在保存的判斷仍綁定輸入時的原報告副本，沒有改綁。"
                )
        elif self._draft_snapshot is not None:
            if current_identity != self._draft_snapshot_identity:
                self._set_status(
                    f"草稿仍綁定原報告身份 {self._draft_snapshot_identity}；切換不會改綁。"
                )
            else:
                self._set_status("草稿已綁定目前報告副本；保存會保留此份報告與原文。")
        elif self._draft_source_missing and self.editor.toPlainText().strip():
            self._set_status(
                "此草稿輸入時沒有已載入報告，不能自動綁到新報告；清空後重新輸入。"
            )
        elif current_identity is not None:
            self._set_status("新判斷會綁定目前報告副本；既有筆記保留各自保存時的報告。")
        elif previous_identity != current_identity:
            self._set_status("目前沒有可保存的新報告；已保存筆記仍可明選讀取。")
        self._update_controls()

    def refresh_notes(self) -> None:
        """在背景刷新筆記清單；不自動選取任何修訂。"""

        self._clear_comparison()
        if self._shutdown:
            return
        if self.is_busy():
            self._refresh_requested = True
            return
        self._set_status("正在讀取已保存判斷清單…")
        self._start_worker(
            "list",
            self._service.list_notes,
            stock_code=self._stock_code,
            job={"kind": "list", "stock_code": self._stock_code},
        )

    def is_busy(self) -> bool:
        return self._active_worker is not None

    def shutdown(self) -> None:
        """合作取消背景讀取，但保護已送出的追加保存。"""

        if self._shutdown:
            return
        self._shutdown = True
        self._clear_comparison()
        worker = self._active_worker
        job = self._active_job
        if worker is not None and job is not None:
            if job.get("kind") == "save":
                self._set_status(
                    "保存已送出，關閉時不會強制中止；結果確認前請在重開後刷新筆記。"
                )
            else:
                worker.cancel(cooperative=True, wait=False)
                self._set_status("已要求停止背景讀取；清單或內容不會寫入。")
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
        self._read_or_open_selected("read")

    def _open_selected_report(self) -> None:
        self._read_or_open_selected("open")

    def _read_or_open_selected(self, kind: str) -> None:
        if self.is_busy() or self._shutdown:
            return
        revision_id = self._selected_revision_id()
        note = self._notes_by_id.get(revision_id or "")
        if note is None:
            self._set_status("請先明選一筆已保存判斷。")
            return
        action = "重新讀取保存時報告" if kind == "open" else "讀取指定判斷"
        self._set_status(f"正在背景{action} {revision_id}…")
        self._start_worker(
            kind,
            self._service.get_note,
            revision_id,
            job={
                "kind": kind,
                "revision_id": revision_id,
                "expected_note": note,
                "stock_code": self._stock_code,
                "generation": self._snapshot_generation,
            },
        )

    def _compare_with_previous(self) -> None:
        if self.is_busy() or self._shutdown:
            self._clear_comparison()
            self._update_controls()
            return
        pair = self._comparison_pair()
        if pair is None:
            self._clear_comparison()
            self._set_status("所選修訂沒有可核對的同報告副本直接前版。")
            self._update_controls()
            return
        previous, selected = pair
        self.comparison_previous_identity.setText(
            _comparison_identity("直接前版", previous)
        )
        self.comparison_previous_identity.setToolTip(
            _comparison_identity_tooltip("直接前版", previous)
        )
        self.comparison_selected_identity.setText(
            _comparison_identity("目前修訂", selected)
        )
        self.comparison_selected_identity.setToolTip(
            _comparison_identity_tooltip("目前修訂", selected)
        )
        self.comparison_previous_text.setPlainText(previous.text)
        self.comparison_selected_text.setPlainText(selected.text)
        self.compare_dialog.show()
        self.compare_dialog.raise_()
        self.compare_dialog.activateWindow()

    def _comparison_pair(
        self,
    ) -> tuple[StockResearchReportNote, StockResearchReportNote] | None:
        selected_id = self._selected_revision_id()
        selected = self._notes_by_id.get(selected_id or "")
        if type(selected) is not StockResearchReportNote:
            return None
        previous_id = selected.revision_of
        if (
            not isinstance(previous_id, str)
            or not previous_id
            or previous_id == selected.revision_id
        ):
            return None
        previous = self._notes_by_id.get(previous_id)
        if type(previous) is not StockResearchReportNote:
            return None
        if not _notes_share_snapshot(previous, selected):
            return None
        return previous, selected

    def _clear_comparison(self, *, close_dialog: bool = True) -> None:
        if hasattr(self, "comparison_previous_text"):
            self.comparison_previous_text.clear()
            self.comparison_selected_text.clear()
            self.comparison_previous_identity.setText("直接前版：尚未載入")
            self.comparison_selected_identity.setText("目前修訂：尚未載入")
            self.comparison_previous_identity.setToolTip("")
            self.comparison_selected_identity.setToolTip("")
        dialog = getattr(self, "compare_dialog", None)
        if close_dialog and dialog is not None and dialog.isVisible():
            dialog.close()

    def _prepare_revision(self) -> None:
        selected_id = self._selected_revision_id()
        note = self._loaded_note
        if note is None or note.revision_id != selected_id:
            self._set_status("請先讀取所選判斷；唯讀原文載入後才能另存修訂。")
            return
        try:
            revision_snapshot = _decode_trusted_snapshot(note.snapshot)
        except (TypeError, ValueError):
            self._set_status("保存筆記中的報告副本身份無法核對，不能建立修訂草稿。")
            return
        if self.editor.toPlainText().strip():
            self._set_status("目前仍有草稿；請先保存或清空，避免覆蓋未保存文字。")
            return
        self._draft_snapshot = revision_snapshot
        self._draft_snapshot_identity = revision_snapshot.identity_sha256
        self._draft_revision_of = note.revision_id
        self._draft_source_missing = False
        self._updating_editor = True
        self.editor.setPlainText(note.text)
        self._updating_editor = False
        self._set_status(
            f"已建立直接修訂草稿，沿用明選筆記保存時的報告副本；"
            f"{_note_report_times(revision_snapshot)}｜"
            f"SHA-256：{revision_snapshot.identity_sha256}。"
            "目前畫面報告不會替修訂改綁。"
        )
        self._update_controls()

    def _save_current_draft(self) -> None:
        if self.is_busy() or self._shutdown:
            return
        text = self.editor.toPlainText()
        if not text.strip():
            self._set_status("請輸入我的判斷。")
            return
        if len(text) > _MAX_NOTE_LENGTH:
            self._set_status(f"判斷超過 {_MAX_NOTE_LENGTH} 字，尚未保存。")
            return
        snapshot = self._draft_snapshot
        if snapshot is None or not _snapshot_is_saveable(snapshot):
            if self._draft_source_missing:
                self._set_status("草稿開始時沒有已載入報告；請清空後在報告明確載入時重新輸入。")
            else:
                self._set_status("沒有可驗證的報告副本；尚未保存。")
            return
        identity = _snapshot_identity(snapshot)
        if identity != self._draft_snapshot_identity:
            self._set_status("草稿報告身份不一致；拒絕改綁或保存。")
            return
        revision_id = str(uuid4())
        revision_of = self._draft_revision_of
        job = {
            "kind": "save",
            "snapshot": snapshot,
            "snapshot_identity": identity,
            "stock_code": snapshot.stock_code,
            "as_of": snapshot.report.as_of,
            "generated_at": snapshot.report.generated_at,
            "text": text,
            "revision_id": revision_id,
            "revision_of": revision_of,
        }
        self._set_status("正在保存此份報告與判斷；原有筆記不會被覆寫…")
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
        worker_type = _StockResearchReportNoteSaveWorker if kind == "save" else TaskWorker
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
        except Exception as exc:
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
        elif kind == "save":
            if outcome_kind == "error":
                failure = _friendly_error(kind, str(value))
                if self._shutdown:
                    self._set_status(f"{failure} 重開後請刷新筆記清單確認保存狀態。")
                else:
                    self._post_refresh_status = f"{failure} 請核對修訂清單。"
                    self._refresh_requested = True
            else:
                if self._shutdown:
                    self._set_status("關閉期間保存結果未知；重開後請刷新清單確認，原筆記不會被覆寫。")
                else:
                    self._post_refresh_status = "保存結果未知；請核對清單，原筆記不會被覆寫。"
                    self._refresh_requested = True
        elif kind == "list" and job.get("stock_code") == self._stock_code:
            if outcome_kind == "error":
                self._set_status_after_refresh_failure(_friendly_error(kind, str(value)))
            else:
                self._set_status_after_refresh_failure("筆記清單讀取未完成；沒有執行筆記寫入。")
        elif self._job_is_current(job):
            if outcome_kind == "error":
                self._set_status_after_refresh_failure(_friendly_error(kind, str(value)))
            else:
                self._set_status_after_refresh_failure("背景讀取未完成；沒有執行筆記寫入。")

        if self._refresh_requested and not self._shutdown:
            self._refresh_requested = False
            self.refresh_notes()

    def _apply_worker_result(self, kind: str, value: Any, job: dict[str, Any]) -> None:
        if kind == "list":
            if job.get("stock_code") != self._stock_code:
                self._refresh_requested = True
                return
            self._apply_note_list(value)
            return
        if kind in {"read", "open"}:
            if not self._job_is_current(job):
                if not self._shutdown:
                    self._set_status("股票、報告或明選判斷已改變；舊背景結果已丟棄。")
                return
            expected = job.get("expected_note")
            if not _matches_fresh_note(value, expected):
                self._set_status("讀回筆記身份或報告副本不符；沒有套用或開啟。")
                self._update_controls()
                return
            if kind == "read":
                self._loaded_note = value
                self.saved_text.setPlainText(value.text)
                self._set_status(
                    f"已讀取判斷 {value.revision_id}｜"
                    f"{_note_report_times(value.snapshot)}｜"
                    f"實際保存時間：{_note_recorded_at(value)}｜"
                    f"報告 SHA-256：{value.snapshot.identity_sha256}。"
                )
                self._update_controls()
                return
            self.openSnapshotRequested.emit(value.snapshot)
            self._set_status(
                f"已重新讀取保存時報告副本 {value.revision_id}｜"
                f"{_note_report_times(value.snapshot)}｜"
                f"實際保存時間：{_note_recorded_at(value)}。"
            )
            self._update_controls()
            return
        if kind == "save":
            if not _matches_save_result(value, job):
                message = "保存回傳與送出時的報告身份或原文不符；正在刷新筆記清單核對。"
                if self._shutdown:
                    self._set_status("保存回傳身份不符；重開後請刷新清單確認，結果未套用。")
                else:
                    self._post_refresh_status = message
                    self._refresh_requested = True
                return
            if (
                self.editor.toPlainText() == job.get("text")
                and self._draft_snapshot_identity == job.get("snapshot_identity")
                and self._draft_revision_of == job.get("revision_of")
            ):
                self._updating_editor = True
                self.editor.clear()
                self._updating_editor = False
                self._reset_draft_binding()
            current_identity = _snapshot_identity(self._snapshot)
            if current_identity == value.snapshot.identity_sha256:
                message = (
                    f"已保存判斷 {value.revision_id}｜{_note_report_times(value.snapshot)}｜"
                    f"實際保存時間：{_note_recorded_at(value)}｜"
                    f"報告 SHA-256：{value.snapshot.identity_sha256}。"
                )
            else:
                message = (
                    f"已保存到輸入時報告副本 {value.snapshot.identity_sha256}｜"
                    f"{_note_report_times(value.snapshot)}｜實際保存時間："
                    f"{_note_recorded_at(value)}；切換後仍未改綁。"
                )
            if self._shutdown:
                self._set_status(f"{message} 保存結果已確認。")
            else:
                self._post_refresh_status = message
                self._refresh_requested = True
            return
        self._set_status("背景工作回傳未識別的結果；請刷新清單後重新讀取。")

    def _apply_note_list(self, value: Any) -> None:
        self._clear_comparison()
        if type(value) is not tuple or any(type(item) is not StockResearchReportNote for item in value):
            self._set_note_list_issue("筆記清單格式無法核對；既有內容沒有清除。")
            return
        notes: dict[str, StockResearchReportNote] = {}
        for note in value:
            if (
                not isinstance(note.revision_id, str)
                or not note.revision_id.strip()
                or note.revision_id in notes
                or not _note_is_well_formed(note)
            ):
                self._set_note_list_issue("筆記清單含無效或重複身份；拒絕猜選。")
                return
            if self._stock_code and note.snapshot.stock_code != self._stock_code:
                self._set_note_list_issue("筆記清單含篩選股票以外的內容；拒絕套用。")
                return
            notes[note.revision_id] = note

        selected_before = self._selected_revision_id()
        self._notes_by_id = notes
        self._updating_revisions = True
        self.revisions.clear()
        for note in value:
            self.revisions.addItem(_note_label(note), note.revision_id)
            self.revisions.setItemData(
                self.revisions.count() - 1,
                note.revision_id,
                Qt.ItemDataRole.UserRole,
            )
        selected_index = (
            self.revisions.findData(selected_before, Qt.ItemDataRole.UserRole)
            if selected_before
            else -1
        )
        self.revisions.setCurrentIndex(selected_index)
        self._updating_revisions = False
        selected_after = self._selected_revision_id()
        if self._loaded_note is not None and self._loaded_note.revision_id != selected_after:
            self._loaded_note = None
            self.saved_text.clear()
        if self._post_refresh_status is not None:
            self._set_status(f"{self._post_refresh_status}（筆記清單已刷新）")
            self._post_refresh_status = None
        else:
            self._set_status(
                f"已載入 {len(value)} 筆保存判斷；請明選修訂後讀取或開啟其報告副本。"
            )
        self._update_controls()

    def _job_is_current(self, job: dict[str, Any]) -> bool:
        return (
            job.get("generation") == self._snapshot_generation
            and job.get("stock_code") == self._stock_code
            and job.get("revision_id") == self._selected_revision_id()
        )

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
        self.revisions.setEnabled(not self._shutdown and not busy and bool(self._notes_by_id))
        self.refresh_button.setEnabled(not self._shutdown and not busy)
        self.read_button.setEnabled(
            not self._shutdown and not busy and selected_note is not None
        )
        self.open_report_button.setEnabled(
            not self._shutdown and not busy and selected_note is not None
        )
        can_revise = (
            not self._shutdown
            and not busy
            and selected_note is not None
            and self._loaded_note is not None
            and self._loaded_note.revision_id == selected_note.revision_id
            and not editor_text.strip()
        )
        self.revise_button.setEnabled(can_revise)
        can_compare = not self._shutdown and not busy and self._comparison_pair() is not None
        self.compare_previous_button.setEnabled(can_compare)
        if not can_compare:
            self._clear_comparison()

    def closeEvent(self, event: Any) -> None:
        self.shutdown()
        super().closeEvent(event)


def _snapshot_identity(
    snapshot: StockResearchReportProjectionSnapshot | None,
) -> str | None:
    if snapshot is None:
        return None
    value = getattr(snapshot, "identity_sha256", None)
    return value if isinstance(value, str) and _SHA256_RE.fullmatch(value) else None


def _decode_trusted_snapshot(
    snapshot: StockResearchReportProjectionSnapshot,
) -> StockResearchReportProjectionSnapshot:
    if type(snapshot) is not StockResearchReportProjectionSnapshot:
        raise TypeError("snapshot must be StockResearchReportProjectionSnapshot")
    try:
        decoded = read_stock_research_report_projection_snapshot(
            snapshot.canonical_json,
            expected_identity_sha256=snapshot.identity_sha256,
        )
    except StockResearchReportSnapshotCodecError as exc:
        raise ValueError("snapshot canonical_json 與 SHA-256 無法核對") from exc
    if not _snapshot_is_saveable(decoded):
        raise ValueError("snapshot 解碼後報告型別或股票身份無效")
    return decoded


def _snapshot_is_saveable(
    snapshot: StockResearchReportProjectionSnapshot | None,
) -> bool:
    if type(snapshot) is not StockResearchReportProjectionSnapshot:
        return False
    report = snapshot.report
    return (
        isinstance(snapshot.stock_code, str)
        and bool(snapshot.stock_code.strip())
        and _snapshot_identity(snapshot) is not None
        and isinstance(snapshot.canonical_json, str)
        and bool(snapshot.canonical_json)
        and type(report) is StockResearchReportDTO
        and report.stock_code == snapshot.stock_code
        and report.read_only is True
    )


def _snapshot_report_as_of(snapshot: StockResearchReportProjectionSnapshot) -> str:
    return _display(snapshot.report.as_of)


def _snapshot_generated_at(snapshot: StockResearchReportProjectionSnapshot) -> str:
    return _display(snapshot.report.generated_at)


def _display(value: Any) -> str:
    return value if isinstance(value, str) and value else "未提供"


def _note_recorded_at(note: StockResearchReportNote) -> str:
    value = getattr(note, "recorded_at", "")
    return value if isinstance(value, str) and value else "未提供"


def _note_report_times(snapshot: StockResearchReportProjectionSnapshot) -> str:
    return (
        f"查詢截至：{_snapshot_report_as_of(snapshot)}｜"
        f"原報告產生時間：{_snapshot_generated_at(snapshot)}"
    )


def _note_is_well_formed(note: StockResearchReportNote) -> bool:
    return (
        type(note.snapshot) is StockResearchReportProjectionSnapshot
        and _snapshot_is_saveable(note.snapshot)
        and isinstance(note.text, str)
        and bool(note.text.strip())
        and len(note.text) <= _MAX_NOTE_LENGTH
        and isinstance(note.recorded_at, str)
        and (note.revision_of is None or isinstance(note.revision_of, str))
    )


def _matches_fresh_note(
    value: Any,
    expected: Any,
) -> bool:
    return (
        type(value) is StockResearchReportNote
        and type(expected) is StockResearchReportNote
        and _note_is_well_formed(value)
        and value.revision_id == expected.revision_id
        and value.text == expected.text
        and value.revision_of == expected.revision_of
        and value.recorded_at == expected.recorded_at
        and value.snapshot.identity_sha256 == expected.snapshot.identity_sha256
        and value.snapshot.stock_code == expected.snapshot.stock_code
        and value.snapshot.canonical_json == expected.snapshot.canonical_json
    )


def _matches_save_result(value: Any, job: dict[str, Any]) -> bool:
    return (
        type(value) is StockResearchReportNote
        and _note_is_well_formed(value)
        and value.revision_id == job.get("revision_id")
        and value.snapshot.identity_sha256 == job.get("snapshot_identity")
        and value.snapshot.stock_code == job.get("stock_code")
        and value.snapshot.report.as_of == job.get("as_of")
        and value.snapshot.report.generated_at == job.get("generated_at")
        and value.snapshot.canonical_json == job.get("snapshot").canonical_json
        and value.text == job.get("text")
        and value.revision_of == job.get("revision_of")
    )


def _notes_share_snapshot(
    previous: StockResearchReportNote,
    selected: StockResearchReportNote,
) -> bool:
    return (
        previous.revision_id != selected.revision_id
        and previous.revision_id == selected.revision_of
        and previous.snapshot.identity_sha256 == selected.snapshot.identity_sha256
        and previous.snapshot.stock_code == selected.snapshot.stock_code
        and previous.snapshot.canonical_json == selected.snapshot.canonical_json
    )


def _note_label(note: StockResearchReportNote) -> str:
    identity = note.snapshot.identity_sha256[:12]
    revision_type = "修訂" if note.revision_of else "原始判斷"
    return (
        f"{note.snapshot.stock_code}｜{_note_report_times(note.snapshot)}｜"
        f"{revision_type}｜保存 {_note_recorded_at(note)}｜{identity}…｜{note.revision_id}"
    )


def _comparison_identity(label: str, note: StockResearchReportNote) -> str:
    snapshot = note.snapshot
    return (
        f"{label}｜股票：{snapshot.stock_code}｜修訂 ID：{note.revision_id}\n"
        f"{_note_report_times(snapshot)}｜實際保存時間：{_note_recorded_at(note)}\n"
        f"報告 SHA-256：{snapshot.identity_sha256[:16]}…"
    )


def _comparison_identity_tooltip(label: str, note: StockResearchReportNote) -> str:
    snapshot = note.snapshot
    return (
        f"{label}｜股票：{snapshot.stock_code}｜修訂 ID：{note.revision_id}\n"
        f"{_note_report_times(snapshot)}｜實際保存時間：{_note_recorded_at(note)}\n"
        f"完整報告 SHA-256：{snapshot.identity_sha256}"
    )


def _friendly_error(kind: str, raw_error: str) -> str:
    detail = raw_error.splitlines()[0].casefold()
    if "revision" in detail and ("conflict" in detail or "different" in detail):
        reason = "修訂身份衝突，沒有覆寫既有原文"
    elif "snapshot" in detail or "identity" in detail or "stock_code" in detail:
        reason = "報告副本身份或股票不一致"
    elif "text" in detail or "character" in detail or "empty" in detail:
        reason = "判斷原文無效或超出長度限制"
    else:
        reason = "背景作業失敗；請刷新清單核對已保存內容"
    action = "保存" if kind == "save" else "讀取"
    return f"{action}未完成：{reason}。已保存判斷不會被覆寫。"
