# Position Health Increment 1 QA（2026-09-15）

## 範圍

本次增量只把既有 Paper `DailyPositionHealthTransitionEvaluator` 的 persisted
receipt 接到 Portfolio 與 Workbench 的共同 typed read model。消費端只讀
`position_health_transition\latest_status.json`、result 與 latest pointer，不執行
evaluator，也不寫 receipt、registry、scheduler、Paper／人工 ledger 或 broker。

本次不建立 `user_declared` entry layer，不改 Advice、replay、continuity 或正式交易
執行 gate。所有 health action 固定是 `research_only=true` 的 proposal。

## 實作與契約檢查

- `PositionHealthPresentationDTO` 與 `PositionHealthReadModel` 集中於
  `app_module/decision_presentation.py`，Portfolio／Workbench 共用同一份 projection。
- `PositionHealthTransitionReadService` 會驗證 producer／schema、result hash、latest
  pointer、source snapshot id／rows hash、cohort、exact `position_id`、decision／
  observed clock、來源 `available_at`、future／stale／corrupt scope，以及
  `research_only` 安全邊界。
- source／thesis／metrics／condition 不完整、identity 未驗證或 receipt 失敗時，raw
  proposal 不會直接變成 action；consumer 會撤銷成 `WATCH`／未知並留下 why／why-not。
- Portfolio 的人工持倉 `default:<code>` 與 Paper identity
  `paper:<portfolio>:<code>:entry-...` 不以股票代號猜配。無 exact identity 時，人工表
  顯示 `觀察／未知`／`未精確對應`；Paper projection 在獨立唯讀區塊呈現。
- Portfolio 不使用人工持倉的價格日期決定 Paper scope；只傳一日 freshness gate，
  因而舊 receipt 不會被標成當前有效建議。

## 測試證據

### 新增 read service／caller／identity 測試

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_position_health_transition_read_service.py -q -o addopts=
```

結果：`15 passed`。

涵蓋：

- 真實 evaluator source provider → receipt → read service 的 `HOLD`、
  `REDUCE_CANDIDATE`、`EXIT_CANDIDATE`。
- missing receipt、corrupt result hash、future available time、stale requested date、
  stale `max_age_days`、identity scope mismatch、cohort scope mismatch、row source
  snapshot mismatch。
- 使用 `tmp_path` 內由 `build_twse_calendar_cache` 產生的 hash-bound calendar fixture；
  不依賴 repository 未追蹤或會更新的 `output` calendar cache。
- 真實 `PortfolioService` 產生 `default:2330`，並證明不會誤套
  `paper:2330:entry-20260901`；Paper row 仍在獨立 projection table 可見。
- `WorkbenchSourceService.inspect` 真實 refresh caller 讀取同一份 typed projection。

### UI／型別／語法

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_portfolio_view.py tests/test_ui_qt_portfolio_condition_monitor.py tests/test_position_health_transition_read_service.py -q -o addopts=
.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
.\.venv\Scripts\python.exe -m py_compile app_module\decision_presentation.py app_module\position_health_transition_read_service.py app_module\position_health_transition_evaluator.py app_module\workbench_dtos.py app_module\workbench_source_service.py ui_qt\models\workbench_table_models.py ui_qt\views\portfolio_view.py ui_qt\views\workbench_view.py scripts\qa_position_health_increment_1_visual.py tests\test_position_health_transition_read_service.py
```

目前結果：Portfolio／health focused suite `42 passed`；Workbench／evaluator focused
suite `66 passed`；source-provider suite `16 passed`；mypy `Success: no issues found`；
changed Python files 全數通過 `py_compile`。pytest 僅有既有 `.pytest_cache` 權限 warning，
不影響測試結果。

### 受控 real Qt presentation QA

```powershell
.\.venv\Scripts\python.exe scripts\qa_position_health_increment_1_visual.py --output-dir <isolated-evidence-dir>
```

結果：`visual_qa_status=passed`、positive evaluator/read-service row 1 筆，Portfolio
與 Workbench positive `rowCount=1` 且 Portfolio table 確實綁定 typed model；missing
receipt 兩個 consumer 都是 `source=missing／quality=unknown`、無可安全呈現列；選取
positive row 後，兩頁詳情都可讀到 exact identity 與來源 hash。
Runner 以正式 CJK font／Midnight theme、UTF-8 stdout、`tmp` source fixture 運行，
只輸出四張 isolated panel PNG，process bounded exit `0`。

### Update tab mandatory QA

`scripts\qa_validate_update_tab.py`：`Passed 25 / Failed 0 / Skipped 4`，process
exit `0`。

Mandatory Update UI suite `tests/test_ui_qt_update_view_workbench.py` 為 `84 passed`。
受控 Qt panel evidence 的實際輸出為：

- `<USER_HOME>\.codex\visualizations\2026\09\15\01a0a414-bafb-79a0-aeff-1c462f5cded6\position-health-qt\portfolio_verified.png`
- `<USER_HOME>\.codex\visualizations\2026\09\15\01a0a414-bafb-79a0-aeff-1c462f5cded6\position-health-qt\portfolio_degraded.png`
- `<USER_HOME>\.codex\visualizations\2026\09\15\01a0a414-bafb-79a0-aeff-1c462f5cded6\position-health-qt\workbench_verified.png`
- `<USER_HOME>\.codex\visualizations\2026\09\15\01a0a414-bafb-79a0-aeff-1c462f5cded6\position-health-qt\workbench_degraded.png`

## 獨立唯讀 smoke 結論

缺 receipt 的 smoke 會回傳 `status=blocked`、`source_status=missing`、空 positions 與
`position_health_receipt_unavailable`，不會回報假成功；hash 竄改會回傳 blocked 且不
提供 positive projection。freshness 過期時會回傳 `status=stale`，保留診斷但將 row
action 撤銷為 `WATCH`。

## 保留事項

目前 Paper lane 仍受真實 snapshot／entry lineage／human thesis／PIT condition／
Decimal metrics 的實際 coverage 限制；來源缺口顯示 degraded／unknown 是資料品質結論，
不是 transition 完成。後續若要接 `user_declared`、正式 approval 或 broker execution，
必須另經對應 gate，不在本增量內擴張。
