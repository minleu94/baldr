# 補完範圍再核對（2026-10-08）

本次核對保留原補完計畫範圍，不以目前已完成的技術研究頁代替所有選股條件。依據為目前 app／UI／query contracts 與只讀代理審查；不包含正式資料 SQL、重新訓練或正式排程變更。

## 使用者回報與驗收仍開放的項目

- d9a115f67d2b 的推薦理由、排名門檻及排名因素不能完整閱讀，仍屬未接受。93f9c57d7995 已提供整頁捲動候選，真人需確認最後一段可見；不能以文字存在或 widget 測試代替真人接受。
- 2382 個股證據約 20 秒，尚未證明已加速。首次名單、選股下鑽及獨立目前行情需分開量測。
- 原 H20 毛報酬估計與另一份一般 ML 報告的缺件各自判讀；後者不能否定前者。獨立目前行情入口已接，但不能代替原 H20 同版圖表。
- 篩選紀錄只回答「為何未入選」。量能變化 -31.229…% 未達要求 +50%，在打分前停止，沒有推薦分數或排名；此紀錄不足以代替完整個股研究。

## 全母體與條件覆蓋

P01 技術 v4 的契約上限為 100,000 檔，每頁上限 256；目前接受的合成保存版本不代表實際全市場覆蓋。F17 官方市場／處置研究已接保存版 catalog、exact read、完整 cohort 篩選、全域排序、分頁、比較與收藏；尚未接正常來源更新至產製的產品閉環。

| 條件 | 實際缺口 |
|---|---|
| F01 均線金叉 | 已保存 MA5／MA20 交叉；不等於 F02。 |
| F02 均線轉強 | MA5／10／20／60 嚴格排列已有版本化後端證據及正常 exact opener；複合 query 完整接線／UI／收藏仍待，MA20 上彎尚無此產品事實契約。 |
| F03 KD／KDJ | KD 5/3/3 SMA 已接；KDJ 未完成。 |
| F04 MACD | 已接 12/26/9 交叉。 |
| F05 量能 | 已接具名 20 日／5 日含當日比率；舊策略口徑須分開。 |
| F06 波動收斂 | 缺完整窗口、基準與突破條件。 |
| F07 價格區間／排序 | 已有獨立 v1 Decimal 收盤價範圍／全域排序、分頁／比較／收藏與來源版 257 股 Main／新程序讀回；固定 EXE 已還原保存狀態，但完整守衛／收尾及真人接受仍未通過。 |
| F08 分點、F09 法人連買 | 有原料／既有服務，缺保存全母體事實及可得時間契約。 |
| F10 權證 | 缺標的關係與掛牌／到期／終止來源契約。 |
| F11 基本面、F12 月營收 | F12 有獨立 Decimal 事實與測試；未併入完整母體 query／UI。 |
| F13 族群強度、F14 族群核心 | 未接版本化保存事實與全母體條件。 |
| F15 新資金 | 未接；成交金額不能冒稱已核淨流入。 |
| F16 注意股票 | 有 current reader，缺帶 coverage 的保存事件條件。 |
| F17 官方處置 | 保存研究路徑已接；正常更新／產製閉環及歷史資格未完成。 |
| F18 處置預警 | 缺可核公開規則版本與事件歷史。 |
| F19 日期／風險 | 技術與 F17 有 cutoff／unknown 限制；其他域未統一。 |
| F20 多欄排序 | 技術／F17 部分已接；價格、籌碼、營收、族群未綁定。 |
| F21 分母 | 選定保存 cohort 的 declared／included／excluded／processed／pending／missing 已接；非全市場證明。 |
| F22 多策略、F23 三面向共振 | 未完成；五項技術規則不能替代多策略或三資料域。 |

權威程式入口：`daily_market_technical_method_contract_v4.py`、`daily_market_technical_universe_v4_store.py`、`daily_market_technical_universe_v4_query.py`、`daily_market_technical_official_disposition_bundle_v1.py`、`daily_market_technical_official_disposition_query_reader_v1.py`、`daily_market_technical_official_disposition_query_v1.py`。

## 接續工作與證據要求

1. H20 綁定 OHLCV 圖表：沿同次 private copy 核驗的原 logical-row hashes 投影，初讀／終態一致後才簽發程序內 view；不重開來源、不改原 capture，不用 latest 補值。摘要需分列原 H20 圖表與一般報告完整度。
2. F17 正常來源閉環：先核實既有 updater 的公開 raw capture／exact pins 出口，再以明示 pins 產製保存 bundle，正常 catalog 選版、比較／收藏、新程序 exact reopen；取消／失敗不得發布。
3. F02 的排列後端需完成複合 query／UI／收藏；MA20 上彎及 F06 仍需明示版本化事實契約。F07 已有獨立價格 v1，但完整 EXE／真人接受仍待。其他資料域需各自可得時間與完整母體接線；不得直接把舊 v4 五規則宣稱為全條件完成。

F17 目前仍是 `current_only`、`official_available_at=None`、`historical_pit_eligible=false`；source coverage 與 projection completeness 必須分開。最新獨立程式封套 `output/qa/f17_native_same_source_20261008_a/attempt_116cdedcf554/controller_receipt.json` 為 `failed_preserved_attempt`，總 deadline 300 秒，source parent 未完成，因此尚未啟動 frozen child；不能授予 Native、真人、效能或正式來源接受。

