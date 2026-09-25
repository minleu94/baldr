# R010 實作報告：PreparedMLInput 與 ML 邊界契約

## 結果

R010 已在隔離 worktree 完成純資料契約、應用層 Protocol shell 與 focused tests。依獨立審查的兩項 CHANGES_REQUIRED finding，已補 production model safety gate 與 date-only availability 支援。沒有修改既有 ML feature、model、loader、store、producer、資料庫或 provider；也沒有載入模型、讀取來源、建 feature、推論、訓練或寫入正式資料。R010 不是資料搬移或 ML ABI 相容實驗的完成證明。

新增 `ml_module/prepared_input_contract.py`，以 frozen/slotted scalar records 綁定 execution、候選、Rule/ML 來源快照、feature/transform、固定 model/release、權限與成本收據身分。快照要求明確 dataset/bounded 類型、source/snapshot ID、schema version、內容與 row-identity SHA-256、列數／日期範圍、來源 revision、availability、品質／缺件及 PIT/current/research scope。availability 可保留只有 `available_date` 的 date-only 精度，或 aware `available_at` timestamp；未知 availability、品質或 scope 保留為 UNKNOWN。缺值不得以 0 代替。dataset 類型必須提供真實 dataset ID；bounded 類型禁止編造 dataset ID，但必須提供可驗證雜湊。

新增 `app_module/recommendation/ml_adapter.py`，只定義 application-side Protocol。prepare boundary 強制呼叫端提供 `mode`，因為既有 `RecommendationExecution.Context` 尚無 mode 欄位。projector 接受已綁定的 `PreparedMLInput`；Protocol 不含 provider I/O、特徵計算、模型載入或推論實作。date-only `available_date == decision_date` 無法證明日內是否早於 `decision_at`；沒有另外可驗證的 policy 時，projector 必須拒絕投影，不可補午夜、開盤或收盤時間。ML leaf 契約只依賴標準函式庫，沒有反向 import application/data/provider/DB/model。

## 舊欄位與新契約對照

