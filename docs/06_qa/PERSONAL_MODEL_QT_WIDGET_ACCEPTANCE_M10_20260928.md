# m10 個人模型 Qt widget 驗收（2026-09-28）

## 結果

全新隔離 run `m10` 的 `status=PASS_QT_WIDGET_PERSONAL_MODEL_JOURNEY`。真 MainWindow Qt widgets 完成個人 V2 source-time preview／保存、推薦、canonical result save/readback、capture v3、cold restart、停用、fresh source proposal 後版本回退，以及最後 `rule_only` readback。這是 Qt widget 操作證據，不是 OS foreground、桌面截圖或原生視窗層證據。

總收據 [`personal_model_acceptance.json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m10/receipts/personal_model_acceptance.json)，SHA-256 `74bd1156e64065fa0bad01808c64f34f254aa6971e87aa4802653b71b3c60c65`。啟用階段 [`personal_model_activate.json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m10/receipts/personal_model_activate.json)，SHA-256 `ed19eb829933571db70cca9ab8f12c5f268bacbf429aa48b7b569ce621225f5d`；cold restart／停用／rollback 階段 [`personal_model_restart_disable_rollback.json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m10/receipts/personal_model_restart_disable_rollback.json)，SHA-256 `2f276a94f852c864e0d58b85df09a65ed47e5731bf2d5b76ad6df6be2bf7267c`。

## 身分與隔離

- Candidate：`rec-cal-3f8b2c276ef316e28de3806d`；19 列均為 `active_effective`、校準機率 6000 bp。after-cost 機率 unavailable/null，不代表 0。
- Canonical result：`rec_26fcc0776bff4c0d85c6c54787202ca8`；結果保存／讀回後，UI 機率投影與 sealed execution 的列身分核對通過。
- Capture v3：[`aa90c91d932c69919da3111da6bcb894a9591472bedb68353f3aa2a2df97fa7c.json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m10/output/_test/personal_prediction/captures/aa90c91d932c69919da3111da6bcb894a9591472bedb68353f3aa2a2df97fa7c.json)，SHA-256 `b1d2f4d2985b198990e8bf6752743a19235433708225b34f24a68ce9c3936b1d`；canonical capture readback 成功。
- Policy revision：1 personal calibrated → 2 rule-only → 3 fresh-proof rollback 至歷史 revision 1 → 4 final rule-only。歷史 target policy SHA 為 `sha256:af290ee1f685258c45f410333228e9385b18a5428a8999633a20a93d05d2b7c9`；final revision 4 policy SHA 為 `sha256:12830032c6b3e4549809896eb5c8b0a7e0b4e42dddf8fcc2eff1ebb6ec940d23`。最終 candidate/trust 已清除，global pointer 未改。
- 固定 source snapshot 為 3,827,728,384 bytes、SHA-256 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`；其 `snapshot_receipt.json` SHA-256 為 `15e1f66f496865f55f97e6e76d1bb291cb1cb842d42d29ee42b7e8905f5b0e83`。Run-local working DB `m10\data\_test\sqlite\twstock.db` 執行前後亦為相同 SHA／大小，且無 WAL／SHM sidecar。正式來源 `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` 僅可作建立 QA snapshot 的唯讀來源；m10 程序未開啟該正式庫。
- Read-only learning tree `output/qa/pc-fit-v7` 的前後 pin 均為 `3b84158f9ab5edb9420fbcbbc427f0d80ea675fa13a5a741a26824fe8d0f1105`，沒有改寫候選或 lineage。
- 畫面檔 [`personal_model_active_widget.png`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m10/receipts/personal_model_active_widget.png)（SHA-256 `b8622758e9238c9d0eeb867c3b4342180a975e48793c3cdd8e0dcd6fa437150a`）與 [`personal_model_rule_only_widget.png`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m10/receipts/personal_model_rule_only_widget.png)（SHA-256 `b7a97416942e9c4188b0f3c7b2e0cf7405c3702130d5a6806719d30bb3e0e4b5`）均由 `QWidget.grab()` 產生，是 widget render，不是 OS screenshot。

## 候選 fit 範圍與時間假設

Candidate `rec-cal-3f8b2c276ef316e28de3806d` 的 fit receipt 為 [`fit-v7-fe4e918b1257.receipt.json`](../../output/qa/pc-fit-v7/fit-v7-fe4e918b1257.receipt.json)。訓練資料含 8 檔（2308、2317、2327、2330、2344、2408、2454、3037）；history start 2024-10-24、replay end 2026-06-26，512 筆 replay samples 採用 64 個決策日（2025-11-28 至 2026-05-28）。`training_as_of=2026-05-25`、`training_cutoff=2026-06-26`；336 cutoff-eligible training rows，其中 176 OOF calibration rows、16 untouched holdout rows。標籤 horizon 為 20 sessions，固定 round-trip cost scenario 為 50 bp。特徵只使用決策日前一交易日資料；時間可得性採 user-declared、日粒度來源契約，未證同日盤中可得。Technical publication time 與 corporate-action adjustment 的獨立官方證明仍缺，因此不是 official historical PIT。Holdout Brier 為 2730 bp、50% null baseline 為 2500 bp，候選差 230 bp；這是應揭露的效果訊號，不代表工程採用失敗，也不能宣稱勝過基準。

## Stage C 與限制

同一 m10 capture 的 Stage C summary [`3c78725f8033b25f35ae21df777fc219bb20861f0bd8af2e55dbc12c140b17e4.json`](../../output/qa/stagec_m10_assessments/s10_20260928T151528958Z/personal_natural_outcomes/runs/3c78725f8033b25f35ae21df777fc219bb20861f0bd8af2e55dbc12c140b17e4.json)，summary SHA-256 `f6184b1d66c25c7ee74f26930394e82ab2554e415dbe1ab2fbfaca4f72bc00da`，payload SHA `sha256:3c78725f8033b25f35ae21df777fc219bb20861f0bd8af2e55dbc12c140b17e4`。狀態為 `completed_with_pending`、mature 0、pending 19，reason `personal_outcome_source_or_cost_incomplete`；outcome artifact 為 null、published 0、global evidence／promotion 均 false。這不是績效失敗，也沒有已成熟績效可報告。

V2 時間來源仍是 user-declared research-only，`official_historical_pit_verified=false`。此驗收不證明官方 historical PIT、正式 promotion、OS foreground／desktop input、WP1 正常日自然 scheduler 或完整 WP5 十情境通過。WP5 仍未整體完成；未來需等真實來源與成本證據成熟，再對同一 capture 明確路徑做 Stage C 評估。
