# V4.2 每日推薦自動學習與受控調整 QA（2026-09-13）

## 驗收範圍

本輪驗收的是每日 recommendation calibration 的 research／shadow engineering loop，不是正式
推薦改權重、Formal promotion、broker execution 或 production evidence credit。驗收包含：

- bounded historical replay 與 walk-forward training；
- frozen challenger、immutable candidate capture、自然 maturity 與 same-sample authority gate；
- active champion monitor、自然 drift recheck 與 fail-closed rollback；
- source contract 的實際 rows digest／期間／symbol coverage、technical availability 與 corporate-action
  label-window gate；
- observed liquidity cost 的 after-cost target、獨立 null baseline 與 adopted active rows 的 cutoff
  隔離；
- 05:40 → 05:45 排程順序、Asia/Taipei official calendar、重跑冪等、recoverable failure 與 status receipt。

本次需求已授權的範圍，是完成 recommendation calibration 的每日自動學習、受控 shadow
調整／active monitor、自然 maturity、rollback 與 05:45 排程 wrapper／註冊定義。learning
loop 已整合至 canonical `dev`，並在取得明確部署批准後完成單一 learning task 的實機註冊；
這是既有 learning scope 的部署步驟，不代表 broker execution、正式 Recommendation／Portfolio
allocation promotion、正式推薦權重變更或 production evidence credit 已獲准。

## 安全與資料邊界

`scripts/scheduled/run_daily_recommendation_learning.py` 對正式 SQLite 使用 `mode=ro`／
`PRAGMA query_only=ON` 的 provider；輸出只寫專用的
`RECOMMENDATION_LEARNING_OUTPUT_ROOT/recommendation_learning/`。candidate、
active capture、evidence、authority receipt 與 pointer 均綁定 feature／availability、model／
dataset／policy／transform lineage。歷史 replay 只可作 training data，不能取得 natural forward
evidence credit；自然 evidence 必須由當日 capture 與之後可得的市場 close source 產生。active monitor
與 challenger 分開保存；同日新 maturity 若使 active model drift 或 source health 失敗，runner 可在
同一次 main run 立即 rollback。

本輪 P1 root contract 修正後，正式預設 `DATA_ROOT=D:\Min\Python\Project\FA_Data` 對應
`RECOMMENDATION_LEARNING_OUTPUT_ROOT=D:\Min\Python\Project\FA_Data_Shadow`，因此實際
learning artifact 位於 `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\`，不會
落在 formal `DATA_ROOT` 內。自訂專用 root 必須是絕對路徑且位於 `DATA_ROOT` 外；一般
`OUTPUT_ROOT` 保留給既有產品／scheduled snapshot，不作 learning root fallback。scheduler、
`DailyRecommendationLearningRunner`、read-only calibration consumer 與 Workbench 都使用同一
resolver；不安全路徑會輸出 `recommendation_learning_output_root_invalid` 並停止。

source contract 不以宣告的 `verified` bool 為充分條件。實際驗證包含 requested symbols 的 canonical
source-row digest、coverage／period、schema／source table、technical feature builder 實際使用 row
的 `available_at <= decision`，以及 corporate action factor／availability／label-window。raw label
window 若遇未被 adjusted-price custody 覆蓋的 non-unit corporate action，受影響列保守排除並保留
blocker。after-cost 只採可追溯 `evidence_outcomes.liquidity_cost_bp`；缺成本時 target 與 consumer
after-cost projection 皆為 missing，成本存在時才使用具名獨立 null baseline。adopted active model
的 matured post-adoption rows 需通過 current identity／receipt 且 `label_available_date <= training_as_of`，
才進下一輪 training。

## 自動化端到端回歸

主 E2E 測試以 `main(argv)` 驗證實際 orchestrator，而非預先傳入 `drift_status`、`emergency` 或
final evidence。只替換測試 clock、read-only provider／feature builder 與 isolated SQLite source，
讓每日 capture → 多日 maturity → A adopt → B 建立 → A active degradation → 同日 rollback 完整發生。
測試也驗證 after-cost 成本存在時會產生 after-cost training／consumer projection，沒有成本時保持
`None`；source contract fixture 使用實際 canonical digest 並覆蓋 technical `available_at`、corporate
action no-op rows 與 evidence cost rows。

## P1 root contract 回歸

初版 default path 會把一般 `OUTPUT_ROOT`／`DATA_ROOT` 下的目錄誤當成 learning artifact root，
使 `SafeShadowModelArtifactLoader` 在正常 config 下直接拒絕候選。修正後由
`app_module/recommendation_learning_paths.py` 集中解析：正式預設為
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning`；scheduler、runner、consumer
與 Workbench 共用同一 root。整合測試在未設定專用 env、使用正常 `TWStockConfig` 時，實際寫入
candidate，並驗證 loader 回傳 `shadow_model_ready`、consumer pointer 與 Workbench latest status
都指向同一 root；另驗證 explicit root 落在 `DATA_ROOT` 內時，resolver 與 CLI 都以清楚的
`recommendation_learning_output_root_invalid` fail closed。wrapper 改以
`RECOMMENDATION_LEARNING_OUTPUT_ROOT` 傳入專用 root，不改動一般 `OUTPUT_ROOT` 契約。

