# 快速參考

## 常用入口

| 需求 | 文件 |
|---|---|
| 完整 UI 操作 | [APPLICATION_MANUAL.md](APPLICATION_MANUAL.md) |
| 三步啟動 | [QUICK_START.md](QUICK_START.md) |
| 安裝與環境 | [INSTALL_GUIDE.md](INSTALL_GUIDE.md) |
| 更新每日資料 | [HOW_TO_UPDATE_DAILY_DATA.md](../03_data/HOW_TO_UPDATE_DAILY_DATA.md) |
| 更新故障排除 | [APPLICATION_MANUAL.md 第 12 節](APPLICATION_MANUAL.md#12-常見問題) |
| 回測功能與限制 | [BACKTEST_LAB_FEATURES.md](../02_features/BACKTEST_LAB_FEATURES.md) |
| 回測操作與排錯 | [APPLICATION_MANUAL.md](APPLICATION_MANUAL.md) |
| 目前狀態 | [PROJECT_SNAPSHOT.md](../00_core/PROJECT_SNAPSHOT.md) |
| 未來路線 | [ROADMAP_6M_ENGINEERING.md](../00_core/ROADMAP_6M_ENGINEERING.md) |

## 啟動

```powershell
.\.venv\Scripts\python.exe ui_qt\main.py
```

## 日常更新

- 速度優先：數據更新 → 快速更新 (跳過大型合併)（仍更新必要日檔 CSV 並同步 SQLite）
- 完整備份：數據更新 → 安全更新（完整 CSV + SQLite）
- 只查狀態：數據更新 → 檢查數據狀態

## 研究流程

```text
Update
  -> Market Watch / Smart Money
  -> Recommendation
  -> 候選池 / 選股清單
  -> Research Lab
  -> 保存結果；只有符合 Lifecycle Gate 並獲准時才申請 Promote
  -> Portfolio / Journal
```

## 常用維護命令

```powershell
# 批量更新股價
.\.venv\Scripts\python.exe scripts\batch_update_daily_data.py --start-date 2026-06-01

# 更新單日並合併
.\.venv\Scripts\python.exe scripts\update_daily_stock_data.py --date 2026-06-12 --merge

# 合併既有每日檔
.\.venv\Scripts\python.exe scripts\merge_daily_data.py
```

## 快速排錯

- 推薦沒有最新資料：檢查 `daily_prices` 與 `technical_indicators` 日期。
- Smart Money 無資料：檢查券商分點下載、合併與 `broker_flows`。
- 回測 0 交易：檢查整股資金、暖機、門檻與成交量限制。
- Promote 停用：先保存結果，再檢查 Registry／驗證狀態及 Lifecycle Gate；狀態不是 FAIL 不代表已符合 Promote 資格。
- Watchlist 可直接送 Research Lab 批次回測；若要保存成可重用的 Universe，再另存為選股清單。

