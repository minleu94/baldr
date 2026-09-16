# V6 個人化 Contract / Engineering Plan（2026-09-15）

## 0. 文件定位與本輪邊界

本文件是 V6 evidence-driven personalization 的 code-backed design／acceptance plan，不是 V6 功能完成報告，也不是自然效果宣稱。它以 2026-09-15 的現有程式與 QA 文件為基準，目的在於先把 identity、PIT、outcome、baseline／challenger、統計 denominators、daily loop、rollback 與可驗收 runner 定義清楚。

本輪只新增本文件，沒有修改既有程式、資料、Manual、SSOT、Roadmap、Git index 或 scheduler，也沒有執行大型 backtest、full pytest、Qt 或排程。既有 working tree 的其他未提交變更均不屬於本計畫。

本文件遵守以下邊界：

- V6 仍是產品方向與 engineering contract；在真實 user decision／mature natural outcome 不足前，不宣稱個人化改善、報酬保證、隱藏缺口已補齊，亦不允許 auto rebalance、broker order 或正式 advice authority 改變。
- L（PIT official taxonomy/source chain）與 K（cross-page continuity integration）是獨立 follow-up dependency；本計畫可以先做 contract、offline evaluation、shadow receipt 與 guardrails，不把 L/K 尚未完成誤報成 V6 已完成。
- 不另造 parallel recommendation、portfolio、paper、user-decision ledger；先重用既有 Recommendation result／projection、EvidenceEvent／EvidenceOutcome、DecisionContinuity／Journal、User-declared research lane 與 Paper research ledger 的 identity，再建立 read-side join/projection。
- 策略、回測、推薦、資金、風控與績效核心欄位以整數 bp、股數、分鐘或 Decimal 表示；任何 sklearn／統計套件的 float 僅能被隔離在既有 analytics boundary，contract 與 receipt 不保存裸 float。
+ 所有 prediction、feature、label、cost、action 與 baseline 都做 look-ahead audit；決策日必須使用 timezone-aware `available_at <= decision_at` 且 `captured_at <= decision_at` 的資料，`available_date`／`decision_date` 只作 trading-day grouping；label 只能在 `label_available_date` 後進入成熟 evaluation。

## 1. 結論摘要

現有系統已具備 population calibration 的大部分骨架：recommendation evidence dataset、PIT label cutoff、purged walk-forward／OOF calibration、candidate／manifest／artifact hash、probability transform、active/champion consumer、natural-forward capture、maturity 與 fail-closed promotion/rollback。現有 DTO 也已將 ranking score 與 calibrated probability 分開。

V6 的真正缺口不是再寫一個 learner，而是把以下五類資料以同一個可驗證的 user scope contract 串起來：

1. 明確且不可猜測的 `personalization_scope_id`（不能把 portfolio、`profile_id`、holding_id 或 `source_id` 自動當成 user）。
2. exact recommendation candidate identity（`result_id + stock_code`）、prediction receipt／model lineage 與 feature/PIT source binding。
3. user action 的 append-only revision（accepted、skipped、watch、held、buy、sell、review、not_recorded），且 `not_recorded` 不等於 skipped。
4. exact natural／paper／declared／replay outcome identity、maturity 與 availability；缺結果不能被編成 0 return。
5. 同一批 row、同一 label/horizon/cost/universe/policy 的 population baseline 與固定 personal challenger，並分開 calibration、action utility、risk 與 uncertainty。

第一個可實作 slice 應是「既有資料的 typed recorder + read-only assembler + fixed shrinkage evaluator + deterministic inspection runner + negative tests」。它不重寫 `RecommendationCalibrationTrainingService`，不把 personal candidate 寫進現有 global active pointer，也不讓任何個人化結果進入正式下單。

## 2. 現況 code audit

### 2.1 Prediction、dataset、training 與 inference

| 現有路徑 | 已可重用的 contract／證據 | 實際缺口 | V6 phase |
|---|---|---|---|
| `app_module/recommendation_calibration.py:187,214,391,1166` 的 `RecommendationCalibrationDataset`、builder、config、evaluation | 已有 recommendation event/outcome 的固定 universe、決策日前 cutoff、missing／duplicate／not-ready exclusion、purged split、raw／calibrated／baseline comparison、dataset manifest；這是目前最接近「RecommendationDataset」的正式類別 | 沒有 user scope、action revision、accepted/skipped/held/sell semantics；dataset manifest 尚未單獨封裝「user evidence join + natural row IDs + source contract」 | **已有 population design；V6 需增加 join contract，不另造母體 learner** |
| `ml_module/recommendation_calibration_training.py:161,660,825` 的 `RecommendationCalibrationSample`、`RecommendationCalibrationTrainingResult`、`RecommendationCalibrationTrainingService` | 已有 `decision_date`、`feature_as_of_date`、`feature_available_date`、`label_end_date`、`label_available_date`、forward return、after-cost label、Decimal cost、固定 cost scenario、purged walk-forward、OOF calibration、untouched evaluation fold、artifact/manifest hash | sample 是 recommendation-level，不是 user-decision-level；只有 strategy/profile／source quality 等既有 lineage，沒有明確 `personalization_scope_id`、action revision、user outcome state | **重用 sample／trainer；先加 personal adapter/evaluator，不改 learner** |
| `ml_module/recommendation_calibration_learning_runner.py:72,109` 的 `DailyRecommendationLearningRunner` | 已有 output root 隔離、training cutoff、`label_available_date <= training_as_of`、candidate package、lineage、authority receipt、`formal_order_allowed=false`、shadow-only、retry／rollback | merged dataset hash 與 user action／personal evidence manifest 尚未形成同一個 immutable closure；既有 runner 仍是全體 recommendation calibration，不是 scope-specific personal evaluation | **重用 operational receipt 形狀；V6 先另出 scope evaluation receipt，不擴大 scheduler** |
| `app_module/recommendation_calibration_consumer.py:63,484,522,701,968`、`app_module/recommendation_service.py:413`、`app_module/advice_dtos.py:106` 附近 | `RecommendationCalibrationProjection` 已保存 ranking、calibrated／after-cost probability、model/dataset/cost identity、`source_trace`、`training_provenance`、`inference_provenance`、compatibility、projection hash；Advice DTO 已保留 projection provenance；RecommendationService 已寫入 immutable projection receipt | recommendation selection 仍先以 rule top-N，model probability 是 projection，不可把 ranking 當 probability；current builder 對 user scope/action 沒有輸入；來源 identity 需由 receipt 精確 join，不能靠 UI 畫面或目前資料重算 | **直接重用；V6 projection 只加 scope join/status，不改 ranking authority** |
| `app_module/recommendation_repository.py` | 保存 `result_id`、JSON result 與 metadata，可用 exact result 讀回 candidate／advice | constructor 會建立目錄／SQLite schema，且 legacy repository 有 delete；V6 read-side 必須使用 read-only adapter/connection，不在 projection 中觸發 write 或 delete | **建立 read-only adapter；不把 repository 變成第二份 user ledger** |

