# 2026-10-12 研究基線歸檔核對

範圍：本套件與本次增加的索引關聯。以下記錄文件保存與核對，不是產品功能、模型效果或完整系統驗收。

於 2026-10-12 完成以下核對：

| 核對 | 結果與範圍 |
|---|---|
| 來源／保存完整性 | 20 項通過：五份原報告／版本／方法、五份歸檔內容、五份原 raw 診斷、量測摘要 hash、三庫摘要一致性，以及版本與方法的 exact byte copy。 |
| 文件工作流、連結與錨點 | `document_control.py check` exit 0；本次 15 個變更路徑與既有 11 項功能地圖結構核對通過，沒有缺件或錨點錯誤。 |
| 研究結論與數字保存 | 三份研究報告保留原結論及未驗證限制；歸檔摘要由既有 census 整理，長檔案分布與產品內部精確 AST 候選數值核對相符。 |
| 查找與適用範圍 | 中央 Index、External Blueprint、QA 與 Archive 共同指向同一入口；固定時點、增量確認與重構後另建新版的規則已寫入。 |

具名本機檢查產物為 ignored `output/tasks/research_baseline_archive_20261012/archive_integrity.json`、`document_check.json` 與 `task.json`。可分享的結論保存在本頁，完整 raw output 沒有移入文件庫。

本次未重跑全庫 census、Graphify、產品測試、真人 UX、效能 profiling、外部模型訓練或回測。這些項目與文件歸檔無關，沒有把它們列為已通過；實際產品資格仍按各自權威與具名收據判讀。程式、正式資料及排程沒有變更，兩份既有 dirty 文件未由本任務寫入。

來源、目的與 SHA-256 見 [ARCHIVE_MANIFEST](ARCHIVE_MANIFEST.json)；使用及增量更新規則見 [基線入口](README.md)。
