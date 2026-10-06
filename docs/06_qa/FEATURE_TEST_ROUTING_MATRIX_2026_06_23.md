# Feature-to-Test Routing Matrix (2026-06-23)

## 2026-10-06 label readiness測試路由

`tests/test_rule_research_label_readiness.py`與`tests/test_rule_research_label_readiness_cli.py`驗sealed source／全母體分母、版本政策、缺件／未成熟、固定時序界線、取消重試、跨method/source與新程序一致；連同既有forward/source/store/reader/benchmark及`test_ml_historical_contracts`／`test_ml_purged_walk_forward`回歸。深fixture用短user Temp；沒有UI變更、Native或fit驗收。fullmypy／changed compile／quant／diff與數字見[QA](UX22_LABEL_READINESS_20261006.md)。


## 2026-10-06 UX21 benchmark接線測試路由

`test_rule_research_benchmark_adapter`＋`test_rule_research_benchmark_integration`驗typed設定、source／basis／period／availability／pins與成本保存；既有`test_rule_research_forward_outcome`／`test_rule_research_forward_isolated`／`test_rule_research_forward_outcome_reader`／`test_rule_research_daily_owner`驗core、null相容與日報；`test_ui_qt_forward_outcome_receipt`／`test_ui_qt_parent_receipt_dialog`驗readonly顯示、cancel／retry／return／stale。deep parent使用短user Temp避免Windows260路徑超限。UI仍強制Workbench／validator／fullmypy、changed compile／quant。[公開市場唯讀與fixture分報](UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md)。

## 2026-10-06 UX08 同版保存圖表測試路由

新增`test_saved_stock_technical_chart`／`test_ui_qt_saved_stock_chart`；改動service先跑`test_stock_research_report_service`／`test_stock_research_chart_payload`／`test_stock_research_technical_history`／`test_stock_research_shared_feature_consumer`／`test_ui_qt_stock_research_report`，producer／repository／screener及parent capture／daily owner／forward isolated驗相容；rank bookmark flow／source recovery／navigation驗最新研究與來源返回。深parent fixture用短authorized Temp避免Windows路徑超限。UI後強制Workbench／update validator／完整mypy與changed Python compile、quant。[251案例去重及raw收據](UX08_SAVED_CHART_READBACK_20261006.md)。

## 2026-10-06 第一版有限工程封存路由

`scripts/qa_validate_first_version_release.py`重用F4 actual MainWindow隔離三程序，唯讀既有250次保存與當下容量；須保留原raw案例，不重跑producer／舊Native／已接受性能。context補驗使用`test_ui_qt_stock_research_navigation`／`test_stock_research_source_recovery`／`test_stock_research_ml_scope_context`／`test_research_bookmark_main_bridge`／`test_ui_qt_research_context_status`。MainWindow修改後仍強制Workbench／update validator／完整mypy；有限工程、完整UX與外部接受分界見[UX24收據](UX24_FIRST_VERSION_ENGINEERING_SEAL_20261006.md)。

> **Scope**: 本文件是 Testing / QA Agent 所使用的功能對應測試路由矩陣（Feature-to-Test Routing Matrix），定義六大高頻 UI 工作區之測試橋接、對照測試路徑與模式支援。
>
> **角色定義與權威來源**：
> - 本文件僅作為測試路由之知識庫與對照矩陣，不包含 Agent 角色與行為定義。
> - 完整與權威的 Agent 角色定位、職責與工作流程，請參見 [testing_qa_agent.md](../agents/testing_qa_agent.md)。

---

## 1. 測試路由基本原則

Testing / QA Agent 接收到功能驗證請求後，將其映射到系統的六大高頻 UI 工作區之一，並根據本矩陣決策測試模式與稽核需求：
- **Quick Mode**：僅包含執行時間短、無龐大外部/資料依賴、安全無副作用的測試。
- **Full Mode**：包含較重型的 UI 聯動、跨頁 workflow、多 Research Run 比較或較複雜的計算。
- **條件式資料稽核**：僅於涉及真實資料演算、回測正確性校驗、或判定 SQLite / CSV 欄位與資料新鮮度時，方條件式觸發 Data Audit Agent 支援；純 UI smoke / contract 測試則不予觸發。

