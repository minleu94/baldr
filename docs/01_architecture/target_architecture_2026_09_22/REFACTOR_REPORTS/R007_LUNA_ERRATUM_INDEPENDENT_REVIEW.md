# R007 日期深凍結勘誤獨立審查

REVIEW_STATUS: PASS

## 凍結範圍

本審查只針對下列 root 指定的終版 bytes。三檔 SHA-256 在測試前及測試後均核對相符；未對仍在變動的 app／decision 檔案作 bytes verdict。

| 檔案 | SHA-256 |
|---|---|
| `data_module/contracts/market.py` | `6BE9FA87D9B3E49F75603CAD6F3263E27EEFE5942D2566902B7169FD752C3D84` |
| `tests/test_data_market_contracts.py` | `878113E6E7A92FC966FEA90D6A981613F8FCFBE80F3E051E5BCA73AF9FCC30B6` |
| `REFACTOR_REPORTS/R007_DATETIME_FREEZE_ERRATUM_REPORT.md` | `F51C781CBDEA9DD88FB0137CFA44149F22A34DCDE038DD17D7DE935E03CA6243` |

## 審查結果

終版封住本輪發現的 caller-owned alias 路徑。所有非空字串欄位要求 exact `str`；`Availability.status` 要求 exact `AvailabilityStatus`，拒絕 `__class__` 偽裝物件；`SourceObservation` 的 unit、availability、source ref 與 `MarketSlice` 的 observation、source ref 均要求 exact contract type。`MarketSlice` 將輸入 iterable 複製成 tuple，tuple 內容再受上述 exact-type 與欄位驗證保護。

日期欄位要求 exact `date`，因此 `datetime`／可帶額外狀態的 date subclass 不會留在契約欄位。Aware datetime subclass 會快照成 builtin `datetime`；讀取底層日期／時間／fold 欄位使用 builtin descriptor。`utcoffset()` 的 `timedelta` subclass 也會以 builtin descriptor 重建成 exact `timedelta`，不保留其 mutable payload。即使 exact `datetime.timezone` 包著 timedelta subclass，也會走快照路徑。只有 exact builtin datetime、標準 `timezone` 或 `ZoneInfo`，且 offset 為 exact builtin `timedelta` 時才保留原時區物件。

`timezone.utc` 與一般固定 `timezone` 的 wall-clock、offset、microseconds、fold、ISO 與 timestamp 維持原值；`ZoneInfo` 保留原 identity、名稱及 DST／fold 語意。其他時區只保留建構當刻的 offset，custom `tzname()` 不在保留契約內，且不執行時區轉換。

PIT 欄位保留其事實語意：known availability 必須有日期或 aware timestamp；unknown 不得攜帶日期或 timestamp。日期型 availability 不會被補成 timestamp；`None` 值、Decimal zero、unknown availability 與缺少 observation row 彼此有測試區分。`MarketSlice` 拒絕晚於 `as_of_date` 的 observation date；它保存 availability／cutoff 事實，不宣稱已替 consumer 判定 PIT eligibility。

canonical `AvailabilityStatus` 是本契約允許的 enum。其全域 singleton 可被 trusted code 事後 monkeypatch 非契約屬性；依本次裁定，這不屬 constructor-retained caller alias，且底層 status/value 未變，因此不列為本勘誤 blocker。constructor 不接受自訂 mutable Enum 或偽裝物件。

契約模組僅依賴 Python 標準函式庫；`data_module` 頂層只用 lazy exports，contracts package 只匯出 market leaf types。靜態 imports 與子程序 import audit 均未發現檔案／SQLite I/O、app／analysis／backtest／decision／ML／portfolio／UI 逆向載入。

## 獨立驗證

R007 leaf 與既有 data-module import 相容 focused route：`20 passed`。

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_data_market_contracts.py tests\test_data_module.py -q -o addopts= -p no:cacheprovider
```

erratum 所列相鄰合併 focused command 另跑得 `63 passed`：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_data_market_contracts.py tests\test_data_module.py tests\test_recommendation_contracts.py tests\test_r008_decision_numeric_enum_rework.py -q -o addopts= -p no:cacheprovider
```

勘誤報告記載的較早合併執行為 `62 passed`；本次擴大重跑為 `63 passed`，兩次均無失敗。R008／app／decision 工作檔不在本審查凍結 bytes 集合，故只記錄測試結果，不對其內容或狀態作判定。

已檢查對應 regression cases：mutable tzinfo、datetime subclass 覆寫 `utcoffset()`／日期屬性、mutable timedelta subclass offset（含 trusted timezone 內的 offset）、`timezone.utc`、ZoneInfo DST fold、nested contract subclass、mutable str subclass、enum class spoof、None／zero／unknown／missing 與 duplicate identity，以及 import I/O／逆向依賴。

## 未解 finding

無。R007 勘誤終版 bytes 與 focused tests 支持本審查範圍內的 INV-03／INV-08 判定。
