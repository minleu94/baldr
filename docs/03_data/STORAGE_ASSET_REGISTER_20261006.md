# 資料資產用途與恢復登記

## 2026-10-09 C 槽歷史封存更新

使用者明確授權後，六批歷史 QA／備份／2026-10-02 研究快照已搬至 `E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009`，12,862 檔、148.06 logical GiB，逐檔 SHA-256 複驗通過，原位置改為 Junction。實際 C 可用空間淨增加約 90.67 GiB，postflight 約剩 204.06 GiB；E 約剩 205.86 GiB。既有冷封存、正式 D 槽來源、近期候選、dist 及排程未改。精確範圍、收據與回滾見 [C 槽歷史 QA 冷封存](C_DRIVE_QA_COLD_ARCHIVE_20261009.md)。下方 10/06 容量與原地保留狀態是歷史盤點，不作為本輪目前位置；嚴格拒絕 reparse point 的歷史重跑需先還原普通目錄。補完計畫仍暫停。

## 2026-10-06 後續集中整理狀態

- 先前可恢復隔離已完成：repo 351 個根、Croot r015/r20/r26 17 個根，共 368 個、5,439,427,167 logical bytes。完整保留內容與 manifest，尚未釋放容量；隔離根為 `C:/Projects/RepositoryBackups/technical_analysis_temp_quarantine_20261006` 與 `C:/Projects/RepositoryBackups/technical_analysis_croot_temp_quarantine_20261006`。metadata 全量複驗 0 差異，正式來源／H20／私人配置保護項目 0 變更。
- 追加具名 10-root 計畫見[歷史測試集中清冊與還原指南](HISTORICAL_TEST_QUARANTINE_20261006.md)，共 5,633,484,456 logical bytes。用途、保留必要性、完整原新位置與還原方式已列出；空根只保存拓樸紀錄。
- 追加計畫尚未搬移：主要對話批准已轉送，但同命令重試一次後，執行任務的自動審核仍不接受轉送內容作為可信授權，於 CreateProcess 前拒絕。10 個來源原處保留，`C:/Projects/RepositoryBackups/historical_test_quarantine_20261006` 尚未建立；未再試或改路線。
- 批准記錄不是搬移證據。這批實際搬移量為 0 bytes；清冊的原位置仍是目前實際位置，目標位置只屬未執行計畫，durable manifest／證據副本未建立。
- 本頁下方 19:59 cleanup terminal 是當時紀錄；後續已隔離的根依上述 manifest 查詢，不把歷史盤點再計為目前 root 或已釋放容量。`C:/ta_iso_1005` 仍保留原處，直到追加搬移實際完成。

> 盤點時點：2026-10-06 19:21 UTC；cleanup terminal：19:59 UTC。容量為 logical GiB，部分是下限，不能當作可釋放空間。公開文件使用 `{REPO}`／`{DATA_ROOT}` 等 portable 說明，不包含個人 DB 內容或預測值。

## 分類與保留責任

