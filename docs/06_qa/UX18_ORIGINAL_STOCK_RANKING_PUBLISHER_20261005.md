# UX18 原引擎排名不可變發布與同源讀回

> **閱讀界線：** 「來源語意及相容性」與「剩餘工作與接受邊界」中的排名收藏／個股路由待工程，是 publisher-only 收尾時點。2026-10-05 的有限收藏與個股來源版本化收尾見本頁末段及[原排名收藏與個股來源版本化](UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)；它只關閉該 bounded 子項，不取代其餘待辦。

基線 `27768eb9ee0896668c80312580f49e74794e2d4b`，沿唯一原計畫新增有限工程收據。原 StockScreener 價量公式與引擎檔案不修改。本包僅背景／offscreen，未操作使用者視窗。

## 發布與消費契約

- 已核驗 feature snapshot 及明示有界母體為 parent；來源 DB query-only、每股最多120觀測／最多16股。重新核對原輸入指紋、schema、DB／WAL、母體設定及引擎來源。
- 原生 day／week × strong／weak 分別保存 immutable artifact、manifest 與 atomic latest。方法／版本／固定參數、母體、decision date、逐股原比較日、價量變化、native rank／score label、來源 hash 與 research-only 資格全數保存。
- reader 不啟動原引擎或 producer；UI worker 讀回，模式切換捨棄過期結果。Daily 清單、候選摘要與研究母體 Market 使用同一排名 DTO／parent identity；沒有來源、錯來源或缺排名不補值，不以 MA 替代。
- 原排名排序按 native rank，不重新編號篩選後列。原引擎未排名股票保持未知；母體研究成員與原 eligible 成員分開。完整來源審計保留提示，首屏來源 ID 縮短。
- unchanged 不重跑引擎；200GiB reserve、8MiB 新增／暫存、64MiB／4096項儲存界限。writer OS lock 在程序退出後釋放，取消／中斷保留已發布來源；不自動清理。

## 來源語意及相容性

舊引擎已用 Top／Bottom 百分比字串覆寫內部數值評分，因此沒有暴露數值 score。發布器原樣保存字串，不能反推數值或修改原公式；該百分比不可直接按一般「前幾％」或勝率解讀。day 比較前一觀測，week ≥6筆比較倒數第6筆，3–5筆比較倒數第3筆；保存實際比較窗，不冒稱週OHLC或固定完整週。量能沿20／5／更少既有窗口。

feature v2 schema／舊收藏不改寫。舊來源沒有排名時仍可按原 MA／Decimal 指標使用；原排名排序收藏明示拒絕，避免 silently 退為代碼排序。新排名收藏與個股報告 source context 須另做版本化。隔離 ranking root 必須由 consumer 明示配置，不改主要App預設。

## 剩餘工作與接受邊界

已交付範圍為有界研究母體的原生四模式排名發布／讀回及兩 consumer。第一版仍須工程：排名身份收藏／回訪與個股報告路由；其他原大盤／強弱 consumer 融合；完整 feature／method dictionary；正式母體與排程部署；長期 storage／growth 及其他生命週期 crash 驗收。這些不是等待自然成熟。

來源決策另列：正式合格母體權威、官方 availability／歷史 membership／PIT；舊 Top／Bottom 標籤口徑及數值 score 暴露須原引擎方法決策。手工三股 research scope 不授全市場排名、勝率、正式推薦或自然 ML 資格。

原 Backtest 18.62%／20%門檻未達，本包不重測或放寬。Native鍵鼠、縮放、跨頁、全App startup及3–5真人驗收待桌面時段；offscreen不能取代。沒有全市場採集、正式DB／registry寫入、訓練、大DBcopy、永久清理或push。未知capture及還原映射未動。

## 更新記錄

- 2026-10-05：新增原排名發布／消費契約與明確接受邊界；最終驗證見下節。


## 最終有限驗證收據

- 87個不同受影響測試有pass證據：首輪82pass／4fail，僅四失敗精準重驗4pass；另新增inflight mode切換1pass。舊UI fixture接受新可選original_ranking參數，無來源排序項文字補明示未提供。模式fixture初輪漏sync_cutoff參數修正，原失敗保留。agent22／4與root重疊，不加總。
- Workbench85pass、validator25pass／4skip／0fail；全域mypy783source、12個changed Python compile、金融float／look-ahead guard通過。第一輪14個typing標註問題已修，runtime仍lazy import，首輪log保留。
- 真D query-only1477／2330／2382，決策日2026-10-05；既有已發布feature parent SHA `2d241068d3b6df9a06c65267da0c0925c30d3244c6116da626d6a537f742311c`。四mode各published/readback、eligible3／missing0，再觸發day strong unchanged且rank inventory完全不變；正式DB／WAL／SHM stat、原feature全部5檔inventory、引擎SHA自本包preflight至final一致。
- 200GiB預檢通過、四mode總檔案內容18478bytes（含pointer，不是filesystem allocation）。每股120筆上限，未全市場／collector／train；比較window逐股保存，metadata完整publisher run identity明示非legacy原run。
- 真D來源＋隔離rank store的8張offscreen圖，Daily／Market共享同rank object，四mode分離且parent不變；worker0、finalcodepins一致。字型用既有helper，非Native／真人／全App startup。

| 模式 | rank manifest SHA256 | eligible |
|---|---|---|
| day_strong | `775a9931fc4fb215e36a36f9c593fdb27c9c820a37d27e0c9e11fd486a0e8605` | 3 |
| day_weak | `f43cc89c0571f50788a27408f036ee2c1f95f08be4eb254a77cd4c4bf4c1c211` | 3 |
| week_strong | `75f07044a31186abc1ae317a8aeb3944a4c5cd60d868e59a14745adf16d73e11` | 3 |
| week_weak | `77af9eca06c49a5115f51f588522d9b7492f6422a91d1e38394c3a6b89ecd192` | 3 |

raw output維持ignored：`output/qa/original_rank_publisher_20261005/verification_summary.json`、`real_publish_receipt.json`、`offscreen_receipt.json`、initial/repair/mode XML與log；本地commit與blob讀回見同目錄commit_readback，未push。soleplan原151202-byte prefix SHA `6e3cca0947eb87d191513bbccfbf926a61f3f032a092390221fa21ea2b5331f2`保留。

## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

[原排名收藏與個股來源版本化](UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)：已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。 受影響測試 136 首輪通過＋1 項定向修正後通過（合計 137 個案例）；Workbench 85；更新頁 validator 25 通過／4 略過；mypy 783 檔；18 個 Python 檔語法與 quant guard 通過。 既有 publisher QA 的「原排名收藏尚待」僅是上一版本狀態；本批僅補 consumer／收藏，未重跑 publisher。
