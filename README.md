# baldr

baldr 是台股資料整理、技術研究、選股比較與投資組合研究工具，主要介面是 PySide6。研究輸出與資料更新、手動保存會寫入你設定的資料／報告目錄；不內附私人行情庫、帳戶、模型或憑證，不會因安裝而建立 Windows 排程或自動交易。

`main` 是本機使用版本，`dev` 保留完整開發歷史、規劃與驗收素材。模型推論接線及研究功能可使用，正式資格、自然結果成熟與投資效果依具名來源判讀；unknown／pending 不當零，也不代表可交易。

## 安裝與首次啟動

使用 Windows x64、Python 3.11。在專案根目錄的同一個 PowerShell 執行：

```powershell
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt -c requirements-py311-windows.constraints.txt
$env:DATA_ROOT = Join-Path $env:LOCALAPPDATA "baldr\data"
$env:OUTPUT_ROOT = Join-Path $env:LOCALAPPDATA "baldr\reports"
.\.venv\Scripts\python.exe ui_qt\main.py
```

兩個 roots 必須分別設定：只改 DATA_ROOT 不會同步改 OUTPUT_ROOT。PYTHONUTF8 避免舊版 Windows pip 將 requirements 註解以其他編碼解讀。這些環境設定只作用於目前 shell；`.env.example` 是欄位示意，目前程式不自動載入 `.env`。首次不設定 PERSONAL_*／模型 opt-in。

首次開啟「數據更新」→「檢查數據狀態」，確認缺庫／缺表與來源日期。依官方來源、所需日期與使用權取得資料後再更新研究；資料不足時保留缺件，不補假值。程式會建立目錄與 logging。不要把別人的 SQLite、持倉或模型直接放進自己的 roots。

- [安裝與排錯](docs/07_guides/INSTALL_GUIDE.md)
- [快速開始](docs/07_guides/QUICK_START.md)
- [完整操作手冊](docs/07_guides/APPLICATION_MANUAL.md)
- [目前狀態](docs/00_core/PROJECT_SNAPSHOT.md)
- [示例資料說明](examples/README.md)

## 開發與限制

需要測試及型態檢查時，另裝 `requirements-dev.txt`；`requirements.txt` 保留相容的完整開發安裝。constraints 是 Windows Python3.11 的直接依賴快照，不是跨平台完整鎖檔；安裝或來源失敗請保留錯誤型別，不抄用他人的本機 wheel 或憑證。

此 repo 尚未提供新的開源授權；本機 main 整理不代表已公開發布或授予再散布權。歷史資料及來源也需各自授權。不要提交私人根目錄、token、模型權重或測試暫存。正式自然日常結果與品質成熟仍待實際排程及交易日驗收。
