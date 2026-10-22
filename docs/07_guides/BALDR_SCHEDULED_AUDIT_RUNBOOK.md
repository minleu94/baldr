# baldr 全排程唯讀稽核 Runbook

2026-10-14 owner已在本輪自然退出後停用Direct每日重跑：`\baldr-ml-direct-chain-maintainer` 預期 `Enabled=false`，原10:00 trigger/action保留。現行 inventory 為21個具名 Windows task，仍須逐項唯讀核對；不要把Direct已授權停用判成意外缺件或自行重新啟用。其餘20項與晨晚automation依各自證據判讀。停用不等於本輪fit成功或自然累積恢復；詳見[排程運維指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)。

人類另行授權的修正重跑應獨立列 producer 收據與資料寫入範圍；手動執行不代表 Scheduler Last／Result 恢復。Forward／Decision 的手動 `--reservation-wait-seconds` 僅限定等待，不豁免鎖或來源资格；唯讀 audit 不使用它啟動 producer。台北10/14盤前具名重跑、恢复及未解除阻塞見[10/13修復報告](../06_qa/BALDR_SCHEDULE_REPORT_REPAIR_20261013.md)。

本 Runbook 核對既有排程設定與同次執行證據；它不註冊、啟用、停用、手動觸發任務，不啟動 producer、訓練、重建資料或寫入 Task／Codex automation。完整 21-task 文件化時點見[排程運維與搬機指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)，新機接手見[機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)。

本機兩個 operational heartbeat 的文件化時間為 America/Los_Angeles 05:30 晨報與 06:20 晚間／Paper 報告。它們僅彙整已有證據，不等於 Windows producer trigger、完成期限或自然執行證據；實際 automation／thread 狀態需另行唯讀讀回。

## 1. 查詢範圍與限制

10/22 新自然觀測與工程修復見 [Track B 驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)。Freshness／Evidence 的 create-only 終態已自然產生；Quick 本輪仍在另一份 excluded revision 的舊資料庫身份拒絕，不能宣稱上游恢復。新三-family custody profile 只定位精確原 hash 鏈及18份來源；原件沒有逐檔搬遷 SHA PASS，不得以新語義核驗冒稱該證據。原 revision、歷史 PIT、用途與寫入守衛保持。

Formal input 新終態為 `formal-input-producer-terminal-receipt.v1`，latest 的 `terminal_receipt` 只定位原 bytes。核相同 UUID、task、UTC started/completed、code SHA、nested 原 producer schema/status/exit、blockers 與外部 receipt SHA；attempts 的前置 phase 不代表 terminal 已持久化，必須另核 final phase。收據或 log 持久化失敗仍非零；金融資格不由該 envelope 升格。舊 run 不補造新終態；新的自然 run 另行核驗。CLI manifest 的 receipt path 必須在明示 root 內且為相對路徑，SHA 使用不含前綴的64位hex，不能直接把latest的絕對 locator當接受。
既有唯讀檢查器 `scripts/inspect_scheduled_task_registration.py` 預設 stdout 模式一次盤點預期的 21 個 baldr tasks，包括完整 task path、State、Enabled、LastRun、LastTaskResult、NextRun、action、arguments、working directory、trigger、timeout、IgnoreNew／retry 與電源條件。使用前核對當下程式入口和其設定的 EXPECTED_TASKS；不要拿本文件表格代替主機查詢。

一般 sandbox 的 CIM access denied、COM unknown、schtasks network／path 錯誤只代表查詢受限。保留錯誤並將相應欄位標為 `unknown`；不得改 ACL、principal、系統服務或權限，也不能把 query failure 推成 task missing。`confirmed_missing=0` 也不表示所有 task 已存在。

每日營運可另以唯讀 CLI 對已固定 SHA-256 的 observation snapshot 和收據分類：`scripts/audit_daily_operations.py <manifest> --snapshot-sha256 <外部固定SHA-256> --receipt-root <收據根目錄>`。輸出六種 component 狀態：`HEALTHY`、`DEGRADED`、`BLOCKED_SOURCE`、`STALE`、`EXECUTION_FAILED`、`UNKNOWN`。輸入無法核實、收據缺失或格式不支援時保留 `UNKNOWN` 或相應阻塞狀態；這不是 task 設定讀回，也不替代 scheduler inspector、同次 producer terminal 或 consumer readback。沒有可核實的執行用量記錄為 `UNOBSERVABLE`，不可當成零用量或已完成。

