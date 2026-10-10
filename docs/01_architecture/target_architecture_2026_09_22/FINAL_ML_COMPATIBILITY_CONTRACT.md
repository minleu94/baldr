# 最終 ML 相容性契約

> **狀態：最終設計基線（2026-09-22）；完整目標尚未全域完成，部分 bounded slices 已有接受記錄。** [FINAL_TARGET_ARCHITECTURE.md](FINAL_TARGET_ARCHITECTURE.md) 是本輪唯一設計權威；本文件是其 ML 規範分冊，細化資料、模型與遷移契約，不建立另一套目標架構。既有 [ML_COMPATIBILITY_PLAN.md](../../09_archive/target_architecture_2026_09_22/ML_COMPATIBILITY_PLAN.md) 留作上一輪提案追溯，衝突處依最終主文與本分冊。本文件不授權重訓、資料重建、正式寫入或 promotion。

**2026-09-27 dated acceptance addendum：** 使用者接受另立 R027 logical-time revision B；Root其後依frozen source diff、R028 full8與獨立source/runtime review接受scoped R028 migration。此決策不改寫本分冊原 strict gate、Direct／OOC identity、artifact ABI或任何既有 `INCONCLUSIVE` receipt。原R027 strict仍INCONCLUSIVE，原oracle/raw receipts保留。詳見 [R027 logical-time acceptance revision](../../06_qa/R027_LOGICAL_TIME_ACCEPTANCE_REVISION_20260927.md) 與 [R028 implementation report](REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md)；R031 attempt6 當時的 relevant regression及mandatory checks已由root接受；本紀錄為提交前snapshot，staged review與commit結果以Git history及root最後交付為準。原strict與artifact/identity邊界不變。

本分冊已讀取 [紅隊審查](ARCHITECTURE_RED_TEAM_REVIEW.md) 及 [必要變更](ARCHITECTURE_REQUIRED_CHANGES.md)。紅隊的 ML 中途取資料風險納入必要設計邊界。原第 7 項實驗要求是 2026-09-22 設計時狀態；其後 [R028 scoped production migration](REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md) 已接受 `TechnicalIndicatorJob` orchestration 切片，但該接受不等於整個 ML frozen-input／feature materialization／artifact compatibility 目標全部完成。

## 1. 永久目標與第一輪凍結

永久目標是「application 明示安排資料準備與推論；ML 計算只消費已綁定的資料版本」，並非把所有 ML 資料塞入推薦 `MarketSlice`。ML 可以有自己的 data provider，其 I/O 必須出現在明示的 prepare／resolve 階段；進入 build／infer 後不得暗讀目前 SQLite、CSV、latest pointer 或重新解析來源。

第一輪保持既有 producer、Direct／OOC builder、trainer、feature／label builder、store、loader 與現有讀取模式。以外側 adapter 封存原執行結果與 provenance，先不改內部查詢順序、來源選擇或更新同步方式。**凍結例外不是最終邊界已達成的證據**；不能將新的 envelope 宣稱為已隔離所有 live reads。

| 責任 | 永久 owner | 依賴限制 |
|---|---|---|
| 原始 observation、availability／revision、來源 custody、storage wire／reader／writer | `data_module` | 純紀錄契約不 import provider、ML trainer 或 app；storage adapter 可依賴必要 ML leaf record |
| feature ID／順序／單位／缺值、label／target／training record、transform、model／release contract | `ml_module` | 純契約不 import trainer、DB／HTTP、CLI 或 app；計算消費 frozen records |
| ML 專用來源取得 | 明示 data provider；由 application 注入與安排 | 可查 source／store，但只在 prepare／resolve；不能由 projection 偷偷觸發 |
| 跨來源 assembly 與 publication／training job 協調 | application 的對應功能 use case／job | 排程 prepare→build→infer／publish；不得自定 feature／label 語意 |
| 推薦結果與 ML projection 的身份綁定、執行 outcome | application recommendation | Rule selection 與 ML annotation 分離；保存 exact receipt 及缺值原因 |

現有逆向邊須列管：`portfolio_ml_direct_numeric_store.py` 與 `portfolio_ml_dataset_assembler.py` 匯入 trainer 的 `AllocationTrainingSample`；`historical_feature_builder.py` 由 snapshot provider 匯入 observation types；OOC store 由 CLI 匯入 `_parse_sample`。目標分別是 ML training leaf contract、data observation leaf contract、ML codec；第一輪不為移除 import 而改動凍結 source bytes。後續改動必須依第 5、7 節獨立驗收。

