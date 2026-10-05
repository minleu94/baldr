# UX09 長期歷史索引、分頁與程式內版本復原（2026-10-05）

本包完成研究限定的可重建 manifest index、背景分頁與索引版本復原。唯一原計畫為 `output/plans/baldr_product_experience_plan_20261004.md`，只追加。起點 2ca5bb09726d1ea0051ad1611ea53fb934179410；本包期間其他 owner 的 edcfe021d56c04a91f1326b270cfe32b14b732b7 保留為父提交，不讀改該 Paper 入口。其他對話資料容量／Evidence 修改由使用者確認其責任，排除本包。

## 交付與邊界

- `research_membership_history_index.py`：index／pointer／cursor／generation v1；manifest v2 strict metadata。SQLite keyset pagination、固定 cohort/as-of/date/current-pin/generation/query，日期與發布時刻升序呈現；同日 revisions 各列。預設 sibling cache，不容許落 immutable source 裡，也拒絕 redirect／reparse 路徑。
- `daily_market_research_screener.py` 與 read model：已存在索引就使用最近最多 31 歷史 refs 加當期，來源三態與相鄰交易日核驗沿既有方法。不完整頁可判已核驗相鄰變化，但首次觀測／連續期數僅本頁；不能宣稱全歷史首次入選。缺索引維持舊有界 reader；索引存在但無效時 fail closed，不自動建立或 fallback 冒充完整。
- `research_membership_history_view.py`／UI：當期來源固定，選股歷史另窗最多32觀測；導航只保留64頁游標滑動窗口，較早頁可繼續超過64頁。背景 TaskWorker、合作取消、失敗／過期回呼／錯 pin 保留當期研究主線；建立索引必須明示，不寫歷程事件。
- CLI `manage_membership_history_index.py rebuild|rollback`：只管理派生索引；每次建立新 generation，完整驗證後 atomic activation，啟用前失敗／取消保留舊 active。來源變更不接受舊 generation 回退當現況。晚到取消與完整啟用依 receipt 核對，不移除任何舊 generation／staging。
- 年度 calendar 累積超過32份原本會整批未知，改為有界串流驗證（目錄4096 entries、年度32MiB），只保留最新有效 cache；40份 fixture 與超位元組預算拒絕已驗。沒有網路／producer，也不放寬 availability／休市來源或 historical PIT。

每頁對整個 index 串流 SHA（chunk1MiB、generation最多64MiB），不以 size／mtime 代替內容核驗；same-size且恢復mtime的 mutation亦拒絕。每頁最多32 refs、manifest輸入與DTO輸出各32MiB，consumer manifest/artifact頁讀32MiB。重建掃 manifest metadata、不把全部 artifact archive 載入 RAM；分頁只 strict讀本頁與current pin，原始 archive 未讀artifact不宣稱全域重驗。source fingerprint是來源路徑／目錄stat／manifest數量的變更界線，不是假裝全 archive 內容hash。

索引／pointer未知schema、manifest v1／v999明示拒絕；manifest v1原 reader 已不支持，沒有隱性升級。既有合法 MA bookmark v1及rank bookmark v2的immutable參照契約不改。consumer fault 測試核對 MA bookmark payload與pinned v2來源；既有rank pinned-refs保護未改、前批已驗，本批不重跑 publisher。

## 最終驗證

| 範圍 | 結果 | 本機 raw 收據 |
|---|---|---|
| 新歷史UI、既有UX09／UX04 view、lifecycle／reader（含40份calendar） | 41 pass | `root_final_retry.xml/txt` |
| 既有 screener 來源／條件契約 | 15 pass | `screener_final.xml/txt` |
| 真 CLI建立／重建／回退與無效generation | 2 pass | `cli_final.xml/txt` |
| Index 分頁／schema／cancel／fault／source／預算／same-size hash | 12 pass（11＋新增1） | `index_agent/pytest.log`、`same_size_hash_test.log` |
| strict reader→service→TaskWorker／UI及bookmark fault | 9 pass | `recovery_agent/pytest_final.txt` |
| UI強制作業 | Workbench85 pass；validator25 pass／4 skip／0 fail | `workbench_final.txt`、`validator_final.txt` |
| 型態／語法／量化防禦 | mypy788 source files pass；11變更Python compile；精度／未來函數guard0違規 | `mypy_final.txt`、`compile_quant_guard.json` |

前五組合計79個不重複案例；Workbench與validator另列，不累加重跑次數。未跑全套回歸／正式 producer／ML／排程。pytest cache權限警告及Qt teardown通知不影響通過。索引12項最終收據需與agent附錄一起核對。

