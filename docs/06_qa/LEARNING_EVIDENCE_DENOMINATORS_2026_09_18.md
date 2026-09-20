# Learning Evidence Denominator QA — 2026-09-18

## 範圍

本切片只檢查既有 `RecommendationLearningEvidenceProjectionService` 的 learning evidence read model，沒有修改 UI、DB、active pointer、scheduler 或 promotion authority。變更集中在 service DTO／projection 與其專屬 focused tests；BankTaiwan lane 沒有納入本次讀取，數字不可與其他 lane 混用。

## 目前唯讀結果

讀取 `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning` 的 `latest_status.json`（decision date `2026-09-17`），候選為 `rec-cal-29c1b6129396a3885a89d080`，cost lane 為 `legacy_fixed_bp`：

| 口徑 | captures | rows | distinct decision dates | 用途 |
|---|---:|---:|---:|---|
| 既有 capture verifier 原始結果 | 7 | 21 | 3 | 七個同候選 capture 通過 verifier；仍未做 projection 的跨 capture 去重／衝突排除 |
| projection conflict-free 累積分母 | 2 | 16 | 2 | 同候選、同 cost/horizon/source 合約，排除衝突後可列入此 lane 的 valid prediction 分母 |
| latest snapshot | 1 | 14 | — | 最新 capture 的 snapshot row count，與累積分母分開呈現 |

原始 captures 共 8 個 JSON；其中 1 個 capture verifier 失敗且屬其他 candidate，因此不計入本候選 lane 的 invalid count。本候選 projection 的 `invalid_capture_count=0`、`capture_conflict_count=5`、`capture_scan_status=complete`。`16 rows / 2 dates` 是此候選 lane 的保守、衝突排除後分母，不是原始 verifier 的 `21 rows / 3 dates`，也不是 BankTaiwan 的樣本數。

目前 projection 為 `pending`：`matured_sample_count=0`，`pending_prediction_row_count=16`、`pending_prediction_decision_date_count=2`，狀態為 `awaiting_typed_natural_verification_with_scope_conflicts`。pending 在此表示 valid capture 等待 typed natural verification；不能由這個欄位推斷每一列都尚未達 maturity。

latest snapshot 的 lane、candidate、cost scenario 與 20 trading-day horizon 均獨立輸出。`capture_count` 代表衝突排除後的 verified capture 數，`recorded_row_count` 代表 latest snapshot rows；累積 rows/dates 使用新增的 `valid_prediction_*` 欄位，避免把兩個分母混成每日一筆。

## 去重、衝突與掃描邊界

- 同一 row content 跨 capture 重複時只保留一次 valid row，不能因 capture 數增加而膨脹分母。
- 同一 `symbol + decision_date` 出現不同 fingerprint 時，相關 captures 整組標為 conflict 並排除；先後讀取順序不改變結果。duplicate capture id 若 hash 不同也同樣保守排除。
- capture path 去重、capture id 去重及 latest snapshot metadata 分開處理；無法通過既有 verifier、path/hash 不可信或 source contract 不 ready 的 capture 不會產生 valid rows，invalid 只以 capture count 呈現。
- bounded scan 的上限可注入。`capture_scan_limit=0` 明確回報 `truncated`，不回報 `listed_only`；掃描被截斷時 next-gap 會標示累積數字可能不完整。

## policy binding

本次 pending snapshot 沒有 production positive typed natural receipt proof，因此 `policy_binding_status=unknown`，`next_gap` 不計算 adoption samples／dates 缺口。receipt bytes 只讀一次，只有既有 authority verifier 的成功 `receipt_hash` 與同一份 bytes 的 hash 相符，且 payload 的 policy hash 通過固定 authority policy 比對，才會暴露採用門檻；capture 或 receipt 自報相同 hash 不能取代這項證明。focused test 已覆蓋 forged/self-reported matching hash 仍維持 unknown；本輪沒有擴充 authority 或建立新的 ledger。

## 驗證

```text
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_learning_evidence_projection.py -q -o addopts=
17 passed, 1 PytestCacheWarning（僅 .pytest_cache 寫入權限）

.\.venv\Scripts\python.exe -m mypy app_module\recommendation_learning_evidence_projection_service.py
Success: no issues found in 1 source file

.\.venv\Scripts\python.exe -m py_compile app_module\recommendation_learning_evidence_projection_service.py tests\test_recommendation_learning_evidence_projection.py
passed
```

raw read-only projection 與驗證輸出存於 [`output/qa/learning_denominators_20260918/`](../../output/qa/learning_denominators_20260918/)，其中 `projection_read_only.json` 保留來源、完整 projection、原始 verifier counts、policy 狀態與副作用聲明。

本切片沒有寫入正式資料、DB、pointer、scheduler 或 UI；未建立 branch、worktree 或 commit。若需 rollback，僅需依 review 保留／還原本切片的 service、專屬 test、QA 文件與 ignored raw output，無需資料重建。
