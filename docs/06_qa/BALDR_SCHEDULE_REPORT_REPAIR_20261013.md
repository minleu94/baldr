# 2026-10-13 晨間／晚間排程工程查核與修正

## 範圍與判讀

使用者授權將 05:30 Evidence morning report 與 06:20 晚間／Paper report 的問題仔細查核、修正工程缺陷、更新文件及 commit。本輪不變更 Task／automation、不解鎖或中止其他 producer、不抓來源、不寫正式市場或證據 DB、不回填歷史、不交易／promotion／push。原失敗與來源缺件保留。角色由同一 root 依序履行 Tech Lead、Data Audit、Execution、Testing / QA、Documentation；沒有委派獨立 Agent。

來源依目前 wrappers／設定：正式 `D:/Min/Python/Project/FA_Data`，G6 `D:/Min/Python/Project/FA_ML_Research`，G9 `D:/Min/Python/Project/FA_Data_Shadow`，Bank `D:/Min/Python/Project/FA_Data_Shadow_BankTaiwan`。模型每日來源與 G6 中央母體、推薦 eligible、formal PIT 分別驗證。

## 可定位的工程變更

| 用途 | 精確原因與修正 | Owner／驗收 |
|---|---|---|
| 推薦／Paper 的當次官方日曆 | refresh terminal `refreshed` 已有新 cache，consumer 卻優先取刷新前 `inspection.selected`。改讀同次刷新終態、按台北決策年選取；刷新缺件／hash錯誤不退回 inspection、舊檔或目錄掃描。 | Calendar／Recommendation：同次刷新檔 path、file SHA、capture≤decision、expiry 均經 public verifier。 |
| Evidence preflight 診斷 | aggregate `blocked` 與真正 task/date/root identity mismatch 共用錯誤。分開 `scheduled_recommendation_status_not_passed:blocked` 與 identity mismatch；仍要求 passed／canonical result／非未來時鐘，沒有降低下游資格。 | Evidence／推薦：blocked 明確拒絕且不啟動 child；通過推薦後才核同 result 的 pipeline report。 |
| Paper NULL open 的合法重試 | 整列缺失可 retry，但 `daily_prices.open:1435 is missing` 沒被分類，legacy failed receipt 因而報不可重試。僅將精確 NULL open token 視為同日缺價重試；nonfinite／負值／混合 clock／identity 不納入。 | Paper／行情：同原 source、日期、hash 讀回；原失敗收據不改。已跨執行日仍拒絕 `pending_execution_session_missed`，不得補跑10/12或改期。 |
| ML Forward 未開始的 maturity 誤診 | child 在 shared lock preflight 即退出、無 daily orchestration／record，wrapper 又要求成功 child 的 cutoff。對此精確 preflight 狀態列 `not_started`，保留 parent `blocked_child_exit`／exit2、不掃 sidecar、不授 credit；真正成功但缺 cutoff 仍 blocked。 | Forward／heavy-chain：原 child failure 保留，只有合法 completed clock／cutoff 可驗自然完成。 |
| G9 H20 3600秒逾時 | 同次原10檔於06:51–07:26保存，07:37有manifest，但終態仍反覆重建相同完整source binding，07:45 child timeout。每日與manifest使用既有 operation-local `PersonalH20ReadSession`；逐檔hash／完整母體仍讀，成功前重驗每個來源群組及manifest終態，不跨operation快取。 | H20／G9：來源或manifest終態改變必須失敗；原3600秒child／14400秒pipeline與frozen模型資格不變。 |
| Sector 來源錯誤可追溯性 | `t187ap03_O` invalid UTF-8 JSON 保持拒絕；診斷新增原bytes SHA、byte count、parse error型別，不猜HTML或改用未知來源。 | Sector／來源：下一次合法盤前response留下原hash，通過完整UTF-8 JSON／schema／cutoff／分母與下游gate才恢復。歷史失敗沒有原raw path／hash，不能由本輪重建。 |
| Bank 的等待終態辨識 | 舊收據 `upstream_stopped` 未保存最後Task observation，可能混入query failure。None明確列query unknown，錯task/path列identity mismatch；可讀非Running才列stopped，保存最後Task觀測。 | Bank／G9：same run、Task last-run、projection與producer lineage完整；未知不冒充上游停止，也不借舊projection。 |

