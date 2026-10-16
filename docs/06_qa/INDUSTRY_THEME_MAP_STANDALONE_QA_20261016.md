# 台股 L2 產業鏈與題材萃取對應獨立模組 QA 驗證收據 (2026-10-16)

- **任務 ID**：`industry-theme-map-standalone-20261016`
- **受測模組**：[`decision_module/industry_theme_map.py`](../../decision_module/industry_theme_map.py)
- **測試套件**：[`tests/test_industry_theme_map.py`](../../tests/test_industry_theme_map.py)
- **設計文件**：[`docs/02_features/INDUSTRY_THEME_MAP_DESIGN.md`](../02_features/INDUSTRY_THEME_MAP_DESIGN.md)

---

## 1. 驗證範圍與邊界

1. **獨立性與零入侵驗證**：
   - 確認 [`decision_module/industry_theme_map.py`](../../decision_module/industry_theme_map.py) 僅匯入 `data_module.config.TWStockConfig` 取得路徑，未修改任何既有 `ui_qt`、`app_module` 或每日選股／回測程式碼。
2. **三大產出檔案完整性驗證**：
   - 產業檔案：`D:/Min/Python/Project/FA_Data/meta_data/industry_chains_catalog.csv`（25 條標準產業鏈）。
   - 題材檔案：`D:/Min/Python/Project/FA_Data/meta_data/industry_themes_catalog.csv`（90 個有效 L2 題材，均滿足 `company_count >= 3`）。
   - 產業題材股票對應檔案：`D:/Min/Python/Project/FA_Data/meta_data/industry_theme_stock_map.csv`（2,535 筆對應列，涵蓋 2,341 檔 4 碼普通股，每檔股票恰好 1 筆 `is_primary=True`）與季度快照 `industry_chain_snapshots/industry_theme_stock_map_20261016.csv` + `manifest.json`。
3. **PIT 與來源資格防線 (`lookahead`, `source_qualification`, `decimal_or_integer`)**：
   - 確認 `load_pit_mapping` 對齊 `available_date <= as_of_date`；當查詢日早於快照可見日時，顯式回傳 `pit_status = "current_snapshot_replay_only"` 與 `"theme_mapping_uses_post_hoc_snapshot"` 警告。
   - 確認無新增任何裸 `float` 計算，所有統計計數與排序序號均為明確 `int`。

---

## 2. 實跑命令與結果

```text
$env:PYTHONUTF8=1
.\.venv\Scripts\python.exe -m py_compile decision_module/industry_theme_map.py tests/test_industry_theme_map.py
.\.venv\Scripts\python.exe -m pytest tests/test_industry_theme_map.py -q -o addopts=
.....                                                                    [100%]
5 passed in 0.75s

.\.venv\Scripts\python.exe -m mypy decision_module/industry_theme_map.py
Success: no issues found in 1 source file

.\.venv\Scripts\python.exe -m decision_module.industry_theme_map build-files --snapshot-date 2026-10-16
-> total_chains: 25, total_themes: 90, total_companies: 2341, total_rows: 2535
```
