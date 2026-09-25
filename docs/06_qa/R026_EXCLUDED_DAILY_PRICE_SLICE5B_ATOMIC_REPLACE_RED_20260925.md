# R026 Excluded Daily-Price：Slice 5B atomic-replace QA

**日期：** 2026-09-25
**狀態：** 本文件保留修補前的隔離 synthetic baseline，並追加 Slice 5B1 有界修補證據。Archive payload／acquisition receipt 與 non-full market source manifest 的 hash／size／parse 現共用同次讀取 bytes；R015 獨立複核（無 P1/P2）後，root 判定 Slice 5B1 為 bounded `ACCEPTED_SCOPE`。rollback typed collector 缺口仍以單獨預期紅測保留；R026 與 `TMP-ML-01` 仍 `IN_PROGRESS`／`ACTIVE`。

## 路由與隔離

在 Windows、repo Python 3.11.9 與 `PROFILE=test` 下，`TEMP`、`TMP`、`DATA_ROOT`、`OUTPUT_ROOT`、pytest `--basetemp` 均指向新的 TEMP root：
`C:\Users\archi\AppData\Local\Temp\r026_excluded_atomic_red_ea13abf2b7b2469986186235e4eb251e`。

```powershell
$env:TEMP='C:\Users\archi\AppData\Local\Temp\r026_excluded_atomic_red_ea13abf2b7b2469986186235e4eb251e'
$env:TMP=$env:TEMP
$env:PROFILE='test'
$env:DATA_ROOT="$env:TEMP\data"
$env:OUTPUT_ROOT="$env:TEMP\output"
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_excluded_daily_price_atomic_replace_red.py -q -s -o addopts= --basetemp "$env:TEMP\pytest-tmp"
```

結果：**3 failed，0 passed，0 skipped**（約 1.71 秒）。完整輸出保存在 `C:\Users\archi\AppData\Local\Temp\r026_excluded_atomic_red_ea13abf2b7b2469986186235e4eb251e\pytest.log`，其 SHA-256 為 `3CA8002BB5BA0DEC5BBB0772B127FD8F0EB9FD9A6CE51C4C3CA764109CC7A511`。測試直接呼叫既有 archive loader 與 market-chain validator，沒有因為新 typed collector 尚未存在而遮蔽前兩項 race 結果。測試檔 SHA-256：`819538F5B9BC7C23E4C3FC86366B1E1843F903A2C3D0CEF99D5614D8C0A43C50`。

## Slice 5A 凍結 bytes 上的紅測重跑

R015 凍結 Slice 5A 後，以另一個 fresh TEMP root `C:\Users\archi\AppData\Local\Temp\r026_excluded_atomic_red_frozen_dfe574bb117d4ba08feb5c18c8e5b9f2` 重跑同一個 Slice5B 測試。執行時 `data_module/excluded_daily_price_revision.py` SHA-256 為 `5DBC116C9B3FF7E04B656AEA16FB283C9A275A1BED7DBF773CFA32F3A45A7035`，`tests/test_excluded_daily_price_revision.py` synthetic writer fixture SHA-256 為 `A5071E47C0A563301FBF3B14BDB30E909C98A9C5177E919AC661CC25B640DB2A`；Slice5B 測試檔仍為 `819538F5B9BC7C23E4C3FC86366B1E1843F903A2C3D0CEF99D5614D8C0A43C50`。

```powershell
$env:TEMP='C:\Users\archi\AppData\Local\Temp\r026_excluded_atomic_red_frozen_dfe574bb117d4ba08feb5c18c8e5b9f2'
$env:TMP=$env:TEMP
$env:PROFILE='test'
$env:DATA_ROOT="$env:TEMP\data"
$env:OUTPUT_ROOT="$env:TEMP\output"
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_excluded_daily_price_atomic_replace_red.py -q -s -o addopts= --basetemp "$env:TEMP\pytest-tmp"
```