Look-ahead 自查：不把現在價格補進原決策，不改 execution date／planned maturity，不把 post-cutoff capture 改成盤前，不以 source revision 的現值替代歷史可得性。沒有新增金融 float 計算。

## 同次證據與仍需處理的來源

- Evidence 原 status SHA `sha256:b2b38a46ea05b9682355cb23d317647f396a883493d8b7860ca566964de8020f`；pipeline 未啟動。推薦 result `rec_01acfe079b994a31884b86009149e20c`，status SHA `sha256:4dcc411fa5d94c806f8704c170253cd5373ed2bd81fc7e7eba82c47b54ea8da6`，整體仍 blocked。工程修正不回寫今天成功。
- Calendar refresh 新檔 SHA `sha256:a030013a0aca7ddd54f72c539079bd050686a57785556fe5a49ea14d3b143dfe`；舊 inspection cache SHA `sha256:37083f2b35c79d6d0e11ccd7ba2f5583be4b8c09babdb96e9518e4f0107a6157` 已過期。使用原byte hash及public clock verifier，不改cache。
- Paper 10/12 receipt SHA `sha256:c69d061bc2db1696fbeb6f254907c8b39b48b878edb892c75d99bf19017183ed`；決策10/8、執行10/12，1435官方open缺失。10/13舊收據拒絕 SHA `sha256:890fe74dd3eaad53cf0479fad851ffe2d0fb15ac976d784b47244013d4cdd062`，不得用10/13價格。修正後舊session仍過期，需Paper owner處理原未執行來源，不能當本輪完全恢復。
- Official wrapper immutable `runs/20261013T115002292732Z-84fcc6084299.json` SHA `sha256:90c3bcb044d95d1417c3c6354c0a6de5675862b58e882d0c0df8b01a6fc200c0`：14/15 current captures，TPEx HTTP520；valuation child已captured但日期分別TWSE10/12、TPEx10/13，歷史revision ambiguity仍保留。來源owner須核同次raw／publication日，不能以另一child成功結案。
- Forward Outcomes run `20261013T124003318616Z` SHA `sha256:acffd28ea68ebf2601ec1c0ad7fd769cd40dce20fc884a4cb354cf100ac7363f`：1538 H5缺9/17 close、H10缺9/24 close（official planned session）；legacy expected dates10/2、10/12另列，不能借後日close或以row offset改成熟日。43 events、172 outcomes更新，84自然pending，2來源缺價，非整鏈成功。行情／Forward owner按原event `evt_bbd3c5eea73341bcb4a83d0fa28991f4`核價。
- Decision Capture run `20261013T122502426287Z-9eadf30576bd` 已passed，06:43:06 PDT完成；SHA `sha256:ba83d27283e03f29f19ceb7e689e78360d7ff7582f895cc707bfd0ac84ba721a`。此為producer狀態讀回，不取代全部consumer／正式資格。
- G6 同次 `raw-pit-20261013T120503489023Z-5176-fd383b60ca814c66b5441135ecc3baf9` 中央terminal completed，06:41:23 PDT；SHA `sha256:d38ae61f7dd17c411647815b13f38d508b7b5f7f2f0539e0c64d86a6ef2782dc`。formal raw仍blocked_source_revision（2014-01-02起）；research completed不升formal PIT。
- G9 run `20261013-20261013T124502274974Z-d4cab532d26a` 已failed，07:45:04 PDT，child3600秒timeout；status SHA `sha256:4a1eb0b15355e35be4859f48e8d137d979c14e711a8b2d26802f58fa4f1b4c3f`。新試跑與正式terminal分開。
- Bank run `2026-10-13-attempt-001-959250f9deba` failed_dependency，06:44:08 PDT，SHA `sha256:326b34fc3f9f143f0d8d135f3b41ed7076206cc4367f6d74199e82051525521f`；沒有相容current projection。舊最後Task query未留證，原因unknown保持，不能倒推G9當時已停止。
- ML Forward同次 child receipt SHA `sha256:af38387cd9342e74d815419dfcf0d1c3e7a695774500d195c35575ed66d55c1d` blocked_shared_heavy_chain_lock；repository scheduler pointer仍舊休市，不能借它結案。
- Sector status SHA `sha256:f3b39f7343e8bd68f0dde113a26958f3fac9496b87c37f84587c8b8155b4fcc5`；sidecar缺10/13 verified denominator，formal input仍candidate_only。修正診斷不給分母、ledger或三consumer正式readback資格。
- Quick法人9/29有49衝突／缺00636K、00643K、00657K、00668K；9/30有76衝突／缺3碼；credit實際10/12。週monthly child仍2 failed，quarterly待審；promotion corporate-action custody hash stale。這些來源／人工資格未變，不自動覆寫或核准。
- Direct今天10:00已開始，11:56讀到fresh heartbeat／verified maintenance lock，fit_completion_verified=false；昨日無效owner／lock收據保留。不解鎖、不借無同次binding的child當完成。

