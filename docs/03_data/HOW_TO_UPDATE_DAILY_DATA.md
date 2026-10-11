# 每日資料更新操作指南

> 日常使用優先從 PySide6 UI 的「數據更新」工作區執行。
> 完整 UI 說明見 [APPLICATION_MANUAL.md](../07_guides/APPLICATION_MANUAL.md)。

## 1. 啟動

```powershell
.\.venv\Scripts\python.exe ui_qt\main.py
```

## 2. 日常首選：快速更新

1. 開啟「數據更新」。
2. 點擊「檢查數據狀態」。
3. 點擊「快速更新 (跳過大型合併)」。
4. 等待底部日誌顯示完成。
5. 再次檢查狀態，確認每日股價與技術指標日期。

快速更新預設會下載結束日前最近 10 個工作日的缺失資料；仍會更新必要的每日來源 CSV 並增量同步 SQLite，只略過大型歷史合併檔的重寫，不是「僅 SQLite」。每日股價包含 TWSE `MI_INDEX type=ALL` 與 TPEX official daily close quotes；TWSE CSV 會寫到 `DATA_ROOT/daily_price/YYYYMMDD.csv`，TPEX CSV 會寫到 `DATA_ROOT/daily_price_tpex/YYYYMMDD.csv`，最後一併 upsert 到 SQLite `daily_prices`。

## 3. 完整備份：安全更新

使用「安全更新（完整 CSV + SQLite）」時，系統會保留完整 CSV 整合與 SQLite 同步流程。適合：

- 定期備份
- 資料修復後
- 需要人工檢查完整 CSV
- 確認雙軌資料一致性

安全更新同樣預設使用最近 10 個工作日窗口，並會在每日股價步驟後抓取 TPEX official daily close quotes，在 SQLite 同步時與 TWSE 日價一起寫入 `daily_prices`。TPEX endpoint 連線 timeout 或暫時失敗時會在完成訊息中以警告顯示，流程仍會繼續同步已成功取得的 TWSE 與其他資料，不會靜默略過。

## 4. 手動更新單一來源

### 每日股價

1. 選擇「每日股價」。
2. 設定結束日期與最近範圍。
3. 點擊「手動下載此資料源」。
4. 等待完成，並確認 SQLite 同步與技術指標更新結果。

目前 UI 的「每日股價」手動下載會依序處理 TWSE 與 TPEX 指定日期範圍：TWSE 寫入 `DATA_ROOT/daily_price/YYYYMMDD.csv`，TPEX 寫入 `DATA_ROOT/daily_price_tpex/YYYYMMDD.csv`，接著同步 SQLite `daily_prices` 並執行技術指標增量更新。因此這個流程不需要再手動點「合併每日股價」或另開「技術指標」重跑。若來源更新、SQLite 同步或技術指標計算失敗，請依完成訊息中的失敗／警告檢查狀態，再針對缺漏項目處理；TPEX 暫時 timeout 時 UI 會顯示 warning。

若需要長期間補齊 TPEX 與技術指標，可在每日股價頁使用「背景補齊 TPEX + 技術指標」；進度由 `DATA_ROOT/meta_data/tpex_full_refresh_status.json` 記錄，並可用「檢查背景任務狀態」讀取。

### 大盤與產業

設定日期範圍後下載，並確認資料已同步至 `market_indices` 或 `industry_indices`。

### 券商分點

1. 設定日期範圍。
2. 手動下載。
3. 點擊「合併券商分點」。
4. 確認 `broker_flows` 日期與筆數。

追蹤範圍以 Registry 的有效啟用列為準，數量可能隨設定變更。資料品質使用 `observed`、`estimated`、`unavailable` 三態。`broker_flows` 的 SQLite 身份鍵包含 `trade_type`，因此同一分點 / 股票 / 日期可以同時保存買超與賣超榜單；舊 DB 若仍是三欄主鍵，下一次同步券商分點時會先備份再受控升級。現行操作與安全界線以 [Application Manual](../07_guides/APPLICATION_MANUAL.md) 為準。

### 技術指標

- 增量更新：日常使用。
- 強制全量更新：只在算法變更或資料修復時使用。
- 可輸入單一股票代號限制處理範圍。

## 5. SQLite Inspector

