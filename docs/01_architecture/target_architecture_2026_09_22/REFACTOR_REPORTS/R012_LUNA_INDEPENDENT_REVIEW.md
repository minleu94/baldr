# R012 Luna 獨立唯讀審查

> **時點／狀態導覽（2026-10-11）：** 本文的 `CHANGES_REQUIRED` 是第一版凍結內容的歷史 finding；後續 [R012 Luna 回修複審](R012_LUNA_REWORK_REVIEW.md) 與 [SOL 整合驗收](R012_SOL_INTEGRATION_ACCEPTANCE.md) 記錄四項 finding 已按 bounded scope 回修並通過 R012 gate。目前 R012 disposition 以 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 為準。原 findings、skip 與未放行聲明保留為歷史證據，不代表目前仍有相同 blocker，也不宣稱整體 refactor 通過。

**結論：`CHANGES_REQUIRED`。** 此審查針對 worker 凍結 SHA，並核對 R012 spec、FINAL §6.2、FINAL_DATA_FLOW §3、INV-01/10/12/17、R004 characterization，以及 R009 codec contract。未修改實作或測試。以下兩項資料完整性問題需修正並補上回歸測試；目前不放行 C1 或 Wave 6。

## 凍結版本與驗證

下列凍結檔案雜湊與派工提供值相符：ports `C4F0BCBF`、persistence `8DBEF496`、save `7C84ABD5`、queries `2B6962BF`、store `D1D31ACF`、legacy repository `35672320`、R012 tests `2D88B4FD`。實作報告 `68996263`、rollback note `B4F17AB1`。

唯讀 focused tests：

```text
tests/test_r004_recommendation_persistence_characterization.py
tests/test_recommendation_execution_codec.py
tests/test_r012_recommendation_artifact_persistence.py
65 passed, 3 skipped
```

三個 skip 均因 Windows 環境無法建立 symlink（WinError 1314），涵蓋 root/file symlink 與 reparse-link 情境。因此目前有一般 Windows 路徑測試，但沒有成功建立 link 的正向 reparse 行為證據。

## Findings

### P1 — index rebuild 的 stale inventory 會刪除已成功提交的另一 writer

`app_module/recommendation/persistence.py:302-324` 先在沒有 SQLite writer transaction 的情況下掃描 artifacts，再把快照交給 store。`data_module/result_artifact_store.py:926-930` 取得 `BEGIN IMMEDIATE`；其後 `:943-960` 清空整個 projection，只重插先前快照。

可重現順序：rebuild 掃到 A；另一 writer 完成 B 的 artifact、metadata claim 與 index commit，並回傳 `INDEXED`（`result_artifact_store.py:400-476,682-794`）；rebuild 接著取得鎖並以只有 A 的舊快照替換 projection。B 的檔案和 metadata claim 還在，但 SQLite index row 被刪除，`get(B)` 不再可見。沒有錯誤回報，也沒有要求成功的 B writer 重試。這違反 INV-12 的 index 可重建性及成功保存後可查詢契約。

**修正／驗收：** inventory 與替換必須避免此 lost update（例如將 writer 序列化覆蓋到完整 inventory/replace 流程，或在 replace 時重驗並保留掃描期間已 claim 的 artifacts）。加入可控交錯測試：先掃描只含 A 的快照，完成 B 的 `INDEXED` 保存，再執行該快照的 replace；斷言 B 仍可查詢，且重建結果符合實際 artifact inventory。

### P1 — canonical writer 接受 legacy file-only orphan，會封死 R004 同 ID recovery

R012 保留 legacy orphan recovery（`REFACTOR_TASKS/R012.md:29-32`）。R004 characterization 明確要求僅有舊 `runs/<id>.json`、無 `runs` row 的檔案可透過既有 `save_result_create_only` 同 ID 恢復，並保留原始 bytes（`tests/test_r004_recommendation_persistence_characterization.py:328-343`）。

canonical preflight 只查 canonical metadata/index 及 legacy `runs` row（`app_module/recommendation/persistence.py:205-210`）；store reservation 也只查 legacy row 與 canonical metadata（`data_module/result_artifact_store.py:415-428`），不檢查 `runs/<id>.json`。因此當舊 orphan 存在時，新的 canonical save 可用相同 ID 回傳 `INDEXED` 並建立另一份 canonical artifact。此後舊 `save_result_create_only` 因 canonical identity guard 而拒絕（`app_module/recommendation_repository.py:134-160,353-367`），使既有 legacy orphan 無法按 R004 契約復原。舊 bytes 雖未被覆寫，卻出現同一 ID 兩份互相排斥的保存身分，且恢復路徑被 canonical claim 永久封住。

**修正／驗收：** canonical reservation 應將既存 legacy orphan 視為該 ID 已被占用，保留原檔並拒絕建立 canonical claim，讓既有 legacy recovery API 可處理；或定義並實作能無損轉移 orphan 所有權的明確流程。回歸測試需建立 legacy create-only 檔案、刪除其 `runs` row（只在臨時測試資料根目錄），嘗試 canonical 同 ID save，並驗證不會回傳成功且舊 bytes 可由 legacy API 原樣 recovery。此例已由 root 以 tmp-only repro 確認。

