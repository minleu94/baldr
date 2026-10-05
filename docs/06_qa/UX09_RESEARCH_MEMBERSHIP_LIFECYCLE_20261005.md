# UX09 研究名單入選生命週期有限包（2026-10-05）

基線 `708284919f2b0ac994bbf499281a2d36883d9aa4`；前批 UX19 與另一對話 `39cc1ec` 保留，不重做或改其容量／Evidence／Paper 檔。唯一原計畫 `output/plans/baldr_product_experience_plan_20261004.md` 保留並僅追加。

## 原計畫條文與依賴

|原條文（本包啟動前行號）|要求|本包落點|
|---|---|---|
|§8.1，361 行|「本次新入選」「持續符合」「重新入選」「未再符合」「無法比較／歷史不足」；沒有足夠歷史只能首次觀測|讀既有 MA 三態結果，不稱自上市首次|
|§8.1，363 行|分組取策略／版本／設定／商品／市場／研究範圍；日期與 run／result 是各次身份，不要求值相同；daily 按 session／weekly 按自身節奏|同 semantic 方法／母體／窗口，保存各次 hash／cutoff／publication；不造 weekday session|
|§8.1，365–367 行|只有完整可比執行能判變化；失敗／缺價／母體改變／改版／修訂／保存失敗不算退出；重入必須先命中→有效未命中→再次命中；不得刷新時隱性建歷史|純讀模型與可回放 identities，沒有新 event ledger 或策略升降級冒充|
|§10，588／591 行|快照依賴必要來源／容量；階段5自然追蹤依賴 custody／calendar／capture-outcome 合約|沿已接受 bounded current-observed 快照，只做 UX09 read projection；自然 capture／outcome 未啟動|
|§11，623 行|UX09「比較模型、欄位、列表與歷史視圖」；漏日／失敗／改版不算退出與重入|名單／候選至少顯示狀態、前次日期、原因與來源回放|
|§12，671／674 行|缺快照／失敗／停市／改版／母體／新上市／修訂不造退出；cutoff 後資料不改舊訊號|unknown 邊界及 as-of publication／晚到回填隔離測試|
|§14，781 行|「既有快照是否足以做名單生命週期：不足則顯示歷史不足，自此向前累積」|現有真實來源僅同日，明示歷史不足，不重跑過去資料補造|

這些條文允許有界研究切片，沒有要求先更換母體權威或重定義原 Top/Bottom。可比較 calendar／source evidence 未達時顯示 unknown，不對漏日作負樣本；它是資料／工程接受條件，不是等待使用者選新策略。本包不宣告首版或完整階段5完成，Backtest18.62%／20%原缺口保留。

## 母體來源的具體候選與最小建議

|現有候選|本地權威與差異|本包採用／真正需決策的情境|
|---|---|---|
|明示具名有界研究設定|`app_module/daily_market_research_universe.py` 的 `daily-market-research-universe.v1`：ID/version/as-of、納入／排除理由／分母、source bytes hash、bounded_research_cohort、research_only；例如既有1477／2330／2382、排除2317批次|**建議沿用**，不授予全市場或PIT；相同semantic成員／排除／方法政策才可比，日期／raw hash保存各次身份|
|官方當期上市／上櫃 prospective 封套|`data_module/pit_prospective_denominator.py`：TWSE `official:twse:t187ap03_L`／data.gov18419官方CSV及OpenAPI；TPEX `official:tpex:t187ap03_O`／data.gov25036官方CSV及OpenAPI。JSON source custody、獨立CSV expected denominator、metadata／Swagger／授權指紋、coverage_start後 clock-bound create-only|現有registered候選，不宣稱所有自然封套已合格。要擴大正式母體才須決定涵蓋市場、公司／商品類型與排除政策；另驗證raw custody與clock，不能改名成歷史membership|
|官方興櫃 optional source|`data_module/prospective_official_pit_source.py` 登記 `official:tpex:t187ap03_R`／`tpex_emerging`；僅clock universe包含興櫃時容許|本包不開；正式納入興櫃才需要scope／來源接受決策|
|現況狀態與私人清單|`current_market_status_observation.py` 為current_only／PIT_ELIGIBLE=false，缺報價／名錄不推論停牌／下市；`UniverseService` 個人清單的manual／screening／industry來源不是完整資格母體|不能代用歷史可比母體；個人收藏增刪不是入選／退出|

上述是本地現有契約與已登記source候選，沒有新抓取官方名冊或自行接受新授權／市場範圍。最小保守選項不需使用者再定案，UX09可繼續。真正需要決策的是擴大正式母體的產品scope，或另立資料源接受／歷史membership契約；過去current-only快照不能藉這個選擇取得PIT。

## 原標籤的具體選項

