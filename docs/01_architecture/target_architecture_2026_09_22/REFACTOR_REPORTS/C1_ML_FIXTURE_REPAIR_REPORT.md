# C1 ML Fixture Repair Report

## 結果

已修復 C1 calibration integration 測試中六個自然驗證案例因評估日早於 exact-20 session endpoint 而在服務呼叫前失敗的問題。只調整 `tests/test_recommendation_service_calibration_integration.py` 內的測試日期與合成資料覆蓋；`tests/natural_session_source_fixture.py` 的 maturity guard 保持原樣，production code、正式資料與 ML ABI 均未更動。

## 日期鏈與語意

- 六個自然驗證案例的候選日仍為 2026-06-01，訓練 as-of 與既有訓練樣本未變。20 個 capture weekdays 為 6/1 至 6/26；最後一筆的 exact-20 endpoint 是 7/24。評估／採納日改為 2026-07-27（星期一），嚴格晚於所有 endpoint。
- 公開服務案例仍驗證 T-1／跨日行為：凍結時鐘為 2026-07-27 16:50 UTC，換算台北時間為 2026-07-28 00:50。來源 cutoff 為 7/27，個人化決策與事件日期維持台北隔日 7/28。合成市場列與 SQLite source rows 均延伸至 cutoff 7/27；歷史研究呼叫仍明確使用原有 2026-06-20 cutoff。
- 前瞻事件價日為 2026-07-28；fixture 日曆下從次一日開始計算，第 20 個 weekday 為 2026-08-25。Outcome price、label availability 與 recorded/calculated timestamps 同步使用 8/25，保存 20-session close-to-close label 的相對語意。
- Advice 的 decision date 改為 7/27，data-as-of 改為 7/26，保留 T-1 關係。候選日期、feature schema、feature order/value、訓練/推論數值與 after-cost assertions 不變。

## 範圍與驗證

涉及的六個案例：

- `test_real_consumer_producer_advice_workbench_ui_path`
- `test_public_service_real_builder_saves_result_and_reverse_reads_receipt`
- `test_active_training_label_contract_missing_or_mismatched_fails_closed`
- `test_active_training_label_contract_missing_from_provenance_fails_closed`
- `test_real_consumer_rejects_future_research_candidate_context`
- `test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation`

驗證結果：

- `python -m pytest tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider`：**12 passed**。
- 目標測試檔 `py_compile`：通過。
- 目標測試檔 `git diff --check`：通過。
- 日期核對：7/27 16:50 UTC = 7/28 00:50 Asia/Taipei；7/28 之後至 8/25 共 20 個 weekday。

此修復只解除既有測試 fixture 的日期矛盾；不代表 C1 其他 validation gates 已通過，也不取代完整 C1 checkpoint 審查。
