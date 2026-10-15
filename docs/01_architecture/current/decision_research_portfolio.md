# 決策、研究與 Portfolio

本冊涵蓋目前的 Recommendation、回測、研究證據與 Portfolio 責任。產品能力與 Advice 契約以 [Product Roadmap](../../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md) 為準；工程 Gate 及驗收標準以 [6M Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md) 為準；現況只看 [Snapshot](../../00_core/PROJECT_SNAPSHOT.md)。

## 模組責任

| 模組 | 主要責任 |
|---|---|
| `decision_module/` | 策略與評分契約、推薦排序、理由、篩選、Regime、Factor 與純計算核心 |
| `analysis_module/` | 技術指標、型態、訊號及其他分析計算 |
| `backtest_module/` | 策略模擬、台股撮合限制、成本、部位與績效分析 |
| `portfolio_module/` | Portfolio 領域帳務投影；服務組合、研究 read model 與 UI orchestration 位於 `app_module/` |
| `app_module/` | Recommendation、Backtest、Research Run、Evidence、Portfolio、Position Health 等 use case 與 DTO 組合 |
| `financial_module/` | 金額、比例、股數等核心數值單位 |
| `ml_module/` | 受治理的模型研究、校準與 shadow 路徑；不因 package 存在而取得正式推薦權限 |

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

`app_module/backtest_service.py`、`batch_backtest_service.py`、`optimizer_service.py`、`walkforward_service.py` 與推薦組合回放服務組合 `backtest_module/`。服務負責資料讀取、策略執行、結果保存與交接；UI 不自行計算訊號、撮合、權重或績效。

- `next-session-open.v2` 在 T 日收盤形成委託，於下一個有效且可交易 session 開盤撮合；停牌、零量或缺開盤時不回退到收盤價。
- 明確標記的舊同日收盤路徑保留其舊語意；未版本化舊 run 不會被改寫成新契約。
- benchmark、特徵、標準化、篩選、停損停利與交易價格只使用決策當時可取得的資料。
- Walk-forward 的 OOS 交易狀態在測試窗起點重設；訓練窗口可提供 T-1 歷史特徵，不能把訓練期持倉或交易混進 OOS 績效。
- Replay、OOS、forward、paper 與 live 是不同證據層級。歷史回放不能替代真實決策日後的 outcome。

金融核心金額、成本、股數、PnL、權重與風控不得新增裸 `float` 計算；使用 Decimal、整數股數、整數 bp 或分為單位的整數金額。浮點數只在隔離的 analytics／展示邊界使用。

Research Lab 的保存績效由 `StrategyHistoricalPerformanceReadService` 沿Registry exact run讀回，Paper快照由 `StrategyPerformanceReadService` 沿明示strategy／version／account namespace／operation／snapshot／aware cutoff讀回。Paper catalogue只在同一READY route內作query-only有限查詢，最多200候選及截斷提示，候選不自授verified／eligible；選列後仍須公開exact reader核完整來源。帳戶每日operation SHA與ledger operation SHA分開保存，各自按原 `sha256:<hex>` 契約核對，不互相替代。兩張卡分開generation，關閉時合作式取消並等待native worker完成，失效回覆不得套用。

一般單股與批次回測的Registry保存入口先以 `research_run_dated_equity_copy` 保留實際date／日期欄或DatetimeIndex，再交既有writer以index=False保存；原曲線、金額與attrs不改，拒缺日、重複、乱序與模糊日期。舊run缺日不由requested period補造；版本化期間損益、幣別／成本、同股雙策略完整比較仍待，日期保存不授績效資格。

P03正常Main由成對的外部binding path/hash解析固定cohort及既有接受錨點，經decision composition重驗全市場，注入同一reader至preparer/provider；session固定hash-bound pin及natural invocation clock，共用可用時間取較晚者，推薦context保存同pin與實際read outcomes。無配置保留原路由，部分配置／錯版本／任一必要快照失效拒絕，不fallback。合成Main父29512→新PID33656已限定驗證input/context，不代表完整推薦、官方接受或EXE；歷史/select-latest保持原版本路由。

