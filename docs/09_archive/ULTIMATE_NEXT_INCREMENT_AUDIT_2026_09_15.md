# 終極目標產品完成度與下一增量稽核

> **歷史稽核／派工界線（2026-10-11）：** 本文觀察截止於 2026-09-15；「下一工程增量」、檔案範圍與驗收條件是當時提案，不代表目前狀態、優先序或工作授權。後續判讀請依現行權威文件與具名 QA；本文不授權執行舊列測試、資料操作或排程變更。

稽核日期：2026-09-15
觀察截止：2026-09-15；工程基線 `7e029933` 已提交；A 的補充收尾已於 `841ca16e` 提交。主審已核對 84 UI tests、validator `25/0/4`、全域 mypy 614，並驗收 MainWindow close／跨程序 writer→reader readback。
稽核範圍：目前 `dev` 真實程式、已提交的 QA／SSOT 證據，以及已知但未提交的進行中變更
本輪限制：未執行 Python、Qt、pytest、GUI、正式資料或排程；僅修改本文件與列明的 roadmap SSOT，未修改 Manual、`PROJECT_SNAPSHOT.md`、Increment C QA、程式或其他 dirty；文件同步由本輪 commit 收口。

## 一、結論先行

目前產品已具備一條可檢查的「大盤 → 產業 → 股票 → Advice → decision/outcome → learning」工程骨架，但尚未達到可宣稱的完整投資決策產品。現階段最重要的分界如下：

- 已有工程驗收：唯讀大盤／產業／股票決策工作台、Advice action 與機率來源分離、歷史 bootstrap／forward outcome 的資料契約、每日 shadow learning 的受控調整與 rollback、精確 identity 的 decision→outcome 唯讀旅程，以及 Increment A/B/C 所涵蓋的 continuity 寫入／控制元件。A 的真 MainWindow `app.exec` 自然 exit 0，及 writer PID 32268 → reader PID 12432 的跨程序讀回也已由主審實證。
- Position Health source caller／Portfolio／Workbench read-only projection 的 Increment 1 已由 `5a3ed5db` 完成並驗收；仍是後續工程／治理缺口的是 continuity review loop、正式 decision outcome 對應下一次人工調整，以及不在本增量內的 `user_declared` research layer。跨程序 writer／reader 本身不再列為未驗證缺口。
- 只待自然證據：同一 candidate／dataset／horizon／cost 定義下的自然前瞻成熟樣本、校準效果與長期 regime 穩定性。歷史 replay、fixture、shadow receipt 或 `verified` 字串都不能替代它。
- 外部資料缺口：point-in-time industry membership／代表股、TPEX／OTC 覆蓋、可接受的技術／公司行動／成本來源，以及 Paper health lane 所需的 verified entry lineage。verified fill 是 Paper／正式 health lane 的前置，不是所有持倉研究視圖的前置；使用者聲明資料可另走明確標記的 `user_declared` research-only lane。

因此，Qt／Increment C 後的「Position Health source caller／Workbench state」已由 `5a3ed5db`
完成 bounded read-only acceptance；不應重做既有 UI、Advice DTO、calibration consumer
或 historical replay。下一輪工程優先序為「`user_declared` 持倉研究層」、「PIT 產業資料
acceptance」；自然 evidence 仍列為持續觀察線，不佔用下一個工程增量名額。

## 二、判定方式與證據等級

本稽核把「已提交 QA 證明的工程契約」、主審已驗收且由 `841ca16e` 收尾的實際輸出，以及工作樹中尚未提交的施工分開記錄。未提交程式不升格為已提交 QA；主審指定的 close／cross-process 實際結果則列為「已驗證且已提交」，不再寫成未重跑或尚未驗證。Workbench state 接線仍按目前程式實證判為工程缺口。

四種標籤的意義：

