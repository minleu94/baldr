# 錯價修復後 Allocation 重訓 Runner QA（2026-09-23）

## 結果與邊界

新增的 sealed-restated research runner 已用真實封存資料完成 H5、H10、H20、H60 的 ridge/logistic fit、時間切分 heldout 評估、train-only naive baseline、不可變 release 寫入、loader readback 與 actual-now research inference smoke。這是可執行的新研究模型家族，**不是**既有 bounded 雙算法模型的修復，也不是完整正式重訓：目前僅有 2,697 列、6 檔 sample，full dataset 尚未完成建置，正式 OOS、production alpha/action、broker order 與 active pointer 都保持關閉／未變。

歷史欄位是 restated snapshot，`historical_pit=false`；時間切分只證明列的 event、成熟標籤、purge 與 embargo 順序，不把重述歷史變成歷史 point-in-time 證據。新增列沒有舊 teacher targets，meta 僅套用經原始 targets audit 驗證的固定 cash-only neutral policy，並明確不宣稱模型學會資產配置。

## 受控資料與訓練規則

- 輸入 manifest：`E:\codex_model_repair_20260923\dataset\fit_sample_2024_2026_6symbols_v3\manifest.json`，dataset identity `sha256:94eb3665394b6a0565b97c58c07c55575eb9ff22123d592060e0127f9ac93734`，manifest 檔案 SHA-256 為 `sha256:50a28c42c7f67b27e8a89eb55e0fa4138a0b7c23e8b6cd2d9cd4f9eb8228f30c`。
- 每列依封存契約驗證 62 維 feature 順序、mask、scale、schema hash；H5/H10/H20/H60 各自驗證九個 label 欄位、缺值 mask、整數範圍與 maturity timestamp。所有訓練前處理只 fit 各自 train rows；median 使用 deterministic bounded sample，最多 100,000 列，means/scales 遍歷全部選定 train rows。
- 每個 horizon 以 maturity、60 個交易 session purge 與 heldout 前 5 個 session embargo 切分；calibration 僅用 heldout 前已成熟 forecasts，calibration 兩段間另留 5 個 session。Heldout 起日固定為 `2026-05-20`，不以重複舊 2015 fold 取代修復後期間。
- 模型純 fit 沿用既有線性 head contract：`ridge_alpha_bp=100`（實際 ridge alpha `0.01`）、logistic IRLS 6 iterations、RANK_CONTRACT_V2。四 horizon candidate 使用一個 downside isotonic mapping，跨列出的 feature packs 與 horizons pooled 擬合；manifest 記錄 pooling 範圍與各 horizon 觀測數，不代表原 bounded calibrator 形狀。
- 每次訓練的 manifest 綁定 runner、CLI、frozen fit service、linear release、calibration、release contract、feature/rank/head contract 與 inference readback adapter 等 source SHA，以及 Python、NumPy、scikit-learn、SciPy、joblib、pyarrow、threadpoolctl 版本。V2 training identity 另綁 merger identity builder 的 source SHA，並記錄所讀 manifest 宣告的 dataset schema version。source SHA 在 fit 結束後重算確認未變。runner 限制程序內 OMP/MKL/OpenBLAS/NumExpr 與 threadpoolctl 執行緒上限為 2，並記錄實際 threadpool、命令列與記憶體峰值；不修改系統或使用者層環境設定。
- Heldout Parquet receipts 保存 row IDs、日期、九欄真值與逐欄 mask、模型預測及 train-only naive 預測，SHA/count 放在 `evaluation_metrics.json`，可供獨立重播。

## 嚴格 loader 與 source custody 更新

