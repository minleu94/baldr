# R026 單一模型 artifact same-bytes loader

**狀態：** bounded implementation 獲 root 依 R015 獨立複核判為 `ACCEPTED_SCOPE`。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。此 slice 只為 opt-in loader 提供「artifact hash 與反序列化使用同一捕獲 bytes」；未接 live service/runtime handoff，不代表完整 R026 acceptance。

## 變更範圍與行為

`SafeShadowModelArtifactLoader.load()` 的原有簽章、`ShadowModelArtifactLoadResult` 型別、Path deserializer 路徑與既有拒絕行為未改。本 slice 新增 `load_same_bytes_v1()`，並以 `SameBytesShadowModelArtifactLoadResultV1` 回傳舊 load result 的包裝與兩個明確 digest：

- `captured_artifact_sha256`：由這次單次串流寫入 private seekable spool 的 serialized bytes 計算；即使 hash 不符也可用來辨識捕獲到的 bytes。
- `loaded_serialized_bytes_sha256`：只有預設 joblib deserializer 已從該 spool 成功返回物件才提供；模型後續 identity check 失敗時仍可辨識已載入的 bytes。

opt-in 路徑只允許 loader 建構時使用預設 `joblib.load`；custom Path deserializer 會 fail closed，不會被改為接收 file object。通過既有 root/path、manifest schema/hash、model family、registry/schema/library 與 artifact identity checks 後，loader 將 artifact 以 1 MiB chunks 串流到 `SpooledTemporaryFile`，同一 pass 寫 spool 並計 SHA-256。預設 spool 記憶體門檻為 8 MiB，超過後由 Python tempfile rollover；只有捕獲 hash 等於 manifest artifact hash，且捕獲後 path 仍解析至同一受控 root child，才 rewind spool 並呼叫 `joblib.load(spool, mmap_mode=None)`。spool 由 `with` 管理，所有返回路徑均關閉。Hash mismatch、I/O、deserialization、path/control 或 model identity 問題均不回傳 ready model。

此 API 的版本為 `shadow-model-artifact-same-bytes.v1`。它只綁定本次 joblib deserializer 的單一 serialized artifact input，不綁定 pointer、candidate JSON、原始 manifest JSON bytes、training provenance、lineage sidecar、receipt 或 service invocation。它也不是完整 `ModelBinding` 或 `PreparedMLRuntimeInputV1`。`SameBytesShadowModelArtifactLoadResultV1` 是可由呼叫者手工建構的 dataclass；只有由 `load_same_bytes_v1()` 產生的結果才帶有該次 loader path 的 provenance，不能只憑手工組出的 digest 宣稱已驗證同 bytes。同一 loader 可分別處理 active 與 prior/lineage artifact 根目錄；目前沒有將此 API 接入 consumer 的 active/lineage production 路徑，亦不代表有序 lineage 集合及其 manifest 已共同綁定。

## 紅綠與相容性案例

`test_same_bytes_loader_closes_hash_then_reopen_toctou_without_changing_legacy_path` 建立相同 manifest identity、不同額外模型參數的兩份 joblib bytes。測試在舊 Path API 完成 hash 後，對 deserializer 的 artifact open 以 one-shot `builtins.open` shim 回傳替代 bytes；舊 API 會回傳替代模型。相同 seam 下新 API 不重新開 artifact path，回傳原 artifact 對應模型，且 `loaded_serialized_bytes_sha256 == manifest.artifact_hash`。這固定舊 ABI 路徑與新 opt-in 路徑的差別。

其餘測試涵蓋 hash mismatch 不呼叫 deserializer、captured 與 loaded digest 的定義、active/prior 兩組獨立 artifact 都可走同一 opt-in API、custom Path deserializer 仍只供舊 API 使用，以及新 API 保留 library、root containment 與 post-deserialization model identity gates。Malformed manifest container 有直接回歸測試；spool 短寫 guard 目前僅經程式碼檢視，沒有直接注入短寫測試。模型參數只作 synthetic discriminator，不參與策略、feature 或市場計算。

## Fresh TEMP 驗證

