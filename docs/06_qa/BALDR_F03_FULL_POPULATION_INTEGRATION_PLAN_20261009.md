# F03 KDJ 全母體接線計畫

日期：2026-10-08
狀態：規劃與未發行資格的 collector 骨架；F03 全母體、UI、收藏與保存重開仍未完成。

## 範圍與回滾

本切片只新增本計畫、KDJ compact projection 骨架及其單元測試。回滾時移除新增的三個檔案即可；不回退或改動既有 KDJ leaf、MA/F17/P01、Main、Watchlist 或其他工作區檔案。

已接受的 KDJ leaf 是 `app_module/daily_market_technical_kdj_evidence_v1.py`，方法為 `daily_market.kdj_kd_golden_cross_9_3_3_sma`／`kdj-sma.v1`。既有 KD 為 STOCH 5/3/3 SMA，兩者分開保存；leaf 的自洽 hash 不代表來源資格。Leaf 只使用保存 snapshot 的最多 120 列原料、Decimal 固定 context、最後 14 列、前後觀測列與同日內 K/D 黃金交叉；available-at 為 unknown、historical PIT 為 false。leaf 通過的 12 項合成測試不代表 F03 全母體完成。契約依據見 [F03 leaf review](BALDR_F03_KDJ_CONTRACT_REVIEW_20261008.md)。

## 現行接點與不可越過的邊界

- P01 的 `DailyMarketTechnicalUniverseV4ReadSessionBuilder` 目前只有一個 `_verified_projection`。`bind_verified_projection()` 只准讀取開始前綁一次；`_consume_verified_segment()` 在既有 snapshot→parent row 迴圈中先建立一次 row，再把同一 snapshot/row 送給 observer。KDJ 必須用此處的同次投影，不能另讀 child、另建 parent row 或再掃完整來源。
- F17 現有 opener 會按既有 MA 路徑工作；它們不計算 KDJ。KDJ 必須走新的明示 opt-in opener，該路徑在同一次 `BundleReader.read_exact()` 前準備 MA+KDJ observer tuple。一般 F17／MA 呼叫保持既有成本與行為。
- MA collector 的 finalizer 目前要求 Builder slot 本身就是 MA collector。單把 dispatcher 放進 slot 會使該檢查失敗。正式接線需由 Root 核准的共享 hook 增加 exact member 身分查詢，不能只靠 type、名稱或自洽 digest。
- 尚未取得 exact bundle state、P01 verified session、selection 與 parent reference 前，manifest metadata 和 KDJ evidence 都是未核資料。collector 的 compact entries 及 projection group 不發行 index/session/page qualification；此新增骨架刻意沒有 publication/finalize API。

## 明示 opt-in 的來源流程

1. 使用者或 SavedRecipe 明示選擇保存的 F17 bundle reference；metadata-only 讀取只建立未核的來源要求，不決定最新版本、不掃描資料夾、不讀 facts。
2. 新 KDJ opener 由同一份 manifest metadata 建立一份 MA source request、MA collector 與 KDJ collector。KDJ source request 包住同一個 typed MA source request，並綁 `kdj-sma.v1` method identity；兩個 collector 必須指向同一個 source request object。
3. 建立不可變的有序 `(MA collector, KDJ collector)` projection group，在 exact read 開始前一次綁定。不得 late-add、remove、reorder、重複 bind 或把 group 重播至另一個 Builder。此 opt-in group 佔用 P01 唯一 observer slot；既有一般 opener 不建立 group。
4. `read_exact()` 只呼叫一次。既有 callback 先驗 parent、segment、clock、method、receipt、batch 與 snapshot；每列 `_make_row(snapshot)` 只跑一次，之後以同一 typed snapshot/row 依固定順序送 MA、KDJ。任一 callback、取消或 pin 驗證失敗，整個 exact operation 失敗，沒有半份 index 或 F17 session。
5. exact read 完成後，Root 的共享 publication seam 在同一 finalization 邊界先驗 bundle state、P01 verified session/base query/selection、parent references、完整 counts 和 group exact membership，再暫存地 finalize MA 與 KDJ。只有兩者皆成功才建立帶兩個已核 session 的 F17 session；任一失敗都不發布 session。一般 F17／MA route 仍走舊單一 collector 路徑。

## KDJ compact index／query 契約

### compact request 與 entry

KDJ request 保存未核的同來源 MA request、KDJ method ID/version/identity、availability/PIT 限制；metadata request 自身不構成資格。每筆 compact entry 僅保存：股票代碼與 segment、snapshot/source/window/evidence identity、決策與前後觀測日期、前後 RSV/K/D/J Decimal、`match/no_match/unknown`、具名 reason、暖機狀態，以及固定 `source_available_at=None`／`historical_pit_eligible=False`。整份 14 列日期與 fingerprint 清單只保留為有界 window digest；不得把完整 leaf DTO、120 列 snapshot、parent object 或 child artifact reference 複製進每檔 entry。

