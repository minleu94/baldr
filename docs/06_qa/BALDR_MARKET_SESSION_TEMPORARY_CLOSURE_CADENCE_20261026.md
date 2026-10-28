# MarketSessionCadence 臨時休市 sidecar 修正（2026-10-26）

## 範圍與根因

2026-10-26 05:15 的 Evidence dry-run 使用 2026-10-22 作為市場資料日。當時 `MarketSessionCadence.for_config()` 只把年度行事曆快取傳給官方來源 provider；`TWStockConfig` 沒有 `temporary_closure_path` 設定，因此同一日曆資料夾中的官方臨時休市 sidecar 未被讀取。年度日曆把 10/23 視為一般交易日，故將 10/22 錯判為 stale。

修正後，臨時休市來源使用明確設定的 sidecar 路徑；未另行設定時，與年度日曆共用快取目錄。sidecar 仍由既有官方來源、payload 與 hash 驗證流程判定，不以無證據日期推定休市。

## 官方快取證據

- 年度 TWSE 日曆快取：`F:\Min\Python\Project\BaldrStorage\repo-output\paper_execution_eod_replay\calendar_cache\twse_holiday_schedule_2026_20261020T002504109447Z_4b409b180cd8.json`，包括 2026-10-26 補假休市。
- 官方臨時休市 sidecar：同目錄 `twse_temporary_closure_20261023_0ee4c564cac1659a.json`，確認 2026-10-23 全日休市。sidecar SHA-256：`39562938315520005bb8242f2cbc0d123f062ab63d3fc40c303e5fe4947a442`；內含官方 detail payload SHA-256 `96582e89e28ec539995e750eca1ae1e2645bfc519f62d7d009577d63fc0965f2`。
- 2026-10-26 決策日、資料日 2026-10-22 的唯讀 cadence probe 回傳 `status=current`、`expected_date=2026-10-22`、`actual_date=2026-10-22`、`calendar.status=verified`，無 cadence blockers。probe 使用正式輸出根目錄的既有快取唯讀讀取，未寫入 DB、狀態或排程輸出。

## 驗證

- 修改檔案：`app_module/market_session_cadence.py`、`tests/test_baldr_calendar_source_selection.py`。
- 新回歸案例以年度日曆的 2026-10-26 補假和 hash-bound 的 2026-10-23 臨時休市 sidecar 建立隔離快取；確認官方臨時休市被套用，並使 2026-10-22 成為 10/26 的最新有效交易日。
- 受控定向命令：`tests/test_baldr_calendar_source_selection.py tests/test_operational_quality_cadence.py tests/test_watchlist_trigger_service.py`；結果 **42 passed in 3.15s**，exit 0。Python modules／測試編譯通過；受控 Job 的 8 GiB／12 process 上限讀回成功，程序自然歸零、handles 關閉。receipt SHA-256：`A13D461E4618BE7C5F3B5BB84AEE1627B76C6602A4C3BC97C22B433B4C7D8E45`。

## 影響與未完成項目

這份修正證明 cadence 可正確判定 10/22 為目前有效交易日；它沒有重跑 10/26 全套 Evidence pipeline，也沒有改寫原 run 報告或任何正式資料。因此 05:15 原報告中的 stale／degraded 訊息仍是當次歷史輸出，不能標記為已由完整 pipeline 清除。

該次報告的 `watchlist_trigger_not_ready`、`risk_prompt_not_ready` 仍待處理。獨立調查確認 Watchlist 最新資料只到 2026-10-20；即使移除錯誤的 10/22 stale 判定，Watchlist 仍落後於正確預期日 10/22。`market_breadth_skipped_rows:75`、relative-strength/liquidity 的 42 個略過股票及其餘來源品質缺口也不是行事曆修正所能解除。此次原始報告沒有 risk-alert blocker。

## 2026-10-27 隔離完整 Evidence dry-run

