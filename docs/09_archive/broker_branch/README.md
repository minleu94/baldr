# 券商分點早期設計與實作歷史

本專區保留 2025-12 至 2026-01 的早期設計、實作摘要、解析／錯誤檢查記錄，以及 2025-12-29 手動測試與故障排除指南。封存原文供追溯，不作目前架構、操作、資料品質、驗收或待辦狀態依據。

| 封存原文 | 原始性質 | 判讀界線 |
|---|---|---|
| [資料模組設計 V2](BROKER_BRANCH_DATA_MODULE_DESIGN_V2_HISTORY.md) | 2025-12 版資料配置、欄位、流程與 Phase 1–3 建議 | 舊路徑範例與 Phase 建議不構成目前執行計畫；目前優先序以 Snapshot／6M Roadmap 為準 |
| [初期實作摘要](BROKER_BRANCH_IMPLEMENTATION_SUMMARY_HISTORY.md) | 2025-12 實作清單與當日測試結果 | 舊檔案與方法清單不代表目前模組邊界；當日測試不代表目前驗收 |
| [錯誤檢測改進](BROKER_BRANCH_ERROR_DETECTION_IMPROVEMENT_HISTORY.md) | 2026-01 錯誤頁面辨識與日誌改進記錄 | 不作為目前錯誤偵測行為的唯一說明 |
| [解析改進](BROKER_BRANCH_PARSING_IMPROVEMENT_HISTORY.md) | 2026-01 對手券商名稱解析案例與建議 | 不作為目前 parser 契約或來源資料品質的證明 |
| [手動整合測試與故障排除指南](BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md) | 2025-12-29 手動測試、troubleshooting 與歷史測試結果 | 三個人工整合腳本有 2026-10-08 停止警告；勿執行，舊測試結果不代表目前驗收 |

## 現行入口

- 目前模組邊界與資料流：[系統架構](../../01_architecture/system_architecture.md)
- 目前 UI 操作、同步與結果判讀：[Application Manual](../../07_guides/APPLICATION_MANUAL.md)
- 原路徑的停止警告與相容導引：[券商分點安全導引](../../04_broker_branch/BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md)；[封存長篇原文](BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md)
- 券商分點目錄：[目前導覽](../../04_broker_branch/README.md)
- 全域現況與工程優先序：[PROJECT_SNAPSHOT](../../00_core/PROJECT_SNAPSHOT.md)、[6M Engineering Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md)
- 四份早期設計／實作原件的追溯：[Coverage History Entry 126](../DOC_COVERAGE_HISTORY_2026.md#coverage-entry-126)；手動指南來源、雜湊與 Entry 126 決策更新：[Coverage History Entry 155](../DOC_COVERAGE_HISTORY_2026.md#coverage-entry-155)

本專區現在保存五份歷史原文。手動測試指南的原路徑只保留停止警告與導引；警告仍有效，歸檔不代表腳本已修復、隔離或通過驗收。本次未移動程式、資料或 QA 原始輸出。
