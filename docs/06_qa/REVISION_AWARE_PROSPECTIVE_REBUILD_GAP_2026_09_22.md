# Revision-aware prospective rebuild gap QA（2026-09-22）

> 狀態：draft for root review。這份 QA 只記錄本輪診斷與最小工程缺口；沒有修改正式 SQLite、repair sidecar、source gate、scheduler、capture 或 credit。觀測時間為 UTC `2026-09-22T13:49:57.2356533Z`、台北 `2026-09-22T21:49:57.2356533+08:00`。

## 已證實的 9/22 blocker

BankTaiwan 9/22 source contract：

`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\source_contract\2026-09-22\dade69b6fe67504b\contract.json`

file SHA 是 `sha256:b681292c9ceab5dfe8b77b2c3311df687fbd856ae1a04fbb66b9ed298e394850`，`checked_at=2026-09-22T12:50:05.381095+00:00`，requested symbols 為 `1521, 1560, 1569, 1595, 1709`。`technical.prospective_feature_snapshot` 為 `blocked`、`verified=false`，reason 是 `prospective_feature_snapshot_failed:DailyPriceSourceRevisionError`。`formal_source_contract_eligible=false`、`historical_pit_eligible=false` 等欄位是另外的 scope 狀態，不是本輪首因。

bounded reproduction 的呼叫鏈為：

`recommendation_calibration_source_contract._prospective_feature_snapshot` → `MLHistoricalSnapshotProvider.load` → `check_daily_price_source_revision` → `_check_receipt`。gate 位於 [ml_daily_price_revision_gate.py](../../data_module/ml_daily_price_revision_gate.py) 的 `check_daily_price_source_revision`、`_check_receipt` 與既有 fail-closed policy；provider 在 [ml_historical_snapshot_provider.py](../../data_module/ml_historical_snapshot_provider.py) 讀取前呼叫它，source contract 只把例外型別轉成 blocked reason。現有 policy 會先讀 pending marker；它沒有完整 rows，所以對本次 requested symbols 保守採 all-symbol hold。

5/20 repair sidecar：

- pending：`D:\Min\Python\Project\FA_Data\output\scheduled\daily_price_repair_receipts\20260520\historical_price_spike_20260921\pending.json`，file SHA `sha256:f60fe67d82930280f3ce76d8a0a3e0dd4b0f28e00fa48900e86f0fa1bf8b19b7`，`status=applied_receipt_written`，`created_at=2026-09-22T07:30:49.586086+00:00`。
- final：同目錄 `receipt.json`，file SHA `sha256:a157a401b21f3eaac8ae82fd21859161f37acc277fcd3d26a0614ccb6a6d280f`，`status=applied`，`corrected_at=2026-09-22T07:30:49.544569+00:00`，`allowlist_count=868`，`available_at=null`，`historical_decision_time_available=false`，`formal_training_allowed=false`，`promotion_eligible=false`。
- final receipt 與 requested cohort 的精確 affected intersection 是 `1521, 1560, 1709`；`1569, 1595` 不在 final 的 868 rows，但仍受 pending all-symbol hold 影響。`official_capture_at=2026-09-07T19:24:00.737021+00:00` 不能代替修訂值的歷史 available time。

## 5 symbols 的 feature dependency readback

以正式 DB `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` 以 `mode=ro`、`PRAGMA query_only=ON` 查核，決策日 `2026-09-22` 的前一交易日 cutoff 為 `2026-09-21`。目前 feature registry 最大 rolling period 是 60 日，故每檔 computed feature 的最後依賴 tail 為 61 個觀測列。結果如下：

| symbol | daily rows ≤ 9/21 | feature tail | tail range | 5/20 raw row | 5/20 in tail | 5/20 technical rows |
|---|---:|---:|---|---|---|---:|
| 1521 | 3091 | 61 | 2026-06-26..2026-09-21 | true | false | 1 |
| 1560 | 3091 | 61 | 2026-06-26..2026-09-21 | true | false | 1 |
| 1569 | 3076 | 61 | 2026-06-26..2026-09-21 | true | false | 1 |
| 1595 | 3071 | 61 | 2026-06-26..2026-09-21 | true | false | 1 |
| 1709 | 3084 | 61 | 2026-06-26..2026-09-21 | true | false | 1 |

這只證明當前 rolling feature tail 與 5/20 沒有日期交集；raw prefix 仍含 5/20，且 gate 仍依整個 PIT prefix fail closed。9/22 prospective feature snapshot 因 gate 失敗沒有 persisted rows，因此本次 DB readback 不是 capture，也不表示 source contract 已通過。完整 bounded proof 留在 ignored QA：`output/qa/revision_aware_rebuild_gap_20260922/proof.json`（SHA `sha256:a492395a9d4af41c73278963283fdb151b8e9f9071ab71920a02a918380a86e7`）。

