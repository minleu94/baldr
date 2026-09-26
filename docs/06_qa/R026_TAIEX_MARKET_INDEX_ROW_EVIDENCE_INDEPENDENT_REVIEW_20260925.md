# R026 TAIEX 大盤列證據獨立複審（2026-09-25）

## 結論

**原版 CHANGES_REQUIRED（兩項 P2）；修正版複審收據見文末。** 本輪獨立探測 SQLite row-evidence reader 的複合鍵唯一性與缺失資料庫唯讀行為；兩項均以 synthetic `PROFILE=test` 資料重現。依當時指示，確認程式缺陷後先修復，未重跑既有四檔路由；既有測試未涵蓋這兩個案例，當時並無資料可稱路由已知會失敗。這不是整體 R026 或 R028 裁決。

## 凍結來源識別

本輪探測開始前確認 HEAD 為 `bec423eef1d9e9d4a32410dac96cd233304489aa`。直接相關 frozen source SHA-256：

- `data_module/taiex_market_index_publication.py`：`ABDF171C6C82984F474922688BCBAC08D1455C1C1B3782D3C975EA379CB9465B`
- `tests/test_taiex_market_index_publication.py`：`B67B34266EF63119EB89E2290A69202F37C112110E71E8D5B6BA82DD1D96BD1B`

本報告描述上述 hash 對應的程式與測試狀態。未修改程式、測試或共用 `R026_TAIEX_MARKET_INDEX_ROW_EVIDENCE_20260925.md`。

## P2-1：Reader 接受重複 TAIEX 複合鍵

`data_module/taiex_market_index_publication.py:363-367` 對 `(指數名稱, 日期)` 執行 typed `SELECT` 後直接 `fetchone()`；沒有確認結果恰為一列。Reader 在 `:769-771` 只確認 sidecar 欄位仍存在，再以這個單列結果比對 hash/value/type，因此在無 UNIQUE 或 PRIMARY KEY 的相容表上，多出的同鍵列不會被檢查。publisher 的 schema 欄位驗證也不要求複合鍵唯一。

### 最小重現

1. 用 `tests/test_taiex_market_index_publication.py` 的 `_config`、`_loader` 與合成 TWSE response helper，在新 TEMP root 執行 `update_market_index("2026-05-28", capture_manifests=...)`，再呼叫 `UpdateService.publish_taiex_market_index(...)`，取得成功 sidecar。
2. 在該 synthetic SQLite DB 將 `market_indices` 重建成相同欄位、但不含任何 UNIQUE/PRIMARY KEY 限制的表；先插回剛發布的原 TAIEX 列，再插入第二列，其 `(指數名稱, 日期)` 相同、`收盤指數` 增加 1。
3. 確認該 key 的列數為 2；使用原 descriptor 呼叫 `read_taiex_market_index_evidence(...)`。

結果：`row count=2`，reader 仍回 `status="attested"`。第一列與 sidecar 相符，`fetchone()` 因而遮蔽第二列的不同值。使用的 synthetic TEMP root 為 `C:\Users\archi\AppData\Local\Temp\r026_duplicate_probe_ae649e0a338b460793e72759b67508d9`。

### 最小修復與回歸測試

保持 values 與 `typeof` 在同一 read transaction 和同一 SELECT 中，取至多兩列（例如 `fetchmany(2)`），只有恰一列才可比對／attest；零列與多列都回 `unknown`。加上無唯一鍵 schema 的 reader 測試，分別驗證第二列值不同及相同時都拒絕重複 key。現有 `tests/test_taiex_market_index_publication.py:542-545` 的 keyed replacement schema 明確有 `PRIMARY KEY ("指數名稱", "日期")`，未覆蓋這個相容 schema 邊界。

## P2-2：缺失資料庫路徑以讀取方式被自動建立

`data_module/taiex_market_index_publication.py:763` 使用預設 `sqlite3.connect(database_path)`。在 sidecar 的 database identity 符合該路徑時，SQLite 對不存在的路徑會建立空資料庫；reader 隨後雖回 `unknown`，但 readback 仍造成檔案系統寫入。

### 最小重現

