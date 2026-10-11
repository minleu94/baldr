# V4.2 Prospective Source Daily Learning QA（2026-09-14）

> **目前判定：P1 daily custody／normal-lane acceptance PASS；整體 V4.2 仍 PENDING（natural forward／formal PIT 尚未驗證）**。2026-09-14 04:22:11-07:00 的正式 default wrapper 已成功：pipeline `passed_with_warnings`、`blockers=[]`；quick publication 於 `2026-09-14T04:21:27.181165-07:00` 為 `published`；normal learning `completed` 並保存新 immutable capture。symbol source=`scheduled_recommendation_snapshot:scheduled_rec_20260914_042140.json:eligible`、symbols=`1528`、candidate=`rec-cal-29c1b6129396a3885a89d080`、natural sample=`0`、decision=`retain_current`、reason=`natural_forward_evidence_receipt_missing`。新 capture hash=`sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`。P1 cache-hit engineering gap 已由獨立 custody QA 修復並通過：`tests/test_recommendation_learning_cache_hit_custody.py` 為 `1 passed, 1 warning in 1.25s`；source-contract／capture／official-custody／guards focused `17 passed`、update-service／process-pool／technical-analysis focused `10 passed`、targeted mypy `5 files` clean、inventory `12 passed` 且登錄總量 `805`／recommendation `31` 均已核實。修後 nested blocked-capture／same-second microsecond regressions 為 `33 passed`，scheduler metadata suite 為 `14 passed`；主 Luna 回報 QA 7.1 為 `33 passed`（確切命令、34.54s、exit 0 已列於 QA 表）。real durable flow 仍為 `retain_current`；工程與正式 default smoke 已由父任務接受，僅主 Luna git commit 尚待完成；這些結果不能取代自然 evidence、formal PIT 或 actual cost。

## 1. 範圍與判定原則

本次 QA 對象是 05:45 的每日推薦學習路徑：由 source/data 更新、official market-event custody、正常 scheduled recommendation snapshot，到 query-only learning child。持久 shadow 根目錄是：

```text
D:\Min\Python\Project\FA_Data_Shadow
```

這條路徑只產生 shadow dataset、recommendation snapshot、source contract、capture、自然成熟 evidence、authority 與 pointer。它不寫正式 recommendation／evidence DB、Portfolio、Formal 或 broker state，也不改正式推薦權重與下單狀態。

本文件不授予下列任何結論：

- V4.2 已完成或已達 production readiness。
- alpha、收益、命中率或投資有效性已改善。
- `passed_with_warnings` 等於正常 cohort 已完成。
- 50 bp 固定成本估計等於 observed transaction cost。
- historical replay、紙上 ledger 或單日 capture 等於 forward evidence。
- explicit 三檔 capture 等於正常 scheduled cohort。

## 2. 實際入口與 pipeline 行為

### 2.1 排程與程式入口

既有 Task Scheduler `baldr-recommendation-calibration-learning-daily` 在主機 local time 05:45 執行：

```text
scripts\scheduled\run_recommendation_calibration_learning.cmd
  └─ scripts\scheduled\run_daily_recommendation_learning_pipeline.py
       ├─ scripts\scheduled\run_daily_data_update_quick.py
       ├─ scripts\scheduled\run_official_market_event_backfill.py
       ├─ scripts\scheduled\run_scheduled_recommendation_snapshot.py
       └─ scripts\scheduled\run_daily_recommendation_learning.py
```

它接在同一主機 local time 05:40 的 `baldr-forward-outcomes-daily` 之後。learning runner 以 `_taipei_now()` 與官方交易日曆決定 decision date；主機 local clock 不是台北早盤可得時間的替代品。

pipeline 依序做以下工作：

1. **Quick data update**：更新官方日價、market、industry、technical 路徑。每日 learning lane 明確傳入 `--skip-broker-branch`，MoneyDJ broker branch 只在 status 中標成 `skipped`，不把缺少 broker source 說成已完成。
2. **Official market-event custody**：以 `prospective_bounded` publication scope 嘗試 bounded refresh。端點失敗時保留 failure；只有 prospective pointer、raw retrieval time 與 hash 都能重驗時，才可使用 last-known-good replay。replay 不算當日新抓取，也不授予 historical PIT credit。
3. **Normal recommendation snapshot**：以 `max-stocks=200`、`top-n=50` 建立 shadow snapshot，保存 requested／eligible／missing／degraded cohort 與每個 symbol 的 coverage。它會寫 shadow recommendation result，但不寫 evidence DB。
4. **Learning child**：使用 query-only SQLite。省略 `--symbols` 時只接受同日 scheduled snapshot 的 `eligible_symbols`，不做 universe discovery；預設 `--capture-current` 僅在當日是 Asia/Taipei official trading day 且 source contract、feature rows、available-at 與 provider rows 均可驗時保存 capture。