建議沿用 MA compact budget：declared stock 上限 100,000、整份 canonical index 上限 64 MiB；另設單 entry 4 KiB、股票代碼 16 ASCII 字元、source identity 256 UTF-8 bytes、reason 最多 8 項且每項 96 UTF-8 bytes、Decimal token 最多 96 UTF-8 bytes、window 日期/fingerprint 各最多 14 項。4 KiB 與 16 KiB request budget 都量最終 canonical payload（包含 identity 欄位），不是只量 hash 前 body；建構、序列化及 collector append 都必須遵守同一界線。每次序列化先檢 bounds，再累加 canonical byte count；達任一上限立即具名拒絕，不截斷、不落部分 index。取消至少在 callback 前、每列前後、每個 parent 結束及未來 finalizer 建構/回傳前嚴格 poll；callback 非 bool 或丟例外按既有具名取消契約處理，不轉成來源成功。

此限額是 compact projection 的候選 budget，仍須由真 257+1/跨 segment 與最大 entry 合成測試確認實際 byte 使用；64 MiB 與 100,000 是各自硬上限，不表示所有最壞字串組合都可通過。request 和 entry 在公開 dataclass 建構時即驗證包含 identity 的完整 canonical payload 大小，collector 在 append 前另驗同一單筆大小與累積 index 大小。測試會覆蓋 body 尚在 budget 內、附加 identity 後超限的拒絕路徑；緊湊 entry 的測試以局部縮小 budget 觸發此邊界，因現有欄位上限使有效最大 entry 低於 4 KiB。任一 callback/order/source/cancel 例外都會 poison 當次 group/KDJ collector；即使取消旗標之後變回 false，也不可續用先前收集狀態。錯誤前曾累積的 entry 只會在未核 property 拒絕後不可取出，不會轉成合格或部分結果。

當前新增 skeleton 的測試只驗 metadata-unverified request、來源要求與 entry bounds、KDJ evidence 被偽裝成 reader-qualified 時拒絕、固定 MA→KDJ 成員身份/次序、Builder 單次 bind、嚴格取消 callback，以及失敗後無法重用。現有 MA finalizer 會因 Builder slot 指向 projection group 而拒絕單獨發行；未來 shared hook 必須保留此邊界，只有 group 完整驗證 MA/KDJ 兩個 member 後才可原子發行，不能讓取得 group member 參考的呼叫端各自發行部分 session。它沒有真 parent read、沒有重複段/跨段 snapshot source proof、沒有 qualified index/session，也沒有 F17 full-N 驗收；以下共享來源矩陣仍是後續待辦。

### 全母體 composite query

後續 versioned query 只保存研究條件與固定來源 recipe，不把頁碼塞入 global query identity。F17 nested query 維持 MA composite 已定的 neutral sort/page contract；外層 composite query 保存技術規則、MA states、KDJ states、唯一 `AND|OR`、唯一 `include|exclude|only` unknown policy 與全域 sort。獨立 typed `PageRequest` 綁 composite query identity 和 `page_index/page_size≤256`。

只有明示啟用的技術、MA、KDJ 三個 truth group 參與外層 AND/OR；停用 group 是 `not_applicable`，不作 TRUE。row-scope 決定哪些列可供瀏覽／稽核，與研究資格分開；明示股票、market/disposal 狀態、technical stock eligibility 才是研究資格外層硬 gate，OR 不可救回 excluded、pending 或不合資格股票。硬 gate 後才套 unknown policy。audit 可見列與研究資格要分開：既有 F17/MA 在沒有啟用研究條件、且 row-scope 明示包含 excluded 時，excluded 列仍可作為 `not_evaluated` audit 記錄顯示（既有 matrix 可見 259 列）；這不等於 match、合格推薦或進入 qualified count。後續 query 必須分開記完整 declared population、各 group 全母體 truth（包括 `not_evaluated`）、hard eligible、unknown-policy included/excluded、visible/audit rows 與 final qualified rows。即使將來可瀏覽 pending，也不能把它算成研究 truth 或讓 OR 將其升格。

Execute 必須在同一完整母體 traversal 同步 merge F17 fact rows、P01 sorted technical rows、MA compact entries、KDJ compact entries，先得完整 counts/keys，再 global sort，再 page。不可先各自執行 query 再交集，也不可在 table local filter。暖 page 只讀最多 256 selected bundle rows、P01 rows 與 bounded index positions；不重算 KDJ、不重掃全 N、不重開來源。結果/page 都需 reader-issued anchor 綁全 query、來源、ordered keys/counts、request/rows；`dataclasses.replace` 或自洽重雜湊不可借用資格。