補充判定：在 scoped code 中未找到名為 `RecommendationDataset` 的正式類別；本計畫明確把 `RecommendationCalibrationDataset` 定位為 population dataset，把 `RecommendationCalibrationSample` 定位為 learner sample，避免重新命名造成錯誤完成感。

### 2.2 Evidence、maturity、natural forward 與 authority

| 現有路徑 | 已可重用 | 實際缺口／限制 |
|---|---|---|
| `app_module/evidence_event_dtos.py:84` 的 `EvidenceEvent` | 已有 `event_id`／`event_hash`、symbol、decision/event/as-of/available dates、source snapshot、run/profile、score、cost model、benchmark、quality、metadata | 沒有 user scope；`source_id` 可能是 provider/strategy/source identity，禁止當作 user identity；user action 不應塞成模糊 metadata 後再推斷 |
| `app_module/evidence_event_dtos.py:129` 的 `EvidenceOutcome` | 已有 `(event_id, window_days, return_basis)` 語意、forward/benchmark/industry return bp、MAE/MFE、tradable/limit/suspended、liquidity cost、status、`data_as_of_date` | base enum 只有 `ready/pending/missing_price/insufficient_future_data`；V6 projection 需把 invalid／matured-but-missing／not-applicable 明確正規化，不能把不完整 outcome 當 negative model evidence |
| `app_module/evidence_event_repository.py:27,84,193,246` 與 `app_module/evidence_event_service.py:144,163` | append/upsert 與 exact event/outcome identity、lineage、review proposal 已存在；可作為 natural outcome source | repository outcome upsert 是 evidence source，不是 user-specific action store；V6 要以 exact event/outcome key join，不能按 symbol/date 近似配對 |
| `app_module/outcome_maturity_service.py:15` | 用 official trading dates 計算 expected trading date、`ready/pending/waiting_for_calendar`、remaining days | 需在 V6 receipt 中保存 calendar identity/version 與 evaluation `as_of`；calendar 尚未證實時應是 waiting/blocked，不是 mature |
| `ml_module/recommendation_calibration_evidence.py:52,79,313,595,963,1316` | prediction capture 已綁 candidate freeze、manifest/artifact/dataset/feature/label/cost/policy hash、source contract；NaturalForwardEvidenceBuilder 只在自然成熟後重算 same sample/same cost metrics | capture row 尚未帶 user scope/action；現有 natural builder 是 global challenger/champion lane；不能直接用它的 sample count 代表某個 user 的成熟 evidence |
| `ml_module/recommendation_calibration_authority.py:56,452,466,577` | `RecommendationPromotionPolicy` 已有 natural matured sample/date gates、Brier improvement、calibration gap、cost/lineage verification、pointer receipt、adopt/retain/rollback；任何 decision receipt 都是 `formal_order_allowed=false` | 現有 authority 控制 global calibration candidate，不自動授予 per-user authority；V6 第一 slice 應產生 scope-specific shadow decision，後續若要接 authority 必須有明確 scoped pointer/schema，不可把 user candidate 混進 global pointer |
| `ml_module/calibration_monitor.py:1`、`ml_module/ooc_cross_fitted_calibration.py:264` | 已有 matured-only monitor、integer-bp Brier、ECE、sample count；OOC helper 用 integer bp 計算校準指標 | reliability interval、uncertainty、personal cohort denominators 尚未形成一份 V6 receipt；應重用 metric convention，不再寫一套裸 float 指標 |

### 2.3 Decision continuity、Journal、user-declared 與 Paper

| 現有路徑 | 已可重用 | V6 必須保留的邊界 |
|---|---|---|
| `app_module/dtos/decision_continuity_dtos.py:94-234` 的 `DecisionIdentity`／`DecisionContinuityRevision` | exact candidate key 是 `(result_id, stock_code)`；snapshot id/hash、decision date 獨立保存；revision、payload、tombstone、revision_of 可保存 append-only history | 不得 fallback 到 `source_id`、`profile_id`、portfolio 或 holding_id；缺 result identity 必須 unknown/conflict/fail-closed，不得猜候選人 |
| `app_module/decision_continuity_controller.py:95,128,144,276,353` | exact identity readback、CAS/request id idempotency、conflict/read error fail-closed、accepted/skipped/review 等 action 已有 controller | controller 現在沒有 typed `personalization_scope_id`／decision kind／prediction receipt 的 payload API；第一 slice 只做向後相容的 typed payload extension，仍由既有 controller/Journal 寫入，不新增 ledger |
| `app_module/journal_service.py:25,138,141,203,334` | `record_decision_action`／`record_research_action` 及 `list_decision_revisions`、append-only journal store 可作 user action source | action payload 目前以 continuity identity 為主；需加明確 optional personalization envelope，並保留 request id／revision chain；任意 note 或 tag 不足以作統計 identity |
| `app_module/user_declared_holding_research.py:476,1339,1396,1476,1613,1946` | user-declared holding 有 immutable holding/revision、PIT custody、Decimal mark、research-only、`calibration_status=excluded_user_declared`、`effectiveness_cohort=excluded_user_declared` | `holding_id` 不得變成 recommendation decision id；沒有 exact `result_id + stock_code` 時只能當 held/position context，不能當 prediction label、calibration credit 或 effectiveness evidence |
| `app_module/paper_trade_ledger.py:34,207,220`、`data_module/paper_daily_execution_producer.py:118,178` | Paper fill 有 exact fill/order/source_event identity、Decimal fill/cost、research-only、broker/auto-rebalance false；producer 以 frozen recommendation `result_id`／`source_result_id` 驗證 source chain | Paper 是 research execution tier，不是 natural user decision；`PaperTradeFill.source_event_id` 不得直接當 user action id；要經 `source_result_id`、candidate/symbol 與 scope join 才能成為 paper outcome row，且仍與 natural outcome 分 cohort |

## 3. V6 `personalization-decision-evidence.v1` contract

這個名稱先代表 logical contract／read-side projection，不代表現在要建立新的資料表或 JSONL ledger。它將既有來源投影成一個可驗證的 immutable view；寫入 user action 時只透過既有 DecisionContinuity／Journal revision，prediction 仍來自既有 recommendation／calibration receipt，outcome 仍來自 EvidenceEvent/EvidenceOutcome 或 Paper read adapter。

### 3.1 Identity envelope

| 欄位 | 必填規則 | 語意與禁止事項 |
|---|---|---|
| `schema_version` | 固定 `personalization-decision-evidence.v1` | schema version 必須進 receipt hash；不可無版本解析 |
| `personalization_scope_id` | 非空、穩定、明確提供 | V6 的 user scope。可以是 opaque user id 或明確宣告的 profile scope；不可由 portfolio、holding、source、strategy 自動推導。scope 不存在時 row 只能 population-only，不能稱 personal |
| `scope_type` | `user`、`profile` 或明確 future enum | `profile_id` 只有在上游明確宣告它就是 scope 時才能使用；既有 recommendation profile 不自動等於 user |
| `result_id` | 必須是既有 persisted Recommendation result identity | 與 `stock_code` 組成 exact candidate identity；空值、模糊 source id、目前畫面 index 均 fail closed |
| `stock_code` | 非空 canonical code | 不以股票名稱、顯示列號或 Paper fill id 代替 |
| `decision_date` | ISO trading date，且與 recommendation／event identity 一致 | 不可以 action timestamp 的日期覆寫決策日 |
| `decision_revision_id` | 若有 action，必須對應既有 Journal/Continuity revision | 同一 candidate 可有多個合法歷史 revision；同一 revision id 的不同內容是 conflict，不可覆寫 |
| `continuity_event_id`／`request_id` | 若由 user action 產生則保存 | 支援 idempotent retry 與 append-only audit；不可只用 wall-clock 近似去重 |
| `decision_kind` | `recommendation_observation`、`buy`、`hold`、`sell`、`watch`、`review` 等固定 enum | buy／sell 不能共用同一 label contract；held 是 action state，不是成功 outcome |

