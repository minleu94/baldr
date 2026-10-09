# 跨模型 dispatch packets

本目錄由 SOL orchestrator 維護。每個 wave 只有在 `REFACTOR_EXECUTION_ORDER.md` 的前置 task、review 與 checkpoint gate 全部通過後才能釋出。

> 2026-10-09 生命週期整理：R003／R005／R006 回修 packet 與 Wave 1／Wave 2 唯讀分析輸入已先封存（Entry 135）；本批再封存 R002 review、R003／R005／R006 implementation 與 review packets、R004 review 及 Wave 1 review prompts（[Coverage History Entry 147](../../../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-147)）。舊路徑保留短導引。封包均為歷史材料，不代表目前待辦、正式驗收或新工作授權；R006 未知正式 binary 仍未 load／predict，RK-19 風險依 R031 列管。R008 review 仍依本索引與 Wave 2 checkpoint。

每次釋出 wave 的固定順序：

1. SOL 重新核對 dependency、HEAD、既有 dirty scope、中央檔案獨占與當次 gate 證據。
2. 先為該 wave 已解鎖的 Gemini implementation task 建立完整 packet 與可直接貼給 Gemini 的 prompt，並明確通知使用者 `READY_FOR_GEMINI: Rxxx`。若該 wave 只有 Luna implementation、但需要 Gemini review，先建立 review readiness 說明與交接 prompt；正式 review packet 必須等 Luna 的實際 diff、實作報告與測試結果凍結後才能建立。
3. 隨即平行派出同 wave、檔案範圍互不衝突的 Luna Max worker；每位 worker 只擁有一個 R-task。SOL 同步審查回傳實作與相容性證據，不因 worker 閒置而派遣後續 wave。
4. Gemini 結果回來後，SOL 讀取實際 repository diff、報告、測試及架構 invariant；需要的獨立 review 未 PASS 前，不把 task 標 PASS。整個 wave 及其 checkpoint 通過後才重新評估下一個 wave。

- `GEMINI_Rxxx.md`：Gemini implementation packet。
- `GEMINI_REWORK_Rxxx.md`：SOL 審查為 `CHANGES_REQUIRED` 後，在原 task scope 內回修的完整 packet。
- `GEMINI_REVIEW_Rxxx.md`：Gemini 對 Luna implementation 的獨立 review packet。
- `WAVEx_GEMINI_PROMPTS.md`：該 wave 的可複製交接 prompt；review readiness 不等於要求 Gemini 提前審查未完成的 Luna diff。
- `GEMINI_WAVE1_PARALLEL_ANALYSIS.md`：已封存的一次性唯讀分析輸入；實際分析與正式 review 結果見 `REFACTOR_REPORTS/WAVE1_GEMINI_PARALLEL_ANALYSIS_REPORT.md` 與 `WAVE1_R003_R005_GEMINI_REVIEW.md`。
- 已封存的 Wave 1 review prompts 僅供追溯：[封存原件](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/WAVE1_GEMINI_REVIEW_PROMPTS.md)。R003／R005／R006 review 已有結果，不需重送；R006 長測限制與 RK-19 依 R031 保留。
- `GEMINI_WAVE2_PARALLEL_ANALYSIS.md` 與 `WAVE2_GEMINI_PROMPTS.md`：已完成的 R008 唯讀預分析封包與一次性提示；輸入封存、prompt 首段已標為歷史。結果看 R008 report／Wave 2 checkpoint；不是新 review，也不釋出 Wave 3。
- `GEMINI_REVIEW_R008.md` 與 `WAVE2_GEMINI_REVIEW_PROMPTS.md`：R008 Luna 的 ML availability 回修與 SOL 重驗後，依最新九檔 SHA 凍結的正式唯讀獨立審查封包／prompt；Gemini 結果仍須由 SOL 核對才能進 Wave 2 checkpoint。

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
- [GEMINI_REVIEW_R008.md](GEMINI_REVIEW_R008.md)

### Wave／共用 packets
- [已封存的 GEMINI_WAVE1_PARALLEL_ANALYSIS.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_WAVE1_PARALLEL_ANALYSIS.md)
- [已封存的 GEMINI_WAVE2_PARALLEL_ANALYSIS.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_WAVE2_PARALLEL_ANALYSIS.md)
- [WAVE1_GEMINI_PROMPTS.md](WAVE1_GEMINI_PROMPTS.md)
- [已封存的 WAVE1_GEMINI_REVIEW_PROMPTS.md](../../../09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/WAVE1_GEMINI_REVIEW_PROMPTS.md)（歷史 prompt 不需重送；R006 限制依 R031。）
- [WAVE2_GEMINI_PROMPTS.md](WAVE2_GEMINI_PROMPTS.md)
- [WAVE2_GEMINI_REVIEW_PROMPTS.md](WAVE2_GEMINI_REVIEW_PROMPTS.md)
