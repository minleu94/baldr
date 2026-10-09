# F03：MA／KDJ／波動三路暫存投影協調器 v2

日期：2026-10-09  
狀態：受控新增檔的未核資格 adapter 切片；不是 F03 全母體、query、UI、收藏或保存重開完成。

## 範圍與回滾

本切片只新增：

- `app_module/daily_market_technical_universe_projection_group_v2.py`
- `tests/test_daily_market_technical_universe_projection_group_v2.py`
- 本 QA 記錄

開始前上述三個路徑皆不存在。回滾只移除這三個新增檔；不回退或修改 F17、P01、MA、KDJ、F06 volatility、Main、Watchlist 或其他 agent 的工作樹變更。本切片不 stage／commit。

## 讀取／look-ahead 自查

協調器只接 P01 已完成來源核驗的 `DailyMarketTechnicalParentCaptureV4VerifiedRead`，取其已驗 `verified_batches` 內的 snapshot 物件引用，再在原有 P01 snapshot→row 迴圈中把同一 snapshot 與同一 parent row 依 MA、KDJ、volatility 固定順序交給三個既有 collector。它不開資料庫、不讀 child artifacts、不重建 row、不延伸資料窗口、不從目前來源補資料。各既有 evidence 方法仍按自己的已保存決策截止及方法契約計算；來源可用時間仍未知，歷史 PIT 資格仍為 false。這層只是 callback fan-out，沒有新增策略或金融公式。

真正 F17 bundle exact-open、來源 parent/reference 發行、F17 session 發行及合格 index/query/page 尚未接入本模組。單獨跑本測試不能證明 F17 bundle qualification 或 full-N product completion。

## API 與不變式

唯一建構入口為 `DailyMarketTechnicalUniverseProjectionGroupV2(ma_source_request, cancel_callback=None, max_stocks=100000, max_total_bytes=201326592)`。KDJ 與 volatility request 均由同一個 `ma_source_request` 物件建構；KDJ 使用既有 MA+KDJ pair group 私下滿足 exact member 綁定，但 P01 Builder 的唯一 observer slot 只綁本三路協調器。協調器不公開 `members`、entries、index、finalizer 或 publication API，僅提供狀態與已處理數量的診斷欄位。

`bind_to_builder` 只能成功一次，並在讀取開始前把協調器綁到 P01 Builder。parent 開始前先核 exact typed parent/batch/snapshot 型別、batch 每批最多 16 列、總數不超 request／100,000 上限，通過後才建立有界 snapshot 引用 tuple。parent 順序必須連續、segment index 必須是嚴格 `int`（不接受 `bool`），相同 plan/receipt identity 不可跨 segment 重播。每列三路都必須恰好新增一個相同股票的 compact entry；任一子路失敗、數量不符、來源錯配、順序錯誤或取消會永久毒化整組。

失敗毒化會清除全部暫存 entries、observations、seen-code 與 parent 暫存。MA collector 被設為 `_finished=True`、`_issued_session=None`；即使呼叫端先前保留 MA collector 參照，也不會留下可用的部分 observations/entries。KDJ pair group 與 volatility collector 同步標為失敗並清空。測試另對保留的 MA 參照呼叫帶有刻意無效 DTO 的 finalizer，僅核對呼叫被拒；該負例不歸因於 `_finished` 分支，因無效 DTO 或 Builder projection slot 同樣可能觸發同一錯誤。取消 callback 在建構、綁定、parent 開始、每個 member callback 前後、parent 結束及狀態發佈計數前後嚴格檢查；回傳非 bool 或丟例外均不作成功處理。

資源上限沿用既有三個 member 各 64 MiB compact index 上限，協調器另核三路暫存 compact entry JSON bytes 加換行分隔的累積總和不超過 192 MiB，並核每個 KDJ entry ≤4 KiB、volatility entry ≤16 KiB；股票上限為 100,000。此 192 MiB 只限制暫存 entry buffers，不含最終 index identity、source request 或外層 envelope；日後發行層必須獨立核完整 canonical payload 上限。超限時至多在當前一列三路處理後檢查，隨即毒化並清除全部暫存，沒有 partial output。

即使 parent callback 已返回，狀態也只會是 `between_parents`；它不表示 bundle、完整母體或整個 exact read 已完成。未來正式 publication seam 仍須由唯一 reader authority 核完整 counts、所有 parent references、bundle/P01 source pins、clock/method及終態，不能信任此處的 callback 診斷計數。

## 測試界線

新增測試重用既有真合成 `synthetic_small_full_store` fixture：由 SQLite producer 建立 technical snapshots、parent capture 及完整 P01 store，再以 `DailyMarketTechnicalUniverseV4StoreReader.read_exact_with_verified_parent_callback` 呼叫真 Builder observer。它沒有 fake parent row、沒有直接呼叫 leaf 公式、沒有 SQL 到正式資料，也沒有觸發 full-N fixture。對 fault/cancel 矩陣，測試重用該次 exact-read 收集到的真 typed parent、snapshot 與 row 物件，在新 group/builder 上逐一驗證 MA、KDJ、volatility 的 begin／consume／end 失敗及 callback 後取消均永久 poison；沒有為每種注入故障重開來源。

案例核對三個 callback 對每一股收到相同 snapshot 與 parent-row 物件、精確處理數量、exact read 之後仍只顯示 `between_parents`、Builder 不發行 verified session；也涵蓋 constructor/bind 取消、錯 clock、parent replay、`bool` segment 索引拒絕、三個 member 在 begin／consume／end 各自故障及回呼後取消、單股暫存 entry budget 失敗，以及 poison 後 MA 的 `_finished`、`_issued_session` 與 partial buffers 結構狀態。帶無效 DTO 的 finalizer 呼叫只作一般拒絕案例，不證明是哪一個 guard 拒絕。這些測試只驗三路暫存協作與 fail-closed；不代表跨多個真 parent segment、100,000 股／192 MiB buffer 上界、F17 exact bundle、qualified full-N query、排序分頁、收藏、UI 或 fresh-process restore 已完成。

下一片需由 Root 審核並提供受控 publication seam：由唯一 reader authority 在完整 source read 成功後原子核驗三個 member 的終態與完整 parent/store pins，再發行一個不可拆分的三路資格物件。不得先讓 MA 發行，再由 KDJ/volatility 失敗；不得讓外部取得 members 後分別 finalize；舊 MA-only 與 F17 預設路徑成本及語義維持不變。
