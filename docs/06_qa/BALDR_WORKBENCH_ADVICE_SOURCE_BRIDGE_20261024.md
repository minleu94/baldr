<a id="2026-10-27-workbench-advice-missing-fields-field-specific-route"></a>

## 2026-10-27 Workbench Advice 缺欄改為按欄位來源導引

缺欄判讀卡原先把所有必要欄位都指示成「回查原推薦與策略設定」，但策略版本服務只在建立新版本時接受 Advice contract；已保存版本不可事後補綁。現在欄位依責任分為可回查同筆來源欄位與策略作者聲明欄位。來源欄只有已核對同筆 ID 時可用原有 exact-result 回查；否則明確保留未知。作者欄（進場論點、失效條件、持有期間、檢視頻率）明示需要新的合格回測與新策略版本，Workbench 新增條件式按鈕導至 Backtest。該按鈕只導航，不執行回測、不升版、不寫入或推填欄位；選取／狀態重置時隱藏。

Root 手動檢查了分類、按鈕顯示條件、選取重置和 Main Backtest 導航；`workbench_view.py`、`main.py` py_compile 通過。此輪沒有新增或執行測試套件，也沒有 Owner 原生 GUI UAT。限定 `document_control check` 涵蓋 12 features／3 link sources，但因 `output/` junction 權限回報兩條既有 `APPLICATION_MANUAL.md` 歷史 trial-guide 連結 WinError 5 而未通過；未把它記成產品回歸失敗或 link check 成功。本變更只移除操作死路，不補 Advice 或資料欄位，不改策略或任何 Gate／PIT／ML 資格。

## 2026-10-26 Quick Read 分開政策／資格限制與同股來源證據

Workbench Advice 的 `why_not_reasons` 是 policy／資格判斷原因，不代表個股反證。Quick Read 表頭與內容已改標「政策／資格限制」；欄位提示另列同一 Advice 列的同股保存來源證據，若無來源列則明示「未提供；不能據此推定沒有反證或風險」。明確選取的保存研究 lane 也分列策略／資格限制及來源證據。Composer 的 exact result／stock source matching、策略決策、資料庫與 Gate 狀態未改。

驗證：`tests/test_ui_qt_update_view_workbench.py` 與 `tests/test_ui_qt_workbench_view.py` **151 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,155 source files clean**；兩個 production Python 檔與一個測試檔 `py_compile` 通過。Windows owned Job 上限讀回 8 GiB／12 processes／kill-on-close；最高 Job memory 2.15 GiB，驗證後 active processes 0、handles 關閉。原始輸出與 receipts 留在隔離 scratch `owned-validation/ui-advice-copy/`。驗證涵蓋 offscreen Workbench 與隔離 validator，未做 Owner 原生 GUI UAT。`document_control check` 對指定四份文件回報 29 個既有 `output/tasks`／`output/trial` 越界連結（Snapshot 及 Manual）；QA note 與 UI feature file 沒有連結錯誤，本次新增的 Snapshot→QA anchor 也未列入錯誤。

這只修正理由分類與呈現，沒有新增反證來源、資料、Formal／PIT／ML 或 Gate credit；Gate 1 仍需策略契約與來源資料完整性等證據。
# Workbench Advice 排程候選接線 — 2026-10-24

<a id="2026-10-26-backtest-registry-promotion-readback"></a>

## 2026-10-26 Backtest Registry 升版前置與契約讀回核對

新保存的單股回測在 Research Run Registry；BacktestView 先前卻以 legacy `BacktestRunRepository` 檢查升版條件，之後又可能以不同保存入口建立策略版本，造成作者可能到不了既有 Advice 契約表單，或 Registry run／StrategyVersion 雙邊關聯無法由成功提示證明。現在 Backtest 的 Registry run 先以 `PromotionReconciliationService` 核對 storage／integrity、版本化參數契約與 Month 6 lifecycle 前置條件，再以同一 Registry run 建立 StrategyVersion；只有不在 Registry 的 legacy run 才沿用舊檢查與保存路徑。

升版回填後，服務立即讀回 StrategyVersion JSON 及 Registry metadata，核對 `source_run_id`、`strategy_id`、參數、選填顯示名稱、Advice contract（含 canonical hash）、`promoted_version_id` 及 `synced` 狀態。讀回失配不回報成功；若 Registry 已回鏈，版本與 run 會留在 `reconciliation_required` 供查核，不以無法確定的狀態刪掉可能已被引用的版本。成功視窗顯示回鏈已核對、作者契約 hash 或略過狀態，並明示版本建立不等於正式 Gate 接受。

升版對話框的選填版本名稱現在保存為 StrategyVersion 的 `display_name`，legacy 與 Registry run 都會沿用並讀回核對；已保存版本清單會優先顯示該名稱，成功視窗也會回顯；自動產生的語意版本號不受此顯示名稱影響。

