# 終極決策工作台整合缺口矩陣（2026-09-14）

## 1. 目的與判定

本文件是本輪「市場 → 產業 → 個股 → 觀察清單／持倉 → Advice／Evidence」整合的
requirements-to-code evidence matrix。它把可交付的 V4.1／V4.2 工程工作，與尚未
成立的 V4 formal maturity、後續 V5 全決策體驗及 V6 證據驅動個人化分開管理；不以
UI 已能顯示、fixture、historical replay、shadow receipt 或 scheduler Ready 取代自然
forward evidence、source acceptance、observed fill/cost 或人工 Gate。

本輪結論是：

- **已完成第一個可審查的呈現增量**：`DecisionPresentationDTO` 會把校準機率與
  rank／score 分開，並可帶出 decision date、data-as-of、status、source、model、dataset、
  horizon、sample 與 evidence kind；WorkBench Advice row 可展開唯讀完整依據。
- **已完成安全的 shadow／natural read-only 呈現**：`available` 只表示上游有可用估計，
  不能推出 natural validation；`shadow` 只顯示「研究中／shadow」，不猜測是 prospective。
  Workbench／Research Console 現在透過 typed candidate／active／capture verifier 投影
  natural receipt；未通過 verifier、日期／成本／source identity 不一致或尚待成熟時，仍只
  顯示 pending／blocked／unknown。
- **尚未完成真實端到端驗收**：本輪已補做使用實際 PySide6 view／既有 shadow paths 的
  離屏實際 Qt render，並以 controlled DTO／fixture 保留既有 presentation smoke；這些
  驗證 UI 可讀性與 read-only 邊界，並未證明真實資料已形成每日市場、產業、個股內容鏈，
  也未把既有 Journal／Evidence／Portfolio ledger 的 lane-specific identity 統一成產品
  decision journey，或把 learning adjustment 寫回正式 Recommendation／Portfolio。
- **正式安全邊界維持不變**：UI、scheduler、shadow consumer 都不下 broker order、不
  寫正式 Portfolio／Recommendation、不授予 Formal evidence credit；正式資料仍以唯讀
  或既有受控流程為準。

## 2. 本輪可核對的程式與運行證據

### 2.1 程式接線

| 層次 | 可核對位置 | 本輪能證明的事情 | 不能由此推出的事情 |
|---|---|---|---|
| 主 UI／導覽 | `ui_qt/main.py`、`ui_qt/views/decision_desk_view.py`、`ui_qt/views/workbench_view.py` | Workbench、Daily Decision Desk 與研究／下鑽入口可由同一主程式組裝；Workbench Advice row 有「查看機率依據」唯讀展開操作。 | 已形成一條沒有缺資料的 production end-to-end journey。 |
| 市場／產業／個股 | `app_module/decision_desk_*`、`ui_qt/views/decision_desk_view.py`、`ui_qt/views/stock_research_report_view.py` | 既有 DTO／service 可將市場焦點、產業焦點、個股研究與 quality/warning 送至 UI。 | 每日產業 membership、PIT source 或每檔報告內容都已完整可得。 |
| 觀察清單／持倉 | `ui_qt/views/watchlist_view.py`、`ui_qt/views/portfolio_view.py`、`app_module/watchlist_service.py`、`app_module/portfolio_service.py` | 既有列選取、研究報告與保存結果／持倉摘要的唯讀下鑽存在。 | 選取一次就會產生可追蹤的 decision id，或 outcome 一定會回連到同一 decision。 |
| 既有日誌／證據／帳本 identity | `app_module/journal_service.py`、`app_module/dtos/portfolio_dtos.py`、`app_module/evidence_event_service.py`、`app_module/evidence_event_repository.py`、`data_module/portfolio_ledger_repository.py` | Journal 已有 `journal_id`、`linked_id`、`source_id`、`source_snapshot_hash`；Evidence 已有 `event_id`／`event_hash`、`source_snapshot_id`、`run_id` 與以 `event_id + window_days + return_basis` 對齊的 outcome；Portfolio ledger 已有不可變 `event_id`、`thesis_id`、`source_snapshot_hash`。 | 這些是各 lane 的既有 identity，不是可直接互換的 user decision id；Journal 仍有 delete／overwrite legacy API，不能不加治理就宣稱 append-only decision journal。 |
| 呈現契約 | `app_module/decision_presentation.py` | rank／score、校準機率、成本後機率、資料日期、status、source、model、dataset、樣本／期間與 warnings 可在同一 presentation contract 內保留；短摘要會遮蔽長 hash，詳情保留完整 hash。 | presentation contract 本身就是 authority receipt；它不查 DB、不驗證自然 evidence、不重算 score／probability。 |
| 上游校準 | `app_module/recommendation_calibration_consumer.py`、`app_module/recommendation_service.py` | existing consumer 的 model/dataset/source/calibration projection 可以向 Advice DTO 傳遞。 | `status=available`、source 字串、hash 或宣稱的 evidence kind 已通過 typed natural authority verifier。 |
| 每日 shadow learning | `scripts/scheduled/run_daily_recommendation_learning.py`、`scripts/scheduled/run_daily_recommendation_learning_pipeline.py` | 05:40 forward outcome 後有 05:45 bounded shadow learning、frozen challenger、active monitor／rollback 與 durable receipt。 | learning 已改正式推薦、Portfolio allocation、正式權重或 broker。 |

