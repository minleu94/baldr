# PROJECT_NAVIGATION 日期化更新記錄（2026-10-05 至 10-07）

> 本文逐位元組保存根目錄 PROJECT_NAVIGATION 原有的更新記錄與日期化補充，只作歷史追溯，不作現行模組邊界、產品狀態或工程優先序依據。現況回到 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)、[DEVELOPMENT_ROADMAP](../00_core/DEVELOPMENT_ROADMAP.md) 與各具名 QA。

## 更新記錄

- 2026-09-06：新增八卡 DTO／服務／儲存與整合交接導航，保持正式資料及 V4 外部 Gate。


## 2026-10-05 原排名研究導航

入口：每日研究條件的日／週及強／弱選項 → 相容不可變原排名 → 研究母體盤勢同源呈現。發布CLI為scripts/publish_original_stock_ranking.py；backend app_module/original_stock_ranking.py；呈現ui_qt/original_ranking_presentation.py。原feature／舊收藏不改，未提供來源未知。[操作](../07_guides/APPLICATION_MANUAL.md)、[QA及限制](../06_qa/UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)。

- 2026-10-05 更新：新增原排名有限工程入口及接受邊界。

## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。 入口：daily_market_research_bookmark.py 的 v2 factory／dispatch、original_stock_ranking.py 的 pinned reader、watchlist_service.py 的同 ledger 儲存、StockReport service／view 與 Main 路由。 [操作](../07_guides/APPLICATION_MANUAL.md)、[限定 QA](../06_qa/UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)。


## 2026-10-05 UX19 有界儲存與發布復原延伸

本批唯讀參照盤點與 dry-run 不提供永久刪除授權；歷史 manifest／artifact／v1-v2 收藏參照保留，未知 schema、缺件、來源不完整及超預算採保守保留。排名首次發布的缺件指標 CAS 與隔離跨程序復原收據、容量時點政策及驗證結果見 [限定收尾收據](../06_qa/UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)。未改原引擎／排名／方法／日期，未重跑既有真實 publisher 或 ML。

真實 MainWindow 九工作區在空資料、隔離配置、offscreen 子程序最小啟動／正常關閉通過（PID 23772，worker 0，guard 無違規）；這不替代帶正式資料的 App 功能、Native 或真人驗收。其他 consumer／完整方法字典／正式母體與排程／其他 writer 生命周期／長期自然成長仍是工程待辦；Backtest18.62%／20%保持未達，來源 availability／PIT／自然資格另列。使用者其他對話的容量／Evidence 變更保留且不納入本批提交，中央政策以時點 pin 為準。


## 2026-10-05 UX09 有界 MA 名單入選歷程

既有兩條 MA 三態快照經純比較模型、有限歷史 reader 與背景 UI 呈現本次新入選／持續符合／重新入選／未再符合，並保存前次日期、理由與可回放來源身份；不是策略升降級服務。無效／缺件／漏日／同日修訂／版本或母體變更及回填保持未知，不在刷新時寫事件。日曆只讀現有快取，publication 前可得性核驗；現有真實來源只有同日，不能作跨日自然歷程證明。