## QA 與交付邊界

本機收據位於 `output/qa/schedule_report_repair_20261013/`，不提交raw output。驗證使用owned Windows Job：8GiB／12程序、至少8GiB可用RAM、suspended assign-before-resume、workspace mutex；每組串行，terminal須自然Job0／handles closed／mutex released。

- `schedule_1791917192130081500`：156 passed／1 skipped，12.422秒。
- `forward_1791917259811929000`：原3 failed／79 passed／1 skipped保留。定位為過期fixture：public evidence新operation在mock clock之外、ledger精確schema漏掉既有daily operations表；保持所有精確斷言並修正fixture。
- `forward_1791917316550246900`：82 passed／1 skipped，14.828秒；成功child缺cutoff仍拒絕。
- `h20_1791917552693494700`：48 passed，6.812秒；包含來源終態變動拒絕與HTML／invalid encoding／duplicate JSON key原hash診斷。

最終回歸 `schedule_1791918165264418600`：156 passed／1 skipped（含同次多年份刷新、tamper及無終態拒絕）；Bank `bank_1791918101920159000`：75 passed／4 skipped；完整H20自然迴路 `loop_1791918198779900500`：176 passed／1 skipped。各組有重疊測試，不將各組數量當成唯一案例總數。

真來源全迴路 `central_1791917625629417800`：exit0、435.375秒（約7分15秒）、自然Job0／handles closed，沒有強制清理或放寬原3600秒期限。原件 `smoke_1791918060735060100.json` SHA `sha256:c40e0e2cfba4c036ad213cd191ea01289976dfbb8d8cbcba8b5329eb5d89f769`；PDT11:53:47–12:01:00，台北決策日10/14、cycle source日10/13、feature日10/13。10／10原frozen predictions、完整manifest及自然batch核驗完成；manifest SHA `sha256:09f4cb24120bc5d2d7661be2fb0f82bd5c857fc7ed1ac414d9fcd18d5e886a3b`，新隔離私人根 `C:/Users/archi/AppData/Local/Temp/h20trial_gbaqxsxn`。結果 `completed_with_pending`、entry `same_date_entry_session_missing`、batch pending10／matured0；原activation／fit／G6 terminal raw pins前後不變。沒有倒填10/13預測或fake成熟樣本。