## 實機部署與有界入口驗證（2026-09-13）

canonical `dev` 已完成 fast-forward integration（包含 `a2e3797f`、`bee59b9e`、`8cde901f`、
`c46c6039`、`b146abe8` 與 recoverable retry compatibility 修正）；`main` 未變更，也未 push。主機 `DESKTOP-4663E62` 的
Windows timezone 是 `Pacific Standard Time`；兩個 Task Scheduler trigger 都以 deployment host
local 05:40／05:45 執行，且 runner 以 `Asia/Taipei` clock 與 official calendar 判定資料日期。

以提升權限唯讀回讀註冊結果：

- `baldr-forward-outcomes-daily` 已存在、Enabled、Daily 05:40；Action 是
  `cmd.exe /c "C:\Projects\PythonProjects\technical_analysis\scripts\scheduled\run_forward_outcomes_daily.cmd"`，
  2026-09-13 05:40 的 `LastTaskResult=0`，NextRunTime 為 2026-09-14 05:40。
- `baldr-recommendation-calibration-learning-daily` 只以精確 task registration 建立／更新，沒有呼叫
  aggregate `RegisterAll`；Enabled／Ready、Daily 05:45，XML StartBoundary 為無 offset 的
  `2026-09-13T05:45:00`，Action 是
  `cmd.exe /c "C:\Projects\PythonProjects\technical_analysis\scripts\scheduled\run_recommendation_calibration_learning.cmd"`，
  MultipleInstances=`IgnoreNew`，NextRunTime 為 2026-09-14 05:45。初始 LastTaskResult=`267011`
  (`0x41303`，尚未執行)，因此下列 CLI bounded run 是獨立正常入口驗證，不冒充 task 已執行。
  XML 沒有 `TimeZone` 或 synchronize-across-time-zones 設定，`schtasks` 讀回為 Daily local
  05:45；因此驗收契約是 host-local 05:40 forward → host-local 05:45 learning，沒有把 learning
  trigger 固定成某個 UTC 時刻；此處只依無 offset local trigger 與目前排程回讀，不延伸推導未回讀的
  DST 觸發結果。
- 預設 shadow root 是 `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\`；
  由 resolver 建立的 root 位於 formal `D:\Min\Python\Project\FA_Data` 外。正式 SQLite 讀取仍由
  `MLHistoricalSnapshotProvider:sqlite_mode_ro_query_only` 執行；未建立任何 formal DB writer。

正常 canonical entrypoint（沒有 `--skip-capture-current`、沒有注入 source contract／mature data）：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_daily_recommendation_learning.py `
  --decision-date 2026-09-13 `
  --history-start-date 2024-01-01 `
  --max-decision-dates 5 `
  --fixed-round-trip-cost-bp 50
```

