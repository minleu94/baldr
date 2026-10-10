# C 槽歷史 QA 與研究副本冷封存

本文件是 2026-10-09 第一批冷封存的歷史操作摘要，只記錄該批六個指定根目錄。使用者授權使用 E 槽封存，並明確同意逐根核驗後移除 C 槽原副本、建立 Junction；接受拒絕 reparse point 的嚴格讀取器需要先還原再重跑。產品補完計畫「維持暫停」只描述第一批操作當時，不是目前產品狀態；目前進度見[專案快照](../00_core/PROJECT_SNAPSHOT.md)與[恢復開發 QA](../06_qa/BALDR_COMPLETION_RESUME_20261009.md)。

封存根：`E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009`。既有 `cleanup_20260929_selective_v1` 是舊資料唯一恢復來源，保持原樣。正式 D 槽 FA_DATA、私人設定與排程未納入第一批；「近期候選與 dist 未搬移」也只描述第一批範圍，不能代表後續封存後的整體位置。第二批範圍與兩批終態見[第二批清單](C_DRIVE_QA_COLD_ARCHIVE_BATCH2_20261009.md)及[終態對照](../06_qa/C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md)。

## 回滾清單

| 原位置（相對專案根） | 變更類型 | 封存大小 GiB | 回滾方式 | 回滾風險 |
|---|---|---:|---|---|
| output/qa/personal_daily_product_20261006 | 移動 | 64.25 | 依封存根同名相對路徑複製回原處，核對 SHA-256 清單 | 須先移除 Junction，不能遞迴刪除其目標 |
| output/qa/astra_engineering_20261003 | 移動 | 24.65 | 同上 | 嚴格讀取器需普通目錄 |
| output/qa/closeout_commit_20261003 | 移動 | 14.05 | 同上 | 保留歷史失敗收據及備份內容 |
| output/data_completion_20260909/backups | 移動 | 12.83 | 同上 | 不用歷史備份覆蓋正式資料 |
| output/ml_research/current_stock_cycles/2026-10-02 | 移動 | 25.57 | 同上 | 不推論 PIT 或正式資格已成立 |
| output/qa/tp20_20260920T061923Z | 移動 | 6.71 | 同上 | 重跑需沿用原來源與資格限制 |

## 驗證及執行紀錄

本批六個根共 158,977,761,695 bytes（約 148.06 GiB），12,862 個檔案，已逐檔比對 C／E SHA-256，複製回傳碼均為 1（成功複製），樹狀項目數一致。`complete.json` 的狀態為 `copies_verified_sources_retained`，只證明複製與核驗，不代表已釋放 C 槽。

最終釋放步驟再次比對來源／封存 SHA-256、精確路徑、檔案數、樹狀項目與無既存 reparse point，通過後才移除來源並建立 Junction。逐根實際釋放結果以 `*.released.json` 為準；全部完成以 `released_complete.json` 為準。未產生最終收據前，不把全數 148.06 GiB 說成已釋放。

最終執行 exit 0，`released_complete.json` status=complete，六個根均為 archived_verified_junction_installed。Root 另核對六個 Junction 的精確目標，並各取 manifest 一個檔案從原 C 路徑讀回，SHA-256 均相符。完整內容已在複製及最後釋放前各做全檔雜湊比對；抽樣只驗連結讀回，不代替全檔核驗。

容量口徑：搬移 logical bytes 為 148.06 GiB，最後釋放程序期間 C 可用空間從 121,755,623,424 增至 219,108,855,808 bytes，淨增加約 90.67 GiB；這是磁碟可用空間觀測差，不把 logical bytes 當 allocated bytes，也不假定期間沒有其他寫入。postflight C 剩約 204.06 GiB，E 剩約 205.86 GiB。先前進度訊息的各批 GiB 指內容量，不能作為實際釋放容量。

## 還原步驟

1. 確認指定歷史目錄沒有使用中的程序，並保留 E 槽副本。
2. 核對原位置確為指向登記封存目標的 Junction；只移除連結本身，不使用遞迴刪除。
3. 將指定封存樹複製回原位置，逐檔比對對應 `*.sha256.jsonl` 的路徑、大小與 SHA-256。
4. 核對普通目錄、檔案數及樹狀項目數，再重跑需要的歷史驗證；未驗證前不移除 E 槽副本。

E 槽需保持連接。舊路徑可供一般查閱，但不能藉 Junction 冒充嚴格讀取器所要求的普通目錄或原檔案身分。這次保留全部內容，沒有刪除歷史證據。
