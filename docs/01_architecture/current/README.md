# 目前架構分冊

本目錄收納目前已存在模組的穩定責任與跨模組契約。系統入口、主要資料流與整體分層見[目前系統架構](../system_architecture.md)；目前完成度看[專案快照](../../00_core/PROJECT_SNAPSHOT.md)。

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
