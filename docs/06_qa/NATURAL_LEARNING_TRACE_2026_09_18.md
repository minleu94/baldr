# Natural learning trace（2026-09-18）

本文件是一次獨立、唯讀的 source-backed trace。審核時點為
`2026-09-18T01:43:26-07:00`。範圍是 2026-09-17 forward-outcome receipt 的
5 trading-day `ready` row、其 prediction／outcome／calibration evaluator 邊界，
以及 BankTaiwan 影子學習 lane 的自然成熟門檻。沒有執行正式 runner、沒有修改
產品 code、SQLite、scheduler、Manual 或 shared state，也沒有把任何研究結果當成
收益保證。

## 先給診斷

唯一的 5d `ready` row 是**真實後續價格研究結果，非可採用機率校準樣本**。它有
事件快照、事件收盤價、後續收盤價與 TAIEX benchmark，對已宣告的
close-to-close 研究定義沒有看到價格上的 look-ahead；但事件沒有 candidate／champion
probability、prediction capture、binary label 或 calibration identity。因此它不能進
natural calibration evaluator，也不能計 Brier、calibration gap 或 probability change。
它最多只能留在同一 cohort 的 forward outcome／effectiveness read-model 研究 lane，
並保留 `formal_credit_granted=false` 與 `requires_named_review=true`。

BankTaiwan 的三批 `scheduled_live` prediction capture 共 18 rows，9/17 receipt 仍是
`completed_waiting_natural_maturity`，natural matured samples `0/20`、distinct
natural decision dates `0/20`，所以應維持 `retain_current`。1120 筆 replay、80 個
replay decision dates 不得折抵這兩個門檻。沒有正式 maturity calendar observation，
不推算下一個成熟日。

## SSOT、時間與查詢方法

主要來源如下；檔案 hash 是審核時讀取的 bytes hash。

| 用途 | 原始路徑與觀測 |
|---|---|
| forward latest status／receipt | `D:\Min\Python\Project\FA_Data\output\scheduled\forward_outcomes\latest_status.json`；`status=passed_with_warnings`；`checked_at=2026-09-17T20:40:02+08:00`；bytes SHA-256 `sha256:92795ec0159224a08862cd8788c4551b94e5f10c396eff63a7220fcb55ff1bee`。同一 run receipt 為 `...\runs\20260917T124002436970Z.json`。 |
| recommendation source snapshot | `D:\Min\Python\Project\FA_Data\output\recommendation\runs\scheduled_rec_20260910_051003.json`；`created_at=2026-09-10T05:10:03-07:00`；bytes SHA-256 `sha256:9bd0b64de2214e9907302481d6cc2124fec405dbef49d8aec406547f84b1f022`。 |
| formal SQLite | `D:\Min\Python\Project\FA_Data\sqlite\twstock.db`；讀取時 size `3,582,468,096` bytes，LastWrite `2026-09-17T05:55:17`；`daily_prices` 與 `market_indices` 最大日期均為 `20260917`。 |
| legacy learning status | `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\latest_status.json`；9/17 `retain_current`、natural matured `0`；bytes SHA-256 `sha256:7ee82045facf69a16be2c53c3486f4645fb262ebc42d573f83bb972e308855d8`。 |
| BankTaiwan scheduled status | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\scheduled\recommendation_learning_banktaiwan\latest_status.json`；bytes SHA-256 `sha256:d425f153624817fb36a490726b36fd2d123b62fb85638e9554c482a80833319538`。 |

SQLite 檢查以 Python `sqlite3.connect('file:<db>?mode=ro', uri=True)` 開啟，接著執行
`PRAGMA query_only=ON`；讀回值為 `1`。查詢使用明確日期／event id 條件、聚合與
`LIMIT`，未透過會建 schema 的 repository constructor。主要 bounded SQL 形狀為：

```sql
SELECT ...
FROM evidence_events e
JOIN evidence_outcomes o ON o.event_id = e.event_id
WHERE e.event_date BETWEEN '2026-09-10' AND '2026-09-16'
  AND e.event_type = 'recommendation_included'
