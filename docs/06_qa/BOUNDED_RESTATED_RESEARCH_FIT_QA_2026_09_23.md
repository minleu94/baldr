# Bounded 全特徵重述研究模型：實際 fit、OOF 與當日 heads readback

本紀錄驗收 2026-05-20 價格修訂後，原 bounded 22,093 列資料的四個 horizon labels 與 62-slot features 重算、新版研究模型 fit、base OOF 成效，以及當日 heads-only readback。所有輸出均為 `restated_research`：晚期修訂實際可用時間保留為 2026-09-23；資料不是歷史 PIT，不是正式 OOS，不可用於 production action、promotion 或 release。

## 官方市場 v3：本次最新結果

官方交易日及真實 OHLC／成交股數修訂後，17,285 列保留、4,808 列因股票價格路徑不完整排除，原資料仍保留。新四個測試日期窗不變，fold-002 訓練截止日收緊，確保原 trainer 的 60 日 purge；四 folds train/test 為 1,318/1,953、3,394/3,472、6,887/3,950、11,145/4,284。新資料、實際 fit、來源與模型 hashes 見[大盤來源核對](MODEL_REPAIR_MARKET_SOURCE_AUDIT_2026_09_23.md)。以下較舊 v2 結果不能直接與 v3 比較優劣，因樣本母體與 fold 訓練數已改變。

獨立 verifier 不匯入 trainer，從保存的分片 labels 與 base OOF array 逐筆驗算：**327,816 筆、13,659 個 unique test rows、96 個 algorithm/horizon/pack/fold 群組**。每組的 row IDs 恰等於該 fold 完整測試集合；train-only 基準依實際有效訓練截止日及成熟 labels 計算。全程整數累加、Decimal 彙總；來源分片與 audit 前後 hashes 一致。每個 pooled algorithm/horizon 的 n=40,977 包含同列三組特徵預測，不是獨立樣本數。

| Horizon | Ridge MAE bp | HGB MAE bp | Train-mean MAE bp | Ridge downside Brier | HGB downside Brier | Train-prevalence Brier |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 218.55 | 222.85 | 215.06 | 0.22469 | 0.22420 | 0.22315 |
| 10 | 320.85 | 338.68 | 313.39 | 0.23648 | 0.23680 | 0.23424 |
| 20 | 479.99 | 493.50 | 465.92 | 0.24430 | 0.24291 | 0.24132 |
| 60 | 898.67 | 921.27 | 853.46 | 0.25486 | 0.25218 | 0.24501 |

兩算法、四期間的 pooled 報酬 MAE 與 downside Brier 均不優於同母體 train-only 基準。24 個 per-pack 表也保留；少數分類分數較佳不代表整體達標，未以 heldout 選新 winner 或調參。本驗算不涵蓋校準後 ensemble、實際策略成本績效或歷史 PIT 有效性。

證據為 integration `output/qa/model_repair_review/bounded_official_v3_oof_independent_metrics.json`，file SHA `cdb2267ce4e79dd1ed10d062c77ef7ca399f5f367114e6bd53c277f2eadfb664`；verifier SHA `a9de38f7a803cd0e356647c10e4768097be567cdb1ce28625ba93a18fe42fd66`。實際 model fit、獨立評估與新資料推論均完成，但**品質不支持正式使用**。

後續補查全部九種 base heads，逐筆覆蓋 864 個 algorithm/horizon/pack/fold/head 群組，報酬／downside 與前述獨立結果完全相同。五個風險幅度 heads 中，HGB 部分波動、尾損及回撤的 MAE 比基準低，例如 H5 波動 56.98 對 58.81 bp、H60 波動 54.33 對 55.79 bp；這些描述性分數沒有多重比較或顯著性驗證，不授予品質 gate。產業超額報酬全部缺標籤。成交可行性每個 algorithm/horizon 有 5,859 個缺 prediction（第一 fold 三 packs）；其餘 35,118 個有輸出的列上，Ridge Brier=0.01035、HGB=0.00026、同列 train-prevalence 基準=0.00026。不能把缺輸出列剔除後的成績當作全覆蓋，也不能用極不平衡標籤的近滿分 accuracy 宣稱模型有用。

全 heads 結果保存 `output/qa/model_repair_review/bounded_official_v3_all_heads_metrics.json`，file SHA `0a766d2f4fe784424994110779c22961ce4ef19c13a34a9eb45c358b856693c2`，verifier SHA `10e5420527ae3fc033a2188f8ca650fc10e9f3ee4e43985b9af538416b720253`；同時包含 pooled／per-pack 指標及缺 truth／prediction 數。只驗算 base OOF，沒有重調參數或改動模型。

