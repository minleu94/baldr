# Decision Continuity Increment C QA 紀錄

> **歷史 QA 快照（2026-10-10）：** 本文記錄 2026-09-14～15 的受控 launcher、TPEX 取消與 MainWindow/readback 驗收；其中 `614 source files`、CLOSE／TPEX 結果與 runner 命令不代表目前資料、功能或缺陷狀態，也不是重跑授權。現況看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)、[QA 導覽](../06_qa/README.md) 與 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

日期：2026-09-14～2026-09-15
狀態：完成受控 launcher 的 Win32 process-tree 修正、TPEX 合作式取消與 MainWindow 一次 X 自動收尾驗證；已完成真實 production MainWindow 的 idle／busy 單次關閉與兩個獨立 child continuity readback。

## 範圍分層

### 元件範圍

- `ResearchStockContextDTO`、`StockResearchContextChanged`、`ResearchSessionStore` 的 typed result／stock／date／snapshot identity。
- `DecisionContinuityController` 對已知 snapshot id、snapshot hash、decision date 的衝突阻擋、同 request id 的 revision 衝突，以及未知 legacy identity 的唯讀限制。
- `WatchlistService` 與既有 `WatchlistRepository` 的明確 identity 綁定；不新增平行資料庫。
- `TaskWorker` 的 managed/live registry lifecycle：每次 `start()` 重新登記；start 失敗與未啟動 `deleteLater()` 清理；native finished 移除 stale wrapper；shutdown probe 遇到已刪除 C++ wrapper 時丟棄而不拋出。
- MainWindow 關閉協調：第一次 X 送出一次合作式取消、凍結每日決策／Portfolio pending generation、鎖住內容操作但保留 Qt event loop，依短週期 probe 在 worker 與 TPEX process 完成後自動 `close()`；等待原因與耗時寫入 logger。
- MainWindow 關閉驗收：idle 視窗一次 close 直接接受；busy 視窗一次 close 先保留可見、等待 worker 與 TPEX receipt，再由 Qt timer 自動完成 close，`QApplication.exec()` 自然返回。
- TPEX backend 讀取 view 建立的 cancel marker，只在網路／檔案／SQLite 安全邊界停止，並以 `cancel_completed=true` receipt 區分「已請求」與「已完成」；native crash／非零退出不會被誤標為取消完成。

### 全路徑範圍

既有 offscreen production `MainWindow` writer child 驗證：

`Recommendation → StockResearch → 納入／略過／筆記／提醒 → Watchlist → exact same result／same stock → Workbench`

並驗證：

- `result A / 2330`、`result B / 2330`、`result A / 2317` 三個 candidate key 不串接。
- `result A / 2330` 的 accepted、note、review 可讀回；note request replay 不增加 revision。
- `result B / 2330` 維持 unrecorded；`result A / 2317` 維持 skipped。
- Watchlist 儲存升級後使用 canonical SQLite repository。

writer child 原證據：

`C:\Users\archi\.codex\visualizations\2026\09\14\01a0a234-4ea7-7680-823c-a6939608b18d\mainwindow_journey\run_20260914_224346_24817bcf\summary.json`

該次 exit code 為 0、journal revision 為 4，且同程序 MainWindow 關閉後重建可讀回磁碟資料。另以獨立 reader child 對同一 shared root 重新建立 production MainWindow 並讀回；writer／reader 的 PID 與 process metadata 分開保存。

本次兩個獨立 child continuity 證據：

- writer runner：`C:\Projects\PythonProjects\technical_analysis\output\qa\qtcw_20260915\controlled_run_20260915_004558_87310382\process.json`
- writer child summary：`C:\Projects\PythonProjects\technical_analysis\output\qa\qtcw_20260915\controlled_run_20260915_004558_87310382\summary.json`
- reader runner：`C:\Projects\PythonProjects\technical_analysis\output\qa\qtc_r_20260915\controlled_run_20260915_004625_9a05d12f\process.json`
- reader child summary：`C:\Projects\PythonProjects\technical_analysis\output\qa\qtc_r_20260915\controlled_run_20260915_004625_9a05d12f\summary.json`
- shared durable root：`C:\Projects\PythonProjects\technical_analysis\output\qa\qtcx_20260915`
- writer child PID `32268`、reader child PID `12432`；兩者皆 exit code 0，且 runner 皆記錄 `owned_process_tree_closed=true`、`reported_child_pid_running_after_tree_close=false`。

