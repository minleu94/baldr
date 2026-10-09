# C 槽歷史 QA 冷封存狀態對照（2026-10-09）

> 本頁依 E 槽逐批收據及 C 槽目錄／Junction metadata 對照兩批封存文件。第二批終態收據於 2026-10-09 21:37:40 UTC 寫入；C 槽 Junction 對照於 21:37:45 UTC 核對。它是搬移狀態的 QA 導覽與核對摘要；精確目錄用途、原始複製紀錄與還原步驟仍見資料資產文件。此次只讀收據與 metadata，沒有重新雜湊或掃描完整資料樹。

## 目前狀態

| 批次 | 計畫範圍 | 複製／SHA 收據 | C 槽來源狀態 | 結論 |
|---|---:|---:|---|---|
| 第一批 `baldr_c_drive_archive_20261009` | 6 個根、12,862 個檔案、158,977,761,695 logical bytes（約 148.06 GiB） | 6 份逐根複製收據、SHA 清單、release-ready 與 released 收據；`released_complete.json` 為 `complete` | 6/6 為 Junction，目標均與收據所列 E 槽路徑相符且存在 | 收據記錄全檔 SHA-256 核驗後完成封存；本次只核收據與連結 metadata，沒有重算全部 SHA。 |
| 第二批 `baldr_c_drive_archive_20261009_batch2_plain` | 28 個根、145,850 個檔案、39,268,782,429 logical bytes（約 36.57 GiB；精確根清單見[第二批範圍表](../03_data/C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md#精確範圍)） | 28 份逐根複製收據、SHA 清單、release-ready 與 released 收據；`released_complete.json` 為 `complete`，28 根皆為 `archived_verified_junction_installed` | 28/28 為 Junction，目標均與收據所列 E 槽路徑相符且存在 | **截至上述終態收據與 Junction 核對時，第二批完成。** 本次沒有重新計算完整資料樹的 SHA。 |

兩批合計 34 個根、158,712 個檔案、198,246,544,124 logical bytes（約 184.62 GiB）。邏輯資料量不等於磁碟實際釋放量。

## 狀態變化與判讀邊界

- 第二批狀態在稽核過程中從 22/28、24/28、26/28 逐步變成 28/28；這些是中間讀取，不作最終狀態。最終依據為 E 槽 `released_complete.json`（`status=complete`、28 根）及 2026-10-09 21:37:45 UTC 對 28 個 C 槽項目的唯讀檢查（28 個 Junction、目標相符、E 目標存在）。
- 第一批容量收據記錄 C 可用空間由 121,755,623,424 bytes 增至 219,108,855,808 bytes，觀察差為 97,353,232,384 bytes（約 90.67 GiB）。第二批終態收據記錄由 194,551,021,568 bytes 增至 228,999,462,912 bytes，觀察差為 34,448,441,344 bytes（約 32.08 GiB）；E 槽終態可用空間記錄為 181,347,819,520 bytes。批次間 C 槽起始值與前批終值不同，代表不同時間點，不可相加推算整段淨釋放量；所有可用空間值都不是目前即時容量。
- 本次稽核依據逐批收據、SHA 清單 metadata、終態收據及 C 槽 reparse/Junction metadata；沒有重新計算任何封存樹的全量 SHA。原始全檔比對只按各批執行收據所記錄結果表述。

## 授權、精確範圍與收據定位

- 第一批執行說明記錄了使用者授權及六根核驗後才移除原目錄、建立 Junction 的程序；本次使用者提供的完成摘要也指向這六根。第二批清單記錄使用者針對精確 28-root 清單同意移除原副本並建立 Junction。這些授權紀錄只涵蓋各自清單，不擴張到其他資料根；本頁是事後核對，沒有執行資料操作或新增授權。
- 第一批精確來源表與還原步驟見[第一批冷封存文件](../03_data/C_DRIVE_QA_COLD_ARCHIVE_20261009.md)。第二批精確目錄表見[第二批清單](../03_data/C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md#精確範圍)，其來源範圍亦與 E 槽 `E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009_batch2_plain/plan.json` 的 28 roots 一致。**範圍清單由各批 plan／資料文件維護；本頁維護兩批終態對照。**
- 第一批 E 槽終態檔為 `E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009/released_complete.json`；第二批為 `E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009_batch2_plain/released_complete.json`。第二批終態收據於 2026-10-09 21:37:40.470862 UTC 記錄 `status=complete`、28 roots、C 可用空間由 194,551,021,568 增至 228,999,462,912 bytes、E 可用空間 181,347,819,520 bytes。這些數字是該終態收據的操作快照，不是即時容量。
- 第一批 6 roots 與第二批 28 roots 路徑不重疊；也未與先前已隔離的 368 roots 或 10-root 歷史測試集中提案重疊。`HISTORICAL_TEST_QUARANTINE_20261006` 記載的 10-root 目標仍未建立、該提案搬移量仍為 0 bytes；不得把它併入本次 34-root 統計。

## 需要保留的例外與判讀邊界

- `dist/candidate_20261006` 有 released 收據及 Junction，但其 SHA 清單、receipt 與 manifest 都記錄 0 bytes、0 files、0 manifest entries。這是空目錄封存，不代表存在可恢復的候選封裝內容。
- `output/ml_research/integration_20261002` 曾出現在停止的 29-root 初次嘗試說明中；後續 28-root `plan.json` 與 `released_complete.json` 均包含該路徑，C 槽為指向第二批 E 槽副本的 Junction。初次嘗試的排除描述屬歷史過程，不再代表最終範圍。
- 第一批記錄的「近期候選與 dist 未搬移」只描述第一批執行範圍；第二批清單包含 21 個 `dist/candidate_*` roots，其中 `candidate_20261006` 是 0-byte 空目錄。兩批範圍不同，不能用第一批句子推定目前所有候選封裝仍在 C 槽。
- 第一批文件所述 `exit 0` 及抽樣 SHA 讀回，無法只由目前 E 槽逐根收據獨立證明；本次沒有重做該抽樣。逐檔 SHA 完整核驗僅能表述為「第一批原執行收據記錄已核驗」。
- 第二批根層 `complete.json` 是較早的 `copies_verified_sources_retained` 複製階段收據，不代表最後狀態；最終狀態看後續 `released_complete.json` 及逐根 released 收據。

## 文件入口與同步終態

- [資料資產用途與恢復登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md)：第一批完成摘要及容量／恢復入口。
- [第一批冷封存與回滾說明](../03_data/C_DRIVE_QA_COLD_ARCHIVE_20261009.md)：六個根的精確來源、逐批操作與還原方式。
- [第二批範圍與回滾文件](../03_data/C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md)：記錄 28 根完成與終態收據；初始 29-root 嘗試的排除決定已明確標為歷史，後續精確 28-root plan 納入 `integration_20261002`。
- [資料文件導覽](../03_data/README.md)：資料領域入口。

本次資料整理沒有改變正式 FA_DATA、生產排程、模型或產品功能。以下列出初版核對時發現的同步工作及目前終態，避免把已解決項目繼續當成待辦：

| 文件 | 初版發現／需同步內容 | 終態 |
|---|---|---|
| [`docs/03_data/README.md`](../03_data/README.md) | 標示第二批完成並加入終態 QA 對照入口。 | 已同步；標示 28/28 完成及未重算全量 SHA 的限制。 |
| [`C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md`](../03_data/C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md) | 保留初始 29-root 停止史，同時說清楚後續 28-root plan 納入 `integration_20261002`。 | 已同步；最終 C 槽狀態指向 E 槽副本的 Junction。 |
| [`STORAGE_ASSET_REGISTER_20261006.md`](../03_data/STORAGE_ASSET_REGISTER_20261006.md) | 將 `integration_20261002` 初次排除與後續納入分清楚，並限制第一批保留描述的範圍。 | 已同步；第一批文字明確限定為第一批範圍，第二批按終態記錄。 |
| [`PROJECT_SNAPSHOT.md`](../00_core/PROJECT_SNAPSHOT.md) | 加入封存摘要並保留容量快照及核驗邊界。 | 已同步；34 根、158,712 檔案、logical bytes 與終態 QA 入口均列明。 |
| [`DOCUMENTATION_INDEX.md`](../00_core/DOCUMENTATION_INDEX.md) | 加入資料資產與保留恢復入口。 | 已同步；資產登記連至終態 QA 對照。 |

上述同步依據逐批終態收據與 Junction metadata；沒有改寫原始 QA 收據、重新計算封存樹全量 SHA，也沒有改變正式 FA_DATA、生產排程、模型或產品功能。