結果仍是 **3 failed，0 passed，0 skipped**（約 1.82 秒），與三項預期紅點完全相同。輸出 log 為 `C:\Users\archi\AppData\Local\Temp\r026_excluded_atomic_red_frozen_dfe574bb117d4ba08feb5c18c8e5b9f2\pytest.log`，SHA-256 `67870E2A3A8D1DFD10F58E65A9BF3CA6AACCCC9B2DC1001D850DDB6524B70487`。archive payload、receipt 與 market manifest 的 hash/parse mismatch SHA 也與前次相同；rollback legacy list 仍為 `[]`，typed collector 仍缺席。這次 rerun 把 Slice5B red baseline 綁定至上述 Slice 5A source/helper bytes；仍是刻意失敗的 regression characterization，不是修復或 acceptance。

## 修補前預期紅點與觀測

1. `test_archive_payload_and_acquisition_receipt_hash_parse_same_atomic_bytes`（初次 red baseline 名稱）：在 archive payload 完成第一次 hash-read 後，以 `os.replace` 原子替換 payload 與 acquisition receipt，再讓 hash pass 讀取舊 receipt、JSON parser 重開新檔。舊 loader 正常返回，但相同路徑的 hash/parse bytes 不同。Payload SHA-256 從 `fc9a8a3b41b937af1e7d7dfcf0027cde14644473938ff2c05ea808bdde4265fb` 變為 `3b459285f7546a4b4dc19394b33d01729c640cec590067e3bcb7888d4bbdad09`；receipt 從 `86097c46ad76c4f44ca622fb962320d5a5467f532ff10f09361430bbc1b4948c` 變為 `8cacf24190c8b4c94dd4f6c2d01f1653cf0a8bf1b02ae8cc794c995620c56319`。這是單一 synthetic atomic-replace 重現，不表示所有 archive 檔案都已測完。

2. `test_market_source_manifest_hash_and_parse_use_same_atomic_bytes`：在 `_validate_market_chain` 對 source manifest 計算 hash 後原子替換 manifest，validator 接著重開並解析新 bytes，仍正常返回。hash SHA-256 為 `e10caf87fa71da2cf19d529a4ed81c864c80bb589a6b64365c21276d052657be`，解析 bytes SHA-256 為 `354bbca40fc230fb0e4eb5c4e259ad5a321e897e51eddfa4b00a8c67a006d3b1`。

3. `test_rolled_back_run_is_legacy_empty_but_typed_namespace_present`：透過真實 TEMP `repair.recover(..., rollback=True)` 產生 rollback。legacy `load_exclusion_evidence()` 符合既有行為回傳 `[]`；未來 typed collector 應回傳 `EXCLUDED_DAILY_PRICE_REVISION` 的 `PRESENT`，並包含 `/rollback.json` role。當前 collector 尚不存在，故此獨立預期紅點失敗於「excluded revision typed collector 尚未實作」。這只固定 API/語意缺口，不推斷目前已有 typed rollback 實作。

新測試已登錄 `qa/full_app_healthcheck/test_inventory.py`，分類為 `service-oracle-recommendation`；該檔 SHA-256：`0E7C433A8017707CE47386E170553F7F6E9AA74910EED451DA92590C4ECE2BCE`。初次 red run 使用 source baseline `09A2F9175CDBD536647EB18A023D06B3F956F53885AE58F494A4170C768A79C4`；其後在 Slice 5A 凍結 source `5DBC116C…`、fixture helper `A5071E47…` 上重跑，三項仍 red。namespace test 在本輪開始時 SHA 為 `6980F3A6A6E90D20D9BAA6D3262CE84F9AD1C24EDB299B8AA73FDD1699EC71CB`；並行中 R015 另加 4 個 formal-market regression/control，當前 SHA 為 `5AA95EE057C1E3650AECB14A49D6DE027CCB97BF00FFC63248CEDECCD78CD9A9`。本 Slice 5B 沒有修改該 namespace test。

## Slice 5B1：archive 與 market manifest 同次 bytes 驗證