## 封存資料與 fit

輸入是隔離封存的 run02 snapshot，檔案 SHA-256 為 `38ab1d1dfd201285ed817c8e94f689f91a50b39dc30cdbb8a90a49b7ce898771`。新資料集目錄為 `E:\codex_model_repair_20260923\bounded_fullfeature_label_restatement_20260923_v2`，manifest 檔案 SHA-256 為 `5b554b231ed0c3f57322aab8c0c9c09742743662747fdc95ea1ce0a7b984bd19`，canonical manifest identity 為 `sha256:cbac586973eab97b328fff000afa0d5cbbb7588ed98b86014901885578ab17e6`。嚴格 readback 載入 13 個年度 shards、22,093 samples、62 slots 與 4 folds。

每列重算 20 個 technical slots 及 5 個相依 quality/missing slots；實際重述時間為 `2026-09-23T05:32:46.127133+00:00`。相較原 bounded rows，原 37 個未重述 feature payload 共 817,441 項維持一致；25 個重述 payload 共 552,325 項，其中 84,758 個值改變。210 個 H60 labels 改變，其他 88,162 個 horizon labels 完整一致；row order、targets、portfolio state、label maturity/calendar 均保留。2014-01-03 的 1101 row 之 20 個 technical 值全 missing，符合沒有暖機歷史時不補值的規則。來源差異原因只記為「無可核驗暖機／晚期有數值差異；120 尾窗並未重現本樣本差異」，沒有把 bfill 或 120 尾窗推定為本樣本已證實根因。

fit 輸出在 `E:\codex_model_repair_20260923\bounded_fullfeature_label_restatement_20260923_v2\training_run01`。實際傳入的設定是 `random_state=42`、`hgb_max_iter=60`、`ridge_alpha=1`；算法為 `ridge_logistic` 與 `hist_gradient_boosting`，horizon 為 5／10／20／60，共 3 packs、4 outer folds。這些是本次明確傳入的服務參數，沒有宣稱是原歷史 bounded 訓練 recipe。Python 3.11.9、numpy 2.3.5、scikit-learn 1.8.0、threadpoolctl 3.6.0，fit threadpool limit 為 2。

| 產物 | SHA-256 |
| --- | --- |
| `bounded_restated_research_model.joblib` | `0a9f7a9c399c379d4bed5b98ec124db5661f9358c21d523477dedafe4f04b7e6` |
| `allocation_training_audit.json` | `5353d8d124b857b917a11a64910cded95ea141ca30e44b4af2900f09e47a4063` |
| `fit_receipt.json` | `543f6293da39ad7f1fbaea016dd3b905483c7ea3811714c17cddff6dc43c490f` |

receipt 確認 model、audit、dataset manifest hashes 一致，fit 前後輸入檔與 source-code hashes 不變。狀態為 `completed_research_only`，`historical_pit=false`、`formal_oos_allowed=false`、`production_action_allowed=false`、`promotion_eligible=false`。

## OOF 評估

`allocation_training_audit.json` 沒有 aggregate accuracy 表。本輪以 mmap 串流讀取 audit 的 base OOF array，將 426,624 筆 predictions 與封存 dataset labels 對齊重算，逐筆處理 237,126,161-byte audit。unique outer-test universe 是 17,776 rows；下表每個 algorithm/horizon 的 `n=53,328` 是這 17,776 個 row 各由 3 個 feature packs 預測後合併的數量，不是 53,328 個獨立樣本。初版摘要的逐 fold 結果同樣 pool 三 packs；Root 的後續獨立驗算另保存 per-pack 分表。

fold train/test row counts 與 fit receipt 完全相符：

| Fold | Train rows | Test rows |
| --- | ---: | ---: |
| fold-001 | 1,967 | 4,792 |
| fold-002 | 6,788 | 4,750 |
| fold-003 | 11,653 | 3,950 |
| fold-004 | 15,911 | 4,284 |

預期超額報酬以 bp 計 MAE；train-mean baseline 是逐 fold、逐 horizon 以 outer-train labels 計算，zero 是固定 0 bp baseline。Downside Brier 比較同 fold train prevalence。數值不支持模型勝過 naive：

