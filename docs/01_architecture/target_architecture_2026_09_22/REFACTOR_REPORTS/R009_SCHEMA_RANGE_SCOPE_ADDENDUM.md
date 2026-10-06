# R009 schema revision 支援範圍落點補充裁決

STATUS: APPROVED_NARROW_SCOPE_ADDENDUM

## 證據與裁決

`FINAL_TARGET_ARCHITECTURE.md` §6.1 明定 `EXECUTION_SCHEMA_REVISION` 與支援 revision 範圍固定宣告於 `app_module/recommendation/contracts.py`。R009 第一輪把支援範圍只定義在 `codec.py`，使契約 owner 沒有明示相容範圍；獨立 reviewer 依權威架構提出此落點缺口。先前同一輪的 additive revision 測試亦證明 codec 不能只接受目前 revision。

此裁決只為實現原定 R009 codec 版本 dispatch，**不重設架構、不改已封存欄位或數值語意**。R009 worker 除原 scope 外，僅可在 `app_module/recommendation/contracts.py` 增加明確的 `SUPPORTED_EXECUTION_SCHEMA_REVISIONS: tuple[int, ...] = (1,)`，讓 codec 從該契約匯入並驗證。若需以其他等價名稱，須在報告列明。不得改 `EXECUTION_SCHEMA_REVISION`、`schema_version`、其他 R008 contract 欄位、validation、parent export 或既有測試 golden。

R009 必須補測：目前 revision 1 接受；未知 0/2 拒絕；模擬未來 contract 同時宣告 current revision 2 與 supported `(1, 2)` 時，舊 revision 1 缺 optional 欄依 default 讀回。新增 optional scalar 時的修改仍只落在 owner contract、root revision 與明示支援範圍，不逐欄修改 codec。

R008 contract SHA 因此會改變。SOL 須核對此窄 diff、重跑 R008 contract/import 聚焦測試並記相依勘誤；R009 獨立 reviewer 依新 SHA 複核。R010 worktree 必須在自身修正完成與凍結前同步新的 contract bytes，重新驗證其相依 SHA 與測試。Wave 3 在上述檢查完成前仍為 `IN_PROGRESS`，不得放行 R011。
