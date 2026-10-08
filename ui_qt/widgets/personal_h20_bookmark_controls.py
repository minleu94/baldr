"""觀察清單內 H20 原保存研究收藏的精確重開與移除控制項。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_research_bookmark import (
    DailyMarketResearchBookmarkMutationResult,
    DailyMarketResearchBookmarkRestoreToken,
)
from app_module.recommendation.personal_h20_research_bookmark import (
    PERSONAL_H20_RESEARCH_BOOKMARK_SCHEMA,
    PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE,
    PersonalH20ResearchBookmark,
    PersonalH20ResearchBookmarkState,
)
from app_module.watchlist_service import WatchlistService
from ui_qt.workers.task_worker import TaskWorker


PersonalH20BookmarkStateReader = Callable[..., PersonalH20ResearchBookmarkState]
SelectionRestoreResult = Literal["selected", "queued", "rejected"]


@dataclass(frozen=True, slots=True)
class _PersonalH20BookmarkEntry:
    """一筆已驗 H20 收藏或仍須顯示的明確拒絕列。"""

    bookmark_id: str
    stock_code: str
    label: str
    bookmark: PersonalH20ResearchBookmark | None = None
    error_code: str = ""
    error_detail: str = ""


def _check_cancel(cancel_callback: Callable[[], bool] | None) -> None:
    if cancel_callback is None:
        return
    try:
        value = cancel_callback()
    except Exception as exc:
        raise ValueError("personal_h20_bookmark_cancel_check_failed") from exc
    if type(value) is not bool:
        raise ValueError("personal_h20_bookmark_cancel_callback_invalid")
    if value:
        raise InterruptedError("personal_h20_bookmark_cancelled")


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


def _is_personal_h20_candidate(row: Mapping[str, Any]) -> bool:
    payload = row.get("research_bookmark")
    payload_schema = payload.get("schema_version") if isinstance(payload, Mapping) else None
    return (
        row.get("source") == PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE
        or payload_schema == PERSONAL_H20_RESEARCH_BOOKMARK_SCHEMA
    )


def _invalid_entry(
    *,
    bookmark_id: str,
    stock_code: str,
    index: int,
    code: str,
    detail: str = "",
) -> _PersonalH20BookmarkEntry:
    display_code = stock_code or f"第 {index + 1} 筆"
    return _PersonalH20BookmarkEntry(
        bookmark_id=bookmark_id,
        stock_code=stock_code,
        label=f"{display_code}｜H20 收藏無法核驗（{code}）",
        error_code=code,
        error_detail=detail or code,
    )


def _list_personal_h20_bookmarks(
    service: WatchlistService,
    watchlist_id: str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[_PersonalH20BookmarkEntry, ...]:
    """沿公開 WatchlistService API 列 H20 typed bookmarks，不重開 latest。"""

    _check_cancel(cancel_callback)
    rows = service.get_stocks(watchlist_id)
    _check_cancel(cancel_callback)
    if not isinstance(rows, list):
        raise ValueError("personal_h20_bookmark_watchlist_rows_invalid")

    candidates: list[tuple[int, Mapping[str, Any], str, str]] = []
    for index, raw_row in enumerate(rows):
        _check_cancel(cancel_callback)
        if not isinstance(raw_row, Mapping) or not _is_personal_h20_candidate(raw_row):
            continue
        bookmark_id = _text(raw_row, "source_id")
        stock_code = _text(raw_row, "stock_code")
        candidates.append((index, raw_row, bookmark_id, stock_code))

    candidate_ids = {bookmark_id for _index, _row, bookmark_id, _code in candidates if bookmark_id}
    identity_counts: Counter[str] = Counter(
        source_id
        for raw_row in rows
        if isinstance(raw_row, Mapping)
        for source_id in (_text(raw_row, "source_id"),)
        if source_id in candidate_ids
    )

    entries: list[_PersonalH20BookmarkEntry] = []
    for index, row, bookmark_id, stock_code in candidates:
        _check_cancel(cancel_callback)
        if not bookmark_id:
            entries.append(
                _invalid_entry(
                    bookmark_id="",
                    stock_code=stock_code,
                    index=index,
                    code="personal_h20_bookmark_source_id_missing",
                )
            )
            continue
        if identity_counts[bookmark_id] != 1:
            entries.append(
                _invalid_entry(
                    bookmark_id=bookmark_id,
                    stock_code=stock_code,
                    index=index,
                    code="personal_h20_bookmark_identity_ambiguous",
                )
            )
            continue
        try:
            bookmark = service.get_research_bookmark(bookmark_id, watchlist_id)
        except Exception as exc:
            code = str(getattr(exc, "code", "personal_h20_bookmark_decode_failed"))
            entries.append(
                _invalid_entry(
                    bookmark_id=bookmark_id,
                    stock_code=stock_code,
                    index=index,
                    code=code,
                    detail=f"{code}: {exc}",
                )
            )
            continue
        if not isinstance(bookmark, PersonalH20ResearchBookmark):
            entries.append(
                _invalid_entry(
                    bookmark_id=bookmark_id,
                    stock_code=stock_code,
                    index=index,
                    code="personal_h20_bookmark_typed_payload_required",
                )
            )
            continue

        source = row.get("source")
        stock_name = _text(row, "stock_name")
        if (
            source != PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE
            or bookmark.source_id != bookmark_id
            or bookmark.stock_code != stock_code
            or stock_name != bookmark.stock_code
        ):
            entries.append(
                _invalid_entry(
                    bookmark_id=bookmark_id,
                    stock_code=stock_code or bookmark.stock_code,
                    index=index,
                    code="personal_h20_bookmark_watchlist_identity_mismatch",
                )
            )
            continue
        entries.append(
            _PersonalH20BookmarkEntry(
                bookmark_id=bookmark.bookmark_id,
                stock_code=bookmark.stock_code,
                label=(
                    f"{bookmark.decision_date}｜{bookmark.stock_code}｜"
                    f"cycle {bookmark.cycle_id}"
                ),
                bookmark=bookmark,
            )
        )
    for index, raw_row in enumerate(rows):
        _check_cancel(cancel_callback)
        if not isinstance(raw_row, Mapping) or _is_personal_h20_candidate(raw_row):
            continue
        conflicting_id = _text(raw_row, "source_id")
        if conflicting_id not in candidate_ids or identity_counts[conflicting_id] < 2:
            continue
        entries.append(
            _invalid_entry(
                bookmark_id=conflicting_id,
                stock_code=_text(raw_row, "stock_code"),
                index=index,
                code="personal_h20_bookmark_identity_conflict_with_other_watchlist_row",
                detail="同一 source_id 同時用於另一個觀察清單項目；所有衝突列均停用。",
            )
        )
    _check_cancel(cancel_callback)
    return tuple(entries)


def _read_personal_h20_bookmark_state(
    service: WatchlistService,
    bookmark_id: str,
    watchlist_id: str,
    config_path: Path,
    market_root: Path,
    prediction_reader: Callable[..., Mapping[str, Any]] | None,
    bookmark_state_reader: PersonalH20BookmarkStateReader | None,
    *,
    cancel_callback: Callable[[], bool] | None = None,
    sqlite_read_root: Path | None = None,
    require_sqlite_copy: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> PersonalH20ResearchBookmarkState:
    _check_cancel(cancel_callback)
    bookmark = service.get_research_bookmark(bookmark_id, watchlist_id)
    if (
        not isinstance(bookmark, PersonalH20ResearchBookmark)
        or bookmark.bookmark_id != bookmark_id
    ):
        raise ValueError("personal_h20_bookmark_exact_identity_required")
    original_payload = bookmark.to_dict()
    if type(require_sqlite_copy) is not bool:
        raise TypeError("personal_h20_sqlite_copy_requirement_must_be_bool")
    if require_sqlite_copy and sqlite_read_root is None:
        raise ValueError("personal_h20_sqlite_read_root_required")
    if require_sqlite_copy and bookmark_state_reader is None:
        raise ValueError("personal_h20_bookmark_secure_typed_reader_required")
    if bookmark_state_reader is not None:
        reader_options: dict[str, Any] = {
            "config_path": config_path,
            "market_root": market_root,
            "cancel_callback": cancel_callback,
        }
        if require_sqlite_copy and progress_callback is not None:
            reader_options["progress_callback"] = progress_callback
        if require_sqlite_copy:
            reader_options["sqlite_read_root"] = sqlite_read_root
            reader_options["require_sqlite_copy"] = True
        state = bookmark_state_reader(bookmark, **reader_options)
    else:
        if not callable(prediction_reader):
            raise ValueError("personal_h20_bookmark_public_prediction_reader_required")
        state = service.get_personal_h20_research_bookmark_state(
            bookmark_id,
            watchlist_id,
            config_path=config_path,
            market_root=market_root,
            prediction_reader=prediction_reader,
            cancel_callback=cancel_callback,
        )
    _check_cancel(cancel_callback)
    if not _state_matches_bookmark(state, bookmark, original_payload):
        raise ValueError("personal_h20_bookmark_reopened_state_identity_mismatch")
    latest_exact = service.get_research_bookmark(bookmark_id, watchlist_id)
    if (
        not isinstance(latest_exact, PersonalH20ResearchBookmark)
        or latest_exact.to_dict() != original_payload
    ):
        raise ValueError("personal_h20_bookmark_changed_during_read")
    _check_cancel(cancel_callback)
    return state


def _state_matches_bookmark(
    state: object,
    bookmark: PersonalH20ResearchBookmark,
    bookmark_payload: Mapping[str, Any],
) -> bool:
    if not isinstance(state, PersonalH20ResearchBookmarkState):
        return False
    if state.bookmark.to_dict() != dict(bookmark_payload):
        return False
    cohort = state.cohort
    if (
        cohort.manifest_sha256 != bookmark.manifest_sha256
        or cohort.candidate_id != bookmark.source_candidate_id
        or cohort.contract_hash != bookmark.source_contract_hash
        or cohort.cycle_id != bookmark.cycle_id
        or cohort.decision_date != bookmark.decision_date
    ):
        return False
    matching_rows = tuple(
        row for row in cohort.rows if row.symbol == bookmark.selected_row.symbol
    )
    if len(matching_rows) != 1 or state.selected_row != matching_rows[0]:
        return False
    selected = state.selected_row
    return (
        selected.symbol == bookmark.selected_row.symbol
        and selected.sample_id == bookmark.selected_row.sample_id
        and selected.prediction_id == bookmark.selected_row.prediction_id
        and selected.capture_sha256 == bookmark.selected_row.capture_sha256
    )


def _remove_personal_h20_bookmark(
    service: WatchlistService,
    bookmark_id: str,
    watchlist_id: str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketResearchBookmarkMutationResult:
    """送出精確 COW 移除；開始寫入後不回報成可取消操作。"""

    _check_cancel(cancel_callback)
    result = service.remove_research_bookmark(bookmark_id, watchlist_id)
    if (
        not isinstance(result, DailyMarketResearchBookmarkMutationResult)
        or result.bookmark_id != bookmark_id
        or result.watchlist_id != watchlist_id
    ):
        raise ValueError("personal_h20_bookmark_remove_result_identity_mismatch")
    return result


def _model_status_text(status: str) -> str:
    return {
        "enabled_same_contract": "目前啟用來源與收藏契約相同。",
        "disabled": "原保存來源已重開；目前個人模型停用。",
        "enabled_other_contract": "原保存來源已重開；目前啟用的是不同模型契約。",
    }.get(status, "目前模型狀態未知；不代表模型已啟用。")


class PersonalH20BookmarkControls(QWidget):
    """背景列出、精確重開與 COW 移除已收藏的 H20 原保存研究。"""

    stateReady = Signal(object)

    def __init__(
        self,
        watchlist_service: WatchlistService,
        *,
        config_path: str | Path,
        market_root: str | Path,
        prediction_reader: Callable[..., Mapping[str, Any]] | None = None,
        bookmark_state_reader: PersonalH20BookmarkStateReader | None = None,
        watchlist_id: str = "default",
        confirm_remove: Callable[[str, str], bool] | None = None,
        sqlite_read_root: str | Path | None = None,
        require_sqlite_copy: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if bookmark_state_reader is not None and not callable(bookmark_state_reader):
            raise TypeError("personal_h20_bookmark_typed_state_reader_required")
        if bookmark_state_reader is None and not callable(prediction_reader):
            raise TypeError("personal_h20_bookmark_public_prediction_reader_required")
        if type(require_sqlite_copy) is not bool:
            raise TypeError("personal_h20_sqlite_copy_requirement_must_be_bool")
        self.watchlist_service = watchlist_service
        self.watchlist_id = watchlist_id
        self.config_path = Path(config_path)
        self.market_root = Path(market_root)
        self.prediction_reader = prediction_reader
        self.bookmark_state_reader = bookmark_state_reader
        self.sqlite_read_root = (
            None if sqlite_read_root is None else Path(sqlite_read_root)
        )
        self.require_sqlite_copy = require_sqlite_copy
        self._confirm_remove_callback = confirm_remove
        self._generation = 0
        self._active_generation = 0
        self._selection_generation = 0
        self._opening_bookmark_id = ""
        self._opening_selection_generation = 0
        self._operation = ""
        self._refresh_pending = False
        self._restore_selection_id = ""
        self._has_loaded_list = False
        self._worker: TaskWorker | None = None
        self._closing = False
        self._last_restore_token: DailyMarketResearchBookmarkRestoreToken | None = None
        self._setup_ui()

    @property
    def last_restore_token(self) -> DailyMarketResearchBookmarkRestoreToken | None:
        """保留最近移除結果的精確復原 token，供後續 Undo 接線使用。"""

        return self._last_restore_token

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.bookmarks = QListWidget(self)
        self.bookmarks.setObjectName("personalH20Bookmarks")
        self.bookmarks.setAccessibleName("個人 H20 保存研究收藏")
        self.bookmarks.currentRowChanged.connect(self._selection_changed)
        layout.addWidget(self.bookmarks, 1)

        self.refresh_button = QPushButton("重新整理收藏", self)
        self.refresh_button.setAccessibleName("重新整理個人 H20 收藏")
        self.open_button = QPushButton("重開所選 H20 研究", self)
        self.open_button.setAccessibleName("重開所選個人 H20 原保存研究")
        self.remove_button = QPushButton("移除所選收藏", self)
        self.remove_button.setAccessibleName("移除所選個人 H20 收藏")
        self.cancel_button = QPushButton("取消讀取", self)
        self.cancel_button.setAccessibleName("取消個人 H20 收藏讀取")
        for button in (
            self.refresh_button,
            self.open_button,
            self.remove_button,
            self.cancel_button,
        ):
            button.setMinimumHeight(32)
            layout.addWidget(button)

        self.status_label = QLabel(
            "只讀取觀察清單中的 H20 typed 收藏；重開沿原 manifest 與 capture pins 核驗。",
            self,
        )
        self.status_label.setObjectName("personalH20BookmarkStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.diagnostic_text = QPlainTextEdit(self)
        self.diagnostic_text.setObjectName("personalH20BookmarkDiagnostic")
        self.diagnostic_text.setAccessibleName("個人 H20 收藏核驗診斷")
        self.diagnostic_text.setReadOnly(True)
        self.diagnostic_text.setMaximumBlockCount(80)
        self.diagnostic_text.setPlaceholderText("選取一列可查看完整收藏身份或拒絕原因。")
        self.diagnostic_text.setMinimumHeight(72)
        layout.addWidget(self.diagnostic_text)

        self.refresh_button.clicked.connect(self.refresh_bookmarks)
        self.open_button.clicked.connect(self.open_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        self.cancel_button.clicked.connect(self.cancel)
        self._refresh_controls()

    def refresh_bookmarks(self) -> None:
        """背景列出 H20 typed 收藏；失敗時保留上一份可見列表。"""

        if self._closing:
            self._can_start()
            return
        if self._worker is not None:
            self._refresh_pending = True
            if self._operation == "remove":
                self.status_label.setText("移除已送出，正在保存；完成後會重新整理收藏列表。")
            else:
                self.status_label.setText("目前的唯讀工作完成後，會合併執行一次列表刷新。")
            return
        self._refresh_pending = False
        worker = TaskWorker(
            _list_personal_h20_bookmarks,
            self.watchlist_service,
            self.watchlist_id,
        )
        self._start_worker(worker, "list")
        self.status_label.setText("正在背景讀取觀察清單中的 H20 typed 收藏…")

    def open_selected(self) -> None:
        """沿選取 bookmark 的原 manifest SHA 背景重開完整 H20 狀態。"""

        if not self._can_start():
            return
        entry = self._current_entry()
        if entry is None:
            self.status_label.setText("請先選取一筆個人 H20 收藏。")
            return
        if entry.error_code or entry.bookmark is None or not entry.bookmark_id:
            self.status_label.setText(
                f"此列無法核驗，已拒絕重開（{entry.error_code or 'personal_h20_bookmark_invalid'}）。"
            )
            self.diagnostic_text.setPlainText(entry.error_detail or entry.error_code)
            self._refresh_controls()
            return

        self._opening_bookmark_id = entry.bookmark_id
        self._opening_selection_generation = self._selection_generation
        worker = TaskWorker(
            _read_personal_h20_bookmark_state,
            self.watchlist_service,
            entry.bookmark_id,
            self.watchlist_id,
            self.config_path,
            self.market_root,
            self.prediction_reader,
            self.bookmark_state_reader,
            sqlite_read_root=self.sqlite_read_root,
            require_sqlite_copy=self.require_sqlite_copy,
            progress_callback=lambda message: worker.progress.emit(message, 0),
        )
        worker.progress.connect(self._on_open_progress)
        self._start_worker(worker, "open")
        self.status_label.setText("正在背景沿固定原 manifest 核驗所選 H20 收藏…")

    def remove_selected(self) -> None:
        """顯示預設否的明確身份確認，再移除精確 bookmark_id。"""

        if not self._can_start():
            return

        entry = self._current_entry()
        if entry is None:
            self.status_label.setText("請先選取一筆個人 H20 收藏。")
            return
        if entry.error_code or entry.bookmark is None or not entry.bookmark_id:
            self.status_label.setText(
                f"此列無法核驗，已拒絕移除（{entry.error_code or 'personal_h20_bookmark_invalid'}）。"
            )
            self.diagnostic_text.setPlainText(entry.error_detail or entry.error_code)
            self._refresh_controls()
            return
        if not self._confirm_remove(entry):
            self.status_label.setText("已取消移除；收藏與來源資料均未變更。")
            return

        worker = TaskWorker(
            _remove_personal_h20_bookmark,
            self.watchlist_service,
            entry.bookmark_id,
            self.watchlist_id,
        )
        self._refresh_pending = True
        self._start_worker(worker, "remove")
        self.status_label.setText("移除已送出，正在保存觀察清單 COW 變更…")

    def restore_selection(self, bookmark_id: str) -> SelectionRestoreResult:
        """精確恢復收藏選取；回傳 selected、queued 或 rejected。"""

        if self._closing:
            return "rejected"
        if (
            type(bookmark_id) is not str
            or not bookmark_id
            or bookmark_id != bookmark_id.strip()
        ):
            self.bookmarks.setCurrentRow(-1)
            self.status_label.setText("拒絕恢復收藏選取：bookmark_id 格式無效。")
            self.diagnostic_text.setPlainText("personal_h20_bookmark_restore_identity_invalid")
            self._refresh_controls()
            return "rejected"
        if self._worker is not None:
            if self._operation == "list" or self._refresh_pending:
                self._restore_selection_id = bookmark_id
                self.status_label.setText("已排定精確收藏選取；列表刷新後會核對身份再選取。")
                return "queued"
            self.status_label.setText("目前背景工作尚未完成；未變更收藏選取。")
            return "rejected"
        if not self._has_loaded_list:
            self._restore_selection_id = bookmark_id
            self.refresh_bookmarks()
            if self._worker is None:
                self._restore_selection_id = ""
                return "rejected"
            self.status_label.setText("已排定精確收藏選取；列表讀取完成後會核對身份。")
            return "queued"
        if self._apply_exact_selection(bookmark_id):
            return "selected"
        return "rejected"

    def _confirm_remove(self, entry: _PersonalH20BookmarkEntry) -> bool:
        callback = self._confirm_remove_callback
        if callback is None:
            answer = QMessageBox.question(
                self,
                "移除 H20 收藏",
                f"要從觀察清單移除 {entry.stock_code} 的這筆 H20 收藏嗎？\n\n"
                f"固定身份：{entry.bookmark_id}\n原 manifest SHA：{entry.bookmark.manifest_sha256}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return answer == QMessageBox.StandardButton.Yes
        try:
            answer = callback(entry.stock_code, entry.bookmark_id)
        except Exception as exc:
            self.status_label.setText(f"移除確認失敗，未送出變更：{exc}")
            return False
        if type(answer) is not bool:
            self.status_label.setText("移除確認回傳格式錯誤，未送出變更。")
            return False
        return answer

    def cancel(self) -> None:
        """取消讀取工作；已送出的 COW 移除不能中途撤回。"""

        if self._operation == "remove" and self._worker is not None:
            self.status_label.setText("移除已送出，正在保存；此 COW 寫入不能中途取消。")
            self._refresh_controls()
            return
        self._refresh_pending = False
        self._restore_selection_id = ""
        if self._worker is not None:
            self._generation += 1
            self._worker.cancel(cooperative=True, wait=False)
            self.status_label.setText("已取消讀取；晚到的舊結果會丟棄。")
        self._refresh_controls()

    def begin_shutdown(self) -> bool:
        """使 UI 結果失效；唯讀工作合作取消，已送出的 COW 自然收尾。"""

        self._closing = True
        self._generation += 1
        self._refresh_pending = False
        self._restore_selection_id = ""
        if self._worker is not None and self._operation != "remove":
            self._worker.cancel(cooperative=True, wait=False)
        self._refresh_controls()
        return self._worker is None or not self._worker.isRunning()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 覆寫命名遵循 Qt API
        self.begin_shutdown()
        event.accept()

    def _can_start(self) -> bool:
        if self._closing:
            self.status_label.setText("H20 收藏控制項已關閉，未啟動工作。")
            return False
        if self._worker is not None:
            self.status_label.setText("目前仍有背景工作；請先等待或取消。")
            return False
        return True

    def _start_worker(self, worker: TaskWorker, operation: str) -> None:
        self._generation += 1
        self._active_generation = self._generation
        self._operation = operation
        self._worker = worker
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.native_thread_finished.connect(self._on_worker_thread_finished)
        self._refresh_controls()
        worker.start()

    def _on_open_progress(self, message: str, _percentage: int = 0) -> None:
        worker = self.sender()
        if (
            worker is not self._worker
            or self._closing
            or self._operation != "open"
            or self._active_generation != self._generation
            or self._opening_selection_generation != self._selection_generation
        ):
            return
        self.status_label.setText("正在背景重驗 H20 原收藏：" + str(message))

    def _current_entry(self) -> _PersonalH20BookmarkEntry | None:
        item = self.bookmarks.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return value if isinstance(value, _PersonalH20BookmarkEntry) else None

    @Slot(int)
    def _selection_changed(self, _row: int) -> None:
        self._selection_generation += 1
        entry = self._current_entry()
        if entry is None:
            self.diagnostic_text.clear()
        elif entry.error_code:
            self.diagnostic_text.setPlainText(
                f"股票：{entry.stock_code or '未知'}\n"
                f"收藏身份：{entry.bookmark_id or '缺少 source_id'}\n"
                f"拒絕原因：{entry.error_detail}"
            )
        elif entry.bookmark is not None:
            bookmark = entry.bookmark
            self.diagnostic_text.setPlainText(
                f"股票：{bookmark.stock_code}\n"
                f"決策日：{bookmark.decision_date}\n"
                f"收藏身份：{bookmark.bookmark_id}\n"
                f"原 manifest SHA：{bookmark.manifest_sha256}\n"
                f"原 capture SHA：{bookmark.selected_row.capture_sha256}\n"
                "重開時只沿上述固定原來源讀取；不改指 current/latest。"
            )
        self._refresh_controls()
        if (
            self._worker is not None
            and self._operation == "open"
            and self._selection_generation != self._opening_selection_generation
        ):
            self._generation += 1
            self._worker.cancel(cooperative=True, wait=False)
            self.status_label.setText("選取已變更；取消舊收藏重開並忽略晚到結果。")

    def _refresh_controls(self) -> None:
        idle = self._worker is None and not self._closing
        entry = self._current_entry()
        actionable = (
            entry is not None
            and not entry.error_code
            and entry.bookmark is not None
            and bool(entry.bookmark_id)
        )
        self.refresh_button.setEnabled(idle)
        self.open_button.setEnabled(idle and actionable)
        self.remove_button.setEnabled(idle and actionable)
        self.cancel_button.setEnabled(
            self._worker is not None
            and not self._closing
            and self._operation != "remove"
        )

    @Slot(object)
    def _on_worker_finished(self, value: object) -> None:
        worker = self.sender()
        if worker is not self._worker:
            return
        if self._closing or self._active_generation != self._generation:
            return
        if self._operation == "list":
            if not isinstance(value, tuple) or any(
                not isinstance(entry, _PersonalH20BookmarkEntry) for entry in value
            ):
                self.status_label.setText("H20 收藏列回傳格式不符；原列表保留。")
                return
            self._show_entries(cast(tuple[_PersonalH20BookmarkEntry, ...], value))
            return
        if self._operation == "open":
            if not isinstance(value, PersonalH20ResearchBookmarkState):
                self.status_label.setText("原來源 reader 未回傳 H20 typed 狀態；未發出重開結果。")
                return
            if value.bookmark.bookmark_id != self._opening_bookmark_id:
                self.status_label.setText("重開結果與所選收藏 source_id 不符；未發出結果。")
                return
            if self._selection_generation != self._opening_selection_generation:
                self.status_label.setText("選取的收藏已變更；忽略晚到的舊讀取結果。")
                return
            self.status_label.setText(
                f"已沿原保存 manifest 重開 {value.selected_row.symbol}（決策日 "
                f"{value.cohort.decision_date}）；{_model_status_text(value.current_model_binding_status)}"
                if value.selected_row.status == "available"
                else f"原保存名單已重開，但 {value.selected_row.symbol} 的 capture 目前未知；"
                f"{_model_status_text(value.current_model_binding_status)}"
            )
            self.stateReady.emit(value)
            return
        if self._operation == "remove":
            if not isinstance(value, DailyMarketResearchBookmarkMutationResult):
                self.status_label.setText("COW 移除回傳格式不符；請重新整理核對保存狀態。")
                return
            if value.status == "removed" and value.restore_token is not None:
                self._last_restore_token = value.restore_token
                self.status_label.setText(
                    "H20 收藏已移除；精確復原 token 已保留，正在重新整理列表。"
                )
            else:
                self.status_label.setText(
                    f"H20 收藏未移除（{value.code}）；正在刷新以核對目前列表。"
                )
            self._refresh_pending = True
            return
        self.status_label.setText("背景收藏工作類型不符；未發出狀態。")

    def _show_entries(self, entries: tuple[_PersonalH20BookmarkEntry, ...]) -> None:
        selected = self._current_entry()
        selected_id = (
            selected.bookmark_id
            if selected is not None and selected.bookmark is not None and not selected.error_code
            else ""
        )
        restore_id = self._restore_selection_id or selected_id
        # 返回要求必須沿合併刷新鏈保持到最後一次，不能被下一次空列表
        # 摘要覆蓋「原收藏已缺漏」的確切拒絕原因。取消會另行清除此要求。
        self._restore_selection_id = restore_id if self._refresh_pending else ""
        self.bookmarks.clear()
        self.bookmarks.setCurrentRow(-1)
        for entry in entries:
            item = QListWidgetItem(entry.label, self.bookmarks)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            if entry.bookmark is not None:
                item.setToolTip(
                    f"固定收藏身份：{entry.bookmark_id}\n"
                    f"決策日：{entry.bookmark.decision_date}\n"
                    f"原 manifest SHA：{entry.bookmark.manifest_sha256}"
                )
            if entry.error_code:
                item.setForeground(Qt.GlobalColor.darkRed)
        self._has_loaded_list = True
        selection_restored = self._apply_exact_selection(restore_id) if restore_id else True
        if entries:
            invalid_count = sum(bool(entry.error_code) for entry in entries)
            self.status_label.setText(
                f"已列出 {len(entries)} 筆 H20 收藏；{invalid_count} 筆身份或格式無法核驗，仍保留顯示。"
            )
        else:
            self.status_label.setText("此觀察清單沒有個人 H20 研究收藏。")
        if restore_id and not selection_restored:
            # _apply_exact_selection 已留下確切拒絕原因；列表摘要不覆蓋它。
            self.status_label.setText(self._restore_rejection_status(restore_id))
        self._refresh_controls()

    def _apply_exact_selection(self, bookmark_id: str) -> bool:
        matches: list[tuple[int, _PersonalH20BookmarkEntry]] = []
        for row_index in range(self.bookmarks.count()):
            item = self.bookmarks.item(row_index)
            entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(entry, _PersonalH20BookmarkEntry) and entry.bookmark_id == bookmark_id:
                matches.append((row_index, entry))
        if (
            len(matches) == 1
            and matches[0][1].bookmark is not None
            and not matches[0][1].error_code
        ):
            self.bookmarks.setCurrentRow(matches[0][0])
            return True

        self.bookmarks.setCurrentRow(-1)
        if not matches:
            code = "personal_h20_bookmark_restore_target_missing"
            detail = f"找不到指定收藏身份 {bookmark_id}。"
        elif len(matches) > 1:
            code = "personal_h20_bookmark_restore_target_ambiguous"
            detail = f"收藏身份 {bookmark_id} 對應多筆或衝突列，拒絕選取。"
        else:
            entry = matches[0][1]
            code = entry.error_code or "personal_h20_bookmark_restore_target_invalid"
            detail = entry.error_detail or "指定收藏列未通過身份核驗。"
        self.diagnostic_text.setPlainText(
            f"拒絕恢復收藏選取：{detail}\n未改選其他列。\n拒絕代碼：{code}"
        )
        self._refresh_controls()
        return False

    def _restore_rejection_status(self, bookmark_id: str) -> str:
        matches = [
            item.data(Qt.ItemDataRole.UserRole)
            for row in range(self.bookmarks.count())
            if (item := self.bookmarks.item(row)) is not None
            and getattr(item.data(Qt.ItemDataRole.UserRole), "bookmark_id", None) == bookmark_id
        ]
        if not matches:
            return "列表已更新，但找不到指定收藏；沒有改選其他列。"
        if len(matches) > 1:
            return "列表已有重複或衝突身份；拒絕選取，也沒有改選其他列。"
        return "指定收藏列未通過核驗；拒絕選取，也沒有改選其他列。"

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        worker = self.sender()
        if worker is not self._worker:
            return
        if self._closing or self._active_generation != self._generation:
            return
        first_line = message.splitlines()[0].strip() if message.splitlines() else "讀取失敗"
        self.diagnostic_text.setPlainText(message)
        if self._operation == "list":
            self.status_label.setText(f"H20 收藏列表讀取失敗，原列表保留：{first_line}")
        elif self._operation == "remove":
            self.status_label.setText(
                f"移除已送出但結果未能核對（{first_line}）；正在刷新保存狀態。"
            )
            self._refresh_pending = True
        else:
            self.status_label.setText(f"原 H20 收藏重開失敗，未發出狀態：{first_line}")

    @Slot()
    def _on_worker_cancelled(self) -> None:
        worker = self.sender()
        if worker is self._worker and not self._closing and self._active_generation == self._generation:
            self.status_label.setText("H20 收藏讀取已取消；沒有套用或發出晚到結果。")

    @Slot()
    def _on_worker_thread_finished(self) -> None:
        worker = self.sender()
        refresh_pending = False
        if worker is self._worker:
            self._worker = None
            self._operation = ""
            self._opening_bookmark_id = ""
            refresh_pending = self._refresh_pending
            self._refresh_pending = False
            self._refresh_controls()
        if isinstance(worker, TaskWorker):
            worker.deleteLater()
        if refresh_pending and not self._closing:
            self.refresh_bookmarks()


__all__ = ["PersonalH20BookmarkControls"]
