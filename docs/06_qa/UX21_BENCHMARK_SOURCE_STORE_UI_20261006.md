# UX21 明示 benchmark 的來源／保存／唯讀畫面整合（2026-10-06）

基線 `5b978df24022e165bf3366b9d7b8777c36d1e9d1`。review lane `10508947ec9e60890a1dbae2ecdd345a15e37dfc` 的715行 adapter、606行測試及QA；focused35通過後三新增檔 cherry-pick為 `57934c51`。本收據記實際接線，不把 lane 已驗當整合完成。唯一 Luna Max lane只做唯讀 Qt consumer，root整合 source／store／CLI／QA。

## 明示契約與比較

未找到屬於這條 UX21 exact parent source／store 的既定具名基準；其他 ML／backtest 的選擇不能移植成預設。runtime v1仍只接受 `benchmark=null`；runtime v2允許null或 `rule-research-explicit-benchmark-settings.v1`。明示版本、資料庫absolute path、source identity、基準名稱、幣別／單位／價格／公司行動basis、逐日availability與rowset／decision／target source pins。decision、H5／10／20 endpoint及asof由同parent與同calendar導出，不能另外選期間混算。

CLI `--benchmark-settings <明示JSON>` 或 `--without-benchmark` 互斥；不給選項就使用runtime原設定，null沒有預設代入。設定檔 raw hash／original runtime／effective version一併封存；兩份檔案均在publish前重核，來源與outcome目錄不得重疊。首次未帶pins只能顯示觀測pin與unknown，操作者明示接受後重送；接線沒有自動接受hash。

target query-only來源原為 TWD／unadjusted_close，公司行動與availability權威unknown。額外明示研究basis須與實際 target DB／schema／main-WAL revision hash相符，才可給既有PricePoint同basis研究宣告；失配blocked，未pin不採宣告。這是 caller-declared research only，不改source原unknown provenance，不授自然權威或PIT。benchmark adapter核對精確日期與basis、price／close aliases、SQLite值型態／REAL identity、pin及source-stable；未知、缺日、不唯一、來源／revision／basis失配不輸出可用spec／prices。

qualified benchmark spec與points才交原Decimal／整數bp core；同decision→同endpoint且幣別、價格與公司行動basis相容才有excess。gross/net沿原公式，成本必須有明示version／formula與target／benchmark進出bps，null／缺成本保留空值，不補0。adapter及保存qualifications固定false；方法matched／notmatched仍不等於交易selected。

## 保存與畫面

新configured保存為 saved.v2／source adapter.v2；舊saved.v1／source.v1／benchmark=null完整保留。v2封存設定與版本、基準spec／逐日價格內容身份、期間、basis／availability、observed rowset／decision pins及target source pin；contract JSON/hash、runtime設定、projection spec／points與cost version讀回再核對，跨來源替換即使重算外層identity仍拒絕。既有bounded compression／retention／20GiB reserve／atomic publish不放寬；修訂另存revision，重跑相同來源duplicate，舊收據新程序不查較新DB。

原母體收據UI唯讀展示「基準設定：具名／版本」或「未設定」，已比較行與缺件、成本版本、完整分母及H5／10／20沿同projection。沒有可比行顯示未知／空值，詳細source／basis／availability／hash留折疊診斷。CLI負責明示設定選項，UI不在舊保存收據上臨時換基準重算。cancel／retry／return／generation與receipt指紋gate保留；新的label也隨取消／換來源清空，不讓stale callback改名或舊基準掛到新收據。

## 隔離fixture與公開市場資料分報

fixture經actual SQLite source→producer／exact parent→明示benchmark request→core→store→新程序readback，驗gross excess196bp與明示成本後excess、source／revision／缺日／未知availability／target pin／basis拒絕、保存修訂與舊null相容、CLI設定來源hash、query後合作取消與重試。這些研究basis／availability是fixture明示，不能當正式歷史資料權威。

公開資料另記 `public_readonly_receipt.json`：重用原9/1 parent（1477／2382及明示排除），不重跑producer／learner；市場檔 `D:/Min/Python/Project/FA_Data/sqlite/twstock.db` 以mode=ro／query_only=1讀TAIEX四個exact日期。main／WAL pins前後不變，isolated保存duplicate與新程序相同；兩個CLI選項preflight通過。TAIEX只為本QA具名請求，沒有設使用者預設。availability只宣告本次讀取日觀測，不宣告歷史決策可得；公司行動basis與accepted pins仍缺，結果benchmark unknown／spec null／所有excess null，不以fixture合格代稱公開資料已合格。

最終受影響案例、Workbench、validator、mypy／compile／quant與offscreen圖像／hash見 `output/qa/ux21_benchmark_integration_20261006/validation_receipt.json`；raw不提交。保留review初次lane venv路徑錯誤、mypy nullable型別修正、UI深fixture Windows路徑與未show可見性失敗及最終重跑，不以失敗作通過證據。

## 完整label還缺的最小工程

| 缺口 | 最小工程／外證 | 本包界線 |
|---|---|---|
| 真正交易session與時點 | official actual-session／臨時休市revision、可得時間與custody證據，decision-time可用性核驗 | 年度計畫calendar不冒充actual-session／PIT |
| 同basis歷史序列 | target／benchmark公司行動與價格調整版本、同期間對齊及原可得證據 | caller宣告只供研究，不變自然權威 |
| 期間路徑label | 有界完整期間OHLC、高低點／停牌與缺列語義、Decimal MFE／MAE及hash封存 | 現有endpoint-only，不宣稱MFE／MAE／期間停牌已評估 |
| 成本與label版本 | 使用者明示成本／滑價／費率政策與原單位，label schema與source/version lineage | 現有四bps成本研究公式，不替使用者選政策 |
| ML consumer資格 | event／method／股號／horizon對齊、purge／embargo／資料洩漏驗證及eligibility gate | selection未知；不開fit、訓練或正式daily部署 |

benchmark工程切片done不代表完整labels、UX21全項或stage7完成；UX21仍partial、stage7pending。原計畫bytes只append；9stage 1done／7partial／1pending、24UX 2done／20partial／2pending不變。未知資格不升、無正式Task／DB寫入／個人migration／Native／push／清理／重訓；07:00UTC安全停止界線有效。


## 最終有限驗證

root final core/source/store/reader/daily92通過＋UI22通過，去重共114個不同案例；Workbench85、validator25通過／4略過／0失敗，fullmypy815、9檔compile、quant／diff通過。actual receipt offscreen兩條路已核對：公開資料TAIEX unknown與fixture qualified（gross excess196bp／net excess165bp），同收據reload文字相同、diagnostics預設收合；圖像與source／cost／population值見visual_receipt.json。視覺driver首次在選parent之前放outcome而被既有換來源gate清掉，修正為實際順序parent→outcome→reload後通過，無產品變更。原plan prefix證據與原測試失敗raw均保留。
