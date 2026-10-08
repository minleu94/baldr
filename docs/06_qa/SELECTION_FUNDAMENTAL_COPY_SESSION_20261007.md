# 基本面來源副本 session 中央審查紀錄

新增來源 session 目標是完整母體只核驗一次來源clock並共用至每批16檔，不把F08–F19縮成永久unknown。早期原SQLite mode=ro仍可能在WAL主檔旁建立WAL/SHM；query_only與SQL零寫入不足以證明原始資料無異動，故原直讀葉片未取得來源資格。沒有用正式資料測試此副作用。

目前新增snapshot leaf先以1MiB區塊捕捉原main/WAL/SHM/journal presence、stat與SHA，只複製至唯一隔離captured和reader兩份實體檔，SQLite只開reader copy。finish核原檔、captured檔及manifest真bytes/checksum；complete前再檢查外部取消。來源clock保留原檔身份及明示copy binding，不把reader路徑偽裝成原來源。WAL缺SHM仍拒絕；main-only WAL不授予未checkpoint歷史或PIT資格，雙份磁碟成本不等於效能合格。

中央合跑新source、既有provider/source-root/materialization測試73項通過（3.06秒），唯一合成TEMP C:/t/p03-copy-root-20261007-i，raw log為ignored output/qa/baldr_completion_m2_20261007/p03_copy_root_20261007_i.log。涵蓋真正未checkpoint WAL row、原檔bytes/mtime不變、captured篡改、publication窗口取消及既有provider相容；仍須逐條審查實際assertions，不以綠燈代表P03完成。

中央尚未提交來源葉片：SelectionFundamentalReadSession.open目前仍可直接開未證明copy-bound的任意provider DB，公開新API可能繞過copy路徑，不能取得原來源無寫入資格。正在審查如何限定內部copy-bound helper；正常updater接線、原F08–F19各具名source規則與UI保存、真全母體效能都未完成。

## 型別契約與實體檔隔離複驗（2026-10-07）

前文公開 helper 可直接開任意 DB 的缺口已在新葉片修正：open 必須提供 FundamentalReadCopyBinding，連線前重新核 manifest、來源及副本 pins，拒絕缺契約或篡改。路徑互斥不足以證明副本獨立；中央審查另發現 hardlink 缺口，已要求 captured、reader 與 manifest 為單連結檔案，並以 device/inode 拒絕來源與兩份副本共用實體檔案。source 本身可以有多連結，限制只施於隔離副本。

中央最新唯一合成 TEMP C:/t/p03-copy-root-20261007-o，source suite 32 項通過（2.02 秒）。三種 NTFS hardlink 情境在 SQLite connect 前拒絕，原來源 bytes/stat/link count 不變。首次預設 sandbox 在 TEMP mkdir 即 WinError5，32 個 setup errors，沒有進入產品測試；明示合成 TEMP 與 hardlink 範圍後以 require_escalated 複驗成功。代理紅測、前像與驗收紀錄保留於 ignored output/qa/p03_copy_hardlink_*，未拿正式資料建立 hardlink。

此結果只驗 source-session 葉片；portable snapshot root、updater 接線、F08–F19 各資料規則、UI 保存及完整市場效能仍待，不能判定 P03 完成。

中央相容性合跑補驗：新source suite與既有provider/source-root/月營收materialization共79項通過（3.60秒），唯一TEMP C:/t/p03-copy-root-20261007-p。全域production mypy889檔通過（含同時凍結的H20控制項），兩則既有untyped body notes保留。金融來源保持固定aware cutoff與current-observed-only，未新增策略金額或裸float運算，不能據此授予歷史PIT。
