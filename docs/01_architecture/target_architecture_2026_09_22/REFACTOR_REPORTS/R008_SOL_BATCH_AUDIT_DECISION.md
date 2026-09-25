# R008 並行批量審查：SOL 裁決與回修路由

INTEGRATION_STATUS: CHANGES_REQUIRED_WITHIN_R008

本輪三份互不改碼的獨立報告為 `R008_LUNA_PARALLEL_CONTRACT_AUDIT.md`、`R008_LUNA_PARALLEL_IMPORT_QA_AUDIT.md` 及 `WAVE2_LUNA_PARALLEL_GATE_PREFLIGHT.md`；另由 `R008_ML_BINDING_SCOPE_AUDIT.md` 對 receipt binding 進行專項核對。所有報告只審 R008／Wave 2，不是 Gemini 正式 `REVIEW_STATUS`。`WAVE2_LUNA_PARALLEL_GATE_PREFLIGHT.md` 寫入時的 `READY_EXCEPT_GEMINI` 已被隨後的實際 findings 取代，不能用它放行 gate。

| Finding | SOL 裁決與最小 owner | 狀態 |
|---|---|---|
| R008-LUNA-01 failed/cancelled 無明示原因 | FINAL §5.2 明文要求狀態與原因；原 R008 Luna worker 修改 app contract 和專用測試 | 已回修，待 SOL 合併重驗 |
| R008-LUNA-02 receipt/execution binding 僅裸 `VersionReference` | FINAL ML §2 要求 exact ID/hash/candidate/date/cost lane；依 `R008_ML_RECEIPT_BINDING_ADDENDUM.md` 補最小 immutable app receipt binding，R010/R026 保留真實 body/ML 驗證 | Luna 回修中 |
| R008-LUNA-03 `Request.options` 任意核心字典 | INV-11 禁止無型別核心擴充；因尚無 production consumer，移除泛用 options，保留具名 request/version refs | 已回修，待 SOL 合併重驗 |
| R008-LUNA-04 百分位 bp、universe count 無 range | FINAL §5.3 的 unit/range 意義；decision 專屬 worker 補 0..10000／非負驗證與獨立測試 | 已回修，待 SOL 合併重驗 |
| R008-IQA-01 任意 Enum 帶 mutable payload 穿透 | INV-08 的實際 alias 反例；app 與 decision 兩個 helper 各由其檔案 owner 限定 exact enum allowlist | 已回修，待 SOL 合併重驗 |
| R008-IQA-02 17 個 parent export identity 未全量自動驗證 | 現時 runtime 17/17 相容，但持續 oracle 只測部分；原 R008 worker 擴充專用測試逐項核對 | 已回修，待 SOL 合併重驗 |

兩個修改 worker 分別獨占 app contract／既有專用測試與 decision contract／新增獨立測試，沒有共同修改 production 中央檔；SOL 負責最後合併驗證、主實作報告整合、九檔新 SHA、Gemini 封包更新。原 `GEMINI_REVIEW_R008.md` 與 prompt 已標示暫停派送，舊 Gemini `CHANGES_REQUIRED` 仍只適用更早的回修前 SHA。R008、Wave 2 和後續 Wave 3 均不因上述局部修正或測試通過而自動 PASS。
