# Position Health Source Provider Calendar Cache 隔離 QA

日期：2026-09-15
範圍：`tests/test_position_health_source_providers.py` 的本機 calendar cache 時間相依修復
狀態：已完成 bounded 修復；未修改 production 判定、正式 output/cache、排程、UI、Manual 或其他協作者檔案。

## 根因

測試中的三個成功路徑直接讀取
`output/paper_execution_eod_replay/calendar_cache`。測試固定
`DECISION_AT=2026-09-08T13:00:00+00:00`，但該本機正式 cache 的
`available_at` 已更新到 2026-09-14，因此 production 的
`OfficialCalendarSourceProvider`／`build_position_health_source_bundle`／
`evaluate_baseline_file` 正確回報：

`official_calendar_available_at_future:2026`

這不是 production 判定錯誤，而是測試把可變動的正式 cache 當成固定 PIT fixture。

## 修復

在 `tests/test_position_health_source_providers.py` 新增
`_write_isolated_calendar_cache(tmp_path)`：

- 以既有 `build_twse_calendar_cache` 建立 2026 年完整年度 cache。
- raw response 僅為測試用年度休市 payload，並以 `write_twse_calendar_cache` 寫入 pytest 的
  `tmp_path/isolated-calendar-cache`；不觸碰正式 cache。
- 固定 `captured_at=2026-09-08T12:00:00+00:00`，`requested_at` 為前一秒，
  `max_age=31` 天；因此 `available_at <= DECISION_AT`，且在測試觀察期間仍未過期。
- 三個原本依賴正式 cache 的測試均改用該 isolated、hash-bound directory；future／stale／
  content hash／完整年度等 production 驗證仍由既有 loader 執行。

## 驗證

執行：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_position_health_source_providers.py -q -o addopts= -p no:cacheprovider
```

結果：`16 passed in 2.36s`；再以全新 `--basetemp` 執行同一命令為 `16 passed in 2.45s`，可在
乾淨 temporary workspace 重現。

另確認測試檔已無 `output/paper_execution_eod_replay/calendar_cache` 依賴；本修復未執行或修改
正式資料、正式 cache、排程、UI 或其他測試檔案。
