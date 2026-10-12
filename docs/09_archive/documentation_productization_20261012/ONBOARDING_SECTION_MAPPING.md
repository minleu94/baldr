# 使用者入口、Manual 最終 Topic Mapping 與排程靜態核對

核對日期：2026-10-12。此文件記錄文件入口和 repository 靜態定義，不代表任何新機的安裝、Task 註冊／啟用、Codex automation 讀回或自然觸發已通過。

## 舊入口到現行落點

| 舊節點／使用者問題 | 現行入口 | 歷史材料／界線 |
|---|---|---|
| 第一次安裝 baldr | [`docs/07_guides/README.md`](../../07_guides/README.md) → [`FIRST_INSTALL_PROMPT.md`](../../07_guides/FIRST_INSTALL_PROMPT.md) → [`INSTALL_GUIDE.md`](../../07_guides/INSTALL_GUIDE.md) → [`QUICK_START.md`](../../07_guides/QUICK_START.md) | GUI 安裝不會註冊排程；完整 scope 依 prompt／runbook。 |
| 接手既有資料或排程 | [`MACHINE_BOOTSTRAP_RUNBOOK.md`](../../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md) → [`SCHEDULE_OPERATIONS_AND_MIGRATION.md`](../../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md) | 舊機清冊、XML、roots、writer、DPAPI／native credential、模型 lineage 與回滾按 owner 核准的 scope 處理。 |
| Windows 可攜版 | [`PORTABLE_WINDOWS.md`](../../07_guides/PORTABLE_WINDOWS.md) | 現行設定與排錯在指南前段；2026-10-06 EXE bytes／hash／PASS 僅是具名歷史 QA，不是最新版本、其他 Windows 主機或 Task runtime 的證明。 |
| UI 日常操作 | [`APPLICATION_MANUAL.md` §1–3](../../07_guides/APPLICATION_MANUAL.md#1-日常使用旅程) → [主題手冊地圖](../../07_guides/manuals/README.md) → [資料與市場研究](../../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md)、[推薦與 Research Lab](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)、[觀察清單與持倉](../../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md) | 日期化舊章節保留舊 anchor，原文在 `docs/09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md`。下表列出本輪從原 Manual／Supplements 找回的現行 userflow 落點。 |
| 全部排程的唯讀核對 | [`BALDR_SCHEDULED_AUDIT_RUNBOOK.md`](../../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md) → [21-task 文件基準](../../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md#windows-21-個任務的文件化基準) | 主機 readback 必須由目標 Windows／Codex 平台取得；文件表不是 live inventory。 |
| 舊 Manual Supplements 內容 | [`APPLICATION_MANUAL_SUPPLEMENTS.md`](../../07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md) 歷史索引 | 各節全文轉到 `docs/09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md`；不能再當作 current runbook。現行 Manual 只抽取仍可由 UI／owner code 支持的使用者流程；具名 QA 與日期結果留在歷史。Immutable ML retention 的現行檢視／核准邊界已由 [`data_storage_runtime.md`](../../01_architecture/current/data_storage_runtime.md#immutable-ml-retention-的目前檢視與核准邊界) 接管：目前 inventory reader 唯讀，沒有 destructive retention runbook。 |

## Manual 舊節點到現行主題落點

本輪逐項比對封存原件 `APPLICATION_MANUAL.md`（4,579 行）和 `APPLICATION_MANUAL_SUPPLEMENTS.md`（2,710 行）與現行三份 Manual。舊檔中的日期化工程、特定機器驗收、CLI 執行紀錄和已過期狀態留在 archive；下面只把仍適用且由現行 UI／程式 owner 支持的操作步驟帶回現行手冊。整體 Gate、自然 run 和新機狀態仍以當前 Snapshot／具名 QA／主機 readback 判斷。

| 封存節點／曾有的使用者問題 | 現行操作落點 | 只作歷史或目前限制 |
|---|---|---|
| Manual §4 數據更新、§5 市場探索；Supplements「V5 日常操作與可讀性工程」中的入口、資料日、來源與失敗恢復 | [`DATA_AND_MARKET_RESEARCH.md`](../../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md)：資料狀態、快速／安全更新、Regime、個股／產業強弱、主力流向；新增每日研究條件與具名母體流程。 | 當時的樣本數、日期與來源 freshness QA 不作現況；更新 owner 仍是 UI/application/data service。 |
| Manual §6.7 官方市場／技術條件；§7 尾端 UX04／05、UX13／18、UX20 等已保存來源、Union、分頁、比較和收藏節點 | [`RECOMMENDATION_AND_RESEARCH_LAB.md`](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)：「6.7 官方市場與技術條件研究」及「已保存來源與完整母體研究」。 | 靜態來源與讀回操作可用於已核驗的指定保存版本；來源 available time 未知、coverage 不完整或 external root 唯讀時仍保留限制。歷史版本數值／PASS 留 archive。 |
| Manual §7.3 個股研究報告；Supplements「個股摘要的變化與資料限制」、保存價格／MA 圖、精確返回 | [`WATCHLIST_AND_PORTFOLIO.md`](../../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md)「個股研究報告」；H20 詳細名單流程在推薦手冊「個人 H20 保存研究」。 | 具名缺資料畫面、特定 EXE／Native QA 和日期化模型效果只供追溯；最新／原保存 context 是不同研究路由。Owner：`ui_qt/views/stock_research_report_view.py`、`ui_qt/views/stock_research_workspace.py`、`ui_qt/main.py`。 |
| Manual §9.9.1c／f／g 個人模型擷取、摘要、H20 原模型與 policy 路徑 | [`RECOMMENDATION_AND_RESEARCH_LAB.md`](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)「個人 H20 保存研究」保留現行 UI 名單、欄位、選取下鑽、收藏、取消及失敗判讀。 | 舊 fit／policy／自然 maturity 的工程命令和單次收據仍是歷史或 owner 維運內容；不宣稱模型品質、自然成熟或正式 scoring 通過。Owner：`ui_qt/main.py`、`ui_qt/widgets/personal_h20_research_widget.py`、`scripts/scheduled/personal_h20_daily_hook.py`。 |
| Manual §10.0 使用者聲明持倉研究（步驟、成本、source/Advice pair、cutoff、WAIT_CONFIRMATION） | [`WATCHLIST_AND_PORTFOLIO.md`](../../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md)「聲明持倉研究」。保存、修訂、重新讀取、來源日期及可得時間安全均保留為 UI userflow。 | Entry lineage 未證明；`可檢視` 不是安全結論或實際績效。Owner：`app_module/user_declared_holding_research.py`、`ui_qt/widgets/user_declared_holding_research_widget.py`。 |
| Manual §10.8 Health 歷史生命週期；Supplements「Position Health read model 的 Portfolio／Workbench 呈現契約」 | [`WATCHLIST_AND_PORTFOLIO.md`](../../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md)「Paper 持倉健康／退出候選」說明只讀 UI 列、狀態、Paper identity 與 producer／consumer readback。 | 依 `PROJECT_SNAPSHOT.md`，Health 正式整合和完整工作包驗收仍待；舊 QA 不當目前通過。若無可核 read model，顯示 unknown／缺 receipt，不能把人工帳同股列 join 到 Paper。Owner：`app_module/position_health_transition_read_service.py`、`ui_qt/views/portfolio_view.py`。 |
| Supplements「Portfolio 背景刷新與一致性」、「Workbench／Scheduled Evidence 的機器狀態、stale 與 Retry」 | Paper refresh／readback 的使用者判讀在 [`WATCHLIST_AND_PORTFOLIO.md`](../../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md)；task／schedule 的 producer 狀態在 [`SCHEDULE_OPERATIONS_AND_MIGRATION.md`](../../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md) 與 [`BALDR_SCHEDULED_AUDIT_RUNBOOK.md`](../../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。 | 舊 run status／Task exit 不是新機現況或 consumer 成功；須核同一來源、snapshot、receipt 與 UI consumer。Owner：`ui_qt/views/portfolio_view.py`、`ui_qt/views/workbench_view.py` 及各 lane reader。 |
| Supplements「個人觀察清單：明示選擇」、「最新個人儲存位置決策」、COW／legacy migration 節點 | [`WATCHLIST_AND_PORTFOLIO.md`](../../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md)「私人儲存位置與收藏讀回」；搬機與設定另見 Machine Bootstrap Runbook。 | 根/mode 成對選擇；Personal store 缺失不 fallback，啟動不 migrate。舊個人實際路徑與曾選過的 DATA_ROOT 值是機器歷史，不當新機建議。Owner：`docs/01_architecture/current/data_storage_runtime.md`、`app_module/application_bootstrap.py`、`app_module/watchlist_service.py`。 |
| Supplements「人工 retention 決策與清理後驗證」 | Manual 連到 [`data_storage_runtime.md` 的現行 retention 邊界](../../01_architecture/current/data_storage_runtime.md#immutable-ml-retention-的目前檢視與核准邊界)；Research Lab 已明示一般使用者不可清理 artifact。 | 舊命令、archive/delete 決策與 QA 僅供歷史追溯。現在只有 `scripts/inspect_ml_storage_retention.py` 唯讀 metadata inventory；repo 沒有 destructive retention runbook，也沒有從 Manual 授權刪除。 |

## 首次安裝文件一致性

`FIRST_INSTALL_PROMPT.md` 與 `MACHINE_BOOTSTRAP_RUNBOOK.md` 一致：fresh／owner-migration 與 plan-only／configure／restore-and-enable 分別描述模式和授權；bootstrap-plan 是純計畫；roots 與資產有 owner 身份；不複製 venv、credentials、DPAPI 或 Codex auth；以完整具體清冊一次授權，在已授權範圍內逐項核對而不逐 Task 重問；舊 writer 未停、資產／authority 未核、或清冊外差異保留 pending／另行確認；設定完成、readback、自然 run 與產品 Gate 分開，並保留回滾路徑。

`INSTALL_GUIDE.md` 的 source GUI 建置步驟和 portable 指引是環境安裝入口，不會替代上述完整移機流程。此次補上排程不屬於 GUI 安裝步驟的說明，並將使用者導向唯讀核對與移機指南；Prompt／Runbook 本身未修改。

## 21 個 Windows task 靜態對照

以下逐項核對 `scripts/inspect_scheduled_task_registration.py` 的 `EXPECTED_TASKS`（程式行 29–50）與 `TASK_WRAPPER_PATHS`（行 53–74）、現行排程運維表及工作目錄檔案。21 列均為 `required=true`；表內 21 個 canonical wrapper 路徑均存在。標準時區欄是目前註冊契約／文件基準；checker 的 19 個 Pacific `schedule` 字串本身只寫頻率和鐘點，沒有宣告 timezone。實際新機 XML、offset、principal、enabled 與 `NextRun` 仍需讀回。

| 完整 Task ID | `EXPECTED_TASKS.schedule`／時區基準 | `TASK_WRAPPER_PATHS` canonical wrapper | 靜態比對 |
|---|---|---|---|
| `baldr-data-update-quick-daily` | `DAILY 04:20` · Pacific local | `scripts/scheduled/run_daily_data_update_quick.cmd` | ID、時間與 wrapper 相符 |
| `baldr-official-market-events-daily` | `DAILY 04:50` · Pacific local | `scripts/scheduled/run_official_market_event_backfill.cmd` | ID、時間與 wrapper 相符 |
| `baldr-data-freshness-check-daily` | `DAILY 05:00` · Pacific local | `scripts/scheduled/run_daily_data_freshness_check.cmd` | ID、時間與 wrapper 相符 |
| `baldr-ml-raw-pit-refresh-daily` | `DAILY 05:05` · Pacific local | `scripts/scheduled/run_ml_raw_pit_refresh.cmd` | ID、時間與 wrapper 相符 |
| `baldr-recommendation-snapshot-daily` | `DAILY 05:10` · Pacific local | `scripts/scheduled/run_recommendation_snapshot.cmd` | ID、時間與 wrapper 相符 |
| `baldr-evidence-pipeline-dry-run-daily` | `DAILY 05:15` · Pacific local | `scripts/scheduled/run_evidence_pipeline_dry_run.cmd` | ID、時間與 wrapper 相符 |
| `baldr-ml-promotion-evidence-daily` | `DAILY 05:17` · Pacific local | `scripts/scheduled/run_ml_promotion_evidence.cmd` | ID、時間與 wrapper 相符 |
| `baldr-ml-promotion-authority-daily` | `DAILY 05:18` · Pacific local | `scripts/scheduled/run_ml_promotion_authority.cmd` | ID、時間與 wrapper 相符 |
| `baldr-ml-allocation-copilot-daily` | `DAILY 05:20` · Pacific local | `scripts/scheduled/run_ml_allocation_copilot.cmd` | ID、時間與 wrapper 相符 |
| `baldr-decision-evidence-capture-daily` | `DAILY 05:25` · Pacific local | `scripts/scheduled/run_decision_evidence_capture.cmd` | ID、時間與 wrapper 相符 |
| `baldr-ml-direct-chain-maintainer` | `DAILY 10:00` · Pacific local baseline | `scripts/scheduled/run_ml_direct_chain_maintenance.cmd` | checker／PowerShell 是 10:00；舊 CMD registrar 衝突，見下節 |
| `baldr-forward-outcomes-daily` | `DAILY 05:40` · Pacific local | `scripts/scheduled/run_forward_outcomes_daily.cmd` | ID、時間與 wrapper 相符 |
| `baldr-recommendation-calibration-learning-daily` | `DAILY 05:45` · Pacific local | `scripts/scheduled/run_recommendation_calibration_learning.cmd` | ID、時間與 wrapper 相符 |
| `baldr-recommendation-calibration-learning-banktaiwan-shadow-daily` | `DAILY 05:50` · Pacific local | `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.cmd` | 專用 lane；不在 aggregate subset |
| `baldr-paper-execution-eod-replay-daily` | `DAILY 06:00` · Pacific local | `scripts/scheduled/run_paper_execution_daily_isolated.cmd` | ID、時間與 wrapper 相符 |
| `baldr-pit-sector-membership-preopen-capture-daily` | `DAILY 16:00` · Pacific local | `scripts/scheduled/run_pit_sector_membership_preopen_capture.cmd` | ID、時間與 wrapper 相符 |
| `baldr-paper-portfolio-daily` | `DAILY 08:25 +08:00` · Asia/Taipei | `scripts/scheduled/run_paper_portfolio_daily.cmd` | checker 明列 offset；讀 XML 與 NextRun |
| `baldr-ml-allocation-forward-daily` | `DAILY 08:25 +08:00` · Asia/Taipei | `scripts/scheduled/run_ml_allocation_forward_daily.cmd` | checker 明列 offset；專用 XML，不在 aggregate |
| `baldr-formal-pit-sidecar-postcutoff-daily` | `DAILY 18:00` · Pacific local | `scripts/scheduled/run_formal_pit_sidecar_postcutoff.cmd` | ID、時間與 wrapper 相符 |
| `baldr-formal-input-producer-daily` | `DAILY 21:25` · Pacific local | `scripts/scheduled/run_formal_input_producer_daily.cmd` | ID、時間與 wrapper 相符 |
| `baldr-v2-2-weekly-collection` | `WEEKLY SUN 18:00` · Pacific local | `scripts/scheduled/run_v2_2_weekly_collection.cmd` | ID、週期與 wrapper 相符 |

## 平台與驗收界線

- **Windows Task Scheduler：**上表 21 個 Windows task。checker 及登記器各有範圍限制；Aggregate registrar 不含 ML forward 專用 XML，也不含 BankTaiwan recommendation shadow。`source`／`portable-gui` 是 GUI runtime 選擇，不代表排程 action 可切成 EXE。
- **本機 Codex heartbeat：**排程指南文件化兩個唯讀 heartbeat：每日 `America/Los_Angeles` 05:30 晨報與 06:20 晚間／Paper 報告。它們不在 21 個 Windows task 中，也不啟動 producer。實際 target thread、cadence、狀態和 model 要在 Codex 端讀回。
- **本機 Codex cron／雲端排程：**平台與 owner 分開盤點；本機未見不代表雲端不存在。不得用 Windows 21-task 查詢替代另一平台的讀回。
- **兩個 offset 任務：**Taipei 08:25（UTC 00:25）換算為 PDT 前一日 17:25／PST 前一日 16:25。這是固定時刻換算，不是 seasonal Task QA 或自然觸發證據；新機要核 Task XML offset 和實際 UTC／本地 `NextRun`。自然 run 尚未驗收。

## 發現的 trigger 衝突與未完成核驗

`register_baldr_scheduled_tasks.cmd` 的 dry-run 摘要和 `/Create` 呼叫仍把 `baldr-ml-direct-chain-maintainer` 設成 DAILY 05:30；`inspect_scheduled_task_registration.py` 的 `EXPECTED_TASKS` 與 `register_baldr_scheduled_tasks.ps1` 預設均為 DAILY 10:00。文件只把 10:00 當目前靜態基準，並已明示舊 `.cmd` 不作移機註冊入口。此次未改 scheduler runtime，未執行任何 registrar，也未聲稱此舊腳本已修復。

PowerShell helper 的 `DryRun` 只列所選 task spec；未讀取／比較完整 desired-versus-observed 清冊，不能當成 full diff 或冪等證據。移機前先唯讀盤點、逐項審閱完整差異並確認 owner 對清冊的整體授權；只在其明確 scope 內按適用的 PowerShell／dedicated registration 路徑操作，之後精確 readback。若發現清冊外或高風險差異，先停相應範圍。

`register_baldr_scheduled_tasks.ps1` 是 aggregate subset；個別 Windows task 專用 XML／registrar 和兩個 Codex heartbeat 仍須各自處理。2026-10-09 QA 所記四個 `pythonw.exe → run_scheduled_cmd_hidden.py → CMD` 與其餘 17 個 CMD action 是歷史 readback，不是新機／本機現況證明。新機需核 XML、wrapper／argv、working directory、principal、enabled、timezone、trigger／NextRun、根目錄、帳戶與依賴；設定完成不等於自然 run 或下游 consumer 驗收。

## 本次處置與未做事項

已更新 `INSTALL_GUIDE.md`、`SCHEDULE_OPERATIONS_AND_MIGRATION.md` 與 `scripts/scheduled/README.md`，把舊 `.cmd` trigger 衝突、PowerShell subset／dry-run 限制與精確 readback 要求放到使用者入口；排程運維表改成 21 個完整 ID、預期 schedule 和 canonical CMD 相對路徑。沒有修改 Prompt、Runbook、scheduler 程式、schema／map／tests；沒有執行 Python、pytest、mypy、compile、import、Task 註冊／啟用或 Codex automation 寫入。靜態路徑檢查確認本表 21 個 canonical wrapper 檔案皆存在。

### 來源定位

- `scripts/inspect_scheduled_task_registration.py:29-50`：預期 task ID、schedule 字串與 `required`。
- `scripts/inspect_scheduled_task_registration.py:53-74`：21 個 task 到 canonical wrapper 的 mapping。
- `scripts/scheduled/register_baldr_scheduled_tasks.cmd:114-116,200`：舊 Direct 05:30 摘要與 `/Create`。
- `scripts/scheduled/register_baldr_scheduled_tasks.ps1:8`：Direct 預設 10:00；`199-201`：DryRun 僅結束而不註冊；此檔不產出完整 host diff。
- `docs/07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md`：21-task 文件基準、兩個本機 heartbeat、時區轉換及 readback／自然 run 界線。
- `docs/07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md` 與 `FIRST_INSTALL_PROMPT.md`：scope 授權、清冊、bootstrap-plan、移機、安全與分階段驗收；本次只讀。
