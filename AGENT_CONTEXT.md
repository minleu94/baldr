# Agent／Developer 快速導航

baldr 是一套可驗證、可回溯、可演化的台股研究與投資決策工作台。這份文件只導覽穩定入口，不保存日期化 readiness、任務狀態或第二套工作流程。

## 開始任務

依根目錄 [`AGENTS.md`](AGENTS.md) 開工：先讀共同安全規範，再讀目前狀態摘要，再由唯一人類路由入口 [`docs/agents/skills_registry.md`](docs/agents/skills_registry.md) 選角色。多階段工作使用 [`docs/agents/skills/team.md`](docs/agents/skills/team.md)。

## Scoped SSOT

| 問題 | 權威入口 |
|---|---|
| 目前狀態與當前風險 | `docs/00_core/PROJECT_SNAPSHOT.md` |
| 產品方向與現行資料來源優先序 | `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md` |
| 六個月工程里程碑 | `docs/00_core/ROADMAP_6M_ENGINEERING.md` |
| 長期產品成熟度 | `docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md` |
| Roadmap 導覽、舊工作承接 | `docs/00_core/DEVELOPMENT_ROADMAP.md`、`LEGACY_ROADMAP_CARRYOVER.md` |
| 現行架構 | `docs/01_architecture/system_architecture.md` |
| 目標領域背景與目標實作設計 | `docs/01_architecture/target_system_architecture.md`、`target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md` |
| 使用者操作 | `docs/07_guides/README.md` 章節地圖、`APPLICATION_MANUAL.md` 相關章節 |
| 文件位置與生命週期 | `docs/00_core/DOCUMENTATION_INDEX.md`、`DOCUMENTATION_STRUCTURE.md` |
| 文件 coverage 與變更流程 | `DOC_COVERAGE_MAP.md`、`FEATURE_DOCUMENT_MAP.json`、`PRODUCT_CHANGE_WORKFLOW.md` |

依任務載入相關文件，不將此導航表當成每項任務都要完整閱讀的清單。日期化歷史只供相關主題追溯。

## 主要程式入口

- PySide6 UI：`ui_qt/main.py`
- Application services：`app_module/`
- Decision domain：`decision_module/`
- Backtest：`backtest_module/`
- Portfolio：`portfolio_module/`
- Runtime：`runtime/`
- Data、SQLite 與設定：`data_module/`
- QA／維護工具：`scripts/`

資料路徑、量化精度、Look-ahead bias、程序管理、Git 與未提交變更等共同硬規則見 [`docs/agents/shared_context.md`](docs/agents/shared_context.md)。Antigravity／Gemini CLI 的平台適配見 [`GEMINI.md`](GEMINI.md) 及 `.agent/rules/`。

## 任務狀態

多階段本機任務狀態位於 `output/tasks/<task_id>/task.json`，建立與 legacy singleton 所有權見 [`docs/agents/shared_state/README.md`](docs/agents/shared_state/README.md)。它不取代 Snapshot 或其他產品狀態權威。

## 更新記錄

- 2026-10-12：改為穩定入口與 Scoped SSOT 導覽，不複製完整必讀清單、硬規則或日期化任務狀態。
