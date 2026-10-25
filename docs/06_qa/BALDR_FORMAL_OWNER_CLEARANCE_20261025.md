# Prospective Formal Owner 清障與新 clock 候選（2026-10-25）

## 2026-10-25 UTC Owner 授權後的週 Evidence 再核對

實際 Workbench 使用者環境仍指向 `C:\Temp\external-evidence-shadow\approved-weekly-history-projection.json`；週 sidecar 未設專用覆蓋，故走 `F:\Min\Python\Project\FA_Data\output\scheduled\v2_2_weekly_collection\evidence_scheduler.db`。正式 sidecar 的 17 筆 pending rows 仍是舊 D 槽來源路徑與無 coverage payload；此環境下無法逐筆驗證它們，故不把 Codex 的 Owner 委派解讀成對未知內容的批次核准。

隔離 candidate sidecar 的三筆 capture 是同一期間 `2026-10-12..18`、相同來源 DB SHA-256=`74324dbc7a6b3bf0dfd6ed656f6452958f959de97550e59cc0500dfff262f2e1`，並非三個週期。以有界 runner 對正式 DB 唯讀串流核 hash（4,108,730,368 bytes）後與該 source hash 完全一致。最完整 capture 有 5 個交易日、9,813 列、1,980 代號、0 重複、15 列 OHLC 均缺；同日 TWSE `MI_INDEX` custody 的五份 raw response 均 HTTP 200，`raw_response.bin` 的五個實際 SHA-256 均與 receipt 的 `raw_response_sha256` 完全一致，且各例官方 OHLC 為 `--`。這確認缺值源自官方回覆；它不補足全市場 universe 分母、也不使週資料完整。

目前 projection loader 僅把核准期間計入 history；readiness 仍獨立列出 sidecar pending rows，且 projection 沒有 collection ID／source hash 欄位可精準對應 capture。即使新增一筆週期核准，現有正式 sidecar 的 17 個 pending 也不會被消除；按期間粗略隱藏會錯把不同 capture 一併結案。故本次不產生可冒充清障的 projection、不改使用者環境變數、不改正式 sidecar、不授 Formal credit。剩餘項目不是等待 Owner 再選，而是舊列缺審閱材料，以及 readiness 尚無精確審閱—capture 關聯契約。原始驗證收據位於 task workspace `owned-validation/weekly-source-db-hash-20261025/receipt.json`；approval packet 與隔離 capture 仍列於上節。

## 2026-10-25 Formal 與週 Evidence 續查

### Formal input inventory

使用唯讀 `scripts/inspect_formal_input_candidates.py`，明確掃描 `F:\Min\Python\Project\FA_Data\output\formal_prospective`（manifest 上限 512，未截斷）。實際觀察 7 份 manifest，全部分類為 `prospective_only`；預期三種正式 schema（causal non-cash portfolio ledger、Rule Champion snapshot history、PIT sector membership）各為 0。故目前 Strict Formal readiness 仍為 0/3，不能把既有 clock 的 staging／diagnostic artifact 直接接線。