以修正後程式和正式唯讀來源執行當前決策日 `2026-10-27` 的完整 dry-run；所有 report/status/log/receipt 寫入隔離工作區 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\evidence-cadence-recheck-20261027`。正式資料 DB、Recommendation/Freshness/Paper 狀態與官方日曆快取均作唯讀輸入。受控 Job 設定為 kill-on-close、8 GiB、12 processes，讀回成功；exit 0、剩餘程序 0、handles 關閉。

- Wrapper status：`degraded`，pipeline `degraded`，exit 0、errors 0；`writes_evidence_db=false`、`production_scheduler_allowed=false`、scheduler readiness before/after 均 `not_ready`。
- 修正效果：本次 6 個 actionable warning 中不再有 market breadth／relative-strength／sector 的 10/22 cadence-stale 警告；正確休市日期已由 cadence 使用。此結果由 10/27 全流程隔離重跑確認，不改寫 10/26 歷史報告或正式 `latest_status`。
- 仍阻擋：`watchlist_trigger_not_ready`、`risk_prompt_not_ready`。六個 warning 為 `forward_summary_status:DEGRADED`、`market_breadth:market_breadth_skipped_rows:75`、`risk_prompt_not_ready`、`risk_prompts:risk_prompt_source_quality:market_breadth:degraded`、`watchlist_trigger_not_ready`、`watchlist_triggers:watchlist_trigger_empty_pool`。Watchlist 的 `as_of_fallback:2026-10-20` 和 42 個 relative-strength/liquidity skipped symbols 留在 advisory；其中 75 個 breadth rows 無法判定漲跌且無 verified corporate-action exclusion，故 Market Breadth 與 RiskPrompt 仍降級。Watchlist empty pool／10/20 資料落後是另一個阻塞，不能以 cadence 修正代替來源更新或 trigger 計算。
- 同次 Paper research 輸入回到 2026-09-07；baseline 日期 2026-07-12，所列 3 個持倉缺 entry thesis、invalidation、holding horizon、review date。這是手動持倉記錄未更新造成的獨立資料缺口；本次不連券商、不推定持倉／理由，也未更新正式 Paper 狀態。
- 完整 dry-run 報告：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\evidence-cadence-recheck-20261027\output\scheduled\evidence_pipeline_dry_run\reports\20261027_20261026_095715_297677_evidence_pipeline_dry_run.md`，SHA-256 `1022654759AD60DBC8DE2D8E3CD592B9610827E0457A1BF53E0987789DE2BDF8`。Terminal receipt SHA-256 `83D8E4FF40D4FF4EBB292691C1C878B3517B8F9BDB9A458CB41B0C0C46329BA0`；owned Job receipt SHA-256 `77918737A651E36A3B65F1A19E6EE3C78ADCACAA7BC822EC3362BD04C932CB50`。

## 2026-10-27 dry-run snapshot/importer 同源修正

### 根因與修正

完整 dry-run 的 source-coverage reconciliation 會採用同決策日 transient snapshot；但 `_build_importers()` 之前先讀 `latest_before_or_on()` 的 durable snapshot，所以 10/27 source coverage 可以顯示當日，事件 capture 卻使用 10/23 durable record。修正後，dry-run 若有決策日完全相同的 transient snapshot，Watchlist／Portfolio Alert／RiskPrompt importers 都取同一份；沒有 transient 時維持既有 durable fallback。非 dry-run importer 仍使用 durable snapshot。事件 metadata 記錄 `decision_desk_snapshot_source`，可辨認 transient 與 durable 來源。

### 回歸驗證

- 新增兩個案例：有舊 durable snapshot 時，dry-run 選同日 transient；非 dry-run 仍選 durable。受控 `tests/test_evidence_pipeline_runner.py` **25 passed in 3.09s**；2 個修改 Python 檔 `py_compile` 通過。Owned Job 8 GiB／12 processes 上限讀回，exit 0、剩餘 PID 0、handles 關閉。
- 額外合跑 scheduled wrapper 測試時，預設 pytest temp 位於 sandbox 拒絕的 AppData 路徑；改到長路徑 visualizations basetemp 後則觸發 Windows `WinError 206` path length。該 wrapper suite 因執行環境限制未驗收，不能記為通過；本次程式變更的 focused runner suite 綠燈。

### 使用正式手動 Watchlist 的隔離全流程重跑

前一個 scratch run 因隔離 `output_root` 沒有手動 Watchlist 檔案，`WatchlistService` 在 scratch 建立空 default list，造成 `watchlist_trigger_empty_pool`。這是驗證配置造成的假空池，不代表正式 Watchlist 空白。第二次 run 在 scratch 複製正式 `output/watchlist/default.json` 的原始 bytes，來源與副本 SHA-256 都是 `91C6FD0B3C4FDD292E1BE956594D156BF2972D17F369D5549CBC8EEB464D9C14`；正式原件未修改。

