# 目前架構分冊

本目錄收納目前已存在模組的穩定責任與跨模組契約。系統入口、主要資料流與整體分層見[目前系統架構](../system_architecture.md)；目前完成度看[專案快照](../../00_core/PROJECT_SNAPSHOT.md)。

## 從入口到責任

Windows 啟動由 baldr_launcher.py 交給 ui_qt/main.py；UI 組裝工作區並把明確請求交給 app_module/。Application 組合 use case、來源與服務，注入 data_module/ reader／writer，呼叫領域模組，再將 DTO 回傳 UI。View 不直接讀寫正式資料或重做領域計算。這是責任方向摘要，不代表每條路徑都已接線或通過產品 Gate；能力與現況依本頁指向的 scoped SSOT 與 Snapshot。

| 責任 | 主要模組 | 上游／下游 |
|---|---|---|
| 輸入、導航、DTO 呈現與 worker lifecycle | ui_qt/ | 使用者 → app_module/ |
| use case 組合、身份驗證、服務與 DTO | app_module/ | UI → data_module/ reader／writer 與領域模組 |
| 資料來源、正式 reader／writer、保存資料 | data_module/ | 由 application 明示注入；讀取結果回 application |
| 策略／推薦契約、分析、回測、Portfolio 與金融核心 | decision_module/、analysis_module/、backtest_module/、portfolio_module/、financial_module/ | application 傳入契約資料；結果回 application |
| Runtime 事件與健康狀態 | runtime/ | application 封裝 Runtime DTO，再呈現於 Runtime Observatory |
| 受治理模型研究與 shadow 路徑 | ml_module/ | 不因 package 存在而取得正式推薦權限 |

九個工作區與 Daily Decision Desk 所在位置見[UI 與應用流程](application_and_workspaces.md)；Recommendation、Backtest、Portfolio 深層契約見[決策、研究與 Portfolio](decision_research_portfolio.md)；來源與保存責任見[資料、保存與 Runtime](data_storage_runtime.md)。

## 依問題閱讀

| 想了解 | 分冊 | 範圍 |
|---|---|---|
| 工作區、UI 與 application service 如何組合 | [UI 與應用流程](application_and_workspaces.md) | 九個工作區、Daily Decision Desk 位置、服務組合、執行與呈現邊界 |
| 推薦、回測、Portfolio 與 Evidence 如何互動 | [決策、研究與 Portfolio](decision_research_portfolio.md) | 決策核心、時間軸、金融數值、組合資料種類、證據與 ML 權限 |
| 來源、SQLite、保存資料及排程如何隔離 | [資料、保存與 Runtime](data_storage_runtime.md) | 資料根目錄、來源可得日、讀寫模式、保存身份、Runtime 與排程 |

## 實際模組地圖

目前程式使用 `ui_qt/`、`app_module/`、`decision_module/`、`backtest_module/`、`portfolio_module/`、`data_module/`、`analysis_module/`、`financial_module/`、`ml_module/`、`development_module/` 與 `runtime/`。這份清單描述 repo 中實際存在的 package；不代表其中每個研究或目標能力已通過產品 Gate。

`ui_qt/main.py` 是 PySide6 主程式入口；`baldr_launcher.py` 是 Windows launcher。`app_module/` 組合 use case 與 DTO；領域計算和資料取得分屬各自 package。Target-only package 與責任拆分方案請讀[目標架構導覽](../target_system_architecture.md)，實作設計唯一權威是 [FINAL_TARGET_ARCHITECTURE](../target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)。

本目錄只保存穩定的 current 契約。日期化驗收數字應讀對應 QA 收據；舊狀態與來源 bytes 由 `docs/09_archive/` 的封存副本及治理 manifest 追溯，不按文件先後推斷現況。