回歸案例涵蓋 Registry 前置檢查、StrategyVersion／Advice contract／顯示名稱／Registry backlink 正向讀回、讀回失配轉待 reconciliation、未通過理由可呈現、legacy run fallback、saved-version reader／lookup 顯示，以及 BacktestView 使用同一 Registry repository。受控 Windows Job：升版／Advice／saved-version reader／lookup 聚焦 **60 passed**；必要 Update Workbench UI **97 passed**；`scripts/qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**；全域 mypy **1,157 source files clean**；9 個修改 Python 檔 `py_compile` 通過。最終 runner receipt SHA-256 `738b462da631ce5c5f60ed7f15c6796d34ee938acdcd2e78e03324629b820686`，exit 0、8 GiB／12 processes 限制讀回成功、remaining PID 0、無強制清理。原生 GUI／Owner UAT 未執行。

此修正只打通 Research Registry run 的升版前置與一致性讀回，不創造策略論點、不改正式財務資料，也不把 lifecycle promotion 當成 Gate 1／PIT／來源接受或 ML 資格通過。作者契約仍由作者明確填寫；正式版本、參數鎖定、disclosure 與來源／績效等 Gate 證據仍須各自成立。

## 2026-10-26 手動保存研究結果交接至 Workbench

RecommendationView 新增「送至 Workbench 作研究」入口。只有當前精確 canonical 保存結果已完成 index／payload integrity 讀回、執行成功且有推薦列時按鈕才啟用；按鈕只傳 result ID，Main 重新唯讀載入並核對 result／execution ID、payload hash 格式、schema revision 及保存的決策日／資料日。日期優先沿用結果 config；缺日期欄時只使用同一 canonical execution 的 typed cutoff。Workbench 強制以 Professional／`RESEARCH` 顯示，並保留 Why／Why Not／Risk、來源警告及原始日期。此 lane 獨立於 `WorkbenchDashboardDTO`，不混入今日排程 Advice／DailyInvestmentJourney，不寫資料庫、Journal、研究決定或 artifact；讀回失敗會清除上一筆 lane 並顯示錯誤。

受控驗收：必要 Workbench UI、保存結果 query consumers、Workbench view 與 MainWindow 真實按鈕 signal／slot round-trip 合計 **164 passed**；端到端案例另核對保存結果 ID、原決策／資料日期、`RESEARCH` 動作、排程 Advice 投影保持獨立，以及錯誤讀回清除舊 lane。Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,155 source files，無錯誤**；8 個修改 Python 檔 `py_compile` 通過。驗證使用 kill-on-close Windows Job，8 GiB／12 processes 限制讀回成功，啟動前可用 RAM 27.35 GB，Jobs 自然歸零、程序／Job handles 關閉、無強制清理。最終測試＋編譯 receipt SHA-256 `60968ff9990fcdcad017dec9be0997378534c25ffaff8abfcb0d53f89e128d1b`。原始收據與日誌留在隔離目錄 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\saved-research-*`。

這條路徑完成已保存研究結果到 Workbench 的可用操作閉環，不代表來源資料補齊、正式策略採用、PIT 或 Gate 1 通過。真實原生 GUI／Owner UAT 尚未執行；資料、策略、正式資料庫及 Gate／ML 資格均未改變。

## 2026-10-26 Workbench Advice 設定下次檢視

合格 Advice 列新增「設定下次檢視」。按鈕只在每日候選與 Advice 的 result ID、股票、決策日、資料日及 source snapshot ID 完全核對且 dashboard 非 stale 時啟用；對話框以台北時間由研究者明確選值，不由策略檢視頻率自動推算。保存前再次核對目前候選身份；若候選在對話框期間改變，拒絕寫入。控制器保存後立即讀回，Workbench 檢查同筆 identity、讀取錯誤及下次檢視時間完全相符才顯示「已保存並讀回核對」。此操作只追加人工研究狀態，不產生交易或 fill，也不改 Advice、資料來源或 Gate 資格。

受控驗證：Advice continuity／Workbench presentation **40 passed**、必要 Workbench UI **96 passed**、Update validator **25 passed／0 failed／4 skipped**、全域 mypy **1,154 source files clean**、4 個修改 Python 檔 `py_compile` 通過、`git diff --check` 通過。Windows owned Job receipt SHA-256 `44b5d145d9a4a103a1b3780b4bff3f3c2d80b5cf3e7e22f9c70496855520956d`；exit 0、剩餘程序 0，kill-on-close／8 GiB／12 程序限制讀回成功，無強制清理。原始輸出保留在隔離 task output。原生 GUI／Owner UAT 未執行；沒有解除資料品質、來源、PIT、Gate 或 ML blocker。

## 2026-10-26 Guided Advice 缺策略契約時 fail closed