### 2.2 Identity 與同日重跑

每日 cohort 的 `run_scope`／`capture_scope` 可以隨 snapshot eligible cohort 改變；固定的 `experiment_scope` 不得因當日 cohort 改變。相同 decision date、相同 identity 與相同 source hash 的 receipt 仍受 create-only／冪等規則保護。

`--symbols` 只用於 controlled trial 或針對指定群組的受控 capture。2026-09-14 的 `1528,1558,1560` 三檔 source-bound capture 不能被當作 normal 200-row cohort，也不能拿去填補正常 cohort 的缺口；同日另一個 identity 的 capture 不能重用。

### 2.3 故障、重試與 timeout

wrapper 的正常參數與 retry 邊界如下：

```text
official timeout       30 秒
official max attempts  4 次
official retry delay   2 秒
official request delay 1 秒
child timeout          3600 秒（pipeline 預設）
pipeline timeout       7200 秒（pipeline 預設）
```

child timeout 會標記 recoverable／`timed_out`，不刪除既有 durable receipt；資料補齊後可在同一 decision date 重跑。pipeline 總時間用盡時，尚未執行的 child 會留下 `pipeline_timeout:<step>` blocker。snapshot 不可用時不啟動 learning child；缺價、待重試日期、degraded source 與 official replay warning 要向上傳到 child／pipeline status。未知 child status 會 fail closed。

## 3. 操作參數與輸出路徑

### 3.1 正常 wrapper 預設

```text
DATA_ROOT=D:\Min\Python\Project\FA_Data
RECOMMENDATION_LEARNING_OUTPUT_ROOT=D:\Min\Python\Project\FA_Data_Shadow
DB_PATH=D:\Min\Python\Project\FA_Data\sqlite\twstock.db
RECOMMENDATION_LEARNING_HISTORY_START_DATE=2014-01-01
RECOMMENDATION_LEARNING_MAX_DECISION_DATES=100
RECOMMENDATION_LEARNING_COST_BP=50
RECOMMENDATION_SNAPSHOT_MAX_STOCKS=200
RECOMMENDATION_SNAPSHOT_TOP_N=50
RECOMMENDATION_OFFICIAL_MAX_ATTEMPTS=4
RECOMMENDATION_OFFICIAL_TIMEOUT_SECONDS=30
RECOMMENDATION_OFFICIAL_RETRY_DELAY_SECONDS=2
RECOMMENDATION_OFFICIAL_REQUEST_DELAY_SECONDS=1
```

正常排程不要設定 `RECOMMENDATION_LEARNING_SYMBOLS`。指定 symbols 時，操作者必須把結果標成 controlled capture，不能寫成正常 daily cohort。

### 3.2 直接執行 pipeline

需要對同一 pipeline 做受控重跑時，可明確指定與 wrapper 相同的 source、output、snapshot、replay、成本與 official retry 參數：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_daily_recommendation_learning_pipeline.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data_Shadow `
  --source-db D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --max-stocks 200 --top-n 50 `
  --history-start-date 2014-01-01 --max-decision-dates 100 `
  --fixed-round-trip-cost-bp 50 `
  --official-timeout-seconds 30 --official-max-attempts 4 `
  --official-retry-delay-seconds 2 --official-request-delay-seconds 1 `
  --child-timeout-seconds 3600 --pipeline-timeout-seconds 7200