- **已驗收（工程）**：已有可追溯的程式／測試／QA 文件證據，表示契約或 bounded slice 成立；不等於自然投資效果成立。
- **工程缺口**：既有邊界尚未接通、未持久化、未完成 caller，或只有單程序／唯讀證據。
- **只待自然證據**：工程契約與 gate 已備妥，剩餘主要是自然日期、成熟窗口與真實結果累積。
- **外部資料缺口**：需要外部來源、來源治理、PIT publication／license／custody 或真實交易／持倉資料；不能靠內部 fixture 補足。

## 三、六項終極目標核對

| 終極目標 | 目前已可證明的部分 | 主要未完成邊界 | 判定 |
|---|---|---|---|
| 大盤 → 產業 → 股票完整盤勢 | `DecisionDeskService`／`DecisionDeskDashboardComposer` 已組合 market breadth、sector rotation、relative strength／liquidity、watchlist／portfolio alerts；`RecommendationService` 可產生股票 ranking 與 Advice read model。 | Industry strength 仍是 current-research：目前 registry／代表股不是 PIT membership；TPEX／興櫃未納入；缺失／停牌價格仍造成 DEGRADED；歷史 recommendation filter 仍可能回 `industry_membership_pit_unavailable`。 | **已驗收（目前研究視圖）＋外部資料缺口**；尚非「完整盤勢」。 |
| watchlist／holding 的買進、持有、減碼、退出係數 | `AdviceAction`、`PortfolioAdviceDTO` 已有 `ADD_CANDIDATE`／`HOLD`／`REDUCE_CANDIDATE`／`EXIT_CANDIDATE` 等 action；target／current／gap 以整數 bp 表達；ranking、calibrated probability、after-cost probability 與 confidence 分離；watchlist 有 exact `result_id + stock_code` identity 與 append-only／tombstone 契約。 | Advice 仍是唯讀／proposal。`PositionHealthBaselineService` 會在缺 human fields 時固定 `WATCH`（`app_module/position_health_baseline_service.py:59-98`）；既有 Position Health source bundle／evaluator 尚未全面接到 Portfolio／Workbench；repo 沒有 native `user_declared` holding source tier。 | **Advice 工程已驗收＋工程缺口＋外部資料缺口**；不是所有研究功能都必須先有真 fill。 |
| 可驗證的期間上漲機率與校準 | typed calibration projection 有 model／dataset／horizon／sample／cost／source trace gate；raw mapping、錯 scope、只有 ranking 或 declared-but-unpriced after-cost 都 fail closed；independent null baseline 才能產生 after-cost probability。 | 歷史 probability 仍是 research；正式 authority 需要自然 matured sample、同 candidate／同 cost、校準比較與 named review；目前自然 sample 為 0。 | **工程已驗收＋只待自然證據**；source／PIT／cost acceptance 另屬外部資料缺口。 |
| historical bootstrap + natural forward | historical method pack 有 event×horizon manifest、decision／available／as-of／maturity、strategy／universe／benchmark／cost identity；bootstrap 已證明日期／row overlap 與 label-boundary crossing 為 0。正常 prospective capture 可產生 immutable receipt。 | V4.1 formal run 為 221 events、24 outcomes、442 rows，但 mature observations 0、walk-forward folds 0、calibration `not_evaluable`；正常 snapshot 只有 1 eligible／199 degraded，natural sample 0。 | **歷史工程已驗收＋只待自然證據＋外部資料缺口**；bootstrap 不等於 PIT 或 natural forward。 |
| 每日評估、受控調整、rollback | daily learning runner 已有 immutable receipt、candidate／dataset／same-date／cost checks、retain／adopt／rollback 決策、idempotency／recoverability；目前 normal lane 能在缺自然證據時 `retain_current`，不改 current champion。 | 2026-09-14 receipt 為 `natural_evidence_supplied=false`、`natural_matured_sample_count=0`；BankTaiwan 05:50 已知 registration 不等於 first natural execution；正式 source acceptance、named review 與自然結果尚未成立。 | **工程已驗收（shadow／受控）＋只待自然證據＋外部資料缺口**；尚非正式自動調整。 |
| decision → outcome 持續累積 | `decision-outcome-journey.v1` 以 exact event／result／snapshot identity 串 Evidence、Outcome、Journal、Portfolio ledger，禁止 same-stock/date fallback；Increment A 有 append-only／tombstone／idempotency 契約；B 有研究頁 controls 與 watchlist migration evidence；主審已驗收 MainWindow 自然 close，以及 writer／reader 跨程序 readback。 | 官方唯讀 smoke 為 582 evidence events、4 outcomes，5/10/20/60 日皆 `insufficient_future_data`，Journal／Portfolio ledger 為 0，3 筆 legacy trade 未連結；Workbench 目前只把 dashboard rows 填入 status／review／evidence／operating-loop models（`ui_qt/views/workbench_view.py:1686-1700`），尚未全面呈現 continuity state。 | **唯讀旅程、continuity runtime 工程已驗收＋Workbench state／自然 outcome 仍缺**；不宣稱完整持續學習閉環。 |