`_verify_archive()` 逐一讀取八份 official payload 與八份 acquisition receipt；同一 buffer 供 entry hash、宣告 byte length、JSON parse 與 payload/receipt SHA cross-link 使用，不再 `_read_json()` 或 `_hash_file()` 重新開檔。Archive manifest 原已用單次 bytes 驗 hash 與解析。`_validate_market_chain(..., full_source_validation=False)` 現用一次 `source_path.read_bytes()` 驗 source SHA 並交同一 bytes 給 JSON parser。Market source plan 既有 entry 只有 `path`／`sha256`，沒有 expected byte length 欄位；本切片不增 schema 或 byte-length contract。`full_source_validation=True` 的 loader 路徑不在此切片變更。

修補後 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r026_slice5b1_frozen_fca1ac4ea43c49d18b5ed86c252adff8` 使用 Windows／Python 3.11.9、`PROFILE=test`、TEMP/TMP/DATA_ROOT/OUTPUT_ROOT 及 pytest basetemp 隔離。七檔 route 涵蓋 Slice5B race tests、Slice5A namespace tests、excluded writer/loader、overlay、write guard、formal market repair 與 market evidence：

```powershell
$env:TEMP='C:\Users\archi\AppData\Local\Temp\r026_slice5b1_frozen_fca1ac4ea43c49d18b5ed86c252adff8'
$env:TMP=$env:TEMP
$env:PROFILE='test'
$env:DATA_ROOT="$env:TEMP\data"
$env:OUTPUT_ROOT="$env:TEMP\output"
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_excluded_daily_price_atomic_replace_red.py `
  tests/test_r026_excluded_daily_price_namespace_red.py `
  tests/test_excluded_daily_price_revision.py `
  tests/test_daily_price_source_revision_overlay.py `
  tests/test_daily_price_revision_write_guard.py `
  tests/test_formal_market_data_repair.py `
  tests/test_r026_market_revision_evidence.py `
  -k 'not rolled_back_run_is_legacy_empty_but_typed_namespace_present' `
  -q -s -o addopts= -p no:cacheprovider --basetemp "$env:TEMP\pytest-tmp"
```

結果 **81 passed，1 deselected，0 unexpected failures**（15.87 秒）；log SHA-256 `8F3B3D832FA53990DE24234DB90F875868BEA62CF6A3505F99E27AAA363DA7D0`。Parameterized `payload`／`receipt` cases 各驗一次 atomic replacement；loader 實際走完整八個日期／兩個 venue，斷言 16 個 payload／receipt 每檔恰一次 `Path.read_bytes()`、每份 parser bytes 與 hash bytes相同，且八份 payload 均不再走 `_hash_file()` 重讀。Market manifest race也確認一次讀取後以同一 bytes hash/parse。

Rollback typed-presence test 被有意從綠路由 deselect，並在獨立 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r026_slice5b1_rollback_frozen_09e1ab61a6fa41c7b21e416bc4096480` 執行，結果 **1 failed**，只因 `collect_excluded_daily_price_revision_evidence` 尚不存在；legacy rollback list 仍為 `[]`。該 log SHA-256 `A80442460D2F95DDC7481D23986691615B82D880F1E053C0EB3E0C7F3CC8444D`。此預期紅點尚未修，不將它計入綠路由失敗。

Scoped mypy：`mypy data_module/excluded_daily_price_revision.py tests/test_r026_excluded_daily_price_atomic_replace_red.py tests/test_excluded_daily_price_revision.py`，3 files／0 issues。上述三個 Python 檔 `py_compile` 通過，`git diff --check` 無 whitespace error（Git 僅提示 source LF/CRLF 轉換）。Look-ahead 自查：本片只改已明示 source receipt/manifest 的 bytes identity 檢查；不改 cutoff、日期、來源選擇、writer、legacy list／overlay ABI 或任何市場／金融計算。沒有建立多檔原子快照、跨檔一致性、ABA 防護或 typed collector。

