# 跨模型 dispatch packets

本目錄由 SOL orchestrator 維護。每個 wave 只有在 `REFACTOR_EXECUTION_ORDER.md` 的前置 task、review 與 checkpoint gate 全部通過後才能釋出。

每次釋出 wave 的固定順序：

1. SOL 重新核對 dependency、HEAD、既有 dirty scope、中央檔案獨占與當次 gate 證據。
2. 先為該 wave 已解鎖的 Gemini implementation task 建立完整 packet 與可直接貼給 Gemini 的 prompt，並明確通知使用者 `READY_FOR_GEMINI: Rxxx`。若該 wave 只有 Luna implementation、但需要 Gemini review，先建立 review readiness 說明與交接 prompt；正式 review packet 必須等 Luna 的實際 diff、實作報告與測試結果凍結後才能建立。
3. 隨即平行派出同 wave、檔案範圍互不衝突的 Luna Max worker；每位 worker 只擁有一個 R-task。SOL 同步審查回傳實作與相容性證據，不因 worker 閒置而派遣後續 wave。
4. Gemini 結果回來後，SOL 讀取實際 repository diff、報告、測試及架構 invariant；需要的獨立 review 未 PASS 前，不把 task 標 PASS。整個 wave 及其 checkpoint 通過後才重新評估下一個 wave。

- `GEMINI_Rxxx.md`：Gemini implementation packet。
- `GEMINI_REWORK_Rxxx.md`：SOL 審查為 `CHANGES_REQUIRED` 後，在原 task scope 內回修的完整 packet。
- `GEMINI_REVIEW_Rxxx.md`：Gemini 對 Luna implementation 的獨立 review packet。
- `WAVEx_GEMINI_PROMPTS.md`：該 wave 的可複製交接 prompt；review readiness 不等於要求 Gemini 提前審查未完成的 Luna diff。
- `GEMINI_WAVE1_PARALLEL_ANALYSIS.md`：使用者將 Wave 1 回修交 Luna 後，供 Gemini 同步進行唯讀獨立驗收分析；正式 PASS/CHANGES_REQUIRED review 仍以回修後凍結的 diff 與測試為準。
- `WAVE1_GEMINI_REVIEW_PROMPTS.md`：已凍結的 Wave 1 Luna 回修之正式 Gemini review 啟動 prompt；每個 prompt 指向含完整規格、報告及測試的自足封包。
- `GEMINI_WAVE2_PARALLEL_ANALYSIS.md` 與 `WAVE2_GEMINI_PROMPTS.md`：Wave 1 gate PASS 後，供 Gemini 與 R008 Luna 實作同步進行的唯讀契約驗收風險分析；不是正式 review，也不釋出 Wave 3。
- `GEMINI_REVIEW_R008.md` 與 `WAVE2_GEMINI_REVIEW_PROMPTS.md`：R008 Luna 的 ML availability 回修與 SOL 重驗後，依最新九檔 SHA 凍結的正式唯讀獨立審查封包／prompt；Gemini 結果仍須由 SOL 核對才能進 Wave 2 checkpoint。

未解鎖 task 不預先建立 packet，避免 dependency evidence、HEAD、dirty scope 或測試結果過時。Packet 本身不授權下一 wave。