## 四、關鍵實證摘要

### 1. 大盤、產業與股票鏈已存在，但「完整」被 PIT 與覆蓋率卡住

`industry_strength_service.py` 的現行模型會依 requested date 選取有效資料，使用明確的 `tw-industry-explicit-map.v1`、TAIEX 5／20 benchmark 與 current registry；這證明產業排序不是空殼。但既有 `INDUSTRY_DECISION_JOURNEY_2026_09_14.md` 的 smoke 結果是 32 個產業、5／20 可排名 32、registry 2343、TWSE mapping 1084，TPEX／興櫃排除 1208，PIT eligible 0，current unmapped categories 3，missing／suspended price 11／12，品質為 DEGRADED。

所以目前可交付的是「current-research market context」，不是可供歷史推薦、ML 或正式 effectiveness 使用的完整產業盤勢。代表股也只能解讀為現行 registry 下的研究代表，不能倒推歷史 leader／laggard。

### 2. Advice 的係數與機率來源已分層，並且大多數錯誤路徑會拒絕

`AdviceComposer`、`RecommendationService`、`RecommendationCalibrationConsumer` 與 `DecisionPresentationService` 已形成下列邊界；呈現 DTO 的實際欄位與 bp／日期／lineage 驗證位於 `app_module/decision_presentation.py:267-304`、`:306-399`：

- ranking score／percentile 不會自行冒充勝率。
- calibrated probability 只接受 typed projection 或完整 scoped DTO；缺 model、dataset、horizon、cost、source trace、stock scope 或 status 時回到 unknown／rule-only。
- after-cost probability 只在獨立、明確宣告的 5000 bp null baseline 與可驗證成本條件成立時可用；estimated BankTaiwan cost 仍是 research-only，observed fill／slippage 尚未納入。
- `AdviceAction` 的 action 是政策與風險邊界的建議，不是 broker order，也不是未來獲利保證。

實際 consumer 接線在 `app_module/recommendation_service.py:179-230`；authority 對自然樣本數、日期數、Brier improvement 與 calibration gap 的拒絕條件在 `ml_module/recommendation_calibration_authority.py:577-584`，natural receipt／same-date／same-cost／capture custody 驗證在 `:1033-1135`。這一層屬已驗收的工程 contract。未完成的是用自然 forward outcomes 驗證它是否校準、是否跨 regime 穩定，以及是否足以支持正式 action／allocation。

### 3. 歷史 replay 與 shadow learning 已能安全地「不採用」

`V4_1_HISTORICAL_METHOD_PACK_2026_09_12.md` 證明 historical bootstrap 的 manifest、maturity 與 label boundary contract；`V4_2_PROSPECTIVE_SOURCE_DAILY_LEARNING_2026_09_14.md` 證明正常 lane 可保存 immutable capture、建立 candidate 並在自然 evidence 缺席時 `retain_current`。這是很重要的 fail-closed 能力，但不是自然效果證據。