## 2. PreparedMLInput 與單次 execution 的一致性

下列為目標 API／資料契約，不是現有已實作類別：

```text
application 建立 execution identity／decision cutoff
  → 明示 prepare／resolve（ML data provider）
  → PreparedMLInput（實際資料或不可變、可驗 hash 的 artifact reference）
  → build（固定 feature／transform contract）
  → infer（固定 model／release）
  → validate／publish exact projection receipt
  → 封存 RecommendationExecution
```

`PreparedMLInput` 的目標位置為 `ml_module/prepared_input_contract.py`，只保存必要身分 scalar／純 record，不 import app 的 execution 型別。它是 ML 輸入的獨立契約，不假定 `MarketSlice` 含有 ML 所需歷史窗口、模型特徵或來源欄位。主 execution 僅保存必要身分、摘要與不可變 reference；大型矩陣不複製進 UI DTO。至少綁定：

| 契約部分 | 必要內容與驗證 |
|---|---|
| execution binding | `result_id`、exact candidate identity 集合及對應 symbol、`decision_at`（含時區）、決策日、`as_of`／feature cutoff、mode；不能只以股票代號配對 |
| consumed input | 實際消費的 dataset／source snapshot ID、schema version、內容 hash、row identity 與範圍、來源 revision；不存在 dataset ID 的即時 bounded snapshot 必須有可驗 snapshot identity，不能編造 dataset ID |
| availability | 各來源可得時間、資料期／觀測日、品質／缺件、PIT／current／research status；unknown 不可補成決策當時已知 |
| feature binding | ordered feature schema、registry hash、transform contract hash／version、缺值規則；training source hash 與此次 inference source hash 分開 |
| model binding | 固定 model／release ID、artifact hash、受支援 library contract、quarantine／shadow／權限狀態；active pointer 只在明示 resolve 時解析 |
| ownership | deeply immutable values／defensive copy 或內容定址的 immutable reference；不可保留可變 DataFrame、live connection 或 latest-path 作已凍結證據 |

Rule 與 ML 可使用不同、已明示的 snapshot，但都必須遵守同一 execution 的決策 cutoff；只對共用來源／欄位驗證其應有一致性，不能要求不同 training/inference snapshots 的 hash 相等。若需以 Rule 選定 candidate 後縮小 ML 集合，ML provider 只能從已固定版本解析該集合，不能取稍後更新的資料冒充原 execution。

不能固定資料版本時，第一輪維持經基線驗證的舊 call order 與既有更新互斥；互斥範圍須涵蓋實際來源讀取窗口。僅有「先讀 Rule，再讀 ML」的順序不足以證明一致性。無法證明 cutoff／版本／共用來源一致時，拒絕此次 ML projection，記錄 unavailable／blocked 原因，保留 Rule outcome；禁止以現在的 DB hash、事後 timestamp 或補寫 sidecar 偽造一致性。

ML 不改 Rule top-N、排序、filter 或交易權限。Execution 封存精確 receipt 的 ID／hash／candidate／date／cost lane，以及 missing、schema mismatch、quarantined、source version unavailable 等結果；缺 projection 不補 0。既有 receipt 先發布再封存結果的副作用順序必須保持可觀察，保存失敗不可偽裝成 ready。重讀／保存 execution 不重新推論、不重讀 active pointer，也不以新 projection 覆寫舊結果。

原始碼定位：[歷史 feature builder](../../../ml_module/historical_feature_builder.py) 的 `HistoricalFeatureBuilderLoadContract`／`HistoricalFeatureBuilder.load`；[推論 provenance](../../../ml_module/recommendation_inference_provenance.py) 的 `build_inference_provenance`、`validate_provenance_compatibility`、`build_inference_projection_receipt`；[consumer](../../../app_module/recommendation_calibration_consumer.py) 的 `project`。這些既有契約可重用，但不等於目標 `PreparedMLInput` 已存在。

## 3. 必須保持的 numeric／artifact ABI

