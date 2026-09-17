# V6 個人化 Contract / Engineering Plan（2026-09-15）

## 0. 文件定位與本輪邊界

本文件是 V6 evidence-driven personalization 的 code-backed design／acceptance plan，不是 V6 功能完成報告，也不是自然效果宣稱。它以 2026-09-15 的現有程式與 QA 文件為基準，目的在於先把 identity、PIT、outcome、baseline／challenger、統計 denominators、daily loop、rollback 與可驗收 runner 定義清楚。

本輪已完成 C-owned bounded slice：新增／更新 typed contract、read-only projection、固定 Decimal/bp evaluator、deterministic fixture runner 與負向測試，並把 caller-owned local research scope 接到既有 Recommendation save/readback 與 Journal technical delivery ACK 路徑；另以獨立 process 驗證正式 `MainWindow()` 的 save／ACK／readback／close。`PersonalizationDecisionRecorder` 與明示 action CLI 也已接到既有 Journal revision，並以 verified training lineage custody 核對 label contract／return basis。正式 D 槽、自然效果、A/B/L/K 及 V6 adoption 仍不因此完成；Snapshot、Roadmap 與 Manual 只同步本 C-owned 狀態，未改 Git index、scheduler、formal order 或既有 human action 語意。

本文件遵守以下邊界：

- V6 仍是產品方向與 engineering contract；在真實 user decision／mature natural outcome 不足前，不宣稱個人化改善、報酬保證、隱藏缺口已補齊，亦不允許 auto rebalance、broker order 或正式 advice authority 改變。
- L（PIT official taxonomy/source chain）與 K（cross-page continuity integration）是獨立 follow-up dependency；本計畫可以先做 contract、offline evaluation、shadow receipt 與 guardrails，不把 L/K 尚未完成誤報成 V6 已完成。
- 不另造 parallel recommendation、portfolio、paper、user-decision ledger；先重用既有 Recommendation result／projection、EvidenceEvent／EvidenceOutcome、DecisionContinuity／Journal、User-declared research lane 與 Paper research ledger 的 identity，再建立 read-side join/projection。
- 策略、回測、推薦、資金、風控與績效核心欄位以整數 bp、股數、分鐘或 Decimal 表示；任何 sklearn／統計套件的 float 僅能被隔離在既有 analytics boundary，contract 與 receipt 不保存裸 float。
- 所有 prediction、feature、label、cost、action 與 baseline 都做 look-ahead audit；決策日必須使用 timezone-aware `available_at <= decision_at` 且 `captured_at <= decision_at` 的資料，`available_date`／`decision_date` 只作 trading-day grouping；label 只能在 `label_available_date` 後進入成熟 evaluation。

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
| `app_module/decision_continuity_controller.py:95,128,144,276,353` | exact identity readback、CAS/request id idempotency、conflict/read error fail-closed、accepted/skipped/review 等 action 已有 controller；C slice 由 `PersonalizationDecisionRecorder` 在 delivered projection 後委派既有 writer | controller 本身仍不自動產生 personal action；typed scope／prediction receipt 只可由新 recorder 明示放入既有 revision payload，不能由 profile／holding／delivery 推導或替代 user intent |
| `app_module/journal_service.py:25,138,141,203,334` | `record_decision_action`／`record_research_action` 及 `list_decision_revisions`、append-only journal store 可作 user action source；technical delivery ACK 與 typed personal action 都沿用 revision stream | action payload 已支援 optional `personalization_action` envelope；仍須保留 request id／revision chain，且 Journal 的 head CAS／human action 競態不能被 personal wrapper 假定為已完成；任意 note 或 tag 不足以作統計 identity |
| `app_module/user_declared_holding_research.py:476,1339,1396,1476,1613,1946` | user-declared holding 有 immutable holding/revision、PIT custody、Decimal mark、research-only、`calibration_status=excluded_user_declared`、`effectiveness_cohort=excluded_user_declared` | `holding_id` 不得變成 recommendation decision id；沒有 exact `result_id + stock_code` 時只能當 held/position context，不能當 prediction label、calibration credit 或 effectiveness evidence |
| `app_module/paper_trade_ledger.py:34,207,220`、`data_module/paper_daily_execution_producer.py:118,178` | Paper fill 有 exact fill/order/source_event identity、Decimal fill/cost、research-only、broker/auto-rebalance false；producer 以 frozen recommendation `result_id`／`source_result_id` 驗證 source chain | Paper 是 research execution tier，不是 natural user decision；`PaperTradeFill.source_event_id` 不得直接當 user action id；要經 `source_result_id`、candidate/symbol 與 scope join 才能成為 paper outcome row，且仍與 natural outcome 分 cohort |

## 3. V6 `personalization-decision-evidence.v1` contract

這個名稱先代表 logical contract／read-side projection，不代表現在要建立新的資料表或 JSONL ledger。它將既有來源投影成一個可驗證的 immutable view；寫入 user action 時只透過既有 DecisionContinuity／Journal revision，prediction 仍來自既有 recommendation／calibration receipt，outcome 仍來自 EvidenceEvent/EvidenceOutcome 或 Paper read adapter。

### 3.1 Identity envelope

| 欄位 | 必填規則 | 語意與禁止事項 |
|---|---|---|
| `schema_version` | 固定 `personalization-decision-evidence.v1` | schema version 必須進 receipt hash；不可無版本解析 |
| `personalization_scope_id` | 非空、穩定、明確提供 | 可是 opaque user scope，或本機單安裝研究用的明確 local scope；不可由 portfolio、holding、source、strategy 自動推導。scope 不存在時 row 只能 population-only，不能稱 personal |
| `scope_type` | `user`、`profile`、`local` 或明確 future enum | `local` 只表示本機研究 lane，不代表人類身份；`profile_id` 只有在上游明確宣告它就是 scope 時才能使用，既有 recommendation profile 不自動等於 user |
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

