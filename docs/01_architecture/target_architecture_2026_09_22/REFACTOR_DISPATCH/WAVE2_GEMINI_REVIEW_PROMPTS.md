# Wave 2 Gemini 正式 review prompt

> 暫停派送：Wave 2 並行稽核已重現 R008 深凍結與契約驗證缺口，Luna 正在同一 R008 範圍回修。本檔的九檔 SHA 是回修前版本；待 SOL 重驗、重新凍結並移除此註記後才可交 Gemini。

R008 Luna 已完成 SOL 要求的 ML availability 範圍內回修，SOL 已重驗並更新九個凍結 SHA。使用者剛帶回的 `R008_GEMINI_STALE_REVIEW.md` 審的是回修前四個舊 SHA；其 finding 已被回修，但不構成目前版本 PASS。此 prompt 是**對最新版本重新進行的正式唯讀獨立審查**；請勿重用舊檔案快照。Gemini 回傳後由 SOL 核對實際 repository changes、報告、測試及架構不變條件，再決定 R008/Wave 2 gate。Wave 3 仍 blocked。

```text
請在 C:\Projects\PythonProjects\technical_analysis 對 R008 **目前磁碟版本**重新執行正式唯讀獨立審查。先讀 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R008_STALE_GEMINI_REVIEW_INTAKE.md，確認前一次 `CHANGES_REQUIRED` 僅審到缺 ML availability 的舊 SHA；再完整讀取 docs/01_architecture/target_architecture_2026_09_22/REFACTOR_DISPATCH/GEMINI_REVIEW_R008.md。該封包內嵌 R008 規格、FINAL invariants、Luna 回修報告、SOL 重驗與九個最新凍結 SHA。先以 `R008_SOL_REWORK_REVIEW.md` 的九個**完整 SHA**逐檔核對實際 bytes 與 diff；尤其 app contract 必須為 `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487`、R008 測試必須為 `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA`。如遇舊 `C12670CD…` 或 `2975AC35…`，停止並回報版本漂移，不要重交舊 finding。獨立審查新的 `MLAvailability` status/reason/reference 組合是否符合 INV-09／FINAL ML 契約，以及 parent lazy exports、深凍結、terminal 狀態、Decimal/bp、typed refs、schema ownership、無 I/O import 和測試充分性。SOL 擴大測試中的六個 ML integration 失敗在固定日期 fixture 建立階段，請獨立核對其分類，不要誤稱整組測試通過。只做唯讀 review，不改檔案或開始其他 R-task；有問題請給檔案、行號、可重現證據與最小修正方向。最後一行只能是 REVIEW_STATUS: PASS、REVIEW_STATUS: CHANGES_REQUIRED 或 REVIEW_STATUS: BLOCKED 三者之一。
```
