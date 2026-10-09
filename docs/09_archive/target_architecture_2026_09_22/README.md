# 2026-09-22 目標架構草案封存

本目錄保存六份已被同批 `FINAL_*` 設計取代的目標架構草案。它們保留當時的方案、假設與遷移想法，供決策追溯；不能作為目前設計權威、目前實作狀態或新工作授權。

封存副本只調整了相對 Markdown 連結，讓它們在本目錄仍可導向 FINAL 權威與同批歷史草案。歸檔前原件的位元組數與 SHA-256、引用檢查及生命週期決定，見 [Coverage History Entry 124](../DOC_COVERAGE_HISTORY_2026.md#coverage-entry-124)。架構區原路徑保留相容導引，仍可由舊連結抵達封存原文。

| 封存草案 | 現行設計接續文件 |
|---|---|
| [TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md) | [FINAL_TARGET_ARCHITECTURE.md](../../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) |
| [TARGET_DATA_FLOW.md](TARGET_DATA_FLOW.md) | [FINAL_DATA_FLOW.md](../../01_architecture/target_architecture_2026_09_22/FINAL_DATA_FLOW.md) |
| [ML_COMPATIBILITY_PLAN.md](ML_COMPATIBILITY_PLAN.md) | [FINAL_ML_COMPATIBILITY_CONTRACT.md](../../01_architecture/target_architecture_2026_09_22/FINAL_ML_COMPATIBILITY_CONTRACT.md) |
| [ARCHITECTURE_INVARIANTS.md](ARCHITECTURE_INVARIANTS.md) | [FINAL_ARCHITECTURE_INVARIANTS.md](../../01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md) |
| [EXTENSIBILITY_TEST.md](EXTENSIBILITY_TEST.md) | [FINAL_EXTENSIBILITY_MODEL.md](../../01_architecture/target_architecture_2026_09_22/FINAL_EXTENSIBILITY_MODEL.md) |
| [MIGRATION_STRATEGY.md](MIGRATION_STRATEGY.md) | [FINAL_MIGRATION_SEQUENCE.md](../../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md) |

評估、紅隊審查與必要變更等 FINAL 設計輸入仍保留在[現行架構套件](../../01_architecture/target_architecture_2026_09_22/README.md)。仍開放的工作與驗收狀態以 [PROJECT_SNAPSHOT](../../00_core/PROJECT_SNAPSHOT.md)、FINAL migration sequence 及具名 QA 為準；本次封存不代表遷移 Gate 結案。
