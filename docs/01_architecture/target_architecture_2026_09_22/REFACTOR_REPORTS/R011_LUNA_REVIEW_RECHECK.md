# R011 Luna review recheck

> **時點／狀態導覽（2026-10-11）：** 本文的 `REVIEW_STATUS: CHANGES_REQUIRED` 是針對當時凍結版本的歷史裁定；後續 [R011 SOL 整合驗收](R011_SOL_INTEGRATION_ACCEPTANCE.md) 記錄非有限數值轉字串問題已修正，且 [R011 Luna 最終複審](R011_LUNA_FINAL_REVIEW.md) 為 `PASS`。目前 task disposition 以 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 為準；R029 的保留相容範圍見 [R029 report](R029_IMPLEMENTATION_REPORT.md)。本 recheck 保留原始發現，不代表整體 refactor 或其他 Gate 通過。

REVIEW_STATUS: CHANGES_REQUIRED

## 凍結版本與範圍

本次只審查 R011，不納入其他 main 工作樹變更。審查時 HEAD 為 `85e2be8a2a93f5e0eef989710efa57f62bfe9109`，與本次 R011 檔案 SHA 對應。

| 檔案 | 實際 SHA-256 | 派工指定 SHA-256 | 結果 |
|---|---|---|---|
| `app_module/recommendation_service.py` | `4C82F56243918A33034247BF51C2E671EBDD52F7CA0013B1A6801F5F5BA5EE90` | 同左 | 符合 |
| `app_module/recommendation/execute.py` | `98F27DDBCC4A3113E89076520B677804B2CA4221209BC464A962FEE8B9012519` | 同左 | 符合 |
| `tests/test_recommendation_execution_use_case.py` | `8D0C6E2155736D6D5C89CCE1E1641C89111CC34D15C273F524C722C6F54B6791` | 同左 | 符合 |
| `REFACTOR_REPORTS/R011_IMPLEMENTATION_REPORT.md` | `B1CE2101473627B5CB406D592ECFA438205A6B94A2FD6D0595D1FB0A7ACA6AB1` | 同左 | 符合 |

本 recheck 針對前次 review 的兩項 finding，並核對新報告中的 TMP-REC-01 duplication retirement note。沒有修改 production/test 檔案，也沒有開始 R012。

## 前次 finding 的結果

### R11-REV-01 — unknown evidence 與非字串 key

**已修正。** `execute.py:831–905` 現在對 mapping key 要求 `type(key) is str`，對 Mapping/list/tuple 做循環偵測；DataFrame、callback、自訂物件及其他未列入 allowlist 的型別會 raise `TypeError`。`tests/test_recommendation_execution_use_case.py:227–242` 覆蓋 DataFrame、callback、自訂型別、`{1: ..., '1': ...}` key collision 的拒絕，也確認受支援 NumPy scalar 轉換。

這和 R008 `decision_module/recommendation/contracts.py:97–108` 的字串 key 與型別白名單一致。未發現 unsupported object 再被字串化的路徑。

### R11-REV-02 — TMP-REC-06 paired harness

**已修正，且在單一計算 body 的架構下兩路有足夠獨立性。** `test_tmp_rec06_paired_legacy_and_execution_lanes_match_with_isolated_side_effects` (`tests/test_recommendation_execution_use_case.py:245–320`) 建立兩個獨立 service，使用分開的 `tmp_path` 根、固定輸入與固定時間：legacy lane 直接呼叫保留的 `_run_recommendation_body`，new lane 走 `run_recommendation → execute_recommendation`，再比較完整 DTO payload/數值型別/次序及 `last_*` context、screening matrix 與負面證據資料。這兩路分別經過原始 body 呼叫形狀與新 execution adapter；計算 body 必須共用，否則會違反 single-body invariant。

另以唯讀 AST 比對派工基準 commit `5e2d2efcfdc91c5e29810eb823b1c582199a44cc` 的舊 `run_recommendation` 與新 `_run_recommendation_body`：兩者 856 行，正規化函式名稱後 AST 完全相同。這確認 paired harness 的 legacy lane 呼叫的是未改算法語意的原 body。R002 characterization 提供固定 golden outputs，補足 fixed/quantile、ties、缺值與負面證據等行為 oracle；兩者不依賴 facade 與 execute 彼此互相比對來建立全部數值基線。

### TMP-REC-01 — raw matrix 重複表示

**已具名列管，非本次阻擋。** implementation report `:47` 明確說明 raw screening matrix 同時出現在 compatibility event 與 `CandidateAssessment` evidence 是暫時重複表示，由 R019 consolidation 移除，保留 typed assessment，event 只留下仍需要的 legacy-only evidence。此 owner 與 TMP-REC-01 的 R019 退出方向一致。移除前應把兩份表示視為同 invocation 的同一份資料，不作獨立來源證據。

## 新發現 R11-REV-03 — 非有限數值仍被轉成合法字串

`execute.py:841–866` 對 `Decimal`、Python `float` 與 NumPy floating 的非有限值回傳 `str(value)`。已執行最小重現：

```text
_safe_contract_value(Decimal('NaN'))  -> 'NaN'
_safe_contract_value(float('inf'))    -> 'inf'
_safe_contract_value(np.float64('nan')) -> 'nan'
```

這避開 R008 `_freeze_value` 對非有限 `Decimal` 的拒絕，也把非法數值由數字型別改寫成允許的文字 evidence。既有合法 legacy matrix 不需要這個轉換：`app_module/recommendation_run_support.py:46–48` 已將 `observed_value`、`required_value`、`total_score` 在 matrix 建構時轉成文字；receipt candidate identity 也在 receipt normalization 時轉為 JSON-ready payload。若既有欄位本身是文字 `"NaN"`，新 converter 會原樣保留文字，因此拒絕數值型 NaN/Inf 不改變 legacy 字串語意。

此缺口違反 INV-06 對合法數值及 INV-11 對 typed contract fail-closed 的要求。最小修正：有限 Decimal/float/NumPy floating 照目前 explicit conversion；數值型非有限值一律 `TypeError` 或 `ValueError`，不得降格為文字。最小驗收需拒絕 `Decimal('NaN')`、`float('inf')`、`np.float64('nan')`，並確認字串 `"NaN"`、有限 NumPy scalar、`Decimal('70.0100')` 及現有 recommendation matrix fixtures 仍通過。

## 驗證

- `tests/test_recommendation_refactor_characterization.py`, `tests/test_recommendation_execution_state_characterization.py`, `tests/test_recommendation_execution_use_case.py`, `tests/test_recommendation_execution_coordinator.py`：**32 passed**。
- `tests/test_recommendation_contracts.py`, `tests/test_recommendation_execution_codec.py`, `tests/test_r004_recommendation_persistence_characterization.py`, `tests/test_refactor_ml_compatibility_baseline.py`：**60 passed**。
- `py_compile`：通過；R011 兩個 source file 的 `mypy --follow-imports=skip`：**無錯誤**。
- 手動 non-finite converter 反例：三種非有限 numeric 都被字串化，因此確認 R11-REV-03。

完成 R11-REV-03 修正並收到新的凍結 SHA 後，需重跑受影響的 evidence/contract 測試，並再核對實際 diff 與 hashes。此報告只對上表版本有效。
