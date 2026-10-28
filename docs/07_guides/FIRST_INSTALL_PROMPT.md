# baldr 首次安裝／完整移機指南與 Prompt

本文件提供 baldr 在新電腦首次安裝或從舊電腦完整移機時的**資料打包清冊、避坑指南、目錄放置結構與操作 Prompt**。

---

## 移機核心概念：代碼 vs 資料 vs 個人資產

在將 baldr 轉移到另一台電腦時，請先區分三大資產，不要整包硬拷：

1. **代碼庫（Repository）**：
   * 包含 Python 程式碼、UI 介面、測試腳本與操作手冊。
   * **不需要打包**：直接在新電腦透過 `git clone <repo_url>` 取得最新版本即可。
2. **資料根目錄（`DATA_ROOT`，舊機預設 `F:\Min\Python\Project\FA_Data`）**：
   * 存放台股歷年行情、技術指標快取、特徵與 SQLite 主資料庫。
   * **必須從舊機打包壓縮後移轉**（因為資料未追蹤於 Git）。
3. **個人與決策資產（Personal & Portfolio）**：
   * 存放個人持倉狀態（`portfolio/portfolio_state.json`）、自選股資料庫（`personal/watchlists/watchlists.v3.sqlite`）、推薦系統紀錄（`personal/recommendation_h20/`）以及輸出目錄下的決策日誌（`OUTPUT_ROOT/portfolio/journal_entries.jsonl`）。
   * **若您有記錄個人持倉、自選名單或交易日誌，必須依 Tier C 一併打包移轉**。
4. **報告根目錄（`OUTPUT_ROOT`，預設 `.../FA_Data/output`）**：
   * 存放本機執行報告、暫存與排程收據。
   * **新機建立空目錄即可**（除上述 `OUTPUT_ROOT/portfolio/` 需搬移外），程式執行時會自動初始化。

---

## 舊機按需打包資料清冊（到底要打包壓縮哪些資料？）

為了避免平時在磁碟常駐無用的巨型壓縮檔，baldr 採**按需打包（On-demand Packaging）**。需要移機時，依您的需求選擇以下分級：

### 打包分級清單

| 等級與用途 | 包含之檔案／目錄相對路徑 | 預估容量（未壓縮／ZIP） | 適用場景與說明 |
|---|---|---|---|
| **Tier A：最小核心行情包**<br>*(最推薦／輕量快速)* | • `sqlite/twstock.db`（核心 SQLite 主資料庫）<br>• `daily_price/*.csv`（TWSE 上市日行情）<br>• `daily_price_tpex/*.csv`（TPEx 上櫃日行情） | 約 4.39 GB ／ **約 1.56 GB** | • 新電腦快速恢復運行環境<br>• 啟動桌面 GUI 介面<br>• 瀏覽最新大盤行情與個股歷史價格 |
| **Tier B：完整日常研究與選股包**<br>*(功能完整／日常標配)* | **包含 Tier A 全部項目**，另加：<br>• `broker_flow/`（券商分點籌碼進出，約 218 MB）<br>• `financial_data/`（季財報相關數據，約 132 MB）<br>• `technical_analysis/`（全市場個股技術指標快取，約 2.25 GB）<br>• `meta_data/` 現役檔案（約 300 MB，包含 `all_stocks_data.csv`、`stock_data_whole.csv*`、`companies*.csv`、`Date_table.csv`、`market_index.csv`、`industry_*.csv`、`monthly_revenue_availability.csv`、`broker_branch_registry.csv`、`official_market_daily_sources/`、`industry_chain_snapshots/` 等）<br>• *選配*：`industry_analysis/`、`industry_correlation/`、`KY__buy_sell/`、`TS_daily/` | 約 9.95 GB ／ **約 3.2–3.8 GB** | • 需要完整使用決策工作台（Workbench）<br>• 策略建議（Advice）與候選名單篩選<br>• 券商分點籌碼與全市場技術指標研究 |
| **Tier C：個人持倉、自選與決策日誌**<br>*(個人重要資料／強烈建議包含)* | • `portfolio/portfolio_state.json`（**個人持倉、現金部位與損益紀錄**，約 1 KB）<br>• `personal/`（**個人自選股** `personal/watchlists/watchlists.v3.sqlite`、推薦校準 `personal/recommendation_h20/`，約 3~15 MB）<br>• `OUTPUT_ROOT/portfolio/`（**決策日誌** `journal_entries.jsonl`、交易紀錄 `trades.jsonl`，約 1~5 MB）<br>• `models/`（模型權重與 lineage，約 5.5 MB）<br>• *選配*：已保存研究報告（優先以 `scripts/copy_research_output.py`、`scripts/copy_price_bookmarks.py` 匯出） | 約 10–150 MB | 移轉個人自選清單、持倉狀態、交易歷史與研究決策日誌 |