最低可計算 identity 是 `(personalization_scope_id, result_id, stock_code, decision_revision_id)`；prediction／outcome 則各自有下列 exact key，不能以 symbol/date fuzzy join。

### 3.2 Prediction、PIT 與 model/data lineage

PIT 的 canonical ordering 是 timezone-aware decision_at、available_at、captured_at；全部正規化 UTC。decision_date／available_date 只作 trading-day grouping。除了 date-level 條件外，必須驗證 available_at <= decision_at 且 captured_at <= decision_at；同日但 decision 後才到的資料一律不可用。legacy 僅有 date 的 row 標示 temporal_precision_unproven，不進 personal readiness。

每筆 prediction 必須保存：

- `prediction_id`、`recommendation_event_id` 或既有 `capture_row_id`、`projection_receipt_hash`。
- `selection_authority`、`ranking_score_bp`、`ranking_percentile_bp`、`ranking_method` 與 `ranking_kind`；這些欄位永遠與 `probability_bp` 分開。
- `population_probability_bp`、`raw_probability_bp`、`calibrated_probability_bp`、`after_cost_probability_bp`，每一個欄位有 status；缺值是 unavailable，不是 0。
- `candidate_id`／`model_id`、candidate freeze／manifest／artifact hash、`dataset_id`／`dataset_hash`、feature registry/schema hash、probability transform／baseline id/hash、training provenance、inference provenance、projection hash。
- `source_snapshot_id`／`source_snapshot_hash`、raw snapshot/row hash、feature transform contract、`feature_as_of_date`、`feature_available_date`、timezone-aware `decision_at`、`available_at`、`captured_at`。date 欄位只作 trading-day grouping；canonical validation 是 `feature_as_of_date < decision_date`、`available_at <= decision_at`、`captured_at <= decision_at`。
- `label_contract_id`／`label_registry_hash`、`horizon_days`、`window_type`、`return_basis`、benchmark/industry id。
- `cost_scenario_id`／version/hash、cost basis、policy estimate date、fixed/estimated/research-only role。fixed cost 與 estimated liquidity 不得在同一 label 中無標籤混用。
- `source_contract_binding`、code/contract version、capture origin、recorded_at。

`result_id + stock_code` 只連到既有 candidate identity；`prediction_id`／projection receipt 才是某一次 delivered prediction 的 identity。若 RecommendationService 尚未產生可驗證 projection receipt，V6 assembler 回傳 `prediction_unavailable`，不以 DTO 畫面重新計算。

### 3.3 User action envelope

個人 scope 必須在 delivered prediction 產生時已存在，而不是等 user action 才補。第一片重用既有持久化 envelope：batch 寫入 RecommendationResultDTO.run_context["personalization_scope"] 與 inference projection receipt 的 selection_contract["personalization_scope"]；per-candidate 由 RecommendationDTO.calibration_provenance["personalization_scope"] 連回同一 envelope/hash。source_contract_binding 仍只表示資料來源；未明確提供 scope 時標示 scope_status=unbound，後續 action 不得事後回填成當時的 personal prediction。

action 必須保存：

- `action`：`accepted`、`skipped`、`watch`、`held`、`buy`、`sell`、`review_scheduled`、`note`、`not_recorded` 等固定 enum。
- `action_state`：`recorded`、`not_recorded`、`superseded`、`voided`、`conflict`；未點擊／未觀察不可推成 skipped。
- `action_at`／`recorded_at`：含 timezone 的 timestamp；`decision_date` 仍是 recommendation decision date。
- `action_source`、`actor`、`decision_revision_id`、`continuity_event_id`、`request_id`、`revision_of`、`note`／structured payload。
- `user_intent` 與 `execution_state` 分開。accepted 只代表研究意向；不代表 broker fill。buy/hold/sell 若沒有 Paper 或 broker 來源，不得稱 executed。

第一個 writer API 應是 `PersonalizationDecisionRecorder` 的薄 facade：驗證 scope + exact `DecisionIdentity` 後，委派 `DecisionContinuityController`／`JournalService.record_research_action`，把 typed personalization envelope 放進既有 revision `payload`。它不能直接另寫 `personalization.jsonl`、SQLite table 或第二套 CAS。

### 3.4 Maturity、outcome 與 source tier

每筆 outcome 保存：

- `outcome_id`、`event_id`、`window_days`、`window_type`、`return_basis`、`expected_maturity_date`、`trading_calendar_id/version`。
- `outcome_status`：`pending_maturity`、`ready`、`matured_missing`、`invalid`、`not_applicable`；可與既有 `pending`、`missing_price`、`insufficient_future_data` 做明確 normalization。
- `label_available_date`、`data_as_of_date`、`calculated_at`、price dates、forward/benchmark/industry return bp、MAE/MFE、tradable/limit/suspended、liquidity cost bp。
- `outcome_tier` 必須是 `natural_forward`、`paper_research`、`user_declared_context`、`historical_replay` 或 `synthetic_fixture` 之一；不同 tier 不可合併成同一個 natural denominator。
- after-cost utility 使用 Decimal／bp，並保存 cost scenario identity；estimated research cost 只能標示 research/diagnostic，不可冒充 observed execution。
- `outcome_state`：`no_result`、`missing`、`deleted_tombstoned`、`edited_superseded`、`duplicate_exact`、`duplicate_conflict`；no result 是 status，不是 return 0。

`OutcomeMaturityService.evaluate` 是 maturity source；只有 official trading dates 已知、expected date `<= evaluated_as_of` 且 EvidenceOutcome ready，才進 ready denominator。matured-but-missing 轉成 data gap；不得當成 model negative。user-declared mark 只作 context，除非另有 exact recommendation event/outcome identity，否則 `excluded_user_declared`。

### 3.5 Revision、dedupe 與 audit

contract 每筆 projection 都需保存 `record_id`、`revision_id`、`revision_of`、`record_hash`、`previous_record_hash`、`status`、`invalidated_reason`、`created_at`、`writer`、`idempotency_key`。

