# 強勢個股目前清單本機搜尋 QA

## 範圍與依據

強勢個股原全市場頁新增股票代號／名稱部分文字搜尋；共用研究快照投影目前只有股票代號欄，搜尋框會在該模式提示只支援代號。搜尋只隱藏目前模型中不符合的列，保留來源 DataFrame、表格排序和選取索引；不重新查詢、不擴大 `Universe`，也不改變共享研究快照的查詢條件。計數標籤另列符合數與目前清單總數，區分尚未載入、成功空清單及有列但零符合。

Danny Quant 參考頁：[Signal Lottery Preview](https://www.dannyquant.com/signal-lottery-preview)，觀察日期 2026-10-27。頁面將完整當日清單、今日清單、篩選後清單與資料完整度數量分開呈現，並說明篩選後剩餘筆數；當次公開快照仍顯示「正在讀取資料池…」，所以未把當時的 `0` 當成成功空結果。Baldr 此切片沿用「清單範圍與符合數分開、載入與空結果分開」的資訊提示方式。

## 驗證

各 Python 驗證由 root 以 8 GiB Job memory 上限、12 個程序上限與 kill-on-close 執行；每份收據讀回限制，結束時 Job 程序數為零，沒有強制清除程序。

| 檢查 | 結果 | 收據 |
|---|---|---|
| 強弱勢 UI 與共享市場研究消費者 | 18 passed | `output/tasks/strong-stocks-local-filter-20261027/evidence/single_owned_qa_193bc60caeb0420bb34c13a030514fcd/receipt.json` |
| 必要 Workbench UI regression | 97 passed | `output/tasks/strong-stocks-local-filter-20261027/evidence/single_owned_qa_fc4357f412f14ba3a03bd4bb1ad66a5c/receipt.json` |
| Update tab validator | 25 passed／0 failed／4 skipped | `output/tasks/strong-stocks-local-filter-20261027/evidence/single_owned_qa_90690b6e07474c669af24b90a6e48701/receipt.json` |
| StrongStocks targeted mypy | 通過，1 source file | `output/tasks/strong-stocks-local-filter-20261027/evidence/single_owned_qa_5adaf27e95104ea7be57346363864772/receipt.json` |
| 修改 Python 檔 `py_compile` | 通過，2 檔 | `output/tasks/strong-stocks-local-filter-20261027/evidence/single_owned_qa_45de475943aa41f6ba475887ca0c6672/receipt.json` |
| repo-wide mypy | 未通過：未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 有語法錯誤；阻止後續檔案檢查 | `output/tasks/strong-stocks-local-filter-20261027/evidence/single_owned_qa_7beffd665d6e4466bbcdcaea44cb9abf/receipt.json` |
| changed-path document control | 有 4 個既有 Snapshot 錨點缺件；本輪新增連結沒有列入錯誤 | `output/tasks/strong-stocks-local-filter-20261027/evidence/single_owned_qa_dba0a5d566bf4403bcb4ed4a31f3d125/receipt.json` |
| `git diff --check` | 通過；沒有 whitespace error | `output/tasks/strong-stocks-local-filter-20261027/evidence/git_diff_check.log` |

## 行為回歸

`tests/test_ui_qt_weak_market_views.py` 與 `tests/test_shared_market_research_consumers.py` 共 18 項通過。新增案例驗證原全市場模式的代號／名稱部分比對、符合數及零符合提示、搜尋清除還原列、排序後可見列仍對應原代號、搜尋隱藏所選列時清除選取，以及成功空清單與未載入的區別。共用快照案例用沒有名稱欄的投影，確認模式提示、代號搜尋、原來源摘要與 query 不變，且搜尋不觸發新的共用研究請求。

## 文件與差異檢查

`document_control check --task ... --path` 對本輪七份文件檢查結構與連結，列出 `PROJECT_SNAPSHOT.md` 內四個既有日期化 QA 錨點缺件；沒有列出本輪新增的 QA／手冊連結錯誤。未改動那些既有錨點的範圍外文件。預設 task-wide 檢查另列出既有連向 ignored `output/` 的文件連結。`git diff --check` 通過；Git 只提示數個已 dirty 檔案的 LF／CRLF 工作樹轉換警告。

## 限制

本次未走查原生 MainWindow，也沒有 Owner UAT、正式資料搜尋量測或端到端 p50／p95 延遲數字。回歸只驗證目前表格模型的本機列篩選，不代表來源完整度、全市場搜尋、策略資格或任何產品 Gate 通過。搜尋列只描述目前載入的清單；`Universe` 仍獨立表示來源掃描範圍。