---

## 2. 六大高頻 UI 功能測試路由矩陣

### 2.1 UpdateView / 資料更新頁

* **Direct Bridge 測試** (可立即執行)：
  * `tests/test_ui_qt_update_view_workbench.py` (id: `ui-update-workbench`)
  * `scripts/qa_validate_update_tab.py` (id: `qa-update-tab`)
* **Candidate UI 測試** (待進一步橋接)：
  * 無
* **Service Oracle 測試** (邏輯驗證)：
  * `tests/test_update_service_status.py`
* **Manual-only / 尚未自動化缺口**：
  * 真實向 TWSE/TPEX 抓取資料時的進度條顯示、長任務取消流程、SQLite 資料同步的對話框確認。
* **是否安全可跑 Quick**：
  * **是** (僅限 `ui-update-workbench` 單元測試；QA validation 腳本必須跑 `Full`，因為它會執行較完整的元件載入與模擬)。
* **資料稽核政策 (Data Audit Policy)**：
  * **條件式觸發 (Conditional)**。執行 UI 佈局 smoke 測試時不觸發；僅於需要比對 SQLite db schema 與 daily price CSV 整合狀態時，才需觸發 Data Audit。

---

### 2.2 Daily Decision Desk / 每日決策

* **Direct Bridge 測試** (可立即執行)：
  * `tests/test_ui_qt_decision_desk_view.py` (id: `ui-decision-desk`)
* **Candidate UI 測試** (待進一步橋接)：
  * `tests/test_ui_qt_decision_desk_main_integration.py`
* **Service Oracle 測試** (邏輯驗證)：
  * `tests/test_decision_desk_dashboard_service.py`
  * `tests/test_decision_desk_risk_prompt_service.py`
  * `tests/test_decision_desk_service.py`
  * `tests/test_decision_desk_ui_contract.py`
* **Manual-only / 尚未自動化缺口**：
  * 各種不同降級狀態（如籌碼缺失、指標過期）在 UI 上的視覺警示排版、Why Not 按鈕點擊後彈出說明的文字可讀性。
* **是否安全可跑 Quick**：
  * **是** (使用 `ui-decision-desk` 驗證元件狀態與 DTO binding)。
* **資料稽核政策 (Data Audit Policy)**：
  * **條件式觸發 (Conditional)**。純 UI smoke 測試不觸發；若需要核實 decision desk 警示所關聯 the watchlist risk 或持倉資料的真偽時才觸發。

---

### 2.3 Research Lab / 策略回測

* **Direct Bridge 測試** (可立即執行)：
  * `tests/test_ui_qt_research_workflow.py` (id: `ui-research-workflow`)
  * `tests/test_ui_qt_run_registry_compare.py` (id: `ui-run-registry-compare`)
* **Candidate UI 測試** (待進一步橋接)：
  * `tests/test_ui_qt_research_lab_mode_driven_ui.py`
  * `tests/test_ui_qt_research_lab_workbench_copy_text.py`
  * `tests/test_ui_qt_research_run_save.py`
* **Service Oracle 測試** (邏輯驗證)：
  * `tests/test_research_lab_mode_taxonomy.py`
  * `tests/test_research_result_presentation.py`
  * `tests/test_research_run_repository.py`
  * `tests/test_research_run_service.py`
* **Manual-only / 尚未自動化缺口**：
  * 回測進度條與 cancel 按鈕的執行緒安全退出、自訂策略參數滑桿的 resize 佈局是否會吃掉文字、Equity Curve 圖表的雙擊放大功能。
* **是否安全可跑 Quick**：
  * **否** (回測策略涉及繁重計算、並行運算與大量 SQLite I/O，建議限於 `Full` 模式跑橋接測試)。
* **資料稽核政策 (Data Audit Policy)**：
  * **條件式觸發 (Conditional)**。純 UI 佈局或回測頁面切換等 UI smoke 測試不需要觸發；僅於需要確認歷史價格完整性、回測邏輯正確性、或判定是否存在 look-ahead bias 時，才需觸發 Data Audit。

---

### 2.4 Market Regime / 市場觀察

* **Direct Bridge 測試** (可立即執行)：
  * `tests/test_ui_qt_market_regime_view.py` (id: `ui-market-regime-view`)