個人 scope 必須在 delivered prediction 產生時已存在，而不是等 user action 才補。C slice 以獨立 `personalization-delivery-capture.v1` envelope 保存 scope、request/delivery/prediction identity、PIT clock、既有 projection receipt hash 與 generated/persisted/delivered/not_delivered 狀態；既有 `recommendation-calibration-projection-receipt.v1` 與其 hash 不改寫。Recommendation save/readback 已接入明確的 local caller-owned scope，post-save delivery ACK 追加到既有 Journal 技術事件；在 scope 或 exact readback 缺失時只能輸出 population-only／not_delivered，後續 action 不得事後回填成當時的 personal prediction。

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

personal calibration 的 fit 與 evaluation 是兩個不可互換的 API。fit 只讀取 fit_rows，產生不可變的 PersonalizationFitArtifact（fit_as_of、aware `created_at`、fit_row_fingerprint、row/prediction/statistical/receipt IDs、scope/cohort contract、fit_policy_hash、overlay_hash、bin/prior contract）；ready fit row 必須有精確 `label_available_at`、`outcome_recorded_at` 與 receipt clock，且 artifact `created_at` 不得早於 fit cutoff 日期或任何依賴資料。evaluate 只接受該 artifact 與 evaluation_rows，並以 prediction_id/row_id/statistical identity exact disjoint check 拒絕 overlap。evaluation labels 不得先被用來計算該 artifact 的 bin rate。

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
2. train/fit cohort 只包含 `label_available_date <= training_cutoff` 的 matured rows；label/outcome 必須有 timezone-aware availability／recorded clock，`created_at` 不得早於 `fit_as_of` 日期或其依賴時間；label end、outcome data_as_of、action timestamp 不能穿越 cutoff。
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
PersonalizationDeliveryCaptureService
        │ explicit scope + delivery/prediction identity + PIT clocks
        ▼
Read-only PersonalizationProjectionService
        │ exact result/candidate/receipt；未交付不進 prediction denominator
        ▼
DecisionContinuity / Journal exact action read adapter
        │ action absence = not_recorded；不反推 skipped
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

- `PersonalizationDeliveryCaptureService.capture()` 在 prediction 交付前接收 caller 明確提供的 `PersonalizationDeliveryScope`，建立 immutable `delivery_id + request_id + prediction_id + projection_receipt_hash` capture。沒有 scope 的 delivery 永久是 unbound，不能在 action 時回補。
- capture 保存 timezone-aware decision_at、available_at、captured_at 並正規化 UTC；date 欄位只作 trading-day grouping。captured_at > decision_at 或 available_at > decision_at 一律 temporal/PIT invalid。
- capture 的 `generated` → `persisted` → `delivered` transition 是 immutable DTO transition；`PersonalizationDeliveryCaptureService.verify_saved_capture()` 只做既有 RecommendationResult readback 驗證，不自行寫檔或建立 ledger。
- 在 recommendation result/projection 持久化邊界，保存 exact `result_id`、`stock_code`、decision date、scope、prediction receipt hash、source snapshot/PIT/provenance、model/dataset/cost/horizon。若沒有通過保存 readback，capture 不能進 prediction denominator，projection 以 `not_delivered` 或 `unavailable` 表示。
- `delivered_at` 是 UI／caller 的實際交付 clock，不是 captured_at 的替代品；late delivery 只作 exposure diagnostic，不給 natural delivery credit。first slice 不回寫已保存的 immutable result；post-save ACK 需另指定既有 append-only persistence 後再審查。
- `RecommendationPredictionCaptureService`／active capture 的 source contract 仍是 prediction lineage；V6 不在 capture 中自行計算 future label。
- 既有 Controller action 的一般 UI 語意維持不變；新增的 bounded `PersonalizationDecisionRecorder` 只作明確 personal action 入口，驗證 delivered prediction 的 scope／result／stock／prediction／receipt／horizon／cost／label／return contract 後，委派既有 `DecisionContinuityController`／`JournalService` revision。舊 action 沒有 personal envelope 時只作 legacy diagnostic，禁止 retrofit；任何入口都不能直接寫 personal ledger。
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

## 8. 第一個可實作 slice 與 shared hook gate

### 8.1 建議新增／最小修改範圍

First-slice ownership is intentionally narrow；本輪已完成下列 C-owned read／offline 部分，並已獲准把 caller-owned local research scope 接到既有 recommendation save/readback path，以及提供受控、明示的 action writer entry：

- `PersonalizationDeliveryCaptureService` 接收明確 `PersonalizationDeliveryScope`，建立 immutable capture；不從 profile_id、portfolio、holding、source_id 或 action 猜 scope。
- `PersonalizationProjectionService` 只做 read-side exact join；不建立 repository、資料表、ledger、active pointer 或寫入副作用。
- `PersonalizationCalibrationEvaluator` 只做 frozen artifact 之後的 fixed bin-wise Decimal/integer-bp evaluation；fit/evaluation identity、PIT、purge/embargo、delivery status、outcome status 都 fail closed。
- `RecommendationSaveRequest` 的 save/readback binding 只接受明確 caller-owned scope；正常 recommendation composition 由 `PersonalizationRecommendationSaveAdapter` 產生 `scope_type=local` 的本機研究 scope，不能以 profile／holding 假扮 user，也不能讀 live `last_run_context` 作最後 identity。capture 會附在既有 `RecommendationResultDTO.run_context` 與 candidate provenance，並沿用既有 result persistence 做 exact readback；舊 projection receipt body 不改寫。
- post-save delivery ACK、retry、CAS/identity conflict、repository save error、cross-scope、late delivery 與未送達狀態只走同一個 capture/result path；沒有 ACK 不能升級成 delivered，也不會把 action 缺失編成 accepted。
- `app_module/decision_continuity_controller.py` 的既有 human action semantics 維持不變；`PersonalizationDecisionRecorder` 只在 read-side verified delivered projection 後，委派既有 `JournalService` JSONL revision append，且本輪不寫 broker、Portfolio order、scheduler 或 active pointer。
- `scripts/inspect_personalization_contract.py --fixture` 僅使用 in-memory fixture；不讀正式資料根目錄、不啟動 scheduler、不建立 active pointer。任何模組都不得建立 parallel personal ledger。

