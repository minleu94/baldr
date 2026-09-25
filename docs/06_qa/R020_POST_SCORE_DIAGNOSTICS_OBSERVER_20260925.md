# R020 Post-score Diagnostics Observer Slice

日期：2026-09-25
範圍：抽出 `StrategyConfigurator.screen_stocks` 的價格／成交量 diagnostic passes，讓同一 observer 可獨立呼叫；不接 replay provider 或 evaluator，也不改最終篩選 owner。R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`。

## 變更

`decision_module.strategy_configurator.observe_screening_diagnostics(frame, filters, *, logger, counter_owner)` 只在診斷副本上依序執行價格、成交量 pass，記錄既有 debug／warning，並更新傳入 owner 的類別 warning counters；不回傳 eligible rows 或 disposition。`StrategyConfigurator.screen_stocks` 呼叫同一 observer 後，仍以原始 frame 呼叫唯一的 `filter_completed_frame(df, filters)` 並回傳該結果。

刻意保留的診斷行為：

- 每個 category 的 counter 在 warning cap 後仍持續遞增；warning 僅在各自 count 不大於 3 時發出。
- 價格 pass 清空後仍會進入成交量 pass；若成交量比較此時拋錯，先前價格 warning/counter 已完成。
- 若只有 `price_change_max` 清空資料，價格 warning 分支仍先遞增 counter，再直接讀取缺少的 `filters['price_change_min']` 並拋 `KeyError`；本切片沒有改成 `.get`。
- 欄位缺失仍只跳過對應 diagnostic pass；present-but-invalid 值仍在原 pass 產生相同 native exception。
- helper 只接收呼叫當下已有的 scored/current frame，沒有新增日期讀取、視窗延伸、排序或前視資料；未新增金融數值運算。

## 驗證

Fresh TEMP `C:\t\r20diagr354c90`，`PROFILE=test`，`TEMP`／`TMP`／`DATA_ROOT`／`OUTPUT_ROOT` 均指向隔離目錄。六檔路由命令：

```powershell
$qaRoot = 'C:\t\r20diagr354c90'
$env:PROFILE = 'test'
$env:TEMP = $qaRoot
$env:TMP = $qaRoot
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r020_post_score_diagnostics_observer.py tests/test_r020_post_score_diagnostics_characterization.py tests/test_strategy_screening_support.py tests/test_r020_post_score_legacy_policy_characterization.py tests/test_r020_real_scorer_filter_stage.py tests/test_r020_post_score_unsupported_metric_legacy_characterization.py -q -s -o addopts= -p no:cacheprovider
```

結果：`43 passed in 1.77s`。log：`C:\t\r20diagr354c90\adjacent.log`，SHA256 `24F9B48926AF10BE6B7820E6F2041929EF6D02F90474C33F206FF2E3C1CB8ADD`。

其他檢查：

- Scoped mypy：`decision_module/strategy_configurator.py decision_module/strategy_screening_support.py tests/test_r020_post_score_diagnostics_observer.py`，3 files／0 issues。
- `py_compile`：策略配置器、screening support、新測試通過。
- `scripts/quant_guard_linter.py`：float-boundary 與 look-ahead 檢查通過。
- `git diff --check`：通過；Git 僅回報既有 LF／CRLF 轉換提示。
- Full-app-healthcheck inventory 已登錄新測試；本 slice 只直接核對本測試的 category entry，沒有聲稱整庫 inventory gate 通過。

## 凍結檔案

| 檔案 | SHA256 |
|---|---|
| `decision_module/strategy_configurator.py` | `1758FC07654E744A218D04EE193F627C9D1379D88D27EF00EBEA997EC53D3100` |
| `decision_module/strategy_screening_support.py`（未修改） | `A3FBDC613798F947F24733CD8FBD6B1406EF49FCFB75F0BC54E109071B085F9E` |
| `tests/test_r020_post_score_diagnostics_observer.py` | `AD3A8D22C31B710C36946B9D24A13876250F0EAE2F8CB6451A1CC5FB0B856CE0` |
| `tests/test_r020_post_score_diagnostics_characterization.py`（未修改） | `0B7A9B7FF9E60044AD3D4FE2BE049F5F4F802123DB467041DA12A15CDD8A3988` |
| `qa/full_app_healthcheck/test_inventory.py` | `F6AF81B4F19C5629CFB19ED4DD77E5B3E2C88CB496A7B9814AE9368E6EC7DA01` |

本 slice 僅抽出診斷副作用 helper 並固定其現有例外／warning 時序。它不改 `StrategyConfigurator` eligibility policy，不解決 legacy diagnostic 與 replay typed post-score evaluator 的數值 parity，也不接線 provider；R020／`TMP-REC-04`／`TMP-NUM-01` 均維持 open。

## 獨立複核收據（2026-09-25）

R015 對 frozen source/test 獨立複核，判定 bounded `ACCEPTED_SCOPE`，未發現 P1/P2。Root 另獨立重跑同一六檔路由並回報 `43 passed`。接受範圍限於 diagnostics observer 抽取：observer 不回傳 eligibility，`screen_stocks` 仍對原始 frame 呼叫唯一的 `filter_completed_frame`。這不證明 replay typed post-score 與 Pandas native 行為完全 parity，也不代表 provider cutover。

R015 使用 fresh TEMP `C:\t\r020obsreview_5c4c9c95`、`PROFILE=test`，並將 `TEMP`、`TMP`、`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest basetemp 隔離；六檔路由 `43 passed in 1.62s`。log SHA-256：`533FAF1FB3F34399F4A36029AB5CA9962CFF4C071ACE487EFD70CA0E5730E6E4`。重跑命令：

```powershell
$qaRoot = 'C:\t\r020obsreview_5c4c9c95'
$env:PROFILE = 'test'
$env:TEMP = $qaRoot
$env:TMP = $qaRoot
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'out'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r020_post_score_diagnostics_observer.py tests/test_r020_post_score_diagnostics_characterization.py tests/test_strategy_screening_support.py tests/test_r020_post_score_legacy_policy_characterization.py tests/test_r020_real_scorer_filter_stage.py tests/test_r020_post_score_unsupported_metric_legacy_characterization.py -q -s -o addopts= -p no:cacheprovider --basetemp (Join-Path $qaRoot 'pytest-tmp')
```

Scoped mypy 對策略配置器、screening support 與 observer test 為 `3 files／0 issues`；三個 Python 檔 `py_compile` 通過。Frozen source/test SHA-256：`decision_module/strategy_configurator.py` `1758FC07654E744A218D04EE193F627C9D1379D88D27EF00EBEA997EC53D3100`；`tests/test_r020_post_score_diagnostics_observer.py` `AD3A8D22C31B710C36946B9D24A13876250F0EAE2F8CB6451A1CC5FB0B856CE0`。R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 維持 `ACTIVE`；完整 Pandas native parity、provider 接線與 full V-REPLAY 均未由此 slice 驗收。
