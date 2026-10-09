# F06 波動 compact collector 契約

日期：2026-10-09  
狀態：新增未核資格投影骨架；尚未接入 P01/F17 observer，也沒有 full-N qualification。

## 回滾範圍

本切片只新增下列三個檔案；回滾時移除它們，不還原或修改其他工作區檔案。

| 檔案 | 變更 | 回滾方式 | 風險 |
|---|---|---|---|
| `app_module/daily_market_technical_universe_volatility_alignment_query_v1.py` | 新增波動來源 request、compact entry、未核索引和 poison collector | 刪除此新增檔 | 無既有 API 依賴；刪除會移除此未接線骨架 |
| `tests/test_daily_market_technical_universe_volatility_alignment_query_v1.py` | 新增合成資料契約測試 | 刪除此新增檔 | 無既有測試語義變更 |
| `docs/06_qa/BALDR_F06_VOLATILITY_COLLECTOR_CONTRACT_20261009.md` | 記錄本切片的界線和後續 observer 接點 | 刪除此新增檔 | 無產品執行影響 |

## 方法與未來函數自查

投影只重用已版本化的 `daily_market_technical_volatility_evidence.v1`：BB30 population ±2σ 與 ATR14 rolling-SMA True Range。兩種 measure 的方法 identity SHA、固定 Decimal context、窗口日期和原料 row fingerprint 均保存在 entry 內。每個 measure 自己保留 `observed/unknown` 與具名原因；資料不足或合法 OHLC 缺件是 unknown，不補零、不回退到較舊窗口，也不讓 BB30 缺件遮蔽仍可觀測的 ATR14。最新無效原料不以先前有效列替代。

leaf 只使用傳入保存 snapshot 的原料；collector 對同一 typed snapshot 和 parent row 做身份欄位比對，再投影一次。窗口的最後觀測日期不得晚於決策日，日期只依來源列順序遞增，不把週末或其他日曆日差額推定成缺少交易日。`source_available_at` 固定為 null、可用性為 unknown、historical PIT eligibility 固定 false。collector 不讀資料庫、不搜尋最新版本、不宣稱收斂或突破。

## DTO 與資源界線

`DailyMarketTechnicalUniverseVolatilitySourceRequestV1` 包住明示的 MA source request，並同時固定 BB30、ATR14-SMA 的 method ID、version 與 identity SHA。其 `verification_status` 為 `metadata_unverified`，最終 canonical JSON（含 identity）上限 16 KiB。

`DailyMarketTechnicalUniverseVolatilityCompactEntryV1` 保存 segment、股票、決策時計、source/snapshot/window pins、同列 parent-row identity，以及完整的雙 measure leaf DTO。entry 最終 canonical JSON（含 compact identity）上限 16 KiB，以完整保留 30 筆 BB 窗口和 15 筆 ATR 窗口日期與 fingerprint。單 entry 過界即拒絕，絕不截短窗口。

collector 最多接受 100,000 筆股票，整份未核索引的最終 canonical JSON 上限 64 MiB。各上限分開生效，任何一項超界都拒絕整個暫存 operation。JSON 內禁止 float、重複或非字串 key、超過 32 層巢狀內容；source text、股票碼、segment index 與 window/Decimal bounds沿用 leaf 與 F03 compact 的固定限制。Budget 在包含 identity 的最終 payload 上核算。

collector 僅暴露明示 `unqualified_entries` 與 `unqualified_index()`。它沒有 `finalize_verified_publication`、qualified session 或 page API。呼叫端目前以 `begin_unqualified_segment` 提供 callback 形狀的 typed snapshots tuple；這個入口本身不驗 parent capture receipt、完整 StoreReader cohort 或 Bundle manifest，因此內容仍是未核資料。投影失敗、錯列、重複股票、順序錯誤、取消、非 bool callback 或超界會永久 poison collector；清除取消旗標也不可恢復，partial entry 不再可讀。

segment index 在 begin、consume 與 end 三個入口都必須是 `type(value) is int` 且落在固定範圍；Python 中 `bool` 雖是 `int` 子類別，但 `False == 0`、`True == 1` 不會被視為合法 segment。unqualified index 建構時逐筆核 compact entry 的決策日、完整 cutoff ISO 字串與 source-clock SHA 必須等於 source request；即使 entry 與 index 的自洽 identity 都重新計算，跨日期、cutoff 或 clock 的 entry 仍拒絕。這些欄位關係只保證 transport 自洽，不授予 reader qualification。

自訂 `max_index_bytes` 會同時限制 index body 與最後加入 `index_identity_sha256` 的 canonical JSON；identity 欄位帶來的額外 bytes 不能越過呼叫端設定的較小 budget。若 final payload 超限，`unqualified_index()` 失敗並 poison collector，已累積 entries 不再可讀。

## 與同次 exact observer 的後續接線

P01 builder 目前只有單一 verified projection slot；既有 F02 MA 與 F03 KDJ 接線各自保存固定 member 身份。一般 F17/MA/KDJ reader 必須維持原成本與行為，波動計算採明示 opt-in。未來 Root 的同次 exact observer 應由固定不可變 member tuple 同步接收原始 F17 parent row、MA、KDJ、volatility 四組資料；同一 snapshot 和同一 parent row 只建一次、依固定順序投影一次，不為不同 query 結果做事後交集。

共享 publication 必須核對 exact bundle/P01 pins、完整 ordered cohort、segment/parent receipt、同時計與方法 SHA，並在全部 member 完成、所有 counts 通過和最終取消檢查後原子發行。任何 member 失敗或取消都不得交付半份 index/session。MA/KDJ/volatility 結果各自保留 unknown；硬資格不因 OR 改變，之後的 composite query 才負責 truth/unknown、全域排序與分頁。本次新增 skeleton 沒有實作上述 fan-out、query、結果/page seal、收藏或 fresh-process reopen，不能稱為 F06 完成。

## 測試範圍

新增合成測試以 SQLite 隔離資料建立 typed snapshot，覆蓋未核 request、完整 30+15 窗口、兩股排序、單方法 unknown、最新列無效不回退、parent row 不相符、取消後不可恢復、布林 segment index 的 consume/end 拒絕、自洽重雜湊後跨 request 日期/cutoff/clock 的拒絕、自訂 byte budget 含最終 identity，以及無 qualification API。它不使用正式來源、不接 P01/F17 shared observer，也不代表 100k 母體、跨 segment qualification、UI 或效能驗收。

本次邊界修正版使用 `.venv` 執行同一測試檔，在全新隔離 `C:\t\f06-volatility-boundary-fix-20261009-b` 下結果為 **11 passed in 1.47s**。同版 `py_compile` 成功，scoped mypy（模組與測試檔）為 **no issues found in 2 source files**。第一個修正版 attempt `C:\t\f06-volatility-boundary-fix-20261009-a` 留有 **9 passed / 2 failed**：兩個失敗均為新增測試把 property 先求值後傳入測試 helper，未進入預期錯誤捕捉；只修正測試呼叫後以新隔離根重跑。完整原始輸出在 `output/qa/f06_volatility_boundary_fix_20261009_a/`。更早的 8 項初始 skeleton 證據仍是舊版本結果，不替代本次 11 項修正版測試。pytest 預設 AppData 暫存根目錄曾在 `DailyMarketTechnicalReadSession` 的 strict `Path.resolve` 遇 WinError 5；該失敗保留並以隔離 `C:\t` 根驗證，未 skip 或放寬來源檢查。
