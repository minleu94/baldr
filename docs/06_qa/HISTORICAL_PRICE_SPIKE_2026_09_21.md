# 2026-09-21 歷史價格尖峰稽核

本次稽核針對 2026-05-20 的 1256、1477 價格異常，採唯讀 evidence；沒有寫入 formal SQLite、沒有執行修復、回填、collector 或 scheduler。原始稽核結果見 [no_merged_v2 evidence](../../output/qa/historical_price_spike_20260921/no_merged_v2/historical_price_spike_audit.json) 與 [merged baseline evidence](../../output/qa/historical_price_spike_20260921/historical_price_spike_audit.json)。

官方 response 的日期欄為 `20260520`，表題為 `115年05月20日 每日收盤行情(全部)`。完整已驗 hash response 與 canonical daily price 對照確認：

- 1256 官方／canonical：OHLC `185 / 189 / 183 / 183`，成交股數 `111,643`，方向 `-`、差 `0.50`；formal SQLite 與 corrupt backup 則為 `139 / 139 / 138.5 / 139`。
- 1477 官方／canonical：OHLC `212.5 / 217 / 210.5 / 213`，成交股數 `2,714,451`，方向 `+`、差 `3.00`；formal SQLite 與 corrupt backup 則為 `123 / 124.5 / 122.5 / 124.5`。
- canonical 全檔對照中 1,088 筆均可在完整官方 response 找到；numeric mismatch 為 0。嚴格值相等 1,082 筆，另 2 筆只有零漲跌時官方 `X` 與 canonical 空白的符號編碼差異。

5/20 的 TWSE SQLite↔canonical 差異共 868 筆，其中 865 筆為完整 numeric 差異，1538、2321、5906 為 OHLC 缺值列；三列在「官方 response 與 canonical CSV」之間的 OHLC 缺失 mask 一致，其他非缺值 numeric 欄位相等；SQLite 仍保留錯誤價格。另有 54 筆沒有 canonical 對應，維持暫不動。缺 OHLC 只記錄為缺值 evidence，不推論停牌。前後交易日及 2026 年 5–6 月其餘日期，未見同一 SQLite↔canonical 來源差異；historical backup 僅用於 5/20 的逐列對照。

官方證據是 2026-09-07 保存的 2026-05-20 retrospective capture：response／receipt hash 已驗證，但 `historical_decision_time_available=false`、`formal_training_allowed=false`、`promotion_eligible=false`；原先 33 檔 comparison custody 不包含 1256、1477，兩檔依完整 response raw rows 另行核對。因此它支持來源數值核對，不等同於當時決策時間的正式真值或已批准修復。

目前不修改 formal DB。任何修復須先由 owner 核准逐列來源與範圍，再以受控、可回滾方案執行；回滾證據與下游重算／模型影響評估另行建立，不能與來源核准混為同一步驟。

本輪 QA：historical spike focused tests `5 passed`（僅 cache permission warning），audit script 與 tests `py_compile` 通過；既有 UI0238e6b4 evidence 為 19 focused、UpdateView 84、validator 25 passed／4 skipped、mypy 638。

## Evidence

- [canonical full-response comparison](../../output/qa/historical_price_spike_20260921/official/canonical_full_response_comparison.json)
- [official capture verification](../../output/qa/historical_price_spike_20260921/official/official_capture_verification.json)
- [historical spike audit script](../../scripts/audit_historical_price_spike_20260921.py)
- [focused audit tests](../../tests/test_audit_historical_price_spike_20260921.py)

## 2026-09-22 使用者核准修復與下游邊界

使用者已核准謹慎修復，並要求一併處理既有訓練模型。上述「未修改」是前一輪唯讀稽核的歷史狀態；本節記錄後續執行，不能用前一輪結果代替修復驗收。

修復範圍固定為 2026-05-20 的 868 筆官方／canonical 可核對價格列，以及這些股票從該日起的相依技術指標。54 筆沒有 canonical 的列保持原樣。官方缺 OHLC 的 1538／2321／5906 保留 SQL NULL，不補前日價格、不補 0，也不據此推論停牌。原始 daily CSV、corrupt backup、舊模型、凍結訓練資料與歷史決策產物均保留。

