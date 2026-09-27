# R028 implementation report — scoped migration accepted（2026-09-27）

**裁定：`ACCEPTED_SCOPED_R028_PRODUCTION_MIGRATION`。** Root 依使用者接受的 R027 logical-time revision B、凍結來源的實際 diff、R028 full8 與 source/runtime 獨立審查，接受本次有界 production migration。R031 attempt6的288-path relevant regression與mandatory checks亦已由root接受；本報告與current closeout是提交前驗收snapshot，staged review與commit結果以Git history及root最後交付為準。

## 實際 owner 與相容邊界

`app_module.technical_indicator_job.TechnicalIndicatorJob` 現為 technical-indicator publication orchestration 的唯一 production owner。`UpdateService.calculate_technical_indicators` 保留 public facade 並 lazy-delegate 至 job；既有process-pool port維持父程序單一寫入邊界。移動的是 R028 原 conditional scope 的 inline orchestration，沒有增加第二 writer，也沒有宣稱刪除不存在的 guard exception 或 Direct15 data→app edge。保留 historical reader、必要 class aliases、Direct15/OOC identity、資料source identity、既有checkpoint定義與 publication artifacts；app service/job owner source mapping則依核准manifest明確遷移。未啟用正式 scheduler、重建市場資料、重新訓練或 promotion。

R028 使用受控 frozen baseline fixture `scripts/experiments/r028/frozen_baseline/app_module/update_service.py`，由原 ignored pre-migration source bytes固定，不由 candidate 重建。Baseline source SHA-256 為 `697c3bd89aa256867f964e3cd01c253a28284f75a1c6d2d963354223e6daedec`；candidate facade `app_module/update_service.py` SHA-256 為 `27d0dd226ca8d9ac18b039a7778d74c5381b987f3d9f36b29053fa00175cf8b4`；job `app_module/technical_indicator_job.py` SHA-256 為 `77d34c79ff63ec82a928b7e62dfa0f8395ae9307f54723752d2c270ebf81c97e`。Pinned static migration manifest SHA-256 為 `36f65c3cf52943161ba613d32681657f697aa61bcea59b81a8b86dce5935a85f`。凍結 gate `scripts/experiments/r028/logical_time_gate.py` SHA-256 為 `3d5efe64231fb95ed62cf8723db09b996cd468c0354b672c62ef306b904c3d31`；focused test `tests/test_r028_technical_indicator_job.py` SHA-256 為 `24b112b174b22fe0018974fb47589b3d44c4530ffb26c03c24073abb32fc0724`。

## 驗收證據

- Focused R028 gate/file suite：40 passed、0 failed，1.88 秒，自然 exit 0；final focused receipt `r028_technical_indicator_job_gate_final5.json` SHA-256 `5aa64b90bef18fee3ea5d683238d84255b38f189f4cb37d8eeb7086306ce8c99`。4 個 Python 檔案 `py_compile` 通過，7-path owner scope hash穩定。
- Root 獨立 full8 replay自然 exit 0；R028 gate與runner均為 `PASS`，8/8 固定 case及8/8 negative controls皆通過。20個實際 worker exit code皆為0；3,312個selected source-scope files前後相同；Direct15、pinned5、HEAD及git status均穩定，6項runner integrity checks皆true。原指定 publication phase的SQLite main DB raw bytes、SHA與size逐項一致。
- Raw receipt `output/qa/refactor_completion_20260927/r028_root_full8_20260927.json` SHA-256 `1a3b496973c7053c7d25612754a733cb505765667afa478be453efd2c5a19d82`，1,986,813 bytes。Gate input SHA-256 `7db43aa6943c7845b1c7f707a1ac6d8af9d1e14f971bb7376fdbd2d9ce5bf116`，198,221,505 bytes。Root actual runtime review SHA-256 `80af02ddc72b093cb059feb647396e51263ade10d3265a0dcecf590648073329`；root acceptance decision SHA-256 `cc375897612e705e6c6c268a0ef63aa38c4f998d214a32fdd74d038567f792db`。
- Raw runner內的 `r028_full_replay_accepted=false` 是 root 裁定前產生、不可改寫的歷史欄位。以上方獨立 acceptance decision為current裁定依據；raw receipt保持原bytes/hash。

## 與 R027 strict 歷史的關係

原 R027 strict verdict仍是 `INCONCLUSIVE`：post-Qt raw receipt `r027_post_qt_lifecycle_root_all_20260927.json` SHA-256 `9a19c3ac9cc28d6c07ecda6506e1f4f35b30a7ffa4cf74cb915f531e414f5ef7` 保留8/8 `INCONCLUSIVE`、947 strict differences。原 comparator診斷對本次R028 relocation結果為 `FAIL`（995 exact differences，其中48為每case六項經核准的owner／late-load projection差異）；comparator及strict結果都未修改。使用者接受的revision B另行固定phase-call序列，保留全部raw OS clock、mtime、WAL/SHM與reader observations，但不要求這些physical值跨process逐值相同；每個原phase main-DB raw bytes/hash/size、committed visibility、fresh-reader/readback及recovery仍須通過。R028 acceptance使用此獨立gate，不把strict `INCONCLUSIVE`或legacy comparator `FAIL`改名為PASS。

R027 revision與原strict證據見 [versioned R027 acceptance addendum](../../../06_qa/R027_LOGICAL_TIME_ACCEPTANCE_REVISION_20260927.md)。R028 task原文與歷史條件仍見 [R028 task](../REFACTOR_TASKS/R028.md)。目前可重跑入口為 `python -m scripts.experiments.r028.run_production_replay`；原R027 extraction runner是pre-migration snapshot工具，不應描述為可直接在目前已遷移source graph重跑原 extraction。

## R031 final route與限制

Attempt6的288-path current relevant route與mandatory checks已自然完成並由root接受：2,951P／5S／36W、817.03秒；JUnit 2,956 tests／0 failures／0 errors。Workbench 84P／0S、Update QA 25P／0F／4S、mypy 731 files／0 issues、changed-Python compile 109 files；3,313 source／fixture inputs無drift，Direct15／pinned5 exact。pytest 5 skips為4個Windows symlink權限與1個longdouble mantissa條件，Update QA另有4項下載／merge skip，均不計PASS。Root raw receipt SHA `9ec19361748ac2a0e0de120eee62043241d42375014af3bed60b6c2a02eefd4d`、assessment SHA `b8d3f224d786f195ce5bbc8133ce95cae12a33320d627ccb27b80a1495e02b27`。此為提交前snapshot；staged review與commit結果以Git history及root最後交付為準。正式資料、official scheduler、native UI teardown、full-market rebuild、model promotion及未知正式serialized artifact load/predict均未由本報告驗收。
