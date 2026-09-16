# 跨頁決策旅程：真實 MainWindow 驗收紀錄（2026-09-15）

## 結論

本次 bounded acceptance 已完成。驗收以實際 `MainWindow` signal／slot 路徑驗證：

`Market／Industry → Stock Research → Recommendation save → Watchlist／Portfolio → Workbench → Decision → Outcome Journey → review action → 獨立程序讀回`

結果與限制如下：

- exact identity 以 `(result_id, stock_code)` 為 candidate key，並同步檢查 decision date、data date、source snapshot id/hash。
- Recommendation producer 使用 production `RecommendationService.run_recommendation()`；未手動指定 `result_id`，由 production default 產生 `rec_<uuid>`，再由真實 `RecommendationView` save button／save coordinator 保存。
- Market／Industry 與 Recommendation 的行情／產業資料是明示的 synthetic UI fixture；Portfolio 交易也是研究驗收用 synthetic position，不代表 broker order 或實際成交。
- 缺 candidate、future outcome、identity conflict、讀取失敗與過期結果均採 fail-closed；既有 stale Position Health gate 另以 focused test 驗證。
- 本輪只同步 `APPLICATION_MANUAL.md` 的最小 user-visible hunk；未修改任何 SSOT／Roadmap／index，也未 stage、commit 或 push。

## 主流程驗收

執行：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_cross_page_decision_journey_mainwindow.py -q -o addopts= --tb=short
```

結果：`4 passed`。其中包含：

1. 真實 MainWindow 的 Market／Industry representative signal 進入 Stock Research，無 `result_id` 時呈現未連結。
2. 真實 RecommendationView 以 production recommendation producer 產生 UUID result，透過 save button 寫入 result、watchlist 與後續 exact source identity。
3. 同一股票的 R1／R2／UUID-R3 不以第一列或同股替代；Watchlist、Portfolio、Workbench 均依 exact result identity 定位。
4. Workbench double-click 進入真實 Stock Research dialog，再等待 Journey 實際完成，驗證 candidate、maturity、continuity controls 與 reminder。
5. 唯一額外寫入是使用者明確按下「設定下次檢視」；推薦 JSON、Watchlist、Portfolio trades 在讀取／Journey 路徑前後 SHA-256 不變。
6. Recommendation saved row 的 English／Chinese stock-code alias 任一缺失仍相容；同列矛盾且涉及 requested code，或有效 row 加上同候選矛盾列，均維持未連結；與 requested code 無關的矛盾列不會封鎖該候選。

## fail-closed／競態驗收

執行：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_ui_qt_decision_outcome_journey.py tests\test_ui_qt_decision_continuity_controls.py tests\test_cross_page_decision_journey_mainwindow.py::test_actual_mainwindow_journey_fail_closed_for_missing_future_and_conflict -q -o addopts= --tb=short
```

結果：`11 passed, 1 skipped`。

- missing candidate：`R1:1101` 不會補接 `R1:2330`，Journey 顯示沒有 exact candidate，四個研究動作全部停用。
- future outcome：呈現「待成熟（未有足夠未來資料）」；不把未來日期或 pending row 宣告為 ready／實際損益。
- identity conflict：Journey badge 顯示「衝突」，不啟動跨來源 join，四個研究動作全部停用。
- unsaved／缺 `result_id`：既有 Journey／continuity component gate 會明示未連結且不呼叫 service、不綁定其他 decision。
- read failure → success：失敗時 actions 停用；下一次 exact context 成功後 controls 恢復，舊 failure 不會污染新結果。
- late return：切換股票／result 後，較慢的舊 worker response 不會覆蓋新 context。

