# Wave 1 Gemini 正式 review prompts

狀態更新：**R003、R005、R006 正式 Gemini review 與 SOL 整合驗收均已 PASS，不需重送。** R003／R005 合併審查原文保存於 `REFACTOR_REPORTS/WAVE1_R003_R005_GEMINI_REVIEW.md`；Wave 1 checkpoint 已 PASS。以下 prompt 僅作歷史派送紀錄。R006 的完整長測仍有一項具名既有 shadow-boundary failure，不可說成全通過。

## R003

```text
請在 C:\Projects\PythonProjects\technical_analysis 只做 R003 的唯讀獨立審查。完整讀取 docs/09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R003.md；該檔包含完整原始規格、Luna 實作報告、SOL 初審、凍結 SHA 和必查 acceptance criteria，請把整份內容當作本次 review prompt。先核對受審兩檔的 SHA，依實際 repository source／test/diff 判斷，精確列出 findings；不要改檔或開始其他 R-task。最後一行只能是 REVIEW_STATUS: PASS、REVIEW_STATUS: CHANGES_REQUIRED 或 REVIEW_STATUS: BLOCKED。
```

## R005

```text
請在 C:\Projects\PythonProjects\technical_analysis 只做 R005 的唯讀獨立審查。完整讀取 docs/09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R005.md；該檔包含完整原始規格、Luna 實作報告、SOL 初審、凍結 SHA、R001 source-path 勘誤補註和必查 acceptance criteria，請把整份內容當作本次 review prompt。先核對受審兩檔的 SHA，依實際 repository source／test/diff 判斷，精確列出 findings；不要把已由 R001 修正的舊路徑追溯 gap 當成新的 R005 failure；不要改檔或開始其他 R-task。最後一行只能是 REVIEW_STATUS: PASS、REVIEW_STATUS: CHANGES_REQUIRED 或 REVIEW_STATUS: BLOCKED。
```

## R006

已完成正式審查並 PASS；以下 prompt 僅作派送紀錄，**不要重複派送**。

```text
請在 C:\Projects\PythonProjects\technical_analysis 只做 R006 的唯讀獨立審查。完整讀取 docs/09_archive/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R006.md；該檔包含完整原始規格、Luna 實作報告、QA ABI 清冊、兩輪 SOL findings、最終初審、凍結 SHA 和必查相容性條件，請把整份內容當作本次 review prompt。先核對受審三檔的 SHA，依實際 repository source／test/artifact metadata 判斷，精確列出 findings；未知 joblib/pickle 不可載入，正式資料與檔案只能唯讀。完整長測的 73 passed、1 個已知 shadow-boundary failure 必須如實判讀；不要改檔或開始其他 R-task。最後一行只能是 REVIEW_STATUS: PASS、REVIEW_STATUS: CHANGES_REQUIRED 或 REVIEW_STATUS: BLOCKED。
```

Wave 1 已封口；Wave 2 只依 `WAVE2_GEMINI_PROMPTS.md` 與 R008 任務規格執行。
