# C2 mandatory UI/static gate 現況收據（2026-09-25）

**狀態：`C2=ACCEPTED_WITH_NAMED_QA_BASELINE`（2026-09-25）。** C2 current 141-path union、Workbench 84P、broad mypy 724/0、67-file changed-Python compile 均完成。Update validator 兩次 fresh TEMP 路由都於 SQLite cleanup 遇到 Windows `WinError 32`，留下 25 passed／1 failure／4 skipped、exit 1；此例依既有 R023 同類 teardown baseline 具名接受，不稱全綠。完整 C2 route、static receipts 與限制見下文。

所有執行使用 `.venv` Python 3.11.9、NumPy 2.3.5、Pandas 2.3.3、`PROFILE=test` 與各自新系統 TEMP 根。source fingerprint 由 `git ls-files --cached --others --exclude-standard -- '*.py'` 列出所有 tracked/unignored Python 檔後逐檔計算 SHA-256；每個 route 都保存執行前／後 JSON。指紋含 2,297 個 Python 檔。未操作正式資料或 scheduler；Workbench 使用 `QT_QPA_PLATFORM=offscreen`。

## Workbench

- 命令：

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts= -rs -p no:cacheprovider --basetemp <fresh-TEMP>\pytest-base --tb=short
  ```

- 結果：**84 passed**，exit 0。
- TEMP：`C:\Users\archi\AppData\Local\Temp\c2u_wb_204b18a4`
- Log：`C:\Users\archi\AppData\Local\Temp\c2u_wb_204b18a4\pytest.log`，SHA-256 `A70A95ABA49CF7F08FCA9BD28AD1EB3F741F5BB97144C42CF1A36C53D52A7DF1`。
- Python-source fingerprint：執行前與後均 2,297 files、SHA-256 `01CEB52CE99B9F03C93B180729B14D97884E6EC9E36F5CBE74A0A31C36DFE041`。
- receipt：`C:\Users\archi\AppData\Local\Temp\c2u_wb_204b18a4\receipt.json`。

## Update validator

命令為 `.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py`，腳本將 `DATA_ROOT` 與 artifacts 放在本次 TEMP 下的 `task-loop-01-qa-*`；依既有 script 行為，彙總報告另寫入 repo `output/qa/update_tab/VALIDATION_REPORT.md`，本次副本也保存在各自 TEMP。

| 嘗試 | 結果與 failure | TEMP / log / SHA-256 |
|---|---|---|
| 第一次 | 25 passed／1 failure／4 skipped，exit 1。唯一 failure 是 `Main_Exception`：清理合成 SQLite `twstock.db` 時 `PermissionError [WinError 32]`，重試 9 次仍被 process handle 鎖住。 | `C:\Users\archi\AppData\Local\Temp\c2u_upd_5c2d00ed`；log `update_validator.log` SHA `1703CE83F24E98985B8A5AA495347590B690C159FAFEB68B91D59E971044C069`；report copy SHA `768C974A90805F8A1449AFD05991D6DE19B72016E67E7A514353DD0DF2408308`（10,845 bytes）。 |
| 唯一重跑 | 同樣 25 passed／1 cleanup failure／4 skipped，exit 1；同一 `WinError 32` teardown stack，未發現 assertion failure。依 owner 指示停止重試。 | `C:\Users\archi\AppData\Local\Temp\c2u_upd2_561fbe42`；log `update_validator.log` SHA `43794475CE8A4696EB2FE89588B3433B8649A7C8F9786BAFAC2D9200C705A3D3`；report copy SHA `CCFD1359987BD342C88983F1F43CD9930B5396F7A877A3C9BF0496EB7EE51511`（10,850 bytes）。 |

兩次均保留 4 個既有 skip：`update_daily_Execution`、`update_market_Execution`、`update_industry_Execution` 跳過實際下載；`merge_daily_data_Execution` 跳過實際資料合併。兩次 Python-source fingerprint 各自前後相同，均為 2,297 files／SHA-256 `01CEB52CE99B9F03C93B180729B14D97884E6EC9E36F5CBE74A0A31C36DFE041`。

此 teardown failure 與 [FINAL_MIGRATION_SEQUENCE 的既有 R023 Update QA 記錄](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md) 同類（25P／1F／4S、WinError 32 TEMP SQLite teardown）。Owner：Update QA／DB resource lifecycle。它是具名 QA baseline，**仍是 exit 1，不能稱為通過**；本輪沒有改 production 或 script。

## Broad mypy 與 changed-Python compile

- Broad mypy 命令：`.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`。
- 結果：`Success: no issues found in 724 source files`，exit 0。
- TEMP：`C:\Users\archi\AppData\Local\Temp\c2u_mypy_60db9709`
- Log：`C:\Users\archi\AppData\Local\Temp\c2u_mypy_60db9709\mypy.log`，SHA-256 `24AACBC9F81E6E28993808804EFF64BD05E02E27D75D1F6064296186DF3386ED`。
- Python-source fingerprint：2,297 files，執行前／後 SHA-256 均為 `01CEB52CE99B9F03C93B180729B14D97884E6EC9E36F5CBE74A0A31C36DFE041`。
- `py_compile`：67 個變更 Python 檔，exit 0；完整路徑清單在 `C:\Users\archi\AppData\Local\Temp\c2u_compile_c9e0cc85\changed_python_paths.txt`。輸出 log 為 `py_compile.log`，SHA-256 `EB8FDB454BD90D30C614B2547FCDE100D1E147192E228F75234ED7DC12224969`；執行前／後 Python-source fingerprint 均為 2,297 files／SHA-256 `7A52F2EC4133CD084E68E29492B9104C7A5F9C236C2FCAB22E315F5234012944`。
- `git diff --check`：exit 0；只輸出共用工作樹既有 LF→CRLF notices。
- Capture 修復後再次對凍結的 67 個 changed-Python files 執行 `py_compile`，exit 0。路徑清單 `C:\Users\archi\AppData\Local\Temp\c2c_final_compile_8d44f7\changed_python_paths.txt` SHA-256 `D9905FA26CE327B0B24429CDC24CA0CE6F49A88F07EDA47F4A408476DD10AD03`；執行前後逐檔 SHA 清單均為 11,748 bytes／SHA-256 `2A5A84FF189BF22C80491EECB8E9F02D2226FF935035A6F1457E33B2047E3939`。空輸出 log SHA-256 `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`。`tests/test_personalization_generation_cli.py` 凍結 SHA 為 `40F209EED4ABD6400AEB361539CD050A57C20D1F528D17C55B53CB3B14AD7F90`。

Broad mypy／compile 前後 fingerprint 都未漂移。mypy receipt 到 compile receipt 之間只出現 `tests/test_personalization_generation_cli.py` 的 owner fixture 更新（SHA `B761BDB9E3B3880C7125B4881AED5F95B695CFA5067069C4A82392A783D7FC1F` → `BEFA803C68CE83634328A6C6F341FC8CD9551C6F91BDFB9332A746FD8EF102CC`）；不是 production source drift。C2 manifest 必須在 owner 再次 freeze 後重生。

## Root C2 current union route

首次 route 使用的 141-test／88-source manifest：`C:\Users\archi\AppData\Local\Temp\c2final_luna_20260925_qa\manifest.json`，當時 SHA-256 `8B901F647865D0A90F43DC5299B58DDC8417A3903B840CCBAF0C566B0892E27E`。首次結果為 **1858 passed／2 failed／5 skipped／34 warnings**，106.96 秒；兩個 failure 都在 `tests/test_personalization_generation_cli.py`，原因為 typed-receipt fixture 尚未遷移。首次 route log：`C:\Users\archi\AppData\Local\Temp\c2r_417c62\pytest.log`，SHA-256 `37694AD8B9E82A7B5B2D823459EED1B3D815AA1425A72C57E87EBF087294BB3E`。本次 route 的 229 manifest inputs 前後 hash 一致；owner 後續修正 test，因此首次結果只作為修復前歷史收據。

Capture owner 修正後，root 審查新 test SHA-256 `40F209EED4ABD6400AEB361539CD050A57C20D1F528D17C55B53CB3B14AD7F90`，並以三檔 focused route 確認 **61 passed／6.05 秒**；log `C:\Users\archi\AppData\Local\Temp\c2f_3c0277\pytest.log`，SHA-256 `27DB978C167B0885B1667F91A6020BFC9B794AB26497073202BB8D71522BAD5F`。

修復後 current route：NP2、141 unique tests／88 source files，142 個 request paths 中 1 個已依 R015 退休紀錄不存在的 `tests/test_recommendation_save_coordinator.py`，共 229 個 frozen inputs。ROOT route manifest 為 `C:\Users\archi\AppData\Local\Temp\c2s_bcd34f\route.json`，SHA-256 `003A30C91510782077536C282EF4A32F37CBA30C7125C673338E85BB1B3FB862`；`pre.json`／`post.json` 各 46,592 bytes，SHA 均為 `B215D86E5D969212F995099B0F5807A403CE017F30ADF2B50DA854A160BAB91D`，229 個 inputs 零漂移。結果為 **1,860 passed／5 skipped／34 warnings，102.75 秒，exit 0**。pytest log `C:\Users\archi\AppData\Local\Temp\c2s_bcd34f\pytest.log`，7,126 bytes，SHA-256 `193EF45EA69B984A356F238CFAD4D00D714AB2B026E01CE89887260E59604687`。

5 個 skips 均保留為不適用條件：`tests/test_c1_legacy_query_readiness.py:439` 與 `tests/test_r012_recommendation_artifact_persistence.py:1160,1191,1211` 共 4 例因 Windows `WinError 1314` 無法建立測試 symlink；`tests/test_r020_numeric_runtime_differential.py:685` 因該 runtime 的 `longdouble` mantissa 未寬於 `float64`。較早的 NP1 17 個 R026 unsupported-profile failures 屬歷史 baseline；後續明確 NP1 registry route 68P、root default route 1P 已通過，因此不得暗示 current NP1 仍有該不支援 profile failure，也不可把歷史失敗算作通過。