### 執行前回滾清單

| 變更 | 回滾方式 | 限制 |
| --- | --- | --- |
| 價格修復工具、PIT 修訂保護與測試 | 以本任務 commit 作針對性 revert | 不覆寫其他未提交變更；資料修復後不能只移除保護 |
| `daily_prices` 868 列 | 備份保存原庫；正常回滾依 receipt 的 before／after 逐列比對、transaction 還原指定欄位 | 不能用整庫備份覆蓋後來新增的資料；遇目標欄位漂移停止 |
| 相依技術指標與可變 cache | 保存 before values／原 cache，逐列核對後恢復 | 保留 5/20 前與範圍外資料，不覆蓋後續更新 |
| 模型／PIT 修訂保護 | 保留修訂記錄，待新版本資料與模型重新驗證 | 修復價格不代表既有模型已修好；禁止把晚到修訂標成事件日已知 |

SQLite 寫入前須取得既有 heavy-chain reservation、建立包含 WAL 的 online backup、驗證 quick_check 與目標 before rows。修訂 pending marker 先於 transaction 建立；receipt 保存來源 hash、修正時間與逐列 before／after。即使 DB 已 commit 而 receipt 寫入失敗，也不能靜默讓舊 PIT 建置繼續。

### 技術指標與模型判讀

隔離探針顯示，單日更正會影響後續 MA、RSI、MACD 等；部分遞迴指標差異延續到 9/21。865 檔完整目標 OHLC 的歷史 prefix 中，102 檔仍有其他 OHLC 缺值，因此舊 calculator 的 ffill／bfill 輸出不能直接當修復值。正式重算須明確保留缺值及暖機期，不使用未來價格反向補值。全 prefix 重算與原 cache 的差異也可能包含既有 seed／warmup 差異，不全部歸因於 5/20。

目前 calibration active pointer 是 `rule_only`。另有實際每日 shadow 使用的 derived h5 release，不能因為 formal／alpha 關閉就宣稱所有模型均未使用。需分開記錄目前用途、訓練來源與時間交集、修订後是否仍允許載入；舊 artifacts 的 bytes 不修改。若模型的 feature／label 訓練來源受到影響，後續必須使用新的 dataset／run identity 重建與重訓，既有績效不得直接移植到新版本。

### 價格正式 apply 與獨立驗收

正式 apply 於 `2026-09-22T07:30:49.544569+00:00` 完成，plan hash 為 `sha256:7f899b2d93f93ed8ee7124569c645f90e3fac893ed9177599797ecca2ddd0a87`。`DATA_ROOT/output/scheduled/daily_price_repair_receipts/20260520/historical_price_spike_20260921/` 保存 `sqlite_before_repair.db`（3,600,588,800 bytes）、`pending.json` 與 `receipt.json`。Pending 留存表示來源修訂需要下游重新驗證，不代表本次價格 transaction 尚未完成。

Root 另開 `mode=ro` 連線，驗證 receipt body hash、868 筆全欄 after values 與同日非目標 fingerprint：868／868 相符、mismatch 0、非目標 hash 不變。1256／1477 的 OHLC 與上述官方值一致；1538／2321／5906 的四個 OHLC 欄均為 NULL。自動 PIT marker 與已知 shadow 模型 hash 的唯讀檢查均回報 blocked，沒有載入真實模型。

價格工具 focused fixtures `6 passed`，涵蓋來源／row drift、額外 trigger 全交易回滾、逐列回滾保留後續寫入，以及 final receipt 寫入失敗仍保留 pending；py_compile 通過。模型 gate 整合 `55 passed`，全域 mypy `639 source files` 通過。程式 hash 與 pre-apply evidence 在 [修復前記錄](../../output/qa/historical_price_spike_20260921/repair_preapply_evidence_20260922.json)，模型測試詳見[模型 QA](PRICE_REPAIR_MODEL_IMPACT_2026_09_22.md)。

相依技術指標與 CSV cache 尚待本輪後續 apply；本節不宣稱全資料鏈完成或模型已重訓。
