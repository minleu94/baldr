# Windows／Codex 排程運維與搬機指南

## Direct 昂貴重跑暫停（2026-10-14）

依 owner 明確授權，待10/13 10:00 PDT的Direct流程自然結束後，於10/14 01:07 PDT停用 `\baldr-ml-direct-chain-maintainer`，保留原每日10:00 trigger與action；目前 `Enabled=false`，不再每日自動建置／訓練。其他20個Windows Task與晨晚唯讀稽核automation保留。新機不得把這個owner停用狀態當成缺件而自行重新啟用。

需要重跑時，先核上次失敗原因、正式teacher inputs與自然證據累積資格，再取得另行人類授權；不能僅因前次failed或有新receipt就重跑。資格不足不降低gate、不補造歷史，保留blocked收據。停用不是模型驗收或自然證據累積恢復；本輪完整結果、hash與核對界線見[具名QA報告](../06_qa/BALDR_SCHEDULE_REPORT_REPAIR_20261013.md)。

本指南說明 baldr 排程的種類、日常核對入口與移機界線。它是操作文件，不是註冊、啟用、手動觸發、改帳戶或切換 portable executable 的授權。若目標是新機或 owner 移交，從[機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)開始；唯讀查證看[全排程唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。

## 排程種類與權威

| 類型 | 由什麼執行 | 移機時要核對 |
|---|---|---|
| Windows Task Scheduler | baldr canonical CMD wrapper 或固定隱藏 dispatcher | Task identity、action／argv、working directory、principal、timezone／trigger、enabled、retry／timeout、依賴和同次產物 |
| 本機 Codex cron | 保存的 automation prompt 加 execution model／effort／project／working directory | 原 owner、目標 project、實際 execution model、effort、通知、cadence、timezone、paused／active |
| 本機 Codex heartbeat | 喚回既有 Codex 對話；保存目標 thread 與週期 | 目標 thread 是否可用、對話真正 model、週期、timezone、通知和狀態；不可搬 session database |
| 雲端排程 | 雲端服務自己的 automation | 需在雲端排程頁另行盤點；本機找不到不代表沒有，也不應新增重複工作 |

Prompt 文字寫著某模型不代表實際 execution model；heartbeat 對話 metadata 也不是下一輪已接受模型的證據。變更使用該平台支援的 UI／API，保留 owner、timezone、通知、effort、cwd 與 enabled 狀態。不得直接修改 Codex 對話資料庫或執行中的 turn。

## Windows 21 個任務的文件化基準

下表逐項對照 `scripts/inspect_scheduled_task_registration.py` 的 `EXPECTED_TASKS`（21 個完整 ID 與預期 trigger）及 `TASK_WRAPPER_PATHS`（21 個 canonical CMD 路徑），並保留 2026-10-06 文件化用途。這是 repo 靜態契約／文件基準，不是任何 Windows 主機的 scheduler readback。Checker 的 19 個一般 Pacific 時間字串不包含 timezone；`Pacific Standard Time` 是目前註冊契約與文件基準，兩個 offset 任務則在 checker 字串中明列 `+08:00`。新機仍須讀 XML、principal、trigger、timezone／offset 與實際 UTC／本地 `NextRun`，不可由此表推定已註冊或自然 run 通過。

| 完整 Task ID | 預期 trigger／timezone | canonical wrapper | Lane／用途 |
|---|---:|---|---|
| `baldr-data-update-quick-daily` | DAILY 04:20 · Pacific local | `scripts/scheduled/run_daily_data_update_quick.cmd` | Quick 行情與 SQLite 增量、近期研究資料 child |
| `baldr-official-market-events-daily` | DAILY 04:50 · Pacific local | `scripts/scheduled/run_official_market_event_backfill.cmd` | 官方事件 append-only 回填 |
| `baldr-data-freshness-check-daily` | DAILY 05:00 · Pacific local | `scripts/scheduled/run_daily_data_freshness_check.cmd` | 唯讀檢查行情與來源新鮮度 |
| `baldr-ml-raw-pit-refresh-daily` | DAILY 05:05 · Pacific local | `scripts/scheduled/run_ml_raw_pit_refresh.cmd` | 通過 freshness／revision gate 後更新 PIT |
| `baldr-recommendation-snapshot-daily` | DAILY 05:10 · Pacific local | `scripts/scheduled/run_recommendation_snapshot.cmd` | 保存推薦研究與候選快照 |
| `baldr-evidence-pipeline-dry-run-daily` | DAILY 05:15 · Pacific local | `scripts/scheduled/run_evidence_pipeline_dry_run.cmd` | 唯讀 Evidence dry-run |
| `baldr-ml-promotion-evidence-daily` | DAILY 05:17 · Pacific local | `scripts/scheduled/run_ml_promotion_evidence.cmd` | 核 promotion evidence 與同源 lineage |
| `baldr-ml-promotion-authority-daily` | DAILY 05:18 · Pacific local | `scripts/scheduled/run_ml_promotion_authority.cmd` | 讀相容 evidence／本機 authority |
| `baldr-ml-allocation-copilot-daily` | DAILY 05:20 · Pacific local | `scripts/scheduled/run_ml_allocation_copilot.cmd` | 缺資格時維持 rule-only 的配置研究 |
| `baldr-decision-evidence-capture-daily` | DAILY 05:25 · Pacific local | `scripts/scheduled/run_decision_evidence_capture.cmd` | 保存決策摘要與 evidence event |
| `baldr-ml-direct-chain-maintainer` | DAILY 10:00 · Pacific local | `scripts/scheduled/run_ml_direct_chain_maintenance.cmd` | Direct／OOC／release custody chain |
| `baldr-forward-outcomes-daily` | DAILY 05:40 · Pacific local | `scripts/scheduled/run_forward_outcomes_daily.cmd` | 有界 forward outcomes writer |
| `baldr-recommendation-calibration-learning-daily` | DAILY 05:45 · Pacific local | `scripts/scheduled/run_recommendation_calibration_learning.cmd` | 推薦 capture／outcome／learning shadow |
| `baldr-recommendation-calibration-learning-banktaiwan-shadow-daily` | DAILY 05:50 · Pacific local | `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.cmd` | 同源 BankTaiwan 成本 shadow lane |
| `baldr-paper-execution-eod-replay-daily` | DAILY 06:00 · Pacific local | `scripts/scheduled/run_paper_execution_daily_isolated.cmd` | EOD Paper replay 與 bounded dependency gate |
| `baldr-pit-sector-membership-preopen-capture-daily` | DAILY 16:00 · Pacific local | `scripts/scheduled/run_pit_sector_membership_preopen_capture.cmd` | PIT 產業成分盤前 capture |
| `baldr-paper-portfolio-daily` | DAILY 08:25 +08:00 · Asia/Taipei | `scripts/scheduled/run_paper_portfolio_daily.cmd` | Paper preopen snapshot；08:30 guard |
| `baldr-ml-allocation-forward-daily` | DAILY 08:25 +08:00 · Asia/Taipei | `scripts/scheduled/run_ml_allocation_forward_daily.cmd` | Forward candidate-only shadow；08:30 cutoff／08:35 deadline |
| `baldr-formal-pit-sidecar-postcutoff-daily` | DAILY 18:00 · Pacific local | `scripts/scheduled/run_formal_pit_sidecar_postcutoff.cmd` | cutoff 後 PIT sidecar／Paper event capture |
| `baldr-formal-input-producer-daily` | DAILY 21:25 · Pacific local | `scripts/scheduled/run_formal_input_producer_daily.cmd` | Rule、Paper、PIT candidate handoff |
| `baldr-v2-2-weekly-collection` | WEEKLY SUN 18:00 · Pacific local | `scripts/scheduled/run_v2_2_weekly_collection.cmd` | Weekly collection 及有界研究 children |

Windows task 啟動順序不代表上游成功或來源已完成。`IgnoreNew` 僅限制同一 task；跨 task 需沿 immutable receipt、run／date、lock、source identity 及 consumer readback 確認依賴，不以時間間隔替代。

排錯先核[10/13晨間／晚間查核](../06_qa/BALDR_SCHEDULE_REPORT_REPAIR_20261013.md)及[唯讀稽核](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。現行consumer把刷新前inspection與刷新終態分開，Evidence把identity與not-passed分開；H20每日及manifest只在同一read operation共用完整binding，終態重驗後才發布reference，不跨operation保存快取。期限、Task配置與automation通知規則不因此改變。失敗來源與missed Paper session仍按原owner處理，不刪收據或重建歷史。

## Codex operational heartbeats

文件化的兩個本機唯讀 heartbeat 為：

| 用途 | 文件化週期 | 時區 | 操作界線 |
|---|---:|---|---|
| 晨間 report | 每日 05:30 | `America/Los_Angeles` | 彙整已存在 evidence；不啟動 producer 或修復來源 |
| 晚間／Paper report | 每日 06:20 | `America/Los_Angeles` | 核對已存在 Paper／排程 evidence；不寫帳本、不啟動排程 |

這是文件化基準，不表示目標 thread 或本機 automation 現況已讀回。Heartbeat 對話通常保存 cadence／target，而 prompt 的模型文字不是實際模型設定。兩份 report 都不能代替 Windows producer trigger 或自然執行期限。

## 時區、offset 與 DST

多數 Windows task 依 `Pacific Standard Time` 本地時鐘執行，隨 DST 變化；Generic registrar 在現有文件化契約中只接受 Windows Pacific 時區，不要把台北時間改寫成一個固定 Pacific 鐘點。Paper Portfolio 與 ML forward 兩者於 Taipei 08:25（UTC 00:25）offset 喚醒；其時區換算是 PDT 前一日 17:25／PST 前一日 16:25。這是鐘點換算，不是 seasonal Task QA 或自然 run 證據。

Paper 流程再等真實台北 08:30 guard；ML forward 在 08:30 cutoff 前不消費並有 08:35 deadline。移機或 DST 變換後須讀新機 Task XML offset、trigger 與實際 UTC／本地 `NextRun`，再核台北時鐘、日曆和 lane status。若實際時區不同、offset 缺失或查詢權限不足，標示 drift／unknown 並停在 plan；不可手工換算後宣稱驗收通過。

## 登記器範圍與 runtime

Aggregate registrar 只覆蓋它定義的子集，不代表完整 21-task inventory；它不註冊 ML forward 專用 XML，也不包含 BankTaiwan recommendation shadow lane。Paper Portfolio、PIT sector capture 與部分 Direct／Forward 入口亦有專屬 wrapper、preflight 或 dispatcher 契約，需按各自 lane 核驗，不能以 aggregate 的成功代替。

`scripts/scheduled/register_baldr_scheduled_tasks.cmd` 是舊批次入口：它仍把 `baldr-ml-direct-chain-maintainer` 顯示及建立為 05:30，和 checker `EXPECTED_TASKS`、現行 `register_baldr_scheduled_tasks.ps1` 的 10:00 基準衝突。移機註冊不要使用這個舊 `.cmd`。對 PowerShell registrar 支援的子集，先唯讀查詢現有設定並逐項核對完整 desired-versus-observed 差異；其 dry-run 輸出不能取代完整差異審查，也未在此證明 writer 冪等。只有差異、專用 lane 與帳戶／action 已核實、完整變更清冊已獲授權後才可註冊，之後立即精確讀回。

在 2026-10-09 具名設定 QA 的回讀範圍內，Direct、Paper Portfolio、PIT sector preopen 和 ML Allocation Forward 四項使用 `pythonw.exe → run_scheduled_cmd_hidden.py --task <exact task> → canonical CMD`；另外 17 項使用 canonical CMD action。這是該次 QA 記錄，不是新機讀回結果。source GUI 和 portable GUI 都有各自設定流程；更換 GUI 不會自動將排程 wrapper 從 CMD／Python 換成 EXE。

移植 wrapper 時不可複製 venv。先依目標 runtime 建立相容 Python／portable environment，核 wrapper 的 interpreter、展開 argv、working directory、timeout、flags 和環境根。個別 `BALDR_PYTHON`、fallback 或子命令是否可用，需按原 wrapper source 和該機 readback 確認。可攜版要搬整個包，但 Task Scheduler replacement 必須逐項另行審核。

## 帳戶、資料根與模型權限

- 每個 task 核 Windows principal、登入／電源情境、必要檔案 ACL、可讀寫 roots、timeout 與 retry。Task XML 備份不等於新機可直接沿用原 principal 或 HighestAvailable。
- `DATA_ROOT`、`OUTPUT_ROOT`、Shadow、BankTaiwan、repository Paper、私人持倉與 model/research root 各自盤點，不以 `OUTPUT_ROOT` 或檔案存在推斷其他 root。
- 使用者帳戶、Paper／私人資料與 model lineage 需要 owner 的來源／帳本／manifest／hash pins；模型權重單檔不足以證明 source/account、PIT、cutoff 或使用資格。
- DPAPI/native credential 綁定機器與帳戶，舊機狀態不能靠複製檔案搬移。新機需由可信流程重新註冊／授權；不可複製密碼、token、broker credential 或 Codex auth/session 檔。
- 查詢拒絕或可見範圍不足時記 `unknown`；不要降低 gate、改 ACL 或把私人資產置換成空資料庫。

## 搬機順序與差異處理

逐步執行[機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)：

1. 舊機匯出清冊與 task XML 備份，記錄 assets、clock、model pins、Codex cron／heartbeat 的實際狀態。
2. 停止要移交的舊機 writer 並取得可核證據；manifest 的 `old_machine_writer_stopped` 是布林欄位，設為 false 或缺少證據時不要在新機啟用同 lane。
3. 新機選 source／portable GUI，設定自己的 `repo_root`、roots、timezone，依 owner 授權移交資產；不搬 venv 或 credentials。
4. 將 manifest 的 `schedules[]` 作為 desired、`observed_schedules[]` 作為新機實際讀回，逐項比較 task identity、platform、wrapper／argv、working directory、timezone、principal 和 enabled state。
5. `scripts/document_control.py bootstrap-plan` 只唯讀檢查／輸出 JSON 計畫，不能安裝、搬資料、寫設定或註冊排程。差異、pending 和 error 修正後可再產生計畫；plan 可重複讀取，不表示 schedule writer 已證明冪等。
6. 操作前核對 owner 是否已授權這份完整、具體的變更清冊。清冊逐項列 before／after、owner、停舊／啟新順序、風險及回滾；一份授權可涵蓋清冊列出的完整範圍，不必每個 task 重複詢問。尚未授權時先交付可審查 plan；超出清冊或出現高風險新差異才另行確認。一個 writer/lane 一次切換，不可雙機同時寫入。
7. 排程設定 readback、第一次自然 run 和下游 consumer readback 分開驗收；自然 run 前不能宣稱該季節、時區或 lane 已驗收。

Manifest 公版欄位與範例見 [`examples/machine_bootstrap_manifest.example.json`](../../examples/machine_bootstrap_manifest.example.json)。私有本機 manifest、帳戶、絕對私人路徑和 credential 不得提交進 repository；task 狀態和計畫位置由工具實際回報的 `output/tasks/` 任務目錄核對。

## 日常核對與自然 run 驗收

唯讀 audit 用 [`scripts/inspect_scheduled_task_registration.py`](../../scripts/inspect_scheduled_task_registration.py) 核對完整 task name/path、State、Enabled、LastRun／LastResult、NextRun、action、argv、working directory、trigger、timeout、電源／retry 及 dispatcher mapping。CIM、COM、schtasks 權限錯誤代表查詢環境失敗，不代表 task missing；能讀幾項也不代表全表完整。細節見[全排程唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。

每次驗收沿同一 identity 建立 `task → producer → status → immutable terminal/receipt → artifact → consumer readback` 路徑。latest status 只用來定位；核 exact run/date、parent/hash、terminal 和下游 readback。`Task Ready`、`LastResult=0`、exit 0、heartbeat 回報、status receipt 存在或檔案時間更新都不足以單獨宣稱自然成功。

對 Paper／Forward，保留其共同 08:25 wakeup 與 08:30 readiness/cutoff 的不同角色；未到 cutoff、holiday、`waiting_for_taipei_cutoff` 或 `completed_with_pending` 不能結案成成功或自然成熟。對 recommendation learning、Forward outcome、promotion 與 model shadow，source／樣本不完整或未到 maturity 保持 pending，不從工程試跑、舊 latest 或離線 replay 增授自然 credit。

## lane 操作入口

| Lane | 使用者入口 |
|---|---|
| Quick 更新與 freshness | [資料與市場研究手冊](manuals/DATA_AND_MARKET_RESEARCH.md) |
| Recommendation、forward outcome 與 calibration shadow | [推薦與 Research Lab 手冊](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)及[排程唯讀稽核](BALDR_SCHEDULED_AUDIT_RUNBOOK.md) |
| Paper EOD／Portfolio、持倉與成本 | [觀察清單與持倉手冊](manuals/WATCHLIST_AND_PORTFOLIO.md) |
| ML shadow／自然 evidence | [ML Shadow 推論操作 Runbook](ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md)及[歷史 ML Shadow Runbook](HISTORICAL_ML_SHADOW_RUNBOOK.md) |
| PIT、正式 sidecar／repair | [PIT 歷史資料修復 Runbook](PIT_HISTORICAL_DATA_REPAIR_RUNBOOK.md) |
| Weekly collection | [V2.2 Weekly Review Runbook](V2_2_WEEKLY_REVIEW_RUNBOOK.md) |

舊排程日記、逐次 error、特定 QA 時點和全部私有路徑已移入[歷史封存](../09_archive/README.md)，以原件追溯時不可取代當前主機讀回。回滾前先停止新機 writer、保存本輪 XML／diff／產物，再逐項撤回本次變更；確認新機停止後才能另行授權恢復舊機 writer，避免雙寫。
