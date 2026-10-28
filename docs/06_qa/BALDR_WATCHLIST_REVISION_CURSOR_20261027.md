# Watchlist v3 inventory revision cursor QA（2026-10-27）

## 變更範圍

`data_module/watchlist_item_storage.py::inventory()` 仍執行同一條 `SELECT ... ORDER BY watchlist_id,revision`，逐筆驗證每一條 revision、event ref、header、delta、chain 及 current projection。本輪只移除 revision rows 的 `.fetchall()`；SQL、排序、驗證次序與輸出建構維持不變。這不會略過非目標 watchlist 的損壞記錄，也不更改資料寫入、schema、來源或資格。

新增回歸驗收兩個 watchlist、多個 revision 的 revision／event 順序，並確認另一 watchlist 的 object hash 損壞仍會讓 `get_current("default")` 以 `object_hash_mismatch` 拒絕。既有測試之外，以 HEAD 原始 `fetchall()` 實作與工作樹 cursor 實作在同一個合成 DB 比較結果 digest 及晚期壞 revision header 的拒絕碼。

## 合成 inventory 基準

`output/tasks/watchlist-revision-cursor-20261027/evidence/benchmark_revision_inventory.py` 使用 repository API 在 OS temp 建立 1,800 筆 revision；inventory 共 3,607／4,096 rows，且完整驗證通過。各組暖身 3 次，交錯計時 40 次；peak memory 各量 5 次，使用 tracemalloc。HEAD 與現行輸出 SHA-256 相同：`ee4a45c9db2edfd83fb93ef76dbb24eddc0ba3199531655ca288b7ffaaefd6a4`。

| 指標 | HEAD `.fetchall()` | Cursor | 差異 |
|---|---:|---:|---:|
| Inventory p50 | 84.66845 ms | 84.26990 ms | −0.47%（不足以宣稱實際速度提升） |
| Inventory p95 | 123.8257 ms | 120.0263 ms | −3.07%（合成 microbenchmark） |
| tracemalloc peak p50 | 11,656,474 bytes | 10,317,919 bytes | −1,338,555 bytes（約 −11.5%） |

晚期將最後一個 revision header 改為無效 canonical JSON，兩個版本皆拒絕，錯誤碼都是 `revision_header_mismatch`。記憶體改善可重現；延遲變化很小，不能外推至正式 DB、低 revision 數或 UI 端到端回應。

## 驗證與限制

| 項目 | 狀態 | 結果／證據 |
|---|---|---|
| Storage focused tests | passed | 27 passed；`output/tasks/watchlist-revision-cursor-20261027/evidence/focused_watchlist_storage_tests.log` |
| Inventory A/B benchmark | passed | digest、row order、late corruption error code 相同；tracemalloc peak 降 1.34 MB；`output/tasks/watchlist-revision-cursor-20261027/evidence/revision_inventory_benchmark.log` |
| Targeted mypy | passed | `data_module/watchlist_item_storage.py`，0 issues；`output/tasks/watchlist-revision-cursor-20261027/evidence/changed_file_targeted_mypy.log` |
| Python compile | passed | 兩個變更 Python 檔通過；`output/tasks/watchlist-revision-cursor-20261027/evidence/changed_python_compile.log` |
| Diff whitespace check | passed | scoped diff check 通過；`output/tasks/watchlist-revision-cursor-20261027/evidence/diff_check.log` |
| Repo-wide mypy | failed | 未修改 `data_module/mops_t164_pdf_disposition_bridge.py:411` syntax error，mypy 因此停止 further checking；`output/tasks/watchlist-revision-cursor-20261027/evidence/repository_mypy.log` |
| Document control | failed | 63 個既有錯誤、60 個來源：4 個 PROJECT_SNAPSHOT 舊錨點及 59 個 ignored `output/` 引用；本輪新增連結未列缺件；`output/tasks/watchlist-revision-cursor-20261027/evidence/document_control_check.log` |
| 正式 DB／自然使用者端到端延遲 | not_run | 只使用暫存合成資料；未接觸正式資料或執行 UI |

第一次 benchmark 數值已產生，但測試程式因 SQLite 連線未明確 close 而在 temp cleanup 失敗。補上所有測試連線明確 close 後重新完整執行，表中的 40 次結果對應 exit 0、無殘留 Job process 的收據。這是暫存測試工具的修正，產品程式與正式資料未受影響。

全域 mypy 與 document_control 的失敗均未由本輪改動引入：前者在未變更 T164 bridge 停止；後者的 63 個問題都來自原有 Snapshot 日期錨點與 ignored `output/` 文件引用。此次新增的 Snapshot／QA 索引連結未出現在錯誤清單中。
