# 產品與個股研究 QA 索引

> [回 QA 證據導覽](README.md)。本索引只供導覽。每份收據仍須按自身日期、範圍與限制判讀；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。索引不代表 Gate 通過，也不改變 QA 原件的生命週期。

## 個股研究與產品 UX

| 主題 | 建議閱讀順序 | 範圍提示 |
|---|---|---|
| H20 個股研究 | [H20 gross model 契約](BALDR_A02_H20_GROSS_MODEL_20261006.md) → [研究 cohort](BALDR_H20_RESEARCH_COHORT_20261007.md) → [目前候選](BALDR_H20_CURRENT_CANDIDATE_93F9C57D_20261008.md) → [操作讀回](H20_READ_OPERATION_SESSION_20261007.md) → [圖表契約](H20_BOUND_CHART_CONTRACT_REVIEW_20261008.md) → [O attempt02 root follow-up](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md) | O attempt02 在設定讀取前置 guard 失敗；檔案與 SQLite 真讀均未發生，source-port 未通過。模型研究、目前來源、保存與圖表是不同驗收面；不能互推 ML 正式資格。 |
| UX02–UX24 研究工作台 | [UX08 viewport 整合 QA](UX08_VIEWPORT_INTEGRATION_20261006.md) → [UX08 純 controller handoff 歷史](../09_archive/README.md#2026-10-09-qa-historical-snapshots-scheduler-health-and-ux08-controller) → [UX16 來源契約](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md) → [UX24 首版工程封存（bounded）](../09_archive/UX24_FIRST_VERSION_ENGINEERING_SEAL_20261006.md) → [UX21 Forward Outcome](UX21_FORWARD_OUTCOME_20261006.md) → [UX09 歷史索引](UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md) | UX24 僅關閉其七項有限工程終點，整體 UX／正式啟用／Native 真人／自然成熟仍待各自驗收；目前 UX08 也仍有 Native／真人與其他明列驗收未完成，單張 UX 收據只覆蓋其標示的卡與階段。 |
| BALDR 產品補完 | [10/09 恢復開發基線](BALDR_COMPLETION_RESUME_20261009.md) → [原暫停交接](BALDR_COMPLETION_HANDOFF_20261009.md) → [補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md) → [First wave](BALDR_COMPLETION_FIRST_WAVE_20261006.md) → [B01–B14 收據](#baldr-b01b14) → [10/08 排程修復](BALDR_SCHEDULE_REPAIR_20261008.md) | 恢復 QA 保留首輪失敗與未驗證界線，不是產品完成或發布收據；lane 工程接線不代表全母體、自然累積或正式資格完成。First Wave QA 引用的兩張 Python／exe 截圖在 ignored 的本機 `output/qa/`，乾淨 checkout 不包含圖片。 |
| BALDR M2／H20 深化 | [M2 完整工程收據](BALDR_COMPLETION_M2_20261007.md) → [中央 cohort／Natural／BB UI 整合](BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md) → [推薦真人回饋](BALDR_RECOMMENDATION_HUMAN_FEEDBACK_20261007.md) | M2、自然樣本與真人／Native 驗收各有獨立限制；以缺口表及原收據判讀，不把局部工程結果視為產品結案。 |
| 來源資料日期呈現（P10） | [來源資料日呈現核驗](RESEARCH_SOURCE_DATE_PRESENTATION_20261008.md) | 只驗證明示日期的呈現與截止型別處理；不授予來源新鮮度、歷史 PIT 或交易資格。 |
| 技術完整母體保存來源 Main 旅程 | [正常 Main 旅程收據](TECHNICAL_READ_ROOT_MAIN_JOURNEY_20261007.md) | 合成 257 納入／1 排除來源上的 bounded MainWindow 查詢、保存與讀回；不代表真實市場資料、Native 或全產品接受。 |
| 個人研究筆記與儲存隔離 | [Personal Storage Separation](PERSONAL_STORAGE_SEPARATION_LANE_20261005.md) → [Personal Journal](PERSONAL_JOURNAL_LANE_20261006.md) | 正式儲存遷移、啟用與跨頁 readback 仍有未結 Gate；兩份收據範圍不同，請分別核對。 |
| UX20–UX23 固定觀測日與 ML Readiness | [UX20 觀測日接受政策](UX20_OBSERVATION_DAY_ACCEPTANCE_20261006.md) → [UX20 Daily Owner](UX20_DAILY_OWNER_ISOLATED_20261006.md) → [UX21 Benchmark source store](UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md) → [UX22 同源公平比較](UX22_FAIR_COMPARISON_20261006.md) → [UX23 Registry read-only consumer](UX23_REGISTRY_INTEGRATION_20261006.md) | 這些收據記錄 bounded 隔離流程與來源限制；UX20／UX21／UX22／UX23 各自的 Stage、部署與模型資格不得互相推定。 |

## 近期與跨主題收據

| 要查的內容 | 證據入口 |
|---|---|
| 四用途 UX 結果、近期工程增量 | [B03 Update／Runtime](BALDR_B03_UPDATE_RUNTIME_20261006.md)、[B04 收藏](BALDR_B04_SELECTION_WATCHLIST_20261006.md)、[B05 圖表](BALDR_B05_CHART_INCREMENT_20261006.md)、[B06 投資組合摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、[B10 私人覆盤](BALDR_B10_PRIVATE_REVIEW_20261006.md)、[B12 隔離 runtime](BALDR_B12_DAILY_RUNTIME_20261006.md) |
| 個股研究的其他讀回 | [報告與 ML 分流](H20_REPORT_ML_SEPARATION_COPY_20261008.md)、[目前來源診斷](H20_SAVED_AND_CURRENT_SOURCE_DIAGNOSIS_20261008.md)、[獨立 current research](H20_INDEPENDENT_CURRENT_RESEARCH_20261008.md)、[載入 candidate](BALDR_H20_LOADING_CANDIDATE_421BC973_20261008.md) |
| BALDR／H20／UX 分支與 bounded 收據 | [36 份原件的分組導覽](BALDR_UX_EVIDENCE_GUIDE_20261009.md) | 依模型／自然結果、候選與發布、Registry／復原、圖表、研究工作台、capture 分組；逐份狀態仍以原件與較新 QA 判讀。 |

<a id="baldr-b01b14"></a>
### BALDR B01–B14

依產品補完缺口表選擇對應收據：B01 [歷史標籤邊界](BALDR_B01_HISTORICAL_LABEL_BOUNDARY_20261006.md)、B02 Windows COW 見 [closeout status 表](BALDR_CLOSEOUT_STATUS_20261006.md)、B03 [市場首頁](BALDR_B03_MARKET_HOME_20261006.md)／[Update runtime](BALDR_B03_UPDATE_RUNTIME_20261006.md)、B04 [選擇與收藏](BALDR_B04_SELECTION_WATCHLIST_20261006.md)、B05 [圖表](BALDR_B05_CHART_INCREMENT_20261006.md)、B06 [投資組合摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、B07 [規則歷史](BALDR_B07_RULE_HISTORY_20261006.md)、B08 [個人路由](BALDR_B08_PERSONAL_ROUTES_20261006.md)、B09 [個人投資組合](BALDR_B09_PERSONAL_PORTFOLIO_20261006.md)、B10 [私人覆盤](BALDR_B10_PRIVATE_REVIEW_20261006.md)、B11 [模型家族目錄](BALDR_B11_FAMILY_CATALOG_20261006.md)、B12 [每日 runtime](BALDR_B12_DAILY_RUNTIME_20261006.md)、B13 [模型輸入](BALDR_B13_MODEL_INPUT_20261006.md)、B14 [Shadow evidence](BALDR_B14_SHADOW_EVIDENCE_COMPOSITION_20261006.md)。

### 2026-10-06 至 10-09 收據直達索引

以下提供近期產品、研究與 UX 收據／計畫的直達入口。文件仍保留各自的範圍與時點；此索引不把它們合併成新的現況、完成度或待辦判定。

- **H20 研究來源與讀回**：[固定來源建置](BALDR_H20_FIXED_SOURCE_BUILD_REVIEW_20261009.md)、[來源清單環境橋接審查](BALDR_H20_SOURCE_MAP_SEAM_REVIEW_20261009.md)、[verifier 模組相容性 root review](BALDR_H20_VERIFIER_MODULE_COMPATIBILITY_ROOT_REVIEW_20261009.md)、[MA 固定合成旅程 root review](BALDR_MA_V9_CHILD_IDENTITY_ROOT_REVIEW_20261009.md)、[設定入口 L root review](BALDR_H20_L_CONFIG_SOURCEPORT_ROOT_REVIEW_20261009.md)、[WAL keeper root review](BALDR_H20_WAL_KEEPER_ROOT_REVIEW_20261009.md)、[Runtime root 契約](BALDR_H20_RUNTIME_ROOT_CONTRACT_REVIEW_20261008.md)、[Snapshot builder](BALDR_H20_SNAPSHOT_BUILDER_REVIEW_20261008.md)、[WAL snapshot](BALDR_H20_WAL_SNAPSHOT_REVIEW_20261008.md)、[版面 teardown 與窄控制](BALDR_LAYOUT_TEARDOWN_AND_NARROW_CONTROLS_20261008.md)、[Bookmark controls](H20_BOOKMARK_CONTROLS_20261007.md)、[Bookmark core](H20_BOOKMARK_CORE_20261007.md)、[凍結來源 root 修復](H20_FROZEN_SOURCE_ROOT_REPAIR_20261007.md)。另見 [M7 原來源 S4 Main bounded 旅程](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)：旅程及 120 筆 OHLC／684 bp 對照通過，來源 unchanged；不代表新 EXE、真人驗收或正式 PIT／收益資格。MA 收據仍依各自來源與範圍判讀。
- **推薦介面與個人工作區**：[推薦理由完整保存審核](BALDR_COMPLETE_REASONS_REVIEW_20261008.md)、[推薦鍵盤捲動](BALDR_RECOMMENDATION_KEYBOARD_SCROLL_20261008.md)、[推薦詳情目前捲動審查](BALDR_RECOMMENDATION_SCROLL_CURRENT_REVIEW_20261009.md)、[個人 Watchlist thread serialization](PERSONAL_WATCHLIST_THREAD_SERIALIZATION_20261007.md)、[推薦閱讀版面](RECOMMENDATION_READING_LAYOUT_20261007.md)。捲動審查使用合成資料與 offscreen 畫面，不是原始股票或真人接受；新版 EXE 與真人操作驗收仍待完成，H20 下鑽另有獨立關卡。
- **產品補完與發布**：[F17 正常 capture pair review](BALDR_F17_NORMAL_CAPTURE_PAIR_REVIEW_20261009.md)、[正常技術／官方來源聯合產製 UI review](BALDR_F17_NORMAL_PRODUCTION_UI_REVIEW_20261009.md)、[官方當下處置來源 leaf](SELECTION_OFFICIAL_DISPOSAL_SOURCE_20261007.md)、[平行工作交接](BALDR_PARALLEL_NEXT_WORK_20261009.md)、[portable configured bootstrap](BALDR_PORTABLE_CONFIGURED_BOOTSTRAP_20261006.md)、[portable Windows](BALDR_PORTABLE_WINDOWS_20261006.md)、[F07 固定候選](F07_FIXED_CANDIDATE_F2FBA4C7_20261008.md)、[F17 single graph integration](F17_SINGLE_GRAPH_INTEGRATION_20261008.md)。該 leaf 的 `available_at` 未知、`current_only`、`historical_pit_eligible=false`；F17 UI review 的正常來源增量已驗，但完整 Main 下鑽、全母體效能、跨程序聯合收藏與 EXE 接受仍未完成，不代表 PIT acceptance 或 F17 結案。
- **日期語義、篩選與 Universe**：[決策 Snapshot 日期語義](DECISION_SNAPSHOT_DATE_SEMANTICS_20261006.md)、[P01 篩選 Profile diagnostics](P01_FILTER_PROFILE_DIAGNOSTIC_CONTRACT_20261008.md)、[同次 Session metadata 效能候選](BALDR_P01_SESSION_METADATA_PERFORMANCE_CANDIDATE_20261009.md)、[路徑渲染候選 root review](BALDR_P01_PATH_RENDER_DESIGN_ROOT_REVIEW_20261009.md)、[1,000 檔效能失敗與下一 Gate](BALDR_1000_STOCK_PERFORMANCE_NEXT_GATE_20261009.md)、[單次頁面路徑 tuple memo](BALDR_P01_COMPONENT_TUPLE_MEMO_20261009.md)、[單頁路徑渲染 memo](BALDR_P01_PAGE_PATH_RENDER_MEMO_20261009.md)、[render-prefill 初版候選紀錄](BALDR_P01_RENDER_PREFILL_20261009.md)、[render-prefill root review](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)、[已簽發來源 DTO 重建](BALDR_P01_PROOF_GATED_REHYDRATION_20261009.md)、[技術規則視窗重用](TECHNICAL_RULE_WINDOW_REUSE_20261007.md)、[技術 Universe query stream](TECHNICAL_UNIVERSE_QUERY_STREAM_20261007.md)、[技術 Universe read root](TECHNICAL_UNIVERSE_READ_ROOT_20261007.md)。固定 85bc 六角色矩陣暖操作 p95 為翻頁 196.205 ms、排序 191.8186 ms、篩選 523.902 ms；篩選仍超過 300 ms。冷啟動至首頁 p95 為 20.0319 秒。這是隔離診斷矩陣，不是一般產品旅程驗收。

### F02／F03／F06／F12 功能驗收鏈（2026-10-10）

先看[產品補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md)與[平行工作 root review](BALDR_PARALLEL_ROOT_REVIEW_20261009.md)掌握跨功能阻礙，再按下列收據追查各自範圍。這些是 bounded 工程證據，不等於完整 UI、EXE 或真人驗收，也不代表相關 Gate 已通過。

- **F12 月營收**：[來源審查](BALDR_F12_MONTHLY_REVENUE_SOURCE_REVIEW_20261009.md) → [index 整合複核](BALDR_F12_INDEX_INTEGRATION_REVIEW_20261009.md) → [全母體 query reader 驗收](F12_MONTHLY_REVENUE_QUERY_READER_20261009.md) → [saved-recipe root review](BALDR_F12_SAVED_RECIPE_ROOT_REVIEW_20261009.md) → [WAL exact reopen](BALDR_F12_WAL_EXACT_REOPEN_ROOT_REVIEW_20261009.md) → [durable raw archive v2](BALDR_F12_DURABLE_RAW_ARCHIVE_V2_20261009.md) → [archived finish root review](BALDR_F12_ARCHIVED_FINISH_ROOT_REVIEW_20261009.md) → [Main integration review](BALDR_F12_MAIN_INTEGRATION_REVIEW_20261009.md) → [D focused／Main root follow-up](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。頁碼按鈕修補與 4 項按鈕回歸通過；最新 T10 focused 12 項通過，但完整 Main 仍在明示 Watchlist COW 啟用逾時，來源維持唯讀。Reader 的 current-only／未知來源時間界線保留，完整新程序收藏讀回、EXE 與真人驗收仍待完成。
- **F02 均線條件**：[四均線來源缺口與子模組根審（10/08）](F02_SAVED_FEATURE_GAP_20261008.md) → [fdopen guard 診斷](BALDR_F02_FDOPEN_GUARD_DIAGNOSIS_20261009.md) → [V4 oracle／supervisor review](BALDR_F02_V4_ORACLE_SUPERVISOR_REVIEW_20261009.md) → [M guard root review](BALDR_F02_M_GUARD_ROOT_REVIEW_20261009.md)。10/08 報告確認保存特徵缺口並記錄單一子模組驗證，不代表產品接線或驗收。完整 257 檔矩陣、正常來源、新 EXE、真人驗收與 MA20 上彎契約仍未完成；局部 guard／oracle 結果不可當成產品通過。
- **F03 KDJ 條件**：[full-population 整合計畫](BALDR_F03_FULL_POPULATION_INTEGRATION_PLAN_20261009.md) → [KDJ query contract](BALDR_F03_KDJ_QUERY_CONTRACT_20261009.md) → [MA／KDJ／Volatility group v2](BALDR_F03_MA_KDJ_VOLATILITY_GROUP_V2_20261009.md) → [多 parent 共同發行邊界計畫](BALDR_F03_MULTI_PARENT_GROUP_PUBLICATION_PLAN_20261009.md) → [multi-parent callback review](BALDR_F03_MULTI_PARENT_CALLBACK_REVIEW_20261009.md) → [prepare root follow-up](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。截至已提交 commit `8945df89`，formal reader／group-session bounded publication slice 有 17 個節點取得通過證據（首輪 15 passed；僅重跑兩個 QA-overlay 修正節點）；固定 258/257/1 來源的窄窗 View G8 與收藏 identity C 亦各有 bounded 通過證據。這些不等於全域 query、正常 Main 或新程序收藏閉環驗收；本索引不納入後續未提交 QA 追加。
- **F06 波動條件**：[來源證據與方法缺口計畫](BALDR_F06_VOLATILITY_EVIDENCE_PLAN_20261009.md) → [composite query contract](BALDR_F06_COMPOSITE_VOLATILITY_QUERY_CONTRACT_20261009.md) → [Decimal 方法提案](BALDR_F06_DECIMAL_VOLATILITY_METHOD_PROPOSAL_20261009.md) → [collector contract](BALDR_F06_VOLATILITY_COLLECTOR_CONTRACT_20261009.md) → [presenter bounded integration evidence](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。`8945df89` 提交 presenter 與 reader-issued observed／unknown 測試，2 項 focused tests 及記錄的強制檢查通過；目前無正式 UI 呼叫端、無 full-N reader-issued 結果，方法提案仍不是已採納產品規則。

### 2026-10-10 待真人實測

- **複合研究與收藏重開**：[真人驗收步驟](BALDR_COMPOSITE_HUMAN_CHECK_20261010.md)。原碼自動化旅程已通過，但真人結果尚未取得；此收據不代表完整 UI、EXE 或投資驗收。
- **BALDR／P08 有界工程收據**：[產品補完狀態快照](BALDR_PRODUCT_COMPLETION_STATUS_20261010.md)、[P08 價格證據切片](BALDR_P08_PRICE_EVIDENCE_SLICE_20261010.md)、[P08 現金種子切片](BALDR_P08_CASH_SEED_SLICE_20261010.md)。這些是 10/10 的狀態與有限工程證據，不代表 P08 或整體產品補完完成。

## 其他常用路徑

- **投資組合與 Paper**：[三帳摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、[個人 Paper producers](BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md)、[個人 Paper ledgers](BALDR_PERSONAL_PAPER_LEDGERS_20261006.md)。
- **Watchlist 儲存與 COW 遷移（F4，2026-10-05）**：[revision retention](F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md) → [SQLite COW](F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md) → [Legacy JSON COW](F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md) → [整合／容量驗收](F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)。這組隔離工程收據與正式資料 apply／activation 分開判讀，也不同於後續 B02 個人儲存工作包。
- **技術分析與圖表**：[BBANDS 上軌入口](BALDR_A01_BBANDS_UPPER_20261006.md)、[每日 BBANDS](BALDR_DAILY_BBANDS_CENTRAL_20261007.md)、[H20 圖表契約](H20_BOUND_CHART_CONTRACT_REVIEW_20261008.md)。
- **早期產品 QA（歷史）**：推薦分析與數據更新 Tab 的四份舊問題盤點／QA 摘要已移至[歷史封存入口](../09_archive/README.md#2026-10-08-early-recommendation-and-update-tab-qa)。原路徑保留短導引；其中的路徑、測試數字與待辦不代表目前實作或驗收結果。現行操作與排錯以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準，測試範圍看 [Feature-to-test routing matrix](FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md)。
- **Workbench 歷史 UI closeout**：[左側主導覽 IA（2026-07-07）](../09_archive/WORKBENCH_LEFT_NAVIGATION_IA_CLOSEOUT_2026_07_07_HISTORY.md)、[視覺層級 polish（2026-07-07）](../09_archive/WORKBENCH_VISUAL_HIERARCHY_POLISH_CLOSEOUT_2026_07_07_HISTORY.md)：保留當時 UI 與測試證據，不作目前狀態依據；現行操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。
- **Readability polish closeout（2026-07-07，歷史）**：[Archive 原文](../09_archive/README.md#2026-07-broker-flow-and-ui-closeout)；當時 formal-data waits 是該次快照，現況看 Snapshot／Manual。
- **Workbench 低流動性提示分流 QA（2026-09-21，歷史）**：[封存收據](../09_archive/WORKBENCH_LIQUIDITY_REVIEW_ROUTING_QA_2026_09_21_HISTORY.md)保留當日 read-only snapshot／UI route 與 `1121` liquidity、`10` weakness 的 bounded 結果；後續整合路由見[封存的 V5 readability acceptance](../09_archive/V5_READABILITY_ACCEPTANCE_2026_09_21.md)，目前操作仍以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準。該收據不驗證 liquidity 資料品質或正式來源 Gate；本批封存來源 bytes／SHA 見 [Coverage History Entry 149](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-149)，低流動性收據原件見 [Entry 125](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-125)。
- **Position Health／Paper thesis 工程盤點（V4，2026-09-08）**：[source-to-caller gap map](V4_POSITION_HEALTH_SOURCE_CALLER_GAP_MAP_2026_09_08.md) → [transition evaluator contract](V4_POSITION_HEALTH_TRANSITION_EVALUATOR_CONTRACT_2026_09_08.md)。兩份原件記錄當時輸入盤點與 proposal-only caller 範圍，不代表目前 Gate 6 readiness 或投資有效性；現況看 Snapshot 與近期 QA。
- **UI geometry audit（2026-09-29，歷史）**：[封存收據](../09_archive/UI_LAYOUT_AUDIT_20260929.md)記錄六格 offscreen viewport 矩陣及合成 UI 覆蓋；這不證明 Windows 原生視窗行為，也未證實先前 native access violation 的根因或永久修復。原路徑保留相容導引，來源與替代入口見 [Coverage History Entry 151](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-151)。

## 補充收據索引（2026-10-10 治理補登共 85 份）

> 本區收錄經 2026-10-10 全量盤點查核之專屬 QA 驗收證據；各原件維持各自日期與範圍，不推升為目前全域狀態。

- [A03 個人模型每日保存與自然結果](BALDR_A03_PERSONAL_MODEL_DAILY_20261006.md)
- [BALDR B10 Notes Backup / Restore Adapter QA](BALDR_B10_NOTES_BACKUP_20261006.md)
- [B14 獨立 shadow control port 工程收據](BALDR_B14_SHADOW_CONTROL_20261006.md)
- [BBUI01 有限 BB 上軌第三條件 UI（2026-10-07）](BALDR_BBANDS_RESEARCH_UI_20261007.md)
- [c611 固定候選：建置及同版驗證](BALDR_C611_CANDIDATE_20261007.md)
- [固定 acd18a1e 候選與接受範圍](BALDR_CANDIDATE_ACD18A1E_20261008.md)
- [個人 Current-observed H20 每日入口：受驗保存與自然接線](BALDR_CURRENT_OBSERVED_H20_DAILY_20261006.md)
- [dev／main 兩用途整理與可恢復發布準備](BALDR_DEV_MAIN_RELEASE_PREPARATION_20261007.md)
- [Baldr 收尾差異：已授工程與未決事項（2026-10-06）](BALDR_ENGINEERING_DECISION_DELTA_20261006.md)
- [F03 KDJ 方法契約與缺口盤點](BALDR_F03_KDJ_CONTRACT_REVIEW_20261008.md)
- [Baldr 已授範圍最終穩定窗收據（2026-10-06）](BALDR_FINAL_AUTHORIZED_UNION_20261006.md)
- [原保存 2382：一次實際旅程計時方案（尚未執行）](BALDR_H20_2382_TIMING_PLAN_20261010.md)
- [H20N01 完整 cohort 自然結果 caller](BALDR_H20_NATURAL_BATCH_20261007.md)
- [本機 main 使用版 packaging 驗收](BALDR_LOCAL_MAIN_PACKAGING_20261007.md)
- [四均線正常來源入口：局部驗證與待完成項目](BALDR_MA_NORMAL_OPENER_REVIEW_20261008.md)
- [Baldr 下一波精確 ownership 派工收據（2026-10-06）](BALDR_NEXT_OWNERSHIP_DISPATCH_20261006.md)
- [下一次Task唯讀驗收與原24UX已知工程差異（2026-10-07）](BALDR_NEXT_RUN_AND_REMAINING_ENGINEERING_20261007.md)
- [P08 策略帳戶綁定切片（2026-10-10，未完成 P08）](BALDR_P08_ACCOUNT_BINDING_SLICE_20261010.md)
- [P08 快照來源紀錄切片（2026-10-10，P08 尚未完成）](BALDR_P08_SNAPSHOT_RECEIPT_SLICE_20261010.md)
- [BBP01 BBANDS30 上軌完整具名母體驗證（2026-10-07）](BALDR_PARENT_BBANDS30_UPPER_20261007.md)
- [個人 H20 模型中央接線與真候選核對（2026-10-06）](BALDR_PERSONAL_MODEL_ACTIVATION_INTEGRATION_20261006.md)
- [個人真模型啟用前讀回入口](BALDR_PERSONAL_MODEL_ACTIVATION_PREFLIGHT_20261006.md)
- [BALDR 產品可用性與 BUI-001 修復收據（2026-09-25）](BALDR_PRODUCT_USABILITY_20260925.md)
- [BALDR R01 Registry 有界同份讀取（2026-10-06）](BALDR_R01_REGISTRY_READ_BUDGET_20261006.md)
- [Baldr 讀取 session 中央審核（2026-10-08）](BALDR_READ_SESSION_CENTRAL_REVIEW_20261008.md)
- [1,000 檔合成保存研究產製與獨立讀回](BALDR_SYNTHETIC_UNIVERSE_1000_READBACK_20261008.md)
- [dev／main 分支整理與可恢復收據](BALDR_TWO_BRANCH_RECOVERY_20261007.md)
- [臺銀證券電子下單成本估算 QA（2026-09-14）](BANKTAIWAN_COST_ESTIMATE_2026_09_14.md)
- [C2 mandatory UI/static gate 現況收據（2026-09-25）](C2_MANDATORY_UI_STATIC_GATES_20260925.md)
- [C4 最終 mandatory UI/static gates 收據（2026-09-25）](C4_FINAL_MANDATORY_STATIC_GATES_20260925.md)
- [每日 Decision Evidence Capture 修復 QA（2026-09-18）](DAILY_CAPTURE_RECOVERY_2026_09_18.md)
- [Experiment V1 Preregistration Template](EXPERIMENT_V1_PREREGISTRATION_TEMPLATE.md)
- [Graphify 程式碼引用查核收尾（2026-09-17）](GRAPHIFY_CODE_REFERENCE_REVIEW_2026_09_17.md)
- [H20 同次來源圖表接線中央審查](H20_BOUND_CHART_INTEGRATION_20261008.md)
- [H20 返回來源：避免重複名單核驗](H20_RETURN_SINGLE_REFRESH_20261007.md)
- [H20 可見等待、取消終態與單一讀取](H20_VISIBLE_LOADING_SINGLEFLIGHT_20261008.md)
- [Journal 跨頁 worker gate 隔離診斷（2026-10-06）](JOURNAL_JOURNEY_WORKER_GATE_20261006.md)
- [Learning Evidence Denominator QA — 2026-09-18](LEARNING_EVIDENCE_DENOMINATORS_2026_09_18.md)
- [Learning Evidence Workbench QA 紀錄（2026-09-14）](LEARNING_EVIDENCE_WORKBENCH_2026_09_14.md)
- [m11 個人模型與自然結果評估（2026-09-28）](M11_PERSONAL_RESEARCH_OUTCOME_STAGEC_20260928.md)
- [Natural maturity calendar refresh wiring QA（2026-09-18）](MATURITY_CALENDAR_REFRESH_WIRING_2026_09_18.md)
- [Forward maturity calendar 接線 QA（2026-09-18）](MATURITY_CALENDAR_WIRING_2026_09_18.md)
- [2026-10-03 行情發布節奏與 Paper 研究隔離驗收](OPERATIONAL_QUALITY_AND_RESEARCH_ISOLATION_20261003.md)
- [Paper EOD credit candidate freshness policy QA（2026-09-22）](PAPER_EOD_CREDIT_CANDIDATE_POLICY_QA_2026_09_22.md)
- [Paper EOD freshness lane unknown projection QA（2026-09-21）](PAPER_EOD_FRESHNESS_LANE_QA_2026_09_21.md)
- [Paper EOD 非交易日 gate 修正 QA（2026-09-25）](PAPER_EOD_NON_TRADING_DAY_GATE_QA_2026_09_25.md)
- [Paper EOD scope manifest v2→v3 受控修正計畫](PAPER_EOD_SCOPE_MANIFEST_MIGRATION_PLAN_2026_09_21.md)
- [Paper event source capture failure diagnostics QA — 2026-10-02](PAPER_EVENT_SOURCE_CAPTURE_FAILURE_DIAGNOSTICS_QA_20261002.md)
- [Personalization real-source fit runner QA（2026-09-17）](PERSONALIZATION_FIT_RUNNER_QA_2026_09_17.md)
- [Personalization 真實來源唯讀入口 QA（2026-09-16）](PERSONALIZATION_READONLY_SOURCE_QA_2026_09_16.md)
- [個人日常產品交付工作包與驗收矩陣](PERSONAL_DAILY_PRODUCT_DELIVERY_20261006.md)
- [Personal Delivery Activation QA（2026-09-18）](PERSONAL_DELIVERY_ACTIVATION_2026_09_18.md)
- [m10 個人模型 Qt widget 驗收（2026-09-28）](PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md)
- [個人研究 UI 隔離啟動器（2026-09-28）](PERSONAL_RESEARCH_UI_ISOLATION_20260928.md)
- [Personal subtree 政策變更 lane](PERSONAL_SUBTREE_POLICY_LANE_20261006.md)
- [Position Health Increment 1 QA（2026-09-15）](POSITION_HEALTH_INCREMENT_1_QA_2026_09_15.md)
- [PRODUCT_STAGE01_SOURCE_MATRIX_20261005](PRODUCT_STAGE01_SOURCE_MATRIX_20261005.md)
- [階段1早期SQL取消與下一包依賴（2026-10-05）](PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)
- [Qt／Python 原生事件唯讀追查補充](QT_NATIVE_CRASH_READONLY_FOLLOWUP_2026_09_15.md)
- [R006 unknown artifact 與保留策略（2026-09-27 addendum）](R006_UNKNOWN_ARTIFACT_RETENTION_ADDENDUM_20260927.md)
- [Recommendation Learning Runtime Wiring QA — 2026-09-15](RECOMMENDATION_LEARNING_RUNTIME_WIRING_QA_2026_09_15.md)
- [Scheduler / Paper 空持倉與研究種子範圍修復 QA](SCHEDULER_PAPER_SCOPE_REPAIR_20260930.md)
- [Stage6／UX11 規則卡唯讀投影限定收據（2026-10-06）](STAGE6_RULE_CARD_READMODEL_20261006.md)
- [完整母體逐段核驗讀取 API](TECHNICAL_VERIFIED_PARENT_STREAM_20261007.md)
- [user_declared Holding Research Increment 2 QA](USER_DECLARED_HOLDING_RESEARCH_INCREMENT_2_QA_2026_09_15.md)
- [UX02 共用狀態詞彙有限切片（2026-10-05）](UX02_SHARED_STATUS_VOCABULARY_20261005.md)
- [UX07 圖表可行性調查（2026-10-05）](UX07_CHART_FEASIBILITY_20261005.md)
- [UX08 原生圖同源契約限定驗證（2026-10-05）](UX08_NATIVE_CHART_CONTRACT_20261005.md)
- [UX08 推薦 execution 保存圖表有限閉環（2026-10-06）](UX08_RECOMMENDATION_SAVED_CHART_20261006.md)
- [UX08 保存價格／MA20／MA60 同版本讀回（2026-10-06）](UX08_SAVED_CHART_READBACK_20261006.md)
- [UX09 研究名單入選生命週期有限包（2026-10-05）](UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)
- [UX10 多方法共同符合：獨立 lane 限定交接](UX10_MULTI_METHOD_LANE_20261006.md)
- [UX11 保存結果與規則來源核對限定收據（2026-10-06）](UX11_SAVED_RESULT_RULE_READBACK_20261006.md)
- [UX18 原引擎排名不可變發布與同源讀回](UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)
- [原排名收藏與個股來源版本化](UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)
- [UX19 儲存治理與發布復原有限收尾（2026-10-05）](UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)
- [UX20 具名母體多批 capture 整合收據（2026-10-06）](UX20_PARENT_CAPTURE_INTEGRATION_20261006.md)
- [UX20 保存母體收據 UI 限定整合（2026-10-06）](UX20_PARENT_RECEIPT_UI_20261006.md)
- [UX20 固定 MA 研究樣本 capture 獨立 lane](UX20_RULE_SAMPLE_CAPTURE_LANE_20261006.md)
- [UX20 MA 完整控制組 capture 主線限定整合（2026-10-06）](UX20_SAMPLE_CAPTURE_INTEGRATION_20261006.md)
- [UX21 具名 benchmark 唯讀 adapter 獨立 lane](UX21_BENCHMARK_ADAPTER_20261006.md)
- [UX21 實際來源、隔離保存與日報限定收據](UX21_SOURCE_STORE_DAILY_20261006.md)
- [UX21 endpoint label → UX22 樣本／公平比較 readiness（2026-10-06）](UX22_LABEL_READINESS_20261006.md)
- [UX23 registry 唯讀 reader 隔離驗收（2026-10-06）](UX23_REGISTRY_READONLY_20261006.md)
- [UX23 隔離 shadow 最小工程狀態（2026-10-06）](UX23_SHADOW_ACCEPTANCE_20261006.md)