### 2.2 已保存的運行證據

實機 Task Scheduler 的**唯讀查詢**（由父任務以提升權限執行）觀察到：

- `baldr-forward-outcomes-daily`：TaskPath `\\`、State `Ready`。
- `baldr-recommendation-calibration-learning-daily`：TaskPath `\\`、State `Ready`。
- 最新 shadow receipt：`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\latest_status.json`。
  receipt schema 為 `daily-recommendation-learning-receipt.v1`，`status=completed`、
  `decision=retain_current`、`natural_evidence_supplied=false`、
  `natural_matured_sample_count=0`、`formal_order_allowed=false`、`shadow_only=true`。
- receipt 的 `decision_reason=natural_forward_evidence_receipt_missing`，因此本次學習
  只保留目前 champion／rule path，沒有因 replay 或 shadow prediction 取得自然 evidence
  credit。這是最新 runtime observation，不是 scheduler promotion approval。

## 3. Requirements → current-code evidence → gap → acceptance matrix

| # | 需求／使用者問題 | 目前程式與證據 | 真正缺口 | 下一個可接受增量／驗收條件 |
|---:|---|---|---|---|
| 1 | 一個入口能從今日市場開始，逐步到研究與候選判讀。 | MainWindow 導向 Daily Decision Desk、Workbench、Market Explore、Stock Research；既有 callback 與 drill-down contract 可用。 | 目前是多個 read-only view 的串接；既有 Journal／Evidence／Portfolio ledger 各自有 identity，尚未形成同一條 decision journey 的 read model／review state／next action。 | P0 先以 adapter／read model 重用既有 `JournalService`、`JournalEntryDTO`、Evidence event/outcome 與 Portfolio ledger identity，不新增第二套資料庫；每筆 projection 明示 decision date、user action、source snapshot、status、next review。既有 UI 無法安全寫入時仍 fail-closed。 |
| 2 | 市場 → 產業 → 個股研究要先顯示有內容的每日結論，再顯示技術細節。 | `DecisionDeskSnapshot`、Market Explore、Stock Research Report 與既有 quality／warning DTO 已能承載焦點與下鑽。 | 三個大型空表可能占滿首屏；上方仍可能出現 debug state／`AdviceDashboardDTO` 文字；產業 membership、跨日 PIT、缺價／缺來源時沒有完整內容優先的 fallback。 | P0 先收斂成每日結論卡、候選／持倉卡、再展開 technical detail；空表折疊或合理 empty state；每一張卡有 decision date、data-as-of、source、missing reason。接受條件是缺資料時轉 `RESEARCH`／`NO_NEW_POSITION`，不產生看似完整的候選。 |
| 3 | 觀察清單與持倉要延續同一檔股票的研究、Advice 與 evidence。 | Watchlist／Portfolio 的 selected row 可開同一 `StockResearchReportDialog`；既有 `from_watchlist_analysis`、`from_position`、`from_advice` presentation adapters 可共用欄位。既有 Journal `linked_id`／`source_snapshot_hash`、Evidence `event_id`／`source_snapshot_id`、Portfolio ledger `event_id`／`source_snapshot_hash` 可作候選 join input。 | 現在主要是 read-only snapshot continuity；lane-specific IDs 尚未有受治理的 crosswalk，不能保證隔日仍能回答「當時看了什麼」。 | P0 建立 immutable crosswalk／projection，重用既有 IDs，不新增 decision DB：`stock_code + decision_date + advice/result identity + source snapshot + presentation version` 只作可驗證 view key；舊資料缺 key 時顯示 unknown，不回補猜測。 |
| 4 | Ranking、score、probability、confidence 必須分開。 | `DecisionPresentationService`／`DecisionPresentationDTO` 保留排名分數與百分位；`_probability_text`、`_after_cost_probability_text` 只從明確 bp 機率欄位讀取，不以 rank fallback。 | 上游仍可能把分數、confidence、calibration projection 混在同一 payload；自然驗證 authority 尚未接到 typed consumer projection。 | P0 每種量使用獨立欄位、獨立 label、獨立 source/status；測試必須證明只有 score 時機率為 unknown／unavailable，不能產生百分比。 |
| 5 | 機率、日期、資料狀態、缺漏、樣本、來源要同時可判讀。 | Advice summary 顯示 calibrated／after-cost probability 的 evidence label；`RecommendationLearningEvidenceProjectionService` 將 candidate／active／capture、cost lane、model／dataset、horizon、maturity、receipt hash 與 typed reliability bins 接到 Workbench／Research Console；80% 解讀只從 verifier 通過的 natural comparisons 產生。 | 真實 natural sample 仍可能為 `0`；BankTaiwan 預設 lane 目前是 pending，legacy 50bp 為獨立 lane，且跨 capture／cost／日期／source identity 不一致時 fail closed。 | 持續累積同一 candidate／同一成本／同一決策日的自然成熟證據；每個 probability 維持 `value + raw_status + evidence_kind + model + dataset + source + decision_date + data_as_of + horizon + sample + receipt` 契約。缺欄即 unknown／研究中，短摘要不得放完整 hash。 |
| 6 | 證據不足時要轉研究 fallback，而不是硬湊建議。 | `DecisionDesk` quality／warnings、Advice DTO 的 `RESEARCH`／`AVOID`／`NO_NEW_POSITION` 與 Workbench empty/degraded states 已存在；shadow／calibration 缺件會保留研究狀態。 | fallback 目前主要是狀態與 warning，還沒有「下一個要補什麼資料／要回答哪個研究問題／何時再檢查」的 research packet，也沒有使用者回饋閉環。 | P0 建立 `ResearchFallbackPacket`：missing fields、as-of cutoff、source owner、下一問題、再檢查日期、禁止的 action；接受條件是 insufficient evidence 時只顯示研究／避免新增，不顯示正向機率或權重。 |
| 7 | 成本基準要區分估計、paper、observed fill；不可用裸數字假裝成交成本。 | 臺銀電子下單成本 policy 與 Recommendation／Portfolio backtest consumer 已提供研究用 `estimated_research_only`、policy version、Decimal／整數量與 `broker_fill_not_observed`／`slippage_not_modeled` 警告；本輪可先消費這個估算 read model。 | observed fills、partial fills、實際滑價與 broker 對帳尚未形成正式 evidence；成本後機率不可由 gross score 推導。 | P1 先把臺銀估算以 typed `estimated` 狀態放入 Daily evidence／Advice view；估算可用於研究淨效用，但不能標 paper／live。observed fill、partial-fill 與 broker 驗證獨立列為後續 execution-realism Gate。 |
| 8 | 決策 → 結果 → 學習 → 下一輪推薦調整要可追蹤。 | 現有可觀察 chain 是：使用者查看 Daily Desk → 選市場／產業／個股 → 讀研究報告 → Workbench 只讀呈現；另有 05:40 forward outcome producer → 05:45 learning pipeline → frozen challenger／authority／rollback → consumer → 下一輪 Recommendation／Advice。現在 Workbench／Evidence 已以 read-only projection 消費 candidate／active typed verifier；2026-09-14 durable receipt 仍為 `retain_current`、natural sample `0`，故本次沒有 adjustment。 | UI 尚未把 user decision／override／review 與既有 Journal／Evidence／Ledger IDs 做受治理 crosswalk；真實 natural maturity 與正式 Advice adoption 仍未成立。 | P1 先做既有 identity 的 adapter／idempotent join，不新增 decision DB；每輪回答 decision date、model/dataset、candidate／champion、outcome maturity、receipt hash、decision。既有 policy 內的 shadow 可自動選擇／採用／回退；replay／fixture 不可增加 natural sample，也不可改正式 recommendation。 |
| 9 | 模型可受控調整、比較與 rollback。 | `RecommendationCalibrationConsumer`、shadow active pointer、frozen challenger、monitor／rollback metadata 與 durable receipt 已存在；routine shadow adoption／rollback 由既有每日 policy 自動執行，正式 order flag 固定 false。新增的 read-only projection 只接受既有 candidate／active／capture verifier 通過的 receipt／lineage，並顯示 failure reason、horizon 與 cost scope。 | 超出既有 shadow policy 的正式 promotion package 尚未完整；實機目前沒有可授予 formal credit 的 natural matured sample，且 BankTaiwan／legacy lane 必須維持隔離。 | 持續以 verifier receipt 累積有效 natural evidence；candidate／champion、rollback target、effective window、failure／drift reason 全部可讀。routine shadow 不要求使用者每日批准；正式決策影響範圍另立 reviewer／promotion Gate。無 verifier 時 status 必須 unknown，不能用 source/hash 字串升格。 |
| 10 | 安全與正式邊界要明確：不能從研究畫面下單。 | Workbench／presentation 只讀；shadow learning receipt 為 `shadow_only=true`、`formal_order_allowed=false`；架構權限矩陣禁止 UI／scheduler／ML shadow 直接改正式決策或 broker。 | 需要把既有 Journal／Evidence／Ledger adapter 與 routine shadow learning 的 permission／write target 對帳，而不是新增一個平行 command store；並由 runtime receipt 證明沒有跨到正式 DB。 | P0/P1 所有新 adapter／command 都有 explicit mode、target root、write intent、idempotency、backup／rollback；QA 可重放並確認正式 DB／broker 狀態不變。任何不明 write target 都 fail-closed。 |
| 11 | 每日工作要有可核對的排程、操作與最新 receipt。 | 實機唯讀觀察到 forward outcome 與 calibration learning 任務皆 `Ready`；最新 durable receipt 是 completed／retain_current／natural sample 0。 | `scripts/inspect_scheduled_task_registration.py` 的 expected task 清單與實機 learning task 的一致性、owner／trigger／action／latest receipt 對帳仍需收斂；這不是重新註冊或重啟 scheduler 的授權。 | P1 只做 read-only registration／action／trigger／receipt audit：兩任務各有 task path、state、command hash、last result、latest run path 與 owner；不註冊、不重啟、不改 trigger。 |

