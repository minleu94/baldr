# R026 invocation model-resolution capability — bounded experimental evidence

**狀態：** R015 獨立複核未發現 P1/P2，root 判此 consumer-side model-resolution capability 為 bounded `ACCEPTED_SCOPE`。接受嚴限 experimental API，不得接入 runtime handoff；它不證明完整 mutable model-graph isolation，也不是 `PreparedMLRuntimeInputV1` handoff。R026 與 `TMP-ML-01` 維持 open。

## 實作界線

`RecommendationCalibrationConsumer.resolve_invocation_projection_capability()` 只接受 ASCII invocation scope、decision date 及呼叫端已捕獲的 identity。建立能力時直接讀 pointer bytes，使用 fresh consumer 與預設 `joblib.load` 安全載入路徑重新 resolve active candidate/lineage，再核對 pointer bytes 前後與 fresh identity。只有 exact `RecommendationCalibrationConsumer`、exact `SafeShadowModelArtifactLoader`、default `joblib.load` 及 exact `RunnableRecommendationCalibrationModel` top-level type 可取得能力；自訂或 memoizing deserializer 被拒絕。帶 `source_contract_binding` 的 inference provenance 也會在來源合約檔案讀取前被拒絕，避免 capability projector 在投影期間再做 filesystem provenance validation。

每個 capability 綁定一個 consumer owner、scope、date 與 identity digest，且該 capability 僅能投影一次、不可 copy/deepcopy/pickle。`WeakValueDictionary` 只在同 scope 的 capability 仍存活時拒絕重複建立；capability 被 garbage-collected 後 scope 可重用，永久唯一性須由未來 caller 保證，本 slice 未證明。帶 `source_contract_binding` 的投影請求會在 capability 被標為 used 前拒絕；這是呼叫參數的 filesystem-I/O guard，不構成持久 source policy 或 validated-input 證據。未來 runtime caller 必須先提供 immutable、已驗證的 input facts。這是 model-resolution API；沒有綁定本次 feature/candidate set，也沒有 live service caller。pointer 在最後一次 byte check 後仍可改變，ABA 與 receipt publication 競態亦未由此能力解決。

## 尚未證明的 nested mutable graph

精確 production model class `RunnableRecommendationCalibrationModel`（`ml_module/recommendation_calibration_training.py`）含 return/upside/optional after-cost `Pipeline`、upside/optional after-cost `FittedShadowProbabilityCalibrator`。training factories 建立 `SimpleImputer → StandardScaler → Ridge` 或 `SimpleImputer → StandardScaler → LogisticRegression`；fitted calibrator 的 `.estimator` 是 mutable `IsotonicRegression`。其 fitted state 會持有 mutable estimators、step/list/dict state 與 NumPy arrays；頂層 dataclass 亦非 frozen。現有 alias guard 比較 consumer/model/lineage 與直接 model component identity，測試可拒絕共享 model、共享 pipeline component 和自訂 memoizing deserializer，但沒有遞迴驗證 Pipeline 內 estimator、transformer arrays、calibrator estimator/arrays 的整個 object graph。故不得宣稱 arbitrary mutable alias isolation；nested graph validation 是 runtime handoff 前的獨立 gate。

## QA 收據

Fresh short TEMP `C:\r26q\c4359f12`，`PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP`、`TMP` 隔離。此收據是在最終 consumer source SHA `471F02A1E7E440A5BAD7DC19794D5B5926368A8C7F0F8CB25FA3C8321F864CA6` 寫入後重跑。專項命令：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py -q -o addopts= -p no:cacheprovider
```

結果 **10 passed**，pytest log SHA-256 `493AB8ECB0C44D1622F50C8DB3E3FB10AE7B9B51A7EAB65FD1AD21A8B1E1BCAB`。

先前在 TEMP `C:\r26q\b07829ac` 的 10-pass log `840CB09639E8287E075A32422976529EC5DDF61D8E963AAA4F994BAB3EFB08CB` 早於最終 source write，只作歷史 diagnostic，不作最終 source 收據。

相鄰 service route 使用 fresh short TEMP `C:\r26q\22dd7215`：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py tests/test_prepared_ml_input_contract.py tests/test_recommendation_service_calibration_integration.py -k 'not workbench_ui and not isolated_producer_consumer_advice' -q --tb=short -o addopts= -p no:cacheprovider
```

結果 **44 passed／2 deselected**，pytest log SHA-256 `8A57262E1BCA16F369F52813698758E65C2AF274CB6AA4362953FC653BD968BA`。被排除的是兩個 UI/workbench tests。

