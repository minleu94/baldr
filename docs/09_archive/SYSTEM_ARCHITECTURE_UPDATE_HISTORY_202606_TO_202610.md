# 系統架構更新記錄（2026-06 至 2026-10）

> 原 system_architecture 第 16 節的逐次狀態與驗收流水帳；僅作歷史追溯。現行架構請看 system_architecture 主文，目前狀態請看 PROJECT_SNAPSHOT。

## 16. 更新記錄

- 2026-09-25（歷史快照，已由當日稍後 R031 closeout 更新）：同步 R026 exact NP1／NP2 bounded runtime migration 的 C2 acceptance 與 `TMP-ML-01` scoped closeout；當時保留 C3／C4 pending 與 Update SQLite teardown named baseline。請以 [R031 final closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 的 C3／C4 acceptance、named boundary baseline 及 retained owners 為現況。
- 2026-09-26：Wave14 candidate 在獨立 managed worktree 首次完整 union 為 2,404P／44F／5S／35W；42 個 exact-fixture byte／EOL mismatch 與 2 個既有 shadow-boundary aggregate failures 已具名，首次 480-input unchanged 不含全部實際 C1 fixture bytes，因此不能視為完整 input closure。五個 byte-pinned fixture 已還原至原 HEAD blobs，focused route 80P／1S；526-input 第二輪 union 為 2,431P／17F／5S。第三輪 526-input short-path full union 為 2,446P／2F／5S／35W；15 個 custody nodes 已在 short-path focused route 全數通過。Root 比對第三輪 CLI captured stdout JSON 與 C4 為 584 files／11 occurrences／10 distinct、`shadow_only=true` 且兩個 failing nodes 相同，裁定 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`；R031 engineering scope complete with retained blockers。這不是全綠或整體 refactor unqualified PASS。9/25 C4 receipts 保持獨立歷史收據；不代表產品／正式資料 gate。詳見 [R031 final closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 與 [Wave14 candidate manifest](../06_qa/WAVE14_CANDIDATE_CHANGE_MANIFEST_20260926.json)。

- 2026-09-14：同步 Decision Workbench 的 probability／rank provenance 詳情、unknown／shadow
  判讀、既有 Journal／Evidence／Portfolio ledger identity 重用原則，以及 daily shadow policy
  內的自動採用／回退邊界；不新增平行 decision store、不授權 formal promotion 或 broker。

- 2026-09-14 02:34:17-07:00：normal pipeline 已完成並保留 source／cohort warnings；learning child 以 `recovered_completed` 的 `time_stratified_eligible_dates` historical bootstrap 產生 255 training rows、candidate 與 1 row immutable capture。manifest 的 `initial_seen_start=2026-04-23`，bootstrap replay selected date window 為 `2024-09-16` 至 `2026-02-11`，date／row overlap 與 label boundary crossing 均為 0；decision 仍為 `retain_current`，自然 forward evidence 尚未成熟。affected focused／mature fixture 已完成，主線 QA final status 維持 pending；P1 cache-hit custody QA 其後獨立通過。

- 2026-09-14：獨立 UI／型別 QA：UI Workbench 81 passed（1 個 cache permission warning）、Update Tab 25 passed／0 failed／4 skipped；source-contract Mapping guard 修正後 mypy 606 source files no issues。real durable daily flow、主線新版 wrapper smoke 與 QA final status 仍待父任務交付；P1 cache-hit custody QA 另已獨立通過。

- 2026-09-14：主線驗收補充：affected focused suites 107 passed（11 個 test files、36.44 秒、既有 1 個 cache warning）；changed scheduled scripts 的 mypy 7 files 成功；changed scripts／modules／tests 以暫時 `PYTHONPYCACHEPREFIX` py_compile 通過，原有 `__pycache__` permission 限制保留；inventory 12 passed；新增 guards test 後登錄總量 804、recommendation 30。synthetic mature fixture 已通過 production source verifier 與 authority adopt／rollback assertions；舊 cache-hit guard 的 P1 source-audit／cross-root lookup／隔日 DB 變更缺口其後已由 verified receipt reuse 修復，獨立 cache QA 已通過；主線新版 wrapper smoke 與修後 source tests／型別／compile／inventory 最終 handoff 仍待交付。

- 2026-09-14：P1 cache-hit custody 修復後獨立 QA 已通過：`tests/test_recommendation_learning_cache_hit_custody.py` 為 `1 passed, 1 warning in 1.25s`、exit 0；三日正式 output receipt → Shadow verified reuse、原 timestamp、production source audit hash／value／lineage 與正式 ADX producer 輸出均驗證。此為 bounded fixture custody proof；主線新版 wrapper smoke 與修後 source tests／型別／compile／inventory 最終 handoff 仍待交付。

- 2026-09-14：主線修後 focused handoff：source-contract／capture／official-custody／guards `17 passed`；update-service／process-pool／technical-analysis `10 passed`；targeted mypy `5 files` clean；inventory `12 passed`，登錄總量 `805`／recommendation `31`；cache custody `1 passed`。scheduler 修正 test fixture 後的最終重跑與新版 wrapper smoke 尚待交付，整體收尾維持 pending。

- 2026-09-14 04:22:11-07:00：正式 default wrapper true-success：pipeline `passed_with_warnings`、`blockers=[]`；quick publication 於 `2026-09-14T04:21:27.181165-07:00` 為 `published`；learning child `completed`，symbol source=`scheduled_recommendation_snapshot:scheduled_rec_20260914_042140.json:eligible`、symbols=`1528`、candidate=`rec-cal-29c1b6129396a3885a89d080`、natural sample=`0`、decision=`retain_current`。新 immutable capture hash=`sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`；04:10 microsecond／nested capture false-success 不列為 pass，主 Luna 回報 QA 7.1 為 33 passed；僅主 Luna git commit 尚待完成。

- 2026-09-14：同步 V4.2 每日推薦學習的 wrapper → pipeline → source custody → normal snapshot → learning 資料流；補上 `--skip-broker-branch`、warning／degraded 傳遞、child／pipeline timeout、normal cohort 與 explicit capture 的 identity 隔離，以及 technical／official event／corporate sidecar 的 prospective 邊界。2026-09-14 durable readback 仍為 partial／degraded 與待自然成熟，維持 shadow-only、不可宣稱 V4／alpha／收益提升；QA handoff 待當日最終測試與正常 cohort status。

- 2026-09-13：新增 V4.2 每日推薦自動學習與受控校準閉環架構同步；05:40 forward outcome 後的 05:45 bounded replay／training／capture／自然成熟／active recheck／authority rollback 皆維持 shadow-only。補上 source contract 實際 digest／coverage／available-at／corporate-action conservative gate、after-cost 獨立 baseline 與 adopted active rows 的 cutoff 隔離；同步 dedicated `FA_Data_Shadow` root resolver 與 scheduler／runner／consumer／Workbench 共用路徑契約；不寫正式 recommendation／evidence DB、不啟用正式 promotion 或 broker。

- 2026-09-06：同步八卡日期／品質 DTO、推薦 context、T+1 版本、顯式 Registry 恢復、Evidence 提案、候選帳本／候選池及 Runtime 生命週期；保留正式來源與外部 Gate。

- 2026-09-04：Data Update 增加月營收／Phase 3C 候選更新 service wrapper 與子分頁操作入口；所有候選寫入仍隔離於正式 SQLite，來源狀態查詢在 production 根目錄唯讀時採 fail-soft manifest warning。全部資料頁操作列與狀態卡採 status-first responsive layout。
- 2026-08-29：將 `release_v4` 明確定位為 engineering／storage namespace，不再稱 `V4.0 Operational Production`；補入 immutable PIT／Direct／OOC pointer、dependency closure、人工 retention、resume abandonment、tombstone 與 stale status 邊界。Runtime environment／clone proof 與 production transaction proof 維持分層；Formal 0/3、alpha 0、scheduler／broker disabled 不因容量清理改變。
- 2026-08-26：補強 Data Update trust UX；UpdateView 狀態卡改為明確 status token／freshness 判定並清除部分 payload 的舊卡片，quick/safe 與各寫入型 worker 增加互斥、子流程進度區間映射與 final-status 100% gate。SQLite Inspector 與 UpdateService 狀態讀取共用 `mode=ro`／`query_only` adapter，缺 DB 時以 unavailable fail-soft，不建立空資料庫；TWSE 明確失敗時每日來源流程在 TPEX／SQLite／技術指標前停止；同步補上 UI、每日更新與 SQLite 操作手冊及回歸測試邊界。

- 2026-07-15：同步 corporate-action availability history staging-only CLI 邊界；JSON root deterministic fail-closed、既有 target 拒絕覆寫、staging publish／cleanup 與環境 `DATA_ROOT` forbidden-root guard 均不接正式資料或 Formal lifecycle。
- 2026-07-13：新增 Terra Development Dataset V0 獨立 development-only generation 邊界；四個 core source 唯讀、T-1／252 日 observed universe、2025 development／2026 evaluation-only、append-only artifact 與 zero-formal-write safety flags 不接正式 Rule-only path。
- 2026-07-12：新增 Gate 1 Advice Current Architecture 邊界；Advice policy / composer 在 application layer，Workbench UI 僅渲染 DTO，所有輸入維持 as-of / fail-closed / no-write contract。
- 2026-07-11：新增 Target Architecture 與 Post-Refactor Product Roadmap companion 連結；修正目前主 UI 為 8 個左側主工作區，Daily Decision 已內嵌於「決策工作台 > 決策來源」；本文件仍只描述 Current Architecture。
- 2026-07-11：新增 Safe Refactoring Master Report 為行為不變重構執行 companion；該 program 於 2026-07-12 closeout 後已歸檔為 `docs/09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md`，目前架構、產品 Roadmap 與使用流程權威邊界不變。
- 2026-07-07：更新 Phase 2 Workbench MVP shell 架構同步；`ui_qt/views/workbench_view.py` 與 `ui_qt/models/workbench_table_models.py` 只呈現 `WorkbenchDashboardDTO`，主 UI 透過 `WorkbenchSourceService` 注入，新增中文顯示、預設 replay JSON summary 分析與舊 Daily Decision / Evidence Review / Portfolio read-only drill-down，不直接讀 SQLite / replay DB、不寫 DB、不啟用 scheduler、不重算 scoring / portfolio / backtest / lifecycle。
- 2026-07-08：補充 Pre-V2 readiness source-gap closeout fallback；同日 scheduled dry-run `latest_status.json` 可作為修正後歷史觀察日的唯讀證據，仍不回補 DB、不觸發 confirm、不解除 production scheduler gate。
- 2026-07-07：補充 Workbench background evidence feed / read-only Action Items MVP 架構；`WorkbenchDashboardDTO` 新增背景證據流與只讀人工待處理列，來源只限既有 snapshot/readiness/agent/replay summary payload，Action Items 保留 source trace / degraded reason / drill-down target 且 `write_intent=false`。
- 2026-07-07：補充 Workbench Action Items 人工佇列 follow-up 架構；Action Item DTO 增加 queue group / source label / sort rank，composer 只排序既有 payload，Qt view 補空 / 降級狀態文案與 drill-down target contract，仍不接 DB / replay / scheduler / lifecycle。
- 2026-07-07：補充 Workbench Phase 2C / 2D closeout 架構；`WorkbenchOperatingLoopStep` / `WorkbenchOperatingLoopTableModel` 只從 `WorkbenchDashboardDTO` 串接 daily first-look、manual queue、weekly history、multi-day dry-run、manual review note 與 scheduler gate，所有 step `write_intent=false`，Phase 0 時間 gate 與 production scheduler gate 不因 UI closeout 被補完。
- 2026-07-06：文件架構補上 `VERSION_ROADMAP_V2_1_TO_V4_0.md`，定位為 V2.0 之後長期版號 companion；本文件仍只維護目前架構、模組邊界與資料流。
- 2026-07-06：新增 V2.0 Phase 1 read-only Workbench prototype 架構同步，確認 DTO / composer / replay summary adapter / CLI 只組合唯讀樣本與 replay JSON summary，不寫 DB、不掛主 UI、不重算策略、不啟用 scheduler。
- 2026-07-06：新增 Workbench formal read-only source adapter 架構同步，確認 `WorkbenchSourceService` 只用 SQLite `mode=ro` / `query_only` 讀受控 DB path 的 DDD snapshot，並組合 Pre-V2 readiness、Agent summary 與可選 replay JSON；missing DB / table 只回 diagnostics，不建立 schema、不寫 DB、不解除 Phase 0 / scheduler gate。
- 2026-08-27：Decision Desk／Pre-V2／Evidence source coverage 的 current snapshot 查詢統一以台灣市場今日為上限；future row 保留 raw 稽核、輸出 blocker／diagnostic，不進入 current evidence。`EvidenceSourceCoverageService` 與 `inspect_decision_desk_snapshots.py` 改用 query-only 讀取，避免唯讀正式 DB 被 writer repository 初始化 schema。
- 2026-08-27：Data Update UI 的日期控件統一由台灣市場日期服務提供「今日」；localized `不可用` 會落到異常狀態；全域狀態檢查失敗會將六個核心與三個候選來源 inline 摘要同步清除並保留共同錯誤原因，避免狀態卡與來源頁殘留不同步；候選來源分頁也會投影自己的檢查結果。此為 presentation／diagnostic 邊界，不改資料更新與 SQLite 寫入契約。
- 2026-08-27：每日資料合併的 cancellation callback 延伸至單一 CSV 的讀取批次邊界；完整檔案讀取完才加入待提交集合，取消仍不會截斷或替換正式整合檔。這改善長檔等待期間的可觀測性，但不等於逐列中斷或解除 single-writer 安全邊界。
- 2026-08-27：ScoringEngine 的 rolling PatternScore 同步保存已確認型態的唯讀 evidence（名稱、方向、確認日與衰減日數），並投影 `PatternNames`／`Pattern_Signal`／`PatternAgeDays` 給 ReasonEngine。Explain 不在單列資料上重新呼叫 PatternAnalyzer；缺少具體名稱時只顯示 generic 方向訊號，避免把 end_idx 或分數臆測成已成立型態。
- 2026-08-27：Recommendation 與四個策略 executor 移除未使用的全歷史 `identify_patterns()` 預掃描，統一由 ScoringEngine rolling path 產出分數與 evidence；不改策略訊號，只避免重複計算與未確認型態的誤解釋。
- 2026-08-27：UpdateService 的 SQLite 輸入正規化修正為先辨識受治理的日期／股票代號／股票名稱別名，再在寫入副本上統一 canonical 欄位、日期與四碼代號；修正重複條件造成的英文欄位被提前丟棄問題。raw CSV 與呼叫端 DataFrame 不被原地改寫，必要欄位缺失仍 fail-closed。
- 2026-09-12：新增 V4.1 A 線第二輪 historical method pack 架構同步，確認 manifest 的 row-level time／lineage／gap contract、20／5 walk-forward reuse、PIT theme fail-closed 與 create-only frozen shadow artifact；不改 Recommendation／Scoring、不寫 formal DB、不授予 natural forward evidence credit。
- 2026-07-06：新增 Historical Evidence Replay 架構同步，確認 replay service 只做 working-copy / replay DB orchestration，recommendation result 受 `created_at <= decision_date` 限制，forward outcome 受 `data_as_of_date` 限制，不改 scheduled dry-run、不寫 formal DB、不啟用 production scheduler。
- 2026-07-06：補充 Phase 0A reference return fix 架構契約，確認 missing benchmark fallback 到 TAIEX、market index `收盤價` fallback 與保守 industry sector mapping 只影響 evidence outcome reference lookup，不改 scoring、portfolio 或 scheduler。
- 2026-07-06：新增 Pre-V2 readiness inspector 架構同步，確認 `PreV2ReadinessService` 只做 weekly history / multi-day record / source gaps / Agent report sample 唯讀檢查，不建立 schema、不寫 evidence、不啟用 scheduler。
- 2026-07-06：補充 Pre-V2 非時間型 closeout 與 Recommendation liquidity payload follow-up，確認 working-copy source gaps / UI smoke / Agent sample 已收斂，但 formal DB write、weekly / multi-day 時間 gate 與 production scheduler approval 仍未完成。
- 2026-07-05：完成 V1.6 Cross-sectional Factor Pipeline v1 架構同步，新增 snapshot DTO / repository / migration、FactorGate-backed pipeline、concept basket available-date gate、rank / quantile persistence 與 read-only attribution summary CLI；保持 application governance layer，不改 scoring、不啟用 scheduler。
- 2026-07-05：完成 V1.7 Screening Matrix & Negative Evidence v1 架構同步，新增 Recommendation result screening matrix、negative evidence payload capture、screening matrix events 與 source coverage warning；只消費已保存 payload，不回補、不重算、不改 scoring、不啟用 scheduler。
- 2026-07-04：文件架構補上 `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md`，作為外部開源專案參考、資料源補強優先序與 V1.5-V2.0 版本形狀 companion；本文件仍只維護目前模組邊界與資料流。
- 2026-07-04：完成 V1.5 Data Credibility & Corporate Action Gate v1 架構同步，新增 read-only source capability registry、corporate action policy、microstructure governed metadata 與 shared evidence source coverage service；不寫正式資料、不改 scoring、不啟用 scheduler。
- 2026-07-02：完成 V1.2 Research Credibility & Execution Model v1 架構同步，確認 Profile replay 訓練 / 驗證分離、推薦回放 rolling risk、microstructure preflight 與 relative attribution 都位於 application diagnostics boundary，不改交易、PnL、cash ledger 或策略生命週期。
- 2026-07-03：完成 V1.3 Evidence Operations & Manual Lifecycle v1 架構同步，新增 weekly evidence operations service / CLI；manual approval package 與 action item planning 只供人工覆盤，不啟用 scheduler、不自動套用 lifecycle action。
- 2026-07-03：完成 V1.4 Evidence Review History v1 架構同步，新增 weekly review history repository、dashboard service 與 Research Lab `Evidence Review -> 覆盤歷史` 唯讀子頁；history 只保存人工覆盤快照，不啟用 scheduler、不自動 lifecycle action。
- 2026-07-02：完成 V1.1 workflow bridge v1 架構同步，新增 `ProfileReplayComparisonService` / DTO application boundary；Profile replay 比較只讀注入 runner 結果並輸出人工 lifecycle candidate，不寫 DB、不重算推薦、不自動升降級。
- 2026-06-23：完成 Healthcheck Batch 2 架構同步，新增 `DecisionDeskDashboardComposer` 與 `SmartMoneySemanticService` 邊界；Daily Decision Desk answer-first dashboard 與 Smart Money 5 / 20 / 60 日語意診斷皆由 app service / DTO 提供，Qt UI 不重算籌碼或市場邏輯。
- 2026-07-01：新增 Post-V1 evidence layer 架構邊界，確認 Evidence Event Store / Forward Outcome Calculator 只保存事件與 close-to-close research outcomes，不改 scoring、推薦權重、portfolio 或 UI。
- 2026-07-01：新增 Evidence Review Dashboards read-only UI pack 架構邊界，Research Lab `Evidence Review` 只透過 dashboard service 讀取 Forward Evidence、Live vs Research Gap、Signal Decay 與 Decision Quality；UI 不直接讀 SQLite / repository，不改 scoring、portfolio、Research Run 或 Strategy Lifecycle，也不建立 scheduler。
- 2026-06-23：完成 Healthcheck Batch 3 架構同步，新增 `RecommendationProfileService` 作為推薦分析 Profile lifecycle 邊界，支援內建 / 自訂 / gate-passed 策略版本 Profile，並明確規範 Profile-Regime mismatch 只作解釋與分數揭露。
- 2026-06-23：完成 Healthcheck Batch 4 架構同步，新增 `research_result_presentation.py` 作為 Research Lab 結果頁呈現邊界；推薦回放段落、Train-Test / Walk-forward 樣本可靠度提示與 Registry 比較中文判讀只讀既有結果，不重跑回測、不抓新資料、不產生交易建議。
- 2026-06-17：完成 Month 5 Fundamental Layer v1 closeout 架構同步，確認 fundamental tables / provider / adapters / diagnostics 為保守接入邊界；P/B、P/S 已補 guarded presentation policy，官方歷史 PIT 公告日保留為後續治理 residual；Month 6 Strategy Lifecycle 不得直接污染 ScoringEngine。
- 2026-06-17：補上 P/B / P/S valuation policy 架構同步，確認 P/B / P/S 僅接受 governed external observations 或 future backfill records，不在系統內推導估值分子 / 分母。
- 2026-06-17：完成 Month 6 Strategy Lifecycle / Portfolio Feedback v1 架構同步，新增 lifecycle rule engine、drift detector、portfolio feedback attribution、Portfolio Review snapshot 與 Registry-based Promote lifecycle gate；持倉管理 UI 只讀 service attribution，不重算策略或改寫持倉。
- 2026-06-17：補上 lifecycle evidence 架構同步，新增 append-only `strategy_lifecycle_repository.py`、latest state projection 與 demote / retire proposed evidence 保存邊界；Promotion 成功後可記錄 applied evidence。
- 2026-06-15：完成 Daily Decision Desk Portfolio Alert Attribution v1，將持倉警示拆為來源標籤、condition status、chip risk level、reason tokens 與 data quality flags，並整合至主 UI 與風險提示，明確定義由 PortfolioAlertService 進行歸因產生的架構職責。
- 2026-06-15：完成 Daily Decision Desk Why Not / 風險提示 v1 對接，由既有 section DTO 欄位與警告推導，輸出對應之低流動性、相對弱勢、Watchlist 觸發與持倉警示提示，不重複計算。
- 2026-06-15：補入 baldr 願景與架構權威邊界，更新 Daily Decision Desk v1 已接上主 UI；Market Breadth v1已接 SQLite `daily_prices` provider，Sector Rotation v1 已接 SQLite `industry_indices` provider，Relative Strength / Liquidity Ranking v1 已接 SQLite `daily_prices` provider，Watchlist Trigger v1 已接 `WatchlistService` 與 SQLite `technical_indicators`，Portfolio Alert v1 已接 `PortfolioService`、`PortfolioConditionMonitor` 與 `PortfolioChipService`，其餘 Strategy Drift 與 Post-trade Attribution 仍屬後續工作；同步 Month 3 Portfolio Replay 可信度、固定組合 per-stock factor metadata保存與後續資料因子接入防線。
- 2026-06-16：完成 Month 4 Daily Decision Desk 收尾架構註記，確認 v1 以 service snapshot 聚合並新增 UI boundary contract test；Month 5 可從 Fundamental Layer preflight 開始，Strategy Drift 與 Post-trade Attribution 仍屬後續工作。
- 2026-06-16：啟動 Month 5 Fundamental Layer preflight 架構落點，新增公告日 / available_date 初版政策、raw 月營收正規化契約、候選 SQLite schema dry-run / report API 與 fundamental adapter contract，確認 raw fundamental CSV 缺 `available_date` 時不得產生 normalized record / factor record，未來資料仍須經 FactorGate 驗證。
- 2026-06-16：新增月營收 availability mapping dry-run 驗證入口與 CLI 架構邊界，確認它們只讀 mapping、輸出 diagnostics，不建立或改寫正式 mapping、raw CSV 或 SQLite。
- 2026-06-16：新增月營收 availability historical dry-run builder 架構邊界，確認 TWSE/TPEX 最新月 OpenAPI 或人工官方 JSON 只能產生候選 mapping / diagnostics，正式 mapping 寫入與 monthly revenue backfill 仍需人工 gate。
- 2026-06-16：補上 MOPS 官方 HTML source-dir 架構邊界；`--mops-html-dir` 只讀人工保存且含 `出表日期` 的官方 HTML，缺欄位時 fail-closed，不由 raw CSV 補日期。
- 2026-06-17：補上 MOPS `--mops-static` 架構邊界與 45 天合理揭露窗口；historical static report 的重新出表日會被視為過晚 available_date，不得形成 candidate row。
- 2026-06-16：補上授權 PIT 月營收公告日 CSV 架構邊界；`--pit-csv` 只接受具 source_version 的 point-in-time 匯出檔並產生候選 mapping，不寫正式 mapping、不回填 SQLite、不接 ScoringEngine。
- 2026-06-16：補上 GitHub public archive source audit 架構邊界；commit first-seen 可作未來 PIT 候選方法，但目前已檢查 public repos 皆未提供可追溯 daily snapshot，因此不新增 `github.*` allowed source。
- 2026-06-16：新增 MOPS snapshot / FinMind create_time 候選抓取器架構邊界；兩者只輸出 candidate/raw evidence 到 output 目錄，不推定正式 available_date，不寫 `monthly_revenue_availability.csv` 或 SQLite。
- 2026-06-16：新增估值呈現政策 / adapter 架構邊界，確認只輸出相對估值區間與 diagnostics，不接 ScoringEngine，不產生目標價、合理價、上漲空間或買賣建議。
- 2026-06-16：新增 valuation data layer 架構邊界，確認資料層只建立受治理 observation 與同產業分位，估值輸出仍由 presentation policy 控制。
- 2026-06-16：新增 valuation metrics backfill 架構邊界，確認 `daily_prices.本益比` 需經 dry-run / confirm / backup workflow 才能寫入 `fundamental_valuation_metrics`，且不接 ScoringEngine。
- 2026-06-16：新增 Abnormal Fundamental diagnostics 架構邊界，確認異常基本面只進 Research metadata 與 Daily Decision Desk risk prompts，不改財報、不改 score。
- 2026-06-16：新增 TPEX daily price backfill 架構邊界，確認官方 TPEX daily close quotes 只能經 dry-run / confirm / backup workflow 補寫 `daily_prices`，不修改 `companies.csv`、fundamental tables 或 scoring。
- 2026-06-18：更新 TPEX daily price 架構邊界，確認日常 / 手動 / 背景流程以官方 afterTrading historical endpoint 補缺少日期，SQLite sync 同時讀取 TWSE `daily_price/` 與 TPEX `daily_price_tpex/`，並 upsert `daily_prices`；背景補齊狀態寫入 `DATA_ROOT/meta_data/tpex_full_refresh_status.json`。
- 2026-06-16：更新 SQLite / broker flow 邊界，確認 `broker_flows` 唯一鍵需包含 `trade_type`，且 SQLite Inspector 顯示 alias 不得影響表格 model 取值。




2026-10-03後續驗證：見 `docs/06_qa/FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md`。current fundamentals 為weekly成功後的獨立writer；current revision與正式PIT分離，decision date使用Asia/Taipei、market cutoff保留獨立日期；Evidence依child stdout/summary/report與來源品質驗收。個股研究提供明確保存來源／指定股票分析及獨立技術觀察，仍守正式ML來源修訂隔離。
