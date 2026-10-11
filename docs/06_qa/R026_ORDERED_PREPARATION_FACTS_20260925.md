# R026 ordered candidate / feature preparation facts QA

**狀態：** R015 獨立複核未發現 P1/P2，root 判定本 app-side preparation facts slice 為 bounded `ACCEPTED_SCOPE`。R026 仍為 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`；本 slice 不建立或接線 `PreparedMLInput.v1`、`PreparedMLRuntimeInputV1` 或 live inference handoff。

## Contract 與資料範圍

`app_module/recommendation/ml_preparation_facts.py` 提供 `RecommendationMLPreparationFactsV1`、`CandidateFeatureFactV1` 與 `build_recommendation_ml_preparation_facts_v1()`。Factory 接收明示 `result_id`、decision/cutoff dates、有序 `RecommendationItem`s、有序 `HistoricalFeatureRow`s 與 exact canonical `HistoricalFeatureBuilder`。它直接呼叫既有 `HistoricalFeatureBuilder.load(row)`，保留其 canonical feature ID/order/schema、missing-as-`None` 數值與 `snapshot_hash`；沒有另建 feature ABI。

Factory fail closed 條件包括：空白 result ID、非 exact date、cutoff 不早於 decision date、非 canonical builder/registry/load contract、候選或 row 數量不一致、重複 symbol、row/item 次序或 symbol 不同、feature decision/cutoff 不符、非 canonical available-date、available date 晚於 decision date、registry/schema hash 或 feature ID/dtype/unit/order/width 不符。Feature values 僅接受 exact `int | None`，因此 `bool` 不會冒充整數；缺漏與多餘 feature ID 都由 canonical `load(row)` 拒絕。

`candidate_id` 是 invocation-bound opaque ID，格式為 `candidate.v1:` 加小寫 SHA-256。Hash 原文使用固定 UTF-8 canonical JSON：`ensure_ascii=False`、`allow_nan=False`、sorted object keys、compact separators。Candidate ID 的 domain 是 `r026.recommendation-candidate.v1`，輸入含 `result_id`、兩個日期、selected 順序 index、symbol、selected item 的獨立 domain hash、registry/schema hash 與 canonical feature-row hash。它刻意會隨 selected item、feature bytes、result/date 或位置變化；不代表跨 feature revision 穩定的候選身份。Symbol 是另一個明示欄位，不作 candidate ID。Feature row hash 仍獨立保存，不與 candidate ID 混稱。

Selected item hash 使用 `r026.selected-recommendation-item.v1` domain，並以 exact frozen dataclass 欄位順序和具型別標記的 Decimal/int/bool/string/date/tuple/nested record 編碼。頂層 `payload_sha256` 覆蓋 contract version、結果與日期、registry/schema/load-contract facts 及有序 candidates/features。測試鎖定代表性 canonical golden：payload `sha256:e8516ec9535dd14d7501aafc893bc67e93db374f38add3d679369e280a66347b`；候選 IDs 分別為 `candidate.v1:80fd427d7840ad758302c920a7cc5aca2558a79e838dc263255493ea957926df` 與 `candidate.v1:51927b62b1acbe4fadb9d2f580466b2b365edb088390b41362a4cdb3939a9bf5`。

使用邊界：canonical source-to-feature 證據來自此 factory 路徑及其 `load(row)`；dataclass constructor 本身只能驗結構、候選衍生 ID 與頂層 payload hash，不能在任意手工建構的物件上證明提供的 `feature_row_sha256` 對應某個外部 builder row。因此下游只能把 factory 產物當作此 slice 的 preparation result；不宣稱任意手工構造的同內容 facts 有來源完整性。沒有 snapshot reference、source revision aggregate、same-day availability policy、ModelBinding、candidate-to-snapshot reference、model/lineage identity 或 receipt identity。

## Look-ahead 自查

測試決策日為 `2026-09-25`、feature cutoff 為 `2026-09-24`。Factory 核對 row 的 decision date、feature-as-of date 與 available date；`HistoricalFeatureRow` 也要求 feature-as-of 早於 decision 且 available date 不晚於 decision。Feature values/order 只由既有 canonical `load(row)` 提供。此 slice 沒有加入未來列、標準化、fit、label/forward value、資料查詢或新的特徵計算；它也沒有驗證呼叫端傳入 rows 的外部來源身份。

## Fresh TEMP 驗證

Runtime fingerprint：Windows CPython `3.11.9`、NumPy `2.3.5`、Pandas `2.3.3`。TEMP、TMP、PROFILE、DATA_ROOT、OUTPUT_ROOT 與 pytest basetemp 均設在 `C:\r26p\prep_final2_0925`；未讀寫正式資料。

```powershell
$qaRoot = 'C:\r26p\prep_final2_0925'
$env:TEMP = $qaRoot
$env:TMP = $qaRoot
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
New-Item -ItemType Directory -Force -Path $env:DATA_ROOT | Out-Null
New-Item -ItemType Directory -Force -Path $env:OUTPUT_ROOT | Out-Null
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_ml_preparation_facts.py tests/test_ml_historical_feature_builder.py tests/test_ml_historical_feature_computation.py tests/test_prepared_ml_input_contract.py -q -s -o addopts= -p no:cacheprovider --basetemp (Join-Path $qaRoot 'pytest')
```

結果 **42 passed**。完整 transcript：`C:\r26p\prep_final2_0925\pytest-transcript.txt`，SHA-256 `EB2E268188BF1F2C6DF0F5C2BE82B02CD59D9FF02436A1B5956C24899286AD98`。Scoped mypy：`app_module/recommendation/ml_preparation_facts.py`，1 source file／0 issues。Changed Python source/test `py_compile` 通過；`git diff --check` 通過 report hunk，兩個新檔亦經 trailing-whitespace/final-newline 檢查。

Frozen SHA-256：

- `app_module/recommendation/ml_preparation_facts.py`: `06752E976C340CDEABD9DC89B2E655AD890A60B5EE03F0A99FFA4820CF517151`
- `tests/test_r026_ml_preparation_facts.py`: `E8C8EEF258538683A5F22708FB8A6B2416FE994306093338BB88F64AF49E00BA`

R015 獨立 fresh TEMP 四檔路由為 **42 passed**；scoped mypy 1 source file／0 issues，`py_compile` 通過，未發現 P1/P2。此 slice 的測試已在 `qa/full_app_healthcheck/test_inventory.py` 以 `service-oracle-recommendation` 登錄一筆。這只證明本測試的 membership/category；inventory 全庫仍有其他既存 missing/guard failures，不能稱全庫 inventory guard 通過。後續非阻擋覆蓋建議包括 nested `FactorContribution`／`SourceRef`／`UniverseReference` hash golden，以及 factory 直接收到 future `available_date` 的負控。此 slice 不證明 model/snapshot binding、外部 feature-row source custody、projector no-I/O、receipt parity、A/B runtime handoff 或 TMP-ML-01 retirement。

## 後續 supported handoff 狀態（2026-10-10）

本文的 `TMP-ML-01` 與「未建立 `PreparedMLRuntimeInputV1`」是此 preparation-facts factory 的 2026-09-25 範圍描述。依 [R026 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md)，正常 `RecommendationService` NP1／NP2 supported caller/profile 後續已採 prepared-runtime／typed post-calibration handoff，遷移條件為 `CLOSED`；不表示本 `RecommendationMLPreparationFactsV1` factory 已接入該路徑，亦不關閉 R026 其他 source-evidence slices。
