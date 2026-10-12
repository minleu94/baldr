# baldr 全排程唯讀驗收

本文件是兩個既有 operational heartbeat 的共同查核規則。Windows Task 負責執行 producer；Codex 晨報 05:30、晚間／Paper 驗收 06:20 是 America/Los_Angeles 時區的報告工作。報告時間不是 producer trigger 或完成期限。實際設定以當輪 Windows readback 為準。

## 1. 有限唯讀查核與查詢環境

依 AGENTS.md 完成必讀。使用 `scripts/inspect_scheduled_task_registration.py` 的預設 stdout 模式，一次查核其中 EXPECTED_TASKS 的全部 21 個 baldr task，包括完整 path、State、Enabled、LastRunTime、LastTaskResult、NextRunTime、missed runs、action、arguments、working directory、trigger、timeout、IgnoreNew 與電源條件。此工具不修改 Task，也不觸發 producer。

普通 sandbox 的 CIM access denied、schtasks network address／0x80070003、COM unknown 只表示查詢環境失敗。在當輪工具提供且核准精確 host read-only 查詢時，可用該環境重做同一唯讀查詢；不改 ACL、principal、登入、權限或系統服務。核准被拒或仍無法讀取時標 unknown，保存錯誤類別，不能說 task 缺失。`confirmed_missing=0` 也不能證明 task 存在。Scheduler Operational 查詢另列 enabled／disabled／unknown；heartbeat 不啟用日誌。

檢查器接受四個已部署固定 `pythonw.exe → run_scheduled_cmd_hidden.py --task <exact task> → canonical CMD`，必須核 interpreter、argv、cwd 與固定 mapping。Direct maintainer 目前為 10:00 Pacific；05:30 是舊設定，不用舊期待宣稱 trigger drift。其餘 17 個既有 canonical CMD 同樣核對，不自行套用註冊器。

## 2. 最新產出與來源根

個人 H20（2026-10-12 修正）另讀 G9 `personal_h20_natural_lane`：其母體必須等於同次 G6 terminal 的完整 `current_symbols`，不能借一般推薦名單。沿 lane 的 `output_root` 讀 `recommendation_learning` captures／outcomes，沿 daily receipt 讀 activation 私人根的 immutable manifest／predictions，核 exact run／hash。`completed_with_pending` 只代表模型完成而 entry／自然結果仍待條件；漏日不能當自然成熟。當輪唯讀 audit 不啟動此 producer。工程試跑與期限收據見 [自然迴路驗證](../06_qa/BALDR_NATURAL_LOOP_TRIAL_20261012.md)。

全部 21 個 Windows task 的 wrapper／status 對應看 [排程操作與搬機指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)。沿實際 action／CMD、TWStockConfig 及有效環境建立 task→producer→status→immutable receipt→artifact→consumer 關係，不以根目錄或 mtime 猜結果。latest 只定位；locator／pointer 必須核 typed schema、exact parent/run/date、receipt SHA 和原 bytes。

- 正式 source roots 預設 DATA_ROOT=`D:/Min/Python/Project/FA_Data`、OUTPUT_ROOT=`DATA_ROOT/output`；研究 active root 沿 repository `output/ml_research_storage.json`。shadow、Bank、Paper 與模型根分別定位。
- Official market wrapper 從 `OUTPUT_ROOT/scheduled/official_market_events_wrapper/latest_status.json` 追同次 immutable status，分別驗三個 children，不只查 historical events 舊 status。
- ML Allocation Forward 非交易日／config preflight receipt 在 repository `output/v4_ml_forward_scheduler/latest_status.json`；已載入 config 的 child 才使用 `config.output_root/scheduled/ml_allocation_forward/latest_status.json`。先追當輪 launcher stdout／receipt 和 config，不借舊 child 失敗當今日結果。
- Quick／weekly 研究採集使用 `scripts/audit_scheduled_research_acquisition.py --quick-status <actual path> --output-root <actual root>`，stdout-only；weekly typed parent、start／terminal、monthly／quarterly children 及 artifacts 分別核對。固定工具期限按實作；不可按資料夾時間補父 binding。
- G6 raw 外層正式來源 hold 和同 run research cycle 分列；追 cycle terminal、B terminal、source context、snapshot、model 與 registry original pins。registry index 可能續增，核當輪 immutable record，不把現 index hash與完成時 hash不同當失敗。canonical hash與file bytes SHA不同欄位，不混稱。

## 3. 時鐘、依賴與失敗判讀

每個 task 都列「文件 cadence」「實際 trigger」「當輪查核截止時間」「Scheduler結果」「producer／consumer結果」。Pacific 執行日與 Asia/Taipei 決策日、data_as_of／market session 分別顯示；台北可能已是次日。Task Ready、exit0 或 LastTaskResult0 都不授整鏈成功。

晨報通常早於 05:40 Forward、05:45 learning、05:50 Bank、06:00 EOD；報告尚未到期的項目並回讀上一個已驗 terminal。晚間 06:20 也不保證長 G6／G9 已完成；讀 heartbeat、實際 wrapper期限及 exact source wait pin。G9 CMD 預設 14400 秒（四小時）、children 各3600秒及300秒收尾；Bank Task PT5H／child7200秒；G6 annual child預設六小時。均以當輪實際 argv／settings為準。未到期限列進行中，heartbeat過期或逾時無 terminal 明確列工程問題，不靠改檢查時間掩蓋。

