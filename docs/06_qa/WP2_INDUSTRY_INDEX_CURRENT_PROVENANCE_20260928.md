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

## 2026-09-28 TWSE industry capture / date-scoped projection follow-up

此 follow-up 修改 `data_module/data_loader.py::DataLoader.update_industry_index`、新增 `data_module/twse_industry_index_capture.py`、修改 `scripts/batch_update_market_and_industry_index.py` 與 `app_module/update_service.py`，並更新 `tests/test_data_loader_industry_index_update.py`、新增 `tests/test_twse_industry_index_capture.py`。它保留六欄 CSV 與既有 SQLite table/schema，不新增 DDL；同日所有舊列會由驗證過的 response rowset 整日取代，不再 carry-forward 舊列。解析或 completeness 不明時，僅保留 degraded source capture，CSV 與 SQLite 不變。

Capture receipt create-only 保存 raw response bytes/hash、requested/final URL、request parameters、HTTP metadata、selected table titles、解析後 exact six-column rowset/hash 與 aware UTC local body-read completion time。它固定記錄 official `available_at`／`published_at` 為 unknown/null、`historical_pit_eligible=false`。scope 僅是 TWSE `MI_INDEX type=IND` 回應中通過 table-title 與名稱篩選的 rows；不推論上市／上櫃 venue、成分股或個股 membership，也不默認代表 TPEx／興櫃。Parser 要求 payload/title 有可核對日期，且所有明示日期與 request date 一致；缺失為 `date_unverified`，跨日或錯誤日期 rejected。名稱集合相較最近嚴格較早 CSV 日期有變化時保留 degraded，人工確認前不投影，因目前來源資料沒有合法停用／改名 completeness 契約。

CSV 使用同目錄 temporary file、flush/fsync、六欄/date rowset 暫存 readback 後才 atomic replace。SQLite path 只接受 capture 所列日期，先確認既有六欄 schema、不要求不存在的 PK，也不呼叫 `ensure_columns`；transaction 內 exact readback、commit 後新連線獨立 readback。寫 marker 前會再以同一份 raw CSV bytes 驗證整檔 SHA-256 與 capture 日期 exact rowset；不符時不建 marker，並依 before-image/CAS 條件補償。CSV 若在此次最終 readback之後、marker create之前再被其他程序改寫，仍存在未由 OS 級共用鎖封閉的競態窗口，因此本流程不宣稱跨程序全原子；後續 verified-skip 會重新比對 marker 綁定的 CSV hash、CSV 日期 rowset 與 SQLite rowset，不一致時不接受 marker。Marker 寫入失敗時會比對當前 SQLite rowset/hash 後嘗試還原本次日期 before-image，CSV 也只在目前 bytes 仍等於本次 projection 時還原；無法證明安全補償時回傳 `partial`，不建立 complete marker。Capture receipt、raw response 與 projection marker 的 writer/readback 都檢查 OUTPUT_ROOT 內的父層 reparse-point/symlink containment。`update_industry` 起點先封鎖 legacy whole-CSV fallback；成功 no-capture no-op（例如官方無交易日或目前 projection marker 確認的日期）會 skip，失敗且無 capture 保持 failed。批次日期僅在 projection marker、capture receipts 與目前 CSV／SQLite scoped rowsets 全部吻合時才 verified skip；沒有任何 capture artifact／marker 的前契約 CSV 日期保留為 `unknown_legacy_rows_skipped`，不宣稱本輪已更新，且 legacy-only no-capture 批次回傳 `success=false`，避免 scheduled `_run_step` 把 unknown 標為 passed；有 degraded／未完成 capture artifact 而缺少有效 marker 的日期保持待重試。歷史 rows 不會因此取得 source receipt 或 PIT。

相容性附記：root 於 2026-09-28 對正式 `D:\Min\Python\Project\FA_Data\meta_data\industry_index.csv` 與 SQLite 只讀檢視，CSV 六欄與 `CSV_COLUMNS` 相同；資料庫 `industry_indices` 六欄依序為 `日期 TEXT`、`指數名稱 TEXT`、`收盤指數 REAL`、`漲跌 TEXT`、`漲跌點數 REAL`、`漲跌百分比 REAL`，全部無 primary key。CSV 最近五日（2026-09-18、09-21、09-22、09-23、09-24）各有 75 列／75 個唯一名稱。正式資料只作唯讀相容性觀察，沒有 updater 或 writer；QA 使用同形 no-PK 隔離 DB 驗證，不藉此宣稱官方 `type=IND` wire contract 已驗。

