# 資料資產用途與恢復登記

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