真consumer唯讀 `readback_1791918084294664400` exit0：新版日曆實際選到刷新後 `twse_holiday_schedule_2026_20261013T002502332864Z_ada7cdea115c.json`，file SHA及expiry完整通過；refresh receipt SHA `sha256:9b612ab728e8530f8b604f8fdd0a6702fb9c2935b4253862b64ac2bf4594ea02`。Evidence明確拒絕 `scheduled_recommendation_status_not_passed:blocked`，原Paper10/12 receipt通過原hash／source／日期驗證，僅in-memory分類；正式source檔hash不變，未啟producer或pipeline。

mypy初次 `repair_types_1791918121811833500` 因namespace重複定位中止，保留原失敗；以 `--explicit-package-bases` 明確同一package身份後 `repair_types_1791918141422027200` 8來源通過，未降低type規則。16 Python檔語法 `repair_compile_1791918244144425300`、quant guard `guard_1791918247608877400` 均exit0／自然Job0。沒有UI修改，UI重型驗收不適用。本輪沒有產品Gate或正式資料資格接受變更；他task的Snapshot／補完進度dirty內容保留、不納入commit。隔離模型／fixture成功不等於今天正式排程恢復；歷史缺價與資格仍依前述owner／條件處理。

## 主機 Scheduler snapshot（PDT）

host唯讀21-task inventory `inventory_1791917218772825400`，captured `2026-10-13T18:46:59Z`（11:46:59 PDT），21可查、全部啟用、action／schedule／cwd匹配、0確認不存在。晨報sandbox unknown是查詢環境失敗；本輪未改權限。下表Last／Result／Next只表示Scheduler，producer按上文收據判讀；Running不是成功。

| Task（baldr-前綴） | Last PDT | Result | Next PDT |
|---|---|---|---|
| data-update-quick-daily | 10/13/2026 04:20:01 | 0x00000000 (ready) | 10/14/2026 04:20:00 |
| official-market-events-daily | 10/13/2026 04:50:01 | 0x00000001 (ready) | 10/14/2026 04:50:00 |
| data-freshness-check-daily | 10/13/2026 05:00:01 | 0x00000000 (ready) | 10/14/2026 05:00:00 |
| ml-raw-pit-refresh-daily | 10/13/2026 05:05:01 | 0x00000000 (ready) | 10/14/2026 05:05:00 |
| recommendation-snapshot-daily | 10/13/2026 05:10:01 | 0x00000002 (ready) | 10/14/2026 05:10:00 |
| evidence-pipeline-dry-run-daily | 10/13/2026 05:15:01 | 0x00000002 (ready) | 10/14/2026 05:15:00 |
| ml-promotion-evidence-daily | 10/13/2026 05:17:01 | 0x00000000 (ready) | 10/14/2026 05:17:00 |
| ml-promotion-authority-daily | 10/13/2026 05:18:01 | 0x00000000 (ready) | 10/14/2026 05:18:00 |
| ml-allocation-copilot-daily | 10/13/2026 05:20:01 | 0x00000000 (ready) | 10/14/2026 05:20:00 |
| decision-evidence-capture-daily | 10/13/2026 05:25:01 | 0x00000000 (ready) | 10/14/2026 05:25:00 |
| ml-direct-chain-maintainer | 10/13/2026 10:00:01 | 0x00041301 (running) | 10/14/2026 10:00:00 |
| forward-outcomes-daily | 10/13/2026 05:40:01 | 0x00000002 (ready) | 10/14/2026 05:40:00 |
| recommendation-calibration-learning-daily | 10/13/2026 05:45:01 | 0x00000001 (ready) | 10/14/2026 05:45:00 |
| recommendation-calibration-learning-banktaiwan-shadow-daily | 10/13/2026 05:50:01 | 0x00000002 (ready) | 10/14/2026 05:50:00 |
| paper-execution-eod-replay-daily | 10/13/2026 06:00:01 | 0x00000002 (ready) | 10/14/2026 06:00:00 |
| pit-sector-membership-preopen-capture-daily | 10/12/2026 16:00:01 | 0x00000002 (ready) | 10/13/2026 16:00:00 |
| paper-portfolio-daily | 10/12/2026 17:25:01 | 0x00000000 (ready) | 10/13/2026 17:25:00 |
| ml-allocation-forward-daily | 10/12/2026 17:25:01 | 0x00000002 (ready) | 10/13/2026 17:25:00 |
| formal-pit-sidecar-postcutoff-daily | 10/12/2026 18:00:01 | 0x00000002 (ready) | 10/13/2026 18:00:00 |
| formal-input-producer-daily | 10/12/2026 21:25:01 | 0x00000002 (ready) | 10/13/2026 21:25:00 |
| v2-2-weekly-collection | 10/11/2026 18:00:00 | 0x00000001 (ready) | 10/18/2026 18:00:00 |

