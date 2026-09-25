# R026 市場修訂 namespace 證據身份決策附錄

**日期：** 2026-09-24
**狀態：** 僅 `market_revision` namespace bounded checker slice 已由 root 依獨立複核判為 `ACCEPTED_SCOPE`；root fresh TEMP 五檔 route 為 62 passed。本文只裁決此 namespace 的 role identity 與讀取邊界，不涵蓋其他 namespace 或跨 namespace aggregate；R026 整體與 `TMP-ML-01` 仍 open，也不代表 ML cutover 完成。
**關聯：** [R026 實作報告](R026_IMPLEMENTATION_REPORT.md)、[R026 跨資源 source revision identity 決策附錄](R026_SOURCE_REVISION_IDENTITY_DECISION_ADDENDUM_20260924.md)、`REFACTOR_TASKS/R026.md`、`data_module/contracts/source_revision.py`。

## 決策範圍

本附錄只處理 `data_module/formal_market_revision.py` 掃描的 `formal_market_repair_receipts/<run>/revision.json` 鏈，及如何把該次完整檢查表示成 `ValidatedNamespaceEvidenceV1`。它不裁決 historical session、excluded daily-price、direct repair receipt 的 capture 實作，也不建立四個 namespace 的共同交易或 durable generation。

目前 `assert_market_revision_safe(database_path, decision_date) -> None` 維持既有公開簽章、import 路徑、回傳型別及 `ValueError` 阻擋行為。後續可新增內部 capture helper，供 R026 消費不可變的 namespace evidence；既有 assertion 仍作薄 wrapper，呼叫 helper 後丟棄 evidence。不得讓舊呼叫端突然收到 evidence 物件，亦不得以 `None` 同時代表明確空集合與 identity 不可用。

## Role identity：以相對 run path 編碼

每個 `role_id` 以 receipt root 下的相對 run-directory path 識別來源，再以 UTF-8 無 padding base64url 編碼為安全 ASCII path segment。建議形狀如下：

```text
runs/run_<base64url(relative_run_path)>/revision.json
runs/run_<base64url(relative_run_path)>/journal.json
runs/run_<base64url(relative_run_path)>/plan.json
runs/run_<base64url(relative_run_path)>/receipt.json
runs/run_<base64url(relative_run_path)>/rollback.json
```

`relative_run_path` 從固定的 `formal_market_repair_receipts` 根目錄計算；只將路徑分隔符正規化為 `/`，不含磁碟機、絕對路徑或資料根目錄。UTF-8 位元組經 URL-safe base64 編碼後移除 `=` padding，並加 `run_` 前綴。此字元集符合現有 `source_revision.py` 的 ASCII role-ID 格式。即使相對名稱含空格或非 ASCII 字元，編碼後仍是可驗證的安全 segment。

不得使用排序後的 `runs/0000/...` ordinal，也不得以內容 hash 代替 role identity。加入較早排序的 run 不得重新命名既有角色；不同 run 即使檔案 bytes 完全相同，也必須保留不同 role ID。內容 SHA-256 仍記錄在各 `ValidatedEvidenceFileV1`，負責表示 bytes 身分；role ID 表示該 bytes 在 namespace 中的來源位置。

路徑大小寫照檔案系統列舉出的相對 run path 保留，不一律轉小寫，避免在大小寫敏感檔案系統上合併不同 run。絕對 root 的別名或大小寫不進入 role ID；root／資料庫範圍由外層 `scope_id` 綁定。若未來允許多層 run path，整個相對 POSIX path 一起編碼，不得逐段混用排序序號。

## Presence 與 fail-closed 語意

- **EMPTY**：只有在 receipt root 成功且完整列舉，確認沒有 `revision.json` 時才成立；回傳空的 `ValidatedNamespaceEvidenceV1`。
- **PRESENT**：至少一個 revision chain 已完整驗證。合法的 `pending`、`applied` 但來源起始日晚於 cutoff、以及 `rolled_back` 都仍是 PRESENT；它們表示有經檢查的修訂紀錄，是否阻擋 PIT 是另一項判定。
- **阻擋或驗證失敗**：cutoff 已落入會阻擋使用的修訂範圍、marker／chain 格式未知、required file 缺失、hash/link 不符、讀取或完整列舉失敗、路徑逃出 receipt root，均不得回傳 EMPTY 或部分 evidence。保留舊 assertion 的 `ValueError` fail-closed 行為。

Capture helper 應先在區域變數累積所有 marker 的驗證結果；必須完成整個 namespace 的列舉與所有 chain 驗證，且沒有 cutoff blocker，才能回傳 PRESENT／EMPTY。第二個 run 失敗時，不得讓第一個有效 run 的部分 evidence 外洩。

## 單次 bytes 的 hash 與解析

每個檔案都以單次 `read_bytes()` 得到不可變 bytes；hash 與任何解析、欄位比對及鏈結驗證都使用同一個 bytes buffer。不得先讀文字解析、再重開檔案計算 hash，也不得重讀後把第二份 bytes 當作已解析內容的 identity。role/hash 對照如下：

| 狀態 | 本次 chain 應捕捉的角色 |
| --- | --- |
| 所有有效狀態 | `revision.json`、`journal.json`、`plan.json` |
| `pending` | 不期待完成 receipt；若協定要求不存在 receipt，必須在 writer contract／測試中明確固定，不把缺 receipt 當作 namespace 空集合 |
| `applied` | 再捕捉並驗證 `receipt.json`，保留 marker→receipt→plan 及 journal→plan 的既有 hash/link 檢查 |
| `rolled_back` | 再捕捉 `rollback.json`，保留 marker 宣告之 rollback SHA-256 驗證 |

