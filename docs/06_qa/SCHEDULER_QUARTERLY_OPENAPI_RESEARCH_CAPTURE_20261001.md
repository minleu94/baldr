# TWSE／TPEx 季度 OpenAPI 研究觀測器 QA（2026-10-01）

## 結論與界線

新增的季度觀測器為固定 scope 的研究收集工具：每次先取得兩份官方 OpenAPI catalog，驗證 host、目標路由、response schema ref 與 24 個 target schema fingerprint；兩份都通過後，才依固定次序各 GET 一次 TWSE／TPEx 的 income 與 balance 六類 endpoint。任何 catalog contract drift 都在數值請求前 fail closed。每個 run 有獨立 create-only 目錄，保存實際 entity bytes、request receipt、preview、run summary 與最後 readback terminal。

已保存季度原始觀測與可解析 preview；這不等同正式完整數值 dataset 或來源採納，發行人母體、完整 row coverage、單位接受與歷史 availability 均未證明。全路由嘗試旗標與全市場 issuer coverage 是不同旗標；`issuer_identity_verified`、`issuer_coverage_complete`、`full_market_coverage_verified`、`historical_pit_eligible`、`formal_credit`、`training_eligible` 與資料庫寫入均維持 false。第一版不建立 canonical dataset，也不呼叫 MOPS T164 小樣本路徑。weekly wrapper 現已在 core 成功後獨立執行財報公告 availability 與季度觀測兩個 research child；`BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0` 與 `BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH=0` 可分別停用，child 失敗不改寫原 core exit，季度 child 仍會在財報公告 child 停用或失敗後執行。

執行 CLI 不帶參數或帶 `--preview` 時只列出固定計畫：不建立 HTTP session、不發 GET、不建立 output root。只有明確提供 `--capture` 才開始 26-request capture。CLI 沒有可覆寫 URL、category、date、clock、timeout、retry、output root 或 request range 的選項。2026-10-01 台北時間 07:41:42–07:42:57 已經 root 核准，完成唯一一次實際 26-request research capture；一般 sandbox 的首輪 WinError 10013 與其 receipts 亦保留，後續相同命令只做一次 purpose-specific escalation。Escalated capture 的 collector readback 已完成，但 CLI 結尾輸出遇到 Windows `cp1252` UnicodeEncodeError，故 outer return code 為 1；實際 raw／summary／terminal 都已落盤且可離線獨立重驗。已將 CLI JSON 輸出改為 ASCII-escaped JSON，解析後原中文文字不變；cp1252 regression 以 mock 驗證，沒有重跑 live HTTP。

## 固定來源與 catalog contract

執行時每次重新取得 catalog，不會讀取 QA seed 檔作為 runtime 輸入。成功實際 response 中，TWSE 傳回 `Content-Encoding: gzip`，custody 保存的是 32,941 encoded entity bytes（SHA-256 `6ead11673a2776cd7c9e82be46196b6c477f874073bf38c9604f271f15d91bfa`），解析後為 309,960 decoded bytes；設計 seed 是 decoded body（SHA-256 `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0`）。此 bytes 差異來自 gzip 傳輸編碼，不是 catalog schema drift：

