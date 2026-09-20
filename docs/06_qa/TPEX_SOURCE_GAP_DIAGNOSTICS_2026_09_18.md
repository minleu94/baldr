# TPEX source gap diagnostics — 2026-09-18

## 結論

本次正式 decision evidence capture run `20260918T122502797364Z-414cfa43c1b0` 已完成並通過 receipt，但品質分布為 `1080 degraded`、`3 estimated`、`15 observed`（共 `1098` events）。其中 `702` warnings 是兩個每筆 exclusion metadata 標記各 `351` 次，不代表 `702` 個獨立來源失敗。

最高價值的可修資料流缺口是 TPEX 同日 raw 未落地：`data_update_quick/latest_status.json` 的 `update_tpex_daily_prices` 明確為 warning，`failed_dates=["20260918"]`、`updated_dates=[]`、`source_dates=[]`、`tpex_rows=0`、`diagnostic_count=0`、`source_custody=[]`；`daily_price_tpex/20260918.csv` 也不存在。TWSE 同日來源有 custody receipt 和 `1090` rows，故本輪有充分證據判定 TPEX 9/18 raw 缺件，但沒有足夠保存證據把早上排程的原因再分類為官方供應、HTTP/fetch、日期回應不符或 parser。

13:00:25–13:00:27Z 的獨立、唯讀官方 probe 隨後各發一次 bounded GET：after-trading endpoint 回 HTTP `403`、Cloudflare HTML `5483` bytes（response hash `ff8945fa53509c53529f8e8d13f01f37dd3933b68fd73232696694a59d540578`），OpenAPI endpoint 也回 HTTP `403`、`5483` bytes（response hash `1d4280595abc0c9a4e6380cbd3d362e38286d526c6643705ddf44832ac0b0271`）；兩次都標示 `parse_result.status=not_attempted_http_status`，沒有進入 production parser。這直接證明 probe 時點的官方端點被 HTTP 層阻擋，但不能回溯認定早上排程就是同一原因；早上 run 的根因仍為 unknown。原始 probe 報告見 [TPEX source probe raw report](../../output/qa/tpex_source_probe_20260918/probe_report.json)。

同日 BankTaiwan learning 也已實際執行，並非尚未啟動：wrapper run
`2026-09-18-attempt-001-91feea81e0f4` 以 `failed_dependency`／child exit `2` 收尾，
`missing_source_symbols=[1569]`、當日 TPEX technical receipt 只到 9/17，
`prospective_available=false`，因此 live capture 被保守阻擋。有效 captures 仍是 9/15–17
三份、18 rows、matured=0；這是同日 source custody 缺件，不把 13:00 probe 回溯成早上 run 根因。
有效核心 readback 見 [BankTaiwan learning readback](../../output/qa/banktaiwan_learning_readback_20260918/readback_20260918T130922Z_core.json)。

## 最新官方 raw 恢復觀測與正式補入

2026-09-19T07:20:33.071218Z，對原指定官方 `afterTrading/otc` 端點完成一次
bounded、`verify=True`、無重試的唯讀 GET。這次回應不是早先 403／remote-close probe 的回溯改判，
而是新的保存證據：HTTP `200`，原始 body `146419` bytes，SHA-256
`2eae9b5185bfde35ddb63ed6ed4d331f3a97a195229394a693db54ddc9739e62`。

payload 自帶 `source_date=20260918`，official afterTrading table 找到代號 `1569`：
`Close=55.50`、`Open=52.00`、`High=57.00`、`Low=52.00`、`TradingShares=5,164,000`。
Production parser 對保存 body 的 canonical row 也通過。隔離 raw、JSON 與 metadata 位於
[heartbeat raw evidence](../../output/qa/tpex_source_acquisition_20260918/heartbeat_20260919T071913Z_after_trading_otc/)，
其中 metadata 記錄實際完成時間、參數、headers、TLS 設定與 hash。

