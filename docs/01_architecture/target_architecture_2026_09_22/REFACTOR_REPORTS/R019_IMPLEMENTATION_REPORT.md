# R019 純推薦 evaluator 抽離實作報告

> **2026-10-11 狀態導覽：** 本文頂部與 C3C3 段落的 `TMP-REC-02`、`TMP-NUM-01`、`TMP-ML-01 ACTIVE` 及「R020 尚未完成」等狀態是 2026-09-24 切片快照。R031 current overlay 將 R019 列為 `ACCEPTED_WITH_RULE_BRIDGE_SCOPE`；R029／migration ledger 後續將窄 `TMP-REC-01` bridge、原 bounded `TMP-NUM-01` gate 及 supported caller/profile `TMP-ML-01` 條件列為 CLOSED，並為 `TMP-REC-02` 記錄永久相容保留。這些裁定不代表所有 caller、runtime、formal data 或 production gate 完成。見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)、[R029 report](R029_IMPLEMENTATION_REPORT.md) 與 [migration ledger](../FINAL_MIGRATION_SEQUENCE.md)。

## 狀態與範圍

- TASK：R019 — 純推薦 evaluator 抽離。
- 範圍：root 已逐段驗收 3A、3B、3B2、3B3A、3B3B、C1、C2、C3A、C3B、C3C1、C3C2、C3C3 的 bounded slices；2026-09-24 root final gate 確認修訂後 R019 bounded task acceptance 全部滿足。
- 狀態：`R019 BOUNDED_COMPLETE`；evaluator core 為 `ACCEPTED_SCOPE`，`TMP-REC-01` narrow legacy rule bridge 已 CLOSED。這是 R019 task 範圍完成，不代表相關 caller／replay／ML／numeric／Wave gates 完成。
- R020 的 evaluator-core dependency gate 由此 bounded acceptance 滿足；R020 replay 實作及其自身 acceptance gates 尚未完成。
- `TMP-REC-02`、`TMP-NUM-01`、`TMP-ML-01` 仍 ACTIVE；ML capture preparation／receipt projection 由 R026 負責退出證據。Block 5、Wave 7–14、正式資料接受、production rollout、全 caller cutover 與 numeric migration 均未完成。
- R019 沒有改推薦公式、篩選順序、分數、rounding、排名政策、資料讀取政策、保存／UI／replay 算法或 ML frozen provider。
- 本輪合成測試使用 fresh TEMP／`PROFILE=test`。未讀寫正式 `DATA_ROOT`／`OUTPUT_ROOT`、正式 SQLite、正式推薦 artifacts 或模型。

依據：[R019 task](../REFACTOR_TASKS/R019.md)、[FINAL_TARGET_ARCHITECTURE](../FINAL_TARGET_ARCHITECTURE.md)、[FINAL_DATA_FLOW](../FINAL_DATA_FLOW.md)、[FINAL_MIGRATION_SEQUENCE](../FINAL_MIGRATION_SEQUENCE.md)。2026-09-24 scope split 依 C3B／C3C2／C3C3 與 parity evidence 關閉 REC-01 的 rule bridge；不宣稱 app private source-orchestration body 或 execution telemetry capture 已移除。

## 版本與共享工作樹限制

文件整理時 branch 為 `dev`，report-time `HEAD` 為 `e16f92928980a025d24bd5b023eeadf9d6a31daa`。這是文件整理時的 repository HEAD，**不是**被測 source 的 frozen revision；R019 source/test files 位於含多個其他 task 未提交變更的共享工作樹。R019 起始 HEAD 未由本報告作者固定，故不猜測或以 report-time HEAD 取代。下列 touchpoints 是責任邊界與測試入口，並非把整份 dirty diff 歸因於 R019。

## 責任搬移與保留邊界

