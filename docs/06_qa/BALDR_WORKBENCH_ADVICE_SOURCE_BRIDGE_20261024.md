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

## 2026-10-26 Advice 帳戶來源導覽

當 Advice 原警告明確指出缺少同一決策日帳戶持倉／現金／風險預算時，Workbench 提供導覽按鈕直達 Portfolio「配置研究封存」來源選擇頁；Main 會切到該 tab，方便使用者明選策略 Paper 帳戶、版本與 Health 收據。此按鈕只改善下一步導覽，不把被選來源自動接入 Advice，也不授正式資格或推算 risk budget。專案任務初始化因 repo `output/` Junction 在此 sandbox 無法讀取，未建立 task.json；程式／測試工作繼續在既有 checkout 進行。

`tests/test_ui_qt_workbench_view.py` 與 `tests/test_ui_qt_workbench_portfolio_health_navigation.py` 合計 **66 passed**，涵蓋缺帳戶警告按鈕的顯示／callback，以及 Main 直達「配置研究封存」tab；強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；修改的 4 個 Python 檔 `py_compile` 通過。QA 收據 `document_control check` 通過；Manual／Snapshot 檢查仍只被既有 `output/` Junction 外部引用拒絕讀取擋住。受控 runner 日誌位於 scratch `quarterly-coverage-qa/paper-account-navigation-focused.log`、`paper-account-navigation-workbench.log`、`paper-account-navigation-validator.log`、`paper-account-navigation-mypy.log` 與 `paper-account-navigation-pycompile.log`。原生 GUI、Owner UAT 與真實 checkpoint 選取未執行；帳戶資料尚未接線，Gate 1／正式來源／PIT／ML 狀態不變。

## 2026-10-26 Paper snapshot 明確傳至 Workbench 背景顯示

完成 exact Paper scenario comparison 後，Portfolio「配置研究封存」才顯示傳送按鈕；送出時重核目前 checkpoint、候選集合、Paper namespace 與 snapshot identity。Main 將 typed comparison 暫存在 Workbench Source service 記憶體，切回 Workbench 並重新讀取。Dashboard 新增獨立 `paper_account_context` DTO，顯示來源日、可得時鐘、原始 account source hash、精確 NAV／現金與估值持倉。比較日必須等於 Workbench 決策日，snapshot 可得時間不得晚於比較時鐘，且比較時鐘不得晚於 Workbench 評估時鐘；過期或日期不符時只保留身份／診斷，所有金額與持倉清空。帳戶背景 DTO 不進 AdviceComposer、`portfolio_result` 或 risk budget，既有「無同日風險預算就不提供配置／加碼」警告保持不變。來源選取只存在本次 app session，不落盤。

聚焦的 Portfolio initial widget、Workbench source service 與 Workbench account navigation 共 **41 passed**；其中包含 Main 接收後返回 Workbench 並刷新、傳送只能由有效明選 comparison 觸發、候選更改會清除預覽，以及日期／來源讀取不符時不洩漏金額與持倉。強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；8 個修改 Python 檔 `py_compile` 通過。受控 runner 輸出在授權 scratch `quarterly-coverage-qa/account-context-focused-final3.log`、`account-context-workbench-final3.log`、`account-context-validator-final.log`、`account-context-mypy-final3.log`、`account-context-pycompile-final3.log`。首輪聚焦測試有 1 個新 UI 測試斷言 Qt 隱藏父視窗下的可見性語意錯誤；改為驗證按鈕明確 hidden state 後通過。

尚未重啟原生 GUI、未由 Owner 執行真實 checkpoint 選取／UAT，未證明當日自然 snapshot 可用。此切片只讓所選 Paper snapshot 能作可追溯背景呈現；不代表 Advice 輸入、風險預算、正式來源接受或 Gate／PIT／ML 通過。repo `output/` Junction 仍被 sandbox 拒讀，task 初始化未成功；既有 `qa/` 未追蹤目錄保留且未納入本次工作。

## 2026-10-26 Advice 缺欄列的 exact 保存來源回查