官方 calendar planner 的後繼候選為 `clock:prospective:20261028:planned-v1`，規劃 2026-10-25 至 10-27 準備窗、10-28 activation，calendar-only planner blocker 為空。這是日期候選，沒有建立正式 clock；截至本次查核，TWSE 2026-10 月 2330 `STOCK_DAY` 頁最新列為 10/22，TPEx daily-quote 頁資料日期亦為 10/22。10/23 官方 MI_INDEX 與 TPEx 查詢此前均曾無資料／網路捕獲失敗，與官方 calendar 顯示 10/23 開市的落差仍未解；不能以 10/22 補作 10/23 T-1。來源頁：[TWSE STOCK_DAY](https://www.twse.com.tw/exchangeReport/STOCK_DAY?date=202610&response=html&stockNo=2330)、[TPEx 上櫃股票行情](https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=htm)。

Formal input candidate inventory JSON、執行收據及 clock planner candidate 均保存在 task visualization workspace；本次唯讀掃描未寫 Formal／ML／Paper 路徑、clock、SQLite 或正式資料。下一個合法動作是 10/27 收盤後依同一日期重新捕獲正式來源、確認 T-1，然後重新凍結當期身份並評估是否可在 10/28 activation；若任何來源未到，時鐘必須順延。

### Weekly Evidence approval packet

以 `scripts/build_evidence_weekly_approval_input.py` 分別讀取正式 collection sidecar 與隔離 candidate sidecar。正式 sidecar 的 17 筆 pending record 使用舊 D 槽來源路徑、只含 last trading date／來源 hash，coverage／品質／重複列皆為 unknown，不能據此逐週 review 或核准。隔離候選 packet 有 3 筆完全同一期（2026-10-12..18）capture；每筆 source hash 相同，不能把重複 capture 當成三個週期。

隔離候選的來源品質明細為：5 個交易日、9,813 列、1,980 代號、0 重複；full-universe denominator 未知，且 15 列缺 OHLC。每列都由同日 TWSE custody raw 回覆 `--`，本地投影遺失官方有值行情 0，未知原因 0。因此缺值原因已可解釋，但該週仍為 degraded；不能把它算成完整 OHLC coverage 或直接形成 owner-approved history。Review input packet 只供審閱，不會寫正式 sidecar 或產出 approved projection。

隔離 packet：`weekly-approval-input-enriched-candidate-20261025.json`；正式 sidecar packet：`weekly-approval-input-owner-review-20261025.json`；inventory：`formal-input-candidate-inventory-20261025.json`。這些 workspace 輸出不是正式 Gate credit。當前正式側的原始週記錄、批准 projection 與 readiness status 均未改動。

## 範圍與結論

本次承接 Owner「所有卡關項目直接清障」授權，只處理 Prospective Formal／ML 的 clock 與啟動前置；不更改既有 Owner 策略選擇，不啟動 Formal OOS、ML promotion、broker 或真實交易。

目前沒有待 Owner 再選的策略政策：`manual-rule-only-daily-rank-v1` + `foreground-owner-bound-v1` 已於 2026-08-21 接受，identity hash 為 `sha256:cb09ef93b6442d8714d27ed0a7f92aa98fa4cc088301b5797bbadc65d10da2c8`。環境只讀 preflight 顯示 controlled-store 與 HMAC secret-store 均已設定；三個 Formal manifest 路徑仍各自指向不存在的檔案。Deferred activation 契約允許這三個路徑在 activation 前留空，但那不會把 strict readiness 從 0/3 變成 ready。

## 已完成

- 以現行有界擷取器取得 TWSE 2026 年度及 TPEx 2026-10、2026-11 官方日曆原始回應，保存 exact bytes、來源 metadata 與 SHA-256。TWSE／TPEx 都證明 2026-10-26 休市、2026-10-27 共同交易；官方公告可由 [TWSE 市場開休市日期](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html) 與 [TPEx 2026 開休市公告](https://www.tpex.org.tw/storage/eb_data/11411/11400754581.html)核對。
- planner 以台北時間 `2026-10-25 08:49:04`、已接受的 Owner decision timestamp `2026-08-21T07:32:24+08:00`、完整準備日規則及全部既有 clock IDs，產生候選 `clock:prospective:20261027:planned-v1`。它仍是日期候選，沒有建立正式 clock manifest。
- 目前受控環境 preflight：controlled-store=`configured`、HMAC secret-store=`configured`；Formal portfolio ledger、Rule history、PIT sector 三個目標檔均 `file_missing`。未輸出 secret 值。

## 證據檔與 Hash

候選與 raw bytes 保存在工作區外的唯讀查閱套件：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\formal-clock-candidate-20261027\`。

- calendar bundle hash：`sha256:803d4e6742a8a0b6da0f16e4cc3c7367be33d6de9d467b8a87aa10214625b0f8`
- raw-evidence manifest hash：`sha256:73b4ebaef5636bc786d483b984493e4990f31c6965dac20d17a49f3d4558b519`
- TWSE annual raw response：`sha256:7644c1a8af784c09f54670fd7413f536b13eb76c54d658058e8873d1aee32117`
- TPEx 2026-10 raw response：`sha256:fca5e83a35570f490d3fcfa8789f2401031ae660de619aebe8ff516278921d37`
- TPEx 2026-11 raw response：`sha256:d602859f4e86fe07d9ce2d89d4eff0280f7166c0d9e331fb3c448da15abf004`
- plan hash：`sha256:bcd71ea131617f577fcadbaa50aca4a8320d84705629be96eb6b63a18658606b`
- activation environment preflight file hash：`sha256:bdfa3e943f1968cd2904b32a23260e661fa8dd81c1e0a1249ea62fcc34336861`

## 尚未解除的 Gate

1. 10/27 clock 需要 10/23 作為 T-1；目前 Snapshot 記錄 TWSE／TPEx 官方頁未找到 10/23 可核成交列，市場 DB 也未證明該日完整。這個 clock date 即使日曆合格，也不能在缺少 T-1 證據時啟動。
2. 不能沿用 2026-08-28 過期 clock、舊 calibration identity 或舊 universe hash 來補新 cycle。新 clock 必須綁定當期可重播的 frozen universe、source、model、calibration、evaluation 及正確 T-1 lineage。
3. Strict readiness 的 causal non-cash portfolio ledger、clock-bound Rule history、PIT sector membership 尚未建立。它們需由新 clock 的前瞻 capture 產生；不能用空 manifest 或歷史 current snapshot 代替。
4. Paper 真實 fills／成本及其目前帳戶 snapshot 仍缺獨立來源；Prospective Formal 候選不會解除 Paper Gate。

因此，本次沒有改環境變數、沒有寫正式 Formal／Paper／ML 路徑、沒有發布 deferred activation manifest、沒有啟動 producer／scheduler／training、沒有宣稱任何 Formal／ML Gate 通過。`formal_oos_allowed=false`、alpha=`0`、promotion=`false`、broker=`false` 維持不變。

## 2026-10-25 UTC Formal 臨時休市與 clock 日期更正

本節更正上文「10/23 官方 MI_INDEX 無資料、與開市日曆落差未解」的舊判讀。TWSE 官方 newsList/detail 已取得 2026-10-23 集中市場休市公告，公告發布於 2026-10-22 20:10 +08:00；原始 detail response SHA-256 為 `sha256:0ee4c564cac1659a6255e287e20d58bbaa780436bbd7af7e97615b8ca0668fb9`，create-only verified cache SHA-256 為 `sha256:39562938315520005bb8242f2cbc0d123f0627ab63d3fc40c303e5fe4947a442`。公告已經過 hash-bound loader，並且此前已接入 `OfficialTradingCalendar` 的正式 temporary-closure cache。

本輪再以 bounded runner 呼叫實際 `formal_schedule_day_state`，關閉 online probe，唯讀回讀三日：2026-10-23=`(False, twse_temporary_closure_official)`、10/26=`(False, twse_holiday_schedule_cache_closed)`、10/27=`(True, twse_holiday_schedule_cache_open)`。runner `formal-calendar-correction-readonly-20261025` return code 0、自然排空、handles／lock 關閉、source pins 不變。因此 10/23 的 MI_INDEX 無資料是休市，不是應有交易日缺行情；10/27 候選 activation 的上一交易日應核對 10/22，而不是 10/23。此結果與官方公告及[年度開休市表](https://www.twse.com.tw/holidaySchedule/holidaySchedule?queryYear=115&response=html)一致。

這只修正日期與 T-1 判讀，沒有發布 Formal clock、沒有建立或補造 10/27 的三份 clock-bound inputs，也沒有啟動 producer。前次 Strict Formal inventory 的三項正式 schema 仍 0/3；Paper snapshot／fill source 仍缺，formal OOS、ML promotion、scheduler 與 broker 均關閉。需在接下來的自然準備／交易週期中，以 10/22 行情與當期身份重新做精確 preflight；任何來源／lineage 不足時，clock 必須順延。未改正式行情、Paper、Formal、ML 資料或環境設定。

## 2026-10-25 Formal/Paper source 與自然排程最新讀回

更正「Paper snapshot／fill source 仍缺」的範圍：Formal runtime 的三個受控 manifest 仍缺，但 producer wrapper 預設的隔離 Paper source 實際存在於 `output/paper_execution_eod_replay`。Bounded、read-only/query-only 精確 preflight 判定 snapshot source 有 45 rows、trade-ledger source 有 8 rows，schema 都在；main DB bytes hash 分別為 `sha256:45fb32a3811c4f1e3b56f08fb023c3384f82bae31010abc42f023d4eb29c5bb3` 與 `sha256:cca92fbed09e36a0a59aefc0f08b72e2a092dd3f9bf8d001bde80687726a5da2`。snapshot 日期範圍 2026-07-12..10-20；fill rows 日期為 2026-09-08（6 filled、1 partially filled、1 rejected），全部 `research_only=true`、`broker_order_allowed=false`、`auto_rebalance_allowed=false`。因此「source table 有資料」已證明，但不是已核准或可直接作 Formal input。

同次唯讀檢查見 fill DB 的 `paper_trade_daily_operations` 與 `paper_trade_transitions` 各 0 rows，且 8 筆中 1 筆 `fill_price` 為 NULL（與該列狀態的相容性尚未精確核對）；receipt directory 有 54 個 JSON，但其與這 8 筆 fills 的 exact binding 尚未重驗。故 causal ledger 目前仍未生成或 exact-readback。正式 owner paths 仍指向不存在的舊 D 槽 clock-20260819 manifests，三項 Formal controlled input 仍 0/3；Paper 環境變數未設定不是全部 Paper source 缺失的證明，因 scheduled wrapper 會指定 repository Paper EOD source。

`formal_daily_publications/scheduler/latest_status.json` 於 2026-10-24 21:25 PDT 寫入 `skipped_non_trading_day`，exit 0、blockers 空、formal candidate count 0；這是週六安全 no-op，不是 producer 通過或失敗。`rule_source` 最新目錄為 2026-10-20，`pit_sector_membership_formal` 最新目錄為 2026-10-08，`pit_history_candidate` 有至 10/20 的 candidate archive。10/27 自然交易週期才會驗證能否以當期 10/22 T-1、Rule source、盤前 PIT archive 與 Paper receipt 產生並由 consumer exact-readback；未先把 candidate 直接接到 controlled manifests，也未啟動 OOS、訓練或 promotion。

唯讀 preflight receipt `formal-paper-source-preflight-readonly-20261025` 為 passed、source unchanged；隔離 SQLite 摘要 receipt `paper-ledger-lineage-summary-readonly-20261025` 亦 passed、source unchanged。兩者都只證明 source shape／row aggregates，未證明 causal-ledger consumer 接受。無測試套件或 UI UAT。

## 2026-10-25 T-1 行情來源再查

依既有 `capture_twse_historical_daily.py` 唯讀契約，對 TWSE MI_INDEX 的 2026-10-23 以 2330、0050 為核對標的，先後查 `type=ALL` 與 `type=ALLBUT0999`。兩次皆 HTTP 200，官方回覆 `stat=「很抱歉，沒有符合條件的資料!」`。壓縮原始回應（87／94 bytes）及 SHA-256、查詢參數和受限解讀保存於任務 workspace 的 `formal-t1-official-capture-20261025/official-no-data/`。

TWSE 官方 115 年開休市表未列 2026-10-23 為休市，且官方行情頁截至本次查核仍顯示 2026-10-22；因此這只能判定為「10/23 兩種 MI_INDEX 查詢皆無資料、原因未解」，不能推斷休市或把舊日列補成 10/23。[TWSE 開休市表](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html)、[TWSE 當前 MI_INDEX 頁](https://www.twse.com.tw/exchangeReport/MI_INDEX?date=%25s&response=html&type=ALLBUT0999)。正式 SQLite、CSV、clock 與任何 ML/Formal 路徑均未寫入；T-1 rows verified 仍為 0，10/27 clock 不得啟動。

## 2026-10-25 Formal runtime binding 與續期根因

本次只讀回讀排程 attempt log 後，確認 Formal daily producer 的工作日失敗被週末 `latest_status.json` 的 no-op 覆蓋：10/21 attempt 的 blocker 是 `formal_input_wrapper_runtime_config_binding_path_mismatch`；10/22 與 10/23 分別回報 `runtime_config_expired:2026-09-09:2026-10-22` 及 `runtime_config_expired:2026-09-09:2026-10-23`，exit code 2，Formal writes=false、candidate count=0。10/24 與 10/25 是週末 `skipped_non_trading_day`，不能代表工作日 producer 成功。

續期鏈同樣有明確路徑錯誤：`output/v4_next_formal/runtime_roll_forward_status/latest.json` 記錄 10/24 `blocked`、exit 2，原因為 `rule_baseline_root_missing:D:\Min\Python\Project\FA_Data\output\formal_prospective`。目前 configured data root 與資料庫均在 F 槽，且 `F:\Min\Python\Project\FA_Data\output\formal_prospective`、`F:\Min\Python\Project\FA_Data\sqlite\twstock.db` 可讀。2026-10-21 的 immutable runtime candidate 仍含 D 槽 `DATA_ROOT`、market DB 與 Rule baseline；該候選已過期，不能直接重用。這表示 runtime environment binding 的來源設定及其 process contract 需要重新核對，不能只延長舊 config 的日期。

本次未修改 runtime config、binding、使用者環境、Task Scheduler 或正式來源；沒有跑 producer、roll-forward 或測試。要解除此工程 gate，先以當期官方 calendar、有效 portfolio clock 與正確 F 槽來源建立新的 candidate config，跑既有五角色唯讀 preflight，核對所有五個 wrapper role 的 source/path binding 及安全旗標，再按 `write_formal_runtime_environment_binding.py` 的 append/create-only 流程落地。此 binding 只會解除路徑／日期卡點，不會讓 Strict Formal 的三類輸入、Paper Gate 或 ML Gate 自動通過。

## 2026-10-25 Owner 授權後 runtime binding 修復

依使用者 Owner 授權，從現有 hash-bound 2026-10 官方 calendar bundle、固定累積 Paper clock、F 槽 market DB／Rule baseline 與 repository Paper sources，使用 `build_rolling_runtime_config` 建立 2026-10-27 candidate config。正確設定位於 `formal_daily_runtime_config_v7/2026-10-27.json`，SHA-256=`sha256:d3efa05d5944fa561e4d9f168bc9d540f89a5022c3f73d0d0f5e630eeede0663`。bounded owned runner 收據 `formal-runtime-candidate-rollforward-20261025f` return code 0、source pins unchanged、handles／lock closed；config 明列 candidate-only、read-only sources、market DB/formal paths/scheduler write=false、broker=false、historical backfill=false。

候選 config 通過 `write_formal_runtime_environment_binding.py` dry-run 五角色 preflight；再依 Owner 決策 ID `owner-authorized-formal-runtime-binding-20261025` create-only 建立版本化 binding `formal_runtime_environment_binding_20261025.json`，binding SHA-256=`sha256:1f9c289bb22c77db4ac6d7e2e5d4b90b155bad2707ad7a6e7d42b1082fea03f7`，原 binding 保留。套用後以新 binding 再跑 `qa_formal_runtime_environment_preflight.run_preflight(load_binding=True)`：`all_five_roles_verified=true`、五個 role 均選取 10/27 config、`candidate_only=true`、`formal_oos_allowed=false`、狀態 `waiting_for_activation`、source pins present；無 market DB、controlled path、persistent user environment 或 scheduler 寫入。binding backup 已 create-only 保存，SHA-256=`sha256:5d922b7df8f47e5a717f393e96746fdb3d0dc2e299d4506bb2dda9df9b9e4d32`。

五個既有入口 `run_formal_rule_source_preopen.cmd`、`run_pit_sector_membership_preopen_capture.cmd`、`run_formal_pit_sidecar_postcutoff.cmd`、`run_formal_input_producer_daily.cmd`、`run_paper_execution_daily_isolated.cmd` 現於 process boundary 設定 `FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE` 指向新版本化 binding；未重註冊或修改 Task Scheduler。第一次 candidate builder 因 launcher 注入隔離 `DATA_ROOT` 建出不適用的 v6 candidate，沒有啟用；該 immutable artifact 保留作失敗證據。修正版 v7 明確 pin F 槽來源。

這只修復 runtime path／config activation 綁定。尚未跑自然 Rule／PIT／Formal／Paper tasks；下次有用的開市日窗口是台北 2026-10-27，需核同次 wrapper status、immutable receipt、來源身份與 consumer exact-readback。Strict Formal controlled inputs 仍 0/3；causal Paper ledger exact lineage、當期 Rule history、PIT sector sidecar、Paper 成交／cost 完整性及 ML OOS／成熟 forward evidence 均未因此通過。Task Scheduler 實際下一次觸發與本機 Task Scheduler CIM readback仍不可觀測，需以自然 receipt 驗證，不可僅憑 wrapper 修改宣稱排程已成功。

## 2026-10-25 Paper receipt 搬遷定位修復與正式消費者讀回

先前 54 份 receipt 的淺層身份摘要顯示 8/8 fills 均能以至少兩個相同身份欄位匹配，並各有唯一 fill ID 命中；這只證明身份關聯，不代表 Paper consumer 接受。正式 `_validate_queue_receipt` 深驗收時，唯一涵蓋這 8 筆的 terminal receipt 原先因推薦來源路徑仍記為舊 D 槽而拒收。D 槽路徑不存在；F 槽同 result ID 的 JSON SHA-256=`sha256:9330c91d8934405629d9f4f48d2c1a239741f1d886a71bfc75d4086fa33df165`，與 receipt 宣告來源 hash 相同。既有 `legacy_recommendation_run_locators_20261022.json` 將此筆列為 tier-1，並固定獨立原檔 hash、recommendation DB row hash 與 result ID；bounded read-only 檢查成功由 `locate_legacy_recommendation_run` 驗出 `custody_verified=true`、`research_only=false`。沒有修改 receipt、推薦 JSON、DB、環境變數或遷移清冊。

已修正 `data_module/paper_daily_execution_producer.py`：receipt 指向檔案不存在時，僅透過上述 SHA-pinned locator、精確 result ID／origin path／DB row hash、tier-1 custody 與預期檔案 SHA-256 定位副本；不採用一般 D/F 路徑替換，也不放寬原來源／內容／日期驗證。bounded runner `paper-receipt-relocation-pycompile-20261025b` return code 0，source pins unchanged、Job 清空、handles／lock 關閉。之後以正式 `_paper_execution_receipt_projection` 唯讀重讀，正確指定 receipt 綁定的 `paper_portfolio/paper_portfolio.sqlite`，結果為 `custody_verified_formal_ineligible`、`rejected_receipts=[]`；8/8 fill IDs 均被唯一 terminal receipt 完整涵蓋。

該 receipt 仍明確 `execution_event_time_proven=false`、`execution_source_capture_at=null`、`formal_consumer_compatible=false`，資料型態是盤後日線 EOD replay，不能證明開盤成交事件的當時可得性；因此 `formal_eligible=false`、`formal_ready=false`、不授 Formal credit。全部 8 筆 fill 也都落在 2026-09-08；這不能替代新自然週期的 clock-bound fills／快照與 causal ledger。新增定位修復解除了「舊磁碟路徑讓 receipt 驗收提前失敗」的工程缺陷，Paper／Formal／ML Gate 仍由來源時間證據與完整當期資料決定。輸入唯讀；bounded audit `paper-receipt-consumer-audit-after-correct-path` 通過、source pins unchanged、Job 清空、handles／lock 關閉。沒有執行 pytest、正式 producer、Formal publication、scheduler 或 UI UAT。

## 2026-10-25 Formal scheduler 休市狀態保留最近工作日結果

先前每次休市 no-op 都覆寫 `scheduler/latest_status.json`，即使 append-only `attempts.jsonl` 仍保存 10/21–23 的失敗，使用者從 latest status 只能看到 `skipped_non_trading_day`，不易直接讀到最近工作日 blocker。現於 `scripts/scheduled/run_formal_input_producer_daily.py` 在休市終態中新增 `last_non_skipped_attempt` 摘要：帶出最近非休市 run ID、status、觀測／完成時間、exit code、blockers 與 terminal receipt 路徑／hash；連續休市時沿用既有摘要。每次 no-op 仍明確標示自己的 `skipped_non_trading_day`，沒有改 Formal Gate、exit policy、Task Scheduler 或自然資料流程。

bounded `py_compile` 收據 `formal-status-recovery-pycompile-20261025` return code 0；focused 測試 `tests/test_scheduled_formal_input_producer.py::test_non_trading_day_status_preserves_last_non_skipped_failure` 1 passed。測試模擬「舊版 latest 已被 no-op 覆蓋、沒有摘要欄位」，確認可從 append-only attempts log 與 receipt 還原，之後連續 no-op 仍保留摘要。第一次測試只因 pytest 預設 AppData temp 的 Windows atomic rename 被 sandbox 拒絕；改用授權 visualization basetemp 重跑，同一測試通過。另以 bounded runner 對實際 `latest_status.json`、`attempts.jsonl` 與 terminal receipt 做唯讀 recovery，還原最新非休市 run `f7686dc61a384594bc353804a549ddfe`：10/23 `blocked`、exit 2、blocker=`runtime_config_expired:2026-09-09:2026-10-23`；receipt SHA-256=`sha256:f28ec6a1c2abacc61bc286154e94b75ae91f5d686bb4ad78144af6e392442b4f`。live recovery source unchanged，沒有改寫舊 status／attempt／receipt。runner 自然排空、handles／lock 關閉、source pins unchanged。尚未有下一次自然 scheduler run，故新欄位的正式 latest-status 寫回尚未被觀測。

## 2026-10-25 Formal blocker 日常排程狀態接線

檢查既有讀取鏈後發現，Runtime／Update 的 `ScheduledOperationsStatusService` 原先只掃 `output/scheduled/<job>/latest_status.json`；Formal producer 實際位於另一個 `output/formal_daily_publications/scheduler/latest_status.json`，所以其狀態不會出現在日常核心排程清單。現增加明確 `formal_status_path` 接線，並由正式 Update／Runtime 呼叫端指向該 artifact。Formal producer 納入核心操作計數；休市日保留 raw status `skipped_non_trading_day`，畫面對最近非休市狀態以共享唯讀 reader 核對 latest summary，必要時從 append-only attempts log 還原，並驗證 terminal receipt 的 SHA-256、run ID 與 status 後呈現 blocker。Update 排程詳細、Runtime 清單與原始診斷都可見此資訊；讀取失敗不推定成功，最近狀態為 blocked 時顯示 attention。此呈現不授 Formal／Paper／ML Gate credit，也不觸發排程。

正式 artifact service 唯讀 readback 顯示本次 `skipped_non_trading_day`，最近工作日 `blocked`，exit 2，blocker=`scheduled_formal_input_producer_failed:FormalRuntimeConfigError:runtime_config_expired:2026-09-09:2026-10-23`，run ID=`f7686dc61a384594bc353804a549ddfe`。status 與 attempts log 讀取前後 SHA-256 相同。bounded `py_compile` 通過；聚焦 pytest 覆蓋 scheduled operation service、UpdateService artifact projection、Update 排程 formatter、RuntimeController／Runtime view 及 scheduler no-op regression，結果 54 passed。第一次 pytest 使用長 basetemp 路徑時有 3 個既有 decision-capture fixture 路徑失敗；改用 workspace 內短 basetemp 重跑後全數通過，未修改 fixture。`document_control route --kind implementation` 將本輪分類為 medium risk，角色為 execution、testing_qa、documentation；document_control check 對 Feature Map 的 12 個 feature passed、errors=0。此接線不代表新 Formal candidate binding 已由自然排程驗收；GUI 實際重啟／Owner UAT 尚未執行。
