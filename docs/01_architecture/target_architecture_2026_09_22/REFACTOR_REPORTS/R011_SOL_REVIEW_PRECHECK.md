# R011 — SOL 審查前置清單

> **時點／狀態導覽（2026-10-11）：** `IN_PROGRESS` 與下列六項 fixture failure 是審查前置快照，不是目前 R011 狀態；後續 [R011 SOL 整合驗收](R011_SOL_INTEGRATION_ACCEPTANCE.md) 與 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 記錄 R011 已依 bounded scope 接受並保留必要相容性。舊 fixture 觀測仍是當時範圍的歷史紀錄，勿解讀成目前 Gate verdict。

狀態：`IN_PROGRESS`。本檔只記錄唯讀稽核發現與驗收條件，不代表 R011 已通過。

## 必須由實際 diff 與測試證明

1. 舊 public `run_recommendation` 簽名、例外訊息、DTO 清單順序、數值型別與 Decimal exponent 遵守 R002 oracle；private body 只有一份，`execute` 不反呼叫 façade。
2. R008 execution 在同一次 invocation 返回前封存；A/B 交錯及返回後修改來源、`last_*`、DTO 巢狀清單／字典，均不能改變各自的 execution。舊 caller 仍只看該次 façade 的 `last_*` 相容投影。
3. R008 決策欄位不含舊 DTO 的價格、分項分數、產業、自由格式理由或逐股票 ML 欄位；暫時 legacy 投影需保留原型別與原始 JSON shape，不得由 DecisionBatch／後續 live state 反推。`TMP-REC-01/02/06`、`TMP-NUM-01` 登錄及退休 owner 必須明確。
4. 參數驗證失敗在原 body 重置 `last_*` 前；provider 失敗在重置後、context 建立前。新 terminal outcome 可明示失敗，但舊 façade 的例外與觀察狀態不能漂移。空結果是 completed，取消／失敗的 partial evidence 不可誤作可採用推薦。
5. 真實 ML receipt 在寫檔／readback 後仍可能因 post-write active identity race 而失敗。execution 必須保留可證明的同次寫入副作用與錯誤，不得重讀 latest pointer、掃目錄或用 mtime 猜 binding；成功時檢查 result_id、date、candidate、hash、cost、股票集合與 receipt body。現有 calibration race fixture 在寫入前分支終止，不足以覆蓋此窗口。
6. Per-invocation view 對 `_fundamental_sqlite_provider`、`_fundamental_provider_initialization_attempted` 與 `_personalization_execution_clocks` 的處理不可改變來源／例外時序，且不能跨 invocation 污染。

審查命令依 `REFACTOR_VALIDATION_MATRIX.md` 的 R011 列：`V-REC`、`V-EXEC`、focused `V-ML-SMALL`；另跑 R008/R009 codec roundtrip、`py_compile`、scoped mypy、`git diff --check`。實作者報告與獨立 Luna review 凍結後再填入實際結果及最終判定。

## 既有 fixture gap（待 gate 分帳）

SOL 預跑 `test_recommendation_refactor_characterization.py`、`test_recommendation_execution_state_characterization.py`、`test_recommendation_service_calibration_integration.py`：`27 passed, 6 failed`。六個失敗皆在 `tests/natural_session_source_fixture.py:130` 建立 natural evidence 時，因既有 `evaluation_day=2026-06-22` 未晚於 exact-20 session endpoint，於進入 R011 service 之前拋 `ValueError`。六個受影響測試為 `test_real_consumer_producer_advice_workbench_ui_path`、`test_public_service_real_builder_saves_result_and_reverse_reads_receipt`、`test_active_training_label_contract_missing_or_mismatched_fails_closed`、`test_active_training_label_contract_missing_from_provenance_fails_closed`、`test_real_consumer_rejects_future_research_candidate_context`、`test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation`。測試與 fixture 檔均 clean；fixture 上次提交為 `5c6eee95`（2026-09-19）。R011 不修改此既有 fixture/golden，後續 gate 將精確區分此基線 gap 與新增回歸。
