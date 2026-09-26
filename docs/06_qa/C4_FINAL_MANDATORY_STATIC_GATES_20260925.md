# C4 最終 mandatory UI/static gates 收據（2026-09-25）

**狀態：C4 mandatory static/UI gates 與 relevant-suite union 均已完成。** 本文記錄 Workbench、Update validator、broad mypy、changed-Python py_compile、`git diff --check` 及 C4 union pytest 收據；C4 union 由 root 裁定 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`。這些結果不重寫較早 C2 route 的失敗收據。

全部命令使用 `.venv` Python、`PROFILE=test`、合成 TEMP；Workbench 使用 `QT_QPA_PLATFORM=offscreen`，沒有開啟互動式 UI 或操作正式環境。mandatory static/UI gates 執行時完整 Python source fingerprint 為 2,297 files、SHA-256 `A7F674B9551CC98090D6356E7879E1CE13452655C95EA311CDD2D3E859063AFF`。這是該組 mandatory gates 的執行時點收據；其後 C3/C4 471-input 比對中的 3 個 source/test inputs 有 scoped 更新，最終 C4 source/test 狀態以本報告的 C4 manifest 與 pre/post SHA 為準。

## Workbench

- 命令：`.\.venv\Scripts\python.exe -m pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts=`
- 結果：**84 passed**，exit 0。
- TEMP：`C:\Users\archi\AppData\Local\Temp\c4u_wb_20260925_8dd223`
- Log SHA-256：`831893BEA118BC6080282C085CE07F480911829B283FD9CB32DB0C6CFDEC0671`。
- 執行前／後 Python source fingerprint 相同：2,297 files，SHA-256 如本文開頭。

## Update validator

- 命令：`.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py`
- 結果：**25 passed／0 failed／4 skipped**，exit 0。
- TEMP：`C:\Users\archi\AppData\Local\Temp\c4u_upd_20260925_8dd223`
- Log：`C:\Users\archi\AppData\Local\Temp\c4u_upd_20260925_8dd223\update_validator.log`，9,753 bytes，SHA-256 `8904E9894EFD2996897339203BD747BB335F0FDF0BBF46DC44038298DA149FC2`。
- Validator report 副本：`C:\Users\archi\AppData\Local\Temp\c4u_upd_20260925_8dd223\VALIDATION_REPORT.md`，8,074 bytes，SHA-256 `55BDA0FBC5F57DB04DA0CFDDF840D64B6EB307A90D3BEF6D82C1B1AD8A26C066`。
- 4 個既有 skip：daily、market、industry update 測試略過實際下載；daily merge 測試略過實際資料合併。
- 此次完整 Python source fingerprint 前後一致，見本文開頭。

這次 C4 Update validator 成功。C2 當時兩次 Update validator 的 `WinError 32` TEMP SQLite teardown 失敗仍保留為歷史收據；C4 pass 不會把那些 C2 exit 1 改寫成 pass。C2 維持 root 裁定 `ACCEPTED_WITH_NAMED_QA_BASELINE`，owner 為 Update QA／DB resource lifecycle。

## Broad mypy

- 命令：`.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`
- 結果：`Success: no issues found in 724 source files`，exit 0。
- TEMP：`C:\Users\archi\AppData\Local\Temp\c4u_mypy_20260925_8dd223`
- Log SHA-256：`24AACBC9F81E6E28993808804EFF64BD05E02E27D75D1F6064296186DF3386ED`。
- 執行前／後完整 Python source fingerprint 一致。

## Changed-Python compile 與 whitespace

- `py_compile`：凍結清單中的 **67 個 changed/untracked Python files** 全數成功，exit 0。
- TEMP：`C:\Users\archi\AppData\Local\Temp\c4u_compile_20260925_8dd223`
- 路徑清單：`changed_python_paths.txt`，SHA-256 `D9905FA26CE327B0B24429CDC24CA0CE6F49A88F07EDA47F4A408476DD10AD03`。
- 67 路徑的執行前／後 bytes 清單均為 11,748 bytes、SHA-256 `2A5A84FF189BF22C80491EECB8E9F02D2226FF935035A6F1457E33B2047E3939`。空輸出 `py_compile.log` SHA-256 `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`。
- `git diff --check`：exit 0；只輸出共用工作樹的 LF-to-CRLF notices。Log `C:\Users\archi\AppData\Local\Temp\c4u_diff_20260925_8dd223\git_diff_check.log`，6,897 bytes，SHA-256 `4E4DDB4E4A35D3C3795BCD4AA824B4F43DBE34CDB0EC7ADFC515176B013A4472`。
- diff-check 前後完整 Python source fingerprint 一致。

## C4 final union pytest

**Root 裁定：`ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`。** C4 current route 使用 234 個 test files、237 個 source files（共 471 frozen inputs），NP2；結果 **2,446 passed／2 failed／5 skipped／35 warnings，640.25 秒，exit 1**。兩個 failure 是已知 ML shadow-boundary CLI/repository assertions，均由原有 11 occurrences／10 distinct residual 引起；C4 沒有新增 failure。這是有具名 baseline 的接受，不是全綠 pytest 或無限制 repo PASS。

- TEMP root：`C:\Users\archi\AppData\Local\Temp\c4r_de0d7b`；runtime 為 Python 3.11.9、NumPy 2.3.5、scikit-learn 1.8.0、SciPy 1.16.3、joblib 1.5.2。
- 原始 route manifest：`C:\Users\archi\AppData\Local\Temp\c4r_de0d7b\route.json`，142,438 bytes，SHA-256 `3E7CF99F6CB2133D5B019B8E99C305FAC1CF386E973210CA49D7490F57358E72`。
- 原 bytes 副本：[C4 final suite manifest](C4_FINAL_RELEVANT_SUITE_MANIFEST_20260925.json)，142,438 bytes；SHA-256 與原始 route manifest 完全相同：`3E7CF99F6CB2133D5B019B8E99C305FAC1CF386E973210CA49D7490F57358E72`。此 manifest 保存全部 234 test paths 與 237 source paths/hash。
- 471-input pre/post JSON 各為 94,786 bytes，SHA-256 均為 `CBE8B12FE5EF41DFFC58EE4F118BD1CF5BA3186A4A56DFD2EC84CBCB6AE016FF`。
- Pytest log：`C:\Users\archi\AppData\Local\Temp\c4r_de0d7b\pytest.log`，10,878 bytes，SHA-256 `88797C7C2476576D771E88099E0016D49C10A78D29B0494B2A3CE834A8CF29F9`。
- Compact machine receipt：[C4 union receipt](C4_FINAL_UNION_RECEIPT_20260925.json)。

兩個 failed tests 為 `tests/test_ml_shadow_boundary_cli.py::test_shadow_boundary_cli_passes_repository` 及 `tests/test_ml_shadow_dependency_boundary.py::test_repository_respects_ml_shadow_dependency_boundary`。C3 focused review 已接受新增 R026 exact edges 的最小 allowlist/negative coverage；目前兩項 assertion 僅剩既有 11 occurrences／10 distinct diagnostics。這個 baseline 仍具名列管，沒有擴大允許整個 module/package。

5 個 skip 與此 Windows host 條件一致：`tests/test_c1_legacy_query_readiness.py:439` 及 `tests/test_r012_recommendation_artifact_persistence.py:1160,1191,1211` 因 `WinError 1314` 無 symlink privilege；`tests/test_r020_numeric_runtime_differential.py:685` 因該 runtime 的 `longdouble` mantissa 未寬於 `float64`。均未計入 passed。

### C3 → C4 frozen-input delta

兩次 471-input manifest 比對只有下列 3 個 path 的 bytes 改變；其餘 468 個 input hashes 相同。此有限 delta 對應已審查的 R026 guard edges 與 UI save fixture 修復。

| Path | C3 SHA-256 | C4 SHA-256 |
|---|---|---|
| `ml_module/shadow_boundary_guard.py` | `48074B1F4F5A73737530A409F18E5BFCC91D6A70F2A0750F2813ADA5EA7B1D05` | `1E5E4AF198A9FC2FEC0AAF1A35786701F94734B245C98212A9349D75D594A4A9` |
| `tests/test_ml_shadow_dependency_boundary.py` | `550C09EE88A75F86751F92B893823630C64D4066FE1CA707DB2D286BF71600CE` | `3C0408DD7C810E6F9AD183CD36370AA278FEE2063391E571D3589C688FC9B59F` |
| `tests/test_ui_qt_research_run_save.py` | `E06B166088595CB14A4063EF04ABD41C6E1CB554754191D7F68765E1C2EA1044` | `53C230AA1D6AEB193A01ED558103359AD6C5BB0489C6357DD9904315A0181D7B` |

### Delta files scoped static receipts

上述三個 delta input 的定點靜態證據已各自 readback，未重跑 full union：

- `ml_module/shadow_boundary_guard.py`：`mypy` 1 source file／0 issues；guard 與 `tests/test_ml_shadow_dependency_boundary.py` 的 `py_compile` 通過。當前來源、測試 SHA 與 focused pytest receipt 見 [R026 exact-allowlist QA](ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md)。
- `tests/test_ui_qt_research_run_save.py`：`py_compile` 通過；capture owner 的 focused UI route 為 22 passed，log SHA-256 `97EE3347873ADEC2692D9BEAA3EC3D5692BEA1752E6E01FF6B1AE1E0BFC31494`，test SHA-256 與 C4 frozen input 一致。focused receipt 見 [R031 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。
- C4 mandatory gates 的 `A7F674…` fingerprint 僅描述 mandatory gates 當時核對的 2,297 個 Python files；C4 最終 route 的凍結 inputs 是 manifest 所列 234 個 tests 加 237 個 sources，前後 SHA-256 均為 `CBE8B12FE5EF41DFFC58EE4F118BD1CF5BA3186A4A56DFD2EC84CBCB6AE016FF`。

### Reproduction command

從 repo root 使用短的新 system TEMP root；manifest 中的 `tests` 陣列提供固定的 234 個 test paths。命令將 profile 與資料輸出導向合成 TEMP，並以 `p` 作 pytest basetemp：

```powershell
$qaRoot = Join-Path $env:TEMP ('c4r_' + [guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$env:TEMP = $qaRoot
$env:TMP = $qaRoot
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $qaRoot 'd'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'o'
$env:QT_QPA_PLATFORM = 'offscreen'
$qaManifest = Get-Content -Raw 'docs/06_qa/C4_FINAL_RELEVANT_SUITE_MANIFEST_20260925.json' | ConvertFrom-Json
$qaTests = @($qaManifest.tests | ForEach-Object { $_.path })
if ($qaTests.Count -ne 234) { throw "Expected 234 tests; got $($qaTests.Count)" }
.\.venv\Scripts\python.exe -m pytest @qaTests -q -rs -o addopts= -p no:cacheprovider --basetemp (Join-Path $qaRoot 'p') --tb=short
```

C4 最終 union receipt 是 current route 的完整驗證收據。R031 closeout 同時保留 C3 原始 4F log 與後續 focused evidence；root 的裁定是保留 boundary baseline 與具名相容性 blockers 下完成有限工程範圍，不是整體 refactor 無條件 PASS。詳見 [R031 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。
