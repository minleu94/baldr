# 2026-09-21 歷史價格尖峰稽核

本次稽核針對 2026-05-20 的 1256、1477 價格異常，採唯讀 evidence；沒有寫入 formal SQLite、沒有執行修復、回填、collector 或 scheduler。原始稽核結果見 [no_merged_v2 evidence](../../output/qa/historical_price_spike_20260921/no_merged_v2/historical_price_spike_audit.json) 與 [merged baseline evidence](../../output/qa/historical_price_spike_20260921/historical_price_spike_audit.json)。

官方 response 的日期欄為 `20260520`，表題為 `115年05月20日 每日收盤行情(全部)`。完整已驗 hash response 與 canonical daily price 對照確認：

- 1256 官方／canonical：OHLC `185 / 189 / 183 / 183`，成交股數 `111,643`，方向 `-`、差 `0.50`；formal SQLite 與 corrupt backup 則為 `139 / 139 / 138.5 / 139`。
- 1477 官方／canonical：OHLC `212.5 / 217 / 210.5 / 213`，成交股數 `2,714,451`，方向 `+`、差 `3.00`；formal SQLite 與 corrupt backup 則為 `123 / 124.5 / 122.5 / 124.5`。
- canonical 全檔對照中 1,088 筆均可在完整官方 response 找到；numeric mismatch 為 0。嚴格值相等 1,082 筆，另 2 筆只有零漲跌時官方 `X` 與 canonical 空白的符號編碼差異。

5/20 的 TWSE SQLite↔canonical 差異共 868 筆，其中 865 筆為完整 numeric 差異，1538、2321、5906 為 OHLC 缺值列；三列兩來源的 OHLC 缺失 mask 一致，其他非缺值 numeric 欄位相等，沒有 numeric mismatch。另有 54 筆沒有 canonical 對應，維持暫不動。缺 OHLC 只記錄為缺值 evidence，不推論停牌。前後交易日及 2026 年 5–6 月其餘日期，未見同一 SQLite↔canonical 來源差異；historical backup 僅用於 5/20 的逐列對照。

官方證據是 2026-09-07 保存的 2026-05-20 retrospective capture：response／receipt hash 已驗證，但 `historical_decision_time_available=false`、`formal_training_allowed=false`、`promotion_eligible=false`；原先 33 檔 comparison custody 不包含 1256、1477，兩檔依完整 response raw rows 另行核對。因此它支持來源數值核對，不等同於當時決策時間的正式真值或已批准修復。

目前不修改 formal DB。任何修復須先由 owner 核准逐列來源與範圍，再以受控、可回滾方案執行；回滾證據與下游重算／模型影響評估另行建立，不能與來源核准混為同一步驟。

本輪 QA：historical spike focused tests `5 passed`（僅 cache permission warning），audit script 與 tests `py_compile` 通過；既有 UI0238e6b4 evidence 為 19 focused、UpdateView 84、validator 25 passed／4 skipped、mypy 638。

## Evidence

- [canonical full-response comparison](../../output/qa/historical_price_spike_20260921/official/canonical_full_response_comparison.json)
- [official capture verification](../../output/qa/historical_price_spike_20260921/official/official_capture_verification.json)
- [historical spike audit script](../../scripts/audit_historical_price_spike_20260921.py)
- [focused audit tests](../../tests/test_audit_historical_price_spike_20260921.py)
