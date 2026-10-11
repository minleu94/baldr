# F12 月營收來源批次中央複驗

狀態：current-only 來源與生命周期批次通過；完整母體 query／UI、正常更新閉環與正式 PIT 尚未完成。

`DailyMarketMonthlyRevenueReadSessionV1.open(provider, snapshot_root=..., stock_codes=..., cutoff_at=..., cancel_callback=...)` 沿既有 `FundamentalReadSnapshotSession` 與 fundamental provider 使用唯讀副本。完整、固定排序的 declared 清冊逐批 `load_batch()`；批次仍是 provisional，只有完整 `finish()` 回傳 reader-issued cohort。未完成或取消不得發行完成 token。

每檔保留 current／合格同比 comparator、Decimal 數值、期間、單位、來源版本、原 HTML SHA、觀察與可得時鐘、診斷及來源狀態。provider 拒絕的零值／負值／缺值另存 raw comparator evidence，不升格為合格基期；只對同次已核的 exact HTML pin 重用既有 parser。不新增 YoY、推薦或收益公式。

來源固定 `current_observed_only`、availability unknown、historical/formal PIT false。aware cutoff 與未來 revision prefix 測試只證本次觀察隔離，不能冒充官方公布時間。JSON decoder 僅產生未重新核來源的 `UnverifiedMonthlyRevenueArchiveV1`；自洽重新雜湊不能簽發來源資格。

新增 snapshot public `close()`／context manager：跨執行緒 cancel 只送取消訊號，唯讀 SQLite 由 owner thread 關閉。成功 finish 保留完成 token；失敗與 context cleanup 的 primary／secondary 例外一起保留。publication lock 內不呼叫外部取消 callback，避免自取消鎖死。

## 獨立固定版本證據

Root 在 native 環境執行完整 P03 32 項、生命周期 5 項、月營收 8 項，共 **45 passed／3.45 秒**；兩個來源模組 mypy clean。正式收據 `output/qa/F12_MONTHLY_REVENUE_SESSION_20261008_A/root_frozen_review_1791506219482930300.json`，兩份 log 為同目錄 `root_combined45_1791506219482930300.log`／`root_mypy_1791506219482930300.log`。收據四檔前後 SHA 一致：

- snapshot：`d8b65a2df3a22c3aca971c5b44b4945d2163d2b739c1588138f4e9a3ce4fa5ca`
- monthly wrapper：`b8419e8c78c29616c01b988cd08c8161b46e62c16769badda575d8a3d3da599a`
- lifecycle test：`1e76a6e835ae59ee436e75ca25a68cf9bd55eb96d748cdf4055c03abbd4d727d`
- monthly test：`368a0616b6927bc04ba99264c308ac4c1f93ca0be4c44383ee0de44eb9796e08`

早期零基期來源 reference 對應錯誤、callback 測試預期及 archive 信任範圍錯誤已經修正；受限 sandbox 的 WinError 5 失敗保留，未靠移除來源核驗解決。

下一批需將 reader-issued 全清冊事實接到版本化 compact index 與複合查詢，重用既有 Decimal 投影，保存各域來源身份、完整分母與 unknown／blocked。不能以這個獨立讀取器宣稱 F12 選股條件、UI、跨程序還原或全補完計畫完成。

## 後續索引／查詢整合狀態（2026-10-11）

上段列出的 reader-to-index/query 工作，已由後續 `BALDR_F12_INDEX_INTEGRATION_REVIEW_20261009.md` attempt03 與 `F12_MONTHLY_REVENUE_QUERY_READER_20261009.md` 取得 bounded 合成驗收：258 declared、257 processed、1 excluded，8 passed。這更新的是 full-population synthetic reader/query 切片；current-observed-only、availability unknown、PIT false 仍保留，不能外推為正式市場或完整產品通過。

後續 `BALDR_F12_MAIN_INTEGRATION_REVIEW_20261009.md` 的真來源 UI／worker attempt04 有界通過，但不是完整 Main constructor。F03 root follow-up 的 T38 full Main 仍於收藏前 `unexpected_private_sqlite_uri` 失敗，child 與新程序 typed reopen 未到達；正常更新閉環、完整 Main／收藏、EXE、真人與正式 PIT 尚未因此完成。
