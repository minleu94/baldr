"""
強勢個股視圖
顯示強勢股票列表
"""

from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableView, QHeaderView, QMessageBox, QSizePolicy, QLineEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import pandas as pd
from typing import Any, Optional

from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.workers.task_worker import TaskWorker
from app_module.screening_service import ScreeningService
from app_module.watchlist_service import WatchlistService
from ui_qt.widgets.info_button import InfoButton
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.widgets.layout_helpers import create_scroll_area, ensure_visible_rows
from ui_qt.shared_market_research_consumer import SharedStockResearchMixin


def _load_strong_stock_screening_result(
    screening_service: ScreeningService,
    period: str,
) -> tuple[Any, date | None]:
    """只在 worker 執行緒讀取強勢股來源並回傳 DTO 資料日。"""

    dto_method = getattr(screening_service, "get_strong_stocks_dto", None)
    if callable(dto_method):
        screening_dto = dto_method(period=period, top_n=50)
        effective_date = getattr(screening_dto, "effective_date", None)
        return screening_dto.to_legacy(), effective_date
    return (
        screening_service.get_strong_stocks(period=period, top_n=50),
        None,
    )


class StrongStocksView(SharedStockResearchMixin, QWidget):
    """強勢個股視圖"""

    _shared_direction = "strong"
    
    def __init__(self, screening_service: ScreeningService, watchlist_service: WatchlistService = None, parent=None):
        """初始化強勢個股視圖
        
        Args:
            screening_service: 篩選服務實例
            watchlist_service: 觀察清單服務實例（可選）
            parent: 父窗口
        """
        super().__init__(parent)
        self.screening_service = screening_service
        self.watchlist_service = watchlist_service
        
        # 數據模型
        self.stocks_model: Optional[PandasTableModel] = None
        
        # 數據緩存（避免重複計算）
        self._cached_data = {
            'day': None,  # 緩存本日的數據
            'week': None  # 緩存本周的數據
        }
        self._cached_effective_dates: dict[str, date | None] = {
            'day': None,
            'week': None,
        }
        self._cached_universe_counts: dict[str, int] = {
            'day': 0,
            'week': 0,
        }
        self._screening_request_id = 0
        self._screening_worker: TaskWorker | None = None
        self._retired_screening_workers: list[TaskWorker] = []
        self._screening_view_closing = False
        self._search_result_loaded = False
        
        self._setup_ui()
        self.init_shared_research_consumer()
        # 不自動計算，等待用戶點擊「載入數據」按鈕或切換到這個 tab
        self._show_empty_state()
    
    def _setup_ui(self):
        """設置 UI"""
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_content = QWidget()
        main_layout = QVBoxLayout(page_content)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 標題列（標題 + InfoButton）
        title_layout = QHBoxLayout()
        title = QLabel("強勢個股")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        title_layout.addStretch()
        info_btn = InfoButton("strong_stocks", self)
        title_layout.addWidget(info_btn)
        main_layout.addLayout(title_layout)
        
        # 控制欄
        controls_widget = QWidget()
        control_layout = QHBoxLayout(controls_widget)
        
        # 時間範圍選擇
        control_layout.addWidget(QLabel("時間範圍:"))
        self.period_btn_day = QPushButton("本日")
        self.period_btn_week = QPushButton("本周")
        self.period_btn_day.setCheckable(True)
        self.period_btn_week.setCheckable(True)
        self.period_btn_day.setChecked(True)
        self.period_btn_day.clicked.connect(lambda: self._on_period_changed('day'))
        self.period_btn_week.clicked.connect(lambda: self._on_period_changed('week'))
        control_layout.addWidget(self.period_btn_day)
        control_layout.addWidget(self.period_btn_week)
        self.setup_shared_research_controls(control_layout)
        
        control_layout.addStretch()
        
        # Universe 顯示標籤
        self.universe_label = QLabel("Universe: -")
        self.universe_label.setStyleSheet("color: #666; font-size: 10px;")
        control_layout.addWidget(self.universe_label)
        
        # 加入觀察清單按鈕（僅在有數據時顯示）
        self.add_to_watchlist_btn = QPushButton("加入觀察清單")
        self.add_to_watchlist_btn.setVisible(False)  # 初始隱藏
        self.add_to_watchlist_btn.clicked.connect(self._add_selected_to_watchlist)
        if self.watchlist_service:
            control_layout.addWidget(self.add_to_watchlist_btn)
        
        # 載入數據按鈕（首次載入或強制重新計算）
        self.load_btn = QPushButton("載入數據")
        self.load_btn.setProperty("variant", "primary")
        self.load_btn.clicked.connect(lambda: self._refresh_stocks(use_cache=False))
        control_layout.addWidget(self.load_btn)
        
        # 刷新按鈕（強制重新計算，僅在有數據時顯示）
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setVisible(False)  # 初始隱藏
        self.refresh_btn.clicked.connect(lambda: self._refresh_stocks(use_cache=False))
        control_layout.addWidget(self.refresh_btn)
        
        self.controls_scroll_area = create_scroll_area(
            controls_widget,
            object_name="strongStocksControlsScrollArea",
            horizontal_scroll=True,
        )
        self.controls_scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.controls_scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        main_layout.addWidget(self.controls_scroll_area)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜尋目前清單："))
        self.stocks_search_input = QLineEdit()
        self.stocks_search_input.setPlaceholderText("股票代碼或名稱")
        self.stocks_search_input.setAccessibleName("強勢個股目前清單搜尋")
        self.stocks_search_input.setClearButtonEnabled(True)
        self.stocks_search_input.setMaximumWidth(260)
        self.stocks_search_input.textChanged.connect(self._on_stocks_search_changed)
        self._set_stocks_search_mode_hint()
        search_layout.addWidget(self.stocks_search_input)

        self.stocks_search_count_label = QLabel("尚未載入")
        self.stocks_search_count_label.setAccessibleName("強勢個股目前清單搜尋筆數")
        self.stocks_search_count_label.setAccessibleDescription(
            "顯示目前已載入強勢個股清單中符合搜尋的股票筆數；不代表市場完整母體。"
        )
        self.stocks_search_count_label.setToolTip(
            "只統計目前已載入主表的列，不代表市場完整母體。"
        )
        self.stocks_search_count_label.setStyleSheet("color: #94a3b8; margin-left: 4px;")
        search_layout.addWidget(self.stocks_search_count_label)
        search_layout.addStretch()
        main_layout.addLayout(search_layout)
        main_layout.addWidget(self.source_scope_label)
        
        # 表格
        self.stocks_table = QTableView()
        self.stocks_table.doubleClicked.connect(lambda _index: self.open_shared_selected_stock())
        apply_financial_table_style(self.stocks_table)
        self.stocks_table.setSelectionBehavior(QTableView.SelectRows)
        self.stocks_table.setSortingEnabled(True)
        self.stocks_table.horizontalHeader().setStretchLastSection(True)  # 最後一列（推薦理由）自動拉伸
        self.stocks_table.setWordWrap(True)  # 允許推薦理由換行
        ensure_visible_rows(self.stocks_table, rows=5)
        main_layout.addWidget(self.stocks_table)

        self.status_label = QLabel("尚未載入")
        self.status_label.setWordWrap(True)
        self._set_status_label(self.status_label, "尚未載入", level="info")
        main_layout.addWidget(self.status_label)

        self.page_scroll_area = create_scroll_area(
            page_content, object_name="strongStocksPageScrollArea"
        )
        page_layout.addWidget(self.page_scroll_area)
        
        # 注意：選擇事件將在設置模型後連接（在 _refresh_stocks 中）

    @staticmethod
    def _set_status_label(label: QLabel, text: str, *, level: str) -> None:
        colors = {
            "info": "#94a3b8",
            "success": "#86efac",
            "warning": "#facc15",
            "error": "#fca5a5",
        }
        label.setStyleSheet(
            f"color: {colors.get(level, colors['info'])}; padding: 2px 0;"
        )
        label.setText(text)

    @staticmethod
    def _effective_date_suffix(effective_date: date | None) -> str:
        if effective_date is None:
            return "；資料日未提供"
        if isinstance(effective_date, datetime):
            return "；資料日未提供"
        return f"；資料日 {effective_date.isoformat()}"

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "排名",
                "證券代號",
                "證券名稱",
                "行情日",
                "收盤價",
                "漲幅%",
                "成交量變化率%",
                "評分",
                "推薦理由",
            ]
        )
    
    def _on_period_changed(self, period: str):
        """時間範圍改變"""
        self._cancel_active_screening_request()
        self._set_screening_controls_busy(False)
        self.period_btn_day.setChecked(period == 'day')
        self.period_btn_week.setChecked(period == 'week')

        if self.is_shared_research_mode():
            self._clear_shared_research_table()
            self.request_shared_research()
            return
        
        # 檢查緩存，如果有緩存就直接使用，不重新計算
        if self._cached_data[period] is not None:
            self._display_cached_data(period)
            # 有數據時顯示刷新按鈕
            self.refresh_btn.setVisible(True)
            self.load_btn.setVisible(False)
        else:
            # 沒有緩存，顯示空狀態或提示用戶載入數據
            self._show_empty_state()
            self.refresh_btn.setVisible(False)
            self.load_btn.setVisible(True)
    
    def _display_cached_data(self, period: str):
        """顯示緩存的數據（不重新計算）"""
        df = self._cached_data[period]
        if df is not None:
            self._update_table_with_data(df)
            universe_count = self._cached_universe_counts[period]
            self.universe_label.setText(
                f"Universe: {universe_count} stocks" if universe_count > 0 else "Universe: -"
            )
            self._set_status_label(
                self.status_label,
                f"已載入快取：{len(df)} 筆"
                + (f"；掃描範圍 {universe_count} 檔" if universe_count > 0 else "")
                + self._effective_date_suffix(self._cached_effective_dates[period]),
                level="success" if len(df) else "warning",
            )
            self._set_screening_controls_busy(False)
    
    def _update_table_with_data(self, df: pd.DataFrame):
        """更新表格顯示（內部方法，用於顯示數據）"""
        df = df.copy()
        if "行情日" not in df.columns:
            df["行情日"] = "未提供"
        else:
            df["行情日"] = df["行情日"].map(self._display_market_date)

        # 確保欄位順序正確
        expected_columns = ['排名', '證券代號', '證券名稱', '行情日', '收盤價', '漲幅%', '評分', '推薦理由']
        if '成交量變化率%' in df.columns and '成交量變化率%' not in expected_columns:
            idx = expected_columns.index('漲幅%') + 1
            expected_columns.insert(idx, '成交量變化率%')
        
        available_columns = [col for col in expected_columns if col in df.columns]
        for col in df.columns:
            if col not in available_columns:
                available_columns.append(col)
        
        if available_columns:
            df = df[available_columns]
        
        # 更新模型
        self.stocks_model = PandasTableModel(df)
        self.stocks_table.setModel(self.stocks_model)
        self._watch_stocks_model_layout(self.stocks_model)
        self._search_result_loaded = True
        self._apply_stocks_search()
        
        # 連接選擇事件
        if self.stocks_table.selectionModel():
            try:
                self.stocks_table.selectionModel().selectionChanged.disconnect()
            except:
                pass
            self.stocks_table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        
        # 調整列寬
        self.stocks_table.resizeColumnsToContents()
        if '推薦理由' in df.columns:
            reason_col_idx = list(df.columns).index('推薦理由')
            self.stocks_table.setColumnWidth(reason_col_idx, 300)

    @staticmethod
    def _display_market_date(value: Any) -> str:
        try:
            if pd.isna(value):
                return "未提供"
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if not text or text.lower() in {"nan", "nat", "none"}:
            return "未提供"
        return text
    
    def _refresh_stocks(self, use_cache: bool = True):
        """刷新強勢股數據
        
        Args:
            use_cache: 是否使用緩存（True=有緩存就不重新計算，False=強制重新計算）
        """
        if self._is_screening_shutting_down():
            return
        if self.is_shared_research_mode():
            self._clear_shared_research_table()
            self.request_shared_research()
            return
        period = 'day' if self.period_btn_day.isChecked() else 'week'
        if use_cache and self._cached_data[period] is not None:
            self._display_cached_data(period)
            return

        self._cancel_active_screening_request()
        self._screening_request_id += 1
        request_id = self._screening_request_id
        self._set_status_label(
            self.status_label,
            self._screening_loading_status(period),
            level="info",
        )
        self._set_screening_controls_busy(True)

        worker = TaskWorker(
            _load_strong_stock_screening_result,
            self.screening_service,
            period,
        )
        self._screening_worker = worker
        worker.finished.connect(
            lambda result, value=request_id, selected_period=period: self._on_screening_worker_finished(
                value, selected_period, result
            )
        )
        worker.error.connect(
            lambda message, value=request_id, selected_period=period: self._on_screening_worker_error(
                value, selected_period, message
            )
        )
        worker.native_thread_finished.connect(
            lambda item=worker: self._release_screening_worker(item)
        )
        try:
            worker.start()
        except Exception as exc:
            self._on_screening_worker_error(
                request_id,
                period,
                f"{type(exc).__name__}: {exc}",
            )
            self._release_screening_worker(worker)

    def _screening_loading_status(self, period: str) -> str:
        previous = self._cached_data[period]
        if previous is None:
            return "載入中…"
        return (
            f"刷新中；暫留前次 {len(previous)} 筆"
            + self._effective_date_suffix(self._cached_effective_dates[period])
        )

    def _set_screening_controls_busy(self, busy: bool) -> None:
        enabled = not busy
        self.load_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.add_to_watchlist_btn.setEnabled(enabled)

    def _screening_request_is_current(self, request_id: int, period: str) -> bool:
        selected_period = 'day' if self.period_btn_day.isChecked() else 'week'
        return (
            request_id == self._screening_request_id
            and period == selected_period
            and not self._is_screening_shutting_down()
            and not self.is_shared_research_mode()
        )

    def _on_screening_worker_finished(
        self,
        request_id: int,
        period: str,
        payload: object,
    ) -> None:
        if not self._screening_request_is_current(request_id, period):
            return
        try:
            if not isinstance(payload, tuple) or len(payload) != 2:
                raise TypeError("強勢個股 worker 回傳格式不是 (result, effective_date)")
            result, effective_date = payload
            self._apply_screening_result(period, result, effective_date)
        except Exception as exc:
            import traceback

            self._handle_screening_error(
                request_id,
                period,
                f"{str(exc)}\n{traceback.format_exc()}",
            )

    def _apply_screening_result(
        self,
        period: str,
        result: object,
        effective_date: object,
    ) -> None:
        # 處理新的返回格式（元組：DataFrame, universe_count）
        if isinstance(result, tuple):
            if len(result) != 2:
                raise TypeError("強勢個股服務回傳格式不是 (DataFrame, universe_count)")
            df, universe_count = result
        else:
            # 向後兼容：如果返回的是舊格式（只有 DataFrame）
            df = result
            universe_count = 0

        if universe_count > 0:
            self.universe_label.setText(f"Universe: {universe_count} stocks")
        else:
            self.universe_label.setText("Universe: -")
        if not isinstance(df, pd.DataFrame):
            raise TypeError("強勢個股服務未回傳 DataFrame")

        self._cached_data[period] = df.copy()
        self._cached_universe_counts[period] = (
            universe_count if isinstance(universe_count, int) and universe_count > 0 else 0
        )
        self._cached_effective_dates[period] = (
            effective_date
            if isinstance(effective_date, date)
            and not isinstance(effective_date, datetime)
            else None
        )
        self._update_table_with_data(df)
        self.refresh_btn.setVisible(True)
        self.load_btn.setVisible(False)
        if self.watchlist_service:
            self.add_to_watchlist_btn.setVisible(True)
        self._set_status_label(
            self.status_label,
            (
                f"已更新：{len(df)} 筆"
                + (f"；掃描範圍 {universe_count} 檔" if universe_count > 0 else "")
                + self._effective_date_suffix(self._cached_effective_dates[period])
            ),
            level="success" if len(df) else "warning",
        )
        self._set_screening_controls_busy(False)

    def _on_screening_worker_error(
        self,
        request_id: int,
        period: str,
        message: str,
    ) -> None:
        self._handle_screening_error(request_id, period, message)

    def _handle_screening_error(
        self,
        request_id: int,
        period: str,
        message: str,
    ) -> None:
        if not self._screening_request_is_current(request_id, period):
            return
        first_line = str(message).strip().splitlines()
        error_summary = first_line[0] if first_line else "未知錯誤"
        QMessageBox.critical(
            self,
            "錯誤",
            f"刷新強勢股失敗：\n{message}",
        )
        # 清除舊模型，避免錯誤時將前次排名當成目前結果。
        self.stocks_model = PandasTableModel(self._empty_frame())
        self.stocks_table.setModel(self.stocks_model)
        self._watch_stocks_model_layout(self.stocks_model)
        self._search_result_loaded = False
        self._apply_stocks_search()
        self.universe_label.setText("Universe: unavailable")
        self.refresh_btn.setVisible(False)
        self.load_btn.setVisible(True)
        if self.watchlist_service:
            self.add_to_watchlist_btn.setVisible(False)
        self._set_status_label(
            self.status_label,
            f"載入失敗：{error_summary}",
            level="error",
        )
        self._set_screening_controls_busy(False)

    def _release_screening_worker(self, worker: TaskWorker) -> None:
        if self._screening_worker is worker:
            self._screening_worker = None
        if worker in self._retired_screening_workers:
            self._retired_screening_workers.remove(worker)
        worker.deleteLater()

    def _cancel_active_screening_request(self) -> None:
        self._screening_request_id += 1
        worker = self._screening_worker
        if worker is None:
            return
        self._screening_worker = None
        if worker not in self._retired_screening_workers:
            self._retired_screening_workers.append(worker)
        try:
            worker.cancel(cooperative=True, wait=False)
        except RuntimeError:
            self._retired_screening_workers.remove(worker)

    def _is_screening_shutting_down(self) -> bool:
        if self._screening_view_closing:
            return True
        ancestor = self.parentWidget()
        while ancestor is not None:
            if getattr(ancestor, "_shutdown_close_requested", False):
                return True
            ancestor = ancestor.parentWidget()
        return False

    def _on_shared_research_mode_changed(self, index: int) -> None:
        self._cancel_active_screening_request()
        self._set_screening_controls_busy(False)
        super()._on_shared_research_mode_changed(index)
        self._set_stocks_search_mode_hint()

    def _on_shared_research_result(self, read: object) -> None:
        super()._on_shared_research_result(read)
        if self.is_shared_research_mode() and self.stocks_model is not None:
            self._watch_stocks_model_layout(self.stocks_model)
            self._search_result_loaded = True
            self._apply_stocks_search()

    def _clear_shared_research_table(self) -> None:
        super()._clear_shared_research_table()
        if self.stocks_model is not None:
            self._watch_stocks_model_layout(self.stocks_model)
        self._search_result_loaded = False
        self._apply_stocks_search()

    def begin_shutdown(self) -> bool:
        self._screening_view_closing = True
        self._cancel_active_screening_request()
        return super().begin_shutdown()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.begin_shutdown()
        super().closeEvent(event)
    
    def _on_selection_changed(self):
        """表格選擇改變"""
        # 可以添加詳細信息顯示（可選）
        pass
    
    def _show_empty_state(self):
        """顯示空狀態（提示用戶載入數據）"""
        self.stocks_model = PandasTableModel(self._empty_frame())
        self.stocks_table.setModel(self.stocks_model)
        self._watch_stocks_model_layout(self.stocks_model)
        self._search_result_loaded = False
        self._apply_stocks_search()
        self.stocks_table.resizeColumnsToContents()
        self.universe_label.setText("Universe: -")
        self._set_screening_controls_busy(False)
        self._set_status_label(
            self.status_label,
            "尚未載入：請點擊「載入數據」按鈕開始計算",
            level="info",
        )

    def _on_stocks_search_changed(self, _text: str) -> None:
        self._apply_stocks_search()

    def _set_stocks_search_mode_hint(self) -> None:
        if self.is_shared_research_mode():
            self.stocks_search_input.setPlaceholderText("股票代號（快照目前不含名稱）")
            description = (
                "研究快照投影目前只有股票代號欄；只搜尋目前已載入的代號列，"
                "不會重新查詢或更改快照條件。"
            )
        else:
            self.stocks_search_input.setPlaceholderText("股票代號或名稱")
            description = (
                "只搜尋目前已載入清單中的股票代號或名稱；"
                "不會重新查詢資料或擴大 Universe。"
            )
        self.stocks_search_input.setAccessibleDescription(description)
        self.stocks_search_input.setToolTip(description)

    def _watch_stocks_model_layout(self, model: PandasTableModel) -> None:
        model.layoutChanged.connect(
            lambda *_args, source_model=model: (
                self._apply_stocks_search()
                if self.stocks_model is source_model
                else None
            )
        )

    def _apply_stocks_search(self) -> None:
        """只篩目前主表已載入列，保留原始模型與排序／選取索引。"""

        model = self.stocks_model
        if model is None:
            self.stocks_search_count_label.setText("尚未載入")
            return

        row_count = model.rowCount()
        if not self._search_result_loaded:
            for row in range(row_count):
                self.stocks_table.setRowHidden(row, False)
            self.stocks_search_count_label.setText("尚未載入")
            return

        frame = model.getDataFrame()
        query = self.stocks_search_input.text().strip().casefold()
        if not query:
            matches = [True] * row_count
        else:
            matching_rows = pd.Series(False, index=range(row_count), dtype=bool)
            for column_name in ("證券代號", "證券名稱"):
                column_position = next(
                    (
                        position
                        for position, name in enumerate(frame.columns)
                        if name == column_name
                    ),
                    None,
                )
                if column_position is None:
                    continue
                values = (
                    frame.iloc[:, column_position]
                    .reset_index(drop=True)
                    .astype("string")
                    .fillna("")
                    .str.casefold()
                )
                matching_rows |= values.str.contains(query, regex=False, na=False)
            matches = matching_rows.tolist()
            if len(matches) < row_count:
                matches.extend([False] * (row_count - len(matches)))
            matches = matches[:row_count]

        selected_rows = self.stocks_table.selectionModel().selectedRows()
        if any(
            index.row() < 0
            or index.row() >= len(matches)
            or not matches[index.row()]
            for index in selected_rows
        ):
            self.stocks_table.clearSelection()

        for row, matches_query in enumerate(matches):
            self.stocks_table.setRowHidden(row, not matches_query)

        matching_count = sum(matches)
        if not query:
            count_text = (
                f"目前清單 {row_count} 檔（已載入空清單）"
                if row_count == 0
                else f"目前清單 {row_count} 檔"
            )
        elif row_count == 0:
            count_text = "符合 0／0 檔（已載入空清單）"
        elif matching_count == 0:
            count_text = f"此清單無符合標的（0／{row_count}）"
        else:
            count_text = f"符合 {matching_count}／{row_count} 檔"
        self.stocks_search_count_label.setText(count_text)
    
    def _add_selected_to_watchlist(self):
        """將選中的股票加入觀察清單"""
        if not self.watchlist_service or not self.stocks_model:
            return
        
        selection = self.stocks_table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "提示", "請先選擇要加入觀察清單的股票")
            return
        
        # 取得選中的股票
        df = self.stocks_model.getDataFrame()
        stocks = []
        for index in selection:
            row = index.row()
            if row < len(df):
                try:
                    # 使用更安全的方式獲取數據
                    row_data = df.iloc[row]
                    stock_code = row_data.get('證券代號') if '證券代號' in row_data.index else None
                    stock_name = row_data.get('證券名稱') if '證券名稱' in row_data.index else None
                    
                    # 處理 NaN 和 None
                    if stock_code is None or (isinstance(stock_code, float) and pd.isna(stock_code)):
                        continue
                    
                    stock_code = str(stock_code).strip()
                    if not stock_code or stock_code == '-' or stock_code == 'nan':
                        continue
                    
                    # 處理股票名稱
                    if stock_name is None or (isinstance(stock_name, float) and pd.isna(stock_name)):
                        stock_name = stock_code
                    else:
                        stock_name = str(stock_name).strip()
                        if not stock_name or stock_name == '-':
                            stock_name = stock_code
                    
                    stocks.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name
                    })
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"處理第 {row} 行股票數據時出錯: {e}")
                    continue
        
        if stocks:
            try:
                added_count = self.watchlist_service.add_stocks(stocks, source='market_watch')
                if added_count > 0:
                    QMessageBox.information(self, "成功", f"已將 {added_count} 檔股票加入觀察清單")
                else:
                    QMessageBox.warning(self, "提示", "選中的股票已在觀察清單中")
            except Exception as e:
                import traceback
                error_msg = f"加入觀察清單失敗：\n{str(e)}\n\n{traceback.format_exc()}"
                QMessageBox.critical(self, "錯誤", error_msg)
    
    def load_data_if_needed(self):
        """如果需要，載入數據（當 tab 被點擊時調用）"""
        period = 'day' if self.period_btn_day.isChecked() else 'week'
        if self.is_shared_research_mode():
            if self.shared_research_consumer.snapshot is None:
                self._on_shared_research_failure(
                    "尚無已接受的研究快照；請先從每日研究名單讀取來源。"
                )
            else:
                self.request_shared_research()
            return
        # 如果沒有緩存，顯示空狀態
        if self._cached_data[period] is None:
            self._show_empty_state()
            self.refresh_btn.setVisible(False)
            self.load_btn.setVisible(True)
            if self.watchlist_service:
                self.add_to_watchlist_btn.setVisible(False)
        else:
            # 有緩存，直接顯示
            self._display_cached_data(period)
            self.refresh_btn.setVisible(True)
            self.load_btn.setVisible(False)
            if self.watchlist_service:
                self.add_to_watchlist_btn.setVisible(True)

