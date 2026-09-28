# WP2 產業指數 Current-only Provenance 切片

日期：2026-09-28。此文件記錄 IndustryMapper 產業指數來源的 bounded engineering slice，不代表官方歷史可得時間、歷史 PIT 或市場資料更新驗收。

## 結果與邊界

`IndustryMapperDataProvider` 現在會為 SQLite 優先讀取或 CSV fallback 讀取的 `industry_indices` frame 附上 `industry_index_source_observation`。觀測包含實際傳入 mapper 的欄位、列數、日期範圍、排序後未重排的 rowset hash、來源儲存類型與定位資訊。CSV 另記同一次讀取並解析的原始 bytes 大小與 SHA-256；SQLite 只記查詢結果 rowset 身分，不宣稱是整個 DB 檔案的 hash。

兩種來源都固定為 `status=unknown`、`pit_eligible=false`、`available_at=null`、`published_at=null`。`observed_at` 是本機讀取時間；`observation_sha256` 綁定這次觀測封套，因此不同讀取可不同。穩定的列內容身份是 `rowset_sha256`，CSV 原始檔 bytes 身分則是 `stored_artifact_sha256`。兩者都不是官方簽章或來源 authority 證明。

只有 `RecommendationService._record_current_industry_mapping_use` 記錄 `current_industry_index_performance_for_reason` 時，才把 observation 複製進同次既有 `company_registry_source_snapshot`，並核對封套與實際 mapper DataFrame 的欄位、列數、日期範圍及 rowset hash。缺失或不吻合時保留 `unknown`、空 observation 與明確 warning。事件原有 snapshot hash/readback 驗證仍負責封存；沒有新增 UI、PIT 或歷史資料讀取路徑。

日期欄按 `YYYYMMDD`／ISO 日期解析；SQLite 整數日期不會交由 pandas 當成 epoch nanoseconds。rowset hash 保留列順序及 JSON scalar 型別差異。既有 SQLite-first、CSV fallback、missing／empty 與錯誤降級行為未變；六欄 CSV wire format、update writer、DB schema、歷史 cutoff 路徑均未變。

## 上游時間與仍缺的來源契約

`data_module/data_loader.py::DataLoader.update_industry_index` 會向 TWSE `MI_INDEX` 端點請求資料並解析 JSON，再更新既有產業指數 CSV；目前它沒有把原始 response bytes/hash、最終 response URL 或 source-specific capture completion time 一同持久化。SQLite 同步由既有資料更新流程負責，也沒有在這個切片中增加 source receipt。因此 provider 不能證明某列何時由官方發布或何時可供決策。

`scripts/scheduled/data_freshness_probe.py` 對 SQLite source status 使用 quick-update receipt clock，並明列 `source_publish_or_fetch_receipt_not_recorded` 一類 time provenance。該 quick receipt 不是 `industry_indices` 原始 response 的 source-specific capture receipt；此切片不讀它，也不把它轉成 `available_at`。`companies.csv` 的既有 registry sidecar只描述公司分類來源，不能替產業指數背書。

所以此 payload 只可說明「本次 current mapper 實際看見哪些列及其內容身份」。它不得供歷史 recommendation/PIT membership、回測或 personal model 的時間資格使用。要提升為 source-time contract，後續 writer 必須在同一官方 response 寫入流程保存實際 endpoint、request date/type、response bytes hash 與 aware UTC capture 完成時間，並將 receipt 原子地綁到所寫列；本切片沒有改動該 writer。

## 檔案與驗證

本次只修改兩個 production source 與兩個既有 test files，另新增本文件：

- `data_module/industry_mapper_data_provider.py`
- `app_module/recommendation_service.py`
- `tests/test_industry_mapper_provider.py`
- `tests/test_recommendation_personal_use_policy.py`
- `docs/06_qa/WP2_INDUSTRY_INDEX_CURRENT_PROVENANCE_20260928.md`

四個程式／測試檔在變更前已備份於 ignored `output/qa/personal_daily_product_20261006/industry_index_current_provenance_20260928/before/`；before manifest SHA-256 為 `9990a9beee726cdd39c18a2a131e867d61f1f122946d354a5d4e56a0b6e5a694`。變更前／目前 SHA-256：