實跑 exit code=`0`。它從既有 `scheduled_rec_20260913_051004.json` 讀到原生
`證券代號` symbol source：`1528,1558,1560,1569`；這也回歸了正式 snapshot 的中文 identifier
欄位，不再要求人工補 symbols。receipt／latest status 位於
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\`，結果為：
`status=skipped_no_data`、`decision=retain_current`、`decision_reason=no_new_matured_or_historical_rows`、
`recoverable=true`、`formal_order_allowed=false`、`shadow_only=true`。官方 calendar 在 receipt 的
`decision_calendar` 明確回報 `Asia/Taipei / official_calendar_is_trading_day=false /
official_calendar_reason=weekend_closed`；live capture 使用正常預設開關，因 requested historical
date 不是當下 Taipei date 而回 `status=skipped`、`reason=capture_current_requires_current_asia_taipei_date`。
這不是以 skip flag 代替日曆驗證；calendar check 實際執行並保留 weekend blocker。run receipt 是
可恢復 attempt：`runs/2026-09-13/attempts/attempt-3e40ba4539442809b4a05c2a.json`，沒有 candidate、
natural evidence 或 promotion。

另以真正的 canonical wrapper 做無日期覆寫、無顯式 symbols、預設 `max-decision-dates=100` 的入口驗證：

```powershell
& .\scripts\scheduled\run_recommendation_calibration_learning.cmd
# wrapper 的 governed Python exit code: 2
```

當時本機為 2026-09-13 11:58 PDT，runner 的 Asia/Taipei decision date 已是 2026-09-14，
但 `scheduled_rec_20260914_*.json` 尚未由前置 recommendation snapshot task 產生。因此 wrapper
正確輸出 `symbol_source=unresolved`、空 symbols、`symbol_cohort_preflight_failed:ValueError`，
不做 universe discovery、不進 replay／capture，也不偽造 snapshot；`latest_status.json` 為
`status=failed_dependency`、`decision=retain_current`、`finalized=false`、`recoverable=true`、
`formal_order_allowed=false`、`shadow_only=true`，且 `recovery_policy=recoverable_attempt`。
失敗會回傳 exit 2 供排程觀測，但不會永久鎖定當日；同一 decision date 的 snapshot 到齊後可直接
重跑。先前曾產生的 `run_receipt-emergency-rollback.json` 原樣保留，SHA-256 為
`406DB4323B76FB82597F2AB793CD758E821983781D746EF4D0D86E4256DB0BD3`，active pointer 仍為
`rule_only`；舊 recoverable attempt 與新版 next-step schema 衝突時，runner 會保留舊 receipt，另建
不可覆寫的 retry attempt，不會使 wrapper crash。新增 main 級測試也以真實 runner／authority receipt、
rule-only pointer 與 220 筆 historical samples 證明同日 snapshot 出現後可建立 candidate/pending。

同一個 shared resolver 回讀確認：consumer pointer 是
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\recommendation-calibration-active-pointer.json`，
Workbench 讀取同一個 `latest_status.json` 且 diagnostics 為空；formal `DATA_ROOT`、generic
`OUTPUT_ROOT` 與 shadow artifact root 沒有混用。剩餘 Gate 仍是 production source contract、
technical publication／PIT availability、corporate-action adjustment custody、自然成熟 outcomes
與 observed liquidity cost。

## 本輪命令與結果

使用共享 runtime：

```powershell
C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe -m pytest tests\test_recommendation_historical_replay.py tests\test_recommendation_calibration_training.py tests\test_daily_recommendation_learning_loop.py -q -o addopts=
C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe -m pytest tests\test_recommendation_historical_replay.py::test_verified_source_contract_unlocks_only_traceable_cost_and_source_gates -q -o addopts=
C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe -m pytest tests\test_daily_recommendation_learning_loop.py::test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags -q -o addopts=
C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe -m pytest tests\test_daily_recommendation_learning_loop.py::test_default_config_uses_external_shared_shadow_root_and_loader_reads_candidate tests\test_daily_recommendation_learning_loop.py::test_recommendation_learning_root_rejects_formal_data_root_descendant tests\test_daily_recommendation_learning_loop.py::test_daily_cli_reports_invalid_learning_root_without_starting_replay tests\test_recommendation_service_calibration_integration.py::test_default_recommendation_service_has_read_only_consumer_from_dedicated_shadow_pointer tests\test_workbench_source_service.py::test_workbench_source_service_reads_daily_learning_latest_status_as_read_only_evidence tests\test_scheduled_cmd_scripts_exist.py::test_recommendation_learning_cmd_requires_governed_python_interpreter -q -o addopts=
```

實際結果如下：

- 三個核心測試檔：`25 passed`；source-contract 指定測試：`1 passed`；main orchestrator
  E2E：`1 passed`。
- P1 root contract regression：default config／loader／consumer／Workbench／wrapper 與 invalid-root
  CLI 測試全部通過（`6 passed`）；合併受影響檔案回歸為 `28 passed`。
- 受影響整合回歸（含 DTO／service／scheduled 靜態契約）：`107 passed`。
- UpdateView workbench：`81 passed`；`qa_validate_update_tab.py`：`25 passed`、`4 skipped`。
- mypy：`Success: no issues found in 600 source files`；變更／新增 Python `py_compile` 通過；
  quant guard 的 float 與 look-ahead 檢查均通過；金融邊界／單位／ML dependency guard：`50 passed`。
- review fix 後，兩個 commit 涉及的 24 個 production／script Python modules 以完整 imports
  mypy 通過；所有本次修改／新增 Python 檔案 `py_compile` 通過；合併 replay／training／learning／
  consumer／Workbench／scheduled 受影響回歸為 `41 passed`。先前 `recommendation_historical_replay.py`
  的 3 個 assignment 型別錯誤已修正，未以 skip-import 掩蓋。

scheduled 全量回歸（21 個 `test_scheduled_*.py` 檔）為 `164 passed, 10 failed`。失敗項目與原因
均為隔離驗證環境限制或既有 baseline，沒有把 skipped 當成 passed：