| Slice | 責任移動／鎖定的行為 | 對應入口與證據 |
|---|---|---|
| 3A | 將候選 evaluator 的 typed seed、source-fact request/response、assessment、disposition 與 `DecisionBatch` 放到 `decision_module/recommendation/evaluate.py`；decision 只消費 facts，不讀 DB／檔案／HTTP／UI。 | `CandidateSeed`、`CandidateEvaluationOutcome`、`RecommendationEvaluationResult`、`RecommendationEvaluator.evaluate_batch_result`；`tests/test_recommendation_decision_diagnostics.py`、`tests/test_recommendation_evaluator_staged.py`。 |
| 3B／3B2 | app driver 依 decision 發出的 `NeedSourceFact` 一次讀取並回傳 typed response；service 保留候選處理順序與 PE→月營收→產業等 lazy read 時點，純 evaluator 負責既有 fixed／quantile、母體、percentile、top-N 和 stable tie 行為。 | `app_module/recommendation/evaluation_driver.py::evaluate_candidate_staged`；`tests/test_recommendation_input_read_order_characterization.py`、`tests/test_recommendation_refactor_characterization.py`、`tests/test_recommendation_evaluator_staged.py`。 Root checkpoint：fresh TEMP staged／R002／read-order／negative suite `33 passed`；後續 8-file fresh TEMP focused suite `55 passed`，broad mypy `699 source files, 0 issues`。 |
| 3B3A／3B3B | 鎖 pure decision import boundary，並以舊服務輸出固定理由文字／tag／次序、行業資料 cutoff、格式化與 regime 邊界及例外優先序。 | `tests/test_recommendation_decision_diagnostics.py` 的 transitive import/no-I/O guard；`tests/test_r019_reason_regime_parity.py` 覆蓋 explicit cutoff 不回退 current industry、83.99／84.00／84.01 對 TotalScore 80 的嚴格 `FinalScore > TotalScore * 1.05`、理由／格式／score fallback 與既有例外時點。 |
| C1／C2 | late score/regime facts 和完整 `RecommendationItem` finalization 使用 typed decision-owned contracts；canonical item 與舊 DTO 值、runtime 數值型別、`UniverseReference`、cutoff 綁定，逐候選轉換失敗不公布部分 item。 | `decision_module/recommendation/finalization.py`；`tests/test_r019_score_regime_finalization.py`、`tests/test_r019_canonical_item_finalization.py`、`tests/test_r019_full_item_parity.py`、`tests/test_r019_industry_integer_overflow.py`。 |
| C3A | 將歷史模式的 19/20 筆資料 preflight 去重：19 筆維持既有 `insufficient_history` diagnostics，20 筆才繼續 feature enrichment／scoring；不重複執行舊 evaluator 或提早做 feature/scorer 工作。 | `tests/test_r019_history_preflight.py` 比較 19 筆 pure preflight 與舊 evaluator diagnostics，並以 19／20 筆鎖定 service enrichment/scorer 呼叫次數與舊 matrix 語意。這是 history preflight slice，並非 typed body direct return。 |
| C3B | body 由 `_run_recommendation_body_result` 直接回傳 `RecommendationBodyResult`；execute 消費同 invocation 的 typed result，驗證 identity/context/DTO sidecar；canonical decision 不再從 `last_screening_matrix`／舊 DTO 重建。 | `app_module/recommendation/body_result.py::RecommendationBodyResult`、`RecommendationService._run_recommendation_body_result`、`app_module/recommendation/execute.py::execute_recommendation`；`tests/test_r019_body_service_early_returns.py`、`tests/test_recommendation_body_result.py`、`tests/test_r019_execute_canonical_handoff.py`、`tests/test_r019_closure_integration.py`、`tests/test_r019_failed_execution_context.py`、`tests/test_r019_postprocess_typed_facts.py`。測試含非空 execute→codec round trip、empty success、body error/cancel、同碼 A/B interleave，以及 legacy matrix/context 與 typed facts 衝突負控。 |
| C3C1 | 舊 `_assessments` oracle 移至測試專用 helper；production execute 不再把它當 canonical assembly path，R002 預期仍由固定測試邏輯保存。 | `tests/test_recommendation_body_result.py::_legacy_assessments_oracle`；fresh TEMP 的 body-result／decision-diagnostics／staged suite `44 passed`，另以 synthetic matrix 對照舊 production helper 的值、型別與 sidecar 行為一致。該 synthetic parity 僅為合成樣本，不外推正式資料。 |

