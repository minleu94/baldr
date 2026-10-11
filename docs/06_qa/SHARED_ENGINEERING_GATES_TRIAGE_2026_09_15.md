# Shared Engineering Gates Triage（2026-09-15）

> 性質：有界 triage。初始診斷未重跑全域 pytest；後續依 owner 授權修補兩個 calendar fixture 測試，並完成 accepted inventory path 補登；未修改 production code、GUI、排程、Manual／SSOT，未 stage／commit。
>
> 基準：目前 HEAD 031e11ab（feat: complete continuity review workbench R1）。主要結果與節點來源為 docs/06_qa/CONTINUITY_REVIEW_WORKBENCH_R1_QA_2026_09_15.md。
>
> **歷史快照：** 本文中的 inventory 數字與「目前 HEAD」只描述 2026-09-15 triage。較新的唯讀 inventory 核對見 [文件治理狀態矩陣](../00_core/DOCUMENTATION_STATUS_MATRIX_20261009.md)；不得把本文 836／831／5 的數字當作目前清冊。

## 結論摘要

| Gate | 判定 | 建議 owner／下一步 |
|---|---|---|
| ml_shadow_boundary_guard20 | 20 項是混合結果：15 項為唯讀 frozen inference／evidence 候選但尚未進入目前的窄 allowlist；1 項 ML → app 反向依賴；4 項集中在實際呼叫 fit 的 learning runner。 | Recommendation calibration／ML lane 先重畫邊界，再決定是否以明確、逐檔的 contract 例外註冊；不可用全域放寬取代架構修正。 |
| 兩個 calendar failure | 修補前都是 cache freshness／replay clock 導致的 evidence 不可用；修補後兩個正向節點通過，且未改 production expiry。 | 保留 deterministic clock、hash-bound cache 與過期／tamper 的 fail-closed negative case。 |
| inventory drift | 初始 audit 為 24 個 missing；registry consolidation 後為 831 個 registry entries、5 個 remaining missing，且 documented count drift 已歸零。 | 21 個 committed baseline、BankTaiwan cost test 與 support 已補登；保留 2 個 foreign、1 個 L lane 及 2 個 C lane untracked tests 為 residual。 |

## 範圍與觀測方法

- R1 QA 文件記載的歷史全域 session 為 5444 passed, 5 skipped, 12 failed，耗時 1584.29s。該結果是後續 targeted／dirty 變更前的 snapshot，本輪依指示不重跑全域 pytest。
- 以既有 scripts/check_ml_shadow_boundary.py 做唯讀 guard diagnostic：掃描 506 個檔案，回報 20 項 violation；沒有改寫報告或 guard state。
- 初始 inventory audit 的唯讀比較為測試區 833 個 Python 檔案、registry 809 筆、24 個 missing；文件化 category／total 有 4 個 count drift。
- registry consolidation 後再次做唯讀 audit：raw 測試區 836 個 Python 檔案、registry 831 筆、5 個 missing、0 個 stale，且文件化 category／registry-total count drift 已為 0。
- shadow_only=true、formal_order_allowed=false 等輸出安全欄位是必要條件，不是依賴方向或訓練邊界自動豁免的證據。
- 受控 fixture 修補只改 tests/test_ml_forward_scheduled_wrapper.py 與 tests/test_paper_daily_execution_producer.py：兩者都使用 tmp path 的真實 builder／writer、hash-bound cache 與 deterministic observed clock；production expiry、network guard 與 ML boundary 均未改動。

## 1. ml_shadow_boundary_guard20：20 項逐群分類

目前 guard 的 allowlist 是逐檔、逐 import 的 allocation／release adapter 例外（ml_module/shadow_boundary_guard.py:19-51），不是「所有 shadow code 均可被 production root 引用」。因此下列「候選」只代表已經有唯讀 frozen contract 的跡象，不代表現在應直接修改 allowlist。