Slice5B1 frozen SHA-256：`data_module/excluded_daily_price_revision.py` `453BE833F6EC4EBCA2DE53011C302930D9B77DDB5A44E5D07FF4B4B7B53546E5`；`tests/test_r026_excluded_daily_price_atomic_replace_red.py` `A46728D1D0856D73D89BDB03211ACBCCFB2DCE3D3191849DDA84ED2B3D4CDAC8`。本段記錄 Slice5B1 frozen inputs；獨立複核與最終 bounded 狀態見下節。R026 維持 `IN_PROGRESS`、`TMP-ML-01` 維持 `ACTIVE`。

## 最終狀態與獨立複核

Root 依 R015 獨立複核（無 P1/P2）將 Slice5B1 判為 bounded `ACCEPTED_SCOPE`。獨立 fresh TEMP 七檔路由為 **81 passed／1 deselected**；log 位於 `C:\t\r0265b1review_20260925\pytest.log`，SHA-256 `B619DC3391918692E0497469484B708882CAE281CFEECD539A58E75208B25B86`。這筆獨立收據與上方 Slice 5B1 implementation route 的 81-pass 收據是不同執行，不應混為同一 log。deselected 的 typed rollback collector 測試仍是未實作預期紅點。

接受只涵蓋八組 payload／receipt（共 16 個 archive 檔）與 `full_source_validation=False` 的 market source manifest 同次 bytes 驗證。`full_source_validation=True` loader、typed rollback collector、跨檔原子快照／一致性與 ABA 防護仍未完成；R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Slice 5B2：excluded revision typed namespace collector

**狀態：** 經 R027 獨立唯讀複核（無 P1/P2）並由 root 判為 bounded `ACCEPTED_SCOPE`；只涵蓋 excluded daily-price namespace collector，不代表 R026 整體接受。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

新增 `collect_excluded_daily_price_revision_evidence(database_path, decision_date)`，回傳 `ValidatedNamespaceEvidenceV1`。collector 與 `load_exclusion_evidence()` 共用一次 `_marker_paths()` 掃描及 `_validated_excluded_runs()` 驗證結果，不先呼叫 legacy loader 再重掃。該次驗證實際讀取的 bytes 以 `ValidatedEvidenceFileV1` 記 role 與 SHA-256：applied run 包含 marker、plan、journal、receipt、archive manifest、八份官方 payload、八份 acquisition receipt，以及 nested market marker/journal/plan/receipt 和每份 market source manifest；rolled-back run 記錄其實際驗證的 marker、plan、journal、rollback receipt。Market source plan 只宣告 path/hash，沒有增加 size 欄位。role 前綴由 lexical run path 相對固定 receipt root 的 UTF-8 bytes 做 URL-safe Base64，子角色固定，不使用絕對路徑。

經完整掃描後的 missing receipt root 與合法 prepare-only run 回傳 `EMPTY`；validated applied 或 rolled-back run 回傳 `PRESENT`。Pending、損毀 hash/parse chain、掃描錯誤與路徑驗證錯誤均 fail closed，不會被報成空集合。PIT cutoff 仍以最早 applied `source_start_date` 為界，與既有 `assert_excluded_source_revision_safe()` 共用邏輯；rollback 不增加 active exclusions。Legacy `load_exclusion_evidence()` 仍只回傳 applied rows，九欄及原欄位順序不變；`load_exclusions()`、`load_excluded_dates()`、writer 和 overlay ABI 未改。

Test-first 初始紅測在 collector 尚不存在時有 5 個新 collector cases 因 API 缺席而失敗；Slice5B1 same-bytes regression 另有獨立測試。修補後 fresh TEMP `C:\t\r026s5b2_final_a66a8a9c8264`、Windows／repo Python 3.11、`PROFILE=test`，且 `TEMP`、`TMP`、`DATA_ROOT`、`OUTPUT_ROOT` 與 pytest basetemp 均隔離，執行八檔路由：

