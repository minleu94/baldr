# R026 Excluded Daily-Price Namespace：Slice 5 紅測基線

**日期：** 2026-09-25

**狀態（修補前紅測基線）：** 本節記錄受控修補前的隔離合成測試結果；三項缺口在當時的 production reader 上以預期紅測重現。後續 Slice 5A 已實作並追加至本 QA note 與 R026 報告。`R026` 與 `TMP-ML-01` 維持 open／active。

## 隔離方式與測試路由

使用 Windows、Python 3.11.9、`PROFILE=test`，並把 `DATA_ROOT`、`OUTPUT_ROOT`、pytest `--basetemp` 指向全新短路徑 `C:\t\r26s56c227b`。測試中的資料庫、writer-like receipt、官方 archive、market source manifest 及 junction target 都建立在 pytest `tmp_path`；沒有讀寫正式資料。

執行命令：

```powershell
$env:PROFILE='test'
$env:DATA_ROOT='C:\t\r26s56c227b\data'
$env:OUTPUT_ROOT='C:\t\r26s56c227b\output'
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_excluded_daily_price_namespace_red.py -q -o addopts= --basetemp=C:\t\r26s56c227b
```

結果為 **5 passed、3 failed、0 skipped**。Windows junction 由 `cmd.exe mklink /J` 真正建立，沒有 skip 或以一般目錄替代。新測試 SHA-256：`23CCBDB5DA8C0C9D17B471750AB7E0528C01BC0940CAC0C3D8EBC2E89495BDA6`。

另以第二個 fresh TEMP 執行既有 writer／loader 控制路由：

```powershell
$env:PROFILE='test'
$env:DATA_ROOT='C:\t\r26s58f3797\data'
$env:OUTPUT_ROOT='C:\t\r26s58f3797\output'
.\.venv\Scripts\python.exe -B -m pytest tests/test_excluded_daily_price_revision.py -q -o addopts= --basetemp=C:\t\r26s58f3797
```

結果為 **6 passed**。它確認既有計畫、apply／rollback、pending recovery、PIT cutoff 與來源 tamper oracle 在本切片前仍通過。

## 三個預期紅點與目前觀察

1. `test_dangling_receipt_root_junction_is_not_reported_as_empty`：把固定 receipt root junction 指向 TEMP 目錄後刪除 target，再呼叫舊 `load_exclusion_evidence()`。目前回傳 `[]`，未拒絕失效 root，測試以「失效的 receipt-root junction 被當成 EMPTY 接受：[]」失敗。這直接證明 `Path.exists()`／marker glob 的缺口。

2. `test_external_receipt_root_junction_is_not_reported_as_empty`：固定 receipt root junction 指向資料根目錄外的空 TEMP 目錄。目前仍回傳 `[]`，沒有檢查 resolved root containment，測試以「超出資料根目錄的 receipt-root junction 被當成 EMPTY 接受：[]」失敗。這是外部路徑被誤當成有效空集合的重現。

3. `test_archive_manifest_is_hashed_and_parsed_from_the_same_bytes`：在 archive manifest 第一次 `read_bytes()` 已回傳、hash 尚待驗證後，使用 `os.replace` 原子替換成只改 `archived_at`、保留其他內容的有效 manifest。loader 仍回傳 applied legacy evidence；測試觀測到 hash bytes SHA 為 `4bb07fdaae634fcfada5d40b951bb471fd74445084415defca85e6f7042caf9b`，後續被解析 bytes SHA 為 `da3ba289800f168865e4a39649d4dbf5e43d326b9176c7a504e522e81a62e51f`，因此同 bytes 斷言失敗。這只測 archive manifest 的 hash／parse double-read，不代表其他 16 個 archive files 或 market source manifests 已逐一重現。

## 綠色控制與介面相容

- Writer `prepare()` 留下只有 `plan.json` 和 `before_rows.json` 的 before-start 目錄，舊 loader 回傳 `[]`。
- Applied 控制確認舊 projection 仍是一筆、110 個排序 keys；欄位及插入順序固定為 9 欄：`keys`、`closed_dates`、`plan_sha256`、`receipt_sha256`、`receipt_path`、`acquired_at`、`source_start_date`、`evidence_archive_relative`、`market_plan_sha256`。`load_exclusions()` 和 `load_excluded_dates()` 與 projection 相符。
- Rolled-back 控制經真實 TEMP writer recovery 後，舊 active list 仍為 `[]`。
- Pending 控制注入在 SQLite apply commit 後、receipt 寫入前；舊 loader 以「進行中」拒絕。
- 合成 receipt-root `PermissionError` 在本機 Python 3.11.9 由 `Path.exists()` 傳出，既有路徑沒有把此控制吞成空清單；這不是 junction 缺口的替代測試。