Runner 接受完整的 `portfolio-ml-restated-research-dataset.v1`，以及 A 完成後的 `portfolio-ml-restated-research-dataset.v2`。V1 以共用 identity 欄重算 `dataset_identity_hash`、`manifest_hash` 和 `dataset_id`。V2 使用 merger 公布的固定 `V2_IDENTITY_FIELDS` 和明列欄位順序重算三項 identity，並驗證 parent v1、22-symbol corrected subset、row-id patch summary、來源 alias、merge/parser/kernel hashes 與外部 sidecar 一致；實際讀取並重 hash parent/subset manifest，核對 identity、row count 及各自 revision clock。V2 的 `training_as_of` 綁 corrected subset 時鐘，`revision_observed_at` 綁 parent/subset 中較晚的觀測時鐘；每列再依 22-symbol scope 驗證真實 parent/subset row clock，不把時鐘回填成同一值。兩版都核對固定 62 欄順序/scale/hash、九 label 欄序/scale、非正式旗標、60-session purge/5-session embargo、完整年度 partition 清單、row count、byte count、每年完整 Arrow schema。每個 Parquet 開始 materialize 前及 materialize 後都核對檔案 SHA；fit 開始前、所有 heads fit 結束後再重驗 manifest、partition、lineage manifests 和 sidecar。

超過 100,000 列的資料必須提供 manifest 外的 `model-repair-source-custody.v1` JSON 與其檔案 SHA，sidecar 綁定完成狀態、manifest 檔案 SHA/identity/row count、原始 `source_hashes`、builder/kernel bytes 證據與誠實的完成/來源重查時鐘。未觀察到建置開始時的 source capture 必須保持 null，不能補寫為 start-time 證據。低於門檻的小樣本可不附 sidecar；training identity 會標成 `not_provided_small_sample`，full fit 命令不得省略。

`feature_event_asof_at` 只表示 `stock_event_date` 的 14:30 台北時間。若原 parquet 兩者皆 NULL，runner 以內部 `event_days=-1` 和空字串保留缺值，不用 `market_event_date` 代填；同時必須驗證 41 個 stock-only feature slot 全部為 null/missing。訓練依原 feature mask 保留該列並統計 dataset、fold、heldout 與 final-fit 缺事件數；最新推論拒絕沒有 stock event 的 row。V2 也逐批核對六欄原始 targets：每列只能完整保留已 audit 的 cash-only `[0,0,0,0,10000,0]` 或六欄全缺；每個欄位的 observed count 都必須等於 Direct baseline 3,353,096，絕不把修訂後 appended rows 填入 teacher target。

2026-09-23 13:31 +08:00 再以 v3 六標的樣本跑 H5-only strict loader/fit/readback：2,697 列、評估 fit 1,523 列、heldout 422 列、最終成熟列候選 2,628 列，受限 smoke fit 2,000 列；三個 feature packs fit、staged/final release loader readback 與 actual-now 六標的 inference 均通過。training manifest SHA 為 `sha256:c6796049e822c6c6f160f538f747da3fee8e7671de9dfdd88642412e3d56d630`，artifact SHA 為 `sha256:c730bed330708f3ec1fd18a42d4efe0d56bf235b1d9eecbf9dafa394931e2448`，release identity SHA 為 `sha256:a1275e7f422add5a8c587eab653704bff246090963e8566a8da2b1b6b9ba05ca`。輸出在 `E:\codex_model_repair_20260923\training\strict_v2_validator_rerun_20260923\runs\restated-repair-22f90a907a3f13af`；此小樣本明確未附 source-custody sidecar，training identity 已記錄該狀態。該 sample fit 只證明 runner 接線、不能代表 full v2 已 fit 或模型表現可靠。

這次重跑只證明新版 loader、fit、release readback 與 inference smoke 能串接，不作為最終精度評估。A 發現並修正 v1 的 OHLC/bid/ask 千分位字串漏讀；6-symbol smoke 集與受影響 22 個 symbols 不重疊。Full fit 只能使用完整修復後的 v2 dataset identity 與外部 custody sidecar；v1 全量產物保留作歷史證據，不得作為最終 full-fit 輸入。

## 實際四 horizon sample fit

命令由 repo root 執行：

```powershell
$env:OMP_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
$env:NUMEXPR_NUM_THREADS = '2'
python -B scripts/train_ml_allocation_restated_research.py `
  --manifest 'E:\codex_model_repair_20260923\dataset\fit_sample_2024_2026_6symbols_v3\manifest.json' `
  --output-root 'E:\codex_model_repair_20260923\training\four_horizon_linear_candidate_v1' `
  --horizons 5 10 20 60