過期資料另執行：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_position_health_transition_read_service.py -q -o addopts= -k stale --tb=short
```

結果：`1 passed, 14 deselected`；stale artifact 仍撤銷 raw hold candidate，不會降級成可操作持倉。

## 獨立程序讀回證據

讀回程序會重新建立 production `MainWindow`，不是只讀 JSON 或只呼叫 Continuity service。它等待 Report 與 Journey 各自完成，並斷言：

- persisted result、watchlist、portfolio trade、continuity 都有一致的 result、stock、decision date、snapshot id/hash。
- Journey 真正找到 `(result_id, stock_code)` candidate。
- Journey source identity、Report context、Journey context、session strip 完全一致。
- continuity controls 的 exact candidate 與 `next_review_at` 存在，且 reminder 真的出現在 controls status text。
- `app.exec()` 回傳 0、window 隱藏、沒有剩餘 worker、沒有 watchdog／forced termination。

驗證 receipt：

`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_mainwindow_readback_receipt_verified.json`

本次 receipt 的核心結果為：`persisted_identity_consistent=true`、`journey_loaded=true`、`exact_identity_visible=true`、`app_exec_returncode=0`、`process_exit_code=0`、`remaining_workers_after_exec=0`。實際測試 result id 為 `rec_5578d5bcc23c4bf59e0edcd5e3be3180`。

### 外層 OS runner 證據

原先的 inline-only 記錄不作驗收依據；本輪已依授權使用既有 `qa_run_research_journey_qt_subprocess._OwnedProcessTree` helper，實際執行一次 bounded runner。outer command 在 owned tree/workdir `C:\Projects\PythonProjects\technical_analysis` 執行：

```text
.\.venv\Scripts\python.exe scripts\qa_cross_page_mainwindow_owned_runner.py --output-root 'C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_owned_runner' --timeout-seconds 90
```

outer `functions.exec_command` tool result：`chunk_id=90373f`、`exit_code=0`、`wall_time_seconds=16.6487867`、無 `session_id`（同步完成，未被 executor timeout）。外層 runner summary：[processes.json](C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_owned_runner\run_20260915_115657_e43fe5fb\processes.json)；summary 的 `status=passed`、runner PID `35392`、workdir 與 command 均已保存。

- Readback writer／reader：外層 child `return_code=0`、`timed_out=false`、`timeout_seconds=90`、`termination_scope=owned_windows_job_object_process_tree`、`process_tree_binding=create_suspended_assign_before_resume`、`process_tree_management=windows_job_object_kill_on_close`、`owned_process_tree_attached=true`、`owned_process_tree_closed=true`、root PID `22376` 在 tree close 後 `false`。實際 child stdout：[stdout.log](C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_owned_runner\run_20260915_115657_e43fe5fb\readback_writer_reader\stdout.log)；外層 process receipt：[process.json](C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_owned_runner\run_20260915_115657_e43fe5fb\readback_writer_reader\process.json)。child stdout 實際為 `1 passed, 1 warning`；測試內的 readback child 仍以 `subprocess.run(..., timeout=30)` 並斷言 return code `0`。
- Busy-close：外層 child `return_code=0`、`timed_out=false`、`timeout_seconds=90`、同一 owned Job Object binding／management、root PID `33880` 在 tree close 後 `false`。實際 child stdout：[stdout.log](C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_owned_runner\run_20260915_115657_e43fe5fb\busy_close\stdout.log)；外層 process receipt：[process.json](C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_owned_runner\run_20260915_115657_e43fe5fb\busy_close\process.json)。production close receipt：[busy_receipt.json](C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_owned_runner\run_20260915_115657_e43fe5fb\busy_receipt.json) 仍記錄 `user_close_requests=1`、`forced_termination=false`、`app_exec_returncode=0`。

兩個 `stdout.log` 是 owned child 的實際檔案輸出；`process.json` 是 runner 直接寫入的 OS process／tree metadata，不把 workdir 本身冒稱為 Windows Job tree。

## Busy-close／一次 close 證據

執行的是獨立 OS process 與實際 `MainWindow`，worker 在可控 barrier 停留於 busy，對主視窗只發出一次 user close，再由 production close lifecycle 合作取消並自動完成收尾：

```text
.\.venv\Scripts\python.exe scripts\qa_cross_page_mainwindow_busy_close.py --data-root <isolated-data-root> --output-root <isolated-output-root> --receipt <receipt-path>
```

驗證 receipt：

`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\cross_page_mainwindow_busy_close_receipt_rerun.json`

核心欄位：`actual_main_window=true`、`report_worker_reached_busy_barrier=true`、`close_requested_while_busy=true`、`user_close_requests=1`、`dialog_finished=true`、`watchdog_fired=false`、`forced_termination=false`、`app_exec_returncode=0`、`process_exit_code=0`。`main_window_close_event_count=2` 是一次 user request 加上 production deferred auto-close，不是第二次使用者操作；probe finally 亦使用正式 `_drain_qt_deferred_deletes`。

## 既有 gate 與程式檔

本次實作／驗收相關檔案：

- `ui_qt/views/portfolio_view.py`：同股多 position 以 selected row 的 `position_id` 解析，不取第一筆；saved result 的 English／Chinese alias 缺一相容、涉及 requested code 的矛盾 fail-closed，無關矛盾不誤封鎖。
- `ui_qt/widgets/decision_continuity_controls.py`：Journey 尚未驗證 exact candidate 時提供明確 blocked state。
- `ui_qt/widgets/decision_outcome_journey_widget.py`：loading、error、missing candidate、identity conflict 時停用 actions；valid candidate readback 後重新同步 controls。
- `tests/test_cross_page_decision_journey_mainwindow.py`、`scripts/qa_cross_page_mainwindow_busy_close.py`、`scripts/qa_cross_page_mainwindow_readback.py`、`scripts/qa_cross_page_mainwindow_owned_runner.py`：真實 MainWindow 主流程、獨立 close、獨立讀回與 owned process-tree 證據。

既定 gate 亦已通過：

- `tests\test_ui_qt_update_view_workbench.py`：`84 passed`。
- `scripts\qa_validate_update_tab.py`：`通過 25／失敗 0／跳過 4`。
- `mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`：`Success: no issues found in 622 source files`。
- 變更 Python 檔案 `py_compile`：通過；`mypy ui_qt\\views\\portfolio_view.py`：`Success: no issues found in 1 source file`。

pytest 的唯一警告是受限環境無法寫入 repository `.pytest_cache`；不影響測試結果，也未納入本次變更。

## Manual 最小增補（本輪已套用）

以下是本輪套用的 user-visible 最小 hunk；既有 `docs/07_guides/APPLICATION_MANUAL.md` 的 foreign／L dirty 內容保留，沒有 stage：

```diff
--- a/docs/07_guides/APPLICATION_MANUAL.md
+++ b/docs/07_guides/APPLICATION_MANUAL.md
@@
 4. 只有明確需要改變研究狀態...
+5. 由觀察清單或持倉列開啟的個股研究報告，需等待「報告已載入」及「決策 → 結果」完成 exact candidate 驗證；驗證期間、讀取失敗、candidate 缺件或 identity conflict 時，Journey 的研究動作會停用。驗證成功後才會恢復目前 candidate 的 controls。
@@
 - result_id 是推薦結果根；同一股票出現在多個結果時...
+- Portfolio 同一股票可能有多個持倉來源；研究入口依目前選取列的 `position_id` 及其保存的 `result_id` 定位，不會取第一筆同股持倉。Recommendation 保存列若缺少 exact stock、重複或雙語代號矛盾，保持未連結。
@@
 - 看見 identity conflict...
+- Journey 顯示「待成熟（未有足夠未來資料）」時，只代表未有足夠 future observation，不是 ready，也不是成交損益；缺件／讀取失敗／identity conflict 時，可重新載入原結果，但不能視為已驗證或手動猜配對。
```