使用「SQLite 資料檢視」可唯讀查看：

- 資料預覽
- Schema
- 股票、分點與日期篩選
- 受控筆數上限

不要把 Inspector 當成資料修改工具。

SQLite Inspector 日期控件預設為單一日期今天、區間本月 1 日至今天；若查詢 `3207` 只看到近一兩日，代表 TPEX 歷史補齊或 SQLite 同步未完成。歷史基準：2026-06-17 的排查記錄當時 `20140102..20260617` 共 2,907 筆，見[當日 healthcheck 原件](../09_archive/FULL_APP_HEALTHCHECK_2026_06_16.md)；這個日期與筆數不是目前資料庫狀態，現況須以 Inspector 的選定查詢範圍檢查。

## 6. 匯出 CSV

個別資料頁的「匯出 CSV 備案」可輸出最近範圍或全部歷史，使用 UTF-8 with BOM。

## 7. 受限 CLI 參考（不等同完整 UI 流程）

以下舊式 CLI 範例不等同 UI 的完整 TWSE／TPEX／SQLite／技術指標流程。`batch_update_daily_data.py` 僅下載 TWSE 日檔到 `daily_price/`，不會同步 SQLite `daily_prices`；省略 `--end-date` 時會更新到今天。`update_daily_stock_data.py --merge` 會把 TWSE 日檔彙整到 `all_stocks_data_file`，不含 TPEX，也不會同步 `daily_prices`。這與下方 `scripts/merge_daily_data.py` 是不同流程：後者讀取 `daily_price/` 與 `daily_price_tpex/` 可用日檔並寫出彙整 CSV，也不代表已完成 UI 的 SQLite 同步或技術指標更新。日常完整更新請依上方 UI 流程；執行任何會寫入的 CLI 前，先確認 `DATA_ROOT`、輸出路徑與日期範圍。

### 批量更新

```powershell
.\.venv\Scripts\python.exe scripts\batch_update_daily_data.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

### 單日更新

```powershell
.\.venv\Scripts\python.exe scripts\update_daily_stock_data.py --date 2026-06-12 --merge
```

### 合併既有每日檔

```powershell
.\.venv\Scripts\python.exe scripts\merge_daily_data.py
```

### TPEX 歷史缺口檢查

日常每日股價、快速更新、安全更新與背景補齊流程都會補缺少的 TPEX CSV 並同步 SQLite。若需要先盤點缺口，可產生 dry-run plan，確認日期範圍、候選新增筆數、既有筆數與失敗日期：

```powershell
.\.venv\Scripts\python.exe scripts\plan_tpex_daily_price_history_backfill.py --start-date 2026-01-01 --end-date 2026-06-16
```

此工具只讀資料並輸出報告，不寫正式 DB；實際補齊優先使用 UI 每日股價區間更新或背景補齊流程。

## 8. 注意事項

1. 日期使用 `YYYY-MM-DD`。
2. 週末與休市日沒有交易資料。
3. 手動下載完成不代表所有分析資料均可用。每日股價 UI 流程會自動同步 SQLite 並增量計算技術指標；其他來源是否需要另行合併或計算，請依該流程的完成訊息與狀態檢查結果判斷。
4. 不要把強制重建當成日常更新。
5. 不得刪除正式 raw 原始資料。
6. `companies.csv` 只是公司 / 產業 / 市場 registry，不代表 `daily_prices` 已有該股票日價；TPEX 日價屬市場資料層，不屬於 fundamental layer。

## 9. 排錯

### API 或網路錯誤

檢查網路、交易日與底部日誌，等待後重試缺失日期。

### 更新完成但 UI 日期未變

1. 重新檢查數據狀態。
2. 確認資料已合併至 SQLite。
3. 確認技術指標已計算。
4. 使用 SQLite Inspector 查看對應資料表。

### 詳細故障排除

目前排錯請見[操作手冊第 12 節](../07_guides/APPLICATION_MANUAL.md#12-常見問題)；更新操作與安全限制見[操作手冊第 4 節](../07_guides/APPLICATION_MANUAL.md#4-數據更新)。舊故障排除指南已[封存](../09_archive/TROUBLESHOOTING_DAILY_UPDATE_HISTORY.md)。