| 檔案／模組 | 目的 | 邊界 |
|---|---|---|
| `app_module/personalization_contract.py`（新增） | typed identity、prediction/outcome/action envelope、status、hash、denominator DTO 與 validation | 不保存資料；只定義 contract，不複製 `DecisionIdentity` 或 Evidence DTO 的既有語意 |
| `app_module/personalization_projection.py`（新增） | read-only assembler：Recommendation result/projection + Journal revisions + Evidence event/outcome + Paper read adapter + user-declared context | 不建立新 ledger；所有 source 都 exact join；read path 不呼叫會 mkdir/schema/write 的 repository constructor |
| `app_module/personalization_calibration.py`（新增） | fixed bin-wise Decimal/integer-bp shrinkage、matched baseline/challenger metrics、CI、cold-start policy | 不呼叫／修改 learner fit；不改 global active pointer；不使用 post-hoc best-model selection |
| `app_module/personalization_projection.py` 內的 `PersonalizationDeliveryCaptureService` | 建立／驗證 generated/persisted/delivered capture、retry identity、既有 result readback contract | 不自行建立新 ledger；save adapter 以既有 recommendation result persistence 保存 capture 狀態，post-save ACK 仍要求 exact result/scope/prediction/CAS identity，舊 projection receipt 不改寫 |
| `app_module/personalization_save_adapter.py`、`app_module/recommendation_save_coordinator.py` | caller-owned local research scope → generated capture → existing save → exact load/readback → explicit delivery ACK 的 composition binding | 只處理 prediction delivery；scope 不從 profile／holding 推導，無 ACK 保持 persisted/not_delivered，錯誤與跨 scope fail closed，不寫 action 或正式交易狀態 |
| `app_module/journal_service.py`、`app_module/decision_continuity_controller.py` | human action writer/controller 維持既有語意；JournalService 提供技術性 delivery ACK 的 append/readback | ACK 沿用既有 JSONL revision chain、request identity 與 history-token CAS；不新增 `personalization.jsonl`、SQLite ledger 或 parallel portfolio state |
| `app_module/personalization_action_recorder.py` | 新 personal action 的受控 facade；保存完整 envelope 並沿用既有 Journal revision／retry | 不 retrofit legacy action；action 必須在 delivery 後，`action_at` 不得早於 `delivered_at`，不寫新 ledger |
| `app_module/personalization_read_service.py`、`scripts/inspect_personalization_sources.py` | 真實 Recommendation／Journal／Evidence／receipt 的 bounded readonly projection、fingerprint、inventory、分母與 optional evaluator | 不建立 writer constructor、lock、DDL、source writes、learner、promotion 或 order；來源變動時 invalidated |
| `scripts/record_personalization_action.py` | 明示 scope/result/stock/action/request 的 CLI preflight → 既有 Journal append → exact readback | preflight 失敗不建立 writer；不自動建立 scope、不 retrofit legacy action、不新增 ledger、不授權 order |
| `scripts/run_personalization_recommendation.py` | 明示 scope/data root/config 執行既有 RecommendationService → save/readback → technical delivery ACK | 無 durable receipt 不保存普通結果；不建立 human action、order 或 parallel ledger |
| `scripts/inspect_personalization_contract.py`（新增） | deterministic in-memory fixture/readback runner，產生 contract receipt、hash、counts、metrics、negative-case diagnostics | `--output` 只 create-only；不得寫正式 DATA_ROOT、formal DB、broker、scheduler 或 active pointer |
| `scripts/qa_personalization_mainwindow_save_readback.py`（新增） | 以獨立 process 呼叫正式 `MainWindow()` constructor，走實際 RecommendationView save → result/Journal ACK → read projection → close/workers probe | 只接受明確隔離的 DATA_ROOT／OUTPUT_ROOT；producer 可用 bounded fixture；不替換 window composition、不寫正式 DB、broker、scheduler 或 active pointer |
| `tests/test_personalization_contract.py`、`tests/test_personalization_projection.py`、`tests/test_personalization_calibration.py`、`tests/test_personalization_runner.py`、`tests/test_personalization_save_integration.py`、`tests/test_personalization_action_recorder.py`、`tests/test_personalization_read_service.py`、`tests/test_personalization_generation_cli.py`（新增） | contract、join、metrics、cold-start、dedupe、PIT、runner、save/readback、ACK、action retry/clock、CLI preflight/append/readback/no-writer gate、producer→save→ACK/custom Journal retry、read source race/WAL/inventory/identity bounds 與 delivery negative tests；另驗證 host integration 與獨立 MainWindow process receipt | bounded targeted tests；不先開 full pytest/scheduler |

shared production first-slice acceptance：使用既有 RecommendationService → RecommendationSaveRequest → RecommendationRepository save/readback 路徑，透過 composition adapter 綁定明確 `scope_type=local` 的 caller-owned research scope，故意不寫任何 action；save 後以 exact `load_result()` 驗證 persisted `RecommendationResultDTO.run_context`、每個 candidate `calibration_provenance` 的 scope envelope/hash，以及 projection receipt/result_id 反查。delivery ACK、retry、CAS/identity conflict、save error、cross-scope、late／未送達均在同一路徑隔離測試；另以獨立 process 的正式 `MainWindow()` constructor probe 驗證真實頁面、window-owned Journal／Repository、save button、ACK、read projection 與單次 close/workers=0；任何未具備 exact readback 的 capture 不可升級成 delivered。

### 8.2 介面草案

最小 evaluator API 必須拆開：

