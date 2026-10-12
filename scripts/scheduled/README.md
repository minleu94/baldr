# baldr Scheduled Wrappers

此目錄放置 baldr Windows Scheduled Task 使用的 canonical wrappers、少數 dedicated registration／dispatch adapter，以及其呼叫的排程入口。這份文件提供穩定入口和 lane 導覽；逐次工程診斷及日期化 QA 已封存，不用來推定目前主機設定。

一般使用者由[排程運維與搬機指南](../../docs/07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)查看文件化 cadence 和移機流程；唯讀核對完整 21 tasks 用[全排程唯讀稽核 Runbook](../../docs/07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。新機第一次建置或 owner migration 看[機器啟動 Runbook](../../docs/07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md)。

## 執行與管理入口

| 目的 | 入口 | 範圍與注意事項 |
|---|---|---|
| 取得 baldr 新機盤點／計畫 | [`scripts/document_control.py`](../document_control.py) 的 `bootstrap-plan` | 只唯讀檢查並輸出 JSON 計畫；不設定 roots、不搬資料、不註冊或啟用 task。輸出與狀態看本機 `output/tasks/` 實際回報位置。 |
| 查目前 Windows task | [`scripts/inspect_scheduled_task_registration.py`](../inspect_scheduled_task_registration.py) | 唯讀盤點；拒絕／權限不足要標 `unknown`，不能把查詢失敗當 missing。 |
| Aggregate registration | [`register_baldr_scheduled_tasks.ps1`](register_baldr_scheduled_tasks.ps1) | 目前 PowerShell helper；只涵蓋其定義的子集，不是完整 21-task reconciliation。`-Mode DryRun` 只列所選 task spec，不讀取並比較完整 desired-versus-observed inventory，也不證明 writer 冪等。 |
| Dedicated registration | Paper、BankTaiwan、PIT handoff 等 lane 的個別 `register_*` wrapper | 各 lane 有自己的 identity、preflight、root 和保留契約；aggregate register 不代替個別核對。 |
| 查歷史工程背景 | [排程操作封存原件](../../docs/09_archive/documentation_productization_20261012/originals/scripts/scheduled/README.md) | 原有日期化 runtime／repair diary bytes；僅供追溯來源與舊 anchor，不是當前設定。 |

本文件和 registrar 不授予註冊、停用、啟用、手動觸發、改 principal、改 timezone、改 wrapper 或替換 source runtime 為 portable EXE 的權限。安裝 `baldr.exe` 也不會自動修改 Task Scheduler action。`dryrun`／preflight 的 side effects 要以實際 wrapper source／輸出界線核實，不應因名稱含 dry-run 就假定完全無寫入。

[`register_baldr_scheduled_tasks.cmd`](register_baldr_scheduled_tasks.cmd) 是舊批次入口，不作目前移機註冊入口：其 dry-run 摘要與 `schtasks /Create` 仍將 `baldr-ml-direct-chain-maintainer` 設為 05:30；checker `EXPECTED_TASKS` 與現行 PowerShell helper 的基準為 10:00。不要把兩個 registrar 當成等價版本。移機前先完成全清冊唯讀查詢與逐項 desired-versus-observed 差異審閱；PowerShell `DryRun` 不是完整差異報告，未核清差異前不要註冊。授權後只使用適用 lane 的現行 PowerShell／dedicated registration 路徑，並以精確 readback 確認 action、trigger、timezone、principal、enabled 與 NextRun。此文件沒有證明任何 registrar 的冪等性。

## Windows task wrapper 導覽

以下 mapping 與 2026-10-06 文件化的 21-task inventory 對齊。此清單是 repo 導覽，不是主機已註冊或自然 run 的證明；實際 trigger、action、working directory、principal、enabled 和 NextRun 請以 audit readback 核實。

| Lane | Wrapper | 用途／細節 |
|---|---|---|
| Quick 行情更新 | `run_daily_data_update_quick.cmd` | [資料與市場研究手冊](../../docs/07_guides/manuals/DATA_AND_MARKET_RESEARCH.md) |
| 官方市場事件 | `run_official_market_event_backfill.cmd` | append-only 官方事件來源；readback 需逐 child 核驗 |
| 行情 freshness | `run_daily_data_freshness_check.cmd` | 唯讀查行情和來源日期 |
| ML raw／PIT refresh | `run_ml_raw_pit_refresh.cmd` | freshness／revision gate 通過後發布 |
| Recommendation snapshot | `run_recommendation_snapshot.cmd` | [推薦與 Research Lab 手冊](../../docs/07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md) |
| Evidence pipeline | `run_evidence_pipeline_dry_run.cmd` | dry-run 和 production write scope 分別核驗 |
| Promotion evidence／authority | `run_ml_promotion_evidence.cmd`、`run_ml_promotion_authority.cmd` | 核同源 evidence、machine authority 和 lineage |
| ML allocation copilot | `run_ml_allocation_copilot.cmd` | 缺資格時保留 rule-only |
| Decision evidence | `run_decision_evidence_capture.cmd` | 核來源日期及 evidence identity |
| Direct／OOC chain | `run_ml_direct_chain_maintenance.cmd` | 基準 10:00 Pacific；不要沿用舊 05:30 trigger expectation |
| Forward outcomes | `run_forward_outcomes_daily.cmd` | 到期 outcome writer；未成熟價格保持 null |
| Recommendation learning | `run_recommendation_calibration_learning.cmd` | learning／calibration shadow lane |
| BankTaiwan learning shadow | `run_banktaiwan_recommendation_learning_daily.cmd` | 獨立 BankTaiwan lane；不在 aggregate registration 子集 |
| Paper EOD replay | `run_paper_execution_daily_isolated.cmd` | [觀察清單與持倉手冊](../../docs/07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md) |
| PIT sector preopen | `run_pit_sector_membership_preopen_capture.cmd` | 專用 capture／handoff identity |
| Paper Portfolio | `run_paper_portfolio_daily.cmd` | offset wakeup 後等待台北 08:30 guard |
| ML Allocation Forward | `run_ml_allocation_forward_daily.cmd` | 專用 XML／配置路徑；offset wakeup、08:30 cutoff、08:35 deadline；不在 aggregate 子集 |
| Formal PIT sidecar | `run_formal_pit_sidecar_postcutoff.cmd` | cutoff 後 sidecar／Paper event capture |
| Formal input producer | `run_formal_input_producer_daily.cmd` | Rule、Paper、PIT candidate handoff |
| V2.2 weekly collection | `run_v2_2_weekly_collection.cmd` | [Weekly Review Runbook](../../docs/07_guides/V2_2_WEEKLY_REVIEW_RUNBOOK.md) |

兩個文件化的 Codex operational heartbeat 分別為 Pacific 05:30 晨間 report 和 06:20 晚間／Paper report；它們是唯讀報告，不在此目錄的 Windows task wrapper 清單內，不啟動 producer。實際 automation target、模型、狀態仍需 Codex 端另行讀回。

## Runtime 與結果邊界

2026-10-09 的具名設定 QA 記錄四個 deployed task（Direct、Paper Portfolio、PIT sector preopen、ML Allocation Forward）使用 `pythonw.exe → run_scheduled_cmd_hidden.py --task <exact task> → canonical CMD`，其餘 17 個使用 canonical CMD action。新機需核 actual dispatcher mapping、argv、cwd，不把該 QA 當作新機驗收。

桌面 UI 可使用 source 或 portable GUI；schedule wrapper 仍依已核准的 canonical CMD／action 和原子程序列執行。`baldr.exe` 的單 script／module dispatch 不等於完整 CMD wrapper 語意，不能省略多段 child、環境、preflight、timeout、retry 或 flags。搬機時不複製 venv；按[機器啟動 Runbook](../../docs/07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md)重新建立 runtime 並核 paths。

每輪驗收沿同一 `task → producer → status → terminal/receipt → artifact → consumer` identity 鏈。Task Ready、exit 0、檔案存在或 latest mtime 不是自然成功證據；詳細 readback／time zone／cutoff／帳戶／DPAPI 邊界見[排程唯讀稽核 Runbook](../../docs/07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。
