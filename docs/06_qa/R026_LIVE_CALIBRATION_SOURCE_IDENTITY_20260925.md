# R026 Live Calibration 單次載入前後來源證據

日期：2026-09-25
狀態：live 四 namespace sidecar pre/post gate 經 R027 獨立複核後 bounded `ACCEPTED_SCOPE`；R026 仍 `IN_PROGRESS`、`TMP-ML-01` 仍 `ACTIVE`。此紀錄不代表 R026 或 ML cutover 完成。

## 實作範圍

`RecommendationService._apply_recommendation_calibration()` 在 live calibration 有消費者、日期與候選時，建立只在本次呼叫使用的 ASCII scope token。Token 不取自 `result_id`、`staged_invocation_id` 或路徑，也不寫入 context、inference provenance 或 receipt。

服務在 provider 載入前及 feature 建構後，各呼叫一次四 namespace source revision aggregate。兩次呼叫使用相同 resolved database path、決策日 cutoff、排序去重後的股票代碼及 scope token。服務驗證 aggregate 的型別、schema、scope、cutoff 與 digest；任一蒐集錯誤、身份不符或 digest 變更，都沿既有 unavailable/fail-closed 路徑結束，保留 rule recommendation，不讀 active model identity、不投影 ML、不寫 projection receipt。穩定證據時既有 provider PIT 載入、feature projection、provenance 與 receipt 格式不變。

## 驗證

Fresh 短 TEMP 根：`C:\Users\archi\AppData\Local\Temp\r269084e3`。`PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP/TMP` 及 pytest basetemp 均隔離於此根。

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_recommendation_service_calibration_integration.py tests/test_r026_calibration_legacy_preparation_baseline.py -q -s -o addopts= -p no:cacheprovider --basetemp C:\Users\archi\AppData\Local\Temp\r269084e3\p
```

結果：**34 passed**，12.20 秒，exit 0。完整輸出：`C:\Users\archi\AppData\Local\Temp\r269084e3\q.log`。

新增測試驗證兩次 aggregate 緊鄰同一 provider load/feature build、A/B 呼叫使用不同 token、錯配不滲入 provenance、前置蒐集失敗不讀 provider、後置錯誤不讀 active identity／不投影／不寫 receipt，以及 digest 變更 fail closed。既有 SQLite row 更新測試仍照原行為投影：該案例沒有修改任何 revision sidecar，aggregate 不代表 SQLite row generation。

`py_compile` 通過。`mypy --follow-imports=silent app_module/recommendation_service.py` 為 1 個 source file、0 issues。原 implementation QA 的一般 scoped 命令曾因相依 provider `__exit__` 型別註記失敗；該註記已在獨立 provider-only lease 試作修正。本次 R027 bounded service review 未重跑 service+collector mypy，因此不把舊錯誤當作目前結果，也不宣稱該組合已有新的 mypy gate。`git diff --check` 通過；Git 僅顯示工作檔 LF/CRLF 正規化提醒。

本次記錄的共享工作樹檔案 SHA-256：

- `app_module/recommendation_service.py`: `54205E777A6C3C8754217003FF50A819A3AA114CE8E3F264CAECCCBC0875926F`
- `tests/test_recommendation_service_calibration_integration.py`: `C35F7068AE4528FE905F20964982B9AD73D573803A01F2D3B25B8DB2939F1DE7`

較長 TEMP 根曾令三個既有 receipt 整合案例的 Windows hard-link 建立回報 `FileNotFoundError`；根因是巢狀 receipt 路徑過長。改用上述短隔離根後，兩檔完整路由通過。該失敗未透過修改 receipt 實作或測試預期處理。

## 限制與未完成項目

- 四 namespace aggregate 檢查的是 revision sidecar/artifact，不是 SQLite 資料列摘要或跨載入 generation。raw SQLite row 變動、WAL 變動與 ABA 不在此 gate 偵測範圍；本次保留舊 SQLite row mutation oracle。
- 前後掃描不是跨檔、跨 namespace 或 SQLite transaction 的原子快照；它只拒絕可由此 aggregate 觀察到的身份／digest 不一致。
- 本切片僅涵蓋 live calibration 的一次 provider load，不涵蓋 historical replay 的多次 provider calls，也不建立跨 SQLite generation 保證。
- R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`；仍需獨立處理 generation、WAL/ABA 與其他 namespace/呼叫路徑。

## R027 獨立複核狀態

R027 對 frozen service/test bytes 做 read-only review，並以 fresh short TEMP 重跑本 QA 所列兩檔 route：**34 passed**，11.78 秒，exit 0；TEMP root `C:\Users\archi\AppData\Local\Temp\r026live_review_ff84e49b`。未發現 P1/P2，僅接受 sidecar pre/post gate 的 bounded scope。服務 SHA-256 為 `54205E777A6C3C8754217003FF50A819A3AA114CE8E3F264CAECCCBC0875926F`；測試 SHA-256 為 `C35F7068AE4528FE905F20964982B9AD73D573803A01F2D3B25B8DB2939F1DE7`。

R026 另有 [provider-only SQLite read lease 原型](R026_SQLITE_READ_LEASE_20260925.md)，目前尚未接入 service，且仍待獨立複核。四 namespace evidence digest 不包含 SQLite row bytes/generation；SQLite-only mutation、跨資源原子性與 ABA 仍是後續 gate，故不關閉 `TMP-ML-01`。