目前最容易被誤讀的數字是：歷史資料有可訓練 rows、normal snapshot 有候選、runner 有 `completed` receipt。這些只能證明 pipeline 運作；在 natural sample 仍為 0 時，不能提升 calibration、不能升級 formal candidate、不能改 Advice／Portfolio allocation。

### 4. decision/outcome 的 exact join 已建立，但真實成熟資料尚未形成 cohort

`DECISION_OUTCOME_JOURNEY_2026_09_14.md` 與 UI QA 證據已明確禁止以相同股票／日期猜測連結，並將 close-to-close forward observation 與 execution PnL 分開。官方 smoke 中 4 個 outcome 全部尚未成熟，這是資料時間狀態，不是 pipeline 成功或失敗的正面證據。Journal／Portfolio ledger 為 0 也表示目前尚不能由該 smoke 宣稱「已累積真實決策效果」。

本次觀察截止前，主審另驗收三項實際 runtime 證據：`output/qa/qtshut_20260915_r2/controlled_run_20260915_004531_6945aee2` 證明真 MainWindow 的 `app.exec` 自然 exit 0；`output/qa/qtcw_20260915/controlled_run_20260915_004558_87310382` 的 writer PID 32268 與 `output/qa/qtc_r_20260915/controlled_run_20260915_004625_9a05d12f` 的 reader PID 12432 均正常 exit 0，並讀回 `accepted`／`note`／`review`／journal 4 筆。這些證據已由 A 的 `841ca16e` 收尾，不再列為待 commit／待驗證，也不再列為「跨程序尚未驗證」。剩餘工程缺口是 Workbench 未全面接上該 continuity state，而非重做 writer／reader。

### 5. Position Health／holding caller 的實際程式邊界

目前 repo 已有可組合的 V2.5 source／evaluator，但它不是完整的 Portfolio／Workbench caller：

- `PaperPositionIdentityProvider` 的政策明定只從「flat → positive 的 verified filled buy」推導 identity（`app_module/paper_position_identity_provider.py:124-170`）；無法證明的股票會留下 `paper_position_identity_unproven`（`:240-296`），自然 entry identity 的欄位則在 `:613-630` 產生。這是 Paper health／正式 lineage lane 的嚴格邊界，不應套用成所有 holding research 的前置。
- `PositionHealthBaselineService` 從 Paper snapshot 建立 `WATCH`，並填入 `missing_entry_thesis`、`missing_invalidation`、`missing_holding_horizon`、`missing_review_date`（`app_module/position_health_baseline_service.py:59-98`）。`PositionHealthDailyRefreshService` 也明確寫入 `health_transition_not_evaluated`、`health_transition_requires_human_thesis_and_current_condition_source`，並保持 `research_only`／`auto_action_allowed=false`（`app_module/position_health_daily_refresh_service.py:961-1095`）。
- market source producer 已能輸出 hash-bound PIT condition 與 Decimal metrics，但其語義明確是「有 governed entry thesis 前只作 observation」（`app_module/position_health_market_source_producer.py:410-434`）；receipt 也標記 read-only、research-only、無 formal credit／broker execution（`:457-487`）。
- `DailyPositionHealthTransitionEvaluator` 已驗證 lineage、PIT condition、thesis、metrics、calendar，並產生 proposal（`app_module/position_health_transition_evaluator.py:246-365`、`:388-489`、`:509-573`）；`evaluate_baseline_file` 能在明確傳入 source paths 時組 bundle（`:628-821`）。但目前 Portfolio UI 仍直接呼叫 legacy `PortfolioConditionMonitor.evaluate`（`ui_qt/views/portfolio_view.py:2376-2380`），再由 `PortfolioFeedbackService` 顯示 lifecycle feedback（`:2626-2654`），不是上述 daily source-backed transition read model。
- thesis provider 對 human registry 會做 identity／available_at／hash／版本驗證（`app_module/position_health_source_providers.py:285-407`），bundle 以 human-reviewed contract 覆蓋 machine-policy fallback（`:1787-1805`）；writer 也拒絕非 `human_reviewed`（`:1855-1873`）。`PositionThesisContract` 的合法 source type 只有 `human_reviewed`／`machine_policy`（`app_module/position_thesis_contract.py:11-14`、`:58-85`），目前沒有 `user_declared` contract。
- Workbench 目前更新 dashboard 的 status／advice／review／evidence／operating-loop models（`ui_qt/views/workbench_view.py:1686-1700`），但查不到把 continuity state 或 Position Health evaluator receipt 接入同一 presentation state 的 caller。

