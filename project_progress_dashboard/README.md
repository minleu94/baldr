# Baldr 專案進度與接線 Dashboard

`index.html` 列出產品主導覽、子頁、頁內視圖、使用服務、畫面資訊來源、Gate 0–7 位置、局部交付狀態與目前缺口；另有逐項卡點責任、ML 架構層次、訓練收據、正式流程介入狀態，以及接到 Baldr 唯讀盤點服務的儲存狀態。

目前文件定義的 Gate 0 是已關閉的 Safe Refactor Closeout；2026-10-27 Advice 輸出政策調整屬 Gate 1。Gate board 分別顯示已完成、進行中、條件未滿及後續 Gate，不把 Advice 解鎖、局部 QA 或 route 接線換算為 Gate 完成率。

## 卡點責任怎麼看

總覽和「未接通與阻塞」頁會把複合 Gate 拆成單一下一步，標示下一個動作者與交接時機；標籤表示誰應接下一棒，不代表工作已開工或已正式派工：

- **Codex 現在可推進**：有具名工程或唯讀查核工作，不需要先等 Owner 核准。
- **你現在要點頭**：只計入此刻已具備決策證據、確實要 Owner 決定的項目。
- **來源／時間等待**：缺官方原件、來源回應或自然成熟結果；按刷新不會補造證據。
- **證據備妥後交你**：Codex 先完成證據包，再由 Owner 做 UAT 或逐來源處置。
- **Gate 條件成熟後／選用**：目前不是正在等你批准的工作；依前置條件或你的產品需求再排入。

截至 2026-10-28，Gate 1 的正式唯讀 Daily Journey／Advice、固定行情／策略／policy deterministic replay、人工決定保存讀回，以及隔離 MainWindow 的歷史查找均已有工程證據。現在交接 Owner 核對正式日常 GUI 流程第 1–3、5–6 項；第 4 項已由 Owner 回報完成。Gate 3 正式來源／PIT 接受仍是獨立限制，Advice 會持續明示。Gate 2 的 scheduler 也因 3 個真實 weekly review period、3 個操作日 evidence record、backup／restore、disable-first recovery rehearsal 尚未全數滿足而保持 disabled；Owner 啟用決定只在這些證據齊備後才需要。責任分類是依 Snapshot、Roadmap 與具名 QA 人工核對，不以 Git 作者猜責任。

## 開啟與刷新

### 只看內嵌清冊

可直接以瀏覽器開啟 `index.html`。不啟動本機服務時，頁面會使用 HTML 內的最後盤點；刷新按鈕會提示尚未連線。

### 從目前工作樹刷新

若 Windows 不允許預設連接埠 8765，服務會改用作業系統分配的本機連接埠，並自動開啟及印出實際網址。也可用 `--port 0` 強制自動分配；服務全程只綁定 loopback。

在 repository 根目錄雙擊 `project_progress_dashboard/Open Dashboard.cmd`，或在 PowerShell 執行：

```powershell
.\.venv\Scripts\python.exe project_progress_dashboard/serve_dashboard.py --open
```

啟動器會優先使用 repository 的 `.venv`，再啟動唯讀服務並開啟 dashboard。頁面載入時會自動做一次刷新；之後按「刷新專案狀態」重新讀取目前來源，個人追蹤會保留。預設網址為 `http://127.0.0.1:8765/project_progress_dashboard/index.html`。要換連接埠可執行 `.\.venv\Scripts\python.exe project_progress_dashboard/serve_dashboard.py --port 8766 --open`。在服務終端按 Ctrl+C 停止。

server 只綁定 `127.0.0.1`、只處理 GET，並限制靜態文件在 dashboard 與 `docs/` 範圍。刷新會唯讀取得 Git HEAD／分支／變更檔案數、`PRIMARY_NAVIGATION`／`PRODUCT_ROUTES`、`PROJECT_SNAPSHOT.md` 最新五筆日期段落、兩份具名 ML QA 收據，以及 Baldr 儲存維護頁使用的 `app_module.storage_overview.inspect_storage`。儲存根目錄透過純設定解析器讀取，包含市場資料、產品輸出、應用狀態與明示的 `dist` Trial 根；不建立目錄、不套用設定、不載入 Baldr app、不讀正式資料庫、不啟動更新／排程／訓練、不連外。

儲存盤點每次頁面載入或手動刷新執行一次，沒有背景輪詢。資料根目錄只顯示整個磁碟總量／可用量；同一磁碟上的多個路徑不可相加。`dist` 盤點沿用服務上限：最多 64 個版本、共用 4,096 個項目。缺少或不可讀的盤點根會明確顯示未完成；連結、不可讀項目或超限會標記部分量測。Dashboard 不會清理、刪除或修改任何檔案。

