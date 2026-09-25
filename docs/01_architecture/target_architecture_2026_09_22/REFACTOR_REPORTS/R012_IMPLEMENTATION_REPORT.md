# R012 實作報告：create-only result artifact store、save 與 query

IMPLEMENTATION_STATUS: READY_FOR_REVIEW

## 範圍與基線

本次只實作 R012。派工 HEAD 為 `fbc4047b6d0e5c31d64164e95987a6ff1a15f104`；執行期間共享 HEAD 依序前進到 `85fa3cd0b78013614aa97fca082a03463922388d`、`8674cf1451720394fec3017b1450eb2ae12402ba`。root 確認兩次 model-repair 變動均位於不含 R012 owner 檔的路徑；本實作沒有 stage、commit、push、reset 或 clean。

本次回應 SOL 與 Luna 的 `CHANGES_REQUIRED`。修改前共享 HEAD 為 `1cc88ceaa079efdb90f99158558caf158d16ad8a`；修改前 SHA-256：`ports.py` `C4F0BCBF5010972FB3733F22D84607E33F9D08DA2E366D56891E4596E5E9B016`、`persistence.py` `8DBEF4961ACAF8F8C3821365F955CFADD932A2678EFC9EA29F43E5C2D3E5F79C`、`result_artifact_store.py` `D1D31ACFDE922850F2C522814FD45B6154898C3D388B57A7EEE6539CCED36622`、R012 tests `2D88B4FDE3A3646115B3C12EAB802E9400C582A562F2CA08536D180572597A90`、本報告 `689962631F8068C8F2B4F0DBBB66408EFF4B08C3A74EAD0EDD7880FB23F490AC`、rollback note `B4F17AB1B331A3E4727A7809BC215A8B0F77BEBDD6C676C24A97D67EDDABC64A`。

