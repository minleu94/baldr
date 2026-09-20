# TPEX 單日 pre-captured raw 補入 QA（2026-09-18）

本輪在既有 `scripts/backfill_tpex_daily_prices.py` 增加受控的單日 official afterTrading raw 模式，保留原有 `--source-json`／OpenAPI 舊模式。新模式要求明確的 `--source-raw`、同源 `--capture-metadata`、日期、`--required-symbol 1569`、data/output/db/backup roots；預設為 dry-run。它只接受 HTTPS `www.tpex.org.tw` 的 `/www/zh-tw/afterTrading/otc`，驗證 production 使用的西元日期參數、response hash／bytes、capture clock、payload source date、目標行情 table 與 1569。

provenance、既有 CSV 與 DB 內容衝突會先檢查；custody 與 CSV 實際落地仍逐一使用 create-only 驗證，沒有跨檔 transaction 宣稱。apply 會以 official custody helper 保存 raw 與 receipt（`historical_backfill_claimed=true`，因此 `historical_pit_status=not_proven_by_after_close_capture`，`formal_source_contract_eligible=false`），SQLite 先保留 backup；完成後再以 query-only readback 核對所有 normalized rows 及 1569 的 OHLC／成交股數。這是晚取得的歷史補入工具，不會回填舊 failed receipt、啟動 scheduler，或授予 natural／calibration credit。

## 驗收結果

- `.\.venv\Scripts\python.exe -m pytest tests\test_tpex_daily_price_backfill_cli.py -q -o addopts=`：**10 passed，exit 0**。涵蓋舊 CLI 相容、dry-run 無寫入、official provenance、日期 mismatch、CSV／DB conflict、multiple tables 選取、ambiguous quote tables 拒絕、apply 後 receipt／CSV／DB 與 readback。
- `.\.venv\Scripts\python.exe -m py_compile scripts\backfill_tpex_daily_prices.py tests\test_tpex_daily_price_backfill_cli.py`：**exit 0**。
- `.\.venv\Scripts\python.exe -m mypy --explicit-package-bases scripts\backfill_tpex_daily_prices.py`：**Success: no issues found in 1 source file，exit 0**。
- `git diff --check -- scripts/backfill_tpex_daily_prices.py tests/test_tpex_daily_price_backfill_cli.py docs/07_guides/APPLICATION_MANUAL.md docs/06_qa/TPEX_SINGLE_DAY_PRECAPTURED_BACKFILL_2026_09_18.md`：**exit 0**；Git 僅提示既有 Windows CRLF 轉換警告。

本輪 insert-only focused 驗收另執行 `pytest tests/test_tpex_daily_price_backfill.py tests/test_tpex_daily_price_backfill_cli.py -q -o addopts=`，**18 passed，exit 0**；`data_module/tpex_daily_price_backfill.py`、`scripts/backfill_tpex_daily_prices.py` 與兩份測試檔 `py_compile` 為 **exit 0**；`mypy --explicit-package-bases data_module/tpex_daily_price_backfill.py scripts/backfill_tpex_daily_prices.py` 為 **Success: no issues found in 2 source files，exit 0**。原始輸出保存在 `output/qa/tpex_source_acquisition_20260918/official_cli_isolated_20260919/insert_only_focused_pytest.txt`、`insert_only_pycompile.txt` 與 `insert_only_mypy.txt`。

## 真實 custody 隔離 dry-run

使用既有 2026-09-17 official TPEX custody raw 作 parser／contract compatibility check；沒有把它當成 2026-09-18 source，也沒有寫入正式資料。原始來源為：

`D:\Min\Python\Project\FA_Data\output\scheduled\daily_price_source_custody\tpex\20260917\63be241cd5de8b53\raw_response.bin`