修正一個會讓正式 Guided Advice 在沒有已核驗策略作者契約時仍輸出 `ADD_CANDIDATE` 的決策缺口。Guided 策略需已 promoted、鎖定參數、揭露完整、資料已觀測、執行可行狀態未明確否決，且 Advice 契約來自同一個 canonical verified execution，才允許輸出新增候選。缺少或無法核驗精確版本契約時輸出 `NO_NEW_POSITION`，原因為 `guided_mode_strategy_advice_contract_missing_or_unverified`；Professional 模式不套用此 Guided 契約 Gate，候選仍為 `RESEARCH`。帳戶預算與手動持倉不受影響。

契約快照本身由 `StrategyAdviceContract` 驗證論點、失效條件、持有期間、檢視頻率與 canonical SHA；execution context 再將其綁定 `strategy_version_id`。AdviceComposer 只從 `canonical_payload_and_index_verified` 的 exact read model 取用，legacy、未核驗或缺快照均不算通過。Workbench 將拒絕原因翻成白話；不推測或自動填寫契約內容。

驗收紀錄（2026-10-26）：Windows owned Job 可用 RAM 預檢 24.12 GiB；Job 上限實際讀回 8 GiB committed memory、12 個程序，kill-on-close 與工作區互斥鎖正常。Advice policy/composer/workbench/report 及升版略過提示回歸 **147 passed、1 deselected**；deselected 是會啟動 MainWindow 並讀取 sandbox 外正式 ML research storage 的既有整合測試，sandbox 中設定的 `baldr/research_state` 路徑不存在。更新頁必跑 workbench pytest **93 passed**；全域 mypy、11 個修改 Python 檔 `py_compile`、Feature Document Map 結構檢查均 exit 0。更新頁 validator 使用既有 `BALDR_UPDATE_TAB_QA_LOG_DIR` 將日誌及報告留在隔離目錄，結果 **25 passed／0 failed／4 skipped**。聚焦回歸首次發現 stock report 共用呈現卡露出機器原因碼，已修正共用標籤並重跑通過；升版略過提示也已有回歸，明示舊版本不可補綁及建立新版本所需路徑。收據及原始輸出保存在本機隔離目錄 `.tmp_guided_advice_qa_artifacts/`，未納入正式資料。這些證據只驗證契約 fail-closed 與文案，不代表 Gate 1 完成，也未變更財務資料、Gate 授權或 ML 資格。

## 2026-10-26 Gate 1 Advice 未知欄位與來源追溯完整性

Workbench Advice 完整性摘要之前把任何非空字串算作已填，造成 `liquidity_state=UNKNOWN`、`execution_feasibility=UNAVAILABLE` 等尚未可判讀的必要狀態從缺件清單消失；必要欄位也漏掉 `source_trace`。現在空字串、`UNKNOWN`、`UNAVAILABLE`、`NOT_PROVIDED`、`N/A`、中文「未知／未提供」都視為待補；tuple/list 逐項檢查。必要欄位加入來源追溯，精確結果 ID 或具體來源／拒絕依據才算有效，單獨來源型別名稱不算。`GATE_FAIL`、`NOT_FEASIBLE`、`MISSING` 等已知負向狀態仍按已知值呈現，不表示正向證據或通過。

回歸案例涵蓋未知流動性、不可用成交狀態、空來源追溯、只有泛型來源類別而無身份，以及所有欄位有已知值（含負向結果）和具體追溯的完整 Advice。詳細選列仍提醒欄位有值不代表來源或 Gate 合格。受控 Windows Job：Advice Composer **30 passed**、Workbench view **53 passed**、必要 Workbench UI **93 passed**、Update validator **25 passed／0 failed／4 skipped**、全域 mypy **1,153 source files，無錯誤**，5 個修改 Python 檔 `py_compile` 通過。Advice QA 文件 document-control check 通過（12 features／1 link source／0 errors）；Manual／Snapshot 檢查受既有 `output` junction 的 WinError 5 阻擋。Job receipt SHA-256 `7dbbc0c121f68d172e62484bf8ead32ae0adcdca7f686a64c774332566fcf388`，exit 0、剩餘程序 0，kill-on-close／8 GiB／12 程序限制讀回通過，無強制清理。原始收據及 validator 輸出留在授權 scratch `industry-theme-qa/owned-qa-20261025-8b72bdac6e6e4daea5e4b7da4dbb7433/single_owned_qa_abadb682580c486d842dd63d1f4b5c9f/`。

## 2026-10-26 Gate 1 Advice 流動性 Gate 投影

`AdviceComposer` 以前未填 `RecommendationAdviceDTO.liquidity_state`，所以必要欄位檢查和列表都無法呈現保存推薦中的逐股流動性排除。現在只從同一 `result_id` 的已保存流動性負向 payload 投影：單一同股列必須有 liquidity reason／threshold、`status=fail` 且 `quality=observed` 才標 `GATE_FAIL`。缺列、重複列、品質／狀態不足、其他股票或來源 ID 不符都標 `UNKNOWN`，絕不從負向專用 payload 推論 Gate 通過。

