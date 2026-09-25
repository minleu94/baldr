# R008 ML receipt binding 範圍內回修裁決

SCOPE_DECISION: CHANGES_REQUIRED_WITHIN_R008

`R008_ML_BINDING_SCOPE_AUDIT.md` 核對現行 `VersionReference` 只有 `kind`、`reference_id`、可選 `version`；其本身不能封存 FINAL ML 契約要求的 exact receipt ID/hash、result ID、候選/股票代碼、決策日與成本 lane。既有 `RecommendationInferenceProjectionReceipt` 與 readback 已有更完整的 payload/hash 驗證，但 production 尚未接 canonical execution，R008 也不能把其一般 mutable payload 直接放入 sealed execution。因此 R008 需補 **app-owned、純 scalar/tuple 的不可變 receipt binding reference**；這是既有「execution 組合 ML projection/receipt typed reference 或 immutable snapshot」規格的具體化，不搬 ML feature/model schema 或 I/O。

最小欄位：ML_RECEIPT 類別的既有 `VersionReference` 作導航 ID、必填小寫 `sha256:<64 hex>` receipt hash、本次 `result_id`、decision date、非空 model candidate ID、精確且不重複的 projected stock-code tuple、可未知的 cost-scenario hash（已知時必須是同格式）。若加入 cutoff/mode/aware decision_at 摘要，只能保存已知值，不能拿目前時間或目前來源補歷史未知。`RecommendationExecution` 應保存此明示 binding tuple；對 `result_id`、可知的 `Context.as_of_date` 和 `DecisionBatch` stock-code 集合做局部一致性檢查。未知的 Context date 不得由 receipt 反向補值；不具完整證據時不能宣稱 `AVAILABLE`。零候選 completed 仍合法，但不能為它杜撰現有 writer 不會發布的 receipt；測試可驗證零列與無 receipt 的明示非 available 狀態。

R008 只驗本地純契約條件：型別、深凍結、hash 格式、重複候選、result/date/stock-code 局部不一致及 status/reference 組合。**不**讀 receipt 檔、不呼叫 builder/model、不改現有 receipt bytes/class path/cost 計算、不要求舊 receipt 新增目前不存在的 scenario ID/version，也不改 legacy DTO/consumer/writer。實際 receipt body/hash、exact candidate ID 與 symbol、decision_at/cutoff/mode、cost lane 相對於 PreparedMLInput 的真實一致性以及發布時序，由 R010 的 boundary contract 和 R026 的 production 接線驗證。R008 報告須明列這個驗證上限，不能聲稱已有端到端 ML compatibility。

允許回修 `app_module/recommendation/contracts.py`、必要的 `app_module/recommendation/__init__.py`、`tests/test_recommendation_contracts.py` 與 `R008_IMPLEMENTATION_REPORT.md`；不可再改 decision contract、parent package、舊 DTO 或 ML 內部。新增有意義的綁定錯配拒絕測試，並保持 `schema_version="recommendation-execution.v1"`/revision 1，因新 writer 尚未發布。完成後 SOL 重驗全部 R008 與相關切片，重凍結正式 Gemini packet。
