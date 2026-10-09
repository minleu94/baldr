# F06 Decimal 波動原料方法提案

狀態：Root 已接受首批方法定義；獨立 evidence leaf 已實作並以合成來源測試。尚未接入 v4／F17，未產生收斂或突破訊號；本文件不代表 F06 完成。

本提案只固定可重現的原料算法，讓後續 P07 規則卡能引用明確版本。單日 ATR 或 bandwidth 偏低本身不等於波動收斂，也不等於突破已確認；本切片不改推薦分數、不產生 match/no-match 策略判定。

## 現行方法與相容界線

目前可核對的程式有兩種不同基準：

- `analysis_module/technical_analysis/technical_indicators.py::calculate_causal_indicators` 呼叫 TA-Lib `ATR(high, low, close, timeperiod=14)`，並呼叫 `BBANDS(close, timeperiod=30, nbdevup=2, nbdevdn=2, matype=SMA)`。這是既有浮點分析路徑；ATR 的 seed／遞迴語義由 TA-Lib 與傳入 prefix 決定，結果不能直接當作有界 Decimal 保存證據。
- `decision_module/market_regime_kernels.py::calculate_bollinger_bandwidth` 使用 window 20、`min_periods=1`、pandas 預設 sample standard deviation，並把缺值填成 0。它既不是 BB30，也不能區分「暖機不足」與真正的 0。

推薦新 evidence 使用自己的版本與 identity。它不改寫、不取代舊兩條路，也不宣稱與其輸出逐位相同。若未來需求要求 Wilder ATR 的相容值，必須另立方法版本並固定 prefix anchor，不能把本提案的 SMA ATR 改名為舊 ATR14。

## 建議方法版本

| 證據 | 建議 method id | 定義與暖機 | 相容邊界 |
|---|---|---|---|
| Bollinger bandwidth | `bollinger-bandwidth-sma30-population-2x.v1` | 取決策日及其之前最近 30 筆連續有效收盤觀測；`middle = sum(close)/30`；population variance 為 `sum((close-middle)^2)/30`；`sigma = sqrt(variance)`；`upper/lower = middle ± 2*sigma`；`bandwidth_pct = (upper-lower)/middle*100`。必須滿 30 筆。 | 窗口與舊 BB30 對齊；variance／Decimal context／序列化 identity 由新版本固定。不可把 pandas window20、sample std、`min_periods=1` 或 fillna(0) 的結果當作同一方法。 |
| ATR 原料 | `atr14-sma-true-range.v1` | 取決策日及其之前最近 14 個 True Range；每筆 `TR_t = max(H_t-L_t, abs(H_t-C_{t-1}), abs(L_t-C_{t-1}))`。第一筆 TR 需要一筆更早的有效前收，因此至少需 15 筆連續有效 OHLC 觀測。`atr14 = sum(TR)/14`，`atr14_pct = atr14/current_close*100`。沒有遞迴 seed。 | 這是有界 rolling SMA，不是 TA-Lib Wilder ATR14，也不以任意長歷史 seed 假裝可從 15 筆資料重建 Wilder 值。舊 ATR14 繼續沿舊路徑。 |

若產品明確要求 Wilder 對照，可新增不同 identity，例如 `atr14-wilder-seeded-window.v1`：先在明示來源 prefix 的前 14 個 TR 取 SMA 作 seed，之後每筆 `ATR_t=(13*ATR_{t-1}+TR_t)/14`。此值依 prefix anchor 而變，必須在 evidence 內保存 anchor 日期、seed TR 數與完整計算 prefix fingerprint；不得和 `atr14-sma-true-range.v1` 共用 query 欄位、排序值或 identity。此版本不在本推薦首批實作範圍。

### Decimal 數值邊界

已接受的方法 context 與 KDJ leaf 一致：精度 34、`ROUND_HALF_EVEN`、`Emin=-6143`、`Emax=6144`、`clamp=0`。`InvalidOperation`、`DivisionByZero`、`Overflow`、`FloatOperation` traps 開啟；其餘 Decimal signals 明確關閉。計算不繼承呼叫端 context。

輸入和輸出使用不同的資源界限，且均納入 method identity。計算窗口內每個 OHLC 原始 token 最多 96 UTF-8 bytes、最多 34 coefficient digits、exponent 為 `[-34, 12]`、adjusted exponent 為 `[-12, 12]`；超界在公式前以具名錯誤拒絕。輸出 Decimal token 最多 256 bytes、最多 34 coefficient digits、exponent 與 adjusted exponent 都在 `[-100, 100]`。這些限制避免極端指數與過長精度進入數值運算；它們不改寫來源 snapshot 自身的原料驗證契約。

