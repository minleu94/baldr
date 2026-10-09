# 技術文檔目錄

> **技術細節和優化文檔**

本目錄包含系統的技術細節和優化相關文檔。

## 📄 文檔列表

- [歷史參數設計改進紀錄（Phase 2.5）](PARAMETER_DESIGN_IMPROVEMENTS.md)
  - 保存當時的參數建議與實施記錄；內文日期、優先級及「待執行」狀態不可直接當作目前待辦。

- [早期技術分析優化備忘錄（歷史）](../09_archive/TECHNICAL_ANALYSIS_OPTIMIZATIONS_HISTORY.md)
  - [舊路徑](technical_analysis_optimizations.md)保留短導引；原文的 API、回傳型態與資料路徑範例不符合目前實作。現況看系統架構與實際 source。

- **`UI_QT_CHART_RENDERING.md`**
  - Qt Backtest 圖表 fast Canvas renderer、payload layer 與 Matplotlib fallback 架構

- [路徑隔離功能更新說明（v1.3.0，歷史）](../09_archive/PATH_ISOLATION_UPDATE_V1_3_HISTORY_20241016.md)
  - 保存 2024-10-16 舊版本的命令、預設與測試記錄；目前路徑規則依 `TWStockConfig`、系統架構與操作手冊判讀。

- **`RUN_WITHOUT_VENV.md`**
  - 不使用虛擬環境運行指南

- **`MCP_YFINANCE_OPENMARKETS_PATCH_MEMO.md`**
  - openmarkets / yahoo-finance MCP 相容性修補備忘
  - 保存 `.venv` 重建後的本機 patch 與驗證方式

## 🔗 相關目錄

- `../00_core/` - 核心文檔
- `../02_features/` - 功能文檔

