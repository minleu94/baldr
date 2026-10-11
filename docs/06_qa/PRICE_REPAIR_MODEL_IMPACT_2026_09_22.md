# 2026-05-20 價格修訂的模型影響與最小隔離

> 本文紀錄日期為 2026-09-22；標題的 2026-05-20 是受影響的市場資料日期。模型隔離只涵蓋本文具名確認的產物，不代表全部歷史模型均已核實。

本紀錄涵蓋模型 metadata 盤點與修訂保護；這部分未載入正式 joblib/pickle、未重訓或 promote，focused tests 僅使用隔離 synthetic fixture。另一路已完成的正式價格修復見[修復紀錄](HISTORICAL_PRICE_SPIKE_2026_09_21.md)。價格修復 receipt 的 canonical schema 是 `historical-price-spike-repair-20260921.v1`；模型 guard 不另建第二套 receipt 格式。

## 已確認的產物

- 實際每日 shadow release：`output/v4_ml_derived_h5_20260907_real_v2/release_manifest.json`。`model_id=baldr-ml-allocation-derived-h5-v4-rank-v2`，artifact hash 為 `sha256:aa152ebb8e8d7913a6a2274a0526620d8b8ce151a5f667d8de446df9724c895c`，manifest hash 為 `sha256:c306c1ea53ccef112204a8412a605b575e4d107b4503b2b5be5d6d5ee50910ea`。training manifest 的 `training_as_of` 是 `2026-09-04T08:30:00+08:00`，來源明列 `sqlite.daily_prices` 與 `derived:daily_prices.ohlc`。
- 每日 shadow 的 release observation receipt 在 `output/v4_ml_daily_derived_shadow_real_v2/natural_date_shadow/release_receipts/2a4a149076b69f9ad48f056821e696ad0c3cfc7cebbd5b655f7ce9d37ff83613.json`，同樣綁定上述 artifact hash；因此不能只用 `formal_oos_allowed=false` 或 `production_action_allowed=false` 宣稱它從未使用。
- `D:\Min\Python\Project\FA_Data\output\release_v4\ml_allocation_bounded_v4_operational\training_manifest_v2.json` 的 training manifest 記錄 `training_as_of=2026-07-30T08:30:00+08:00`、22,093 rows，且 formal/production action flags 關閉。這些 flags 是權限狀態，不是資料修訂安全證明。
- 實際校準 active pointer 是 `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\recommendation-calibration-active-pointer.json`，狀態為 `rule_only`，candidate/artifact/dataset 為 null，formal order 關閉；本輪沒有可停用的 calibration candidate。
- 舊 `D:\Min\Python\Project\FA_Data\models\*.pkl` 只做 metadata inventory，沒有載入；其訓練時間窗與來源 hash 無法由檔案 mtime 證明，不能推論為乾淨。

完整的 bounded readback 在 [model_impact_metadata.json](../../output/qa/price_repair_20260921/model_impact/model_impact_metadata.json)，盤點程式為 [inspect_model_metadata.py](../../output/qa/price_repair_20260921/model_impact/inspect_model_metadata.py)。

## 已實作的最小保護

`data_module/ml_daily_price_revision_gate.py` 是 exporter、歷史 snapshot provider 與 release adapter 共用的唯讀 gate：

1. 依 `database_path` 自動找到 SQLite sibling data root 的 `output/scheduled/daily_price_repair_receipts/20260520/historical_price_spike_20260921/{pending.json,receipt.json}`。
2. caller 若另傳 receipt，會和自動找到的 sidecar union 去重，不能用一個無關 explicit path 取代正式 marker。
3. pending marker 沒有完整 rows 時以 all-symbol 保守阻擋；即使 final receipt 同時存在，pending 仍是事故 hold，直到後續流程明確收口。
4. decision cutoff 或 forward label window 的 end date 到達 `source_date` 就 fail closed；`history_start_date` 較晚不構成安全證明，因為 rolling features 與較早決策的 5/10/20/60 日 labels 仍可能依賴修訂列。
5. `MLHistoricalSnapshotProvider.load()`、`load_forward_price_window()` 與 `MLAllFieldSnapshotProvider.load()` 在任何 SQLite query 前檢查 gate。個股研究報告的 current-price read path 不在這個歷史訓練隔離範圍內，應正常顯示修復後值。
6. `AllocationReleaseAdapter` 與 `MLAllocationInferenceService` 都在 joblib 反序列化前以 artifact hash quarantine 已知的 2026-09-07 derived h5 release，以及 `FA_Data` 的 bounded operational training artifact，回報 `stale_source_revision`；原始 release 保留供稽核。新的 dataset/model 必須使用新 identity 重建與重新驗證後，才可由後續流程解除隔離。