| 範圍 | 凍結契約 |
|---|---|
| Historical registry | `CORE_LONG_HISTORY_FEATURE_REGISTRY` 的 `core-long-history-features-v1`、20 個有序 id/dtype/unit、registry hash、`missing_is_not_zero`、availability policy；不只比較欄位集合 |
| Historical matrix | `_matrix` 的 None→NaN；原 linear median imputer／`keep_empty_features`／StandardScaler 與 HGB 原生 NaN；fit 僅限原訓練 fold，不在推論重新 fit |
| Allocation matrix | `FeaturePackDefinition.feature_ids` 的順序；逐特徵 `value_int / scale`；HGB 矩陣後半 missing mask 為缺=1、observed=0；其浮點矩陣布局與 store 的獨立 u1 mask 檔分開驗證 |
| OOC binary | `portfolio-ml-ooc-store.v3`、year v3、checkpoint v1、fold-index v1；values `<i8`、mask `u1`、targets `<i4`、labels `<i4`、row refs `<i8`；保留 endian／shape／欄寬與各欄位順序 |
| 缺值與零值 | OOC feature／label masks 為缺=1、observed=0；保留原 sentinel／nullable contract 與各矩陣轉換；缺資料不等於真 0，不以新 imputation 默默改舊值 |
| Row／fold linkage | 年度 local row index、symbol/date/custody，`(year_ordinal, local_row_index)` int64 fold refs；排序、rechunk 或延伸 block 不可改 join 身份 |
| Direct | `portfolio-ml-direct-numeric.v4`、checkpoint v2、carry v2、label contract v1、跨年 feature／volume carry、manifest-last／atomic publication 與原 resume 驗證 |
| Label／target | horizon、maturity、teacher、benchmark、return basis、成本 lane、split／purge／embargo；observed row calendar 不冒充官方完整交易日曆 |
| Immutable blocks | 原 artifact ID／key／descriptor／version／hash／parent custody；同 key 不可指向新內容，不改既有 bytes 或 source revision |
| Model／release | 模型 family、feature／label registry、ordered schema、fitted transform、hyperparameter／training identity、joblib bytes／hash、Python qualified class paths；allocation release 與一般 shadow manifest 各用原 validator |
| Library／source ABI | 依各 loader 原支援版本驗證，不以「同大版」概括；例如 `ModelArtifactLoadContract.validate` 比較 library major/minor。搬 module、改 class path 或 source fingerprint 均需獨立相容決議 |
| Safety gates | price revision marker、quarantine、capacity／reservation／path guard、candidate／formal、shadow／production、active pointer／promotion 權限；原拒絕與降級也是必須保持的行為 |

OOC 的有序欄位必須保持：

```text
TARGET_FIELDS = target_weight_bp, delta_weight_bp, risk_contribution_bp,
                risky_budget_bp, cash_bp, rebalance_worthwhile
LABEL_FIELDS  = benchmark_excess_return_bp, sector_excess_return_bp,
                downside_observed, mae_bp, mfe_bp, realized_volatility_bp,
                max_drawdown_bp, tail_loss_bp, fill_feasible_observed
```

ML 的浮點運算限既有 matrix／estimator 邊界；公開金融結果回到原 int／bp／scaled contract。不得趁架構整理把整數 store 換 float32／float64，或更動 Decimal／捨入政策。

以上依據：[feature registry](../../../ml_module/feature_registry.py)、[historical trainer](../../../ml_module/historical_training_service.py)、[allocation trainer](../../../ml_module/allocation_training_service.py)、[OOC store](../../../data_module/portfolio_ml_out_of_core_store.py)、[Direct store](../../../data_module/portfolio_ml_direct_numeric_store.py)、[model manifest](../../../ml_module/model_artifact_manifest.py) 與 [allocation feature contract](../../../ml_module/allocation_feature_contract.py)。這是 source contract 清冊，尚不是正式磁碟上的 artifact 全清冊；不得宣稱所有既有模型已通過載入測試。

## 4. 新技術指標與舊資料／舊模型共存

新增 analysis 技術指標只改該指標的計算／參數／publication 契約，不自動加入 ML。ML 明確 opt-in 後，才建立新 feature registry／contract、dataset publication、transform 與 model／release；不得 append 至舊 v1 常數卻沿用舊 hash。

既有 20 欄資料、reader、模型、順序與 fitted preprocessing 保持原樣。新 rows 缺該特徵時依新契約記 missing，沒有決策當時資料就不能補造歷史值。新版本可以使用新 artifact；只有既有 immutable extension 機制確實支援時，才重用原 base block 並另發布 feature block。延伸 join 驗 exact row identity、唯一性、缺鍵、parent hash、cutoff 與 availability；不按列位置拼接。

不支援加欄的 monolithic binary 必須建立新 artifact，不能承諾零重算或零額外容量。新資料投影為舊模型輸入，必須經版本化 adapter 證明原欄同值、同序、同尺度、同缺值及同 cutoff；丟掉新增欄本身不構成相容證明。新模型不自動取代 active pointer，也不授予 formal／natural evidence credit。

## 5. Direct source identity 與凍結清單

