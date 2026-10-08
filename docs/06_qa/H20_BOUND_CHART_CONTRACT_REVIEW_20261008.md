# H20 同來源圖表接線審查（2026-10-08）

狀態：已完成程式只讀核對，受控實作中；本文件不表示圖表已可用或速度已接受。沒有讀正式 SQLite、複製正式大檔或更改原 capture。

## 原保存資料實際綁定範圍

`run_personal_current_observed_h20_daily._source_port` 以 `asdict(CurrentObservedFeatureRow)` 保存 `feature_rows_by_symbol`。其中 `source_row_sha256_by_table` 包含 daily_prices、technical_indicators、market_indices、industry_indices；`row_sha256` 納入這些彙總雜湊，capture 再核重建 mapping 與 payload hash。因此不能說原 capture 完全沒有價格邏輯列雜湊。

daily_prices 的雜湊涵蓋 provider 查詢的日期、代號、成交股數、成交金額與 OHLC，範圍依原 symbols、history_start_date、feature_as_of_date；這是正規化完整邏輯列集合的彙總雜湊。technical_indicators 只涵蓋日期、代號、RSI、MACD、ADX，不涵蓋 MA20／MA60。

價格圖表應從同次已核 verifier 的 `raw.prices` 投影最多 120 點，保留完整集合雜湊至圖點的來源關係，再封住投影窗口。不能把另查的 120 點子集雜湊直接當作完整集合雜湊。

## 接線與不變量

- Read ports 加可選 observer，在原 verifier 返回 mapping 不變的前提收集 typed 價格投影；不改 H20 推論、保存內容或原雜湊契約。
- 初讀及終態沿同一 SQLite operation copy 核對 capture、source binding、symbol、cutoff 與窗口，semantic session、operation finish、取消檢查全部完成後才簽發不可序列化的 verified view。
- 列表選股只投影程序內 sealed view，不增加來源 SQL 或第二次大檔複製；bookmark 新程序仍須 fresh exact reopen，不能序列化舊 seal 當作已核。
- 本次僅交付已綁定 OHLCV。MA20／MA60 缺原邏輯列及方法 lineage，保持未知，不補算、不稱合格技術規則。
- 非空來源 WAL 沿 pinned reader 的拒絕契約；不能改用 immutable 忽略 sidecar，也不能把 cycle 上游 WAL 觀測當作 snapshot 原時點 sidecar pin。
- 圖表失敗、容量超限或缺件只拒絕該圖表增補，不截短完整 H20 cohort、刪除 unknown 或回填最新價格。原估計、日期與來源仍保留。
- H20 manifest 上限 50、單 source binding 上限 16 是現有 H20 契約，不是實際全市場證明；新增圖表上限不得改变其分母。
- 摘要分列「一般個股報告來源完整度」與「H20 綁定圖表完整度」，不改原 report JSON、不把圖點灌入 generic report DTO、不授予 PIT／收益資格。
- 金融數值使用 Decimal／整數；浮點轉換只容許 Qt 繪圖展示邊界。

## 必需驗證

正常 Main 的 H20 列表 → 選股 → 有界同源圖表 → 返回與選取保留；收藏新程序 exact reopen；初讀／終態漂移、錯 symbol／capture／cutoff、seal tamper、取消／關閉及容量超限均不得發布假圖。缺 MA 與 generic report 缺件的摘要要分開。確認選股不再 SQL／複製，並分開量測首次核驗與單股下鑽；不能以合成單次量測宣稱正式 2382 的 20 秒問題已解決。

## 更新記錄

- 2026-10-08：根據 provider、feature builder、capture、hook、verified view 與摘要程式，確認價格列雜湊已保存，限定同源 OHLCV 接線及相應拒絕／驗收契約。