* **Candidate UI 測試** (待進一步橋接)：
  * 無
* **Service Oracle 測試** (邏輯驗證)：
  * `tests/test_walkforward_service.py` (包含 regime label & hysteresis 驗證)
* **Manual-only / 尚未自動化缺口**：
  * 規則匹配度 tooltip 是否與手冊規範的「不是勝率」一致、Regime 分類明細下拉的排版。
* **是否安全可跑 Quick**：
  * **否** (市場狀態判定需要完整的大盤指標與歷史收盤價，計算較繁重，應歸在 `Full` 模式)。
* **資料稽核政策 (Data Audit Policy)**：
  * **條件式觸發 (Conditional)**。UI smoke 測試不觸發；若要核實 Regime 計算數值的真實來源與一致性時才觸發。

---

### 2.5 Smart Money Flow / 主力流向

* **Direct Bridge 測試** (可立即執行)：
  * `tests/test_ui_qt_smart_money_flow_view.py` (id: `ui-smart-money-flow`)
* **Candidate UI 測試** (待進一步橋接)：
  * 無
* **Service Oracle 測試** (邏輯驗證)：
  * `tests/test_smart_money_semantic_service.py`
  * `tests/test_broker_branch_decode.py`
  * `tests/test_broker_flow_units.py`
* **Manual-only / 尚未自動化缺口**：
  * 點擊「下鑽詳細主力流向」與持倉/個股聯動的高亮、多日分點統計排序。
* **是否安全可跑 Quick**：
  * **否** (主力流向需讀取大量券商進出資料，磁碟 I/O 量大，應歸在 `Full` 模式)。
* **資料稽核政策 (Data Audit Policy)**：
  * **條件式觸發 (Conditional)**。主力流向之資料來源為 `broker_flow_dir` 目錄、SQLite `broker_flows` 資料表、以及券商分點基礎資料（非寫死單一 Parquet 解析）。當需要稽核這些分點資料之欄位完整性、主鍵約束以及 ETF 排除代號之 schema 一致性時，才需觸發 Data Audit。

---

### 2.6 Run Registry Compare / 策略比較

* **Direct Bridge 測試** (可立即執行)：
  * `tests/test_ui_qt_run_registry_compare.py` (id: `ui-run-registry-compare`)
* **Candidate UI 測試** (待進一步橋接)：
  * 無
* **Service Oracle 測試** (邏輯驗證)：
  * `tests/test_research_run_comparison_service.py`
* **Manual-only / 尚未自動化缺口**：
  * 橫向跨 run 參數對比、Normalized Equity 曲線 Matplotlib 渲染。
* **是否安全可跑 Quick**：
  * **否** (比較多組 Research Run 需要讀取並載入 SQLite Run metadata 與 Parquet 明細，應限於 `Full` 模式)。
* **資料稽核政策 (Data Audit Policy)**：
  * **從不觸發 (Never)** (純粹比較回測 Registry 數值，無額外外部資料稽核需求)。

---

## 3. 2026-07-13 System Integration 測試路由

| 範圍 | 路由 | 說明 |
|---|---|---|
| `tests/test_cross_workstream_system_integration.py` | slow E2E / environment | 依固定 A→C→E1→D→B→E2→F dependency order 驗證跨流契約；不放 Quick。 |
| `tests/test_verify_system_execution_blueprint.py` | governance / docs / tooling | 純 JSON verifier、malformed input 與 fail-closed contract；可獨立 focused 執行。 |
| `tests/test_full_app_healthcheck_test_inventory.py` | healthcheck-owned contract | 保護 inventory 完整性；新增測試必須先分類，不得以未登錄測試繞過 healthcheck。 |
| Broker latency、P0、PIT、market visibility、corporate action | service oracle / data-market | 需要真實資料判讀時才觸發 Data Audit；正式 DB 一律唯讀並比對 integrity。 |
| `ml/` focused unit tests | general unit / keep in pytest | 僅驗證 shadow contract、split、identity、drift 與 gate；不得宣稱 formal OOS 或 production。 |
| Smart Money async UI | candidate UI bridge | 驗證 loading、stale-result、error recovery 與 UI responsiveness；真實大量 broker I/O 留在 Full。 |

