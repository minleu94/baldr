# C 槽歷史封存第二批清單（2026-10-09）

本文件記錄 2026-10-09 第二批冷封存範圍、核驗與回滾。建立時的文件整理與產品開發狀態屬當時快照；目前文件入口看 [資料文件導覽](README.md)，產品補完狀態看 [專案快照](../00_core/PROJECT_SNAPSHOT.md) 與 [恢復開發 QA](../06_qa/BALDR_COMPLETION_RESUME_20261009.md)。

來源根：`C:/Projects/PythonProjects/technical_analysis`。目標根：`E:/FA_Data_ColdArchive/baldr_c_drive_archive_20261009_batch2_plain`。下列 28 個目錄已按同名相對路徑封存並建立 Junction。完整搬移最初遭自動審查拒絕；其後使用者針對精確清單授權，才執行核驗後移除原副本與建立連結。

原 29-root 嘗試在複製前發現 integration_20261002 內含刻意建立的 Junction 測試案例，因此立即停止，沒有複製或移除來源。該 root 在這次初始嘗試中被排除；其餘 28-root 巢狀連結盤點無發現。此段只描述初始嘗試。後續依使用者確認的精確 28-root plan，`integration_20261002` 被納入第二批並完成封存；最終狀態以本文件的 released 收據及 [終態對照](../06_qa/C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md) 為準。初始失敗的 batch2 目錄只保留該次停止前的計畫與回滾文件，不冒充成功封存。

使用者後續針對此精確清單明確答覆：「同意清單中 28 個目錄核驗後移除原副本並建立 Junction」。移除與 Junction 已取得範圍授權；實際完成仍以逐批收據及終態收據為準，不將批准當成搬移結果。

## 精確範圍

| 相對目錄 | 類型 |
|---|---|
| `output/ml_research/integration_20261002` | 歷史 QA／備份 |
| `output/qa/wp5_verified_snapshot_seed_20260929_01` | 歷史 QA／備份 |
| `output/qa/technical_source_contract_20260919` | 歷史 QA／備份 |
| `output/qa/ui_layout_20260929` | 歷史 QA／備份 |
| `output/fundamental_current_backups` | 歷史 QA／備份 |
| `output/qa/price_repair_20260921` | 歷史 QA／備份 |
| `output/v4_ml_research_shadow_union_bounded_20260907/.tmp` | 歷史 QA／備份 |
| `dist/candidate_0f25b8c6ee51_44e24c54` | 舊候選封裝 |
| `dist/candidate_20261006` | 舊候選封裝 |
| `dist/candidate_290a93d7135a_fb67ad60` | 舊候選封裝 |
| `dist/candidate_2b6fda426b6f_3ed9cb87` | 舊候選封裝 |
| `dist/candidate_330b98f416f7_afa55c15` | 舊候選封裝 |
| `dist/candidate_421bc973a891_ca7c9022` | 舊候選封裝 |
| `dist/candidate_4b40788bea9e_dd7335f7` | 舊候選封裝 |
| `dist/candidate_58f8420ccae6_a2954bef` | 舊候選封裝 |
| `dist/candidate_7b21e0d4076b_98fff903` | 舊候選封裝 |
| `dist/candidate_93f9c57d7995_5ffdbdd4` | 舊候選封裝 |
| `dist/candidate_96ecf00121d8_ce6aeecb` | 舊候選封裝 |
| `dist/candidate_9bc1cbfb67b2_d502d017` | 舊候選封裝 |
| `dist/candidate_9d542bdb705f_7499370d` | 舊候選封裝 |
| `dist/candidate_acd18a1efcc0_56943844` | 舊候選封裝 |
| `dist/candidate_b61e978fac97_91bfa999` | 舊候選封裝 |
| `dist/candidate_bd5d2f86367a_3b730f86` | 舊候選封裝 |
| `dist/candidate_c589bc71e8f1_8e967bc9` | 舊候選封裝 |
| `dist/candidate_c611ed515ca0_1cc2db97` | 舊候選封裝 |
| `dist/candidate_e5026b3a5afa_abeea6de` | 舊候選封裝 |
| `dist/candidate_e97f01466f29_728b3cf2` | 舊候選封裝 |
| `dist/candidate_f2fba4c735ac_844ab7ab` | 舊候選封裝 |

## 回滾與保留範圍

變更類型：移動（已取得授權並完成）。每個目錄先完整複製，逐檔 SHA-256、大小與樹狀項目數核對，成功後才移除 C 槽來源並建立指向 E 槽的 Junction。失敗時原副本保留；E 槽完整副本與 manifest 長期保留。

回滾：確認無程序使用；核對原路徑確為指定 Junction，只移除連結本身（不遞迴刪除目標），將對應 E 槽樹複製回普通目錄，逐檔比對 manifest。嚴格拒絕 reparse point 的歷史驗證需先還原。

保留：dist/baldr、全部 baldr_* 回退版本、candidate_d9a115f67d2b_da8a88e9、近期 H20／F12／P01 候選、正式 FA_DATA、私人設定、排程、既有冷封存與第一批封存。Codex 資料庫及使用中的暫存不移動。

精確起訖收據、檔案清單及回滾副本位於目標根；logical 容量不等於實際釋放容量。

## 完成驗證與容量

複製及釋放兩個程序均 exit 0；28 個目錄、145,850 個檔案、39,268,782,429 bytes（36.57 logical GiB）完整保存。複製階段逐檔比對 SHA-256；移除來源前再次全檔比對 C／E 內容，並核對樹狀項目數與精確路徑。`released_complete.json` status=complete，全部根均為 archived_verified_junction_installed。

Root 最後另查 28 個 Junction 的精確目標；27 個非空根各抽一檔從原 C 路徑讀回，SHA-256 與 manifest 相同。candidate_20261006 原本空目錄，只核對拓樸與連結。抽樣只證明連結讀回，不替代前兩輪全檔核驗。**在 2026-10-09 第二批完成核對時，baldr、回退版本與 d9a115f67d2b 仍為普通目錄；此句不代表目前狀態。**`integration_20261002` 雖在初始 29-root 嘗試被排除，後續已列入精確 28-root 清單；當時 C 槽原路徑是指向第二批 E 槽副本的 Junction。

釋放程序期間 C 可用空間由 194,551,021,568 增至 228,999,462,912 bytes，觀測淨增加約 32.08 GiB；這不是 logical bytes，也不假定期間沒有其他程序寫入。postflight C 約剩 213.27 GiB，E 約剩 168.89 GiB。

本文初版記錄當時只新增本檔並在 `STORAGE_ASSET_REGISTER_20261006.md` 末尾追加索引，未 stage／commit，產品補完亦處於暫停。其後文件同步已提交至本機 `dev`（`6247a177`）；產品恢復狀態以專案快照與恢復開發 QA 為準。這段保留的是初版建立時的歷史，不代表目前 Git 或產品狀態。
