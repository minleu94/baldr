# F06 波動收斂：來源證據與方法缺口

狀態：Root 唯讀盤點與下一切片規劃，未實作、未產製、未發布收斂訊號。

## 目前程式的實際差異

原補完計畫 F06 要求觀測窗口、比較基準、連續性、閾值來源及突破確認；低 ATR 單點不代表收斂，短史保持未知。現行 v4 方法契約只有 MA5、MA20、slowk、slowd、MACD、MACD_signal、volume_shares 七項 feature，沒有 ATR 或 Bollinger bandwidth 的保存方法。

Graphify 圖譜（built_at_commit `665d8a9b2e249897540d9760c760b17346ecc2ab`）找到 bandwidth kernel、regime detector、scorer 及相關測試連結，Root 再核目前原碼：

- `analysis_module/technical_analysis/technical_indicators.py` 的因果指標路徑使用 TA-Lib ATR14；Bollinger 是 SMA30、上下兩倍標準差。
- `decision_module/market_regime_kernels.py` 的 bandwidth 使用 pandas window20、min_periods=1、預設 sample std，再將缺值填 0；輸出是百分比。它與上項窗口、暖機及缺值政策不同，且沿既有浮點分析路徑。
- `tests/test_market_regime_kernels.py` 的 prefix-invariant 測試證明既有 kernel 沒有使用後綴列，但不證完整暖機、保存來源資格或 F06 收斂成立。

因此不能直接把某處已有 bandwidth／ATR 或 0 值當作 F06 合格證據，也不能把這兩個方法混成同一條保存規則。圖譜只供定位；上述結論以目前原碼為準。

## 最小可實作切片

先建立獨立版本的 Decimal 波動原料 evidence，不修改舊 kernel／v4，也不判斷收斂或突破。輸入沿同份已保存、日期／股票／token／fingerprint 經驗證的 OHLC 原料；leaf 不做 I/O、不讀 live DB，不發 reader qualification。

方法契約必先固定以下欄位，參數選擇尚待 P07 定版：

| 證據 | 必須固定的定義 |
|---|---|
| Bandwidth | SMA 期數、population/sample variance、上下倍數、`(upper-lower)/middle*100` 的單位；暖機需完整窗口，middle=0 或缺值回 unknown，不填 0。 |
| ATR | True Range 的前收來源、期數、SMA 或 Wilder 遞迴、初始 seed 與來源前綴錨點；有限保存窗口不能冒稱與任意長歷史 seed 的結果等價。 |
| 正規化 ATR | ATR／當日收盤的百分比，明列分母與單位；分母無效回 unknown，不將價格單位 ATR 與百分比混排。 |
| 每日資料 | 觀測日、原 row fingerprint、source／snapshot pins、窗口起訖、實際暖機列數、方法 identity、數值 context 與具名 unknown 原因。 |
| 資格 | source_available_at 未知、historical_pit_eligible=false；raw 自洽 hash 只是內容識別，完整母體資格由 exact reader 發行。 |

Decimal precision、rounding、Emin／Emax／clamp／traps 全部明示且納入方法 identity，不能繼承 caller 狀態。既有 float arrays 不反向進入新規則核心。

## P07 規則卡與驗收

收斂規則另定當期窗口、互不混淆的基準窗口、需連續成立的觀測數、比較方式／閾值／端點及短史政策。突破另列確認價、比較區間與成交量條件；在決策當下尚未觀測的後續突破保持待確認，不能回填當時訊號。未有這份規則卡以前，evidence 不輸出收斂 match、不增加推薦分數。

切片驗收包含：獨立 Decimal oracle、完整暖機邊界、零分母／缺列／無效 OHLC、兩種 variance 的可辨識向量、ATR seed／前收錨點、外部 Decimal context 污染、合法 cutoff 後來源列不改 cutoff 前 evidence、原始資料 tamper 拒絕、來源未知不升 PIT，以及舊 KD／MA／v4 相容。

完整 F06 後續仍需同次 exact full-N 投影、硬資格與三態計數、global sort 後分頁、保存 recipe 新程序重開、UI 原因與日期可讀、取消／故障原子性及同版 EXE。原料 leaf 或本盤點文件都不算 F06 完成。
