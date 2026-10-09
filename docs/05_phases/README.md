# 歷史 Phase 與研究 SOP 文檔目錄

> **狀態**：Historical / Reference。
> **最後整理**：2026-10-08（僅校正現行入口與 Roadmap Hub 職責）。
> **判讀規則**：本目錄保留 Phase 時期的設計、驗收與研究 SOP 脈絡，不作為目前 roadmap、目前完成狀態或下一步優先順序依據。

目前專案已改採 Scoped SSOT：

- 目前狀態、本週優先事項與高風險區看 `../00_core/PROJECT_SNAPSHOT.md`。
- 未來 6 個月工程路線看 `../00_core/ROADMAP_6M_ENGINEERING.md`。
- V1.1 至 V2.0 已完成版本演進見 [`../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md`](../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md)，僅作歷史追溯。
- 架構與模組邊界看 `../01_architecture/system_architecture.md`。
- 實際操作方式看 `../07_guides/APPLICATION_MANUAL.md`。

本目錄作為逐檔判讀的歷史資料入口保留。目前核實到的 Active 文件直接引用只有 [`STRATEGY_DESIGN_SPECIFICATION.md`](../02_features/STRATEGY_DESIGN_SPECIFICATION.md) 連到 [`PHASE2_ARCHITECTURE.md`](PHASE2_ARCHITECTURE.md)。其餘文件暫留供追溯，是否搬入 `09_archive/` 依各文件的引用、證據與歷史價值逐檔判斷；沒有直接連結不等於可以刪除。原文中的下一步、進行中、Gate 或階段描述若與核心權威文件衝突，以核心權威文件為準。

## 文檔列表與目前處置

| 文件 | 目前處置 | 用途 |
|---|---|---|
| [PHASE2_ARCHITECTURE.md](PHASE2_ARCHITECTURE.md) | 保留為 Historical / Reference | Phase 2 策略架構設計追溯；目前有一筆 Active 直接引用。 |
| [PHASE2_STRATEGY_LIBRARY.md](PHASE2_STRATEGY_LIBRARY.md) | 保留為 Historical / Reference | Phase 2 策略資料庫設計追溯。 |
| [PHASE_2A_DATA_SOURCES_AUDIT.md](PHASE_2A_DATA_SOURCES_AUDIT.md) | 保留為 Historical / Reference | CSV-first 到 DB-first 過渡盤點；目前資料架構以 [system architecture](../01_architecture/system_architecture.md) 與 `../03_data/` 文件為準。 |
| [PHASE2_5_COMPLETION_STATUS.md](PHASE2_5_COMPLETION_STATUS.md) | 保留為 Historical / Reference | Phase 2.5 完成狀態追溯；fixed / quantile 現況以 Snapshot、6M Roadmap 與 QA 報告為準。 |
| [PHASE3_3B_RESEARCH_DESIGN.md](PHASE3_3B_RESEARCH_DESIGN.md) | 保留為 Historical / Reference | Research Lab / Promote 早期設計脈絡；目前 Research Run Registry / lifecycle gate 以核心文件與架構文件為準。 |
| [EPIC2_MVP2_ARCHITECTURE_DESIGN.md](EPIC2_MVP2_ARCHITECTURE_DESIGN.md) | 保留為 Historical / Reference | 過擬合風險提示早期架構設計。 |
| [EPIC2_MVP2_IMPLEMENTATION_CHECKLIST.md](EPIC2_MVP2_IMPLEMENTATION_CHECKLIST.md) | 保留為 Historical / Reference | 過擬合風險提示實作 checklist 追溯。 |
| [PHASE4_PORTFOLIO_DESIGN.md](PHASE4_PORTFOLIO_DESIGN.md) | 保留為 Historical / Reference | Portfolio MVP 初始設計；目前 Portfolio / lifecycle 狀態以 Snapshot、Architecture 與 Manual 為準。 |
| [PHASE4_STARTUP_SUMMARY.md](PHASE4_STARTUP_SUMMARY.md) | 保留為 Historical / Reference | Phase 4 啟動摘要追溯。 |
| [phase3_5_research/README.md](phase3_5_research/README.md) | 保留為 Historical SOP / Reference | 研究流程、指標判讀與 Phase 4 entry gate 的歷史文件目錄；若要成為日常操作規範，需另行改寫到 `../07_guides/` 或 `../02_features/`。 |

已歸檔的相關文件：

- [PHASE_3_3B_IMPLEMENTATION_PLAN.md](../09_archive/PHASE_3_3B_IMPLEMENTATION_PLAN.md)：Phase 3.3b 實施規劃，已移至歸檔目錄並只作歷史追溯。

## 📁 子目錄

- [phase3_5_research/README.md](phase3_5_research/README.md) - Phase 3.5 歷史文件索引
  - [RESEARCH_ITERATION_PLAYBOOK.md](phase3_5_research/RESEARCH_ITERATION_PLAYBOOK.md) - 研究迭代流程的歷史設計
  - [METRIC_INTERPRETATION_PRIORITY.md](phase3_5_research/METRIC_INTERPRETATION_PRIORITY.md) - 指標判讀優先順序的歷史設計
  - [BENCHMARK_PRESENTATION.md](phase3_5_research/BENCHMARK_PRESENTATION.md) - 回測 Benchmark 呈現的歷史設計
  - [PHASE4_ENTRY_CRITERIA.md](phase3_5_research/PHASE4_ENTRY_CRITERIA.md) - Phase 4 進入條件的歷史紀錄

## 狀態判讀

- 目前狀態、本週優先事項與高風險區以 `../00_core/PROJECT_SNAPSHOT.md` 為準。
- 未來 6 個月工程路線以 `../00_core/ROADMAP_6M_ENGINEERING.md` 為準。
- Roadmap 導覽由 `../00_core/DEVELOPMENT_ROADMAP.md` 負責；目前狀態與優先事項看 Snapshot，工程順序看 6M Roadmap。Hub 不保存 Next 或狀態摘要。
- Phase 3.3b、Phase 3.5 與 Phase 4 相關文件保留為設計與實作脈絡，不再代表目前未完成狀態。
- Phase 4 Portfolio 主要深化已完成；後續主線已從舊 Phase 敘事轉為 Post-V1 evidence-driven 版本節奏與 6M Roadmap。
- V1.1 至 V2.0 的完成狀態與當時下一步已封存在上述歷史路線圖；目前待辦與優先順序只依 `PROJECT_SNAPSHOT.md`、`ROADMAP_6M_ENGINEERING.md` 判讀。

## 🔗 相關目錄

- `../00_core/PROJECT_SNAPSHOT.md` - 目前狀態入口
- `../00_core/ROADMAP_6M_ENGINEERING.md` - 6 個月工程路線
- `../00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub
- [功能文件目錄](../02_features/README.md)

## 更新記錄

- 2026-07-03：將本目錄重新定位為 Historical / Reference；保留文件但明確標示不作目前 roadmap、完成狀態或下一步依據。
- 2026-10-08：更新 Scoped SSOT 入口說明，將 Roadmap Hub 標為純導覽，不再描述它維護 Next 摘要。
- 2026-10-08：列出已核實的 Active 直接引用，並為 Phase 文件與子目錄建立可點選入口；未移動或改寫歷史原文。
