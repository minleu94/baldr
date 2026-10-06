# R016 legacy 完整 payload query projection 實作報告

TASK_STATUS: `U4_LEGACY_QUERY_EXTENSION_ACCEPTED_SCOPE`
OWNER: `Luna Max — R016 U4 query extension`
DATA_SCOPE: `synthetic tmp_path only`
INDEPENDENT_REVIEW: `ACCEPT_WITH_NONBLOCKING_NOTES`
SOL_DECISION: `ACCEPTED_SCOPE`（synthetic/engineering；無 trusted digest 的 legacy 僅 read-time-only）

## 完成範圍

- 在 `app_module/recommendation/queries.py` 新增 `LegacyRecommendationOriginalPayload` 與 `RecommendationExecutionQueries.get_legacy_original_payload()`。輸出包含 result ID、固定 runs 範圍內的資料路徑、完整 deep-frozen payload mapping、read-time SHA-256、既有 trusted/read-time integrity basis，以及 `registered_legacy_run` / `unindexed_legacy_file` 來源標記。
- Registered legacy 仍只透過唯讀 SQLite/raw-byte reader 取值；同一份 bytes 先由既有 `decode_artifact` 驗 hash、legacy DTO 與 result identity，再於同 bytes 保留完整 JSON mapping。回傳前再次確認 bytes、path、result identity 與 trusted hash authority 未變。每次 registered raw read 都要求設定 runs 絕對路徑等於 `resolve(strict=True)` 結果，並在讀前、讀後拒絕 root symlink/reparse；Canonical opaque ID 的 legacy 衝突檢查只查 SQLite identity metadata，不會按該 ID 開啟 legacy filename。
- Registered 與 unindexed legacy 路徑都改用 query 自有 no-follow file helper。Windows 以 `CreateFileW(OPEN_REPARSE_POINT)` 開啟並持有 volume/root/每層 parent/file handles；從同一 handle 要求 `GetFileType == FILE_TYPE_DISK`、拒絕 device/reparse attribute，並核對目錄／一般檔案型別，再讀取該 file handle；不含 `FILE_SHARE_DELETE`，避免持有期間替換 root/parent。缺少 Win32 API 時 fail closed。POSIX 以 `dir_fd`、`O_DIRECTORY`、`O_NOFOLLOW` 逐層錨定並讀取.
- Legacy SQLite metadata 不再以 SQLite URI/path 重開檔案。Windows no-follow disk handle 與 POSIX 從 `/` 起的 held directory-FD walk 讀取 main DB bytes；讀前／讀後檢查 sidecar，核對同一 handle 的 file type、大小與時間／identity 穩定性，再 `deserialize()` 到 `:memory:`、設定 `query_only` 並執行 `integrity_check` 與 runs schema 驗證。WAL header、存在的 `-wal/-shm/-journal`、dangling reparse sidecar、缺少 `deserialize` API、完整性／schema 失敗皆 fail closed，不做 pathname fallback。只有在初始 preflight 已證明 runs tree 尚未建立，或 held root 下 no-follow stat 證明 main DB 原本不存在時才回傳空結果；preflight 後 root、DB entry 或 sidecar 改變皆為 integrity failure。
- Registered 與 unindexed 的 legacy ID 共用 Windows 單一檔名 guard；拒絕 ADS 冒號、DOS device aliases、Win32 禁用字元及尾隨空白／句點。Canonical typed query 仍可讀取含 Win32 特殊檔名字元的 opaque ID，因 canonical artifact 使用自身安全命名；若同 ID 同時被 legacy SQLite 註冊則 fail closed。`list()` 將不安全 legacy ID 回報為 integrity error。
- Unindexed 舊 JSON 預設不讀。僅 `allow_unindexed_legacy=True` 可讀 store 所屬 runs 根目錄下精確 `<simple-result-id>.json`；讀取前後重查 bytes/path、SQLite registration 與 canonical claims。路徑必須是 runs root 的直接子檔，並拒絕 symlink/reparse、scope escape、非一般檔案及 canonical identity/index 衝突。此來源明示為 `unindexed_legacy_file`，不冒充 index registration 或歷史可信 hash。
- Canonical result 經 legacy-only API 讀取時 fail closed；canonical execution typed read model 沒有新增任意 mapping。沒有獨立可信 digest 的結果仍只標 `legacy_read_time_hash_only`。
- 不修改 Journey consumer、R014/R017/Qt、writer/store/codec、正式資料或 legacy bytes。專用測試將 query projection 提供給既有 Journey parser，核對 source identity、candidate rank 與 opaque payload 可供原有 Journey read model 完整保留；正式 consumer 接線仍屬 R016 consumer owner。

## 測試情境

專用 `tmp_path` 合成測試覆蓋：

