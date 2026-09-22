# 2026-09-21 個股研究資料鏈 Incident QA

## 結論

2026-09-21 的個股研究報告資料不是全鏈均勻新鮮。Formal daily price 與 technical 在目標交易日查到 bounded rows，且完成日期、重複鍵與 raw 對照檢查；這不等於全域交易所真值。institutional、credit、TDCC、monthly／quarterly fundamentals 與個別 broker coverage 則各有明確的期別或來源缺口。這些缺口必須保留為 stale、partial、unknown 或 source coverage，不能補成 0，也不能把候選庫內容當成 formal evidence。

本輪確認的程式根因是 freshness receipt 的 `candidate_only=true` 項目原本可能透過 source alias 認證 formal SQLite。修正後 `StockResearchReportReadService` 會跳過這類 receipt；候選資料只有在正式發布並進入 formal source 後才能被 formal reader 使用。沒有把正式 reader 改成 `immutable=1` fallback，也沒有放寬時區、future cutoff 或整份報告的 decision-date 契約。

## 查核範圍與來源

查核日：2026-09-21（Pacific local）；freshness receipt 的 `checked_at` 為 `2026-09-21T12:21:09-07:00`。

| 類別 | 實際路徑／證據 | 邊界 |
|---|---|---|
| Formal data root | `D:\Min\Python\Project\FA_Data` | 依 `TWStockConfig` 預設路徑；本輪只讀 |
| Formal SQLite | `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` | 3,600,588,800 bytes；未寫入 |
| Candidate SQLite | `D:\Min\Python\Project\FA_Data_candidate\phase3c_candidate.db` | 只作 candidate research；未發布到 formal |
| Freshness receipt | `D:\Min\Python\Project\FA_Data\output\scheduled\data_freshness\latest_status.json` | 保存 source status、actual／expected period 與 candidate-only 標記 |
| Raw daily files | `daily_price\20260921.csv`、`daily_price_tpex\20260921.csv` | 只作 raw row 對照，未回填 |

Formal SQLite 以 `file:...twstock.db?mode=ro` 開啟，另設 `PRAGMA query_only=ON`；沒有初始化 schema、writer、checkpoint、scheduler、回填或 learning update。sandbox 普通 `mode=ro` 的 `unable to open database file` 只保留為環境 lock 訊號；在受控 elevated read-only 查核中同一路徑可嚴格讀取，因此沒有把 immutable fallback 當成產品修復。active DB 查核未見 `twstock.db-wal` 或 `twstock.db-shm`。

可重跑的 scratch evidence：

- `output/qa/incident_20260921/formal_sql_queries.sql`
- `output/qa/incident_20260921/mode_ro_readback.json`
- `output/qa/incident_20260921/data_audit_readback.md`

## Formal 2026-09-21 row evidence

### 全市場 bounded counts

| Table | 2026-09-21 rows | distinct codes | 查核結果 |
|---|---:|---:|---|
| `daily_prices` | 1,968 | 1,968 | 查到 target-date rows；duplicate key 0 |
| `technical_indicators` | 1,965 | 1,965 | 查到 target-date rows；duplicate key 0 |
| `broker_flows` | 6,955 | 904 | branch grain；不能用 `(date, code)` 當唯一鍵 |

Formal daily／technical required code/date 欄位的 invalid count 為 0，且目標 raw rows 與查詢結果可對照；查核範圍內沒有晚於 2026-09-21 的 future rows。這是 bounded/full aggregate evidence，不代表所有資料源都在同一日期，也不替代官方交易所全域核驗。

### 使用者指出的個股

| 股票 | `daily_prices` 2026-09-21 | close | technical latest | formal broker latest／coverage |
|---|---:|---:|---|---|
| 2382 廣達 | 1 row | 344.5 | 2026-09-21 | 2026-09-21；19 rows |
| 3207 耀勝 | 1 row | 38.25 | 2026-09-21 | 2026-08-20；41 rows |
| 9935 慶豐富 | 1 row | 18.2 | 2026-09-21 | 2026-09-14；40 rows |
| 1418 東華 | 1 row | 17.55 | 2026-09-21 | 無 formal broker rows |

`institutional_flows` formal latest 為 2026-09-08（229,472 rows）；`credit_transactions` formal latest 為 2026-09-08（22,163 rows）；`tdcc_shareholding` formal latest 為 2026-09-04（4,047 rows）。四檔的這些來源只能標示其實際可得資料日，不能標成 9/21 current。

基本面 formal monthly 的全庫 latest available 約為 2026-07-15，statement latest available 為 2026-06-17；receipt 對目前 expected period 的判定仍為 stale。四檔的 valuation coverage 也不一致：2382／9935 有 2026-08-06 observation，3207／1418 沒有 valuation row。報告保留公告／available date 與 PIT 限制，不把 current snapshot 回填歷史表。

## Candidate 與 Paper 分類

Candidate DB 的 2026-09-21 institutional rows 為 23,704（2382／3207／9935 各 19，1418 為 17）；credit rows 為 2,216（四檔各 19）。這些 rows 位於 candidate DB，freshness receipt 亦帶 `candidate_only=true` 與 `candidate research only`，所以不是 formal SQLite 的 current evidence。