```

output root 必須是 `DATA_ROOT` 以外的絕對路徑；不安全或把 shadow output 指向正式資料根目錄時，流程以 `recommendation_learning_output_root_invalid` fail closed。

### 3.3 主要 readback 路徑

```text
D:\Min\Python\Project\FA_Data_Shadow\scheduled\recommendation_calibration_learning\latest_status.json
D:\Min\Python\Project\FA_Data_Shadow\scheduled\data_update_quick\latest_status.json
D:\Min\Python\Project\FA_Data_Shadow\scheduled\official_market_events\latest_status.json
D:\Min\Python\Project\FA_Data_Shadow\scheduled\recommendation_snapshot\latest_status.json
D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\latest_status.json
D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\source_contract\YYYY-MM-DD\<hash>\contract.json
D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\captures\YYYY-MM-DD\<capture_scope>\<candidate_id>-<request_fingerprint>.json
```

判讀順序是 pipeline wrapper → data update → official events → recommendation snapshot → learning child → source contract／capture。先看 `status`、`warnings`、`blockers`、`recoverable`、`finalized`、`snapshot_cohort`、`natural_evidence` 與 `formal_order_allowed=false`，再看 nested receipt；不能只看 wrapper 最外層的 terminal status（包括 `passed_with_warnings` 或 `failed`）。

## 4. 2026-09-14 durable readback

以下是目前持久 shadow root 的可重驗事實；它們是工程 readback，不是最終 QA pass。

| 來源 | 目前 readback | 判讀 |
|---|---|---|
| `scheduled/recommendation_calibration_learning/latest_status.json` | 2026-09-14 04:22:11-07:00 wrapper 完成；`status=passed_with_warnings`、`blockers=[]`；同輪 quick publication 於 `2026-09-14T04:21:27.181165-07:00` 為 `published` | 最新 durable orchestration 已有 terminal receipt；warning／degraded source 仍須保留，不能當成自然 evidence 或整體 V4 完成 |
| `scheduled/recommendation_snapshot/latest_status.json` | `status=passed`；screening matrix 200 rows；recommendations 1；requested 200、eligible 1（`1528`）、missing 0、degraded 199；coverage `degraded` | normal snapshot 是 partial／degraded，不能說 200 檔都形成正常 recommendation cohort |
| `recommendation_learning/latest_status.json` | `status=completed`；symbol source 為 `scheduled_recommendation_snapshot:scheduled_rec_20260914_042140.json:eligible`；symbols=`1528`；training rows=255；candidate=`rec-cal-29c1b6129396a3885a89d080`；experiment scope=`scheduled-experiment-ff4d2ab937e2c8b32bf2df04`；decision=`retain_current`；reason=`natural_forward_evidence_receipt_missing`；natural sample=`0` | single-class blocker 已由 bounded bootstrap 處理；新 normal capture 已保存但 real natural sample 尚未成熟，不能宣稱 promotion 或整體 V4 完成 |
| historical bootstrap dataset | observation status=`recovered_completed`；selection policy=`time_stratified_eligible_dates`；manifest=`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\datasets\recommendation-dataset-da3d867b06b5436d\dataset.json`；`initial_seen_start=2026-04-23`；bootstrap replay selected date window=`2024-09-16` 至 `2026-02-11`；date overlap=`0`、row overlap=`0`、label boundary crossing=`0` | 已有 bounded training lineage 的分層與零重疊觀測；這不是 natural forward evidence 或 formal PIT，real durable-flow 判讀仍分開保存 |
| normal live capture | `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\captures\2026-09-14\scheduled-capture-5f4de77ffb404af2\rec-cal-29c1b6129396a3885a89d080-850760d54413e019199be668.json`；hash=`sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`；`reuse_mode=new_immutable_scope_capture` | 04:22 true-success 已保存新 immutable capture；自然 sample=`0`，仍等待自然成熟 |
| `scheduled/data_update_quick/latest_status.json` | `passed_with_warnings`；core steps 有 receipt；broker branch 明確 skipped；保留 2 個待重試日期 warning | source update 有可用部分，但不是全來源 complete |
| technical publication receipt | `D:\Min\Python\Project\FA_Data_Shadow\scheduled\technical_indicator_publication\2026-09-14\0f533bde5119890a\receipt.json`；verified、1,954 rows；`rows_sha256=sha256:ef58d8d5cc49a772ce3eb89ab772fe752460e3309b66affc44490e1837828fae`；`content_sha256=sha256:4a24f6422ce4cde3092f038bc1cab4eb2ddea9c2a4e743c9a3ed51508a799304`；technical computation evidence verified | exact output rows／hash／microsecond completion time 有 receipt；TPEx `20260914` 缺價 warning 仍需保留 |
| official market-event custody | `prospective_latest_manifest.json` 與對應 manifest／raw hash 可重驗；TWSE endpoint refresh 出現 redirect／`Location` anomaly，失敗被保留，使用已驗證的 last-known-good prospective replay | replay 是 provenance-preserving fallback，不是當日新抓成功，也不是 historical PIT |
| corporate adjustment sidecar | `D:\Min\Python\Project\FA_Data_Shadow\release_v4\corporate_action_adjustments\runs\corporate-action-adjustments-2bcb882e3daeb04b77fca78d\manifest.json`；1,276 rows；manifest hash `sha256:7335383cc95f1f666e4f6f50c0f29e24376fd578d36d24709ad8e775d389360a`；`prospective_only=true`、`formal_source_contract_eligible=false`、`historical_pit_eligible=false` | prospective sidecar 已有 custody，但 formal／historical gate 仍未過 |

pipeline 外層與 child 的差異是本日最重要的判讀：2026-09-14 04:22:11-07:00 的外層與 learning child
都有 durable receipt；外層 `passed_with_warnings` 且 `blockers=[]`，quick publication 在
`2026-09-14T04:21:27.181165-07:00` 為 `published`，child 的 decision 是 `retain_current`，
原因為 `natural_forward_evidence_receipt_missing`，natural sample 為 `0`。04:10 smoke 的
microsecond completion witness 與 nested capture failure 曾造成 false-success 判讀，不能列為
pass；此次只採信 04:22 true-success。historical bootstrap 的 observation status 為
`recovered_completed`，selection policy 為 `time_stratified_eligible_dates`，其 date／row overlap
與 label boundary crossing 均為 0；這些只屬 bounded training lineage，不是自然 evidence 或 formal PIT。
因此可以記錄 normal training／capture 已產生，仍不能把它寫成 promotion、alpha 或整體 V4 完成。

## 5. Source contract 與自然證據邊界

本次正常 scheduled lane 已建立 1 row 的新 immutable capture：

```text
D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\captures\2026-09-14\scheduled-capture-5f4de77ffb404af2\rec-cal-29c1b6129396a3885a89d080-850760d54413e019199be668.json
```

其 `capture_scope=scheduled-capture-5f4de77ffb404af2`、`reuse_mode=new_immutable_scope_capture`、hash=`sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`；這是正常 cohort 的 source-bound capture，不是三檔 controlled capture。它尚未形成 natural outcome，`matured_sample_count=0`、reason=`natural_forward_evidence_receipt_missing`。

2026-09-14 三檔 controlled capture 的既有 durable 檔案是：

```text
D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\captures\2026-09-14\rec-cal-7ecaacb53cc043f36360f140.json
```

它保存 `1528,1558,1560` 三列 source-bound feature rows，`source_contract_binding` 指向：

```text
D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\source_contract\2026-09-14\89aae22ade5659d4\contract.json
```

可重驗的 binding 摘要如下：

```text
contract_content_sha256        sha256:89aae22ade5659d468a2a995b7b0be3e5de5cd80553a4a572b2c785900d185fc
contract_file_sha256           sha256:8150fae0cebafd6d42bf4912a5a9b5c452705c2be69756d3ab7e3483bd305df8
feature_snapshot_content_sha256 sha256:24d413b15c47f073f08e7f99366e4bc20f19ec45493bdc37c24aab5ede813acc
feature_snapshot_rows_sha256  sha256:bdd028ddc4e115033e3e9bcf01e609f5124d6336b43b726706070fc3cf518327
corporate_adjustment_manifest  sha256:7335383cc95f1f666e4f6f50c0f29e24376fd578d36d24709ad8e775d389360a
source_semantics                prospective_input_only;not_historical_backfill
historical_pit_eligible         false
```

最新 source-contract audit 位於：

```text
D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\source_contract\2026-09-14\2d9722b3c685d39b\contract.json
```

該 audit 的 feature snapshot、official event 與 adjustment custody 已通過 prospective availability；overall contract 仍為 `blocked`，因 observed liquidity fill lineage 與 formal technical／corporate contract 尚未完成。lane 必須拆開看：

每次 source-contract audit 都使用帶 timezone 的精確 `availability_cutoff_at`：timestamp 先正規化為 UTC，再要求 `available_at <= capture cutoff`。同一 instant 的 `+08:00` 與 `Z` 表示法可接受；晚於 cutoff 的同日 publication 必須拒絕。capture binding 會逐一檢查 technical publication、daily source receipt、prospective feature snapshot、official event publication 與 corporate-adjustment manifest 的 availability timestamp。這個 cutoff 契約是 prospective-only 條件，不能反推 historical PIT eligibility。

| Lane | 目前狀態 | blocker／限制 |
|---|---|---|
| `price_up` prospective | `prospective_status=ready` | 可等待自然 forward maturity；整體 formal technical／corporate gate 仍未授予 promotion credit |
| `after_cost` | `blocked` | formal technical contract 未驗證、corporate adjustment 未驗證、沒有具 fill lineage 的 observed liquidity cost；50 bp 只能是 fixed estimate |
| `actual_execution` | `blocked`／out of scope | `broker_actual_fill_custody_not_in_scope`；沒有 broker transaction ledger |
| historical replay | 不具 forward eligibility | 只可作 training／method research；新 capture 不能回填 historical decision 或 PIT evidence |

observed cost 的 readback 是 `actual_fill_lineage_rows=0`、`ready_rows=0`；paper ledger 仍是 research-only，不能作 observed fill。自然 price-up 可獨立進入 maturity verification，但在真正 future market source 到齊前仍是 pending。

## 6. QA 驗證表（工程與正式 smoke 已接受；產品成熟度邊界另列）

下表的 `PASS` 只代表已核實的工程 gate／正式 default smoke；`PENDING` 或 `OUT OF SCOPE` 僅保留給自然 forward、formal PIT、observed cost 與 broker execution 等尚未具備的產品證據。

| QA 項目 | 已讀取的工程事實 | QA 判定 | 判讀邊界 |
|---|---|---|---|
| source root 與 output boundary | durable root 為 `FA_Data_Shadow`；output root 越界會 fail closed，guards／focused QA 已驗證 | **PASS** | 工程 boundary gate 已接受；不授予 natural／formal PIT credit |
| technical computation receipt | `D:\Min\Python\Project\FA_Data_Shadow\scheduled\technical_indicator_publication\2026-09-14\0f533bde5119890a\receipt.json`；status=`verified`；2148 檔股票 bounded 真重算完成；receipt 保留 exact rows／hash／microsecond completion | **PASS** | TPEx `20260914` 缺價 warning 保留；formal PIT 另行判讀 |
| official event bounded refresh／replay | endpoint anomaly、prospective pointer、raw time 與 hash 可重驗的 last-good replay 均保留 | **PASS** | engineering custody／replay gate 已接受；replay 不是當日新抓取或 formal PIT |
| corporate adjustment custody | 1,276-row prospective sidecar 與 manifest hash 已保存；formal／historical eligibility 為 false | **PASS** | custody gate 已接受；仍不得授予 formal／historical credit |
| normal 200-row snapshot | snapshot status=`passed`；requested 200、eligible 1（`1528`）、missing 0、degraded 199，TPEx warning 保留 | **PASS（警告）** | engineering snapshot gate 已接受；degraded rows 不等於完整 200 檔 natural cohort |
| normal daily learning E2E | 04:22 wrapper `passed_with_warnings`／`blockers=[]`；quick publication `published`（04:21:27.181165-07:00）；learning `completed`；normal capture hash=`sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`；natural sample 0、decision `retain_current` | **PASS** | 正式 default smoke 已接受；natural evidence 尚未成熟，不作 promotion credit |
| historical bootstrap lineage | observation=`recovered_completed`；policy=`time_stratified_eligible_dates`；date overlap、row overlap、label boundary crossing 均為 0 | **PASS** | bounded lineage gate 已接受；不授予 natural forward／formal PIT credit |
| experiment／run／capture identity | fixed experiment scope、daily cohort scope 與 explicit capture identity 已分離，guards 已交付 | **PASS** | identity gate 已接受；同日 capture 不重用 |
| warning propagation | snapshot degraded、TPEx gap、待重試等 warning 已由 child／pipeline durable status 保留 | **PASS** | warning propagation gate 已接受；警告仍須在操作判讀中保留 |
| child／pipeline timeout | child timeout／recoverable receipt 與 pipeline blocker 傳遞 guards 已驗證 | **PASS** | timeout gate 已接受；前兩輪 180 秒 timeout 及 04:10 false-success 僅為失敗診斷，不列驗收 |
| after-cost／actual execution gate | observed fill lineage rows=0；固定 50 bp 只是 estimate；broker lane 不在 scope | **PENDING／OUT OF SCOPE** | actual observed cost、broker fill 與 formal PIT 證據尚未具備 |
| UI Workbench focused test | `tests/test_ui_qt_update_view_workbench.py`：81 passed；1 個 pytest cache permission warning，不影響測試 exit 0 | **PASS** | 保留 warning；不代表 daily learning focused tests 或 V4 gate 完成 |
| Update Tab QA | `scripts/qa_validate_update_tab.py`：25 passed、0 failed、4 skipped；exit 0 | **PASS** | skipped 項目與 daily learning focused／maturity evidence 仍分開判讀 |
| full-scope mypy | source-contract Mapping guard 修正後檢查 606 source files，`Success: no issues found in 606 source files`；exit 0 | **PASS** | canonical run exit 0；natural／formal PIT 與產品證據仍分開判讀 |
| affected focused suites | 主 Luna 交付 11 個 test files、`107 passed`、`36.44s`，保留既有 1 個 cache warning | **PASS** | 只代表 affected focused subset；工程 focused gate 已接受；不授予 natural／formal credit |
| synthetic mature fixture authority | `tests/test_daily_recommendation_learning_loop.py::test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags` 已通過 production source verifier；assert adopt／active pointer／active challenger／after-cost calibration sample、mature evidence、drift、rollback 與 final `rule_only` | **PASS** | 這是 synthetic fixture 的 authority proof；real durable flow 仍 `retain_current`，不授予 real natural maturity 或 promotion |
| changed scheduled scripts type check | changed scheduled scripts 的 mypy 檢查 `7 files` 成功 | **PASS** | 不等於全主線 focused／maturity／promotion gate 完成 |
| changed scripts／modules／tests compile | 以暫時 `PYTHONPYCACHEPREFIX` 執行 py_compile 通過；原有 `__pycache__` permission 限制保留 | **PASS** | 不刪除或重寫既有 cache；不代表 full pytest 或 natural／formal evidence |
| inventory／guards registration | inventory `12 passed`（1 個既有 cache warning）；新增 cache guard 後登錄總量 `805`、recommendation `31` | **PASS** | 登錄數是 inventory／coverage metadata，不是 805 個測試全數通過的宣稱 |
| three-day technical cache-hit custody QA | `tests/test_recommendation_learning_cache_hit_custody.py`；正式 output receipt 從各日 `FA_Data/output` 跨 root 解析至 Shadow 真實 verified reuse；保留原 timestamp；source-audit hash／value／lineage 與正式 ADX producer 輸出均通過；`1 passed, 1 warning in 1.25s` | **PASS** | fixture source 為 `fixture.invalid`，且 historical／formal eligibility 均為 false；此為 custody proof，不授予 natural forward 或 formal PIT credit |
| source／capture／official custody／guards focused | `17 passed` | **PASS** | focused gate 已接受；scheduler `14 passed` 與正式 wrapper smoke 另列，仍不授予 natural／formal credit |
| update-service／process-pool／technical-analysis focused | `10 passed` | **PASS** | focused gate 已接受；不取代 natural／formal／actual evidence |
| targeted mypy | `5 files` clean | **PASS** | targeted modules 已接受；canonical full-module mypy 606 files 另列 |
| QA 7.1 microsecond／nested blocked-capture regression | command: `python -m pytest tests/test_recommendation_calibration_contract_guards.py tests/test_daily_recommendation_learning_loop.py -q -o addopts=`；主 Luna 回報 `33 passed`、34.54s、exit 0 | **PASS** | 覆蓋 completion microseconds 與 nested blocked capture；不授予 natural／formal／actual credit |
| Python／mypy／已交付工程驗證 | UI81、Update Tab 25／0／4、canonical full-module mypy 606 files、affected 107、source／capture／official custody／guards 17、update-service／process-pool／technical-analysis 10、targeted mypy 5 files、mature fixture、py_compile、inventory 12、registration 805／31、cache custody 1、scheduler 14、QA 7.1 33 passed、04:22 default wrapper smoke 均已核實 | **PASS** | 這不是 full pytest 或 V4 completion 宣稱；僅主 Luna git commit 尚待完成 |
| 文件同步 | Snapshot、system architecture、Application Manual 與本 QA 已同步最新 04:22／QA7.1／限制判讀 | **PASS** | 僅主 Luna git commit 尚待完成；不再保留泛稱 parent handoff pending |

### 6.1 Affected focused command manifest

以下 11 個 test-file operands 組成不跑 full pytest 的 affected focused command；總結果為
`107 passed`、`36.44s`，並保留 1 個既有 warning：

```text
tests/test_daily_recommendation_learning_loop.py
tests/test_recommendation_calibration_contract_guards.py
tests/test_recommendation_calibration_source_contract.py
tests/test_recommendation_capture_source_binding.py
tests/test_corporate_action_adjustment_custody.py
tests/test_corporate_action_availability_history.py
tests/test_official_daily_price_custody.py
tests/test_scheduled_data_update_runner.py
tests/test_ml_purged_walk_forward.py
tests/test_ml_probability_calibration.py
tests/test_ml_available_date_boundary.py
```

其中 synthetic mature fixture 的 production-source verifier 測試為：

```text
tests/test_daily_recommendation_learning_loop.py::test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags
```

它驗證 active pointer、authority `adopt`、active challenger、after-cost calibration sample、
mature evidence、drift、`rollback` 與 final `rule_only`。這是 synthetic fixture 的 authority
proof；real durable flow 仍為 `retain_current`。

## 7. 目前收尾狀態與剩餘邊界

04:22 正式 default wrapper 的 pipeline status 為 passed_with_warnings、blockers=[]；quick publication 已於 2026-09-14T04:21:27.181165-07:00 published；learning 已完成並保存 normal immutable capture。technical receipt 路徑為 D:\Min\Python\Project\FA_Data_Shadow\scheduled\technical_indicator_publication\2026-09-14\0f533bde5119890a\receipt.json 且已 verified；2148 檔股票 bounded 真重算完成。normal sample=0、retain_current 與 natural_forward_evidence_receipt_missing 仍照實保留。

工程 gate 與正式 smoke 已由父任務接受：UI81、Update Tab 25／0／4、canonical full-module mypy 606 files、affected 107、source／capture／official custody／guards 17、update-service／process-pool／technical-analysis 10、targeted mypy 5 files、mature fixture、py_compile、inventory 12、registration 805／31、cache custody 1、scheduler 14 均已交付；主 Luna 回報 QA 7.1 為 33 passed（確切命令、34.54s、exit 0）。

剩餘判定只在產品證據邊界：natural forward 尚未成熟；formal PIT／promotion 尚未授予；actual observed cost／broker fill 不在 scope，50 bp 仍只是 estimate；historical replay 與 bounded bootstrap 不取得 forward credit。

四份 owned 文件已同步本次狀態；僅主 Luna git commit 尚待完成。
### 7.1 Final acceptance readback（2026-09-14 04:22 PDT）

本次 P1 daily custody／normal-lane acceptance 以新版 default wrapper 的 durable readback 為準：

| 項目 | 最終結果 |
|---|---|
| formal wrapper | `cmd.exe /c scripts\scheduled\run_recommendation_calibration_learning.cmd`；`exit=0`；pipeline `passed_with_warnings`；`blockers=[]` |
| technical producer | quick passed_with_warnings；completed=2026-09-14T04:21:27.181165-07:00；publication=published；evidence=verified；receipt=D:\Min\Python\Project\FA_Data_Shadow\scheduled\technical_indicator_publication\2026-09-14\0f533bde5119890a\receipt.json；2148 檔股票 bounded 真重算完成；TPEx warning 保留 |
| learning lane | `status=completed`；`live_capture.status=captured`；new immutable capture hash=`sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`；decision=`retain_current`；natural sample=`0` |
| regressions | QA 7.1 command: python -m pytest tests/test_recommendation_calibration_contract_guards.py tests/test_daily_recommendation_learning_loop.py -q -o addopts=；主 Luna 回報 33 passed、34.54s、exit 0；scheduler metadata 14 passed；targeted mypy 5 files clean；cache custody 1 passed；工程 regression gate 已接受，不授予 natural／formal／actual credit |
| limitations | official／TPEx retry warnings、199 degraded snapshot rows 與 natural sample=0 仍可見；actual fill lineage rows=0、50 bp 仍為 estimate、broker lane 不在 scope；natural forward、formal PIT、promotion、observed cost 與 overall V4.2 仍 pending／out of scope |

前兩輪 180 秒 timeout 是失敗；04:10 default 雖完成，但 publication 因 completion microsecond witness 不合法而 blocked，normal capture 亦因 nested capture blocked 且被舊 training completed 遮蔽而出現 false-success。兩者均不列為驗收；04:22 才是採信的 true-success。四份 owned 文件已同步；僅主 Luna git commit 尚待完成。

## 8. 更新記錄

- 2026-09-14 02:34:17-07:00：normal pipeline `passed_with_warnings`、blockers 空；learning child `completed`，`recovered_completed` 的 `time_stratified_eligible_dates` bootstrap 後 training rows=255、candidate 已產生、normal lane 新增 1 row capture。manifest 的 `initial_seen_start=2026-04-23`，bootstrap replay selected date window 為 `2024-09-16` 至 `2026-02-11`，date／row overlap 與 label boundary crossing 均為 0。decision 仍 `retain_current`，自然 forward receipt 尚未成熟；主線 QA final status 維持 `PENDING`，P1 cache-hit custody QA 其後獨立通過。

- 2026-09-14：獨立 UI／型別 QA 已完成：UI Workbench 81 passed（1 個 cache permission warning）、Update Tab 25 passed／0 failed／4 skipped；主 Luna 修正 source-contract Mapping guard 後 mypy 606 source files no issues。這些結果只關閉相應 UI／型別項目；real durable daily flow、主線新版 wrapper smoke 與自然 forward evidence 仍分開判讀，P1 cache-hit custody QA 另已獨立通過。

- 2026-09-14：主線驗收補充：affected focused suites 11 個 test files、107 passed、36.44 秒（既有 1 個 cache warning）；changed scheduled scripts 的 mypy 7 files 成功；changed scripts／modules／tests 以暫時 `PYTHONPYCACHEPREFIX` py_compile 通過，原有 `__pycache__` permission 限制保留；inventory 12 passed；新增 guards test 後登錄總量 804、recommendation 30。`test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags` 已通過 production source verifier 與 adopt／active／rollback assertions；舊 cache-hit guard 的 P1 source-audit／cross-root lookup／隔日 DB 變更缺口其後已由 verified receipt reuse 修復，獨立 cache QA 已通過；主線新版 wrapper smoke 與修後 source tests／型別／compile／inventory 最終 handoff 尚待交接，整體 QA 維持 PENDING。

- 2026-09-14：P1 cache-hit custody 修復後獨立 QA：`tests/test_recommendation_learning_cache_hit_custody.py -q -o addopts=` 為 `1 passed, 1 warning in 1.25s`、exit 0；三日正式 output receipt → Shadow verified reuse、原 timestamp、source-audit hash／value／lineage 與正式 ADX producer 輸出均通過。fixture source 仍為 `fixture.invalid`，historical／formal eligibility 均為 false；此項改判 **PASS**，scheduler 修正 test fixture 後的最終重跑與新版 wrapper smoke 仍待交付。

- 2026-09-14：主線修後 focused handoff：source-contract／capture／official-custody／guards `17 passed`；update-service／process-pool／technical-analysis `10 passed`；targeted mypy `5 files` clean；inventory `12 passed`，登錄總量 `805`／recommendation `31`；cache custody `1 passed`。scheduler 修正 test fixture 後的最終重跑與新版 wrapper smoke 尚待交付，整體 QA 維持 **PENDING**。

- 2026-09-14 04:22:11-07:00：正式 default wrapper true-success readback：pipeline passed_with_warnings、blockers=[]；quick publication 完成於 2026-09-14T04:21:27.181165-07:00 且為 published；technical receipt 0f533bde5119890a 已 verified，2148 檔股票 bounded 真重算完成；learning child completed，symbol source=scheduled_recommendation_snapshot:scheduled_rec_20260914_042140.json:eligible、symbols=1528、candidate=rec-cal-29c1b6129396a3885a89d080、natural sample=0、decision=retain_current；新 immutable capture hash=sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0。前兩輪 180 秒 timeout 與 04:10 microsecond／nested capture false-success 均不列驗收；主 Luna 回報 QA 7.1 為 33 passed、34.54s、exit 0；工程與正式 default smoke 已由父任務接受，僅 git commit 尚待完成。

- 2026-09-14：建立本 QA handoff，固定 wrapper／pipeline／source custody／normal snapshot／learning 行為、參數、路徑、retry／timeout、durable readback 與 source lane 限制。所有最終 QA 判定先維持 `PENDING`，等待父任務轉交正常 cohort 與測試結果。

## 2026-10-11 歷史交付狀態補記

本文多處「僅主 Luna git commit 尚待完成」只表示 2026-09-14 handoff 當時狀態。文件後續已包含於 commit `b26f943afe8815e7a8beb0a0bfa17af07fb032a5`（2026-09-14，`Finalize daily learning custody UI and docs`）。此提交只結清當時的文件交付狀態；本 QA 的 durable readback、natural sample、formal PIT、observed cost、promotion 與 V4.2 整體成熟度仍維持各自 2026-09-14 記錄範圍，不因提交而改判。
