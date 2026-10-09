> **已被取代，僅供審查歷史（2026-09-22）**：本草案不再作為實作依據。請閱讀 [FINAL_ML_COMPATIBILITY_CONTRACT.md](../../01_architecture/target_architecture_2026_09_22/FINAL_ML_COMPATIBILITY_CONTRACT.md)；所有目標架構決策以 [FINAL_TARGET_ARCHITECTURE](../../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 為準。下文保留原稿供核對紅隊引用，與 FINAL 衝突的條文全部失效。

# ML 相容性保護計畫

> 架構遷移計畫，不是重訓、模型核準或資料重建授權。現有 ML 路徑初期保留；已知修訂／quarantine 與 shadow／formal 限制繼續生效。

## 1. 已核實的契約

| 資產／責任 | 原始碼依據 | 必須保持 |
|---|---|---|
| Historical feature registry | [feature_registry.py](../../../ml_module/feature_registry.py) `CORE_LONG_HISTORY_FEATURE_REGISTRY` | `core-long-history-features-v1`；20 個特徵的有序 id/dtype/unit tuple；`missing_is_not_zero`、availability policy、registry hash |
| Historical dataset／labels | [historical_contracts.py](../../../ml_module/historical_contracts.py)、[dataset_manifest.py](../../../ml_module/dataset_manifest.py)、[label_registry.py](../../../ml_module/label_registry.py) | feature／label ID、horizon、cutoff、availability、source snapshot identity；不把 observed row calendar 當官方完整日曆 |
| Historical training matrix | [historical_training_service.py](../../../ml_module/historical_training_service.py) `_matrix`、`_fit_family` | None→NaN；linear 的 median imputer（keep_empty_features）＋StandardScaler；HGB 原生 NaN；原 train/fold 邊界與 fitted transform |
| Allocation feature pack | [allocation_training_service.py](../../../ml_module/allocation_training_service.py) `FeaturePackDefinition`、`_pack_matrix` | frozen `feature_ids` 順序；`value_int / scale`；HGB matrix 後半是明示 missing mask（缺=1、observed=0）；不同演算法矩陣不可通用化 |
| OOC numeric store | [portfolio_ml_out_of_core_store.py](../../../data_module/portfolio_ml_out_of_core_store.py) L37–70 | store/year v3；values `<i8`、mask `u1`、targets `<i4`、labels `<i4`、row refs `<i8`；TARGET_FIELDS／LABEL_FIELDS 有序列表 |
| OOC row identity／fold index | 同上；[allocation_out_of_core_training_service.py](../../../ml_module/allocation_out_of_core_training_service.py) | 年度 local row index、symbol/date/custody、`(year_ordinal, local_row_index)` int64 fold reference；不因排序／rechunk 改 join |
| Direct numeric | [portfolio_ml_direct_numeric_store.py](../../../data_module/portfolio_ml_direct_numeric_store.py) L60 起 | `portfolio-ml-direct-numeric.v4`、checkpoint v2、carry v2、label contract、跨年 features／volume carry、續跑與 publication protocol |
| Direct computation identity | 同檔 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` | 指定 source paths／計算 fingerprint 影響 resume；UI 重構不應改此清單；列內檔案不能初期搬移 |
| Immutable shared blocks | [ml_direct_shared_block_resolver.py](../../../data_module/ml_direct_shared_block_resolver.py)、[immutable_ml_block_store.py](../../../ml_module/immutable_ml_block_store.py) | artifact ID/key/version、內容 hash、descriptor、原 immutable block；不重寫既有 key 指向新內容 |
| Model manifest／safe load | [model_artifact_manifest.py](../../../ml_module/model_artifact_manifest.py)、[model_artifact_loader.py](../../../ml_module/model_artifact_loader.py) | `ml-model-artifact-manifest.v1`；ordered FeatureSchema、feature/label registry hash、model family、artifact hash、library compatibility、shadow flags；先驗再反序列化 |
| Allocation release | [allocation_release_contract.py](../../../ml_module/allocation_release_contract.py)、[allocation_release_loader.py](../../../ml_module/allocation_release_loader.py)、[allocation_feature_contract.py](../../../ml_module/allocation_feature_contract.py) | 各自 release schema 與 feature contract hash，不以一般 shadow manifest 替換 |
| Recommendation calibration | [recommendation_probability_transform.py](../../../ml_module/recommendation_probability_transform.py)、[recommendation_inference_provenance.py](../../../ml_module/recommendation_inference_provenance.py)、[recommendation_training_lineage.py](../../../ml_module/recommendation_training_lineage.py) | probability transform、return basis／label contract、cost lane、training/inference lineage 分離、exact result/candidate/date identity |
| 空間與修訂保護 | [ml_storage_capacity.py](../../../data_module/ml_storage_capacity.py)、[ml_price_availability_contract.py](../../../data_module/ml_price_availability_contract.py)、[模型修訂隔離紀錄](../../06_qa/PRICE_REPAIR_MODEL_IMPACT_2026_09_22.md) | reserve／reservation／path guard、price revision marker、model quarantine；保留原 artifacts 不等於允許推論 |

此表是程式契約盤點，**不是正式磁碟 artifact 全清冊**。未逐一讀目前所有 dataset／joblib；既有文件提到的 artifact 可用性仍須以本次移轉前的唯讀 manifest/hash inventory 證明。未知版本保留原檔，拒絕猜測。

## 2. 第一輪相容邊界

```text
app recommendation／portfolio use case
  → 明示 ML projection/read adapter
  → 既有 manifest／release validator
  → 原 feature reader／原 inference
  → 原 exact projection receipt
  → application execution 的 optional projection＋quality/events
```

初期只改 caller 如何傳入 request、取得完整結果與 references；以下維持原檔案路徑／程式內容／格式：

- Direct／OOC builders、年度 shards、shared block resolvers、checkpoint／carry／source fingerprint 清單。
- Feature/Label Registry 的既有版本、feature builder／label builder、target／teacher 算法、缺值／scale／normalization。
- Trainer、split／purge／embargo、calibrator、hyperparameters、模型 selection 與 frozen exposure evidence。
- 既有模型 artifacts、fitted imputer/scaler、joblib/Python qualified class paths、release schema 與 loader 驗證。
- Production/shadow separation、active pointer／promotion／rollback authority、capacity guard。

如 caller 的 exact ML import 被 boundary guard 拒絕，只把 I/O 集中到已存在的窄 bridge，不能順手放寬 training imports。需要從 trainer 抽出 `RECOMMENDATION_RETURN_BASIS` 等 leaf contract 時，先檢查它是否進入 computation hash／serialized class path；是則獨立版本遷移，否則同值抽取＋舊 re-export＋guard 測試。不要直接改 frozen trainer 來滿足一般分層美觀。

## 3. Schema versioning，不做自動格式升級

分開五個版本軸：

| 軸 | 何時變更 | 不可混用 |
|---|---|---|
| data/wire schema | 欄位、dtype、shape、mask／row index encoding 改變 | 同名 feature 不保證 binary compatible |
| feature contract | feature ID/order/unit/scale/window/missing/availability 語意改變 | 新排序不能沿用舊 registry hash |
| transform contract | fitted preprocessing、scaling、imputation、matrix construction 改變 | 不能用新 scaler 配舊模型 |
| label/target contract | horizon、benchmark、成本、maturity、return basis、teacher 改變 | 新 label 不能冒充舊 outcome |
| artifact/release | model／library／serialization／permissions／freeze identities 改變 | 可載入不等於允許 production |

版本號便於導航，**hash 與完整 schema 才是相容判定**。新模型必須聲明支援哪個精確組合；reader 用明確版本 dispatch，不以「最新」自動嘗試。

對既有 artifact 不回填新 metadata 以改變 hash。若需補相容說明，新增外部 sidecar，記 original byte hash、producer/version、實際驗證範圍、adapter version；sidecar 不追認未知 available time，也不修改既有 manifest hash。

對無 manifest／dtype 證據的舊資料，最多提供明示 legacy reader 作研究檢視，標 unknown／unverified；無法確認欄位順序時不能送 model 推論。

## 4. 舊 numeric datasets 如何持續可用

1. 移轉前對已授權範圍做只讀 inventory：schema/hash、feature order、dtypes/endianness、shape、mask coding、row key、fold refs、source revisions、producer computation identity、dependent models。
2. 舊 reader 原樣可讀既有 immutable bytes；application adapter 接受舊版 contract，返回原 semantics。與推薦 execution 改成 typed envelope 無關的 dataset 不重算。
3. 選擇 row 的依據是既有 row identity／index，不能以 DataFrame 新排序後的位置拼接。shared block 仍讀原 descriptor 與 hash，保留跨年度 carry。
4. 數值轉換僅在原 ML matrix boundary：int/scale→浮點、None／mask→NaN 依既有 policy；不能全系統把 int store 改 float32／float64，也不能換 endian、mask 極性或將缺值填 0。
5. 同 model、同 library 環境、同 input、同 transform 的 prediction 應保持一致；舊資料因價格修訂或 quarantine 而被既有 gate 拒絕時，拒絕本身也是相容行為，不能為「可用」而解除保護。
6. 若新版 reader 不支援舊 schema，明示 unsupported 並仍提供已測試的舊 decoder；不原地改檔。歷史 decoder 只解碼，不保留第二套 trainer/evaluator。

## 5. 新增一個 ML feature 的受控方式

假設新增 `turnover_stability_20d_bp`：

1. 在新 feature registry/version 定義 ID、dtype、unit/scale、順序、window、availability、missing policy；不 append 到舊常數並沿用舊 hash。
2. 現有 v1 的 reader、model、20-column matrix 保持原樣。新 feature calculator 只依當時可得資料；新 registry 對沒有此資料的 rows 明示 missing，不給舊資料合成未知值。
3. 新 dataset 有兩種成本選擇，但只有一套語意：可建新的 bounded publication；若既有 immutable extension 機制能綁 exact row identity／hash，則將新 feature 保存於新 block／sidecar，base block 原樣重用。**現有 monolithic binary 不支援加欄時，不承諾零重算**；需容量核準後建立新 artifact。
4. Join 必須驗證同 symbol/date/row ID、no duplicates／missing keys、source cutoffs、parent hashes，不能按列號盲接。新 feature 不具備時按新模型明示 policy 拒絕或缺值處理。
5. 新模型使用新 schema/order/transform，產生新 model/release。舊模型可繼續用其精確 v1 view；只有經註冊、驗證為同值同序的 projection adapter 才能把新資料投影回 v1，不能單純丟掉一欄就自稱相容。
6. 新 dataset 不使舊訓練資料失效；新模型亦不自動取代舊 active pointer。照原 shadow／promotion gate 判定。

## 6. 必做的相容驗證

| 層級 | 測試輸入與 oracle | 驗收 |
|---|---|---|
| binary／manifest | 小型保留 fixture：正常、missing、真 0、極值、年度邊界、不同 schema | bytes/hash 未改；dtype/order/shape/masks 精確相同 |
| row/fold linkage | 同 symbol/date、跨年、缺中間日、重複 key、缺 feature block | 原 row refs／fold membership 相同；錯 join 被拒絕 |
| transform | 原 fit data、fitted imputer/scaler 與已保存 transform | train-only fit 不變，推論不 fit；全缺欄位維持 shape |
| model load | wrong schema/order/hash/library、quarantined model、unknown version | 反序列化前拒絕，原 fallback/blocker 可追溯 |
| prediction | 原模型＋固定 input＋相同版本環境 | 對整數 bp/public outputs exact equality；浮點中間量若非 bitwise，需先制定按欄位 tolerance，禁止通用寬鬆誤差掩蓋差異 |
| resume | 原 checkpoint＋同 source fingerprint；新增程式碼 fingerprint case | 同 fingerprint 正常續跑；不同 fingerprint 保守拒絕，不混寫同 run |
| governance | shadow projection 與 rule selection、cost lane、natural evidence | top-N／Rule 不改；沒有新 formal/natural credit |
| storage capacity | tiny tmp fixture 注入 bounded probe＋低空間負例 | production reserve 不降低、不重訓、不建立大型正式產物 |

現有測試起點：`test_ml_model_artifact_manifest.py`、`test_ml_model_artifact_loader.py`、`test_ml_direct_numeric_shared_reuse.py`、`test_ml_shadow_dependency_boundary.py`、`test_recommendation_training_lineage.py`、`test_recommendation_service_calibration_integration.py`。完整實作驗證依變動檔案再選 route，不將本文件的測試計畫寫成已執行。

## 7. 之後才可整理的內部責任

等 execution/save boundary 穩定、legacy dataset inventories 與 compatibility fixtures 成立，再獨立處理：CLI 私有 parser 移入 ML codec、trainer contracts 抽 leaf、Direct builder 依 publication／assembly 分割。每項都先量測對 source fingerprint、resume、serialized class path 的影響。

若確實改變 computation identity，產生新 run/schema/artifact；保留舊 readonly result readers 與有明確期限的舊 producer import aliases，決定既有未完成 checkpoint 是用其原環境完成、停止，還是以新 identity 重啟。不能靠改 hash 清單／偽造原 fingerprint 避免 conflict。

## 更新記錄

- 2026-09-22：盤點現行 historical／allocation ML 契約，制定保守相容與新特徵演進計畫；未重訓或變更 ML 程式。
