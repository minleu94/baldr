# PROJECT_SNAPSHOT（必讀｜目前狀態）

# 2026-09-21 個股研究資料鏈查核

正式資料只讀查核已完成：`D:\Min\Python\Project\FA_Data\sqlite\twstock.db` 的 2026-09-21 `daily_prices` 查到 1,968 rows／1,968 codes，`technical_indicators` 查到 1,965 rows／1,965 codes；2382=344.5、3207=38.25、9935=18.2、1418=17.55 的查詢 rows 日期均為 2026-09-21，並完成日期／重複鍵／raw 對照檢查。這只證明本輪查詢範圍內的存在性與一致性，不代表官方交易所全域真值或全來源同日 fresh。

目前高風險資料邊界：formal institutional／credit 最新到 2026-09-08、TDCC 最新到 2026-09-04；月營收／季報 PIT 仍有 expected period 與 announcement／available-time 缺口；broker coverage 依股票不同（2382 到 9/21、3207 到 8/20、9935 到 9/14、1418 無 formal broker row）。1418 Paper blocked 分類為 candidate／lineage 缺件，不是 price corruption。候選 DB 的 rows 不得替 formal SQLite freshness 認證；`candidate_only=true` receipt 現由 read service 排除。

本輪未寫入 formal data、未重建／回填／重跑 scheduler、未更新 learning 或交易狀態。資料日、可得時間、PIT／current、source coverage 與 candidate-only 限制須在研究報告中分開判讀；缺件不可補 0。完整 evidence、SQL、focused QA 與 freeze 後整合 QA 見 [2026-09-21 個股研究資料鏈 Incident QA](../06_qa/STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)。

2026-09-21 候選池提醒呈現修正：首頁與每日決策已共用逐股原因、資料日／品質與查看步驟，缺前次分數不再只顯示籠統人工判讀；首頁一般觸發提醒導向候選池。候選表以可讀的「推薦來源」狀態替代原始識別字典，保留內部 exact identity。此為呈現修正，不改指標觸發、推薦評分、資料或交易權限；操作見 Manual 第 7.1 節。

## 2026-09-21 V5 日常操作與可讀性工程狀態

工作台、候選／研究／持倉、推薦／回測與導覽的 bounded presentation slice 已完成 frozen QA evidence：首頁優先顯示每日重點與下一步，日常／進階研究／系統維護分層，研究報告深頁按需繪製，缺 OHLC 可退回 close chart，錯誤保留白話恢復入口。A／B／D 的 final screenshots 已由 root 以正式 theme 審查；before／after 只在 30-row isolated fixture、2 samples、in-process boundary 下成立，不能外推 production dataset。

本輪 mandatory update pytest、QA validator、全域 mypy、changed Python py_compile、frozen manifest 與 isolated after perf 均已保存。精選整合 route 為 `299 passed, 1 warning`；`test_workbench_source_service_reads_real_read_only_sources` 已精準核對 seeded 2330 portfolio alert 的來源、原因、trace、drill-down、action 與 `write_intent=false`，並保留完整 background evidence feed。pytest cache warning 已獨立記錄，不影響測試結果。

最新 UI freeze evidence 以 `output/qa/incident_20260921/ui_readability/freeze_final_v2/summary.json` 為準（`passed`，offscreen）；all-pages focused route 為 122 passed／1 skipped，UpdateView 84，validator 25 passed／4 skipped，mypy 638 source files，changed Python py_compile passed。freeze 後 affected integration route 為 135 passed／1 skipped；全頁 loaded/error／極長真實資料未全部重演，native window／screen-reader 未測試。

版本名稱為「V5日常操作與可讀性工程」。這是工程可用性／導引進度，不是正式 V4／V5 gate、V6 user-level personalization maturity、自然 learning 效果或 production data readiness；原有 formal／natural／cross-page pending 保持不變。

本輪 UI 整合修正已納入工作樹：左側導覽群組與項目左對齊；個股報告換股會清除舊報告，同股 reload 失敗／取消會明示 last-good data 並保留 Journey 原因；來源摘要與完整 source trace 分層呈現；持倉頁分開日常正文、日期／原始 timestamp、Paper health 與模擬／歷史資料，進階正文可捲動並保留可讀 splitter 比例；工作台與說明按鈕把 machine token 轉為白話。這些是呈現與導引修正，不改資料、評分、交易或 writer；portfolio footer pane freeze 後的 mandatory integration QA 已通過。

> **2026-09-17 HEAD 校準**：目前文件基線為已提交 `0219d709`（C P1 bounded
> next-day inference／projection provenance），並承接 `9a9e778b` 的 Qt 關閉修復。已驗收的 bounded slices 包含
> `5a3ed5db`＋`ef594007` Position Health、`a4996cba` `user_declared`、`031e11ab` Continuity
> Review Workbench R1、`89a264f6` PIT reader/caller、`086ba60c`＋`0aaf0dff` BankTaiwan
> root guard／受控 retry，以及 `94d30b51` calendar／inventory audit。`0219d709` 已完成
> training／inference source 與 PIT hash 分離、共享 schema／transform compatibility、immutable
> hash-verified projection receipt、exact result／candidate／date／cost readback、normal UI
> default UUID → save → exact readback 與 identity conflict fail-closed；rule top-N selection
> authority 保留不變。相關 bounded QA 為 75 tests、mypy 9 source files、ML boundary guard
> 509 inspected／0 violations，詳見 [P1 provenance audit](../06_qa/DAILY_PROBABILITY_LEARNING_NEXT_INCREMENT_AUDIT_2026_09_15.md)。
> L 的官方 taxonomy source chain、完整跨頁整合、自然 evidence 與 V4 formal Gate 仍待完成；本工作樹另已
> 接上 C-owned V6 personal capture／read／ACK／明示 action／evaluation bounded slice，但尚未形成正式
> personal sample。下一順序仍是 **L source chain → 整合使用流程 → 以真實 user decision/outcome evidence
> 驗證個人化效果**，不把工程接線、fixture、replay 或 `natural sample=0` 縮寫成 V4／V5／V6 完成。

2026-09-18 core static follow-up 的 12 個 production files compile／mypy clean，float／
look-ahead quant guard clean；global ML shadow boundary re-inspected 518 files，仍保留 4 項
既有跨層 import residual，沒有以本輪 allowlist 掩蓋。這 4 項 residual 不改寫上述
personal／natural／formal readiness 邊界。

## 2026-09-21 晨間排程與資料接線修復

五項晨間／週排程 action 均仍指向 repository canonical CMD wrapper，且 2026-09-21 最終
`LastTaskResult=0`。Evidence dry-run 已修正隔離 Paper status schema／path、Frozen Rule producer
status、Position Health market-lane warning projection、CMD／PowerShell orchestrator parity、唯一 log 與
bounded Exit timeout；Windows task 連續兩次同日實跑皆 exit 0。Position Health proposal 改用
`position_health_transitions_v2.sqlite` 的 semantic identity，同一市場 rows 重跑保持 5 筆且
`persistence=idempotent`；舊 v1 DB 保留 immutable audit，不搬移未核准 proposal。

Phase3C institutional／credit candidate DB 已驗證 2026-09-21 兩市場 source coverage、無 natural-key
duplicate；freshness 改讀明確 candidate DB，不再以正式 DB 舊 candidate tables 誤判。月營收 2026-08
current observations 已受控 apply，但 formal monthly／statement PIT 仍缺 announcement／availability／
revision evidence，因此 freshness 合理維持 fundamental degraded。Evidence 最終為 `degraded` 而非
`failed`：工程 blockers 已清除，剩餘是 1418 position lineage 與既有持倉 thesis 人工欄位、以及
自然 outcome maturity；仍不授權 formal credit、production Evidence 寫入或自動交易。
05:30 read-only heartbeat prompt 已同步上述 candidate／formal／Position Health 判讀與 timestamp log
pointer；排程時間、target thread 與「不重跑、不修復、不寫檔」邊界未變。

## 2026-09-18 ABC bounded follow-up

本輪核心合併 validation 為 **168 passed**，包含 A daily-main、B cost 29 cases、strict
resolver 11 cases、wrapper 與 source-contract coverage；standalone natural CLI 的真實
provider fixture 另 **3 passed**，兩組測試檔不重複，合計 **171 passed**。先前 focused
slice 的 `77 passed`（A wrapper／identity／durable receipt `33`、B maturity calendar
wiring `27`、C learning-evidence denominator projection `17`）僅作 component/history
分解，不再加回核心總數。

### A capture repair

`run_scheduled_decision_evidence_capture.py` 已修正 parent／child temporal receipt 的精度邊界：
`decision_at`／`captured_at` 維持完整 aware ISO precision，child 不再以整秒重建 hash context。
wrapper／identity／durable-receipt focused suite `33 passed`，snapshot／evidence child與 service suite
`24 passed`，合計 `57 passed`；py_compile、targeted mypy 與 quant guard 亦通過。每次合法 run 另保存
subsecond+UUID immutable receipt、raw child stream bounded artifact、原始 byte count／hash／truncation、
OS returncode／timeout 與 latest pointer；receipt 或 artifact I/O 失敗 fail closed。9/17 latest failed status
仍保留為歷史 receipt，不重跑、不回填、不授予 natural／Paper／Formal credit；合法下一次排程
可依既有 latest pointer 規則自然產生新 status，但仍須驗證新的 parent／child hash readback
與 evidence step，不追認舊失敗。
詳見 [每日 Decision Evidence Capture 修復 QA](../06_qa/DAILY_CAPTURE_RECOVERY_2026_09_18.md)。

