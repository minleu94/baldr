# 階段1限定效能修正驗證（2026-10-05）

本包基於 `00bb43ea186272b4589e86fd6f56bbfd6234f6f9`，沿用唯一原計畫 `output/plans/baldr_product_experience_plan_20261004.md`，完成啟動與盤勢價格批次的限定改善。兩位代理按使用者指定以工具參數 `gpt-6-luna/max` 執行，root 統一整合、量測與提交；工具接受參數不等於後端型號／effort 的獨立自省證明。未新增代理、方法或 UX18 Gate。這是階段1的一個工程切片，不是完整 UX17／全產品階段1驗收。

## 產品改變與安全邊界

- `data_module/industry_mapper_data_provider.py`：hash／日期範圍各自於單次呼叫內 memoize 重複日期解析。沒有跨來源 persistent cache；完整列序、canonical JSON、日期 fallback、hash 與來源觀測契約保留。
- `ui_qt/views/backtest/result_panel.py`、`backtest_view.py`：四張回測圖及兩張推薦組合圖延至首次結果頁使用建立。待繪參數深複製為資料快照，最新結果取代未顯示的舊結果；重訪保留 widget。單圖繪製失敗顯示提示、保留 payload 供下次進頁重試，其他圖繼續顯示。未宣稱延後全部 QtWebEngine import。
- `app_module/decision_market_frame.py`：同輪盤勢 frame 的近期價格一次按股票分組，避免逐股重複大表篩選／排序。最多兩個來源 path/stat、決策日及 window 鍵；reset 清空，date／來源／window 改變失效，回傳副本。stat 是快取鍵，不是 custody hash；不承諾偵測同輪 WAL-only 寫入，也不延伸成跨輪快取。
- `smart_money_semantic_service.py`、`decision_desk_service.py`、`ui_qt/views/decision_desk_view.py`：相容既有 provider 的可選取消 callback，在 Smart Money SQL progress handler、股票批次及盤勢區段間合作檢查。只有 SQL progress handler 已確認中止，才將資料庫例外轉為取消；真正資料庫故障不被取消狀態遮蔽。取消例外不作一般缺資料降級，視窗等 native worker 完成才關閉。

Look-ahead 自查：SQL 仍限制決策日可用日期，共用市場交易日 window、股票日期排序與價格截取契約保留；沒有新增策略、績效、特徵標準化或 benchmark 算式。價格與核心計算仍使用 Decimal／既有整數契約；本收據的時間／RSS／改善百分比是隔離診斷邊界。未修改 `ui_qt/main.py`、QA profiler、資料庫 schema 或正式資料／模型／registry。

取消粒度仍有限：Market Breadth／Relative Strength 進行中的 SQL 尚未接收 callback，僅在區段前後檢查，不能宣稱每一查詢都立即取消。既有全視窗 shutdown coordinator 維持，未用強制終止或假完成訊號。

## 同條件五跑 before／after

Before 見[階段0收據](PRODUCT_STAGE01_PERFORMANCE_BASELINE_20261005.md)。After 使用同一唯讀 QA snapshot、實際 reader、原輸出 seed、Windows Native platform、五個全新程序；第一跑載入強勢股並執行30次不同列點選，另外四跑只啟動。量測期間未跑其他 tests／代理實作，未操控使用者既有視窗；OS page cache 與其他使用者背景活動未強制清除或控制。

固定 CLI：`.venv/Scripts/python.exe scripts/qa_profile_startup.py --platform windows --runs 5 --loaded-selections 30 --label stage1_after_20261005_native`。提交版 profiler SHA256 `0a8a3ef5d8808c7bbc8151948fc5f8a6d98f731f3a367ef261e76ed9257f1003` 未改。Before 測量版 SHA／末尾 Unicode print exit1 的歷史限制保留於前收據；與目前版差異僅父程序 UTF8 print 及 process-total CPU 欄名，不變更 child 測量。

| 指標 | Before | After | 中位數改善 |
| --- | ---: | ---: | ---: |
| 首屏可操作，父時鐘，5跑 median | 10.148s | 8.642s（8.540–9.145） | 14.84% |
| Workbench 首次資料，child 時鐘，5跑 median | 10.126s | 8.504s（8.450–9.043） | 16.02% |
| MainWindow construct＋show，5跑 median | 6562.32ms | 5018.89ms（4935.91–5255.30） | 23.52% |
| IndustryMapper，5跑 median | 3206.33ms | 1841.59ms（1757.57–1912.58） | 42.56% |
| BacktestView，5跑 median | 1097.90ms | 893.45ms（884.30–938.70） | 18.62% |
| 30列高亮 p95 nearest-rank | 116.60ms | 49.65ms（max 91.67） | 單次場景，非全互動 SLA |

父／child 時鐘起點不同，不相減。修改前 `STAGE1_INTAKE_AND_ROLLBACK.md` 凍結的是 IndustryMapper 與 BacktestView 兩段各自至少20%：IndustryMapper 42.56%通過；BacktestView 18.62%未達，差1.38個百分點，不能用前者通過代表兩者全過。首屏與同情境 RSS 沒有超過10%回退；30列高亮低於既定300ms預期。父層接受本包改善並要求不為湊百分比再微調Backtest；門檻原值及未達結果保留，因此本包門檻為部分通過，不是全產品成熟度 Gate。

