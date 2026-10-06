# 明示市場 CSV consumer 工程 lane

2026-10-06。基準 `1454a125db0e61dbecc7522c48b236997ff7b242`，branch `lane/market-csv-export-20261006`，worktree `C:/Projects/PythonProjects/technical_analysis/output/worktrees/market-csv-export`。唯一 dev 整合 owner：`01a10f1e-1fa7-7660-b46e-4e2107d52078`。

本包僅新增 `app_module/market_csv_export.py`、`tests/test_market_csv_export.py` 與本 QA。未改 shared personal paths、config、UI、Manual、plan、排程或正式 migration。未讀取／複製真 personal files 或真 DB，未匯出、上傳、分享或永久刪除任何使用者資料；本 lane 不 cherry-pick dev 或 push。

開始時 `git grep` 核對既有 `MarketOnlyExportPlan`／`plan_market_only_export` 只有 metadata producer 與測試，沒有 copy consumer。Graphify 既有圖共 51,303 nodes，但未收錄這组符號，不能用舊圖宣稱 consumer 存在；直接讀目前原始碼及 `PERSONAL_SUBTREE_POLICY_LANE_20261006.md` 核對。最新使用者已取消午夜停工，舊 UTC07:00 限制不適用；本 lane 完成提交後仍依委派交父層整合。

## API 與 ownership

```python
from app_module.market_csv_export import export_market_csv

# plan 沿既有 producer 建立；此 lane 不增加 root/config 預設。
# accepted_hashes 由 caller 核對並明示接受，必須與 plan 明列路徑完全同鍵。
receipt = export_market_csv(
    plan,
    expected_sha256=accepted_hashes,
    cancelled=cancelled,  # None 或無參數、回傳 bool 的合作取消 callback
)
```

`expected_sha256` 是 lowercase 64 字元 SHA-256，不能缺鍵、多鍵、未知或自動接受 consumer 當下觀察到的內容。API 回傳 immutable `MarketCsvExportReceipt`：destination、canonical receipt path、receipt bytes SHA-256、逐檔 relative path／來源 identity／size／SHA-256。沒有 CLI、UI 接線或網路功能。

只接受 exact `MarketOnlyExportPlan`。先走其既有 whitelist／personal／output／link／alias 守衛，再要求非空清單、新目標不存在、父目錄已存在。沒有 glob 或整包 FA_Data copy；禁止將目標與 market／personal／legacy output 重疊。nested personal／output／sqlite／watchlists／research_notes／ledgers components、DB／sidecar 名稱也拒絕。SQLite 主檔、WAL、rollback journal header 或 NUL binary 即使改名 CSV 也拒絕。

本版要求 Windows handle backend；其他平台明確 `export_platform_unsupported`，沒有降級為未鎖定 copy。以 `CreateFileW` 的 OPEN_REPARSE_POINT／BACKUP_SEMANTICS 鎖定完整目錄鏈，來源和輸出 handle 不分享 write／delete，目錄鏈不分享 write／delete。取得 handle 後再次核對路徑、來源 fd identity、nlink 與 caller hash；所有 handle 保留至最後發布。複製分塊、flush／fsync、輸出 hash、全來源 hash／identity 及輸出 identity 再核驗；最後一次取消 callback 之後重驗，防 callback 自身新增 hardlink 或改路徑。只檢查已建立目標的明列子目錄，拒絕額外 artifact，不掃描其他來源檔案。

只有 `market-csv-export.v1.json` canonical filename 的原子、不可覆寫 rename 是 completion commit point。payload `status=verified` 描述核驗；`.market-csv-receipt.<id>.pending` 即使有相同 payload，也不是完成收據。先寫 exclusive pending、flush／fsync／hash，使用原 receipt handle 的 `SetFileInformationByHandle(FileRenameInfo)`，不重新追蹤 pending path 且 `ReplaceIfExists=false`。完成 receipt 只包含明列市場 CSV metadata，不含 personal root、私人檔內容或 DB。

取消／失敗以具名 `MarketCsvExportCancelled`／`MarketCsvExportError`／原有 `PersonalDataPathError` 回報；原有目標拒絕，失敗後新 partial 與 pending 保留供核對，不刪除、不覆寫，也不能直接重試原目標。重試必須明示另一全新目標。第三方在 commit point 插入既有 receipt 時，原子操作拒絕且保留第三方 bytes；consumer 不宣稱該第三方收據是本次完成。

## 驗證結果

最終 **156 passed，9.08s，0 skipped**：consumer 52 項、既有 personal paths 104 項，同次 synthetic 回歸。沒有新增 UI；未執行或宣稱 UI／全 repository gates 通過。