Workbench Advice 列表與選取判讀卡顯示「流動性 Gate：未通過／未知」並保留原始狀態；Advice DTO 仍只表示負向 Gate 證據，不能替代流動性數值或交易可成交性。回歸案例覆蓋同股 observed fail、跨股票隔離、降級／估算及重複列。受控 Windows Job：Advice Composer **30 passed**、Workbench view **50 passed**、必要 Workbench UI **93 passed**、Update validator **25 passed／0 failed／4 skipped**、全域 mypy **1,153 source files，無錯誤**，5 個修改 Python 檔 `py_compile` 通過。Advice QA 文件的 document-control check 通過（12 features／1 link source／0 errors）；Manual／Snapshot 的 check 仍被既有 `output` junction 存取拒絕（WinError 5）阻擋。Job receipt SHA-256 `d8f9e5e034975b3865284fe0036041bf58c1c9316b63926ebe53d795ea6b8fbd`，exit 0、剩餘程序 0，kill-on-close／8 GiB／12 程序限制讀回通過，無強制清理。原始收據及 validator 輸出留在授權 scratch `industry-theme-qa/owned-qa-20261025-8b72bdac6e6e4daea5e4b7da4dbb7433/single_owned_qa_d3c3e3dfad4e4fffb707096d8c6eb30b/`。

此可見性修正沒有寫正式資料、解除資料品質缺漏、授予 Gate 1、來源、PIT 或 ML 資格，也未呼叫券商 API。富邦官方 Market Data 文件所列為台股即時／歷史市場資料；該 API 文件沒有 MOPS 公告時間或財報版本配對欄位，無法補本輪公告橋接缺件。正式財報公告映射仍須依每一報表期間使用相應公告，不能以行情 API 取代。

## 2026-10-26 Advice 列決策信心欄

Workbench Advice／Professional 研究候選表新增「決策信心」欄，直接投影 `RecommendationAdviceDTO.confidence_tier`。常見 high／medium／low 顯示為高／中／低，缺值顯示「未提供」，欄位提示保留原始值。此欄與選列詳情的「證據信心」分開，不推導或補寫資料。

回歸案例覆蓋缺值與 medium 顯示、欄名及原始值提示。受控 Windows Job：`tests/test_ui_qt_workbench_view.py` **50 passed**、必要 `tests/test_ui_qt_update_view_workbench.py` **93 passed**、Update validator **25 passed／0 failed／4 skipped**、全域 mypy **1,153 source files，無錯誤**，三個修改 Python 檔 `py_compile` 通過。Job receipt SHA-256 `631314900ddff2e4da3b96095362d257754bbdfa2d5000277aa366ef3f0b6e0f`，exit 0、剩餘程序 0，kill-on-close／8 GiB／12 程序限制讀回通過，無強制清理。原始收據及 validator 輸出留在授權 scratch `industry-theme-qa/owned-qa-20261025-8b72bdac6e6e4daea5e4b7da4dbb7433/single_owned_qa_bc41ee47cca4419d972024162eb11e76/`。

此項只改善已存在信心欄位的可見性，不補資料或改推薦計算、來源／Gate／PIT／ML 資格；原生 GUI 與 Owner UAT 未執行。

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

## 2026-10-26 Advice 證據成熟度明示

Advice 列的資料／執行狀態摘要現在另列「證據成熟度」；選列判讀卡、提示及無障礙描述也顯示成熟度原始值。呈現只翻譯 Product Roadmap 列明的 `insufficient`、`directional`、`forward-reviewed`、`paper-validated`、`live-reviewed`。缺值或未對齊值（例如原始 capture label `forward`）一律顯示「未知／未對齊」，完整性摘要仍將 `evidence_tier` 列為待補；不將 replay／forward／paper／live 自動映射為 Advice 的覆核成熟度。

Workbench view 聚焦 **53 passed**，必要 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,153 source files，無錯誤**；三個變更 Python 檔 `py_compile` 通過。每項驗證使用單一 Windows Job，8 GiB 記憶體／12 程序上限及 kill-on-close 讀回成功，Job 剩餘程序 0，未強制清理。receipt／原始輸出留在授權 scratch `owned-validation/evidence-tier-*/`。第一次 runner 呼叫未提供 child Python executable，未啟動測試程序；修正命令後上述受控驗證通過。QA 文件 scoped document-control **12 features／2 link sources／0 errors**；包含 Manual／Snapshot 的較廣檢查只列出既有 `output/` Junction 外部 trial／task 連結無法解析，沒有新增章節連結錯誤。`git diff --check` 通過；原生桌面 GUI／Owner UAT 未執行。

