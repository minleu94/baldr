# A01 BBANDS30 上軌工程驗證（2026-10-06）

固定 base：`36dc1baf740007834f385ff0f654c7fe268a36f3`。隔離分支：`lane/baldr-a01-bbands-upper-20261006`。本包完成有限 `close > BBANDS30 upper` 的版本化來源、保存及研究投影；驗證使用隔離 synthetic fixture，不作正式產品或模型資格證據。

## Ownership 與來源

原排他範圍為 method contract、feature snapshot、research screener、research capabilities、cohort projection 五檔，以及新增測試和本紀錄。中央 owner `01a11020-88c2-7506-acc3-d51ecb674032` 已批准擴鎖：`stock_research_report_service.py` 僅 `_read_technical` 的 BB 欄位讀取；另含 `daily_market_snapshot_source.py`、`daily_market_snapshot_producer.py`、`daily_market_snapshot_repository.py` 的 opt-in、version-aware 增量。未修改 dev、config/main、consumer composition、正式 Task、Manual 或原 plan。

既有 `analysis_module/technical_analysis/technical_indicators.py:calculate_causal_indicators` 使用 `BBANDS(timeperiod=30, nbdevup=2.0, nbdevdn=2.0, matype=SMA)`，按連續有效 OHLC 區段計算；technical analyzer 將 `upperband` 保存為 `BB_Upper`。本包讀取既有欄位，不重算 band、不新增核心裸 float。程式來源不等於每筆資料參數 lineage 證明，`parameter_lineage_verified` 保持 false。

決策只讀截止日資料，要求 close 與 band 日期、來源、品質相符及 30 筆連續有效 OHLC warmup。缺值、非有限值、無效來源／日期、重複日或 warmup 不足均為 unknown。使用 Decimal 嚴格比較：大於成立，等於不成立。availability/calendar/historical PIT 及 formal/model 資格不升格。

## Frozen API

- 舊預設 `daily-market-feature-snapshot.v2`、`close/MA20/MA60`、兩個 MA registry 及 legacy payload 保留。
- 新常數 `DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER` 為 `daily-market-feature-snapshot.v3.bbands30-upper`，增加 `BB_Upper` 與 `close_above_bbands30_upper`。
- `feature_contract_for_version(version) -> DailyMarketFeatureContract` 為 frozen dataclass，提供 version、feature/condition keys、canonical method JSON/hash；`.method_contracts` 回傳 detached dict。
- `method_contracts_payload(*, include_bbands30_upper=False)` 明確 opt-in，拒絕非 bool。
- `DailyMarketFeatureSnapshotService.project`、`daily_market_feature_input_fingerprint`、`DailyMarketSnapshotProducer.produce` 接受 keyword `contract_version=None`，預設解析舊 v2。
- source `load/load_input`、stock reader `_read_technical`、screener `produce_snapshot` 接受 keyword `include_bbands30_upper=False`。screener readback 依保存版本重新讀取及核對來源 fingerprint。
- method id `daily_market.close_above_bbands30_upper`；family `close_vs_bollinger_upper`；version `1.0.0`；required fields `close/BB_Upper`；參數 30、`"2.0"`、`"2.0"`、SMA、above。
- repository 接受精確 v2/v3 schema 與各自 method binding。v2 加入 BB 或 v3 缺少 BB 均拒絕，跨版本不能 reuse。未綁定 method metadata 的新 BB 條件維持 unknown；舊 MA minimal payload 行為保留。

## 驗證與證據

相鄰基線：43 passed / 2.99 秒。最終固定 source 的受影響範圍：**155 passed / 7.75 秒**，含新測試 24 cases、原五個 owner 模組、producer/repository/consumer 與 stock report 測試。未跑全倉 gate。

raw/JUnit 位於 repo 根目錄 `output/qa/baldr_a01_bbands_upper_20261006/final.txt`、`final.xml`。九個 source 的 targeted mypy 成功，紀錄 `source_mypy_final.txt`。十個變更 Python 檔的 compile、quant guard、diff check 另存該目錄。本地輸出皆忽略、不提交。

首輪 capability error-code 相容性失敗已修復。另兩個既有 stock report 測試因 sandbox 下 Windows Temp 祖先唯讀 no-follow handle 權限失敗，允許該唯讀檢查重跑後 2 passed；最終同範圍全部通過。未改 guard、ACL 或舊測試斷言。

測試覆蓋 source → producer → repository → screener → cohort/capabilities → 新 Python 程序回讀，保存前後 identity 相同；SQLite fixture 主檔 hash/mtime 不變；改變 fixture band 後來源 fingerprint mismatch 被拒絕。未搬移真資料或改寫舊 artifacts。

四個 v2 baseline pins 保持：

| 項目 | SHA256 |
|---|---|
| MA registry | `029bcb5ada592619d9748d327eef509db0642a1c6904b652b31f186027025dc5` |
| input fingerprint | `485832355546a911852cd74f70b07f90adb668f36663f9123e22ad5239017c67` |
| snapshot identity | `82b91a12471e7fa3ec39cf633311b6b79dcf30f11fe55da6def91aa0656003bf` |
| canonical payload | `819e6f0c95f0f8418787b7210f55f6d9da3efe7bd4d1c05f05b6e1fd911bead6` |

本地提交 full hash、各檔 Git blob 及 raw/JUnit hash 交付於忽略輸出 `handoff_receipt.json`。需要回滾時由 owner revert 本 lane 提交，無須重建資料。

## 中央剩餘接線

中央須為日常 capture 選用 opt-in v3；`stock_research_report_service.read_report` 兩處 consumer fingerprint composition 仍為 v2，需依保存 manifest 版本讀取 BB 並傳入相同 contract version。本 lane 未取得這兩處 composition ownership。

中央另須同步 family catalog、Manual、Snapshot、架構／索引及 test inventory。有限 upper 比較可用不等於 compression 完成。compression、H20 gross、每日模型預測／自然結果優化及正式資格由對應 lane／中央接線。樣本成熟度不作永久工程阻塞，synthetic 結果不作真實上線或效果證據。未註冊正式 Task、交易、push 或清理。
