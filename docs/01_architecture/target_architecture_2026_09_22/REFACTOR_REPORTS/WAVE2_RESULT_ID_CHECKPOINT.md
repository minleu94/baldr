> **歷史 Wave checkpoint**：本文只記錄當時的依賴與有限釋出狀態，不提供目前的 release 或派工授權。後續 C1／Wave 6 裁決見 [C1 checkpoint](C1_CHECKPOINT.md) 與 [Wave 6 最終 gate 報告](WAVE6_FINAL_GATE_REPORT.md)；目前狀態看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)。

# Wave 2 — result_id 勘誤後 checkpoint

CHECKPOINT_STATUS: PASS

R008 現版 `CCF12635…` 已由 `R008_LUNA_RESULT_ID_INDEPENDENT_REVIEW.md` 獨立審查 `PASS`，並由 `R008_SOL_RESULT_ID_ACCEPTANCE.md` 驗收 `PASS`。R007 最新 dependency 亦已 PASS。原 Wave 2 的 contract 深凍結、terminal 組合、typed ownership、無 I/O leaf import 與 parent export identity 維持；新增 result_id 兼容驗證保留既有身份與 receipt 綁定，沒有 codec、writer 或 consumer 接線。

Wave 3 可恢復 R009/R010，但必須先將兩個隔離 worktree 的 R008 app contract/test 更新至本次凍結 SHA 並核對其餘 copied dependency 未漂移。C1 仍是 R012 後的硬 gate，尚未執行。
