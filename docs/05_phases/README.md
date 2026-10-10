# 歷史 Phase 與研究 SOP 文檔目錄

> **狀態**：Historical / Reference。
> **最後整理**：2026-10-09（明確區分歷史 Phase 4 與現行 Gate 4）。
> **判讀規則**：本目錄保留 Phase 時期的設計、驗收與研究 SOP 脈絡，不作為目前 roadmap、目前完成狀態或下一步優先順序依據。

目前專案已改採 Scoped SSOT：

- 目前狀態、本週優先事項與高風險區看 `../00_core/PROJECT_SNAPSHOT.md`。
- 未來 6 個月工程路線看 `../00_core/ROADMAP_6M_ENGINEERING.md`。
- V1.1 至 V2.0 已完成版本演進見 [`../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md`](../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md)，僅作歷史追溯。
- 架構與模組邊界看 `../01_architecture/system_architecture.md`。
- 實際操作方式看 `../07_guides/APPLICATION_MANUAL.md`。

本目錄保留導覽 README 與舊路徑轉址；13 份 Phase／SOP 原文已依原目錄層次移入 [`docs/09_archive/`](../09_archive/README.md)。目前可核實的現行產品／功能文件引用只有 [`STRATEGY_DESIGN_SPECIFICATION.md`](../02_features/STRATEGY_DESIGN_SPECIFICATION.md) 使用舊路徑 `../05_phases/PHASE2_ARCHITECTURE.md`；該路徑先到本目錄的相容轉址頁，再導向 Archive 原文。下表為方便查閱而直接連到封存原文。日期化歷史設計規格如 [strategy-scoring-governance-design](../09_archive/superpowers/specs/2026-06-13-strategy-scoring-governance-design.md) 已直接連到 Archive；其舊 Superpowers 路徑仍保留相容導引。沒有現行功能文件直接連結不等於可以刪除。歸檔內容中的下一步、進行中、Gate 或階段描述若與核心權威文件衝突，以核心權威文件為準。

## 文檔列表與目前處置

| 文件 | 目前處置 | 用途 |
|---|---|---|
| [PHASE2_ARCHITECTURE.md](../09_archive/PHASE2_ARCHITECTURE.md) | 已歸檔；舊路徑保留轉址 | Phase 2 策略架構設計追溯；目前有一筆 Active 引用經轉址連至原文。 |
| [PHASE2_STRATEGY_LIBRARY.md](../09_archive/PHASE2_STRATEGY_LIBRARY.md) | 已歸檔；舊路徑保留轉址 | Phase 2 策略資料庫設計追溯。 |
| [PHASE_2A_DATA_SOURCES_AUDIT.md](../09_archive/PHASE_2A_DATA_SOURCES_AUDIT.md) | 已歸檔；舊路徑保留轉址 | CSV-first 到 DB-first 過渡盤點；目前資料架構以 [system architecture](../01_architecture/system_architecture.md) 與 `../03_data/` 文件為準。 |
| [PHASE2_5_COMPLETION_STATUS.md](../09_archive/PHASE2_5_COMPLETION_STATUS.md) | 已歸檔；舊路徑保留轉址 | Phase 2.5 完成狀態追溯；fixed / quantile 現況以 Snapshot、6M Roadmap 與 QA 報告為準。 |
| [PHASE3_3B_RESEARCH_DESIGN.md](../09_archive/PHASE3_3B_RESEARCH_DESIGN.md) | 已歸檔；舊路徑保留轉址 | Research Lab / Promote 早期設計脈絡；目前 Research Run Registry / lifecycle gate 以核心文件與架構文件為準。 |
| [EPIC2_MVP2_ARCHITECTURE_DESIGN.md](../09_archive/EPIC2_MVP2_ARCHITECTURE_DESIGN.md) | 已歸檔；舊路徑保留轉址 | 過擬合風險提示早期架構設計。 |
| [EPIC2_MVP2_IMPLEMENTATION_CHECKLIST.md](../09_archive/EPIC2_MVP2_IMPLEMENTATION_CHECKLIST.md) | 已歸檔；舊路徑保留轉址 | 過擬合風險提示實作 checklist 追溯。 |
| [PHASE4_PORTFOLIO_DESIGN.md](../09_archive/PHASE4_PORTFOLIO_DESIGN.md) | 已歸檔；舊路徑保留轉址 | Portfolio MVP 初始設計；目前 Portfolio / lifecycle 狀態以 Snapshot、Architecture 與 Manual 為準。 |
| [PHASE4_STARTUP_SUMMARY.md](../09_archive/PHASE4_STARTUP_SUMMARY.md) | 已歸檔；舊路徑保留轉址 | Phase 4 啟動摘要追溯。 |
| [phase3_5_research/README.md](phase3_5_research/README.md) | 保留為歷史索引；子文件已歸檔 | 研究流程、指標判讀與 Phase 4 entry gate 的歷史文件地圖。 |

