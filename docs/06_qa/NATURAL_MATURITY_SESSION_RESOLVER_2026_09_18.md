# Natural maturity session resolver QA（2026-09-18）

本文件記錄 `data_module/natural_maturity_session_resolver.py` 的 bounded
contract 與本輪可重現驗證。範圍只包含官方交易日序列、TAIEX 收盤觀測與 proof
重驗；沒有執行 production runner、scheduler、資料寫入或自然學習 credit。

## Contract

`NaturalMaturitySessionResolver(db_path, calendar_cache_path,
temporary_closure_path=None)` 提供：

```python
resolve(
    capture_date: str,
    evaluation_at: datetime,
    horizon_sessions: int = 20,
) -> SessionResolution
```

`evaluation_at` 必須是 timezone-aware。resolver 只接受三種狀態：

- `ready`：官方 annual plan、temporary closure scope（若有配置）、capture 日
  baseline 與 exact N 個 TAIEX session close 都已驗證。
- `pending`：市場列缺失、尚未到 close visibility、calendar/market 衝突或
  baseline 不可用；缺少中間 session 不會移位到下一筆 row。
- `waiting_for_calendar`：annual cache 缺失、future、過期、tampered，或已配置的
  temporary closure cache 不可驗證。

session 序列只由 hash-verified TWSE annual cache 加上明確 temporary closure
evidence 決定。未配置 temporary cache 時 proof 會標示
`calendar.status=annual_plan_only`，不把它解讀為完整未來休市保證。

市場來源是 SQLite `market_indices` 的 `指數名稱='TAIEX'` rows，使用
`mode=ro` 與 `PRAGMA query_only=ON`。close 必須是 finite、positive 且
`收盤指數`／`收盤價`（若同時存在）一致；同一 TAIEX 日期重複、衝突或 malformed
會 fail-closed。proof 同時保存：

- `market.baseline_observation`：capture 日唯一 TAIEX close，供 close-to-close
  benchmark 使用。
- `market.observations`：exact planned session rows。
- `market.bounded_source_observations_hash`：bounded query 的完整 row hash。
- `market.source_db_path`、`source_schema_hash` 與 resolve 當下的 `source_db_stat`。
  stat 是同一 source 的 capture metadata；verifier 不以今天整個 DB 的 mtime／size
  取代 bounded row hash 驗證。

可見市場日期由台北時間 14:30 close cutoff 決定。evaluation 當日 14:30 前的
同日 row 不會影響較早 endpoint；evaluation 之後的 rows 也不在 query 範圍內。
capture 到 endpoint 內若出現週末或 official calendar 判定休市的 TAIEX row，結果為
`calendar_market_session_conflict`。

## Proof verifier

`NaturalMaturitySessionResolver.verify_session_proof(...,
expected_db_path=...)` 不只檢查 proof 自報 hash：

1. 依 proof 列出的 annual cache exact path，在 proof 原始 `evaluation_at` 重跑既有
   `load_verified_twse_calendar_cache`，核對 bytes、content hash、source evidence。
2. 只重驗 proof 列出的 temporary closure exact files；新增的後續檔案不會改寫既有
   receipt，檔案本身被竄改則 fail-closed。
3. 以重驗後的 schedule 重建 exact session sequence，核對 endpoint、horizon 與
   proof session dates。
4. 以 `expected_db_path` bounded 重讀 capture 到可見日期的 TAIEX rows，核對
   baseline、每個 planned observation、row hash、schema hash 與完整 bounded hash。

因此重新計算一個偽造 proof hash，仍不能把不同的 calendar 或市場 close 變成可驗證
的 natural evidence。通過 resolver proof 也不代表自然學習 credit 已授予；consumer
仍須使用 exact 個股 endpoint、既定 evaluator 與 promotion policy。

## 驗證證據

專屬測試：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_natural_maturity_session_resolver.py -q -o addopts=
11 passed, 1 warning
```

原先的 9-case 結果仍保留在歷史 raw log
`output/qa/natural_maturity_session_resolver_20260918/`；本輪最新 11-case 結果在
`output/qa/daily_banktaiwan_learning_cost_20260918/pytest_natural_maturity_final.log`。
11 個案例涵蓋 ready proof 重讀、DB row tamper、重算 proof hash 的偽造 row、annual
cache tamper、missing middle session 不移位、evaluation close-time cutoff、future
malformed row 排除、expired cache 不跨 resolve 重用、weekend/calendar-market
conflict，以及 compact `YYYYMMDD` 與 ISO `YYYY-MM-DD` 的跨年 bounded query。跨年
案例使用 capture `2025-12-15`、horizon `20`、官方 `2026-01-01` 休市排除，兩種
日期格式都得到同一 endpoint `2026-01-13`，並完成 `verify_session_proof` 重讀。
warning 僅為 pytest cache 目錄權限，未影響測試結果。

語法與型別：

```text
.\.venv\Scripts\python.exe -m py_compile data_module/natural_maturity_session_resolver.py tests/test_natural_maturity_session_resolver.py
exit code 0

.\.venv\Scripts\python.exe -m mypy data_module/natural_maturity_session_resolver.py
Success: no issues found in 1 source file
```

raw command output 保存在被 git 排除的
`output/qa/natural_maturity_session_resolver_20260918/` 與
`output/qa/daily_banktaiwan_learning_cost_20260918/`。成本 fixture 的 3-case、
完整 29-case、resolver 11-case、`py_compile`、resolver `mypy` 與 diff check
摘要見同目錄 `SUMMARY.md`；該摘要明確區分正式／production source 的唯讀稽核與
隔離 pytest fixture 建立暫存 SQLite。這些測試結果不保證收益，也不把 historical
replay 或 synthetic fixture 轉成 natural authority。

本輪新增／修改範圍只有 resolver、其專屬測試與本 QA 文件，以及成本測試的隔離
fixture／QA output；沒有修改正式 DB、scheduler、production runner 或 C
integration。