- 同一 `idempotency_key` 且 canonical payload 完全相同：回傳原 revision，不新增第二筆。
- 同一 idempotency/request id 但 payload 不同：`conflict`，拒絕寫入或進 quarantine；不得取最後一筆覆蓋第一筆。
- 同一 exact prediction/outcome key 的完全相同 evidence：計數一次，保存 duplicate diagnostic。
- user action 的 accepted → skipped、watch → buy、buy → sell 可是新的 append-only revision；不是原 row update。舊 revision 保留在 audit，current projection 只按明確 revision chain 決定。
- delete/edit 只產生 tombstone/superseded revision；不物理刪除、不卡掉 historical denominator 的 audit count，也不把舊結果改寫成新結果。
- 任一 identity、PIT、hash、cost、horizon、label contract conflict 都是 `blocked/conflict`，不是自動修正。

## 4. Statistical contract：哪些算、哪些不算

### 4.1 三個不同 denominator

V6 receipt 必須分開列出以下 counts，不可以只報一個 sample size：

1. `prediction_available_count`：scope 已明確、exact recommendation/prediction receipt 可讀、PIT/provenance valid 的 delivered prediction。這個分母可以包含 `not_recorded`、accepted、skipped；它回答 calibration 是否對所有交付預測負責。
2. `outcome_ready_count`：上述 prediction 有同一 label contract、同一 horizon、成熟且 valid 的 outcome。pending、matured_missing、invalid、conflict、duplicate 不進 ready metric。
3. `action_utility_count`：只有 action semantics 與 utility label 相容，且有真實／研究 execution outcome、cost contract 完整的 row。skipped/not bought 不進 PnL 分母，也不編成 0。

另外報 `action_recorded_count`、`action_not_recorded_count`、`accepted_count`、`skipped_count`、`held_count`、`buy_count`、`sell_count`、`paper_count`、`natural_count`、`declared_context_count`、`replay_count`、`synthetic_count`、pending/missing/conflict/duplicate counts。

### 4.2 action／holding／未買／賣出的規則

| 狀態 | prediction calibration | action utility / risk | 禁止解讀 |
|---|---|---|---|
| `accepted` | 可進同一 delivered prediction cohort；label 仍來自 market outcome | 只有有匹配 execution/fill 或明確 research execution 才進 utility | accepted 不等於買進、不等於報酬 |
| `skipped`／未買 | 可進 prediction calibration，因為 skipped 不是 return 0；另報 skipped coverage | 不進 realized PnL；可做 decision coverage／selection analysis | 不得把未買編成負報酬或 positive failure |
| `not_recorded` | 若 scope/prediction 明確且 label ready，可進 prediction calibration；另報未記錄比例 | 不進 action-conditioned utility | 不得把未記錄推成 skipped 或 held |
| `held` | 依 prediction identity 與 label contract 決定；holding state 不是 outcome | 可進持有風險／MAE cohort，必須有 exact decision revision 與 horizon | held 不等於成功；user_declared holding 無 exact result 不得進 calibration |
| `buy`／`accepted + paper` | 可進 prediction calibration；action label 仍不可取代 market label | 只有 exact Paper fill／research execution identity 與 cost 才進 utility | Paper 不等於 broker execution；不得進 formal portfolio |
| `sell`／`exit` | 使用 predeclared sell/downside/exit label，與 buy/upside 另分 target | 需 exact sell event、持有來源與 exit cost；獨立報 risk/utility | 不得把 sell 與 buy/upside 混在同一 Brier |
| `user_declared_holding` | `excluded_user_declared`；只有 exact recommendation link 才能作 context join | 可做 declared context／mark-to-declared-cost 報表 | holding_id 不能變成 decision_id，不能給 calibration credit |

### 4.3 missing、duplicate、delete/edit 與 tier

- horizon 尚未到：`pending_maturity`，保留 prediction，不能進分母，也不是 negative evidence。
- horizon 已到但 price/outcome 缺失：`matured_missing`，從 metric denominator 排除，統計為 data gap；不能編 0、不能算 model fail。
- outcome invalid、PIT future、source snapshot mismatch、candidate/hash/cost/horizon mismatch：`invalid/conflict`，拒絕 metric，保留 diagnostic。
- exact duplicate：idempotent、只計一次；conflicting duplicate：quarantine，兩筆都不進 metric，等待人工處理。
- delete/edit：只使用最新合法 revision 作 current projection；歷史 revision 與 superseded/tombstone 數量留在 audit，不物理刪除、不回填成新的自然樣本。
- `natural_forward`、`paper_research`、`historical_replay`、`synthetic_fixture` 永遠分 cohort；replay/synthetic 只能驗證程式與 offline protocol，不提供 natural credit。

## 5. Population baseline 與 personal challenger 的公平 offline protocol

### 5.1 Baseline 定義

population baseline 是「同一個 delivered recommendation row、同一個 feature snapshot、同一個 decision cutoff、同一個 universe policy、同一個 label/horizon、同一個 cost scenario」下的既有 population output：優先使用 active/champion calibrated probability。若該 row 的 population probability 不可驗證，personal probability 只能是 unavailable；rule score、percentile、row order 與 null benchmark 都不得作 probability fallback，null benchmark 只能獨立列為 reference。baseline 不能在 user-selected subset 上重新 fit，不能用目前 winners 反推過去。

`ranking_score_bp`、`ranking_percentile_bp` 與 model probability 分欄保存。推薦 top-N 的 `selection_authority` 仍是 rule／portfolio selection；personal calibration 只改 probability projection，第一階段不改 selection authority。

### 5.2 固定 personal challenger：calibration overlay，不重寫 learner

personal calibration 的 fit 與 evaluation 是兩個不可互換的 API。fit 只讀取 fit_rows，產生不可變的 PersonalizationFitArtifact（fit_as_of、fit_row_fingerprint、fit_policy_hash、overlay_hash、bin/prior contract）；evaluate 只接受該 artifact 與 evaluation_rows，並以 prediction_id/row_id exact disjoint check 拒絕 overlap。evaluation labels 不得先被用來計算該 artifact 的 bin rate。

第一個 challenger family 定義為 fixed bin-wise personal shrinkage calibrator：

- 先固定 probability bins、target、horizon、cost scenario、universe/policy 與 prior strength `k`；這些設定在 evaluation 開始前寫入 policy hash，holdout 後不得調參。
- 對每個固定 bin，以 personal matured rows 的 positive count／count 得到 observed rate bp，再向同一 bin 的 population rate／baseline probability shrink：

  `personal_probability_bp = round_bp((n_personal * personal_rate_bp + k * population_bin_rate_bp) / (n_personal + k))`

- `n_personal=0`、scope 缺失或 provenance 不完整時，effective output 必須等於 population baseline，status=`population_cold_start`，不是 0、不是 natural failure。
- `after_cost` 只使用 cost scenario exact match 且 liquidity/cost 可計算的 rows；fixed、estimated、missing cost 不混為一個 target。
- 所有輸入為 integer counts／bp，比例與四捨五入使用 Decimal 或整數分子分母；不把 personal overlay 包裝成新的 sklearn learner，也不改動既有 `RecommendationCalibrationTrainingService`。

這個 challenger 是 V6 first slice 的 offline/shadow candidate，不是 production model。若未來要換 personal learner，必須另立固定 candidate family、training manifest、untouched holdout 與 scoped authority；不能每次挑 holdout 表現最好的模型。

### 5.3 歷史 walk-forward、時間切分與 look-ahead

