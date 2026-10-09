# MA V9 主視窗子程序身分檢查審查

Root 直接讀取 V8→V9 diff、目前 V9 runner 與 pure003 原始 terminal/stderr。這份候選尚未取得完整 Main 旅程執行核准。

## 已確認的缺陷

- pure003 exit code 為 1，原因是 `repository_root_mismatch`。該次 runner 為 209346 bytes、SHA256 `6798b8faec8fe35edb96225204dc3b019c7a98c7162d31371d52bfbda1c8fb1d`；審查時 runner 已變成 209517 bytes、SHA256 `1aad4b256b98337da78ba0b64baf8b0e87772bed130ca0b950d0aa38f01f8ef6`。失敗紀錄不能作為修正後候選的通過證據。
- `_child_main` 實際呼叫 `MainWindow()`；然而 V9 子程序 finally 卻以 `_build_identity_probe_events_valid(..., 0)` 要求零次身分查詢，並允許 build identity 模組未載入。這與實際主視窗建構流程矛盾，會把正常的第一次查詢判成失敗。

## 已交付修正要求

子程序須與父程序一樣驗證：恰好一次由固定來源函式、精確 root/argv/kwargs/environment 發起的 Git 查詢，在真正 Popen initializer 前以 OSError 阻擋；實際 `detect_build_identity` 回傳 truthful unverified；模組載入且來源及函式身分不變。不得放寬 foreign caller/root 或允許真 Git 子程序。

保留原失敗封套，修正後以新 pure attempt 驗證並凍結 diff、來源 pins 與 terminal/log。只有審查通過後，才執行一次完整父 Main→收藏→關閉→新子 Main→Watchlist 雙擊重開旅程。這份 QA guard 審查不構成正式 UI、EXE 或原 H20 驗收。

## 獨立身分檢查證據

Root 已直接讀取 `build_identity_only_contract_001/stdout.log`、`terminal.json` 與空 stderr。實際 `_build_identity_fallback_contract_self_test()` 回傳 `build_identity_fallback_contract_passed`，16 項 checks 全為 true：固定 root 的第一次精確查詢被阻擋於 initializer 前、實際產品回傳 unverified、外部 caller 與不同 root 拒絕、timeout/argv/environment 額外改動拒絕、child receipt identity mapping 篡改拒絕、Popen alias 復原。原 initializer attempts/completions/real Popen 均為 0。runner 212504 bytes、SHA256 `f3181d5185ef22a7dfbcb6b32fe8aef5adc73bbcda8355ce59f968e8f724df0a`；build identity SHA256 `1eb85f261306de1bfbd23e192e1c73c545f2da339795abf3be09dc92bedd0084`，封套 postflight 表示候選輸入未變。

外層 wrapper 使用錯誤的預期 status 字串，故原 terminal status failed/exit 1 保留；不得把它改寫為整次執行成功。可認可實際函式的有限範圍結果，不是完整 V9 self-test、Main 身分／收藏旅程或 EXE 驗收。

V9 pure005 在啟動前因 P01 正在修改 `personal_data_paths.py` 及 universe query 的來源 pins 漂移而拒絕；不能重釘未審來源或把未啟動解讀為測試通過。完整候選須等待 P01 受審來源固定後，再核對同一組 pins。
# V10 來源更新補充

Root 實讀 V10 runner 對 V9 差異，程式 bytes 相同；source pin manifest 僅更新已接受 `f9ead461` 的 query／paths 兩項 SHA 與 size。Root 獨立讀取並重算全部 32 項 code files，零 mismatch；原 V9 封套保留。V10 使用自身動態 QA_ROOT，不需修改產品入口。完整 self-test 尚待原始終態收據核對，沒有以 identity-only helper 代替完整契約；完整 Main／收藏／正常關閉／fresh PID Watchlist 重開仍未接受。

V10 pure001 原始 terminal 為 exit 0；Root 以 UTF-16 讀取 stdout JSON，獨立重算 SHA `9cc045183df5f038353be493a83c8fd85a18e3e00cd6ac0827be134244a412ff`。build identity 20、platform 13、runtime guard 36 項 checks 無失敗，membership 與 retirement contracts 通過；不代表 Main 已執行。Root 再讀 freeze receipt，並重算 manifest 的 13 個頂層 artifact SHA，零 mismatch。已授權固定 V10／R/J 合成來源一次完整父 Main 收藏與正常關閉、新 Job 子 Main Watchlist 雙擊重開；執行 owner 管理唯一 live handle，失敗保留，不盲重跑。

完整 attempt001 在沙箱 pinned V3 `resolve` 遭 WinError 5，尚未建立 Main；保留封套。原生 attempt002 終態 exit 1，215.87 秒：父 Main 三個 query cases、收藏、正常關閉、零 running workers 與 wrapper retirement 完成；子程序在 `child_typed_ma_bookmark_restore` 等待逾時。Root 直接讀 child receipt／stderr：來源不變、guard 還原、子 close finalizing、running workers 零；只有私有 application SQLite 接線，不能宣告 typed restore 已開始或完成。

Root 實讀 child 操作，`window.show()` 後未見把主 tab 切到 Watchlist 就對其 viewport 發送雙擊。hidden table 的非空 visualRect 不能證明能接收滑鼠事件；此為待確認的候選缺陷。下一步先核 currentWidget、祖先可見性、model row mapping、typed capture 與 operationSettled，再決定修正，不能以延長等待或重跑相同候選替代。