Root 裁決：market `rollback.json` 維持既有 hash-only/link 驗證；本 slice 不新增 JSON parsing、rollback schema 或 required-field rejection。其實際讀取的單一 bytes buffer 以 marker 宣告的 hash-link 驗證後，可記入 `ValidatedEvidenceFileV1`。該契約 docstring 已明確容許 namespace 既有 JSON parser 或已比對 hash-link 驗證；因此不會把 rollback body 誤稱為已解析或語意驗證。其他既有會解析的檔案仍須以同一 bytes buffer 完成 hash 與解析。此裁決不改寫既有 rollback bytes，也不宣稱多檔原子性。

Marker/journal/plan/receipt/rollback 的 bytes hash 全部納入 namespace evidence。只有被實際讀取且依該狀態驗證的檔案才列入；每個 run 的所有檔案角色分開保存，不以相同 hash 去重。

## Windows 路徑與 junction containment

Evidence capture 的固定 receipt root 與每個實際讀取的 marker／child file 都必須檢查 resolved path 仍位於該 resolved root 內。不可只用 `Path.is_symlink()` 作邊界判定。隔離 TEMP 探針在 Windows、Python 3.11.9 以 Junction 建立 `link` 後觀察到：`Path.is_symlink()` 為 `False`、`Path.is_dir()` 為 `True`，而 `Path.resolve()` 會追到 Junction target。因此必須以 resolved containment 判斷逃逸；若 `resolve()` 到 receipt root 外，就 fail closed。

role ID 仍取自列舉到的 lexical relative path，不取 resolved target path；否則 Junction target 會讓角色跨 namespace 改名或暴露絕對環境路徑。本 slice 明確接受單一 lexical run alias 指向固定 receipt root 內的巢狀 run 目錄，前提是 resolved target 留在 root 內，且實際讀取檔案的前後 resolved path identity 不變；role 仍以 alias path 編碼。若兩個 immediate run entry 指向同一 resolved run，仍 fail closed。root 外 symlink／junction 一律拒絕。receipt-root 祖先或 child file 的 root 內連結不在這個相容性裁決範圍內，不宣稱已個別驗證。

## 最窄 red/green 驗收清單

1. **Role identity**：相同目錄重複執行與反向列舉產生相同 role IDs／digest；新增排序更早的 run 不改既有 IDs；同 bytes 位於不同 run 時保留兩組 IDs；空格／非 ASCII run name 經 UTF-8 base64url 後符合 role-ID 格式。不得出現 ordinal 或絕對路徑。
2. **Presence 與狀態**：完整無 marker 得 EMPTY；合法 before-cutoff `pending`／`applied` 及 `rolled_back` 得 PRESENT；cutoff blocker 不回 evidence；未知 marker／journal／plan／applied receipt schema、未知狀態、缺檔、壞 hash、壞 link、無法完整列舉均 fail closed。`journal.json`、`plan.json` 與 `applied receipt.json` 必須是 writer 的 `formal-market-repair.v1`；rollback 維持 hash-only，不要求 schema。
3. **同一 bytes**：用受控讀取 hook 證明 hash 與 parser 收到同一 buffer；讀取後立刻改變路徑上的檔案，不得讓第二次讀取改變已捕捉摘要或讓 parser/hash 分別消費兩個版本。測 marker、journal、plan 與 state-specific terminal file。
4. **無部分結果**：多 run 中先有一條有效 chain、後有一條壞 chain時，helper 不回傳部分 namespace。舊 assertion 仍只回 `None` 或拋 `ValueError`，cutoff 決策與既有 import／簽章不變。
5. **路徑邊界**：TEMP 內部正常路徑通過；外部 symlink／Windows junction resolve 到 receipt root 外時拒絕。`is_symlink()` 單獨判斷須有反例。單一 run-level alias 指向 root 內巢狀 run 時接受並保留 lexical role；兩個 immediate run alias 指向同一 resolved target 時拒絕。receipt-root 祖先與 child-file 內部連結未由本 slice 個別授權或驗證。
6. **Rollback 相容**：以既有 rollback fixture／artifact 固定 hash-only baseline；匹配的 marker hash-link 通過、不匹配時 fail closed，且不解析 rollback body、不要求新欄位、不改寫 artifact bytes。

## 未解限制與實作前確認

- 單次 buffer 保證 hash 與 parser 指向同一份已讀 bytes；它不使多個 JSON 檔案成為同一個原子 snapshot，也不偵測 bytes 在不同檔案讀取間被協調更新後形成的有效混合鏈。
- 前後兩次 evidence 比對仍有 ABA 窗口；若 writer 可在兩次檢查間改寫再還原 bytes，僅靠 pre/post digest 不保證偵測。需共同 writer lock、durable generation 或不可變 artifact 才能提出更強承諾。
- 此 market namespace slice 不提供 historical-session、excluded-price、direct-receipt identities，也不證明跨 namespace／跨 provider calls 同版本。四 namespace aggregate、`PreparedMLInput.source_revision` 接線、invocation-wide consistency 與 model pointer 綁定仍是後續 R026 gates。
- 已由本 slice 固定：base64url role 編碼規格、root 外連結拒絕、單一 root 內 run alias 接受、重複 resolved run alias 拒絕、namespace 掃描失敗與真正空集合的區別、既有 assertion 消費者與 monkeypatch 測試的回歸範圍。receipt-root 祖先／child-file 的 root 內連結行為仍未個別驗證。

因此本文記錄 role identity 與 namespace capture 的設計決策及其 bounded Slice 3 實作；該 collector 已回傳經本次 checker 驗證的 typed market namespace evidence。它不提供四 namespace aggregate、不宣稱 R026／`TMP-ML-01` 已完成，也不授權 ML inference cutover。