G9 failed 時要讀 `steps.recommendation_learning.child_status.dependencies.source_contract` 和 typed terminal：DailyPriceSourceRevisionError、technical_prospective_source_not_ready、cohort缺股屬來源／工程資格缺口，不能全歸為自然樣本不足。parent blocked_source_revision 也不阻止對已驗 research child獨立報告，但不授 formal PIT。

Evidence wrapper 非零須另核 `paper_health_source_receipt.blockers`，不能只看 `pipeline_exit_code`。若舊 baseline 的 carried entry 日期／可得時鐘缺失，列原身分證據缺口；修正後只沿 `position_identity_source` 原證據延續，缺件維持 unproven，不改舊檔。G9 `live_capture.calendar_diagnostic` 的官方年表要求須沿公開 `read_operation` 的同次 evidence 核驗，不以私有 instance memo 或本地指數列授 session proof。工程回歸與自然排程恢復分列，見[10/12 契約修正 QA](../06_qa/BALDR_SCHEDULE_CONTRACT_REPAIR_20261012.md)。

Quick 月營收 child 的 `failed`／`rejected` 必須保留 parent SHA、child receipt SHA 與 `child_diagnostics`。`quick_parent_changed_during_child_audit` 只用於初始、child 查核所用與查核後父檔的 bytes SHA 不一致；缺少 SHA 應是 `quick_parent_audit_hash_missing`，不能推定檔案競態。若官方 TWSE／TPEx 原件月份不同（例如 11508／11509），列來源月份不一致、研究候選未建立；核心 Quick 結果另列，不改期別、不合併不同月份、不用核心 exit 0 解除 child 失敗。後次官方來源自然對齊並經同次 child/artifact 驗證後，才報恢復。

Direct supervisor 對自己啟動的 builder／OOC／release child 使用保留的 `Popen` handle 確認退出並讀取 exit code；已退出的 child 不需要在等待上游後再次出現在 live PID 清單。仍活躍的 child 必須符合 command custody；外來 legacy PID 仍需實際觀測。完整鏈必須同時滿足 OOC／release exit 0 與兩份 terminal `complete`，否則保留 child blocker。`was not observed under custody` 要核對自有 child 等待邏輯與其日誌，不能直接斷言 fit 未啟動／未完成，也不能把修正程式當成歷史執行已成功。缺 formal teacher、ledger、sector 或 Rule history 時維持資格 gate，不藉改 prompt、重試上限或排程時間解除。

Forward `outcome_price_missing` 要列 event_id、symbol、planned official maturity date／horizon與價格查核結果；最新正常行情不解除歷史缺價。Maturity official calendar與附加 calendar_observation分開，後者unknown不等同前者invalid。未成熟的未來價格保持null；不補平盤、不猜停牌、不刪失敗或回填時鐘。

## 4. 資料、研究與人工事項

Candidate credit／institutional current、歷史 reconciliation conflicts、formal monthly／statement、current-observed與正式 PIT 分列。當前日期恢復不清舊衝突；保留各日期keys／值差異、舊raw／parser／revision溯源需求。正式基本面缺期或availability map缺檔需官方公告、available-at、revision lineage；研究capture不得補成正式歷史可得日。TDCC週頻及官方休市按有效日曆／發布寬限判讀，不降門檻。

Recommendation 保存成功與cohort/source品質分列：列result_id、decision_date／data_as_of、requested／eligible／missing／degraded、why-not原因、status binding hash和可核的獨立 payload hash；缺獨立payload hash明列未驗。cohort degraded先讀逐股具名原因，區分低流動性／無訊號與資料缺件，不籠統歸為source failure。

Evidence列工程errors、actionable warnings、natural maturity、advisories、blocking gaps與readiness；dry_run=true／confirm=false／writes_evidence_db=false／production_scheduler_allowed=false維持原值。INSUFFICIENT_SAMPLE、pending_human_review與owner-approved UI projection不授正式接受。若需manual review，列真實待審對象／影響及期限；相同待審不每天催。

Paper machine seed 1418不是真人持倉；不要求補虛構交易或thesis。真正manual_action_required／user_actions與research qualification分開。每個write flag都標主詞：上游producer宣告的寫入，不等於本輪唯讀audit有寫入；反之audit唯讀不否認其他正式排程已宣告的有界寫入。

## 5. 通知與完成標準

以目標thread上份實際報告的run/hash與未解問題為基準，只在新增／惡化失敗、恢復、完成、逾時、重要binding drift或需要使用者動作時通知。相同已揭露缺件、合法休市／週頻等待／自然成熟／待審保持安靜；首次無基準一次完整摘要。

通知先用白話列「這輪恢復／新增失敗、影響用途、下一個具體處理」，再附21-task精簡表與精確來源；僅差異／blocked項詳列run、receipt/hash、原因及owner。把「可修工程」「需來源證據」「待自然成熟／人工審查」與驗收條件列清楚。不得自行修復、HTTP抓資料、啟動producer／訓練、寫DB／sidecar／repo/output、改Task／automation／ACL、使用confirm、交易、promotion、commit/push；另一次人類明確授權的修正任務依其scope執行。
