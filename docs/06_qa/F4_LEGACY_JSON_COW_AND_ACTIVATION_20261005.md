# F4 Legacy JSON 無損 COW 與明示啟用（2026-10-05）

本批基線 `cb1ff3c494ef8da297c6384725c669a677d110ce`。補齊實際預設 legacy JSON v1 到獨立 SQLite v3 的工程路徑；正式使用者套用仍須批准。沒有讀取／複製使用者內容、初始化缺失正式 DB、執行 Native、producer、ML、清理或 push。

## 契約與無損範圍

來源是單一明示 legacy JSON v1 object／items array；同目錄其他清單或已有 canonical SQLite 的歧義具名拒絕。原 JSON 不覆寫，獨立 target 建立後逐項核驗才可明示啟用。原 raw payload、未知合法 JSON 欄位、巢狀項目、理由、日期、來源與排序保存；JSON 內的 opaque 歷史資料原樣保留，不臆造可執行的 revision ledger。原檔沒有可驗證的版本鏈時，v3 明示 synthetic baseline；這不是補回不存在的歷史。

JSON source 的 marker 為 `default.json.cow-active.json`，與 canonical SQLite marker 分開。fresh service 讀回、過期 service writer、source pin、容量、取消與錯 metadata 依同一指標鎖守衛。回退回 JSON 指向，保留原 JSON、target 新寫入、conversion receipt 與 rollback audit，不自動合併。錯 marker 不允許 JSON fallback writer。

## 驗證與保留預算

## 2026-10-05 Legacy JSON v1 COW 與明示切換（最新）

實際一般啟動沿 legacy JSON v1；本批補齊單一 JSON→獨立 SQLite v3 converter、原升級按鈕的 convert／核對／activate、新程序 discovery、source-aware writer 與 rollback，不建立缺失 canonical。多份 JSON、已有 canonical 歧義、錯來源／marker、容量／版本／型態／編碼與並發 writer 具名拒絕。來源 raw bytes 與合法未知巢狀欄位保留，opaque history 不臆造 ledger；JSON 無版本鏈只建明示 synthetic baseline。回退回 JSON，保留 target 新 revision、雙來源和 audit，不自動合併。既有 SQLite COW 路徑沿原契約。

限定統一路由 113 passed，Workbench85、validator25／4skip、mypy 794及CLI1、12檔compile與6產品檔精度／未來函數AST守衛0違規。14個隔離新程序完成 JSON CLI轉換／啟用／追加／回退，來源 bytes unchanged、target r2保留、canonical未建立；合成 JSON 起點20／120／250次保存之總留存 181,902／444,060／816,793 B，未冒稱自然來源／全書籤負載增長。17份已接受immutable來源SHA及正式JSONsize／mtime保持，正式資料未套用。

正式來源 `D:/Min/Python/Project/FA_Data/output/watchlist/default.json` 為1948B；候選 `watchlists.v3-cow.sqlite`、marker `default.json.cow-active.json` 與 canonical `watchlists.db` 仍不存在。本批不讀原 JSON 內容／不初始化缺失 DB。真正apply另由父層／使用者確認單來源、writer時段、當下容量與明示批准，再按Manual dry-run→convert→preview→activate→新程序讀回；rollback保留雙來源／新內容。PID39400／41588無原PID/starttime owner收據，保留未停止，不能當writer已停止的證據。

F1 exact18.621965821542936%／20%差15.1294400013285ms（約15.13ms）例外尚未批准；F2／F3 A/A不重開。UX07未啟動，新Native／真人／自然資格另列。原整份計畫階段done1／partial5／pending3、UX done2／partial14／pending8保持，有限工程完成不等於整份產品計畫完成。沒有清理、producer／ML重跑、Native或push；其他對話檔案保留排除。

## 實際來源與正式批准邊界

已核實一般啟動沒有可讀根路徑 override；預設來源 `D:/Min/Python/Project/FA_Data/output/watchlist/default.json` 為 legacy JSON v1，1948 bytes。預設 `watchlists.db`、新 target 與 JSON COW marker 尚不存在；本批只保存這些路徑的 metadata 前後收據，不讀原 JSON 內容。本批合成 fixture 僅仿結構，不複製使用者持倉／收藏內容。

正式套用前由使用者／父層確認來源與單清單 scope、可用時段／writer、當下容量和明示批准，再依 Manual 執行 dry-run、獨立 convert、preview、activate、新程序讀回；rollback 仍保留雙來源及新庫內容。本批不執行這些正式步驟，也不把缺失的 canonical DB 建出來。

PID 39400／41588 雖符合舊 pytest 命令列與隔離路徑，沒有原始 PID/starttime owner 收據，故保留；不是正式 writer 已停止的證據。線索留 `output/qa/f4_legacy_json_cow_20261005/pid_readonly_ownership.json`。

## 文檔與回復

唯一原計畫只追加，原 bytes 前綴保持。程式回復以 reviewed reverse patch／新本地 revert commit，不 reset／clean 或覆寫他人工作；資料回退只切指標，不刪來源／target／stage／audit。Raw QA 根 `output/qa/f4_legacy_json_cow_20261005/` 保留全部成功與失敗，不提交。


| 合成保存次數 | 原JSON bytes | v3 target bytes | 雙來源／audit總bytes |
|---|---:|---:|---:|
| 20 | 6,367 | 167,936 | 181,902 |
| 120 | 6,367 | 430,080 | 444,060 |
| 250 | 6,367 | 802,816 | 816,793 |

原 JSON CLI 收據 SHA-256：`e42a8901c08ca14bbabb55e23e14a8b3c78ebca3070f38364d11783e55dc2a98`；20／120／250 收據 SHA-256：`06514d789eefdb4ebeacbcd6b8e1d2ecaa1d68e18ebd3b741bb3c70e59e421d9`。最終結果及各log見 raw QA 根；失敗保留且不加總重跑案例。


### 最後故障與精確測試計數

最後統一路由 `focused_root_02.log` 為112 passed／1 failed；唯一失敗是原 bookmark 測試仍期待舊 `legacy_import`。已同步新 schema3 的 `migration_baseline` 契約，單點 `focused_fix_03.log` 1 passed；因此113個不重複案例有通過證據，不把重跑計為新增案例。

首輪 `focused_root_01.log` 因較長QA basetemp加SQLite journal名超過Windows路徑限制，offscreen warning未攔截而停住；已中斷本次自有exec session，保留原fixture／輸出。改用 `.t/jcow-root02` 短隔離路徑，UI測試攔截warning並在失敗時附status原因；相關10項定向診斷全部通過。正式apply也須核對可用路徑，超限是工程拒絕，不是等自然成熟。沒有停止PID39400／41588或操作使用者視窗。

受控保存fixture初始20項manual合成資料，每次追加一項；20／120／250表示保存revision數，而非自然交易日／全書籤負載。既有rich bookmark長留存證據沿前批收據，本批只補實際JSON來源路徑；保留原4MiB／32MiB／64MiB／4096上限，不放寬中央容量。