### 真實資料範圍

上述 runner 使用既有 `RecommendationRepository` 寫入隔離 output 的 synthetic `RecommendationResultDTO`。未涵蓋正式行情、券商資料、Evidence pipeline、live trading、Windows 前景焦點或螢幕閱讀器。

## 原生錯誤與 lifecycle 證據

重開機後的唯讀檢查沒有發現新的 Python WER/Application Error，且當時沒有存活 Python process。可定位的歷史 Python 原生事件為：

- 2026-09-08 22:02:32：`Qt6Gui.dll`、exception `0xc0000005`、PID `0x5924`。
- 2026-09-09 22:41:43：`Qt6Core.dll`、exception `0xc0000409`、PID `0x586C`。
- 2026-09-14 16:54:33–34：Python `AppHangB1`，沒有 faulting module、exception code 或 PID。

正式 crash diagnostics log（唯讀取證）
`D:\Min\Python\Project\FA_Data\logs\ui_qt_crash.log` 的下列紀錄均出現：

`main closeEvent → request_cooperative_task_worker_shutdown → running_task_workers → worker.isRunning → RuntimeError: Internal C++ object (TaskWorker) already deleted`

- `2026-09-10T05:41:43Z`
- `2026-09-12T04:08:33Z`
- `2026-09-13T18:22:32Z`

這證實 stale C++ wrapper 是 production close path 的實際缺陷；尚不能單獨證明它就是使用者 memory-write popup 的完整根因。

## 受控 runner

- launcher：`scripts/qa_run_research_journey_qt_subprocess.py`
- child：`scripts/qa_validate_research_journey_qt.py`
- child 在第一次 Qt import 前，僅在 `TECHNICAL_ANALYSIS_QA_CHILD=1` 下呼叫 process-local `SetErrorMode`；不修改 WER registry 或全域設定。
- 既有 `ui_qt.crash_diagnostics` 在隔離 `DATA_ROOT` 下寫 `SESSION_START/END` 與 native faulthandler trace；launcher 的 child stdout/stderr（含 bounded hang breadcrumb）寫入 `runner.log`。
- Windows launcher 不再以 Popen attach-after-start：先建立 configured Job Object，再以 `CreateProcess(CREATE_SUSPENDED)` 保留 primary process／thread handle，`AssignProcessToJobObject` 成功後才 `ResumeThread`。因此 venv redirector 在可執行前已被納入 tree，之後的 payload 也受 `KILL_ON_JOB_CLOSE` 管理。
- Win32 raw probe：`C:\Projects\PythonProjects\technical_analysis\output\qa\ptree_20260915_r2\run_20260915_004940_69e419b4\win32_process_tree_probe.json`；normal／timeout child log 分別位於同目錄 `normal\child.log`、`timeout\child.log`。
- launcher 寫 `process.json`：launcher PID、redirector/root PID、child 回報的 payload PID／PPID、開始／結束時間、timeout、真正 child exit code、process-tree binding／termination scope、Job close 結果、payload PID cleanup proof、retry count。
- 同類 launcher 使用 process-held lock；一次只啟動一個 Qt child，失敗不自動重試。
- timeout 先有限地處理 runner root，再關閉該 runner 專屬 Job Object；會查驗 child 回報的 payload PID 在 tree close 後已不存在。Job close／payload proof 失敗時 launcher 明確報錯，不宣告 pass；不停止其他 Python，不呼叫全域 `taskkill`，不修改 WER／registry。

受控命令（本次已按 parent gate 執行；每次 runner 只啟動一個 child，失敗不自動重試）：

```powershell
.\.venv\Scripts\python.exe scripts\qa_run_research_journey_qt_subprocess.py --output-dir <隔離 evidence 路徑> --timeout-seconds 120
```

`journey` writer 的內部 restart scope 仍標記為同一 child 內的 MainWindow reconstruction；真正的程序重啟驗收已由 `journey` writer 正常退出後，再以 `continuity_readback` reader child 對同一隔離 `OUTPUT_ROOT`／`DATA_ROOT` 讀回完成。reader 不共享 writer 的 Qt／Python 記憶體。

MainWindow shutdown 原始證據：