- raw bytes：146161
- raw hash：`sha256:63be241cd5de8b539a31b4f8653dbb252e07d3ce142766dadf761fbfd2e0096f`
- receipt `captured_at`：`2026-09-17T11:20:13.204722+00:00`（原值保留）
- normalized rows：867
- strict diagnostics：147，其中 `invalid_stock_code=126`（非四碼股票列／特殊證券）與 `invalid_price=21`（停牌或無有效收盤價）
- CLI dry-run：exit 0，`ready_for_apply=true`；隔離 DB／output 下沒有正式 custody、CSV 或 DB 寫入

CLI 原始輸出保存在 [real_9_17_dry_run.txt](../../output/qa/tpex_precaptured_contract_20260918/real_9_17_dry_run.txt)，metadata 由同一份既有 receipt 轉換，沒有手抄 stdout。9/17 raw 僅作 parser／contract compatibility check，不能替代 9/18，也沒有產生 natural credit。

## 2026-09-18 official raw 正式補入

2026-09-18 官方 afterTrading/otc response 由唯讀 probe 保存於 `output/qa/tpex_source_acquisition_20260918/heartbeat_20260919T071913Z_after_trading_otc/response.body`，其 download metadata 與 CLI capture sidecar 為同目錄的 `download_metadata.json` 與 `capture_metadata_for_backfill.json`。HTTP 200 response 自帶 `20260918`，raw 為 146,419 bytes、SHA-256 `sha256:2eae9b5185bfde35ddb63ed6ed4d331f3a97a195229394a693db54ddc9739e62`，完整 body 讀取完成時間為 `2026-09-19T07:20:33.071218+00:00`；1569 的官方列為收盤 `55.50`、成交股數 `5,164,000`、成交金額 `281,868,400`。capture metadata 保留該實際時間，沒有把晚取得資料追認為 9/18 decision-time 或 natural PIT evidence。

正式 D apply 前的唯讀 snapshot 顯示 `daily_prices` 在 20260918 已有 1,090 rows，日期 rows hash 為 `sha256:9eee2427f1b8f4358f89bcac76950935895dcde71bbffb0c87398fa35f70828e`，1569、TPEX CSV 與 custody 均缺漏；normalized candidate 為 868 rows，145 個 strict diagnostics（`invalid_stock_code=125`、`invalid_price=20`），與既有 rows overlap／content conflict 為 0。

正式 apply 使用 pre-captured official raw，exit 0，`inserted_count=868`，並完成 query-only readback。raw mode 使用 `insert_only=True`，競態下遇到既有 key 只保留既有資料；legacy apply 的預設更新行為維持不變。

正式結果如下：9/18 日期 rows 為 1,958（增量 868），1569 為開 `52.0`／高 `57.0`／低 `52.0`／收 `55.5`／成交股數 `5,164,000`／成交筆數 `2,537`／成交金額 `281,868,400`；CSV `D:\Min\Python\Project\FA_Data\daily_price_tpex\20260918.csv` 有 868 rows，SHA-256 `sha256:0885957af1ce0039858dc4293e858b7aab8a2c1bc2618b4f14ee510eb3211664`；custody raw／receipt 位於 `D:\Min\Python\Project\FA_Data\output\scheduled\daily_price_source_custody\tpex\20260918\2eae9b5185bfde35`，receipt raw hash 一致；DB backup 為 `D:\Min\Python\Project\FA_Data\meta_data\backup\twstock_tpex_daily_price_backfill_20260919_003431.db`（SHA-256 `sha256:a5c57014253738a826a155071a30667338c7a7807ae9a0785cf33f29b3e2a99f`）。custody receipt 仍標示 `historical_pit_status=not_proven_by_after_close_capture`、`formal_source_contract_eligible=false`，因此本次補入只恢復市場資料完整性，不增加 natural、calibration、promotion 或 broker credit。

正式 apply 前後與 readback 摘要保存在 [before_state.json](../../output/qa/tpex_source_acquisition_20260918/formal_apply_20260919/before_state.json)、[after_state.json](../../output/qa/tpex_source_acquisition_20260918/formal_apply_20260919/after_state.json)；完整 apply stdout 在 [formal_apply.txt](../../output/qa/tpex_source_acquisition_20260918/formal_apply_20260919/formal_apply.txt)。
