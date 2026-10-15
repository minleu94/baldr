"""Research Lab 的 Paper 保存快照選取器；只讀、有限清單、明示 exact identity。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_module.strategy_paper_account_availability import (
    StrategyPaperAccountAvailabilityError,
    StrategyPaperAccountCheckpointCandidate,
    StrategyPaperAccountCheckpointCatalogue,
    list_strategy_paper_account_checkpoint_candidates,
)
from app_module.strategy_performance_read_service import (
    PaperCheckpointCard,
    PaperCheckpointSelector,
    ReadStatus,
)


def parse_explicit_aware_cutoff(value: str) -> datetime:
    """只解析使用者輸入的 ISO 時間；不填 now、不補本機時區。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("請明示時區感知的決策截止時間，例如 2026-08-01T09:00:00+08:00。")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("決策截止時間必須是有效 ISO 日期時間。") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("決策截止時間必須明示時區偏移。")
    return parsed


def build_exact_selector(
    *,
    strategy_id: str,
    strategy_version_id: str,
    account_namespace: str,
    decision_cutoff: datetime,
    catalogue: StrategyPaperAccountCheckpointCatalogue,
    candidate: StrategyPaperAccountCheckpointCandidate,
) -> PaperCheckpointSelector:
    """只把同一明示 catalogue 中可送 exact reader 的一列轉成 selector。"""

    if type(catalogue) is not StrategyPaperAccountCheckpointCatalogue:
        raise ValueError("checkpoint_catalogue_shape_unknown")
    if type(candidate) is not StrategyPaperAccountCheckpointCandidate:
        raise ValueError("checkpoint_candidate_shape_unknown")
    if not (
        any(row is candidate for row in catalogue.rows)
        and strategy_id == catalogue.strategy_id
        and strategy_version_id == catalogue.strategy_version_id
        and account_namespace == catalogue.account_namespace
        and decision_cutoff == catalogue.decision_cutoff
        and candidate.row_state == "candidate_pending_exact_reader"
        and not candidate.blockers
        and candidate.exact_reader_required is True
        and candidate.checkpoint_verified is False
        and candidate.performance_eligible is False
        and candidate.observed_portfolio_id == catalogue.portfolio_id
        and candidate.observed_account_namespace == catalogue.account_namespace
        and candidate.observed_binding_sha256 == catalogue.binding_sha256
        and catalogue.checkpoint_verified is False
        and catalogue.performance_eligible is False
    ):
        raise ValueError("checkpoint_candidate_not_bound_to_explicit_catalogue")
    return PaperCheckpointSelector(
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        account_namespace=account_namespace,
        operation_id=candidate.operation_id,
        snapshot_id=candidate.snapshot_id,
        decision_cutoff=decision_cutoff,
    )


