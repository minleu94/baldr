# 2026-10-27 Workbench Advice 快速判讀與窄版欄位

## 範圍

依 864 px 截圖檢視 Workbench 首屏 Advice 區。資料來源與 DTO 不變；本輪只調整標籤、缺值說明、理由摘要及表格欄位顯示。

## 證據判讀

- 截圖顯示正式 Advice 0 列、Professional 研究候選 10 列、配置列 0 列。畫面不是完全沒有資料；「決策信心：未提供」代表來源未提供 `confidence_tier`，配置列 0 代表這次沒有配置資料列，不代表 0% 配置。
- 研究候選的「研究」動作供人工研究，不是正式 Advice 或交易指令。支持理由欄摘要支持原因與 Why Not 政策／資格限制；長理由仍在 tooltip 與選列詳情。
- 截圖視窗約 864 px。舊表格固定欄位寬度為 76、136、100、220、248 px，最後的理由摘要只剩約 32 px；被截斷主要是欄寬配置，與缺值不同。

## 變更

- 保留「今日策略建議」區塊名稱與正式／研究分組，新增來源列數、缺值和配置零列的白話說明，以及研究候選用途提示。
- 把 `支持／政策資格` 改為 `支持理由／資格限制`，縮短主表快速理由字串；完整來源理由、風險與證據仍由 tooltip／選列詳情核對。
- 視窗小於 1100 Qt logical px 時，表格收合主要風險與資料狀態欄，將寬度交給理由摘要；寬版恢復兩欄。
- 未更動 Advice DTO、判斷、資料、金融數值、資格 Gate 或寫入行為。

## 驗證

- Offscreen Qt 的 Advice 表格尺寸切換測試覆蓋 864／1280 px，欄位收合與恢復斷言通過。
- `tests/test_ui_qt_workbench_view.py` + `tests/test_workbench_advice_contract.py`：65 passed、4 failed。失敗項目為必要欄位文案舊斷言、Professional 回測導覽按鈕可見性、空 Advice 舊標題斷言、選列卡舊高度斷言；它們不在本輪修改差異內，保留為目前工作樹的未解 regression，未改測試門檻或隱去結果。
- `tests/test_ui_qt_update_view_workbench.py`：97 passed。
- `scripts/qa_validate_update_tab.py`：25 passed、0 failed、4 skipped。第一次使用預設 `output/` log 位置時被受限工作區拒絕；改以 `BALDR_UPDATE_TAB_QA_LOG_DIR` 將報告寫入任務視覺化工作區後重跑成功。報告位於 `C:\Users\archi\.codex\visualizations\2026\10\27\01a17c6b-8f6f-7b10-8a1e-9c996cc05997\workbench_advice_qa\update_tab\VALIDATION_REPORT.md`。
- 修改的兩個 UI／model 模組 targeted mypy：通過；指定的全域 mypy 仍被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋。
- 四個修改 Python 檔 `py_compile`：通過；`git diff --check`：通過。
- Document Control 對本輪 QA、QA index 及 UI feature 文件檢查通過，Feature Map JSON 可解析。Manual／Snapshot 檢查仍回報既有 output junction 存取拒絕與舊錨點缺件；未列出本輪新增連結問題。
- Python 驗證以單一 owned Windows Job 序列執行；啟動可用 RAM 約 25.5 GiB，Job 上限 8 GiB／12 個程序，各程序自然結束且 Job 剩餘程序為 0。

## 限制

此結果只確認 offscreen 測試下的狀態與欄位切換，不代表原生 MainWindow 繪製、不同 DPI 或 Owner UAT 已接受。形式來源資格、Gate、正式資料與端到端載入時間均未改動或重驗。