| 違規群 | 數量 | 證據 | 分類 |
|---|---:|---|---|
| ml_module/recommendation_calibration_evidence.py → app_module.recommendation_calibration_consumer | 1 | ml_module/recommendation_calibration_evidence.py:708 動態 import consumer，約 :756 透過 consumer 做 prediction。這是 ML package 反向依賴 app package。 | 真正的 ML → production boundary violation。不是 frozen neutral contract。 |
| app_module/daily_recommendation_learning_runner.py → 4 個 ML modules | 4 | app_module/daily_recommendation_learning_runner.py:19-35 import manifest、promotion authority、training service、cost scenario；約 :355 實際呼叫 training_service.fit(...)。 | 真正的 training boundary violation。雖然 runner 的輸出被隔離、標成 shadow-only，fit 仍在 production-root namespace 內；不能以安全旗標直接豁免。 |
| app_module/recommendation_calibration_consumer.py → 7 個 ML modules | 7 | app_module/recommendation_calibration_consumer.py:23-41 使用 feature registry、artifact loader／manifest、label／hash DTO、cost scenario、policy 與 probability transform；RecommendationCalibrationConsumer（約 :181）是 fail-closed inference adapter，reload（約 :209）只讀 pointer／artifact。未發現 fit 或 formal writer。 | 已接受形狀的 frozen inference／read-only contract 候選，但目前未註冊。需先由 owner 將 contract 邊界固定，再做逐檔 allowlist。 |
| app_module/recommendation_learning_evidence_projection_service.py → 5 個 ML modules | 5 | app_module/recommendation_learning_evidence_projection_service.py:27-45 使用 evidence／policy／cost／natural-outcome verifier；模組與 RecommendationLearningEvidenceProjectionService（約 :315）是唯讀 typed projection，未發現 fit 或 writer。 | Read-only evidence／projection contract 候選，但目前未註冊。其依賴的 recommendation_calibration_evidence 仍含上述反向 app import，故不能未審計就放行。 |
| app_module/recommendation_service.py → 3 個 ML modules | 3 | app_module/recommendation_service.py:60-68 接入 calibration consumer、baseline／transform；約 :150-183 描述並執行唯讀 recommendation projection，缺少 pointer／artifact／feature 時保留 rule-only score；未發現 training call。 | Read-only inference／feature contract 候選，但目前未註冊。應針對 adapter boundary 做窄註冊，不應豁免整個 recommendation_service。 |

### 目前的修正判斷

1. 先處理兩個硬邊界：移除 ML → app 的依賴；把 training orchestrator 移到明確的 ML／shadow 邊界，或建立經審核的中性 orchestration contract。不得因目前輸出 shadow_only 就把 training runner 加進通用 production allowlist。
2. 15 項唯讀候選需由 recommendation calibration owner 提供可驗證的 contract 證據後，才可逐檔註冊；必要條件包括：只讀 frozen pointer／manifest／feature hash、無 fit、無 formal DB／order writer、production／promotion flags 不得為 true。
3. 每個候選都應保留一組 positive check（valid hash-bound pointer／artifact 能產生 inference 或 evidence projection）與 negative check（pointer 過期、hash 不符、訓練入口或反向 production import 必須 fail closed）。
4. 本輪不修改 ml_module/shadow_boundary_guard.py，也不把 20 項視為可用「補登註冊」一次消除的單一問題。

## 2. 兩個 calendar failure

### 2.1 ml_forward_scheduled_wrapper

節點：tests/test_ml_forward_scheduled_wrapper.py::test_forward_calendar_uses_verified_cache_without_network。

- 修補前測試固定讀取 output/paper_execution_eod_replay/calendar_cache/twse_holiday_schedule_2026_20260907_capture1.json（約 tests/test_ml_forward_scheduled_wrapper.py:834-843）；該舊 pointer 現已由 tmp path fixture 取代。
- 該檔 schema 為 official-trading-calendar-cache.v1，capture 約為 2026-09-07T19:20:27Z，expiry 約為 2026-09-14T19:20:27Z；目前已有較新的 twse_holiday_schedule_2026_20260914T231502118687Z_e02efc5483b2.json。
- data_module/official_trading_calendar_cache.py:1186-1187 接受 v1 schema，但約 :1320-1332 以實際 datetime.now(timezone.utc) 檢查 expiry。過期後，data_module/official_trading_calendar.py:106-115 才會進入 network fetch；offline probe 最終會回傳 lacks_official_evidence（約 :430-446）。

判定：舊 fixture／cache pointer 過期，非 schema mismatch，亦沒有足夠證據指向 reader regression。測試期待 cache-open，但它指向的 cache 已不再 fresh，因此回傳 lacks_verified_official_evidence 是目前 fail-closed 行為的合理結果。

已修補：positive case 改用 tmp path 的 build_twse_calendar_cache／write_twse_calendar_cache，並以 test-only patched observed clock 驗證 fresh hash-bound cache；network 仍由 assertion guard。expired／tampered negative case 另以官方 cache tests 驗證，沒有延長 production freshness。

### 2.2 paper_daily_execution_producer

節點：tests/test_paper_daily_execution_producer.py::test_real_paper_consumer_reads_hash_bound_calendar_cache。

