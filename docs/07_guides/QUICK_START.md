# 快速開始

先依 [安裝指南](INSTALL_GUIDE.md) 在Windows x64／Python3.11建全新venv，設定自己的兩個root。使用者資料不內附，請勿使用開發者預設機器路徑。

```powershell
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt -c requirements-py311-windows.constraints.txt
$env:DATA_ROOT = Join-Path $env:LOCALAPPDATA "baldr\data"
$env:OUTPUT_ROOT = Join-Path $env:LOCALAPPDATA "baldr\reports"
.\.venv\Scripts\python.exe ui_qt\main.py
```

1. 開啟數據更新→檢查數據狀態，記錄來源日期、缺庫及缺表。
2. 依可用官方來源及日期使用快速更新（SQLite），需要CSV備份時選安全更新；來源無資料時不把missing當零。
3. 確認股價／技術指標日期及窗口後，再執行選股、回測或圖表研究。
4. 個人store與模型屬opt-in；首次不初始化他人資料，不自動啟Task、fit或交易。保存名單／自然pending與效果成熟是不同證據。

程式及更新會寫入設定roots；`.env`目前不自動讀入。UI空資料時先核設定与来源，不以latest／別人模型／fixture填補。示例僅展示資料形狀，見 [examples](../../examples/README.md)；完整步驟與限制見 [Manual](APPLICATION_MANUAL.md)。