下游 read-only code review 確認 `IndustryMapperDataProvider` 的 `industry_index_source_observation` 仍只封存 mapper 實際載入的 current rowset/storage observation；它不讀取本 follow-up 的 capture receipt 或 projection commit marker，也沒有帶出 `capture_id`／source receipt version／`captured_at`。此實作只補上 upstream capture 與 writer projection evidence，不代表 `market→industry→stock` 下游 consumer 已連到該 evidence；official `available_at`、`published_at` 仍 unknown，PIT eligibility false。跨 RecommendationService/UI 的 consumer 接線留待另行協調與驗收。

本次只用 fake HTTP 與 pytest 隔離的臨時 CSV／SQLite；未呼叫真實 TWSE endpoint、正式 updater／scheduler，未讀取或寫入正式 `D:` DB。Repository 內目前沒有可確認為 `MI_INDEX type=IND` 的 raw fixture，所以 parser 的日期欄位／title wire contract、回應版本差異與 endpoint completeness 仍屬未驗；`MI_INDEX` 的 `ALLBUT0999` raw/title 範例只說明 response date 可能與 request date 不同，不作為 IND contract 證據。這些結果是 bounded implementation QA，不代表 WP2 上游來源已完成 acceptance、資料已正式重建或具備歷史 PIT。

焦點驗證：`tests/test_data_loader_industry_index_update.py` 與 `tests/test_twse_industry_index_capture.py` 共 24 passed、1 skipped（本機 Windows 環境不允許建立目錄 symlink，實體 symlink-parent writer 負例因此跳過；reparse-point receipt-parent 負例以注入 reparse guard 覆蓋）；執行 pytest 時停用 cache provider，未產生 cache warning。`mypy data_module/twse_industry_index_capture.py app_module/update_service.py scripts/batch_update_market_and_industry_index.py` 0 errors；六個本 follow-up Python source/test files 通過 `py_compile`。測試覆蓋民國／Gregorian 日期、日期缺失／跨日／無效值拒絕、前日與同日名稱集合變更 fail-closed、raw path escape 拒絕、reparse-point parent guard、原始 bytes/hash、同日列精確替換、no-PK 六欄 QA schema、date-scoped SQLite success/readback、partial batch caller 與 final marker 狀態、zero-capture failure 封鎖 legacy CSV sync、verified marker current readback、verified／legacy／degraded 三種 batch skip/retry 行為、legacy-only 到 scheduled `_run_step` 的 failed status、marker 前 CSV bytes/hash 與 exact rowset 並發改寫拒絕，以及 final marker 故障補償前後整個 QA DB schema/rowsets 與 CSV bytes 相同。正式 `type=IND` endpoint wire shape 仍未驗；capture-to-provider consumer 接線、WP3/UI 與 overall WP2 acceptance 未驗。

## 2026-09-28 batch exception-after-capture caller regression

跨 WP2/WP1 caller regression 使用隔離的真 `UpdateService` 與 scheduled quick runner：batch entrypoint 在已持久化 capture receipt、完成 CSV 投影並 append manifest 後拋例外時，UpdateService 仍回傳可驗證的 manifests 與 receipt source dates，保留 `success=false`、`partial=true`、`failure_date_unknown=true`、請求範圍及 `partial_reason`；`failed_dates` 只列能證明的日期，未知時為空。Runner 依 manifests 對成功日期做 scoped SQLite sync，projection marker 標為 `batch_scope_status=partial`，runner terminal 仍 failed 且 exit code 1。Marker只證明已捕獲日期的投影 readback；空 `failed_dates` 不代表整批無失敗，未知原因與範圍保留於同次 terminal/result。零 capture 例外回 `partial=false`／空 manifests，不觸發 scoped 或 legacy SQLite sync，同樣保留 failed terminal。

本回歸不涵蓋現有 `DataLoader.update_industry_index` 的窄寫入窗口：目前日期 CSV atomic replace 之後才 append capture manifest；若程序恰於 replace 與 append 間中止，CSV 可能已變而 runner 尚無 manifest 可做 scoped sync。此 owner slice 未改 DataLoader；整體流程不宣稱 CSV/SQLite/manifest 跨程序全原子，該窗口仍需另行處理或由 writer lock／恢復檢查封閉。

