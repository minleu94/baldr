# baldr 專案目錄盤點

本頁列出穩定的程式、文件與發行目錄，協助開發者找入口；不記錄日期化狀態、QA 工作副本或本機資料清冊。功能到 UI／service／來源的逐項對照見[功能文件對照表](docs/00_core/FEATURE_DOCUMENT_MAP.json)。目前狀態與未解事項以[專案快照](docs/00_core/PROJECT_SNAPSHOT.md)為準。

## 核心程式目錄

| 目錄 | 職責 | 導航提示 |
|---|---|---|
| `ui_qt/` | 目前 PySide6 桌面 UI | 入口 `main.py`；工作區 Views 位於 `views/`。 |
| `app_module/` | Application service、協調流程與 DTO | 先由功能對照表定位 consumer，再讀系統架構的資料流。 |
| `decision_module/` | 策略設定、評分、篩選與市場狀態判讀 | 修改前遵守金融精度與 point-in-time 規則。 |
| `recommendation_module_legacy/` | 舊推薦模組的相容層 | 不因目錄名稱推定所有推薦入口都在此。 |
| `backtest_module/`、`financial_module/` | 回測、交易模擬與金融數值元件 | 依回測／績效功能對照查找實際 consumer。 |
| `portfolio_module/` | 持倉、交易帳本與研究用 Paper 契約 | 手動、聲明持倉與 Paper 資料各有不同來源和身份。 |
| `data_module/` | 市場資料設定、讀取、更新與來源治理 | 正式資料根由 `TWStockConfig` 決定；看 `data_module/config.py`。 |
| `ml_module/` | ML 資料、推論、模型治理與 shadow 能力 | candidate、shadow、自然結果及正式資格必須分開判讀。 |
| `analysis_module/`、`technical_analysis/` | 分析邏輯與技術分析支援 | 以功能對照表和目前架構確認呼叫路徑。 |
| `runtime/` | 任務執行、context、治理事件與 Runtime 狀態 | Runtime 可見性不等於產品、資料或排程已驗收。 |
| `utils/` | 共用工具與基礎元件 | 尋找目前引用者後再修改共用契約。 |
| `ui_app/` | 舊 Tkinter UI | 目前主要 UI 為 `ui_qt/`。 |

## 工具、測試與發行

| 目錄 | 用途 |
|---|---|
| `scripts/` | 資料維護、稽核、研究與排程 wrapper；各子目錄 README 是操作入口。 |
| `scripts/scheduled/` | Windows 排程 wrapper、Task 管理器與相關操作說明；先讀[排程運維指南](docs/07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)。 |
| `packaging/`、`dist/` | Windows 打包規格與本機候選輸出；`dist/` 產物不代表目前已發布版本。 |
| `tests/` | 契約、單元與整合測試；測試範圍依 repo 規則及功能對照表選擇。 |
| `examples/` | 文件使用的公開示例與 schema；私人路徑、帳戶及憑證不得放入。 |
| `notebooks/`、`test_data/` | 分析筆記與測試資料；不代表正式資料來源。 |
| `docs/` | Scoped SSOT、架構、功能、資料、QA、指南與歷史文件。 |

## 主要文件路徑

- 使用者：根目錄 [README](README.md) → [快速開始](docs/07_guides/QUICK_START.md)／[首次安裝 Prompt](docs/07_guides/FIRST_INSTALL_PROMPT.md) → [完整操作手冊](docs/07_guides/APPLICATION_MANUAL.md)。
- 新環境或移機：[機器啟動 Runbook](docs/07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md) → [排程運維與搬機指南](docs/07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)。
- 開發者：[PROJECT_NAVIGATION](PROJECT_NAVIGATION.md) → [功能文件對照表](docs/00_core/FEATURE_DOCUMENT_MAP.json) → [系統架構](docs/01_architecture/system_architecture.md)。
- Agent：[AGENTS.md](AGENTS.md) → `docs/agents/README.md`、`docs/agents/shared_context.md` 與角色文件。
- 現況與方向：狀態看 [PROJECT_SNAPSHOT](docs/00_core/PROJECT_SNAPSHOT.md)，產品方向看 [PRODUCT_ROADMAP_POST_REFACTOR](docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)，工程順序看 [ROADMAP_6M_ENGINEERING](docs/00_core/ROADMAP_6M_ENGINEERING.md)。

## 本機資料與輸出

市場資料預設位置和覆寫規則以 `data_module/config.py` 的 `TWStockConfig` 為準，正式資料根預設為 `F:/Min/Python/Project/FA_Data`，也可由 `DATA_ROOT` 覆蓋。2026-10-20 搬遷已將 repo 大型產出放到 `F:/Min/Python/Project/BaldrStorage`；D 舊根待開啟中的日誌程序退出後再完成清理，詳[搬遷紀錄](docs/06_qa/BALDR_STORAGE_MIGRATION_20261020.md)。研究輸出、私人資料、Paper 狀態、模型與本機 QA 輸出可能分屬不同根目錄；不得因根目錄名稱或最新修改時間推定所有權、用途或可刪除性。

`output/`、快取、虛擬環境、測試暫存及本機模型／帳戶資料是工作環境產物，不是來源控制下的產品說明。Stage／commit 前依 [git exclusions](docs/agents/git_exclusions.md) 排除不應提交的資料。
