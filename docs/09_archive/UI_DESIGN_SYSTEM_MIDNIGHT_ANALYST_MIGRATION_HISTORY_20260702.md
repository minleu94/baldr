# Midnight Analyst UI 第一輪低風險遷移清單（2026-07-02 歷史摘錄）

> 本檔只保存 UI 設計系統文件中日期化的第一輪遷移完成清單。這是 2026-07-02 的歷史描述，不代表目前所有 UI 工作區已完成一致性檢查或 QA 全面驗收。

## 原文摘錄

2026-07-02 第一輪低風險遷移已完成下列範圍：

- 設計 token：新增資料正負色、低干擾邊框、表格 hover / selected 與溫和重點色。
- 全域 QSS：補齊 button variants、tooltip、表格 corner、水平 / 垂直 scrollbar 與空狀態框。
- 共用 helper：新增 `EmptyStatePanel`、`apply_financial_table_style()` 與 text sanitizer。
- 門面頁：每日決策與持倉管理已整理為較一致的工作台視覺。
- 主殼層：`LeftNavigationWidget` 使用 restrained Midnight Analyst left rail，主工作區由 `QStackedWidget` 切換；每個主工作區使用自製線條 SVG icon 協助掃描，expanded 狀態顯示 icon + label，collapsed 狀態只保留 icon；子工作區仍可使用上方 `QTabWidget`。
- Workbench：總覽頂部新增四個指揮台摘要 block，先顯示今日待判讀、人工待處理、等待真實時間與 Warnings；等待真實時間 block 應顯示 weekly history / multi-day dry-run 比例。Evidence / 持倉追蹤 / 操作節奏子頁目前定位為摘要與下鑽入口 / 預留深挖區，不應被文件或 UI 標成完整功能已完成。
- Runtime Observatory：頂部 scope note 應維持緊湊，讓任務狀態、治理健康與事件流靠近上方，不保留大片空白作為「未載入」式空間。
- 其他工作區：資料更新、推薦分析、回測、Watchlist、市場探索與 evidence review 相關表格已逐步套用通用表格與按鈕語言。

## 判讀界線

目前的 theme token、共用元件、QSS 與後續修改規則仍以 [`ui_design_system_midnight_analyst.md`](../01_architecture/ui_design_system_midnight_analyst.md) 為準；原文件保留第 9 節標題與「本輪遷移邊界」。此摘錄只記錄當時的完成範圍，不能用來推定現況或替代 QA 證據。
