# 券商分點手動整合檢查與故障排除：安全導引

> **停止執行（2026-10-08 警告仍有效）：請勿執行本指南中的三支手動整合腳本。** 舊命令指向不存在的 `scripts/` 路徑；檔案實際位於 `tests/scripts/`，且腳本的 `project_root` 仍指向 `tests/`。這些腳本會連網並呼叫資料更新，可能寫入 `TWStockConfig` 指定的 `DATA_ROOT`；全分點腳本還使用 `force_all=True`。它們是人工整合檢查，不屬於預設 pytest。只有在腳本 root 修正且 `DATA_ROOT` 已隔離後，才可重新評估是否執行。

原 2025-12-29 長篇測試與故障排除指南已移至 Archive，保留為歷史參考；不得將舊測試結果、腳本命令或 troubleshooting 步驟當成目前驗收與操作方式。

- [封存指南原文](../09_archive/broker_branch/BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md)
- 目前券商分點目錄：[本目錄 README](README.md)
- 現行操作與資料安全邊界：[Application Manual](../07_guides/APPLICATION_MANUAL.md)
- 自動測試、人工測試與 `tests/scripts/` 執行分類：[tests README](../07_guides/tests_readme.md)
- 歸檔原件、雜湊與引用追溯：[Coverage History Entry 155](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-155)
