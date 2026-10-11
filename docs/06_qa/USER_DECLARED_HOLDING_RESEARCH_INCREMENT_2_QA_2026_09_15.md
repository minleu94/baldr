# user_declared Holding Research Increment 2 QA

> 日期：2026-09-15
>
> 範圍：使用者自行聲明持倉的 research-only 保存、修訂、封存、PIT 研究讀模型、Portfolio UI 與關閉生命週期。
>
> 操作步驟與欄位判讀請從[操作手冊 §10.0](../07_guides/APPLICATION_MANUAL.md)進入；本 QA 僅保存本輪 bounded acceptance evidence。

## 1. 驗收結論

Increment 2 已通過 bounded engineering acceptance。這條 lane 只保存使用者聲明的
股票、整數股數、Decimal 聲明成本、聲明日期、備註與研究假設；它不宣稱券商成交、
Paper verified entry、正式 Portfolio fill、已實現績效或投資有效性。

核心與 Portfolio focused suite 共 `43 passed`；TaskWorker／shutdown regression 為
`24 passed`。Update UI 必要 suite 為 `84 passed`，validator 為 `25 passed / 0 failed /
4 skipped`，全域 mypy 為 `Success: no issues found in 617 source files`，本輪變更 Python
檔案 `py_compile` exit `0`。

## 2. Acceptance matrix

| 面向 | 驗證 | 結果 |
|---|---|---|
| append-only identity | `holding_id + revision_number`、revision chain、archive history、CAS | 通過 |
| idempotency／conflict | 同 request replay 只讀回同一 event；不同 active 同股 request conflict；封存後新 request 可建獨立 holding | 通過 |
| PIT cutoff | evaluation／evaluated_at 不得 future；as-of／availability 不得晚於單一 timezone-aware cutoff | 通過 |
| source quality | source id、`sha256:<64 hex>`、quality allowlist、stock scope、market／condition freshness | 通過 |
| historical custody | 本機檔案 mtime 只作 current local observation；歷史正向研究需 source `availability_custody` | 通過 |
| real condition integration | 既有 Recommendation／PortfolioConditionMonitor 的 regime、score、stop／take-profit 規則可映射 HOLD／REDUCE／EXIT；只有價格時維持 WAIT | 通過 |
| saved recommendation baseline | 以聲明日前 baseline 與評估日 current 的不同 snapshot 比較；self-compare、缺 baseline、profile／version／score identity 不一致均 WAIT | 通過 |
| UI revision safety | 保存後以 exact `(holding_id, revision)` 選取；切換歷史日期不會把舊 revision 靜默編輯成 current | 通過 |
| UI presentation | 1366×768 與 1700×1100 Portfolio 實際視窗；表單預設收合；頁內垂直捲動；主表至少可見完整表頭與一列 | 通過 |
| close lifecycle | busy worker 時 user-level close 一次；合作取消；MainWindow shutdown coordinator 自然關窗；不 terminate／wait | 通過 |

## 3. Independent writer／reader QA

執行命令：

```text
.\.venv\Scripts\python.exe scripts\qa_user_declared_holding_research.py --mode all
```

最新 run：`output/qa/user_declared_holding_research_increment_2/run_6c0bc1098d89/`。
writer 與 reader 是兩個獨立 subprocess，共用同一個 runtime root；reader 沒有建立
fixture，也沒有呼叫 create API。

writer 由實際 Qt `PortfolioView` 驗證新增與修訂，再以與既有 `MainWindow` 相同的
shutdown coordinator methods 建立最小 `QMainWindow` harness。此 harness 不是完整
MainWindow 初始化的冒充；它只讓本 QA 在實際 Portfolio UI 上驗證既有關窗協調器的
單次 user close、worker cancellation 與 `app.exec()` 自然結束。

writer 結果：

- `close_requests_from_user=1`
- `busy_close_started=true`
- `cancel_observed=true`
- `app_exec_exit_code=0`
- `forced_termination=false`
- UI 實際新增後修訂至 `revision 2`
- 修訂內容含 `quantity=120`、`notes=writer revision note`、`研究假設=writer revision 研究假設`

reader 結果：

- `fixture_created_by_reader=false`
- 同一 runtime root 讀回同一 `holding_id` 的 `revision_number=2`
- `history_actions=[created, revised]`、`history_count=2`
- `quantity=120`
- notes／研究假設與 writer 修訂值完全一致
- reader subprocess return code `0`

## 4. UI visual evidence

最新圖檔位於：

- `output/qa/user_declared_holding_research_increment_2/run_6c0bc1098d89/evidence/portfolio_user_declared_research_1366.png`
- `output/qa/user_declared_holding_research_increment_2/run_6c0bc1098d89/evidence/portfolio_user_declared_research_1700.png`
- `output/qa/user_declared_holding_research_increment_2/run_6c0bc1098d89/evidence/user_declared_research_technical.png`

1366×768 首屏確認：

- 黃色安全邊界完整換行，沒有以截斷文字取代限制說明。
- 表單預設收合，主表看得到完整表頭與 `2330 / 120 / 持有 / 可檢視 / 仍符合` 一列。
- 主表以精簡中文呈現；完整 action、entry lineage、fill verification、source trace 與
  research-only flags 留在明細／技術詳情。
- 研究內容在 Portfolio 右側 tab 內垂直捲動，不把整個 Portfolio main window 撐出
  1366×768 viewport，也不改變 Paper identity。

## 5. Commands and output

```text
.\.venv\Scripts\python.exe -m pytest tests/test_user_declared_holding_research.py tests/test_ui_qt_user_declared_holding_research.py tests/test_ui_qt_portfolio_view.py -q -o addopts=
43 passed, 1 warning

.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_task_worker.py tests/test_ui_qt_shutdown_coordinator.py -q -o addopts=
24 passed, 1 warning

.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=
84 passed, 1 warning

.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
通過: 25；失敗: 0；跳過: 4

.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
Success: no issues found in 617 source files

.\.venv\Scripts\python.exe -m py_compile <本輪變更 Python 檔案>
exit 0
```

pytest 的唯一 warning 是受控環境無法寫入 `.pytest_cache`；不影響 test exit code，
也沒有把 cache 或 QA output 當成正式資料提交。

## 6. 明確不在本輪範圍

- 不寫正式 Portfolio trade ledger、Paper ledger、Evidence credit 或 broker state。
- 不把聲明成本當成 observed fill，不計算 realized PnL、滑價、費稅或 calibration cohort。
- 不因本輪 synthetic／local QA 宣稱自然 forward evidence、Paper effectiveness、V4
  formal closeout 或策略有效。
- 不修改或重建正式 `DATA_ROOT` 原始資料；QA 使用隔離 runtime root。

## 7. 回滾與保留

- 回滾程式時保留 `user_declared_holdings.jsonl` 原始 append-only 檔案及所有 revision；
  不以刪除檔案方式清理功能。
- 若新 UI 無法讀回，先保留 runtime／JSONL 與 technical detail，回到上一個已驗收的
  Portfolio UI；不得把歷史 revision 改寫成成交或 Paper entry。
- 若需再次驗證，使用新的隔離 `run_<id>` 目錄，不覆寫既有 evidence 或正式資料。