| 官方 catalog | 已保存的設計參考原件 | 已知 body SHA-256 | 本輪本機 readback |
|---|---|---|---|
| [TWSE Swagger](https://openapi.twse.com.tw/v1/swagger.json) | `output/qa/twse_openapi_catalog_metadata_20261001_run02/response_body.raw` | `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0` | 309,960 decoded bytes；12/12 target routes fingerprint 通過 |
| [TPEx OpenAPI](https://www.tpex.org.tw/openapi/swagger.json) | `output/qa/tpex_openapi_catalog_metadata_20261001_run02/response_body.raw` | `05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e` | 476,923 bytes；12/12 target routes fingerprint 通過 |

兩份 seed 均只供開發時校驗 target fingerprint。TWSE 是 Swagger 2.0、host `openapi.twse.com.tw`、base path `/v1`；TPEx 是 OAS 3.0、server `https://www.tpex.org.tw/openapi/v1`。兩者目標 response schema 都宣告為 string-property object、沒有 required fields、沒有 query parameter；這些 metadata 本身不證明 runtime numeric response 外層格式或 issuer coverage。TPEx balance `ins`、`mim` 路由保留 catalog 實際的 `insA`、`mimA` component refs，未把 route 改抓 sibling A endpoint。

固定 24 個數值 URL 由下列四組和六個允許 suffix 組成，collector 內存完整 URL allowlist，不接受執行時擴張：

| Market／venue | 綜合損益表 | 資產負債表 | 六個允許 suffix |
|---|---|---|---|
| TWSE／上市 | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_{code}` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_{code}` | `basi`、`bd`、`ci`、`fh`、`ins`、`mim` |
| TPEx／上櫃 | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_{code}` | `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_{code}` | `basi`、`bd`、`ci`、`fh`、`ins`、`mim` |

以上 `basi` 金融業、`bd` 證券期貨業、`ci` 一般業、`fh` 金控業、`ins` 保險業、`mim` 異業。第一版不納入 TPEx `_A` income siblings、公開發行／興櫃市場、現金流量表或權益變動表；本次 catalog 未證實後兩者存在於這組報表路由。

## 首次實際觀測結果（research-only）

隔離的成功 outer capture receipt：`output/qa/quarterly_openapi_live_capture_20261001_d363e2f900c24c8aa09024dea7069e73/`；其開始／完成 UTC 為 `2026-09-30T23:41:41.8688758Z`／`2026-09-30T23:42:57.6952643Z`，CLI return code 為 1，`outer_receipt.json` SHA-256 為 `218b54a2e64d389e76d3320c57b96c31864969e31132d1cfc6be48671cfc9585`。預設 sandbox 的 WinError 10013 attempt 位於 `output/qa/quarterly_openapi_live_capture_20261001_43494419d08f4ae58d0fa66b166fbf0a/`；UTC 2026-09-30T23:40:54.0719546Z–23:40:57.0055899Z（台北 07:40:54–07:40:57），outer return code 2，outer receipt SHA-256 為 `20a92aeaada8d54adee0cfe66bb96e6f5434a4f72c54805500149a28ed5851b6`；collector terminal SHA-256 為 `e6e5e2e877015dc049175b5896fce031af62223f4ba14ac1f0f8807e8338ce89`。兩個 catalog request 都因 WinError 10013 失敗，沒有 HTTP status 或 response body，也沒有數值請求。成功 collector run 是 `output/mops_quarterly_openapi_research/quarterly-openapi-20260930T234142052845Z-f0e035f3ff514fa8a022b08567f8e725/`，UTC capture phase 為 `2026-09-30T23:41:42.052845Z`–`23:42:57.118881Z`（台北 10/1 07:41:42–07:42:57）；終端 status `completed_with_review_items`，terminal SHA-256 為 `77a48a8c3a4311fabdfa6b3e0b791a868c402be65675a21dc2558b207c58a33d`。TWSE catalog HTTP 200、32,941 encoded bytes（gzip）、解壓後 309,960 bytes、encoded SHA-256 `6ead11673a2776cd7c9e82be46196b6c477f874073bf38c9604f271f15d91bfa`；解壓 body 與設計 seed 同 SHA-256 `06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0`，所以 byte 長度差是傳輸壓縮，不是 schema drift。TPEx catalog HTTP 200、476,923 bytes、SHA-256 `05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e`。兩份 runtime catalog 均重驗 12/12 target routes；實際 24 個 numeric endpoints 全各取得一份 bounded raw 和 receipt，原件 SHA／bytes 清單在同目錄 `run_summary.json` 的 `artifact_files`，逐筆可讀 `*/receipt.json`。CLI return code 1 只發生在 collector readback 後 cp1252 輸出中文 JSON；原件與 terminal 另由無網路 readback 重驗成功，且 ASCII-safe 修正只在 mock 離線驗證，未重發 HTTP。

全路由取得 3,960 列 raw observation，其中 3,952 列通過目前 key/schema preview；差額 8 列恰為 6 個 TPEx endpoint 各 1 列公司／期別 key 未識別，以及 TPEx balance `ins`、`mim` 各 1 列 schema drift，保留在 raw／review 計數，未輸出 preview。16 個 endpoint 為 `observed_row_array`，6 個 TPEx endpoint 為 `key_review_required`，TPEx balance `ins`、`mim` 各 1 列 `schema_review_required`。分市場結果如下：

| Market／statement | Raw rows | Preview rows | 分類 |
|---|---:|---:|---|
| TWSE income | 1,084 | 1,084 | 6 endpoint 全為 observed；辨識列期別為 2026-Q2 |
| TWSE balance | 1,084 | 1,084 | 6 endpoint 全為 observed；辨識列期別為 2026-Q2 |
| TPEx income | 896 | 892 | 2 endpoint observed；4 endpoint 各 1 列 key review |
| TPEx balance | 896 | 892 | 2 endpoint observed；2 endpoint key review、`ins`／`mim` 各 1 列 schema review |

run terminal 記錄 `completed_with_review_items`，重驗 55 個 artifacts、2 catalogs、26 request receipts、3,960 numeric rows 與 3,952 preview rows；raw 2,806,324 bytes、preview 12,600,942 bytes。兩數差 8 列：6 個 TPEx endpoint 各有 1 列公司／期別 key 未識別，另 2 列 TPEx balance `ins`、`mim` schema 不符合 catalog shape；這 8 列都保留於原始資料與 review 計數，未輸出 preview。另一個無網路、read-only `verify_capture_run` 重驗輸出保存於 outer run 的 `independent_offline_readback.json`，結果相同。觀測窗口為 UTC 2026-09-30 23:41:42.052845–23:42:57.118881（台北 10/1 07:41:42–07:42:57）；各 response observation 完成時間分別保存在 26 份 receipt／endpoint summary。數值列的 `available_at` 仍 null；preview 中 60,136 個一般數值欄位標記為 `unit_unknown`、1,976 個欄名明示 `元/股`、4,372 個欄名明示 `股`。這些 HTTP 200 與路由觀測不證明全市場 issuer coverage、一般金額單位、歷史可得時間或正式數據完整性。`formal_pit_eligible`、`issuer_coverage_complete`、`official_no_data` 均 false。成功 collector 的終端 SHA-256 為 `77a48a8c3a4311fabdfa6b3e0b791a868c402be65675a21dc2558b207c58a33d`；outer receipt SHA-256 為 `218b54a2e64d389e76d3320c57b96c31864969e31132d1cfc6be48671cfc9585`，記錄 post-capture CLI return code 1。失敗 default-sandbox outer attempt 在台北 07:40:54–07:40:57 只留下 WinError 10013，未取得 HTTP status／response body；collector block terminal 與其外層 receipt 均保留。

## 觀測資料、單位與時間

數值回應以嚴格 JSON reader 解析：重複 object key、`NaN`／無限常數、無效 JSON、深層解析失敗都在保存 bounded raw 後拒絕當作有效 payload；JSON 小數以 `Decimal` 載入，沒有 float 換算。列中的任何 null／非字串欄值會標 `schema_review_required` 並不輸出 preview row；多語 identity aliases 衝突標 `identity_review_required`，key／period 不能判定則標 `key_review_required`。這些列會留在 raw、計數及有限診斷樣本內，不會被默默修正。

HTTP 200 且 JSON 為 `[]` 時，狀態是 `observed_empty_list`／`empty_response`，`official_no_data=false`、`full_market_complete=false`；catalog 宣告 object 並沒有定義空 list 的語意。其他非 array payload 會標 schema review。即使 24 個 endpoint 都被嘗試，也不等於公司母體已覆蓋、沒有跨業別重複或資料列完整；目前沒有 issuer denominator binding，也不去重資料列。

Preview 保留來源原始數字字串並另以 `Decimal` 產生文字值。一般金額欄位一律 `unit_unknown`／`unknown_from_catalog`，不乘 1,000，也不宣稱幣別；只有欄名明列的 EPS 使用 `元/股`，股數欄名明列「單位：股」才標 `股`。`available_at` 一律 null，報表日期不會被當作可得日；以 HTTP completion 的實際台北日期判斷尚未到季末的列，仍保留身份與期別觀測，但不輸出該列數值。

HTTP 完成時間是 source observation clock；`research_artifact_materialized_at_utc` 與 `research_artifact_readback_verified_at_utc` 是完整 raw/parser/readback 後研究 run artifact 的時鐘。它們不是 source row 的歷史公告時間或 `available_at`。`candidate_available_at` 繼續為 null，避免把研究檔案完成時間誤讀為歷史資料可得證據。

## Custody 與 request budget

每輪固定最多 26 GET：2 catalog + 24 數值 endpoint；每個 URL 一次、0 retry、不 follow redirect、Requests connect/read timeout 30 秒，請求間隔固定 2 秒。另以 monotonic clock 設每 request 60 秒、整輪 900 秒 elapsed budget；送出 request 前、每次 body read/probe 前後、request 完成後，以及每次 2 秒 pacing 後都會檢查。超限後停止後續 URL，將當次已取得的 bounded prefix、HTTP 狀態與 receipt 保留，terminal 明確標記 `request_elapsed_budget_exceeded` 或 `run_elapsed_budget_exceeded`。`requests` 的 30 秒是每次 connect/read operation timeout，不是整個 request 的上限；若單次阻塞 read 在控制權回來前跨過 elapsed budget，該單次 read 無法被此同步 collector 中斷，receipt 會記錄實際超時時間，並且不再開始下一個 request。因此 900 秒是停止後續網路呼叫的 elapsed gate，不是可保證的程序硬牆鐘終止時間。weekly wrapper 僅在 core collection exit 0 後呼叫此工具；預設啟用，`BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH=0` 可停用。此 research child 的失敗不覆蓋 core exit；`BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0` 或財報公告 availability child 失敗都不會跳過季度 child。

每份 encoded raw entity 最多 8 MiB、decoded JSON 最多 8 MiB、單輪 aggregate saved raw 最多 256 MiB、preview 最多 128 MiB、metadata 合計最多 16 MiB，且每次寫入前保留 16 MiB free-space reserve。到達 8 MiB 時會再讀一個 byte 作為 EOF／超限 probe；該 byte 不保存。若有額外 byte，只留前 8 MiB bounded prefix、標記 truncated／limit reached、不解析或當作成功；若 `Content-Length` 與實際 EOF byte count 不符則 fail closed。所有檔案先檢查目標及祖先路徑，拒絕 symlink、reparse point、hardlink、path escape；以 create-only 寫入並做 open/fstat/path-after identity、size/hash readback。

HTTP entity raw 寫入並 readback 成功後才 decode、parse 或 preview。raw write/readback 失敗保留失敗狀態、原 HTTP status、source hash 與 attempted path；catalog raw custody 失敗不再發第二個 catalog 或數值請求，numeric raw custody 失敗將該 endpoint 標 transport failure 並停止本輪後續 numeric URLs。無法保存的原件不得進入 preview。每輪成功 terminal 前重驗固定 URL／request receipt 序列、raw hashes 與 decode、catalog contracts、numeric rows、所有 preview rows 與 summary counters；只有 readback 驗收完成才寫 terminal status。

## CLI 與測試

安全預覽（已執行，輸出 `network_requests=0`、`files_written=false`）：

```powershell
.\.venv\Scripts\python.exe scripts\capture_mops_quarterly_openapi_research.py
```

唯一一次已核准的 live 命令（已執行；不可因 CLI 輸出錯誤而重送）：

```powershell
.\.venv\Scripts\python.exe scripts\capture_mops_quarterly_openapi_research.py --capture
```

Focused route 使用合成、無真實公司資料的 TWSE／TPEx catalogs 與 mock HTTP session；所有 test request 都由 fake session 回應，沒有 network fallback：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_mops_quarterly_openapi_research_capture.py -q -o addopts= -p no:cacheprovider
```

結果：**30 passed**。路由涵蓋固定 24 targets／26-request plan、完整 mock capture 中的有效非空 row、Decimal/單位與 raw-source readback、`[]` 語意、future-period withholding、schema null/non-string、identity alias conflict、catalog drift 先擋 numeric、catalog/numeric raw custody 失敗阻止後續請求、JSON duplicate key／non-finite／invalid／deep-recursion 原件保留、raw readback failure、EOF cap probe／Content-Length lie、metadata free-space reserve、preview existing file 讀回、oversize read-before-open guard、hardlink reject、CLI preview 零 HTTP／零輸出副作用與 CLI scope override 拒絕、cp1252 console safe JSON rendering。新增 elapsed tests 驗證 60 秒單 request／900 秒 run gate 停止後續 URL、pacing 後重查 deadline、保留當次 prefix/receipt；另驗證 HTTP 404、response URL mismatch、body 完整後才跨 request budget 時原件、decode hash 與 failure status 均能 readback。

| 檢查 | 指令 | 結果與 log |
|---|---|---|
| Focused tests | 上述 pytest 指令 | `30 passed in 6.73s`；`output/qa/quarterly_openapi_research_mock_20261001_run06/pytest.log` |
| Syntax | `.\.venv\Scripts\python.exe -m py_compile data_module\mops_quarterly_openapi_research_capture.py scripts\capture_mops_quarterly_openapi_research.py tests\test_mops_quarterly_openapi_research_capture.py` | exit 0；`output/qa/quarterly_openapi_research_mock_20261001_run06/py_compile.log` |
| Mypy | `.\.venv\Scripts\python.exe -m mypy --config-file mypy.ini --explicit-package-bases data_module\mops_quarterly_openapi_research_capture.py scripts\capture_mops_quarterly_openapi_research.py tests\test_mops_quarterly_openapi_research_capture.py` | `Success: no issues found in 3 source files`；`output/qa/quarterly_openapi_research_mock_20261001_run06/mypy.log` |
| 保存 catalog readback | local parse／validate 兩份 QA seed raw | TWSE 309,960 bytes、12 route；TPEx 476,923 bytes、12 route；`output/qa/quarterly_openapi_research_mock_20261001_run02/catalog_seed_validation_final.log` |
| CLI 預覽 | 上方不帶參數的安全預覽命令 | exit 0，`network_requests=0`、`files_written=false`、maximum request plan 26、request/run elapsed gate 60/900 秒；`output/qa/quarterly_openapi_research_mock_20261001_run06/cli_preview.json` |
| weekly wrapper fake-child route | `.\.venv\Scripts\python.exe -m pytest tests\test_scheduled_mops_statement_custody.py -q -o addopts= -p no:cacheprovider` | Windows 上 `20 passed in 0.76s`；fake Python/children，無 HTTP；`output/qa/quarterly_openapi_weekly_hook_mock_20261001_run02/pytest.log` |
| weekly route syntax | `.\.venv\Scripts\python.exe -m py_compile data_module\mops_quarterly_openapi_research_capture.py scripts\capture_mops_quarterly_openapi_research.py tests\test_mops_quarterly_openapi_research_capture.py tests\test_scheduled_mops_statement_custody.py` | exit 0；`output/qa/quarterly_openapi_weekly_hook_mock_20261001_run02/py_compile.log` |
| Scoped source mypy | 同上季度 source mypy 命令（三個 source／focused test 檔；不含 Windows batch 測試） | `Success: no issues found in 3 source files`；`output/qa/quarterly_openapi_weekly_hook_mock_20261001_run02/mypy_quarterly_scope.log` |

初次直接執行 CLI 曾因缺少 repo-root `sys.path` bootstrap 而在 import 前失敗，沒有建立 HTTP session；失敗 traceback 保存在 `output/qa/quarterly_openapi_research_mock_20261001_run02/cli_preview.json`。已依既有 script 慣例加入唯讀 repo-root path bootstrap，之後的 preview 命令成功，並確認預設 candidate root 未建立。失敗 log 保留，不重造或抹除。

weekly wrapper 接線已完成；控制流回歸使用 fake Python child，沒有觸發 Windows Task 或再發 HTTP；下一次自然 weekly Task 尚未實際驗收。core 非 0 時短路；core 為 0 才依序執行財報公告 availability 與季度兩個獨立 research child。`BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0` 或財報公告 child 失敗都不跳過季度 child；`BALDR_ENABLE_MOPS_QUARTERLY_OPENAPI_RESEARCH=0` 可停用季度 child；所有 research child exit 不覆蓋 core exit／`pending_human_review` 語意。未新增／修改 Windows Task、Manual、snapshot、canonical dataset、正式 DB、D 資料根或 Formal/pointer 檔；未做 apply、訓練或 publisher 執行。即使 26-request capture 與 readback 通過，結果仍只證明 endpoint 觀測，不代表 issuer coverage 完整，也不補足未涵蓋的現金流量表／權益變動表、historical PIT availability 或正式單位契約。

wrapper test 的控制流案例僅在 Windows 執行（非 Windows 會 skip，因為沒有 `cmd.exe`）。wrapper 測試獨立 mypy route 還會跟入既有凍結 helper `tests/test_mops_success_response_custody.py`，在該 helper 第 187、207 行回報兩個 `object` 不可索引診斷；此處不修改 shared helper。季度 source／CLI／focused tests 的 scoped mypy route 獨立通過，不將此結果外推為整個 repo 型別檢查乾淨。