## frozen candidate 的影響界線

`rec-cal-b48b793f35280ce0ff9d5109`：

- candidate：`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\runs\2026-09-14\scheduled-snapshot-5f4de77ffb404af2-efed573\candidates\rec-cal-b48b793f35280ce0ff9d5109\candidate.json`，file SHA `sha256:c35bb83e01d9758f8adce815b98923fafe541285737204e527afab5856e6d2ab`。
- manifest file SHA `sha256:723b21b42261bd32abe3bc374abcea75d62d79c9ae3eebcea86efff782f19466`，artifact hash `sha256:90d1828c84b53c1f929f1929fd17a29a4b7578ffeb307870ada39ea867f4a6b7`。
- frozen candidate 宣告 `training_as_of=2026-01-28`、`training_row_count=255`、`horizon_trading_days=20`、dataset `recommendation-dataset-4928f33774d499f2`。

依 candidate 自身的 training cutoff，5/20 晚於宣告的 training as-of；但 candidate 沒有逐列 source-date/hash map。本輪只能給 bounded date-based assessment，**不能證明該 candidate 逐列不相交，也不能把此缺口描述成已證實的外部輸入缺失**。run receipt 所記錄的後續 bootstrap 是 `attempted`、trigger 為 `candidate_training_failed`，不作 frozen candidate 成功來源證明。

本輪也沒有重新驗證既有 Bank 30 captures／4 dates 的有效性；先前 `matured=0` 界線保留，不能宣稱全部有效或全部作廢。

## Technical publication 的時間解讀

fresh technical receipt：

`D:\Min\Python\Project\FA_Data\output\scheduled\technical_indicator_publication\2026-09-22\821c97efa2ab6685\receipt.json`

file SHA `sha256:9af39ed407f49ddf6394b7f156176c6123433e7349e215618e32e1caa7525901`，`available_at=2026-09-22T04:36:58.875816-07:00`、content SHA `sha256:821c97efa2ab66858f73087bbe464c9ab6b2f865d06cf5171dce0c92997ed4dd`、`technical_step_status=passed`。wrapper receipt `3384ffe8e13fc2df` 的 file SHA 是 `sha256:11b85d8393eb120b99ee3075d5345864f18a1646bb66d4d30b0bc290aaecc4f9`，同樣指向該 fresh computation。

這些時間只能證明 publication `available_at` 晚於 repair `corrected_at`。目前 receipt 沒有足夠的 computation start、source snapshot hash 或 cache invalidation evidence，因此不能據此斷言 technical 一定在 repair 後重新計算，也不能排除舊 cache 被重用。兩份 receipt 仍是 `prospective_source_only=true`、`formal_source_contract_eligible=false`、`historical_pit_eligible=false`。

## 最小工程缺口與安全依賴順序

現有 `scripts/build_ml_pit_year_shards.py --source-revision-receipt` 與 `PITYearShardExporter.build` 只提供 revision guard；帶入目前 receipt 仍會 fail closed。`RecommendationHistoricalReplayService` 也透過同一 provider/gate，沒有 revision-aware acceptance。缺口是受控的 **revision-aware prospective acceptance**，不是放寬現有 gate，也不是 generic framework。

安全順序應為：

1. 對原失敗的 9/22 cutoff 建立 shadow-only research diagnostic；保留原 decision/cutoff，明示 source 是 late-obtained，不能重建成今晚的 natural capture，也不能授予 natural/formal/PIT credit。
2. 未來真正的新 decision 只能在當下自然時間，以新 source acquisition/publication receipt 建立新的 prospective capture。歷史 `available_at` 缺失不能補造，但不構成對未來 prospective 的永久禁止。
3. acceptance manifest 必須綁定新的 `decision_at`/timezone、source publication path/file hash/content hash、repair lineage、DB read-only snapshot hash、feature rows hash、registry hashes、no-lookahead readback 與 affected-row coverage。任何不具 authoritative available evidence 的歷史列只能維持 research/pending。
4. 新決策的 future label window 必須保存為 `pending`；不得為了完成 manifest 預填成熟 label，也不得使用 current clock 回填舊 capture。只有自然 future window 真實到期並通過既有 maturity 規則，才可另行形成 outcome evidence。

本輪未新增 acceptance code，未修改 gate/DB/credit，也未提交。這份文件只供 root review。
