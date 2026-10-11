> **時點／狀態導覽（2026-10-10）**：本文的 `CHANGES_REQUIRED`、`READY_FOR_REVIEW`、`BLOCKED` 與 Wave／下游 gate 敘述，只代表撰寫當時的 implementer／reviewer／root 裁定，不是目前 disposition；目前 task 狀態看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 及 [final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)，現況看 [Project Snapshot](../../../00_core/PROJECT_SNAPSHOT.md)。原審查結論與限制保留。

# R008 SOL 範圍內回修裁決：ML availability

STATUS: CHANGES_REQUIRED_WITHIN_R008

`FINAL_TARGET_ARCHITECTURE.md` §5.2 與 `FINAL_ARCHITECTURE_INVARIANTS.md` INV-09 明定 terminal status、quality、ML availability、persistence outcome 必須分開；`FINAL_ML_COMPATIBILITY_CONTRACT.md` §2 進一步要求缺 projection 時記錄 unavailable／blocked 原因，並能區分 missing、schema mismatch、quarantined 與 source version unavailable 等結果。

目前 `app_module/recommendation/contracts.py` 的 `RecommendationExecution` 有 terminal `status`、`quality` 與 ML projection／receipt reference tuple，`SaveReceipt` 另表達保存結果，卻沒有明示的 ML availability/outcome。兩個空 reference tuple 不能區分未要求、未知、不可用、阻擋或尚未發布；`ExecutionEvent` 可放自由文字，但沒有強制的 ML 維度，不能作為 INV-09 的契約保證。這是 R008 canonical execution contract 的範圍內缺口，不是架構重新設計或 R009+ consumer migration。

請原 R008 worker 僅於 `app_module/recommendation/contracts.py`、`tests/test_recommendation_contracts.py` 與 `R008_IMPLEMENTATION_REPORT.md` 補上最小的明示、不可變 ML availability/outcome 表達和缺值原因；區分「未要求／未知」與「不可用／阻擋」，不得從空 refs 或 terminal status 猜測，亦不得把缺 projection 補成 0。維持 projection／receipt refs 的原 owner、既有 schema version/revision、DecisionBatch 欄位與 ML ordered ABI；不接 consumer、不改舊 DTO、ML 模組、writer、UI 或演算法。新驗證要涵蓋零參照下可區分的狀態、原因保存、深凍結、非法組合及原有 import 邊界。由 SOL 重新驗證並更新正式 Gemini review packet 的凍結 SHA 後，才將此輪提交獨立審查。

原先的 Gemini 並行分析僅是實作前風險提示；本裁決來自 SOL 對權威規格與實際 contract 的核對，不宣稱已有 Gemini 正式 `REVIEW_STATUS`。
