# 文件閱讀與查找入口

首次接觸專案先看[產品介紹](../../README.md)。本頁按問題帶往現行正文；索引、QA或歷史文件不代替對應權威。

## 理解或使用產品

| 問題 | 入口 |
|---|---|
| 能做什麼、日常從哪裡開始 | [README](../../README.md)、[快速開始](../07_guides/QUICK_START.md) |
| 現在有哪些入口與限制 | [Snapshot](PROJECT_SNAPSHOT.md) |
| 產品目標與成立條件 | [Product Roadmap](PRODUCT_ROADMAP_POST_REFACTOR.md)、[願景](../01_architecture/system_vision_specification.md) |
| 系統如何組成 | [目前架構](../01_architecture/system_architecture.md)、[主題分冊](../01_architecture/current/README.md) |
| 完整操作與結果判讀 | [手冊](../07_guides/APPLICATION_MANUAL.md)、[指南](../07_guides/README.md) |
| 首次安裝或換電腦 | [Prompt](../07_guides/FIRST_INSTALL_PROMPT.md)、[Runbook](../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md)、[Windows可攜版](../07_guides/PORTABLE_WINDOWS.md) |

## 開發、驗證與維護

| 問題 | 入口 |
|---|---|
| 修改功能該找哪裡 | [功能導航](../../PROJECT_NAVIGATION.md)、[功能關聯地圖](FEATURE_DOCUMENT_MAP.json) |
| 任務如何選角色與交付 | [角色路由](../agents/skills_registry.md)、[產品變更流程](PRODUCT_CHANGE_WORKFLOW.md) |
| 任務閱讀範圍、Context／程式追溯與現行清冊 | [任務上下文](PRODUCT_CHANGE_WORKFLOW.md#任務上下文與漸進閱讀)、[Issue register](DOCUMENT_GOVERNANCE_ISSUES.json) |
| 各 Roadmap 的責任 | [Hub](DEVELOPMENT_ROADMAP.md)、[6M工程](ROADMAP_6M_ENGINEERING.md)、[長期maturity](VERSION_ROADMAP_V2_1_TO_V4_0.md) |
| 目標package、契約與遷移設計 | [Target背景](../01_architecture/target_system_architecture.md)、[FINAL設計](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) |
| 資料來源、保存與恢復 | [資料專區](../03_data/README.md)、[資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md) |
| 排程與搬機 | [操作／搬機](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)、[唯讀稽核](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)、[wrapper入口](../../scripts/scheduled/README.md) |
| 測試與驗收證據 | [QA索引](../06_qa/README.md)、[測試指南](../07_guides/tests_readme.md) |
| 程式規模、產品落差與外部專案比較 | [2026-10-12 研究基線](../09_archive/product_research_baseline_20261012/README.md)：重構前沿用，按影響增量確認 |
| 文件同步與處置 | [Coverage](DOC_COVERAGE_MAP.md)、[生命週期](DOCUMENTATION_STRUCTURE.md) |

<a id="必要調度與維運"></a>

排程與搬機先依[操作／搬機指南](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)及[唯讀稽核 Runbook](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)處理；日期化 remediation 與驗收收據由 [Operations Testing QA Index](../06_qa/OPERATIONS_TESTING_QA_INDEX.md) 導覽。Task 狀態或 exit code 不代替產物及 consumer readback。

## 領域導航

[核心](README.md)／[架構](../01_architecture/README.md)／[功能](../02_features/README.md)／[資料](../03_data/README.md)／[券商分點](../04_broker_branch/README.md)／[歷史Phase](../05_phases/README.md)／[QA](../06_qa/README.md)／[指南](../07_guides/README.md)／[技術](../08_technical/README.md)／[Agent](../agents/README.md)／[策略](../strategies/README.md)／[開發plans/specs](../superpowers/README.md)／[Archive](../09_archive/README.md)。

## 歷史與查證

- 本輪整理：[處置、原件與恢復](../09_archive/documentation_productization_20261012/README.md)、[驗收](../06_qa/DOCUMENTATION_PRODUCTIZATION_ACCEPTANCE_20261012.md)。
- 之前全庫EOF覆核：[日期化治理矩陣](DOCUMENT_GOVERNANCE_STATUS_MATRIX_20261011.md)及[其manifest](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)。它們固定於原治理基線，不能當本次變更後的新全庫指紋。
- 舊目錄：[歷史快照](DOCUMENTATION_CATALOG_20261006.md)，舊工作處置：[Legacy Carryover](LEGACY_ROADMAP_CARRYOVER.md)。
- 圖譜是定位輔助：[Graphify維護](DOCUMENTATION_GRAPH_GUIDE.md)。舊節點或圖譜邊不是功能驗收證據。

每份專項文件沿領域README／主題索引查找；中央入口不複製逐輪收據，也不要求一次讀全部文件。
