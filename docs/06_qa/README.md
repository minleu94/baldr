# QA 證據導覽

> 本目錄保存日期化驗收、調查與交接證據。它們描述各自的範圍與時間點；目前專案狀態請看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，產品操作請看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。主題相同不代表證據可互換，舊報告中的待辦也不自動成為目前待辦。

## 先從這裡開始

1. [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)：目前狀態、未成熟項目與阻礙。
2. [10/08 產品補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md)：近期補完範圍與缺口入口。
3. [10/08 排程修復](BALDR_SCHEDULE_REPAIR_20261008.md)：近期排程修復的證據入口；查更早時點再讀 [9/30 排程修復](SCHEDULED_OPERATIONS_REPAIR_20260930.md)。
4. 按下方主題表選擇主線；需要操作步驟時回到 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

## 八個主題地圖

| 主題 | 建議閱讀順序 | 範圍提示 |
|---|---|---|
| H20 個股研究 | [H20 gross model 契約](BALDR_A02_H20_GROSS_MODEL_20261006.md) → [研究 cohort](BALDR_H20_RESEARCH_COHORT_20261007.md) → [目前候選](BALDR_H20_CURRENT_CANDIDATE_93F9C57D_20261008.md) → [操作讀回](H20_READ_OPERATION_SESSION_20261007.md) → [圖表契約](H20_BOUND_CHART_CONTRACT_REVIEW_20261008.md) | 模型研究、目前來源、保存與圖表是不同驗收面；不能互推 ML 正式資格。 |
| R026／R031 依賴重構 | [R031 最終 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) → [31-task evidence index](R031_TASK_REPORT_INDEX_DRAFT_20260925.md) → [R026 exact allowlist](ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md) → [source revision aggregate](R026_SOURCE_REVISION_EVIDENCE_AGGREGATE_20260925.md) | index 是各 task 結案／範圍的導覽；R001、R006、R020 的大型 dated receipts 已移至 [Archive](../09_archive/README.md#2026-10-08-r001-r006-r020-historical-qa)。aggregate 與逐項 R026 收據按各自的來源身分、版本與範圍判讀。 |
| UX02–UX24 研究工作台 | [UX16 來源契約](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md) → [UX24 首版工程封存](UX24_FIRST_VERSION_ENGINEERING_SEAL_20261006.md) → [UX21 Forward Outcome](UX21_FORWARD_OUTCOME_20261006.md) → [UX09 歷史索引](UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md) | 單張 UX 收據只覆蓋其標示的卡與階段；Native、真人、自然資格另判。 |
| BALDR 產品補完 | [補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md) → [First wave](BALDR_COMPLETION_FIRST_WAVE_20261006.md) → [B01–B14 收據](#baldr-b01b14) → [10/08 排程修復](BALDR_SCHEDULE_REPAIR_20261008.md) | lane 工程接線不代表全母體、自然累積或正式資格完成。 |
| WP1–WP5 工作包 | [WP5 HEAD 缺口診斷](WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md) → [WP5 checkpoint](WP5_CHECKPOINT_CURRENT_20260928.md) → [WP5 integration checklist](WP5_INTEGRATION_CHECKLIST_20260928.md) | pending 項目與完成項目需按目前 HEAD 的逐筆證據判讀。 |
| Task Loop 01–08 | [01](TASK_LOOP_01_HANDOFF.md) → [02](TASK_LOOP_02_HANDOFF.md) → [03](TASK_LOOP_03_HANDOFF.md) → [04](TASK_LOOP_04_HANDOFF.md) → [05](TASK_LOOP_05_HANDOFF.md) → [06](TASK_LOOP_06_HANDOFF.md) → [07](TASK_LOOP_07_HANDOFF.md) → [08](TASK_LOOP_08_HANDOFF.md) | 連續交接紀錄；讀取單張時保留其原始前置條件與交接邊界。 |
| ML Shadow 與前瞻證據 | [Gate 7 工程入口](GATE_7_ML_SHADOW_ENGINEERING.md) → [R026 ML boundary](ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md) → [V4 daily evidence loop](V4_DAILY_EVIDENCE_LOOP_HANDOFF_2026_09_12.md) → [Prospective restart direction](PROSPECTIVE_FORMAL_RESTART_DIRECTION_2026_08_19.md) → [被拒絕的 V2 staging 歷史](../09_archive/PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_27_V2_STAGING_HISTORY.md) | Shadow、engineering readiness、成熟度與正式 OOS／投資有效性是不同狀態；V2 文件只記錄當時被拒絕的 staging，不代表目前狀態。 |
| Data Governance 與來源 | [10/03 data closeout](FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md) → [正式資料修復](FORMAL_DATA_REPAIR_2026_09_23.md) → [PIT taxonomy daily source](PIT_TAXONOMY_DAILY_SOURCE_QA_2026_09_15.md) → [產業來源驗收](PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md) | source coverage、publication、PIT eligibility 與正式訓練資格不可混為一談。 |

## 近期與跨主題收據

| 要查的內容 | 證據入口 |
|---|---|
| 四用途整合、來源／ML/UI 的限界收尾 | [Astra engineering closeout（10/03–05）](ASTRA_ENGINEERING_CLOSEOUT_20261003.md) |
| Windows、資料、ML 與原生 UI 的三階段整合修復 | [Integration repair acceptance（10/02–03）](INTEGRATION_REPAIR_ACCEPTANCE_20261002.md) |
| 指定時點的排程修復、失敗與後續補充 | [Scheduled operations repair（9/30）](SCHEDULED_OPERATIONS_REPAIR_20260930.md)；目前看 [10/08 排程修復](BALDR_SCHEDULE_REPAIR_20261008.md) |
| 舊 ML program readiness 稽核與後續修正 | [8/27 稽核](../09_archive/PROGRAM_READINESS_AUDIT_2026_08_27.md) → [8/28 更新](../09_archive/PROGRAM_READINESS_AUDIT_2026_08_28.md)；只作歷史底冊，現況看 Snapshot |
| 測試資產候選與保留判斷 | [結案報告](../09_archive/TEST_ASSET_CONSOLIDATION_CLOSEOUT_2026_09_17.md) → [V2 方法補正](../09_archive/TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17_V2.md) → [V1 撤回紀錄](../09_archive/TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17.md)；139 組／1,107 檔為 bounded 範圍，不代表完整測試母體 |
| 基本面與估值來源 | [月營收來源審查](BALDR_F12_MONTHLY_REVENUE_SOURCE_REVIEW_20261009.md) → [基本面快照設定](FUNDAMENTAL_SNAPSHOT_CONFIG_20261007.md) → [來源採納與季度目錄](FUNDAMENTAL_SOURCE_ACCEPTANCE_AND_QUARTERLY_CATALOG_20261001.md) | 每份收據只覆蓋其來源與時點；candidate／capture 不等於正式採納、歷史 PIT 或正式評分。 |
| 四用途 UX 結果、近期工程增量 | [B03 Update／Runtime](BALDR_B03_UPDATE_RUNTIME_20261006.md)、[B04 收藏](BALDR_B04_SELECTION_WATCHLIST_20261006.md)、[B05 圖表](BALDR_B05_CHART_INCREMENT_20261006.md)、[B06 投資組合摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、[B10 私人覆盤](BALDR_B10_PRIVATE_REVIEW_20261006.md)、[B12 隔離 runtime](BALDR_B12_DAILY_RUNTIME_20261006.md) |
| 個股研究的其他讀回 | [報告與 ML 分流](H20_REPORT_ML_SEPARATION_COPY_20261008.md)、[目前來源診斷](H20_SAVED_AND_CURRENT_SOURCE_DIAGNOSIS_20261008.md)、[獨立 current research](H20_INDEPENDENT_CURRENT_RESEARCH_20261008.md)、[載入 candidate](BALDR_H20_LOADING_CANDIDATE_421BC973_20261008.md) |

### BALDR B01–B14

依產品補完缺口表選擇對應收據：B01 [歷史標籤邊界](BALDR_B01_HISTORICAL_LABEL_BOUNDARY_20261006.md)、B02 Windows COW 見 [closeout status 表](BALDR_CLOSEOUT_STATUS_20261006.md)、B03 [市場首頁](BALDR_B03_MARKET_HOME_20261006.md)／[Update runtime](BALDR_B03_UPDATE_RUNTIME_20261006.md)、B04 [選擇與收藏](BALDR_B04_SELECTION_WATCHLIST_20261006.md)、B05 [圖表](BALDR_B05_CHART_INCREMENT_20261006.md)、B06 [投資組合摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、B07 [規則歷史](BALDR_B07_RULE_HISTORY_20261006.md)、B08 [個人路由](BALDR_B08_PERSONAL_ROUTES_20261006.md)、B09 [個人投資組合](BALDR_B09_PERSONAL_PORTFOLIO_20261006.md)、B10 [私人覆盤](BALDR_B10_PRIVATE_REVIEW_20261006.md)、B11 [模型家族目錄](BALDR_B11_FAMILY_CATALOG_20261006.md)、B12 [每日 runtime](BALDR_B12_DAILY_RUNTIME_20261006.md)、B13 [模型輸入](BALDR_B13_MODEL_INPUT_20261006.md)、B14 [Shadow evidence](BALDR_B14_SHADOW_EVIDENCE_COMPOSITION_20261006.md)。

### 2026-10-06 至 10-09 收據直達索引

以下連結補齊近期 25 份原始收據的閱讀入口。收據仍保留各自的範圍與時點；此索引不把它們合併成新的現況、完成度或待辦判定。

- **H20 研究來源與讀回**：[固定來源建置](BALDR_H20_FIXED_SOURCE_BUILD_REVIEW_20261009.md)、[Runtime root 契約](BALDR_H20_RUNTIME_ROOT_CONTRACT_REVIEW_20261008.md)、[Snapshot builder](BALDR_H20_SNAPSHOT_BUILDER_REVIEW_20261008.md)、[WAL snapshot](BALDR_H20_WAL_SNAPSHOT_REVIEW_20261008.md)、[版面 teardown 與窄控制](BALDR_LAYOUT_TEARDOWN_AND_NARROW_CONTROLS_20261008.md)、[Bookmark controls](H20_BOOKMARK_CONTROLS_20261007.md)、[Bookmark core](H20_BOOKMARK_CORE_20261007.md)、[凍結來源 root 修復](H20_FROZEN_SOURCE_ROOT_REPAIR_20261007.md)。
- **推薦介面與個人工作區**：[推薦鍵盤捲動](BALDR_RECOMMENDATION_KEYBOARD_SCROLL_20261008.md)、[個人 Watchlist thread serialization](PERSONAL_WATCHLIST_THREAD_SERIALIZATION_20261007.md)、[推薦閱讀版面](RECOMMENDATION_READING_LAYOUT_20261007.md)。
- **產品補完與發布**：[F17 正常 capture pair review](BALDR_F17_NORMAL_CAPTURE_PAIR_REVIEW_20261009.md)、[平行工作交接](BALDR_PARALLEL_NEXT_WORK_20261009.md)、[portable configured bootstrap](BALDR_PORTABLE_CONFIGURED_BOOTSTRAP_20261006.md)、[portable Windows](BALDR_PORTABLE_WINDOWS_20261006.md)、[F07 固定候選](F07_FIXED_CANDIDATE_F2FBA4C7_20261008.md)、[F17 single graph integration](F17_SINGLE_GRAPH_INTEGRATION_20261008.md)。
- **基本面與資料快照**：[選股基本面副本 session](SELECTION_FUNDAMENTAL_COPY_SESSION_20261007.md)、[月營收 YoY](SELECTION_MONTHLY_REVENUE_YOY_20261007.md)、[Snapshot typed parts reuse](SNAPSHOT_TYPED_PARTS_REUSE_20261007.md)。
- **日期語義、篩選與 Universe**：[決策 Snapshot 日期語義](DECISION_SNAPSHOT_DATE_SEMANTICS_20261006.md)、[P01 篩選 Profile diagnostics](P01_FILTER_PROFILE_DIAGNOSTIC_CONTRACT_20261008.md)、[技術規則視窗重用](TECHNICAL_RULE_WINDOW_REUSE_20261007.md)、[技術 Universe query stream](TECHNICAL_UNIVERSE_QUERY_STREAM_20261007.md)、[技術 Universe read root](TECHNICAL_UNIVERSE_READ_ROOT_20261007.md)。

## 其他常用路徑

- **排程與自動化**：[10/08 修復](BALDR_SCHEDULE_REPAIR_20261008.md) → [10/07 修復](BALDR_SCHEDULE_REPAIR_20261007.md) → [10/06 稽核](BALDR_SCHEDULE_AUDIT_20261006.md)；需要歷史初始狀況再讀 [9/30 收據](SCHEDULED_OPERATIONS_REPAIR_20260930.md)。
- **投資組合與 Paper**：[三帳摘要](BALDR_B06_PORTFOLIO_SUMMARY_20261006.md)、[個人 Paper producers](BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md)、[個人 Paper ledgers](BALDR_PERSONAL_PAPER_LEDGERS_20261006.md)。
- **Watchlist 儲存與 COW 遷移（F4，2026-10-05）**：[revision retention](F4_ITEM_REVISION_STORAGE_AND_RETENTION_20261005.md) → [SQLite COW](F4_SQLITE_COW_CONVERTER_AND_ACTIVATION_20261005.md) → [Legacy JSON COW](F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md) → [整合／容量驗收](F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)。這組隔離工程收據與正式資料 apply／activation 分開判讀，也不同於後續 B02 個人儲存工作包。
- **技術分析與圖表**：[BBANDS 上軌入口](BALDR_A01_BBANDS_UPPER_20261006.md)、[每日 BBANDS](BALDR_DAILY_BBANDS_CENTRAL_20261007.md)、[H20 圖表契約](H20_BOUND_CHART_CONTRACT_REVIEW_20261008.md)。
- **測試路由與人工驗收**：[Feature-to-test routing matrix](FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md)、[test inventory healthcheck classification](TEST_INVENTORY_HEALTHCHECK_CLASSIFICATION_2026_06_23.md)、[早期 Full App healthcheck（已歸檔）](../09_archive/FULL_APP_HEALTHCHECK_2026_06_16.md)、[歷史 V1 release checklist](../09_archive/V1_RELEASE_CHECKLIST_2026_06_30.md)。
- **早期產品 QA**：[Recommendation Tab issues](QA_RECOMMENDATION_TAB_ISSUES.md)、[Recommendation Tab summary](QA_RECOMMENDATION_TAB_SUMMARY.md)、[Update Tab issues](QA_UPDATE_TAB_ISSUES.md)、[Update Tab summary](QA_UPDATE_TAB_SUMMARY.md)。
- **歷史工程閉環與沿用契約**：[V3.3 Engineering closeout](V3_3_ENGINEERING_CLOSEOUT_2026_07_12.md) 仍被外部驗證登記、Control Center 與 Manual supplements 引用為 Daily／Weekly／Monthly／Maturity／Failure 操作契約；引用契約時需回核現行 Manual／Snapshot。 [V4 daily evidence handoff](V4_DAILY_EVIDENCE_LOOP_HANDOFF_2026_09_12.md) 是日期化交接。V1.5–V2.0 milestone QA 見[歷史專區](../09_archive/README.md#v15v20-qa-milestones)；V2.1–V2.5 readiness／closeout 見[第二歷史專區](../09_archive/README.md#v21v25-historical-readiness-and-closeout)；Program Readiness 與測試資產舊稽核亦已歸檔。P0 source register 及 approval 收據仍留在本目錄；歷史 roadmap 見[歸檔版本史](../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md)。
- **V4 9/7 bounded release／data QA（歷史）**：當日三份收據見 [Archive 專區](../09_archive/README.md#v4-2026-09-07-bounded-evidence)；資料後續收尾見 [10/03 closeout](FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md)，現況仍看 Snapshot。
- **V4 9/8 Formal／ML／Ops handoffs（歷史）**：三份 owner handoff 已移入 [Archive 專區](../09_archive/README.md#2026-10-08-v4-next-handoff-history)；Formal bootstrap 的後續讀回見 [9/30 repair](SCHEDULER_FORMAL_BOOTSTRAP_REPAIR_20260930.md)，目前排程狀態看 Snapshot／近期 QA，操作看 Manual。
- **Post-V1 Evidence Pipeline（2026-07，歷史）**：當時的 event store、forward outcome、review 與 scheduler 收據已集中於 [Archive 專區](../09_archive/README.md#post-v1-evidence-pipeline-qa)；目前狀態看 Snapshot，操作看 Manual 與最新排程 QA。
- **Broker Flow 效能歷史收據（2026-07）**：[原始 dashboard failed gate → 後續 semantics scoped pass](../09_archive/README.md#2026-07-broker-flow-and-ui-closeout)；兩份收據保留各自的母體、測量與 gate 範圍。

- **Workbench 歷史 UI closeout**：[左側主導覽 IA（2026-07-07）](../09_archive/WORKBENCH_LEFT_NAVIGATION_IA_CLOSEOUT_2026_07_07_HISTORY.md)、[視覺層級 polish（2026-07-07）](../09_archive/WORKBENCH_VISUAL_HIERARCHY_POLISH_CLOSEOUT_2026_07_07_HISTORY.md)：保留當時 UI 與測試證據，不作目前狀態依據；現行操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。
- **Readability polish closeout（2026-07-07，歷史）**：[Archive 原文](../09_archive/README.md#2026-07-broker-flow-and-ui-closeout)；當時 formal-data waits 是該次快照，現況看 Snapshot／Manual。
- **2026-06／07 一次性 QA、工程 closeout 與 audit**：依主題於 [Archive 專區](../09_archive/README.md#2026-10-08-early-qa-closeouts)查找；Evidence Rehearsal runbook、Full App coverage mapping、External Validation Register 與現行狀態文件仍留在目前入口。

## 閱讀與歸檔規則

- QA 原文保存當時輸入、失敗、結果、回滾與接受邊界；入口摘要只供導覽，不改寫證據結論。
- 超長報告先讀標題、開頭的範圍／結論及本頁入口，再依問題查原始章節；不要把整份 terminal dump 當成目前狀態。
- JSON 收據與 `project_status_2026_08_14/` 是機器或報告伴隨物，應與對應說明文件一起判讀；不要只憑檔名把它們當作獨立產品文件。
- 歷史 archive 的定位與規則見 [docs/09_archive README](../09_archive/README.md)；完整文件分類見 [DOCUMENTATION_INDEX](../00_core/DOCUMENTATION_INDEX.md)。
- 已歸檔 QA： [文件編碼稽核（2026-06-16）](../09_archive/DOCUMENT_ENCODING_AUDIT_2026_06_16.md)、[文件與 Roadmap 重整稽核（2026-07-03）](../09_archive/DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md)、[Pre-push 文件治理稽核（2026-07-06）](../09_archive/DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06_HISTORY.md)、[Pre-V2 非排程 readiness closeout（2026-07-06）](../09_archive/PRE_V2_NON_SCHEDULE_READINESS_CLOSEOUT_2026_07_06_HISTORY.md)、[ML Shadow 推論操作 closeout（2026-07-15）](../09_archive/ML_SHADOW_INFERENCE_OPERATIONS_CLOSEOUT_2026_07_15_HISTORY.md)、[SQLite inspector 關閉探測（2026-09-15）](../09_archive/QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md)。
