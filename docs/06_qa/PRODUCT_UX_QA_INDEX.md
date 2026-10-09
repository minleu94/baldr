# 產品與個股研究 QA 索引

> [回 QA 證據導覽](README.md)。本索引只供導覽。每份收據仍須按自身日期、範圍與限制判讀；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。索引不代表 Gate 通過，也不改變 QA 原件的生命週期。

## 個股研究與產品 UX

| 主題 | 建議閱讀順序 | 範圍提示 |
|---|---|---|
| H20 個股研究 | [H20 gross model 契約](BALDR_A02_H20_GROSS_MODEL_20261006.md) → [研究 cohort](BALDR_H20_RESEARCH_COHORT_20261007.md) → [目前候選](BALDR_H20_CURRENT_CANDIDATE_93F9C57D_20261008.md) → [操作讀回](H20_READ_OPERATION_SESSION_20261007.md) → [圖表契約](H20_BOUND_CHART_CONTRACT_REVIEW_20261008.md) | 模型研究、目前來源、保存與圖表是不同驗收面；不能互推 ML 正式資格。 |
| UX02–UX24 研究工作台 | [UX08 viewport 整合 QA](UX08_VIEWPORT_INTEGRATION_20261006.md) → [UX08 純 controller handoff 歷史](../09_archive/README.md#2026-10-09-qa-historical-snapshots-scheduler-health-and-ux08-controller) → [UX16 來源契約](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md) → [UX24 首版工程封存（bounded）](../09_archive/UX24_FIRST_VERSION_ENGINEERING_SEAL_20261006.md) → [UX21 Forward Outcome](UX21_FORWARD_OUTCOME_20261006.md) → [UX09 歷史索引](UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md) | UX24 僅關閉其七項有限工程終點，整體 UX／正式啟用／Native 真人／自然成熟仍待各自驗收；目前 UX08 也仍有 Native／真人與其他明列驗收未完成，單張 UX 收據只覆蓋其標示的卡與階段。 |
| BALDR 產品補完 | [補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md) → [First wave](BALDR_COMPLETION_FIRST_WAVE_20261006.md) → [B01–B14 收據](#baldr-b01b14) → [10/08 排程修復](BALDR_SCHEDULE_REPAIR_20261008.md) | lane 工程接線不代表全母體、自然累積或正式資格完成。First Wave QA 引用的兩張 Python／exe 截圖在 ignored 的本機 `output/qa/`，乾淨 checkout 不包含圖片。 |
| BALDR M2／H20 深化 | [M2 完整工程收據](BALDR_COMPLETION_M2_20261007.md) → [中央 cohort／Natural／BB UI 整合](BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md) → [推薦真人回饋](BALDR_RECOMMENDATION_HUMAN_FEEDBACK_20261007.md) | M2、自然樣本與真人／Native 驗收各有獨立限制；以缺口表及原收據判讀，不把局部工程結果視為產品結案。 |
| 個人研究筆記與儲存隔離 | [Personal Storage Separation](PERSONAL_STORAGE_SEPARATION_LANE_20261005.md) → [Personal Journal](PERSONAL_JOURNAL_LANE_20261006.md) | 正式儲存遷移、啟用與跨頁 readback 仍有未結 Gate；兩份收據範圍不同，請分別核對。 |
| UX20–UX23 固定觀測日與 ML Readiness | [UX20 觀測日接受政策](UX20_OBSERVATION_DAY_ACCEPTANCE_20261006.md) → [UX20 Daily Owner](UX20_DAILY_OWNER_ISOLATED_20261006.md) → [UX21 Benchmark source store](UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md) → [UX22 同源公平比較](UX22_FAIR_COMPARISON_20261006.md) → [UX23 Registry read-only consumer](UX23_REGISTRY_INTEGRATION_20261006.md) | 這些收據記錄 bounded 隔離流程與來源限制；UX20／UX21／UX22／UX23 各自的 Stage、部署與模型資格不得互相推定。 |

## 近期與跨主題收據

| 要查的內容 | 證據入口 |
|---|---|
| 四用途 UX 結果、近期工程增量 | [B03 Update／Runtime](BALDR_B03_UPDATE_RUNTIME_20261006.md)、[B04 收藏](BALDR_B04_SELECTION_WATCHLIST_20261006.md)、[B05 圖表](BALDR_B05_CHART_INCREMENT_20261006.md)、[B06 投資組合摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、[B10 私人覆盤](BALDR_B10_PRIVATE_REVIEW_20261006.md)、[B12 隔離 runtime](BALDR_B12_DAILY_RUNTIME_20261006.md) |
| 個股研究的其他讀回 | [報告與 ML 分流](H20_REPORT_ML_SEPARATION_COPY_20261008.md)、[目前來源診斷](H20_SAVED_AND_CURRENT_SOURCE_DIAGNOSIS_20261008.md)、[獨立 current research](H20_INDEPENDENT_CURRENT_RESEARCH_20261008.md)、[載入 candidate](BALDR_H20_LOADING_CANDIDATE_421BC973_20261008.md) |

<a id="baldr-b01b14"></a>
### BALDR B01–B14

依產品補完缺口表選擇對應收據：B01 [歷史標籤邊界](BALDR_B01_HISTORICAL_LABEL_BOUNDARY_20261006.md)、B02 Windows COW 見 [closeout status 表](BALDR_CLOSEOUT_STATUS_20261006.md)、B03 [市場首頁](BALDR_B03_MARKET_HOME_20261006.md)／[Update runtime](BALDR_B03_UPDATE_RUNTIME_20261006.md)、B04 [選擇與收藏](BALDR_B04_SELECTION_WATCHLIST_20261006.md)、B05 [圖表](BALDR_B05_CHART_INCREMENT_20261006.md)、B06 [投資組合摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、B07 [規則歷史](BALDR_B07_RULE_HISTORY_20261006.md)、B08 [個人路由](BALDR_B08_PERSONAL_ROUTES_20261006.md)、B09 [個人投資組合](BALDR_B09_PERSONAL_PORTFOLIO_20261006.md)、B10 [私人覆盤](BALDR_B10_PRIVATE_REVIEW_20261006.md)、B11 [模型家族目錄](BALDR_B11_FAMILY_CATALOG_20261006.md)、B12 [每日 runtime](BALDR_B12_DAILY_RUNTIME_20261006.md)、B13 [模型輸入](BALDR_B13_MODEL_INPUT_20261006.md)、B14 [Shadow evidence](BALDR_B14_SHADOW_EVIDENCE_COMPOSITION_20261006.md)。

### 2026-10-06 至 10-09 收據直達索引

以下連結補齊近期 26 份原始收據的閱讀入口。收據仍保留各自的範圍與時點；此索引不把它們合併成新的現況、完成度或待辦判定。

- **H20 研究來源與讀回**：[固定來源建置](BALDR_H20_FIXED_SOURCE_BUILD_REVIEW_20261009.md)、[來源清單環境橋接審查](BALDR_H20_SOURCE_MAP_SEAM_REVIEW_20261009.md)、[verifier 模組相容性 root review](BALDR_H20_VERIFIER_MODULE_COMPATIBILITY_ROOT_REVIEW_20261009.md)、[Runtime root 契約](BALDR_H20_RUNTIME_ROOT_CONTRACT_REVIEW_20261008.md)、[Snapshot builder](BALDR_H20_SNAPSHOT_BUILDER_REVIEW_20261008.md)、[WAL snapshot](BALDR_H20_WAL_SNAPSHOT_REVIEW_20261008.md)、[版面 teardown 與窄控制](BALDR_LAYOUT_TEARDOWN_AND_NARROW_CONTROLS_20261008.md)、[Bookmark controls](H20_BOOKMARK_CONTROLS_20261007.md)、[Bookmark core](H20_BOOKMARK_CORE_20261007.md)、[凍結來源 root 修復](H20_FROZEN_SOURCE_ROOT_REPAIR_20261007.md)。兩份 10/09 seam／verifier 收據未證明完整 Main、H20 下鑽或 EXE 真人驗收通過。
- **推薦介面與個人工作區**：[推薦理由完整保存審核](BALDR_COMPLETE_REASONS_REVIEW_20261008.md)、[推薦鍵盤捲動](BALDR_RECOMMENDATION_KEYBOARD_SCROLL_20261008.md)、[個人 Watchlist thread serialization](PERSONAL_WATCHLIST_THREAD_SERIALIZATION_20261007.md)、[推薦閱讀版面](RECOMMENDATION_READING_LAYOUT_20261007.md)。完整理由審核只涵蓋程式碼與版面驗證；新版 EXE 與真人操作驗收仍待完成，H20 下鑽另有獨立關卡。
- **產品補完與發布**：[F17 正常 capture pair review](BALDR_F17_NORMAL_CAPTURE_PAIR_REVIEW_20261009.md)、[正常技術／官方來源聯合產製 UI review](BALDR_F17_NORMAL_PRODUCTION_UI_REVIEW_20261009.md)、[官方當下處置來源 leaf](SELECTION_OFFICIAL_DISPOSAL_SOURCE_20261007.md)、[平行工作交接](BALDR_PARALLEL_NEXT_WORK_20261009.md)、[portable configured bootstrap](BALDR_PORTABLE_CONFIGURED_BOOTSTRAP_20261006.md)、[portable Windows](BALDR_PORTABLE_WINDOWS_20261006.md)、[F07 固定候選](F07_FIXED_CANDIDATE_F2FBA4C7_20261008.md)、[F17 single graph integration](F17_SINGLE_GRAPH_INTEGRATION_20261008.md)。該 leaf 的 `available_at` 未知、`current_only`、`historical_pit_eligible=false`；F17 UI review 的正常來源增量已驗，但完整 Main 下鑽、全母體效能、跨程序聯合收藏與 EXE 接受仍未完成，不代表 PIT acceptance 或 F17 結案。
- **日期語義、篩選與 Universe**：[決策 Snapshot 日期語義](DECISION_SNAPSHOT_DATE_SEMANTICS_20261006.md)、[P01 篩選 Profile diagnostics](P01_FILTER_PROFILE_DIAGNOSTIC_CONTRACT_20261008.md)、[單次頁面路徑 tuple memo](BALDR_P01_COMPONENT_TUPLE_MEMO_20261009.md)、[單頁路徑渲染 memo](BALDR_P01_PAGE_PATH_RENDER_MEMO_20261009.md)、[已簽發來源 DTO 重建](BALDR_P01_PROOF_GATED_REHYDRATION_20261009.md)、[技術規則視窗重用](TECHNICAL_RULE_WINDOW_REUSE_20261007.md)、[技術 Universe query stream](TECHNICAL_UNIVERSE_QUERY_STREAM_20261007.md)、[技術 Universe read root](TECHNICAL_UNIVERSE_READ_ROOT_20261007.md)。三份 P01 memo 是不同快取／重建層的證據；固定 1,000 檔矩陣的 filter p95 仍超過 300 ms，不能視為效能通過。

### F02／F03／F06／F12 功能驗收鏈（2026-10-09）

先看[產品補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md)與[平行工作 root review](BALDR_PARALLEL_ROOT_REVIEW_20261009.md)掌握跨功能阻礙，再按下列收據追查各自範圍。這些是 bounded 工程證據，不等於完整 UI、EXE 或真人驗收，也不代表相關 Gate 已通過。

- **F12 月營收**：[來源審查](BALDR_F12_MONTHLY_REVENUE_SOURCE_REVIEW_20261009.md) → [index 整合複核](BALDR_F12_INDEX_INTEGRATION_REVIEW_20261009.md) → [saved-recipe root review](BALDR_F12_SAVED_RECIPE_ROOT_REVIEW_20261009.md) → [WAL exact reopen](BALDR_F12_WAL_EXACT_REOPEN_ROOT_REVIEW_20261009.md) → [durable raw archive v2](BALDR_F12_DURABLE_RAW_ARCHIVE_V2_20261009.md) → [archived finish root review](BALDR_F12_ARCHIVED_FINISH_ROOT_REVIEW_20261009.md) → [Main integration review](BALDR_F12_MAIN_INTEGRATION_REVIEW_20261009.md)。Reader 仍是 current-only，來源時間不明時不可授予歷史 PIT 資格；完整 Main／UI、EXE 與真人驗收仍待完成。
- **F02 均線條件**：[四均線來源缺口與葉模組根審（10/08）](F02_SAVED_FEATURE_GAP_20261008.md) → [fdopen guard 診斷](BALDR_F02_FDOPEN_GUARD_DIAGNOSIS_20261009.md) → [M guard root review](BALDR_F02_M_GUARD_ROOT_REVIEW_20261009.md) → [V4 oracle／supervisor review](BALDR_F02_V4_ORACLE_SUPERVISOR_REVIEW_20261009.md)。10/08 報告確認保存特徵缺口並記錄單一葉模組驗證，不代表產品接線或驗收。完整 257 檔矩陣、正常來源、新 EXE、真人驗收與 MA20 上彎契約仍未完成；局部 guard／oracle 結果不可當成產品通過。
- **F03 KDJ 條件**：[full-population 整合計畫](BALDR_F03_FULL_POPULATION_INTEGRATION_PLAN_20261009.md) → [KDJ query contract](BALDR_F03_KDJ_QUERY_CONTRACT_20261009.md) → [MA／KDJ／Volatility group v2](BALDR_F03_MA_KDJ_VOLATILITY_GROUP_V2_20261009.md) → [multi-parent callback review](BALDR_F03_MULTI_PARENT_CALLBACK_REVIEW_20261009.md)。有界切片不代表 full-population query、共同發布或 UI 已完成。
- **F06 波動條件**：[composite query contract](BALDR_F06_COMPOSITE_VOLATILITY_QUERY_CONTRACT_20261009.md) → [Decimal 方法提案](BALDR_F06_DECIMAL_VOLATILITY_METHOD_PROPOSAL_20261009.md) → [collector contract](BALDR_F06_VOLATILITY_COLLECTOR_CONTRACT_20261009.md)。目前尚無 full-N reader-issued 結果；方法提案不是已採納的產品規則。

## 其他常用路徑

- **投資組合與 Paper**：[三帳摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、[個人 Paper producers](BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md)、[個人 Paper ledgers](BALDR_PERSONAL_PAPER_LEDGERS_20261006.md)。
- **Watchlist 儲存與 COW 遷移（F4，2026-10-05）**：[revision retention](F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md) → [SQLite COW](F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md) → [Legacy JSON COW](F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md) → [整合／容量驗收](F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)。這組隔離工程收據與正式資料 apply／activation 分開判讀，也不同於後續 B02 個人儲存工作包。
- **技術分析與圖表**：[BBANDS 上軌入口](BALDR_A01_BBANDS_UPPER_20261006.md)、[每日 BBANDS](BALDR_DAILY_BBANDS_CENTRAL_20261007.md)、[H20 圖表契約](H20_BOUND_CHART_CONTRACT_REVIEW_20261008.md)。
- **早期產品 QA（歷史）**：推薦分析與數據更新 Tab 的四份舊問題盤點／QA 摘要已移至[歷史封存入口](../09_archive/README.md#2026-10-08-early-recommendation-and-update-tab-qa)。原路徑保留短導引；其中的路徑、測試數字與待辦不代表目前實作或驗收結果。現行操作與排錯以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準，測試範圍看 [Feature-to-test routing matrix](FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md)。
- **Workbench 歷史 UI closeout**：[左側主導覽 IA（2026-07-07）](../09_archive/WORKBENCH_LEFT_NAVIGATION_IA_CLOSEOUT_2026_07_07_HISTORY.md)、[視覺層級 polish（2026-07-07）](../09_archive/WORKBENCH_VISUAL_HIERARCHY_POLISH_CLOSEOUT_2026_07_07_HISTORY.md)：保留當時 UI 與測試證據，不作目前狀態依據；現行操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。
- **Readability polish closeout（2026-07-07，歷史）**：[Archive 原文](../09_archive/README.md#2026-07-broker-flow-and-ui-closeout)；當時 formal-data waits 是該次快照，現況看 Snapshot／Manual。
- **Workbench 低流動性提示分流 QA（2026-09-21，歷史）**：[封存收據](../09_archive/WORKBENCH_LIQUIDITY_REVIEW_ROUTING_QA_2026_09_21_HISTORY.md)保留當日 read-only snapshot／UI route 與 `1121` liquidity、`10` weakness 的 bounded 結果；後續整合路由見[封存的 V5 readability acceptance](../09_archive/V5_READABILITY_ACCEPTANCE_2026_09_21.md)，目前操作仍以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準。該收據不驗證 liquidity 資料品質或正式來源 Gate；本批封存來源 bytes／SHA 見 [Coverage History Entry 149](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-149)，低流動性收據原件見 [Entry 125](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-125)。
- **UI geometry audit（2026-09-29，歷史）**：[封存收據](../09_archive/UI_LAYOUT_AUDIT_20260929.md)記錄六格 offscreen viewport 矩陣及合成 UI 覆蓋；這不證明 Windows 原生視窗行為，也未證實先前 native access violation 的根因或永久修復。原路徑保留相容導引，來源與替代入口見 [Coverage History Entry 151](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-151)。