## 檔案選擇

- **HTML** 呈現導覽、服務／來源、缺口、ML 層次、訓練收據、篩選與個人追蹤。
- **JSON** 存 dashboard 的離線清冊與本機刷新回應；個人追蹤可匯出／匯入 JSON。
- **CSV** 匯出 route 的服務、來源、缺口及個人追蹤欄位，供試算表整理。
- **Python 標準函式庫 HTTP server** 提供 loopback-only 唯讀刷新 API，不需安裝額外套件。
- **Windows CMD 啟動器** 提供雙擊開啟方式；服務只在使用者啟動時執行，不安裝常駐背景工作。
- **Markdown** 保留使用方式；專案現況與資格以 Snapshot、架構文件及具名 QA 為準。

## 個人追蹤

在子頁卡片展開「我的追蹤」，設定未盤點、進行中、已完成、阻塞或延後，並寫負責人／下一步／日期。狀態保存在目前瀏覽器的 localStorage，不會回寫程式、資料庫或 Gate。

- 下載 CSV：匯出 route 與個人追蹤欄位。
- 匯出追蹤 JSON：備份個人狀態與備註，不含 dashboard 來源清冊。
- 匯入追蹤 JSON：從備份還原個人狀態。

瀏覽器會把 `file://` 和 `http://127.0.0.1` 視為不同儲存來源。若曾在 `file://` 填寫追蹤，先匯出 JSON，再於 localhost 頁面匯入；資料不會自動搬移。

## ML 狀態如何解讀

H20 個人模型與 restated allocation H5 是不同 lane：

- **H20 個人 gross-head lane**：A02 QA 僅有合成 artifact，未做真實 fit；A03 每日個人模型收據也明定 `auto_fit_performed=false`、`formal_order_allowed=false`。即時訓練進度目前未知，server 不監看執行中的訓練程序。
- **Restated allocation H5 research lane**：QA 記錄 2026-09-23 的特定訓練作業已完成，dataset 3,496,189 列、final fit 3,468,254 列。這個 100% 只代表該作業的終態，不代表 H20 lane 或整體 ML 專案完成。資料為 restated research，文件標示 `historical_pit=false`；評估結果不支持升格。
- **正式介入**：H20 入口可供研究檢視；正式 Advice／配置沒有 ML credit，自動下單未啟用。研究畫面可見，不等於模型已改變正式決策。

要顯示目前正在跑的訓練百分比，訓練 runner 還需要產生 versioned progress receipt，描述 run identity、資料集、已完成工作量與 completed／failed／cancelled 終態；沒有收據時 dashboard 顯示未知，不用舊作業填值。

## 來源與狀態界線

- 按刷新時，路由名稱／ID／workspace 來自 `ui_qt/main_window_coordinator.py`。已盤點 route 保留人工核對的服務、來源與缺口描述；新 route 會提示待盤點，不會猜資料來源。
- 儲存位置與容量來自純設定解析及 `inspect_storage`；`dist` 版本大小是有界盤點結果，不是整個磁碟使用量，也不代表版本可刪除。
- Git 變更只顯示檔案數，不列出其他工作中的檔名或 diff。
- 最新 Snapshot 段落會刷新；route 卡內的產品 Gate、服務、資訊來源和未接通狀態仍是人工核對的 dashboard 清冊，Snapshot 或 Scoped SSOT 改變後要複核清冊描述。
- 卡點責任與交接時機也是人工清冊；刷新會顯示最新 Snapshot 摘錄，但不會自動重分責任。Snapshot／Roadmap 改變後，須一併核對 `index.html` 的卡點項目。
- server 不查正式 DB、外部服務、排程、執行中的 app 或 trainer；H20 即時訓練進度在沒有 runner receipt 時保持未知。刷新時間是 dashboard 讀取時間，不代表資料本身都是最新。
- UI 接線、資料品質／PIT、工程 QA、產品 Gate、自然成熟與 Owner 接受是不同層次，不用頁數或測試數量加總成完成率。

## 更新清冊

HTML 內 `dashboardData` JSON 是無 server 時的 fallback。若 Snapshot 或 Scoped SSOT 顯示服務、缺口、資格或證據已改，應人工核對後更新對應 route／ML 清冊，再保留可追溯 QA 連結。刷新可偵測 UI route 變動；新增 route 會顯示待補視圖、服務、資訊來源與接受狀態的提示。

## 驗證狀態

- 本次責任呈現調整尚未執行測試，也未完成 dashboard 的瀏覽器視覺 QA；請勿將程式碼檢視描述成已通過 QA。
- `file://` 畫面預覽曾遭安全政策拒絕；沒有改用其他瀏覽器方式繞過。
- Qt 產品程式與正式資料未變更。