歷史 action 狀態依 evaluation_cutoff_at 讀取 revision.created_at <= cutoff_at 的最後合法 revision；事後 skip／tombstone／edit 只產生新的 current/correction receipt，不改寫已 freeze 的 delivered prediction 或舊分母。若要重算，必須建立新 cutoff 與新 receipt。

對每個 `personalization_scope_id`：

1. 先依 `decision_date` 排序，所有 feature／prediction provenance 必須在決策日可取得。
2. train/fit cohort 只包含 `label_available_date <= training_cutoff` 的 matured rows；label end、outcome data_as_of、action timestamp 不能穿越 cutoff。
3. 使用 expanding time split；保留與 population learner 相同的 purge/embargo 邏輯，避免 horizon overlap。若 personal rows 太少，不自行縮短 purge，也不把 future labels 借給前一 fold。
4. challenger policy、bin、prior strength、minimum sample/date gates 在 holdout 前 freeze；untouched holdout 只評估一次，不能用結果回頭改 policy。
5. baseline 與 challenger 必須在完全相同 `row_id`／`prediction_id`、label、horizon、cost、benchmark、data quality cohort 上 pairwise compare；被 personal action selection 排除的 row 仍保留為 coverage diagnostic。
6. 不做 accepted-only survivorship training。accepted/skipped/held 是 action subgroup；prediction calibration 的主結果以所有 scope-linked delivered prediction 報告，action utility 另行報告。
7. scope 缺失、source contract mismatch、user-declared-only、future available date 或 exact identity 不成立的 row 不進 personal cohort；不能以 population aggregate 偽造 user-level evidence。

### 5.4 Sparse、cold start 與 adoption threshold

即使 n=0，每個 row 的 effective probability 也必須 value-equivalent 於該 row 的 population_probability_bp。population probability 缺失時回傳 unavailable；禁止用 ranking score、percentile 或其他 row order fallback。null benchmark 只能獨立列為 reference，不是 population baseline。
- `n=0`：輸出 population baseline；receipt 標示 `personal_cold_start`。
- `0 < n < minimum_matured_rows` 或 distinct decision dates 不足：仍輸出 population／shadow overlay diagnostic；不改 active output、不阻塞既有 global learner。
- 達到 engineering threshold 只代表 evaluator、receipt、metrics、rollback 可運作；達到 natural/adoption threshold 才能進入另行審查，不能把兩者混稱。
- natural sample=0 時允許完成 offline contract／fixture／historical replay QA；只能顯示 `insufficient_natural_evidence`，不可宣稱候選人優於 baseline，也不應把「沒有自然證據」當 negative model label。
- personal scope 的 output 不得寫 global `recommendation-calibration-active-pointer.json`。在有 scoped pointer 與正式 authority 前，一律 `shadow_only=true`、`formal_order_allowed=false`、`auto_action_allowed=false`。

## 6. Metrics、uncertainty 與 quality reporting

### 6.1 Calibration metrics

Wilson／Beta 只作 per-bin descriptive reliability CI。由於同一 decision day 的多股 rows 與 overlap horizon 不獨立，receipt 必須另標 independence_assumption=descriptive_only、adoption_confidence_status=adoption_not_evaluable。真正 adoption 需要 predeclared paired-row、decision-day/overlap-block 聚合的 dependency-aware method（或既有已驗證 cluster/block method）；普通 Wilson、row count 或單純 Brier difference 不得當 adoption confidence。
每一個 target／horizon／cost／cohort 都要各自輸出：

- Brier：沿用 integer-bp convention，`round(Σ(probability_bp - label*10000)^2 / (n*10000))`；與既有 `_brier_bp`／OOC metric convention 對齊。
- Reliability table：固定 bins 的 `bin_count`、mean predicted bp、observed positive-rate bp、gap bp、population/challenger difference。
- ECE／calibration gap：使用既有 integer-bp convention；沒有足夠 bin count 時標示 `not_evaluable`，不輸出假精確小數。
- uncertainty：每個 proportion/bin 以 counts 產生 Wilson 或預先固定的 Beta interval，保存 `interval_method`、`lower_bp`、`upper_bp`、`confidence_level_bp`、`sample_count`；CI 計算不能混用不同分母。
- report `matured_sample_count`、`distinct_decision_date_count`、pending/missing/invalid/conflict/duplicate counts；任何 Brier improvement 都附 matched row fingerprint。

### 6.2 After-cost utility、risk 與 probability 分離

- probability calibration 只評估 probability 對 binary label 的一致性；不能以 realized return 代替 Brier。
- after-cost utility 使用 `gross_return_bp`、`liquidity_cost_bp`、commission/tax/slippage Decimal、`net_return`／`profit_label`；沒有完整 cost contract 就是 unavailable，不是 net return=0。
- risk 至少分開報 MAE、MFE、downside/negative label rate、limit/suspended/tradable coverage、outcome missing rate 與 uncertainty；不要把「機率高」當成低風險。
- paper／estimated cost 的結果只能進 research utility／diagnostic tier；natural observed outcome 與 Paper fill 不合併，不將 Paper credit 提前給自然 authority。

### 6.3 Ranking 與 probability 的驗收規則

任何 receipt／DTO 若同時有 ranking 與 probability，必須能回答：

- 此 row 為何被選入？看 `selection_authority`、rule score、top-N/universe policy。
- 此 probability 如何得到？看 model/candidate、transform、baseline、dataset/provenance、cost/label contract。
- calibration 改變了什麼？只能說 probability projection；除非另有 freeze 的 selection experiment，不能聲稱 ranking／portfolio allocation 改善。

## 7. Daily loop：capture → maturity → evaluation → shadow adoption/rollback

第一階段不新增排程；只把既有流程與 V6 scope/action join 定義清楚。

```text
既有 Recommendation / projection receipt
        │ exact result_id + stock_code + prediction/provenance
        ▼
DecisionContinuity / Journal typed action envelope
        │ explicit personalization_scope_id + action revision
        ▼
Read-only PersonalizationProjectionService
        │ join EvidenceEvent / EvidenceOutcome / Paper read adapter
        ▼
OutcomeMaturityService + matured natural/paper/replay tier separation
        ▼
Matched population baseline vs fixed personal challenger
        │ Brier / reliability / utility / risk / CI / denominator receipt
        ▼
shadow decision receipt（retain population / continue shadow / rollback）
        │ fail-closed；formal_order_allowed=false
        ▼
future scoped authority only after explicit gate and natural evidence
```

### 7.1 Decision-day capture

- delivery caller 在 prediction 交付時明確提供 PersonalizationDeliveryScope；batch 寫入 RecommendationResultDTO.run_context["personalization_scope"] 與 inference projection receipt selection_contract["personalization_scope"]，per-candidate calibration_provenance 只保存同一 envelope/hash 的連結。沒有 scope 的 delivery 永久是 unbound，不能在 action 時回補。
- capture 保存 timezone-aware decision_at、available_at、captured_at 並正規化 UTC；date 欄位只作 trading-day grouping。captured_at > decision_at 或 available_at > decision_at 一律 temporal/PIT invalid。