此項改善成熟度資訊可讀性與 fail-closed 顯示，不會填寫成熟度、改 Advice 動作或授予 Gate 1、來源、PIT、Gate 2 或 ML 資格；正式資料未變。

## 2026-10-26 Advice 精確保存來源身份接線

`AdviceComposer` 現把符合安全格式的保存 `result_id` 填入每筆 Advice 的 `source_result_id`，讓 Workbench 可在每日 candidate result／股票／決策日／資料日仍完全吻合時顯示精確來源回查與人工研究決定入口。`source_payload_sha256` 只從 `RecommendationExecutionReadModel` 讀取，必須同時為 `canonical_payload_and_index_verified`、沒有 legacy payload、execution result ID 與 Advice result ID 相同且 hash 為 canonical SHA-256；舊格式／未核驗輸入不帶 hash。Workbench 的既有 snapshot ID 核對保留；Advice payload hash 不替代 daily source snapshot hash，也沒有自動執行人工決定或 writer。

驗證 `tests/test_advice_composer.py` + `tests/test_workbench_advice_contract.py` **42 passed**，含 Composer 產生的實際 Advice 接回 Workbench 後開啟同筆保存結果並啟用人工研究入口，以及 snapshot hash 不會被 payload SHA 代填。必要 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,153 source files clean**；三個變更 Python 檔 `py_compile` 通過。QA 使用單一有界 Windows Job，8 GiB／12 process／kill-on-close，所有 Job 自然結束、remaining 0。QA 文件定向 document-control **12 features／1 link source／0 errors**；Manual／Snapshot 較廣檢查列出 29 條既有 `output/` trial／task 外部連結無法解析，沒有修動本機輸出。原生 GUI、Owner UAT、真實人工決定 writer 未執行；此工程修復不改 Gate 1、Gate 2、來源、PIT 或 ML 資格。

### 人工研究決定讀回摘要補強

按「重新讀取同筆決定」成功後，Workbench 將既有狀態碼翻成「尚無人工決定／已納入研究／已略過」，並同列有效研究註記數及下次檢視時間。未知狀態保留原值提示，無效註記數顯示未知；身份衝突與 read error 沿用既有明確失敗摘要。後續選列自動唯讀讀回見下節。

### 2026-10-26 Advice 選列自動唯讀讀回研究狀態

在 Workbench 選取 Advice／Professional 候選列時，沿用既有每日結果 ID、股票、決策日、資料日及 snapshot ID 精確比對；吻合後立即唯讀讀取同一候選的 continuity 狀態，呈現「尚無人工決定／已納入研究／已略過」、有效註記數及下次檢視時間。身份缺件、失配、衝突或讀回錯誤會維持明確未知／失敗，不推定為尚未記錄。相同列由 current-row 與 click 事件重複觸發時，同一選取只自動讀回一次；再次更新可使用「重新讀取同筆決定」。選列讀回只呼叫 readback，不會建立研究動作；只有三個明確寫入按鈕會呼叫 append-only writer。

驗證（2026-10-26）：Workbench candidate selection／view／source service **93 passed**；必要 Update Workbench UI **96 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,154 source files clean**；Workbench view 與候選選列測試 `py_compile` 通過；Feature Map JSON 與 `git diff --check` 通過。Feature Map、UI features 與本 QA 文件的 scoped `document_control check` 通過（12 features／2 link sources／0 errors）。Manual／Snapshot 加入廣域 link check 時，既有 `output/` Junction 因 WinError 5 無法讀取，列出歷史試用／任務連結無法驗證；未更改這些連結，不能據此判定目標檔案不存在。單一 owned Windows Job receipt SHA-256 `086076400ceb1f95782edb19761ca75b4f0719f64844de9a0c2e2bc087268145`，exit 0、Job remaining 0、kill-on-close／8 GiB／12 process 限制讀回通過，無強制清理。Validator 報告與原始輸出位於 scratch `monthly-quality-detail-20261026/workbench_auto_readback_qa_final/`；scoped document check receipt SHA-256 `5e0af1ed56dc8852384c819d23f1ee2d179d33e8e711b958d0c945cd92e481ad`。此工程沒有寫 Journal、正式資料或策略，只驗證選列自動讀回與重複事件防重；未執行原生 GUI／Owner UAT，也未改 Gate 1、資料來源、PIT 或 ML 資格。

已更新 `tests/test_workbench_advice_contract.py`，驗證略過狀態、兩筆註記與台北時區下次檢視時間同屏可見。受控 Windows Job 結果：`tests/test_workbench_advice_contract.py` + `tests/test_ui_qt_workbench_view.py` **60 passed**；必要 `tests/test_ui_qt_update_view_workbench.py` **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,150 個來源檔無錯**；兩個修改 Python 檔 `py_compile` 通過。Job exit 0、剩餘程序 0、無強制清理。validator 報告留在授權 scratch `industry-theme-qa/mrd00866/logs/VALIDATION_REPORT.md`，受控收據 hash 為 `27b98c2c785d12c5c6ff420b1a064e667cd25469215e919c7b44f2c40448af10`。