驗證命令 `pytest tests/test_scheduled_data_update_runner.py tests/test_twse_industry_index_capture.py tests/test_data_loader_industry_index_update.py` 在隔離 basetemp 下為 46 passed、1 skipped；另 `mypy app_module/update_service.py`、UpdateService 與兩個直接測試檔 `py_compile` 通過。正式 endpoint、updater 與 D 資料未觸碰。

## 2026-09-28 CSV replace 後 receipt manifest 登記前的 restart recovery

既有 DataLoader 順序仍是：先 create-only 保存 raw response 與完整 capture receipt，接受 completeness 後以同目錄 temp file 驗證並 atomic-replace 六欄 CSV，最後才把 receipt path append 到本次記憶體 manifest sink。若程序在 replace 與 append 之間硬中止，下一次同範圍 batch 可從持久化 receipt 找回這次投影；本修補不改 DataLoader 寫入順序，也不將它宣稱為 CSV／SQLite／manifest 全鏈原子交易。

復原只針對本次交易日範圍中，CSV 已有列、存在既有 capture attempt artifact、尚無目前 verified projection marker 的日期；需由呼叫者提供 manifest sink。Scanner 固定在 `OUTPUT_ROOT/industry_capture/twse/<source-date>/` 內，不遞迴或跟隨 symlink／junction，並限每批 64 個日期、每日期 64 個 raw-hash 子目錄、每個 observations 目錄 8 個項目；每個 raw response 上限 16 MiB、receipt 上限 32 MiB、每次 recovery receipt 總讀取量上限 64 MiB、raw bytes 總讀取量上限 128 MiB、CSV 上限 64 MiB。正式 `industry_index.csv` 唯讀觀測約 11.6 MB，低於 64 MiB cap；超出任一單檔或總量上限均 fail closed。目錄列舉採 max+1 方式遇界限即停止，再只排序界限內項目；讀取前先 stat 檢查 bytes 上限，recovery scanner 會重用同一次已驗 receipt/raw snapshot，不在 scanner 內重讀 raw response。之後 UpdateService 的 scoped sync 仍獨立重新驗證傳入 receipts，因此 recovered receipt/raw 快照跨 scanner 與 sync 兩階段最多各讀一次：對 recovered subset 的總量上界分別為 128 MiB raw 與 64 MiB receipt；同一 run 若另有新抓日期，這些 capture 不包含在 recovery scanner 的總量上界內，但仍受每個 response/receipt 單檔 cap 限制。目錄結構異常或 reparse-point 也 fail closed，要求縮小日期範圍或人工檢視。它會驗證 receipt 檔名身份、receipt 內容 hash、raw bytes 名稱／大小／hash、TWSE type=IND contract、raw JSON 解析與 receipt rowset/hash；之後同一份目前 CSV bytes 必須有正確六欄 schema，且該 source date 的完整列集合與 capture rowset exact match。符合時只把 receipt path 加入本次 manifest sink，回報 `recovered_dates`，不重抓 endpoint、不重寫 CSV；既有 UpdateService 隨後仍以 date-scoped SQLite transaction、獨立 readback 與 marker-last 流程完成同步。

日期狀態處理如下：

- 現有 marker 只有在 receipt、CSV 同日 rowset、完整目前 CSV bytes SHA-256（`csv_sha256`）及 SQLite readback 都吻合時，才沿用 `verified_projection_noop` 安全略過。即使只修改其他日期的 CSV 列，整檔 hash 變化也會使 marker stale；若目標日 capture 唯一且同日 rowset仍 exact，batch 可 recovery 後重新 scoped sync 並建立綁定新 CSV hash 的 marker；否則一般 retry/failure。
- marker 缺失但 SQLite 已有同樣列時，唯一匹配 receipt 會進 scoped sync；同步可重寫相同日期列並在獨立 readback 後建立 marker。這是重啟等價測試，不證明 SQLite 曾由先前程序成功 commit。
- 沒有 capture receipt 的前契約 CSV 日期沿用既有 `unknown_legacy_rows_skipped`，不 recovery、不宣稱 fresh update；如果有 receipt artifact 但其 rowset 與目前 CSV 不同，recovery 不匹配，日期回到一般來源 retry；retry 若失敗則整體 failed。
- 單一 tampered receipt、同日多筆 receipts（即使內容 rowset 相同）、reparse-point、異常目錄或超出 scanner 界限都 fail closed；不呼叫日期更新 writer，也不建 projection marker。