`RecommendationAdviceDTO` 新增 optional `source_result_id` 與 canonical payload `source_payload_sha256`。Workbench Source 只在每日旅程 status 為 `candidate`、每日 candidate result ID 與同次 typed recommendation read model 完全相同、股票屬目前候選且 Advice 決策日／資料日吻合時，才把結構化 source identity 綁到該列；canonical hash 只接受 integrity basis `canonical_payload_and_index_verified` 及格式有效的 `sha256:`。Legacy exact result 可有 ID 而沒有 canonical hash。refusal、缺 ID、日期／股票不同或來源無法核對時不綁定。

Workbench 只有在目前選取的 Advice／研究候選列其 ID 又與當日 daily evidence 完全相同、Dashboard fresh 且 Recommendation callback 可用時，顯示「回查這筆保存推薦結果」。按鈕觸發 Main 的 exact result reader；讀取失敗不改選別筆。dashboard stale、candidate 不再 current 或選取列改變時隱藏／拒絕回查。source ID 不由自由文字 source trace 解析；回查只看原件，不回填欄位或影響 Policy／Gate。

`tests/test_advice_composer.py`、`tests/test_workbench_advice_contract.py`、`tests/test_workbench_source_service.py` 與 `tests/test_ui_qt_workbench_view.py` 針對 Advice exact source 回查切片 **89 passed**；帳戶背景與來源回查兩切片最終合併聚焦 6 個測試檔 **119 passed**。強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；本次 10 個修改 Python 檔 `py_compile` 通過。受控 runner log 在授權 scratch `quarterly-coverage-qa/advice-source-return-focused-final.log`、`implementation-focused-final.log`、`implementation-workbench-required-final.log`、`implementation-validator-final.log`、`implementation-mypy-final.log`、`implementation-pycompile-final.log`。

這只縮短由缺欄提示回查來源的步驟，不補缺漏資料，不代表 Advice completeness 或 Gate 1／正式來源／PIT／ML 已通過。Owner UAT 與自然資料仍未驗證。

本次定向 `document_control check` 對 Feature Map、此 QA 收據與 Workbench 架構文件核對通過（12 features、3 個 link sources、0 errors）。另對 Manual／Snapshot 的廣域核對仍回報既有 `output/` Junction 外部引用無法讀取；未因此宣稱廣域文件檢查通過，也未更動該等引用。`git -c core.fsmonitor=false diff --check` 通過；僅有 Git 換行格式提示。

## 2026-10-25 Advice 校準期間與持有期間分離

來源語義審查確認 `RecommendationCalibrationProjection.horizon` 與 `RecommendationDTO.calibration_horizon` 是機率校準／證據範圍，不是策略預期持有期間。Advice DTO 與 Decision Presentation 現在各自保留 `calibration_horizon` 和 `holding_horizon`；Workbench 明確分開顯示「校準適用期間」和「策略持有期間」。持有期間欄位只接受明確的持有期間來源，不再把校準 horizon 填進去。策略沒有提供持有期時仍顯「未提供」，不猜測為 20 日持有建議。

回歸案例擴充 `tests/test_advice_composer.py` 與 `tests/test_decision_presentation.py`：驗證 20 trading days 顯示為校準適用期間，策略持有期間留空或使用明確來源值，兩者不互相挪用。Advice composer／DTO／presentation／Workbench view 聚焦套件 **114 passed**；強制 Workbench UI 回歸 **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；本輪所有 17 個修改 Python 檔 `py_compile` 通過。最終 scratch log 位於 `quarterly-coverage-qa/advice-horizon-semantics-final2-focused.log`、`advice-horizon-workbench-required-final.log`、`advice-horizon-validator-final.log`、`advice-horizon-mypy-final.log`、`advice-horizon-pycompile-final.log`。限定 QA 收據文件檢查 **12 features、1 個 link source、0 errors**；納入 Manual／Snapshot 後仍只因其既有 `output/` junction 連結讀取遭 WinError 5 拒絕而未通過，未改動該目錄。這是欄位語義與呈現修正；Gate／來源資格／PIT／ML 證據狀態不變，原生 GUI 與 Owner UAT 未執行。