以正式 DB／行情、Recommendation、Paper 狀態及 TWSE 日曆作唯讀來源，使用該清單副本與修正程式，在隔離 output root 重跑決策日 2026-10-27：wrapper `degraded`、pipeline `degraded`、exit 0、errors 0、4 actionable warnings，`writes_evidence_db=false`、`production_scheduler_allowed=false`。Source coverage 確認 `source_coverage_basis=dry_run_transient_decision_desk_snapshot`、`watchlist_trigger_capture_ready=true`、`risk_prompt_capture_ready=false`；唯一 blocking gap 為 `risk_prompt_snapshot_quality_not_ready`／`risk_prompt_not_ready`。Watchlist fallback 與空池 warning 均消失，event capture 看到 1,689 events、寫入 0。Scheduler readiness 仍 `not_ready`。

目前正式清單 8 檔在 10/22 指標均有資料。6000bp threshold 下只有 1477 超線；它 10/21 與 10/22 都約 6,394bp，沒有新增或分數變化，因此觸發 0 檔是有效 no-trigger 結果。不得把 no-trigger 改成缺資料，也不得沿用歷史 durable snapshot 的 10/20 fallback。

本次剩餘 4 warnings：`forward_summary_status:DEGRADED`、`market_breadth:market_breadth_skipped_rows:75`、`risk_prompt_not_ready`、`risk_prompts:risk_prompt_source_quality:market_breadth:degraded`。其中 RiskPrompt 唯一 blocker 來自 breadth 有 75 列無法判定漲跌且無 verified corporate-action exclusion；不得放寬品質 gate。Relative-strength/liquidity 42 個 skipped 是 advisory。隔離報告 SHA-256 `2D5BF9D87A9459A172790C7005FF5FC60E0779EDEE1EAD048FD5BF2FC26A0DA3`，terminal receipt SHA-256 `693D0CFDCE447625B55328EFB99F7ABDF0A7B6221990B8225619F1CFABA7C456`，owned Job receipt SHA-256 `69D922F2FEA561077E607A03C9CBE8B936ECB55EC5EFB3F6A7F9D374AEA4F90A`。完整流程尚未 ready；下一步是逐類查出 breadth 75 列的 missing/change 原因與可核驗公司行動證據，再決定如何補源或安全排除。10/21–23 historical snapshots 不得由現在的 10/22 資料反向覆蓋，因當時 availability 未證。

## 2026-10-26 TWSE 原始方向證據接回與隔離 dry-run 重驗

75 列 TWSE 缺方向的根因不是缺行情，而是 SQLite 將兩種官方狀態都壓成 `unknown`：74 列同日 TWSE 原始方向符為空白且變動額為 0.00；0056 原始符號為 `X`，官方定義為不比價。修正由 custody receipt 的 hash／大小、來源、日期與 parser 核驗原始列，再以代碼、漲跌價差、收盤價、成交量精確連回 SQLite。只有完全相符的空白／0.00 才分類為平盤；`X` 作官方不可比排除，兩筆 TPEx 除權息列仍依既有證據排除。沒有把所有 unknown 或零變動泛化成持平。

完整 dry-run 的第二個問題是 `--output-root` 指向 scratch 時，Decision Desk 也從 scratch 讀行情 custody，導致新診斷器看不到正式唯讀來源。新增 `--market-quote-custody-root` 將證據來源根和本次輸出根分開；UI／一般 builder 未另指定時仍使用設定的 output root。此項只讀取官方 custody，dry-run 產物仍留在 scratch。

以正式 SQLite／官方行情／MOPS sidecars、推薦、Paper 狀態及日曆作唯讀來源，隔離 watchlist 副本 SHA 保持一致；完整 pipeline dry-run exit 0、`dry_run=true`、`confirm=false`、errors 0、events 寫入 0、forward outcomes 寫入 0。Breadth 的 `market_breadth_skipped_rows` 已由 75 降至 0，RiskPrompt blocker 清空，`risk_prompt_capture_ready=true`，`blocking_gaps=[]`；scheduler readiness 從 `ready_for_design` 到 `ready_for_manual_confirm`。最終仍有 2 warnings：Forward summary degraded、TWSE 官方不可比 1 列；2 項 advisories 為 TPEx corporate-action 排除 2 列及 relative-strength/liquidity skipped 42 檔。因此 overall status 仍是 `degraded`，不是全流程完全觀察到或 Gate 通過。

