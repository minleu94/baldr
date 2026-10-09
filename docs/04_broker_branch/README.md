# 券商分點相關文檔目錄

> **券商分點資料更新相關文檔**

本目錄包含所有與券商分點資料更新相關的文檔。

## 現行操作與安全指南

- **[手動整合檢查與故障排除](BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md)**（目前暫停其中三個整合腳本）
  - 2025 年指南中的腳本路徑與匯入根目錄不正確，且腳本可能連網／寫入 `DATA_ROOT`；勿視為一般 pytest。分類與執行邊界看 [tests_readme](../07_guides/tests_readme.md)。目前架構與操作看 [system_architecture](../01_architecture/system_architecture.md) 與 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

## 歷史設計與實作追溯

- **[早期設計、實作與改進文件封存專區](../09_archive/broker_branch/README.md)**
  - 收錄 2025-12 至 2026-01 的舊版資料模組設計、實作摘要、錯誤檢測與解析改進記錄。原路徑保留含 SHA-256 的相容導引；這些內容不代表目前架構、操作方式或待辦狀態。

## 🔗 相關目錄

- `../03_data/` - 數據相關文檔
- `../01_architecture/` - 架構文檔

