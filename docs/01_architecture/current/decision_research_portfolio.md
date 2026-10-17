# 決策、研究與 Portfolio

本冊涵蓋目前的 Recommendation、回測、研究證據與 Portfolio 責任。產品能力與 Advice 契約以 [Product Roadmap](../../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md) 為準；工程 Gate 及驗收標準以 [6M Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md) 為準；現況只看 [Snapshot](../../00_core/PROJECT_SNAPSHOT.md)。

## 模組責任

個股目前基本面另可消費明選的`OperatingSummaryReportProvider`，沿原`StockFundamentalObservationDTO`保留H1累計、TWD／percent、來源SHA、成功批次可用小時及basis核實。該版本只供2330目前查閱；`aggregate_feature_eligible`與`formal_pit_eligible`為false，不流入P07策略、P12決策擷取或績效比較。前期與成長率缺件保留，詳[具名營益資料契約](data_storage_runtime.md#具名營益目前研究版本)。

表內先列 UI、application 與資料存取入口，再列領域責任。九個工作區與 UI／application 邊界見[UI 與應用流程](application_and_workspaces.md)；產品能力與 Gate 仍依本冊開頭所列的 Product Roadmap、6M Roadmap 與 Snapshot。

| 模組 | 主要責任 |
|---|---|
| ui_qt/ | 收集使用者輸入、呈現 DTO／圖表／狀態、工作區導航與 worker lifecycle；不負責領域計算或直接維護正式資料 |
| app_module/ | 組合 Recommendation、Backtest、Research Run、Evidence、Portfolio、Position Health 等 use case、service、DTO 與 repository |
| data_module/ | 管理資料來源、reader／writer 與市場資料保存；由 application 明示注入及呼叫 |
| runtime/ | Runtime 狀態與事件服務；UI 經 application／Runtime DTO 消費，不直接讀取 Runtime store |
| `decision_module/` | 策略與評分契約、推薦排序、理由、篩選、Regime、Factor 與純計算核心 |
| `analysis_module/` | 技術指標、型態、訊號及其他分析計算 |
| `backtest_module/` | 策略模擬、台股撮合限制、成本、部位與績效分析 |
| `portfolio_module/` | Portfolio 領域帳務投影；服務組合、研究 read model 與 UI orchestration 位於 `app_module/` |
| `financial_module/` | 金額、比例、股數等核心數值單位 |
| `ml_module/` | 受治理的模型研究、校準與 shadow 路徑；不因 package 存在而取得正式推薦權限 |

<a id="entry-and-dataflow"></a>
## 入口與上下游

Windows 啟動入口為 baldr_launcher.py；桌面主程式入口為 ui_qt/main.py。UI 收集條件並顯示結果，經 app_module/ 的 composition／use case 發送明確請求。Application 組合來源與服務，經注入的 data_module/ reader 取得資料，呼叫領域模組計算，再把 DTO 交回 UI。需要保存時走對應的 application／data writer；View 不直接讀寫資料根或重算領域數值。

| 工作階段 | 責任 | 上游與下游 |
|---|---|---|
| UI／工作區 | 收集參數、導航與呈現 DTO，管理 worker 取消及過期回覆 | 使用者 → ui_qt/ → app_module/ |
| Use case／composition | 選來源、組合服務、驗證身份與保存流程、組裝 DTO | app_module/ → data_module/ reader／writer 與領域模組 |
| 資料存取 | 依明示來源提供 reader／writer 與保存資料 | 由 application 注入；市場及研究資料流向 application use case |
| 領域計算 | Recommendation、策略／回測、Portfolio、分析與金融數值各由其模組負責 | 收到 application 傳入的契約資料；結果回到 application |
| Runtime 狀態 | Runtime subsystem 持有事件與健康狀態 | application 封裝為 Runtime DTO，再呈現在 Runtime Observatory |

此圖描述目前責任方向，不表示所有資料路徑均已接線或通過產品 Gate。特定流程的實際開啟範圍仍依 Snapshot 與具名 QA 收據。

## Recommendation 與 Decision

`RecommendationService`、`ScreeningService` 及其 composition 位於 `app_module/`；`ScoringEngine`、策略契約、`StockScreener`、市場 Regime 與 Factor 契約位於 `decision_module/`。資料 provider 由 application 明示注入，Decision 層不自行建立資料路徑或 SQLite connection。

核心契約如下：

- 正式推薦權重使用整數 bp，總和為 10,000；評分與金融核心精度以 Decimal／整數治理。
- 舊設定未指定 threshold mode 時維持 fixed；quantile 為明確 opt-in。quantile 門檻只使用 T-1 以前資料，暖機需要足夠歷史觀測。
- 當日 eligible universe 先固定，再計算橫斷面百分位；同分保留同一排名語意，母體不足時明確拒絕，不靜默改用其他模式。
- 新 factor 必須保存 `as_of_date`、`available_date`、來源版本、品質與 missing policy。晚於決策日或可得日未知的資料不能供當下決策使用。
- Candidate／shadow 輸入與 formal decision layer 分開。診斷、Research metadata、保存排名或負面證據不等於正式分數、Advice 或 Promotion。
- Regime 的 `date`／effective date 表示請求的判斷日；`details.source_data_date` 表示實際可用行情日，兩者不得混用。此來源日期隨 DTO／snapshot lineage 傳遞；缺日期或超過 cutoff 時，不得借另一個資料集補值，也不改變分類或 PIT 資格。

## 回測與研究時間軸

### 計分策略的版本化因果輸入

三個原計分ID以1.1.0另立缺值方法，legacy baseline1.0及穩健／暴衝1.0.0保持。`StrategyRegistry.get_strategy_meta(..., version=...)`可唯讀查明示版本的原metadata，不建立executor；未知版本回None，不借目前預設值。分析邊界`prepare_causal_score_input`核日期／OHLCV及別名，保存缺指標；`calculate_causal_score_frame`只分析連續有報價區段並清內部ATR快取，既有indicator reuse的明示因果政策不以未來非空值決定重算。原四價全缺且量明示0的列不計分、不發新單，部分缺件或矛盾仍拒絕；不在此處補價或改Broker。

原單股producer對1.1.0 fixed／next_open保存`single-backtest-rule-execution.v3`：spec、各`*-fixed.v2`契約、政策、runtime、11個來源SHA與逐日score／score_bp／ready／signal共同綁定。原saved reader純核原件、成本與版本，不查目前Registry／executor或重算。BasicStrategySavedPairReader只比較同一方法版的穩健／暴衝，核共同10份來源與runtime／政策，混版拒絕；legacy v1／v2原保存契約不遷移。service、reconciliation及UI都保留研究不可晉升；數值因果不授歷史PIT。候選狀態與原失敗見[120 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment120-causal-score-input)。

### 四均線研究的同次來源與唯讀回訪

`baldr_ma_alignment_basic_v1@1.0.0`沿原StrategyRegistry／BacktestService／Broker及ResearchRunService；executor由同份OHLCV經既有因果SMA分析邊界取5／10／20／60期，再以Decimal比較排列及轉折。正常producer只取前180曆日最多61列供均線／前列排列，窗前不發委託、不帶部位；缺件清前列狀態並重暖機。`single-backtest-ma-alignment-execution.v1`保存同次spec、規則、10個來源檔案SHA、分析runtime、原Broker設定、輸入指紋／前置窗與逐列四MA、前後排列、訊號及原因。專用pure reader核版本、規則、排列／轉折、日期及metadata成本綁定，不查目前Registry／executor、不重算行情；原schema與共用撮合公式不改。打包新增兩份策略原始檔供同版SHA核對，宣告缺件拒絕。研究策略在service及promotion reconciliation均拒晉升；來源hash不授來源用途、歷史PIT、成本權威或績效資格。操作與平台證據見[四均線指南](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#四均線多頭排列研究)及[119 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment119-ma-alignment)。

`execute_single_backtest_with_rule_source` 對原穩健／暴衝1.0.0的fixed next_open增存 `single-backtest-rule-execution.v2`，沿同一載入／typed executor／BacktestService／BrokerSimulator，不改交易與權益。producer一次捕獲StrategyMeta，保存ScoreThresholdPolicy實際門檻與五個具名來源hash；pure identity resolver只按明示schema/id/version分流。原baseline v1、其他模式及舊run保持原契約。saved reader只讀原Registry與來源，交叉綁spec／metadata／data／execution／broker；費率核原整數單位，風控先核精確raw_params再核舊ratio*100 HALF_UP投影，不能把歷史欄名誤當真bp。正常歷史規則卡共用原dialog，fresh不查當前Registry／executor、不重算或保存。原executor缺值準備有bfill限制，完整有限行情的prefix測試與來源hash不授歷史PIT；績效仍not_evaluable。

`app_module/backtest_service.py`、`batch_backtest_service.py`、`optimizer_service.py`、`walkforward_service.py` 與推薦組合回放服務組合 `backtest_module/`。服務負責資料讀取、策略執行、結果保存與交接；UI 不自行計算訊號、撮合、權重或績效。

- `next-session-open.v2` 在 T 日收盤形成委託，於下一個有效且可交易 session 開盤撮合；停牌、零量或缺開盤時不回退到收盤價。
- 單股撮合未成交仍進入當日收盤處理，保留逐session權益、原反向取消及下一開盤使用的最近完成收盤；限價／量能／費稅／整手公式不改。預存MACD重用沿重算相同的MACD_Signal別名，原NaN及既有欄位優先保留，scorer觀測守衛不變。
- UI將total_trades標為已完成進出場配對；零配對不能推論零成交。即時摘要只讀report明示成交與期末持股，未知不補零；歷史摘要沿既有保存欄位，不重算或變更Registry格式。缺分數／門檻不推論原因，未平倉權益不當已實現損益。
- 明確標記的舊同日收盤路徑保留其舊語意；未版本化舊 run 不會被改寫成新契約。
- benchmark、特徵、標準化、篩選、停損停利與交易價格只使用決策當時可取得的資料。
- Walk-forward 的 OOS 交易狀態在測試窗起點重設；訓練窗口可提供 T-1 歷史特徵，不能把訓練期持倉或交易混進 OOS 績效。
- Replay、OOS、forward、paper 與 live 是不同證據層級。歷史回放不能替代真實決策日後的 outcome。

金融核心金額、成本、股數、PnL、權重與風控不得新增裸 `float` 計算；使用 Decimal、整數股數、整數 bp 或分為單位的整數金額。浮點數只在隔離的 analytics／展示邊界使用。

Research Lab 的保存績效由 `StrategyHistoricalPerformanceReadService` 沿Registry exact run讀回，Paper快照由 `StrategyPerformanceReadService` 沿明示strategy／version／account namespace／operation／snapshot／aware cutoff讀回。Paper catalogue只在同一READY route內作query-only有限查詢，最多200候選及截斷提示，候選不自授verified／eligible；選列後仍須公開exact reader核完整來源。帳戶每日operation SHA與ledger operation SHA分開保存，各自按原 `sha256:<hex>` 契約核對，不互相替代。兩張卡分開generation，關閉時合作式取消並等待native worker完成，失效回覆不得套用。

一般單股與批次回測的Registry保存入口先以 `research_run_dated_equity_copy` 保留實際date／日期欄或DatetimeIndex，再交既有writer以index=False保存；原曲線、金額與attrs不改，拒缺日、重複、乱序與模糊日期。舊run缺日不由requested period補造；版本化期間損益、幣別／成本、同股雙策略完整比較仍待，日期保存不授績效資格。

舊`BacktestRunRepository`的新Parquet保存沿用Registry的`normalize_research_run_json_value`：先複製DataFrame，只將attrs內有限Decimal轉成精確文字；列值、index與producer原attrs不改。這避免原曲線／交易因附註JSON序列化失敗而降級CSV，再由舊CSV reader推斷為float。既有CSV reader、SQLite REAL摘要與真正Parquet失敗時的降級行為保留；不遷移歷史、不把既有float DTO升格為精確Decimal權威。來源版保存／fresh證據與固定EXE界線見[Increment116 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment116-legacy-parquet-precision)。

Research Lab雙run完整期間頁沿同一FullPeriodPairReadV1展示兩側capture.observations的原Decimal文字，以實際日期聯集與每頁100日排列現金／持倉估值／權益及原件可選P&L。UI不讀Registry附件、不補日或重算金融；分頁不觸發reader，返回／取消／選取變更沿原generation及clear清空。來源、幣別、日曆、成本缺件與performance/PIT資格維持原reader判定，原wire shape及金融引擎不變。

通用Registry metadata comparator 遇到任一 recommendation_portfolio run 即回 incompatible，UI停用一般「比較選中」並指向兩筆exact run的完整期間診斷；直接呼叫服務也不可輸出通用績效混排或標準化權益。其他run仍沿原比較規則。這只阻止錯誤金融判讀，不補足pair的來源、日曆、貨幣、成本權威或完整績效資格。

兩個原 `1.0.0` 單股基本策略的對照另走 `BasicStrategySavedPairReader`，不從通用metadata comparability授績效。它以所選兩個 exact run 核原執行輸入、實際權益期間、共同來源hash、成本／成交設定及版本化指標，再走原 `ResearchHistoryLookup`、`StrategyHistoricalPerformanceReadService` 與保存規則卡讀回；任一缺件不並列數值。UI只投影原保存摘要，可逐側開原明細並返回同一選取，沒有新增保存格式、重算或排名資格。原規則卡的 `performance_status=not_evaluable` 必須保留；歷史PIT、成本／來源權威及完整雙策略帳本仍分開驗收。

P03正常Main由成對的外部binding path/hash解析固定cohort及既有接受錨點，經decision composition重驗全市場，注入同一reader至preparer/provider；session固定hash-bound pin及natural invocation clock，共用可用時間取較晚者，推薦context保存同pin與實際read outcomes。無配置保留原路由，部分配置／錯版本／任一必要快照失效拒絕，不fallback。合成Main父29512→新PID33656已限定驗證input/context，不代表完整推薦、官方接受或EXE；歷史/select-latest保持原版本路由。

P08 `recommendation_portfolio_period_precision_v2` DTO/codec保存精確Decimal text；原next-session-open.v2 producer現於轉float前直接捕獲實際cash／position value／equity。僅全部來源／訂單／持倉／推薦為同一精確股票時發行captured_unqualified，取消只保留partial實際列，未入迴圈fallback不是觀察；多股／需正規化代碼／三元組不符拒絕。每日realized/unrealized P&L未提供仍為None，不新增算式。新tuple不加入V1 DTO／Registry wire shape；V2 sidecar／exact reader及期間比較仍待。缺currency、來源clock/raw、正式calendar與成本authority不授真來源／績效資格。

Paper外部artifacts root為可選明示設定，缺少或無效只停用Paper查找；版本來源沿用正常Main與Research Lab共同的StrategyVersionService。此consumer不建立帳戶、不寫帳本、不改用latest；單一快照沒有完整期間曲線或底層來源可得性時，績效指標保持None／未合格。正式工作樹限定QA與正常Main／fresh／同版EXE的資格分開，最新證據見[本輪補完QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

P08 雙 run 診斷沿既有 pair／public portfolio reader，固定兩筆 metadata SHA、外部日曆原件 SHA／市場及 protected roots；V1 保留 parent，V2 交叉綁策略／parent／capture／precision。typed取消穿過 Registry、replay child 與 pair ports，不掩蓋 integrity error。Backtest controller 保留 worker 至 native finished，再重核選取、execution generation、日曆 pin 與 metadata；換版或關閉時合作取消。JSON metadata finalize 沿 staging codec 比對 Decimal text／tuple，仍拒絕既有值變更及 CAS 衝突，不新增 float 計算。限定診斷接線不授候選日曆／unknown來源資格，完整績效仍待。

原next-open producer另捕獲 `RecommendationPortfolioExecutionInputsV1`：submitted fee／slippage／tax及lot與實際effective route分列，policy metadata深層凍結，None不合併明示0。正常保存入口把原捕獲明示交給同一Registry owner，以additive V3包原V1／V2 canonical document；V3綁run／parent／真Parquet SHA、策略與原執行／成本／lot，讀回同一DTO欄位。未opt-in者維持原V1／V2，舊run不補新值；同ID更改None／0輸入會衝突。V3與V2讀前同設16MiB上限，public reader預設也拒絕超大sidecar。input SHA僅識別原輸入，不是execution或cost implementation authority；不從DataFrame／市場／cents補造source或currency。正常Main／fresh重用保存來源已限定驗證，完整績效仍待；原FAIL與QA狀態見[Increment22紀錄](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment22原producer執行輸入捕獲進行中)。

## Portfolio、Paper 與持倉研究

Increment47 為首次策略帳研究加入 `PortfolioResearchInitialSourceProvider`，由正常 Main 以原 `PaperCheckpointAccountInputs` 的 PERSONAL／合約根及同一版本服務組裝，workspace 保持可選注入，原 v3 artifact／v1 scenario store 不換版。公開策略 checkpoint DTO 增帶原 mark 證據及可選 allocation prefix；ledger 在同一 query-only transaction 驗證決策日前完整前綴與所選 operation hash，若有後續 operation（包括零成交）則拒用舊 checkpoint。週換手沿原 common-price weights／canonical turnover 及 rolling 7 日排除決策日，不加總 fill gross、不把缺件填零；舊不要求 prefix 的 reader 呼叫契約保留。

`position_health_strategy_archive` additive v2 只接同 namespace／checkpoint／原行情／可證開倉 lineage，保留原 Health baseline、evaluator、custody 與 projector。v1 策略 namespace 拒絕規則不動。prepare、原評估、publish 可由 `run_strategy_position_health.py` 明示五項身分串接；只寫衍生版本、不改交易或排程。收據固定來源／baseline／result SHA、實際 writer clock 及 Health 決策日期，重開沿原日期重核，不能以今天時間替舊版本取得 PIT。缺治理來源仍是 degraded WATCH，initial provider 拒將其當已知 Health；流動性／cooldown 未提供，沿原配置守衛。

首次比較與保存接回原 scenario service/repository；保存以原 preview decision_at 重核來源及 canonical bytes，取消只在提交前生效。UI 明選成對來源與股票、保存後同步原帳戶身分，未保存不得借舊 artifact 下鑽。原等權 construction／配置由 scenario service 外層固定 Decimal 60 精度，避免 caller prec/traps 改變結果。此為策略帳已有完整來源的限定出口；手動／聲明初次來源、未持有候選等原 P06 範圍仍待；Registry 引用路徑見下述 Increment52。

Increment68 將 P06 初次來源的研究時鐘接回原 v2 Health 收據：清單只提供 `available_at` 台北日期與 `decision_date` 相同的 checkpoint／Health 對，另計跨日才保存的收據；比較先從同 namespace 有界收據清單核精確 reference／SHA 與實際 `available_at`，再以該原時刻重建 exact account reader 與 Health reader。這避免先以今日帳本核舊 checkpoint 而混入後續 operation；任何帳本、原 mark、Health 或收據晚於原 cutoff 仍沿原 guard 拒絕，保存也用同一 preview 時鐘與 canonical artifact 重核。這是同日已保存證據的研究快照，不補歷史 PIT、未持有候選 Health／行情或正式交易資格。

手動 Portfolio 既有帳務、使用者聲明持倉、虛擬 execution trace 與 Paper Trade Ledger 是不同來源。它們的 identity、保存位置、寫入者與證據資格不能因共用股票代碼或畫面而合併。

- 手動交易不會由 backtest 或 recommendation 自動匯入；回測 run 不是實際 fill。
- 使用者聲明持倉只形成研究投影，依 cutoff、可得時間、來源品質與 snapshot hash 判讀；缺少 entry lineage 時不能當成實際成交、已實現損益或績效校準。
- Paper trade event 使用明示的 research-only identity；paper snapshot、benchmark、成本與 execution gap 必須可追溯。查詢服務不建 schema、不寫資料、不把 paper 結果轉成正式 Portfolio。
- Paper daily account 的 writer 以策略 id/version、paper account namespace、operation id、execution date、portfolio identity、aware decision／mark cutoff、selected READY route 與 policy 綁定同一 operation；金融量值採固定 Decimal context。ledger 與 state 各有獨立 SQLite transaction；兩庫之間沒有原子提交保證，`PENDING → LEDGER_COMMITTED → FINALIZED` 未到 `FINALIZED` 不可供 availability reader 當完成結果。重試必須核同一 operation identity、payload、marker/hash 與既有 checkpoint；不可跳過 partial finalize、以新 identity 重做同一 operation，或把部分提交投影成可用 Paper snapshot。
- Position Health／Exit 輸出是具來源及資料品質的 read model 或 proposal；不自動交易、平倉或改寫持倉 lifecycle。Saved Health 結果以 immutable result、receipt、baseline 與 source witness 綁定及各自 hashes 發布；writer 在發布並讀回後才簽發 aware UTC `available_at`，相同有效重試沿用原 receipt clock。這個 writer availability 只表示 exact receipt 可讀，不替代 witness 的 source availability 或 PIT 資格。讀取以 exact `receipt_id` 選取，並核 portfolio、snapshot、decision date、完整 position IDs／股票／股數及 aware cutoff；要求 receipt 可得時間不晚於 cutoff、result `observed_at` 不晚於 writer availability，且 result、receipt、baseline、source witness 的 identity／hash／scope 全部相符。缺件、晚到、identity 或 hash 不符一律拒絕；不以 mutable latest 補件。
- Portfolio research scenario 將 account kind、portfolio、snapshot、source hash、request 與 aware cutoff 綁成 exact context。`portfolio-research-scenarios.v3` 是 canonical JSON artifact payload，`portfolio-research-store.v1` 是獨立 SQL store schema，不能混為同一版本；reader 以原 bytes/hash 核版本、canonical encoding 與完整欄位，未知 schema、浮點／非有限金額或含糊 payload 一律拒絕。保存完整 cash、shares、mark、market value 與 NAV；以 Decimal／整數單位維持金額守恆，bp 僅供呈現、不反推金額，正股數即使呈現為 0 bp 仍是持倉。讀取只沿 `PORTFOLIO_RESEARCH` 明示 route，不 fallback 到其他帳戶或市場資料。
- 新增或重播資料以不同 namespace／evidence tier 保存；不得以目前市場資料補回舊保存結果。

`PortfolioResearchScenarioWorkspace` 將既有 v3 artifact／v1 store 接到 Portfolio「配置研究封存」。正常 Main 沿中央 `PersonalStoreSelection` 組合 `PORTFOLIO_RESEARCH` route；未配置不回退 legacy，LEGACY_READ_ONLY 不可 append。背景 exact read 後只允許改 request 的 explicit target；account、完整 context、原 cutoff、candidate、turnover 與 source hash 不變，現行 allocation policy hash 與原 artifact 不同則拒絕重算。另存重新核原件及預覽，再交原 repository append，不產製 Health、不讀今日市場、不寫交易。UI 以 generation 拒收舊回呼，返回個股只恢復同 artifact，不能用手動帳同股選取取代；其他帳種的初次 account/context、未持有候選仍待；策略帳限定初次來源見本節 Increment47。

Increment52 的 `PortfolioScenarioRegistryService` 與 Main 共用原 `ResearchRunRepository`，只把明確保存的 scenario 登錄為 `portfolio-scenario-registry-reference.v1`。同一 Registry SQLite 追加獨立 `portfolio_scenario_registry` 表及該名稱的 version 1 marker；原 `research_runs` version 2、metadata、Parquet 與情境 store 格式不變。不建立假本金／成本／空回測表。建構與查詢不建表，缺表回空；不相容、缺一半 marker/table、錯 columns／主鍵／trigger 一律拒絕。只有 PERSONAL 情境的明確登錄可建新表，既有 Registry v1／未知版不自動遷移。

引用 canonical JSON 上限 8 KiB，獨立 SHA 綁 record、帳種／portfolio、artifact、snapshot、decision、原保存時間、登錄時間及 input hash；資料量檢查先於 JSON 載入，列表最多 200、正常 UI 25 筆。相同來源重試保留首筆登錄，衝突不覆寫。保存與登錄不是跨庫交易，失敗保留原 artifact 可重試。開啟時固定 selection 的引用 SHA，再以原 repository exact 原件交叉核身分／時間／hash；不重算、另存或讀 latest。登錄不改原可得時間、不授 PIT／績效／自然成熟。兩個 UI 的唯讀 worker 沿 cancellation／generation／native 終態，寫入期間禁止取消與來源切換；Main 正常路由回同一 Portfolio panel 與原個股返回。

Increment40 的 `registered_strategy_spec()` 沿 public `StrategyRegistry.get_strategy_meta()` 解析同策略明確且無衝突的版本，複製原設定形成新請求。BacktestView 的一般／逐檔執行、規則卡與 Walk-forward 共用此接點；Optimizer 在行情讀取及執行組合前固定一次 metadata，每組只替換 params。缺件拒絕，不預設版本或重新標記歷史 run；原金融引擎、Registry 格式及 module boundaries 不變。版本正確不能取代 source／PIT／performance qualification，既有 UI mypy ignore 也不代表強型別。

Increment44 將 `PortfolioScenarioStockReference(account_kind, portfolio_id, artifact_id)` 接入原 `ResearchStockContextDTO`；Main 對個股 reader 注入同一 `PortfolioResearchScenarioWorkspace`。唯讀 exact 重讀後再次核 canonical hash、帳種／帳戶、外層 account source hash、原決策日及現在時鐘，再由 `portfolio_research_stock_projection` 複製原現金／NAV／股數／估值／Health／targets，不重跑金融計算。Mapping 入口也驗來源交叉綁定，失配不走目前持倉 reader；未保存預覽不冒用舊 artifact。完整帳本中無此候選持倉的 0 股與缺件錯誤分開。UI 失敗／取消／換股清除投影，普通持倉與 H20 沿原路徑；行情獨立可得時間缺件及初次來源 producer 仍未補齊。

### Saved Health 的 exact consumer 與回訪偏好

`PositionHealthExactPaperScopeFactory` 從 receipt 指定的同 route Paper snapshot 重建完整持倉 scope；`PositionHealthSavedPanel` 由正常 Main 成對注入 scope factory 與 `SavedHealthSelectionStore`。`portfolio-saved-health-selection.v1` 只保存回訪偏好，包含 receipt／result／snapshot rows hashes、decision date、完整 Paper identity、選中 position id 與分開的時鐘。不能按股票代號、最新結果或檔案 mtime 推測缺件。使用者流程見[已保存健康評估與回訪](../../07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md#已保存健康評估與回訪)。

Immutable archive reader 與 snapshot reader 保持 bounded、no-follow、regular-file／alias 與 read-only 契約。讀者重核 exact receipt、snapshot、positions、cutoffs、witness 與來源 SHA；缺件、未來時鐘、錯誤身份及晚到回呼保持拒絕／未知。Panel 只允許當前 generation 在 UI thread 提交選擇偏好，正常 close 先取消並等待 native TaskWorker 收尾；reader 不建立 schema、不產製 Health，也不操作帳本。偏好以 16 KiB 上限、精確欄位與 canonical bytes 讀回，不授來源、PIT、模型或交易資格。

## Evidence 與模型權限

P02的候選 `daily_market_technical_official_disposition_composite_query_v2` 消費同一sealed V3 group，F07價格facts與MA／KDJ／波動共用來源、母體及callback；價格範圍是既有四組AND／OR後的共通AND gate。V1四組三態計數保留，V2另列價格與最終可見計數，完整母體先排序再分頁，價格缺值置尾並以股票代碼作穩定tie-break。Result／page的逐次發行錨點核完整欄位與原V3 group，不能僅重算hash取得reader-verified資格。V2 presenter及bookmark只接受該版公開結果；bookmark恢復須由caller提供匹配的sealed V3 group，不能自行開latest。保存來源直接重播、型別及V2正常view已驗；Main新增「官方條件與價格研究」，Watchlist有獨立V2 envelope／typed add/read與schema分派，V1路徑保留。指定合成257股／雙parent的正常Main父54060→新PID34696旅程另通過，pins、query/result/page、basket、條件及scroll精確一致；首次view的scroll恢復用有界layout/range穩定檢查並綁generation/result/page/選列，確實套用後才發成功終態。此為候選限定範圍，未授原producer suite、真N、來源/PIT、Native、EXE或完整P02。具名驗證見[本輪QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

```text
Recommendation／Portfolio／Health 輸出
  → Forward outcome／Paper／Live evidence
  → 人工 review 與效果歸因
  → 保留、限制、降權、退休或另行提出 promotion
```

Evidence Event／Outcome、Research Run Registry、Evidence Review 與 Workbench read model 以已保存 metadata 和 source trace 建立可回溯投影。缺少來源、期限、樣本或可得時間時保留 blocker／unknown，不用歷史 replay 補足正式資格。Promotion、Demotion、Retirement 與 production scheduler 必須經各自受控權限，不由 dashboard、readiness 或 ML projection 自動觸發。

Paper adapter 將一般 Portfolio alerts／risk prompts 與 Paper research lane 的 alerts、risk、status、readiness、blockers 分開保存；研究 seed 不覆蓋使用者持倉。Health read model 將機器治理缺件與使用者待辦分列。排程摘要也要分辨 child return code、來源／研究資格、工程故障與使用者待辦；控制 run 的 evidence writers 留在 QA 控制 namespace，不能因 wrapper 成功就寫入正式市場、Paper 或 Evidence store。

需跨觀測日或保存樣本的研究沿明示 parent／child receipts、calendar、price point、benchmark、cost policy 與固定 cutoff 建立 exact projection。讀者重驗來源 pins，不掃 latest、不呼叫 producer、不寫 outcome store；沒有官方可得時點、benchmark 或 custody evidence 時，狀態仍為未接受。Forward close-to-close return 固定 `is_execution_pnl=false`，不可作為成交損益、next-open 回測或績效校準。

Forward rule observation producer 只接受 exact parent plan／receipt、完整 cohort／generation 與來源 cutoff 等已釘選輸入，predicate 由服務依來源資料計算；caller 不可提供 score、target、fill 或 source clock 來宣稱結果。來源 `captured_at` 不早於 parent receipt completion，parent receipt completion 不早於 source cutoff；artifact 與 receipt 寫入並讀回後才由 writer 產生 `available_at`。reader 要求 aware cutoff 不早於該時間，並重核 parent、cohort、generation、來源時鐘與 hashes。它是窄用途的 regular-file/no-follow bounded reader：單次 capture 至多 2 MiB、256 captures、保留 bytes 合計至多 64 MiB；此限額只適用此 observation reader，不是一般檔案或全域讀取預算。

sealed label readiness、模型公平比較與 shadow acceptance 可讀既有 sealed evidence／匯出 DTO，核同一 sample IDs、decision-source pins、label envelope、split 與成本契約。研究 consumer 不 fit、不改寫 registry、不啟用 model loader，也不把 read-only acceptance 轉成 promotion。Person H20 是個人研究 lane：自然成熟 caller 先核 exact completed terminal，再按完整 `current_symbols` 建獨立 cohort／daily／entry／outcome identity；一般推薦 current-observed eligible 子集合不得替代完整母體。候選 `training_as_of` 是 fit cutoff；merged-lineage manifest 的 `training_as_of` 是 lineage cutoff，兩者不可混為一個欄位。若 candidate 有獨立 `training_cutoff`，它必須等於 lineage cutoff，且 fit cutoff 不晚於 lineage cutoff；沒有獨立欄位的 legacy candidate 只有在 fit cutoff 等於 lineage cutoff 時才可讀。decision-time lane 的兩個 cutoff 均不得晚於 decision date，sample label availability 也須不晚於相應 training cutoff。歷史漏日不回填，這些 identity 規則不代表模型已具 formal 或自然成熟資格。

Recommendation ML Shadow、Portfolio Allocation ML 與 Personal H20 是不同用途及來源路徑。模型存在、訓練成功或 UI 可讀均不代表正式 ScoringEngine 已使用 ML。Formal input、自然成熟 evidence、校準、Promotion review 與 rollback 條件分別依產品 Gate 及對應 QA／運維文件核對。

P08新版 `RecommendationPortfolioPeriodPrecisionCaptureV2` 只由原next-open Decimal loop在float展示邊界前產生。Registry將capture與原V1 canonical結果包成 `recommendation-portfolio-result.v2`，同一附件沿既有staging／finalize CAS／create-only publish／reconcile／同id exact equality；service、repository及public reader依精確schema/revision路由，V1 decoder不變。Initial capital、requested日期與execution在保存／讀回都核Registry明示值；策略／成本缺件保留capture但不建立precision，來源／幣別／calendar unknown不轉資格。合成Main56200→fresh40264的opener／附件讀回已驗，雙策略全期間／UI保存、真來源、Native／EXE仍待。詳[本輪QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

P03 Selection opt-in V2攜full immutable cohort pin與row batch／first-persist identity，在DB open前及finish核全市場；clock只聲明cohort_hour_bound，仍current-only／PITfalse。V1 snapshot wrapper明確拒V2，不降格丟pin；完整V2保存／重開及consumer進度見下方，正常V2投影／UI仍待接線。

接續已以獨立 `FundamentalReadSnapshotSessionV2` 沿原copy owner完成 full pin保存／complete manifest原件SHA／外部hash reference及exact新copy重開，未改V1 schema。全必要市場在發布前再核，發布後取消不撤回已發token；讀reference仍驗原件/root/全部市場。合成父24716→fresh9700、15sourcefiles不變及983mypy/精度守衛已驗；原庫漂移具名拒收，尚無V2 raw archive繞過原庫變化。後續consumer／每日選版進度如下，正常UI與官方／PIT／Native／EXE仍待，原全Gate未接受。

接續 `DailyMarketMonthlyRevenueReadSessionV2` 與Fact／FinishedV2／SourceReferenceV3真走public snapshot，完整code分母及provider／fact雙ledger/counts各自保存；raw source kind不混舊archive V2。`daily_monthly_revenue_series` 由外部固定trust hash與最多64個明示pins／報告月選一次，固定同reader；全missing也須批次hour<=cutoff。合成100PASS／7FAIL後精確7PASS、986mypy／精度守衛與新PID51228重讀舊parent已驗，15來源不變；原F17頁面V2 query／比較／書籤、來源與Native／EXE仍待，全Gate未接受。詳[本輪QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

同日後續已接 `selection_monthly_revenue_yoy_v2`／`daily_market_monthly_revenue_yoy_index_v2`，來源與投影ledger/count獨立，原Decimal方法不變。`daily_monthly_revenue_series_binding`由external binding SHA、bounded pointer/catalog及exact cohort files構成；正常Main只注入lazy factory，RecommendationInputSession在自然invocation首次月營收使用時clone provider與固定reader/pin。失敗不回落未釘選provider，歷史路徑不選live series。Daily snapshot BOM分支保留原件bytes/stat/hash，另綁cohort canonical raw SHA，V1原拒絕不改。正常Main37740→新PID45128的30sourcefiles／fullpin／V3 Index精確重開已驗；F17原頁面的V2 typed source/query/presenter/recipe/bookmark仍待，不用私有小viewer替代。正式publisher、來源/PIT、原庫漂移archive、完整Recommendation、Native／EXE及完整Gate均未接受。

接續已補獨立Revenue QueryV2／SourceV2與ReferenceV3 artifact；F17原read session只增加typed V2方法，full declared母體、硬篩選、issuer pins、全域排序再分頁及V1路徑保留。SourceV2先取得exact F17 cutoff再呼monthly reader factory，保存pin重開則沿外部trust與descriptor/ref雙SHA，不讀mutable catalog。合成實際PID49312→4680、11月營收／參照檔及原320 F17檔不變；混合分母與精確Decimal另有限定驗證。ExactRead／Index建立、翻頁、close需同owner thread，原短命TaskWorker模式尚須接長駐序列工作階段；V2正常頁面、presenter、比較、外層bookmark／Watchlist及Main新程序仍未驗。詳[本輪QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

2026-10-14 原月營收研究頁的每日 SourceV2 已接獨立 BookmarkV2／PresenterV2 及 RevenueSourceActorV2。正常 Main 只從已解析 settings 注入 reader 或 lazy factory／exact-pin factory 與同來源 provider，來源讀取仍在使用者明示選取保存版本後發生。Actor 保持單一 owner-thread，candidate projection 完成才替換，分頁／比較不重選來源，合作 shutdown 等原生執行緒退出；V1 來源路徑保留。Watchlist V2 schema／source／ID／選股嚴格匹配，正常Main重開另讀實際保存內容，不轉一般研究context。候選實證與正常Main／新PID限度見每日政策QA；整體F17仍 current-only／availability unknown／PIT false。
### V2 自含原件封存的下層接線（2026-10-14）

原snapshot Core只共用機械copy／WAL及owner-thread守衛；V2另外發行完整daily pin的archive DTO、私有verified subject與copy binding。public facade新增create-only封存與明示exact archived reopen，Selection reader按exact V2 binding核完整pin；歷史clock／reference不改寫，logical原路徑映射到保存的完整SQLite及raw HTML／CSV樹。既有live-state exact仍拒絕原庫漂移；封存讀回改用自己保存的原件、complete manifest及完整ordered ledger，不跨schema降為V1。

底層合成父16548→新1924在原DB／HTML改變、原snapshot移開後，相同Decimal／full pin／ledger與12檔核對通過；64既有回歸、998mypy及金融精度守衛通過。此為Increment16當時的底層證據；當時consumer／Index／Source／ReferenceV3 artifact／recipe與收藏archive lane尚未整合，Increment17–18後續限定接線及交叉SHA證據見下節，不將舊recipe偷偷換來源。daily immutable市場root與trusted acceptance仍需存在。正式來源接受、publisher／Task、Native／EXE、歷史PIT及完整Gate未接受；限定QA見每日快照政策報告，工作順序沿原補完plan§9.5。

### Increment 17：Monthly／Index V2 封存研究 lane（2026-10-14）

本段更新前述下層封存段當時「consumer 尚未整合」的狀態，不刪除其歷史記錄。新增的 `DailyMarketMonthlyRevenueReadSessionV2.open_exact_archived()` 與 `DailyMarketMonthlyRevenueYoyIndexSessionV2.open_exact_archived()` 要求原 `SourceReferenceV3` 和 `ArchiveReferenceV2` 各自的 caller-provided 外部 SHA，並重驗 crossbind、完整 daily cohort pin、原 decision cutoff、完整 declared stock set，以及 provider-result／fact 雙 ledger。缺件、錯 hash、錯 scope、未來 cutoff 或已變更來源均拒絕；不回落到 live exact、latest 或 V1。一般 live exact 仍只走原 pinned-source 路徑，也不自動切換到 archive lane；caller 必須明確選擇其中一種。

`DailyMarketMonthlyRevenueReadSessionV2`／`DailyMarketMonthlyRevenueYoyIndexSessionV2` 只在完成 finish 後可呼叫 `archive_monthly_raw_sources()`，並檢查 ArchiveReferenceV2 與原 snapshot reference 的 crossbind；已封存 replay 不會再冒充另一份原始 archive。`DailyMarketMonthlyRevenueArchiveReferenceArtifactV4` 以有界雙檔封套保存原 ArtifactV3 descriptor、SourceReferenceV3、ArchiveReferenceV2 的完整 bytes。讀回只產生 Unverified DTO；外部 descriptor／source／archive SHA 才能固定跨程序身份。Archived SavedRecipeV3 綁定原 SavedRecipeV2 和原 V3／V2 外部錨點；翻頁只透過 `with_page()` 改頁面選擇，不改寫原始來源 reference。公開 Archived SourceV3 open／reopen 會重跑完整 F17 exact scope，從自含 archive 原件建新 Monthly／Index V2 operation，再比對穩定 source content、pin、cutoff、codes 與 ledgers。新 operation 可重發新的 SourceReferenceV3／ArtifactV3，但不得覆蓋 recipe 所保存的 origin anchors。

因此，原 DB／capture、原 HTML／CSV、原 snapshot 目錄或原 ArtifactV3 漂移／移走時，封存 lane 仍可讀回已保存的原始 Monthly／Index 來源；完整 immutable daily market roots 與 trusted acceptance 仍須由 caller 提供。封存不授來源接受或歷史可得性；輸出保持 `current_only`，F17 外層 availability 為 `unknown`，月營收 pin 僅標 `cohort_hour_bound`，historical/formal PIT 均為 false。V1 recipe／reader 不 cast、不降格為 V2。

Root 已確認 Monthly 8、Artifact V4 8、Recipe 5、Source V3 8 個限定測試通過。Source V3 native 雙 PID 以父 PID 55252→新 PID 9188 通過：同一 named job、原 120-phase／270-driver 範圍，terminal 與 handles 關閉後才啟動 fresh process。原 DB、raw、snapshot、ArtifactV3 路徑漂移後，完整 258 股票、雙 ledger、full pin、頁 1、Decimal `22.006875`、origin RecipeV3 與 source identity 均保持；fresh ReferenceV3 重發 SHA 不同，原三個外部錨點不變，14 個封存／V4 pair／daily 檔及原 320 個 F17 assets 不變。這是限定 backend 雙 PID 證據，不代表 UI／Watchlist 收藏、EXE 或整體 Gate 已驗；正式來源接受及歷史 PIT 也不在這項狹窄接線的授權範圍。

後續正式樹已接入正常 Main 的 archived SourceV3 月營收研究頁，並以共用 owner-thread actor 管理來源建立、使用與關閉；Bookmark3／Watchlist3 使用明確 typed 路由，既有 V1／V2 僅沿嚴格 live 路徑。Main 從凍結設定讀取帶外部 SHA 的 binding metadata 以取得 source roots，不讀 mutable pointer；完成 protected-root 與路徑重疊檢查後，才建立互為 sibling 的 `monthly-references.v3`、`raw-archives.v2`、`archive-references.v4` 三個保存目錄。V3 公開 source getters 具名型別為 `query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2`、`result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2`、`request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2`、`page: DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2`、`f17_query: DailyMarketTechnicalOfficialDispositionQueryV1`、`monthly_reference: DailyMarketMonthlyRevenueSourceReferenceV3`、`monthly_cohort_pin: DailyMonthlyRevenueCohortPin`、`artifact_descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4`、`source_pair_identity_sha256: str` 與 `monthly_sqlite_connection_closed: bool`；狀態 literals 為 `source_scope="current_only"`、`availability_status="unknown"`、`monthly_availability_status="cohort_hour_bound"`、`historical_pit_eligible=False`、`formal_pit_eligible=False`。Unverified decoder 輸出不授予來源資格。Bookmark3 固定四個 caller-provided 外部錨點：原月營收 SourceReferenceV3、原 ArtifactV3 descriptor、ArchiveReferenceV2、封存 ArtifactV4 descriptor。

限縮回歸證據：Bookmark3 9 PASS、storage 27 PASS／1 protected-reparse SKIP、Watchlist3 5 PASS；standalone 真 archived UI 流程 1 PASS（44.49 秒），涵蓋完整 258 股票、原 1000 YoY、跨頁保存，並在 DB／raw 漂移及原 snapshot／ArtifactV3 移開後精確重開且 actor 關閉。正常 Main/native/fresh 限定合成流程亦由 Root 記錄通過：父 PID 54640→fresh PID 32420，父／fresh source SHA 分別為 `960e1ea04c719afca56ef4a580d38cf191cc40ea58d9cf4aca2996841b089c7e`／`a126fed641ed15584a48a97de74a107b12445b2e381ca11ee779793c4abfb1f3`，外層收據 `a9fd1398409b0c14f8510c4ed6e7e0ba3f20a3417f24dbc859b8a5c7d2fc063d` 已閉鎖。26 個固定來源在父／fresh bytes、SHA、mtime 相同，原 320 個 F17 assets 不變；Main typed saver 與 Watchlist 實際個股分析按鈕重開後保留頁 1、完整 258 股票、1128、origin Recipe3 與四個外部錨點。父程序關閉後再更正私有 DB／raw、移開原 snapshot 與 `monthly-references.v3`、改壞 mutable series pointer，fresh 仍依固定 binding metadata roots 精確重開；原 phase／driver 期限未改，且自然結束、handles 關閉後才進 fresh phase。此為限定合成與保存／重開證據，不代表正式來源用途接受、完整 Recommendation、歷史／正式 PIT、EXE 或整體 Gate 已驗。mypy 1003 PASS 也不證明 UI 強型別已完整驗證，因既有 `ui_qt.*` 設定 `ignore_errors=True`。

### Increment21：日曆完整批次與exact讀回

Data層的typed JSON transport固定raw bytes／HTTP完整性，application的daily snapshot沿原calendar evidence parser建立兩市場分區與session-date manifest。Capture／manifest／receipt是create-only保存版本；reader要求caller的外部manifest／receipt SHA及兩市場獨立來源用途錨點，重驗raw、schema、partition、日曆與台北批次時間，不能由封套自授接受。改正另存、原版不換latest，pending／failure拒讀；93 inclusive日上限保留，長期組合仍待。

19案與合成父6316→新13156已讀回相同8份保存來源，取消空窗修正後限定2案／mypy1010通過；檔案及新程序證據不證斷電目錄耐久。Increment23已新增明示daily read pin及同一pair reader路由：Registry controller只固定批次目錄、外部雙SHA、由owner提供的獨立typed接受錨點與當下UTC aware cutoff，不從封套重建信任；前後以同一daily reader核對版本，結果保留批次／capture／兩SHA與可用小時。原artifact簽名與候選資格不變。

新backend與原pair／新舊controller、widget及必要UI檢查已各自限定驗證；Main父33268→新17672重用17來源，沒有重產run或calendar。兩次操作的actual cutoff各自保留，其餘版本與診斷一致，來源bytes／完整stat不變。這只有隔離QA的合成接受錨點，正式Main尚未配置真用途接受，daily預設阻擋；不授自動更新、正式publisher或Task。來源／幣別／成本、歷史PIT與完整績效不能由批次小時或完整日期推得。規格見[每日來源契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#日曆完整json批次increment21)，原FAIL與收據見[Increment23 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment23每日日曆版本接原registry診斷)。


## 日期化接線細節

以下保留原始細節段落，改按策略／回測與跨頁研究責任查找。段落中的驗收、版本及限制只適用原記錄所述範圍；目前狀態看本頁 Snapshot 引用及具名 QA。

### 策略、版本與回測結果
W底基礎研究`baldr_w_bottom_basic_v1@1.0.0`已接原StrategyRegistry／正常單股producer與保存出口。`causal_w_bottom`以獨立Decimal Context60逐列確認嚴格三點收盤谷，只保留27列；相鄰雙谷／5列前置跌勢／第一谷5%差／頸線高1%／等待與失效按原計畫§5.3，不使用全段find_peaks／ATR均值／補值。executor深拷貝spec與frame，輸出逐列確認證據及意圖；episode只固定原頸線，不是已成交部位。缺行情清幾何但保留既有意圖的歷史頸線；unavailable含暖機／缺件／重啟，不等於原始缺資料列數。

新`single-backtest-w-bottom-execution.v1`沿原manifest保存同次spec／effective rules、9個source-file hash、日期／狀態／意圖／兩谷與頸線證據、原Broker config、runtime及`prior_rows=0`的測試窗全狀態重設政策；不套布林band／暖機。專用pure reader只核已保存規則、原值／日期與episode交叉一致性，不讀current Registry或重跑訊號。metadata builder另核獨立傳入的identity、params、原capital／所有Broker輸入及requested/actual bounds；metadata存實際窗，原請求窗保留raw_params。缺成本不補0，來源收尾取消不回填完整manifest。原baseline／兩策略v2／布林schema不改，原Broker撮合／金融公式不變，研究資格在service與reconciliation明確拒絕；source hash只識別檔案，不授來源／PIT或績效權威。限定正常Main／fresh已驗，其他模式及Native／EXE仍待。

`baldr_bollinger_basic_v1@1.0.0`以獨立純契約／executor接原StrategyRegistry，固定既有causal BBANDS30/2/SMA分析邊界；決策只以Decimal比較當列／前列原值，不走ScoringEngine、補值或自認成交。正常producer同次有界讀取前180曆日、最多31個prior觀測，fingerprint綁實用完整frame；原service按test_start重設確認並裁切後才撮合／計績效。新`single-backtest-bollinger-execution.v1`沿既有Registry保存spec、effective rules、逐日訊號、input_context、分析runtime版本及十個源碼hash，原baseline v1／兩策略v2不換版。專用pure reader核schema／identity／規則／成本／來源集合／qualification及訊號日期與型別，再交原規則卡與結果出口，不查當前Registry或重跑。指標float仍在分析邊界，來源hash不是權威／PIT證明；缺日曆完整性保持unknown，研究版不能由SOP或直接Registry晉升取得正式資格。本輪只驗正常單股研究，其他模式與完整家族仍各自待。

`StrategyVersionService.create_version`的新建身份採時間前綴加UUID，explicit ID沿既有reader的安全basename限制；同目錄獨立exclusive `.tmp`完整flush/fsync後，Windows rename／其他平台hard-link以create-only發布，目標存在必須失敗。只有本次確實建立的暫存可清理，清理錯誤記錄而不遮蔽原例外或已發布成功。catalog僅接受檔名與payload ID一致的JSON，舊暫存原件不刪；明確`update_version`仍是既有可變聲明，不宣稱不可變版本庫。promotion回填失敗先讀回exact backlink，已回填或未知保留版本；僅確認未引用才補償本次新建。生命週期紀錄失敗不刪已回填JSON，標示`reconciliation_required`並由原掃描列出；狀態寫入也失敗時保留原錯誤與log，不授晉升成功。這不是跨store transaction或自動修復，亦不改原preflight／金融／lifecycle門檻。

`SavedStrategyVersionReader`唯讀消費現有VersionService與ResearchHistoryLookup。清單保存canonical版本聲明及exact來源entry，開啟前後重讀版本，核策略／params、source config、data fingerprint、成交／sizing及已存在backlink；版本號是生命週期標籤，不與原run執行器版號強制相等。新`select_registry_run`只按明示ID建metadata/context選取，原resolve再核完整性／預算；不掃latest或建立來源。SavedRuleCard新增可選預算／取消透傳，舊呼叫契約不變。Qt元件只接回原結果／dialog，generation與合作關閉拒晚到；catalog分頁不改run身份。版本JSON摘要只證本次選取一致，沒有跨程序不可變／來源權威效力；legacy缺執行來源及績效未知仍沿原reader，不用目前設定補章。

Increment59固定來源包為兩個既有策略的v2規則收據加三份raw source datas（兩executor與metadata wrapper）；原四份執行來源及兩technical kernels保留。build metadata以AST讀取spec明示literal來源清單，不執行spec；完整三份才加對應hash，partial／缺檔拒絕，舊spec及僅註解含路徑不冒稱v2。runtime仍對實際原檔取hash，metadata不能替代缺檔或來源權威；固定export與EXE各自正常保存／fresh再比金融內容，沒有修改已固定export來補件。

原analyzer的PF改nullable，附 `closed-pair-net-pnl-ratio.v1`／status；Decimal60內計算及既有analytics輸出分開。`backtest_contracts.profit_factor_projection`讓單股／batch／optimizer／新repository只傳有效有限值；缺版本舊值不升格。原runs schema不遷移，未定義保存NULL、舊比較與promotion摘要PF不可用；歷史七欄不增欄或重算。固定9fa尚未backport，見[PF指南](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#獲利因子的可用性與舊結果)。

原 `PerformanceAnalyzer` 增補逐指標有效性，保持原計算／數值出口；新 `single-backtest-performance.v1` node 由原 `BacktestService` 發行，固定七個保存欄位、單位、實際期間／列數、完成配對與股票身份。十進位值文字指紋使原 float analytics 與 UI 的 Decimal JSON 解碼一致；整 node SHA 綁有效性與期間，原 Registry metadata／Parquet 外部身份仍各自核驗，不把 checksum 當來源授權。原 `ResearchRunService` 只對新宣告另保留實際日期欄並在寫入前核對原表；舊無 node 保存／hash 不變。公開歷史 reader 與被動卡片重驗 node／摘要，顯示原已知值，fallback／零配對／無期間維持 None；不重算或推進 qualification／comparability。操作見[指南](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#新單股保存結果的歷史指標後續開發分支)。

### 價格研究、個股與 Portfolio 跨頁接線

持倉頁的手動帳列表獨立於下方進階證據splitter，直接接四張狀態卡／活躍摘要；原DTO、分帳、刷新與交易服務不改。進階切換主動刷新操作列方向，中等寬度保留直列避免裁字。價格研究增三步引導及名稱，UI parser在格式／重複守衛後把代碼集合排序才呼叫原query；不改catalog／strict source session／核心篩選／收藏契約，舊後端仍拒非canonical順序。個股漲跌沿原價差方向守衛，說明缺件不代表0。

Increment71 的價格頁只在 UI 層清除既有篩選並對同一 exact read session 重查，不改來源、價格事實、query／comparison／bookmark DTO 或 PIT 資格。單檔收藏把比較選取留空，不把不足兩檔的籃子冒充比較。手動交易表單的代碼／名稱互補只讀本機公司名冊，唯一且精確匹配才自動填；不改 Portfolio 交易 writer。未連結保存 result 的手動持倉下鑽傳 `current_stock_research`，一般個股 reader 因而可讀目前行情與技術；已有 validated result 的持倉仍傳原保存 scope。回測頁只調 splitter 與選用查找呈現，原結果 reader／金融資料不重算。

價格選股後續可見性修正只在互動式 `source_read`／`query` 成功且 `_PriceViewState` 核驗後收合條件與詳情，依當次 generation／state 在外層結果捲動區定位結果；失敗、取消、翻頁、原來源返回與收藏還原不觸發定位。來源及結果計數仍可展開，原查詢、strict session、basket、bookmark、Decimal／PIT守衛和儲存契約未改。固定 `ec5c95733608` EXE 尚未含此後續來源修正。

個股研究另有獨立 typed `StockOfficialAttentionDTO`／row 與 `official_attention` 尾端欄位；正常 report service 透過 `OfficialAttentionReportProvider` 讀明選 snapshot。三個 `OFFICIAL_ATTENTION_*` 環境設定只識別固定版本，不是資格接受；錯設定隔離此區塊，當日報告用實際 clock，歷史報告截止該台北日末，不能看到後來保存版本。原價／本益比字串、公開來源、雙 SHA、資料日／可用小時與限制投影至正常個股頁，與 `attention_reasons`、market status 交易限制及 Advice 分離；不新增策略規則。持久化與時間守衛見[資料架構](data_storage_runtime.md)，操作見[指南](../../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#單日官方注意公告後續開發分支)。

一般手動觀察股票的未連結研究，由 Watchlist 僅在無source ID、無result／決策日／snapshot且identity=unknown時明示選擇目前個股研究context；現有report reader讀目前行情，返回按原代號定位。已有來源或身份衝突仍保留保存來源路由；不將讀取失敗改成目前行情，也不授歷史PIT。儲存格式、public reader、金融計算與原收藏版本路徑均沿用，限定驗證見[Increment34 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment34v1一般觀察股票下鑽與回訪)。