1418 Paper 的 blocked 狀態分類為 candidate／lineage 缺件；formal 查到 1418 的 9/21 price row，且該 row 可與 raw 對照。1418 沒有 broker row 或 ownership row 時，報告顯示缺件／unknown，不造 0，也不把缺件當作賣出或價格錯誤。

## Report 與 UI 判讀契約

個股報告每個 source row 分開顯示 `來源`、`來源狀態`、`品質`、`資料日`、`資料可得時間`、`更新狀態`、`版本`、`筆數`、`更新週期` 與 `預期資料期`；各區塊可有不同資料日。價格／technical 可顯示 9/21，籌碼可顯示 9/8 或 9/4，broker 依股票顯示個別最新日；這不是日期 label 錯置。

使用者看到 `stale`、`partial`、`unknown`、`missing` 或 source coverage gap 時，應保留診斷並核對 source trace／available time；不可手動補值、把空白當 0、以 candidate latest date 取代 formal date，或以舊的上次成功報告冒充新資料。

本輪整合中的 UI 行為也納入判讀契約：左側導覽群組與工作區項目左對齊；個股報告換股先清除舊股票內容，同股 reload 失敗／取消則明示 last-good data、資料日與本次 Journey 原因；持倉頁分開日常正文、可讀日期／原始 timestamp、Paper health 與模擬／歷史資料，進階正文可捲動；工作台與說明按鈕把 machine token 轉成白話。這些只改呈現與導引，不改 source rows、評分、交易或 writer。

## 修正與驗證

### 程式變更

- `app_module/stock_research_report_service.py`：`_load_freshness_statuses()` 忽略 `candidate_only is True` 的 receipt item，避免 candidate receipt 認證 formal SQLite。
- `tests/test_stock_research_report_service.py`：增加隔離 SQLite regression，確認 candidate-only receipt 不會把 formal source 標為 current，報告保留 `unknown`／`partial`。

### 已完成的 focused QA

```text
.\.venv\Scripts\python.exe -m pytest tests/test_stock_research_report_service.py -q -o addopts=
16 passed, 1 cache permission warning

.\.venv\Scripts\python.exe -m py_compile app_module\stock_research_report_service.py tests\test_stock_research_report_service.py
passed

git diff --check
passed (Git LF/CRLF warnings only)
```

UI readability freeze artifact `output/qa/incident_20260921/ui_readability/freeze_final_v2/summary.json` 為 `passed`，SHA-256 為 `7E4725B8BF4136FC254FB0D7F7CB6E40B540899C32D801C734F61424CB0C53EE`（2026-09-21 21:32:11 -07:00）；`scaling_final/summary.json` SHA-256 為 `115AC29E5E1E6C425310972965F7BEE1F51E33268CD5EEDE2F93DC0A268DED12`（2026-09-21 21:25:31 -07:00）。all-pages focused route 為 122 passed／1 skipped，UpdateView 為 84，validator 為 25 passed／4 skipped，mypy 檢查 638 source files，changed Python py_compile passed。這些是 offscreen／focused evidence；全頁 loaded/error／極長真實資料未全部重演，native window／screen-reader 未測試。

## Freeze 後整合 QA

portfolio final freeze 後的 affected integration route 以最後版本執行：`135 passed／1 skipped`（含 stock research service、report／Journey、portfolio、navigation、workbench、theme、cross-page MainWindow、continuity 與 personalization integration）。mandatory UpdateView pytest 為 `84 passed`；`scripts/qa_validate_update_tab.py` 為 `25 passed／4 skipped`；full mypy 檢查 `638 source files` 無 issues；本輪所有變更 Python `py_compile` 通過；`git diff --check` 通過，僅保留 Git LF／CRLF line-ending warnings。QA 使用隔離 fixture／offscreen，未寫入正式 data root、SQLite、candidate formal boundary、scheduler、learning 或交易狀態。

## 尚未完成與禁止推論

- 本查核不代表全市場所有 source 在 9/21 都 fresh；institutional／credit／TDCC、fundamental PIT 與 broker coverage 仍依實際日期判讀。
- 不把 candidate DB、fixture、Paper、replay 或 current observation 當作 formal／natural／ML evidence。
- 不宣稱 V5 或 V6 完成；V5 readability 是 bounded engineering／QA，V6 personal maturity 仍待真實 evidence。
- 未執行正式 DB write、rebuild、scheduler rerun、backfill、learning update 或 transaction。
- final integration QA 已完成並通過；限制仍是全頁 loaded/error／極長真實資料未全部重演、native window／screen-reader 未測試，以及本輪不宣稱全資料 9/21 fresh 或 V5／V6 formal completion。

## 相關文件

- [完整操作手冊](../07_guides/APPLICATION_MANUAL.md)
- [Qt UI 功能文件](../02_features/UI_FEATURES_DOCUMENTATION.md)
- [專案快照](../00_core/PROJECT_SNAPSHOT.md)
- [Data freshness handoff](V4_DATA_FRESHNESS_HANDOFF.md)
