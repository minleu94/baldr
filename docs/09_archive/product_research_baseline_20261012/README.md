# 產品落差、程式規模與外部參考：2026-10-12 研究基線

本套件保存這次研究與盤點，供重構前的討論直接沿用。先選問題，再讀對應報告；固定日期的研究結論不代替目前產品狀態或工程優先序。

| 你要找什麼 | 從這裡開始 |
|---|---|
| 為什麼投入大量程式，產品仍不好理解、使用 | [產品落差診斷](PRODUCT_DIAGNOSIS.md) |
| 程式行數用在哪裡、大型檔案、重複候選 | [程式規模與維護負擔](REPOSITORY_SIZE_AUDIT.md) |
| 七個 GitHub 專案各自值得借鑑什麼 | [外部專案比較](EXTERNAL_REPO_COMPARISON.md) |
| KittenCN 的 Regime 是否使用 ML、適不適合移植 | [Regime ML 審查](STOCK_PREDICTION_REGIME_REVIEW.md) |
| 引用數值、來源版本或核對研究範圍 | [量測摘要](BASELINE_METRICS.json)、[七庫來源版本](SOURCE_BASELINES.json)、[來源與處置清冊](ARCHIVE_MANIFEST.json) |
| 歸檔完整性與連結檢查 | [歸檔核對](ARCHIVE_CHECK.md) |

## 這份基線能用多久

baldr 程式盤點固定於 `54f1e04d51f4057b04c9288b3ff6a733d6946a01` 的追蹤檔案工作樹；當時只有兩份文件有既有未提交變更，沒有產品程式差異。行數包括空白、註解與 docstring，不能用來代表功能數或執行速度。外部專案各有獨立來源版本，詳見報告與清冊。

**重構前沿用本基線，不因新開任務、換電腦或日期改變就重新盤點全庫。** 後續 Agent 與人員依下列方式使用：

1. 先讀本頁及問題對應的報告，引用數字時保留「2026-10-12 基線」標示。
2. 小幅變動先以本基線 commit 和目前工作樹的 Git diff 確認影響範圍；需要新數字時只補受影響的檔案或目錄。文件歸檔本身不使原產品程式統計失效。
3. 只有核心流程重構、模組責任／目錄大幅調整，或新增／移除主要子系統，才建立新版全庫盤點。未重算的數字繼續標成舊基線，不宣稱是即時統計。
4. 要採用外部原碼或依賴時，核對準備採用的確切版本及相關問題；保留本次研究作對照，不因上游有新 commit 就重做全部七庫比較。
5. 新基線使用新的日期套件並記錄差異；舊研究、失敗發現與來源 hash 保留，索引指向新入口。

## 使用邊界與保存方式

- 這是已結束研究的固定證據與診斷建議，不是新 Roadmap、重構授權、目前架構或功能驗收宣告。
- 靜態盤點沒有判定 unused、可刪除程式、實際重複計算或效能瓶頸；外部專案沒有做模型訓練、回測或收益排名。
- 本套件保存可分享的報告、整理後的量測摘要、來源版本及[量測方法原文](CENSUS_METHOD.py.txt)。沒有將完整逐檔 raw census、任務狀態、外部 clone 或快取搬進文件庫。
- 本機原始研究仍在 `output/tasks/external_stock_prediction_review_20261012/`、`output/tasks/external_repo_comparison_20261012/`、`output/tasks/repository_size_audit_20261012/`，維持 ignored 且未刪除。原路徑、bytes、SHA-256、歸檔目的及修訂範圍見清冊；報告版只修訂歸檔導航與時間語境。
- 移機後即使本機 raw output 不在，這些報告與關鍵數值仍可由此套件取得；需要超出本次摘要的逐檔原始診斷時，再核對本機原件或建立具名的增量調查。

目前狀態看 [Project Snapshot](../../00_core/PROJECT_SNAPSHOT.md)，產品成立條件看 [Product Roadmap](../../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)，工程順序看 [6M Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md)。外部研究由 [External Reference Blueprint](../../00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md) 導覽；完整文件入口見 [Documentation Index](../../00_core/DOCUMENTATION_INDEX.md)。
