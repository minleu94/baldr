# 跨模型 dispatch packets

本目錄由 SOL orchestrator 維護。每個 wave 只有在 `REFACTOR_EXECUTION_ORDER.md` 的前置 task、review 與 checkpoint gate 全部通過後才能釋出。

> 2026-10-09 生命週期整理：R003／R005／R006 回修 packet 與 Wave 1／Wave 2 唯讀分析輸入已先封存（Entry 135）；本批再封存 R002 review、R003／R005／R006 implementation 與 review packets、R004 review 及 Wave 1 review prompts（[Coverage History Entry 147](../../../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-147)）。舊路徑保留短導引。封包均為歷史材料，不代表目前待辦、正式驗收或新工作授權；R006 未知正式 binary 仍未 load／predict，RK-19 風險依 R031 列管。R008 的現行實作／審查分工看 [Model Assignments](../REFACTOR_MODEL_ASSIGNMENTS.md) 與最新 checkpoint；既有 Gemini packet／prompt 只作歷史證據。後續的 [Wave 1／Wave 2 一次性 prompts](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/README.md) 亦已封存（Coverage History Entry 153）；舊路徑只保留導引。

執行期分工以 [Model Assignments](../REFACTOR_MODEL_ASSIGNMENTS.md)、DAG 與 Execution Order 為準；此目錄保留歷史封包與索引。仍適用的 gate 順序如下：

1. SOL 重新核對 dependency、HEAD、既有 dirty scope、中央檔案獨占與當次 gate 證據。
2. 只開始 DAG／Execution Order 已解鎖、且 Model Assignments 指定的工作；實作由指定的 LUNA_MAX worker 負責，檔案 owner 不衝突時才可平行。
3. 高／極高風險 task 先由未參與實作的獨立 LUNA_MAX reviewer 審查凍結 diff；SOL 再核對實際差異、報告、驗證與架構 invariants，作最後 gate 判定。其他風險依分工表由 SOL 審查。
4. 後續不建立 Gemini implementation／review 派送；既有 Gemini packet、review 與 prompt 僅作歷史證據，不得直接重送，也不構成 task 授權。
5. 只有整個 wave 及其 checkpoint 通過後，SOL 才重新評估下一個 wave。

- `GEMINI_Rxxx.md`、`GEMINI_REWORK_Rxxx.md`、`GEMINI_REVIEW_Rxxx.md`：既有 Gemini 實作／回修／審查封包的歷史材料；不代表目前分工或可再次派送。
- `WAVEx_GEMINI_PROMPTS.md`：歷史交接 prompt；完整原文如已封存，舊路徑只保留相容導引。不得把舊 prompt 當成目前授權。
- `GEMINI_WAVE1_PARALLEL_ANALYSIS.md`：已封存的一次性唯讀分析輸入；實際分析與正式 review 結果見 `REFACTOR_REPORTS/WAVE1_GEMINI_PARALLEL_ANALYSIS_REPORT.md` 與 `WAVE1_R003_R005_GEMINI_REVIEW.md`。
- 已封存的 Wave 1 review prompts 僅供追溯：[封存原件](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/WAVE1_GEMINI_REVIEW_PROMPTS.md)。R003／R005／R006 review 已有結果，不需重送；R006 長測限制與 RK-19 依 R031 保留。
- `GEMINI_WAVE2_PARALLEL_ANALYSIS.md` 與已封存的 `WAVE2_GEMINI_PROMPTS.md`：R008 唯讀預分析輸入與一次性 prompt 均已結束，兩者不是正式 review。現行分工與 Wave 狀態看 [Model Assignments](../REFACTOR_MODEL_ASSIGNMENTS.md)；封存材料只供追溯，不提供釋出授權。
- `GEMINI_REVIEW_R008.md` 與 `WAVE2_GEMINI_REVIEW_PROMPTS.md`：較早 Gemini 審查狀態的歷史封包／prompt，內含的舊 SHA、暫停、重送與 Wave 3 blocked 文字不代表目前指示；請勿重送。現行分工與 Wave 狀態只看 [Model Assignments](../REFACTOR_MODEL_ASSIGNMENTS.md)，整體狀態看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)，R008 後續相依證據見 [schema-range recheck](../REFACTOR_REPORTS/R008_SCHEMA_RANGE_DEPENDENCY_RECHECK.md)。[Result-ID acceptance](../REFACTOR_REPORTS/R008_SOL_RESULT_ID_ACCEPTANCE.md) 與 [Wave 2 checkpoint](../REFACTOR_REPORTS/WAVE2_RESULT_ID_CHECKPOINT.md) 是有限範圍的歷史證據；其中「current gate」及「Wave 3 尚未執行」等文字只代表當時。

