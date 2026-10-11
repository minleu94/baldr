# UX20 可執行隔離 daily owner 整合（2026-10-06）

基底0faa099026d08fe4c26b0a81c18a382878bc3bc7。完成既有多批producer/capture→固定觀測日接受→日報/owner receipt的實際隔離全鏈，不是僅文件或契約。Stage5／UX20仍partial，正式部署未做；UX21三檔ownership保持，未讀改／整合其lane。

## 唯讀介面盤點與最小接線

只讀scripts/scheduled/current_stock_research_cycle.py（watchlist/holdings＋raw/outcome/fit，是ML lane）、scheduled_clock.py（America/Los_Angeles）、write_scheduled_status.py（一般覆寫latest status），以及scheduled README／config。既有daily data quick為04:20 Pacific、freshness為05:00 Pacific，共同日期cutoff04:30 Pacific；它們不是本UX20來源資格。未呼叫這些owner、Task COM、ML或資料更新，未改使用者三個pipeline ownership檔。

新增app_module/rule_research_daily_owner及scripts/scheduled/run_rule_research_daily_isolated.py，直接重用SQLiteDailyMarketSnapshotSource query-only、produce_parent_rule_samples、load_observation_policy、preview_or_accept_observation/read_observation_days；operational status沿同一BoundedRuleResearchCaptureWriter atomic envelope，只替換metadata decoder/receipt，不另造producer/calendar/正式資格框架。

## 明示配置／日期／來源

runtime schema rule-research-daily-owner-runtime.v1要求mode=isolated_research、date_source=explicit_policy_dates、policy_config、source_db、snapshot_root/capture_root/acceptance_root/status_root（皆絕對路徑）、per_root_quota_bytes、max_attempts、retry_delay_seconds與parent_universe_configs（日期→具名parent JSON絕對路徑）。缺／空欄位、policy缺截止窗口/預期日皆unconfigured；max attempts 1–3、delay整數0–5秒、quota正整數≤64MiB，無任何生產值或環境fallback。

CLI --runtime-config/--target-date缺一即unconfigured；預設只做preflight。--execute-isolated才允許隔離寫入。source DB也限制repo output/qa或Temp，拒絕正式D市場DB；四output roots互不重疊，不包含source/runtime/policy/universe檔。目標日須在policy expected dates且有exact母體配置，同母體全definition/版本／資料日和固定cutoff一致。不呼叫scheduled_today、不選latest。窗口未到not_due；隔日遲到昨天目標missed_window＋漏日報表，無producer或資料補寫。

全鏈先讀current schema/main/WAL source pin；producer/parent原有單一transaction，返回後再核parent的日期、完整母體原bytes pin及source_binding_sha256與owner preflight同一revision；接受前/後及reuse前再核source與runtime/policy。途中變更blocked，保留已發布證據，不混revision授完成。每job來源pin不變，下一個明示job才可記新revision，舊包保留。

## 執行、有限retry及監控

preflight不建立根／lock。execute取得status_root/.owner.lock，合作cancel與native安全返回，不擅自清stale別人lock。每輪重新核容量/clock/config/source；max_attempts有界，退避每100ms查cancel，總delay≤5秒，不等待無限上游。

已接受的exact source/date/policy且roots/config匹配收據唯一時，already_observed且不重跑producer。未完整單一收據供retry沿原fixed as_of；有歧義便blocked，不挑最新版。各attempt保留逐批production_status/manifest與sample_capture_status；capture拒絕不擦掉producer已發布，同時保存parent/acceptance receipts及day_readiness_status。完全缺目標資料日只記未完整，不能借前日填當日。源變更、source缺日、capacity、busy、cancel與未配置在stdout明示；成功及可安全保存的terminal metadata附atomic owner receipt，容量不足不為寫status再突破守衛。

owner status是operational metadata，非PIT/natural/formal/training；所有資格仍false/unknown。status_root保存包與parent/acceptance分開；若status writer拒絕，保留已有producer/capture/acceptance結果並把owner_status_capture_status列rejected_or_unverified，CLI回2。missed/not_due/preflight只回唯讀JSON，不建status目錄。future Task應保留stdout並讀states/receipts，不能用退出0冒稱全日無漏日。