- `test_scheduled_paper_execution_wrapper.py::test_scheduled_wrapper_uses_queue_without_fixed_recommendation_env`：本 worktree 沒有 `.venv`，舊 paper wrapper 退回 PATH `python`，子程序缺 `pandas`；本輪新增 learning wrapper 已改為明確 governed interpreter，並以 canonical runtime 直接驗證。
- 上述 paper wrapper test 已在 canonical `.venv` 重新單測驗證：`1 passed`；其餘 scheduled 全量失敗項仍維持下列隔離 calendar/cache baseline 說明。
- `test_scheduled_data_update_runner.py::test_scheduled_target_weekday_uses_today_on_weekday`、
  `test_scheduled_data_update_runner.py::test_scheduled_target_weekday_falls_back_to_friday_on_weekend`、
  `test_scheduled_data_update_runner.py::test_weekday_window_includes_requested_number_of_weekdays`、
  `test_scheduled_data_update_runner.py::test_quick_update_publishes_running_before_work_and_terminal_metadata`、
  `test_scheduled_data_update_runner.py::test_quick_update_reports_candidate_step_when_candidate_path_is_configured`、
  `test_scheduled_data_update_runner.py::test_quick_update_releases_capacity_reservation_after_service_exception`：隔離 worktree 沒有 official calendar cache，sandbox 網路無法取得 TWSE holiday schedule，回報 `twse_holiday_schedule_unavailable`；套用既有 canonical calendar cache 重驗後共 `20 passed`。
- `test_scheduled_data_freshness_probe.py::test_freshness_probe_degrades_when_tpex_file_missing_for_latest_daily_date`、
  `test_scheduled_data_freshness_probe.py::test_freshness_probe_degrades_when_latest_quick_update_failed`、
  `test_scheduled_data_freshness_probe.py::test_freshness_probe_degrades_when_latest_quick_update_status_is_stale`：同一 official calendar cache／網路限制；套用既有 canonical calendar cache 後通過。

排程 registration script 的 `-Mode DryRun` 仍通過；實機部署則只操作上述精確 learning task，
保留既有 forward task 與其他排程不變。

## 正式資料 bounded read-only run

執行日為 2026-09-13（Asia/Taipei，週日）。輸入為正式
`D:\Min\Python\Project\FA_Data\sqlite\twstock.db`，明確 symbols `1101,2330`，history
2024-01-01 起、replay 2024-01-02～2026-09-13、latest 80 decision dates、fixed round-trip cost
50 bp；輸出為隔離的 `real_daily_learning_v3` 目錄。結果：160 samples、80 selected decision
dates、200 feature rows seen、40 rows skipped；`training_data_eligible=true`，但
`forward_evidence_eligible=false`、`formal_candidate_eligible=false`。第一次探索性執行曾帶有
`--skip-capture-current`，其 `not_requested` 只代表 caller 停用 capture，不作為日曆功能證據。
隨後沿用同一 frozen candidate／既有 daily receipt，以正常預設入口（省略該 flag）重跑；
status 顯示 `run.idempotent_replay=true`、`live_capture.status=skipped`、
`reason=non_trading_day_official_calendar`、`calendar_reason=weekend_closed`、
`trading_calendar_source=OfficialTradingCalendar`、`official_calendar_is_trading_day=false`。
因此本次才確認週日 skip 且沒有重訓或偽造週末 capture。candidate 保持 pending／retain current，
沒有 matching natural capture／matured evidence。

正式來源仍有以下外部缺口：

- historical replay 不能代替 natural forward evidence；
- production source contract／technical publication time 尚未可驗證；
- corporate-action source／adjustment custody 尚未可驗證；
- observed liquidity cost 缺失，after-cost target／model 維度保持 missing。

因此本輪沒有 formal promotion、production recommendation change、evidence DB write 或 broker
action。config log 在正式 data root 缺少寫入權限時只退回 console logging；這不影響 provider 的
read-only run，但屬主機操作上的可觀測性提醒。

## 未完成 Gate

要從 shadow-only 進入任何正式 promotion，仍必須由 owner 提供可核驗的 production source
contract、technical publication／PIT evidence、corporate-action adjusted-price custody、
具 unique-key 且可重算的 natural matured outcomes 與 observed liquidity cost，並完成正式
Formal／Advice／production allocation review。這些是正式 production／allocation 的外部 Gate，
不是本次已授權 learning loop 的重新批准條件。本輪工程不自行補造這些外部事實；learning
task 已依批准的 canonical wrapper 啟用，後續仍只保留 shadow／fail-closed 邊界，未啟用任何
正式 promotion、broker 或 production evidence credit。
