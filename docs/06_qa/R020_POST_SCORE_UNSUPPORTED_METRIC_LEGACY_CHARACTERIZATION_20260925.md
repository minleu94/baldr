# R020 post-score 缺欄與 unsupported metric 的 legacy characterization

狀態：**bounded legacy characterization**。本測試直接固定舊 `StrategyConfigurator`／pandas 比較，不使用 staged evaluator 作預期值；不代表 provider cutover、跨 runtime 等價、R020 或 `TMP-REC-04` 已驗收。

## 凍結行為

測試涵蓋同一個無效價格門檻 `"bad"`，比較缺少 `漲幅%` 與欄位存在但 numeric projector 無法表示的 object scalar：

| 合成輸入 | projector 識別 | legacy `screen_stocks` 結果 |
| --- | --- | --- |
| 缺少 `漲幅%`，門檻為 `"bad"` | 不需 metric 投影 | 保留 `MISSING` 列；不比較門檻、不記 warning，價格診斷計數維持 0。 |
| object dtype 的 `Decimal("1.25")`，門檻為 `"bad"` | `project_legacy_comparison_pair` 拋 `UnsupportedReplayNumericScalarError` | 價格診斷 pass 直接以原生 `Decimal >= str` 拋 `TypeError: '>=' not supported between instances of 'decimal.Decimal' and 'str'`；只呼叫一次 filter helper，未記 warning，計數維持 0。 |
| object dtype 的 `pd.NA`，門檻為 `"bad"` | `project_legacy_comparison_pair` 拋 `UnsupportedReplayNumericScalarError` | 目前 pandas profile 的原生比較將該列排除；先輸出 `[漲幅篩選] 要求 >= bad%, 但樣本值=<NA>%` 並將價格診斷計數加一，最後結果為空。 |

這證明 `MISSING_COLUMN` 與「欄位存在但 projector 不支援」不能共用一個略過門檻的行為：舊路徑對後者仍執行原生比較，其結果和副作用依 scalar 型別而異。Decimal 案例會在原生比較點拋錯；`pd.NA` 案例會先產生診斷副作用。此處只固定目前 runtime 的 pandas 行為，不外推其他 pandas／NumPy 版本。

## 測試與來源

新增測試：`tests/test_r020_post_score_unsupported_metric_legacy_characterization.py`（3 tests）。它直接呼叫 `StrategyConfigurator.screen_stocks`；只用記憶體 DataFrame，沒有 provider wiring、正式資料或寫入資料根目錄。numeric projector 只用來確認 scalar 不支援，不用其輸出作 legacy oracle。

執行環境：Python 3.11.9、pandas 2.3.3、NumPy 2.3.5。Fresh TEMP：
`C:\Users\archi\AppData\Local\Temp\r020-unsupported-metric-legacy-final-20260925-c`；`PROFILE=test`，`DATA_ROOT` 與 `OUTPUT_ROOT` 均位於該 TEMP。

隔離環境設定：

```powershell
$qaRoot = Join-Path $env:TEMP 'r020-unsupported-metric-legacy-final-20260925-c'
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
New-Item -ItemType Directory -Path $env:DATA_ROOT,$env:OUTPUT_ROOT -Force | Out-Null
$python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
```

執行命令：

```powershell
& $python -B -m pytest `
  tests/test_r020_post_score_unsupported_metric_legacy_characterization.py `
  tests/test_r020_post_score_diagnostics_characterization.py `
  tests/test_r020_post_score_legacy_policy_characterization.py `
  tests/test_r020_real_scorer_filter_stage.py `
  -q -o addopts= -p no:cacheprovider `
  --basetemp "$qaRoot\pytest" --tb=short
```

四檔相鄰路由：**35 passed**。新測試 `py_compile` 通過；`mypy --follow-imports=silent` 為 1 file／0 issues。pytest log SHA-256：`D6497FE1995B71CEFF1594FAB9A65C2A10A568B6AB8AEFB8FAE6A5DB5B603D23`。

| 檔案 | SHA-256 |
| --- | --- |
| 新 characterization 測試 | `E2AD5E161B5B8CED0A3BF6F9AB9DBA386804A06DF8616AB30F3830BC0D03FEC1` |
| `decision_module/strategy_configurator.py` | `0793723E8CAA78184EB2C892C94B13DAABBE3147B3B8F0D387F3F0DC91CC2A70` |
| `decision_module/strategy_screening_support.py` | `A3FBDC613798F947F24733CD8FBD6B1406EF49FCFB75F0BC54E109071B085F9E` |
| `app_module/recommendation/replay_numeric_projection.py` | `EA88A370E3485A3199BD7EBBF78F2E70CDA960C301D16B4D7F9B1BFF1E500D3C` |
| `qa/full_app_healthcheck/test_inventory.py` | `A7A757477194B68CB288C9193F5AF66FC01CDBF5E7790E1D5D908343C2C7C305` |

新測試已登錄為 `service-oracle-recommendation`。這是舊路徑的 test baseline，尚未驗證 deferred evaluator 對 unsupported metric 的 request／terminal 行為，也未完成 warning/counter adapter 或 same-mode replay parity。
