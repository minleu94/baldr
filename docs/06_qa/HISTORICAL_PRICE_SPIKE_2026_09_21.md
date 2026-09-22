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

價格階段完成後，相依技術指標與 CSV cache 另依下節方案完成受控 apply；模型仍須使用新版本重建驗證，沒有重訓或解除隔離。

### 衍生資料修復的驗收條件

技術指標修復使用每檔股票完整 OHLC prefix 計算，但只更新 5/20 起既有的技術指標列。任一 OHLC 缺值即切段，下一段重新暖機；不使用 ffill、bfill 或補零。ATR 不在本次重算白名單，其他未知欄位與 5/20 前的指標保持原樣。這是供目前研究使用的事後重算，不把 9 月才取得的更正視為 5 月已知。

CSV 必須獨立保存原值，不能借用 SQLite 的 before values：五檔抽查發現 CSV 的 OHLC 為舊錯價，而技術指標表的中英文 OHLC aliases 是 NULL；MA5／ADX 則一致。彙總 `all_stocks_data.csv` 沒有 ADX 欄位，修復不得因此新增欄位。個股與彙總快取只處理既有日期／欄位交集，同一價格的中英文 aliases 須一致；原始 `daily_price/*.csv` 與 `stock_data_whole.csv` 不在快取修復範圍。

套用前須驗證計算使用的完整 daily OHLC prefix hash、逐欄 before values、剩餘磁碟容量及 online backup。CSV 分檔備份與修改 journal 必須保留各自原值及 hash；若部分檔案已替換而後續失敗，應依 journal 回復該批指定欄位，不以整庫或整檔舊備份覆蓋其他後續資料。最後逐欄讀回與 receipt 驗證通過，才可宣稱衍生資料修復完成。

抽查 evidence：[技術表與 CSV 結構／數值對照](../../output/qa/historical_price_spike_20260921/technical_cache_schema_comparison_20260922.json)、[研究報告實際讀取服務驗收](../../output/qa/historical_price_spike_20260921/stock_research_consumer_readback_summary_20260922.json)。後者涵蓋 1256／1477 及三檔官方缺價股票的 5/19、5/20、5/21，共 15 組讀取，並非僅驗證原始 SQL。

### 技術指標與快取正式 apply

`7aebf678` 保存已審查的修復工具與 13 項 focused fixtures；涵蓋分段暖機、來源漂移、CSV 個別原值、部分發布失敗、程序中止恢復與 final receipt 失敗後補寫。獨立 delta review 通過，py_compile、diff-check 與 quant guard（financial-float／look-ahead）通過；見[凍結程式 QA](../../output/qa/price_repair_20260921/technical_frozen_qa_summary_20260922.json)。未修改本次工作區中另一個 UI 任務的程式。

正式 apply 於 `2026-09-22T08:26:37.224486+00:00` 完成。計算來源為 868 檔、2,622,006 筆完整日期／OHLC prefix；修復範圍含 75,442 筆既有 technical rows，自 5/20 起更新 1,257,696 個指標欄位與 19,439 個來源欄位，合計 1,277,135 個 DB 欄位。138 筆受缺值影響的列保留 NULL；全 prefix 有缺 OHLC 的 279 檔與先前較窄探針的 102 檔範圍不同，不能直接相減或視為新增異常。

869 份既有個股／彙總快取已發布，共處理 1,912,408 個欄位；這個計數包含已等於目標值的欄位，不等同於實際數值差異數。快取未涵蓋的日期及沒有的欄位維持不新增，receipt 分別記錄 missing cells 與 skipped columns，不能解讀成快取已補齊所有歷史日期。原始 daily CSV、`stock_data_whole.csv`、模型與歷史訓練產物保持原樣。

`DATA_ROOT/output/scheduled/technical_indicator_repair_receipts/20260520/historical_price_spike_20260921/` 保存 online backup、逐檔 cache backup、cell journals、pending 與 final receipt。Final body hash 為 `sha256:773795469f91ea7c526ef0237b3ce2feb886deb713e6ba970b0c45672292ce32`；technical backup hash 為 `sha256:c9e237273ae039e10817cd5d548c0b53abbbc64771d2c993bce7e370bdf74387`；使用的 dry-run manifest hash 為 `sha256:7cabe725d520bc68a5d8267bb5cb70daf471341f7b6a7d9aace19432580678cd`。Pending 狀態為 `receipt_written`，不表示仍有未提交 transaction。

精確執行命令、程式／輸入 hash、容量預檢與測試結果見 [technical pre-apply evidence](../../output/qa/price_repair_20260921/technical_indicator_preapply_evidence.json)。修復保留至少 200 GiB 磁碟餘裕；執行紀錄見 [apply log](../../output/qa/price_repair_20260921/technical_indicator_apply_20260520.log)。

獨立唯讀驗收另以 manifest 建立預期值，核對 868 檔：1,277,135 個 after cells 全部相符；同批受影響列中 2,117,755 個非修改欄位與修復前備份一致；869／869 快取 after hashes 相符，receipt、manifest 與 technical backup hash 均通過。SQL 使用既有索引，沒有逐股 CAST 全表掃描。完整結果見[獨立驗收](../../output/qa/price_repair_20260921/technical_indicator_repair_verification.json)。驗收程式最初的備份讀取權限與前導零代碼正規化問題已修正；未以 immutable fallback 或改動正式資料讓驗收通過。

驗收範圍不包含整個歷史資料庫或全部來源完整性認證。抽查發現 1538／2321／5906 的部分非 5/20 CSV 價格／符號與 daily NULL 不同；這些來源欄位不在本次 5/20 修復 allowlist，不能把此次通過解讀成所有日期的舊 CSV 補值問題均已排除。三檔的 5/20 官方缺價與本次指標 NULL 政策仍依修復清單驗證。

五檔補充抽查確認上述 19 個來源差異為修復前既有值：225 個選定 cache 欄位與各自備份逐欄比較均未改動。彙總快取尾端可見日期為 2026-06-29，不能把要求的 9/21 缺列當作此次修復新增的差異；其 920,610 個缺列欄位維持跳過，ADX 原本缺欄的 75,442 個位置也未新增。這些限制與 scope 外差異保存在[consumer baseline 補件](../../output/qa/price_repair_20260921/technical_indicator_repair_consumer_baseline_20260922.json)，後續需另做來源核對，不能直接以舊 CSV 補值作正式價格或訓練真值。