**使用者聲明的持倉資料可先做什麼。** 目前沒有 native `user_declared` schema；但在下一個明確 source-tier 增量中，可以讓使用者提供股票、數量、成本、日期、備註與 thesis 文字，形成標記為 `source_status=user_declared`、`entry_lineage_status=unproven`、`fill_verification=not_provided`、`research_only=true` 的研究 overlay。它可以支援目前價格／條件／相對於「聲明成本」的資訊性觀察、假設覆盤、`HOLD`／`REDUCE_CANDIDATE`／`EXIT_CANDIDATE` 的 research proposal 與人工 review；所有金額／數量計算須在新 boundary 內使用 Decimal／整數單位。它不能宣稱 verified fill、execution PnL、observed slippage、formal calibration credit 或 promotion，也不能餵入 Paper verified lineage。若日後同一筆資料要進 Paper health lane，仍必須通過 `PaperPositionIdentityProvider` 的 verified lineage；兩條 lane 必須並存而不互相冒充。

## 五、完成 Qt／Increment C 後的觀察線與最多三個下一工程增量

以下三項是可直接執行的工程增量，依「先把既有 source／evaluator 接成可用 read model，再建立不依賴真 fill 的持倉研究層，最後補全 market→industry→stock 的 PIT 邊界」排序。全部沿用既有 authority／identity／read-model，不另建 parallel decision DB；不包含 broker 下單或自動平倉。

### 持續觀察線（不列為下一工程增量）：natural forward authority

這條線已有 runner、authority、candidate、same-date／same-cost 與 rollback code，現在主要等待自然日期與成熟結果；不要把它包裝成下一個開發項。當前 normal lane 仍是 `natural_evidence_supplied=false`、`natural_matured_sample_count=0`、`retain_current`。

觀察驗收條件維持：

1. normal prospective lane 產生 immutable capture；必須是真實 prospective date、官方交易日與實際可取得時間，不得以 fixture、explicit-symbol capture、historical replay 或 synthetic label 充當 natural evidence。
2. candidate、model／dataset、strategy／universe、decision date、horizon、benchmark、cost contract、source hash、corporate-action／technical availability 與 outcome artifact 可逐欄核對；`same_date_same_cost=true`，body／artifact hash 可重算，outcome 以 trading-date maturity 產生。
3. 依現行 promotion policy 觀察至少 20 個 matured samples、20 個 distinct natural decision dates、Brier improvement 至少 50 bp、calibration gap 不超過 1000 bp；未達門檻一律 `retain_current`，不改 active pointer。
4. 若 source contract、candidate identity 或 health 不完整，維持 `rule_only`／previous valid pointer／rollback；BankTaiwan 05:50 registration 與 first execution 分開記錄，legacy 50 bp 不混入正常 lane。

這條線的主要分類是 **只待自然證據**；P0 source／custody、PIT、成本與 named review 未成立的部分仍是 **外部資料／治理缺口**。observed fill／slippage 屬後續 execution realism／formal gate，不是第一批 daily learning 的必備前置。

### 增量 1：Position Health source caller 與 Workbench state projection

