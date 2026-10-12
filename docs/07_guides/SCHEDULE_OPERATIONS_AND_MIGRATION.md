# Windows／Codex 排程運維與搬機指南

本指南維護排程用途與搬機契約；實際任務清單、帳戶、絕對路徑、XML、模型與回讀證據保存於本機 ignored 清冊。最新設定與 producer 回讀見 [2026-10-09 排程修正 QA](../06_qa/BALDR_SCHEDULE_REMEDIATION_20261009.md)；日常唯讀核查規則見[全排程稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。[2026-10-06 排程稽核](../06_qa/BALDR_SCHEDULE_AUDIT_20261006.md)保留較早的時點證據。本文件不是自動註冊、啟用或切換 exe 的授權。

## 排程的三個層次

| 層次 | 執行內容與前提 | 搬機處理 |
|---|---|---|
| Windows Task Scheduler | 以所選 Windows 帳戶執行 canonical cmd wrapper；受登入、電源、時區、trigger、timeout、權限影響 | 重建 action／環境與同等必要權限，核對 XML 與自然 run |
| 本機 Codex cron | 從保存 prompt 建立獨立工作；具有自己的 execution model／effort／project／cwd | 新機重新連結 project，保留 cadence、停用狀態、通知，核對真 model 欄位 |
| 本機 Codex heartbeat | 喚回既有對話，TOML 通常僅保存 target thread；模型需核對目標對話 metadata | 同帳戶確認目標對話可用；缺對話時先重建持久指令並保持停用，不搬 session DB |
| 雲端使用者排程 | 與本機 Codex 分開管理，沒有本機資料夾存取契約 | 從雲端排程頁另盤點；不要因本機找不到就新增重複項 |

Codex 的文字 prompt 中寫某個模型，不能代替實際 execution model。heartbeat 目標對話的模型 metadata 也不是下一輪 server 已接受模型的證據。修改需 supported API／UI，保留 effort、fast、通知、owner、trigger、timezone、cwd、status；不能直接修改對話資料庫或執行中的 turn。官方 [Scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app) 說明本機工作需要電腦開機、App 運行與 project 可用，並可選模型／reasoning effort。

## Windows 任務與入口

以下是 2026-10-06 的 21 個專案任務。時間除兩個帶 offset 的任務外，都是 **Windows `Pacific Standard Time` 本地時間，隨 DST**；不是全年固定 UTC 或台北時刻。Task 名稱加 `baldr-` 前綴，入口都在 `scripts/scheduled/`。Windows 工作的 Codex model／effort 為「不適用」；ML 模型則是具 lineage 的模型 artifact，不是 Codex LLM。

縮寫：`O` 是有效 OUTPUT_ROOT，`R` 是 repository root，`S` 是既有 recommendation-learning shadow root，`B` 是 BankTaiwan shadow root。`O` 不一定等於 `R/output`；私人／Paper／模型根也不能全塞進 O。收據欄列驗收入口，還必須追同次 immutable terminal／run identity／hash。

| Task（省略 baldr-） | Trigger | 用途／先後依賴 | canonical wrapper | 驗收輸出 |
|---|---|---|---|---|
| data-update-quick-daily | 04:20 daily | Quick 行情與 SQLite 增量、research monthly child；官方來源與交易日 | run_daily_data_update_quick.cmd | O/scheduled/data_update_quick/latest_status.json；子收據另核 |
| official-market-events-daily | 04:50 daily | append-only 官方事件；來源 raw／availability | run_official_market_event_backfill.cmd | O/scheduled/official_market_events/latest_status.json |
| data-freshness-check-daily | 05:00 daily | 唯讀核 Quick、DB／raw 日期及來源契約 | run_daily_data_freshness_check.cmd | O/scheduled/data_freshness/latest_status.json |
| ml-raw-pit-refresh-daily | 05:05 daily | freshness 與 revision-ready 後發布 immutable PIT | run_ml_raw_pit_refresh.cmd | O/scheduled/ml_raw_pit_refresh/latest_status.json |
| recommendation-snapshot-daily | 05:10 daily | 保存研究推薦／candidate；current-observed 與 thesis policy | run_recommendation_snapshot.cmd | O/scheduled/recommendation_snapshot/latest_status.json |
| evidence-pipeline-dry-run-daily | 05:15 daily | 讀推薦／freshness／Paper 證據，不當 production write | run_evidence_pipeline_dry_run.cmd | O/scheduled/evidence_pipeline_dry_run/latest_status.json |
| ml-promotion-evidence-daily | 05:17 daily | 同源 OOC／replay／shadow evidence，需 corporate-action custody | run_ml_promotion_evidence.cmd | O/scheduled/ml_promotion_evidence/latest_status.json |
| ml-promotion-authority-daily | 05:18 daily | 讀相容 promotion evidence；機器 DPAPI authority | run_ml_promotion_authority.cmd | O/release_v4/ml_promotion_authority/latest_status.json |
| ml-allocation-copilot-daily | 05:20 daily | 核 promotion／forward／Paper，缺資格維持 rule-only | run_ml_allocation_copilot.cmd | O/scheduled/ml_allocation_copilot/latest_status.json |
| decision-evidence-capture-daily | 05:25 daily | 保存 decision snapshot／evidence event；核 decision 日期與來源 | run_decision_evidence_capture.cmd | O/scheduled/decision_evidence_capture/latest_status.json |
| ml-direct-chain-maintainer | 10:00 daily | Direct／OOC custody chain；lock、儲存、來源 gate；10/07 已調整晨間競爭窗口 | run_ml_direct_chain_maintenance.cmd | O/scheduled/ml_direct_chain_maintenance/latest_status.json |
| forward-outcomes-daily | 05:40 daily | 有界 evidence outcome writer；需到期可見行情 | run_forward_outcomes_daily.cmd | O/scheduled/forward_outcomes/latest_status.json |
| recommendation-calibration-learning-daily | 05:45 daily | source capture→推薦→outcome→shadow learning；原 H20 activation 另沿 exact G6 中央母體 | run_recommendation_calibration_learning.cmd | S/scheduled/recommendation_calibration_learning/latest_status.json；H20 獨立 lane 位於實際 learning output/personal_h20_natural/recommendation_learning/，私人 manifest 沿 activation 根 |
| recommendation-calibration-learning-banktaiwan-shadow-daily | 05:50 daily | 重用同源 learning snapshot／custody，成本 shadow lane | run_banktaiwan_recommendation_learning_daily.cmd | B/scheduled/recommendation_learning_banktaiwan/latest_status.json |
| paper-execution-eod-replay-daily | 06:00 daily | Quick／freshness 同日 gate 後 EOD Paper；同凍結來源最多 3 次、間隔 900s | run_paper_execution_daily_isolated.cmd | R/output/paper_execution_eod_replay/dependency_gate/latest.json 指向 hash 綁定收據及 retry／terminal |
| pit-sector-membership-preopen-capture-daily | 16:00 daily | 台北開盤前 Rule／PIT 候選，verified denominator | run_pit_sector_membership_preopen_capture.cmd | R/output/formal_daily_publications/scheduler/pit_preopen_capture/latest_status.json；rule_source 的獨立收據 |
| paper-portfolio-daily | 帶 offset；當次美西 17:25 | 台北 08:25 wake-up／08:30 guard；原 Paper state 與 calendar | run_paper_portfolio_daily.cmd | R/output/paper_execution_eod_replay/scheduled/paper_portfolio_isolated/latest_status.json |
| ml-allocation-forward-daily | 帶 offset；當次美西 17:25 | 台北 08:30 cutoff／08:35 deadline；calendar、PIT、Paper、release pin | run_ml_allocation_forward_daily.cmd | holiday／config preflight：R/output/v4_ml_forward_scheduler/latest_status.json；config child：依 config.output_root/scheduled/ml_allocation_forward/latest_status.json |
| formal-pit-sidecar-postcutoff-daily | 18:00 daily | cutoff 後 sidecar；同 wrapper 續做 Paper event capture | run_formal_pit_sidecar_postcutoff.cmd | R/output/formal_daily_publications/scheduler/pit_sidecar/latest_status.json；Paper event source capture 另核 |
| formal-input-producer-daily | 21:25 daily | Rule＋causal Paper ledger＋PIT 三路 handoff；candidate 不冒 formal | run_formal_input_producer_daily.cmd | R/output/formal_daily_publications/scheduler/latest_status.json |
| v2-2-weekly-collection | Sunday 18:00 weekly | core collection 成功後基本面／公告／季度 research children | run_v2_2_weekly_collection.cmd | O/scheduled/v2_2_weekly_collection/latest_status.json locator→hash 綁定 terminal |

排程時間只提供啟動順序，不保證上游已完成。Windows 的 IgnoreNew 僅約束同一 Task，不保證不同 Task 共用來源檔案不重疊；接受同次來源／lock／idempotency gate，不以時間間隔代替依賴核驗。05:45 learning 會重用 Quick status，因此 04:20 的驗收須依 run id／時間／immutable receipt，不只讀 latest。

本機 Codex operational heartbeat：morning report 是美西 05:30 有限唯讀核對；paper 是美西 06:20 有限唯讀核對。它們不應自行修改 Task、重跑 producer、重訓或改正式資料。其他專案、停用的舊重構排程與全部模型清冊保存在私有清單，不納入本 repo 公版模板。

## Python 與可攜入口

2026-10-09實際回讀：Direct、Paper Portfolio、Sector preopen、ML Allocation Forward四個既有Task使用`pythonw.exe → run_scheduled_cmd_hidden.py --task <固定名稱>`，由固定mapping執行原CMD；其餘17個Task仍為canonical CMD action。下段CMD形狀描述的是wrapper契約；核對已部署背景action時依[全排程驗收runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)確認精確interpreter／argv／cwd。Operational日誌本輪已啟用；不補回先前未記錄事件。

現有 action 為 `cmd.exe /c "<REPO>/scripts/scheduled/<wrapper>.cmd"`，WorkingDirectory 為 REPO。wrapper 再選 `.venv/Scripts/python.exe` 或受支援的 BALDR_PYTHON；部分舊 wrapper 缺 venv 會 fallback `python`。搬機應驗 Python 3.11 runtime 與依賴，不能直接複製舊 venv；沒有 venv 不應讓全域 Python 偶然代跑。每個 wrapper 是否接受 BALDR_PYTHON 需逐檔核對。

可攜版需整個 `baldr` 資料夾。單腳本 dispatch 形狀為 `baldr.exe scripts/scheduled/<原腳本>.py <原參數>`，模組為 `baldr.exe -m <原模組> <原參數>`。**不是** `baldr.exe <wrapper>.cmd`，也不能省略 wrapper 的多段執行、環境、gate、timeout 或原 flags。上表 canonical wrapper 與本機 `wrapper_audit.json` 保存各 Python 子入口；遷移 exe 時需逐段列出展開後 argv，包含官方 calendar、Paper retry、weekly children 等，另做相容驗證。目前 Task 保持 source／Python，exe 的新版本修復由另一 owner 處理。

Source roots 沿 TWStockConfig／wrapper；exe 為環境 > 外部 config.json > LOCALAPPDATA 空根，兩者都不自動載入 `.env`。只搬 config.json 不會替 Windows Python wrapper 改 roots。詳 [可攜指南](PORTABLE_WINDOWS.md)。

## 資料、私人與模型需求

- 市場 DATA_ROOT、衍生 OUTPUT_ROOT、Shadow 根、repository Paper operation root 分別登記。部分 Paper adapter 固定受控原市場來源，writer 固定 repository output；改環境不等於可自由 retarget。換路徑需先檢查相關 contract／hard-coded defaults。
- 私人 DATA／Watchlist、Journal、Store 的 root／mode 成對保存，仍採原已選來源；不新建空庫替代真帳，不覆寫來源。H20 使用 DATA_ROOT/personal/recommendation_h20/activation.json 或明示 override；和 PERSONAL_MODEL_POLICY_PATH namespace 分開，不因搬機重啟 enable／fit。
- ML forward 需要原 release bundle、release_manifest.json 與其 file hash pin、training／derived manifest、PIT archive、official calendar cache、Paper snapshot／ledger、日期化 config。policy、raw、dataset/model lineage 必須可回驗，不能只搬模型權重。推薦 thesis policy 與 PIT taxonomy source config 也需單獨檢查。
- DPAPI authority 不可直接複製成新機有效授權；新機需經原可信註冊／授權流程重新建立。不要搬 authentication token、password、broker credential、Codex auth.json 或私聊 session 資料庫。
- 存在檔案只是 readiness metadata，不等於 hash、source/account、PIT／cutoff、coverage 或模型品質已接受。unknown／candidate／shadow 保持原資格。

## 建立本機私有清冊

將以下內容保存至 ignored `output/qa/<日期化目錄>/`，做外部安全備份；ignored 不會隨 Git 搬機。公版文件只留 placeholder，不提交帳號、使用者絕對私人值或 XML 原機 principal。

| 每項必填 | 核對內容 |
|---|---|
| 身份與用途 | 層次、Task path／automation id、所屬 project、owner、writer／readonly |
| 模型 | cron execution model／effort／fast；heartbeat target model 與觀測來源；Windows ML artifact／pin |
| 時鐘與狀態 | trigger／timezone、DST／offset、NextRun、啟用或停用、notification、missed-start／retry／power／timeout |
| 執行環境 | executable、展開 argv、WorkingDirectory、Python／portable branch、登入方式及必要權限 |
| 依賴與設定 | 上游 immutable receipts、DATA／OUTPUT／private／model 根、config／policy／calendar／source pins |
| 驗收 | LastResult＋同次 terminal＋consumer readback、run/date/hash、failed／unknown／warnings |
| 恢復 | 哪些可以原單次冪等重試、不可替換凍結來源、備份及本輪差異撤回步驟 |

Windows 可用 `Get-ScheduledTask`／`Get-ScheduledTaskInfo`／`Export-ScheduledTask` 唯讀查詢；權限拒絕記 unknown，取得核准的唯讀權限後再查，不改 ACL 或 credential。原 XML 只是備份，不能直接作新機最高權限／原帳號模板。Codex 可用 automation API view，失敗時可讀已合法授權的 automation.toml；改 prompt 後還要核真正 execution model。

## 搬機檢查表

1. 保存舊機清冊、所有停用狀態、Task XML、wrapper／model／policy pin、immutable receipt；記錄原時區與下一自然 run。舊機先由使用者安排停寫窗口，避免新舊雙 writer。
2. 取得正確 repository 分支與可回溯 commit。重新建立 Windows x64／Python 3.11 venv，按 requirements-runtime 安裝；可攜 GUI 另搬整包並驗校驗。不要把另一工作樹暫存當正式源。
3. 依 [資料資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md) 搬市場、輸出、Shadow、Paper、私人與模型資產，保留原 bytes／lineage。活躍 SQLite 用一致備份契約，勿僅複製正在寫入的主 DB；本輪指南不授資料遷移。
4. 用新機合法路徑設定環境／外部 JSON，逐項核實原 selected store 與 H20 descriptor。若受控 Paper 固定來源不符，先提出最小修改並審核，不能用 alias／ACL 繞過。
5. Codex 登入與連 project，核模型 catalog 支援原 effort。cron 改真 execution field；heartbeat 確認 target／模型的 supported 設定方式，保留通知及停用，不直接改 threads DB。不因搬機新增重複排程。
6. 先 `scripts/scheduled/register_baldr_scheduled_tasks.cmd dryrun` review 註冊計畫；aggregate 模板不是全部 21 個現況，forward、Paper、BankTaiwan 與 PIT 的專用註冊／pins 需另核。dryrun 本身不註冊，但個別 preflight 是否寫檔依原實作檢查；首次在隔離 output 做。不要在舊機自然觀測窗口跑 execute。
7. 核對美西本地 trigger 與帶 offset trigger，依新機時區換算台北 cutoff。兩者不能統一改成當地相同鐘點；避免 DST 重複／缺失小時。Generic registrar 目前只接受 Windows Pacific 時區，換時區時不要直接套用。
8. 用新機帳戶建立最小必要權限的停用 Task／paused automation；需無人登入也執行時另審帳戶模式與 credential，不照搬舊 Interactive 或 HighestAvailable。保留原停用項；不複製 credential。
9. 先隔離 dry-run／preflight 核 argv、roots、依賴 hash、日期／unknown behavior；無 execute 權限時不跑 writer。使用者批准啟用後按依賴窗口啟用，逐個自然 run 驗收。LastResult=0＋檔案存在不足，需 exact run/date/hash／terminal／consumer。
10. 驗收 failed 時先保存失敗收據，查源日期、model manifest／pin、principal、環境、時區、權限、空間與上游終態。暫時來源失敗只用原 bounded retry；不造數據、不重建資料、不改 frozen source／cutoff、降低 gate 或補未來資料。

## 回滾

新機 Task 設定有誤時，由使用者停用新機 writer，保存失敗證據，核對沒有舊機雙 writer後恢復已核舊設定。程序版本回退不等於資料 schema 可回退；保留資料與備份。模型欄位或 prompt 修改前保存原 TOML bytes／SHA、exact diff與readback；回退前先比較目前與本輪 after pin，若他人已更新，不整檔覆蓋，僅撤回本輪欄位。公版文件可逐項撤回新增段落，不回復他人 dirty 檔。

2026-10-06：新增排程層次、21 Task契約、私有清冊與搬機／驗收／回滾檢查表。沒有註冊、啟用、手動 trigger、資料／模型寫入或 Task executable 切換。
2026-10-09：加入最新 21-task 設定與 producer 回讀 QA、共用唯讀稽核 Runbook 入口；保留 10/06 稽核作為歷史時點證據，沒有更改操作授權。
