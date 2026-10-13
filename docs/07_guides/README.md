# 指南與操作手冊

這裡提供首次安裝、日常 UI 操作、可攜版設定，以及 Windows／Codex 排程維運入口。一般使用者先看「快速開始」；已有資料或排程的 owner 搬機先看機器啟動 Runbook。

## 依情境開始

| 情境 | 入口 |
|---|---|
| 全新安裝或第一次設定 | [首次安裝 Prompt](FIRST_INSTALL_PROMPT.md) → [安裝指南](INSTALL_GUIDE.md) → [快速開始](QUICK_START.md) |
| 使用整包 Windows 可攜版 | [可攜版指南](PORTABLE_WINDOWS.md) |
| 新電腦接手舊環境、資料或排程 | [機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md) → [排程運維與搬機指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md) |
| 查一般 UI 日常操作 | [完整操作手冊](APPLICATION_MANUAL.md) → [主題手冊地圖](manuals/README.md) |
| 唯讀核對全部 baldr 排程 | [全排程唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md) |

## 完整操作手冊章節地圖

主手冊先列日常旅程，再連到三份主題手冊；安裝與排程維運各有獨立入口。以下路徑可用來定位操作、參數、結果判讀、安全限制與排錯內容。

| 工作 | 手冊章節 |
|---|---|
| 安裝、啟動及四種日常情境 | [APPLICATION_MANUAL §1–3](APPLICATION_MANUAL.md#1-日常使用旅程) |
| 資料狀態、快速／安全更新與市場探索 | [資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md) |
| Recommendation、個股研究與 Research Lab | [推薦與 Research Lab](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md) |
| 觀察清單、個股報告與持倉 | [觀察清單與持倉](manuals/WATCHLIST_AND_PORTFOLIO.md) |
| 已保存 Paper 健康評估的明示選取與回訪 | [已保存健康評估與回訪](manuals/WATCHLIST_AND_PORTFOLIO.md#已保存健康評估與回訪) |
| Daily Decision Desk、結果品質與共通排錯 | [APPLICATION_MANUAL §8–12](APPLICATION_MANUAL.md#8-每日決策-daily-decision-desk) |
| Windows Task Scheduler 與 Codex 排程 | [排程運維與搬機指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)及[全排程唯讀稽核](BALDR_SCHEDULED_AUDIT_RUNBOOK.md) |

## 開發與受控維運指南

- [scripts 說明](scripts_readme.md)：`scripts/` 的分類與執行入口。
- [tests 說明](tests_readme.md)：測試組織與驗收路由。
- [週度 Review Runbook](V2_2_WEEKLY_REVIEW_RUNBOOK.md)：Evidence Review、working-copy DB 與 sidecar 操作邊界。
- [P0 Daily Source Candidate Runbook](P0_DAILY_SOURCE_CANDIDATE_RUNBOOK.md)：資料來源候選的唯讀品質稽核；現況仍依 Snapshot 與具名 QA 判讀。
- [Evidence rehearsal](EVIDENCE_REHEARSAL_RUNBOOK.md)、[ML Shadow 推論](ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md)、[歷史資料修復](PIT_HISTORICAL_DATA_REPAIR_RUNBOOK.md)：限定工程與維運操作，使用前先確認資料根、scope 與授權。

日期化工程筆記與原始文件版本供[歷史封存區](../09_archive/README.md)追溯；封存內容不能單獨作為目前操作或驗收依據。現況看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，架構看[系統架構](../01_architecture/system_architecture.md)。
