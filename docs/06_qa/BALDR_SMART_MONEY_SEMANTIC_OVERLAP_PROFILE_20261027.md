# Smart Money semantic overlap 效能與正確性 QA（2026-10-27）

## 結論與範圍

Smart Money dashboard 已載入的近期事件可供 60 個交易日 semantic batch 重用。實作只在 dashboard 快照與目前來源版本、指紋、資料日及交易日序列一致，且來源為無警示的 `observed` 時啟用；只查詢未覆蓋的日期。任何來源身份、日期身份、重複事件鍵或股票名稱有歧義時，回退原完整批次；股票名稱衝突僅完整重讀該股票。自訂 semantic port 沒有新方法或來源版本不穩時仍走原介面。

這是唯讀 query path 的內部效能優化。輸出摘要、資料來源、品質、日期界線及資格語意不變；未讀寫正式資料，也沒有宣稱正式資料庫或完整 UI 的效能收益。

## 合成 SQLite A/B

合成資料庫含 500 檔 × 60 個交易日 × 20 個分點，共 600,000 列；另以 100 檔作語意批次，dashboard 已載入最近 20 日的 200,000 列。每一路徑做 15 次交錯樣本；計時包含語意查詢、事件物化、60 筆收盤價查詢及摘要建構，不含 dashboard 共用來源載入。

| 指標 | 完整 60 日批次 | 重用 dashboard 重疊列 | 差異 |
|---|---:|---:|---:|
| 每次新增物化列 | 120,000 | 80,000 | −33.33% |
| dashboard 已載入且重用列 | 0 | 40,000 | 40,000 列避免重讀 |
| p50 | 1,030.566 ms | 773.506 ms | −24.94% |
| p95 | 1,134.926 ms | 886.021 ms | −21.93% |

完整與快路徑輸出 digest 相同，SHA-256 `924e7b02edb0fb6add93755fcaae20a336a18e57f6884cca31c0f4a166fcd2a8`。合成 A/B 原始摘要位於 `output/tasks/smart-money-semantic-overlap-profile-20261027/evidence/semantic_overlap_profile.json`；bounded Job 收據 SHA-256 `f5fcd1b93c0a0f4c87c5f9c50b3cfd5bdfcf1b83177b383e4f9057204d997406`。暫存資料庫在成功收尾時已刪除。這些數值只代表該合成資料與計時範圍，不能外推為正式 DB、完整頁面或使用者感知延遲。

此 A/B 在正式程式碼修改前執行；候選組是隔離的 benchmark 實作，用來衡量可行性，不是已上線 adapter 的效能實測。正式程式碼的 correctness 由下列 repository/service regression 驗證，正式 DB 與真實 UI timing 尚未量測。

Profile 中的 fallback oracle 亦確認：來源版本不符、dashboard 日期身份不符及股票名稱衝突都回到等價輸出。生產實作完成後，repository tests 另以合成 SQLite 驗證 dashboard overlap、舊批次、來源版本／日期不符及股票名稱衝突的完整輸出相等。

## 實作與驗證

- `BrokerFlowSQLiteReadRepository` 將原始 row-to-event 規則抽成共同轉換，讓完整查詢與快路徑使用同一套語意。快路徑核對來源版本／指紋、完整 60 日序列、dashboard 日期後綴、事件日期與唯一鍵；不符合時回到原完整查詢。
- `SQLiteSmartMoneyBatchSemanticAdapter` 新增可選 dashboard-aware builder；dashboard query service 僅在來源 cache key 讀取前後穩定時呼叫，其他 semantic port 照舊使用既有方法。
- `tests/test_broker_flow_dashboard_query_service.py` 與 `tests/test_broker_flow_sqlite_read_repository.py`：**42 passed**。
- 三個修改應用模組 targeted mypy：通過；5 個修改 Python 檔 `py_compile`：通過；`git diff --check`：通過。
- 必要的 repo mypy 命令 `mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` 因未變更檔案 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤退出 2，未能完成其餘來源檢查。獨立嘗試 `mypy .` 則在遞迴忽略的 `output/qa` 路徑時遇到 WinError 3，未當作 repo Gate 結果。
- 最終定向測試／mypy／compile／diff bounded Job 收據 SHA-256 `141be2695fc3db0ee575551c8bf8263d26d9283c6f2dc1cb31989c89d082d218`；正確 repo mypy 收據 SHA-256 `31d8d1d3cf9368f82da096808adaac611f2f0fd052f34aa58f1b0e53527e14f8`。兩個 Job 都自然結束、剩餘 PID 為 0、沒有強制清理；限制為 8 GiB 記憶體與 12 個程序。
- Scoped document-control 檢查 12 個 features／4 個更新連結來源為 0 errors，並通過 task route／coverage check；收據 SHA-256 `d9b5fa255f10f3643ffb9e97bb4c3f01fd92f86a33486d7fb0ff2bbaef2f2302`。Snapshot 單獨檢查仍回報 4 個既存的 Market Session QA 歷史錨點缺件；本次新增的 semantic overlap QA 連結有效，既有錨點未由本任務修改。
- 原生 GUI／Owner UAT、正式資料庫 timing 與完整 UI repaint timing 未執行。

文件中的合成數據不構成正式效能 SLA；正式 DB、來源品質、資料接受、Gate、PIT 與 ML 資格不變。
