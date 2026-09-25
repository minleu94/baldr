# R012 schema publication 與 rollback note

本 note 僅涵蓋 R012 的兩張 additive SQLite table：

- `result_artifact_index`：由已驗證 immutable artifact 重建的 query projection。
- `result_artifact_metadata`：mutable `label`、`notes`、`persisted_at` 與 ID/payload-hash identity claim 的權威位置。

兩表沿用既有 `recommendation_runs.db`，沒有正式 data migration。import、app startup、query/list 不建立 DB/schema；只有明示 `RecommendationSaveService.save_execution()` writer 可建立表。writer 的 index projection transaction 永遠在 payload create-only publish 後執行。Metadata claim 也只在 payload publish 後 commit；其 SQLite writer lock 用來與舊 `runs` writer 互斥，避免同 ID 雙重可見。

store constructor 與每次 operation 固定要求大小寫精確的同一 `runs/execution_artifacts/` + `runs/recommendation_runs.db`；POSIX 大小寫變體不代表相同 namespace，會在路徑建立前拒絕。部署仍須將此既有 runs root/database 與舊 `RecommendationRepository` 對齊。canonical writer 在同一 SQLite identity reservation transaction 中也檢查舊 `runs/<result_id>.json` orphan；遇到 orphan 時 fail closed，保留原 bytes 供 `save_result_create_only()` 復原。artifact inventory 與 projection replacement 共用 `BEGIN IMMEDIATE`；併發 save 會被線性化，不會被舊 inventory 清掉。

若只需回滾程式且尚無正式 artifact，移除 R012 新入口即可；測試生成物在 `tmp_path`。一旦任何非 tmp 環境已有 canonical artifact 或 metadata claim，回滾只能停止新 writer 並保留 artifact、metadata、SQLite tables 及其 reader；不得刪除 artifact、清空 index/metadata、或讓舊 replace 接管相同 ID。需要另行審查 reader/decoder 支援和資料處置後，才能做資料移除或格式轉換。

`result_artifact_index` 可從 artifact 重建；`result_artifact_metadata` 是可變權威，不在 artifact 內。若 SQLite DB 整體遺失，label、notes、persisted_at 無法復原；projection rebuild 只會恢復 identity/hash/schema 欄位並讓缺失 metadata 顯示為 unknown，不偽造原值。

Windows 目前以 handle-level reparse 檢查保護 artifact root/payload entry，但目錄 fsync 不提供經驗證的斷電 durability。正式啟用 writer 前若要求 power-loss durability，需補 Windows 平台證據或決議可接受的恢復保證；此限制不得以一般程序中斷測試代替。