- 登記 legacy JSON 保留 top-level `source_id`、`source_snapshot_id`、`source_snapshot_hash`、candidate `recommendation_rank`、未知 row 欄位及多層 opaque payload；Journey read model 取得相同 identity、rank 與 payload。
- deep immutability、query 前後原始 bytes 不變、預設 read-time digest，以及明確注入可信 digest／錯誤 digest fail closed。
- unindexed exact-ID JSON 預設不讀；明示 opt-in 後保留完整 payload且維持 read-time-only 信任標記。
- unsafe legacy ID（ADS、DOS devices、尾隨 dot/space、禁用字元）、registered/unindexed root reparse guard、合成 root resolve retarget、Windows clean-preflight 後 handle reparse 模擬、同一 handle 的 `GetFileType` 拒絕 character device、`GetFileType` API 缺失、readback bytes/path 變化、無效 JSON、已有但路徑不合法的 SQLite registration、metadata-only canonical claim 與 canonical index collision 都 fail closed；壞 SQLite row 不會降級重讀同名 unindexed file。
- Windows canonical opaque-ID regression 證明含冒號的 canonical ID 仍可讀取，並驗證同 ID 一旦出現在 legacy SQLite identity 即拒絕回傳。
- SQLite 合成測試涵蓋一般 DELETE-mode 快照、query-only／integrity／schema、WAL header、三種既有 sidecar、讀取期間出現 sidecar、handle fstat 改變、缺少 deserialize API、不完整 runs schema、POSIX ancestor/DB entry no-follow swap、POSIX DB leaf 預檢後消失、Windows DB leaf lstat 後消失與 dangling sidecar reparse。
- 所有檔案與 DB fixture 均建在 pytest `tmp_path`；測試不建立正式資料輸出。

## 驗證命令與結果

下列命令執行前設定臨時環境變數：

```powershell
$env:DATA_ROOT = Join-Path $env:TEMP 'r016-query-u4-final-data'
$env:OUTPUT_ROOT = Join-Path $env:TEMP 'r016-query-u4-final-output'
$env:PROFILE = 'test'
.\.venv\Scripts\python.exe -m pytest tests\test_r016_legacy_query_projection.py tests\test_c1_legacy_query_readiness.py tests\test_r012_recommendation_artifact_persistence.py -q -rs -o addopts= -p no:cacheprovider
.\.venv\Scripts\python.exe -m py_compile app_module\recommendation\queries.py tests\test_r016_legacy_query_projection.py
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module\recommendation\queries.py
```

```text
.\.venv\Scripts\python.exe -m pytest tests\test_r016_legacy_query_projection.py tests\test_c1_legacy_query_readiness.py tests\test_r012_recommendation_artifact_persistence.py -q -rs -o addopts= -p no:cacheprovider
110 passed, 4 skipped
```

4 個 skip 是既有 C1/R012 symlink 測試；此 Windows 環境無權建立測試 symlink，回報 `[WinError 1314] A required privilege is not held by the client`。新 SQLite 測試另以 deterministic hooks 模擬 POSIX ancestor/DB entry 的 no-follow race、DB bytes/stat 改變、Windows sidecar reparse／post-lstat 消失，不依賴 symlink privilege。未宣稱完成 OS 層實際 symlink/reparse 實測。

獨立 query 專用測試：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_r016_legacy_query_projection.py -q -rs -o addopts= -p no:cacheprovider
```

```text
49 passed
```

```text
.\.venv\Scripts\python.exe -m py_compile app_module\recommendation\queries.py tests\test_r016_legacy_query_projection.py
passed

.\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module\recommendation\queries.py
Success: no issues found in 1 source file
```

## 複審歷史與目前狀態

第一輪獨立複審提出 Windows no-follow P2；後續複審要求同一 handle 證明一般 disk file、補 registered ID 的 Win32 alias guard，並驗證 registered runs root 沒有 reparse/resolve retarget。已加入 Windows `GetFileType` disk-only 與 device/reparse 拒絕、registered/unindexed 共用 ID guard、canonical opaque-ID regression、metadata-only legacy collision lookup，以及 root reparse／resolve-retarget 負例。

早先第三輪獨立複審曾接受當時的 U4 scope（reviewer focused `50 passed, 1 skipped`），但後續獨立安全複審發現 POSIX runs root ancestor 只在最後 component 使用 no-follow，以及 SQLite URI pathname reopen／sidecar race，因此已重新開啟此 gate；該歷史接受不代表目前修訂已接受。

本次候選加入 filesystem-root 起逐層 `dir_fd|O_DIRECTORY|O_NOFOLLOW` 錨定、同 handle pinned main-DB bytes、sidecar 前後檢查、SQLite in-memory deserialize/query-only、integrity/schema proof、WAL 與 sidecar 拒絕、初始缺少 runs tree 與讀取競態分流，以及相應 deterministic 負例。最新合併 focused run 為 `110 passed, 4 skipped`；單獨 U4 suite 為 `49 passed`；`py_compile` 通過、mypy `Success: no issues found in 1 source file`。

獨立第二輪複審最終 verdict 為 `ACCEPT WITH NONBLOCKING NOTES`，確認本 query extension 無剩餘 scoped P1/P2，reviewer 專用 TEMP suite 為 `49/49 passed`。非阻塞限制為：此 Windows host 未跑 native POSIX race runtime，且實際 symlink/reparse 建立受 Windows 權限限制；相關 race 以 deterministic hooks 覆蓋。無獨立可信 digest 的 legacy 仍只有 read-time hash 信任級別。SOL 裁決 U4 `ACCEPTED_SCOPE`（synthetic/engineering）；這不代表整體 R016 或 Wave 6 已接受。

## 信任邊界與後續

- Read-time SHA-256 只能識別本次讀取到的 bytes；沒有獨立保存的 trusted expected hash 時，不能證明讀取前的歷史完整性，也不能證明舊 mutable source 在不同讀取時刻保持不變。此時只標示 `legacy_read_time_hash_only`，不宣稱 trusted historical integrity。
- Unindexed projection 僅是 exact-ID 唯讀相容通道，不會寫入或補建 SQLite index，也不會出現在 `list()`；R016 consumer 應保留明確來源標記。
- Journey production adapter 尚未改接此 query API；這是 R016 consumer owner 範圍。此報告只簽收 U4 query extension，不代表 R016 整體完成。
- 未執行 scheduler、正式資料、full ML、stage、commit 或 push。
