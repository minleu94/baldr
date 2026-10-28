# 強勢個股狀態列資料日呈現 QA

## 範圍

強勢個股頁的成功狀態保留原筆數及掃描範圍，新增 `ScreeningResultDTO.effective_date` 顯示；各週期快取保存該日期，切回快取時顯示同一行情日。DTO 無日期或使用舊版服務回傳時，狀態明示「資料日未提供」。不從刷新時間、顯示列或其他來源推算日期。排名資料、篩選、Universe、來源品質與資格均不變。

`ScreeningService._freeze_frame()` 以實際來源資料框的「日期」欄解析有效日期，取該來源資料的最大日期；缺日期欄或沒有有效觀測時，DTO 的 `effective_date` 為 `None` 並保留原 missing/degraded 警示。這項 UI 顯示不代表資料新鮮度、PIT 或交易資格。

## 驗證

所有命令由本任務 root-owned Windows Job runner 執行，限制為 8 GiB Job memory、12 個程序，至少保留 8 GiB 可用記憶體；receipt 在 ignored 任務 evidence 目錄。

| 檢查 | 結果 |
|---|---|
| `pytest tests/test_ui_qt_weak_market_views.py -q -o addopts=` | 9 passed；驗有日期、missing date、週期快取續顯，以及舊服務無日期狀態 |
| 必要 Workbench UI `pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 97 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| 強勢股 view targeted mypy | passed，1 source file |
| 指定 repo-wide mypy | failed：未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤，中止其他檔檢查 |
| 修改 Python 檔 `py_compile` | passed，2 files |
| `git diff --check` | passed |

原始輸出、命令清單及 runner receipt：`output/tasks/strong-stocks-effective-date-20261027/evidence/`。repo-wide mypy 的既有語法錯誤需在獨立修復後重跑；本任務沒有修改該 bridge。

## 限制

本輪驗證的是 Qt view 合成服務測試與指定回歸，不是原生 GUI／Owner UAT，未讀正式行情資料，也沒有做頁面端到端延遲量測。這是一項來源日期可見性修正，不主張提升計算速度、資料新鮮度或推薦品質。

## 文件控制

本任務 changed-document scoped check 回報 4 個錯誤，均為本任務開始前已存在於 `PROJECT_SNAPSHOT.md` 的四個臨時休市 QA 錨點缺件；本輪新加的 Snapshot、QA 索引及手冊連結沒有缺件。Broad `document_control check --task` 回報 63 個 repository-wide errors，包含上述四個舊錨點及既有 ignored `output/` 越界連結；不把全域錯誤歸因於本次文件變更。
