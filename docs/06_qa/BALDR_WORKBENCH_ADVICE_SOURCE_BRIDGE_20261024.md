# Workbench Advice 排程候選接線 — 2026-10-24

## 修改

`DailyInvestmentJourneyService` 保留既有 `build()` 回傳契約，另提供單次讀取的 read-model 伴隨結果。WorkBench Source 只在每日旅程確認當日候選、保存結果身份、日期與 cohort 後，才把同一份 verified read model 注入 `AdviceDashboardDTO`。

接線只呈現日期明確且品質非降級的 Professional 研究候選。來源策略為 `promoted` 時，這條 read path 因沒有採用 Gate、參數鎖定與揭露證據而不注入；同日帳戶持倉、現金或風險預算缺失時不提供配置判斷。舊日、未來、失配、空列或讀取失敗仍不會成為今日 Advice。後續補上阻擋結果 DTO：已把「等待 Advice DTO」的空白狀態改為帶有候選狀態／缺件警告的空 Advice DTO；缺資料日保留未知值，不用決策日代填。

## 驗證

- 初版受控 Windows Job 執行受改檔案與測試檔 `py_compile`，以及 `tests/test_workbench_source_service.py`、`tests/test_advice_composer.py`：**26 passed**；其後新增 source-service 正向整合案例，最終批次見下列 27 passed 收據。
- Workbench Source + Advice 既有 Job receipt SHA-256 `0a40ebafccc333104eef3fcdf564162b80ee07909f5f588518373f3b8ae4101e`；啟動前可用 RAM 30,002,061,312 bytes。阻擋結果 DTO 變更後最終 Job receipt SHA-256 `f1034269412b2d0eae1db3effcbf2257e676d34ffb77e1ae9f3ee6493e4105f9`；啟動前可用 RAM 31,143,718,912 bytes。後一 Job 的 limits read-back：kill-on-close 開啟、8 GiB 全 Job committed-memory、12 程序；自然結束、remaining PIDs 為 0、程序／Job handles 關閉、執行鎖釋放，無強制回收。
- 較廣 `tests/test_daily_investment_journey.py` 加上述兩測試檔，預設系統 temp 首輪：**44 passed、2 failed、4 errors**。canonical artifact fixture 的 2 個測試在 `os.rename` 回報 WinError 3，4 個 scheduled producer fixture 因 artifact 發布失敗而 setup error；未將其計為通過。
- 較早的工作區 temp 根批次為 **46 passed、4 errors**。四個錯誤都在 scheduled producer fixture setup，表面錯誤為 `ExecutionArtifactWriteError`。受控診斷確認 `os.rename` 發生時來源檔及兩側目錄都存在，惟目標路徑長 275 字元；這是 Windows 長路徑造成的 `WinError 3`，不是 producer／artifact writer 的產品錯誤。
- 補上 source-service 正向整合案例 `test_workbench_source_service_injects_exact_current_legacy_candidate_read`：用隔離 fixture 建立精確當日的已保存 legacy 推薦，呼叫真實 `WorkbenchSourceService.inspect`，核對結果身份／資料日進 Advice DTO、候選分類為 Professional Research Candidate、trace 帶 result ID，且沒有虛構配置列。合成 fixture 只證明服務接線，不是自然資料或正式來源證據。加入此案例後，受控 Windows Job 的 `tests/test_workbench_source_service.py`、`tests/test_advice_composer.py` 加受改檔案 `py_compile` 最終批次為 **27 passed**；receipt SHA-256 `f09d67a176bb9113e5d38d09f24ae3ae342dbea4e5fa5bb79887d9ee8b01dcec`。Job limits read-back：kill-on-close、8 GiB 全 Job committed-memory、12 程序；自然結束、remaining PIDs 0、handles 關閉、鎖釋放，無強制回收。
- 將 pytest basetemp 改為 repo 根下的短路徑 `.q/wbwide` 後，合併執行 `tests/test_daily_investment_journey.py`、`tests/test_workbench_source_service.py`、`tests/test_advice_composer.py`：**51 passed in 5.98s**，4 個 producer fixture errors 全部消失，無產品程式變更。Job receipt SHA-256 `AF255750E63815DB21D5C35ED463A8409CD7FF0D075C05E48B8B79CF6E7740E9`；啟動前可用 RAM 30,521,196,544 bytes；limits read-back 為 kill-on-close、8 GiB、12 程序；自然結束、remaining PIDs 0、handles 關閉、鎖釋放，未強制回收。原始 pytest 輸出：`51 passed in 5.98s`。
- `git -c core.fsmonitor=false diff --check`、Feature Map JSON、Feature Map `document_control check`、新增 QA 收據 `document_control check`：通過；Feature Map 已把 Source、Daily Journey、Advice Composer 與測試列入 Workbench 代表入口。
- Manual／Snapshot 的 `document_control check` 有既有外部引用無法驗證：`output/` Junction 被 sandbox 拒絕讀取（WinError 5），Snapshot 另有既存 `QA_RESULTS.md` 相對連結越界。這些均不是本輪新增連結；沒有更動既有外部路徑或 Junction。

