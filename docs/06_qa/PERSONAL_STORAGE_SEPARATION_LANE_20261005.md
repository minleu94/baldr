# 個人儲存與市場包分離 lane（2026-10-05）

## 交付與邊界

本 lane 基底為 `631d6ad189e490dc75e964ee4abafc69df7ce114`；worktree 為 `C:/Projects/PythonProjects/technical_analysis_personal_store_lane`，branch 為 `lane/personal-store-separation-20261005`。只新增本文件、`app_module/personal_data_paths.py` 與 `tests/test_personal_data_paths.py`。沒有依賴或帶入共享 dev 的 UX08 未提交修改，沒有共用檔修改。

使用者已授權程式／架構與 synthetic fixture 工作，未授權正式資料 migration、配置啟用、writer 切換或 DB 分享。本交付是可獨立測試的路徑契約及 market-only export metadata 計畫，不是正式部署完成。沒有讀取真實收藏內容、複製市場 DB／raw、搬文件、建真 DB、打包、上傳或修改原計畫。沒有觸碰 chart／research UI、快照策略、中央容量與 Paper owner 的帳本。

採 Execution 實作、Tech Lead 路徑風險自查與 Testing/QA service-oracle 驗證。此切片不涉及金融數值或策略／特徵／績效計算，沒有新增 float 或 look-ahead 邏輯。可用工具列確認 GPT-6 Luna 支援 max，但本 lane 未派子 agent，也沒有宣稱變更本 thread 模型或代替父層 Astra。

既有 graphify 圖譜日期為 2026-09-29，讀到 WatchlistService canonical 為 OUTPUT_ROOT/watchlist 的節點；它早於 COW 新版，只作導航。實際行為以本 lane 基底程式為準。未重建圖譜、安裝依賴、讀受禁 sessions 或改 Codex memory。

## 已完成的 path contract

`resolve_personal_data_paths(market_root, personal_root=..., legacy_output_root=..., environ=...)` 明示參數優先於 `PERSONAL_DATA_ROOT`。沒有配置時回 `personal_root_unconfigured`；不會偷偷採用候選 root，也不建立目錄。caller 必須傳入 TWStockConfig 已解析的 data_root 與 output_root，避免忽略 OUTPUT_ROOT 覆蓋與 test profile。

`PersonalDataPaths` 提供 watchlist DB、marker、conversion receipt、DB backup root、marker backup root、research notes root、ledger root 的純計畫值。所有個人路徑在 personal root 下；personal root 與 market root／legacy output root 相同、包含或被包含均拒絕。既有檔案不能充當目錄 root。祖先與子路徑 symlink／Windows junction／其他 reparse point 均拒絕，不只檢查 resolve 後的 containment。個人已存在的 DB／marker／receipt 若為多連結檔也拒絕。

相對 root、drive-relative、`..`、Windows ADS／保留裝置名／尾端空格或點／device namespace 均拒絕。`validate()` 每次重新檢查，供未來 consumer 在使用前再核對，而不是相信啟動時的舊路徑。

## market-only export 邊界

`plan_market_only_export(paths, relative_files, destination_root=...)` 接受明列的 POSIX 相對檔名，無 glob、目錄遞迴、檔案內容讀取或 copy。輸出 frozen metadata manifest；不建立目的 root。

固定白名單如下：

- `daily_price/**/*.csv`、`daily_price_tpex/**/*.csv`、`technical_analysis/**/*.csv`、`broker_flow/**/*.csv`：只限明列的 regular file。
- `meta_data/market_index.csv`、`industry_index.csv`、`stock_data_whole.csv`、`all_stocks_data.csv`、`broker_branch_registry.csv`：只限這五個精確名稱。

output、收藏、研究筆記、帳本、log、任意 JSON、SQLite／DB／WAL／SHM 均未授權。未知市場來源也先拒絕，需 owner 審核後擴充白名單與測試。若 output_root 被自訂在白名單樹內，仍排除該整個 output subtree。destination 與 market／personal／legacy output 不得包含、被包含或相同。

