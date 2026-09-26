# R026 capability pointer captured-bytes 品質驗證

**狀態：**Root 依 R015 獨立複核裁定本 pointer captured-bytes 切片為 bounded `ACCEPTED_SCOPE`，無 P1/P2。接受範圍僅是 experimental capability 在 fresh consumer reload 時解析 outer capture 的 pointer bytes；R026 維持 `IN_PROGRESS`、`TMP-ML-01` 維持 `ACTIVE`，不代表 runtime handoff 或 R026 結案。

**範圍：**僅供 experimental capability 使用，將 `resolve_invocation_projection_capability()` 已讀取的 pointer bytes 傳給 fresh consumer 的 `reload()`。一般 `reload()` 與 service 路徑不變。R026 維持 `IN_PROGRESS`；`TMP-ML-01` 維持 `ACTIVE`；本切片未授權 runtime handoff。

## 本切片固定的行為

capability resolver 僅在 fresh consumer 上保留初始 pointer byte buffer。啟用 experimental capture flag 時，`reload()` 會解碼並解析該 buffer，不會重新開啟 pointer path 讀取 JSON。resolver 仍執行原有的載入後 path-byte 檢查、loaded-payload 比對、identity 檢查與清理。buffer 與其消耗摘要會在 `finally` 清除。

Evidence 分別提供以下摘要：

- `raw_bytes_sha256` 對精確捕獲的序列化 pointer bytes 計算雜湊。
- `canonical_payload_sha256` 使用既有 canonical JSON payload hash（`ensure_ascii=False`、鍵排序、compact separators）。

行為測試在 outer capture 與 fresh reload 之間，暫時將 pointer 換成不同的 `rule_only` payload，再還原原始 bytes。fresh resolver 仍維持 active，並記錄原始 pointer payload。第二個測試將 path 內容換成相同 JSON 值的另一種序列化，並觀察 reload 實際消耗的 JSON 輸入；fresh reload 解析的仍是原始序列化。兩者的 raw digest 不同，但 canonical payload digest 相同。legacy 對照測試確認一般 reload 與 projection 輸出未改變。

same-bytes parse evidence 僅適用於這條 optional capability path 捕獲的 pointer bytes。它不會綁定 candidate JSON、manifest、lineage declarations、decision receipt、artifact bytes 或後續 receipt 發布。既有 before/after path 檢查不是 lease，無法避免 A→B→A 競態，也無法阻止 capability 建立後的變更。

## 凍結檔案

- `app_module/recommendation_calibration_consumer.py` SHA256: `C73CEEC76ECA26924C0858AEEE16E6E4E2E4340CF284224774F0C591257EE8A3`
- `tests/test_r026_invocation_model_capability.py` SHA256: `780D0F9F301306B938CB1ABF91CD8096B6466515F484162A059467D238F1B312`
- 既有 inventory 已登錄 `tests/test_r026_invocation_model_capability.py`；本次不需修改 inventory。

## Fresh TEMP 驗證

Runtime：Windows CPython 3.11.9；`PROFILE=test`；`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP`、`TMP` 與 pytest basetemp 均隔離在 `C:\Users\archi\AppData\Local\Temp\r26pc_99321350`。

聚焦與相鄰測試路由：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_invocation_model_capability.py tests/test_r026_model_resolution_facts.py tests/test_r026_model_artifact_same_bytes_loader.py tests/test_ml_model_artifact_loader.py tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider --basetemp C:\Users\archi\AppData\Local\Temp\r26pc_99321350\pytest
```

結果：**64 passed**，exit 0。Log：`C:\Users\archi\AppData\Local\Temp\r26pc_99321350\focused-route.log`，SHA256 `FDD09C228F5629DDC7A5DB66344A05E53E876C3E4D1B22E093AF167EDB5464EF`。

其他檢查均通過：

```powershell
.\.venv\Scripts\python.exe -m mypy app_module/recommendation_calibration_consumer.py --follow-imports=silent
.\.venv\Scripts\python.exe -m py_compile app_module/recommendation_calibration_consumer.py tests/test_r026_invocation_model_capability.py
.\.venv\Scripts\python.exe scripts\quant_guard_linter.py
git diff --check -- app_module/recommendation_calibration_consumer.py tests/test_r026_invocation_model_capability.py
```

## 獨立複核收據

R015 以另一個 fresh short TEMP 重跑相同五檔路由，結果 **64 passed**，並完成 scoped mypy、py_compile；未發現 P1/P2。R015 未保存獨立 console log，因此本段只記錄其回報的測試結果與檢查，不提供未留存的 log 路徑或 SHA。Root 核對 source/test SHA 與 owner 保存的五檔路由收據均未漂移。

以上僅是 experimental pointer handoff 的有界證據，不代表 R026 或 `TMP-ML-01` 結案，也未建立 durable source generation、完整 `ModelBinding` 或 `PreparedMLRuntimeInputV1`。
