# baldr Windows 可攜版

可攜版包含 `baldr.exe` 與 `_internal`。**必須保存整個 baldr 資料夾**，不可只複製 exe。Windows x64 不需 IDE、全域 Python 或虛擬環境；雙擊 `baldr.exe` 開啟既有九工作區。建置版號為 `2026.10.06`，不是產品成熟度版號。

## 首次啟動與既有使用者

本機交付位置：`C:/Projects/PythonProjects/technical_analysis/dist/baldr/baldr.exe`。exe 大小 52,271,117 bytes；SHA256：`2f150edd5be13e3f506b832a53c0ea189a4ff44b75ff729dcce8e9c09ca49618`。建置依賴 PyInstaller 6.16.0／Python 3.11.9／Qt 6.10；支援 Windows 10 1809 以上 x64／Windows 11，依 [Qt 平台文件](https://doc.qt.io/qt-6.10/supported-platforms.html)。依賴與整包校驗見交付目錄 `BUILD_INFO.json`／`SHA256SUMS.txt`。

已驗隔離 offscreen 啟動、空資料設定提示、九工作區、Unicode／空格工作目錄、synthetic 模型安全載入與新程序重開、multiprocessing、保存重開、Worker 取消與重新執行，以及 CLI／scheduler 未配置 preflight。Native 真人操作、真實私人模型、正式 Task 自然 run、其他 Windows 機器尚未由本包驗證；不以 fixture 改寫原資格。

四用途以合成來源／空報價 fixture 驗證畫面與安全未知狀態；推薦 legacy SQLite runs 的 canonical 保存結果重開，在本環境受既有 no-follow handles root／ancestor guard 阻擋，不能列為通過。此限制沿原 audit 保留，沒有放寬 guard；Watchlist 保存重開不等同推薦保存重開。

首次未明示設定時使用 `%LOCALAPPDATA%\baldr\market` 與 `output` 空根，顯示設定提示。空來源保持 missing／unknown，不帶行情、私人持倉或模型。設定檔位於 `%LOCALAPPDATA%\baldr\config.json`；可用 `BALDR_CONFIG` 指定另一個絕對路徑。設定檔不是 `.env`，程式不自動讀 `.env`。同名環境變數優先於 JSON。

```json
{
  "DATA_ROOT": "D:/My Baldr/market",
  "OUTPUT_ROOT": "D:/My Baldr/results"
}
```

1. 關閉程式並等待背景工作安全收尾。
2. 在上述檔案填自己的絕對路徑；roots 必須在程式包外且可寫。設定後重開。
3. 既有使用者沿原啟動器／設定填相同 DATA_ROOT、OUTPUT_ROOT。不要因為換 exe 建立或搬移資料。
4. 私人選擇沿原契約填 `PERSONAL_DATA_ROOT`／`PERSONAL_WATCHLIST_SOURCE`、`PERSONAL_JOURNAL_ROOT`／`PERSONAL_JOURNAL_MODE`、`PERSONAL_STORE_ROOT`／`PERSONAL_STORE_MODE`；單設拒絕，不改市場 writer。
5. 已接受個人模型填原 `PERSONAL_MODEL_POLICY_PATH`，指向原可信 policy；指定路徑不自動訓練／啟用。原 manifest、same-bytes、identity、source、cutoff 核驗仍適用。
6. 在數據更新確認行情日期與缺件；看盤勢／持倉健康／選股研究／個股研究仍按 [完整手冊](APPLICATION_MANUAL.md) 操作。

Runtime 狀態與預設研究 registry 放在 `OUTPUT_ROOT/application_state`，保留外部可寫狀態。這是新可攜使用者的空狀態；原保存研究必須從原已選定來源重開，不能把未知補成綠燈。原模型 artifact、真帳與 FA_Data 均不在程式包。

## 子程序與排程

可攜入口支援 `baldr.exe scripts/scheduled/<原腳本>.py <原參數>` 與 `baldr.exe -m <模組> <原參數>`。相對腳本以程式包資源根解析，不依目前工作目錄；參數、dry-run／preflight／execute gate 仍以原腳本為準。例：`baldr.exe scripts/scheduled/run_daily_data_update_quick.py --help` 只列說明。

原正式 Task 不會自動改為 exe，也不會註冊或手動觸發。日常排程若要換入口，需另外確認完整 action、環境與身份，不以本輪隔離驗證代替原 Task 自然 run。取消與關閉沿原合作式收尾；重開保留外部設定與保存結果。

## 排錯、安全與建置

- 未簽章；簽章與 SmartScreen 信譽未知。不得繞過 Windows 警告或降低防護。本包不是已簽章安裝程式。
- 首次無字或缺資料：確認整個資料夾存在、設定為 UTF-8 JSON 且 root 為絕對路徑；中文字型沿 Windows 原字型，未複製 Windows 字型。
- 沒有 console 的日誌在 `%LOCALAPPDATA%/baldr/stdout.log`／`stderr.log`，主 App crash diagnostics 沿原資料根機制。資料根／來源拒絕時核對提示，不改 hash／no-follow／ACL。
- 合法 `passed_with_warnings` 表示更新完成但有警告；最後成功時間、來源資料日期、新鮮度與警告分開判讀。failed／unknown／invalid／stale 不假成功。
- 任意深層 OUTPUT_ROOT 的既有 Windows 長路徑限制仍適用；本輪測 Unicode／空格，未保證所有大於 260 字元的保存路徑。
- 維護者先裝原 runtime 與 `packaging/requirements-build.txt`，再執行 `.\.venv\Scripts\python.exe packaging/build_windows.py`。建置器限定 venv／系統 PATH 與空 userbase，避免外部 Poppler ICU 遮蔽 Windows 系統 ICU；spec 統一已安裝 Qt wheel 附帶的 C++ runtime。只收正式程式、必要資源和依賴，不收 QA、experiments、FA_Data、私人模型或 `.env`。

替換版本前保留舊可攜資料夾；回滾時改用舊 exe＋整個舊資料夾。資料與設定不刪除，不清 cache、不重建 DB；程式回滾不代表資料 schema 遷移回滾。
