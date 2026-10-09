# Weekly Natural Evidence Review（2026-09-20）

本文件整理 2026-09-14 至 2026-09-20 的自然證據與 V2.2 weekly collection 狀態，並納入 2026-09-21 的唯讀觀測。V2.2 collection、BankTaiwan natural capture 與 ML natural shadow 是不同 lane；本文件不把研究觀測、prospective input 或 collection metadata 當成自然成熟績效。

## 週期與觀測邊界

- 週期：2026-09-14 至 2026-09-20；最新交易日為 2026-09-18。
- 唯讀重讀 cutoff：美西 2026-09-21 02:35:32、台北 2026-09-21 17:35:32。當時 9/21 quick 04:20 與 BankTaiwan 05:50（美西）尚未到，因此本文件不宣稱 9/21 的正式日結果。
- Formal root：D:\Min\Python\Project\FA_Data；source artifact root：D:\Min\Python\Project\FA_Data_Shadow。
- 本輪依既有 readiness probe 的 inspect_source_contract，以 SQLite mode=ro 讀取七個目標 symbols；未執行 scheduler、capture、recalc 或 writer。
- 本輪 compact evidence：output/qa/formal_scheduler_readiness_current_20260921_023520/current_readiness.json；9/20 實際 proof：output/qa/formal_scheduler_readiness_20260919/current_readiness.json。

## Technical / formal lane

Formal quick 最新 run 為 20260920-1460，狀態 passed_with_warnings，technical publication receipt 為 published，可用時間為 2026-09-20 04:30:44（美西）。Receipt 位於：

    D:\Min\Python\Project\FA_Data\output\scheduled\technical_indicator_publication\2026-09-18\cfd6ce9b23dd7d5d\receipt.json

本 receipt 的完整 SHA-256 為 1d97d6da0e22ee5a4565bf213d493246867d1eb89f4ab4c393e0e8eb14f81991；published output 與目前 formal DB 的讀回結果一致：content SHA-256 為 271979dd...e07f7，rows SHA-256 為 830cdf5a...b94620，7 個目標 symbols 全覆蓋，row count 為 7,826，covered symbols 為 1,975。current readback 顯示：

- prospective_available=true；
- technical_output_value_binding_verified=true；
- technical output content hash、receipt lineage 與 feature snapshot 均 verified；
- price-up prospective status=ready，prospective blockers 為空；
- historical replay 仍不 eligible。

這裡的「9/20 實際 proof」指 readiness probe 的實際觀測時間 2026-09-20 00:05:49（美西）；舊 probe 檔案位於名稱為 formal_scheduler_readiness_20260919 的歷史目錄，目錄名稱不代表觀測日期。該 9/20 proof 曾記錄 value binding 未驗證；本次 9/21 readback 已看到 receipt 與 current DB hash 對齊，因此目前 technical binding blocker 已解除。

目前整體 source contract 仍為 blocked，剩餘 formal technical source contract 未驗證，原因為 recommendation_source_contract_missing。Corporate action 的 prospective custody 已驗證，但 formal custody 仍未驗證。因此 price-up 的 prospective input 已 ready，不等於 formal gate 或 natural gate 已通過。

這次 hash 對齊只能證明目前排程產物與目前 DB 的 current binding 狀態，不能宣稱 root cause 已永久修復。已知 recurrence 風險是：9/19 shadow quick 曾寫同一份 formal DB，之後 publication blocked；caller path 正在調整，尚未驗收。因此不能把目前狀態寫成 permanent resolved 或 root fix 已完成。

## Lane A：BankTaiwan natural capture / learning

目前 immutable capture 只有：

- 2026-09-15：2 rows；
- 2026-09-16：2 rows；
- 2026-09-17：14 rows；
- 合計 18 rows，matured 0。

目前沒有 9/18、9/20 或 9/21 新 capture。BankTaiwan 9/20 run 2026-09-20-attempt-001-654f8e546cd6 是週末 skipped_non_trading_day；最近交易日 9/18 run 2026-09-18-attempt-001-91feea81e0f4 當時因 technical prospective source not ready 而 failed_dependency。本次 readback 證明 technical binding 已恢復，但不回寫、不重分類該 immutable run。

Natural evidence 仍 pending，matured sample=0、natural training sample=0；不能由現有 capture 推導績效、成本校準、promotion 或正式 recommendation eligibility。

## Lane B：ML natural shadow

W38 最新 evidence 仍為 observation_count=29、pending=29、matured=0，與前一版計數相同；evidence hash 已更新。本輪 summary schema 沒有保存 producer 契約欄位；依 55c0cbc6 先前 QA（docs/06_qa/NATURAL_SHADOW_WEEKLY_EVIDENCE_AUDIT_2026_09_20.md）的已驗證 producer readback，這批 observation 明確寫入 promotion_day_credit_allowed=false，並保留 formal_rule_champion_weight_snapshot_missing、formal_sector_thesis_health_context_missing；daily caller 也沒有為此 research lane 產生自然可用的 observation availability clock，collector 保留 observation_available_at_missing。因此這 29 筆是 contract blocked，不能累積 promotion credit，也不是單純等待時間即可通過。

Horizon maturity 是另一組時間／資料條件：h5、h10、h20、h60 的 actual downside coverage 尚未形成，成熟計數均為 0/20，natural shadow days 為 0/20。這些數字只能描述 maturity 尚未達標，不能掩蓋前述 contract blockers，也不能把 pending 改寫為 matured。ML lane 不得用 BankTaiwan 的 18 rows 或 technical prospective ready 狀態補足。

## Paper preopen 與 EOD 歷史因果查核（唯讀）

