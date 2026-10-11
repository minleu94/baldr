# 分支與工作樹整理紀錄（2026-09-27）

> **截至 2026-09-27 整理完成時的歷史快照**：refs、worktree 數量、髒檔案與本機分支狀態不代表目前狀態；本文僅留作該次操作的依據與復原紀錄。

本紀錄列出本機 `dev` 歷史整理的依據與復原位置。未推送、未修改遠端分支；19 個 worktree 目錄與髒檔案均保留。

## 已執行變更

- `main` 保持 `1bedee9aff0be2a375f90eb677911cb029688339`。
- 整理前 `dev` 為 `cb486ee03c625583cdae87eb75630a7e04b51187`，tree `63b08037e74c38d8eeda3adf9bd515c21c68dfa8`。
- 將四個已審查分支以單一 `--no-ff -s ours` 歷史提交併入 `dev`：`758e90108749d60bc1f24b834f07bb6a1b387fdd`。五個 parent 為整理前 dev 與四個候選分支；前後 tree hash 相同，沒有把分支檔案內容覆蓋到 dev。歷史合併完成時 dev 相對遠端追蹤分支 ahead 280；本紀錄提交後為 ahead 281。
- 八個已掛載的 codex 分支工作樹切離至原 HEAD；九個 codex 本機分支 refs 在確認已是 dev 祖先後刪除。整理完成時現有本機分支僅 `main`、`dev`。所有原工作樹目錄、髒檔案與兩個 stash 都保留。
- 共用 `.git/info/exclude` 僅新增兩條精確路徑，排除本機 raw inventory；原檔未變。沒有新增寬泛的 tmp/editor 規則。

## 備份與差異盤點

- 完整 bundle：`output/qa/branch_consolidation_20260927/archive/repo-all-refs-detached-stashes-20260927.bundle`，22,731,770 bytes，SHA-256 `DF817F9D3EECA8ED533E85508D97BDEEB6379441CFDC7C326DE6E1DFD73A158B`。`git bundle verify` 通過，另在獨立 bare repo 驗證 dev/main、所有 worktree HEAD 與兩個 stash commit 物件均可讀。
- 髒工作樹封存索引：`output/qa/branch_consolidation_20260927/archive/working-tree-snapshot/snapshot_manifest.json`，SHA-256 `bd7c5a3fd948f8db551779da742488e50f8e16cb242bd2beddb6e318317bb321`。它保存 19 棵工作樹的 staged、unstaged、combined binary patches，並將 untracked 原檔以內容雜湊封存、記錄原路徑：100 個出現位置、91 個唯一內容。
- 早期 47 筆是漏計後的數字：原盤點記錄三個 `.codex/worktrees` 因 Git dubious-ownership 錯誤而將狀態設為 0。使用精確 `safe.directory` 重查後共 174 筆展開狀態；其中 wave14-closeout 佔 127（`git status` 一般模式折疊後 120），其餘 dirty trees 共 47。這是先前漏計，不是整理造成新增。

九個原分支 refs 與 SHA：

| 分支 | 原 SHA | 整理前狀態 |
|---|---|---|
| `codex/formal-data-repair-20260923` | `e16f92928980a025d24bd5b023eeadf9d6a31daa` | 已是 dev 祖先 |
| `codex/luna-price-revision-research-20260922` | `2268a98a7fe332cd4074850724b6a60e926eb73a` | 已是 dev 祖先 |
| `codex/model-repair-bounded-market-20260923` | `2292e6604fe13533e2db398acefbcfc3d89903ad` | 已是 dev 祖先 |
| `codex/model-repair-dataset-20260923` | `7c8a08c2972561410fe357b4cafb67654e97a203` | 歷史保留合併 |
| `codex/model-repair-dataset-v2-20260923` | `dcee1c92fca8affa712d5655e93bb0b7fd37e6d9` | 歷史保留合併 |
| `codex/model-repair-integration-20260923` | `85aeddf18651f1ff16d143f03ae40d964388e18f` | 已是 dev 祖先 |
| `codex/model-repair-market-build-20260923` | `56fc40bef47fe99f728ead026dde503f1c7c4343` | 已是 dev 祖先 |
| `codex/model-repair-source-20260923` | `7f1d7ad377af9f2e46bec4d62ffb8dababfff556` | 歷史保留合併 |
| `codex/model-repair-training-20260923` | `0dbc2775e04b552ad977194eb9b12cfc40c571b6` | 歷史保留合併 |

## 保留的後續工作與 stash

唯一尚未整合的獨立功能候選是 Phase3C repair detached HEAD `f215444f1203ffa39865ff391883d7c72aba7b4c`，留在原工作樹並已納入 bundle。它只針對隔離的 `phase3c_candidate.db` 與 2026-09-11 institutional rows；runbook 預期 21,479 source rows、32 updates、5 inserts，要求 owner 審查後才 apply，並提供 staging、backup、hash/preimage 檢查與逐列 rollback。這不是正式資料庫修復核准，也沒有證據顯示該輪已接受或套用；應列為未來待審候選，不合入本次整理。

wave14-closeout 工作樹保留原樣。127 項含 58 tracked modifications、69 untracked；主要是 44 tests、34 QA 報告/manifest、29 source/script、15 architecture/docs 與 2 零星檔。22 個 code/test 路徑經換行正規化後，19 個與 dev 內容相同（差異僅 LF/CRLF）；其餘 `app_module/update_service.py`、`scripts/scheduled/run_daily_data_update_quick.py`、`tests/test_scheduled_data_update_runner.py` 是舊工作樹版本，dev 已有 2026-09-26 經驗證的更新版本（`d31ab647`、`bb23a162`）取代。這些髒 source/test 沒有額外未整合功能。QA/architecture 歷史報告留存在原工作樹與封存，不合入 dev。逐檔摘要在 ignored `output/qa/branch_consolidation_20260927/wave14_vs_dev_diff_summary.json`。

兩個 stash 保留不動：`stash@{0}` `8a4950354610edff3b959a984895b92a67ee820d`（monthly-revenue adapter，變更已在 dev）；`stash@{1}` `62000f96f2fa11f4812c16ace020cfc23caac119`（架構文字，變更已在 dev）。

## 復原

bundle 可用於重建 refs/commit 歷史；移除的分支可從上表以 `git branch <name> <saved-SHA>` 重建。工作樹 tracked patches 和 untracked blobs 依 snapshot manifest 原路徑回放並驗 SHA-256。歷史保留合併沒有檔案差異；不建議為改變 refs/history 執行 reset 或移除該 merge，若確有需要須先保留 bundle 並另行確認。
