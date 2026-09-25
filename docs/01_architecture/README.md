# 架構文檔目錄

> **系統架構相關文檔**

本目錄包含系統的架構設計和技術文檔。

## 📄 文檔列表

- **[2026-09-22 最終目標架構](target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)**
  - 唯一實作設計權威及五份 FINAL 分冊：資料流、擴充模型、ML 相容、不變條件、五區塊遷移
  - 已逐項裁決紅隊意見；先前草案保留為歷史，尚未實作，不改目前狀態或產品 Gate

- **[2026-09-22 重構實作 DAG](target_architecture_2026_09_22/REFACTOR_IMPLEMENTATION_DAG.md)**
  - 31 個具依賴、驗收與回滾契約的任務；另含[任務規格索引](target_architecture_2026_09_22/REFACTOR_TASKS/README.md)、[執行波次](target_architecture_2026_09_22/REFACTOR_EXECUTION_ORDER.md)、[驗證矩陣](target_architecture_2026_09_22/REFACTOR_VALIDATION_MATRIX.md)與[風險登錄](target_architecture_2026_09_22/REFACTOR_RISK_REGISTER.md)
  - 僅供後續 coding agent 分派；尚未開始 R001，也未修改 production code

- **`system_architecture.md`**
  - 系統的技術架構說明
  - 模組結構、數據流程、技術細節

- **`target_system_architecture.md`**
  - 領域背景與治理邊界導覽；工程目標決策導向 FINAL_TARGET_ARCHITECTURE
  - 不代表 target-only package 或能力目前已實作

- **`system_vision_specification.md`**
  - North Star、Bounded Advice、Evidence Requirements、Success Levels 與 Non-goals

- **`system_flow_end_to_end.md`**
  - 系統端到端流程說明
  - 從環境初始化到 UI 應用的完整流程

- **`data_collection_architecture.md`**
  - 數據收集系統的架構
  - API 端點、數據更新流程、數據存儲結構

- **`runtime_observatory_rules.md`**
  - Runtime Subsystem、DTO、UI bridge 與依賴方向治理規範

- **`ui_design_system_midnight_analyst.md`**
  - PySide6 UI theme tokens、共用元件、QSS 與效能限制

歷史遷移與已完成安全重構報告已移至 `../09_archive/`；QA closeout 與移除稽核位於 `../06_qa/`。

## 🔗 相關目錄

- `../00_core/` - 核心文檔
- `../03_data/` - 數據相關文檔
- `../06_qa/` - QA、驗證與 closeout 證據
- `../09_archive/` - 歷史遷移與已完成計畫

## 更新記錄

- 2026-09-22：將 FINAL 架構轉成 31 份可分派任務、DAG、波次、驗證矩陣與風險登錄；未開始實作。

- 2026-09-22：將目標架構入口更新為紅隊裁決後的 FINAL 主文與五份規範分冊。

- 2026-09-22：加入目標架構工程分冊導航。

