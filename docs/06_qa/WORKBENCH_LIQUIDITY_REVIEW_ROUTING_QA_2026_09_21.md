# Workbench 低流動性提示分流 QA（2026-09-21）

## 目的與範圍

本次修正只調整既有 `DecisionDeskSnapshot.risk_prompts` 在 Workbench 的唯讀呈現路由：

- `category=liquidity|weakness` 且 `source=relative_strength_liquidity` 各聚合成一筆背景證據列。
- portfolio、watchlist、continuity、readiness 的明確人工項目仍進入人工佇列。
- portfolio/watchlist prompt 只覆蓋部分 section 代號時，未覆蓋代號仍以「其餘」人工項目呈現。
- 已知 `market_context/market_regime` 與 `fundamental_diagnostic/fundamental` 維持逐項風險提示；其他無法辨識的 category/source 保留在背景診斷與單一 action diagnostics。

本 slice 不改上游低流動性門檻、策略計算、snapshot、SQLite、排程或正式 writer。Workbench 仍是 read-only DTO 呈現。

## 正式唯讀觀測

正式 Daily Decision snapshot 的唯讀觀測識別如下：

| 欄位 | 觀測值 |
| --- | --- |
| snapshot id | `dds_290832656f329969` |
| snapshot hash | `sha256:290832656f329969a127b0c269f6ea1e3efc07fc1b289accf5b758c77c4e578a` |
| decision date | `2026-09-21` |
| ranked / skipped | `1962 / 26` |
| low-liquidity prompts | `1121` |
| risk prompts | `1134`（liquidity `1121`、weakness `10`、portfolio alert `3`） |
| relative-strength metadata | 最近 20 筆觀測；`min_avg_turnover=20,000,000` |

低流動性數值是上游以收盤價乘成交股數、取最近 20 筆觀測得到的估算平均每日成交金額；這份 Workbench 修正沒有重算或改變該值。相鄰交易日觀測到低流動性數量約 `1114–1125`，未觀察到當日數量突增；本修正處理的是 projection 分流，不代表完整流動性資料品質驗收。

正式 snapshot 的原始資料在本 slice 僅作既有 read-only evidence；沒有重新執行 writer、recalc、snapshot 或 DB 更新。

以同一個正式 snapshot 做的純唯讀 composer readback（2026-09-21 12:31:39 工具記錄）結果如下：

- `risk_prompt_count=1134`；review `4` 筆（watchlist `1`、portfolio `3`），action `4` 筆（watchlist `1`、portfolio `3`）。
- 背景 batch `2` 筆：liquidity `1121`、weakness `10`；兩者均以 `daily_decision` 作為下鑽目標。
- portfolio section 保留 `2382, 3207, 9935` 三個代號；watchlist section 保留 `1721, 1560` 兩個代號。
- readback 使用 `DecisionDeskSnapshotRepository(read_only=True)` 與既有 `dds_290832656f329969`，hash 為上表值；access boundary 仍為 `writes_allowed=false`、`production_scheduler_allowed=false`。這是風險路由 readback，不是完整 source gate 驗收。

同一份 DTO 的 Qt offscreen 唯讀呈現也已核對：review table `4` 列、action table `4` 列，首頁 market card 顯示「待判讀 4 項」，`daily_decision` 導覽 callback 成功路由。首頁「背景提示」顯示 `5` 批，是把 Daily Decision source、portfolio quality、兩筆 market batch 與 replay missing 一併計入；其中本次低流動性分流本身仍只有兩筆 market batch。這次 offscreen check 沒有啟動 source service 或寫入資料。

## 隔離回歸

測試以 1121 筆 liquidity、2 筆 weakness、少數 portfolio/watchlist 與 1 筆未知 category/source 的 DTO fixture 驗證：

- review queue 不再產生 1121 筆低流動性人工列。
- liquidity／weakness 各只有一筆背景 batch，包含 count、code preview、`daily_decision` 下鑽與機器狀態分類。
- unknown prompt 保留 category、source、code、reason diagnostics，並產生單一 grouped action；沒有靜默遺失。
- watchlist `A/B` 只有 prompt `A` 時，`B` 同時存在於 review 與 action 的「其餘」列。
- 已知 market context／fundamental prompt 仍逐項可見，不被歸入 unknown。
- UI 在人工 queue 為空且有市場 batch 時，顯示機器狀態待處理與背景批次數；空 queue 不顯示為風險已確認。

執行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_workbench_read_only_composer.py tests\test_workbench_view_presenter.py tests\test_ui_qt_workbench_view.py -q -o addopts=
```

結果：`55 passed`；pytest 僅回報既有 `.pytest_cache` 無法寫入的環境 warning，未影響測試結果。

Workbench UI 契約測試：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts=
```

結果：`84 passed`；同一個 `.pytest_cache` permission warning，未影響測試結果。

語法檢查：

```powershell
.\.venv\Scripts\python.exe -m py_compile app_module\workbench_read_only_composer.py ui_qt\views\workbench_presenter.py ui_qt\views\workbench_view.py tests\test_workbench_read_only_composer.py tests\test_workbench_view_presenter.py tests\test_ui_qt_workbench_view.py
```

結果：exit code `0`。

型別與 Update Tab QA：

```powershell
.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
```

結果：mypy `Success: no issues found in 636 source files`；Update Tab QA `25 passed / 0 failed / 4 skipped`。4 個 skip 是刻意隔離的實際下載／全量合併操作：`update_daily_Execution`、`update_market_Execution`、`update_industry_Execution` 避免下載大量資料，`merge_daily_data_Execution` 避免修改資料；完整報告位於 `output/qa/update_tab/VALIDATION_REPORT.md`。

## 邊界

這些測試證明的是 Workbench DTO 的分類與呈現一致性，不是正式 snapshot 重建或交易可用性驗證。背景 batch 的 count 不代表需要逐筆人工處理；portfolio/watchlist 的具體 action、source trace 與 reason 仍須依既有人工流程判讀。空人工佇列也不代表 source、Phase gate 或風險已通過。