| 檔案 | Before | Current |
|---|---|---|
| `data_module/industry_mapper_data_provider.py` | `f88cfd7ffd7a28e978b259b2c4772fec228f8a9e6989c0c2fd6ba52ec92305f3` | `c3fe1cc49c3d5e198b85863b53ba5c9f93c4878d8537b915f06215365b303092` |
| `app_module/recommendation_service.py` | `95b958d96c7561e5f966c8ea57226204b3dc1f93aa0a4f3b0c81103e0700a512` | `f3b80bf84b51f15a2962fd954ce2b1358ce4537dbaf0ee508c6da26aa849570b` |
| `tests/test_industry_mapper_provider.py` | `da6f00b466ba054b0e118e596cbfc51cb904e441f9c3f07239c5191498018ce4` | `4f0fc3747ba955bbd17a3d590adaa316b4153fe7f5a8ad504be6a15dad81f9fe` |
| `tests/test_recommendation_personal_use_policy.py` | `911a99ae358818d8047745f7294156d6c5740236544fbc91958ad74e7b42334a` | `adae831b534aefe12e6ef24b51a50633f1aa41a23e5702df48226f4888002fb8` |

focused 驗證使用臨時 CSV、fake SQLite reader 與隔離 pytest basetemp，未讀取或寫入正式 `D:` 資料，也未執行 updater／scheduler：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m pytest tests/test_industry_mapper_provider.py tests/test_recommendation_personal_use_policy.py -q -o addopts= --basetemp .tmp_wp2idx04
.\.venv\Scripts\python.exe -m mypy data_module/industry_mapper_data_provider.py app_module/recommendation_service.py
.\.venv\Scripts\python.exe -m py_compile data_module/industry_mapper_data_provider.py app_module/recommendation_service.py tests/test_industry_mapper_provider.py tests/test_recommendation_personal_use_policy.py
git diff --check
```

結果：44 passed、1 pytest cache write warning（sandbox 權限，不影響測試結果）；mypy 2 files 無錯；四檔 py_compile exit 0；`git diff --check` exit 0。完整 stdout 與 exit files 保存在 `output/qa/personal_daily_product_20261006/industry_index_current_provenance_20260928/`。測試驗證 SQLite／CSV 共用 observation shape、實際 frame rowset/hash 綁定、整數日期、row order／int-float 型別區別、CSV 改變後 content hashes 改變、missing／empty 語意、Service event readback、detached snapshot 與 metadata mismatch fail-closed。

此 slice 尚未有官方 response receipt、source publication time、PIT eligibility、正式 updater run、UI 呈現或整體 WP2 接受證據；不要把這些 bounded checks 擴寫成產業資料已具歷史來源證明。

## 2026-09-28 事件封存邊界附記

在 `execute.py::_capture_events` 增加 current-index-use 的 nested observation/echo 一致性檢查。只有用途包含 `current_industry_index_performance_for_reason` 且 snapshot 至少帶一個新 observation 欄位時，才要求新欄位完整，並驗證 observation 封套 hash、外層 echo、`unknown` 狀態、空的 available/published 時間，以及 capture-time-unknown warning。若 observation 缺失，必須同時沒有 inner hash，且有具名 missing/mismatch/not-JSON warning。舊 context 若完全沒有這組新欄位，仍走既有相容路徑。

新增負例會在竄改 inner observation 後重算 inner hash、outer echo 與 outer snapshot hash；事件仍因時間/狀態矛盾而拒絕。另有 canonical execution save、fresh query readback 的正例，確認事件保存的是同一 observation。這些 hash 是一致性封套，不是不可偽造的來源證明；若呼叫者移除整組新欄位，這個相容性檢查本身不能辨識該刪除。Service 在建立 current snapshot 時對實際 mapper frame 的 rowset 驗證仍是另一個保護層。此附記不提供官方來源時間、歷史 PIT、更新 writer 或正式資料驗收。

此附記新增範圍為 `app_module/recommendation/execute.py` 與既有 `tests/test_recommendation_personal_use_policy.py`；原始四檔 freeze/收據保持歷史，不覆寫。此次在隔離 `PROFILE=test`、DATA_ROOT/OUTPUT_ROOT 與 pytest basetemp 下，執行該測試檔及 `tests/test_industry_mapper_performance_cache.py`、`tests/test_recommendation_calibration_source_contract.py`，結果為 42 passed；另對 execute.py 執行 targeted mypy、對兩個修改程式檔執行 py_compile，並執行 `git diff --check`，均 exit 0。pytest 有一項 sandbox 無法寫 `.pytest_cache` 的 warning。驗證命令、環境、逐項 exit、before/current hashes 與輸出 log 收在 `output/qa/personal_daily_product_20261006/wp2_nested_observation_echo_20260928/followup_receipt.json`；首輪測試曾因測試把 frozen `mappingproxy` 當 `dict` 而失敗，已只修正測試解凍比較後由後續通過結果覆蓋，保留在收據作歷史診斷。
