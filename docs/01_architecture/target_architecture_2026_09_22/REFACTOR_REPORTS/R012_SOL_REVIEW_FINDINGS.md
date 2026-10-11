> **時點／狀態導覽（2026-10-10）**：本文的 `CHANGES_REQUIRED`、`READY_FOR_REVIEW`、`BLOCKED` 與 Wave／下游 gate 敘述，只代表撰寫當時的 implementer／reviewer／root 裁定，不是目前 disposition；目前 task 狀態看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 及 [final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)，現況看 [Project Snapshot](../../../00_core/PROJECT_SNAPSHOT.md)。原審查結論與限制保留。

# R012 — SOL 凍結版審查發現

REVIEW_STATUS: CHANGES_REQUIRED

凍結版 source/test SHA 依 `R012_IMPLEMENTATION_REPORT.md`；SOL 已逐檔核對 SHA。這份發現針對凍結版，實作者尚未回修。Wave 5、C1 與 Wave 6 仍未放行。

## P1 — stale artifact inventory 可刪除剛保存成功的 index

`RecommendationExecutionPersistence.rebuild_index()` 在未持有 SQLite writer lock 時先掃描 artifact，再呼叫 `ResultArtifactStore.rebuild_index_projection(entries)`。後者在取得 `BEGIN IMMEDIATE` 後直接 `DELETE FROM result_artifact_index`，只插入先前掃描到的 entries。若 B 在掃描 A 後、重建交易前完成保存並返回 `SaveReceipt(index_status=INDEXED)`，重建會把 B 的 index 刪掉；B 的 artifact/metadata 仍在，但 `queries.get("B")` 返回 `None`。這違反已成功保存後可查詢及索引重建的契約。

SOL 在 `tempfile.TemporaryDirectory` 中重現：以 R012 測試 helper 建 stack，先保存 A 並捕捉 `tuple(store.iter_artifacts())`，再保存 B（此時 B 可查），將 `store.iter_artifacts` 暫時改成只產生該舊清單後呼叫 `persistence.rebuild_index()`；B 由可查變為不可查。輸出：`B indexed before stale rebuild: True`、`B indexed after stale rebuild: False`。這等價於實際並行時的舊 inventory；未碰正式資料。

請在 R012 原 scope 內修復重建與保存的並行一致性，補有 barrier 的真並行 regression test，驗證 B 保存完成後仍可查或重建與保存線性化，且既有 stale index-only 清除、metadata 保留、壞 artifact fail-closed 測試仍通過。不得靠每次 query 自動重新算／掃描 artifact 掩蓋缺失。

## P1 — 新 writer 可搶走既有 legacy file-only orphan 的 ID

R004 已明示：舊 `runs/<id>.json` 存在而 `runs` row 尚未建立時，`save_result_create_only()` 對相同 legacy bytes 可補 index，原檔 bytes 不變。R012 新 writer 的 preflight 與 `publish_artifact()` 只檢查 `runs` row、canonical metadata/index 和 canonical safe artifact path；它未檢查既有 legacy JSON 的 file-only orphan。因此同一 ID 的 new save 可建立 canonical artifact/index，後續舊 create-only 的 canonical guard 會永久拒絕原本可恢復的 legacy orphan。舊 bytes 雖未覆寫，但既有 orphan recovery 契約與全域 result_id 身分不再成立。

SOL 在隔離暫存根重現：先以舊 repository 保存 `same-id-after-legacy-orphan`，只刪該 ID 的暫存 `runs` row 以模擬原有故障窗口、保留 `<id>.json`；同 ID 的新 `save_execution()` 回傳 `indexed`，新 query 可見另一份 execution。獨立 Luna 亦核對 `R004` 既有 oracle 與程式路徑。請在 canonical reservation 時對 legacy orphan 安全地 fail closed，讓舊相同 bytes retry 仍能補索引；加雙向格式回歸測試，保留 opaque ID 的路徑安全。

## P2 — POSIX 大小寫別名可繞過共用 DB／artifact 路徑約束

`ResultArtifactStore._validate_config()` 對 `execution_artifacts` 與 `recommendation_runs.db` 使用 `name.casefold()` 比對。POSIX 大小寫敏感檔案系統上的 `runs/Execution_Artifacts` 和 `runs/RECOMMENDATION_RUNS.DB` 因此通過驗證，卻是舊 repository 的 lowercase 路徑以外的另一個 artifact 目錄與 SQLite DB。新舊 writer 不再共用 `BEGIN IMMEDIATE` 鎖，legacy orphan guard 亦看不到新檔；同 ID 全域互斥聲稱不成立。store 本身具有 POSIX open/fsync 分支，不能只按 Windows 大小寫語意解釋。請按實際檔案系統語意強制兩個固定名稱／路徑，加入 case-variant layout 反例，確保在 POSIX 被拒絕而正常 layout 通過。

## P2 — 重建索引時 SQLite 與 artifact 故障被混為一類

`RecommendationExecutionPersistence.rebuild_index()` 將 `ResultArtifactStoreError` 與 `sqlite3.Error` 一律轉成 `ExecutionArtifactIntegrityError`；其中包含 store 的 `ResultArtifactIndexError`。R012 驗收要求 JSON/SQLite failure 可辨，重建命令不能把 DB transaction failure 宣稱為 artifact bytes／schema 損壞。請區分重建期間的 index I/O error 與 artifact integrity error，保留原 cause，補注入測試。`iter_artifacts()` 的 store 錯誤也應通過 app 層一致分類。

## 已驗證但非放行

- 凍結版 R004＋R009 codec＋R012：`65 passed, 3 skipped`；3 個 skip 都是此 Windows 帳號無權建立暫存 symlink (`WinError 1314`)，不是 PASS。
- 舊 save coordinator、DTO roundtrip、capture source binding：`11 passed`。
- R012 改動 Python `py_compile` 與五個新 source 的 scoped mypy 均通過。
- 正式獨立 Luna 全面審查與 ML/codec 窄審查仍在進行；它們可能增加同批修正項。