環境為 Windows 10 build `10.0.26200-SP0`、CPython `3.11.9`、joblib `1.5.2`、NumPy `2.3.5`、Pandas `2.3.3`、SciPy `1.16.3`、scikit-learn `1.8.0`。`PROFILE=test`；`TEMP`、`TMP`、`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest basetemp 均設於新 TEMP 根 `C:\Users\archi\AppData\Local\Temp\r026_samebytes_final_8d15d994`。

執行命令：

```powershell
$qaRoot = 'C:\Users\archi\AppData\Local\Temp\r026_samebytes_final_8d15d994'
$env:PROFILE = 'test'
$env:TEMP = Join-Path $qaRoot 'tmp'
$env:TMP = $env:TEMP
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'out'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_model_artifact_same_bytes_loader.py tests/test_ml_model_artifact_loader.py tests/test_ml_model_artifact_manifest.py tests/test_r026_invocation_model_capability.py tests/test_r026_model_resolution_facts.py tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider --basetemp (Join-Path $qaRoot 'pytest')
```

結果 **60 passed in 15.96s**，exit 0；pytest log `C:\Users\archi\AppData\Local\Temp\r026_samebytes_final_8d15d994\pytest.log` SHA-256 `7E7B10E959FD78D9A14283F59F1EBF28FA77A9CA83E96F3DB92CC900A5870EF2`。路由含新 loader、既有 loader/manifest、invocation capability、model-resolution facts 與 calibration service integration，確認 legacy default consumer 沒有改用 opt-in API。R015 以另一 fresh TEMP 對最終 frozen bytes 獨立重跑六檔路由 **60 passed**，log `C:\t\r26sb1\pytest.log` SHA-256 `F4157EBF0613934D94C22EEA96D9771B9B850119EEA9AB972E5562606A23636B`；mypy 1 file／0 issues、compile 通過，未發現 P1/P2。Root 依此判 bounded `ACCEPTED_SCOPE`。

Scoped mypy：`ml_module/model_artifact_loader.py`，1 file／0 issues。該 source 與新 test `py_compile` 通過；`scripts/quant_guard_linter.py` 的 financial-float 與 look-ahead checks 通過。曾有一次未保留 traceback 的 inventory membership 命令回傳 exit 1，原因無法從該次收據確診；以直接匯入 `TEST_INVENTORY` 並檢查同一 key/category/count 重跑，結果 exit 0，恰有一筆 `service-oracle-recommendation` entry。這只是本測試的 membership/category 檢查，不是全庫 inventory guard。`git diff --check` 與 QA note trailing-whitespace scan 通過；report 的 LF/CRLF 僅有 Git 平台換行提示。

Frozen SHA-256：

- `ml_module/model_artifact_loader.py`: `F5A54A94FBCC3CB4AFDC35C7B4825A4D8A455ED3DB9B518289C07EECC0CBEA1B`
- `tests/test_r026_model_artifact_same_bytes_loader.py`: `0D8BF557D3B8FEBA503A67CC05632DD3F6E8E5130B63C228725D15417262A938`
- `qa/full_app_healthcheck/test_inventory.py`: `C1CBABACD0D3EE587AEF7A8F952A2726EE16B924D877178701B7EA11F54A05B7`

Manifest/producer/schema 與 serialized model bytes 均未改；既有 artifact hash 和 old loader output ABI 維持。Source 檔 SHA 有變，已透過上述 old loader、manifest、capability、facts 與 service integration 路由重驗相容性。

## Look-ahead 與安全限制

本 slice 僅讀取 shadow model artifact 與 manifest，不讀市場資料、不建 feature、不預測、不改模型、不訓練，也不改 decision date/cutoff；沒有新增 look-ahead 路徑。Deserializer 只在 artifact bytes 已與已驗 manifest 宣告 hash 相符後執行，且只呼叫既有預設 `joblib.load`，不接受自訂 deserializer 擴大載入接口。

其餘 pointer/candidate/manifest/training-lineage/receipt 仍各自有 path reads；manifest hash 是 canonical payload hash，不等於原始 manifest bytes hash。現行 consumer 尚未使用新 API；active/prior 測試是兩個合成 artifact-root 呼叫，不是 lineage integration test。Captured spool 與 path postcheck 不能排除路徑 restore/ABA 或 postcheck 之後競態；temp disk 容量、超大模型、磁碟錯誤與其他 joblib/runtime profile 未驗。這個 single-artifact slice 不證明完整同次 source/model/receipt identity，不建立完整 ModelBinding，不構成 PreparedMLRuntimeInput 或 runtime handoff，也不關閉 R026／`TMP-ML-01`。