2026-09-18 原排程 EOD research run 的 bounded readback 於 2026-09-18T12:26:13Z 觀測：
run_id 為 `20260918T122502797364Z-414cfa43c1b0`，status=`passed`、receipt=`complete`，
evidence／snapshot child 均 returncode 0 且 saved，events `1098/1098`、duplicates=0、
failures=0、snapshot sections_missing=[]；receipt SHA-256 為
`95bc1d0addebe391e06be5b4a0b6353beca4c385ea493d7611c8dd8605cf2533`。quality counts 為
degraded 1080、estimated 3、observed 15，warnings 702。這是 research-only capture，
`natural_authority=false`；audit 本身未觸發 scheduler 或修改正式 source。[readback raw JSON](../../output/qa/decision_evidence_capture_readback_20260918/readback_20260918T1226Z.json)
保留 immutable context／identity hash 與 4 raw hash 對帳。

### B natural learning trace

9/17 forward receipt 的 11 個 qualifying events 中，5d 為 `ready=1`、`pending=10`，
10／20／60d 仍為 `ready=0`。唯一 5d ready row（1454）是 close-to-close forward outcome
研究，gross `-195bp`、TAIEX benchmark `-139bp`、excess `-56bp`；事件沒有
candidate／probability／prediction capture／label／calibration policy binding，因此不進
natural probability calibration，也不代表可成交 entry 或收益證據。BankTaiwan 9/18 排程
已實際執行（台北 `20:50:03–20:50:50`），wrapper run
`2026-09-18-attempt-001-91feea81e0f4` 以 `failed_dependency`／child exit `2` 收尾，
原因為 `live_capture_blocked:prospective_price_up_source_not_ready:technical_prospective_source_not_ready`。
technical publication 本身為 passed，source hash／value／lineage 與
`prospective_feature_snapshot_verified` 均為 true，`missing_technical_symbols=[]`；但 requested 7 檔中
`missing_source_symbols=[1569]`，當日 technical receipt 只有 TWSE、TPEX 到 9/17，
`prospective_available=false`，所以 live capture 保守阻擋。[有效核心 readback](../../output/qa/banktaiwan_learning_readback_20260918/readback_20260918T130922Z_core.json)
保存了本次 blocked 結果。這是 1569 同日來源 custody 缺件，
不是 technical computation failure；不降低 gate、不剔除該樣本湊數，既有 formal technical source
contract unverified 仍是原有 formal gate。有效 captures 仍只有 9/15–17 三份、18 rows、matured=0；
replay 不折抵 maturity gate，9/18 Decision Evidence capture 的 1098 events 也不能視為新增
calibration 成熟樣本。
Forward maturity calendar wiring 的 bounded suite 為 `27 passed`；annual plan 只提供 planned
maturity diagnostics，保留 legacy symbol-price-row-offset outcome contract，不改 READY／return basis 或 natural
credit。共用 annual cache refresh wiring 另有 `12 passed`（含 annual-64 最新候選 regression，
compile／mypy clean）；這是增量驗證，上一輪核心合併仍為 `168 passed`、standalone CLI `3 passed`，
不把它宣稱為新的 `172` 合併 suite。詳見 [Natural learning trace](../06_qa/NATURAL_LEARNING_TRACE_2026_09_18.md)、
[Forward maturity calendar wiring](../06_qa/MATURITY_CALENDAR_WIRING_2026_09_18.md) 與
[Maturity calendar refresh wiring](../06_qa/MATURITY_CALENDAR_REFRESH_WIRING_2026_09_18.md)。

同一觀測日的 source quality 仍需單獨判讀：2026-09-18 `data_update_quick` 為
`passed_with_warnings`（TWSE passed、TPEX warning），`data_freshness` 明示
`tpex_daily_price_file_missing:20260918`；13:00:25–27Z 的兩次官方唯讀 GET 後續都回
HTTP `403`、Cloudflare HTML，且沒有進入 parser。這只能證明 probe 時點的 HTTP 阻擋，不能追認
早上排程的原始根因；同輪 recommendation degraded 的主要診斷為
`relative_strength_liquidity`。這是來源覆蓋／品質警告，不是 decision capture 失敗，也不能由跨日
code count 推定官方應有 coverage 或 API 根因。A 的 TPEX range 修正保留每個來源失敗的
`failure_diagnostics`（requested／fallback／range phase、message、`diagnostic_count`、
`source_date` 與 bounded row counts），並在取消或後續 exception 時保留已收診斷；本輪 UpdateService
完整測試為 `65 passed`（僅既有 pytest cache permission warning）；另有本輪不重疊的 resolver
`12 passed`，兩組合計 `77 passed`，不能與歷史 `171 passed` 相加。source gap 與 bounded 修補邊界見
[TPEX source gap diagnostics](../06_qa/TPEX_SOURCE_GAP_DIAGNOSTICS_2026_09_18.md)。

### 2026-09-19 TPEX 9/18 official raw 歷史補入

後續合法取得的官方 `afterTrading/otc` raw 於 `2026-09-19T07:20:33.071218Z`
完成保存，並已完成受控 insert-only backfill：正式 DB
`20260918` rows 由 `1090` 增至 `1958`（新增 `868`），1569 正式 row 為
`52.00/57.00/52.00/55.50`、成交股數 `5,164,000`；CSV 亦保存 `868` rows，custody
raw `146419` bytes，SHA-256 為
`sha256:2eae9b5185bfde35ddb63ed6ed4d331f3a97a195229394a693db54ddc9739e62`。
獨立唯讀驗收確認 apply 前既有 rows hash 未變、normalized keys overlap `868`、conflict `0`。
完整來源、DB/CSV/custody hash 與 bounded 限制見
[TPEX source gap diagnostics](../06_qa/TPEX_SOURCE_GAP_DIAGNOSTICS_2026_09_18.md) 及
[independent readback](../../output/qa/tpex_source_acquisition_20260918/formal_db_preflight_20260919T072937Z/independent_readback.json)。

這只完成 9/18 daily-price source 的歷史資料補入與 custody 保存；原先 9/18 decision
capture／BankTaiwan failed receipt 不回填或改判，receipt 的
`historical_pit_status=not_proven_by_after_close_capture` 與
`formal_source_contract_eligible=false` 仍有效，也不授予 natural learning、calibration
或 decision-time credit。Fubon／FinMind 的 `5,422,427` 只記為候選回應成交股數，與官方
afterTrading `5,164,000` 不視為同一 volume 口徑。
本次 `9-18-tpex` heartbeat 已 `PAUSED`；來源晚於原始 decision capture，故不追認 old
natural／decision-time evidence。

本輪 run identity 唯讀審計確認：wrapper `run_id` 是排程嘗試／immutable receipt identity，
`evidence_events.run_id` 是事件／研究 lineage key，scheduled child 未接收 wrapper run id；事件的
完整 `metadata.capture_context` 與 temporal／identity hash 已可供語意對帳。natural evidence 讀取
immutable prediction capture、source contract 與 natural receipt，不依賴 `list_events_for_run()`，
因此 9/18 event rows 的空 `run_id` 不構成 daily natural evidence blocker。隔離契約單測為 `1 passed`；
不新增 run-id 接線。

### C personalization limitation

目前 active calibration pointer 為 `rule_only`、`candidate_id=null`，consumer 的
`active_identity()` 為 `None`；沒有 verified projection receipt，因此 real scope 的
personal capture 為 `0`。`action_not_recorded` 不代表 prediction 失敗，也不要求現在選擇
scope；在既有 authority／promotion gate 通過前，不得建立 active candidate、回填 capture，
不得把 shadow／fixture 冒充 personal delivery，也不得僅憑 technical ACK 授予 natural／calibration credit。
C 的 learning-evidence denominator projection focused suite 為 `17 passed`：legacy lane
經 conflict 排除後為 `2 captures／16 rows／2 decision dates`，latest snapshot 為 `14 rows`，
`capture_conflict_count=5`、`capture_scan_status=complete`；這個累積分母與 latest snapshot
分開呈現，不能與 BankTaiwan lane 混用。新的 policy binding 尚未以真實成熟 positive receipt
驗證，`policy_binding_status=unknown`，因此不得宣稱 adoption 或升級為 ready。詳見
[Personal Delivery Activation QA](../06_qa/PERSONAL_DELIVERY_ACTIVATION_2026_09_18.md) 與
[Learning Evidence Denominator QA](../06_qa/LEARNING_EVIDENCE_DENOMINATORS_2026_09_18.md)。

### Strict natural label binding（2026-09-18，進行中）