## 人類授權正式重跑與再分析（台北 2026-10-14 03:09–03:39）

本節為修正後的人類授權操作，與晨間／晚間唯讀 automation 分開。America/Los_Angeles 05:30／06:20、target thread、啟用及通知設定未修改。使用自然時鐘，沒有改期、補造價格、回填歷史、promotion、交易或變更 Task。正式 writer 僅使用原 producer 與原證據範圍。

**結論：官方事件與日曆、Sector 原始解析已恢復；自然證據累積尚未恢復。** 不是所有問題都能靠重跑解除。當前 Direct 正在持有共用 heavy-chain reservation，G6 中央 cycle、G9、Forward 與 Decision 因此沒有新的合格完成證據。不得以 G6 CLI exit0、既有10筆隔離試跑或旧 child 宣稱 live lane 成功。

| Producer | 真實重跑結果、原因 | Owner／驗收条件 |
|---|---|---|
| Official market events | exit0，`20261013T191144298170Z-8ae61900fa50` 三個 child succeeded；舊 HTTP520 partial 已恢復 | Official：同次 wrapper／三個 child 保持一致 |
| Sector | 10/14 archive `459a2842d77310ba-9f70d015fefe8c95` 已保存，原 invalid UTF-8 JSON 恢復；分母仍拒絕 `government license document fingerprint is not the registered version` | Source／PIT：核實原始授權文件版本與 hash，再提供同日 verified denominator；不得直接改 hash 放行 |
| Recommendation | `rec_594a6349acd6416795f62f269f9fba13` 已保存；calendar 已選同次 verified refresh。10/14 decision 與 item 的10/13 eligible universe 不符，`paper_frozen_source_eligible_date_mismatch` | Recommendation／Paper：證明當次來源、universe 與 decision 的契約；不得任意重標 universe 日期或倒填決策日 |
| Evidence pipeline | exit2，`scheduled_recommendation_status_not_passed:blocked`，pipeline 未啟動 | Evidence：上游同次 passed canonical result 通過後才驗 child |
| G6 | 新 raw `raw-pit-20261013T192528568989Z-16856-2ba239dae64e4c8f8ca8a41eafba5c7b`，B `completed_research_only`；cycle `eb789eabf5970938457335720b86ef41` waiting_source，parent skipped_locked／direct_chain_maintenance_is_running | ML／Direct：合法 owner 自然釋放鎖後，以新當次 raw 完成完整中央 cycle、registry 與 terminal；未解鎖或停止其他作業 |
| G9 | 修正依賴順序後 run `20261014-20261013T192746043795Z-4a944d93a612` exit1：`pinned_raw_run_terminal_status_not_eligible`、technical_source_refresh_blocked；1516 缺股 | Learning：同日開始的 eligible G6 terminal／hash，加完整 cohort 與四小時內 terminal，不借舊 run |
| Bank | exit2，`2026-10-14-attempt-001-05bf62deafcd` failed_dependency：terminal_run_start_too_late，child not_started | Bank：恢復其實際 Task 時窗下 G9 proof；手動 run 不授予排程 proof |
| Forward outcomes | run `20261013T193746199383Z`，exit2、heavy_chain_reservation_timeout；writer 未開啟 | Evidence／Direct：取得原共用鎖後在截止前完成，同次 outcome readback；尚未成熟保持 null |
| Decision capture | run `20261013T193759039886Z-c2c4344a6b82`，exit1、blocked_reservation_timeout；snapshot／evidence child not_run | Evidence／Direct：原鎖與自然 clock guard 通過後才允許兩個原 writer |
| Paper EOD | exit2，10/14 source CSV 尚未發布且 quick／freshness 非同日；未到當日 EOD，不能據此稱今日排程已失敗 | Paper／行情：待合法当日行情及同日 gate；1435／10/12 NULL open 的舊失敗保留，跨日不得補交易 |
| Sidecar／Paper source capture | exit2；sidecar waiting_for_taipei_0830_cutoff，source capture waiting_for_paper_session_window | PIT／Paper：待08:30 cutoff／09:00–13:30 source window，再驗同日分母，不提前製造完成 |
| Formal input | exit2，缺 verified current denominator，其他 source gates 尚未完整 | Formal：所有原 gate 及 source readback 通過才可授 formal qualification |
| ML Forward | 原 wrapper **preflight** exit2：known_source_revision_quarantine；child_started=false、wait_started=false | ML source：恢復正式 revision／release qualification，再在08:30合法時窗執行；本次沒有執行 child 或借旧 child |