初次失敗保留：browse首輪選中股取得方式錯誤已修正；index編輯中Windows fsync O_RDONLY、SQL Row／type錯誤已修正；CLI在未凍結helper狀態的初輪失敗已保留，凍結後2 pass；root首輪測試檔名誤植未collect，正確路由41 pass；consumer取消錯誤原期待底層IndexError，依既有service映射DailyMarketResearchCancelled修正後9 pass；全套mypy初輪11 index模組錯誤修正後788 pass。真實harness第一次呼叫current read_latest觸及正式DB的檢查被guard拒絕，沒有放寬guard；改為strict保存來源pin回放，不能宣稱這次重核了當期DB身份。

## 合成較長歷史資源量測

130決策日×2同日revision＝260 manifest fixture，沒有artifact objects。重建 wall0.296080s／CPU0.140625s，generation159744 bytes。走9頁260個不同refs，無重複／缺漏、最多32refs／頁；wall0.375762s／CPU0.359375s。最大page JSON13814 bytes、tracemalloc峰值1226583 bytes；每頁index SHA159744 bytes（全走1437696 bytes），manifest JSON268讀／349204 bytes（current pin重核另讀）。收據 `index_agent/resource_measurement.log`，原始source保留。這是合成metadata工程量測，不能當自然20session或全市場artifact／SQLite／WAL／backup容量驗收；所有generation保留會成長，中央reserve／真實部署總預算仍由F4收尾。

## 既有真實快照隔離回放

三股1477／2330／2382、cohort `ux16-three-stock-research`，完整僅相對3股research cohort。strict讀已保存manifest，不連線正式DB；derived index只寫QA隔離根。manifest SHA `2d241068d3b6df9a06c65267da0c0925c30d3244c6116da626d6a537f742311c`；identity `6c4a3fd3c82f074f5085a9ac6dff0437c7ba287c80ea8e696bc16118d3f2d9e6`；cutoff2026-10-05T23:59:59+08:00；publication2026-10-06T00:41:36.077969+08:00。三股歷程unknown，2382歷史頁1列unknown（翌日發布，當時可得性未證明），保留source_available_at未記錄。17份snapshot/rank來源hash不變，正式DBsize/mtime不變，worker0。engine SHA `48c58d292c5cd5182a5e9ecbb98205790742a61207c88bad34e81f2f41ef6ed2`不改。

Raw根 `output/qa/ux09_history_recovery_20261005/`；`real_readonly_receipt.json`、`real_history_page.json`、`real_lifecycle_replay.json`及3張real_single_date圖片。Root實際看歷史頁像素：日期／股號／未知及理由可讀，長發布時刻欄位省略但tooltip保留來源；無錯字方框。本包offscreen，不操控使用者視窗，不能當Native或真人驗收。

## 回滾與交接

程式回退沿本包explicit whitelist commit，派生索引可明示rebuild或同source完整generation rollback；不用刪source／real DB／bookmark或清理舊generation換pass。索引schema／版本復原的工程子項已關閉，正式部署／資料遷移與其餘工程不被這項收據替代。原計畫追加保留162440 bytes原prefix（SHA91b1e1b7d6de4afbd7e96214b955ba53127e56535af240452710080a6983c97b），最終hash／commit blob讀回在本機receipt。

# 第一版 stage 1–3 工程凍結清單（2026-10-05）

沿用唯一原計畫，不擴展 UX01–24。此表限定第一版既有技術研究流程；新增圖表、題材、新聞、ML target、策略模擬及新方法屬原階段 4–7，不移入第一版。每項 owner 是後續單一責任角色，父層安排有限批次；本包不啟動表外工作。