| PreparedMLInput 欄位 | 現有資料來源／可映射內容 | 相容限制與無證據時的處置 |
|---|---|---|
| `result_id` | `RecommendationExecution.result_id` | 原樣保留 opaque 字串；不轉 UUID、不正規化大小寫或字元。 |
| `candidate_identities` | Rule 結果可提供 `RecommendationItem.stock_code`；呼叫端必須另給每個候選的穩定 opaque identity | 股票代碼只作 `symbol`，不可冒充 candidate identity。`MLReceiptBinding.model_candidate_id` 是模型候選／凍結候選身分，不等於逐股票 candidate ID；不可自行合成映射。缺少真實逐候選 ID 時，後續 adapter 必須拒絕 ML projection。順序照呼叫端傳入值保留，ID 與 symbol 都不得重複。 |
| `decision_date` / `decision_at` | execution `Context.as_of_date` 與 `Context.decision_at` | 日期與時區時間分別保留；`decision_at` 必須 aware。不得以執行主機當前時間補值。 |
| `as_of_date` / `feature_cutoff_date` | execution `Context.as_of_date`；歷史 ML provider 的 `decision_date` / `feature_as_of_date` | 兩個 snapshot lane 可以不同，但各自 row range 必須不晚於共用 feature cutoff；timestamp availability 必須不晚於 `decision_at`，date-only availability 必須不晚於 `decision_date`，兩項證據分別保留且各自校驗。R007 允許同時有兩者，不要求其日曆日期相同。同日 date-only 只證明日期相等，不能證明日內先後，交由有證據 policy 裁決，否則 projector 拒絕投影。provider 的 `feature_as_of_date < decision_date` 只證明日期界線，不足以單獨證明 availability。 |
| `mode` | 現有 `Context` 沒有 mode | 由 application 在 adapter 邊界明確傳入；不得推測 interactive/replay。 |
| `rule_snapshot_refs` | `Context.source_refs`、`Context.data_snapshot_refs` 是候選的 execution-level provenance | 現有 references 不必然包含實際消費列的 content hash、row identity、availability、品質與 scope；不得直接升格為已驗證的 row snapshot。缺欄位需由持有證據的 caller 明示補齊，否則拒絕投影。 |
| `ml_snapshot_refs` | `MLHistoricalSnapshotProvider.HistoricalRawSnapshot` 提供 decision/feature dates、來源表、原始觀測、`source_fingerprint`、`query_count` | `source_fingerprint` 是舊 provider 的來源指紋，不能當作本契約要求的精確 consumed-row content hash 或 row-identity hash；provider 亦未直接給予 dataset ID、逐列 availability（R007 的 availability record 可保留 date-only 或 timestamp 證據）、品質／缺件與 PIT/current/research 語意。不能將指紋改名後假稱內容 hash；無法真實計算／證明時保持 unavailable/unknown 並拒絕投影。 |
| `SnapshotReference.quality_status`, `missing_inputs` | execution `Context.input_quality` 與來源提供的明確品質／缺件證據 | `QualityReport` 不能自動代表 ML 各來源完整。現有 provider 沒有契約化缺件清單；不從空 list 推定 complete。缺件須以 `MissingInput(item_id, reason_code)` 表達；COMPLETE 不可同時列缺件，DEGRADED/MISSING 必須列出缺件。 |
| `SnapshotReference.scope_status` | 來源擁有者對實際資料語意的明確聲明 | 只能由證據分類 PIT、CURRENT 或 RESEARCH。僅有歷史日期 cutoff 或 read-only query 不足以推定 PIT；未知狀態保留 UNKNOWN。 |
| `FeatureContract` | `CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema` / `registry_hash`、既有 feature builder/schema 與模型 manifest | 有序 feature ID、dtype、unit、registry hash、transform ID/version/hash、missing/mask/normalization policy 必須一致綁定。R010 不改變現有 20 欄的順序、名稱、dtype、尺度、遮罩、正規化、真零／缺值解讀或 historical numeric-store 語意。 |
| `ModelBinding` | 已驗證的 `ModelArtifactManifest`、loader result 與明確 resolve 後的 model/release identity | 綁定 model/release/family、training dataset identity/hash、registry/label/transform hash、artifact/manifest hash、class path、serialization format、library versions、quarantine、shadow、production 與 permission 狀態。只有 quarantine `CLEAR`、permission `GRANTED`、`shadow_only=False` 且 `production_eligible=True` 時，才允許 `production_action_allowed=True`；任何 DENIED/QUARANTINED/UNKNOWN 或 shadow-only 狀態均拒絕。manifest 的 `artifact_filename` 或 active/latest pointer 不是固定 release identity，不得存入契約當作已解析模型。若舊 artifact 缺少任一必要 hash/version/狀態，不得虛構；保持不可用。 |
| `CostReceiptBinding` | consumer 的 active cost scenario ID/version/hash；若已有輸入 receipt 則可綁 receipt ID/hash | 情境 ID/version/hash 成對綁定；receipt ID/hash 必須成對提供。輸出 projection receipt 由投影完成後另行建立，R010 不預造 receipt。既有 `MLReceiptBinding` 的 receipt reference/hash、result/date/model-candidate/projected symbols/cost scenario hash 仍按原語意使用。 |

R010 的 record 可表示未知狀態，但本身不聲稱來源已滿足 ML 可用條件。呼叫端不得將空值、缺欄或 provider 的檔案指紋轉成假 dataset ID、已知 availability、complete quality、PIT scope 或 row-level proof；亦不得由 date-only availability 合成精確 timestamp。

## 數值、持久化與 replay 相容性

- 本任務只保存型別化身分與 policy 字串，沒有計算數值或轉換既有 feature。既有 feature 排序、名稱、dtype、scale、mask、正規化、missing/zero 區分、Direct/OOC numeric store 與歷史 model artifact ABI 均未修改。
- 契約不讀寫資料庫、檔案、模型或收據。沒有更新 manifest、checkpoint、store、receipt、正式輸出或使用者資料。
- `decision_date`、`decision_at`、`as_of_date`、共同 feature cutoff、兩條彼此獨立的 snapshot lane 與明確 mode 均可被封存。R010 沒有執行 replay；實際 replay adapter 仍須提供對應原始版本 references，否則不可用目前來源代替歷史來源。
- `TMP-ML-01` 只指未來 adapter 內沿用已凍結 legacy preparation 順序的分支，依 DAG 由 R026 移除。永久 `ml_adapter.py` Protocol 與純契約不是待刪臨時元件。