- 在 recommendation result/projection 已持久化後，保存 exact `result_id`、`stock_code`、decision date、scope、prediction receipt hash、source snapshot/PIT/provenance、model/dataset/cost/horizon。
- `RecommendationPredictionCaptureService`／active capture 的 source contract 仍是 prediction lineage；V6 不在 capture 中自行計算 future label。
- 使用者 action 走 `PersonalizationDecisionRecorder` → `DecisionContinuityController` → `JournalService`，同一 request id 重試回傳原 revision；不能直接寫 personal ledger。
- 若使用者沒有做 action，顯式保存或投影 `not_recorded`；不能在 daily job 以 absence 推成 skipped。

### 7.2 Maturity 與 outcome

- 以 `OutcomeMaturityService.evaluate` 和 official trading calendar 計算 expected maturity；保存 calendar id/version、evaluated_as_of、remaining days。
- natural outcome 由既有 `EvidenceEventRepository`／outcome producer 按 exact event/horizon/return basis 產生；V6 assembler 只讀並驗證，不以 current quote 重算歷史 identity。
- paper outcome 由 `PaperTradeLedger` read-only adapter 讀 fill、source event、cost 與 research-only flags；只有經 `source_result_id`/candidate/symbol exact join 才可掛到 prediction。
- user-declared row 只在有 exact recommendation link 時作 context；無 link 時輸出 `excluded_user_declared`。

### 7.3 Evaluation 與 shadow decision

- evaluator 只在 matured ready rows 上計算 metrics；pending/missing/invalid/conflict/duplicate 全部出現在 receipt counts。
- natural evidence 的 same sample/same cost/same candidate identity gate 重用既有 authority 的驗證精神；不要拿 historical replay 或 fixture 冒充 natural forward。
- V6 first slice 產生 scope-specific `retain_population`／`continue_shadow`／`blocked`／`rollback_to_population` receipt，不改 existing global active pointer。
- 之後若要接 `RecommendationCalibrationPromotionAuthority.evaluate_and_apply`，必須先有 scoped candidate identity、scoped pointer、scope-specific lineage 與 authority policy；不能把個人 challenger 當成 global candidate 直接 adopt。

### 7.4 Fail-closed rollback

以下任一條件立即回到 population baseline 或 unavailable，不保留 personal overlay：

- user scope、result/candidate/prediction identity 缺失或 conflict。
- feature available date future、source snapshot／feature transform／dataset／model／cost／label／horizon hash mismatch。
- matured outcome 的 identity、row fingerprint、sample count、metric receipt 重算不一致。
- personal challenger gate、drift、uncertainty、minimum sample/date 或 data quality gate 未通過。
- action/outcome tier 被錯誤混合，或 Paper/declared/replay 被誤標 natural。
- active/global authority 無法 verify、pointer 不一致或 output root 受到 formal DB/order path 影響。

rollback receipt 必須保存 reason、previous population identity、scope、evaluated_as_of、matched sample fingerprint、formal/action flags；失敗時不得 silently fallback 到另一個 versionless model。

## 8. 第一個可實作 slice（只作為後續 engineering ticket，不在本輪實作）

### 8.1 建議新增／最小修改範圍

First-slice ownership is intentionally narrow：

- delivery binding 由 app_module/recommendation_service.py 接收明確的 PersonalizationDeliveryScope，寫入 last_run_context，並傳給既有 inference projection receipt builder；不從 profile_id、portfolio 或 action 猜 scope。
- batch save/readback 由 app_module/recommendation_save_coordinator.py 負責：build_result() 將 last_run_context 的 canonical scope 放進 RecommendationResultDTO.run_context，persist() save 後立即 read back，驗證 result_id、scope envelope/hash、projection receipt hash 與每個 RecommendationDTO.calibration_provenance 一致；無 action 也必須保留 delivery scope。
- receipt/provenance 由 ml_module/recommendation_inference_provenance.py 與既有 recommendation_calibration_evidence.py 負責最小向後相容欄位擴充：optional decision_at/available_at/captured_at、selection_contract.personalization_scope、legacy temporal_precision_unproven；不改既有 candidate/model/learner semantics。
- Journal/Continuity 只負責 action revision，Evidence/Paper 只負責 outcome，personalization_projection.py 只做 read-side exact join，personalization_calibration.py 只做 frozen artifact 之後的 evaluation。K 只處理 UI/widgets/tests 接線，不修改上述 production services；本 slice 的 service/save/readback 接線由此 ownership 負責。任何模組都不得建立 parallel personal ledger。

| 檔案／模組 | 目的 | 邊界 |
|---|---|---|
| `app_module/personalization_contract.py`（新增） | typed identity、prediction/outcome/action envelope、status、hash、denominator DTO 與 validation | 不保存資料；只定義 contract，不複製 `DecisionIdentity` 或 Evidence DTO 的既有語意 |
| `app_module/personalization_projection.py`（新增） | read-only assembler：Recommendation result/projection + Journal revisions + Evidence event/outcome + Paper read adapter + user-declared context | 不建立新 ledger；所有 source 都 exact join；read path 不呼叫會 mkdir/schema/write 的 repository constructor |
| `ml_module/personalization_calibration.py`（新增） | fixed bin-wise Decimal/integer-bp shrinkage、matched baseline/challenger metrics、CI、cold-start policy | 不呼叫／修改 learner fit；不改 global active pointer；不使用 post-hoc best-model selection |
| `app_module/journal_service.py`、`app_module/decision_continuity_controller.py`（最小向後相容修改） | 讓既有 revision payload 可帶 typed personalization envelope、scope、prediction receipt hash、decision kind | 仍使用既有 request id/CAS/revision chain；不新增 `personalization.jsonl`、SQLite ledger 或 parallel portfolio state |
| `scripts/inspect_personalization_contract.py`（新增） | deterministic fixture/readback runner，產生 contract receipt、hash、counts、metrics、negative-case diagnostics | 使用 temporary fixture root；不得寫正式 DATA_ROOT、formal DB、broker、scheduler 或 active pointer |
| `tests/test_personalization_contract.py`、`tests/test_personalization_projection.py`、`tests/test_personalization_calibration.py`（新增） | contract、join、metrics、cold-start、dedupe、PIT、rollback negative tests | bounded targeted tests；不先開 full pytest/Qt/scheduler |

production first-slice 的 acceptance 不能只 instantiate DTO：使用既有 RecommendationService → RecommendationSaveCoordinator → RecommendationRepository save/readback 路徑，傳入 delivery_scope、故意不寫任何 action，驗證 persisted RecommendationResultDTO.run_context 與每個 candidate calibration_provenance 仍有相同 scope envelope/hash、projection receipt/result_id 可反查。測試 owner 是既有 tests/test_recommendation_save_coordinator.py 與 tests/test_recommendation_service_calibration_integration.py，必要時只新增 bounded integration case；K 不修改這些 production service。

### 8.2 介面草案

最小 evaluator API 必須拆開：

