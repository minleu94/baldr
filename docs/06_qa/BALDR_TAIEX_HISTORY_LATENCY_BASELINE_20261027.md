# TAIEX 歷史頁合成資料端到端延遲基線（2026-10-27）

## 目的與外部參考

[Danny Quant 每日選股預覽](https://www.dannyquant.com/signal-lottery-preview)分開呈現今日名單、套用篩選後名單和資料讀取狀態；本次檢視時頁面顯示「正在讀取資料池...」。這支持將載入狀態與載入後結果清楚區分的呈現方向，但該頁沒有與本測量相同的計時起點、資料量或畫面完成事件，因此不把兩邊的毫秒數作直接比較。

本次建立 Baldr「加權指數走勢」頁的合成資料延遲基線，檢視實際 `TaiexHistoryView`、`TaskWorker`、唯讀 SQLite reader 與圖表套用鏈。目的是找出後續可比較的本機基準；不是產品 Gate 或正式資料效能驗收。

## 量測範圍

- 使用真實 `TaiexHistoryView` 與受管 `TaskWorker`，在獨立 Qt `offscreen` 程序中顯示固定 1280×760 頁面。未建立 `MainWindow`，不含工作區導覽或主程式啟動時間。
- 臨時 SQLite 資料庫僅供此程序建立，符合 `market_indices` 的 `(指數名稱, 日期)` 主鍵與 `日期` 索引；以唯讀 URI、`query_only=ON` 執行 reader。
- 資料為 2014-01-01 至 2026-10-28 的合成週一至週五日期，不是官方交易日曆：123,802 列、37 個合成指數名稱、3,346 筆 TAIEX 歷史列、11,440,128 bytes。
- 排除建置資料庫、Qt 啟動和首次畫面初始化。5 次暖機後記錄 30 次刷新；每次均等待 worker 結束，並確認 UI 完成套用後收到第一個圖表 Paint。
- 計時使用同一程序的單調時鐘：請求開始、`TaskWorker.started`、reader 進出、GUI 套用 slot 進出、結果狀態正確後的首個 Paint。

## 結果

延遲為毫秒；p95 使用 30 個樣本的 nearest-rank 計算法。

| 階段 | p50 | p95 |
|---|---:|---:|
| 請求到 worker 開始 | 0.6918 | 0.7920 |
| SQLite reader | 3.0947 | 3.7839 |
| reader 返回到 GUI 套用 slot | 1.3588 | 1.6276 |
| GUI 套用 slot | 0.3029 | 0.4338 |
| 套用結束到圖表 Paint | 2.7517 | 2.9573 |
| **刷新請求到正確狀態的圖表 Paint** | **8.2659** | **8.6771** |

35 次讀取（含暖機）的 DTO SHA-256 完全相同：`2eb559820b9cfe4d9f3f2ce8651eb797fc9777d1bf1f180287808908bcaacbfb`；可見狀態 SHA-256 完全相同：`11e93375a99277c5923c3cd079dc178114175b4e22cd657885bcf9d67ddac44e`。每次狀態均為 `complete`，圖表顯示 120 筆；套用結果與 reader DTO 相同，且 UI slot 和 Paint 都在 GUI thread。

SQLite query plan 使用主鍵索引按 `指數名稱` 搜尋；日期選取另使用暫存 B-tree 分組，讀取 bars 也使用同一主鍵索引。此次合成負載未觀察到整表掃描，沒有證據支持本輪修改 SQL 或新增索引。

## 驗證與限制

- 受控 benchmark 程序：成功；Windows Job 讀回 8 GiB 記憶體上限、12 個程序上限與 kill-on-close；退出碼 0、Job 殘留程序 0、沒有強制清理。收據：`output/tasks/taiex-history-synthetic-latency-20261027/evidence/single_owned_qa_6042876b7374421396226fe52d4e72c1/receipt.json`。
- 機器可讀結果與逐樣本數列：`output/tasks/taiex-history-synthetic-latency-20261027/evidence/taiex_history_latency_result_20261027.json`。輸入 SQLite SHA-256：`3a2be00deed4325a2aabf50f5c2932f3dd10830c6cac367458d54018c6c7004e`；合成列內容 SHA-256：`db9e2f97750944fea6b9d373ea0af37b264f65c3cb77871d8f9fac1d43bd9ef8`。
- Changed-path document control：12 個功能、2 個連結來源、0 errors；收據：`output/tasks/taiex-history-synthetic-latency-20261027/evidence/single_owned_qa_caae50dbac124752918e4550f08b077c/receipt.json`。
- Task-wide document-control check：61 個 link sources 有 63 個既有問題，包括 Snapshot 四個舊錨點及舊文件指向 `output` junction 的連結；本次兩個 changed paths 的檢查仍為 0 errors。收據：`output/tasks/taiex-history-synthetic-latency-20261027/evidence/single_owned_qa_e3ae5e9b79fc4cab947e2d271abbee7d/receipt.json`。
- `git diff --check`：退出碼 0；本任務文件差異沒有 whitespace errors。
- 本輪沒有修改產品程式或測試，因此未執行通用 Workbench UI 回歸、Update validator 或 repo-wide mypy。此量測也未覆蓋正式資料、正常 `MainWindow` 導覽、真實螢幕繪製、其他硬體／DPI、併發負載或 Owner UAT。
- Offscreen Paint 只代表 Qt 排程至畫圖事件，不能代表顯示器完成呈現。合成資料與單一主機結果不能作為正式 SQLite 延遲承諾，也不能推論 Danny Quant 的回應速度。

## 結論

在本次合成負載下，TAIEX 頁從刷新呼叫到 Qt 圖表套用結果並進入 Paint 的 p95 為 8.6771 ms，DTO 與畫面狀態連續 35 次一致。此結果建立 page-level 比較基準；未發現值得在本輪引入的讀取或繪圖優化。正式資料延遲仍未測量。