manifest 保存檔案 dev／inode／size／mtime_ns／ctime_ns；`validate()` 重驗白名單、link、hardlink、來源 identity、duplicate 與目的子路徑。任何多連結 regular file 拒絕，阻擋把個人 CSV 硬連結到允許樹。Windows junction 指向個人檔、規劃後來源變動、規劃後換 link、目的子路徑 link 都拒絕。

此層保證的是指定路徑／類別的邊界，不解析 CSV 私人內容，也不驗證市場來源授權／license。無法因此宣稱任何同名 CSV 都經 privacy 審查。未實作的包裝 consumer 必須在受控、禁止其他 writer 改動的來源快照上使用，並在開啟時以 no-follow／handle 身分核對消除驗證到開檔的 TOCTOU；本 metadata plan 不是併發安全複製工具。使用者現在直接 zip 整個 FA_Data 仍會帶出既有 output 中的 legacy 收藏，不能因本模組存在就宣稱已可分享。

## 正式位置提案（待使用者確認，未建立）

主要建議：此 Windows 使用者的 `%LOCALAPPDATA%/baldr/personal`，此機完整值為 `C:/Users/archi/AppData/Local/baldr/personal`。資料與市場抓取包分離，且不同 Windows 使用者有各自 root。

| 用途 | 完整建議路徑 |
|---|---|
| 收藏 DB | `C:/Users/archi/AppData/Local/baldr/personal/watchlists/watchlists.v3.sqlite` |
| 啟用 marker | `C:/Users/archi/AppData/Local/baldr/personal/watchlists/watchlists.v3.sqlite.cow-active.json` |
| 轉換 receipt | `C:/Users/archi/AppData/Local/baldr/personal/watchlists/watchlists.v3.sqlite.cow-conversion.v1.json` |
| 個人設定／pointer | `C:/Users/archi/AppData/Local/baldr/personal/settings/`（尚未接線） |
| 原 JSON bytes 備份 | `C:/Users/archi/AppData/Local/baldr/personal/backups/watchlists/<conversion-id>/default.json`（尚未建立） |
| DB 備份 | `C:/Users/archi/AppData/Local/baldr/personal/backups/watchlists/` |
| rollback marker 備份 | `C:/Users/archi/AppData/Local/baldr/personal/activation_backups/watchlists/` |
| 個人研究筆記 | `C:/Users/archi/AppData/Local/baldr/personal/research_notes/` |
| 帳本／持倉域 root | `C:/Users/archi/AppData/Local/baldr/personal/ledgers/` |

若使用者偏好 D 槽，候選為同級 `D:/Min/Python/Project/FA_Personal`，同樣套用以上相對子路徑；DB 即 `D:/Min/Python/Project/FA_Personal/watchlists/watchlists.v3.sqlite`。此名稱只作提案，不自動由 FA_Data 推算或啟用。帳本目前 owner 與各 DB schema 不變，本 lane 只提供 root 契約。

舊 `D:/Min/Python/Project/FA_Data/output/watchlist/default.json` 必須原樣保留。委派提供的 version1／1948B 是背景資訊，本 lane 沒有讀檔或重驗該 metadata，不冒稱真實 migration 已驗收。正式位置、轉換來源、目標、備份、marker 位置與切 writer 必須另行具體批准。

## 既有 COW 接線 patch 說明（未套用）

關鍵缺口：現有 `watchlist_cow_activation.py` 的 `cow_activation_marker_path(source)`、`_backup_path(source, activation_id)` 與 `_lock_path(source)` 均在舊來源旁。只把 converter destination 換成外部 root 不會讓 marker／rollback audit 離開 FA_Data。本模組的 activation_marker 是未來 personal control plane 位置，不能現在直接當作現有 source-bound API 的 canonical source。

