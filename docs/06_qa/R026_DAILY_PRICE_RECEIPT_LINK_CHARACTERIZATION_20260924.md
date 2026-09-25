# R026 每日價格修訂 receipt 連結特性查核

- 日期：2026-09-24
- 範圍：`data_module/ml_daily_price_revision_gate.py` 的直接 repair receipt 自動搜尋與連結解析。
- 狀態：直接 repair receipt 路徑 guard bounded slice 已由 root 獨立複核為 `ACCEPTED_SCOPE`。此 slice 不關閉 R026 或 TMP-ML-01。

## 隔離與來源

- 平台：Windows，Python 3.11.9，`sys.platform=win32`。
- 執行環境：`PROFILE=test`；`DATA_ROOT`、`OUTPUT_ROOT` 指向新建的短 TEMP QA 目錄。每個案例另用 pytest `tmp_path` 建立合成資料根、空 SQLite 路徑佔位檔及合成 receipt；三個其他 revision guard 只在該測試程序內替換成 no-op，不讀正式資料。
- 目錄 junction 能以 PowerShell 建立。Python 對 junction 回報 `Path.is_symlink() == False`，但 `Path.resolve()` 會追到目標。
- 檔案 symlink 探針因 Windows `WinError 1314`（目前登入權限缺少必要 privilege）無法建立；本輪未把檔案 symlink 算入覆蓋，也未將其跳過後宣稱通過。測試直接使用可建立的目錄 junction 驗證同一個父路徑解析邊界。
- 修補前 baseline 的 `data_module/ml_daily_price_revision_gate.py` SHA-256：`09CB384DE93ACDD5771A823CB4214009CF052688312FC77349846DA41132117E`；修補後 SHA 見本報告的最終驗證段。

## 修補前觀察到的行為（baseline）

| 合成情境 | 目前觀察 | 安全判讀 |
|---|---|---|
| 沒有自動 receipt | `check_daily_price_source_revision()` 回傳 `None` | 正常的無 receipt 行為；不單獨代表有修訂。 |
| 資料根內普通 receipt，修訂日落在決策 prefix | 拋出 `DailyPriceSourceRevisionError`，訊息為 PIT prefix block | 已找到並解析的相關修訂維持 fail-closed。 |
| 目錄 junction 目標仍在隔離資料根內 | receipt 被讀取，摘要路徑為解析後的內部目標 | 內部 junction 可用；本案例沒有跨出隔離資料根。 |
| 自動 receipt 目錄 junction 指向資料根外 | `is_file()` 跟隨 junction 找到 receipt；`_check_receipt()` 將候選 `resolve()` 到外部檔案，且 `is_symlink()` 為 false | 目前對自動搜尋路徑沒有資料根 containment。外部未來日期 receipt 仍回傳摘要、`relevant_row_count=0`；外部 cutoff 內 receipt 仍會被讀取並觸發 PIT block。故這是信任邊界 fail-open，並非相關修訂列的 cutoff 檢查也 fail-open。 |
| 自動 receipt 目錄 junction 的目標被移除 | dangling junction 下的 `pending.json`／`receipt.json` 不符合 `Path.is_file()`，候選變成空 tuple，函式回傳 `None` | 缺失的自動候選被當成沒有 receipt，屬 fail-open。 |
| 同一 dangling junction 下明確指定 `receipt.json` | explicit path 先 resolve 成不存在的目標檔；`_check_receipt()` 拋 `receipt is missing` | explicit 缺檔維持 fail-closed。 |
| 明確路徑使用資料根內 junction alias，且自動搜尋已找到同一普通 receipt | `source_revision_receipt_candidates()` 的 tuple 去重後只含一個候選；摘要計數為 1 | 目前的內部 alias 可去重，沒有重複套用同一 receipt。 |

上述結果由實際合成檔案與當前 gate 呼叫得到，沒有對外部目標寫入任何資料。此報告不主張 explicit 外部路徑的授權政策；本輪 red 預期只針對自動搜尋根的 containment 與 dangling 自動候選的 fail-closed 行為。

## Characterization 與修補後驗證

