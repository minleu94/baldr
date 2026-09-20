# Personal Delivery Activation QA（2026-09-18）

## 結論

本次查核確認 personal capture、save、technical delivery ACK、projection read 與 evaluation read 的正常接線已存在。對**正常 UI 的 personal delivery contract** 而言，第一個阻擋使用者開始累積 scope-linked delivered prediction 的條件，是目前 calibration active pointer 處於 `rule_only`，且沒有可驗證的 active candidate；因此 `RecommendationService` 無法產生 verified calibration projection receipt，save 流程會安全地保留普通 recommendation result，而不建立 personal capture。這個 active gate 只限定正常 UI 的 personal delivery 路徑，不阻擋獨立的 shadow research read model。

這是目前的 promotion／authority 狀態缺口，不是 human action 必填、不是 evaluator 將無 action 判定為 prediction 失敗，也不是本次 scope personalization 模組內可安全修補的 save bug。本次沒有修改 pointer、promotion、broker、scheduler、正式 D／DB 或任何 global authority。

## 查核邊界

- 起始版本為 `ff2af5f3ca0d0c55166cff062ff39fc1f63827ec`；開始查核時工作樹乾淨。
- 本次只做 personalization contract、projection、recorder、read service、save coordinator 與正常 MainWindow save/readback 的檢查。
- 產出的唯讀證據放在 `output/qa/personal_delivery_20260918/`；該目錄是 QA 暫存輸出，不是正式資料。
- 查核期間觀察到其他工作中的變更：`scripts/scheduled/run_scheduled_decision_evidence_capture.py`、`tests/test_scheduled_decision_evidence_capture.py` 與 `docs/06_qa/DAILY_CAPTURE_RECOVERY_2026_09_18.md`；本次未修改它們。
- `APPLICATION_MANUAL.md`、`PROJECT_SNAPSHOT.md`、shared state 與正式 D／DB 均未修改。

## 第一個阻擋點

唯讀檢查 `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\recommendation-calibration-active-pointer.json` 得到：

- `status = rule_only`
- `candidate_id = null`
- `formal_order_allowed = false`
- `decision_id = recommendation-calibration:2026-09-14:emergency-rollback`
- pointer SHA-256：`1B156104152F74DBC38C588C5C5C3107F2A186E2A62F8DBB7DB47BB45F94C1A1`

以 `build_default_recommendation_calibration_consumer()` 重新載入目前日期 `2026-09-18` 時，consumer 回報 `rule_only`，`active_identity()` 為 `None`。`RecommendationService._persist_calibration_projection_receipt()` 對沒有 `candidate_id` 的 identity 直接不建立 receipt；接著 `PersonalizationSaveAdapter.bind_result()` 沒有 verified receipt 時不附加 capture，仍保留普通 save 的既有行為。

因此目前不能把下一步寫成由工程或 root 直接重新建立 active。只有既有 authority／promotion policy 的全部條件通過、合法 natural evidence receipt 可驗證，才可採用 active candidate／projection receipt；工程 QA 不得以批准替代來源證據。本任務不改 pointer，也不以測試資料或人工回填繞過這個 gate。

## 真實 scope 的唯讀結果

使用既有 D root、scope `local_research_scope_v1` 與 as-of `2026-09-18` 執行 `scripts.inspect_personalization_sources`，報告為：

- `source_consistency_status = verified`
- `source_completeness_status = verified`
- projection 數：438
- `population_only_count = 33`
- `prediction_available_count = 0`
- `prediction_unavailable_count = 405`
- `linked_prediction_count = 0`
- `action_recorded_count = 0`、`action_not_recorded_count = 0`
- `evaluation_row_count = 0`、`natural_forward_count = 0`
- cohort：`pending_or_insufficient`

報告位於 `output/qa/personal_delivery_20260918/real_scope_read_report.json`，SHA-256 為 `5158BF0370196A931EC3CC54701411FA383908C429259DC37907976E44AEBB3B`。報告顯示目前歷史資料沒有可合法回填的 personal prediction：較新的 rows 缺 scope／capture，較舊的 scheduled rows 缺決策時間或 producer context。這些 rows 不應以保存時間、holding、portfolio 或 source 推測 scope，也不應回填 capture time 或 natural outcome。

## Rollback decision 與 shadow candidate 的唯讀查核

`2026-09-14` 的 emergency decision receipt 明確記錄 `decision=rollback`、`reason=explicit_emergency_rollback`、`data_dependency_status=failed`、`outcome_dependency_status=failed`，且沒有 candidate／natural evidence。後續 `2026-09-14`、`2026-09-15` 與 `2026-09-17` 的一般 decision 都是 `retain_current`，原因是 `natural_forward_evidence_receipt_missing`。因此目前 `rule_only` 是既有決策 receipt 的結果，不是 personal capture 模組自行阻擋。

shadow challenger `rec-cal-29c1b6129396a3885a89d080` 確實存在且可在隔離研究 lane 唯讀讀取：artifact loader 回報 `shadow_model_ready`，但 candidate metadata 同時標示 `shadow_only=true`、`production_eligible=false`、`production_action_allowed=false`、`formal_candidate_eligible=false`、`forward_evidence_eligible=false`。既有 capture verifier 以檔案為分母，對 shadow root 的 8 個 capture 檔案驗證出 7 個合法 candidate capture；這 7 個檔案合計 21 rows。另 1 個較早 capture 因 technical publication availability 缺失而 fail-closed。這些是候選研究證據，不能當成 active 或個人 delivered evidence。

