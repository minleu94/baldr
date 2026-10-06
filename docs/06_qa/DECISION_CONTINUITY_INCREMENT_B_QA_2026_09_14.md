# Decision Continuity Increment B QA（2026-09-14）

## 範圍

本次驗收涵蓋個股研究報告「決策 → 結果」分頁的研究動作控制項、Journey Journal 精確範圍，以及觀察清單 JSON → SQLite 的明確一次性升級。研究動作只保存 append-only Journal，不採用 Advice、不建立 Portfolio trade、不呼叫 broker。

研究上下文必須同時帶有 exact `result_id` 與 `stock_code`。缺少、未知、衝突或讀回失敗時，控制項 fail-closed；不以 `source_id`、同股同日、日期或目前 head 猜測 identity。接受／略過意向與下次檢視提醒分開投影，筆記以獨立 entity 回連同一 candidate。

## 自動化證據

以下測試均使用隔離的 `tmp_path`／offscreen Qt，不讀寫正式資料：

- `tests/test_decision_continuity_controller.py`：exact result+stock、接受／略過／筆記／提醒、同 request id 在較新 action 後重送、snapshot 衝突、寫入後讀回失敗。
- `tests/test_ui_qt_decision_continuity_controls.py`：中文狀態／按鈕、日期時間選擇、重開讀回、技術詳情收合、缺 identity 停用、失敗重試。
- `tests/test_ui_qt_journal_scope_increment_b.py`：typed identity 的 A → B → A 隔離、legacy shared scope、malformed／unknown／conflict／direct-link conflict fail-closed。
- `tests/test_watchlist_storage_wiring_increment_b.py`：第二份來源失敗、staging 清理、來源核對失敗、未完成 activation、marker 失敗後重啟 recovery、來源變更拒絕啟用、成功後唯一 SQLite writer 與 JSON bytes 保留。

必要的既有回歸包含 `tests/test_decision_continuity_write_path.py`、`tests/test_ui_qt_decision_outcome_journey.py`、`tests/test_task_loop_07_contract.py`、`tests/test_ui_qt_watchlist_layout.py`、`tests/test_ui_qt_stock_research_navigation.py` 與 `tests/test_ui_qt_update_view_workbench.py`。

## Production Qt CJK 畫面 smoke

使用 production `apply_app_theme`、實際 `DecisionOutcomeJourneyWidget`／研究動作控制項與 offscreen Qt 產生三張隔離畫面：

- 初始 exact candidate：`<USER_HOME>\.codex\visualizations\2026\09\14\01a0a234-4ea7-7680-823c-a6939608b18d\decision_continuity\decision_continuity_default.png`
- 保存後（已納入研究、筆記、下次檢視）：`<USER_HOME>\.codex\visualizations\2026\09\14\01a0a234-4ea7-7680-823c-a6939608b18d\decision_continuity\decision_continuity_saved.png`
- 缺少 `result_id` 的 identity blocked：`<USER_HOME>\.codex\visualizations\2026\09\14\01a0a234-4ea7-7680-823c-a6939608b18d\decision_continuity\decision_continuity_identity_blocked.png`

畫面可見繁體中文狀態、筆記／提醒摘要、研究按鈕與停用原因；technical ID／history 仍收合。這是 production widget 的 isolated visual smoke，不宣稱完整的 Recommendation → Watchlist → Research → Workbench 往返或正式 MainWindow 全流程已驗收；完整往返仍需另做隔離 MainWindow smoke。

## 儲存啟用驗收

MainWindow 啟動只對 `OUTPUT_ROOT/watchlist/watchlists.db` 做 query-only readiness 與 activation marker discovery，不在啟動時建立或遷移 DB。使用者在候選池頁明確按下「升級觀察清單儲存」後，服務才會：

1. 預檢 bounded `watchlist/*.json` 的 payload 與重複股票身份。
2. 在暫存 DB 完成所有來源的 migration，核對原始 bytes、payload 與 source hash。
3. 以不覆寫既有目標的方式發布 canonical DB，再建立 `watchlists.db.active` 的 complete marker。
4. 只有 DB、全部來源與 marker 都成功後才切換 service writer；成功後日常增改只寫 SQLite，原 JSON 保留且 bytes 不變。

任一來源、schema、來源 hash、post-publish readback 或 marker 寫入失敗，都留下原 JSON 可用，canonical 保持 inactive（若已發布但未有 marker，重啟仍選 JSON），並顯示可重試訊息。已有完整 schema、但目錄仍有 legacy JSON 且沒有 complete marker 的 DB 不會被搶先採用；沒有 legacy JSON 的既有 schema v2 DB 則保留明確相容讀取。

## 結果

- Increment B 與既有 Journey／Watchlist／navigation 回歸：`59 passed, 1 skipped`。
- `tests/test_ui_qt_update_view_workbench.py`：`81 passed`。
- `scripts/qa_validate_update_tab.py`：`通過 25、失敗 0、跳過 4`。
- mypy：`Success: no issues found in 614 source files`。
- 變更 Python 檔案 `py_compile`：通過。

pytest 只出現既有 `.pytest_cache` 無法寫入的環境 warning；不影響測試結果，也未接觸正式資料。

驗證命令如下：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_decision_continuity_controller.py tests/test_ui_qt_decision_continuity_controls.py tests/test_ui_qt_journal_scope_increment_b.py tests/test_watchlist_storage_wiring_increment_b.py tests/test_ui_qt_watchlist_storage_wiring_increment_b.py tests/test_decision_continuity_write_path.py tests/test_ui_qt_decision_outcome_journey.py tests/test_task_loop_07_contract.py tests/test_ui_qt_watchlist_layout.py tests/test_ui_qt_stock_research_navigation.py -q -o addopts=
.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=
.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
.\.venv\Scripts\python.exe -m py_compile app_module\decision_continuity_controller.py app_module\decision_outcome_journey.py app_module\watchlist_service.py ui_qt\main.py ui_qt\views\stock_research_report_view.py ui_qt\views\watchlist_view.py ui_qt\widgets\decision_continuity_controls.py ui_qt\widgets\decision_outcome_journey_widget.py tests\test_decision_continuity_controller.py tests\test_ui_qt_decision_continuity_controls.py tests\test_ui_qt_journal_scope_increment_b.py tests\test_watchlist_storage_wiring_increment_b.py tests\test_ui_qt_watchlist_storage_wiring_increment_b.py
```

pytest 的既有環境可能因 `.pytest_cache` 權限顯示 warning；該 warning 不代表測試失敗，也不涉及正式資料。任何正式資料操作仍須另依更新鎖、備份與資料完整性流程，不能以本次 isolated QA 取代。
