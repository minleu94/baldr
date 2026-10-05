# baldr Scheduled Operational Wrappers

這些 wrappers 使用 CMD 入口；aggregate 保留 Windows `schtasks.exe`，完整唯讀查詢與 Paper 原地更新使用現有 Python／pywin32 Task Scheduler COM。PowerShell `.ps1` 曾被本機 execution policy 阻擋，不修改或繞過 policy。只有專用 Decision/Evidence capture task 進入既有 append-only event capture；Forward task 依有界當日計算更新研究 outcome rows，EOD Paper 依自身契約追加獨立研究 ledger。所有 Gate 都由機器重驗，不建立等待人工批准的排程 task。

2026-10-02 整合修復的最新設定／受控 producer／consumer 證據見[整合修復紀錄](../../docs/06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。21 項 Exec WorkingDirectory 已原地設為 repo；Paper／ML 具時區 trigger 為台北 08:25，兩項暫停已恢復。以下 9/30、10/1 runtime 清冊是歷史，不能取代新設定讀回或新一次執行。

2026-10-04 的接線修復與逐批實測見[四用途工程收尾](../../docs/06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。工程驗收狀態以該文件為準；Windows Task 顯示 Enabled／Ready、受控執行成功、下一次自然 trigger 成功是三種不同證據，不互相替代。

Decision Capture／Forward 的確認寫入共用 G6 的 canonical `OUTPUT_ROOT/release_v4/.ml_heavy_chain.lock`；單次報告 `--output-root` 不改變正式 DB 的鎖根。Forward 最長等待 10,500 秒，並保留臺北日界前 3,600 秒完成預算；Capture 另按兩個 child timeout 與收尾時間計算。取得 lease 後重驗時鐘與來源，finally 釋放自身 lease後再落終端拒絕收據；timeout、跨日、release failure 都不能當成成功。Forward dry-run 與 health reader 均唯讀、不等待 writer；手動 Forward、`capture_evidence_events.py` 與 Evidence pipeline CLI 遇 canonical lock 忙時立即拒絕，取得鎖前不建立可寫 repository。手動 Capture 預設 dry-run，Evidence／Decision Desk 來源 repository 同樣唯讀。

Forward 核心及既有入口共用 verified official maturity calendar，5／10／20／60 視窗只在計畫官方 session 取價。尚未到期為 `insufficient_future_data`，到期卻缺唯一有效 close 為 `missing_price` 並保留 null 報酬，日曆不可驗證為 `blocked_time_contract`。`expected_maturity_date` 的 row-offset 僅作 `legacy_price_row_offset` 診斷，不延長 horizon；`planned_official_maturity_date` 才是目標日。自然入口 cutoff 為實際臺北日期，歷史 replay 保留逐日 cutoff；來源 cache 與操作方式見 [Manual](../../docs/07_guides/APPLICATION_MANUAL.md)。

### 官方資料的三個獨立 child

`run_official_market_event_backfill.cmd` 交由 `run_official_market_status_bundle.py` 依序執行既有歷史事件、現況上市／交易限制及現況官方估值。各 child 以同一 wrapper run ID 綁定不可變回執、實際 stdout／stderr bytes SHA 與 raw；前一 child 失敗仍執行其餘 child，整批狀態保留失敗。歷史事件 publication 的正式資格門檻不變，現況觀測不取得歷史 PIT 資格。

現況上市狀態與個別公告來源清單在 `data_module/official_market_status_notice_sources.json`；清單只記官方 URL，股票、起迄日期和結論仍由本次原文解析。每個來源失敗均保存診斷；只缺某個來源時仍可讀已驗證的現況證據，UI 必須同時顯示 coverage 不完整。估值捕獲放在 `<OUTPUT_ROOT>/current_valuation`，提供官方 PE／PB／殖利率；TPEx 主端點失敗時可使用官方 OpenAPI fallback，保留前次失敗 raw／receipt。缺 PE 不填零，不用 PB 推算。

### 原始行情到目前股票研究模型

`--project-daily-source-rows` 在 same-run projection 完成後接 `ml_daily_source_row_research_adapter.py`，重驗 B manifest／row custody，建立研究 numeric store；再由 `current_stock_research_cycle.py` 讀取目前觀察清單與真實持倉的聯集。Operational status 仍在 canonical `OUTPUT_ROOT`，模型研究產物由共同 resolver 讀取本機 `output/ml_research_storage.json` 的 active root；設定缺席才用 `<repo>/output/ml_research`，舊根只按原 pin 讀取。設定格式、保護目錄、容量與回復方式見 [Manual](../../docs/07_guides/APPLICATION_MANUAL.md#研究儲存位置與容量排錯)，不把 formal publication pointer 指向研究資料。

cycle 綁定 raw run／行情日／B terminal、實際股票範圍、唯讀一致 SQLite snapshot、revision source context、outcome、fit、sidecar 與 registry。scope 超出既有 bounded bridge 的 2–16 檔界線、來源缺欄、日期／hash 不符或容量不足時保留具體 blocker。snapshot 的決策觀測時鐘與驗證完成後的 fit freeze 分開保存；不回填 availability。沒有 WAL 的來源採明確 absent v2 契約，保留真實 SQLite header／journal mode／前後內容 pins，不建立假 WAL 來通過驗證。

收據明確釘選為既存 0-byte WAL 且 SHA 為空內容時，允許兩次驗證之間只有 mtime 改變；實際路徑、非 reparse、大小、內容雜湊及同次讀取前後 stat 仍須一致。WAL 新增內容、非空 WAL 的時間或內容變動、主 DB／snapshot／receipt 變動仍拒絕。舊 failed run 不因修補改成成功；需以當前來源建立新的獨立 run。

法人來源的新增觀測與現況 revision 投影在同一交易內處理，包含官方數值回復 base 的情形；投影失敗則回滾該次資料寫入並保留失敗觀測及 checkpoint。相同觀測時鐘的全部修訂須各自核驗來源，九個法人數值欄位須一致，不能只比較最後兩筆；僅 source_version 改變且九欄相同不新增修訂。現況 reader 目前供個股報告的法人區塊使用，不宣稱它已成為推薦排名或 CORE19／20 模型特徵；正式 base 與歷史 PIT 資格不變。

相同輸入重用需要股票範圍、觀察清單／持倉完整 input pins（含 bytes／mtime／hash）、行情內容、來源修訂及 B registry／映射／選定股票數值語意全符；僅 capture 時鐘或新 run ID 不同不必再訓練，映射或資料改變則不可重用。每次仍保存新的 child 回執並重驗舊模型閉環。研究 cycle 的容量上限獨立核算為 2 GiB 持久增量、2 GiB 暫存、來源 DB／WAL 快照上限與 200 GiB reserve；正式重型 raw 的 35／40／200 GiB 門檻不變。外層 raw core exit 0 不能替代 nested cycle 的 completed／skipped_same_inputs terminal。

另有兩個 Codex app heartbeat，不屬於此處的 Windows Task inventory：`baldr-scheduled-evidence-morning-report` 每天美西 05:30；`paper`（晚間學習與 Paper 排程驗收）每天美西 06:20。它們只讀同次 Task/run receipts、identity、hash 與有限 log，變化通知採 change-only，不啟動 producer、Task、訓練或 Paper action。時區使用 `America/Los_Angeles` 本地時間並隨 DST 變更；不要另建立固定 UTC task 或把 heartbeat 當成 Windows trigger。

2026-09-30 Task inventory 與截至 2026-10-01 已讀回的 execution evidence 以[排程修復 QA](../../docs/06_qa/SCHEDULED_OPERATIONS_REPAIR_20260930.md)為準；該文件將受控人工執行、自然 trigger、safe no-work 與 failed dependency 分開記錄。最近的 21-task inventory 為 `output/qa/scheduled_task_inventory_20261001T002916Z_940402272834.json`（52,144 bytes、SHA-256 `9bbe91e9c6b1cc723222e87cd92a9751e8ff9985de9f3d7f4f76c2946193e374`），21/21 exact root task paths、0 errors。9/30 Pacific 16:15（10/1 Taipei 07:15）Paper Portfolio 與 ML forward 仍沒有同次 terminal：runtime 為 `waiting_for_taipei_cutoff`／`terminal=false`、heartbeat stale，latest 仍為前一日；原因尚未證實，不能用舊 latest 結案。inventory 在 Taipei 08:29:16 觀測，早於 08:30 cutoff 44 秒；不由 cutoff 到達推論成功。

使用者已明確表示沒有 1418 持倉。`paper-main-20260930` 的 1418 是 machine-initialized Paper research seed，不是使用者真實持倉；identity／thesis 診斷只描述該 seed 的研究品質，不得要求使用者補 1418 成交或 thesis，也不代表其他使用者持倉皆為空。05:15 Evidence dry-run 不寫 Evidence DB；9/30 05:25 自然 capture 已另行保存 `eod_research`／`research_only` 事件，但不授予 Health transition、verified 或 Formal qualification。Paper EOD 06:00 safe no-work 與 16:15 Paper Portfolio 是不同 Task。

Aggregate `register`／`register-all` 只允許在 Windows `Pacific Standard Time`
主機建立這些以 Pacific local time 表示的 task；`dryrun` 仍可在其他時區唯讀檢查。
Paper Portfolio 與 ML forward 預設 trigger 為具時區的台北 08:25（UTC 00:25；
前一個 Pacific 日期 PDT 17:25／PST 16:25）。adapter 等待真實台北 08:30，
準時啟動時等待五分鐘；不能以人工或較早日期時鐘補造決策證據。
完整 Windows 清冊目前是 20 個每日 task 加 1 個 weekly task，共 21 個；其中 ML forward 與 BankTaiwan shadow 使用專用管理路徑，不在 aggregate 18 daily + 1 weekly 註冊集合內。
`baldr-ml-allocation-forward-daily` 使用 pinned UTF-16 XML 與獨立 preflight，
aggregate `register`／`register-all` 不會建立或覆蓋它；aggregate `unregister`
也只會查詢並保留它；原地更新的回復使用同一 exact task 的 before XML，讀回
原 trigger／settings／Enabled，不刪除 task。

## Tasks

| Task | State | Trigger | Behavior |
|---|---:|---|---|
| `baldr-data-update-quick-daily` | enabled after register | daily local time 04:20 | Runs the non-UI quick data update path for the recent weekday window. Writes market data CSV / SQLite updates plus status and logs under `OUTPUT_ROOT/scheduled/data_update_quick/`. If TPEX has failed dates, the task continues later steps and writes `passed_with_warnings`. After all core phases, technical publication, terminal history and status complete successfully, the `.cmd` may run its default-on, bounded monthly-revenue research child; `BALDR_CAPTURE_MONTHLY_REVENUE_RESEARCH_CANDIDATE=0` disables it. It creates repository candidates only and does not write formal mappings or DB. |
| `baldr-official-market-events-daily` | enabled after register | daily local time 04:50 | 依上節同批依序執行 historical events、current market status 與 official valuation；各 child 獨立驗證回執及失敗狀態，歷史 publication 原有 coverage／PIT gate 不變。缺歷史事件不阻止安全的現況 capture，也不因此把研究來源提升成正式來源。 |
| `baldr-data-freshness-check-daily` | enabled after register | daily local time 05:00 | Read-only SQLite / `DATA_ROOT` freshness check. Also verifies raw TWSE / TPEX daily price files for the latest SQLite daily date. Writes only status and logs under `OUTPUT_ROOT/scheduled/data_freshness/`. |
| `baldr-ml-raw-pit-refresh-daily` | enabled after register | daily local time 05:05 | 先驗 quick terminal freshness proof，再於 formal source-revision hold 前執行前瞻 capture、same-run projection、B adapter／numeric store 與 bounded current-stock research cycle（詳上節）。`BALDR_ENABLE_ML_DAILY_SOURCE_ROW_PROJECTION=0` 停 projection 及依賴 children，`BALDR_ENABLE_ML_PROSPECTIVE_DAILY_CAPTURE=0` 同時停 capture。Nested failure 保留獨立 terminal，不改 core revision hold／exit。正式 raw builder 仍要求 35 GiB 持久、40 GiB 暫存及 200 GiB reserve；同 cutoff 已有較新 publication 可安全 skip，成功 formal publication 仍由 Direct／OOC watcher 接續。 |
| `baldr-recommendation-snapshot-daily` | enabled after register | daily local time 05:10 | Runs the research-only recommendation snapshot path after freshness. Saves the canonical execution artifact at `OUTPUT_ROOT/recommendation/runs/execution_artifacts/<opaque-id-sha256>.json` and indexes it in the same runs directory's `recommendation_runs.db`. Status/logs remain under `OUTPUT_ROOT/scheduled/recommendation_snapshot/`. The wrapper verifies the create-only save and query readback before forwarding the typed saved result. Historical legacy `<result_id>.json` files are read-only. The scheduled result explicitly carries strategy `scheduled-recommendation-default-v1`, market benchmark `TAIEX`, primary cohort horizon `20`, and gross/unpriced cost identity `gross-close-to-close-no-cost-v1`; the latter is not a cost-adjusted claim. The scheduled caller also emits immutable candidate-only packets under the repository `output/forward_position_thesis/YYYY-MM-DD/`; recommendation reasons and Decimal-text scores are preserved, while missing explicit invalidation／horizon policy remains `awaiting_explicit_policy`. It does not write the production evidence DB, does not confirm evidence, does not change portfolio state, and does not automate trading. |
| `baldr-evidence-pipeline-dry-run-daily` | enabled after register | daily local time 05:15 | Runs `scripts/run_evidence_pipeline.py` with `--dry-run` and forwards the resolved `DATA_ROOT` / `OUTPUT_ROOT` explicitly. Before the child, it refreshes the derived Paper health baseline from the repository snapshot using the preopen status receipt and the append-only Paper trade ledger; the scheduled path also enables `PaperPositionIdentityProvider`, which derives a stable ID only from a verified bounded flat-to-positive Paper fill. Same-snapshot or receipt-backed no-event continuity may preserve human fields, while missing coverage or entry evidence keeps the current row `WATCH`/unknown and preserves prior fields in history. Because the v1 ledger has no same-day sequence/time, multiple material fills for one stock on one date are blocked instead of ordered by `fill_id`. It then runs `--produce-position-health-sources`: quick/freshness receipts are checked first, and a read-only SQLite capture of selected `technical_indicators`/`daily_prices` rows is bound to real capture start/completion timestamps. The condition and Decimal metrics artifacts are create-only immutable; missing identity never falls back to stock code, and condition remains observation-only until a governed thesis/current condition exists. The CMD caller also consumes every immutable receipt under `output/forward_position_thesis/bindings/` through `--paper-health-forward-binding`; the consumer rechecks candidate/recommendation file and content hashes, Paper source event/order/fill, ledger row and evidence hash, then adds lineage provenance only. Missing or awaiting binding stays degraded and never supplies a human thesis. The CMD caller also runs `--evaluate-position-health-transition`, passing the source capture completion to the evaluator so an earlier quick receipt cannot backfill a later database read. The evaluator writes only the isolated `OUTPUT_ROOT/position_health_transition/` proposal receipt and append-only proposal repository. The same 05:15 CMD action passes `--run-exit-effectiveness`, which invokes `scripts/run_exit_effectiveness_daily.py` as a bounded 300-second child with the transition SQLite, repository Paper ledger, market SQLite, and verified calendar cache. Its create-only research artifact is written under `OUTPUT_ROOT/exit_effectiveness/YYYYMMDD.json`; timeout, malformed output, blocked source, or non-zero child status is surfaced in `latest_status.json` and returns non-zero. The child has no historical as-of switch, never applies a transition, never places an order, and never treats a stale prior artifact as a successful run. Missing thesis/condition/metrics remains `degraded`; only a proposal is written, never a human approval or execution action. Writes report, status, and logs under `OUTPUT_ROOT/scheduled/evidence_pipeline_dry_run/`; health source artifacts are under `OUTPUT_ROOT/position_health_sources/`. Scheduled status inherits freshness and pipeline overall status: missing / stale / blocking data is `degraded`, while complete observed-or-estimated MoneyDJ provenance is `ready_with_advisories`. |
| `baldr-ml-promotion-evidence-daily` | enabled after register | daily local time 05:17 | 固定 discovery 並重驗 formal OOC v5、雙 replay、Shadow outcome、逐 horizon calibration／drift 與 hash custody。證據不完整時只寫 blocked status，不更新 compatible pointer；若 OOC readiness 不足，blocker 會附上 `formal_ooc_dataset_full_market_not_ready:<readiness_check,...>` 的具體檢查名；若 direct store 落後最新 verified official market-event publication，會輸出 `formal_ooc_corporate_action_custody_stale:<field,...>`；完整時也只發布 unsigned evidence。 |
| `baldr-ml-promotion-authority-daily` | enabled after register | daily local time 05:18 | 由獨立 DPAPI user-scope authority 重驗 compatible evidence、Gate registry 與決策有效窗。只有所有機器門檻通過才簽章；否則成功 fail closed，維持 alpha 0。 |
| `baldr-ml-allocation-copilot-daily` | enabled after register | daily local time 05:20 | 執行配置型 ML promotion 評估並寫入 append-only sidecar、promotion artifact 與 `latest_status.json`。缺少、無效或未授權證據時仍成功完成每日流程，但固定輸出 `formal_oos_allowed=false`、`selected_alpha_bp=0` 與四條未通過 lane；不改寫來源資料庫或投組狀態。 |
| `baldr-decision-evidence-capture-daily` | enabled after register | daily local time 05:25 | 依台北時間選擇最近一個**已到達**的 08:30 `calendar_decision_at` 作為日曆選擇器；實際保存的 aware `decision_at`／`captured_at` 則使用本次 capture 的真實時鐘，`as_of` 明確綁定該選擇日。05:25 Pacific 約為台北 20:25，預設標為 `capture_mode=eod_research`、`research_only=true`，不宣告 `preopen_authority`／`natural_authority`，也不以 capture clock 改寫 source availability。既有 hash／unique key 使重跑轉為 duplicate；任一步失敗即回傳失敗並保留下一次重跑能力。它不推定交易日／成熟日、不改 Rule／Advice／Portfolio 狀態，也不連接券商執行。 |
| `baldr-forward-outcomes-daily` | enabled after register | daily local time 05:40 | 在 Decision/Evidence capture 之後，wrapper 預設只處理帶有身份契約的 `recommendation_included` 事件，並在計算前跳過缺少策略／成本／benchmark／policy／snapshot／horizon 的事件，以台北當日可見資料及固定 120 個曆日／2,500 個合格事件上限，重算 5／10／20／60 交易日 close-to-close research outcome。選取先把未完成 outcome 排到前面，再以完整 policy／snapshot identity 套用 bounded 上限，避免新事件排擠舊 60 日 pending；`health` receipt 會分類 normal completion／normal no-op／natural maturity／engineering blocker／external source missing，列出 cohort／決策日與各 horizon ready／pending／missing。可用 `FORWARD_OUTCOME_EVENT_TYPE` 受控切換事件類型；只有 wrapper 明確傳入 `--confirm --allow-production-db-confirm` 才更新 `evidence_outcomes`；事件、推薦、Paper／Formal、模型與券商狀態不變。自然未成熟保留明確 warning／degraded；confirmed run 遇到工程 blocker 或外部來源缺失會以 `blocked`／`exit_code=2` fail closed，並留下 blocking reason／next action／recovery verification。不補未來價格、不做 historical backfill。 |
| `baldr-recommendation-calibration-learning-daily` | enabled after register | daily local time 05:45 | 接續 05:40 forward outcome source，執行 bounded、read-only 的 recommendation calibration learning loop。若未設定 `RECOMMENDATION_LEARNING_SYMBOLS`，只會讀取同日已保存的 scheduled recommendation snapshot 明確股票群組，不做 universe discovery；原生 snapshot 的 `證券代號` 也會被視為 symbol source。snapshot 尚未到位或 provider 暫時不可用時，以 exit 2 寫入 `failed_dependency`、`finalized=false`、`recoverable=true` 的 attempt；同一 decision date 資料到齊後可直接重跑，舊 receipt 不覆寫。只有來源完整性破壞、active model fault 或明確 emergency rollback 才進入 fail-closed rollback。replay 使用 latest bounded decision-date window，讓新成熟資料可進入下一 training cycle。candidate 一次 freeze，之後每日 live capture 只保存當下 feature／candidate／active champion identity；自然成熟由可驗證 capture + market close source 產生，缺 observed liquidity cost 時 after-cost 維度保持 missing。promotion 沿 `baldr-ml-promotion-authority-daily` authority family，固定 distinct decision-date／Brier／gap／probability-cap／cooldown gates；不足、無改善或正常成熟不足只保留 current/rule-only，成功 receipt 才鎖定同日冪等。輸出位於 `RECOMMENDATION_LEARNING_OUTPUT_ROOT/recommendation_learning/`；永遠不寫 recommendation result、evidence DB、Portfolio、Formal 或 broker state。非 Asia/Taipei 交易日明確跳過 live capture。Task Scheduler 以 file path 直接啟動時，入口會先綁定 repository root，確保 technical reuse 的內部 import 與 package／pytest 邊界一致；unexpected exception 會以 fail-closed terminal receipt 記錄 run、stage、error 與 bounded child projection，並保留原 log，不會把未完成執行留成 `running`。 |
| `baldr-paper-portfolio-daily` | enabled after register | daily Asia/Taipei 08:25（UTC 00:25；前一個 Pacific 日期 PDT 17:25／PST 16:25，等待真實 08:30） | 由 `run_paper_portfolio_daily_isolated.py` 先以 D 槽 snapshot 的 SQLite read-only consistent backup 建立 repository state；兩種 offset 都等待真實台北 08:30，再 append preopen/T-1 估值 snapshot。isolated status 固定使用 `paper-portfolio-daily-isolated-scope.v1`，並發布 `paper-preopen-coverage.v1` 與 `paper-state-write-contract.v1`，供 Forward child 綁定當日 producer receipt。之後 D snapshot 永遠只讀，EOD 與 Formal 共用 repository state。盤前只以 `mode=ro/query_only` 讀市場 SQLite 與 EOD ledger；不覆寫既有 snapshot、不把 snapshot 當成交、不自動調倉、不修改 Advice，也不具券商執行能力。 |
| `baldr-ml-allocation-forward-daily` | registered by dedicated XML | daily Asia/Taipei 08:25（UTC 00:25；等待真實 08:30，08:35 後 fail closed） | 只執行 repository-isolated、candidate-only ML forward shadow。每日 config producer 依 offline official calendar、單一交易日 freshness、archive custody 與固定 V2 release manifest hash 建立 create-only config；child 必須保留完整 outer payload，`forward_credit_granted=false`。不寫市場 SQLite、不下單、不改正式 Paper／Formal 狀態；註冊前先執行 `run_ml_allocation_forward_daily.py --preflight`，aggregate registration 不會替換其設定。 |
| `baldr-pit-sector-membership-preopen-capture-daily` | enabled after dedicated register | daily local time 16:00（PDT 台北 07:00；PST 台北 08:00） | 在台北 08:30 前以官方 TWSE／TPEx response completion timestamp 建立 current-day PIT machine candidate，保存 raw custody、machine consumer readback 與 durable archive；同一 task 會先重驗當日獨立 denominator，缺少時自動以 data.gov dataset/resource、官方 Swagger 與授權文件建立 bounded create-only refresh；來源失敗會保留具體 status 並讓 sidecar 下輪重試。若 clock 或 response 越過 cutoff，fail closed，不建立可被當日 handoff 消費的 archive。 |
| `baldr-formal-pit-sidecar-postcutoff-daily` | enabled after dedicated register | daily local time 18:00（PDT 台北 09:00；PST 台北 10:00） | 先只讀盤前已完成的 PIT archive，以當下 Taipei decision clock 重建 handoff；sidecar 階段通過獨立 denominator、coverage、license scope 與 assembler readback 才 create-only 發布 sidecar，隨後同一 action 呼叫 `run_paper_event_source_capture_daily.py`，在台北 09:00..13:30 以固定 TWSE MIS endpoint 保存 Paper session-open raw bytes。沒有完整證據寫 blocked receipt，不重新抓取同一自然日 PIT HTTP source；Paper capture 缺來源時只保留 bounded retry 診斷，不建立 fill。 |
| `baldr-formal-input-producer-daily` | enabled after register | daily local time 21:25（PDT 台北 12:25；PST 台北 13:25） | 使用當下自然時間執行 Rule／causal Paper ledger／current PIT 的 bounded machine handoff。Rule 與 ledger 的 immutable manifest、source custody、publication context 與 receipt 寫入 repository output durable root；candidate 與 development 工作區每輪使用新的 TEMP 子目錄。缺 Rule source 不會阻止 PIT capture；缺任一 input 會保存具體 blocker，candidate-only 或 blocked 回傳非零狀態，不計入 Formal 3/3。 |
| `baldr-paper-execution-eod-replay-daily` | enabled after register | daily local time 06:00（PDT／PST 分別對應台北 21:00／22:00） | 先以固定 D 槽唯讀 dependency gate 驗證同一台北自然日的 quick update、freshness、daily_prices open rows 與 TWSE／TPEX source hash，再從持久 recommendation queue 選取下一官方 session 已到期的 frozen input。Paper writer 以 execution date 與完整 recommendation file/content hash 讀取同一份 repository `event_captures` durable manifest；缺失、hash／日期／source custody 不符時 fail closed。只有 durable capture、candidate、processed receipt 與 query-only ledger readback 全部綁定才保存 research-only fill；Formal consumer 仍另驗 event-time 與三來源 common identity。上游暫時來源最多重試 3 次並保留每次診斷，terminal blocker 立即停止；不跑 snapshot valuation，也不接受 D／環境變數 writer path 覆寫。 |
| `baldr-ml-direct-chain-maintainer` | enabled after register | daily local time 05:30 | 自動解析並重驗最新全市場 immutable raw PIT pointer、official market-event custody 與目前 Direct identity，然後啟動／維持 `maintain_ml_direct_v3_refresh_chain.py --watch-formal-inputs`。使用既有 instance lock 防止重複訓練；無效輸入只寫 `blocked_invalid_bootstrap_input`，不寫來源 SQLite、不建立未受控 sidecar、不放寬 formal／alpha／broker gate。 |
| `baldr-v2-2-weekly-collection` | `weekly-register` 後啟用 | 每週日 18:00 | 執行 `run_v2_2_weekly_collection.cmd`，以 SQLite read-only 讀取來源並將 evidence append 至 sidecar。對外狀態為 `pending_human_review`；需要人工判讀，但不代表 Gate 通過、不寫 weekly history，且 `write_intent=false`。只有 core collection exit 0 才啟動兩個獨立 research children：statement availability 預設開啟、`BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0` 可停用；季度 OpenAPI 預設開啟、`BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH=0` 可個別停用。Child 狀態／failure 以各自 per-run receipt 與 wrapper process output 判讀，不覆寫 core exit 或 pending 狀態。季度入口每週最多 26 GET（2 catalog + 24 數值 endpoint），只產生 repo create-only research candidate。 |

### 2026-10-01 研究 child readback 範圍

最近完整 7 日的 statement-availability candidate `output/research/mops_statement_availability/run_20260930T221808809646Z/` 有 6 次成功查詢、36 events／36 projection rows，並保存 6 個成功 HTTP entity（16,506 bytes）；這是 bounded capture receipt，不代表之後自然 weekly wrapper child 已驗收。較早 8 月 diagnostic 的 15/15 queries／3,150 events 是另一個 run；該 legacy artifact 沒有成功 HTTP entity raw sidecar，不能混為一份完整 custody。季度 OpenAPI 的一次實際 26 GET capture 為 3,960 raw rows、3,952 preview rows，8 rows 留在 key/schema review；它同樣不是自然 weekly Task 的同次 child receipt。兩種候選均不代表已接受一般金額單位、正式 mapping、PIT、Formal、訓練或 credit，詳見[排程修復 QA](../../docs/06_qa/SCHEDULED_OPERATIONS_REPAIR_20260930.md)及[季度 capture QA](../../docs/06_qa/SCHEDULER_QUARTERLY_OPENAPI_RESEARCH_CAPTURE_20261001.md)。

正式 `run_recommendation_snapshot.cmd` 在 `EXPORT_PAPER_FROZEN_SOURCE` 未設定時預設啟用；明確設為 `0` 可關閉。啟用時會先唯讀重驗既有官方年表，再以 create-only 方式產生 `paper_frozen_<result_id>.json`。這份 Paper 專用投影保留 canonical 結果識別與來源雜湊，不加入 recommendation index，也不回填舊日期；已驗證休市會跳過，年表未知或開市日來源日期不符則記錄 blocked。Python CLI 本身預設不匯出，Shadow learning 呼叫不傳此選項。

Paper EOD dependency gate 的 freshness 是 lane projection，不會改寫 aggregate
`freshness_status`。只有 aggregate `status=degraded`、`errors=[]`，且每個 warning
都能由 `source_statuses[].source_id`／`freshness_status` 對應到明確的非 EOD source 時，
才可能輸出 `status=ready_with_warnings`；`twse.daily_prices.raw`、
`tpex.daily_prices.raw`、`sqlite.daily_prices` 必須同日 `current`，既有 quick／freshness
target date、aware timestamp、raw CSV 與 SQLite readback 也必須全部通過。投影會保留
aggregate status 與被忽略的非 EOD warnings，供稽核判讀，不把它們宣稱為 freshness
`passed`。未知或未分類 warning、source ID／status 缺漏或 malformed、未被合法 warning
歸屬的 non-current source、`failed`／`expected_wait`、必要市場 source `stale`／`partial`，
以及任何日期、時間、raw／DB reconciliation blocker 都維持 fail closed；
`passed_with_warnings` 也不會繞過這個界線。兩個明確的跨 consumer `unknown` 例外是
`tdcc_shareholding` 與 `fundamental.statement_availability_map`：前者只屬 TDCC 週資料
候選／shadow completeness，後者只屬 MOPS Fundamental/PIT availability mapping，兩者都
沒有 Paper EOD downstream。`freshness_lane.not_required_for_paper_eod` 會保留完整原始
source diagnostic、reason code 與 consumer boundary；它不把來源改成 `current`，也不
放寬 TDCC 或 Fundamental 自己的 fail-closed gate。其他 unknown source、required source
unknown、malformed、failed 或 aggregate errors 仍阻擋 Paper。

Phase3C 的 `credit_transactions` candidate stale／partial 只有在 source row 同時明確標示
`candidate_only=true`、`frequency="daily candidate source"`、
`downstream=["candidate research only"]` 與
`update_entry="UpdateService.update_phase3c_candidate_range"` 時，才由具名
`p0_candidate_shadow` policy 投影到 `freshness_lane.not_required_for_paper_eod`。這不代表
資料 current，也不代表 Paper 使用該來源；缺任一欄位、欄位值改變、`failed`／
`expected_wait`／`unknown` 或其他 candidate source，仍維持 unattributed／blocked。source row
的 `reason` 也必須是非空字串；投影會保留原始 row、`freshness_status`、`candidate_only`
與 `reason`。即使 aggregate 帶有 `credit_transactions` warning，具名 policy 不符仍會
阻擋，不會由一般 warning allowlist 放行。

### V4 跨日 evidence identity 與每日 health

每日推薦 snapshot 會保存 `universe_policy_id/hash`（跨日政策）與
`universe_snapshot_id/hash`（決策日實際成分），並以 `strategy_config_id/hash`、horizon、
cost、benchmark、return basis、evidence tier 固定可比較邊界。`universe_id/hash` 是相容 alias，
不應再作為跨日 policy key。缺 policy／snapshot 的既有事件保留 legacy／missing 診斷，不由目前
股票池回填。

`baldr-forward-outcomes-daily` 每輪 `latest_status.json` 與 `runs/<run_id>.json` 的 `health`
保存 `latest_qualifying_event_date`、`qualifying_event_count`、`cohort_count`、每 cohort 的
`decision_day_count`／snapshot 清單、各 horizon ready／pending／missing、最近 capture／outcome／
evaluation、`next_maturity_date`、blockers／warnings 與自然鍵冪等結果。分類可為
`normal_completion`、`normal_no_new_outcomes`、`waiting_for_natural_maturity`、
`actionable_engineering_blocker`、`external_source_missing`；只有最後兩類需要修正工程或來源。
confirmed run 若 health 分類為最後兩類，receipt 會同步輸出 top-level `blockers`、
`blocking_reason`、`next_action`、`next_maturity_date`、`recovery_verification`，並以
`status=blocked`／`exit_code=2` fail closed；同輪已完成的 bounded、冪等 outcome write
仍保留在摘要中。`waiting_for_natural_maturity` 維持 `passed_with_warnings`／`exit_code=0`，
只等待官方可見價格，不補未來資料、不做 historical backfill。這些欄位由
`ScheduledEvidenceStatusService`／UI 唯讀投影，不會重跑 producer 或寫 DB。

同一輪會另外在 `<OUTPUT_ROOT>/scheduled/evidence_progress/` 保存
`latest_status.json` 與不可變的 `runs/<run_id>.json`。progress receipt 只消費
forward receipt，彙總當日／當週實際 capture、5／10／20／60 maturity 與 next action；
同一 `run_id` 重試只更新 latest projection，不覆寫 immutable run。連續兩個應有資料的
工作日沒有新 capture 會標成 `no_new_data_alert.status=alert`；週末或
`data_freshness.latest_status.json` 已驗證的官方休市日標成 `suppressed_non_trading_day`。
官方 calendar 未知時不猜成休市，而保留 expected-day 觀測並加 warning。告警由
`ScheduledEvidenceStatusService` 與 UI 讀取，
不會把 no-new 狀態當成新證據，也不會寫 evidence DB、Paper 或 broker。

`run_paper_portfolio_daily.cmd` 先呼叫 `run_paper_portfolio_daily_isolated.py`。首次
執行只將 `DATA_ROOT\output\paper_portfolio\paper_portfolio.sqlite` 以 SQLite
`mode=ro/query_only` 一致 backup seed 到
`<repo>\output\paper_execution_eod_replay\paper_portfolio\paper_portfolio.sqlite`，
並以 immutable `state_seed_manifest.json` 綁定來源 main/WAL/SHM hash；repository
state 後續由公開 `scripts/run_paper_portfolio_daily.py` append，D snapshot 不再是
writer target。若呼叫端設定 `PAPER_EXECUTION_RECOMMENDATION_JSON`，cmd 只會以同一
repository state 建立 T+1 next-session-open、bounded、research-only candidate；
不接受環境變數將 state／ledger 導回 D。台北 08:25 的 Paper Portfolio
hook 仍不追加 ledger；adapter 等待真實台北 08:30 cutoff，
目前 Pacific 06:00（PDT／PST 對應台北 21:00／22:00）的 EOD replay task
透過 `run_paper_execution_daily_isolated.cmd`／`run_paper_execution_daily_isolated.py` 固定使用
固定的 `D:\Min\Python\Project\FA_Data\output\recommendation\runs` 自動選取下一
official session 到期的 frozen recommendation，並以 repository operation root 的
`receipts` 保存每次 processed／
superseded／waiting／failed／skipped receipt。Queue 的唯一鍵是
`portfolio_id + next_official_execution_date`；同一鍵只採用最新的 frozen
recommendation，其餘候選會留下 `queue_state=superseded`，因此 processed hash 被排除後
不會在下一次重跑切換到較舊目標。它預設傳入明確的 append flag，將 research-only fill 寫入
repository 隔離的 `PAPER_EXECUTION_LEDGER_DB`；設定 `PAPER_EXECUTION_APPEND=0` 才保留 candidate-only
預覽。processed receipt 只有在 schema、receipt content hash、來源 recommendation
檔案 hash、candidate result 與 append/readback ledger 均可重驗時才會阻止同一 source
重跑；損壞或不完整 receipt 會被忽略並留下具體 diagnostic。candidate 會驗證 recommendation 的自然日、下一個官方 session、開盤價／
reference session 收盤成交量、Decimal 成本與自然日界線。preopen snapshot 已存在時，
它被視為 execution 的 T-1 起始狀態；EOD writer 只追加獨立 postfill transition，
不覆寫 snapshot。下一個 preopen runner 以唯讀 ledger 投影該 transition 至新 snapshot，
並以現金／股數守恆驗證。現有 `daily_prices` 是沒有逐列 capture timestamp
的 EOD 來源，runner 以台北交易日 15:00 的保守延遲重播門檻消費；15:00 前只回傳
`waiting_for_execution_source`，不把全天成交量拿來決定開盤 cap，也不宣稱即時成交。
Queue root 不存在、沒有待執行 source 或 source JSON 無法解析時，會輸出
`skipped_no_pending_recommendation` 及原始 blocker；不會靜默以 exit 0 偽裝成已處理。

Forward child 使用 Paper state 時，T-1 reader 必須把 weekly snapshot 對齊 official
calendar 的每個 session，且最後日期必須是 strict T-1；成交政策 turnover 只取
`paper_trade_transitions` 的 canonical integer bp，fill gross bp 只作 Decimal audit。
state 與 transaction ledger 讀取均保存 hash-before／after。若 08:30 preopen writer 與
derived wrapper 的外層 stat 同時變動，只有 inner `paper_read_consistency`、完整
`preopen_coverage`、write scope、receipt bytes 與最新 state head 全部一致，才會標為
`expected_preopen_producer_overlap`；沒有 receipt、空／過期／範圍錯誤 receipt 或
receipt 在 hash/read 間變動，一律 `failed_read_only_integrity`。snapshot-only turnover、
缺 coverage 或舊 8-row ledger 不得被補算成 Forward 證據。

若唯讀 scheduler query 顯示 `baldr-paper-portfolio-daily` 尚未採用最新時序，使用專用的
`scripts\scheduled\register_paper_portfolio_task.cmd dryrun` 核對後，再以同一腳本的
`register` 模式只更新已存在的 exact root task，先保存 XML 備份，使用 COM
`TASK_UPDATE` 保留 principal、登入、電池、retry、Enabled 與 timeout；缺 task 或查詢
錯誤 fail closed，不建立替代 task。預設台北 08:25；`register [HH:mm]`
保留明確的 Windows 本機時間 override，第三參數可明確指定 ISO duration，省略則
保留 timeout。輸出必須為 `registered_and_readback_verified` 才視為套用完成；失敗時依
before XML 回復並讀回，不刪 task。此入口不呼叫 aggregate，也不修改其他 task。

Paper EOD task 若在唯讀 scheduler query 中缺失，使用專用的
`scripts\scheduled\register_paper_execution_task.cmd dryrun` 檢查後，再以同一腳本的
`register` 模式只建立 `baldr-paper-execution-eod-replay-daily`；它不會呼叫 aggregate
registration，也不會修改其他 task。06:00 Pacific 在 PDT／PST 分別對應台北 21:00／22:00，
所以不會在延遲 EOD source cutoff 前讀取開盤資料。Query 仍須實際讀回
`Task To Run`、`Last Result`、登入模式與電池條件；初次建立 task 的
`Last Run Time=1999/11/30` 或非零結果只是未成功執行／來源未就緒證據，不能當成 Paper
fill 已完成。scheduled Paper wrapper 只可使用研究用隔離 ledger；broker、正式行情與
Formal controlled path 永遠維持 false。

官方下一 session 判定優先讀取
`<repo>\output\paper_execution_eod_replay\calendar_cache\` 中由
`official-trading-calendar-cache.v1` 保存的 TWSE annual `holidaySchedule`。隔離
adapter 每輪先重驗同年度 cache；有效 cache 不發 request，缺失／過期／竄改／錯年份時才
對官方 endpoint 做最多兩次 bounded request，成功後以實際 response completion 建立新的
create-only 檔案，舊檔永不覆寫或刪除。每次結果另保存於 `receipts\calendar_refresh_*.json`，
因此失敗、保留舊檔與下一次重試都有可讀回狀態；refresh 只允許 operation root 內的 repo
output，不能使用 D 或既有正式 ledger。

05:10 recommendation forward candidate 若帶 approved policy，不直接把 policy 的
immutable `calendar_cache_path` 當成永遠有效的 current cache。caller 會讀同一個
`v4_ml_forward_scheduler/calendar_cache_refresh/latest_status.json`，只接受
`cache_valid_for_forward_horizon`／`refreshed` 的 read-only receipt，使用 receipt 指定的
exact cache path／file hash 並重新驗證；candidate 會保留 policy pin custody，另記
`calendar_observed_path`／`calendar_observed_sha256`。refresh receipt 缺失、過期、篡改或
安全邊界不符時，forward candidate 維持 blocked／degraded，不掃描或猜測舊檔。

每個 cache 保存原始 response bytes、HTTP status／headers、request／response URL、response
SHA-256、實際 `captured_at_utc`、七日 freshness window 及完整年度正規化 projection；consumer
會重新驗 raw hash、年份、完整 coverage、timestamp chain 與 expiry。年度表的 `weekday
absence is planned open` 只代表年度排定狀態，不涵蓋 capture 後公布的颱風或其他臨時全面休市；
cache 明確綁定 TWSE 天然災害處理規則頁
`https://www.twse.com.tw/zh/clearing/suspended.html`，臨時事件必須另有官方事件公告
證據，不能從 365 日 projection 推導。若 refresh 仍不可得，Paper 保持
`official_calendar_not_proven:*`，不以 weekdays、行情列或空結果代替。cache 是 read-only
operational source observation，不建立 Formal clock、PIT 歷史信用或 broker 權限。

若 TWSE 發布臨時全面休市公告，可用
`scripts\capture_twse_temporary_closure_cache.py --closure-date YYYY-MM-DD
--source-url <TWSE公告URL> --output <repo output> --confirm-network` 建立
`official-twse-temporary-closure-cache.v1`。capture 會要求官方 HTTPS 公告 response
同時包含指定日期及明確休市文字，並重驗 response／outer hash、URL、status 與 capture
時間；天然災害規則頁本身沒有事件日期，不能直接通過。isolated resolver 只接受驗證過的
`twse_temporary_closure_*.json`，事件可覆蓋同日 annual plan；缺少或失效事件證據不會被
自動補成休市，也不會由 weekday 或行情列推導。

isolated Paper adapter 每輪也會自動呼叫 TWSE 官方
`https://www.twse.com.tw/rwd/zh/news/newsList?tag=%E4%BC%91%E5%B8%82&response=json`
清單，再對最多 8 筆標題明示「單日全面休市」的公告呼叫
`/rwd/zh/news/newsDetail?id=<zhId>`。清單與明細都必須是 HTTP 200、final URL
仍在指定 TWSE endpoint、response bytes／公告 ID／日期／時間可重驗；只有通過
驗證才 create-only 寫入 `calendar_cache/twse_temporary_closure_*.json`。清單
不可得、欄位改變、公告不是單日全面休市或明細驗證失敗時，receipt 會保留
`temporary_closure_discovery_blocked`／`temporary_closure_events_partial` 與具體
原因，下一輪自動重試；不會要求每日人工執行 CLI，也不會用年度表、weekday 或
行情有無推導臨時休市。sidecar 的 discovery raw list、detail raw bytes、source
hash 與實際 response completion time 會由 `OfficialTradingCalendar` consumer
再次 readback，仍只影響研究用日曆判定，不建立 Formal credit 或 broker 權限。

Paper EOD scheduled task 不使用通用 wrapper 的可覆寫環境變數。隔離 adapter 固定
既有 `D:\Min\Python\Project\FA_Data` 下的 recommendation queue 與
`sqlite\twstock.db` 為 SQLite `mode=ro/query_only` 來源；repository
`output\paper_execution_eod_replay\paper_portfolio\paper_portfolio.sqlite` 是盤前
adapter 建立、EOD 唯讀消費的唯一 Paper state。每輪 candidate 寫入
`<repo>\output\paper_execution_eod_replay\candidates\run_<uuid>`，receipt 寫入
同一 operation root 的 `receipts`，append-only research Paper ledger 固定為
`<repo>\output\paper_execution_eod_replay\paper_trade_ledger.sqlite`。啟動時會 exact
驗證 immutable `scope_manifest_v2.json`；合法歷史 v2（可含既有
`writable.event_capture_root`）只會以 append-only、create-only 方式建立自洽的
`scope_manifest_v3.json`，並保存 create-only migration receipt，絕不覆寫 v2 bytes。
來源、target 或 manifest 任一 root 漂移時會在建立 v3 前 terminal fail closed，固定的
scope-validation failure receipt 不使用未驗證 writer root；缺少 ledger 不會被當成 Formal
或已完成 evidence，只有具體 machine-verified Paper fill 才會建立 append transition。

PIT 的日常來源分成盤前 capture 與盤後 sidecar 兩個排程。

盤前 CMD 未收到 `PIT_TAXONOMY_SOURCE_CONFIG` override 時，使用版本化的
`scripts/scheduled/pit_taxonomy_source_config.json`，直接抓官方 TWSE／TPEx 規格與 ISIN
證券清冊；不依賴 TEMP raw file、固定 HTTP timestamp 或人工 symbol mapping。TWSE
採已生效 B.12.12 composite（base／2023 change／revision history／current regulation），
B.12.13(202612) 只作 revision history，不提前採用未生效版本；TPEx 為 V12.18 TCPIP。
此設定的 license scope 明確是 `research_only_unaccepted`、`formal_acceptance_granted=false`，
不是 formal license approval。Direct Python caller 須明確傳 config 或設定相同環境變數。

真實 archive／獨立 denominator 抓取完成後重新取得時鐘，再驗 taxonomy source completion，
不拿啟動前 clock 對比本輪完成時間。08:30 cutoff 仍由 producer 驗證；denominator 或
taxonomy blocked 時，wrapper status 為 degraded 並回 exit 2，不以 archive 單獨成功掩蓋。
Post-cutoff history 使用與前置 gate 一致的離線官方日曆 cache；缺 cache 不補發 HTTP。
History inventory 中日期資料夾早於明確 coverage start 的 archives 保留並列入
`out_of_scope_archives`，不參與當期 universe／license／coverage。未知日期資料夾與
範圍內失敗仍阻擋；被排除的舊檔不能拿來補 required coverage，也不提供歷史 credit。

兩個排程的原始接線如下：`run_pit_sector_membership_preopen_capture.cmd`
固定在 Pacific 16:00 執行，PDT/PST 分別對應台北 07:00/08:00，並在每個官方
response completion timestamp 越過台北 08:30 時停止。盤前 task retry 會先重驗同一
台北自然日既有的 archive；只有當日完全沒有 archive 才進入一次 live capture，存在
但竄改或不完整則 fail closed，避免重試製造多個不同 capture timestamp；
`run_formal_pit_sidecar_postcutoff.cmd`
固定在 Pacific 18:00 執行，PDT/PST 分別對應台北 09:00/10:00，只讀前一 task
已保存的 archive。aggregate register 會呼叫這兩個 task 的專用註冊流程；也可用
`register_pit_sector_handoff_tasks.cmd dryrun` 檢查後再以 `register` 單獨建立，
不會改動其他 task。`run_formal_input_producer_daily.cmd` 若設定
`FORMAL_DAILY_PIT_PREOPEN_ARCHIVE_ROOT`（wrapper 預設為 publication root 下的
`pit_candidate_archive`），盤後也只重驗該 archive，不會重新抓取同一自然日的 PIT
HTTP source；缺 archive 會保存具體 blocker。

## Formal input producer durable handoff

`baldr-formal-input-producer-daily` 的入口是
`scripts/scheduled/run_formal_input_producer_daily.cmd`。只針對這一項 task 的註冊計畫由
`scripts/scheduled/register_formal_input_producer_task.cmd` 提供；它要求 Windows
timezone ID 為 `Pacific Standard Time`，並使用本機 21:25。這個時刻在 Pacific
Daylight Time 對應台北 12:25，在 Pacific Standard Time 對應台北 13:25，全年都
落在 Rule 09:00–13:30 capture window。若主機不是 Pacific Standard Time，註冊腳本
fail closed，不把固定 local time 冒充台北時區排程。入口不接受 `--now` 或人工確認；每輪以實際 clock 建立新的 TEMP
candidate／Rule development 子目錄，再把 Rule history 與 causal Paper ledger 的
immutable manifest、source custody、publication context、receipt 寫入
`<repo>\output\formal_daily_publications`。設定
`FORMAL_DAILY_PUBLICATION_ROOT` 可指定另一個合法 repo `output` 或隔離 TEMP root；
該值是持久 parent，每輪會自動建立唯一空 run，不能直接當成固定 candidate 目錄。

使用者環境只需設定一次 Rule 來源：
`FORMAL_DAILY_CLOCK_MANIFEST`、`FORMAL_DAILY_UNIVERSE_SYMBOLS`、
`FORMAL_DAILY_OWNER_ACCEPTANCE`。market DB 預設為
`DATA_ROOT\sqlite\twstock.db`；Paper snapshot／fill 預設讀取
`<repo>\output\paper_execution_eod_replay\paper_portfolio\paper_portfolio.sqlite`
（盤前 runner append、Formal 唯讀）與
`<repo>\output\paper_execution_eod_replay\paper_trade_ledger.sqlite`（由 isolated
Paper EOD task append、Formal 唯讀）；production cmd 固定傳遞這兩個 repository path，
不把 Formal reader 指回 D。正式
controlled path 若已存在，可用 `FORMAL_DAILY_FORMAL_LEDGER_PATH`、
`FORMAL_DAILY_FORMAL_RULE_HISTORY_PATH`、`FORMAL_DAILY_FORMAL_SECTOR_PATH` 指定，
否則沿用既有 `BALDR_ML_FORMAL_*` 環境設定；所有 path 都由 consumer 唯讀重驗。

Rule clock／universe／owner 缺件只會使 Rule lane 產生具體 blocker，不會封鎖 PIT
現況 capture；PIT 仍由官方 response completion time gate。缺 Paper fill、官方日曆、
HMAC 或 consumer custody 時，狀態會保存相應 blocker。wrapper 的
`latest_status.json` 位於 publication root 的 `scheduler` 子目錄，會以原子替換
更新；其中 `status=candidate_only` 或 `blocked` 都以 exit code 2 回報，只有三個
明確 formal paths 皆由正式 consumer readback 才回傳 0。這不會把等待中的輸入、歷史
時間或 TEMP candidate 轉成 Formal credit。

所有 Formal Rule／PIT preopen／PIT sidecar／Formal input 與 Paper session-open
wrapper 都必須先用 `OfficialTradingCalendar` 的離線、hash-bound cache 判斷當日，
再載入只對交易日有效的 runtime config。官方確認休市時寫
`skipped_non_trading_day`、`blockers=[]` 並回傳 0；日曆 unknown 仍 fail closed。
因此週末或國定休市日不會因上一交易日 config 已過期而被誤報成排程失敗，也不會
啟動 PIT HTTP capture。Paper EOD 後的 runtime roll-forward 若已存在同一個下一開市日
config，會完整重驗 immutable bytes、wrapper contract 與 activation day 後重用；不以
新的 `generated_at` 重建相同日期，也不放寬 create-only mutation guard。

Evidence 的 Paper position identity consumer 也明確支援這個休市日契約：當最新
Paper status 是 `skipped_non_trading_day` 時，只能沿用最後一個交易日 snapshot，且必須
同時證明沒有 append snapshot、官方日曆為休市、isolated ledger path 完全一致，以及
status 內的 state-head SHA-256 與目前 Paper state DB bytes 完全一致。通過時記為
`paper_position_identity_coverage_reused_non_trading_day`；state hash、路徑或安全邊界任何
一項不符仍 fail closed，不會把 `stock_code` 猜成 position identity。

每次 scheduled wrapper 也會在同一個 durable scheduler root 追加
`attempts.jsonl`。每筆記錄保存實際 `python_executable`、entrypoint、wrapper command、
working directory、arguments、producer status、blockers 與 exit code；不保存完整環境或
secret。`latest_status.json` 同步保存 `exit_code` 與 `attempt_log_path`。因此
`Last Result=2` 可由 status／attempt log 直接追到「candidate-only／blocked 的具體來源」；
不能把它改成零來掩蓋缺少 Rule、causal ledger、PIT formal sidecar 或自然時間窗口。

PIT capture 在同一輪 machine consumer readback 通過後，會把 publication、receipt、
operational envelope 及兩份官方 raw bytes 以 create-only 方式保存到
`<publication_root>\pit_candidate_archive\<Taipei capture date>\<short key>\`。
`archive_manifest.json` 保存完整 source／archive file hashes、capture time、producer
code hash 與 candidate-only 邊界；readback 直接以 archive 內的 raw bytes 重驗 rows，
不依賴已結束的 TEMP 目錄。這是持久的 machine candidate custody，不是 Formal sector
source，也不會把 `formal_consumer_compatible`、promotion 或 broker 權限改為 true。

盤前 capture task 會在相同 publication root 下查找當日
`pit_denominator\<Taipei capture date>-run-*\denominator.json`。找到仍可由完整
child bytes 重驗的封套時只讀重用；找不到時，才自動抓取兩市場 OpenAPI、兩份 data.gov
CSV／metadata、兩份官方 Swagger 與 data.gov 授權文件，並將回應完成時間、final URL、
HTTP status、內容 hash、coverage start 與 machine license scope 寫入新的 immutable
run。這個 resolver 僅接受 coverage start 等於當日台北自然日的封套；過期、竄改、錯年或
來源不可得都會留下 `missing_verified_current_denominator` 或
`pit_denominator_refresh_failed:*`，不以舊日清冊補當日，也不要求人工每日設定 path。

若要讓同一輪另外建立 PIT history handoff，設定可選的
`FORMAL_DAILY_PIT_EXPECTED_UNIVERSE`（或
`BALDR_ML_PIT_EXPECTED_UNIVERSE_PATH`）指向 archive 以外、由獨立來源驗證的
排序唯一 symbol JSON；`FORMAL_DAILY_PIT_HISTORY_COVERAGE_START` 指定明確的
`YYYY-MM-DD` coverage 起點。兩者任一缺少時仍可保存 current archive，但 handoff
會保留 `pit_formal_independent_expected_universe_missing` 或
`pit_formal_history_coverage_start_missing` blocker。handoff 以台北每日 08:30
cutoff 逐日檢查 capture／archive availability、官方日曆與 source/license lineage，
並以 create-only bytes 保存到
`<publication_root>\pit_history_candidate\<Taipei decision date>\handoff-<hash>.json`。
它固定 `candidate_only=true`、`formal_ready=false`、
`formal_consumer_compatible=false`；current source union、任何 owner 名稱或
外層重簽 hash 都不能取代獨立 denominator、正式 sidecar publication 與 license
scope evidence。

要安裝這一項 task，先以
`scripts\scheduled\register_formal_input_producer_task.cmd dryrun` 驗證 timezone、
21:25 trigger 與 wrapper path，再以同一腳本的 `register` 模式建立或更新
`baldr-formal-input-producer-daily`；該腳本只呼叫這一項 task 的 `schtasks.exe /Create`，
並套用最長 1 小時與重複 instance=`IgnoreNew`，不會順手重註冊其他 task。Query 顯示目前
環境為 `Interactive only`、電池供電不啟動／切換電池會停止；這不是無人值守服務，必須由
已登入的 Windows 使用者承接首次執行與 terminal status。若來源尚未就緒，task 仍會留下
機器可讀 blocker 並等待下一輪，不會寫入來源資料庫或啟動交易／訓練。整體 task 清單的 aggregate register 仍可供既有維運使用，
但不屬於本項單獨安裝計畫。

`baldr-data-update-quick-daily` 預設以 serial technical-indicator path 執行。
只有在受控 canary 的 task environment 明確設定
`BALDR_ENABLE_TECHNICAL_PROCESS_POOL=1` 時，CMD wrapper 才會傳入
`--enable-technical-process-pool`；worker 上限、in-flight 與 retry 預設仍為
`2 / 4 / 1`，每次 running／terminal status 會留存實際旗標。未設定時不會啟動
technical process pool，也不會因 staging acceptance 自動改變排程行為。

Quick CMD wrapper 固定傳入 `--reverify-unknown-legacy-industry-dates`；Python runner 的此
`store_true` 參數預設 false，且 nullable 欄位解析沒有獨立 CLI flag。只有在方向、漲跌點數、
漲跌百分比全缺值時，parser 才將三欄保留為 NULL；方向空白但任一變動欄有數值（含 0／0.00）、
缺值與數值混合、或未知非空方向都會拒絕。明確正負方向搭配數值 0 仍可接受；收盤指數、
來源日期、表格結構或請求日期驗證失敗仍 fail closed。重查選項只涵蓋請求窗口內沒有有效
projection marker 的 legacy 日期，窗口外日期不重抓，既有有效 marker 略過；不會把缺值補成 0。

技術指標 publication custody 以 calculator 實際回報的最後交易日及 hash-bound
`technical_computation.source_date_start/source_date_end` 為準，不以 scheduler 的自然日
硬套來源窗口。排程在週末或休市日重驗 current technical rows 時，會綁定最近實際交易日
的 TWSE／TPEx daily-price custody receipt；若 computation witness 沒有可驗證的實際日期，
才退回該輪 requested start/end，仍維持 fail closed。

## Direct chain automatic bootstrap

`baldr-ml-direct-chain-maintainer` 的入口是
`scripts/scheduled/run_ml_direct_chain_maintenance.cmd`。wrapper 會從
`OUTPUT_ROOT/release_v4/ml_pit_year_shards/latest_manifest.json` 解析最新
pointer，重驗 publication／dataset canonical hash、`all_universe=true`、raw
dataset safety、`decision_at` 與 official market-event custody，再把已驗證的
immutable manifest 傳給既有 Direct → OOC maintainer。它不建立 raw data、不改寫
來源 SQLite、不建立歷史 sector membership，也不把 `companies.csv` 當成 PIT sidecar。

wrapper 在取得 immutable input 後、啟動 maintainer 前會做唯讀三段 filesystem
capacity preflight。Direct chain scheduled 預設檢查 35 GiB 持久新增、40 GiB 暫存峰值與
200 GiB 安全保留；raw PIT wrapper 也至少保留 200 GiB。任一項不足時只寫
`status=blocked_insufficient_storage` 與 `storage_preflight.capacity_budget`（含
total／used／free bytes 與 blockers），不建立 Direct/OOC worker、不進入 retry loop，也不
刪除既有 run。可用 `--persistent-storage-budget-bytes`、`--temporary-storage-budget-bytes`
與 `--safety-reserve-bytes` 在受控環境調整；舊的 `--minimum-free-space-bytes` 仍作相容安全
保留門檻，但低於 200 GiB 的值會 fail closed。全鏈啟動前可搭配
35 GiB 持久新增與 40 GiB 暫存峰值；required headroom 因此至少為 275 GiB。先用
`--preflight-only` 驗證，再由 owner 依 raw shard 估算與 rollback 空間確認容量。這個容量政策
不是 Formal／promotion gate。

狀態寫入：

```text
<OUTPUT_ROOT>/scheduled/ml_direct_chain_maintenance/latest_status.json
```

wrapper 在長時間監督期間會定期重驗 training output instance lock，並更新
`heartbeat_at`、`maintenance_lock_state` 與 `maintenance_owner_process_id`；因此
`running` 狀態中的 owner 是 child maintainer 取得 lock 後的實際命令列 custody，
不是只在 bootstrap 時讀到的暫時值。wrapper 結束後也會重新讀取一次 lock 狀態。

`status=running` 代表已通過 bootstrap 並正在監督既有 chain；`completed` 代表
wrapper 子程序正常返回（包括 instance lock 已由現有 owner 持有的安全重複觸發）。
若是後者，status 會明列 `execution_disposition=existing_owner_lock`、
`maintenance_lock_state=verified` 與經命令列驗證的 `maintenance_owner_process_id`；命令列
還必須與同一個 `training_output_dir` 完整相符，避免把其他 lineage 的 maintainer 誤認為現有
owner，或把安全跳過誤讀成 Direct/OOC 已完成。若 live owner 命令列暫時無法讀取，wrapper
會改列 `execution_disposition=owner_lock_unverifiable` 與
`maintenance_lock_state=owner_lock_unverifiable`，保留 lock 並等待下次驗證；
`blocked_invalid_bootstrap_input` 代表輸入驗證失敗，舊 publication／run 會保留，
不會用猜測資料啟動訓練。status 永遠明列 `database_mode=ro`、`query_only=true`、
`writes_source_database=false`、`formal_oos_allowed=false`、`production_alpha_bp=0`
與 `broker_order_allowed=false`。完成排程註冊後不需要人工重新執行 Direct、OOC 或
promotion；每日觸發會自動重試，既有 lock 與 hash-bound checkpoint 負責冪等續接。

若要診斷既有 Direct checkpoint 的 provenance，使用唯讀入口：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_ml_direct_checkpoint_provenance.py `
  --store-root <DIRECT_STORE_ROOT>
```

它只讀取 `runs/<run_id>/checkpoint.json` 與同 run 的 manifest，先保存檔案
SHA-256，再區分 `legacy_missing_computation_provenance`、
`computation_identity_drift`、checkpoint／manifest custody corruption，以及
`resumable_under_current_computation_identity`。`checkpoint_provenance_valid`
只代表 checkpoint 的計算身分可驗證；`resume_allowed` 還必須通過已存在
manifest 的 canonical hash、run／identity 對應與 complete checkpoint 對帳。
未完成 checkpoint 尚未有 manifest 時可按 in-progress 語意檢查；已存在但損壞、
竄改或 identity 不符的 manifest 一律阻擋。穩定 computation identity 只綁定
明確 dependency source bytes／compiled source fingerprint，不把 loaded-module
或 runtime constants 的整包 hash 放進 run identity。Legacy checkpoint 絕不由目前
source 自動補 hash；完整 legacy artifact 只保留 audit-only，後續必須經 owner
review、容量與 process custody 檢查後，以新的 run identity 建立 fresh Direct。

OOC handoff 在訓練前還會重新驗證 Direct manifest 與 checkpoint 的 stable identity、
dependency snapshot、runtime custody 及兩者一致性；legacy、drift 或任何 manifest／
checkpoint corruption 都會 fail closed，不會直接把舊 current-v4 store 送進 OOC。
若要一併檢查 lock／gate／process custody，可加
`--maintenance-output-dir <OOC_TRAINING_OUTPUT_DIR>`；工具會保留
`probe_stage`、`errno`、`winerror` 與 unlock 結果，並以 `rb` 做不寫入的 advisory-lock
probe。read-only open 被 permission denied 時只標為 `inspection_permission_unknown`，
不把 sandbox/access denied 推論成 holder 或 stale；`free_observed` 只表示該瞬間未
觀察到 holder，正式 execution 仍必須由 canonical owner protocol 原子取得 reservation；
只有 advisory-lock stage 的明確 lock violation 才能當作該時間點的 holder 證據；
before／after bytes 不一致會標為 `probe_file_changed`，handoff gate enumeration
失敗會標為 `handoff_gate_enumeration_incomplete`，兩者都不會被 aggregate 成
`no_active_lock_observed`。

## OOC refresh continuation

Direct v4 完成後，若新的 PIT sector sidecar 被放入 direct output lineage，
`continue_ml_direct_ooc_after_store.py` 會先以正式 assembler 驗證 canonical manifest、
accepted/license/source hash、可得時間與 training cutoff；全部通過才建立新的 immutable
Direct run，否則沿用現有 publication 並維持 formal gate 關閉。可用
`BALDR_ML_PIT_SECTOR_MEMBERSHIP_PATH` 指向受控來源；未設定時只掃描明確的
`pit_sector_membership`／`sector_membership`／`sidecars` 目錄與固定檔名，不會把
`companies.csv` 或研究輸出當成 PIT 歷史資料。若要讓這個等待跨越 worker／supervisor
中斷，維護程序可加 `--watch-formal-inputs`；它只在偵測到一個合規且唯一的 sidecar
時自動續跑，沒有來源時不會重複訓練。

維護器的 `--watch-formal-inputs` 不只等待 sector sidecar：它會以 pointer、canonical hash、
raw dataset safety、dataset decision_at 與現行 Direct identity 驗證新版或同一 cutoff 的新版
all-field raw PIT publication；也會驗證最新 official market-event publication。合格輸入會在同一
次 immutable Direct → OOC chain 綁定，並保留既有已驗證的 sector sidecar；只重發 wrapper、但
canonical events hash 未變時不會觸發不必要的重訓。這些探測不會自動建立或採用未受控的 causal
non-cash ledger／Rule Champion artifact，formal gate、alpha=0、broker disabled 仍維持。

正式 ledger／Rule Champion 可由受控 Windows 使用者環境變數
`BALDR_ML_FORMAL_PORTFOLIO_LEDGER_PATH`／`BALDR_ML_FORMAL_RULE_CHAMPION_HISTORY_PATH`
交給同一 watcher。維護器先執行唯讀 ledger chain、cutoff 與 Rule history HMAC 驗證；只有
sector、ledger、history 三項都可合法 hash-bind 時，formal-only refresh 才會啟動。分批出現
或驗證失敗的來源只會等待，不會觸發部分重訓、改寫舊 run 或提升 alpha。

長駐 watcher 每輪也會重新讀取 Windows 使用者／系統環境登錄值，讓 watcher 啟動後才完成的 owner deposit 能交接到同一個 process；只會將受控
path、HMAC key 與 store id 放入目前 process memory，絕不寫入檔案、命令列、status 或 log。若 watcher 自己採用的登錄值被移除，會清掉
該 process 內的值並回到 fail-closed 驗證；log 最多記錄被刷新的是變數名稱，不記錄任何 value。這不會繞過 ledger chain、Rule HMAC、PIT
sector 或 formal promotion gate。

獨立執行 `scripts/inspect_ml_formal_input_readiness.py` 時也會使用同一套 controlled Windows registry handoff：它只把 owner deposit 接到當前 read-only process memory，不寫回 registry、artifact 或 source DB。

Direct numeric store runs also publish `runs/<run_id>/heartbeat.json` with the
current stage, PID, completed years, and UTC `updated_at`.  While the OOC
continuation helper is waiting, it mirrors the latest valid heartbeat into
`continuation_status.json` when available and when its PID matches the
direct process being supervised.  This is progress observability only;
`checkpoint.json`, the finalized year manifests, and the hash-bound
`latest_manifest.json` remain the completion authority.  A stale or missing
heartbeat must never be interpreted as a completed store.

New direct builds also publish real annual boundaries: each source shard first
reports `raw_spool_source_shard_<year>_rows_<n>_processed` while validating (at
least every 100,000 rows or after 30 seconds without a progress event) and
then `raw_spool_source_shard_<year>_complete`, followed by
`year_raw_spool_complete` and `year_labels_complete`. During the potentially
long annual assembly, the builder reports
`assembly_decision_<date>_rows_<n>_processed` from the sample-row loop at the
same bounded row/time cadence, so a single large decision date cannot silence
the heartbeat. The label-spool stage also reports
`label_spool_starting_<symbols>_symbols_<dates>_dates`, bounded
`label_spool_symbol_<n>_of_<total>_decision_<n>_of_<total>_processed` events
while a single symbol is expensive, and `label_spool_symbols_<n>_of_<total>_processed`
at symbol boundaries, followed by `label_spool_complete`. The annual stages then
continue with `year_assembly_complete`, `year_artifacts_complete`, and
`year_directory_finalized`. These are
observability stages only; continuation still requires the checkpoint,
finalized year manifest, and hash-bound latest pointer before it can start OOC
training.

The initial raw discovery pass uses the same bounded heartbeat contract. It
reports `discovery_source_shard_<year>_rows_<n>_processed` and
`discovery_source_shard_<year>_complete` while verifying compressed hashes,
row hashes, feature definitions, and source content custody, so a long resume
scan remains observable without treating progress as completion.

After a successful discovery, the direct run stores a hash-bound
`discovery_cache.json`. A later checkpoint resume rechecks the raw manifest
identity and every compressed shard hash before reusing the cached feature
registry, calendar, folds, and source digest; any mismatch falls back to the
full fail-closed discovery scan.

Promotion evidence custody compares the official market-event canonical file
hash to the direct store. A republished wrapper with the same
`canonical_events_hash` is accepted as a no-op publication change, so an
unchanged immutable direct store is not rebuilt solely for corrected duplicate
metadata. Any canonical timeline hash change still produces
`formal_ooc_corporate_action_custody_stale` and remains fail-closed.

On Windows a venv launcher may have a separate Python worker PID.  The OOC
continuation accepts a direct heartbeat only when its PID is the supervised
launcher or a live descendant of that launcher; an unrelated or stale PID is
ignored.  This preserves process custody while still exposing the real annual
stage.

The annual raw spool now commits at each source-shard boundary to keep the
ephemeral SQLite transaction bounded; no annual artifact is published until
the complete work directory, hashes, and checkpoint pass validation.

The OOC trainer also keeps final-meta training bounded: it streams matured OOF
rows fold-by-fold and batch-by-batch, uses only a deterministic bounded sample
for medians, and makes separate bounded passes for normalization, Gram fitting,
and logistic IRLS. It does not materialize one full-width `train.meta.f32`, so
the 4GB memory guard remains meaningful on Windows.

OOC classifier calibration now has an expanding outer-fold cross-fitted
diagnostic: each target fold uses only earlier OOF blocks whose labels are
mature before the next fold starts. The report is integer-bp and explicitly
`oof_diagnostic_only=true` / `production_eligible=false`; it does not rewrite
the raw base vector consumed by the meta allocator. A later training manifest
may therefore replace `classifier_calibration_not_cross_fitted` with
`classifier_calibration_not_attached_to_ooc_model`; that remains a fail-closed
shadow boundary until a calibration artifact is attached to OOC inference.

若要先做成本後增益的低複雜度 shadow，可直接執行
`scripts\train_ml_allocation_out_of_core.py --profile minimal_linear_shadow --algorithm ridge_logistic --horizon <H>`；
這個 profile 強制單一 Ridge／Logistic 與單一明確 horizon，缺少恰好一個 horizon 或指定
HGB 會停止。`full_shadow` 才是既有多 horizon／Ridge+HGB 研究流程；兩者均不授予
Formal OOS、非零 alpha 或 broker 權限。

`scripts\continue_ml_direct_ooc_after_store.py` 啟動時會先將 `continuation_status.json` 寫成 `waiting_for_direct_store`，避免沿用上一輪的 terminal `blocked` 診斷；direct store 完成後才會驗證 custody 並啟動 OOC。所有新版 waiting、custody、training heartbeat、complete 與 blocked status 都明列 `formal_oos_allowed=false`、`production_alpha_bp=0`、`broker_order_allowed=false`。若舊版 helper 完成時缺少這三個欄位，已結束 OOC helper 的 release coordinator 會自動補寫 fail-closed 欄位；明確的 true／非零值則直接阻擋，不以缺欄位或不安全值放行。Direct numeric v4 會把官方 halt/resume timeline 以 decision-time `effective_at`／`available_at` 寫入 replay source；舊 direct run 不會被原地改寫，續接流程會以新的 immutable custody 重新發布。接著 `scripts\continue_ml_release_after_ooc.py` 必須先觀察到 PID 與命令列均相符的 OOC helper，再等待其結束；之後才確認 training `latest_manifest.json`、continuation status 與兩者 manifest hash 完整一致，並依序執行 promotion evidence、promotion authority 與 daily ML copilot。任何缺件、hash 不一致或非零 exit code 都只寫 `blocked`，它不取代 Windows Task Scheduler，也不修改正式 market SQLite。

若 direct process 已正常完成但 supervisor 因 Windows custody／launcher race 中斷，可使用 `--resume-after-direct-store` 重新驗證 immutable direct manifest 後續接 OOC；此模式不宣稱 direct PID 仍存活，且同樣要求完整 checkpoint、年度 manifest、fold index 與 hash custody。

release follow-up 的三個命令現在以受監督子程序執行；每個命令會在 `post_ooc_followup_status.json` 發布 `followup_command_running`／`followup_command_complete`、子程序 PID、命令序號、開始時間與 return code。這只增加長命令的可觀測性，不改變 fail-closed promotion gate 或任何正式資料寫入邊界。

ML promotion evidence 與 promotion authority 的 status／pointer atomic publication 也使用 120 次、每次 0.5 秒的 Windows transient-lock bounded retry；重試耗盡仍會 fail-closed，不會以半成品覆寫既有狀態。

OOC handoff 在啟動訓練前會先發布 `store_custody_validation_starting`，再重新計算 direct top-level manifest canonical hash，並驗證 complete checkpoint、每個年度的 8 個 artifact hash／byte custody，以及所有 fold index artifact；任一年度、fold 或 checkpoint 不一致即停止在 `blocked`，不會開始訓練。

若現行 legacy direct run 已經在執行，`scripts\continue_ml_direct_v3_refresh_chain.py` 可由受控背景程序接手：它先以 PID／完整命令列等待既有 direct、OOC、release 三層全部結束，再啟動新的 immutable v4 direct build，並在 direct process 尚未退出前綁定新的 OOC helper 與 release helper，避免 process-custody race。狀態保存於 `v3_refresh_chain_status.json`，建置與下游輸出保存於 direct/training `logs\*v3_refresh.log`；任何失敗仍 fail-closed，不會刪除舊 run、改寫正式 SQLite 或開啟 alpha。

若 supervisor 本身在 legacy chain 停止後被中斷，重啟時使用 `--resume-after-legacy-chain`；此模式會先掃描完整命令列，若仍有任何相符的 direct／OOC／release process 就拒絕啟動，確認無 active target 後才從既有 checkpoint 接續。正常模式會在等待前一次性驗證三個 legacy PID，避免後續 helper 已先退出而造成錯誤的 custody failure。

若需要讓這條長時間 refresh chain 在 worker 或 supervisor 因 Windows sleep／process
中斷後自行恢復，可由受控背景程序執行
`scripts\maintain_ml_direct_v3_refresh_chain.py`。它會先以完整命令列掃描
Direct／OOC／release target；只要任一 target 存活就只等待，不會平行啟動。全部
target 停止且 primary status 尚未 `complete` 時，才會呼叫既有
`--resume-after-legacy-chain`，由相同 run identity 的 checkpoint、年度 manifest
與 raw hash 決定可否續跑。它另以 training output 目錄的 instance lock 防止兩個
維護器競爭；任何 retry 都維持 `formal_oos_allowed=false`、alpha 0、broker false，
不刪除舊 run、不改寫正式 SQLite 或手動發布 pointer。

補充：`continue_ml_direct_v3_refresh_chain.py` 若以自訂 `--status-path` 啟動，會自動把 direct／OOC／release 的 operational log 寫到 heartbeat 同層的 `logs` 目錄；因此即使正式資料目錄的 log 權限受限，也能繼續執行而不改寫正式資料。未指定自訂 status path 時仍使用既有 direct/training `logs` 位置。

## Register

Preview:

```cmd
scripts\scheduled\register_baldr_scheduled_tasks.cmd dryrun
```

Create or replace the daily tasks:

```cmd
scripts\scheduled\register_baldr_scheduled_tasks.cmd register
```

Create or replace all 16 daily tasks and the weekly collection task in one explicit operation:

    scripts\scheduled\register_baldr_scheduled_tasks.cmd register-all

Both registration modes run a wrapper-file preflight first. If a selected wrapper
is missing, the command exits before calling schtasks and leaves existing tasks
untouched. Use dryrun to inspect all 17 actions without registration.

The register script creates:

```text
baldr-data-update-quick-daily
  DAILY 04:20
  cmd.exe /c "<repo>\scripts\scheduled\run_daily_data_update_quick.cmd"

baldr-official-market-events-daily
  DAILY 04:50
  cmd.exe /c "<repo>\scripts\scheduled\run_official_market_event_backfill.cmd"

baldr-data-freshness-check-daily
  DAILY 05:00
  cmd.exe /c "<repo>\scripts\scheduled\run_daily_data_freshness_check.cmd"

baldr-ml-raw-pit-refresh-daily
  DAILY 05:05
  cmd.exe /c "<repo>\scripts\scheduled\run_ml_raw_pit_refresh.cmd"

baldr-recommendation-snapshot-daily
  DAILY 05:10
  cmd.exe /c "<repo>\scripts\scheduled\run_recommendation_snapshot.cmd"

baldr-evidence-pipeline-dry-run-daily
  DAILY 05:15
  cmd.exe /c "<repo>\scripts\scheduled\run_evidence_pipeline_dry_run.cmd"

baldr-ml-promotion-evidence-daily
  DAILY 05:17
  cmd.exe /c "<repo>\scripts\scheduled\run_ml_promotion_evidence.cmd"

baldr-ml-promotion-authority-daily
  DAILY 05:18
  cmd.exe /c "<repo>\scripts\scheduled\run_ml_promotion_authority.cmd"

baldr-ml-allocation-copilot-daily
  DAILY 05:20
  cmd.exe /c "<repo>\scripts\scheduled\run_ml_allocation_copilot.cmd"

baldr-decision-evidence-capture-daily
  DAILY 05:25
  cmd.exe /c "<repo>\scripts\scheduled\run_decision_evidence_capture.cmd"

baldr-paper-portfolio-daily
  DAILY Asia/Taipei 08:25 (+08:00; UTC 00:25; 17:25 PDT / 16:25 PST previous date)
  cmd.exe /c "<repo>\scripts\scheduled\run_paper_portfolio_daily.cmd"
```

舊 `baldr-evidence-working-copy-smoke-manual` 不再屬於排程清單；獨立 smoke script 只保留作工程診斷。unregister wrapper 仍會清除可能殘留的舊 task。

只建立或取代週日 sidecar collection task：

```cmd
scripts\scheduled\register_baldr_scheduled_tasks.cmd weekly-register
```

`weekly-register` 只建立 `baldr-v2-2-weekly-collection`，其排程為 `WEEKLY SUN 18:00` 並執行 `run_v2_2_weekly_collection.cmd`。它不建立、取代、啟用或以其他方式變更任何每日 task。

The weekly-register mode still only changes the weekly collection task. The
register-all mode performs the daily and weekly registrations together, but
both modes require the selected wrapper files to pass preflight first.

## Query

ML forward 等候台北 cutoff 時另保存 operational custody：
`output/v4_ml_forward_scheduler/runtime_state.json` 及 `run_state/<unique-run-id>/state.json`。
每次 wait observation（間隔最多 60 秒）更新 phase／heartbeat；可捕捉中斷回 130，未處理
例外保留失敗 state 並正常以非零退出，terminal state 保存真正 run_once return code。
等待 state 不覆寫 business latest status、不授予 forward credit。硬 kill 後留下非 terminal
heartbeat 只能證明最後觀察時間，`terminator=unknown`，不是仍存活或已知中止者的證據。

```cmd
scripts\scheduled\query_baldr_scheduled_tasks.cmd
schtasks /Query /TN baldr-official-market-events-daily /V /FO LIST
schtasks /Query /TN baldr-data-freshness-check-daily /V /FO LIST
schtasks /Query /TN baldr-ml-raw-pit-refresh-daily /V /FO LIST
schtasks /Query /TN baldr-recommendation-snapshot-daily /V /FO LIST
schtasks /Query /TN baldr-evidence-pipeline-dry-run-daily /V /FO LIST
schtasks /Query /TN baldr-ml-promotion-evidence-daily /V /FO LIST
schtasks /Query /TN baldr-ml-promotion-authority-daily /V /FO LIST
schtasks /Query /TN baldr-ml-allocation-copilot-daily /V /FO LIST
schtasks /Query /TN baldr-decision-evidence-capture-daily /V /FO LIST
schtasks /Query /TN baldr-paper-portfolio-daily /V /FO LIST
schtasks /Query /TN baldr-v2-2-weekly-collection /V /FO LIST
```

查詢錯誤、sandbox Access denied 與 detail error 均為 unknown；完整 COM enumeration
後才能判定 missing。wrapper 不把本機查詢失敗當成 task 不存在，也不把 producer exit
當作 Scheduler LastTaskResult。

機器可讀的唯讀檢查使用 `scripts\inspect_scheduled_task_registration.py`，或上述 CMD
query 入口。工具核對 21 個 exact root tasks（含 05:45 learning 與 05:50 BankTaiwan）、
本機 wrapper、實際 action、WorkingDirectory 與 trigger；COM 補充 State、原生
LastTaskResult、last／next host-local time、missed count、timeout、retry、parallel、
battery 與 StartWhenAvailable。`configuration_ready` 只表示設定核對完整，不證明 producer
或資料品質成功。缺 action／working directory 為 unobserved；query error 為 unknown。
工具遮蔽帳號、secret 與 SID，不修改 task，也不提升 Windows 權限。

Query 的 task inventory 與機器 inspector 由 regression 核對完全一致；CMD summary 的
expected count 由清單推導，不再以舊的 20 項硬編碼。這只是可觀測性，不會讓 aggregate
register 接管 BankTaiwan／forward 等專用 task，也不把 `Last Result=0` 當成來源完整。

## Unregister

Preview:

```cmd
scripts\scheduled\unregister_baldr_scheduled_tasks.cmd dryrun
```

Remove the scheduled tasks:

```cmd
scripts\scheduled\unregister_baldr_scheduled_tasks.cmd unregister
```

也可以在 Windows Task Scheduler 手動停用或刪除每日 task。若只要停止週日 sidecar collection，請在其中停用 `baldr-v2-2-weekly-collection`，或執行：

```cmd
scripts\scheduled\unregister_baldr_scheduled_tasks.cmd weekly-unregister
```

Rollback 時禁止自動 drop sidecar SQLite table；保留 `pending_human_review` 與 `collection_failed` record 供稽核與人工處理。

## Logs And Reports

官方市場事件：

```text
<OUTPUT_ROOT>/scheduled/official_market_events/latest_status.json
<OUTPUT_ROOT>/release_v4/official_market_events/latest_manifest.json
<OUTPUT_ROOT>/release_v4/official_market_events/runs/<publication_id>/
<OUTPUT_ROOT>/release_v4/official_market_events/quarantine/<failure_id>/
```

TPEx 官方端點暫時不可用時，wrapper 會保留最後一個完整 formal publication，將本次失敗的 raw custody 移入 quarantine，並在 `latest_status.json` 記錄 `failure_class`、`formal_publication_preserved` 與可重試狀態；不會寫入 active SQLite，也不需要人工確認。若 latest pointer 仍可驗證但只涵蓋近兩年，下一次成功執行會自動 recovery 到 2014 起點；只有通過完整年度覆蓋與 hash 驗證的 publication 才能繼續供 PIT／ML evidence 使用。

TWT49U 的名稱修訂是受限的顯示觀測例外，不是 last-write-wins：只有同一 natural key、source identity 與所有經濟欄位完全相同，且差異只在 `股票名稱` 時，才建立 `revision_kind=display_name_only`。舊版與新版 raw response 都留在下一份 publication 的 `raw_index.jsonl`；新版 canonical row 的 `available_at` 取該 raw 的 `retrieved_at`，所以 historical `as_of` 不會把後來才觀測到的名稱倒灌到較早日期。adjustment sidecar 仍保留每個 revision 的 source lineage，但 `portfolio_ml_dataset_assembler` 以 `available_at` 選可用 revision、以 set 聚合 effective date；兩版不會形成兩個 eligible effective dates，也不會把 adjustment factor 乘兩次。sidecar 固定 `prospective_only=true`、`historical_pit_eligible=false`，不得直接當 historical price adjustment 或 Formal feature。經濟欄位、日期、代號、source identity、schema／endpoint 異常或 predecessor 不明時，維持 quarantine／fail closed；不覆寫舊 raw、canonical history、SQLite 或 last-known-good pointer。

Data freshness:

The quick update publishes `status=running` with a run/process identity before its long-running steps begin, then records `started_at` and `completed_at` on the terminal status. Downstream freshness and ML evidence checks treat a running or stale update as not-ready, so a partially completed update cannot be consumed.

若正式 `OUTPUT_ROOT` 的 ACL 只允許讀取，`run_daily_data_freshness_check.cmd` 可由 owner
明確設定 `BALDR_FRESHNESS_STATUS_PATH`；若未另外設定
`BALDR_FRESHNESS_LOG_PATH`，wrapper 會把 log 放在 status path 同一位置（加上 `.log`）。
兩個變數都未設定時維持既有 `<OUTPUT_ROOT>/scheduled/data_freshness/` 出口。這只改變
read-only status／log 的寫入位置，不會繞過正式 DB、scheduler、Evidence 或 Formal gate；
UI 若要讀取外部 status，另需設定 `DATA_FRESHNESS_STATUS_ARTIFACT` 指向同一個明確檔案。
若 status／log 路徑仍因 ACL 或其他 `OSError` 無法寫入，canonical
`data_freshness_probe.py` 不再留下未處理 traceback；它會在 stdout 輸出
`status=failed` 與 `status_artifact_write_failed:<ErrorType>`／
`log_artifact_write_failed:<ErrorType>`，並以 exit code `1` 結束。如此 scheduler／wrapper
可以把「資料檢查失敗」與「結果檔無法發布」分開診斷；能寫入的 artifact 也會被重寫成同一份
結構化錯誤，不會沿用舊的 `passed` 假狀態。
`run_daily_data_freshness_check.ps1` 也只委派這個 canonical probe，並接受相同的
`BALDR_FRESHNESS_STATUS_PATH`／`BALDR_FRESHNESS_LOG_PATH` 或參數覆寫，避免維運入口維護第二套
日期／freshness 判定。

Freshness receipt 的 `checks` 明示 `calendar_cutoff_local="04:30"` 與
`calendar_cutoff_timezone="America/Los_Angeles"`。狀態頁按該時區的每日 cutoff
比較檢查／查詢是否處於同一發布週期，不以台北午夜判過期；跨下一 cutoff 就要求重新
probe。舊的無時區收據只相容精確 `baldr-data-freshness-check-daily` 的既有固定契約。
未知時區、未來或無時區 checked_at 仍拒絕；本契約不授予來源公告時間或歷史 PIT 資格。

The same runner appends bounded `data-update-status-history.v1` records to `history.jsonl` (or the explicit `--history-path`) for the running and terminal attempts. The history is append-only and idempotent by record hash; it does not backfill an existing `latest_status.json` and does not change any downstream readiness or write permission.

The status boundary converts service result dataclasses (including the Phase 3C `BackfillSummary`), paths, dates, and scalar wrappers before writing JSON or history. A serialization problem in one step therefore cannot leave the run permanently reported as `running`; the terminal status is still published and the original structured result remains visible in the artifact.

```text
<OUTPUT_ROOT>/scheduled/data_update_quick/latest_status.json
<OUTPUT_ROOT>/scheduled/data_update_quick/history.jsonl
<OUTPUT_ROOT>/scheduled/data_update_quick/YYYYMMDD_data_update_quick.log
<OUTPUT_ROOT>/scheduled/data_freshness/latest_status.json
<OUTPUT_ROOT>/scheduled/data_freshness/YYYYMMDD_data_freshness.log
```

Automatic raw PIT refresh:

```text
<OUTPUT_ROOT>/scheduled/ml_raw_pit_refresh/latest_status.json
<OUTPUT_ROOT>/scheduled/ml_raw_pit_refresh/refresh.log
<OUTPUT_ROOT>/release_v4/ml_pit_year_shards/latest_manifest.json
<OUTPUT_ROOT>/release_v4/ml_pit_year_shards/runs/<publication_id>/
```

`latest_status.json` records the upstream data-update status, core dates, decision cutoff,
source database read-only contract, builder return code, and published manifest hashes.
若 builder 因 daily-price source quality guard 退出，terminal receipt 另保存 bounded
`source_quality_summary`：candidate／classification 計數、受影響日期 top list、最多 12
筆樣本與完整 report hash；不保存數百萬筆 candidate payload，也不以摘要放寬
quarantine。這讓 ML/data-quality owner 可先依日期／市場 probe 定位缺檔或數值映射
問題，修復與重跑仍須另行審核。
`blocked_upstream_not_ready` means the runner waits for a later data-update proof;
`skipped_current` means the current pointer already covers the cutoff; `completed` means
the immutable raw publication passed pointer, canonical hash, all-universe scope, dataset
safety, and decision-time validation. `blocked_insufficient_storage` means the runner
observed less than the configured free-space threshold before launching the builder; the
status includes `storage_preflight` and the runner never creates a partial publication.
The runner never deletes an earlier publication.

`data_update_quick/latest_status.json` uses `passed_with_warnings` when TPEX failed dates remain, for example `TPEX 每日股價缺少日期：20260706`. `data_freshness/latest_status.json` uses `degraded` when SQLite is current but either `daily_price/YYYYMMDD.csv` or `daily_price_tpex/YYYYMMDD.csv` is missing for that latest daily date.

Phase3C institutional／credit／TDCC quick steps 寫入明確設定的隔離 candidate DB。freshness probe 以 SQLite `mode=ro`／`PRAGMA query_only=ON` 直接驗證該 candidate DB 的 latest date、TWSE／TPEx source versions、natural-key duplicates 與 row count，不再以正式 `twstock.db` 的舊 candidate tables 代表 quick step。官方 endpoint 的 HTTP 200 若仍是 release-not-ready `stat` 或缺明細 table，fetcher 最多重試 3 次、每次等待 30 秒；transport error、日期 mismatch 與 schema mismatch 不會被這個 retry 隱藏。

`fundamental_current_observations` 可由受控 snapshot apply 更新目前觀測值，但不是 formal PIT promotion。`fundamental_monthly_revenues`／formal statement table 缺 expected period 時，仍要求 official announcement、availability 與 revision lineage；freshness 會保留 fundamental degradation，不會用 current-only row 冒充歷史可得性。

Recommendation snapshot:

```text
<OUTPUT_ROOT>/scheduled/recommendation_snapshot/latest_status.json
<OUTPUT_ROOT>/scheduled/recommendation_snapshot/YYYYMMDD_recommendation_snapshot.log
<OUTPUT_ROOT>/recommendation/runs/execution_artifacts/<opaque-id-sha256>.json
<OUTPUT_ROOT>/recommendation/runs/recommendation_runs.db
```

The wrapper saves the canonical execution before invoking the forward producer. The
artifact and its SQLite index share the same `recommendation/runs/` root; the query
readback is verified by result identity and payload hash. The status and log paths above
are unchanged. Historical legacy `<result_id>.json` files are read-only and are not
recreated by this scheduled task.

The recommendation snapshot status includes `result_id`, `recommendations_count`, `screening_matrix_rows`, `why_not_payload_rows`, `liquidity_gate_payload_rows`, `writes_recommendation_result`, `writes_evidence_db`, `auto_trading`, and `lifecycle_action`.
Canonical request 的 `as_of_date` 必須取自同一份 typed body context；只有 caller 明確
指定時才可覆寫，body context 缺值時才退回 runtime config。這確保 persisted request、
context 與 learning cohort preflight 使用同一資料日，不會把自然執行日誤當市場資料日。

Recommendation calibration learning (shadow-only):

05:45 orchestration 若已找到同日 formal technical publication，仍須通過既有 source contract
對來源、hash、窗口與 available-at 的完整重驗；通過才記錄
`steps.data_update_quick.status=skipped`／`verified_existing_same_day_technical_receipt`，不再
重啟 quick updater 或覆寫其 latest status。只有日期相同、receipt path 存在並不足以重用。
不合格時走既有 bounded updater／fail-closed 分支；不關閉 source-revision 或未來資料 gate。

```text
baldr-recommendation-calibration-learning-daily
  DAILY 05:45 canonical host local time
  Task Scheduler XML: StartBoundary=2026-09-13T05:45:00 (no offset; host-local trigger)
  cmd.exe /c "<repo>\scripts\scheduled\run_recommendation_calibration_learning.cmd"
```

這個 task 接續同一 canonical host local time 的 05:40 `baldr-forward-outcomes-daily`；在
deployment host 上兩者都以無 offset 的 host-local trigger 保存，維持 05:40 → 05:45 的順序；
runner 另以 `Asia/Taipei` clock 與 official calendar 判定資料日期。
canonical entrypoint 是
`scripts\scheduled\run_daily_recommendation_learning.py`；它以 SQLite
`mode=ro`／`PRAGMA query_only=ON` 讀取 bounded historical training rows、當日
candidate／active capture 與真正成熟的 forward outcomes，只把 versioned dataset、candidate、
evidence、authority receipt 與 fail-closed pointer 寫入隔離的
`RECOMMENDATION_LEARNING_OUTPUT_ROOT\recommendation_learning\`。它不繼承一般產品的
`OUTPUT_ROOT` 作為 learning artifact root，也不寫 `recommendation`、`evidence_outcomes`、
Portfolio、Formal、broker 或正式推薦權重。

BankTaiwan shadow operational wrapper 使用與 Formal/Paper 相同的 repository
`output/paper_execution_eod_replay/calendar_cache`（可由
`FORMAL_DAILY_CALENDAR_CACHE_ROOT` 覆寫）判斷國定休市日。確認休市時不讀取同日
recommendation snapshot，receipt 會標示 `snapshot.status=not_applicable` 並以
`skipped_non_trading_day`／exit 0 結束；日曆證據 unknown 才保留 recoverable dependency。

learning root 由 scheduler、runner、read-only calibration consumer 與 Workbench 共用同一個
resolver。未指定 `RECOMMENDATION_LEARNING_OUTPUT_ROOT` 或 CLI `--output-root` 時，若
`DATA_ROOT=D:\Min\Python\Project\FA_Data`，預設為同層的
`D:\Min\Python\Project\FA_Data_Shadow`；自訂 `DATA_ROOT` 時預設為
`<DATA_ROOT 的上一層>\FA_Data_Shadow`。明確 override 必須是絕對路徑且位於
`DATA_ROOT` 外；違反時 CLI 會輸出 `recommendation_learning_output_root_invalid` 並以 exit code 2
fail closed。正式 recommendation snapshot 仍可使用一般 `OUTPUT_ROOT`，但不應與 learning
shadow artifact 混用。

Windows wrapper 只接受明確的 `BALDR_PYTHON`，或 repository
`.venv\Scripts\python.exe`；兩者皆不存在時直接 fail closed，不退回 PATH 的未治理
`python`。正式整合到 `C:\Projects\PythonProjects\technical_analysis` 後，應確認
`C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe` 存在，或在
Task Scheduler service environment 明確設定 `BALDR_PYTHON`，並從 wrapper log 的
`Governed Python` 行核對實際 interpreter。

若未設定 `RECOMMENDATION_LEARNING_SYMBOLS`，wrapper 只讀同日 scheduled recommendation
snapshot 已明確保存的 symbol cohort；不做 universe discovery。`latest_eligible_dates` 只限制
bounded replay 選取，不能把 historical replay 當 natural forward evidence。candidate freeze
後，每日 live capture 會保存 feature、candidate／active identity、manifest／artifact／lineage
hash；active monitor 與 challenger 分開，當日新 evidence 成熟後會重新檢查 active performance，
因此當天達到 20 個不同 decision dates 且 breach drift gate 時可立即 rollback，不等隔日。

`recommendation_source_contract` 若存在，service 不信任宣告的 `verified` bool：會重算
symbol-scoped 實際來源 rows 的 canonical digest、期間與 symbol coverage，並驗證 feature builder
實際使用的 technical row `available_at <= decision`。corporate action source 需有可讀實際
records、有效 factor、coverage 與一致 digest；raw label window 遇 non-unit action 且沒有
adjusted-price custody 時，受影響列保守排除並保留 blocker。正式 DB 缺 contract／來源時仍可
建立 research training，但 receipt 必須揭露 source blocker。

after-cost target 只使用有來源的 `evidence_outcomes.liquidity_cost_bp`。成本缺失時 target、
after-cost model output 與 consumer projection 保持 missing；成本存在時使用獨立
`after_cost_null_benchmark_50pct_v1`／5000 bp baseline。adopted active model 的 post-adoption
matured rows 只有在 label availability cutoff 前成熟並通過 identity／receipt 驗證後，才可進
下一個 training cycle。

主要輸出：

```text
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\latest_status.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\runs\YYYY-MM-DD\run_receipt.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\datasets\<dataset_id>\dataset.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\challenger\current.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\captures\YYYY-MM-DD\<candidate_id>.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\active_captures\YYYY-MM-DD\<candidate_id>.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\evidence\<candidate_id>\YYYY-MM-DD.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\active_evidence\<candidate_id>\YYYY-MM-DD.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\recommendation-calibration-active-pointer.json
```

`pending` 只表示等待自然 maturity／樣本門檻；`retain_current`／`rule_only` 表示 authority
未通過；`adopt` 仍是 shadow consumer 的 versioned projection，不是正式 Recommendation
變更；`rollback` 會恢復 previous candidate 或 explicit rule-only。pointer、artifact、manifest、
lineage、policy、source contract 或 evidence receipt 損壞時 fail closed。建議以明確隔離的
output root 先執行 bounded CLI；非 Asia/Taipei official trading day 會跳過 live capture，
不會偽造交易日。

Evidence dry-run:

```text
<OUTPUT_ROOT>/scheduled/evidence_pipeline_dry_run/latest_status.json
<OUTPUT_ROOT>/scheduled/evidence_pipeline_dry_run/YYYYMMDD_HHMMSS_microseconds_evidence_pipeline_dry_run.log
<OUTPUT_ROOT>/scheduled/evidence_pipeline_dry_run/YYYYMMDD_HHMMSS_microseconds_exit_effectiveness.log
<OUTPUT_ROOT>/scheduled/evidence_pipeline_dry_run/reports/YYYYMMDD_evidence_pipeline_dry_run.md
```

CMD 與 PowerShell wrapper 都委派同一個 scheduled orchestrator，且預設讀取隔離 Paper status `output/paper_execution_eod_replay/scheduled/paper_portfolio_isolated/latest_status.json`。Paper 外層 status 使用 `paper-portfolio-daily-status.v1`；隔離 scope version 是獨立欄位。consumer 只保留有明確 boundary flags 的 bounded legacy compatibility，不接受任意 schema alias。

Position Health market source 只在核心 daily-price／technical lane 已 current、quick warnings 僅屬 Phase3C candidate step、freshness degradation 僅屬明列的 fundamental current-observation lane 時允許 `degraded` 繼續；未知 warning 仍 blocked。Frozen Rule provider 接受 producer 的 `rule_source_bundle_created`／`rule_source_bundle_reused`。Exit Effectiveness child 使用 300 秒 bounded timeout；主 pipeline 與 child log 每次使用唯一 timestamp，log write error 轉成結構化 blocker／非零 exit，不以 traceback 終止 wrapper。

Exit artifact 以 create-only 寫入 `OUTPUT_ROOT/exit_effectiveness/YYYYMMDD.json`；同日 bytes 不同時 producer 使用 16 位 SHA-256 後綴 sibling，保留原檔。Wrapper 只把 child 回傳且通過 exact root／date filename、32 MiB bounded no-follow readback、file hash、schema／台北業務日／UTC generated clock、evidence hash、stdout body 與 research-only flags 驗證的檔案記作 actual artifact。Status 的 `exit_effectiveness_output` 是 requested path，`exit_effectiveness_artifact_path` 才是 verified actual path；無效或缺少目前 v1 artifact identity 會 blocked，不讀回 requested 舊檔。此 32 MiB 上限只適用 Exit Effectiveness artifact，不套用至 BankTaiwan snapshot。

Position Health proposal identity v2 只 hash 決策承載內容與 semantic source hashes；capture timestamps、artifact paths 與 receipt-only file hashes 仍保留在結果 provenance，但不會讓相同市場 rows 的同日重試變成衝突。scheduler／Exit 使用 `<OUTPUT_ROOT>/position_health_transition/position_health_transitions_v2.sqlite`；舊 `position_health_transitions.sqlite` 原封不動保留，不自動搬移或升級未核准 proposal。實質 position、condition、metric、policy 或 semantic source hash 改變時，同一 position/date 仍 fail closed。

ML allocation Production Co-pilot：

```text
<OUTPUT_ROOT>/scheduled/ml_promotion_evidence/latest_status.json
<OUTPUT_ROOT>/release_v4/ml_allocation_promotion_evidence/latest_pointer.json
<OUTPUT_ROOT>/release_v4/ml_promotion_authority/latest_status.json
<OUTPUT_ROOT>/release_v4/ml_promotion_authority/latest_authorization_pointer.json
<OUTPUT_ROOT>/scheduled/ml_allocation_copilot/latest_status.json
<OUTPUT_ROOT>/scheduled/ml_allocation_copilot/raw_pit_publications/runs/<publication_id>/
<OUTPUT_ROOT>/scheduled/ml_allocation_copilot/orchestration/YYYYMMDD/<run_hash>/*_post_freeze_shadow_input.json.gz
<OUTPUT_ROOT>/scheduled/ml_allocation_copilot/orchestration/YYYYMMDD/<run_hash>/*_allocation_proposal.json
<OUTPUT_ROOT>/scheduled/ml_allocation_copilot/artifacts/YYYYMMDD_<hash>_promotion.json
<OUTPUT_ROOT>/scheduled/ml_allocation_copilot/sidecar/YYYYMMDD_<hash>_shadow.json
```

排程入口是 `scripts/run_daily_ml_allocation_orchestration.py`。它先用官方交易日曆求 strict T-1，再從正式 SQLite 以 `mode=ro/query_only` 發布固定 11 檔、730 日 causal lookback 的 immutable `all_field_enriched` raw snapshot；只在 post-freeze input 與 ML allocation inference 都成功後才呼叫 promotion evaluator。`<run_hash>` 綁定決策時間、raw publication、凍結 training manifest、模型 artifact 與 policy；相同輸入冪等重跑，不同 custody 版本不覆蓋舊輸出。凍結 release 預設為 `DATA_ROOT/output/release_v4/ml_allocation_bounded_v4_operational`，可用 `BALDR_ML_RELEASE_ROOT` 覆寫。新增的 `AllocationReleaseAdapter` 會在 daily consumer 載入前重驗 release manifest、artifact／preprocessor／calibrator hash、feature order、missing policy 與 dataset lineage；同一批 frozen rows 可執行 OOC→release parity，任何 mismatch 直接停止 ML path。校準 mapping 僅接受跨 fold 的單調整數 bp artifact，未附正式校準器時仍回退既有未校準輸出並保留 Rule-only 邊界。

任何 release、官方日曆、strict T-1、raw publication、post-freeze input 或 inference 缺件都會留下 `passed_rule_only`、`alpha=0`、`formal_oos_allowed=false`、`broker_order_allowed=false`，且不呼叫 promotion evaluator，因此不會新增假的 shadow sidecar。`latest_status.json` 明列 `post_freeze_input_status`、`inference_status`、`promotion_status`，以及 raw manifest、input、兩份 audit、proposal、replay 與 promotion 的 domain/file hashes。完成 inference 後產生的 sidecar 只代表一筆 observation；每日編排器固定輸出 `shadow_day_credit_allowed=false`，是否能列入 20 個真實交易日由後續 evidence collector 依完整性另行判定，不在此處自行加總。

Promotion evidence 與 authorization 不接受人工作業環境變數注入。05:17 builder 只能從固定、hash-bound custody pointer 發布 unsigned evidence；05:18 Authority 只能以 DPAPI 保護的本機 user-scope key 簽署同一決策窗；05:20 Co-pilot 只讀固定 `latest_authorization_pointer.json`，且再次要求授權的 model／dataset 與實際 inference release 完全相同。任何錯配都回退 Rule-only。

四條 alpha lane 固定為 `0 / 2000 / 3500 / 5000 bp`。Evidence 不存在、格式無效、門檻未通過或 authorization hash 不相符時，runner 一律 fail closed 為 `alpha=0`。同一決策日與同一輸入會得到相同 hash 與相同檔名；若同日證據版本不同，舊 sidecar 與 artifact 仍會保留。

Decision Desk / Evidence confirmed capture：

```text
<OUTPUT_ROOT>/scheduled/decision_evidence_capture/latest_status.json
```

`latest_status.json` 記錄 `calendar_decision_at`（只負責選擇已到達的台北 08:30 日曆日）、實際 aware `decision_at`、`as_of`、`captured_at`、`capture_mode`、`temporal_status` 與 authority flags，另保存本次 `current_capture_context` 及首次持久化的 `persisted_snapshot_capture_context`／`persisted_event_capture_context`。05:25 Pacific 的正常路徑是台北收盤後 `eod_research`；不得把它標成盤前，也不得用它推定自然成熟。明確指定未到達的日期仍由 capture CLI 以 `decision_date cannot be future-dated` fail closed。舊的 date-only CLI caller 可相容執行，但 `temporal_status=temporal_precision_unproven`，不會隱式補 08:30。source `available_date` 與 source metadata 時間戳保持原值；不把 capture time 當作歷史可得時間，也不回寫／回填歷史事件。`trading_calendar_validated=false`、`maturity_date_inferred=false` 的既有 safety flags 仍不變，不把週末、休市或未成熟資料偽裝成正式交易日證據。snapshot 成功、event capture 失敗時，下次執行會重用 snapshot identity 並再次嘗試 event unique-key capture；若 child 未回讀相同 temporal context／hash，外層 runner fail closed。

Paper Portfolio 每日估值（repository isolated）：

```text
<repo>/output/paper_execution_eod_replay/paper_portfolio/paper_portfolio.sqlite
<repo>/output/paper_execution_eod_replay/scheduled/paper_portfolio_isolated/latest_status.json
```

runner 先以 D 槽 baseline／snapshot 的唯讀來源建立 repository state seed，並在
`state_seed_manifest.json` 綁定來源與初始 target hash；每次 repository append 後以
`state_head_manifest.json` 綁定最新 state hash。排程預設選擇最近一個已到達的台北
08:30 cutoff；明確指定仍未到達的 `--decision-at` 會寫入 `skipped_future_decision`，
且不開啟 state／market DB。市場 DB 永遠唯讀，SQL 與 domain runner 都拒絕
`price_date >= decision_date` 或 `available_date >= decision_date`；同一決策日重跑只
回報 duplicate。來源缺件、seed/head hash 不一致或來源在 backup 期間變動時會 blocked，
不建立無 provenance state。此排程不把 current weight 猜成 0、不產生交易、不套用配置提案。

Working-copy smoke diagnostic script（不構成人工 Gate，也不註冊為 task）：

```cmd
scripts\scheduled\run_evidence_working_copy_smoke.cmd <source-db-path> <working-copy-db-path> [YYYY-MM-DD] [repeat]
```

If the DB paths are missing, the wrapper prints usage and exits. Repeat defaults to 2.

每週 sidecar collection：

```text
<OUTPUT_ROOT>/scheduled/v2_2_weekly_collection/evidence_scheduler.db
<OUTPUT_ROOT>/scheduled/v2_2_weekly_collection/logs/v2_2_weekly_collection_YYYYMMDD_HHMMSS.log
<OUTPUT_ROOT>/scheduled/v2_2_weekly_collection/v2_2_weekly_collection_YYYYMMDD.json
<OUTPUT_ROOT>/scheduled/v2_2_weekly_collection/v2_2_weekly_collection_YYYYMMDD.md
```

sidecar record 刻意與 source DB 分離。Schema v3 只允許 `pending_human_review` 與 `collection_failed`；首次開啟舊 sidecar 時，repository 會在單一 SQLite transaction 內保留所有 `collection_id`、payload、hash、error 與建立時間，並把舊版 `observed_automatic`（尚未取得人工核准）原子映射回 `pending_human_review`。Migration 可重跑且不開啟或修改 source DB。收集成功只代表待人工審核，收集失敗則保存 `collection_failed` 與 diagnostics。

## Evidence Boundary

The daily automation runs only:

- non-UI quick market data updates for the recent weekday window;
- read-only data freshness checks;
- research-only recommendation snapshot generation and recommendation result save;
- evidence pipeline dry-run reports.
- unsigned, fail-closed ML promotion evidence construction.
- independent DPAPI-protected machine authorization.
- fail-closed ML allocation promotion evaluation and append-only sidecar records.
- dedicated confirmed Decision Desk snapshot and Evidence Event append-only capture.
- strict T-1 append-only Paper Portfolio valuation.

### ML allocation automatic catch-up

run_ml_allocation_copilot.cmd 會固定傳入 --auto-catch-up。只有在沒有
明確指定 ML_ALLOCATION_DECISION_AT、排程選到下一個台北曆日，且完整
orchestration 實際證明該候選日的 strict T-1 尚未就緒時，runner 才會
向後重試最多 31 個曆日，選擇最近的已過交易日。判定依據是既有
hash-bound raw publication 與 post-freeze T-1 proof，不新增另一套資料
解讀，也不寫入來源 SQLite、不使用未來資料；資料庫或官方日曆狀態未知時，
不猜測，保留 fail-closed。明確指定日期時不會自動改日期。

latest_status.json 會保存 decision_selection_mode、
requested_decision_at、decision_selection_reason 與每個候選的
decision_selection_attempts，因此自動補跑不需要人工猜測，也不會把
回溯日期偽裝成原本的決策日。

### ML forward 自然日設定產出（已註冊、尚待自然執行）

`run_ml_allocation_forward_daily.cmd` 是第 18 個 daily task 的前瞻 shadow 入口，
目前已由 pinned UTF-16 XML 獨立註冊；它不由 aggregate registration 建立或覆寫。
省略
`ML_FORWARD_CONFIG_PATH` 時，Python wrapper 在真實 Asia/Taipei 08:30
到達後呼叫 `prepare_ml_allocation_forward_config.py`，將當日設定以
`<ML_FORWARD_CONFIG_ROOT>\configs\YYYY-MM-DD.json` create-only 建立，並把
候選選擇收據寫到 `selection_receipts/`、以 atomic pointer 更新
`latest_selection.json`。既有日期設定若 bytes 不同會 fail closed，不能以
較新的候選取代已凍結來源；wrapper 也只讀該日期檔案，不掃描 latest 檔案。

自然執行前可執行 `run_ml_allocation_forward_daily.cmd preflight`；這個模式唯讀
檢查 wrapper、V2 release manifest hash、repo shadow／Paper 路徑、D market DB、
calendar refresh caller 與 offline calendar cache，不等待台北時間、不發網路、不
呼叫 producer、不啟動 child，也不建立 Windows task。直接省略 `preflight` 才會
進入自然日流程；
目前 task 雖已註冊，尚未授權手動啟動或宣稱已有自然日 shadow 累積結果。

設定產出只接受既有 ML PIT archive consumer 完整重驗過的單一 archive。產出器
先保存 manifest bytes hash，再由 consumer 做 source custody、current code、
raw rebuild、available／archived time 與 manifest readback；consumer 最終回傳的
manifest file hash 必須與前讀 hash 完全一致，任何替換都拒絕。freshness window
只允許決策日當日 08:30 前已完成的 archive 或上一個由官方日曆判定的交易日；
週末／休市日寫 `skipped_non_trading_day` 且不建立 config，官方日曆 unknown、
過舊 archive、source hash mismatch 都是 blocked。正式 runtime 預設唯讀使用
`output\paper_execution_eod_replay\calendar_cache\` 的已驗證 TWSE annual
cache 與 temporary-closure cache，`allow_online_probe=false`；缺少、過期或
竄改 cache 時不以 weekday 或行情列猜測交易日。

forward `.cmd` 在等待台北 08:30 前先呼叫
`run_official_calendar_cache_refresh_daily.py`。它以實際 Asia/Taipei 時鐘計算下一個
08:30 cutoff；只有現有 annual cache 的 `expires_at_utc` 不涵蓋該 cutoff 時，才透過
既有 `capture_official_trading_calendar_cache.py --confirm-network` 發出最多一次
bounded capture。capture 的 `captured_at_utc`、`expires_at_utc`、原始 response hash
與新檔 hash 會寫入
`output\v4_ml_forward_scheduler\calendar_cache_refresh\`；檔名使用實際執行時間與
唯一尾碼，舊 cache 永不覆寫或刪除。cache 仍過期、response 不完整、hash／時間驗證
失敗時 wrapper 直接退出，producer 與 child 不會啟動。這個前置步驟不寫 market DB、
Paper ledger 或 formal clock，也不給予 forward credit。

前瞻設定的預設路徑刻意固定在 repository isolated output：market SQLite 仍是
`DATA_ROOT\sqlite\twstock.db`，shadow output 是
`output\v4_ml_daily_derived_shadow_real_v2`，Paper state 是
`output\paper_execution_eod_replay\paper_portfolio\paper_portfolio.sqlite`，
frozen release 是
`output\v4_ml_derived_h5_20260907_real_v2`，其
`release_manifest.json` 必須符合固定 hash
`sha256:c306c1ea53ccef112204a8412a605b575e4d107b4503b2b5be5d6d5ee50910ea`。
每日 config 會保存該 hash，wrapper 在啟動 child 前重新讀回比對；路徑或
manifest bytes 被替換時 fail closed。如需變更，使用
`ML_FORWARD_DATABASE`、`ML_FORWARD_OUTPUT_ROOT`、`ML_FORWARD_PAPER_STATE_DB`、
`BALDR_ML_RELEASE_ROOT`、`BALDR_ML_RELEASE_MANIFEST_FILE_HASH` 與
`ML_FORWARD_ARCHIVE_ROOT` 明確指定，不能以一般
`OUTPUT_ROOT` 的 D 槽 fallback 取代上述 custody。

wrapper 從具時區台北 08:25 喚醒後只等待真實台北 08:30；子程序超過台北
08:35、外層 capacity／read-only status 失敗、或
`daily_orchestration.natural_forward_completion_clock` 沒有在期限內完成，
都保留完整 outer blocked payload，不給 forward credit。archive 與 operational
publication 是互斥來源；既有 05:20 `--auto-catch-up` task 維持盤後補跑，
不會因這個入口而改成 08:30 前瞻 consumer。完整 ML child／frozen release
契約雖已完成首日接線與註冊驗收，task 尚未有自然執行 receipt；在自然日
shadow、maturity、promotion 與 broker gate 全部完成前，仍不得授權
production alpha／broker。

預備中的 forward child 使用
`run_daily_ml_allocation_derived_shadow.py`。由 scheduled caller 傳入的
archive branch 只包含 `--pit-machine-archive-root`、exact
`--pit-machine-archive-manifest` 與其 frozen file hash；child 在 forward mode
依 `decision_at + 5 分鐘` 固定 08:35 deadline，並把完整 daily orchestration
payload 保留在 outer stdout。若未來採用 operational branch，ML owner 必須另行
接通 publication bytes hash 的 child 驗證，不能由 scheduler 僅靠 path 名稱放行。
完整 payload 的 `status`、capacity／read-only 結果優先；完成時間位於
`daily_orchestration.natural_forward_completion_clock`，至少包含
`post_inference_completed_at`、`observation_emitted_at` 與 `within_*` gate
欄位。既有 05:20 `--auto-catch-up` task 不傳上述 forward 參數，仍維持
盤後 catch-up 語意。

週日 sidecar task 只執行 collection CLI；不呼叫 `--save-history` 或 `--confirm-action-items`，也不寫 source DB。成功週期由 Pre-V2/V4 readiness 自動計數與重驗；不足證據只限制 formal evidence credit，不阻擋 Rule／Advice／Paper operational production。

### ML promotion evidence automatic catch-up

05:17 `run_ml_promotion_evidence.cmd` 會以唯讀方式解讀
`scheduled/data_update_quick/latest_status.json` 的 `check_overview_after`，只接受
`daily_data` 與 `technical_indicators` 都已到達的最晚日期。若原始下一個官方決策日的
strict T-1 超過該日期，就依官方日曆向後掃描最多 31 個曆日，改選最近一個已具備
T-1 證據的決策日；若 strict T-1 已完整，則維持預備的下一個決策日。此選擇不使用
未來資料、不寫正式 SQLite，也不更新 compatible pointer。

Evidence runner 在選日前先驗證 upstream `data_update_quick` status 為 `passed` / `passed_with_warnings`，且 `daily_data` / `technical_indicators` latest date 不得超過當前台北日。status 遺失、failed、格式破損或未來日期時，直接寫 blocked，不猜測未來決策日。

Evidence status schema v3 會保存 `requested_decision_at`、`decision_selection_mode`、
`decision_selection_reason`、`decision_selection_attempts` 與
`latest_core_feature_date`、`upstream_data_update_proof_state` 與
`upstream_data_update_proof_reason`。選日調整不是 Gate 通過；formal OOC、PIT、replay、shadow
或 authority 任一缺件仍會回傳 blocked、alpha 0。

Only the dedicated Decision/Evidence capture task writes the durable snapshot and production evidence event tables through the existing idempotent repositories. The forward-outcome task writes only `evidence_outcomes` after its bounded read-only source preflight and explicit confirm boundary. The Paper Portfolio task writes only its isolated append-only paper ledger. The data freshness, recommendation, evidence dry-run, ML co-pilot and weekly collection tasks do not write the production evidence DB. No scheduled task runs the UI, reads UI state, changes the live portfolio, changes `ScoringEngine`, changes recommendation weights, promotes / demotes / retires strategies, connects to a broker, or automates trading.

ML allocation co-pilot task 只消費前兩個獨立 task 產生、且與本次 inference release 相同的 evidence／authorization custody。Evidence builder 不簽章，Authority 不訓練模型，Co-pilot 不自行製造 OOS、PIT、calibration、drift 或 shadow days 證據；非零 alpha 必須通過三層重驗。

The recommendation snapshot is intentionally saved before the evidence dry-run so the dry-run can observe the latest recommendation payloads, including screening matrix / why-not / liquidity gate payloads when available.

Scheduled CMD／PowerShell callers 固定帶 `--bind-scheduled-recommendation`：只讀當日
`scheduled/recommendation_snapshot/latest_status.json`，核對 task、成功、日期、root、已保存／
無 Evidence write flags 與 aware／非未來 clock，再按其精確 `result_id` 從 canonical execution
query 驗證日期、persisted clock 與 payload hash。該 ID 同時交給 importer／coverage；不在
formal 與 shadow 混合 inventory 中猜 latest。缺檔、過期、未來、root 不符或 canonical
readback 失敗時，寫 `recommendation_binding_error`、exit 2，且不啟動 pipeline。Manual CLI
不帶此 flag 時保留原契約。Pipeline child 有 600 秒 timeout，保留 partial stdout、非零退出
與 `pipeline_execution_error`，不把 timeout 當空成功，也不使用 `--confirm`。

Generated evidence reports 是機器 Gate 的可稽核輸入；它們本身不證明 alpha，也不得直接轉成交易指令。

During dry-run, the runner may build a transient Daily Decision Desk snapshot for the same run. Reports mark this as `source_coverage_basis=dry_run_transient_decision_desk_snapshot`; this reconciles diagnostics only and does not persist the snapshot.

The evidence dry-run `latest_status.json` also includes selected pipeline summary fields from the same run, including `pipeline_overall_status`, warning counts, advisory counts, source-quality coverage rows, diagnostics, and source-coverage readiness. `pipeline_warnings_count` is only actual warning occurrences. `pipeline_natural_maturity_warning_counts` separates `insufficient_future_data` from `pipeline_actionable_warning_counts`; `natural_maturity_only=true` means the remaining degradation is expected to resolve only as forward observations mature and is not a manual repair blocker. `manual_action_required=true` is reserved for a failed or stale freshness input, missing pipeline summary, pipeline error / blocking gap, or non-natural warning. The wrapper always records `dry_run=true`, `confirm=false`, `writes_evidence_db=false`, and `production_scheduler_allowed=false`. `pipeline_advisories_count` separately records complete but estimated MoneyDJ provenance; it does not mean source data is missing. Fixed-threshold recommendation snapshots may leave `score_percentile_bp` empty because no comparable ranked universe is persisted; that is not a warning. These fields are copied from the dry-run stdout only; the wrapper does not rerun the pipeline. Decision Desk SQLite section providers use `mode=ro` / `query_only` for scheduled reads.

產業指數更新的完整性比較以請求日前最近一個有效交易日的指數集合為基準；歷史上已停用或改名的指數不應造成每日 false-positive warning。若目前有效集合仍缺少指數，仍須保留 warning，因為服務會保留既有當日資料但不會假造來源數值。Portfolio alert 的 `portfolio_alerts_chip_data_missing:<stock_code>` 代表持倉代號在目前籌碼來源不可用，必須先核對持倉來源與公司主檔，不得由 scheduled wrapper、dry-run 或 Codex automation 自動改碼。

### Paper session-open capture 與 Formal 綁定

`baldr-formal-pit-sidecar-postcutoff-daily` 的既有 18:00 Pacific action 會先執行
`run_formal_pit_sidecar_postcutoff.py`，再執行
`run_paper_event_source_capture_daily.py`；沒有另建平行 Task。capture caller 只讀
固定的 D recommendation root
`D:\Min\Python\Project\FA_Data\output\recommendation\runs` 與 D market SQLite
`D:\Min\Python\Project\FA_Data\sqlite\twstock.db`，並把官方 TWSE MIS response
的 bounded raw bytes 寫到 repository 的
`output\paper_execution_eod_replay\event_captures\`。每個 execution date 與
recommendation 完整 file/content hash 各自形成 immutable bucket，保存 envelope、
`raw_response.bin`、capture metadata 與 manifest；不覆寫已存在 bytes，也不寫 D。

capture 僅接受台北 `09:00 <= captured_at < 13:30`、官方固定 endpoint、同一 frozen
recommendation、同日 execution date 與 parser/row/hash readback。production path 以
`now=None` 讓 producer 在 bounded HTTP read 完成後取 `captured_at`；逾 session、
identity/hash/path/schema/custody 錯誤直接 fail closed。GET／空 response 等 transient
錯誤最多重試 3 次，每次都重驗最初 recommendation file/content hash；完整 durable
capture 重跑不再 GET，失敗 attempts 會留在 status receipt。

`run_paper_execution_daily_isolated.py` 的 EOD writer 依同一 execution date 與 frozen
recommendation identity exact resolve durable capture，將候選與 capture manifest 綁成
`paper_execution_candidate_bound.json`，再產生 repository research-only processed
receipt。Formal consumer 重新讀 receipt、candidate、ledger SQLite、capture envelope
與官方 raw response，逐列比對 stock、reference price、fill／費稅／股數、event/capture
時間與 hash；只有 custody 與 event-time eligibility 都成立才可進 Formal，今日 delayed
EOD 或缺三來源仍維持 candidate/no-credit。

### Paper queue 固定 namespace 與來源 pin

Isolated EOD adapter 只允許 literal source pattern `paper_frozen_*.json`；共用 resolver
與其他 callers 的預設仍為 `*.json`，不接受任意 glob、遞迴路徑或可變 root。namespace
只選新的 queue source；append-only receipts 仍全部執行既有驗證。任何 unresolved
pending 必須以 portfolio、result、來源完整檔案 SHA、aware recorded clock、decision／
execution date 與 session identity 從 scoped 或整個 legacy root 中精確唯一匹配，legacy
fallback 採 bounded regular-file/no-follow read。scoped source 存在時也必須完成同樣驗證；
來源 missing、tampered、identity／clock 不符、零匹配或多重匹配都 blocked，不能讓新的
frozen source 取代舊 pending。新選取的 path／identity／hash／session 及 fallback proof
須在 candidate/status hash 前記錄，並於 writer 產生任何 effect 前再次用 bounded pinned
bytes reader 比對且直接解析同一份 bytes。已驗證 terminal 僅依同 portfolio／session／hash
結案；future terminal 不結案較早 pending，naive clock、同 session 衝突與無法驗證的
歷史 receipt 保持 fail closed。

### BankTaiwan upstream barrier 與輸出界線

專用 05:50 Task 先對固定 05:45 calibration Task 做 native state、同日 LastRun、run id、
root、receipt 與 snapshot source hash 綁定。若同日有效 terminal projection 已存在則不等；
僅當確認本輪 producer 新 run 正在執行時才 pin 新 run 並等待，最多 1,800 秒、每 5 秒
輪詢，30 秒心跳最多 4 KiB。若已發布的 matching current-run terminal projection 通過 native
LastRun/runStart−2 秒／+30 秒容差、completed/mtime、immutable receipt、canonical artifact、
invocation/cohort/hash 雙重讀回，即使 Task state 是 Running 或 Ready 也可採用；只有缺有效
matching terminal proof 且上游已停止、LastRun 改變或 deadline 到達時才 fail closed。native
時鐘容差不是唯一識別證據，也不能排除兩秒內極快重觸發的 race。原 Task 總執行預算
為 7,200 秒，包含前置檢查、等待與 child，並保留 300 秒 terminal flush reserve；child 的實際
timeout 會依剩餘預算裁切，通常不超過 6,900 秒。這是 dependency synchronization，不改 Task
trigger，也不放寬資料／revision／PIT gate。

snapshot source 與 operational latest／attempt JSON 各有 8 MiB cap；immutable pipeline
terminal receipt 限 64 KiB，child run receipt 限 16 MiB。raw CLI stdout artifact 使用獨立
16 MiB cap，以 create-only 保存並完成 hash/readback 後才生成 typed summary。超限在完整
解析前 blocked；不得讀入大型 parent JSON 作驗收，也不能把 stdout cap 當作擴大 source
scope 的授權。Exit actual artifact verifier 使用獨立 32 MiB 上限。Bank snapshot source 與
operational JSON 的既有 8 MiB 上限不變；Paper frozen source 與 Health 各角色仍依各自既有
上限驗證。

### Position Health 與 Formal 當日來源日期

`position-health-daily-refresh.v1` 可把通過 source identity、snapshot date、baseline
`as_of_date`、coverage、來源 clock 與 `available_at` 驗證的舊 Paper holdings 表示為當日
`observation_only`；它不是同日 Paper producer 成功證據。transition reuse 只接受精確 v2
研究內容身分，保留既有 event id 與原 input hash，並將本輪 hash／available-at 留在新
receipt；只有完整 proof 證明 v2 研究內容身分完全相同時才可 reuse。無法驗證一致或內容
實質變更仍 blocked 並使 wrapper 回傳 nonzero；不得降成 warning／degraded，也沒有新增 DB
schema。

Formal expected denominator 的自動發現只在 active config 的
`activation_trading_date == observed_at` 台北當日且 aware clock 通過時啟用，使用 16 MiB
bounded no-follow regular-file reader 與穩定 file identity/hash 驗證。明確的 expected-universe
或 coverage pin（包括 invalid 或明確空 pin）不得被 auto-discovery 取代；
原 Rule／sidecar／history／ledger 路徑各守其既有契約。resolver proof 只列明來源、hash、
日期與 coverage，不重寫舊 archive、不取 symbols 交集，也不升格 Formal。

### Snapshot 官方基本面來源根

Snapshot／personalization CLI 的 `--current-fundamental-source-root` 控制 current PE 與 MOPS 月營收來源，與 `--output-root` 的推薦產物目的地分離。來源優先序為顯式 CLI、`CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT`、獨立 canonical `TWStockConfig` 的 `OUTPUT_ROOT`／`DATA_ROOT/output`。05:10 CMD 轉送來源參數；05:45 pipeline 轉送同一 canonical source root 至 snapshot child。Bank 保持讀取保存 snapshot 與獨立學習 lane，不新增 snapshot producer。自訂 `OUTPUT_ROOT` 若用作 Shadow，須另明示 canonical source root。Snapshot receipt 與 execution lineage 必須能核對實際來源；不可把錯根造成的缺 PE／YoY 判成自然資料不足。

### G6 raw 與 G9 current-observed 的依賴等待

05:45 recommendation-learning wrapper 保留 Shadow lane 的推薦快照與學習輸出，另從
`CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT` 讀取 G6 狀態。該變數預設沿用 raw wrapper 的
`OUTPUT_ROOT`，未設定時採 `DATA_ROOT/output`。pipeline 先釘選並等待台北當日啟動的一個
raw run，再執行 Quick、official refresh、snapshot 與 learning；避免 Quick 與尚未完成的
G6 爭用同一資料鎖。等待上限取 10,500 秒與 pipeline 三小時剩餘期限扣除 Quick、learning
各一個 child timeout 及五分鐘 terminal flush reserve 後的較小值；預設約 55 分鐘。
後續每個 child 仍保留五分鐘收尾；learning 之前的 child 另保留一個 learning timeout。
若剩餘額度不足，該步不啟動並留下 timeout，不借未驗證快照來完成學習。
同一 exact raw run id、cycle terminal path 與 SHA 一直傳至 learning，不在交接時另取 latest。
Quick 的 plan、receipt、status、child output 及鎖也使用同一 canonical source root。
Quick 的資料範圍與可重用收據末日比對 G6 已驗證的 `source_date`；週末決策日不送進
交易日更新範圍，收據 `available_at` 保留原值且仍須通過實際來源驗證。只有確實需要
Quick writer 時，先在既有總期限與保留預算內最多等 30 秒取得再釋放同一 OS reservation，
讓完成中的 G6 正常交還鎖；Quick 啟動後仍自行取得原鎖，新的競爭仍可使它安全停止。
未取得有效 G6 pin 時不啟動或重用 Quick；獨立 official／snapshot 可繼續，但 learning 保持
blocked。不得以 Shadow 的舊 raw status 取代 canonical raw root。

來源日期先套用共同的 04:30 America/Los_Angeles cutoff，再由既有離線官方日曆解析
最新 session。cutoff 後來源可為當日，cutoff 前、週末及已驗官方休市則取該邊界前最近
官方交易日；G9 feature `as_of` 仍維持決策日前一官方 session。pointer 改變、未允許的
parent／child 失敗、terminal pin 不符或等待跨台北決策日都會留下明確 blocker，停止
該次 current-observed child。逾時不算 capture 成功，也不回填捕獲時鐘。

`blocked_insufficient_storage` 僅有 `InsufficientFreeSpace`／`scheduled_raw_pit_bootstrap`
這個明確正式建置 headroom 例外可進入研究 terminal 讀回：formal root、固定 35/40/200 GiB
整數容量帳與唯一 blocker 皆須吻合，available 不得低於 200 GiB。再核實獨立 completed G6
的自身容量與完整來源／研究資格；重用須驗原 completed terminal 的相同證據。其他容量
失敗或 child failed 不接受，外層正式 raw status、275 GiB 門檻及所有正式資格旗標不變。

05:50 BankTaiwan wrapper 最多等待 10,500 秒取得同次 G9 Task projection 與 terminal，
並在五小時總預算內保留既有兩小時 child 與五分鐘 terminal flush。新 task 註冊採
`PT5H`；既有 task 的註冊路徑仍保留現場設定，須另做精確設定更新與讀回。2026-10-04
07:16:35 UTC 已將現有 Bank task 從 `PT2H` 更新為 `PT5H`，只有期限節點改變，
LastRun／LastTaskResult 保持；詳見 [本輪收尾證據](../../docs/06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。
這些期限約束交接時間，不保證超過預算的 G6／G9 仍能完成。

## Codex Morning Summary

The Codex app has two separate read-only heartbeats. `baldr-scheduled-evidence-morning-report` runs daily at 05:30 Pacific local time and reads the Windows Task status plus the same-run update, freshness, recommendation and evidence receipts. `paper` (「晚間學習與 Paper 排程驗收」) runs daily at 06:20 Pacific local time and checks the Paper／ML run identity, immutable receipts, terminal state and bounded warning sections. Both use `America/Los_Angeles`, so DST is handled by the local-time schedule. Their prompts were updated in place and read back; they notify only on meaningful changes and do not launch producer tasks, train models, modify receipts, or perform Paper actions. They are Codex app automations, not Windows Task Scheduler entries.

It must not rerun data update, rerun data freshness, rerun the evidence pipeline, enter confirm write mode, create or modify Windows Task Scheduler tasks, write the production evidence DB, change portfolio / scoring / recommendation weights, apply lifecycle actions, push, or produce trading advice.


2026-10-03後續驗證：見 `docs/06_qa/FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md`。current fundamentals 為weekly成功後的獨立writer；current revision與正式PIT分離，decision date使用Asia/Taipei、market cutoff保留獨立日期；Evidence依child stdout/summary/report與來源品質驗收。個股研究提供明確保存來源／指定股票分析及獨立技術觀察，仍守正式ML來源修訂隔離。

## 2026-10-03 品質判讀與 research lane

Evidence runner 使用 aware UTC 真實 clock。MarketSessionCadence 以既有 hash-bound 官方 cache 驗 latest completed session；04:30 Pacific 為專案 cutoff，不授 publication/PIT 證明。raw-bound corporate-action exclusions 與相對強度具名排除保留；只有既定 advisory 可以通過 capture-ready，未知警告仍阻擋。

Paper adapter 只在 source_lineage/metadata/source_coverage 的 paper_research lane 附加 alerts/risk/status/warnings/blockers/ready，不取代普通 Portfolio/Risk。required_governance_fields 與來源確認使用者的 required_human_fields/user_actions 分開；legacy manual 名稱不能證明 real holding。wrapper summary failed/errors>0 強制 exit2，實際 child exit 另列。engineering_action_required、source_qualification_required/gaps、research_qualification_required、validation_attention_required 與自然 sample 分報；aggregate freshness／正式 PIT/model gates 不放寬。

`--validation-decision-date` 控制實跑仍必須唯一 QA status-path 與 recommendation identity；所有衍生 writer 只在其 controlled_runs。自然 Windows LastTaskResult 不被控制 run 改寫。驗收見 [補驗報告](../../docs/06_qa/OPERATIONAL_QUALITY_AND_RESEARCH_ISOLATION_20261003.md)。
