# BALDR Windows Scheduler 與 Codex automations 唯讀盤點（2026-09-25）

## 範圍與收據

本報告記錄 2026-09-25 Pacific 時區的只讀盤點。沒有啟動、停止、註冊、啟用、停用或修改 Windows task；沒有觸發 Codex automation；沒有執行資料更新、formal producer、Paper writer、ML rebuild／promotion，也沒有讀寫資料庫。

- Task Scheduler 查詢時間：`2026-09-25T20:56:47.9763771-07:00`；時區 ID `Pacific Standard Time`，當次 UTC offset `-07:00`。
- 查詢方式：`Get-ScheduledTask`、`Get-ScheduledTaskInfo`、`Export-ScheduledTask`。初次預設 sandbox 查詢被 Windows 拒絕，後以核准的唯讀 elevated query 完成；沒有執行任務。
- Windows task 總數 223；名稱符合 `baldr-*` 的任務 21 個。
- 21 份 task XML/settings 備份：`C:\Users\archi\AppData\Local\Temp\baldr_scheduler_final_ro_b5ea86b8\`。task XML 路徑與逐份 SHA-256 都在機器清冊。
- 結構化 Scheduler inventory：[BALDR_SCHEDULER_RECONCILIATION_20260925.json](BALDR_SCHEDULER_RECONCILIATION_20260925.json)，SHA-256 `C95D745F503D730744026431664BDDD3B3FE114C85988F7520A459820CDC0B20`。
- Codex automation 清冊：[BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json](BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json)，SHA-256 `0D126E1D1D6C1498DA0773741528F3C840E999BE6E2426C6FBCC3491325DC148`；唯讀 48 個 `automation.toml`，未直接修改 TOML，也未讀其他 Codex 設定或 secret config。

## Windows task 設定

21 個 task 目前皆為 `Ready`、`Enabled=true`；principal 都是 `archi`／Interactive／Limited。所有 action 均為 `cmd.exe /c` 呼叫 repo 內 `scripts/scheduled/*.cmd` canonical wrapper，wrapper 路徑與當次 SHA-256 均在 JSON。20 個 action 的 Task Scheduler `WorkingDirectory` 未設值；只有 `baldr-ml-allocation-forward-daily` 明設 repository root。wrapper 會自行切到 repository root。

Trigger 與共通設定：20 個 daily，1 個 weekly Sunday 18:00；時間按 `Pacific Standard Time` 解讀。所有 task 都是 `MultipleInstances=IgnoreNew`、restart count 0、沒有 scheduler retry interval；`StartWhenAvailable=false`、idle/network/wake 限制皆 false，`AllowDemandStart=true`。Execution timeout 分布為 `PT72H` 16 個、`PT2H` 2 個、`PT1H` 3 個。Action、trigger 的完整 XML 欄位以及設定值以機器清冊為準。

Task XML 沒有獨立環境變數區塊；環境預設由 wrapper 設定或繼承互動使用者環境。JSON 逐項保存 wrapper 宣告的環境變數與有效 CLI command line；任何可能帶 token／key／password 的值已遮蔽。以下狀態列按 Scheduler 當次執行與可讀 artifact 分開判斷：`LastTaskResult=0` 僅代表程序 exit code。

| Pacific 排程 | Task | Scheduler 最近一次結果 | 同次/最新 producer readback |
|---|---|---|---|
| 04:20 daily | `baldr-data-update-quick-daily` | 9/25 04:20，`0x00000001` | D 槽 `data_update_quick/latest_status.json` 目前是 05:45 recommendation-learning 子流程寫入的 run `20260925-60944`，狀態 `failed`；不是 04:20 task 的同次收據。內容顯示 technical recompute 無更新；`writes_market_data_db=true`、`writes_evidence_db=false`。 |
| 04:50 daily | `baldr-official-market-events-daily` | 9/25 04:50，`0x00000000` | `official_market_events/latest_status.json` 為 `published`；recommendation-learning 以此作為來源 receipt。 |
| 05:00 daily | `baldr-data-freshness-check-daily` | 9/25 05:00，`0x00000000` | `data_freshness/latest_status.json` 為 `degraded`；列出 quick update 失敗及 fundamental current-observed period warnings。此 receipt 由 Evidence dry-run 與 Paper dependency gate 讀取。 |
| 05:05 daily | `baldr-ml-raw-pit-refresh-daily` | 9/25 05:05，`0x00000000` | `ml_raw_pit_refresh/latest_status.json` 為 `blocked_upstream_not_ready`。 |
| 05:10 daily | `baldr-recommendation-snapshot-daily` | 9/25 05:10，`0x00000000` | `recommendation_snapshot/latest_status.json` 為 `passed`，result `rec_dabcb6a3fd3f4abfab5e6c3cac32b09e`；寫入 research Recommendation result，不寫 evidence DB。learning 與 morning report 讀此結果。 |
| 05:15 daily | `baldr-evidence-pipeline-dry-run-daily` | 9/25 05:15，`0x00000002` | `evidence_pipeline_dry_run/latest_status.json` 為 `failed`、`exit_code=2`、`dry_run=true`、`writes_evidence_db=false`。Gate/report 有 blockers；不是 production evidence write。 |
| 05:17 daily | `baldr-ml-promotion-evidence-daily` | 9/25 05:17，`0x00000000` | `ml_promotion_evidence/latest_status.json` 為 `blocked`；下游 authority 沒有相容 evidence pointer。 |
| 05:18 daily | `baldr-ml-promotion-authority-daily` | 9/25 05:18，`0x00000000` | `ml_promotion_authority/latest_status.json` 為 `skipped_evidence_unavailable`；`authorization_created=false`、`formal_oos_allowed=false`、alpha 0。 |
| 05:20 daily | `baldr-ml-allocation-copilot-daily` | 9/25 05:20，`0x00000000` | `ml_allocation_copilot/latest_status.json` 為非交易日 skip；formal OOS=false、alpha 0。 |
| 05:25 daily | `baldr-decision-evidence-capture-daily` | 9/25 05:25，`0x00000000` | `decision_evidence_capture/latest_status.json` 為 `skipped_non_trading_day`。 |
| 05:30 daily | `baldr-ml-direct-chain-maintainer` | 9/25 05:30，`0x00000000` | `ml_direct_chain_maintenance/latest_status.json` 為 `blocked_insufficient_storage`；`formal_oos_allowed=false`。Task 仍啟用，本輪沒有停用或觸發。 |
| 05:40 daily | `baldr-forward-outcomes-daily` | 9/25 05:40，`0x00000000` | `forward_outcomes/latest_status.json` 為 `passed_with_warnings`；warning `legacy_incomplete_identity_skipped_without_backfill`，`writes_evidence_db=true`。此為既有排程 evidence writer；本輪只讀 status，未查 DB 或執行 writer。 |
| 05:45 daily | `baldr-recommendation-calibration-learning-daily` | 9/25 05:45，`0x00000001` | D 槽 Shadow learning receipt 為 `failed`，含 `technical_source_refresh_failed`、`recommendation_learning_failed`。同一 workflow 會呼叫 technical refresh 並更新與 04:20 共用的 quick-update `latest_status.json`，因此須用 run id/timestamp 區分。 |
| 05:50 daily | `baldr-recommendation-calibration-learning-banktaiwan-shadow-daily` | 9/25 05:50，`0x00000002` | BankTaiwan Shadow receipt 為 `failed_dependency`。 |
| 06:00 daily | `baldr-paper-execution-eod-replay-daily` | 9/25 06:00，`0x00000002` | Repo output 的 dependency gate receipt 為 `blocked`、`query_only=true`、未寫 source DB/files。原因包含上游 update/freshness、9/25 TWSE/TPEx source CSV 缺件；retry runner 未把資料不完整狀態當可交易候選。 |
| 16:00 daily | `baldr-pit-sector-membership-preopen-capture-daily` | 9/25 16:00，`0x00000002` | Rule source 與 PIT capture receipt 均為 `blocked`，原因 `runtime_config_expired`，formal OOS=false。 |
| 16:15 daily | `baldr-ml-allocation-forward-daily` | 9/25 16:15，`0xC000013A` | Task 被中止的結果碼；記錄本身無法辨認發起者或原因。最新可讀 forward receipt 觀察時間仍是 9/22，狀態 `blocked_child_exit`；不是同次 9/25 readback。 |
| 16:15 daily | `baldr-paper-portfolio-daily` | 9/25 16:15，`0xC000013A` | Task 被中止的結果碼；最新 repository portfolio receipts 的 decision date 是 9/22，非 9/25 同次結果。D 槽對應路徑不存在。 |
| 18:00 daily | `baldr-formal-pit-sidecar-postcutoff-daily` | 9/25 18:00，`0x00000002` | 同一 wrapper 依序執行 PIT sidecar 與 Paper event source capture；兩個 current receipts 均 `blocked`，原因 `runtime_config_expired`。未 refresh runtime config，也未重跑 producer。 |
| 21:25 daily | `baldr-formal-input-producer-daily` | 最近一次 9/24 21:25，`0x00000002`；下一次預定 9/25 21:25 | 最近一次 scheduler receipt 為 expired runtime config。盤點時 21:25 尚未到；沒有手動啟動。 |
| 週日 18:00 | `baldr-v2-2-weekly-collection` | 9/20 18:00，`0x00000000`；下一次 9/27 18:00 | 最近產物 `v2_2_weekly_collection_20260920.json` 為 `pending_human_review`、`write_intent=false`、`human_approval_required=true`。平日不應誤判為當日漏跑。 |

## Source → artifact → consumer readback

- Quick update 寫 market-data CSV/SQLite 並寫 `data_update_quick/latest_status.json`；freshness、Evidence dry-run、Paper dependency gate 讀 status。05:45 learning 子流程也重用這個 latest pointer，故 04:20 Scheduler result 與最新 pointer 不能視為同一 run。
- Official market events 與 Recommendation snapshot 形成 learning 的上游輸入；snapshot status 持有 result ID、decision date、推薦數與 research-only write flags。Morning report 交叉比對 Scheduler last run 與 receipt timestamps。
- Evidence pipeline 是 `--dry-run`；status 指向 report/log 並明示 `writes_evidence_db=false`。Forward outcomes 是另一個既有排程寫入者，本次只從 `latest_status` 和 progress receipt metadata 讀回，沒有查詢其資料庫。
- ML raw PIT → promotion evidence → promotion authority 形成一條 fail-closed gate；當次 authority 無 authorization、formal OOS=false、alpha=0。Direct-chain maintainer 雖然 Scheduler exit 0，status 仍明確阻擋容量不足。
- Formal Rule source → PIT preopen capture → PIT sidecar → Formal input producer 的 status receipts 均保留；runtime config 已過期時為 blocked。排程 task 的存在或 `Ready` 不授權 refresh config、重跑或升級。
- Paper EOD retry runner 先讀 update/freshness status、target-date source files，再留下 dependency gate latest pointer 與 immutable attempt receipt。當次 query-only gate blocked，沒有寫 source DB/files。Paper portfolio 9/25 task 被取消，舊 latest result 不可當作當日 readback。
- V2.2 weekly artifact 僅進人工 review queue；`pending_human_review`、`write_intent=false` 不表示 accepted evidence 或 formal credit。

所有 25 個 artifact readback 的路徑、最後寫入時間、bytes、SHA-256、安全欄位與 consumer 關係均記在 JSON `artifactReadbacks`。其中沒有遺失的 listed receipt；兩個 0xC000013A task 與 stale Paper/ML results 仍明確標示「無同次 receipt」。

## Codex automation 現況與唯一提案

48 個 automation 中 3 個 `ACTIVE`、45 個 `PAUSED`。完整 ID、prompt、model、rrule、status、notification、runtime/destination/project 欄位都在獨立 JSON；本輪唯讀 TOML，未直接修改。

| ID | 現況 | 決策 |
|---|---|---|
| `baldr-scheduled-evidence-morning-report` | 05:30 America/Los_Angeles，既有目標 thread `01a08626-6d14-7350-8502-61ba8fc3aa30`；唯讀查四個每日 baldr tasks與週資料 | 保留原 prompt、日程與通知設定，不修改。 |
| `moomoo-200-risk-lab` | Moomoo 獨立風險實驗 | 本範圍外，不修改。 |
| `paper`（21:08 PDT inventory 快照） | 本地 RRULE 每日 06:20（本次 Pacific daylight time 對應台北 21:20）；原 prompt 用台北時間描述，DST 後須以實際 trigger 核對 | 當時唯一提案為保留 bounded 修復／測試／文件用途、重用 Luna Max 既有 agent、移除 stage／commit／push；明列 same-run typed result readback、Paper root/scope/nested schema 分層與 stale blocker 判讀。該快照提案尚未套用；後續管理工具更新見文末。正式 writer、evidence producer、rebuild、promotion 及 task/automation 變更仍需另行授權。 |

提案 before/after、原文及 rollback request 見 [BALDR_PAPER_AUTOMATION_PROMPT_PROPOSAL_20260925.md](BALDR_PAPER_AUTOMATION_PROMPT_PROPOSAL_20260925.md) 與 [BALDR_PAPER_AUTOMATION_UPDATE_REQUEST_20260925.json](BALDR_PAPER_AUTOMATION_UPDATE_REQUEST_20260925.json)。提案保留原 daily prompt 用途與 bounded repair 權限；只移除 stage／commit／push，並更新 Luna Max、same-run readback 和 schema/clock 判讀。本代理不呼叫 `automation_update`；Codex 管理操作由 root review/call。

## 建議與限制

Windows task action/account/trigger/timeouts/retry/overlap 均未發現可由本輪證據支持的最小修正，因此建議原樣保留。已啟用的 direct-chain maintainer、promotion authority、forward outcomes、formal input producer 等任務，維持其原設定；部分狀態 blocked、stale 或未授權，須按現有 fail-closed receipt 判讀，不能手動觸發或藉此重新訓練、promotion 或寫入。

不以 Scheduler `Ready` 或 exit 0 宣稱產品資料完整或 gate 通過；不重播 terminal 失敗、不刷新過期 runtime config、不建立新的 production evidence writer。前述「`paper` prompt proposal 仍待 root 審查／套用」只描述當時盤點狀態；後續套用與讀回見本報告末尾 current 狀態更新。

## P1：Paper preopen receipt 與自然觀測時鐘後續驗證

本節是本報告唯讀排程盤點之後的隔離程式契約驗證；沒有啟動或重播 Task Scheduler、Paper writer、formal producer 或 ML rebuild/promotion，也沒有讀寫正式 Paper／市場 SQLite。測試只建立全新的系統 TEMP root 與 pytest 暫存資料庫。9/22 最新 Paper status 沒有被改寫；它的原始 bytes 複製到受版控的測試 fixture，供唯讀契約回歸。

### Schema handoff

- Frozen source：`output/paper_execution_eod_replay/scheduled/paper_portfolio_isolated/latest_status.json`，5822 bytes，SHA-256 `8972FC031F95A0FBD3D52052C3047D68DB93210DA3C846A7E4B9A0F7E29C740C`。實際欄位依序是 root `paper-portfolio-daily-status.v1`、獨立 `isolated_scope_schema_version=paper-portfolio-daily-isolated-scope.v1`、nested `preopen_coverage.schema_version=paper-preopen-coverage.v1`；receipt status 是 `passed`、source/read safety flags 為 false。
- 原 reader 曾把隔離 scope version 當 root schema，因而拒絕這份已治理 receipt。現在 `app_module/ml_allocation_shadow_evidence.py` 對 canonical root 與獨立 scope version 分別要求 exact match；nested coverage 仍另外驗證。舊版 scope-as-root 僅在 `paper_daily_status_schema_supported` 明確驗證 producer、candidate-only 與完整 no-credit／隔離安全旗標時相容；任意或未治理 root、scope、coverage 皆拒絕。`scripts/run_daily_ml_allocation_derived_shadow.py` 的第二道 consumer gate同步核對 root、scope、原始 bytes hash 與 inline receipt。
- 日期、state／ledger paths、snapshot ID/date/relation、current state head hash、讀取期間 receipt hash、status、寫入契約、calendar、no-credit、no-broker 與未授權交易 flags 均保留原 gate。
- Frozen fixture：`tests/fixtures/paper_preopen_coverage_receipts/passed_20260922_latest_status.json`（歷史 fixture 現缺；保留以下原 bytes／SHA 證據，見[缺件登記](../09_archive/DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md#壞鏈處理)），5822 bytes；複製前後 raw bytes 相等，SHA-256 `8972FC031F95A0FBD3D52052C3047D68DB93210DA3C846A7E4B9A0F7E29C740C`。測試 reader 只解析 status；沒有開啟該 JSON 指向的 Paper state／ledger DB。
- 結果：15 passed、9 deselected。涵蓋 frozen exact bytes、canonical 兩層與 nested schema、bounded legacy 正例、無治理 root/scope/coverage、未受限 legacy、no-credit 變異，以及日期、路徑、snapshot、state hash、receipt-race 負例。收據：`C:\Users\archi\AppData\Local\Temp\prp1_f77fd1\schema-focused.log`，SHA-256 `35B2384E81894F28B45538EC50EE1C8049C3015C0F3CCA2100CF07B729808E70`。

### `emitted_at` append-clock

- `record_and_mature` 現在每次建立新 observation 時，在 append 前捕獲一次真實 UTC `emitted_at`；同一 clock 仍負責檢查自然 forward deadline。`decision_at` 保持原決策日 08:30，不以 append clock 改寫；不加入歷史回填，也不改 `promotion_day_credit_allowed=false` 或 maturity／promotion gate。
- synthetic 回歸證明：無 deadline 的 current append 寫入 clock；同 custody 重跑保留首筆 payload、hash 與 clock；不同 custody 的新 revision 記錄自己的新 clock；舊 immutable row 不被補填；late forward emission 仍 rollback 並拒絕。結果 4 passed、33 deselected。收據：`C:\Users\archi\AppData\Local\Temp\prcl_8220cb\clock-focused.log`，SHA-256 `CA69C727DB2B3A33A3379C150020EEDB811DCC4A62CADA49E1D1DCEF72391DD9`。

### 可重跑驗證

以下命令均以 PowerShell 執行，建立各自新的短 TEMP root；`PROFILE=test`，`TEMP`／`TMP`／`TMPDIR`、`DATA_ROOT`、`OUTPUT_ROOT` 指向該 root。兩個 pytest route 不執行 scheduler：

```powershell
$qaRoot = Join-Path $env:TEMP ('prp1_' + [guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$env:TEMP = $qaRoot; $env:TMP = $qaRoot; $env:TMPDIR = $qaRoot
$env:PROFILE = 'test'; $env:DATA_ROOT = Join-Path $qaRoot 'data'; $env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
$pytestBase = Join-Path $qaRoot 'p'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_daily_ml_allocation_derived_shadow.py -q -o addopts= --basetemp=$pytestBase -k 'outer_wrapper_accepts_only_receipted_preopen_state_writer_overlap or real_preopen_producer_and_inner_reader_authorize_current_state_overlap or outer_wrapper_blocks_invalid_preopen_receipt_variants or frozen_real_preopen_receipt_preserves_exact_bytes_and_schema_layers or reader_rejects_legacy_root_with_separate_scope_schema'
```

```powershell
$qaRoot = Join-Path $env:TEMP ('prcl_' + [guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$env:TEMP = $qaRoot; $env:TMP = $qaRoot; $env:TMPDIR = $qaRoot
$env:PROFILE = 'test'; $env:DATA_ROOT = Join-Path $qaRoot 'data'; $env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
$pytestBase = Join-Path $qaRoot 'p'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_ml_allocation_shadow_evidence.py -q -o addopts= --basetemp=$pytestBase -k 'collector_records_four_lanes_then_matures_all_four_horizons or collector_captures_actual_append_clock_without_forward_deadline or append_observation_does_not_backfill_legacy_immutable_clock or forward_deadline_rolls_back_slow_observation_emission'
```

後續 reviewer 指出 bounded legacy reader 尚未單獨拒絕「舊 root + 另一個 scope schema」；outer gate 原本會拒絕，但無法證明 reader 自身一致 fail-closed。現 reader 也要求 legacy scope 欄位缺席，並新增直接 reader negative test。修改後兩套受影響 suites 完整回歸：`63 passed in 2.62s`，exit 0。收據：`C:\Users\archi\AppData\Local\Temp\prfull_2a0d1a\paper-p1-two-suites.log`，SHA-256 `D1EF07B8D61587C03D95D1C52BE193EAFA1F220AC5AEF8B0CB4DE890A7EC7E4A`。另單獨直接 reader 負例為 `1 passed, 25 deselected`，log `C:\Users\archi\AppData\Local\Temp\prrdr_b4d30b\legacy-reader-focused.log`，SHA-256 `B099AF626B9CBBD92E6BCBF8FDB460E232E85CBA29DE6DC6EEBB0253E4088106`。

完整兩-suite route 的重跑命令：

```powershell
$qaRoot = Join-Path $env:TEMP ('prfull_' + [guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$env:TEMP = $qaRoot; $env:TMP = $qaRoot; $env:TMPDIR = $qaRoot
$env:PYTHONPYCACHEPREFIX = Join-Path $qaRoot 'pycache'
$env:PROFILE = 'test'; $env:DATA_ROOT = Join-Path $qaRoot 'data'; $env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
$pytestBase = Join-Path $qaRoot 'p'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/test_daily_ml_allocation_derived_shadow.py tests/test_ml_allocation_shadow_evidence.py -q -o addopts= --basetemp=$pytestBase
```

Static receipts：changed Python 四檔 `py_compile` exit 0（isolated pycache）；兩個 changed production source 的 scoped mypy `--follow-imports=silent` exit 0，`Success: no issues found in 2 source files`；四檔 `git diff --check` exit 0，僅回報既有工作樹 LF/CRLF 轉換提示。完整命令：

```powershell
$qaRoot = Join-Path $env:TEMP ('prstatic_' + [guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$env:TEMP = $qaRoot; $env:TMP = $qaRoot; $env:TMPDIR = $qaRoot
$env:PYTHONPYCACHEPREFIX = Join-Path $qaRoot 'pycache'
.\.venv\Scripts\python.exe -m py_compile app_module\ml_allocation_shadow_evidence.py scripts\run_daily_ml_allocation_derived_shadow.py tests\test_daily_ml_allocation_derived_shadow.py tests\test_ml_allocation_shadow_evidence.py
.\.venv\Scripts\python.exe -m mypy --follow-imports=silent --cache-dir (Join-Path $qaRoot 'mypy-cache') app_module\ml_allocation_shadow_evidence.py scripts\run_daily_ml_allocation_derived_shadow.py
git diff --check -- app_module/ml_allocation_shadow_evidence.py scripts/run_daily_ml_allocation_derived_shadow.py tests/test_daily_ml_allocation_derived_shadow.py tests/test_ml_allocation_shadow_evidence.py
```

mypy log：`C:\Users\archi\AppData\Local\Temp\prmy_ff8756\scoped-mypy.log`，SHA-256 `0C37C4158C91EF55C724BA017BF6465F26018199BADB08E3FF13F98ACDF056C2`；py_compile log 為空輸出、exit 0，路徑 `C:\Users\archi\AppData\Local\Temp\prpc_2a5405\pycompile.log`。

這些是隔離 contract／synthetic 測試證據，不等同 Windows Scheduler 新 run 或 9/22 receipt 的 live post-fix readback；下次既有排程的同次 `LastRunTime`／status `run_id`／decision date 對齊仍是 operational readback。該測試收據寫入時，程式切片仍待 cross/root review；其後獨立接受狀態見本報告 current 更新。沒有 stage、commit 或 push。

## 2026-09-26 current 狀態更新

### Paper source slice 與自然 run gate

- Paper root/scope/nested coverage schema、derived-shadow consumer gate 與 append-clock slice 已完成 cross/root 獨立複審，沒有 P1/P2；兩套受影響 suites `63 passed / 2.54s`，隔離 synthetic 合約證據接受。原凍結 fixture 5822 bytes，SHA-256 `8972FC031F95A0FBD3D52052C3047D68DB93210DA3C846A7E4B9A0F7E29C740C`。
- 此結果不等同下一次 Paper task 的 live same-run readback。成功仍要求 producer 輸出、consumer typed result、root/scope/nested schema、日期、來源 bytes/hash、snapshot、state 與 no-credit 條件在同一 run 對齊；失敗需保留具名 blocker。未重跑 task，未讀寫正式 Paper／market SQLite。

### Codex `paper` automation prompt 已套用

- Root 以 Codex automation 管理工具更新 prompt 並完成 readback，狀態 `APPLIED_AND_READBACK_VERIFIED`。prompt SHA-256 `86BB652A882031D2A72517579DC00395F43F23CAB7683E0C2FD0DB71A19A7DE3`；TOML after SHA-256 `9D7CADB0A63D9B87264A2BAD11B85C86321E329456CB6FB1EB2C5300AD468DF9`。
- readback 的 changed keys 僅 `prompt`、`updated_at`；automation 仍 ACTIVE，原 RRULE、target thread 與 notification null 保留。套用前 TOML 備份在 `C:\Users\archi\AppData\Local\Temp\baldr_paper_automation_preupdate_20260925\automation.toml`，SHA-256 `604D336B2037246A8938034EA21B1BA194B8848A9032BB36CE2181D46D1D152E`。尚無套用後的正常排程 run；TOML 不曾由本 agent 直接修改。

### Daily technical parse／partial failure slice

- 隔離 synthetic integration 已覆蓋真實 SQLite `daily_prices` TEXT alias 的讀取路徑：`2,150.00`／`2,270.00` 先經 canonical parser，再進 approved alias guard；stale/nonfinite 變異 fail closed 且不進 CSV fallback。quick runner 保留部分成功／失敗股票與具名錯誤分類。
- 四套受影響 suites `141 passed / 9.10s / exit 0`；pytest log `C:\Users\archi\AppData\Local\Temp\tp_final_f7f67a47\pytest.log` SHA-256 `0CBD09AA54F3BE715914B557AA7C21FA2BCF0E33EB009B6AD2771D832BC0C0E1`。`py_compile` 五檔 exit 0；scoped mypy 兩個 production files 0 errors；`git diff --check` exit 0。未執行 Scheduler 或正式資料 writer。
- 可重跑命令、temporary roots、全部 changed-file sizes/hashes 與隔離邊界見 [daily technical QA report](BALDR_DAILY_TECHNICAL_PARSE_DIAGNOSTIC_QA_20260925.md)。