| ID／原 stage | 尚需交付的工程 | 明確終點 | 唯一 owner |
|---|---|---|---|
| F1／1、UX17 | Backtest 初始化凍結門檻差距 | 同基線、同設定五跑 median 改善至少 20%，結果身份／首屏／記憶體無回退；或父層記錄使用者明確接受的例外。現有 18.62% 差 1.38 個百分點仍未達，前次「不為湊數微調」沿用，本包不重測／放寬。 | Sol 效能 owner；父層審核 |
| F2／2–3、UX13／18 | 尚未接共用 immutable 來源的原盤勢／強弱 consumer | 原大盤／強弱與研究名單明示相同 cohort/date/method/hash；day/week、strong/weak、完整 eligible／排除、原標籤不重算，榜外與來源缺件分開；切換／返回不 producer；受影響 consumer 與 source-change 拒絕案例通過。原大盤統計不以三股 cohort 冒充全市場。 | Sol consumer 整合 owner |
| F3／2、UX16／18／19 | 完整 feature／method 能力矩陣與正式合格母體的接線界線 | 首版已開放 close/MA20/MA60 及兩條固定方法的欄位／單位／暖機／缺值／availability／版本／成本／來源逐項登記且未知明示；未開方法停用不新增字典項。當期研究可保留 A 具名 full-cohort。若採 B 官方母體，固定 TWSE/TPEX 名冊時鐘、raw custody、納入排除／分母及完整分批，部分不冒充完整；原資料管線 owner 提供新同版收據。歷史 PIT 證據不得由接線補造。 | Sol source-contract owner；既有資料管線 owner 負責正式來源／容量 |
| F4／1–3、UX17／19／24 | 首版跨頁整合與資源／部署終驗 | 明示來源配置的隔離 MainWindow 啟動→查詢→個股→收藏→精確返回→新程序原來源讀回；舊 schema 明示支持／拒絕，取消與過期回呼不改 last-good；兩種 research／original-rank source 同 identity，有限 queue/cache；20 session＋較長保留預算納入實體、staging/WAL/index/backup及當下中央政策，未知容量不 writer。不重做已接受 UX19 fault 或 Native1477。沒有正式排程部署授權時保留明示執行模式；Windows 排程變更另由既有排程 owner 授權執行。 | Sol release-integration owner；既有排程／容量 owner 保留其子責任 |

本包只關閉 UX09 長期索引／分頁及索引程式內版本復原子項；合成長歷史量測不是自然增長或自然樣本。原 immutable 快照、原收藏 schema／refs 與其他 owner 修改保留。工程缺陷列在上表，不能改寫成等待自然成熟。

## 外部驗收／證據，與工程分列

- **已完成舊 Native**：1477 cancel terminal→retry→save→新程序原來源讀回、錯 date/run/hash，沿 6691ec784eea6e020d181d8e0aacc485679910a2 及 NATIVE_1477_RETRY_READBACK_ACCEPTANCE_20261005.md。上一 UX09 附錄沿用較早「仍待」文字過時，以此及原計畫 09:23 UTC 最新收據為準；不重跑。
- **新 Native 待驗**：本次歷史索引／分頁、原排名／跨頁鍵鼠與原計畫未驗縮放範圍，安排可用桌面時段。本包只 offscreen，不操作使用者程式。1000×835 outer／125% 已接受；不將 1000×800 未達重新列硬門檻。
- **真人待驗**：3–5 位未參與開發者依原 §12.1 任務，記錄耗時／求助／誤解並修前三障礙；不能拿開發者測試代替。
- **自然／資格**：跨真實日期的合格觀測、官方原始 availability／historical membership／PIT、H5/10/20 成熟與 ML baseline/OOS／投資效果各自保存；不以 fixture、翌日發布或 current-only 快照宣稱通過。

## 先前來源權威與 Top/Bottom 決策：具體選項

本包不需要新用戶決策；保留現有研究限定可推進。

| 題目 | A：本包最小建議，沿現況 | B：擴充時要明確決定 |
|---|---|---|
| 母體權威 | 具名人工研究母體 daily-market-research-universe.v1，保存原設定 bytes/hash、納入／排除理由及已知／未知分母；完整僅相對 declared cohort，不宣稱全市場。 | 採現有 registry 的 TWSE t187ap03_L（data.gov.tw/18419）與 TPEX t187ap03_O（25036），CSV expected denominator 配 OpenAPI/raw custody，固定 decision/observed/available 時鐘、coverage_start與排除政策；興櫃 t187ap03_R 僅明示選入後開放。這是 prospective 當期名冊，不補造歷史成分。 |
| Top/Bottom 用語 | 保留原 StockScreener 原完整字串，標示「原引擎標籤；非一般前幾％／勝率」，列實際比較窗與缺數值分數；不改算法／排名／收藏身份。 | 若要更正百分位口徑、公開原 numeric score 或新增 TopN 入選 predicate，先各自定 method/version、分母、窗口、方向、缺件與 tie policy、回放與 UI 語意，明確批准後新版本發布，舊收藏仍讀舊源。不能反推未存分數。 |

A 不阻擋工程收尾；B 才需要產品／來源版本決策。ML 排序或下行 target、圖表選型與商業授權按原階段決定，不當此包泛詞阻塞。
