# R020 post-score 診斷與篩選舊行為 characterization

狀態：**bounded legacy characterization**。本文件記錄尚未遷移的 `StrategyConfigurator` 舊行為；不代表 pure post-score evaluator 已接線、同模式 parity 已通過或 `TMP-REC-04` 已關閉。

## 範圍與來源版本

新增測試 `tests/test_r020_post_score_diagnostics_characterization.py` 固定診斷篩選、最終篩選、原生比較和 concrete replay provider 終端。測試只使用記憶體 DataFrame 和合成 provider input，沒有讀寫正式資料，也沒有修改 production code、R005 oracle 或 R020 主報告。

測試觀察時的來源 SHA-256：

| 檔案 | SHA-256 |
| --- | --- |
| `decision_module/strategy_configurator.py` | `0793723E8CAA78184EB2C892C94B13DAABBE3147B3B8F0D387F3F0DC91CC2A70` |
| `decision_module/strategy_screening_support.py` | `A3FBDC613798F947F24733CD8FBD6B1406EF49FCFB75F0BC54E109071B085F9E` |
| `app_module/recommendation_dataframe_provider.py` | `F0B50C21D08D7867BE2B59D4F9B54D1A33C9E9CCD17A6788FAB2FDFBCDFC6630` |
| `decision_module/recommendation/evaluate.py` | `88B55FC4F450230ADFB92E46C7BC30ABD67A28AF4FC83C31138D8A96EC73F6CC` |

執行環境：Python 3.11.9、pandas 2.3.3、NumPy 2.3.5、pytest 9.0.2。complex 與 NumPy/Pandas dtype 行為僅代表此環境，不宣稱跨 runtime 等價。

## 凍結的舊行為

`StrategyConfigurator.screen_stocks` 先在複本上獨立執行 price 診斷，再執行 volume 診斷，最後才從原始 frame 套完整篩選。完整篩選 helper 依 price min → price max → volume min → RSI min → RSI max 執行；即使前一步已篩成空 frame，後續比較仍會發生。

| 情境 | 合成舊路徑觀察 |
| --- | --- |
| price min 篩空、volume threshold 為字串 | price 診斷先記錄警告 `[漲幅篩選] 要求 >= 100%, 但樣本值=0.00%` 並將 `_price_filter_log_count` 加一；接著在空的 float64 Series 比較時拋 `TypeError: Invalid comparison between dtype=float64 and str`。volume 計數未增加，最終 pass 未執行。 |
| price min 篩空、price max 為字串 | price 診斷內的 price max 在空 Series 上先拋同型 `TypeError`；警告和價格計數都尚未發生，volume 診斷與最終 pass 未執行。 |
| price 診斷先警告、final RSI threshold 為字串 | price 警告先發生，完整篩選再在空的 int64 RSI Series 上拋 `TypeError: Invalid comparison between dtype=int64 and str`。 |
| 欄位或 threshold key 缺席 | 缺少對應欄位時跳過該篩選；所有欄位缺席但 threshold 是無效字串時，列仍保留。threshold key 缺席也保留列。 |
| threshold key 存在且值為 `None` | 在目前 pandas profile，price min `None` 比較不拋錯而排除該列，並輸出 `None%` 警告。這與 key 缺席不同。 |
| RSI 欄位優先序 | 同時存在時依 `RSI`、`rsi`、`RSI_14` 選第一個欄位；缺少前兩者時使用 `RSI_14`。 |
| NaN／±Inf | `>= 0` 保留 `0`、`+Inf` 及正值；`<= 0` 保留 `-Inf`、`0`。NaN 不通過任一側。 |
| NumPy complex128 | 本環境依 pandas/NumPy 原生 complex 排序執行 `>=`、`<=`，測試固定其保留列；Python complex object comparison 則分別對應原生 `>=`／`<=` `TypeError`。 |
| concrete provider terminal | scorer 內一般錯誤被 `StrategyConfigurator` 的既有保護區塊轉成空 DataFrame，因此 provider 記錄 `SKIPPED_EMPTY`。post-score RSI 比較錯誤逸出後則記錄 `SKIPPED_SCORER_EXCEPTION`／`TypeError`。 |
| visible output | 成功時仍提供既有 v1 row，assessment 的 `filter_outcomes` 僅含 `replay_prefilter`、`replay_scoring`。post-score 篩為空時 rows 與 scoring outcomes 仍為空，call-local terminal 保留 `SKIPPED_EMPTY`／`scorer_empty_result`。 |

## QA 證據

Fresh TEMP 使用 `PROFILE=test`，`DATA_ROOT` 與 `OUTPUT_ROOT` 均位於該 TEMP 子目錄。最終同次 focused route 的隔離設定：

```powershell
$qaRoot = Join-Path $env:TEMP 'r020-postscore-diagnostics-final4-20260924'
New-Item -ItemType Directory -Path $qaRoot -Force | Out-Null
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'out'
New-Item -ItemType Directory -Path $env:DATA_ROOT,$env:OUTPUT_ROOT -Force | Out-Null
```

執行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_r020_post_score_diagnostics_characterization.py `
  tests/test_r020_post_score_legacy_policy_characterization.py `
  tests/test_r020_real_scorer_filter_stage.py -q -o addopts=
```

結果：**31 passed**。新增 characterization 檔單獨包含 14 個測試。`py_compile` 通過；對新增測試檔執行 `mypy --follow-imports=silent` 為 0 issues。Fresh TEMP pytest log：`C:\Users\archi\AppData\Local\Temp\r020-postscore-diagnostics-final4-20260924\pytest.log`（SHA-256 `C994F42FBB6AD18AEDFC263F1D139E65901BCCD484E7385AE1CFC3839FF2D1B5`）。

`qa/full_app_healthcheck/test_inventory.py` 已將新測試登錄為 `service-oracle-recommendation`；同檔當時 SHA-256 為 `3718BA224D306A1145D3CD80DACEC30B53C25280D68DBAEC03891973EB942B72`。inventory guard 的其餘全庫測試為 6 passed、1 failed；唯一失敗是全庫 `test_all_python_files_in_tests_are_registered_exactly_once`，列出多個與本 slice 無關、尚未登錄的測試/fixture。新測試路徑已登錄，且不在該次 missing 清單內；不將全庫 inventory 宣稱為 PASS。

新測試 SHA-256：`0B7A9B7FF9E60044AD3D4FE2BE049F5F4F802123DB467041DA12A15CDD8A3988`。以上只證明目前 legacy profile 的舊行為，不替代 pure evaluator 遷移後的 same-mode parity，也不解除 R020、`TMP-REC-04` 或 `TMP-NUM-01` gate。

## 2026-10-11 後續 R020 disposition（保留本收據範圍）

本文件的 2026-09-24／25 行為觀察與測試仍是日期化 legacy evidence。後續 [R020 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md) 記錄 post-score cutover 僅在已測 Win32／Python 3.11.9／Pandas 2.3.3／NumPy 1.26.4 與 2.3.5 profiles bounded accepted；[R029 ledger](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R029_IMPLEMENTATION_REPORT.md) 與 [R031 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 將 R020 R005 replay/recovery bounded scope、`TMP-REC-04`、原範圍 `TMP-NUM-01` 列為已關閉，C2 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`。

後續裁定不把本文件單獨提升為 provider/evaluator cutover 或 full same-mode parity 證明，也不外推至所有 runtime/profile/caller、無界 V-REPLAY 或跨 store atomic recovery；原始 legacy 行為、測試數字與限制保留其歷史時點。
