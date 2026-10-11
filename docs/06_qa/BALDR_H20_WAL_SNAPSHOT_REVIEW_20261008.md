# H20市場副本的非空WAL方案：合成中央審核

> **時點／範圍：**本文記錄 2026-10-08 至 10-09 的合成 SQLite WAL snapshot 方案與隔離測試；不代表 D Main 或完整產品旅程已執行。其他固定來源／Main 路徑需由各自收據判讀，不能把本文件的合成結果轉移為其接受證據。

此驗證限定全新隔離合成SQLite；不是原市場DB、H20 Main、候選EXE或真人接受。原凍結bridge／child／supervisor沒有因此修改或取得啟動資格。

helper SHA `169fa40c6c87c68268bfe40caf361f54618732e685adca02fd9de931c373221f`，runner SHA `a46d2eda07ce3f85dc476940827007e8d4bcb64fef87c91b5a501f37c024c713`。中央獨立native重跑exit0，log `output/qa/h20_wal_snapshot_20261008_a/root_wal_selftest_native.log`；receipt `attempt_receipt_20261009T000230Z_db4419c137f2/receipt.json` SHA `60e78b8b5b8b4e96bee719a1c4a2f77af50b818bfc61613870c52982269021e6`。

方案固定原main／WAL位元組與起訖檔案身分，SHM僅核metadata及inode；只把main／WAL複製到自有隔離目錄。SQLite在副本重建私有SHM，再以唯讀交易backup產生合併快照，不以immutable旗標忽略WAL。合成已提交資料進入backup，未提交資料沒有進入；來源未由SQLite連線。

來源漂移、損毀WAL、缺SHM、rollback journal、容量超限、中途取消、未知私有檔案及同位元組換inode負例保留。中央實際junction reparse拒絕也通過。來源漂移與cleanup身分置換同時發生時保留primary `source_file_group_changed_during_snapshot`，secondary另列 `owned_copy_artifact_identity_changed`，不刪除未知replacement或舊inode。

先前沙箱路徑權限、目錄mtime被誤當身分、Windows live SHM無法串流及cleanup遮蔽primary的失敗attempt均保留。此原型的單一fixture表格oracle不能直接授原twstock全庫接受；實際接線還需完整backup／schema／consumer核驗、區分原main與derived snapshot SHA，以及市場與H20兩份獨立來源的總容量與終態清理。

另已確認凍結啟動契約的輸出根矛盾：supervisor要求 `H20_GUARD_OUTPUT_ROOT=OUTPUT_ROOT=attempt/output`，child及legacy probe卻再接一層output。後續採新版本副本明示CASE_ROOT與OUTPUT_ROOT，經真子程序環境解析驗證後才接原來源；不篡改舊凍結封套。
# WAL market bridge 合成契約補記（2026-10-09）

Root 獨立執行 `output/qa/h20_wal_market_bridge_20261009_a/test_wal_merged_market_bridge_qa.py`，terminal exit 0，6 passed／0.76 秒。六份收據位於該目錄 `attempts/*_20261009T002326Z_*/receipt.json`，逐份確認正／負案例通過、來源 SQLite 連線數為 0、操作副本已清理。

範圍包括多表與多執行緒同一 merged snapshot、第三資料庫／連線參數／SQL 寫入拒絕、長查詢 progress-handler 取消、連線 opening reservation 阻擋 finish、來源變動與 merged snapshot 竄改拒絕。原 main/WAL pins 與 merged snapshot SHA 分別保留，不冒充 `PinnedSQLiteReadSession`。

凍結 adapter SHA `0de4a00d94746da5d9027fe0c870d11cd684822b745569a6864d623f609a37f2`；test SHA `219da364967616861b6e6273a60ea1a3c74b39d47346c50399ea92e4ce975b10`。

此 adapter 仍委派原合成 WAL helper，其 `create_merged_snapshot()` 核驗查詢寫死 `market_prices`。所以六項通過不能證明實際 twstock schema 相容。下一個必要候選須移除測試專屬 row oracle，以通用 backup／integrity／schema 核驗與應用 logical-row 核驗分層，並用完全不存在 `market_prices` 的合成市場資料驗證。未啟動 Main／EXE、未連線原始資料庫，也未授予原始 H20 完整旅程接受。