使用既有 `RecommendationLearningEvidenceProjectionService` 對 `2026-09-17` 做唯讀 inspect，candidate lane 為 `pending`、`capture_status=recorded`、`capture_count=7`、`recorded_row_count=14`、`matured_sample_count=0`，reason 是 `no_capture_rows_have_naturally_matured`；active lane 則是 `not_applicable`，diagnostic 為 active pointer `rule_only`。這裡的 `capture_count=7`／`recorded_row_count=14` 來自 `latest_status` 的 candidate live capture read model：前者是 capture 計數，後者是該最新 live snapshot 的 row count；它不是 verifier 讀到的 7 檔 21 rows 的去重結果，也不能與 21 rows 相加或混稱為可用 personal 樣本。現有 read model 沒有把其餘檔案的 row union 宣稱為當前 recorded rows；其成熟度仍是 0。這證明 shadow candidate 有合法的研究 read model，但還沒有 natural credit。

正常 Recommendation UI 的 `RecommendationCalibrationConsumer` 只從 global active pointer 讀取；它不讀 `challenger/current.json` 或 candidate capture。故現況不是「完全沒有 shadow prediction」，而是 shadow prediction 只能停留在既有 read-only research projection，不能沿目前 personal save contract 變成 delivered prediction。`PersonalizationSaveAdapter` 要求 RecommendationService 提供 active candidate 的 verified projection receipt；直接拿 shadow capture 代替會破壞 candidate／receipt／decision provenance，契約不允許。

目前有兩個安全選項：

1. **維持 population／研究等待。** 保持 `rule_only` 與 global active 不變，讓已存在的 shadow captures 等待自然 maturity；read-only projection 持續顯示 `pending`，不產生 personal delivery 或 adoption credit。
2. **明示研究 projection。** 沿用既有 shadow capture verifier 與 `RecommendationLearningEvidenceProjectionService` 顯示 candidate 的研究結果，明確標為 shadow／research／pending。這不改 active pointer、不改正常 UI 的 global consumer、不寫 personal D，也不推動 adoption；若未來要把 candidate 連到 user scope，需另訂明示的 research receipt／producer contract，不能由工程批准代替 authority evidence。

這個選項判斷不要求現在詢問使用者 scope；在 active gate 尚未通過前，scope 選擇不是當下阻擋點。

## 正常產品流程接線證據

使用實際 `MainWindow`、實際 `RecommendationView`、window-owned `JournalService`、實際 repository 與正常 save entry，僅將 fixture producer context 綁到一次隔離 probe；結果如下：

- normal save entry clicked、result readback、journal ACK readback 與 projection readback 均成功。
- `projection_status = linked_prediction`、`delivery_status = delivered`。
- `action_state = not_recorded`、`journal_ack_count = 1`、`late_delivery = false`。
- projection read 不改寫 result JSON。
- Qt process exit code 為 0，沒有殘留 worker。

probe 輸出為 `output/qa/personal_delivery_20260918/mainwindow_probe.json`，SHA-256 為 `61D6FCE81A42D4AEA66232C0AFB8E54CF0ACBD7F03FFCFC1BAC7C02AED6735A0`。這是工程接線證明，不是正式 D 的使用者樣本；fixture context 不得轉成正式 personal evidence。

本次以外層 PowerShell launcher 執行 probe 的原始 command result 也回傳 OS exit code `0`；上列 `app_exec_returncode` 與 `process_exit_code` 是 probe 留存的實際執行欄位，沒有用它們反推或取代外層 launcher 結果。

程式語意也符合驗收邊界：

- `delivery_at > human_decision_at` 才會標記 late delivery；沒有 human action 時不會因此否定已 delivered 的 prediction。
- read service 的 evaluation row 不要求 action；action 是另行計算的 utility denominator。
- `action_not_recorded` 是合法的 prediction／delivery 狀態；只有使用者明確採取 action 時，才由 `PersonalizationDecisionRecorder` 寫入 action。
- technical ACK 只證明系統交付，不代表 adoption、交易或 natural outcome。

## Scope 邊界

目前程式已有 `local_research_scope_v1` 這個本機 research scope。它是明示的研究 scope envelope，不是帳號、人類 identity，也不應從 holding 或 portfolio 推導。這個 scope 選擇目前不構成阻擋；只有既有 authority gate 通過、RecommendationService 取得 verified projection receipt 後，才需要在正常產品流程中確認是否採用該 local research lane。沒有 active receipt 時，系統應保持普通 save，避免製造無 provenance 的 personal capture。

## 驗證命令與結果

已完成下列 bounded tests：

```text
\.venv\Scripts\python.exe -m pytest tests\test_personalization_contract.py tests\test_personalization_projection.py tests\test_personalization_read_service.py tests\test_personalization_save_integration.py tests\test_personalization_action_recorder.py tests\test_personalization_generation_cli.py tests\test_recommendation_save_coordinator.py -q -o addopts=
70 passed, 1 warning

\.venv\Scripts\python.exe -m pytest tests\test_recommendation_service_calibration_integration.py -q -o addopts=
12 passed, 1 warning
```

warning 僅為 pytest cache 權限提示；本次沒有 Python source change，故沒有新增 compile／mypy 結果。MainWindow probe 的結果與 process exit code 見上節。

## Root 審核邊界與 rollback

本次可接受變更只有此 QA 文件與 ignored 的唯讀 QA output。若不採用文件，可移除 `docs/06_qa/PERSONAL_DELIVERY_ACTIVATION_2026_09_18.md`；`output/qa/personal_delivery_20260918/` 可由 root 依需要清理。沒有 source code、pointer、formal D／DB、scheduler 或 global state 變更可 rollback。

後續只有既有 authority policy 通過並產生可驗證 receipt 後，才可從新的正常產品操作開始累積 evidence；不得把本次歷史 rows、shadow capture、fixture probe、technical ACK 或既有 holding 當作使用者 action、natural outcome、adoption 或 calibration success。