直接 provider 唯讀重算：有效收盤價母體 1,957；方向分類 1,954（上漲 394、下跌 1,423、平盤 137），74 筆 TWSE 空白符核驗列為平盤；0056 官方 `X` 不比價排除 1，TPEx 除權息排除 2，unknown skipped 0。其 bounded receipt SHA-256 為 `7371B1E1B05CEDC1997604184E7C593D833958C86CDA10F4473E26A61A338532`。Decision Desk 廣度卡現於來源日／品質旁顯示方向分類分母、TWSE 空白符核驗平盤、官方不比價／除權息排除及方向未知略過數；UI QA 用 1,954／1,957 fixture 核對文案，未將隔離 dry-run 結果寫進正式 snapshot 或資料庫。

剩餘 Forward summary degraded 是獨立 outcome 覆蓋問題，不是 RiskPrompt blocker。當次摘要包含 recommendation group/window 20、11 筆樣本；outcome quality 為 observed 43、degraded 11、missing 32，warnings 為 `source_not_ingested` 22、目標交易日官方價格缺件 19、`insufficient_future_data` 13。報告未提供逐筆 event／outcome identity、目標交易日或 `next_expected_maturity_date`，因此不能把 13 筆都當成等待成熟，也不能把 19 筆或 22 筆推定可由現有來源補齊；本次 `outcomes_attempted=0`，沒有回填或改 Gate。後續須逐筆只讀核對 event、target session、行情及來源 custody，才可安全分類。

驗證：market breadth／TWSE direction／factory／Evidence runner 定向 **73 passed**；加上 Decision Desk UI regression 後 **127 passed**，owned Job 限制 8 GiB／12 processes、測試進程歸零、handles closed。完整 dry-run 報告 SHA-256 `E348363C116D9F4A07785B5E540D5B5F330522C963A79E8B070FC2DDC93A2598`；owned Job receipt SHA-256 `9CD036C3F206C80995E436A3F3728474281E09DB6C08AB96E30AA465BE88CAB8`，stdout SHA-256 `A21CD0176C80BFEEE5E1CB51F230579979725ED90F3471C4CFC29EE104437543`。正式資料、持久 snapshot、自然排程與 Gate 狀態均未改；過去日期的 snapshot 不以目前 custody 反向重寫。

## 2026-10-27 Forward stale window-20 精確重算

### 核驗與寫入範圍

前次完整 Evidence dry-run 的 19 筆 `missing_price` 都已在正式 `daily_prices` 找到同代碼／目標日唯一正收盤列，並逐筆對上 hash-verified TWSE／TPEx 原始 JSON：2026-10-21 有 7 列、10-22 有 12 列。官方 raw bytes SHA 分別為 TWSE `b200d88bf95dd077b301c85fb58b6dafff7f5bae9412ac15f07a49a79343bee8`、TPEx `b37b4f6ec91766d702bde957818c8e01f0f38b67ee4992f1b0fb626e441fb87a`；10-22 TWSE `32eb2d792c9865709b23663ed0210c50e3a3aac2c3023d805992264a9e0157f9`、TPEx `607afa4d03db76ada55fa8f7df1a01c816ac7880a2e1b52d74980e2932050750`。歷史可得時間仍標為 `prospective_capture_only`；結果價只用於事後 outcome realization，不授予 PIT／訓練／來源接受資格。

因原計算入口無 event ID allowlist，新增可重複 `--event-id` 精確篩選，並將選取傳入 Forward service、排程 receipt 與健康摘要。排程入口把空清單保留原有全 cohort 行為；明確清單最多 800 IDs，空白 ID 拒絕。正式選取 19 個 stale IDs、單一 `window=20`、決策日期 2026-09-18 至 09-21，透過有 reservation 的 production-confirm writer 重算。其餘日期、event、視窗不在 allowlist；在 C: 建立的正式 DB recovery copy 為 4,111,110,144 bytes、SHA-256 `8092D8D62AEB1DB4BC6A4FFA062CF34B2C1D7DA5D14FD4BF36EA8652239BA64F`，`quick_check=ok`，19 個既有 outcome row 完整可讀。

### 結果與頁面資料