這個 hash quarantine 涵蓋目前已知的兩個 artifact hash：derived h5 shadow release 與 `FA_Data` bounded operational training artifact。其他歷史 artifacts 若沒有相同 hash 或新的 source receipt，不會被本輪假稱為全面隔離；直接繞過上述入口的舊 consumer 仍需另行盤點。

目前的 manifest source hash 與 training window 證明來源時間窗相交，不能單靠 metadata 證明每一列模型輸入都已污染；本輪 quarantine 是保守的 preemptive hold，也不表示所有模型均已污染。解除隔離前仍須以修訂後的新 dataset/model identity 逐列重建、驗證與重新產生 evidence。

唯讀路徑檢查確認每日 shadow 正常 caller 在 `scripts/run_daily_ml_allocation_derived_shadow.py:1262` 使用 `AllocationReleaseAdapter().load(release_root)`；v3 readback 也在 `ml_module/allocation_v3_linear_release.py:987` 經中立 loader 轉入同一 adapter。這次只做 source search，沒有啟動真實 shadow 或載入模型。

## 驗證

- `pytest tests/test_ml_pit_year_shard_exporter.py -q -o addopts=`：18 passed；`tests/test_build_ml_pit_year_shards_cli.py`：3 passed；`tests/test_ml_historical_snapshot_provider.py`：5 passed；`tests/test_ml_all_field_snapshot_provider.py`：10 passed；四條 gate/provider/exporter route 合計 36 passed。
- `pytest tests/test_allocation_release_adapter.py -q -o addopts=`：8 passed。
- `pytest tests/test_ml_allocation_inference_service.py -q -o addopts=`：11 passed，包含 operational wrapper 在 joblib 前執行 quarantine callback 的回歸；六條 route 的正式整合命令合計 55 passed，完整 stdout 保存在 [pytest_integration_55.log](../../output/qa/price_repair_20260921/model_impact/pytest_integration_55.log)。
- collect-only readback：55 tests collected；route 計數為 18 + 3 + 5 + 10 + 8 + 11。
- 回歸涵蓋：無 CSV source dirs 仍會被 receipt 阻擋、自動 pending marker、explicit 與 automatic union、all-symbol empty rows、cutoff 未到 source date 可通過、snapshot direct DB 阻擋，以及 5/19 起跨 5/20 的 forward label window 阻擋。
- `python scripts/quant_guard_linter.py`：financial float boundaries 與 look-ahead checks 均通過；原始輸出保存在 [quant_guard_linter.log](../../output/qa/price_repair_20260921/model_impact/quant_guard_linter.log)。
- focused mypy：7 source files 無錯，輸出保存在 [mypy_7_sources.log](../../output/qa/price_repair_20260921/model_impact/mypy_7_sources.log)；changed Python files 已通過 `py_compile`，輸出保存在 [pycompile.log](../../output/qa/price_repair_20260921/model_impact/pycompile.log)。小型索引見 [qa_summary.json](../../output/qa/price_repair_20260921/model_impact/qa_summary.json)。

模型隔離子任務沒有修改 `daily_prices`、`technical_indicators`、scheduler、collector 或模型 bytes；正式資料修復狀態以獨立修復紀錄為準。修訂後的 availability 沒有回填成 2026-05-20 當時已知。