## Before／after call graph

R019 前，R011 capture 將 service 的可變 latest-state 留作相容材料；execute 再由這些材料重建 canonical assessment/result：

```text
caller
  -> RecommendationService.run_recommendation() -> list[RecommendationDTO]
  -> invocation body 執行既有推薦迴圈並寫 last_* buffers
  -> execute capture legacy DTO / last_screening_matrix / last_run_context
  -> _assessments(matrix) 重建 typed assessments
  -> RecommendationExecution
```

截至 C3C3，domain evaluator 直接產生 typed decision 結果；execute 只驗證同次 invocation 身分並封存該結果，不由 captured `last_*`／legacy matrix 重建 canonical rule result。app 仍擁有輸入準備、來源讀取、execution/context 組合和相容 DTO 投影；invocation clocks/error/progress 由 app execution telemetry capture 提供，ML availability/projection receipt capture 由 `TMP-ML-01`／R026 列管：

```text
production caller
  -> app execute：建立 invocation view + input_session + result identity
  -> RecommendationService._run_recommendation_body_result(...)
       -> app evaluation_driver 依 NeedSourceFact 呼叫原 source reader
       -> decision RecommendationEvaluator.start/advance
       -> decision finalization + evaluate_batch_result
       -> RecommendationBodyResult(DecisionBatch, assessments, context, legacy snapshots)
  -> execute 驗證 result/context/sidecar，直接採用 body_result.decision
  -> RecommendationExecution -> codec/save/query/UI projection

LegacyService.run_recommendation() -> list projection 仍保留為相容 façade
```

R019 將決策解讀／候選排名與 typed disposition 移入 decision；沒有把來源 I/O、execution 組合、ML annotation 或保存責任搬入 decision。app driver 只讀 evaluator 當下要求的 fact，未一次預取所有 PE／月營收，也未更換 source priority、cutoff 或原 read order。

## Exact parity 與 QA 證據

R002 的 frozen baseline 是 parity oracle；它要求 exact 欄位／順序／runtime type／Decimal quantum 比較，不使用寬鬆 numeric tolerance。R002 報告記錄其 V-REC bundle `64 passed, 0 failed`，oracle 獨立執行 `8 passed`。這是既有 baseline 證據，不等同 R019 全 suite。

R019 的精確行為覆蓋如下：

- `tests/test_r019_reason_regime_parity.py`：reason code/text/tag/order、半點格式與三列截斷、明示 cutoff 下不讀 current industry fallback、regime 嚴格 1.05 邊界、缺／無效分數 matrix disposition、FinalScore fallback、ReasonEngine 例外優先於稍後分數轉換錯誤。
- `tests/test_r019_full_item_parity.py`：legacy DTO 與 canonical item 的數值值及 runtime 型別、universe identity/cutoff；late per-stock conversion error 不留下成功 DTO/item，而其他股票仍依舊 policy 完成。
- `tests/test_r019_execute_canonical_handoff.py`／`tests/test_r019_closure_integration.py`：execution 使用相同 invocation 的 `DecisionBatch`，非空 codec decode 保持 typed decision/context parity；A/B 同碼交錯不串用結果；反向 calibration prediction 不改 rule top-N／順序。
- `tests/test_r019_body_service_early_returns.py`：四種成功空分支的 typed empty batch/context/assessment identity、PIT unavailable/empty matrix 和 negative evidence 次序、quantile 零 scored 合法完成；有 scored 但低於 minimum 仍拋既有錯誤且不發布成功 BodyResult。
- `tests/test_r019_postprocess_typed_facts.py`／`tests/test_r019_scheduled_cutoff_provenance.py`：typed cohort JSON/hash 等於既有 builder、A/B identity 不可錯接、legacy context/matrix 污染不能改 canonical cutoff/cohort；scheduled decision date 由同 invocation start clock 綁定，保存 caller date 與市場 cutoff 分開。
- `tests/test_recommendation_body_result.py`：BodyResult consistency、deep freeze、sidecar、assessment ordering 與錯接 identity 的 regression；test-only oracle 保留既有輸出語意。

