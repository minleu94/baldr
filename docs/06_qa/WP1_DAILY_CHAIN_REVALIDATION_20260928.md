# WP1 每日資料鏈重驗（2026-09-28）

## 範圍與結果

基準 HEAD 為 `29ff35b4a17fa3fc270aef6168ab70eaf48eeb1b`。本次只修改 Bank Taiwan 每日 learning wrapper 與其精準測試，新增本報告；未執行正式 updater、排程器或 child，也未讀取正式行情 rows。

Wrapper 現在只接受本次 child stdout 中符合 CLI v3 schema 的終態 JSON，並以 bounded、no-follow 方式讀取其 run-local receipt，核對 run ID、台北決策日、receipt 路徑、終態、成本情境與摘要欄位。缺 stdout、錯誤 run status、stdout/receipt 不一致或不安全路徑都 fail closed；不再以 lane 的舊 `latest_status.json` 補作本次成功。相同失敗 run 可建立新 attempt；已驗證的成功 terminal 仍沿用既有冪等行為。

測試覆蓋 `returncode=0` 但 child 明示訓練失敗、stdout 與 receipt 不一致、缺 stdout 且 lane 留有舊成功 status、同日 retry attempt 遞增，以及 closed-day 不讀 snapshot／不啟 child。另有相鄰 learning loop、outcome CLI、Stage C outcome 與官方日曆路由。

- Wrapper focused：20 passed、2 skipped，exit 0。
- 相鄰 WP1 路由：69 passed、1 skipped，exit 0。
- Targeted mypy、兩檔 py_compile 與 `git diff --check`：exit 0。

完整命令、環境、程式雜湊與閉市 dry-run 的 DB 前後 metadata 見 [final_revalidation_receipt.json](../../output/qa/personal_daily_product_20260928/wp1_child_terminal_contract_01/final_revalidation_receipt.json)。程式與測試修改前雜湊分別為 `8fe0cc43882d1cfe5846843921919a988fb58066d161d3cb5e0bb1e619171703` 及 `5dd99f8ef98ce4139c81c804b42baf30e4371e7e2f302cd779af7981e1a94645`；修改後 SHA 由該收據固定。

## 2026-09-28 隔離 dry-run

新 QA root 為 `output/qa/personal_daily_product_20260928/wp1_child_terminal_contract_01/closed_day_dryrun_01/`。原始收據 SHA-256 `1b8a7298c9686ba268dda4fb7fa748882498c89e8fd9c878d55655b5fd7b715f`，plan SHA-256 `9e6ace3c387d63ea3de4eab0e34d89410e164ae1c3bfd91b6a2e3ac0e8b8aa13`。Asia/Taipei 官方日曆回報非交易日，原因 `twse_holiday_schedule_cache_closed`；結果為 `dry_run`、snapshot `not_applicable_non_trading_day`、child `not_run`。這只是閉市 gate 驗證，不能當作正常交易日 child 或整條日常鏈通過。

正式來源 `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` 及 WAL/SHM 的存在、大小、建立/寫入時間在 dry-run 前後相同：主 DB 3,827,728,384 bytes；WAL 0 bytes；SHM 32,768 bytes；journal 不存在。此處記錄的是 metadata 對照，未計算整個 3.8 GB DB 的 SHA。

## 剩餘外部條件

下一個官方開市日仍需先具備同日 canonical recommendation snapshot 與成功 pipeline status；二者需有相符的 result/cohort/date/clock identity，並經保存結果 readback。只有這個 pair 可用後，才可在隔離 root 驗證真 child 終態 receipt、canonical readback 與同日重跑冪等。既有 2026-09-24 historical probe 已記錄 snapshot/pipeline 身分不相符與 pipeline failed，詳見 [歷史 rehearsal](WP1_REAL_CHILD_REHEARSAL_20260928.md)；舊 receipt 未改寫。

本次未執行自然 scheduler，也未得到正常開市日的 fresh pair；未驗證自然 20-session outcome 成熟。Outcome 路由的測試通過只證明程式語義，不代表實際樣本已成熟或產生正式績效。

## 2026-09-28 終態重用與 fingerprint follow-up

此 follow-up 以本文件上一版的 child terminal-readback 工作樹為起點（不是乾淨 HEAD）：wrapper 起始 SHA-256 `8a91c268068aaf6f6b57fd1170ad8f5da768b1a4efbd16eaf1aa8c83aa1af2cc`、operational test 起始 SHA-256 `60c756566b1d3e75c51a8b49f7ca94eb4e93b8ca424898f8499397a62b07e77a`。終版 wrapper SHA-256 為 `d642653c4772c1a62f4e81de18ae1be29a4533e17a048b0d28816f2c1ca9a0a8`，test SHA-256 為 `4958223178f9cb91a56390a765bba44cbe58982bd72ffc48af876971018c7d0b`。

本次調整讓 child `failed_*` 與未知 run status 在任何 closed-day capture skip 分類之前先判定；child 宣稱官方休市 skip，只有 wrapper 同一日曆判定也為非交易日才可能歸類為 closed-day skip。正式 wrapper 在非交易日原本不會啟動 child，因此開市 wrapper 下的 child closed-day skip 現為不一致依賴失敗，不會被重用成成功終態。

Input fingerprint 升至 v3，綁定 `history_start_date`、`max_decision_dates`、選日策略與固定成本，並包含本次官方日曆日期、判定、reason、已驗 annual/temporary cache evidence 的穩定身份及目標日期 cache candidate 的 lstat marker。只排除每次重驗才改變的 `validated_at` 類觀測欄；cache response hash 與 capture 時間仍保留。對同樣的 snapshot，改變訓練範圍、上限或官方 cache identity 會建立新 attempt，不沿用舊 terminal。

Terminal reuse 現在先以 8 MiB 上限、no-follow reader 讀 latest status，再要求它指向同日期、同 run ID 的 runs-root receipt；receipt 以 16 MiB 上限 no-follow 讀回，核實 latest 所存 raw SHA-256，並比較終態 payload 的完整欄位。tamper、缺欄、超限或 unsafe read 都不重用，轉為新 attempt。只在 latest projection 存 `terminal_receipt_sha256`；不可變 run receipt 本身不做自我雜湊。這是 wrapper 終態／冪等控制，不證明 child 以外的整條每日產品鏈已自然通過。

本輪隔離驗證路由 `tests/test_banktaiwan_recommendation_learning_operational.py` + `tests/test_official_trading_calendar.py` 得到 38 passed、4 skipped、exit 0；定向 mypy 1 source、兩檔 `py_compile` 與兩檔 `git diff --check` 均 exit 0。測試加入 failed child 與 closed-day skip 混合負例、三種 replay/calendar fingerprint 變化、run receipt tamper、bounded reader 拒讀、oversize 與 symlink 條件控制。完整命令、PROFILE=test 隔離變數、log 與雜湊見 [follow-up 收據](../../output/qa/personal_daily_product_20260928/wp1_terminal_reuse_fingerprint_followup_01/receipt.json)（SHA-256 `d236c88ef03d3ac936396fd81ece5c48bc53fd70ea87f790454a861132965244`）；pytest log SHA-256 `2d688b06c299d8c314111fd6deaf684f7e6cd93b19e36a58259d5f4e2d012a44`。

這些均為隔離測試與靜態檢查；沒有打開正式 `D:` DB、沒有執行正式 child、updater 或 scheduler，也沒有宣稱 2026-09-28 休市日的 child 成功。下一個正常交易日的 fresh 同日 snapshot/pipeline pair 與自然排程仍待驗。