### SavedRecipe 與 fresh reopen

後續另立 KDJ SavedRecipe schema；不改舊 F17／MA bookmark bytes。recipe 保存明示 bundle output root／identity／manifest SHA、完整 F17 與 composite 條件、排序、目前 page 與 basket 每檔的 page request/code。它不保存舊程序 session/index/page proof 當資格。fresh process 僅依原明示 bundle exact-open 一次，重建完整 MA+KDJ index、global execute 一次，逐頁核 basket code 後原子套用 UI。新的 operation/session/index identity 可不同；bundle/manifest、P01 plan/receipt/cohort/source clock/method、snapshot facts、cutoff、條件與列內容必須與保存 recipe 完整相符。來源缺失、混版、篡改或取消一律拒絕；不可讀 live/latest 補值，也不可把 current-only 改稱 PIT。

## 共享 hook 的最小 patch 預覽（尚未套用）

1. `app_module/daily_market_technical_verified_projection_v1.py`：保留既有 Protocol，增加有序 projection group 的明確型別或受控 dispatch helper；固定 members tuple 與 exact identity membership，不提供公開 add/reorder。
2. `app_module/daily_market_technical_universe_v4_query.py`：保持舊 `bind_verified_projection(single)` 完全相容；增加一次性 `bind_verified_projection_group(tuple/group)` 與 exact `has_registered_verified_projection(member)`。群組必須在讀取／segment/build 開始前綁定。既有 `_make_row` 次數與 observer callsite不變，dispatcher 每個 member callback 後都要 poll cancel。
3. `app_module/daily_market_technical_universe_ma_alignment_query_v1.py`：只將 `builder._verified_projection is self` 改成 Builder 的 exact registered-member identity check；其餘 source/state/index validation保持不變。
4. `app_module/daily_market_technical_official_disposition_query_reader_v1.py`：不改預設 F17／MA opener；新增明示 KDJ opener/recipe reopen。兩者沿用同一次 metadata read、同一 `BundleReader.read_exact()`，在此入口才 opt-in 建 MA+KDJ tuple。`_issue_session_from_verified_bundle()` 對兩個 collector 做同一原子 finalization，F17 read session新增 optional KDJ session及 same P01/bundle/source pin驗證。新 `execute_kdj_query_v1` 執行全母體三群 composite，原 `execute_ma_query_v1` 原封保留。
5. 新 backend 模組：`app_module/daily_market_technical_universe_kdj_alignment_query_v1.py` 負責 source request、compact entry、projection group/collector與後續 reader-issued index/session；`app_module/daily_market_technical_official_disposition_kdj_query_v1.py` 負責 canonical query/result/page/request/sort DTO。SavedRecipe 可在 backend qualification完成後另包版本檔。

共享 patch 的驗收必須證明舊 F17／MA opener 不呼叫 KDJ、KDJ opt-in 恰好一個 exact read、projection 次數等於 processed snapshots、同列只建一次 parent row、MA/KDJ 任一失敗均不發 session。此計畫及當前 collector 骨架不包含該 qualification 接線。

## 最小測試矩陣與完成界線

- collector skeleton：metadata request 標記 unverified；一般 object、錯型別、callback 非 bool／raise／cancel、duplicate/reordered segment、重複 snapshot、超 stock/entry/index bytes 均具名 fail；不得出現 qualified index/session。
- 共享來源正例：真合成保存 F17 bundle 至少 257+1、跨 segment、含 match/no_match/unknown，projection 完整 counts 等於 exact reader；無第二次 child讀取或 parent row建構。
- query 正例/反例：技術／MA／KDJ 三群全部 AND/OR active/inactive 組合、unknown 三政策、outer hard gate不能被 OR救回、null-tail/tie排序、全頁 union與獨立 Decimal oracle一致；pending/excluded/missing分母保留並按狀態 `not_evaluated`。
- seal/source：跨 bundle、parent reference、cutoff、clock、method、cohort 混搭；snapshot/page/result/ordered keys/counts 被 `replace` 並自行重雜湊；全部不得得到 qualified publication。
- freshness/cancel：pre-cancel、逐列、段末、MA finalize後 KDJ finalize前、兩個finalizer後、page/result構建後取消皆不發半套；fresh process recipe同來源重新 exact-open，只允許新 operation ID變化。
- UI／Main／Watchlist、producer、正式來源、native 真人、效能／P95、本方法的投資效益與歷史 PIT 均不在本切片，不能用 leaf或collector skeleton測試替代。