```python
PersonalizationDeliveryScope(
    scope_id: str,
    scope_type: str,
    delivery_id: str,
    declared_at: str,
    decision_at: str,
    available_at: str | None,
    captured_at: str | None,
    receipt_created_at: str,
    envelope_hash: str,  # init=False；由 canonical payload 計算
)

PersonalizationDeliveryCaptureService.capture(
    *,
    scope: PersonalizationDeliveryScope,
    request_id: str,
    result_id: str,
    stock_code: str,
    prediction_id: str,
    projection_receipt_hash: str,
    generated_at: str,
) -> PersonalizationDeliveryCapture

PersonalizationDeliveryCaptureService.verify_saved_capture(
    saved_result: RecommendationResultDTO | Mapping[str, Any],
    capture: PersonalizationDeliveryCapture,
) -> None

request = RecommendationSaveRequest(
    ...,
    personalization_scope=PersonalizationDeliveryScope | None,
    personalization_request_id=str | None,
)
request.persist(
    *,
    recommendation_repository: RecommendationRepositoryPort,
    universe_service: UniverseWatchlistPort | None,
    recommendation_service: RecommendationEvidencePort,
    regime_service: RegimeServicePort,
) -> RecommendationSaveOutcome

PersonalizationRecommendationSaveAdapter.acknowledge_delivery(
    *,
    recommendation_repository: RecommendationRepositoryPort,
    journal_service: JournalService,
    result_id: str,
    scope_id: str,
    delivery_id: str,
    persisted_at: str,
    delivered_at: str,
    recorded_at: str | None = None,
    expected_capture_hashes: Mapping[str, str] | None = None,
) -> RecommendationDeliveryAckOutcome

PersonalizationProjectionService.build_for_candidate(
    *,
    result_id: str,
    stock_code: str,
    personalization_scope_id: str | None = None,
    evaluated_as_of: str | None = None,
    evaluation_cutoff_at: str | None = None,
    result: Mapping[str, Any] | None = None,
) -> PersonalizationProjectionResult

PersonalizationCalibrationEvaluator.fit(
    fit_rows: Sequence[PersonalizationEvaluationRow],
    *,
    fit_as_of: str,
    policy: PersonalizationCalibrationPolicy,
) -> PersonalizationCalibrationFitArtifact

PersonalizationCalibrationEvaluator.evaluate(
    *,
    artifact: PersonalizationCalibrationFitArtifact,
    evaluation_rows: Sequence[PersonalizationEvaluationRow],
    evaluated_as_of: str,
) -> PersonalizationCalibrationEvaluation
```

實際實作已將 mutable collection default 改為 immutable／`None` 形式，並沿用 strict mapping、date、bp、hash validation。缺少 `captured_at` 不會補成 `decision_at` 或升級成 verified；delivery capture service 只接受有 verified captured clock 的 scope。`PersonalizationRecommendationSaveAdapter` 僅消費明確 `local` research scope，將 generated capture 綁入既有 result/run_context 與 candidate provenance，save 後 exact load/readback，再由 caller 將 technical ACK 追加到既有 Journal stream 才可在 read-side 視為 delivered；沒有 ACK 保持 persisted/not_delivered。`PersonalizationProjectionService` 回傳 `linked_prediction`、`population_only`、`not_delivered`、`unavailable`、`duplicate_exact`、`duplicate_conflict` 等 explicit status，不能只回傳 probability；receipt 才是 probability／horizon／decision date／model／dataset 的 verified source，context row 不得覆蓋。Calibration artifact 另存 row、prediction、statistical、receipt identity、scope 與 cohort contract hash，並在 evaluate 邊界重新驗證；`PersonalizationDecisionRecorder`／`scripts/record_personalization_action.py` 已提供受控 human-action writer，只有明示且已 delivered 的 projection 才能追加既有 Journal revision，沒有 UI save 自動 action 或 legacy retrofit。

### 8.3 First-slice definition of done

- fit artifact 與 evaluation rows 分離；exact retry 只計一次，任何 row/prediction/statistical identity overlap、fit cutoff 後 label 或 policy/overlay hash 不一致都拒絕。
- fit/evaluation 必須具有相同 scope 與可比較 cohort contract（tier、source、receipt schema、model、dataset、universe、label、return basis、horizon、cost）；missing lineage 不得推成 verified，natural/replay/fixture 不混樣本。
- delivered scope contract 在 capture 產生時已存在；只在 action 時才出現的 scope 不得回填 prediction denominator。正常 save path 會先保存並 exact readback capture；只有明確 ACK 才是 delivered，沒有 ACK 仍是 persisted/not_delivered。
- calibration evaluation 保存 `evaluation_cutoff_at`；cutoff 不得晚於 `evaluated_as_of`，label/outcome 的 exact availability／recorded clock 必須不晚於 cutoff，日期-only 不進 ready denominator。projection 對 action reader 只讀 cutoff 前最後合法 revision，並以 timezone-aware action/recorded/created clock 排序；事後 skip/tombstone/edit 不改寫既有 capture／receipt。
- reliability CI 明確標 descriptive-only；在 paired decision-day/overlap-block method 未完成前，adoption_confidence_status 必須是 adoption_not_evaluable。
- 相同 scope + exact result/stock + same delivery/request/prediction identity 的 retry 不增加 calibration row；不同 payload 被拒絕並留下 conflict diagnostic。save/readback ACK 的 CAS 在既有 result path 內做 exact compare-and-set；`PersonalizationDecisionRecorder` 具備 request/revision idempotency、既有 Journal append/readback 與 stream lock，但不把一次 read-state 後的 human action head CAS 宣稱為本輪已完成。
- save error、readback 缺 row、cross-scope／cross-result、ACK 重複或 identity conflict、late delivery 與未送達均不污染 prediction identity／denominator；ACK writer 只可在既有 result persistence 內做 exact compare-and-set，不建立 parallel ledger。
- 無 result id、scope 缺失、`source_id` 偽裝 result、holding-only、future available date、source/hash/cost/horizon mismatch、context row 覆蓋 verified receipt、outcome prediction/horizon/label/return contract alias 全部 fail closed。
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

