> **時點／狀態導覽（2026-10-11）**：本文的 `INTAKE_STATUS`、finding 判讀與歷史派送路由只適用其舊版審查封包，不等同 R008 整體現行 disposition。[R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 將 R008 列為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`；[R031 final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 未列 R008 專項。此處僅導覽 task-level 狀態，不重裁本文對舊版封包的結論或限制；原始判讀與限制保留。

# R008 舊版 Gemini 正式審查收件裁決

INTAKE_STATUS: SUPERSEDED_SNAPSHOT_REVIEW

使用者帶回的 Gemini 報告已原文保存於 `R008_GEMINI_STALE_REVIEW.md`，其 SHA-256 為 `3B543D5E39E325BAD3A27998D5D61A9FE91078BAB35B4F14F6527E37DFAF81EE`。末行為 `REVIEW_STATUS: CHANGES_REQUIRED`，Finding R008-01 認為 `RecommendationExecution` 只有空 ML references，不能區分未要求、不可用和 blocked。此 finding 對**舊凍結版本**有效，且已由 SOL 在 `R008_SOL_CHANGES_REQUIRED_ML_AVAILABILITY.md` 獨立判定並交 Luna 回修。

報告審查的 app recommendation `__init__.py`、contract、測試與實作報告 SHA 分別為 `F2020F50…`、`C12670CD…`、`2975AC35…`、`E0761D09…`；目前磁碟實際 SHA 分別為 `6C72A5C3…`、`EDEED3DD…`、`54BC7201…`、`0FA98AF3…`。Gemini 記錄讀取的封包止於第 299 行，也與目前已納入回修報告和 SOL 重驗的封包不同。故此 `CHANGES_REQUIRED` **不能作為目前版本的正式審查結論**，不另派 Luna 重做已完成的同一修正，也不能據此標記 R008 PASS。

SOL 現讀 `app_module/recommendation/contracts.py` 已有 frozen `MLAvailability`、typed status/reason、`RecommendationExecution.ml_availability`，專用測試明示相同空 refs 下的未要求、未知、不可用與 blocked 狀態。SOL 再跑 `tests/test_recommendation_contracts.py` 與 `tests/test_update_service_import_contract.py`：`15 passed`。這證明舊 finding 的核心缺口在目前版本已補上；**是否完全符合 INV-09／FINAL ML 契約仍待 Gemini 針對最新九檔 SHA 獨立審查**。

在本文 intake 撰寫當時，權威派送文件為 `REFACTOR_DISPATCH/GEMINI_REVIEW_R008.md` 和 `REFACTOR_DISPATCH/WAVE2_GEMINI_REVIEW_PROMPTS.md`，Wave 2 gate 及 Wave 3 尚未放行。後續 Wave 2 在 R008 新 SHA 上恢復 PASS，見 [R008 schema-range dependency recheck](R008_SCHEMA_RANGE_DEPENDENCY_RECHECK.md)；目前 R008 task disposition 以 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 為準。
