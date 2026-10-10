# 受限 System Python 備援（非標準安裝）

標準安裝與新環境一律依 [INSTALL_GUIDE](../07_guides/INSTALL_GUIDE.md)：Windows x64／Python 3.11、全新 `.venv`、`requirements-runtime.txt` 與 constraints。這份備忘僅供已配置好相容套件的本機 system Python 臨時執行；不作為新手安裝或環境修復流程。

## 先處理虛擬環境啟用問題

PowerShell 執行策略阻止 activate script 時，不必改用全域 Python。直接執行 `.venv` 內的解譯器即可：

以下日期是命令範本，請替換成實際範圍，並明確指定 `--end-date`；省略結束日期會延伸更新到今天。

```powershell
.\.venv\Scripts\python.exe scripts\batch_update_daily_data.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

這是標準 `.venv` 的直接呼叫方式，不需先啟用環境。更新腳本可能寫入資料；執行前須確認 `DATA_ROOT`、`OUTPUT_ROOT`、`PROFILE` 與目標日期符合預期，並依 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 的資料更新流程操作。

## system Python 的使用條件

只有在電腦已由管理者準備好 Python 3.11 x64、所需 runtime 套件與相容版本，且確認命令解析到該解譯器時，才使用此備援。不同腳本的依賴與副作用各異；下面檢查只作基本資訊，不能替代對應腳本的完整相依檢查。

```powershell
Get-Command python | Select-Object -ExpandProperty Source
python --version
python -c "import platform, pandas, numpy, requests; print(platform.architecture())"
python -m pip check
```

確認後才可用該 system Python 呼叫經核對的腳本，例如：

```powershell
python scripts\batch_update_daily_data.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

UI 只有在完整 runtime 相依均已按相容版本準備好時才可能啟動：

```powershell
python ui_qt\main.py
```

## 缺少模組或版本不符

不要對全域 Python 執行無版本約束的 `pip install`。請改用 [INSTALL_GUIDE](../07_guides/INSTALL_GUIDE.md) 建立乾淨 `.venv`，再依 `requirements-runtime.txt` 與 `requirements-py311-windows.constraints.txt` 安裝。常用腳本的預設環境與命令假設見 [scripts README](../07_guides/scripts_readme.md)。
