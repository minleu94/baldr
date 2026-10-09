# 技術文檔目錄

> **技術細節和優化文檔**

本目錄包含系統的技術細節和優化相關文檔。

## 現況與歷史判讀

- 目前模組邊界與資料流以[系統架構](../01_architecture/system_architecture.md)為準；目前操作以[完整操作手冊](../07_guides/APPLICATION_MANUAL.md)及[安裝指南](../07_guides/INSTALL_GUIDE.md)為準。
- 本目錄的日期化參數建議、舊版本備忘與本機 patch 記錄用於追溯。它們不建立目前工程待辦，也不代表新環境的預設安裝步驟；目前優先順序看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與 [Roadmap Hub](../00_core/DEVELOPMENT_ROADMAP.md)。

## 📄 目前技術文件

- [Qt 圖表呈現架構](UI_QT_CHART_RENDERING.md)：Backtest Canvas renderer、payload layer 與 Matplotlib fallback。
- [受限 System Python 備援](RUN_WITHOUT_VENV.md)：只供已配置相容 runtime 的本機解譯器；新環境依[安裝指南](../07_guides/INSTALL_GUIDE.md)使用 .venv，不執行無約束全域安裝。

## 歷史技術備忘

完整原件集中在 Archive；表中的舊路徑保留相容導引。原件雜湊、來源與歸檔判讀見[Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)及[Archive README](../09_archive/README.md)。

| Archive 原件 | 舊路徑導引 | 保留內容 |
|---|---|---|
| [Phase 2.5 參數設計改進](../09_archive/PARAMETER_DESIGN_IMPROVEMENTS_HISTORY.md) | [原路徑](PARAMETER_DESIGN_IMPROVEMENTS.md) | 當時的參數建議與實施狀態，不作目前待辦。 |
| [早期技術分析優化備忘](../09_archive/TECHNICAL_ANALYSIS_OPTIMIZATIONS_HISTORY.md) | [原路徑](technical_analysis_optimizations.md) | 舊 API、回傳型態與資料路徑範例；現況依系統架構與程式碼。 |
| [路徑隔離更新 v1.3.0](../09_archive/PATH_ISOLATION_UPDATE_V1_3_HISTORY_20241016.md) | [原路徑](path_isolation_update.md) | 2024-10-16 版本的命令、預設與測試記錄；原件識別見 [Coverage Entry 162](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-162)。 |
| [MCP Yahoo Finance／openmarkets 本機 patch](../09_archive/MCP_YFINANCE_OPENMARKETS_PATCH_MEMO_HISTORY.md) | [原路徑](MCP_YFINANCE_OPENMARKETS_PATCH_MEMO.md) | 環境限定診斷線索；未鎖套件版本或 hash，不直接作新環境安裝步驟。 |

## 🔗 相關目錄

- `../00_core/` - 核心文檔
- `../02_features/` - 功能文檔

