> **歷史封存警語（2026-10-10）：**本文保留當時的 Wave 1 分析派送內容；其中 SHA（如有）、scope、角色、指令與狀態僅代表原快照，不得據此重派、重跑或視為目前任務／授權。現況請以 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 與 [REFACTOR_MODEL_ASSIGNMENTS](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md) 為準；後續 Wave 1 狀態見 [WAVE1_R007_TZNAME_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE1_R007_TZNAME_CHECKPOINT.md)。

# Gemini Wave 1 唯讀獨立驗收分析封包

以下整份內容可直接複製給 Gemini。R003、R005、R006 的回修現由三位 Luna Max 在同一 repository 的互不重疊檔案範圍平行執行。你要同步進行跨模組、相容性敏感的**唯讀**分析，提供 SOL 後續審查使用；本工作不是實作，也不是回修後的正式 PASS review。

## ROLE／TASK ID／PURPOSE

你是獨立 Gemini reviewer。任務是 `WAVE1_PARALLEL_ANALYSIS`，只分析 R003、R005、R006 的原始規格、SOL `CHANGES_REQUIRED` 發現、實際 production 行為及足以判斷 acceptance criteria 的 oracle。找出 SOL 或 Luna 可能漏掉的反例，並按每個 R-task 提供可直接檢查的驗收矩陣。不要修改任何檔案。

## CURRENT SYSTEM CONTEXT／COMPLETED DEPENDENCIES

- 工作目錄：`C:\Projects\PythonProjects\technical_analysis`。開始時基線 HEAD 為 `391b057c`；工作樹已有其他未提交變更，不得清理、覆寫、stage 或 commit。
- Wave 0 的 R001 已 PASS。Wave 1 的 R002、R004、R007 已 PASS；R003、R005、R006 的原實作經 SOL 審查為 `CHANGES_REQUIRED`。Wave 2–14 仍 blocked。
- R003 只在 `tests/test_recommendation_execution_state_characterization.py` 和 `REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md` 回修；R005 只在 `tests/test_recommendation_replay_characterization.py` 和 R005 報告回修；R006 只在 `tests/test_refactor_ml_compatibility_baseline.py`、`docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md` 和 R006 報告回修。上述檔案正在由 Luna 寫入，不要把你讀到的暫態版本當成最終 diff。

## AUTHORITATIVE ARCHITECTURE／RELEVANT INVARIANTS

先讀 repository 的 `AGENTS.md` 與指定必讀文件，再只讀下列與本分析直接相關的權威文件：

- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R003.md`、`R005.md`、`R006.md`
- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_SOL_REVIEW.md`、`R005_SOL_REVIEW.md`、`R006_SOL_REVIEW.md`
- `docs/01_architecture/target_architecture_2026_09_22/FINAL_ARCHITECTURE_INVARIANTS.md`、`FINAL_DATA_FLOW.md` 相關節、`FINAL_ML_COMPATIBILITY_CONTRACT.md` 相關節、`REFACTOR_VALIDATION_MATRIX.md`

重點：INV-01（原始與歷史 bytes 不變）、INV-05（decision-time availability）、INV-06（數值語意不變）、INV-07–10（execution identity、凍結、terminal 狀態、hidden state）、INV-13（歷史 replay mode 自身語意）、INV-14–15（ML frozen boundary 和舊 ABI）、INV-16（worker life cycle）、INV-18（工程驗證不等於 formal permission）。不得重新設計架構。

## ALLOWED SCOPE／OUT OF SCOPE／FILES LIKELY INVOLVED

只可**唯讀**查閱規格、production source、測試與報告；可在回答中提出具體斷言或測試路由。R003 關注 `recommendation_service.py`、execution coordinator、TaskWorker 和 Qt stale callback；R005 關注 DataFrame provider、historical replay、portfolio dates/manifest；R006 關注 feature registry、historical matrix、OOC/Direct stores、manifest/loader 及安全受控 fixture。

