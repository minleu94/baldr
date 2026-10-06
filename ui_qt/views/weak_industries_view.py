"""
弱勢產業視圖
顯示弱勢產業列表（與強勢產業同架構，反向排名）
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableView, QHeaderView, QMessageBox, QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import pandas as pd
from typing import Optional

from ui_qt.models.pandas_table_model import PandasTableModel
from app_module.screening_service import ScreeningService
from ui_qt.widgets.info_button import InfoButton
from ui_qt.widgets.table_style import apply_financial_table_style
from app_module.research_session import ResearchStockContextDTO
from ui_qt.widgets.layout_helpers import create_scroll_area, ensure_visible_rows


class WeakIndustriesView(QWidget):
    """弱勢產業視圖"""

    stockResearchRequested = Signal(object)
    
    def __init__(self, screening_service: ScreeningService, parent=None):
        """初始化弱勢產業視圖
        
        Args:
            screening_service: 篩選服務實例
            parent: 父窗口
        """
        super().__init__(parent)
        self.screening_service = screening_service
        self._comparable_mode = (
            getattr(screening_service, "industry_strength_service", None) is not None
        )
        
        # 數據模型
        self.industries_model: Optional[PandasTableModel] = None
        
        # 數據緩存（避免重複計算）
        self._cached_data = {
            'day': None,  # 緩存本日的數據
            'week': None  # 緩存本周的數據
        }
        
        self._setup_ui()
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
        title = QLabel(
            "弱勢產業（依相對大盤排名）" if self._comparable_mode else "弱勢產業"
        )
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        title_layout.addStretch()
        info_btn = InfoButton("weak_industries", self)
        title_layout.addWidget(info_btn)
        main_layout.addLayout(title_layout)
        self.source_scope_label = QLabel(
            "本頁母體沿既有全產業／映射來源，非具名股票研究 cohort；"
            "資料日／來源／版本依本頁已核對結果，缺少母體成分身份時比較性未知。"
        )
        self.source_scope_label.setWordWrap(True)
        main_layout.addWidget(self.source_scope_label)
        
        # 控制欄
        controls_widget = QWidget()
        control_layout = QHBoxLayout(controls_widget)
        
        # 時間範圍選擇
        control_layout.addWidget(QLabel("時間範圍:"))
        self.period_btn_day = QPushButton(
            "近5交易日" if self._comparable_mode else "本日"
        )
        self.period_btn_week = QPushButton(
            "近20交易日" if self._comparable_mode else "本周"
        )
        self.period_btn_day.setCheckable(True)
        self.period_btn_week.setCheckable(True)
        self.period_btn_day.setChecked(True)
        self.period_btn_day.clicked.connect(lambda: self._on_period_changed('day'))
        self.period_btn_week.clicked.connect(lambda: self._on_period_changed('week'))
        control_layout.addWidget(self.period_btn_day)
        control_layout.addWidget(self.period_btn_week)

        self.level_label = QLabel("層級：")
        self.level_selector = QComboBox()
        self.level_selector.setAccessibleName("選取產業排名層級")
        self.level_selector.addItem("細分產業", "leaf")
        self.level_selector.addItem("綜合類別", "aggregate")
        self.level_selector.addItem("全部層級", "all")
        self.level_selector.currentIndexChanged.connect(self._on_level_changed)
        self.level_label.setVisible(self._comparable_mode)
        self.level_selector.setVisible(self._comparable_mode)
        control_layout.addWidget(self.level_label)
        control_layout.addWidget(self.level_selector)
        
        control_layout.addStretch()
        
        # 載入數據按鈕（首次載入或強制重新計算）
        self.load_btn = QPushButton("載入數據")
        self.load_btn.setProperty("variant", "primary")
        self.load_btn.clicked.connect(lambda: self._refresh_industries(use_cache=False))
        control_layout.addWidget(self.load_btn)
        
        # 刷新按鈕（強制重新計算，僅在有數據時顯示）
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setVisible(False)  # 初始隱藏
        self.refresh_btn.clicked.connect(lambda: self._refresh_industries(use_cache=False))
        control_layout.addWidget(self.refresh_btn)
        
        self.controls_scroll_area = create_scroll_area(
            controls_widget,
            object_name="weakIndustriesControlsScrollArea",
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
        
        # 表格
        self.industries_table = QTableView()
        apply_financial_table_style(self.industries_table)
        self.industries_table.setSelectionBehavior(QTableView.SelectRows)
        self.industries_table.setSortingEnabled(True)
        self.industries_table.clicked.connect(self._select_representative_row)
        self.industries_table.doubleClicked.connect(self._select_representative_row)
        self.industries_table.horizontalHeader().setStretchLastSection(True)
        ensure_visible_rows(self.industries_table, rows=5)
        main_layout.addWidget(self.industries_table)

        drilldown_layout = QHBoxLayout()
        drilldown_layout.addWidget(QLabel("代表股下鑽:"))
        self.representative_selector = QComboBox()
        self.representative_selector.setAccessibleName("選取弱勢產業代表股")
        self.representative_selector.setMinimumWidth(240)
        self.representative_selector.addItem("請先選取產業列")
        drilldown_layout.addWidget(self.representative_selector, 1)
        self.open_representative_button = QPushButton("開啟所選代表股研究")
        self.open_representative_button.setProperty("variant", "secondary")
        self.open_representative_button.setEnabled(False)
        self.open_representative_button.clicked.connect(self._open_selected_representative_stock)
        drilldown_layout.addWidget(self.open_representative_button)
        main_layout.addLayout(drilldown_layout)

        self.status_label = QLabel("尚未載入")
        self.status_label.setWordWrap(True)
        self._set_status_label(self.status_label, "尚未載入", level="info")
        main_layout.addWidget(self.status_label)

        self.page_scroll_area = create_scroll_area(
            page_content, object_name="weakIndustriesPageScrollArea"
        )
        page_layout.addWidget(self.page_scroll_area)

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
    def _data_identity_suffix(df: pd.DataFrame) -> str:
        if df.empty:
            return ""
        row = df.iloc[0]
        data_date = str(row.get('資料日') or '未知')
        source_id = str(row.get('資料來源') or '未知')
        version = str(row.get('資料版本') or '未知')
        return f"｜資料日 {data_date}｜來源 {source_id}｜版本 {version}"

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        return pd.DataFrame(columns=["排名", "指數名稱", "收盤指數", "跌幅%"])
    
    def _on_period_changed(self, period: str):
        """時間範圍改變"""
        if period == 'day':
            self.period_btn_week.setChecked(False)
        else:
            self.period_btn_day.setChecked(False)
        
        # 檢查緩存，如果有緩存就直接使用，不重新計算
        if self._cached_data[period] is not None:
            self._display_cached_data(period)
            self.refresh_btn.setVisible(True)
            self.load_btn.setVisible(False)
        else:
            self._show_empty_state()
            self.refresh_btn.setVisible(False)
            self.load_btn.setVisible(True)
    
    def _display_cached_data(self, period: str):
        """顯示緩存的數據（不重新計算）"""
        df = self._cached_data[period]
        if df is not None:
            visible_df = self._update_table_with_data(df)
            self._set_status_label(
                self.status_label,
                f"已載入快取：{len(visible_df)} 筆{self._data_identity_suffix(df)}",
                level="success" if len(visible_df) else "warning",
            )

    def _on_level_changed(self, _index: int) -> None:
        if not self._comparable_mode:
            return
        period = 'day' if self.period_btn_day.isChecked() else 'week'
        if self._cached_data[period] is not None:
            self._display_cached_data(period)

    def _apply_level_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        if (
            not self._comparable_mode
            or "產業層級" not in df.columns
            or not hasattr(self, "level_selector")
        ):
            return df
        selected = self.level_selector.currentData()
        if selected not in {"leaf", "aggregate"}:
            return df
        level_values = df["產業層級"].astype(str).str.strip().map(
            {"細分產業": "leaf", "綜合類別": "aggregate"}
        ).fillna(df["產業層級"].astype(str).str.strip())
        return df.loc[level_values == selected].reset_index(drop=True)

    def _update_table_with_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """更新表格顯示（內部方法，用於顯示數據）"""
        self._reset_representative_selector()
        # 複製 DataFrame 以避免修改原始數據
        df = df.copy()
        
        # 重命名欄位以符合弱勢產業的語義
        if '漲幅%' in df.columns:
            # 將漲幅%轉換為跌幅%（弱勢產業的漲幅%通常是負數，取絕對值顯示為正數跌幅）
            df = df.rename(columns={'漲幅%': '跌幅%'})
            # 取絕對值，確保顯示為正數跌幅（因為弱勢產業的漲幅%是負數）
            if '跌幅%' in df.columns:
                # CSV／舊服務可能回傳字串；這裡是純顯示邊界，無法轉換者保留 NaN。
                df['跌幅%'] = pd.to_numeric(
                    df['跌幅%'], errors='coerce'
                ).abs()

        df = self._apply_level_filter(df)
        if '產業層級' in df.columns:
            df['產業層級'] = df['產業層級'].astype(str).str.strip().map(
                {'leaf': '細分產業', 'aggregate': '綜合類別'}
            ).fillna(df['產業層級'])
        if '資料品質' in df.columns:
            quality_labels = {
                'observed': '正常',
                'estimated': '估算',
                'degraded': '降級',
                'missing': '缺漏',
            }
            df['資料品質'] = df['資料品質'].astype(str).str.strip().str.lower().map(
                quality_labels
            ).fillna(df['資料品質'])
        
        # 更新模型
        self.industries_model = PandasTableModel(df, red_positive_columns={'跌幅%'})
        display_columns = [
            '排名', '產業名稱', '產業層級', '5日漲幅%', '20日漲幅%', '5日超額%', '20日超額%',
            '5日覆蓋率%', '20日覆蓋率%', '代表股票', '資料品質',
        ]
        if (
            '跌幅%' in df.columns
            and not {'5日漲幅%', '20日漲幅%'}.intersection(df.columns)
        ):
            display_columns.insert(3, '跌幅%')
        available_columns = [col for col in display_columns if col in df.columns]
        if available_columns:
            self.industries_model.setVisibleColumns(available_columns)
        self.industries_table.setModel(self.industries_model)
        
        # 調整列寬
        self.industries_table.resizeColumnsToContents()
        return df

    def _select_representative_row(self, index) -> None:
        if self.industries_model is None or not index.isValid():
            return
        frame = self.industries_model.getDataFrame()
        if index.row() < 0 or index.row() >= len(frame):
            return
        row = frame.iloc[index.row()]
        self.representative_selector.clear()
        raw_names = str(row.get('代表股票名稱') or '').strip()
        names = [item.strip() for item in raw_names.split(',')]
        raw_codes = str(row.get('代表股票代號') or '').strip()
        codes = [item.strip() for item in raw_codes.split(',') if item.strip()]
        for position, code in enumerate(codes):
            name = names[position] if position < len(names) and names[position] else code
            self.representative_selector.addItem(f'{code} {name}', {
                'code': code,
                'name': name,
                'industry': str(row.get('產業名稱') or row.get('指數名稱') or '').strip(),
                'data_date': str(row.get('資料日') or '').strip(),
                'source_id': str(row.get('資料來源') or 'industry_strength.sqlite_current_research'),
                'source_version': str(row.get('資料版本') or '').strip(),
                'mapping_source_id': str(row.get('映射來源') or '').strip(),
                'mapping_version': str(row.get('映射版本') or '').strip(),
                'mapping_observed_date': str(row.get('映射觀測日') or '').strip(),
            })
        if not codes:
            self.representative_selector.addItem('此產業沒有可用代表股')
        self.open_representative_button.setEnabled(bool(codes))

    def _reset_representative_selector(self) -> None:
        self.representative_selector.clear()
        self.representative_selector.addItem('請先選取產業列')
        self.open_representative_button.setEnabled(False)

    def _open_selected_representative_stock(self) -> None:
        payload = self.representative_selector.currentData()
        if not isinstance(payload, dict) or not payload.get('code'):
            return
        self.stockResearchRequested.emit(
            ResearchStockContextDTO(
                stock_code=str(payload['code']),
                stock_name=str(payload.get('name') or payload['code']),
                decision_date=str(payload.get('data_date') or ''),
                data_date=str(payload.get('data_date') or ''),
                source_id=str(payload.get('source_id') or 'industry_strength.sqlite_current_research'),
                source_version=str(payload.get('source_version') or ''),
                mapping_source_id=str(payload.get('mapping_source_id') or ''),
                mapping_version=str(payload.get('mapping_version') or ''),
                mapping_observed_date=str(payload.get('mapping_observed_date') or ''),
                source_kind='industry_strength',
                source_label=f"弱勢產業／{payload.get('industry') or '未知產業'}",
                source_workspace='market_explore',
            )
        )
    
    def _refresh_industries(self, use_cache: bool = True):
        """刷新弱勢產業數據
        
        Args:
            use_cache: 是否使用緩存（True=有緩存就不重新計算，False=強制重新計算）
        """
        self._set_status_label(self.status_label, "載入中…", level="info")
        try:
            # 獲取當前選擇的時間範圍
            period = 'day' if self.period_btn_day.isChecked() else 'week'
            
            # 檢查緩存
            if use_cache and self._cached_data[period] is not None:
                self._display_cached_data(period)
                return
            
            # 調用服務（重新計算）
            dto_method = getattr(self.screening_service, "get_weak_industries_dto", None)
            df = (
                dto_method(period=period, top_n=50).to_legacy()
                if callable(dto_method)
                else self.screening_service.get_weak_industries(period=period, top_n=50)
            )
            
            if not isinstance(df, pd.DataFrame):
                raise TypeError("弱勢產業服務未回傳 DataFrame")
            
            # 保存到緩存
            self._cached_data[period] = df.copy()
            
            # 更新表格顯示
            visible_df = self._update_table_with_data(df)
            
            # 更新按鈕狀態
            self.refresh_btn.setVisible(True)
            self.load_btn.setVisible(False)
            self._set_status_label(
                self.status_label,
                f"已更新：{len(visible_df)} 筆{self._data_identity_suffix(df)}",
                level="success" if len(visible_df) else "warning",
            )
            
        except Exception as e:
            import traceback
            error_msg = f"刷新弱勢產業失敗：\n{str(e)}\n\n{traceback.format_exc()}"
            QMessageBox.critical(self, "錯誤", error_msg)
            self.industries_model = PandasTableModel(
                self._empty_frame(), red_positive_columns={'跌幅%'}
            )
            self.industries_table.setModel(self.industries_model)
            self._reset_representative_selector()
            self.refresh_btn.setVisible(False)
            self.load_btn.setVisible(True)
            self._set_status_label(
                self.status_label,
                f"載入失敗：{str(e).splitlines()[0] or type(e).__name__}",
                level="error",
            )
    
    def _show_empty_state(self):
        """顯示空狀態（提示用戶載入數據）"""
        self._reset_representative_selector()
        self.industries_model = PandasTableModel(
            self._empty_frame(), red_positive_columns={'跌幅%'}
        )
        self.industries_table.setModel(self.industries_model)
        self.industries_table.resizeColumnsToContents()
        self._set_status_label(
            self.status_label,
            "尚未載入：請點擊「載入數據」按鈕開始計算",
            level="info",
        )
    
    def load_data_if_needed(self):
        """如果需要，載入數據（當 tab 被點擊時調用）"""
        period = 'day' if self.period_btn_day.isChecked() else 'week'
        if self._cached_data[period] is None:
            self._show_empty_state()
            self.refresh_btn.setVisible(False)
            self.load_btn.setVisible(True)
        else:
            self._display_cached_data(period)
            self.refresh_btn.setVisible(True)
            self.load_btn.setVisible(False)