## 4. V4.1／V4.2 工程軌與 V4 formal maturity 分流

### V4.1 Engineering：可判讀的 Recommendation／Advice vertical slice

V4.1 工程工作是把既有推薦結果變成可追溯、可降級的呈現與 application contract：

1. 完成 recommendation probability／after-cost probability 的欄位、日期、樣本、模型、
   dataset、source 與 evidence kind 傳遞；排名與機率不互相代換。
2. 完成 content-first Workbench：每日結論、候選／持倉、研究 fallback 先呈現，技術
   lineage 詳情後展開；空表不應占滿首屏。
3. 完成 market／industry／stock → watchlist／portfolio 的 immutable snapshot identity，
   讓同一 decision date 的研究結果可回溯。
4. 先接入臺銀成本 policy 的 `estimated_research_only` typed read model；估計／paper／
   observed 分離，不把估計寫成交易結果。observed fills／broker 對帳另列後續 execution-
   realism Gate，不阻擋本輪 content-first 工程。

V4.1 的 Exit Criteria 是「缺資料時不誤導、每個數字有來源／日期／狀態、可從研究回到
同一份 snapshot」，不是投資有效性或 Formal closeout。

### V4.2 Engineering：自然時間 custody、shadow learning 與 rollback

V4.2 工程工作是把自然 forward capture、成熟 outcome、模型／資料集／receipt lineage、
active monitor 與 rollback 接成可審查的 shadow loop：