## 2026-10-25 Workbench 首屏顯示今日策略建議

把既有「今日 Advice 與研究候選」完整唯讀面板移至 Workbench 總覽的標題後、預設首頁區域，不再藏在預設收合的完整工作台內；標題改為「今日策略建議」。既有正式 Advice、Professional 研究候選、空結果／refusal 原因、警告、選列判讀、精確保存結果回查與機率來源追跡均沿用原 DTO／回呼。配置列僅在有資料時標示為「可選配置研究（手動紀錄脈絡）」。Paper snapshot 背景只有明確傳入來源時顯示；缺少 Paper 帳戶上下文不會再占用 Advice 首屏或顯成前置缺件。

`tests/test_ui_qt_workbench_view.py` 增加 Advice 不在收合進階區、首屏標題及 Paper 上下文預設隱藏案例；並更新手動帳戶背景提示語意。聚焦 Workbench／Paper navigation／Advice composer **90 passed**；強制 Workbench UI 回歸 **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；18 個修改 Python 檔 `py_compile` 通過。第一次聚焦執行有一項舊測試仍要求顯示「風險預算仍未核對」，該斷言已依 Owner 確認的產品範圍改驗證「不改變策略建議」，最終聚焦通過。scratch log：`quarterly-coverage-qa/advice-first-workbench-focused.log`、`advice-first-workbench-focused-final.log`、`advice-first-workbench-required.log`、`advice-first-validator.log`、`advice-first-mypy.log`、`advice-first-pycompile.log`、`advice-first-doc-check.log`、`advice-first-doc-check-final.log`。定向 QA 收據與架構文件檢查 **12 features／2 link sources／0 errors**；納入 Manual／Snapshot 的較廣檢查只因既有 `output/` junction 連結被 WinError 5 拒讀而未通過，未改該目錄。Gate／資料資格／PIT／ML 狀態未改，原生 GUI 與 Owner UAT 未執行。

## 2026-10-25 核心 Advice 不依賴真實帳戶

依 Owner 對產品用途的澄清，核心流程是使用者手動維護持倉／交易紀錄，baldr 依市場資料、保存推薦、策略版本與可追溯證據提供策略研究建議；程式不連真實帳戶。Workbench 不再因帳戶／風險預算缺漏導覽至 Paper 帳戶選擇；`AdvicePolicy` 只以策略資格、資料品質及明確不可成交狀態決定策略 action，風險預算／現金／持倉數／目標權重不再阻擋策略 Advice。未知執行狀態保留 `UNKNOWN` 並附未核實風險；明確不可行才 `AVOID`。候選 Advice 警告說明手動記錄邊界與不輸出個人配置金額。Paper snapshot 背景資料保留為明確選用的唯讀研究參考，不屬策略建議 Gate。產品 Roadmap 與 6M Gate 1／可選 Gate 4 同步此邊界。

`tests/test_advice_policy.py`、`tests/test_advice_composer.py`、`tests/test_workbench_source_service.py`、`tests/test_workbench_advice_contract.py` 與 `tests/test_ui_qt_workbench_view.py` 合計 **106 passed**；強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；14 個修改 Python 檔 `py_compile` 通過。定向 `document_control check` 核對 12 features、5 link sources、0 errors；`git diff --check` 通過。scratch log：`quarterly-coverage-qa/strategy-policy-account-independence-focused-final2.log`、`strategy-policy-workbench-required.log`、`strategy-policy-validator.log`、`strategy-policy-mypy.log`、`strategy-policy-pycompile.log`、`strategy-policy-pycompile-tests-final.log`、`strategy-advice-doc-check-final4.log`。首次測試曾分別因 pytest basetemp 父目錄不存在，以及長 scratch 路徑造成 fixture setup error；改用短 `%TEMP%` basetemp 後，同一完整聚焦組通過。

較廣文件核對再納入 Manual／Snapshot 後，只回報這兩份文件既有 `output/` Junction 外部連結因 WinError 5 無法讀取；沒有其他結構／錨點錯誤。該 Junction 在目前 sandbox 不可讀，本次未改外部連結。沒有以 Owner 決策代替來源品質、策略採用、PIT、自然 evidence 或 ML Gate 證據。原生 GUI 與 Owner UAT 未執行。

