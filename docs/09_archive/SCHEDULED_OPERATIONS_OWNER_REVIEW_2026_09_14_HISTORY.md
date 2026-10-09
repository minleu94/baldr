# 2026-09-14 排程與週資料受託審查

審查者：Codex（受使用者 archi 本對話委託）。審查日期：2026-09-14。

## 週收集審查決定

- Collection ID：`ewc_9b13e3a1f90bbdbe`。
- 期間：2026-09-07 至 2026-09-13；最新交易日：2026-09-11。
- 來源：`D:/Min/Python/Project/FA_Data/output/scheduled/v2_2_weekly_collection/v2_2_weekly_collection_20260913.json`。
- 宣告來源 hash：`sha256:bb378f21b2866bdb998963478bb8db078d76bac9c67ab7cd48869a7f1c7d0a85`；本次未將已變動的市場 DB 假稱為該歷史快照。
- 決定：`reviewed_with_follow_up`。收集紀錄的期間、唯讀來源、安全旗標及無錯誤欄位一致；週收集程序審查完成。
- 正式採認：未通過。收集檔僅記錄資料最大日期與來源識別，不能證明整週 quality、coverage、PIT 或逐來源 acceptance；既有 freshness 與 portfolio/risk gaps 仍在。
- 本文件為具名受託審查紀錄，不改寫 immutable collection、不冒充獨立人工 reviewer、不修改 approved projection 或 production scheduler gate。

## SQLite

早晨 log 在 04:20:15 顯示 `sync_daily_prices_to_sqlite` 因 `database is locked` 失敗。本次使用 mode=ro、query_only 連線查得 daily_prices 最大日期為 20260914、journal_mode=wal，`PRAGMA quick_check` 回傳 ok。這不等於整批 CSV/SQLite 已一致，也不將早晨失敗 status 改寫成成功。

DBManager 的等待改為 30 秒以容忍短暫 writer 競爭；長期占用仍須協調 writer，不刪除 WAL 或強制終止程序。隔離測試涵蓋競爭交易釋放後寫入及例外 rollback。

## 警告分類修正

- `forward_summary_status:INSUFFICIENT_SAMPLE` 歸入自然樣本等待。
- `position_health_baseline_is_not_an_exit_instruction` 與 `position_health_daily_refresh_does_not_evaluate_transition` 歸入 advisory。
- 缺價格、進場身分未驗證、缺 thesis、pipeline errors 與 blocking gaps 仍保留。
- 13 項 focused tests 通過；未重跑會寫入其他衍生產物的整個 scheduled wrapper。

## 持倉證據

實際 `output/portfolio/trades.jsonl` 為 2382／廣達、3207／耀勝、9935／慶豐富；三筆交易均無 source_id、source_snapshot_hash、source_summary 或 notes。Paper 的 1418 身分警告不可映射為實際持倉的出場判定。

本次未生成持倉／出場建議，未捏造歷史進場理由；後續目前時點的評估必須使用經確認的行情與明示的風險規則，並保留其產生時間，不回填歷史 thesis。

## 回滾

保留本次 diff；回滾時僅反向套用 DBManager timeout、warning classifier、測試與手冊新增段落。不得還原其他使用者變更，不涉及正式資料刪除或歷史報告覆寫。
