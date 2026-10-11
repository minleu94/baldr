> **時點／狀態導覽（2026-10-11）**：本文的範圍裁決與 `SCOPE_STATUS` 是當時的歷史判讀，不等同 R008 整體現行 disposition。後續具體化的 receipt binding 範圍見 [R008 ML receipt binding addendum](R008_ML_RECEIPT_BINDING_ADDENDUM.md)。[R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 將 R008 列為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`；[R031 final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 未列 R008 專項。此處僅導覽 task-level 狀態，不重裁本文特定範圍或限制；原始判讀與限制保留。

# R008-LUNA-02 ML Receipt／Execution Binding 範圍裁決

審查日期：2026-09-22。此報告為指定範圍的唯讀裁決，只新增本文件，未修改 production/test/既有檔案，也未 stage、commit 或 push。

## 裁決

R008 的 `VersionReference` 不足以滿足 exact receipt ID/hash/candidate/date/cost lane。R008 應補一個薄型、typed、immutable 的 receipt binding/reference contract，並在建構 `RecommendationExecution` 時驗證它與本次 execution 一致。這只建立 app execution 保存及核對 binding 的形狀；PreparedMLInput 的內容、實際 receipt bytes/hash 驗證、發布順序與 legacy call order 仍由 R010/R026 負責。

## 證據

`app_module/recommendation/contracts.py:167-177` 的 `VersionReference` 只有 `kind`、非空 `reference_id` 與可省略的 `version`。`_check_reference`（234-240）只驗型別及 kind。`RecommendationExecution`（386-468）把 projection/receipt 都收為 `tuple[VersionReference, ...]`，僅拒絕錯誤 kind；`AVAILABLE` 只要求兩組 tuple 非空，沒有 hash、result、candidate、date、cutoff 或 cost lane 對照。故 `VersionReference(ML_RECEIPT, "receipt-unbound")` 可作為唯一 receipt reference，並被 `AVAILABLE` execution 接受。`R008_LUNA_PARALLEL_CONTRACT_AUDIT.md` finding 02（第 40-50 行）所列反例可由現行驗證直接確認。

現行真正的 recommendation inference receipt 是 `ml_module/recommendation_inference_provenance.py:922-930` 的 frozen `RecommendationInferenceProjectionReceipt(payload, receipt_hash, receipt_path)`。Builder（766-918）把 result ID、決策日、model candidate identity、projection symbols/rows hash 與 cost scenario hash 放入 receipt；persist（933-956）以日期、candidate ID、receipt hash 建路徑並 create-only 寫入；readback（958-1012）可核對檔名與內容 hash，並按呼叫者提供的 expected 值核對日期、candidate、result、stock code 與 cost hash。這是有用的既有產物，但它不是 R008 execution field：receipt dataclass 的 `payload` 是一般 `Mapping`，型別本身沒有深凍結或 binding 驗證；核對只在 builder/readback 呼叫時成立，`VersionReference` 不要求保存那些 expected 值。Builder 亦拒絕空 projection rows（796），所以現行 writer 不會替零列 execution 發布此類 receipt。

實際呼叫路徑確認了 receipt 能提供哪些證據，也顯示它尚未進入 canonical execution contract：`RecommendationService.run_recommendation` 在 `app_module/recommendation_service.py:1023-1030` 先配置並保存 `result_id`；calibration 分支於 350-360 呼叫 `_persist_calibration_projection_receipt`；該方法（493-634）建 receipt、create-only 發布、以 hash/date/candidate/result/cost hash readback，再重讀 active identity 防止 candidate race。呼叫者把回傳的 path/hash/result ID 放進 legacy `last_run_context` 與各 recommendation 的 `calibration_provenance`（404-482），沒有轉成 `RecommendationExecution.ml_receipt_refs`。所以現行 writer 的局部校驗不能補足 R008 欄位形狀的缺口。

其他 projection 型別也不能替代該 binding：`RecommendationCalibrationProjection`（`app_module/recommendation_calibration_consumer.py:64-112`）是單股票投影列，含 cost scenario id/version/hash 與 inference provenance，但沒有 receipt ID/hash/result ID 或完整 batch binding，且 provenance 為一般 mapping；`MLShadowProjectionDTO`（`app_module/ml_shadow_projection_dtos.py:38-54`）只有日期、model/dataset、狀態及 prediction tuple，沒有 receipt hash、result ID 或 cost lane。兩者均不能作 exact receipt reference。

## R008 最小增補及驗證界線

在 `app_module/recommendation/contracts.py` 定義 app-owned frozen receipt reference/binding record，將 `ml_receipt_refs` 改為該型別的 tuple。只保存身分及驗證摘要，不收 feature matrix、model schema 或訓練資料。最低欄位為：receipt ID/穩定 locator、必填 `sha256:<64 hex>` receipt hash、`result_id`、候選 binding tuple（每筆是不透明 candidate identity 加 symbol）、`decision_at`、decision date、feature cutoff、mode，以及 typed cost lane identity（scenario ID/version/hash）。候選 tuple 必須支援空集合，以表達零候選 execution 的精確集合；不能因空集合而杜撰 receipt。

建構 execution 時至少拒絕：receipt result ID 不等於 execution `result_id`；decision date/`decision_at` 不等於 `Context`；候選身份重複、symbol 對應不完整或 symbol 集合不等於該次 ML 投影所選的 decision rows；feature cutoff 晚於 decision cutoff；cost lane 與 execution 保存的實際 cost lane 不一致；receipt hash 格式錯誤。現有 `Context`（267-321）沒有 cost lane 欄位，因此需增加一個精簡 typed cost lane reference 作 execution-side 對照；否則只能封存 receipt 自報的 lane，無法拒絕跨 lane 錯配。`DecisionBatch` 目前的 row identity 是 `stock_code`（`decision_module/recommendation/contracts.py:176-200, 301-316`），不要把 ML schema 搬入 `RecommendationItem`；候選身份的權威來源與 receipt 內容核對交由 R010/R026，R008 僅核對 reference snapshot 與可見 execution identity。

hash 的格式與本次 execution 欄位相等性可由 R008 contract 驗證；實際檔案 bytes 是否符合 hash、reference 是否解析到該檔案、receipt body 是否與 PreparedMLInput 相符，必須由 R010/R026 的現有 readback/receipt owner 驗證。`ml_projection_refs` 可保留為導航用 reference；它們不能單獨作為 receipt binding 證據。保留既有 status 語意：`NOT_REQUESTED` 不收 refs；`UNKNOWN` 可保留 refs 但不得轉稱 `AVAILABLE`；`AVAILABLE` 除 projection ref 外必須帶完整且通過 execution binding 驗證的 receipt reference。

## R010／R026 邊界與驗收例

R008 task 的 ML requirement 明定 execution 組合既有 typed reference 或 immutable snapshot，且 out-of-scope 是修改 ML contract internals。R010 負責 `PreparedMLInput` 及 adapter contract，包含 result/candidate/date/cutoff/source/dataset/feature/transform/model identity 與 cost lane；R026 負責 production preparation、infer、receipt wiring、既有 receipt identity 與發布順序。這些 owner 不需要把 feature/model/schema 搬進 R008；R010/R026 將驗證後的精簡 binding 填入 R008 reference 即可。若 R008 保留裸 `VersionReference`，下游 task 的核准範圍沒有明確承載該 execution-side binding 的 canonical 欄位，並會把 R008 自己列出的 ML acceptance 缺口推遲到後續 owner。

R008 對應測例應涵蓋：空候選的 completed execution 可用空 candidate tuple 精確綁定；result ID、candidate/symbol、日期、cutoff、cost lane 任一錯配即拒絕；hash 缺失/格式錯誤即拒絕；`UNKNOWN` 保留 refs 但不標成 available。空候選 binding 測的是 contract 不誤配；現有 builder 拒絕空 rows 的 receipt 發布行為不在 R008 改動範圍，R026 應維持其既有 fail-closed/unavailable 語意或另以相容證據處理，不得在 R008 製造 synthetic receipt。

依據文件：`FINAL_TARGET_ARCHITECTURE.md` §5.1-5.2；`FINAL_ML_COMPATIBILITY_CONTRACT.md` §2；`FINAL_ARCHITECTURE_INVARIANTS.md` INV-07、INV-14、INV-15；`REFACTOR_TASKS/R008.md`、`R010.md`、`R026.md`。

SCOPE_STATUS: R008_CHANGES_REQUIRED