P08 `recommendation_portfolio_period_precision_v2` DTO/codec保存精確Decimal text；原next-session-open.v2 producer現於轉float前直接捕獲實際cash／position value／equity。僅全部來源／訂單／持倉／推薦為同一精確股票時發行captured_unqualified，取消只保留partial實際列，未入迴圈fallback不是觀察；多股／需正規化代碼／三元組不符拒絕。每日realized/unrealized P&L未提供仍為None，不新增算式。新tuple不加入V1 DTO／Registry wire shape；V2 sidecar／exact reader及期間比較仍待。缺currency、來源clock/raw、正式calendar與成本authority不授真來源／績效資格。

Paper外部artifacts root為可選明示設定，缺少或無效只停用Paper查找；版本來源沿用正常Main與Research Lab共同的StrategyVersionService。此consumer不建立帳戶、不寫帳本、不改用latest；單一快照沒有完整期間曲線或底層來源可得性時，績效指標保持None／未合格。正式工作樹限定QA與正常Main／fresh／同版EXE的資格分開，最新證據見[本輪補完QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

## Portfolio、Paper 與持倉研究

手動 Portfolio 既有帳務、使用者聲明持倉、虛擬 execution trace 與 Paper Trade Ledger 是不同來源。它們的 identity、保存位置、寫入者與證據資格不能因共用股票代碼或畫面而合併。

- 手動交易不會由 backtest 或 recommendation 自動匯入；回測 run 不是實際 fill。
- 使用者聲明持倉只形成研究投影，依 cutoff、可得時間、來源品質與 snapshot hash 判讀；缺少 entry lineage 時不能當成實際成交、已實現損益或績效校準。
- Paper trade event 使用明示的 research-only identity；paper snapshot、benchmark、成本與 execution gap 必須可追溯。查詢服務不建 schema、不寫資料、不把 paper 結果轉成正式 Portfolio。
- Paper daily account 的 writer 以策略 id/version、paper account namespace、operation id、execution date、portfolio identity、aware decision／mark cutoff、selected READY route 與 policy 綁定同一 operation；金融量值採固定 Decimal context。ledger 與 state 各有獨立 SQLite transaction；兩庫之間沒有原子提交保證，`PENDING → LEDGER_COMMITTED → FINALIZED` 未到 `FINALIZED` 不可供 availability reader 當完成結果。重試必須核同一 operation identity、payload、marker/hash 與既有 checkpoint；不可跳過 partial finalize、以新 identity 重做同一 operation，或把部分提交投影成可用 Paper snapshot。
- Position Health／Exit 輸出是具來源及資料品質的 read model 或 proposal；不自動交易、平倉或改寫持倉 lifecycle。Saved Health 結果以 immutable result、receipt、baseline 與 source witness 綁定及各自 hashes 發布；writer 在發布並讀回後才簽發 aware UTC `available_at`，相同有效重試沿用原 receipt clock。這個 writer availability 只表示 exact receipt 可讀，不替代 witness 的 source availability 或 PIT 資格。讀取以 exact `receipt_id` 選取，並核 portfolio、snapshot、decision date、完整 position IDs／股票／股數及 aware cutoff；要求 receipt 可得時間不晚於 cutoff、result `observed_at` 不晚於 writer availability，且 result、receipt、baseline、source witness 的 identity／hash／scope 全部相符。缺件、晚到、identity 或 hash 不符一律拒絕；不以 mutable latest 補件。
- Portfolio research scenario 將 account kind、portfolio、snapshot、source hash、request 與 aware cutoff 綁成 exact context。`portfolio-research-scenarios.v3` 是 canonical JSON artifact payload，`portfolio-research-store.v1` 是獨立 SQL store schema，不能混為同一版本；reader 以原 bytes/hash 核版本、canonical encoding 與完整欄位，未知 schema、浮點／非有限金額或含糊 payload 一律拒絕。保存完整 cash、shares、mark、market value 與 NAV；以 Decimal／整數單位維持金額守恆，bp 僅供呈現、不反推金額，正股數即使呈現為 0 bp 仍是持倉。讀取只沿 `PORTFOLIO_RESEARCH` 明示 route，不 fallback 到其他帳戶或市場資料。
- 新增或重播資料以不同 namespace／evidence tier 保存；不得以目前市場資料補回舊保存結果。

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
