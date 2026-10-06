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
