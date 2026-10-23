# Track C 具名回收核驗 — 2026-10-22

本輪接續 [先前盤點](STORAGE_ML_READINESS_20261022.md)，未重掃整顆 F 槽。4 項條件式 `SAFE_RECLAIM` 共 **9,909,706,064 bytes（約 9.23 GiB）**，Owner 隨後回覆「全部批准」，包含 snapshot 即時 resume 的還原條件；本輪已重新核驗並完成四項精確刪除。原批准清單保存於 commit `c97685daa256`，本清單已更新為執行紀錄。

2026-10-22 22:48（America/Los_Angeles）執行後觀察：F 槽總容量 1,024,191,361,024 bytes，可用 73,412,988,928 bytes（約 68.37 GiB）。其他 Track 可同時寫入，前後差值與歸因限制見下方執行結果。既有 V2 RC、Trial、正式資料、收據、排程與 ML Promotion 守衛皆保留。

## 已批准並回收的 4 項

完整實體路徑、檔案身分、SHA、證據 SHA、還原方式及前後檢查見 [Manifest](RECLAIM_MANIFEST_20261022.json)。容量為唯一普通檔案 AllocationSize 估計，不能保證與並行系統的磁碟空間增量相等。

| Manifest ID | 預估 bytes | 保留的還原副本 | 風險 |
|---|---:|---|---|
| `dist-extra-theme-06` | 978,534,056 | Trial `Baldr-Theme-Research-06/app` | 低；歷史 dist 路徑若再使用，須先還原 |
| `dist-extra-theme-07` | 978,542,248 | Trial `Baldr-Theme-Research-07/app` | 同上 |
| `failed-snapshot-extra-1e40b7ef8b34297429a36e81f37990f9` | 3,976,314,880 | `437aa76c88ac050886a9f3a7fd7c6a91/snapshot/source.sqlite` | 中；失敗 cycle 暫失即時自足性 |
| `failed-snapshot-extra-f65f59b1a430d84cc9a1e11b9b0fb918` | 3,976,314,880 | 同一保留 anchor | 同上 |

兩份 dist 各 7,124 檔，逐檔 SHA、相對路徑及空目錄完全相符；各 7,638 個節點的 owner/group/DACL 與必要還原 metadata 已保存。檔案均獨立、nlink=1，無 ADS／reparse。完整具名檔案 Restart Manager 查詢成功、無使用者，exclusive read probes 成功。224 個 Task XML、51 個 automation、版本前綴、junction alias、實際 builder／launcher 與已知任務引用均已核對。build receipt 的歷史 dist 路徑屬被動引用，仍保留 receipt 與 Trial。程序路徑有 156 個系統程序無法讀取，不能宣稱全機程序皆已辨認；以完整具名檔案 RM 補查，且有自開檔案正向測試。

三份 snapshot 已 bounded hash 驗證，各 3,976,314,880 bytes，SHA 均為 `505964dc2125e0f79d59e190f9a6379dbaa2cf1b36026c8359df8f4a4790640b`，符合各自 receipt 的 size／mtime／SHA。只提案移除兩份未發布失敗 cycle 的 `source.sqlite`，**不移除 WAL、SHM、metadata、failure evidence 或目錄**。WAL 為空，SHM 穩定，DB/WAL/SHM 的 RM 與 probes 通過；未用 SQLite 開啟資料庫。整個 `437...` run 保留，包含歷史 QA 所引失敗證據。

實際 cycle index 與 18 份經 index SHA 驗證的 registry record 正文均無兩個候選的發布引用；不能只以簡化 run index 缺 cycle UUID 作判斷。已查 Tasks、automations、15 個 ML latest 與 20 個受限 consumer locator。這是具名觀察，非永遠無引用的保證；批准後必須重新核 raw-run／cycle／model／active-task 引用、完整 SHA、metadata、sidecars 與 handles，任一漂移即停止。