```

輸出位於 `E:\codex_model_repair_20260923\training\four_horizon_linear_candidate_v1\runs\restated-repair-a119146c1eb75553`，training manifest SHA 為 `sha256:8f146cd14d17d335ea7f162bd5ac9d550ef34973757002bd97c852bfebfbb5f7`，artifact SHA 為 `sha256:ea7b67ca9c1bdb6beb6825c49695c571105342be333dc49059dc59e0f198e434`，release identity SHA 為 `sha256:4a6187b325cfc8cbf532a4d341182320e923ce6dec594816d42279910ca9de49`。Family ID 為 `baldr-ml-allocation-restated-revision-aware-ridge-logistic-h5-h10-h20-h60-rank-v2`，清楚標示這是 restated research ridge/logistic family。

| Horizon | 評估 fit rows | 最終成熟列 fit | Heldout rows | Heldout 起日 |
|---|---:|---:|---:|---|
| H5 | 1,523 | 2,628 | 422 | 2026-05-20 |
| H10 | 1,450 | 2,555 | 372 | 2026-05-20 |
| H20 | 1,322 | 2,417 | 275 | 2026-05-20 |
| H60 | 1,027 | 2,085 | 60 | 2026-05-20 |

這四 horizon sample 小於 runner 的 100,000 row candidate cap，因此各 horizon 最終 fit 使用此 sample 的所有成熟列。H5 單 horizon 預設不設 row cap；完整資料到位後的 H5 full fit 仍待執行。H60 holdout 只有 60 列，不能單獨支撐穩健結論。

Calibration 共使用 3,531 個已成熟 downside forecast（H5 846、H10 876、H20 924、H60 885；各自跨 feature packs），映射在 heldout 前 fit。資源收據記錄 peak RSS `270,503,936` bytes、peak working set `283,828,224` bytes、最低可用系統記憶體 `18,953,093,120` bytes；實際 BLAS/OpenMP pools 均為 2 threads。stage loader 與 final release loader 均通過，current smoke 在 `2026-09-23 12:40:15 +08:00` 對封存 sealed snapshot 的 6 個當前 symbols 產生四 horizon predictions；smoke 與 release 均標記 `formal_oos_allowed=false`、`production_action_allowed=false`、`broker_order_allowed=false`、alpha `0`，active pointer 未變。

## heldout 對 naive baseline 的解讀

`data_quality` feature pack 在 sample 的四個 horizons 上，ridge/logistic 的 benchmark-excess-return MAE 與 downside raw Brier score 都高於只以 train labels 均值／正例率預測的 naive baseline：

| Horizon | Heldout | Return MAE：模型 / naive（bp） | Downside Brier：模型 / naive（bp²） |
|---|---:|---:|---:|
| H5 | 422 | 381 / 371 | 22,421,470 / 22,090,371 |
| H10 | 372 | 556 / 520 | 23,258,686 / 21,124,833 |
| H20 | 275 | 1,003 / 809 | 24,414,721 / 18,820,644 |
| H60 | 60 | 3,053 / 2,220 | 26,979,566 / 18,219,769 |

其他 feature pack 亦有多項預測指標弱於 baseline；例如 `market_sector_cross_section` 的預期超額報酬 MAE 在 H5/H10/H20/H60 分別為 10,201/9,685/9,346/7,480 bp，而相同 horizon train-only baseline 為 371/520/809/2,220 bp。H60 的 heldout 樣本很小，且 pooled calibration 在部分 pack/horizon 有改善、其他組合變差。這些結果支持 runner 的可重播 fit/eval 功能，但**不支持把 candidate 升格或宣稱錯價後模型已具備可用 alpha**。

原 Direct OOC targets 的唯讀全量 audit 已由整合工作確認 3,353,096 rows 的 `target_weight/delta_weight/risk_contribution/risky_budget/rebalance` 全為 0、`cash_bp` 全為 10,000；runner 保留這個已證實的 cash-only 原語意，不替 appended rows 製造 teacher target。sector-excess labels 缺失時，對應 head 保持 missing，不複製其他 label 代替。

## 未完成項目

- 本次來源只有 2,697 rows 的 6-symbol sealed sample。daily H5 原模型的 3,353,096-row full fit 尚未執行；A 必須先完成千分位價格解析修正與 v2 sealed dataset/sidecar。之後使用不設 `--max-fit-rows` 的 H5-only 命令並附 `--source-custody` 和對應 `--source-custody-hash`，再獨立驗算 evaluation receipts、manifest binding 與 release loader。
- 已知 bounded operational model 是四 horizons 的 HGB + ridge/logistic 雙算法 family。本 runner 的多 horizon artifacts 只有 ridge/logistic，為候選研究 family；不能標記成舊 bounded model 已修復或取代原 CLI default。
- 此 runner 不接線舊 cmd 18–19、daily formal 08:30 consumer、active calibration pointer、production release root 或 formal historical PIT gate。current research entrypoint 需另外驗證其 sealed revision-aware provider/readback；本 runner smoke 不作為正式 daily readiness 證據。
- D 資料根目錄與舊 quarantine artifacts 未寫入、覆蓋或刪除。

V2 full H5 fit 的命令已固定如下；只有 root 獨立確認 A 的完整 v2 rowset/sidecar 後才執行。此命令不帶 `--max-fit-rows`，保留所有符合成熟度與時間切分規則的 H5 training rows；程序內 threadpool 上限固定為 2，訓練 manifest 記錄命令列、native thread pools、每個主要階段 RSS/peak working set 與可用記憶體。輸出使用獨立新路徑，不接觸正式 pointer 或既有 release：

```powershell
$dataset = 'E:\codex_model_repair_20260923\dataset\full_restated_v2\manifest.json'
$custody = 'E:\codex_model_repair_20260923\training\full_restated_v2_source_custody.json'
$custodyHash = 'sha256:' + (Get-FileHash -LiteralPath $custody -Algorithm SHA256).Hash.ToLowerInvariant()
python -B scripts/train_ml_allocation_restated_research.py `
  --manifest $dataset `
  --output-root 'E:\codex_model_repair_20260923\training\full_h5_repair_v2_20260923' `
  --horizons 5 `
  --batch-size 8192 `
  --source-custody $custody `
  --source-custody-hash $custodyHash
