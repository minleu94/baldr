# PROJECT_SNAPSHOT（必讀｜目前狀態）

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

## 2026-09-10 V4.1 A 線推薦機率校準切片

已完成 research-only 的 20 trading-day primary／5 trading-day auxiliary walk-forward calibration 垂直切片：固定 decision time、return、benchmark、成本與 universe policy，分離 train／calibration／untouched test，輸出 baseline、raw score、整數 bp calibrated probability、probability bins、Brier／ECE、Wilson 不確定性、成本後與 benchmark 比較，並分開保存 ranking score、upside probability、after-cost profit probability、action suitability、evidence confidence。deterministic sample 可測得 OOS；正式 evidence DB 目前讀到 217 recommendation events、8 未成熟 outcomes，但成熟 observations／fold 仍為 0，不能宣稱有效或失效。price／volume 只對未來新 event 保存 component metadata，未回填歷史；chip／funding、industry、PIT theme 與自然 forward evidence 仍待後續真實時間累積。完整契約、實際 read-only 結果與測試見 [V4.1 推薦機率校準垂直切片](../06_qa/V4_1_RECOMMENDATION_CALIBRATION_VERTICAL_SLICE_2026_09_10.md)。

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