```python
PersonalizationDeliveryScope(
    scope_id: str,
    scope_type: str,
    declared_at: str,
    decision_at: str,
    envelope_hash: str,
)

RecommendationService.run_recommendation(
    ...,
    delivery_scope: PersonalizationDeliveryScope | None = None,
) -> list[RecommendationDTO]

RecommendationSaveCoordinator.persist(
    ...,
    delivery_scope: PersonalizationDeliveryScope | None = None,
) -> RecommendationSaveOutcome

build_inference_projection_receipt(
    ...,
    delivery_scope: Mapping[str, Any] | None = None,
)

PersonalizationDecisionRecorder.record_action(
    *,
    personalization_scope_id: str,
    decision_identity: DecisionIdentity,
    action: str,
    decision_kind: str,
    prediction_receipt_hash: str,
    request_id: str,
    action_at: str,
    actor: str,
    payload: Mapping[str, Any] | None = None,
) -> DecisionContinuityRevision

PersonalizationProjectionService.build_for_candidate(
    *,
    personalization_scope_id: str,
    result_id: str,
    stock_code: str,
    evaluated_as_of: str,
) -> PersonalizationDecisionEvidence

PersonalizationCalibrationEvaluator.fit(
    *,
    fit_rows: Sequence[PersonalizationEvaluationRow],
    fit_as_of: str,
    policy: PersonalizationCalibrationPolicy,
) -> PersonalizationFitArtifact

PersonalizationCalibrationEvaluator.evaluate(
    *,
    artifact: PersonalizationFitArtifact,
    evaluation_rows: Sequence[PersonalizationEvaluationRow],
    evaluated_as_of: str,
) -> PersonalizationEvaluationReceipt
```

實際實作須將 mutable default 改為 immutable／`None` 形式，並沿用現有 DTO 的 strict mapping、date、bp、hash validation。`PersonalizationProjectionService` 回傳 `population_only`、`personal_shadow`、`pending`、`blocked` 等 explicit status，不能只回傳 probability。

### 8.3 First-slice definition of done

- fit artifact 與 evaluation rows 分離；任何 exact row/prediction overlap、fit cutoff 後 label 或 policy/overlay hash 不一致都拒絕。
- delivered scope 在 result/run receipt 產生時已存在；只在 action 時才出現的 scope 不得回填 prediction denominator。
- evaluation receipt 保存 evaluation_cutoff_at 與當時最後合法 revision；事後 skip/tombstone/edit 不改寫舊 receipt。
- reliability CI 明確標 descriptive-only；在 paired decision-day/overlap-block method 未完成前，adoption_confidence_status 必須是 adoption_not_evaluable。
- 相同 scope + exact result/stock + same request id 的 retry 不增加 revision；不同 payload 被拒絕並留下 conflict receipt。
- 無 result id、scope 缺失、`source_id` 偽裝 result、holding-only、future available date、source/hash/cost/horizon mismatch 全部 fail closed。
- projection 可從既有 sources 重建 exact prediction provenance；不在 UI 或 evaluator 中重算 model output。
- pending、matured_missing、invalid、natural、paper、declared、replay、synthetic 的 counts 與 denominators 可區分。
- n=0／sparse 的 effective probability 等於 population；personal challenger 只在 fixed policy 下產生 shadow metrics。
- baseline/challenger 使用相同 row fingerprint；Brier/ECE/reliability/CI 與 after-cost/risk 分開，全部有 integer bp/Decimal contract。
- personal scope evaluation 不會寫 global active pointer、formal DB、broker、Portfolio order、Paper append 或 scheduler state；receipt 固定 `formal_order_allowed=false`、`auto_action_allowed=false`。
- runner 能產生可重算的 JSON receipt，含 source hashes、policy hash、sample counts、metric denominators、decision/reason、artifact hash。

## 9. Runner evidence 與 QA acceptance matrix

### 9.1 既有可引用 evidence（本輪不重跑）

以下既有路徑是 V6 first slice 的 regression dependencies，不代表 V6 personal effect 已證明：

- `tests/test_recommendation_calibration.py`、`tests/test_recommendation_calibration_training.py`：dataset、label、purged split、calibration、untouched evaluation。
- `tests/test_recommendation_calibration_learning_runner_lineage.py`、`tests/test_daily_recommendation_learning_loop.py`、`tests/test_banktaiwan_recommendation_learning_operational.py`：daily runner、lineage、receipt、shadow isolation。
- `tests/test_recommendation_capture_source_binding.py`、`tests/test_recommendation_service_calibration_integration.py`：capture/projection/provenance binding。
- `tests/test_decision_continuity_controller.py`、`tests/test_decision_continuity_write_path.py`、`tests/test_decision_outcome_journey.py`、`tests/test_continuity_review_workbench_r1.py`：exact identity、CAS、readback、journal history。
- `tests/test_user_declared_holding_research.py`、`tests/test_paper_trade_ledger.py`、`tests/test_paper_daily_execution_producer.py`、`tests/test_evidence_event_repository.py`、`tests/test_outcome_maturity_service.py`：research-only、evidence、maturity 與 Paper separation。

### 9.2 新 runner receipt contract

`scripts/inspect_personalization_contract.py --fixture` 後續應輸出 `personalization-contract-runner-receipt.v1`，至少包含：

```json
{
  "schema_version": "personalization-contract-runner-receipt.v1",
  "run_id": "...",
  "evaluated_as_of": "YYYY-MM-DD",
  "personalization_scope_id": "explicit-scope",
  "scope_type": "user",
  "input_prediction_count": 0,
  "linked_prediction_count": 0,
  "prediction_available_count": 0,
  "outcome_ready_count": 0,
  "action_utility_count": 0,
  "pending_maturity_count": 0,
  "matured_missing_count": 0,
  "invalid_count": 0,
  "duplicate_exact_count": 0,
  "duplicate_conflict_count": 0,
  "baseline_metrics": {},
  "personal_challenger_metrics": {},
  "cohort_counts": {},
  "source_hashes": {},
  "delivery_scope_hash": "...",
  "decision_at": "...+00:00",
  "captured_at": "...+00:00",
  "fit_as_of": "YYYY-MM-DD",
  "fit_row_fingerprint": "...",
  "fit_policy_hash": "...",
  "overlay_hash": "...",
  "evaluation_row_fingerprint": "...",
  "independence_assumption": "descriptive_only",
  "adoption_confidence_status": "adoption_not_evaluable",
  "policy_hash": "...",
  "matched_sample_fingerprint": "...",
  "decision": "retain_population",
  "reason": "...",
  "natural_forward_credit": false,
  "shadow_only": true,
  "formal_order_allowed": false,
  "auto_action_allowed": false,
  "receipt_hash": "..."
}
```

### 9.3 Bounded acceptance cases