`scripts/inspect_personalization_contract.py --fixture` 已輸出 `personalization-contract-runner-receipt.v1`；目前採 nested `counts`／`metrics`／`hashes`，至少包含：

```json
{
  "schema_version": "personalization-contract-runner-receipt.v1",
  "mode": "fixture",
  "bounded": true,
  "counts": {},
  "metrics": {"baseline": {}, "personal_challenger": {}},
  "hashes": {"scope_envelope_hash": "...", "capture_hash": "...", "projection_receipt_hash": "...", "policy_hash": "..."},
  "projection": {},
  "calibration": {"evaluation_cutoff_at": "...+00:00", "independence_assumption": "descriptive_only"},
  "adoption_confidence_status": "adoption_not_evaluable",
  "policy_hash": "...",
  "matched_sample_fingerprint": "...",
  "decision": "retain_population",
  "reason": "...",
  "natural_forward_credit": false,
  "shadow_only": true,
  "formal_order_allowed": false,
  "auto_action_allowed": false,
  "runner_receipt_hash": "..."
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
| P-22 | 無任何 action，但 delivery 已帶明確 scope；save coordinator 寫入後 read back | （shared hook gate）prediction_available denominator 保留 scope；action 狀態為 not_recorded，不需等 action 才成立 |
| P-23 | fit/evaluation row id overlap，或 population probability 缺失 | fit/eval 拒絕 overlap；缺 population probability 回傳 unavailable，不使用 rank/percentile |
| P-24 | evaluation cutoff 後才來的 skip/tombstone/edit | 舊 frozen receipt/denominator 不變；只產生 current/correction 新 receipt |
| P-25 | 多股同日或 overlap horizon 的普通 Wilson CI | 只標 descriptive_only；adoption_confidence_status=adoption_not_evaluable |
| P-26 | exact duplicate evaluation row 或 row/prediction/statistical identity alias | exact retry 去重；conflicting alias 或 fit/eval overlap 拒絕 |
| P-27 | fit/eval scope、tier、source、model、dataset、receipt schema、universe、label contract 不一致 | cohort contract mismatch；不產生 evaluated metrics |
| P-28 | cutoff 早於 label availability、future outcome clock、evaluated_as_of/cutoff 不一致、date-only ready row | pending/temporal blocked 或 fail closed；不進 denominator |
| P-29 | action/outcome scope、prediction、horizon、cost、label/return basis 缺失或 alias | not_recorded/conflict；不得升格 action/outcome |
| P-30 | fit artifact mapping、fit identity、cohort 或 overlay hash 被事後修改 | immutable write failure 或 artifact validation failure |
| P-31 | context probability/horizon/model/dataset 與 immutable receipt 不同；scope 缺 captured_at | unavailable／population_only；不得使用 context 覆蓋 receipt |
| P-32 | ready fit row 缺 `outcome_recorded_at` 或僅有 date-level availability | fit precision unproven；拒絕建立 fit artifact |
| P-33 | artifact `created_at` 早於 `fit_as_of` 或 label/outcome/receipt dependency | fit creation clock conflict；拒絕建立 artifact |
| P-34 | 正常 RecommendationSaveRequest 由 local composition adapter 建立 scope；不能用 profile／holding 偽裝 user | capture 僅接受明確 `scope_type=local`、verified clock；candidate 與 run_context scope hash 一致 |
| P-35 | 既有 RecommendationRepository save 後 `load_result()` exact readback | capture、scope envelope、receipt hash/result_id 與 candidate provenance 均可反查；舊 receipt body 不變 |
| P-36 | delivery ACK／retry／save error／CAS conflict／cross-scope／late／未送達 | 同一 prediction identity 只保留一次有效 delivery；未 ACK 不進 delivered denominator，錯誤與 late 狀態隔離 |

### 9.4 真實來源 read／evaluation operational slice

`PersonalizationReadService` 與 `scripts/inspect_personalization_sources.py` 已把上述 projection 從 fixture-only runner 接到既有 Recommendation JSON／metadata、Journal revision／delivery ACK、EvidenceEvent／outcome 與 receipt source。入口要求明確 `scope_id`、`evaluated_as_of`，可選 exact `result_id`／`stock_code`、cutoff、fit artifact 與 bounds；不建立 writer constructor，不 mkdir／DDL／lock，不寫任何正式來源。

Read report 會保存 source fingerprint（bytes、size、mtime、hash），並在任何內容讀取前建立 baseline；Recommendation metadata／JSON、Journal、receipt files 與 Evidence SQLite 主檔及 `-wal`／`-shm` 都納入。Evidence event 與 outcomes 使用同一 read transaction；若來源在讀取期間變動，report 會 `source_consistency_status=invalidated`，不輸出 ready evaluation row 或 evaluator 結果。`source_completeness_status` 另行表示 bounded Journal／Evidence 掃描是否完整：malformed／non-object／read error，以及 exact identity matching rows 超過 bound 會是 `incomplete`，evaluation 與 action preflight 都 fail closed；不會把未知誤標成 `not_recorded`。

bounded inventory 不再靜默切片：report 列出 result／candidate 的 available、selected、excluded、limit、selection order、truncated 與 exclusion reason；exact Evidence result identity 在 `max_events` 前過濾，避免同 symbol 的 sibling rows 擠掉較舊 target。Journal 的 exact `(result_id, stock_code, scope_id)` action／ACK 也在 bound 前過濾，並保留 alias conflict。讀取 service 會 reset in-memory source cache，重用 instance 不會沿用舊 JSONL／Evidence／receipt bytes。

Producer temporal contract 另行區分三種情況：自然 personal entry 由實際 RecommendationService 以 source-latest exact cutoff 產生，caller 的 `--as-of-date` 只作一致性 assertion；顯式舊 cutoff 必須使用 `historical_research_not_as_if_available`，而沒有 mode、cutoff policy、actual decision anchor 或 immutable receipt horizon anchor 一律 fail closed。合法 T-1 只依 aware clock 的 `Asia/Taipei` market date 檢查，不以日期差或 weekday 猜測 session；真實 RecommendationService／receipt integration 同時覆蓋 source-latest T-1 與 explicit historical separation。

目前正式 D 槽 probe 的 `local_research_scope_v1`（2026-09-16）讀到最新 scheduled Recommendation 的 2 個 candidates，但沒有可驗證 personal scope／delivery capture；正式 Journal 為空，故 `population_only=2`、`prediction_available=0`、action／outcome／natural_forward／evaluation rows 皆為 0，並保留 `scope_missing_population_only` 與 `fit_artifact_missing:evaluation_not_run`。這是樣本 pending／missing，不是效果為零；fixture、Paper、user-declared context 與 `source_id` 均不得代替 natural personal evidence。完整 command、hash、WAL coverage 與回歸清單見 [Personalization 唯讀來源 QA](PERSONALIZATION_READONLY_SOURCE_QA_2026_09_16.md)。

本輪已執行的 bounded command：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_personalization_contract.py tests/test_personalization_projection.py tests/test_personalization_calibration.py tests/test_personalization_runner.py tests/test_personalization_save_integration.py tests/test_recommendation_save_coordinator.py tests/test_recommendation_service_calibration_integration.py tests/test_decision_continuity_controller.py tests/test_decision_continuity_write_path.py tests/test_ui_qt_decision_desk_main_integration.py -q -o addopts=
.\.venv\Scripts\python.exe -m pytest tests/test_personalization_read_service.py tests/test_personalization_action_recorder.py tests/test_personalization_generation_cli.py -q -o addopts=
.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=
.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
.\.venv\Scripts\python.exe scripts\inspect_personalization_contract.py --fixture
$env:PYTHONIOENCODING = "utf-8"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe scripts\qa_personalization_mainwindow_save_readback.py `
  --data-root output\qa\personalization_mainwindow_probe_20260916\data `
  --output-root output\qa\personalization_mainwindow_probe_20260916\output `
  --receipt output\qa\personalization_mainwindow_probe_20260916\receipt.json
