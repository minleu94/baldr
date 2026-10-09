# ML allocation Formal input readiness（2026-09-20）

本頁是 2026-09-20 的 bounded 唯讀查核，針對下一個官方開市日 2026-09-21。沒有執行帶未來 `training_as_of` 的 readiness validator，沒有啟動 writer／scheduler，沒有改 binding、source pins、Formal flags 或 accepted artifact。

## 判定

9/21 runtime candidate 已存在，且其固定 source pins 可讀；這只代表下一個自然日有可用的 candidate runtime wiring，不代表 9/21 已完成 PIT、Rule、Paper 或 ML Formal input。9/21 的實際自然證據尚未產生，因此目前不能宣稱 accepted sidecar、Formal 3/3 或 ML natural eligibility。

候選設定是：

- `output/v4_next_formal/formal_daily_runtime_config_v6/2026-09-21.json`
- `status=candidate_ready_for_root_review`
- `activation_trading_day=2026-09-21`
- `generated_at=2026-09-18T13:00:05.435955+00:00`
- 檔案 SHA-256：`sha256:6977d1b48263f6da6f15586db5689a07b679da7749776323029dd8d3b65d63b3`
- `config_hash=sha256:ab7b389aa209adde9478444c0643e15cd7af71150b12d9389e58b0527efb81b8`
- `candidate_only=true`、`formal_oos_allowed=false`、`promotion_eligible=false`、`broker_order_allowed=false`

它與 active binding 使用同一個 `FORMAL_DAILY_RUNTIME_CONFIG_ROOT`。9/21 到達台北自然日後，loader 才會在 process 內選取同目錄的 `2026-09-21.json`；不需要也不應手動改 `FORMAL_DAILY_RUNTIME_CONFIG` pointer。9/20 的 `runtime_config_expired:2026-09-09:2026-09-20` 是週日沒有同名檔時回退舊 explicit path 的結果，不是 owner approval TTL 到期。

## 9/21 candidate 的 source pin

candidate 內的來源存在且標示 read-only：

- 官方日曆：`output/formal_daily_publications/calendar_candidate_archive/2026-09-09/1b6227dd0464eded-aff4c96e1edab151/v4_calendar_20260909_20260908_104849140.json`；選出的 9/21 為 TWSE／TPEx open，bundle hash `sha256:1b6227dd0464edede4d3d0a3a50679f3a241e3c82eb8f61448cdb7a82c2eb062`。
- 固定 portfolio clock：`output/formal_daily_publications/clock_candidate_archive/2026-09-09/d9852b1985ef89f60479110c1ef7974d7a06ea718c7ceddaf777d5284af571e1/clock/manifest.json`；clock id `clock:prospective:20260909:planned-v1`，manifest hash `sha256:d9852b1985ef89f60479110c1ef7974d7a06ea718c7ceddaf777d5284af571e1`，不按自然日重置。
- Rule parent：D 槽 `D:\Min\Python\Project\FA_Data\output\formal_prospective\clock-20260828\clock\manifest.json`、`metadata\owner_acceptance.json`、`metadata\universe_symbols.json`；candidate 的 preflight 標示 `status=verified`、parent symbol count 1932。D SQLite 只作 read-only market source。
- runtime／Paper source：`output\paper_execution_eod_replay\calendar_cache`、`paper_portfolio\paper_portfolio.sqlite`、`paper_trade_ledger.sqlite` 均存在；它們只是輸入 pin，9/21 的 Paper receipt／fill 尚未存在。
- 目前 `data_module/pit_sector_membership_machine.py` 檔案 hash 為 `sha256:fbf06b87f68a8e6687a81f5023464307ea5cdb5c24fcb66bae2e1efea1c2edab`，與最新 9/17 machine candidate 的 `producer_code_sha256` 相同。這只能證明 producer identity 一致，不能把 candidate 變成 Formal source。

## 9/21 自然時窗與實際缺件

candidate 的 execution order 要求下列順序；目前 9/21 對應檔案均尚未產生：