## 2026-10-25 Advice 保存結果逐股證據呈現

Advice DTO 增加唯讀 `source_evidence` 欄位。AdviceComposer 只讀取與目前 Advice 同一個保存結果 read model 的 `screening_matrix_json`、`why_not_payload_json`、`liquidity_gate_payload_json`，依完全相同的股票代碼分組，並投影階段、狀態、資料品質與原理由碼；不投影分數數值、不從其他股票搬入排除理由。Advice DTO 缺少逐股來源列時會明示「不能據此推定沒有反證或風險」。Workbench 選取 Advice／候選後在判讀卡顯示此獨立區塊。來源證據不參與 AdvicePolicy，不改 action、排序或配置；手動持倉／Paper 背景仍為選用資料。缺少 thesis、失效條件、持有期間、PIT 或正式資格時仍保留缺漏。

回歸案例覆蓋 legacy 保存欄位與 canonical typed negative-evidence projection、同股才顯示、其他股票 why-not／liquidity 不串入、Advice 行為不因來源證據改變、缺件明示、DTO 往返及 Workbench 選列呈現。聚焦 `tests/test_advice_composer.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_workbench_advice_contract.py` **82 passed**；強制 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；工作樹全部 18 個修改 Python 檔 `py_compile` 通過。Scratch logs：`quarterly-coverage-qa/advice-source-evidence-focused-final3.log`、`required-workbench-advice-evidence.log`、`required-update-validator-advice-evidence.log`、`required-mypy-advice-evidence.log`、`required-pycompile-advice-evidence.log`。第一次 canonical 案例錯把最小測試設定期待成 `ADD_CANDIDATE`；實際 Policy 正確拒絕正式新增。保留首次失敗 log `advice-source-evidence-focused-final.log`，修正斷言後最終聚焦通過。

定向文件檢查涵蓋 QA／架構，12 features、2 link sources，通過，log 為 `quarterly-coverage-qa/advice-source-evidence-doccheck-final.log`。擴大檢查再納入 Snapshot／Manual 後，檢查器遇到 29 條既有 `output/` junction 連結並回報 WinError 5 access denied；錯誤均指向既有 trial／task 外部目標，不涉及此新增章節，詳 `advice-source-evidence-doccheck-all-anchors.log`。未改動外部 junction／連結。最後 `git diff --check` 通過，只有 CRLF 提示。

這只讓既有、可精確連到同一標的的保存篩選與反證更容易查看；未新增或補填資料，也未宣稱 Gate 1、正式來源、PIT、自然 evidence、ML、原生 GUI 或 Owner UAT 通過。資料品質／來源資格狀態不變。

## 2026-10-26 Advice 列快速判讀摘要

Workbench Advice／Professional 研究候選列表改以五欄直接呈現標的、動作、支持／反證摘要、主要風險與資料／執行狀態。支持、反證與風險欄以首要項目作短顯示，完整理由保留在欄位提示及原選列證據詳情；資料狀態列同時顯示品質、可成交性及資料日，提示另列決策日。空理由顯「未提供」，空風險明示「未提供風險判讀」，日期缺漏顯「未知」。若有多個理由／風險，短列標出其餘項數，提示保留完整列表。常見 Advice reason token 以中文呈現；未登記 token 將底線轉為空格，較完整原文仍可由既有來源追跡核對。

本切片只投影 Advice DTO 現有欄位；股票名稱來自同一 Recommendation DTO，只有 Workbench 已將 `source_result_id` 與當日 candidate read model、股票代碼、決策日及資料日核對一致時才與代碼同列顯示，其他列保留代碼。沒有新增價格／漲跌或新報價來源，也不改排序、策略 action、政策或配置。現有 `RecommendationDTO.price_change` 沒有逐股報價日／品質，且 producer 的舊相容路徑會把缺值轉為 0；因此不把它或無逐股 quote date 的 close price 當即時行情呈現。首屏快速表仍可能因較窄視窗出現水平捲動；列已設主要欄穩定寬度並讓支持／反證欄取得剩餘寬度。未做原生桌面截圖、固定 EXE 或 Owner UAT，因此此收據只驗 Qt model／Workbench 自動化呈現，不代表真人可讀性接受。