---

## 嚴格排除清單（避坑指南：千萬不要整包硬拷！）

> [!WARNING] 
> **千萬不要把整個 `FA_Data` 或專案目錄直接右鍵壓縮！**  
> 歷史暫存、過期備份與大型 ML 產物合計**超過 870 GB**，若無腦全包會導致壓縮幾十小時、隨身碟塞爆，且絕大部分是新環境完全不需要的垃圾廢料。

### 打包時必須嚴格排除的項目（合計 > 870 GB）：
* ❌ `sqlite/backups/`（約 23.5 GB，SQLite 自動定時產生的歷史舊備份）
* ❌ `sqlite/twstock.db.bak*`（約 1.4 GB，修復或暫存備份檔）
* ❌ `meta_data/backup/` 與 `meta_data/backups/`（約 17.2 GB，歷史舊 metadata 備份）
* ❌ `meta_data/*.lock`（鎖定暫存檔，例如 `.monthly_revenue_availability.csv.monthly-revenue.lock`）
* ❌ `output/release_v4/`（約 444.6 GB，ML 歷史模型訓練與 PIT 分塊暫存）
* ❌ `output/scheduled/`（約 74.5 GB，歷史排程收據與自動修復 log）
* ❌ `output/research_only/`（約 10.5 GB）、`output/evidence_working_copies/`（約 3.1 GB）
* ❌ `BaldrStorage/`（約 183.5 GB，pytest 暫存、repo-dist 與建置產物）與 `FA_ML_Research/`（約 103.1 GB）
* ❌ 任何 `.env`、API 金鑰或 Windows DPAPI 憑證（具本機機器綁定特性，搬至新電腦無法解密且有外洩風險）

---

## 舊機打包前安全檢查（避免資料庫損壞）

在舊機進行打包壓縮前，請務必確認以下兩點：
1. **停止寫入程序**：關閉桌面 GUI（`ui_qt`）、排程任務或任何資料更新腳本。
2. **核對 SQLite WAL 狀態（關鍵步驟）**：
   檢查 `sqlite/twstock.db-wal` 檔案大小：
   * 若大小為 **0 bytes** 或檔案不存在：代表已乾淨 checkpoint，可安全打包 `twstock.db`。
   * 若大小 **> 0 bytes**：代表仍有暫存交易未寫入主資料庫！請在舊機執行以下命令完成 checkpoint：
     ```powershell
     $env:PYTHONUTF8 = "1"
     .\.venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('F:/Min/Python/Project/FA_Data/sqlite/twstock.db'); conn.execute('PRAGMA wal_checkpoint(TRUNCATE);'); conn.close(); print('Checkpoint 完成，WAL 已歸零！')"
     ```

---

## 新電腦收到壓縮包後的放置與設定

### 1. 解壓縮至新機資料目錄
在硬碟建立您的新機資料目錄（例如 `D:\BaldrData` 或維持 `F:\Min\Python\Project\FA_Data`），將壓縮包解壓進去。解壓後的目錄樹應呈現：
```text
<DATA_ROOT>\
├── sqlite\
│   └── twstock.db
├── daily_price\
│   └── *.csv
├── daily_price_tpex\
│   └── *.csv
├── broker_flow\          (若選 Tier B)
├── financial_data\       (若選 Tier B)
├── technical_analysis\   (若選 Tier B)
├── meta_data\            (若選 Tier B)
├── portfolio\            (若選 Tier C，持倉部位 portfolio_state.json)
├── personal\             (若選 Tier C，自選股 watchlists.v3.sqlite)
└── models\               (若選 Tier C，模型權重)
```

### 2. 建立新機輸出目錄與放入決策日誌
在新機建立空白輸出目錄（例如 `D:\BaldrReports`）：
```text
<OUTPUT_ROOT>\
└── portfolio\            (若選 Tier C，放 journal_entries.jsonl 與 trades.jsonl)
```

