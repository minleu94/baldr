# F02 四均線來源缺口核驗

2026-10-08，中央對dev `f2fba4c7` 的實際方法契約執行Python讀回，沒有讀取正式資料、模型或排程。

實際保存特徵只有 `MA5`、`MA20`、`slowk`、`slowd`、`MACD`、`MACD_signal`、`volume_shares`。五個規則仍是MA5／20交叉、KD交叉、MACD交叉及20／5日量比。`MA10`、`MA60`不存在，因此四均線多頭排列尚未提供，不能把兩均線交叉顯示為F02已完成。

核驗入口：`app_module/daily_market_technical_method_contract_v4.py` 的 `daily_market_technical_method_contract_v4_payload()`；來源界限 `DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS=120`。快照保存120筆以內OHLCV原料、逐列fingerprint、原時計及最多最近兩日的既有七個特徵。raw_values只含日期、股票、OHLC與成交量，沒有未核MA10／MA60可直接取用。`observed_prefix_contiguous`只描述來源觀測前綴；官方交易日完整性仍未知，不能據此宣稱60個已核官方交易日。

下一項實作須新增獨立版本的均線證據與query擴充，保持舊v4五規則、方法hash與收藏bytes不變。四均線排列必須同一股票、同一原保存窗口、同一截止，精確涵蓋MA5>MA10>MA20>MA60；不得混用目前行情或另一份technical_indicators表。計算沿明示SMA方法與版本、原始Close來源、完整warmup及因果窗口保存lineage；金融核心使用Decimal或整數／精確有理比較，第三方浮點僅限既有明示指標計算邊界。MA20上彎是另一條未定坡度方法，不因四均線排列而自動成立。

來源日期超過決策截止、原當日row／session pin不能唯一核對、短於60筆、無效價格、觀測不連續或來源遭修改時保持具名未知／拒絕，不回退較舊價格湊齊。每項query在完整已處理母體先分類match／no_match／unknown，再全域排序與分頁；未知與excluded／pending／missing分開列，不能由當頁推全市場。

驗收須包含真保存來源60筆及不足59筆、嚴格排列與相等／逆序、超過截止／無效／重複row、精確小數邊界、原料或lineage tamper、取消不發半份結果，以及257跨段全域篩選與新程序收藏重開。新方法出現在正常UI及同版EXE前，不授F02產品接受。本文件是已完成缺口核驗與後續實作邊界，沒有新增四均線功能。
