# 文檔索引

> 2026-10-06 整理。本頁維護閱讀與文件位置；目前狀態只看 Snapshot，日期化測試數字只看原 QA receipt。

## 權威入口

Windows 雙擊入口、整個資料夾需求與外部設定：[PORTABLE_WINDOWS](../07_guides/PORTABLE_WINDOWS.md)。

| 問題 | 入口 |
|---|---|
| 目前狀態與下一步 | [PROJECT_SNAPSHOT](PROJECT_SNAPSHOT.md) |
| 路線與產品 Gate | [Roadmap Hub](DEVELOPMENT_ROADMAP.md)、[產品方向](PRODUCT_ROADMAP_POST_REFACTOR.md)、[6M 工程](ROADMAP_6M_ENGINEERING.md) |
| 長期 maturity／外部參考／舊工作 | [V2.1–V4.0](VERSION_ROADMAP_V2_1_TO_V4_0.md)、[外部藍圖](EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md)、[Legacy Carryover](LEGACY_ROADMAP_CARRYOVER.md) |
| 目前與未來架構 | [目前架構](../01_architecture/system_architecture.md)、[FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) |
| 安裝與操作 | [安裝](../07_guides/INSTALL_GUIDE.md)、[快速開始](../07_guides/QUICK_START.md)、[完整 Manual](../07_guides/APPLICATION_MANUAL.md) |
| 文件治理與全清單 | [結構規則](DOCUMENTATION_STRUCTURE.md)、[Coverage Map](DOC_COVERAGE_MAP.md)、[全文件目錄](DOCUMENTATION_CATALOG_20261006.md) |
| 資料與保留恢復 | [資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md) |
| 知識圖與更新 | [Graphify 維護入口](DOCUMENTATION_GRAPH_GUIDE.md) |

## 領域導航

[核心](README.md)／[架構](../01_architecture/README.md)／[功能](../02_features/README.md)／[資料](../03_data/README.md)／[券商分點](../04_broker_branch/README.md)／[歷史 Phase](../05_phases/README.md)／[QA 收據](../06_qa/README.md)／[指南](../07_guides/README.md)／[技術](../08_technical/README.md)／[Agent](../agents/README.md)／[策略](../strategies/README.md)／[開發 plans/specs](../superpowers/README.md)／[Archive](../09_archive/README.md)。

根目錄 [README](../../README.md)、[PROJECT_NAVIGATION](../../PROJECT_NAVIGATION.md)、[PROJECT_INVENTORY](../../PROJECT_INVENTORY.md) 與 [AGENTS](../../AGENTS.md) 保留各自職責。31 份 refactor task specs 與 FINAL 分冊是設計／執行契約，不等於完成證明。

## 必要調度與維運

[Windows／Codex 排程運維與搬機指南](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md) 提供任務用途、入口、依賴、時區、私有清冊與搬機驗收；[2026-10-06 排程稽核](../06_qa/BALDR_SCHEDULE_AUDIT_20261006.md) 保留模型替換未完成項與 Windows 唯讀證據。

[Scheduled CMD／契約](../../scripts/scheduled/README.md)、[日常 morning check](../07_guides/EVIDENCE_SCHEDULED_MORNING_CHECK.md)、[Evidence rehearsal](../07_guides/EVIDENCE_REHEARSAL_RUNBOOK.md)、[ML shadow inference 維運](../07_guides/ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md)、[模型 shadow runbook](../07_guides/HISTORICAL_ML_SHADOW_RUNBOOK.md) 與安裝／設定手冊保留為可完整調度系統的必要文件，不因包含排程或 ML 就當成 internal junk。啟用權限、正式來源與模型品質仍依 Manual／Snapshot／具名 receipt；可攜 exe 已交付，本輪沒有改 Task；操作見可攜指南。

## 產品補完接續計畫

[Baldr 產品補完接續計畫（2026-10-06）](../superpowers/plans/baldr_product_completion_plan_20261006.md)：對照唯一原始 Danny Quant 計畫、當前原碼與九個保留檔案，整理四用途、完整選股母體、ML／持倉研究、策略績效、排他分工及端到端驗收。使用者後續已授權 Luna Max 開發；工作區先提交為 `bf9207fb`，第 14 節追加 exe／Python 共用入口、設定與同版建置驗收。首波M1已交固定commit candidate並通過同版隔離比較，P01底層已驗但UI未接線；[首波QA](../06_qa/BALDR_COMPLETION_FIRST_WAVE_20261006.md)明列版本、失敗保留與未驗項，不代表全部功能完成；原計畫及既有 QA 證據均保留。

## 歷史與原始證據

[2026-09-22 目標架構草案封存](../09_archive/target_architecture_2026_09_22/README.md)：六份已被 FINAL 設計取代的提案及接續權威入口。歸檔來源 bytes／SHA 與引用核對見 [Coverage History Entry 124](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-124)。

原本索引的日期化補充全文見 [歷史索引](../09_archive/DOCUMENTATION_INDEX_HISTORY_20261006.md)，舊入口紀錄見 [入口歷史](../09_archive/DOCUMENTATION_ENTRY_HISTORY_20261006.md)。[整理 manifest](../09_archive/DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md) 保存 old→new、原 SHA 與恢復規則。

[Qt MainWindow shutdown teardown 修正 QA（2026-09-15）](../09_archive/QT_SHUTDOWN_TEARDOWN_FIX_QA_2026_09_15.md)：MainWindow 關閉後的 bounded Qt teardown 證據；不代表 Native crash popup 根因或 SQLite inspector shutdown 問題已解。原 QA 路徑保留短導引，完整移動與 bytes/hash 記錄見 [Coverage History Entry 100](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-100)。

