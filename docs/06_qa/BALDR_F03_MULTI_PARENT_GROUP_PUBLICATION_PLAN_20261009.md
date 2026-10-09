# F03 多 parent 投影群組與共同發行邊界計畫

狀態：設計提案，尚未實作或驗收。這份文件只定義 MA、KDJ、波動度三路投影如何沿同一次 F17 exact read 完成完整 parent 核驗並共同發行；不代表 F03 全母體 query、UI、收藏或跨程序恢復已完成。

## 目前可用接點與缺口

P01 Builder 目前只有一個 verified-projection observer slot。`DailyMarketTechnicalUniverseV4ReadSessionBuilder.bind_verified_projection` 在 bundle 綁定或任何 callback 開始前只允許註冊一次（`app_module/daily_market_technical_universe_v4_query.py:2699-2716`）。`consume_verified_parent` 依序通知 parent begin、跑既有 segment reader、通知 parent end，最後記錄該 parent observation（同檔 `:2724-2766`）。既有 `_consume_verified_segment` 逐筆建立 parent row 後，把同一個 typed snapshot 與 row 傳給 observer，並立即檢查取消（同檔 `:952-1013`）。這是三路投影唯一允許的資料接點；不得在 collector 外重讀 artifacts、重建 rows 或執行第二次 source graph。

BundleReader 在所有 exact source/row 驗證成功後才呼叫 Builder 建立並發布 P01 read session（`app_module/daily_market_technical_official_disposition_bundle_v1.py:1284-1369`）。Builder 的 `_validate_read_session_material` 會在發行前核對 callback segments、parent references、counts、codes、pending 與 missing（`app_module/daily_market_technical_universe_v4_query.py:1550-1575, 1752-1818`）。因此單次或最後一段 observer callback 結束都不代表完整母體已核驗；完整性必須等 exact BundleReader 成功並取得同一 Builder 的 `verified_session` 後，才可判定。

F17 的兩個正式入口目前都建立 MA collector，並將它綁成 Builder 唯一 observer：既有 query reopen 位於 `app_module/daily_market_technical_official_disposition_query_reader_v1.py:3631-3680`，明示 bundle root/id/manifest 的入口位於 `:3734-3792`。兩者最後進入 `_issue_session_from_verified_bundle`（`:3683-3731`），目前先呼叫 MA `finalize_verified_publication`，再建構 F17 session（`:3707-3729`）。MA finalizer 會驗來源與完整 observations、建立 index，並直接發行獨立 MA session（`app_module/daily_market_technical_universe_ma_alignment_query_v1.py:1977-2081`）。這種先發 MA、之後才處理其他投影的順序不能用於三路原子發行。

現有 MA+KDJ group（`app_module/daily_market_technical_universe_kdj_alignment_query_v1.py:869-1070`）與新三路 callback group（`app_module/daily_market_technical_universe_projection_group_v2.py:107-514`）只負責 callback fan-out 和失敗毒化，沒有三路共同的 source qualification 或 publication API。波動度目前只可取得 unqualified index（`app_module/daily_market_technical_universe_volatility_alignment_query_v1.py:757-794`）。新 group 在 parent callback 完成後保持 `between_parents`；不應把此狀態改稱全來源完成。

## 最小接線設計