不得改任何檔案、執行未知 joblib/pickle 反序列化、寫正式資料或 artifact、設計新 contract、替 Luna 修 code、修四條既有 ML shadow boundary import、啟動另一 R-task 或釋出下一 wave。

## CURRENT BEHAVIOR TO PRESERVE／COMPATIBILITY

- R003：completed-nonempty、completed-empty、validation rejection、failed、cancelled 可由事件而非 `[]` 分辨；合作式取消、progress shape、stale UI callback 不覆寫 last-good、同一服務 A/B 交錯後延遲讀 A、巢狀 alias、worker close、receipt 在 cancel/failure 後的可見順序。這是 characterization；發現現況違反目標 invariant 時列為現況 gap，不要求 Luna 改 production。
- R005：`RecommendationDataFrameProvider` 是 portfolio/replay 的 legacy evaluator，不是 interactive 推薦入口。以同 mode 的完整 snapshot、ordered rows、profile/config/as-of、diagnostics、portfolio refs 固定舊語意；數字 `YYYYMMDD`、future append、availability、lookback 80、max stocks 200、fast filters、score fallback、sort/top_n、per-stock exception 及 factor manifest 均須有可判斷 oracle。跨 mode 差異不得硬性抹平，不能導入 look-ahead 或改數值排序。
- R006：舊 historical 20 欄的 id/order/dtype/unit、None→NaN、imputer/scale、HGB mask、OOC endian/shape/row-fold refs、Direct carry/checkpoint 和 15 路徑 stable computation identity/runtime loaded-code integrity 必須分帳。source contract 不等於磁碟 artifact inventory；注入 `DummyModel` 不能證明真實舊 joblib 相容。未知外部 binary 保留為 unknown/unsupported，不能宣稱已隔離或已驗證，更不能載入。正式 artifact、manifest、checkpoint 皆唯讀。
- SOL 先前執行 R006 focused suites 得 `69 passed, 1 failed`；唯一失敗為 `test_ml_shadow_dependency_boundary` 揭露四條既有 production→ML import。它們不是 R006 的修補範圍，不可用 allowlist 或誤報全綠掩蓋。

## REQUIRED ANALYSIS／TESTS／ACCEPTANCE CRITERIA

1. 對 R003、R005、R006 各列一個驗收矩陣：`規格條款 | 可觀察 oracle | 建議 fixture / source seam | 對應測試路由 | 現有證據或缺口 | 是否屬原 scope`。以原始 task 規格與 SOL 發現為準，避免把你建議的新功能當必做項。
2. 每項至少給出最容易假陽性通過的兩個案例、它們為何不證明相容，以及可區分的負例。對 R006 明確分 `source-declared`、`controlled-fixture verified`、`artifact-readback verified`、`unknown`。
3. 指出任何與三位 Luna 允許檔案範圍衝突、需要 production mutation 或可能碰其他 task owner 的要求；只提出證據和 SOL 處置建議，不自行修改。
4. 列出 R003 的 `V-EXEC`、R005 的 `V-REPLAY`、R006 的 `V-ML-SMALL`／`V-ML-DIRECT` 應跑的 focused tests；不要將未執行測試寫為 PASS。若你自行執行唯讀測試，報告精確命令、結果及是否與正在寫入的 Luna 檔案交錯。
5. 回覆最後使用 `ANALYSIS_STATUS: COMPLETE` 或 `ANALYSIS_STATUS: BLOCKED`，再列 `NEEDS_FINAL_DIFF_REVIEW: YES`。此狀態不是 task PASS。

## STOP CONDITIONS／REQUIRED REPORT

若必須動 production、正式資料、未知模型或需要改核准架構才能回答，停止該部分並具名回報；其他可唯讀分析的部分繼續。回答以繁體中文列每個 R-task 的驗收矩陣、假陽性／負例、測試路由、scope 風險與最後狀態；不用建立 repository 檔案。

Do not redesign the architecture.

Do not perform unrelated cleanup.

Do not silently fix unrelated bugs.

Do not begin another R-task.

If repository evidence contradicts this task specification in a way that prevents safe implementation, stop and report ARCHITECTURE_BLOCKER with evidence.