以下 15 條路徑逐項取自現行 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS`，不是從整個 repository 推導，也不得為了讓 guard／resume 通過而縮小清單：

```text
data_module/portfolio_ml_direct_numeric_store.py
data_module/portfolio_ml_dataset_assembler.py
data_module/portfolio_ml_out_of_core_store.py
data_module/ml_storage_capacity.py
data_module/ml_pit_shared_block_resolver.py
data_module/ml_direct_shared_block_resolver.py
data_module/formal_portfolio_ledger.py
data_module/rule_champion_snapshot_service.py
data_module/teacher_input_source_producer.py
ml_module/allocation_training_service.py
ml_module/allocation_contracts.py
ml_module/allocation_teacher.py
ml_module/immutable_ml_block_store.py
ml_module/purged_walk_forward.py
data_module/ml_price_availability_contract.py
```

`_direct_computation_dependency_payload` 保存 build-start 的 disk source custody。`_stable_direct_computation_identity_payload` 以排序後的 `path`、source byte SHA256、compiled-source fingerprint 建立持久 identity，明示排除 loaded module／runtime constants。`_dependency_payloads_compatible` 另檢查進程中已載入 module／code／constants 不變性，並處理合法 lazy import。**兩者是不同驗證，不可把 runtime constants 寫成 stable identity 的組成。**

凍結包括路徑與 source bytes；只改註解也會改 byte hash。後續搬檔、抽函式、contract re-export、alias 不能預設透明。若 identity 改變，建立新 run／artifact identity；不把純 source 搬移自動稱為 data schema 改版，各版本軸分開決定。舊未完成 checkpoint 必須明示採原環境完成、停止或新 identity 重啟，不把新程式混寫同一 run，不偽造原 fingerprint。

Owner：ML/data contract 維護者共同保存 source 清冊與 artifact dependency inventory；application owner 負責外側接線。本凍結直到第 7 節實驗及相容驗收成立前有效，不能以架構文件定稿作解除依據。

## 6. 永久讀取支援與暫時 runtime 機制

| 機制 | 性質 | 刪除條件 |
|---|---|---|
| 歷史 schema decoder | 目標架構的持久讀取責任 | 受支援 artifact 留存期限結束或獨立受控移轉完成；一般遷移完成不構成刪除理由 |
| 必要 joblib qualified class-path 支援 | 持久 artifact ABI，不是第二套 trainer | 實際 artifact inventory 證明不再依賴，或完成另行核准的轉換與原模型 load／prediction 回歸 |
| 一般 caller import re-export／舊 façade | 暫時 runtime 相容 | exact caller inventory 為零、外部支援期結束、動態入口及序列化依賴皆排除、回滾驗證完成 |
| 暫時 ML 外側 adapter | 遷移接線 | 新 prepare／resolve 路徑通過一致性驗收，所有 caller 遷移；不得移除仍承擔永久 I/O port 的正常 adapter |
| source-path／跨層 import 凍結例外 | 暫時技術限制 | 新 ownership、identity／checkpoint 處置與舊 artifact 讀取驗收全部成立；未完成前不得宣稱最終依賴規則已達成 |

具體序列化證據：`historical_training_service.py` 的 joblib payload 含 `ResearchBlendPolicy` 與 fitted calibrator；`allocation_training_service.py` 的 `_ConstantProbabilityClassifier` 可進入最後模型。僅搜尋程式碼 import 為零，不能證明這些路徑可刪。歷史 decoder／類別相容只服務讀取與原語意，不複製第二套可修改的 trainer／evaluator，不重算或覆寫舊 artifact。

未知 schema、缺 manifest／dtype／順序證據的資料保留原檔並明示 unsupported／unverified；可提供受限研究 reader，但不得送進模型猜測推論。補充外部相容 sidecar 只能記原 hash、adapter version 與真實驗證範圍，不得追認未知 availability 或改寫舊 manifest。

## 7. R7：UpdateService 搬移實驗與明確 Gate

**2026-09-27 scoped acceptance：R028 technical-publication migration 已接受。** `UpdateService.calculate_technical_indicators` 的 orchestration owner 已移至 `app_module.technical_indicator_job.TechnicalIndicatorJob`，UpdateService 保留 lazy facade；範圍與限制見 [R028 implementation report](REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md)。這項接受只覆蓋該報告明列的 source/runtime 與 publication 邊界，不推定所有 listed dependencies、ML feature materialization timing、模型輸入 hash 或 artifact compatibility 均已驗收；其餘契約仍須逐項依下方條件核對。

未來實驗必須是獨立、可丟棄程式副本與極小 fixture，source／DB／輸出 root 全隔離，無正式資料、scheduler 實跑、重訓或 full-market rebuild。不得在同一長存進程內先 import baseline 再替換磁碟程式冒充 candidate。

1. **鎖 baseline**：記錄 exact source bytes／15 路徑、stable computation identity、dependency payload、library versions；保留原方法對少量股票的正常、warmup／missing、年度邊界與取消結果，以及 row／feature／manifest hash。baseline 使用原實作，不與 candidate 共用被抽出的新 helper 當 oracle。
2. **隔離候選**：只在實驗副本抽取該方法的協調責任；不改公式、參數、warmup、數值格式、fallback 或 writer。以獨立子進程各跑原接線／候選接線。
3. **查 identity**：逐檔比較 path／SHA256／source-code fingerprint、stable identity；獨立核對 build-start 到各階段的 loaded-code／constants compatibility。使用極小 checkpoint fixture 驗同 identity 可續跑、錯 identity 拒絕，不混寫同 run。
4. **查時序**：用可控 barrier 在 compute、publication、SQLite commit、snapshot prepare 與 infer 間注入更新／取消；比較實際消費 rows、availability、cutoff、publication receipt 與候選 identity。fixture 必須能重現 Rule 已讀、ML 尚未讀時來源更新的競爭。
5. **查結果與拒絕**：同原輸入的原 numeric bytes／整數結果／mask／row refs 精確相等；source 更新、缺來源、identity conflict 時明確使用原版本或拒絕 projection，不 silently refresh。原 guard 的既有失敗須獨立列出，不能藉本實驗加整包 allowlist。

| 結果 | 決議 |
|---|---|
| 通過 | 必要 hash／bytes、loaded integrity、feature availability／call order、resume 正反例與拒絕語意均符合 baseline；只允許將該 bounded 搬移提交審查，不外推其他 producer 可搬 |
| hash 或 identity 改變 | 原同 identity 搬移假設失敗；停留舊接線。若仍要改，另立新 identity／checkpoint 處置計畫，不能改 hash 清單假裝通過 |
| hash 相同但數值／時序改變 | 同樣失敗；source hash 不涵蓋全部行為，不能以 hash 相等覆蓋 race／look-ahead 差異 |
| 無法控制 live 來源或證明 availability | 阻擋新接線；維持既有序列／更新互斥或拒絕 projection，不能產生假的一致性 receipt |
| 回滾 | 只切回原程式／provider 接線；保留實驗 evidence，正式 artifact／模型／checkpoint 不變。若未來另案已發布新格式，先停新 writer，保留新 reader，不用舊 writer 覆寫新格式 |

## 8. 實作驗收與完成邊界

開始任何 ML 內部整理前，先完成授權範圍內的唯讀 artifact inventory：producer/version、bytes/hash、schema/order/dtype/scale/mask、shape、row/fold refs、source revisions、checkpoint、model class paths 與 dependent releases。沒有 inventory 的資產不以「未找到 caller」刪除，也不強制轉成最新版。

小型相容驗證至少包含：正常／missing／真零／極值、跨年度 carry、欄位調序、wrong hash/library/schema、quarantine、重複／缺 row key、all-missing column、train-only transform、同版本 prediction、checkpoint resume 成功／拒絕、低容量／path guard、execution A/B 交錯及保存時來源更新。整數／bp 與 binary output exact equality；浮點若不能 bitwise 比較，事前按具體欄位定義 tolerance，不以全域寬鬆誤差掩蓋改變。

可從現有 `test_ml_model_artifact_manifest.py`、`test_ml_model_artifact_loader.py`、`test_ml_direct_numeric_shared_reuse.py`、`test_recommendation_training_lineage.py`、`test_recommendation_service_calibration_integration.py` 與 `test_ml_shadow_dependency_boundary.py` 路由起步，再依改動選 affected tests。此段是設計時的驗收要求；R028 已有其具名 bounded route，但本文件列出的其餘測試及全範圍 ML 相容性條件不能因此視為已執行或通過。

本輪只完成契約定稿與原始碼核對。ML 外側 envelope、`PreparedMLInput`、provider 隔離、ownership 抽取與 source-path 退出均不得記為已實作；原 rule-only／shadow／formal／natural／production safety gates 維持原狀。

## 更新記錄

- 2026-09-22：依最終裁決建立 ML 規範分冊，明定永久資料邊界、第一輪凍結、15 路徑 ABI、歷史讀取支援、新特徵演進與 R7 未執行實驗 Gate；未修改 production code、模型或資料。