本輪修正後 code/test 凍結 SHA-256：

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation/ports.py` | `BB16251D819FDBA3738EDB02A822974071F6C9E98C99E8B6D48AA86139ECEDCD` |
| `app_module/recommendation/persistence.py` | `A271C4DE1417833087E0B7F4D70B3D8D4A169467CC8162BCCD6787B9AEB4A8C5` |
| `app_module/recommendation/save.py` | `7C84ABD5EDFA3158BFD90E8C73B5143D28A3B814954D6FA4275C502269B4855B` |
| `app_module/recommendation/queries.py` | `2B6962BFC640E5B92E2358D00FB47EFADE0D0C09677C785D6C327992A785238F` |
| `data_module/result_artifact_store.py` | `5E002148D2BA0AF56AA275AAF497F45046CE456255D55453BE14F124D616EE64` |
| `app_module/recommendation_repository.py` | `35672320FCABAB9C8C4D44DC57408887927329AF126EA0068BF1DA0032ABBD35` |
| `tests/test_r012_recommendation_artifact_persistence.py` | `3B2EB2B54A74DCF70668ED1ACD1B650D8E4303ABEC904791F59D4E813DE36B63` |

派工前 exclusive-owner 檔案 SHA-256：

- `app_module/recommendation_repository.py`：`D7B8460FBCD5F1D70D66D640E5770DBA9FB3662284EF6F7D4AC9BA156208373F`。此檔為處理跨 writer identity collision 而做了狹義修改；修改前 SHA 即上述派工值。
- `app_module/recommendation_save_coordinator.py`：`86844FFD8A5EC0E4C956E5B4068C78ADA877343AFFE8566C43F36FC01423411D`，未修改。

凍結相依仍逐位元符合派工 baseline：`codec.py` `A1BC97DE557C58FCAA039D06DAE909123A3E405B5E2DD7776B94F9A80ED653BE`、`execute.py` `5BFDF952AF5BC8E1A570CDE52BF06B21309A9586DD1B3F0F61150A2314486B5D`、`contracts.py` `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81`。

## 實作與資料權威

新增檔案：

- `app_module/recommendation/ports.py`
- `app_module/recommendation/persistence.py`
- `app_module/recommendation/save.py`
- `app_module/recommendation/queries.py`
- `data_module/result_artifact_store.py`
- `tests/test_r012_recommendation_artifact_persistence.py`
- 本報告及 [`R012_SCHEMA_PUBLICATION_ROLLBACK.md`](R012_SCHEMA_PUBLICATION_ROLLBACK.md)

狹義修改 `app_module/recommendation_repository.py`：舊 `save_result` 與 `save_result_create_only` 在既有 `BEGIN IMMEDIATE` 交易中檢查 canonical index、metadata identity claim 及 SHA-256-safe artifact path；同一 ID 已由新 writer 使用時拒絕舊寫入。`recommendation_save_coordinator.py`、凍結 codec/contracts/execute 和其他 consumer 均未修改。

唯一新 writer 路徑為 `RecommendationSaveService.save_execution` → `RecommendationExecutionPersistence.save` → `ResultArtifactStore`。它只接受 `COMPLETED RecommendationExecution`，呼叫既有 codec 產生 canonical bytes/hash，不從 live service 重算；receipt／projection references 經 codec 原樣往返。query 只依 exact `result_id` 讀安全映射檔名、驗證 raw hash、payload hash、embedded ID、canonical bytes 與支援的 schema，再建立 read projection。

artifact 檔名為 `sha256(result_id UTF-8).hexdigest() + ".json"`，SQLite 仍保留未正規化的原始 opaque ID；因此 `/`、大小寫、尾空白、Windows reserved name 與 traversal 文字不改 identity，也不造成檔名碰撞。query 不採信 index 的任意 path/name，而重算預期檔名。POSIX 使用 no-follow open；Windows 使用 `CreateFileW(OPEN_REPARSE_POINT)` 後由同一 handle 查 reparse attributes，並在操作期間持有 root handle、禁止 delete sharing。每筆結果只寫入 `tmp_path`，沒有正式 data/output artifact。

SQLite schema revision 沿用 artifact schema `recommendation-execution.v1 / revision 1`，沒有正式資料/schema migration：

- `result_artifact_index` 是由 artifact 可原子重建的 projection，包含 exact ID、safe artifact name、payload/raw hash 與 schema identity。
- `result_artifact_metadata` 是 label、notes、persisted_at 的可變權威，也先承接 payload-hash identity claim。它與 projection 為不同責任，但同在 `recommendation_runs.db`。
- import、app startup、query/list 不建立資料庫或 schema。只有明示 `save_execution` writer 可 additive-create 這兩張表；store constructor 與每次操作都 fail-closed 限定大小寫精確的 `runs/execution_artifacts/` 和同一 `runs/recommendation_runs.db`。不以 `casefold()` 接受 POSIX 上其實是不同的目錄或 DB；錯誤配置在建立任何路徑前拒絕。artifact root/file 在讀取時不建立。
- `rebuild_index()` 把 artifact inventory 以 lazy iterable 傳入 store；store 先取得 `BEGIN IMMEDIATE`，再掃描、驗證並原子替換 `result_artifact_index`。canonical publisher 使用同一 DB writer lock，因此 inventory 與 projection replace 有線性化順序：併發 save 要嘛被 inventory 收錄，要嘛等重建提交後發布並補寫 index；不會以舊快照刪除已回傳 `INDEXED` 的新列。它會清掉 index-only stale row，並保留 metadata authority。若整個 SQLite DB 遺失，可重建 identity/hash/schema projection，但 label、notes、persisted_at 已不可從 artifact 推得，query 回傳缺值；不會猜值或宣稱完整 metadata 可重建。DB 仍在但 metadata row 缺失時，`restore_missing_metadata()` 可插入呼叫端提供的值，不覆寫既有 rename/notes。

## Writer 身分互斥與故障恢復

兩種格式共用 `recommendation_runs.db`，result ID 採全域互斥。新 writer 先做無副作用 preflight；發布時在 SQLite `BEGIN IMMEDIATE` 內再次檢查 legacy `runs` row、legacy `runs/<result_id>.json` file-only orphan 與 metadata hash，create-only 發布 bytes，然後 commit metadata identity claim；`result_artifact_index` 只在 artifact 已發布後由後續獨立 transaction 寫入。legacy orphan 檢查依舊 writer 的原始 ID 路徑、以 `lstat` 判斷、不讀取或改寫 bytes；作業系統明確拒絕的檔名不可能是舊 writer 建立的檔案。舊兩個 writer 也在自身 `BEGIN IMMEDIATE` 內查 canonical rows/claim 和安全映射 artifact path。SQLite 寫鎖序列化兩邊，競態中只有一個 namespace 能讓結果成為可查詢 identity。

| 故障窗口 | 留下的狀態與恢復方式 |
|---|---|
| preflight 或 reservation transaction 取得 lock／查 `runs` 失敗 | 未發布 artifact；以 `ExecutionIndexReadError` 區別於 JSON/artifact 問題，可同 ID/hash 重試。已存在 legacy ID 會以 `ExecutionIdentityConflict` 拒絕，無副作用。 |
| reservation 發現 legacy `<result_id>.json` orphan | 不 create canonical payload 或 identity claim；明示 writer 可能已建立空 canonical 目錄及 additive schema。回報 `ExecutionIdentityConflict`，保留原 bytes，既有 `save_result_create_only()` 可同 bytes retry 復原 row。 |
| exclusive file create 失敗 | transaction rollback，不留 identity claim、index 或 `.json`；同 ID/hash 可重試。測試另確認 temp file cleanup。SQLite additive tables 可能已建立，但不含該 identity。 |
| artifact 已發布、metadata claim 寫入/commit 失敗 | 回報 `PartialExecutionPersistenceError(PENDING)`；canonical file-only orphan 保留。舊 writer 即使看不到 claim，也會在其 transaction 內檢查 safe artifact name，因此不能搶走 ID。相同 ID/hash 驗證 bytes 後可補 claim/index；異 hash 拒絕。 |
| metadata claim 已 commit、projection index 尚未寫入／commit 失敗 | artifact 與 claim 已存在，query 不會暴露無 index 項目；回報 PENDING。同 hash 重試保留原 metadata 並補 projection，異 hash 為 hard conflict。 |
| 舊 writer 先提交同 ID | 新 writer 的 transaction guard 看見 `runs` row，在發布前拒絕。 |
| 新 writer 先提交同 ID | 舊 replace/create-only 的 transaction guard 看見 metadata claim/index 或 safe artifact file，拒絕且不改舊/新 artifact。純 legacy ID 的 replace 行為仍按 R004 characterization 保留。 |
| 任一競態 | 兩方交易鎖決定唯一 winner；反向並行測試驗證兩個 reader 不會同時讀到相同 ID 的兩份結果。metadata claim commit 前進程中斷的 orphan 也由舊 writer 的 safe-path guard 保護，new same-hash retry 可恢復。 |
| 明示 rebuild 遇到併發 save | rebuild 在 writer lock 內讀 inventory 並替換 projection；另 writer 等鎖後保存並索引，或先保存後由 inventory 收錄。SQLite 錯誤回報 `ExecutionIndexRebuildError`，壞 artifact/inventory 回報 `ExecutionArtifactIntegrityError`，兩者保留原始 cause。 |

索引缺 artifact、raw/payload hash 不符、embedded ID 不符、未知 revision、untrusted index name 或 symlink/reparse 均 fail closed。整份 list 遇到任一壞項也不回傳部分結果，以免把損壞索引當有效歷史。

## Legacy 與暫時項目

舊 `RecommendationRepository.save_result` 的 pure-legacy replace、`save_result_create_only`、`load_result`、`list_results` 和 legacy JSON 格式 reader 保留；R004 characterization 通過。canonical ID 已被 claim 時，舊 replace/create-only 現在 fail closed；新 writer 若遇 legacy file-only orphan 也 fail closed，不留下 canonical claim，讓舊 `save_result_create_only` 可用相同 bytes 補 row；回歸測試驗證 orphan bytes 不變且 legacy recovery 成功。舊 reader 不會把 canonical artifact 當 legacy JSON 顯示。新 writer 從未呼叫舊 repository replace/create-only 方法。舊 DTO 保存 coordinator 尚未接線至新 writer；`TMP-REC-03` 保存 caller bridge 的 owner 是 R015，本任務不移除或宣稱已 cut over。

## 驗證（凍結版基準與審查修正後結果）

執行命令及結果：

- `.\.venv\Scripts\python.exe -m pytest tests\test_r004_recommendation_persistence_characterization.py tests\test_recommendation_execution_codec.py tests\test_r012_recommendation_artifact_persistence.py -q -o addopts= -rs`：`65 passed, 3 skipped`（R004 11、R009 codec 18、R012 36 passed；測試時 HEAD `8674cf1451720394fec3017b1450eb2ae12402ba`）。
- 修正後命令 `.\.venv\Scripts\python.exe -m pytest tests\test_r004_recommendation_persistence_characterization.py tests\test_recommendation_execution_codec.py tests\test_r012_recommendation_artifact_persistence.py -q -o addopts= -rs`：`73 passed, 3 skipped`（R004 11、R009 codec 18、R012 44 passed；測試時 HEAD `1cc88ceaa079efdb90f99158558caf158d16ad8a`）。含 coordinator/source-binding 回歸的完整命令 `.\.venv\Scripts\python.exe -m pytest tests\test_r004_recommendation_persistence_characterization.py tests\test_recommendation_execution_codec.py tests\test_r012_recommendation_artifact_persistence.py tests\test_recommendation_capture_source_binding.py tests\test_personalization_save_integration.py -q -o addopts= -rs`：`88 passed, 3 skipped`。三個 skip 仍均為 Windows `WinError 1314`，無建立 symlink 權限。
- 最新共享 HEAD `bcde4094267d013d69a1d113c03f27ce2c64611d` 上，root 獨立重跑本節五檔 focused pytest 組合為 `88 passed, 3 skipped in 7.00s`；R012 `--collect-only` 為 `47 tests collected`。HEAD 相對 `1cc88cea` 的提交僅含 model-repair disjoint paths。
- `tests\test_r012_recommendation_artifact_persistence.py --collect-only -q -o addopts=`：47 個 test cases collected；AST 檢查無重複 top-level test function 名稱，避免 Python 後定義覆蓋先前案例。測試新增 barrier-controlled rebuild/save 並行、legacy orphan → new writer refusal → legacy recovery、artifact/DB/runs 三處大小寫變體配置拒絕、SQLite delete trigger 故障與 inventory store 故障分類。
- `.\.venv\Scripts\python.exe -m mypy --follow-imports=skip --ignore-missing-imports app_module\recommendation\ports.py app_module\recommendation\persistence.py app_module\recommendation\save.py app_module\recommendation\queries.py data_module\result_artifact_store.py`：`Success: no issues found in 5 source files`。
- 對上述 5 個 production files、狹義修改的 `app_module/recommendation_repository.py` 及 R012 test 執行 `py_compile`：exit 0。
- `git diff --check`：exit 0。Git 對其他任務既有的 tracked dirty files 顯示 LF→CRLF warnings；沒有 whitespace error。
- `rg -n "[\t ]+$"` 對 R012 變更 Python/Markdown 檔案無命中。

R012 tests 全部使用 pytest `tmp_path`，覆蓋固定 store layout 與大小寫變體 fail-closed、safe opaque IDs、same/different hash、concurrent create、file/index/metadata-claim failure windows、canonical/legacy orphan reservation、legacy orphan 恢復、stale index rebuild、barrier 控制的 rebuild/save 競態、metadata row recovery/rebuild authority、rename、legacy fixture、save-after-source-change、query integrity failures、legacy→new、new→legacy、兩 writer 競態單一可見 identity、pure legacy replace、data store 無 app import、非 completed 無副作用，以及 SQLite/index vs artifact/inventory error classification。三個 symlink/reparse integration tests 因 Windows `WinError 1314`（目前帳號無建立 symlink 權限）skip；Windows regular-file query 路徑仍經 no-follow handle 執行，但直接 symlink/reparse 測試證據受此環境限制。所有報告內的 JSON/SQLite artifact 路徑均在 pytest temp 目錄；未執行 R013/C1 或正式資料流程。

## 未解風險與 review 項

- Windows `_fsync_directory()` 目前 no-op；payload file `fsync` 不等於已證明 Windows 目錄項目在斷電後持久。現有恢復證據涵蓋程序/應用中斷和同 ID/hash retry，不能宣稱 power-loss durability 已驗證。部署若要求斷電保證，需先完成平台實證/補強。
- Windows handle-level guard 防止檢查後將 artifact root 或 payload entry 換成 reparse point；目前 path-based child operations 假設設定路徑的祖先目錄受應用/OS ACL 保護，不涵蓋能惡意更換祖先路徑的本機攻擊者。symlink tests 因權限 skip，需在允許建立測試 link 的 Windows runner 補跑。
- canonical/legacy 全域互斥依兩邊使用同一 `recommendation_runs.db` 及同一 runs root；部署接線必須維持既有 storage path。R012 未進行 consumer cutover。

上述是待獨立審查的限制，不代表 R012 已取得 PASS。