此為原計畫 §8.1／UX09 的研究讀取切片；不更換母體權威或舊標籤、不啟動自然 capture／outcome 階段5，不宣告首版完成。完整方法字典、其他 consumer 融合、正式母體／排程與其他 writer 生命周期仍是工程待辦，Backtest18.62%／20%不變；Native與真人驗收另待桌面時段。詳見 [UX09 限定收據](../06_qa/UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。


## 2026-10-05 UX09 歷史索引／分頁與有限版本復原（最新）

長期保存的研究manifest以可重建SQLite派生索引查詢，32 refs／頁、固定來源／query／generation游標、64頁滑動導航窗口且可持續向更早頁讀取。背景history／explicit rebuild保持當期個股與篩選主線可用；schema／來源／hash／cancel／故障不偽造完整，原immutable來源／舊收藏不遷移。索引最多64MiB，每頁串流重核全index SHA及頁內原manifest/artifact，年度calendar以4096entries／32MiB逐份驗證，不再32份正常累積即整批未知。

限定受影響79個不重複案例、Workbench85、validator25／4skip、mypy788、11變更Python編譯與精度／未來函數guard通過。真實已保存三股來源隔離offscreen回放：晚發布仍unknown、17來源hash與正式DBsize/mtime不變、worker0；沒有讀正式DB去重核current identity。130日×2修訂合成metadata全260refs走9頁，index159744 bytes、最大page JSON13814 bytes／tracemalloc1226583 bytes；不當自然樣本或正式長期總容量證明。

本包關閉UX09索引／分頁／索引程式內版本復原；第一版工程剩餘固定F1–F4，詳細終點與owner見收據。Backtest18.62%／20%仍差1.38百分點，不重測湊數或放寬。舊1477 Native已在6691ec78通過，較早「仍待1477」文字由此更正；新分頁／跨頁Native及3–5位真人另驗。1000×835 outer／125%已接受，不新增1000×800硬門檻。具名full-cohort與原完整Top/Bottom標籤沿現況，官方全市場／新百分位方法只有擴充時才要明確決定，不阻塞目前研究限定工程。

完整操作與排錯見 APPLICATION_MANUAL 的歷史索引小節；[詳細驗證、來源選項與F1–F4凍結清單](../06_qa/UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。

程式入口：`app_module/research_membership_history_index.py`、`research_membership_history_view.py`；CLI：`scripts/manage_membership_history_index.py`；測試：`test_research_membership_history_index.py`、`test_ux09_history_recovery_consumers.py`、`test_ux09_history_browse_view.py`、`test_membership_history_cli.py`。


- 2026-10-05：[F2／F3 原市場共享來源及已開能力矩陣](../06_qa/F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)，A／A 限定完成；F1／F4 與新 Native／真人另列。


- 2026-10-05：[F4跨頁整合與資源終驗](../06_qa/F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)：actual三程序雙收藏讀回通過；20-session實測有效，120/250長保留因二次payload超現有預算blocked，F4未全關閉；F1／新Native／真人另列。

- 2026-10-05：[F4項目revision儲存與20／120／250實測](../06_qa/F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md)：新v3長留存與actual App通過，原預算不變；正式舊SQLite COW converter與切換仍待工程／核准。

- 2026-10-05：[F4 SQLite COW converter／明示activation終驗](../06_qa/F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md)：隔離工程完成；20→21→rollback20保留雙庫與target新歷史。正式store/mode與使用者apply批准另列，不讀真實JSON、不初始化缺失DB。


- 2026-10-05：[F4 Legacy JSON COW／原升級入口終驗](../06_qa/F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md)：單JSON至獨立v3、新程序讀回及rollback保留新內容；正式apply另行批准，F1例外尚未批准，UX07未啟動。


- 2026-10-06：[個人觀察清單整合](../06_qa/PERSONAL_STORAGE_SEPARATION_LANE_20261005.md)：`app_module/personal_watchlist_service.py` 選擇服務，`personal_data_paths.py` 私人控制路徑與 CSV export manifest，config／App／CLI／候選池明示啟用；正式遷移未執行。


- 2026-10-06：[UX10 MA研究方法符合度](../06_qa/UX10_MULTI_METHOD_LANE_20261006.md)：`app_module/multi_method_research_consensus.py` 純readmodel／pinned adapter；每日研究名單沿同accepted快照呈現方法與家族counts，不增加排序分數或新方法。


- 2026-10-06：[Journal 個人路徑及 UI composition](../06_qa/PERSONAL_JOURNAL_LANE_20261006.md)：`personal_journal_paths.py` 明示 selector／JSONL adapter；config → Main writer/controller、Workbench continuity、推薦 Personalization 與 outcome journey。模式獨立 watchlist，未設定仍保留相容 writer；正式位置／migration 未批准。


2026-10-06：回測策略設定新增按需版本化規則說明（ui_qt/widgets/strategy_rule_card_dialog.py），唯讀目前Spec，不連既有run；操作及限制見docs/07_guides/APPLICATION_MANUAL.md，UX11仍partial。


2026-10-06：研究Registry新增單筆保存結果／規則来源核對，app_module/saved_strategy_rule_card.py＋既有RunRegistryCompareWidget；QA見docs/06_qa/UX11_SAVED_RESULT_RULE_READBACK_20261006.md。

### 2026-10-06 UX20 單批 MA 樣本限定整合

既有隔離 MA CLI 明示保存完整 matched/notmatched/unknown/excluded 單批capture＋receipt，再按原pin唯讀核對readiness；既有MA頁只呈現當期完整控制組投影並明示尚未保存。included≤16、超限拒絕；未知availability/calendar/outcomes不補PIT或訓練資格。Stage5／UX20 partial，多批parent／排程與Outcome接線仍是工程待辦。QA：`docs/06_qa/UX20_SAMPLE_CAPTURE_INTEGRATION_20261006.md`；操作以Manual同日章節為準。個人儲存／Journal程式已整合，只有正式migration／activation未做。


### 2026-10-06 UX20 多批母體有限整合

具名parent manifest已沿既有query-only source／producer／capture／readiness完成多批保存、新程序讀回、取消／失敗／安全重試；每批included≤16，完整母體最多16批，缺批與途中來源／方法改變不能complete。producer發布狀態與sample捕捉狀態分開，uncaptured另列。UI未改；Stage5／UX20仍partial，固定時鐘／排程留存、Outcome H5/10/20與母體UI瀏覽仍待工程；官方available-at／日曆及自然成熟另待證據。操作依APPLICATION_MANUAL最新多批章；收據：docs/06_qa/UX20_PARENT_CAPTURE_INTEGRATION_20261006.md。


### 2026-10-06 UX20 保存母體收據瀏覽

每日研究條件新增明示選取parent receipt的背景唯讀視窗，沿原writer/readiness核對；首屏列母體／資料日／方法、完整／uncaptured與每批producer/capture結果，技術身份折疊。重複點擊／取消／返回／stale回應不重跑producer或套舊資料；readiness拒絕時保留已驗envelope的發布記錄，母體資格未確認。15 offscreen測試、Workbench85、validator25/4skip、mypy806+final targeted2通過。Stage5／UX20保持partial；固定觀測日policy、漏日／修訂接受與owner容量部署仍待工程，UX21獨立lane未接受。QA：docs/06_qa/UX20_PARENT_RECEIPT_UI_20261006.md；操作依Manual最新章。


### 2026-10-06 UX20 固定觀測日接受限定完成

既有parent receipt→原readiness→child exact資料日→固定cutoff/窗口/expected dates接受policy→共用atomic writer→新程序唯讀日報已接線；隔離CLI預設preview，--accept明示保存。缺目標資料日不能借latest或前日補完整，同日不同revision保舊、相同policy/parent冪等、failure/partial安全重試。23不同案例、targeted mypy2/compile3/quant/diffcheck通過；UI未改不重跑前批gates。Stage5／UX20仍partial；正式daily owner/Task/cadence監控／容量留存部署與官方來源治理仍待工程/決策，UX21三檔獨占未接受。操作依Manual最新章與Supplements，QA：docs/06_qa/UX20_OBSERVATION_DAY_ACCEPTANCE_20261006.md。


### 2026-10-06 UX20 隔離daily owner可執行整合

新增明示runtime/target日期的isolated daily runner，直接沿既有producer/parent/observation接受串全鏈，preflight為預設；capacity/quota先檢，有限retry/合作cancel/漏日與revision監控，exact receipt重用。source/日期/配置一致才完成，producer已發布與capture拒絕分列保留；未配置不選生產值。17不同案例＋最後source/config兩例重核、targeted mypy2/compile3/quant通過；UI未改。Stage5/UX20仍partial，正式date-owner/calendar/Task/ACL/留存治理待工程/決策；UX21三檔未整合。QA：docs/06_qa/UX20_DAILY_OWNER_ISOLATED_20261006.md；操作依Manual。


### 保存母體 H5／H10／H20 研究結果（2026-10-06）

- 純DTO／Decimal契約：`app_module/rule_research_forward_outcome.py`。
- exact receipt＋明示JSON有界唯讀consumer：`app_module/rule_research_forward_outcome_reader.py`。
- 原每日研究母體視窗與TaskWorker：`ui_qt/rule_research_parent_receipt_dialog.py`。
- 邊界／新程序／取消與UI：`tests/test_rule_research_forward_outcome_reader.py`、`tests/test_ui_qt_forward_outcome_receipt.py`；[QA](../06_qa/UX21_FORWARD_OUTCOME_20261006.md)／[Manual](../07_guides/APPLICATION_MANUAL.md)。不作交易或ML target，原資料不寫。


### UX21 endpoint label→UX22 readiness（2026-10-06）

- 封存來源薄consumer：`app_module/rule_research_label_readiness.py`；重用HistoricalLabelSpec/Row，明示policy與固定時間窗，不fit。
- 可測試唯讀入口：`scripts/run_rule_research_label_readiness.py`，repeat exact parent/outcome receipts，輸出有界來源/hash/分母/缺件JSON。
- `tests/test_rule_research_label_readiness.py`／`tests/test_rule_research_label_readiness_cli.py`；[QA](../06_qa/UX22_LABEL_READINESS_20261006.md)／[Manual](../07_guides/APPLICATION_MANUAL.md)。既有learner／same-sample比較器缺完整特徵與prediction inputs時blocked；不造PIT/模型/Task。


### UX22 同源公平比較（2026-10-06）

- `app_module/rule_research_fair_comparison.py`：明示target／來源契約、CORE20 feature與整數shadow DTO共同樣本比較。
- `scripts/run_rule_research_fair_comparison.py`：預設白話摘要，--json保存有界研究收據；不fit或寫registry。
- focused／CLI／ML boundary tests與[QA](../06_qa/UX22_FAIR_COMPARISON_20261006.md)；[Manual](../07_guides/APPLICATION_MANUAL.md)列政策、分母／缺件及排錯。UX22保持partial。


### UX23 隔離 shadow 工程驗收（2026-10-06）

入口 `scripts/run_rule_research_shadow_acceptance.py`；consumer `app_module/rule_research_shadow_acceptance.py`；操作依 [Manual](../07_guides/APPLICATION_MANUAL.md)，工程／資料效果／未啟用三軸及未完項依 [UX23 QA](../06_qa/UX23_SHADOW_ACCEPTANCE_20261006.md)。不連 registry、不啟用正式行為。


### 2026-10-06 UX08 推薦保存圖表

推薦執行→同次frame capture→immutable execution→exact保存來源研究圖／精確表；helper為`app_module/recommendation_saved_chart.py`，接線service／execute／report read service，既有Qt consumer。使用流程見完整Manual，[範圍／測試／下一包接線](../06_qa/UX08_RECOMMENDATION_SAVED_CHART_20261006.md)。UX08整項仍partial，viewport／CSV lane待父層安排。


### 2026-10-06 UX08 viewport產品按鈕

app_module/chart_viewport_state.py接StockResearchReportView價格頁按鈕；範圍控制只切原DTO，原生paint/hover日期槽一致，精確表全量。流程見Manual，[scope／失敗基線／限制](../06_qa/UX08_VIEWPORT_INTEGRATION_20261006.md)。


### 2026-10-06 明示市場CSV CLI

scripts/export_market_csv.py提供唯讀preview、caller保存接受的preview後明示execute；app_module/market_csv_export.py只consumer，no Task/上傳/分享/根目錄啟用。Windows handles／來源與exact receipt核驗，實際流程看Manual，[synthetic範圍](../06_qa/MARKET_CSV_EXPORT_INTEGRATION_20261006.md)。


### 2026-10-07 完整保存母體瀏覽（dev）

查每日研究完整來源 UI：ui_qt/views/daily_market_universe_view.py；完整 query／原 child 解析：app_module/daily_market_universe_selection.py；個股發出／返回／取消續接：ui_qt/views/daily_market_research_view.py。底層仍沿既有 daily_market_universe_run 與 parent repository。操作見[完整手冊](../07_guides/APPLICATION_MANUAL.md#2026-10-07-施工版完整保存母體瀏覽)，限制與88項UI回歸見[M2 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md)。尚未代表新五規則full-N產製／收藏／比較或候選可用。


v4技術保存底層：app_module/daily_market_technical_snapshot_v4_repository.py（exact manifest唯讀）、daily_market_technical_snapshot_v4_producer.py（finish窗口保存批次）、rule_research_technical_parent_capture_v4.py（immutable plan／append-only parent進度及明示續跑）。與舊v2／v3保存隔離，最多256納入是child parent邊界；full-N orchestration及UI尚未完成。中央92 passed／1權限skip及契約見[M2 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md)。


v4正常bounded產製入口：app_module/daily_market_technical_parent_v4_producer.py／produce_daily_market_technical_parent_v4；單一finish後真保存／明示receipt續跑與每批source pin重驗，caller中央20案例通過。full-N aggregate及正常UI另在施工，操作入口尚未開放，不用舊候選驗新caller。


H20原保存來源獨立摘要（dev）：ui_qt/main.py的_context_changed/read/recheck/refresh cohort routes，ui_qt/views/stock_research_workspace.py首屏卡；公開product reader仍在app_module/recommendation/personal_h20_product_evidence.py未改。完整來源／失敗仍顯示／stale／retry／pointer漂移測試：tests/test_ui_qt_h20_saved_source_journey.py，UI panel測試：tests/test_ui_qt_personal_h20_workspace_panel.py。中央96案例與Native限制沿[M2 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md)。


2026-10-07 v4固定來源查詢：`app_module/daily_market_technical_parent_v4_query.py`／`tests/test_daily_market_technical_parent_v4_query.py` 提供canonical固定query、真parent／child讀回、五規則狀態與Decimal排序／分頁、逐批取消。單段上限256納入＋256排除，full-N另由新store／producer／aggregate query補完；中央8例與targeted mypy通過，不能由此宣稱完整選股器完成。


2026-10-07 v4讀回修正：`daily_market_technical_feature_snapshot_v4.py`／`daily_market_technical_snapshot_v4_repository.py`／`rule_research_technical_parent_capture_v4.py`移除同一read內重複語義核驗，保留每次真檔pin與變動核驗；零child公開parent讀回可用。六套中央67 passed／1 Windows symlink權限skip，full-N各leaf及正常UI閉環仍待整合。

五規則完整母體：app_module/daily_market_technical_universe_v4_query.py（全域保存查詢）、daily_market_technical_universe_v4_stock.py（原頁個股）、daily_market_technical_universe_v4_comparison.py（原query各欄比較）、daily_market_technical_universe_v4_bookmark.py（固定收藏與typed重開）；持久化沿app_module/watchlist_service.py原JSON／COW caller，工程限制見docs/06_qa/BALDR_COMPLETION_M2_20261007.md。
