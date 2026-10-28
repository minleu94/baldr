# Smart Money 範圍切換來源快取 QA（2026-10-27）

## 範圍與行為

Smart Money dashboard 查詢依資料主檔與 WAL 檔案身分、明確資料日及期間保留一份 process-local 來源快照。Top 50、Bottom 50、All 切換時可重用同一份來源事件，仍各自重算市場聚合、清單排序、摘要及語意批次。來源主檔／WAL 變更、WAL 身分不可讀、rollback journal 存在或來源版本在讀取前後不同時，不使用該快取。傳給 dashboard 的事件 DTO 會複製，避免 mutable snapshot 被修改後影響下一次範圍計算。取得來源版本後，dashboard 輸出快取會先淘汰其他版本的結果，避免版本 churn 時保留已無法命中的大型舊 snapshot；同版本的 scope 輸出與來源快取鍵照常使用。

這是唯讀 query service 的效能變更，不改正式資料、資料品質、來源接受、PIT、Gate 或 ML 資格。

## 合成 SQLite A/B

測試資料庫由本次工具建立於 OS temporary directory，含 697 檔合成股票、10 個分點、20 日、共 139,400 列；未讀寫正式資料庫。每個測量先載入預設 Top／Bottom 50，再對目標範圍做一次 warm-up，接著量 20 次相同範圍。每次測量後清除精確 dashboard 結果快取以量到 source-cache 路徑；有快取組仍保留來源快照。計時涵蓋 query service 的來源取得、事件轉換、聚合、訊號排序、輸出 DTO 隔離及摘要，不含 Qt worker 排程、widget 更新與繪製。

| 範圍 | 無來源快取 p50 / p95 | 有來源快取 p50 / p95 | p50 降幅 | 每組來源讀取次數 |
|---|---:|---:|---:|---:|
| Top 50 | 1,074.128 / 1,102.875 ms | 111.060 / 151.350 ms | 89.7% | 22 → 1 |
| Bottom 50 | 1,074.872 / 1,141.421 ms | 110.377 / 163.104 ms | 89.7% | 22 → 1 |
| All | 1,041.596 / 1,420.047 ms | 703.373 / 822.457 ms | 32.5% | 22 → 1 |

來源讀取次數包含預設載入、目標範圍 warm-up 及 20 次測量。有／無快取的輸出 digest 相同；digest 核對資料日、品質、警告、source fingerprint、摘要、訊號欄位及輸出事件欄位。完整原始樣本在 `output/tasks/broker-flow-scope-cache-20261027/evidence/benchmark_scope_cache.json`，root-owned Job 收據位於同目錄 `single_owned_qa_51de9f954bd74c669bbafb5605765395/receipt.json`，wrapper SHA-256 為 `1e4cc300750b075351b0b3be90538deffd2fa4f8ae11cbdb8159da23f15273ff`。

數值只代表合成資料上的 service-level 範圍切換，不能當作實際資料庫、完整 Main 視窗或使用者感知延遲的保證。All 範圍仍需複製並呈現完整事件 DTO，因此改善幅度低於 Top／Bottom。

## 來源版本 churn 記憶體 A/B

另以同一份 139,400 列、15,835,136-byte 合成 SQLite，讓 All 查詢連續遇到 9 個不同來源版本。比較修改前 attempt03 與淘汰舊版本輸出後的 attempt04；兩次的來源讀取均為 9 次，輸入資料庫 hash 相同，語意輸出 digest parity 為 true。固定後的 9 次查詢只保留 1 份 dashboard output snapshot；修改前保留 8 份、直到第 9 次才由容量上限逐出最舊項目。

| 有來源快取 | 修正前峰值 RSS | 修正後峰值 RSS | 修正前 tracemalloc 峰值 | 修正後 tracemalloc 峰值 |
|---|---:|---:|---:|---:|
| 關閉 | 1,902.6 MB | 422.7 MB | 654.1 MB | 134.1 MB |
| 開啟 | 1,911.6 MB | 596.9 MB | 688.7 MB | 197.6 MB |

有來源快取的版本 churn 對照中，峰值 RSS 下降 68.8%，tracemalloc 峰值下降 71.3%。修正後，有來源快取組的峰值 RSS 仍比停用組高 174.2 MB；兩組 source reads 都是 9 次，所以這個案例量的是舊 dashboard output snapshot 的版本 churn，不是來源快取重用收益。這是合成 SQLite、獨立 child process 與 9 個全量 All 輸出的壓力情境；它說明版本切換時不再累積舊輸出 snapshot，不能推論正式資料庫、一般 UI 操作的記憶體或延遲。原始 before／after 報告為 `output/tasks/broker-flow-scope-cache-20261027/evidence/benchmark_scope_cache_memory_attempt03.json` 與 `.../benchmark_scope_cache_memory_attempt04.json`；修正後 root-owned Job 收據為 `output/tasks/broker-flow-scope-cache-20261027/evidence/single_owned_qa_7e4303bb4a70438d896039efdd75ae98/receipt.json`（SHA-256 `aa0a768b9da58b564962784c42f52e9cfbf66166fdd5939ddcfdaec470e31db6`）。

## 正確性與回歸

- `tests/test_broker_flow_dashboard_query_service.py`、`tests/test_broker_flow_sqlite_read_repository.py`、`tests/test_ui_qt_smart_money_flow_async.py`、`tests/test_ui_qt_smart_money_flow_view.py`：加入跨來源版本輸出快取淘汰測試後，68 passed。root-owned Job 收據 `output/tasks/broker-flow-scope-cache-20261027/evidence/single_owned_qa_de8afa537cc34543981fb580d122ebb3/receipt.json`。
- `source_cache_key` 測試確認 WAL 尚未 checkpoint 的提交會改變快取鍵，即使 DB 主檔 size／mtime 不變；rollback journal 存在時回傳不可快取狀態。
- Service 測試確認切換 scope 與 limit 不重讀來源、品質／warning／摘要與選取資料保持一致、變更來源版本會失效，以及回傳事件被改動後不會污染快取來源；讀取前後版本不一致時不保留快取。
- 加入版本淘汰程式與回歸後，`mypy` 對兩個應用模組 targeted 檢查和修改 Python 檔 `py_compile` 均通過；收據 `single_owned_qa_de8afa537cc34543981fb580d122ebb3/receipt.json` SHA-256 `fcb9c0ff6053c2cc452d26976f63b5735d23cfd3436406c173be27a06df1e816`。全 repo `mypy` 仍被未變更 `data_module/mops_t164_pdf_disposition_bridge.py:411` 的既有語法錯誤阻斷。
- 最後一次更新文件及 task record 的 scoped document check 結果記在 `output/tasks/broker-flow-scope-cache-20261027/evidence/cache_pruning_document_check_results.json`：12 features／4 changed-document link sources／0 errors，`git diff --check` 通過。Snapshot 新 QA 連結有效，但單獨檢查仍報 4 個既有、與本次無關的缺錨點；全 repository check 另報既有 `output/` 越界連結。

未執行原生 GUI／Owner UAT、真實大型 DB timing 或正式工作程序記憶體量測；這些仍是後續 UX 驗收的限制。手冊操作步驟與結果判讀沒有改變。
