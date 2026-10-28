# 可比產業超額圖卡清晰度 QA

日期：2026-10-28  
任務：`industry-strength-cards-20261028`  
範圍：市場總覽的「可比產業超額表現」改為自適應 3／2／1 欄小卡；每卡分列 5／20 日相對超額、方向及成分資料覆蓋率，卡片可展開當期報酬與來源詳情。未改 DTO、資料計算、排名、資料來源、資格、快照寫入或交易行為。

## 顯示語意

- 相對超額（bp）＝產業指數報酬－TAIEX 報酬；`+137 bp` 即領先 1.37 個百分點，負值代表落後。卡片以台股紅漲綠跌色搭配正負號與方向文字，不只依賴顏色。
- `覆蓋 9,803 bp` 改為「成分資料 98.03%」。分母是產業成分股，分子是該期間具備區間行情、可計算報酬的成分股數；它不是報酬，也不是市值覆蓋率。
- 每一期 hover 說明產業報酬、基準報酬、相對超額、可計算成分股數及資料日。點卡片標題在卡內展開兩期明細、品質、來源與映射身份；所選產業的同次來源代表股仍列在圖卡區下方。
- Unknown 保持缺值，不轉成 0；同群組內 5／20 日保留共同零軸與尺度。

## 驗證結果

| 檢查 | 結果 |
|---|---|
| `pytest tests/test_ui_qt_decision_desk_view.py tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 152 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped（避免實際合併而跳過） |
| 定向 mypy：`ui_qt/views/decision_desk_view.py` | 通過，1 source file |
| repo-wide mypy | 未通過；未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 出現語法錯誤，檢查提前停止 |
| 變更 Python 檔 `py_compile` | 通過 |
| Scoped `git diff --check` | 通過 |
| Scoped document-control：本次修改文件連結與 task record | 通過 |
| 預設 repository-wide document-control links | 未通過；檢查範圍外既有文件的 `output/tasks`／`output/trial` 連結被判越界，本次五份文件的 scoped 檢查通過 |
| Windows 主程式畫面 | 重新啟動 `ui_qt/main.py`，實際載入 2026-10-27 快照；看到 3 欄小卡、5／20 日紅綠方向與百分比覆蓋率，點卡展開後可讀資料日、快照／列品質、來源及映射資訊。該快照品質為降級，畫面仍依原值標示。 |

所有 Python 檢查均由受控 Windows Job 序列執行，使用 repo 原共用鎖、8 GiB Job memory 上限、12 個程序上限及啟動時至少 8 GiB 可用 RAM；每次 run 的 process receipt 顯示 owned Job 關閉且鎖範圍為同一 repo QA lock。原始輸出留在 ignored `output/qa`：

- pytest：`output/qa/industry_strength_cards_pytest_final/controlled_run_20261028_003722_2f4fda4c/`
- Update Tab validator：`output/qa/industry_strength_cards_update_tab_validator/controlled_run_20261028_003742_39dd16d6/`
- 全域 mypy：`output/qa/industry_strength_cards_mypy/controlled_run_20261028_003754_d87960bc/`
- 定向 mypy：`output/qa/industry_strength_cards_mypy_targeted/controlled_run_20261028_003819_9c9c4843/`
- py_compile：`output/qa/industry_strength_cards_pycompile/controlled_run_20261028_003812_6190be44/`

原生畫面只確認本機目前 UI 與載入快照；不代表固定舊 EXE、正式資料 Gate 或 Owner UAT 已驗收。Offscreen／型別／編譯結果也不外推為全庫 mypy 通過。

## 文件 Coverage

| 範圍 | 狀態 | 理由／入口 |
|---|---|---|
| UI 實作與回歸測試 | updated | 卡片排列、切換欄數、方向／覆蓋率語意、hover、展開與代表股回歸均有對應測試。 |
| 操作手冊與領域說明 | updated | `APPLICATION_MANUAL.md`、`manuals/DATA_AND_MARKET_RESEARCH.md` 已說明讀法、欄位意義與操作。 |
| UI 功能文件與 QA 索引 | updated | 列出本輪呈現變更並連到此 QA 收據。 |
| DTO、資料流與架構文件 | not_required | 未改資料契約、Service、計算公式或來源流程。 |
| Roadmap、PROJECT_SNAPSHOT、產品 Gate | not_required | 未改產品能力 Gate、資格或接受狀態。 |