| 階段 | 自然時窗／契約 | 目前唯讀結果 |
| --- | --- | --- |
| PIT preopen | 台北 07:00–08:30；只能保存當日官方 raw custody 與 machine receipt | `pit_candidate_archive/2026-09-21` 不存在；目前最新 durable candidate 是 9/17 |
| PIT denominator／handoff | 外部 validated denominator、每個 archive 的 universe binding、coverage 與 cutoff | 目前 denominator 目錄只到 9/11；`pit_history_candidate/2026-09-21` 不存在 |
| Formal PIT sidecar | 09:00 後只重用 08:30 前 archive；需 `formal_pit_history_handoff` 與 `formal_pit_sector_publisher` readback | `pit_sector_membership_formal/2026-09-21/sidecar.json` 與 `receipt.json` 均不存在 |
| Rule source／history | 盤前 machine Rule bundle，之後 09:00–13:30 daily Rule history | 9/21 `rule_source` bundle 與 `rule_history/2026-09-21/manifest.json` 尚不存在；最近 status 仍是 9/20 runtime-expired blocked |
| Formal input/common identity | exact Rule／PIT／Paper 三來源與 common identity | `output/v4_next_formal/formal_identity_20260921.json` 不存在 |
| Paper／causal ledger | 當日 EOD 真 fill、費稅與 closed interval | `paper_execution_eod_replay/receipts/2026-09-21` 與 9/21 causal ledger 尚不存在 |

9/17 的 machine candidate 位於 `output/formal_daily_publications/pit_candidate_archive/2026-09-17/ae4a36a4afc8774a-01343f5f868dcc9a/`，是 `machine_verified`、1986 rows、官方 raw custody 已重讀，但 `formal_consumer_compatible=false`、`candidate_only=true`。它的 `effective_from=2026-09-17`；目前未證明它符合 9/21 runtime 所要求的 same-day archive／coverage 契約，不能僅靠 `effective_from` 推定可用。

## Validator 邊界

`scripts/inspect_ml_formal_input_readiness.py` 的 `build_readiness_report()`（約 `:839-918`）會把 `training_as_of` 轉成 decision time，並由 CLI 的 `_atomic_write_json()`（約 `:922-944`）寫出報告；以 9/21 作為 `training_as_of` 會把未來時間當成已觀測時間，因此本輪沒有執行。`scripts/inspect_formal_operational_readiness.py` 的公開 CLI 使用 host clock，但若指定 `--output` 仍會寫 QA 報告；本輪同樣只做靜態契約與檔案 readback。

正式 PIT publisher 的既有入口是 `data_module/formal_pit_history_handoff.py:44-320` → `data_module/formal_pit_sector_publisher.py:233-414`。它會重新驗證外部 denominator、archive rows／universe hash、available／archive cutoff、license scope、sidecar hash 與 assembler consumer readback；缺任一項便留下 blocked receipt，不能用 9/11 舊 receipt、9/17 candidate 或未來 clock 補過。

## 下個合法動作

實際 9/21 observation／receipt 必須在合法真實時窗產生：先完成 07:00–08:30 PIT／Rule source capture，再由 09:00 後 sidecar 重用 exact archive，接著產生 Rule history、Paper EOD／causal ledger 與 common identity。現在可以做有明確標示的診斷與準備，例如檢查排程能讀到既有 9/21 candidate root、確認外部 denominator 與 owner-controlled source path；這些準備不得被宣稱為已發生的 9/21 evidence，也不得授予 ML／Formal credit。

仍需 owner／正式 producer 完成的部分是：accepted Formal Rule Champion snapshot、9/21 PIT denominator/handoff/sidecar 的正式 readback、Paper 真 fill／closed interval，以及 ML lane 自己的 formal sector thesis/health context。9/21 runtime candidate 本身是 Rule-only wiring，不能解除 `formal_rule_champion_weight_snapshot_missing` 或 `formal_sector_thesis_health_context_missing`。
