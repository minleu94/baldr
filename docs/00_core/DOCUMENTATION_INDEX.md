# 文檔索引

> 2026-10-09 更新。本頁維護閱讀與文件位置；目前狀態只看 Snapshot，日期化測試數字只看原 QA receipt。

## 權威入口

Windows 雙擊入口、整個資料夾需求與外部設定：[PORTABLE_WINDOWS](../07_guides/PORTABLE_WINDOWS.md)。

| 問題 | 入口 |
|---|---|
| 目前狀態與下一步 | [PROJECT_SNAPSHOT](PROJECT_SNAPSHOT.md) |
| 路線、產品 Gate 與資料來源優先序 | [Roadmap Hub](DEVELOPMENT_ROADMAP.md)、[產品方向／來源優先序 §11](PRODUCT_ROADMAP_POST_REFACTOR.md#11-data-source-roadmap)、[6M 工程順序](ROADMAP_6M_ENGINEERING.md) |
| North Star、原則與成功標準 | [System Vision](../01_architecture/system_vision_specification.md) |
| 長期 maturity／外部候選研究／舊工作 | [V2.1–V4.0](VERSION_ROADMAP_V2_1_TO_V4_0.md)、[外部候選研究藍圖](EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md)、[Legacy Carryover](LEGACY_ROADMAP_CARRYOVER.md) |
| 目前與未來架構 | [目前架構](../01_architecture/system_architecture.md)、[目標領域背景](../01_architecture/target_system_architecture.md)、[FINAL 目標實作設計](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) |
| 安裝與操作 | [安裝](../07_guides/INSTALL_GUIDE.md)、[快速開始](../07_guides/QUICK_START.md)、[完整 Manual](../07_guides/APPLICATION_MANUAL.md) |
| 文件治理與歷史目錄快照 | [結構規則](DOCUMENTATION_STRUCTURE.md)、[Coverage Map](DOC_COVERAGE_MAP.md)、[2026-10-09 整理狀態矩陣](DOCUMENTATION_STATUS_MATRIX_20261009.md)、[2026-10-06 全文件目錄快照](DOCUMENTATION_CATALOG_20261006.md) |
| 資料、保留與恢復 | [資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md)、[C 槽冷封存終態對照](../06_qa/C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md) |
| 知識圖與更新 | [Graphify 維護入口](DOCUMENTATION_GRAPH_GUIDE.md) |

## 領域導航

[核心](README.md)／[架構](../01_architecture/README.md)／[功能](../02_features/README.md)／[資料](../03_data/README.md)／[券商分點](../04_broker_branch/README.md)／[歷史 Phase](../05_phases/README.md)／[QA 收據](../06_qa/README.md)／[指南](../07_guides/README.md)／[技術](../08_technical/README.md)／[Agent](../agents/README.md)／[策略](../strategies/README.md)／[開發 plans/specs](../superpowers/README.md)／[Archive](../09_archive/README.md)。

根目錄 [README](../../README.md)、[PROJECT_NAVIGATION](../../PROJECT_NAVIGATION.md)、[PROJECT_INVENTORY](../../PROJECT_INVENTORY.md) 與 [AGENTS](../../AGENTS.md) 保留各自職責。PROJECT_NAVIGATION 的 2026-10-05 至 10-07 日期化更新記錄已移至[歷史摘錄](../09_archive/PROJECT_NAVIGATION_HISTORY_20261005_TO_20261007.md)；現況仍看 Snapshot。31 份 refactor task specs 與 FINAL 分冊是設計／執行契約，不等於完成證明。

## 必要調度與維運

[2026-10-09排程／automation修正與最新報告](../06_qa/BALDR_SCHEDULE_REMEDIATION_20261009.md)：21個Task設定回讀、Operational啟用、兩個prompt修正、稽核誤判修復與仍未解除的資料資格事項；共同操作見[全排程驗收runbook](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。

[2026-10-08 自然排程故障修正與驗證](../06_qa/BALDR_SCHEDULE_REPAIR_20261008.md)：保存該日排程修正範圍、驗證結果與限制；目前狀態以 Snapshot 為準。

[2026-10-07 排程故障修正與有限驗證](../06_qa/BALDR_SCHEDULE_REPAIR_20261007.md)：保存該日的故障修正與有限驗證證據；不取代較新的排程狀態。

[Windows／Codex 排程運維與搬機指南](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md) 提供任務用途、入口、依賴、時區、私有清冊與搬機驗收；[2026-10-06 排程稽核](../06_qa/BALDR_SCHEDULE_AUDIT_20261006.md) 保存該次唯讀稽核證據。

[Scheduled CMD／契約](../../scripts/scheduled/README.md)、[Evidence rehearsal](../07_guides/EVIDENCE_REHEARSAL_RUNBOOK.md)、[ML shadow inference 維運](../07_guides/ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md)、[模型 shadow runbook](../07_guides/HISTORICAL_ML_SHADOW_RUNBOOK.md) 與安裝／設定手冊是調度及維運文件入口；目前全排程唯讀查核見上方共用 Runbook，啟用狀態與驗收資格看 Manual、Snapshot 及具名 QA。

## 產品補完接續計畫

[Baldr 產品補完接續計畫（2026-10-06）](../superpowers/plans/baldr_product_completion_plan_20261006.md)：維護完整 P00–P14／M1–M3／F01–F23 範圍與驗收依賴，不是完成證明。checkpoint、恢復基線與驗收界線分見 [恢復開發 QA](../06_qa/BALDR_COMPLETION_RESUME_20261009.md) 及 [產品補完交接](../06_qa/BALDR_COMPLETION_HANDOFF_20261009.md)；目前狀態以 Snapshot 為準。

## 歷史與原始證據

[2026-09-22 目標架構草案封存](../09_archive/target_architecture_2026_09_22/README.md)：六份已被 FINAL 設計取代的提案及接續權威入口。歸檔來源 bytes／SHA 與引用核對見 [Coverage History Entry 124](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-124)。

[券商分點早期設計與實作記錄](../09_archive/broker_branch/README.md)：2025-12 至 2026-01 的初期設計、實作及解析／錯誤檢查記錄；現況回到券商分點目錄、系統架構與操作手冊。逐檔 bytes／SHA 與引用核對見 [Coverage History Entry 126](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-126)。

原本索引的日期化補充全文見 [歷史索引](../09_archive/DOCUMENTATION_INDEX_HISTORY_20261006.md)，舊入口紀錄見 [入口歷史](../09_archive/DOCUMENTATION_ENTRY_HISTORY_20261006.md)。[整理 manifest](../09_archive/DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md) 保存 old→new、原 SHA 與恢復規則。

[Qt MainWindow shutdown teardown 修正 QA（2026-09-15）](../09_archive/QT_SHUTDOWN_TEARDOWN_FIX_QA_2026_09_15.md)：MainWindow 關閉後的 bounded Qt teardown 證據；不代表 Native crash popup 根因或 SQLite inspector shutdown 問題已解。原 QA 路徑保留短導引，完整移動與 bytes/hash 記錄見 [Coverage History Entry 100](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-100)。

[Position Health calendar-cache 測試隔離 QA（2026-09-15）](../09_archive/POSITION_HEALTH_SOURCE_PROVIDER_CALENDAR_CACHE_ISOLATION_QA_2026_09_15.md)：保存以 isolated `tmp_path` fixture 修復測試時間相依性的原文；不代表 Position Health 正式 transition Gate 結案。QA 舊路徑與歷史 Catalog 引用保留導引，bytes/hash 見 [Coverage History Entry 101](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-101)。

[ML allocation Formal input readiness（2026-09-20，事件前快照）](../09_archive/ML_ALLOCATION_FORMAL_INPUT_READINESS_2026_09_20.md)：保存 9/21 前的 candidate-only 設定與當時缺件，不是 9/21 實際驗收；目前 Gate／狀態看 Snapshot、Gate 7 與 External Validation Register。原 QA 路徑保留導引，bytes/hash 見 [Coverage History Entry 102](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-102)。

[排程與週資料受託審查（2026-09-14，歷史）](../09_archive/SCHEDULED_OPERATIONS_OWNER_REVIEW_2026_09_14_HISTORY.md)：保存 `reviewed_with_follow_up` 與未通過正式採認的當日結論，不代表目前 scheduler 狀態或 CSV／SQLite 全量一致；現況看 Snapshot／近期排程 QA。原 QA 路徑保留導引，bytes/hash 見 [Coverage History Entry 103](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-103)。

[唯讀服務合作式取消 QA（2026-09-30，歷史）](../09_archive/READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md)：保留當次 125 passed／1 failed 與另一份 V5 acceptance 的分開結果，未改寫原始證據；raw pytest logs 為 ignored sidecar。現行契約看程式／測試，bytes/hash 見 [Coverage History Entry 104](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-104)。

[V4.2 每日推薦自動學習部署 QA（2026-09-13，歷史）](../09_archive/V4_2_DAILY_RECOMMENDATION_LEARNING_2026_09_13_HISTORY.md)：保留單一 task 註冊與 bounded run 證據，task 當時尚未執行，未取得正式 promotion／production credit。現況看 Snapshot／Gate 7，操作看 Manual；bytes/hash 見 [Coverage History Entry 105](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-105)。

[V4.2 C 線每日決策工作台 QA handoff（2026-09-12，歷史）](../09_archive/V4_2_C_DAILY_DECISION_WORKBENCH_QA_HANDOFF_2026_09_12_HISTORY.md)：保存該輪 bounded UI handoff 與驗證限制；目前流程看 [Manual Supplements](../07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md)，整體跨頁 [acceptance plan](../06_qa/CROSS_PAGE_DECISION_JOURNEY_ACCEPTANCE_PLAN_2026_09_15.md) 仍開放。原 QA 路徑保留導引，bytes／SHA 見 [Coverage History Entry 123](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-123)。

[Weekly Natural Evidence Review（2026-09-20，歷史）](../09_archive/WEEKLY_NATURAL_EVIDENCE_REVIEW_2026_09_20_HISTORY.md)：保存 9/14–20 週期與 9/21 唯讀觀測，分清 weekly collection、BankTaiwan capture 與 ML natural shadow，不代表成熟、promotion 或 human approval。現況看 Snapshot／Gate 7；bytes/hash 見 [Coverage History Entry 106](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-106)。

[V4 每日自然證據運行閉環 handoff（2026-09-12，歷史）](../09_archive/V4_DAILY_EVIDENCE_LOOP_HANDOFF_2026_09_12_HISTORY.md)：保存當時 maturity、Paper benchmark／fills 與 saved checkout 交接缺口；均為歷史未完成事項，不代表目前 Gate 已解除。現況看 Snapshot／Gate 7，操作看 Manual；原 QA 路徑保留導引，bytes／SHA 見 [Coverage History Entry 127](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-127)。
[Daily Decision Desk 初始 Spark execution plan（2026-06-15，歷史）](../09_archive/superpowers/plans/2026-06-15-daily-decision-desk-spark-execution-plan.md)：原始頂層 Tab 設計已被現行「市場探索 > 市場總覽」入口取代；Month 4 closure plan 保留結案摘要與尚未勾選的 Task 1–7。現行操作看 Manual §8、架構看 system architecture §4、狀態看 Snapshot；原路徑導引與 bytes／SHA 見 [Coverage History Entry 128](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-128)。

[BankTaiwan 研究型學習（2026-09-14，單日 bounded run）](../09_archive/README.md#2026-10-09-banktaiwan-2026-09-14-initial-shadow-run)：成本估算與營運 QA 保留為歷史快照；`retain_current`、自然成熟樣本 0，不代表 lane maturity 或 promotion。現況看 Snapshot／Gate 7，逐檔 bytes／SHA 見 [Coverage History Entry 120](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-120)。

[資料補齊驗收（2026-09-09，歷史）](../06_qa/DATA_COMPLETION_2026_09_09.md)：為延續既有交接引用，完整總驗收保留 QA 原路徑；封存副本、flows／TDCC 歷史收據見 [Archive 專區](../09_archive/README.md#data-completion-20260909) 與 [Coverage History Entry 122](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-122)。現況看 Snapshot／QA Data Governance。

[觀察清單分析與 ML 可見性驗收（2026-09-06，歷史）](../09_archive/WATCHLIST_ANALYSIS_ML_HANDOFF_2026_09_06_HISTORY.md)：保留當日 UI／分析與 `0/3` readiness inspection，非目前 ML 狀態或 promotion。現行操作／來源／Gate／狀態看 Manual／Architecture／Gate 7／Snapshot；bytes/hash 見 [Coverage History Entry 107](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-107)。

[三面向清查建議實作交接（2026-09-07，歷史）](../09_archive/THREE_PERSPECTIVE_IMPLEMENTATION_2026_09_07_HISTORY.md)：保留當時分析／ML／UI 實作驗收及未完成 Gate，不代表目前狀態。現況看 Snapshot／Gate 7／Manual；bytes/hash 見 [Coverage History Entry 108](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-108)。

`output/plans/` 與 `output/qa/` 是 ignored 本機需求／原始驗收證據，不因 ignored 即可刪。唯一 Danny Quant plan 原路徑 `output/plans/baldr_product_experience_plan_20261004.md` 保留原 bytes，另有本轮可還原快照；raw 失敗、JUnit 與 receipts 不重寫。正式摘要可放 QA，私人內容不能直接公開。


[M2施工與工程QA（2026-10-07）](../06_qa/BALDR_COMPLETION_M2_20261007.md)：受控研究根、長路徑產製與新程序重開、技術來源／封裝局部驗證及H20三日期保存來源旅程。原失敗與synthetic模型邊界明列；完整UI與新technical版本／candidate仍在施工，不能當完整產品或Native接受收據。

[Wave 2 舊 R008 SHA checkpoint（歷史）](../09_archive/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE2_CHECKPOINT.md)：只保留舊 SHA 的驗收快照；現行 Wave 2 結果見 [result_id checkpoint](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE2_RESULT_ID_CHECKPOINT.md)，不代表 C1、Wave 6 或整體重構通過。搬移前 bytes／SHA 與引用核對見 [Coverage History Entry 129](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-129)。
