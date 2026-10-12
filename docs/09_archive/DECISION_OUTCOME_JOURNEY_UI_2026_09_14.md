# Decision → Outcome Journey UI QA（2026-09-14）

> **歷史 UI／資料 QA（2026-10-10）：** 本文的正式資料筆數、效能數字、測試結果與「完整 UI mypy 有 7 errors」均是 2026-09-14 的證據快照，不代表目前資料量或 UI 缺陷狀態，也不表示完整產品驗收。現況看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)、[QA 導覽](../06_qa/README.md) 與 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

> **歷史 smoke 重跑界線（2026-10-11）：** 文中的 `RUN_DECISION_OUTCOME_JOURNEY_REAL_SMOKE=1` 命令是當日 opt-in 驗收收據；執行會讀取設定的正式 result／Evidence SQLite，並可依截圖環境變數寫入 QA 圖片。此歷史命令不授權目前重讀正式資料或產生 QA 輸出。

## 範圍

本切片把既有 `ResearchStockContextDTO.result_id` 帶入「個股研究報告」對話框，新增唯讀「決策 → 結果」分頁。畫面由 `DecisionOutcomeJourneyService` 建立 read model，不重算推薦、不寫 Journal／Portfolio、不建立交易。

主畫面摘要使用產品語言呈現：

- 5／10／20／60 個交易日分開顯示「連結狀態」與「結果狀態」。`已連結` 不等於 outcome 已成熟。
- `insufficient_future_data` 顯示「尚待結果成熟」；混合 horizon 有 conflict／ambiguous 時，衝突優先於 pending 顯示。
- 缺少 `result_id` 明示「未連結」，不以同股同日猜測來源；完整 result identity、candidate key、provider、snapshot 與策略設定收在預設收合的技術詳情。
- Evidence 只用 exact `(result_id, stock_code)` candidate key；既有 Journal 依 result root 或精確 ledger key 分別標示共用／個股範圍；研究前瞻報酬與個人 Portfolio event 分開呈現。
- 讀取在 `TaskWorker` 背景執行，切股後用 request generation、股票代號與 `result_id` 丟棄過期回傳；失敗保留可操作畫面與「重新讀取」。

Evidence outcome 讀取由 exact event id 批次 query 支援：單一 read-only connection、明確 `BEGIN` 快照、900 bind 參數 chunk、只查授權 event id，不改 schema、index 或正式資料。

## 正式資料 smoke

來源：

- result：`D:\Min\Python\Project\FA_Data\output\recommendation\runs\scheduled_rec_20260914_051003.json`
- Evidence SQLite：`D:\Min\Python\Project\FA_Data\sqlite\twstock.db`（正式 WAL；以提升權限正常 `mode=ro` 讀取）
- 測試候選：`1528 恩德`

DTO 讀取結果為 582 筆 exact result evidence event、4 筆 maturity row（5／10／20／60）；本次來源四個 outcome 的實際 `outcome_status` 均為 `insufficient_future_data`，UI 依 DTO 顯示「待成熟（未有足夠未來資料）」；沒有將它轉成成交損益。

讀取前後 SQLite stat 均為 `size=3568181248`、`mtime_ns=1789389906888879900`，`SOURCE_STAT_UNCHANGED=True`。批次優化前的 threaded build 曾在逐 event outcome read 堆疊停留約 15.288 秒；批次後同 run/threaded 記錄約 7.631 秒。兩者不是受控 cache 公平 benchmark，數字只用來確認瓶頸與改善方向。

可讀 CJK 截圖：

- default 收合版（Git-ignored 本機輸出，未入庫；原位置：output/qa/decision_outcome_journey_20260914_default.png）
- 技術詳情展開版（Git-ignored 本機輸出，未入庫；原位置：output/qa/decision_outcome_journey_20260914_expanded.png）

## 驗證結果

```text
.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_decision_outcome_journey.py -q -o addopts=
7 passed, 1 skipped

.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_decision_outcome_journey.py tests/test_decision_outcome_journey.py tests/test_evidence_event_repository.py \
       tests/test_ui_qt_stock_research_report.py \
       tests/test_ui_qt_stock_research_navigation.py \
       tests/test_ui_qt_research_context_status.py \
       tests/test_ui_qt_daily_journey.py -q -o addopts=
44 passed, 1 skipped

.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=
81 passed

.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
exit 0（25 passed, 4 skipped）

.\.venv\Scripts\python.exe -m py_compile app_module\decision_outcome_journey.py app_module\evidence_event_repository.py ui_qt\widgets\decision_outcome_journey_widget.py ui_qt\views\stock_research_report_view.py ui_qt\main.py tests\test_decision_outcome_journey.py tests\test_evidence_event_repository.py tests\test_ui_qt_decision_outcome_journey.py
changed Python files：通過

.\.venv\Scripts\python.exe -m mypy --follow-imports=skip ui_qt\widgets\decision_outcome_journey_widget.py ui_qt\views\stock_research_report_view.py ui_qt\main.py app_module\evidence_event_repository.py app_module\decision_outcome_journey.py
Success: no issues found in 5 source files
```

正式 smoke 使用以下明確 opt-in 指令，避免一般測試在缺少正式資料時誤報成功：

```powershell
$env:RUN_DECISION_OUTCOME_JOURNEY_REAL_SMOKE='1'
$env:DECISION_OUTCOME_JOURNEY_SCREENSHOT_PATH='C:\Projects\PythonProjects\technical_analysis\output\qa\decision_outcome_journey_20260914_default.png'
.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_decision_outcome_journey.py::test_official_scheduled_result_renders_cjk_journey_screenshot_when_available -q -o addopts=
```

default 與展開版各自均為 `1 passed`；default smoke 約 8.42 秒、展開 smoke 約 8.24 秒。完整 UI mypy 目前仍有 7 個既有 A 線 `portfolio_store.py`／`journal_service.py` 錯誤（`flock`／`LOCK_*` 與 `DecisionContinuityRevision | None`），本切片 changed source 的 follow-imports=skip 檢查通過，未修改或掩蓋該外部問題。

## 非範圍與安全界線

本切片沒有觸碰 Workbench／evidence review 的另一條 UI hunk；沒有重建正式 DB、補建 index、修改 outcome、寫入 journal/trades、建立 broker order 或把 research forward return 宣稱為 personal execution PnL。`output/qa` 截圖是本機 QA 產物，不是正式資料來源。