整合 owner 後續受控 patch 建議：

1. `data_module/config.py` 加 opt-in personal_root（或由 app composition 將明示設定傳給 resolver）；保留 data_root／output_root 的市場意義。傳入已解析 output_root，禁止 personal 模式 fallback 到 FA_Data/output。未設定時明示尚未配置；不以新契約偷偷 migration。
2. `app_module/watchlist_cow_activation.py` 以 keyword-only `control_paths`（或等價集中契約）讓 preview／activate／resolve／rollback／writer guard 共用本模組的 marker、backup 與 lock 位置。legacy source path、hash／stat、receipt canonical_path、完整 raw payload／revision lineage 仍 pin 真正舊 JSON；不要把 canonical source 換成未建立的 target。所有 marker／rollback／鎖／staging metadata 都在 personal root，禁止僅更改 activation 函式一處。
3. converter 接 target=`paths.watchlist_db`、receipt=`paths.conversion_receipt`，備份使用 `paths.backup_root`；逐版 COW 驗證、create-only、rollback preservation、cancel 與 writer locks 保留。source read-only；不得寫新 marker 到 legacy output。需完成 synthetic activation／重開／損毀 marker fail-closed／回復／target 新 revision 保留測試後，再提請正式轉換批准。
4. `app_module/watchlist_service.py` 的 canonical_repository_path 與 discovery／constructor 接 personal selector；原 service 會 mkdir legacy watchlist_dir，不能只改 canonical_repository_path。personal mode 的 startup discovery 只找明示 personal marker，不掃整個市場包或自動建空庫。舊 JSON 留在舊路徑，未啟用前如何保持 legacy 相容由 owner 明示設計。
5. `scripts/watchlist_sqlite_cow.py` 暴露 personal control paths／source／destination 的明示 preview；把 DB ready、marker active 與正式部署批准分開。所有正式寫入仍需具體授權，本 lane 沒有執行 CLI。
6. market-only 包裝 caller 消費本 manifest；整庫 SQLite export 暫拒絕，未來必須另外定義經核驗的市場表白名單與新庫生成契約、包含表／trigger／view／sidecar 審查，不能直接複製既有 twstock.db 後聲稱不含私人資料。

上述五個共用程式檔本 lane 全部未修改。Manual、Snapshot、current architecture、導航及 QA index 的同步由主整合 owner 隨真正接線更新；本 lane 不 stage 共享文件。原 output/plans 計畫只讀，未改。

## 驗證與回滾

在 lane cwd 使用共享 venv interpreter，fixtures 在全新獨立 Temp root：

```powershell
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m pytest tests/test_personal_data_paths.py -q -o addopts= --basetemp=C:/Users/archi/AppData/Local/Temp/ta_personal_lane_1005_d
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m mypy app_module/personal_data_paths.py --follow-imports=skip
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m py_compile app_module/personal_data_paths.py tests/test_personal_data_paths.py
```

實測：68 passed、無 skip；Windows junction 與 hardlink synthetic 負例實際通過。mypy 單檔通過、兩檔 compile 通過。沒有 UI 修改，不重跑 UI gate 或 full-stack。正式資料／真實 migration／Native／consumer copy 尚未驗收，不借用 fixture 宣稱通過。

| 新增檔案 | 回滾方式 | 風險 |
|---|---|---|
| app_module/personal_data_paths.py | 整合前不採用 lane commit；整合後在受控分支 git revert 該 commit | 目前無 runtime caller；無真實資料風險 |
| tests/test_personal_data_paths.py | 同提交 revert | 不改正式資料 |
| 本 lane QA 文件 | 同提交 revert | 交接記錄須先保存 |

回滾先確認分支與 dirty files ownership，再執行受控 revert，重跑相關測試。未執行回滾、worktree 清理、cherry-pick 或 push。此 lane 可單獨 cherry-pick，但只交父層／主整合 owner 審查，不能把此提交描述成正式資料已分離。