本輪 recovery CLI 採六軌：WindowsExecution、Application、SourceFreshness、FinancialQualification、DependencyReadiness、Observability。只有同一 run 的精確 schema、run ID、開始／完成時鐘、terminal、來源／cutoff、artifact 與 hash 可互相綁定；舊 adapter 不補缺失時間或 run identity，未知欄位留 `UNKNOWN`。Freshness／Evidence 新終態 receipt含實際 run 時鐘、code version、failure code 與 payload SHA；latest 是 locator，不是結果證據。root-owned CLI integration 已驗，修復後自然驗證待觀測，詳見[2026-10-21 recovery 觀測](../06_qa/BALDR_DAILY_OPERATIONS_RECOVERY_20261021.md)。

2026-10-21 主機讀回 21/21，query error 0、XML definition delta 0。唯一新增自然執行是 formal-input 21:25 PDT，blocked/result 2，原因為 2026-09-09 runtime config 對 2026-10-22 已過期；formal write=false 且沒有 immutable run receipt。Paper 08:25 Taipei 同次 terminal 的輸出越界與 Forward 同次 PIT archive 缺件各自保留失敗。Direct maintainer 的 `Enabled=false` 是預期狀態，不列為告警。Quick custody 的實際 readback 與 21-task CLI readback 分開記錄；必要工程 QA 已驗，整體 `DAILY_OPERATIONS_PARTIAL_RECOVERY`；修復分支等自然 run，ML raw 原失敗不可觀測與Owner外部動作另列。精確 21-row branch 狀態、QA003–QA007 原結果與具名依賴鏈見[recovery 摘要](../06_qa/BALDR_DAILY_OPERATIONS_RECOVERY_20261021.md)。這些是當日證據，不代表修復後自然驗收。

2026-10-09 具名設定 QA 的 readback 範圍記錄 Direct、Paper Portfolio、PIT sector preopen 和 ML Allocation Forward 四項透過 `pythonw.exe → run_scheduled_cmd_hidden.py --task <exact task> → canonical CMD`；另 17 項使用 canonical CMD action。這是該次主機 QA 的設定描述，不是本次或新機驗收。核 hidden dispatcher 時逐項比對 interpreter、exact argv、cwd 和固定 mapping。

Direct maintainer 文件化 trigger 是 Pacific 10:00；05:30 是舊預期。舊 trigger expectation 不能用來判斷目前 drift；仍應以該輪 scheduler readback 為準。

## 2. 先確認同一執行身份

依實際 action、wrapper、TWStockConfig 與有效環境整理以下鏈：

`task → producer → status → immutable terminal/receipt → artifact → consumer readback`

每一環記錄 task identity、execution run／parent ID、實際日期與時區、source/data date、status、hash、輸出根和 consumer。`latest`／locator 只用來找到候選結果；必須核 typed schema、exact parent/run/date、receipt SHA 和原始 bytes。Hash 欄位若定義為 canonical content hash，就不能和 file-byte SHA 混稱。

先依實際設定確認來源根；source mode 常見預設 `DATA_ROOT=F:/Min/Python/Project/FA_Data`，`OUTPUT_ROOT` 預設相對於 DATA_ROOT，但環境與 runtime 可能覆蓋。研究 active root、Paper、Shadow、BankTaiwan、私人持倉和模型根各別解析，不用 repository／`OUTPUT_ROOT` 假定全部寫在一處，也不從檔案 mtime 推導有效性。

有幾個容易誤讀的 status 位置：

