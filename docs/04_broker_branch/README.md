# 券商分點相關文檔目錄

> **券商分點資料更新相關文檔**

本目錄包含所有與券商分點資料更新相關的文檔。

## 目前安全狀態與操作入口

- **[手動整合檢查指南（停止執行）](BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md)**：本頁是安全導引；2025 年長篇指南已封存。
  - 三支 `tests/scripts/` 手動整合腳本仍暫停：`project_root` 指向 `tests/`，腳本會連網並可能寫入 `DATA_ROOT`，全分點腳本使用 `force_all=True`。它們不是預設 pytest。修正 root 並確認隔離 `DATA_ROOT` 前請勿執行。分類看 [tests_readme](../07_guides/tests_readme.md)，現行操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

## 歷史設計與實作追溯

- **[早期設計、實作與改進文件封存專區](../09_archive/broker_branch/README.md)**
  - 收錄 2025-12 至 2026-01 的舊版資料模組設計、實作摘要、錯誤檢測與解析改進記錄。原路徑保留含 SHA-256 的相容導引；這些內容不代表目前架構、操作方式或待辦狀態。

## 🔗 相關目錄

- `../03_data/` - 數據相關文檔
- `../01_architecture/` - 架構文檔

