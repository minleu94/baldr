# Baldr 儲存搬遷進度（2026-10-20）

## 狀態

`IN_PROGRESS`。本次只新增 D→F 缺少檔案，並將 repo 內三棵大型資料樹完整複製到 F 的新儲存根；C 原件仍保留，尚未建立 junction、刪除任何來源、切換 `DATA_ROOT`／`OUTPUT_ROOT`，也未更改排程或安裝包。這份紀錄不是正式資料搬遷驗收。

## 磁碟現況

盤點時 PowerShell 回報 C 約 61 GiB、D 約 140 GiB、F 約 295 GiB 可用。完成本輪複製後，F 回報可用 `95,656,177,664` bytes（約 89 GiB）。磁碟容量以本次唯讀查詢為準；Windows CIM 的 `Get-Volume` 查詢遭拒，因此使用 PowerShell FileSystem PSDrive 數值。

## D→F 資料比對與新增副本

來源根為 `D:\Min\Python\Project`，目的根為 `F:\Min\Python\Project`。使用 Robocopy `/L /E /XJ` 先盤點，並以 `/XC /XN /XO` 限定只複製 F 不存在的檔案；未覆寫既有同名檔，未刪除 D 端任何內容。複製後再次以相同唯讀比對確認來源獨有檔案為 0、失敗為 0。

| 資料根 | 新增檔案 | 新增 bytes | 複製後來源獨有 | 結果 |
|---|---:|---:|---:|---|
| `FA_Data` | 1,876 | 614,266,955 | 0 | 複製及清單核對完成 |
| `FA_Data_candidate` | 8 | 63,577 | 0 | 複製及清單核對完成 |
| `FA_Data_Shadow` | 83 | 86,699,345 | 0 | 複製及清單核對完成 |
| `FA_Data_Shadow_BankTaiwan` | 14 | 53,421,573 | 0 | 複製及清單核對完成 |
| `FA_ML_Research` | 312 | 21,213,911,652 | 0 | 複製及清單核對完成 |
| `ig_data` | 0 | 0 | 0 | 原本即一致 |

新增副本合計 2,293 個檔案、21,968,363,102 bytes。D 端沒有 `SportsLottery_Data`；F 端該目錄予以保留，沒有從別處補造來源。

### 尚未合併的同名差異

Robocopy 初始清單另指出 D 端有 2,264 個既存同名檔較 F 端新，合計 7,961,225,483 bytes。候選分布為：`FA_Data` 2,241 個／6,689,741,539 bytes、`FA_Data_candidate` 1 個／1,222,467,584 bytes、`FA_Data_Shadow` 12 個／2,082,733 bytes、`FA_Data_Shadow_BankTaiwan` 4 個／46,782,206 bytes、`FA_ML_Research` 6 個／151,421 bytes。這些尚未覆寫或以 SHA-256 判定內容等價；F 端 `FA_Data` 還有 4 個 D 端沒有的檔案（23,170,635 bytes），均保留。

`FA_Data` 差異包含 `sqlite/twstock.db`、其 WAL/SHM、推薦資料庫、排程狀態／記錄及 `writer.lock`。搬遷前另見 D 端推薦 DB 與 `data_update_quick/latest_status.json` 時戳晚於 F；目前沒有列舉到 Python／Baldr 執行程序，但 Windows CIM 無法讀取執行中 Scheduled Tasks 清單。這些狀態資料尚未以一致快照搬遷；不可因時間戳較新就直接宣稱正式資料根可切換。

## C 槽 repo 內資料副本

在新根 `F:\Min\Python\Project\BaldrStorage` 建立以下目的目錄。三個 C 來源均完整保留，Robocopy 複製後再以 `/L /E /XJ` 核對；每棵樹需複製檔案為 0、失敗為 0、額外檔案為 0。

| C 來源 | F 副本 | 檔案 | bytes | 狀態 |
|---|---|---:|---:|---|
| repo `output` | `repo-output` | 1,110,585 | 94,061,888,953 | 複製及檔案數／bytes／時間戳清單核對完成 |
| repo `dist` | `repo-dist` | 464,166 | 63,010,833,145 | 複製及檔案數／bytes／時間戳清單核對完成 |
| repo `.t` | `pytest-temp` | 641,165 | 38,392,588,170 | 複製及檔案數／bytes／時間戳清單核對完成 |

三份副本合計 2,215,916 個檔案、195,465,310,268 bytes。清單核對依檔名、大小與時間戳；未對全樹逐檔計算 SHA-256。C 原件尚未移除，因此這些副本目前沒有釋放 C 空間。`.venv` 約 1.42 GB，未搬移，因虛擬環境內含絕對路徑且需另行重建與驗收。

## 尚待完成

1. 在允許的正常額度恢復後，逐批核對 2,264 個同名差異及 4 個 F 獨有檔；對 SQLite／WAL 使用可重現的一致性搬遷程序，保留舊版與來源證據。
2. 取得唯讀方式確認正式資料 writer／排程狀態。不得自行停用、啟用或重觸發正式 Task；未能確認 writer 安全時，維持 D 為現行根。
3. 只有在資料副本完成一致性核驗後，才將 `TWStockConfig`、啟動環境範例與現行操作／架構文件切換至 F；同時保留明確的環境變數覆寫路徑。
4. 對 `output`、`dist`、`.t` 建立可回復的原路徑 junction，確認應用與測試路徑解析到 F，並保存回滾步驟；只在切換及讀回成功後才移除 C 原件。
5. 核對固定 EXE／試用包的資料根設定是否需要具名新候選；不得覆寫既有固定版本或私人原件。
6. 更新產品文件入口與文件關聯，執行與本次設定變更相稱的設定解析驗證；未執行前不得標示通過。

## 本次邊界

沒有執行正式資料寫入、清理、SQLite 重建、排程變更、應用程式設定切換、`DATA_ROOT`／`OUTPUT_ROOT` 修改或產品 QA。工作樹開始時乾淨，HEAD 為 `c377efc51be03ea93dede060c06919f5029602b4`；本文件記錄本次進度，供下次直接恢復。
