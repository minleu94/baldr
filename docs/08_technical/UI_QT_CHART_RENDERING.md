# Backtest Qt 圖表渲染

> 更新日期：2026-10-10。本文描述目前回測結果圖表的元件建立、資料呈現與替代閱讀方式；本文未引用效能基準測試。

## 範圍

回測結果區提供四種主要圖表：

- 淨值曲線（Equity Curve）
- 回撤曲線（Drawdown Curve）
- 交易報酬分布（Trade Return Distribution）
- 持有期間分布（Holding Period Distribution）

目前有 QtWebEngine + HTML5 Canvas 實作，以及 Matplotlib 元件作為替代實作。類別名稱中的 `Fast` 是程式識別字；本文未引用效能基準測試，不能據此宣稱渲染速度較快。

## 元件與建立時機

圖表由資料 payload 與 UI 元件兩層組成：

1. `ui_qt/widgets/chart_payloads.py` 建立 JSON 可序列化資料，處理基準序列正規化、回撤區間 metadata、交易標記、報酬區間與持有天數分組。
2. `ui_qt/widgets/fast_chart_widget.py` 提供 QtWebEngine host，使用本機 HTML5 Canvas 繪圖；不載入外部 JavaScript、CDN 或 TradingView 資產。
3. `ui_qt/views/backtest/result_panel.py` 的 `BacktestResultPanel.ensure_chart_widgets()` 在圖表頁需要顯示時呼叫 widget factory、建立四個圖表並回放尚未繪製的結果。`ui_qt/views/backtest_view.py` 建立 result panel，並在使用者切換至圖表頁時觸發延後建立。

Factory functions：

- `create_equity_curve_widget()`
- `create_drawdown_curve_widget()`
- `create_trade_return_histogram_widget()`
- `create_holding_days_histogram_widget()`

`prefer_fast=True` 且 QtWebEngine 可用時，factory 選擇 `FastEquityCurveWidget`、`FastDrawdownCurveWidget`、`FastTradeReturnHistogramWidget`、`FastHoldingDaysHistogramWidget`。否則選擇 Matplotlib 的 `EquityCurveWidget`、`DrawdownCurveWidget`、`TradeReturnHistogramWidget`、`HoldingDaysHistogramWidget`。

## 圖表呈現規則

### 交易報酬

- 少於 10 筆交易時逐筆呈現，以零軸區分正負報酬；此時不把小樣本描述成分布。
- 至少 10 筆時使用以零為中心的對稱區間；虧損在左側並以紅色呈現，獲利在右側並以綠色呈現，並顯示各區間筆數。
- 95% VaR 標記至少需要 20 筆交易；樣本少於 20 筆時不顯示該標記。實際標記仍依 payload 提供的統計值而定。

### 持有期間

依持有天數分為 `1-5d`、`6-20d`、`21-60d`、`61d+` 四組，顯示各組交易筆數。

### 回撤與淨值

- 回撤圖以零基準線下方的面積表示回撤；payload 有提供 metadata 時，標示最大回撤點及峰值至谷底區間。
- 淨值圖顯示策略淨值、正規化後的 benchmark、買賣標記與 hover crosshair。

## 鍵盤與文字數值替代

QtWebEngine Canvas 設定為可聚焦的 `role="img"`，並提供 ARIA label、資料摘要關聯及快捷鍵資訊。只有淨值與回撤折線圖的 payload 含 `equity`／`series`，聚焦後才可用 `ArrowLeft`／`ArrowRight` 移動資料點，或用 `Home`／`End` 跳到起點／終點。交易報酬分布與持有期間分布是 histogram payload，沒有鍵盤逐點瀏覽；請使用「顯示數值」讀取區間與筆數。Matplotlib 替代元件的鍵盤行為依各自實作而定。

四種 `Fast*` widget 均有「顯示數值」控制項。展開後的文字內容直接由同一份 payload 產生，提供日期／數值或圖表區間／筆數；每次最多列出 200 列，超出部分會標示省略數量。factory 改用 Matplotlib 實作時，呈現方式依該 Matplotlib widget 本身而定。

## 為何目前未使用 TradingView Lightweight Charts

目前圖表用於回測結果與績效分析，Canvas 路徑不需要新增 JavaScript build tooling、網路資產或 TradingView 整合／授權設定。若未來需要 K 線主圖、多窗格技術指標、成交量疊加或繪圖工具，再評估是否導入。

## 驗證入口

以下是文件記錄的定向檢查命令；本次文件整理未執行測試：

```powershell
.\.venv\Scripts\python.exe -m pytest -o addopts= tests\test_ui_qt_chart_payloads.py tests\test_ui_qt_chart_widget_factory.py tests\test_portfolio_mvp.py -q
```

```powershell
.\.venv\Scripts\python.exe -m py_compile ui_qt\widgets\chart_payloads.py ui_qt\widgets\fast_chart_widget.py ui_qt\views\backtest_view.py ui_qt\widgets\__init__.py
```