- 測試以歷史 EOD_REPLAY_NOW = 2026-09-07 15:00（Taipei）建立 cache（約 tests/test_paper_daily_execution_producer.py:1344-1359），因此 cache 的七日 expiry 也是相對該 replay clock 產生。
- production loader 仍以實際現在時間驗證 freshness；在目前日期 2026-09-15 執行時，該 fixture 已過期。
- data_module/paper_daily_execution_producer.py:3634-3642 先以 default online probe 取得 calendar evidence；約 :3665-3670 才嘗試 offline probe，過期 cache 兩者都不能證明 trading day，最後約 :3680-3685 回傳 official_calendar_not_proven:<reason>。
- 測試 patch 的 network guard（約 :1361-1365）因此捕捉到 valid cache must be consumed before network。這表示 fixture 已不再 valid，不表示 reader 沒有讀 v1 cache；同一 production builder 建出的 schema／hash 形狀是正確的。

判定：歷史 replay fixture 的 freshness clock drift，非 schema mismatch，亦非目前證據支持的 production reader bug。run_paper_execution_daily 使用 default online probe 的行為本身不能在過期 cache 後保證不觸發 network。

已修補：fixture 仍由既有 production builder 產生，但 loader 的 observed clock 固定為 EOD replay instant，讓 capture／expiry 與 replay 同一時間軸；network assertion 維持，positive case 驗證 machine_verified 與 hash-bound source mode。expired／tampered cache 維持 blocked，且沒有用 weekday／local inference 繞過 official evidence。

### Calendar 修補驗證結果

~~~text
tests/test_ml_forward_scheduled_wrapper.py::test_forward_calendar_uses_verified_cache_without_network     passed
tests/test_paper_daily_execution_producer.py::test_real_paper_consumer_reads_hash_bound_calendar_cache   passed
tests/test_official_trading_calendar_cache.py::test_cache_rejects_rehashed_payload_with_changed_raw_response passed
tests/test_official_trading_calendar_cache.py::test_expired_cache_keeps_calendar_unknown_when_network_is_unavailable passed
tests/test_paper_daily_execution_producer.py::test_unknown_calendar_keeps_next_session_blocked          passed
tests/test_paper_daily_execution_producer.py::test_calendar_falls_back_to_local_market_indices_evidence passed
~~~

六個 targeted nodes 均通過；pytest 只留下既有 .pytest_cache permission warning。

## 3. Inventory drift 24：註冊責任與 dirty 邊界

初始唯讀 inventory audit 結果為 FILES=833、REGISTRY=809、MISSING=24。registry consolidation 後的最新 recheck 為 raw FILES=836、REGISTRY=831、MISSING=5、STALE=0、count drift=0、collection_errors=0。最新 remaining missing 僅是兩個 foreign untracked tests、1 個 L lane test 與 2 個 C lane tests，未以註冊掩蓋。

~~~text
general-unit-keep-in-pytest:           149
governance-doc-tooling:                 152
service-oracle-data-market:             123
service-oracle-portfolio-decision-runtime: 130
service-oracle-recommendation:           33
service-oracle-research-backtest:        74
slow-e2e-or-environment:                  4
ui-healthcheck-candidate-bridge:         37
ui-healthcheck-direct-bridge:            12
write-risk-dry-run-required:             71
registry total:                         831
~~~

### 3.1 21 個乾淨、已有 commit 且已補登的 baseline 路徑

這些路徑已有 commit origin，且已依下列預分類補進 registry；它們不再與當前 dirty／untracked work 混為一談：

~~~text
tests/pit_test_support.py
tests/test_banktaiwan_recommendation_learning_operational.py
tests/test_daily_investment_journey.py
tests/test_decision_continuity_controller.py
tests/test_decision_continuity_write_path.py
tests/test_decision_outcome_journey.py
tests/test_pit_industry_callers.py
tests/test_pit_sector_membership_reader.py
tests/test_position_health_transition_read_service.py
tests/test_qa_research_journey_subprocess.py
tests/test_recommendation_learning_evidence_projection.py
tests/test_research_fallback_packet.py
tests/test_ui_qt_daily_journey.py
tests/test_ui_qt_decision_continuity_controls.py
tests/test_ui_qt_decision_outcome_journey.py
tests/test_ui_qt_journal_scope_increment_b.py
tests/test_ui_qt_research_fallback.py
tests/test_ui_qt_user_declared_holding_research.py
tests/test_ui_qt_watchlist_storage_wiring_increment_b.py
tests/test_user_declared_holding_research.py
tests/test_watchlist_storage_wiring_increment_b.py
~~~

