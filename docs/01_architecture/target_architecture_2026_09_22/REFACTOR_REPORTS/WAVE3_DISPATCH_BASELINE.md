> **歷史派工基線（勿依此重新派工）**：owner、HEAD、檔案雜湊、路徑與狀態只代表該次交接快照，不代表目前負責人或執行授權。現況與優先順序看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 及最新具名 QA；目標設計以 [FINAL_TARGET_ARCHITECTURE](../FINAL_TARGET_ARCHITECTURE.md) 為準。

# Wave 3 R009／R010 隔離派工基線

CURRENT_STATUS: RELEASED_AFTER_DEPENDENCY_SYNC。R008 result_id 勘誤已依 `R008_SOL_RESULT_ID_ACCEPTANCE.md` 與 `WAVE2_RESULT_ID_CHECKPOINT.md` 通過；兩個 worktree 的 app contract/test 已更新至新 SHA，逐檔核對 13 個共用凍結輸入皆與 main 相同、HEAD 同為 `166ad745…`。兩位 worker 在修正期間曾被中斷，未留下 R009/R010 task output，現可在原隔離 worktree 續作。

續作後另一隔離模型修復任務把 main fast-forward 至 `3462ec7a85b4f17021c98883a1e6809bf23a5239`；`166ad745..3462ec7a` 的變更只涉及 model-repair research/current capture、其測試及文件，沒有 R009 codec/DTO seam、R010 PreparedMLInput/adapter 或凍結 R007/R008 dependency 路徑。兩個實作 worktree 暫留在 `166ad745` 以免執行中切換；SOL 整合時必須再對最新 main HEAD 重驗並處理其餘共享 dirty bytes，不能把 worktree HEAD 誤報為當時 main HEAD。

Wave 2 checkpoint 為 PASS 後才建立本批工作樹。兩個 task 起初從 main HEAD `4467cd5ff73bf360235cf95a9e2ad08a3015716d` 建立獨立 detached worktree。派工前另一隔離任務將 main fast-forward 至 `166ad745710914312ee8e2e698f230577bfb41a4`；我先核對新 commit 只涉及獨立 ML research／QA 路徑、與本批凍結 dependency 及 task owner 檔無重疊，再對兩個 worktree 使用非強制 `git switch --detach` 切到同一新 HEAD。切換後已重驗 copied dependency SHA、DTO blob 及 worktree status。未 stage、commit 或 push。main working tree 既有 Wave 0–2 與其他 dirty/untracked 檔保持原樣，Git index 為空。詳細 Wave 1/2 dependency evidence 見 `R007_SOL_TZNAME_ACCEPTANCE.md`、`R008_SOL_FINAL_ACCEPTANCE.md`、`WAVE2_CHECKPOINT.md`；R004/R006 依原 Wave 1 PASS 證據。

| Task | 隔離目錄 | 唯一可新增／修改的工作輸出 |
|---|---|---|
| R009 | `output/agent_worktrees/refactor_r009_20260922` | `app_module/recommendation/codec.py`、窄 `app_module/dtos/__init__.py` seam、R009 tests/report |
| R010 | `output/agent_worktrees/refactor_r010_20260922` | `ml_module/prepared_input_contract.py`、`app_module/recommendation/ml_adapter.py`、R010 tests/report |

HEAD 不含尚未提交的 R007/R008 dependency。已從 main 精確複製並逐檔確認 SHA 相同：

| 兩側共用凍結輸入 | SHA-256 |
|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` |
| `data_module/__init__.py` | `D05D5275D2A4453FC4CF86B8F2D99FE611AEC98F610C58A8D63BA289A8825537` |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` |
| `data_module/contracts/__init__.py` | `C36C0AAB8805F98B9FCEABCF48BABDF68587704D0AB261CE1E2A9580E2860FE6` |
| `data_module/contracts/market.py` | `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A` |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` |
| `decision_module/recommendation/contracts.py` | `65BE03D7DC9DC667759D814D10A293333BD4D5FA34E30BC8C4854AB5A4C1C85D` |
| `app_module/recommendation/__init__.py` | `1BF187FF2A083E691C274B9FF2ACF24FC46F2E11286E09BF85E01B0EB15DEACA` |
| `app_module/recommendation/contracts.py` | `CCF12635EBE037548C7695154D2CD661C1FF8182C6663222F1CC219F982BBC63`（R008 result_id 勘誤後更新） |
| `tests/test_data_market_contracts.py` | `E98E905515C4B9BE6D4EFD420D44A16AD3ED6FFE1D128A68E850340D4F0C4E4B` |
| `tests/test_recommendation_contracts.py` | `29AA1B7EE2412F772526471A962CA6E238B808978FAEE859F40888D547C094CA`（R008 result_id 勘誤後更新） |
| `tests/test_r008_decision_numeric_enum_rework.py` | `74CCE82275B7A18AE7499084730AB278ED33E5FD6B6EA280ADD8A6CB4E4BAC9B` |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` |

R009 額外複製 `tests/test_r004_recommendation_persistence_characterization.py` SHA `F7F9F5E34CB9653511E4B2BC4A7280CFCCECD0F9A54BB3F54D153972F4A1E321`；R010 額外複製 `tests/test_refactor_ml_compatibility_baseline.py` SHA `EE182953773EBBF3E8E4D77632454BBA8EE45BD7F9F0124A4E2D2634E9372F0E`。兩側僅可讀取這些 dependency copies，不得修改；結束時須逐檔比對。

R009 的舊 DTO seam 在 main 與新 worktree 均為 clean tracked 內容，`git hash-object` 同為 `9d6607148d9d8f018b887c110562bb5e24f5a02f`；工作樹 raw SHA 因 checkout 行尾不同而分別為 main `8242E02087D32E5CE5F311633D9CD520FD7E0F553D90003198B5B8BB7B1CCDDD`、R009 `3C35DA79BB2334F41AC73B21B73FC419253DD31E6CE0198DD950155FC6F356EE`。整合時須用窄 diff／hunk 套入 main，不能直接以 R009 worktree 全檔覆寫 main DTO。

兩個 task 完成後先檢查各自 status 與凍結輸入 SHA；只把各 task 的授權輸出逐檔整合回 main。任何來源變更、額外路徑或 seam 原始 git blob 漂移都需先停下重審，不作整目錄複製或清理。
