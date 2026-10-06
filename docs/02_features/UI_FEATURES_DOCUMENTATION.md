# UI 功能文件（Qt）

## UX13／18 具名母體盤勢與指標排序（2026-10-05）

市場探索新增研究母體盤勢，接收每日名單相同 verified snapshot，顯示明示≤16檔母體／行情日／source與方法身分，以及每固定方法三態分母。partial 缺件計未知且不偽造可開啟股票列；篩選不改盤勢分母。原排名未提供明示未知，名單按原 close／MA20／MA60 等值以 Decimal 排序，缺值固定尾端，不是投資分數。摘要短列日期、母體與方法 counts，完整來源／方法審計保留提示。操作見 [Manual共用投影](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux1318-具名研究母體盤勢與指標排序)。


### UX04／05 每日研究條件（2026-10-05）

Recommendation內切換每日研究條件與既有推薦研究來源。明示≤16股；close／MA20／MA60兩條既有條件AND／OR，符合／不符合／未知及原因分列；明確更新與read-only重讀分開。選股→個股沿同manifest與as-of，切股／返回保原清單，來源修訂顯未知與更新引導，不升格正式推薦。操作與排錯見[Manual日常研究flow](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux0405-每日研究條件與同源個股)。

### UX19 隔離研究快照來源（2026-10-05）

個股研究 service 可明示 snapshot root／cohort，經 verified reader 讀已發布 close／MA 研究快照，來源不符保留 unknown 與具名錯誤。CLI 支援同一路徑的實際 `read_report()` 讀回；桌面 UI 預設仍用 live 有限投影，本包未新增 UI 操作。來源身分／資格與操作見 [Manual UX19](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux19-隔離研究快照生產與讀回)。

## 2026-10-05 個股日特徵共用三態

