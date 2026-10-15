"""固定法人批次的唯讀檢視控制項。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_module.institutional_daily_snapshot import (
    InstitutionalDailySnapshotPin,
    InstitutionalDailySnapshotRead,
)
from app_module.institutional_source_use import (
    InstitutionalSourceUsePin,
    InstitutionalSourceUseRead,
    TPEX_INSTITUTIONAL_USE_SCOPE,
)


_TAIPEI_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Taipei")
_METRIC_FIELDS = (
    "foreign_investor_buy",
    "foreign_investor_sell",
    "foreign_investor_net",
    "investment_trust_buy",
    "investment_trust_sell",
    "investment_trust_net",
    "dealer_buy",
    "dealer_sell",
    "dealer_net",
)
_TABLE_HEADERS = (
    "資料日",
    "代碼",
    "外陸資合計（含外資自營）買進股數",
    "外陸資合計（含外資自營）賣出股數",
    "外陸資合計（含外資自營）買賣超股數",
    "投信買進股數",
    "投信賣出股數",
    "投信買賣超股數",
    "自營商（自行＋避險）買進股數",
    "自營商（自行＋避險）賣出股數",
    "自營商（自行＋避險）買賣超股數",
)


class InstitutionalDailySnapshotWidget(QWidget):
    """讓使用者明確指定法人批次 pin，並以原始整數唯讀呈現。"""

    readRequested = Signal(object, str, int)
    cancelRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.generation = 0
        self._loading = False
        self.requested_source_use_pin: InstitutionalSourceUsePin | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(
            self._new_label("固定法人批次（TWSE／TPEx OpenAPI，唯讀）")
        )

        self.directory_edit = QLineEdit(self)
        self.directory_edit.setPlaceholderText("輸入固定批次目錄")
        self.manifest_sha_edit = QLineEdit(self)
        self.manifest_sha_edit.setPlaceholderText("輸入 manifest SHA-256")
        self.receipt_sha_edit = QLineEdit(self)
        self.receipt_sha_edit.setPlaceholderText("輸入 receipt SHA-256")
        self.stock_code_edit = QLineEdit("2330", self)
        self.stock_code_edit.setPlaceholderText("輸入股票代碼")
        self.source_use_path_edit = QLineEdit(self)
        self.source_use_path_edit.setPlaceholderText("source_use.json 絕對路徑")
        self.source_use_path_edit.setAccessibleName("TPEx 用途接受檔絕對路徑（選填）")
        self.source_use_path_edit.setToolTip(
            "選填；僅明選 TPEx diagnostics 用途接受檔，不授其他用途。"
        )
        self.source_use_sha_edit = QLineEdit(self)
        self.source_use_sha_edit.setPlaceholderText("外部 SHA-256（選填）")
        self.source_use_sha_edit.setAccessibleName("TPEx 用途接受檔外部 SHA-256（選填）")
        self.source_use_sha_edit.setToolTip(
            "與 source_use.json 路徑一併提供，使用外部小寫 SHA-256。"
        )

        self._add_labeled_edit(layout, "固定批次目錄", self.directory_edit)
        self._add_labeled_edit(layout, "Manifest SHA-256", self.manifest_sha_edit)
        self._add_labeled_edit(layout, "Receipt SHA-256", self.receipt_sha_edit)
        self._add_labeled_edit(layout, "股票代碼", self.stock_code_edit)
        layout.addWidget(self._new_label("TPEx 用途接受檔（選填；僅 diagnostics）"))
        source_use_inputs = QHBoxLayout()
        source_use_inputs.addWidget(self.source_use_path_edit, 2)
        source_use_inputs.addWidget(self.source_use_sha_edit, 1)
        layout.addLayout(source_use_inputs)

        buttons = QHBoxLayout()
        self.open_button = QPushButton("開啟指定批次", self)
        self.cancel_button = QPushButton("取消／清除結果", self)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.status_label = self._new_label(
            "尚未載入。請輸入批次目錄、雙 SHA 與股票代碼。"
        )
        self.identity_label = self._new_label("")
        layout.addWidget(self.status_label)
        layout.addWidget(self.identity_label)

        self.rows_table = QTableWidget(0, len(_TABLE_HEADERS), self)
        self.rows_table.setHorizontalHeaderLabels(list(_TABLE_HEADERS))
        self.rows_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.rows_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.rows_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rows_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.rows_table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.rows_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.rows_table.setMinimumHeight(220)
        layout.addWidget(self.rows_table, 1)

        self.open_button.clicked.connect(self._on_open_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        for edit in (
            self.directory_edit,
            self.manifest_sha_edit,
            self.receipt_sha_edit,
            self.stock_code_edit,
            self.source_use_path_edit,
            self.source_use_sha_edit,
        ):
            edit.textChanged.connect(self._on_input_changed)

    @staticmethod
    def _new_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        return label

    def _add_labeled_edit(
        self, layout: QVBoxLayout, title: str, edit: QLineEdit
    ) -> None:
        label = self._new_label(title)
        layout.addWidget(label)
        layout.addWidget(edit)

    def _on_input_changed(self, _text: str) -> None:
        self.generation += 1
        self.requested_source_use_pin = None
        self.clear_result()
        self.status_label.setText("輸入已變更；已送出取消舊讀取，請重新開啟指定批次。")
        self.cancelRequested.emit()

    def _on_cancel_clicked(self) -> None:
        self.generation += 1
        self.requested_source_use_pin = None
        self.clear_result()
        self.status_label.setText("已送出取消請求；等待讀取端回報完成。")
        self.cancelRequested.emit()

    def _on_open_clicked(self) -> None:
        if self._loading:
            return
        self.requested_source_use_pin = None

        directory_text = self.directory_edit.text()
        stock_code = self.stock_code_edit.text().strip()
        source_use_path = self.source_use_path_edit.text().strip()
        source_use_sha256 = self.source_use_sha_edit.text().strip()
        if not directory_text.strip():
            self.show_error("請輸入固定批次目錄。")
            return
        if not stock_code:
            self.show_error("請輸入股票代碼。")
            return
        if bool(source_use_path) != bool(source_use_sha256):
            self.show_error("用途接受檔路徑與外部 SHA 必須一併提供，或都留白。")
            return

        try:
            pin = InstitutionalDailySnapshotPin(
                directory=Path(directory_text),
                manifest_sha256=self.manifest_sha_edit.text().strip(),
                receipt_sha256=self.receipt_sha_edit.text().strip(),
            )
            source_use_pin = (
                InstitutionalSourceUsePin(
                    path=Path(source_use_path), sha256=source_use_sha256
                )
                if source_use_path
                else None
            )
        except Exception as exc:
            self.show_error(f"固定批次識別資料無效：{exc}")
            return

        self.requested_source_use_pin = source_use_pin
        self.status_label.setText("已送出指定批次讀取要求。")
        self.readRequested.emit(pin, stock_code, self.generation)

    def set_loading(self, loading: bool) -> None:
        self._loading = bool(loading)
        self.open_button.setEnabled(not self._loading)
        if self._loading:
            self.clear_result()
            self.status_label.setText("正在核驗同批原件、品質、時間與雙 SHA…")

    def show_result(self, result: InstitutionalDailySnapshotRead) -> None:
        self.clear_result()
        try:
            self._validate_result(result)
            display_rows: list[tuple[str, ...]] = []
            for row in result.rows:
                if row.stock_code != result.stock_code:
                    raise ValueError("結果列股票代碼與批次查詢代碼不一致。")
                date_value = row.decision_date
                display_date = (
                    date_value.isoformat()
                    if callable(getattr(date_value, "isoformat", None))
                    else str(date_value)
                )
                values = tuple(getattr(row, field) for field in _METRIC_FIELDS)
                if any(type(value) is not int for value in values):
                    raise ValueError("法人股數欄位不是原始整數，拒絕顯示。")
                display_rows.append(
                    (display_date, str(row.stock_code), *(str(value) for value in values))
                )

            identity = self._format_identity(result)
            self.rows_table.setRowCount(len(display_rows))
            for row_index, values in enumerate(display_rows):
                for column_index, value in enumerate(values):
                    self.rows_table.setItem(
                        row_index, column_index, QTableWidgetItem(value)
                    )
                source = result.rows[row_index]
                self.rows_table.item(row_index, 0).setToolTip(
                    f"原件 SHA：{source.raw_sha256}\n來源版本：{source.source_version}\n"
                    f"官方時間原文：{source.official_timestamp_original_text or '未提供，依成功批次時間'}\n"
                    f"官方時間（台北）：{source.official_timestamp or '未提供'}"
                )
            self.identity_label.setText(identity)
            if not display_rows:
                self.status_label.setText(
                    f"指定批次已載入；股票 {result.stock_code} 為 0 命中（這是已載入批次的查詢結果，不是未載入）。"
                )
            else:
                self.status_label.setText(
                    f"指定批次已載入；股票 {result.stock_code} 命中 {len(display_rows)} 筆，日期欄保留原始資料日。"
                )
        except Exception as exc:
            self.show_error(f"批次結果不符合唯讀顯示契約：{exc}")

    def _validate_result(self, result: InstitutionalDailySnapshotRead) -> None:
        if not isinstance(result, InstitutionalDailySnapshotRead):
            raise ValueError("結果型別不是固定法人批次讀取 DTO。")
        if result.market not in {"TWSE", "TPEx"}:
            raise ValueError("市場只能是 TWSE 或 TPEx。")
        if result.candidate_only is not True:
            raise ValueError("candidate_only 必須為 True。")
        if result.historical_pit_eligible is not False:
            raise ValueError("historical_pit_eligible 必須為 False。")
        source_use = getattr(result, "source_use", None)
        if result.source_use_accepted is True:
            if result.market != "TPEx":
                raise ValueError("來源用途接受只可呈現於 TPEx 結果。")
            if not isinstance(source_use, InstitutionalSourceUseRead):
                raise ValueError("source_use_accepted=True 必須有 typed 用途接受讀回。")
            if not isinstance(source_use.pin, InstitutionalSourceUsePin):
                raise ValueError("用途接受讀回缺少 typed 外部 pin。")
            acceptance = source_use.acceptance
            scope = getattr(acceptance, "scope", None)
            if scope != TPEX_INSTITUTIONAL_USE_SCOPE:
                raise ValueError("用途接受 scope 必須精確符合 TPEx diagnostics。")
            if scope.market != "TPEx" or scope.intended_use != "diagnostics":
                raise ValueError("用途接受只授 TPEx diagnostics。")
            if not isinstance(source_use.attribution, str) or not source_use.attribution.strip():
                raise ValueError("用途接受讀回缺少來源顯名。")
            self._require_aware_datetime(acceptance.accepted_at, "用途接受時間")
        elif result.source_use_accepted is False:
            if source_use is not None:
                raise ValueError("source_use存在時，source_use_accepted必須為 True。")
        else:
            raise ValueError("source_use_accepted 必須是布林值。")
        if not isinstance(result.rows, tuple):
            raise ValueError("rows 必須是固定批次的 tuple。")
        if type(result.total_records) is not int or result.total_records < 0:
            raise ValueError("total_records 必須是非負整數。")
        self._require_aware_datetime(result.first_persisted_at, "首次保存時間")
        self._require_aware_datetime(
            result.successful_batch_completed_at, "批次完成時間"
        )
        self._require_aware_datetime(result.available_hour, "台北可用小時")
        if not isinstance(result.availability_basis, str):
            raise ValueError("availability_basis 必須是文字。")
        if len(result.rows) > result.total_records:
            raise ValueError("股票命中筆數大於批次母體筆數。")
        if result.candidate_only is not True or result.historical_pit_eligible is not False:
            raise ValueError("這個入口只呈現候選事實，且不授歷史 PIT 資格。")

    @staticmethod
    def _require_aware_datetime(value: datetime, title: str) -> None:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError(f"{title}必須是含時區的 datetime。")
        if value.utcoffset() is None:
            raise ValueError(f"{title}的時區資訊無效。")

    @staticmethod
    def _format_identity(result: InstitutionalDailySnapshotRead) -> str:
        pin = result.pin
        first_saved = result.first_persisted_at.astimezone(_TAIPEI_TIMEZONE).isoformat()
        completed = result.successful_batch_completed_at.astimezone(
            _TAIPEI_TIMEZONE
        ).isoformat()
        available = result.available_hour.astimezone(_TAIPEI_TIMEZONE).isoformat()
        source_use_text = ""
        if result.source_use_accepted is True:
            source_use = result.source_use
            acceptance = source_use.acceptance
            accepted_at = acceptance.accepted_at.astimezone(
                _TAIPEI_TIMEZONE
            ).isoformat()
            source_use_text = (
                f"TPEx diagnostics 用途接受 ID：{acceptance.acceptance_id}\n"
                f"用途接受檔 SHA-256：{source_use.pin.sha256}\n"
                f"用途接受時間（台北）：{accepted_at}\n"
                f"接受來源：{source_use.attribution}\n"
            )
            usage_limits = (
                "用途限制：候選資料；用途接受僅授 TPEx diagnostics，不代表正式來源接受或 P0 整桶接受；"
                "不具歷史 PIT 資格，不得用於連買判斷、評分或交易。"
            )
        else:
            usage_limits = (
                "用途限制：候選資料；尚未載入合格用途接受，不具歷史 PIT 資格；"
                "不得用於連買判斷、評分或交易。"
            )
        return (
            f"市場：{result.market}\n"
            f"Manifest SHA-256：{pin.manifest_sha256}\n"
            f"Receipt SHA-256：{pin.receipt_sha256}\n"
            f"股票代碼：{result.stock_code}；批次母體筆數：{result.total_records}；"
            f"該股命中：{len(result.rows)} 筆\n"
            f"本成功版本首次保存（台北）：{first_saved}\n"
            f"成功批次完成（台北）：{completed}\n"
            f"台北可用小時：{available}\n"
            f"可用性依據：{result.availability_basis}\n"
            f"{source_use_text}"
            "每列資料日的提示保留該版官方時間原文、台北時間及原件 SHA。\n"
            f"{usage_limits}"
        )

    def show_error(self, message: str) -> None:
        self.clear_result()
        self.status_label.setText(str(message))

    def clear_result(self) -> None:
        self.rows_table.setRowCount(0)
        self.identity_label.clear()
        self.status_label.setText("尚未載入。請輸入批次目錄、雙 SHA 與股票代碼。")