本輪新增的 natural producer integration 以 `NaturalMaturitySessionResolver` 綁定 exact 20
個官方交易 session；resolver proof 同時保存 calendar evidence、TAIEX capture-day baseline、
exact endpoint、resolver identity/version 與 bounded source fingerprint。個股只讀 capture day
與 endpoint day，缺中間個股列不會向後滑動。producer 會在讀個股前後核對 proof 的 source DB
與同一 SQLite bytes stat；缺 official calendar、TAIEX baseline／endpoint、stock endpoint、
source-contract anchor、未收盤／future row 或 evaluation clock 時維持 pending。

strict receipt 的 `evaluation_at` 必須是 aware datetime，且 `Asia/Taipei` 日期等於
`evaluation_date`，不得使用 future wall clock；authority 會以已驗證 capture source contract
的 `source_database` 作 expected anchor，不能採用 receipt 自報 path。舊 generic forward
仍是 legacy symbol-price-row-offset／return-basis 研究結果，不可與 strict natural receipt
混算或授予 natural calibration credit。`run_scheduled_forward_outcomes.py` 的 calendar cache
參數只控制 generic forward 的 bounded maturity diagnostics；standalone natural CLI 現已依同一
source DB 建立 resolver、傳入 aware Taipei checked clock，並支援 annual／temporary cache
參數；缺 calendar、日期不一致或 source proof 不足仍 fail closed。

2026-09-15、16、17 的三個 real-market captures 已於 2026-09-18 重驗並標示
`source_verified`；這只證明當次 source custody／bytes 對帳，不等於 20-session matured
sample、personal delivery 或 adoption。
annual calendar cache 的最新唯讀 refresh receipt 於 `2026-09-17T23:15:02.193862Z` 觀測為
`cache_valid_for_forward_horizon`，與 ML forward／Paper 共用
`output/paper_execution_eod_replay/calendar_cache/`；目前有效期限為
`2026-09-21T23:15:03.532140Z`（台北時間 2026-09-22 07:15）。refresh 由既有共用 ML
forward／Paper 路徑負責，strict natural consumer 只讀驗證後 cache，缺失或過期仍 fail closed；
cache 不宣稱永久有效。主機 Task Scheduler 的 Enabled／LastRun／NextRun 因權限不足未由本輪證據宣稱。
strict resolver 的 compact／ISO SQL range guard 與跨年等價 regression 已包含在核心合併驗證。

C-owned component slice 保留為 25 passed／2 deselected、strict resolver／producer 11 passed；
A daily-main 與 B cost 29 cases、resolver 11 cases 已納入核心合併 **168 passed**，standalone
CLI 真實 provider fixture 另 **3 passed**，合計 **171 passed**（測試檔不重複）。這些是工程
驗證數字，不授予 natural adoption 或 formal readiness；既有 4 項 global ML shadow boundary
residual 仍以專屬 raw QA 如實保留。

## 2026-09-17 A／B／C bounded status（working tree）

### A Paper／calendar／Recommendation

2026-09-17 的正式 Recommendation receipt 已由 root 逐欄核對 source、calendar 與全部 14
candidate file hash；calendar capture／availability 為 2026-09-14，早於 candidate decision
2026-09-17。這 14 筆仍是 candidate-only，不能當 Paper 或 Formal evidence；`1418` 目前只有
rejected sell、沒有 filled entry source，維持 unproven。Paper 完成判定必須同時有同一 decision
date 的 terminal run、latest／immutable phase receipt、`calendar.available <= decision` 以及
source／state hash；heartbeat 舊 snapshot 不構成完成。

Paper 的 default `calendar=None` → `CALENDAR_CACHE_ROOT` actual-loader 正反例已通過 2 tests。
legacy 05:45 的 2026-09-17 實跑已恢復為 `passed_with_warnings`；BankTaiwan 為 pending 18、
matured 0；raw PIT 為 invalid 7、unavailable 16,913。official-events 的
`prior canonical raw lineage missing` 已定位並修復為 reader compatibility gap；A lineage path
跨檔 focused QA 為 `8 passed`（`tests/test_official_market_event_prior_lineage.py` 單檔含 3 tests），
隔離 next-publication real chain output-only readback（`output/qa/official_event_next_publication_output_only`）
為 `runs=1`、`events=28,636`、`raw=95`、`missing=0` 且 source bindings 均在 self-contained output 內。
先前 failed latest receipt 仍保留；output-only readback 已由 root 以 `_load_prior_publication` 驗證，
但正式 job 尚未重跑。因此不能歸類為真實 raw 缺件或純 external missing，也不能宣稱 Paper／Formal
完成。唯讀 ancestor custody review 已核對 current 37＋ancestor 43 共 80 個 required raw hash、
missing 0 且 raw bytes 全驗證；artifact 為
`official_event_ancestor_custody_review.json`（SHA256 `bc4607a46c10513700e1a9c531be81f502e87aac1219327b464f5f703207f280`）。Paper 既有
9/7 與 repository 9/14 狀態及 runstate 缺口仍保留，詳見
[A operations latest status review](../06_qa/A_OPERATIONS_LATEST_STATUS_REVIEW_2026_09_17.md)。

正式 input readiness artifact（`formal_input_readiness_20260917.json`，SHA256
`e75d4130d486dd2b6bae0dae532afc8040765ff51e2f8f53497738b24a839614`）的原始 aware clock 為
`training_as_of=2026-09-17T11:19:45.4764372-07:00`、`created_at=2026-09-17T11:19:46.502565-07:00`；
loader 以 `Asia/Taipei` 轉出的 `training_as_of_date` 是 `2026-09-18`，readiness 為 `0/3`。
三個 configured input path 仍指向 `clock-20260819` 且 `prospective_output_not_published`；這只證明
configured input 缺失，不能外推 D 槽沒有其他產物。

### B historical context／label assembly

B 已修正 historical feature 的 observed market／stock date union assembly：requested cutoff、
market gap 與 stock gap 保留 explicit empty slot，不把上一個 market date 冒充 cutoff，也不以
trailing row count 壓縮 missing-middle session。label builder 以 market calendar keyed lookup，
缺 stock row 直接 diagnostic／block。bounded report 以 row-count、observed-calendar exact join、
value completeness 與 horizon completeness 分開；`market_indices DISTINCT 日期` 不是 official
complete session calendar，因此 horizon complete、formal/training credit 均為 false。報告與 residual
見 `C:\Users\archi\.codex\visualizations\2026\09\17\01a0aea7-bd95-70c2-8ff6-a355b6b1f216\b_historical_context_inventory_20260917.json`
及同資料夾同名 `.md`；report `report_hash`=`sha256:06304a44340e3cfad623c2710e6bd84cd1d479950df0c344623ba3a2ad8f1b72` 是排除自身欄位後的
canonical logical hash，JSON file SHA256=`f6c3d15bb04f93782c1b42a903a3934fdd30109f6039c0d541c3bf14a7fef698`。

### C personalization

C 的 fit producer／persistence／CLI、artifact persistence 與 readback engineering 已 bounded
accepted：fit runner／CLI／calibration／read service focused suite `41 passed`，wrong-scope
empty-evaluation 為 exit `2` 且不產生 evaluation／verified binding；C 五檔 explicit-package-bases
mypy clean。source fingerprint artifact 為
`c_personalization_fit_acceptance_20260917.json`（SHA256 `d45033e0ea8a4c418150df685e96d26d7425872a6c633695f0aa752054f0a3d3`）。
正式 D 的 real scope／delivery／human action／natural outcome 仍缺，不能授予 formal／natural
credit 或 V6 adoption。

9/17 PIT completion audit 亦維持 read-only candidate-only：artifact
`C:\Users\archi\.codex\visualizations\2026\09\17\01a0aea7-bd95-70c2-8ff6-a355b6b1f216\PIT_COMPLETION_AUDIT_20260917.json`
SHA256=`38fbb42fd6134e70068a01454b659094610d3783c160c39eb42991fe8d7796cf` 記錄的 denominator
refresh attempt 在 DNS／HTTP response 前失敗，未進 CSV parser；同 URL 的 9/11 已有可解析 artifact，故不定性
為 parser code defect。另有晚到的唯讀 transport probe receipt
`output/qa/pit_denominator_urlopen_transport_probe_20260917_receipt.json`：單次
`_fetch_one`＋`urlopen` 於 `2026-09-17T19:18:23Z–19:18:26Z` 得 HTTP 200、672,624 bytes，body
SHA-256=`7954eb03c42e22704f71ff39ef7e20c900b0334b9661cb97d1f086f813b53e30`，與 requests
結果相同且 URL metadata 無漂移。這只證明該觀測時點的 transport／URL metadata 可用；觀測晚於
9/17 PIT cutoff，不能回補 same-day denominator，也不能授予 formal sidecar／Paper／formal credit。
9/17 same-day denominator／taxonomy publication 仍未完成，security lifecycle 僅 historical research
replay、formal input／owner license gate 與 real scope／human action／natural outcome 仍缺；parent `5371`
與 current `3718` 不得 carry-forward。既有 residual 依序分為 D read-only／candidate10 apply 與 heavy
rebuild holds、未來合法時窗的新 PIT／Paper capture 與 actual terminal receipt、真實 human thesis／actions／
entry custody 缺件、historical source 缺件、natural maturity，以及 formal input／owner license gates；
全局 ABC 仍為 `in_progress`，不得宣稱 formal job／Paper／V4 完成。

