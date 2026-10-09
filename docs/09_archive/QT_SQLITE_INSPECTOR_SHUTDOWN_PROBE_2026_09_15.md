# SQLite inspector refresh／close bounded probe（2026-09-15）

## 結論

本次只驗證一條 production MainWindow → UpdateView `db_inspector` → SqliteInspectorWidget refresh／busy close 路徑。有效 owned probe 通過，OS `exit_code=0`、`timed_out=false`；busy 時只送出一次 user close，合作式取消後自動完成關閉。沒有重現 GUI `wait()` deadlock、stale C++ wrapper 或非零 OS exit，因此沒有新增 product fix。

## 實際路徑與收據

- 實際建立 production `MainWindow` 與 `SqliteInspectorWidget`。
- 實際呼叫 `UpdateView._on_nav_changed()` 進入 `db_inspector`，確認 `refresh_tables()` 已執行。
- child-only fake service 僅讓唯讀 `query_table_data_count()` 在 background Qt thread 暫停；不讀寫正式資料。
- busy worker 可觀測後，只呼叫一次 `MainWindow.close()`；首次 close 被忽略，既有合作式取消與 auto-close 完成。
- 有效 run：2026-09-15 11:28:22.432070 至 11:28:27.302256 -07:00；owned Job tree 關閉後 payload 已退出。
- 收據位於 `output/qa/qt_sqlite_inspector_probe_20260915/controlled_run_20260915_112822_f34e5c02/`：`process.json`、`sqlite_inspector_probe.json`。

關鍵狀態為：`refresh_tables_called=true`、`close_calls=1`、`worker_running_at_close=true`、release callback 在 GUI thread 返回且 `worker_running_before=false`、`QApplication.exec()` 自然返回 0、worker 在 exec 返回後不存活。

## 靜態候選與限制

`SqliteInspectorWidget._release_worker()` 仍在 `worker.isRunning()` 時呼叫同步 `wait()`；但本次實際 callback 到達時 worker 已停止，沒有實測到該 wait race。故只能判定本次 tested path 未重現阻塞，不能排除所有 signal scheduling race；不以單一路徑通過宣稱候選不可能發生。

第一次 11:27:42 run 只是一次性 child harness 的 `sys.path` 錯誤，尚未載入 Qt，不能作產品失敗證據；其後修正 import path 的 harness 原文與 outer command 保存在同一個 ignored QA 目錄供核驗。既有 memory-write popup 的 PID／native stack 仍未對上，本 probe 不宣稱兩者同根因。

本次未修改 `ui_qt/main.py` 或 `sqlite_inspector_widget.py`，未重跑無關 gates，未修改 Manual，未觸碰其他 owner dirty。驗證期間未操作 index；本文件提交範圍僅 QA 紀錄。