- 官方市場 wrapper 應追 wrapper 自己的同次 immutable status，再分別核三個 children；舊 `historical_events` status 不能代表整條 wrapper。
- ML Allocation Forward 的 holiday/config preflight receipt 在 repository `output/v4_ml_forward_scheduler/latest_status.json`；已載入 config 的 child 才沿該 config 的 `output_root/scheduled/ml_allocation_forward/latest_status.json`。先確認本輪 launcher／config identity，不借舊 child status 結案。
- Quick、weekly research acquisition 要同時核 parent／child、開始與 terminal、日期／hash及 artifacts；task exit 0 不能補齊缺少的 parent binding。
- H20 natural lane 若由同次 G6／G9 research chain 生產，核母體與 source pin 一致、exact run／hash、activation lineage；`completed_with_pending` 代表仍有條件未到或缺件，不是成熟成功。唯讀 audit 不啟動該 producer。

`refreshed` 日曆使用刷新終態而非preinspection；新檔缺件、hash錯誤或時鐘不合仍blocked。Evidence先區分身份與aggregate status未passed，不以persisted result替代passed gate。Paper NULL open同日retry與跨日missed分開；1435／10月12日舊缺價收據不能由audit改期。ML Forward lock preflight `not_started`不等於恢復，Bank task query unknown不等於upstream stopped；保留最後Task observation。G9 child timeout須核原期限與全母體manifest終態，不能拿部分predictions當完成。具名修正及未解除的來源見[10/13雙報告QA](../06_qa/BALDR_SCHEDULE_REPORT_REPAIR_20261013.md)。

## 3. 時鐘與 lane 依賴

逐項列「文件基準 cadence」「主機實際 trigger」「查核時點」「Scheduler 結果」「producer／consumer 結果」。Pacific execution date、Asia/Taipei decision date、market session／`data_as_of` 可能不是同一天；日期字串需連時區一起記錄。

Paper Portfolio 與 ML forward 於台北 08:25（UTC 00:25）offset 喚醒，PDT 前一日 17:25／PST 前一日 16:25 是同一時刻的時區換算，不代表當季 Task 已自然驗收。前者等真實 08:30 guard；後者等 08:30 cutoff 並有 08:35 deadline。新機必須讀 Task XML offset 和實際 UTC／本地 `NextRun`。台北 cutoff 尚未到、holiday、`waiting_for_taipei_cutoff` 或 `completed_with_pending` 都不能當成完整成功或自然 maturity。

Pacific Task 隨 DST 改變本地鐘點所代表的 UTC 時間；台北 offset lane 則依固定 UTC offset 執行。每次 DST 切換、搬機或時區設定改動後，必須以該機 Task XML 和實際 UTC／本地 `NextRun` 確認；沒有讀回資料時記 `UNOBSERVABLE`，不可用手算換算填成已驗收。

晨間 05:30 report 早於 05:40 Forward、05:45 learning、05:50 Bank 和 06:00 EOD；只可報告這些尚未到期或上一個已驗 terminal 的實際狀態。06:20 report 也不保證長時間 G6／G9 chain 已完成；timeout、仍活躍 child 或 heartbeat 過期分別報告，不能以放寬檢查時間掩蓋。timeout、retry、電源條件及 cutoff 以當次實際 argv／Task XML 為準。

跨 task 依賴透過同次 source identity、receipt、lock、terminal 和 consumer readback 來判斷，不能因排程時間前後相接就推定上游完成。`Task Ready`、`LastTaskResult=0`、process exit 0、單一 status file 存在、heartbeat 回報和人工執行成功各是不同證據。

## 4. 產出與結果解讀

| 候選結果 | 必要核對 | 不足以單獨證明 |
|---|---|---|
| Window Task 已啟動 | exact task path、action／argv／cwd、trigger、principal、last／next run | task ready 或 action 字串相似 |
| Producer 完成 | 同一 run ID 的 terminal／exit、source/date、結果 status、輸出 hash | exit 0、舊 latest 或 output mtime |
| Artifact 可讀 | typed manifest、bytes hash、lineage、source/account、日期／cutoff、coverage | 檔案存在或 model 權重有大小 |
| Consumer 接受 | 同一 parent/run/date/hash 的唯讀 consumer readback 與 warnings | 上游 status 顯示 complete |
| 自然成熟 | 自然 trigger 發生於正確時區／cutoff，等待期滿，完成同次 terminal、lineage 與 consumer 核驗 | 手動 replay、離線 QA、未到期資料或 engineer trial |