另有 Fubon／FinMind 候選回應的成交股數 `5,422,427`；它與本 official afterTrading
`5,164,000` 不是同一 source／volume 口徑，不能互相替代或用來改寫本 row 的 official
證據。這份 raw 後續才進入受控 dry-run、正式補入與獨立 readback；Fubon／FinMind
候選回應仍不能用來分解官方成交股數的零股、盤後或鉅額組成。

## 正式補入與獨立唯讀 readback（2026-09-19）

A 的受控 insert-only apply 以 exit `0` 完成，正式 readback 也為 `true`。獨立驗收使用
保存的 apply backup 與正式 DB，各自以 SQLite `mode=ro`、`PRAGMA query_only=ON` 讀取
受影響的 `20260918` 日期範圍，沒有使用 immutable、沒有寫入 DB、沒有執行 runner 或 scheduler。

- 正式 DB 9/18 rows：`1090 → 1958`，delta `868`；normalized official source keys overlap `868`、conflict `0`。
- 1569 正式 row：`Open=52.00`、`High=57.00`、`Low=52.00`、`Close=55.50`、`成交股數=5,164,000`、`成交筆數=2,537`、`成交金額=281,868,400`。
- apply 前既有 1090 rows 的 hash 為 `sha256:9eee2427f1b8f4358f89bcac76950935895dcde71bbffb0c87398fa35f70828e`；apply 後以同一組既有 keys 讀回的 hash 相同，確認既有 rows 未變。
- formal CSV 已建立 `868` rows，SHA-256 為 `sha256:0885957af1ce0039858dc4293e858b7aab8a2c1bc2618b4f14ee510eb3211664`。
- formal custody raw 為 `146419` bytes，SHA-256 仍為 `sha256:2eae9b5185bfde35ddb63ed6ed4d331f3a97a195229394a693db54ddc9739e62`；receipt 的 raw hash 與之相同。
- backup 為 `D:\Min\Python\Project\FA_Data\meta_data\backup\twstock_tpex_daily_price_backfill_20260919_003431.db`；custody 及 CSV 路徑均保存於正式資料根目錄。

獨立驗收原始結果見 [formal DB preflight/readback](../../output/qa/tpex_source_acquisition_20260918/formal_db_preflight_20260919T072937Z/independent_readback.json)，
apply 前基線見 [preflight before apply](../../output/qa/tpex_source_acquisition_20260918/formal_db_preflight_20260919T072937Z/formal_db_preflight_before_apply.json)，
而 A 的 apply evidence 見 [formal apply evidence](../../output/qa/tpex_source_acquisition_20260918/formal_apply_20260919/after_state.json)。
readback 只針對受影響日期及 backup 的既有 rows；未做全庫掃描，非 `20260918` 的未變更結論依
insert-only 的日期輸入範圍與 backup 既有 rows hash 支持。

這表示 9/18 TPEX daily-price source gap 已完成歷史資料層的受控補入與 custody 保存，但不會
回溯改寫原先 `decision evidence capture` 的 failed receipt、BankTaiwan 的 failed dependency
或當時的 source availability 判定。
Receipt 仍明確保留 `historical_pit_status=not_proven_by_after_close_capture`、
`formal_source_contract_eligible=false`；本次補入不產生 natural learning、calibration 或
decision-time credit。

## 呼叫鏈與影響

資料更新呼叫鏈為：

`run_daily_data_update_quick.py` → `UpdateService.update_tpex_daily_price_range` → `TpexDailyPriceSource.update_for_date` → TPEX 官方 endpoint/fallback。

原本區間方法在單日 `success=False` 時只留下 `failed_dates`，遺失來源 `message`、`source_date`、`diagnostic_count`；fallback 失敗也未進入可保存結果。下游 `DecisionMarketFrameLoader` / `RelativeStrengthLiquidityService` 因同一份 daily price SQLite 的當日覆蓋不足而標為 degraded。bounded main-file 觀測為 9/17 `1957` 個代號、9/18 `1090` 個代號，差 `867` 個；此 SQLite 觀測僅代表 audit 時點，不能單獨當作 live database 的永久缺失證明。當日 raw freshness 狀態與 TPEX 檔案缺失提供獨立佐證。

