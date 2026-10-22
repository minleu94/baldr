# Scripts 目錄說明

月營收明選原件的歷史分批擷取、版本歸檔、固定SHA查詢與資格包百分率研究入口為 `scripts/monthly_revenue_archive.py`；命令、參數與拒絕原因見[月營收研究管線](MONTHLY_REVENUE_RESEARCH_PIPELINE.md)。輸出限repo `output`，不自動接正式資料或排程。

## 概述
本目錄包含系統中獨立的腳本，主要用於數據更新、修復、合併以及參數優化等任務。這些腳本在系統架構中扮演重要角色，確保數據的完整性和系統的穩定性。

下方 `python` 命令範例假設目前 shell 使用專案相容的 Python 3.11 `.venv`。Windows PowerShell 可直接使用：`.\.venv\Scripts\python.exe`，不必啟用環境；新環境安裝看 [INSTALL_GUIDE](INSTALL_GUIDE.md)。不要把未啟用環境時解析到的全域 Python 當成預設；受限備援條件見[System Python 備忘](../08_technical/RUN_WITHOUT_VENV.md)。

## 相關文檔
- [系統架構文檔](../01_architecture/system_architecture.md) - 系統架構和模組說明
- [早期資料收集架構藍圖（歷史）](../09_archive/DATA_COLLECTION_ARCHITECTURE_HISTORY.md) - 舊 API、CSV 與路徑設計追溯
- [早期技術分析優化備忘錄（歷史）](../09_archive/TECHNICAL_ANALYSIS_OPTIMIZATIONS_HISTORY.md) - 原 API／路徑範例已過時；目前實作與模組邊界以 [System Architecture](../01_architecture/system_architecture.md) 和 source 為準
- [專案快照](../00_core/PROJECT_SNAPSHOT.md) - 當前開發進度總覽
- [測試目錄說明](tests_readme.md) - 測試相關說明

## 資料路徑與設定

使用 `TWStockConfig` 的腳本以 `DATA_ROOT`、`OUTPUT_ROOT` 與 `PROFILE` 解析資料和輸出位置；命令列覆蓋須逐一確認該腳本是否支援。`update_all_data.py` 與 `update_stock_data.py` 目前先後解析共用設定與腳本參數，命令列參數互相衝突，請不要照下方舊範例執行，也不要假設所有入口都支援 `--dry-run`。不要使用舊文件中的 `TWSTOCK_DATA_DIR` 或直接在建構後改寫衍生欄位 `base_dir`。

完整環境設定與隔離操作請看 [Application Manual](APPLICATION_MANUAL.md)；資料來源與輸出位置看 [DATA_FETCHING_LOGIC](../03_data/DATA_FETCHING_LOGIC.md) 及 [daily data update guide](../03_data/daily_data_update_guide.md)。目前設定欄位定義見 [TWStockConfig](../../data_module/config.py)。

## 腳本列表

下方帶固定日期的命令只是歷史參數範例。執行前請換成此次明確核定的日期範圍，並確認該腳本實際解析的資料與輸出根；不要照抄舊日期當作目前更新範圍。

### 1. 數據更新腳本

#### 基本面因子診斷（工程入口）

