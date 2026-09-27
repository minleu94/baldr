# 目標架構與重構契約入口

本目錄保存三種不同用途的文件。檔案多不代表有多套實作權威；目前進度與未解除限制請讀 [PROJECT_SNAPSHOT](../../00_core/PROJECT_SNAPSHOT.md)及 [R031 closeout](../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。

## 實作設計權威

[FINAL_TARGET_ARCHITECTURE](FINAL_TARGET_ARCHITECTURE.md) 是唯一目標架構決策來源；其中連結的五份 `FINAL_*` 分冊分別定義資料流、擴充、ML 相容、不變條件與遷移順序。這些是設計契約，不代表每個目標都已完成。

## 任務與驗收

- [任務 DAG](REFACTOR_IMPLEMENTATION_DAG.md)、[31 份任務規格](REFACTOR_TASKS/README.md)、[執行順序](REFACTOR_EXECUTION_ORDER.md)、[驗證矩陣](REFACTOR_VALIDATION_MATRIX.md)和[風險登錄](REFACTOR_RISK_REGISTER.md)：保留依賴、交付、驗收與回滾契約，不當作目前待辦清單。
- `REFACTOR_REPORTS/`：各任務實作、審查與重驗的日期化證據。不同輪次不相互覆蓋，不把 bounded acceptance 當作全域通過。
- `REFACTOR_DISPATCH/`：歷史分派、審查意見與重作要求；可能引用報告原文與固定 SHA，以維持交接證據。舊指令不構成新的執行授權。

## 歷史設計與裁決輸入

[SYSTEM_ARCHITECTURE_ASSESSMENT](SYSTEM_ARCHITECTURE_ASSESSMENT.md)、[紅隊審查](ARCHITECTURE_RED_TEAM_REVIEW.md)、[必要變更](ARCHITECTURE_REQUIRED_CHANGES.md)，以及沒有 `FINAL_` 前綴的目標架構、資料流、ML 相容、擴充、不變條件與遷移草案，保留作決策追溯。草案已被 FINAL 裁決取代，不能授權實作；其中的舊模組路徑與「尚未實作」只代表當時基線。

閱讀目前架構請回到 [system_architecture](../system_architecture.md)，不要把歷史評估或目標設計當成目前程式結構。
