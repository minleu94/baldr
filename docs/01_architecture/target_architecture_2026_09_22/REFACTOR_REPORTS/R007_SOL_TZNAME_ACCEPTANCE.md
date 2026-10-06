# R007 時區名稱別名勘誤：SOL 驗收

TASK_STATUS: PASS

R007 的前次 PASS 僅適用於舊 SHA。本次補上 exact `datetime.timezone` 保留 caller-owned `str` 子類名稱的別名缺口；封存後的 `tzname()` 不再回傳呼叫者持有且可變的名稱物件。修正只涉及 R007 leaf contract、其測試與勘誤報告，沒有接入 production consumer 或改動資料、數值計算、ML ABI。

## 驗收基準

| 證據 | SHA-256／結果 |
|---|---|
| `data_module/contracts/market.py` | `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A` |
| `tests/test_data_market_contracts.py` | `E98E905515C4B9BE6D4EFD420D44A16AD3ED6FFE1D128A68E850340D4F0C4E4B` |
| `R007_TZNAME_ALIAS_ERRATUM_REPORT.md` | `989FD167DAFDE5C461EACAF8462A6C9881AE8778641227B70DFFAB33C0B843A3` |
| 獨立 Luna 複核 | `R007_LUNA_TZNAME_INDEPENDENT_REVIEW.md`，`REVIEW_STATUS: PASS` |
| SOL 合併契約測試 | R007/R008/import/execution focused bundle `80 passed`，其中 R007 leaf/import route `21 passed` |
| SOL scoped mypy | 6 個指定 data/decision/app source 無錯誤 |
| SOL 語法與 diff | changed contract/test `py_compile` 通過；`git diff --check` exit 0；index 為空 |

我檢查了實際 helper：exact 標準時區只有在 offset 為 exact `timedelta`、名稱為 exact `str` 時保留；其他標準時區名稱用 `str.__str__()` 複製底層文字，offset 用內建 `timedelta` 描述符複製，保留原時點、fold、ISO 與 timestamp。新測試涵蓋 `Availability`、巢狀 observation 及 `MarketSlice`，外部變更名稱後 sealed value 不漂移。既有 no-I/O import、DST/fold、datetime/timedelta 子類與數值型別邊界仍通過。

此裁決僅恢復 R007 與 Wave 1 dependency；R008 仍須依最新 SHA 獨立審查並由 SOL 驗收，Wave 3 不因此單獨解鎖。既有工作樹其他 dirty/untracked 檔案保留，未 stage、commit 或 push。