**目前狀態（2026-09-15）。** 原列工程缺口已由 `5a3ed5db` 完成：
`PositionHealthTransitionReadService` 將 persisted evaluator receipt 驗證後投影為
Portfolio／Workbench 共用 typed read model；Portfolio／Workbench 真實 caller、exact
Paper identity、future／stale／corrupt／scope fail-closed 與缺 receipt unknown path 已
由 [Position Health Increment 1 QA](../06_qa/POSITION_HEALTH_INCREMENT_1_QA_2026_09_15.md) 驗收。
這只完成 Paper verified health lane 的 read-only presentation，不代表自然 evidence、
formal PIT、broker execution 或 `user_declared` 已完成。

**實作前缺口與檔案（歷史基線）。** source provider、daily refresh、transition evaluator 已存在，但 `ui_qt/views/portfolio_view.py:2376-2380` 仍走 legacy `PortfolioConditionMonitor`，`ui_qt/views/workbench_view.py:1686-1700` 只填 dashboard models；需在既有 `app_module/position_health_daily_refresh_service.py`、`app_module/position_health_source_providers.py`、`app_module/position_health_transition_evaluator.py`、`app_module/decision_presentation.py` 建立一個明確的 source-backed read-model caller，並接到 `ui_qt/views/portfolio_view.py`／`workbench_view.py`。`scripts/run_position_health_transition_daily.py:69-87` 與 `scripts/scheduled/run_scheduled_evidence_pipeline_dry_run.py:661-687` 可作為既有入口，不新增第二套 evaluator。

**驗收條件。**

1. 一次正常 refresh 能沿 `Paper snapshot → position identity → hash-bound condition／Decimal metrics → evaluator → read model` 完成，並保留每筆 position identity、decision／available time、source trace、required fields、quality、reason 與 proposal state。
2. Paper lane 僅接受 `PaperPositionIdentityProvider` 的 `same_snapshot_verified`／`ledger_continuous_no_trade`／`natural_entry_verified`／`carried_verified`；無 lineage 仍輸出 `WATCH`／`degraded`，不能用 stock code 猜測成 verified。
3. Workbench／Portfolio 可讀取同一 receipt／read model，明確呈現 `HOLD`／`REDUCE_CANDIDATE`／`EXIT_CANDIDATE`、人工 review required 與 source status；任何缺 source／future date／identity conflict 都 fail closed，維持 `research_only=true`、`auto_action_allowed=false`、無 broker execution。
4. 完成 service contract tests、scheduled caller tests 與一個非 screenshot 的 read-only smoke；A 已驗收的 close／跨程序 readback 僅作 identity／continuity 依賴，不在本增量重做。

**依賴。** A 的已驗收 identity／readback 介面完成 commit／必要 checks、既有 Paper snapshot／official calendar／condition／metrics source；不要求所有 holding 先有真 fill，只有 Paper health／formal lineage lane 必須遵守 verified policy。

**分類。** **工程已驗收（read-only／research-only）**；後續 continuity review loop 與正式
decision outcome 對應不在本增量內。

### 增量 2：`user_declared` 持倉研究層（與 Paper verified lane 分離）

**明確缺口與檔案。** repo 沒有 native `user_declared` holding schema；`PositionThesisContract` 目前只允許 `human_reviewed`／`machine_policy`（`app_module/position_thesis_contract.py:11-14`、`:58-85`），legacy `app_module/dtos/portfolio_dtos.py:59-79` 只有泛用 `source_type`／float 欄位。新增明確的 `app_module/user_declared_holding_research.py`（或等價 domain module）與 `tests/test_user_declared_holding_research.py`，再由 `app_module/decision_presentation.py`、`app_module/portfolio_condition_monitor.py`／`portfolio_feedback_service.py` 消費其 research read model；不要把它塞進 Paper identity provider 或 human thesis registry。

**驗收條件。**