[Position Health calendar-cache 測試隔離 QA（2026-09-15）](../09_archive/POSITION_HEALTH_SOURCE_PROVIDER_CALENDAR_CACHE_ISOLATION_QA_2026_09_15.md)：保存以 isolated `tmp_path` fixture 修復測試時間相依性的原文；不代表 Position Health 正式 transition Gate 結案。QA 舊路徑與歷史 Catalog 引用保留導引，bytes/hash 見 [Coverage History Entry 101](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-101)。

[ML allocation Formal input readiness（2026-09-20，事件前快照）](../09_archive/ML_ALLOCATION_FORMAL_INPUT_READINESS_2026_09_20.md)：保存 9/21 前的 candidate-only 設定與當時缺件，不是 9/21 實際驗收；目前 Gate／狀態看 Snapshot、Gate 7 與 External Validation Register。原 QA 路徑保留導引，bytes/hash 見 [Coverage History Entry 102](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-102)。

[排程與週資料受託審查（2026-09-14，歷史）](../09_archive/SCHEDULED_OPERATIONS_OWNER_REVIEW_2026_09_14_HISTORY.md)：保存 `reviewed_with_follow_up` 與未通過正式採認的當日結論，不代表目前 scheduler 狀態或 CSV／SQLite 全量一致；現況看 Snapshot／近期排程 QA。原 QA 路徑保留導引，bytes/hash 見 [Coverage History Entry 103](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-103)。

[唯讀服務合作式取消 QA（2026-09-30，歷史）](../09_archive/READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md)：保留當次 125 passed／1 failed 與另一份 V5 acceptance 的分開結果，未改寫原始證據；raw pytest logs 為 ignored sidecar。現行契約看程式／測試，bytes/hash 見 [Coverage History Entry 104](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-104)。

[V4.2 每日推薦自動學習部署 QA（2026-09-13，歷史）](../09_archive/V4_2_DAILY_RECOMMENDATION_LEARNING_2026_09_13_HISTORY.md)：保留單一 task 註冊與 bounded run 證據，task 當時尚未執行，未取得正式 promotion／production credit。現況看 Snapshot／Gate 7，操作看 Manual；bytes/hash 見 [Coverage History Entry 105](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-105)。

[V4.2 C 線每日決策工作台 QA handoff（2026-09-12，歷史）](../09_archive/V4_2_C_DAILY_DECISION_WORKBENCH_QA_HANDOFF_2026_09_12_HISTORY.md)：保存該輪 bounded UI handoff 與驗證限制；目前流程看 [Manual Supplements](../07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md)，整體跨頁 [acceptance plan](../06_qa/CROSS_PAGE_DECISION_JOURNEY_ACCEPTANCE_PLAN_2026_09_15.md) 仍開放。原 QA 路徑保留導引，bytes／SHA 見 [Coverage History Entry 123](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-123)。

[Weekly Natural Evidence Review（2026-09-20，歷史）](../09_archive/WEEKLY_NATURAL_EVIDENCE_REVIEW_2026_09_20_HISTORY.md)：保存 9/14–20 週期與 9/21 唯讀觀測，分清 weekly collection、BankTaiwan capture 與 ML natural shadow，不代表成熟、promotion 或 human approval。現況看 Snapshot／Gate 7；bytes/hash 見 [Coverage History Entry 106](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-106)。

[BankTaiwan 研究型學習（2026-09-14，單日 bounded run）](../09_archive/README.md#2026-10-09-banktaiwan-2026-09-14-initial-shadow-run)：成本估算與營運 QA 保留為歷史快照；`retain_current`、自然成熟樣本 0，不代表 lane maturity 或 promotion。現況看 Snapshot／Gate 7，逐檔 bytes／SHA 見 [Coverage History Entry 120](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-120)。

[資料補齊驗收（2026-09-09，歷史）](../06_qa/DATA_COMPLETION_2026_09_09.md)：為延續既有交接引用，完整總驗收保留 QA 原路徑；封存副本、flows／TDCC 歷史收據見 [Archive 專區](../09_archive/README.md#data-completion-20260909) 與 [Coverage History Entry 122](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-122)。現況看 Snapshot／QA Data Governance。

[觀察清單分析與 ML 可見性驗收（2026-09-06，歷史）](../09_archive/WATCHLIST_ANALYSIS_ML_HANDOFF_2026_09_06_HISTORY.md)：保留當日 UI／分析與 `0/3` readiness inspection，非目前 ML 狀態或 promotion。現行操作／來源／Gate／狀態看 Manual／Architecture／Gate 7／Snapshot；bytes/hash 見 [Coverage History Entry 107](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-107)。

[三面向清查建議實作交接（2026-09-07，歷史）](../09_archive/THREE_PERSPECTIVE_IMPLEMENTATION_2026_09_07_HISTORY.md)：保留當時分析／ML／UI 實作驗收及未完成 Gate，不代表目前狀態。現況看 Snapshot／Gate 7／Manual；bytes/hash 見 [Coverage History Entry 108](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-108)。

`output/plans/` 與 `output/qa/` 是 ignored 本機需求／原始驗收證據，不因 ignored 即可刪。唯一 Danny Quant plan 原路徑 `output/plans/baldr_product_experience_plan_20261004.md` 保留原 bytes，另有本轮可還原快照；raw 失敗、JUnit 與 receipts 不重寫。正式摘要可放 QA，私人內容不能直接公開。


[M2施工與工程QA（2026-10-07）](../06_qa/BALDR_COMPLETION_M2_20261007.md)：受控研究根、長路徑產製與新程序重開、技術來源／封裝局部驗證及H20三日期保存來源旅程。原失敗與synthetic模型邊界明列；完整UI與新technical版本／candidate仍在施工，不能當完整產品或Native接受收據。
