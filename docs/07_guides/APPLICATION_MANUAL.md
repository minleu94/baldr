# baldr 完整操作手冊

> 本文件是目前 UI 的操作權威，正文從第 1 章開始，依工作區任務讀取相關流程。日期化維運與進階研究見[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前狀態以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準，驗收以具名 QA 為準。

## 章首歷史補充與舊連結導引

### 2026-10-09 全排程與 Codex automation 驗收

> **歷史狀態快照（截至 2026-10-09）**：以下「已啟用」與本輪驗收結果只描述該日記錄，不保證今天的 Task 狀態或最新收據。現行排程操作依[21 個 Task 的驗收 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)，最新專案狀態依 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md) 判讀。

Windows Task 執行 producer；Codex 05:30 晨報／06:20 晚間驗收只讀取已保存結果。全部21個Task的操作、來源根、時鐘、參數／期限判讀、安全限制與排錯見[全排程驗收runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。本輪已啟用Scheduler Operational，修正Direct10:00期待與四個背景action誤判；ML Forward休市／preflight須讀scheduler根，不能借舊child狀態。正式來源缺口、最新結果與回復見[10/09修正QA](../06_qa/BALDR_SCHEDULE_REMEDIATION_20261009.md)。

> 下列章首補充原文已完整移入[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)，這些連結保留舊章節錨點。原文中的日期、通過、失敗、pending 與未驗證界線均照原樣保留；目前使用方式請依[操作手冊章節地圖](README.md)查找。

### 均線／月營收／官方對照研究（開發中，尚未交付新版）

> 此研究入口仍標記為開發中、未交付新版；目前範圍與驗收限制見 [F12 主程式整合審查](../06_qa/BALDR_F12_MAIN_INTEGRATION_REVIEW_20261009.md)。原章節內容保留於手冊附冊。

核驗保存來源並完成查詢後，可用「上一頁／下一頁」瀏覽同一份已核查詢的排序結果；首頁的上一頁及末頁的下一頁會停用，讀取期間等待背景作業完成。頁碼只改變顯示範圍，不更換來源或篩選條件；跨頁比較籃保留所選股票與原頁碼。讀取失敗或取消時保留目前結果，查看狀態訊息後再操作，不以畫面仍有資料解讀為新頁已完成。尚未載入結果時，換頁與比較操作停用。這項操作說明不代表新版 EXE 或完整收藏重開旅程已驗收；最新測試及已知問題見[補完 QA](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。

### 2026-10-08 排程維運補充

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 2026-10-07 排程故障排查補充

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### Windows 可攜版入口

> 目前可攜版操作請看 [Windows 可攜指南](PORTABLE_WINDOWS.md)；原日期快照與驗收界線保留於手冊附冊。

### 2026-10-06 文件整理時的有限驗收快照（歷史）

> 這是日期化歷史證據入口；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，原範圍與 QA 界線保留於手冊附冊及具名 QA。

### 發布使用者首次安裝補充

> 目前首次啟動與安裝流程見[第 2 章](#2-安裝與啟動)、[安裝指南](INSTALL_GUIDE.md)及[快速開始](QUICK_START.md)；舊補充原文保留於附冊。

### 2026-10-06 收尾可用範圍與驗證

> 這是日期化歷史證據入口；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，原範圍與 QA 界線保留於手冊附冊及具名 QA。

### 2026-10-06 歷史結果有界讀取與排錯

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 2026-10-06 scheduled v2來源核驗與操作界線

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 2026-10-06 自然成熟證明與研究 run 發布排錯

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 私人儲存與合法深層路徑（2026-10-06）

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 首頁四個用途與股號搜尋（2026-10-06）

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 個股摘要的變化與資料限制（2026-10-06）

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 2026-10-06 明示市場基準的研究成效

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 2026-10-06 保存價格／MA20／MA60 的原版本圖表

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

### 2026-10-06 第一版有限研究流程與驗證入口

> 當時原文與限制保留於[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)；目前操作按[章節地圖](README.md)查找，狀態與驗收回到 Snapshot／具名 QA。

先依下方章節完成安裝、工作區操作與排錯。進階研究、日期化操作補充和受控維運見[手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)。

## 1. 系統能做什麼

### 頁面的 i 說明按鈕

點頁面標題旁的「i」可開啟該頁操作說明。視窗依實際功能分區，包含操作順序、輸入框與選單的用途、表格欄位與單位、圖表和狀態的判讀，以及載入或缺件時應查看的資訊。內容可以捲動及選取複製；按「關閉」回到原頁，原本輸入、篩選和已載入結果會保留。

回測頁的買入／賣出分數門檻位於「顯示進階研究設定」展開後的策略配置；啟用參數最佳化時，到最佳化區設定固定值或搜尋範圍。說明中分開解釋單次回測與最佳化的設定位置。資料日期、研究分數、報酬及缺資料狀態則依各頁的欄位定義判讀。

目前系統提供：

1. 更新每日股價、大盤、產業、券商分點與技術指標。
2. 用市場 Regime、強弱個股、強弱產業與 Smart Money 觀察市場。
3. 用 Profile 或進階參數產生推薦候選，查看 Why、Why Not 與分數拆解。
4. 建立觀察清單（候選池）與可重用選股清單。
5. 執行單股、批次、固定組合、推薦回放與策略研究。
6. 保存研究結果、比較既有結果，並在符合 Registry 與 Month 6 lifecycle Gate 時升級策略版本。
7. 記錄交易、持倉、覆盤日誌、停損停利、籌碼監控與生命週期回顧。
8. 唯讀觀察 Runtime 狀態、治理健康與事件流。

目前不能保證：

- 推薦股票一定上漲或策略一定獲利。
- quantile 一定優於 fixed；2026-06-14 的 10 檔 OOS 實證未顯示 quantile 優於 fixed，因此仍為 opt-in。
- 推薦回放等同可成交的實盤績效；V1.2 新增的 rolling risk、microstructure preflight 與 relative attribution 只是可信度診斷，不會把 replay 變成實盤撮合。
- Forward Evidence / Forward Performance 的 close-to-close forward return 等同實盤可執行績效，或能證明任一訊號有效。
- Daily Decision Desk 是主 UI「市場探索 > 市場總覽」的唯一實例；「決策工作台 > 決策來源」只保留導覽入口，不再嵌入第二份畫面。市場總覽保留 answer-first dashboard：先顯示今日主結論、研究模式註記、優先 / 風險產業與股票焦點，再保留各模組細節；股票焦點可下鑽至「市場探索 > 主力流向」。Market Breadth v1 已由 SQLite `daily_prices` 接線，Sector Rotation v1 已由 SQLite `industry_indices` 接線，Watchlist Trigger v1 已由 `WatchlistService` 與 SQLite `technical_indicators` 接線，Portfolio Alert v1 已由 `PortfolioService`、`PortfolioConditionMonitor` 與 `PortfolioChipService` 接線，Relative Strength / Liquidity Ranking v1 已由 SQLite `daily_prices` 接線，Why Not / 風險提示 v1 已由 `DecisionDeskRiskPromptService` 對接，並可呈現 fundamental diagnostics 來源的基本面風險提示。缺口會以 MISSING / DEGRADED / ESTIMATED 顯示，並保留 warnings。
- Runtime Observatory 會自動修復問題或自動下單。
- 觀察清單等同實際投資組合。

## 2. 安裝與啟動

### 2.1 建立環境

在專案根目錄執行：

```powershell
$env:PYTHONUTF8 = "1"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt -c requirements-py311-windows.constraints.txt
```

新使用者的 Windows x64／Python 3.11 安裝細節、空資料根與驗證步驟見[安裝指南](INSTALL_GUIDE.md)。`requirements.txt` 是相容的完整開發環境入口，不是一般使用者的預設安裝方式。若專案已經有可用且相容的 `.venv`，不需要重新建立。

### 2.2 資料位置

`TWStockConfig` 未設定時的相容預設正式資料根目錄：

```text
D:/Min/Python/Project/FA_Data
```

可在啟動前覆蓋：

```powershell
$env:DATA_ROOT = "D:\your\data\root"
$env:OUTPUT_ROOT = "D:\your\data\root\output"
```

新使用者請依[安裝指南](INSTALL_GUIDE.md)為行情與輸出各設定自己的空目錄；既有使用者則沿用已確認的原始資料根，不要因新建環境而改指向上述預設位置。

SQLite 主資料庫位於：

```text
<DATA_ROOT>/sqlite/twstock.db
```

### 2.3 啟動主程式

推薦：

```powershell
.\.venv\Scripts\python.exe ui_qt\main.py
```

若目前 shell 已啟用正確虛擬環境：

```powershell
python ui_qt/main.py
```

`ui_app/main.py` 是 Legacy Tkinter UI，不是目前主要入口。

### 2.4 第一次啟動檢查

1. 左側主導覽預設停在「決策工作台」；若是第一次啟動或要先檢查資料，切到「數據更新」。
2. 點擊「檢查數據狀態」。
3. 確認每日股價、大盤、產業、券商分點與技術指標有日期與筆數。
4. 若顯示待更新，依需求執行快速或安全更新。
5. 完成後回到「決策工作台」查看今日待判讀；需要研究時再進入「市場探索」、推薦與回測。

### 2.5 介面呈現一致性

主 PySide6 UI 採用金融研究工作台風格：深色背景、緊湊表格、狀態色、清楚的主要 / 危險 / 次要按鈕，以及無資料時的空狀態提示。這些設計 token、表格樣式與缺字 icon 清理只影響畫面呈現與操作可讀性，不改變資料抓取、SQLite 同步、推薦、回測、每日決策 snapshot、持倉計算或任何 service / domain 運算語意。

#### 視窗、頁面與表格的完整閱讀方式

主視窗以約 1400×800 的大小置中開啟，並依螢幕可用範圍限制初始位置與尺寸。全螢幕或放大視窗可以增加同時可見內容；視窗縮小、系統顯示縮放或長內容超出畫面時，請使用頁面自己的垂直捲動區域繼續查看。視窗放大不會取消頁面捲動，也不代表頁尾、警示或進階內容已全部留在首屏。

閱讀各工作區時依序操作：

1. 先用左側導覽選工作區，再切換該頁的子分頁／結果分頁。頁面標題或摘要若列出進階入口，按入口展開後仍可捲動同一頁的其餘內容。
2. 游標移到頁面正文後使用滑鼠滾輪，或拖曳正文右側捲軸；捲軸只有在內容超出視窗時才會出現。持倉頁的摘要、警示與進階明細共用整頁垂直捲動區。
3. 表格與清單保留自己的捲動，初始 viewport 至少容納前五筆資料（表格另含表頭）；實際資料不足五筆時仍保留閱讀高度，不會補造資料。清單長標籤換行時會依實際列高保留空間。超過五筆時移到表格／清單內再滾動，避免把頁面捲動誤認成資料已結束。若表格很寬，拖曳下方水平捲軸，或拖曳欄名邊界調整欄寬；窄控制列與技術細節區（例如 SQLite Inspector 篩選列、Market Regime layer3）也可能有各自的水平捲動。主頁其餘內容仍可垂直捲動查看。
4. 儲存格以省略號顯示長內容時，將游標停在儲存格上查看完整 tooltip；必要時拉寬欄位或水平捲動至該欄。長文字的折行、截短或表格捲動只改變閱讀方式，不會改變來源值。
5. 推薦分析與策略回測先讀摘要及狀態／警告，再往下查看表格、診斷、圖表或其他結果分頁。圖表不會代替表格中被捲出視窗的資料列；回測和推薦的結果狀態、日期、來源與限制仍須一併判讀。

顯示資料前先確認選取的工作區、子分頁、股票／結果身份與資料日期。空狀態、載入中、缺來源與零筆資料是不同狀態；捲動只會尋找已呈現的內容，不會補抓資料或把缺件轉成零。若無法找到預期內容，依序檢查所在分頁、頁面捲軸、表格／清單內部捲軸與水平欄位；仍有問題時記下主工作區、子分頁、視窗大小、系統縮放比例及可見狀態／錯誤文字，交由 UI 維護者重現。不要為了顯示資料改動正式來源檔案或 SQLite。

本輪版面調整只改 widget 尺寸、排列、scroll viewport、表格欄位 tooltip 與初始視窗幾何；不改資料、金融計算、推薦／回測邏輯、持久化或寫入權限。跨工作區 MainWindow 六格 offscreen 幾何矩陣已通過；viewport、使用步驟及 OS 原生視窗驗收邊界見 [UI Layout Audit 2026-09-29](../06_qa/UI_LAYOUT_AUDIT_20260929.md)。

### 2.6 左側主導覽與決策工作台

主視窗目前使用左側主導覽切換 9 個主工作區，預設第一屏為「決策工作台」：

1. 決策工作台
2. 市場探索
3. 推薦分析
4. 策略回測
5. 觀察清單
6. 個股研究
7. 持倉管理
8. 數據更新
9. 系統狀態（Runtime）

左側主導覽每個主工作區都有自製線條 SVG icon，協助快速辨識工作區意義；可用導覽列頂部的收合按鈕切換為 icon-only 模式以釋放橫向空間，也可以在目前已選取的主工作區按鈕上再點一次直接收合 / 展開。收合後仍可用 tooltip 辨識完整工作區名稱，並且只影響畫面空間，不改變任何資料載入、排程、報告或 service 行為。

主視窗會只以目前可見的工作區決定最小尺寸，避免隱藏的圖表或設定頁把整個 App 撐大。當視窗寬度不大於 1120 px，左側導覽會自動收成 icon-only；若這次是系統自動收合，視窗回到 1240 px 以上時才會自動展開。使用者手動收合的選擇不會被這個規則覆寫。

「每日決策」不再是頂層主工作區；唯一畫面位於「市場探索 > 市場總覽」。決策工作台內部子頁仍包含「總覽」、「決策來源」、「研究證據」（Evidence）、「持倉追蹤」與「操作節奏」，其中「決策來源」只提供「開啟市場總覽」導覽，不持有 Decision Desk widget，也不啟動第二次背景刷新。今日待判讀佇列清空時會顯示空狀態，提示可前往「市場探索」研究。這只代表目前 DTO payload 沒有待判讀項目，不代表 Phase gate 已完成，也不是買賣建議。

#### 今日待判讀與背景市場提示

「今日待判讀」只列出已有明確人工邊界的項目，例如持倉警示、觀察清單觸發、研究連續性提醒、來源缺口或明確需要 reviewer 裁決的準備度項目。市場篩選結果不會因為每一檔都產生提示就逐筆膨脹人工佇列；Workbench 只整理既有 `DecisionDeskSnapshot`，不重跑策略、不改變上游門檻。

`category=liquidity` 或 `weakness` 且 `source=relative_strength_liquidity` 的提示會各自聚合成一筆背景證據列，顯示提示數、代號預覽、來源追蹤與 `daily_decision` 下鑽。這些提示中的低流動性數值是以收盤價乘成交股數、取最近 20 筆觀測的「估算平均每日成交金額」，並非官方逐筆成交金額合計；門檻仍由 Relative Strength / Liquidity service 提供。它是研究前的機器篩選訊號，不等於每一檔都必須人工覆盤，也不等於可交易。

Workbench 會保留 portfolio/watchlist 提示的具體代號、原因與 action hint；若 section 還有未被 prompt 覆蓋的代號，會另列「其餘」人工項目，避免聚合時遺失。已知的 `market_context`／`fundamental_diagnostic` producer contract 仍以原本的逐項風險提示呈現；無法辨識的 category/source 則集中在「未分類風險提示」背景列與 action diagnostics 中，保留 code、reason 與來源追蹤，不會靜默丟棄。

當人工佇列為空時，請同時查看背景證據流、來源狀態與每日檢查清單；空佇列不代表風險已確認、Phase gate 已完成或可以交易。所有列仍是唯讀 DTO，不寫 SQLite、不標記完成、不啟用正式排程器。

「總覽」現在先顯示「今日行動中心」：四張卡依序整理資料狀態、市場判讀、Advice／候選與持倉覆盤；上方唯一主要按鈕會依既有 DTO 選出下一個應檢查的工作區。它只會切換至數據更新、市場總覽、推薦分析或持倉管理，不會更新資料、執行策略、產生或套用 Advice、寫入持倉或交易。資料待確認時先看數據更新；有持倉 Action Item 時先看持倉管理；再依待判讀與 Advice DTO 狀態導向市場總覽或推薦分析。

資料可用性判讀先看畫面上的研究／決策基準日（`as_of`）、資料日期、來源狀態與 warnings；UI 不把本機日期猜成台股交易日，也不自行補 freshness。Workbench DTO 沒有提供資料日期時會明示未知，應按「查看數據更新」回到既有來源投影。空白、載入中、部分完成、stale、失敗與已取消是不同狀態；背景更新只顯示目前階段與已處理數量，總量未知時不製造百分比。取消後保留已完成成果並標示真實取消狀態，不能解讀成完整更新。

行動中心下方保留四個指揮台摘要 block：今日待判讀、人工待處理、等待真實時間、Warnings。等待真實時間 block 會明確顯示 weekly history 與 multi-day dry-run 比例，讓使用者掃描重點後再往下看表格。「研究證據」（Evidence）子頁已替換為唯讀 Research Console；「持倉追蹤」與「操作節奏」仍是摘要與下鑽入口。Research Console 的可見性不代表 formal evidence、source acceptance 或 promotion 已完成。

Workbench 仍只透過 `WorkbenchSourceService` / `WorkbenchDashboardDTO` 讀取既有資料；不寫 DB、不啟用 production scheduler、不執行 replay、不補 lifecycle gate、不產生買賣建議。Evidence 必須按來源層判讀：formal/canonical DB credit 未授予；未設定 projection 時 legacy DB 可能顯示 `0/3`；歷史 working-copy Week 1=`1/3`；owner-approved UI projection=`3/3`；正式 sidecar 已有 `10` 期 `pending_human_review`；multi-day dry-run=`3/3`。目前缺口已不是「等待 Week 2／3 出現」，而是由具名 reviewer 對 10 期逐期裁決、取得 formal credit，並完成 backup／rollback／recovery 與 scheduler approval。UI 重排、replay、fixture 或人工改表都不能替代上述步驟。

若來源投影明確回報決策 snapshot 未來日期、snapshot table 缺失或其他 source gap，Workbench 會在「決策來源缺口」列中保留可讀原因與 `evidence_mode` 下鑽；機器-only readiness gap 不會被改標成人工 review。此時先查看來源 trace／數據更新／Evidence，不要在 UI 查 DB、改日期或把空佇列當成安全。

窄版（例如 390×844）會把今日行動卡、主要內容與 Inspector 依序堆疊；推薦、Research Lab 與 Portfolio 的設定／結果或操作列也會改為垂直排列。頁面正文可垂直捲動；需要完整查看欄位時，表格、長控制列或技術細節區可使用各自的水平捲軸。主要錯誤、取消與下一步仍可在頁面內容中查看。Workbench Inspector 的技術欄位預設收合，按「查看技術欄位（DTO raw）」才展開 hash、schema 與 Gate 細項；DTO 沒有提供時顯示未知，不由 view 重建。

#### 每日投資結論／每日決策旅程

這是目前「決策工作台 > 總覽」的首屏唯讀入口。畫面依序呈現決策日與資料日、盤勢、產業／市場指數代理、今日研究候選、持倉警示、證據成熟度與下一步；`Research Workflow` 預設收合，按「展開」才查看市場→產業→個股→觀察清單／持倉的既有導覽。

操作每日候選時，按「開啟 <股票代號> 個股研究報告」會把候選的股票代號、決策日、資料日、result/source identity 交給既有 `StockResearchReport`。這條路徑不要求候選先存在觀察清單，也不會自動新增觀察清單；「查看既有觀察清單」仍只開啟目前清單。按「查看證據成熟度」會切到既有 Evidence／Research Console，按「查看每日來源詳情」才展開完整 identity、hash、scope 分母、各 horizon、learning receipt 與 diagnostics。

參數意義以來源 payload 為準：決策日是 Workbench 的比較基準；資料日是候選或 snapshot 明示的有效資料日；Evidence 只採用 forward receipt 指定的 `event_type`、日期範圍、`require_cohort_identity`、`max_events` 與 outcome windows；Learning 分開顯示 receipt、候選／challenger 與 active pointer 的自然成熟樣本。UI 不重算推薦、forward outcome、模型或產業排名，也不把 `available`、hash、evidence kind 或 shadow 標籤升格為自然驗證權威。

結果判讀時，`研究候選` 只代表可下鑽的研究輸入；資料降級、缺漏、過期、未來日期與來源讀取失敗都要依狀態處理。`尚待成熟` 代表需要等待後續官方交易日的可見價格，不回填、不補未來資料；`0` 件／筆是明確零計數，不等於安全或 Gate 通過。產業卡若顯示「市場指數代理／缺產業分類」，不能直接解讀成真實產業領先／落後。Learning 顯示 `rule_only` 或尚無 natural matured sample 時，不得稱為 current champion、正式模型或下單依據。

安全限制：每日旅程只讀取既有 DTO、排程 JSON、EvidenceEvent／Outcome 與隔離 learning receipt；不寫正式 SQLite／FA_Data、不啟用 production scheduler、不執行策略或 runner、不改 Advice／Portfolio、不新增候選、不下單。真實 Evidence、typed verifier、PIT 產業分類、Journal／Portfolio ledger continuity 與正式 promotion 仍由各自 Gate 判定。

排錯順序：先按「重新整理狀態」，再核對數據更新的資料日與排程 `latest_status.json`；若候選為來源待檢查，確認 recommendation snapshot 與其 result 對應的 run JSON；若證據為待成熟，等待合法官方交易日；若顯示來源讀取失敗、過期或未來日期，保留詳情供人工核對後重試，不把舊畫面或空結果當成今日結論。若產業名稱含槓桿／反向產品字樣，回到來源詳情確認代理來源，不自行改標產業強弱。

#### Research fallback packet（每日證據不足）

Workbench「總覽」的每日決策旅程會在 evidence 不足時直接顯示一個唯讀 Research fallback packet。它沿用同一份 `WorkbenchDailyEvidence` 的 result／stock（若已知）、決策日、source identity 與 learning cost lane，並說明：

- `缺什麼`：既有 candidate／EvidenceEvent／Outcome／capture／typed receipt 的明確缺口或衝突原因；`pending_natural_evidence`（等待自然成熟）與 `blocked_*`（日期、provenance、身份或成本受阻）不可混讀。
- `研究問題` 與 `下一步`：只要求核對或補上同一決策日、同一 candidate／source／cost scope 的既有資料，再重新整理 Workbench；不會由畫面啟動 runner、scheduler、重算或寫入。
- `再看`：只有同 scope 的 pending EvidenceEvent 原決策日、正整數 horizon 與可解析的 `OfficialTradingCalendar` 都存在時，才估算官方交易日；其餘顯示 `未知`，不以日曆天數、今天日期或缺件日期倒填。
- `source owner`：既有 DTO／receipt 沒有提供 owner 時固定顯示「未知（既有來源未提供 owner）」；不可自行填人名或把 source ID 當 owner。
- `限制`：packet 永遠是 `read_only=true`、`write_intent=false`、`positive_fallback_allowed=false`，不提供有效機率、score、權重或買賣結論。若有 historical replay／evaluation，只能另作研究比較，不能與 natural evidence 混算。

按「查看每日來源詳情」可核對 packet 的 scope key、來源、缺口、研究問題、下一步、再看日期／未知理由與禁止動作。正常狀態不顯示 fallback 區塊，仍依既有成熟度閱讀；capture 缺失、資料缺件、identity／cost conflict 與 provenance blocked 各自保留不同狀態。若再看日期是未知，先修復或確認官方日曆／同 scope pending event／horizon 的缺口，再重整；不要手動補日期，也不要把 packet 當成 Advice approve 或交易入口。

### 2.7 顯示縮放、鍵盤與長表格驗證

PySide6 主視窗的可重跑縮放／鍵盤 smoke 使用真實 `MainWindow`、左側工作區導覽、Runtime 狀態元件，以及實際嵌入的「推薦分析」`results_table` 與「持倉管理」`positions_table`。它在隔離 `DATA_ROOT`／`OUTPUT_ROOT` 中以 Qt `offscreen` 平台執行，不會寫入正式資料；會在 150% 與 200% scale factor 下以固定 1366×768 logical viewport 執行 `QTest`，以 `Space` 切換「市場探索」與「Runtime」，確認焦點保留，並把隔離 DTO 注入兩個實際頁面的 600 列表格，以 `PageDown`／`Ctrl+Home` 驗證捲動及返回頂端。執行命令：

```powershell
.\.venv\Scripts\python.exe scripts\qa_validate_ui_scaling_keyboard.py `
  --output-dir "$env:TEMP\baldr_ui_scaling_keyboard" `
  --scale 1.5 `
  --scale 2.0
```

結果 `summary.json` 會保存要求／實測 scale factor、DPR、固定 logical viewport、實際頁面表格名稱與 viewport 尺寸、鍵盤步驟、Runtime 狀態文字、長表格 scroll 數值與隔離 PNG；`evidence_kind=offscreen_qtest` 明確表示這是 Qt offscreen 證據。它不能證明 Windows 前景焦點、實體螢幕在系統 150%／200% 顯示設定下的實際外觀或螢幕閱讀器支援。若要取得這些證據，需在可控的 Windows 前景環境逐一按 Tab／Space／PageDown 並保存畫面；沒有實作時不要把 offscreen 結果寫成真人鍵盤或 screenreader 驗證。

推薦分析的 Regime 建議中，「Regime 判讀信心」只描述市場狀態 detector 對當下資料的判讀，不是獲利機率、風險預算或個人適配。建議由 `RecommendationProfileService.suggest_profile_for_regime` 依既有 Profile-Regime 適用性及 Profile 自己明確宣告的風險等級決定；已選的使用者 Profile 會被保留。沒有可證明的風險預算時，只在相容 Profile 中提出最低已宣告風險等級的研究建議，並清楚標示不代表個人適配；若已選 Profile 超過指定預算、預算格式無效、缺少風險 policy、風險預算不相容或 Regime 不可用，會保留 selected identity 但維持 blocked／incompatible，不把使用者選擇呈現為 policy 通過，也不自動換用另一個 Profile。這個建議不會自動套用 Profile、寫入資料或建立交易。

## Gate 1 Advice：決策工作台的唯讀操作

在「決策工作台」收到 Advice DTO 時，先看 mode、`decision_date`、`data_as_of_date`、資料品質與 warnings，再閱讀 action、Why / Why Not / Risk、source trace，以及持倉的 target/current/gap。這是可追溯的研究與人工決策輔助，不是委託、報酬保證或自動交易。

1. Guided Mode 僅顯示 promoted、參數鎖定且 disclosure 完整的策略結果；candidate / shadow 會 fail-closed。
2. Professional Mode 可以查看 candidate 研究結果，但不能把它與 formal Advice 混為同一決策依據。
3. `NO_NEW_POSITION`、`RESEARCH`、`AVOID` 是安全結果。看到這些結果時，先檢查拒絕原因（策略狀態、資料品質、可成交性、風險預算、現金或持倉限制），不要手動補值或繞過限制。
4. 平衡風險檔為最低現金 `2000 bp`、最多 8 檔、單檔上限 `1500 bp`；權重使用整數 bp，金額使用 `Decimal`。UI 只能顯示結果，不能修改 policy。
5. Advice 的 decision / data-as-of date 與 source trace 必須存在；資料截止日不得晚於決策日。缺資料、降級或未來資料會被拒絕或降級，不能當作可交易結論。

### Advice 機率與來源依據（2026-09-14）

在 Advice 表格選取一列後，先閱讀同一行的「校準機率」與「成本後獲利機率」旁的證據
標籤，再按「查看機率依據」。這兩個欄位與排名分數／百分位是不同量；只有上游提供的
整數 bp 機率才會轉成百分比，不能用排名分數或文字信心代換。

- `可用估計／自然驗證未證明` 只表示有可用的校準估計，不是自然 forward 已驗證。
- `研究中／shadow` 只表示研究／shadow 路徑；不要自行解讀成 prospective 或正式 Advice。
- 若只看到自然 evidence receipt 但沒有 typed authority verifier 的驗證結果，畫面會保留
  unknown；source、hash 或 `status=available` 都不能自行視為核准證明。
- 依據詳情會列出 decision date、data-as-of、適用期間、樣本數、模型版本、資料集版本、
  機率來源、evidence kind、自然 evidence 狀態、完整 source trace 與 warnings。短摘要會
  遮蔽完整 hash，完整 hash 只在「機率依據詳情（唯讀）」中查看。
- 這個按鈕只展開既有 DTO 的唯讀內容，不查詢或改寫正式 DB、不建立 journal、不改
  Recommendation／Portfolio、不啟用 scheduler，也不建立 broker order。畫面 screenshot 或
  controlled fixture 只代表呈現可讀，不代表真實市場→產業→個股端到端已驗收。

本輪端到端來源契約稽核另確認：正式 `RecommendationService` 產生的
`RecommendationCalibrationProjection` 才是校準／成本後機率的來源；`AdviceComposer` 對 bare
raw mapping、只含數字／status、缺 model／dataset／horizon／cost／source，或股票 scope 不符的
payload 會 fail-closed。正常 typed shadow projection 可保留 ranking、校準機率、成本後機率、
sample、20 trading days、model／dataset 與 cost trace，但畫面仍標示「研究中／shadow」，不等於
自然驗證。正式 producer 只有在 active candidate metadata 明示獨立的
`after_cost_null_benchmark_50pct_v1`／`5000 bp` contract 時才傳入 after-cost baseline，consumer
也會核對 candidate metadata；宣告但未提供數值、或 consumer／source 不可用時仍保持 unavailable，
不以數字補值；null baseline 若收到非 `5000 bp` 數值也會 fail-closed。只有 ranking score 時機率維持未知，
confidence 也不是獲利機率。

歷史 walk-forward／untouched-test 校準可以作研究比較；若來源明確是 historical／replay，會標示
「研究中／歷史研究」，不因 natural sample 尚未成熟而全部隱藏，也不與 natural matured evidence、
formal Advice 或 promotion credit 混算。沒有 typed scope 或實際資料時顯示 unknown／研究中；不要
手動填入 80%、自然樣本或 observed cost。

Advice 表格有三種空白狀態，不能只用「沒有列」判斷：`WAITING_FOR_ADVICE_DTO` 代表尚未載入 Advice DTO，應先依畫面導引檢查資料更新或推薦分析；`NO_ELIGIBLE_ADVICE` 代表 DTO 已成功載入但沒有符合條件的建議；`ADVICE_DTO_ERROR` 才代表 DTO 遺失、結構不完整或安全診斷拒絕。來源顯示 degraded / warning 但仍帶有有效 recommendations 時，表格應照常呈現，並把警告保留在摘要與警告區；不得把它誤判成 DTO 錯誤。

Advice 不寫 DB、不啟用 scheduler、不建立 broker order、不改 Scoring / ranking / backtest，也不套用 lifecycle action。weekly review history 的 working-copy 保存與真實時間累積屬 Gate 2；人工覆盤完成後只能以 `build_evidence_operations_weekly_review.py --save-history` 對隔離 working-copy DB 保存，再以 `--list-history` 核對，不得直接編輯 history、使用 production DB 或以 replay / fixture 補週數。它不因 Gate 1 完成而自動通過。

## 3. 每日建議流程

### 快速研究流程

1. 數據更新：先檢查資料狀態，必要時執行快速更新。
2. 市場探索：檢測 Regime，查看強弱與主力流向。
3. 推薦分析：選 Profile，執行推薦並閱讀 Why / Why Not。
4. 加入觀察清單：保存要研究的股票。
5. Research Lab：使用單股或批次回測驗證。
6. 保存結果；只有符合 Gate 的結果才升級策略版本。
7. 需要追蹤交易時記錄到持倉管理，後續寫覆盤日誌。

### 完整備份流程

定期或資料修復後使用「安全更新（完整 CSV + SQLite）」，保留 CSV 歷史備份與 SQLite 同步。

備份檔集中在 `DATA_ROOT/meta_data/backup/`，同一來源同一天只保留最新一份，最多保留最新 5 個日期版本；migration / backfill / registry / 大型 merge 入口也採同一 retention 規則。既有大型備份來源與清理候選見 [BACKUP_RETENTION_AUDIT_2026_07_06.md](../03_data/BACKUP_RETENTION_AUDIT_2026_07_06.md)，清理前必須先由使用者確認。

## 4. 數據更新

### 4.1 全部資料看板

「檢查數據狀態」及來源明細是唯讀觀測：缺 DB、缺來源或資料降級會保留實際日期、quality 與 warnings，不因檢查而建表、寫入 manifest 或修復資料。candidate 可用不代表已接受正式來源。下載／合併／指標計算仍使用各自明確操作；技術指標由單一寫入者落地，週末資料缺官方交易 session 證據時不會被誤收為交易日。

窄視窗（小於 720px）會將左側資料來源導覽移到內容上方，核心狀態卡改為雙欄、候選資料卡改為單欄、快速／安全／狀態檢查按鈕改為直列；整個更新頁可垂直捲動。所有更新子頁沿用同一套 Midnight Analyst 深色面板、語意按鈕與狀態摘要樣式，不會因切換來源而變成淺色表單。這只是畫面排版，更新日期、worker、SQLite 同步與 fail-closed 規則不變。

「全部資料」頁先顯示資料影響與下一步，分開列出最後成功完成、股價資料日及技術指標資料日，再提供「立即操作」與本次手動更新摘要。最後成功完成來自已保存更新時間軸；資料日來自同次各來源狀態，不以目標日或成功操作代填。未知、過期、部分完成與檢查失敗不能解讀成資料齊全；本輪缺欄位時不沿用舊日期。按「檢查數據狀態」後先核對各來源卡片，再依原因選擇個別更新。核心卡寬版採三欄、窄版採雙欄；整頁可捲動。候選資料與月營收分頁仍保留檢查／抓取操作列。

更新時間軸與執行歷史、候選資料、官方來源候選與接受條件、使用資格與完整阻擋原因預設收合，按對應「展開／收合」可查看原完整明細。候選有資料不表示正式來源已接受；收合不解除阻擋或改變寫入權限。刷新保留資料頁、展開選擇，以及仍存在的步驟／來源／lane／Run 選擇。檢查失敗時先展開明細核對錯誤與來源，再重新檢查；原快速／安全更新、取消、SQLite 同步及人工確認規則不變。

狀態卡片包括：

- 每日股票數據
- 大盤指數數據
- 產業指數數據
- 券商分點數據
- 技術指標數據
- 月營收資料

月營收卡片會以「最新可用日」顯示該期全部資料的 `available_date`，並在附加列顯示 `fundamental_monthly_revenues` 的「已匯入期別」；這兩者不能視為每日交易資料的「最新日期」。若同一期仍有部分公司尚未到可得日，該期仍列為待生效；卡片會顯示待生效期別數與完整可用起始日。這是 point-in-time 可見性保護，不代表更新失敗。

若 `OUTPUT_ROOT/monthly_revenue_mops_snapshots` 中存在比 SQLite 已匯入期別更新的受控命名 snapshot，卡片會改顯示「候選可用」，並列出「候選待套用期別」與抓取日。即使候選與已匯入期別相同，也會顯示「候選快照期別」與抓取日，避免重抓或修訂候選在畫面上消失。這只代表已取得新的數值候選，不代表公告日 availability mapping 或 SQLite 已完成；仍須先跑 availability validator 與 backfill dry-run，再由人工確認是否正式套用。snapshot 選擇依檔名的資料期別／抓取日，不依檔案大小，UpdateView 與兩個 availability builder 共用同一規則，避免歷史大檔遮蔽最新候選。

狀態檢查也會依台灣市場日期與一般 MOPS 公告節奏提供「預期最新期別」提示：每月 1--9 日先以前兩個月作操作提示，10 日起以之前一個月作提示。例如 2026-09-04 的提示是 `2026-07`。這只是候選抓取的導引，不是官方公告證據；若正式資料仍停在 2026-06，卡片會標成「待更新」並明示必須先取得數值 snapshot 與可得日 mapping。已有更新候選時則優先顯示候選狀態，不把候選誤報成正式資料已套用。

若 snapshot 尚未放入正式 `OUTPUT_ROOT`，可設定 `MONTHLY_REVENUE_SNAPSHOT_CANDIDATE=<絕對路徑>` 讓狀態檢查唯讀投影該明確候選；這不會掃描 TEMP、不會自動替換正式 snapshot，也不會改變更新頁的正式 backfill 欄位。路徑不存在或檔名不符合受控規則時，卡片會保留「缺漏／候選無效」與診斷，不會悄悄退回另一份 snapshot。

若已有由 `build_monthly_revenue_availability_history.py` 或受控 PIT 匯入產生的公告日／可得日候選 CSV，可設定 `MONTHLY_REVENUE_AVAILABILITY_CANDIDATE=<絕對路徑>`。資料更新狀態檢查只會讀取這個明確檔案，先執行 validator，再對正式 mapping 做唯讀 merge preview；卡片會列出候選期別、筆數、可用日、可併入／已併入／衝突／無效狀態，以及新增與衝突筆數。候選期別無法解析時也會保留狀態與最多兩筆 validator 診斷，避免檔案遺失或格式錯誤被誤看成「沒有候選」。`ready_for_merge` 仍只是候選可併入，不會自動寫入正式 mapping 或 SQLite；正式套用仍須另行執行 availability merge 與月營收 backfill 的確認流程。未設定此變數時不會掃描 TEMP 或其他相鄰目錄，也不會把 snapshot 候選誤當成公告日證據。

狀態意義：

| 狀態 | 意義 |
|---|---|
| 正常 | 本地資料接近最新交易日且可讀。 |
| 待更新 | 資料庫可讀，但日期落後。 |
| 異常 | SQLite 或必要資料讀取失敗。 |
| 未檢查 | 本次啟動尚未執行狀態檢查。 |

Formal 與 Candidate 是不同資料 lane。畫面或 payload 的 `FORMAL_AVAILABLE` 表示正式資料表可讀，`CANDIDATE_AVAILABLE` 表示隔離候選來源可讀；兩者各自顯示日期及筆數。這些 token 只說明各 lane 的讀取狀態，不代表來源已接受、資料已新鮮或符合 PIT／交易資格。Candidate 有資料不表示已接受正式來源，也不會被合併計入 Formal 筆數、推薦分數或交易資格。若 candidate 狀態待重驗，應查明 Candidate DB 與當次 run receipt，不要把它改讀成正式來源。

當市場指數、產業指數、券商分點或技術指標標為「待更新」且服務回傳
`freshness_status=lagging` 時，卡片與來源詳情會額外顯示「新鮮度基準日」及「資料最新日」。
這兩個日期用來直接判讀落後幅度；它們不是新的資料來源，也不會自動觸發下載或寫入。

狀態燈只依明確的 `status` token 判定：`ok`／`success`／`current`／`normal` 才是綠色「最新」；`error`、`missing`、`empty`、`unavailable` 或狀態查詢失敗會顯示紅色「異常」，不會因說明文字出現「最新」就視為正常。inline 摘要會把 `success`／`current`／`normal` 統一顯示為中文「正常」。若回傳 payload 缺少某一資料源，該卡片與對應 inline 摘要都會重設為「尚未檢查」，不沿用上一輪的日期、筆數或 0 筆判讀。

尚未按下檢查按鈕時，卡片內的提示文字不會被當成 `status` 欄位；燈號會維持灰色「未檢查」，不會誤顯示黃色「待更新」。

全部資料頁的卡片下方另有「資料更新時間軸（唯讀）」：按「檢查數據狀態」後會讀取固定的 `OUTPUT_ROOT/scheduled/data_update_quick/latest_status.json`、`OUTPUT_ROOT/scheduled/data_update_quick/history.jsonl`、`OUTPUT_ROOT/scheduled/data_freshness/latest_status.json` 與 `DATA_ROOT/meta_data/tpex_full_refresh_status.json`，顯示最後成功完成時間、run、目標資料日、每個更新步驟、最近執行歷史、freshness 結果與診斷。時間軸狀態 `最新`、`部分可用`、`freshness 異常`、`已過期`、`執行中`、`失敗`、`缺漏`、`格式異常`、`未設定` 的判讀彼此不同；history 缺檔時，若 latest status 仍存在，UI 會明示「新版 runner 尚未產生；不回填舊 latest」，`empty` 會明示等待下一次真實排程，`invalid` 會明示需修復 JSONL。缺檔或讀取失敗會清掉本輪步驟列與歷史列，不沿用上一輪成功結果。這個投影只讀檔，不掃描其他 `latest_status`、不發網路、不寫資料庫，也不把檔案修改時間當成成功完成時間。

時間軸旁另有「本次手動更新」摘要，專門記錄目前 UI 觸發的快速／安全／單一來源更新：執行中會顯示進度與資料區間，完成、失敗、錯誤或合作式取消會保留本輪訊息、失敗步驟、成功／失敗日期數與警告。它與排程時間軸分開，不會把上一輪排程成功結果當成本輪手動更新成功，也不會把手動結果回填成排程 history；若要確認實際 SQLite／CSV 狀態，仍應在工作完成後按「檢查數據狀態」。

手動更新若以失敗或背景例外結束，畫面在顯示本輪錯誤後會再做一次唯讀狀態檢查；因此即使前面已安全提交部分 CSV／SQLite，也會把實際最新日期與筆數刷新出來。這個重查不會重跑下載、合併或寫入，也不會把部分成功改標成完整成功。

「全部資料」頁另有「整體程式 readiness（唯讀）」區塊。若要在 UI 同時查看 P0、Evidence、
Paper Portfolio、Formal／ML、Runtime、效能／容量與更新歷史七個 lane，請在啟動前設定：

```powershell
$env:PROGRAM_READINESS_ARTIFACT = "C:\path\to\program_readiness.json"
```

按「檢查數據狀態」後，區塊會顯示整體狀態、每個已投影 lane 的狀態、阻擋原因、下一步與
是否需要外部輸入；原始 machine token 會保留在表格中。此路徑必須是明確的
`program-readiness.v1` JSON 檔，UI 不會自動搜尋或選擇 TEMP／正式目錄中的其他 artifact。
未設定、遺失、超過大小上限或 schema 不符時會顯示「未設定／缺漏／格式異常」診斷；這個區塊
永遠是 query-only，不會寫入 SQLite、發網路、啟用 scheduler／broker、解除 source acceptance
或取得 Formal credit。

要讓效能 lane 同時顯示「證據已整理」與「仍待 owner 決策」，產生 readiness 報告時可加上
`--performance-owner-packet <PERFORMANCE_OWNER_PACKET_JSON>`。該檔必須是由
`scripts\build_performance_canary_owner_packet.py` 產生、位於 OS TEMP 的
`performance-canary-owner-review.v1`；inspector 只投影 packet status、review lane 數與待處理
數，不讀取任意 nested payload。UI 的效能摘要會顯示 owner packet 狀態與 `待處理／總 lane`，
但 `needs_named_owner_reviewer`／`ready_for_owner_review` 都不是 production canary 授權，
仍須另外完成 technical backup／rollback、容量與 broker review。

同一頁的「P0 官方來源證據（候選／唯讀）」表格固定顯示 13 個來源及其治理／machine 狀態、實際 route、PIT／公告、coverage、license 與 owner／下游邊界。Fallback 欄位會區分：`是` 代表替代路徑真的被採用；`否（已嘗試但未採用）` 代表曾 probe 但因 `date_mismatch`、`official_no_data`、`network_error` 或其他 fail-closed 結果沒有採用；`否`／`未提供` 則表示沒有可觀測的 fallback 嘗試。日期不符會同時列出要求日與觀測日，傳輸／解析錯誤會在滑鼠提示中保留 error type、endpoint、HTTP／payload evidence；summary 另顯示 fallback 已嘗試、已採用與未採用計數。這些欄位只改善診斷，不授予 source acceptance，`downstream_eligibility` 永遠為 `none`。

表格最右側的「Probe 路徑狀態」會逐條顯示候選 route 的實際 probe 結果，例如 `已觀測（observed）`、`失敗（failed）`、`官方無資料（official_no_data）`、`日期不符（date_mismatch）` 或 `未嘗試（not_attempted）`，並以「已選」與 `fallback` 標記 lineage。摘要會列出已嘗試／總路徑及各狀態計數；若舊 artifact 沒有這個欄位，畫面保留「未提供」，不會把 route registry 當成網路成功證據。這仍是候選、唯讀診斷，不會解除 license／owner／PIT gate。

P0 表格的長欄位採固定上限欄寬、儲存格換行與水平捲動；完整原文仍保留在每格滑鼠提示中。這樣在一般視窗寬度下可以先讀到狀態與 blocker，不會因 endpoint、hash 或 license URL 把整頁撐寬；縮小視窗時請使用表格底部水平捲軸查看其餘欄位。

由「產生 P0 candidate intake／Owner packet」工具輸出的 machine evidence 也會保留 route probe status；packet 內 route label 會附上 `observed`／`failed`／`not_attempted` 與 selected／fallback 標記。這只方便 Owner 逐路徑複核，不會把 route registry 或單次 probe 自動轉成 accepted／limited。

若要讓 UI 使用最新 route status，請把明確產生的 audit 檔設定到 `P0_SOURCE_CONTROL_CENTER_AUDIT`（例如 `C:\Users\archi\AppData\Local\Temp\technical_analysis_p0_audit\p0_evidence_20260828_route_status_refresh.json`）後重新開啟或重新載入更新頁；UI 不會自行掃描 TEMP。這份 refresh 若未同時指定 MOPS 季報 artifact，季報列顯示 `artifact_missing` 是預期的 fail-closed 結果，不代表其他 12 個來源的 probe 失敗。

快速更新排程會在 `latest_status.json` 旁以 append-only 方式保存 `data-update-status-history.v1` JSONL；每次真實執行會記錄 `running` 與 terminal status 的 run／時間／步驟摘要。預設 history 路徑為 `OUTPUT_ROOT/scheduled/data_update_quick/history.jsonl`，也可用 runner 的 `--history-path` 或 UI 的 `DATA_UPDATE_HISTORY_ARTIFACT` 指定。這個功能不會回放既有 latest status、不會把檔案 mtime 當成完成時間；既有環境的 history 缺檔會顯示「缺漏」，等下一次真實排程自然產生，不得手動複製舊結果補足。

快速更新的狀態邊界會先把 Phase 3C `BackfillSummary` 等 dataclass、路徑、日期與數值 wrapper 轉成 JSON-safe 結構，再寫入 latest status 與 history。單一步驟若回傳非原生 JSON 物件，不會使整輪停在「執行中」；終端 status 仍會發布，步驟結果的結構化內容也會保留在 artifact。

若 history 缺檔，先用下列唯讀命令確認 Windows task 是否真的存在：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_scheduled_task_registration.py `
  --output C:\Users\archi\AppData\Local\Temp\scheduled_task_status.json
```

輸出會列出 21 個預期 task（20 個 daily、1 個 weekly）的 available／missing 計數、安全摘要，以及本地 wrapper
manifest 是否存在、每個 task action 是否指向預期 `.cmd`；若 task 可用但 `Task To Run`
未出現，會另標示 action 尚未觀測，不能算 `configuration_ready`。它不會註冊或修改 task；若要
指定其他 checkout，可加 `--repo-root <path>`。也可把該 JSON 以 unified readiness 的
`--scheduled-task-status` 載入，讓 Update History lane 顯示
`scheduled_tasks_missing_or_unavailable:<available>/<total>`、wrapper 缺漏或 action mismatch。
若 task 缺失，需由 owner 在正確帳號下執行受控的
`scripts\scheduled\register_baldr_scheduled_tasks.cmd`，再觀察下一次真實 running／terminal
history；不可用舊 latest status 回填。
此 inspector 在解析參數前會設定 UTF-8 stdout／stderr，因此 Windows CP1252 主控台也能
正常使用 `--help` 與輸出繁中診斷；這只改善診斷工具顯示，不會改變 query-only 與不註冊 task
的安全邊界。

### 4.1.1 整體程式 readiness 盤點（唯讀）

若要一次確認目前各 Gate「在哪裡、卡在哪裡、下一步是什麼」，使用：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_program_readiness.py `
  --data-root <DATA_ROOT> `
  --output-root <OUTPUT_ROOT> `
  --training-as-of 2026-08-28T00:00:00+08:00 `
  --format markdown
```

需要載入已存在的證據時，再加上 `--p0-audit-json`、`--p0-license-evidence-json`、
`--approved-weekly-history-projection`、`--technical-performance-baseline` 與
`--broker-performance-baseline`。若要把 Direct/OOC 維護的容量結果一起納入
performance lane，另加 `--ml-direct-chain-status <ML_DIRECT_CHAIN_STATUS_JSON>`；
當 status 是 `blocked_insufficient_storage` 時，報告會保留
`direct_chain_storage_preflight_blocked`，只提示容量／保留策略，不啟動 worker。
這個 status 是一次執行的 terminal evidence，不是永久磁碟屬性。2026-08-29 cleanup 後，
較新的唯讀 retention inventory 已觀察 D free 約 `338.9 GiB`、`headroom_ok`；cleanup 前
`6.11/6.56 GiB` status 應標成 historical。不要手改舊 status；若只為刷新畫面，使用
`run_ml_direct_chain_maintenance.py --preflight-only`，不要呼叫一般 wrapper，因為 headroom
通過後一般 wrapper 會真正啟動 Direct/OOC rebuild。完成 preflight 後再重建 unified readiness。
若已建立效能 owner handoff，另加
`--performance-owner-packet <PERFORMANCE_OWNER_PACKET_JSON>`；報告與 UI 會顯示
`needs_named_owner_reviewer`／`ready_for_owner_review`、review lane 總數與待處理數，
但只作交接投影，不授予 production worker／fetch pool、Formal OOS 或清理權限。
若已有允許實際 host context 產生的 `runtime-environment-readiness.v1` 唯讀 artifact，
可再加 `--runtime-readiness-json <RUNTIME_READINESS_JSON>`；它只載入已核實的 Runtime
read model，不重新探測或修改正式 logger／Registry 路徑。schema 不符會 fail-closed，且
這仍不等同正式 Registry transaction／rollback proof。若要在不寫正式 Registry 的前提下
驗證目前正式 DB 的 schema 與 transaction 契約，可再加
`--runtime-registry-snapshot-probe <REGISTRY_SNAPSHOT_PROBE_JSON>`；它只載入由
`scripts\inspect_research_registry_transaction.py` 產生的 read-only source → TEMP clone
證據，不能把 clone proof 當成正式 ACL 寫入成功。
程式會固定顯示 P0、Evidence、Paper、Formal/ML、
Runtime、Update history、Performance 七個 lane 以及依序下一步；未提供的 artifact
會顯示 `waiting_for_external_input` 或 `action_required`，不會自行搜尋、回放、補歷史
或改接 prospective path。若要把獨立的 `data_freshness/latest_status.json` 一起投影，
可明確加入 `--freshness-status-path <FRESHNESS_STATUS_JSON>`；報告會分開列出
freshness status、`checked_at`、warnings／errors 與 read-only 標誌，不會用 freshness
結果掩蓋排程未註冊或 history 尚未累積。`update_history` 另外檢查 history JSONL
是否超過 8 MiB、是否有重複 record、terminal run，以及 latest status 與 history
最新 run 是否一致。

每個 lane 的「下一步」欄也會顯示 bounded 進度摘要，讓「已有機器證據」與「尚未通過治理／執行 gate」分開閱讀：P0 會顯示來源數、機器證據比例、`accepted／limited` 與 route 嘗試數；Evidence 會顯示 weekly／dry-run `已觀測／要求`、sidecar 中待人工審核的 `pending_human_review` 期數與 Formal credit 是否授權；Paper 會顯示 snapshot、benchmark、cost ledger 狀態、成本紀錄與 fills，避免只看到 `0` 卻不知道是 ledger 缺漏；Formal／ML 會顯示 owner-controlled input `ready／total`；Runtime、效能與更新歷史則顯示 host probe、canary／容量、排程與 freshness 摘要。阻擋原因會先顯示中文意義，括號保留原始 machine token，方便直接對照 log／artifact；這些只是 UI read model，不會改變任何 gate。

此命令是 query-only readiness projection：不建立資料夾、不寫正式 SQLite、不發網路、
不啟用 scheduler／broker；輸出 `partial` 也不代表 Formal credit、source acceptance、
Paper 成本後週報或平行 worker 已完成。若要保存報告，才另以 `--output <REPORT_PATH>`
指定明確的報告檔案。

若要在受控環境改用另一個已核准的 artifact，可設定 `DATA_UPDATE_STATUS_ARTIFACT`、`DATA_UPDATE_HISTORY_ARTIFACT`、`DATA_FRESHNESS_STATUS_ARTIFACT`、`TPEX_REFRESH_STATUS_ARTIFACT`、`MONTHLY_REVENUE_SNAPSHOT_CANDIDATE` 或 `MONTHLY_REVENUE_AVAILABILITY_CANDIDATE`；每個變數都必須是完整檔案路徑。未設定時使用上述固定出口，找不到時畫面會明示「缺漏／未設定」，不會自行搜尋相鄰目錄。

每日股價、大盤指數、產業指數、券商分點、技術指標、月營收，以及法人／信用／集保三個候選資料源分頁，都會在「檢查此資料源狀態」下方顯示同一份唯讀來源摘要；全域檢查完成後也會同步刷新這九份摘要。個別來源查詢失敗時只會將該來源標為異常，不會把其他來源卡片誤刷成錯誤。候選來源摘要仍屬 research-only，不代表正式評分或交易訊號。

若正式資料根目錄目前唯讀，來源狀態查詢仍會回傳 SQLite／Candidate DB 的實際結果；寫入 status manifest 失敗只會留下 `status_manifest_write_skipped:<error_type>` 警告，不會把可讀取的資料源誤標成查詢失敗。

若狀態卡顯示黃色「待更新」且文字含 `讀取模式：immutable_fallback`，代表 Windows 當下無法取得一般 SQLite read lock，系統使用最後已提交的 immutable 唯讀快照；這不是資料已確認最新，請先停止其他 SQLite 寫入工作，再按「檢查數據狀態」重查。SQLite 資料檢視頁的頁首也會顯示「immutable 唯讀快照，可能非即時」。

更新中的進度只代表目前這一輪工作；TWSE 批次下載會把子程序逐日期輸出映射到外層區間，TPEX 區間抓取也會逐日期回報，技術指標等其他子流程則映射到各自外層區間，進度不會倒退。每日資料合併會回報目前讀取的檔案與整合檔寫入批次；若增量模式沒有較新的 CSV，會明確顯示「資料已是最新」並標記為 no-op，不把它誤報成重新合併，也不會因 no-op 先建立整合檔備份；只有確認有新資料、即將原子提交時才建立備份；SQLite CSV 匯出會先以 query-only 查詢取得預估筆數，再回報已處理筆數。若來源端沒有可量化進度，畫面會保留目前階段文字，不把等待時間誤宣稱成百分比。最終「刷新資料狀態」若失敗，會停在未完成狀態，不會先顯示 100%。CSV、SQLite、合併、技術指標與匯出等寫入型背景工作同一時間只允許一個；若畫面提示「背景工作進行中」，請等待完成後再重試。唯讀的資料源狀態／詳情檢查可以在寫入期間執行。
寫入型背景工作啟動後，進度列下方會出現「取消目前工作」按鈕。按下後會送出合作式取消，TWSE 目前 API／batch 請求會先安全收尾，TPEX、券商分點與技術指標則在目前日期、檔案或 SQLite 寫入邊界停止；不會呼叫 `QThread.terminate()`，也不會截斷半筆 SQLite／CSV 寫入。畫面會顯示「已送出合作式取消」，待 worker 自然結束後恢復按鈕；已完成的部分會保留，請再按「檢查數據狀態」確認實際日期與筆數。
大型每日資料／券商分點合併與 CSV 匯出目前會先完成正在進行的安全操作，再套用取消；這段期間按鈕會保持停用並在日誌顯示等待收尾，不代表資料已回滾。這是目前仍保留的長任務限制，避免在檔案重建或 SQLite 交易中途切斷。
更新完成或未完成的訊息會同時列出 SQLite 同步狀態、來源、目標 table、寫入筆數與錯誤／取消原因；不必從日誌中的自然語言猜測 SQLite 是否真的寫入。
全域「檢查數據狀態」與 SQLite 個別來源詳情共用 daily reference freshness；市場指數、產業指數或技術指標的最晚日期落後每日股價時會標成 `lagging`／「待更新」，不會因為表內仍有舊資料就顯示「正常」。月營收則依公告 `available_date` 與期別判讀，不能拿每日交易日直接比較。

CSV 送入 SQLite 前會先在寫入用副本上正規化欄位與識別值：日期欄接受 `日期`／`date`／`Date`／`trade_date`／`decision_date`，股票代號接受 `證券代號`／`股票代號`／`stock_code`／`stock_id`／`code`／`ticker`，股票名稱接受 `證券名稱`／`股票名稱`／`stock_name`／`name`；日期轉為 `YYYYMMDD`、股票代號補足四碼。這不會改寫 raw CSV 或原始 DataFrame；缺必要欄位時仍 fail-closed 跳過並在結果／日誌保留原因。

### 4.2 快速更新與安全更新

| 模式 | 內容 | 適用情境 |
|---|---|---|
| 快速更新（跳過大型合併） | TWSE / TPEX 每日股價與券商分點會依 UI 最近範圍補齊，預設為結束日前最近 10 個工作日，並直接增量同步 SQLite；會保留已下載的日檔 CSV，但跳過 `stock_data_whole.csv` 與券商分點 `merged.csv` 的大型重寫。 | 日常盤後更新、只需要讓 SQLite 查詢與技術指標追上最新資料。 |
| 安全更新（完整 CSV + SQLite） | 依 UI 最近範圍補齊 TWSE / TPEX / 大盤 / 產業 / 券商分點，預設為結束日前最近 10 個工作日；完成後重建每日股價大表與券商分點 `merged.csv`，再同步 SQLite。 | 資料修復、備份完整性檢查、需要確認 CSV 歷史資料庫也完整時。 |

#### V4 freshness 與官方交易日閉環（2026-09-08）

每日更新與 freshness probe 共用 `OfficialTradingCalendar` 的 TWSE `holidaySchedule`／temporary closure evidence；不再以 weekday、`Date_table.csv` 或 `MAX(date)` 猜交易日。盤前尚未到下一個官方 session 的資料是「等待公告／等待來源」，官方 session 已結束仍缺少才是「過期」；官方日曆無法解析時 fail-closed，不修改日期、不 forward-fill 行情。

唯讀 probe 會檢查最近 10 個官方交易 session、TWSE／TPEx raw 與 SQLite 的 row count／code set、market／industry／broker 覆蓋，以及 technical eligible coverage。狀態 token 為 `current`、`expected_wait`、`stale`、`failed`、`partial`、`not_applicable`、`unknown`；`candidate` 只代表已取得候選，不代表正式 mapping／SQLite 已套用。probe 的 `latest_status.json` 由既有 `UpdateService.check_data_status` 唯讀投影到更新頁，不會因檔案存在而把缺月／缺季資料標為正常。個股報告只採用與查詢日、同一 `data_root`／SQLite 綁定的 receipt；receipt 缺失、損壞、日期或資料根不符時保留 `unknown`，不以資料日早於查詢日猜成過期。

狀態頁消費 receipt 時還會重驗 `DATA_ROOT`、SQLite／Candidate DB 路徑、來源實際期別、`calendar_cutoff_local` 與 `calendar_cutoff_timezone`。Freshness 的每日發布截止為 **04:30 America/Los_Angeles**（台北夏令期間 19:30、冬令期間 20:30），不是台北 04:30。檢查與查詢必須位於同一發布週期：洛杉磯午夜到 04:30 前仍屬前一週期，跨台北午夜本身不使收據失效；一旦跨越下一個洛杉磯 04:30，就必須重新執行唯讀 probe，即使來源日期沒有變動也不能沿用舊的 `expected_wait`。新收據明示 IANA 時區；舊收據僅在精確辨識為本專案既有 Freshness task 且符合其固定時區契約時相容，未知或不符時區要求重驗。合法收據可投影其明確 `stale` 狀態，consumer 不自行推定 current／stale。`unknown`／`needs_revalidation` 時，先執行既有唯讀 freshness probe（或觸發其既有排程）並查看 log、目前 DB 日期與新收據，再按「檢查數據狀態」讀回。此按鈕只讀既有狀態，不會啟動 probe；不要手改 receipt 的時區、時鐘或日期。

「取消目前工作」是合作式停止，worker 會在日期、檔案或 transaction 安全邊界接收取消。已安全提交的 CSV／SQLite 部分結果可能保留；取消不會強制終止 QThread，也不會把已保留資料宣稱成全範圍更新成功。畫面若同時有真正的 parser／writer exception，錯誤仍保留為 failed；工作結束後先按「檢查數據狀態」，再依失敗步驟決定是否重試。

三大法人、信用交易與 TDCC 是獨立 candidate lane。TDCC 只代表官方提供的最近每週最後營業日資料，不支援用最新 response 冒充指定歷史日；rows 與成功 checkpoint 原子保存，重跑會按自然鍵冪等核對。中斷後先做唯讀 reconciliation；完全相同的已提交列可安全略過／重試，衝突、缺列或部分 transaction 不得視為完整成功，不要手工刪 checkpoint 來強迫重抓。

合法假日區間沒有官方交易日會回報成功 no-op，不呼叫 API；HTTP、timeout、schema、parser、mapping 或 SQLite transaction 失敗會保留 failed／diagnostic。market／industry 同步只替換驗證過的 date keys，不會以整表 DELETE 取代增量交易。

產業指數的這條 capture 路徑只保存 TWSE `MI_INDEX type=IND` 回應中符合既有 table title 與產業名稱篩選條件的列；它不證明指數成分股、個股產業 membership、上市／上櫃分類，也不代表 TPEx 或興櫃覆蓋。原始 response receipt 的 UTC 時間是本機讀完 response body 的時間，官方 `available_at`／`published_at` 保持 unknown，`historical_pit_eligible=false`。回應本身沒有可核對日期、日期與請求日不一致，或與最近較早 CSV 日期的名稱集合不同時，該日標為 degraded、等待人工確認且不改寫 CSV；不以同日舊列補齊新 response。只有本次 capture 綁定日期會進入明確 date-scoped SQLite 替換；最終 projection commit marker 要等 CSV 與 SQLite 六欄 rowset 獨立 readback 一致後才建立。批次只有在 marker 有效且目前 CSV／SQLite scoped rowset 仍相符時才可 verified skip；沒有 marker 或 capture attempt 的舊 CSV 日期保留為 unknown legacy rows，不宣稱本次已更新；只有本次請求日期落入這種 legacy skip 而沒有新的 capture 時，更新步驟回報 unknown/degraded，不會當成成功更新。請求範圍外的舊日期仍是 unknown，但不會阻擋當日 verified no-op。已有 degraded／未完成 capture artifact、尚無有效 marker 的日期會重試。若批次只有部分日期通過，capture 日期可完成 scoped projection，但 updater 結果與 marker 保留 partial／失敗日期；quick scheduled runner 會在終止前只同步本次已驗證 capture 的日期一次，仍將整體 run 標為 failed、保留失敗日期並停止後續步驟；同步失敗時沿用 `UpdateService` 的 CSV／SQLite before-image compensation。此分支不會改走舊 CSV 整份 fallback。零 capture 的 updater 後續同步仍會拒絕以舊 CSV 做整份 fallback。下游 IndustryMapper observation 仍只描述 mapper 實際讀取的 current rows，沒有帶入 capture receipt／projection marker ID 或本機 capture time；不能由此推導 official availability 或 PIT。這個 marker 不提供官方公告時間或歷史 PIT 證據。

月營收 MOPS snapshot 與公告／可得日 mapping 是兩個不同 gate。snapshot 可用時仍須先跑 availability validator／merge preview，再由 owner 確認後執行 `scripts/apply_monthly_revenue_recovery.py`；正式 apply 前要有 task-specific DB／mapping backup、journal、WAL transaction 與 Direct heavy-chain lock 狀態讀回。季報沒有 availability map 時顯示 `unknown`，不能用月營收或 legacy aggregate 代替。

既有 V2.2 weekly collection 成功後，排程另預設呼叫 `scripts/fetch_mops_statement_availability.py --last-complete-taipei-7-days`，保存 MOPS Ezsearch 公告查詢原文與研究狀態；此路徑只收公告可得性，不收財報數值，也不代表季度 numeric dataset 已齊。該 legacy artifact 的 `production_scheduler_allowed=false` 是 production consumer／training／Formal 資格旗標，不會關閉這個 research acquisition；查詢排程狀態以每次 run 的 `weekly_research_status.json` 為準。設定 `BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=0` 可關閉此研究收集。此研究 capture 會輸出公告事件與研究用 availability CSV／candidate，但不會建立已接受的正式 mapping 或寫正式 DB；正式使用仍須通過對應來源與 maturity gates。

TWSE 補檔遇到平日休市（例如颱風停市）時，只有在至少一個官方查詢型別明確回覆「沒有符合條件的資料」且沒有任何成功資料時，才會標記為「官方無交易資料日」並略過。HTTP 錯誤、逾時或無法辨識的回覆仍保留為更新失敗；更新結果會保留各查詢型別的 HTTP / API 狀態與實際日期，方便後續診斷。

快速更新仍會更新必要的日檔 CSV，因為 SQLite 同步以這些日檔作為可追溯來源；速度優勢主要來自跳過大型合併檔重寫。最近 10 個工作日可涵蓋使用者約兩週才開一次程式的常見情境；若間隔更久，請改用個別資料來源日期範圍或安全更新補齊。若近期資料已存在，系統會先用 CSV / SQLite 判斷並跳過網頁抓取。

一鍵更新會先檢查更新前總覽。若任一核心資料源的狀態 payload 明確是 `error`／`failed`／`exception`，畫面會顯示「已停止寫入」並不啟動任何下載、合併或 SQLite 寫入；請先依失敗資料源的錯誤訊息排除資料庫或來源問題，再重新執行。`lagging`、`empty`、`unavailable` 是資料可用性診斷，不等同於這個前置寫入阻擋，但最後狀態刷新仍必須通過才會顯示更新完成。

安全更新的資料防護原則：
- 狀態檢查必須是唯讀；券商分點 registry 不會因狀態檢查自動修復或寫回。
- SQLite 同步只從本次已產生或已合併的 CSV 結果寫入資料庫，不會反向覆蓋 CSV；每日股價同步採日期範圍替換，避免清空未碰到的歷史資料。
- 備份檔只保留在 `meta_data/backup/`，同一來源同一天只留最新一份，且最多保留最新 5 個日期版本，降低大型 CSV 備份對硬碟的壓力。
- 大盤指數若 TWSE API 失敗而使用 yfinance 備援，只接受目標日或目標日前最近交易日資料；不使用目標日之後的資料補寫。
- 技術指標計算一律使用 `TWStockConfig` 解析的資料路徑，不使用硬編碼正式資料根目錄。

### 4.3 個別資料來源

左側可選：

- 每日股價
- 大盤指數
- 產業指數
- 券商分點
- 技術指標
- 月營收
- SQLite 資料檢視

另有「三大法人」、「信用交易」、「集保股權」與「自動排程狀態」四個唯讀治理頁。

- **三大法人與信用交易**：目前屬於 Phase 3C 候選研究資料 (Candidate Data)。可使用獨立受控的歷史回補 CLI 腳本（`scripts/update_phase3c_candidates.py`），依據具官方證據的台股交易日進行斷點續跑匯入。apply 必須明確指定位於 `DATA_ROOT` 外的 Candidate DB；例如 `D:/Min/Python/Project/FA_Data_candidate/phase3c_candidate.db`。絕不寫入或覆寫正式資料庫 `twstock.db`。UI 只會讀取 `PHASE3C_CANDIDATE_DB_PATH` 指定的 Candidate DB，並顯示其筆數、最早/最新日期與 checkpoint 覆蓋率；Windows process environment 尚未刷新時，會唯讀採用同名 HKCU 使用者環境設定。兩者都未設定時仍不猜測路徑，也不將正式 DB 當成候選資料。
- UI 的 Candidate status read model 會以 SQLite URI `mode=ro` 並啟用 `PRAGMA query_only=ON` 開啟明確指定的 Candidate DB；即使目前只執行 SELECT，也不允許狀態查詢意外建立寫入連線。結果仍標示 `formal_records=0` 與「候選研究資料，不參與評分或投資決策」。
- **集保股權 (TDCC)**：目前官方 OpenData 端點 (`id=1-5`) 僅提供最新單週公開資料，不支援歷史多日期輪詢回補。加入 `--include-latest-tdcc` 時，系統只匯入 payload 自帶資料日的最新週 snapshot；例如在 2026-08-13 查詢時，官方最新資料日可仍為 2026-08-07。歷史期別仍明確標示為 `BLOCKED_NO_HISTORICAL_ENDPOINT` / `PARTIAL`，不會把執行日偽造成資料日。
- Phase3C 的 Quick／UI range updater 使用同一個官方日曆。明確休市才安全跳過；`BLOCKED_CALENDAR_UNKNOWN` 表示日曆尚未解析、需要重試，不能列為完成或休市。單日維護可加 `--calendar-cache-path output/paper_execution_eod_replay/calendar_cache`；指定的年度快取必須通過來源／hash 驗證並涵蓋請求年度，明確快取缺失時會阻擋，不轉而上網猜測。Quick 每週一另取得一次 TDCC 最新週 snapshot；其他日仍依每日來源更新，不造逐日 TDCC 歷史。
- Freshness 的月營收／季報 expected period 是通用申報期限基線：月營收以次月 10 日、Q1–Q3 以季末後 45 日、年報以次年 3/31 計算；週末期限順延至週一，期限當日仍可申報，次日才切換。非週末國定假日、特殊會計年度、金融／外國公司例外與每家公司實際公告時間另需驗證，不能把 aggregate stale 解讀成每家公司均已逾期。最新期別有 row 仍不足以證明全公司覆蓋或歷史 PIT；季度 row 只代表期別存在時顯示 `partial`。依據為[證券交易法第 36 條](https://twse-regulation.twse.com.tw/TW/law/DOC01.aspx?FLCODE=FL007009&FLNO=36)與[交易所公告的公司例外／週末順延實例](https://www.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d697fc438f01987eedfea50228.pdf)。
- TDCC freshness 依最新已完成交易週的最後官方交易日判讀；前一週資料可在後續兩個官方交易日內列 `expected_wait`，更早的多週資料仍列 `stale`。兩個交易日是本系統保守等待政策，**不是官方公布的發布期限**；官方日曆未知時列 `unknown`。各狀態保留資料期、真實可得／觀測時間、來源版本與範圍未驗證診斷，不把週資料變成每日資料。[TDCC 的週資料定義](https://www.tdcc.com.tw/portal/zh/smWeb/qryStock)
- TDCC 最新週更新先查既有官方 CSV，失敗才查已登錄 OpenAPI `https://openapi.tdcc.com.tw/v1/opendata/1-5`。兩路均驗完整 1–17 級與嚴格整數，16／17 級僅作完整性核對，分布指標仍由 1–15 級產生；OpenAPI 回應上限為 16 MiB。來源版本分開保存，資料日只取 payload；缺官方公告時間時留空，以本次取得完成時間記錄可觀測時點，不補成歷史 PIT。TPEx 信用交易舊明細失敗才查已登錄 margin OpenAPI，必須同時有 TWSE 與 TPEx 完整市場且日期精確相符；兩路皆失敗仍待重試，不省略市場或補零。
- Phase3C CLI 成功或合法無工作回傳 0；尚有 retryable failure／日曆未知回傳 2，詳細結果以 summary 各來源統計判讀。Paper EOD 僅在 typed candidate／weekly policy、期間與來源版本契約完整時，將 TDCC 列為非 EOD 依賴並保留完整診斷；失敗、未來日期或畸形 metadata 仍阻擋，其他必要來源須符合原門檻。
- **排程狀態**：只讀取最近狀態紀錄，供人工判讀背景工作是否曾執行；它不授權啟用 production scheduler，也不代表資料已完整。按「檢查此資料源狀態」會重新彙整 `OUTPUT_ROOT/scheduled/*/latest_status.json`，顯示核心工作就緒數、正常／受控／需處理／不可用數與逐工作診斷；下方 raw JSON 也會同步刷新，不會只停留在開頁時讀到的舊檔。
- 排程狀態的推薦詳情另顯示「工程執行狀態」、研究用途與 canonical cohort 分類：可用候選、策略排除、缺資料、來源品質問題、其他未判定。只有同一推薦 ID、已驗證 payload／index 與 typed cohort 才計數；缺 canonical proof 時顯示未確認，不以 0 掩蓋。已有 source warnings 會保守列來源品質問題，僅已知流動性／無策略訊號排除且 metadata 相符才列策略排除；eligible 與 coverage 重疊時每檔只計一次。原始 quality missing／degraded 統計仍另列，不改原 cohort hash 或篩選門檻；候選數、執行 passed 與資料品質都不是勝率或正式 Advice 授權。

每日股價、大盤、產業、券商分點操作：

1. 設定「結束日期」；可用日曆選取，或按「今日」一鍵帶入今天。
2. 設定「最近範圍」；系統換算出的開始日期會納入下載與缺漏檢查範圍。
3. 先按「檢查此資料源狀態」。
4. 按「手動下載此資料源」會依資料源下載或補齊指定日期範圍的原始資料。
5. 每日股價手動下載會同時處理 TWSE 與 TPEX：TWSE raw CSV 寫入 `DATA_ROOT/daily_price/YYYYMMDD.csv`，TPEX official daily close quotes 寫入 `DATA_ROOT/daily_price_tpex/YYYYMMDD.csv`，完成後同步 SQLite `daily_prices` 並觸發技術指標增量更新。TWSE 會先查 `MI_INDEX type=ALL`，若該 type 回傳錯誤或查無資料，會 fallback 到 `ALLBUT0999` 並以欄位辨識個股交易表。執行「合併每日股價」時，`stock_data_whole.csv` 也會同時納入這兩個日檔目錄。
6. 券商分點下載後，還要執行對應的「合併」才會寫入分析資料庫。

每日股價與券商分點按「檢查此資料源狀態」後，結果會顯示在該資料源頁面內的摘要列，包含最新日期、筆數、SQLite / CSV 狀態與缺漏提示；下方日誌只保留細節，不是唯一判讀入口。

按主頁的全域「檢查數據狀態」後，該摘要列也會同步刷新；若某個 payload 缺漏，卡片與頁面內文都會顯示「尚未檢查／異常」，不沿用上一輪數字。

每日股價的「強制重新合併所有每日股價」屬高風險維護操作。系統會先顯示二次確認對話框，按「取消」不會執行，只有按「確認強制合併」才會重建衍生合併資料；此流程不應亦不會修改或刪除 `DATA_ROOT` 底下的 raw CSV 原始檔。

若開啟「SQLite 資料檢視」時資料庫尚不存在、損毀或沒有讀取權限，頁面會保留並顯示「SQLite 不可用」；這是唯讀診斷結果，不會自動建立空的 `twstock.db`。請先確認 `TWStockConfig.db_file` 指向正確資料庫，再重新按「載入數據與結構」。

若「檢查數據狀態」顯示 SQLite `unavailable`，代表設定的 DB 尚未存在或不可讀；UpdateService 也不會為了顯示狀態而建立空資料庫，應先完成受控資料初始化／同步，再重新檢查。

若 TWSE 每日股價 batch 回報任何真正 `failed_dates`，該每日股價步驟會視為失敗並停止後續流程，避免 UI 顯示完成但實際缺個股日價；單一來源流程也不會再呼叫 TPEX、SQLite 同步或技術指標。若沒有任何成功資料，至少一種查詢型別必須精確回覆「很抱歉，沒有符合條件的資料！」，且所有其他嘗試只能回覆同一官方文案或 HTTP 307；符合此條件時，日期才會列在 `no_data_skipped_dates`（同時保留於 `skipped_dates`），快速更新會顯示「TWSE 上游查無資料，已跳過日期：YYYY-MM-DD」警告並繼續 TPEX / SQLite / 技術指標流程；這種安全跳過不是成功下載，也不等同於資料完整。HTTP／timeout、JSON／欄位解析失敗、「查詢日期大於今日」或其他非完整的「查無資料」文案仍是 `failed_dates`，不會被當成休市日。若 TPEX endpoint timeout、Cloudflare/HTTP 阻擋或部分日期失敗，UI 會繼續已成功的 TWSE / SQLite / 技術指標流程，但最後會標示「未完整」並列出 `TPEX 每日股價缺少日期：YYYYMMDD`；這代表需要重測或補跑缺漏日期，不代表 TWSE 資料也失敗。區間結果同時保留 `failure_diagnostics`，逐項記錄 `requested_date`、`phase`（`requested`／`fallback`／`range`）、`result_requested_date`、`source_date`、來源 `diagnostic_count`、row／skipped counts、截斷至 512 字的 `message` 與 `message_truncated`；top-level `diagnostic_count` 是來源診斷數總和，項目數不等於 count。若在來源結果後取消，或後續日期拋出 exception，已收的 per-date diagnostics 仍會保留；這些是 bounded 區間結果／receipt context，不是原始 response bytes，也不能單獨追認 API 根因。今日 raw 缺漏應以 freshness 的明確 token 與原始 log 交叉判讀，不以 `failure_diagnostics` 猜測官方 coverage。若只有 TWSE 成功，`daily_prices` 當日可能只含上市股票，技術指標與全市場判讀應等 TPEX 缺口補齊後再視為完整。

本輪 2026-09-18 的 raw 缺漏由 freshness 明示為 `tpex_daily_price_file_missing:20260918`；13:00:25–27Z 的獨立官方 probe 對 after-trading 與 OpenAPI 各發一次 GET，兩次都回 HTTP `403` 的 Cloudflare HTML，`parse_result.status=not_attempted_http_status`。這只證明 probe 時點的 HTTP 阻擋，不能追認早上排程的根因；今日或其他日期仍應以 freshness token 與原始 log 交叉判讀，不以 `failure_diagnostics` 猜測官方 coverage。完整 source-gap readback、probe raw 與修補限制見 [TPEX source gap diagnostics QA](../06_qa/TPEX_SOURCE_GAP_DIAGNOSTICS_2026_09_18.md)。

若已由合法官方來源保存一份 afterTrading/otc raw response 與同源 capture metadata，可用既有 `scripts\backfill_tpex_daily_prices.py` 做單日受控補入。先以 dry-run 預覽：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_tpex_daily_prices.py `
  --source-raw <OFFICIAL_TPEX_AFTER_TRADING_RAW> `
  --capture-metadata <CAPTURE_METADATA_JSON> `
  --date YYYY-MM-DD --required-symbol 1569 `
  --data-root <ISOLATED_OR_DATA_ROOT> `
  --output-root <CUSTODY_OUTPUT_ROOT> `
  --db-file <DATA_ROOT>\sqlite\twstock.db `
  --backup-dir <DATA_ROOT>\meta_data\backup
```

raw 模式只接受 HTTPS `www.tpex.org.tw/www/zh-tw/afterTrading/otc`、production 的西元日期參數與目標行情 table，會保留 response hash、實際 `captured_at`、原始 receipt 與 bounded parser diagnostics；預設不寫 custody、CSV 或 SQLite。只有在 CSV／DB conflict、來源 provenance、日期／1569、schema 與 hash 全部 preflight 通過後，才可加上 `--apply --confirm apply-tpex-daily-price-backfill`。DB 會先建立 retained backup，CSV 與 custody 使用 create-only 寫入，完成後再以唯讀 readback 核對 1569 的 OHLC／成交股數。第三方來源、OpenAPI payload、不同內容的既有日檔或資料列都會停止。這類晚取得的歷史補入標示 `not_proven_by_after_close_capture`、`formal_source_contract_eligible=false`，不能回填舊 failed receipt，也不能授予 natural／calibration credit；補入後仍須重新檢查來源 receipt 與 freshness。

每日股價分頁另有「背景補齊 TPEX + 技術指標」與「檢查背景任務狀態」。背景任務不會先強制跑 TWSE 全量，也不會強制全量重算技術指標；同步 SQLite 後會比對每日股價與技術指標最新日期，若技術指標已追上每日股價，狀態會顯示 skipped。每日股價頁面內另有可見狀態列，會顯示 `尚未啟動`、`執行中`、`完成` 或 `失敗` 及最後更新時間；狀態檔無法建立時，系統會停止啟動背景程序並顯示原因，不讓畫面留下無法追蹤的假執行狀態。狀態檔位於 `DATA_ROOT/meta_data/tpex_full_refresh_status.json`；若狀態顯示 `running`，請用狀態查詢確認進度，不要重複啟動第二個背景任務。日期範圍同步若發生例外會寫入下方日誌，應先處理該錯誤再開始下載。

#### 背景工作與安全關閉

資料更新、推薦／回測報告匯出、每日決策與主力流向等背景工作執行時，關閉主程式會先送出**非阻塞合作式取消**。Workbench 的首次載入／重新整理會在背景 worker 讀取唯讀 DTO；Research Console 到第一次切入「研究證據」分頁才開始讀取。SQLite 長查詢與有界 artifact 讀取會檢查取消狀態。系統不會對持有 SQLite、檔案或報告暫存資源的工作呼叫 `QThread.terminate()`，也不會在 UI 主執行緒無期限 `wait()`。若工作或 TPEX 獨立背景程序仍未結束，視窗會保持開啟並提示「已暫停關閉」，每隔數秒更新等待時間與狀態，完成後會自動關閉；按一次關閉即可，不必反覆重按。唯讀載入取消不會把資料標為成功；有 last-good DTO 時仍會保留並標明狀態。

背景 worker 的結果 signal 可能早於原生 Qt thread return 抵達 UI；系統會保留 worker 參考直到 native `QThread.finished()`，且把過早的 `deleteLater()` 延後到 thread 停止後，避免 queued UI cleanup 釋放仍在執行的 Qt thread。若按下更新頁的取消按鈕，這個生命週期保護會繼續等待自然收尾；取消完成前不要切換成「更新成功」的人工判讀。

若主視窗仍可回應，但顯示「已暫停關閉」，請先等待背景工作的合作式取消與安全收尾；狀態列會持續更新，完成後自動關閉。若視窗在按下關閉後完全沒有回應，請保留 `DATA_ROOT/logs/ui_qt_crash.log` 中最後一個 `DIAGNOSTIC` 階段與時間，並對照 Windows 事件檢視器的 Application Hang／WER；目前關閉記錄會標示事件迴圈、取消等待及 Qt deferred-delete drain 階段，且不寫入工作參數或完整路徑。診斷記錄無法寫入時不會阻止正常關閉。

針對研究工作台與 Evidence review 這兩個已修頁面，頁面被釋放後，延遲更新與排程狀態回呼不再存取該頁面的畫面。

這個保護不會把未完成更新標成成功，也不會刪除 raw CSV、SQLite 或既有報告。若工作長時間沒有自然結束，應先保留 log／status 後依對應資料源的排錯流程處理，不要以強制結束程序取代資料一致性檢查。

桌面 App 直接啟動時會在載入 Qt 前啟用持久化 crash diagnostics，檔案固定為 `DATA_ROOT/logs/ui_qt_crash.log`。`SESSION_START` 後若沒有對應的 `SESSION_END`，或結尾為 `clean_shutdown=false`，代表程序未走完無例外的正常關閉；Python 主執行緒、背景執行緒與已被啟動邊界攔下的例外會保存 traceback，native fatal fault 則由 `faulthandler` 保存所有執行緒堆疊。每個 session 也會記錄 executable、argv0、cwd、parent PID 與 DATA_ROOT（不記錄完整環境或秘密），方便把 WER 對回實際 entrypoint。Windows 事件檢視器的 `RADAR_PRE_LEAK_64` 是記憶體壓力／疑似洩漏預警，不可單獨當成實際 crash；需與這份 log、WER Application Error 或 dump 一起判讀。

`QApplication.exec()` 返回後，production entrypoint 會在 QApplication 仍有效的 GUI thread 內排空已關閉主視窗的 Qt `DeferredDelete`，再交回 Python interpreter。這個 teardown 不會同步等待背景 worker，也不會以 `terminate()` 或 End Task 代替合作式取消；若主視窗關閉後仍沒有 `SESSION_END`，仍應依上述 diagnostics、WER 與背景狀態收據排錯。即使看到 `SESSION_END clean_shutdown=true`，也不能單獨證明 native process 已正常退出；仍須對照 OS exit code、owned process tree 與實際 PID 是否殘留。

關閉驗證可在 repository root 分別執行 `.\.venv\Scripts\python.exe scripts\qa_validate_ui_natural_shutdown.py --scenario slow_workbench_read` 與 `.\.venv\Scripts\python.exe scripts\qa_validate_ui_natural_shutdown.py --scenario slow_research_console_read`。測試以合成 500ms 唯讀 stub、Qt offscreen 與臨時資料路徑確認事件循環仍能回應，並核對自然退出；這不是正式資料庫負載或 Windows 前景視窗操作的替代驗收。

啟動訊息含有繁體中文；`ui_qt/main.py` 會在直接或被其他 launcher 呼叫的 entrypoint 先將 stdout/stderr 嘗試切換為 UTF-8，並以 `backslashreplace` 處理不允許 reconfigure 的 console。這避免 Windows cp1252 console 在建立 `QApplication` 前因 `UnicodeEncodeError` 退出；若 stream 不可調整，會 fail-soft 繼續啟動，真正的例外仍由上述 diagnostics 記錄。

`config.log`、`db_manager.log`、`data_loader.log`、`market_data_process.log` 或 `technical_calculation.log` 若因唯讀環境、短暫檔案鎖或權限問題無法建立，核心服務會降級為 console-only logging，不再只因診斷檔不可寫就中止 App 啟動或資料計算。這只放寬 log sink；SQLite、來源資料與任何正式 gate 的權限並未放寬。

券商分點同步會保存 `trade_type`，同一分點 / 股票 / 日期可同時有買超與賣超 rows。若舊 SQLite `broker_flows` 還是三欄主鍵，下一次同步券商分點時會先備份 DB，再把唯一鍵升級為 `(分點名稱, 證券代號, 日期, trade_type)`。

券商分點下載在 `force_all=false` 時會先檢查日檔 CSV 與 SQLite `broker_flows`。SQLite 檢查會同時比對分點顯示名稱與系統 key，避免 DB 已有資料卻仍啟動 MoneyDJ / Selenium 重新抓取。

券商分點下載仍採保守序列流程，但進入 MoneyDJ 前會先用每日股價日檔或 SQLite `daily_prices` 檢查目標日期是否有行情證據；無行情證據的日期會整天跳過，不會讓每個分點各自重試。MoneyDJ 正常頁面會優先使用 HTTP fast path 直接抓取 Big5 HTML，只有 HTTP 失敗或解析不到資料時才退回 Selenium fallback。預設請求間隔為 0.5 秒；若一次更新約 40 個分點耗時較長，先確認是否已有 CSV / SQLite 既有資料可跳過。本版尚未支援 5 或 10 worker 並行，避免對 MoneyDJ 造成過高併發與站方阻擋風險。

若需要量測技術指標本身而不觸發寫入，可使用：

```powershell
.\.venv\Scripts\python.exe scripts\qa_technical_indicator_latency.py `
  --technical-dir D:\Min\Python\Project\FA_Data\technical_analysis `
  --stocks 0050 2330 3008 --rows 500 --runs 3
```

此 probe 只讀取明確指定的既有指標 CSV，輸出 CSV read／calculate latency，並固定
標示 `parallelism_enabled=false`、`observed_worker_count=1` 與
`single_writer_required=true`。它不建立備份、不寫 SQLite，也不能用來宣稱全市場
更新已完成多核心化；完整規劃與 acceptance criteria 見
`docs/06_qa/DATA_UPDATE_PERFORMANCE_BASELINE_2026_08_28.md`。

若要量測 raw stock CSV 的全批次記憶體流程，可使用：

```powershell
.\.venv\Scripts\python.exe scripts\qa_technical_indicator_full_batch.py `
  --stock-data-file D:\Min\Python\Project\FA_Data\meta_data\stock_data_whole.csv `
  --stocks 0050 2317 2330 2454 `
  --min-rows 30 --max-rows-per-stock 120 --runs 1 `
  --output-json <TEMP_OUTPUT>
```

此 probe 會完整讀取明確 CSV，再在記憶體中依股票分組、呼叫
`calculate_all_indicators` 並 concat 結果；不呼叫 writer、不建立 backup、不寫
CSV／SQLite，也不啟用 worker。`--max-rows-per-stock` 只限制本次計算的樣本，不能
當成正式指標回補設定。輸出會分開列出 read／normalize／group／calculate／aggregate
耗時、row count、失敗代號與 `write_attempted=false`；它仍不能證明 CSV serialization、
backup 或 SQLite contention 已通過，後續需在 isolated staging 另做 write probe。

若要在不碰正式資料的前提下量測 CSV serialization、既有 SQLite writer 與 single-writer contention，可使用：

```powershell
New-Item -ItemType Directory -Path C:\Users\archi\AppData\Local\Temp\technical_analysis_write_probe_stage -Force
.\.venv\Scripts\python.exe scripts\qa_technical_indicator_write_probe.py `
  --stock-data-file D:\Min\Python\Project\FA_Data\meta_data\stock_data_whole.csv `
  --staging-root C:\Users\archi\AppData\Local\Temp\technical_analysis_write_probe_stage `
  --protected-root D:\Min\Python\Project\FA_Data `
  --protected-root D:\Min\Python\Project\FA_Data\output `
  --confirm-write-probe --stocks 0050 2330 --min-rows 30 --max-rows-per-stock 120 `
  --output-json <TEMP_OUTPUT>
```

這個 probe 必須明確傳入既有 staging root、至少一個 protected root 與 `--confirm-write-probe`；
未確認時不建立任何檔案，staging root 位於 protected root 內也會 fail-closed。確認後只在
staging 的 ephemeral 子目錄寫入逐股／合併 CSV 與 SQLite，結束後自動清除；正式 raw CSV
以前後 SHA-256 驗證未變更。輸出會列出 CSV／SQLite 各 stage 的耗時、row count、hash、
`database is locked` contention、serialized retry、cleanup 結果與
`production_write_attempted=false`。這只能證明隔離 writer 邊界，不代表 production
writer 已改造或授權提高 worker 數；在 broker rate-limit、取消／重試與 bounded worker
acceptance 通過前，技術指標仍維持單一 worker。

若要把真正的 `TechnicalIndicatorCalculator` 放進受控 process pool 做 staging throughput
驗收，可使用：

```powershell
New-Item -ItemType Directory -Path C:\Users\archi\AppData\Local\Temp\technical_analysis_process_pool_stage -Force
.\.venv\Scripts\python.exe scripts\qa_technical_indicator_process_pool.py `
  --stock-data-file D:\Min\Python\Project\FA_Data\meta_data\stock_data_whole.csv `
  --staging-root C:\Users\archi\AppData\Local\Temp\technical_analysis_process_pool_stage `
  --protected-root D:\Min\Python\Project\FA_Data `
  --protected-root D:\Min\Python\Project\FA_Data\output `
  --confirm-process-pool-probe --stocks 0050 2330 --min-rows 30 `
  --max-rows-per-stock 120 --workers 2 --max-in-flight 4 --max-retries 1 `
  --transient-fail-stocks 0050 --output-json <TEMP_OUTPUT>
```

這個 probe 必須明確指定 bounded 股票範圍、staging root、protected root 與確認旗標；
worker 只回傳計算結果，逐股／合併 CSV 由父程序寫入 ephemeral staging，SQLite connection
不會進入子程序。輸出會列出 worker PID、in-flight 上限、retry、CSV serialization、
cleanup、input hash 與 `production_worker_enabled=false`。`status=measured` 只代表真實
calculator 的 staging process-pool 形狀通過；這份 probe 本身不涵蓋 worker crash recovery、
長時間取消與正式 single-writer integration，因此 production worker 數維持 1。

若要在同樣的隔離邊界驗證 worker process 意外結束後的 recovery、queued cancellation
與 partial-result discard，可使用：

```powershell
New-Item -ItemType Directory -Path C:\Users\archi\AppData\Local\Temp\technical_analysis_worker_recovery_stage -Force
.\.venv\Scripts\python.exe scripts\qa_technical_indicator_worker_recovery.py `
  --stock-data-file D:\Min\Python\Project\FA_Data\meta_data\all_stocks_data_top10.csv `
  --staging-root C:\Users\archi\AppData\Local\Temp\technical_analysis_worker_recovery_stage `
  --protected-root D:\Min\Python\Project\FA_Data `
  --protected-root D:\Min\Python\Project\FA_Data\output `
  --confirm-probe --stocks 2330 2308 --min-rows 30 --max-rows-per-stock 120 `
  --workers 2 --max-in-flight 2 --max-retries 1 --output-json <TEMP_OUTPUT>
```

此 probe 會以真實 `TechnicalIndicatorCalculator` 驗證 `BrokenProcessPool` 後重建
executor、取消 queued work 與丟棄取消後才完成的結果；接著在 ephemeral staging
由父程序依序寫入逐股／aggregate CSV 與既有 `DBManager` SQLite writer，並驗證
SQLite lock／retry。worker 不持有 CSV／SQLite writer，staging 結束後會清理。
`status=measured` 代表 recovery／取消與 parent writer staging contract 通過，
而 `production_single_writer_integration=staging_measured`、scope=`isolated_staging`
仍不是正式資料寫入證明。現在 production batch 已接上明確 feature flag，但預設仍關閉；
未完成 backup／rollback 與 owner-approved canary 前，不應在排程 task 傳入啟用旗標。

若要在受控環境以已驗收的 contract 執行一次 bounded technical worker，可明確傳入：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_daily_data_update_quick.py `
  --data-root <DATA_ROOT> --output-root <OUTPUT_ROOT> `
  --enable-technical-process-pool --technical-process-pool-workers 2 `
  --technical-process-pool-max-in-flight 4 --technical-process-pool-max-retries 1
```

這個旗標只把計算放入 bounded process pool；日期／warm-up 決策仍在父程序，
worker 不寫 CSV／SQLite，父程序才逐股保存並做整合寫入。每次 run 的 running／terminal
status 會記錄 flag 與 queue 參數，便於回滾與查核。未傳入旗標時維持既有 serial path；
worker 例外或取消不會自動降級成另一套計算結果。

若要驗證券商 HTTP fetch 的 bounded queue、global rate-limit、retry、duplicate 與
single-writer 契約，可使用離線 transport probe：

```powershell
New-Item -ItemType Directory -Path C:\Users\archi\AppData\Local\Temp\technical_analysis_broker_fetch_stage -Force
.\.venv\Scripts\python.exe scripts\qa_broker_bounded_fetch_acceptance.py `
  --staging-root C:\Users\archi\AppData\Local\Temp\technical_analysis_broker_fetch_stage `
  --protected-root D:\Min\Python\Project\FA_Data `
  --protected-root D:\Min\Python\Project\FA_Data\output `
  --confirm-broker-fetch-probe --max-tasks 9 --workers 2 --max-in-flight 4 `
  --max-retries 1 --rate-limit-seconds 0.005 --response-delay-seconds 0.02 `
  --output-json <TEMP_OUTPUT>
```

此 probe 不連線、不啟動 Selenium，使用假的 response 但實際呼叫既有
`BrokerBranchUpdateService._fetch_metric_records_http`／parser；9 個 submission 含
duplicate、transient 與預期 permanent failure，結果只由父程序寫入 ephemeral CSV。
`status=measured` 代表離線工程契約通過，不能當成 MoneyDJ 真實來源、授權或
canary 成功；真實 HTTP canary、rate-limit 觀測、Selenium driver recovery 與 production
broker worker 仍需另行取得環境／owner 允許。

若要只做一次真實來源連線驗證，可使用受控 canary：

```powershell
New-Item -ItemType Directory -Path C:\Users\archi\AppData\Local\Temp\technical_analysis_performance -Force
.\.venv\Scripts\python.exe scripts\qa_broker_real_http_canary.py `
  --staging-root C:\Users\archi\AppData\Local\Temp\technical_analysis_performance `
  --protected-root D:\Min\Python\Project\FA_Data `
  --protected-root D:\Min\Python\Project\FA_Data\output `
  --branch-system-key 1030_1030 --branch-broker-code 1030 --branch-code 1030 `
  --branch-display-name 土銀 --url-param-a 1030 --url-param-b 1030 `
  --date 2026-08-28 --metric lots --timeout 15 `
  --confirm-real-http-canary `
  --baseline-json C:\Users\archi\AppData\Local\Temp\technical_analysis_performance\broker_bounded_fetch_20260828.json `
  --output-json <TEMP_OUTPUT>
```

未提供 `--confirm-real-http-canary` 時完全不發網路請求；確認後固定只發一個 GET、
`retries=1`，使用既有 HTTP parser，Selenium 與平行 fetch 均不啟動。輸出會保留
branch/date/metric、endpoint、解析列數、parsed-row hash、cleanup 與所有 production
write flags。若加上 `--baseline-json`，只會讀既有離線 baseline 並產生新的合併 artifact，
不改寫 baseline。一次成功不能代表來源授權、長期 rate-limit、Selenium recovery 或
production writer 已通過；後續仍需 owner review，broker pool 維持關閉。

若要驗證 technical process-pool 的正式 single-writer 邊界，只能對一檔股票執行受保護的 production canary：

```powershell
.\.venv\Scripts\python.exe scripts\qa_technical_indicator_production_canary.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data\output `
  --protected-root D:\Min\Python\Project\FA_Data `
  --protected-root D:\Min\Python\Project\FA_Data\output `
  --stock-id 2330 --expected-latest-date 2026-08-28 `
  --output-json C:\Users\archi\AppData\Local\Temp\technical_analysis_performance\technical_production_canary_20260828.json
```

上述預設為唯讀預演，不建立 backup、不呼叫 `UpdateService`，且會先確認 production SQLite
完整性、指定股票日價與 expected latest date。只有 owner 明確提供
`--owner-approval technical-single-writer-canary`、
`--no-concurrent-writer-ack no-concurrent-writer` 及
`--confirm-production-technical-canary`，並先停止其他資料寫入者，才會建立 SQLite online backup
與單股 technical CSV backup，接著以 bounded process pool 重算一檔；worker 不寫檔，parent 才寫 CSV／SQLite。
建立 backup 前還會唯讀檢查 backup 所在檔案系統的 headroom，預設至少需要 20 GiB；不足時回報
`production_canary_storage_preflight_blocked`，不建立 backup、不啟動 writer。只有在受控環境明確調整
`--minimum-free-space-bytes` 且容量可追溯時才可降低門檻。
若 post-state 驗證失敗，工具會嘗試以 backup 回復並在 artifact 記錄 rollback 結果；canary 不下載行情、
不啟動 broker／Selenium，也不會註冊 scheduler。`status=measured` 只代表這一次 owner-approved
canary 的 backup／single-writer／post-state 驗收通過，不能直接把 scheduler worker 數提高。

若要把目前分散的效能證據交給 owner／reviewer，可使用唯讀 owner packet builder：

```powershell
.\.venv\Scripts\python.exe scripts\build_performance_canary_owner_packet.py `
  --technical-preview <TECHNICAL_PREVIEW_JSON> `
  --worker-recovery <WORKER_RECOVERY_JSON> `
  --broker-canary <BROKER_CANARY_JSON> `
  --direct-storage-preflight <DIRECT_STORAGE_PREFLIGHT_JSON> `
  --retention-direct <RETENTION_DIRECT_JSON> `
  --retention-ooc <RETENTION_OOC_JSON> `
  --output-json <TEMP_PERFORMANCE_OWNER_PACKET_JSON> `
  --markdown-output <TEMP_PERFORMANCE_OWNER_PACKET_MD> `
  --owner-role <NAMED_OWNER_ROLE> `
  --reviewer-role <NAMED_REVIEWER_ROLE>
```

六個輸入必須是呼叫端明確指定、位於 OS TEMP 的既有 artifact，且 schema／安全旗標不符時會
fail-closed；輸出也只能位於 OS TEMP，不能覆寫輸入。packet 只保留 bounded metadata、來源
path 與 SHA-256，固定 `candidate_only=true`、`write_performed=false`、
`destructive_action_performed=false`，不啟動 technical worker／broker production fetch pool、
不做 Formal OOS／broker order，也不刪除或搬移 Direct/OOC run。`needs_named_owner_reviewer` 或
`ready_for_owner_review` 只表示交接欄位狀態，不是 production canary 授權；容量低於 20 GiB
時必須先停止並交由 owner 決定 archive／擴容，不能用 packet 取代 capacity preflight。

若要驗證未來 technical compute-only worker 的 bounded queue 契約，可使用 synthetic probe：

```powershell
.\.venv\Scripts\python.exe scripts\qa_bounded_worker_acceptance.py `
  --workers 2 --max-in-flight 4 --max-retries 1 --cancel-after 3 `
  --output-json <TEMP_OUTPUT>
```

它不讀取或寫入任何正式資料，只驗證 in-flight 上限、有限 retry、permanent failure 不寫入、
duplicate idempotency、取消後停止新提交，以及 worker 不直接寫入而由主執行緒 single writer
收口。`status=measured` 只代表 synthetic orchestration contract 通過；真實 indicator
process-pool throughput 與 crash recovery 已有獨立 staging probe，broker HTTP rate-limit／retry
與正式 single-writer integration 仍需另外驗收，在此之前 production worker 數維持 1。

### 4.4 技術指標

- 「增量更新」：只發布新資料與重疊區間，日常首選；若單股指標已到最新股價日期會直接跳過，只有落後時才回看 120 個交易日決定發布範圍。計算前會保留完整、按日期排序的單股 OHLC prefix，算完才切發布列，避免截斷遞迴指標的歷史暖機。
- 「強制全量更新」：重算所有股票歷史資料，只在指標算法改動或資料損毀時使用。
- 股票代號留空代表處理全部；輸入例如 `2330` 代表只處理單一股票。
- 缺少或非有限 OHLC 會保留缺值並將指標計算切段，後續有效區段重新暖機；不以前值、未來值或 0 填補。初始暖機期間的 NaN 是預期結果，不應當成漏算補值。
- SQLite 與 `all_stocks_data.csv` 的局部更新只合併本輪已成功發布的股票／日期，保留其他股票、未發布日期及未提供欄位；只有明確全市場強制重算且所有股票完成時，才可全量替換彙總資料。
- 增量寫入單股指標 CSV 時，若舊檔或新結果缺少可辨識日期欄位，會避免直接疊加資料；必要時以新計算結果覆蓋該單股檔，防止同一股票歷史列倍增。
- 一鍵更新與排程判斷技術指標是否可跳過時，除了比較 `daily_prices` / `technical_indicators` 最新日期，也會檢查最新日 eligible 股票覆蓋數；若 TWSE 先完成、TPEX 後補進來，系統會再跑增量計算，不會因全表最新日期相同而漏掉 TPEX 股票。
- 技術指標計算預設仍是單流程；若受控 caller 傳入 `--enable-technical-process-pool`，才會以 bounded compute-only worker 平行計算，並由父程序單一 writer 統一寫入 CSV／SQLite。可設定的 worker、in-flight 與 retry 上限會寫入 run status；正式 scheduler 預設不傳旗標，待 backup／rollback、真實 canary 與效能觀測完成後才評估啟用。
- 推薦與回測載入已保存技術指標後，只有在參數等於系統標準預設、欄位完整且含有效值時才直接重用；自訂參數、缺欄位、全無效欄位、ATR 或 ADX 仍會按原流程計算。這項最佳化不改技術指標更新排程、SQLite schema、推薦門檻或回測規則。

### 4.5 SQLite 資料檢視

1. **選擇與篩選**：選擇資料表，設定每頁限制筆數，填入股票代號、名稱、券商分點或日期篩選。券商分點可在 `broker_flows` 時由下拉選單選取，也可手動輸入關鍵字。日期預設空白，不會自動套用條件；打開日曆時會定位到今天。單一日期可按「今日」快速帶入今天，區間旁的「清除」會同時清掉單一日期與區間日期。
2. **載入數據**：點擊「載入數據與結構」按鈕。
3. **基本面資料表**：資料表下拉選單會列出 `fundamental_monthly_revenues`、`fundamental_statement_items`、`fundamental_valuation_metrics`。月營收表可用股票代號與日期篩選，日期對應 `as_of_date`，例如 `2026-05-31`。
4. **資料分頁控制**：
   - 底部設有分頁控制列，包含「上一頁」、「下一頁」、「跳至第 X 頁碼（輸入頁碼並按跳頁按鈕）」、以及「當前頁數 / 總頁數」與「篩選後總記錄數」。
   - **防禦機制**：修改篩選條件並重新載入時，系統會自動重設為第一頁，並快取 schema 避免不必要的拉取。
   - **Stale 結果防護**：連續切換分頁或資料表時，舊有的非當前背景查詢結果會被自動忽略；執行中的背景查詢會安全保留到自然結束，防止 UI 資料錯亂或執行緒提前銷毀。
5. **欄位結構**：在「欄位結構」Tab 查看欄位 Schema 與型態描述。
6. **表頭排序**：在「資料預覽」點擊任一欄位表頭可切換升冪 / 降冪。排序由 SQLite 端以白名單欄位 `ORDER BY` 執行，並沿用目前篩選與分頁限制，避免 UI 端載入全表排序。
7. **漲跌欄位顯示**：`daily_prices` 若遇到舊 schema 的簡體 `涨跌`，畫面會顯示為繁體 `漲跌`；`漲跌價差` 會依 `漲跌(+/-)` 或 `漲跌` 方向顯示正負號，以利顏色與排序判讀。
8. **重複顯示欄名防護**：若 raw schema 與 alias 造成相同顯示欄名，表格仍以欄位位置取值，不應出現 `PandasTableModel.data` 的 Series ambiguity 錯誤。

此工具是受控唯讀檢視器，不應用來修改或刪除資料。

### 4.6 市場資料完整性修復（受控 CLI）

當資料品質稽核發現 `daily_prices` 有空白股票代號、非交易日誤入資料，或 `market_indices` 缺少指數名稱時，使用受控 CLI；它不會改動 raw CSV、策略、Recommendation、evidence 或 scheduler。星期六、日不是直接刪除條件：個股日檔必須先符合「含 `證券代號`、`收盤價`」的欄位契約；若日期落在週末，還必須有 TWSE `MI_INDEX` 的官方開市資料才允許同步。官方查詢失敗時 fail-closed，不把該日當作可交易日。

```powershell
# 先只讀列出預計修復範圍與每個週末日期的官方查詢證據
.\.venv\Scripts\python.exe scripts\repair_market_data_integrity.py --json-output

# 人工核對後才套用：只建立一份 SQLite snapshot、移除已驗證非交易日 / 空代號列，並由 raw market_index.csv 重建 market_indices
.\.venv\Scripts\python.exe scripts\repair_market_data_integrity.py --apply --confirm apply-market-data-integrity-repair --json-output
```

套用前腳本會用 SQLite backup API 建立 `DATA_ROOT/sqlite/backups/twstock_before_market_data_integrity_<timestamp>.db`，並執行 `PRAGMA quick_check`。若驗證不通過，正式 DB 不會進行刪除。回復時應停止寫入工作、以該 snapshot 依 SQLite backup API 還原，再重新跑 `PRAGMA quick_check`；不可用複製貼上方式覆寫仍在使用中的 WAL 資料庫。

大型備份不會由腳本自動刪除。先以只讀盤點確認健康度與保留候選，再由 owner 對每一份候選確認用途與可回復性：

```powershell
.\.venv\Scripts\python.exe scripts\audit_sqlite_backup_retention.py --verify
```

預設建議是保留 active DB 與三份最新、已驗證的完整 snapshot；舊 snapshot 僅列為人工審核候選，絕不自動刪除，避免破壞與 migration / backfill 對應的回復點。

### 4.7 匯出 CSV 備案

個別資料頁可選：

- 最近範圍
- 全部歷史

輸出使用 UTF-8 with BOM，方便用 Excel 開啟。這是離線備份與人工研究功能，不影響系統日常運作。

### 4.8 高風險操作

「強制重新合併」與「強制全量更新」會長時間處理大量歷史資料。只有在資料損毀、schema 修復或算法變更後使用，不要作為日常更新方式。

### 4.9 Month 5 月營收候選資料抓取

月營收候選資料抓取只負責來源驗證與 raw evidence 保存；抓取 CLI 本身不會寫入正式 `DATA_ROOT/meta_data/monthly_revenue_availability.csv`，也不會寫入 `fundamental_monthly_revenues`。正式 mapping 與 SQLite 回填需另外走 validator / backfill 流程，並在高風險操作前由人工確認。

在更新頁中途取消 MOPS 候選抓取時，已完整取得的 raw HTML response 可留作診斷；取消流程不會發布不完整的 candidate CSV。訊息「保留 X 筆已解析資料」是本次解析進度摘要，不代表這些列已形成可載入候選檔。先檢查本次狀態與保存的 raw response；要重新產生候選時，使用新的完整受控 run，不要把未完成輸出手動併入正式資料。

以下是 2026-06-16 留存的歷史命令範本，不是目前日期或正式資料根目錄。要重新抓取時，先確認本機 `DATA_ROOT`／`OUTPUT_ROOT`、本次查詢期間與 fetch date，再以自己的值取代範本中的 `YYYY-MM`、`YYYY-MM-DD` 和路徑；不要照抄歷史日期或 `D:\Min\Python\Project\FA_Data`：

```powershell
.\.venv\Scripts\python.exe scripts\fetch_mops_monthly_revenue_snapshot.py --start-period YYYY-MM --end-period YYYY-MM --markets twse,tpex --output-dir "<OUTPUT_ROOT>\monthly_revenue_mops_snapshots" --fetch-date YYYY-MM-DD --sleep-seconds 0.5
.\.venv\Scripts\python.exe scripts\fetch_finmind_monthly_revenue_create_time.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --raw-dir "<DATA_ROOT>\financial_data" --output-dir "<OUTPUT_ROOT>\monthly_revenue_finmind_create_time" --max-requests-per-hour 480 --resume --fetch-date YYYY-MM-DD
```

第一個命令會保存 MOPS raw HTML 與完整市場月營收 snapshot CSV；它只代表營收內容快照，不得用 period 或歷史查詢日推定官方公告日。若從某天開始每日保存 MOPS snapshot，可把本機首次看見該月營收列的日期視為 first-seen observation candidate，搭配 `available_date=first_seen+1 calendar day` 作保守候選 mapping；這仍不是官方 MOPS 公告日，正式寫入前必須由人工確認。第二個命令會使用已加密保存於本機的 FinMind token 逐檔抓取 `TaiwanStockMonthRevenue.create_time`，輸出 create_time 分組檔；`create_time` 只作備用 / 交叉檢查與每月分批更新參考，不作主線 mapping。若 FinMind 流程中斷，用同一個 `--output-dir` 加 `--resume` 重跑即可接續。

毛利率不是月營收資料。MOPS `t163sb06` 是季度財務比率 / 毛利率彙總表，查詢維度是年度與季別；後續若要納入，應走季度財報 / 財務比率 pipeline，另建公告日與 `available_date` gate，不要混進今晚的月營收 snapshot 或 FinMind create_time 流程。

### 4.10 Gate 2 Data Governance Consolidation & PIT Safeguards

#### 4.10.1 資料品質防線 (DataQualityFirewall)

`DataQualityFirewall` 提供非破壞性數據品質診斷，絕不上寫或刪除正式 SQLite 原始資料庫：

1. **`daily_prices` 診斷**:
   - 捕捉 NULL / 空白 / 非法 `證券代號`（隔離標記 `QUARANTINE_REJECT`）。
   - 捕捉週末 / 休市日 OHLC 記錄（標記 `SUSPICIOUS_WEEKEND_DATE` 與警告日誌）。
   - 捕捉重複主鍵 `(證券代號, 日期)` 與價格範圍違規（`QUARANTINE_ISOLATE`）。
   - 產出可追溯 anomaly report，包含 exact primary key、row hash、原因與建議處置。

2. **`market_indices` 診斷**:
   - 檢核規範欄位 `指數名稱` 與舊欄位 `收盤價` / `收盤指數`。
   - 若 `指數名稱` 缺失但舊 OHLC 仍可由 fallback 讀取，系統明確評估為 `degraded`（降級），絕不誤報為 `healthy`。

#### 4.10.2 PIT (Point-In-Time) 安全防線

適用於 `fundamental_monthly_revenues`、`fundamental_statement_items` 與 `valuation`：

1. **可得日規則**: 強制要求 `available_date <= decision_as_of_date` 才能在歷史推薦、策略評分與回測中採信。
2. **未來資料偏誤攔截**:
   - `available_date > decision_as_of_date` 觸發 `PIT_FUTURE_LOOK_AHEAD` 並強制拒絕。
   - `available_date` 缺失觸發 `PIT_AVAILABLE_DATE_MISSING` 並強制拒絕/降級。
   - 月營收與季度財報讀取同時要求可驗證的 `announced_date`；缺失時觸發 `PIT_ANNOUNCED_DATE_MISSING` 並 fail-closed，不得把回填 `available_date` 當作歷史 PIT 證據。
   - 事後補齊之公告日觸發 `PIT_POST_HOC_ANNOUNCEMENT` 並強制拒絕。
3. **無 Future Leakage 保證**: 防線確保缺失資料不會默默填充為 0 或高分，絕不引入未來函數。

#### 4.10.3 Gate 2 證據三層模型與運作包

1. **三層模型**:
   - **Layer 1: Weekly Collection**: 側邊每週自動採集，標記為 `pending_human_review` 或 `collection_failed`。
   - **Layer 2: Approved History Projection**: 經具名 owner 核准之外部唯讀 JSON 投影 (`approved-weekly-history-projection.v1`)，固定 `formal_credit_authorized=false`。
   - **Layer 3: Formal DB Credit**: 正式資料庫 credit 權限，必須由具名人工權責角色簽署。
2. **Projection 驗證限制**: 嚴禁 projection 指向正式 SQLite 資料庫目錄，並重複檢查週期重疊與 Schema 格式。
3. **人工審查包與災原演練**:
   - 提供週次審查表單範本、Working-Copy 備份與復原演練 SOP 及緊急回滾核對清單。

#### 4.10.4 排程與日常證據可觀測性

1. **五大排程任務相依性**:
   - `daily_data_update_quick` -> `daily_data_freshness_check` -> `scheduled_recommendation_snapshot` -> `scheduled_evidence_pipeline_dry_run` -> `v2_2_weekly_collection`
   - 這是 health service 的五個邏輯證據單元，不是 Windows task 總數。Windows
     registration inspector 的 2026-09-09 歷史輪次曾檢查 18 個每日 task 與 1 個 weekly task；
     數量不代表今天的主機狀態，承接時須重新唯讀核對 registration receipt 與主機查詢。
     `baldr-ml-allocation-forward-daily` 由固定 XML 及專用 preflight 管理，aggregate
     `register`／`register-all` 不會覆蓋它。
2. **寫入意圖劃分**:
   - `daily_data_update_quick` 允許進行市場價格資料更新寫入 (`MARKET_DATA_UPDATE_WRITE`)。
   - `production_scheduler_allowed=false` 僅約束正式 DB Evidence 寫入，**絕不代表禁止每日市場價格資料更新**。



## 5. 市場探索

### 5.1 大盤指數

1. 點擊「檢測市場狀態」。
2. 查看 Regime、規則匹配度與判斷摘要。
3. 展開技術細節時，可查看價格與均線、趨勢、評分、其他指標與判斷條件。
4. 將策略建議作為 Profile 選擇參考，不要視為買賣訊號。

Regime 是對當下市場環境的分類，不是未來預測。規則匹配度是 detector 對目前資料符合既有規則的程度；100% 代表達到目前規則上限，不代表未來勝率或成功機率。

若市場資料來源讀取失敗，`Trend`／`0.5` 與 `details.error` 是降級結果，不是新訊號；判讀前先確認來源資料可讀及有效日期。若 history 損壞或偵測到其他程序同時更新造成提交衝突，本輪狀態視為不可用，不要把上一輪 Regime 當成本輪成功結果。先檢查市場來源及是否有同時寫入，再保留 `regime_history.json` 原狀；不要手動刪除或覆寫。問題持續時依系統維護流程處理後再重試。

### 5.2 強勢與弱勢個股

市場服務同時保留決策日與實際有效日。較舊資料會標為 degraded 並保留 fallback 日期；只有未來資料、日期未知或有效樣本不足時保持 missing。Breadth 的比例以基點、Regime 的規則匹配度以分類分數交換，均不是勝率。指定歷史決策日的應用服務先裁切可用資料才排名，追加未來行情不改當日已凍結母體；本次沒有新增歷史日期 UI 控件。

1. 選擇「本日」或「本周」。
2. 第一次進入可按「載入數據」。
3. 需要重新計算時按「刷新」。
4. 選取股票後按「加入觀察清單」。

強勢排名不等於建議追價；弱勢排名也不等於做空或立即賣出。

強弱勢表格下方的狀態列會顯示「載入中」、「已更新」與實際筆數；若服務回傳空資料會顯示 0 筆，若刷新失敗則顯示第一行錯誤診斷並清空上一輪表格，避免把過期排名誤讀成目前結果。請先依狀態列診斷資料來源，再重試刷新。

弱勢頁的跌幅欄位位於顯示邊界，會安全處理 CSV／舊服務傳入的字串數字；無法轉換的值留為缺值，不會把整頁誤判成載入成功，也不會以 `0` 補值。

弱勢個股頁的 `跌幅%` 會把來源的負漲幅取絕對值顯示，例如來源 `-9.90%` 在畫面顯示為 `9.90`，並以紅色表示下跌語意；欄名已經說明這是跌幅，所以不再用負號重複表意。這只是視覺語意修正，不改變篩選排名或 scoring。

效能邊界：強 / 弱勢個股在 SQLite 啟用時會優先從 SQLite `daily_prices` 只讀近期交易日與必要欄位；產業共振理由會使用 `IndustryMapper` 最新產業表現快取，避免逐檔股票重掃產業指數 DataFrame。recent provider 回傳空 `DataFrame` 代表來源已成功讀取，結果為空時不會再掃描舊來源；只有回傳 `None`（例如資料庫不存在或 recent 查詢失敗）才會進入 fallback。個股 fallback 先嘗試唯讀 SQLite `daily_prices`／`technical_indicators` JOIN，無可用資料時再掃描 `technical_dir/*_indicators.csv`；產業 fallback 先嘗試唯讀 SQLite `industry_indices`，再依序檢查設定的 `industry_index_file`、`technical_dir/industry_index.csv`、`meta_data_dir/industry_index.csv`。所有 SQLite 查詢使用唯讀連線，不會修改正式資料庫。

若狀態列顯示 0 筆，先分辨 recent 資料來源可用但沒有候選，還是資料來源缺失／查詢失敗。再核對設定的資料庫路徑與個股技術指標目錄、產業 CSV 路徑；來源修復後按「刷新」重試。若仍感到卡頓，應先量測 SQLite 查詢、DataFrame 分組與 UI thread 更新時間；不要把排名結果解讀成交易指令。

候選池頁同樣採狀態列語意：載入中、已更新筆數、空候選與錯誤都會直接顯示在表格下方；空清單或載入失敗不會插入 `-` 佔位資料列，批次回測按鈕也會維持停用。

### 5.3 強勢與弱勢產業

使用本日可得的 5／20 個 TAIEX 交易 session 排名判斷產業相對強弱，再回到個股研究頁查看產業內股票。這是 current-research 讀模型，不是歷史 PIT membership、回測結果或交易建議。

強 / 弱勢產業由 `IndustryStrengthService` 從 SQLite `industry_indices`、`market_indices` 的精確 `TAIEX` 與 `daily_prices` 唯讀組成。表格顯示產業、指數、層級、5／20 日報酬、相對 TAIEX 報酬、coverage、代表股與 quality；來源 ID、資料日、mapping version、PIT 狀態與完整 warnings 由狀態列／詳情保留。找不到 TAIEX 或有效窗口時 fail-closed，不任意改用其他 benchmark，也不把缺價補成 0。

產業列只接受明確 pure-index mapping；槓桿、反向、策略與產品型指數會排除。父層 aggregate 與 leaf 分層排名，不混成互斥同級；`mapping_mode=current_research_only`、`historical_pit_eligible=false` 時，畫面只可作當期人工研究。coverage 分母固定是與 TAIEX／TWSE scope 對齊的 current registry members，TPEX／興櫃及未映射類別會以警告與缺口欄位揭露。

操作時先在表格選取產業，再在「代表股」選擇器選一檔明確股票，按「開啟所選代表股研究」進入既有個股研究報告。排序後仍須重新確認目前選取列；點擊或雙擊表格列只會選取產業，不會偷偷開啟第一檔代表股。此路徑傳遞股票、產業、資料日與來源身份，不寫入觀察清單或 watchlist。

弱勢產業頁的 `跌幅%` 同樣以正數顯示跌幅大小、以紅色表示下跌語意；不應把紅色正數解讀為上漲。

### 5.4 主力流向

「個股資金流向」操作：

1. 選擇日線、週線或月線。
2. 選擇直方、折線或面積趨勢圖。
3. 選擇顯示範圍；預設為「Top / Bottom 50」，主表只顯示買超前 50 與賣超後 50，摘要統計仍使用全市場掃描結果。
4. 點擊「開始掃描」。
5. 點選主表股票，右側顯示分數、集中度、訊號原因與分點明細。
6. 主表新增「語意狀態」與「5/20/60 日診斷」欄；語意狀態包含 `初轉買`、`買超延續`、`初轉賣`、`賣超延續`、`高檔出貨疑慮`、`分點集中異常`。
7. 主表欄寬預設優先保留 5/20/60 日診斷與近期趨勢圖；集中度、語意狀態、5/20/60 日診斷與 Badges 欄都依目前資料最長內容加少量留白自動貼合，不吃掉所有剩餘空間。近期趨勢欄維持 compact 固定寬度，直方圖會在欄內以緊湊間距並保留左側 padding 繪製，右側分點 panel 會取得多餘空間；完整數字與品質細節保留在 tooltip。
8. 懸停列可查看 5 / 20 / 60 日 Top N quantity 集中度、observed / estimated / unavailable 筆數、5 / 20 / 60 日淨量與價格位置等診斷。
9. 表格標頭可排序。
10. 有 Watchlist service 時，可按「+ 觀察清單」。
11. 右側分點明細表會依 panel 寬度自動分配「分點名稱 / 買進張數 / 賣出張數 / 淨買賣超」四欄，優先完整顯示內容與淨買賣超 bar，不應需要水平捲動。
12. 在右側分點明細雙擊分點名稱，會切到「分點進出追蹤」並選中該分點。

「分點進出追蹤」操作：

1. 選擇券商分點。
2. 查看該分點近期操作股票、張數、標籤與趨勢。

資料品質：

| 品質 | 解讀 |
|---|---|
| observed | 原資料直接觀測到張數或金額。 |
| estimated | 由可用價格與金額估算，信心較低。 |
| unavailable | 無足夠資料，不應硬補成 0。 |

語意診斷限制：

- 5 / 20 / 60 日視窗只使用決策日以前可取得的分點事件，不使用未來資料補滿視窗。
- 分點集中度使用 quantity（張數 / 股數等價數量）計算，不使用千元金額直接當集中度。
- unavailable 事件不放進集中度分子或分母，會在 tooltip 揭露排除筆數與覆蓋率。
- `高檔出貨疑慮` 是價格位置與主力賣超聯動的風險提示，不等於賣出建議。
- `分點集中異常` 代表同方向淨量集中於少數分點，應搭配價格、成交量與資料品質判讀，不直接代表利多或利空。

單一分點買超不等於真實主力意圖，應優先觀察多分點共振、價格行為與資料覆蓋率。

## 6. 推薦分析

### 6.1 新手模式

1. 查看系統偵測的市場狀態與 Profile 建議。
2. 可按「一鍵套用建議 Profile」。
3. 或自行選擇 Profile。下拉會標示來源：
   - `內建｜...`：系統內建模板，例如暴衝、穩健、長期。
   - `自訂｜...`：使用者從目前推薦設定保存的 Profile，會標示「自訂，未經回測驗證」。
   - `策略版本｜...`：Research Lab / Strategy Registry 已通過 gate 的策略版本；停用或未通過 gate 的版本不顯示，但歷史策略版本資料不會被刪除。
4. 選擇 Profile 後，閱讀說明區的「對應進階設定」，確認權重、技術分類、型態預覽與主要篩選條件是否符合預期。三個內建 Profile 不只是 buy score / sell score 門檻不同，也會帶入不同的 `pattern` / `technical` / `volume` 權重、啟用技術分類、型態偏好與漲幅 / 成交量篩選。
5. 若目前設定值得重用，可按「保存目前設定為自訂 Profile」；保存後會出現在 `自訂｜...` 清單。
6. 點擊「執行推薦分析」。

推薦分析頁開啟時會直接讀取每日排程狀態所指向的精確保存結果；「載入每日推薦」可重新讀取該狀態中的結果 ID。畫面會標示快照決策日與候選筆數，並明確說明這是研究候選，不代表投資建議或交易。此讀取只查詢該筆 canonical 結果，不重新執行推薦、不寫入 Evidence、不執行 lifecycle 或交易。排程狀態缺失、未通過或保存根目錄不一致時，狀態文字會說明原因並保留目前畫面。

執行或選取結果後，結果區上方的「研究上下文」會沿用同一檔股票、研究區間、決策日、資料日期、來源與 Profile。切到個股研究、Research Lab 或 Portfolio 時，應以這組 context 核對是否仍在同一研究假說；缺少欄位會顯示未知，不由 UI 猜測或重新計算。

推薦分析執行期間，進度列會顯示目前百分比；下方「執行狀態」會同步顯示四個階段（讀取資料、建立分析範圍、執行推薦規則、整理結果）、耗時與最後活動時間。這些欄位是本輪背景工作的可觀測狀態，不會把等待中的時間推算成額外完成度。按「取消分析」只會送出合作式取消，按鈕會改為「取消中…」並等待背景工作安全收尾；收尾前不套用部分結果，也不會強制終止仍可能持有資料資源的執行緒。完成後畫面會保留「已安全取消」及本輪耗時，需重新按「執行推薦分析」才能開始新一輪。

按下執行時，畫面會凍結當次 Profile 與設定；工作期間仍可查看、保存上一筆完整結果。取消、失敗或晚到的舊工作回呼不會套用部分結果或覆蓋上一筆結果與選取列。新一輪完整完成後才切換到新結果；若完整結果為空，舊股票列會清空。Qt 手動執行會在封存的 caller 設定快照中標記 `manual_qt_snapshot=true` 供來源辨識，執行規則前會移除此來源標記，因此不影響策略選擇或分數。

市場狀態卡會顯示 Regime 中文名、regime code、confidence / 規則匹配度、Regime score、資料日期與來源。confidence / 規則匹配度是當下資料符合分類規則的程度，不是未來走勢勝率。

推薦結果的規則分數、資料品質、研究訊號與校準機率是不同欄位；`reliability=0.9` 或 Regime confidence 不能寫成 90% 勝率。Profile 的風險 policy、相容性與 blocked／incompatible 理由仍由 `RecommendationProfileService` 決定，畫面不會因高 confidence 自動改選高風險 Profile。

Profile-Regime 說明：

- `match` / `bonus`：目前 Regime 落在 Profile 適用 Regime；既有 scoring 會以 regime 權重調整揭露加分語意。
- `mismatch` / `penalty`：目前 Regime 不在 Profile 適用範圍；結果不會被直接排除，只在排序、分數或原因中揭露不匹配。
- `neutral` / `no_bonus`：Regime 尚不可用或 Profile 未指定適用 Regime；不套用 Profile-Regime 加分。

### 6.2 進階模式

可設定：

- 技術指標
- 圖形模式
- 最小漲幅
- 最小成交量比率
- 產業
- 排名門檻
- 月營收 YoY 最低值（可選）
- PE 最高值（可選）

參數治理限制：

- 新版配置啟用的技術指標必須提供完整參數；字串代替整數、未知欄位、越界值或衝突組合會直接顯示失敗，不會靜默使用猜測值。
- 關閉的子指標不會計算，也不會產生空欄位。
- 評分權重使用 `pattern`、`technical`、`volume` 三項整數基點，總和必須為 `10000 bp`。
- 核心總分使用 Decimal 並固定至 `0.01` 分；畫面摘要顯示兩位小數，游標提示保留原始 Decimal 值，排序使用未四捨五入的值。設定錯誤屬治理例外，不會被轉成空結果。
- buy score / sell score 是總分完成後的判讀門檻；調整門檻只改入選 / 賣出判讀，不會改變各項指標如何貢獻總分。若要改變「為什麼得分」，必須修改 Profile 權重、技術指標、型態或前置篩選，並重新做推薦回放 / Research Run 驗證。
- 啟用月營收 YoY 或 PE 篩選時，系統只採用 `available_date <= decision_date` 的基本面版本；決策日期無法標準化、PE／同月去年營收缺失、或未達門檻時，候選會以 `skipped` 留在 screening matrix，不會以 0、空值或未來資料補足。PE 預設 `999`、YoY 預設 `-100` 為停用哨兵；調整後才會啟用對應篩選。

### 6.3 固定門檻與百分位排名

| 模式 | 行為 |
|---|---|
| 固定門檻 | 使用既有絕對分數與篩選邏輯。 |
| 百分位排名 | 在當日 eligible universe 中計算橫斷面排名。 |

百分位模式參數：

- 最低百分位：例如 80% 代表保留當日母體中較高排名區間。
- 最小母體數：避免用太少股票產生不穩定百分位。
- 排名方法：目前為「最近名次法」，使用排序後最接近的觀測值作為百分位門檻，方便追溯。

若出現 eligible universe too small：

1. 放寬前置篩選。
2. 增加最大掃描股票數。
3. 降低最小母體數。
4. 不要把錯誤改成自動退回 fixed；兩種模式應保持可辨識。

quantile 目前是 opt-in，不能宣稱比 fixed 更準。

### 6.4 結果判讀

推薦服務保留決策日、實際行情日與排名母體；top_n 只限制入選數，不改百分位母體。已啟用指標缺值、基本面缺可得證據或總分無效時，結果保留 Why Not 並降低品質，不以零分或中性分數代替未知。無符合候選可以是有效空結果。

指標只在父層與該指標都啟用時參與評分；父層停用會連同子項一起排除。歷史行情需求會按啟用指標的實際週期計算，並至少取 60 個有效交易 bars；較長的 MA、RSI、MACD、KD、ADX、Bollinger 或 ATR 週期會提高所需 bars。資料日不得晚於決策日。缺少啟用指標觀測值時，候選是「不可計分／來源缺件」，不是零分或被門檻篩掉；先檢查來源與有效交易 bars，不要為了產生非空清單而放寬門檻。

空結果畫面會區分三種情形：沒有可評估的候選資料，先檢查來源日期與候選清單；有候選但沒有可計分資料，先檢查來源欄位與啟用指標；候選已完成評分但全數未通過目前篩選／排名條件，才檢查門檻設定。只有第三種表示評分後的策略篩選結果為空；前兩種不能靠降低門檻修復。零筆也只有在同一 `result_id` 的 canonical 保存與讀回通過時才是有效空結果；沒有保存、身份不符或讀回失敗仍是缺件，不可用「沒有資料」代替驗證。

- Why：為何入選。
- Why Not：哪些條件不足或限制排名。
- Explain：技術、圖形、量能等子分數與風險點。
- 圖形理由若顯示型態名稱，代表該型態已在可用收盤資料的確認日成立，並標示仍處於 20 個交易日衰減觀察窗的第幾天；`end_idx` 本身不算確認。若只看到「圖形訊號偏多／偏空」，代表資料沒有提供可核對的具體型態名稱，系統刻意不臆測。
- 百分位與母體：只在 quantile 模式有意義。
- Regime match / mismatch：顯示目前 market Regime 與 Profile 期望 Regime 是否一致；mismatch 是解釋與排序訊號，不是自動排除或交易指令。

選取結果列後，在「推薦結果與風險判讀」按「展開推薦理由」，可依序閱讀分數拆解、排名門檻、推薦理由與「可能影響排名的因素」。展開後理由全文沿整個結果頁往下排列，請使用結果頁右側捲軸或在理由文字上滾輪；文字區取得焦點後，也可用 PageDown／PageUp 或 End／Home 到下一頁、上一頁、全文末尾或開頭。窄視窗不應截掉下半段文字；按「收合推薦理由」可恢復較短高度，內容不會刪除。這些區塊是同一筆結果的解釋，不是另一輪分析，也不會修改排名。

若選取的是「篩選紀錄／未入選」，先讀最上方的中文說明，再看下方原篩選證據。例如成交量變化 `-31.23%`、要求至少 `50.00%`，表示相對該次量能基準量縮、未達放量條件；這項檢查在打分前停止，因此沒有該次推薦分數或排名。它可用來核對策略條件、資料日期及比較不同策略，不能當作個人 H20 預測。缺少或矛盾的數值不補量縮結論；個人 H20 保存的20交易日未扣成本估計，請回「個人模型選股研究（H20 毛報酬）」或個股頁獨立 H20 區塊查看。

V1.7 後，「保存結果」會一併保存推薦當下的 screening matrix：每檔候選會以 pass / fail / degraded / skipped / missing 標示狀態，並保留 Why Not、Liquidity exclusion、歷史不足、無訊號或例外降級等原因。2026-07-06 後，若個股因 `min_volume_ratio` / `volume_ratio_min` 成交量門檻而沒有策略結果，會以 `liquidity_volume_ratio_below_min` 進入 Liquidity payload；這只補來源追溯，不會改分數、不會自動調整持倉、不會自動降級策略版本。

即時推薦會先核對本次執行固定的官方市場狀態來源。只有具備同股終止公告、原件雜湊、有效日期及擷取時鐘，而且公告已在決策當時生效的股票，才以「官方市場狀態（current_market_status_gate）」及「已核驗下市／終止（official_delisted）」排除；它仍保留在本次篩選紀錄。這項排除先於歷史長度檢查，因此已下市股票不再誤報成等待累積歷史行情。來源不可讀、時間不符或公告無法核驗時，保留未知狀態並繼續既有資料檢查，不猜填下市。明示歷史截日與歷史研究不使用新取得的現況證據。

排程狀態的「市場狀態排除」還會核對同一保存執行的篩選列與逐股證據；只有文字原因而缺少來源身分不能取得此分類。排錯時先檢查同筆結果中的來源 run、官方 URL、擷取時間與有效日；再檢查正式來源根的 `release_v4/current_market_status/current_market_status_pointer.json`。重新更新來源後須重新執行推薦，舊保存結果不會被目前狀態改寫。

個股研究的來源選單、頁首與 Advice 會分開呈現決策日和保存當次實際資料日，例如 10/5 決策使用 10/2 行情。新保存結果會保留當次已取得的行情日期與來源指紋；載入時核對同筆結果、執行身分及日期，不用目前最新資料改寫舊結果。已有自然觀測 lineage 的保存結果可沿原封存證據取回日期；其他舊結果若未保存可驗證日期，仍顯示未知。日期欄位本身不證明公告時間、歷史可得性、可重播快照或模型資格，也不會把較舊行情改標為最新。

若重新開啟後日期不符，先核對所選股票、結果 ID、決策日及來源選項；錯日期或錯來源仍拒絕。若舊結果沒有日期證據，可從同股研究入口另做目前分析並保存成新結果；不要把新日期填回舊歷史分析。來源選單保留明確選擇，切股後須使用新股票自己的來源。

「目前策略傾向摘要」只描述已勾選技術指標與圖形模式推導出的摘要，不是可調偏好控制。若需要改變偏短線、偏長線或盤整 / 趨勢取向，應回到 Profile 或進階設定調整實際條件。

推薦分析不會自動下單、不會自動調整持倉，也不會把自訂 Profile 視為已通過回測驗證。策略版本 Profile 只代表該版本通過既有 gate，可作推薦設定來源，仍需自行判讀資料品質、風險與研究證據。

#### 隔日校準 projection 與 provenance（唯讀）

若結果列或「決策工作台」顯示校準機率，先在 provenance 詳情核對
`projection_receipt_path`、`projection_receipt_hash`、`result_id`、`decision_date`、
candidate 與 cost scenario。receipt 的預設路徑為
`<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\inference_projection\<decision_date>\<safe_candidate>\<receipt_digest>.json`；
保存結果的 `run_context.calibration_projection_receipt` 也會保留 path、hash 與 result identity。
一般按「執行推薦分析」未另傳 `result_id` 時，服務會在本輪 receipt 發布前產生含 UUID 的唯一 `rec_...` identity，
同一輪重複保存沿用該 ID；明確傳入的 ID 會原樣保留。保存 coordinator 若發現 live run context、frozen context、
receipt 或推薦列 provenance 的 identity 不一致，會拒絕保存並提示衝突。
查詢時必須使用 exact `result_id`、股票代號、決策日、candidate 與成本 lane 交叉核對，
並確認 receipt hash readback 通過；不可用 latest、同股同日或第一筆結果替代。這些欄位只供唯讀追溯，
不會因開啟 receipt 而重跑推薦、寫入資料庫或改變持倉。

- `provenance_status=verified` 且 receipt 已 `persisted`：表示 training／inference source、PIT、feature transform 與共享 cost／probability contract 已核對，可讀取該筆 model projection；正式 top-N 仍由 rule selection authority 決定，不能把機率當成未授權的選股改排依據。
- `legacy_unproven`：舊 candidate 缺少 P1 training lineage 的相容標記，不代表已驗證，也不等於策略失敗；不可計入 verified evidence 或據此自動升級。
- `unavailable`／`not_persisted`：receipt、source、pointer 或 identity 核對失敗；系統保留原 rule selection，但撤回 model-derived probability／ranking 欄位，不應手動補成 verified。
- `estimated`：成本或成交資料是研究估算（例如 fees/tax-only），不是 observed fill；只可作 research-only 判讀，不得當成正式成本、promotion、績效或 broker 依據。

一般使用仍按既有「執行推薦分析」流程，不需新參數。若 live calibration 的 SQLite 來源在 snapshot 載入後或模型 projection 期間變更，系統保留 rule 排序與分數，將校準標為 `unavailable`，不發布 model-derived 欄位或模型 receipt。Historical recommendation replay 另在日期列舉前開啟同連線 SQLite observation lease，並於整輪建立完成後檢查來源；若期間有其他連線提交變更，整輪 replay 會 fail closed，不發布部分結果。每日 scheduled learning 將 `changed during read lease` 分類為 source-integrity emergency rollback，不是可直接重試的 recoverable dependency failure；先查看 finalized status 與來源修訂狀態，再依排程維護流程處理。不要手動修改 receipt/hash，也不要拿舊 receipt 代替本輪結果。這些 lease 只比較同一連線的 `data_version` 與來源檔案 stat，不會持有整輪 SQLite transaction，也不建立 durable generation；sidecar 與 SQLite 仍不在共同原子交易內，所有 ABA 情境亦未排除。

缺少自然成熟 evidence 時，receipt 仍只證明工程 provenance 與當次 projection，不會自動 promotion、產生自然證據信用或下單；看到 identity conflict、future row 或 hash mismatch 時，應停止採用該 projection，保留 rule-only 結果並處理警告。

### 6.5 結果後續操作

保存時會沿用本輪 sealed execution 的 Profile／設定、決策日、候選列、母體與負面證據，不再從推薦服務的「最新一次執行」狀態補資料。送推薦回放會傳送獨立設定快照，後續修改畫面設定不改已送出內容。歷史 as_of_date 目前是應用服務接點；若歷史產業篩選缺當時成分證據，回報 `industry_membership_pit_unavailable`，不能改用今日產業分類解鎖。

加入觀察清單只附上真實已保存且完成 canonical readback 驗證的推薦結果 ID；未保存的新分析不捏造 source_id。新一輪分析執行時，畫面保留上一筆完整結果；新 completed 結果套用後才清除前一筆保存身份，避免候選被錯接到舊結果。

- 「保存結果」：保存同一份 completed execution 的 canonical artifact，並以 exact `result_id` 查詢 verified readback；成功訊息會顯示保存 ID、artifact 位置、Profile、Regime、名單數與下一步入口。只有 readback 的 execution、payload hash、artifact、時間與名稱／備註都符合保存回條後，畫面才採用已保存身份。
- canonical 保存與 verified readback 成功後，系統會以同一份 execution 的股票代號建立既有自動選股清單；清單建立失敗是 soft failure，不回滾已驗證的推薦結果，畫面會分別說明清單未建立的原因。
- 「加入觀察清單」：只有選取列所屬結果已完成 canonical 保存與 verified readback，或已由完整 ID 單筆載入並重新驗證後，按鈕才會啟用。未保存結果會顯示停用狀態；即使從表格右鍵操作，也會由共用 handler 再次拒絕未驗證身份。寫入項目綁定該筆 `result_id`、股票代號、決策日與 sealed execution 的 universe snapshot ID/hash。WP2 的公司分類／產業指數來源事件是另一組身分：v2 顯示封存的決策日與行情資料日，分類狀態仍是 current-only、`PIT eligible=false`；舊 v1 或缺少行情日期的結果顯示未知，不用今日資料補歷史。若本次確實使用產業指數表現，來源區還會顯示同次 sealed observation 的來源 rowset、儲存方式／定位、列日期範圍、列數、欄位、rowset hash 與本機觀察時間。尚未保存時標為「僅本機觀測」；完成保存後以精確結果 ID 讀回才標示 canonical readback。`observed_at` 只代表本機讀取時間；`available_at`／`published_at` 仍未知，不能作官方可得時間或 historical PIT。若 observation 缺失、雜湊／echo 不符或時間欄矛盾，畫面保留 unknown 並提示檢查同次事件或重新產生，不會再讀目前 CSV/SQLite 替舊結果補值。若同一股票／結果身分已存在，畫面會說明未新增且既有來源連結未變更，不會聲稱已重新綁定。
- 「送 Research Lab 批次回測」：用推薦名單建立批次研究輸入。
- 「送 Research Lab 推薦回放」：重播整套推薦 Profile / Config 在歷史期間每個決策點會產生的推薦，不是只拿今日名單回測。回放結果可保存為 Research Run / Evidence，再由 Registry 與 lifecycle gate 判讀 promote / hold / demote_candidate / retire_candidate；目前不會從推薦頁直接自動降級或刪除策略版本。
- 表格右鍵「記錄到持倉管理」：只有推薦結果已 canonical 保存並 verified readback 才能記錄；來源必須是同一份封存 execution、保存回條與選取股票，保留結果 ID、候選身份、artifact 位置及 payload hash。未提供的校準／機率資料維持不可得，不會用畫面文字或舊結果補值。
- 「匯出 Excel」：建立包含元數據、今日推薦配置、Regime 狀態以及推薦股票名單的 Excel 報告，並在背景執行原子寫入。

#### canonical 保存、重試與來源追溯

1. 在「推薦分析」完成一輪分析後，按「保存結果」並輸入結果名稱。
2. 畫面先用唯一推薦 execution ID 寫入 canonical artifact，再查回該 ID 驗證 execution、payload hash、artifact、保存時間與本次名稱／備註；只有驗證通過才顯示保存完成並建立自動選股清單。
3. 若 artifact 已發布但索引尚未完成，畫面會提示索引待重試；再次按「保存結果」會沿用首次名稱／備註，並以相同 result ID 呼叫保存服務修復索引。若保存已回條但 readback 失敗，重試會先查回同一 result ID，不重複寫 artifact。這些未驗證狀態都不建立選股清單。
4. 已完成保存的 execution 再按「保存結果」只顯示已保存資訊，不會重寫結果或重複建立自動選股清單。選取其他股票時， Portfolio 來源摘要仍需與目前 verified result、execution item 及保存回條一致。
5. 若同次保存的個人模式快照已驗證為 `personal_calibrated_probability`，canonical readback 成功後會在背景建立個人模型擷取並重新讀回核對，檔案保存在本機 `OUTPUT_ROOT/personal_prediction`。這是保存同次已驗證推薦與模型來源的封存，不會重跑推薦。
6. 若當次實際採 `rule_only`，畫面會說明本次沒有個人模型擷取；若舊結果沒有當次政策快照，模式會標為未知，不會套用目前設定補寫歷史。個人模型擷取失敗不影響已保存推薦，也不會重建自動選股清單；可對目前核實的結果或輸入完整 ID 讀取的已保存結果按「建立／重試個人模型擷取」。相同內容的重試會讀回既有擷取；若保存內容不一致，系統拒絕覆寫。
7. 一般 Qt 手動推薦沒有個人化 scope／request identity，因此此保存流程不建立個人化送達 ACK；保存成功不等於已送達、採納、接受或交易。若 execution 帶有個人化 scope，畫面會明確提示 ACK 目前不可由 Qt 保存流程提供，後續送達紀錄由 R015 負責。

操作限制與排錯：

- 若顯示「保存或 verified readback 失敗」，先保留畫面中的 `result_id` 與完整錯誤；再次點擊會依目前狀態重試 readback，或沿用首次名稱／備註修復索引。不要刪除 canonical artifact、索引或改寫 hash。
- 若推薦保存成功但自動選股清單未建立，推薦結果仍已驗證保存；依訊息檢查 Universe service 或輸出路徑，再從下次完整推薦保存建立新的清單。
- `manual_qt_snapshot=true` 只標記來源，不代表資料品質、策略驗證、個人化送達或交易權限。
- 保存與跨頁追溯都是 research-only；不會下單或自動調整持倉。個人化 ACK、接受狀態及 broker order 由各自授權流程處理。

### 6.6 鍵盤與圖表文字替代

推薦／回測結果中的淨值與回撤折線圖若使用快速 Canvas renderer，可先聚焦圖表，再用方向鍵、Home、End 移動目前資料點。交易報酬與持有期間 histogram 不支援鍵盤逐點瀏覽；按「顯示數值」可展開同一份 payload 的日期、數值或區間筆數。Smart Money 主表與分點追蹤表可用方向鍵或 Tab 瀏覽，Badges 與近期趨勢圖形欄也提供可朗讀的文字數值替代。

### 6.7 官方市場與技術條件研究

在「推薦分析」的來源頁籤列選擇「官方市場與技術條件研究」。窄視窗若看不到此頁籤，使用頁籤列的左右箭頭移動，再點選頁籤；研究頁的條件與明細可以向下捲動。本頁使用已保存研究來源，不會因開啟頁面自動產製新資料。

1. 按「選擇保存來源資料夾」，指定包含研究封套的根目錄，再按「更新來源清單」。來源清單可用「下一頁候選」繼續盤點；選取一份保存版本後，按「核驗並開啟所選保存版本」。若尚無合格封套，清單為空，不能靠修改門檻產生來源。
2. 設定母體範圍、官方市場／處置狀態、指定股票代碼，以及技術、四均線、KDJ、波動率條件，再按「套用條件並重新全域查詢」。只改輸入控制不代表既有結果已重新查詢；「清除條件」可重設條件。
3. 用「上一頁／下一頁」瀏覽同一份全域排序結果。選取股票後，按「查看保存事實與原因」閱讀完整保存事實；向下捲到末尾，再按「返回原結果頁」，原頁與選取會保留。
4. 可跨頁「加入比較籃」，用「顯示 2–5 檔保存事實」比較同一來源與查詢中的保存資料；「從比較籃移除」只改比較狀態。
5. 按「準備研究收藏」後，主視窗會在背景保存已核驗的研究狀態；先確認頁面中的保存成功訊息。到「觀察清單」選取該收藏，按「查看選中個股研究報告」或雙擊該列，即可沿保存身份重新核驗來源並重開研究頁。重新啟動程式後，仍由觀察清單開啟。

| 參數 | 意義 |
|---|---|
| 母體列範圍、官方市場／處置、指定代碼 | 先限制保存母體；群組 OR 不能繞過這些外層條件。指定代碼以逗號或空白分隔，需勾選「只查指定代碼」。 |
| 技術條件及規則間 AND／OR | 每條規則可選「符合／不符合／未知」保存狀態；規則間合併與四群合併分開設定。 |
| 四均線、KDJ | 依來源保存狀態篩選；沒有可核驗資料時保持未知。 |
| Bandwidth、ATR14 SMA 範圍 | 單位為 percent，以十進位字串輸入；空白代表該端不設界限，不代表零。上下界需有效且順序合理。 |
| 啟用群組 AND／OR、未知政策 | 決定技術／四均線／KDJ／波動率群組如何合併，以及未知列納入、排除或只看未知。 |
| 全母體排序、每頁列數 | 排序作用於完整查詢結果；每頁 1–256 列，翻頁不重新選來源。 |

結果中的來源完整性、宣告／納入／已處理／排除／待處理母體，以及可見列數是不同概念；本頁列數不代表推薦入選數。來源若標示 `current_only`、coverage 不完整、官方可得時間未知或歷史 PIT 不適用，這些限制會保留，不因收藏或重開而升級資格。結果、比較與收藏只供研究，不產生 Advice、交易指令、獲利機率或已驗證收益。

收藏保留原查詢、全部來源身份、排序、頁碼、選取股票、比較籃順序及捲動位置。重新開啟時會重新讀取並核驗相同來源；資料缺失、身份或雜湊不符時拒絕，不改用最新來源，也不改寫舊收藏補齊未知。

排錯：來源清單為空時先核對所選根目錄與保存封套；查詢拒絕時保留狀態訊息，核對輸入範圍、來源身份與完整性；背景工作可按「取消背景工作」並等待工作結束。收藏失敗時先核對觀察清單儲存模式與頁面的保存訊息。原來源唯讀時，必須依第 7 章的明示私人儲存流程處理，不直接修改來源檔案或略過遷移確認。

翻頁、重新查詢與返回原頁都由背景讀取處理。取消後保留最近一次已核驗結果，晚到結果不會替換目前畫面；已開始的檔案讀取須安全收尾，不能把按下取消解讀成工作已全部停止。請等待背景工作結束後再重試，若來源缺失或核驗失敗，依狀態訊息處理原保存來源，不改用最新資料。此流程沒有新增參數；目前尚未通過完整千檔效能與新版 EXE 驗收。

本輪已驗固定合成來源的窄窗主視窗與新程序重開；目前仍未驗新 EXE、真人操作、960px 視窗或完整私人 COW 旅程。詳細接受界線見 [具名 QA](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。

## 7. 觀察清單與選股清單

候選池「編輯收藏理由／已確認查看／稍後查看」在已啟用個人儲存且來源身份可核驗時，保存原個人 Watchlist revision；理由沿原備註、查看狀態沿私人 extension，重新開啟仍可讀回。只讀／未啟用模式不可保存。取消理由對話框或切換來源不保存；衝突須重讀並核對來源，不能覆寫晚到版本。理由上限 4096 字元，不能包含 NUL。「稍後查看」是保存的查看狀態，不會建立排程提醒。變化只比較兩份明示且相同股票／來源／帳戶的保存快照；資料不足維持未知，不使用今日行情補舊資料。此接線不自行核准正式個人儲存啟用。

### 候選股分析與跨頁下鑽（2026-09-06）

桌面寬度下，畫面固定為兩個主面板：「觀察候選池」在左側負責刷新／新增／移除／清空、候選表格、個股研究摘要與下一步動作；「已保存選股清單」在右側負責選取清單、預覽股票及載入／新增／編輯／刪除。候選池操作不再獨立佔一欄，清單與個股預覽共享右側高度；窄版才切回上下排列，仍維持先看候選池、再看已保存清單的順序。

進入觀察清單、切換視窗寬度或再次返回時，只顯示頁內候選池，不會另跳出「研究候選池」提示視窗；個股研究報告由對應按鈕切換至主程式「個股研究」頁，頁面說明仍由說明按鈕開啟。

點選已保存的「選股清單」，會直接列出該清單的股票代號與名稱，不必先加入候選池。單擊預覽股票可讀取分析摘要，雙擊可下鑽主力流向；預覽本身不修改清單或候選池。

在上方「觀察候選池」選取一檔股票，下方摘要會讀取已保存推薦的分數、理由及分析日期。有推薦來源 ID 時使用該次保存結果；沒有來源 ID 時使用最近保存的一份推薦，並明示來源與日期。這是當時策略的分析快照，並非即時行情或重新評分；沒有結果、未包含該股、日期缺失或晚於查詢日期時，顯示缺件原因，不推論為看空。讀取失敗可刷新重試；若尚未保存推薦，先至「推薦分析」完成並保存分析。

按「查看選中個股分析／主力流向」、雙擊股票或使用右鍵選單，即可前往「市場探索 → 主力流向」。股票即使未進入目前掃描榜，仍會查詢個股分點資料；不補造主力分數。資料日與週期沿用主力流向頁，沒有可用分點時明細為空，不能解讀成沒有交易。多選時須先改為單選，批次回測仍使用原有「送 Research Lab 批次回測」入口。

### ML 現況與查看位置

ML 的模型訓練位於 `ml_module/allocation_training_service.py`，凍結模型的推論由 `app_module/ml_allocation_inference_service.py` 轉為整數基點配置提案；配置服務另檢查 promotion 授權。模型產物存在不代表已介入正式推薦或持倉，UI 也不執行訓練。

畫面入口為「決策工作台 → Evidence／Research Console」：Development Pipeline 查看 Dataset、Rule Baseline、ML Challenger 與產物；Safety Boundary 查看正式 ML、alpha 與 Rule-only 狀態；Evidence／Source Gates 查看缺件。Runtime 與數據更新的排程狀態可協助判讀工作執行，但排程成功不等於模型獲准使用。

2026-09-06（美西）本次唯讀檢查：目前 process 的 `RESEARCH_CONSOLE_PROJECTION` 指向 2026-07-14 產生的開發投影，scope 為 historical research seen development data，alpha=0、四項 apply flags=false。實際呼叫 ResearchConsoleSourceService.inspect() 回報 degraded／projection_stale。預設正式 output 的舊 scheduled readiness 日期為 2026-08-14；另以台北 2026-09-07 00:00 作查詢 cutoff 重跑正式 input 唯讀檢查，結果仍為 0/3、waiting_for_formal_inputs，三項配置的 prospective input 尚未正式發布：非現金因果帳本、正式 Rule 快照歷史與 PIT 產業成分。新報告僅寫入 repo 的 `output/watchlist_analysis/ml_readiness_current.json`，沒有啟動訓練或修改正式產物。需要最新 ML 畫面時應由既有受控流程產出新 sanitized projection，再更新明確設定；不能只修改 generated_at 或解除 alpha 掩蓋過期。

2026-09-27 較早檢查點的個人模型狀態：當時來源/PIT admission 尚未取得獨立官方歷史可得時間證明，也尚無使用者指定來源信任；兩個 `legacy_unproven` 舊候選不可啟用，個人模式保持 `rule_only`。其後使用者已明確選擇 V2 指定 SQLite 的個人研究信任流程，詳見 9.9.1d；該聲明仍不是官方歷史 PIT／publication availability 證明。WP2 company-registry sidecar 的 `available_at` 是本次 HTTP response capture 完成時間，不是官方公告／publication 時間。個人結果操作詳見下方「個人推薦模型擷取與自然結果」。

#### 7.0.1 Current-restated 年度研究資料、Outcome Direct 與推薦學習操作（2026-10-03）

本節說明受控研究路徑：以已驗證的 readonly SQLite snapshot 建立年度 raw shards，產生 outcome-only Direct 數值與標籤，訓練並重新載入研究模型，再由 Legacy、Pipeline 或 Bank Taiwan 學習入口使用已釘選模型建立 source-row sidecar。研究樣本是 B 與 Direct 驗證的來源列（目前例為 2317、2330），不是推薦清單。本節 G6 與受控 current-restated 研究輸出都應放在 configured active research root 的唯一執行目錄；不得寫入正式資料根、正式模型或 release pointer。實際 CLI 參數以各入口的 `--help` 為準，來源收據與 hash 必須取自同一份已驗收產物，不可自行改寫清冊來符合參數。 下方 `<active研究根>` 請先在 repo 以 `.\.venv\Scripts\python.exe -c "from data_module.ml_research_output_boundary import get_ml_research_root; print(get_ml_research_root())"` 取得；本機設定方式見本手冊「研究儲存位置與容量排錯」。歷史已驗收的 C 槽路徑範例保留原 pin，不能改成 D 槽後重用舊 hash。

Current-restated 保留歷史事件日期，同時保存當前觀測、修訂依賴驗證及衍生完成的實際時鐘。這些時鐘不能互相替代；匯出時間不是歷史公告時間，未知公告時間仍是未知。這是以現今可驗資料做的年代順序研究，不具歷史 PIT 或正式 OOS 資格。一般 PIT 型別仍拒絕不符合當時可得性的特徵。

**取得 typed source context 與 current vector**

先用 `data_module.ml_daily_price_revision_gate.load_verified_current_restated_source_context()` 讀取已釘選的 snapshot DB／receipt，並以原始來源 DB、兩份檔案的實際 bytes SHA、當下含時區的 `decision_at` 與 `training_as_of` 驗證 namespace 與實體 dependency closure。接著由 `ml_module.current_restated_research_bridge.save_verified_current_restated_context_file()` 將 typed context create-only 保存到新的 `<active研究根>/<唯一執行目錄>`；記錄它回傳的檔案路徑及 bytes SHA，再用 `load_verified_current_restated_context_file()` 重新驗證後才能交給 fit。資料選取時鐘、context 的再次驗證時鐘與真正模型 fit cutoff 是不同時鐘；不能以 snapshot 完成時間、資料日期或 QA readback 手工拼一份 context JSON。

已接受的輸入邊界為 `output/ml_research/integration_20261002/source_snapshot_20261003T002224799623Z/`（snapshot DB actual SHA `6dbc12a50c3ab84d5021e68c2e5458e3ec129137d8d76b77fafe9f795a8875b2`；receipt bytes SHA `83e9fd7a2107af7ebd988ae53ad3a4bcc73e7f51d0f98a6fde2a57b39ddef784`）、`annual_current_restated_20261003T024252809641Z/runs/current-restated-1c2e9c5f0ea133fd47bfd823/`（publication／Core dataset bytes SHA `507041d1a174f178e7a88d84fc2e01f12ebd618cb6e2bc78ae2e74c03e69a511`／`83408f8ea7c00b151bb15662deb96bf437d5b535e12bab68b0050e54ebf07c30`），以及 `current_restated_direct_20261003T032031415703Z/runs/current-restated-outcome-196e0cff4d2cffaf22d4e083/`（manifest bytes SHA `04b39a482cd9a40ebba0b06b1f3e63a17cf6cd04a2fc3c8221a2ce107f894471`）。這些是受控 run 身分範例；再次執行必須使用全新輸出目錄並重新釘選當次 bytes，不能把歷史收據套到更新後的來源。

Current 向量由 `data_module.ml_research_direct_ooc_adapter.load_verified_ml_research_numeric_artifact()` 讀取 B immutable numeric artifact，再由 `ml_module.current_restated_research_bridge.verify_b_current_vector_against_core19()` 以 verified Direct observation／registry、source rows、masks、日期與 B receipts 建立 19 欄 CORE pack。若沿 CLI 推論，`--inference-vector-json` 應使用此受控 bridge 輸出及它的外部 bytes SHA；不得手寫值、把 49 欄 Direct 當成 CORE19、把 2317／2330 冒充當日推薦 cohort，或用沒有成熟標籤的 10/2 樣本製造推論回報。

**1. 建立唯讀驗證的年度 raw shards**

先確認 snapshot DB、snapshot receipt、原始來源 DB 與各自的實際 bytes SHA-256；選用新的、尚不存在的研究輸出目錄。CLI 入口是 `scripts/build_ml_pit_year_shards.py`。Current-restated 必須明確啟用研究模式，並同時提供 snapshot 及原始 DB 的身份資料：

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_pit_year_shards.py `
  --database <已驗證的snapshot.db> `
  --output-dir <active研究根>\<唯一raw執行目錄> `
  --decision-at <含時區的ISO-8601截點> `
  --history-start-date <YYYY-MM-DD> `
  --years 2023 2024 2025 2026 `
  --symbols 2317 2330 `
  --current-restated-research `
  --snapshot-database <已驗證的snapshot.db> `
  --snapshot-receipt <snapshot收據.json> `
  --expected-snapshot-database-sha256 <snapshot資料庫bytes SHA-256> `
  --expected-snapshot-receipt-sha256 <snapshot收據bytes SHA-256> `
  --original-source-database <原始來源資料庫.db> `
  --data-selection-as-of <含時區的ISO-8601資料選取截點> `
  --batch-size 512 `
  --temporary-storage-budget-bytes <臨時空間上限> `
  --persistent-storage-budget-bytes <持久空間上限> `
  --safety-reserve-bytes <保留空間>
```

將 `--database` 與 `--snapshot-database` 指向已驗證的同一份 snapshot。`--expected-*sha256` 必須是指定檔案目前的 bytes hash。`--data-selection-as-of` 是來源選取截點；它不是模型 fit freeze，也不能把它當作每列特徵的歷史 available-at。Current-restated 的 `--years` 依事件日期年度分片，manifest 會記錄 `event_date_calendar_year`；不要套用一般 PIT 按可得時間分片的解讀。正式執行前先用 `--help` 確認當前參數及資源限制，並維持足夠的安全保留空間。

**2. 建立 Outcome Direct 數值、標籤與合格 folds**

對 raw publication manifest 及 Core dataset manifest 讀回 bytes SHA 後，執行 `scripts/build_ml_current_restated_outcome_store.py`。目前受控 profile 使用 2317、2330 與 TAIEX，最低 125 個 purge 後訓練交易日、63 個測試交易日、60 日 purge 及 5 日 embargo：

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_current_restated_outcome_store.py `
  --raw-publication-manifest <raw發布清冊.json> `
  --expected-raw-publication-manifest-sha256 <raw發布清冊bytes SHA-256> `
  --expected-core-dataset-manifest-sha256 <Core清冊bytes SHA-256> `
  --output-dir <active研究根>\<唯一Direct執行目錄> `
  --target-symbols 2317 2330 `
  --benchmark-entity-id TAIEX `
  --minimum-train-dates 125 `
  --test-date-count 63 `
  --purge-trading-days 60 `
  --embargo-trading-days 5 `
  --max-raw-rows 1000000 `
  --repository-root <repo>
```

這些值是研究 lane 的最低門檻；不得為了取得成功退出而降低。Direct 清冊應能追溯原始 raw manifests、feature registry、來源列、masks、標籤及實際全域交易日曆。若可用樣本、標籤成熟度或真實日曆不足，維持 blocked/null 並調查來源，不得造 fold 或把缺值改為 0。

Outcome 標籤的 `benchmark_excess_return_bp` 是股票 gross 報酬減 benchmark gross 報酬，再扣標準模型目標成本 80 bp（買進 25 bp、賣出 55 bp）。此成本只定義模型目標，不等於實際成交成本，也不是 Legacy 或 Bank 的成本輸入。

**3. 訓練並保存 bounded research 模型**

`scripts/train_bounded_restated_research.py --help` 列出完整入口。下列來源 context、Outcome artifact、B 消費收據及 model output 都必須以已驗 bytes SHA 釘選；符號、事件日期和 B freeze 必須與同一研究 cohort 相符：

```powershell
.\.venv\Scripts\python.exe scripts\train_bounded_restated_research.py `
  --fit-current-restated-outcome-artifact <Direct outcome artifact> `
  --expected-outcome-artifact-sha256 <Outcome artifact bytes SHA-256> `
  --expected-raw-publication-manifest-sha256 <raw發布清冊bytes SHA-256> `
  --expected-raw-dataset-manifest-sha256 <raw dataset清冊bytes SHA-256> `
  --expected-outcome-feature-registry-sha256 <Outcome registry SHA-256> `
  --source-context-file <source context.json> `
  --expected-source-context-sha256 <source context bytes SHA-256> `
  --b-consumption-receipt <B消費收據.json> `
  --expected-b-consumption-receipt-sha256 <B收據bytes SHA-256> `
  --expected-b-candidate-manifest-sha256 <B candidate SHA-256> `
  --expected-b-adapted-manifest-sha256 <B adapted SHA-256> `
  --expected-b-feature-registry-sha256 <B registry SHA-256> `
  --b-current-observation-freeze <含時區的ISO-8601觀測截點> `
  --current-symbols 2317,2330 `
  --current-event-date <YYYY-MM-DD> `
  --output-directory <active研究根>\<唯一模型目錄>
```

`--b-current-observation-freeze` 是 B 來源觀測的 freeze，不是訓練時間。Trainer 以實際 UTC 時鐘建立 fit 時間與模型收據；不得用歷史時間或未來時間覆寫。保存後記錄 model manifest、bundle、feature registry、training audit 與當次完整 code pins。

**4. 在新 Python process 驗證模型並推論**

對每個符號準備受驗證的 inference vector JSON，讀取其 bytes SHA，再各自以新 process 執行下列命令。模型 manifest、bundle、vector 檔案與 vector bytes SHA 都必填；`--inference-at` 可明確指定含時區的當下 ISO-8601 時間，省略時程式使用實際 UTC 現在時間：

```powershell
.\.venv\Scripts\python.exe scripts\train_bounded_restated_research.py `
  --verify-current-restated-model <model manifest.json> `
  --expected-model-manifest-sha256 <model manifest bytes SHA-256> `
  --expected-model-bundle-sha256 <model bundle bytes SHA-256> `
  --inference-vector-json <該symbol的inference-vector.json> `
  --expected-vector-sha256 <vector bytes SHA-256> `
  --inference-at <含時區的當下ISO-8601時間>
```

省略最後一個參數時由程式採用真實 UTC 現在時間。不得用歷史時鐘偽裝現在推論，也不可把舊 code pins 的模型與新版本程式混用。若預測值為負，應依模型目標的基點語意判讀；它不是賣出指令或投資建議。時間或來源 pin 不符時應停止並重驗相同模型與輸入，不要手動改收據。

**5. 使用 Legacy、原學習 Pipeline 或 Bank Taiwan 的研究 sidecar**

三個 wrapper 入口分別為 `scripts/scheduled/run_daily_recommendation_learning.py`、`scripts/scheduled/run_daily_recommendation_learning_pipeline.py` 及 `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py`。三者需使用同一組研究輸入、模型及輸出根目錄。`--current-restated-research-only` 只選擇 source-row research sidecar，不會訓練模型，也不會解除正式 calibration、teacher、PIT 或決策資格限制。

三個入口共用以下研究參數；值必須與同一次已驗收的 source context、Outcome Direct、B receipt 及 model 相符：

| 參數 | 用途 |
| --- | --- |
| `--research-context-file`、`--research-context-sha256` | source context 路徑及其 bytes SHA-256。 |
| `--research-outcome-receipt`、`--research-outcome-receipt-sha256` | Direct outcome receipt 路徑及 bytes SHA-256。 |
| `--research-raw-publication-manifest-sha256`、`--research-raw-dataset-manifest-sha256`、`--research-outcome-feature-registry-sha256` | 綁定 raw 發布、raw dataset 與 Direct registry。 |
| `--research-b-consumption-receipt`、`--research-b-consumption-receipt-sha256` | B 消費收據及其 bytes SHA-256。 |
| `--research-b-candidate-manifest-sha256`、`--research-b-adapted-manifest-sha256`、`--research-b-feature-registry-sha256` | 綁定 B 原始 candidate、adapted manifest 與 registry。 |
| `--research-model-manifest`、`--research-model-manifest-sha256`、`--research-model-bundle-sha256` | 綁定已保存模型；wrapper 驗證並重用模型，不在 sidecar 內重訓。 |
| `--research-current-symbols`、`--research-current-event-date` | 指定經 Direct 與 B 共同驗證的來源符號及事件日期。 |
| `--research-b-current-observation-freeze` | B 來源觀測的含時區 freeze。 |
| `--research-inference-at` | 可選的含時區推論時鐘；省略採實際現在時間。 |
| `--research-output-root` | 位於 configured active research root 內的新研究輸出根；舊 repository 根在切換後僅供唯讀。 |

Legacy 使用 `--cost-scenario legacy_fixed_bp --fixed-round-trip-cost-bp 50`，且不接受 upstream terminal 參數。Pipeline 入口另接受四個推薦 snapshot **參考旁證**參數：`--research-reference-snapshot-result-id`、`--research-reference-snapshot-cohort-hash`、`--research-reference-snapshot-output-path`、`--research-reference-snapshot-output-sha256`。推薦 snapshot 不是訓練樣本；若其中沒有 2317／2330，不得描述成 cohort match。啟用 `--current-restated-research-only` 時，Pipeline 會在日常 producer 前返回，只唯讀驗證推薦 snapshot 參考旁證、啟動 Legacy research child，並寫入研究 sidecar 收據；不執行日常 producers 或 snapshot 工作。未啟用研究模式時，正式預設仍走原日常流程。研究分支會寫入隔離研究產物，因此不能稱為全程唯讀或僅供模型驗證的指令。

Bank 必須在 Legacy 成功且已驗證的 terminal receipt 上執行，並提供三個上游綁定參數：`--research-upstream-terminal-receipt`、`--research-upstream-terminal-receipt-sha256`、`--research-expected-upstream-binding-sha256`。它會核對 receipt bytes、binding、研究 cohort、模型及來源 pins；任何不符即拒絕，不能以另一個 Legacy 執行或不同模型的 receipt 替代。Bank 成本輸入包括 `--cost-policy-estimate-date`，以及二選一的 `--research-order-quantity-shares` 或 `--research-order-amount-twd`；另外指定 `--research-order-lot-type full_lot` 與 `--research-instrument-type ordinary_stock`。成本估算日期是政策參數，應依受控作業明確設定，不是系統自動認定的通用交易日。

Legacy 的固定 50 bp 假設與 Bank 依真實 T+1 買賣價格估算的費用、稅及 round-trip 成本，都是各自 sidecar 的成本情境。兩者讀 gross 價格標籤，不再重扣模型 target 已扣的標準 80 bp；估算成本也不代表實際成交回報。未成熟或缺 entry／exit 價格時，相關結果應為 `null`／未成熟，不能以 0 代替。Sidecar terminal `verified_research_sidecar` 只表示研究輸入及模型重用的收據綁定通過，不代表正式校準、模型訓練、historical PIT、decision-time eligibility 或正式批准。缺 teacher 時完整 allocation 仍 blocked；不可假造 teacher 或將 outcome prediction 宣稱為投組配置。

**結果判讀與排錯**

- SHA、binding、source context、code pin 或 Bank upstream 驗證失敗：停止流程，保留原檔與錯誤輸出，重新核對同一 publication、receipt、model 及輸入向量。不可改 manifest/hash、略過 gate 或借用舊模型。
- 輸出目錄已存在：為下一次受控嘗試建立新的唯一研究目錄；研究產物採 create-only，不要刪除或覆寫先前收據。
- fold 數、歷史涵蓋或 label maturity 不足：依實際來源缺件調查，保持 blocked/null。不得降低 125／63／60／5 門檻、壓縮全域日曆、放寬 purge／embargo 或將缺標籤填成 0。 新日曆資格版本接受至少 905 個完整來源交易日，實際數量與全日曆 SHA 綁定 verified Direct manifest；超過 905 日不截短成固定長度。每 fold 至少 125 個成熟訓練日、63 個測試日、60 日 purge、5 日 embargo，且至少四個合格 fold，仍在 fit 前驗證。只有資料真的缺少成熟 fold 才屬累積等待，來源／格式／路徑錯誤仍列工程失敗。
- PowerShell 執行 Unicode `--help` 時若遇到 cp1252 編碼錯誤，先設定 `$env:PYTHONIOENCODING='utf-8'` 再讀 help；這只影響終端輸出編碼，不改變模型或資料。
- 原始資料時鐘、模型 fit／inference 時鐘及 Bank policy estimate date 是不同欄位。不要以檔案修改時間、匯出完成時間或 policy date 推定來源公告時間。

模型讀取或來源失敗時必須保留規則結果，不以 0 或錯誤機率替代未知值。已隔離的同源 V1／Derived V2 artifact 不得別名成 current-restated CORE19；Unicode 不合法、pointer 缺失、版本不相容或 manifest I/O 失敗時依既有 consumer／loader contract 回退到 rule-only 或 blocked，不切正式 pointer。ML preflight 的 `deployment_path_ready` 只代表部署路徑可讀，必須另看 `model_source_ready` 與具體 quarantine blocker；路徑存在不等於模型來源通過。

2026-10-03 最終受控 ML receipt 為 `root_phase3_ml_acceptance_20261003T070413001284Z.json`，SHA `007d245a4228d9f260ef3e4fd39373ce3eb4c62dac8129e88e29f33f2f8afc9f`；最終 research model 位於 `output/ml_research/integration_20261002/current_restated_core19_phase3_20261003T064855260194Z/`，manifest SHA `f4f8b70f2da3515089007698c44497ca32fa7b56258cec8880e62e8aa6fe2e2b`。root 獨立核對 16 個 code pins、12 項實際 evidence 及 13 項語意檢查，包含兩個新 Python process、原 Legacy→Bank 研究 sidecar、四筆成熟歷史成本及 55 個 protected formal／V2 檔未變。current-restated 是 research-only／non-PIT；沒有 Formal 校準、teacher、promotion、交易權限或投資效果接受。同一版本的跨頁 51-test 已通過。c625 原生 UI 驗收 receipt `output/qa/integration_20261002/phase3_native/root_native_final_acceptance_20261003T105541987127Z.json`（SHA `483170b2c330b0121ce51435ff7a5966b073e2082c846289f56d33cade0597b6`）以 43 筆實際觀測 pins、兩個成功正常關閉 sessions 與具名檢查接受 baseline 及 125% 成本情境；不應把 43 筆觀測說成 43 項全數通過。取消、重試與保存沿用 7eb 版本中未變的 Recommendation 程式既有觀測；c625 本次新驗的是成本情境結果 `rec_3e78a92cdfc04edf9f18618747fa0c29` 重開與新程序讀回。該收據不代表 current-restated ML 取得 Formal、PIT、teacher、promotion 或交易資格；c625 的 1017×768 縮放嘗試未成功，先前 7eb 版本的窄視窗觀察不重標成 c625。整體範圍與限制見[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。

### 7.1 候選池操作

#### 候選池觸發提醒與推薦來源（2026-09-21）

首頁「今日待判讀」與每日決策會列出候選股的股票代號、觸發原因、資料日及資料品質。提醒來自既有指標快照，不會因查看而重新評分；「兩筆」表示兩檔候選出現符合規則的指標變化，不是兩筆成交或兩項待簽核文件。

- **分數新達觀察門檻**：前次低於門檻、目前達到門檻。查看價格／技術與原推薦理由是否支持繼續觀察。
- **分數上升／下降**：目前仍達門檻，但相較前次分數改變；下降不等於跌破門檻或應賣出。查看量價與原推薦理由有無轉弱。
- **缺前次分數**：目前達門檻，但不能確認新轉強；先核對前次資料。原因缺失、不一致或只有總數沒有代號時，畫面明示缺件，不推測方向。

判讀步驟：點選首頁提醒查看完整說明，使用下鑽入口前往「候選池」，選取說明中的股票，再按「查看選中個股研究報告」。先核對資料日期與品質，再查看價格／技術、風險與原推薦理由，決定繼續觀察或記錄疑慮。「已查看」仍只表示本次 UI session 看過提醒，不代表已批准交易或完成風險確認。

觸發服務預設門檻為 `6000` 基點；目前 SQLite provider 以 `RSI × 100` 供應這個指標分數，即預設 RSI 60。這不是推薦總分、排名、股價漲跌或獲利機率。畫面只翻譯既有分類，不以目前預設門檻替舊快照補造當時數值；資料降級時應先確認顯示的資料日，刷新只會重讀可用來源。

候選表的「推薦來源」取代原本直接展示的 `decision_identity` 字典：

- **已連結原推薦**：保有指向該次推薦與該股票的識別資料，方便找回原理由及後續結果；不表示推薦正確、結果成熟或已成交。
- **未連結原推薦**：仍可研究該股票；要追溯特定推薦時，選取股票並按「選擇原推薦來源」。沒有可選結果時，先確認原推薦已保存。
- **來源不一致，需核對**：來源識別與該股票不一致，先核對原推薦，不靠相同股票或日期猜配。

完整識別資料保留於內部，研究報告的「決策 → 結果」技術詳情供追溯使用；它本身不是警示原因、評分或買賣訊號。

- 「新增股票」：手動輸入股票代號；系統會先用正式股票資料查找名稱，查不到的代號會被阻擋，不會混入正式觀察清單。
- 「移除選中」：刪除選取列。
- 「清空候選池」：刪除全部候選，無法復原。
- 「刷新」：重新載入資料。

候選池保存來源、加入時間與備註，用於研究，不是實際持倉。

股票名稱由應用服務查詢；跨頁提供的 source_id／result_id 會保留，重複股票不新增。舊 JSON 損毀時保留原檔並顯示錯誤，請先檢查副本，不會自動換成空池。底層 SQLite 副本 helper 只接受 caller 指定 sandbox 內的 JSON；正式候選池仍不會在 UI 啟動時轉換，必須由下方一次性升級入口明確觸發。added_at 截止不代表已具備完整歷史候選池事件帳。

正式 MainWindow 啟動時只會以唯讀方式尋找 `OUTPUT_ROOT/watchlist/watchlists.db` 與其啟用狀態，不建立、重建或遷移資料庫。若 canonical DB 已有完整的 `watchlists.db.active` 啟用標記，後續觀察清單日常寫入只走 SQLite；保留的 JSON 不會再被雙寫。舊版已存在、且目錄中沒有 legacy JSON 的 Watchlist schema v2 DB 仍可作為明確的相容來源。

若仍使用 JSON，候選池頁會顯示「升級觀察清單儲存」按鈕。只有使用者明確按下後，系統才會先預檢所有 `watchlist/*.json`，在暫存 DB 完成全部清單的 migration、來源 bytes／payload／source hash 核對，再以不覆寫既有 DB 的方式發布 canonical DB 與 durable activation marker。原 JSON 不會刪除、改名或覆寫；任一清單失敗、來源在過程中改變、schema／核對或啟用標記失敗，頁面會明示仍使用 JSON 並可重試。重開程式時，沒有完整 marker 的 canonical DB 不會搶先成為 writer；修復後只有再次通過所有來源核對才會啟用。

### 7.2 選股清單

- 「保存為選股清單」：把目前候選池保存為可重用 Universe。
- 「載入到候選池」：把既有 Universe 載入目前候選池。
- 「新增 / 編輯 / 刪除」：管理 Universe 名稱、說明與股票內容。

「送 Research Lab 批次回測」可直接把目前觀察清單送到 Research Lab，並切到批次股票回測模式。若清單為空，按鈕會停用並在 tooltip 顯示原因；若要保存成可重用 Universe，仍可使用「保存為選股清單」。

### 7.3 個股研究報告

「價格／技術」的 K 線 hover 與十字線保留資料日、開高低收、成交量、原 MA 數值及事件／帳本含義；來源、可得時間與 SHA-256 留在資料稽核或精確表提示。保存版本與來源核驗不變，未知數值仍標示未提供。

Rule／ML 的 H5 `not_mature` 表示原保存實際結果尚未成熟，或仍待合格讀回；研究估計仍可查看，不能當成已驗證收益。個人 H20 預測與 H5 成本後超額分開：H20 是未扣成本的 20 交易日估計。可在個股頁上方查看獨立 H20 區塊，或從「推薦分析 → 個人模型選股研究（H20 毛報酬）」讀取每日已保存模型名單、選擇股票後開啟研究。模型資料暫時無法驗證時可重新載入重試，畫面保留來源診斷。 名單上方的來源身份與失敗時的完整錯誤明細皆可選取、複製並向下捲動；窄視窗中請在文字區內捲到末尾。重新核驗失敗或取消時，保留上次清單與選取；上次結果不代表本次已核驗。按「讀取每日已保存模型名單」僅重試原來源，讀取期間可按取消並等待背景工作安全收尾。

H5 成本後超額研究會列出原模型 manifest 所存成本情境，例如該模型假設總成本 0.8%（買進 0.25%、賣出 0.55%）；這是原模型假設，不代表使用者實際交易成本。缺少原成本契約仍顯示未提供，基準名稱與期間定義缺件亦不自行代入；H20 未扣成本估計另列。此呈現不重算原預測或模型。

由決策上下文開啟研究報告時，歷史行情 cutoff 使用該上下文的 `decision_date`，不以電腦今天或最新可用日期取代。若決策日期缺漏或格式不合法，報告會阻擋該歷史查詢；下鑽結果因此保持在原決策時點，不能解讀為即時訊號。

觀察清單與持倉管理共用主程式左側「個股研究」頁面，不另開彈出視窗。也可直接按左側「個股研究」並輸入股票代碼。報告是唯讀研究畫面，不會自動下單、不會直接修改持倉，也不會因為開啟報告而重新計算另一套股票評分。

在觀察清單選取一檔股票後，可按「查看選中個股研究報告」、雙擊股票列，或由右鍵選單開啟；在持倉管理選取一列後，可按「查看個股研究報告」、雙擊持倉列，或由右鍵選單開啟。未選取股票時，持倉按鈕會停用或提示先選取持倉。報告上方輸入代碼後按 Enter／「載入個股報告」可切股；從清單開啟時，上／下一檔只使用目前來源頁已有的股票代碼。按「重新載入」只重新讀取目前報告。

報告首屏顯示身份、查詢日、最新可用價格、關注理由、主要風險、資料更新狀態、既有 Advice 與來源狀態；詳細內容分為價格／技術、基本面／營收財報、籌碼／產業事件、持倉／Health／Exit、Rule／ML／歷史。來源表另顯示資料日、資料可得時間、來源 cadence、預期資料期與更新說明。

結論文字要區分規則理由與資料警訊。首屏既有「值得看原因」欄可能列出缺件或風險提示；當結論說明資料不足或需核對時，應以該結論及來源狀態為準，不把欄位名稱當成正向證據。若目前沒有可用價格或最新收盤缺值，摘要會以「資料不足，需核對：…」說明原因；其他來源警訊以「需核對資料：…」呈現。只有既有規則理由才會使用「值得深入核對」；資料缺件或 freshness 警訊不是正向選股證據。歷史 Portfolio Alert 仍優先顯示歷史提示，不代表現持倉。

2026-10-03 的 c625 原生觀察中，載入缺少最新可用價格的 9999 後，結論顯示「資料不足，需核對：缺少最新可用價格」，且先前 2330 報告內容已清除。這只確認缺件時的文案與跨股票內容隔離，不代表補齊價格或驗證個股來源；對應畫面記錄為 `output/qa/integration_20261002/phase3_native/observation_20261003T104832574Z_vc625_missing9999_new_copy_actual_pixels.json`（SHA-256 `56bc0690abf205920bff594d6c962ee0027c8d1aa397d2e5162f5bad865afbcb`）。

「籌碼／產業事件」依分點交易、法人、信用、集保股權分散、產業／事件分區閱讀。集保持股級距每列分別顯示持股範圍、人數、股數與占集保庫存比例；`—` 表示未提供，`0` 才是來源提供的零。第 15 級為 1,000,001 股以上，第 16 級為差異數調整，第 17 級為合計；調整列不是一般持股級距，不將它判讀為大戶。比例僅將來源整數基點轉成百分比，沒有重新計算持股或交易訊號。分級定義依 [官方資料標準附件](https://schema.nat.gov.tw/gsp/frontstage/resource.download/9f7d9184-20a0-49eb-b7dd-96e23686c4ef)。

目前研究可顯示另行核驗的法人、信用與集保觀測資料。從觀察清單選股票並開啟「個股研究」，在未指定歷史日期的目前研究查看「籌碼／產業事件」，再到來源表核對該筆資料日、來源資格及觀測時間。法人／信用使用候選資料庫中可重算雜湊、核對股票與數值的正規化觀測；集保使用官方原件與 manifest 重播。信用數量依來源單位顯示，不能把不同市場的股數／張數直接混加。

「目前觀測／非歷史 PIT」表示此刻能核驗這份資料，不表示決策當時已發布。`observed_at` 是本地觀測或讀回時鐘；來源未提供的公告／可得時間仍顯示未提供，不能拿觀測時鐘補成發布時間。保存的 Advice、明示歷史日期及模型訓練資格各自維持原契約，不會借用今天的新觀測補舊判斷。遇到原件雜湊、來源、股票、期別或時鐘不符時，該觀測不顯示數值；先查看來源診斷，再重試目前研究，不要改日期或關閉保護繞過錯誤。

自然更新沿用既有每日 Quick：法人與信用更新候選觀測；週一 TDCC 路徑另保存獨立官方原件至 `{OUTPUT_ROOT}/current_observed_market_ownership/tdcc/<capture-id>/`。這份原件有自己的擷取身份，不能說成較早 candidate DB 的同一次 HTTP 回應；每個 run 保留原始收據。週末、假日或官方尚未更換週資料時，報告日期可能合法維持上一期。原件抓取失敗與來源尚未發布分開判讀，排程 dry-run 不抓資料、不寫正式 EvidenceDB。

TDCC 既有手動重播使用 `scripts/capture_tdcc_shareholding_candidate.py --raw-file <既有原件> --output-dir <repo/output/內的新目錄>`，沿用原件 metadata 時鐘，不能附排程 run ID。`--output-root` 是 Quick 的保存入口，必須附 `--capture-id` 與該 Quick 的 `--scheduled-run-id`；它只接受新的官方 HTTP 擷取，不能將手動重播冒稱自然排程成功。完整 tier／aggregate 保留有界大小檢查，64 MiB 上限涵蓋目前官方全市場檔案。

事件列表先看日期、事件、品質與摘要，選取一列後於下方閱讀可換行的來源、原因、風險與後續結果。內部識別與原始欄位保留在提示中；未有中文對應的代碼會標示其他／未對應，不猜成投資結論。來源資料日與可得時間分開判讀。若級距格式無法解析，畫面會顯示格式提示並保留原始內容供查核，請重新載入或檢查來源明細，不把格式錯誤視為沒有持股。

價格／技術圖會明示圖表涵蓋範圍與最新涵蓋日；每根 K 線或折線點不一定是最新日。將游標移到資料點可查看該日日期、開高低收與成交量；原始資料缺少的欄位會顯示「未提供」，不會由畫面補造。

價格頁維持離線原生圖，不需要 TradingView 或 WebEngine。圖與開高低收／量等數值表共用同一份核對後資料；先看查詢截止日、實際涵蓋日與來源，再查看每列數字。歷史或保存來源切換保持原截止日，不借最新行情補舊圖；明確另開「當下獨立研究」時仍沿既有服務當下查詢日，返回保存決策恢復其原日期，pinned 日研究快照不改查當下。截止後資料與明示晚於截止日才可得的資料不顯示；來源缺少可得時間時保留未知，日期篩選通過不等於歷史 PIT 已合格。

服務回傳股號不符，或價格投影的已知日期／來源身份／行指紋核對失敗時，拒絕該份圖表及價格表，不沿用另一來源的數字；請核對來源詳情後重新載入原來源。沒有行指紋的舊 DTO 保留身份未知，不補造 hash。圖表初始化或填入資料失敗時，已核對數值表仍可閱讀；缺 OHLC 降為收盤線，缺量不補零。尚未具備完整股號／來源指紋的事件不冒充圖上已驗證交易標記。本批不新增縮放／平移或外部圖商整合。

#### 原生歷史 MA20／MA60（2026-10-06 限定接線）

在「價格／技術」頁查看 MA20（金色）與 MA60（藍色），下方歷史技術數值表提供同一日期、同一核對後序列的精確值；游標提示與表格提示保留來源／列指紋。只讀既有儲存指標，不重算均線或改研究策略。空值、缺列或缺收盤日處斷線，不插值、補零或重複末值；缺值原因未提供時不猜測是暖機不足。已有值也不代表暖機與歷史 PIT 合格。

歷史讀取限於價格圖日期與查詢截止日；未來或明示晚到資料排除，已知股號／來源／日期／hash 失配拒絕。保存／pinned 研究沒有同來源歷史序列時，畫面明示缺件，不能借最新 live 指標填線。單日指標快照仍獨立顯示；沒有合法序列就不畫歷史線。覆蓋線更新保留既有價格日期、模式、widget 幾何與游標，這不代表已新增可縮放或平移的 viewport。圖表填值失敗時，價格與歷史技術精確表仍可檢視。

歷史 Portfolio Alert 會保留事件日期與來源。它描述的是當時保存的警示快照，不是目前持倉清單，也不能單憑歷史警示推定現在仍持有該股票；請回「持倉管理」確認目前帳本與價格。

#### 市場資料與個人狀態分離（2026-10-06 已選 FA_Data/personal）

抓取的市場／來源資料與收藏、個人研究紀錄、筆記、記帳及持倉狀態必須使用獨立 root 與專用儲存；不同表或 `FA_Data/output` 下的另一個 DB 仍不足以防止整包帶出。未設定個人模式時，既有觀察清單與 COW 路徑仍在 `OUTPUT_ROOT/watchlist`。2026-10-06 新增明示個人模式，詳見本手冊末尾；正式來源尚未遷移，其他個人領域也未因本批自動分離。

以下為先前未選位置時的歷史候選；最新選擇已是 `{DATA_ROOT}/personal`，本次模型使用其 `recommendation_h20` 子樹，並非再次等待選位置。舊候選為 `%LOCALAPPDATA%/baldr/personal`，此電腦的候選完整值為 `C:\Users\archi\AppData\Local\baldr\personal`；觀察清單專用 DB 候選為 `C:\Users\archi\AppData\Local\baldr\personal\watchlists\watchlists.v3.sqlite`。若需 D 槽，另一候選為 `D:\Min\Python\Project\baldr_PersonalData\watchlists\watchlists.v3.sqlite`，兩者都在 `FA_Data` 外。上述候選不採用；本次已建立模型專屬子樹，觀察清單／其他帳本未因此搬移或切 writer。

未來個人路徑設定須獨立於 `DATA_ROOT`／`OUTPUT_ROOT`，不能為搬收藏而改整個市場來源根。activation pointer、conversion receipt、rollback audit、SQLite sidecar 及內容備份全部留個人 root；新的 reader／writer／fresh-process discovery 必須同步認識該路徑，不能只把 target DB 移到 C 槽而繼續在市場包寫 marker。現有 Portfolio JSONL 仍沿原 owner 路徑，本批不遷移。

市場資料匯出只允許明示的市場 DB／原始來源清單，不遞迴打包整個 `FA_Data` 或所有 `OUTPUT_ROOT`，也不附加個人 DB。排除整個個人 root，以及舊 `output/watchlist`、`output/portfolio`、個人 Journal／筆記、activation 設定、receipt／audit／backups 與相關 WAL／SHM。這是新要求與後續匯出驗證規則，尚未宣稱程式已實作防洩漏匯出；使用者未要求分享，本批不分享或上傳任何 DB。

正式遷移須先完成新個人路徑／marker discovery 工程與隔離測試，再核對單一來源、writer 時段、當下容量、實際寫入權限及批准。保留原 JSON 精確內容備份與 pin；回退只切 writer／pointer，保留新 DB、新 revision、雙來源與 audit，不合併、不刪檔。尚在市場 root 的 legacy 個人檔案仍須排除，不能只備份一份到 C 槽就宣稱市場包已乾淨。

每個來源依自己的可得時間與 cadence 判讀。每日行情依官方交易 session，月營收與季報依公告／可得 cadence；週末／假日的上一個官方交易日不會只因資料日早於查詢日就被標為過期。`current` 與合法的 `expected_wait` 只有在個股資料期與 receipt 預期資料期相符時才可保持 fresh，`stale`／`partial` 顯示過期或範圍不足，`failed`／`unknown` 顯示 partial／degraded。freshness receipt 缺失、損壞、日期或資料根不符時不採用，報告保留來源日期但更新狀態為未知，不把它猜成過期。基本面每表最多顯示 24 筆，先依報告期／資料日選最新期，再以可得時間選同一期版本，避免較晚取得的歷史 row 擠掉最新報告。

「缺資料」不等於零值或利空；法人／信用／集保、持倉、Exit、ML 沒有實際 provider 或 row 時不補假資料。Advice 只讀取既有已保存推薦，沒有合格來源時顯示不可用，不重新評分。切換股票時，舊 worker 的晚到結果會被丟棄，不會覆寫新股票。「返回來源清單」會回到來源頁並定位目前研究的股票，保留來源頁的篩選狀態。切換左側工作區會保留研究頁內容，再點「個股研究」可繼續閱讀；從其他清單開啟股票時會更新來源上下文並回到報告分頁。主程式關閉時會等待報告與決策結果的背景讀取安全收尾。若持倉返回上下文帶有 `result_id`，目前持倉列必須通過同一保存推薦結果的 exact 驗證；失配時不以同股票替代選取，狀態列會提示回推薦分析重新開啟正確結果。沒有 `result_id` 的既有 unlinked 研究仍維持單一股票代號返回相容行為。

若下鑽上下文帶有明示 `result_id`，報告另提供「決策 → 結果」分頁：依同一 `result_id` 與 exact `candidate_key` 顯示 Evidence、5／10／20／60 個交易日的連結／結果狀態、既有 Journal 與 Portfolio event。`已連結` 不代表 outcome 已成熟；`insufficient_future_data` 會顯示「尚待結果成熟」。缺少 `result_id` 時明示未連結，不以同股同日猜測；研究前瞻報酬與個人筆記／持倉事件分開，畫面唯讀且不建立交易。完整 result identity、event key 與來源 snapshot 收在收合的技術詳情中；Journal／Portfolio 缺件不阻擋推薦研究檢視。

當上下文同時帶有 exact `result_id` 與 `stock_code` 時，分頁下方會出現「研究動作（不採用 Advice／不下單）」：可按「納入研究」、「略過」、「記筆記」或用台北時間日期／時間選擇器「設定下次檢視」。目前研究狀態、筆記摘要與下次檢視會在重開報告後由同一份 append-only Journal 讀回；「已納入研究」或「已略過」意向不會被提醒動作覆蓋。缺少或衝突 identity 時，動作會停用並說明原因，不以同股同日或 `source_id` 猜測結果。儲存失敗會保留失敗狀態並提供相同 request id 重試；寫入成功但讀回失敗時只顯示「已寫入、讀回失敗」，不標成已驗證。完整 ID、revision 與歷史收在「顯示技術詳情」中；這些研究動作不採用 Advice、不建立 Portfolio trade，也不呼叫 broker。

2026-10-06 來源保存補正：由已核報告 context 明示的 `source_id` 隨新研究動作保存到原 Journal；此參數只標記原來源，不替代 exact result／stock／snapshot 身份。操作方式仍是開啟已保存候選的個股研究，再按「納入研究」等動作。未提供 source_id 或直接以旧 DecisionIdentity 呼叫時保存空值，不補查、不回填舊資料，也不借前次來源畫 marker。圖表仍須原列 custody hash、來源／帳別／日期／aware clock 全部符合才畫推薦確認標記。

排錯與重試：相同 request id 必須帶相同 source_id；來源改變時回報 command conflict，不新增修訂。切換報告、即使同候選但來源不同，都會清除原重試；同步 signal 或已完成舊 command 的晚到結果不能覆蓋新 context。取消讀取不產生 marker；寫入已完成則保留真實紀錄，不假稱取消回滾。舊 unknown 紀錄保持未知，研究動作仍不代表交易或正式模型資格。


<a id="8-每日決策-daily-decision-desk"></a>
## 8. 每日決策（Daily Decision Desk）

### 8.1 進入與刷新

決策工作台的「已保存快照日」與市場總覽的「本次評估日（台北）」用途不同：前者保留最後成功保存的 Decision Desk 日期，後者是本次查詢的台北日期與資料截止上限。行情資料日另列實際可驗的行情日期，不能把評估日當成已取得當日收盤資料。例如美西 10/6 晚間已是台北 10/7，行情仍可能截止 10/6；若 10/6 保存逾時，工作台仍可顯示 10/5 的已保存快照。

工作台會另列最近保存作業的狀態；「逾時」或「失敗」不會把舊快照改成今天，也不代表舊快照損壞。狀態缺件、格式無效或日期在本次評估日之後時保留「未知」。行情與指數日期僅表示各來源目前可讀的最新日期，不保證所有股票或交易日完整。

預設日期的市場總覽每次按「更新決策摘要」都重新取得台北評估日，跨台北午夜後會隨下一次更新切換日期；明確指定的歷史日期則保留指定日。更新市場總覽只重新建立畫面摘要，不會補存工作台快照。遇到工作台日期落後時，先查看最近保存狀態與資料日期，再由保存作業的診斷確認原因；不要為了統一日期把歷史快照日期改成今天。

Daily Decision Desk 採用 Midnight Analyst 深色介面：深色背景、section header 狀態 badge、緊湊摘要卡片與分行代碼清單。強勢、弱勢與低流動性代碼每類預設顯示前 8 檔，其餘以剩餘檔數摘要；完整資料仍由 service snapshot 保留，不因 UI 摘要而改變計算結果。

Market Breadth、Relative Strength / Liquidity 與 Smart Money 會在同一次 snapshot 內共用唯讀市場資料 frame，減少重複 SQLite 查詢；每次重新建立 snapshot 都會重新載入，且只接受 `日期 <= as_of_date`。這不會跨排程沿用 cache，也不改各 section 的 quality、warnings 或降級規則。

頁面最上方會先顯示 answer-first dashboard：

- `今日主結論`：以 `積極研究`、`正常研究`、`保守觀察`、`暫停新進場` 表示市場研究節奏。
- `研究模式註記`：提醒本頁是市場與籌碼輔助判讀，不是交易建議。
- `優先產業` / `避開產業 / 風險區`：由產業輪動摘要產生，幫助先決定研究方向。
- `優先研究股票` / `風險股票`：整合相對強弱、Watchlist、持倉警示與 Smart Money 語意摘要。
- 股票焦點按鈕可下鑽到「市場探索 > 主力流向」並定位該股票。

Watchlist、持倉或單一股票風險不會直接降低整體市場行動等級；它們只影響股票焦點、風險清單與提示文字。整體行動等級主要由 Market Regime、Market Breadth 與資料品質決定。

warnings 在 UI 會以繁體中文說明主要原因與影響範圍；原始 token 保留在底層 snapshot / log 供除錯追溯，不直接作為一般畫面文字。看到 warnings 時先判斷是資料覆蓋率、歷史不足或服務降級，不應只看工程代碼做決策。

1. 進入左側主導覽「市場探索」，選擇第一個子頁「市場總覽」。也可在「決策工作台 > 決策來源」按「開啟市場總覽」前往同一個唯一實例。
2. 進入頁面時會先顯示「尚未載入 / 載入中」，Snapshot 會在背景執行緒建立，避免主 App 啟動被每日決策查詢阻塞。
3. 點選「更新決策摘要」可在背景重建 Snapshot；載入期間按鈕會暫時停用，完成後自動更新畫面。
4. 若初始化或刷新失敗，畫面會保留可閱讀狀態並顯示 fallback 提示，不會中斷整體 App。

### 8.2 結果解讀

各區塊保留實際資料日期；較舊資料降級，未來或缺日期來源保持未知。有效空候選池顯示 0；全數分數未知保持缺件。前期分數不足的新候選帶 estimated 提示，不代表已驗證的即時突破。刷新期間更換決策日，舊請求結果與錯誤不會蓋掉新日期。進入股票研究報告時，畫面另列本次查詢日（`as_of`）；它不是行情資料日。資料日只採該股票、該來源實際可驗的 row date，來源不能證明時保留「未知」。歷史 alert 保留原事件日期與來源，只代表曾有該提示，不代表目前持倉或目前狀態。

主畫面以唯讀 provider 載入決策日當下已保存的推薦，保留 result ID、Profile、品質及資料指紋；缺 context 或檔案損毀時顯示缺資料，不自行重新評分。完整 loop snapshot 重載到 Workbench 時保留推薦與 source_lineage；舊 snapshot 沒有來源欄位仍以既有缺件語意顯示。候選 ledger 僅在應用服務明確注入時可用，缺行情時 blocked，不顯示安全等級，也不生成調倉或成交。

每日決策摘要會顯示：

- 主結論與行動等級
- 優先 / 風險產業與股票焦點
- `as_of_date`：本次評估的資料截止上限；實際行情資料日依各來源另列
- `quality`：整體品質（`OBSERVED` / `ESTIMATED` / `DEGRADED` / `MISSING`）
- `warnings`：所有 section 的缺口與降級原因彙總
- 各區塊 section：如 Market Regime、Market Breadth、Sector Rotation、Watchlist Trigger、Portfolio Alert
- 「資料可見性與擴充因子」：顯示月營收廣度、三大法人市場流向，以及各來源的觀測日、可得日、PIT 與 eligibility 狀態。此區塊只供研究可見性，不參與主結論、行動等級、產業／股票焦點、Score 或整體品質聚合。

月營收正向比例以整數 basis points 呈現為百分比；例如 `5636 bp` 顯示為 `56.36%`。三大法人尚未匯入時會顯示「尚未匯入（0 筆）」，不會把缺漏資料假裝成「外資 0」。可見性服務失敗時，只有此區塊降級為 `DEGRADED`／`MISSING` 並保留來源 warning；既有 Decision Desk action、focus 與 Score 不會因此被重算或改寫。

Market Breadth v1 會從 SQLite `daily_prices` 唯讀推導：

- 多方 / 空方 / 持平家數
- 廣度比率 BP
- 20 / 60 日新高新低 metadata
- 漲跌停近似統計與成交量擴散 metadata

若指定日期不是交易日或該日尚無資料，本頁會使用最近可用交易日並在 warnings 顯示 fallback 日期，不會把缺資料補成當日觀測值。

漲跌方向依來源的變動值與方向欄位共同判讀；只有方向明確且相符時才列入多方或空方。來源缺方向、方向未知或欄位彼此矛盾時會跳過多空計數並保留為未知，不以正負號猜補，也不把缺值當持平。查看 breadth 時也要同時確認資料日、來源警告與涵蓋範圍。

產業強弱 current-research v1 會從 SQLite `industry_indices`、精確 `TAIEX` 與 `daily_prices` 唯讀推導：

- leaf／aggregate 分層的產業列與 5／20 日報酬；層級內以相對 TAIEX basis points 排名。
- `market_return_*_bp`、`excess_*_bp`、index close、代表股與每個窗口 coverage。
- `source_id`、`source_version`、mapping source／version、mapping observed／available time、資料日、market scope 與 PIT eligibility。
- `unmapped_industry_categories`、`unmapped_index_names`、duplicate／ambiguous membership、缺價／停牌與 scope exclusions 等可追溯 diagnostics。

指定日期會先裁切到不晚於請求日的最後一個 TAIEX session；5／20 日端點都取同一份 market session 序列。找不到精確 TAIEX、窗口不足或產業缺 index 時，該列保持缺值並以 `MISSING`／`DEGRADED` 與 warnings 揭露，不以任意市場指數或 0 代替。current registry 的 mapping 只在當期研究適用，歷史 PIT 不可用時不進入回測、ML 或 Formal eligibility。

在市場總覽的產業卡按「研究代表股」後，選取要研究的產業代表股即可開啟既有個股研究 context；這是明確選股的唯讀導覽，不建立 watchlist、不改 Advice／Portfolio。若仍看見舊版 `Sector Rotation v1` 的代理文字，應先確認 nested industry strength 是否存在，再依來源／mapping identity 判讀，不把 proxy 當成完整產業分類證據。

Watchlist Trigger v1 會從 `WatchlistService` 與 SQLite `technical_indicators` 唯讀推導：

- 個股強度評分 `score_bp`（RSI * 100，值域 0~10000）
- 個股風險警示 `risk_alert`（偏離 RSI > 80 / < 20 或收盤價低於布林通道下軌 `Close < lowerband`）
- 新進候選、強度提升、強度下降等觸發統計

若指定日期不是交易日或該日無指標資料，本頁會採用最近可用交易日，並在 `warnings` 顯示 fallback 日期，且 quality 降級為 `DEGRADED`（在 warnings 中標註 `watchlist_trigger_as_of_fallback:<date>`）。

Portfolio Alert v1 會整合持倉條件監控與 `PortfolioChipService` 籌碼摘要。當持倉條件失效、警告，或個股籌碼風險為 bearish / extreme / risk 時，會列入持倉警示；若籌碼股數資料缺失、估算或部分事件不可用，會在 warnings 顯示 `portfolio_alerts_chip_*`，並將 quality 降級為 `ESTIMATED` 或 `DEGRADED`。`portfolio_alerts_chip_estimated:<stock_code>` 代表券商分點資料中存在 amount-only 觀測列：有買賣金額但缺買賣股數，因此系統用金額與收盤價換算股數，保留為估算品質揭露；要完全消除此 warning，需要上游 `broker_flows` 補齊實際股數，而不是把估算值標成 observed。Portfolio Alert 的來源歸因會顯示每檔警示持倉的來源標籤、condition 狀態、chip risk level 與原因 token。這用於解釋警示來源，不代表自動賣出或調倉。

Relative Strength / Liquidity Ranking v1 會從 SQLite `daily_prices` 唯讀推導 5 / 20 日相對強度與平均成交金額，顯示強勢代碼、弱勢代碼與低流動性代碼。
- **畫面呈現**：每日決策頁會把強勢、弱勢與低流動性代碼以單一 compact list 分行顯示，單類別只顯示前 8 檔並標示剩餘檔數，避免大量股票代碼撐寬主視窗；各 section 的品質狀態以 header badge 顯示。
- **流動性過濾**：當 20 日平均成交金額低於預設的 20,000,000 元時，該股將被列為低流動性代碼。
- **強弱勢判定**：股票的 20 日相對強度必須至少有 21 個有效交易觀測值（當日 + 前 20 日歷史）。若因歷史資料不足（如新上市股票或資料缺失）無法滿足 21 天，該股票將不參與強度排序，並以 `relative_strength_liquidity_skipped_symbols:<count>` 保留覆蓋率 warning；少量 skipped 不會自動拖累整個模組 quality。若使用 fallback 日期、整個模組無可用觀測歷史，或 skipped symbol 比例超過容忍門檻（預設 5%，以 basis points 記錄在 meta），quality 才會降級為 `DEGRADED`；整體無法排序時會在 warnings 中標註 `relative_strength_liquidity_insufficient_history`。

Why Not / 風險提示 v1 會從既有已計算的區塊 DTO 中，推導出可行動的風險提示（prompts），而不在 UI 或此服務內重新計算複雜邏輯：
- **市場風險提示（market_context）**：大盤為 risk-off 或 bear 等狀態時提示「市場風險偏高」，建議降低對個股強勢的解讀信心。
- **流動性提示（liquidity）**：個股被 Relative Strength / Liquidity 判定為低流動性時提示「低流動性」，提醒檢查部位大小。
- **相對弱勢提示（weakness）**：個股在 20 日相對弱勢清單時提示「相對弱勢」，提醒確認反轉條件再行考慮。
- **觀察清單風險觸發提示（watchlist_risk）**：個股觸發 Watchlist 的 risk_alert 時提示「觀察清單風險觸發」。
- **持倉警示提示（portfolio_alert）**：個股位於 Portfolio Alert 警示名單時提示「持倉警示」。
- **基本面診斷提示（fundamental_diagnostic）**：當 Research metadata 或 application service 提供 abnormal fundamental diagnostics 時，會以 `source=fundamental` 顯示營收與獲利背離、一次性收益風險或資料品質缺口。這只是研究風險提示，不代表財報已被重算、推薦分數已被扣分或系統產生買賣建議。
- **品質警告規則**：當來源區塊品質為非 OBSERVED 時，會產生 `risk_prompt_source_quality:...` 警告，並將 Why Not 區塊之 quality 降級為 `DEGRADED`。

#### quality 與 warnings 規則

- `OBSERVED`：當前節點資料完整且已驗證可用。
- `ESTIMATED`：有可補值但非直接觀測值。
- `DEGRADED`：有資料但需降級顯示，需注意風險。
- `MISSING`：節點缺資料，僅保留警示，不能視為可交易依據。

#### 限制與排錯

- 本頁是每日決策摘要，不是自動交易或下單介面。
- Market Breadth v1、Sector Rotation v1、Relative Strength / Liquidity Ranking v1、Watchlist Trigger v1 與 Portfolio Alert v1 已接線，但仍可能因 SQLite 缺資料、資料日期 fallback、歷史不足或籌碼資料缺失而降級顯示 `DEGRADED` 或 `ESTIMATED`。
- Portfolio Alert 僅為持倉摘要警示，未直接改變持倉。
- 基本面診斷提示僅使用已治理 metadata；不會直接讀 raw financial CSV、不會改寫財報、不會輸出目標價、合理價、上漲空間或交易建議。

#### 月營收 availability mapping 維護

月營收 raw CSV 不能自行推定公告日或可得日。若要建立候選 mapping，可先使用 TWSE/TPEX historical dry-run builder：

```powershell
.\.venv\Scripts\python.exe scripts\build_monthly_revenue_availability_history.py --start-period 2020-01 --end-period 2026-05 --markets twse,tpex
.\.venv\Scripts\python.exe scripts\build_monthly_revenue_availability_history.py --start-period 2020-01 --end-period 2026-05 --markets twse,tpex --stock-code 2330 --output <candidate-csv>
.\.venv\Scripts\python.exe scripts\build_monthly_revenue_availability_history.py --start-period 2024-04 --end-period 2024-04 --markets twse --mops-html-dir <mops-html-dir> --output <candidate-csv>
.\.venv\Scripts\python.exe scripts\build_monthly_revenue_availability_history.py --start-period 2024-04 --end-period 2024-04 --markets twse --stock-code 2330 --mops-static
.\.venv\Scripts\python.exe scripts\build_monthly_revenue_availability_history.py --start-period 2020-01 --end-period 2024-04 --markets twse,tpex --pit-csv <authorized-pit-export.csv> --pit-source-version <export-version> --output <candidate-csv>
```

未提供 `--output` 時只輸出 summary，不寫檔；指定 `--output` 時只寫候選 CSV，不會改寫正式 `DATA_ROOT/meta_data/monthly_revenue_availability.csv`。候選列使用官方 `出表日期` 作 `announced_date`，並以公告日隔天作保守 `available_date`，避免同日盤中可得性假設。`--mops-html-dir` 僅讀人工保存的官方 MOPS HTML，檔名規則為 `twse_YYYY-MM.html` / `tpex_YYYY-MM.html`；HTML 必須含頁面層級 `出表日期` 與 `公司代號` 表格，否則只輸出 diagnostics，不用 raw CSV 日期補值。`--mops-static` 會走新版 MOPS `/mops/api/redirectToOld` 取得 `mopsov.twse.com.tw/nas/t21/...` historical static report，只作來源驗證；目前該 report 的 `出表日期` 是查詢當日重新出表日，不是歷史原始公告日，因此會被 `as_of_date + 45 days` 合理揭露窗口擋下。

自 2026-08-06 起，任何要進入正式 availability mapping 的新列都必須符合 `formal-availability.v2`：`evidence_class=official_announcement`、明確 `announced_date`、SHA-256 `source_hash`，以及連續的 `revision`／`parent_revision`。目前正式 builder 對有官方公告證據的列會自動輸出這些欄位；`first_observed`、`local_first_seen`、本機 observation 與 `manual.available_date_mapping` 只可作 shadow／研究候選，validator 會 fail-closed。為維持既有日常資料可用，只有 `twse.monthly_revenue_announcement / twse-openapi-t187ap05-l-2026-07-14` 與 `tpex.monthly_revenue_announcement / tpex-openapi-mopsfin-t187ap05-o-2026-07-14` 這兩組已 materialize 的 2026-06 mapping 可走精確 legacy compatibility；它不是未來新資料的範本。

若取得授權 point-in-time 月營收公告日匯出檔，可使用 `--pit-csv`。匯出檔必須至少有股票代號、資料年月與公告日欄位；支援 `stock_code` / `公司代號`、`period` / `資料年月`、`announced_date` / `公告日` / `出表日期` 等欄名。`--pit-source-version` 必須非空，並會原樣寫入候選 mapping 的 `source_version`。PIT 匯入來源目前治理為 `tej.monthly_revenue_announcement_pit`；此路徑仍只產生 candidate CSV，不會寫正式 mapping，也不會回填 SQLite。

舊版 TWSE OpenAPI 候選產生器仍可用於單一最新月來源測試：

```powershell
.\.venv\Scripts\python.exe scripts\build_monthly_revenue_availability.py --fetch-date 2026-06-16
.\.venv\Scripts\python.exe scripts\build_monthly_revenue_availability.py --source-json <twse-json> --output <candidate-csv> --fetch-date 2026-06-16
```

寫入正式 `DATA_ROOT/meta_data/monthly_revenue_availability.csv` 前，必須先以 `scripts\validate_monthly_revenue_availability.py --path <candidate-csv>` 驗證 v2 provenance、PIT 日期與 revision chain，並取得人工確認；此工具不會自動改寫正式 mapping、raw CSV 或 SQLite。

若要把已驗證候選安全地併入既有 mapping，可先預覽 merge plan：

```powershell
.\.venv\Scripts\python.exe scripts\apply_monthly_revenue_availability_candidate.py --candidate <candidate-csv> --target D:\Min\Python\Project\FA_Data\meta_data\monthly_revenue_availability.csv
```

此 plan 會保留既有列、以 `(stock_code, period)` 做 natural-key 去重；相同內容視為 idempotent，內容不同則以 conflict 停止，不會猜測覆蓋。只有人工確認後才可套用：

```powershell
.\.venv\Scripts\python.exe scripts\apply_monthly_revenue_availability_candidate.py --candidate <candidate-csv> --target D:\Min\Python\Project\FA_Data\meta_data\monthly_revenue_availability.csv --apply --confirm apply-monthly-revenue-availability
```

套用前會將既有 mapping 備份到 `--backup-dir`（預設為 target 同層 `backup`），並在 target 同一目錄先完成 UTF-8 CSV 暫存檔後 atomic replace；candidate、raw CSV 與 SQLite 不會由此 CLI 改寫。套用 mapping 後，仍須另外對同一 candidate 與 MOPS snapshot 執行 `backfill_monthly_revenue_fundamentals.py --dry-run`，確認 0 diagnostics，再以 `--confirm apply-monthly-revenue-backfill` 明確回填 SQLite。兩個 apply 必須分開確認，避免 availability 日期與數值資料只更新一半時被誤認為完成。

截至 2026-06-16，TWSE 上市 endpoint `/opendata/t187ap05_L` 與 TPEX 上櫃 endpoint `/openapi/v1/mopsfin_t187ap05_O` 均可提供最新月 `出表日期`；樣本為 `2330` / `9935` 的 `2026-05` 公告日 `2026-06-15`，以及 `3207` 的 `2026-05` 公告日 `2026-06-16`。這些 OpenAPI 目前未提供歷史 period query；MOPS historical static report 可透過新版 API 取得，且可看到 `113/04` 的 `2330`、`9935`、`3207` rows，但其 `出表日期` 是查詢當日，不能視為歷史公告日。正式 raw 月營收目前只到 `2024-04`，與最新月來源無交集，因此 `2020-01..2026-05` dry-run 產生 0 candidate rows。歷史公告日仍需可追溯的原始公告日批次來源或受控人工 mapping。

#### 月營收 normalized backfill

正式 DB 已有 `fundamental_monthly_revenues` schema，但回填必須先通過 availability mapping。可先執行 dry-run：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_monthly_revenue_fundamentals.py --dry-run
```

dry-run 只輸出 plan，不寫入 SQLite。若正式 `DATA_ROOT/meta_data/monthly_revenue_availability.csv` 不存在，結果會是 `ready_for_apply=false` 並輸出 `fundamental_availability.mapping_file_missing`，不會讀 raw 月營收 rows，也不會產生 normalized records。

MOPS snapshot 可以作月營收**數值**主來源，但不能自行證明歷史公告／可得時間。只有每一筆數值都能與 v2 或上述受限 legacy 正式 availability mapping 完整對應時，才可用 `--mops-snapshot-file` 做 dry-run；不需先轉成 `financial_data/*_monthly_revenue.csv`：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_monthly_revenue_fundamentals.py --dry-run --mops-snapshot-file <mops-snapshot.csv> --availability-file <formal-availability-v2.csv> --source-version <snapshot-version>
```

此路徑會把 normalized record 的 `source` 保留為 `mops.monthly_revenue_static_snapshot`，但其正式可得性一律以獨立 mapping 為準。2026-06-16 的 1,848 筆 2026-05 MOPS first-seen 回填是歷史資料：原始 DB row 保留、不可刪除，但因沒有正式 mapping，現在已被 Recommendation／Fundamental provider 的 live gate 隔離，不能作為正式 PIT 特徵。當前可正式使用的是 1,832 筆 2026-06 值，它們與 TWSE／TPEX 官方公告 mapping 的日期完整對應。

正式回填必須在 mapping 通過驗證後，由人工確認再執行：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_monthly_revenue_fundamentals.py --apply --confirm apply-monthly-revenue-backfill
```

正式 apply 會先備份 DB；缺少 `--confirm apply-monthly-revenue-backfill` 時會拒絕執行。回填工具只寫入 `fundamental_monthly_revenues`，不會修改 raw CSV、availability mapping 或既有核心表。apply 後必須以正式 provider／推薦 filter 再確認 row 與 mapping 的 `stock_code`、`period`、`as_of_date`、`announced_date`、`available_date` 完全一致；只標為 `quality=observed` 不足以取得正式讀取資格。若指定 `--db-file` 但未指定 `--backup-dir`，備份會放在該 DB 同層的 `backup` 目錄；未指定 `--db-file` 時才沿用正式 `DATA_ROOT/meta_data/backup`，明確的 `--backup-dir` 優先。

#### 更新頁月營收功能

主 UI 的「資料更新」頁新增「月營收」分頁。此分頁提供三個欄位：

- `MOPS 月營收快照檔`：從 MOPS snapshot CSV 讀取各公司每月營收值。
- `正式可得日對照檔`：指定 `monthly_revenue_availability.csv`，用來決定每筆月營收從哪一天起可被因子層讀取。
- `本次寫入版本名稱`：寫入資料表的版本名稱，用於日後追溯與比對。

此分頁提供三個操作：

- `抓取最新候選快照`：依頁面顯示的預期期別，向 MOPS 官方 static endpoint 取得 TWSE／TPEx 數值候選。每次在 `OUTPUT_ROOT/monthly_revenue_mops_snapshots/captures/run_<抓取日>_<UUID>/` 建立獨立目錄，將受控 CSV 與同層 `raw_html/` 保存在一起；同日重抓亦保留前次原件。不寫正式 SQLite、不修改正式 availability mapping；完成後會自動把本次輸出 CSV 帶入快照欄位。

- `先檢查，不寫入`：只檢查可回填筆數與診斷結果，不寫入正式資料庫。
- `確認後寫入月營收`：先跳出確認視窗，再建立 DB 備份並寫入 `fundamental_monthly_revenues`。此按鈕不抓取新 MOPS HTML、不修改 raw CSV，也不更新 availability mapping。

操作順序是「抓取候選 snapshot → 以官方公告日期 builder／validator 產生並檢查 availability candidate → 先合併正式 mapping → 回到此頁執行 dry-run → 人工確認後 apply」。更新頁目前只負責候選 snapshot 與 SQLite backfill；不會用 snapshot 查詢日推定公告日，也不會自動把候選 mapping 或數值寫入正式資料。UI 不會把「候選可用」誤顯示成「已套用」。

2026-10-03 的 2026-08 月營收診斷案例取得 1,855 筆 raw 候選列，但正式可得日 mapping 未能對應任何列：`normalized_record_count=0`、`diagnostic_count=1`、`ready_for_apply=false`，診斷碼為 `fundamental_availability.snapshot_mapping_incomplete`。這表示候選抓取已完成，不表示資料已治理可用。失敗對話框、更新摘要與 log 會保留診斷碼、原始訊息與下一步；應先補齊並核准相同資料期別的正式 availability mapping，再重新執行 dry-run。抓取日／本機首次觀測日不能代替公告日或 `available_date`；未知診斷仍維持失敗，不可按正式回填。

同日 10:49 UTC 的 c625 原生觀察已在失敗對話框與更新 log 顯示上述診斷碼、1,855 筆 unmatched 候選、中文原因與下一步；`normalized=0`、`diagnostics=1`，該次操作停在檢查，沒有執行 Apply。觀察收據為 `output/qa/integration_20261002/phase3_native/observation_20261003T104915223Z_vc625_monthly_diagnostic_modal_observation.json`（SHA-256 `70dc23d6c3af985062f086163f1b6a057ac3634033e3bb368ba5a4c4eff8f453`）。

root 最終 c625 原生接受收據 `output/qa/integration_20261002/phase3_native/root_native_final_acceptance_20261003T105541987127Z.json`（SHA-256 `483170b2c330b0121ce51435ff7a5966b073e2082c846289f56d33cade0597b6`）確認月營收失敗摘要顯示診斷原因與重試控制；該次沒有按 Apply，也沒有建立正式 mapping。重試控制可用不等於可得日已核准；重試後仍須重新核對 mapping diagnostics 與 `ready_for_apply`，不可略過後續治理檢查。

若要補抓最新月份，先以 MOPS snapshot CLI 取得數值，再用 TWSE／TPEx historical availability builder 取得官方 `出表日期` 候選；兩者交集才可進 backfill dry-run。兩條來源缺一時，更新頁只應顯示候選／缺口，不可用 snapshot 查詢日或本機檔案日期推定公告日。

#### 月營收因子檢視

若要確認正式 SQLite 月營收是否已進入基本面 factor layer，可使用唯讀檢視 CLI：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_fundamental_factors.py --all-monthly-revenue-stocks --decision-date 2026-06-30 --diagnostic-limit 8 --stock-summary-limit 12
```

此工具只讀取 `fundamental_monthly_revenues`、`fundamental_statement_items` 與 `fundamental_valuation_metrics`，透過 `FundamentalFactorService` 產生當下可見的 factor records / diagnostics，不寫 SQLite、不修改 CSV，也不接 `ScoringEngine`。2026-06-16 單月營收初版檢查結果為：股票數 1,848、factor records 4,464、diagnostics 3,696；其中月營收已產生 `fundamental.revenue_3m_trend` 1,848 筆與 `fundamental.revenue_new_high` 1,848 筆。2026-06-17 retroactive baseline 補齊後，Revenue Factor Pack 可產生 YoY 1,843 筆、MoM 1,842 筆、3M trend 1,848 筆與 new high 1,848 筆，剩餘 diagnostics 11 筆。這代表 Month 5 已能把 SQLite 月營收送到 Revenue Factor Pack；但 historical baseline 多數 quality 為 `degraded`，不可解讀為官方歷史 point-in-time 公告日，也不可直接接入 `ScoringEngine`。

#### 月營收歷史 baseline 候選

MOPS snapshot 可以用來補「從導入日之後才可使用」的歷史 baseline。此路徑不是官方歷史公告日 mapping；產出的 source 固定為 `manual.retroactive_baseline_mapping`，`announced_date` 留空，`available_date` 設為人工指定的導入可用日，品質會是 `degraded`。因此它可讓 2026-06-17 之後的決策日計算 YoY / MoM baseline，但不得用於 2026-06-17 以前的歷史回測。

建議先產生候選檔，不覆蓋正式 mapping：

```powershell
.\.venv\Scripts\python.exe scripts\build_monthly_revenue_retroactive_baseline_mapping.py --snapshot-file D:\Min\Python\Project\FA_Data\output\monthly_revenue_mops_snapshots\mops_monthly_revenue_snapshot_2014-04_2026-05_2026-06-16.csv --start-period 2014-04 --end-period 2026-04 --available-date 2026-06-17 --source-version mops-retroactive-baseline-2014-04_2026-04-2026-06-17 --output D:\Min\Python\Project\FA_Data\output\monthly_revenue_availability_candidates\mops_retroactive_baseline_monthly_revenue_availability_2014-04_2026-04_2026-06-17.csv
.\.venv\Scripts\python.exe scripts\validate_monthly_revenue_availability.py --path D:\Min\Python\Project\FA_Data\output\monthly_revenue_availability_candidates\mops_retroactive_baseline_monthly_revenue_availability_2014-04_2026-04_2026-06-17.csv
.\.venv\Scripts\python.exe scripts\backfill_monthly_revenue_fundamentals.py --dry-run --mops-snapshot-file D:\Min\Python\Project\FA_Data\output\monthly_revenue_mops_snapshots\mops_monthly_revenue_snapshot_2014-04_2026-05_2026-06-16.csv --availability-file D:\Min\Python\Project\FA_Data\output\monthly_revenue_availability_candidates\mops_retroactive_baseline_monthly_revenue_availability_2014-04_2026-04_2026-06-17.csv --source-version mops-static-snapshot-monthly-revenue-2026-06-16
```

2026-06-16 dry-run 結果：candidate 242,651 筆、validator accepted 242,651 筆、backfill normalized 242,651 筆、diagnostics 0。依人工確認正式 apply 後，`fundamental_monthly_revenues` 共有 244,499 筆，期間 `2014-04..2026-05`，股票數 1,848、period 數 146、0 duplicate；品質分布為 242,651 筆 `degraded` historical baseline 與 1,848 筆 `observed` 2026-05 records，DB 備份為 `D:/Min/Python/Project/FA_Data/meta_data/backup/twstock_mops_monthly_revenue_backfill_20260616_224147.db`。factor inspection 顯示 `fundamental.revenue_yoy` 1,843 筆、`fundamental.revenue_mom` 1,842 筆、`fundamental.revenue_3m_trend` 1,848 筆、`fundamental.revenue_new_high` 1,848 筆，剩餘 diagnostics 11 筆主要為 baseline missing / zero。

#### 季度財報 available date gate

季度財報 raw CSV 不能直接進入因子層；必須先有 `fundamental_statement_availability.csv` 作 `available_date` gate。正式預設路徑為 `DATA_ROOT/meta_data/fundamental_statement_availability.csv`，欄位為 `stock_code`、`statement_type`、`period`、`as_of_date`、`announced_date`、`available_date`、`source`、`source_version`。

MOPS 公告快易查現在可作季報官方發布時間的 research-only 主線。它只讀查詢 `F26` 資產負債表、`F27` 綜合損益表、`F28` 現金流量表與 `F29` 權益變動表，保存「公告日期時間」至秒及 `+08:00` 時區；不使用 `M31`，因為 M31 同時包含「董事會預計召開日期」與「董事會通過財報」，不能一律視為財報已發布。執行範例：

MOPS 公告時間 artifact 只證明 availability，不能自行衍生 ROE、毛利率、營益率、負債比或 EPS。任何聲稱 numeric PIT 的 research candidate 必須以獨立、唯讀保存的原始數值財報 artifact 為來源，並同時保存 raw-numeric artifact、MOPS availability artifact、canonical dataset manifest/dataset 的 SHA-256 lineage；每列要有 raw numeric row 與 availability event 的 SHA-256、帶時區 publication timestamp、次一曆日的 `available_date`，且數值只用整數 minor units／basis points。validator 只會標為 `research_candidate`，不會賦予 official、source acceptance、formal OOS 或 production eligibility。內建常數、sample/default ratio、固定更正履歷、或將寫入前的 digest 塞回同一份 JSON 的輸出，一律 fail-closed。

若需要建立可核驗的 bounded numeric PIT candidate，可使用 `scripts/build_mops_numeric_pit_candidate.py`。它從 MOPS `t163sb06` 保存季度數值比率 raw HTML，再從 `t57sb01` 保存同一公司／季度的 IFRSs 合併財報 listing，以 listing 上的原始上傳時間和更(補)正欄建立 publication/revision lineage；所有檔案、各層 SHA-256 與 candidate 都會寫入唯一 TEMP run directory。範例：

```powershell
.\.venv\Scripts\python.exe scripts\build_mops_numeric_pit_candidate.py `
  --stock-code 2330 --roc-year 114 --season 1 --market sii `
  --output-root C:\Temp\technical_analysis_development_output `
  --run-id dev71-mops-numeric-pit-2330-2025q1-r1 `
  --canonical-manifest C:\Temp\technical_analysis_development_output\generations\terra-v0-canonical-2025-dev-20260714\manifest.json `
  --canonical-dataset C:\Temp\technical_analysis_development_output\generations\terra-v0-canonical-2025-dev-20260714\dataset.json
```

`--run-id` 不可重用；工具會在同一目錄保存 raw HTML、numeric source、availability source、candidate 與 run manifest，並在發布 candidate 前重新執行 validator。MOPS listing 若顯示更(補)正，不會猜測 revision，而是停止要求另行建立具比較基準的 correction lineage。此工具可計算 canonical dataset 的 PIT-eligible coverage；coverage 有限時只代表 source artifact 已取得，不能當作 feature 已 materialize、ML 可訓練、source accepted 或 Formal evidence。

#### MOPS t164 三表 universe plan、bounded batch 與隔離 consumer

要逐批取得 2026-Q2 合併資產負債表、綜合損益表與現金流量表，先用已保存的官方 `companies.csv` 建立 research-only universe plan。首批代表性驗證才使用 `representative_initial`，必須明確列出最多 8 家、兩個市場、至少 4 個產業並包含 2881；後續一律使用 `continuation`，不指定 `--select` 時依 `(registry_market, stock_code)` 穩定順序自動選取下一批，尾批可以只有一個市場。`--verified-artifact` 只接受可重新核對 child／batch manifest、candidate、raw 與 SHA-256 的完成證據；`--caller-excluded` 只是暫不取數，不會被算成完成。

```powershell
# 首批只在明確需要代表性覆蓋時使用；以下為 bounded request 範例
.\.venv\Scripts\python.exe scripts\plan_mops_statement_universe.py `
  --registry D:\Min\Python\Project\FA_Data\meta_data\companies.csv `
  --period 2026-Q2 --profile representative_initial `
  --select 2881:twse --select 1101:twse --select 1301:twse --select 2603:twse `
  --select 2303:twse --select 3105:tpex --select 3293:tpex --select 6547:tpex `
  --output C:\Projects\PythonProjects\technical_analysis\output\v4_data_recovery_2026-09-07\quarterly\universe-initial.json

# 後續 plan 綁定已完成 manifest；未指定 --select 時自動選下一批，最多 8 家
.\.venv\Scripts\python.exe scripts\plan_mops_statement_universe.py `
  --registry D:\Min\Python\Project\FA_Data\meta_data\companies.csv `
  --period 2026-Q2 --profile continuation `
  --verified-artifact C:\path\to\prior-batch-manifest.json `
  --max-selected-companies 8 `
  --output C:\Projects\PythonProjects\technical_analysis\output\v4_data_recovery_2026-09-07\quarterly\universe-continuation.json
```

將 plan 交給 bounded batch driver。每家公司先保存 checkpoint，再獨立執行既有 MOPS fetcher；單一解析／科目 gate 失敗會繼續處理其他公司，但同一官方來源的 transport 失敗達 `--max-source-transport-failures` 後會暫停後續列，避免重複撞擊不可達來源。`--max-attempts-per-child 2` 與來源失敗上限都會寫入批次 identity；`--resume` 只驗證成功 child 並重試仍未完成的列，不重抓已成功 raw，且會開啟新的來源 transport 嘗試窗口。失敗原因、來源、attempt 時間、circuit event 與 remaining budget 會留在 batch manifest。成功 child 仍是 `research_only=true`，不代表全 universe 已完成。

```powershell
.\.venv\Scripts\python.exe scripts\build_mops_statement_batch.py `
  --universe-plan C:\path\to\universe-continuation.json `
  --output-root C:\Projects\PythonProjects\technical_analysis\output\v4_data_recovery_2026-09-07\quarterly `
  --batch-manifest C:\Projects\PythonProjects\technical_analysis\output\v4_data_recovery_2026-09-07\quarterly\batch-manifest.json `
  --canonical-manifest D:\Min\Python\Project\FA_Data\meta_data\stock_data_whole.csv `
  --canonical-dataset D:\Min\Python\Project\FA_Data\meta_data\all_stocks_data.csv `
  --run-id-prefix v4-quarterly-universe-2026q2-r1 `
  --max-companies 8 --max-attempts-per-child 2 `
  --max-source-transport-failures 1 --timeout-seconds 30

# 網路或解析失敗後，沿用同一 operation identity 續跑
.\.venv\Scripts\python.exe scripts\build_mops_statement_batch.py `
  --universe-plan C:\path\to\universe-continuation.json `
  --output-root C:\Projects\PythonProjects\technical_analysis\output\v4_data_recovery_2026-09-07\quarterly `
  --batch-manifest C:\Projects\PythonProjects\technical_analysis\output\v4_data_recovery_2026-09-07\quarterly\batch-manifest.json `
  --canonical-manifest D:\Min\Python\Project\FA_Data\meta_data\stock_data_whole.csv `
  --canonical-dataset D:\Min\Python\Project\FA_Data\meta_data\all_stocks_data.csv `
  --run-id-prefix v4-quarterly-universe-2026q2-r1 `
  --max-companies 8 --max-attempts-per-child 2 `
  --max-source-transport-failures 1 --timeout-seconds 30 --resume
```

MOPS t164 response 先驗證官方表名與實際期別，再以同公司／同季度 XBRL hidden metadata 取得官方 row code；一般仟元金額以整數 TWD／`value_scale=1000` 保存，EPS 以 cents/share／`value_scale=100` 保存。損益表保留 `quarter_single`，現金流量表保留 `year_to_date`，資產負債表保留 `period_end_snapshot`。若金控公司第一步回傳母子公司選擇表，只在公司代號欄精確等於請求代號且 onclick `co_id` 唯一時 follow-up `step=2`；不可因全文含有代號就接受 28810001 或其他子公司。已核對的同名 continuing basic／diluted EPS 才可依官方出現序號局部消歧；其他同名或金額／縮排不一致會 fail-closed。

數值完成時間 `capture_completed_at` 與公告事件時間分開保存；date-only consumer 以完成時間轉換後的下一個台北曆日作 `available_date`，不可把 listing 首次公告日回填成目前數值的 PIT 可得日。若 listing 的原始主站暫時 DNS 失敗，保留失敗原因；其他 host 的 404 只算該 host probe，不可當成官方公告不存在。空白科目保留 excluded 分母，不能補 0 來湊完整率。

若需要診斷 Python transport 是否為環境限制，可對既有官方 t57 URL 做一次瀏覽器唯讀查詢；金控公司可能先返回精確母公司／子公司 selector，再由官方頁面已呈現的母公司查詢控制取得 publication listing。保存 selector 與 publication DOM、觀察時間、公司／期別／檔名／上傳日期及 hash 時，必須標示 `capture_basis=Chrome rendered DOM observation`、`raw_http_bytes_saved=false`；瀏覽器 DOM 可作來源與 gate 診斷，不能冒充 HTTP raw 或把上傳日期回填為 numeric `available_at`。若三表 numeric raw 尚不完整，沿 research staging 保留並等待缺少的 listing/raw 證據，再交既有 candidate adapter。

完成候選後，只能在 repo output／TEMP 以隔離資料庫驗證 consumer：

```powershell
.\.venv\Scripts\python.exe scripts\materialize_mops_statement_candidates.py `
  --candidate C:\path\to\statement-pit-candidate.json `
  --db-path C:\Projects\PythonProjects\technical_analysis\output\v4_data_recovery_2026-09-07\quarterly\isolated-statement.db `
  --decision-date 2026-09-07 --decision-date 2026-09-08 `
  --evidence-output C:\Projects\PythonProjects\technical_analysis\output\v4_data_recovery_2026-09-07\quarterly\isolated-statement-evidence.json
```

materializer 會拒絕正式 `DATA_ROOT`、formal SQLite、symlink／junction、未標記既有 DB，以及 candidate／DB／evidence path 重疊；第一次與相同輸入的重跑應分別核對 inserted 與 idempotent existing，並檢查 9/7 不可見、9/8 可見、EPS Decimal、unit、period basis、official code 與 sidecar lineage。此入口不寫正式 `fundamental_statement_items`、availability mapping 或 D 槽 raw，也不授予 Formal credit。

#### MOPS numeric PIT aggregate、bounded resume 與 materialization gate

多份 candidate 只能在 TEMP／development root 內以 `scripts/aggregate_mops_numeric_pit_candidates.py` 聚合；aggregate validator 會重新核對四層 source identity、canonical/candidate/manifest SHA-256、candidate identity 唯一性、`0 <= eligible <= matching <= denominator` 與固定 `8,000 bp` coverage policy。`--minimum-coverage-bp` 不得用來降低門檻，輸出採 staging 後 atomic rename，不能寫入正式 `DATA_ROOT`、SQLite 或 Formal DB。

`scripts/acquire_mops_numeric_pit_batch.py` 是前景 bounded 工具，`--max-items` 必填；既有 `(stock_code, period)` 只有在 batch manifest 明確提供且完全相符的 `candidate_sha256` 時才可 skip。缺 hash、hash 衝突、既有 bundle 損壞或 output path 不在 TEMP root 時，會在 fetch 前 fail-closed；不會自動建立 revision，也不啟用 scheduler、background job 或 retry loop。

`check_mops_materialization_readiness` 與 `materialize_development_feature_overlay` 只接受有效 aggregate、具名 Source Owner／Reviewer dossier，以及 append-only decision registry 的 `accepted`／`limited` applying revision；revision 的 source、evidence IDs、decision timestamp、rollback reference、allowed use case 與 dossier 必須逐項相符。沒有 registry revision、coverage 不足、license 未核准或 lineage 不一致時不得 materialize。即使 gate 通過，輸出仍固定 `research_only=true`、`formal_oos_allowed=false`、`production_blend_alpha_bp=0`、`downstream_eligibility=none`，不得進入 scoring、Recommendation、Portfolio、Exit、training 或正式資料庫。

```powershell
.\.venv\Scripts\python.exe scripts\fetch_mops_statement_availability.py `
  --start-date 2026-07-27 `
  --end-date 2026-07-28 `
  --query-window-days 7 `
  --query-retries 2 `
  --output-root C:\Temp\technical_analysis_development_output\mops-statement-availability
```

`--output-root` 必須位於正式 `DATA_ROOT` 與 repo 之外；整體日期範圍最多 31 天，`--query-window-days` 可將每個 market/item 拆成 1–31 天的連續窗口。MOPS 單一 query 回傳達 1000 筆時會拒絕該窗口；應縮小此參數後重跑，artifact manifest 會保留每個實際 query window 與 response hash，避免把分段查詢誤看成同一個未分窗請求。`--query-retries` 最多允許 3 次額外重試，只重試被標為 error 的 query；成功後 manifest 會保留 `attempt_count` 與前次 `retry_error_codes`，最終失敗仍維持 `degraded`，不會把錯誤轉成官方無資料。輸出包含完整 JSON artifact 與 `fundamental-statement-availability.csv` 候選 mapping；JSON 保留官方 `announcement_at`，CSV 因既有 consumer 只有 date grain，固定以公告次一曆日作 `available_date`，避免同日盤中 look-ahead。具官方 timestamp 的延後申報採實際公告日，不再套用 120 天推定窗口。此 CLI 不寫正式 availability mapping／SQLite、不執行每日更新或排程、不提供 Formal credit；要接到正式資料仍須另一個明確 apply 決議與備份流程。

CLI 的 `--help` 與 JSON summary 會在可重設的 Windows stdout/stderr 上先採 UTF-8；若由 pytest 或其他 host 管理的 stream 不允許重設，會保留原 stream 繼續執行，不因繁體中文說明而中止。舊主控台若仍顯示亂碼，可在執行前設定 `$env:PYTHONIOENCODING='utf-8'`。

查詢品質摘要會把三種結果分開保存：`successful_query_count` 是有正常回應的查詢、`official_no_data_query_count` 是官方以 `status=fail` 回覆且沒有資料列、`failed_query_count` 才是 timeout／網路／解析錯誤。官方無資料不會被誤報成 outage，但仍會留在 `query_manifest`，供 owner 判斷市場範圍是否完整；若有真正錯誤，整體狀態為 `degraded`，不得以部分列數宣稱完整 coverage。輸入若把 `status=fail` 與資料列混用，builder 會 fail-closed。

歷史 EZSearch 回應可能出現欄位漂移（例如舊列缺 `CTIME`）。builder 會逐列將無法解析的 row 放入 bounded `invalid_event_samples`，以 `invalid_event_error_counts` 保存完整錯誤計數，並保留同一 query 回應內的有效列；只要 `invalid_event_count>0`，artifact 與 CLI 狀態就會是 `degraded`、return code=`3`，不可把部分成功當成完整 coverage。這種 quarantine 只保留可稽核摘要，不會把 malformed row 轉成 availability evidence。

若目前只要建立「導入日後可用」的歷史 baseline candidate，可先產生候選檔：

```powershell
.\.venv\Scripts\python.exe scripts\build_statement_retroactive_baseline_mapping.py --raw-dir D:\Min\Python\Project\FA_Data\financial_data --available-date 2026-06-17 --source-version statement-retroactive-baseline-2026-06-17 --output D:\Min\Python\Project\FA_Data\output\statement_availability_candidates\statement_retroactive_baseline_availability_2026-06-17.csv
.\.venv\Scripts\python.exe scripts\validate_statement_availability.py --path D:\Min\Python\Project\FA_Data\output\statement_availability_candidates\statement_retroactive_baseline_availability_2026-06-17.csv
.\.venv\Scripts\python.exe scripts\backfill_fundamental_statement_items.py --dry-run --raw-dir D:\Min\Python\Project\FA_Data\financial_data --availability-file D:\Min\Python\Project\FA_Data\output\statement_availability_candidates\statement_retroactive_baseline_availability_2026-06-17.csv --source-version financial-data-statements-2026-06-17
```

2026-06-16 dry-run 結果：statement availability candidate 170,425 筆、validator accepted 170,425 筆、diagnostics 0；statement item backfill normalized 1,645,555 筆、diagnostics 0。依人工確認正式 apply 後，`fundamental_statement_items` 期間為 `2014-Q2..2024-Q1`、股票數 1,567、period 數 40、0 duplicate，quality 全為 `degraded`，DB 備份為 `D:/Min/Python/Project/FA_Data/meta_data/backup/twstock_statement_items_backfill_20260617_004912.db`。此資料已可作導入日後 EPS、毛利率、營益率、ROE、業外損益 factor 的 baseline foundation；factor layer 只輸出 records / diagnostics，不接 `ScoringEngine`。

`backfill_fundamental_statement_items.py --dry-run` 現在會將診斷輸出限制為前 20 筆，同時保留 `diagnostics`、`diagnostic_counts` 與 `missing_availability_count` 的完整數字；任何一筆缺 `available_date` 都會讓 `ready_for_apply=false`。這避免大量歷史 raw row 把 console 淹沒，也不會因截短顯示而誤放行 apply。只有 plan 的 `diagnostic_count=0`、`missing_availability_count=0` 且有 normalized records 時，才可進入既有明確 confirmation、備份與 apply 流程。dry-run 若已明確提供 `--raw-dir`／`--availability-file`，不會為了取得不使用的 DB／backup 預設值而初始化正式 `TWStockConfig`。

不同月份或不同官方窗口可重複傳入 `--availability-file`，例如：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_fundamental_statement_items.py --dry-run `
  --raw-dir D:\Min\Python\Project\FA_Data\financial_data `
  --availability-file C:\Temp\mops_2024_03.csv `
  --availability-file C:\Temp\mops_2024_04.csv `
  --availability-file C:\Temp\mops_2024_05.csv
```

讀取器會忽略重複的完整列；若相同 `(stock_code, statement_type, period)` 出現不同公告／provenance，會保留 revision-chain 診斷並拒絕 apply，不猜測哪個窗口正確。這讓多路徑、分月補件能累積 coverage，同時維持正式 mapping／SQLite 的 fail-closed 邊界。

若要先確認整個 raw universe 能否落到既有 schema，可把導入日後的 `statement_retroactive_baseline_availability_2026-06-17.csv` 與 MOPS candidates 一起 dry-run。這可能得到 `ready_for_apply=true`，但必須檢查 quality 分布：baseline 仍是 `degraded`、不能作正式歷史 PIT；只有具官方公告時間且經 owner／reviewer 核准的 rows 才能進入正式 availability mapping。此 hybrid dry-run 不會自動寫入 SQLite，也不會授予 source acceptance 或 Formal credit。

歷史窗口若收到官方 `status=fail` 且零資料列，會計入 `official_no_data_query_count`；這和 timeout、network error、schema drift 的 `failed_query_count`／`invalid_event_count` 不同。官方無資料不可直接補成 baseline，也不可把其他月份的成功列宣稱為全期間 coverage。

季度財報 factor layer 已可用唯讀方式檢查：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_fundamental_factors.py --all-monthly-revenue-stocks --decision-date 2026-06-30 --diagnostic-limit 12 --stock-summary-limit 12
```

2026-06-17 正式 DB inspection 結果：總 factor records 14,840、diagnostics 812；statement factors 為 `fundamental.statement.eps` 1,411 筆、`fundamental.statement.gross_margin` 1,368 筆、`fundamental.statement.operating_margin` 1,374 筆、`fundamental.statement.roe` 1,277 筆、`fundamental.statement.non_operating_income_ratio` 1,261 筆。缺 statement rows、缺必要科目或分母為 0 時只輸出 diagnostics，不輸出中性訊號，不接 `ScoringEngine`。

PB / PS 目前只做來源政策檢查：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_valuation_source_policy.py
```

Month 5 後 P/E、P/B、P/S 都具備 presentation policy。P/B 與 P/S 只接受 governed external observations 或後續明確 backfill records；系統不會在內部用不完整財報推導 book value、share count、market cap 或 TTM sales，也不會把估值指標接進 `ScoringEngine`。

#### Month 5 closeout 判讀

Month 5 Fundamental Layer v1 的完成定義是「基本面資料已能以受治理、可診斷、可追溯的方式進入 factor records / diagnostics」，不是把基本面自動納入推薦分數。使用者在 Daily Decision Desk、Research metadata 或 factor inspection 看到 fundamental diagnostics 時，應將其視為研究風險提示與資料品質揭露；系統不會因此自動買賣、調倉、改寫財報或調整 `ScoringEngine` 分數。下一階段 Month 6 才會討論策略生命週期與 Portfolio feedback 如何使用這些 evidence。

#### 公司清單 / 產業 mapping 更新

`meta_data/companies.csv` 可用官方 TWSE/TPEX 公司基本資料更新。預設 dry-run 不寫檔：

```powershell
.\.venv\Scripts\python.exe scripts\update_company_registry.py --dry-run
```

正式寫入必須人工確認：

```powershell
.\.venv\Scripts\python.exe scripts\update_company_registry.py --apply --confirm apply-company-registry
```

正式 apply 會先備份既有 `companies.csv`，只更新公司 registry CSV，不修改 SQLite、daily price 或 raw financial CSV。2026-06-16 已以官方 TWSE/TPEX 來源正式更新：輸出 2,326 筆、0 diagnostics、無重複 `stock_id`，備份為 `D:/Min/Python/Project/FA_Data/meta_data/backup/companies_company_registry_20260616_031111.csv`。抽查 `3207` 耀勝為 `電子零組件業 / tpex`，`9935` 慶豐富為 `居家生活 / twse`。

CLI 會先讀取官方 JSON OpenAPI；若 JSON endpoint 暫時不可用（例如 HTTP 520），會自動切換至同一官方資料平台的 CSV 來源。JSON／CSV 都失敗時，CLI 會輸出 `status=blocked`、`reason=official_company_registry_source_unavailable` 與 `writes_allowed=false`，return non-zero 且保留既有 `companies.csv`；不得用部分市場回應或舊快照覆寫完整 registry。來源恢復後可重新執行 dry-run，再依既有備份／確認契約 apply。

注意：`companies.csv` 是公司與產業 registry，不代表 `daily_prices` 已具備該股票行情。TPEX daily price 已納入日常市場日價管線；若歷史 TPEX 股票缺舊日價，需由每日股價區間補齊、快速 / 安全更新或背景補齊流程處理，不應用 company registry 或 fundamental layer 假造價格列。

#### TPEX daily price 日常更新與歷史 dry-run

日常快速 / 安全更新會在 TWSE 每日股價後抓取 TPEX official daily close quotes，保存到 `DATA_ROOT/daily_price_tpex/YYYYMMDD.csv`，並在 SQLite 同步時寫入 `DATA_ROOT/sqlite/twstock.db` 的 `daily_prices`。這是市場資料層更新，不修改 `companies.csv`、raw financial CSV、fundamental tables、技術指標算法或推薦分數。

若上櫃股票存在於 `companies.csv` 但缺歷史 `daily_prices`，先使用歷史 dry-run plan：

```powershell
.\.venv\Scripts\python.exe scripts\plan_tpex_daily_price_history_backfill.py --start-date 2026-01-01 --end-date 2026-06-16
```

dry-run plan 只讀官方來源或指定 source JSON、SQLite 既有資料，輸出日期範圍、每日來源筆數、已存在筆數、新增候選筆數、失敗日期與估計耗時，不寫正式 DB。正式歷史回補需另行人工確認。

單日受控補寫工具仍保留給已確認日期使用。預設先 dry-run：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_tpex_daily_prices.py --date 2026-06-16 --dry-run
```

dry-run 只讀官方 TPEX daily close quotes 與 SQLite，顯示 `ready_for_apply`、`insert_count`、`existing_count` 與 diagnostics，不寫入資料。正式寫入必須先取得人工確認，再執行：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_tpex_daily_prices.py --date 2026-06-16 --apply --confirm apply-tpex-daily-price-backfill
```

正式 apply 會先備份 DB；缺少 `--confirm apply-tpex-daily-price-backfill` 時會拒絕執行。此 workflow 只寫入 `daily_prices`，不會修改 `companies.csv`、raw financial CSV、fundamental tables、技術指標或推薦分數。批次模式只處理指定交易日、四碼普通股且收盤價為正數的 rows；債券、權證、ETF 或停牌無價 rows 會被跳過。

若官方 afterTrading response 已由受控唯讀 probe 保存為 raw bytes，可用 pre-captured 模式先核對單日 provenance。`--source-raw` 與 `--capture-metadata` 必須同源；metadata 需保留官方 HTTPS URL、production 日期參數、HTTP status、raw bytes／SHA-256 與完整 body 讀取完成時間，且必須明確指定 `--required-symbol 1569`。此模式只接受 `www.tpex.org.tw/www/zh-tw/afterTrading/otc`，會驗證 payload 日期、行情 table、1569、CSV 狀態與 SQLite conflict；預設 dry-run 不寫 custody、CSV 或 DB：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_tpex_daily_prices.py `
  --source-raw <official-response.body> `
  --capture-metadata <capture-metadata.json> `
  --date 2026-09-18 --required-symbol 1569 `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data\output `
  --db-file D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --backup-dir D:\Min\Python\Project\FA_Data\meta_data\backup `
  --dry-run
```

只有在單日來源、DB conflict、CSV conflict 與 custody 條件都由 owner 審核後，才可加上 `--apply --confirm apply-tpex-daily-price-backfill`。pre-captured apply 會先以 official custody helper create-only 保存 raw／receipt，再 create-only 保存 CSV、建立 DB backup，並以 query-only readback 核對所有 normalized rows 及 1569；raw lane 使用 insert-only，若 preflight 後已有相同 key，只回報實際新增數，不覆寫既有列。capture 發生在交易日之後時，receipt 會保留 `historical_pit_status=not_proven_by_after_close_capture` 與 `formal_source_contract_eligible=false`，不得把晚到資料解讀成舊 decision-time、natural 或 calibration credit。

2026-06-16 已對正式 DB 執行一次：dry-run 顯示可新增 877 筆、0 diagnostics；正式 apply 後備份為 `D:/Min/Python/Project/FA_Data/meta_data/backup/twstock_tpex_daily_price_backfill_20260616_034627.db`。驗證結果：`daily_prices` 的 `20260616` 有 877 筆四碼上櫃日價、0 duplicate `(證券代號, 日期)` keys；`3207` 耀勝已有 `20260616` 日價，`9935` 慶豐富既有日價仍保留。

2026-09-19 另完成 2026-09-18 的 official afterTrading raw 單日補入：正式 DB 原有 1,090 rows，經 868 rows 的 normalized candidate 且 overlap／content conflict 為 0 後，新增 868 rows，日期總數為 1,958；1569 收盤 `55.50`、成交股數 `5,164,000`。官方 raw 與 receipt SHA-256 為 `sha256:2eae9b5185bfde35ddb63ed6ed4d331f3a97a195229394a693db54ddc9739e62`，捕捉完成時間為 `2026-09-19T07:20:33.071218+00:00`；backup 為 `D:/Min/Python/Project/FA_Data/meta_data/backup/twstock_tpex_daily_price_backfill_20260919_003431.db`。此為資料完整性補入，receipt 仍標示晚取得、非 formal source contract eligible，不產生 natural／calibration／promotion／broker credit。

#### 估值 metrics backfill

正式 DB 已有 `fundamental_valuation_metrics` schema。P/E v1 可由 SQLite `daily_prices.本益比` 與 `meta_data/companies.csv` 產業 mapping 建立受治理 valuation records，並計算同產業整數基點分位。預設只執行 dry-run：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_valuation_metrics.py --dry-run
.\.venv\Scripts\python.exe scripts\backfill_valuation_metrics.py --as-of-date 2026-06-15 --dry-run
```

未指定 `--as-of-date` 時，工具會選擇 `daily_prices` 中最新有 P/E 的交易日。dry-run 只輸出 plan，不寫入 SQLite；P/E 非正數、無法解析或缺產業 mapping 的 rows 會列為 diagnostics 並跳過。同產業只有單一樣本時會保留 record，但 `industry_percentile_bp` 為空且 quality 降級，後續估值 adapter 只會輸出 diagnostics。

正式寫入必須先取得人工確認，再執行：

```powershell
.\.venv\Scripts\python.exe scripts\backfill_valuation_metrics.py --apply --confirm apply-valuation-metrics-backfill
```

正式 apply 會先備份 DB；缺少 `--confirm apply-valuation-metrics-backfill` 時會拒絕執行。此 workflow 只寫入 `fundamental_valuation_metrics`，不會修改 raw CSV、`companies.csv` 或既有核心表。若指定 `--db-file` 但未指定 `--backup-dir`，備份會放在該 DB 同層的 `backup` 目錄；未指定 `--db-file` 時才沿用正式 `DATA_ROOT/meta_data/backup`，明確的 `--backup-dir` 優先。2026-06-16 更新官方 `companies.csv` 後再次執行正式 apply：最新 P/E 日為 `2026-06-15`，來源 1,090 筆，831 筆可正規化，259 筆 diagnostics；正式表 count 為 831，0 duplicate primary keys，quality 全為 `observed`，DB 備份為 `D:/Min/Python/Project/FA_Data/meta_data/backup/twstock_valuation_metrics_backfill_20260616_031146.db`。

## 9. Research Lab / 策略回測

### 9.1 五種實驗模式

| 模式 | 主要用途 |
|---|---|
| 單股回測 | 驗證一檔股票套用策略後的交易表現。 |
| 批次股票回測 | 比較同一策略在多檔候選股票上的差異。 |
| 固定組合回測 | 研究固定股票清單的逐檔結果；目前 Registry 保存採 per-stock run，`fixed_basket_stock` 只表示固定清單來源，不是共享現金組合。 |
| 推薦系統回放 | 回放推薦配置與名單。 |
| 策略研究 | 比較策略模板、參數、最佳化與驗證結果。 |

模式下方會用「適合 / 輸入來源」說明目前模式該用在哪種研究情境，以及主要輸入來自股票代號、候選池、固定清單、推薦結果或策略模板。

Research Lab 左側設定面板預設保留足夠寬度給長下拉選項與表單欄位，右側結果區吃剩餘空間；一般 1400px 預設主視窗不應需要手動左右拖動才看得到完整「執行價格」等設定列。

在窄版研究時（寬度低於 1200px，例如 fixed 1024×768），左側設定與右側結果會改為上下堆疊，並依目前 viewport 高度重新分配兩區，保留可操作的設定與結果空間；1366px 維持左右分欄。「收合左側設定」仍只改變 UI 空間，不改參數、已選 run 或結果。比較前先核對股票池、日期區間、成本政策、成交假設、樣本數與 benchmark；不相容 run 以中文原因揭露，不能用一個綠色總分掩蓋差異。

### 9.2 基本設定

1. 選擇策略來源或載入 Preset。
2. 選擇單股或選股清單。
3. 設定開始與結束日期。
4. 設定初始資金、手續費與滑價。
5. 執行價格建議使用 `next_open`；`close` 是同根 K 收盤成交假設，必須清楚揭露。

策略研究模式的 Optimization 與 Walk-forward 是互斥操作；兩者預設都不勾選，勾選其中一項時另一項會自動取消，執行按鈕與狀態只會反映目前唯一的研究操作。

推薦系統回放會顯示並鎖定實際 replay contract：`next-session-open.v2`、百分比停損／停利，以及目前畫面中的資金、手續費與滑價假設；離開回放模式後，原先的模式與可編輯狀態會恢復。固定組合仍是逐檔研究結果，不是共享資金 portfolio engine。

`next_open` 新結果使用 `next-session-open.v2`：T 收盤訊號最快於下一可交易 session 的有效開盤成交。缺開盤、零量或停牌延後，不回退收盤價；期末沒有後續 session 時委託保留未成交，已有部位按期末價格估值，不合成強制清倉。單股／批次／固定組合的 per-stock 結果遵守同一契約；固定組合仍不是完整共享現金 portfolio engine。

開始日期與結束日期可開啟日曆選取；開始日期預設為今天往前一年，結束日期預設為今天。日曆開啟時會先定位到今天，方便從目前日期往前選擇研究區間。

### 9.3 停損、停利與部位

- 百分比模式：使用固定停損停利百分比。
- ATR 倍數模式：依市場波動調整距離。
- 全倉：可用資金集中於目前部位。
- 固定金額：每次使用指定金額。
- 風險百分比：依風險比例與 ATR 決定部位。

部位管理包括最大持倉數、等權/分數加權/波動調整、加碼、重新進場與冷卻期。

台股整股模擬以 1000 股為單位。高價股若資金不足一張，可能產生 0 交易。

最大持倉數設為 `0` 代表無限制；設為 `1` 代表最多同時只持有 1 檔。這是部位數量限制，不是買賣訊號來源。

### 9.4 市場限制

- 漲跌停限制
- 成交量限制
- 最大參與率

如果訊號很多但交易為 0，先檢查資金、整股限制、成交量與參與率，不要直接判定策略沒有訊號。

### 9.5 固定門檻與百分位排名

- 「固定門檻」使用固定買賣分數。
- 「百分位排名」使用 T-1 以前的 expanding 歷史分布，暖機需要 60 個有效觀測值。
- 暖機完成前不應產生 quantile 交易訊號。
- 比較兩模式時必須使用相同資料、成本、成交假設與期間。

### 9.6 參數最佳化

1. 選擇目標：Sharpe、年化報酬或 CAGR-MDD。
2. 設定工作線程數。範圍為 1 到 8，預設使用保守上限；目前是 ThreadPool，不是 ProcessPool 多進程。
3. 對要掃描的參數設定固定值或範圍。
4. 執行參數掃描。大型掃描會先顯示預估組合數、worker 數、資料來源與取消提示，確認後才開始。
5. 在「最佳化 / 驗證」查看結果。
6. 選取結果後按「套用選中參數」。

資料與效能邊界：單股最佳化會在執行前預載該股資料一次；`config.use_sqlite=True` 時優先讀 SQLite，缺資料或讀取失敗才 fallback CSV。Optimizer 會用 bounded in-flight futures 分批提交任務，避免一次把所有參數組合送進 ThreadPool。

取消流程：按取消後系統會停止提交新組合，並清理已啟動子任務；清理期間 UI 會顯示「已送出取消」。若組合數很大，已啟動的少量子任務仍需要安全結束才會完全解鎖。

最佳化結果是 In-Sample 候選，不能直接視為可靠策略。表格上方的「Top-N 穩定性（探索性）」只根據目前保留的 Top-N：objective top／median／worst、dispersion，以及每個參數的 unique count、數值範圍／類別值與 Top-5 modal share（最常見取值比例；顯示有值分子／Top-5 分母）。摘要另顯示 `objective valid n / retained N`；缺少 objective 的列不補零，且不混入 objective 統計。它不是完整 parameter surface、confidence interval 或 OOS 證明；樣本不足會顯示 `insufficient`，必須另跑 Walk-forward／OOS。

### 9.7 Walk-forward

- Train-Test Split：單次訓練/測試切分。
- Walk-forward：以訓練月數、測試月數與步進月份滾動驗證。

結果摘要會顯示樣本可靠度提示。Train-Test 會列出訓練集交易數與 OOS 交易數；Walk-forward 會列出 Fold 數、OOS 交易數與測試期正向 Sharpe 覆蓋率。Fold 少於 3、OOS 交易數不足，或出現勝率 100% 但最大回撤偏大的不直覺組合時，系統會提示「樣本不足，不宜作正式策略判斷」。此提示只使用該次驗證已產生的結果 metadata，不重新抓取目前資料，也不改變績效計算。

至少檢查：

- OOS 報酬是否穩定
- 最大回撤是否惡化
- 交易次數是否足夠
- 不同窗口是否只靠單一期間獲利
- fixed / quantile 是否用完全相同條件

本專案 2026-06-14 基準實證使用 10 檔股票、每檔 8 個 OOS fold；fixed 57 筆、quantile 79 筆交易均通過 20 筆最低樣本 Gate，Regime coverage 為 100%。結果未顯示 quantile 的平均 OOS Sharpe 優於 fixed，詳見 `docs/06_qa/WALK_FORWARD_COMPARISON_REPORT.md`。

### 9.8 執行、取消、保存與升級

- 下方綠色「主要執行」是唯一執行 CTA；它會依模式與進階選項顯示「執行單股回測」「執行批次回測」「執行固定清單逐檔回測」「執行推薦回放」「執行參數最佳化」或「執行 Walk-forward 驗證」。按鈕旁的執行意圖會說明輸入母體；最佳化、Walk-forward、推薦回放的舊內嵌按鈕只保留相容屬性，不再重複顯示。
- 「取消執行」：合作式取消；已開始的單檔工作可能安全收尾。
- 「保存結果」：將單股回測、批次回測單檔結果、固定組合 per-stock 結果或推薦回放結果保存到 Research Run Registry；系統會保存參數快照、資料 fingerprint、成本、成交假設、績效摘要、factor snapshot / contribution metadata、equity curve 與 trades。單股、批次與固定組合 per-stock 結果的 factor metadata 來自該次回測已產生的 score/factor records，不會在保存時重算分數或重新抓取資料。新的推薦回放 Registry save 必須有該次執行的完整 `RecommendationPortfolioBacktestResultDTO`，並把 v1 snapshots、holdings、contributions、summary、diagnostics、hints 與 details 封存；不接受從摘要或舊 row dict 拼出 DTO。若有同次 invocation 的 typed parent／children，UI 保存前會逐一 create-only 保存並讀回驗證 R012 child，再保存 lineage sidecar descriptor。Registry `run_id`、replay parent ID 與 legacy portfolio run ID 是不同識別碼。
- 「升級為策略版本」：新版 Gate 必須讀取 Research Run Registry，不得只靠單次 summary；run 需 committed / valid、未封存、未升級、具備可還原參數合約版本，且通過最低 validation gate 與 Month 6 lifecycle gate。Lifecycle gate 會檢查交易次數、總報酬、Sharpe、最大回撤、勝率、benchmark excess return、factor quality 與 regime compatibility。成功升級後，若 lifecycle evidence repository 已啟用，系統會保存 applied evidence，包含 decision snapshot、gate reasons 與 version id。

「保存結果」與「升級為策略版本」按鈕會依目前是否已有可保存結果、是否已保存、validation 是否允許而啟用；停用時 tooltip 會說明原因。保存成功訊息會顯示 Registry run ID 與下一步。

保存、刪除或升級成功後，Research Lab 會刷新歷史列表、圖表選單與 Registry 比較面板，並在進度文字顯示剛保存的 run ID 或升級後的策略版本 ID。推薦回放存入 Registry 後，可到「研究 Registry」篩選「推薦回放」，只選取一筆並按「開啟推薦回放」讀回已保存結果；開啟不會重新跑回測，也不會把 Registry run 放入「歷史推薦回測」舊格式下拉選單。Registry 讀回為唯讀，不可由舊刪除／升級按鈕操作或再存成另一筆。

Month 6 lifecycle gate 的預設最低交易數為 20 筆，且缺 benchmark excess return 或 factor snapshot 時會保守降級，不允許只靠單次高報酬升級策略版本。通過 Gate 不代表已完成實盤驗證。Demote / retire 判斷會先以 proposed evidence 保存，供人工 review；系統不會自動刪除策略版本或改寫歷史 run。

保存安全限制：

- 只有目前成功完成且尚未被新一輪執行取代的結果可以保存。
- 開始新一輪回測或推薦回放後，舊 pending result 會被視為 stale，不可再保存。
- Registry 寫入採 SQLite metadata + Parquet 明細；若 hash 不符或檔案不完整，載入時會以完整性錯誤處理，不會靜默讀取部分結果。
- 推薦回放若有完整 DTO、但 custom／legacy provider 沒有可封存的 canonical child，v1 recommendation rows 仍會保存，manifest 會以 schema version 1、相同 replay parent ID 標示 lineage `unavailable`；這不代表沒有推薦列，也不會補造歷史 child。Registry 讀回時會先驗 sidecar、Parquet 與 manifest identity/hash，再驗完整 declared R012 child 集合；任一完整性錯誤都不顯示 partial DTO／children，也不會暗中修復或重算。舊 markerless Registry run 可供既有 metadata／equity／trades 比較，但沒有完整 portfolio DTO；開啟時會明示 unavailable，不從摘要重建。Registry 回放圖表不回抓目前 benchmark，因此 benchmark 時序 overlay 會標示不可用。舊 portfolio JSON 與「歷史推薦回測」下拉選單仍只屬 legacy repository；跨 store failure recovery 與 V-REPLAY 仍是獨立限制。
- Legacy 單股回測 / 推薦組合保存庫仍可用於歷史資料與 backfill；新的「保存結果」入口以 Research Run Registry 為準。

### 9.9 結果分頁

Registry 保存 `execution_contract`、凍結成本／部位假設與 run_status。v2、legacy 同日收盤及無版本舊 run 不互相升級；不同執行版本或 cancelled／partial 結果停止績效混排與權益標準化。成本／稅／lot 假設不同為 Caution。推薦 v2 的 0.10 停損比例保存為 1000 bp，14.25 bp 手續費保存為 1425 bp_x100；判讀時先確認單位與 manifest。

保存過程依 staging→files_ready→committed 保護半成品。刷新、列表與載入都不暗中修復；只載入 committed、valid 且雙 Parquet hash 一致的結果。缺檔、損毀、未知 schema／execution version 時停止比較並顯示原因。維護 owner 需先在隔離副本驗證，再明確執行 reconciliation；不要把重新整理當修復操作。原始 run 不因市場追加未來資料而重算。

Evidence 的 close-to-close outcome 是事後診斷，不是 v2 執行 PnL；成熟 outcome 仍保留原 event 的 replay／forward／paper／live 宣告來源。應用服務的人工覆盤接點接受 run_id、reviewer、notes 與下一輪研究問題，回傳原推薦 snapshot、event、outcome 與缺件；沒有新增 UI 核准按鈕。宣告 tier 與 reviewer 字串不等於正式來源接受、真實時間或身分驗證，提案不增加 Formal credit 或 promotion 權限。

比較畫面先顯示可直接比較／需謹慎比較／不可直接比較及其原因，再顯示既有淨值、回撤、換手、成本或 benchmark 欄位。數值未由服務提供時顯示 `unknown` 與原因，不在 UI 補值。Registry 清單可依類型、strategy、tag 篩選並分頁；勾選的 run ID 會跨頁保留，最多 5 筆，畫面顯示「已選 n / 5」與清除選取入口，選滿 2 至 5 筆才可比較。結果的研究回放、自然前瞻觀測、Paper 成交紀錄與正式可用 scope 必須分開，任何一層都不能替代另一層。

- 實驗摘要：績效摘要與交易明細；切換研究模式時會作為單股 drill-down 的 primary 頁。
- 分析診斷：分析師 KPI、trailing 20／60 報酬與年化波動、月度報酬矩陣、frozen benchmark attribution。曝險與現金使用率以 bp 顯示；Turnover 定義為買賣成交金額總和／權益曲線平均權益；成本 fee／slippage／total 以初始資金為分母。rolling 只用 trailing equity，月度採相鄰月末權益變化；首月無明確 initial capital／起始權益 anchor 或 legacy 缺欄位時顯示 `unknown` 與原因，不補算、不回抓資料。
- 圖表：權益、回撤、交易報酬、持有天數。交易報酬會依樣本數自適應：少於 10 筆逐筆用零軸發散條／lollipop 顯示，每筆標出正負與數值，並明示不宜解讀為分布或 95% VaR；至少 10 筆才顯示直方圖，至少 20 筆才顯示 95% VaR。樣本不足時只代表估計不穩定，不應把單筆或小樣本視為策略分布。
- 最佳化 / 驗證：參數掃描與 Walk-forward。
- Legacy 歷史：載入、刪除與比較舊 `BacktestRunRepository` 結果；這是相容歷史入口，不是統一 Research evidence SSOT，不自動遷移或重算。
- 研究 Registry：列出正式 Research Run Registry 中的 run，可依類型、strategy、tag 篩選並分頁瀏覽；類型在 UI 會明確顯示「單股回測」「批次股票回測」「固定組合（逐檔）」或「推薦回放」，存檔 metadata 仍保留原始 run type。run 清單每列以兩行顯示名稱、類型、策略與時間，勾選可跨頁保留（最多 5 筆，畫面顯示選取計數與清除入口），不需要猜測 Ctrl 多選是否能跨頁。選取 2 至 5 個 run 後，先以深色語意狀態列顯示「可直接比較 / 需謹慎比較 / 不可直接比較」與中文原因，再把所選 run 映射為 A / B / C / D / E 代號；摘要卡只顯示代號與中文欄位重點，長 run name / run_id 保留在上方對照與 tooltip，不塞進每個差異欄位。指標區會以小型對照表呈現，左欄為中文指標名稱，右欄為 A / B / C 數值，避免長段落混在一起。標準化權益需先按「比較選中」才會觸發，且所選 run 必須都有 equity curve 與共同日期；沒有共同日期或缺欄位時會顯示原因，不會補值或推估。比較是 evidence 入口，不等於可 promote。推薦回放另有單筆「開啟推薦回放」入口；舊 markerless run 顯示完整 DTO unavailable，不重新計算。開啟完整 DTO 時只讀 Registry 與已驗證 child artifact，完整性錯誤不顯示部分結果；Registry run 不會進入 legacy history 下拉選單或 legacy 刪除／升級流程。
- 批次／固定清單模式會把批次結果設為 primary，仍保留摘要、分析診斷、圖表供雙擊單檔 drill-down；固定清單的 per-stock 結果不代表共享現金 portfolio。
- 證據覆盤：唯讀檢查已保存 evidence / observation / review，以及 Windows Task Scheduler 產出的最新 scheduled dry-run 狀態。子頁包含「前瞻證據」、「研究落差」、「訊號衰退」、「決策品質」、「覆盤歷史」與「排程狀態」。頁面上方會顯示目前實際讀取的 SQLite 資料庫路徑，並提供「複製路徑」按鈕，方便確認是否使用 working-copy DB。各子頁日期欄位使用日曆選擇器，未選日期時不套用日期篩選；未選日期的日曆會先定位到今天，不會停在 sentinel 年份。
  - 前瞻證據：檢查已保存 evidence events / outcomes 的 forward summary。可依日期、event type / family、source type、股票、regime、sector、profile、strategy version、window days、group by 與最小樣本數篩選，並查看事件總數、已完成 / 等待中 / 缺失結果、樣本不足、benchmark / industry 缺口、quality 與 warnings。close-to-close forward return 是 research basis，不代表可執行績效。
  - 研究落差：檢查 portfolio source trace、Research Run / strategy version、evidence event / outcome link、portfolio mode、gap metrics、attribution categories、match confidence、quality 與 warnings。沒有真實交易與人工 override 記錄時，只能解讀為 research / simulated gap。
  - 訊號衰退：檢查 event_type、event_family、strategy_version、profile scope 的短窗 / 長窗樣本、decay score、status、lifecycle candidate、confidence、quality 與 warnings。`demote_candidate` / `retire_candidate` 只是人工覆盤候選，不會自動套用。
  - 決策品質：檢查週 / 月 / custom review item、process score、reason codes、review question、open / reviewed / dismissed 狀態、quality 與 warnings。score 只代表流程 evidence，不是投資能力、不是交易建議，也不是責備使用者。
  - 排程狀態：唯讀讀取 `OUTPUT_ROOT/scheduled/data_freshness/latest_status.json`、`OUTPUT_ROOT/scheduled/recommendation_snapshot/latest_status.json`、`OUTPUT_ROOT/scheduled/evidence_pipeline_dry_run/latest_status.json`、`OUTPUT_ROOT/scheduled/forward_outcomes/latest_status.json` 與 latest status 指向的 report preview。畫面顯示 data freshness、recommendation snapshot result id / 筆數 / screening matrix rows、evidence dry-run、forward outcome 的 status／掃描事件數／寫入結果數／待成熟數，並顯示 health 的最新合格事件日、完整身份事件數、cohort／決策日數、各 horizon ready／pending／missing、最近 capture／outcome／evaluation、下一成熟日、blocking reason、next action、recovery verification 與 blockers／warnings；同時保留 `pipeline_overall_status`、report path、warning occurrences、blocking gaps 與 `confirm / writes_recommendation_result / writes_evidence_db / forward_outcome_writes_evidence_db / auto_trading / lifecycle_action` 安全邊界。health 分類 `normal_completion`、`normal_no_new_outcomes`、`waiting_for_natural_maturity`、`actionable_engineering_blocker` 與 `external_source_missing` 會投影到 machine status；confirmed run 的工程／來源阻塞也會在 receipt 頂層以 `blocked`／非零 exit code fail closed；缺少新 receipt 會顯示 source gap，不補值。推薦結果寫入與 forward outcome 寫入會分別標示 research-only output，不會和 production evidence / trading write risk 混為同一概念。若 scheduled recommendation latest status 缺失，只有已由唯讀 query 驗證、同一 decision date 且完成決策的舊人工結果，或保存的 `execution.request.config_snapshot.manual_qt_snapshot=true` canonical Qt manual execution，才會把 recommendation source 顯示為 `manual_result`、status 顯示為 `manual_observed`；這只代表人工結果可供判讀，不代表 scheduled snapshot 正常，也不計入 scheduled 共同觀測天數。下方狀態明細採「判讀摘要 / 人工要看 / 關鍵欄位 / 安全邊界」優先，report preview 只保留前段 metadata，完整 JSON diagnostics 請依 `report_path` 或 `forward_outcome_status_path` 開啟原始 receipt。這只是讓每日 scheduled output、forward outcome 累積與人工補跑觀察在 UI 可見；頁面不重跑 producer／pipeline、不寫 evidence DB、不自動追加 `POST_V1_EVIDENCE_PIPELINE_MULTI_DAY_DRY_RUN_RECORD.md`。
  - 推薦結果來源判讀與排錯：入口在「證據覆盤 → 排程狀態」。舊 `rec_YYYYMMDD_*.json` 與 `scheduled_rec_YYYYMMDD_*.json` 檔名只用來發現候選 ID；實際 bytes、payload `result_id` 與 `run_context.as_of_date` 都由唯讀 Recommendation Execution query 驗證後，才計入人工或排程觀測日。損毀、連結檔、ID／日期不符、unsafe ID 或 query integrity 錯誤會留診斷且不算觀測，不要手動修檔或複製成第二份 JSON。當排程 latest status 缺失時，只有同日、完成且決策可用的已驗證 legacy manual 結果，或 `execution.request.config_snapshot.manual_qt_snapshot=true` 且日期一致的 canonical Qt execution，才可顯示為 `manual_observed`；舊結果按 `rec_YYYYMMDD_*.json` ID 日期和已驗證 `run_context.as_of_date` 判別。canonical scheduled inventory 需有已保存 `scheduled_snapshot=true`，其決策日期還要與可用的 request／context as-of 日期相同；沒有來源標記或日期矛盾時會顯示 unavailable／ambiguous，不推測為人工或排程。單一 legacy namespace 保留既有檔名排序；legacy 與 canonical 同日候選只有在全部保存時鐘含時區且可轉 UTC 比較時才選較新，naive／未知時間會明示 ambiguous。舊檔沒有可信歷史 digest 時，畫面只取得此次 read-time hash，不能證明檔案過去未被替換。排錯時先查看狀態診斷中的 result ID、日期與 query failure；觀測日缺少時確認結果是否已保存、是否同日及是否具來源標記，不用重新執行推薦或 ML 補值。
  這個分頁只使用 dashboard service、已保存 read model 與 scheduled output status 檔，不重算推薦、不重算策略、不讀 UI state、不寫 evidence，也不建立或修改排程；樣本不足或資料降級時只能作資料品質檢查，不可作訊號有效性判斷。
  - 覆盤歷史：只讀取已保存 weekly review；若 history DB／table 不存在，畫面會顯示 `evidence_operations_history_db_missing`／`...table_missing` 診斷與 CLI 建立指引，絕不因刷新畫面建立空 schema。
  - 研究落差、訊號衰退與決策品質子頁以 dashboard 專用 SQLite 唯讀連線查看既有歷史，不會建立資料庫、資料表或索引。若資料庫或對應 evidence table 不存在，畫面會顯示明確診斷並以空狀態呈現；重新整理不會修復或初始化來源。需要新增 evidence 時，請使用各自明確的 dry-run／保存流程，不要把 dashboard 刷新當成寫入操作。
- 批次結果：排行榜與整體統計，雙擊股票可載入明細；排行榜的 MDD 以回撤幅度絕對值排序，較小回撤優先。摘要會分開顯示總標的數、有效回測、失敗／無交易、coverage（有效回測／總標的），以及「獲利標的／有效回測」；後者是標的層級比例，不是交易筆勝率。排行榜的 `WinRate%` 只有在單檔交易明細有值時才代表交易筆勝率。CAGR／MDD 中位數會標出各自有效樣本數，不把缺值或失敗標的混入母體。這些欄位只用來理解本批次覆蓋率與結果分布，不代表正式策略判斷、交易建議或持倉調整。
- 推薦回放：摘要分為概況、交易假設與可信度、風險與情境指標、Monte Carlo 情境；V1.2 result details 會補充 `rolling_risk_metrics`、`microstructure_preflight` 與 `relative_attribution`，用來判讀 rolling risk、可選台股微結構風險與 benchmark / industry / concept 背景；下方以分頁呈現組合價值 / 回撤圖、期間持倉、股票貢獻與交易紀錄。

### 9.9.1 Evidence Pipeline Runner（手動 dry-run）

Evidence Pipeline Runner 是手動 CLI，用來模擬每日 evidence pipeline；它不是 Windows Task Scheduler、cron 或背景 job。預設只做 dry-run，所有 Evidence／Decision Desk repository 讀取皆唯讀，不初始化 schema 或寫入來源 DB；report、status 與獨立衍生輸出仍可保存。正式 `--confirm` 只能對 explicit working-copy DB 執行，且仍需人工審核 diagnostics report。若 legacy recommendation metadata 含日期，只有具名 date／datetime 欄位以 ISO 編碼，既有合法字串與 canonical hash 保持相容；未知型別仍報錯，不以通用字串轉換掩蓋問題。

常用命令：

```powershell
.\.venv\Scripts\python.exe scripts\run_evidence_pipeline.py --decision-date 2026-06-30 --dry-run --json-output
.\.venv\Scripts\python.exe scripts\run_evidence_pipeline.py --decision-date 2026-06-30 --dry-run --sources recommendation,watchlist-trigger,portfolio-alert,risk-prompt --report-output output\evidence_pipeline\reports\evidence_pipeline_2026-06-30.md
.\.venv\Scripts\python.exe scripts\run_evidence_pipeline.py --decision-date 2026-06-30 --confirm --db-path <working-copy-db>
.\.venv\Scripts\python.exe scripts\inspect_evidence_source_coverage.py --db-path <working-copy-db> --decision-date 2026-06-30 --json-output
.\.venv\Scripts\python.exe scripts\smoke_evidence_pipeline_working_copy.py --source-db-path <source-db> --working-copy-db-path <working-copy-db> --decision-date 2026-06-30 --repeat 2 --json-output
.\.venv\Scripts\python.exe scripts\evaluate_evidence_scheduler_readiness.py --db-path <working-copy-db> --json-output
.\.venv\Scripts\python.exe scripts\evaluate_evidence_scheduler_readiness.py --db-path <working-copy-db> --approval-artifact <owner-approved-json> --json-output
.\.venv\Scripts\python.exe scripts\inspect_data_source_capabilities.py --json-output
.\.venv\Scripts\python.exe scripts\inspect_corporate_action_policy.py --json-output
```

支援參數包含 `--decision-date`、`--start-date`、`--end-date`、`--db-path`、`--sources`、`--windows`、`--group-by`、`--window`、`--min-sample-size`、`--limit`、`--dry-run`、`--confirm`、`--skip-snapshot`、`--skip-capture`、`--skip-outcomes`、`--skip-summary`、`--json-output`、`--report-output`。`--dry-run` 與 `--confirm` 互斥；`--confirm` 必須指定 `--db-path`。若 DB path 看起來是正式 DB，還需要額外 `--allow-production-db-confirm`，但一般 QA 不應使用正式 DB。

Runner steps：

1. `source_coverage_check`
2. `capture_decision_desk_snapshot`
3. `capture_evidence_events`
4. `calculate_forward_outcomes`
5. `summarize_forward_performance`
6. `write_diagnostics_report`

輸出 summary 會包含 events_seen、events_inserted、events_skipped_duplicate、outcomes_attempted、outcomes_created、outcomes_updated、outcomes_pending、summary_groups、groups_ready、groups_insufficient_sample、groups_degraded、warnings_count、warning_counts、warning_unique_count、warning_top_counts、errors_count、blocking_gaps、warnings 與 scheduler_readiness。Markdown report 的 `Warning Summary` 會分開顯示跨 pipeline steps 的 warning occurrence 總量與唯一 warning token 數，`Warning Breakdown` 會列出完整 warning token 分布；`diagnostic:<code>` 代表 warning 等級 diagnostic，不代表 blocking error。Readiness 最高只到 `ready_for_manual_confirm`，不代表 production scheduler 已批准。

V1.5 後，source coverage 由 `EvidenceSourceCoverageService` 統一判讀。`recommendation_persisted_missing`、`decision_desk_snapshot_missing`、`watchlist_trigger_snapshot_section_missing`、`portfolio_alert_snapshot_section_missing`、`risk_prompt_snapshot_section_missing` 是 durable source blocking gaps；`screening_matrix_missing`、`why_not_payload_missing` 與 `liquidity_gate_payload_missing` 是 payload warnings，會使整體 readiness 維持 `dry_run_only`，但不等於 durable source missing。V1.7 後新保存的推薦結果會包含 screening matrix、Why Not 與 Liquidity payload；舊推薦結果若缺 payload，只會列 warning / diagnostic，不回補、不重算。2026-07-06 後，成交量門檻造成的 empty strategy result 會被保存為 Liquidity payload，而非一般 `strategy_filter_no_signal`。若 runner dry-run 在同一輪建立 transient Daily Decision Desk snapshot，報告會以 `source_coverage_basis=dry_run_transient_decision_desk_snapshot` 標示，並把同輪 transient snapshot 用於 source coverage 判讀，避免把 dry-run 未寫 durable snapshot 誤列為 stale `decision_desk_snapshot_missing`；這只影響 report diagnostics，不寫 durable snapshot 或 production evidence DB。若使用 `--sources why-not` 或 `--sources liquidity-gate` 明確要求 exclusion source，runner 仍會在該請求層級阻擋缺 payload 的 capture。Current 查詢會以台灣市場今日為日期上限；active Decision Desk future row 會列為 `decision_desk_snapshot_future_dated` blocker，並排除於 current latest，原始 row 不刪除。`EvidenceSourceCoverageService`、`inspect_evidence_source_coverage.py` 與 `inspect_decision_desk_snapshots.py` 都是 query-only 檢查，不會因 repository 初始化 schema 而寫入正式 DB。`inspect_data_source_capabilities.py` 只檢查 source registry，不抓外部資料；`inspect_corporate_action_policy.py` 只輸出價格政策與資料表候選，不建立 adjusted price、不寫正式 DB。

### 9.9.1a 每日前瞻結果累積

`baldr-forward-outcomes-daily` 在 05:40 執行獨立的 bounded producer，讓前一個
Decision/Evidence capture task 已保存的事件可以在後續交易日成熟時補上 outcome。它以
`data_as_of_date` 為價格可見上限，預設只讀最近 120 個曆日、最多 2,500 個事件，觀察窗為
5／10／20／60 交易日，固定使用 `close_to_close_event_date`。排程 wrapper 預設以
`event_type=recommendation_included` 消費已具身份契約的推薦事件，避免低價值診斷事件
佔滿每日上限；wrapper 同時使用 `--require-cohort-identity`，缺少明確策略、成本、
benchmark、universe 或正整數 horizon 的舊事件會跳過並記入
`events_skipped_incomplete_identity`；可透過 `FORWARD_OUTCOME_EVENT_TYPE` 受控切換。未成熟的 60 日區間、缺事件價、
缺大盤／產業 benchmark 或政策資料會留下 `pending`／`missing` 與 warning，不以曆日補算、
不回填事件身份，也不會把結果變成投資建議。

官方交易日 maturity 與 legacy 有效價格 row offset 已確認不一致時，outcome 為
`PENDING + DEGRADED`，保留兩種 maturity 日期與 lineage，尚不計算報酬、benchmark、
MAE 或 MFE。既有歷史 READY mismatch row 也會在 Forward／Score reader 排除於績效，
畫面列為「待觀測/受阻」並揭露 `maturity_calendar_comparison_blocked`；這是時間契約需
修復，不是單純等待樣本成熟。`annual_plan_only` 本身不阻擋已核對 match 的資料。

選取順序先以 `(event_id, window_days, return_basis)` 的 ready 缺口把未完成事件排在前面，
再以完整 cohort identity 篩選並套用相同的 2,500 event 上限；因此每日新事件不會長期排擠
舊的 60 日 pending。若 health 分類是 `actionable_engineering_blocker`，先修正身份／caller／
DB 路徑再重跑；`external_source_missing` 代表補齊指定來源；`waiting_for_natural_maturity`
才代表只需等待自然交易日。confirmed run 遇到前兩類時，receipt 頂層必須是
`status=blocked`／`exit_code=2`，並列出 `blocking_reason`、`next_action`、
`next_maturity_date` 與 `recovery_verification`；同輪已完成的 bounded outcome write 仍可
存在，重跑以自然鍵冪等。dry-run 保留 `status=dry_run`，但仍揭露 blocker。`normal_no_new_outcomes`
是冪等 no-op，不需要為了製造數字改模型。

排程 wrapper 會明確傳入 `--confirm --allow-production-db-confirm`，因此只更新正式
SQLite 的 `evidence_outcomes` table；它不新增或修改 `evidence_events`，不改推薦、Rule、
Paper、Formal、模型或券商狀態。每輪都先以 SQLite `mode=ro`／`PRAGMA query_only=ON`
確認 `evidence_events`、`evidence_outcomes` 與 `daily_prices` 存在，再保存
`OUTPUT_ROOT/scheduled/forward_outcomes/latest_status.json` 及不可覆寫的
`runs/<run_id>.json`。直接手動執行若未加 `--confirm` 只會產生 dry-run receipt；正式 DB
若未再加 `--allow-production-db-confirm` 會 fail closed。
Outcome 以 `(event_id, window_days, return_basis)` 為自然鍵；重跑只更新該鍵下的價格、
成熟度、品質與 warning，保留既有 `outcome_id`，使下游 Evidence 引用在重算後仍穩定。

常用命令：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_scheduled_forward_outcomes.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data\output `
  --db-path D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --event-type recommendation_included `
  --require-cohort-identity `
  --windows 5,10,20,60 --lookback-calendar-days 120 --max-events 2500
```

只有在受控排程或明確隔離 DB 寫入時才加 `--confirm`；若目標是
`TWStockConfig.db_file`，還要明確加 `--allow-production-db-confirm`。此入口的
`passed_with_warnings` 只表示 outcome 計算完成並揭露缺口，不能授予 V4 maturity、正式 alpha、
production scheduler 或 broker 權限。

### 9.9.1b Strict natural recommendation maturity（20 個官方交易 session）

strict natural lane 使用 `NaturalMaturitySessionResolver`，每筆 capture 固定解析 **20 個官方
交易 session**，不以 20 個股票 row、曆日差或 weekday 推算成熟。resolver proof 會保存
`resolver_id`／`resolver_version`、annual calendar evidence、TAIEX capture-day baseline、
exact endpoint observation、session dates、bounded SQLite source fingerprint 與
`source_database` anchor。個股 provider 只讀 capture day 與 exact endpoint day；中間個股缺列
不會滑到下一筆，缺 endpoint、缺任一官方 calendar／market proof、未收盤或 future row 時維持
`pending`。

producer 建立 strict evidence 時，caller 必須以同一個唯讀 market SQLite 建立 resolver 與
provider，並傳入帶時區的 `evaluation_at`。`evaluation_at` 轉成 `Asia/Taipei` 後必須等於
`evaluation_date`，不可是 future wall clock；resolver 的 horizon 固定為 `20`。producer 在
讀個股前後核對 proof 的 source DB path、size 與 mtime，receipt／authority 再以已驗證 capture
source contract 的 `source_database` 重驗；不能採用 receipt 自報 path、calendar hash 或
policy hash。舊 receipt 可作歷史診斷，但缺 strict resolver proof 不得進新 natural adoption。
每日入口 `run_daily_recommendation_learning.py` 同樣接受
`--calendar-cache-path`／`--temporary-closure-cache-path`，並沿用相同的
`NATURAL_MATURITY_CALENDAR_CACHE_PATH`、`ML_FORWARD_CALENDAR_CACHE_ROOT` 與
`NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH` resolution；每日 caller 以實際 checked clock
驗證 Taipei 日期，不以主機日期或歷史時間補造成熟度。

目前 generic forward CLI 仍保留原有研究契約：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_scheduled_forward_outcomes.py `
  --db-path <READONLY_OR_EXPLICIT_WORKING_COPY_DB> `
  --calendar-cache-path <OFFICIAL_ANNUAL_CACHE> `
  --temporary-closure-path <OPTIONAL_CLOSURE_CACHE> `
  --data-as-of-date YYYY-MM-DD --windows 5,10,20,60 `
  --require-cohort-identity
```

`--calendar-cache-path`／`--temporary-closure-path` 只提供 generic forward 的 bounded calendar
diagnostic；該 lane 仍保留 legacy symbol-price-row-offset／`return_basis` 語意，不能把結果折抵
strict natural maturity。

standalone strict natural CLI 會沿用同一組 resolver 與 checked clock：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_recommendation_natural_outcomes.py `
  --source-db <READONLY_SOURCE_DB> `
  --calendar-cache-path <OFFICIAL_ANNUAL_CACHE> `
  --temporary-closure-cache-path <OPTIONAL_CLOSURE_CACHE> `
  --capture <IMMUTABLE_CAPTURE_JSON> `
  --output <NATURAL_EVIDENCE_JSON>
```

`--calendar-cache-path` 省略時依序沿用
`NATURAL_MATURITY_CALENDAR_CACHE_PATH`、`ML_FORWARD_CALENDAR_CACHE_ROOT` 或 repo
default；`--temporary-closure-cache-path` 省略時依序沿用
`NATURAL_MATURITY_TEMPORARY_CLOSURE_PATH` 或維持 `None`，不把缺件當成通過。
CLI 將同一個 source DB 傳給 provider 與 resolver，並以實際 aware Taipei checked clock
推導未指定的 `--evaluation-date`。若明示歷史日期與 checked clock 的 Taipei 日期不一致，
service 會回傳 pending 的 clock mismatch，不補造 23:59 時間。命令成功啟動、`source_verified`
或 raw row 數量都不等於 natural credit。

2026-09-15、16、17 的三個 real-market captures 已於 2026-09-18 重驗並標示
`source_verified`；這只表示該次 source bytes／contract 可對帳，不代表 20-session matured
sample、personal delivery、human action 或 promotion。共用 annual cache refresh receipt 於
`2026-09-17T23:15:02.193862Z` 觀測為 `cache_valid_for_forward_horizon`，ML forward／Paper
與 strict natural 共用 `output\paper_execution_eod_replay\calendar_cache\`；目前有效期限為
`2026-09-21T23:15:03.532140Z`（台北時間 `2026-09-22 07:15`）。refresh 由既有共用路徑負責，
缺失或過期時 consumer 維持 pending／fail closed；日曆不具永久有效性。主機 Task Scheduler
的 Enabled／LastRun／NextRun 因權限不足不能由本輪操作宣稱。B 的 compact／ISO 日期 SQL
格式／長度限制、canonical bounded guard 與跨年等價 regression 已由核心合併 suite 驗證；不得
改用 ISO fixture 繞過 compact source 的驗證。annual-64 refresh discovery regression 另以
`12 passed`、compile／mypy clean 驗證，詳見 [Maturity calendar refresh wiring QA](../06_qa/MATURITY_CALENDAR_REFRESH_WIRING_2026_09_18.md)。

### 9.9.1c 個人推薦模型擷取與自然結果（2026-09-27）

**目前安全預設仍是 `rule_only`。** 個人來源/PIT admission 尚無獨立官方歷史可得時間證明；inventory 中兩個 `legacy_unproven` 候選仍不可啟用。使用者已明確選擇 V2 指定 SQLite 來源時間信任，操作方式與研究限定見 9.9.1d；此聲明不等同外部 authority 或官方 historical PIT 證明。不要回填舊候選 lineage 或改動 global active pointer。Outcome CLI 即使可執行，也不會自行准入模型或建立模型預測。

若未來已有明確准入、在當次保存結果中實際採 `personal_calibrated_probability` 的模型，操作順序如下：

1. 在「推薦分析」以明確政策完成推薦，按「保存結果」並等 canonical save/readback 成功。保存結果的 `result_id`、當次 policy snapshot 與 source/candidate identity 必須吻合；不可從同股、日期或 latest 推回缺失身份。
2. 僅由該次已保存結果建立並讀回 Stage A 個人 prediction capture；UI 使用本機 `OUTPUT_ROOT\personal_prediction` 作為 capture root，檔案位於其 `captures` 子目錄。Capture 封存當次輸出，不重新推論。若結果是 `rule_only`、舊結果缺 policy event、canonical readback 失敗，capture 不會建立；修復來源問題後再對同一明確結果重試，不要手造 capture/receipt。
3. 取得官方 annual trading calendar 與明確 market SQLite source 後，逐一指定需要評估的 capture，手動執行下列 Stage C CLI。所有路徑都要是使用者明確選定的絕對路徑；canonical recommendation root、capture root、market DB、calendar 與 isolated output 必須分開。`<...>` 是佔位符，不能原樣貼上；`evaluation-at` 必須換成真正執行時的 aware ISO 時間，不可用歷史時間回填。

```powershell
.\.venv\Scripts\python.exe scripts\run_personal_recommendation_outcomes.py `
  --canonical-recommendation-output-root "<CANONICAL_OUTPUT_ROOT>" `
  --capture-path "<PERSONAL_CAPTURE_ROOT>\captures\<EXPLICIT_CAPTURE_FILE>.json" `
  --personal-capture-root "<PERSONAL_CAPTURE_ROOT>" `
  --market-source-db "<READ_ONLY_MARKET_DB>" `
  --calendar-cache-path "<OFFICIAL_ANNUAL_CALENDAR_CACHE>" `
  --temporary-closure-cache-path "<OPTIONAL_OFFICIAL_CLOSURE_CACHE>" `
  --evaluation-at "<ACTUAL_AWARE_ISO_DATETIME_WITH_OFFSET>" `
  --isolated-output-root "<SEPARATE_PERSONAL_OUTPUT_ROOT>"
```

`--capture-path` 可重複，最多 500 個；每個都要是 `personal_capture_root\captures` 下明確指定的 JSON 檔。CLI 不掃描 latest、不接受 glob。若沒有可驗證的 temporary-closure cache，可省略該參數；輸出會保留 `annual_plan_only` 限制，不能把年曆計畫當臨時休市公告已核實。`--market-source-db` 必須是可唯讀使用且與輸出隔離的明確來源；正式 DB 的使用需要另行授權，本手冊範例不構成正式資料讀寫或 scheduler 執行授權。CLI 的所有輸出寫入 `--isolated-output-root\personal_natural_outcomes`，採 create-only；不要刪除既有 receipt 來重跑。

Stage C 先以 canonical query 嚴格讀回 capture 對應的已保存 recommendation，再用官方 session resolver 檢查完整 20 個交易 session。成熟 endpoint 的標籤明確為 `start_date=decision_date` 到 `end_date=verified endpoint` 的 close-to-close 事後結果，`is_execution_pnl=false`：它不是可成交價格、持倉損益或下單紀錄。Outcome v2 只以 `active_model` rows 計算模型預測／分數；`rule_only_fallback` rows 保留在 delivered cohort 與 coverage，但沒有模型機率，不可算作模型預測。after-cost 是依完整可得的估算手續費／稅費輸入計算的估算標籤，不是實際成交成本；若成本或流動性輸入缺失，after-cost 維持 pending／unknown，不以零成本補值。個人結果不建立 global natural evidence 或 promotion credit。

排錯時先看 CLI JSON 的 `status`、`capture_statuses`、`summary_path` 和各 outcome hash：

| 狀態／症狀 | 判讀與處理 |
|---|---|
| UI 顯示 `rule_only`／capture 按鈕不可用 | 本次結果沒有個人模型預測。當前來源准入未通過時是預期安全狀態；不要改指標、補 lineage 或重用 `legacy_unproven` artifact。 |
| `pending`／`completed_with_pending` | 20 個官方 session、endpoint close 或 outcome 必要來源證據尚未齊全。保留原 capture，待資料成熟後再以同一 explicit path 評估；不要以曆日或 weekday 補 session。若 gross 結果已成熟但估算成本／流動性輸入不足，則只把 outcome 內的 after-cost 欄位保留為 pending／unknown，不代表 gross maturity 也失敗。 |
| `unknown`／`completed_with_unknown`（CLI exit code 2） | 身份、來源、日期、calendar 或必要證據無法核對。讀完整 `message`／`capture_statuses`，修正確切輸入路徑或等待官方證據；不要改 capture/hash 使其通過。 |
| `error`（CLI exit code 2） | 參數、路徑、讀回或發布失敗。保存完整 stderr/stdout 與路徑，確認輸出未被改寫，再依 create-only 契約另行處理；不要刪檔或覆蓋舊 receipt。 |
| `completed`（CLI exit code 0） | 只表示本次明列 capture 的輸出已完成並返回 receipt。它不代表模型獲准、表現有效、自然 scheduler 完成、實際成交或 global learning/promotion。 |

較早 scoped QA 檢查點的 WP3／Stage B／C／Workbench／Update QA 數字各自只對當時範圍有效；最終 relevant route 另見交付 QA 文件。當時「尚未完成可見 native 操作」已由 2026-09-28 m10 Qt widget journey 更新，詳見 9.9.1d；m10 不是 OS desktop screenshot，也沒有完成 WP1 自然 scheduler、官方 PIT 或成熟績效。Stage C 測試、個人候選來源與個人政策不得折抵 global training、global evidence 或 promotion 條件。

### 9.9.1d 使用者明示來源時間信任的個人研究模式（V2，2026-09-27）

本節補充更新 9.9.1c 的來源信任說明：使用者已明確選擇可信任自己指定的 SQLite 資料庫，系統因此提供 V2 個人研究限定流程。這是「使用者聲明的來源時間信任」，不是官方歷史發布時間、獨立歷史 PIT 或資料來源簽章。安全預設仍是 `rule_only`。原有兩個 `legacy_unproven` 候選未補造 lineage；兩者雖曾通過安全 loader 載入檢查，仍缺訓練 lineage／來源時間契約，且績效未獨立驗證，不可因此啟用。2026-09-28 隔離後端已用新候選完成推薦、保存／讀回與 capture 驗收；候選只屬 user-declared research-only，不能稱為 official PIT 或 formal promotion candidate。當前個人設定最後已回到 `rule_only`。Qt widget 模型旅程已於 2026-09-28 m10 完成限定範圍驗收；不是 OS foreground／desktop screenshot。Stage C 對同次 capture 仍為 19 pending、0 matured，沒有成熟績效。

操作入口在「推薦分析」頁的「個人推薦模式」區塊：

1. 按「讀取候選清冊」，在已設定的 learning root 中選取 `rec-cal-3f8b2c276ef316e28de3806d`。UI 以 `RECOMMENDATION_LEARNING_OUTPUT_ROOT` 指定 learning 輸出根目錄；該環境變數須是絕對路徑，並指向**包含 `recommendation_learning` 子目錄的 output root**，不是該子目錄本身。未設定時，resolver 依 `DATA_ROOT` 使用同層的預設 `FA_Data_Shadow`。清冊只列可檢查的候選；缺少完整 lineage／來源證據的 `legacy_unproven` 項目不能藉由手動挑選或重雜湊升格。隔離 QA 候選只會出現在該 QA run 明確指定的 learning root；一般 UI 預設 root 沒有列出它時，先核對啟動設定，不要複製候選或改寫 pointer。
2. 在「個人研究來源 SQLite（明確選擇）」輸入目前隔離 run 的 SQLite 絕對路徑，或按「選擇 DB…」。V2 來源綁定要與推薦服務本次實際使用的工作資料庫相同，並核對路徑、檔案身分及訓練切片；使用隔離 QA working copy 時，要綁該 working copy，而不是其父來源或其他 snapshot。正式 `D:` 只可作為建立隔離來源的唯讀原始來源，不要讓 UI 或本功能寫入正式庫。畫面不會從 `DATA_ROOT` 推定來源或代表使用者同意。按「檢查指定來源與候選」只執行唯讀來源檢查與有界 replay，不會寫入來源 SQLite 或保存信任。
3. 檢查預覽所列資料庫絕對路徑、檔案身分、來源切片 SHA-256、資料集、決策日期、股票、樣本數與候選完整 pins。資料庫大小只供診斷；不能用它代替來源身分或切片驗證。來源切片綁定模型實際訓練窗內的資料列、可讀的 `available_at`、可重建的來源契約及成本等訓練輸入。本次僅在 `coverage.source_contract.technical`、`source_disclosures.source_contract.technical`、`source_disclosures.technical.source_contract` 三處 technical contract 投影中排除 `content_digest`、`content_row_count`、`coverage_end`、`evidence_hash` 四個全庫彙總欄；另不把 replay 結果最外層的 `dataset_id`、`dataset_hash`、`source_fingerprint` 三個由全庫 source fingerprints 衍生的識別欄納入此來源切片比對。上述例外以外，其他來源與欄位仍依原契約比較；候選已保存 manifest/pins 與逐筆樣本仍獨立核對。這不改原 replay manifest 或 global oracle。若 technical publication 或 corporate-action adjustment contract 缺失／未驗證，gate evidence 仍是 `unknown`／`false`；使用者信任指定資料庫不會把它升格為官方 PIT。來源日期只接受 `YYYY-MM-DD` 或 `YYYYMMDD`；完整 ISO 日期時間必須帶時區，並先換算為台北日期，再與決策日作日粒度比較。缺時區的 naive 日期時間及其他延伸日期格式會拒絕候選。此日期粒度不證明同日盤中可得時間；無效或晚於決策日的 `available_at` 會拒絕候選。若已知非單位公司行動落在 label window，候選也會被拒絕。`available_at` 不會改稱官方發布時間。
4. 確認候選與指定資料庫確實是你要採信的來源後，選擇「個人校準機率（需選擇已驗證候選）」，勾選「我明確信任以上指定 SQLite 的資料時間來源，僅供個人研究，不代表官方歷史 PIT。」再按確認按鈕。按鈕會依所選模式顯示「信任此來源並保存個人研究模式」或規則模式的相應文字。V2 設定會用 CAS 保存並讀回 revision/hash；接著系統以同一明示資料庫重新檢查。只有重新檢查成功後，當前畫面才可在呼叫時要求 personal calibrated mode；consumer 仍會在載入模型前獨立重驗來源與候選。
5. 按「執行推薦分析」完成分析，先確認本次實際模式；接著按「保存結果」，等 canonical save/readback 成功後，再檢查逐列機率與狀態。保存前的結果表尚未接上已驗證 read model 的逐列 projection，不能據此判斷模型是否提供機率。每次模型執行都必須對本次 MainWindow 實際使用的 working DB 重新核對來源路徑、檔案身分與來源切片；明示的來源 SQLite 必須與此畫面及 `RecommendationService` 實際使用的資料庫相同，路徑或檔案身分不同時不會啟動個人模型推薦；無法證明同源的自訂行情／歷史特徵 provider 也會 fail closed。舊政策或前一階段的 source proof 不能代替本次重驗。只有保存讀回核對同一 `result_id`、政策快照、模型 receipt 與投影後，結果表才會顯示已驗證的模型欄位。主要欄位是 `calibrated_probability_bp`、`calibrated_probability_status`、`after_cost_profit_probability_bp`、`after_cost_profit_probability_status`、`calibration_model_version`、`calibration_horizon`、`calibration_source` 與 `calibration_warnings`。`_bp` 以 10,000 = 100% 表示；例如 6,000 bp = 60%。模型只提供校準機率與來源證據，不改規則 `rule_score`、入選股票、top-N 或原推薦排序。只有實際模式為 `personal_calibrated_probability` 且列狀態有效、機率值有來源時，才能說模型影響了該列的機率呈現；`unavailable`、`unknown`、fallback 或空值不是 0，也不能當成模型已影響該股票。canonical 保存讀回通過後，系統會依當次模式建立個人模型 capture 並讀回驗證；若需重試，只對目前已驗證的同一結果按「建立／重試個人模型擷取」，不會重跑推薦或重新推論。capture 失敗不會倒置已保存結果。
6. 關閉並重開程式後，已保存路徑可顯示作為提示，但不代表本次啟動已重新驗證。先核對 UI 實際 `TWStockConfig.db_file`，再按「檢查指定來源與候選」取得綁定該 working DB 的新預覽；保存政策後、開始下一次模型呼叫前仍須確認路徑、檔案身分及來源切片與本次 runtime 一致。若初始化或其他階段改變 working DB，原預覽即不得沿用，需重做來源檢查；若預設以外的自訂行情來源或未識別模型特徵 provider 無法證明使用同一 DB，個人模型模式也會拒絕啟動。任何核對不一致時，系統 fail closed 並保留 `rule_only`。
7. 要停用個人校準時，選擇「規則排序（個人紀錄）」。原本啟用校準時，確認按鈕會顯示「停用校準並保存規則模式」；按下後 V2 會建立新 CAS revision 並清除候選與來源信任。若原本已是規則模式，按鈕文案為「確認並保存規則模式」。此操作只影響本機個人政策，不改全域 active pointer、training、promotion、learning credit 或自動下單。
8. 回退 V2 的校準設定時，按「讀取歷史版本」並選擇要回復的已保存版本。若所選版本是 V2 個人校準，確認（必要時重新選取）其候選、輸入同一來源 SQLite 並按「檢查指定來源與候選」；只有新鮮 proposal 與封存 trust 完全相符時，才可按「回退到所選版本」並在確認視窗同意。回退會建立新 revision，不回寫歷史政策或推薦結果；儲存的舊 trust 本身不是目前來源仍可信的證明。V1 設定仍可讀取，但 V1 calibrated policy 不會因此取得 V2 來源信任。

若更新的是隔離 snapshot，V2 來源驗證不會只因一般資料庫彙總值變化便自動失效：訓練窗以外的更新只有在同一檔案身分仍成立、且實際訓練切片（含資料列、可讀時間欄、來源契約及成本）完全相同時，才不改變該切片比對結果。缺少獨立 publication／adjustment 證據時，狀態仍為未知，不會以使用者聲明補成官方時間證明；訓練窗內可見的未來 `available_at` 或已知非單位公司行動仍會阻擋。若檔案被替換，或訓練切片內資料／時間／來源契約／成本改變，驗證會拒絕；請由已確認的正式唯讀來源另建穩定 snapshot，再重新驗證候選並明確確認。不得自行改 manifest、hash、時間或政策 JSON 讓檢查通過。即使符合使用者的來源聲明，仍只屬研究限定，並非官方 historical PIT。

| 狀態／症狀 | 判讀與處理 |
|---|---|
| 候選清冊沒有列出 `rec-cal-3f8b2c276ef316e28de3806d`，或只列 `legacy_unproven` | 核對隔離 run 的 learning root 是否正確；不要複製／修改候選或 lineage。舊 `legacy_unproven` 候選仍因缺訓練 lineage／來源時間契約而不可啟用，維持 `rule_only`。 |
| 來源檢查按鈕／信任勾選框不可用 | 尚未明確選取候選與絕對 SQLite 路徑，或預覽已因路徑／候選改變而清除；重新選擇並檢查。 |
| 顯示 V1 或未重新驗證的 V2 | 舊設定可讀，但不代表目前來源有效；同一候選與資料庫需重新檢查，並在需要時明確保存 V2。 |
| CAS revision/hash 衝突或保存後讀回失敗 | 不要覆寫政策檔；重新載入目前設定、核對來源及候選後再操作。保存若已完成但畫面未確認，先讀回設定，不要猜測結果。 |
| `source_time_binding_mismatch`、來源切片 SHA 或候選 pins 不符 | 檔案身分或實際訓練切片有差異；停止個人校準。回到原唯讀訓練來源，或依法重新產生候選，再做新的來源檢查與明示確認。 |
| 顯示 `official_historical_pit_verified=false` | 這是預期狀態，表示使用者聲明不等於獨立官方 PIT；不得據此作 global promotion 或正式績效宣稱。 |

受限的可見 Windows 原生操作曾驗證規則模式的推薦、保存／重新開啟讀回與個人選擇；它沒有驗證 V2 個人模型操作。後續隔離後端 E2E 使用候選 `rec-cal-3f8b2c276ef316e28de3806d` 和使用者指定正式資料建立的唯讀 QA snapshot：V2 revision 1 完成 fresh source recheck、consumer load、`RecommendationService` 真實呼叫、canonical result save/readback 與 capture v3 readback。結果 `pc-real-2026-09-28-1790588347` 的規則排序為 2454、2408、3037，三列 calibrated probability 均為 6000 bp；模型沒有重排推薦。After-cost probability 為 unavailable/null，不代表 0。該候選 16 筆 holdout Brier 2730 bp，較 50% null benchmark 的 2500 bp 差 230 bp；此效果訊號需揭露，但個人使用不因低績效自動封鎖。來源信任仍標 `research_only=true`、`official_historical_pit_verified=false`，未取得正式 promotion eligibility。

此隔離候選使用 8 檔（2308、2317、2327、2330、2344、2408、2454、3037），history start 2024-10-24、replay end 2026-06-26；512 筆 replay samples 中採用 64 個決策日（2025-11-28 至 2026-05-28），label horizon 為 20 sessions。特徵只取決策前可得的前一交易日資料；來源 `available_at` 的訓練檢查是日粒度 user-declared 信任，不代表同日盤中可得或 official publication。候選以 50 bp fixed round-trip cost scenario訓練，`training_as_of=2026-05-25`、`training_cutoff=2026-06-26`；共 336 筆 cutoff-eligible rows，其中 OOF 校準 176 筆、未碰測試 holdout 16 筆，其餘屬訓練折。完整候選 root 與 candidate／freeze／manifest／artifact／dataset pins 見[隔離 E2E 收據](../../output/qa/pc-e2e-v1/backend_e2e_acceptance_20260928.json)。

較早 backend-only capture 的 3 列均 pending、成熟 0 列；其 resolver 指出缺 `2026-09-28` 的 TAIEX baseline observation，沒有建立 outcome、global natural evidence 或 promotion credit。這不是後續 m10 capture 的列數或狀態。m10 對其獨立 capture 的最新 Stage C 結果見下文：19 pending、0 matured。Annual calendar cache 的臨時休市 coverage 為 `not_covered`。較早個人政策曾依序啟用、停用為 rule-only、經新鮮 source recheck 回退候選，再以新 revision 設為最終 rule-only；global active pointer 未變。完整後端收據及各階段 hash 見[個人模型隔離後端 E2E 收據](../../output/qa/pc-e2e-v1/backend_e2e_acceptance_20260928.json)（SHA-256 `5da799f8994eed9623c28e938593b4075256c83e9505408469d3118b585ee080`），結果成熟度診斷見 `resolver_diagnostic_receipt.json`。

2026-09-28 m10 已通過隔離 Qt widget journey：V2 candidate recheck、模型推薦、canonical result save/readback、capture v3 readback、cold restart、停用、fresh proposal revision rollback、final rule-only。精確 pins 見 [m10 驗收報告](../06_qa/PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md)。畫面證據是 `QWidget.grab()` widget render，不是 OS foreground／desktop screenshot。預設仍為 `rule_only`；user-declared source time 只限個人研究，不是官方 historical PIT。Stage C 對 m10 capture 為 `completed_with_pending`、19 pending／0 matured、reason `personal_outcome_source_or_cost_incomplete`，outcome artifact null、published 0、global／promotion false。逐筆 CLI 仍依 9.9.1c 的 explicit capture path 與 `evaluation-at` 使用；它不會提前成熟 outcome 或替代官方來源／日曆檢查。

正式資料根目錄預設為 `D:\Min\Python\Project\FA_Data`（可由 `DATA_ROOT` 覆寫），正式 SQLite 為 `D:\Min\Python\Project\FA_Data\sqlite\twstock.db`。該正式庫只可依授權作建立 snapshot 的唯讀來源；m10 UI 程序沒有開啟正式庫。實際 runtime/source trust 綁定的是隔離工作副本 `m10\data\_test\sqlite\twstock.db`，不是父 snapshot，也不是正式庫。

若要親自操作畫面，先依下方自動旅程範例設定路徑並完成 `prepare`（只執行到準備隔離 run 為止），再以該全新 `$run`、`$learning`、`$policy` 啟動 MainWindow：

```powershell
.\.venv\Scripts\python.exe scripts\qa_personal_research_ui.py launch `
  --run-root $run `
  --learning-output-root $learning `
  --policy-config-path $policy
```

在「推薦分析」頁讀取候選清冊，選取指定候選；輸入同一 run 的 runtime SQLite 後按「檢查指定來源與候選」，核對路徑、檔案身分、slice SHA 與研究限定，再明確勾選來源信任並保存 V2。執行推薦後按「保存結果」，確認 canonical readback 後檢視逐列機率，再建立／讀回 capture。要停用時保存 `rule_only`；要回退時讀取歷史版本、重新取得與封存 trust 相符的 fresh source proposal，再確認回退，最後再保存 `rule_only`。若要以已審查的自動 Qt widget 控制重現整段流程，才使用下方 `preflight`／`accept` 命令；它不是人手操作或 OS-level 桌面證據。m10 的已完成收據供查核，不要重用 m10 root；自行操作必須重新 `prepare` 全新隔離 root。

隔離 journey 的實際命令（每次使用全新且不存在的 run ID；不得重用完成、失敗或中斷的 root）：

```powershell
$repo = 'C:\Projects\PythonProjects\technical_analysis'
$runId = 'native_qt_wp4_model_<unique>'
$run = Join-Path $repo "output\qa\personal_daily_product_20261006\personal_research_ui\$runId"
$snapshot = Join-Path $repo 'output\qa\personal_daily_product_20261006\real_source_validation_runs\formal_source_snapshot_v2\twstock.db'
$snapshotReceipt = Join-Path (Split-Path $snapshot) 'snapshot_receipt.json'
$learning = Join-Path $repo 'output\qa\pc-fit-v7'
$policy = Join-Path $run 'app_config\personal_use_policy.json'
.\.venv\Scripts\python.exe scripts\qa_personal_research_ui.py prepare `
  --run-root $run `
  --source-snapshot $snapshot `
  --snapshot-receipt $snapshotReceipt `
  --learning-output-root $learning `
  --policy-config-path $policy
.\.venv\Scripts\python.exe scripts\qa_native_personal_model_acceptance.py preflight --run-id $runId
.\.venv\Scripts\python.exe scripts\qa_native_personal_model_acceptance.py accept --run-id $runId --confirm-qt-model-run
```

成功旅程會在「推薦分析」內逐步檢查明示 DB source、V2 trust、推薦、保存讀回、capture、冷啟、停用與 rollback；每一個 source proof 以該 run 真正的 `TWStockConfig.db_file` 為準。準備器複製已 pin 的 QA snapshot，learning root `output/qa/pc-fit-v7` 保持唯讀。若任何 phase 失敗或逾時，保留原 receipt 與 run tree、停止後續動作並改用新 run ID；不得清理或覆寫失敗 root。

### 9.9.1g 個人 H20 原模型準備與 policy 路徑（2026-10-06）

目前原 trainer 已有20交易日 absolute/no-cost 毛報酬 head，不需先新增 trainer。使用者已准有限上軌比較與 H20 gross、希望每天保存真模型預測；自然績效未成熟要顯示狀態，不作無限等待的個人使用 gate。正式交易與 PIT 資格仍須獨立證據。

啟動 UI 前可在 config.personal_model_policy_path 或環境 `PERSONAL_MODEL_POLICY_PATH` 設**絕對 policy 檔路徑**；MainWindow explicit policy_config_path 優先，其次 config，最後原 AppConfigLocation 預設。設定路徑不自建檔案或啟用候選。操作仍在推薦頁原個人模型選擇／來源信任／保存流程；relative path 會在資料 I/O 前拒絕，應改為私人目錄的絕對檔名。不要放進 market DB 或 FA_Data。

維運者可先執行 `scripts/qa_prepare_personal_h20_gross_contract.py --fit-receipt <原fit收據絕對路徑> --fit-receipt-sha256 <獨立核准rawSHA>`。結果列出原 lineage／artifact／runtime／schema pins、holdout 評估與 blockers；不 fit、deserialize、保存 policy 或改 Task。candidate 自述 verified 不足以替代原可信 fit 收據。

需要重新產候選時先看 `scripts/scheduled/rebuild_personal_calibration_candidate.py --help`；來源 DB、data root、新 output、shared heavy-chain lock、symbols、history/replay期間、training cutoff、decision date、max dates、cost bp 與 scope 均須明示。預設 preview 只讀；0樣本／來源拒絕表示缺件，不能補成0預測或刪 revision marker。execute 不屬 preview，本次未執行；原 capacity 與 shared lock 仍保留，output 必須全新且與來源／App 分離。

已核可信原候選 `rec-cal-3f8b2c276ef316e28de3806d`，真 artifact 對9月28日原保存請求重播三筆 H20 為1613／1963／1086bp，等於原保存值；holdout Brier2730比null2500差230bp，after-cost仍缺件。重播不算今日新自然預測。目前來源提案對原 frozen snapshot 可用，對 live DB 仍 training_source_time_training_rows_unbound；正式來源 revision guard 也阻擋 historical PIT replay。每日 current-restated 來源與 A03 CLI composition 尚在整合，不要使用9月24日 frozen snapshot冒稱最新行情。回退沿原 rule-only／policy CAS，不刪預測或來源收據。完整證據：[中央整合 QA](../06_qa/BALDR_PERSONAL_MODEL_ACTIVATION_INTEGRATION_20261006.md)。

### 9.9.1e 已保存推薦的個人決定與旅程回看（2026-09-28）

這段流程記錄使用者對已保存推薦的個人選擇，並在個股研究的「決策 → 結果」頁回看同一結果的 Journal 歷史。它不重跑推薦、不改寫推薦排序、不建立成交或持倉，也不代表模型成效。

1. 在「推薦分析」完成分析並按「保存結果」，等 canonical save/readback 成功後，選取一檔推薦股票。尚未保存、沒有選取股票或保存身份無法核驗時，個人決定按鈕會停用。
2. 在結果區下方「個人決定（研究紀錄，不下單）」按「個人採用」或「個人拒絕」；按「推翻並記原因」時，輸入非空的具體理由後才會保存。每次操作都會沿用同一份已保存 `result_id`、股票與來源 snapshot，由既有 typed Journal writer 保存並立即重新讀回核對。
3. 如需回看，保持選取同一列並按「查看個股研究」，在個股研究中的「決策 → 結果」查看「此推薦結果的個人決定歷史」。Journey 是唯讀表格，依記錄時間顯示各筆 adopt／reject／override 與推翻理由；每筆都是 append-only 歷史，先前紀錄會保留，不代表多筆決定同時有效。
4. Journal 歷史只在推薦結果、股票、決策日、來源 snapshot 與保存 artifact 身分都吻合時顯示。不同結果、快照、artifact 或衝突列不會以同股票／日期猜測補接；身份缺件或衝突時顯示未連結／衝突或停用操作。Journal 歷史不會遮住 Evidence／Outcome 的 pending、unknown 或尚待成熟狀態。

這是隔離 Qt MainWindow journey 的 bounded 功能增量；其 UI 測試使用明確標記的 synthetic producer fixture，再由真 RecommendationView 與 Journal writer 保存／讀回，不代表自然行情、自然 outcome 或 OS 前景操作。測試收據與未解跨頁回歸見[WP3 Journey choice QA](../06_qa/WP3_WATCHLIST_QA_20260928.md#2026-09-28-recommendationjournal-choice-follow-up)。

### 9.9.1f 個人模型評估摘要讀回（唯讀）

「推薦分析」的「個人模型評估」區只讀取已保存並核驗的單筆推薦、其 personal capture 與一份由你明確選取的 Stage C 日摘要。它不執行評估、不寫入摘要，也沒有自動選取最新檔案的索引。

1. 先在「推薦分析」輸入完整 `result_id` 並按「讀取已保存結果」，或保存目前推薦；確認結果已載入並通過 canonical readback。沒有可核驗結果時，個人模型評估不能開始。
2. 在「個人模型評估（唯讀）」分別按「選擇 capture…」及「選擇 Stage C summary…」，明確挑選與目前保存結果相同的 capture JSON 與日摘要 JSON。檔案路徑會留在畫面上供核對；重新開啟程式後須再次載入 exact result 並重新選擇兩個檔案。未選摘要時畫面顯示「尚未執行評估」，這代表本頁尚未讀取，不代表系統已查明其他位置沒有摘要。
3. 按「讀取指定評估」。系統唯讀核對結果 ID、canonical payload/raw artifact、V2 個人政策、capture、Stage C 日摘要的 payload hash、來源根目錄與唯一對應 capture 列。若任一身份或來源不符，畫面會拒絕顯示並清空舊明細；不同結果、不同 capture 或另一個摘要不會按股票、日期或檔名猜測替代。
4. 狀態列顯示選定摘要內的已成熟與待觀察數；詳細區列出結果／capture／摘要身份、評估範圍、metrics、成本後狀態、缺件與下一步。`unknown` 表示證據或來源未能核實；未成熟指標維持不可得，不以零補值。即使有成熟單筆，本版仍不足以判斷模型效果或建議採用／停用。

成熟 outcome 的價格讀回目前要求穩定、已 checkpoint、沒有 `-wal`／`-shm` sidecar 的隔離 SQLite 副本。正式資料庫若仍有 WAL/SHM，請勿為了讓評估通過而手動 checkpoint 或改寫正式資料；請依核准的 SQLite backup 流程建立隔離副本，確認副本在評估期間不會被替換或寫入，再於來源選擇器明確指定。若來源帶 sidecar 或在讀取期間變動，系統會拒絕成熟讀回；這是來源無法安全重驗，不代表模型無效。m11 的 19 筆 pending 是該次 Stage C summary 記錄的來源／成本證據不完整，並非因 WAL/SHM 被拒。

此評估只限個人研究來源，非官方歷史 PIT 可得時間證明；其 20 個交易日標籤是決策日到後續收盤的 close-to-close 觀察，不是成交損益、模擬成交或持倉報酬。固定 50% null baseline 只作明示比較基準，不把 `rule_score` 當機率。畫面不寫 Journal／Outcome、不回補歷史、不切換模型。更換結果、重跑推薦或更換任一來源檔時，先前的評估明細會清除；來源錯誤時請重新確認精確保存結果、capture 根目錄及 Stage C summary，而不要改名、重算或複製原摘要。實來源與 isolated UI 邊界的測試證據見[WP3 Journey choice 與 Stage C UI QA](../06_qa/WP3_WATCHLIST_QA_20260928.md#2026-09-28-個人模型評估-ui-follow-up)。

### 9.9.2 Historical Evidence Replay（歷史排程重放）

Historical Evidence Replay 用來把 Evidence Pipeline 放到半年前或指定歷史期間逐交易日重放。它會先把 source SQLite DB 複製成 replay DB，再每天只使用當日可見的資料跑 source coverage、snapshot capture、recommendation evidence capture 與 forward outcome maturity。這是 `historical_replay` / `simulated_scheduler`，不是既有 Windows Task Scheduler，也不會取代每天 05:15 的 scheduled dry-run report。

常用命令：

```powershell
.\.venv\Scripts\python.exe scripts\replay_historical_evidence_pipeline.py --start-date 2026-01-06 --end-date 2026-07-06 --source-db-path <source-db> --replay-db-path tmp\historical_replay\evidence_replay_2026h1.db --json-output --report-output output\evidence_pipeline\historical_replay_2026h1.md
.\.venv\Scripts\python.exe scripts\replay_historical_evidence_pipeline.py --start-date 2026-01-06 --end-date 2026-07-06 --source-db-path <source-db> --replay-db-path tmp\historical_replay\evidence_replay_2026h1.db --confirm --overwrite-replay-db --sources all --windows 5,10,20,60 --outcome-mode final --json-output
```

主要參數：

- `--start-date` / `--end-date`：要重放的歷史日期區間；實際執行日會從 source DB 的 `daily_prices` 交易日中挑出。
- `--source-db-path`：原始 SQLite DB，只用來複製與查交易日；不可與 replay DB 同一路徑。
- `--replay-db-path`：重放用 working-copy DB。若不存在會由 source DB 複製；若已存在，只有加 `--overwrite-replay-db` 才會重建。
- `--confirm`：預設不寫 business rows；加上後才會對 replay DB 寫入 evidence events / outcomes。正式 evidence DB 不應拿來當 replay DB。
- `--outcome-mode final|daily`：預設 `final`，逐日 capture 完成後只在 replay end date 做一次 forward outcome 計算，適合半年 replay；`daily` 會每天用當日 `data_as_of_date` 重新計算 outcome maturity，語意更細但大型 DB 會明顯變慢。
- `--sources`、`--windows`、`--group-by`、`--window`、`--min-sample-size`、`--limit`：沿用 Evidence Pipeline Runner / forward summary 的控制語意。
- `--report-output`：輸出 Markdown replay report；JSON summary 會固定印到 stdout。

No-look-ahead 邊界：

- Recommendation 類來源只會選 `created_at` 日期不晚於當日 decision date 的 persisted result；若沒有當日以前 result，會記錄 `recommendation_asof_result_missing`，並略過 `recommendation` / `why-not` / `liquidity-gate` 類來源，不用未來 result 補值。
- Event metadata 會帶入 `replay_mode=historical_replay`、`source_label=simulated_scheduler`、`replay_run_id`、`replay_decision_date` 與 `replay_data_as_of_date`，方便和真實 scheduled dry-run 分開查。
- Forward outcome 計算會以 `data_as_of_date` 限制價格可見日；`final` 模式以 replay 最後一個交易日作上限，`daily` 模式以每日 replay date 作上限。在可見日尚未成熟的 5 / 10 / 20 / 60 日 window 仍會維持 pending，不會提前看未來價格。Pending outcome 會依交易日序列揭露 `expected_maturity_date` 與剩餘交易日；日曆資料不足時顯示 `waiting_for_calendar`，不得用 calendar days 補算。
- Replay report 只能用來看 source gap、payload gap、decision workflow 與 V2.0 Workbench 設計方向；不計入 formal/canonical credit，也不能把歷史 working-copy `1/3`、UI projection `3/3`、sidecar pending `10` 或 multi-day `3/3` 互相替代。它不構成具名 review、manual approval、production scheduler gate 或投資有效性證明。

結果判讀：

- 2026-07-06 reference return fix 後，若 event 沒有 `benchmark_id`，forward outcome 會以 `TAIEX` 作為市場 benchmark default；`market_indices` 可使用未命名市場序列，並在 `收盤指數` 缺值時 fallback 到 `收盤價`。
- Industry return / excess 不會推估未知產業；只有 event 有 `industry_benchmark_id` 或 `sector` 且可保守映射到 `industry_indices` 時才會填入。缺值會保留 `NULL` 與 `missing_industry_benchmark` warning，不會填 0。
- `_reference_fix` replay 產物中，ready benchmark return / excess 已可用；industry 大量 `DEGRADED` 代表舊 recommendation payload 缺 sector / industry，不代表 raw forward return 或 benchmark excess 壞掉。cleanup 後保留位置為 `D:/Min/Python/Project/FA_Data/output/evidence_pipeline/historical_replay_reference_fix_20260706/`；Workbench CLI 只應讀其中 JSON summary。
- `source_missing_screening_matrix` 代表舊 recommendation result 沒有當時的 screening matrix payload；系統不回補、不重算舊結果。

### 9.9.3 Simulated Phase Progress 與 Phase 5 Approval Rehearsal

V2.2 後，可用 `scripts\inspect_simulated_phase_progress.py` 將 Historical Evidence Replay summary、scheduled dry-run latest status 與 Pre-V2 readiness 串成 simulated Phase 0-5 判讀。這個 CLI 只讀既有 JSON / Markdown / DB，不執行 replay、不啟用 scheduler、不寫 evidence DB，也不會把 replay 補成 official gate。它與 Workbench 共用 `WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH`；如需明確指定 owner-approved projection，可加上 `--approved-weekly-history-projection <path>`，只會影響 UI／readiness 揭露，不授予 formal credit。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_simulated_phase_progress.py --db-path <working-copy-db> --replay-summary-path D:\Min\Python\Project\FA_Data\output\evidence_pipeline\historical_replay_reference_fix_20260706\historical_replay_2026-01-06_2026-07-06_reference_fix.json --scheduled-output-root D:\Min\Python\Project\FA_Data\output\scheduled\evidence_pipeline_dry_run --decision-date <YYYY-MM-DD> --json-output
.\.venv\Scripts\python.exe scripts\inspect_simulated_phase_progress.py --db-path <working-copy-db> --replay-summary-path <replay-summary.json> --approved-weekly-history-projection <projection.json> --json-output
.\.venv\Scripts\python.exe scripts\inspect_simulated_phase_progress.py --db-path <working-copy-db> --replay-summary-path D:\Min\Python\Project\FA_Data\output\evidence_pipeline\historical_replay_reference_fix_20260706\historical_replay_2026-01-06_2026-07-06_reference_fix.json --scheduled-output-root D:\Min\Python\Project\FA_Data\output\scheduled\evidence_pipeline_dry_run --decision-date <YYYY-MM-DD> --markdown --report-output output\qa\simulated_phase_progress.md
```

輸出判讀：

- `simulated_overall_status=simulated_ready` 只代表 approval rehearsal 可演練，不代表 official gate 完成。
- replay-derived evidence 必須保留 `replay_mode=historical_replay`、`source_label=simulated_scheduler`、`official_gate_credit=false`、`requires_real_world_validation=true`。
- scheduled dry-run latest status 若為 `dry_run=true`、`confirm=false`、`writes_evidence_db=false`，只代表看見 raw output；`manual_record_credit=false` 時不可計入 multi-day record。
- `official_phase_5_status=blocked` 與 `production_scheduler_allowed=false` 必須保留，直到正式 Phase 0 / approval gates 通過。

不得標示為已完成、必須等待正式資料的項目：

| 項目 | 完成前必須等到 |
|---|---|
| weekly history | 3 筆不同週期、人工確認後保存的 weekly evidence operations history。 |
| multi-day dry-run | 3 個真實交易日的 freshness、scheduled dry-run、working-copy confirm smoke、dashboard review 與 manual notes。 |
| manual review note rhythm | 真實操作日可比較的人工覆盤 notes。 |
| action item rhythm | 真實 review / dismissed / follow-up 節奏；目前 Action Items 只是 read-only queue。 |
| Phase 3 source acceptance | 每個 candidate source 的 available-date / quality / missing policy 與 dry-run diagnostics。 |
| Phase 4 execution realism acceptance | spread、odd-lot、locked limit、gap execution、unfilled reason 等 research-only sandbox 驗證。 |
| Phase 5 scheduler approval | backup / rollback / recovery evidence、source gaps acceptance、working-copy idempotency 與 explicit manual approval。 |

`docs/06_qa/V2_2_PHASE5_APPROVAL_REHEARSAL_PACKAGE_2026_07_07.md` 是目前的審核包預演文件；它可用來準備審核材料，但不改 lifecycle、不開 scheduler、不代表 production readiness。

Phase 3C 後，可用 `scripts\inspect_source_candidate_readiness.py` 做三大法人、信用交易與 TDCC / 集保庫存 source candidate dry-run。此 CLI 只檢查 candidate readiness / coverage / diagnostics，不正式接入策略訊號，不寫 production DB，不提供 `--confirm`，不啟用 scheduler，不改 `ScoringEngine`、推薦分數、threshold、profile 權重、portfolio 或 lifecycle。

Phase 3C adapter 的 provider-facing source identity（`twse_institutional`、`twse_credit`、`tdcc_shareholding`）與 Gate 3 canonical contract 的對應，固定由 `data_module.p0_source_contract_registry.map_candidate_source_id()` 的 `p0-candidate-source-alignment.v1` 明確映射：分別對應 `institutional_flows`、`credit_transactions`、`tdcc_shareholding`。這只是 identity／traceability 對齊，不會自動接受來源，也不會授予 `downstream_eligibility`。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_source_candidate_readiness.py --sample --format json
.\.venv\Scripts\python.exe scripts\inspect_source_candidate_readiness.py --sample --format markdown
.\.venv\Scripts\python.exe scripts\inspect_source_candidate_readiness.py --db-path <working-copy-db> --decision-date <YYYY-MM-DD> --format json
```

輸出判讀：

- `institutional_flows` 檢查外資、投信、自營商的 buy / sell / net buy-sell 欄位與 source quality / available_date / decision_date 邊界。
- `credit_transactions` 檢查融資買進、融資餘額、融券賣出、融券餘額；`financing`、`securities_lending` 只有資料存在才列入，缺欄位只回 `missing_optional_source`，不補值。
- `tdcc_shareholding` 檢查股權分散、持股級距、大戶比例、散戶比例等候選 payload；週資料或公告延遲資料必須保留 explicit `available_date`，缺 available date 不得進 decision-time feature。
- 缺 DB、缺 table 或尚未 ingestion 時會輸出 `source_not_ingested` / `missing_db` / `missing_table`，不建立 DB 或 table。
- table 存在但缺 `available_date` 時會輸出 `missing_available_date`，且 `decision_ready=false`。
- `available_date > decision_date` 會輸出 `future_data_blocked`，不得被使用。
- `access_boundary` 必須保留 `writes_allowed=false`、`production_scheduler_allowed=false`、`scoring_engine_write_allowed=false`、`investment_effectiveness_claim=false`。

### V2.3 P0 資料來源人工接受台帳

`docs\06_qa\V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md` 是 Gate 3 / V2.3 的逐來源人工決策台帳。它完整涵蓋除權息 / 除權、未登錄的減資 / 分割 / 面額變更、停牌 / 復牌、處置、分盤、全額交割、漲跌停鎖死、三大法人、信用交易、TDCC / 集保持股分散與 PIT fundamentals；它不是資料抓取命令，也不會改變 CLI、UI、DB 或資料來源設定。

操作與結果判讀：

1. 先以本節的 candidate readiness CLI 保留來源 diagnostics、`available_date` 與 quality 證據；候選資料只可用於審核，不能直接接入策略訊號。
2. 再由具名人工決策人逐列審核 source version、`as_of_date`、授權 / 使用範圍、rate limit、freshness / coverage、PIT 語意、missing / outage、quarantine、retry 與 evidence / review / rollback pointer。
3. 未填完人工作業前，台帳的 `human decision` 必須維持 `requires_human_acceptance`，`owner` 與 `date` 必須分離保持未填，`downstream eligibility` 必須維持 `none`。
4. `decision_ready_candidate` 只代表該筆候選資料未觸發 available-date / required-field blocking diagnostic；它不是 `accepted`，不得讓資料進入 `ScoringEngine`、Advice、Portfolio、lifecycle 或 production scheduler。
5. 資料缺失、outage、stale、缺 `available_date` 或 `available_date > decision_date` 時，維持 fail-closed 或明示 degraded / warning；不得補值或當作 observed。除權息 / 除權 capability 不能延伸主張為減資 / 分割 / 面額變更；後三者及停牌 / 復牌均須各自完成來源接受。
6. `python -m scripts.build_source_acceptance_dossier --input <candidate-json> --output <TEMP-projection.json>` 只可輸出到正式 `DATA_ROOT` 之外。投影的 `dossier_content_hash` 是 dossier 欄位的 canonical SHA-256；檔案傳輸或落盤完整性必須另算 serialized file SHA-256，兩者不可混用。投影仍固定 `candidate_only=true`、`formal_oos_allowed=false`、`production_blend_alpha_bp=0`，不構成來源接受。

只有台帳已記錄真實的 `accepted` / `limited` / `rejected` / `deferred` 結論、owner、日期與明確 downstream eligibility 時，才可另行規劃後續受控實作。本手冊與台帳本身不授權任何 ingestion 或策略變更。

V1.6 後，可用 cross-sectional factor snapshot inspection CLI 唯讀檢查已保存的 daily factor snapshot。這個 CLI 不建立 DB、不寫 snapshot、不重算 scoring；若指定的 DB 不存在會以錯誤結束。snapshot 只會在其他受控 workflow 明確呼叫 `CrossSectionalFactorPipeline` / `CrossSectionalFactorRepository` 保存後才存在。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_cross_sectional_factor_snapshot.py --db-path <working-copy-db> --latest --json
.\.venv\Scripts\python.exe scripts\inspect_cross_sectional_factor_snapshot.py --db-path <working-copy-db> --snapshot-id <snapshot-id> --markdown
```

輸出會包含 snapshot metadata、row count、factor / quality / rank bucket 分布、sector / concept basket counts 與 diagnostics counts。rank / quantile 只代表當日橫斷面 factor 排序與研究 attribution，不是推薦名單、不代表買賣訊號，也不會改 `ScoringEngine`。Concept basket 只有在定義的 `available_date <= decision_date` 時才會進入 row；未到可得日只會出現在 diagnostics。

V1.8 後，可用 Portfolio Sandbox inspection CLI 檢查研究用 allocation / virtual execution trace 的樣本輸出。這個 CLI 目前只支援 `--sample`，不讀正式 DB、不寫 output、不建立持倉、不產生 broker order；輸出全部標示為 research-only。Allocation 結果使用整數 bp 權重、`Decimal` 金額字串、整數股數與 lot sizing；trace event 只表示虛擬 lifecycle，不代表實際委託或成交。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_portfolio_sandbox.py --sample --format json
 .\.venv\Scripts\python.exe scripts\inspect_portfolio_sandbox.py --sample --format markdown
```

### 資料來源路由與 FinMind 配額

日常更新優先使用富邦 market-data API、TWSE／TPEX／MOPS／TDCC 官方端點與已受控的自有網頁抓取器；每種資料必須先依資料語意選擇 provider，不能把價格、法定公告與盤中狀態互相冒充 fallback。富邦是授權市場資料主源，適用於即時／當下可觀測行情與已文件化的公司行動欄位；MOPS 仍是財報、月營收與更補正的法定公告鏈；TWSE／TPEX／TDCC 仍是市場制度與日終資料鏈。

資料源的嘗試順序為：同一語意的富邦或官方 API／官方 HTML fast path → 同一語意的受控爬蟲 fallback（MoneyDJ 僅 HTTP Big5 失敗或無法解析時才啟用 Selenium）→ 已保存 raw artifact 的唯讀重試。任何 source 切換都要保留 provider、source version、實測時間、row count、成功／失敗原因與 fallback 原因；沒有等價語意的來源時 fail closed，不以其他資料類型補值。

FinMind 是低頻 bulk／缺口來源，不是全市場逐檔的日常更新主線。帳戶上限為每小時 600 requests，實作與人工執行均採 `480` requests/hour 軟上限，保留 20% 給暫時錯誤與人工查詢；逐檔 dataset 必須以缺口 queue、夜間執行與 `--resume` 續跑，官方或富邦已成功取得的同一資料不得重複請求。月營收 create-time CLI 必須明確提供至少一個 `--stock-code`；若確實要使用 raw 清單做批次，必須同時提供 `--all-raw-stock-codes --resume`，避免無意間啟動全市場逐檔請求。可一次取得全市場或涵蓋所需期間的 FinMind dataset 才可進 bulk queue；`create_time` 僅是 FinMind 觀測時間，不能取代 MOPS／交易所公告時間。

### 富邦行情 API 人工唯讀連線測試

`scripts/test_fubon_readonly_marketdata.py` 只供人工確認 Windows Credential Manager API key、憑證與 OTC 行情 snapshot 連線。可在目前終端設定 `FUBON_PERSONAL_ID`、`FUBON_CERT_PATH`，必要時設定 `FUBON_CERT_PASS`；若 Codex／Antigravity 等終端 process 不共用環境變數，則可在 Windows Credential Manager 建立下列 Generic Credentials，username 一律為 `market-data`：`fubon-neo-readonly-api-key`（API key）、`fubon-neo-readonly-personal-id`（身分識別）、`fubon-neo-readonly-cert-path`（憑證完整路徑），以及只有私鑰密碼不同於身分識別時才建立的 `fubon-neo-readonly-cert-pass`。工具優先使用當前 process 的環境變數，其次讀取這些 Credential Manager 項目；不得把任何值寫入 repo、命令列或 log。缺少任一必要 credential 時腳本以 exit code 2 停止，登入失敗以 exit code 1 停止；成功登入後唯一允許的資料呼叫是 OTC snapshot quotes。此工具不呼叫帳務、持倉、委託或交易 API，不保存行情、不寫 DB，也不代表 broker lane、source acceptance 或 Formal evidence 已成立。自動化與測試只能使用 injected fake SDK，不得代替人工實際登入。

### 富邦行情 Source Acceptance Dossier 唯讀盤點與評估

`scripts/inspect_fubon_dossier.py` 用於對富邦 market-data 的 source acceptance dossier 進行唯讀盤點與評估。它可以檢測當前 dossier 缺少的證據，並區分「程式可驗證」與「只能由 owner / legal / source owner 提供」的項目，最後在指定安全白名單的 shadow root 目錄下產生一個供 owner 審查的繁體中文範本：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_fubon_dossier.py `
  --dossier C:\Temp\external-evidence-shadow\fubon_dossier_projection.json `
  --output-template C:\Temp\external-evidence-shadow\review_template.md `
  --shadow-root C:\Temp\external-evidence-shadow
```

本工具為 review-only，所處理之 dossier 被標記為 deferred candidate，且狀態始終保持為 owner review pending。無論檢核項目是否完整，狀態一律投影為 deferred、allowed_use_cases=()，且下游 downstream_eligibility=none。此工具不寫入正式資料庫，預設不輸出 template 檔案，且只有當 `--output-template` 與 `--shadow-root` 同時存在並通過嚴格的正式路徑拒絕驗證時才允許寫入。

### Formal clock 起跑前檢查

Formal clock 不是 development adapter 完成的延伸；只有在真實決策當下才能建立第一個 observed day。開始前必須同時具備：

1. 具名 owner 的 `HoldoutConsumptionRegistry.jsonl` 已置於 development output root 的 `governance/`，並在每次綁定前重新檢查；它必須可證明 owner decision 指定的第一個未消費交易時段尚未被使用。沒有 registry 時不得宣稱 holdout 已綁定、已消費或 formal readiness 成立。
2. 真正 decision-time 產生的 `manual_observed` JSON：`decision_timestamp`、`max_available_timestamp`、`data_as_of_date`、source versions、Rule champion identity、universe hash、symbol、why／why-not／risk、restriction state 與所有 missing/degraded reason 都必須來自當下可見的決策輸出。不得由歷史 replay、fixture、事後補寫或 automation invocation count 合成。
3. owner 若已綁定 Rule-only lane，可在該 lane 的**真實台北盤中 09:00–13:30**，以新的 foreground-only 命令產生當下的 decision source。它只讀 `daily_prices` 中嚴格早於決策日的最近 60 個交易日，使用固定 20 日價格／成交量整數 bp 排名，輸出受 HMAC 驗證的 Rule Champion、hash-addressed decision output 與可交給下一步的 `manual_observed.json`。它不讀 MOPS／富邦／基本面／ML，不寫 market DB、Recommendation、Portfolio、Exit、Score、lifecycle 或 evidence ledger，也不建立 scheduler。第一次使用前，owner 必須在自己的 Windows 使用者環境設定受控的 `RULE_CHAMPION_CONTROLLED_STORE_HMAC_KEY` 與非空的 `RULE_CHAMPION_CONTROLLED_STORE_ID`；key 不得寫入 repo、命令列、log 或 JSON artifact。

```powershell
.\.venv\Scripts\python.exe scripts\run_manual_rule_only_decision.py `
  --development-output-root C:\Temp\technical_analysis_development_output `
  --market-db <TWStockConfig.db_file 的實際 SQLite 路徑> `
  --lane-decision-json C:\Temp\technical_analysis_development_output\governance\FormalObservationLaneDecision_20260807_r1.json `
  --confirm produce-manual-rule-only-decision
```

成功時請從 JSON 輸出取得 `manual_observed_json` 路徑；這只建立決策來源，**不**代表 formal credit、elapsed day、holdout consumption、source acceptance 或 production readiness。若命令回報盤外、session mismatch、registry／lane 無效、資料庫時間晚於決策時間、資料不足或 attestation key 缺失，保持 snapshot count=`0`，不要用改時間、fixture、歷史資料或再次 automation invocation 補造輸出。

4. snapshot 僅可追加到 TEMP 或明確命名的 shadow sidecar，並由下列命令人工確認；它不寫 market DB、不啟用 scheduler、交易、training、promotion 或 formal OOS：

```powershell
.\.venv\Scripts\python.exe scripts\capture_external_evidence_manual.py `
  --db $env:TEMP\external-evidence-shadow\evidence.sqlite `
  --output-root $env:TEMP\external-evidence-shadow `
  --snapshot-json <真實決策當下保存的-manual_observed.json> `
  --confirm append-external-evidence
```

5. 每一筆 P0 source 仍需依 `docs/06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md` 取得具名 owner／reviewer 的 license、quality、PIT、coverage、missing／outage 與 rollback 決議；candidate、degraded 或 research-only artifact 都不會自動變成 accepted source。

若上述任一項缺失，snapshot count 維持 0；不得以同日多次執行、pending outcome、歷史回填或 fake／replay artifact 取得 formal credit。

不得用內建常數、sample rows、固定 timestamp／score／source hash 的 CLI 輸出組裝 `manual_observed`。每個 snapshot 的 `parent_artifact_ids` 至少必須有一個 hash-addressed 的真實 decision-output lineage（格式含 `:sha256:`）；缺少時 capture 與 preflight 都會拒絕。即使其他 schema 欄位相符，該 JSON 仍是 synthetic fixture，沒有真實決策輸出與來源 provenance，必須排除於 Formal snapshot、observed day、denominator 與 credit。

`HoldoutConsumptionRegistry.jsonl` 是 owner 的 append-only 決議載體，不是 automation 可代寫的設定檔。`development_holdout_start` 是開發資料的排除起點；`formal_trading_session` 則是 owner 在綁定當下選定的第一個未消費正式觀測交易時段，兩者不可因為現在才綁定而倒填成過去的 observed day。owner 真正決定綁定後，才可依下列一行 JSONL 契約建立第一筆 record；尖括號內容必須是 owner 的真實資料，不能直接複製為正式證據：

```json
{"schema_version":"holdout-consumption-registry.v2","record_type":"formal_holdout_binding","development_holdout_start":"2026-07-15","formal_trading_session":"<綁定後第一個未消費臺灣交易時段>","owner_id":"<具名 owner>","binding_authorization":"<可引用的 owner 決議 ID 或 artifact>","bound_at":"<含時區的綁定時間>","owner_decision_sha256":"<DevelopmentDataUsageDecision.jsonl 的 sha256:...>","unconsumed_before_binding":true,"formal_oos_allowed":false,"production_blend_alpha_bp":0}
```

preflight 會拒絕缺欄、無時區、早於 owner decision、formal session 早於 binding、decision hash 不符、未明示 `unconsumed_before_binding=true`，或任何解除安全旗標的 record；snapshot 的決策日期也必須剛好等於 `formal_trading_session`。它只能驗證 owner 的結構化聲明，不能自行證明交易時段確為「第一個」；該判定與授權仍屬 owner 責任。

若舊 v2 session 已經留下 shadow-only／deferred artifact，不得覆寫或倒填。owner 可以另建一份 `formal-observation-lane-decision.v1`，以 `holdout_id`、決議時間、第一個決議後未使用交易日、Rule-only source whitelist 與 candidate-source exclusion list 凍結新 lane；接著使用下列 CLI append 一筆 v3 binding。CLI 會保留舊 v2 record，拒絕重複 `holdout_id`、重複交易時段、決議前 binding、非 owner 核准 session、repo／正式 `DATA_ROOT` 路徑與任何安全旗標放寬：

```powershell
.\.venv\Scripts\python.exe scripts\bind_formal_observation_lane.py `
  --development-output-root C:\Temp\technical_analysis_development_output `
  --decision-json C:\Temp\technical_analysis_development_output\governance\FormalObservationLaneDecision_20260728_r1.json `
  --formal-trading-session 2026-07-29 `
  --bound-at <含時區的真實綁定時間>
```

v3 binding 只是 future observation lane 的 owner-attested boundary，不是 observed snapshot、holdout consumption、Formal credit 或 source acceptance。富邦可以同時維持 shadow／candidate 可用，但若 decision artifact 未把 `fubon.marketdata` 排除，lane contract 會 fail closed。

先以唯讀 preflight 檢查 owner decision、owner-attested registry binding 與**已存在**的 snapshot 結構；此命令不建立 registry、不綁定 holdout、不寫 evidence，也不會宣稱 formal readiness。`can_capture_shadow_snapshot=true` 僅表示 binding 契約與 snapshot 均通過結構驗證；實際「第一個未消費交易時段」的判定仍須具名 owner 決議，且 source acceptance 未完成時 `formal_readiness` 一律為 `false`。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_formal_clock_readiness.py `
  --development-output-root C:\Temp\technical_analysis_development_output `
  --lane-decision-json C:\Temp\technical_analysis_development_output\governance\FormalObservationLaneDecision_20260728_r1.json
```

若已有真正 decision-time artifact，才可額外傳入其路徑檢查契約；不要用 fixture、replay 或事後補寫檔案測試後就執行 capture：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_formal_clock_readiness.py `
  --development-output-root C:\Temp\technical_analysis_development_output `
  --lane-decision-json C:\Temp\technical_analysis_development_output\governance\FormalObservationLaneDecision_20260728_r1.json `
  --snapshot-json <真實決策當下保存的-manual_observed.json>
```

V2.4 紙上政策可用下列唯讀 CLI 檢查。它固定使用核准的平衡型參數，對現金、單檔、產業、週轉與 cooldown 限制產生 `PAPER_TRADE_CANDIDATE` 或 `NO_PAPER_TRADE`；結果不是交易指令，也不讀實際持倉或寫入任何資料庫。

Paper Portfolio 日更工程另提供 append-only snapshot repository。每個 `snapshot_id` 只能新增一次，歷史 snapshot 不可覆寫；價格、現金與市值以 Decimal 字串保存，權重以整數 bp 保存。此 repository 僅存 research paper ledger，不連接正式持倉或 broker。

Daily mark-to-market runner 只使用 `price_date <= decision_date` 且 `available_date <= decision_date` 的價格。若任一持倉沒有 causal price，整次日更 fail-closed，不建立部分 snapshot；非交易日可使用前一個可見交易日並留下 diagnostic。它只重算紙上市值與權重，不執行再平衡或 broker order。

日常 Paper execution candidate producer 使用 research-only Recommendation、
preopen T-1 Paper snapshot 與官方 `daily_prices` 唯讀列，在下一個已由官方證據
證明的 session open 執行。Recommendation 的 `decision_date` 可以是休市自然日；
市場 reference 會沿官方日曆／本地 market_indices evidence 綁到該日或之前最近的
實際交易 session，不能把週日當成 `daily_prices` 日期。reference session 的
`收盤價` 只作來源 binding；成交 reference 改用下一 session 的 `開盤價`，並驗證開盤事件已到
台北 09:00 cutoff、reference session 收盤時已可取得的 `成交股數`、整張與 5%
participation cap。execution 日的完整 EOD `成交股數` 不得回看作為開盤前
cap；目前 `daily_prices` 沒有盤中來源時間，因此候選明確標示
`delayed_eod_replay_after_session_close`、`execution_source_capture_at_proven=false`
與 `realtime_execution_allowed=false`。tick slippage、commission、賣出稅、
turnover 與 execution gap 都保留在候選內；preopen snapshot 是 execution 的 T-1
起始狀態，EOD writer 只追加獨立 postfill transition，不由 snapshot 反推成交、不
更新既有 snapshot、不寫正式行情／Formal DB，也不連接 broker。

每筆委託都會依實際可證明的流動性與現金政策獨立保存
`requested_quantity`、`filled_quantity`、`remaining_quantity`、`status` 與
`execution_reason`。推薦日成交量的 5% cap 向下取整至 1000 股；cap 為零時該筆為
`rejected`，cap 小於請求量時為 `partially_filled`，其他股票仍會繼續評估。現金
不足只會限制買入數量；合法賣出即使期初現金低於 reserve 也會先增加可用現金，未
成交部位在下一個 snapshot 保留。來源缺失、帳務不一致、超額賣出或負現金仍會讓
整輪 fail-closed。現金結算採 `gross_amount + commission + tax`（賣出為 gross
減費用）；`fill_price` 已包含 tick slippage，所以 `slippage_cost` 只進入
`total_cost` 歸因，不會再次從現金扣除。此版本在 candidate 的
`cash_settlement_semantics=gross_amount_plus_commission_plus_tax_v1` 與
`cost_attribution_semantics=commission_plus_tax_plus_slippage_attribution_v1`
明確保存語意，既有 ledger payload／hash 欄位維持相容。

由於來源沒有逐列 capture timestamp，runner 以台北交易日 15:00 作為保守的
EOD replay 最早可消費時間；09:00 後但 15:00 前只回傳
`waiting_for_execution_source`，不讀行情／snapshot、不建立 fill。這個時間是
延遲重播政策門檻，不是宣稱官方 HTTP 在 15:00 已完成發布。

```powershell
.\.venv\Scripts\python.exe scripts\run_paper_execution_daily.py `
  --recommendation-json <當日-scheduled-recommendation.json> `
  --state-db <paper_portfolio.sqlite> `
  --market-db <twstock.db> `
  --output-root <新的-OS-TEMP-目錄>
```

CLI 不接受日期覆寫；Recommendation 的 `decision_date` 必須早於下一個官方
execution session，且 `created_at` 必須早於該 session open。snapshot 可以先於
execution session 的 preopen cutoff 建立，會以 T-1 state 重用；reference session
close、reference session 可用成交量與 execution 日 open 均須和官方
row 綁定，交易日證據不可由星期幾猜測。沒有盤中開盤來源 timestamp 時，這是
延遲 EOD replay candidate，不是 09:00 即時成交。預設只產生
`machine_verified_candidate`、
`waiting_for_execution_session` 或具體 `blocked` receipt。只有同時提供 `--ledger-db`
並明確傳入
`--confirm-append-paper-ledger` 才會呼叫既有 append-only Paper fill writer；該
ledger 仍固定 `research_only=true`、`broker_order_allowed=false`、
`auto_rebalance_allowed=false`。`run_paper_portfolio_daily.cmd` 會先呼叫
isolated adapter；首次只將 D 槽 `OUTPUT_ROOT\paper_portfolio\paper_portfolio.sqlite`
以 SQLite `mode=ro/query_only` consistent backup seed 到
`<repo>\output\paper_execution_eod_replay\paper_portfolio\paper_portfolio.sqlite`，
再由公開 `run_paper_portfolio_daily.py` 在 repository state append。來源、初始
target 與後續 state head hash 都保存於 seed/head manifest，D snapshot 永遠不是
writer target。若設定 `PAPER_EXECUTION_RECOMMENDATION_JSON`，cmd 只以同一份
repository state 建立 candidate；排程 hook 不會自動追加 ledger。排程 hook 先建立
台北 08:30 preopen snapshot，再由 EOD task 在 15:00 後重用該 T-1 state；首次
postfill append 與相同 deterministic fill IDs 的 idempotent retry 都可驗證，partial／
divergent batch 仍保留 blocker，不能把 snapshot 解讀成成交。下一個
`run_paper_portfolio_daily.py` 以 repository `--ledger-db` 的唯讀 transition projection
將已 append fill 套用到隔日 snapshot，並保存現金／股數守恆 diagnostic。

日常排程不需要每天改寫 recommendation 路徑：
`baldr-paper-execution-eod-replay-daily` 使用
`--recommendation-root <OUTPUT_ROOT/recommendation/runs>` 依下一官方 session 到期
順序挑選 frozen input，並把每次結果保存到
`<OUTPUT_ROOT>/scheduled/paper_execution_eod_replay/receipts/`。它預設以
`PAPER_EXECUTION_LEDGER_DB` 追加 research-only Paper fill；若只要預覽，可設定
`PAPER_EXECUTION_APPEND=0`。receipt 的 `queue_state=processed` 只在 append
readback（或 no-trade）完成時出現；`waiting`、`candidate_only_pending_append`、
`superseded`、`failed` 與 `skipped` 都保留原始原因，不會被排程轉成 ready。Queue
唯一鍵是 `portfolio_id + next_official_execution_date`；同一 execution session
若有多份 frozen recommendation，只選最新建立者並為其餘 source 保存
`superseded` receipt，避免 processed hash 排除最新 source 後改執行較舊目標。
排程只有在 receipt schema、content hash、來源 recommendation 檔案 hash、candidate
result 與 Paper ledger append/readback 都能重新驗證時，才把 source 視為已處理；
損壞 receipt 不會阻止重試，source JSON 解析失敗會以具體 blocker 顯示。

Portfolio-level rebalance evaluator 會依固定順序逐檔套用現金、單檔、產業、cooldown 與累計週轉限制；前一筆 paper candidate 會占用後續批次的週轉額度。結果固定 `apply_rebalance=false`、`broker_order_allowed=false`，需要另行人工檢視，不會改寫 snapshot。

Equal-weight benchmark 在 baseline 日凍結 constituents 與等額 units，後續不因新推薦或下市存活狀態替換成分，以避免 survivor bias。每日 benchmark ledger 只接受 causal price 並 append-only 保存；任一 frozen constituent 缺價即 fail-closed。

Weekly paper report 只有在 snapshot 成本基礎與逐 snapshot ledger 視窗可核對時，才可計算 gross／net／benchmark／net excess。現有歷史 snapshot 未保存上述證據，週報維持 `not_computable`，不猜 gross／net 或零成本。已含成交成本的 net NAV 不可再次扣成本；成本窗口採起始日含、結束日不含的 `[period_start, period_end)`。純 API 的成本加回 gross 僅為明示報告口徑，不是無成本反事實績效。報告固定 `research_only=true`、`investment_effectiveness_claim=false`。

Position thesis contract 要求人工保存 entry thesis、entry/decision/available date、持有期限、下次 review date、source trace 與至少一條結構化 invalidation rule。規則 threshold 使用 Decimal，future-available thesis 會被拒絕；contract 固定 `auto_exit_allowed=false`。

Position Health state machine 僅使用決策日當下可得的 Decimal metrics。future 或 missing metric 會 fail-closed 到 `WATCH`；invalidation rule 可標示 `action=reduce` 或 `action=exit`，論點弱化先提出 `REDUCE_CANDIDATE`，硬性失效才提出 `EXIT_CANDIDATE`。holding horizon 只有在呼叫端提供涵蓋 entry／decision 兩端的官方交易日曆時才計數；日曆不完整會留下 `time_stop_calendar_incomplete`，不猜曆日。`CLOSED` 是終態。所有結果固定 `apply_transition=false`、`auto_exit_allowed=false`。

Position Health transition repository 採 append-only event。`proposal` 事件的 `recorded_state` 必須維持 previous state；只有帶 reviewer 的 `human_approved` 事件可記錄核准後狀態。兩者都固定 `auto_action_allowed=false`，不會送出賣單。

Workbench 的 engineering closure projection 只顯示工程包完整度與尚待人工／時間／授權／ML 重驗項目。每列會顯示 owner、最早驗證日、進度及下一個驗證命令；Action Item 固定唯讀，不能在 Workbench 直接標記完成、修改 registry 或套用任何 production action。

Exit effectiveness read model 依 reason code 分組，只將 maturity=`ready` 的 outcome 放入績效分母，分別揭露 avoided loss、early-exit regret、precision 與 realized return；pending 只計數。報告固定不宣稱投資有效性，也不啟用 auto exit。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_paper_portfolio_policy.py --sample --format json
```

若要從已保存 Recommendation 建立第一個真實資料 paper baseline，使用下列命令。輸出只寫 JSON artifact，不寫 Portfolio DB、不產生 broker order、不自動再平衡；正式操作前仍需確認來源 result ID 與輸出位置。

```powershell
.\.venv\Scripts\python.exe scripts\build_paper_portfolio_baseline.py --recommendation-json <saved-recommendation.json> --output <paper-baseline.json>
```

V2.5 可用下列唯讀 CLI 檢查持倉健康狀態的輸出形狀。它以內建樣本顯示 thesis／condition／feedback 缺口如何形成 `HEALTHY`、`WATCH` 或 `EXIT_CANDIDATE`；任何狀態都不是交易或平倉指令，`auto_action_allowed` 固定為 false。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_position_health.py --sample --format json
```

可由 paper baseline 建立 fail-closed health baseline；缺 entry thesis、invalidation、holding horizon 或 review date 時固定為 `WATCH`，並列為人工必填欄位。此命令不寫正式持倉，也不允許自動 action。

```powershell
.\.venv\Scripts\python.exe scripts\build_position_health_baseline.py --paper-baseline <paper-baseline.json> --output <health-baseline.json>
```

目前支援的 allocation method 為 `equal_weight`、`score_weight` 與 `inverse_volatility`。`max_position_weight_bp` 只會限制單一部位上限，不會自動把超出的權重重新分配到其他股票；買不起最小 lot 或套用上限後的現金差額會留在 `residual_cash` 與 diagnostics。Virtual trace 支援 `created`、`submitted`、`partially_filled`、`filled`、`rejected`；`cancelled`、零股、買賣價差、完整撮合與 gap actual execution model 仍是後續 execution-model residual。

V1.9 後，可用本地 MCP server `twstock-evidence-access` 讓支援 MCP 的 Agent 查詢 evidence。這個 server 只包裝 `AgentEvidenceAccessService`，使用 read-only SQLite URI / `PRAGMA query_only=ON` 與既有 read-only repository；它不建立 schema、不寫 DB、不修改策略、不下單、不套用 lifecycle action。若 DB 或 table 不存在，輸出會在 `diagnostics` 回報，檔案不會被建立。

```powershell
.\.venv\Scripts\python.exe mcp_servers\evidence_access_server.py
```

MCP tools：

- `get_agent_permission_model`：回傳 read-only role、allowed / denied actions、DB policy 與 lifecycle policy。
- `get_ai_report_template`：回傳 evidence-only report template，要求引用 evidence rows、quality、warnings、source trace 與 limitations。
- `query_evidence_events`：查 evidence events，必要時包含 forward outcomes；支援 symbol、event type、decision date / date range、limit、window days。
- `summarize_forward_evidence`：依 event type / family / source / regime / sector / profile / score bucket / liquidity / data quality 彙總 forward outcomes。
- `query_research_runs`：唯讀查 Research Run Registry metadata，可依 run id、run type、strategy id 過濾。
- `query_portfolio_review_evidence`：查已保存 live research gap observation 與 lifecycle evidence rows；Portfolio Review snapshot 本身不是 V1.9 的持久化查詢物件。

輸出判讀：

- `access_boundary.mode` 應固定為 `read_only`，`writes_allowed=false`。
- `limitations` 必須與 report 一起保留；結果不是買賣建議，不是策略變更，也不是 lifecycle action。
- `diagnostics` 有值時代表資料源、table 或查詢條件不足；不得用空結果推論策略有效或失效。
- AI report 只能把查到的 evidence rows 整理成摘要與審核問題；LLM thesis 不是 primary evidence。

V2.0 前可用 `scripts\inspect_pre_v2_readiness.py` 做非排程 readiness 檢查。此 CLI 只讀既有 evidence DB、Research Run DB、multi-day record markdown 與 scheduled dry-run `latest_status.json`，不建立 schema、不寫 evidence、不啟用 scheduler；missing DB / table 只會回 diagnostics。它會把 weekly history、multi-day dry-run、source gaps 與 read-only Agent report sample 分成 `ready`、`waiting_for_time`、`action_required`，且 `production_scheduler_allowed` 永遠是 `false`。JSON／Markdown 也會明確輸出 `formal_credit_authorized=false`，避免把 owner-approved projection 的 `ready` 誤讀成 Formal credit 已授權。CLI 現在與 Workbench 共用 `WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH`；也可用 `--approved-weekly-history-projection <path>` 明確指定同一份 `approved-weekly-history-projection.v1`，明確參數優先於環境變數。projection 只供 UI／readiness 揭露，不授予 formal credit。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_pre_v2_readiness.py --db-path <working-copy-db> --decision-date 2026-07-06 --multi-day-record-path docs\06_qa\POST_V1_EVIDENCE_PIPELINE_MULTI_DAY_DRY_RUN_RECORD.md --json-output
.\.venv\Scripts\python.exe scripts\inspect_pre_v2_readiness.py --db-path <working-copy-db> --decision-date 2026-07-06 --markdown --report-output output\qa\pre_v2_readiness.md
# 與 Workbench 使用同一份 owner-approved projection（只讀）
.\.venv\Scripts\python.exe scripts\inspect_pre_v2_readiness.py --approved-weekly-history-projection <projection.json> --json-output
```

`waiting_for_time` 代表仍需真實多週 / 多日累積，不可用 fixture、單次 smoke 或無證據的手動改表替代。V2 closeout 可接受修正後歷史觀察日，但必須保留同日或指定觀察日的 dry-run report / scheduled `latest_status.json`；source-gap closeout 只會在 `dry_run=true`、`writes_evidence_db=false`、`source_coverage_blocking_gaps=[]`、`pipeline_blocking_gaps=[]` 且 `scheduler_readiness_after=ready_for_manual_confirm` 時採信。此 fallback 只解除 readiness inspector 的 source-gap 紅點，不代表正式 DB 已 confirm、scheduler approval、production readiness、投資有效性或交易建議。

V2.0 Phase 1 / Phase 1.5 可用 `scripts\inspect_v2_workbench_prototype.py` 檢查 read-only Workbench prototype 輸出。這個 CLI 保留 `--sample`，也可用受控 `--db-path` / `--decision-date` 讀 existing read-only sources：Pre-V2 readiness、Daily Decision durable snapshot、AgentEvidenceAccess summary 與可選 Historical Replay JSON summary。Current Workbench 與 Pre-V2 查詢上限固定為台灣市場今日；若 DB 內有未來 Decision Desk row，會保留 raw 診斷／blocker，畫面只採用最後一筆安全 snapshot，不把未來 row 當成 current evidence。它不寫 evidence、不掛主 UI、不建立 scheduler、不下單、不套用 lifecycle action，也不重算 scoring、portfolio、backtest 或 lifecycle 狀態。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_v2_workbench_prototype.py --sample --format json
.\.venv\Scripts\python.exe scripts\inspect_v2_workbench_prototype.py --sample --format markdown
.\.venv\Scripts\python.exe scripts\inspect_v2_workbench_prototype.py --sample --replay-summary-json D:\Min\Python\Project\FA_Data\output\evidence_pipeline\historical_replay_reference_fix_20260706\historical_replay_2026-01-06_2026-07-06_reference_fix.json --format markdown
.\.venv\Scripts\python.exe scripts\inspect_v2_workbench_prototype.py --db-path <working-copy-db> --decision-date 2026-07-06 --multi-day-record-path docs\06_qa\POST_V1_EVIDENCE_PIPELINE_MULTI_DAY_DRY_RUN_RECORD.md --format json
.\.venv\Scripts\python.exe scripts\inspect_v2_workbench_prototype.py --db-path <working-copy-db> --decision-date 2026-07-06 --replay-summary-json D:\Min\Python\Project\FA_Data\output\evidence_pipeline\historical_replay_reference_fix_20260706\historical_replay_2026-01-06_2026-07-06_reference_fix.json --format markdown
```

輸出會包含：

- `access_boundary.mode=read_only`、`writes_allowed=false`、`production_scheduler_allowed=false`。
- `source_mode=sample_only`、`sample_plus_historical_replay`、`read_only_sources` 或 `read_only_sources_plus_historical_replay`。
- 「今日待判讀」、Evidence mode、market context、portfolio / watchlist summary、Daily Checklist、warnings。
- 若 `--db-path` 缺檔、缺 `decision_desk_snapshots` table 或找不到指定 decision date snapshot，輸出會保留 read-only dashboard 並在 warnings / review items 揭露 degraded source；若發現 future decision date，會顯示 `decision_desk_snapshot_future_dated` 與排除診斷；CLI 不會建立 DB 或 schema。
- 若讀取 `_reference_fix` replay JSON summary，會揭露 simulated scheduler、source gap、source gap coverage、payload gap、outcome maturity、benchmark coverage、industry benchmark coverage、missing industry benchmark、pending future-data 與「方向正確但尚未 production-ready」限制。

V3 score effectiveness audit 可用 `scripts\inspect_score_effectiveness.py` 檢查既有 Evidence Event / Forward Outcome 中，`TotalScore` raw bucket 與 forward outcome 的唯讀關係。第一版支援 `--sample`、`--format json|markdown`、`--output`、`--min-sample-size`，也可用明確 `--db-path` 以 SQLite `mode=ro` / `PRAGMA query_only=ON` 讀既有 evidence DB。現在每個 bucket 另輸出 `liquidity_cost_bp_by_horizon`、`cost_adjusted_excess_bp_by_horizon` 與描述性 `benchmark_excess_ci95_bp_by_horizon`；成本後欄位只扣除 evidence 的 liquidity cost，不把缺失的 turnover、手續費、稅費補成零。這個 CLI 只做 read-only aggregation，不寫 production DB、不提供 `--confirm`、不啟用 scheduler、不改 `ScoringEngine`、不改推薦權重、不改 threshold，也不訓練 ML model。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_score_effectiveness.py --sample --format json
.\.venv\Scripts\python.exe scripts\inspect_score_effectiveness.py --sample --format markdown --output output\qa\score_effectiveness_sample.md
.\.venv\Scripts\python.exe scripts\inspect_score_effectiveness.py --db-path <working-copy-db> --format json --min-sample-size 10
```

輸出固定保留 `0-40`、`40-50`、`50-60`、`60-70`、`70-80`、`80-100` 六個分數區間，即使該 bucket 沒有樣本也會顯示 empty bucket。每個 bucket 會列出樣本數、ready / pending / missing outcome、各 horizon 的 forward return bp、benchmark excess bp、industry excess bp、liquidity cost、成本後超額、描述性 95% 區間、max drawdown bp、win rate bp、warnings 與 limitations。`access_boundary.writes_allowed=false`、`production_scheduler_allowed=false`、`investment_effectiveness_claim=false` 與 `ml_training_allowed=false` 必須保留；結果只能用於研究覆盤，不能解讀為買賣建議、投資有效性證明、threshold promotion 或 ML production readiness。

V4.1 A 線的推薦機率校準研究可用 `scripts\inspect_recommendation_calibration.py`。此 CLI 以既有 `recommendation_included` Evidence Event 與成熟的 20／5 trading-day Evidence Outcome 建立固定 outcome contract，按 decision date 做 expanding `train`／`calibration`／`untouched-test` walk-forward。它會輸出 baseline prevalence、`score_percentile_v1`、整數 bp isotonic calibrated probability、10 個 probability bins、樣本數、Wilson 95% 區間、Brier／ECE，以及 forward return、benchmark return／excess、cost-adjusted return／excess。主目標是 20 日，5 日只作輔助觀察。

```powershell
# 只跑 deterministic sample，不讀正式資料
.\.venv\Scripts\python.exe scripts\inspect_recommendation_calibration.py --sample --format markdown
.\.venv\Scripts\python.exe scripts\inspect_recommendation_calibration.py --sample --format json --output output\qa\recommendation_calibration_sample.json

# 既有 evidence DB 只讀查詢；缺成熟 outcome 時會回 not_evaluable 與 diagnostics
.\.venv\Scripts\python.exe scripts\inspect_recommendation_calibration.py --db-path <working-copy-db> --format markdown
.\.venv\Scripts\python.exe scripts\inspect_recommendation_calibration.py --db-path <working-copy-db> --fixed-round-trip-cost-bp 80 --format json
```

固定判讀規則：

- decision time 是 event 的 `decision_date`；`event_date`、`as_of_date`、`available_date` 晚於 decision date 的 row 會被排除。training／calibration 的 label end 也必須在各自切點前成熟；test row 不回流 fit。
- primary labels 是 `forward_return_bp > 0` 與 `forward_return_bp > fixed_round_trip_cost_bp + observed liquidity_cost_bp`。缺 liquidity cost 不補零、不進 after-cost label；fixed cost 預設 `0 bp` 不代表完整手續費、證交稅或 execution ledger 已提供。
- benchmark 直接使用 Outcome 保存的 benchmark 欄位；缺值只縮小該項統計，不補成 0。成本後欄位明確揭露成本來源與 sample count。
- `ranking_score_bp`、`score_percentile_bp`、`upside_probability_bp`、`after_cost_profit_probability_bp`、`action_suitability`、`evidence_confidence` 是不同欄位；probability 不是 score，也不是自然語言 confidence 的百分比勝率。
- `price_volume_v1` 目前只是 challenger ablation。新匯入的 recommendation event 會保存決策當下的 indicator／pattern／volume component bp；歷史缺件不回填。chip／funding、industry、PIT theme 尚未接入，必須先有可核對的 decision-time／PIT source lineage。
- report 固定 `production_eligible=false`、`production_scheduler_allowed=false`、`natural_forward_evidence_credit=false`，不改 ScoringEngine、推薦權重、threshold、alpha 或 promotion pointer。sample／replay 不可視為自然 forward evidence。

### V4.1 A 線第二輪歷史研究與候選方法包

使用 `scripts\build_v41_historical_method_pack.py` 可將既有 recommendation Evidence Event／Outcome 以 query-only 方式展開為逐列、逐 horizon 的 dataset manifest，並重用同一套 20 日 primary／5 日 auxiliary expanding `train`／`calibration`／`untouched-test` evaluator。它會另外列出 current baseline、price／volume challenger、chip／funding、industry-relative 與 PIT theme 的 ready／blocked coverage 與 gap codes；PIT theme 只有在決策當下可得的 membership id、as-of、available-at 與 source hash 全部存在時才可列為 ready。

```powershell
# 正式 evidence SQLite：只讀，輸出請放在 DATA_ROOT 外的專屬目錄
.\.venv\Scripts\python.exe scripts\build_v41_historical_method_pack.py `
  --db-path D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --output-dir C:\Temp\v41_historical_method_pack_YYYYMMDD `
  --format markdown

# deterministic sample：只驗證契約與 walk-forward 結構，不是自然 forward evidence
.\.venv\Scripts\python.exe scripts\build_v41_historical_method_pack.py `
  --sample --output-dir C:\Temp\v41_historical_method_pack_sample_YYYYMMDD `
  --format json
```

輸出目錄會以 create-only 方式保存 `historical_dataset_manifest.json`、`historical_calibration_report.json` 與 `frozen_candidate_artifact.json`；若任一同名檔案已存在，CLI 會拒絕覆寫。manifest 每列保留 `decision_date`、`available_at`（含 precision）、`label_maturity`／`label_end_date`、strategy config、universe policy／snapshot、return basis、benchmark、fixed／liquidity cost、event／outcome／source hash 與 `gap_codes`。缺 outcome 只標為 `missing_outcome`，未成熟 outcome 標為 `insufficient_future_data`，不以 fixture、replay 或 current snapshot 回補。

正式資料若回 `observation_row_count=0`、`fold_count=0` 或 `status=not_evaluable`，只能判讀為目前沒有足夠成熟且可追溯的樣本；它不代表策略有效或失效。`frozen_candidate_artifact.json` 固定 `shadow_only=true`、`production_eligible=false`、`promotion_eligible=false`、`recommendation_weights_changed=false`、`scheduler_enabled=false`，只能交給 B 線做 hash 驗證與唯讀 shadow，不能改正式推薦或寫回 SQLite。完整 2026-09-12 結果見 [V4.1 歷史研究與候選方法包 QA](../06_qa/V4_1_HISTORICAL_METHOD_PACK_2026_09_12.md)。

正式 evidence DB 若出現 `observation_count=0` 或 `fold_count=0`，只能解讀為成熟度／來源不足，不能解讀為策略有效或失效。完整契約、實際 2026-09-10 read-only 結果、測試與限制見 [V4.1 推薦機率校準垂直切片](../06_qa/V4_1_RECOMMENDATION_CALIBRATION_VERTICAL_SLICE_2026_09_10.md)。

### V4.2 每日推薦自動學習與受控校準調整

每日 shadow loop 的排程入口是 `scripts\scheduled\run_recommendation_calibration_learning.cmd`。wrapper 會呼叫
`scripts\scheduled\run_daily_recommendation_learning_pipeline.py`，依序完成官方日價／技術來源、
official market-event custody、正常 scheduled recommendation snapshot，再呼叫
`scripts\scheduled\run_daily_recommendation_learning.py`。在 canonical host 上，它接續同一主機
local time 05:40 的 `baldr-forward-outcomes-daily`，於 host-local 05:45 執行；Task Scheduler
以無 offset local trigger 保存這個順序，runner 仍以 `_taipei_now()` 與官方 calendar 判定資料日期，
不把主機 local clock 誤當台北早盤時間。它只讀取指定的 market SQLite，並把 dataset、frozen
challenger、prediction capture、自然成熟 evidence、promotion decision 與 rollback receipt 寫入
專用的 `RECOMMENDATION_LEARNING_OUTPUT_ROOT\recommendation_learning\`。這個 root 不繼承一般產品的
`OUTPUT_ROOT`：未指定專用環境變數或 CLI override 時，`DATA_ROOT=D:\Min\Python\Project\FA_Data`
會解析到同層的 `D:\Min\Python\Project\FA_Data_Shadow`；自訂 `DATA_ROOT` 則解析到其上一層的
`FA_Data_Shadow`。`RECOMMENDATION_LEARNING_OUTPUT_ROOT` 與 CLI `--output-root` 都必須是
`DATA_ROOT` 外的絕對路徑；違反時以 `recommendation_learning_output_root_invalid` fail closed。
scheduler、pipeline、runner、read-only consumer 與 Workbench 共用這個 root contract。它不寫
`recommendation`、`evidence_outcomes`、Portfolio、Formal 或 broker state，也不改 `ScoringEngine`、
正式推薦權重或 scheduler write mode。

#### Canonical runner、lineage 與 cutoff 診斷（2026-09-15）

本輪 canonical learning implementation 是
`ml_module\recommendation_calibration_learning_runner.py` 的
`DailyRecommendationLearningRunner`；scheduled entrypoint
`scripts\scheduled\run_daily_recommendation_learning.py` 直接使用它。舊的
`app_module\daily_recommendation_learning_runner.py` 不再是 runtime entrypoint。要檢查
ML shadow dependency boundary，可使用：

```powershell
.\.venv\Scripts\python.exe scripts\check_ml_shadow_boundary.py
```

fresh candidate 的 `candidate.json` 若宣告 training lineage，必須同時保存
`training_lineage_manifest_hash` 與 `training_lineage_manifest_path`，並可由 immutable
manifest 讀回驗證。兩個欄位都不存在的舊 frozen candidate 才能標示
`legacy_unproven`；只缺其中一個、欄位為空或格式／讀回驗證失敗時，runner 必須寫入
`failed_lineage`／`invalid` 並保留 `frozen_candidate_lineage_invalid_fail_closed`，不可
手動刪欄位把 damaged declaration 降級成 legacy 相容。

`training_as_of`／`training_cutoff` 晚於本次 `decision_date` 時，只有在 dataset quality
明確同時宣告 `research_only=true` 與
`training_semantics=historical_research_only` 才能建立 historical research artifact；
其 lineage 的 `decision_time_eligible` 必須是 `false`。沒有這兩個語義時，runner 以
`failed_training`／`retain_current` fail closed。即使 research artifact 已建立，authority
與 read-only consumer 仍不得把它當作較早 decision date 可用的 candidate；應回到
`rule_only`，且 future label 不得進入 decision-time training／inference path。

#### 2026-09-14 source → snapshot → learning 操作順序

正常 wrapper 的環境與預設值如下；若要做 controlled trial，才額外設定
`RECOMMENDATION_LEARNING_SYMBOLS`，不要把 explicit symbols 當成正常 daily cohort：

```text
DATA_ROOT=D:\Min\Python\Project\FA_Data
RECOMMENDATION_LEARNING_OUTPUT_ROOT=D:\Min\Python\Project\FA_Data_Shadow
DB_PATH=D:\Min\Python\Project\FA_Data\sqlite\twstock.db
RECOMMENDATION_LEARNING_HISTORY_START_DATE=2014-01-01
RECOMMENDATION_LEARNING_MAX_DECISION_DATES=100
RECOMMENDATION_LEARNING_COST_BP=50
RECOMMENDATION_SNAPSHOT_MAX_STOCKS=200
RECOMMENDATION_SNAPSHOT_TOP_N=50
RECOMMENDATION_OFFICIAL_MAX_ATTEMPTS=4
RECOMMENDATION_OFFICIAL_TIMEOUT_SECONDS=30
RECOMMENDATION_OFFICIAL_RETRY_DELAY_SECONDS=2
RECOMMENDATION_OFFICIAL_REQUEST_DELAY_SECONDS=1
```

直接檢查同一 pipeline 時，可明確指定相同參數；`--child-timeout-seconds=3600` 與
`--pipeline-timeout-seconds=10800` 是 pipeline 的預設硬上限（2026-10-04 更新）：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_daily_recommendation_learning_pipeline.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data_Shadow `
  --source-db D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --max-stocks 200 --top-n 50 `
  --history-start-date 2014-01-01 --max-decision-dates 100 `
  --fixed-round-trip-cost-bp 50 `
  --official-timeout-seconds 30 --official-max-attempts 4 `
  --official-retry-delay-seconds 2 --official-request-delay-seconds 1
```

pipeline 的四個子步驟與判讀如下：

1. `run_daily_data_update_quick.py` 走官方日價／market／industry／technical path；正常 learning
   pipeline 會傳入 `--skip-broker-branch`，因此 MoneyDJ broker-branch 只在 status 中明確標記
   `skipped`，不會讓這條核心學習 lane 假裝有 broker source。TPEx 缺價、待重試日期與 technical
   publication hash 必須保留在 `latest_status.json` 與 receipt，不能把 partial source 當 complete。
2. `run_official_market_event_backfill.py` 使用 `prospective_bounded` publication scope。端點失敗
   時 fail closed；只有已驗證的 prospective pointer、raw retrieval time 與 hash 都能重驗時，才可
   保留 last-known-good replay，且 replay 不算當日新抓取或 historical PIT evidence。
3. `run_scheduled_recommendation_snapshot.py` 使用 `max-stocks=200`、`top-n=50`；snapshot status
   必須同時查看 `requested_symbols`、`eligible_symbols`、`missing_symbols`、`degraded_symbols`
   與 warnings。未指定 `--symbols` 的 learning child 只讀同日 snapshot 的 eligible cohort，不做
   universe discovery；每日 cohort 會改變 `run_scope`／`capture_scope`，但不改固定的
   `experiment_scope`。因此 manual 三檔 capture 不得被正常一檔或另一日 cohort 重用。
4. learning child 使用 query-only SQLite，預設 `--capture-current` 會先檢查當日是否為
   Asia/Taipei official trading day，再保存 source-bound feature capture；週末、休市、缺 symbol
   rows 或 source contract 不合格時會 skip／blocked，不能以 `--skip-capture-current` 的
   `not_requested` 當成日曆或自然 evidence 證明。

目前日期的正常分支與歷史來源修訂拒絕分支，都會獨立處理 current-observed 自然研究 lane。`--skip-capture-current` 只停用本次新增輸入 capture：狀態為 `not_requested`，仍會驗證並掃描既有 immutable captures 的到期結果。當日收盤前，新 entry 為 `pending`（`official_session_not_closed_yet_wait_for_scheduled_close`），`same_day_rows_consulted=false`；不讀未收盤列，也不阻止舊樣本的成熟掃描。歷史決策日不執行這條現在觀測支線。

判讀 learning CLI 時，同時查看頂層退出碼、`run.status`、`dependencies`、`current_observed_input_capture` 與 `current_observed_natural_research`，並核對它們的 exact receipts。RC0 可以與研究支線 pending、正式 `failed_dependency` 同時存在，不能據此判定正式模型可用。自然研究 fit 不將樣本加入正式 replay／training；`historical_pit_eligible`、`formal_training_allowed` 與 `promotion_credit_created` 保持 false。

每個 child 的 timeout 都是可恢復狀態，timeout 不刪除既有 durable receipt；pipeline 的總時間用盡時，
尚未執行的 child 會以 `pipeline_timeout:<step>` blocker 收尾。snapshot 不可用時 learning 不會啟動，
同一 decision date 的資料補齊後可重跑；同日相同 identity／hash 的 receipt 仍受 create-only 與冪等規則保護。

2026-09-18 BankTaiwan learning 排程已實際執行，並非尚未啟動：台北 `20:50:03–20:50:50` 的
wrapper run `2026-09-18-attempt-001-91feea81e0f4` 以 `failed_dependency`／child exit `2` 收尾，
診斷為 `live_capture_blocked:prospective_price_up_source_not_ready:technical_prospective_source_not_ready`。
technical publication 本身已 passed，`missing_technical_symbols=[]`，但 requested 7 檔中的
`missing_source_symbols=[1569]` 缺同日來源 custody；當日 TPEX technical receipt 只到 9/17，
`prospective_available=false`，所以 live capture 保守阻擋。這是來源 custody 缺件，不是 technical
計算失敗；不降低 gate 或刪除 1569 湊數。有效自然 captures 仍為 9/15–17 三份、18 rows、
matured=0，待後續合法來源更新後由既有排程重試。

```powershell
# bounded shadow run；明確股票群組，不做 universe discovery
.\.venv\Scripts\python.exe scripts\scheduled\run_daily_recommendation_learning.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root <DATA_ROOT 外的隔離輸出目錄> `
  --source-db D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --symbols 1101,2330 `
  --history-start-date 2014-01-01 `
  --replay-selection-policy latest_eligible_dates `
  --max-decision-dates 100 `
  --fixed-round-trip-cost-bp 50
```

固定判讀與安全限制：

- replay 只作 training data；每列固定 20 trading-day absolute stock-return labels，feature 與 label 都要通過決策日／label availability 的 causal cutoff。它永遠標記 `forward_evidence_eligible=false`，不能用歷史 replay 灌滿自然成熟日。
- `--symbols` 若省略，只接受同日已保存的 scheduled recommendation snapshot 明確股票群組；沒有群組會以 exit 2 寫入 `failed_dependency`／`recoverable=true` attempt，不做 universe discovery，snapshot 在同一 decision date 到齊後可直接重跑。台北週末／休市日可完成 bounded receipt，但跳過 live capture，不把自然日算成交易日。
- candidate 第一次 fit 後以 candidate、dataset、manifest、artifact、policy、feature schema 與 probability lineage freeze；後續每日只新增當下 feature 與 active/challenger identity capture。重跑同日同 hash 是冪等，暫時 dependency 失敗保留 `finalized=false` 的 recoverable attempt，資料到齊後可在同一 decision date 重跑；只有 source integrity／active fault 或明確 emergency rollback 才會建立 finalized rollback receipt。
- 自然 evidence 只接受 immutable capture 加上後來真正成熟的 forward price／market source；至少 20 筆且至少 20 個 distinct decision dates 才能進比較。重複 `(symbol, decision_date, horizon)` 不增加分母。candidate 與 active monitor 分開計算；active monitor 的新成熟 receipt 會在同一次 main run 重新檢查，若超過 drift gate 即同日 fail-closed rollback。
- 每輪都會產生 `recommendation-calibration-source-contract.v1` inspection receipt。它至少要有 component、source id/table、status、coverage、available-at、SHA-256、source columns 與 verification 欄位；service 另外重算 symbol-scoped 實際 source rows digest、期間／symbol coverage，並驗證 feature builder 實際使用的 technical row `available_at <= decision`。只填 `verified=1` 或只填任意 hash 不會通過；contract blocked 時仍可保留 historical research artifact，但 prospective capture 與 promotion 會保留明確 source blockers。固定 caller symbol cohort 不宣稱 PIT constituent history。
- source custody 每輪以帶 timezone 的精確 `availability_cutoff_at` 判定：timestamp 先正規化 UTC，再要求 `available_at <= capture cutoff`；同一 instant 的 `+08:00` 與 `Z` 可接受，晚於 cutoff 的同日 publication 會拒絕。technical publication、daily source receipt、prospective feature snapshot、official event publication 與 corporate-adjustment manifest 都要逐一通過 availability binding；這只建立 prospective boundary，不授予 historical PIT eligibility。
- 即時推薦校準的 fail-closed 判讀：若來源在單次 SQLite snapshot 載入後或模型 projection 期間變更，服務保留規則推薦與規則分數，將校準結果標示為 unavailable，丟棄尚未發布的模型 projection，且不發布模型 receipt。來源穩定後，可由既有推薦流程重新執行；若反覆發生，先檢查同時寫入與來源修訂狀態，依維護流程處理，不要手動改寫或刪除 source receipt、資料庫或 hash。
- Live calibration 的 lease 涵蓋單次 provider load 至 model projection 後的 postcheck；historical replay 的 lease 涵蓋整輪多次讀取前後的同連線 observation check，任一可見的外部 commit 都會拒絕整輪結果。這不是長讀取交易或 durable generation，也不提供 sidecar／SQLite 跨資源原子性，或排除所有 ABA 與 postcheck 後競態。規則推薦仍是規則結果，不代表校準 projection 可用。
- corporate action source 必須有實際可讀 records、有效 adjustment factor、coverage 與一致 digest。raw close 沒有可驗證 adjusted-price custody 時，non-unit action 落在 label window 會保守排除該列並保留 blocker；不可只因 table 存在或 bool 為 true 就把 raw label 當成 adjusted。
- after-cost label 只在取得可追溯的 `evidence_outcomes.liquidity_cost_bp` 時建立。成本存在時，使用獨立命名的 `after_cost_null_benchmark_50pct_v1`／5000 bp baseline；成本缺失時 after-cost target、model output 與 consumer projection 均保持 `None`，不補零、不借用 upside baseline。adopted active model 的 post-adoption matured rows 會在其 label availability cutoff 通過後，以同一 null-baseline contract 供下一 training cycle 使用，不把 active prediction 當 target。

主要輸出：

```text
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\latest_status.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\scheduled\recommendation_calibration_learning\latest_status.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\scheduled\recommendation_calibration_learning\latest_snapshot_source_status.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\scheduled\data_update_quick\latest_status.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\scheduled\official_market_events\latest_status.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\scheduled\recommendation_snapshot\latest_status.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\runs\YYYY-MM-DD\run_receipt.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\datasets\<dataset_id>\dataset.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\challenger\current.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\source_contract\YYYY-MM-DD\<hash>\contract.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\captures\YYYY-MM-DD\<capture_scope>\<candidate_id>-<request_fingerprint>.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\active_captures\YYYY-MM-DD\<capture_scope>\<candidate_id>-<request_fingerprint>.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\evidence\<candidate_id>\YYYY-MM-DD.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\active_evidence\<candidate_id>\YYYY-MM-DD.json
<RECOMMENDATION_LEARNING_OUTPUT_ROOT>\recommendation_learning\recommendation-calibration-active-pointer.json
```

BankTaiwan 05:50 排程的 snapshot root 預設與 05:45 Legacy learning shadow root 相同（`BANKTAIWAN_SOURCE_ARTIFACT_ROOT`），不是正式 `DATA_ROOT\output`。05:45 保留完整 pipeline status 供診斷，另外原子發布 `daily-recommendation-snapshot-source.v1` 小型同次投影；BankTaiwan 優先讀投影，再依 immutable stdout、canonical artifact、cohort、日期與雜湊做唯讀回驗。沒有投影的舊輸出才讀完整 status，仍受 8 MiB 上限約束；投影存在但格式錯誤時不得回退至舊 status。若顯示 `recommendation_pipeline_status_missing_or_invalid`，先核對兩個 wrapper 的 root 與上述投影，不要複製正式 snapshot 來湊同次身分。這仍是 research-only，不提供正式 Evidence 或交易授權。

判讀時先看 `dependencies`、`natural_evidence`、`active_model_natural_evidence`、`model_performance`、`candidate_blockers`、`decision_receipt` 與 `formal_order_allowed=false`。`pending` 代表等待真正成熟時間或不足門檻；`failed_dependency` 且 `finalized=false`／`recoverable=true` 代表暫時前置資料未到，可於同一 decision date 重跑；`retain_current`／`rule_only` 代表沒有通過 authority；`adopt` 只代表 shadow consumer 可讀取 versioned candidate，並不改正式 Recommendation；`rollback` 會回到完整 previous candidate，沒有可恢復 champion 時回到 explicit rule-only。pointer、artifact、manifest、lineage、policy 或 evidence receipt 損壞時一律 fail closed。目前正式 DB 的 source contract、自然 matured evidence 與成本覆蓋仍須以當次 receipt／QA 判讀，不可用 fixture、historical replay、單次 bounded run 或手動改 JSON 解除 gate。

2026-09-14 的實際 readback 應分開看：normal 200-row snapshot 仍是 partial／degraded，TPEx `20260914`
缺價 warning 仍在；2026-09-14 04:22:11-07:00 的最新 wrapper 已完成，pipeline status 為
`passed_with_warnings`、blockers 為空；同輪 quick publication 於
`2026-09-14T04:21:27.181165-07:00` 完成且 publication 為 `published`。technical computation receipt 為 `D:\Min\Python\Project\FA_Data_Shadow\scheduled\technical_indicator_publication\2026-09-14\0f533bde5119890a\receipt.json` 且已 verified；2148 檔股票的 bounded 真重算已完成。learning child 已
`completed` 並保存 normal live capture：正常 cohort 的 symbol source=
`scheduled_recommendation_snapshot:scheduled_rec_20260914_042140.json:eligible`，只有
`1528`；bounded historical bootstrap 後 training rows 為 255，candidate 為
`rec-cal-29c1b6129396a3885a89d080`，沿用 experiment scope
`scheduled-experiment-ff4d2ab937e2c8b32bf2df04`；single-class blocker 已處理，沒有使用三檔
capture 代替正常 lane；natural sample 為 `0`，authority 仍 `retain_current`，原因為
`natural_forward_evidence_receipt_missing`。

bootstrap 的 durable observation status 為 `recovered_completed`，selection policy 為
`time_stratified_eligible_dates`；manifest 為
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\datasets\recommendation-dataset-da3d867b06b5436d\dataset.json`。
manifest 的 `initial_seen_start=2026-04-23`；bootstrap replay selected date window 為
`2024-09-16` 至 `2026-02-11`，date overlap、row overlap、label boundary crossing 均為 `0`。
這組結果只說明 bounded training lineage 的分層觀測，不能當作自然 forward evidence 或 formal PIT。

本次正常 lane 的新 immutable capture scope 是 `scheduled-capture-5f4de77ffb404af2`，實體路徑為
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\captures\2026-09-14\scheduled-capture-5f4de77ffb404af2\rec-cal-29c1b6129396a3885a89d080-850760d54413e019199be668.json`，
hash 為 `sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`。
decision 仍為 `retain_current`，原因是 `natural_forward_evidence_receipt_missing`，自然 sample 為
`0`；不能把 candidate trained 或 pipeline warning 收尾當成自然 evidence、promotion 或收益證明。
price-up 可獨立進入 prospective natural verification；after-cost
缺 observed liquidity cost 與 fill lineage 時保持 missing／blocked，固定 50 bp 不得標成 observed；
actual execution 與 broker lane 不在本流程。前兩輪 180 秒 timeout 是失敗；04:10 default 雖完成，但 publication 因 completion microsecond witness 不合法而 blocked，normal capture 亦因 nested
 capture blocked 且被舊 training completed 遮蔽而出現 false-success。兩者均不列為驗收；04:22 新 durable run 才採信。affected focused suites 已有 107 passed（11 個 test
files、36.44 秒、既有 1 個 warning）；P1 三日 cache-hit custody QA 亦已通過
（`tests/test_recommendation_learning_cache_hit_custody.py`：`1 passed, 1 warning in 1.25s`）。
該 QA 驗證 2026-09-08 至 2026-09-10 的正式 output receipt 可跨 root 由 `FA_Data/output` 真實
verified reuse 至 `FA_Data_Shadow`、保留原 timestamp，並通過 source-audit hash／value／lineage
與正式 ADX producer 輸出；fixture source 仍為 `fixture.invalid`，不授予自然證據。real natural
maturity、formal PIT 與 observed cost 仍依各自 gate 維持 pending／out-of-scope；工程與正式 default smoke 已由父任務接受，
不能用單次試跑、fixture、replay 或 orchestration `passed_with_warnings` 取代；04:22 wrapper
true-success 已記錄。

獨立 UI／型別驗證的最新 readback 為：`tests/test_ui_qt_update_view_workbench.py` 81 passed（1 個
pytest cache permission warning）、`scripts/qa_validate_update_tab.py` 25 passed／0 failed／4
skipped；主 Luna 修正 source-contract Mapping guard 後，mypy 檢查 `606` 個 source files 並回報
`Success: no issues found in 606 source files`。另有獨立三日 cache-hit custody QA 通過；這些結果
仍不代表 real durable daily flow、自然 forward evidence 或 V4 整體 gate 已完成。

進一步的主線驗收 readback 為：affected focused suites `107 passed`（11 個 test files、`36.44s`、既有 1 個 cache warning）；
source-contract／capture／official-custody／guards focused `17 passed`，update-service／process-pool／technical-analysis
focused `10 passed`，targeted mypy `5 files` clean；changed scheduled scripts 的 mypy 檢查 `7 files` 成功；changed
scripts／modules／tests 以暫時 `PYTHONPYCACHEPREFIX` 執行 py_compile 通過，但原有 `__pycache__` permission 限制仍需保留在
判讀中；inventory 驗證 `12 passed`，新增 cache guard 後登錄總量已核實為 `805`、recommendation 為
`31`。synthetic mature fixture 為
`tests/test_daily_recommendation_learning_loop.py::test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags`，已通過 production source verifier、adopt／active／rollback assertions。P1 三日 technical cache-hit custody QA 已以 `currentity→verified receipt reuse` 修復並通過：正式 output receipt、原 timestamp、production source audit hash／value／lineage 與正式 ADX producer 輸出均驗證；結果為 `1 passed, 1 warning in 1.25s`。這只證明 bounded fixture 的跨 root custody，不解除 real natural
forward、formal PIT、actual cost 或 V4 gate。scheduler `14 passed` 已接受，04:22 wrapper
true-success 已記錄；主 Luna 回報 QA 7.1 為 `33 passed`；僅主 Luna git commit 尚待完成。

Phase 2 起，Qt 主 UI 新增 `決策工作台` 分頁作為 read-only Unified Decision Workbench MVP shell。2026-08-14 後，總覽第一屏先顯示「今日行動中心」與單一下一步導覽，再顯示今日重點帶、語意色摘要卡、今日待判讀、背景證據流、只讀 Action Items 與 Inspector；這些導覽按鈕只切換既有工作區。操作節奏、Evidence mode / data quality、Daily Checklist 與 warnings / degraded source 改成可收合區塊，需要時再展開。畫面只透過 `WorkbenchSourceService` 取得 `WorkbenchDashboardDTO`，不直接讀 SQLite、不寫 DB、不啟用 scheduler，也不重算 scoring、portfolio、backtest 或 lifecycle。若預設 `_reference_fix` replay JSON summary 存在於 `OUTPUT_ROOT/evidence_pipeline/historical_replay_reference_fix_20260706/`，主 UI 會自動把 JSON summary 傳入 WorkbenchSourceService；這仍只是讀 summary，不會讀 replay DB 或執行 replay。

操作與判讀：

- 入口：執行 `.\.venv\Scripts\python.exe ui_qt\main.py`，開啟頂層 `決策工作台` 分頁。
- 今日重點帶與摘要卡：第一屏最上方會用醒目色帶彙總待判讀、人工處理、等待真實時間與 warnings。橘色代表需要人工注意或等待真實時間，紅色代表 warning / blocked / missing 類高風險，藍色代表資訊或 manual observed，綠色代表 ready / observed / passed。顏色只用來輔助掃描，仍需依 Inspector 與原始 source trace 判讀。
- 操作下鑽：`開啟市場總覽`、`開啟市場探索`、`開啟證據覆盤`、`開啟持倉管理` 只會切到既有 Market Exploration / Daily Decision、Research Lab / 證據覆盤、Portfolio 頁面；Workbench 不嵌入或建立第二份 Decision Desk。它們是 expert drill-down，不會從 Workbench 觸發寫入、scheduler、回測或 lifecycle action。Action Items、今日待判讀與背景證據流的 row drill-down target 也走同一個舊頁導向 contract：`daily_decision` 切到「市場探索 > 市場總覽」、`portfolio_review` 切持倉管理、`evidence_review` / `evidence_mode` 切證據覆盤。推薦結果與觀察清單的單股下鑽會把股票、決策日、資料日、結果 ID、Profile 與來源 workspace 寫入共用 `研究上下文`；市場探索頁完成後可按「返回來源」回到原清單並重新定位股票，不會重新計算或猜測來源。
- Status strip：檢查 Daily Decision durable snapshot、Evidence gate、Data quality 與 Production Scheduler；scheduler 應維持 `off` / `production_scheduler_allowed=false`。
- 今日待判讀：只列出需要人工 review 的 watchlist trigger、portfolio alert、risk prompt 或 readiness gap；它不是買賣建議，也不會產生下單動作。
- 詳情檢視 / Inspector：點選今日待判讀、背景證據流或 Action Items 的任一列，右側會用狀態徽章與三個分區顯示完整內容：「重點摘要」看標題與 summary，「來源與邊界」看 source trace、degraded reason、drill-down target 與 read-only 保證，「診斷訊號」看 diagnostics token。表格只保留掃描欄位；完整證據不要在表格橫向捲動找，改看 Inspector。
- 背景證據流：只彙整既有 DTO / service payload，包括 Daily Decision snapshot、Evidence Review readiness、Portfolio alerts 與可選 replay summary diagnostics。清單表格只顯示「證據來源 / 狀態 / 摘要」，完整 source trace、degraded reason、diagnostics 需點列後在 Inspector 查看。這個區塊不讀 replay DB、不重跑 Evidence Pipeline、不重新判斷 portfolio 或 scoring。若清單為空，文案會提醒只是 DTO payload 為空，不代表 gate 通過；若來源降級，文案會要求依 source trace / diagnostics 人工檢查，不補值、不重跑 pipeline。
- 背景證據流也會顯示 `Scheduled morning pipeline`，來源是 `ScheduledEvidenceStatusService` 唯讀讀取 `OUTPUT_ROOT/scheduled/*/latest_status.json`、recommendation snapshot 檔、經 query 驗證的同日人工 recommendation result fallback、evidence dry-run report 檔與 forward outcome receipt。它會顯示最新 scheduled 或 manual recommendation result id、推薦筆數、recommendation snapshot 觀測天數、manual recommendation 觀測天數、evidence dry-run 觀測天數、forward outcome status 與 scheduled recommendation/evidence 共同觀測天數；`manual_observed` 只解除人工判讀的資訊缺口，不會把 scheduled 狀態標成 passed，也不會自動解除正式 multi-day gate。forward outcome receipt 缺失時只呈現 source gap，不以推薦結果或資料日期推估 outcome。
- 只讀 Action Items：只顯示人工待處理事項；清單供排序與掃描，完整 `queue_group`、`severity`、`source_label`、`source_trace`、`degraded_reason`、`drilldown_target` 與 `write_intent=false` 可點列後在 Inspector 查看。Composer 會先依 severity，再依 queue group 與 source 排序，讓持倉警示、風險提示、觀察清單與 readiness gap 更容易掃描。空狀態不代表可以交易或 gate 已通過；降級狀態只供人工覆盤排序，不是買賣建議。Workbench 不建立 action item repository、不 append DB、不標記完成、不套用 lifecycle action。
- 操作節奏：只從 `WorkbenchDashboardDTO.operating_loop_steps` 顯示 daily first-look、manual queue、weekly review history、multi-day dry-run、manual review note 與 scheduler gate。這個區塊預設收合；展開後以直列 timeline card 呈現步驟編號、狀態 badge、摘要與 linked item chips，避免水平捲動。長的 source trace、人工提示與 `write_intent=false` 會收在「展開細節」中；Workbench 不會把項目標記完成、不會寫 DB、不會補 weekly history / multi-day dry-run、不會啟用 scheduler。
- Evidence mode / data quality：讀取 DTO 內的 evidence summary 與 diagnostics；上方以兩張摘要卡拆分「邊界與 Gate 摘要」及「覆蓋率與缺口」，下方表格只保留證據、狀態與摘要，完整 diagnostics 需點列後在 Inspector 查看。若 payload 帶 replay summary，會揭露 `simulated_scheduler`、source gap / coverage、payload gap、outcome maturity、benchmark coverage、industry benchmark coverage、missing industry benchmark 與 pending future-data 限制。2026-07-06 `_reference_fix` summary 的目前判讀是市場 benchmark coverage 已補齊成熟 outcomes，但 screening matrix source gap、產業 benchmark 大量缺口與 pending future-data 仍阻擋 production readiness；這不是投資有效性結論。
- Workbench >「研究證據」（Evidence / Research Console）：此子頁固定分成 Safety Boundary、Development Pipeline、Evidence / Source Gates 三區。Safety Boundary 必須顯示 `formal_oos_allowed=False`、`production_blend_alpha_bp=0`、Production ML disabled、正式 Recommendation / Portfolio 維持 Rule-only，以及 promotion / retrain / scheduler / trading disabled。頁面上方先給中文結論（例如 Rule 使用中、ML 未參與、缺正式輸入或投影已過期），技術識別碼與原始 blocker 預設收合，按「顯示技術診斷」才展開。Development Pipeline 只複製顯式 `RESEARCH_CONSOLE_PROJECTION` 指向的 sanitized `ResearchConsoleProjection.json`，顯示 Dataset V0、Rule Development Baseline、ML Development Challenger、E2E identity、row / feature count、label maturity、artifact citation 與 blockers；缺欄使用 `Missing / Unknown`，不補零。Evidence / Source Gates 固定保留 EV1–EV5、13 個 P0 source、獨立 Broker lane、P0 Data Source Control Center 與 Artifact Inspector；Control Center 逐列顯示 governance/machine/audit/decision status、row 數、blockers 與 `downstream_eligibility`，沒有 audit 時仍顯示 13 列 `contract_only`，不把 development、candidate、provisional、degraded、fixture 或 replay 冒充 formal accepted / forward evidence。頁面唯一控制是「重新載入唯讀 projection」，沒有 Apply、Promote、Retrain、Blend、Accept Source 或 Trade。
- Workbench >「研究證據」（Evidence / Research Console）的「每日學習／機率校準（唯讀）」區塊置於安全邊界之後、大型開發／P0 來源表之前，預設選取 `banktaiwan_estimated_research`（`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning`），另可切換但不混用 `legacy_fixed_bp`（`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning`）。它只讀 `latest_status.json`、candidate／capture／receipt 與 active pointer，並透過 typed candidate／active natural-evidence verifier 與 prediction-capture verifier；不執行 producer、不重算、不寫 receipt／pointer、不 promotion、不下單。摘要先以繁中短句顯示目標決策日、學習資料決策日、臺銀費稅估算／成本 lane、該日預測是否已記錄、候選／目前路徑成熟樣本與決策日數、保留原因及下一步；沒有 capture 時明示「尚未建立該日預測紀錄」。長 candidate／model／dataset／scenario／receipt／source trace 與 raw reason 預設收在「驗證詳情」，不擠滿主摘要。明細表分開列 candidate natural、active model natural、capture recorded、各 horizon 的 recorded／matured sample 與 decision-date count、Brier／calibration gap；只有 verifier 通過的 natural comparison 才能進入 reliability bins。沒有已驗證自然樣本時不顯示機率可靠度或區間；80% 區間的 observed 欄位是成熟樣本的實際上漲比例，不是 ranking score 的準確率或交易保證。臺銀估算成本及其 after-cost 結果一律標 `research_only_estimated`；歷史 evaluation／untouched test 只作 historical replay，不能與 natural matured evidence 合併。
- 每日學習區塊的判讀順序是 `cost lane` → requested／learning decision date → candidate／active identity → capture `recorded`／`pending`／`blocked_provenance` → horizon maturity → typed receipt／reliability bins。`stale`、`future_blocked`、capture 缺日期、改列／hash、歷史 origin、成本 scenario 不一致、receipt bytes 在驗證後被換檔或 source path 越界都必須保持 blocked／unknown；不得用另一 lane、舊 replay、controlled fixture 或缺 receipt 的 capture 補值。當前若顯示 `natural_forward_evidence_receipt_missing`、`retain_current` 或沒有 verified natural sample，代表等待真正後續交易日，不是安全、promotion 或正式機率通過。
- BankTaiwan 排程若在 `scheduled/recommendation_learning_banktaiwan/latest_status.json` 顯示 `failed_dependency`、`child_exit_code:2` 與 `decision_reason=cost_scenario_root_conflict`，先保留該 attempt receipt、`recommendation_learning/challenger/current.json`、latest status、decision receipt、candidate、manifest 與 artifact，不刪 marker 或手改 JSON。舊 challenger pointer 一般必須具備完整 candidate identity、canonical manifest、實際 artifact bytes、candidate freeze、cost contract 與 label registry；僅已核驗的 legacy 05:45 marker 可以在只缺 top-level `candidate_freeze_hash` 時進入 read-only compatibility，而且必須有同 cohort 的完整 freeze challenger anchor，latest status 與 immutable receipt 的 candidate／root／manifest／artifact／dataset／`run_scope` exact match。缺 root、缺 cohort、swapped candidate／root／dataset、任何 hash／artifact／freeze 衝突或 receipt bytes 不一致一律 fail closed；不會補目前預設 50 bp，也不會寫回 marker、receipt、candidate 或 freeze。完整 2026-09-15 首次失敗、2026-09-16 cross-anchor 唯讀 root 回驗與隔離回歸見 [BankTaiwan 首次排程失敗 QA](../06_qa/BANKTAIWAN_FIRST_SCHEDULED_RUN_FAILURE_2026_09_15.md)。
- Research Console 排錯：未設定 `RESEARCH_CONSOLE_PROJECTION`、檔案不存在、JSON/schema 不合法時，頁面仍可開啟並顯示 `Missing` 或 `degraded`；若 projection scope 不是 exact `historical_research_seen_development_data`，或宣稱 formal OOS、非零／非整數 alpha、promotion eligible、缺少 canonical apply flag、出現額外 flag、任一 flag 不是 literal `false`，service 會以 `projection_boundary_violation` fail-closed，不套用該內容。`lineage.generated_at` 必須是含時區的 ISO-8601；缺少、格式錯誤、超過未來 5 分鐘或距目前超過 7 天時，分別顯示 `projection_generated_at_missing`、`projection_generated_at_invalid`、`projection_generated_at_future` 或 `projection_stale`，保留 sanitized identity 供排錯但整體固定降級，不代表 formal elapsed day。E2E row 的 artifact hash 是實際 projection bytes 的 SHA-256；injected mapping 沒有實體檔時保持 Unknown。啟動與重新載入只讀 JSON，不掃描 development／正式資料目錄、不建立 SQLite 連線、table、directory 或 artifact。
- 工程預演狀態 / Evidence Rehearsal：在「Evidence mode」下方查看注入的 `EvidenceRehearsalDashboard`。此唯讀區塊固定揭露「工程／Replay／Shadow；不是 forward evidence」、rehearsal tier、coverage、blockers、是否提供 Shadow comparison 與 `Forward handoff：pending`。coverage 會逐來源列出 observed、missing、degraded、future-blocked 與 immature-label 計數；`missing`、source outage 或 `insufficient_sample` 必須維持已阻擋／預演狀態，不得被畫成 clean、ready 或正式通過。這個區塊沒有 apply / promote 按鈕，不能寫入 DB、啟用 scheduler、改變 Advice 或把 replay / shadow 結果視為 forward evidence；要補齊問題時，只能依 blocker 回到既有人工、資料授權或真實時間流程處理。
- Daily Checklist：以 status card 顯示 freshness、Evidence gate、multi-day dry-run、manual review 與 scheduler write-mode 等 gate，內容可換行，不再以寬表格呈現。未設定 approved projection 時 legacy DB 可能顯示 `0/3`；歷史 working-copy=`1/3`、UI projection=`3/3`、sidecar pending=`10`、multi-day=`3/3`，但 formal credit 仍未授予。現在要完成的是 10 期具名 review、formal credit、backup／rollback／recovery 與 scheduler approval；fixture、單次 smoke、手動改表或 replay 都不能補齊。
- Warnings / degraded source：missing DB、missing table、snapshot missing、replay limitation 或 Agent sample limitation 都會以 warning 保留；Warnings 會依唯讀 / Phase Gate、缺漏來源、Replay / 模擬資料、資料品質、需要人工覆盤與其他警示分組，每組預設顯示前三項，其他項目可展開查看。不要手動補空資料或改表讓畫面變綠。

Replay summary 只能使用 JSON summary；不得把 replay DB 直接交給 prototype CLI 或 Qt Workbench。`--db-path` 建議使用 working-copy DB 或明確允許的 read-only source path；missing / degraded source 是要被呈現的 evidence gap，不可手動補 fixture 當作 gate 通過。Workbench CLI 與 Qt shell 都是 V2.0/V2.1 資訊架構與 read-only contract 檢查，不代表 production scheduler approval，也不是交易建議。

目前 replay summary 分析數字（讀自 `historical_replay_2026-01-06_2026-07-06_reference_fix.json`）：118 個交易日、118,056 events、472,224 outcomes；成熟 outcomes 為 380,736，pending future-data 為 91,488。成熟 outcomes 的市場 benchmark coverage 為 380,736/380,736、missing benchmark 為 0；產業 benchmark coverage 為 2,245/380,736、missing industry benchmark 為 378,491；`source_missing_screening_matrix` 出現在 118/118 replay days，另有 missing event price 216。這表示 Workbench 的 read-only evidence direction 是正確的，因為 benchmark 全缺問題已解除且缺口可被揭露；但仍不能宣稱 production readiness、投資有效性或啟用 scheduler。

2026-07-06 closeout 的參考結果：在 ignored working-copy DB 與 output-root mirror 中，source gaps 為 `ready`、read-only Agent report sample 為 `ready`、Evidence Review UI smoke passed、all-source working-copy confirm smoke repeat=2 idempotency passed；當日整體仍為 `waiting_for_time`，因 weekly history `0/3`、multi-day dry-run `1/3`。2026-07-08 已將 multi-day dry-run record 累積至 `3/3 ready`；weekly history 與 manual review / action-item rhythm 仍未完成。這個結果不代表正式 DB 已 confirm，也不代表 production scheduler 可啟用。

Working-copy smoke 會先確認 source DB 與 working-copy DB 不是同一路徑；若 working-copy DB 不存在，會以 `shutil.copy2` 從 source DB 複製一份，再只對 working-copy DB 執行 confirm smoke。預設 repeat 至少 2 次，用 event / outcome counts 檢查 idempotency；source DB 應維持 read-only。readiness evaluator 會彙總 source coverage、smoke report 與 dashboard availability；若未提供具名 owner 簽署的 `evidence-production-scheduler-approval.v1`，即使其他輸入沒有 blocking gap，仍會保留 `production_scheduler_approval_missing`／`invalid` 並維持 `production_scheduler_allowed=false`。只有該 artifact 的七項 checks 全部通過且未過期時，才可能回報 `operational_production`；正式排程前仍需人工 review `docs/06_qa/POST_V1_EVIDENCE_PRODUCTION_SCHEDULER_APPROVAL_CHECKLIST_2026_07_07.md` 的 source coverage、diagnostics report、backup path、rollback path 與 manual approval steps。

Live vs Research Gap linkage CLI 用來把 portfolio position source trace、Evidence Event / Outcome 與 saved source metadata 串成 gap observation。這是 evidence，不是 action；不修改持倉、不修改 Research Run、不做 lifecycle action，也不是完整實帳歸因。沒有真實交易與人工 override 記錄時，只能解讀為 research / simulated gap。Symbol / date fuzzy match 只會列為 low-confidence candidate，不會當作 confirmed evidence link。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_live_research_gap.py --observation-date 2026-07-03 --json-output
.\.venv\Scripts\python.exe scripts\capture_live_research_gap.py --observation-date 2026-07-03 --dry-run --json-output
.\.venv\Scripts\python.exe scripts\capture_live_research_gap.py --observation-date 2026-07-03 --confirm --db-path <working-copy-db> --json-output
```

Signal Decay Monitor CLI 用來檢查已保存 forward evidence 與 live gap observation 是否在近期相對長窗轉弱。v1 支援 `event_type`、`event_family`、`strategy_version`、`profile` scope；`factor_name` scope 尚未完成。Research Lab `Evidence Review` 已提供唯讀 Signal Decay 子頁。輸出的 `demote_candidate` / `retire_candidate` 只是 lifecycle proposed payload，不會自動修改策略狀態、策略版本或持倉。樣本不足時只會標示 `insufficient_sample`，不能解讀為策略失敗；缺 benchmark 或 live gap evidence 時會降低 confidence。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_signal_decay.py --observation-date 2026-07-03 --json-output
.\.venv\Scripts\python.exe scripts\capture_signal_decay.py --observation-date 2026-07-03 --scope event_type --scope-id recommendation_included --dry-run --json-output
.\.venv\Scripts\python.exe scripts\capture_signal_decay.py --observation-date 2026-07-03 --scope all --confirm --db-path <working-copy-db> --json-output
```

`capture_signal_decay.py` 預設 dry-run；`--confirm` 必須指定 explicit `--db-path`，疑似正式 DB 仍需額外 `--allow-production-db-confirm`。一般 QA 與人工審核應使用 working-copy DB。

Decision Quality Review CLI 用來建立週 / 月 / custom 流程覆盤。它只檢查 source trace、journal linkage、manual override、portfolio alert、large live gap、signal decay candidate 與資料品質是否已有覆盤證據；輸出的 score 是 process quality bp，不是投資能力、不是交易建議，也不是責備使用者。Research Lab `Evidence Review` 已提供唯讀 Decision Quality 子頁；CLI 與 repository 仍是資料來源。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_decision_quality.py --start-date 2026-06-01 --end-date 2026-06-30 --json-output
.\.venv\Scripts\python.exe scripts\capture_decision_quality_review.py --review-type weekly --start-date 2026-06-24 --end-date 2026-06-30 --dry-run --json-output
.\.venv\Scripts\python.exe scripts\capture_decision_quality_review.py --review-type monthly --start-date 2026-06-01 --end-date 2026-06-30 --confirm --db-path <working-copy-db> --json-output
```

`capture_decision_quality_review.py` 預設 dry-run；`--confirm` 必須指定 explicit `--db-path`，疑似正式 DB 仍需額外 `--allow-production-like-db`。缺 journal、缺 source trace 或 sample size 不足都只代表 review gap / warning，需要人工判讀。

V1.3 / V1.4 Evidence Operations weekly review CLI 用來把 scheduler readiness、Decision Quality、Signal Decay 與 action item 彙總成每週人工覆盤包，並可在 V1.4 以 append-only weekly review history 保存人工覆盤快照。它預設只讀並輸出 JSON 或 Markdown；`production_scheduler_allowed` 仍固定為 `false`。樣本不足時 status 會是 `coverage_only`，只能要求繼續累積 evidence，不可解讀成策略結論。Signal Decay 的 `demote_candidate` / `retire_candidate` 只會列為 `manual_lifecycle_candidates`，每筆 `apply_action=false`，不會自動修改策略版本。

```powershell
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date 2026-06-24 --end-date 2026-06-30 --db-path <working-copy-db> --json-output
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date 2026-06-24 --end-date 2026-06-30 --db-path <working-copy-db> --plan-action-items --json-output
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date 2026-06-24 --end-date 2026-06-30 --db-path <working-copy-db> --confirm-action-items --save-history --action-owner human --json-output
.\.venv\Scripts\python.exe scripts\build_evidence_operations_weekly_review.py --start-date 2026-07-01 --end-date 2026-07-04 --db-path <working-copy-db> --list-history --json-output
```

`--plan-action-items` 只預覽 open Decision Quality item 會形成哪些 action item，不寫入 DB。`--confirm-action-items` 才會 append-only 寫入指定 DB，且必須提供 explicit `--db-path`；CLI 會 canonicalize 實際 DB path 並比對 configured／環境 `DATA_ROOT` 與預設正式 root，故 `--data-root` 不可繞過 production-like DB 拒絕，也沒有 allow 旗標。正式 weekly review 要將 `--confirm-action-items --save-history --action-owner <owner>` 合併於同一次 working-copy 操作，讓 snapshot 保存 owner、planned action 與 created / skipped 結果。`--save-history` 會把當次 weekly review payload、hash、status、scheduler readiness 與 production scheduler disabled 邊界保存到 `evidence_operations_weekly_reviews`；`--list-history` 只讀取已保存歷史，缺 DB / table 時回 diagnostics，並在 config 初始化前完成純 path 解析，絕不建立 DB parent、log directory 或 SQLite 物件。一般覆盤應先用 `smoke_evidence_pipeline_working_copy.py` 的 copy/guard 建立 working-copy DB。

Research Lab `Evidence Review` 分頁在 V1.4 新增「覆盤歷史」子頁，用來唯讀檢查已保存 weekly review history 的週期、status、scheduler readiness、Decision Quality / Signal Decay 數量、manual lifecycle candidate 數量與 warnings。此子頁只讀 dashboard service，不建立週報、不寫 action item、不啟用 scheduler，也不自動套用任何 lifecycle action。

若 weekly history 保存在隔離 working-copy DB，主 UI 不會自行掃描或合併該 DB。可由具名 owner 建立外部 `approved-weekly-history-projection.v1` JSON，並在啟動 UI 前設定 `WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH` 為該檔案的絕對路徑；決策工作台只讀取其中 `status=approved_weekly_review`、具 `review_id`、`review_hash`、週期、`owner_role` 與 `approved_at` 的列，顯示其累積數。projection 必須固定 `formal_credit_authorized=false`，只供 UI 揭露 weekly Gate 進度，不寫入正式 DB、不授權 formal credit、不啟用 scheduler 或交易。

Workbench 的證據門檻摘要會另外列出 sidecar 中仍為 `pending_human_review` 的期數與日期區間（最多預覽前三期），並同時顯示 `formal_credit_authorized=false`。因此 `3/3` 是已觀測／具名核准 projection 的數量，不代表 pending 週期已核准，也不代表 Formal 或 production scheduler 已開啟。
若未設定該環境變數，Workbench 會在 warnings 與 weekly history 詳情明示 `approved_weekly_history_projection_not_configured`，並只計算正式 evidence DB 內可讀的 legacy review history；這不代表 projection 已自動核准，也不會把 pending sidecar 轉成 Gate credit。

若 sidecar 已累積 `pending_human_review` 期段，可先用下列唯讀命令產生具名 owner／reviewer 的交接輸入包：

```powershell
.\.venv\Scripts\python.exe scripts\build_evidence_weekly_approval_input.py `
  --sidecar-path <WEEKLY_COLLECTION_SIDECAR_DB> `
  --output-json <TEMP_APPROVAL_INPUT_JSON> `
  --markdown-output <TEMP_APPROVAL_INPUT_MD> `
  --owner-role <NAMED_OWNER_ROLE> `
  --reviewer-role <NAMED_REVIEWER_ROLE>
```

這個命令只對明確指定的 sidecar 做 SQLite `mode=ro`／`PRAGMA query_only=ON` 讀取，驗證
collection id、期間、來源路徑／SHA-256、payload 與錯誤欄位，並輸出
`evidence-weekly-approval-input.v1`。輸出中的 owner／reviewer 只是交接欄位；即使填入角色，
每列 `review_decision`、`reviewed_at` 與 `review_note` 仍需人工完成，packet 仍固定
`candidate_only=true`、`formal_credit_authorized=false`、`production_scheduler_allowed=false`、
`downstream_eligibility=none`、`write_performed=false`。不要把此檔案直接改名或送入
`approved-weekly-history-projection.v1`／Formal loader；人工完成審核後，必須沿既有 governed
path 另外產生相容的 approved projection。輸出路徑不可覆寫 sidecar、`twstock.db`，且 parent
directory 必須先存在；此流程不寫 sidecar、正式 Evidence DB、Registry 或 scheduler。

Report evidence boundary 固定為：This report is research evidence only. Close-to-close forward return is not executable live performance. No trading recommendation is produced.

#### 私人 Review 週報與歷史保存（2026-10-06）

已明示 `--personal-store-root <private-root> --personal-store-mode personal` 時，週報讀取此 root 下 `reviews/decision_quality.sqlite` 的審查紀錄，市場 Evidence/Gap/Decay 仍從 `--db-path <approved-working-copy-db>` 唯讀取得。私人庫不存在或尚無審查 table 時，顯示 `selected_review_store_missing`；不借用市場庫的舊 review。缺市場 decay 顯示 `market_decay_source_missing`，不能解讀成健康或完整。

預覽沿用上述日期與 `--json-output`，不加寫入旗標。要保存人工已核對的週報，須另外明示 `--save-history` 與隔離 working-copy 的 `--db-path`；歷史 payload、原來源 ID/hash、選取 store 路徑與週報 hash 保存於私人 Review DB。`--db-path` 此時仍是行情證據來源，不是私人輸出位置。保存後用相同私人 root/mode 加 `--list-history --json-output` 讀回並核對 `review_hash`。list 缺庫/table 僅回 diagnostics，不建目錄、不初始化 schema，也不回退 legacy。

JSON 的 `source_lineage` 保留原 review/decay ID/hash 與來源路徑；`source_snapshot_qualification=unknown`，不宣稱跨來源原子快照或歷史 PIT 資格。只配置 root 或 mode、空 root、路徑衝突、link/hardlink/sidecar 不合規均拒絕；請修正配置與來源，勿改 ACL 或關閉 guard。`legacy_read_only` 只能讀取原歷史；未配置這兩欄時沿原 legacy working-copy 流程。私人週報 reader 不會自動變成 action-item writer，`--confirm-action-items` 仍需獨立核准與已綁定 writer；這項接線不代表正式私人啟用、migration、scheduler 或自然週數完成。

### 9.9.2 V2.2 Weekly Review Runbook

V2.2 的固定三週人工覆盤格式與 working-copy 操作順序見 `docs/07_guides/V2_2_WEEKLY_REVIEW_RUNBOOK.md`。每週必填週期日期、資料 freshness、dry-run 狀態、warnings、reviewed / dismissed / follow-up、owner、working-copy DB path、`--save-history` 結果與下一步；少任何一項都不能計入三週 Gate。先以既有 copy/guard 建立隔離副本，再產生唯讀週報；取得明確人工核准後，在同一次 working-copy 操作使用 `--confirm-action-items --save-history --action-owner`，最後以 `--list-history` 唯讀核對。不要對正式 DB 保存 history；production-like DB 強制拒絕，沒有 `--allow-production-like-db` 可用。

截至 2026-07-12，Week 1 已完成並保存於隔離 working-copy，weekly history 為 `1/3 waiting_for_time`；multi-day dry-run 為 `3/3 ready`，scheduler 尚未獲核准且 `production_scheduler_allowed=false`。這是當日狀態，不是目前進度；原始週期證據見 [V2.2 Week 1 QA](../09_archive/V2_2_WEEK1_REVIEW_2026_07_12.md)。10/09 最新排程 QA 記錄 10/04 weekly collection 為 `pending_human_review`，這是 sidecar collection 狀態，不能取代三週人工 review history。不可建立 V2.2 formal closeout；replay、fixture、raw scheduled report、單次 smoke 或手動補表都不能補足 Week 2 / Week 3。三週紀錄完成後，仍需人工完成 backup / rollback / recovery 演練與 scheduler approval package；日後若 scheduler 獲准，也只能保存 evidence，不得自動交易或套用 lifecycle action。

### 9.9.3 Evidence Review Manual Smoke / Multi-day Dry-run

Evidence Review UI 完成後，正式 scheduler 前仍需要人工 closeout：

- `docs/06_qa/POST_V1_EVIDENCE_REVIEW_UI_SMOKE_CHECKLIST_2026_07_12.md`：人工檢查 Forward Evidence、Live vs Research Gap、Signal Decay、Decision Quality、boundary banner、empty / degraded / insufficient sample states、read-only guarantee 與無買賣建議語言。
- `docs/06_qa/POST_V1_EVIDENCE_PIPELINE_MULTI_DAY_DRY_RUN_RECORD.md`：記錄 3-5 個交易日的 data update status、source coverage、dry-run pipeline、working-copy confirm smoke、events / outcomes / summary / warnings / blocking gaps、dashboard review 與人工 decision。
- `docs/06_qa/POST_V1_EVIDENCE_SCHEDULER_APPROVAL_SOP.md`：描述 Manual run → Multi-day dry-run → Working-copy confirm smoke → Dashboard review → Manual approval checklist → Production scheduler design → explicit approval 後才 implementation。

這些文件是 production scheduler 前的 QA scaffold；目前只允許受控 market data quick update、read-only freshness 與 evidence dry-run 範圍。現有 Windows Task Scheduler 會先執行非 UI 快速資料更新，再跑 data freshness check 與 evidence pipeline dry-run，不是 production confirm scheduler。任何 production confirm 未來都需要 backup、rollback、diagnostics 與 explicit human approval；scheduler 不得自動 lifecycle action，也不得自動交易。

### 9.9.4 Evidence Scheduled Dry-run Wrappers

`scripts/scheduled/` 提供 safe scheduled wrappers，用於每日自動產生「可人工檢查」的 freshness 與 evidence dry-run 輸出。PowerShell `.ps1` 註冊路徑曾被 local execution policy 擋住，因此目前採 CMD wrapper；aggregate 保留 Windows 內建 `schtasks.exe`，Paper 專用原地更新與完整唯讀查詢使用現有 Python／pywin32 Task Scheduler COM，不需要修改 execution policy。

2026-10-02 已實際讀回 21 個 exact root tasks，所有 Exec WorkingDirectory 指向 repo。Paper／ML 盤前已改為具時區的台北 08:25（UTC 00:25；前一個 Pacific 日期 PDT 17:25／PST 16:25），並恢復 Enabled=true。Windows 可將 boundary 正規化為等值的 Pacific offset；核對 aware UTC instant 與每日排程語意，不以顯示字串相同作標準。timeout 保留實查值（Paper PT72H／ML PT2H），這不代表歷史 `0xC000013A` 的原因已查明。完整 before／after 與受控執行見[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。

```cmd
scripts\scheduled\register_baldr_scheduled_tasks.cmd dryrun
scripts\scheduled\register_baldr_scheduled_tasks.cmd register
scripts\scheduled\register_baldr_scheduled_tasks.cmd register-all
scripts\scheduled\query_baldr_scheduled_tasks.cmd
scripts\scheduled\unregister_baldr_scheduled_tasks.cmd unregister
```

aggregate `register` 會處理 18 個每日 task；`register-all` 會在同一個受控
操作中處理這 18 個每日 task 與每週日 collection task。完整 Windows Task Scheduler
清冊另有兩個每日 task 不由 aggregate path 接管：`baldr-ml-allocation-forward-daily`
使用獨立的 pinned UTF-16 XML 定義；`baldr-recommendation-calibration-learning-banktaiwan-shadow-daily`
使用 BankTaiwan 專用 registration wrapper。現有主機清冊因此是 20 個每日 task
加 1 個 weekly task，共 21 個。兩個 aggregate 模式都會先
檢查自己選定的 `.cmd` wrapper 是否存在，缺檔時在呼叫 schtasks 前停止，不會留下
指向不存在檔案的 task。執行前仍須先以 dryrun 檢查 repo root、時間與 action，執行後
再用 registration inspector 與真實 terminal history 驗證。不要為了讓 aggregate 數字
符合完整清冊而重註冊或覆蓋這兩個獨立 task；清冊差異只描述管理範圍。

Formal input producer 可透過單項排程入口受控管理，也屬於上述 18 個 aggregate 每日 task；
若只需操作這一項，可使用獨立入口，避免重註冊其他 task：

```cmd
scripts\scheduled\register_formal_input_producer_task.cmd dryrun
scripts\scheduled\register_formal_input_producer_task.cmd register
```

這個入口只建立／更新 `baldr-formal-input-producer-daily`，aggregate `register`／
`register-all` 也會管理它；入口並要求 Windows timezone ID
為 `Pacific Standard Time`。觸發時間為本機 21:25；PDT 對應台北 12:25，PST 對應台北
13:25，兩者都在 Rule 09:00–13:30 capture window。其他 timezone 直接 fail closed，
避免 Windows Task Scheduler 的 local time 被誤當成台北時區。它不接受 clock override、
人工 confirmation、交易或 broker 參數；candidate／blocked 結果仍依 wrapper status
回報，不計入 Formal 3/3。註冊入口同時套用最長 1 小時與
`MultipleInstancesPolicy=IgnoreNew`；目前 Task Scheduler 登記為
`Interactive only`，且電池供電不啟動、切換電池會停止，所以必須由已登入的 Windows
使用者承接執行與 status 觀測，不能當成無人值守服務。

目前 Windows Task Scheduler task：

- `baldr-ml-allocation-forward-daily`：獨立每日 task，具時區的 Asia/Taipei 08:25 喚醒，wrapper 等待真實 08:30，08:35 後 fail closed；只產生 repository-isolated candidate shadow，不授予 formal／production／broker credit。固定使用 `output/v4_ml_daily_derived_shadow_real_v2`、repository Paper state、離線 calendar cache 與 V2 release manifest hash。部署前執行 `run_ml_allocation_forward_daily.cmd preflight`；此模式不抓網路、不等待、不產 config 或啟動 child，只核對路徑與固定模型 hash。既有 task 僅原地更新與讀回，不以整份 XML 覆蓋其 principal／settings；aggregate 不接管它。回復使用同一 exact task 的 before XML，重新讀回原 trigger／settings／Enabled，不以刪除 task 作 rollback。正式當日 producer 仍須另通過 calendar、archive、config 與 cutoff 防護。

- `baldr-recommendation-calibration-learning-banktaiwan-shadow-daily`：獨立每日 task，本機 05:50，由 `register_banktaiwan_recommendation_learning_task.cmd` 專用管理；aggregate `register`／`register-all` 不會建立、更新或移除它。它執行 BankTaiwan research-only learning shadow；source、cost lane、candidate 與自然 evidence 仍依各自 receipt 判讀，不授予正式 Recommendation、promotion 或交易權限。

- `baldr-data-update-quick-daily`：每日本機時間 04:20，走非 UI 快速更新路徑，補最近工作日窗口的 TWSE / TPEX 每日股價、大盤、產業、券商分點、SQLite 同步與必要的技術指標增量；輸出位於 `<OUTPUT_ROOT>/scheduled/data_update_quick/`。若 TWSE 的 `ALL` 與 `ALLBUT0999` 都精確回覆「很抱歉，沒有符合條件的資料！」，該日會列入 `no_data_skipped_dates`，task 會以 `passed_with_warnings` 記錄警告並繼續同步；HTTP、timeout、解析錯誤、未來日期或其他非完整文案回覆仍是 `failed`。若 TPEX 當日或窗口內日期抓取失敗，task 會繼續可完成步驟並以 `passed_with_warnings` 保存 `TPEX 每日股價缺少日期：YYYYMMDD`，不再把只有既有 skipped CSV 的情況誤判為完整成功。
- 快速更新 wrapper 預設使用 10 個官方交易日，並明確啟用 `--reverify-unknown-legacy-industry-dates`；Python runner 的 `store_true` 選項預設為 false，單獨執行不會重查。這個日期選項只重查請求窗口內沒有有效 projection marker 的 legacy 產業日期；窗口外 unknown rows 不重抓，已有有效 marker 的日期略過，來源失敗仍保留 unknown 並回報 failed。nullable parser 沒有獨立旗標：方向、漲跌點數、漲跌百分比全缺值時保留三欄 NULL；方向空白而任一變動值存在（包括 0 或 0.00）、一欄缺值一欄有值，或未知非空方向，即拒絕該回應。明確 `+`／`-` 方向搭配數值 0 仍是有效數值；收盤指數缺值、缺日期證據、日期不符或表格列無效仍 fail closed。TWSE capture 被接受後，狀態先標為 `pending_csv_sqlite_readback`；只有 CSV 與 SQLite 對應日期列完成獨立精確 readback 並寫入 projection marker 後，才標為 `committed_after_exact_csv_sqlite_readback`。Capture receipt 的 `available_at`／`published_at` 保持 null、`historical_pit_eligible=false`；現在取得的官方回應不等於歷史決策時間可取得證明。
- 受控補跑時先讀 Task 的 Enabled／State／Action／LastRun，確認同一資料源沒有 active writer，並重查原 capacity／reservation gate；只啟動既有 Task，保留 wrapper 的 10 日窗口與 optional source 重試。等待同一 run terminal 後核對 Task exit、status／receipt、capture、CSV 與 SQLite 日期列；若 Quick 尚未 terminal 或日期仍 pending，不能接 Freshness。手動觸發的 LastRun 與 receipt 是人工補跑證據，不代表自然 04:20 已驗收；Freshness 應在同次 Quick terminal 後再檢查，且須讀當日 status／expected date，不沿用前一日 latest。
- `baldr-data-freshness-check-daily`：每日本機時間 05:00，唯讀檢查 SQLite / `DATA_ROOT` freshness，只寫 `<OUTPUT_ROOT>/scheduled/data_freshness/latest_status.json` 與 logs。除了 SQLite `daily_prices` / `technical_indicators` 最新日期，也會反查同一最新日的 `daily_price/YYYYMMDD.csv` 與 `daily_price_tpex/YYYYMMDD.csv`；若 SQLite 最新但 TPEX 原始日檔缺失，狀態會是 `degraded`。freshness 也會讀取最近一次 `data_update_quick/latest_status.json`；若快速更新為 `failed`、status 檔遺失或 status 日期未達預期工作日，即使資料年齡仍在容許範圍，freshness 仍會是 `degraded` 並列出相應 warning。
- 若正式 `OUTPUT_ROOT` ACL 不允許 freshness status／log 寫入，owner 可在受控 Task Scheduler 執行環境明確設定 `BALDR_FRESHNESS_STATUS_PATH`；未設定 `BALDR_FRESHNESS_LOG_PATH` 時 wrapper 會將 `.log` 放在 status path 旁。UI 另設定 `DATA_FRESHNESS_STATUS_ARTIFACT` 讀取該明確 status 檔。這只是把 read-only 觀測輸出導到已核准可寫路徑，不會建立或修改 DB、source acceptance、Evidence、Formal 或 broker 權限；未設定覆寫時仍使用既有 `<OUTPUT_ROOT>/scheduled/data_freshness/`。
- `baldr-recommendation-snapshot-daily`：每日本機時間 05:10，在 freshness check 後產生一筆 research-only recommendation snapshot，保存到 `<OUTPUT_ROOT>/recommendation/runs/`，並寫 `<OUTPUT_ROOT>/scheduled/recommendation_snapshot/latest_status.json`。status 會列出 `result_id`、`recommendations_count`、`screening_matrix_rows`、`why_not_payload_rows`、`liquidity_gate_payload_rows`、`writes_recommendation_result=true`、`writes_evidence_db=false`、`auto_trading=false` 與 `lifecycle_action=false`。它只保存推薦結果供 evidence dry-run 與 UI 判讀，不寫 production evidence DB、不改 portfolio、不自動交易、不自動 lifecycle。
- `baldr-evidence-pipeline-dry-run-daily`：每日本機時間 05:15，只執行 evidence pipeline `--dry-run`；scheduled wrapper 會把已解析的 `DATA_ROOT`、`OUTPUT_ROOT` 與 `DB_PATH` 明確傳給內層 pipeline，避免環境覆蓋時讀到另一套預設來源。scheduled status 會同時承接 freshness 與 pipeline `overall_status`。子程序 exit code 為 `0` 只代表正常完成並產生報告；只要 pipeline 為 degraded、warnings_count 大於 0、blocking gaps 非空，或 freshness 不是 passed，`latest_status.json` 的 `status` 就不會誤標為 passed。因 05:10 已先保存當日 recommendation snapshot，dry-run 可讀到最新 recommendation payload（含 screening matrix / why-not / liquidity gate payload，若當日推薦流程有產出）。輸出位於 `<OUTPUT_ROOT>/scheduled/evidence_pipeline_dry_run/`。2026-07-06 後，`latest_status.json` 會另外保存 pipeline summary 摘要欄位，例如 `pipeline_overall_status`、`pipeline_diagnostic_codes`、`source_coverage_warnings`、`recommendation_screening_matrix_available`、`recommendation_exclusion_payload_available` 與 `source_coverage_basis`；2026-07-09 後也會保存 `pipeline_warning_counts`、`pipeline_warning_unique_count` 與 `pipeline_warning_top_counts`，對應 markdown report 的 `Warning Summary` / `Warning Breakdown`，方便 read-only morning report 直接判讀 V1.7 payload readiness、warning occurrence 總量與 warning 分布。新版 status 另分開保存 `pipeline_natural_maturity_warning_counts`、`pipeline_actionable_warning_counts`、`natural_maturity_only` 與 `manual_action_required`；只有非自然 warning、error、blocking gap、缺少 pipeline summary 或 freshness 非 passed 才列為需人工處理，`insufficient_future_data` 仍是自然成熟度，不應以補跑或人工填值消除。安全旗標固定為 `dry_run=true`、`confirm=false`、`writes_evidence_db=false`、`production_scheduler_allowed=false`。證據覆盤的「排程狀態」會把 pipeline warnings 與 freshness warnings 分開顯示；若看到 `freshness warnings: 無` 但 `pipeline warnings` 有數量，代表資料新鮮度檢查沒有 warning，但 evidence dry-run 仍有來源品質或事件品質 warning。這些欄位只來自同次 dry-run stdout，不額外重跑 pipeline。
- `baldr-evidence-pipeline-dry-run-daily`：每日本機時間 05:15，只執行 evidence pipeline `--dry-run`；scheduled wrapper 會把已解析的 `DATA_ROOT`、`OUTPUT_ROOT` 與 `DB_PATH` 明確傳給內層 pipeline，避免環境覆蓋時讀到另一套預設來源。scheduled status 會同時承接 freshness 與 pipeline `overall_status`。子程序 exit code 為 `0` 只代表正常完成並產生報告；只要 pipeline 為 degraded、warnings_count 大於 0、blocking gaps 非空，或 freshness 不是 passed，`latest_status.json` 的 `status` 就不會誤標為 passed。因 05:10 已先保存當日 recommendation snapshot，dry-run 可讀到最新 recommendation payload（含 screening matrix / why-not / liquidity gate payload，若當日推薦流程有產出）。輸出位於 `<OUTPUT_ROOT>/scheduled/evidence_pipeline_dry_run/`。2026-07-06 後，`latest_status.json` 會另外保存 pipeline summary 摘要欄位，例如 `pipeline_overall_status`、`pipeline_diagnostic_codes`、`source_coverage_warnings`、`recommendation_screening_matrix_available`、`recommendation_exclusion_payload_available` 與 `source_coverage_basis`；2026-07-09 後也會保存 `pipeline_warning_counts`、`pipeline_warning_unique_count` 與 `pipeline_warning_top_counts`，對應 markdown report 的 `Warning Summary` / `Warning Breakdown`，方便 read-only morning report 直接判讀 V1.7 payload readiness、warning occurrence 總量與 warning 分布。新版 status 另分開保存 `pipeline_natural_maturity_warning_counts`、`pipeline_actionable_warning_counts`、`natural_maturity_only` 與 `manual_action_required`；只有非自然 warning、error、blocking gap、缺少 pipeline summary 或 freshness 非 passed 才列為需人工處理，`insufficient_future_data` 仍是自然成熟度，不應以補跑或人工填值消除。安全旗標固定為 `dry_run=true`、`confirm=false`、`writes_evidence_db=false`、`production_scheduler_allowed=false`。證據覆盤的「排程狀態」會把 pipeline warnings 與 freshness warnings 分開顯示；若看到 `freshness warnings: 無` 但 `pipeline warnings` 有數量，代表資料新鮮度檢查沒有 warning，但 evidence dry-run 仍有來源品質或事件品質 warning。這些欄位只來自同次 dry-run stdout，不額外重跑 pipeline。產業指數更新的完整性比較以請求日前最近一個有效交易日的指數集合為基準，避免歷史停用／改名指數造成固定 false-positive；Portfolio alert 的 `portfolio_alerts_chip_data_missing:<stock_code>` 則是持倉代號與目前籌碼來源需要人工核對的資料品質問題，不得由 wrapper、dry-run 或 Codex automation 自動改碼。
- `baldr-evidence-working-copy-smoke-manual`：不建立每日 task；只保留 manual-only script，必須人工指定 source DB 與 working-copy DB，且不得寫 source DB 或 default `DATA_ROOT/sqlite/twstock.db`。

Codex app 另外有一個 read-only daily automation：`baldr scheduled evidence morning report`。它每日本機時間約 05:30 只查詢 Task Scheduler 狀態、`latest_status.json`、最新 data update / freshness / evidence dry-run report 與必要 log 區段，並產生繁體中文摘要；它不重新執行 data update / freshness / evidence pipeline、不建立或修改 Windows Task Scheduler task。

另有已更新的 `paper` heartbeat「晚間學習與 Paper 排程驗收」，每天約 06:20（`America/Los_Angeles`）唯讀檢查 Paper／ML 排程及同次 run receipts。兩個 Codex heartbeat 都採美西本地時間，依時區規則跨夏令／標準時間切換，不應手動換成固定 UTC trigger；TOML readback、task/run identity 與 prompt 內要求的 immutable receipt/hash 綁定需同一 run。通知僅針對有意義變化，例行無變化保持安靜。這兩項 automation 不改 Windows Task Scheduler，不重跑 producer、訓練或 Paper action。

目前 21 個 Task 與兩個 Codex heartbeat 的唯讀查核步驟見[全排程稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。早期 Evidence dry-run 的 QA 收據見 [2026-07-12 scheduled pipeline QA](../09_archive/POST_V1_SCHEDULED_EVIDENCE_PIPELINE_QA_2026_07_12.md)；舊 PowerShell execution policy block 歷史見 [2026-07-12 QA](../09_archive/POST_V1_EVIDENCE_SCHEDULED_DRY_RUN_QA_2026_07_12.md)。

這些 wrappers 中只有 `baldr-data-update-quick-daily` 會寫 market data CSV / SQLite；evidence dry-run 與 Codex read-only 摘要不寫 production evidence DB、不跑 UI、不讀 UI state、不做 portfolio / lifecycle action，也不代表任何訊號或事件類型已被證明有效。

### 9.9.5 DEV-70 Development ML Data Inventory & Experiment Runner

DEV-70 提供獨立、Sanitized、Machine-Readable 的 ML 資料盤點 CLI (`scripts/inspect_development_ml_data_inventory.py`) 與 ML 實驗執行 CLI (`scripts/run_development_ml_experiment.py`)。其所有輸出皆限定於 TEMP 根目錄 (`validate_development_output_root`)，絕不寫入正式 DB、不改寫 Formal Acceptance 狀態，也不授權 Production Promotion。

1. **Development ML Data Inventory Inspection CLI**:
   盤點核心 20 個特徵、4 個標籤、MOPS 季報時間軸 (Availability Gate)、Broker/Fundamental 候選族群與 DEV-69 TWSE 微觀結構 5 個 Source 的訓練狀態與遮蔽原因。
   ```powershell
   .\.venv\Scripts\python.exe scripts/inspect_development_ml_data_inventory.py --manifest C:\Temp\technical_analysis_development_output\generations\terra-v0-canonical-2025-dev-20260714\manifest.json --dataset C:\Temp\technical_analysis_development_output\generations\terra-v0-canonical-2025-dev-20260714\dataset.json --output-root C:\Temp\technical_analysis_development_output
   ```

2. **Development ML Experiment Runner CLI**:
   執行具備不可變 Contract 的隔離 ML 開發實驗，支援特徵組合 (Feature Pack: `core_20`, `technical_only`, `price_only`, `price_technical`)、模型家族對比 (`linear_logistic`, `hist_gradient_boosting`) 與超參數 Grid 實驗。
   ```powershell
   .\.venv\Scripts\python.exe scripts/run_development_ml_experiment.py --manifest C:\Temp\technical_analysis_development_output\generations\terra-v0-canonical-2025-dev-20260714\manifest.json --dataset C:\Temp\technical_analysis_development_output\generations\terra-v0-canonical-2025-dev-20260714\dataset.json --output-root C:\Temp\technical_analysis_development_output --experiment-id exp-ablation-technical-v1 --feature-pack technical_only
   ```

安全旗標恆定為：`formal_oos_allowed=false`, `production_blend_alpha_bp=0`, `promotion_allowed=false`。


**報告匯出按鈕**：
- 在「實驗摘要」設有「匯出 Excel 報告」按鈕（僅在單股回測成功後啟用）。
- 在「批次結果」設有「匯出批次 Excel」按鈕（僅在批次回測成功後啟用）。
- 在「推薦回放」設有「匯出回放 Excel」按鈕（僅在推薦組合回測成功後啟用）。
- **安全設計**：所有匯出皆在背景線程（`TaskWorker`）執行，防止 UI 卡死，並採用臨時檔寫入後 `os.replace` 原子替換；替換失敗時既有報告保持不變。報告使用執行結果與參數快照，不重跑策略或摘要績效；equity curve 可接受 `日期`、`date` 或日期 index。若元數據缺失，會在「資料完整性」警示中顯示中文欄位名並保留原始代號，例如「資料截止日期（data_as_of_date）」；系統不以目前 UI 值或預設常數代填。

Registry 比較只使用已保存的 metadata、equity curve 與 benchmark_results，不重新抓取目前資料。資料 fingerprint、execution 或 sizing 不同時會標示為「不可直接比較」，並以中文原因顯示如「資料指紋不同」「成交假設不同」「部位 sizing 模式不同」；期間、Universe 或成本不同時會標示為「需謹慎比較」，並以「日期區間不同」「Universe 股票池不同」「交易成本模型不同」等原因提醒，不應直接做優劣排名。畫面中的參數、指標、Regime 與 Benchmark 會先以摘要卡顯示重點，並以 A / B / C 代號對應長 run 名稱；完整資料仍來自同一批已保存 run metadata，不重新計算。標準化權益只在共同日期交集上把每個 run 的第一筆淨值設為 10000；沒有共同日期時不補值、不推估，也不重新計算回測。Registry-based Promote 會先做 Registry Gate，通過後才建立策略版本。

策略回測頁左側設定面板頂部有「收合左側設定」按鈕，可暫時隱藏設定面板，讓右側結果分頁、Registry 比較與圖表取得更多橫向空間；收合後標題列會顯示「展開左側設定」作為恢復入口。此操作只改變 UI 空間配置，不改變目前輸入參數、已選 run、回測結果或保存狀態。

固定組合目前的 Registry 保存粒度是每檔股票的 per-stock run，metadata 會標記為 `fixed_basket_stock` 以保留固定組合來源，並沿用該檔回測產生的 factor records 生成 `factor_snapshot` / `factor_contributions`。完整固定組合層級的現金帳、再平衡、未成交、Liquidity / Gap 風險揭露仍未建成，不應把 per-stock 保存結果解讀為完整可成交的固定組合績效；Month 3 v1 的完整 portfolio credibility 揭露集中在推薦組合回放。

### 9.10 推薦回放

目前預設 `next-session-open.v2`。T 收盤建立委託，下一個有有效開盤且可交易的 session 才成交；停損停利在收盤確認後，下一有效開盤退出。持有天數從實際進場日起算曆日，到期收盤建立退出訊號。UI 使用所選手續費／滑價、30 bp 賣出稅與 1000 股整張；API 未指定成本仍會揭露 `unspecified_cost_assumptions`。撮合層會以獨立 `ConservativeFillPolicy` 檢查已知成交量參與率與開盤漲跌停，並將請求股數、實際成交股數、未成交股數與 `filled`／`partially_filled`／`unfilled` 狀態寫入診斷；缺已知成交量時不猜測成交量。

期末 `position_status=open`、空 exit date 與 open_position_count 表示未平倉；ending_equity 包含估值，realized_pnl／unrealized_pnl 分列，不能將期末部位當完成交易。未成交會保留 missing_open_or_suspended、end_of_data、現金／已知量不足、開盤漲跌停等原因；partial fill 會保留 request／fill 差額；cancelled 是部分結果。gap_risk 使用訊號收盤至實際成交開盤，Equal Weight benchmark 使用同一批凍結推薦、成本及 sessions。這仍是日頻保守撮合，沒有逐筆委託簿、bid/ask 或真實 fills。

建議從推薦頁按「送 Research Lab 推薦回放」載入配置。這個入口會帶入當下 Profile / Config，並在歷史期間按設定重新產生推薦；它不是只回測今日推薦名單。

可設定：

- 每次推薦檔數
- 每期候選上限
- 持有天數
- 每週重播或只跑一次：每週重播會在回放期間定期重新產生推薦名單，只跑一次則只用起始日名單。
- 等權或分數加權：等權配置平均分配資金，分數加權會讓高分股票取得較高權重。

執行後可保存到 Research Run Registry。結果頁摘要只顯示一次，並用段落解釋總報酬、最大回撤、交易檔數、資金使用、交易假設、虧損交易占比、最拖累股票、Sharpe / Sortino 與 Monte Carlo P05 / P50 / P95。資金使用代表期間投入金額，不等同最終淨值；Monte Carlo P05 / P50 / P95 分別是偏弱、中位與偏強情境，不是保證績效。期間明細、個股貢獻與交易紀錄在結果頁內部分頁查看，避免被底部區域吃掉。若要比較 Profile 或判斷升降級，應以訓練期間先提出候選調整，再用獨立驗證期間或 walk-forward 驗證凍結邏輯，避免用同一段未來資料同時調參與宣稱有效；`ProfileReplayComparisonService` 的驗證期必須晚於訓練期，驗證結果只輸出人工 lifecycle candidate，不會自動降級、退休或刪除策略版本。

#### Legacy 同日收盤結果（legacy-same-day-close.v1）

以下僅描述顯式選用的歷史 legacy 路徑；其成交／風控與成本假設不能套用到目前 v2 結果，也不宣稱符合新時間線精度。既存 run 不重算。

歷史載入、刪除與 legacy Promote 能力仍保留在舊 repository 邊界；新版 Cross-run Comparison 與 Registry-based Promote Gate 以 Registry run 為準。結果 details 會包含 `portfolio_credibility`、`unfilled_orders`、`cash_ledger`、`weight_exposure` 與 `gap_risk`：若推薦股票在回放視窗內沒有可用價格列，會以 `missing_price_rows` 記錄為未成交，而不是靜默跳過；若呼叫端提供 `max_participation_rate`，系統會用進場日成交股數與收盤價估算可參與金額，配置金額超過時以 `liquidity_limited` 記錄為未成交。回放現在會在建立 holding 前檢查可用現金，現金不足時以 `cash_limited` 記錄為未成交；`cash_ledger` 由這個現金 gate 流程產生買進、賣出與 `ending_cash`。若呼叫端提供 fee / tax / slippage bps，成本會套用到買賣現金流、ledger breakdown 與 `total_transaction_cost`；未提供時維持無成本回放。若呼叫端提供 `lot_size`，配置金額會依進場價向下取整為可成交整股股數，買不起最小交易單位時以 `lot_size_limited` 記錄為未成交。期間持倉的 `allocation_weight` 代表推薦配置的目標權重，`actual_allocation_weight` 代表整股 sizing 與 cash gate 後的實際可成交權重；`weight_exposure` 會依每個再平衡日彙總目標權重、實際權重、未成交權重與殘餘現金權重。若歷史資料含「開盤價」，`gap_risk.records` 會列出每筆 holding 的 `entry_close_price`、下一個可用交易日 `next_open_price`、`gap_pct`、`gap_direction` 與 `severity`，用來揭露同日收盤成交假設在隔日開盤可能遇到的跳空風險。V1.2 details 另含 `rolling_risk_metrics`、`microstructure_preflight` 與 `relative_attribution`：rolling risk 只讀已產生 equity curve / holdings；microstructure preflight 只檢查歷史資料內可選的處置股、分盤交易、全額交割、漲跌停鎖死與除權息欄位，缺欄位時揭露 missing source；relative attribution 只在 history 提供 benchmark / industry / concept 參考欄位時產生相對報酬。`portfolio_credibility` 仍會揭露同日收盤成交、再平衡現金重用限制、成交量 / Liquidity 與 Gap 限制；目前仍未建零股、委託簿撮合、買賣價差或 gap 實際成交模型，`gap_risk`、microstructure 與 attribution 只做診斷，不會改變 PnL、成交價、cash ledger 或 sizing。這些 warning 應先讀完，再判讀回放績效。結果仍依成交與推薦回放假設，不等同實盤。

## 10. 持倉管理

在持倉頁「分帳查看」選手動登錄、聲明研究或 Paper。三帳各用自己的資料與總值；手動登錄未核券商成交，聲明成本只供研究，Paper 非實盤績效。切聲明／Paper 時不顯示手動帳金額卡，沿原分頁核對資料。手動帳成本／已實現損益為毛額，已記錄費稅另列；估值日依同列原報價，資料更新時鐘不等於估值日。缺價格、日期未知／異日／未來、或價格與同列來源失配，市值顯示未知；前值、滑價、換手率與集中度缺件不補零。

選持倉後按「個股研究」沿同股原來源，未驗原結果維持未連結，不能借今天結果補舊身份。聲明列可看估值日，明細顯示評估日與聲明成本；過期、缺件或沒有精確健康資料時不能判安全。刷新取消／失敗保留上次資料並明示未確認最新。中央 MainWindow 已將選定 store 的 route 與 paths 注入 PortfolioService、Declared store 及 Paper readiness／weekly query-only readers；B09 初始交接中「待中央接線」是較早時點，後續有限接線與 P2／M03 readback 範圍見 [B09 QA](../06_qa/BALDR_B09_PERSONAL_PORTFOLIO_20261006.md)、[P2／M03 integration receipt](../06_qa/BALDR_SECOND_WAVE_INTEGRATION_20261006.md) 與[架構補記](../01_architecture/system_architecture.md)。這不表示 Paper trade-ledger／benchmark／daily producers 全鏈完成，也不代表正式私人資料啟用、migration 或排程已獲授權；未接入／失效時仍檢查主程式 service composition，不回退舊資料或自動 migration。

### 10.0 使用者聲明持倉研究（user_declared）

「持倉管理」右側的「聲明持倉研究」是獨立的 research-only lane，專門保存使用者
自行聲明的股票、整數股數、Decimal 聲明成本、聲明日期與研究假設。它與右側
「Paper Portfolio」分頁分開：這裡不是券商成交、不是已驗證 Paper entry，也不會把
聲明資料猜配到正式 Portfolio identity。資料以 append-only JSONL 保存於
`<OUTPUT_ROOT>/portfolio/user_declared_holdings.jsonl`；每筆 holding 以
`holding_id + revision_number` 精確識別，修訂與封存都保留歷史 revision。

#### 操作步驟

1. 執行 `.\.venv\Scripts\python.exe ui_qt\main.py`，進入左側「持倉管理」，再切到
   「聲明持倉研究」分頁；研究頁內容不足時可使用頁內垂直捲動。
2. 先按「展開新增／修訂表單」，再輸入股票代號、整數股數、聲明成本、聲明日期；備註與
   研究假設可選填。成本請輸入十進位文字，例如 `612.50`；核心服務不接受 binary `float`。
   沒有研究假設時，研究動作會維持「待確認」。
3. 按「新增保存」。保存成功後，畫面會以背景 worker 重新讀取並自動定位剛保存的
   `holding_id／revision 1`。同一 portfolio 的同一股票已有 active holding 時，請選取
   該列按「修訂保存」，不可再建立第二個 active identity。
4. 修改欄位後按「修訂保存」；系統使用目前顯示的 exact revision 做 CAS 檢查。若另一個
   caller 已先修訂，畫面會拒絕保存，請重新讀取後再編輯。按「封存選取」只停止 active
   research view，不刪除歷史 revision；需要再次研究時可建立新的 holding identity。
5. 以「評估日期」選擇目前或歷史研究日，再按「重新讀取研究」。刷新在背景執行，畫面
   會保留最近一次可信結果；快速連按時只保留最新日期／generation。關閉 Portfolio 時，
   worker 只做合作式取消並自然收尾，不強制終止正在讀檔的執行緒。

#### 來源、參數與結果判讀

- 預設市場來源是 `TWStockConfig` 的 `daily_price_dir`（若未提供則使用
  `<DATA_ROOT>/daily_price`）CSV；它只讀取不修改原始日價。來源 row 會保留檔名、原始
  bytes SHA-256、資料日與本機看到檔案的時間。檔案 mtime 只是本機觀測，不是官方
  availability custody，因此歷史日研究可能安全降級為未知。
- 預設 condition／Advice 來源只讀取已保存的 `RecommendationResultDTO` runs，並透過既有
  `PortfolioConditionMonitor` 對照 regime、score 或明確停損／停利規則。聲明日以前的
  baseline 與評估日的 current 必須是不同保存結果，且 profile、profile version、score
  config identity 相同；缺 baseline、只找到一個結果、結果不是獨立 snapshot 或 identity
  不同時，動作維持「待確認」，不會自我比較一份 current 結果。
- `評估日期` 不得晚於目前台北日。歷史日必須明確提供同一台北日的 cutoff；source 的
  `as_of_date` 不得晚於評估日，`available_at` 不得晚於 cutoff，來源品質、source ID 與
  `sha256:<64 hex>` snapshot hash 也必須通過檢查。資料不完整、過期、future、hash／品質
  不合約或 availability custody 不足時，畫面顯示「資料不足／未知」與原因，不把未知當
  成 0 或可執行建議。
- 主表以精簡中文顯示「持有／減碼候選／退出候選／待確認」、「可檢視／待確認」與帳面
  變化；完整 `Entry lineage`、`Fill`、source trace 與原始 action 可在「查看技術詳情」核對。
  `可供研究檢視` 只表示本次市場／condition 來源完整且研究假設可讀；`持有（研究建議）`、
  `減碼候選（研究建議）`、`退出候選（研究建議）` 分別是既有 monitor 的 valid／warning／
  invalid 映射。若只有價格／成本，價格本身不會產生 HOLD，結果一定是「待確認」。
- 表格的「帳面變化（資訊）」是 `目前價格 × 聲明股數 − 聲明成本 × 聲明股數`，僅為
  Decimal mark-to-declared-cost；不含手續費、稅、滑價或資金流，也沒有 realized PnL。
  研究 row 的 `Entry lineage=unproven`、`Fill=not_provided`、`Research only=是` 應與
  結果一起閱讀；來源 hash、revision、日期與 blocker 可在「查看技術詳情」核對。

#### 安全限制與排錯

- 這條 lane 固定 `research_only=true`、`formal_credit=false`、`broker_execution=false`、
  `auto_action_allowed=false`，並排除 calibration／effectiveness cohort。它不寫正式
  Portfolio trade、Paper ledger、Evidence credit，不呼叫 broker、不自動調倉、不自動下單。
- `缺少目前價格`／`目前價格已過期`：先確認指定評估日前存在唯一日價 row 與正確檔名；不要
  用今天價格回填歷史日。
- `缺少 condition／Advice 來源`、`沒有可追溯的研究規則` 或 `研究規則缺少可比較的目前
  訊號`：確認 Recommendation runs 含同股聲明日前 baseline 與評估日 current，且兩者
  profile／version／score config 相同；不要把價格或 legacy monitor 的 fallback valid 當
  成 HOLD。
- `研究基準與目前快照不是獨立結果`、`研究基準與目前分析身份不同`：保存新的、不同
  `result_id` 的同 scope snapshot，或接受本輪維持 WAIT；不要修改歷史 JSON 來製造獨立性。
- `availability custody`／future／cutoff blocker：先核對來源自己的 capture／availability
  證據與台北時間；本機檔案 mtime 不足以解鎖歷史正向建議。只要不確定，保留未知並由人工
  review。
- 主視窗關閉時若看到「刷新已取消／保留最近一次結果」，代表取消回執，不代表研究成功；
  等自然收尾後再次開啟或按「重新讀取研究」。保存後重開應能從同一 JSONL 讀回 exact
  holding／revision；若讀回失敗，保留檔案與技術詳情供排錯，不要刪除原始資料。

### 10.1 手動記錄交易

既有 UI／JSONL 路徑維持相容。新的精確 SQLite 事件帳本只在 caller 明確注入候選 repository 時啟用：append-only、整數分／股、Decimal 成本、namespace 與 source ID，撤銷以 compensation event 重播。JSONL→SQLite 只處理指定 sandbox 副本並保留來源 hash；沒有正式 migration 或預設切換。backtest 結果不得轉成 Portfolio fills，paper namespace 仍需真實 producer 與 source acceptance。

候選帳本 read-model 保留決策日、ledger ID／hash、event_count、quality 與缺件；有部位而缺已提交行情時 blocked，缺 source／thesis 時 degraded。缺 fills 不能補造現金、部位或安全評級；超賣、重複事件、namespace 不一致與啟用負現金拒絕政策時的違規會停止投影。

1. 點擊「手動記錄交易」。
2. 輸入股票、買賣別、價格、股數、日期、費用與稅金。
3. 可選擇策略來源並填寫備註。
4. 保存後系統重算持倉與平均成本。

也可以按「匯入交易 CSV」匯入券商或紙上交易檔：

1. 選擇 CSV；系統先以 UTF-8／CP950 嘗試解碼並自動辨識中英文欄名。
2. 系統逐列檢查證券代號、買賣別、股數、價格、交易日期、費用與稅金，先產生唯讀預覽。
3. 預覽全部通過且檔案 SHA-256 未變更時，按確認才會 append 到 Portfolio；取消、欄位錯誤、重複匯入或檔案被修改都不寫入。

匯入只支援可映射的成交明細，不連接券商 API，也不代表券商已成交；同一檔案的重複列會以來源 hash 與列內容產生可追溯交易 ID。CSV 欄名無法辨識時，請改用 `stock_code`、`stock_name`、`side`、`quantity`、`price`、`trade_date` 及可選 `fees`、`taxes`、`notes`。

輸入股票代號後，系統會嘗試從 stock master / SQLite 自動補證券名稱；找不到正式代號時會提示。手續費與證交稅會依台股預設值自動估算，使用者仍可手動覆寫。

賣出數量不得超過目前可用持倉。

### 10.2 從推薦或回測建立來源追溯

- 推薦結果表右鍵「記錄到持倉管理」。
- 回測交易明細右鍵記錄交易。

這些入口會保存推薦結果、回測 run 或策略版本來源。它們仍是手動記錄，不會送出券商委託。

從持倉列開啟原推薦研究時，系統只會在已保存的推薦結果 ID、股票代號、決策／資料日期與來源資料相符時，將研究頁連回該保存結果。若保存結果不存在、該股票不在結果中，或日期／來源資訊缺漏或衝突，研究頁不會沿用另一筆最新推薦；請回到「推薦分析」確認正確的已保存 ID、股票與來源資料後再開啟。此連結用來確認持倉的推薦來源；如歷史摘要或機率與原推薦不一致，請以推薦分析中的原保存結果核實。

相容 API `PortfolioService.get_benchmark_comparison()` 在尚未提供比較期間、現金／資金流帳與固定 benchmark constituents 時會回傳 `status=not_computable` 與 `None`，不再用數值 0 冒充已完成的超額報酬比較。正式的成本後 Portfolio／Equal Weight 比較要走 Paper Portfolio 的期間化 ledger 與 weekly report。

目前不要把批次回測排行榜理解成已提供直接加入持倉入口；可記錄到持倉的主要入口是推薦結果表與回測交易明細。

Portfolio 首層分開判讀研究建議、待成交／Paper 佇列與已記錄成交：研究建議不等於 fill，待成交不等於已成交，交易歷史只代表既有帳本事件。右側「交易歷史」與「Paper Portfolio」沿用服務／帳本狀態；缺數值時顯示未知或不可計算，不以 0 冒充完成。窄版會將持倉操作列與明細 tabs 直向排列，保留「清除篩選」與明確的記錄／取消入口；此頁不自動下單、不擅自套用配置。

### 10.3 Paper Portfolio 與 Equal Weight 狀態

持倉管理右側「Paper Portfolio」分頁是排程紙上帳的唯讀觀測面：

1. 顯示 daily status、最新可採用 snapshot 日期／ID、raw 累積 snapshot 筆數、現金、總值與最新安全持倉列；若 raw 最新列是未來日期，會保留 blocker／diagnostic 並排除於 current projection。
2. 顯示 Equal Weight benchmark 觀測數、Paper Trade Ledger 狀態、成本合計、full／partial／reject／override 統計與 weekly report 狀態；缺 benchmark、ledger 或 ledger 欄位不完整時會明示 `partial`／`not_computable`，不會以 0 補值。
3. 顯示 status／snapshot 路徑、blockers、warnings 與固定安全邊界。此分頁不建立資料庫、不寫正式 Portfolio、不調 Advice、不啟用 broker 或自動再平衡。
4. 「計算最近週報」會以最近 `5` 筆（可調整 `1–31`）snapshot 的實際首尾日期，唯讀核對 Paper weekly evidence。歷史 snapshot 缺少版本化成本基礎或逐 snapshot ledger 視窗證據時，畫面保留成本列數與 `paper_weekly_snapshot_cost_basis_unknown`／`paper_weekly_snapshot_ledger_window_unproven`，週報為 `not_computable`，不顯示推測的收益。觀測不足、期間邊界不一致、缺 turnover／execution gap 或缺 ledger 時，同樣保留具體 blocker，不把缺口當成 0。新策略帳戶的 binding 也不等於逐筆績效資格。
5. 「匯入 Paper 成交 CSV」只接受完整的 paper execution 欄位，先顯示檔案 hash、筆數與總成本，二次確認後才 append 至 Paper Trade Ledger；不會修改手動 Portfolio、Paper snapshot 或發送 broker 訂單。取消、欄位缺失、狀態／數量不一致或檔案在確認前變更時，整批拒絕且不建立 ledger。
6. 「匯出成交範本」會建立空白 `paper_fills_template.csv`；範本只有欄位標題、不包含示例交易，且預設不覆寫既有檔案。請填入真實 execution 後，再按「匯入 Paper 成交 CSV」走預覽與二次確認。
7. 每日 Paper／Decision Desk 排程預設採用最近一個已到達的台北 08:30 cutoff；若以 `--decision-at` 明確指定尚未到達的時間，Paper runner 會回報 `skipped_future_decision` 並不開啟 state／market DB，避免再產生 look-ahead row。
8. 「預覽／建立 Equal Weight」會先唯讀驗證 baseline safety flag、snapshot 首尾日期、frozen constituents 與每個決策日的 T-1 市場價格；預覽成功後才二次確認建立新的 benchmark ledger。目標已存在、輸入在確認前變更、future snapshot 或缺因果價格時會拒絕，不覆寫既有資料；這只補 benchmark observation，不能替代真實 Paper fills。

`export_paper_trade_csv_template.py --help` 會先設定 UTF-8 console；Windows CP1252 主控台也能正常顯示繁中說明。這只影響 CLI 顯示，不改變範本不含資料、預設不覆寫與不建立 Paper ledger 的安全邊界。

可用下列命令做相同的唯讀檢查：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_paper_portfolio_readiness.py `
  --output-root <OUTPUT_ROOT> `
  --format json
```

上述 Paper readiness、Paper weekly evidence、Equal Weight builder 與 Runtime readiness CLI 會在解析參數前設定 UTF-8 主控台輸出；Windows 預設 CP1252 環境也能正常使用 `--help` 與繁中診斷。這只影響顯示，不改變唯讀與不建 schema 的安全邊界。

Equal Weight readiness 預設讀取 `<OUTPUT_ROOT>/paper_portfolio/paper_equal_weight_benchmark.sqlite`；若 ledger 放在其他位置，可明確提供：

```powershell
$env:PAPER_EQUAL_WEIGHT_BENCHMARK_PATH = '<EQUAL_WEIGHT_LEDGER.sqlite>'
```

此環境變數只供唯讀檢查定位既有 ledger；預設檔案不存在時會顯示 `equal_weight_benchmark_db_missing`，不會由 readiness／weekly evidence 自動建立 schema。持倉管理 > Paper Portfolio 的「預覽／建立 Equal Weight」會使用 baseline、Paper snapshot 與 `TWStockConfig.db_file` 的市場資料，先產生只讀 preview；使用者明確確認後才建立新的研究用 append-only ledger，且若目標已存在會拒絕覆寫。這個入口不改市場 DB、Paper snapshot、手動 Portfolio 或 Paper Trade Ledger，也不把 benchmark 當成成交紀錄。

最近一次實測有 `21` 筆 raw snapshot，raw 最新日 `2026-08-28`、總值 `490950.00`；本次台北市場日同為 `2026-08-28`，該列可作當日 current projection。受控流程已以 frozen constituents `1418／1536／1615` 在 `<OUTPUT_ROOT>/paper_portfolio/paper_equal_weight_benchmark.sqlite` 建立 `21` 筆 Equal Weight observation，benchmark reader 為 ready；這只補齊研究用 benchmark 輸入，不補足 Paper Trade Ledger，也不代表成本後績效或投資有效性。正式 readiness 仍為 `partial`。若執行時台北市場日早於 snapshot 日期，readiness 會將該列標成 future、排除於 current NAV，並只保留 blocker／diagnostic。

若 Paper Portfolio、weekly evidence 或 Equal Weight builder 遇到 `paper_snapshot_future_dated`、`paper_daily_status_future_dated` 或 `paper_weekly_report_future_period`，先停止採用該期間，不要刪除、回填或手動改寫正式資料；請由 owner 追查排程時鐘、時區與來源事件。現行排程入口已改採最近已到達 cutoff，且 writer 對明確未到達的 `--decision-at` fail-closed；既有 future row 仍只作 blocker／diagnostic。Equal Weight builder 也會在 preview／apply 前拒絕 future snapshot，避免 look-ahead 污染 benchmark。

Paper Trade Ledger 的手動匯入預設位置為 `<OUTPUT_ROOT>/paper_portfolio/paper_trade_ledger.sqlite`，也可用 `PAPER_TRADE_LEDGER_PATH` 或 CLI 的 `--cost-ledger-db` 指定。日常 EOD replay 排程使用 repository 隔離的 `<repo>/output/paper_execution_eod_replay/paper_trade_ledger.sqlite`；盤前與 Formal runner 會以唯讀方式讀取該隔離 ledger。Ledger 必須由受控 paper execution producer 寫入；不能把手動 Portfolio 的 `trades.jsonl`、virtual order trace 或 snapshot mark 直接複製成成本帳。每筆 fill 至少要有 requested／filled 數量、狀態、Decimal 成本、turnover、execution gap 與來源事件；缺任何必要欄位時 weekly report 維持不可計算。Readiness 會另外檢查 `event_date` 是否晚於台灣市場日；future-dated fill 會保留 raw row 供稽核但標成 `paper_trade_ledger_future_dated`、排除成本總額與 ready 判定，Portfolio UI 會顯示 future-dated fill 計數。

目前可用的受控 producer CLI 為：

```powershell
.\.venv\Scripts\python.exe scripts\append_paper_trade_ledger.py `
  --input-json <PAPER_FILL_JSON> `
  --ledger-db <PAPER_TRADE_LEDGER.sqlite>
```

上述命令只驗證與預覽，不建立 ledger；確認事件與來源無誤後，才加上 `--confirm-append-paper-ledger`。CLI 仍只寫研究用 Paper Trade Ledger，不會改寫手動 Portfolio、正式市場 SQLite 或呼叫券商。

JSON producer 會在預覽輸出 `source_hash`，並把 SHA-256 前 16 碼綁入每筆
`source_event_id`（`paper_json:<hash-prefix>:<event-id>`）；確認 append 前會再次
檢查輸入檔 hash，檔案在讀取期間變更就整批拒絕。若未提供 `source_type`，會固定標為
`paper_trade_json_import`，方便 readiness／weekly evidence 判斷來源；這仍不代表該
JSON 內的事件已由系統驗證為真實成交，owner 仍須提供可稽核的 paper execution 來源。

若來源是 CSV，可使用與 UI 相同的完整 execution contract：

```powershell
.\.venv\Scripts\python.exe scripts\append_paper_trade_csv.py `
  --input-csv <PAPER_FILLS.csv> `
  --ledger-db <PAPER_TRADE_LEDGER.sqlite>
```

CSV 至少要有 `fill_id`、`order_id`、`portfolio_id`、`event_date`、`stock_code`、`side`、`requested_quantity`、`filled_quantity`、`reference_price`、`fill_price`、`commission`、`tax`、`slippage_cost`、`turnover_bp`、`execution_gap_bp`、`status` 與 `source_event_id`；`override_reason` 可選。預覽成功後才加上 `--confirm-append-paper-ledger`。匯入 producer 固定寫入 `source_type=paper_trade_import`，並將 CSV hash 綁入 `source_event_id`，以便週報保留來源追溯。

在確認 append 前，建議先用 query-only reconciliation 對帳外部 fills 與 Paper snapshot 的期初／期末股數：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_paper_trade_reconciliation.py `
  --input-csv <PAPER_FILLS.csv> `
  --state-db <PAPER_PORTFOLIO.sqlite> `
  --ledger-db <PAPER_TRADE_LEDGER.sqlite> `
  --portfolio-id paper-main `
  --period-start 2026-08-24 `
  --period-end 2026-08-28 `
  --format markdown
```

這個預覽先重驗完整 `paper-trade-import.v1` execution contract，再以 SQLite
`mode=ro`／`PRAGMA query_only=ON` 讀取明確期間的唯一期初／期末 snapshot，逐股票比較
buy／sell 的 `filled_quantity` 與 snapshot quantity delta，也會檢查既有 ledger 的
`fill_id` collision。輸出 `paper-trade-reconciliation.v1` 固定是 candidate-only、
`write_performed=false`；只有明確期間、snapshot 邊界與數量對帳均通過才顯示
`status=ready`／`ledger_append_allowed=true`。period 自動推導或對帳不一致只回
`needs_review`；欄位 invalid、future event、portfolio 不符或 collision 回 `rejected`。
snapshot 不會被用來反推成交，`ready` 也不會自動寫 ledger；確認仍須回到上方
`append_paper_trade_csv.py --confirm-append-paper-ledger`，並重新驗證輸入檔 hash。

對帳結果現在也會顯示期初／期末現金與 fills 現金流的守恆差額。預設只把差額留在 `cash_reconciliation` 與 diagnostics，維持舊流程可讀；若要把現金不一致列為 append 前阻擋，加入 `--require-cash-reconciliation`。此選項仍只做 query-only preflight，不會寫入任何帳本。

若缺少欄位格式，可先建立空白範本（只寫入欄位標題，不建立 ledger）：

```powershell
.\.venv\Scripts\python.exe scripts/export_paper_trade_csv_template.py `
  --output-csv <PAPER_FILLS_TEMPLATE.csv>
```

既有檔案預設不覆寫；只有確認目標是未使用的範本檔時才使用 `--overwrite`。

若要以既有 paper baseline、snapshot 日期與正式行情的 T-1 價格建立 frozen-constituent Equal Weight benchmark，可先執行唯讀 preview：

```powershell
.\.venv\Scripts\python.exe scripts\build_paper_equal_weight_benchmark.py `
  --baseline <PAPER_BASELINE_JSON> `
  --state-db <PAPER_PORTFOLIO.sqlite> `
  --market-db <TWSTOCK.sqlite> `
  --output-ledger <EQUAL_WEIGHT.sqlite>
```

preview 會驗證 baseline safety flags、首日邊界、snapshot 日期唯一性、frozen constituents 與每一日可取得的 T-1 價格；不建立 output。確認結果後才加上 `--confirm-build-paper-benchmark`，且 output 已存在時會拒絕、不覆寫。此命令只寫新的研究用 Equal Weight ledger，不改正式市場 SQLite、paper snapshot、手動 Portfolio 或 broker；建立後仍需用本節 readiness inspector 檢查週報輸入與成本帳是否完整。

若 benchmark 與 Paper Trade Ledger 都已存在，可用下列命令唯讀重建指定期間的週報 evidence：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_paper_portfolio_weekly_evidence.py `
  --output-root <OUTPUT_ROOT> `
  --period-start 2026-08-20 `
  --period-end 2026-08-21 `
  --expected-trading-days 2 `
  --benchmark-db <EQUAL_WEIGHT.sqlite> `
  --cost-ledger-db <PAPER_TRADE_LEDGER.sqlite> `
  --format json
```

此 CLI 與 Portfolio UI 使用相同的 query-only adapter；只會讀既有 SQLite，缺資料或 schema 時回報原因並以非零狀態結束，不建立資料庫。成本列的 `source_type` 必須保留 `paper_` provenance；手動交易、`broker_csv`、snapshot mark 或 virtual execution trace 不會被當成成交成本。`expected-trading-days` 是完整性標示，不是補值參數；週報的研究邊界固定為 `research_only=true`、`investment_effectiveness_claim=false`、`writes_allowed=false`、`broker_execution=false` 與 `auto_rebalance_allowed=false`。

JSON evidence 使用 `paper-portfolio-weekly-evidence.v2`；`observed_cost_disclosure_total` 只加總目前讀到且通過檢查的成本列，任一成本讀取 blocker 出現就保持未知。`cost_disclosure_complete=false` 表示沒有完整視窗證明，不得把該金額當作完整成本。這兩個欄位目前僅在 JSON 輸出可見；UI 與 Markdown 顯示列數、狀態及阻擋原因。成本區間為 `[period_start, period_end)`，結束日成交留至下一期。遇到 basis／ledger-window blocker，先核對 snapshot 的版本化 basis、逐 snapshot receipt、portfolio/account、prior snapshot、決策時點與 fill/source event 對照；證據未齊前不手改 snapshot、不補零。此狀態 CLI 回傳 exit code 2，原始資料不會被修改。

策略專屬帳戶若只有前向現金開戶紀錄，表示明示版本已保存500000現金、空持倉與實際建立時間；這不代表每日成交、價格可得時點、成本或 benchmark 已完整。週報遇到 `strategy_account_row_provenance_unverified` 時仍不可計算績效，請保留原紀錄，等待來源鏈補齊，不手填歷史持倉或收益。目前正常 UI 尚未提供這項開戶入口。

### 10.4 持倉與交易歷史

選取持倉後，右側同步顯示：

- 交易歷史
- 覆盤日誌
- 策略與價格監控
- 生命週期回顧
- 籌碼監控

交易歷史可直接選取一列，再按表格下方的「刪除選取交易」；未選取資料時按鈕維持不可按，右鍵刪除仍可使用。持倉列表是一檔股票的衍生彙總，不會因為誤按而直接刪除整檔歷史；每次只刪除選取的一筆原始交易。確認後系統會以剩餘交易重算持倉與平均成本；若刪除會造成超賣或不合法持倉，系統會拒絕並保留原始資料。

從持倉篩選交易歷史時，交易歷史區會顯示目前篩選狀態，並提供「清除篩選」回到全部交易。

持倉頁頂端的「持倉市值（未含現金）」只加總有可用最新價格的活躍持倉；現金帳、未入帳負債與完整 NAV 尚未納入此 MVP，因此不會把投入金額加上已實現損益冒充淨值。缺少價格時顯示 `N/A`，摘要會列出已標記筆數、缺價格股票與價格日期。

2026-10-03 c625 原生接受範圍包含 2330、1,000 股的持倉讀回與成本情境重開：原平均成本 2,500 元、投入 2,500,000 元；變更成本情境將平均成本調為 2,750 元、投入 2,750,000 元，在價格仍為 2,500 元時顯示毛損益 −250,000 元（−9.09%），QA 帳本已記錄手續費 3,563 元、稅 0 元。這是隔離 QA 的持倉成本情境，不是新成交或實際報酬；Health 為 WATCH、曝險 10,000 bp。Exit 顯示 owner 尚未提供單股唯讀 read model，因此不推導賣出；entry decision identity 未知是另一項來源限制。新成本結果在新 Python process 載入成功，canonical 四方讀回的 198 個 Decimal 值逐筆相符。最終原生收據為 `output/qa/integration_20261002/phase3_native/root_native_final_acceptance_20261003T105541987127Z.json`（SHA-256 `483170b2c330b0121ce51435ff7a5966b073e2082c846289f56d33cade0597b6`）；成本視窗為 DPR 1.25、1602×1030，baseline 為 DPR 1.0、1282×832。c625 的 1017×768 縮放嘗試沒有成功；舊 7eb 版本的窄視窗觀察不得當成 c625 驗收。

持倉頁目前投入金額、已實現與未實現金額以毛額呈現，尚未扣除費用與稅額。費稅摘要只彙整來源中已記錄的金額，依原幣別分列並同時顯示已記錄與缺值筆數；缺件不補零，也不把這項摘要當成完整淨損益或已結清帳務。

### 10.5 情境與壓力測試

持倉管理右側「情境壓力」分頁提供唯讀的 Portfolio Scenario & Stress Lab v1。可選擇快速下跌、跳空跌停、相關股同跌、最大持倉事件、流動性消失、輪動失敗或來源中斷等情境，按「執行情境」後查看基準市值、壓力後市值、變動與逐檔明細。

- 價格衝擊是固定的研究假設（例如 `-1000 bp`），不是市場預測，也不會改寫持倉、交易、日誌或資料庫。
- 缺少最新價格時會顯示「部分可計算」並列出股票；只計算已標記持倉，不外推缺失值。
- 「輪動失敗」與「來源中斷」目前會 fail-closed 顯示不可計算，因為尚未有產業曝險或可用來源契約；不可把 `N/A` 解讀成零風險。
- 所有結果固定標示研究用途，不是投資建議、績效證據或交易指令。

按「保存研究快照」並完成二次確認後，才會把目前結果寫入
`OUTPUT_ROOT/portfolio/stress_history.sqlite` 的 append-only history；取消確認、缺少結果或重複相同 payload 都不會新增資料。分頁下方的 Stress 歷史表由 query-only read service 讀取，會顯示執行時間、基準日、情境、狀態、市值變動與 payload hash；資料庫不存在時顯示 `stress_history_not_configured`，不會因畫面 refresh 建立空 DB。保存的快照仍固定為 `research_only=true`、`investment_effectiveness_claim=false`，不得當成正式績效或交易 evidence。

若要在 UI 外預覽或保存單一結果，先將 `PortfolioStressResult.to_dict()` 輸出成 JSON，再使用：

```powershell
.\.venv\Scripts\python.exe scripts\append_portfolio_stress_history.py `
  --input-json .\stress_result.json `
  --history-db .\output\portfolio\stress_history.sqlite

# 只有明確確認才會建立／寫入 history DB
.\.venv\Scripts\python.exe scripts\append_portfolio_stress_history.py `
  --input-json .\stress_result.json `
  --history-db .\output\portfolio\stress_history.sqlite `
  --confirm-save-stress-history
```

### 10.6 覆盤日誌

1. 選取持倉。
2. 點擊「新增日記」。
3. 記錄進場假設、風險、觀察結果與出場理由。

日誌的刪除與清空採 append-only continuity 語意：目前列表會隱藏
`removed`／`cleared` tombstone，但既有 legacy JSONL 行與歷史 revision 不會被
重寫或抹除。若需要稽核，讀取 `OUTPUT_ROOT/portfolio/journal_entries.jsonl`
的 history projection；不要把 tombstone 或 `accepted`／`skipped`／
`review_scheduled` 研究 action 當成新筆記、成交或成熟 outcome。新研究 action
必須帶明示 `result_id`、`stock_code` 與可用的 source snapshot；缺 key 保持
`unknown`，不以同股同日猜測。Increment A 只提供 backend contract，尚未把
Watchlist 預設 writer 切換到 repository，也不對正式資料執行 migration。

### 10.7 策略與價格監控

顯示：

- 目前價格
- 未實現損益
- 停損與停利門檻
- 監控狀態與原因
- 策略、推薦或回測來源

目前價格會一併顯示價格日期。手動建立持倉會顯示為「手動建立，無推薦 / 回測來源」，避免誤解為資料缺失。

目前價格查詢是唯讀路徑：先查詢既有 SQLite `daily_prices`，SQLite 不存在或不可讀時才降級讀取既有每日 CSV；打開持倉頁或查詢價格不會建立空 `twstock.db`。若 SQLite 使用 `immutable_fallback`，應把數值理解為最後已提交快照，並回到「數據更新」或 SQLite Inspector 檢查 freshness。

警示是輔助判讀，不會自動平倉。

### 10.8 生命週期回顧

選取持倉後，右側「生命週期回顧」會顯示：

- Thesis 狀態：假設仍成立、證據降級 / 持續觀察、或假設失效 / 需要覆盤。
- 來源追溯：例如推薦結果、回測 run 或策略版本來源。
- 執行落差：進場平均成本相對來源快照價格的 basis points gap。
- 訊號落差：`PortfolioConditionMonitor` 的 valid / warning / invalid 狀態與原因。
- 市場體制：進場 regime 與目前 regime 是否一致。
- 資料品質：來源 hash、來源品質與 degraded / estimated flags。
- 摘要 tokens：source / execution / signal / market / data_quality 的狀態摘要。

此分頁只做 post-trade attribution 與 live-vs-research gap 判讀，不會自動下單、平倉、調整持倉、刪除策略版本或改寫回測結果。若顯示假設失效，使用者應回到 Research Lab、Registry 比較或覆盤日誌確認原因。

#### Health 保存結果的判讀（開發版接線中）

Health 已增加不可變結果封存與精確讀回服務；目前一般持倉介面仍沿既有最新狀態讀取，尚未提供選取封存 receipt 的完整操作流程。後端 exact 讀回必須明示帳戶、snapshot、決策日、全部持倉身分／股票／股數與含時區的決策截止時間；不能只用同股同日或最新結果代替原保存來源。

來源觀測、評估觀測與封存可得時間分開判讀。封存可得時間由 writer 在完整結果讀回後記錄，重試保留原時間；cutoff 早於可得時間、來源晚到、帳戶／股數不符、檔案損壞或重新封裝 hash 仍有身分不符時，精確讀回會拒絕。缺少原來源 witness 時保留 degraded／unknown，不以最新檔案補成 HEALTHY 或歷史 PIT 資格。這些研究結果不觸發 broker、平倉或自動配置。

排錯時先核對所選帳戶、snapshot、完整持倉及含時區 cutoff，再查看具名來源與 clock blocker；不要修改原檔、回填時鐘或降低驗證。這份後端整合的廣回歸仍有五項失敗，正式開發檔待修正與完整 UI 接線；目前進度與失敗界線見[補完 QA](../06_qa/BALDR_COMPLETION_PROGRESS_20261011.md)。

### 10.9 籌碼監控

顯示籌碼風險、近期分點買賣明細與資料品質。風險等級與品質狀態會以繁體中文顯示，原始 key 保留在 tooltip 供除錯。按「下鑽詳細主力流向」會切換至「市場探索 > 主力流向」並定位目前股票。

### 10.10 清空全體數據

此操作會永久清空持倉交易，必須二次確認。執行前先確認受影響的帳本／交易範圍，並建立可讀回的獨立備份；若對話框未清楚列出範圍、或尚未確認備份可恢復，請取消操作。此手冊目前沒有記錄此清空操作的備份位置與復原程序，不要把市場 SQLite 的備份當成個人持倉備份。覆盤日誌的清空則只追加 tombstone，active 列表變為空但原始 JSONL／history 保留，不能把畫面空白解讀成歷史資料已不存在。

## 11. Runtime Observatory（Owner 營運與治理監控）

此頁標題為「運作狀態與下一步」。先看日常工作、資料與保存位置、治理任務各自的影響，再依提示到「數據更新」檢查資料。當前來源沒有提供最後成功完成與行情資料日期，兩者明示「未知」；每個工作列的「觀測時間」不能當成成功完成、行情資料日或 Windows 排程執行證據。未讀取、未知、來源無法讀取及歷史治理事件均不能解讀成正常。

這是唯讀觀測頁，不是選股工具；它並列呈現兩條**不得互相推論**的觀測平面：

1. **營運排程**：只讀 `<OUTPUT_ROOT>/scheduled/*/latest_status.json` 已保存產物，顯示核心資料更新、資料新鮮度、推薦快照、證據 dry-run、決策證據與 Paper Portfolio，以及 ML／官方市場事件／ML Direct-OOC 維護等安全狀態。
2. **治理 Runtime**：只讀 `runtime/` 的任務、context 與 append-only 治理事件；它反映 agent／governance workflow，不是日常資料、推薦或 Paper 流程的健康度。

營運排程的每一列是「已保存檔案的讀取結果」，**不是** Windows Task Scheduler 的註冊、啟動中、成功結束或 `Last Result` 證明；畫面能讀取的 status artifact 子集合也不等於 Windows Task 總數。若要查核全部 21 個 baldr Windows tasks，請依[全排程唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)執行；該 Runbook 的唯讀查詢不會啟動 producer 或修改 Task。

「路徑與讀寫診斷」、「排程來源與原始診斷」、「治理任務、上下文與完整事件明細」預設收合；按「展開／收合」查看完整上下文、原始狀態、來源路徑及錯誤原因。刷新保留收合選擇與仍存在的工作／路徑選擇；不會啟動更新、訓練或修復。無法讀取／部分無法解析的事件檔即使標為目前觀測，也不能顯示為健康；先核對來源與診斷，再按既有排錯流程處理。

### 11.1 正式路徑環境診斷

首層摘要下的「資料與保存位置（唯讀診斷）」會立即顯示四個 App 依賴位置；展開「路徑與讀寫診斷」可核對 `DATA_ROOT`、`OUTPUT_ROOT`、`DATA_ROOT/logs` 與 `OUTPUT_ROOT/research_runs/research_runs.db`。狀態意義如下：

- **可用**：路徑／檔案已存在，程序目前可讀；需要寫入的既有 logger／Registry 檔案也能開啟寫入 handle（只開啟與關閉，不寫入內容）。
- **待建立**：父路徑可見，但目標尚未建立；此頁只揭露缺口，不會自動建立目錄、probe 檔或 SQLite。
- **需要處理**：路徑可見但讀取、`os.access` 或既有檔案 write-handle probe 不符合需求。
- **無法使用**：資料根目錄不存在、父路徑不可見，或檢查本身失敗。

卡片採首次立即讀取、之後約每 30 秒重新整理。它是 side-effect-free 的環境提示：目錄／檔案先以 `os.access` 檢查，若已有 `config.log` 或 Research Registry，再以不寫入內容的 handle probe 交叉檢查；不會建立檔案或執行 SQLite 寫入，因此仍不能證明 schema 變更、原子提交或網路磁碟鎖定一定成功。若卡片顯示需要處理，先依 diagnostic 修正 ACL／鎖定或改用具名且可寫的 `OUTPUT_ROOT`；系統不會替使用者修改權限。

窄視窗使用 Runtime 時，寬度小於 720px 會自動將「任務狀態機／Context」與「治理 Runtime／事件流」由左右兩欄改為上下排列；整頁可垂直捲動，長狀態文字會換行，底部 Session context 會以省略號保留摘要。主視窗可縮至 320px（左導覽同步改為 icon-only）；這些都是顯示層調整，不會改變資料讀取、排程或寫入權限。

不開啟主 UI 也可執行同一份唯讀檢查：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_runtime_environment_readiness.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data\output `
  --format markdown
```

預設輸出 JSON；`--format markdown` 方便貼入稽核紀錄。整體 `ready` 時 exit code 為 `0`，其餘狀態為 `2`；兩者都不會建立缺少的路徑。輸出會保留 `side_effect_free=true`、`write_probe=os.access_plus_existing_handle` 與每一路徑的 diagnostic，供後續判讀正式 logger／Registry 權限與鎖定問題。

若要在不碰正式資料的前提下驗證實際 ACL／檔案與 SQLite 寫入，可另外指定一個**已存在且位於 `DATA_ROOT`、`OUTPUT_ROOT` 之外的 staging 目錄**。未帶確認旗標時只會回報 `confirmation_required`，不會寫入：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_runtime_environment_readiness.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data\output `
  --write-probe-root C:\Temp\baldr-runtime-probe `
  --confirm-write-probe --format json `
  --output C:\Temp\runtime_write_probe.json
```

確認 staging 目錄無誤後，才可明確加入 `--confirm-write-probe`；`--output` 可把 JSON／Markdown 證據保存到明確指定的非正式路徑。程式會在該目錄建立短生命週期的暫存文字檔與使用正式 `ResearchRunRepository` schema 的 SQLite，寫入／讀回一筆 probe、rollback 後確認該筆消失，再清理全部檔案；JSON／Markdown 會顯示 `registry_transaction_succeeded`，通過時 exit code 為 `0`，其他狀態為 `2`。這只能證明指定 staging 目錄的實際 Registry schema transaction／rollback 與清理能力，不能取代正式 Registry ACL／鎖定驗證；指向正式 `DATA_ROOT` 或 `OUTPUT_ROOT` 會被阻擋。

若需要更接近正式 Registry 的 schema 證據，可使用下列唯讀來源 clone probe：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_research_registry_transaction.py `
  --registry D:\Min\Python\Project\FA_Data\output\research_runs\research_runs.db `
  --confirm-snapshot-probe `
  --format json `
  --output C:\Temp\research_registry_snapshot_probe.json
```

此命令只以 `mode=ro` 開啟 `--registry`，將一致性 snapshot 複製到 OS TEMP，再在 clone
上執行 schema／`quick_check`／insert／讀回／rollback；clone 會自動清除，正式 DB 的
bytes、mtime 與 SHA-256 會前後比對。報告的
`write_probe=formal_registry_read_only_snapshot_clone_transaction`、
`formal_write_attempted=false` 代表目前正式 schema 可由 clone 驗證，並不代表正式
Registry ACL、鎖定或 production writer 已經實寫成功。

若要在 owner 明確核准後驗證**正式 Research Registry 的實際 transaction／rollback**，使用
guarded production canary；它不是 UI 動作，也不應由 scheduler 呼叫：

```powershell
.\.venv\Scripts\python.exe scripts\qa_research_registry_production_canary.py `
  --registry D:\Min\Python\Project\FA_Data\output\research_runs\research_runs.db `
  --output-root D:\Min\Python\Project\FA_Data\output `
  --protected-root D:\Min\Python\Project\FA_Data `
  --owner-approval research-registry-transaction-canary `
  --no-concurrent-writer-ack no-concurrent-writer `
  --confirm-production-registry-canary `
  --output-json C:\Temp\research_registry_production_canary.json
```

執行前必須先停用／確認沒有其他 Registry writer；命令會先做 schema v2、required
tables／columns、`quick_check` 與 row count 預檢，再把正式 DB snapshot 到 OS TEMP。
canary 只插入一筆唯一 marker、讀回後立即 rollback，最後用唯讀連線確認 marker 不存在、
row count／content hash 沒有變化。未同時提供 owner approval、無並行 writer acknowledgement
與 confirm 時，結果是 `confirmation_required` 或 `blocked`，不會開啟正式寫入 handle。
成功輸出 `status=measured` 只表示該次可回滾 transaction 的實際證據，固定
`durable_change_allowed=false`；不代表長期 Registry writer、Formal、Evidence、scheduler
或 broker gate 已開啟。若驗證失敗，OS TEMP backup 會保留供人工比對；不要直接重跑或覆寫
既有 DB。`--output-json` 必須位於 OS TEMP 且不可落在 protected root。

### 11.2 營運排程判讀

- **正常**：核心工作已保存可接受的最新狀態。
- **安全邊界中**：工作受保護地完成或停在預期 gate；例如具完整 natural-maturity 證據的 evidence `degraded`、ML promotion `blocked`，或 ML Co-pilot `passed_rule_only`／`alpha=0`。這不是 ML 已 promotion，也不能人工解除 gate。
- **需要注意**：核心 status 缺失、無法讀取、過期、evidence 缺少完整 natural-maturity 證據，或有未預期狀態。先查看列出的 raw status、時間來源、source path 與 diagnostic，再回到對應功能／排程日誌處理。ML Direct/OOC 顯示 `blocked_insufficient_storage` 時，應先依 `storage_preflight.free_bytes` 盤點容量與保留策略，不要直接重跑或刪除既有 run。
- **無法判定**：非核心／安全工作缺少可用 status；不能把它當成功或失敗。

狀態時間只採 `checked_at`、`generated_at`，否則採檔案修改時間；市場決策日期（如 `decision_at`、`as_of_date`）不是排程完成時間。超過 36 小時的 core artifact 會被視為過期。tooltip 保留 raw status、讀取狀態、時間來源、來源路徑與 diagnostic，供追查 provenance。畫面只保證顯示已知或發現的 status artifact，不保證覆蓋全部 12 個 Windows tasks。

### 11.3 治理 Runtime 判讀

任務來源不存在、無法讀取、格式錯誤或 status 未被識別時，顯示「未知（來源未確認）」。狀態 tooltip 保留 raw status、task/context read state 與 diagnostics；底層無法區分缺檔和部分 I/O 錯誤時保留 missing_or_unreadable。未知不等於閒置，畫面不建立或修復來源。

最近 2,000 個非空 event ID 中，同內容重複事件只發布一次；同 ID 異內容仍保留 conflict 診斷。畫面最多 500 筆不代表底層 log 被裁切。關閉 observer 解除訂閱；重啟從尾端重新觀測，不啟動／重試 task，亦不提供 durable exactly-once queue。

離線 QA 可執行 `scripts/qa_validate_runtime_loop.py`；它自建 TEMP 雙根、輸出逐項結果，失敗非零退出。全程只驗證 observer／Qt 契約，不代表正式 Runtime writer、Windows task 或 V4 readiness。

治理健康度只以目前 24 小時內、時間可解析且不超出容許時鐘誤差的治理事件判定。只有這些 current 事件可使治理狀態成為 `ERROR` 或 `HALTED`；舊事件會顯示為「僅有歷史治理事件」，未來時間或無法解析時間會顯示為不能判定目前狀態。歷史重大違規仍保留供稽核，但不能解讀成今天日常營運已暫停。

事件檔無法讀取或部分無法解析時，畫面會明示「無法讀取」或「部分無法解析」，不會把它降格成「尚無事件」或健康。`ERROR`／`HALTED`、拒絕率與最近重大違規只代表治理 workflow；它們不代表資料更新、推薦、Paper Portfolio 或主 App 一般功能失敗。

「本次開啟後的治理事件流」只顯示此 UI session 開啟後追加的最多 500 筆事件；它是 live 觀測而非完整歷史稽核查詢。當出現 `ERROR` 或 `HALTED`，先查看最近重大違規與 raw tooltip，再回到對應功能頁或日誌排錯。

此頁不會寫入 DB、啟動或修改 Windows task、重跑資料更新／模型訓練、變更 ML alpha／promotion、改寫 Runtime 事件、執行 Paper 操作或送出券商委託。任何需要執行的動作，都必須回到對應功能、排程腳本或受治理流程。

## 12. 常見問題

### UI 無法啟動

```powershell
.\.venv\Scripts\python.exe -c "import PySide6; print(PySide6.__version__)"
.\.venv\Scripts\python.exe ui_qt\main.py
```

確認目前目錄是 repo 根目錄，並檢查 `DATA_ROOT` 是否可存取。

### 圖表空白

確認 PySide6 QtWebEngine 可用；系統無法使用 fast renderer 時會嘗試 Matplotlib fallback。先查看 terminal 或應用日誌的匯入錯誤。

### 更新後推薦仍沒有最新日期

1. 檢查 SQLite 狀態日期。
2. 手動下載後確認已合併。
3. 確認技術指標已增量計算。
4. 在 SQLite Inspector 檢查 `daily_prices` 與 `technical_indicators`。

### Smart Money 沒有資料

確認券商分點已下載、合併並同步至 `broker_flows`。`unavailable` 不應解讀為 0 張。

若主表有股票但「語意狀態」顯示未計算，先確認 `SmartMoneySemanticService` 是否初始化成功，以及 SQLite `daily_prices` 是否可提供決策日前價格；沒有價格時仍可顯示 5 / 20 / 60 日淨量，但高檔出貨疑慮可能不會產生。

若快速更新在「同步券商分點至 SQLite」遇到同一分點 / 股票 / 日期的買超與賣超唯一鍵衝突，代表 DB 仍是舊三欄主鍵；更新後的流程會在同步前先備份並升級為含 `trade_type` 的主鍵。

### TPEX 股票日價缺漏

若在 SQLite Inspector 查 `3207` 缺少某個交易日，先檢查 `DATA_ROOT/daily_price_tpex/YYYYMMDD.csv` 是否存在；若不存在，代表 TPEX 官方日價未抓到或被站方阻擋，不應用 TWSE 當日已存在來判定完整。2026-06-17 排查後的正式歷史狀態應可看到 `3207` 覆蓋 `20140102..20260617`、共 2,907 筆；後續每日若 TPEX 當日失敗，UI / scheduled status 會列出缺少日期。請使用每日股價手動下載、快速/安全更新，或「背景補齊 TPEX + 技術指標」重試缺漏日期並同步。

### TWSE 股票日價缺漏

若 SQLite Inspector 查 TWSE 股票（例如 `2330`）缺少某個交易日，先檢查 `DATA_ROOT/daily_price/YYYYMMDD.csv` 是否存在；若日檔不存在，代表 TWSE 日檔未下載成功或曾被跳過，需用每日股價手動下載或安全更新補齊該日期範圍後再同步 SQLite。若缺少日期是交易所休市日則屬正常，例如 2026-06-19 為端午節休市。

### 回測 0 交易

依序檢查：

1. 資金是否足夠買一張。
2. 日期範圍是否涵蓋足夠訊號。
3. quantile 是否仍在暖機期。
4. 固定門檻是否過高。
5. 漲跌停、成交量與最大參與率是否拒絕成交。
6. 是否只有期末未平倉部位。

### Promote 按鈕不能使用

確認結果已保存，且驗證狀態不是 FAIL。樣本不足、無結果、未保存、run 已封存、run 已升級、資料完整性不是 valid、缺少參數合約版本、最低 validation gate 未通過、缺 benchmark excess return、factor snapshot 品質不足、regime compatibility 不足或 Month 6 lifecycle gate 未通過時，不允許升級。若策略版本 JSON 已寫入但 Registry 回填失敗，系統會執行補償刪除；刪除失敗時標記 reconciliation required，需進入受控修復流程。

## 13. Manual 覆蓋狀態

> 本表的「完成」只表示操作手冊已覆蓋入口、步驟、參數、結果判讀與排錯，不表示該工作區
> 的產品 Gate、外部資料、真實 fills、Formal OOS 或 production writer 已完成。Current product
> readiness 請看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，不由本表的文檔覆蓋判定推導。

| 工作區 | 啟動/入口 | 操作 | 參數 | 結果解讀 | 安全/排錯 |
|---|---:|---:|---:|---:|---:|
| 數據更新 | 完成 | 完成 | 完成 | 完成 | 完成 |
| 市場探索 | 完成 | 完成 | 完成 | 完成 | 完成 |
| 推薦分析 | 完成 | 完成 | 完成 | 完成 | 完成 |
| 觀察清單／個股研究 | 完成 | 完成 | 完成 | 完成 | 完成 |
| 市場探索 / 市場總覽；決策工作台 / 決策來源 | 完成（唯一每日決策實例與跨頁導覽） | 完成 | 完成 | 日期、來源品質、主結論、行動等級、焦點卡、空狀態與降級結果判讀 | 完成；不改評分／交易權限，projection、research 與 formal evidence 分開；即時進度見 Snapshot |
| Research Lab | 完成 | 完成 | 完成 | 完成 | 完成 |
| 持倉管理 | 完成 | 完成 | 完成 | 手動交易、CSV 預覽／匯入、日誌、監控、情境壓力投影與研究快照判讀；Paper 成交／成本缺件須明示，不補造結果 | 部分完成；一般研究唯讀與不接券商自動交易界線已說明，但「清空全體數據」仍需補明帳本範圍、備份位置與復原步驟；該缺口未完成前應取消清空操作 |
| Runtime Observatory | 完成 | 完成 | 不適用 | 完成 | 完成 |

功能行為改動時，必須同步更新本表與對應章節。

完整主 UI 人工 smoke test 母檔維護於 [FULL_APP_HEALTHCHECK_2026_06_16.md](../06_qa/FULL_APP_HEALTHCHECK_2026_06_16.md)。每次修改數據更新、SQLite 檢視、每日決策或跨工作區流程後，除自動化測試外，應依該 healthcheck 做 smoke test。

非破壞式 Full App Healthcheck Runner 可用於開發期間的自動化輔助驗證：

```powershell
.\.venv\Scripts\python.exe scripts\run_full_app_healthcheck.py --mode quick --output-dir output\qa\full_app_healthcheck_tmp --fail-fast
.\.venv\Scripts\python.exe scripts\run_full_app_healthcheck.py --mode full --tab recommendation --output-dir output\qa\full_app_healthcheck_tmp --fail-fast
```

`--tab` 可用於分頁驗證，目前支援 `update`、`market`、`decision`、`research`、`recommendation`、`watchlist`、`portfolio`、`runtime` 與 `cross-flow`。這些測試只代表已核准的非破壞 direct bridge / QA script 通過；真實資料寫入、刪除、匯出檔案、完整 MainWindow 啟動、視覺判讀與真人互動流程仍要依母檔人工確認。

若需要接近真人 UI 操作的 MainWindow smoke，可明確 opt-in：

```powershell
.\.venv\Scripts\python.exe scripts\run_full_app_healthcheck.py --mode full --ui-smoke --ui-smoke-switch-tabs --ui-smoke-screenshot --ui-smoke-resize 1366x768 --ui-smoke-resize 390x844 --ui-smoke-dialog-cancel --output-dir output\qa\full_app_healthcheck_tmp --fail-fast
```

這會在隔離子程序啟動真實 PySide6 MainWindow、逐一切換左側主導覽的 9 個主工作區、保存 startup / resize screenshots、記錄 requested / actual viewport size，並測試 UpdateView 強制重新合併 dialog 的取消路徑。`startup.png` 會在切換工作區前擷取，代表實際初始頁；`resize_*` 則是各指定 viewport 的畫面。`--ui-smoke-dialog-cancel` 只會按取消，不會按確認；若 destructive action 被呼叫，healthcheck 會失敗。Smoke 子程序會自動把 `DATA_ROOT`／`OUTPUT_ROOT` 指到報告目錄下的隔離 `_isolated_app`，因此不會因正式 SQLite 的唯讀權限而在啟動階段中止，也不會改寫正式資料。1024×768 與 1440×900 是目前決策工作台／主導覽的基本 desktop viewport；report 應為 `matched`，仍需人工開圖判讀文字與按鈕的可讀性。

若正式 `OUTPUT_ROOT` 或 Research Run Registry DB 是唯讀，策略回測頁仍會開啟計算與唯讀證據檢視；「保存結果」與 Registry 比較會停用，設定面板會顯示 `Research Run Registry` 的具體錯誤。這代表研究結果持久化尚未可用，請先修正輸出路徑權限或指定可寫的 `OUTPUT_ROOT`，不要把空白 Registry 當成沒有歷史資料。

## 操作補充與維運參考

### 2026-10-03 週度研究採集與讀回

每週入口是 `scripts\scheduled\run_v2_2_weekly_collection.cmd`；它委派 `scripts/scheduled/weekly_collection_controller.py`，先執行既有 core sidecar collection，只有 core exit code 為 0 才啟動兩個研究 child：MOPS statement availability 與 quarterly OpenAPI。不要只看 Task `LastResult` 推定業務完成，也不要把兩個 child 當成正式基本面寫入。若要手動唯讀核對，請提供同一 `OUTPUT_ROOT` 與 Quick status：

```powershell
.\.venv\Scripts\python.exe scripts\audit_scheduled_research_acquisition.py `
  --quick-status "<OUTPUT_ROOT>\scheduled\data_update_quick\latest_status.json" `
  --output-root "<OUTPUT_ROOT>" `
  --output "<隔離 QA 目錄>\weekly_audit.json"
```

`--output` 是本次 audit 摘要的位置，應指定隔離 QA 目錄；此 audit 讀既有 receipts，不啟動 weekly producer。Freshness probe 的 weekly 輸入亦由明確 `--output-root` 對應 locator。只在受控驗證要覆寫 parent receipt 位置時，才加 `--weekly-parent-receipt-path` 與 `--weekly-parent-receipt-sha256`，必須同時提供兩者。

控制器在實際 `OUTPUT_ROOT` 下以 `scheduled/v2_2_weekly_collection/latest_status.json` 發布唯一 locator，並將每次 start／terminal receipt create-only 保存到 `scheduled/v2_2_weekly_collection/controller_runs/<run_id>/`。locator 只負責指出本輪精確 receipt path、bytes SHA、run ID 與狀態，不是成功證據。讀回時沿 locator 的 path／SHA 取得 immutable terminal，核對 schema、run、clock 及其明列的 child 身分與 hashes；只讀它宣告的 artifact，不用 glob、修改時間或另一輪 `latest` 猜 lineage。一般 freshness／audit 由明確 `OUTPUT_ROOT` 讀 locator；若受控驗證明確傳入 `--weekly-parent-receipt-path`，必須同時傳 `--weekly-parent-receipt-sha256`，兩者缺一或不相符就 blocked。Quick 根目錄可省略時，只接受標準 `OUTPUT_ROOT/scheduled/data_update_quick/latest_status.json` 路徑推導；非標準路徑須明確指定 `--output-root`。

Quick core 發布 `pending_after_core_publication` 後，MOPS child 有 90 秒 producer 上限及 30 秒發布寬限；有效等待最長 120 秒。期限內尚未出現 child receipt 可保持 `pending`；超過 120 秒仍缺件就 blocked。若 child 已發布 `failed` 或 partial，不能因 parent marker 尚在寬限內而改成 pending。Weekly freshness 自 parent 的 `started_at_utc` 起對同一 run 計算總等待窗 1,170 秒，邊界包含第 1,170 秒；期限內缺少 terminal 才是 pending，逾時且仍缺件為 blocked／需重驗。部分完成、review items、blocked、failed、skipped 與 pending 必須分開判讀；child 失敗不改寫 core 的 exit／`pending_human_review`。重試要開新 run 與新 receipts，不編輯或覆寫舊資料。

`verified` 代表 parent／child 身分與 immutable receipt 綁定讀回通過，不是來源資格。2026-10-03 受控 run 的 core 為 `pending_human_review`，MOPS 為 `captured_verified`，quarterly 為 `captured_with_review`，且 `formal_credit=false`、仍需人工 review。月營收、季度數值與信用交易候選均不因此取得正式來源接受、公告可得時間、historical PIT、單位／issuer denominator 或交易資格；週採集不改正式基本面 CSV／DB、Recommendation 或正式 pointer。

最新受控週度 readback（2026-10-03 09:27 UTC）的 quarterly OpenAPI child 有 26 個 endpoint 回應、3,958 筆 raw numeric rows、3,950 筆 preview rows；這批候選的 `available_at` 全部為 null，必須維持 research-only。parent／child 綁定讀回已通過，但 core `pending_human_review`、MOPS `captured_verified`、quarterly `captured_with_review`；這些狀態不把缺失可得時鐘補成正式 PIT。readback：`output/qa/integration_20261002/weekly_actual_20261003T092700852463Z/readback.json`（SHA-256 `53364a1c330253e2a7afe57f41602cfa20690ddb4aa31b59123e9f6e5dcfb890`）。

### 2026-09-29 排程完整審視與修復

21 項 Windows task 的查詢、same-day Evidence 身份、technical receipt 重用、官方 taxonomy
接線、PIT coverage scope 與 ML 等待中斷判讀，見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-29-排程完整審視與修復)。
修正程式不等於現有 failed receipt 已變為成功；仍需下一次自然執行與各自資料／核准 gate。

### 2026-09-30 排程執行與日期判讀
本節的 2026-09-30 日期化狀態、receipt 與當時判讀已移至[手冊日期化工程筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#2026-09-30-排程執行與日期判讀)。
現行排程操作依[21 個 Task 驗收 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)；目前狀態依 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md)。
### 2026-10-01 研究收集與排程狀態
本節的 2026-10-01 日期化研究收集狀態與當次 receipts 已移至[手冊日期化工程筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#2026-10-01-研究收集與排程狀態)。
現行排程操作依[21 個 Task 驗收 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)；目前狀態依 [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md)。
### 正式行情修復補充（2026-09-23）

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#正式行情修復補充2026-09-23)。

### 2026-09-22 歷史價格更正與舊模型

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-22-歷史價格更正與舊模型)。

### 重訓現況補充（2026-09-22）

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#重訓現況補充2026-09-22)。

### 2026-09-21 V5 日常操作與可讀性工程

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-21-v5-日常操作與可讀性工程)。

### 2026-09-21 晨間排程、候選資料與 Evidence 判讀

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-21-晨間排程候選資料與-evidence-判讀)。

### 2026-09-14 排程警告與 SQLite 鎖定判讀

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-14-排程警告與-sqlite-鎖定判讀)。

### 2026-09-15 Continuity Review Workbench R1

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-15-continuity-review-workbench-r1)。

### 2026-09-16 Personalization 真實來源唯讀檢視

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-16-personalization-真實來源唯讀檢視)。

### 2026-09-09 官方基本面現況資料

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-09-官方基本面現況資料)。

### 2026-09-10 V4 唯讀有效性與跨日證據

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-10-v4-唯讀有效性與跨日證據)。

### 2026-09-07 月營收恢復與衍生 ML 操作入口

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-07-月營收恢復與衍生-ml-操作入口)。

### 2026-08-15 prospective-only formal simulation（PFS-07）

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-08-15-prospective-only-formal-simulationpfs-07)。

### 2026-08-14 自動鏈 current state

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-08-14-自動鏈-current-state)。

### release_v4 每日工程操作（非正式 V4.0 closeout）

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#release_v4-每日工程操作非正式-v40-closeout)。

### release_v4 工程排程（不代表 V4.0 closeout）

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#release_v4-工程排程不代表-v40-closeout)。

### 全欄位資料稽核與年度 shards

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#全欄位資料稽核與年度-shards)。

### ML revalidation 與推論安全

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#ml-revalidation-與推論安全)。

### V3 pruning review package（唯讀提案）

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#v3-pruning-review-package唯讀提案)。

### 2026-07-13 系統工程整合判讀

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-07-13-系統工程整合判讀)。

### Phase 3C governed ingestion candidate CLI

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#phase-3c-governed-ingestion-candidate-cli)。

### 日常正式 Rule／ledger／PIT bounded input producer（2026-09-07）

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#日常正式-ruleledgerpit-bounded-input-producer2026-09-07)。

### 2026-09-15 關閉與跨頁研究 continuity

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-15-關閉與跨頁研究-continuity)。

### 2026-09-17 A／B／C bounded 狀態與操作邊界

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-17-abc-bounded-狀態與操作邊界)。

### 2026-09-20 ML natural shadow weekly report 判讀

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-20-ml-natural-shadow-weekly-report-判讀)。

### 2026-09-20 TPEX 背景 technical publication receipt 判讀

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-20-tpex-背景-technical-publication-receipt-判讀)。

### 2026-09-21 每日推薦 learning technical child routing

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-21-每日推薦-learning-technical-child-routing)。

### 2026-09-21 Paper EOD ledger schema readiness

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-21-paper-eod-ledger-schema-readiness)。

### 2026-09-24 推薦組合回放 Registry 保存與重啟讀回

本節完整內容見[操作手冊附冊](APPLICATION_MANUAL_SUPPLEMENTS.md#2026-09-24-推薦組合回放-registry-保存與重啟讀回)。


### 歷史：Revision-Aware 研究早期操作模板（2026-10-03）
本歷史模板與早期限制已移至[手冊日期化工程筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#revision-aware-early-template-20261003)。現行受控研究流程與接受範圍依本手冊 §7.0.1 及[整合修復 QA](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。
### 2026-10-02 Paper／quote 擷取失敗與恢復

既有 `baldr-formal-pit-sidecar-postcutoff-daily` 的 wrapper 會在合法台北交易時段帶起 `run_paper_event_source_capture_daily.py`。先讀凍結推薦與官方日曆，固定來源 request 取得回應；合法休市或沒有可處理來源時保留 no-work，不能手動改時鐘重播成當日成交。成功 durable capture 的 manifest、原始 body 與 recommendation hash 必須由 EOD consumer 再核對，capture 本身不建立 fill、不寫 ledger。

根目錄 `paper_event_source_capture.py` 是相容入口，公開函式共用 `data_module.paper_event_source_capture`，命令列共用 `scripts/capture_paper_event_source.py`。可用 `python paper_event_source_capture.py --help` 查看參數；股票來源選 `--symbols`、`--symbols-file` 或 `--recommendation-json`，凍結推薦來源另需 `--durable-root`。實際採集仍須同時提供 `--live` 與 `--confirm-live-readonly`。成功及失敗嘗試的原始回應與收據均沿用正式 producer，輸出根目錄以專案位置及明示參數解析。

HTTP 錯誤、partial read、超限或 schema 不符時，有限 raw body 與 `capture_attempt.json` 會在解析前保存，並將失敗診斷移到 status root 的失敗子目錄再清理 OS 暫存。Attempt receipt 揭露真實 request start／body completion、status、bytes／hash 與失敗型別；拒絕回應不能當有效 durable capture。無 body 的逾時仍保留失敗 receipt。最多三次嘗試，失敗請先看同次 attempt／status／log；修復來源後可用既有流程重試，不能覆寫原失敗證據或補公告時間。

若較早嘗試的暫存清理失敗，即使後次已有合法 durable capture，整體仍 `blocked`／exit 2，另外明列 `capture_status=source_capture_durable`、cleanup blockers 與保留路徑。此時要處理揭露的暫存問題，不能把 capture 存在判成整體成功。Quote observation 繼續使用原三項 fail-closed fetch 契約：HTTP 200、固定 final URL、JSON media、非空 bytes／大小／encoding／完整讀取均驗證，才進入 quote parser；Paper 的失敗 raw custody 不會放寬 quote 使用條件。MIS 的成功碼只接受具名字串 `000`、`0`、`0000` 且 message 為 `OK`，其他型別或錯誤碼拒絕。詳見 [capture QA](../06_qa/PAPER_EVENT_SOURCE_CAPTURE_FAILURE_DIAGNOSTICS_QA_20261002.md)及[本輪實際驗收](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。

## 14. 更新記錄

舊版逐次更新記錄已移至[手冊更新歷史](../09_archive/APPLICATION_MANUAL_CHANGELOG_2026_09_27.md)。第 14 節後原有的 2026-10-03 至 10-08 日期化工程／候選功能紀錄已移至[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md)；本頁保留同名標題作舊錨點導引。現行功能操作與安全限制仍由正文及[操作附冊](APPLICATION_MANUAL_SUPPLEMENTS.md)維護。

## Phase3C 2026-09-11 candidate 法人修復

受控 candidate-only 修復的完整步驟、capture custody、37 operations、history as-of 查回與 row-level rollback 規範，請見 [PHASE3C_CANDIDATE_REPAIR_RUNBOOK.md](PHASE3C_CANDIDATE_REPAIR_RUNBOOK.md)。正式資料、交易與帳務資料不在此流程範圍內。


以下標題保留舊書籤與 repo 內連結；原日期化內容已移至封存筆記。這些標題是導引，不是目前功能或操作保證。

### 個股研究來源恢復與現況基本面更新（2026-10-03）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-001)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-03 行情日期、來源排除與 Paper 研究判讀

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-002)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-04 保存來源、當下研究與持倉日期

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-003)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 自動選股的官方基本面來源與結果目錄

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-004)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 研究儲存位置與容量排錯

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-005)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-05 Current-observed 自然研究的去重、標籤與狀態

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-006)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-05 個股研究首屏與資料稽核

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-007)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 受控效能診斷入口

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-008)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 回測圖表首次開啟與盤勢關閉

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-009)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX02 共用狀態判讀（有限入口）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-010)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX16 唯讀研究來源契約

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-011)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX18 共用日特徵與個股觀察

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-012)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX18 兩條固定研究方法契約

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-013)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX19 隔離研究快照生產與讀回

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-014)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX04／05 每日研究條件與同源個股

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-015)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX13／18 具名研究母體盤勢與指標排序

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-016)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX03／06／13 原研究收藏與返回

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-017)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 UX04／05 固定方法預設與候選摘要

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-018)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 具名有界研究母體（UX16／18，2026-10-05）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-019)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 原引擎日／週排名發布與讀回（UX18，2026-10-05）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-020)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 原排名收藏與個股原來源回看（2026-10-05）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-021)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-05 每日研究鏈阻塞修正

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-022)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 研究快照儲存唯讀診斷與發布復原

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-023)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 每日研究名單：入選歷程（UX09 有界切片）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-024)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 研究歷史索引、分頁與版本復原

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-025)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 原盤勢／強弱頁共享研究來源與已開能力核對

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-026)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-05 明示研究來源配置與手動部署

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-027)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### Watchlist 項目 revision 儲存（2026-10-05）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-028)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### SQLite v1/v2 COW 遷移與明示啟用（2026-10-05）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-029)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 最終容量守衛收尾（2026-10-05）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-030)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### Legacy JSON v1 COW 與原觀察清單升級入口（2026-10-05）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-031)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 個人觀察清單：明示選擇與獨立控制檔（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-032)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 每日名單：MA 方法與家族符合度（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-033)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 個人 notes 明示選擇與舊來源唯讀（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-034)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 最新個人儲存位置決策

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-035)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 回測設定的版本化規則說明（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-036)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 從保存結果查看規則來源

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-037)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 UX20 單批 MA 研究樣本

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-038)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 UX20 具名多批母體保存與唯讀讀回

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-039)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 查看保存的多批研究母體

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-040)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 固定觀測日研究收據接受（隔離 CLI）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-041)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 執行隔離每日研究 owner

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-042)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### typed 日曆／上游 terminal 與多段執行

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-043)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 UX21 保存母體 H5／H10／H20 研究結果

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-044)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 UX21 實際來源與隔離結果保存／日報

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-045)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## UX21 endpoint label → UX22 公平比較 readiness（2026-10-06，有界研究入口）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-046)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## UX22 同源模型公平比較（2026-10-06，研究用 CLI）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-047)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## UX23 隔離 shadow 工程狀態與收據（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-048)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## UX08 推薦保存結果的同版價格／MA20／MA60（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-049)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## UX08 原生圖的縮放／平移／重設（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-050)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 明示市場CSV隔離預覽與執行CLI（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-051)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 私人覆盤與 notes 備份工程入口（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-052)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### UX23：明示 registry snapshot 的唯讀 metadata 核對（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-053)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-06 工程能力字典與模型輸入介面

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-054)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-06 中央私人三帳與原紀錄圖表接線

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-055)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-06 B14 隔離預測封存與監測 API

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-056)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-06 私人 Paper daily／benchmark 選取入口

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-057)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 9.9.1h H20 gross 每日收據與 BBANDS 上軌保存版別（2026-10-06）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-058)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

每日研究條件可選「收盤價高於布林上軌（30）」。先選已有的保存研究來源；勾選此條件只篩選該保存來源，不會自行更新快照。若要產生包含 BBANDS 的 v3 保存快照，明確勾選條件後按「更新研究快照」；其後篩選、排序、返回或收藏都沿用保存值，不重算模型或補入今日指標。條件採 AND／OR 與現有三態規則；兩 MA 預設 preset 會清除 BBANDS 勾選，手動條件可保留。

BBANDS 參數為 30 根有效 OHLC 觀測、SMA、上下標準差倍數 2.0，且只判斷收盤價嚴格高於上軌；相等不符合。30 根有效觀測不代表官方交易 session 完整。結果表分開呈現比較狀態與保存的上軌值；舊 v2 快照、缺件或暖機不足會顯示未知，來源參數 lineage 未核驗也維持未知。這是保存資料的研究條件，不是買入訊號、預測準確度或交易資格。完整 schema、來源 pin 與收藏 readback 限制見[BBUI01 QA 收據](../06_qa/BALDR_BBANDS_RESEARCH_UI_20261007.md)。

### 9.9.1i 個人 H20 每日研究預測、配置與回滾

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-059)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

#### H20目前用途與下一次排程（2026-10-07）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-060)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-07 日常有限 BB 上軌版號接線補充

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-061)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-07 中央整合：保存模型名單與自然結果

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-062)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-07 BB 第三條件與收藏

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-063)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-07 BB全母體日常v3採入補充

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-064)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## Windows 可攜版啟動畫面

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-065)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-07 真人回饋：摘要、收藏與推薦失敗

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-066)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-07 施工版：完整保存母體瀏覽

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-067)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-07 dev 修正：H20 摘要獨立於一般個股報告

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-068)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

## 2026-10-07 新候選：H20 首屏修正與真人重測

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-069)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 五規則完整保存研究入口（dev施工，2026-10-07）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-070)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 推薦理由閱讀修正（2026-10-07）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-071)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 打包版外部研究設定（2026-10-07）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-072)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 0f25 真人重驗後的閱讀與等待修正

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-073)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 單次讀取核驗與階段提示（dev，2026-10-07）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-074)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### d9 候選真人閱讀與H20重驗（2026-10-07）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-075)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 原版本收藏保存（dev，尚未包含d9候選）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-076)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 收藏重開與返回（dev，尚未包含d9候選）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-077)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 完整母體研究的獨立保存來源（dev，尚未包含d9候選）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-078)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 官方當下處置證據（dev 來源入口，尚未接完整選股 UI）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-079)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 最新工程驗證範圍（2026-10-07，dev）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-080)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 返回來源的重讀排程（dev，尚未包含 c611 固定候選）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-081)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 封存 SQLite 的私有讀取設定（dev 工程介面，2026-10-08）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-082)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 名單點擊的個股讀取（dev，2026-10-08）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-083)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 安全副本的畫面接線（dev，2026-10-08）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-084)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 完整保存母體的同次讀取與零結果（dev，2026-10-08）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-085)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 應用程式日誌與 H20 同次核驗檢視

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-086)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 推薦理由捲動與研究來源判讀（dev，2026-10-08）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-087)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 官方市場／處置保存研究（dev，2026-10-08）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-088)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

#### 開啟已保存的官方市場／處置研究

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-089)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

#### 設定全母體條件與排序

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-090)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

#### 查看個股與比較

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-091)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

#### 收藏與從觀察清單重開

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-092)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

#### 重新核驗、取消與關閉

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-093)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

#### 常見狀況

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-094)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-08 保存研究表格與完整查詢（dev來源版）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-095)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-08 資料日呈現補件（來源版）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-096)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 名單的等待、取消與重試（dev來源版，2026-10-08）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-097)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-08 H20 等待候選真人入口

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-098)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 與個股 ML 缺值文案區隔（後續來源版）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-099)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### H20 原研究與目前行情分開查看（後續來源版）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-100)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-08 93f9 獨立行情候選真人入口

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-101)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-08 H20 同份來源價格圖（來源版驗證中）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-102)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-08 F17 保存版本單次核驗（來源版）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-103)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。

### 2026-10-08 原價格條件研究、返回與收藏（開發來源版）

> 歷史原文：[封存筆記](../09_archive/APPLICATION_MANUAL_DATED_ENGINEERING_NOTES_20261010.md#manual-tail-104)；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。