Forward 已知缺價仍分別為1538的 H5（2026-09-17 close）、H10（2026-09-24 close）；不能用其他交易日替代。自然成熟、1516缺股、來源 revision quarantine、授權版本需審核與實際工程錯誤分開。週採集 partial／人工審查與 promotion qualification 未改，也未擴張為未授權重跑。

### 有界手動 writer 與資料保護

新增 Forward、Decision CLI `--reservation-wait-seconds`（整數1..10500），服務同樣驗證。排程預設仍10500秒，CMD／Task未改。本次各用5秒；逾時留下 producer blocked terminal，沒有跳過共用鎖、同日截止、clock／cohort／DB confirm gate。入口為 `scripts/scheduled/run_scheduled_forward_outcomes.py`（其餘參數照原 Forward CMD，包含confirm及production confirm），以及 `scripts/scheduled/run_scheduled_decision_evidence_capture.py`（原data-root/output-root）。依原receipt重試，不可為了取得passed改日期或移除鎖。

前後皆以 readonly SQLite／query_only 查原120日、2500上限、完整身份的選定範圍：43 events、172 outcomes，內容逐列完全相同，沒有新增自然證據。1435／1538指定8筆原價列也完全相同。這是指定範圍比較，不外推為全DB零變更。

- before `output/qa/scheduled_rerun_20261013/before/evidence_tables.json` SHA `dbe9aafc7340070f75890e1852d0668249f12aa26272df7c4b9659bb1793d716`。
- after `output/qa/scheduled_rerun_20261013/after_evidence_tables.json` SHA `3d6de5017cd496a2781ce7d8b9d29ae3cc9db7b6f2d85b0f2ff6a27cc11dbb9c`；檔案包含不同capture時間，故檔案hash不同，tables相同。
- G6 B terminal SHA `b7336ddb9af800f1183901ddc65d37be1c5ec425ac7b0a94e77b4cd14613d5a6`；cycle terminal SHA `84d0265a1b0b5b199b915110111bba474c0d67da05f11c392aac95c25ab99579`。
- Forward immutable run SHA `7cbd2669c07adead36fd20b74fc79ba3f08afc25dfba1642dcbe4e8050843d9e`；Decision latest SHA `e1d6b6013a9457077917b005e7bf3cb05a76049a85e6ffe63cf2d627797c888a`（immutable receipt另沿該run/receipt.json）。

第一次 G9 先於新日 G6 啟動是操作順序錯誤；它僅等待，尚無 learning／writer。依 exact PID57032／建立時間2026-10-13T19:18:13.609729Z／父系與來源核實後取消自有 waiting tree，保留 `g9_waiting_before_cancel.json`、`g9_operator_cancel.json`。**取消不是passed或自然terminal**。後續才先G6、再G9，以上表列後次真實terminal。所有 owned Job8GiB／12程序、自然或已註記取消排空後，remaining0、handlesclosed、mutexreleased；沒有停止Direct。