正常個股研究載入後，首屏與研究理由共用既有close／MA20／MA60 snapshot的三態。暖機末段有效OHLC不足20／60筆、來源品質或日期未確認時顯示「尚無法判讀」，不再由首屏另行直比；一項未知保留另一項已確認觀察。沒有新按鈕、參數、公式或排名。舊DTO空mapping保留原呈現；必要observed-prefix不代表正式PIT／EMA／模型資格。操作與排錯見[Manual UX18](../07_guides/APPLICATION_MANUAL.md#2026-10-05-ux18-共用日特徵與個股觀察)，實際驗證見[既有QA收據新章](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

## 2026-10-04 個股來源與目前研究

觀察清單、持倉共用的個股報告在綁定前重驗同股／run／日期／來源快照；完整封存但未入選的分析可保存其排除理由，未完成或失敗的空結果不能保存。切股及改來源會立即隱藏舊內容，再由 Qt 延後釋放，避免新表格與上一份提示重疊。「查看當下獨立 ML 研究（保留保存 Advice）」讓目前研究輸出與原保存 Advice 分別可讀，並可返回原來源；基點預測、H5 自然成熟、模型資格各自列示，不把研究輸出顯示成正式勝率。

報告另列持倉觀測日及行情資料日，Exit 使用現有持倉條件唯讀結果；歷史查詢不借今天持倉。基本面保留來源單位／期間基礎，官方目前估值與上市／交易狀態顯示來源時間及 partial／unknown 診斷。操作、參數與排錯見 [Manual 的本輪補充](../07_guides/APPLICATION_MANUAL.md#2026-10-04-保存來源當下研究與持倉日期)，實際驗收範圍見 [Astra 工程收尾](../06_qa/ASTRA_ENGINEERING_CLOSEOUT_20261003.md)。

未連結持倉的研究頁首沿用同部位、同股行情快照的資料日，不再回退最後交易日；已保存來源的日期與身份保留。市場總覽另分列判斷日與實際指數行情日，缺少得分或訊號強度時顯示未知，真實零值仍為 0。

### 2026-09-22 個股研究主頁整合

左側日常導覽新增「個股研究」。既有下鑽在主程式內更新單一 `StockResearchWorkspace`，包含報告與「決策 → 結果」；返回來源只切頁並定位目前股票，保留來源篩選及報告內容。來源識別仍沿用 `ResearchStockContextDTO`，不以同股票替代 exact result identity。主程式關閉會同時取消報告與 Journey 的背景讀取。

推薦分析的個人採用、拒絕與推翻理由沿用唯一 typed Journal writer；「決策 → 結果」以唯讀、按時間排列的 append-only 歷史呈現已核驗的同結果／股票／日期／來源 snapshot 選擇。重複紀錄保留為歷史，不表示同時有效；identity 或 artifact 衝突時 fail closed，且不取代獨立的 Evidence／Outcome 狀態。操作步驟與限制見 [APPLICATION_MANUAL.md §9.9.1e](../07_guides/APPLICATION_MANUAL.md#991e-已保存推薦的個人決定與旅程回看2026-09-28)。

推薦分析另有個人模型評估唯讀區，要求使用者明確選擇目前已核驗結果的 personal capture 與 Stage C summary JSON；因目前沒有可信 result→summary 索引，UI 不掃描資料夾或猜 latest。服務重新驗證 canonical result、capture、政策、summary hash 與來源；pending／unknown、缺件及 null metrics 依 DTO 顯示，失配則拒絕並清除舊內容。這不執行 Stage C、不寫入資料、不代表自然績效，且非官方 PIT 或成交損益。操作與限制見 [APPLICATION_MANUAL.md §9.9.1f](../07_guides/APPLICATION_MANUAL.md#991f-個人模型評估摘要讀回唯讀)。

籌碼頁分列分點、法人、信用、集保持股分布與事件；級距 JSON 轉成持股範圍、人數、股數與比例，差異數調整／合計明確標示。事件顯示白話標籤，原始識別與可得時間可追溯，缺資料仍顯示缺資料，不轉成零值或評分。


> **最後整理**：2026-09-30
> **適用範圍**：`ui_qt/` 目前主要使用者介面。

### 頁面內操作說明（2026-10-05）

各頁標題的「i」開啟可捲動、可選取文字的分區說明，內容對照目前控制項與結果欄位，涵蓋操作流程、欄位單位、表格／圖表判讀及載入狀態。說明採共用 `TAB_INFO.sections` 配置，開啟或關閉保留原頁設定與結果；回測明列進階策略門檻及最佳化參數入口。完整操作見 Manual「頁面的 i 說明按鈕」。
> **狀態判讀**：目前狀態以 `docs/00_core/PROJECT_SNAPSHOT.md` 為準；未來 6 個月工程方向以 `docs/00_core/ROADMAP_6M_ENGINEERING.md` 為準；本文件只描述 UI 功能與操作入口。
> **完整操作**：安裝、逐步操作、參數、結果判讀與排錯見 [APPLICATION_MANUAL.md](../07_guides/APPLICATION_MANUAL.md)。

---

## 2026-09-21 V5 日常操作與可讀性工程

本輪把既有 read-only DTO 重新安排成「先結論、再原因、最後進階細節」的日常路徑，版本名稱為「V5日常操作與可讀性工程」。首頁 guided summary、候選／報告／持倉摘要、分層導覽、回測／推薦進階切換與個股報告 lazy tabs 均屬呈現與導引工程；正式 V4／V5 gate、自然 learning maturity 與 V6 user-level personalization 仍依 scoped roadmap 保持 pending。

### 2026-09-21 個股研究來源日期與 candidate 邊界

個股研究報告的來源表逐列呈現 `來源`、`來源狀態`、`品質`、`資料日`、`資料可得時間`、`更新狀態`、`版本`、`筆數`、`更新週期` 與 `預期資料期`；區塊標題也保留該區塊的資料日／可得時間。價格、技術、broker、institutional、credit、TDCC 與 fundamental 不能共用單一「今天」日期。這讓 9/21 price／technical 與較早的籌碼或個別 broker coverage 可以同時被正確揭露。

freshness receipt 的 `candidate_only=true` 會維持 candidate／research-only 語意，不會被 UI 或 read service 視為 formal SQLite 的 current／fresh evidence。來源缺件、PIT stale、unknown、partial 或 broker coverage gap 會顯示為品質／狀態診斷；UI 不以 0 補值、不自行跨來源補日期、不將缺件改成正常或交易訊號。1418 Paper 的 blocked 狀態若缺 source lineage，仍保留 lineage／candidate 診斷；formal 9/21 price row 可獨立呈現。

本輪 bounded formal row counts、target stock evidence、source coverage 與 focused regression 見 [2026-09-21 個股研究資料鏈 Incident QA](../06_qa/STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)。本節描述 UI 顯示契約，不宣稱所有正式資料在同一交易日 fresh，也不代表 V5／V6 formal closeout。

全市場價格跨日稽核另見 [2026-09-21 全市場跨日價格稽核](../06_qa/PRICE_JUMP_AUDIT_2026_09_21.md)：`漲跌價差` 的方向必須合併來源 sign 欄，報告 service 現在以 signed value 或 unknown fail-closed 呈現；UI 不從 close 跳幅自行判定價格合理，也不把 merged stale aggregate 當成 target-date evidence。

### 預設入口與分層

- 左側導覽分成「日常使用」（決策工作台、市場探索、推薦分析、觀察清單、個股研究、持倉管理）、「進階研究」（策略回測）與「系統維護」（數據更新、系統狀態）。保留既有 workspace key／Runtime alias；deep link 會展開所屬群組。
- 決策工作台預設先顯示「今日優先查看」與日期／資料日期／結論／下一步；「顯示進階工作台」才展開完整 workflow、來源、技術與研究證據。市場探索的 Daily Decision Desk 仍只有既有唯一實例。
- 候選池與持倉先顯示狀態、原因、來源可追溯性與下一步；完整研究、歷史、Journal、模擬／Paper／Stress 仍由進階入口進入。「選擇原推薦來源」保留在候選池的日常下一步，用來核對對應當次推薦來源後開啟原理由。

### 個股報告與結果閱讀

個股研究報告的「摘要」先列結論、證據、變化、風險、資料是否足夠與下一步；逐項證據與來源／各區塊日期由兩個進階切換控制。深層分頁進入時才建立內容；完整 OHLC 使用價格／成交量圖，缺少任一 OHLC 時使用 close chart fallback。圖表只使用 service 已提供的 DTO，不重新評分或補造資料。

UX08 原生圖安全切片：價格圖與 OHLC／量數值表共用 application 核對後投影，明示來源、截止日與實際資料範圍，保留 Decimal／整數及缺值。錯股 DTO、已知來源／日期／行指紋失配拒絕；未來與明示晚發布資料排除，缺可得時間仍未知。圖表初始化／填值失敗保留同源數值表。技術資料只有單日快照，不補歷史指標線或未核實交易標記；原生圖仍是 default，未整合 LWC／Hosted Widgets。

後續限定切片加入既存 MA20／MA60 歷史覆蓋線與同序列精確表：缺列／缺值處斷線，不補末值；保存來源缺合法歷史時明示缺件，不向 live 借值。單日技術快照仍獨立，歷史值未授予暖機／PIT資格；沒有新增縮放、平移、外部 bundle 或個人交易 markers。

推薦與回測的 guided summary 只翻譯現有參數與輸入母體。推薦保存仍保留 `result_id`、repository create-only、delivery ACK、Journal／readback 與 context binding；回測的研究模式、日期、策略、資金、費用、滑價、執行價格及停損停利值不因折疊進階而改變。結果頁的摘要、診斷、圖表、最佳化與 Walk-forward evidence 仍是原功能。

### 可讀性與安全契約

所有摘要均標出決策日／資料日／來源品質；缺件、來源不一致、身份衝突、讀取失敗與 last good data 以白話原因及恢復入口呈現。UI 僅讀取既有來源，沒有新增 collector、scheduler、正式 DB、Journal 或 learning writer；缺 cutoff 或 identity 時維持拒絕寫入與 fail-closed。完整 R1–R10 與 frozen QA evidence 見 [V5 readability acceptance](../06_qa/V5_READABILITY_ACCEPTANCE_2026_09_21.md)。

### 本輪 UI 整合修正

- 左側導覽的群組標題與 workspace 項目共用左側內容起點；展開／收合 marker、keyboard focus 與 tooltip 保留，窄版不以置中標題壓縮內容。
- 個股報告換股時會先清除上一檔報告，避免在新股票載入失敗或進階分頁開啟時殘留 A 股內容；同一檔重新載入失敗或取消時保留明示的 last-good data，並把本次失敗原因與重新載入步驟放入 Journey。來源脈絡在日常摘要維持精簡，完整 identity／mapping／snapshot trace 仍在來源進階與 tooltip。
- 持倉頁把日常摘要、進階正文、Paper health、持倉明細與模擬／歷史資料分開呈現；整頁可垂直捲動，更新狀態顯示可讀日期並保留原始 timestamp tooltip，寬／窄版 splitter 不會把操作欄位壓成不可讀細條。
- 決策工作台首頁把 machine token 轉為白話下一步與市場缺件說明；頁面說明按鈕提供可存取名稱與操作限制提示。這些是呈現／導引修正，不改資料、評分、交易或 writer 邊界。

### 2026-09-29 跨工作區版面與內容可達性

主視窗初始位置依螢幕可用範圍置中限制；長頁面、結果面板與動態內容可透過垂直捲動繼續閱讀。可列資料的表格／清單以至少五筆可見資料列作為初始 viewport 目標；表格的水平捲動、欄寬與儲存格 tooltip 協助查看較寬或較長的欄位。窄版的控制列會改為直向排列，避免長標籤與按鈕被擠成細欄；部分控制列與技術細節面板（例如 SQLite Inspector 篩選、Market Regime layer3）亦可水平捲動。這些調整只改 UI 呈現，維持 workspace 對外 widget identity、資料來源及核心計算行為。

跨頁面主視窗尺寸、巢狀分頁、表格／清單與合成長內容已完成日期化 geometry audit；六格 offscreen MainWindow 矩陣全數通過。測試範圍、合成資料覆蓋及 OS 原生視窗限制見 [UI Layout Audit 2026-09-29](../06_qa/UI_LAYOUT_AUDIT_20260929.md)。

### 2026-09-30 讀取期間的介面回應與安全關閉

Workbench 與首次開啟的 Research Console 唯讀來源載入改由受管背景 worker 執行，主視窗可先完成顯示與處理關閉事件；研究證據分頁採首次切入時才載入。SQLite progress handler 與 artifact 階段檢查合作式取消；關閉時仍會等讀取自然安全收尾，沒有強制中止 thread。關閉等待期間狀態列每數秒更新進度，完成後自動關閉；crash diagnostics 增加不含路徑／參數的生命週期階段記錄。這項修正只調整 Qt I/O 執行位置及退出協調，不改資料、績效或金融計算。

關閉回歸使用 production `main()` 與 MainWindow、隔離資料／輸出／個人政策路徑，以及各 500ms 的合成 Workbench／Research Console 慢讀。兩案例都確認讀取在背景執行緒（`Dummy-2`）、heartbeat 最大間隔 63ms、關閉事件延遲分別為 6ms／22ms、`close()` 耗時 16ms／15ms、`app.exec()` 與 OS 子程序自然退出碼皆為 0，且關閉時沒有剩餘受管 worker。此為 Qt offscreen 自動驗證，不等同於正式大資料量或 Windows 前景視窗手動驗收；可用 `scripts/qa_validate_ui_natural_shutdown.py` 重跑隔離情境。

## 一、UI 定位

2026-09-21 候選池判讀呈現更新：首頁與每日決策的候選觸發提醒改列股票代號、指標變化原因、資料日期／品質及查看步驟；缺前次分數明示無法確認新轉強。首頁一般觸發提醒可直接前往候選池；獨立風險提示仍保留其原判讀入口。候選表以「推薦來源」的已連結／未連結／來源不一致狀態取代原始 `decision_identity` 字典，完整資料保留供原推薦與結果追溯，不改觸發規則或來源綁定。操作與排錯見完整手冊第 7.1 節。

Qt UI 不是單純顯示股票名單，而是把「資料更新、候選觀察、策略研究、推薦、持倉檢查、Agent runtime 觀測」串成可回溯的投資決策工作台。

目前入口為：

- `ui_qt/main.py`
- `ui_qt/views/`
- `ui_qt/widgets/`

主要設計原則：

- UI 只負責呈現、輸入、互動與事件轉接。
- 核心計算、資料讀寫與策略邏輯必須在 service / domain 層。
- Recommendation、Backtest、Portfolio 之間的交接必須保留來源 metadata。
- 策略、回測、績效、持倉與金融金額計算不得在 UI 內新增裸 `float` 核心計算。
- 涉及回測或推薦訊號時，必須維持 Look-ahead bias 防線。

---

## 2026-09-06 閉環契約更新

- 更新／市場頁消費 App 的決策日、有效日、quality 與 warnings；來源詳情查詢不寫 manifest，市場缺歷史或未來資料不補零。Regime 匹配度不是勝率。
- 推薦保存 `recommendation-context.v1` 的 Profile／設定、來源指紋與 Why Not；啟用因子缺值不補中性分數。歷史產業篩選缺 PIT 成分證據時拒用，歷史日期仍是服務接點，沒有新增 UI 日期選擇器。
- 推薦回放新預設 `next-session-open.v2`：收盤委託、後續可交易開盤成交，期末持倉與取消狀態明示。Registry 使用執行時 frozen 版本／成本；跨版本、cancelled／partial 不混排，缺檔／損毀停止比較，UI 不 reconcile。
- 候選池名稱由 App 查詢，JSON 損毀保留原檔並顯示錯誤；候選 SQLite／精確帳本只供明確注入與副本驗證，正式 JSON／JSONL 預設未切換。Daily Desk 區分有效空池與未知，舊日期回呼不覆蓋新請求；08-B 已接上保存推薦 provider、推薦加入候選的 current_result_id 及 Workbench 新來源欄位重載；未保存結果不捏造來源 ID。
- Runtime 顯示 UNKNOWN／read state／diagnostics，關閉 observer 解除訂閱；受限事件 ID 去重不是 durable queue，重啟不執行 task。Evidence review proposal 是 App 接點，沒有新增 UI 核准按鈕。

完整操作、參數與排錯以 [Application Manual](C:/Projects/PythonProjects/technical_analysis/docs/07_guides/APPLICATION_MANUAL.md) 為準；實作與整合證據見 [TASK-08](C:/Projects/PythonProjects/technical_analysis/docs/06_qa/TASK_LOOP_08_HANDOFF.md)。本輪不改 `action_required`／V4 Evidence Accumulation，不授予 Formal credit、來源 acceptance、scheduler、broker 或正式 writer 權限。

## 2026-10-03 資料更新 freshness、Formal／Candidate 與合作式取消

資料更新狀態卡將正式 SQLite 與隔離 Candidate DB 分成不同資料 lane。服務回傳的 `FORMAL_AVAILABLE`／`CANDIDATE_AVAILABLE` 是機器狀態 token，代表來源可讀性與所屬資料根；畫面分別顯示正式資料與候選資料的日期／筆數，candidate 不會因此進入正式評分、推薦或交易。Freshness receipt 只有在目前 `DATA_ROOT`、SQLite／Candidate DB 路徑、台北市場日、04:30 cutoff 與 receipt 的實際期別相符時才投影為來源狀態；跨過 cutoff 或 live period 已變動時顯示未知／需重新驗證，重新執行唯讀 freshness probe 後再判讀。

寫入型更新的「取消目前工作」採合作式取消，worker 會在安全單位邊界停止，不強制終止 QThread；已完成的安全提交可能保留，並應再做唯讀狀態檢查。錯誤仍以失敗顯示，不因取消而清除。MOPS 月營收候選抓取取消時可留下完整 raw HTML 作診斷，但不發布未完成的 candidate CSV；訊息所列「已解析資料」筆數不能當成已可用候選。

操作步驟及排錯見 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 第 4 節；狀態、取消及 TDCC checkpoint 邊界的當前證據見[整合修復紀錄](../06_qa/INTEGRATION_REPAIR_ACCEPTANCE_20261002.md)。本段說明 UI contract，不表示 native Windows 前景操作驗收已完成。

## 2026-10-03 推薦、研究與 Portfolio 顯示判讀

- Market Breadth 的多方／空方方向要求來源變動值與方向欄位相符；缺方向、未知或衝突欄位會保留未知，不用正負號代猜。
- 技術評分只使用父層與子指標均啟用的項目。所需行情 bars 隨啟用指標週期增加，至少 60 個有效交易 bars；缺少啟用指標資料屬不可計分，不等於零分或被門檻篩除。
- 推薦空結果分成「沒有可評估候選」、「候選不可計分／來源缺件」與「已評分但未通過目前篩選／排名條件」。只有最後一種是門檻篩選後為空；不要以降低門檻處理前兩種。
- 歷史 Portfolio Alert 顯示原事件日期與來源，是保存的歷史快照，不代表目前持倉；請回持倉管理確認現況。
- 個股研究報告沿用已保存上下文的 `decision_date` 作行情 cutoff。缺漏或不合法時阻擋歷史查詢，不以今天日期替代。
- Portfolio 目前投入、已實現與未實現金額以毛額呈現，未扣費稅。費稅僅彙整已記錄資料，依原幣別列出已記錄及缺值筆數；缺件不補零，不冒充完整淨損益。

Workbench 85 項測試與資料更新頁 validator 25 項通過、4 項需真下載／合併的測試略過；另有 138 項 focused tests、750 個來源檔案的 scoped mypy 與 20 個 Python 檔案 compile 通過。完整結果見 `output/qa/integration_20261002/phase3_luna_implementation_20261003/ui/REPORT.md`。Native Windows 可見操作仍待 root 驗收。完整操作與限制以 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md) 為準。

## 二、頂層 Tab

### 1. 數據更新

主要 view：

- `ui_qt/views/update_view.py`
- `ui_qt/widgets/sqlite_inspector_widget.py`

主要能力：

- 每日股價、大盤、產業、券商分點與技術指標更新；每日股價一鍵更新包含 TWSE + TPEX，TPEX timeout 以 warning 呈現且不阻斷其他資料同步。
- TWSE 每日股價若明確回報失敗，單一來源流程會在 TPEX／SQLite／技術指標之前 fail-closed；只有已驗證的官方無交易日（`no_data_skipped_dates`）才允許後續流程繼續。
- 快速更新（跳過大型合併）與安全更新（CSV + SQLite）分流；兩者預設補齊結束日前最近 10 個工作日，快速更新跳過大型合併，安全更新保留完整 CSV 合併與 SQLite 同步。
- SQLite 狀態檢查、資料表檢視、唯讀 SQL preview，以及具有日期預設（單日今天、區間本月）、完整日期欄寬、穩定排序、重複顯示欄名防護、分頁控制與 stale-result 防護的檢視器分頁。
- 更新狀態卡只在 service 回傳明確的 `ok`／`success`／`current`／`normal` 時顯示綠色「最新」；`error`、`missing`、`empty`、`unavailable` 與部分狀態查詢失敗會顯示異常，不會因描述文字含「最新」而假綠。inline 摘要也會把 `success`／`current`／`normal` 統一顯示為中文「正常」。狀態 payload 缺少資料源時會清除上一輪卡片與 inline 摘要，避免殘留數字或「0 筆」被誤讀；全域檢查也會同步刷新六個核心與三個候選來源頁面的 inline 摘要；個別來源詳情查詢失敗時只標記該來源，不污染其他卡片；全域檢查失敗時九個來源摘要會同步清除舊內容並保留共同錯誤原因。尚未執行檢查的 placeholder 不會被解析成狀態，燈號維持「未檢查」。候選來源仍標示為 research-only，不會因此進入正式評分或交易流程。
- 更新頁所有「今日」日期控件都以台灣市場日期為基準，不受桌面作業系統時區跨日影響；localized `不可用` 會落到異常燈號，避免被誤讀為單純待更新。
- 更新流程的進度由外層 coordinator 統一映射，技術指標子流程固定落在外層區間內；每日資料合併會回報檔案／讀取批次／寫入批次，若沒有新 CSV 會以結構化 no-op 狀態揭露「資料已是最新」，CSV 匯出會回報查詢總筆數與已處理筆數，單一工作生命週期內不會倒退，最終資料狀態檢查完成且通過後才顯示 100%。所有 CSV／SQLite／合併／技術指標／匯出寫入工作具互斥保護，重複啟動會提示等待，唯讀來源詳情仍可並行查詢；合併／匯出取消均保留原子目標檔，不在半個檔案內提交。
- SQLite sync 在寫入前會將日期、股票代號與股票名稱的受治理中英文欄位別名正規化為 canonical 欄位，並統一日期／四碼代號格式；只處理寫入副本，不改 raw CSV，缺必要欄位仍維持 fail-closed。
- 快速／安全一鍵更新先驗證更新前總覽；核心資料源若明確回報 `error`／`failed`／`exception`，會在任何寫入前 fail-closed 並回傳失敗資料源，避免在基線已不可讀時繼續產生部分更新。
- SQLite Inspector 啟動與刷新採明確 `mode=ro`／`PRAGMA query_only=ON`；資料庫不存在、損毀或不可讀時保留頁面並顯示「SQLite 不可用」，不建立空資料庫，也不讓主視窗因 Inspector 初始化失敗而中止。若使用 immutable fallback，頁首會明示快照可能非即時。
- UpdateService 的 overview／detail／technical coverage 狀態查詢共用同一個 query-only adapter；不論資料庫是否已存在，狀態讀取都不建構可寫 `DBManager`、不初始化 schema 或切換 WAL。
- Portfolio 的目前價格／未實現損益投影也共用 query-only adapter；缺少正式 SQLite 時只降級讀取既有 CSV，不會因打開持倉頁而建立空 `twstock.db`。
- Windows 一般 read lock 不可取得時，狀態 payload 會帶 `read_mode=immutable_fallback` 與提醒；UpdateView 以黃色「待更新」及 inline `讀取模式`／`提醒` 揭露可能只到最後已提交內容，不把快照假裝成即時讀取。
- 每日股價分頁的 TPEX 背景補齊會在頁面內顯示 `尚未啟動`／`執行中`／`完成`／`失敗` 與最後更新時間；狀態 JSON 無法建立或讀取時會顯示錯誤並記錄日誌，無法可靠追蹤時不啟動背景程序，避免按鈕已顯示執行中但沒有可查進度的假狀態。日期範圍同步若發生例外也會保留可見日誌。
- UpdateView 內容使用可垂直捲動的工作區；窄版（小於 720px）會將來源導覽移到上方、六張核心狀態卡改為雙欄、候選卡改為單欄、操作按鈕改為直列，避免固定 160px 導覽與六欄卡片把資料更新畫面壓成不可讀細條。
- 券商分點資料更新、合併、長碼解密與品質狀態呈現；SQLite `broker_flows` 唯一鍵包含 `trade_type`，可保存同日買超 / 賣超榜單。
- 「三大法人」、「信用交易」、「集保股權」與「自動排程狀態」為唯讀治理頁；前三者只讀 SQLite 筆數／最新決策日期，`MISSING` 或 0 筆代表未接線或尚未匯入，不能解讀為中性數值，也不提供誤導性的下載控制。

文件同步重點：

- 更新流程改動需同步 `docs/03_data/` 相關指南。
- SQLite / CSV 雙軌行為改動需同步 `docs/01_architecture/system_architecture.md` 與 `docs/03_data/SQLITE_STORAGE_GUIDE.md`。

### 2. 市場探索

主要 views：

- `ui_qt/views/decision_desk_view.py`（「市場總覽」唯一 Decision Desk instance）
- `ui_qt/views/market_regime_view.py`
- `ui_qt/views/strong_stocks_view.py`
- `ui_qt/views/weak_stocks_view.py`
- `ui_qt/views/strong_industries_view.py`
- `ui_qt/views/weak_industries_view.py`
- `ui_qt/views/smart_money/smart_money_flow_view.py`

子 Tab：

- 市場總覽
- 大盤指數
- 強勢個股
- 弱勢個股
- 強勢產業
- 弱勢產業
- 主力流向

主要能力：

- 市場總覽以 answer-first dashboard 顯示結論、焦點與來源可見性；Workbench「決策來源」只導向此唯一實例，不建立第二份 widget。
- 月營收、三大法人、信用交易、TDCC 與券商分點卡片保留 status、row count、available date、coverage 與 warning。`row_count=0`／MISSING／DEGRADED 表示缺漏，不是中性分數或業務數值為零，且不參與 action、focus、Score 或品質聚合。
- 「資料更新 > 全部資料」的月營收狀態卡分開顯示已匯入期別與依該期全部資料 `available_date` 判定的目前完整 PIT 可用期別；只要同一期仍有公司尚未生效，該期就會顯示在待生效數與完整可用起始日中，不會誤標成更新失敗。
- 市場 regime 判斷。
- 強弱勢股票與產業篩選。
- 強弱勢探索表格會在載入中、成功（筆數／掃描範圍）、空結果與失敗時顯示可見狀態；刷新失敗會清空過期模型，不把上一輪排名留在畫面上冒充目前資料。
- Smart Money Terminal：個股資金流向、分點進出追蹤、張數 / 金額品質標示。
- 券商 week／month／股票明細採背景查詢並具 stale-result guard；loading 與單一來源錯誤不凍結主 UI，錯誤以 fail-soft warning 呈現。
- 可把觀察標的送入候選池 / Watchlist。
- 候選池在載入中、成功、空清單與失敗時都顯示可見狀態；空清單／失敗使用真正的空模型，不插入 `-` 佔位列，避免把狀態提示誤讀為候選標的。
- V4.2 C 線的市場焦點卡接到共用 `DecisionPresentationDTO`，顯示研究動作、證據品質、理由、風險、資料日與來源追溯；市場焦點仍是研究輸入，不直接產生正式 Advice 或買賣指令。

文件同步重點：

- 籌碼、分點、資料品質語意改動需同步 `docs/04_broker_branch/`。
- Regime 或 scoring 輸出語意改動需同步 `docs/02_features/SCORE_EXPLANATION.md`。

### 2.5 決策工作台

主要 view / model：

- `ui_qt/views/workbench_view.py`
- `ui_qt/models/workbench_table_models.py`

主要能力：

- Phase 2 Unified Decision Workbench MVP shell，頂層分頁名稱為「決策工作台」。
- 總覽第一屏新增「今日行動中心」：只用既有 `WorkbenchDashboardDTO` 的資料狀態、review items、Advice DTO 與 Action Items，整理資料／市場／Advice／持倉四張行動卡與一個下一步按鈕。按鈕僅呼叫既有數據更新、Daily Decision、推薦分析或持倉管理導覽 callback；不讀 DB、不更新資料、不執行 Policy、不寫入持倉或交易。
- 主 shell 使用 `ui_qt/widgets/adaptive_workspace_stack.py`，只讓當前可見工作區貢獻尺寸提示，避免隱藏工作區的圖表／設定面板鎖死視窗最小尺寸；主視窗在窄桌面寬度會暫時收合左側導覽，但不改變 workspace、資料載入或 service 行為。
- Runtime 窄版（小於 720px）會把治理左右面板改為上下排列，並以內嵌垂直捲動保留完整診斷內容；Session context status strip 會依可用寬度截斷文字。主視窗明確窄版下限為 320px，避免 Runtime 的長路徑提示把視窗鎖在桌面尺寸。
- Runtime 窄版（小於 720px）會把治理左右面板改為上下排列，並以內嵌垂直捲動保留完整診斷內容；Session context status strip 會依可用寬度截斷文字。主視窗明確窄版下限為 320px，避免 Runtime 的長路徑提示把視窗鎖在桌面尺寸。
- 第一版已從中文 read-only shell 推進到 background evidence feed / read-only Action Items 人工佇列體驗，並完成 Phase 2 read-only Operating Loop closeout：呈現 status strip、今日待判讀、背景證據流、依 severity / queue group / source 排序的只讀 Action Items、操作節奏、Evidence mode / data quality、Daily Checklist、warnings / degraded source。
- 只透過 `WorkbenchSourceService` 取得 `WorkbenchDashboardDTO`，或直接呈現呼叫端提供的 DTO；UI 不直接讀 SQLite、不讀 replay DB、不寫 DB、不啟用 scheduler。
- 主程式開啟後，Workbench 首次讀取與重新整理由受管 `TaskWorker` 在背景取得唯讀 DTO，不會在建構主視窗時同步讀資料；Research Console 只在第一次切入「研究證據」分頁時載入。SQL／artifact 讀取支援合作式取消；主視窗關閉會取消這兩項讀取並等待安全結束，舊日期／成本情境結果不會覆蓋最新請求。狀態與關閉診斷只記錄階段、耗時與 worker 數，不改 DTO、財務計算、正式資料 writer 或交易邊界。
- Workbench 的 current Decision Desk／Pre-V2／Evidence projection 以台灣市場今日為日期上限；正式來源若含 future snapshot，畫面保留 raw future date 的 warning／source gap，但不把它當成 current evidence 或完成 gate。
- 背景證據流只彙整既有 DTO / service payload：Daily Decision snapshot、Evidence Review readiness、Portfolio alerts 與可選 replay summary diagnostics；不在 UI 端重算任何 source gap、portfolio、scoring、backtest 或 lifecycle。
- 只讀 Action Items 只列人工待處理事項；每列必須帶 `severity`、`queue_group`、`source_label`、`source_trace`、`degraded_reason`、`sort_rank` 與 `drilldown_target`，且 `write_intent=false`。Qt model 只顯示 DTO payload，drill-down target 必須對齊舊頁導向（Daily Decision、Evidence Review、Portfolio），Workbench 不建立 action item repository、不 append DB、不自動標記完成。
- Read-only Operating Loop 只從 `WorkbenchDashboardDTO.operating_loop_steps` 顯示 daily first-look、manual queue、weekly review history、multi-day dry-run、manual review note 與 scheduler gate；每列必須帶 `source_trace`、`linked_item_ids`、`drilldown_target`、`guidance` 與 `write_intent=false`。Qt model 不標記完成、不寫 DB、不補 Phase 0 時間 gate。
- 若週期紀錄位於隔離 working-copy DB，Workbench 只會讀取 owner 明確提供的 `approved-weekly-history-projection.v1` 路徑，絕不掃描暫存目錄或合併 DB；projection 固定 `formal_credit_authorized=false`，僅顯示已具名核准的 weekly Gate 計數，不構成 formal clock credit、scheduler、交易或任何下游資格。
- Evidence Feed、Action Items 與 Operating Loop 空狀態必須說明「目前沒有 DTO rows」不等於 gate passed 或 actionable 建議；degraded 狀態只提醒人工覆盤資料不完整，不補值、不觸發 replay / scheduler / lifecycle。
- Advice 區以 `WAITING_FOR_ADVICE_DTO`、`NO_ELIGIBLE_ADVICE`、`ADVICE_DTO_ERROR` 分別呈現尚未載入、已載入但無合格建議、與 DTO 損毀／安全拒絕；來源降級但仍有有效 recommendation 時仍渲染表格與 warning，不得誤標為 DTO error。
- V4.2 C 線把決策工作台、Daily Decision／市場總覽、產業探索、觀察清單與持倉覆盤標成單一路徑：`市場總覽 → 產業／市場探索 → 關鍵股研究 → 觀察清單 → 持倉覆盤`。Workbench 提供市場、產業、觀察清單與持倉導覽；關鍵股研究則由市場焦點、觀察清單或持倉列選取個股後，透過 `ResearchStockContextDTO` 開啟個股研究報告。
- 市場焦點、觀察清單分析、Advice、持倉詳情與個股報告共用 `DecisionPresentationService`／`DecisionPresentationDTO` adapter；所有畫面分開呈現排名分數、校準機率、成本後獲利機率、動作適合度、證據狀態／信心、樣本數、適用期間、理由、風險、失效條件、權重差距、決策日、資料日與來源追溯。排名只作排序，不能推導任何機率；缺值固定顯示未知／研究中並 fail-closed。
- 觀察清單以研究／等待與買進候選的既有來源理由、風險、失效條件為主；持倉則將既有 condition monitor 的 valid／warning／invalid 映射為持有／減碼候選／退出候選，並揭露 target／current／gap 權重與成本基準。這些都是唯讀判讀與候選分類，不是自動下單、調倉或平倉。
- 相關決策頁面均補上 status、decision/data-as-of date、source trace 與可返回來源的 context；研究報告沒有來源時隱藏返回控制，避免製造虛假導覽。表格採單列選取、禁止編輯、StrongFocus、Tab 導覽、交替列色與窄版捲動；完整證據移至可選列的詳情區，避免主表塞入低價值長文。
- 共用 adapter 對不支援的 Advice DTO 或非法 bp／機率欄位拒絕適配，不把 ranking score 轉成 probability，也不由 UI 補算權重差距或核心金融數值；契約測試涵蓋欄位分離、字串 bp 正規化與缺值狀態。
- Optional Historical Replay JSON summary 只作 simulated evidence input；若 DTO 帶 replay summary，data quality 區塊必須揭露 `simulated_scheduler`、source gap、payload gap、outcome maturity、benchmark coverage、missing industry benchmark 與 pending future-data。
- Workbench `Evidence` 子頁已由 placeholder 替換為唯讀 `ResearchConsoleView`：三區依序顯示固定 fail-closed Safety Boundary、Development Dataset V0 / Rule baseline / ML challenger / E2E frozen projection，以及 EV1–EV5、P0-13、獨立 Broker lane、P0 Data Source Control Center 與 Artifact Inspector。Control Center 固定保留 13 個 P0 source，顯示 contract、machine/audit、人工 decision、blockers 與 downstream eligibility；沒有 audit artifact 時明示 `contract_only`／`Not supplied`，不把缺資料誤顯示為 ready。資料只來自 `ResearchConsoleSourceService` 的 injected mapping 或顯式 sanitized JSON path；缺 artifact / 欄位顯示 Missing / Unknown，不補零、不讀 DB、不重算 domain logic。
- Research Console 不提供 Apply、Promote、Retrain、Blend、Accept Source 或 Trade；development / candidate / provisional / degraded / fixture / replay 以文字狀態與顏色共同區分，不能解讀為 formal OOS、forward evidence、source accepted 或 production ready。
- Research Console 頂端先顯示中文結論（Rule 使用中、ML 未參與、正式輸入缺漏或投影過期），原始 machine token 與技術診斷預設收合，按「顯示技術診斷」才展開；這只改變讀取順序，不改任何 gate。

防線：

- 不重算 scoring、recommendation、portfolio、backtest 或 lifecycle。
- 不產生買賣建議、不下單、不套用 lifecycle action。
- Phase 0 weekly history 目前由具名 owner-approved projection 顯示 `3/3 ready`，但 `formal_credit_authorized=false`；multi-day dry-run 亦為 `3/3 ready`。畫面仍需明確揭露這只是 read-only readiness，不構成 Formal evidence credit 或 production scheduler approval；pending sidecar 週期仍須 owner/reviewer 審核，兩者皆不能用 fixture、手動改表或 replay 取代。

### Gate 1 Advice（決策工作台）

決策工作台在 DTO 已提供 Advice 時，會顯示 mode、decision / data-as-of date、action、理由、資料品質、可成交性、source trace，以及 Portfolio 的 target/current/gap。畫面是唯讀：不會建立委託、寫入資料庫、套用 lifecycle 或重算 scoring / portfolio / backtest。

- Guided Mode 只接受 promoted strategy；Professional Mode 的 candidate 僅供研究檢視，不能混作 formal Advice。
- `NO_NEW_POSITION`、`RESEARCH`、`AVOID` 是資料、風險、可成交性或策略狀態不符合時的正常安全輸出，不表示系統故障。
- 平衡限制為最低現金 `2000 bp`、最多 8 檔、單檔上限 `1500 bp`；UI 只呈現 contract 結果。
- Advice 不保證報酬、不是 broker 指令，且不解除 weekly evidence、production scheduler 或其他產品 Gate。

### 3. 策略回測

主要 views：

- `ui_qt/views/backtest_view.py`
- `ui_qt/views/backtest/config_panel.py`
- `ui_qt/views/backtest/result_panel.py`
- `ui_qt/widgets/fast_chart_widget.py`

主要能力：

- 單股回測、候選池批次回測、推薦組合回放。
- Strategy registry / preset / promotion 整合。
- Walk-forward、baseline comparison、overfitting risk、validation status。
- Fixed / quantile threshold mode UI 控制與無交易診斷。
- 結果保存已接入 Research Run Registry；Research Lab 內新增 Registry 比較子頁，可篩選、分頁、多選 2 至 5 個 run，顯示 comparability、參數差異、normalized equity、metrics、Regime 與保存 benchmark。推薦回放另要求完整 DTO 才能新存為 marked Registry run；單選推薦回放可走 strict reader 開啟保存的 DTO 與已驗證 child，不重新執行，也不進 legacy portfolio history dropdown。舊 markerless Registry run 明示完整 DTO unavailable；marked DTO 沒有 canonical child 時，若保存 snapshots 有推薦列則保留並標明 child 不可用；snapshots 為空則顯示沒有推薦 snapshots、canonical child 不可用。損毀或錯誤 hash 不顯示 partial 結果。Registry-based Promote Gate 已接入 service 層，且 Month 6 起需通過 lifecycle gate；策略版本 JSON 與 Registry 回填具補償與 reconciliation 防線。
- 規格化 Excel 報告匯出：單股、批次及組合回放結果的背景原子匯出，缺值自動標記 N/A。
- Fast chart renderer：權益曲線、回撤曲線、報酬分佈、持有天數。
- 策略回測日期欄與 Research Lab 證據覆盤日期篩選採受控日曆 popup；回測日期開啟時定位今天，未設定的 evidence 日期篩選也定位今天，不落到 sentinel 年份。
- Research Lab「證據覆盤 > 排程狀態」會分開顯示 freshness warnings、pipeline warning 與 advisory 的 occurrences / unique types、pipeline overall status、推薦結果 research-only write 與 production evidence / trading write risk；pipeline degraded 時不會只因 exit code 0 顯示為 passed，`ready_with_advisories` 也不會被誤標 degraded。
- Research Lab「覆盤歷史」dashboard 採 query-only history repository；缺少 history DB／table 時顯示明確唯讀診斷與建立指引，不會因打開畫面而初始化空 schema。

回測防線：

- 回測訊號只能使用決策當下可取得的資料。
- `next_open` / `close` 撮合假設必須透過 metadata 或 warning 呈現。
- Quantile 模式的門檻需由策略執行器輸出，不應在 UI 或 service 端用完整期間重算。

文件同步重點：

- 回測邏輯變更需同步 `docs/02_features/BACKTEST_LAB_FEATURES.md`。
- 策略參數與門檻語意變更需同步 `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md`。

### 4. 推薦分析

主要 view：

- `ui_qt/views/recommendation_view.py`

主要能力：

- Profile / mode / strategy config 推薦。
- Why / WhyNot / Explain panel。
- Explain 的圖形理由會顯示 rolling detector 已確認的型態名稱、方向與距確認日；若只有方向訊號而沒有型態名稱，會顯示保守的 generic 圖形訊號，不從分數臆測具體型態。
- Regime snapshot 與推薦 metadata 保存。
- 推薦結果保存與 round-trip 載入。
- 一鍵送策略回測。
- 送 Research Lab 批次回測。
- 推薦結果表的單股研究按鈕、雙擊與右鍵入口會建立 `ResearchStockContextDTO`，帶入股票、決策日、資料日、結果 ID、Profile 與來源 workspace；市場探索頁的共用 context strip 可顯示這些欄位並返回來源清單。
- 建立候選池 / Watchlist。
- Fixed / quantile 門檻模式與 eligible universe 橫斷面百分位排名。
- 可選月營收 YoY 最低值與 PE 最高值篩選；啟用時只讀 `available_date <= decision_date` 的 PIT 基本面版本，無法標準化決策日期、缺 PE／去年同期營收或不符門檻者寫入 screening matrix 的 `skipped` 原因，不補零也不讀未來資料。
- 目前推薦 Excel 報告匯出：包含今日配置、Regime 狀態與股票名單的背景原子匯出。

推薦防線：

- Quantile / percentile 推薦必須先固定當日 eligible universe。
- 母體不足時應拒絕降級並顯示可理解錯誤。
- 排序需穩定化，避免相同分數因輸入順序造成結果不可重現。

文件同步重點：

- 推薦分數與百分位語意需同步 `docs/02_features/SCORE_EXPLANATION.md`。
- 推薦策略 contract 需同步 `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md`。

### 5. 觀察清單

主要 view：

- `ui_qt/views/watchlist_view.py`

主要能力：

- 候選池 / watchlist 管理。
- 從 Market Watch、Recommendation、Backtest 取得候選標的。
- 支援後續送入 Backtest / Research workflow。
- 觀察清單單股下鑽會只讀保存結果 metadata 取得來源 ID／資料日／Profile，無保存結果時保留明確缺漏，不重新計算推薦或猜測來源。
- 選取標的時以共用呈現契約顯示既有保存的排名分數、排名百分位／方法、樣本數與理由；校準機率沒有合格來源時固定顯示研究中／不可用，不補值。
- `saved` 只代表有保存的研究結果，動作適合度仍為研究；`not_in_result` 不解讀為看空，也不轉成 0 分。

文件同步重點：

- Watchlist 語意若改為正式投組、研究候選池或交易候選池，需同步 Snapshot、User Guide 與 architecture。

### 6. 持倉管理

主要 view：

- `ui_qt/views/portfolio_view.py`

右側子 Tab：

- 交易歷史
- 覆盤日誌
- Paper Portfolio
- 情境壓力
- 策略與價格監控
- 生命週期回顧
- 籌碼監控

主要能力：

- 手動記錄交易並投影目前持倉。
- 「匯入交易 CSV」先做 UTF-8／CP950、欄位、買賣別、數值、日期與重複交易 ID 預覽；只有檔案 hash 未變更且使用者二次確認後，才由 `PortfolioService.record_trades()` 批次驗證並 append，取消或錯誤不寫入。
- 交易歷史提供常駐的「刪除選取交易」操作；只有選取一筆原始交易時才可按，經確認後交由 `PortfolioService.delete_trade` 驗證剩餘交易仍可重算合法持倉。持倉彙總列不會直接刪除整檔歷史。
- 保存 Recommendation / Backtest / Strategy Version 來源 metadata。
- 顯示目前價格、未實現損益、停損 / 停利與條件監控。
- 頂端摘要只顯示有最新價格持倉的「持倉市值（未含現金）」；缺價格會顯示 N/A 與缺漏股票，不把投入金額／已實現損益冒充完整 NAV。
- 情境壓力：由 `PortfolioStressLabService` 對已標記持倉套用固定、可重播的研究情境；缺價只做部分計算，輪動／來源中斷等缺少必要輸入時 fail-closed，不寫資料、不改持倉、不產生交易指令。
- Stress 歷史：按「保存研究快照」並經明確確認後，才由 `PortfolioStressHistoryRepository` 以 hash-idempotent append-only 方式保存目前情境結果；下方歷史表由 `PortfolioStressHistoryReadService` query-only 讀取，缺 DB 不初始化，固定揭露研究用途與 `writes_allowed=false`。
- Paper Portfolio：由 `PaperPortfolioReadinessService` 唯讀讀取 daily status、append-only snapshot 與可選 Equal Weight ledger；畫面顯示 raw 累積筆數與最新可採用 snapshot，遇到 future row 會保留 blocker／diagnostic、降級並排除於 current projection。缺 snapshot、benchmark 或成本帳時明示 `partial`／`degraded`／`not_computable`，不建立 schema、不把 paper 結果冒充正式持倉或投資績效。
- Paper Trade Ledger v1：由獨立 append-only contract 保存研究用 fill event，要求 requested／filled 數量、狀態、Decimal 成本、turnover、execution gap 與來源；Portfolio readiness 會唯讀顯示 ledger 狀態與 full／partial／reject／override 統計，缺欄位不放行 weekly report。
- Paper 成交 CSV：Paper Portfolio 分頁可先預覽完整 execution CSV，要求狀態、reference／fill price、Decimal 成本、turnover、execution gap 與來源事件；只有二次確認且檔案 hash 未變更才由 `PaperTradeImportService` atomic append 至 Paper Trade Ledger，不更新手動 Portfolio、snapshot 或 broker。
- Paper 成交範本：同一分頁可先匯出只含受治理欄位標題的空白 CSV 範本；範本不填入示例成交、拒絕覆寫既有檔案，也不建立 ledger。填入真實 execution 後仍必須回到 Paper 成交 CSV 的預覽／二次確認流程。
- Paper weekly evidence v1：Portfolio 的 Paper 分頁可按「計算最近週報」，以最近 snapshot 邊界唯讀讀取 Paper snapshot、Equal Weight ledger 與成本帳，顯示毛／淨報酬、benchmark、淨超額、成本、換手與觀測日數；未來 period／snapshot、期間邊界、成本欄位或 ledger 缺件時維持 `partial`／`degraded`／`not_computable`，不補值、不寫資料。Equal Weight builder 也會在 preview／apply 前拒絕 future snapshot。
- 顯示策略版本或推薦來源追蹤。
- 生命週期回顧：顯示 thesis 狀態、來源追溯、執行落差、訊號 / 市場 / 資料品質 attribution 與摘要 tokens。
- 籌碼監控：主力淨買賣、集中度、連續流向天數與風險級別。
- 從 Portfolio 下鑽至 Market Watch 的主力流向並定位個股。
- 持倉表整合共用呈現契約的動作適合度、目標／目前／差距權重（整數 bp）與失效條件；既有 Condition Monitor 的 `valid`／`warning`／`invalid` 只映射為持有／減碼候選／退出候選的唯讀分類。
- 權重差距只接受既有 Portfolio Advice 或持倉來源摘要明確提供的欄位；缺欄位顯示未知並保留警告，UI 不由目標減目前自行推導。
- 持倉條件監控的目前 Regime／分數只讀持倉來源摘要已提供的 current snapshot；缺資料時顯示待更新，不在 UI 掃描全市場或重建推薦分數。

持倉防線：

- 金額、成本、股數、PnL 必須使用 domain/service 層的 Decimal / 整數單位。
- UI 不應自行重算金融核心數值。
- 來源追溯不能被 UI 手動覆蓋成不可追蹤狀態。

目前 Gate 4 尚未收口的部分：Paper Portfolio 的完整 cash-flow ledger、受控 Paper producer 的實際來源資料與人工 review、Equal Weight builder 的明確確認後正式 output review、Stress Lab 的正式 evidence 累積與跨期間 review。現有 UI 已能揭露 Paper snapshot／cost ledger readiness、預覽／匯入 Paper fills、重建最近週報並保存研究用 Stress history，但實際 producer 輸入、成本後證據、壓力結果與 forward outcome 的關聯及 Gate review 仍未完成。

文件同步重點：

- Portfolio 來源模型、條件監控、生命週期回顧或籌碼監控改動需同步 Snapshot、architecture 與 Manual。

### 7. Runtime Observatory

主要 view：

- `ui_qt/views/runtime_view.py`
- `ui_qt/bridges/runtime_event_bridge.py`

主要能力：

- 顯示 AI Runtime Subsystem 狀態。
- 觀測 FSM 狀態、health snapshot 與 event stream。
- 透過 Qt bridge 接收 runtime event bus。

文件同步重點：

- Runtime 狀態、事件或治理規則改動需同步 `docs/01_architecture/runtime_observatory_rules.md`。

---

## 三、跨 Tab 工作流

### 市場觀察到候選池

1. 使用 Market Watch 找出強勢 / 弱勢 / 籌碼異常標的。
2. 加入 Watchlist / Candidate Pool。
3. 候選池可送 Backtest 或作為 Recommendation / Research workflow 的輸入。

### 推薦到回測

1. Recommendation 依 Profile、Regime、strategy config 產生推薦。
2. 使用一鍵送回測或送 Research Lab 批次回測。
3. Backtest 保存 run metadata，必要時 Promote 為策略版本。

### 回測到持倉

1. Backtest run 若符合條件，可建立或輔助建立持倉。
2. Portfolio 保存 `source_type`、`source_id`、strategy / recommendation metadata。
3. 持倉後續用價格、regime、score、籌碼監控做假設檢查。

### 持倉回到研究

1. Portfolio 顯示假設失效、停損 / 停利、籌碼惡化或來源策略資訊。
2. 使用下鑽回 Market Watch / Smart Money 查原因。
3. 回到 Backtest / Recommendation 調整研究假設。

---

## 四、UI Contract

### UI 可做

- 顯示資料、表格、圖表與警示。
- 收集使用者輸入並轉成 service config。
- 轉接跨 Tab 事件。
- 顯示 service/domain 回傳的 metadata、diagnostics 與 validation status。

### UI 不應做

- 不在 UI 內新增策略核心計算。
- 不在 UI 內重算金融金額、PnL、持倉 average cost。
- 不在 UI 內用完整期間資料重算回測門檻或推薦百分位。
- 不直接寫正式資料根目錄，必須透過既有 service / repository。
- Backtest / Research Lab 的新保存入口必須呼叫 `ResearchRunService.save_run()`；UI 只能送出已完成結果 DTO 與執行快照，不可保存 stale pending result。

---

## 五、目前缺口與 6M Roadmap 對齊

近期 UI 相關缺口：

- Phase 5 大表格分頁已完成 (SQLite 檢視器分頁)。
- 規格化 Excel 報告輸出已完成；PDF 仍待完成。
- Research Run Registry 的基礎保存入口、第一版跨 run 比較 UI 與 registry-based Promote service Gate 已完成；後續仍可補更完整的 reconciliation 操作 UI。
- Factor Layer、營收估值、三大法人資料加入後，需要新增可檢查資料品質與 available date 的呈現方式。

對應文件：

- [PROJECT_SNAPSHOT.md](../00_core/PROJECT_SNAPSHOT.md)
- [ROADMAP_6M_ENGINEERING.md](../00_core/ROADMAP_6M_ENGINEERING.md)
- [DEVELOPMENT_ROADMAP.md](../00_core/DEVELOPMENT_ROADMAP.md)
- [system_architecture.md](../01_architecture/system_architecture.md)
- [BACKTEST_LAB_FEATURES.md](BACKTEST_LAB_FEATURES.md)
- [USER_GUIDE.md](USER_GUIDE.md)
- [APPLICATION_MANUAL.md](../07_guides/APPLICATION_MANUAL.md)


## 更新記錄

- 2026-10-05：內建Breadth／Relative Strength的共用與獨立SQLite讀取接入合作取消，視窗等native worker結束才退出；Native查詢中關閉及取消→正常重試通過，取消不冒充完成。四檔backend改動，UI main／view未改；原速度目標與Backtest未達項保留，見 [SQL取消收據](../06_qa/PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)。

- 2026-10-05：回測四張圖與推薦組合兩張圖延至首次結果頁使用建立；待顯示資料採快照且以最新結果取代，切回重用 widget。單張繪圖失敗保留資料、顯示提示並可再次進頁重試。盤勢關閉等待 native worker 結束；取消粒度與 Native 首次使用／效能驗證見 [階段1限定收據](../06_qa/PRODUCT_STAGE1_PERFORMANCE_IMPROVEMENT_20261005.md)，操作與排錯見 Manual。

- 2026-10-05：個股研究 ML 稽核按鈕依狀態切換展開／收合；current／saved／未知 scope 標題與日期分開，不把保存來源標成當前。歷史回顧呈現已讀回的所選日期；ML 品質降級保留具體原因，未提供時明示。操作與限制見 Manual；本輪 offscreen 與 consumer 測試不替代待驗 Native 流程。

- 2026-09-30：完成九個主工作區的長頁捲動、表格／清單五列 viewport 與主視窗幾何整合驗收；完整矩陣與 OS 原生驗收邊界見 UI Layout Audit。
- 2026-09-06：補上八卡 UI／App 契約、08-B 來源接線與正式來源／權限限制，操作細節指向完整 Manual。


## UX02 共用狀態詞彙有限切片（2026-10-05）

盤勢、持倉系統健康、選股與個股研究沿用既有DTO，透過 ui_qt/status_vocabulary.py 翻譯明確原碼；資料缺件、品質降級、載入、時間等待／休市、研究完成、研究資格與真實錯誤分開。專用詞彙保留fallback，未知碼保留，股票／持倉風險不由系統缺件推論；來源、日期及原始診斷沿既有詳情保留。Workbench與回測使用同一呈現邊界。操作、限制及排錯見APPLICATION_MANUAL的UX02段，驗證見 docs/06_qa/UX02_SHARED_STATUS_VOCABULARY_20261005.md；非全頁／全狀態重構。


## 2026-10-05 原研究收藏

「推薦分析 → 每日研究條件」選列後按「收藏此研究」，確認保存至既有觀察清單。書籤固定原來源／方法／日期／條件及排序偏好；重複相同收藏不寫，另一來源同股獨立保存。從觀察清單開個股、同查詢切股與返回都用exact書籤；無效來源不改成手動或latest。「以最新來源另開研究」只讀新研究，原書籤不變；精確移除可取消並在本程序還原。

完整參數、步驟、安全限制與排錯見[Manual](../07_guides/APPLICATION_MANUAL.md)，限定測試／Native／Library證據見[QA](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。本包不改推薦／持倉／自然ML資格，不宣告全計畫完成。


## 2026-10-05 UX04／05 固定方法預設與候選摘要

每日研究條件新增五個固定 MA20／60 查詢預設，選取後須明確套用；只篩選已核驗快照。手動條件／原來源回訪不自動覆蓋，切換預設或Decimal指標排序不改來源／日期／方法／研究資格。完整 declared 分母、已發布／缺件、組合三態、顯示／因篩選隱藏與具名原因可見；缺少 artifact 不造可開列，未知不當反證。原強弱排名未提供，選項停用；不造分數或勝率。選取摘要立即刷新，原方法identity保留詳情。

本包 final 43 affected passed、Workbench85、validator25／4skip／0fail、mypy779、compile／quant guard通過；已發布真D2382／1477 readonly offscreen及preset→收藏payload roundtrip→同源開啟／返回身份核對通過。未啟動正式／全量producer，沒有真實清單寫入／遷移、正式DBwrite、訓練、前景Native或鍵鼠；本包新增Native互動仍待下一使用者桌面時段。完整stage1–3未宣告完成，Backtest18.62%／20%未達及PIT／availability／自然ML／真人證據限制保留。詳見既有[UX16 QA](../06_qa/UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)與[Manual](../07_guides/APPLICATION_MANUAL.md)。


### UX16／18 有界母體來源契約延伸（2026-10-05，基線7e11f5a8）

明示母體設定是隔離研究批次來源：ID／版本／截至日／原檔hash、納入／排除與理由、已知或未知設定分母。可選manifest extension納入原不可變identity，讀取與consumer重新核對來源revision／刪除／成員／date；舊無設定cohort保留來源與原始分母未知。清單、母體盤勢及候選摘要共享同一契約，設定不授予PIT或推薦資格，不計算新分數。CLI明示讀included，禁止無設定手動更新默默降格已綁來源。

原排名來源audit：原計畫指StockScreener本日／本週價量強弱排序（原公式不改）。ScreeningResultDTO有period／method／version／eligible count，但即時結果未有不可變run／完整成員排除／hash發布；strong_stocks_view僅記憶體快取。saved recommendation屬另一rank kind不能代用。有限currentDB schema唯讀未找到rank／screen tables，不推論全球不存在。原排名未知且停用；需原引擎不可變結果發布工程，不稱等待自然成熟。

本包無Native前景或使用者視窗操作，無訓練、全市場producer、正式DB／registry或真實書籤寫入；永久清理仍未執行。驗證與commit結果見同章最終收據補記。

最終驗證：104相關tests、WB85、validator25/4skip/0fail、mypy781、compile13及guard通過；真D三股隔離發布／2382讀回／offscreen同源通過。詳見UX16 QA最新最終驗證章；原排名publisher與Native仍pending，未push。


## 2026-10-05 原排名研究模式

每日研究條件可唯讀選擇日／週比較與強／弱模式，來源存在且核驗相容時啟用原排名排序。研究母體盤勢共用同一來源；MA條件與原名次分開，缺排名未知，不重編篩選後名次。舊Top／Bottom百分比不可當一般前幾％或勝率；來源只授有界研究。原排名收藏已另存 v2，舊非排名研究收藏沿原 v1 契約；詳見本文最新版本化章。隔離CLI發布與參數、解讀／排錯見[完整Manual](../07_guides/APPLICATION_MANUAL.md)，[QA](../06_qa/UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)另列Native及剩餘工程。

- 2026-10-05 更新：同步原排名入口、來源限制與收藏相容性。

## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。 完整入口、步驟、參數、限制與排錯見[Manual](../07_guides/APPLICATION_MANUAL.md)，[限定 QA](../06_qa/UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)。

其他原大盤／強弱 consumer 融合、完整 feature/method dictionary、正式合格母體／排程部署、長期 storage/growth 及其他 lifecycle crash 驗收仍是第一版工程。Backtest 18.62%／20% 未達保留。正式母體權威、official availability／歷史 membership／PIT，以及舊 Top/Bottom 口徑與 numeric score 暴露屬來源／方法版本決策。Native 鍵鼠／縮放／跨頁、完整 App startup 與 3–5 位真人驗收另待桌面時段；不把工程缺件稱為自然成熟。


### 2026-10-05 UX09 研究名單入選歷程

每日研究清單新增入選歷程欄；候選與選中個股摘要保留狀態、前次日期及理由。MA 查詢的背景唯讀比較與排序／顯示篩選分離，來源不足／修訂／改版保持未知；原排名不是新的入選 predicate。操作見完整 Manual 的 UX09 小節；[限定 QA](../06_qa/UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。


## 2026-10-05 UX09 歷史索引／分頁與有限版本復原（最新）

長期保存的研究manifest以可重建SQLite派生索引查詢，32 refs／頁、固定來源／query／generation游標、64頁滑動導航窗口且可持續向更早頁讀取。背景history／explicit rebuild保持當期個股與篩選主線可用；schema／來源／hash／cancel／故障不偽造完整，原immutable來源／舊收藏不遷移。索引最多64MiB，每頁串流重核全index SHA及頁內原manifest/artifact，年度calendar以4096entries／32MiB逐份驗證，不再32份正常累積即整批未知。

限定受影響79個不重複案例、Workbench85、validator25／4skip、mypy788、11變更Python編譯與精度／未來函數guard通過。真實已保存三股來源隔離offscreen回放：晚發布仍unknown、17來源hash與正式DBsize/mtime不變、worker0；沒有讀正式DB去重核current identity。130日×2修訂合成metadata全260refs走9頁，index159744 bytes、最大page JSON13814 bytes／tracemalloc1226583 bytes；不當自然樣本或正式長期總容量證明。

本包關閉UX09索引／分頁／索引程式內版本復原；第一版工程剩餘固定F1–F4，詳細終點與owner見收據。Backtest18.62%／20%仍差1.38百分點，不重測湊數或放寬。舊1477 Native已在6691ec78通過，較早「仍待1477」文字由此更正；新分頁／跨頁Native及3–5位真人另驗。1000×835 outer／125%已接受，不新增1000×800硬門檻。具名full-cohort與原完整Top/Bottom標籤沿現況，官方全市場／新百分位方法只有擴充時才要明確決定，不阻塞目前研究限定工程。

完整操作與排錯見 APPLICATION_MANUAL 的歷史索引小節；[詳細驗證、來源選項與F1–F4凍結清單](../06_qa/UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。


## 2026-10-05 F2／F3 原市場頁共享來源與已開能力矩陣（最新）

F2／F3 在已接受的 A／A 研究限定範圍完成：原大盤指數併列具名摘要，強勢個股、弱勢個股可明示切換至每日研究名單同一 immutable 來源；日／周 × 強／弱四模式保留原完整 eligible、Top／Bottom 標籤、實際比較窗及兩種排除。榜外與研究資料缺件分欄，來源變更／清除／過期回應拒絕，切返嚴格唯讀不啟 producer。既有全市場／產業來源、母體與可比較性仍獨立，沒有用三股取代全市場統計。

能力矩陣只登記 close／MA20／MA60、close_above_ma20／close_above_ma60，完整 field／unit／warmup／missing／availability／version／cost／source 與逐股 audit 可查；官方時點及未量測成本維持 unknown。完整只相對 named declared cohort；既有 feature v2／method hash／原引擎與收藏版本不變，沒有新增正式 B 母體或方法版本。

本批驗證：43 個不重複受影響案例有通過證據（根層首9＋相容29＋實際橋接新增1＋F2 focused4；最後11頁面相容重驗為既有案例不加總）、Workbench85、validator25／4skip／0fail、mypy790、12檔編譯及精度／未來函數 guard 通過。受控小型來源驗實際背景 consumer；真實既有三股保存來源驗能力投影與 offscreen 畫面，17 來源 hash 與正式 DB size／mtime 不變、worker 0；後者沒有開正式 DB 重核 current identity，不能宣稱自然跨日證據或 PIT。詳細來源、失敗保留及回滾見本批 QA 收據。

第一版工程剩 F1（18.62%／20%，差 1.38pp；不重測微調）及 F4（整條跨頁整合、部署、長期總容量）。新 Native／3–5 位真人另驗；舊1477 Native已在6691ec78完成，不重列待辦。1000×835 outer／125%沿已接受，不加1000×800硬門檻。工程缺陷不稱等自然成熟；source/capacity／Evidence 屬另一 owner，保留其變更並排除本批提交。沒有清理、正式資料寫入、訓練、前景視窗操作或 push。

[本批詳細收據](../06_qa/F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)


## 2026-10-05 明示 research source 啟動配置

MainWindow 啟動方可明示研究 snapshot root／cohort 與 original-rank root；快照 root/cohort 成對、非空，原排名 root 不能單獨配置。研究名單初始 cohort 同步明示值，啟動仍不自動讀取／採集；無參數沿原 defaults。操作依 [完整 Manual](../07_guides/APPLICATION_MANUAL.md) 的明示研究來源配置小節；雙來源跨頁與資源終驗依 [F4 QA](../06_qa/F4_RELEASE_INTEGRATION_AND_RESOURCE_ACCEPTANCE_20261005.md)，不以 offscreen 取代 Native／真人。
## 個人觀察清單明示啟用（2026-10-06）

候選池在成對設定 personal root／既有來源時顯示「建立並啟用個人副本」。按鈕先預覽來源、個人 DB、marker、receipt、來源備份與 rollback audit；取消不建立副本，確認後才 convert／activate。未啟用來源只讀；啟用後固定 personal writer，回滾停止 writer 並保留新歷史，不切回市場來源寫入。未設定仍沿既有模式。正式 root／真實遷移／Native 尚未執行；操作與排錯見 [完整手冊](../07_guides/APPLICATION_MANUAL.md)，驗證見 [個人儲存 QA](../06_qa/PERSONAL_STORAGE_SEPARATION_LANE_20261005.md)。