| 驗證 | 結果與限制 |
|---|---|
| Root R019 stage checkpoint | staged／R002／read-order／negative bundle `33 passed`；之後 8-file fresh TEMP focused route `55 passed`，broad mypy `699 source files, 0 issues`。這些數字依 root checkpoint 記錄，與之後 C3C2 snapshot 變更前後的工作樹不是同一 frozen revision。 |
| Root final bounded gate（2026-09-24） | fresh TEMP `PROFILE=test` 的 R002 V-REC 8-file route `63 passed`；R019 `test_r019_*` 加 `body_result/evaluator/execute/codec` route `157 passed`。兩筆是不同 route，不合併成單一 suite。既有 owner/reviewer bounded QA 與 broad mypy `704 source files, 0 issues` 證據仍依前列 C3C2/C3C3 記錄。 |
| C3C1 獨立 focused | `tests/test_recommendation_body_result.py`、`tests/test_recommendation_decision_diagnostics.py`、`tests/test_recommendation_evaluator_staged.py`：fresh TEMP `44 passed`；py_compile 通過；synthetic 舊 assessor oracle parity 通過。 |
| C3C2 legacy compatibility snapshot | R027 獨立 reviewer 給予 bounded `ACCEPTED_SCOPE`，其 fresh TEMP focused route `29 passed`；owner 回報 focused route `155 passed`，root 另回報 focused route `65 passed`，並回報 broad mypy `704 source files, 0 issues`。另有 `tests/test_r019_legacy_compatibility_snapshot.py` fresh TEMP `7 passed` 的契約測試記錄。這些是不同來源／範圍的證據，不是同一 frozen suite，也不代表全 R019 acceptance。 |
| C3C3 legacy capture narrowing | R027 獨立 reviewer 依 frozen source SHA 審查，未發現 P1/P2；8-file fresh TEMP focused route `73 passed`，isolated recommendation QA `7 passed`。owner 另回報 focused route `342 passed, 1 skipped`，root 回報 focused route `52 passed`。上述是不同來源／範圍的 bounded QA，不代表全 R019 acceptance。 |

