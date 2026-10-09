# 券商分點早期設計與實作歷史

本專區保留 2025-12 至 2026-01 的早期設計、實作摘要與解析／錯誤檢查記錄。封存原文供追溯，不作目前架構、操作、資料品質、驗收或待辦狀態依據。

| 封存原文 | 原始性質 | 判讀界線 |
|---|---|---|
| [資料模組設計 V2](BROKER_BRANCH_DATA_MODULE_DESIGN_V2_HISTORY.md) | 2025-12 版資料配置、欄位、流程與 Phase 1–3 建議 | 舊路徑範例與 Phase 建議不構成目前執行計畫；目前優先序以 Snapshot／6M Roadmap 為準 |
| [初期實作摘要](BROKER_BRANCH_IMPLEMENTATION_SUMMARY_HISTORY.md) | 2025-12 實作清單與當日測試結果 | 舊檔案與方法清單不代表目前模組邊界；當日測試不代表目前驗收 |
| [錯誤檢測改進](BROKER_BRANCH_ERROR_DETECTION_IMPROVEMENT_HISTORY.md) | 2026-01 錯誤頁面辨識與日誌改進記錄 | 不作為目前錯誤偵測行為的唯一說明 |
| [解析改進](BROKER_BRANCH_PARSING_IMPROVEMENT_HISTORY.md) | 2026-01 對手券商名稱解析案例與建議 | 不作為目前 parser 契約或來源資料品質的證明 |

## 現行入口

- 目前模組邊界與資料流：[系統架構](../../01_architecture/system_architecture.md)
- 目前 UI 操作、同步與結果判讀：[Application Manual](../../07_guides/APPLICATION_MANUAL.md)
- 尚保留的手動整合檢查與安全警告：[券商分點故障排除指南](../../04_broker_branch/BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md)
- 券商分點目錄：[目前導覽](../../04_broker_branch/README.md)
- 全域現況與工程優先序：[PROJECT_SNAPSHOT](../../00_core/PROJECT_SNAPSHOT.md)、[6M Engineering Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md)
- 原件路徑、bytes／SHA 與引用核對：[Coverage History Entry 126](../DOC_COVERAGE_HISTORY_2026.md#coverage-entry-126)

本次只整理四份歷史文件的位置，未移動程式、資料或 QA 原始輸出。`BROKER_BRANCH_TESTING_AND_TROUBLESHOOTING.md` 仍包含有效安全警告，因此留在原目錄與操作入口。
