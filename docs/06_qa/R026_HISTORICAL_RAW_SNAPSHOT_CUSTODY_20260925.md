# R026 歷史原始快照保管事實——有界切片

## 範圍

本切片新增 `HistoricalRawSnapshotCustodyFactsV1`，並將 `MLHistoricalSnapshotProvider.load()`／`MLHistoricalSnapshotReadLease.load()` 已回傳的四組具型別資料列明確投影為 `SnapshotReference`。builder 不讀取 SQLite、檔案系統、sidecar、lease 或模型；不建立 `PreparedMLInput`、不改 live calibration service，也不執行 runtime handoff。

本 custody slice 在 `HistoricalRawSnapshot` 上新增兩項可選不可變事實：既有讀取交易驗證過的四表精確欄位清單，以及同一次呼叫使用的正規化查詢參數。兩欄預設為 `None`，不參與 dataclass equality/repr；不增加查詢、不改變 `source_fingerprint`／`query_count`。一般 inference provenance serializer 選取固定的 raw snapshot 欄位；相鄰 calibration／receipt 測試仍通過。若呼叫端明確使用 `dataclasses.asdict()`，會看見這兩個可選欄位；程式庫內未找到使用該通用投影保存 raw snapshot 的路徑。

後續 live source identity shadow slice 另加入 optional kw-only `provider_contract_id`，預設 `None`、不參與 equality/repr，production `load()` 設為 `twstock-historical-sqlite-four-table.v1`。它是四表 provider 的邏輯契約標籤，不是持久資料修訂或 DB generation；詳見 [R026 live source identity shadow QA](R026_LIVE_SOURCE_IDENTITY_SHADOW_20260925.md)。

證據類別有公開 Python constructors，因此型別外形本身不是任意 synthetic object 來自 SQLite 的密碼學證明。保管語意只適用於同一次 provider／lease 呼叫實際回傳的 snapshot 及其捕獲的查詢範圍。Synthetic 或手工重建的 snapshot 可作測試輸入，但不是經來源驗證的證據。

## 身分與雜湊契約

- Schema version 是 `historical-sqlite-schema.v1:sha256:<digest>`，由 `daily_prices`、`technical_indicators`、`market_indices`、`industry_indices` 經驗證後的有序欄位名稱計算。它描述觀察到的 schema 契約，不是持久 SQLite revision 或 generation。
- `content_hash` 對完整、帶資料表標記的 `key → value` 資料列紀錄計算 domain-separated hash，包含具型別的 `Decimal`／整數／null 編碼；資料列值或鍵變更時會改變。
- `row_identity_hash` 另對帶資料表標記的 row keys 計算 domain-separated hash。只有值變更時維持不變；鍵或資料列集合變更時會改變。
- `snapshot_id` 以 `historical-raw-snapshot-custody.v1` 綁定明示的邏輯 `source_id`、決策／歷史／cutoff 日期、正規化 symbol／industry 選取、同次呼叫的 schema version、資料列數／範圍、`content_hash` 與 `row_identity_hash`。
- Canonical JSON 使用 UTF-8、`ensure_ascii=False`、排序鍵、緊湊分隔符及 `allow_nan=False`。Decimal 值保留精確文字；沒有新增 float 計算或正規化。

空資料列情況沒有 row range；不同的明示空查詢範圍仍會產生不同 snapshot ID。Sidecar 檔案及其 digest 不屬於這些 raw-row hashes 的輸入。

`to_snapshot_reference()` 設定 `source_revision=None`、availability `UNKNOWN`、quality `UNKNOWN`、scope `UNKNOWN`。程式檢查觀察到的 row cutoff 早於決策日期，但這不代表已證明發布者可得時間、持久來源 revision、來源完整性或一般 PIT 保證。此 reference 不是完整的 prepared runtime input。

## 未來資料與範圍檢查

既有 provider 選取嚴格早於 `decision_date` 的前一個 `daily_prices` 日期；四個資料列查詢限定於請求的 history start 至該 cutoff。新 builder 再檢查每筆回傳 observation 位於該區間內且早於決策日期。它不讀取或引入未來價格、forward labels、衍生 feature normalization 或模型輸出。這是對回傳資料列的結構性 cutoff 檢查，不代表底層來源在當時已對使用者可得。