`scripts/inspect_fundamental_factors.py` 讀取明選SQLite與相鄰的 `meta_data/monthly_revenue_availability.csv`，列出合格因子數及具名診斷，不抓取、不回補、不保存研究，也不連接ScoringEngine。管理者明示 `--db-file`、`--decision-date YYYY-MM-DD` 與可重複的 `--stock-code`；`--diagnostic-limit`／`--stock-summary-limit` 只限制顯示。批次選股參數 `--all-monthly-revenue-stocks` 不等於來源母體接受。先核隔離資料與來源版本；執行仍須遵守[Root owned Job／RAM與mutex規則](../agents/shared_context.md#python-驗證程序與資源)，不要把未驗正式庫當作示範。

月營收 pack 方法為 `fundamental-revenue-pack.v2`。三月趨勢必須含當期及前兩個曆月；缺月或不可用品質標missing並skip。新高只與已提供的前期月份比較，沒有前期回unknown；不能讀成全歷史新高。YoY／MoM沿原Decimal比率；消耗輸入最晚可得日不得晚於決策日，歧義版本、缺可得日、零基期或不可用值有獨立診斷，不補零、不調門檻。

原 `ResearchRunService` 可由工程caller保存factor快照；新程序讀回原方法、輸入版本及skip，不重算或升級舊結果。此次僅在自有合成SQLite驗完整三月／缺月／單月的服務→CLI→保存→fresh，並核原件SHA不變。尚未交正常UI、官方歷史新高、來源用途或完整F12；134試用入口不變，詳[135 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment135-revenue-calendar-history)。

#### `batch_update_daily_data.py`（CLI 批次替代入口）
- **功能**：批量更新多個交易日的每日股票數據（使用主模組）
- **特點**：
  - 使用主模組 `data_module/data_loader.py` 的 `download_from_api()` 方法
  - 自動更新多個交易日（排除週末）
  - 已包含 delay time（預設 4 秒，可調整）
  - 自動跳過已存在的文件
  - 顯示詳細進度和結果摘要
- **使用範例**：
  ```bash
  # 更新從指定日期之後到今天的所有交易日
  python scripts/batch_update_daily_data.py --start-date 2025-08-28
  
  # 更新指定日期範圍
  python scripts/batch_update_daily_data.py --start-date 2025-08-28 --end-date 2025-09-05
  
  # 自訂延遲時間（更安全，避免 API 限制）
  python scripts/batch_update_daily_data.py --start-date 2025-08-28 --delay-min 4 --delay-max 4
  ```
- **詳細說明**：請參考 [HOW_TO_UPDATE_DAILY_DATA.md](../03_data/HOW_TO_UPDATE_DAILY_DATA.md)

#### `update_daily_stock_data.py` ⭐
- **功能**：使用主模組更新單日股票數據
- **使用範例**：
  ```bash
  # 更新單日數據（只更新 daily_price）
  python scripts/update_daily_stock_data.py --date 2025-08-29
  
  # 更新並自動合併到 meta_data
  python scripts/update_daily_stock_data.py --date 2025-08-29 --merge
  ```
- **詳細說明**：請參考 [HOW_TO_UPDATE_DAILY_DATA.md](../03_data/HOW_TO_UPDATE_DAILY_DATA.md)

#### `update_all_data.py`
- **用途**：舊式全資料更新入口，範圍包含市場指數、產業指數與每日價格。
- **目前狀態**：CLI 參數解析衝突。入口先呼叫 `TWStockConfig.from_args()`，再建立自己的 parser；`--days`、`--start`、`--end`、`--check`、`--all` 會先被共用 parser 拒絕，共用設定參數也會再被腳本 parser 拒絕。舊範例不可用；未修正 parser 前，日常更新請走 UI 指南。

#### `update_stock_data.py`
- **用途**：舊式股票資料更新入口。
- **目前狀態**：與 `update_all_data.py` 有相同的共用設定／腳本參數解析衝突；`--date`、`--start-date`、`--end-date`、`--schedule`、`--batch` 等腳本參數會在共用 parser 階段被拒絕。單日命令列入口請看下方 `update_daily_stock_data.py` 與[每日更新指南](../03_data/HOW_TO_UPDATE_DAILY_DATA.md)。

### 2. 數據修復腳本

#### `fix_market_index.py`
- **功能**：直接執行市場指數修復；目前沒有 `--report` 或 `--backup` CLI 參數，也不是唯讀檢查入口。不要照舊的 `--report --backup` 範例執行。

#### `fix_industry_index.py`
- **功能**：直接執行產業指數修復；目前沒有 `--report` 或 `--backup` CLI 參數，也不是唯讀檢查入口。不要照舊的 `--report --backup` 範例執行。

#### `merge_daily_data.py`
- **功能**：合併每日價格數據
- **使用範例**：
  ```bash
  python scripts/merge_daily_data.py
  ```
- **注意**：目前唯一宣告的選用參數是 `--force-all`，會強制重新合併全部資料；`--report` 與 `--compress` 不受支援。

### 3. 技術指標計算腳本

#### `calculate_technical_indicators.py`
- **功能**：計算所有股票的技術指標
- **使用範例**：
  ```bash
  python scripts/calculate_technical_indicators.py
  ```

#### `simple_technical_calc.py`
- **功能**：簡化版技術指標計算（重命名自 simple_indicator_calc.py）
- **使用範例**：
  ```bash
  python scripts/simple_technical_calc.py
  ```

#### `date_specific_indicator_calc.py`
- **功能**：特定日期指標計算
- **使用範例**：
  ```bash
  python scripts/date_specific_indicator_calc.py
  ```

### 4. 工具腳本

#### `audit_document_encoding.py`
- **功能**：唯讀掃描文件編碼，確認 repo Markdown 與 `docs/` 下文字型文件是否可 strict UTF-8 解碼，並列出疑似 mojibake 片段。
- **使用範例**：
  ```bash
  python scripts/audit_document_encoding.py

  # 若希望疑似 mojibake 也使指令失敗
  python scripts/audit_document_encoding.py --fail-on-mojibake
  ```

#### `market_date_range.py`
- **功能**：市場日期範圍管理
- **使用範例**：
  ```bash
  python scripts/market_date_range.py
  ```

## 腳本分類

### 📊 數據管理腳本
- `batch_update_daily_data.py` - 批次更新每日股票數據（CLI 替代入口）
- `update_daily_stock_data.py` - 更新單日股票數據（CLI 替代入口）
- `update_all_data.py` - 全面數據更新
- `update_stock_data.py` - 股票數據更新
- `merge_daily_data.py` - 數據合併

### 🔧 數據修復腳本
- `fix_market_index.py` - 市場指數修復
- `fix_industry_index.py` - 產業指數修復

### 📈 技術分析腳本
- `calculate_technical_indicators.py` - 完整技術指標計算
- `simple_technical_calc.py` - 簡化技術指標計算
- `date_specific_indicator_calc.py` - 特定日期指標計算

### 🛠️ 工具腳本
- `audit_document_encoding.py` - 文件 UTF-8 / mojibake 稽核
- `market_date_range.py` - 日期範圍管理

## 日常操作與維修入口

日常資料更新以[每日更新指南](../03_data/HOW_TO_UPDATE_DAILY_DATA.md)及其中的 UI 流程為入口；該指南另列經核對的 CLI 替代方式。本頁的「CLI 替代入口」只表示可按該指南的條件使用，不代表日常操作優先推薦。執行任何會更新、合併或修復資料的命令前，先確認該入口實際解析到的 `DATA_ROOT`／`OUTPUT_ROOT`；不同腳本支援的設定覆蓋方式不一，應先看本頁上方的資料路徑注意事項與對應操作指南。本頁也不定義額外的「更新 → 合併 → 重算」固定串接順序，避免重複執行 UI 已整合的 SQLite 同步與技術指標增量更新。

資料修復前先查看對應 QA、資料來源與實際腳本行為。`fix_market_index.py` 和 `fix_industry_index.py` 是直接執行修復的入口，不支援 report-only；不可把它們當成檢查命令。需要只讀診斷時，使用對應的狀態檢查或 QA 工具。

## 注意事項

### 執行前準備
- 確保已正確設置環境變量和依賴項
- 建議在執行腳本前先備份數據，以防意外情況發生
- 確保數據目錄具有適當的讀寫權限

### 執行時注意
- 定期檢查日誌文件以監控系統運行狀況
- 注意內存使用，特別是在處理大量數據時
- 某些腳本可能需要較長時間執行，請耐心等待

### 錯誤處理
- 如果腳本執行失敗，檢查日誌文件了解詳細錯誤信息
- 某些腳本支持重試機制，可以多次執行
- 如遇到數據問題，使用相應的修復腳本

## 與其他文檔的關聯

- **每日數據更新詳細指南**：請參考 [HOW_TO_UPDATE_DAILY_DATA.md](../03_data/HOW_TO_UPDATE_DAILY_DATA.md) ⭐
- **數據獲取邏輯說明**：請參考 [DATA_FETCHING_LOGIC.md](../03_data/DATA_FETCHING_LOGIC.md)
- 詳細的系統架構和數據流程可參考 `../01_architecture/system_architecture.md`
- 早期 API、CSV 與檔案路徑設計見[歷史藍圖](../09_archive/DATA_COLLECTION_ARCHITECTURE_HISTORY.md)；現行流程以 [DATA_FETCHING_LOGIC](../03_data/DATA_FETCHING_LOGIC.md) 為準
- 測試相關的說明可參考 `tests_readme.md`
- 早期技術分析優化備忘錄只供歷史追溯，見 [Archive 原文](../09_archive/TECHNICAL_ANALYSIS_OPTIMIZATIONS_HISTORY.md)；目前模組邊界與實作請看系統架構及 source

## 版本更新記錄

### v1.2.1 (2024-04-08)
- 重命名 `simple_indicator_calc.py` 為 `simple_technical_calc.py`
- 刪除重複的 `config.py` 檔案
- 更新腳本說明和分類

### v1.2.0 (2024-04-02)
- 新增 `date_specific_indicator_calc.py` 腳本
- 優化 `calculate_technical_indicators.py` 功能
- 改進錯誤處理和日誌記錄 