1. 使用者可輸入 stock code、數量、聲明成本、日期、備註與 thesis 文字；輸出強制帶 `source_status=user_declared`、`entry_lineage_status=unproven`、`fill_verification=not_provided`、獨立 source trace、`research_only=true`。聲明資料不得被命名為 fill、verified、natural entry 或 observed cost。
2. 在 Decimal／整數數量與金額 boundary 內，可先做目前價格／條件、相對「聲明成本」的資訊性 mark-to-cost、假設覆盤、`HOLD`／`REDUCE_CANDIDATE`／`EXIT_CANDIDATE` research proposal 與人工 review；所有 action 顯示為 research-only，不能驅動 order、close、allocation 或 calibration。
3. `user_declared` thesis 文字只作使用者研究上下文；只有日後另經 human-reviewed registry、available_at／hash／position lineage 驗證，才可變成 `PositionThesisContract`。Paper lane 仍由 `PaperPositionIdentityProvider` 嚴格驗證，兩條 lane 的 status／統計／effectiveness cohort 不混算。
4. 缺少現價、condition、thesis 或資料來源時回 `WATCH`／`REVIEW`／unknown，不產生正向確信；receipt 明確帶 `formal_credit=false`、`broker_execution=false`、`auto_action_allowed=false`。

**依賴。** 增量 1 的統一 read model、使用者聲明輸入與修改規則、既有 current market／condition source；不依賴真成交，也不把使用者聲明冒充為 Paper fill。自然 forward 成熟後，才可另行評估此類 proposal 的效果。

**分類。** **工程缺口**；不是自然等待，也不是把真 fill 當所有 holdings research 的前置。

### 增量 3：P0 point-in-time industry membership 與 Recommendation caller acceptance

**明確缺口與檔案。** `app_module/industry_strength_service.py:478-780` 目前明確標示 current-research、`historical_pit_eligible=false` 與 mapping／coverage warnings；`app_module/recommendation_service.py` 的 industry filter 仍需在 PIT source accepted 後消費。以 `app_module/industry_strength_service.py`、`data_module/pit_sector_membership_machine.py`／`formal_pit_sector_publisher.py`、`app_module/recommendation_service.py`、`app_module/decision_desk_service.py` 為主，補對應 `tests/` contract／fixed-date tests；不重做 DecisionDesk presentation。

**驗收條件。**

1. 有版本化 membership／classification source，含 publication／available time、effective interval、source hash、schema／coverage、license／使用權責；每個 decision date 只消費當時可取得的 membership。
2. representative-stock 規則可重算，清楚區分 TWSE、TPEX／OTC、興櫃、純指數／槓桿／反向商品與未映射類別；coverage denominator、missing／suspended price 與 degraded reason 保留。
3. current 與多組 historical fixed-date smoke 能重建 membership／代表股／適用 benchmark；不以 current registry 回填 historical PIT，accepted historical lane 不再直接回 `industry_membership_pit_unavailable`。
4. Recommendation／DecisionDesk read model 帶 scope、PIT eligibility、source hash、data quality；來源未覆蓋時仍明確顯示 gap，不把 TWSE-only current result 顯示成全市場正式結果。

**依賴。** 外部來源 owner、合法使用與 publication timestamp、TPEX／OTC／興櫃資料、公司行動與交易日對齊、資料品質 reviewer；這是 source acceptance 依賴，不是自然 maturity 等待。

**分類。** **外部資料缺口＋工程接線缺口**。

## 六、明確不列入下一增量的事項

- 不重做已驗收的 Advice DTO、typed calibration consumer、after-cost null baseline、historical manifest、daily runner、rollback receipt 或 read-only Journey。
- 不把 `natural_sample_count=0`、`insufficient_future_data`、fixture／screenshot、historical bootstrap 或 `verified` 字串當成自然效果證據。
- 不把 scheduler task `Ready` 當成 first natural execution；registration、正常 receipt、source custody、maturity 必須分開核對。
- 不把 estimated BankTaiwan fee／tax model 當成 observed fill／slippage，也不把 legacy 50 bp lane 混入正常 learning lane。
- A 的真 MainWindow close 與 cross-process writer／reader readback 已有主審實證，並由 `841ca16e` 提交收尾；本輪不重做該線。剩餘的是 Workbench state projection，不是 process close／reader readback 未驗證。
- 不把 Paper verified entry lineage 當成所有 holdings research 的前置；`user_declared` 必須另有明確 status，且不進 Paper／formal effectiveness cohort。
- 正式 Advice／Portfolio allocation、broker order、auto close 與 V4 promotion 仍需另有正式 review、長期 forward／paper／live、P0 source、cost、calibration、downside、regime stability 與 rollback 證據。

