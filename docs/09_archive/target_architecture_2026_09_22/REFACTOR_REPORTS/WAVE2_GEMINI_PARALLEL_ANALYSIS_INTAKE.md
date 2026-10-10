> **歷史封存警語（2026-10-10）：**本文是 Wave 2 分析收件與 R008 gate 判定的歷史快照；其中 SHA（如有）、scope、待審狀態與結論只代表當時快照，不得據此重派、重跑或視為目前 gate／授權。現況請以 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 與 [REFACTOR_MODEL_ASSIGNMENTS](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md) 為準；後續 checkpoint 見 [WAVE2_RESULT_ID_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE2_RESULT_ID_CHECKPOINT.md) 與 [WAVE3_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE3_CHECKPOINT.md)。

# Wave 2 Gemini 並行分析收件與 R008 gate 判定

## 收件性質

使用者帶回的 `WAVE2_PARALLEL_ANALYSIS` 原文已存於 `WAVE2_GEMINI_PARALLEL_ANALYSIS.md`。其結尾為 `ANALYSIS_STATUS: COMPLETE`，且自述為實作前唯讀風險分析，**不是**凍結後的 `GEMINI_REVIEW_R008.md` 正式獨立審查。故本次收件不構成 `REVIEW_STATUS: PASS`，R008 仍為 `READY_FOR_GEMINI_REVIEW`；Wave 2 尚未完成，Wave 3 不釋出。

原文 SHA-256：`E91AE7A49D8E7BD869593DC92BE08811B7280A5BF8E04EA9A517A2EA78A93E98`。原文所列 R002／R003／R007 三個 characterization 檔的 29 個測試，SOL 已獨立重跑，`29 passed`。此結果僅驗證該測試切片，不能替代 R008 的正式 diff review。

## 對凍結 R008 的審查意見

1. **需要正式核對的風險：ML availability。** `FINAL_TARGET_ARCHITECTURE.md` §5.2 與 INV-09 要求 terminal status、quality、ML availability、persistence outcome 是不同維度；`FINAL_ML_COMPATIBILITY_CONTRACT.md` 要求缺 projection 時保留 unavailable／blocked 原因，不能補 0。現有 `RecommendationExecution` 有 `status`、`quality`、`ml_projection_refs`、`ml_receipt_refs`，保存 outcome 另由 `SaveReceipt` 表達，但沒有明示的 ML availability/outcome 欄位。空參照無法單獨表示「未啟用／無候選／缺資料／schema mismatch／隔離／來源版本不可用」。請 Gemini 正式 review 判定：R008 既定範圍是否已足以明示此維度，或需在原 contract scope 內補足；若需修正，給最小且不改 ML ABI 的具體方案。SOL 不以這份實作前分析自行改動已凍結的 R008 檔案。
2. **應核對而不能直接套用的欄位建議。** 分析把 `close_price`、`price_change`、三種子分數及 `industry` 全部列為 `RecommendationItem` 的必備直接欄位。權威 §5.1 只明定 stock identity、rule score、factor contributions、rank/universe、reasons 與可選 confidence；R008 尚未做 legacy DTO adapter。這份欄位映射屬分析者推論，應由正式 review 依權威規格與實際轉換需求判定，不能直接擴張 canonical schema。
3. **過時的檔案範圍。** 分析稱 R008 只能新增檔案；後續 `R008_SCOPE_ADDENDUM.md` 已基於實測准許兩個 parent `__init__.py` 的窄 lazy-export 修正及一個 import-contract 測試的載入時序 oracle 修正。正式 review 須依修訂後的 R008 規格與實際 diff 評估。
4. **failed/cancelled 的 partial decision。** 分析認為可附帶 partial decision 供診斷；權威 §5.1 只說 failed/cancelled「可無 decision」且 partial 只能診斷、不得當 completed 發布。R008 現拒絕非 completed 的 `DecisionBatch`，診斷另由 events/quality/failure reason 承載。是否足夠應由正式 review 判定，分析意見本身不是架構裁決。

## 下一個 gate

正式封包是 `REFACTOR_DISPATCH/GEMINI_REVIEW_R008.md`，可複製 prompt 在 `REFACTOR_DISPATCH/WAVE2_GEMINI_REVIEW_PROMPTS.md`。Gemini 須核對凍結 SHA、實際 diff、R008 規格、相關不變條件及上述 ML availability 疑點，最後只給 `REVIEW_STATUS: PASS`、`CHANGES_REQUIRED` 或 `BLOCKED`。SOL 收到正式結果後再核對 repository 與測試，決定 R008/Wave 2 gate。

INTAKE_STATUS: ANALYSIS_RECEIVED_FORMAL_REVIEW_PENDING
