"""F07 原價格版本的使用者判斷筆記；Journal 讀寫在背景執行。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
)
from app_module.pinned_stock_research_notes import (
    PinnedStockResearchNote,
    PinnedStockResearchNoteSaveReadback,
    PinnedStockResearchNoteService,
    PinnedStockResearchSource,
    verify_pinned_stock_research_source,
)
from ui_qt.workers.task_worker import TaskWorker


_MAX_NOTE_LENGTH = 8000


class _PinnedStockResearchNoteSaveWorker(TaskWorker):
    """已送出的 Journal 寫入不可由合作式關閉取消。"""

    def cancel(self, cooperative: bool = True, wait: bool = False) -> None:
        return None


class PinnedStockResearchNotesWidget(QWidget):
    """只保存使用者對 F07 原價格與技術規則版本的個人判斷。"""

    open_source_requested = Signal(object)

    def __init__(
        self,
        service: PinnedStockResearchNoteService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._service = service
        self._bookmark: DailyMarketTechnicalUniversePriceBookmarkV1 | None = None
        self._bookmark_identity: str | None = None
        self._stock_code = ""
        self._verified_source: PinnedStockResearchSource | None = None
        self._source_error = ""
        self._source_locator = ""
        self._notes_by_id: dict[str, PinnedStockResearchNote] = {}
        self._note_locators: dict[str, str] = {}
        self._loaded_note: PinnedStockResearchNote | None = None
        self._loaded_source_state: DailyMarketTechnicalUniversePriceBookmarkStateV1 | None = None
        self._loaded_source_error = ""
        self._draft_source: PinnedStockResearchSource | None = None
        self._draft_revision_of: str | None = None
        self._draft_source_missing = False
        self._updating_editor = False
        self._updating_revisions = False
        self._shutdown = False
        self._generation = 0
        self._pending_load = False
        self._post_refresh_status: str | None = None
        self._workers: dict[int, TaskWorker] = {}
        self._active_worker: TaskWorker | None = None
        self._active_job: dict[str, Any] | None = None
        self._active_outcome: tuple[str, Any] | None = None
        self._active_native_finished = False

        self._build_ui()
        self.editor.textChanged.connect(self._on_editor_changed)
        self.revisions.currentIndexChanged.connect(self._on_revision_selected)
        self.read_button.clicked.connect(self._read_selected)
        self.open_source_button.clicked.connect(self._open_selected_source)
        self.revise_button.clicked.connect(self._prepare_revision)
        self.save_button.clicked.connect(self._save_current_draft)
        self._update_controls()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        heading = QLabel(
            "我的個股判斷｜只綁定 F07 原價格與技術規則版本。"
            "這是個人筆記，不是 Advice、策略訊號、交易指示或績效證據。"
        )
        heading.setWordWrap(True)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(heading)

        self.source_label = QLabel(
            "股票：尚未選擇｜行情觀測日：未知｜原研究日：未知"
        )
        self.source_label.setObjectName("pinnedStockResearchNoteSource")
        self.source_label.setWordWrap(True)
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.source_label)

        self.revisions = QComboBox()
        self.revisions.setObjectName("pinnedStockResearchNoteRevisions")
        self.revisions.setAccessibleName("明選已保存個股判斷")
        self.revisions.setToolTip("明選同一股票的一篇筆記，再讀取原文。")
        layout.addWidget(self.revisions)

        action_row = QHBoxLayout()
        self.read_button = QPushButton("讀取所選筆記")
        self.read_button.setObjectName("pinnedStockResearchNoteRead")
        self.open_source_button = QPushButton("開啟原價格版本")
        self.open_source_button.setObjectName("pinnedStockResearchNoteOpenSource")
        self.revise_button = QPushButton("以此筆記另存修訂")
        self.revise_button.setObjectName("pinnedStockResearchNoteRevise")
        action_row.addWidget(self.read_button)
        action_row.addWidget(self.open_source_button)
        action_row.addWidget(self.revise_button)
        layout.addLayout(action_row)

        saved_label = QLabel("保存原文（唯讀）")
        saved_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(saved_label)
        self.saved_text = QPlainTextEdit()
        self.saved_text.setObjectName("pinnedStockResearchNoteSavedText")
        self.saved_text.setReadOnly(True)
        self.saved_text.setPlaceholderText("明選筆記並按「讀取所選筆記」查看原文。")
        self.saved_text.setMinimumHeight(70)
        self.saved_text.setMaximumHeight(130)
        layout.addWidget(self.saved_text)

        draft_label = QLabel("新筆記／修訂草稿（最多 8,000 字）")
        draft_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(draft_label)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("pinnedStockResearchNoteEditor")
        self.editor.setPlaceholderText("輸入自己的研究判斷；不會自動補造觀察。")
        self.editor.setMinimumHeight(78)
        self.editor.setMaximumHeight(150)
        layout.addWidget(self.editor)

        self.save_button = QPushButton("保存新筆記")
        self.save_button.setObjectName("pinnedStockResearchNoteSave")
        layout.addWidget(self.save_button)

        self.status_label = QLabel("請從 F07 明選一筆原價格版本。")
        self.status_label.setObjectName("pinnedStockResearchNoteStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status_label)

    def set_source(
        self,
        bookmark: DailyMarketTechnicalUniversePriceBookmarkV1 | None,
        *,
        stock_code: str = "",
    ) -> None:
        """切換 F07 原版本；不沿用舊筆記 selection 或 parent。"""

        if bookmark is not None and not isinstance(
            bookmark, DailyMarketTechnicalUniversePriceBookmarkV1
        ):
            raise TypeError("bookmark 必須是 DailyMarketTechnicalUniversePriceBookmarkV1 或 None")
        requested_stock = bookmark.stock_code if bookmark is not None else stock_code.strip()
        if bookmark is not None and stock_code and stock_code != bookmark.stock_code:
            bookmark = None
            requested_stock = stock_code.strip()
            input_error = "所選股票與 F07 原價格版本不符；未核對來源。"
        else:
            input_error = ""

        previous_identity = self._bookmark_identity
        next_identity = (
            bookmark.bookmark_identity_sha256 if bookmark is not None else None
        )
        source_changed = (
            previous_identity != next_identity or self._stock_code != requested_stock
        )
        self._generation += 1
        self._bookmark = bookmark
        self._bookmark_identity = next_identity
        self._stock_code = requested_stock
        self._verified_source = None
        self._source_error = input_error
        self._source_locator = ""
        self._loaded_note = None
        self._loaded_source_state = None
        self._loaded_source_error = ""
        self._clear_revision_selection()

        if source_changed and self.editor.toPlainText().strip():
            self._draft_revision_of = None
            if self._draft_source is None:
                self._draft_source_missing = True

        self._render_unverified_source(input_error)
        if bookmark is None and not requested_stock:
            self._pending_load = False
            if (
                self._active_worker is not None
                and (self._active_job or {}).get("kind") != "save"
            ):
                self._active_worker.cancel(cooperative=True, wait=False)
            self._notes_by_id.clear()
            self._note_locators.clear()
            self._update_controls()
            self._set_status("目前沒有指定股票或原價格版本；不讀取其他股票筆記。")
            return

        self._pending_load = True
        if self._active_worker is not None:
            job = self._active_job or {}
            if job.get("kind") != "save":
                self._active_worker.cancel(cooperative=True, wait=False)
            self._update_controls()
            return
        self._start_current_load()

    def clear_source(self) -> None:
        """清除股票及版本，避免顯示其他股票的筆記。"""

        self.set_source(None)

    def is_busy(self) -> bool:
        return self._active_worker is not None

    def has_pending_write(self) -> bool:
        return bool(
            self._active_job is not None
            and self._active_job.get("kind") == "save"
            and self._active_worker is not None
        )

    def request_cancel(self) -> None:
        """關閉時取消讀取；已送出的 Journal 寫入只能等待結果。"""

        if self._shutdown:
            return
        self._shutdown = True
        self._generation += 1
        self._pending_load = False
        worker = self._active_worker
        job = self._active_job or {}
        if worker is not None and job.get("kind") == "save":
            self._set_status(
                "筆記保存已送出且不能安全中止；關閉後結果可能未知，重新開啟後請明選股票並刷新清單核對。"
            )
        elif worker is not None:
            worker.cancel(cooperative=True, wait=False)
            self._set_status("已要求停止背景讀取；本次沒有執行新的筆記寫入。")
        self._update_controls()

    def shutdown(self) -> None:
        """供 Root 關閉流程使用的合作式別名。"""

        self.request_cancel()

    def _render_unverified_source(self, input_error: str = "") -> None:
        if self._bookmark is None:
            stock = self._stock_code or "尚未選擇"
            self.source_label.setText(
                f"股票：{stock}｜行情觀測日：未知｜原研究日：未知｜目前沒有已核對原價格版本"
            )
            self.source_label.setToolTip(input_error)
            return
        self.source_label.setText(
            f"股票：{self._stock_code}｜行情觀測日：待核對｜原研究日：待核對｜原價格版本正在背景核對。"
        )
        self.source_label.setToolTip(input_error)

    def _start_current_load(self) -> None:
        if self._shutdown or self.is_busy() or not self._pending_load:
            return
        self._pending_load = False
        bookmark = self._bookmark
        stock_code = self._stock_code
        generation = self._generation
        expected_identity = self._bookmark_identity
        if not stock_code:
            self._set_status("請明確指定股票；不會載入其他股票的筆記。")
            self._update_controls()
            return

        if bookmark is None:
            source_error = self._source_error

            def list_notes(cancel_callback=None):
                if cancel_callback is not None and cancel_callback():
                    raise InterruptedError("筆記清單讀取已取消")
                notes = self._service.list_notes(stock_code=stock_code)
                if cancel_callback is not None and cancel_callback():
                    raise InterruptedError("筆記清單讀取已取消")
                locators = {
                    note.revision_id: _source_locator(note.source)
                    for note in notes
                    if isinstance(note, PinnedStockResearchNote)
                }
                return {
                    "source": None,
                    "source_error": source_error,
                    "notes": notes,
                    "locators": locators,
                }

            self._start_worker(
                "list",
                list_notes,
                job={
                    "kind": "list",
                    "generation": generation,
                    "stock_code": stock_code,
                    "bookmark_identity": None,
                },
            )
            return

        def verify_and_list(cancel_callback=None):
            source = None
            source_error = ""
            try:
                source = verify_pinned_stock_research_source(
                    bookmark,
                    cancel_callback=cancel_callback,
                )
                if (
                    not isinstance(source, PinnedStockResearchSource)
                    or source.identity_sha256 != expected_identity
                    or source.stock_code != stock_code
                    or source.bookmark_json != bookmark.to_json()
                ):
                    raise ValueError("新鮮核對回傳與明選 F07 股票或版本不符")
                source_locator = _source_locator(source)
            except InterruptedError:
                raise
            except Exception as exc:  # noqa: BLE001 - 保存來源邊界
                source = None
                source_error = _error_text(exc)
                source_locator = ""
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("原價格版本核對已取消")
            notes = self._service.list_notes(stock_code=stock_code)
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("筆記清單讀取已取消")
            locators = {
                note.revision_id: _source_locator(note.source)
                for note in notes
                if isinstance(note, PinnedStockResearchNote)
            }
            return {
                "source": source,
                "source_error": source_error,
                "source_locator": source_locator,
                "notes": notes,
                "locators": locators,
            }

        self._start_worker(
            "list",
            verify_and_list,
            job={
                "kind": "list",
                "generation": generation,
                "stock_code": stock_code,
                "bookmark_identity": expected_identity,
            },
        )

    def _clear_revision_selection(self) -> None:
        self._updating_revisions = True
        self.revisions.clear()
        self._updating_revisions = False
        self._notes_by_id.clear()
        self._note_locators.clear()
        self.saved_text.clear()
        self._update_controls()

    def _selected_revision_id(self) -> str | None:
        value = self.revisions.currentData(Qt.ItemDataRole.UserRole)
        return value if isinstance(value, str) and value else None

    def _on_revision_selected(self, *_args: Any) -> None:
        if self._updating_revisions:
            return
        selected_id = self._selected_revision_id()
        if self._loaded_note is not None and self._loaded_note.revision_id != selected_id:
            self._loaded_note = None
            self._loaded_source_state = None
            self._loaded_source_error = ""
            self.saved_text.clear()
        if self._draft_revision_of and selected_id != self._draft_revision_of:
            self._draft_revision_of = None
            self._set_status("明選筆記已改變；現有草稿不會沿用舊 revision 作父版。")
        self._update_controls()

    def _on_editor_changed(self) -> None:
        if self._updating_editor or self._shutdown:
            return
        text = self.editor.toPlainText()
        if not text.strip():
            self._draft_source = None
            self._draft_revision_of = None
            self._draft_source_missing = False
            self._update_controls()
            return
        if self._draft_source is None and not self._draft_source_missing:
            if (
                self._verified_source is not None
                and self._verified_source.stock_code == self._stock_code
            ):
                self._draft_source = self._verified_source
            else:
                self._draft_source_missing = True
        self._update_controls()

    def _read_selected(self, *, open_after: bool = False) -> None:
        if self.is_busy() or self._shutdown:
            return
        revision_id = self._selected_revision_id()
        note = self._notes_by_id.get(revision_id or "")
        if note is None or revision_id is None:
            self._set_status("請先明選一篇同股票的已保存筆記。")
            return
        if note.source.stock_code != self._stock_code:
            self._set_status("所選筆記股票與目前股票不符，未讀取。")
            return
        expected_note = note
        generation = self._generation
        stock_code = self._stock_code

        def read_and_verify(cancel_callback=None):
            loaded = self._service.get_note(revision_id)
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("筆記讀取已取消")
            if (
                not isinstance(loaded, PinnedStockResearchNote)
                or loaded.revision_id != revision_id
                or loaded != expected_note
                or loaded.source.stock_code != stock_code
            ):
                raise ValueError("讀回的筆記身份或股票與明選項目不符")
            try:
                state = self._service.verify_source(
                    loaded,
                    cancel_callback=cancel_callback,
                )
                if (
                    not isinstance(state, DailyMarketTechnicalUniversePriceBookmarkStateV1)
                    or state.bookmark.to_json() != loaded.source.bookmark_json
                    or state.bookmark.bookmark_identity_sha256 != loaded.source.identity_sha256
                    or state.bookmark.stock_code != loaded.source.stock_code
                ):
                    raise ValueError("原價格版本重新核對結果與筆記 pins 不符")
                locator = _state_locator(state)
                return {
                    "note": loaded,
                    "state": state,
                    "source_error": "",
                    "locator": locator,
                }
            except InterruptedError:
                raise
            except Exception as exc:  # noqa: BLE001 - 原文仍可讀，來源另行標失敗
                return {
                    "note": loaded,
                    "state": None,
                    "source_error": _error_text(exc),
                    "locator": "",
                }

        action = "重新讀取並核對" if open_after else "讀取並核對"
        self._set_status(f"正在{action}明選筆記 {revision_id} 的原價格版本…")
        self._start_worker(
            "open" if open_after else "read",
            read_and_verify,
            job={
                "kind": "open" if open_after else "read",
                "generation": generation,
                "revision_id": revision_id,
                "stock_code": stock_code,
                "expected_note": expected_note,
            },
        )

    def _open_selected_source(self) -> None:
        revision_id = self._selected_revision_id()
        if (
            revision_id is None
            or self._loaded_note is None
            or self._loaded_note.revision_id != revision_id
            or self._loaded_source_state is None
        ):
            self._set_status("請先明選筆記、讀取原文並成功核對原價格版本。")
            return
        self._read_selected(open_after=True)

    def _prepare_revision(self) -> None:
        revision_id = self._selected_revision_id()
        note = self._loaded_note
        state = self._loaded_source_state
        if note is None or note.revision_id != revision_id:
            self._set_status("請先明選並讀取所選筆記；原文載入後才能追加修訂。")
            return
        if state is None:
            detail = f"：{self._loaded_source_error}" if self._loaded_source_error else "。"
            self._set_status(f"原價格版本未能重新核對，不能另存修訂{detail}")
            return
        if (
            self._bookmark is None
            or self._bookmark_identity != note.source.identity_sha256
            or self._verified_source is None
            or self._verified_source.bookmark_json != note.source.bookmark_json
        ):
            self._set_status("修訂只可在目前明選同一原價格版本時進行；可先開啟筆記的原價格版本。")
            return
        if self.editor.toPlainText().strip():
            self._set_status("目前仍有草稿；請先保存或清空，避免覆蓋未保存文字。")
            return
        self._draft_source = note.source
        self._draft_revision_of = note.revision_id
        self._draft_source_missing = False
        self._updating_editor = True
        self.editor.setPlainText(note.text)
        self._updating_editor = False
        self._set_status(
            f"已建立修訂草稿；保存會追加新 revision，沿用原筆記 {note.revision_id}。"
        )
        self._update_controls()

    def _save_current_draft(self) -> None:
        if self.is_busy() or self._shutdown:
            return
        text = self.editor.toPlainText()
        if not text.strip():
            self._set_status("請輸入個人研究筆記內容。")
            return
        if len(text) > _MAX_NOTE_LENGTH:
            self._set_status(f"筆記超過 {_MAX_NOTE_LENGTH} 字，尚未保存。")
            return
        source = self._draft_source
        if self._draft_source_missing or source is None:
            self._set_status("草稿沒有明選並核對的 F07 原價格版本；尚未保存。")
            return
        if (
            self._bookmark is None
            or self._bookmark_identity != source.identity_sha256
            or self._verified_source is None
            or self._verified_source.bookmark_json != source.bookmark_json
            or source.stock_code != self._stock_code
        ):
            self._set_status("草稿鎖定的原價格版本不是目前已核對版本；請先返回該版本。")
            return
        revision_id = str(uuid4())
        revision_of = self._draft_revision_of
        job = {
            "kind": "save",
            "generation": self._generation,
            "source": source,
            "stock_code": source.stock_code,
            "bookmark_identity": self._bookmark_identity,
            "text": text,
            "revision_id": revision_id,
            "revision_of": revision_of,
        }
        save_with_readback = getattr(self._service, "save_with_readback", None)
        uses_save_readback = callable(save_with_readback)
        job["save_with_readback"] = uses_save_readback

        if uses_save_readback:
            readback_saver = save_with_readback

            def save_note():
                return readback_saver(
                    source,
                    text,
                    revision_id=revision_id,
                    revision_of=revision_of,
                )
        else:
            def save_note():
                return self._service.save(
                    source,
                    text,
                    revision_id=revision_id,
                    revision_of=revision_of,
                )

        self._set_status("正在把原文追加到明選 F07 價格版本的個人筆記…")
        self._start_worker("save", save_note, job=job)

    def _start_worker(
        self,
        kind: str,
        function: Any,
        *args: Any,
        job: dict[str, Any],
    ) -> None:
        if self._shutdown or self.is_busy():
            return
        worker_type = _PinnedStockResearchNoteSaveWorker if kind == "save" else TaskWorker
        worker = worker_type(function, *args)
        self._active_worker = worker
        self._active_job = job
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
        except Exception as exc:  # noqa: BLE001 - Qt 工作邊界
            self._workers.pop(id(worker), None)
            self._active_worker = None
            self._active_job = None
            worker.deleteLater()
            detail = _error_text(exc)
            if kind == "open":
                self._loaded_source_state = None
                self._loaded_source_error = detail
                self._set_status(
                    f"原文仍可讀；原價格版本重新核對未能啟動：{detail}。"
                    "不能開啟來源或另存修訂。"
                )
            else:
                self._set_status(
                    f"{('保存' if kind == 'save' else '讀取')}未能啟動：{detail}"
                )
            self._update_controls()
            if self._pending_load and not self._shutdown:
                self._start_current_load()

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
                self._set_status(f"筆記保存失敗：{_error_text(value)}；原筆記未由畫面覆寫。")
            elif kind == "open" and job.get("generation") == self._generation:
                self._loaded_source_state = None
                self._loaded_source_error = _error_text(value)
                self._set_status(
                    f"原文仍可讀；原價格版本重新核對失敗：{self._loaded_source_error}。"
                    "不能開啟來源或另存修訂。"
                )
                self._update_controls()
            elif job.get("generation") == self._generation:
                self._set_status(f"筆記讀取未完成：{_error_text(value)}")
        elif outcome_kind == "cancelled" and job.get("generation") == self._generation:
            self._set_status("背景讀取已取消；沒有執行筆記寫入。")

        if self._pending_load and not self._shutdown:
            self._start_current_load()

    def _apply_worker_result(self, kind: str, value: Any, job: dict[str, Any]) -> None:
        if kind != "save" and job.get("generation") != self._generation:
            return
        if kind == "list":
            self._apply_note_list(value, job)
            return
        if kind in {"read", "open"}:
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("note"), PinnedStockResearchNote)
                or value["note"].revision_id != job.get("revision_id")
                or value["note"] != job.get("expected_note")
                or self._selected_revision_id() != job.get("revision_id")
                or self._stock_code != job.get("stock_code")
                or (
                    value.get("state") is not None
                    and not isinstance(
                        value.get("state"),
                        DailyMarketTechnicalUniversePriceBookmarkStateV1,
                    )
                )
            ):
                if kind == "open" and job.get("generation") == self._generation:
                    self._loaded_source_state = None
                    self._loaded_source_error = "讀回的筆記身份與目前明選項目不符"
                    self._set_status(
                        f"原文仍可讀；原價格版本重新核對失敗：{self._loaded_source_error}。"
                        "不能開啟來源或另存修訂。"
                    )
                    self._update_controls()
                return
            note = value["note"]
            if note.source.stock_code != self._stock_code:
                if kind == "open":
                    self._loaded_source_state = None
                    self._loaded_source_error = "讀回的筆記股票與目前明選股票不符"
                    self._set_status(
                        f"原文仍可讀；原價格版本重新核對失敗：{self._loaded_source_error}。"
                        "不能開啟來源或另存修訂。"
                    )
                    self._update_controls()
                return
            self._loaded_note = note
            self._loaded_source_state = value.get("state")
            self._loaded_source_error = str(value.get("source_error") or "")
            self.saved_text.setPlainText(note.text)
            if self._loaded_source_state is not None:
                locator = str(value.get("locator") or "未知")
                self._set_status(
                    f"已讀取唯讀筆記 {note.revision_id}｜股票 {note.source.stock_code}｜"
                    f"行情觀測日 {_display_date(note.source.data_date)}｜"
                    f"原研究日 {note.source.research_date}｜"
                    f"實際保存時間 {_recorded_at(note)}；原價格版本已重新核對。"
                )
                self.source_label.setToolTip(_source_tooltip(note.source, locator))
            else:
                failure_label = (
                    "原價格版本重新核對失敗："
                    if kind == "open"
                    else "原件核對失敗："
                )
                self._set_status(
                    f"已讀取唯讀筆記 {note.revision_id}｜原文仍可讀；{failure_label}"
                    f"{self._loaded_source_error or '來源無法驗證'}。不能開啟來源或另存修訂。"
                )
            self._update_controls()
            if kind == "open" and self._loaded_source_state is not None:
                self.open_source_requested.emit(self._loaded_source_state)
            return
        if kind == "save":
            note = value
            source = job.get("source")
            if job.get("save_with_readback"):
                prepared_readback = self._prepare_save_readback(value, job)
                if prepared_readback is None:
                    self._set_status(
                        "保存回讀身份與送出內容不符；結果未確認，請刷新清單核對。"
                    )
                    if self._stock_code:
                        self._pending_load = True
                    self._update_controls()
                    return
                note, list_value = prepared_readback
                if self._can_apply_save_readback(note, job):
                    self._clear_saved_draft_if_unchanged(note, job)
                    self._post_refresh_status = (
                        f"已保存筆記 {note.revision_id}｜實際保存時間 {_recorded_at(note)}。"
                        "請明選新修訂讀回原文。"
                    )
                    self._apply_note_list(list_value, job)
                    return
            if (
                not isinstance(note, PinnedStockResearchNote)
                or not isinstance(source, PinnedStockResearchSource)
                or note.revision_id != job.get("revision_id")
                or note.source.bookmark_json != source.bookmark_json
                or note.text != job.get("text")
                or note.revision_of != job.get("revision_of")
            ):
                self._set_status("保存回傳身份與送出內容不符；結果未確認，請刷新清單核對。")
                if self._stock_code:
                    self._pending_load = True
                self._update_controls()
                return
            if (
                self.editor.toPlainText() == job.get("text")
                and self._draft_source is not None
                and self._draft_source.bookmark_json == source.bookmark_json
            ):
                self._updating_editor = True
                self.editor.clear()
                self._updating_editor = False
                self._draft_source = None
                self._draft_revision_of = None
                self._draft_source_missing = False
            current_stock = self._stock_code
            if self._shutdown:
                self._set_status(
                    f"已確認保存筆記 {note.revision_id}（實際保存時間 {_recorded_at(note)}）；"
                    "重新開啟後請明選股票並刷新清單。"
                )
            else:
                self._post_refresh_status = (
                    f"已保存筆記 {note.revision_id}｜實際保存時間 {_recorded_at(note)}。"
                    + (
                        " 清單已切換至另一股票。"
                        if current_stock != note.source.stock_code
                        else " 請明選新修訂讀回原文。"
                    )
                )
                if current_stock:
                    self._pending_load = True
            self._update_controls()
            return

    def _prepare_save_readback(
        self,
        value: Any,
        job: dict[str, Any],
    ) -> tuple[PinnedStockResearchNote, dict[str, Any]] | None:
        try:
            if type(value) is not PinnedStockResearchNoteSaveReadback:
                return None
            note = value.note
            state = value.source_state
            notes = value.notes
            source = job.get("source")
            stock_code = job.get("stock_code")
            if (
                type(note) is not PinnedStockResearchNote
                or type(note.source) is not PinnedStockResearchSource
                or type(state) is not DailyMarketTechnicalUniversePriceBookmarkStateV1
                or type(state.bookmark) is not DailyMarketTechnicalUniversePriceBookmarkV1
                or not isinstance(source, PinnedStockResearchSource)
                or not isinstance(notes, tuple)
                or any(type(item) is not PinnedStockResearchNote for item in notes)
                or not isinstance(stock_code, str)
                or source.stock_code != stock_code
                or source.identity_sha256 != job.get("bookmark_identity")
                or state.bookmark.to_json() != source.bookmark_json
                or state.bookmark.bookmark_identity_sha256 != source.identity_sha256
                or state.bookmark.stock_code != stock_code
                or note.source.bookmark_json != source.bookmark_json
                or note.source.identity_sha256 != source.identity_sha256
                or note.source.stock_code != stock_code
                or note.revision_id != job.get("revision_id")
                or note.text != job.get("text")
                or note.revision_of != job.get("revision_of")
                or not isinstance(note.recorded_at, str)
                or not note.recorded_at.strip()
            ):
                return None

            matching = tuple(
                item for item in notes if item.revision_id == note.revision_id
            )
            if len(matching) != 1:
                return None
            readback_note = matching[0]
            if (
                readback_note != note
                or readback_note.source.bookmark_json != note.source.bookmark_json
                or readback_note.text != note.text
                or readback_note.revision_of != note.revision_of
                or readback_note.recorded_at != note.recorded_at
                or any(
                    not item.revision_id
                    or item.source.stock_code != stock_code
                    for item in notes
                )
                or len({item.revision_id for item in notes}) != len(notes)
            ):
                return None

            locators = {
                item.revision_id: _source_locator(item.source)
                for item in notes
            }
            list_value = {
                "source": note.source,
                "source_error": "",
                "source_locator": _source_locator(note.source),
                "notes": notes,
                "locators": locators,
            }
        except Exception:  # noqa: BLE001 - 回讀收據異常時安全拒絕
            return None
        return note, list_value

    def _can_apply_save_readback(
        self,
        note: PinnedStockResearchNote,
        job: dict[str, Any],
    ) -> bool:
        source = job.get("source")
        bookmark = self._bookmark
        if (
            self._shutdown
            or self._pending_load
            or job.get("generation") != self._generation
            or not isinstance(source, PinnedStockResearchSource)
            or bookmark is None
            or self._stock_code != job.get("stock_code")
            or note.source.stock_code != self._stock_code
            or source.stock_code != self._stock_code
            or self._bookmark_identity != source.identity_sha256
            or job.get("bookmark_identity") != source.identity_sha256
        ):
            return False
        try:
            return bookmark.to_json() == source.bookmark_json
        except Exception:  # noqa: BLE001 - 目前來源不符時安全拒絕
            return False

    def _clear_saved_draft_if_unchanged(
        self,
        note: PinnedStockResearchNote,
        job: dict[str, Any],
    ) -> None:
        if (
            self.editor.toPlainText() == job.get("text")
            and self._draft_source is not None
            and self._draft_source.bookmark_json == note.source.bookmark_json
        ):
            self._updating_editor = True
            self.editor.clear()
            self._updating_editor = False
            self._draft_source = None
            self._draft_revision_of = None
            self._draft_source_missing = False

    def _apply_note_list(self, value: Any, job: dict[str, Any]) -> None:
        if not isinstance(value, dict):
            self._set_status("筆記清單格式無法核對；沒有自動選取任何筆記。")
            return
        notes = value.get("notes")
        if not isinstance(notes, tuple) or any(
            not isinstance(note, PinnedStockResearchNote) for note in notes
        ):
            self._set_status("筆記清單格式無法核對；沒有自動選取任何筆記。")
            return
        note_map: dict[str, PinnedStockResearchNote] = {}
        for note in notes:
            if (
                not note.revision_id
                or note.revision_id in note_map
                or note.source.stock_code != job.get("stock_code")
            ):
                self._set_status("筆記清單含重複身份或其他股票資料；拒絕猜選。")
                return
            note_map[note.revision_id] = note

        source = value.get("source")
        source_error = str(value.get("source_error") or "")
        expected_identity = job.get("bookmark_identity")
        if expected_identity is not None:
            if (
                not isinstance(source, PinnedStockResearchSource)
                or source.identity_sha256 != expected_identity
                or source.stock_code != job.get("stock_code")
            ):
                source = None
                source_error = source_error or "來源讀取器回傳不是明選 F07 版本。"
        else:
            source = None

        self._verified_source = source
        self._source_error = source_error
        self._source_locator = (
            str(value.get("source_locator") or "") if source is not None else ""
        )
        self._notes_by_id = note_map
        self._note_locators = {
            revision_id: str(locator)
            for revision_id, locator in (value.get("locators") or {}).items()
            if revision_id in note_map and isinstance(locator, str)
        }

        self._updating_revisions = True
        self.revisions.clear()
        for note in notes:
            label = (
                f"{_display_date(note.source.data_date)}｜原研究日 {note.source.research_date}｜"
                f"{_recorded_at(note)}｜{note.revision_id[:12]}"
            )
            if note.revision_of:
                label += "｜修訂"
            self.revisions.addItem(label, note.revision_id)
            self.revisions.setItemData(
                self.revisions.count() - 1,
                note.revision_id,
                Qt.ItemDataRole.UserRole,
            )
            self.revisions.setItemData(
                self.revisions.count() - 1,
                _source_tooltip(note.source, self._note_locators.get(note.revision_id, "未知")),
                Qt.ItemDataRole.ToolTipRole,
            )
        self.revisions.setCurrentIndex(-1)
        self._updating_revisions = False
        self._loaded_note = None
        self._loaded_source_state = None
        self._loaded_source_error = ""
        self.saved_text.clear()

        if self._verified_source is not None:
            self._render_verified_source(self._verified_source, self._source_locator)
        else:
            self._render_unverified_source(self._source_error)

        if self._post_refresh_status:
            self._set_status(f"{self._post_refresh_status} 已載入 {len(notes)} 篇同股票筆記。")
            self._post_refresh_status = None
        elif self._verified_source is not None:
            self._set_status(
                f"原價格版本已重新核對；載入 {len(notes)} 篇同股票筆記。明選一篇再讀取。"
            )
        elif self._bookmark is not None:
            self._set_status(
                f"原價格版本核對失敗：{self._source_error or '來源無法驗證'}。"
                f"仍可讀取 {len(notes)} 篇同股票舊筆記；新保存與修訂停用。"
            )
        elif self._source_error:
            self._set_status(
                f"目前原價格版本未核對：{self._source_error}。"
                f"仍可讀取 {len(notes)} 篇同股票舊筆記；新保存與修訂停用。"
            )
        else:
            self._set_status(
                f"目前沒有明選原價格版本；可讀取 {len(notes)} 篇同股票舊筆記，新保存與修訂停用。"
            )
        self._update_controls()

    def _render_verified_source(
        self,
        source: PinnedStockResearchSource,
        locator: str,
    ) -> None:
        self.source_label.setText(
            f"股票：{source.stock_code}｜行情觀測日：{_display_date(source.data_date)}｜"
            f"原研究日：{source.research_date}｜已核對 F07 原價格版本"
        )
        self.source_label.setToolTip(_source_tooltip(source, locator))

    def _update_controls(self) -> None:
        busy = self.is_busy()
        selected_id = self._selected_revision_id() if hasattr(self, "revisions") else None
        selected_note = self._notes_by_id.get(selected_id or "")
        editor_text = self.editor.toPlainText() if hasattr(self, "editor") else ""
        draft_source_matches_current = (
            self._draft_source is not None
            and self._verified_source is not None
            and self._draft_source.bookmark_json == self._verified_source.bookmark_json
            and self._bookmark_identity == self._draft_source.identity_sha256
            and self._draft_source.stock_code == self._stock_code
        )
        draft_is_saveable = (
            draft_source_matches_current
            and not self._draft_source_missing
            and bool(editor_text.strip())
            and len(editor_text) <= _MAX_NOTE_LENGTH
        )
        saving = bool(self._active_job and self._active_job.get("kind") == "save")
        self.editor.setReadOnly(self._shutdown or saving)
        self.save_button.setEnabled(not self._shutdown and not busy and draft_is_saveable)
        self.save_button.setText("保存修訂" if self._draft_revision_of else "保存新筆記")
        self.read_button.setEnabled(
            not self._shutdown and not busy and selected_note is not None
        )
        self.open_source_button.setEnabled(
            not self._shutdown
            and not busy
            and selected_note is not None
            and self._loaded_note is not None
            and self._loaded_note.revision_id == selected_id
            and self._loaded_source_state is not None
        )
        can_revise = (
            not self._shutdown
            and not busy
            and selected_note is not None
            and self._loaded_note is not None
            and self._loaded_note.revision_id == selected_id
            and self._loaded_source_state is not None
            and self._bookmark is not None
            and self._bookmark_identity == selected_note.source.identity_sha256
            and self._verified_source is not None
            and self._verified_source.bookmark_json == selected_note.source.bookmark_json
            and not editor_text.strip()
        )
        self.revise_button.setEnabled(can_revise)
        self.revisions.setEnabled(
            not self._shutdown and not busy and bool(self._notes_by_id)
        )

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt 覆寫
        self.shutdown()
        super().closeEvent(event)


def _display_date(value: str) -> str:
    return value if isinstance(value, str) and value else "未知"


def _recorded_at(note: PinnedStockResearchNote) -> str:
    value = note.recorded_at
    return value if isinstance(value, str) and value else "未知"


def _source_locator(source: PinnedStockResearchSource) -> str:
    bookmark = DailyMarketTechnicalUniversePriceBookmarkV1.from_json(source.bookmark_json)
    return str(bookmark.selected.query.source.store_output_root)


def _state_locator(state: DailyMarketTechnicalUniversePriceBookmarkStateV1) -> str:
    return str(state.selected.query.source.store_output_root)


def _source_tooltip(source: PinnedStockResearchSource, locator: str) -> str:
    return (
        f"完整 Bookmark SHA-256：{source.identity_sha256}\n"
        f"快照 SHA-256：{source.snapshot_identity_sha256}\n"
        f"F07 原件定位：{locator or '未知'}\n"
        f"原研究日：{source.research_date}｜行情觀測日：{_display_date(source.data_date)}"
    )


def _error_text(error: object) -> str:
    lines = str(error).splitlines()
    rendered = lines[0].strip() if lines else ""
    return rendered[:400] if rendered else "未提供原因"