1. 05:40 forward outcome 與 05:45 bounded learning 需以 Asia/Taipei 交易日／可得時間
   對齊；週末、缺價、來源品質或公司行動缺口時 fail-closed。
2. 只有 verifier 已核對的 typed authority receipt 才能把 natural evidence 狀態帶入
   consumer；source `available`、hash、`evidence kind` 或自然語言宣稱都不是 authority。
3. frozen challenger、champion／rollback pointer、model／dataset version、candidate／run
   identity 與 latest receipt 必須可讀且可重現；routine shadow adoption／rollback 依既有
   已授權 policy 自動執行，不要求使用者每日按批准。
4. 實機排程為 Ready 只代表 job 可被觸發；仍須由最新 receipt、natural matured sample、
   reviewer 與 promotion policy 判斷是否可繼續 shadow。當前 `natural_matured_sample_count=0`
   且 `retain_current`，沒有 adjustment 或 formal credit。

V4.2 的 Exit Criteria 是「shadow loop 可觀察、可回退、能在 evidence 不足時保留現況」，
不是正式 Recommendation／Portfolio promotion、broker 或 V4.0。

### V4 Formal maturity：獨立的長期 Gate

V4.0 的 maturity 必須由長期 Forward／Paper／Live evidence 支持，並包含正式 source
acceptance、PIT／available-time custody、observed fills／cost、decision journal、具名
review、OOS／forward／regime／downside／calibration 與 rollback 等 Gate。以下不能計入
正式 maturity：historical replay、fixture、controlled DTO screenshot、一次性 dry-run、
shadow prediction、未經 verifier 的 receipt 宣稱、scheduler Ready 或 `available` 狀態。

