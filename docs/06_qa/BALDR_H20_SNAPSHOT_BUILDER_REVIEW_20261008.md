# H20 固定版本建置工具審核

建置工具 SHA `9698340c28cbbfd369585c9212f1632846c2c7b16addc8b674c5e0eb2fc177b2`、測試 SHA `d62abba3dc0538f118b35a1d5b1c518ee9ee9300e29a82a5391b8a7f53123641`。中央獨立執行3項測試，exit0、2.96秒，收據 `output/qa/h20_immutable_snapshot_builder_20261008_a/root_builder_tests.log`。

測試用合成 Git repository 明示基準 commit與overlay，產物交給固定 supervisor 的 `verify_source_snapshot()` 和 `_load_launch_inputs()` 真入口，沒有以建置工具自驗取代consumer驗證。未列的工作樹檔案不進入封套；來源樹漂移、缺必要依賴pin、錯approval SHA、overlay來源漂移與基準檔SHA不符均拒絕。Main與MA全旅程接受狀態獨立保存，不由建置成功推定。

實際待建置基準為 `396c08e8f16c0d6e0ec2807e15aee387e56ca60e`，包含完整推薦理由修正。中央已固定9個明示runtime dependency副本與22個基準檔指紋，位於本機 `output/qa/h20_root_dependency_inventory_20261008_a/`。此盤點不是啟動核准；正式launch source groups仍需由既有來源收據明列，不由建置器掃描或讀取原SQLite。

本輪僅授建置格式與版本固定契約，尚未產生原H20同版流程通過、候選EXE或真人驗收結論。後續仍須載入原保存名單、2382下鑽、同源摘要與圖表、返回選取及收藏重開的實際證據。

## 具名來源新盤點與 WAL 缺口

新收據 `output/qa/h20_named_source_inventory_20261008_b/attempt_01/inventory.json` SHA `63807dceecb8e6533e05705cf6f4206fc22e33ae3012eadf10d9c1a908030f57`：34個明示檔案共8,119,597,120 bytes，前後檔案身分一致。盤點沒有 SQLite 連線或資料庫複製，未掃描 DATA_ROOT。歷史10/7名單、10個capture與明示H20 snapshot main SHA吻合；日曆及市場資料庫指紋屬此次新盤點，不冒充歷史證據。

市場 DB 的 WAL 為1,021,792 bytes，不能把只複製main的結果當一致快照。後續先用隔離合成非空WAL驗證安全讀取方案，尚未批准原市場DB快照或H20 Main執行。盤點程序exit1的終態診斷已另存：完整盤點落盤後，wrapper將預期的SystemExit(2)捕為例外；原failure與收據均保留，沒有以重跑覆寫失敗。
