# Baldr 儲存搬遷紀錄（2026-10-20）

## 目前狀態

`PARTIAL — F 已設為新資料與大型產出位置；C repo 大型目錄已切換；D 舊資料尚未刪除。` 使用者要求確認內容後只保留 F 槽資料。D→F 複製／合併和 C→F 搬遷已完成，下方列出證據與核驗範圍。刪除 D 舊根之前，需先讓仍持有 `D:\Min\Python\Project\FA_Data\output\application_state\logs\config.log` 的程序正常關閉；不終止未知程序。尚未宣稱 D 已清空。

本機 `output/tasks/<task_id>/task.json` 尚未建立：`document_control.py init-task` 拒絕寫入，因 `output` junction 解析到 repo 外的 F 槽目標，超出該工具的 repository path confinement。此工作目前以本 QA 紀錄維持恢復狀態；沒有繞過該路徑守衛。

本次字串路徑變更已通過 `git diff --check`，現行程式／手動測試入口掃描未留 D 資料根。Python 設定測試與受改檔案 compile 尚未執行：此 checkout 找不到交接規定的 `run_one_owned_qa_root02.py`，因此沒有啟動未受 Job 限制的 Python QA。

## 磁碟與 C 槽目錄

本輪開始時 C 可用空間約 64.4 GiB；搬遷後曾量得 253.9 GiB，Codex 重啟後最新查詢為 `270,541,762,560` bytes（約 252.0 GiB）。相較本輪開始增加約 187.6 GiB；可用空間會隨其他程序寫入而波動。D 可用 `151,000,436,736` bytes（約 140.6 GiB），F 可用 `78,803,542,016` bytes（約 73.4 GiB）。容量由 PowerShell FileSystem PSDrive 查詢；這是整個磁碟空間變化，不等同資料樹的 logical bytes。

repo 的大型目錄已從 C 移至 `F:\Min\Python\Project\BaldrStorage`，C 原路徑改為 junction，並已核對 LinkType、ReparsePoint 及目標存在：

| C repo 路徑 | F 目標 | 檔案 | bytes |
|---|---|---:|---:|
| `output` | `repo-output` | 1,110,585 | 94,061,888,953 |
| `dist` | `repo-dist` | 464,166 | 63,010,833,145 |
| `.t` | `pytest-temp` | 641,165 | 38,392,588,170 |

三棵樹合計 2,215,916 檔、195,465,310,268 bytes。Robocopy mirror-check 回報需複製 0、差異 0、失敗 0、額外檔案 0；原路徑切換前，曾部分移動的 `output` 備援目錄中另有四個 DB 備份，已逐檔以 SHA-256 確認 C 與 F 相同後納入 F。全樹核對使用檔名、大小及時間戳，沒有逐檔 SHA-256；四個補入 DB 有 SHA-256 證據。`.venv` 保留在 C，未移動或重建。

## D→F 資料核對

舊來源根 `D:\Min\Python\Project` 對應新 F 根 `F:\Min\Python\Project`。F 不存在的來源檔已補齊 2,293 個、共 21,968,363,102 bytes；Robocopy 完成後來源獨有檔案 0、失敗 0。複製另保留 F 原有的四個 D 不存在檔案，合計 23,170,635 bytes；`SportsLottery_Data` 只在 F 出現，予以保留。上述新增檔採 Robocopy 檔案清單／大小／時間戳核對，並非逐檔 SHA-256。

D 中較新的同名檔有 2,264 個。先前 F 版本已依使用者指示，在逐檔來源／目的 SHA-256 收據通過後刪除；D 較新版本已合併至 F，2,264 筆目標 SHA-256 收據均為 PASS（含共享寫入日誌，以兩次穩定唯讀雜湊核對）。差異資料共 7,961,233,287 bytes。完整收據位於 F 的 `BaldrStorage` 本機搬遷證據目錄。

目前 D 仍有六個根：`FA_Data`、`FA_Data_candidate`、`FA_Data_Shadow`、`FA_Data_Shadow_BankTaiwan`、`FA_ML_Research`、`ig_data`。SQLite DB／WAL／SHM 及列出的其他資料庫已通過當次獨占開啟檢查；但 D 的 `FA_Data` 下 `config.log` 仍被未知程序開啟，普通獨占讀取失敗。Codex 重啟後 D 日誌長度與時間仍為 2,025,981 bytes／19:53:09 UTC；Restart Manager 唯讀查詢未回報程序。D 日誌兩次唯讀 SHA-256 穩定為 `769F3BDB81B71424A2A8DD67088DEEFD9A74316F044FC7A7F7C70F020690752D`；F 對應日誌亦仍被開啟，穩定 SHA-256 為 `B00CF6BB7754B7D4D13A0B3C0F0F87891D5AD4BBFF0B5AEE157E4D416CB76BD0`（2,030,541 bytes，20:36:24 UTC）。兩者不同，F 版本較新，未覆寫任何一方。D 日誌位元組已另存至 F `BaldrStorage/migration_evidence_20261020/D_FA_Data_config.log`；`D_config_log_receipt.json` 記錄來源、目的、長度、SHA-256 及核對方法。D 六個根目前全部保留；解除程序鎖定後須再確認 D 是否有新寫入，再確認其餘資料無變動，才移除 D 原始資料。沒有終止任何程序。

## 新資料根與程式設定

`data_module/config.py` 預設 `DATA_ROOT` 為 `F:/Min/Python/Project/FA_Data`，`OUTPUT_ROOT` 為其 `output` 子目錄；Windows User 環境變數已設為相同 F 路徑。`.env.example`、啟動／更新腳本、目前架構與操作文件中的執行路徑範例已同步。活動中的 `output/ml_research_storage.json` 已由 D 改指 F，讀回值正確，SHA-256 為 `D2CC72B854CA3C86D872FFA20CC4957E987B39E7196CEB73BD651E146745582C`。

active source 中 `FA_Data`／`FA_ML_Research` 的 D 根路徑已更新至 F；保留測試、歷史文件及封存內容的舊路徑字串，避免改寫歷史來源。`dist` 現有固定包未覆寫；目前試用／固定包的啟動檔未找到 D 根引用。舊包若自行保存絕對 D 路徑，尚未逐一啟動驗證。

## 下一步與限制

1. 待持有 D `config.log` 的程序正常退出後，重新核對 D 該檔及 F 端具名保存原件；其餘 D→F 複製內容已依上述收據／Robocopy 範圍完成核對。
2. 刪除六個 D 原始資料根，確認 D 不再保留這批 Baldr 資料，並量測 D 可用空間變化。刪除只在鎖定解除及 final comparison 成功後執行。
3. 以專案規定的 Windows Job 執行設定測試及受影響 Python 編譯；尚未執行者保持 NOT TESTED，不以字串檢查代替執行驗證。
4. 驗證 F 上試用包／新程序會使用 F 根；舊固定包與私人原件不覆寫。

本紀錄不代表資料集全域一致性、資料庫語義完整性或產品 QA。若 D 有新寫入，先合併／保留可證明的最新版本再清除；不得只依 mtime 刪資料。
