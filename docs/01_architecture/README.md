# 架構文檔目錄

> **系統架構相關文檔**

本目錄包含系統的架構設計和技術文檔。

重構文件較多時，先讀 [目標架構與重構契約入口](target_architecture_2026_09_22/README.md)，區分 FINAL 設計、任務規格、歷史草案及驗收紀錄。

## 📄 文檔列表

- **[2026-09-22 最終目標架構](target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)**
  - 唯一實作設計權威及五份 FINAL 分冊：資料流、擴充模型、ML 相容、不變條件、五區塊遷移
  - 已逐項裁決紅隊意見；先前草案保留為歷史。設計契約與實作進度分開閱讀，目前進度以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準。

- **[2026-09-22 重構實作 DAG](target_architecture_2026_09_22/REFACTOR_IMPLEMENTATION_DAG.md)**
  - 31 個具依賴、驗收與回滾契約的任務；另含[任務規格索引](target_architecture_2026_09_22/REFACTOR_TASKS/README.md)、[執行波次](target_architecture_2026_09_22/REFACTOR_EXECUTION_ORDER.md)、[驗證矩陣](target_architecture_2026_09_22/REFACTOR_VALIDATION_MATRIX.md)與[風險登錄](target_architecture_2026_09_22/REFACTOR_RISK_REGISTER.md)
  - 保存任務的依賴、驗收與回滾契約；各任務結果見 [實作報告](target_architecture_2026_09_22/REFACTOR_REPORTS/)。R031 有限工程範圍已完成並保留具名限制，R027 仍為 `INCONCLUSIVE`、R028 仍為 `BLOCKED`；見 [R031 closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。不代表整體重構或正式產品核准。

- **`system_architecture.md`**
  - 系統的技術架構說明
  - 模組結構、數據流程、技術細節
  - 原第 16 節逐次更新記錄已移至 [架構更新歷史](../09_archive/SYSTEM_ARCHITECTURE_UPDATE_HISTORY_202606_TO_202610.md)；主文保留舊錨點導引

- **`target_system_architecture.md`**
  - 領域背景與治理邊界導覽；工程目標決策導向 FINAL_TARGET_ARCHITECTURE
  - 不代表 target-only package 或能力目前已實作

## 目前架構速讀

`system_architecture.md` 的第 1–15 節是架構主文；原第 16 節更新記錄已歸檔，後續日期化增量仍保存有用的架構決策。先看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 判斷目前狀態，再按問題讀主文：

| 要理解的內容 | 主文位置 |
|---|---|
| 系統定位與整體分層 | 第 1–2 節 |
| UI、Application、Decision、Backtest、Portfolio | 第 3–7 節 |
| 資料、券商分點與 Runtime | 第 8–10 節 |
| 保存治理、匯出、文件架構、高風險修改與驗證 | 第 11–15 節 |

主文後仍有日期化架構增量；它們保存當時的架構變更與限制，不是按時間排序的目前狀態摘要。第 16 節舊更新流水帳已移至 [歸檔](../09_archive/SYSTEM_ARCHITECTURE_UPDATE_HISTORY_202606_TO_202610.md)。目前完成度看 Snapshot，具體驗收看對應 QA 收據。

## ML 架構閱讀順序

1. 先看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 確認日期化現況，再看 [目前系統架構](system_architecture.md) 中的「ML 路線與狀態判讀」。
2. [目標架構 ML Shadow Layer](target_system_architecture.md#1011-ml-shadow-layer) 描述全域 Recommendation ML 的設計邊界，不作為 active model 或目前資格的證據。
3. [Gate 7 ML Shadow Engineering](../06_qa/GATE_7_ML_SHADOW_ENGINEERING.md) 記錄投組配置 ML 的研究訓練與 Formal gate；[Personal H20 整合 QA](../06_qa/BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md) 記錄個股研究 H20 投影範圍。
4. [ASTRA Engineering Closeout（2026-10-03）](../06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md) 是特定日期的歷史執行記錄；只用來追溯當時狀態，不覆蓋較新的 Snapshot／QA。

以上 QA 檔保留原日期與證據用途，不因狀態更新而搬入 Archive 或改名。閱讀時要區分 Recommendation Shadow、Portfolio Allocation Research 與 Personal H20，避免把模型訓練、consumer 接線或研究頁投影說成正式選股已使用 ML。

- **`system_vision_specification.md`**
  - North Star、Bounded Advice、Evidence Requirements、Success Levels 與 Non-goals

- **[舊端到端流程藍圖（歷史）](../09_archive/SYSTEM_FLOW_END_TO_END_BLUEPRINT_HISTORY.md)**
  - 舊模組、資料路徑與建議新增元件僅供架構演進追溯；目前系統流程以 `system_architecture.md` 為準，UI 操作以 `../07_guides/APPLICATION_MANUAL.md` 為準。原路徑保留轉址，接住歷史 catalog 與計畫引用。

- **[資料收集架構歷史藍圖](../09_archive/DATA_COLLECTION_ARCHITECTURE_HISTORY.md)**
  - 早期 API、CSV、檔案路徑與更新流程設計，作為歷史參考。
  - 現行系統資料流看 [system_architecture](system_architecture.md)；操作看 [docs/03_data README](../03_data/README.md) 與 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。原路徑保留導引。

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

