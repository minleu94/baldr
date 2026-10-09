# 資料文件導覽

> 先依任務閱讀本頁，再進入專題文件。即時狀態與操作以 Snapshot、系統架構及操作手冊為準；日期化盤點只代表文件標示的盤點時點。

## 日常更新與排錯

- [每日更新快速指南](HOW_TO_UPDATE_DAILY_DATA.md)：一般每日更新入口。
- [每日資料更新詳細指南](daily_data_update_guide.md)：資料源更新、capture／projection、結果判讀與更新流程。
- [每日更新排錯](../07_guides/APPLICATION_MANUAL.md#12-常見問題)：目前故障排除入口；操作邊界見手冊第 4 節。
- [資料獲取邏輯](DATA_FETCHING_LOGIC.md)：來源、請求及擷取邏輯；實際操作仍以操作手冊與最新程式行為為準。

## 流程、重建與儲存

- [目前推薦分析與 SQLite 資料保存邊界](../01_architecture/system_architecture.md)：模組、資料來源、時間截止、技術指標重用與 read/write 邊界。

## 來源資格、保留與資產盤點

- [基本面來源盤點入口](FUNDAMENTAL_SOURCE_INVENTORY.md)：短導引連到目前狀態、現行架構及來源 QA；Month 5 詳細盤點已封存。
- [備份保留稽核](BACKUP_RETENTION_AUDIT_2026_07_06.md)：保留策略及 2026-07-06 來源掃描；容量／檔案現況以更新的資產登記為準。
- [資料資產用途與恢復登記](STORAGE_ASSET_REGISTER_20261006.md)：2026-10-06 的用途、保留與恢復快照；不是即時容量清單。
- [歷史測試資料集中清冊](HISTORICAL_TEST_QUARANTINE_20261006.md)：記錄 2026-10-06 提案及當時未執行狀態；不可據此推定資料已搬移。
- [月營收公告日 mapping 範本](templates/monthly_revenue_availability.csv)：欄位範本，不是正式公告日資料。正式路徑由資產登記與操作手冊指示。

## 歷史實作摘要

以下一次性摘要與舊版架構指南不作目前操作依據。原文已移至封存區，舊路徑保留導引：

- [產業指數更新摘要（歷史）](../09_archive/INDUSTRY_INDEX_UPDATE_SUMMARY_HISTORY.md)
- [合併與大盤指數摘要（歷史）](../09_archive/MERGE_AND_MARKET_INDEX_SUMMARY_HISTORY.md)
- [SQLite 雙軌相容指南（2026-06 歷史版）](../09_archive/SQLITE_STORAGE_GUIDE_HISTORY_20260602.md)
- [CSV 全量重建指南（歷史版）](../09_archive/DATA_REBUILD_GUIDE_HISTORY.md)
- [舊版推薦分析流程（歷史）](../09_archive/RECOMMENDATION_ANALYSIS_DATA_FLOW_LOGIC_HISTORY.md)：保存舊 CSV／`ui_app` 流程；現況請讀上方系統架構。
- [每日更新故障排除舊指南（歷史）](../09_archive/TROUBLESHOOTING_DAILY_UPDATE_HISTORY.md)：保留舊路徑與命令作為追溯；目前排錯請看操作手冊第 12 節。

現行使用方式請看 [操作手冊](../07_guides/APPLICATION_MANUAL.md) 與上方每日更新指南；現行模組邊界看 [系統架構](../01_architecture/system_architecture.md)。
