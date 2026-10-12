# 指南與操作手冊目錄

> **使用指南、快速參考與專項維護 Runbook**

本目錄包含系統的使用者操作指南、開發者環境說明以及專案受控演練與維護 Runbook。

## 📄 文檔列表

### 1. 核心使用與上手
- **[APPLICATION_MANUAL.md](APPLICATION_MANUAL.md)**
  - 目前 PySide6 UI 的完整操作手冊（SSOT）
  - 涵蓋目前 9 個頂層工作區、跨工作區流程、參數設定、結果判讀、安全限制與排錯
  - 第 14 節後最初的 2026-10-03 至 10-08 日期化開發／候選紀錄及 10/11 移存的歷史排程／研究模板，已移至 [Archive](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md)；手冊尾段以舊書籤導引為主，仍保留少數操作摘要，例如 [9.9.1h BBANDS 保存研究條件](APPLICATION_MANUAL.md#991h-h20-gross-每日收據與-bbands-上軌保存版別2026-10-06)。
- **[APPLICATION_MANUAL_SUPPLEMENTS.md](APPLICATION_MANUAL_SUPPLEMENTS.md)**
  - 操作手冊附冊：保留較長的日期化操作補充、進階研究 CLI、排程與受控維運，以及從主手冊前置區移入的歷史原文；不另作目前狀態權威
- **[QUICK_START.md](QUICK_START.md)**
  - 系統快速開始指南（三步啟動）
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)**
  - 常用命令、操作流程與常見問題速查
- **[INSTALL_GUIDE.md](INSTALL_GUIDE.md)**
  - 系統安裝與環境設置指南（Python 3.11、虛擬環境、依賴與資料路徑）

### 操作手冊章節地圖

APPLICATION_MANUAL 是目前操作權威，篇幅較長；依任務讀相關章節即可。跨工作區流程讀取涉及的章節；日期化工程補充只在與本次功能相關時閱讀，並沿章節連結查看 QA 證據。

主手冊正文從第 1 章開始；原先堆在章首的日期化補充已移入附冊，初始 2026-10-03 至 10-08 的開發／候選快照及 10/11 後續移存的歷史排程／研究模板則移入 Archive。第 14 節後以歷史導引為主，但少數章節仍保留操作摘要，應依章節內容與 QA 連結辨認；功能是否已交付與驗收，仍以 Snapshot 和具名 QA 為準。