上述 TEMP route 設定 `PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest `basetemp` 指向新建短 TEMP。沒有跑完整 repo pytest、正式資料 CLI、正式 scheduler 或 production output 流程。

## Retained temporary boundaries 與後續 gate

| ID | 現況 | 退出條件／本報告不主張的事項 |
|---|---|---|
| `TMP-REC-01` | **CLOSED（narrow R019 rule bridge scope）**。C3B／C3C2／C3C3 與 parity evidence 證明 canonical rule DecisionBatch／assessment／item／rule-context 直接來自同 invocation typed result，泛用 `capture['legacy_state']` 亦已移除。 | 僅關閉 legacy latest-state/matrix→canonical rule result reconstruction bridge。`LegacyCompatibilitySnapshot`、`_r011_invocation_capture`、app private source-orchestration body 與 execution telemetry capture 仍存在；clocks/error/progress 由 app execution telemetry 邊界列管，ML availability/projection receipt 由 `TMP-ML-01`／R026 列管，均不納入本 closure。 |
| `TMP-REC-02` | **ACTIVE（兩個子條件均須滿足；獨立於 R019 bounded task acceptance）**。`RecommendationService.run_recommendation() -> list[RecommendationDTO]`／`_run_recommendation_body() -> list` 相容 façade、latest-state 輸出及 v1 event/callback sidecar 仍有 compatibility consumers。 | (1) direct/dynamic/scheduled/CLI/UI caller inventory、切換、支援期結束及 list/latest-state port 移除；(2) v1 event/callback sidecar consumer inventory 完成、改接 typed execution/read model 並通過 parity後移除。兩條獨立條件缺一不可；永久歷史 decoder 保留且不列入刪除目標。 |
| `TMP-NUM-01` | **ACTIVE（獨立 numeric gate，不是 R019 bounded acceptance 的未完成項）**。此 slices 保持既有分數值、型別、quantum、排序和 rounding；沒有執行獨立 numeric algorithm rewrite gate。 | 需依 R029／獨立 numeric gate 完成原精度、rounding、ties 與所有 caller 等價證據；本次 tests 不關閉 numeric temporary boundary。 |
| `TMP-ML-01` | **ACTIVE（由 R026 負責）**。R019 後 `app_module/recommendation/execute.py` 的 MLAvailability／receipt projection 仍讀 invocation capture／legacy context。 | R026 完成 PreparedMLInput preparation／execute 接線，並提供來源可得時點、projection／receipt identity、發布順序與 unavailable fallback 的 parity／退出證據後再關閉。此 capture 不阻礙 R019 bounded task acceptance。 |
| `TMP-REC-04`／R020 replay bridge | **未完成，屬 R020／Block 3–4 後續 gate**。 | replay caller 和其模式政策依遷移序列另行完成，不因互動式 body evaluator 已接 typed results 而推定完成。 |

### C3C2：legacy compatibility snapshot（bounded ACCEPTED_SCOPE）

C3C2 將八個 legacy field 組成一份 invocation-local `LegacyCompatibilitySnapshot`：capture 整體 graph 一次 deepcopy、每次 `materialize()` 回傳整份獨立 deepcopy，保留跨欄 alias 和 dataclass provenance。production owner 已修正 snapshot capture／strict-validation timing；先前兩項失敗 fixture 未修改。R027 獨立 reviewer 給予 bounded `ACCEPTED_SCOPE`（fresh TEMP `29 passed`）；owner 回報 focused route `155 passed`，root 另回報 focused route `65 passed`，並回報 broad mypy `704/0`。以上是不同來源／範圍的 gate 證據，僅接受 C3C2 bounded scope，不等於全 R019 接受。該 snapshot 仍供相容 capture 使用；其保留不阻止 REC-01 的窄 rule bridge closure。

### C3C3：legacy capture narrowing（bounded ACCEPTED_SCOPE）

C3C3 已移除泛用 `capture['legacy_state']` dictionary；`LegacyCompatibilitySnapshot` 與 `_r011_invocation_capture` 仍保留，作為尚未退役的 app compatibility／execution capture 路徑。R027 獨立 reviewer 依 frozen source SHA 審查，未發現 P1/P2；其 8-file fresh TEMP route `73 passed`，isolated recommendation QA `7 passed`。owner 回報 focused route `342 passed, 1 skipped`，root 回報 focused route `52 passed`。以上是不同來源／範圍的 bounded QA 證據，支持 C3C3 `ACCEPTED_SCOPE`，不單獨代表整體 task gate；2026-09-24 root final gate 已另行裁定 R019 bounded task `BOUNDED_COMPLETE`。REC-01 窄 rule bridge已 CLOSED；`TMP-REC-02`、`TMP-NUM-01`、`TMP-ML-01` 仍 ACTIVE。R020 evaluator-core dependency gate 已 satisfied，R020 replay 本身尚未完成。

## 回滾與接手

- 本報告作者只增加本報告與其文件索引，不 stage／commit，不改 production、正式資料、ledger 或 roadmap。
- source paths 為多 task 共享 dirty files，不能對整檔執行 `git restore`、checkout 或 reset。若 parity 回歸，依 R019 owner 的 hunk／slice rollback 恢復該責任搬移；保留既有歷史 oracle，不調整預期值掩蓋差異。
- R019 bounded task gate 已由 root 通過。後續獨立 gate 包含 `TMP-REC-02` 兩項 compatibility caller/sidecar exit、`TMP-NUM-01` numeric parity、`TMP-ML-01` 的 R026 capture/receipt cutover，以及 R020 replay 與 Block 5；這些未完成項不撤銷 R019 bounded completion，也不代表 Wave 7–14 已解鎖。

`IMPLEMENTATION_STATUS: BOUNDED_COMPLETE` — root 已確認 R019 bounded task acceptance 全部滿足；evaluator core 為 `ACCEPTED_SCOPE`，REC-01 窄 rule bridge 已 CLOSED。`TMP-REC-02`、`TMP-NUM-01`、`TMP-ML-01` 仍 ACTIVE；R020 replay、Block 5、Wave 7–14 與相關正式／caller gates 未完成。R019 bounded completion 不宣告它們完成或 release。
