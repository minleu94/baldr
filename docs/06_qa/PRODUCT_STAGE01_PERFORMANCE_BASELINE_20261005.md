# 原計畫階段 0 首包：來源與效能基線

基線 `d086837172fe3b9c014539760013cedca8adcbfb`。沿用本機唯一計畫 `output/plans/baldr_product_experience_plan_20261004.md`，不另建計畫。此包完成 UX01 的有界差距基線、[UX16 來源子集矩陣](PRODUCT_STAGE01_SOURCE_MATRIX_20261005.md)及 UX17 的初始量測；**階段 0 尚未全面驗收，階段 1 的產品效能修改未開始**。本包產品程式與金融計算均未修改，新增的是可重跑 QA driver。

## 分工與邊界

root 統一整合、文件與 Git。兩個子代理透過工具指定 `gpt-6-luna`、`max`，工具接受：`ux16_source_matrix` 持有來源矩陣／唯讀收據；`ux17_baseline` 持有 `scripts/qa_profile_startup.py`／量測收據。代理只能自述通用 GPT-6，不能獨立核驗後端型號或 reasoning 設定；沒有自行換模型、另開代理或宣稱後端已獨立認證。

未重跑已接受的 learner／1477 操作鏈，未訓練、producer、全套回歸、交易、正式資料／registry 寫入或永久刪除。未知根檔 `paper_event_source_capture.py` 未讀未動；`C:\ta_iso_1005` 和還原映射未動。

## 可重跑入口與隔離

```powershell
.\.venv\Scripts\python.exe scripts\qa_profile_startup.py --platform windows --runs 5 --loaded-selections 30 --label <尚不存在的量測名稱>
```

- `--platform`：`windows` 為可見 Native QA 窗口，`offscreen` 是另一場景，不能混報。僅操作／關閉 driver 自己的窗口；本次桌面授權到 2026-10-05 16:11 UTC，不代表未來執行已獲桌面授權。
- `--runs`：1–5；五次是新 Python 程序，沒有清除 OS cache，不稱 cache-cold。
- `--loaded-selections`：0–30；只在第一跑執行。這是強勢股現有表格的可見列點選、選取身份與同步 repaint，**不包含依賴明細、列表篩選或圖表更新**。
- `--label`：英數、底線或連字號；同名目錄存在即拒絕覆寫。
- data/source output/candidate DB/receipt/output 路徑參數只允許本包固定的既有 QA 來源。正式 D 根、未知 output 或 reparse 別名遭拒，child 入口亦自行驗證，不可用本 driver 直接啟動正式資料環境。
- 重用 `native_final_v4/data/sqlite/twstock.db`（3,976,314,880 bytes），不拷貝大型 DB。每跑只複製 38 個既有 QA output 檔，共 10,799,692 bytes。`PROFILE=integration_qa`、私有 `OUTPUT_ROOT`／INI settings／policy／TEMP／MPLCONFIGDIR；log handler 在 QA 子程序中隔離，QStandardPaths 實際路徑亦入收據。這些都是量測配置，不改日常使用者設定。
- 首屏導覽可操作與 Workbench 首次 DTO／資料完成分開。constructor、既有 reader wrapper 都呼叫原實作，不代換合成 DTO；觀測 reader 結果後原樣返回。

Machine receipt：Windows build 26200、Ryzen 7 9700X 8C/16T、RAM 50,557,452,288 bytes；Python 3.11.9、PySide6 6.10.1。完整記錄在本機 `output/qa/product_stage01_20261005/machine_before.json`。沒有量訓練／盤後 producer 並行、十輪長駐或全市場新方法負載。

## 實際結果與場景分離

| 度量 | 次數 | 中位數 | 範圍／限制 |
|---|---:|---:|---|
| parent 觀測首屏可操作 | 5 | 10.148 秒 | 10.047–10.351 秒；100ms marker 輪詢 |
| Workbench 首次資料完成（child clock） | 5 | 10.126 秒 | 9.995–10.241 秒；與 parent clock 起點不同，不可相減 |
| MainWindow 建構＋show | 5 | 6.562 秒 | 6.487–6.666 秒 |
| IndustryMapper 建構 | 5 | 3.206 秒 | 3.192–3.298 秒 |
| MainWindow._setup_ui | 5 | 3.252 秒 | 3.209–3.305 秒；包含頁面建構，不能再與子 view 時間相加 |
| BacktestView 建構 | 5 | 1.098 秒 | 1.084–1.151 秒 |
| 已載入強勢股可見列選取 | 30 | p50 54.91ms | p95 116.60ms、max 123.81ms；僅選取高亮 |

第一跑強勢股 query/load 1.268 秒，現有 reader 返回 62,728 rows、日期 20260818–20261002，day／volume_lookback=20；畫面 top50，掃描母體 1,978。這是既有 QA snapshot 的實際母體，不外推正式 D 全市場覆蓋。Workbench DTO decision_date=2026-10-02，不改寫成查核日 10/5。

IndustryMapper 讀入 212,500 rows、日期 2014-01-02–2026-10-02；直接保存已存在的 observation，未為量測重算 hash。rowset SHA：`sha256:ff055b018b425fab26ec633babf449c5fbc1ac91a98c22efe1cbdae1f7a03a08`；source=`sqlite.industry_indices`，原 status=`unknown`。來源身份不授 PIT 或模型資格。

資源不能合併成一個「startup」數字：