### 修改驗證與 Scheduler 讀回

Forward／Decision／共用鎖測試 **83 passed**，包含短等待及10500預設傳入，逾時無child／DB write；三個修改來源py_compile、mypy通過。QA收據與原始log位於 `output/qa/scheduled_rerun_20261013/`（本機產出不入Git），本節為可提交人類報告。前次27203e00的其他修正驗證見上文。

Scheduler 於 UTC19:39:20／PDT12:39:20／台北03:39:20 唯讀重查：21項可查且action/cwd/schedule匹配，人工CMD重跑不改Task的Last／Result。仍需原排程自然事件驗收；不能把手動重跑當Task成功。
| Task | Last（PDT） | Result | Next（PDT） |
|---|---|---|---|
| baldr-data-update-quick-daily | 10/13/2026 04:20:01 | 0x00000000 | 10/14/2026 04:20:00 |
| baldr-official-market-events-daily | 10/13/2026 04:50:01 | 0x00000001 | 10/14/2026 04:50:00 |
| baldr-data-freshness-check-daily | 10/13/2026 05:00:01 | 0x00000000 | 10/14/2026 05:00:00 |
| baldr-ml-raw-pit-refresh-daily | 10/13/2026 05:05:01 | 0x00000000 | 10/14/2026 05:05:00 |
| baldr-recommendation-snapshot-daily | 10/13/2026 05:10:01 | 0x00000002 | 10/14/2026 05:10:00 |
| baldr-evidence-pipeline-dry-run-daily | 10/13/2026 05:15:01 | 0x00000002 | 10/14/2026 05:15:00 |
| baldr-ml-promotion-evidence-daily | 10/13/2026 05:17:01 | 0x00000000 | 10/14/2026 05:17:00 |
| baldr-ml-promotion-authority-daily | 10/13/2026 05:18:01 | 0x00000000 | 10/14/2026 05:18:00 |
| baldr-ml-allocation-copilot-daily | 10/13/2026 05:20:01 | 0x00000000 | 10/14/2026 05:20:00 |
| baldr-decision-evidence-capture-daily | 10/13/2026 05:25:01 | 0x00000000 | 10/14/2026 05:25:00 |
| baldr-ml-direct-chain-maintainer | 10/13/2026 10:00:01 | 0x00041301 | 10/14/2026 10:00:00 |
| baldr-forward-outcomes-daily | 10/13/2026 05:40:01 | 0x00000002 | 10/14/2026 05:40:00 |
| baldr-recommendation-calibration-learning-daily | 10/13/2026 05:45:01 | 0x00000001 | 10/14/2026 05:45:00 |
| baldr-recommendation-calibration-learning-banktaiwan-shadow-daily | 10/13/2026 05:50:01 | 0x00000002 | 10/14/2026 05:50:00 |
| baldr-paper-execution-eod-replay-daily | 10/13/2026 06:00:01 | 0x00000002 | 10/14/2026 06:00:00 |
| baldr-pit-sector-membership-preopen-capture-daily | 10/12/2026 16:00:01 | 0x00000002 | 10/13/2026 16:00:00 |
| baldr-paper-portfolio-daily | 10/12/2026 17:25:01 | 0x00000000 | 10/13/2026 17:25:00 |
| baldr-ml-allocation-forward-daily | 10/12/2026 17:25:01 | 0x00000002 | 10/13/2026 17:25:00 |
| baldr-formal-pit-sidecar-postcutoff-daily | 10/12/2026 18:00:01 | 0x00000002 | 10/13/2026 18:00:00 |
| baldr-formal-input-producer-daily | 10/12/2026 21:25:01 | 0x00000002 | 10/13/2026 21:25:00 |
| baldr-v2-2-weekly-collection | 10/11/2026 18:00:00 | 0x00000001 | 10/18/2026 18:00:00 |

