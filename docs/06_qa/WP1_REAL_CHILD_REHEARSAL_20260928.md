# WP1 隔離真 child rehearsal：休市與歷史配對判定（2026-09-28）

## 結論

2026-09-28 的正式日曆快取標示非交易日。Bank Taiwan 隔離 wrapper 的 `--dry-run` 以 exit 0 正常結束，輸出 `twse_holiday_schedule_cache_closed`、`not_applicable_non_trading_day`、`child_invocation=not_run`。本次沒有建立 QA 工作 DB、沒有啟動 child、沒有執行 updater、排程器、正式 writer 或 global pointer；因此不能把這次結果稱為真 child rehearsal 通過。

另對 2026-09-24 僅執行唯讀 dry-run，結果因目前 status 身分不是同日 pair 而封鎖：Shadow 的 `recommendation_snapshot/latest_status.json` 是 2026-09-27，當日 pipeline latest status 是 2026-09-28；而 2026-09-24 的 terminal pipeline receipt 為 `failed`，blockers 包含 `technical_source_refresh_failed` 與 `recommendation_learning_failed`。雖然 9/24 snapshot log 記載 `status=passed` 與 result id `rec_5537cbabba654347af2c752073d7ecf2`，它不能代替 loader 要求的 latest snapshot + 同日成功 pipeline 配對。沒有重建或覆寫任何歷史 status。

## 執行證據

| 項目 | 結果 |
| --- | --- |
| 9/28 closed-day dry-run | exit 0；`is_official_trading_day=false`；`child_invocation=not_run` |
| 9/24 historical dry-run | exit 0；`is_official_trading_day=true`，但 snapshot `blocked`，原因 `recommendation_snapshot_status_decision_date_mismatch`；child 未執行 |
| 9/24 最新 Shadow snapshot status | passed，decision date 2026-09-27，result `rec_c0b327cdcd8343d9aa598cba4fd43eb7` |
| 9/24 最新 Shadow learning pipeline status | failed，decision date 2026-09-28；未形成 9/24 成功 pair |
| 9/24 歷史 pipeline terminal receipt | failed；snapshot 子步驟通過，但 `data_update_quick` 與 `recommendation_learning` 失敗 |
| 寫入邊界 | 只寫本目錄下的 dry-run logs/receipt 與本報告；無 QA DB copy，正式 DB、global pointer、正式輸出未寫入 |

9/28 dry-run 的原始命令與完整 payload、日曆快取與來源 snapshot 雜湊，記錄於 [preflight_receipt_2026-09-28_v2.json](../../output/qa/wp1-real-20260928-01/preflight_receipt_2026-09-28_v2.json)。9/24 dry-run 及 latest-status/歷史 receipt 證據記錄於 [historical_probe_receipt_2026-09-24_v2.json](../../output/qa/wp1-real-20260928-01/historical_probe_receipt_2026-09-24_v2.json)。對應 stdout JSON logs 分別為 [9/28 dry-run](../../output/qa/wp1-real-20260928-01/dry_run_2026-09-28.log) 與 [9/24 probe](../../output/qa/wp1-real-20260928-01/dry_run_2026-09-24_historical_probe_attempt2.log)。

V1 preflight receipt 保留作歷史，不改寫；其中 `snapshot_source_receipt_sha256` 實際填的是 snapshot DB hash，不是 metadata receipt 檔案 hash。V2 receipt 分列 snapshot DB SHA 與 `snapshot_receipt.json` 檔案 SHA，已消除欄名歧義。

## 實際程式門檻

`run_banktaiwan_recommendation_learning_daily.py` 的 `_official_calendar`（約第 119 行）先驗官方日曆；`_dry_run`（約第 1062 行）可顯示 gate 結果但不啟動 child。`load_same_day_snapshot`（約第 304 行）要求指定日期吻合目前 snapshot latest status，並繼續核對同一 output root 的 pipeline latest status、日期及 run identity。因而一份留存的每日 log 或舊 terminal receipt，不能單獨當成今天可重跑的 canonical pair。

`scripts/scheduled/run_scheduled_recommendation_snapshot.py` 的 parser（約第 796–818 行）沒有歷史 decision-date 參數；`main`（約第 994–995 行）以系統排程時鐘決定日期。不得 monkeypatch 時鐘或改寫 latest status，把舊 9/24 資料包裝成當日正式 scheduler output。每日 pipeline 同樣以 Asia/Taipei 系統日期建立 run identity（`run_daily_recommendation_learning_pipeline.py` 約第 824–847 行）。

## 下一個合法 rehearsal

等待官方快取確認的下一個正常交易日，先在全新 QA root 執行 wrapper dry-run。只有日曆判定開市、同一 shadow output root 已有當日 snapshot 與成功 pipeline latest status、canonical result/cohort/clock 身分完整且來源日期如實標示時，才將正式來源唯讀複製到新的 QA working DB，再執行 wrapper child 及同日冪等重跑。每次 run 使用新目錄，先後比對正式 source DB 與其 WAL/SHM 身分及 bytes，不呼叫 updater 或 Task Scheduler。

若當日行情仍止於 2026-09-24，所有推薦與模型結果須保留該資料截止日；不得稱作 9/28 行情更新。20 個交易日 outcome 尚未成熟時保留 `pending`/`unknown`，不可把未到期標籤當失敗。若官方日曆快取在下次執行前過期，需先依獲准流程取得/驗證新官方快取；本次沒有刷新日曆。

本次僅驗證 closed-day gate 與歷史配對拒絕行為。它沒有驗證開市日 child 執行、資料更新、結果持久化、自然 outcome 成熟或 broker 行為。