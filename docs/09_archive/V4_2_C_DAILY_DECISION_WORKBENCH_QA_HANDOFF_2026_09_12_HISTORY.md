# V4.2 C 線：每日投資決策工作台 QA handoff（2026-09-12）

## 目的與範圍

本紀錄涵蓋 V4.2 C 線第二輪：把市場總覽、產業／市場探索、關鍵股研究、觀察清單與持倉覆盤整理成可操作的單一路徑，並統一四個決策畫面的證據呈現與窄版／鍵盤可用性。

本輪只修改 UI、跨頁研究 context、共用 read model adapter 與測試／文件；不修改正式資料、策略、回測、持倉計算或交易服務。變更在 detached worktree 以未提交 diff 交給主線整合，沒有在本 handoff 建立 commit。

## 驗收對照

| 驗收項目 | 實作／判讀 |
|---|---|
| 單一路徑 | Workbench 顯示 `市場總覽 → 產業／市場探索 → 關鍵股研究 → 觀察清單 → 持倉覆盤`；按鈕導向既有 workspace，個股研究由選取的股票 context 開啟。 |
| 導覽 context | `ResearchStockContextDTO` 保留股票、名稱、決策日、資料日、source id／kind／label、來源 workspace 與返回來源；無來源時研究報告不顯示虛假的返回控制。 |
| 欄位分離 | `DecisionPresentationService`／`DecisionPresentationDTO` 分開保存 ranking score、ranking percentile、calibrated probability、after-cost profit probability、action suitability、evidence status／confidence、sample size、horizon、理由、風險、失效條件、權重、日期與 source trace。 |
| fail-closed | 缺值顯示未知／不可用（研究中）；非法或超出 0–10000 bp 的機率不被採用；不從 ranking score 推導 probability，不由 UI 補算權重 gap。 |
| 觀察清單 | 顯示研究／等待與既有分析的理由、風險、失效條件及 status／日期／source；缺分析資料維持 research／unknown。 |
| 持倉覆盤 | 以既有 condition monitor 的 `valid`／`warning`／`invalid` 映射為持有／減碼候選／退出候選，顯示成本與明確提供的 target／current／gap bp；不自動調倉或平倉。 |
| Advice | Workbench 列選取後以同一 formatter 顯示動作、排名、兩種機率、信心、樣本、期間、理由、風險、失效條件、日期與來源；缺資料不變成 0 或可交易結論。 |
| 可用性 | 表格單列選取、禁止編輯、`StrongFocus`、Tab 導覽、交替列色與窄版水平捲動；長證據放在詳情區，避免主表過密。 |
| 安全邊界 | 所有新入口維持 read-only；不寫 DB、不更新正式資料、不呼叫 broker、不自動下單、不套用 lifecycle。 |

## 驗證命令與結果

以下命令使用已配置的共用 Python runtime：`C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe`。此 worktree 沒有另建 `.venv`，不影響程式碼與測試結果。

| 命令 | 結果 |
|---|---|
| `python -m pytest tests/test_decision_presentation.py tests/test_ui_qt_workbench_view.py tests/test_ui_qt_decision_desk_view.py tests/test_ui_qt_portfolio_view.py tests/test_ui_qt_stock_research_navigation.py -q -o addopts=` | 通過；86 passed。 |
| 受影響的 8 個 adapter／Qt UI 測試檔合併執行 | 通過；184 passed。 |
| `python -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 通過；81 passed。 |
| `python scripts/qa_validate_update_tab.py` | 通過；25 項通過、4 項受控跳過，報告寫入隔離 QA output。 |
| `python -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` | 通過；594 source files，無 issues。 |
| `python -m py_compile <本輪修改的 Python 檔案>` | 通過。 |
| `python scripts/quant_guard_linter.py` | 通過 float boundary／look-ahead checks；本輪未新增金融核心裸 `float` 計算。 |
| `git diff --check` | 通過；僅有 Windows 換行格式提示。 |

## 人工／視覺驗證限制

- 本輪有 Qt offscreen／widget regression tests，但沒有宣稱 Windows 前景焦點、實體顯示器 150%／200% 縮放、screen reader 或真人鍵盤操作已完成。
- 研究報告、觀察清單與持倉的真正資料品質仍取決於上游 DTO；畫面顯示 unknown／research 是資料缺口的正確結果，不是證據已通過。
- `RecommendationAdviceDTO`／`PortfolioAdviceDTO` 目前只有在上游明確帶有對應欄位時才會提供校準／成本後機率；adapter 不會猜測或從既有 score 轉換。

## 整合與回復

主線整合前請先檢查 `git diff` 與 `git status`，確認只納入本輪列出的 UI、adapter、測試與文件。若整合後需回復，應由主線依檔案逐項撤回本輪 diff；不要動正式 `DATA_ROOT`、正式 SQLite、原始 CSV 或其他 agent 的未提交變更。

整合後建議再次執行本文件的五個待驗證命令，並開啟 `docs/07_guides/APPLICATION_MANUAL.md` 的 V4.2 C 線章節，人工確認：

1. 路徑按鈕在寬版與窄版均可辨識，個股研究有正確 source／日期／返回狀態。
2. 選取 Advice、觀察清單與持倉列後，排名、兩種機率、信心、樣本、期間與 action 不互相混用。
3. 缺來源或缺值時仍是 unknown／research，且畫面沒有新增 order、apply、rebalance 或 lifecycle 控制。