未解鎖 task 不預先建立 packet，避免 dependency evidence、HEAD、dirty scope 或測試結果過時。Packet 本身不授權下一 wave。

## 逐檔導覽索引

> 此索引只協助回溯既有 dispatch packet 和 wave 分析。舊 prompt 不構成新的執行授權；釋出條件仍以本目錄上方規則、Execution Order 與目前狀態為準。新增 packet 時請同步補入本索引。

### R-task packets
#### R002
- [已封存的 GEMINI_REVIEW_R002.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R002.md)（來源路徑保留導引；R002 ACCEPTED；characterization 不替代 TMP-NUM-01 precision gate。）

#### R003
- [已封存的 GEMINI_R003.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_R003.md)（來源路徑保留導引；R003 ACCEPTED_WITH_BOUNDED_SCOPE。）
- [已封存的 GEMINI_REVIEW_R003.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R003.md)（來源路徑保留導引；R003 ACCEPTED_WITH_BOUNDED_SCOPE。）
- [已封存的 GEMINI_REWORK_R003.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REWORK_R003.md)（來源路徑保留導引）

#### R004
- [已封存的 GEMINI_REVIEW_R004.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R004.md)（來源路徑保留導引；R004 CLOSED_AS_CHARACTERIZATION；R012 writer 獨立判讀。）

#### R005
- [已封存的 GEMINI_R005.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_R005.md)（來源路徑保留導引；R005 ACCEPTED_WITH_R020_BOUNDED_REPLAY；不外推全部 profiles。）
- [已封存的 GEMINI_REVIEW_R005.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R005.md)（來源路徑保留導引；R005 ACCEPTED_WITH_R020_BOUNDED_REPLAY；不外推全部 profiles。）
- [已封存的 GEMINI_REWORK_R005.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REWORK_R005.md)（來源路徑保留導引）

#### R006
- [已封存的 GEMINI_R006.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_R006.md)（來源路徑保留導引；R006 原 inventory／retention scope CLOSED；未知正式 binary 仍依 RK-19 列管。）
- [已封存的 GEMINI_REVIEW_R006.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R006.md)（來源路徑保留導引；R006 scope CLOSED 不代表未知 binary 相容；RK-19 仍開。）
- [已封存的 GEMINI_REWORK_R006.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REWORK_R006.md)（來源路徑保留導引）

#### R008
- [歷史 Gemini R008 review packet（勿重送）](GEMINI_REVIEW_R008.md)

### Wave／共用 packets
- [已封存的 GEMINI_WAVE1_PARALLEL_ANALYSIS.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_WAVE1_PARALLEL_ANALYSIS.md)
- [已封存的 GEMINI_WAVE2_PARALLEL_ANALYSIS.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_WAVE2_PARALLEL_ANALYSIS.md)
- [已封存的 WAVE1_GEMINI_PROMPTS.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/WAVE1_GEMINI_PROMPTS.md)（舊路徑保留相容導引；Wave 1 分析與 review 已完成，R006 未知正式 binary 風險仍依 RK-19 列管。）
- [已封存的 WAVE1_GEMINI_REVIEW_PROMPTS.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/WAVE1_GEMINI_REVIEW_PROMPTS.md)（歷史 prompt 不需重送；R006 限制依 R031。）
- [已封存的 WAVE2_GEMINI_PROMPTS.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/WAVE2_GEMINI_PROMPTS.md)（舊路徑保留相容導引；R008 唯讀預分析不等於正式 review 或 Wave 3 授權。）
- [歷史 Wave 2 Gemini review prompt（勿執行／重送）](WAVE2_GEMINI_REVIEW_PROMPTS.md)
