# Formal Scheduler Current Readiness Audit — 2026-09-20

本 QA 是一次 current-only、唯讀的正式 scheduler readiness 檢查。觀測時間為 `2026-09-20T15:05:49+08:00`，`decision_date` 取同一個實際 Asia/Taipei aware clock 日期 `2026-09-20`。它不代表下一個交易日已通過，也不改判 2026-09-18 的歷史 decision。

## 執行邊界

檢查直接呼叫 `data_module.recommendation_calibration_source_contract.inspect_source_contract()`（`data_module/recommendation_calibration_source_contract.py:1913`），輸入為正式 `D:\Min\Python\Project\FA_Data\sqlite\twstock.db`、正確的 `D:\Min\Python\Project\FA_Data_Shadow` source artifact root、正式 caller 使用的兩個 authorized output roots，以及 7 個 eligible symbols：`1103, 1436, 1437, 1438, 1529, 1560, 1569`。沒有呼叫 `write_source_contract()`、learning CLI 或 scheduler；沒有寫入 formal DB、formal output、capture、pointer 或 receipt。

compact 原始結果保存在 [current readiness JSON](../../output/qa/formal_scheduler_readiness_20260919/current_readiness.json)，可重現 probe 在 [readiness probe](../../output/qa/formal_scheduler_readiness_20260919/readiness_probe.py)。第一次普通 sandbox `mode=ro` 開啟 3.6 GB SQLite 回報 `OperationalError: unable to open database file`；同一 `mode=ro`、未使用 immutable／nolock、沒有 writer 的唯讀權限檢查成功讀取 `HistoricalRawSnapshot`。這是執行環境 ACL 差異，不是以 bypass 取得資料。

## 呼叫鏈與已讀證據

正式路徑為：

`scripts/scheduled/run_recommendation_calibration_learning.cmd` → `scripts/scheduled/run_daily_recommendation_learning_pipeline.py` → `scripts/scheduled/run_daily_data_update_quick.py` → `scripts/scheduled/run_daily_recommendation_learning.py`。

BankTaiwan lane 由 `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.cmd` → `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py` 啟動；該 runner 的 source policy（`scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py:584-598`）明確標示 `technical_refresh_in_this_task=false`，只讀取既有 quick publication。daily learning 的 source artifact root 接線在 `scripts/scheduled/run_daily_recommendation_learning.py:1336-1337,1525-1537`，live capture gate 在 `scripts/scheduled/run_daily_recommendation_learning.py:2668-2733`。

quick runner 已有計算 witness reuse 與 publication：`scripts/scheduled/run_daily_data_update_quick.py:804-822` 讀取 verified witness，`scripts/scheduled/run_daily_data_update_quick.py:927-945` 發布 technical receipt。正式 quick 最新 receipt 是：

`D:\Min\Python\Project\FA_Data\output\scheduled\technical_indicator_publication\2026-09-18\1a73fe8c06df13f9\receipt.json`

它的 `run_id=20260919-2092`、`available_at=2026-09-19T04:30:45-07:00`、source window 為 `2026-09-15..2026-09-18`、technical step `passed`、computation evidence `verified`；technical output 為 7,826 rows、1,975 symbols，7 個 eligible symbols 均存在。receipt file SHA256 為 `05ed2faa0f8a19e5efaaebfc133a9cda53fc63e6c92feb4134e5699fa3a1ff57`。

## Current readiness 結果

source receipts 的日期、時間 cutoff、symbol coverage、receipt lineage 與 7-row prospective feature snapshot 均可讀且通過：`missing_source_symbols=[]`、`missing_technical_symbols=[]`、`technical_source_receipt_lineage_verified=true`、`prospective_feature_snapshot_verified=true`。

目前真正未通過的是 technical output value binding。已發布 receipt 宣告的 technical output 是：

| 項目 | 已發布 receipt | current formal DB 唯讀 snapshot |
| --- | --- | --- |
| source DB | `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` | 相同 |
| 日期範圍 | 2026-09-15 至 2026-09-18 | 相同 |
| rows | 7,826 | 7,826 |
| covered symbols | 1,975，7 個目標均存在 | 1,975，7 個目標均存在 |
| content hash | `sha256:da98d5962839b16e450ed31aacb969a003fc47b7e58e386a1556a62c6481879d` | `sha256:271979ddf865e383fa528e3259472f5868ee82fd82da00c21d39240d852e07f7` |
| rows hash | `sha256:2f67730ee109f7a586111e624e88b328e4ba08b6829feb465579b436c4c40f9e` | `sha256:830cdf5af003c43d07b25ce32425cd69b193070c8fee23db6731e5d246b94620` |

因此 current proof 的 `technical_output_value_binding_verified=false`、`technical.prospective_available=false`，price-up lane 的 prospective blocker 仍是 `technical_prospective_source_not_ready`。formal technical contract 的 `verified=false`（`recommendation_source_contract_missing`）是另一個 formal lane 狀態；corporate adjustment custody 的 prospective proof 為 true，但 formal verified 仍是 false，不能把兩者混成同一個 technical source blocker。

正式 DB 的檔案 mtime 為 `2026-09-19T05:53:28-07:00`，晚於 publication `available_at`；這只能證明 DB 檔案後來被寫過，不能單獨證明 technical table 是重算、哪些 rows 改變，或是哪個 writer 造成 hash drift。下一個 bounded audit 才會沿已知 quick/background status 與 writer path 追查，不在本 QA 內重發布或重算。

## 結論與邊界

本次 proof 證明 source receipt 與 7-symbol coverage 已可被正式 read-only contract reader 找到，也證明目前不能把該 receipt 當成可供自然 capture 的 current technical binding。必須先釐清 receipt 後的 technical output hash drift，再由實際 scheduler 以當下 checked clock 重新建立 source contract；本 QA 不預測下一交易日結果、不回填 2026-09-18、不產生 natural credit。

`f48908a1` 的背景 publication 修正仍是 `ui_qt/views/update_view.py:4049` 的 UI background route；它不能被描述成已改動正式 scheduler。正式 scheduler 是否能在下一個實際交易日完成 current binding，仍以新的 quick receipt、source contract 與 live capture artifact 為準。