- `C:\Projects\PythonProjects\technical_analysis\output\qa\qtshut_20260915_r2\controlled_run_20260915_004531_6945aee2\process.json`
- `C:\Projects\PythonProjects\technical_analysis\output\qa\qtshut_20260915_r2\controlled_run_20260915_004531_6945aee2\runner.log`
- `C:\Projects\PythonProjects\technical_analysis\output\qa\qtshut_20260915_r2\controlled_run_20260915_004531_6945aee2\run_20260915_004531_89a6509c\progress.json`

關鍵結果：idle／busy 各 `close_calls=1`；busy `app_exec_exit_code=0`、TPEX `tpex_status=cancelled`、`tpex_cancel_completed=true`；runner payload PID `30456` 在 Job close 後不存在。第一次較長 evidence 路徑的失敗（SQLite MAX_PATH）另存於 `output\qa\research_journey_qt_controlled_shutdown_20260915`，不是產品錯誤；縮短隔離路徑後針對該環境問題重跑成功。

## 已執行驗證

本次指定的三項必要 gate 已保留實際結果與執行時間：

- `tests/test_ui_qt_update_view_workbench.py`：2026-09-15 執行，`84 passed`、1 個既有
  `PytestCacheWarning`，耗時 `2.17s`。
- `scripts/qa_validate_update_tab.py`：2026-09-15 00:55:02 PDT 執行，exit code `0`，
  通過 `25`／失敗 `0`／跳過 `4`；同期 `VALIDATION_REPORT.md` 生成時間相同。
- 全域 mypy：2026-09-15 00:55:12 PDT（`07:55:12Z`）執行，exit code `0`，
  `Success: no issues found in 614 source files`。

| 驗證 | 結果 | 備註 |
| --- | --- | --- |
| combined focused suite（5 個 test modules） | 118 passed | launcher contract、TPEX backend/UI race、shutdown coordinator、TaskWorker、UpdateView workbench |
| changed Python `py_compile` | 通過 | launcher、TPEX backend、MainWindow／UpdateView／worker、相關測試 |
| `scripts/qa_validate_update_tab.py` | 通過 25／失敗 0／跳過 4 | 2026-09-15 00:55:02 PDT；使用 Temp isolated data/output；未寫入正式資料 |
| `tests/test_ui_qt_update_view_workbench.py` | 84 passed | 2026-09-15；1 個既有 `PytestCacheWarning`；耗時 2.17s |
| global mypy（`ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`） | 通過 | 2026-09-15 00:55:12 PDT（07:55:12Z）；`Success: no issues found in 614 source files` |
| `tests/test_qa_research_journey_subprocess.py` | 4 passed | fake child contract；含 nested PID receipt、Job close failure → launcher error、timeout PID proof |
| `tests/test_tpex_background_refresh_script.py` | 通過 | backend 讀 marker 並寫 `cancel_completed` receipt |
| `tests/test_ui_qt_shutdown_coordinator.py` | 6 passed | 含真 QApplication／真 TaskWorker；第一次 X 後自動 close，未重按 |
| `tests/test_ui_qt_task_worker.py` | 通過 | stale wrapper、native finished、reuse、cancel lifecycle |
| TPEX UI receipt／race tests | 通過 | marker-only cancellation；terminal receipt race；非零 exit 覆寫 stale done/cancelled |
| targeted mypy（9 source files，`--explicit-package-bases`） | 通過 | launcher、child／Win32 probe、MainWindow、UpdateView、DecisionDesk、Portfolio、worker、tests |
| Win32 normal process probe | 通過 | root/redirector PID 與 payload PID 不同；payload 正常退出，Job close／handles close 成功 |
| Win32 timeout process probe | 通過 | payload close 前 running，Job close 後 `payload_running_after_job_close=False`；無遺留 process |
| `mainwindow_shutdown` 受控 Qt runner | 通過 | root `16212`、payload `30456`；idle／busy 單次 close；真 `QApplication.exec()` 自然返回 0；TPEX receipt 完成 |
| `journey` writer + `continuity_readback` reader | 通過 | writer payload `32268`、reader payload `12432`；跨獨立 child 讀回 identity／continuity／journal／Workbench |
| `qa_probe_owned_process_tree.py` | 通過 | raw JSON 已保存 normal／timeout；normal root `7464`／payload `30584`，timeout root `13188`／payload `23132`；兩案 Job／handles close，payload after close 均 false |
| 重開機後 WER／Application Error 唯讀查詢 | 無新的 Python 事件 | 不代表 popup 已修復 |