截至本紀錄，V4 formal 仍是 evidence accumulation／`action_required`：natural matured
sample 為 0，正式 order 為 false，正式 Recommendation／Portfolio 不受本輪 UI 增量改寫。

## 5. V5 全決策體驗（規劃，不宣稱已實作）

V5 是把 V4.1／V4.2 的工程能力與既有真實唯讀資料 journey 收斂為真正的 guided decision
experience。它可以與 V4 formal evidence accumulation **並行**，不以 V4 formal closeout
作為 content-first UX、read-only daily evidence view 或 decision continuity 的前置條件；
formal evidence 只決定 Advice／Guided 的可宣稱範圍：

- 首屏只回答今日市場狀態、每日結論、候選／持倉與資料品質；三個大型空表折疊，debug
  DTO、raw state、完整 hash 收進「機率依據／資料詳情」。
- 以市場 → 產業 → 個股 → 觀察清單／Portfolio → review 的單一路徑呈現內容；每次查看、
  人工接受／拒絕、override、下一次 review 都有 append-only decision journal。
- Advice 同時呈現 Why、Why Not、Risk、evidence tier、機率／排名區分、期限、成本狀態、
  missing／degraded reason 與明確的研究 fallback；證據不足時以研究問題和補件清單收尾。
- T+N outcome 會沿同一 decision／advice／source identity 回饋，讓使用者可以看到研究→
  paper／forward 的落差；既有 daily shadow policy 內的模型候選可自動採用或回退，超出
  shadow 既有正式影響範圍時才另立人工 promotion／review Gate，任何情況都不能直接變成
  下單指令。

V5 不等於自動交易，也不把「體驗完整」當成投資有效性。Content-first 與唯讀旅程可先
交付；若要擴大 Guidance scope 或宣稱投資有效，仍須遵守 V4 formal 的自然時間、source、
cost 與 review evidence Gate。

## 6. V6 證據驅動個人化（規劃，不宣稱已實作）

V6 是個人層級的 evidence-driven personalization，而不是把使用者偏好直接變成黑箱
推薦。最小設計邊界為：

- 保存使用者 profile、risk budget、流動性／產業／持有期間限制與明確版本；不以一句自然
  語言偏好覆寫正式 policy。
- 以 user-level decision／outcome evidence 評估「對誰、在何種 regime／horizon 有效」，
  與 population baseline、Equal Weight、champion／challenger 清楚分開。
- adaptive weighting、personalized candidate ordering、guardrail、drift／fairness／
  exposure review 均需 sample、calibration、rollback、人工批准；不足時回到共用 champion
  或 `RESEARCH`／`NO_NEW_POSITION`。