新測試已登錄 `qa/full_app_healthcheck/test_inventory.py`，分類為 `service-oracle-recommendation`；該 inventory SHA-256 為 `92732341F58D298F5D3C40901E3BA73DF6CA0506DE15EB2B797F397D14D57B03`。Inventory guard 的其餘 6 項通過；全庫 audit 仍因 shared tree 108 個未登錄路徑失敗，新檔不在 missing list：filesystem 1005、registry 897、missing 108、stale 0、collection errors 0。沒有清理本輪以外的 registry 缺漏。

`py_compile` 與新測試檔 scoped mypy 均通過；mypy 為 1 source file、0 issues。此紅測切片沒有修復或驗收 R026；typed namespace evidence、各檔 bytes identity、rollback typed presence 與完整 fail-closed collector 仍待實作及獨立 review。

## Slice 5A：有界 scanner 與 archive manifest 單次解析

**狀態：** 這是同一測試切片的受控修正。固定 receipt root 與 run 掃描現在逐段 `lstat`、strict-resolve、檢查資料根／receipt-root containment，並完整 materialize `scandir` 結果；掃描或列舉錯誤 fail closed。只有 receipt root 的普通路徑元件真正不存在、完整掃描沒有 active marker、合法 writer prepare-only 形狀，或驗證後全為 rolled-back marker 時，舊 active list 才回傳空。prepare-only 形狀固定為一般檔案 `before_rows.json` 與 `plan.json`；journal-only 等無 marker partial run 會拒絕。既有 nested `formal_market` 子樹在本層只作安全解析後保留，不把巢狀 marker 誤作排除修訂。

紅測階段先以凍結的原始檔 SHA `23CCBDB5DA8C0C9D17B471750AB7E0528C01BC0940CAC0C3D8EBC2E89495BDA6` 在 fresh short TEMP 重現 5 passed／3 failed。其後新增 missing-root、journal-only partial、dangling run-junction 與 scandir-error cases；scanner 修正前的擴充路由為 6 passed／5 failed，包含兩項新增結構缺陷及三個原凍結缺口。Windows root/run junction 均透過 `mklink /J` 實際建立，未 skip。

**綠測證據：** fresh TEMP `C:\t\r26s5final1`、`PROFILE=test`、TEMP/資料/輸出隔離，四檔 focused 路由涵蓋本切片、既有 writer/loader、overlay、write-guard，結果 **47 passed／0 failed／0 skipped**。命令：

```powershell
$env:TEMP='C:\t\r26s5final1'
$env:TMP='C:\t\r26s5final1'
$env:PROFILE='test'
$env:DATA_ROOT='C:\t\r26s5final1\data'
$env:OUTPUT_ROOT='C:\t\r26s5final1\output'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_excluded_daily_price_namespace_red.py `
  tests/test_excluded_daily_price_revision.py `
  tests/test_daily_price_source_revision_overlay.py `
  tests/test_daily_price_revision_write_guard.py `
  -q -o addopts= -p no:cacheprovider --basetemp C:\t\r26s5final1\pytest
```

`mypy data_module/excluded_daily_price_revision.py tests/test_r026_excluded_daily_price_namespace_red.py` 為 2 files／0 issues；兩檔 `py_compile` 通過，`git diff --check` 無 whitespace error（Git 僅提示 source 檔 LF/CRLF 轉換）。測試仍驗證九欄 legacy list 欄位／順序、applied keys、rolled-back 空結果、pending 拒絕及 PIT 既有行為。

最終 Slice 5A frozen SHA-256：source `data_module/excluded_daily_price_revision.py` `09A2F9175CDBD536647EB18A023D06B3F956F53885AE58F494A4170C768A79C4`；本測試 `tests/test_r026_excluded_daily_price_namespace_red.py` `6980F3A6A6E90D20D9BAA6D3262CE84F9AD1C24EDB299B8AA73FDD1699EC71CB`；inventory `qa/full_app_healthcheck/test_inventory.py` `92732341F58D298F5D3C40901E3BA73DF6CA0506DE15EB2B797F397D14D57B03`。

