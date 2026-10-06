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

[Scheduled CMD／契約](../../scripts/scheduled/README.md)、[日常 morning check](../07_guides/EVIDENCE_SCHEDULED_MORNING_CHECK.md)、[Evidence rehearsal](../07_guides/EVIDENCE_REHEARSAL_RUNBOOK.md)、[ML shadow inference 維運](../07_guides/ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md)、[模型 shadow runbook](../07_guides/HISTORICAL_ML_SHADOW_RUNBOOK.md) 與安裝／設定手冊保留為可完整調度系統的必要文件，不因包含排程或 ML 就當成 internal junk。啟用權限、正式來源與模型品質仍依 Manual／Snapshot／具名 receipt；可攜 exe 已交付，本輪沒有改 Task；操作見可攜指南。

## 歷史與原始證據

原本索引的日期化補充全文見 [歷史索引](../09_archive/DOCUMENTATION_INDEX_HISTORY_20261006.md)，舊入口紀錄見 [入口歷史](../09_archive/DOCUMENTATION_ENTRY_HISTORY_20261006.md)。[整理 manifest](../09_archive/DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md) 保存 old→new、原 SHA 與恢復規則。

`output/plans/` 與 `output/qa/` 是 ignored 本機需求／原始驗收證據，不因 ignored 即可刪。唯一 Danny Quant plan 原路徑 `output/plans/baldr_product_experience_plan_20261004.md` 保留原 bytes，另有本轮可還原快照；raw 失敗、JUnit 與 receipts 不重寫。正式摘要可放 QA，私人內容不能直接公開。
