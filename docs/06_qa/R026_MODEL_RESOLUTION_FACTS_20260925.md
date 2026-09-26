# R026 同次模型解析事實 QA

**狀態：** Root 依 R015 獨立程式／測試複核判定本 slice bounded `ACCEPTED_SCOPE`：只接受 experimental capability 上的同次 model-resolution facts，未發現程式／測試 P1/P2。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`；此 slice 不是 `PreparedMLRuntimeInputV1`，沒有 live service/runtime handoff。

## 同次來源與接線

`RecommendationCalibrationConsumer.resolve_invocation_projection_capability()` 在既有 exact runtime-profile gate 後，讀取 pointer bytes，建立 fresh consumer，再由一次 `reload()` 使用既有 safe loader 解析 pointer、candidate、manifest、artifact、training provenance 與有序 probability lineage。可捕捉的值皆取自該次 reload 的 locals；runtime profile 在 pointer I/O 前取得一次。外層 pointer-before/after bytes、fresh loaded pointer 與呼叫端 expected identity 都通過後，才組裝並附加 immutable evidence。

Reload 暫存的 raw mappings 只為完成上述檢查而留在 fresh consumer。方法 `finally` 會清空本切片新增的 capture bundle、capture flag 與 runtime profile；capability 仍持有私有 `resolved_consumer`，其中保留既有 `_loaded_pointer`、probability lineage、training provenance 與模型等投影所需解析狀態。因此本切片只保證 `model_resolution_evidence` property 對外提供 deep-immutable facts，不宣稱整個 capability 沒有 mutable state。A/B fresh resolve 產生不同 evidence 物件；相同輸入的 canonical evidence 值相同。取得 `model_resolution_evidence` 不做檔案、pointer、loader 或資料庫 I/O。一般 `project()`／`project_many()`、active identity 欄位形狀、模型推論、receipt bytes 與發布順序未改。

## Facts 與雜湊界線

`RecommendationModelResolutionEvidenceV1` 以 `recommendation-model-resolution-evidence.v1` 版本標記，內容包括：

- pointer/candidate identity claims、candidate training cutoff、candidate schema 與 path recheck 狀態；candidate claim digest 使用 `r026-candidate-identity-claim.v1\0` domain，覆蓋 candidate id、manifest/artifact/freeze/dataset hash 與 training cutoff。這是選定欄位的 identity-claim digest，不是 candidate JSON 檔案 bytes hash。
- 由 safe loader 已驗證的完整 artifact manifest 宣告：model/dataset/run/family、created time、feature/label registry、ordered feature schema、training cutoff、hyperparameter hash、research/production alpha、selection fields、serialization、artifact filename/hash、recorded library versions 與 shadow/production flags。
- training provenance 的 `verified` 或 `legacy_unproven` 狀態及其明示來源/PIT/transform/dataset/date/cost claims。Legacy 缺值維持 `None`，不由 inference facts 升級。
- ordered probability lineage，每個 node 與整列分別有 domain-separated digest；runtime OS/Python/library profile 獨立於 artifact 所記錄的 library versions。

所有 canonical digest 使用 UTF-8 JSON、sorted keys、compact separators、`ensure_ascii=False`、`allow_nan=False`，另加各自固定 domain prefix。Facts dataclasses 使用 frozen slots、tuple 與純 scalar 欄位；`to_payload()` 每次回傳新 mutable copy。

這不是完整 `ModelBinding`：`release_id` 與 artifact-declared qualified class path 明確為 `None`；quarantine 與 permission 為 `unknown`；transform 若是 legacy training provenance 則是 `legacy_unproven`；整體 status 固定 `incomplete_unknown_fields`。Shadow active-pointer eligibility 不是 quarantine clearance 或生產權限。

Artifact loader 先 hash artifact path，再由 deserializer 重新開啟 path；既有 `_pointer_candidate_hashes_match()` 之後再檢查 artifact path。Evidence 因此標示 `path_hash_before_deserializer_reopen_then_path_recheck`、`loaded_bytes_sha256=None`、`same_bytes_binding_status=not_verified`。Candidate JSON 也有路徑重讀，但沒有綁定初次解析和重讀的同一 bytes。不得把 path hash/recheck 說成 deserializer 實際載入 bytes 的 hash，也不排除 pointer/candidate/artifact 的 ABA 或最後檢查後競態。

## Look-ahead 自查與限制

本切片不載入市場 rows、不產生 feature、不做標準化、fit、predict、label 或 forward 查詢。日期只取自已驗證 pointer/candidate/manifest/training-provenance 和同次 decision date；既有 reload 仍拒絕 training cutoff 晚於 decision date。本 facts 不是新增 PIT/source-generation 證明，也未將 artifact、feature set、receipt 或 service invocation 綁成可執行輸入。

Capability 只在既有 exact Windows/Python/NumPy/scikit-learn/SciPy/joblib runtime profile、fresh safe loader 與既有 nested graph alias gate 成功時可建立。未知或 malformed capture 在 optional capability resolver 內 fail closed 為 `None`；既有 legacy projection path 不改。API 不會從 pointer、manifest、training-lineage 或 receipt 做第二次讀取來補欄位。

## Fresh TEMP 驗證

Runtime：Windows CPython `3.11.9`、NumPy `2.3.5`、Pandas `2.3.3`、scikit-learn `1.8.0`、SciPy `1.16.3`、joblib `1.5.2`。最終 route 根為 `C:\r26m\h6ef132`；`PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP`、`TMP` 與 pytest basetemp 均在該 fresh TEMP root。

```powershell
$qaRoot = 'C:\r26m\h6ef132'
$env:PROFILE = 'test'
$env:TEMP = Join-Path $qaRoot 't'
$env:TMP = $env:TEMP
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'out'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_model_resolution_facts.py tests/test_r026_invocation_model_capability.py tests/test_prepared_ml_input_contract.py tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider --basetemp (Join-Path $qaRoot 'p')
```

結果 **62 passed in 15.02s**；log `C:\r26m\h6ef132\l\adj.log` SHA-256 `E6F6D0B2454E5BF6D21B7C8D2E78637A4693DB56971F94D4C828913DFF5B6916`。其中涵蓋同次 evidence/legacy-unproven/malformed claim/pointer mutation/A-B、既有 capability、PreparedMLInput contract 與 service integration。

Scoped mypy：`app_module/recommendation/model_resolution_facts.py` 與 `app_module/recommendation_calibration_consumer.py`，**2 files／0 issues**。上述兩個 source 與專項 test `py_compile` 通過。`scripts/quant_guard_linter.py` 的 financial-float 與 look-ahead checks 通過。Inventory 專項 membership/category assertion 通過，單一 entry 為 `service-oracle-recommendation`；沒有將共享 inventory 的全庫 guard 當成 pass。

較長 TEMP 路徑的兩次 4-file route 當時記錄到同一既有 service integration assertion `projection_receipt_not_persisted_fail_closed` 失敗；該 run 未對 `os.link` 做 instrumentation，當時不能確診根因。後續本機 Windows unprefixed path-length 診斷與 259/260 字元 probe 見本 QA 下方 capability same-bytes lineage 區段；因早期 4-file run 沒有保存底層 OSError/目的路徑，不能斷言那兩次早期失敗與後續三個六檔 failures 完全同因。早期失敗仍不計為 pass 或產品缺陷。

R015 獨立複核收據：fresh short TEMP `C:\r26m\mrv_e1078bfa\pytest.log`，4-file route **62 passed**，log SHA-256 `6158DAA187D57F6551AA132DB2A3CF35BB46FFA580D8871016DFCB453208D29D`；mypy 2 files／0 issues、`py_compile`、quant guard、diff check 通過，inventory 單一 entry。複核未發現程式／測試 P1/P2；原 CHANGES_REQUIRED 僅指本文與 report 將 capability 描述成只持 facts，已由本次修正處理。Root 依此 receipt 接受本 slice 的 bounded 範圍；不延伸為完整 model binding 或 runtime handoff。

## Frozen SHA-256

- `app_module/recommendation/model_resolution_facts.py`: `662A646CFBD0DF60EB361448DE4BBCDC2213F21BC76AF8051070AB8A6395E41A`
- `app_module/recommendation_calibration_consumer.py`: `EF0878163FC315D8B9C532BB429247E8034766CECC964810BB5FE9CB2BD790AC`
- `tests/test_r026_model_resolution_facts.py`: `1DF9A984E7C6ED06582068F3B7208F32798750456AD2CD2B9C7494D6DA152DE0`
- `qa/full_app_healthcheck/test_inventory.py`: `FC109734388B1D0E1E74BE77358943BA126209D5B6F2B978FF11CB594ED24BFF`

`git diff --check` 通過。這些 receipts 只涵蓋上述 experimental model-resolution evidence slice；不證明 same-bytes artifact binding、完整 ModelBinding、feature/source/receipt binding、pointer ABA 防護、runtime handoff、TMP-ML-01 或 R026 結案。

## 歷史：same-bytes loader 唯讀可行性審查（已由後續實作取代）

以下是實作前唯讀 baseline review 的歷史觀察，不描述目前 opt-in route。當時 `SafeShadowModelArtifactLoader.load()` 在 `ml_module/model_artifact_loader.py:96` 以 `manifest_path.read_text()` 解析 manifest，於 `:119` 對 artifact path 呼叫 `_sha256_file()`，再於 `:125` 將同一路徑交給 deserializer；`_sha256_file()` 另以 `open()` 讀檔（`:137-142`）。因此該 baseline 的 artifact hash 與 `joblib.load(path)` 不是同一份已捕獲 bytes。`RecommendationCalibrationConsumer.reload()` 隨後還會用 `_pointer_candidate_hashes_match()` 重驗 artifact path（`app_module/recommendation_calibration_consumer.py:595, 2344-2396`）。Candidate JSON 由 `_read_json()` 讀取，初次 load 與 `_pointer_candidate_hashes_match()` 的欄位核對是分開的 path reads（`:546-555, 2117-2121`）；manifest 驗的是 canonical manifest payload hash，不是原始 JSON bytes。Receipt 檢查也先 hash receipt path、再讀文字解析（`:2440-2462`）。Probability lineage 會載入多個模型，沿用相同 loader 路徑（`:794-872, 918-939`）。前後 pointer bytes 比對能攔截部分變更，但該 baseline 的 reload 仍獨立讀 path；這些觀察不排除短暫替換、restore/ABA 或最後檢查後競態。

Synthetic TEMP probe `C:\r26m\toc2\probe.log`（SHA-256 `6B46FFBDBFE2D044CDA00FFD870E54FA3C0291F0B506042D11837673FBA5D5D9`）使用預設 `joblib.load`，在 artifact path hash 完成後、deserializer 開檔時，透過一次性 `builtins.open` shim 提供另一份有效 joblib buffer。Loader 最終回傳的是替代 buffer 的模型，但 manifest/path SHA 仍是原 bytes。這是對既有 hash-then-reopen seam 的合成重現，不是外部程序 race 的量測。較早使用 injected deserializer 的 `toc1` probe 不作主要證據，因 optional capability 本來會拒絕 injected loader。

另以目前 runtime 的 joblib 1.5.2 做了格式可行性 probe：production-shaped synthetic `RunnableRecommendationCalibrationModel` 以既有 producer 的 `BytesIO`／`joblib.dump(..., compress=0)` 形式序列化後，`joblib.load(Path)`、`joblib.load(BytesIO(captured_bytes), mmap_mode=None)` 與 rolled `SpooledTemporaryFile` 的模型類別及三組 `predict()` 結果相同。probe log `C:\r26m\tofmod\probe.log` SHA-256 `B3EE660B0E0B4CE6139CC838FEFE4D0345EC20BCCCA82E21B13AEB87D0744206`。這只證明目前 synthetic model/profile 的 file-like 可行性，不涵蓋任意 artifact、其他 joblib 版本、最大模型尺寸、故障/磁碟壓力或完整 consumer 行為。

後續已新增 capability-only `load_same_bytes_v1()` opt-in loader，實作收據與 residual 見下方「Same-bytes artifact loader opt-in」及「Capability-only same-bytes ordered artifact lineage」兩節。此歷史設計建議不是目前尚未實作的提案；它當時提出的多檔共同 identity binding、pointer ABA 與 receipt publication race 限制仍未由單一 artifact loader 消除。

上方較早的 model-resolution facts acceptance 僅涵蓋該 facts slice；後續單一 artifact opt-in loader 與 capability lineage 各有自己的 bounded acceptance 範圍。任何單一 artifact spool 修補都不等於完整 `PreparedMLRuntimeInputV1`、pointer/candidate/manifest/lineage/receipt 共用 bytes binding 或 R026/TMP-ML-01 結案。

## Capability-only same-bytes ordered artifact lineage（root bounded `ACCEPTED_SCOPE`）

本 follow-up 僅在 `resolve_invocation_projection_capability()` 建立的 fresh consumer 中使用 `load_same_bytes_v1()` 載入 active artifact 與已驗證的 ancestor lineage artifacts；一般 `reload()`、既有 service 與 receipt 路徑仍使用原 `load()`。成功後 capability 額外暴露 frozen `CapabilityLoadedArtifactLineageEvidenceV1`，依 semantic lineage 順序記錄 null benchmark 或每個模型節點，以及每個模型 artifact 真正由同一 spool 載入的 serialized-bytes SHA-256。既有 `RecommendationModelResolutionEvidenceV1.artifact.loaded_bytes_sha256` 仍為 `None`，未改其既有語意。

Capability-only gate 要求 active candidate id 在 lineage 中恰有一次且位於末端；末端 node 的 normalized root、candidate/model id、manifest/artifact/freeze/dataset hashes 必須與同次 active pointer identity 相符。Ancestor load 或 identity 任一失敗時，不發布部分 capability/evidence。Synthetic multi-node 測試確認順序為 null→ancestor→active、loader 呼叫順序為 active→ancestor，artifact digest 與 fixture bytes 一致；ancestor tamper 使整個 capability fail closed。R015 以 fresh short TEMP 六檔路由獨立複核 **80 passed**，未發現程式／測試 P1/P2；root 依此與修正文檔判定本 slice bounded `ACCEPTED_SCOPE`。

Frozen SHA-256：consumer `app_module/recommendation_calibration_consumer.py` `0E0C9A05C4F8AE82AEAC8BFF4D1F2F134FD0B0F3DEB0082533F3C196C3A06B17`；facts `app_module/recommendation/model_resolution_facts.py` `5898378B4EB6FE0038DDC750607B6DB183F7E48767A3255684A5973CE2040C59`；test `tests/test_r026_invocation_model_capability.py` `29F01813E79B05688CFFB4A31C8CF4A111F768E7C1D63B1D878341719BB25D51`；inventory `qa/full_app_healthcheck/test_inventory.py` `C1CBABACD0D3EE587AEF7A8F952A2726EE16B924D877178701B7EA11F54A05B7`，專項測試維持單一 `service-oracle-recommendation` entry。

Final short TEMP six-file route：`C:\r26q\capfinal_20260925\pytest.log`，**80 passed in 17.27s**，log SHA-256 `28326B0E56DECC1CB29F681CC5BF1E59CC88E511BAADCAED1EEE748BA5BC5607`。命令前後 consumer/facts/test SHA 完全一致。Runtime 為 Windows CPython `3.11.9`、NumPy `2.3.5`、Pandas `2.3.3`、scikit-learn `1.8.0`、SciPy `1.16.3`、joblib `1.5.2`。命令：

```powershell
$r026QaRoot = 'C:\r26q\capfinal_20260925'
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $r026QaRoot 'd'
$env:OUTPUT_ROOT = Join-Path $r026QaRoot 'o'
$env:TEMP = $r026QaRoot
$env:TMP = $r026QaRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py tests/test_r026_model_resolution_facts.py tests/test_r026_model_artifact_same_bytes_loader.py tests/test_ml_model_artifact_loader.py tests/test_prepared_ml_input_contract.py tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider --basetemp (Join-Path $r026QaRoot 'p')
```

Scoped mypy 2 files／0 issues、`py_compile`、quant/look-ahead guard 與 targeted `git diff --check` 通過。

同一六檔路由先前使用較長 TEMP 根 `C:\Users\archi\AppData\Local\Temp\r026_cap_samebytes_full_d868197f9ce247599de6dbec9d6db58d` 得 **77 passed／3 failed**；log SHA-256 `CD13FB89B5879314320F39095D7F0A7E964A0639EA1B836039CDF9CD3523D311`。三個失敗均在既有 service integration 的 receipt assertion（`test_real_consumer_producer_advice_workbench_ui_path`、`test_public_service_real_builder_saves_result_and_reverse_reads_receipt`、`test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation`），訊息為 `projection_receipt_not_persisted_fail_closed`。後續 instrumentation 確認失敗落在 `_write_create_only()` 的 `os.link(temp, final)`：三個目的路徑為 266/266/278 字元，來源暫存檔與 parent directory 都存在，Windows 回 `FileNotFoundError(errno=2, winerror=3)`。同環境短 TEMP 的同類 service case 以 243 字元 receipt path 成功；純合成 boundary probe 259 字元成功、260 字元重現相同 WinError 3。故可將這三個長 TEMP 失敗歸因為目前測試環境的 Windows unprefixed path-length 邊界；原 run 仍是 **FAIL**，不算 pass，也不外推到所有 Windows runtime/configuration。Long diagnostic `C:\Users\archi\AppData\Local\Temp\r026_diag_long3_4e29798113ec4ad9ae9015fb28552412\diag.log` SHA-256 `BBCE58E0D684A598A34CD2D52E4FBDE496EF3D52E2D127E23D15967E60D6EC07`；short diagnostic `C:\r26q\receipt_diag_short_ec7720573b9c42f58ad4654dd44473dd\diag.log` SHA-256 `D5AD80682B680A38A757F93E5995015C2C39303AD5FEB670E0A2A6EDE5C7F590`；boundary script `C:\r26q\receipt_path_boundary_c448716452e645399f5d18dcea6d96ee\repro.py` SHA-256 `0F90780F5C0AEE7AB59D4D14421B18B496FCAFA03D163DBD508101A079DAF19F`，log SHA-256 `915825871D40A8D3FF9DF7198BBFCD704173BCCBA03C9B6A61D7200EE2F225E2`。較長正式 learning root 若超出該環境支援的路徑界線，仍是獨立路徑支援議題；本切片未修改 receipt writer。

Residual：此 capability 是 experimental 且禁止 runtime handoff；每個 artifact 的同 bytes hash/load 不共同綁定 pointer、candidate JSON、manifest bytes、training provenance、receipt 或 service invocation，也不消除 ABA/最後檢查後競態。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。