| 路徑／角色 | Owner／用途與生成來源 | 引用與是否在用 | 量測 GiB | 保留與恢復／原位置歷史 |
|---|---|---|---:|---|
| `{DATA_ROOT}`（本機市場根 `D:/Min/Python/Project/FA_Data`） | Data／官方市場來源、技術資料、來源快照與模型 lineage；設定以 `TWStockConfig` 為準 | config、scheduled CMD 使用；不能視為 repo fixture | 482.429 | 原地保留；修復須依原 pins／before snapshot／receipt，不以目前 DB 冒充歷史來源 |
| `{DATA_ROOT}/personal` | 私人 owner／個人模型、持倉與私人使用資料 | 已實際啟用 H20；只核 metadata／manifest，不讀敏感 DB 或公開私人結果 | 包含於市場根，未獨立量測 | 私人資料原地保留；不得上傳 graphify／main；啟用／回滾依 exact revision 與原備份 |
| `{REPO}/output` | 各 producer／開發者；publication、Paper、研究、fit 與 QA 混合 | scheduled CMD、H20 fit receipt／source pins 有引用；非通用 cache | 185.212 下限 | 原地保留；failed raw／JUnit／receipts 不能改為綠；逐項 lineage 審核才可冷封存 |
| `D:/Min/Python/Project/FA_ML_Research` | ML research／current stock cycles、daily source rows／projections 與 registry | `output/ml_research_storage.json` 明示 active_root | 41.507 | 原地保留；研究資料不自動取得 formal／promotion 資格，owner 詳細責任未知待核 |
| `D:/Min/Python/Project/FA_Data_Shadow` | Shadow／learning capture 與 immutable lineage | calibration learning CMD 預設 root；Task 新鮮讀回未成功，僅核腳本與保存收據 | 0.514 | 保留；不能以正式市場根替代 decision-time lineage |
| `D:/Min/Python/Project/FA_Data_candidate` | Data repair／candidate DB、backfill reports 與修復 receipts | 修復文件引用；尚未證明無 consumer | 1.512 | 保留；不能當 formal DB 或因 candidate 命名清除 |
| `E:/FA_Data_ColdArchive` | 冷封存 owner／9/29 selective ZIP 與 rollback manifest | `cleanup_20260929_selective_v1` 六 ZIP；D 原檔已移除，現為唯一恢復來源 | 8.301 | 依 manifest 的 original→archive 及 rollback 操作恢復；不得再當重複檔刪除 |
| `E:/codex_model_repair_20260923` | ML repair／dataset、restatement、training／source 與 inference | restatement candidate source／dataset 模組有預設引用 | 6.543 | 保留；不等同安裝暫存，確切 current consumer closure 未完成 |
| `C:/ta_iso_1005` | Cleanup owner／879 個舊隔離 fixture／cache root | 108,054 檔現存 bytes；尚無另一 unique bytes backup | 4.513 | 保留；moves／restore manifest／restore.ps1 指回原位置；hash／路徑清單不是內容備份 |
| `C:/Projects/RepositoryBackups/technical_analysis_branch_recovery_20261007` | Git recovery owner／原 refs、HEAD、42 checkout extras、synthetic junction metadata | 42 舊 checkout 已移除；early RESTORE 說「仍在」是舊時點 | 2.072 | 唯一 refs／loose extras 恢復備份保留；按 RESTORE 與 closure receipt，先核目標不存在、不覆蓋現行 worktree |
| `{REPO}/.venv` | Runtime／目前 UI 與 scheduled CMD Python 環境 | 在用 | 1.304 | 保留；可依 pinned requirements 重建，但不是本輪資料清理 scope |
| `{REPO}/graphify-out` | Graphify／圖譜與 query memory／reflections／learning | 既有查詢記憶；非純可重建 cache | 0.601 | 原地保留；本輪新圖寫指定 ignored QA 分區，禁止覆蓋原記憶 |
| `{REPO}/output/plans` | 需求 owner／開發計畫，包括唯一 Danny Quant plan | 原需求與增量紀錄參照；是否全部另備份未知 | 未獨立量測 | 本輪唯一 plan 原路徑／bytes 保留並複製至本輪 original_bytes；其餘不搬、不清除 |
| `{REPO}/output/qa` | 各驗收 owner／raw、來源副本、screenshots、JUnit、immutable receipts | 包含真 model/source dependencies；日期不是失效證明 | 132.631，包含於 output | 原地保留；公開摘要與 raw 分離，任何移動先有內容備份與 old→new mapping |

容量不可相加：`personal`、`output/qa` 等為父 root 子集。D `release_v4` 366.698 GiB、scheduled 74.258 GiB、repo ML research 29.258 GiB 均已包含在各 root；PIT shards／模型 fold／before DB 不能稱為一般 cache。

## Cleanup terminal 的實際結果

只有 `{REPO}/.tb5pe`、`.tc1`、`.tlegacydebug`、`.tpersonalfails` 四個純空 root 共 8 目錄移除，檔案 logical bytes 為 **0**。按 pre-execution topology 可由淺至深建立原目錄，但 inode 身份會不同，不能保證原失敗場景。

14 份 UI DB 的當前 SHA 等於 preserved source；其他 Python 業務使用／dynamic consumer 未排除，全部保留。mypy／pytest 使用不明保留；graphify 查詢記憶保留。2070 Temp roots 的祖先讀取遭 Access denied，沒有繞過或改 ACL，全部保留。其餘 354 repo temp root 為 5,849,861,267 known logical bytes，包含來源／fixture／QA／恢復證據，全部保留。C 自由容量變動不是本輪釋放證明；沒有清除先前約 50.6 GiB 候選。

## 本機證據與 unknown

原盤點：`output/qa/baldr_storage_inventory_20261006/{report.md,inventory.csv,output_deep_report.md}`；最終處置：`approved_cleanup_terminal.md`、`approved_cleanup_final_receipt.json`、`repo_temp_empty_cleanup_receipt.json`。完整 exact paths／identity／pins 以本機 manifest 為準，不把敏感細節複製到公開文件。

精確 owner、dynamic process consumer、部分來源重新建置成本、是否存在其他 unique backup 與未量測子 root 均保留 unknown。本輪未新增外部備份、資料移動、Task／DB／模型／ACL 變更。下次容量更新須註明日期、logical／allocated、errors／下限及 terminal action；不能從 mtime 猜測無用。

## 2026-10-09 第二批封存追加索引

使用者針對精確清單授權後，28 個歷史 QA／備份與舊候選封裝已移至 `E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009_batch2_plain`，原位置建立 Junction。145,850 個檔案、36.57 logical GiB，兩輪全檔 SHA-256 核驗通過；28 個連結目標及 27 個非空根抽樣讀回相符。釋放程序期間 C 可用空間淨增加約 32.08 GiB，postflight C 約剩 213.27 GiB、E 約剩 168.89 GiB。保留現行／回退版本、d9a115f67d2b 及含 Junction 測試案例的 integration_20261002。精確清單、收據與回滾見 [第二批封存說明](C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md)。本段為追加，不改寫前述歷史盤點；補完計畫仍暫停。
