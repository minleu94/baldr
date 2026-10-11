> **歷史狀態導讀（2026-10-10）**：本文的 `READY_FOR_REVIEW` 與相鄰依賴狀態只代表 R003 implementation slice 當時狀態；R031 後續將 R003 列為 `ACCEPTED_WITH_BOUNDED_SCOPE`。原 characterization gap 與 Portfolio P2 source-navigation identity 等限制保留；目前 task disposition 看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)與[final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。

# R003 實作報告

- TASK：R003 — terminal outcome、取消與 hidden-state characterization
- IMPLEMENTER：LUNA（依 SOL `CHANGES_REQUIRED` 進行 R003 範圍內重工）
- RESULT：characterization-only；未修改 production、receipt、repository 或其他 R-task。

## 基線與範圍

- 起始 HEAD：`391b057c92037ec7a19cab2bf951d6029d29b020`，branch `dev`。
- 結束 HEAD：`391b057c92037ec7a19cab2bf951d6029d29b020`，未建立 commit。
- 起始 dirty baseline（`git status --short`）：

  ```text
   M data_module/__init__.py
   M docs/00_core/DOCUMENTATION_INDEX.md
   M docs/01_architecture/README.md
   M docs/01_architecture/target_system_architecture.md
   M tests/test_task_loop_03_contract.py
  ?? =
  ?? data_module/contracts/
  ?? docs/01_architecture/target_architecture_2026_09_22/
  ?? docs/06_qa/REFACTOR_BASELINE_R001_20260922.md
  ?? docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md
  ?? tests/test_data_market_contracts.py
  ?? tests/test_r004_recommendation_persistence_characterization.py
  ?? tests/test_recommendation_execution_state_characterization.py
  ?? tests/test_recommendation_refactor_characterization.py
  ?? tests/test_recommendation_replay_characterization.py
  ?? tests/test_refactor_ml_compatibility_baseline.py
  ```

- 結束 dirty baseline：`git status --short` 路徑集合與上述起始集合相同；R003 測試與報告仍位於原先未追蹤的 target-architecture 目錄中。沒有新增、清理或覆寫其他 baseline entries。
- 起始 R003 檔案 SHA-256 與 rework packet 基線一致：測試 `58570C03BBCE9EFE4FE3DEB6298184C48DCF0674D6573FC1F8A98E83D3452E10`；本報告 `36E6F55896854BB1A05EA229D0D9289B7DB9437949108D517E81881C3B7C12C0`。
- 更新後測試檔 SHA-256：`30C06A571301E732B60840AB2C73E2C17F0DC6488F606272082EF4CAF0B3AA11`。報告自身的最終 SHA-256 在交接訊息提供，避免自我參照。
- 依賴證據：R001 baseline 記錄 Recommendation service 的 `last_*` instance fields 及 UI/service caller；R002 implementation report 記錄 64 passed、`READY_FOR_REVIEW`；R007 implementation report 記錄 13 passed、`READY_FOR_REVIEW`。這些是本輪閱讀的依賴／相鄰切片證據，未重跑其測試。
- 僅修改以下兩個 R003 檔案；其他起始 dirty paths 保留：
  - `tests/test_recommendation_execution_state_characterization.py`
  - `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md`

## 事件矩陣與觀察

| 案例 | 可判定事件序列與 oracle | 現況判讀 |
|---|---|---|
| completed-nonempty | service 單次呼叫回傳一筆 → `TaskWorker.finished([result])`；`error`、`cancelled` 均未送出。實際 view callback 顯示已完成。 | 可與其他終端事件區分。 |
| completed-empty | service 單次呼叫回傳 `[]` → `TaskWorker.finished([])`；`error`、`cancelled` 均未送出。實際 view callback 標示「已完成」及目前沒有符合條件的股票。 | 空結果是合法完成，不能以 `[]` 自身代表失敗或取消。 |
| validation rejection | 實際 `_execute_recommendation` 驗證失敗 → UI warning → 返回；service 呼叫數為 0，沒有建立 worker。 | 這是 worker 啟動前的拒絕，不能由 `validation_error()` 字串單獨當成 worker terminal event。 |
| pre-start cancellation | request callback 在 service 呼叫前回報取消 → 回傳 `[]`、service 呼叫數為 0，進度精確為 `(讀取股票數據…,10)`、`(已取消：推薦分析尚未開始,10)`。 | 與 completed-empty 的 `finished([])` 及 service 執行後取消的 90% checkpoint 分開。 |
| raised failure | service 呼叫並在測試 receipt marker 後 raise → `TaskWorker.error`；沒有 `finished` 或 `cancelled`。實際 view error callback 設為失敗。 | worker signal 能把失敗和空完成分開。 |
| cooperative cancellation | worker 執行中的 service 收到取消請求；測試 receipt marker 在 service 返回前出現 → request 於 service 返回後觀察到取消 → `TaskWorker.cancelled`；沒有 `finished` 或 `error`。實際 view callback 標示取消。 | `ProgressTaskWorker` 在取消後抑制後續進度；直接 request spy 仍觀察到取消 checkpoint `(「已取消：推薦分析結果未套用」, 90)`。 |
| progress | 詳細模式依序收到 `(讀取股票數據…,10)`、`(建立分析範圍…,25)`、`(執行推薦規則…,35)`、service progress、`(整理推薦結果…,90)`、`(分析完成,100)`。 | callback 形狀與順序已有 oracle。 |
| A/B shared state 與 late callback | A worker 完成；同一 service 的 B invocation 開始並把 shared `last_*` 指向 B；延後的 A callback 經實際 `RecommendationView._on_recommendation_finished` 套用。 | A 的舊 callback 會把已顯示的 last-good model/result 換成 A；service hidden state 仍是 B。這是現況 gap，不是預期目標行為。callback 簽章沒有 request id。 |
| 新請求清除 last-good | 以實際 `_execute_recommendation` 搭配可控 worker probe 啟動有效請求；在 `worker.start()` 時檢查 view。 | 啟動 worker 前已呼叫 `results_table.setModel(None)`、清空 detail、設 `current_recommendations=None`、`current_result_id=''`；既有 last-good 已先清除。 |
| actual service A/B state | 同一實際 `RecommendationService` instance 先後跑 A、B 的空資料 invocation；A 的回傳是 `[]`，B 後 `last_run_context` 保存 B config。 | list result 不攜帶 invocation context；延後讀 A 只能讀 service 最新的 B state。測試使用空 provider，不讀正式資料或載入模型。 |
| worker lifecycle | barrier 讓 worker 保持執行 → `deleteLater()` 設為 deferred 且 worker 留在 managed registry → 放行、native thread finished → registry 移除、QObject `destroyed` signal 送達。 | deferred close/native completion 的可觀察生命週期已覆蓋。 |
| nested aliases | 建立 request 後修改外部 nested config → request/service 看到變更；`execute()` 回傳物與 service 持有同一 list，兩端後續 nested mutation 互相可見。 | 現況違反 INV-08 的 input/output alias 證據；未加入 freeze/copy 行為。 |

## 現況 gaps 與後續要求（2026-09-22 R003 snapshot）

> 本節的 gap 與後續要求記錄 R003 characterization 當時所見；狀態均為 2026-09-22 snapshot，不表示目前系統行為。R003 current bounded disposition 見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。

- `RecommendationService` 仍以同一 instance 的 `last_*` 欄位暴露最後一次執行資料，執行回傳的 list 不含其完整 context。A/B delayed-read 測試證明 invocation identity 和 hidden state 可分離；R008/R011 依核准架構建立 execution result 時須把 identity/context 隨該次結果綁定（INV-07、INV-10）。
- 實際 `_execute_recommendation` 在 worker 啟動前就清除 table model、detail、`current_recommendations` 與 `current_result_id`，所以新請求尚未成功時 last-good 已不可用；實際 finished callback 也沒有 request correlation 欄位，測試把 active request 標記為 B 時，延遲 A callback 仍覆蓋目前顯示的 last-good 結果。後續核准的 UI/canonical execution 遷移需保留 last-good，並用 request identity 忽略 stale callback（INV-09、INV-16）。本 task 僅記錄 gap。
- Request 對輸入 config 與 service 回傳物皆保留 nested mutable alias。需由後續 execution capture/contract 實作深度封存並以兩側 mutation oracle 驗證（INV-08）。
- Worker signal 目前能區分 completed、failed、cancelled；validation rejection 在 worker 建立前發生。統一 typed terminal contract 尚未存在，屬後續 R008/R011 工作，不在此新增 status class。
- receipt 時序使用 test-only marker：取消與失敗案例只驗證 marker 先於 worker terminal signal 的可見序列，沒有載入模型、呼叫正式 receipt writer 或寫 repository。實際模型/provider 的 receipt failure/cancel timing 仍需在不違反 R003 限制的後續專項驗證。
- changed files 僅有上列兩個 R003 檔案；production 零修改，未調整數值、推薦語意、持久化或 replay。

## 驗證

V-EXEC 聚焦測試（新 characterization、execution coordinator、直接 TaskWorker、shutdown lifecycle 與現有 worker stale-callback seam）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py tests/test_ui_qt_task_worker.py tests/test_ui_qt_shutdown_coordinator.py "tests/test_ui_qt_portfolio_view.py::test_portfolio_stale_worker_callback_cannot_replace_new_generation" -q -o addopts= -p no:cacheprovider
```

結果：`41 passed in 1.67s`。

新增檔單獨重跑：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_state_characterization.py -q -o addopts= -p no:cacheprovider
```

結果：`13 passed in 0.83s`。

Python 語法檢查：

```powershell
.\.venv\Scripts\python.exe -m py_compile tests\test_recommendation_execution_state_characterization.py
```

結果：exit 0。

空白差異檢查：

```powershell
git diff --check
git diff --no-index --check -- NUL tests/test_recommendation_execution_state_characterization.py
git diff --no-index --check -- NUL docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md
```

結果：`git diff --check` exit 0，無 whitespace error；Git 對既有 tracked dirty files 輸出 LF/CRLF normalization warnings。兩個 R003 檔案在起始 dirty baseline 已是未追蹤檔，`--no-index` 對空 `NUL` 比較均無 whitespace diagnostics；exit 1 僅表示檔案與空輸入有差異，並有各自 LF/CRLF normalization warning。

## 相容性、回滾與判定

- 行為相容性：只觀察現況；沒有修改 production 行為。
- 數值、持久化、replay：未改；沒有正式資料/store 寫入。
- ML：只使用測試用 receipt marker，未載入或訓練模型。
- Rollback：僅還原上述兩個 R003 檔案至起始 packet SHA-256；不回復其他 dirty paths。
- 起始與結束 HEAD 相同；未 stage、commit 或 push。

IMPLEMENTATION_STATUS: READY_FOR_REVIEW
