# C1 Persistence / Query 實作報告

TASK_STATUS: `U4_ACCEPTED_FOR_U5`  
C1_STATUS: `NOT_PASSED`  
WAVE6_STATUS: `BLOCKED`  
OWNER: `Luna Max — U4 持久化／查詢`

## 獨立複審與簽收

REVIEW_STATUS: `Accept U4 only`  
SOL_STATUS: `U4_ACCEPTED_FOR_U5`

獨立複審依 61 passed / 4 skipped、codec 21 passed、py_compile 與 scoped mypy 通過結果簽收 U4。複審提出的三項 blocker 均已修復並由測試涵蓋：

- canonical index 與 artifact 缺失時，仍檢查 metadata-only identity claim；claim 存在或 metadata 讀取失敗都拒絕 legacy fallback。
- ML receipt projection row hash 強制一對一、唯一且與 execution projection references 相符；不同 receipt refs 複製相同 row hash 時回傳 `unavailable` 與空 rows。
- 無 unique constraint 的 legacy `runs` table 若含重複 result ID，單筆 `get()` 會 fail closed。

獨立複審結論：無剩餘 P0/P1/P2。此簽收僅涵蓋 U4；U5 尚待驗證，C1 仍為 `NOT_PASSED`，Wave 6 仍為 `BLOCKED`。

## 完成範圍

- `RecommendationExecutionPersistence.save()` 維持 create-only，且只寫入目前 revision（rev2）。它會驗證輸出的 envelope revision，沒有新增 legacy writer。
- Canonical 讀取使用 U2 `decode_execution_envelope`。Envelope 保留 rev1/rev2 來源 revision、payload hash、raw SHA-256 與原始 bytes；query view 提供來源 schema revision 及兩種 hash。讀取不會重新編碼歷史 execution。
- 重建 index 時會記錄 artifact header 中讀到的 revision。Canonical payload、raw hash、schema 或 revision 不一致時會 fail closed。未知 schema revision 仍由 codec 拒絕。
- `RecommendationExecutionQueries.get/list` 是 canonical rev1/rev2 與無 header legacy runs 的統一讀取 seam。Canonical artifact 存在但 index 缺失時，不會退回 legacy；canonical 與 legacy 的重複 ID 會 fail closed。
- 即使 canonical index 與 artifact 都不存在，只要 metadata table 已有同 ID 的 canonical identity claim，query 也會 fail closed；讀取該 identity metadata 發生錯誤時同樣拒絕 legacy fallback。
- Legacy SQLite `get(result_id)` 最多取兩列；若舊 `runs` table 沒有 unique constraint 且相同 ID 有多列，會 fail closed，不會任意回傳第一列。`list()` 也會拒絕重複 ID。
- Production legacy 路徑是透過既有 `runs(result_id, data_path, ...)` table 的唯讀 SQLite/raw-byte adapter。它不會建立 `RecommendationRepository`、呼叫會吞例外的 `load_result()`、建立 schema，或寫入舊結果 bytes。Adapter 會驗證檔案位於精確的 `runs/<result_id>.json` 範圍內、SQLite/result identity 一致、檔案為一般檔案，且路徑沒有 symlink/reparse point。Query 在回傳前會再讀一次舊 bytes，並要求路徑與 bytes 都一致。
- Legacy 格式分派只經過 U2 `decode_artifact`，query 沒有新增自己的 JSON decoder。若沒有明確提供獨立 expected SHA-256，會以 read-time digest 識別並解碼本次讀到的 bytes；view 標示為 `legacy_read_time_hash_only`。若提供 trusted hash 但不相符，則 fail closed；只有 hash 相符後才標示為 trusted。
- ML view 只透過 `read_inference_projection_receipt` 讀取已保存的 immutable receipt。Query 會驗證 receipt reference/hash、execution 的 result/candidate/date/cost 綁定、projection row hash reference，以及 projected stock code 的精確順序。驗證通過的保存 rows 在 view 中不可變。讀取時不載入模型、不執行 inference，也不重算。缺少 receipt binding 且 execution 狀態為 unknown 時回傳 `unknown`；已綁定但驗證失敗則回傳 `unavailable`、附 diagnostic，且不提供 rows。
- 每個 receipt binding 必須與唯一 execution projection row hash 一對一相符；binding 數、hash 唯一性與 hash 集合都會交叉驗證。不同 receipt reference 若重複綁定相同 row hash，view 標為 `unavailable` 並回傳空 projection rows。

