# BankTaiwan 研究型推薦每日自動學習營運 QA

日期：2026-09-14

範圍：BankTaiwan electronic estimated-research cost lane、daily shadow learning、Task Scheduler wiring、receipt custody

執行主機時區：`Pacific Standard Time`（支援 DST）

決策日曆時區：`Asia/Taipei`

## 結論

BankTaiwan 研究型推薦學習 lane 已接到獨立的 Windows Task Scheduler task，並完成一次以持久化路徑執行的受控 run。此 lane 只做 source-bound recommendation learning、natural outcome evaluation 與 shadow gate；不送出 broker order，也不改動既有 05:40 forward-outcomes 或 05:45 legacy calibration task。

本次受控 run 的結論是 `completed_waiting_natural_maturity`，`retain_current`；沒有足夠的 natural forward evidence，因此沒有 adopt 或 rollback。這是可觀測的等待狀態，不是把缺少的 outcome 當成成功。

## 先行讀回的現有排程與新 task

在註冊前先讀取現有 task 的 action、trigger、重疊策略、執行上限與 next/last run：

| task | action | local trigger | MultipleInstances | ExecutionTimeLimit | 讀回結果 |
|---|---|---:|---|---|---|
| `baldr-forward-outcomes-daily` | `scripts/scheduled/run_forward_outcomes_daily.cmd` | 05:40 daily | `IgnoreNew` | `PT72H` | Ready；next `2026-09-15 05:40`；last `2026-09-14 05:40`；result `0` |
| `baldr-recommendation-calibration-learning-daily` | `scripts/scheduled/run_recommendation_calibration_learning.cmd` | 05:45 daily | `IgnoreNew` | `PT72H` | Ready；next `2026-09-15 05:45`；last `2026-09-14 05:45`；result `0` |

本次新增且單獨註冊的 task：

| 項目 | 讀回值 |
|---|---|
| task | `baldr-recommendation-calibration-learning-banktaiwan-shadow-daily` |
| action | `cmd.exe /c "C:\Projects\PythonProjects\technical_analysis\scripts\scheduled\run_banktaiwan_recommendation_learning_daily.cmd"` |
| trigger | DAILY 05:50，主機 `Pacific Standard Time` |
| Taipei 對應 | 20:50 PDT／21:50 PST；位於既有 05:10 snapshot、05:40 forward、05:45 legacy learning hooks 之後 |
| MultipleInstances | `IgnoreNew` |
| ExecutionTimeLimit | `PT2H` |
| StartWhenAvailable | `false` |
| 讀回狀態 | Ready；next `2026-09-15 05:50`；尚未執行，last `1999-11-30`；初始 scheduler result `267011` |

註冊前先執行 `register_banktaiwan_recommendation_learning_task.cmd dryrun`，確認 wrapper、路徑與 timezone；接著只執行該 script 的 `register`。沒有呼叫 aggregate registration，也沒有覆寫其他 task 的設定。現有排程的完整讀回仍可能包含其他 task 的既有 warning/failure，本 lane 不把它們誤報為前置條件已全部通過。

## 資料鏈與 custody

每日 task 的輸入／輸出邊界如下：

```text
既有 scheduled recommendation snapshot（05:10）
        │ 只讀、驗 hash、同決策日
        ▼
BankTaiwan wrapper（05:50；lock + calendar gate）
        │ 直接呼叫既有 run_daily_recommendation_learning.py
        │ 不重跑 technical／official／snapshot producer
        ▼
source contract → candidate freeze → daily capture → natural outcome
        │
        ▼
controlled shadow evaluation（adopt／rollback gate）→ outer operational receipt
```

本次實際使用的持久化路徑：