snapshot receipt 原有 D: 路徑與 F: 實體位置不一致，保持原件不改。已證明可恢復 F: 實體內容，**不宣稱 source-context replay 或來源資格通過**。恢復時須從 anchor 複製回清單精確路徑、還原該 cycle 的整數 `mtime_ns`、核 size/SHA/time，保留 receipt/context/source dependencies，再由 B 獨立核遷移及資格。檔案 ID／SACL 複製不在保證內。

## 原 33 個大檔的去向

| 分級 | 數量 | 最小解除條件／處理 |
|---|---:|---|
| `BLOCKED` | 3 | 正式 repair evidence，歸 Track B，保留 |
| `REVIEW_REQUIRED` | 7 | 未完成 Direct `.work-year` assembly；先 Owner 放棄 resume、排除 writer，再證明 raw/shard/carry/sector/action/code 等重建閉包 |
| `RETAIN_REFERENCE` | 19 | 18 個已發布 snapshot（含 failed 但已註冊者）＋上述 437 anchor |
| `REVIEW_REQUIRED` | 2 | `5b673cb7db851b64aa551518c82aa986` 無核實替代副本；`910dde3e5bb97afb12234887239b38bf` 缺 snapshot receipt |
| 條件式 `SAFE_RECLAIM` | 2 | 本次兩份冗餘 snapshot，已批准並完成精確回收 |

刪除前 33 個檔案的 ID／length／mtime 與前輪皆一致。7 個舊 heartbeat PID 不存在，不代表已獲刪除或放棄續跑授權。早期 `candidate-33-current.json` 的粗分類已由 `snapshot-classification-final.json` 與本次 Manifest 修正，不能再當最終分類。

## ML 資產與保留政策

15 個 latest pointer 身分與前輪一致。current OOC `allocation-ooc-868b7e805f5c03c65dc303e4`、實際依賴的 Direct `505c6adaf3f71a0c8f0a274e` 及最新 Direct `a1e00e51c5144283b7dbe72f` 均 `RETAIN_ACTIVE`，此分類指消費／依賴關係，不代表金融資格。CORE19、OOS／Golden、raw/PIT 與必要回退為 `RETAIN_REFERENCE`；舊 Ensemble 用途未明仍保留。沒有已證明可退役的模型或 optimizer checkpoint。

OOC 上游 training manifest canonical `ca197fcbfd894bf4785fb39e6f782eaf676eab83dd5a79f06b5c2504e9bf5389` 在受限 5 份現存 training manifest 中未定位；所有未解閉包保持保護，不能宣稱完整 raw closure。現行校準 ECE 2627bp 超過 500bp，Brier 3175 比未校準 2956 差，維持 research／alpha=0。Track B R8 合約仍有 currency／source timing／衝突等缺口，ML training/OOS 未授權；不啟動重訓。

[Retention Policy](RETENTION_POLICY.json) 定義 Release 至少 current RC＋已核 rollback＋所有 Golden；Trial 14 天、cache 30 天只觸發預覽；保留可續跑／最後完成／最佳 accepted checkpoint；failed run 保留原始失敗證據。任何既有產物仍須具名批准。新 cache 身分含 source/revision/availability/cutoff/schema/features/labels/code，不跨 PIT 合併，不重寫正式資料。

容量警戒 120 GiB、緊急審查 40 GiB 為本線操作建議；既有 heavy ML 預算 35 GiB persistent＋40 GiB scratch＋20 GiB reserve＝95 GiB。當前不足 95 GiB；即使回收全部 9.23 GiB 仍不足。工程 probe 限 1 GiB persistent＋1 GiB scratch、8 GiB Job memory／12 processes。未安裝自動清理或更改排程／既有 guard。

## 已完成的小量實際清理與 QA

只清除本任務新建的合成 fixture：52 檔、原預檢唯一配置 442,432 bytes，scratch 根已不存在。首次因本任務內 hardlink 連結數隨 unlink 遞減而安全停止，保存失敗收據後按已核 owned link group 完成剩餘清理。續行觀察 free 增加 **417,792 bytes**；這是磁碟總量觀察，不能全歸因為刪除量，也不是 9.23 GiB 已回收。所有證據收據保留。