## 其他驗收風險與限制

- **P2 — 大小寫路徑別名可繞過同一儲存根目錄約束。** `data_module/result_artifact_store.py:112-127` 用 `casefold()` 驗證名稱；在大小寫敏感檔案系統上，`runs/Execution_Artifacts` 或 `runs/RECOMMENDATION_RUNS.DB` 與 legacy 的精確小寫路徑是不同物件。POSIX 路徑程式存在於 `:323-340,490-498`；legacy 使用固定小寫路徑（`app_module/recommendation_repository.py:83-89,152-160`）。若這些大小寫變體可配置，兩 writer 可能使用不同 DB lock、檔案 guard 也可能檢查錯誤位置。配置測試目前只驗錯誤 basename，未驗大小寫變體（`tests/test_r012_recommendation_artifact_persistence.py:221-266`）。應依 host filesystem identity 拒絕非精確名稱或做正規化，並補 POSIX case-sensitive 測試；若產品明確限定 Windows，須在架構限制中寫明，避免跨平台保證含糊。
- **P2 — rebuild 的 SQLite write failure 被誤分類為 artifact integrity failure。** `rebuild_index()` 把 store/SQLite 錯誤統一包成 `ExecutionArtifactIntegrityError`（`app_module/recommendation/persistence.py:323-326`），但 store 對 projection DB 錯誤回報 `ResultArtifactIndexError`（`data_module/result_artifact_store.py:951-952`）。這與 R012 要求可區分 JSON 與 SQLite failure（`REFACTOR_TASKS/R012.md:58-60`）不符，也會把可重試的 index 寫入故障呈現為 artifact 損毀。加入注入 DB write failure 的 rebuild 測試，驗證保留 index/storage failure 分類。
- **具名限制，非本次阻斷：** POSIX hard link 已建立但 parent-directory fsync 失敗時，`artifact_published` 尚未設為 true（`data_module/result_artifact_store.py:461-475`），流程回報 publish/write error（`:491-496`；app mapping 在 `app_module/recommendation/persistence.py:261-262`），但目錄中可能已存在未索引 artifact。該 artifact 的 durability 未獲證明、也沒有 `INDEXED` receipt；相同 ID/hash 重試可驗證並恢復。因此錯誤契約或文件不得宣稱此情況保證「沒有檔案」，但現有流程本身不足以判為 R012 阻斷。
- **具名限制：** 三項 symlink/reparse 測試因 WinError 1314 skip，故沒有 Windows reparse link 成功建立後的實測證據。不要把這些 skip 算作通過；在允許 symlink 的 Windows runner 補跑後再記錄結果。此限制本身不是對抗式本機 TOCTOU 攻擊的架構 blocker；本次未找到足以要求改設計的證據。

## 已核對且目前無阻斷證據的範圍

- 精確既定 Windows paths 下 canonical/legacy writers 都先取得 `BEGIN IMMEDIATE` 再檢查對方身份與寫入（`app_module/recommendation_repository.py:264-316,350-404`；`data_module/result_artifact_store.py:400-488`）；artifact 使用 exclusive hard-link publish，canonical metadata claim 先於獨立 index transaction。相同 ID 的兩個 canonical writers 在一般競爭下會序列化；metadata claim 失敗留下的 orphan 可由同 hash retry 回收。
- 保存入口拒絕 FAILED/CANCELLED（`app_module/recommendation/persistence.py:185-188`）；new writer 不呼叫 legacy replace API（測試 `tests/test_r012_recommendation_artifact_persistence.py:883-897`）。codec receipt/reference bytes 與 R009 contract 有測試覆蓋（同測試 `:177-200`）。
- SQLite query/index projection 可從 artifact inventory 重建；metadata claim 是持久權威資料，不是可由 artifact bytes 推回的欄位。整個 SQLite DB 遺失時 persisted label/notes/timestamp 會遺失（`app_module/recommendation/persistence.py:295-327`；測試 `tests/test_r012_recommendation_artifact_persistence.py:715-749`）。這與 FINAL §6.2 / INV-12 將 SQLite index 稱為 rebuildable 的最窄一致解讀相符：僅 query/index projection 保證可重建，不是宣稱 SQLite 中全部資料可由 artifacts 重建。
- legacy replace 若 JSON write 完成、SQLite commit 失敗，舊 metadata 配新 DTO 的失敗窗由 R004 characterization 明確記錄（`app_module/recommendation_repository.py:296-320`；`tests/test_r004_recommendation_persistence_characterization.py:548-588`）。這是舊 writer 已知行為，不是新 canonical writer 覆寫 artifact；本次建議不要以改寫 R004 semantics 擴大 R012 scope。
- 此變更維持 R012 的新增 API／窄 legacy guard 範圍；尚未做消費者 cutover，符合移交由 R015 負責的安排。R012 不構成 C1 或 Wave 6 放行依據。
