# 文檔索引

本索引只指向主題權威與目錄入口，不複製 QA 收據、測試數字或目前狀態。判讀衝突時使用下列 Scoped SSOT；日期化驗收內容保留於各自 receipt。

- 原產品計畫階段 0 首包：[來源能力矩陣](../06_qa/PRODUCT_STAGE01_SOURCE_MATRIX_20261005.md)、[效能基線與下一包依賴](../06_qa/PRODUCT_STAGE01_PERFORMANCE_BASELINE_20261005.md)。

## 權威入口

| 主題                     | 權威                                                                                                          |
| ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| 目前狀態、本週優先事項與高風險區       | [PROJECT_SNAPSHOT](PROJECT_SNAPSHOT.md)                                                                     |
| 產品方向、產品 Gate、Non-goals | [PRODUCT_ROADMAP_POST_REFACTOR](PRODUCT_ROADMAP_POST_REFACTOR.md)                                           |
| 六個月工程里程碑與驗收            | [ROADMAP_6M_ENGINEERING](ROADMAP_6M_ENGINEERING.md)                                                         |
| Roadmap 導覽             | [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md)                                                               |
| V2.1–V4.0 長期成熟度        | [VERSION_ROADMAP_V2_1_TO_V4_0](VERSION_ROADMAP_V2_1_TO_V4_0.md)                                             |
| 舊工作移交                  | [LEGACY_ROADMAP_CARRYOVER](LEGACY_ROADMAP_CARRYOVER.md)                                                     |
| 外部參考與 V1.5–V2.0 版本形狀   | [EXTERNAL_REFERENCE_VERSION_BLUEPRINT](EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md)                             |
| 目前架構、模組邊界與資料流          | [system_architecture](../01_architecture/system_architecture.md)                                            |
| 目標架構                   | [FINAL_TARGET_ARCHITECTURE](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) |
| 使用者操作、安全與排錯            | [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)                                                    |
| 文件覆蓋與生命週期              | [DOC_COVERAGE_MAP](DOC_COVERAGE_MAP.md)、[DOCUMENTATION_STRUCTURE](DOCUMENTATION_STRUCTURE.md)               |

## 其他正式入口

- 四用途既有功能的有限工程缺口、Luna Max 分工與當次驗收：[Astra 工程收尾](../06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。是否完成以該文件最後接受與 Snapshot 為準。

- 理想目標架構與 Current → Target 演進：[target_system_architecture.md](../01_architecture/target_system_architecture.md)
- Formal input readiness 最新查核：[FORMAL_INPUT_READINESS_REFRESH_2026_08_30.md](../06_qa/FORMAL_INPUT_READINESS_REFRESH_2026_08_30.md)
- 2026-09-29 跨工作區 UI 版面、捲動與幾何驗收（六格 MainWindow offscreen 矩陣通過）：[UI_LAYOUT_AUDIT_20260929.md](../06_qa/UI_LAYOUT_AUDIT_20260929.md)
- 2026-09-30 七項排程問題修復、Task identity、真實 Quick／freshness receipts 與尚存資料缺口：[SCHEDULED_OPERATIONS_REPAIR_20260930.md](../06_qa/SCHEDULED_OPERATIONS_REPAIR_20260930.md)
- 2026-09-30 唯讀服務合作式取消與 repository contract 驗證：[READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md](../06_qa/READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md)
- 2026-10-01 Gemini ML revision-aware rebuild 交接與建置證據（獨立整合驗收另列）：[ML_REVISION_AWARE_REBUILD_EXECUTION_PLAN_20261001.md](../06_qa/ML_REVISION_AWARE_REBUILD_EXECUTION_PLAN_20261001.md)

- 2026-10-02 三階段整合修復、排程／automation 實際設定與受控執行驗收：[INTEGRATION_REPAIR_ACCEPTANCE_20261002.md](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)
- 2026-10-03 weekly controller、canonical locator、child readback 與 partial／review 判讀：[APPLICATION_MANUAL §2026-10-03 週度研究採集與讀回](../07_guides/APPLICATION_MANUAL.md#2026-10-03-週度研究採集與讀回)

## 領域目錄

- [架構文件](../01_architecture/README.md)：現況架構、target 導覽與系統設計。31 個 refactor task specs 是執行契約，不表示完成；實際狀態以 Snapshot 與 QA receipts 為準。
- FINAL 目標架構規範：[資料流](../01_architecture/target_architecture_2026_09_22/FINAL_DATA_FLOW.md)、[擴充模型](../01_architecture/target_architecture_2026_09_22/FINAL_EXTENSIBILITY_MODEL.md)、[ML 相容契約](../01_architecture/target_architecture_2026_09_22/FINAL_ML_COMPATIBILITY_CONTRACT.md)、[架構不變條件](../01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md)、[遷移順序](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md)。
- [功能文件](../02_features/README.md)、[資料文件](../03_data/README.md)、[券商分點文件](../04_broker_branch/README.md)、[歷史 Phase](../05_phases/README.md)、[QA receipts 與主題入口](../06_qa/README.md)、[操作指南](../07_guides/README.md)、[技術備忘](../08_technical/README.md)。
- [Agent 規範](../agents/README.md)、[策略文件](../strategies/README.md)、[Superpowers 設計與執行追溯](../superpowers/README.md)、[歷史封存](../09_archive/README.md)。
- 根目錄導覽：[README](../../README.md)、[PROJECT_NAVIGATION](../../PROJECT_NAVIGATION.md)、[PROJECT_INVENTORY](../../PROJECT_INVENTORY.md)、Codex 指令入口 [AGENTS.md](../../AGENTS.md)。

Archive、QA receipt、FINAL 設計分冊及 31 份 task specs 仍保留原文件；本索引不重述其結果或狀態。

整理前的日期化摘要與詳細分類保存在 [歷史索引](../09_archive/DOCUMENTATION_INDEX_HISTORY_2026_09_27.md)，只作文件演進追溯。