tests/pit_test_support.py 是 support helper，不應當作普通 pytest test 直接塞入一般 category；補登前需同步 qa/full_app_healthcheck/test_inventory.py 的 PYTEST_SUPPORT_FILES。其餘 20 個才是一般測試路徑，分類仍應由對應 lane owner 確認。

#### 交接用精確分類（本輪已寫入 registry）

| 預分類 | 路徑 |
|---|---|
| support（同步 PYTEST_SUPPORT_FILES） | tests/pit_test_support.py |
| governance-doc-tooling | tests/test_banktaiwan_recommendation_learning_operational.py；tests/test_qa_research_journey_subprocess.py |
| service-oracle-data-market | tests/test_pit_industry_callers.py；tests/test_pit_sector_membership_reader.py |
| service-oracle-recommendation | tests/test_recommendation_learning_evidence_projection.py |
| service-oracle-portfolio-decision-runtime | tests/test_daily_investment_journey.py；tests/test_decision_continuity_controller.py；tests/test_decision_continuity_write_path.py；tests/test_decision_outcome_journey.py；tests/test_position_health_transition_read_service.py；tests/test_research_fallback_packet.py；tests/test_user_declared_holding_research.py；tests/test_watchlist_storage_wiring_increment_b.py |
| ui-healthcheck-candidate-bridge | tests/test_ui_qt_daily_journey.py；tests/test_ui_qt_decision_continuity_controls.py；tests/test_ui_qt_decision_outcome_journey.py；tests/test_ui_qt_journal_scope_increment_b.py；tests/test_ui_qt_research_fallback.py；tests/test_ui_qt_user_declared_holding_research.py；tests/test_ui_qt_watchlist_storage_wiring_increment_b.py |

以上分類已實際寫入 registry：scheduled／process contract 歸 governance，PIT 歸 data-market，daily／continuity／holding／watchlist read model 歸 portfolio-decision-runtime，新 UI 流程維持 candidate bridge。BankTaiwan cost test 另依 recommendation／cost responsibility 補登於 service-oracle-recommendation。

### 3.2 已補登：BankTaiwan cost lane

~~~text
tests/test_daily_banktaiwan_learning_cost.py
~~~

該路徑已由 086ba60c commit 完成驗收，現分類為 service-oracle-recommendation；其成本 scenario／recommendation calibration 責任與 daily recommendation learning loop 同 lane。原先「committed but dirty」是初始 observation，現已解除，不再列為 residual。

### 3.3 外部／L／C lane 未追蹤：保留為 residual，不註冊

~~~text
tests/test_db_lock_wait.py
tests/test_pit_taxonomy_daily_source.py
tests/test_recommendation_calibration_learning_runner_lineage.py
tests/test_recommendation_training_lineage.py
tests/test_review_warning_classification.py
~~~

- test_db_lock_wait.py 與目前 dirty 的 data_module/db_manager.py 同一 foreign workflow，屬 DB lock／busy timeout 進行中 lane。
- test_review_warning_classification.py 與目前 dirty 的 app_module/evidence_pipeline_runner.py、scripts/scheduled/run_scheduled_evidence_pipeline_dry_run.py 同一 foreign workflow，屬 warning classification 進行中 lane。
- `tests/test_pit_taxonomy_daily_source.py` 是 L lane 的 PIT source test；兩個 recommendation lineage tests 屬 C lane。目前三者均尚無本輪 accepted commit／owner integration 證據。

五者均不刪除、不隱藏、不註冊；audit 應維持明列 5 個 missing，不能宣稱全庫 zero-missing。

### Inventory 後續 gate

1. 21 個 clean baseline、pit_test_support support 與 BankTaiwan cost test 已完成集中補登；後續只需維護 owner／scope。
2. 等五個 residual lanes 完成或明確撤回後，才由各 owner（foreign／L／C）分類／補登；不要為了讓 audit green 先行註冊。
3. current counts 已由實際 registry 重算並同步 QA summary；若 residual 改變 filesystem，先重新 audit，再更新數字。

## 建議派工順序

1. Recommendation calibration／ML owner：先拆除反向 ML → app edge，重新安置 training runner，再逐檔審核 15 個唯讀 contract 候選。
2. Forward/calendar 與 Paper/calendar owners：審核已完成的 deterministic observed clock／hash-bound fixture 修補，保留 official evidence 的 expiry／tamper fail-closed checks。
3. Inventory integrator：保留五個 residual 的明列狀態；其 owner 收斂後再重算 registry／support／文件 counts。

本 triage 不建議目前直接修改 guard allowlist、延長 cache freshness、關閉 network guard，或登錄兩個未追蹤測試。
