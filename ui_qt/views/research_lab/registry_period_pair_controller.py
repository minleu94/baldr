"""既有 Backtest Registry 的雙 exact run 唯讀背景接線。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QWidget,
)

from app_module.exceptions import BacktestCancelledError
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.portfolio_result_reader import RecommendationPortfolioResultReader
from app_module.recommendation_portfolio_full_period_pair_v1 import (
    FullPeriodPairReadCancelledV1, FullPeriodPairReadV1,
    RecommendationPortfolioFullPeriodPairReadServiceV1,
)
from app_module.recommendation_portfolio_period_calendar_read_pin_v1 import (
    PortfolioPeriodCalendarDailyReadPinV1, PortfolioPeriodCalendarReadPinV1,
    PortfolioPeriodDailyCalendarIdentityV1,
)
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.saved_strategy_rule_card import metadata_sha256
from ui_qt.views.research_lab.run_registry_compare_widget import RunRegistryCompareWidget
from ui_qt.workers.task_worker import TaskWorker


@dataclass(frozen=True, slots=True)
class _PairRequest:
    token: int
    generation: int
    left_id: str
    right_id: str
    left_sha: str
    right_sha: str
    calendar: PortfolioPeriodCalendarReadPinV1 | PortfolioPeriodCalendarDailyReadPinV1


class RegistryPeriodPairController(QObject):
    """保留 worker 至 native finished，拒絕選取、來源或研究世代過期的結果。"""

    def __init__(
        self, service: Any, config: Any, widget: RunRegistryCompareWidget,
        generation: Callable[[], int], *, parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._config = config
        self._widget = widget
        self._generation = generation
        self._token = 0
        self._closed = False
        self.worker: TaskWorker | None = None
        self._request: _PairRequest | None = None
        self._pin: PortfolioPeriodCalendarReadPinV1 | PortfolioPeriodCalendarDailyReadPinV1 | None = None
        self._daily_acceptances: tuple[DailySourceUseAcceptance, DailySourceUseAcceptance] | None = None
        self._daily_acceptance_configuration_error = ""
        self._result: object = None
        self._error = ""
        self._cancelled = False
        self.calendar_controls = QGroupBox("完整期間日曆版本", parent)
        form = QFormLayout(self.calendar_controls)
        self.source_mode = QComboBox()
        self.source_mode.addItem("保存原件", "artifact")
        self.source_mode.addItem("每日批次", "daily")
        self.artifact_path = QLineEdit()
        self.artifact_path.setPlaceholderText("已保存的日曆原件絕對路徑")
        self.artifact_path.setAccessibleName("完整期間日曆原件路徑")
        self.external_sha = QLineEdit()
        self.external_sha.setMaxLength(64)
        self.external_sha.setPlaceholderText("保存收據的 SHA-256（64 碼小寫）")
        self.external_sha.setAccessibleName("日曆保存收據 SHA-256")
        self.market = QComboBox()
        self.market.addItem("請選擇市場", None)
        self.market.addItem("上市 TWSE", "twse")
        self.market.addItem("上櫃 TPEx", "tpex")
        self.apply_button = QPushButton("固定日曆版本")
        self.status = QLabel("輸入既有原件與保存收據，選取市場後固定版本；不會抓取或補算。")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        self._source_mode_label = QLabel("來源模式", self.calendar_controls)
        self._artifact_label = QLabel("原件", self.calendar_controls)
        self._external_sha_label = QLabel("保存收據 SHA-256", self.calendar_controls)
        self._receipt_sha_label = QLabel("成功收據 SHA-256", self.calendar_controls)
        self.receipt_sha = QLineEdit()
        self.receipt_sha.setMaxLength(64)
        self.receipt_sha.setPlaceholderText("每日批次成功收據 SHA-256（64 碼小寫）")
        self.receipt_sha.setAccessibleName("每日批次成功收據 SHA-256")
        self._market_label = QLabel("市場", self.calendar_controls)
        self._acceptance_label = QLabel("每日用途接受", self.calendar_controls)
        self.acceptance_status = QLabel("尚未配置每日來源用途接受錨點。", self.calendar_controls)
        self.acceptance_status.setWordWrap(True)
        self.acceptance_status.setTextFormat(Qt.PlainText)
        form.addRow(self._source_mode_label, self.source_mode)
        form.addRow(self._artifact_label, self.artifact_path)
        form.addRow(self._external_sha_label, self.external_sha)
        form.addRow(self._receipt_sha_label, self.receipt_sha)
        form.addRow(self._market_label, self.market)
        form.addRow(self._acceptance_label, self.acceptance_status)
        form.addRow(self.apply_button)
        form.addRow(self.status)
        self.source_mode.currentIndexChanged.connect(self._source_mode_changed)
        self.artifact_path.textChanged.connect(self.invalidate_calendar)
        self.external_sha.textChanged.connect(self.invalidate_calendar)
        self.receipt_sha.textChanged.connect(self.invalidate_calendar)
        self.market.currentIndexChanged.connect(self.invalidate_calendar)
        self.apply_button.clicked.connect(self.apply_calendar)
        widget.on_compare_period_pair = self.compare
        widget.on_period_pair_selection_changed = self.selection_changed
        widget.on_cancel_period_pair = self.cancel
        self._render_source_mode()
        self._availability()

    def _availability(self) -> None:
        if self._closed:
            enabled, reason = False, "此研究視窗已關閉。"
        elif self._pin is not None:
            enabled, reason = True, ""
        elif self.source_mode.currentData() == "daily" and self._daily_acceptance_configuration_error:
            enabled, reason = False, (
                "來源用途接受設定無法讀取：" + self._daily_acceptance_configuration_error
            )
        elif self.source_mode.currentData() == "daily" and self._daily_acceptances is None:
            enabled, reason = False, "每日批次比較尚未配置 TWSE 與 TPEx 獨立來源用途接受紀錄。"
        else:
            enabled, reason = False, "請先固定日曆來源、外部 SHA-256 與市場。"
        self._widget.set_period_pair_availability(
            enabled, reason,
        )

    def _render_source_mode(self) -> None:
        daily = self.source_mode.currentData() == "daily"
        if daily:
            self._artifact_label.setText("批次目錄")
            self.artifact_path.setPlaceholderText("完成批次目錄絕對路徑")
            self.artifact_path.setAccessibleName("日曆完成批次目錄")
            self._external_sha_label.setText("Manifest SHA-256")
            self.external_sha.setPlaceholderText("指定批次 manifest SHA-256（64 碼小寫）")
            self.external_sha.setAccessibleName("日曆批次 manifest SHA-256")
            self._receipt_sha_label.setVisible(True)
            self.receipt_sha.setVisible(True)
            self._acceptance_label.setVisible(True)
            self.acceptance_status.show()
            if self._daily_acceptance_configuration_error:
                self.acceptance_status.setText(
                    "來源用途接受設定無法讀取：" + self._daily_acceptance_configuration_error
                )
            elif self._daily_acceptances is None:
                self.acceptance_status.setText("缺少獨立用途接受錨點；每日批次比較會保持停用。")
            else:
                self.acceptance_status.setText(
                    "已配置獨立接受錨點："
                    + "、".join(item.acceptance_id for item in self._daily_acceptances)
                )
        else:
            self._artifact_label.setText("原件")
            self.artifact_path.setPlaceholderText("已保存的日曆原件絕對路徑")
            self.artifact_path.setAccessibleName("完整期間日曆原件路徑")
            self._external_sha_label.setText("保存收據 SHA-256")
            self.external_sha.setPlaceholderText("保存收據的 SHA-256（64 碼小寫）")
            self.external_sha.setAccessibleName("日曆保存收據 SHA-256")
            self._receipt_sha_label.hide()
            self.receipt_sha.hide()
            self._acceptance_label.hide()
            self.acceptance_status.hide()

    def _source_mode_changed(self, *_: object) -> None:
        self._render_source_mode()
        self.invalidate_calendar()

    def set_daily_acceptances(
        self,
        anchors: tuple[DailySourceUseAcceptance, DailySourceUseAcceptance] | None,
        *,
        configuration_error: str = "",
    ) -> None:
        if anchors is not None and (
            type(anchors) is not tuple or len(anchors) != 2
            or any(type(item) is not DailySourceUseAcceptance for item in anchors)
        ):
            raise TypeError("每日用途接受錨點必須是兩個明示的 DailySourceUseAcceptance")
        if type(configuration_error) is not str:
            raise TypeError("每日用途接受配置錯誤原因必須是字串")
        if len(configuration_error) > 512:
            raise ValueError("每日用途接受配置錯誤原因不可超過512字")
        if anchors is not None and configuration_error:
            raise ValueError("每日用途接受錨點與配置錯誤原因不可同時提供")
        if (anchors == self._daily_acceptances
                and configuration_error == self._daily_acceptance_configuration_error):
            return
        self._daily_acceptances = anchors
        self._daily_acceptance_configuration_error = configuration_error
        self._render_source_mode()
        self.invalidate_calendar()

    def _invalidate(self) -> None:
        self._token += 1
        if self.worker is not None:
            self.worker.cancel(cooperative=True, wait=False)
        self._widget.clear_period_pair_result()
        self.status.setText("選取、日曆或研究狀態已變更，舊配對結果已清除。")

    def selection_changed(self) -> None:
        self._invalidate()
        self._availability()

    def invalidate_calendar(self, *_: object) -> None:
        self._pin = None
        self._invalidate()
        self.status.setText("日曆輸入已變更，請重新固定版本。")
        self._availability()

    def apply_calendar(self) -> None:
        if self._closed:
            return
        self._invalidate()
        self._pin = None
        try:
            roots = tuple(
                Path(value) for name in (
                    "data_root", "output_root", "personal_data_root",
                    "personal_store_root", "personal_journal_root",
                ) if (value := getattr(self._config, name, None)) is not None
            )
            if self.source_mode.currentData() == "artifact":
                # 只接受外部保存收據；此處不讀檔、不對當前 bytes 自行產生 SHA。
                self._pin = PortfolioPeriodCalendarReadPinV1(
                    artifact_path=Path(self.artifact_path.text().strip()),
                    expected_sha256=self.external_sha.text().strip(),
                    market=self.market.currentData(), protected_roots=roots,
                )
            elif self.source_mode.currentData() == "daily":
                if self._daily_acceptance_configuration_error:
                    raise ValueError(
                        "來源用途接受設定無法讀取：" + self._daily_acceptance_configuration_error
                    )
                if self._daily_acceptances is None:
                    raise ValueError("缺少 TWSE 與 TPEx 獨立來源用途接受紀錄")
                cutoff = datetime.now(timezone.utc)
                self._pin = PortfolioPeriodCalendarDailyReadPinV1(
                    batch_directory=Path(self.artifact_path.text().strip()),
                    expected_manifest_sha256=self.external_sha.text().strip(),
                    expected_receipt_sha256=self.receipt_sha.text().strip(),
                    market=self.market.currentData(), protected_roots=roots,
                    trusted_acceptances=self._daily_acceptances, decision_cutoff=cutoff,
                )
            else:
                raise ValueError("日曆來源模式未知")
        except (TypeError, ValueError) as exc:
            self.status.setText(f"無法固定日曆版本：{exc}")
        else:
            if type(self._pin) is PortfolioPeriodCalendarDailyReadPinV1:
                self.status.setText("每日批次與雙外部 SHA 已固定；比較仍為候選診斷，不具績效或歷史 PIT 資格。")
            else:
                self.status.setText("日曆版本已固定；比較時核對原件。候選來源仍不具績效或歷史 PIT 資格。")
        self._availability()

    def compare(self, left: ResearchRunMetadataDTO, right: ResearchRunMetadataDTO) -> None:
        if self._closed or self._pin is None or self.worker is not None:
            # 葉片已送出 pending；拒絕後必須恢復其狀態。
            self._widget.set_period_pair_busy(self.worker is not None)
            self._availability()
            return
        if (
            left.run_type != "recommendation_portfolio"
            or right.run_type != "recommendation_portfolio"
            or left.run_id == right.run_id
            or self._widget.selected_run_ids() != [left.run_id, right.run_id]
        ):
            self._widget.set_period_pair_busy(False)
            self.status.setText("所選兩筆推薦回放已變更，請重新選取。")
            return
        self._token += 1
        request = _PairRequest(
            self._token, self._generation(), left.run_id, right.run_id,
            metadata_sha256(left), metadata_sha256(right), self._pin,
        )
        self._request = request
        self._result, self._error, self._cancelled = None, "", False
        worker = TaskWorker(self._read_pair, request)
        self.worker = worker
        worker.finished.connect(self._received, Qt.QueuedConnection)
        worker.error.connect(self._failed, Qt.QueuedConnection)
        worker.cancelled.connect(self._was_cancelled, Qt.QueuedConnection)
        worker.native_thread_finished.connect(self._native_finished, Qt.QueuedConnection)
        self._widget.set_period_pair_busy(True)
        self.status.setText("核對兩筆保存結果與指定日曆中…")
        try:
            worker.start()
        except Exception:
            self.worker, self._request = None, None
            self._widget.set_period_pair_busy(False)
            worker.deleteLater()
            raise

    def _read_pair(self, request: _PairRequest, *, cancel_callback: Callable[[], bool]) -> FullPeriodPairReadV1:
        if cancel_callback():
            raise BacktestCancelledError("完整期間讀取已取消")
        composition = build_recommendation_composition(self._config)
        reader = RecommendationPortfolioResultReader(self._service, composition.persistence)
        pair_reader = RecommendationPortfolioFullPeriodPairReadServiceV1(self._service, reader)
        try:
            if type(request.calendar) is PortfolioPeriodCalendarReadPinV1:
                return pair_reader.read(
                    request.left_id, request.right_id,
                    calendar_path=request.calendar.artifact_path,
                    expected_calendar_sha256=request.calendar.expected_sha256,
                    market=request.calendar.market, protected_roots=request.calendar.protected_roots,
                    expected_left_metadata_sha256=request.left_sha,
                    expected_right_metadata_sha256=request.right_sha,
                    check_cancel=cancel_callback,
                )
            if type(request.calendar) is PortfolioPeriodCalendarDailyReadPinV1:
                return pair_reader.read_daily(
                    request.left_id, request.right_id, calendar_pin=request.calendar,
                    expected_left_metadata_sha256=request.left_sha,
                    expected_right_metadata_sha256=request.right_sha,
                    check_cancel=cancel_callback,
                )
            raise ValueError("完整期間日曆 pin 型別未知")
        except FullPeriodPairReadCancelledV1 as exc:
            raise BacktestCancelledError("完整期間讀取已取消") from exc

    @Slot(object)
    def _received(self, result: object) -> None:
        if self.sender() is self.worker:
            self._result = result

    @Slot(str)
    def _failed(self, error: str) -> None:
        if self.sender() is self.worker:
            self._error = error

    @Slot()
    def _was_cancelled(self) -> None:
        if self.sender() is self.worker:
            self._cancelled = True

    def _is_current(self, request: _PairRequest) -> bool:
        return (
            not self._closed and request.token == self._token
            and request.generation == self._generation() and request.calendar == self._pin
            and self._widget.selected_run_ids() == [request.left_id, request.right_id]
        )

    @Slot()
    def _native_finished(self) -> None:
        worker = self.sender()
        if worker is not self.worker:
            return
        request = self._request
        self.worker, self._request = None, None
        try:
            self._widget.set_period_pair_busy(False)
            if request is None or not self._is_current(request):
                return
            if self._error:
                self.status.setText("完整期間讀取失敗，未套用部分結果：" + self._error.splitlines()[0])
                return
            if self._cancelled or worker.is_cancel_requested():
                self.status.setText("完整期間讀取已取消，未套用部分結果。")
                return
            result = self._result
            if type(result) is not FullPeriodPairReadV1:
                raise ValueError("讀回型別不是完整期間配對")
            if type(request.calendar) is PortfolioPeriodCalendarReadPinV1:
                if (
                    result.daily_calendar_source is not None
                    or result.calendar_external_sha256 != request.calendar.expected_sha256
                    or result.market != request.calendar.market
                ):
                    raise ValueError("配對日曆版本、市場或來源模式與選取不符")
            elif type(request.calendar) is PortfolioPeriodCalendarDailyReadPinV1:
                identity = result.daily_calendar_source
                if type(identity) is not PortfolioPeriodDailyCalendarIdentityV1:
                    raise ValueError("每日批次結果缺少精確來源身份")
                if (
                    result.calendar_external_sha256 != request.calendar.expected_manifest_sha256
                    or result.market != request.calendar.market
                    or identity.batch_id != request.calendar.batch_directory.name
                    or identity.manifest_sha256 != request.calendar.expected_manifest_sha256
                    or identity.receipt_sha256 != request.calendar.expected_receipt_sha256
                    or identity.acceptance_ids != tuple(
                        item.acceptance_id for item in request.calendar.trusted_acceptances
                    )
                    or identity.decision_cutoff != request.calendar.decision_cutoff.isoformat()
                ):
                    raise ValueError("每日批次來源身份與固定 pin 不符")
            else:
                raise ValueError("完整期間日曆 pin 型別未知")
            for run_id, expected_sha in (
                (request.left_id, request.left_sha), (request.right_id, request.right_sha),
            ):
                current = self._service.repository.get_metadata(run_id)
                if current is None or metadata_sha256(current) != expected_sha:
                    raise ValueError("結果排入畫面前，Registry metadata 已變更")
            self._widget.set_period_pair_result(result)
            self.status.setText("已讀回指定兩筆 run；來源資格與日期缺件請見診斷，未建立可排名績效。")
        except Exception as exc:
            self._widget.clear_period_pair_result()
            self.status.setText(f"完整期間結果未套用：{exc}")
        finally:
            self._result, self._error = None, ""
            self._availability()
            worker.deleteLater()

    def cancel(self) -> None:
        # 旗標不更改 token，真實 integrity error 仍須呈現為失敗。
        if self.worker is not None:
            self.worker.cancel(cooperative=True, wait=False)

    def invalidate_execution(self) -> None:
        self._invalidate()
        self._availability()

    def begin_shutdown(self) -> None:
        self._closed = True
        self._pin = None
        self._invalidate()
        self._availability()