- 精確 whitelist 多檔 copy、receipt bytes/hash/identity、無 excluded artifacts、來源 bytes／dev／ino／size／mtime／ctime 不變。
- caller hash exact keys／格式／失配、空 plan、來源修訂、forge path／identity／source、既有目標與重複執行拒絕。
- SQLite／sidecar／binary 偽裝、nested 私人／output 元件、真 synthetic junction 與 hardlink 負例。
- 實際 Windows 分享鎖阻擋 source write／目錄 rename／output overwrite；最後 callback hardlink 不可逃過復核。
- 大於一個 chunk 的 streaming 中途取消、copy 前取消、receipt pending 時取消、故障注入 publication failure、額外 artifact 注入。
- pending 路徑替換拒絕、原子發布不覆寫競爭 receipt、UTF-16 surrogate 目標、新程序重讀逐檔 SHA-256 一致。

```powershell
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m pytest tests/test_market_csv_export.py tests/test_personal_data_paths.py -q -o addopts= --basetemp=C:/Projects/PythonProjects/technical_analysis/.t/mcsv_h --tb=short
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m mypy app_module/market_csv_export.py app_module/personal_data_paths.py --cache-dir=output/qa/market_csv_mypy_fullimports
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m py_compile app_module/market_csv_export.py tests/test_market_csv_export.py
```

mypy 正常 follow imports：2 modules 通過；兩新增 Python compile 通過。初次 runner 缺 basetemp 父目錄為 setup error，補建立後，深層 worktree 的既有 COW fixture 又因 Windows 長路徑失敗；改用 repo 已排除 `.t/mcsv_h` 短 synthetic 路徑後同套全部通過，未改共用 converter 或測試。沙箱也不能以 handle 鎖定 profile 的全部祖先，QA 故使用 repo 隔離 fixtures，不為此升權讀個人資料。所有 raw fixture／cache 留 ignored，不 stage。

## 限制、交接與回滾

這是 Windows 隔離 consumer 工程，尚無實際 caller 接線、真市場包驗收、分享操作或正式啟用。目標必須是 caller 控制的隔離目錄、可鎖定完整祖先鏈的 Windows filesystem；鎖定失敗即拒絕。所有來源／輸出 handles 同時持有，大型清單的資源與效能尚無正式 gate。此介面沒有針對惡意管理員、kernel／raw-volume writer 或不遵守 Windows sharing 的 filesystem 提供保證。

whitelist／hash／binary 守衛不能證明 CSV 每一欄是非私人內容，也不是來源授權、license 或分享接受；caller 應只傳入已核對的明示市場來源。不能把私人資料重新複製成普通文字 CSV 後視為已驗證市場資料。SQLite 表／view／trigger／sidecar 分享契約仍未建立；FA_Data 現包含 personal 子樹，整包仍不得直接分享。

本包不涉及策略、回測、推薦、績效或 benchmark 計算，Look-ahead／金融 float 核心檢查不適用，新增 consumer 無 float 計算、無 SQLite API 或 config 匯入。

主 owner 可 review／採納本限定提交，並另行決定 consumer caller、接受 hash producer 及 Manual／其他 SSOT 同步；本 lane 不修改共享文件或跨 ownership 接線。shared-state 依本委派「只新增三檔」邊界不寫其他檔，交接資料集中本 QA 與最終回覆。

| 檔案 | 類型 | 回滾 | 風險 |
|---|---|---|---|
| app_module/market_csv_export.py | 新增 | `git revert <本包commit>` | 只撤回未啟用 consumer；無資料遺失 |
| tests/test_market_csv_export.py | 新增 | 同上 | 無資料遺失 |
| 本 QA | 新增 | 同上 | 無資料遺失 |

整合前可保留此 branch／worktree 而不採納；沒有執行 revert／清理。回滾程式不撤銷任何 caller 日後實際建立的輸出包，不得因此刪除來源或其他 lane 資料。

## 第二包：獨立 caller CLI（2026-10-06）

父層接受第一包 `f0e1d8e62727a305ee7ff74c3b42e363fecce1db` 後，明示授權此包接續 CLI；仍在相同 branch／worktree。開工及提交前核對 dev／lane 均沒有 `scripts/export_market_csv.py` 或 `tests/test_export_market_csv_cli.py`，無新檔 ownership 衝突。只新增此二檔並追加本 QA；consumer、shared personal paths、config、UI、Manual、plan 皆不修改。

此包補足前段「尚無 caller」的獨立 CLI 工程，但不代表有 UI／Task／正式市場來源接線或真資料分享驗收。原 consumer 的 Windows／隔離 root／來源授權限制維持。完整兩包須依序採納，第二包依賴第一包的 API 與 handle 守衛；唯一 dev owner 仍為 `01a10f1e-1fa7-7660-b46e-4e2107d52078`。

### 操作與輸出契約

本機入口：`python scripts/export_market_csv.py`。以下是 caller 使用示例，本 lane 沒有對任何真來源執行。

```powershell
# 預設唯讀 preview；stdout 為 JSON，caller 可核對後自行保存。
python scripts/export_market_csv.py --market-root <absolute-market-root> --destination-root <absolute-new-target> --file daily_price/20261006.csv --file meta_data/market_index.csv

# 只有 caller 已核對並保存上述 preview，才明示執行。
python scripts/export_market_csv.py --market-root <absolute-market-root> --destination-root <absolute-new-target> --file daily_price/20261006.csv --file meta_data/market_index.csv --execute --accepted-preview <absolute-reviewed-preview.json>
```

