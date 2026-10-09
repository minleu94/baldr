# Wave 1 Gemini 回修交接 prompts

> **2026-10-09 歷史提示：**以下是當時的 Gemini 回修 prompts；R003／R005／R006 後續改由 Luna Max 執行，Wave 1 的唯讀分析與 review 也已完成。**不要重新執行以下 prompts，也不要將其視為目前 task 或授權。**分析輸入已移至 [Archive](GEMINI_WAVE1_PARALLEL_ANALYSIS.md)，結果看同目錄 `REFACTOR_REPORTS/WAVE1_GEMINI_PARALLEL_ANALYSIS_REPORT.md` 與 `WAVE1_R003_R005_GEMINI_REVIEW.md`。以下正文保留作歷史交接紀錄。

## R003 — execution state characterization

```text
請在 C:\Projects\PythonProjects\technical_analysis 只回修 R003。先完整讀取 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REWORK_R003.md，依其中 SOL CHANGES_REQUIRED 發現及附帶的原始 R003 規格執行；該檔就是此工作的完整權威 task packet。只修改 packet 允許的檔案，保留既有未提交變更，不開始其他 R-task。完成後更新 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md，列出實際 diff、測試命令及結果、仍存在的 gap，並回報給 SOL 審查。若安全實作與核准架構衝突，停止並附證據回報 ARCHITECTURE_BLOCKER。
```

## R005 — replay characterization

```text
請在 C:\Projects\PythonProjects\technical_analysis 只回修 R005。先完整讀取 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REWORK_R005.md，依其中 SOL CHANGES_REQUIRED 發現及附帶的原始 R005 規格執行；該檔就是此工作的完整權威 task packet。只修改 packet 允許的檔案，保留既有未提交變更，不開始其他 R-task。完成後更新 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md，列出實際 diff、測試命令及結果、仍存在的 gap，並回報給 SOL 審查。若安全實作與核准架構衝突，停止並附證據回報 ARCHITECTURE_BLOCKER。
```

## R006 — ML compatibility baseline

```text
請在 C:\Projects\PythonProjects\technical_analysis 只回修 R006。先完整讀取 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REWORK_R006.md，依其中 SOL CHANGES_REQUIRED 發現及附帶的原始 R006 規格執行；該檔就是此工作的完整權威 task packet。僅使用安全、受控、唯讀 fixture；不要載入未知外部 pickle/joblib，也不要觸碰正式資料或補 sidecar。只修改 packet 允許的檔案，保留既有未提交變更，不開始其他 R-task。完成後更新 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md，將 verified/source-declared/unknown 分帳，列出實際 diff、測試命令及結果，並回報給 SOL 審查。若安全實作與核准架構衝突，停止並附證據回報 ARCHITECTURE_BLOCKER。
```

SOL 收回每項結果後，逐項核對實際 repository changes；R003、R005、R006 全數 PASS 前，Wave 2 維持 blocked。