1. **加入明示 opt-in 的三路 query/reader 入口。** 新入口接受固定 bundle pins 與三路共用的 typed MA source request。從該 request 建立 KDJ 與 volatility 子 request，嚴格核三者同一 request object／source scope／cutoff／source clock／method 對應。由 metadata 建立 request 不授資格。舊 F17 opener 預設仍只建立既有 MA collector，輸出與成本維持原狀；只有新的 opt-in F03 入口才註冊三路 group。
2. **三路 group 是 P01 唯一 observer。** 在 Builder 尚未綁 bundle、尚未讀取任何 parent 前，group 獨占 `bind_verified_projection`。group 依固定次序把同一 snapshot、同一 parent row 傳給 MA、KDJ、volatility 三個 member。每一列只處理一次；任何 member、order、pin、limit 或 cancellation 錯誤立即毒化整組、清除暫存，並讓 exact read 失敗。
3. **保存一份 group-level parent ledger。** 每個 parent 記錄 segment index、實際驗證的 plan/receipt identity 與 SHA、cohort identity、source clock、method SHA，以及有序 included stock codes。Store callback 的 repository root 只能當 snapshot root；對外可核的 parent root 應在同一 P01 verified state 的 `segment_parent_references` 精確匹配後補入。三路不得各自猜測、重新解析或將缺失欄位互相比對成相等。
4. **將 member finalizer 拆為 prepare 與 issue。** MA、KDJ、volatility 各提供僅供 group 使用的 prepare 操作，回傳不帶 qualified seal、不可由 public caller 取得的 immutable candidate。prepare 僅檢核自身 entry count、order、request/source pins、method/schema 及該 member 的 canonical bytes；不得產生 reader-issued member session。舊 MA-only `finalize_verified_publication` 與舊 F17 路由保留原行為。
5. **只在 F17 共用發行邊界驗證及一次發行。** 在 `_issue_session_from_verified_bundle` 加入互斥路徑：legacy MA-only，或三路 group。group 路徑先驗同一 group 是同一 Builder 的 registered observer、Builder 的 `verified_session` 與 exact Bundle state 相符、P01 base query/selection 為同一已核來源，並核 group ledger 與 P01 全部 `segment_parent_references` 一一對應。接著準備三個 candidate、檢查整體 counts 與終態、建立 F17 外層 session candidate；所有驗證及最後 cancel check 成功後，才由一個私有 reader issuer 發行唯一 `ProjectionGroupSessionV2`，再把它交給 F17 session 並從正常 reader 邊界返回。失敗前任何 member 或 group partial 都不可外部取得。

## 完整性、hard gate 與可見紀錄

完整 bundle `receipt_status` 必須符合來源 reader 的既有 complete 規則：沒有 pending，processed 與 included 數量相等，parent references 與 callback segments 完全一致。未來若支援 partial bundle，必須另定 qualified incomplete contract；本切片不把 incomplete 轉成完整資格。

三路 evidence 只對實際進入 P01 verified snapshot→row 迴圈的 included/processed stocks 建立。excluded 或 pending 不會因 KDJ/MA/volatility truth 而變成合格列；F17 row scope 若明示要求顯示 excluded 的 audit row，仍可保留原可見記錄，但其研究 truth 必須是 `not_evaluated`，不可被 OR 救回推薦資格。missing technical rows 在完整 cohort 中仍保留具名 unknown；不可丟列、補值或回退到較舊來源。availability 仍為 unknown，`historical_pit_eligible` 仍為 false。

三路合併後的 query 必須將 outer eligibility、market/disposal/code scope、pending/excluded policy 作 hard gate；只在已啟用的技術、MA、KDJ、volatility rule-truth 群組間套用 AND/OR。未啟用群組不得以 `TRUE` 參與 OR；unknown policy 只作用於 hard-eligible、已評估列。此計畫的發行結果先提供完整 group evidence，後續 query 才能執行全母體 predicate、全域排序及分頁；不得用各 member 各自 execute 後取交集來代替同一 cohort join。

## Seal 與資源界限

共同 seal 至少綁定：F03 source request identity；bundle root/id/manifest SHA；exact bundle state identity；P01 read-session identity、base query/selection identity；完整 ordered parent-reference/observation digest；三 member 各自 schema/method identity、ordered index identity、population counts 與 canonical payload SHA；availability/PIT status。seal 必須由 reader 私有 issuer 持有的 opaque issuance capability 產生；dataclass replace、重排後重算自我 hash、解碼 canonical transport 都不能取得 qualified session。