本 slice 只把 `archive.json` manifest 的 SHA 與 JSON 解析綁到同一個已讀 bytes buffer，並提供共用 bytes parser。其餘八個來源 payload 與八個 acquisition receipt 尚未在本 slice 改成同 bytes parse/hash；`_validate_market_chain` 的 source manifest 也未改。沒有新增 typed excluded namespace identity，沒有建立跨檔原子快照，也沒有關閉 ABA／掃描完成後的替換風險。writer、overlay、9 欄回傳 ABI 與來源 cutoff 未改。R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`。

## `formal_market` basename 假空結果 P2 follow-up（2026-09-25）

**狀態：** bounded `ACCEPTED_SCOPE`（R027 獨立複核，root 採納）。獨立 fresh TEMP 四檔 route 為 51 passed／0 failed／0 skipped；另跑 `tests/test_formal_market_data_repair.py` 為 11 passed。此 follow-up 不代表 excluded namespace typed identity 已完成，也不關閉 R026／`TMP-ML-01`。

前文「既有 nested `formal_market` 子樹在本層只作安全解析後保留」是 P2 修補前的狀態描述，現由本 follow-up 取代；production scanner 已移除 basename 特例，synthetic market fixture 也已搬回正式 market receipt root。

前次 review 發現 `_marker_paths()` 以 `entry.name == "formal_market"` 且沒有 `revision.json` 作為足夠條件，直接略過該目錄。這會讓 `formal_market/journal.json`、partial 子 run 及 nested run junction 都回傳 legacy `[]`，造成不完整 writer 狀態被當成空集合。修補前 fresh TEMP red 路由為 **3 failed／1 passed**；三個 fail 分別是 journal-only、partial child 與 junction 目錄未被拒絕，prepare-only 控制仍通過。

窄修補移除 basename 特例。現在只有該層恰為普通 `before_rows.json` 與 `plan.json` 的 writer prepare-only 形狀才可略過；journal-only、巢狀 child／junction、其他 partial 形狀皆 fail closed。測試夾具 `_write_market_receipt()` 也改用真實 `formal_market_revision.RECEIPT_DIR` (`output/scheduled/formal_market_repair_receipts/<run_id>`)，不再把 synthetic market receipt 塞進 excluded receipt root 的 `formal_market/<run_id>`。這只修正測試夾具的 namespace 位置，保留 plan 內 market path、market chain 驗證內容與 exclusion writer ABI。

fresh TEMP `C:\t\r26s5a_final_e35cd51d`、`PROFILE=test`、隔離 `DATA_ROOT`／`OUTPUT_ROOT`／`TEMP`／`TMP` 的四檔路由：

```powershell
$env:TEMP='C:\t\r26s5a_final_e35cd51d'
$env:TMP='C:\t\r26s5a_final_e35cd51d'
$env:PROFILE='test'
$env:DATA_ROOT='C:\t\r26s5a_final_e35cd51d\data'
$env:OUTPUT_ROOT='C:\t\r26s5a_final_e35cd51d\output'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_excluded_daily_price_namespace_red.py `
  tests/test_excluded_daily_price_revision.py `
  tests/test_daily_price_source_revision_overlay.py `
  tests/test_daily_price_revision_write_guard.py `
  -q -o addopts= -p no:cacheprovider --basetemp C:\t\r26s5a_final_e35cd51d\pytest
```

結果 **51 passed／0 failed／0 skipped**；pytest log SHA-256 `0E424D9724896686B8534343F929F2DD753CCF4934708AB2D23DDF7ABC70E03F`。三個修改後 Python 檔案 scoped mypy **3 files／0 issues**，`py_compile` 通過，`git diff --check` 無 whitespace error（Git 僅提示 source 與既有 fixture 的 LF／CRLF 轉換）。既有 test path 已登錄 `service-oracle-recommendation`，本 follow-up 沒有改共享 inventory。凍結 SHA-256：`data_module/excluded_daily_price_revision.py` `5DBC116C9B3FF7E04B656AEA16FB283C9A275A1BED7DBF773CFA32F3A45A7035`；`tests/test_r026_excluded_daily_price_namespace_red.py` `5AA95EE057C1E3650AECB14A49D6DE027CCB97BF00FFC63248CEDECCD78CD9A9`；`tests/test_excluded_daily_price_revision.py` `A5071E47C0A563301FBF3B14BDB30E909C98A9C5177E919AC661CC25B640DB2A`。

這只關閉 basename 特例導致的假空結果，不延伸為 nested market chain 驗證、跨 namespace identity、跨檔原子性或 ABA 保證。R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`。
