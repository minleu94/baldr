# Decision Continuity Write Path Increment A QA

日期：2026-09-14
範圍：typed decision identity、WatchlistRepository current/history、JournalService append-only revision、JSONL reader boundary。

## 驗證結果

- focused contract／storage／Journey suite：63 passed
- 指定型態檢查：mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime，612 source files，Success
- changed Python files：py_compile 通過
- 既有 watchlist migration、portfolio delete／journal MVP、JSONL Decimal serialization 與 DecisionOutcomeJourney 測試均納入 focused suite。

## 已驗證契約

1. DecisionIdentity 明確保存 result_id、stock_code 與可用的 source_snapshot_id／source_snapshot_hash；巢狀與頂層值或 context 股票不一致時 fail-closed。legacy source_id 不會被猜成 result identity，candidate_key 在 unknown／conflict 下只供診斷。
2. WatchlistRepository 在同一 SQLite transaction 內更新 current projection 與 append-only revision；legacy current row 升級時先建立 observation-time baseline，刪除留下 tombstone，revision／event conflict 與 stale revision 不會覆寫資料。bounded JSON import 保留來源 bytes，重跑不新增 history。
3. journal_entries.jsonl 保留既有 legacy 行，JournalService delete／clear 只追加 revision tombstone；active projection 隱藏 tombstone，accepted／skipped／review_scheduled 不進 active note，也不建立 trade。JSONL lock、snapshot token、revision parent 與損毀／partial stream 防護拒絕不安全覆寫。
4. Journey reader 會在 query_boundary 先篩選 revision observation time，再建立 active projection；未來 note／tombstone 不會洩漏到較早的 as-of 查詢。研究 identity 缺 key 或 timestamp 不可比較時不猜測。

## 邊界與限制

- 本增量未對正式 DATA_ROOT／個人資料執行 migration、重建或刪除。
- Watchlist 預設 JSON writer 與 MainWindow 預設 repository wiring 尚未切換；UI 研究 action controls 留待 Increment B。
- 本增量不接 broker、不建立正式成交、不改 Portfolio ledger；accepted／skipped／note／review_scheduled 是研究 continuity records。
- Manual 的 Journal 刪除／清空說明已同步為歷史保留語意；其他 agent 的 UI／排程 dirty hunks 不在本 QA commit。

## 重現命令

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_decision_continuity_write_path.py tests/test_task_loop_07_contract.py tests/test_portfolio_delete.py tests/test_portfolio_mvp.py tests/test_portfolio_jsonl_store_serialization.py tests/test_decision_outcome_journey.py -q -o addopts=

.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
~~~