| Horizon | Ridge MAE | HGB MAE | Train-mean MAE | Zero MAE | Ridge downside Brier | HGB downside Brier | Train-prevalence Brier |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 214.51 | 213.12 | 210.98 | 227.11 | 0.22243 | 0.22238 | 0.22207 |
| 10 | 307.35 | 305.55 | 301.53 | 314.73 | 0.23399 | 0.23510 | 0.23352 |
| 20 | 451.06 | 449.57 | 441.82 | 452.35 | 0.24343 | 0.24498 | 0.24101 |
| 60 | 842.53 | 834.56 | 804.46 | 811.64 | 0.25393 | 0.24775 | 0.24460 |

Downside accuracy 也沒有高於 fold-train majority baseline。按 H5／H10／H20／H60 順序，Ridge 為 66.744%／63.004%／58.056%／55.987%，HGB 為 66.787%／61.396%／57.255%／57.390%，majority baseline 為 66.787%／63.023%／59.743%／58.067%。HGB H5 與 baseline 在顯示精度相同；並非勝出。Fill-feasibility 標籤 99.969% 為正例；Ridge 與 HGB 第一 fold 的 14,376 個 pack predictions 沒有可用分類 head，其餘 38,952 個 predictions accuracy 均為 99.969%、Brier 約 0.00031，與 train baseline 相同或近乎相同，不能視為模型已學到有效區辨訊號。

Metrics JSON：`C:\Projects\PythonProjects\technical_analysis\output\qa\model_repair_source_20260923\oof_metric_summary.json`，SHA-256 `1215cefddc24e95add662bbbcdbf348b418cf7696fe44fe22a4b09929fde19d2`。計算程式：`C:\Projects\PythonProjects\technical_analysis\output\qa\model_repair_source_20260923\bounded_oof_metrics.py`，SHA-256 `67ef6f9e515e9b33ba53948bbfc0568e03f11a119af6d8028e7937483e8899a7`。JSON 包含每個 algorithm/horizon 的 regression/classification aggregates 及 per-fold metrics；未產生 per-pack 分表。

這些 outer-window predictions 是用晚期重述 features fit 的 research event-maturity fold 結果，不可稱為 historical OOS：技術與 quality revisions 的實際 availability 在歷史 decision 之後。不可把這些分數推廣成外部、正式或策略績效證據，亦未選出 holdout winner。

Root 另以不匯入 trainer 的 QA 程式，採整數累加、Decimal 計算基準及彙總，獨立驗算上述 **48 個 pooled 數值**，全部一致。96 個 algorithm／horizon／pack／fold 群組均逐筆檢查 row ID 唯一、恰好等於各 fold 完整 test set、日期一致與機率範圍；總計 426,624 筆，來源清冊、13 份資料分片與 audit 前後 hashes 不變。結果位於 integration worktree 的 `output/qa/model_repair_review/bounded_oof_independent_metrics.json`，內含 24 個 per-pack 分表、來源與 verifier SHA；腳本為同目錄 `verify_bounded_oof_metrics.py`。此步未重播模型，也未驗算校準後 ensemble、fill-feasibility 或策略績效；不以 pooled 比較取代這些尚未評估的能力。

## 當日 bounded heads-only readback

獨立 current research readback 使用當日新鮮 capture：`captured_at=2026-09-23T13:44:52.076330+08:00`、`feature_asof=2026-09-22`。13 檔（含 1256、1477）共輸出 312 個 expert heads；312/312 `neutral_fallback=false`。probability/rank 均為 0–10,000 整數基點，return/risk 為整數；只有 sector excess head 缺失（312 筆），其他 heads 正常。這是 heads-only readback，沒有產生資產配置或 production action。

readback receipt：`E:\codex_model_repair_20260923\current_inference\bounded_full_run01\bounded_current_heads\dc496e0f87a583ac9b5538c33650c27e5603cf0ecadff66b2093eaecdef1fa55.json`，receipt file SHA-256 `369c7095bbf865f1db990c249f5de656d04805792b898f5bfed0131f9f6e6451`。

## 驗證結論

- v2 strict readback：22,093 rows、62 slots、13 shards、4 folds 完整通過。
- full training：fit 成功且 hashes 穩定；audit OOF 426,624 predictions 與 sealed labels 完成指標重算。
- current heads readback：312/312 無 neutral fallback，型別與範圍通過。
- targeted mypy：3 個新增 source modules 無型別錯誤；bounded label/full-feature tests 為 16 passed。
- 所有研究 artifacts 均有獨立 identity；沒有載入或覆寫既有 frozen model，也沒有改 formal database、release pointer 或 production artifact。
