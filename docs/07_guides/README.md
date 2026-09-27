# 指南與操作手冊目錄

> **使用指南、快速參考與專項維護 Runbook**

本目錄包含系統的使用者操作指南、開發者環境說明以及專案受控演練與維護 Runbook。

## 📄 文檔列表

### 1. 核心使用與上手
- **[APPLICATION_MANUAL.md](APPLICATION_MANUAL.md)**
  - 目前 PySide6 UI 的完整操作手冊（SSOT）
  - 涵蓋 8 個頂層工作區、跨工作區流程、參數設定、結果判讀、安全限制與排錯
- **[APPLICATION_MANUAL_SUPPLEMENTS.md](APPLICATION_MANUAL_SUPPLEMENTS.md)**
  - 操作手冊附冊：保留日期化操作補充、進階研究 CLI、排程與受控維運；與主手冊共同維護，不另作目前狀態權威
- **[QUICK_START.md](QUICK_START.md)**
  - 系統快速開始指南（三步啟動）
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)**
  - 常用命令、操作流程與常見問題速查
- **[INSTALL_GUIDE.md](INSTALL_GUIDE.md)**
  - 系統安裝與環境設置指南（Python 3.11、虛擬環境、依賴與資料路徑）

### 2. 目錄與程式庫指南
- **[scripts_readme.md](scripts_readme.md)**
  - `scripts/` 目錄下的腳本說明、分類、執行順序建議與路徑隔離
- **[tests_readme.md](tests_readme.md)**
  - `tests/` 目錄結構、測試分類、契約邊界與 healthcheck runner 規範

### 3. 日常維護與覆盤 Runbook
- **[EVIDENCE_SCHEDULED_MORNING_CHECK.md](EVIDENCE_SCHEDULED_MORNING_CHECK.md)**
  - Evidence scheduled dry-run 的每日早晨人工檢查步驟與停用方式
- **[V2_2_WEEKLY_REVIEW_RUNBOOK.md](V2_2_WEEKLY_REVIEW_RUNBOOK.md)**
  - V2.2 人工 Evidence Review、working-copy DB 安全操作、sidecar 收集與 append-only history 操作邊界
- **[P0_DAILY_SOURCE_CANDIDATE_RUNBOOK.md](P0_DAILY_SOURCE_CANDIDATE_RUNBOOK.md)**
  - 13 項 P0 候選資料來源唯讀品質稽核指令、結果判讀與排程隔離邊界

### 4. 專項研發與歷史修復 Runbook
- **[EVIDENCE_REHEARSAL_RUNBOOK.md](EVIDENCE_REHEARSAL_RUNBOOK.md)**
  - 受控證據演練 Runbook，說明 `scripts/run_evidence_rehearsal.py` 的 projection_only 與 working_copy_e2e 模式與安全邊界
- **[HISTORICAL_ML_SHADOW_RUNBOOK.md](HISTORICAL_ML_SHADOW_RUNBOOK.md)**
  - 歷史 ML Shadow 訓練與選模 Runbook（Terra Development Dataset V0）
- **[ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md](ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md)**
  - ML Shadow 單日推論操作 Runbook，說明 `scripts/run_ml_shadow_inference.py` 契約驗證與 rollback 模擬
- **[PIT_HISTORICAL_DATA_REPAIR_RUNBOOK.md](PIT_HISTORICAL_DATA_REPAIR_RUNBOOK.md)**
  - PIT 歷史資料修復 Runbook，說明月營收、季度財報 availability mapping 與 coverage audit

## 🔗 相關目錄

- `../00_core/DOCUMENTATION_INDEX.md` - 全域文檔索引
- `../00_core/PROJECT_SNAPSHOT.md` - 目前專案狀態
- `../03_data/` - 數據相關文檔
- `../09_archive/` - 歷史任務與過期文檔歸檔
