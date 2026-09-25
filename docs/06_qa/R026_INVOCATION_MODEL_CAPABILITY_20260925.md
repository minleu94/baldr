# R026 invocation model-resolution capability — bounded experimental evidence

**狀態：** 原 consumer-side model-resolution API 已有 bounded `ACCEPTED_SCOPE`。Nested known-model graph traversal 與 exact runtime-profile guard follow-up 經 R015 獨立複核，root 判為 bounded `ACCEPTED_SCOPE`，無 P1/P2。接受僅限下列 exact model/lineage graph 與 runtime profile 的 experimental model-resolution API，不得接入 runtime handoff；R026 與 `TMP-ML-01` 維持 open。

## 實作界線

`RecommendationCalibrationConsumer.resolve_invocation_projection_capability()` 只接受 ASCII invocation scope、decision date 及呼叫端已捕獲的 identity。建立能力時直接讀 pointer bytes，使用 fresh consumer 與預設 `joblib.load` 安全載入路徑重新 resolve active candidate/lineage，再核對 pointer bytes 前後與 fresh identity。只有 exact `RecommendationCalibrationConsumer`、exact `SafeShadowModelArtifactLoader`、default `joblib.load` 及 exact `RunnableRecommendationCalibrationModel` top-level type 可取得能力；自訂或 memoizing deserializer 被拒絕。帶 `source_contract_binding` 的 inference provenance 也會在來源合約檔案讀取前被拒絕，避免 capability projector 在投影期間再做 filesystem provenance validation。

每個 capability 綁定一個 consumer owner、scope、date 與 identity digest，且該 capability 僅能投影一次、不可 copy/deepcopy/pickle。`WeakValueDictionary` 只在同 scope 的 capability 仍存活時拒絕重複建立；capability 被 garbage-collected 後 scope 可重用，永久唯一性須由未來 caller 保證，本 slice 未證明。帶 `source_contract_binding` 的投影請求會在 capability 被標為 used 前拒絕；這是呼叫參數的 filesystem-I/O guard，不構成持久 source policy 或 validated-input 證據。未來 runtime caller 必須先提供 immutable、已驗證的 input facts。這是 model-resolution API；沒有綁定本次 feature/candidate set，也沒有 live service caller。pointer 在最後一次 byte check 後仍可改變，ABA 與 receipt publication 競態亦未由此能力解決。

## Bounded known-model graph traversal

此段更新取代前一 checkpoint 的「只驗直接 component、尚無 nested traversal」描述。`_loaded_model_graph_snapshot()` 使用 `r026-known-model-graph.v1` exact-type／field allowlist，遞迴檢查 `RunnableRecommendationCalibrationModel`、`Pipeline`、`SimpleImputer`、`StandardScaler`、`Ridge`、`LogisticRegression`、`FittedShadowProbabilityCalibrator`、`IsotonicRegression` 與 SciPy `interp1d`。根集合含 active/baseline/lineage models、probability lineage、loaded pointer、baseline identity 及 training provenance；巢狀 plain dict/list/tuple、primitive 與 ndarray 也納入。它比對 source/fresh 與仍存活 A/B capability 的 mutable object identity，並以 `np.shares_memory(..., max_work=10_000)` 拒絕共用 ndarray backing storage。

此 slice 只驗證本機 synthetic production-shape：Windows 10 build `10.0.26200-SP0`、CPython `3.11.9`、NumPy `2.3.5`、Pandas `2.3.3`、scikit-learn `1.8.0`、SciPy `1.16.3`、joblib `1.5.2`。一個本輪 active candidate fixture 的完整已載入 model/lineage graph 遍歷到 **70 個 mutable object IDs、41 個 ndarray、936 bytes**；這是 fixture-specific 觀測，不是所有 candidate 的固定規模。另一合成模型圖曾觀測 72 nodes/35 arrays；計數會隨 lineage/model shape 改變，兩組都不構成上限或跨版本證據。此 profile 的 arrays 為 float64、int32、int64。Optional capability resolver 在 pointer I/O 前比較 `sys.platform`、Python major/minor/patch、NumPy、scikit-learn、SciPy 與 joblib 的精確版本；不符即回 `None`。Pandas 版本只記錄、不參與此 graph profile gate。

Walker fail-closed 條件含未知 exact type/field、不同 Pipeline steps、未知 callable、closure/default/可變 function attrs、object/structured/非數值 ndarray、unsupported backing owner、cycle，以及 depth 24、4096 nodes、512 arrays、64 MiB aggregate array bytes、每 array 1,000,000 elements 的 budget。`interp1d._call` 只接受 module import 時捕獲的 SciPy reviewed `_call_linear_np`／`_call_linear` exact function identity，並重驗 no closure/default/kwdefaults/function attrs；執行期 class attr 被換成新 closure-free callable 也會拒絕。此 allowlist 與 runtime gate 只支援上段列出的 exact profile；未知版本回 `None`，不保證任意 Python subclass、未知 native buffer owner 或 future fitted field。