- 正式 writer 掃描／更新 19 筆，`missing_outcome_price=0`、`pending_insufficient_future_data=0`，run 狀態 `passed_with_warnings`。唯讀前後比對正式 DB 與 recovery copy：9/18–23 的 window-20 cohort 共 32 筆，且**恰好只有 19 個 allowlisted event IDs 改變**。
- 後寫入 19/19 outcome status 為 `ready`；19/19 data quality 仍 `degraded`，共有 38 個 `source_not_ingested` 警告，對應企業行動及交易限制兩種來源各 19 次。這兩類不可用收盤價代替。
- canonical `F:\Min\Python\Project\FA_Data\output\scheduled\forward_outcomes\latest_status.json` 已由同一精確 writer 更新；正式排程狀態讀取器可見本次 19 scanned／19 updated／38 warnings。未直接開啟原生 GUI 做目視 UAT。
- 修復後再做 9/10–23、recommendation_included、window-20 的完整唯讀 dry-run：43 scanned、ready 30、pending 13、missing 0；正式 DB 前後檔案 stat 不變。台北時間 2026-10-27 01:57 當日尚未收盤，13 筆仍待 10/27 收盤資料；10/23 臨時休市及 10/26 年度休市均由官方日曆考量。此 dry-run 有 73 個 warning occurrences：38 是本次 19 筆的缺來源警告、22 是既有 11 ready outcomes 的相同雙來源警告、13 為未成熟項目。

### 驗證與限制

Forward repository/service/manual CLI/scheduled CLI 定向回歸 **52 passed**，8 GiB／12 process Job 自然退出且 handles closed。Canonical production receipt 為 run `20261026T175624162476Z`，狀態 `passed_with_warnings`；正式前後差異核驗只命中 19 個 allowlisted IDs。正式資料已改的是 19 個 outcome row；Gate、ML、PIT、策略推薦與原始行情表未因本次重算升格或變更。因 source quality degraded，產品全體 Evidence／Forward 仍不能宣稱完全無缺漏。

## 2026-10-27 CLI 行情 custody 預設沿用推薦來源根

比較兩次相同決策日的完整 Evidence dry-run：10:28 run 明確提供 `--market-quote-custody-root F:\Min\Python\Project\FA_Data\output`，方向證據精確命中、RiskPrompt ready、`blocking_gaps=[]`；10:24 run 指定了同一個 `--recommendation-source-root`，但遺漏行情 custody 參數，結果把 scratch `--output-root` 當行情來源，Breadth 77 列無法分類並重新阻擋 RiskPrompt。兩次 dry-run 日期、正式唯讀 DB、資料根及 Paper／Recommendation 輸入相同；差別是行情 custody 根。

CLI 現於未明示 `--market-quote-custody-root` 時，沿用 `--recommendation-source-root`；若兩種行情／推薦 custody 分置，仍可明確指定行情根覆寫。這讓受控隔離輸出不會遮蔽已設定的唯讀行情原件，也不改變未知方向的 fail-closed 規則。Manual 已同步。

受控 `tests/test_run_evidence_pipeline_cli.py`＋`tests/test_evidence_pipeline_runner.py` **34 passed**；resource Job receipt SHA-256 `D7ED86155A57EBB0CDB38E69F497D731078F3F3A0447F2AAEDBD306C3893B23A`，exit 0、Job 歸零、handles closed。第一次同一測試因 runner 指向不允許寫入的 `C:\Temp` basetemp，setup 34 errors；沒有產品斷言執行。改用 repo 短隔離 basetemp 後完整重跑通過。

另以正式 DB、官方行情 custody、Recommendation、Paper 及日曆作唯讀輸入，隔離輸出全流程重跑 2026-10-27，刻意不傳 `--market-quote-custody-root`。CLI 自動取推薦來源根後，`risk_prompt_capture_ready=true`，breadth 不再出現 skipped-row 警告，`risk_prompt_not_ready` blocker 清空；唯一 blocker 是本次全新 scratch 未帶手動 Watchlist 的 `watchlist_trigger_not_ready`，這與前次成功完整重播先複製正式 Watchlist bytes（SHA 保持 `91C6FD…D9C14`）的設定不同。報告有 4 個 warnings、3 個 advisories；event capture 1,689 筆、寫入 0，forward outcomes 嘗試／新增／更新皆 0。正式 SQLite 前後 size 均為 4,111,114,240 bytes，`LastWriteTimeUtc` 相同；dry-run report SHA-256 `65FA731F3D232B0BA22521452CC933EA54ED225B27D553FADCF1988DDF0FEA08`，owned Job receipt SHA-256 `B982375CE0DA2DA6457615FF07EE1EB947097E32CF984DD5990C1B7765EB9649`，Job exit 0、8 GiB／12 process 上限讀回、歸零且 handles closed。來源日期仍是同日 transient snapshot；overall／scheduler 仍 degraded／not_ready，這次不構成 Gate 或來源資格通過。