- 個人化只改可解釋的排序／研究優先序／風險提示，不能保證報酬、不能隱藏 negative
  evidence、不能自動調倉或下單。

V6 的前置條件是 V5 的 decision journal／outcome continuity、足夠自然 evidence、正式
source／cost custody 與可回滾的 model／policy registry；目前僅作產品方向規劃。

## 7. 分階段 acceptance increments

| 優先級 | 增量 | 依賴／外部 Gate | 必須產出的可核對證據 |
|---|---|---|---|
| P0 | Content-first Workbench：每日結論、候選／持倉優先；空表折疊；debug／technical detail 收進詳情。 | 既有 DTO；不新增來源。 | UI smoke、keyboard／accessible label、missing／degraded screenshot、read-only write audit。 |
| P0 | Daily evidence view：在每日結論旁直接回答本日 evidence 是哪一批、目前成熟到哪裡、為何保留／降級／等待，並連到 candidate／champion／rollback receipt。 | 既有 `DecisionDeskSnapshot`、`EvidenceEventRepository`、`EvidenceOutcome`／`ForwardPerformanceService` 與 shadow receipt；不新增 pseudo source。現在 evidence／outcome 多分散在 Research／runtime view，尚未成為內容優先的 daily read model；`natural sample=0`、missing price、pending 與 retain reason 要同屏可判讀。 | 每日 view 可由 decision date 讀回 event／outcome／receipt identity；任何 pending／missing／shadow 都顯示原因與下一步，不把 replay／fixture 當自然成熟，不產生正向 Advice。 |
| P0 | Decision presentation provenance contract：機率／rank／confidence 分離，model／dataset／source／日期／期間／樣本／status 齊備。 | 既有 Advice／Calibration DTO；typed authority 仍可 unknown。 | focused DTO tests、短摘要／完整詳情 snapshot、no-bare-percent regression。 |
| P0 | Research fallback packet：不足證據時提供 missing reason、補件來源、下一研究問題與 revisit date。 | 既有 quality／warning；不引入未驗證資料。 | fallback fixture、空／降級 UI、禁止正向 action／weight 測試。 |
| P0 | Immutable decision snapshot identity：市場／產業／個股／watchlist／portfolio 使用同一 key。 | 既有 snapshot／advice identity；需要明確 repository boundary。 | idempotent readback、舊資料 unknown、跨頁同 hash／同 decision date。 |
| P1 | 既有 Journal／Evidence／Portfolio ledger identity adapter 與 T+N outcome join。 | 既有 `JournalService`、Evidence event/outcome、Portfolio ledger；具名 owner、append-only 治理與自然時間。 | decision／outcome crosswalk、可重跑 receipt、review／override history、無正式交易寫入；不新增平行 decision DB。 |
| P1 | 臺銀估算成本 read model。 | 既有台灣銀行成本 policy、Decimal／整數契約；observed fill／partial fill 另作後續 Gate。 | `estimated_research_only`、cost version、fill source／未觀測警告；估算淨效用可研究，但不標 paper／live。 |
| P0/P1 | Typed natural authority projection、champion／challenger／rollback package。 | `RecommendationLearningEvidenceProjectionService`、`ResearchConsoleView` 與 Workbench 已以 read-only 方式消費 candidate／active／capture typed verifier；routine shadow adoption／rollback 仍依既有 policy 自動執行，正式影響另需具名 reviewer／promotion decision。 | 真實 natural matured sample、effective window 與正式 promotion package 仍未完整；BankTaiwan／legacy cost lane、candidate／active identity 不可混合，無 verifier 仍 unknown。 |
| P1 | Read-only scheduler/action/receipt audit。 | 實機 Task Scheduler 讀取權限、owner／trigger／command hash；不註冊、不重啟。 | task path/state/action/last result、latest receipt、natural sample、decision reason 對帳。 |
| P2 | V5 guided decision experience。 | P0/P1 的 content／identity／evidence view 可用；不必等待 V4 formal closeout；Guided scope 仍受當前 evidence 限制。 | 使用者路徑、每一步 source／status、why-not、research fallback、review／rollback evidence。 |
| P2 | V6 user-level personalization。 | V5、長期 user-level outcome、guardrail／privacy／review policy。 | baseline 對照、sample／calibration、個人化 rollback、不得自動交易的安全驗收。 |