資源界限需在 collector 開始前固定：股票數最多 100,000；三路各自維持已核的 compact index/entry 上限；每個 member candidate 與最終 group envelope 均須核 canonical bytes，group cap 必須涵蓋 request、member metadata、parent ledger、identity 與 envelope，不能只加總 entry body。優先採不重複複製 member payload 的 immutable references/streaming hash；超限須在進一步擴張記憶體前拒絕。取消檢查至少覆蓋每 parent、每列 fan-out 前後、每 256 個序列化/雜湊項目、每個 prepare 結束及共同 issue 前後。尺寸上限不得以低於合法三路 100,000 股 payload 的未驗估值宣稱可接受；須由真 compact fixture/上界測試支持具體數值。

## 必要驗收

- 使用正常 opt-in F17 bundle opener 的真合成多 parent source；至少跨越 segment 0 與 segment 1。精確核對一個 source open、每個 processed stock 一次 P01 row 建立、三 member 收到同一 snapshot/row object 一次，且三路 ordered codes/counts 與 P01 processed population 完全相等。
- 第一個 parent 結束後狀態仍是 `between_parents`；不得建立 member/session seal。只有 exact BundleReader 與 P01 完整 counts/reference 驗證後才可進入 prepare。錯少一個 parent、重播/換序 parent、reference/plan/receipt/root/cohort/clock/method 不同都不可發行。
- 逐一對 MA、KDJ、volatility 在 begin/consume/end 注入例外；再測各 callback 之間取消、最後 parent 後取消、prepare 各 member 時取消、共同 issue 前取消。每種失敗都確認 Builder/F17 不返回 group session、各 member partial 清除或 poison、MA 保留參照為 `_finished=True`、`_issued_session is None`，且不把一般 invalid-argument 錯誤碼誤稱為 `_finished` guard 命中。
- 測試完整 declared/included/excluded/pending/missing 分母、missing unknown、hard eligibility 不被 OR 繞過，以及 audit-visible excluded/pending 的 `not_evaluated`。若 exact opener 本來拒絕 pending，記錄此入口能力限制，不以手造 callback 冒充合格來源。
- 測試 per-member 與 aggregate canonical payload 剛好在界內／超界、最多 100,000 codes 的邊界邏輯、取消期間不產生超界中間複本；transport self-hash、`dataclasses.replace`、更換 source pin / counts / rows 後重算 identity 都不得取得 reader qualification。
- 舊 F17 MA-only opener 正向/輸出 identity 回歸：預設不建立 KDJ 或 volatility、不改原 query/bookmark bytes；新三路 opt-in 才增加成本。跨程序 recipe、全域 query/page、比較與收藏 restore 留作後續獨立驗收，不在此 slice 宣稱完成。

## 預計檔案與實作順序

共享接線只在 Root 另行釋出後修改：

- `app_module/daily_market_technical_universe_ma_alignment_query_v1.py`：將現有 MA finalizer 的驗證/建 index 部分抽成 group-only prepare，保留舊 MA-only finalizer 相容。
- `app_module/daily_market_technical_universe_kdj_alignment_query_v1.py`：增加不發行資格的 group-only candidate prepare；不讓 KDJ member group 單獨授 F03 seal。
- `app_module/daily_market_technical_universe_volatility_alignment_query_v1.py`：增加同型 prepare/完整 order、source、count、byte 驗證。
- `app_module/daily_market_technical_universe_projection_group_v2.py`：增加 parent ledger 的完整 state/reference 驗證與不可取用的 prepared aggregate；保留當前 callback-only API 行為。
- `app_module/daily_market_technical_official_disposition_query_reader_v1.py`：新增 opt-in opener 路徑，沿既有 `_bind_ma_projection` 的 request/builder/build 次序改綁三路 group，並在 `_issue_session_from_verified_bundle` 唯一發行點原子發布。
- `tests/`：既有 MA/KDJ/volatility collector 回歸、新三路真 multi-parent exact opener 測試，以及 old MA-only compatibility tests。測試使用新的隔離 synthetic bundle，不能重寫/覆蓋既有 fixture。

先做 member prepare 的純型別/Poison 單元契約；接著沿正常 exact opener 完成真多 parent、一 reader 一次的整合驗收；最後再釋出 query/pagination/UI/bookmark。此文件未授權上述共享檔修改；須待 Root 指定每片 ownership 後實作。