| 用途 | 路徑 |
|---|---|
| formal data root | `D:\Min\Python\Project\FA_Data` |
| BankTaiwan shadow lane | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan` |
| lane learning root | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning` |
| existing snapshot root | `D:\Min\Python\Project\FA_Data\output` |
| existing source custody root | `D:\Min\Python\Project\FA_Data_Shadow` |
| source SQLite | `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` |
| outer immutable receipts | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\scheduled\recommendation_learning_banktaiwan\runs` |

受控 run 的 source policy 是 `sqlite_mode_ro_query_only`；source artifacts 只讀，既有 snapshot reused，task 內沒有 technical 或 official refresh。source DB 在 run 前後的 size 為 `3,568,181,248` bytes，`LastWriteTimeUtc=2026-09-14T12:45:06.8888799Z`，未被本 lane 改寫。

## 實際受控 run receipt

外層 immutable receipt：

`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\scheduled\recommendation_learning_banktaiwan\runs\2026-09-14-attempt-001-a5751f3b9d91.json`

執行時間為 `2026-09-14T19:13:18-07:00` 至 `2026-09-14T19:13:45-07:00`。輸入 snapshot：

- path：`D:\Min\Python\Project\FA_Data\output\recommendation\runs\scheduled_rec_20260914_051003.json`
- file hash：`sha256:2d946a89ebdfe2b3ea66fa246b2fbfb2e685de4d02745db7b0f34eaf5aeb353c`
- verified eligible symbol：`1528`
- cohort hash：`sha256:5f4de77ffb404af27caedb511ac1779d959cb177f60ea6422a97481fbb45b6a2`

run identity：

- outer status：`completed_waiting_natural_maturity`
- outer reason：`natural_forward_evidence_receipt_missing`
- child status：`completed`
- child run：`daily-recommendation-learning:2026-09-14:scheduled-snapshot-5f4de77ffb404af2-efed573`
- candidate：`rec-cal-b48b793f35280ce0ff9d5109`
- experiment scope：`scheduled-experiment-fed573cce3809fb128a37fa0`
- run scope：`scheduled-snapshot-5f4de77ffb404af2-efed573`
- capture scope：`scheduled-capture-5f4de77ffb404af2-c73ad38fa8a5c`
- gate decision：`retain_current`
- gate reason：`natural_forward_evidence_receipt_missing`
- challenger pointer：`pending`；training cycle `1`
- natural outcome：`pending`，`no_matching_frozen_challenger_captures`，matured sample count `0`
- live capture：`skipped`，原因 `capture_current_requires_current_asia_taipei_date`；本次使用指定的過去決策日，沒有偽造當日 live capture

candidate root：

`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\runs\2026-09-14\scheduled-snapshot-5f4de77ffb404af2-efed573\candidates\rec-cal-b48b793f35280ce0ff9d5109`

source contract receipt：

`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\source_contract\2026-09-14\93aad1dab9fb8a2e\contract.json`

content hash：`sha256:93aad1dab9fb8a2ef14b04b1786285faafb2e7efee8cf94685785b204669ab34`。該 contract 的 price-up prospective input 可供未來 capture，但 formal technical source contract 與 corporate adjustment contract 尚未 verified；after-cost lane 另外受 observed liquidity/fill lineage 未成熟阻擋。因此本次沒有把研究估算升格為 observed cost 或正式績效。

## BankTaiwan 成本 lane 邊界

本次 run 固定使用：

- policy：`banktaiwan-electronic-order-v1`／`banktaiwan-electronic-order-2026-v1`
- policy estimate date：`2026-01-01`
- scenario：`banktaiwan-electronic-estimate`／`banktaiwan-electronic-estimate-2026-v1`
- scenario hash：`sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450`
- instrument／lot：`ordinary_stock`／`full_lot`
- research sizing：`1000` shares，僅為 configured reference order，非 user position、非 actual fill

此估算只包含 versioned commission／sell tax policy；slippage 未建模，liquidity cost 僅 diagnostic，缺少 observation 不等於零。broker fill、實際成交、真實交易與 real order 均不在本 task 範圍；`formal_order_allowed=false`、`shadow_only=true`、`broker_action=false`。

## 重疊、重試與冪等

- Task Scheduler `MultipleInstances=IgnoreNew`，wrapper 另有 create-only operational lock。
- Windows lock probe 使用 `OpenProcess`／`GetExitCodeProcess` 查詢 PID，不使用 `os.kill`；PID 範圍不合法、malformed、`AccessDenied` 或其他未知狀態均 fail closed。
- 只有明確判定 process 已結束的 PID 才可回收 stale lock；重疊 run 產生 `skipped_overlap`，不覆寫既有 durable receipt。
- 同一 decision date 與相同 input fingerprint 的 terminal run 重跑時只更新 latest projection，child 不會重複執行。
- failed dependency／timeout 可在下一個 scheduled invocation 以新的 attempt receipt 重試；不把前一個失敗 receipt 當成成功。

## QA 驗證

`tests/test_banktaiwan_recommendation_learning_operational.py`：`10 passed`（pytest cache permission warning 不影響結果）。測試涵蓋：

- 同 fingerprint 不重複 child、retry 產生新 attempt
- overlap lock、non-trading-day skip
- child command 直接繫結既有 runner、BankTaiwan cost identity、separate lane/source/snapshot roots
- dedicated registration、05:50、`IgnoreNew`、不呼叫 aggregate registration
- Windows query-only PID probe、自然結束 process 的 reclaim
- unknown／malformed／AccessDenied fail closed

另完成 operational wiring 相關回歸測試、targeted mypy 與 changed Python files 的 `py_compile`；受控 run 使用真實 persistent paths 並產生上述 immutable receipt。

## 預期下一次行為與已知選擇缺口

目前 Taipei 2026-09-15 的 dry-run 因同日 scheduled snapshot 尚未到位而回報 `same_day_scheduled_recommendation_snapshot_missing`，calendar evidence 亦為 `lacks_official_evidence`；因此 child 不執行。這證明新 task 在 source prerequisite 不完整時會留下可稽核的 fail-closed 結果，不會自行刷新昂貴 technical source 或靜默花費。

既有 `build_default_recommendation_calibration_consumer` 與一般 app resolver 仍指向 legacy `FA_Data_Shadow`。本次沒有偷偷把 BankTaiwan lane 切成 UI／Advice／Recommendation 的 default；要檢視新 lane 必須明確傳入 BankTaiwan pointer／root。這是刻意保留的後續 wiring gap，不代表 UI 已採用 BankTaiwan shadow candidate。

本 lane 的 shadow learning／adoption gate 依既有 `fees_tax_only` natural-evidence policy 執行；本次因 natural forward evidence 尚未成熟而等待。broker actual fill、slippage 與 liquidity observation 不因此成為本 lane 的 shadow maturity 前提；它們屬於尚未啟用的真實成交／production execution realism 路徑。formal technical source contract 與 corporate adjustment 的缺口仍限制 historical／after-cost source claims，但不能把這些缺口誤寫成已發生的成交成本。任何正式 production recommendation 或 broker execution 仍須另行授權與驗證。