## 通用 WAL helper 與橋接複驗

另建 `output/qa/h20_wal_market_bridge_20261009_b/`，保留 a 的凍結版本。b helper 移除應用資料表專屬查詢，核對整庫 backup、integrity、完整 schema 與原 main/WAL；應用列核驗由消費端負責。backup 加入 progress callback 取消與 monotonic deadline。

Owner 8 passed／1.28 秒；Root 獨立 native 執行 `test_wal_merged_market_bridge_neutral_qa.py`，terminal exit 0、8 passed／1.47 秒。八份 Root 收據為 `attempts/*_20261009T002916Z_*/receipt.json` 加 `backup_deadline_20261009T002917Z_b5d78227132b/receipt.json`；逐份確認成功正／負案例、來源 SQLite 連線 0、操作副本已清理。覆蓋沒有 `market_prices` 的五表合成市場 schema、備份途中取消與 deadline，以及 a 的連線、SQL、執行緒與來源變動限制。

凍結 SHA256：helper `0480f1ced50d05481a62d6e19c636d259ee23976289162d40076a96d66783bb4`；bridge `73bf9294f6d74f880bf77ec1bd85b7e746a0b80d7c4b4487313ff7ff875f498c`；test `44fced3cab90727c3b83a99f0965ddc5d7c8bb37dae20cf29bfab09df7fe0230`。collection import 與 schema descriptor 範圍不同的早期失敗均保留。此證據補足測試表依賴與 backup 取消缺口，仍不是實際市場 provider、雙來源 Main 旅程、原始 H20 或 EXE 接受。

## 外層 dispatcher 接線前的 attachment 核驗

Root 獨立 native 執行 c 候選的 `test_wal_market_dispatcher_composition_qa.py`，terminal exit 0，3 passed／0.55 秒（工具輸出 f09de9）。閱讀測試後確認：三例直接使用 market operation 的 owner-issued attachment 與 `open_connection()`，涵蓋精確 URI、錯誤 token／原庫路徑拒絕、跨執行緒連線未關閉時拒絕 detach，以及正常 finish／副本清理。

三例沒有實例化或安裝 `_DualSQLiteRouter`，也沒有同時走 H20 與兩個 runtime DB 路由，因此只能授予 market attachment 契約證據，不能稱為外層雙來源 dispatcher 或 Main 旅程通過。後續須以真 router 經公開 `sqlite3.connect` 與 `sqlite3.dbapi2.connect` 核驗四條資料庫路由及拒絕、hook 還原、連線關閉，再進行真 Main 合成旅程。原始來源仍未啟動。

## 真外層路由合成複驗

新 d 候選保存 c 前像與失敗收據，移入已審 CASE_ROOT／OUTPUT_ROOT 契約，修正 Windows concrete Path 核對及私有 copy 初始化前不得讀 active-only 公開 getter 的時序。Root 初輪 5 passed／2 failed 收據仍保存；後續測試補齊 H20 copy／finish 生命週期，不放寬 terminal 對單一 H20 來源的要求。

Owner native 7 passed／0.73 秒。Root 依交付四檔固定 SHA 獨立執行七項，exit 0、7 passed／0.79 秒、四檔前後 pins 完全一致；收據 `output/qa/h20_dual_sqlite_readonly_main_20261009_d/root_frozen_router_review_1791507394490505500.json`。覆蓋 root/output 正例與錯配拒絕、真 router 的 market／H20／兩個 runtime DB、原始／未知／第三 runtime 路徑拒絕，以及 native 連線未關閉時拒絕 finish、關閉後清理與還原 hooks。Runtime delegate 使用合成精確路徑 adapter；此處不是 legacy guard 完整 Main 啟動驗收。

固定 SHA：child `1cfaf5eb3a0be649f5a993c9f3381db125d55e351c5d2c22121a26bad7f0399a`；bridge `864301254a2f930e6680b2f523b54a88bc3bb8fefb80df7805de8b307589ba27`；helper `0480f1ced50d05481a62d6e19c636d259ee23976289162d40076a96d66783bb4`；test `38074366b866d61d02a8acc62001d8295d5ba95f2edf6a9110c4a0acf52179ca`。下一步是真 Main 雙來源合成旅程與固定源封套；原始 H20、EXE、真人及效能接受仍待。