原生 GUI／Owner UAT 與資料／Gate／ML 資格仍未驗收或改動；兩項既有 MainWindow 全旅程也仍受 sandbox no-follow 研究根 WinError 5 阻擋，詳見前一段收據。此切片不宣稱人工可讀性已由 Owner 接受。

### 2026-10-26 MainWindow 跨頁旅程驗收重跑

Root 以受控 Windows Job 重跑 `tests/test_cross_page_decision_journey_mainwindow.py`，此檔涵蓋 MainWindow round-trip、missing／future／conflict fail-closed 與 Portfolio exact-route。結果 **3 passed、2 failed**；兩項失敗在真正跨頁斷言前都卡於 `MainWindow()` 初始化的 `CurrentRestatedMLRunRegistry`：本機 sandbox 的 Windows no-follow 根目錄檢查對 `RESEARCH_STATE_ROOT` 回 WinError 5。分別把該值設在 visualization scratch、`C:\Temp` 和 repo 專屬 `.tmp_` root，仍因路徑不允許檢查或 no-follow handle 被拒而不能完成；沒有以 monkeypatch 繞過 registry／路徑護欄。故這是環境阻擋，不是跨頁行為已通過，也不足以判定產品路徑本身失敗。

最後一次受控 Job receipt SHA-256 `3f628a3d96f69796438edb7a2761d5d124a241735639453cad927c416dc500d6`，kill-on-close、8 GiB／12 程序限制讀回成功、剩餘 PID 0、無強制清理。MainWindow 完整 round-trip 與 fail-closed UI 結果目前維持 **未驗收**；需要能對本機受控研究根完成 no-follow 檢查的正常桌面／CI 執行環境，或經審核的 fixture bootstrap，才能重跑同一驗收。正式資料、Gate、PIT 與 ML 資格沒有變動。

## 2026-10-26 promoted 策略缺接受證據時保留研究候選

Workbench 每日 Advice 遇到保存結果將 `strategy_status` 標為 `promoted`、但沒有精確綁定的正式採用／參數鎖定／揭露核驗證據時，不再清空整份結果。相同保存推薦仍可作 Professional 研究候選顯示，動作固定降為 `RESEARCH`、分類為 `PROFESSIONAL_CANDIDATE`，並附明確警告及診斷 `promoted_strategy_acceptance_evidence_missing_research_only`。`AdviceComposer` 的 `research_only` 只會將策略判定限制到 candidate policy；來源策略 JSON 未被改寫，候選資料日期／品質、result ID、Why／Risk 與既有來源追溯沿用原保存資料。降級狀態不構成正式 Advice、Promotion Gate 接受或新增部位資格。

唯讀查核當前正式資料根的策略版本目錄及 Research Run Registry：唯一策略版本 JSON 為 `version_20260622_150810.json`，`validation_status=pending`，無 Advice contract、參數鎖定或揭露欄位；Registry 106 筆 run 中 0 筆有 promoted version backlink。沒有可供本輪放行正式 Advice 的接受紀錄，因此本次只改善候選顯示，沒有宣稱 Gate 1 通過。

驗證在受控 Windows Job（kill-on-close、8 GiB、12 processes）序列執行：`tests/test_workbench_source_service.py` + `tests/test_advice_composer.py` **42 passed**；`tests/test_ui_qt_workbench_view.py` + `tests/test_workbench_advice_contract.py` **60 passed**；修改後 3 個 Python 檔 `py_compile` 通過；`mypy app_module/advice_composer.py app_module/workbench_source_service.py` 通過。原始 focused log 位於授權 scratch `advice-product-tests-20261026/baldr_command_954dc56b7f/pytest.log`；Workbench view／contract log 為 `baldr_command_d4797a3828/pytest.log`；本輪另有一筆已修正摘要 runner 後重跑，原始 runner 錯誤及其第一次 42 passed 輸出均保留。原生 GUI／Owner UAT 未執行；正式來源、資料、Gate、PIT、Gate 2／3 與 ML 資格不變。

## 2026-10-26 Advice 每日候選 cohort 限定

Workbench 每日旅程已有候選結果 ID 與 `candidate_symbols`。Advice Composer 現在二次核對保存結果 `result_id` 必須完全相同，且候選股票清單非空；任一缺失／不符即回傳空 Advice 及明確診斷。正常組合後只保留每日候選清單中的股票，保存結果內非當日 cohort 股票會被排除並留下診斷與提示；無股票代號且來源明確為 `AdviceComposer.refusal` 的拒絕列保留供 UI 呈現，不當作股票候選。共用保存結果本身沒有改寫，canonical hash 驗證仍對原始 read model 執行。

