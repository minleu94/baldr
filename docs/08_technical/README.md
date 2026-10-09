# 技術文檔目錄

> **技術細節和優化文檔**

本目錄包含系統的技術細節和優化相關文檔。

## 現況與歷史判讀

- 目前模組邊界與資料流以[系統架構](../01_architecture/system_architecture.md)為準；目前操作以[完整操作手冊](../07_guides/APPLICATION_MANUAL.md)及[安裝指南](../07_guides/INSTALL_GUIDE.md)為準。
- 本目錄的日期化參數建議、舊版本備忘與本機 patch 記錄用於追溯。它們不建立目前工程待辦，也不代表新環境的預設安裝步驟；目前優先順序看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與 [Roadmap Hub](../00_core/DEVELOPMENT_ROADMAP.md)。

## 📄 文檔列表

- [歷史參數設計改進紀錄（Phase 2.5）](PARAMETER_DESIGN_IMPROVEMENTS.md)
  - 保存當時的參數建議與實施記錄；內文日期、優先級及「待執行」狀態不可直接當作目前待辦。

- [早期技術分析優化備忘錄（歷史）](../09_archive/TECHNICAL_ANALYSIS_OPTIMIZATIONS_HISTORY.md)
  - [舊路徑](technical_analysis_optimizations.md)保留短導引；原文的 API、回傳型態與資料路徑範例不符合目前實作。現況看系統架構與實際 source。

- **`UI_QT_CHART_RENDERING.md`**
  - Qt Backtest 圖表 fast Canvas renderer、payload layer 與 Matplotlib fallback 架構

- [路徑隔離功能更新說明（v1.3.0，歷史）](../09_archive/PATH_ISOLATION_UPDATE_V1_3_HISTORY_20241016.md)
  - 保存 2024-10-16 舊版本的命令、預設與測試記錄；目前路徑規則依 `TWStockConfig`、系統架構與操作手冊判讀。

- [受限 System Python 備援](RUN_WITHOUT_VENV.md)
  - 只供已配置相容 runtime 的本機解譯器；新環境與 PowerShell activation 問題依 [INSTALL_GUIDE](../07_guides/INSTALL_GUIDE.md) 使用 `.venv`，不執行無約束全域安裝。

- [MCP Yahoo Finance / openmarkets 本機 patch 備忘（環境限定）](MCP_YFINANCE_OPENMARKETS_PATCH_MEMO.md)
  - 保存特定 Python／套件環境中的相容性觀察；沒有鎖定套件版本或 hash，不可直接當成新環境安裝或自動重套步驟。

## 🔗 相關目錄

- `../00_core/` - 核心文檔
- `../02_features/` - 功能文檔