## Historical QA 收據（nested-graph follow-up 前）

以下 10P/44P 與其 SHA 是 graph traversal 實作前的 capability checkpoint 收據，僅保留作歷史記錄；本 note 的 current nested-graph follow-up QA 才對應下方新 source/test SHA。

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py -q -o addopts= -p no:cacheprovider
```

結果 **10 passed**，pytest log SHA-256 `493AB8ECB0C44D1622F50C8DB3E3FB10AE7B9B51A7EAB65FD1AD21A8B1E1BCAB`；該時 source SHA 為 `471F02A1E7E440A5BAD7DC19794D5B5926368A8C7F0F8CB25FA3C8321F864CA6`，不是 current source。

先前在 TEMP `C:\r26q\b07829ac` 的 10-pass log `840CB09639E8287E075A32422976529EC5DDF61D8E963AAA4F994BAB3EFB08CB` 早於最終 source write，只作歷史 diagnostic，不作最終 source 收據。

相鄰 service route 使用 fresh short TEMP `C:\r26q\22dd7215`：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py tests/test_prepared_ml_input_contract.py tests/test_recommendation_service_calibration_integration.py -k 'not workbench_ui and not isolated_producer_consumer_advice' -q --tb=short -o addopts= -p no:cacheprovider
```

結果 **44 passed／2 deselected**，pytest log SHA-256 `8A57262E1BCA16F369F52813698758E65C2AF274CB6AA4362953FC653BD968BA`。被排除的是兩個 UI/workbench tests。

R015 獨立複核另以 fresh short TEMP 重跑最終 frozen source：專項路由 `C:\r26q\rv_00616ae0\unit.log` 為 **10 passed**，log SHA-256 `BBB897D94514ECD40F09F99E89BC5B234D5909504384264DC82CF10B2EFC7017`；相鄰路由 `C:\r26q\ra_5298e53b\adjacent.log` 為 **44 passed／2 deselected**，log SHA-256 `DCF37C2D43C1FC3161D0EB1DCC6B785C72BB2DE9BFD680EB1A9726412A56C0A8`。Reviewer scoped mypy 4 source files／0 issues，py_compile 與 diff-check 通過。Review receipt 僅接受上述 experimental model-resolution API；inventory 中新增測試只有單一 entry，但全庫 inventory guard 為 **6 passed／1 failed**，另有 **108 missing** entries 與 `documentation_count_drift: 5`；不可稱全庫 inventory guard 通過。

先前使用深 TEMP `C:\Users\archi\AppData\Local\Temp\r026cap_verify_6d36eb8935cf48048f74d56f31cf964f` 的 route 有 **39 passed／5 failed／2 deselected**；失敗 traceback 顯示 nested `training_lineage` 或 source-contract temporary path 到 266 characters，Windows `mkstemp/open` 回 `FileNotFoundError`。另以相同 public-service receipt test 做長短路徑對照：short basetemp `C:\Users\archi\AppData\Local\Temp\rcaprcpt_45ebe387509d\pytest` 產生 239-character receipt destination 並 **1 passed**（log SHA `BBB1F8F973008D1153F0B293803204A87EFE0B5AE0B103551460CB9D04B1C7BD`）；長 basetemp `C:\Users\archi\AppData\Local\Temp\r26receipt_long_ad6b6be8661c401d9eb3cea4bf0c586f\pytest` 產生 266-character destination，`_write_create_only()` 的 `os.link(temporary, path)`（`ml_module/recommendation_inference_provenance.py:1860`）回 `FileNotFoundError [WinError 3]`，再包成 `RecommendationProvenanceError("immutable receipt publication failed")`（log SHA `31AD3F3D8AA58DA951795F8CE196955017EEB567CE52A6CE13DE931AE12D705F`）。改用短 TEMP 後完整 service route 44P/2D 通過，沒有 receipt failure。這些失敗由測試輸出根路徑超過 Windows MAX_PATH 引起，不能算作功能 PASS 或產品回歸；舊長路徑 combined-route log SHA `C07F7C89FBC3F99904DD4E2DC9685F672002D97744B014745EB81F2EC0474BDB`。

## Current nested-graph follow-up QA

新測試涵蓋 nested Pipeline estimator、Isotonic estimator、ndarray/view 與 interp1d x-view alias、nested provenance dict、pointer lineage list、A/B capability 共用 ndarray view；另驗 cycle、unknown model field/type、object array、未知 no-closure callable、closure callable、node budget fail closed，以及 runtime mismatch 在 pointer/loader I/O 前 fail closed。測試不呼叫 model fitting/predict，不接 live service runtime handoff。