Canonical 結果的 read view 提供 `execution`，legacy DTO 則由 `legacy_result` 提供，另有 `result` 便利屬性。View 也提供來源 revision、payload/raw hashes、integrity basis、ML read status/projections，以及供下游使用的 diagnostics。

## 合成 fixture pin 與 readback

Fixture manifest 只固定測試輸入。特別是其中的 legacy SHA 並不是 production trust authority。

| Fixture | Bytes | 來源 revision | Result ID | SHA-256 |
|---|---:|---:|---|---|
| `r016_execution_rev1.json` | 5,033 | 1 | `rev1:baseline/0007 ` | `sha256:dbd3c2194ef53c2fee3e41e772187d2453c52237328aa179833282e0cc76a52b` |
| `r016_execution_rev2.json` | 4,302 | 2 | `c1-r016-rev2` | `sha256:0ef36ebabc8277ed5cf27a764dc359164cb3e27a6bc8d41111b4426f7e04e2f2` |
| `r016_legacy_run_zh.json` | 469 | 無 header | `c1-r016-legacy` | `sha256:f625d43792688b35beb78ea1e93e965e79858ee94293c786351d6511f9de5552` |

Readback 測試確認 rev1/rev2 來源 revision 在 index rebuild 與 query 後仍保留，payload/raw hashes 與原始 envelope 相符，artifact bytes 也未改變。Legacy 測試比較 pinned test bytes、query 前後的 raw bytes，並核對預設完整性標記為 read-time-only。另有明確 expected-hash 測試確認匹配的 trusted hash 會標為 trusted，而 mismatch 會 fail closed。新增負例驗證 metadata-only canonical claim、metadata query failure、無 unique constraint 的 duplicated legacy rows，以及兩個不同 receipt paths 複製同一 receipt 與 row hash 時回傳 `unavailable`/空 rows。預設 production adapter 沒有 trusted-hash map。

## 驗證

執行命令與結果：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_r012_recommendation_artifact_persistence.py tests\test_c1_legacy_query_readiness.py -q -rs -o addopts=
61 passed, 4 skipped

.\.venv\Scripts\python.exe -m pytest tests\test_recommendation_execution_codec.py -q -o addopts=
21 passed

.\.venv\Scripts\python.exe -m py_compile app_module\recommendation\persistence.py app_module\recommendation\queries.py tests\test_r012_recommendation_artifact_persistence.py tests\test_c1_legacy_query_readiness.py
passed

.\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module\recommendation\persistence.py app_module\recommendation\queries.py
Success: no issues found in 2 source files
```

以相同 focused pytest 命令加 `-rs` 查看 skip 原因後，4 個 skip 都是執行環境無權建立暫存 symlink（Windows `[WinError 1314] A required privilege is not held by the client`）：

- `test_r012_root_and_file_symlinks_fail_closed`：無法建立暫存目錄 symlink。
- `test_r012_symlinked_artifact_is_not_followed`：無法建立暫存檔案 symlink。
- `test_r012_windows_artifact_reparse_is_rejected_by_open_handle`：Windows 測試同樣因無法建立暫存檔案 symlink 而 skip。
- `test_c1_legacy_reader_rejects_symlinked_result_file`：無法建立暫存 legacy result symlink。

另外也以預設遞迴 mypy 檢查兩個 U4 source files，但在非 U4 檔案發現 6 個錯誤：`app_module/recommendation/contracts.py`（2 個）、`analysis_module/technical_analysis/technical_indicators.py`（3 個）及 `app_module/update_service.py`（1 個）。沒有 U4 source file 被報錯。這些無關錯誤未修改。

## 信任邊界與後續 gate

- Read-time SHA-256 不是歷史完整性證據。Production legacy 結果若沒有獨立保存的 expected hash，就無法偵測本次讀取以前發生的變更。
- Manifest 中的 synthetic legacy hash 只作為測試 pin。Production trust 必須由呼叫端明確注入、且另行受控的 expected-hash mapping。
- Receipt 缺失與 receipt 驗證失敗是不同狀態：沒有 binding 且 availability unknown 時回傳 `unknown`；已存在但無效的 binding 回傳 `unavailable`，不會改用其他來源。
- 未讀取或變更正式 `DATA_ROOT` 資料。未修改 `data_module/result_artifact_store.py`、codec/contracts/execute/service、scheduled wrapper、producer、ML implementation 或 legacy writer。未 stage、commit 或 push 任何檔案。
- U4 已由獨立複審簽收，可進入 U5；U5 尚待驗證。此簽收不代表 C1 通過，也不會解除 Wave 6。