```

## 程式與測試

### 真實 v2 metadata 接線補正

Root 在完整 v2 封存後，以真實清冊查出兩處測試 fixture 未涵蓋的 consumer 錯位：corrected-subset lineage 原本漏接受其實際 `revision_observed_at`，且錯把 merge code SHA 預期放在不存在的 `patch.merge_recipe_sha256`。現在逐一驗證兩份 lineage 的實際觀測時間；merge code SHA 依既有 producer 契約綁定 `builder_code_sha256` 與 `computation_source_hashes.v2_row_merge`，patch 欄位、版本、22 檔範圍與 baseline／append counts 嚴格核對。沒有修改封存清冊來配合讀取器。

完整 v2 為 **3,496,189 列、13 年分片、62 特徵**，manifest file SHA-256 `9b0603b6df3921af1711d971b9e09e881849fdca4743e265d3798299b9a955ce`，custody sidecar SHA-256 `e0062d9af685b383d09c96400d58fb34dd555ffb5a36c4afa88b60fae2b4e9e0`。Root 全欄比對確認 37,115 列精確取自 corrected subset、3,459,074 列完整保留 parent、合併不新增列；完整 metadata／lineage／custody preflight 均通過。此處只表示全量訓練輸入已驗收，實際 fit 結果另列。

- Runner：`ml_module/restated_h5_training_runner.py`
- CLI：`scripts/train_ml_allocation_restated_research.py`
- 聚焦測試：`tests/test_restated_h5_training_runner.py`、`tests/test_restated_h5_training_input_integrity.py`、`tests/test_restated_neutral_meta_lineage.py`
- 驗證命令：`python -B -m pytest --noconftest -p no:cacheprovider tests/test_restated_h5_training_runner.py tests/test_restated_h5_training_input_integrity.py tests/test_restated_neutral_meta_lineage.py -q -o addopts=`；本次結果 `36 passed`，包含 v1/v2 manifest、完整 cash-only target、parent/subset 雙時鐘、v2 lineage/custody、load-time mutation 與 null event 測試。`py_compile` 亦通過。
