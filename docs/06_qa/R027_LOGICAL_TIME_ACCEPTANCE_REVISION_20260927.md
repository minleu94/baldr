# R027 logical-time acceptance revision（2026-09-27）

## 決策與範圍

使用者於 2026-09-27 接受獨立的 R027 logical-time acceptance revision（B）。這份 addendum 只記錄新版本及其結果；原 R027 strict acceptance、9/23 frozen oracle、原 comparator、848 與後續 strict receipts 均維持原值。原 strict verdict 仍是 `INCONCLUSIVE`，不回填成 PASS。

新版本固定 source-owned publication phase call/token 的呼叫次數與順序，並保留所有 raw OS clock、mtime、WAL/SHM 與 reader observation。這些獨立 process 的 raw physical readings 不作跨 process exact equality 條件。每個原 snapshot phase 的 SQLite main DB raw bytes、SHA-256、size 仍須 baseline/candidate exact；亦須驗 committed visibility、兩次 fresh query-only reader 的 schema/row/key/source identity、close/reopen readback，以及取消、失敗與 recovery。Token 僅代表既有 source phase 呼叫，不是產品 publication timestamp；不新增 artifact schema、不使用 `os.utime`、不提前 checkpoint，也不排除 retained raw evidence。

## 新版本實測

Root 於 `r027_logical_time_root_full8_20260927.json` 執行完成；summary 記錄 natural exit 0、gate/runner verdict `PASS`、strict historical verdict `INCONCLUSIVE`。8 個固定 case 全部 PASS：`clean`、`same_input_rerun`、`partial`、`unchanged`、`cancel_resume`、`source_changed_during_run`、`failure_recovery`、`publication_failure_recovery`。8 個控制亦全部成功辨識：3 個真 source/callsite mutation、1 個 main DB `user_version` mutation，以及 4 個明確標示為 receipt-field 的合成變異（artifact bytes、row identity、SQLite visibility、recovery outcome）。合成 receipt control 只驗證 gate 能拒絕被篡改的證據，不冒充 production source fault。

原始 receipt SHA-256 為 `5e1f162cc569c49797d0f9fc9fc72b6d7f4fba41734afcec627a6d9684f372c0`；summary SHA-256 為 `e39f7d2e5ccb3e2a6b8d30be3d595ad2b06a6837ab9a56f9e3689bc221b58980`。該次 selected source scope 為 3,303 個檔案，前後無 scope difference；Direct15、五個 pinned fixtures、HEAD 與 git status custody 均穩定。完整 raw receipt、summary 及 root start decision 位於 `output/qa/refactor_completion_20260927/`；root decision SHA-256 為 `9e13ca0b7feb7d647eb7d33be3c6ae0c46c66780c2c5f0ebf3fa8ad1454fd5df`，記載獨立 reviewer 接受 source/full8 evidence，並授權 R028 implementation 開始。

## 與原 strict gate 及 R028 的關係

新 revision PASS 是使用者接受的替代驗收版本，不能改寫原 strict gate 的 `INCONCLUSIVE`、舊 9/23 oracle 或舊 full8 的 raw observations。舊 post-Qt strict receipt仍為 8/8 `INCONCLUSIVE`、947 strict differences；raw OS clocks、mtime 及 WAL/SHM/reader values仍保留於原 receipts。舊 848 differences亦保留在其歷史版本，不由新版本重建或覆寫。

Root最初依新revision PASS與獨立review裁定R028可開始實作；其後已根據R028 frozen source diff、full8與source/runtime獨立review正式接受scoped production migration。原strict gate仍INCONCLUSIVE，沒有回填舊verdict。R031 attempt6 current 288-path relevant regression與mandatory checks已由root接受；本段為提交前snapshot，staged review與commit結果依Git history及root最後交付；正式scheduler、模型promotion、正式資料重建均未因此獲准。

## 相關證據

- [R027 原始實驗與 strict 歷史報告](R027_TECHNICAL_PUBLICATION_ML_IDENTITY_ISOLATION_20260923.md)
- [R028 task 與 2026-09-27 dated decision](../01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R028.md)
- [使用者接受的 implementation track](../../output/qa/refactor_completion_20260927/USER_ACCEPTED_IMPLEMENTATION_TRACK_20260927.md)
- Raw receipt：`output/qa/refactor_completion_20260927/r027_logical_time_root_full8_20260927.json`
- Summary：`output/qa/refactor_completion_20260927/r027_logical_time_root_full8_summary_20260927.json`

## 2026-09-27 R028 implementation acceptance

Root已正式接受由使用者revision B解鎖的scoped R028 production migration。Acceptance decision `r028_root_acceptance_decision_20260927.json` SHA-256 `cc375897612e705e6c6c268a0ef63aa38c4f998d214a32fdd74d038567f792db`；raw R028 full8 receipt `r028_root_full8_20260927.json` SHA-256 `1a3b496973c7053c7d25612754a733cb505765667afa478be453efd2c5a19d82`。20個實際worker exit 0，8 cases與8 controls PASS，3,312 source-scope files穩定；Direct15、pinned5、HEAD/status stable。Root與boundary source/runtime review均無blocker。

R028把唯一production orchestration owner移至app `TechnicalIndicatorJob`；`UpdateService` facade lazy-delegate，既有process-pool port維持父程序單一寫入邊界。TMP-ML-02原conditional migration scope已滿足。Raw receipt內舊 `r028_full_replay_accepted=false` 欄位是root裁定前的歷史值，不修改；以本dated decision為current裁定。舊R027 strict仍 `INCONCLUSIVE`（post-Qt 947 differences），oracle/comparator/receipts未改寫；R028 legacy comparator diagnostic `FAIL`（995 exact、48 pinned source-owner/late-load mapping differences）亦獨立保留。R031 attempt6 current route及mandatory checks已由root接受；原strict仍INCONCLUSIVE，R028 legacy comparator diagnostic FAIL仍獨立保留。完整bounded implementation evidence見 [R028 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md)。
- Root start decision：`output/qa/refactor_completion_20260927/r028_root_start_decision_20260927.json`
