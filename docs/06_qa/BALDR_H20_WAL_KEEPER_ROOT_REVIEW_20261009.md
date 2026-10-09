# H20 合成 WAL keeper：Root 小測複核

這份紀錄只涵蓋隔離合成行情庫的 WAL 準備與複製，不代表 Main 視窗流程、原 H20 2382、收藏重開或 EXE 已通過。

Root 實讀 `output/qa/h20_wal_keeper_candidate_20261009_a/market_wal_keeper_qa.py` 的開啟邊界與 `selftest_native_attempt05.log`。小測實際為 6 passed、0.97 秒、exit 0；log SHA-256 為 `4d735a80489f961f447d9c0951123c03ca634019f5e8d40d6bd73ff5004218b7`。當時 keeper SHA-256 為 `d3982c5f42555b0fbb207ec2c9414df60824c8e81dc034fc720915a090cdad73`。

先前兩個阻擋項已有具體修正：

- 寫入前要求 caller 傳入 `expected_qa_root`，限定既存 `C:/t/h20dual_*` 的精確 case 子根；manifest、行情庫與 H20 庫都要符合固定來源路徑。目錄祖先、reparse、檔案身分、來源 hash、原有 sidecars 與 DATA_ROOT/OUTPUT_ROOT 重疊在 SQLite 寫入連線前檢查。JSON 的合成標籤本身不構成寫入授權。
- preparer 的 readback 是 dict rows，keeper 按精確鍵與型別解析，再與行情庫實際價格列比較；不再把 dict 誤當 tuple 取索引。合成 schema 補齊既有 bridge 要求的核心表，未放寬 frozen bridge。

Root 另讀六項測試的名稱與斷言：committed WAL 保留、未提交列排除、DELETE journal 拒絕、中途取消清理、manifest 漂移主錯保留、精確 dict schema，以及指向第二個隔離合成根的偽造 manifest 在 SQLite connect 前拒絕。越界負例明確追蹤零 connect calls 並比對另一合成庫起訖檔案 pin。這些小測尚不等同完整視窗流程證據；後續須核 frozen receipt、candidate diff 與 controller 的 keeper finally 生命週期，再執行新 Main case。既有失敗 attempts 保留，正式資料未作為此小測輸入。