測試新增同一保存結果含 2330 與非候選 2317、每日 cohort 只有 2330 的情境，並覆蓋 candidate result ID mismatch 與缺少候選名單時不注入。Advice／每日旅程／Composer／Workbench view 受控聚焦 **119 passed**；月營收 reader／Research Console **94 passed**；必要 Workbench UI 回歸 **93 passed**；Update validator **25 passed／0 failed／4 skipped**；全域 mypy **1,153 source files clean**；8 個修改 Python 檔 `py_compile` 通過。最終 Windows Job receipt SHA-256 `75a4d224695e19bbf1cffe634951521b884205bec1ae5ebeb1ec7a8f815c4bd2`；kill-on-close、8 GiB／12 程序上限讀回通過、exit 0、剩餘 PID 0、無強制清理。首次 Advice suite 因長 scratch basetemp 使 Windows artifact fixture 超過路徑限制而有 4 failures／4 errors；改用 repo `.q/wbc` 短 basetemp 後同組全數通過，沒有產品程式修補。此防線不改策略分數、Advice 動作或正式資料，也不授來源、PIT、Gate 1／2／3 或 ML 資格。原生 GUI／Owner UAT 未執行。

### 2026-10-26 MainWindow 跨頁旅程受控驗收成功

前段 sandbox 內的 **3 passed／2 failed** 是 no-follow 存取環境錯誤，並非這兩個跨頁案例的產品斷言結果。改由受控 Windows Job 在路徑檢查可正常執行的環境，重跑同一 `tests/test_cross_page_decision_journey_mainwindow.py`，五項全數 **5 passed**（15.75 秒）：MainWindow 跨頁 round-trip、missing／future／conflict fail-closed 與 Portfolio exact-route 均通過。Job receipt SHA-256 `e6eda5000fd2e63b265abce1cb0493ef786a841bcdab937e6203436576b6a772`；kill-on-close、8 GiB 記憶體／12 程序限制讀回成功，Job exit 0、remaining PID 0、無強制清理。沒有寫正式資料。

此收據只驗證該測試檔涵蓋的 fixture-based MainWindow 路徑；它不替代整份跨頁計畫的重啟讀回、一次 close、Paper／user-declared 三 lane 共存或 Owner 原生 GUI UAT，也不授 Gate、PIT、正式 Advice 或 ML 資格。這次仍未宣稱整體 cross-page acceptance 完成。

### 2026-10-26 可選 ML 登錄失效時保留規則研究啟動

MainWindow 建立可選 current-restated ML registry 時，若遇到 `CurrentRestatedMLRegistryError` 或 `MLResearchOutputBoundaryError`，現在會明示 ML 暫不可讀並以 `ml_provider=None` 繼續建立個股研究報告服務；service 原有 ML 區塊會顯示不可讀限制，規則研究仍可用。其他未預期例外不攔截，仍依原流程中止並診斷。回歸測試分別注入這兩種錯誤，確認已知錯誤不阻止啟動、provider 保持 None、狀態列有警告；原有正常 provider 注入測試也通過。

受控 Windows Job 最終驗證：`tests/test_ui_qt_stock_research_report.py` **81 passed**、必要 `tests/test_ui_qt_update_view_workbench.py` **96 passed**、Update validator **25 passed／0 failed／4 skipped**、全域 mypy **1,154 source files clean**、`ui_qt/main.py` 與該 UI 測試檔 `py_compile` 通過。Job receipt SHA-256 `dd2b9643b201b71ab04c416f83de5d45499c6840be743b89331ea8fba295d104`；exit 0、remaining PID 0、kill-on-close、8 GiB／12 程序限制讀回成功、無強制清理。第一次 sandbox 執行曾因 `.t` junction no-follow 權限造成 fixture setup errors；在短路徑 basetemp 與核准的可讀取環境下重跑通過，沒有放寬產品護欄或測試斷言。

此路徑只改善可用性，不建立預測、不略過 ML 路徑驗證、不授 ML／Gate 資格。Native GUI／Owner UAT 未執行。

## 2026-10-27 整體 degraded cohort 保留逐檔可判讀建議

每日候選整體狀態仍會如實標示 `candidate_degraded`，並保留 cohort 警告；只要同一 canonical 保存結果、execution ID、cohort hash 與 eligible symbols 全部精確吻合，WorkBench 現可把該 cohort 的逐股票 `observed`／`degraded`／`missing` 品質映射到同股票 Advice。這避免一檔缺漏把同一批其他已觀測股票的建議一併隱藏或降級。逐股 `degraded`／`missing` 仍保留品質狀態並依 policy 留在研究；非 canonical、舊格式、身份／hash 不符或逐股品質缺列均沿用整體品質，不升格。這不改策略 Gate、正式採用資格或資料來源接受狀態。

