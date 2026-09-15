# Qt MainWindow shutdown teardown 修正 QA（2026-09-15）

## 結論

已定位並修正 production Qt entrypoint 的關閉後 teardown hang：`MainWindow.closeEvent()` 與 `QApplication.exec()` 可以完成，但已關閉的 `MainWindow` C++ wrapper 沒有在 `QApplication` 仍有效時排空 `DeferredDelete`，使 Python／PySide6 interpreter teardown 仍可能長時間存活。修正後由 production `main()` 保留 `app.exec()` exit code，並在 return 前於 GUI thread 排空關閉主視窗的 deferred delete；不等待 worker、不呼叫 `terminate()`、`os._exit()` 或全域 End Task。

## 根因證據

1. 2026-09-15 09:58:30 -07:00 的 owned `mainwindow_shutdown` run 在 6.16 秒內結束，但 runner exit code 為 `3221225477`（`0xC0000005`）。子摘要雖然 idle／busy 都記錄 `QApplication.exec()` 自然返回與 `SESSION_END clean_shutdown=true`，不能覆蓋 runner 的 native exit failure。原始收據：
   `output/qa/qt_shutdown_followup_20260915_child/controlled_run_20260915_095830_622adf23/process.json`
2. 2026-09-15 10:02:34 -07:00 的 direct payload 在輸出 `Research journey Qt QA passed`、寫入 clean `SESSION_END` 後，PID 27312（其 venv redirector PID 22368）仍存活逾三分鐘；CPU／thread 狀態固定，顯示 hang 位於 `app.exec()` 返回後的 process teardown。之後只依 exact owned PID 清理 27312／22368，未碰其他 Python、MCP 或 pytest 程序。原始收據：
   `output/qa/qt_shutdown_followup_20260915_direct/summary.json`
3. `task_worker_lifecycle` 在獨立 owned process 中通過；此次對照未重現通用 `TaskWorker` 場景失敗，支持優先定位 MainWindow／Qt object teardown，但不能僅憑單次通過排除所有 launcher 交互。

## 修正後 bounded evidence

### 原始命令

```text
.\.venv\Scripts\python.exe scripts\qa_run_research_journey_qt_subprocess.py --mode mainwindow_shutdown --timeout-seconds 60 --terminate-grace-seconds 5 --output-dir output\qa\qt_shutdown_followup_20260915_fixed2 --lock-path output\qa\.qt_shutdown_followup_20260915_fixed2.lock
```

### 結果

2026-09-15 10:13:20.418636 至 10:13:26.999651 -07:00：

- runner `status=passed`、`exit_code=0`、`timed_out=false`。
- owned Windows Job tree 已附加並正常關閉；payload PID 25020 在 tree close 後不存在，exit proof 為 `pid_not_running_after_tree_close`。
- idle：`user_close_calls=1`、`first_close_auto_accepted=true`。
- busy：`user_close_calls=1`、`first_close_ignored_then_auto_closed=true`；TPEX helper exit code 0、status `cancelled`、`cancel_completed=true`；worker 已取消並解除註冊。
- `QApplication.exec()` 自然返回，exit code 0，elapsed 約 0.141 秒；close elapsed 約 0.016 秒。
- isolated crash log 記錄 `SESSION_END clean_shutdown=true` 且 `exception_observed=false`。

原始收據：

- `output/qa/qt_shutdown_followup_20260915_fixed2/controlled_run_20260915_101320_bfe75abc/process.json`
- `output/qa/qt_shutdown_followup_20260915_fixed2/controlled_run_20260915_101320_bfe75abc/summary.json`

## Harness／entrypoint 邊界

- 曾有一次 intermediate `fixed` run exit 1，原因是 QA harness import 位置錯誤造成 `_drain_qt_deferred_deletes` `NameError`；不是 production failure。修正 import 後才採用 `fixed2` 收據。
- 另以實際 `ui_qt.main.main()` 與實際 `MainWindow` 做 production-entrypoint lifecycle proof：offscreen 啟動，等待實際 top-level window 後只呼叫一次 close；`app.exec()` 自然返回 0，`main()` 返回 0。這證明 entrypoint teardown 邊界，但因 CUA trusted RPC 未配置，不宣稱 foreground Windows 點擊證據。
- `SESSION_END clean_shutdown=true` 是應用程式診斷收據，不是 OS process exit 收據；任何後續排錯都必須同時檢查 OS exit code、owned process tree 與 PID 殘留。
- 既有 memory-write native popup 截圖仍沒有可對應的精確 PID、啟動時間或 native stack；本文件不宣稱該歷史畫面與本次 teardown hang 已證明是同一根因。

## 已完成 gates

- `py_compile`：`ui_qt/main.py`、`scripts/qa_validate_research_journey_qt.py`、`tests/test_ui_qt_shutdown_coordinator.py` 通過。
- `pytest tests/test_ui_qt_task_worker.py tests/test_ui_qt_shutdown_coordinator.py -q -o addopts=`：25 passed；僅既有 `.pytest_cache` permission warning。
- `pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=`：84 passed；僅既有 `.pytest_cache` permission warning。
- `scripts/qa_validate_update_tab.py`：通過 25、失敗 0、跳過 4。
- `mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`：621 source files、0 issues。
- `git diff --check`：通過；僅 LF／CRLF warning。

## 未納入本次修正的已知項目

`ui_qt/widgets/sqlite_inspector_widget.py` 的 `_release_worker()` 仍有獨立候選：worker 自行 emit `finished` 後，queued callback 可能在 native `QThread.run()` 尚未返回時執行 `isRunning()`／`wait()`，使該 inspector refresh／close 路徑阻塞 GUI。本次預設 MainWindow idle／busy reproduction 未開啟 SQLite inspector，也未觀測到該路徑，因此不將此候選與本次已證實的 production MainWindow teardown hang 混為一談。