<a id="歷史回放以決策日評估行事曆證據-2026-10-26"></a>
## 歷史回放以決策日評估行事曆證據（2026-10-26）

### 修正

完整 Evidence replay 以 date-only 決策日執行時，cadence 原先用回放執行當下的觀察時間檢查日曆快取新鮮度。若執行跨到隔日，舊快取可能在目前時間已逾期，而新快取又晚於歷史決策日可得，造成無快取可用。現在歷史決策日使用 `decision_at`（該決策日台北時間日末）建立 calendar observation clock；正式 runtime `observed_at` 另外保留。快取仍須同時滿足 `available_at <= decision_at` 與「在決策時點尚未過期」，因此未引入未來資料。此語意只適用現有 date-only 日末 replay，不宣稱支援 intraday 歷史時點，也不授予歷史 PIT 資格。

### 驗證

- 新回歸案例建立 10/20 舊年曆快取、10/27 新快取及 10/24 擷取的 10/23 官方休市 sidecar，於 10/27 runtime 重播 10/26 決策日；驗證採用當時仍新鮮的 10/20 年曆、保留 runtime／calendar observation 時間差異，並由 10/23 休市得出 10/22 為最近交易日。另更新「未來可得快取不可用」案例，維持 fail-closed 語意。
- 定向套件（calendar selection、operational quality cadence、market breadth、sector rotation、watchlist trigger）**72 passed**，兩個變更 Python 檔 `py_compile` 通過。第一次執行有兩項測試斷言依賴錯誤鍵型／單一錯誤碼；更正斷言後完整重跑通過。Owned Job receipt SHA-256 `EAF7E16B9A0D49DC2BB92E3BBB022519C8CC5A9CBA9E9AD4E92C88A38C8D780`，exit 0、8 GiB／12 process 限制讀回、Job 歸零、handles 關閉，未強制清理。
- 以正式 SQLite、Recommendation、Paper、Watchlist、官方行情 custody 與日曆唯讀輸入，決策日 2026-10-26，完整隔離 Evidence dry-run 重跑。Pipeline `degraded`、0 errors、`pipeline_blocking_gaps=[]`；原有 breadth／sector cadence fallback 警告消失。剩 2 warnings：`forward_summary_status:DEGRADED` 與 `market_breadth_source_declared_non_comparable_exclusions:1`；另有 2 advisories（corporate-action exclusions 2、relative-strength/liquidity skipped symbols 42）。Paper research 仍 degraded／舊 snapshot，不能由 cadence 修正推定其資料新鮮或健康。
- Wrapper 狀態 `degraded`，scheduler readiness `ready_for_manual_confirm`，`production_scheduler_allowed=false`、`writes_evidence_db=false`。Report SHA-256 `F5C730F9AF17F3A7E236B0CACD9570A1AE1200A40253311385FB12AA801CA97D`；terminal receipt SHA-256 `FB197A3297007835BD6E93C4B9D690C1FF38C631D8BC21C039B41CBC58F1251C`；owned Job receipt SHA-256 `652F9181F042E42A1F962673FA548540943D20B5375482190AD91BB3E147C0C7`，exit 0、8 GiB／12 process 限制讀回、Job 歸零、handles 關閉，無強制清理。

本次只證明歷史 dry-run 的日曆 cadence 回放可用；未解除其他資料品質／Forward warning，未寫正式資料，也未改 Gate、PIT、ML 或排程狀態。

<a id="官方不可比行情排除維持披露但改列-advisory-2026-10-26"></a>
## 官方不可比行情排除維持披露但改列 advisory（2026-10-26）

Breadth 已依 hash-bound TWSE 原件確認 0056 原始方向符 `X` 代表不比價，該筆明確排除；它不是 missing／unknown。`MarketBreadthService` 會將官方不可比列從 unknown skipped 分母扣除，unknown 數為 0，quality 保持 `OBSERVED`，並保留排除原因與數量。Evidence pipeline 先前只將官方 corporate-action 排除列為 advisory，卻把同樣經官方來源確認的 non-comparable 排除列為 warning，造成 pipeline 呈現與資料品質狀態不一致。