必填來源／目標為 absolute，`--file` 可重複但必須明列 whitelist CSV，沒有 glob／recursive／whole-root 選項。`--personal-root` 未指定時只明示解析 market-root/personal，`--legacy-output-root` 未指定時 market-root/output；兩者皆排除且不建立。不讀全域 config、環境 root 或預設正式 D: 資料。市場 metadata plan 沿既有 producer，再加 consumer 同款 nested private／SQLite name 守衛；preview 的來源內容讀取也沿 Windows handle/hash/binary 守衛，不繞過真正執行時限制。

preview stdout schema `market-csv-export-preview.v1`，status `preview`：明列 source_roots、destination_root、file_count、整數 total_size_bytes、逐檔 observed_source_pins 的 relative_path／source_identity／size／SHA-256，以及 personal／output／SQLite／未列檔案排除。`source_hashes_accepted=false`、`writes_performed=false`、uploaded/shared false。觀察 hash 不自動接受，preview 不寫任何檔案或建立目錄；接受 preview 的保存是 caller 的獨立明示操作，不由 script 默默代存。

`--execute` 必須同時有 `--accepted-preview`，單給接受文件不能隱性執行。接受文件須在 market／personal／legacy output／destination 外的隔離路徑，拒絕 link／hardlink，限 1 MiB；只讀一次具名文件。接受 schema／status、三 root、精確明列檔案集合、沒有重複、原 identity／size 及合法 hash 都核對；不在下一程序把目前來源重新認成接受版本。檔案有任何來源 identity 修訂或 caller hash 失配即 blocked。目標可以另選新位置，來源 pins 不因此重新接受，允許取消後原接受來源的明示重試。

execute 成功 status `completed`，返回 canonical receipt path／bytes SHA-256、檔數／整數體積、uploaded/shared false。來源與目標仍由 consumer handle guards 復核。既有目標（含完成或 partial）不覆寫，重試需另一全新目標；這不是正式 migration 或傳送資料。SIGINT／Ctrl+C 轉合作取消，恢復原 signal handler；取消回傳 130，blocked／IO／hash／路徑錯誤回傳 2，成功 preview／execute 回傳 0。錯誤列具名 code、error_type（blocked）、destination 與不發布完成／partial 保留規則。標準 argparse 使用錯誤仍輸出 usage，code 2。

本版本 Windows 限制在 `--help`、preview 平台欄位與不支援平台的具名拒絕明示。沒有其他平台未鎖定 fallback。操作 stdout 固定 UTF-8，支援繁體中文 JSON／說明。`--accepted-preview` 是 caller 接受工程來源 pins，不是授權證明或 license／市場分享資格；內容私人與真來源授權仍需 caller 核對。

### 第二包驗證與交接

**182 passed，14.69s，0 skipped**：CLI 26、consumer 52、既有 personal paths 104，同套 synthetic 回歸。three-module mypy 正常 follow imports 通過；兩個新增 Python compile 通過。沒有真市場包、個人資料操作、永久刪除、上傳／分享、Task 或 Native。

CLI 包涵蓋 default preview 不寫／來源 identity 不變、明列來源／體積／排除、明示 execute 與 accepted-preview 配對、新目標 receipt／hash／新程序一致、完成目標拒覆寫／另新目標重試、來源跨 preview 修訂／hash 失配、root／schema／檔案／重複 pins 篡改、整包／glob／personal／output／SQLite 與偽裝 CSV 拒絕、preview 取消、執行 partial 取消後無 canonical receipt、SIGINT 合作取消與 handler 回復、publication IO 故障無假完成、Windows help 限制。

```powershell
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m pytest tests/test_export_market_csv_cli.py tests/test_market_csv_export.py tests/test_personal_data_paths.py -q -o addopts= --basetemp=C:/Projects/PythonProjects/technical_analysis/.t/mcsv_cli_a --tb=short
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m mypy scripts/export_market_csv.py app_module/market_csv_export.py app_module/personal_data_paths.py --cache-dir=output/qa/market_csv_cli_mypy
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m py_compile scripts/export_market_csv.py tests/test_export_market_csv_cli.py
```

此包回滾 `git revert <CLI commit>`，只撤回新 script／tests 和本追加 QA，保留第一包 consumer；沒有資料遺失風險，也不得刪除 caller 日後真實輸出。下一安全接手點為主 owner review 兩包依賴後限定採納；本 lane 完成本機 commit／readback 後停，沒有 dev 整合或 push。真來源完整度、handle／檔數容量效能、分享授權、UI／Task／Manual 正式接線仍未驗收。


## 2026-10-06 dev owner採納與長路徑修正

兩lane commits以ac0cc19b→ffa6e537採納。review重現長路徑canonical receipt錯名，修UTF16尾NUL且發布後核exact path／identity／hash；新10案例、192synthetic全套與深CSV／CLI88重複驗通過。Manual與原plan同步，真資料／分享未做，[整合限制與證據](MARKET_CSV_EXPORT_INTEGRATION_20261006.md)。