本輪 capture 是 research-only，沒有 natural/calibration credit；沒有偽造資料、放寬品質門檻或修改正式 SQLite。

## 最小修補

`app_module/update_service.py` 的 `update_tpex_daily_price_range` 現在在既有回傳結構中增加 `failure_diagnostics`：

- 保存要求日期及 fallback 的非成功結果，包含 bounded（最多 512 字元）message、requested/result requested/source date、success、diagnostic/row/skipped counts 與 custody presence。
- 來源結果回傳後若隨即取消，先保存該失敗診斷；後續區間例外也保留先前 diagnostics，再加入 bounded range exception。
- aggregate `diagnostic_count` 反映已保存的失敗 diagnostics；原有 failed dates、warnings、成功判定、fetch、SQLite sync、coverage 門檻不變。

這只改善下一次合法更新的可追溯性；本次 9/18 historical raw 的補入是後續獨立、受控的
insert-only backfill，不由此修補自動觸發，也不觸發 scheduler 或 production runner。

## 驗證

raw outputs 保存在被排除的 `output/qa/decision_evidence_capture_diagnosis_20260918/`：

- targeted regression：`4 passed, 61 deselected`。
- `tests/test_update_service_status.py`：`65 passed`，僅有既有 `.pytest_cache` 權限 warning。
- `py_compile app_module\update_service.py`：exit `0`。
- `mypy --explicit-package-bases app_module\update_service.py`：exit `0`，`Success: no issues found in 1 source file`。
- `git diff --check`：無 whitespace error。

readback 原始摘要為 `output/qa/decision_evidence_capture_readback_20260918/readback_20260918T1226Z.json`；完整 bounded 診斷與 raw log 索引見 [TPEX_SOURCE_GAP_20260918.md](../../output/qa/decision_evidence_capture_diagnosis_20260918/TPEX_SOURCE_GAP_20260918.md)。

## Run identity bounded audit

本輪沿 wrapper → evidence child → `EvidenceCaptureService` 呼叫鏈唯讀核對：wrapper 的 `run_id` 是排程嘗試／immutable receipt identity；`evidence_events.run_id` 則是 EvidenceEventService 的研究／事件 lineage key，scheduled child 沒有接收 wrapper run id，且該欄位預設為空。事件仍保存完整、可驗證的 `metadata.capture_context`，wrapper 也以 temporal／identity hash 做 readback；natural evidence 讀取 immutable prediction capture、source contract 與 natural receipt，不依賴 `list_events_for_run()`。因此空的 DB `run_id` 不阻斷 daily natural evidence 對帳，也不應為此新增接線。隔離契約 `test_explicit_capture_preserves_context_and_retry_capture_clock_is_idempotent` 為 `1 passed`（exit 0；僅既有 pytest cache permission warning）。

## 限制與 rollback

早期 SQLite audit 曾在普通 `mode=ro` 受限時以 `mode=ro&immutable=1` 讀取當時 main file，觀測到無 `-wal/-shm` 且 journal mode `delete`；那是當時 audit 的限制，不代表本次正式 apply 後狀態。此次 preflight/readback 使用普通 `mode=ro`、`PRAGMA query_only=ON`，保留 WAL 語意，沒有用 immutable 忽略活躍 WAL。這些 bounded 讀取都不是對 concurrent writer 或未來 live 狀態的永久保證。

9/18 TPEX raw 現已完成上述正式 CSV、custody 與 insert-only DB backfill；若需 rollback，應依
apply backup 與既有受控 backfill 流程處理，不能刪除或覆寫原始 receipt。早先排程的 failed
receipt、PIT 未證明與 natural/calibration 不可用狀態仍保留，不把後來取得的 close-close raw
回填成當時 decision-time 可得資料。`update_service.py` 的 failure-diagnostics hunks 與
對應 focused tests 仍可獨立回滾，正式資料、scheduler 與既有 receipt 不因該 code rollback
而自動回滾。
