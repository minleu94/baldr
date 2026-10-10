> **歷史 Wave checkpoint**：本文只記錄當時的依賴與有限釋出狀態，不提供目前的 release 或派工授權。後續 C1／Wave 6 裁決見 [C1 checkpoint](C1_CHECKPOINT.md) 與 [Wave 6 最終 gate 報告](WAVE6_FINAL_GATE_REPORT.md)；目前狀態看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)。

# Wave 5 checkpoint — persistence

CHECKPOINT_STATUS: PASS

唯一任務 R012 已有實作者報告、獨立 Luna 回修複審 `REVIEW_STATUS: PASS` 與 SOL [整合驗收](R012_SOL_INTEGRATION_ACCEPTANCE.md)。create-only、same ID/hash 冪等、異 hash 衝突、兩 writer 競爭、artifact-only/legacy orphan 恢復、partial index 補登、legacy read/list/replace 與 metadata-only rename 均有隔離測試。索引重建與新保存共用 SQLite writer lock；新保存不使用舊 replace API。R004＋codec＋R012 為 73 passed、3 個具名權限 skip；含 capture/personalization 的擴大組合為 88 passed、3 skip。沒有正式 schema apply 或原始/歷史 artifact 變更。

架構方向維持 app use case → codec/port → data store；data store 無 app import，save/query 不讀 live `last_*`。TMP-REC-03 仍由 R015 退休；legacy decoder 與舊資料讀取屬永久相容路徑，不等同第二套推薦計算。Windows symlink/reparse 正向測試因 WinError 1314 未執行、目錄斷電耐久未實證，已在 R012 驗收具名列明。

C1 hard gate 尚未執行。Wave 6 不因本 checkpoint 單獨釋出。
