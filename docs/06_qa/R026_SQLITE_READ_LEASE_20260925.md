# R026 SQLite 單次讀取 Lease 試作 QA

日期：2026-09-25

## 範圍與觀察

本切片只在 `MLHistoricalSnapshotProvider` 增加 provider-only `open_read_lease()` API。Lease 保留同一個唯讀 SQLite connection，於開啟時記錄該 connection 的 `PRAGMA data_version` 與檔案 stat；只允許呼叫一次 `load()`，並可在該次載入後呼叫 `assert_unchanged()`。載入本身仍使用原有交易、查詢順序、query count、source fingerprint 與回傳 DTO；交易在 `load()` 返回前結束，因此 lease 持有連線時不持有 read transaction。既有 `load()` 仍走相同 provider 讀取流程。

受控 TEMP 測試觀察到：

- WAL 模式中，load 後另一個 connection 提交修改，lease postcheck 拒絕。
- WAL 模式中，另一個 connection 先改值再提交還原值的兩次 commit，lease 仍拒絕；fresh load 與已捕獲 snapshot 的 row 值仍為原值。
- DELETE journal 模式中，load 返回後另一個 connection 以 `timeout=0` 成功提交，證明 lease 沒有把 read transaction 留開；lease 隨後拒絕該來源變動。
- Lease 只接受一次 load；關閉後 postcheck 與重新進入均拒絕使用。

這個 API 尚未接入 recommendation service、四 namespace aggregate、`PreparedMLInput`、source revision 或 receipt。相同 connection 的 `data_version` 只支援該 lease 存活期間的外部 commit 觀察；它不是 durable generation、row-content hash 或跨 connection identity，也未排除檔案替換 ABA。此試作不證明 sidecar 與 SQLite 跨資源原子性，亦不擴大先前單次 provider load 交易一致性結論。

## 測試與重跑

先新增四個測試，未實作 API 時 4/4 以 `AttributeError`（provider 尚無 `open_read_lease`）失敗。接線後使用下列 fresh TEMP 路由：

```powershell
$runRoot = Join-Path $env:TEMP ('r026lease_final_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $runRoot 'data'
$env:OUTPUT_ROOT = Join-Path $runRoot 'output'
$env:TEMP = $runRoot
$env:TMP = $runRoot
$baseTemp = Join-Path $runRoot 'pytest'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_sqlite_read_lease.py tests/test_r026_calibration_legacy_preparation_baseline.py tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider --basetemp $baseTemp
```

結果：38 passed，12.56 秒。實際 TEMP root：`C:\Users\archi\AppData\Local\Temp\r026lease_final_0a5974a2`。該次測試未接觸正式資料。

型別與語法檢查：

```powershell
.\.venv\Scripts\python.exe -m mypy data_module/ml_historical_snapshot_provider.py tests/test_r026_sqlite_read_lease.py
.\.venv\Scripts\python.exe -m py_compile data_module/ml_historical_snapshot_provider.py tests/test_r026_sqlite_read_lease.py
```

結果：mypy 2 個檔案 0 errors；py_compile exit 0。新測試已登錄於 `qa/full_app_healthcheck/test_inventory.py` 的 `service-oracle-recommendation` 類別。

凍結檔案 SHA-256：

- `data_module/ml_historical_snapshot_provider.py`: `0223A3665B68DB950CF806D87F7C3CC3BBE925277813D083F7AFBB3A2A8E3928`
- `tests/test_r026_sqlite_read_lease.py`: `1A83FC0D618031A1B002D34DF9661005A308766C249EB8EC13CA0BFB6306323D`
- `qa/full_app_healthcheck/test_inventory.py`: `C7C280BA9A6E5322DE5C784EEEB10105A193E728351ABE212B0D30A031C3ACE4`

## 狀態

這是有界 provider API/行為試作，尚非 R026 cutover 證據。Service wiring、呼叫期間 lease 的生命週期、四 namespace 前後 identity、SQLite row-content revision、跨資源 atomicity、durable generation 與 ABA 排除都仍待獨立設計及驗證；R026/TMP-ML-01 維持開啟。

## R015 獨立複核（2026-09-25）

R015 依 frozen provider SHA-256 `0223A3665B68DB950CF806D87F7C3CC3BBE925277813D083F7AFBB3A2A8E3928` 與 lease test SHA-256 `1A83FC0D618031A1B002D34DF9661005A308766C249EB8EC13CA0BFB6306323D` 完成唯讀複核，未發現 P1/P2，判定 provider-only lease 為 bounded `ACCEPTED_SCOPE`。

R015 使用兩個 fresh TEMP 根執行彼此獨立、內容有重疊的三檔路由；結果不相加：

- `C:\Users\archi\AppData\Local\Temp\r026-lease-review-0fd1cc6d55`：`tests/test_r026_sqlite_read_lease.py`、`tests/test_ml_historical_snapshot_provider.py`、`tests/test_r026_calibration_legacy_preparation_baseline.py`，**26 passed**。
- `C:\Users\archi\AppData\Local\Temp\r026-lease-integration-6d5803fdcb`：`tests/test_r026_sqlite_read_lease.py`、`tests/test_ml_historical_snapshot_provider.py`、`tests/test_ml_historical_feature_computation.py`，**19 passed**。

兩次均設 `PROFILE=test`，將 `DATA_ROOT`、`OUTPUT_ROOT` 與 pytest `--basetemp` 指向各自 TEMP 子目錄；未接觸正式資料。Scoped mypy 命令 `python -B -m mypy --follow-imports=silent data_module/ml_historical_snapshot_provider.py tests/test_r026_sqlite_read_lease.py` 結果為 2 source files／0 issues；provider、lease test 與 provider test 的 `py_compile` 通過。QA 執行結果為本次工具輸出，未另存 pytest log，故不提供 log hash。

複核確認同連線 `data_version`、單次 load 的交易結束、WAL commit 觀察、DELETE journal 鎖與交易後寫入檢查。此結論只接受 provider-only bounded slice：lease 尚未接入 service，`close()` 不自動呼叫 `assert_unchanged()`；sidecar／SQLite atomicity、durable generation、跨多次 provider call 的同版本保證與完整 ABA 排除仍未解。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。