Fresh short TEMP 專項根 `C:\r26q\v8a0be52b`，`PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP`、`TMP` 與 pytest basetemp 隔離：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py -q --tb=short -o addopts= -p no:cacheprovider --basetemp C:\r26q\v8a0be52b\p
```

結果 **20 passed**；pytest log SHA-256 `C2A36889563AD3EE8490701ABE49A6C36A250AA6C815A60E4408D6977221515C`。

Fresh short TEMP 相鄰 route 根 `C:\r26q\be0284eda`：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py tests/test_prepared_ml_input_contract.py tests/test_recommendation_service_calibration_integration.py -k 'not workbench_ui and not isolated_producer_consumer_advice' -q --tb=short -o addopts= -p no:cacheprovider --basetemp C:\r26q\be0284eda\p
```

結果 **54 passed／2 deselected**，pytest log SHA-256 `0CE5418A6D5C0152EE5E9AF9820BBC7E72EBF51252382A0BC07B8195A2DBE67C`。先前以長 TEMP root 執行同兩個 receipt tests 時，投影 receipt status 變為 unavailable；使用短根重跑同 tests 為 2 passed。此回歸收據只採短根結果，避免把 Windows 長路徑的失敗誤作 graph 行為差異。

Scoped mypy：

```powershell
.\.venv\Scripts\python.exe -B -m mypy app_module/recommendation_calibration_consumer.py ml_module/prepared_input_contract.py app_module/recommendation/ml_adapter.py app_module/recommendation_service.py
```

結果 **4 source files／0 issues**。同四個 source 檔及 capability test `py_compile` 通過，`git diff --check` 通過。上述 fingerprint 僅記錄此已驗 Windows runtime。

## 凍結 SHA-256 與限制

- `app_module/recommendation_calibration_consumer.py`: `442A5EB46A5F3241D217834554788FC8A800881BECE494882F519142D85CA4BC`
- `tests/test_r026_invocation_model_capability.py`: `8D6403B8803BD4294745ED46C0CF3F0B41DD1650232674E4803FD5FB5E4D91E2`
- unchanged `app_module/recommendation_service.py`: `B66C6BF37A8EF63798FF6AAF2EB25603852BEEBB23C4378920425F804EB3D0EF`
- unchanged `ml_module/recommendation_calibration_training.py`: `F394E427234A8A43D30BD7688D1AD41BAE4A2174A510FE2F5067E5A661941B61`
- unchanged `ml_module/probability_calibration.py`: `6AB7BCD2074E5588C7B03B6E93E219663727A4EFFA83457D3E17A375B788BB87`
- unchanged `ml_module/model_artifact_loader.py`: `0B76494E757F6DEDDAFC13A5BFFB64B8C09B8C1A4C533A2FF02FC3D1002AB484`

The service integration tests exercise the existing default projection path without passing `_invocation_capability`; the service source remained byte-identical at the cited SHA. The current adjacent evidence is 54P/2D. This slice still does not wire the experimental capability into live service, construct `PreparedMLInput`/`PreparedMLRuntimeInputV1`, call `PreparedMLProjector`, or write receipts. It proves alias isolation only for the exact gated model/lineage profile above. It does not prove pointer lease/ABA exclusion, DB/source/model/receipt shared transaction, or full R026/TMP-ML-01 completion.

## 獨立複核收據與 residual

R015 對上述 frozen source/test 的獨立複核無 P1/P2，root 判定本 nested-graph/runtime-profile follow-up 為 bounded `ACCEPTED_SCOPE`。Reviewer fresh short TEMP 專項 route **20 passed**，log `C:\t\r26g1\pytest.log` SHA-256 `0DD309BA6814B30BD32BC9F745BA0903E41B432C084463802A7E5B1CF0F2661E`；相鄰 route **54 passed／2 deselected**，log `C:\t\r26g2\pytest.log` SHA-256 `462DC72865B970F7AE5C9354A1F94F3C3AE94B716B7D5515411F1CCD5B7BD696`。Reviewer scoped mypy 4 files／0 issues，py_compile 與 diff-check 通過。

此 bounded acceptance 不外推到未列 runtime profile；depth/node/array/byte/element 各 budget 維度未逐一觸發驗證；capability 未綁定 feature/source/receipt；pointer ABA 與 receipt publication race 未解。能力仍是 experimental model-resolution API，不得 runtime handoff；未接 `PreparedMLRuntimeInputV1`，亦不表示 R026 或 `TMP-ML-01` 完成。