R015 獨立複核另以 fresh short TEMP 重跑最終 frozen source：專項路由 `C:\r26q\rv_00616ae0\unit.log` 為 **10 passed**，log SHA-256 `BBB897D94514ECD40F09F99E89BC5B234D5909504384264DC82CF10B2EFC7017`；相鄰路由 `C:\r26q\ra_5298e53b\adjacent.log` 為 **44 passed／2 deselected**，log SHA-256 `DCF37C2D43C1FC3161D0EB1DCC6B785C72BB2DE9BFD680EB1A9726412A56C0A8`。Reviewer scoped mypy 4 source files／0 issues，py_compile 與 diff-check 通過。Review receipt 僅接受上述 experimental model-resolution API；inventory 中新增測試只有單一 entry，但全庫 inventory guard 為 **6 passed／1 failed**，另有 **108 missing** entries 與 `documentation_count_drift: 5`；不可稱全庫 inventory guard 通過。

先前使用深 TEMP `C:\Users\archi\AppData\Local\Temp\r026cap_verify_6d36eb8935cf48048f74d56f31cf964f` 的 route 有 **39 passed／5 failed／2 deselected**；失敗 traceback 顯示 nested `training_lineage` 或 source-contract temporary path 到 266 characters，Windows `mkstemp/open` 回 `FileNotFoundError`。另以相同 public-service receipt test 做長短路徑對照：short basetemp `C:\Users\archi\AppData\Local\Temp\rcaprcpt_45ebe387509d\pytest` 產生 239-character receipt destination 並 **1 passed**（log SHA `BBB1F8F973008D1153F0B293803204A87EFE0B5AE0B103551460CB9D04B1C7BD`）；長 basetemp `C:\Users\archi\AppData\Local\Temp\r26receipt_long_ad6b6be8661c401d9eb3cea4bf0c586f\pytest` 產生 266-character destination，`_write_create_only()` 的 `os.link(temporary, path)`（`ml_module/recommendation_inference_provenance.py:1860`）回 `FileNotFoundError [WinError 3]`，再包成 `RecommendationProvenanceError("immutable receipt publication failed")`（log SHA `31AD3F3D8AA58DA951795F8CE196955017EEB567CE52A6CE13DE931AE12D705F`）。改用短 TEMP 後完整 service route 44P/2D 通過，沒有 receipt failure。這些失敗由測試輸出根路徑超過 Windows MAX_PATH 引起，不能算作功能 PASS 或產品回歸；舊長路徑 combined-route log SHA `C07F7C89FBC3F99904DD4E2DC9685F672002D97744B014745EB81F2EC0474BDB`。

Scoped mypy：

```powershell
.\.venv\Scripts\python.exe -B -m mypy app_module/recommendation_calibration_consumer.py ml_module/prepared_input_contract.py app_module/recommendation/ml_adapter.py app_module/recommendation_service.py
```

結果 **4 source files／0 issues**。同四個檔案 `py_compile` 通過，`git diff --check` 通過。環境為 Windows、CPython 3.11.9、NumPy 2.3.5、Pandas 2.3.3。

## 凍結 SHA-256 與限制

- `app_module/recommendation_calibration_consumer.py`: `471F02A1E7E440A5BAD7DC19794D5B5926368A8C7F0F8CB25FA3C8321F864CA6`
- `tests/test_r026_invocation_model_capability.py`: `A11C6073C3621C37CAED8B130988ADE97364EC189272D956531422BBD201A5E7`
- unchanged `app_module/recommendation_service.py`: `B66C6BF37A8EF63798FF6AAF2EB25603852BEEBB23C4378920425F804EB3D0EF`
- unchanged `ml_module/recommendation_calibration_training.py`: `F394E427234A8A43D30BD7688D1AD41BAE4A2174A510FE2F5067E5A661941B61`
- unchanged `ml_module/probability_calibration.py`: `6AB7BCD2074E5588C7B03B6E93E219663727A4EFFA83457D3E17A375B788BB87`
- unchanged `ml_module/model_artifact_loader.py`: `0B76494E757F6DEDDAFC13A5BFFB64B8C09B8C1A4C533A2FF02FC3D1002AB484`

The service integration tests exercise the existing default projection path without passing `_invocation_capability`; the service source remained byte-identical at the cited SHA. The 44P short-path rerun is the current evidence. This slice does not wire the experimental capability into live service, construct `PreparedMLInput`/`PreparedMLRuntimeInputV1`, call `PreparedMLProjector`, or write receipts. It does not prove arbitrary nested model graph isolation, pointer lease/ABA exclusion, DB/source/model/receipt shared transaction, or full R026/TMP-ML-01 completion.
