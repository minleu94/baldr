"""
回測結果面板
包含所有實驗摘要、圖表、最佳化結果、比較與批次/推薦結果呈現分頁
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QGroupBox, QTableView, QTextEdit, QComboBox, 
    QHeaderView, QListWidget, QTabWidget, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from ui_qt.widgets.fast_chart_widget import (
    create_drawdown_curve_widget,
    create_equity_curve_widget,
    create_holding_days_histogram_widget,
    create_trade_return_histogram_widget,
)
from ui_qt.views.research_lab.run_registry_compare_widget import RunRegistryCompareWidget
from ui_qt.views.backtest.analyst_diagnostics_widget import AnalystDiagnosticsWidget
from app_module.decision_quality_dashboard_service import create_decision_quality_dashboard_service
from app_module.evidence_operations_history_dashboard_service import create_evidence_operations_history_dashboard_service
from app_module.forward_performance_dashboard_service import create_forward_performance_dashboard_service
from app_module.live_research_gap_dashboard_service import create_live_research_gap_dashboard_service
from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatusService
from app_module.signal_decay_dashboard_service import create_signal_decay_dashboard_service
from ui_qt.views.evidence_review_view import EvidenceReviewView
from ui_qt.views.forward_performance_view import ForwardPerformanceView
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.table_style import apply_financial_table_style


class BacktestResultPanel(QWidget):
    """回測結果面板"""
    
    def __init__(self, parent_view, parent=None):
        """初始化結果面板
        
        Args:
            parent_view: 父視圖 BacktestView 實例，用於獲取服務和回調方法
            parent: 父窗口
        """
        super().__init__(parent)
        self.parent_view = parent_view
        
        # 預留的 trades_model 內部變數
        self._trades_model = None
        
        self._setup_ui()
        
    @property
    def trades_model(self):
        return self._trades_model
        
    @trades_model.setter
    def trades_model(self, value):
        self._trades_model = value

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._result_tab_widgets: dict[str, QWidget] = {}
        self._result_tab_titles: dict[str, str] = {}
        self._research_mode_id = "single_stock"

        context_row = QHBoxLayout()
        self.mode_context_label = QLabel()
        self.mode_context_label.setAccessibleName("目前研究模式")
        self.mode_context_label.setToolTip("結果頁會依研究模式只保留相關工作區；不代表資料被刪除")
        self.mode_context_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; padding: 5px 8px; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_badge}px;"
        )
        self.result_purpose_label = QLabel("結果目的：先看模式主結果，再用分析診斷與證據頁複核。")
        self.result_purpose_label.setAccessibleName("結果工作區目的")
        self.result_purpose_label.setToolTip("提示目前結果工作區的閱讀順序")
        self.result_purpose_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_muted}; font-size: 12px;"
        )
        context_row.addWidget(self.mode_context_label)
        context_row.addWidget(self.result_purpose_label, stretch=1)
        layout.addLayout(context_row)
        
        self.result_tabs = QTabWidget()
        self.result_tabs.setAccessibleName("回測結果工作區")

        # Tab 1: 結果
        result_tab = QWidget()
        result_layout = QVBoxLayout(result_tab)
        result_layout.setSpacing(10)
        result_layout.setContentsMargins(5, 5, 5, 5)

        self.result_interpretation_label = QLabel(
            "閱讀順序：淨報酬 → 最大回撤 → 交易筆數 → 成本與資料限制；"
            "歷史結果只供比較，請搭配診斷與證據複核。"
        )
        self.result_interpretation_label.setWordWrap(True)
        self.result_interpretation_label.setAccessibleName("回測結果判讀限制")
        self.result_interpretation_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; padding: 3px 0; font-size: 12px;"
        )
        result_layout.addWidget(self.result_interpretation_label)
        
        # 績效摘要
        summary_group = QGroupBox("實驗摘要")
        summary_layout = QVBoxLayout()
        
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMinimumHeight(150)
        self.summary_text.setFont(QFont("Consolas", 9))
        summary_layout.addWidget(self.summary_text)
        
        # 單股回測 Excel 匯出按鈕
        btn_layout = QHBoxLayout()
        self.export_report_btn = QPushButton("匯出 Excel 報告")
        self.export_report_btn.setEnabled(False)
        self.export_report_btn.setToolTip("匯出目前單股回測的詳細研究報告（報告僅輸出目前結果，不重新計算績效）")
        self.export_report_btn.clicked.connect(self.parent_view._export_single_backtest)
        btn_layout.addStretch()
        btn_layout.addWidget(self.export_report_btn)
        summary_layout.addLayout(btn_layout)
        
        summary_group.setLayout(summary_layout)
        result_layout.addWidget(summary_group, stretch=65)
        
        # 交易明細
        trades_group = QGroupBox("交易明細")
        trades_layout = QVBoxLayout()
        
        self.trades_table = QTableView()
        apply_financial_table_style(self.trades_table)
        self.trades_table.setSelectionBehavior(QTableView.SelectRows)
        self.trades_table.setSortingEnabled(True)
        self.trades_table.horizontalHeader().setStretchLastSection(True)
        self.trades_table.setMinimumHeight(150)
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.trades_table.setFont(QFont("Consolas", 9))
        
        # 啟用右鍵選單
        self.trades_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.trades_table.customContextMenuRequested.connect(self.parent_view._show_trades_table_context_menu)
        
        trades_layout.addWidget(self.trades_table)
        trades_group.setLayout(trades_layout)
        result_layout.addWidget(trades_group, stretch=35)
        
        self._register_result_tab("summary", result_tab, "實驗摘要")

        # 分析師診斷：由 application boundary DTO 提供，不在 UI 內重算回測。
        self.analyst_diagnostics_widget = AnalystDiagnosticsWidget()
        self._register_result_tab("diagnostics", self.analyst_diagnostics_widget, "分析診斷")
        
        # Tab 2: 圖表
        if self.parent_view.chart_data_service:
            chart_tab = QWidget()
            chart_layout = QVBoxLayout(chart_tab)
            
            run_select_row = QHBoxLayout()
            run_select_row.addWidget(QLabel("選擇回測結果:"))
            self.chart_run_combo = QComboBox()
            self.chart_run_combo.setEditable(False)
            self.chart_run_combo.currentTextChanged.connect(self.parent_view._on_chart_run_changed)
            run_select_row.addWidget(self.chart_run_combo)
            run_select_row.addStretch()
            chart_layout.addLayout(run_select_row)
            
            chart_tabs = QTabWidget()
            
            self.equity_chart = create_equity_curve_widget()
            chart_tabs.addTab(self.equity_chart, "權益曲線")
            
            self.drawdown_chart = create_drawdown_curve_widget()
            chart_tabs.addTab(self.drawdown_chart, "回撤曲線")
            
            self.return_hist = create_trade_return_histogram_widget()
            chart_tabs.addTab(self.return_hist, "交易報酬")
            
            self.holding_hist = create_holding_days_histogram_widget()
            chart_tabs.addTab(self.holding_hist, "持有天數")
            
            chart_layout.addWidget(chart_tabs)
            self._register_result_tab("charts", chart_tab, "圖表")
        
        # Tab 3: 最佳化結果
        if self.parent_view.optimizer_service:
            optimization_result_tab = QWidget()
            optimization_result_layout = QVBoxLayout(optimization_result_tab)
            
            optimization_result_group = QGroupBox("最佳化結果")
            optimization_result_layout_inner = QVBoxLayout()

            self.optimization_stability_label = QLabel()
            self.optimization_stability_label.setWordWrap(True)
            self.optimization_stability_label.setAccessibleName("最佳化 Top-N 穩定性摘要")
            self.optimization_stability_label.setToolTip(
                "只描述目前保留的 Top-N 探索性樣本，不是完整參數面、信賴區間或 OOS 證明。"
            )
            self.optimization_stability_label.setStyleSheet(
                f"padding: 7px; color: {MIDNIGHT_ANALYST.text_secondary}; "
                f"background: {MIDNIGHT_ANALYST.surface_2}; border: 1px solid {MIDNIGHT_ANALYST.border};"
            )
            optimization_result_layout_inner.addWidget(self.optimization_stability_label)
            
            self.optimization_table = QTableView()
            apply_financial_table_style(self.optimization_table)
            self.optimization_table.setSelectionBehavior(QTableView.SelectRows)
            self.optimization_table.setSortingEnabled(True)
            self.optimization_table.horizontalHeader().setStretchLastSection(True)
            self.optimization_table.setMinimumHeight(200)
            self.optimization_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            self.optimization_table.setFont(QFont("Consolas", 9))
            self.optimization_table.doubleClicked.connect(self.parent_view._apply_optimization_params)
            optimization_result_layout_inner.addWidget(self.optimization_table)
            
            apply_btn = QPushButton("套用選中參數")
            apply_btn.clicked.connect(self.parent_view._apply_optimization_params)
            optimization_result_layout_inner.addWidget(apply_btn)
            
            optimization_result_group.setLayout(optimization_result_layout_inner)
            optimization_result_layout.addWidget(optimization_result_group)
            
            self._register_result_tab("optimization", optimization_result_tab, "最佳化 / 驗證")
            
        # Tab 4: 比較
        if self.parent_view.run_repository:
            compare_tab = QWidget()
            compare_layout = QVBoxLayout(compare_tab)

            legacy_banner = QLabel(
                "Legacy 歷史：只讀相容舊 BacktestRunRepository 的歷史與比較；"
                "不是統一 Research evidence SSOT，不自動遷移，也不重算歷史。"
            )
            legacy_banner.setWordWrap(True)
            legacy_banner.setAccessibleName("Legacy 歷史說明")
            legacy_banner.setToolTip("Legacy repository compatibility boundary")
            legacy_banner.setStyleSheet(
                f"padding: 8px; color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_2}; "
                f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-left: 4px solid {MIDNIGHT_ANALYST.warning};"
            )
            compare_layout.addWidget(legacy_banner)
            
            history_group = QGroupBox("回測歷史")
            history_layout = QVBoxLayout()
            
            history_btn_row = QHBoxLayout()
            self.refresh_history_btn = QPushButton("重新整理")
            self.refresh_history_btn.clicked.connect(self.parent_view._refresh_history)
            history_btn_row.addWidget(self.refresh_history_btn)
            
            self.delete_history_btn = QPushButton("刪除選中")
            self.delete_history_btn.setProperty("variant", "danger")
            self.delete_history_btn.clicked.connect(self.parent_view._delete_history_runs)
            history_btn_row.addWidget(self.delete_history_btn)
            
            history_btn_row.addStretch()
            history_layout.addLayout(history_btn_row)
            
            self.history_list = QListWidget()
            self.history_list.setSelectionMode(QListWidget.ExtendedSelection)
            self.history_list.itemDoubleClicked.connect(self.parent_view._load_history_run)
            history_layout.addWidget(self.history_list)
            
            compare_btn = QPushButton("比較選中")
            compare_btn.clicked.connect(self.parent_view._compare_runs)
            history_layout.addWidget(compare_btn)
            
            history_group.setLayout(history_layout)
            compare_layout.addWidget(history_group)
            
            compare_result_group = QGroupBox("比較結果")
            compare_result_layout = QVBoxLayout()
            
            self.compare_table = QTableView()
            apply_financial_table_style(self.compare_table)
            self.compare_table.setSortingEnabled(True)
            self.compare_table.horizontalHeader().setStretchLastSection(True)
            self.compare_table.setSelectionBehavior(QTableView.SelectRows)
            self.compare_table.doubleClicked.connect(self.parent_view._on_compare_table_double_clicked)
            compare_result_layout.addWidget(self.compare_table)
            
            compare_result_group.setLayout(compare_result_layout)
            compare_layout.addWidget(compare_result_group)
            
            self._register_result_tab("legacy", compare_tab, "Legacy 歷史")
            
        # Tab 5: 批次結果
        if self.parent_view.batch_backtest_service:
            batch_result_tab = QWidget()
            batch_result_layout = QVBoxLayout(batch_result_tab)
            batch_result_layout.setSpacing(10)
            batch_result_layout.setContentsMargins(5, 5, 5, 5)

            self.batch_interpretation_label = QLabel(
                "比較目的：排行榜用來快速找出同一批次內相對值得複核的股票；"
                "整體統計用來觀察樣本分布與有效回測 coverage；獲利標的比例以有效回測為母體，"
                "不是交易筆勝率；排行榜的 WinRate% 只有在單檔交易明細有值時才代表交易筆勝率。"
                "此頁只整理已完成的批次回測結果，"
                "不代表正式策略判斷、交易建議或持倉調整。"
            )
            self.batch_interpretation_label.setWordWrap(True)
            self.batch_interpretation_label.setStyleSheet(
                f"padding: 8px 10px; color: {MIDNIGHT_ANALYST.text_secondary}; "
                f"background: {MIDNIGHT_ANALYST.surface_2}; "
                f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
                f"border-left: 4px solid {MIDNIGHT_ANALYST.info}; "
                f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px;"
            )
            batch_result_layout.addWidget(self.batch_interpretation_label)
            
            sort_row = QHBoxLayout()
            sort_row.addWidget(QLabel("排序方式:"))
            self.batch_sort_combo = QComboBox()
            self.batch_sort_combo.addItems(["CAGR-MDD", "CAGR", "Sharpe", "MDD（回撤幅度）"])
            self.batch_sort_combo.currentTextChanged.connect(self.parent_view._on_batch_sort_changed)
            sort_row.addWidget(self.batch_sort_combo)
            sort_row.addStretch()
            
            self.export_batch_report_btn = QPushButton("匯出批次 Excel")
            self.export_batch_report_btn.setEnabled(False)
            self.export_batch_report_btn.setToolTip("匯出目前批次操作的排行榜與統計報告")
            self.export_batch_report_btn.clicked.connect(self.parent_view._export_batch_backtest)
            sort_row.addWidget(self.export_batch_report_btn)
            
            batch_result_layout.addLayout(sort_row)
            
            batch_leaderboard_group = QGroupBox("排行榜")
            batch_leaderboard_layout = QVBoxLayout()
            
            self.batch_leaderboard_table = QTableView()
            apply_financial_table_style(self.batch_leaderboard_table)
            self.batch_leaderboard_table.setSelectionBehavior(QTableView.SelectRows)
            self.batch_leaderboard_table.setSortingEnabled(False)
            self.batch_leaderboard_table.horizontalHeader().setStretchLastSection(True)
            self.batch_leaderboard_table.doubleClicked.connect(self.parent_view._on_batch_row_double_clicked)
            self.batch_leaderboard_table.setMinimumHeight(300)
            self.batch_leaderboard_table.setFont(QFont("Consolas", 9))
            batch_leaderboard_layout.addWidget(self.batch_leaderboard_table)
            
            batch_leaderboard_group.setLayout(batch_leaderboard_layout)
            batch_result_layout.addWidget(batch_leaderboard_group, stretch=2)
            
            batch_stats_group = QGroupBox("整體統計")
            batch_stats_layout = QVBoxLayout()
            
            self.batch_stats_text = QTextEdit()
            self.batch_stats_text.setReadOnly(True)
            # 摘要現在明確拆出 coverage、失敗／無交易與各中位數母體，
            # 保留足夠高度避免第 6/7 行被捲軸或容器裁切。
            self.batch_stats_text.setMaximumHeight(150)
            self.batch_stats_text.setFont(QFont("Consolas", 10))
            batch_stats_layout.addWidget(self.batch_stats_text)
            
            batch_stats_group.setLayout(batch_stats_layout)
            batch_result_layout.addWidget(batch_stats_group, stretch=1)
            
            self._register_result_tab("batch", batch_result_tab, "批次結果")
            
        # Tab 6: 推薦回放
        recommendation_portfolio_tab = QWidget()
        recommendation_portfolio_layout = QVBoxLayout(recommendation_portfolio_tab)
        recommendation_portfolio_layout.setSpacing(8)
        recommendation_portfolio_layout.setContentsMargins(5, 5, 5, 5)

        self.portfolio_interpretation_label = QLabel(
            "閱讀順序：組合淨值／回撤 → 交易筆數與持有期 → 成本與重播限制；"
            "回放結果只供歷史檢查。"
        )
        self.portfolio_interpretation_label.setWordWrap(True)
        self.portfolio_interpretation_label.setAccessibleName("推薦回放判讀限制")
        self.portfolio_interpretation_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; padding: 3px 0; font-size: 12px;"
        )
        recommendation_portfolio_layout.addWidget(self.portfolio_interpretation_label)
        
        self.portfolio_summary_text = QTextEdit()
        self.portfolio_summary_text.setReadOnly(True)
        self.portfolio_summary_text.setMaximumHeight(200)
        self.portfolio_summary_text.setFont(QFont("Consolas", 9))
        recommendation_portfolio_layout.addWidget(self.portfolio_summary_text)
        
        # 推薦回放 Excel 匯出按鈕列
        portfolio_btn_row = QHBoxLayout()
        portfolio_btn_row.addStretch()
        self.export_portfolio_report_btn = QPushButton("匯出回放 Excel")
        self.export_portfolio_report_btn.setEnabled(False)
        self.export_portfolio_report_btn.setToolTip("匯出推薦回放的組合持倉與個股貢獻報告")
        self.export_portfolio_report_btn.clicked.connect(self.parent_view._export_recommendation_replay)
        portfolio_btn_row.addWidget(self.export_portfolio_report_btn)
        recommendation_portfolio_layout.addLayout(portfolio_btn_row)
        
        self.portfolio_detail_tabs = QTabWidget()

        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        self.portfolio_chart_tabs = QTabWidget()
        self.portfolio_equity_chart = create_equity_curve_widget()
        self.portfolio_drawdown_chart = create_drawdown_curve_widget()
        self.portfolio_chart_tabs.addTab(self.portfolio_equity_chart, "組合價值")
        self.portfolio_chart_tabs.addTab(self.portfolio_drawdown_chart, "回撤")
        chart_layout.addWidget(self.portfolio_chart_tabs)
        self.portfolio_detail_tabs.addTab(chart_container, "圖表")
        
        self.portfolio_period_table = QTableView()
        self.portfolio_stock_table = QTableView()
        self.portfolio_trades_table = QTableView()
        
        for table in [
            self.portfolio_period_table,
            self.portfolio_stock_table,
            self.portfolio_trades_table
        ]:
            apply_financial_table_style(table)
            table.setSelectionBehavior(QTableView.SelectRows)
            table.setSortingEnabled(True)
            table.horizontalHeader().setStretchLastSection(True)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            table.setFont(QFont("Consolas", 9))
            
        period_tab = QWidget()
        period_layout = QVBoxLayout(period_tab)
        period_layout.setContentsMargins(0, 0, 0, 0)
        period_layout.addWidget(self.portfolio_period_table)
        self.portfolio_detail_tabs.addTab(period_tab, "期間明細")

        stock_tab = QWidget()
        stock_layout = QVBoxLayout(stock_tab)
        stock_layout.setContentsMargins(0, 0, 0, 0)
        stock_layout.addWidget(self.portfolio_stock_table)
        self.portfolio_detail_tabs.addTab(stock_tab, "個股貢獻")

        trades_tab = QWidget()
        trades_layout = QVBoxLayout(trades_tab)
        trades_layout.setContentsMargins(0, 0, 0, 0)
        trades_layout.addWidget(self.portfolio_trades_table)
        self.portfolio_detail_tabs.addTab(trades_tab, "交易紀錄")

        recommendation_portfolio_layout.addWidget(self.portfolio_detail_tabs, stretch=5)
        
        self._register_result_tab("recommendation", recommendation_portfolio_tab, "推薦回放")
        
        layout.addWidget(self.result_tabs)

        if getattr(self.parent_view, "config", None):
            self.add_forward_performance_tab()
        if getattr(self.parent_view, "research_run_service", None):
            self.add_registry_compare_tab()

        self.set_research_mode("single_stock")

    def _register_result_tab(self, key: str, widget: QWidget, title: str) -> None:
        """以 semantic key 註冊頂層結果頁，避免以顯示文字猜 tab。"""
        self._result_tab_widgets[key] = widget
        self._result_tab_titles[key] = title
        self.result_tabs.addTab(widget, title)

    def result_tab_key(self, index: int) -> str | None:
        for key, widget in self._result_tab_widgets.items():
            if self.result_tabs.indexOf(widget) == index:
                return key
        return None

    def focus_result_tab(self, key: str) -> bool:
        widget = self._result_tab_widgets.get(key)
        if widget is None:
            return False
        index = self.result_tabs.indexOf(widget)
        if index < 0:
            return False
        self.result_tabs.setCurrentIndex(index)
        return True

    def _set_result_tab_visible(self, key: str, visible: bool) -> None:
        widget = self._result_tab_widgets.get(key)
        if widget is None:
            return
        index = self.result_tabs.indexOf(widget)
        if index < 0:
            return
        set_tab_visible = getattr(self.result_tabs, "setTabVisible", None)
        if callable(set_tab_visible):
            set_tab_visible(index, visible)
        else:
            # PySide6 舊版沒有 setTabVisible 時，至少停用而不讓使用者進入錯誤頁。
            self.result_tabs.setTabEnabled(index, visible)

    def set_research_mode(self, mode_id: str, *, reveal_single_detail: bool = False) -> None:
        """依研究目的篩選結果頁，並保證 primary tab 可見。"""
        mode = mode_id or "single_stock"
        mode_tabs = {
            "single_stock": {"summary", "diagnostics", "charts", "optimization", "legacy", "registry", "evidence"},
            "batch_stock": {"batch", "summary", "diagnostics", "charts", "registry", "evidence"},
            "fixed_basket": {"batch", "summary", "diagnostics", "charts", "registry", "evidence"},
            "recommendation_replay": {"recommendation", "registry", "evidence"},
            "strategy_research": {"optimization", "summary", "diagnostics", "charts", "legacy", "registry", "evidence"},
        }
        primary = {
            "single_stock": "summary",
            "batch_stock": "batch",
            "fixed_basket": "batch",
            "recommendation_replay": "recommendation",
            "strategy_research": "optimization",
        }.get(mode, "summary")
        allowed = mode_tabs.get(mode, mode_tabs["single_stock"])
        self._research_mode_id = mode
        for key in self._result_tab_widgets:
            self._set_result_tab_visible(key, key in allowed)

        current_key = self.result_tab_key(self.result_tabs.currentIndex())
        target = "summary" if reveal_single_detail else primary
        if current_key not in allowed or reveal_single_detail:
            if target in self._result_tab_widgets and target in allowed:
                self.focus_result_tab(target)
            else:
                for key in self._result_tab_widgets:
                    if key in allowed:
                        self.focus_result_tab(key)
                        break

        mode_labels = {
            "single_stock": "單股回測：摘要／診斷／圖表",
            "batch_stock": "批次回測：批次結果，可雙擊 drill-down",
            "fixed_basket": "固定清單逐檔回測：批次結果，不是共享現金組合",
            "recommendation_replay": "推薦回放：回放結果與證據",
            "strategy_research": "策略研究：最佳化／驗證與證據",
        }
        self.mode_context_label.setText(f"目前模式：{mode_labels.get(mode, mode)}")
        self.result_purpose_label.setText(
            "結果目的：雙擊批次單檔後可回到摘要與診斷；Registry 比較不等於可 promote。"
            if mode in {"batch_stock", "fixed_basket"}
            else "結果目的：先看模式主結果，再用分析診斷與證據頁複核。"
        )

    def update_analyst_diagnostics(self, diagnostics: object) -> None:
        if hasattr(self, "analyst_diagnostics_widget"):
            self.analyst_diagnostics_widget.set_diagnostics(diagnostics)

    def clear_analyst_diagnostics(self) -> None:
        if hasattr(self, "analyst_diagnostics_widget"):
            self.analyst_diagnostics_widget.clear()

    def add_registry_compare_tab(self):
        """將 Research Run Registry 比較頁掛入既有 Research Lab 結果分頁。"""
        existing = getattr(self, "run_registry_compare_widget", None)
        if existing is not None:
            return existing

        service = getattr(self.parent_view, "research_run_service", None)
        if service is None:
            return None

        self.run_registry_compare_widget = RunRegistryCompareWidget(
            service,
            on_open_recommendation_run=(
                self.parent_view._open_recommendation_registry_run
            ),
        )
        registry_banner = QLabel(
            "研究 Registry：正式研究 run 比較與 promotion evidence 入口；"
            "比較不等於可 promote，仍需通過既有驗證與升級條件。"
        )
        registry_banner.setWordWrap(True)
        registry_banner.setAccessibleName("研究 Registry 說明")
        registry_banner.setToolTip("Research Registry comparison and promotion evidence boundary")
        registry_banner.setStyleSheet(
            f"padding: 8px; color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-left: 4px solid {MIDNIGHT_ANALYST.info};"
        )
        registry_container = QWidget()
        registry_layout = QVBoxLayout(registry_container)
        registry_layout.addWidget(registry_banner)
        registry_layout.addWidget(self.run_registry_compare_widget)
        self._register_result_tab("registry", registry_container, "研究 Registry")
        self.set_research_mode(self._research_mode_id)
        return self.run_registry_compare_widget

    def add_forward_performance_tab(self):
        """Mount the read-only evidence review pages in Research Lab."""
        existing = getattr(self, "forward_performance_widget", None)
        if existing is not None:
            return existing

        config = getattr(self.parent_view, "config", None)
        if config is None:
            return None

        service = create_forward_performance_dashboard_service(config)
        self.forward_performance_widget = ForwardPerformanceView(service, auto_refresh=False)
        self.evidence_review_widget = EvidenceReviewView(
            forward_performance_widget=self.forward_performance_widget,
            live_gap_service=create_live_research_gap_dashboard_service(config),
            signal_decay_service=create_signal_decay_dashboard_service(config),
            decision_quality_service=create_decision_quality_dashboard_service(config),
            evidence_history_service=create_evidence_operations_history_dashboard_service(config),
            scheduled_status_service=ScheduledEvidenceStatusService(config),
            evidence_db_path=str(getattr(config, "db_file", "")),
        )
        self._register_result_tab("evidence", self.evidence_review_widget, "證據覆盤")
        self.set_research_mode(self._research_mode_id)
        return self.forward_performance_widget