四筆只啟動的20ms取樣 Python process-tree peak RSS：before 699,899,904–701,960,192 bytes；after 572,538,880–577,310,720 bytes。只啟動 process read bytes 各為 before 212,315,094／after 212,287,584，整個程序 CPU before 10.3125–10.96875s／after 8.59375–9.28125s。read bytes 是 OS process counter，不是實體磁碟讀取或 cache-cold 數字；CPU 包含啟動、事件迴圈與關閉。

Loaded30＋close 場景 before elapsed 90.482s／CPU60.9375s／peakRSS1,569,636,352／read4,513,139,049；after elapsed13.349s／CPU16.90625s／peakRSS674,918,400／read1,038,603,001，關閉後 registered worker=0。Before 達90秒合作關閉上限，After 沒有78秒自檢／90秒超限；不同完成／取消工作量不能用其 CPU／read 差異宣稱完整盤勢計算等比例加速。正常完成另見下一節。

五個 child 與父 CLI exit0、failure=null；所有 QA launcher 與實際 Python PID 均已退出（Windows venv 的兩者不同，已檢查全部10個）。每跑與最終輸入完整性通過。主 DB 3,976,314,880 bytes 與 candidate 613,691,392 bytes 用 stat pins，沒有宣稱完整大 DB hash；WAL／SHM／小型輸出／receipt 有 hash。只有 SHM 的 content hash、size、device、inode 全同時可接受 mtime-only 變動。Before／After preflight 除此 sidecar mtime 外全部相同，未複製大 DB。

來源契約：Industry 212,500 rows、2014-01-02–2026-10-02、`sqlite.industry_indices`，完整 rowset hash 每跑皆為 `sha256:ff055b018b425fab26ec633babf449c5fbc1ac91a98c22efe1cbdae1f7a03a08`。來源 status 仍 unknown；每次 observed_at／envelope hash 可正常改變，不宣稱不同觀測同 envelope hash。強勢股實際 reader 62,728 rows、20260818–20261002、day／volume lookback20，top50／掃描1978與30個 distinct ids 與 Before 相同，非全正式母體覆蓋。

## 首次使用與 focused QA

額外 Native 探針共約29.988s，背景盤勢正常產生真實 snapshot，選取後等待18.170s、worker 已結束，無 `smart_money_dashboard_error`。隨後首次開啟 Backtest 圖表，四個 `Fast*Widget` 實際建立且可見，切離再返回沿用同組 widget。首次開頁觀測1.366s含固定1秒 event pump，不是圖表純建構時間；此場景1次選取，不能混入5＋30同條件比較。其完成＋首次圖表 peakRSS1,451,900,928 bytes、CPU33.8125s、read4,512,968,456，與提前關閉場景分開保留。該次 launcher／Python PID 亦均退出。

Focused 檢查：

- Market 四模組61 passed；root 加入不遮蔽真正 DB 故障的回歸後，loader9 passed（其中8項重複，沒有把重跑當新增覆蓋）。包括 cutoff/window/reset／來源失效／清單副本、SQL SELECT 執行中取消後重試、既有 provider 相容、取消傳播與真實 TaskWorker native-finished 關閉。
- 整合47 passed：provider完整 legacy canonical hash／混合日期／錯格式 fallback／來源更新、mapper cache、回測首次頁／report snapshot／最新report／切回／單圖失敗提示與重試、shutdown coordinator、MainWindow 決策工作區。首次整合46 pass＋1 fail僅測試 fixture 路徑超過 Windows 長度；保留失敗 JUnit，用較短新 Temp basetemp 重跑唯一失敗項1 pass，未改產品來掩蓋失敗。
- 強制 Workbench85 passed；更新頁 validator25 passed／0 failed／4 skipped；mypy766 source files成功；13個變動Python檔 py_compile成功。代理6項 targeted tests與上述整合重疊，不另加總。未跑全量回歸／自然 producer／正式 learner。

原始收據均留 ignored `output/qa/product_stage01_20261005/`，不提交 DB、圖片、JUnit 或量測原檔：

- `baseline_agent/stage1_after_20261005_native/summary.json` SHA256 `cbe6777bddebae19d19c78bc46c48908ae74d63f84bf49d1fd00fd42d3964fa2`；每run result／stderr／source copy／input guard與final integrity留同目錄。
- `baseline_agent/stage1_first_use_20261005_native/run-01/first_use.json` 保留實際 snapshot；wrapper SHA `2fc55d36f87e6cdcfd020920a3516e1d88c3306a3558e652955f4fe3dea71a6b`。這是補充探針，不更改比較 profiler。
- `stage1_verified_metrics.json` 保存全變動程式的測量時 SHA、summary hash、12個 PID 檢查與分場景資源；`stage1_integration.xml`、`stage1_workbench.xml`、各 fresh basetemp 保存測試證據。`STAGE1_INTAKE_AND_ROLLBACK.md` 保留改動前範圍、預算與回復方案。

## 交付與未完成事項

本地 scoped commit／blob／status 核驗後停止交父層，不 push。唯一原plan採append-only；Manual、UI功能、目前架構、Snapshot、索引與兩份交接同步。原來源 warm-up／availability／universe／PIT／benchmark 缺口與研究ML自然成熟／正式資格維持 pending；UX01→UX16/17→UX18/19→UX04/05不跳過。持倉健康、選股、個股研究的全面首次使用與全互動壓力矩陣不在本包完成宣稱內。既有1477 Native保存／新程序讀回驗收不重跑；1000×835／125%接受及1000×800限制維持。

沒有永久刪除、訓練、正式 writer 或排程變更；未讀／修改未知 `paper_event_source_capture.py`，未動 `C:/ta_iso_1005` 或還原映射。容量仍是點時間判斷，不授權後續 writer。