## 範圍限制

此 QA 證明 source adapter 的候選接線契約與 Advice 分類測試，不證明自然排程有可用當日候選，也不解除正式來源、PIT、Gate 1、配置、自然 evidence、ML 或 Owner UAT。Promoted 策略目前刻意不透過這條 Workbench 讀取路徑注入。

## 2026-10-26 Advice 拒絕結果與來源追溯修正

AdviceComposer 在 `evidence_quality=MISSING` 時會產生無個股代號的 `NO_NEW_POSITION` 拒絕 DTO；原來源追溯硬編成 `RecommendationResultDTO`，會誤示有推薦原件。現在標記為 `AdviceComposer.refusal`。Workbench 對只有此拒絕列的 DTO 不渲染空白股票列，改顯「本次結論：暫不新增部位」、拒絕原因及來源警告，並說明這不是賣出／清倉指令；正常有股票代號的個股拒絕列仍留在建議表。

首次聚焦執行為 **78 passed／1 failed**；唯一失敗是同組未修改的 source-service 測試將診斷代碼當成完整字串比對，但現行診斷附帶了額外解碼失敗原因。保留詳細診斷，將測試調整為檢查穩定錯誤代碼前綴後，`tests/test_advice_composer.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_workbench_advice_contract.py`、`tests/test_workbench_source_service.py` 合計 **79 passed**。強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；5 個修改 Python 檔 `py_compile` 通過。收據位於工作區 scratch `quarterly-coverage-qa/advice-refusal-focused2.log`、`advice-workbench.log`、`advice-validator.log`、`advice-mypy.log`、`advice-pycompile.log`。

這項補正沒有新造推薦／配置、沒有改 portfolio 或策略計算，也沒有寫正式資料或 Gate／ML 狀態。它只讓既有缺證據拒絕答案忠實呈現。相同決策日帳戶持倉、現金及風險預算仍未載入，因此 Workbench 仍不給配置／加碼數字；Gate 1 的完整 Advice、自然資料驗收與 Owner UAT 尚未完成。

## 2026-10-26 Advice 保存來源 hash 追溯

canonical `RecommendationExecutionReadModel` 的 payload hash 只有在 query read model 明確標記 `canonical_payload_and_index_verified` 且格式為 `sha256:` 加 64 位小寫十六進位時，才加入每筆 Advice 的 `source_trace`。Workbench 將該項顯示為「已核驗保存結果 payload SHA-256」並保留摘要值，以便對照保存原件。沒有 hash、格式錯誤、legacy read-time hash 或 legacy trusted hash 都不會套用這個 canonical 已核驗標記；artifact 路徑不會輸出。

本切片新增 Advice DTO 來源追溯／round-trip、無效與 legacy hash 排除及 Workbench hash 標籤顯示案例。`tests/test_advice_composer.py` 與 `tests/test_ui_qt_workbench_view.py` 合計 **67 passed**；強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；修改的 4 個 Python 檔 `py_compile` 通過。受控 runner 日誌位於 scratch `quarterly-coverage-qa/advice-provenance-focused2.log`、`advice-provenance-workbench.log`、`advice-provenance-validator2.log` 與 `advice-provenance-mypy.log`。Validator 首次預設寫入 repo `output/qa` 時被沙箱拒絕，改用 `BALDR_UPDATE_TAB_QA_LOG_DIR` 導向授權 scratch 後通過；正式資料未觸碰。

此項只改善保存結果可追溯性，不代表資料來源正式接受、PIT 完整、Gate 1 通過或 ML 資格改變；原生 GUI 與 Owner UAT 未執行。

## 2026-10-26 Advice 必要欄位缺口提示

選取 Advice／研究候選列時，判讀卡會列出 Advice 契約中為空的必要欄位，以及回查推薦來源與策略設定的下一步。顯示只檢查 DTO 已有值，不計算、不補理由、不把空欄當安全結論；`why_not_reasons` 與 `risk_reasons` 的空集合可表示無對應 Policy 原因，因此不會被一律判為缺件。這只能讓缺漏更容易被看到，不能代替真實來源填值或正式樣本 100% completeness Gate。

新增 UI 案例驗證：`tests/test_advice_composer.py` 與 `tests/test_ui_qt_workbench_view.py` 合計 **68 passed**；強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；4 個修改 Python 檔 `py_compile` 通過。受控 runner 日誌位於 scratch `quarterly-coverage-qa/advice-completeness-focused.log`、`advice-completeness-workbench.log`、`advice-completeness-validator.log`、`advice-completeness-mypy.log` 與 `advice-completeness-pycompile.log`。原生 GUI 與 Owner UAT 未執行，Gate 1／來源／PIT／ML 狀態不變。
