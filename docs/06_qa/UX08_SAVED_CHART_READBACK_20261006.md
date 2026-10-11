# UX08 保存價格／MA20／MA60 同版本讀回（2026-10-06）

> 本文是 10/06 新 daily parent chart artifact 的有界讀回收據。文末 UX08／stage 計數屬本次規劃快照，與其他 UX08 收據的計數母體或更新時點未調和，不可直接相加或當作目前總進度；舊保存結果的圖表補建仍不在本批範圍。

基線 `3ee80ff8c6519e392231ec3334e006d1290d079a`。只接原日研究 parent artifact 的有界圖表保存與個股 consumer，不重開已封存 UX03／04／05／06／09／15／17、F1–F4 或舊 Native gate。

## 可用閉環

`SQLiteDailyMarketSnapshotSource.load_input` 在既有唯讀 transaction／來源 pin 內讀取價格與已存 MA20／60 歷史；每日研究、隔離 producer CLI、parent capture 改用此入口。既有 `load` 四元素與舊 input positional 契約保留。只取截止日及價格日期交集、各最多120列，不重算指標、暖機或績效。

`saved_stock_technical_chart` 把 Decimal 字串／整數 DTO 封裝成獨立 `stock-research-saved-technical-chart.v1`，綁股號、完整含時區 cutoff、scope、原 feature input hash、所有內容 SHA-256。原 feature v2 artifact 只增加可選 nested 欄位；reader 接受舊欄位集合或增加此一欄位，新 chart 須核對 manifest cutoff。既有方法契約與 feature input hash 不改。圖表歷史修訂即使最新 feature input 相同，也產生不同 immutable artifact／manifest；不覆寫舊版。

價格／技術各120列、未壓縮256 KiB、encoded envelope48 KiB，仍受既有 artifact64 KiB／capture／20 GiB reserve gate。bounded zlib reader 拒絕尾巴、未完串流、超限、非 canonical JSON、版本／來源／內容 hash／日期失配及已知 cutoff 後可得資料。缺 availability 保留未知，沒有查詢時鐘代填。producer 原 staging／atomic publication／source-stable guard 保留；本包沒有正式發布或資料庫寫入。

個股 service 只讀 context 指定 parent manifest；daily identity、股號、資料日及 rank selected stock 均需一致。原排名下鑽可讀相同 parent chart，缺排名 child 仍維持 ranking unknown。圖與精確表使用同一 frozen rows：原精度、缺列／None 斷線，不插值、不補末值。未知 availability／PIT、未校正價格與未提供技術值明示。圖表資格不替代方法或排名資格：原 feature／rank 的 live revision 核對仍保留，失配時方法／排名 unknown，獨立核驗的保存圖表仍可重現。

舊推薦結果、舊日快照或其他沒有圖表 artifact 的保存來源：價格／MA history 留空，白話顯示「資料不足」「不借今天資料」。可點「另開最新研究」建立獨立 `explicit_latest_stock_research` context，移除原 run／snapshot pins；原保存來源不改寫。原排名的最新研究 signal 沿既有 host 語義保留。本包只讓新日研究 parent 生產圖表；推薦 execution writer、舊保存結果補建／遷移尚未接線，不冒稱全體 saved result 均具備圖表。

重讀同 pin 時只保留已核驗同版圖表與資料日；切換來源仍清除舊報告。背景合作取消保留上一份完成圖表、重試仍同來源、返回保持資料日與 pins；request generation／股號 gate 拒絕 stale callback。修正重讀清空資料日造成同版圖表誤失效的實際問題。

## 驗證與證據

Raw：`output/qa/ux08_saved_chart_20261006/`（不提交）。主要181通過，parent capture／daily owner／forward 隔離54通過，追加codec11與導航26通過；以 classname＋name 去重共251個不同案例。涵蓋實際 SQLite source→producer→保存→service→投影、原資料改成999或資料庫不存在仍讀100.125、新程序重讀同 manifest、MA gaps／精度、版本／身份／hash／壓縮尾巴拒絕、晚到資料、歷史修訂、原排名缺 child 不授資格、舊保存缺件及最新研究分離、取消重試返回／stale。

Workbench85、update validator25通過／4略過、full mypy813、所有修改 Python compile、quant precision／look-ahead guard與 diff check 通過。offscreen actual `StockResearchReportView` 圖、表與缺件畫面已核對：`saved_chart.png`／`legacy_missing.png`，`visual_receipt.json`保存 exact pins／cutoff／100.125／MA20=24／gap與圖像hash。這是隔離實際路徑驗證，非正式DB內容、Native或真人驗收。

保留初次失敗證據：新 subprocess assertion 誤用 DTO 欄位修正；背景 reload context 問題修正；長 Windows pytest path 改短 authorized Temp；舊保存 fixture 斷言更新為明示缺件、Advice仍通過；視覺 driver 首次未建fixture目錄、重試重建既有表錯誤及缺字型畫面均保留，最終採新目錄與明示本機字型。不以失敗輸出冒稱通過。

## 真實進度與剩餘

新日研究 parent 的價格／MA20／60 同版本 producer→reader→原生圖／精確表有限工程終點 done；UX08整項與stage4仍partial。其他指標／尺度、交易 markers、縮放平移／期間互動、圖商選型、推薦 execution writer、舊結果補建、Native／真人仍未完成。原計畫只 raw bytes append，9stage 1done／7partial／1pending、24UX 2done／20partial／2pending不變。正式／ML／training／trading／PIT旗標不提升，無 push／Task／清理／migration／fit／前景 Native。

## UX21 benchmark lane 只讀接線筆記

已只讀核對待整合 `10508947ec9e60890a1dbae2ecdd345a15e37dfc`：僅新增 adapter／test／QA三檔，API `load_explicit_market_benchmark(ExplicitBenchmarkRequest, *, cancel_callback=None, observed_at=None)`，lane35通過不是本分支整合驗收。此包沒有 cherry-pick。

最小後續接線：source 用同 decision＋H5／10／20 endpoint dates 呼叫 adapter，帶明示 benchmark name／DB source identity、currency／unit／price／corporate-action basis、逐日availability及 exact rowset／decision pins；只有 qualified research 才把 spec＋prices交既有 core。將 adapter contract／observed pins及unknown理由封進 source_contract。store 現在明確要求 `projection.benchmark is None`，runtime v1亦只接受 `benchmark=null`；須增加可選具名設定及對應版本化 readback驗證，保持舊null相容、revision identity／新程序readback與日報缺件顯示，不可只移除 guard。

目前本分支具名 benchmark 設定尚不存在，source固定None，成本只有明示 CostPolicy 或null。**現有 target source 的 corporate_action_basis=unknown、availability未知**，因此單把指數接上仍不能產生合格同basis excess。需要使用者決定實際比較基準名稱／期間含義、同期間價格與公司行動basis及其權威證據、成本政策；不能代選交易標的或將指數自然視為相容。年度計畫calendar、官方時點／custody資格另缺。adapter第一讀的觀測hash需由明示第二請求pin，不能在接線時自動把當下觀測升為使用者接受或PIT。這些是後續範圍，非本包 blocker。