| ID | case | expected result |
|---|---|---|
| P-01 | exact `scope + result_id + stock_code`、有效 projection receipt、PIT valid | `linked_prediction`，保存全 lineage |
| P-02 | missing scope、empty result、只有 source_id 或只有 holding_id | `population_only`／`blocked`，不進 personal denominator |
| P-03 | same request id + same payload retry | 回傳原 revision，revision count 不增加 |
| P-04 | same request id + changed action/scope/snapshot | conflict，拒絕覆寫 |
| P-05 | accepted、skipped、not_recorded、held、buy、sell 混合 | action counts 分開；not_recorded 不推 skipped；sell 不混 buy label |
| P-06 | user-declared holding 沒有 exact recommendation result | `excluded_user_declared`，無 calibration/effectiveness credit |
| P-07 | recommendation event exact link，但 outcome horizon 未到 | `pending_maturity`，不進 metrics、不算 negative |
| P-08 | horizon 已到但 missing price／future data | `matured_missing`，不進 metrics，增加 data-gap count |
| P-09 | duplicate exact outcome | 只計一次並記 duplicate diagnostic |
| P-10 | conflicting duplicate / same event with changed return | conflict/quarantine，兩筆不進 metrics |
| P-11 | future feature available date、snapshot/hash/model/cost mismatch | fail closed，fallback population／unavailable |
| P-12 | Paper fill source_event 可讀但 source_result/candidate 不匹配 | 不 join；Paper 不升級為 personal natural outcome |
| P-13 | population and personal rows differ in horizon/cost/universe | evaluator refuse comparison；無 Brier improvement claim |
| P-14 | n=0／sparse personal rows | effective probability equals population；`personal_cold_start`／`continue_shadow` |
| P-15 | fixed shrinkage matched rows | Brier/ECE/reliability/CI 可重算；policy hash 與 row fingerprint 一致 |
| P-16 | accepted-only utility test | utility denominator 只含 valid execution；skipped 不被編成 0 PnL |
| P-17 | tombstone/edit/superseded revision | current projection 依 chain；舊 audit 保留，不物理刪除 |
| P-18 | provenance/metric/drift gate fault | `rollback_to_population`，formal/auto flags 皆 false |
| P-19 | replay/synthetic fixture with apparent improvement | 可驗證程式，但 `natural_forward_credit=false` |
| P-20 | natural sample=0 | offline contract runner 可成功；decision 為 insufficient/retain，不宣稱效果 |

| P-21 | available_at 或 captured_at 在 decision_at 之後、只有同日 date | temporal/PIT invalid；不得只因 available_date 等於 decision_date 而通過 |
| P-22 | 無任何 action，但 delivery 已帶明確 scope；save coordinator 寫入後 read back | prediction_available denominator 保留 scope；action 狀態為 not_recorded，不需等 action 才成立 |
| P-23 | fit/evaluation row id overlap，或 population probability 缺失 | fit/eval 拒絕 overlap；缺 population probability 回傳 unavailable，不使用 rank/percentile |
| P-24 | evaluation cutoff 後才來的 skip/tombstone/edit | 舊 frozen receipt/denominator 不變；只產生 current/correction 新 receipt |
| P-25 | 多股同日或 overlap horizon 的普通 Wilson CI | 只標 descriptive_only；adoption_confidence_status=adoption_not_evaluable |

後續實作完成後的 bounded command 建議為：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_personalization_contract.py tests/test_personalization_projection.py tests/test_personalization_calibration.py -q -o addopts=
.\.venv\Scripts\python.exe scripts\inspect_personalization_contract.py --fixture
.\.venv\Scripts\python.exe -m py_compile app_module\personalization_contract.py app_module\personalization_projection.py ml_module\personalization_calibration.py scripts\inspect_personalization_contract.py
```

本輪不執行以上命令；它們是下一個 implementation/QA turn 的驗收路徑，不是本文件的測試結果。

## 10. 具備、待做、自然效果待證

| 分類 | 目前狀態 | 證據／下一步 |
|---|---|---|
| 已具備 | population dataset、PIT labels、purged/OOF calibration、candidate/manifest/artifact lineage、inference provenance、active/champion consumer、natural capture/maturity/authority、exact continuity identity/CAS、research-only user-declared、Decimal Paper ledger | 既有 `recommendation_calibration*`、`recommendation_calibration_evidence.py`、`recommendation_calibration_authority.py`、DecisionContinuity/Journal、EvidenceEvent、Paper tests/QA docs |
| Engineering to do | explicit scope contract、typed action payload、read-only cross-source assembler、fixed personal shrinkage evaluator、same-row metric/CI receipt、negative cases、deterministic inspection runner、scope-specific rollback receipt | 本文件第 3、5、8、9 節；不重寫既有 learner、不新增 ledger |
| Natural effect to prove | 真實 user decision 數量與成熟 natural outcomes、個人 challenger 在 untouched post-cutoff cohort 相對 population 的 calibration/utility/risk 結果、coverage/survivorship、drift、rollback、source/data quality | 必須等 real scope-linked decision/outcome evidence；historical replay、fixture、Paper、user-declared 不能代替 natural proof |
| 不在本輪 | UI 跨頁接線、Manual、SSOT/Roadmap、L official taxonomy、K cross-page integration、global active pointer、formal order/portfolio/broker | 另立 dependency ticket；本文件只提供 contract/acceptance boundary |

## 11. 風險與回滾清單

### 11.1 主要風險

- `profile_id`、portfolio_id、holding_id、Paper `source_event_id` 被誤當成 user identity，造成跨 scope contamination。
- 僅從 accepted/held/traded rows 學習，造成 survivorship／selection bias；或把 skipped/no result 編成 0 return。
- prediction capture、EvidenceOutcome、Paper fill 的 cost/horizon/source contract 不一致，導致同 sample 名義比較但實際 label 不同。
- merged dataset hash、projection receipt、user action revision 沒有同一個 immutable fingerprint，造成無法重算或重複計數。
- personal candidate 寫入 global pointer 或 formal action path，越過 V6 尚未達成的 authority gate。
- L/K 尚未完成時，UI／來源提供 legacy identity，assembler 若採 guess fallback 會破壞 fail-closed contract。

### 11.2 本輪變更檔案與回滾方式

| 檔案 | 變更類型 | 摘要 | 回滾方式 | 風險 |
|---|---|---|---|---|
| `docs/06_qa/V6_PERSONALIZATION_CONTRACT_PLAN_2026_09_15.md` | 新增 | V6 identity/statistical/daily-loop/QA engineering plan | 經確認未被引用後移除本新增文件；不還原、不碰其他 dirty files | 僅文件移除風險；無資料、程式、DB 或 scheduler 變更 |

本輪不執行任何 destructive rollback command、不清理 `qa-cache-*`、不 reset/checkout 其他檔案、不 stage/commit。後續 implementation 若需要修改 Journal、authority 或 pointer，必須先另開明確 change scope、backup／read-only audit、bounded QA 與專屬 rollback plan。

## 12. 最終判定

V6 現在最安全、可驗收的下一步不是再造一套 personal learner 或 user ledger，而是把既有 Recommendation／Evidence／Continuity／Paper identity 用 `personalization-decision-evidence.v1` 明確封裝，先完成 offline matched evaluation、cold-start/shrinkage、negative cases、receipt 與 population fallback。

只有在 scope-linked natural decision/outcome 足夠、PIT/provenance/cost/label contract 可重算、untouched post-cutoff holdout 與 uncertainty 結果支持時，才可另行審查個人化 adoption；即使如此，仍須保留 fail-closed rollback、no return guarantee、no auto rebalance、no broker order 與 natural/research tier separation。