已新增 recovery 專項回歸：單一 exact receipt 可跨重啟找回；current CSV rowset mismatch 走 retry；receipt tamper、缺 receipt、同日雙 receipt、reparse parent 與日期界限 fail closed；marker 缺失且 QA SQLite 已含同列時，真 `UpdateService` 經 scheduled `_run_step` 將 recovered manifest 做 scoped sync，產生可重新驗證的 projection marker。另以修改非目標日期列驗證整檔 `csv_sha256` 使舊 marker stale，batch 只在目標日 receipt 與列吻合時恢復並重建 marker；receipt／CSV byte cap 也有負例。測試只用 fake HTTP fixture、隔離 CSV／no-PK SQLite 與臨時 OUTPUT_ROOT，未呼叫真 TWSE endpoint、正式 updater／scheduler job，也未讀寫正式 `D:` 資料。`captured_at` 仍僅是本機 aware UTC capture 時鐘；`available_at`／`published_at` unknown，`historical_pit_eligible=false`。CSV scan 與 SQLite sync 間、以及成功 readback 與 marker create 間仍沒有跨程序 OS 級共用鎖；directory check/open 也保留明確 TOCTOU 限制；整體只提供可恢復與 fail-closed 行為，不宣稱完整 crash-atomic。

其餘三項 P2 限制是可用性與並發讀取界線：recovery 對每個候選日期都可能重讀並解析整份 CSV，因此在 64 個日期、每份達 64 MiB 的最壞情況，單次 recovery 最多約讀取／解析 4 GiB CSV；既有 projection marker tree 的 prefix／JSON 列舉沒有總 entry 數或總 byte cap，極大 marker tree 可能增加掃描時間與資源使用；receipt、raw response、CSV 的 `stat` 與 `read_bytes` 不是同一個原子操作，若檔案在兩者之間並發長大，可能先配置超過 stat 所見大小的 buffer，之後才因長度／上限不符拒絕。這些情形記錄為可用性／TOCTOU 限制；現有驗證仍以實際讀取 bytes、rowset 與 marker hash 作判斷，不據此宣稱已觀察到 false-fresh、資料破壞或資料遺失，也不把整個 marker discovery／recovery 流程描述為全程有界。

最終 focused 驗證命令 `pytest tests/test_twse_industry_index_capture.py tests/test_data_loader_industry_index_update.py tests/test_scheduled_data_update_runner.py -q -o addopts= -p no:cacheprovider`（隔離 basetemp）結果為 57 passed、1 skipped；targeted mypy 對 capture helper、UpdateService 與 batch runner 為 0 errors；helper、UpdateService、batch runner 與直接測試檔均通過 `py_compile`；`git diff --check` 無 whitespace error。唯一 skip 是既有 Windows symlink 實體建立限制測試。

## 2026-09-28 PROFILE=test raw-path escape 負控修正

`test_capture_receipt_rejects_raw_path_escape_even_with_rehashed_receipt` 現以同一個 `TWStockConfig.output_root` 產生並驗證 manifest，避免 `PROFILE=test` 將 output root 自動改為 `tmp_path/output/_test` 後，測試卻誤傳 `tmp_path/output`。測試也在竄改 `raw_response_file` 並重算 receipt content hash 後，重算 receipt byte digest 並將檔案放到符合 digest 命名的 observations 路徑；因此 verifier 先通過檔名／內容身份檢查，再依原 oracle 拒絕 `../outside.bin` 固定 raw filename。這是測試 fixture/setup 修正，production guard 與拒絕條件未變。

隔離環境驗證 raw-path escape 負控：未設定 `PROFILE` 為 1 passed；`PROFILE=test` 且 `DATA_ROOT`／`OUTPUT_ROOT` 指向隔離路徑為 1 passed。完整 WP2 group（`test_industry_mapper_provider.py`、`test_recommendation_personal_use_policy.py`、`test_industry_mapper_performance_cache.py`、`test_recommendation_calibration_source_contract.py`、`test_data_loader_industry_index_update.py`、`test_twse_industry_index_capture.py`、`test_scheduled_data_update_runner.py`）在兩種環境均為 113 passed、1 skipped；skip 是 Windows 不支援實體 symlink 的既有測試。pytest 使用獨立 basetemp，未讀寫正式資料。
