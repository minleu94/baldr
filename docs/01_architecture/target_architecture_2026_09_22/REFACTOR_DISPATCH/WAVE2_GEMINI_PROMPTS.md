# Wave 2 Gemini 可複製 prompt

Wave 2 僅釋出 R008（Luna Max 實作、Gemini 正式審查）。以下 prompt 讓 Gemini 與 Luna 同步做唯讀預分析；正式獨立審查要等 R008 產出且由 SOL 凍結 SHA／diff／tests 後，再交新的 review packet。R008 初始 worker 停手後，SOL 已將 parent package 窄 lazy-export 修正納入具名受控 scope；請 Gemini 一併讀 `REFACTOR_REPORTS/R008_SCOPE_ADDENDUM.md`。這份預分析不等於 R008 PASS，也不授權 Wave 3。

```text
請在 C:\Projects\PythonProjects\technical_analysis 執行 Wave 2 的 R008「唯讀並行契約驗收風險分析」。完整讀取 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_WAVE2_PARALLEL_ANALYSIS.md，依其中的角色、權威架構摘錄、既有行為、範圍、檢查表與輸出格式完成分析。這不是實作或正式 code review；不要編輯任何檔案，不要碰 R009 以後任務。請把分析結果直接回傳給我，最後一行只能是 ANALYSIS_STATUS: COMPLETE 或 ANALYSIS_STATUS: ARCHITECTURE_BLOCKER_CANDIDATE。Luna 的 R008 diff／測試凍結後，我會再提供正式審查封包。
```