新增 `scripts/verify_storage_reclaim_pair.py` 是唯讀工具，`--candidate <root> --retained <root>` 比對完整樹、SHA、allocation、hardlink/reparse/ADS、短暫 exclusive read 與掃描前後身分，stdout JSON、相符 exit 0，否則 2。應透過專案 owned Job wrapper 執行；不直接執行未受資源限制的 Python。CLI 本身不做外部引用／metadata 還原審查，不授予 `SAFE_RECLAIM`，不刪檔。RM 函式供具名審查使用，不會 Shutdown／Restart 程序。這些瞬時檢查不能消除並行 writer 競態，實際刪除仍需 Owner 協調靜止窗口。

編譯與 18 個定向測試通過，涵蓋異內容、樹差異、empty dir、budget、重疊、hardlink、junction、ADS、lock、RM 正向查詢及既有 allocation/long path。未跑全 UI／全系統驗收。

本機證據根：`output/tasks/track-c-reclaim-20261022-01a164e7`。`pair-06/07.json`、`security-06/07.json`、`handles-06/07.json`、`reference-scope-expanded.json`、`snapshot-restore-proof.json`、`ml-locator-current.json` 及各 owned QA receipt 保留於 ignored output，不提交原始資料。Manifest 釘住關鍵證據 SHA。

## 整合與續行

僅提交本 Track 的 verifier、tests、README、本文件及兩份 JSON。共享 Snapshot／Manual／QA index 由 Integration Owner 核對其他 Track commit 與回歸後接手；本輪不接管其 dirty files、不 push。此輪只執行已批准清單，不合併跨線或發布產品。

Owner 已批准全部四項；歷史檢視兩個失敗 cycle 前仍須從 anchor 還原，不因此取得來源資格。其他 REVIEW／BLOCKED 項目保持原狀，沒有擴大清理或啟動重訓。

## Owner 批准後執行結果

Owner 回覆「全部批准」後，於 2026-10-22 22:48（America/Los_Angeles；原收據時間為 `2026-10-23T05:48:25.523888+00:00`）完成 4 項。移除 14,250 個檔案（兩份 runtime 共 14,248 個＋兩個 snapshot payload），僅移除已核 runtime 空目錄，不使用遞迴清除。原估唯一配置 **9,909,706,064 bytes（約 9.23 GiB）**。

執行前 F: 可用 **63,504,646,144 bytes**，後為 **73,412,988,928 bytes（約 68.37 GiB）**，觀察增量 **9,908,342,784 bytes（約 9.23 GiB）**。這是全磁碟觀察，並行寫入及檔案系統metadata使其不等同完全可歸因的回收量；增量不是同槽搬移。

完整重新讀回兩份 runtime 與三份 snapshot SHA；核原身分、receipt/context、空 WAL／穩定 SHM、所有檔 ADS／hardlink／reparse、RM／exclusive probes 與全 runtime ACL/time。224 Tasks／51 automations 無目標引用，18 份 registry 正文及 cycle index、已知 consumer／ML latest 再核通過。新增命中的其他 task 及冷封存登記只引用保留的 Trial guide／receipt／source-version，經逐段核對不是刪除目標依賴；該 Trial 與登記均未改。

四個目標已不存在；保留 runtime 的全部檔案身分、三個 run 其餘檔案與目錄身分、anchor 完整 SHA、WAL/SHM、指標與收據 hashes 在執行後保持。逐檔 unlink journal、完整前後證據及 owned Job 收據存於同任務；Job 正常 exit 0、剩餘程序 0、handles 與 mutex 已釋放。沒有終止其他程序，沒有動正式資料／Track A UI／排程／資格。

本機關鍵收據：`evidence/executed_reclaim_receipt.json` SHA `9aa0dc43c166d551900c29a8094815a72b7234aade1c21271c44cef1748c0e1a`；`evidence/executed_job_receipt.json` SHA `c7562ca7b6d2d5f5065d31fff39c4d508721cef9eb545b3913eb8467801d3e1d`。Manifest 釘住同一收據；逐檔 journal 與舊未批准證據仍保留，不覆寫歷史失敗紀錄。容量仍低於既有 95 GiB heavy ML 預算，禁止據此開始訓練。
