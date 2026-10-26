# Scheduled Evidence 受控 Replay 隔離 QA — 2026-10-25

## 結果

用正式推薦輸出作唯讀來源、working-copy DB 作市場資料、scratch 作全部輸出，完成 2026-10-25 controlled scheduled dry-run。正式快照身份綁定成功：result ID `rec_bb92ea25e2194e7885498ec5cb973c7d`，source `latest_status.json` SHA-256 `ca6053a08dcd8f04acf94456d1fbcad634a636a13808b36e7a6084b94cc41a98`，artifact payload hash `sha256:20015622f2c247602e4c621442d378f6b272848493e4d7873a92b5e9f43944dc`。執行後重讀的來源 status SHA 相同。

產物在 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\weekly-review-working-copy-20261025\r2`；正式輸出根未作為輸出目錄。終態 `degraded`、pipeline exit `0`、0 errors、20 warnings（14 個 unique、16 個 actionable occurrences）、scheduler readiness `not_ready`。乾跑檢視 1,695 events、inserted 0；outcomes attempted／created／updated 均為 0。`dry_run=true`、`confirm=false`、`writes_evidence_db=false`、`production_scheduler_allowed=false`。

主要缺口：

- blocking gaps：`watchlist_trigger_not_ready`、`risk_prompt_not_ready`。Watchlist pool 為空；Risk Prompt 使用 degraded 的 market breadth、relative strength/liquidity、sector rotation inputs。
- freshness 為 `degraded`；市場 breadth、relative strength/liquidity、sector rotation 以 2026-10-22 fallback，並帶 stale cadence／skipped rows 警告。
- forward summary 5 組中 4 組 `INSUFFICIENT_SAMPLE`、1 組 `DEGRADED`；沒有新 outcome 計算。
- 5 項 fundamental source qualification gaps：monthly revenues、quarterly statements、current monthly observations、current statement observations、statement availability map。
- Paper research snapshot/status 缺件，故本輪不提供 Paper research capture。

機器狀態與 report：

- `r2\status\latest_status.json` SHA-256 `893cdb5ede0b8660688da7fb4693ba20634337cec4216ff2c7aab4e92e2fb7a0`
- `r2\status\reports\20261025_20261025_172453_422196_evidence_pipeline_dry_run.md` SHA-256 `e92871f4b545a4913ed2f275bcecdc5e7baf24513be7e219b4b25f1edc008c55`
- `r2\status\receipts\evidence-20261025T172453422196-2c4d5f5fb4e440eea5ea5990e1f46676.json` SHA-256 `1770d7cf0fafb57127b41af36eec035ee24d134ea2a4f761c635228e97501b47`

## 修正與測試

首輪受控 replay 將正式推薦綁定成功，但在 event hash canonical JSON 因巢狀 metadata 含 `date` 而停止。`EvidenceEventService` 現將 `date`／`datetime` 穩定轉成 ISO 字串，有限 `Decimal` 保留為十進位字串，並遞迴處理 list／tuple／dict；未知型別仍由標準 JSON encoder 拒絕。第二輪使用短 scratch path 避開 Windows 長路徑限制後，完整 scheduled wrapper 成功產出上述 `degraded` 終態。

受控驗證執行環境在啟動前有 25.55 GiB 可用記憶體；QA child 使用 Windows Job Object、8 GiB Job 記憶體上限、12 process 上限、單一工作區 lock。Job 自然結束，無強制清理。相關測試為 **64 passed、20 deselected**；deselected 包含本機 sandbox 不允許的 exit-effectiveness hard-link 案例，因此該批行為未由此 QA 覆蓋。

## 驗證記錄

- 修改範圍測試：64 passed、20 deselected。
- 修改的 7 個 Python 檔案 `py_compile`：通過。
- 全域 mypy：`Success: no issues found in 1145 source files`。
- Feature Map JSON 解析：通過；`git diff --check`：通過。
- `document_control.py check`：未通過全域文件檢查。回報包含其他既有 workspace 的代表測試未命中 change pattern、PROJECT_SNAPSHOT／QA index 的舊 QA 錨點失效，以及多個 `output` junction 連結因 Windows sandbox `Access denied` 無法檢查。未發現指向本次新增 QA 文件的錯誤；這次檢查無法據此宣稱整體文件連結完整。

## Gate 界線

這份收據證明受控 scheduled dry-run 能綁定正式推薦，同時把 Evidence Pipeline 產物導向隔離 scratch。它是一次性 controlled replay，不是自然排程、weekly human review、Evidence Review dashboard 驗收、backup／rollback／recovery 演練或 Gate 2 history。沒有新增正式 weekly sidecar、Owner／reviewer 決定、source acceptance 或 Gate credit；source qualification、freshness、Paper input 與 dashboard 缺口仍待處理。

## Follow-up：Paper 唯讀輸入根分離

回查發現上一輪 controlled replay 把 Paper state/status 指向空 scratch operation root，因此 `Paper research snapshot/status missing` 只證明該隔離目錄沒有資料，不能推論正式帳戶輸入也缺件。wrapper 現新增 `--paper-evidence-source-root`：指定時由子流程唯讀讀取該根下的 Paper state/status；輸出根仍是 scratch，且來源根不得與 scratch 重疊。未指定時，controlled receipt 明確標示 `not_configured_for_controlled_replay`，不再把空 scratch 傳給 importer。這不代表正式 Paper source 已綁定，也不降低任何 readiness／Gate 條件。

- 新增 Paper source/scratch 分離、未設定 disclosure、來源根重疊拒絕、舊 operation root 保護及 child CLI source path 測試：**5 passed**。
- 修改的兩個 CLI 與兩個測試檔 `py_compile`：通過；全域 mypy：`Success: no issues found in 1145 source files`。
- 完整 wrapper＋CLI 回歸執行：**31 passed、31 failed**。失敗可見 Windows sandbox pytest temp 下 terminal receipt 路徑回 `FileNotFoundError`，及 exit-effectiveness hard-link 案例回 `PermissionError [WinError 5]`；因此不將整套回歸記為通過。5 個新增／關聯 focused tests 在同一受控 Job 下全部通過。

## Follow-up：Evidence blocker 可讀摘要

Evidence Review 的「每日排程證據狀態」頁新增「主要缺口與下一步」卡。已知的 watchlist、risk prompt、portfolio alert、saved recommendation、Why Not、liquidity 與 forward dashboard blockers 會顯示對應檢查方向；未知 blocker 保留原始診斷碼並標明未登錄處理說明。沒有 blocker 時也明示「不等於 Evidence／Gate 已通過」，完整 machine diagnostics 繼續留在下方明細。這是可讀性改善，不改 quality、readiness 或 gate predicate。

- Qt offscreen UI focused tests：**2 passed**，覆蓋已知 blocker 摘要、安全下一步與原始診斷保留。
- 此處未執行原生 GUI 重啟、不同螢幕尺寸視覺檢視或 Owner UAT；卡片尚需在實際 Evidence Review 頁確認版面。
