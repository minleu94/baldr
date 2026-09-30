# 唯讀服務刷新取消與回歸驗證（2026-09-30）

## 結果

唯讀服務支援合作式取消：長時間 SQLite 查詢可由 worker 取消，取消訊號不會降級成一般資料錯誤；唯讀連線在中斷後關閉。讀取範圍未延伸到 writer、migration 或正式資料寫入。

## 驗證

- `tests/test_read_only_service_cancellation.py` 與 evidence event、forward performance、research run 三個 repository contract suites：**19 passed**。其中 cancellation case 執行真實 recursive CTE，確認取消通知、native thread finished、無 worker error，並在 worker thread 驗證連線已關閉。
- 其餘指定 service contracts 以 repo-local pytest temp、`TEMP/TMP` 隔離執行；移除三個依賴特定 OS temp 根目錄的個別案例後為 **125 passed、1 failed**。三個路徑契約案例以各自所需環境另行驗證：performance owner packet **1 passed**（一般 OS TEMP），MOPS **2 passed**（外部隔離輸出與獨立 `DATA_ROOT`）。
- 唯一未通過的既有案例為 `test_workbench_source_service_reads_real_read_only_sources`。在隔離 child 中載入 Git `HEAD` 的 `WorkbenchSourceService` 原始碼，再以相同 pytest basetemp 與環境重跑，結果仍相同，確認是基線失敗。fixture 將 `scheduled_rec_*.json` 寫為 `{}`，strict legacy reader 因 `legacy data_path 與 result_id 的舊檔名規則不符` 拒絕內容；拒絕檢查位於未修改的 recommendation query path，沒有放寬安全驗證或改動 fixture。
- repo-wide mypy 739 個來源檔通過（由 root 執行）；本範圍 `py_compile` 與 `git diff --check` 通過。

驗證 logs 保存於 ignored `output/qa/ui_shutdown_20260930/`；repo-local pytest basetemp 為 `output/.ushsvc0930b`，MOPS QA output 與資料根使用獨立隔離目錄。未讀寫正式資料。