### 3. Clone 代碼庫並安裝環境
在新機的 PowerShell 視窗執行：
```powershell
# 1. 取得最新代碼庫
git clone <repo_url> baldr
cd baldr

# 2. 建立 Python 3.11 虛擬環境並安裝依賴
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt -c requirements-py311-windows.constraints.txt

# 3. 指定資料根目錄並啟動 GUI
$env:DATA_ROOT = "D:\BaldrData"          # 替換為您的新機解壓路徑
$env:OUTPUT_ROOT = "D:\BaldrReports"      # 替換為您的新機報告路徑
.\.venv\Scripts\python.exe ui_qt\main.py
```

啟動後至「**數據更新**」分頁查看來源狀態，確認資料庫與行情日期正常識別即可！

---

<a id="舊機按需打包-prompt需要移機資料包時直接複製給-agent"></a>
## 舊機按需打包 Agent Prompt（直接複製給舊機 Agent / Codex）

在**舊機**上需要 Agent 協助自動排除垃圾、精確打包時，將下方內容直接複製發送給 Agent：

```text
請依 AGENTS.md 與 docs/07_guides/FIRST_INSTALL_PROMPT.md 的打包清冊，為我建立跨電腦移機資料包。

來源 DATA_ROOT：F:\Min\Python\Project\FA_Data
來源 OUTPUT_ROOT：F:\Min\Python\Project\FA_Data\output
輸出壓縮檔路徑：<指定輸出路徑，例如 F:\BaldrTransfer\FA_Data_Transfer.zip>
打包等級：<選 Tier A（最小核心，約 1.56 GB）或 Tier B（完整日常研究，約 3.5 GB）>
是否納入個人持倉、自選股與決策日誌（Tier C）：true / false

執行要求：
1. 先唯讀檢查來源 DATA_ROOT，確認無寫入程序正在寫入 sqlite/twstock.db，且核對 twstock.db-wal 狀態；若 WAL > 0 bytes 先執行 PRAGMA wal_checkpoint(TRUNCATE) 歸零，不強行裸拷活躍中資料庫。
2. 嚴格只納入所選 Tier 清單內的目錄與檔案（若含 Tier C，請納入 portfolio/portfolio_state.json、personal/ 與 OUTPUT_ROOT/portfolio/）。
3. 明確排除 sqlite/backups/、sqlite/twstock.db.bak*、meta_data/backup/、meta_data/*.lock、output/release_v4/、output/scheduled/、BaldrStorage/、FA_ML_Research/ 與任何 .env / 憑證私鑰（合計排除 > 870 GB）。
4. 打包完成後產出同目錄下的 TRANSFER_MANIFEST.json，記錄每個納入檔案的相對路徑、原始 bytes、mtime 與 SHA-256，以及最終 ZIP 檔案的總大小與 SHA-256 供新機核驗。
```

---

## 新機首次安裝／移機 Agent Prompt（在新機交給 Codex / Agent）

在新電腦將壓縮包解壓後，將下方內容交給新電腦上的 Agent / Codex 自動配置環境與驗證：

```text
請依 AGENTS.md、README 與 docs/07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md，完成 baldr 首次安裝或完整移機。

模式：owner-migration（已從舊機移轉資料包）/ fresh（全新安裝）
執行範圍：configure（建立環境、設定目錄、唯讀核驗）
新機Repository：<代碼庫絕對路徑>
GUI Runtime：source
新機Windows時區：Taipei Standard Time
DATA_ROOT：<新機解壓後的資料根目錄絕對路徑>
OUTPUT_ROOT：<新機報告根目錄絕對路徑>
舊機清冊（若有）：<TRANSFER_MANIFEST.json 絕對路徑與 SHA-256>
舊機移交writer已停止：true

授權界線：
1. 建立新 .venv、安裝 runtime 依賴並核驗 Python 環境。
2. 核驗 DATA_ROOT 內的 sqlite/twstock.db、行情 CSV、metadata 與個人資產是否可唯讀開啟。
3. 執行唯讀健康檢查，不修改既有歷史資料庫，不註冊未經核准之背景排程。
4. 啟動並驗證桌面 GUI 可正常載入最新市場資料與個人持倉／自選名單。
```

---

## 清冊驗證工具（bootstrap-plan）

若需要對新機 manifest 進行唯讀合規性審查，可執行：

```powershell
.\.venv\Scripts\python.exe scripts\document_control.py bootstrap-plan --manifest output\tasks\<task_id>\bootstrap.json
```

`bootstrap-plan` 僅會唯讀檢查路徑、來源常數與資產 SHA，不會搬移資料或修改任何系統排程。詳細運維說明請參閱 [機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md) 與 [安裝指南](INSTALL_GUIDE.md)。