```powershell
$taskTemp = 'C:\t\r026s5b2_final_a66a8a9c8264'
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $taskTemp 'data'
$env:OUTPUT_ROOT = Join-Path $taskTemp 'output'
\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_excluded_daily_price_atomic_replace_red.py `
  tests/test_r026_excluded_daily_price_namespace_red.py `
  tests/test_r026_source_revision_evidence_contract.py `
  tests/test_excluded_daily_price_revision.py `
  tests/test_daily_price_source_revision_overlay.py `
  tests/test_daily_price_revision_write_guard.py `
  tests/test_formal_market_data_repair.py `
  tests/test_r026_market_revision_evidence.py `
  -q -s -o addopts= -p no:cacheprovider --basetemp (Join-Path $taskTemp 'pytest')
```

結果 **109 passed／0 failed／0 skipped**（19.31 秒）；pytest log SHA-256 `173F675DBBC1E10ADF68CEDE37B9D7D011A8B03536ADF60EB42E2D71B0D0DDA0`。新測試覆蓋 rollback legacy-empty/typed-PRESENT、missing-root/prepare-only EMPTY、穩定 roles 與 cutoff parity、pending／broken chain／scan error fail-closed，以及每個 evidence file 在同次驗證只讀一次且 parser 使用同 bytes。Scoped mypy 命令 `python -B -m mypy data_module/excluded_daily_price_revision.py tests/test_r026_excluded_daily_price_atomic_replace_red.py tests/test_excluded_daily_price_revision.py tests/test_r026_source_revision_evidence_contract.py` 為 4 files／0 issues；四檔 `py_compile` 通過；`git diff --check` 無 whitespace error（shared tree 顯示 LF/CRLF 轉換提示）。Look-ahead 自查：本 slice 僅摘要已驗證的 revision receipts/manifests，沒有更動 source selection、PIT cutoff、日期解析或金融計算。

本 slice frozen SHA-256：`data_module/excluded_daily_price_revision.py` `D5A4484194892A667AFA5A30C898BBD3ADB34259A36C6D2B51A88075ED1DA585`；`tests/test_r026_excluded_daily_price_atomic_replace_red.py` `8AE7E885AD491F64083B7EBEC831E7A7E328D2661C73E57E847FD9A7A476887C`；source-evidence contract test `tests/test_r026_source_revision_evidence_contract.py` `6FA8BC6E01672B1F6444EE957D3D05A910E654F6FCE21B3DCDACBA7E06AA013A`；shared inventory `qa/full_app_healthcheck/test_inventory.py` `0E7C433A8017707CE47386E170553F7F6E9AA74910EED451DA92590C4ECE2BCE`，Slice5B 專項路徑沿用既有 `service-oracle-recommendation` entry，未修改 inventory。

此 collector 記錄同次驗證實際讀取的各檔摘要，但不提供跨檔原子快照、ABA 防護或 SQLite/檔案系統交易原子性；`full_source_validation=True` market loader、其他 namespace aggregate、provider/ML 接線與 R026 全任務 gate 仍未完成。

R027 獨立 fresh TEMP 重跑同一八檔路由，TEMP root 為 `C:\Users\archi\AppData\Local\Temp\r026_slice5b2_review_7d6140032770495bbd074ce3ce256443`，使用 `PROFILE=test` 並隔離 `DATA_ROOT`、`OUTPUT_ROOT` 與 pytest basetemp；結果 **109 passed／0 failed／0 skipped**（15.33 秒，exit 0）。該 reviewer run 未另保存 log hash，勿與 implementation pytest log 混為一筆。root 依此複核判 Slice5B2 bounded `ACCEPTED_SCOPE`，無 P1/P2。

補充限制：nested market source manifest 的 role 使用該次 `plan.json` 來源清單位置 `source-{index:06d}`；role 對固定 plan 穩定，但跨來源清單重排不保留同一 role 名稱。此限制不影響目前單次 plan 的 bytes/hash 驗證；需要跨 plan 版本追蹤來源時，應採 data-root-relative path role。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。