受控 Windows Job 驗證：`tests/test_advice_composer.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_workbench_advice_contract.py`、`tests/test_workbench_source_service.py` 聚焦 **95 passed**；必要 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；`scripts/qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**；全域 mypy **1,149 source files，無錯誤**；本切片涉及的七個 Python 檔 `py_compile` 通過。原始 scratch logs 位於 `quarterly-coverage-qa/advice-quick-read/`：`stock-name-focused-final.log`、`required-workbench-stock-name.log`、`required-update-validator-stock-name.log`、`required-mypy-stock-name.log`、`required-pycompile-stock-name.log`。首次四檔測試使用過長 pytest 暫存路徑，兩個 source-service fixture setup 因 Windows 路徑長度失敗；改用 `%TEMP%` 下短 basetemp 後同一批測試 95 passed，首次錯誤保留在 `stock-name-focused.log`。Validator 首次寫入 repo 預設 `output/qa/update_tab/RUN_LOG.txt` 遭 sandbox 拒絕；改以 `BALDR_UPDATE_TAB_QA_LOG_DIR` 指向授權 scratch 後通過，原失敗 `required-update-validator.log` 保留。QA 使用者介面報告與 `RUN_LOG.txt` 均留在 scratch。`document_control check` 對此 QA 與 Feature Map 定向核對通過（12 features／2 link sources／0 errors）；納入 Manual 與 Snapshot 的較廣檢查仍列出 29 條既有 `output/` 外部試用包／任務連結，未觸碰該 Junction 或其內容。最後 `git diff --check` 通過，僅有既存 CRLF 提示。

## 2026-10-26 Workbench Advice 人工研究決定入口

選取 Advice／Professional 研究候選列後，只有 `source_result_id`、股票、決策日與目前有效每日 read model 中相同結果／股票／決策日／資料日吻合，且有來源 snapshot ID 時，才可明確記錄「已納入研究」、「略過」或新增研究註記。Workbench 將這些欄位送至既有 `DecisionContinuityController`；snapshot hash 若 Workbench DTO 未提供則留空並明示，不以 Advice payload SHA-256 代替。結果顯示 writer 回應及 readback verification 狀態；不建立交易或 fill。精確保存推薦回查仍沿既有 Advice source 按鈕與 Recommendation 頁路徑。

已新增 `tests/test_workbench_advice_contract.py::test_advice_manual_research_decision_requires_exact_current_identity` 與 MainWindow callback 契約測試。首輪 **89 passed／4 failed**、後續 **90 passed／3 failed** 的原始失敗均保留在隔離 scratch；新測試的預期已依 fail-closed identity 契約修正。兩項既有真 MainWindow journey 後續在受控 sandbox 重試，仍於 `repository_output.validate_repository_root(...).resolve(strict=True)` 讀取研究根時遇到 WinError 5；它們沒有通過，不能由其他聚焦測試替代。

Final 受控驗證：Advice／Workbench 聚焦組（排除上述兩項因 sandbox 根目錄 no-follow 檢查而無法完成的 MainWindow journey）**88 passed**；必要 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,150 個來源檔無錯**；本輪修改 Python 檔 `py_compile` 通過。所有驗證在同一個有資源上限的 Windows Job 序列執行，最後 exit 0、剩餘程序 0、無強制清理。首輪與環境阻擋的失敗仍留在授權 scratch，沒有刪改。

此人工研究入口只記錄納入研究、略過或註記，經既有 continuity writer/readback 核對結果；不建立交易／成交，不連接真實帳戶，不以 Advice payload hash 假扮 snapshot hash。正式資料、Advice／Gate 資格均未改。原生 GUI 與 Owner UAT 尚未執行；兩項 MainWindow journey 的 sandbox 限制也仍待可讀取合法研究根的環境重驗。
