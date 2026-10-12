# 核心文件導覽

`docs/00_core/` 集中目前狀態、產品與工程方向，以及文件治理入口。本頁只負責導覽；各主題的權威文件互不取代。若內容看起來衝突，先按下表回到對應權威。

面向使用者的專案說明看[根目錄 README](../../README.md)；開發者／Agent 快速上下文看 [AGENT_CONTEXT](../../AGENT_CONTEXT.md) 與根目錄 [AGENTS](../../AGENTS.md)。

## 核心權威

| 想了解 | 權威文件 | 用途 |
|---|---|---|
| 目前狀態、優先事項、Gate 與風險 | [PROJECT_SNAPSHOT](PROJECT_SNAPSHOT.md) | 唯一目前狀態入口；不從歷史 QA 推定現況。 |
| 產品問題與能力演進 | [PRODUCT_ROADMAP_POST_REFACTOR](PRODUCT_ROADMAP_POST_REFACTOR.md) | 產品方向與產品 Gate；不負責目前進度或工程 checklist。 |
| 未來六個月工程交付 | [ROADMAP_6M_ENGINEERING](ROADMAP_6M_ENGINEERING.md) | Gate、順序、依賴與驗收；實際進度回到 Snapshot。 |
| V2.1–V4.0 成熟度 | [VERSION_ROADMAP_V2_1_TO_V4_0](VERSION_ROADMAP_V2_1_TO_V4_0.md) | 長期產品成熟度標準，不代表工程順序或目前完成狀態。 |
| 外部參考與 V1.8–V2.0 歷史版本形狀 | [EXTERNAL_REFERENCE_VERSION_BLUEPRINT](EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md) | 研究候選與歷史背景，不決定現行優先序。 |
| 舊 Roadmap 項目處置 | [LEGACY_ROADMAP_CARRYOVER](LEGACY_ROADMAP_CARRYOVER.md) | 保留舊項目唯一處置與新版移交位置；新工程順序看 6M Roadmap。 |
| 不確定該讀哪份 Roadmap | [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md) | 導覽 Hub，不複製狀態、風險或歷史 Done。 |
| 開發線路、演進歷史與迴圈狀態 | [DEVELOPMENT_LINE_EVOLUTION_MATRIX_20261011](DEVELOPMENT_LINE_EVOLUTION_MATRIX_20261011.md) | 將產品／工程 Gate、資料／ML／排程 evidence 與待核問題映射成線路索引；不取代 Snapshot。 |
| 文件位置與分類 | [DOCUMENTATION_INDEX](DOCUMENTATION_INDEX.md) | 導航入口，不是狀態或架構權威。 |
| 文件同步責任與 DoD | [DOC_COVERAGE_MAP](DOC_COVERAGE_MAP.md) | 現行權威邊界、跨文件同步矩陣與完成條件。 |
| 文件生命週期與歸檔規則 | [DOCUMENTATION_STRUCTURE](DOCUMENTATION_STRUCTURE.md) | Active、Historical、QA evidence 與歸檔判準。 |

## 架構、操作與歷史

| 主題 | 閱讀入口 |
|---|---|
| 產品 North Star 與安全原則 | [System Vision](../01_architecture/system_vision_specification.md) |
| 目前系統架構 | [System Architecture](../01_architecture/system_architecture.md) |
| 目標領域背景 | [Target System Architecture](../01_architecture/target_system_architecture.md) |
| 目標實作設計 | [Final Target Architecture](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)；這是目標設計，不代表已實作。 |
| 系統操作 | [Application Manual](../07_guides/APPLICATION_MANUAL.md)；章節地圖在 [Guides README](../07_guides/README.md)。 |
| V1.1–V2.0 歷史版本 | [Archive 原文](../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md) |
| V4 收尾計畫快照 | [Archive 原文](../09_archive/V4_COMPLETION_PLAN_2026_09_07_HISTORY.md)；只反映截至 2026-09-10 的計畫狀態。 |
| 已完成安全重構與 rollback 參考 | [Safe Refactoring Master Report](../09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md)；新工作依目前架構與核准計畫。 |
| 文件整理／歸檔沿革 | [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)；逐批來源、去向、雜湊與替代入口。 |

## 快速閱讀順序

1. 先讀 [PROJECT_SNAPSHOT](PROJECT_SNAPSHOT.md) 了解目前狀態。
2. 依問題選產品方向、六個月工程路線或長期成熟度；不確定時從 [Roadmap Hub](DEVELOPMENT_ROADMAP.md) 進入。
3. 核對目前實作看 System Architecture；規劃目標設計看 Final Target Architecture；操作系統看 Application Manual。
4. 找文件位置看 Index；判斷更新／歸檔責任看 Coverage Map 與 Documentation Structure；追溯已封存內容看 Archive。

## 目錄入口

專項文件由各目錄 README 導覽；日期化 QA 不代表目前狀態，歷史 Archive 也不作現況依據。

| 領域 | 導覽 | 領域 | 導覽 |
|---|---|---|---|
| 架構 | [01_architecture](../01_architecture/README.md) | 功能 | [02_features](../02_features/README.md) |
| 資料 | [03_data](../03_data/README.md) | 券商分點 | [04_broker_branch](../04_broker_branch/README.md) |
| 歷史 Phase | [05_phases](../05_phases/README.md) | QA | [06_qa](../06_qa/README.md) |
| 使用指南 | [07_guides](../07_guides/README.md) | 技術備忘 | [08_technical](../08_technical/README.md) |
| 歷史封存 | [09_archive](../09_archive/README.md) |  |  |

## 更新記錄

- 2026-10-09：合併重複文件清單、Scoped SSOT 表格與判讀順序，保留各權威原文、歷史入口與領域導覽。
- 2026-10-08：補入外部參考與 Legacy 入口，澄清 Roadmap Hub 與 Coverage Map 的責任。
- 2026-07-11：加入 Post-Refactor Product Roadmap 與 Target Architecture 導覽。
