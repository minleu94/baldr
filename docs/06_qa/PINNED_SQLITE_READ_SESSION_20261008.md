# 單次 SQLite 私有副本讀取 QA

## 問題與工程範圍

原 H20 真 Main 讀取曾使原快照 SHM mtime 變動；SQLite mode=ro／query_only 不足以保證原檔組中繼資料不變。新增 `data_module/pinned_sqlite_read_session.py` 提供明示來源 SHA、私有根與容量上限的單次副本讀取。此葉片尚未接 provider、ML replay、正常設定或 UI，不能把它解讀成原十股保護與效能已通過。

## 契約

- 原來源只以檔案讀取核 main／WAL／SHM／journal 的 bytes、SHA、stat、祖先與實體身份，SQLite 只連本次 exclusive-create 私有副本。
- 現階段支援主檔加不存在或零 byte WAL；非空 WAL 與任何 rollback journal 拒絕。SHM 只核 pin、不複製，不單憑存在拒絕。
- 私有副本 mode=ro、query_only、authorizer 與明示單一 transaction；兩個後續入口可共用該 transaction。拒 DML、DDL、ATTACH、DETACH、VACUUM 與寫 PRAGMA；正常 COUNT(*) 的已知主表特殊 authorizer 事件限定放行。
- 取消、容量不足、callback 失敗、來源漂移、hardlink／reparse、私有副本變更與 schema 越界均拒絕。finish 先關連線，再核副本及完整原來源終態，成功才給 binding。
- binding 保留原來源路徑；reader path 僅診斷，生命週期明示 closed_and_removed。新操作重新複製。清理只刪本次建立且物理身份相符的副本，置換或未知檔案保留；取消半成品不冒充 verified pin。

## 中央證據

凍結模組 SHA `4d5b4eb4dae01017cd18c101c418bd0c62f7bce2986d7ac4adb68355afda51e1`；測試 SHA `34cc3c3cbf30232deff36e61cac2f4b224fd82a4546e0a4ea37c301ee9278c86`。中央核對與執行 agent 宣告一致。

中央獨立 elevated 合成測試 terminal0：**17 passed／1 skipped，0.63秒**；完整 log 保存在 ignored `output/qa/pinned_sqlite_read_session_root_20261008_c.log`。唯一 skip 是 Windows 不允開啟中的 SQLite 檔改名；另以真連線關閉後再置換副本的可重現測試通過，拒絕結果並保留置換檔。原生 NTFS hardlink 拒絕實測通過。兩檔 targeted mypy 與 py_compile 通過。

早期 DirEntry cached stat 回 inode／nlink=0，中央探針證明 direct lstat／fstat 可取得實際值，已改直接查詢並保留嚴格 guard。中央前輪4失敗／11通過／2跳過、agent前輪失敗紀錄均保留：COUNT誤拒、取消被OSError包裝、closed-connection測試錯誤與型態錯誤已各別修正，不覆寫成成功。

## 未完成與回滾

尚未測原4GB快照、本機磁碟吞吐、原十股／2382／收藏 Main、新程序候選或 Native；本次測試秒數不是 H20 載入時間。shared provider、feature replay與entry replay須由composition傳同一次副本 session，並在結果發布前 finish；App／Qt不直接匯入 ML。正常 private-root設定、manual與UI整合另驗，不以此葉片折抵 P00–P14／M3。

新檔是獨立葉片，實作 preimage、所有失敗／成功 attempts 保留於 ignored QA。回滾限定移除本次新增模組、測試與QA文檔，保留其他聊天 dirty、原來源及保存研究；接線後須先審依賴，不能直接移除。