1,000 檔固定合成保存版本的 source-only 效能控制器已結束（root session 92712，exit 1，attempt `C:/t/p01_4jr3cl29`）。五個 cold 與一個 warm 均保存 `TypeError: 'NoneType' object does not support item assignment`，沒有 bootstrap、PID 或有效 sampler／延遲樣本；完整矩陣未取得，所有 p95 接受均未授予。靜態核對指出 pre-spawn exception handler 對仍為 None 的 termination 賦值會遮蔽原錯誤；此為待重現的診斷，不能當作已知底層觸發原因。下一修正須保留原 traceback／cause／實際清理狀態，pre-bootstrap supervisor failure 應立即停止矩陣，不能重複跑五次相同缺件或捏造零殘留證明。

F17 最新封套的 source parent 另確認 catalog 更新成功且只有一筆候選；逾時發生在「選取保存版本並 exact-open」背景 worker，沒有結果頁或 app-side error。`close_error` 使用已過期的全程 deadline，因此不能據此另判 Main 關閉缺陷；目前封套未證 cooperative cancel latency。下一步需分段記錄 exact bundle／技術來源 open、execute 與 page 的耗時，不改 pins、成功條件或總期限。

正常官方更新確有原始輸出：`refresh_current_market_status_observation.capture_sources` 保存 raw bytes、manifest 與 current pointer；`CurrentMarketAssignmentReader`、`CurrentOfficialDisposalReader` 提供 typed source pins。尚缺將正常更新輸出與技術 generation 送入 `create_from_pins` 並回報保存版的接線。兩 pin 的 cutoff 必須與技術 clock 相同，來源捕捉與 pointer 發布不得晚於 cutoff；較新捕捉不能補入舊 generation。

## 更新記錄

- 2026-10-08 分段診斷：隔離 attempt `attempt_5e851f27208e` 的 controller 為 `failed_preserved_attempt`，全程 281.046 秒，沒有啟動 frozen child。實際 call-site 記錄顯示 `bundle.read_exact` 成功返回、耗時 143.357 秒；隨後 `p01.open_read_session` 耗時 121.005 秒，以 `technical_universe_v4_query_cancelled` 結束；外層 bundle session 累計 264.655 秒。尚未進入 selection、execute 或 page 階段。這是含診斷記錄的合成案例，不能授予產品效能接受，也不能直接套用至使用者 2382 的 20 秒問題。

- 2026-10-08：對照使用者回報與目前程式，保留全條件缺口、H20 同版圖表與速度驗收，記錄 F17 失敗及隔離效能驗證的範圍。
- 2026-10-08 接續：root 審查並重跑監督失敗契約 5 項通過；控制器 `5e906b4d…` 的新隔離 session 14029 為 exit 1，封套 `C:/t/p01_30udafr3/input_integrity_failure.json` 在首個 cold worker 後停止。完整 traceback 證明 Popen 使用 `DEVNULL` 時開啟 Windows `nul` 裝置被 C63 寫入 guard 拒絕；不是股票引擎錯誤，沒有有效延遲樣本。待改用該全新 attempt 的空 regular-file 標準輸入，不放寬原 guard。原 `C:/t/p01_4jr3cl29` 失敗仍保留。
- 2026-10-08 標準輸入修正後：root 審查 `5f3f8e53…` 並重跑 7 項契約通過，包含真實合成 worker 讀空輸入 EOF 與 Job 清理；新 session74142／`C:/t/p01_z1brdyqa` 仍為 exit1，首個 cold 後停止。真 C63 audit 對所有 `subprocess.Popen` 無條件拒絕，與 parent 的六個精確 worker 啟動許可無法在同一 interpreter 組合；交換 hook 順序也不能解決。接續改為 parent 專用、精確 QA metadata 寫入與啟動守衛，worker 繼續原 C63 全保護及禁止子程序。須以真 C63 worker／真 parent guard 的隔離組合測試核對，不能以先前 synthetic guard 自測宣稱完整矩陣可跑；冷暖效能仍無有效樣本。

- 2026-10-08 中央審查補記：H20 固定 bd5d2f86367a 的隔離 Python／EXE 比較通過並交真人，捲動與原保存來源等待仍未接受。F17 單次核驗 builder 尚待中央完整回歸；已要求保留來源工作前的取消拒絕。source-only benchmark parent guard 的 denial 只在整體收尾檢查不足以證立即停跑，已要求每個 launch 前／worker 後檢查；本輪沒有新的效能樣本。

- 2026-10-08 F17 單次圖核驗中央 46 項回歸通過，來源修改本機 commit `330b98f416f718c601c96edb31e6cb9823a3b150`，固定 EXE 建置進行中，Native／效能仍待。1,000 檔 attempt `C:/t/p01_yyuuqth0` 首個真 worker 完整讀回並產生頁面，但 parent metadata helper 多餘 mkdir 被 guard 拒絕，整體 exit1，矩陣停跑且 cleanup unknown；不授 p95。F07 明示數值價格區間與全域排序已分配新版本 query 設計，不改舊 v4 保存契約或以最新資料補值。
