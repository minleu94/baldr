# 核心文檔目錄

> **核心文檔（必讀）**

本目錄包含系統的核心文檔。專案目前採用 Scoped SSOT：不同主題由不同文件負責，不再由單一 Roadmap 承擔所有權威。

## 📄 文檔列表

- **`PROJECT_SNAPSHOT.md`** ⭐ **開場必讀**
  - 專案快照（開場 30 秒狀態）
  - 目前狀態、本週優先事項、高風險區的權威入口

- **`ROADMAP_6M_ENGINEERING.md`**
  - 未來 6 個月可執行工程路線
  - 把 Post-Refactor Product Roadmap 轉成 Gate、交付物、依賴、測試、禁止事項與 Exit Criteria
  - 月份是相對工程順序；目前進度以 Snapshot 為準

- **`PRODUCT_ROADMAP_POST_REFACTOR.md`**
  - 安全重構完成後的產品方向權威
  - 定義 bounded investment advice、Guided / Professional Mode、Portfolio Advice、Position Health / Exit、Evidence、Data、ML 與 signal pruning 的產品演進

- **`VERSION_ROADMAP_V2_1_TO_V4_0.md`**
  - V2.0 之後的長期產品成熟度與版本階梯
  - V2.x 聚焦 Daily Advice / Evidence / Data / Portfolio foundation；V3.x 聚焦 effectiveness / pruning / ML shadow；V4.0 需長期 evidence 支持
  - 2026-09-07 的 V4 執行計畫已移至 [`09_archive`](../09_archive/V4_COMPLETION_PLAN_2026_09_07_HISTORY.md)；封存內容截至 2026-09-10 仍標示進行中，舊核心路徑僅作導引

- **`EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md`**
  - 外部專案參考、資料源候選與 V1.8 至 V2.0 歷史版本形狀
  - 作為研究參考，不定義目前產品方向或工程交付順序

- **`DEVELOPMENT_ROADMAP.md`**
  - Roadmap 導覽 Hub
  - 只連結 Snapshot、產品方向、6M 工程路線、成熟度、外部參考、Legacy、架構、手冊與歷史入口
  - 不複製 Next、目前進度或風險摘要，也不保存完整歷史 Done

- **`LEGACY_ROADMAP_CARRYOVER.md`**
  - 舊 Roadmap 項目的處置與移交證據
  - 已完成或取消項目記錄處置；移交項目連到新版工程路線，舊月份標籤不代表目前排程

- **`DOCUMENTATION_INDEX.md`**
  - 文檔索引（文檔結構的 Single Source of Truth）
  - 完整的文檔導航和分類

- **`DOC_COVERAGE_MAP.md`**
  - 現行權威邊界、文件同步矩陣與 DoD
  - 逐批整理／歸檔沿革另見 [Coverage History](../09_archive/DOC_COVERAGE_HISTORY_2026.md)

- **`DOCUMENTATION_STRUCTURE.md`**
  - 文檔生命週期、歸檔與刪除規則
  - 新增、搬移或整理 Markdown 前必讀

> 根目錄 `README.md` 是使用者導向入口；Agent / 開發者快速上下文請看 repo 根目錄 `AGENT_CONTEXT.md`。本目錄只保留核心權威文件與文件治理規則。

## Scoped SSOT 導航

| 想找的內容 | 權威文件 |
|---|---|
| 現在狀態、本週優先事項、目前 Gate、高風險區 | `PROJECT_SNAPSHOT.md` |
| North Star、Product Principles、Bounded Advice、Evidence、Success Levels、Non-goals | `../01_architecture/system_vision_specification.md` |
| 重構完成後產品方向、投資問題與產品能力演進 | `PRODUCT_ROADMAP_POST_REFACTOR.md` |
| 未來六個月工程 Gate、deliverables、dependencies、tests、Exit Criteria | `ROADMAP_6M_ENGINEERING.md` |
| V1.1-V2.0 歷史版本 | [`../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md`](../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md) |
| V2.1-V4.0 長期產品成熟度 | `VERSION_ROADMAP_V2_1_TO_V4_0.md` |
| 外部專案與資料源候選參考 | `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` |
| 舊 Roadmap 項目處置 | `LEGACY_ROADMAP_CARRYOVER.md`；目前工程順序仍看 6M Roadmap |
| 現在真實架構 | `../01_architecture/system_architecture.md` |
| Transitional / Target Architecture | `../01_architecture/target_system_architecture.md` |
| 已完成的行為不變安全重構 | `../09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md`（歷史／rollback companion） |
| 現在已實作的操作流程 | `../07_guides/README.md` 的手冊章節地圖與 `../07_guides/APPLICATION_MANUAL.md` 相關章節 |
| 文件位置 | `DOCUMENTATION_INDEX.md` |

## 🔗 相關目錄

- `../01_architecture/` - 架構文檔
- `../02_features/` - 功能文檔
- `../03_data/` - 數據相關文檔
- `../07_guides/` - 指南文檔

## 判讀順序

1. 先讀 `PROJECT_SNAPSHOT.md` 取得目前狀態。
2. 若要理解產品為何存在與安全邊界，讀 `../01_architecture/system_vision_specification.md`。
3. 若要規劃重構完成後的產品方向，讀 `PRODUCT_ROADMAP_POST_REFACTOR.md`。
4. 若要執行未來六個月工程，讀 `ROADMAP_6M_ENGINEERING.md`。
5. 若要追溯 V1.1-V2.0 歷史，讀 archive；V2.1-V4.0 的成熟度標準讀 `VERSION_ROADMAP_V2_1_TO_V4_0.md`；外部參考只作研究候選。
6. 若要確認目前或目標架構，分別讀 `system_architecture.md` 與 `target_system_architecture.md`。
7. 若要追溯已完成的安全重構，讀 `../09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md`；新的重構工作仍以目前架構與當期核准計畫為準。
8. 若要操作目前系統，先按 `../07_guides/README.md` 的章節地圖讀取 Manual 相關章節。
9. 若要找文件位置，讀 `DOCUMENTATION_INDEX.md`。
10. 若要追溯舊 Phase 或歷史 Done，讀 archive；Historical 文件不作目前狀態依據。

## 更新記錄

- 2026-10-08：補入外部參考與 Legacy 入口，澄清 Hub 僅導覽、Legacy 月份為歷史標籤，並說明 Coverage Map 同時保存規則與封存證據。
- 2026-07-11：加入 Post-Refactor Product Roadmap 與 Target Architecture 入口，重整 Scoped SSOT 導航與判讀順序，明確分開產品、工程、版本、Current / Target Architecture 與 Safe Refactor 權威。

