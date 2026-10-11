> **歷史 gate 狀態導讀（2026-10-11）**：本文 `TASK_STATUS: CHANGES_REQUIRED_WITHIN_R008` 是 result-ID compatibility finding 當時的裁定；後續 [R008 SOL result-ID acceptance](R008_SOL_RESULT_ID_ACCEPTANCE.md) 記錄原 opaque／generated／legacy ID 範圍已修正並通過獨立複審，R031 task index 將 R008 列為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`。原 finding 與 R012 路徑安全界線保留；此狀態不延伸為所有 R008 consumer、receipt body 或 production writer 的端到端接受。見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。

# R008 result_id 相容性勘誤重開

TASK_STATUS: CHANGES_REQUIRED_WITHIN_R008

R011 唯讀準備發現 R008 的 `_validate_result_id()` 加入未獲既有行為支援的格式限制。`app_module/recommendation_service.py` 的既有 `run_recommendation()` 會原樣保留呼叫者／config 提供並經 `strip()` 的非空 result ID；沒有提供時產生 `rec_{uuid4().hex}`。R002 characterization 明示使用 `r002-fixed-001`、`r002-quantile-001`、`r002-missing-001` 並斷言 `last_run_context["result_id"]` 原值。既有 repository 也可建立 `rec_<timestamp>` legacy ID。R011 任務規格要求保留 public result_id、R002/R003 oracle、receipt/save 身分；FINAL_TARGET_ARCHITECTURE §5.1 的「沿用 `rec_<uuid>`」描述自產慣例，未授權 R008 對既有 caller ID 加上 hyphenated UUID 強制條件。

目前 `RecommendationExecution`、`MLReceiptBinding`、`SaveReceipt` 共用的 R008 驗證只接受 `rec_<canonical hyphenated UUID>`。直接建構 PoC：`r002-fixed-001` 拋 `ValueError: result_id 必須採 rec_<uuid> 格式`；`rec_0123456789abcdef0123456789abcdef` 拋 `ValueError: result_id 必須使用連字號 UUID 格式`。這使 R011 無法同時保留已存在的 ID 與建立完整 execution；將 ID 偷換、雙 ID 或更動 R002 golden 都不符合 INV-07／R011 acceptance。

此為 R008「CURRENT BEHAVIOR TO PRESERVE: result_id」及 typed binding 的原 scope 修正：契約應接受精確 `str` 的非空 resolved ID，保持身分原值並拒絕空白／非字串；由產生者保留既有新 ID 慣例，receipt/execution 仍要求相同 ID，持久化路徑安全由 R012 writer 驗證。需加 caller opaque、服務自產 hex、legacy timestamp ID 的正例與空白／型別反例；不得改 service、R002 oracle 或引入第二個 ID。若實際證據迫使新架構拒絕這些 ID，worker 必須停止並提出 ARCHITECTURE_BLOCKER，不得私自正規化。

R009/R010 已在此發現後即時中斷，兩個隔離 worktree 只保有 copied dependency baseline，沒有新增 task output 或修改 R007/R008。Wave 2 checkpoint 重新 HOLD，Wave 3 不再執行；修正後要更新兩個 worktree 的 R008 dependency bytes、重驗、獨立 Luna review 及 SOL gate 才可恢復。原 `R008_SOL_FINAL_ACCEPTANCE.md` 與舊 `WAVE2_CHECKPOINT.md` 對舊 SHA 的 PASS 保留為歷史，不代表新結果。
