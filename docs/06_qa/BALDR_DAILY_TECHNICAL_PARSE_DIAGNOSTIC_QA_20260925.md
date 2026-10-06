# Daily technical parse／partial failure diagnostic 隔離驗收

## 範圍與裁決

2026-09-25，root 指派修正 daily technical raw-alias 數字解析與 quick-update runner 的部分失敗診斷。QA 於 2026-09-26 以隔離 synthetic 資料完成。結果：四套相關測試 `141 passed / 9.10s / exit 0`；本報告僅接受程式契約與受控回歸，不代表正式資料重算、Windows Scheduler 執行或當日產品資料完整。

### 修正行為

- `app_module/update_service.py` 的 `calculate_technical_indicators` SQLite 路徑在既有 alias guard/context 有效時，先用 `data_module.formal_technical_raw_alias_repair.normalize_raw_alias_values_for_storage` 對六個受保護 alias 欄位解析，再執行其餘既有 `pd.to_numeric(errors="coerce")` 轉換。原始 alias 解析位於 SQLite 讀取 broad fallback 區塊之外；不合法輸入會 fail closed，不會被捕獲成 SQLite 讀取錯誤後改讀 CSV。approved raw-alias guard 未放寬。
- `scripts/scheduled/run_daily_data_update_quick.py` 新增 `_annotate_currentity_recompute_outcome`，區分零更新、一般失敗、SQLite 寫入失敗、取消與部分失敗。部分成功保留成功/更新數量、完整失敗股票清單與具名錯誤碼；不再把 `success=False` 一律當成 `technical_currentity_recompute_produced_no_updates`。
- 合成整合測試在隔離 SQLite 的 `daily_prices` 中實際儲存 TEXT 值 `2,150.00`／`2,270.00`，經真實 `DBManager.execute_query` 讀取，再走 `calculate_technical_indicators(use_sqlite=True)`。有效輸入可在 guard 後到達 calculator 並保有預期值；過期 alias `2,150.01` 與非有限值 `inf` 被拒絕，且測試以存在的合法 CSV fallback 檔和 `read_csv` 追蹤證明沒有退回 CSV。
- runner synthetic regression 覆蓋 2199 筆成功、1 支失敗（`910708`）與零更新分支；保留失敗代號，不隱藏部分結果。

## 重跑命令與環境

驗證使用新的系統 TEMP root、`PROFILE=test`、隔離 `DATA_ROOT`／`OUTPUT_ROOT`／Python cache；沒有 scheduler、正式 writer、正式資料庫或 ML rebuild。PowerShell 重跑：

```powershell
$qaRoot = Join-Path $env:TEMP ('tp_' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
$env:TEMP = $qaRoot; $env:TMP = $qaRoot; $env:TMPDIR = $qaRoot
$env:PYTHONPYCACHEPREFIX = Join-Path $qaRoot 'pycache'
New-Item -ItemType Directory -Path $env:DATA_ROOT,$env:OUTPUT_ROOT,$env:PYTHONPYCACHEPREFIX | Out-Null
& .\.venv\Scripts\python.exe -m pytest `
  tests/test_formal_technical_raw_alias_repair.py `
  tests/test_formal_technical_raw_alias_numeric_formats.py `
  tests/test_scheduled_data_update_runner.py `
  tests/test_update_service_status.py `
  -q -o addopts=
```

實際收據：`<USER_HOME>\AppData\Local\Temp\tp_final_f7f67a47\pytest.log`，SHA-256 `0CBD09AA54F3BE715914B557AA7C21FA2BCF0E33EB009B6AD2771D832BC0C0E1`。無 skip；pytest 報一項 cache-provider 警告：工作區 `.pytest_cache` 權限拒絕寫入 nodeids，測試仍 `141 passed`，未影響隔離 DATA／OUTPUT root。

## Static 驗證

- changed Python 五檔 `py_compile` exit 0：`app_module/update_service.py`、`scripts/scheduled/run_daily_data_update_quick.py`、`tests/test_formal_technical_raw_alias_repair.py`、`tests/test_formal_technical_raw_alias_numeric_formats.py`、`tests/test_scheduled_data_update_runner.py`。空輸出 log `<USER_HOME>\AppData\Local\Temp\tp_finalstatic_b888d424\py_compile.log`，SHA-256 `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`。
- scoped mypy：`python -m mypy app_module/update_service.py scripts/scheduled/run_daily_data_update_quick.py --follow-imports=silent --cache-dir <isolated-cache>`；`2 source files / 0 issues`。log `<USER_HOME>\AppData\Local\Temp\tp_finalmypy_ee470b61\mypy.log`，SHA-256 `0C37C4158C91EF55C724BA017BF6465F26018199BADB08E3FF13F98ACDF056C2`。
- `git diff --check` exit 0。log `<USER_HOME>\AppData\Local\Temp\tp_finalstatic_b888d424\diff-check.log`，SHA-256 `3B49A5A53B534C4CF17569BB67BF2201164F37C652D1EDE5CF729B45A646CED8`；Git 輸出僅有工作樹 LF/CRLF 提示。

## 收據與檔案 bytes

| 路徑 | bytes | SHA-256 |
|---|---:|---|
| `app_module/update_service.py` | 275006 | `85BD255DD25059881452429F344B38448F9B4E44E13F8D6A60073EDD663B41C7` |
| `scripts/scheduled/run_daily_data_update_quick.py` | 45503 | `311654F851F7691E1AD76E3AA589EB46CD79975381C6461C0CB3B3DD5E074E12` |
| `tests/test_formal_technical_raw_alias_repair.py` | 60534 | `FB8816A657897FF07B41E7D4B32122FD2FF253616CE0A238A8A9C881360B7E26` |
| `tests/test_formal_technical_raw_alias_numeric_formats.py` | 8094 | `1EFE1ED846C5B31CBBB9F1C732080A43CA3367364E60B292D92E56B0C4D03955` |
| `tests/test_scheduled_data_update_runner.py` | 20528 | `90FE7CD84F0EF1243CACF114D3024AE7C540AB4CBE987B4383D64C6814D17A23` |

兩個 production source 在本切片開始前已有其他 dirty hunks。本切片僅負責本報告列出的 parser 順序與 runner outcome 分類；原有 TAIEX/source-evidence 變更及其他 owner 的內容均保留，未把整個 dirty file 歸為本切片產物。上述 hash 是目前完整檔案 bytes 的收據，不是只屬於本切片 hunk 的 hash。

## 邊界與後續

- 沒有執行 Windows Task Scheduler、quick-update full chain、正式 SQLite、正式 CSV writer、資料重建、模型訓練或 promotion；沒有觸碰正式資料。
- 測試證明 parser／guard 與 runner classification 的 bounded 行為，不代表 2026-09-25 市場資料已完整更新，也不取代下一次自然排程的 same-run status/artifact readback。
- 本 QA 驗收不涵蓋另行排隊的 formal holiday status 分類、backtest Decimal serializer、calibration learner 或 Runtime family status 投影。
- 未 stage、commit 或 push。