已歸檔的相關文件：

- [PHASE_3_3B_IMPLEMENTATION_PLAN.md](../09_archive/PHASE_3_3B_IMPLEMENTATION_PLAN.md)：Phase 3.3b 實施規劃，已移至歸檔目錄並只作歷史追溯。

## 📁 子目錄

- [phase3_5_research/README.md](phase3_5_research/README.md) - Phase 3.5 歷史文件索引
- [RESEARCH_ITERATION_PLAYBOOK.md](../09_archive/phase3_5_research/RESEARCH_ITERATION_PLAYBOOK.md) - 研究迭代流程的歷史設計
- [METRIC_INTERPRETATION_PRIORITY.md](../09_archive/phase3_5_research/METRIC_INTERPRETATION_PRIORITY.md) - 指標判讀優先順序的歷史設計
- [BENCHMARK_PRESENTATION.md](../09_archive/phase3_5_research/BENCHMARK_PRESENTATION.md) - 回測 Benchmark 呈現的歷史設計
- [PHASE4_ENTRY_CRITERIA.md](../09_archive/phase3_5_research/PHASE4_ENTRY_CRITERIA.md) - Phase 4 進入條件的歷史紀錄

## 狀態判讀

- 目前狀態、本週優先事項與高風險區以 `../00_core/PROJECT_SNAPSHOT.md` 為準。
- 未來 6 個月工程路線以 `../00_core/ROADMAP_6M_ENGINEERING.md` 為準。
- Roadmap 導覽由 `../00_core/DEVELOPMENT_ROADMAP.md` 負責；目前狀態與優先事項看 Snapshot，工程順序看 6M Roadmap。Hub 不保存 Next 或狀態摘要。
- Phase 3.3b、Phase 3.5 與 Phase 4 相關文件保留為設計與實作脈絡，不再代表目前未完成狀態。
- **名稱區分**：封存的 [Phase 4 Portfolio MVP](../09_archive/PHASE4_PORTFOLIO_DESIGN.md) 是初始唯讀決策支援設計；現行 **Gate 4 Portfolio Coach v1** 由 [6M Roadmap](../00_core/ROADMAP_6M_ENGINEERING.md) 定義。兩個編號相同是歷史命名重疊，不代表同一計畫；舊文件不能作為 Gate 4 範圍、驗收或完成狀態依據。
- 舊 Phase 4 Portfolio MVP 當時的主要深化已完成；後續主線已從舊 Phase 敘事轉為 Post-V1 evidence-driven 版本節奏與 6M Roadmap。
- V1.1 至 V2.0 的完成狀態與當時下一步已封存在上述歷史路線圖；目前待辦與優先順序只依 `PROJECT_SNAPSHOT.md`、`ROADMAP_6M_ENGINEERING.md` 判讀。

## 🔗 相關目錄

- `../00_core/PROJECT_SNAPSHOT.md` - 目前狀態入口
- `../00_core/ROADMAP_6M_ENGINEERING.md` - 6 個月工程路線
- `../00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub
- [功能文件目錄](../02_features/README.md)

## 更新記錄

- 2026-07-03：將本目錄重新定位為 Historical / Reference；保留文件但明確標示不作目前 roadmap、完成狀態或下一步依據。
- 2026-10-08：更新 Scoped SSOT 入口說明，將 Roadmap Hub 標為純導覽，不再描述它維護 Next 摘要。
- 2026-10-08：將 13 份 Phase／SOP 原文移入 Archive，保留舊路徑轉址與原層次；本頁改連歸檔原文並保留唯一 Active 引用的相容路徑。
- 2026-10-09：明確區分封存的 Phase 4 Portfolio MVP 初始設計與現行 6M Roadmap Gate 4 Portfolio Coach v1，避免相同編號造成計畫範圍混淆。