修正 `_canonical_advisory_token` 將 `market_breadth_source_declared_non_comparable_exclusions:<count>` 同樣投影為 advisory。原始 warning token 與來源排除記錄仍保存；只改報告嚴重度分類，不把該列改成漲／跌／平，也不降低 unknown missing 警告。獨立 Luna review 確認此做法符合現有品質契約及 corporate-action 排除模式。

- `tests/test_evidence_pipeline_runner.py`＋`tests/test_market_breadth_service.py` **40 passed**；兩個修改 Python 檔 `py_compile` 通過。Owned Job receipt SHA-256 `A5CBE8FB77FD465A54784709BC10032EB467784060B7804C3077219D132DD5B7`，exit 0、8 GiB／12 process 限制讀回、Job 歸零、handles 關閉，未強制清理。
- 以同一決策日與正式唯讀 DB、Recommendation、Paper、Watchlist、官方行情 custody 及日曆再次完整隔離 dry-run：pipeline warnings 從 2 降至 **1**（`forward_summary_status:DEGRADED`）；advisories 從 2 增至 **3**，新列 `market_breadth_source_declared_non_comparable_exclusions:1`，並保留 corporate-action exclusions 2 與 relative-strength/liquidity skipped 42。Pipeline blocking gaps 為 0、errors 為 0，整體仍 `degraded`；scheduler 為 `ready_for_manual_confirm`，production scheduler disabled，Evidence DB 寫入 0。
- Report SHA-256 `D9A950DE3982E70F37633B795666DE7388DED3BEA7B809CDDF34DC1A1D4FD044`；terminal receipt SHA-256 `03C3E60364CEC109B66FFCD19EAF3F94ECE0B7167D3D51DFC5E50898E40E0F78`；owned Job receipt SHA-256 `969C88F24E5E025AB70472102B089A169CAC0FDFB3591B1F856B63613DB558D2`，exit 0、8 GiB／12 process 限制讀回、Job 歸零、handles 關閉、無強制清理。

Forward summary 的 degraded 仍未解除：本次 dry-run 未重算既有 outcome（`calculate_forward_outcomes: seen=0`），摘要缺逐 event 原因，不能用這份收據安全回填或降級處理。已知非可比排除只從 warning 移至 advisory；並非資料來源缺漏被補齊，Gate／PIT／ML、正式資料及排程核准均未改變。

<a id="forward-degraded-群組明細與安全輸出-2026-10-26"></a>
## Forward degraded 群組明細與安全輸出（2026-10-26）

Markdown dry-run 報告新增「Forward Performance Detail」，將已存在的 `forward_summary` 群組彙總輸出，讓 `forward_summary_status:DEGRADED` 不再只有一個泛化 warning。所有非 `READY` 組（包含缺基準與樣本不足）排在 `READY` 前，最多顯示 50 組，提供總組數／顯示組數／截斷旗標；DB 或來源欄位中的反引號會序列化為 `\u0060`，避免關閉 Markdown fence。排序使用既有群組參照，不複製未顯示群組；完整機器可讀 `forward_summary` 仍保存在 JSON summary。

定向 `tests/test_evidence_pipeline_runner.py` **27 passed**，`app_module/evidence_pipeline_runner.py` `py_compile` 通過；受控 Job exit 0、8 GiB／12-process／kill-on-close 限制讀回、程序歸零、無強制清理。Luna 靜態複核發現非 `READY` 的缺基準／樣本不足組也必須優先，且截斷測試需實際包含非 READY 組；已依此修正為非 READY 優先、保留群組參照直到截斷、混合狀態 fixture 與選出群組斷言。最終 focused runner receipt SHA-256 `f44a0a7317899f4de80ae243ea3efb6d71103075ba16fdf3550607f832d587cb`。

以正式 DB、Recommendation、Paper、Watchlist、行情 custody 與行事曆唯讀輸入，在新 scratch 重跑 2026-10-26 全來源 Evidence dry-run。Pipeline `degraded`、0 errors、0 blocking gaps、1 warning（`forward_summary_status:DEGRADED`）、3 advisories；`events_seen=1689`、`events_inserted=0`、`outcomes_attempted=0`、`writes_evidence_db=false`、`production_scheduler_allowed=false`。新增明細揭示群組 `recommendation_included`／window 20：sample 30、pending 13、missing_count 0；quality_counts 為 observed 43、degraded 30、missing 13；warning_counts 為 `source_not_ingested:60`、`insufficient_future_data:13`；首末 event date 為 2026-09-10／09-23，next expected maturity 為 null。這些是 read model 原值；因本次沒有計算 outcome，且仍無逐事件／逐來源識別，尚不能判定 60 個來源 warning 的精確根因，也不能據此回補或降級。

