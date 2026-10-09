# Daily Investment Journey QA — 2026-09-14

本卡只記錄 Workbench 的唯讀每日決策旅程增量，不代表 V5、V4 formal 或投資有效性 closeout。

## 真實資料觀察

- 以 `WorkbenchSourceService.inspect(decision_date=2026-09-14)` 讀取已配置正式來源；沒有執行推薦、forward 計算、learning runner 或任何資料寫入。
- 今日候選為 `1528`；recommendation snapshot cohort requested `200`、eligible `1`、degraded `199`、missing `0`，因此首屏標為資料需複核的研究候選，不是 Advice 或交易指令。
- Evidence 僅沿用排程 forward receipt 的 `recommendation_included`、`2026-05-17..2026-09-14`、`require_cohort_identity=true`、`max_events=2500` 與 `5/10/20/60` 日窗口：完整 identity 事件 `7` 件（今日 `1` 件），不完整 identity `215` 件跳過；outcome `28` 筆，四個窗口各 `7` 筆，`0` 已成熟、`7` 待成熟、`0` 缺件。
- Learning receipt 為 `retain_current`；candidate／challenger 與 active pointer 分開投影，active pointer 仍為 `rule_only`，自然成熟樣本為 `0`，`shadow_only=true`、`formal_order_allowed=false`。這些狀態只作邊界揭露，不升格為 current champion。

## UI 與下鑽驗證

- `Research Workflow` 預設收合，讓每日結論、候選與下一步成為首屏焦點。
- 首屏 headline 與五張卡只顯示繁中投資語意；完整 result/source/event identity、hash、scope 分母與 learning receipt 欄位須按「查看每日來源詳情」才展開。
- 候選按鈕保留股票代號、決策日、資料日與 result/source identity，直接呼叫既有 `StockResearchReport` 路由；不自動新增觀察清單。觀察清單與證據頁仍是既有工作區入口。
- `industry_indices` 來源若出現槓桿／反向名稱，首屏只標示市場指數代理與缺產業分類，不宣稱真實產業領先／落後。

## 失敗邊界與 capture

- `daily_investment_journey_read_failure_20260914.png` 是由真實 dashboard 衍生、明確注入 `status=read_failure` 的受控 UI fixture，不是正式來源當日讀取失敗的事實宣告。
- `daily_investment_journey_real_20260914.png` 是同一輪正式來源唯讀讀取後的 real capture；兩者內容與 SHA-256 不同，來源、預期狀態與 hash 以 `daily_investment_journey_capture_manifest_20260914.json` 為準。

## 尚未完成項

- 真正的 PIT 產業分類映射與可比基準強弱尚未完成；目前不能把代理指數排序當成真實產業結論。
- typed verifier 核對的 natural authority receipt 尚未形成；`available`、hash、evidence kind、shadow label 或 runner completed 都不能授予自然驗證權威。
- Journal、Portfolio ledger、Evidence outcome 與完整 decision continuity 尚未串成單一可回溯結果鏈；本輪只完成候選唯讀 identity 與既有個股研究下鑽。

## 驗證結果

- `pytest tests/test_daily_investment_journey.py tests/test_ui_qt_daily_journey.py tests/test_workbench_source_service.py tests/test_ui_qt_workbench_view.py tests/test_workbench_read_only_boundary.py -q -o addopts=`：`48 passed`。
- `pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=`：`81 passed`。
- `scripts/qa_validate_update_tab.py`：`25 passed / 0 failed / 4 skipped`。
- focused mypy（本輪 6 個 source files）：通過；整合 full mypy 當時為 `Found 12 errors in 5 files`，仍被其他 agent 未提交變更中的 5 個 `app_module`／`ml_module` 檔案型別錯誤阻擋，未在本輪修改那些檔案。
- 變更檔 `py_compile`：通過；`git diff --check`：通過（僅 Git 的 CRLF 轉換提示）。