目前 module trees 全域 mypy 已由 root 以指定範圍驗證為 `Success: no issues found in 630 source files`
（scripts excluded，僅 2 untyped-body notes）；全局 ABC 仍 `in_progress`，不因 A／B bounded slice
或 C fit producer 存在而宣稱正式完成。

## 2026-09-17 C 線個人化真實來源接線與 completion audit（working tree）

本工作樹已完成 C-owned 的 bounded wiring：`RecommendationService` 的實際 producer temporal
context 與 verified training label custody 可經 `RecommendationSaveRequest`／既有
`RecommendationRepository` create-only save/readback 綁定 local research capture；MainWindow
save 後由 window-owned `JournalService` 追加 technical delivery ACK。`PersonalizationReadService`
與 `PersonalizationProjectionService` 以 exact `result_id`／stock／scope／prediction／receipt／
horizon／cost／label／return identity 讀取既有 Recommendation、Journal 與 Evidence sources，
分開呈現 prediction／action／outcome／evaluation 分母、pending／missing／exclusion 與 late delivery。
`PersonalizationDecisionRecorder`／CLI 只在 delivered projection 通過後追加新的 typed Journal
revision；舊 action 不 retrofit，UI save 也不推導 human action。

| 項目 | C 工程狀態 | 正式 production 尚缺／責任 |
|---|---|---|
| prediction／capture／delivery | normal save、technical ACK、retry／CAS／readback 與獨立 real MainWindow process probe 已驗收；probe `1 passed` | 正式 D 槽沒有 scope-linked capture／ACK；需由合法 producer／caller 在 intended root 產生真實新紀錄，fixture 不算樣本。 |
| 真實 scope | local scope 只在 producer capture 時由明確 context／receipt 綁定，不從 profile／holding／portfolio／source 猜測 | D 槽沒有 real user scope；local scope 不代表人類身份，需真實使用者／owner 明示或接受本機 research scope；本任務不代創。 |
| human action | recorder／CLI 已有 preflight、exact Journal revision、request retry 與 clock／delivery gate；不自動 action、不改 legacy | D 槽沒有 personal human action；必須由真實使用者明示 action／actor／action clock。 |
| natural outcome／maturity | read／evaluator 可 exact join、辨識 pending／matured missing／invalid／duplicate，並區分 natural／paper／declared／replay | D 槽沒有 scope-linked natural outcome；需等待同一 prediction 的自然市場結果成熟，Paper／fixture／replay／user-declared 不可替代。 |
| personal fit artifact | fit producer／persistence／CLI、artifact persistence、reader 與 evaluator bounded engineering 已驗收；fit runner／CLI／calibration／read service `41 passed`，wrong-scope empty-evaluation exit `2` fail-closed | 正式 D 槽仍無 real scope／delivery／human action／natural outcome；fixture／replay／`natural sample=0` 不算 formal／natural sample，不能宣稱 V6 adoption。 |

本段只更新 C 狀態；A／B、L official taxonomy、K cross-page integration、正式 D、scheduler、
global active pointer、promotion、broker／order 與 V4 formal Gate 的未完成／外部責任維持原判定。

## 2026-09-15 PIT 產業來源 reader 與 caller 驗收

已完成 prospective PIT 產業 membership 的 bounded engineering slice：新增唯讀
`PITSectorMembershipReader`，重新驗證 sidecar／machine candidate 的 envelope、rows／canonical
hash、官方 raw custody、clock manifest、score-bearing universe identity、taxonomy source、
available／effective cutoff、market scope 與同日衝突。`usable` 與 `industry_filter_usable` 分離；
缺 taxonomy、未知 classification version／產業代碼、部分分母或特殊證券時，Industry Strength
與 Recommendation fail closed，不以 current `companies.csv` 冒充歷史 PIT。

`TWStockConfig` 已提供明確的 PIT artifact／raw／clock／universe／taxonomy path 與環境變數入口；
同一 reader 已接入 Industry Strength、Recommendation 及 non-UI Decision Desk composition。
`formal_rule_source_producer` 同步保存實際 `scores_bp` 與 universe hash input rank order，供
reader 重建 score-bound universe hash。完整測試與限制見
[PIT 產業來源與 caller 驗收 QA](../06_qa/PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md)。

本切片 QA 為 PIT reader／caller 16 passed、相關回歸 66 passed、machine producer／consumer 16
passed、全域 mypy 619 source files clean。D 槽既有 prospective artifact 的 raw custody 通過，
但因缺 score-bearing universe identity 與 taxonomy source 仍為 `unavailable`；本段不代表
historical backfill、Formal OOS、promotion、broker 或 real-money eligibility，也未改寫正式資料。

本段驗收的是 `89a264f6` 的既有 PIT reader／caller bounded slice；L 線尚未提交的官方
taxonomy raw producer／v3／publisher／reader／caller，以及 PDF 與 preopen completion-time
修正仍屬待驗收，不得把本段當成 L 線官方 taxonomy 端到端完成。

## 2026-09-15 BankTaiwan 首次 05:50 排程失敗與成本 root guard 修復

BankTaiwan 首次 `baldr-recommendation-calibration-learning-banktaiwan-shadow-daily` 執行於
`05:50:03–05:50:05 -07:00` 回報 `failed_dependency`、child exit `2`、
`decision_reason=cost_scenario_root_conflict`。原因不是資料庫、snapshot 或 candidate 訓練失敗：
舊 `recommendation_learning/challenger/current.json` 只有 candidate identity，沒有成本情境欄位，
舊 reader 將缺欄位 marker 預設解讀成 legacy fixed 50 bp；同一 root 的 latest status、decision
receipt 與 candidate 實際屬於 `banktaiwan-electronic-estimate`，hash 為
`sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450`。

修復已補上新 challenger writer 的完整 scenario metadata，並將舊 pointer 相容讀取限制為完整
candidate identity anchor 與 canonical manifest／artifact bytes／freeze／cost contract／label
registry 重驗成功；欄位缺失、篡改或 artifact 遺失均 fail closed。隔離成本測試為 `14 passed`，
真實 BankTaiwan 舊 pointer read-only 回驗成功且 root conflict 為 `None`。其後受控 shadow retry
已於 `06:33:12–06:33:25 -07:00` 完成，wrapper／child 均 exit `0`，產生
`completed_waiting_natural_maturity`；`shadow_only=true`、`formal_order_allowed=false`，natural
sample 仍為 `0`，沒有 promotion 或正式 order side effect。第二次同參數驗收回報
`idempotent_replay=true` 且未啟動 child。完整 receipt、hash、回歸矩陣與限制見
[BankTaiwan 首次排程失敗 QA](../06_qa/BANKTAIWAN_FIRST_SCHEDULED_RUN_FAILURE_2026_09_15.md)。
正式 scheduler 未被重跑；本次受控 retry 也不能代替自然 forward evidence、formal PIT 或 observed
cost 門檻。

## 2026-09-15 user_declared Holding Research Increment 2 工程驗收

已完成與 Paper／正式 Portfolio fill lane 分離的 `user_declared` 持倉研究切片：新增
append-only JSONL exact holding／revision identity、CAS 修訂、封存歷史、PIT cutoff、
source quality／SHA-256／availability custody 檢查，以及既有 Recommendation／
PortfolioConditionMonitor 的 condition read model。Saved Recommendation 只在聲明日前
baseline 與評估日 current 是不同 snapshot 且 profile／version／score identity 相同時
提供可比較規則；缺 baseline、self-compare、future、stale、source 不完整或只有價格／
成本時維持 `WAIT_CONFIRMATION`，不把價格本身當成 HOLD。

Portfolio 右側「聲明持倉研究」提供獨立研究 UI：表單預設收合，主表以精簡中文顯示
股票、股數、聲明成本、研究建議、研究狀態、目前價格、帳面變化與原因；Entry lineage、
Fill verification、source trace 與 raw flags 留在技術詳情。1366×768／1700×1100 實際
視窗以頁內垂直捲動保持安全邊界換行與完整表頭／一列可讀；忙碌 refresh 以既有
MainWindow shutdown coordinator 合作取消並自然結束，不 terminate／wait。

Increment 2 QA 已完成：core／UI／Portfolio focused `43 passed`、TaskWorker／shutdown
`24 passed`、Update UI `84 passed`、Update validator `25／0／4`、全域 mypy
`617 source files` clean；隔離 writer 由實際 Portfolio UI 新增／修訂至 revision 2，
獨立 reader 從同一 runtime root 讀回同一 notes／研究假設與兩筆 history，並確認一次
busy close、`app.exec()=0`、合作取消及無 forced termination。完整證據見
[user_declared Increment 2 QA](../06_qa/USER_DECLARED_HOLDING_RESEARCH_INCREMENT_2_QA_2026_09_15.md)。

本段只代表 research-only bounded engineering acceptance；不代表 Paper verified entry、
正式成交、realized PnL、observed slippage、calibration／effectiveness、自然 forward
evidence、V4 formal closeout 或 broker／auto action 開啟。正式資料原始檔與既有 Paper
identity 維持不變。