Root 再讀目前 `ui_qt/main.py`：主導航是 `workspace_stack`，初始 currentWidget 設為 `workbench`；既有 `_select_main_workspace("watchlist")` 才切到觀察清單並同步導航。下一候選須沿此真入口，核 currentWidget、Watchlist 及 viewport 可見後才發滑鼠雙擊；不修改產品接線、不直接 emit signal 或呼 restore 代替使用者操作。

Root 另執行隔離 Qt offscreen 表格事件探針，exit 0，無產品 import 或資料。hidden／visible 兩種狀況的單次 `QTest.mouseDClick` 均未發 `doubleClicked`；先 `mouseClick` 再 `mouseDClick` 均發一次。原始程式與結果在 `output/qa/root_qt_doubleclick_probe_20261009_a/`。因此不能把逾時單獨歸因 hidden widget；更直接的測試事件缺漏是未先建立 click。下一候選須在真可見 Watchlist 上完整發送點擊及雙擊，再核 typed route 恰一次與 generic 零；這個純探針不代表完整 Main 收藏重開通過。

Root 已讀 V11 實際操作 diff：呼叫真 workspace route、等待祖先／table／viewport 可見，核 attached model，以 dataframe position 對應 model row，先 click 核選取再 double-click，保存 typed／generic／settled events。要求修正新增 exception snapshot 的未初始化 `watchlist` 風險，避免 Main 建構失敗時以 UnboundLocalError 蓋掉原錯誤；待 compile 與 actual Qt helper 正負測，不重跑無關已綠 helper。尚未授權此 WIP 與未凍結 P01 來源組合的 native journey。


### V11 精簡操作候選審核續記

Root 已實讀 V10→V11 exact diff 與 `watchlist_activation_contract_selftest_result_002.json`。候選 SHA-256 為 `53504da96a897be7d439e5d1c5738f86158e6f677cceb9e4f010b4217000770f`；constructor 前已初始化 `watchlist=None`，原先 except 診斷遮蔽原錯的風險已修正。候選透過實際 workspace route、附掛 model 的列位置及可見 viewport，先單擊確認選取，再雙擊同列；未直接 emit 產品訊號或呼叫 restore 取代操作。

精簡 Qt 結果確認 visible table 的 clicked/doubleClicked 都是列 1、欄 0；hidden table 與 foreign model index 拒絕，產品 import、SQLite connection 與 process launch attempt 皆為 0。這只證明 QA 操作 helper，不代表完整 Main、typed MA 收藏恢復或跨程序旅程完成。來源 pins 尚待 P01 正式候選接受後重新凍結；此時不授權完整 Main 重跑。

### V11 來源重新凍結核對

P01 正式來源已精確保存於本機 dev commit `30812082`。Root 實讀 V11 source pin refresh diff，確認僅 personal_data_paths 與 snapshot repository 兩項更新至已接受 SHA，其餘 30 code pin 與 1 stdlib pin 不變。Root 獨立重新讀取 33 個檔案並比對 size/SHA，0 mismatch；source manifest SHA 為 `2dd77b76afd5a46ce9ea0ba03b49ee39e7694f4ae15e2c4d1ee5f2379e542342`。完整 Main 尚待 runner/guards/bindings 等 QA artifact freeze 核對，不以 source audit 代替跨程序收藏重開驗收。

### V11 完整旅程執行審核決定

Root 獨立核對 `final_freeze_manifest_v11.json` 中 13 個 QA artifact 的 size/SHA，0 mismatch；freeze SHA=`53f9b0d4332c620fa78bd79ebf6ffb16d3bb4b8c0e5abe31626ed53afeccf95e`。已授權 owner 以 exact runner `53504da…0770f` 執行一次 `--run` 完整 native Main 旅程，使用新 attempt，不覆蓋 V10，保留既有 300/240/180/20 秒 deadline、固定 R/J 九來源與隔離 QA 資料。失敗或 timeout 不自行重跑。此為執行授權，尚非驗收通過；必須讀回 parent、fresh child、typed/generic route、正常關閉、Job 清理及來源前後一致的實際收據。

### V11 完整隔離 Main／新程序收藏重開接受

唯一 attempt=`run_attempt_ffce90498c624514a7f3f1874b89e644`，owner session43936 terminal exit0。Root 直接讀 parent normal_ui_receipt 與 child_receipt；parent elapsed 為 78.984 秒。父 Main 的 AND／OR／OR-only 逐頁實際名單為 59／158／97，page size 50。正常關閉後 wrapper retired、最終 running workers=0。

fresh child 由 workbench 實際切到可見 Watchlist，附掛 model 單擊選取後雙擊，typed capture 恰 1、generic route=0，operation「重開四均線研究收藏」成功。恢復 page1／50、selected1000，比較籃保留1010／1000及原頁0／1；source query/page identities保持。Watchlist bytes 起訖SHA一致，固定九來源起訖一致、candidate files unchanged、guards restored、network events空。Child正常shutdown且running workers=0；Job handle closed，launcher/reporter清理後inactive，child supervision qualified=true。

Root接受本次固定合成MA完整閉環，不再重跑同一旅程。build identity仍如實unverified/unknown，不能視為發布身分。此證據不授予新EXE、原始市場來源、H20原684bp或真人接受；F12營收完整Main／新程序收藏旅程另行推進。
