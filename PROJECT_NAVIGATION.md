# baldr 開發者導航

這份文件提供程式碼定位與功能閱讀路徑，不保存目前完成度或任務流水帳。產品目前狀態見 [PROJECT_SNAPSHOT](docs/00_core/PROJECT_SNAPSHOT.md)，現行模組邊界見[系統架構](docs/01_architecture/system_architecture.md)，使用步驟見[操作手冊](docs/07_guides/APPLICATION_MANUAL.md)。

## 依任務選入口

| 你要處理的工作 | 先看 | 再看 |
|---|---|---|
| 找某項 UI 功能、服務與資料來源 | [功能文件對照表](docs/00_core/FEATURE_DOCUMENT_MAP.json) | 對照表列出的功能文件、UI、application service 與來源模組 |
| 了解目前架構與資料流 | [系統架構](docs/01_architecture/system_architecture.md) | 對應 package 與測試；目標設計另看[最終目標架構](docs/01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) |
| 查目前工作、未解風險或產品界線 | [專案快照](docs/00_core/PROJECT_SNAPSHOT.md) | 依問題轉到 scoped authority 或具名 QA |
| 修改使用者可操作流程 | [完整操作手冊](docs/07_guides/APPLICATION_MANUAL.md) | [指南章節地圖](docs/07_guides/README.md)與對應功能文件 |
| 理解 Windows／Codex 排程 | [排程運維與搬機指南](docs/07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md) | [全排程唯讀稽核 Runbook](docs/07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)及 `scripts/scheduled/README.md` |
| 理解專案目錄與 package 職責 | [PROJECT_INVENTORY](PROJECT_INVENTORY.md) | 本文件的分層與功能表 |
| 變更程式或文件的治理流程 | [AGENTS.md](AGENTS.md) | [Coverage](docs/00_core/DOC_COVERAGE_MAP.md)、[任務上下文／Context CLI](docs/00_core/PRODUCT_CHANGE_WORKFLOW.md#任務上下文與漸進閱讀)與對應 Agent 文件 |

## 程式分層

| 層 | 主要位置 | 責任 |
|---|---|---|
| UI | `ui_qt/` | PySide6 主程式、工作區 View 與跨頁導覽；目前主入口是 `ui_qt/main.py`。`ui_app/` 是舊 Tkinter UI。 |
| Application | `app_module/` | 跨 domain 的流程協調、read model、service 與 typed DTO。 |
| Decision／Recommendation | `decision_module/`、`recommendation_module_legacy/` | 策略設定、評分、篩選與相容推薦邏輯；依功能對照表辨認目前 consumer。 |
| Backtest／Finance | `backtest_module/`、`financial_module/` | 回測執行、交易模擬、金融計算與績效讀模型。 |
| Portfolio | `portfolio_module/` | 持倉、帳本、研究用 Paper 及 Portfolio 來源契約。 |
| Data／ML | `data_module/`、`ml_module/` | 資料設定與讀取、來源治理、模型資料與推論支援。 |
| Runtime | `runtime/` | 任務、context、治理事件與執行狀態，不代表 UI 研究結果或正式授權。 |
| 工具 | `scripts/`、`packaging/`、`mcp_servers/` | CLI、排程 wrapper、Windows 打包與本機工具。執行前先讀各自 README／Runbook 和安全契約。 |

目標領域模型或尚未完成的 package 設計不代表現行程式已接線。判斷功能是否可用時，回到 Snapshot、目前系統架構、功能對照表與最新具名 QA，不以日期化計畫或單次測試推定整體接受。

## 高風險程式區

新增或修改策略、推薦、回測、行情設定與持倉計算前，先確認依賴、資料日期、金融精度及未來函數邊界：

- `decision_module/scoring_engine.py`、`decision_module/strategy_configurator.py`、`decision_module/stock_screener.py`
- `app_module/recommendation_service.py`、`app_module/backtest_service.py`、`app_module/walkforward_service.py`
- 回測、規則卡、Walk-forward 與參數掃描的新請求版本沿 `app_module/registered_strategy_spec.py` 讀 public Registry metadata；不改歷史 run。入口判讀見[回測指南](docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#選模式和研究範圍)。
- `backtest_module/performance_metrics.py`、`backtest_module/broker_simulator.py`
- `decision_module/market_regime_detector.py`
- `data_module/config.py`：`TWStockConfig` 是正式資料路徑的設定權威；不得由 repo 相對路徑猜測使用者資料位置。
- 法人固定候選批次沿 `app_module/institutional_daily_snapshot.py` 重驗原capture／parser／成功小時，`UpdateService`接正常UpdateView與純展示widget；開啟、雙SHA及候選界線見[資料操作指南](docs/07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#單獨保存-twse-法人候選)。
- Portfolio 配置研究封存沿 `app_module/portfolio_research_scenario_workspace.py` → 既有 scenario service／artifact／repository，正常入口是 `ui_qt/views/portfolio_view.py` 與 `ui_qt/widgets/portfolio_research_scenario_widget.py`；先讀[封存操作及來源界線](docs/07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#配置研究封存與另存假設)。
- 日曆接受配置沿`app_module/application_bootstrap.py`與`app_module/recommendation_portfolio_calendar_acceptance_binding_v1.py`定位，再看Main／Backtest結果面板的typed注入；來源接受與每日品質界線見[每日來源契約](docs/03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#tpex年度股票日曆候選解析)。

策略、回測、推薦、資金、倉位、風控、費用與績效等金融核心數值使用 `Decimal` 或有明確單位的整數格式。任何決策日期運算都只可使用當時已取得的資料。完整防線見 [AGENTS.md](AGENTS.md) 與 `docs/agents/skills/quant_defense_guard.md`。