## 2026-09-15 Decision Continuity Increment C／Qt 關閉驗收

工程修復與隔離驗收已完成：`7e029933` 已交付研究 continuity 的跨頁 identity／journal／Workbench
readback 與跨程序 writer／reader；`9a9e778b` 另交付 5 檔 Qt 關閉修復，`MainWindow` 以
`DeferredDelete` 收尾、busy 狀態只合作取消並單次關閉，實際 OS process exit 為 `0`。`TaskWorker／shutdown` 為 25 passed、
Update UI 為 84 passed、Update Tab validator 為 25／0／4，全域 mypy 為 621 source files clean；
`7e029933` continuity 證據見 [Decision Continuity Increment C QA](../06_qa/DECISION_CONTINUITY_INCREMENT_C_QA_2026_09_14.md)，
`9a9e778b` teardown／OS exit 證據見 [Qt shutdown teardown QA](../06_qa/QT_SHUTDOWN_TEARDOWN_FIX_QA_2026_09_15.md)。

本段只代表受控、隔離的工程與程序生命週期驗收，不宣稱自然 evidence 已成熟，也不宣稱已
完整歸因使用者曾見的 memory-write popup；目前沒有把該 popup 的精確 PID／native stack
對上同一根因。正式資料、live trading 與自然前瞻證據邊界維持原狀。Workbench 本次驗證的是
顯示與跨程序讀回，不擴大解讀為所有 Workbench 狀態均已接線。

## 2026-09-15 Continuity Review Workbench R1 唯讀閉環

R1 已把既有 decision-continuity Journal 的 exact `(result_id, stock_code)` reminder projection
接回 Workbench review table 與既有 shared stock research／Decision → Outcome Journey。Portfolio
只有在保存的 Recommendation JSON 通過 `recommendation_result`、result id 與唯一 stock row 檢查時，
才沿用 recommendation identity；其他 source 不會升格。Workbench 主摘要顯示中文股票、研究意向、
台北檢討 cutoff 與原因，technical revision／snapshot／trace 留在詳情。

R1 的 producer-backed isolated acceptance 以 RecommendationRepository、EvidenceEventRepository、
JournalService／DecisionContinuityController、WorkbenchSourceService 與真實 Qt shared dialog 串接：
R1/R2 同股 2330、R3 多候選 2330／2317 均以 exact candidate 進列；Journey 顯示 5 日 ready、
10 日 pending、20／60 缺資料 unknown。Workbench click 前後 Journal bytes／SHA-256 不變；
透過既有 controls 明確改期後，獨立 reader 讀回同一 candidate、原始 accepted intent、新 revision
與 next_review_at。Evidence snapshot 只作已識別 result 的一致性檢查，不可單獨作 join key。

工程 QA 為 R1 projection／identity 8 passed、producer-backed Workbench／Journey／readback 與
barrier standalone busy-close 的合併驗收 9 passed；既有 Workbench／Portfolio／continuity focused
regression 93 passed，Journey regression 17 passed。1366×768 Workbench／Journey 截圖及 child
`app.exec()=0`、外部 process exit `0` receipt 均已保存。完整範圍、artifact 路徑、全域 pytest 的 12 個
failure node、目前 targeted recheck 與已確認／尚未判定分類見
[Continuity Review Workbench R1 QA](../06_qa/CONTINUITY_REVIEW_WORKBENCH_R1_QA_2026_09_15.md)。

本段仍只代表隔離、唯讀 research engineering acceptance：不代表正式 scheduler／broker、自然
forward evidence、投資有效性、V4 formal closeout 或 V5 product closeout；20／60 缺資料與全域
既有 governance／ML／PIT／UI lane failures 仍維持 fail-closed，不以 fixture 通過補發 formal credit。

## 2026-09-15 Position Health Increment 1 工程驗收

`5a3ed5db` 已完成既有 Paper `DailyPositionHealthTransitionEvaluator` receipt 到
Portfolio／Workbench 的 source-backed、唯讀 typed projection。新增
`PositionHealthTransitionReadService` 驗證 result／receipt hash、Paper snapshot／rows
hash、cohort、exact position identity、available／observed clock 與 freshness；Portfolio
人工 identity 與 Paper identity 不以 stock code 猜配，所有缺 source、future、stale、corrupt
或 scope conflict 均 fail closed 為 `WATCH`／未知。UI 只讀 persisted projection，不寫
receipt、registry、scheduler、ledger、broker 或 allocation，所有 action 維持
`research_only=true`。

工程 QA 已完成：health read／formatter `15 passed`、Portfolio／health `42 passed`、
Workbench／evaluator `66 passed`、source-provider `16 passed`、Update UI `84 passed`、
Update validator `25／0／4`，全域 mypy `615 source files` clean，受控 real Qt visual
runner exit `0`。完整記錄見
[Position Health Increment 1 QA](../06_qa/POSITION_HEALTH_INCREMENT_1_QA_2026_09_15.md)。

本段只代表 bounded engineering／read-only acceptance，不代表自然 forward evidence、
formal PIT、observed cost、broker execution 或 V4 完成。下一個獨立工程增量是與 Paper
lane 分離的 `user_declared` research-only layer 已由 `a4996cba`／Increment 2 QA 驗收；自然
證據仍是持續觀察線，尚未完成。後續不把 `user_declared` 再列為待驗收，改由 L 的官方
taxonomy source chain 先完成端到端，再接整合使用流程；C 的 P1 provenance 已由 `0219d709` 完成
bounded engineering acceptance。

## 2026-09-14 V4.2 prospective source custody 與每日學習現況

本節保存 2026-09-14 既有 shadow receipt 的運行觀察；該日 receipt 不能回溯改成 P1 或
V4.2 formal evidence。`719cf7a4` 已提交並驗收 C 的 bounded canonical learning runner、
training lineage、cutoff／ML boundary（88 tests、508 files guard 0 violations、production-scoped
mypy）；後續 `0219d709` 已補齊 P1 next-day inference／projection provenance 的 bounded
engineering receipt 與 exact result readback。下列 receipt 仍只能作歷史／運行 evidence，不能把它或
`natural sample=0` 解讀成 C／V4.2 formal 完成。

05:45 的 `baldr-recommendation-calibration-learning-daily` 已接到同一條有界 pipeline：先跑
官方日價／技術來源更新，再做 official market-event custody，接著保存正常 scheduled
recommendation snapshot，最後才呼叫 recommendation learning child。排程的有效順序是主機當地
05:40 `baldr-forward-outcomes-daily` → 05:45 learning；learning runner 仍以
`Asia/Taipei` clock 與 official calendar 判定決策日，不把主機時區當成市場資料日。所有
dataset、candidate、capture、evidence、authority receipt 與 pointer 仍只寫到
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\`；正式 market SQLite 以
query-only 讀取，`formal_order_allowed=false`，不寫正式 recommendation、`evidence_outcomes`、
Portfolio、Formal 或 broker state。

2026-09-14 的 durable source run 已留下可追溯但含警告的狀態：quick data update 為
`passed_with_warnings`，TPEx `20260914` 缺價並保留 bounded retry warning；technical publication
receipt 綁定 exact output rows／source hash。TWSE official event refresh 遇 endpoint redirect
異常而 fail closed，既有 verified prospective publication 以原始 raw retrieval time 與 SHA-256
做 durable replay，不能把 replay 解讀成當日新抓取。corporate-action adjustment sidecar 已有
prospective hash custody，但尚未形成可供 historical/formal eligibility 的正式 table／contract。

正常 `max-stocks=200` snapshot 目前是 partial／degraded：latest readback 僅有少量 eligible
recommendation（目前為 1 筆），其餘 cohort rows 被標為 degraded，且含 TPEx 缺價警告；這不代表
200 檔 cohort 已完整通過；不能把 partial snapshot 或 pipeline terminal status 當成自然
evidence 已完成。2026-09-14 04:22:11-07:00 的最新 wrapper 已完成，status 為
`passed_with_warnings`、blockers 為空；同輪 quick publication 於
`2026-09-14T04:21:27.181165-07:00` 完成，publication 為 `published`。臺銀 normal shadow
lane 的 learning child 已 `completed` 並保存 normal live capture：symbol source 為
`scheduled_recommendation_snapshot:scheduled_rec_20260914_042140.json:eligible`，只提供
`1528`；candidate 仍為 `rec-cal-29c1b6129396a3885a89d080`，沿用 stable experiment scope
`scheduled-experiment-ff4d2ab937e2c8b32bf2df04`；natural sample 為 `0`，decision 仍為
`retain_current`，原因為 `natural_forward_evidence_receipt_missing`。此前 single-class
training blocker 已由事前決定的 bootstrap 處理，沒有使用三檔 capture 代替正常 lane。
同輪 technical computation receipt 已在
`D:\Min\Python\Project\FA_Data_Shadow\scheduled\technical_indicator_publication\2026-09-14\0f533bde5119890a\receipt.json`
標記 `verified`，2148 檔股票的 bounded 真重算已完成並受該 receipt 約束。

這次 historical bootstrap 的 durable observation status 為 `recovered_completed`，selection policy
為 `time_stratified_eligible_dates`，manifest 位於
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\datasets\recommendation-dataset-da3d867b06b5436d\dataset.json`。
其 `initial_seen_start=2026-04-23`，bootstrap replay 的 selected date window 為
`2024-09-16` 至 `2026-02-11`；date overlap、row overlap 與 label boundary crossing 均為 `0`。
這些是 bounded training lineage 與分割觀測，不是當日自然 forward evidence，也不解除 formal PIT gate。

