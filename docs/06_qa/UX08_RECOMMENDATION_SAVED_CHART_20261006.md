# UX08 推薦 execution 保存圖表有限閉環（2026-10-06）

基線 `1454a125db0e61dbecc7522c48b236997ff7b242`，唯一 dev owner 接線；pure helper 由唯一 Luna Max lane 實作後審閱採納。沒有整合 viewport／CSV lane，沒有 push、前景 Native、正式 Task、正式資料庫或 personal migration。

## 結果與契約

同次 `RecommendationInputSession` 已接受的 `prepared_market.frame` → body publish 前價格與既存 MA20／MA60 capture → immutable `RecommendationExecution` event `recommendation_saved_technical_charts` → 既有 create-only SaveService／codec → exact queries reader → StockResearchReportReadService → 既有原生圖與精確表。writer 不另讀行情、不重算均線、不影響評分或選股；fixture 核對 provider 只呼叫一次。來源明示 `recommendation.market_frame`／`.indicators`，不假稱 SQLite 或官方資料。

每股最多最後120列；每 artifact raw256KiB／envelope48KiB，最多64張、整 capture 2MiB。保留完整推薦股票分母與 charts／missing 分割、分類缺件及計數；超圖數全碼明示 chart_count_limit，超容量全碼明示 capture_byte_limit，分母本身超界拒絕 chart capture，不讓缺圖改變推薦。只對入選來源切片正規化，避免把其他股票全部轉成 records。capture 與內層 content hashes、result／來源／market fingerprint／stock／aware cutoff pins、凍結 Mapping／tuple 都核驗。

來源行情截止日以同次 prepared cutoff 的台北日末保存，只是資料範圍宣告，不代表日末已可得。scheduled canonical 決策日另核驗，原行情 cutoff 不得晚於決策日；不把來源日搬成決策日。unknown availability、None 均線／暖機保持 unknown，缺值斷線，Decimal 字串與整數量值，不授 PIT／ML／交易資格。

reader 驗 canonical immutable execution、同次 legacy provenance、推薦完整股票分母、單一 chart event、source/cutoff/data-date/context。缺件／legacy／來源失配不借 live；即使 context scope mode 矛盾也保留保存來源規則。使用既有「另開最新研究」獨立入口、圖表／精確價格表與MA歷史表，不新增 shared UI 控制。其他 report 區塊仍按既有規則唯讀，不能以保存圖表證明原排名／方法／基本面可得。

## 驗證證據

- 去重相關案例182通過：pure15，推薦 writer／新程序 exact reopen／scheduled日期分離／來源失配／矛盾scope／offscreen consumer，加既有 execution、daily保存圖、投影、read service／shared feature／研究畫面與排程日期回歸。完整命令與輸出 `output/qa/ux08_recommendation_chart_20261006/all_related.txt`。
- Workbench85通過；update validator25通過／4略過；完整 mypy819檔通過；9個改動Python檔 compile、quant precision／look-ahead與diff check通過。
- 真 widget offscreen 背景載入價格100.125、MA20 99.123456、MA60 None；20列同源表與圖。取消保留已載入版本、重試同 chart bytes、舊callback拒收、返回保留來源；新程序重讀相同 chart JSON。實際數值見 `offscreen_readback.json`，截圖 `recommendation_saved_chart_offscreen.png`。offscreen 平台未自動載系統字體，證據fixture唯讀載入 msjh.ttc，沒有改產品字體。
- 既有 no-follow Windows reader 在 sandbox 不能開 C:/Users/archi 祖先 handle；隔離測試以已獲 auto-review 的 require_escalated 執行，未放寬 reader、未略過來源安全核驗。測試DB都在授權Temp。
- rollback／coverage／未來函數自查已先保存 `rollback_coverage.md`；原計畫233742 bytes/hash `13a841145f40f2209a7cd78735d01f5f4732b33bcae9efcd6c79474857dc9047` 原文只追加，prefix另驗。其他 owner三檔未變；既有性能例外不重開。

## 真實進度與下一包

推薦 writer→保存結果→同版圖表／精確表這個有限工程終點完成，UX08整項／stage4仍partial。9stage=1done/8partial/0pending、24UX=2done/22partial/0pending不變。舊保存結果補建、更多指標／markers、期間互動、圖商選型、Native／真人仍未驗收。

viewport lane `e52b27dd91f63982e28329f71ab966b887e994c0` 只有純controller與offscreen接合證據；待父層安排先 review/cherry-pick，StockResearchReportView 保存 controller，在 `_render_price` 投影接受後用 stock/source/version/cutoff/context identity load；按鈕操作切原 DTO，set_points後恢復set_technical_lines，價格表維持全量，補UI取消／stale／identity reset。不能只cherry-pick便稱可操作。

CSV lane consumer `f0e1d8e62727a305ee7ff74c3b42e363fecce1db` → CLI `8d0a6090` 第二hash待父層整合時精確核對。它們仍未採納；先保持獨立CLI，不重設App，不真市場匯出／分享。此包交付後等待下一包安排。
