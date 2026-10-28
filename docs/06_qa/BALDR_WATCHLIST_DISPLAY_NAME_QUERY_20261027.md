# Watchlist 顯示名稱歷史列查詢優化（2026-10-27）

`WatchlistService.query_stock_names()` 只用來補顯示名稱。當 `daily_prices` 有完整 `(證券代號, 日期)` 複合主鍵，或有涵蓋全表、欄位精確相同且順序一致的兩欄唯一索引，而且 `證券名稱` 有 TEXT affinity 時，查詢改為每個去重後的請求代號用日期倒序索引讀取最新非空名稱。結果最多一列／請求代號，避免載入該代號所有歷史日期列。

沒有符合索引或名稱欄契約時，保留原歷史列查詢；SQLite 讀取失敗後既有 CSV／`companies.csv` fallback 順序不變。空白名稱仍按 `str.strip()` 語意略過，無名稱代號不補造；查詢仍為唯讀。這不改 Watchlist 收藏身份、金融來源資格或 UI 結果。

測試增加有索引與無索引 schema，分別核對多日期、最新空白／NULL 後回退到最新非空名稱、缺少代號、重複請求代號與 SQLite 檔案唯讀。聚焦名稱查詢測試 2 passed；修正 Decision Desk stale async 測試 fake `Worker` 缺少 `native_thread_finished` 後，整個 `tests/test_task_loop_07_contract.py` 為 22 passed。Targeted mypy 與 `py_compile` 通過。

另外在暫存合成 SQLite 上，以舊的載入所有匹配歷史列查詢作為基準，和新索引查詢交替各量 30 次（先 warm-up；80 個唯一請求代號，輸入含重複及不存在代號；最新名稱含 NULL／空白並核對回退）。20,000／100,000／400,000 筆歷史列的 p50 為 1.375→0.722 ms、2.730→0.689 ms、7.105→1.182 ms；p95 為 1.760→0.955 ms、3.774→0.966 ms、7.948→1.546 ms。三種資料量新舊輸出 digest 相同，查詢計畫顯示按證券代號使用 SQLite 主鍵索引。完整樣本與執行收據記於工作區 `output/tasks/watchlist-display-name-query-20261027/evidence/watchlist_name_query_synthetic_ab.json` 及相鄰 `single_owned_qa_*` 目錄。

這是唯讀合成資料、service query 微基準；不含正式資料庫 I/O、UI paint、啟動流程或 DannyQuant 對照，不能推論使用者可見延遲比例，也未宣稱端到端速度已勝過 DannyQuant。正式 DB／啟動延遲仍待測。Feature map、UI features、QA index 與本次文件的 scoped document link check 通過；task-wide document-control check 仍回報 Snapshot 四個缺少錨點、既有文件指向被排除的 `output` 儲存 junction，以及四份必要文件未列入 task manifest，不宣稱 repo-wide document check 全通過。