容量沿現有200GiB reserve、parent64MiB/4096 entries與store256KiB/包、8MiB/128包；按batch數×既有producer8MiB新資料上界加親包，另預留child/accept/status envelope。每root配置quota及physical free在首批與retry前檢查，無auto delete。這是保守上界；大母體或接近quota即使實際bytes較少也可能被阻擋，不能降低reserve或截斷母體繞過。partial/busy保留fail closed，fresh root需明示改runtime；正式quota/分段治理仍要部署決策。既有lstat/fstat不冒稱敵對Win32 no-follow或崩潰durability完整證明。

## 實際驗證

17個不同案例passed：16案例15.73s＋缺policy窗口1案例0.53s；最後source/config強化后重跑實際全鏈/revision2案例7.70s，不重複計數。覆蓋query-only小型17 included/2 excluded→兩批snapshot→child/parent receipts→接受→日報→owner receipt、新Python程序CLI exact replay（不准重跑producer）、source DB bytes不變、同批date/cutoff/revision一致；隔日missed/no latest、缺runtime字段/窗口/正式DB拒絕、physical capacity及小quota零寫/修正後retry、sample拒絕保存producer發布紀錄且第二輪成功、缺目標資料日有限次數、同日新revision保舊/途中revision變更blocked、busy保留別人lock與合作cancel、CLI預設只讀。

targeted mypy2、compile3、quant precision/look-ahead、diffcheck通過；UI未改、不重跑Workbench/validator/full regression。只有pytest cache sandbox警告。output/qa/ux20_parent_capture_20261006/daily_owner*.xml與daily_owner_controlled_receipts.json保存raw收據，Temp fixtures保留；probe是受控fixture假容量，正式守衛未改。未正式DB/Task/account/migration/ML訓練/Native/push/永久清理。

## 三個部署決策（推薦提案，尚未配置）

| 決策 | 推薦及repo依據 | 可選替代／界線 |
|---|---|---|
| 日期與時刻 | 沿repo共同04:30 America/Los_Angeles日期cutoff及官方cache；依04:20 quick＋05:00 freshness**同目標日terminal**後觸發，換算當天Taipei固定policy窗口。這是依現有鏈的推薦，非授available-at | 若另採固定Taipei時刻需明示cutoff/start/end與expected dates；本adapter不偷偷選值。目前只接explicit日期，official calendar與upstream terminal adapter仍待工程，DST換算不能省略 |
| 儲存／quota／留存 | 現階段維持repo output/qa隔離；每root明示64MiB上限與31日期segment，沿128包/8MiB store界線不自動刪除。正式候選可依TWStockConfig既有OUTPUT_ROOT（預設D:/Min/Python/Project/FA_Data/output）另劃research roots | 正式落點需另批准source/output allowlist與ACL/segment rollover工程；不與personal/watchlist/notes或正式market SQLite混放。64MiB是既有上限的推薦，不是已啟用quota；永久清理另批准 |
| 執行身份與retry | 依register_paper_portfolio_task.py既有InteractiveToken/LeastPrivilege principal慣例，先維持現有使用者；推薦本新adapter明示max_attempts=2/delay=5秒，capacity/source revision/partial不自行修復 | Task名稱、帳號、啟用與通知路由另決定；不自動升SYSTEM/最高權限。2/5是依本有界adapter提出的推薦值，非repo既有全域defaults，也尚未正式套用 |

部署仍缺工程：官方日曆/04:30 Pacific與exact quick/freshness terminal日期來源接本policy、正式source/output boundary/ACL與分段rollover、Task dry-run registration/執行監控stdout持久化及通知/超時復原；正式Task/account啟用需上述決策。不把這些工程說成等自然樣本。官方custody/可得時間、真正逐日運行與後續outcome成熟／準確度是另一類證據。UX21接受後的Outcome consumer仍後續。

## 原計畫／文件／回滾

9階段done1（0）/partial7（1/2/3/4/5/6/8）/pending1（7）；24UXdone2（01/02）/partial19（03/04/05/06/07/08/09/10/11/12/13/14/15/16/17/18/19/20/24）/pending3（21/22/23），不提前改UX20/UX21為done。

Must同步QA、Manual/Supplements、scheduled README、Snapshot/Architecture、Features/Guide、Index/Navigation及唯一原計畫；產品/6M/版本方向未改。git revert本批commit，保留隔離parent/accept/status/partial，無資料搬移刪除。UTC 07:00 安全暫停是本文件記錄的 2026-10-06 交接安排；本頁不確認它於後續日期仍有效，後續 review 依目前 owner 安排判定。