本輪有限查核針對 2026-09-15 至 2026-09-17 的 Paper preopen snapshot 缺口，沒有執行 scheduler、writer、capture、歷史回填或 credit 變更。2026-09-08 的 registration audit 顯示 `baldr-paper-portfolio-daily` task 為 `available`，schedule 為 `DAILY 16:15`，action 與 `scripts/scheduled/run_paper_portfolio_daily.cmd` 一致；這證明 task 曾正確登錄，但不是 9/15–9/17 的日期級執行證據。

- 現有 preopen terminal receipt 只留下 9/18 `passed`（`paper-main-20260918`）、9/20 週末 skipped，以及 9/21 `passed`（`paper-main-20260921`）。9/15、9/16、9/17 沒有日期綁定的 preopen terminal receipt 或 result；因此不能把「沒有查到 receipt」寫成「task 當時必然未執行」。
- Repository Paper state 與正式 D state 兩份 SQLite 都缺少 `paper-main-20260915`、`paper-main-20260916`、`paper-main-20260917`。目前 9/18、9/21 的正常 preopen 結果只證明後續日期可產生 snapshot，不能重建或補授 9/15–9/17 的歷史 natural credit。
- Preopen wrapper 直接呼叫 isolated portfolio adapter，再進入 `scripts.run_paper_portfolio_daily.run`；EOD wrapper 則進入獨立 `paper_execution_retry_runner.py` 與 `inspect_dependency` freshness gate。兩條 lane 共用 repository ledger 的資料邊界，但目前沒有證據顯示共用 EOD gate。Preopen writer 唯讀投影既有 Paper ledger；其程式契約明列 EOD writer 不寫當日 preopen snapshot。
- 9/15–9/17 的 EOD receipts 確為 `blocked`、`ready=false`、`freshness_status_not_passed:degraded`，且沒有 source DB 或 source file write。這是 EOD lane 的獨立 degraded 證據，不能直接推論成 preopen 三日 snapshot 缺失的根因；歷史根因仍未證明，可能的 task/run、receipt 保存或寫入路徑問題不能由現有證據區分。

本查核的 compact read-only evidence 位於 `output/qa/paper_preopen_causality_audit_20260921/20260921T112202873987Z_read_only/summary.json` 與 `manifest.json`。本節不把目前 preopen 成功、EOD degraded 或研究觀測轉成歷史 natural evidence、績效或 promotion credit。

## V2.2 weekly collection 與 human review

V2.2 weekly scheduler 已於美西週日 2026-09-20 18:00 執行成功，下一次為 2026-09-27 18:00。最新 collection_id 為 ewc_2b70f0c7e4519141，涵蓋 9/14–9/20，last trading date 為 9/18，狀態為 pending_human_review。

最新 JSON/MD 只有 collection metadata；沒有 reviewer、decision、review note 或 owner 的後續 review 內容。後續 review 需依 approval-input 與 isolated working-copy 流程進行；本文件不授予 human approval、credit 或 gate。

## 可審核結論與限制

目前可供 review 的結論是：technical published/current value binding 已恢復，price-up prospective 已 ready；formal technical source contract、corporate-action formal verification、BankTaiwan natural maturity、ML natural maturity 與 V2.2 human review 仍未完成。

因此本週證據不能推成績效、歷史回放 eligibility、正式 calibration、production promotion 或 permanent fix。任何後續判定都必須以新的 immutable scheduled receipt、自然成熟樣本與獨立 human review 為準。

## 2026-09-21 BankTaiwan natural maturity follow-up（唯讀）

本節對應 `output/qa/natural_maturity_readiness_20260921/readback.json`。該 readback 是既有唯讀 tool output 的整理紀錄，沒有重新執行 production runner、capture、formal writer、calendar refresh，也沒有使用 synthetic future clock；因此不新增 9/21 capture 或成功 witness。

- BankTaiwan immutable capture 已由既有 verifier 驗證：9/15 為 2 rows、9/16 為 2 rows、9/17 為 14 rows，共 18 rows；三筆 capture 各自保留完整 path、capture hash、source-contract hash 與 `price_up.prospective_status=ready`。三筆共用 candidate、policy、cost identity，且 policy/cost 設定仍是 research-only；這是已驗證的自然收件，不是 contract blocked。
- H20 由 `RecommendationNaturalOutcomeService` 直接讀 formal SQLite DB 的 raw daily prices/market-index rows，使用既有 outcome resolver；不消費 general `forward_outcomes`。本次實際 resolver readback 顯示 9/15、9/16、9/17 仍分別缺 17、18、19 個 TAIEX session observations，endpoint 尚未形成，因此自然 matured=0，不能把舊 9/18 failed receipt 重新分類。
- 既有 official calendar cache 支持的 planned H20 endpoint 為 10/16、10/19、10/20（分別對應 9/15、9/16、9/17）；這是 planned session date，不是 actual maturity。若後續沒有漏 capture，且 20 個 matured samples、20 個 distinct decision dates、labels/source/cost/proof/authority 全部合格，最早只能規劃 2026-11-16 進入 review；不能保證 promotion、adoption 或 formal eligibility。這個 H20/date 計數不把 BankTaiwan rows 借給 ML lane。
- Calendar cache 精確到期時間為 `2026-09-21T23:15:03.53214Z`，consumer 不負責 refresh；後續使用依賴 `scripts/scheduled/run_official_calendar_cache_refresh_daily.py` 的 refresh。若 cache 過期，應等待/驗證 refresh 結果，不得以舊 planned list 宣稱 actual maturity。
- ML allocation 29 observations 仍為 contract blocked，與 BankTaiwan 18 rows 分離；本節不改寫其 blocker，也不執行跨 lane 補件。