## 測試與靜態檢查收據

Test-first 初次收集因 custody module 尚未建立而以 `ModuleNotFoundError` 停止。`C:\r26raw_final_dd75cc` 是較早的 88 passed run，不能當成最終收據。最終 root fresh short TEMP route 使用 `PROFILE=test` 並隔離 `TEMP`／`TMP`、`DATA_ROOT`、`OUTPUT_ROOT`；其 log 位於 `C:\r26raw_end_5c6445\pytest.log`：

```powershell
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_historical_raw_snapshot_custody.py `
  tests/test_ml_historical_snapshot_provider.py `
  tests/test_ml_historical_feature_builder.py `
  tests/test_ml_historical_feature_computation.py `
  tests/test_prepared_ml_input_contract.py `
  tests/test_r026_sqlite_read_lease.py `
  tests/test_r026_calibration_legacy_preparation_baseline.py `
  tests/test_recommendation_service_calibration_integration.py `
  -q -o addopts=
```

結果：**90 passed／13.10 秒**。Log SHA-256：`D2A49FA2374F6882D743F14BC72F9FD692CB2B58A8CE437C631B6C787F2FE3A5`。

另一次較早的執行記錄為 86 passed／1 failed，失敗測試是 `test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation`，錯誤為 `projection_receipt_not_persisted_fail_closed`；原始 log／實際路徑未保存，因此根因未確診，不計為通過或最終收據。R015 獨立複核曾重現 287 字元 receipt path 的 `WinError 3` 同型路徑失敗，而 251 字元短路徑通過；這是環境路徑診斷，不能證明它就是未保存的 86P／1F 根因。R015 另對最終 frozen source/test 以 fresh TEMP 重跑八檔 route，**90 passed／13.07 秒**，log `C:\r26q\review_raw_20530f90\pytest.log`，SHA-256 `D90BC11D24567A98FB180F46A64B67AFFC92CD4529543C20FCB6291C4C163A62`。

Scoped mypy 命令：

```powershell
.\.venv\Scripts\python.exe -m mypy `
  data_module/ml_historical_snapshot_provider.py `
  app_module/recommendation/historical_snapshot_custody.py `
  tests/test_r026_historical_raw_snapshot_custody.py
```

結果：**3 個檔案、0 個問題**。相同三個檔案的 `py_compile` 通過。`scripts/quant_guard_linter.py` 的 financial-float boundary check 與 repository look-ahead check 均通過。Targeted `git diff --check` 通過。測試 inventory 僅將此測試檔登錄一次為 `service-oracle-recommendation`；這項 membership check 不是完整 inventory guard 結果。R015 獨立複核的 scoped mypy 同為 **3 個檔案、0 個問題**，`py_compile` 及 guard 亦通過。

## 凍結檔案與目前界線

- `data_module/ml_historical_snapshot_provider.py` SHA-256 `CCF2FA00EB3A41E319FC67CFF3B64F12A5222D607A3E6FC0E982F28B262017E4`
- `app_module/recommendation/historical_snapshot_custody.py` SHA-256 `A1F9DEB3015AE878090BA9DC7C3252C1CC674D9BE1160E52265668356310E5C0`
- `tests/test_r026_historical_raw_snapshot_custody.py` SHA-256 `E0B802A666BAB4A12FFD80583301D99B8C6E2DF8ACC2BB41E2C817CB330109FC`
- `qa/full_app_healthcheck/test_inventory.py` SHA-256 `051A263C2CB4CEEA0E453D794C8302D3A1A6A5B9D1DC5EAE0BBDA6E2409617A2`

本切片提供有界 typed-custody facts。它不會將 raw rows 綁定至持久 SQLite generation、sidecar aggregate、model artifact、candidate set、feature-row lineage、receipt 或來源可得性。沒有新增 live service wiring 或 `PreparedMLRuntimeInputV1` handoff。R026 維持 `IN_PROGRESS`；`TMP-ML-01` 維持 `ACTIVE`。
