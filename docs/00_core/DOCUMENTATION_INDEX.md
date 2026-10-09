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

原本索引的日期化補充全文見 [歷史索引](../09_archive/DOCUMENTATION_INDEX_HISTORY_20261006.md)，舊入口紀錄見 [入口歷史](../09_archive/DOCUMENTATION_ENTRY_HISTORY_20261006.md)。[整理 manifest](../09_archive/DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md) 保存 old→new、原 SHA 與恢復規則。

[Qt MainWindow shutdown teardown 修正 QA（2026-09-15）](../09_archive/QT_SHUTDOWN_TEARDOWN_FIX_QA_2026_09_15.md)：MainWindow 關閉後的 bounded Qt teardown 證據；不代表 Native crash popup 根因或 SQLite inspector shutdown 問題已解。原 QA 路徑保留短導引，完整移動與 bytes/hash 記錄見 [Coverage History Entry 100](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-100)。

`output/plans/` 與 `output/qa/` 是 ignored 本機需求／原始驗收證據，不因 ignored 即可刪。唯一 Danny Quant plan 原路徑 `output/plans/baldr_product_experience_plan_20261004.md` 保留原 bytes，另有本轮可還原快照；raw 失敗、JUnit 與 receipts 不重寫。正式摘要可放 QA，私人內容不能直接公開。


[M2施工與工程QA（2026-10-07）](../06_qa/BALDR_COMPLETION_M2_20261007.md)：受控研究根、長路徑產製與新程序重開、技術來源／封裝局部驗證及H20三日期保存來源旅程。原失敗與synthetic模型邊界明列；完整UI與新technical版本／candidate仍在施工，不能當完整產品或Native接受收據。
