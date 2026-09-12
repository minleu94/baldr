# V4 每日自然證據運行閉環 QA Handoff（2026-09-12）

## 目的與範圍

本次收斂 V4 每日自然證據的 scheduler、forward outcome、progress receipt、來源／cohort identity、Paper ledger、跨日測試與 QA handoff。驗證以唯讀讀回、隔離 dry-run 與測試 fixture 為主；不做歷史回填、不製造 synthetic observation、不寫入 formal raw data，也不執行 broker order。

工作基準為 `a657ed9d feat: unify investment decision presentation`。本 worktree 目前仍為 detached HEAD；共享 Git common dir 的 branch／commit 由主線 owner 處理，本文件只記錄可交接的程式與驗證結果。

## 已完成的程式與文件變更

- 新增 `app_module/evidence_progress_receipt_service.py`：建立 `scheduled-evidence-progress.v1` read-model，使用 immutable run、atomic latest pointer 與同 `run_id` idempotency；投影 daily／weekly／maturity、blocker、warning、next action 與 no-new-data alert。
- `scheduled_forward_outcome_service.py`：
  - health 採用明確 V4 `universe policy + snapshot` identity gate，避免 legacy incomplete rows 佔滿 bounded scan 造成新 cohort 被漏掉。
  - progress receipt 失敗時 fail-closed；calendar 只讀當日 freshness receipt，stale／unknown 不得被當成已關市。
  - forward receipt 保存 calendar observation 與 progress readback；保留 `--confirm --allow-production-db-confirm` 的正式資料安全閘門。
- `scheduled_evidence_status_service.py` 與 `scheduled_evidence_status_view.py`：將 progress 狀態、連續無新資料、calendar expected reason、blocker／warning／next action 與 receipt path 顯示於 read-only dashboard。
- `scripts/inspect_scheduled_task_registration.py`：納入 `baldr-forward-outcomes-daily`，對 live Task Scheduler 做 query-only registration／action／schedule／wrapper 檢查。
- `scripts/scheduled/run_scheduled_forward_outcomes.py`：Windows stdout／stderr UTF-8 fallback，避免 dry-run 的 Unicode 狀態輸出造成假失敗。
- `scripts/scheduled/README.md`、`docs/07_guides/APPLICATION_MANUAL.md`：同步 progress receipt、idempotency、no-new alert、calendar safety、未知日曆與排錯說明。

## 驗證結果

### 程式與測試

最終驗證命令與結果：

- 相關測試套件：`122 passed`。
- `mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`：`Success: no issues found in 595 source files`。
- 變更 Python 檔案 `py_compile`：通過。
- `git diff --check`：通過；僅保留既有 CRLF warning，無 whitespace error。
- 量化防禦檢查：`check_financial_float_boundaries.py` 與 `check_look_ahead_bias.py` 均通過。

測試覆蓋 daily／weekly progress projection、連續 no-new alert、週末與 official calendar closed suppression、weekday calendar unknown、receipt idempotency、legacy identity gate、bounded scan starvation、stale calendar receipt、Paper readiness、cross-day contract 與 evidence review dashboard。

### Live scheduler registration

使用 live Task Scheduler 的 query-only inspector：

- `task_count=19`、`available_count=19`、`missing_or_unavailable_count=0`。
- `configuration_ready=true`。
- `baldr-forward-outcomes-daily` 已存在，排程為每日 `05:40`；action、schedule、wrapper 均符合預期。
- live action 指向 saved checkout `C:\Projects\PythonProjects\technical_analysis`，不是本 worktree；因此本 worktree 沒有修改 live Scheduler。

### 隔離 dry-run 與真實 forward readback

隔離輸出根目錄的 real-D dry-run 通過，沒有 evidence write：

- `status=dry_run`、`health=waiting_for_natural_maturity`。
- `events_scanned=6`、`skipped=215`、decision dates 為 `2026-09-10`、`2026-09-11`。
- horizon 5／10／20／60 均為 `ready=0`、`pending=6`、`missing=0`。
- weekend calendar observation 為 `weekend_closed`，progress 為 `suppressed_non_trading_day`。
- warning 保留 `no_maturity_calendar_observation` 與 legacy incomplete identity skip；沒有把 weekend 誤判為缺資料。

正式 D output 的唯讀讀回仍反映尚未自然成熟的狀態：6 個 V4 gated events、215 個 incomplete rows skipped、2 個 decision dates，5／10／20／60 horizon 均為 pending 6。現有 production receipt 是前一輪排程產物，需下一次自然排程重新產生 progress receipt；本次沒有強行重跑 production confirm。

### Paper ledger 與 benchmark readback

唯讀讀回未修改 Paper state：

- snapshot 31 筆，日期 `2026-07-12` 至 `2026-09-11`；最新 total value `479826.11`、cash `161526.11`。
- benchmark 21 筆，最新只到 `2026-08-28`，因此 weekly evidence 目前 `not_computable`，原因是至少需要兩筆可對齊 benchmark。
- cost ledger 8 筆：6 filled、1 partially filled、1 rejected；仍維持 research-only、broker execution disabled。
- cost total `1373.89`，其中 cash settlement cost `823.89`、slippage attribution `550.00`；cash 與最新 snapshot 對得上。
- 尚無可供外部 fill verification 的真實 fills CSV；因此不將 partial／rejected 狀態改寫成成功成交，也不補造 benchmark 或 fill。

## 殘留阻塞與交接責任

以下不是本次程式驗證失敗，而是必須由自然時間或外部來源／部署條件解除的事項：

1. V4 forward horizon 尚未自然成熟；不得以改日期、回填或 synthetic observation 加速。下一個自然排程日才能推進新的 maturity receipt。
2. Paper benchmark 在 `2026-08-28` 後沒有新資料，造成 weekly evidence boundary mismatch；需要授權且可追溯的 benchmark source refresh。
3. 外部 fills CSV 不在目前可讀範圍，Paper reconciliation 只能保留 internal ledger 的 filled／partial／rejected 狀態。
4. live Scheduler 已指向 saved checkout；主線合併／部署後須由 saved checkout owner 再確認 action 與 receipt freshness。另有 production config log 路徑的 ACL warning，但 console fallback 不影響本次 dry-run 結果。
5. 本 worktree 是 detached HEAD；依共享 worktree 協作約定，不在此處強行建立 branch 或 commit。主線 owner 應審閱本 diff、stage、commit，並在 saved checkout 進行下一次自然排程驗證。

## 下一步

- 主線 owner review 本 diff 後提交變更。
- 下一個自然排程執行後，確認 production forward receipt 與 progress latest status 都有新的 checked-at、decision dates 與 maturity projection。
- 外部 benchmark／fills source 可用後，再重跑 Paper weekly evidence 與 reconciliation；在此之前維持 degraded／not-computable，不放寬安全閘門。