class PaperCheckpointCatalogueLookupWidget(QWidget):
    """兩階段 exact Paper 查找；不列舉帳戶、不自動選取、不建立帳戶。"""

    def __init__(
        self,
        *,
        account_service: Any,
        performance_reader: Any,
        performance_card: Any,
        disabled_reason: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.account_service = account_service
        self.performance_reader = performance_reader
        self.performance_card = performance_card
        self._closed = False
        self._request_id = 0
        self.worker = None
        self._catalogue: StrategyPaperAccountCheckpointCatalogue | None = None
        self._selected_row: StrategyPaperAccountCheckpointCandidate | None = None
        self._selector: PaperCheckpointSelector | None = None
        self._card_generation: int | None = None
        self._rendering_rows = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.strategy_id = QLineEdit(self)
        self.strategy_id.setPlaceholderText("必填；不會自動猜測策略")
        self.strategy_version_id = QLineEdit(self)
        self.strategy_version_id.setPlaceholderText("必填；不會取最新版本")
        self.account_namespace = QLineEdit(self)
        self.account_namespace.setPlaceholderText("必填；不會掃描或列舉帳戶")
        self.decision_cutoff = QLineEdit(self)
        self.decision_cutoff.setPlaceholderText("必填 ISO 時間，例：2026-08-01T09:00:00+08:00")
        for name, control in (
            ("策略識別", self.strategy_id),
            ("策略版本識別", self.strategy_version_id),
            ("Paper 帳戶命名空間", self.account_namespace),
            ("決策截止時間", self.decision_cutoff),
        ):
            control.setAccessibleName(name)
            form.addRow(name, control)
            control.textEdited.connect(self._inputs_changed)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.discover_button = QPushButton("列出此帳戶的保存快照")
        self.discover_button.clicked.connect(self.refresh_catalogue)
        self.cancel_button = QPushButton("取消／清除選取")
        self.cancel_button.clicked.connect(self.cancel_pending)
        self.read_button = QPushButton("讀取所選 exact 快照")
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self.read_selected_checkpoint)
        actions.addWidget(self.discover_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.read_button)
        layout.addLayout(actions)

        self.rows = QListWidget(self)
        self.rows.setAccessibleName("Paper 保存快照候選；最多顯示 200 列")
        self.rows.currentItemChanged.connect(self._candidate_changed)
        layout.addWidget(self.rows)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setAccessibleName("Paper 快照查找狀態")
        layout.addWidget(self.status)

        for control in (
            self.strategy_id,
            self.strategy_version_id,
            self.account_namespace,
            self.decision_cutoff,
        ):
            control.setEnabled(account_service is not None)
        self.discover_button.setEnabled(account_service is not None)
        self.cancel_button.setEnabled(account_service is not None)
        if account_service is None:
            self.status.setText(
                disabled_reason
                or "Paper 快照查找未啟用；需 PERSONAL 帳戶及明示外部合約根。"
            )
        else:
            self.status.setText(
                "請輸入策略、版本、帳戶命名空間與時區感知截止時間，再明示列出候選。"
                "清單最多 200 筆；截斷時不代表完整歷史。"
            )

    def _inputs_changed(self, *_args: object) -> None:
        self._invalidate(clear_rows=True, message="查詢條件已變更；舊候選與快照卡已清除。")

    def _invalidate(
        self, *, clear_rows: bool, message: str, close_card: bool = True
    ) -> None:
        self._request_id += 1
        if self.worker is not None:
            self.worker.cancel(cooperative=True, wait=False)
        self._catalogue = None
        self._selected_row = None
        self._selector = None
        self._card_generation = None
        self.read_button.setEnabled(False)
        if clear_rows:
            self.rows.clear()
        if close_card and self.performance_card is not None:
            self.performance_card.clear_selection()
        if not self._closed:
            self.status.setText(message)

    def _query_values(self) -> tuple[str, str, str, datetime]:
        strategy_id = self.strategy_id.text().strip()
        version_id = self.strategy_version_id.text().strip()
        namespace = self.account_namespace.text().strip()
        if not strategy_id or not version_id or not namespace:
            raise ValueError("策略、版本與帳戶命名空間都必須由使用者明示。")
        cutoff = parse_explicit_aware_cutoff(self.decision_cutoff.text())
        return strategy_id, version_id, namespace, cutoff

    def refresh_catalogue(self) -> None:
        if self._closed or self.worker is not None or self.account_service is None:
            return
        self._invalidate(clear_rows=True, message="正在讀取明示帳戶的有限候選清單…")
        try:
            strategy_id, version_id, namespace, cutoff = self._query_values()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        token = self._request_id

        def task(cancel_callback):
            if cancel_callback() or self._closed:
                return None
            catalogue = list_strategy_paper_account_checkpoint_candidates(
                self.account_service,
                strategy_id=strategy_id,
                strategy_version_id=version_id,
                account_namespace=namespace,
                decision_cutoff=cutoff,
            )
            if cancel_callback() or self._closed:
                return None
            return catalogue

        self._start_worker(
            task,
            lambda value: self._apply_catalogue(
                token, value, strategy_id, version_id, namespace, cutoff
            ),
            token=token,
        )

    def _apply_catalogue(
        self,
        token: int,
        catalogue: object,
        strategy_id: str,
        version_id: str,
        namespace: str,
        cutoff: datetime,
    ) -> None:
        if self._closed or token != self._request_id or catalogue is None:
            return
        if type(catalogue) is not StrategyPaperAccountCheckpointCatalogue:
            self._invalidate(clear_rows=True, message="候選清單格式未知，已拒絕呈現。")
            return
        if not (
            catalogue.strategy_id == strategy_id
            and catalogue.strategy_version_id == version_id
            and catalogue.account_namespace == namespace
            and catalogue.decision_cutoff == cutoff
            and len(catalogue.rows) <= 200
            and catalogue.checkpoint_verified is False
            and catalogue.performance_eligible is False
        ):
            self._invalidate(clear_rows=True, message="候選清單與明示查詢身份不一致。")
            return
        self._catalogue = catalogue
        self._rendering_rows = True
        try:
            self.rows.clear()
            for row in catalogue.rows:
                if type(row) is not StrategyPaperAccountCheckpointCandidate:
                    self._invalidate(clear_rows=True, message="候選列格式未知，清單已清除。")
                    return
                label = (
                    f"{row.operation_id} ｜ {row.snapshot_id} ｜ {row.row_state} ｜ "
                    f"persisted={row.persisted_at_text or '未提供'} ｜ "
                    f"available={row.available_at_text or '未提供'}"
                )
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, row)
                item.setToolTip(
                    "此列需使用者明示讀取 exact 快照；阻擋原因顯示於狀態區。"
                )
                self.rows.addItem(item)
        finally:
            self._rendering_rows = False
        binding = f"portfolio={catalogue.portfolio_id}; binding={catalogue.binding_sha256}"
        truncation = "清單已截斷；此列不代表完整歷史。" if catalogue.truncated else "清單未達截斷上限。"
        self.status.setText(
            f"載入 {len(catalogue.rows)} 列；{binding}；{truncation}"
            "候選尚未驗證，不代表績效資格。請明示選取一列後再讀取。"
        )

    def _candidate_changed(self, current: QListWidgetItem | None, *_args: object) -> None:
        if self._closed:
            return
        if not self._rendering_rows:
            # 使用者換選一律廢止舊回覆，即使原 worker 尚待回收。
            self._request_id += 1
            if self.worker is not None:
                self.worker.cancel(cooperative=True, wait=False)
        row = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self._selected_row = (
            row if type(row) is StrategyPaperAccountCheckpointCandidate else None
        )
        self._selector = None
        self._card_generation = None
        if self.performance_card is not None:
            self.performance_card.clear_selection()
        self.read_button.setEnabled(
            self._selected_row is not None
            and self._selected_row.row_state == "candidate_pending_exact_reader"
            and not self._selected_row.blockers
            and self._catalogue is not None
            and self._catalogue.checkpoint_verified is False
            and self._catalogue.performance_eligible is False
            and self.worker is None
        )
        if self._selected_row is not None and self._selected_row.row_state == "blocked":
            self.status.setText(
                "此列有阻擋原因，不能送入 exact reader："
                + "；".join(self._selected_row.blockers)
            )

    def read_selected_checkpoint(self) -> None:
        if self._closed or self.worker is not None or self.performance_reader is None:
            return
        row = self._selected_row
        catalogue = self._catalogue
        if (
            row is None
            or catalogue is None
            or row.row_state != "candidate_pending_exact_reader"
            or row.blockers
            or row.checkpoint_verified is not False
            or row.performance_eligible is not False
        ):
            self._invalidate(clear_rows=False, message="所選列不是可送入 exact reader 的候選。")
            return
        try:
            strategy_id, version_id, namespace, cutoff = self._query_values()
            selector = build_exact_selector(
                strategy_id=strategy_id,
                strategy_version_id=version_id,
                account_namespace=namespace,
                decision_cutoff=cutoff,
                catalogue=catalogue,
                candidate=row,
            )
        except (ValueError, StrategyPaperAccountAvailabilityError) as exc:
            self._invalidate(clear_rows=False, message=f"無法安全讀取所選快照：{exc}")
            return

        self._request_id += 1
        token = self._request_id
        self._selector = selector
        self._card_generation = self.performance_card.begin_selection(selector)
        card_generation = self._card_generation
        self.read_button.setEnabled(False)

        def task(cancel_callback):
            if cancel_callback() or self._closed:
                return None
            card = self.performance_reader.read_paper_checkpoint(selector)
            if cancel_callback() or self._closed:
                return None
            return card

        self.status.setText("正在讀取使用者所選 operation／snapshot；不建立或更新資料。")
        self._start_worker(
            task,
            lambda card: self._apply_card(token, card_generation, card),
            token=token,
        )

    def _apply_card(self, token: int, card_generation: int, card: object) -> None:
        if self._closed or token != self._request_id or card is None:
            return
        if self.performance_card is None:
            self.status.setText("exact reader 回覆與目前選取不符；快照卡保持清空。")
            return
        accepted = self.performance_card.present_card(card_generation, card)
        if type(card) is PaperCheckpointCard and card.read_status is ReadStatus.BLOCKED:
            self.status.setText("所選保存快照被 exact reader 阻擋；未呈現部分資料。")
        elif not accepted:
            self.status.setText("exact reader 回覆與目前選取不符；快照卡保持清空。")
        elif type(card) is PaperCheckpointCard and card.read_status is ReadStatus.VERIFIED:
            self.status.setText(
                "已讀取所選保存快照；來源時間、期間曲線與績效資格仍未核定。"
            )
        else:
            self.status.setText("exact reader 回傳狀態未知；快照卡保持清空。")

    def _start_worker(self, task, apply, *, token: int) -> None:
        from ui_qt.workers.task_worker import TaskWorker

        if self._closed or self.worker is not None or token != self._request_id:
            return
        worker = TaskWorker(task)
        self.worker = worker
        self.discover_button.setEnabled(False)
        self.read_button.setEnabled(False)

        def finished(value):
            if (
                not self._closed
                and token == self._request_id
                and self.worker is worker
            ):
                try:
                    apply(value)
                except Exception as exc:  # 呈現失敗時清除候選與卡片
                    self._invalidate(clear_rows=True, message=f"Paper 唯讀呈現失敗：{exc}")

        def failed(message):
            if (
                not self._closed
                and token == self._request_id
                and self.worker is worker
            ):
                self._invalidate(clear_rows=True, message=f"Paper 唯讀來源讀取失敗：{message}")

        def cleanup():
            active_worker = self.worker is worker
            if active_worker:
                self.worker = None
                self.discover_button.setEnabled(
                    self.account_service is not None and not self._closed
                )
                row = self._selected_row
                self.read_button.setEnabled(
                    not self._closed
                    and row is not None
                    and row.row_state == "candidate_pending_exact_reader"
                    and not row.blockers
                    and row.checkpoint_verified is False
                    and row.performance_eligible is False
                    and self._catalogue is not None
                )
            worker.deleteLater()

        worker.finished.connect(finished)
        worker.error.connect(failed)
        worker.native_thread_finished.connect(cleanup)
        worker.start()

    def cancel_pending(self) -> None:
        self._invalidate(clear_rows=True, message="Paper 查找已取消；候選與快照卡已清除。")

    def on_group_toggled(self, checked: bool) -> None:
        if not checked:
            self.cancel_pending()

    def begin_shutdown(self) -> None:
        self._closed = True
        self._invalidate(clear_rows=True, message="Paper 查找已隨研究工作區關閉。")

    def closeEvent(self, event) -> None:
        self.begin_shutdown()
        super().closeEvent(event)

