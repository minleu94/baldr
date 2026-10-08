# H20 固定版本建置工具審核

建置工具 SHA `9698340c28cbbfd369585c9212f1632846c2c7b16addc8b674c5e0eb2fc177b2`、測試 SHA `d62abba3dc0538f118b35a1d5b1c518ee9ee9300e29a82a5391b8a7f53123641`。中央獨立執行3項測試，exit0、2.96秒，收據 `output/qa/h20_immutable_snapshot_builder_20261008_a/root_builder_tests.log`。

測試用合成 Git repository 明示基準 commit與overlay，產物交給固定 supervisor 的 `verify_source_snapshot()` 和 `_load_launch_inputs()` 真入口，沒有以建置工具自驗取代consumer驗證。未列的工作樹檔案不進入封套；來源樹漂移、缺必要依賴pin、錯approval SHA、overlay來源漂移與基準檔SHA不符均拒絕。Main與MA全旅程接受狀態獨立保存，不由建置成功推定。

實際待建置基準為 `396c08e8f16c0d6e0ec2807e15aee387e56ca60e`，包含完整推薦理由修正。中央已固定9個明示runtime dependency副本與22個基準檔指紋，位於本機 `output/qa/h20_root_dependency_inventory_20261008_a/`。此盤點不是啟動核准；正式launch source groups仍需由既有來源收據明列，不由建置器掃描或讀取原SQLite。

本輪僅授建置格式與版本固定契約，尚未產生原H20同版流程通過、候選EXE或真人驗收結論。後續仍須載入原保存名單、2382下鑽、同源摘要與圖表、返回選取及收藏重開的實際證據。