1. 在新 synthetic TEMP root 完成 capture 與 publication，保留其 descriptor 與 database identity。
2. 將該 TEMP root 內原 SQLite 檔暫移至同目錄備份名稱，讓 descriptor 對應的原路徑不存在。
3. 將原路徑傳入 `read_taiex_market_index_evidence(...)`，然後檢查路徑。

結果：reader 回 `status="unknown"`、`reason_code="evidence_validation_failed"`，但原路徑被建立為 0-byte DB。探測後已移除新建空檔並還原 synthetic DB。使用的 synthetic TEMP root 為 `C:\Users\archi\AppData\Local\Temp\r026_missingdb_probe_eeb2b384cb0d4e2f8031c7926384fb18`。

### 最小修復與回歸測試

以 SQLite read-only URI（`mode=ro`、`uri=True`）開啟 reader 的資料庫，避免不存在時 create。新增同一路徑 identity、但實體 DB 已缺失的測試，斷言 reader 回 `unknown` 且路徑仍不存在。

## 範圍與限制

兩次重現均使用新建 TEMP root、`PROFILE=test` 及測試內 synthetic TWSE responses；未執行 scheduler、未呼叫 live ML，未讀寫正式資料，未 stage/commit/push。其他 R026 檢查與四檔完整路由待修正版重新複審；R028 仍為 BLOCKED。

## 修正版獨立複審收據（2026-09-25）

**兩項 P2 已關閉。接受此 bounded synthetic evidence slice；不代表完整 R026 PASS、R028 解鎖、正式資料／ML promotion 或 production 授權。** 狀態為 R026 `IN_PROGRESS`、R028 `BLOCKED`。

修正版 source SHA-256：

- `data_module/taiex_market_index_publication.py`：`80ECF0BBB74FAE3FF277793BF623CFA54AA5D3A8EC4355743F75AD4B12DB8593`
- `tests/test_taiex_market_index_publication.py`：`37E8D42BCBD8C39301C25151A0D2C063B6D4F9138F4547C285B9803EA25C44D2`

逐項確認：

- `_sqlite_typed_row()` 在同一 read transaction 與同一個 `SELECT` 用 `fetchmany(2)`，並要求恰好一列（publisher lines 363–370）。新增無 UNIQUE 約束的 schema 案例，分別驗證同值／異值的重複鍵都回 `unknown`（test lines 509–555）。
- reader 使用 `mode=ro` 的 SQLite URI（publisher lines 764–765）。缺 DB 測試保留原 path identity，讀取後確認路徑仍不存在，並在 `finally` 恢復 synthetic DB（test lines 558–578）。

本輪 fresh unique TEMP 根目錄：
`C:\Users\archi\AppData\Local\Temp\r026review_48989b29e61d4aa78dd9dcd28e3d8fdb`。路由環境為 `PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT`、pytest `--basetemp` 與 pycache 均置於此目錄下；四檔路由命令為：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests\test_taiex_market_index_publication.py tests\test_formal_market_data_repair.py tests\test_official_market_daily.py tests\test_scheduled_data_update_runner.py -q -o addopts= -p no:cacheprovider --basetemp=C:\Users\archi\AppData\Local\Temp\r026review_48989b29e61d4aa78dd9dcd28e3d8fdb\p
```

結果 **66 passed**。獨立 log 位於
`C:\Users\archi\AppData\Local\Temp\r026review_48989b29e61d4aa78dd9dcd28e3d8fdb\pytest.log`，SHA-256：
`A536859991BB058E88A22EAD0E1DD0BA8862E9B31BD804D5D75CEC78274165FE`。

Scoped checks：兩個修改 Python 檔 `py_compile` 通過；只檢查 publisher 的 scoped mypy 為 **1 source file, no issues found**。依 QA note，測試檔 mypy 探索命令會指出既有 helper typing 診斷；本輪未將其列作修補回歸，也未改動測試。

非行為文件事項：新增測試的兩句 CTAS 註解仍為英文（`tests/test_taiex_market_index_publication.py:524-525`），依 repository 語言規範待 owner 翻成繁體中文。這不影響本輪 66 passed；若僅翻譯註解，更新 test SHA 即可，不需要重跑 66 項路由。

本輪只使用 synthetic fixtures 與授權系統 TEMP；未啟動排程、未呼叫 live ML，未讀寫正式資料根目錄，未 stage/commit/push。