跨流失敗必須回到擁有該 contract 的 workstream 修正。整合 adapter／verifier 不得補缺值、把 `degraded` 改成 ready、放寬 source acceptance／ML promotion Gate，或用 fixture 折抵 forward evidence、real artifact 與人工／時間條件。


### 2026-10-06 UX21 actual source/store/daily

| 變更範圍 | 必跑 |
|---|---|
| current-observed source／atomic outcome／日報 | tests/test_rule_research_forward_isolated.py、test_rule_research_forward_outcome.py、test_rule_research_forward_outcome_reader.py、test_rule_research_observation_acceptance.py、test_rule_research_daily_owner.py |
| parent outcome receipt UI | tests/test_ui_qt_parent_receipt_dialog.py、test_ui_qt_forward_outcome_receipt.py；既有 Workbench、qa_validate_update_tab、全 source roots mypy |

實際來源及來源不可得驗證：[UX21收據](UX21_SOURCE_STORE_DAILY_20261006.md)。長Windows SHA路徑測試使用短Temp basetemp，原失敗保留。


### 2026-10-06 UX22 公平比較

focused：`test_rule_research_fair_comparison.py`／`test_rule_research_fair_comparison_cli.py`／`test_rule_research_fair_boundary.py`；regression：ML historical evaluator、feature builder、shadow DTO及label readiness。驗同源／固定target／共同分母、缺candidate與不可比較、未來資料拒絕、取消重試、JSON有界與新程序readback。未改UI，不重跑Native／效能或已接受工作臺gate；完整ML boundary原HEAD八條違例另記基線，不覆寫其他owner。詳UX22_FAIR_COMPARISON_20261006。


### UX23 隔離 shadow 工程狀態（2026-10-06）

Focused 路由：`tests/test_rule_research_shadow_acceptance.py`、`tests/test_rule_research_shadow_acceptance_cli.py`、`tests/test_rule_research_shadow_acceptance_boundary.py`；同源比較回歸走 `tests/test_rule_research_fair_comparison.py`。驗缺候選／模型版本與非法 lifecycle／失敗回退、明示停止、取消／來源重驗／殘件、duplicate／新程序 exact read。無 UI 改動，不重開已接受效能／Native gate；全 repo boundary 八條既有違例另報，不等於通過。證據見 [UX23 QA](UX23_SHADOW_ACCEPTANCE_20261006.md)。


### 2026-10-06 UX08 推薦保存圖表入口與驗證

[推薦writer→保存圖／精確表收據](UX08_RECOMMENDATION_SAVED_CHART_20261006.md)；Manual入口／步驟／參數／缺件／安全／排錯同步。新增pure helper15案例、writer／新程序／scheduled日期／來源失配及實際offscreen取消重試stale；既有execution、daily保存圖、read service／projection／技術歷史／shared consumer／研究畫面／scheduled日期，去重182相關案例。Workbench85／validator25+4skip／mypy819／compile／quant通過。UX08整項partial，viewport／CSV lanes未採納，不新增done。


### 2026-10-06 UX08 viewport UI測試路由

controller34及新增test_ui_qt_chart_viewport11案例，實際放大／平移／重設、缺價槽hover／None斷線、identity差異／unknown／empty／已淘汰控制、取消重試stale返回／保存新view全量／重畫fallback；既有研究UI／技術歷史／保存來源／投影／navigation，共115通過。擴充V5兩項以96ebcb33原UI重現基線失敗，不改無關summary。mandatoryWorkbench85→validator25/4skip→mypy820、compile／quant。[證據](UX08_VIEWPORT_INTEGRATION_20261006.md)。


### 2026-10-06 市場CSV consumer／CLI路由

test_market_csv_export62／test_export_market_csv_cli26／test_personal_data_paths104，共192通過；長UTF16／surrogate／no-op或錯名publish guard新10，深root CSV／CLI88再驗不增案例。包含preview不寫、來源pins接受／修訂拒絕、publication race／取消partial、來源bytes/stat不變。完整mypy821／CLI targeted3與compile4；不改UI不重跑其gate，不修3個普通open COW長路徑問題，使用新短fixture全套過。[收據](MARKET_CSV_EXPORT_INTEGRATION_20261006.md)。