受控驗證：Composer／逐股品質／Workbench source 聚焦組 **35 passed**；必要 `tests/test_ui_qt_update_view_workbench.py` **97 passed**；Update validator **25 passed／0 failed／4 skipped**；全指定範圍 mypy **1,161 source files clean**；工作區所有修改／新增 Python 檔 `py_compile` exit 0。Windows Job 讀回 8 GiB／12 process／kill-on-close，上述完成後剩餘程序 0、無強制清理。QA scratch `owned-validation/daily-advice-row-quality-20261027-*`。另外一輪擴大 daily journey/source service suite 因沙盒測試 artifact/temp 路徑遭 WinError 3 而未通過；改用 repo `.pytest-owned-temp` 的聚焦契約測試及必要 UI suite 均通過，故不得把該擴大 suite 記為通過。三份相關文件的 document-control 檢查未通過，共 33 項：4 個 10/26 Snapshot 既有錨點與 29 個 `output/` junction 外部連結因 WinError 5 無法核對；新加 QA 錨點沒有出現在錯誤清單。原生 GUI／Owner UAT 未執行。

本項只修正 cohort 層級品質對逐股呈現的連帶影響；不補任何行情或基本面，不解除真實缺值／單位／PIT／策略作者契約，也不宣稱 Gate 1、Gate 2、Gate 3 或 ML 通過。

<a id="2026-10-27-策略排除與資料品質分離"></a>

### 2026-10-27 策略排除與資料品質分離

唯讀重讀 2026-10-26 排程 canonical result `rec_1708b376d5524377ae1bceda654568b3` 的 200 檔 cohort：172 檔因 `liquidity_volume_ratio_below_min`、22 檔因 `strategy_filter_no_signal` 而 `status=skipped`，但舊 producer 將 194 檔一律寫成 `quality=degraded`；另 4 檔為 observed／selected，2 檔因 `total_score_missing_or_nonfinite` 為 missing。所有 200 列 warnings 均空。四張真實 Workbench Advice 卡逐檔有 why、why-not 與 risk，均為 observed／RESEARCH；它們的資料日是 2026-10-22、排程決策日是 2026-10-26。ML receipt binding 缺件仍是 read-model diagnostic，不是上述 194 列或四張卡缺少理由的原因。

已修正新產生結果的分類：策略／流動性正常排除保留 `skipped` 及原原因，quality 改為 `observed`，落入 cohort exclusions；missing、計算降級及來源錯誤仍維持原 quality。排程 cohort 分類器可讀新舊兩種 canonical 結果，因此歷史結果仍按保存原件計數、不重寫。此變更不改分數、排序、策略篩選、四張既有建議或資料來源資格；現有 10/26 保存結果仍保留 194 degraded，需等新的排程結果才會以新分類讀回。

受控 Windows Job：策略評估／服務 characterization／排程分類／typed cohort parity 四個定向案例 **4 passed**；修改 Python 檔 `py_compile` 通過。較廣的四檔套件首輪為 **77 passed／12 failed**：3 個缺分 warning 斷言與工作樹現有 ScoringEngine 警告變更不一致，9 個案例在 sandbox 臨時目錄／symlink／artifact rename 遇 WinError 3/5；這些失敗收據保留於 scratch `owned-validation/cohort-exclusion-quality-20261027/`。定向重跑使用短 repository basetemp；Job 8 GiB／12 process／kill-on-close 限制讀回、自然歸零。未執行正式排程、未寫正式 DB／推薦 artifact、未重算或改寫既有 snapshot，原生 GUI／Owner UAT 未做。

### 2026-10-27 exact Advice 缺欄導覽帶入候選身分

「前往策略回測建立新版本」現在只在目前 Advice 列可和有效每日候選 read model 精確核對 `result_id`、snapshot ID、股票、決策日及資料日時顯示；按下時重新核對，遇 stale／失配即拒絕。Backtest 以純文字唯讀提示顯示候選、策略版本與待作者填寫欄位，沒有載入回測參數、呼叫回測服務、填寫契約或升版。點擊使用原始 Advice DTO 保留來源身分，而不使用格式化後的判讀 presentation。

受控 Windows Job 驗證：Workbench 導覽＋Backtest 唯讀上下文 **3 passed**；必要 `tests/test_ui_qt_update_view_workbench.py` **97 passed**；Update validator **25 passed／0 failed／4 skipped**；全指定範圍 mypy **1,156 source files clean**；六個修改 Python 檔 `py_compile` 通過。Job kill-on-close、8 GiB 記憶體與 12 程序限制讀回成功；validator 日誌及報告寫入隔離 TEMP，未碰 repo `output/`。初次 focused 測試發現點擊使用格式化 presentation 導致 exact ID 遺失，修正為保留原始 DTO 後同組測試通過。原生 GUI／Owner UAT 未執行；本項不改 Advice 內容、策略或 Gate 1／Gate 2／PIT／ML 資格。