帶寬分母必須 `middle > 0`；ATR 正規化分母必須 `current_close > 0`。輸入不完整、暖機不足或觀測序列有缺件時輸出具名 `unknown`，不刪列、不補值、不回填 0。違反原料 OHLC 約束、日期順序、重複日或 fingerprint 的來源資料應拒絕，不降級成 unknown 來掩蓋來源錯誤。有效日期只代表來源實際觀測列；不把相鄰列稱為完整交易所日曆。

## 可手算測試向量

1. **BB30 population 標準差：** 30 筆收盤中 15 筆為 9、15 筆為 11。`middle=10`、population variance `=1`、`sigma=1`、上下界為 12 與 8，因此 bandwidth 為 `40%`。若誤用 sample variance，結果會是 `40*sqrt(30/29)%`，測試可明確分辨兩者。
2. **BB30 平坦與暖機：** 30 筆皆為 10，`bandwidth_pct=0%`；只有 29 筆時是 `unknown(warmup_insufficient)`，不得回 0%。
3. **ATR14 SMA 與 Wilder 差異：** 收盤固定為 100。第 2 至第 15 筆觀測的 TR 依序為 1 至 14，第 16 筆 TR 為 15（以高低區間構造，所有 OHLC 仍有效）。第 16 筆 trailing-SMA ATR 使用 TR 2 至 15，均值為 `8.5`，正規化值為 `8.5%`。若另算 Wilder 對照，第 15 筆 seed 是 `(1+…+14)/14=7.5`，第 16 筆遞迴值為 `(13*7.5+15)/14 = 112.5/14`；兩值不可混稱。
4. **ATR 前收與暖機：** 只有 14 筆 OHLC 時不足 14 個具前收的 TR，應為 `unknown(warmup_insufficient)`；15 筆且每筆有效才得到第一個 ATR14-SMA。移除任一內部觀測不得把左右列當成相鄰列補算。
5. **污染與來源時點：** 以相同 Decimal 原料在外部 context 修改 precision／rounding／traps，輸出仍完全相同；另在 cutoff 後追加有效 OHLC，來源 content identity 可以改變，但 cutoff 前 ATR、bandwidth、窗口日期與 row fingerprints 不得改變。`source_available_at` 仍為 unknown，`historical_pit_eligible=false`。

## Look-ahead 與資格

計算只使用 `feature_date <= decision_date` 且來源明示 cutoff 可見的列；目前快照是 current-only，來源未提供可驗證的歷史 available-at，因此即使公式沒有使用未來列，也不能宣稱 historical PIT。不得往 cutoff 後找最近可用值、以未來突破資料確認當日收斂，或用完整資料集的事後標準化參數。future-prefix 測試需使用同一合成 capture 在截止日後新增列，重建合法 snapshot，逐欄比較 cutoff 前結果；原始來源 fingerprint 可不同，截點前 fact identity 應穩定。

新 leaf 只能從嚴格核驗的 immutable snapshot 接收 typed OHLC 原料；leaf 自身不做 I/O、不連線 SQLite、不讀 live/latest。其 hash 只識別輸入內容，不發來源資格。之後若接入 F17 全母體 query，必須在同一次 exact reader 的既有 snapshot→row callback 產生 compact evidence，並由 reader-issued seal 核准；不得另外掃 source 或只按可見頁計算。

目前 leaf 的具體輸出僅包含 BB30 population bandwidth 與 ATR14 rolling-SMA true-range 及 ATR/current-close 百分比。BB 與 ATR 使用各自窗口、暖機及 unknown 理由；invalid OHLC 在該方法實際窗口內不會被略過。日期只要求原始觀測列嚴格遞增，不要求日曆日相鄰。證據固定 `source_available_at=unknown`、`historical_pit_eligible=false`、`reader_qualified=false`；輸出不判定收斂或突破。

本方法提案不設定「低 ATR／低 bandwidth」門檻、baseline、連續成立天數、breakout confirmation 或推薦權重。這些需要 P07 規則卡明定基準窗口、比較端點、持續性、觸發價、成交量條件與未知政策後才能實作。Leaf 測試與方法定義不代表 F06 已完成。