外部資料 Gate 必須逐項具名：PIT 產業成分與有效期間、官方／授權 source、available-at
與 publication time、缺漏／停牌／公司行動 policy、真實 forward time、source／model／
dataset owner、reviewer、promotion／rollback decision。臺銀估算成本可以先供研究淨效用；
observed fills／broker 對帳是後續 execution-realism／formal Gate，不是本輪 content-first
UX 的前置。尚未取得時
只保留 `research_candidate`／`shadow`／`unknown`，不得建立 pseudo source、不得把新資料
直接塞入 scoring、不得把 historical／fixture 轉成 formal。

## 8. UX 後續觀察（本輪不無限擴張）

本輪的 controlled DTO／fixture screenshot 只驗證機率來源摘要與詳情可讀；另有使用實際
read-only learning paths 的離屏 Qt render，驗證 lane／freshness／pending／blocked 文案與
安全邊界。兩者都刻意沒有把三個大型空表、Workbench 上方 debug state／`AdviceDashboardDTO`
文字、英文 `Action` 等既有工程語彙一次全部改完。這些是下一個 content-first product
increment：先確保有內容的每日結論與候選／持倉，再將空表折疊、空態合理化、技術資訊收進
詳情、中文化使用者操作。這些 follow-up 不能倒推本輪已完成真實市場→產業→個股端到端驗收。

## 9. 本輪驗證記錄

- `tests/test_decision_presentation.py`：14 passed。
- `tests/test_decision_presentation.py tests/test_ui_qt_workbench_view.py tests/test_ui_qt_portfolio_view.py`：69 passed，1 warning（pytest cache 權限警告）。
- 先前基線的強制 UI suite `tests/test_ui_qt_update_view_workbench.py`：81 passed，1 warning；
  本次依根 AGENTS 重跑時 `portfolio_store` import 已恢復，但因共享工作區其他線尚未提供
  `app_module.journal_service` 而在 collection 階段 blocked。
- 先前基線的 `scripts/qa_validate_update_tab.py`：25 pass、0 fail、4 skip；本次重跑同樣在
  import 階段因 `app_module.journal_service` 缺檔 blocked，未把失敗改標為通過；先前 report
  位於 `output/qa/update_tab/VALIDATION_REPORT.md`。最後一次 MainWindow offscreen rerun 也
  因同一缺檔 blocked，舊 summary 只保留最後一次成功 artifact。
- Learning evidence／Workbench focused suites：`72 passed, 1 warning`；完整 case map、
  實際資料 lane readback 與 failure-mode coverage 見
  `docs/06_qa/LEARNING_EVIDENCE_WORKBENCH_2026_09_14.md`。
- changed Python files `py_compile`：passed。
- focused mypy（`decision_presentation.py`、`workbench_view.py`，skip imports）：passed。
- 全域指定 mypy（本次依根 AGENTS 重跑，指令為
  `\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`）：
  `Success: no issues found in 611 source files`；臺銀成本子任務已另外完成其 public API／
  consumer 的型別修正，本輪只消費其已提交的 research estimate，不修改成本核心。
- 已產生並目視檢查的 local render：
  - 離屏實際 Qt learning projection（實際 read-only BankTaiwan／legacy paths；不是 native desktop mouse／screenreader）：
    `C:\Users\archi\.codex\visualizations\2026\09\15\01a0a278-54ae-72b3-bae7-ada2025777cb\learning_projection_qt_20260914\manifest.json`
  - MainWindow offscreen keyboard／geometry smoke：
    `C:\Users\archi\.codex\visualizations\2026\09\15\01a0a278-54ae-72b3-bae7-ada2025777cb\mainwindow_smoke_20260914\summary.json`
  - 舊有 controlled DTO／fixture render：
    - `output/qa/ultimate_workbench/decision_workbench_advice_detail_20260914.png`
    - `output/qa/ultimate_workbench/decision_workbench_lineage_panel_20260914.png`

本文件若與運行狀態衝突，以 `docs/00_core/PROJECT_SNAPSHOT.md` 的最新 durable receipt、
正式 QA artifact 與本次具時間／hash 的 read-only observation 為準；本文件不授權資料寫入、
scheduler 變更、promotion 或 broker action。
