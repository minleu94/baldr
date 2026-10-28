# Daily Decision Desk 資料脈絡優先版面 QA

日期：2026-10-27  
任務：`decision-desk-evidence-first-20261027`  
範圍：只調整 Daily Decision Desk 頂部區塊順序。原有「總覽」中的評估／快照判讀日、來源市場資料日、quality 與警示摘要現在先於「今日主結論」；保存推薦、完整警示與後續研究區塊沿用原呈現。未改 DTO、來源讀取、判斷／計算、Gate 或寫入行為。

## 驗收

- 畫面與操作手冊一致：讀者先核對決策日、行情資料日、quality、warnings 與來源，再讀主結論與市場內容。
- Offscreen 版面測試確認來源資料日期與品質摘要在主結論之前；主要市況廣度圖卡仍完整落在 `1280×620` 視窗 viewport 內。
- 保留既有「總覽」、保存推薦與完整警示的內容及唯讀語意。

## 驗證結果

| 檢查 | 結果 |
|---|---|
| `pytest tests/test_ui_qt_decision_desk_view.py -q -o addopts=` | 54 passed |
| 必要 Workbench UI：`pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 97 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| 全域 mypy | 未通過；未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 有既存語法錯誤，檢查提前停止 |
| 定向 mypy：`ui_qt/views/decision_desk_view.py` | Success，1 source file |
| 變更 Python 檔 `py_compile` | 通過 |
| 本任務 scoped `git diff --check` | 通過 |
| Scoped document control | 未通過；8 個來源中有 4 個既有 PROJECT_SNAPSHOT 錨點缺件，本任務新增連結未缺件 |
| Task-wide document control | 未通過；共 63 個既有連結／錨點問題，未列本任務 Coverage 結構錯誤或新增 QA 連結缺件 |
| Native Windows GUI／Owner UAT | 未執行 |

Python 驗證均由本任務 root-owned bounded QA runner 序列執行；該 Job 的 8 GiB 記憶體／12 程序限制讀回相符，結束後程序數歸零。此次只驗證版面與既有工程回歸，不量測正式資料延遲，也不代表整體產品、Gate 或 Danny Quant 等級比較已完成。

## 文件同步

Daily Decision Desk 操作手冊本來要求先核對資料日期、品質、警示及來源；本次將版面調整為符合該既有判讀流程。功能文件、操作手冊、產品 UX QA 索引與 PROJECT_SNAPSHOT 已連結本紀錄。架構、資料儲存與產業／題材設計契約未改。