GROUP BY e.event_id
ORDER BY e.event_date, e.symbol
LIMIT 20;
```

## Forward receipt 與 11 個 qualifying events

9/17 receipt 的 bounded summary 是 `qualifying_event_count=11`，decision dates 為
`2026-09-10`、`09-11`、`09-14`、`09-15`、`09-16` 共 5 日；44 個自然鍵 outcome
row（11 events × 4 horizons），duplicate outcome key `0`。horizon 結果為：

| horizon | ready | pending | missing |
|---:|---:|---:|---:|
| 5 | 1 | 10 | 0 |
| 10 | 0 | 11 | 0 |
| 20 | 0 | 11 | 0 |
| 60 | 0 | 11 | 0 |

receipt 同時標示 `return_basis=close_to_close_event_date`、`historical_backfill=false`、
`research_only=true`、`production_scheduler_allowed=false`，以及
`source_preflight.read_only=true`、`query_only=true`。`events_skipped_incomplete_identity=215`
不是成熟樣本，也沒有被回填。

## 唯一 5d `ready` row：exact trace

| 欄位 | 值 |
|---|---|
| event | `evt_ceca67a706894b10b5c1b12a3da97e25` |
| event hash | `sha256:754171a169f682c51b0a75d19771c47ad8fd703e1f1b9e7b40bc55eacd47588a` |
| outcome | `out_0445c3419494417892d4165861741b76` |
| symbol／source | `1454` 台富；`source_type=recommendation_result`；`source_id=source_snapshot_id=scheduled_rec_20260910_051003` |
| decision／event date | `2026-09-10`；`available_date=as_of_date=2026-09-10` |
| source time | snapshot `2026-09-10T05:10:03-07:00`，即台北 `2026-09-10 20:10`；DB event `created_at=2026-09-10 12:25:46` 未帶 timezone，不以它推導時區 |
| event／outcome price | 9/10 close `12.85` → 9/17 close `12.60` |
| outcome | `window_days=5`、`window_type=trading_days`、`outcome_price_date=2026-09-17`、`outcome_status=ready` |
| returns | `forward_return_bp=-195`；TAIEX `benchmark_return_bp=-139`；`benchmark_excess_bp=-56` |
| cost | `cost_model_id=gross-close-to-close-no-cost-v1`；`liquidity_cost_bp=NULL` |
| quality／warnings | event `observed`；outcome `degraded`；`source_not_ingested` × 2 |
| cohort identity | strategy `scheduled-recommendation-default-v1`；strategy hash `sha256:f5fb20951d866eac0fc8cc07c88fdc805b672b846a1907620b71649185e95971`；universe hash `sha256:1e9b622ec3dd256b74aa6f12be77d46f5785261f2fc8ba6979583993393e836f`；universe policy hash `sha256:1370d68049aad470f11406de8915f4e7beeb643dca2916a8df583304ae0cff27`；benchmark `TAIEX`；tier `forward` |
| lineage flags | `formal_credit_granted=false`；`requires_named_review=true`；`run_id=""` |
| freeze／capture | prediction capture、candidate freeze、candidate id、probability hash、label registry：**事件 row 未提供** |

原始 snapshot 的 1454 recommendation row 只有排名／score 與理由；`total score=61.44`、
`ranking_method=fixed_threshold`，沒有可供 calibration evaluator 使用的機率。事件與
outcome metadata 的 `horizon_days=20` 是來源推薦的 primary horizon，DB outcome 的
`window_days=5` 是本次成熟觀測窗；兩者不能互換。industry return 雖為 `-140bp`，
但 `industry_benchmark_id=NULL`，不把它當成可核驗的 industry excess 結論。

### 收盤後 capture 與 look-ahead 判讀

snapshot 時間是台北收盤後。對本 row 已宣告的 close-to-close 研究定義，使用 9/10
收盤作為 event price、以之後的 9/17 收盤作為 target 是時間順序一致的價格觀測；這
不代表 9/10 收盤前已有 prediction，也不把它當作可成交 entry。更嚴格的 calibration
label 仍要求 capture 的 candidate／champion probability、`upside_label`、
`label_available_date`／`label_end_date` 與 same-date／same-cost receipt；這些欄位在
本 row 缺失，因此不允許由 `-195bp` 推導任何校準或收益命題。

對該 event 的其他 maturity row，資料庫明確是：

| window | status | maturity metadata |
|---:|---|---|
| 5 | `ready` | `expected_maturity_date=2026-09-17`、`remaining_trading_days=0` |
| 10 | `insufficient_future_data` | `waiting_for_calendar`、expected date null、remaining 5 |
| 20 | `insufficient_future_data` | `waiting_for_calendar`、expected date null、remaining 15 |
| 60 | `insufficient_future_data` | `waiting_for_calendar`、expected date null、remaining 55 |

forward health 的 `next_maturity_date=null` 並帶
`no_maturity_calendar_observation`；沒有正式 calendar observation 時不猜下一日期。

## Calibration evaluator 與 policy gate

原始 evaluator source 是
`ml_module/recommendation_calibration_authority.py`：

- `RecommendationPromotionPolicy`（約 `:55-90`）的 runtime defaults 為：natural matured
  samples `20`、distinct decision dates `20`、Brier improvement `50bp`、maximum
  calibration gap `1000bp`、maximum probability change `1000bp`、cooldown `20` calendar
  days。由這組 dict 計出的 policy hash 是
  `sha256:856cb0f16c727101fe816febf1245dc4ee5e7b87f3451f7834af0de62a546272`。
- gate（約 `:577-586`）先要求自然成熟樣本／日期，才檢查 Brier、gap 與 cooldown。
- natural evidence verifier（約 `:1033-1127`）要求 matured prediction-capture receipt、
  `same_date_same_cost=true`、可信 live source、capture binding 與 policy identity。
- comparison row（約 `:1264-1419`）要求 candidate／champion probability、
  `upside_label == stock_return_bp > 0`、label availability／end date 時序、同一 symbol／
  date／20-horizon key，以及成本與 liquidity lineage。缺 observed cost 時 after-cost
  label 必須維持 missing。

因此 5d forward outcome 不符合 evaluator 的最小輸入，且其 no-cost／5d scope 也不能
灌入 legacy fixed-50bp／20-horizon calibration lane。

## BankTaiwan：實際 20/20 gate 與 lane 分離

9/17 scheduled receipt：

- `status=completed_waiting_natural_maturity`、`reason=natural_forward_evidence_receipt_missing`；
  `decision_date=2026-09-17`、`decision_timezone=Asia/Taipei`。
- `natural_evidence.status=pending`、`reason=no_capture_rows_have_naturally_matured`、
  `diagnostics=["pending_rows=18"]`、`matured_sample_count=0`。
- `decision=retain_current`、`formal_order_allowed=false`、`broker_action=false`；active
  pointer 為 null，沒有 promotion／adoption。
- capture candidate 是 `rec-cal-b48b793f35280ce0ff9d5109`，freeze hash
  `sha256:13ac9a6ef895a7c079009544a17b0f9354cf9f1b54d3e017d9a9b1394e37f85`，dataset hash
  `sha256:4928f33774d499f24c1560980fc28f867b244144a5b22893a57874b556487d07`。
- cost 是獨立的 `banktaiwan-electronic-estimate`，scenario hash
  `sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450`，
  `cost_basis=estimated_research_only`、`fixed_round_trip_cost_bp=null`，liquidity cost
  是 diagnostic-only 且尚無 observed fill lineage。

三份 capture 的 immutable 摘要如下：

| capture date | rows | capture id／capture hash | captured_at | file SHA-256 |
|---|---:|---|---|---|
| 2026-09-15 | 2 | `capture-462f9ff1e1c3cf5368deec63`／`sha256:600dbd742d6c512e289161e9cb8a6cca1b5203e1a0896a95600ccd5850380770` | `2026-09-15T21:33:24+08:00` | `sha256:3f10ac64956bd5736a7aacd02333265c896bb212663789d14e44627c2b46f39b` |
| 2026-09-16 | 2 | `capture-67cd7a5b04071c223cd9aa72`／`sha256:01b5a1e017fb8f282f9344543202b1f2f93d913299db64a66005c4773fee78fa` | `2026-09-16T20:50:14+08:00` | `sha256:1bcbde40b679e4a6bea3372156041d5c8289a8790a551fb6cb2f31488ff716c3` |
| 2026-09-17 | 14 | `capture-310614fa5e190e6baa56b698`／`sha256:c3c11c6444e378b32fa00b936efa30b32dc2b573501120cf6a28148579067b3e` | `2026-09-17T20:51:29+08:00` | `sha256:b50a6e3999cb13019e11dd8c34d28694d9940e9421809be16fc73595904b8b0a` |

三份 capture 都是 `schema_version=recommendation-prediction-capture.v3`、
`capture_origin=scheduled_live`，policy hash 都是上述 runtime default hash，
`maximum_probability_change_bp=1000`。這確認的是 **capture-level policy binding**。
BankTaiwan 的 scheduled wrapper 與 `recommendation-calibration-decision-receipt.v2`
沒有 `policy_hash` 欄位，且 active pointer 尚未建立；因此 **receipt-level policy
binding 未確認**，不能把 capture hash 自動當成 receipt 的 live policy 證明。讀到的
capture／pointer／receipt 沒有 threshold override；這不替代缺少的 receipt binding。

BankTaiwan replay 明確標示 `sample_count=1120`、`selected_decision_date_count=80`，
但 `historical_replay_is_natural_evidence=false`、`forward_evidence_eligible=false`、
`formal_candidate_eligible=false`。因此實際 gate 差距是：

| gate | observed | required | gap |
|---|---:|---:|---:|
| natural matured samples | 0 | 20 | 20 |
| distinct natural decision dates | 0 | 20 | 20 |
| natural Brier improvement | null | 50bp | 尚無法評估 |
| natural calibration gap | null | ≤1000bp | 尚無法評估 |

after-cost lane 另外要求 observed cost；estimated fee／tax scenario 與 replay 不構成
actual fill evidence。price-up calibration 也仍受 source contract／corporate-action
驗證與自然 outcome maturity 約束。沒有正式 maturity calendar observation，下一個
成熟日保持 unknown。

## 2026-09-18 排程與資料新鮮度

原始排程契約位於 `scripts/scheduled/register_baldr_scheduled_tasks.ps1` 與
`scripts/scheduled/README.md`：forward 05:40、legacy learning 05:45、BankTaiwan
05:50，均為 host-local Pacific schedule。9/17 已讀到 forward receipt（20:40+08）與
BankTaiwan receipt（20:50–20:51+08）；截至本次 01:43 Pacific audit，9/18 的
05:40／05:45／05:50 尚未到達，所有相關 latest status／receipt 最後都仍是 9/17。

對三個 task 做 query-only `Get-ScheduledTask` 時均回傳 `Access denied`：

- `baldr-forward-outcomes-daily`
- `baldr-recommendation-calibration-learning-daily`
- `baldr-recommendation-calibration-learning-banktaiwan-shadow-daily`

所以 live scheduler 的 9/18 trigger、last-run 與 result 是 **unknown**；不能以 task
registration 或 `Ready` 推定已執行。SQLite 此刻最大日期為 20260917，與尚未到達
9/18 learning schedule 的 receipt snapshot 一起記錄，不把它推論成 scheduler failure。

### 受控補充：decision-evidence-capture task

依本次授權，另以一次升權、唯讀的 `Get-ScheduledTask`／`Get-ScheduledTaskInfo`
查詢只核對 `baldr-decision-evidence-capture-daily`；沒有觸發或修改 task。讀回值為：

| 欄位 | 值 |
|---|---|
| State | PowerShell raw value `3` |
| executable | `cmd.exe` |
| arguments | `/c "C:\Projects\PythonProjects\technical_analysis\scripts\scheduled\run_decision_evidence_capture.cmd"` |
| working directory | 空字串 |
| next run | `2026-09-18T05:25:00-07:00` |
| last run | `2026-09-17T05:25:01-07:00` |
| last result | `1` |

這筆 action 確認 scheduler 指向本 repo 的 `scripts\scheduled\run_decision_evidence_capture.cmd`；
`LastTaskResult=1` 是 task result evidence，不能單獨替代 capture receipt，也沒有在本次
檢查中重新執行 task。其餘 forward、legacy learning 與 BankTaiwan task 仍維持前述
`Access denied`，沒有擴大升權查詢。

## 最終 lane 判定

| 證據 | 可進 lane | 不可進 lane | 判定理由 |
|---|---|---|---|
| 1454 的 5d row | 真實後續價格研究／forward outcome read-model | natural probability calibration、formal natural authority、可成交 entry | 有價格與 benchmark，沒有 prediction capture／label／same-cost policy binding；5d、no-cost scope 也與 evaluator 不同 |
| BankTaiwan 18 capture rows | 後續自然 maturity 觀察；capture-level prospective input | replay 折抵、promotion、after-cost calibration、formal order | natural matured `0/20`、dates `0/20`；estimated cost、observed fill 與 receipt policy binding 尚不完整 |
| BankTaiwan replay 1120 rows | research training／replay diagnostics | natural evidence、forward credit | receipt 明確標示 replay 不是 natural evidence |

本 trace 不支持任何收益、勝率、校準改善或可交易績效保證。