## 測試與驗證

focused regression 指令在隔離 worktree 執行，使用 repo venv 的 Python，關閉 bytecode 與 pytest cache，避免觸碰凍結相依檔：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe -B -m pytest tests/test_prepared_ml_input_contract.py tests/test_refactor_ml_compatibility_baseline.py tests/test_data_market_contracts.py tests/test_recommendation_contracts.py tests/test_r008_decision_numeric_enum_rework.py -q -o addopts= -p no:cacheprovider
```

同步 R009 contract addendum 後的最後 regression：**92 passed in 4.21s**。測試覆蓋 frozen records 與 caller-list defensive copy、aware datetime/tzinfo 內容凍結、opaque candidate 順序與唯一性、SHA 格式、date-only/aware timestamp availability 精度、未知與未來 availability、兩種 availability 證據獨立保留與各自 cutoff、dataset/bounded 來源識別、品質與缺件正反例、PIT/current/research/unknown scope、Rule/ML 分立 snapshot 共用 cutoff、feature/model binding、production safety status 正反例、成本 receipt identity、ML import DAG/no I/O 及 R006/R007/R008 focused regressions。

其他檢查：

- `python -B -m py_compile ml_module/prepared_input_contract.py app_module/recommendation/ml_adapter.py tests/test_prepared_ml_input_contract.py`：通過。
- `python -B -m mypy --follow-imports=skip ml_module/prepared_input_contract.py app_module/recommendation/ml_adapter.py`：2 個變更來源通過。
- `git diff --check`：無 whitespace error；只回報 frozen copied files 既有 LF／CRLF 工作樹提示。
- 未執行訓練、資料重建、來源搬移、live read、ML projection、正式資料寫入或 R7 搬移實驗；這些超出 R010 範圍。

## 產物與隔離狀態

唯一 R010 產物：

- `ml_module/prepared_input_contract.py`
- `app_module/recommendation/ml_adapter.py`
- `tests/test_prepared_ml_input_contract.py`
- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R010_IMPLEMENTATION_REPORT.md`

R007/R008 與 R006 凍結相依檔未由本次 R010 程式修正修改。依父任務指示，先確認原副本為 `CCF12635EBE037548C7695154D2CD661C1FF8182C6663222F1CC219F982BBC63`，再只從 R009 worktree 同步 `app_module/recommendation/contracts.py`；來源與目的 SHA 均為 `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81`。與 main 舊版本的窄 diff 僅新增 `SUPPORTED_EXECUTION_SCHEMA_REVISIONS: tuple[int, ...] = (1,)`。其餘 13 個 frozen dependency 與 main 相同；總計 14/14 均符合最終派工基線。核對時 main HEAD 為 `5e2d2efcfdc91c5e29810eb823b1c582199a44cc`，R010 worktree HEAD 為 `166ad745710914312ee8e2e698f230577bfb41a4`，R009 同步檔仍為未提交的 leaf contract。未 stage、commit、push、reset、clean 或整合回 main；整合時仍須對屆時最新 main HEAD 與全部 frozen dependency bytes 重新核對。

## 最終 SHA-256

以下為檔案原始 bytes 的 SHA-256（報告本身的雜湊不遞迴寫入自身）：

| 路徑 | SHA-256 |
|---|---|
| `ml_module/prepared_input_contract.py` | `E39EE8ACB37CEDBCABE5276FE85703B2FDBEB98C2DE9702B23184934D6513D03` |
| `app_module/recommendation/ml_adapter.py` | `61ED294BC577A9D68A1887DC73F357C5563F6D7D465F3FC5C97235D1DB300755` |
| `tests/test_prepared_ml_input_contract.py` | `CBF892E0ABFF3583962205E7C3BC41F798D29E8D4087683D15BC3BFC1F142B9A` |

本報告自身的 SHA-256 會在交接訊息另行提供，避免自我引用雜湊。
