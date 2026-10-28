# 2026-10-27 Workbench Advice 摘要與候選卡

## 範圍與畫面判讀

調整 Workbench「今日策略建議」區塊的資訊呈現。原 864 px 截圖仍以舊分類顯示 Advice 0 列、Professional 研究候選 10 列、配置資料列 0 列；Gate 1 Advice 解鎖後，未升格 candidate 保留為 Advice，摘要改顯示 Advice 總數與未升格 Advice 子數。候選理由塞在固定欄寬表格，使字串被截短；這是版面造成的可讀性問題。來源缺少信心層級、當日價格等欄位，會造成個別狀態顯示「未提供」或資格限制，但不是原表格難讀的原因。

## 呈現方式與欄位意義

- 三張摘要卡分別顯示 Advice 總資料列、未升格 Advice 列與配置資料列。這些數字是來源回傳的列數；「配置資料列 0」不代表配置為 0%。未升格 Advice 仍屬 Advice；策略升格成熟度由限制提示呈現。
- 摘要行保留模式、決策日與資料日。提示說明「未提供」代表來源缺少欄位，不等於 0 分或安全狀態。
- 未升格策略 Advice 改為獨立卡片，桌面寬度兩欄且各自垂直堆疊、窄視窗一欄。卡面列標的、建議動作、決策信心、最多兩項編號理由、首要策略限制、主要風險、資料品質與可成交性；其餘理由／限制以數量提示，完整內容仍可展開查看。
- 點卡片內容或「詳情」會選取同一筆 Advice，並在卡片內顯示原本共用的完整判讀與研究紀錄操作；一次只展開一張。收合會清除該列選取與操作狀態。
- 未升格策略仍是 Advice；此呈現不將其降為研究專用產品，也不代表自動下單。沒有新增欄位推定，也沒有改動來源、DTO、排序、策略、資料品質、Gate 或寫入行為。

## 驗證

- `tests/test_workbench_advice_contract.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_ui_qt_workbench_candidate_selection.py`：99 passed。包含桌面雙欄／窄版單欄重排、點卡／理由展開、卡片切換、同筆操作歸屬及收合清除狀態。
- 必要 `tests/test_ui_qt_update_view_workbench.py`：97 passed。
- 必要 `scripts/qa_validate_update_tab.py`：25 passed、0 failed、4 skipped。
- `ui_qt/views/workbench_view.py` 與 `ui_qt/models/workbench_table_models.py` targeted mypy、兩檔 `py_compile`：通過。
- Repo-wide mypy 未通過：被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋。
- Offscreen 以五筆合成 Advice 產出收合／展開畫面，確認桌面雙欄獨立堆疊、窄版單欄及完整判讀原地展開；環境 fallback 字型未提供可讀中文字形，因此產圖只供檢視結構，不能作為字型或美觀驗收。畫面位於本機任務視覺化目錄：`C:\Users\archi\.codex\visualizations\2026\10\27\01a17c6b-8f6f-7b10-8a1e-9c996cc05997\workbench_advice_card_layout\final_visual\advice_cards_collapsed.png` 與 `advice_cards_expanded.png`。
- Python 驗證依序執行於受管 Windows Job，Job memory limit 為 8 GiB、process limit 為 12；執行前可用記憶體約 20.4 GiB，各子程序自然結束，Job active process count 為 0。
- Scoped document control 檢查 6 個文件來源／12 個 feature，回報 33 個既有問題（包括 Snapshot 舊錨點及 `output/` junction 存取拒絕）；本次 QA 文件與新增導覽連結沒有列為缺件。Feature Map JSON 解析及本輪 scoped `git diff --check` 通過。

## 限制

尚未在原生 MainWindow、一般中文字型、不同 DPI 或 Owner UAT 中驗收。Offscreen 卡片內容使用既有 Advice DTO 欄位，不驗證實際來源完整度、正式資料資格、投資用途或端到端響應時間。