目前 `decision_module/stock_screener.py` 原公式不改；四mode immutable publisher的完整Top／Bottom字串已保存，consumer明示非一般「前幾％」或勝率，沒有公開／反推numeric score。

最小選項A：繼續保存原字串與警示，生命週期只讀已有close_above_ma20／60的match／no_match／unknown；rank是獨立排序，沒有已批准的rank入選predicate就不把名次變動當退出。**不阻擋本包**。

選項B：若使用者要更正舊百分比口徑、公開原score、或設rank TopN入選predicate，須先定method version、period/window／母體／門檻與含義，再驗同方法比較；這是新增方法／呈現語意決策。本包不換公式、不把相關名次當機率，也不假設兩條MA等於原強弱方法。

## 安全與驗證邊界

僅唯讀已有 immutable snapshots／已保存官方calendar；不新producer、自然capture／outcome、訓練、正式DB／registry／收藏寫入或排程部署。以current pinned publication觀測時点回放，未來發布／晚到回填／修訂與unknown邊界保留。不得跨unknown／gap／母體／版本比較補出退出／重入。無前景Native／永久刪除／push，未知capture與restore maps未讀未動。


## 最終限定驗收與接手（2026-10-05）

本批建立 UX09 研究名單唯讀比較：兩個既有 MA 規則及 AND／OR 固定查詢，原始排名獨立，不新增 TopN predicate、分數或策略資格。實作只讀 immutable snapshot 與離線日曆；UI 背景核對並呈現入選歷程、前次日期、理由與來源身份。完整 archive 範圍內首次命中可判新入選，不能宣稱自上市首次命中。中間漏觀測、未知、修訂、錯方法／母體／來源身份一律形成比較邊界。

驗證為 78 個不重複受影響測試案例通過：初批 29、追加 guard 4、其餘 consumer／rank／screener 45。最終 reader 11 案重驗通過（包含上述重疊案例，不另加總）；Workbench 85 通過、validator 25 通過／4 略過、mypy 786 檔通過、8 個變更 Python 編譯通過。首次 fixture、舊 enum、原排名欄位假設與日曆正例失敗均保留於限定 QA 收據；沒有全套回歸或訓練。日曆正例實際走 factory→service，禁止 network／SQLite；錯 raw hash、未來 capture、明示缺失 overlay、未完成保存、超預算與取消保持未知或明示取消。日曆 loader 帶 sha256: 的核驗雜湊正規化後綁定；未設定 overlay 沿既有年度預期交易計畫 annual_planned_cache.v1，不授予實際開市或 PIT 證明。

真實 readonly cohort 為 ux16-three-stock-research（1477／2330／2382，排除 2317），decision date 2026-10-05；manifest SHA 2d241068d3b6df9a06c65267da0c0925c30d3244c6116da626d6a537f742311c。cutoff 2026-10-05T23:59:59+08:00，published_at 2026-10-06T00:41:36.077969+08:00；晚發布不能證明決策當時可得，source_available_at 未記錄仍保持未記錄。三列入選歷程皆未知／沒有有效前次比較，不將單日渲染當跨日成熟或 Native 驗收。17 個既有 feature／rank 檔 SHA 與正式 DB/WAL/SHM 的 size／mtime 前後一致；完整分類 JSON round-trip、worker 數 0。offscreen 圖 real_single_date_lifecycle.png 與 real_single_date_lifecycle_list.png 保存在 output/qa/ux09_membership_lifecycle_20261005；圖已檢視，可見摘要與列表歷程欄。

工作起點 708284919f2b0ac994bbf499281a2d36883d9aa4；提交父節點保留其他對話的 4f306f500945ade17afe56a5ea6d250fc2557515。容量／Evidence／Paper 修改屬其他 owner，本批沒有容量驗收、不改 reserve、不重標舊 natural failed run。未知根檔 paper_event_source_capture.py 未讀未動。指定原計畫僅附加本批結果，保留原 158986-byte prefix SHA 7510d7482d123a8c253ee0603e427dc553444aa5d04241f85050ef1fc6514974；output 依 Git 排除規範不提交。

回滾為停用新 lifecycle reader／UI 消費接線或反向本批限定提交，保留既有快照、正式資料與其他 owner commit；不刪資料、不清理分支。不需要新增產品決策才能採用此 bounded MA 研究切片；正式母體擴充、rank TopN predicate 或新分數仍須另定明確方法契約與批准。

完整第一版仍未完成，Backtest 18.62%／20% gate 不變，未啟動 phase 5 capture／outcome 或正式發布。待工程包含長期歷史索引／分頁與成長容量、正式母體與多 consumer 整合、writer crash／部署復原；待驗收包含 Native 取消→重試→保存→新程式重開及錯 date/run/hash、3–5 位使用者體驗。自然跨日證據與原始可得性／PIT 資格另列，不能掩飾上述工程缺口。