遇到 `failed`、`blocked`、`unknown`、`partial`、`degraded`、`pending` 或空結果，保留原 status 和原因。工程程式修復、人工手動執行、來源恢復、自然 trigger 和下游讀回要分開記錄；程式修正不追溯改寫舊 run 成功。樣本不足、合法等待和缺證據也要分開，不把未成熟值補成平盤或零報酬。

有代表性的 lane 限制：

- Evidence 的 `dry_run`、`confirm`、寫入旗標和 production permission 分別讀；`INSUFFICIENT_SAMPLE` 或 `pending_human_review` 不代表已正式接受。
- Paper seed／機器模擬資料不是使用者真實持倉。Paper snapshot、成交 ledger、EOD replay 和 Paper Portfolio schedule 也不是同一資料。
- 推薦候選與 cohort 先列 result／decision date、data date、requested／eligible／missing／degraded 和 why-not；空候選與來源失敗分開。
- Forward outcomes 必須按 official calendar 的 planned maturity date 和可得價格查核。尚未成熟保持 null；不能拿近期價格、row offset 或其他交易日補成熟結果。
- 正式 PIT、current-observed、shadow 和歷史 replay 的資格分開列。candidate／shadow 狀態不會因排程成功自動升格為 Formal、promotion 或 broker authority。

## 5. 彙報與不變事項

每份 audit 至少包含日期／時區、21 tasks 的查詢覆蓋、read failure／unknown、兩個 heartbeat 讀回狀態（若有）、新增／恢復／持續 blocker、exact run／receipt／hash、下游結果和下一步 owner。只對新失敗、恢復、完成、超期或需要人處理的差異詳報；例行休市、正常週頻等待、自然成熟等待和既有人工待審依 notification 契約處理。

這項稽核不得自行 HTTP 抓資料、執行 writer／producer／訓練、修改 DB／sidecar／repo output、改 Task／Codex automation／credentials／ACL、交易、promotion、commit 或 push。發現需要修正時，留下具體 affected run、原始 blocker、驗收條件與所需 owner；若另獲明確授權再以獨立 scope 修正。

Read-only 狀態或失敗收據不授權重跑 writer、補跑錯過的自然排程或重建歷史；先保留原始 failure、查同一 run 的終態與下游讀回，待來源及期限資格明確後再依獨立人類授權處理。正式金融資料、正式評分／回測、Paper／Forward、ML Promotion 與交易仍各受正式來源、PIT、金融精度與用途 Gate 約束；`HEALTHY` 只表示本 CLI 核過的同次收據符合其輸入契約，不等於任何正式金融接受或績效證明。

失敗分支的修復後條件各自獨立：Quick add-only binding、BankTaiwan 精確 D→F candidate/manifest/artifact hash 與 receipt gate、Paper 隔離 output 邊界、Forward PIT/cutoff、Formal runtime config、Freshness/Evidence same-run terminal。已核的 Quick 868 rows／14,756 cells 只證明該次唯讀 scope；Bank F counterpart 的 candidate 等 identity hashes 相符，但 migration receipt 缺 candidate.json／manifest.json 精確 PASS。這些工程分支已經必要QA，仍待新自然 run；不得降低 guard 或把一個分支的 PASS 外推到其他 lane。

過往逐日診斷、工程假設與 named QA 時點見[歷史封存區](../09_archive/README.md)，不可用來推定目前排程已存在或已自然執行。現行排程基準與 lane 入口見[排程運維與搬機指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)。

ML raw 每run診斷位於有效 OUTPUT_ROOT 的 scheduled/ml_raw_pit_refresh/launcher_logs；核有效roots、Python、UTC／timezone、兩streams與child exit。這不是producer receipt；建log失敗73且不啟動child，不能據此補回10/21舊失敗原因。Freshness／Evidence收據明示receipt_root，拒絕內層junction與reparse，repo/output僅沿既有核准mountpoint resolver。
