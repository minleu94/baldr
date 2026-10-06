# R007 標準時區名稱別名勘誤報告

IMPLEMENTATION_STATUS: READY_FOR_REVIEW

## 發現

R007 前一版會在 exact builtin `datetime.timezone`、exact builtin `timedelta` offset 的情況下直接保留原 datetime。若建立 timezone 時傳入帶可變 payload 的 `str` 子類別，`datetime.tzname()` 仍回傳同一個呼叫者名稱物件，讓 sealed contract graph 間接保留外部可變別名。這影響 `Availability.available_at` 與 `MarketSlice.cutoff_at`；巢狀 observation 透過同一個 `Availability` 建構路徑受影響。

## 修正

`_freeze_aware_datetime()` 現在也檢查 exact builtin `timezone`／`ZoneInfo` 的 `tzname()` 結果。只有 exact builtin datetime、exact builtin timedelta offset 與 exact builtin str 名稱同時成立時才保留原 datetime，因此標準 `ZoneInfo` identity、DST／fold 規則、offset、ISO、timestamp 與名稱語意維持原樣。

標準時區名稱若為 `str` 子類別，會以 `str.__str__()` 建立 exact builtin str 快照；offset 子類別仍使用 `timedelta` builtin 描述器複製為 exact builtin timedelta。新的 builtin datetime 使用固定 offset 與封存名稱，不留住呼叫者的 timezone 或名稱物件。若標準時區回傳值不是字串則拒絕，不把無法安全表示的值封存。

回歸測試確認同一個帶可變 payload 的名稱子類別，經 direct Availability、巢狀 observation Availability 與 MarketSlice cutoff 封存後都不再可達；sealed 名稱為 exact str，且原 offset、ISO、timestamp 與 fold 相同。既有 ZoneInfo DST/fold identity 測試繼續通過。

## 驗證

- `PYTHONDONTWRITEBYTECODE=1 .\.venv\Scripts\python.exe -B -m pytest tests\test_data_market_contracts.py tests\test_data_module.py -q -o addopts= -p no:cacheprovider`：**21 passed**。涵蓋 leaf contract 與子程序 import 無 I/O／無逆向依賴檢查。
- `mypy --explicit-package-bases data_module\__init__.py data_module\contracts\market.py data_module\contracts\__init__.py`：**Success，3 source files**。
- `py_compile data_module\contracts\market.py tests\test_data_market_contracts.py`：exit 0。
- whitespace 檢查：兩個程式檔與本報告無 trailing whitespace。
- 第一次 pytest 未將 `PYTHONDONTWRITEBYTECODE` 傳入 import-smoke 子程序，稽核 hook 因該子程序寫 `.pyc` 而拒絕；設置繼承環境變數後重跑全數通過。這是測試啟動環境差異，非 contract import 的檔案／DB I/O。

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests\test_data_market_contracts.py tests\test_data_module.py -q -o addopts= -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m mypy --explicit-package-bases data_module\__init__.py data_module\contracts\market.py data_module\contracts\__init__.py
.\.venv\Scripts\python.exe -B -m py_compile data_module\contracts\market.py tests\test_data_market_contracts.py
```

## SHA-256

| 檔案 | 目前 SHA-256 |
|---|---|
| `data_module/contracts/market.py` | `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A` |
| `tests/test_data_market_contracts.py` | `E98E905515C4B9BE6D4EFD420D44A16AD3ED6FFE1D128A68E850340D4F0C4E4B` |

## 範圍與回復

只修改 `data_module/contracts/market.py`、`tests/test_data_market_contracts.py`，並新增本 R007 勘誤報告。未修改 app／decision R008 檔、provider、正式資料或其他 task；未 stage、commit 或 push。

變更前的兩個未追蹤 R007 檔案備份於 `%TEMP%\r007_tzname_alias_prechange_20260922\`。回復時將備份中的 `market.py` 與 `test_data_market_contracts.py` 複製回各自 repo 路徑，並移除本報告；此操作不涉及其他 dirty files。
