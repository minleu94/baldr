# R008 Gemini 舊快照 PASS 交接裁決

> 本 intake 記錄舊 SHA PASS 及當時等待新 Gemini／Wave 2 gate 的狀態；後續 R008 bounded disposition 以 [R031 R008 row](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 為準。本頁保留為歷史交接，不再作派工或 release 指示。

INTAKE_STATUS: HISTORICAL_PASS_NOT_CURRENT_GATE

使用者於 2026-09-22 帶回的唯讀 Gemini 報告已原樣保存在 `R008_GEMINI_PRE_BATCH_PASS.md`。該報告的 `REVIEW_STATUS: PASS` 核對的是 ML availability 初次回修後的九檔快照，其中 `app_module/recommendation/contracts.py` SHA-256 為 `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487`、`decision_module/recommendation/contracts.py` 為 `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB`、`tests/test_recommendation_contracts.py` 為 `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA`。

這些受審 bytes 已被後續平行稽核和範圍內回修取代。後續稽核指出 failed/cancelled 原因、ML receipt exact binding、無型別 request options、百分位與 universe 範圍、mutable Enum alias，以及 export identity 測試覆蓋的缺口。舊報告在其指定快照上的結論予以保留，但不能證明現行版本 PASS，也不能解除 Wave 2 gate。

SOL 將在所有 R008 回修完成後重新跑定向與相關切片驗證，凍結新 SHA，更新 `REFACTOR_DISPATCH/GEMINI_REVIEW_R008.md` 和可複製 prompt，再請 Gemini 對該新快照正式複審。新的 Gemini `REVIEW_STATUS: PASS` 與 Wave 2 gate 均通過前，R009/R010 不得執行。