## Direct 本輪自然失敗後停用（2026-10-14 01:07 PDT／16:07 台北）

人類明確授權「讓這次跑完，暫停昂貴重跑，有需要且資格確認後才執行」。本次不修正／降低teacher gate，不啟動任何新的producer或訓練，不中斷本輪，不清理資料，也不重新觸發先前blocked證據writer。

同次started_at `2026-10-13T17:00:02.142672Z`，numeric run `direct-ooc-a1e00e51c5144283b7dbe72f`。2014–2026年度建置及fold indexes完成，產出manifest logical hash `sha256:e3b85ac8f71f89cce699e28d0f60a48c19e82299d577a249cb6cdc642b5fc8d4`、file SHA `65bb7e99b27dd79fccaec318d4314f930938278c8d20b1885a050d15de022ef1`。實檔在 `D:/Min/Python/Project/FA_Data/output/release_v4/portfolio_ml_direct_numeric_production_v4_v2/runs/direct-ooc-a1e00e51c5144283b7dbe72f/manifest.json`。

OOC training invocation回傳2：`allocation teacher eligibility gate blocked: blocked_missing_formal_teacher_inputs`；原因仍為正式Rule champion history、PIT sector membership、正式Portfolio ledger缺件。未獲成功fit terminal，不得說本輪重訓成功。release回傳2，`ooc_continuation_not_complete`。同次chain `blocked`；maintainer於UTC07:57:48記continuation_exited=2，07:59:48 restart_cap_reached=1；wrapper `failed`／returncode2，finished_at `2026-10-14T08:00:14.155872Z`（PDT01:00:14），全鏈約15小時。

Owner40248、Direct launcher2728／worker34840、OOC launcher50484／worker28876、release launcher29844／worker7092均已退出；先前建立時間與父系已驗，並核同次chain與wrapper terminal。既有 `D:/Min/Python/Project/FA_Data/output/release_v4/.ml_heavy_chain.lock` 可用Read／FileShare.None開啟且立即關閉，證明查核當下無持有者；未寫入或刪除此鎖。這證明本輪退出及鎖釋放，不宣稱未重驗的自然證據已恢復。

僅設定Windows Task `\baldr-ml-direct-chain-maintainer.Enabled=false`。前後XML原件保存 `output/qa/direct_pause_20261014/direct_before.xml`、`direct_after.xml`；原XML省略Enabled預設true，後XML明示false，移除該節點後其餘XML完全相同，action／args／cwd／daily10:00 trigger及其他settings保留。初次XML比較器未處理省略的預設節點而失敗，並非Task停用失敗；修正比較後通過，沒有重複變更。Task讀回State1 disabled、LastResult2；其他20個baldr Task仍enabled。只修改這一項Task；晨間05:30／晚間06:20automation、其thread與通知設定保留。

操作收據 `output/qa/direct_pause_20261014/pause_receipt.json` SHA `336dba9f3ce9539fa0c31aefafd26011bfc1439c6fa80f5fc7cbd75b6ee27865`，原始產出不提交Git。未修改Python，無需新pytest／mypy／compile；本次QA為同次terminal、七個PID、鎖釋放及精確Task前後設定核對。最新AGENTS context以scheduler_automation／Level1有限定位；首次runtime領域為Unknown，改用工具列出的有效領域成功，有限索引不外推為完整產品驗收。

今後Direct只在另行人類授權、上次阻塞解除、正式來源完整與自然證據資格核實後手動執行。原「前次失敗→每日checkpoint recovery→新來源檔案hash產生新numeric run→再次昂貴建置」工程行為未在本次改程式；以停用未來排程防止自動重複。現行自然成熟、來源revision、缺價與證據writer仍按各自同次收據判讀。主操作手冊正由其他任務修改，本次不混入其dirty內容，停用流程同步於排程運維指南與唯讀audit Runbook。