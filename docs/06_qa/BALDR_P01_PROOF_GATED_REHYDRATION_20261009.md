# P01 已簽發來源的私有 DTO 重建回歸

本記錄涵蓋 P01 exact read session 內的私有 DTO 重建切片。它只省略同一已簽發 semantic proof 所涵蓋 bytes 的重複語義重建，不改來源、特徵、決策時間或查詢結果，也不是 1,000 檔效能通過證據。

## 實作邊界

快速路徑只接受 repository 簽發的 semantic proof、精確 P01 session 與該 session 最終發出的 artifact reference。能力核對 exact 類別、proof 登錄、弱參照 session/reference 身分、owner token、read-session identity、reference pins 與 session reference tuple；`dataclasses.replace` 的 session/reference、同名假 session、外部 session、換 root 或來源 binding 不符都不能借用資格。測試證明 capability 不會延長 session 生命週期，也拒絕替換 reference；reference 本身回收後的獨立負例未在本輪測試。

每次實際頁面讀取仍重新核驗 manifest、完整 artifact 清冊、所需來源檔 bytes 與 SHA、路徑/layout 及 row/source identity，並保留取消檢查。只有通過同一 proof 與 fresh bytes 驗證後，repository 才以私有 decoder 重建 immutable DTO；不保存 snapshot、原始 batch 或跨操作快取。一般 `from_json` 與公開 `read_selected_exact` 仍走 strict validator，普通呼叫端不能要求跳過語義驗證。

ContextVar 只在同步讀取期間攜帶一次性 P01 context。helper 先把 context 捕獲為區域值，再於外部 callback 執行期間清空 ambient context，並在 `finally` 還原呼叫者原值。dataclass clone 在已授權讀取的 callback 中重入時會走 strict `from_json`；另一個真實 reader session 重入時則以自己的能力讀取。取消、例外與成功返回都恢復外層 ContextVar，不會把外層 capability 借給 nested read。

Look-ahead 自查：此切片只從已驗證的原 snapshot bytes 還原相同欄位，不計算新特徵、不變更 cutoff、source clock、availability、PIT 狀態、規則、Decimal 值、排序或分頁。

## 驗收證據

固定候選回歸於全新隔離 pytest 暫存目錄執行，完整命令為：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m pytest `
  tests\test_daily_market_technical_snapshot_v4_semantic_rehydration.py `
  tests\test_daily_market_technical_universe_v4_session_metadata.py `
  tests\test_daily_market_technical_universe_v4_read_session.py::test_session_full_index_matches_strict_filter_sort_and_global_paging `
  tests\test_daily_market_technical_universe_v4_read_session.py::test_all_supported_sort_keys_preserve_decimal_and_stable_null_ordering `
  tests\test_daily_market_technical_universe_v4_read_session.py::test_reader_issued_selection_distinguishes_unrestricted_and_explicit_empty `
  tests\test_daily_market_technical_universe_v4_read_session.py::test_selection_cancel_during_materialization_returns_no_partial_page `
  tests\test_daily_market_technical_universe_v4_read_session.py::test_read_session_source_counts_is_frozen_and_does_not_rescan `
  tests\test_daily_market_technical_universe_v4_read_session.py::test_session_rejects_source_mismatch_overflow_and_cancel_inside_parent_read `
  -q -o addopts= -p no:cacheprovider --basetemp C:\t\p01_rehydration_final_d
```

結果為 **37 passed in 56.96s，exit 0**。原始輸出保存在 `output/qa/p01_proof_rehydration_20261009_d/final_owned_plus_session_metadata_and_read_session_regressions.log`。另一次 nested scope 定向回歸為 **2 passed in 7.98s，exit 0**，輸出保存在 `output/qa/p01_proof_rehydration_20261009_c/nested_scope_targeted.log`。

回歸包含 fast/strict DTO 與 selection identity 等值、AND/OR 結果與排序頁面等值、同頁 artifact 路徑逐一對應及 fresh-read 次數、已選/未選 artifact bytes 被改後即使恢復 mtime 仍拒絕、session/reference clone 與 foreign scope 拒絕、capability 不延長 session 生命週期、strict JSON 自洽重雜湊的無效 PIT 欄位拒絕、nested clone strict fallback、另一 session 的獨立 scope，以及取消/例外後無部分頁並還原 context。普通 parser 的 strict 測試與既有 session metadata/read-session 選定回歸一併通過。

`py_compile` exit 0；scoped mypy 對 repository、feature snapshot、query 三個來源檔回報 `Success: no issues found in 3 source files`。Root 的唯讀 scope probe 另觀察到 strict branch `observed_none=true`、`inherited_outer=false`，且外層 context 與 helper 狀態均已還原；該 probe 只驗 ContextVar 窄修正，不代替上述完整 pytest。

來源四檔在最終回歸前與回歸後的 SHA 相同；機械比對收據為 `output/qa/p01_proof_rehydration_20261009_d/root_review_validation_receipt.json`（SHA-256 `de16468da34154c9f62d4133b7a26d9659e0a6490d5361a28bb99cc9368c75a5`）。收據保存實際 executable、working directory、完整 argv、before/after pins 與原始 log SHA。原始 `py_compile` 與 scoped mypy 輸出分別保存在同目錄 `py_compile_final.log`、`mypy_final.log`；最終 pytest 原始輸出與 nested 定向輸出路徑如上。

## 未涵蓋範圍

本切片沒有重跑固定 1,000 檔五冷一暖矩陣，沒有量測新的 p95，也沒有把既有超過 300 ms 的結果改列通過。它尚待 Root 審查與新的受控效能矩陣驗證；此處測試證明的是 DTO/identity 等價、資格邊界與 fresh-source tamper 拒絕，不代表效能門檻達成。

## 檔案 SHA-256

- `app_module/daily_market_technical_snapshot_v4_repository.py`：`1bbfb41a41283fcfefea861248ccf9158e9f1484bf691b9a77d1cb4552b41ec7`
- `app_module/daily_market_technical_feature_snapshot_v4.py`：`844bce406a0e477c8dfd29c1f51e9831dac01b0db3a6e5f6405681b6b8121cd5`
- `app_module/daily_market_technical_universe_v4_query.py`：`341b9d9de98b1fa760023de0021bf547e0181a90e066900add0dffb10d1d7b1b`
- `tests/test_daily_market_technical_snapshot_v4_semantic_rehydration.py`：`30871d1fcd121988e29a6656c81095f78a010ab82e90e55aac4b443ec0286d29`

## 更新記錄

- 2026-10-09：新增 P01 proof-gated 私有 DTO 重建與 ContextVar nested read 回歸結果，明確保留效能門檻未驗收狀態。

## 後續固定效能矩陣

後續 QA 接續記錄此 proof-gated 來源已完成固定 1,000 檔、五 cold／一 warm、每類 30 樣本矩陣：page flip p95 `220.0639 ms`、global sort p95 `248.2336 ms` 通過嚴格 `< 300 ms`；filter p95 `677.9689 ms` 未通過。首次冷啟動至 page 0 的 p95 為 `21.1921328 秒`，是不同計時項目，不代表原 2382 Main 操作延遲已改善。完整時點與範圍見[補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md)。本矩陣不把本文件的定向回歸改寫成效能通過；篩選失敗仍未解除。
