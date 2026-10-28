# 2026-10-27 Workbench Advice 摘要與候選卡

## 範圍與畫面判讀

調整 Workbench「今日策略建議」區塊的資訊呈現。Gate 1 解鎖後，Professional candidate 仍保留 `PROFESSIONAL_CANDIDATE` 分類，但 Advice 摘要應包含它們。原卡片實作只把未升格 candidate 交給小卡格線；正式 `FORMAL_ADVICE` 仍留在 Advice 橫向資料表。原生 MainWindow 讀到 10 筆正式 Advice、0 筆未升格 Advice 時，因此仍顯示被截短的表格。這是渲染分流不完整，不是 Advice 缺資料；本次改為所有策略 Advice 都進卡片格線，保留來源順序，並將正式 Advice 表格留作非顯示的相容 model。來源缺少信心層級、當日價格等欄位會使個別狀態顯示「未提供」或資格限制，但不是版面難讀的原因。

## 呈現方式與欄位意義

- 三張摘要卡分別顯示 Advice 總資料列、未升格 Advice 列與配置資料列。這些數字是來源回傳的列數；「配置資料列 0」不代表配置為 0%。未升格 Advice 仍屬 Advice；策略升格成熟度由限制提示呈現。
- 摘要行保留模式、決策日與資料日。提示說明「未提供」代表來源缺少欄位，不等於 0 分或安全狀態。
- 正式 Advice 與未升格策略 Advice 統一以逐筆閱讀的小卡網格呈現：寬視窗三欄、中等寬度兩欄、窄視窗一欄。卡面以動作、信心徽章和理由／限制膠囊整理資訊，列標的、最多兩項編號理由、首要策略限制、主要風險、資料品質與可成交性；其餘理由／限制以數量提示，完整內容仍可展開查看。可選配置研究列維持表格。
- 點卡片或右上角箭頭會選取同一筆 Advice，並在卡片內顯示原本共用的完整判讀與研究紀錄操作；展開卡會獨佔一列以保留詳情寬度，其餘 Advice 保持小卡排列。每日候選連結會在同一張卡片中選取並展開精確符合 result ID、股票與日期的列；遇到缺件或重複身份仍 fail closed。一次只展開一張；收合會清除該列選取與操作狀態。
- 參考圖另有訊號分數、營收／法人數值、產業與新聞等欄位；目前 Advice DTO 未提供這些資料，因此卡片不顯示或推算。若之後要增加同等資訊密度，需先確認來源、日期與欄位語意，再擴充資料契約。
- 未升格策略仍是 Advice；此呈現不將其降為研究專用產品，也不代表自動下單。沒有新增欄位推定，也沒有改動來源、DTO、排序、策略、資料品質、Gate 或寫入行為。

## 驗證

- `tests/test_workbench_advice_contract.py`、`tests/test_ui_qt_workbench_view.py`、`tests/test_ui_qt_workbench_candidate_selection.py`：100 passed。包含正式 Advice 與未升格候選都走卡片、三欄／雙欄／單欄重排、展開卡獨佔一列、同筆操作歸屬及收合清除狀態。
- 必要 `tests/test_ui_qt_update_view_workbench.py`：97 passed。
- 必要 `scripts/qa_validate_update_tab.py`：25 passed、0 failed、4 skipped。預設 log 位置受 `output/` junction 權限限制，改以 `BALDR_UPDATE_TAB_QA_LOG_DIR` 將 QA 輸出導向本機任務證據目錄後重跑通過。
- `ui_qt/views/workbench_view.py`、`ui_qt/models/workbench_table_models.py` 與兩個修改的測試檔 `py_compile`：通過；兩個 UI/model 檔 targeted mypy：通過；`git diff --check`：通過。
- Repo-wide mypy 未通過：被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋。
- 原生 MainWindow 以 `ui_qt/main.py` 重新啟動並讀取本機 2026-10-27 資料：Advice 10 筆、未升格 Advice 0 筆、配置資料列 0 筆。約 1400×830 畫面顯示正式 Advice 卡片三欄排列、舊橫向 Advice 表格未顯示；展開 1526 日馳後，同筆完整判讀在卡片內展開並獨佔一列。這是原生視窗視覺核對，沒有保存截圖檔。
- Offscreen 以十筆合成 Advice 產出三欄收合（1054×1032）及展開（1054×1565）畫面，檢查逐列順序與展開卡獨佔一列；環境 fallback 字型未提供可讀中文字形，產圖只供檢視結構，不能作為中文字型或美觀驗收。畫面位於本機任務視覺化目錄：`C:\Users\archi\.codex\visualizations\2026\10\27\01a17c6b-8f6f-7b10-8a1e-9c996cc05997\workbench_advice_card_layout\grid_render\advice_cards_collapsed.png` 與 `advice_cards_expanded.png`。
- Python 驗證依序執行於受管 Windows Job，Job memory limit 為 8 GiB、process limit 為 12；最低啟動前可用記憶體約 18.3 GiB，各 QA 子程序自然結束，Job active process count 為 0，未依賴強制回收。
- Scoped document control 檢查 6 個文件來源／12 個 feature，回報 33 個既有問題（包括 Snapshot 舊錨點及 `output/` junction 存取拒絕）；本次 QA 文件與新增導覽連結沒有列為缺件。Feature Map JSON 解析及本輪 scoped `git diff --check` 通過。

## 限制

尚未在其他 DPI／縮放比例或 Owner UAT 驗收。原生視覺核對使用現有來源資料，該資料仍標記需複核／降級；卡片不改變正式資料資格，也不驗證投資用途或端到端響應時間。Offscreen fallback 字型不能代表一般中文字型顯示品質。