最終隔離 Markdown report SHA-256 `01bc8a2c539f8c3b789382fd871835d1c7c7835640b4651f53f5cb9befb16e40`；terminal receipt SHA-256 `851fe9320d7c9d51f0fa262c0ed37506e34e0d39576f03a5ec12985051dd7532`；owned Job receipt SHA-256 `67c4f9355033545eca949e10902325caa519df3ff8bab4dedb891e19a5c886da`，exit 0、Job 歸零、handles 關閉。只改善 degraded 摘要可見度；Forward 資料、Gate／PIT／ML、正式 DB 與排程核准均不變。下一步依明細窗口逐筆唯讀列出 event/outcome、目標日、來源警告與 custody，再對官方來源核對；不可將 `source_not_ingested` 群組數直接當成可補資料筆數。

<a id="forward-maturity-calendar-自動沿用共置的官方臨時休市-sidecar-2026-10-26"></a>
## Forward maturity calendar 自動沿用共置的官方臨時休市 sidecar（2026-10-26）

對同一 43 個 event IDs／20 日 window 唯讀重算時，Forward maturity calendar 原只載入年度行事曆，沒有傳入與年度檔共置、已核驗的 TWSE 2026-10-23 臨時休市 sidecar。年度規劃因此把 10/23 當作成熟交易日，造成 5 筆 9/22 cohort 暫時輸出 `missing_outcome_price`。同一批重算明確傳入既有 calendar-cache 目錄後，10/23 休市證據被讀到，這 5 筆回到尚待成熟；更新建構器讓它在已存在共置 sidecar 時自動沿用該目錄後，再以未指定 closure path 的相同唯讀重算確認結果一致。

`build_official_maturity_calendar` 保留明確參數及 config 設定優先；只有被選中的年度 cache 同目錄存在 `twse_temporary_closure_*.json` 時才將該目錄作為 closure 候選根。`OfficialMaturityCalendar` 仍負責逐檔核對 hash、來源、可得時間與 freshness；沒有 sidecar 時不把未知當成「無休市」證明。正式 sidecar file SHA-256 `39562938315520005bb8242f2cbc0d123f0627ab63d3fc40c303e5fe4947a442`、content SHA-256 `96582e89e28ec539995e750eca1ae1e2645bfc519f62d7d009577d63fc0965f2`，事件公告為 2026-10-23 全日休市。

定向 `test_forward_outcome_context.py`、`test_official_maturity_calendar.py`、`test_forward_performance_service.py`、`test_historical_evidence_replay.py` **44 passed**；兩個修改 Python 檔 `py_compile` 通過。受控 Job receipt SHA-256 `4e9736dd8d2c19e2dcd22ec477f93f48d15ad3b9175e73529107eaf147227c64`，exit 0、8 GiB／12-process／kill-on-close 限制讀回、程序歸零、無強制清理。

以現在預設 calendar builder 對 43 個精確事件唯讀 dry-run：30 ready、13 insufficient-future-data、0 missing price；警告分別為 `corporate_action_source_not_ingested:30`、`trading_restriction_source_not_ingested:30`、`insufficient_future_data:13`。正式 DB size 前後同為 4,111,114,240 bytes，mtime ns 前後同為 `1793042650263189900`；未寫 outcome。此修正使排程可依已存在官方休市證據正確排定成熟日，不解除 60 個公司行動／交易限制來源 warning，也不提前計入 13 筆未成熟 outcome。

同日期完整 Evidence dry-run 結果仍為 `degraded`、0 blocking gaps、1 pipeline warning、3 advisories、`events_inserted=0`、`outcomes_attempted=0`、`writes_evidence_db=false`、`production_scheduler_allowed=false`。隔離 report SHA-256 `92b73336ac2a260213f90f4330bcd131e2154fe47aa44e13c7ba352915833342`；terminal receipt SHA-256 `b5625847e33562d2245890639bb72797c58314e792036ff6acbf2fdd1fde6bd0`；owned Job receipt SHA-256 `32ad77853ae2ef245b300d801af9868cd98fe80a2b577fe1e6cb555060dfdaaf`，exit 0、Job 歸零、handles 關閉。日曆 wiring 修正不代表 Gate、PIT、ML 或正式資料品質通過。
