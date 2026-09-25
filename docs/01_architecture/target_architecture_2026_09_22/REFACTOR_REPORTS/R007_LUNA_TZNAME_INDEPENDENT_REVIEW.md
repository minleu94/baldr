# R007 標準時區名稱別名勘誤獨立審查

## 凍結範圍

本次只審查 root 指定的三份凍結輸入。審查開始、測試完成後的 SHA-256 均相同。

| 檔案 | SHA-256 |
|---|---|
| `data_module/contracts/market.py` | `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A` |
| `tests/test_data_market_contracts.py` | `E98E905515C4B9BE6D4EFD420D44A16AD3ED6FFE1D128A68E850340D4F0C4E4B` |
| `REFACTOR_REPORTS/R007_TZNAME_ALIAS_ERRATUM_REPORT.md` | `989FD167DAFDE5C461EACAF8462A6C9881AE8778641227B70DFFAB33C0B843A3` |

另核對 R007 規格、`INV-03/05/08`、既有 R007 驗收與獨立審查。以修正前暫存副本比對實際檔案後，production diff 僅在 `_freeze_aware_datetime()` 封存標準時區名稱並用 builtin `str` 重建固定時區；測試 diff 僅新增可變 `str` 子類別名稱的回歸案例。未改 package exports、provider、consumer、資料、ML schema 或數值計算。

## 審查結果

修正封住了 `datetime.timezone` 保留呼叫者可變 `str` 子類別名稱的別名。只有 exact builtin `datetime`、標準 `timezone`／`ZoneInfo`、exact builtin `timedelta` offset 與 exact builtin `str` 名稱同時成立時才保留原物件。其他標準時區名稱會以 `str.__str__()` 複製成 builtin 字串，並以凍結 offset 和該名稱建立新的固定時區；非標準 `tzinfo` 仍只封存當時 offset。這符合 INV-08 的無可變別名要求。

直接 `Availability.available_at`、巢狀 observation 的 availability 與 `MarketSlice.cutoff_at` 都有回歸覆蓋。測試確認時區名稱內容、offset、ISO 表示、timestamp 與 `fold` 保持一致，且封存值不再指向來源時區或可變名稱物件。原有 `ZoneInfo` DST/fold identity、mutable `tzinfo`、datetime 子類別和 timedelta 子類別案例仍在同一測試範圍。

我另以 `days`、`seconds`、`microseconds` 屬性遭覆寫的 `timedelta` 子類別做唯讀 probe；封存結果仍是 exact builtin `timedelta(+05:00)`，ISO 與 timestamp 與來源一致。mapping payload 被封閉的 `MarketFactValue` 型別拒絕；exact `date`、revision/scalar 型別、status enum、nested record exact type 與 tuple 複製檢查均符合現有程式碼。`None`、數值零、unknown availability 與缺少 row 保持不同表示，沒有重新推算 availability 或改變 PIT／商業語意，符合 INV-05。

契約 leaf 只依賴 Python 標準函式庫；`data_module/contracts/__init__.py` 只匯出 market types。現有 subprocess import audit 通過，未觸發 SQLite 或非程式檔案讀取，且沒有載入 app、domain、ML、UI 或具體 data provider，符合 INV-03。

## 獨立驗證

- `tests/test_data_market_contracts.py tests/test_data_module.py`：**21 passed**。
- `mypy --no-incremental --explicit-package-bases data_module/__init__.py data_module/contracts/market.py data_module/contracts/__init__.py`：**Success，3 source files**。
- 額外 timedelta 子類別覆寫屬性及 mapping payload probes：通過。
- 三份凍結輸入測試後 SHA-256 與指定值一致；來源、測試與實作報告無 trailing whitespace。
- 未修改 production code 或 tests；本報告是唯一新增檔案。

未發現範圍內缺陷，R007 timezone-name erratum 可按指定 bytes 通過獨立審查。

REVIEW_STATUS: PASS