## 七、稽核依據

主要依據如下，包含本輪讀取的 repo 文件／目前程式，以及主審提供的 2026-09-15 runtime artifact；沒有重新執行測試或排程：

- `docs/00_core/PROJECT_SNAPSHOT.md`
- `docs/00_core/DEVELOPMENT_ROADMAP.md`
- `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md`
- `docs/00_core/ROADMAP_6M_ENGINEERING.md`
- `docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md`
- `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md`
- `docs/01_architecture/system_architecture.md`、`target_system_architecture.md`
- `docs/06_qa/ULTIMATE_DECISION_WORKBENCH_2026_09_14.md`
- `docs/06_qa/INDUSTRY_DECISION_JOURNEY_2026_09_14.md`
- `docs/06_qa/V4_1_HISTORICAL_METHOD_PACK_2026_09_12.md`
- `docs/06_qa/V4_2_PROSPECTIVE_SOURCE_DAILY_LEARNING_2026_09_14.md`
- `docs/06_qa/DAILY_BANKTAIWAN_OPERATIONAL_2026_09_14.md`、`DAILY_BANKTAIWAN_LEARNING_COST_2026_09_14.md`
- `docs/06_qa/DECISION_OUTCOME_JOURNEY_2026_09_14.md`、`DECISION_OUTCOME_JOURNEY_UI_2026_09_14.md`
- `docs/06_qa/DECISION_CONTINUITY_WRITE_PATH_QA_2026_09_14.md`
- `docs/06_qa/DECISION_CONTINUITY_INCREMENT_B_QA_2026_09_14.md`
- `docs/06_qa/DECISION_CONTINUITY_INCREMENT_C_QA_2026_09_14.md`
- `app_module/industry_strength_service.py`、`decision_desk_service.py`、`decision_desk_dashboard_service.py`
- `app_module/advice_composer.py`、`recommendation_service.py`、`recommendation_calibration_consumer.py`、`decision_presentation.py`
- `app_module/forward_performance_service.py`、`outcome_maturity_service.py`、`daily_recommendation_learning_runner.py`
- `ml_module/recommendation_calibration_authority.py`
- `app_module/decision_outcome_journey.py`、`data_module/watchlist_repository.py`
- `app_module/position_health_baseline_service.py`、`position_health_daily_refresh_service.py`、`position_health_market_source_producer.py`
- `app_module/position_health_source_providers.py`、`position_health_transition_evaluator.py`、`position_thesis_contract.py`
- `app_module/paper_position_identity_provider.py`、`app_module/portfolio_condition_monitor.py`、`app_module/portfolio_feedback_service.py`
- `app_module/dtos/portfolio_dtos.py`、`ui_qt/views/portfolio_view.py`、`ui_qt/views/workbench_view.py`
- 主審驗收 artifact：`output/qa/qtshut_20260915_r2/controlled_run_20260915_004531_6945aee2`、`output/qa/qtcw_20260915/controlled_run_20260915_004558_87310382`、`output/qa/qtc_r_20260915/controlled_run_20260915_004625_9a05d12f`

本輪只修改本 audit 與 `PRODUCT_ROADMAP_POST_REFACTOR.md`、`ROADMAP_6M_ENGINEERING.md`、`DEVELOPMENT_ROADMAP.md`、`VERSION_ROADMAP_V2_1_TO_V4_0.md` 四份 roadmap SSOT；未修改 Manual、`PROJECT_SNAPSHOT.md`、Increment C QA、程式、正式資料、排程或其他 dirty，foreign dirty 保留。