| 任務 | 在 APPLICATION_MANUAL 搜尋的章節標題 |
|---|---|
| 系統概覽、安裝與啟動 | 1. 系統能做什麼、2. 安裝與啟動 |
| Advice、每日建議與每日決策 | Gate 1 Advice：決策工作台的唯讀操作、3. 每日建議流程、8. 每日決策（Daily Decision Desk） |
| 資料更新、資料狀態、來源與 SQLite | 4. 數據更新 |
| 市場探索 | 5. 市場探索 |
| 推薦分析與結果判讀 | 6. 推薦分析 |
| 觀察清單與選股清單 | 7. 觀察清單與選股清單 |
| Research Lab、策略回測 | 9. Research Lab / 策略回測；[9.9.1h BBANDS 保存研究條件](APPLICATION_MANUAL.md#991h-h20-gross-每日收據與-bbands-上軌保存版別2026-10-06) |
| 持倉管理 | 10. 持倉管理 |
| Runtime 與營運監控 | 11. Runtime Observatory（Owner 營運與治理監控） |
| 常見問題與覆蓋狀態 | 12. 常見問題、13. Manual 覆蓋狀態 |
| 進階研究、日期化維運補充 | [APPLICATION_MANUAL_SUPPLEMENTS](APPLICATION_MANUAL_SUPPLEMENTS.md)；依章節連結核對對應 QA 與目前狀態 |
| 舊版開發／候選功能快照 | [APPLICATION_MANUAL 日期化工程筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md)；只供追溯，原手冊標題保留轉址 |

日期化細節若未整合到相應章節，再搜尋 APPLICATION_MANUAL_SUPPLEMENTS 的相關標題。不要把單次 QA 收據當成目前操作權威；接受狀態回到對應 QA 或 PROJECT_SNAPSHOT 核對。

### 2. 目錄與程式庫指南
- **[scripts_readme.md](scripts_readme.md)**
  - `scripts/` 目錄下的腳本說明、分類、執行順序建議與路徑隔離
- **[tests_readme.md](tests_readme.md)**
  - `tests/` 目錄結構、測試分類、契約邊界與 healthcheck runner 規範

### 3. 日常維護與覆盤 Runbook
- **[V2_2_WEEKLY_REVIEW_RUNBOOK.md](V2_2_WEEKLY_REVIEW_RUNBOOK.md)**
  - V2.2 人工 Evidence Review、working-copy DB 安全操作、sidecar 收集與 append-only history 操作邊界
- **[P0_DAILY_SOURCE_CANDIDATE_RUNBOOK.md](P0_DAILY_SOURCE_CANDIDATE_RUNBOOK.md)**
  - 2026-07-19 前後的 13 項 P0 候選來源唯讀品質稽核範例、結果判讀與排程隔離邊界；現行來源與接受狀態須核對具名 QA、Snapshot 及排程實作

### 4. 專項研發與歷史修復 Runbook
- **[EVIDENCE_REHEARSAL_RUNBOOK.md](EVIDENCE_REHEARSAL_RUNBOOK.md)**
  - 受控證據演練 Runbook，說明 `scripts/run_evidence_rehearsal.py` 的 projection_only 與 working_copy_e2e 模式與安全邊界
- **[HISTORICAL_ML_SHADOW_RUNBOOK.md](HISTORICAL_ML_SHADOW_RUNBOOK.md)**
  - 歷史 ML Shadow 訓練與選模 Runbook（Terra Development Dataset V0）
- **[ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md](ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md)**
  - ML Shadow 單日推論操作 Runbook，說明 `scripts/run_ml_shadow_inference.py` 契約驗證與 rollback 模擬
- **[PIT_HISTORICAL_DATA_REPAIR_RUNBOOK.md](PIT_HISTORICAL_DATA_REPAIR_RUNBOOK.md)**
  - PIT 歷史資料修復 Runbook，說明月營收、季度財報 availability mapping 與 coverage audit

### 5. Windows 發布、排程搬機與歷史修復

- **[BALDR_SCHEDULED_AUDIT_RUNBOOK.md](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)**
  - 兩個Codex operational heartbeat的共同21-task唯讀查核、實際來源根、期限、資料品質、通知與排錯規則。
- **[EVIDENCE_SCHEDULED_MORNING_CHECK.md](EVIDENCE_SCHEDULED_MORNING_CHECK.md)**
  - 舊晨間檢查路徑的相容導引；封存原文保留在 `docs/09_archive/`，目前排程稽核請看上方共同 Runbook。
- **[PORTABLE_WINDOWS.md](PORTABLE_WINDOWS.md)**
  - 可攜 Windows 版的資料夾要求、首次啟動、設定位置與已驗／未驗邊界
- **[SCHEDULE_OPERATIONS_AND_MIGRATION.md](SCHEDULE_OPERATIONS_AND_MIGRATION.md)**
  - Windows Task Scheduler 與 Codex 排程用途、搬機前提及受控驗收；私人任務清冊不在此文件
- **[PHASE3C_CANDIDATE_REPAIR_RUNBOOK.md](PHASE3C_CANDIDATE_REPAIR_RUNBOOK.md)**
  - 2026-09-11 candidate DB 的隔離法人資料修復歷史 runbook；不適用於正式資料庫或目前日常操作

### 6. 已封存的歷史工作計畫

- [LUNA 平行工作計畫舊路徑導引](LUNA_PARALLEL_PLAN_2026_09_07.md)：原始計畫與[整併檢查](../06_qa/PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md)、[整合結案收據](../09_archive/LUNA_INTEGRATION_CLOSEOUT_2026_09_08.md)均可由此追溯。該輪工作已於 2026-09-08 結案，不是目前任務清單；逐檔來源與 SHA 見 [Coverage History Entry 118](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-118)。

## 🔗 相關目錄

- `../00_core/DOCUMENTATION_INDEX.md` - 全域文檔索引
- `../00_core/PROJECT_SNAPSHOT.md` - 目前專案狀態
- `../03_data/` - 數據相關文檔
- `../09_archive/` - 歷史任務與過期文檔歸檔
