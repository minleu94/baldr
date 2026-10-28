# Research Registry 背景載入與本機篩選 QA（2026-10-27）

## 變更範圍

Research Lab 的 Registry 比較頁首次顯示及手動重新整理改用 `TaskWorker` 呼叫原 `ResearchRunService.list_runs()`。類型、策略及標籤變更只在已載入 metadata 快照上重新篩選與呈現，不重複查詢 Registry。狀態列區分尚未載入、載入中、刷新中、已載入與錯誤，顯示總列數和目前符合篩選的數目；刷新時保留上一份有效快照，錯誤詳情放在狀態提示中。

Request ID 拒收被新刷新或關閉流程淘汰的回覆；BacktestView 的正常首次進入及保存／刪除後刷新改呼叫非同步入口，並在工作區合作式關閉時收尾清單 worker。同步 `refresh_runs()` 仍保留供既有測試和程式呼叫相容。Repository 的有效性過濾、原有比較流程、資料保存及績效資格沒有改變。

## 驗證結果

| 檢查 | 結果 |
|---|---|
| `tests/test_ui_qt_run_registry_compare.py tests/test_ui_qt_research_workflow.py -q -o addopts=` | 53 passed（16.65 秒） |
| 必要 UI 回歸 `tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 97 passed（3.04 秒） |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| 兩個變更 UI 模組 targeted mypy | 通過 |
| 修改的 4 個 Python 檔 `py_compile` | 通過 |
| `git diff --check` | 通過 |
| `FEATURE_DOCUMENT_MAP.json` JSON parse | 通過 |
| 指定 repo-wide mypy | 未通過；在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 報既有語法錯誤，mypy 因而停止後續檢查 |
| Scoped `document_control check` | 未通過；回報 PROJECT_SNAPSHOT 四個既有日期化錨點缺件，以及 decision/research 分冊一個既有連至 ignored `output/` 的越界連結；本輪新增文件連結未列缺件 |

聚焦測試涵蓋首次載入在非 GUI 執行緒、載入中狀態、篩選時不再讀取 service、刷新錯誤保留既有清單、新刷新拒絕舊回覆，以及關閉期間拒絕晚到結果。第一次聚焦執行曾有一個既有基本策略 worker 等待測試超過 10 秒；同一測試檔重跑後通過，沒有為該既有測試改動程式。

受控 QA runner 的原始命令輸出與 Job 收據保存在 `output/tasks/research-registry-async-load-20261027/evidence/`。此次檢查不包含原生 GUI／Owner UAT，也沒有量測正式 Registry 資料的端到端延遲；測試證明讀取移至背景執行緒，不代表正式資料庫讀取時間已改善。Danny Quant（[網站](https://www.dannyquant.com)）僅是使用者指定的 UI 參考，本輪沒有進行可比的站點效能基準。

## 目前限制

- 刷新錯誤狀態保留舊快照；若尚無成功快照則顯示載入失敗與重試指引。
- 本機篩選只作用於當前成功載入的有效 runs；要取得最新 Registry 狀態需按「重新整理」。
- Repo-wide mypy 尚受上述未修改的 T164 語法錯誤阻擋；不能將其記為通過。
- Scoped document control 的五項既有文件連結問題仍待其 owner 修復；本輪新增入口與手冊錨點沒有新增錯誤。
- 沒有執行正式資料讀取、原生 UI 手動走查或 Owner 驗收。