新增 `tests/test_r026_daily_price_receipt_link_characterization.py`，涵蓋正常缺席、一般 receipt、內部 junction、外部 junction、內部 alias 去重、讀取中 alias retarget、dangling 自動 root／child junction，以及 explicit dangling path。Windows 目錄 junction 均實際建立並執行，沒有 skip；一般檔案 symlink 因 `WinError 1314` 無法建立，未算入覆蓋。測試已登錄為 `service-oracle-recommendation`。

修補前 red receipt：fresh TEMP 路由 `C:\Users\archi\AppData\Local\Temp\r026red-53e40661\pytest.log` 為 `3 failed, 10 passed`；三個失敗是外部自動搜尋 root junction、dangling 自動 root junction及 dangling receipt child 被當成缺席。SHA-256 `670574A0D7CAC68FF362E28F3DAB4BCAD13291DD710BAF27E1E4193F173B7E3E`。這是修補前預期失敗證據，不作最終 gate。

修補後使用 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r026fix-62948352`，`PROFILE=test`、`DATA_ROOT=<TEMP>\data`、`OUTPUT_ROOT=<TEMP>\out`，執行 characterization 和既有同 bytes oracle：

```powershell
$env:PROFILE='test'
$env:DATA_ROOT='C:\Users\archi\AppData\Local\Temp\r026fix-62948352\data'
$env:OUTPUT_ROOT='C:\Users\archi\AppData\Local\Temp\r026fix-62948352\out'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_daily_price_receipt_link_characterization.py `
  tests/test_r026_daily_price_receipt_same_bytes.py `
  -q -o addopts= -p no:cacheprovider
```

結果為 **14 passed / 0 skipped**。log `C:\Users\archi\AppData\Local\Temp\r026fix-62948352\pytest.log`，SHA-256 `9A86CF045083BA7C42E3B5ED84B3F296FD3131584865355E0A7D368308E010E7`。`mypy` 對 gate、link characterization、同 bytes 測試三檔為 0 issues；三檔 `py_compile` 通過，scoped `git diff --check` 無 whitespace error。此輪 inventory 已含新測試 entry；全庫 inventory blocker 不在此 bounded slice 處理。

Root 另以獨立 fresh short TEMP 路由執行 link characterization、同 bytes oracle 與 `tests/test_ml_pit_year_shard_exporter.py`，回報 **32 passed**，據此接受本 bounded slice。root gate 執行時的動態 TEMP 名稱未輸出，亦未保存 pytest log，故此處只記錄 root gate 回報，不虛構路徑或 log hash。

```powershell
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_daily_price_receipt_link_characterization.py `
  tests/test_r026_daily_price_receipt_same_bytes.py `
  tests/test_ml_pit_year_shard_exporter.py `
  -q -o addopts= -p no:cacheprovider
```

本輪實作 SHA-256：source `data_module/ml_daily_price_revision_gate.py` `C571F3155846ACB9DAE8D248432D72C571320CB76DF47436A66DE19DCC8143A9`；測試 `tests/test_r026_daily_price_receipt_link_characterization.py` `FDFB631F2EC3589E3E9EA3705FF801F1DC726065A45795DB242A041C86F97E7F`；shared inventory `qa/full_app_healthcheck/test_inventory.py` `61A322FB7C46A79DFD2DA953A2E05B09862ADAB7C690527E849B3CCE2E0D53C1`。

## 限制與下一步

- 自動固定搜尋根現在會拒絕 dangling、不可讀及資料根外路徑；明確指定路徑保留原行為。
- Windows 檔案 symlink 因 privilege 不足未能驗證；目前 coverage 是目錄 junction 的實際解析行為。
- 此隔離路由沒有測量完整 ML preparation、跨 checker source revision identity 或模型載入 ABI，不得視為 R026/TMP-ML-01 完成或 source-consistency gate 關閉。
- 讀取前後的兩次 resolve 只保證兩次觀察時是同一 target，不排除期間 retarget 後再還原的 ABA。此 slice 未建立 direct daily-price namespace identity，也未保證多檔／SQLite 交易原子性；跨 namespace identity 與 `TMP-ML-01` 仍未關閉。