| 場景 | 樣本 | 程序樹峰值 RSS | 全程 CPU | OS process read_bytes |
|---|---:|---:|---:|---:|
| 只啟動並合作關閉 | 4 | 699.9–702.0 MB | 10.31–10.97 秒 | 各約 212.3 MB |
| 首次市場探索＋真實載入＋30 次選取＋關閉 | 1 | 1,569.6 MB | 60.94 秒 | 4,513.1 MB |

RSS 是 20ms 採樣，可能漏短命子程序；read_bytes 是 OS 傳輸 counter，不等同實體磁碟讀量。CPU 是全程 process CPU，不能把第一跑的 60.94 秒稱首屏 CPU；測量時舊 summary 的 `startup_cpu_s` 欄名錯誤，原值保留，提交版已改名 `process_total_cpu_s`。

**第一跑關閉問題仍未接受。** 導覽到 `market_explore` 時，Overview 的 `DecisionDeskView.showEvent` 觸發既有 async refresh worker。78 秒 stack 顯示 `TaskWorker → DecisionDeskSnapshotBuilder → SmartMoneySemanticService._price_position → DecisionMarketFrameLoader._slice_to_lookback`，正在 pandas 大表布林切片。parent 到 90 秒上限發合作關閉後，child 約 90.48 秒退出，registry 最終為 0；ret0／最終退出不代表滿足 90 秒接受門檻。這是下一個有界工程調查入口，尚不能把該 stack 當全部耗時的已證根因或新功能的自然成熟問題。

## 資料完整性與失敗紀錄

五個 child ret0，逐跑及最終完整性檢查無未允許差異；root 讀回五個 PID 均已不存在。主 DB／candidate 大 DB 用 device/inode/size/mtime pin，**未做全檔 hash**；小 WAL／SHM／原 output／receipt 有 hash。SQLite 唯讀連線可能使用 mmap SHM 作協調快取，它不含 DB content。[SQLite 官方說明](https://www.sqlite.org/walformat.html#the_wal_index_or_shm_file)

第一次 smoke 因子程序中文 stdout 編碼與失敗分支 writer 問題停止；第二次因 SHM stat 改變停止。另一次 `mode=ro`＋`query_only=ON`、2382 LIMIT1 小查詢重現：主 DB stat 未變，WAL=0 bytes、stat/hash 未變；SHM 32,768 bytes、device/inode/hash 未變、byte-diff=0，只有 mtime 改變。原第二次 smoke 沒留起始 SHM bytes，不能倒補其 bytes 證明。五跑起才精確允許 SHM **mtime-only，且大小／識別／hash 全同**；其他變化仍停止，不改 reader 為 immutable、不 checkpoint、不刪 sidecar。

五跑父 runner 在完成並保存 summary 後，最後中文路徑列印遇 cp1252 錯誤、parent exit1；原失敗保留，不能聲稱 parent exit0。子程序、完整性與摘要均已獨立讀回。提交版只再修父入口 UTF-8 輸出與 aggregate CPU 名稱，不重跑或改寫原 summary。

- 測量版 driver SHA：`643dd724ed801d77a909ed5c7e509d0436e995352d44e4446cf49de79e544f90`。
- 提交版 SHA：`0a8a3ef5d8808c7bbc8151948fc5f8a6d98f731f3a367ef261e76ed9257f1003`。
- summary SHA：`94193d66f4f83f7b5efb134dab149558414dd8d932d487f024fb5d399c25d5f7`。
- 測量版在修改前未另存；其 bytes 由只反轉上述兩項修改重建，**完整 SHA 精確匹配測量時記錄**。重建副本／變更映射與原 trace 均留本機，不假稱事前備份。
- 提交版 py_compile／CLI help 通過；正式 data 根、未知 output 的父入口拒絕，以及正式 data 根的 child 入口拒絕已驗，拒絕時沒有建立 run 目錄。root 完整性讀回曾因把 errors 的空 dict 當 list 誤判，修正讀回器後完成；不是產品／資料失敗。

原始證據：`output/qa/product_stage01_20261005/baseline_agent/baseline_20261005_native/`（summary、五份 run/result/input_integrity、final integrity、78 秒 stack、postrun delta、測量版副本）、`source_matrix_agent/read_receipt.json`、`package_verification.json`。原先受控 DTO 圖與 1477 接受收據沿用，不重做。沒有 UI 產品修改，因此不為本包重跑已接受的 Workbench／validator／mypy 全域檢查。

## 凍結預算與下一包依賴

產品修改前已凍結：相同場景的首屏中位數與 RSS 峰值不得回退超過 10%；已載入列選取 p95<300ms；選定瓶頸分段中位數改善目標至少 20%。列選取這一小場景達標，**不等於所有 UX17 互動、關閉、資源或階段 1 已通過**。沒有產品修改，故沒有 after 值或改善宣稱。比較須分開四筆只啟動資源與一筆 loaded 資源；若下一包要五筆純啟動 RSS，先補該缺額，不混場景補數。

原依賴保留 `UX01 → UX16／UX17 → UX18／UX19 → UX04／UX05`。下一包先有界確認市場探索 worker 的實際資料讀路徑／反覆大表切片與取消檢查點，再選最小效能切片；IndustryMapper 3.206 秒與非首屏 BacktestView 1.098 秒另為可定位的候選。若改來源 canonicalization，必須證明完整 rowset hash 不變，不能靠改 hash／trim history／繞過來源資格來提速。方法欄位、暖機、全市場覆蓋、PIT／availability 與 benchmark 缺口見 UX16；未完成前不啟動 UX18／新選股方法。此首包本地 commit／blob／status 核驗後停止，交父層決定下一個產品切片。