.\.venv\Scripts\python.exe -m py_compile app_module\application_ports.py app_module\personalization_contract.py app_module\personalization_calibration.py app_module\personalization_projection.py app_module\personalization_save_adapter.py app_module\recommendation_save_coordinator.py app_module\recommendation_service.py app_module\journal_service.py app_module\recommendation_repository.py app_module\dtos\decision_continuity_dtos.py ui_qt\views\recommendation_view.py ui_qt\main.py scripts\inspect_personalization_contract.py scripts\run_personalization_recommendation.py tests\test_personalization_contract.py tests\test_personalization_projection.py tests\test_personalization_calibration.py tests\test_personalization_runner.py tests\test_personalization_save_integration.py tests\test_personalization_generation_cli.py tests\test_recommendation_service_calibration_integration.py tests\test_ui_qt_decision_desk_main_integration.py
.\.venv\Scripts\python.exe -m mypy app_module\application_ports.py app_module\personalization_contract.py app_module\personalization_projection.py app_module\personalization_calibration.py app_module\personalization_save_adapter.py app_module\recommendation_save_coordinator.py app_module\recommendation_service.py app_module\journal_service.py app_module\recommendation_repository.py app_module\dtos\decision_continuity_dtos.py ui_qt\views\recommendation_view.py ui_qt\main.py
.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
.\.venv\Scripts\python.exe -m compileall -q ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
```

結果：本輪 training／lineage focused suite 為 `17 passed`；RecommendationService consumer／real receipt temporal integration 為 `12 passed`；personalization read／projection／generation／contract／calibration suite 為 `62 passed`；action／save integration 為 `20 passed`；UI update／workbench 為 `84 passed`；獨立 real MainWindow process probe 為 `1 passed`，`qa_validate_update_tab.py` 為 `25 passed／0 failed／4 skipped`。producer 相關 11 個 source files 的 `mypy` 為 `Success: no issues found`，changed-file `py_compile` 通過。pytest cache 寫入受環境權限警告不影響結果；fixture runner 與 MainWindow probe 只證明隔離工程鏈，不是正式 personal sample。RecommendationService 已補實際 execution clocks、source-latest exact cutoff、可選 clock assertion、合法 T-1 cutoff、explicit historical tier；consumer／receipt 另核對 verified training label registry／contract／return basis，readback 另覆蓋 Journal exact bound／overflow／malformed incomplete、late delivery 與 immutable retry。正式 D 槽仍只做 bounded read-only probe，未執行 scheduler、full runner、資料重建或 generation writer；本輪 shared gate 仍不證明自然效果或 adoption。

## 10. 具備、待做、自然效果待證

| 分類 | 目前狀態 | 證據／下一步 |
|---|---|---|
| 已具備 | population dataset、PIT labels、purged/OOF calibration、candidate/manifest/artifact lineage、inference provenance、active/champion consumer、natural capture/maturity/authority、exact continuity identity/CAS、research-only user-declared、Decimal Paper ledger | 既有 `recommendation_calibration*`、`recommendation_calibration_evidence.py`、`recommendation_calibration_authority.py`、DecisionContinuity/Journal、EvidenceEvent、Paper tests/QA docs |
| C slice 已完成 | explicit scope/delivery capture contract、三個 clock 分離與 late exclusion、read-only exact assembler、fixed personal shrinkage evaluator、same-row metric/CI receipt、negative cases、deterministic in-memory inspection runner | `app_module/personalization_contract.py`、`app_module/personalization_projection.py`、`app_module/personalization_calibration.py`、`scripts/inspect_personalization_contract.py` 與 bounded tests；不重寫既有 learner、不新增 ledger |
| Shared gate 已完成 | RecommendationService → RecommendationSaveRequest → existing RecommendationRepository 的 caller-owned local capture/save/readback 接線；MainWindow 注入既有 JournalService，UI save 後由 caller 明確追加 technical delivery ACK，read-side 才可視為 delivered；另有受控明示 action recorder／CLI | `app_module/personalization_save_adapter.py`、`recommendation_save_coordinator.py`、`recommendation_repository.py`、`recommendation_service.py`、`journal_service.py`、`ui_qt/main.py`、`ui_qt/views/recommendation_view.py`、`personalization_action_recorder.py`、real MainWindow process probe 與 action/save integration tests；不回寫 immutable result／receipt，不自動寫 human action |
| 真實來源 read slice 已完成 | bounded source read／exact projection／diagnostic 與 optional evaluator composition；source bytes／mtime/hash consistency、SQLite WAL snapshot、result/candidate inventory bounds、cache reset 與 no-write missing-root gate | `app_module/personalization_read_service.py`、`scripts/inspect_personalization_sources.py`、`tests/test_personalization_read_service.py`、[read-only source QA](PERSONALIZATION_READONLY_SOURCE_QA_2026_09_16.md)；正式 `local_research_scope_v1` 仍 `population_only=2`，不宣稱 natural effect |
| Natural effect to prove | 真實 user decision 數量與成熟 natural outcomes、個人 challenger 在 untouched post-cutoff cohort 相對 population 的 calibration/utility/risk 結果、coverage/survivorship、drift、rollback、source/data quality | 必須等 real scope-linked decision/outcome evidence；historical replay、fixture、Paper、user-declared 不能代替 natural proof |
| Manual 最小同步已完成 | 推薦保存／送達紀錄操作、未採納與 `not_recorded` 判讀、缺 scope、不可覆寫與排錯；增加真實來源唯讀 CLI、inventory／fingerprint／pending 判讀，以及 producer source-latest／historical／T-1 時間語意 | `APPLICATION_MANUAL.md` 與 `PERSONALIZATION_READONLY_SOURCE_QA_2026_09_16.md`；clock 由 RecommendationService actual context／receipt 提供，CLI 只作 optional assertion |
| 不在本輪 | L official taxonomy、K cross-page integration、global active pointer、formal order/portfolio/broker、個人化 fit artifact 的正式 producer/persistence | RecommendationView/MainWindow 的本輪 save/ACK composition 已接線；本輪只同步 SSOT/Roadmap 的 C 段落；完整跨頁 K、正式 authority 與 real-source fit artifact 另立 dependency |

### 10.1 C 線 completion audit（2026-09-17 working tree）

下表只描述 C-owned bounded engineering 與正式 D 槽目前的證據狀態；fixture／隔離
MainWindow probe 的通過不計為正式 personal sample，表內測試數字彼此可能有套件重疊，不能相加宣稱效果。

| 項目 | 工程接線狀態 | 正式個人化仍缺／責任歸屬 |
|---|---|---|
| training／lineage／consumer | training provenance、label registry／contract／return basis custody、inference provenance、immutable projection receipt 與 fail-closed consumer 已核對；training／lineage `17 passed`、consumer／service integration `12 passed` | 仍是 population／shadow calibration；不把 active candidate 或 receipt 當 personal fit 或 natural effect，需後續 scoped evidence gate。 |
| service／save／UI prediction capture | RecommendationService 實際 producer clocks → `RecommendationSaveRequest`／existing Repository create-only save/readback → MainWindow／Journal technical ACK 已接線；正常 ACK 不誤報 late，遲交相對 human anchor 會排除 natural credit；action/save `20 passed`、real MainWindow probe `1 passed` | D 槽目前沒有可驗證的 scope-linked capture／delivery ACK。要取得真實 production row，必須由合法 producer／caller 在 intended root 執行新結果並保存 exact readback；不得拿 probe fixture 冒充。 |
| read／projection／CLI／evaluator | `PersonalizationReadService`、exact Recommendation／Journal／Evidence join、三個 clock、cohort／exclusion／pending／mature denominators、late delivery diagnostics、`record_personalization_action.py` preflight／append／readback 與 fixed Decimal/bp evaluator 已接線；相關 suite `62 passed` | D 槽目前 `prediction_available=0`、action／outcome／evaluation rows 為 `0`；這是 source evidence 缺少，不是 evaluator 宣稱零效果。 |
| 真實 scope | local research scope 只能在 capture 產生時由 producer context／receipt 綁定，不能由 profile、holding、portfolio 或 source id 猜出；normal local path 可用，但 `local` 不代表人類身份 | 真實 user scope／使用者身份不會由工程自動生成。需由真實使用流程明示或接受 local research scope，並保留 scope envelope；本任務不替使用者創建。 |
| technical delivery | UI save 與 CLI generation 後的 technical ACK、CAS／retry／readback 已有 bounded path；ACK 只是交付，不是採納 | D 槽沒有真實 ACK。需由實際 producer delivery 產生 persisted／delivered receipt；不能把 saved result 或 producer inference 單獨視為 delivered。 |
| human action | `PersonalizationDecisionRecorder`／CLI 只在 delivered projection、exact prediction identity 與 label／return／cost／horizon contract 通過後，追加既有 Journal revision；不自動由 UI save 產生 action，不 retrofit legacy action | D 槽沒有 personal human action。必須由真實使用者明示 action／actor／action clock；工程不代填 accepted、skipped、held、buy 或 sell。 |
| natural outcome／maturity | reader／evaluator 可 exact join EvidenceEvent／Outcome、辨識 pending／matured missing／invalid／duplicate，並分離 natural／paper／declared／replay tier | D 槽沒有 scope-linked natural outcome；需等待同一 prediction 的官方自然價格／outcome producer 在 horizon 後提供可驗證 maturity／availability。Paper、fixture、historical replay、user-declared 不可替代。 |
| personal fit artifact | evaluator 可驗證 supplied frozen fit artifact 的 row／prediction／statistical／cohort／overlay hash；fixture runner 可在記憶體產生 artifact | 尚無 real-source personal fit artifact 的 producer／durable persistence／operational runner，且缺少足量 eligible／mature rows。這是工程 follow-up，資料樣本仍須由真實 scope／action／natural outcome 提供。 |

因此目前結論是：C 的 capture／read／action／evaluation bounded wiring 已可操作，但正式
個人化證據鏈仍停在 `population_only`／missing／pending 邊界；不能宣稱 V6 完成、自然效果、
adoption、promotion 或收益改善。

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
| `app_module/personalization_contract.py` | 修改 | typed scope/capture/action/evaluation row contract；增加 delivery status/PIT validation | 只回滾本檔 C-owned diff；不還原其他 agent dirty files | 無資料／DB／scheduler 寫入 |
| `app_module/personalization_calibration.py` | 修改 | fixed bin-wise Decimal/bp fit/evaluate、purge/embargo、maturity/status/CI | 只回滾本檔 C-owned diff；不還原其他 agent dirty files | 無資料／DB／scheduler 寫入 |
| `app_module/personalization_projection.py` | 新增 | read-only exact projection 與 capture verifier | 移除本新增檔前須確認未被引用；不使用 destructive command | 不建立 repository、ledger 或 pointer |
| `scripts/inspect_personalization_contract.py` | 新增 | bounded in-memory fixture runner；output create-only | 移除本新增檔前須確認未被引用；不清理正式輸出 | 不讀正式 DATA_ROOT／DB／scheduler |
| `scripts/qa_personalization_mainwindow_save_readback.py` | 新增 | 隔離根目錄下的 real MainWindow process save／ACK／projection／close receipt probe | 移除本新增檔前須確認未被引用；不清理保留的 QA receipt | 僅 bounded fixture 與 research-only output；不碰正式資料 |
| `tests/test_personalization_contract.py`、`tests/test_personalization_projection.py`、`tests/test_personalization_calibration.py`、`tests/test_personalization_runner.py`、`tests/test_personalization_save_integration.py`、`tests/test_ui_qt_decision_desk_main_integration.py` | 新增／修改 | bounded contract/projection/calibration/runner/save/readback/ACK/CAS/race/orphan、host integration／Journal injection 與獨立 real MainWindow process receipt probe | 移除本新增測試前須確認未被引用；不碰既有 tests | 僅測試／fixture；worker 關閉狀態有 probe |
| `app_module/recommendation_save_coordinator.py`、`app_module/recommendation_repository.py`、`app_module/recommendation_service.py` | 修改 | local scope composition、existing result create-only/save/readback、shared SQLite write lock 與 personal capture immutable overwrite guard、正常 execution clocks | 只回滾本檔 C-owned diff；不還原其他 agent dirty files | 既有 recommendation save 相容；personal capture 不可降級或被競態覆寫 |
| `app_module/journal_service.py`、`app_module/dtos/decision_continuity_dtos.py` | 修改 | 沿用既有 JSONL revision chain 的 technical delivery ACK、history-token CAS 與 readback；human action semantics 不變 | 只回滾本檔 C-owned diff；不還原其他 agent dirty files | 不新增 personal ledger；不寫 human action／order |
| `ui_qt/main.py`、`ui_qt/views/recommendation_view.py` | 修改 | MainWindow 傳入既有 JournalService；UI save 成功後明確 ACK，失敗顯示簡短 fail-closed 訊息 | 只回滾本檔 C-owned diff；不還原其他 agent dirty files | save 成功但 ACK 失敗時不隱藏結果、不升級 delivered |
| `docs/06_qa/V6_PERSONALIZATION_CONTRACT_PLAN_2026_09_15.md` | 修改 | 同步實際 C slice、路徑、QA 結果與 shared gate | 只回滾本檔 C-owned diff；不還原其他 agent dirty files | 僅文件變更；無資料、DB 或 scheduler 變更 |
| `docs/07_guides/APPLICATION_MANUAL.md` | 修改 | 補推薦保存／送達紀錄、未採納／`not_recorded`、缺 scope、不可覆寫與排錯操作說明，以及 source-latest／historical／T-1 時間語意 | 只回滾本段 C-owned diff；不還原其他 agent dirty files | 僅使用手冊變更；不以 CLI clock 取代 producer actual clock |
| `docs/06_qa/PERSONALIZATION_READONLY_SOURCE_QA_2026_09_16.md` | 新增 | 真實來源 read／evaluation operational gate、WAL／race／inventory regression 與 D 槽唯讀 probe | 移除本新增 QA 文件前須確認未被引用；不清理正式資料 | 僅文件；未寫正式來源 |

本輪未執行任何 destructive rollback command、未清理 `qa-cache-*`、未 reset/checkout 其他檔案、未 stage/commit；Manual 已同步保存／送達、source-latest／historical／T-1 時間語意與上述排錯邊界。create-only metadata failure 若留下 orphan，Repository 保留原檔並允許內容完全相同的 create-only retry，legacy save 對 unknown／orphan／personal data path 均拒絕覆寫。後續若要修改 authority、pointer、正式交易或 scheduler，必須先另開明確 change scope、backup／read-only audit、bounded QA 與專屬 rollback plan。

## 12. 最終判定

截至本次 C handoff，最小 `personalization-decision-evidence.v1` contract、capture／read／ACK／明示 action、offline evaluator、negative cases、receipt 與 population fallback 已具備可驗收的 bounded wiring；下一步不是再造 user ledger，而是補 real-source personal fit artifact 的 producer／persistence，並由合法使用流程累積 scope-linked delivery、human decision 與 natural outcome。

只有在上述真實 evidence 足夠、PIT/provenance/cost/label contract 可重算、untouched post-cutoff holdout 與 uncertainty 結果支持時，才可另行審查個人化 adoption；在此之前正式 D 槽維持 read-only／population-only，仍須保留 fail-closed rollback、no return guarantee、no auto rebalance、no broker order 與 natural/research tier separation。