本次正常 lane 的新 immutable capture scope 仍為
`scheduled-capture-5f4de77ffb404af2`，路徑為
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\captures\2026-09-14\scheduled-capture-5f4de77ffb404af2\rec-cal-29c1b6129396a3885a89d080-850760d54413e019199be668.json`，
hash 為 `sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`；
natural evidence 仍 pending、sample `0`，decision 為 `retain_current`。今天另有明確三檔 controlled capture 成功保存
`1528,1558,1560` 的 feature-row、source-contract 與 adjustment manifest hash，狀態仍是等待
自然成熟；這筆 explicit capture 不得回填或冒充正常 cohort 的 daily run。04:10 smoke 的
前兩輪 180 秒 timeout 是失敗；04:10 default 雖跑完，但 publication 因 completion
microsecond witness 不合法而 blocked，normal capture 亦因 nested capture blocked 且被舊
training completed 遮蔽而出現 false-success。兩者均不列為驗收；本段只採信 04:22 的新
durable success。

本段記錄的是 04:22:11-07:00 的最新 durable run；affected focused suites 與 synthetic mature
fixture 已有工程驗證。P1 三日 cache-hit custody QA 亦已通過：
`tests/test_recommendation_learning_cache_hit_custody.py` 為 `1 passed, 1 warning in 1.25s`
（exit 0）；2026-09-08 至 2026-09-10 的正式 `FA_Data/output` receipts 可跨至
`FA_Data_Shadow` 真實 verified reuse，保留原 timestamp，production source audit 的
hash／value／lineage 與正式 ADX producer 輸出均通過。這是 fixture custody proof，來源仍為
`fixture.invalid` 且 `historical_pit_eligible=false`、`formal_source_contract_eligible=false`；
real natural maturity、formal PIT 與 actual cost 仍各自維持待成熟或 out-of-scope，不把
bounded bootstrap、單次 capture 或 pipeline warning 寫成 V4 完成；工程 gate 與正式 default
smoke 已由父任務接受。

前一輪獨立 UI／型別 QA 曾以 `test_ui_qt_update_view_workbench.py` 81 passed、
`qa_validate_update_tab.py` 25 passed／0 failed／4 skipped 及 606 個 source files 的 mypy
結果收尾；該數字保留為前一輪工程證據。最新整合 QA 已由父任務接受，指定全域 mypy 改以
`.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`
執行並以 `Success: no issues found in 612 source files` 為目前型別基準；UI、Update Tab、
MainWindow offscreen smoke、主線 focused suites、synthetic mature fixture 與三日 cache-hit
custody QA 仍與 real natural maturity、formal source gate 及主線最終 QA 分層判讀。

主 Luna 另交付 affected focused suites `107 passed`（11 個 test files、`36.44s`、既有 1 個
warning）；source-contract／capture／official-custody／guards focused 為 `17 passed`，
update-service／process-pool／technical-analysis focused 為 `10 passed`；targeted mypy `5 files`
clean。先前 changed scheduled scripts 的 mypy `7 files`、以暫時 `PYTHONPYCACHEPREFIX` 執行的
py_compile 也保留通過結果，原有 `__pycache__` permission 限制仍保留。inventory 驗證為
`12 passed`（既有 1 個 cache warning）；新增 cache guard 後登錄總量已核實為 `805`，其中
recommendation 為 `31`。synthetic mature fixture
`tests/test_daily_recommendation_learning_loop.py::test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags`
已通過 production source verifier、adopt／active／rollback assertions。P1 三日 technical cache-hit
custody QA 已以 `currentity→verified receipt reuse` 修復並通過：三日正式 output receipt 重新解析
至各日 `FA_Data/output`、Shadow publication 保留原 timestamp，source-audit hash／value／lineage
與 ADX 正式 producer 輸出均驗證；測試結果為 `1 passed, 1 warning in 1.25s`。這只關閉 bounded
fixture 的跨 root custody 缺口，不等於 real natural maturity、formal PIT、actual cost 或 V4 完成。
scheduler 14 passed、04:22 wrapper true-success 與已交付工程 gate 均已由父任務接受；
主 Luna 回報 QA 7.1 為 `33 passed`（含 microsecond／nested blocked-capture regression，未杜撰命令）。
前一輪「主 Luna commit 尚待完成」是當時的 dated record，不作目前 source custody 的完成依據；
`719cf7a4` 已提交並驗收 C 的 bounded canonical learning／training lineage／cutoff／ML boundary，
後續 `0219d709` 已完成 P1 next-day inference／projection provenance；real natural maturity、
formal PIT 與 actual cost 仍維持各自的 pending／out-of-scope 邊界。

目前可分開判讀的 gate 是：price-up calibration 的 prospective source lane 可進入後續自然
驗證，但整體 promotion 仍等待自然 maturity 與 formal source gate；after-cost 仍因沒有可核驗
broker fill lineage 的 observed liquidity cost 而 blocked，固定 50 bp 只是估計參數；actual
execution 仍 blocked 且不在本工作線範圍。historical replay 永不取得 forward evidence credit，
因此本頁不宣稱 V4 完成、alpha、收益提升、正式推薦變更或 broker execution。工程與正式
default smoke 已完成接受；最新正常 cohort 的 natural evidence、formal PIT 與 observed cost
仍依各自 gate 判讀，詳見
[V4.2 prospective source 與每日學習 QA](../06_qa/V4_2_PROSPECTIVE_SOURCE_DAILY_LEARNING_2026_09_14.md)。

## 2026-09-14 Decision Workbench／決策連續性 scoped status

以下是本日已由父任務接受的工程切片；它們是可核對的 engineering acceptance，不能改寫成
V4 formal completion：

- `0d9d72af`／`cad07762` 已建立每日首屏與 content-first 唯讀旅程；`25544142` 已建立
  真實產業指數強弱與官方 TAIEX 5／20 日基準的可比研究讀模型，並排除槓桿／反向產品型
  指數。市場 → 產業 → 個股的唯讀下鑽可讀，但 current representative-stock mapping、
  TPEX／興櫃 coverage、historical PIT membership 與完整每日歸因仍待外部資料 Gate。
- `8acf29f0`／`b39fd399` 已隔離臺銀 `estimated_research_only` 成本 lane 與學習排程；首次
  05:50 實際 run 已於 `05:50:03–05:50:05 -07:00` 以 `failed_dependency` 結束，root guard
  已由 `086ba60c` 修復；`0aaf0dff` 的受控 shadow retry 已完成並為
  `completed_waiting_natural_maturity`，natural sample 仍為 `0`，也不等於 next-day inference
  provenance，後續正常排程持續觀察。observed fill／實際滑價是後續 execution-realism／formal
  Gate，不是每日學習的前置條件。
- `421ab844` 已交付 candidate／active／capture typed verifier 的唯讀 learning projection，
  BankTaiwan 與 legacy 50bp lane 保持分離；就 2026-09-14 臺銀正常 scheduled lane 的觀測，
  natural sample 為 `0`、decision 為 `retain_current`；legacy 50bp 是獨立 lane，可能維持
  `blocked`，不得把兩者合併判讀。這只證明既有 projection／receipt readback；C 的 bounded
  canonical runner、training lineage、cutoff／ML boundary 已由 `719cf7a4` 提交並驗收，P1 next-day
  inference／projection provenance 則由 `0219d709` 完成 bounded engineering receipt；兩者都不等於
  natural maturity 或 formal Gate。
  `53b456a0`／`ffb66c6f` 已交付唯讀 Decision → Outcome journey；`5339230f` 與 `031e11ab` 已分別
  驗收 Increment A storage 與 Continuity Review Workbench R1 的 exact reminder／controls／readback。
  完整 market→industry→stock→watchlist／portfolio 的整合使用流程，以及跨頁一致性及推薦／決策／
  outcome 追溯的整合驗收仍待接線，不再把 R1 列為未開始。

仍可施工的工程先是 L 的官方 taxonomy 端到端 source chain：補 raw producer／v3／
publisher／reader／caller，並完成 PDF／preopen completion-time 修正。接著才做 market→industry→
stock→watchlist／portfolio 的整合使用流程，以及跨頁一致性及推薦／決策／outcome 追溯的整合驗收；
這些不需等待 V4 formal closeout，但目前尚未驗收。C 的 personal capture／read／明示 action／
evaluation bounded wiring 與 fit producer／persistence／CLI 已在工作樹可核對並完成工程 bounded
acceptance；fit runner／CLI／calibration／read service 的 source fingerprints 與 41-pass QA 見
 `c_personalization_fit_acceptance_20260917.json`。正式 D 仍需真實 user decision／natural outcome
 的長期證據、sample、negative evidence 與既有門檻，才能推進 adoption。
historical bootstrap、controlled capture、fixture、shadow natural sample `0` 與任何 scheduler
registration 都不折抵 natural／formal 門檻；策略評估也不保證逐日準確率改善。

## 2026-09-12 V4.1 A 線第二輪歷史研究與候選方法包

已完成 research-only 的第二輪方法包：以正式 evidence SQLite 的 query-only 讀取建立逐列、逐 horizon 的 `historical_dataset_manifest.json`，再交給既有 20 trading-day primary／5 trading-day auxiliary expanding `train`／`calibration`／untouched-test evaluator。2026-09-12 正式 DB 讀到 221 個 `recommendation_included` events、24 個 outcomes，展開 442 rows；其中 `missing_outcome=430`、`insufficient_future_data=12`，成熟 observations=0、folds=0，因此正式結果為 `not_evaluable`，12 列等待自然成熟，其餘缺 outcome 仍是可追蹤缺口，不得回填。

本輪正式 source file hash 為 `sha256:16b7a0347706c37bf18611d05355af6f6edf98dd7c676107717325eff7fc3cc1`；DB 執行前後 size 與 mtime 未變。候選覆蓋為 current baseline `442/442` ready、price／volume `8/442` ready、chip／funding `0/442`、industry-relative `0/442`、PIT theme `0/442`。在 matched mature OOS 不存在時，pre-fix rule 保留 `current_score_v1`；frozen artifact 明確標示 shadow-only、read-only、`production_eligible=false`、`promotion_eligible=false`，不改 Recommendation／Scoring／正式 writer／scheduler。完整 manifest、候選 artifact、gap 分類與 QA 見 [V4.1 歷史研究與候選方法包](../06_qa/V4_1_HISTORICAL_METHOD_PACK_2026_09_12.md)。

## 2026-09-10 V4.2 C 線每日決策呈現切片

已完成第一個可用的唯讀垂直切片：市場總覽焦點卡、觀察清單保存分析、持倉條件監控與個股研究報告共用 `decision-presentation.v1`。畫面現在可沿「市場總覽 → 重點研究 → 觀察清單 → 持倉」判讀動作適合度、排名分數、證據品質、樣本／信心、理由／風險、權重欄位與失效條件；所有欄位由既有 DTO／service 適配而來，不在 UI 重算推薦。

本切片的安全邊界仍保留：市場焦點與保存的 Watchlist 結果只標為研究；校準機率沒有明確合格來源時維持研究中／不可用；持倉的 `valid`／`warning`／`invalid` 只映射為持有／減碼候選／退出候選；目標／目前／差距權重缺來源時顯示未知，不由 UI 推導。這不代表正式 Advice、自然 evidence、scheduler、broker 或 promotion 已開放。

本輪工作區驗證：presentation tests 6 passed、受影響 UI／service tests 106 passed、UpdateView workbench 81 passed、`qa_validate_update_tab.py` 25 passed／4 skipped、mypy 588 source files 無錯；QA output 不納入提交。

## 2026-09-10 V4 跨日證據閉環工程完成

本輪已修正每日推薦把決策日與 selected codes 放進跨日 `universe_id`、導致 evaluator
永遠一日一 cohort 的根因。新事件現在沿 RecommendationService → persisted DTO／JSON →
RecommendationEvidenceImporter → `evidence_events` → bounded forward outcome → SQLite
read model → evaluator 全鏈保存：

- 穩定的 `universe_policy_id/hash` 描述可跨日比較的政策；`universe_snapshot_id/hash` 另保存
  決策日、當日成分與 selected-code hash。evaluator 以 policy 作跨日 key，並揭露快照數與組成變化。
- `strategy_config_id/hash`、horizon、cost、benchmark、return basis 與 evidence tier 具體隔離；
  舊事件不猜測、不批次回填，缺件會在 read model／forward health 顯示。
- forward producer 維持 120 曆日／2,500 event bounded 上限，優先未完成 outcome，再以完整身份
  過濾後套用上限；health receipt 與排程狀態頁提供日數、horizon ready／pending／missing、最近
  capture／outcome／evaluation、下一成熟日與五種阻塞分類。
- `tests/test_v4_cross_day_evidence_contract.py` 以隔離 SQLite 實際驗證 DTO/importer/event/
  outcome/read model/evaluator 接線、三日同 cohort、動態成分、身份分組、冪等、舊 schema 診斷及
  長 horizon 優先順序。這些是工程證據，不增加正式 D 槽自然 outcome，也不授予 V4／Formal／alpha。

## 2026-09-10 B 線唯讀盤點與每日可靠性修正

以 `TWStockConfig` 實際解析的 `DATA_ROOT=D:\Min\Python\Project\FA_Data`、
`OUTPUT_ROOT` 與 read-only receipt／SQLite 完成 B 線盤點，沒有執行正式資料 writer、schema
變更或歷史回填：

- 2026-08-20～09-10 的 `evidence_events` 每日仍有約 1,650～1,700 筆 capture，
  `recommendation_included` 合計 217 筆，9/10 有 2 筆；但 `evidence_outcomes` 唯讀聚合為
  5／10／20／60 各 2 筆，全部尚未成熟，ready=0。
- 9/10 forward receipt 的 health 已正確辨識 215 筆不完整 cohort identity；修正前 top-level
  卻是 `passed_with_warnings`／`blockers=[]`／`exit_code=0`。現在 confirmed run 遇到
  `actionable_engineering_blocker` 或 `external_source_missing` 會 fail closed 為
  `blocked`／2，並保留 blocking reason、next action、next maturity 與 recovery verification；
  `waiting_for_natural_maturity` 仍只是自然等待，不回填舊事件或未來價格。
- Canonical isolated Paper 截至 9/10 有 6 個持倉、現金 `161526.11`、總值 `482526.11`；
  ledger 8 筆（6 filled、1 partially filled、1 rejected），費稅合計 `1373.89`，Decimal
  現金對帳一致。readiness 仍為 `partial`，原因是 Equal-Weight benchmark 與週報 benchmark
  observations 缺失，這不是 Paper accounting mismatch。
- 本次受限 shell 的 `schtasks.exe /Query` 無法找到目標系統路徑，故不把 receipts 當成
  實機 Task Scheduler 註冊／最近成功證據；scheduler、Formal OOS、promotion、alpha 與 broker
  旗標仍關閉。下一輪只需在可見排程主機重驗 live task 與最近成功時間。

## 2026-09-09 V4 read model 收尾增量

V4 effectiveness SQLite read path 現已在指定 `window_days` 時保留沒有 outcome 的事件，
並固定讀取單一 canonical `return_basis`，避免缺件被 SQL 篩掉或不同口徑重複計算；大量
缺少 cohort 欄位的 row-level 警告改以原因／數量彙總。此增量仍是 query-only、人工覆盤資料，
不會增加成熟 outcome、Formal credit、alpha 或交易權限。驗收見
[V4 有效性與資料來源工程驗收](../06_qa/V4_EFFECTIVENESS_READ_MODEL_2026_09_08.md)。

同日新增推薦證據身份接線：`RecommendationService` 會依政策設定產生穩定的
`universe_policy_id/hash`，並以決策日與實際處理股票集合產生每日
`universe_snapshot_id/hash`；舊 `universe_id/hash` 僅作 snapshot 相容 alias。每日排程固定宣告
`strategy_version_id=scheduled-recommendation-default-v1`、
`cost_model_id=gross-close-to-close-no-cost-v1`、`benchmark_id=TAIEX` 與
`horizon_days=20`；其中 no-cost 只代表 gross research observation，尚未扣除費稅滑價，
evaluator 會保留 `cost_model_not_cost_adjusted` 警告。evidence importer 只傳遞結果或執行
context 明確宣告的策略、成本、benchmark、policy／snapshot universe 與 horizon 欄位。缺件不猜測、不以
profile 或推薦列補值，也不回填既有 51,866 筆事件；這只讓後續新事件可被正確分 cohort，
不授予任何成熟度或正式權限。

同日已接上 `baldr-forward-outcomes-daily` 的每日 outcome producer。它在 05:40 以台北
當日可見價格，按 120 個曆日／2,500 events 上限計算 5／10／20／60 交易日
`close_to_close_event_date` 結果，排程 wrapper 預設限定 `recommendation_included` 事件；
並跳過缺少完整 cohort identity 的舊事件，將數量寫入 receipt；
只有排程明確帶入 confirm 旗標時才更新
`evidence_outcomes`，並以獨立 status／不可覆寫 run receipt 揭露缺件。這是讓後續自然
outcome 能累積的 producer 接線，不是回填既有事件，也不改目前 `evidence_outcomes=0`
的正式盤點結果。

既有證據覆盤與 Decision Workbench 的排程狀態頁也已接上這份 receipt：它只讀取
`forward_outcomes/latest_status.json`，顯示掃描／寫入／待成熟數、machine status 與
`forward_outcome_writes_evidence_db` 邊界；receipt 缺失時保留 source gap，不把推薦或
資料新鮮度誤當成 outcome。舊 DTO 注入仍維持相容，不會因尚未產生新 receipt 而讓既有
排程狀態讀取失效。

2026-09-09 正式 D 槽 Evidence SQLite 唯讀盤點為 `evidence_events=51,866`、
`evidence_outcomes=0`，且事件缺明確 `universe_id`，所以目前沒有可計算的有效 cohort。
整體 program readiness 仍為 `action_required`；Formal operational audit 為
`no_credit`（0/3），Paper readiness 為 `partial`（29 個 snapshot、0 fills、benchmark／cost
ledger 尚未具備）。這些狀態只描述目前可驗證資料，不會把等待 EOD、自然時間或來源缺件改成完成。

## 2026-09-08 root 執行收尾增量

本輪在不改寫原始資料與不解除正式權限的前提下，已加入 V4 cohort effectiveness 唯讀評估器／CLI、
FinMind `TaiwanStockCashFlowsStatement` numeric-only 候選抓取器、共用 heavy-chain 容量 reservation、
每日 quick 的明確 Phase3C candidate 接線，以及所有主要 SQLite backfill／migration 的 WAL-safe online backup／restore。
相關輸出均保存來源雜湊、觀測時間、候選或唯讀邊界；`pending`／`missing` 不會增加成熟分母，容量鎖忙或低於 200 GiB reserve 會 fail closed。
這些是工程能力與可重播檢查，不會製造自然前瞻日、公告可得日、成交或投資有效性；V4 八項 maturity、Formal 3/3、alpha、promotion、broker 仍維持關閉，
細節與測試見 [V4 有效性與資料來源工程驗收](../06_qa/V4_EFFECTIVENESS_READ_MODEL_2026_09_08.md)。

## 2026-09-09 官方資料實際補齊

已備份後增量入庫並從正式SQLite讀回：月營收7月1,851／8月已公告873家公司；法人229,472筆與信用22,163筆（8/26～9/8共10交易日）；集保9/4共4,047筆；Q2損益／資產負債66,358筆、1,972家公司。2330／1240／1108個股報告實測可讀最新數值，更新頁已區分現況與歷史PIT。D剩296.610 GiB。

未完成範圍必須保留：8月未公告公司、4筆集保加總異常、現金流數值及6家TDR財報；現況快照不授予歷史PIT／ML credit。歷史基本面表仍為原期別；新數值存於 `fundamental_current_observations`，當下報告依完整觀測時間讀取。每日quick尚未接新capture/apply入口。詳細來源、真入庫、驗證與限制見 [資料補齊驗收](../06_qa/DATA_COMPLETION_2026_09_09.md)。下方9/8工作線表是前一輪整合快照，資料狀態以本段為準。

## 2026-09-09 排程落地與狀態發布收尾

Windows Task Scheduler 已以 `register-all` 加上專用 Paper／PIT 路徑完成註冊；root elevated live query
確認 18 個 daily 與 1 個 weekly 共 19 個 task 均為 `Enabled`／`Ready`，wrapper action 與 Pacific local
trigger（04:20–21:25 daily、16:00／16:15／18:00 handoff、週日18:00）一致。任務維持
`Interactive only` 與既有電池／單實例限制，主機必須保持已登入的 Windows 使用者工作階段；這不會把
排程註冊解讀為 production evidence、Formal OOS、promotion 或 broker 授權。

每日 quick 更新曾因 Phase 3C `BackfillSummary` 非原生 JSON 物件，使 2026-09-09 那輪完成資料步驟後
latest status 停在 `running`。runner 現已在 latest status／history 邊界統一轉換 dataclass、Path、日期與
scalar wrapper，並以回歸測試證明 terminal status 與 append-only history 仍會發布；不重跑當日正式更新以免
重複寫入 D 槽，既有 stale receipt 會由下一個 04:20 真實輪次取代。其餘 `pending`／`blocked` 仍只代表
自然成熟、來源授權、成本／成交或 owner-controlled input 尚未取得，不能改寫成完成。

## 2026-09-10 V4.1 A 線推薦機率校準切片（前一輪紀錄）

前一輪已完成 research-only 的 20 trading-day primary／5 trading-day auxiliary walk-forward calibration 垂直切片：固定 decision time、return、benchmark、成本與 universe policy，分離 train／calibration／untouched test，輸出 baseline、raw score、整數 bp calibrated probability、probability bins、Brier／ECE、Wilson 不確定性、成本後與 benchmark 比較。當輪 formal snapshot 記錄 217 recommendation events、8 未成熟 outcomes；目前狀態以本頁 2026-09-12 第二輪為準。完整契約見 [V4.1 推薦機率校準垂直切片](../06_qa/V4_1_RECOMMENDATION_CALIBRATION_VERTICAL_SLICE_2026_09_10.md)。

## 2026-09-08 Luna 交付整合收尾

目前是工程整合與自然證據建立階段，**V4 尚未完成**。以下是目前狀態；先前逐輪測試、失敗與中途進度已移到歷史封存，不再把「早期待啟動」與「後續已中止」同列為現況。

|工作線|目前可採認範圍|仍待完成|
|---|---|---|
|每日資料更新|新handoff提供9/8 TWSE／TPEx／SQLite／market／industry／broker／technical對帳；root更新頁81項及QA25項通過|月營收正式apply、季報來源與availability、尚未啟用的candidate資料路由|
|Direct|新namespace已交付2014–2020年度manifest／carry驗證|2021因容量hold停止，2022–2026未完成；須重新核對live headroom，不能重複盲啟動|
|Formal／Paper|跨日與跨月工程、真producer隔離整鏈已交付；既有Paper自然執行曾獨立核對|自然0/3；9/9 capture仍卡9/8過期pending，須修caller選擇與同日合法來源，再驗共同時間證據。隔離3/3不折抵正式信用|
|持倉Health|政策→candidate→Paper entry proof→Decimal metrics→evaluator正例已交付；root相關整合套件通過|新版每日自然持倉證據；不回填舊三筆缺lineage持倉、不自動核准|
|Exit|producer與read model已修正mtime污染、實際／假設結果分離及扣成本計算；已接入既有每日Evidence caller，root相關36項通過|row-level可得價格證據及自然成熟結果；不自動交易|
|個股研究報告|持倉／觀察清單共用下鑽介面、唯讀服務、來源週期freshness與Manual已整合；root個股20項通過|可用資料覆蓋與合格ML provider；缺ML保留unavailable、不造結果|
|ML投資效果|自然前瞻與成熟審查框架存在|最近獨立採認26筆觀測、成熟0；不能以fixture或資料建置授予alpha／promotion|

## 本輪驗證與工作區

- root已通過：個股／UpdateView合計101 passed；更新QA25 passed／4 skipped；mypy585檔；Quant及ML shadow boundary；Exit／policy／candidate40 passed及Exit／caller相關36 passed（集合有重疊，不加總）。
- 完整pytest首輪5,031 passed／7 failed／4 skipped；7個失敗已全部修正並定向重驗通過。最新清冊／MCP／Paper隔離／Direct guard合計32 passed，Direct實際build／resume單項1 passed。保留首輪失敗紀錄，不把定向重驗改稱全套重跑全綠。
- 兩批共刪除2,469個快取／舊QA暫存、50,254,082 bytes。保留原始資料與持久證據；正式Manual已整併中繼補丁，現況與歷史文件入口已整理。
- canonical freshness已備份舊receipt並在實際時間重跑唯讀probe，24來源為7 current／2 stale／14 not_applicable／1 unknown。UI實際個股讀回可取得新版狀態；不是只有QA副本。
- 檔案說明／prompt提交 `31efeaa3`；資料、Direct、Formal、Health及排程核心工程提交 `c8dc5a7d`。個股介面提交 `9e25fc90`；手冊與整合驗收記錄另以文件提交保存；不stage output、DB、raw或工具產物。
- 保留main/dev與既有單一worktree；原始資料不得刪除，Direct與D磁碟持續保留200 GiB reserve。OOC／fit／fold-006+尚未啟動，券商交易與正式promotion未開放。

## 權威入口

- [本輪整合驗收](../06_qa/V4_LUNA_REVIEW_AND_WORKSPACE_CLOSEOUT_2026_09_08.md)
- [資料更新交付](../06_qa/V4_DATA_FRESHNESS_HANDOFF.md)
- [Direct交付](../06_qa/V4_DIRECT_RELEASE_HANDOFF.md)
- [個股報告交付](../06_qa/V4_STOCK_RESEARCH_REPORT_HANDOFF.md)
- [工作區分類與整理](../06_qa/WORKSPACE_FILES_AND_CLEANUP_2026_09_08.md)
- [V4完成計畫](V4_COMPLETION_PLAN_2026_09_07.md)
- [版本成熟度](VERSION_ROADMAP_V2_1_TO_V4_0.md)
- [操作手冊](../07_guides/APPLICATION_MANUAL.md)
- [完整歷史封存](../09_archive/PROJECT_SNAPSHOT_HISTORY_2026_09_08.md)

本頁只維護目前狀態；詳細驗收命令、過程與限制保留在專項QA，歷史數字不改寫為本次結果。
