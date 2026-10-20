# Baldr 儲存搬遷紀錄（2026-10-20）

## 目前狀態

`STORAGE CUTOVER COMPLETE — F 為 Baldr 資料及大型產出的唯一儲存位置；C repo 大型目錄已改接 F junction；D 的六個 Baldr 資料根已核對並刪除。` Repository source code 仍在 C。六個 F 對應根仍存在，D 的 `Min\Python\Project` 現在為空。D 的 `config.log` 在刪除前沒有找到阻擋性占用；原始 bytes 已先保存至 F 證據目錄並核對 SHA-256。下方保留核驗範圍、時間點與限制。

本機 `output/tasks/<task_id>/task.json` 尚未建立：`document_control.py init-task` 拒絕寫入，因 `output` junction 解析到 repo 外的 F 槽目標，超出該工具的 repository path confinement。此工作目前以本 QA 紀錄維持恢復狀態；沒有繞過該路徑守衛。

本次字串路徑變更已通過 `git diff --check`，現行程式／手動測試入口掃描未留 D 資料根。Python 設定測試與受改檔案 compile 尚未執行：此 checkout 找不到交接規定的 `run_one_owned_qa_root02.py`，因此沒有啟動未受 Job 限制的 Python QA。

## 磁碟與 C 槽目錄

搬遷前後的可用空間曾多次量測，會隨其他程序寫入而波動。完成刪除後本次量得 C `261.84 GiB`、D `751.58 GiB`、F `73.37 GiB`；刪除前最近一次 D 為 `156.03 GiB`，本次觀測增加約 `595.55 GiB`。這是整個磁碟空間變化，不等同資料樹的 logical bytes。

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

刪除前再次對六個 D 根執行 Robocopy dry-run（`/E /L /XO /COPY:DAT /DCOPY:DAT /R:0 /W:0`）：所有根 `Copied=0`、`Mismatch=0`、`Failed=0`；D 的 `FA_Data\output\application_state\logs\config.log` 是唯一來源較舊檔，由 `/XO` 跳過，不覆蓋 F 現行日誌。FA_Data 另有四個 F-only 檔案、23,170,635 bytes，保留在 F。F 下其餘五根均無 extras。依既有逐檔 SHA-256 收據，2,264 個原先由 D 更新的同名檔已核實；D 日誌 SHA-256 為 `769F3BDB81B71424A2A8DD67088DEEFD9A74316F044FC7A7F7C70F020690752D`，與先前保存到 `F:\Min\Python\Project\BaldrStorage\migration_evidence_20261020\D_FA_Data_config.log` 的原件一致，長度均為 2,025,981 bytes。F 的活動日誌持續增長，故不與 D 舊快照混為一談。

Resource Monitor 以 D 槽完整路徑搜尋沒有結果；唯讀獨占讀取成功，Write / ReadWrite 的 Win32 回報為 `ERROR_ACCESS_DENIED (5)`，不是 `ERROR_SHARING_VIOLATION (32)`。因此沒有查到會阻擋刪除的程序；沒有結束任何程序。刪除前確認六個 D 根皆非 reparse point、內部沒有 junction，F 對應根全部存在。之後逐一刪除六個精確 D 根，PowerShell 回報全部 `DELETED`；D 專案資料父目錄目前為空，六個 F 根仍存在。沒有刪除 D 上層 `D:\Min\Python\Project`，也沒有刪除 F-only `SportsLottery_Data`。

## 新資料根與程式設定

`data_module/config.py` 預設 `DATA_ROOT` 為 `F:/Min/Python/Project/FA_Data`，`OUTPUT_ROOT` 為其 `output` 子目錄；Windows User 環境變數已設為相同 F 路徑。`.env.example`、啟動／更新腳本、目前架構與操作文件中的執行路徑範例已同步。活動中的 `output/ml_research_storage.json` 已由 D 改指 F，讀回值正確，SHA-256 為 `D2CC72B854CA3C86D872FFA20CC4957E987B39E7196CEB73BD651E146745582C`。

active source 中 `FA_Data`／`FA_ML_Research` 的 D 根路徑已更新至 F；保留測試、歷史文件及封存內容的舊路徑字串，避免改寫歷史來源。`dist` 現有固定包未覆寫；目前試用／固定包的啟動檔未找到 D 根引用。舊包若自行保存絕對 D 路徑，尚未逐一啟動驗證。

## 後續與限制

1. C→F 路徑、F 資料根及 Windows User 環境設定已核對；此為本機設定，不會同步至其他 Windows 帳戶或電腦。
2. 以專案規定的 Windows Job 執行設定測試及受影響 Python 編譯；尚未執行者保持 NOT TESTED，不以字串檢查代替執行驗證。
3. 驗證 F 上試用包／新程序會使用 F 根；舊固定包與私人原件不覆寫。

本紀錄不代表資料集全域一致性、資料庫語義完整性或產品 QA。D→F 的全樹核對依 Robocopy 的相對路徑、大小、時間與 dry-run 結果；逐檔 SHA-256 覆蓋 2,264 個較新同名檔及具名 D 日誌，並非全樹逐檔雜湊。若日後在 D 重建資料，需重新核對後再清除，不得只依 mtime 刪除。
