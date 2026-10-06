# Baldr 下一波精確 ownership 派工收據（2026-10-06）

本文件是既有 Astra／Sol 審核與唯一原 plan 的派工補件，不是另一條 roadmap。固定基準 **5d9ddf9d611bd6e117d75d0b4fdbf8751ee2e5a0**；開始審查時 tracked clean。下列是待父層鎖定的 proposal，本文未派新 thread，也未修改 production、tests、inventory registry。原核准 union 收據沿用，不全面重測。

## 可立即平行

父層已派 B01-H6/H7；本次另可立即派 **P1 Paper ledger custody** 與 **I20 inventory 首 20 檔**。P2 在 P1 API／commit 定版後執行；可以由同一 Paper Sol 接續，初期最多一位 LunaMax。中央主線可持有文件同步、P1/P2 dependency 整合與驗收收據；source_id 三檔仍等待直接人類批准，不做間接 workaround。

### P1：兩個 Paper ledger 的 selected route／每 I/O custody

**排他 ownership（兩個 production＋新增 test／QA）**
- app_module/paper_trade_ledger.py
- app_module/paper_equal_weight_benchmark_ledger.py
- tests/test_baldr_personal_paper_ledgers.py（新增）
- docs/06_qa/BALDR_PERSONAL_PAPER_LEDGERS_20261006.md（新增）

**實際入口**：PaperTradeLedgerRepository.__init__(db_path)、append/append_many/append_batch、list/list_transitions、schema_readback/_ensure_schema；EqualWeightBenchmarkLedger.__init__(db_path)、append/list。目前兩 ctor 都先 mkdir／SQLite schema 寫入，必須在這些副作用前分流。

**API 凍結要求**：保留原 positional db_path；新增 keyword-only route: PersonalStoreRoute | None、personal_paths: PersonalDataPaths | None。routed portfolio_id 必須 exact route.identity.key；benchmark_id 是另一個已知 caller 身份，不能用 portfolio_id 冒充；routed ledger 對 append/list 的身份都 exact 核驗。由 caller 明示身份的新 keyword 名稱／signature，在落檔前回中央及 P2。PERSONAL 缺 paths 拒絕；LEGACY_READ_ONLY writer 在 mkdir/schema/connect 前拒絕，reader 必須 mode=ro/query_only、不建庫。無 route 的舊 API 保持既有相容；明示配置的 CLI 必須由 P2 在接觸該 API 前 fail-closed，不讓 configured caller 偷走舊路。

重用唯讀 PersonalPaperStorePaths.from_route 與 PersonalStoreCustody：cost_ledger_db／benchmark_db exact path，main/journal/wal/shm 每次 connect 前驗；canonical 身份不變，只 I/O 用既有 extended-length renderer。驗所有 append_batch 原交易與 transition 原子性，不能拆 transaction。純 fee、現金、部位、Decimal／bp、schema、query、去重與成本公式不改。

**依賴**：基準既有 route＋selection.paths／custody API，不依賴 source_id 或 B01；P2 依賴此包穩定 API。
**驗收**：原 ledger 回歸＋新 routed synthetic 保存→新程序同 root/account/readback；未配置舊 caller 相容；missing paths、wrong domain/account/db、legacy-readonly writer、post-constructor hardlink/junction、sidecar alias、lexical alias、deep Unicode/emoji >260 拒絕或正向；每項負例先核沒有 mkdir/schema/新檔。保存市場及 legacy sentinel bytes/hash/mtime 不變。changed mypy/compile/quant，pytest raw＋JUnit 在固定 local commit 落地。
**禁止**：改 shared routes/paths/config/DTO、Snapshot repository、UI/main、Manual、正式 DB／資料搬移／Task／ACL／交易／模型；不能整個 private root 或任意 staging path 放行。

**worker prompt**：先讀 AGENTS 及原 plan，以固定基準建立專屬 worktree，只改以上四檔。先回 exact constructor／identity API，保留兩 ledger 原公式與 atomic transaction。做 isolated synthetic 新舊 API／custody 負例與 fresh-process readback；每 I/O 驗 exact path、sidecars、route mode／identity，補 >260。只交 owned local commit、blobs、raw/JUnit/hash、Manual 建議與限制，不 dev cherry-pick/push；共享 API 若需擴鎖先報精確檔與理由，不自改。

### P2：benchmark builder＋daily／benchmark CLI 的完整 selected routing

**排他 ownership（三個 production＋新增 test／QA）**
- app_module/paper_equal_weight_benchmark_builder.py
- scripts/run_paper_portfolio_daily.py
- scripts/build_paper_equal_weight_benchmark.py
- tests/test_baldr_personal_paper_producers.py（新增）
- docs/06_qa/BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md（新增）

**四檔舊提案校正**：app_module/paper_portfolio_daily_runner.py 只有 PaperPortfolioDailyRunner.run 的純 Decimal 計算，沒有 I/O，保持唯讀。實際 benchmark 檔案出版是 Builder.write_new_ledger 的 mkdir→mkstemp→ledger→rename，不在純 daily runner。完整涵蓋兩個 CLI，最低是 P1 兩檔＋本包三檔，共五個 production，不能把第五檔隱藏成已接線。

**實際入口／API**：
- Builder.__init__(portfolio_id,benchmark_id,today_provider) 增 route／personal_paths keyword；preview/build_entries/commit/write_new_ledger 的原公開參數保持相容，commit confirm=False 原限制不變。state/baseline/benchmark 是 PersonalPaperStorePaths exact selected；market_db 是獨立只讀市場 caller，不能從 private root 推導。
- daily run(*,baseline_path,state_db,market_db,output_root,decision_at,calendar=None,now=None,ledger_db=None) 增 route／personal_paths keyword；先核 selected baseline/state/cost/status＋account，再有任何 status/mkdir/讀檔/connect。既有 Snapshot repository 的 route＋paths API 直接重用，該檔唯讀。
- 兩 CLI 用既有 config／selector 解析個人 mode/root，先拒 root-only/mode-only/blank/unknown 配置與 override mismatch；selected 模式忽略 legacy PAPER_EXECUTION_LEDGER_DB env，明示 path mismatch 拒絕。市場設定維持原 market config，不能重定向成 personal DB。selection 失敗只輸出錯誤，daily main except 不准掉回 legacy latest_status.json。
- 原 read-only helpers／baseline hash／cost projection 都每 I/O 驗 custody、用 renderer；不要先 resolve 掩蓋 alias。原 future decision、official calendar unknown、08:30 cutoff、query/schema/formula／200GiB 與既有 role reserve 政策保留，不另造 default 容量。

**staging 需明示**：既有 PersonalStoreCustody allowlist 不含任意 .tmp。daily 的 .latest_status.json.PID.tmp 與 builder mkstemp 的 .stem.*.tmp.sqlite 必須綁本次 generated exact temporary、selected target／parent、single-link／no-follow／sidecars，每次 I/O 檢查；不得擴整個 parent/root wildcard。Builder 不能把 arbitrary public db_path 轉成已核 staging。若需要擴 shared helper，由 worker 先交 exact API／檔案、等待父層鎖 ownership；不在本包偷偷改 PersonalPaperStorePaths。

**依賴**：P1 穩定 commit／signature；固定基準已有 B09 readonly consumers／Snapshot、selection/custody。無 source_id 依賴。
**驗收**：synthetic private baseline／原 fill ledger＋原 benchmark builder＋daily state/status 保存→B09 readiness/weekly 新程序同 account/root exact readback；市場 bytes/hash/mtime 與 legacy sentinel 不變。preview 不写，benchmark confirm false 拒絕；unknown calendar／future decision 不提高資格。CLI 配置錯誤／env/mismatch 不得 fallback 或 error-status 寫 legacy；post-preview/post-constructor swap、hardlink/junction/temp alias、publication race、deep >260、新程序 reader 均驗。只跑 affected Paper／CLI tests、targeted mypy/compile/quant；raw/JUnit 對 immutable owned commit，整合後必要的接線 subset，不重跑已核准四用途與 mandatory 全集。
**禁止**：改 pure daily runner、金融公式、shared storage/config/routes/DTO/main/UI、正式 Task／真資料／migration／ACL／交易；正式 writer 啟用仍未授權。此包只證明 synthetic selected chain。

**worker prompt**：採父層批准的 P1 owned dependency 到自己的 lane，鎖以上五檔，先回 builder/run 新 keyword API 和 exact temporary custody 設計。完整接兩 CLI，核 daily error handler 不落 legacy；沿原 producer／ledger／Snapshot 真實 synthetic 保存，不 stub 掉正向 writer。保原 confirm/calendar/cutoff/schema/hash/capacity／Decimal，完成新程序 consumers readback及 alias/override/errorpath/deep-path 負例，交 commit/blobs/raw/JUnit/Manual 素材，不改唯讀 shared 檔、不啟用 Task。

## I20：176 inventory 缺件的有限首 20 檔

**排他 ownership（只四個治理檔）**
- qa/full_app_healthcheck/test_inventory.py
- docs/06_qa/FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md
- docs/06_qa/FULL_APP_HEALTHCHECK_COVERAGE_MAPPING_2026_06_24.md
- docs/06_qa/TEST_INVENTORY_HEALTHCHECK_CLASSIFICATION_2026_06_23.md

**精確 subset**：見下表。20 個檔案在固定 HEAD 存在且全在 missing_inventory_paths；source SHA／AST test count／imports／I/O 索引在同名 output/qa manifest。這些是 scope 證據，AST 的 append/connect 命中不自動決定 write-risk，也不代表已跑 pytest。worker 必須逐檔讀 fixtures／assert／執行入口，給分類理由與副作用位置；尤其 subprocess/producer 是否只 synthetic、GUI 是否真橋接，要照既有分類規則。

| # | exact readonly test path |
|---|---|
| 1 | tests/test_daily_market_cohort_main_bridge.py |
| 2 | tests/test_daily_market_cohort_projection.py |
| 3 | tests/test_daily_market_feature_snapshot.py |
| 4 | tests/test_daily_market_method_contract.py |
| 5 | tests/test_daily_market_research_bookmark.py |
| 6 | tests/test_daily_market_research_capabilities.py |
| 7 | tests/test_daily_market_research_screener.py |
| 8 | tests/test_daily_market_snapshot_consumer.py |
| 9 | tests/test_daily_market_snapshot_producer.py |
| 10 | tests/test_daily_market_snapshot_repository.py |
| 11 | tests/test_rule_research_benchmark_adapter.py |
| 12 | tests/test_rule_research_benchmark_integration.py |
| 13 | tests/test_rule_research_daily_owner.py |
| 14 | tests/test_rule_research_fair_boundary.py |
| 15 | tests/test_rule_research_fair_comparison.py |
| 16 | tests/test_rule_research_fair_comparison_cli.py |
| 17 | tests/test_rule_research_forward_isolated.py |
| 18 | tests/test_rule_research_forward_outcome.py |
| 19 | tests/test_rule_research_forward_outcome_reader.py |
| 20 | tests/test_rule_research_label_readiness.py |

**依賴／API**：只更新 TEST_INVENTORY 精確 path→既有分類與三文件對應數量；tests、production、runner、直接 bridge 名單皆唯讀。B01 label boundary 測試也唯讀，不借分類修 assert。P1/P2 新 test 等中央實際採入才另外登錄，不在本包先造不存在路徑。
**驗收**：只新增這 20 entries，舊 entries 值不变；direct bridge 精確 12 paths 不變、manual/legacy 不擅提升；三文件對應數量無漂移；scripts/audit_test_inventory.py --skip-pytest-collection --output-json output/qa/i20_inventory.json 的 filesystem=1281/inventory=1125/missing=156（固定基準且沒有中央其他採入時）、stale=0、documentation drift=0、overall仍 failed。若父層已採其他新檔，報基準→實際 delta，不硬湊數。collection skipped，不能宣稱全 pytest／全 registry PASS。需要 raw log/JSON/hash＋20逐檔理由及 base/head blobs；不得批量把其餘156歸 unit、放寬治理／排除清單或直接 runner。
**禁止**：動 test source、source_id 三檔、B01 guard、任何 UI／DB／正式執行／runner bridge／assert/xfail；不得把 missing inventory 宣稱產品 bug，也不跑全176。
**worker prompt**：固定 HEAD 建專屬 lane，讀四治理檔規則後只處理表中20。逐檔读 imports/fixtures/assert/CLI/subprocess 的真副作用，先列原類別候選／理由再寫 registry；不執行真資料測試。更新精確數量，capture skip-collection audit 與剩156 FAIL，commit 四 owned 檔，交差分/20分類理由/raw/hash。下一批由中央再鎖，不自行擴20。

## 邊界與中央接手

本輪文件審查沒有寫 DB、沒有跑測試，沒有新增 lane。基準已核四用途64、Workbench85、validator25/4skip、full-roots mypy839的證據沿用。原9stage／24UX、七有限 closed、性能例外、unknown／自然累積與正式啟用限制原樣保留。source_id 三檔直接批准尚未收到；本文不更改其鎖，也不建替代 caller 繞過。父層可立即派 P1＋I20；P2 收 P1 exact API 後由同 Sol 接續或另派。


## I156 一次有界分類收尾（I20 採入後）

這是原 B15「清冊完整性」可修工程，證據是原 test_all_python_files_in_tests_are_registered_exactly_once 及 audit 的 unregistered_test_files blocker；不屬自然時間／真人資格／源授權等待。可本次一次完成的範圍是 **I20 後凍結的全部156既存 Python檔逐項分類**，不是每20重開一輪。不得由登錄取得 executed coverage／正式 ML/PIT／UI runner資格。

**固定 code base**：e1857a310daa3b4803bb9c9fd1a06a7d31079fea。I20 worker2f7c467c→中央95d381a4，四檔exact scope、20來源blobs／舊entries／direct12與raw hashes已核；中央metadata1281/1125/missing156/stale0/docdrift0、exit1。P1 workerd4d32fe2→中央e1857a31，新增tests/test_baldr_personal_paper_ledgers.py：它是另外一個已採入且具名的登錄增量，owner同包核證補入，**不是156來源集合之一**。因此當前scope為156＋P1具名新檔1；無其他採入時結束filesystem/inventory應同為1282。P2未採新測試不得預登錄；如果收尾前P2已中央採入，只接受其具名新檔與owned receipt的額外增量，與156分報，不重新擴搜尋成無限循環。

### 單一寫 owner 與四個只讀證據 lane

只允一個 I156 owner 修改原四治理檔：
1. qa/full_app_healthcheck/test_inventory.py
2. docs/06_qa/FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md
3. docs/06_qa/FULL_APP_HEALTHCHECK_COVERAGE_MAPPING_2026_06_24.md
4. docs/06_qa/TEST_INVENTORY_HEALTHCHECK_CLASSIFICATION_2026_06_23.md

中央在父層鎖 I156 後不共改四檔；P1/P2、B01、其他 reviewer 也不改。owner 收齐逐項 evidence 才一次寫mapping／三文件，最後一次metadata audit＋原兩inventory測試檔（13 governance cases）／targeted typing/compile/diff。不每group重跑全查、不執行156測試、不重UI union。只讀 reviewer 沒有任何 source/test/doc ownership，只各寫命名 ignored receipt；父層開thread，最多每Sol初期一位LunaMax，不能自行喚醒idle或開其他cloud thread。

| scope | 數量 | 維護角色／證據責任 | 唯一可寫receipt |
|---|---:|---|---|
| G0 helpers／governance | 8 | 同一 I156 writer 先只讀核 helpers、locking/cadence/COM／controller；另核P1新test1 | output/qa/i156-G0-evidence.json |
| G1 ML observed/restated／rule research chain | 47 | readonly reviewer；區別純DTO／研究計算、真正fit/model deserialize、publish/CLI/live來源風險，unknown資格不升 | output/qa/i156-G1-evidence.json |
| G2 source/PIT/acquisition/scheduled | 33 | readonly reviewer；沿原fixture到endpoint/DB/file入口，核write/apply/publish與network／env dependency | output/qa/i156-G2-evidence.json |
| G3 personal/COW/portfolio | 19 | readonly reviewer；分清原synthetic保存、migration/activation CLI、oracle和UI呈現，不正式啟用 | output/qa/i156-G3-evidence.json |
| G4 UI／stock／history／presentation | 49 | readonly reviewer；真QWidget／MainWindow callback才是candidate，純payload/readmodel仍oracle/unit；COM/Native/環境需求不可假轉direct | output/qa/i156-G4-evidence.json |

群組是**派工分區而非分類結果**。源 manifest對156全部給 exact path／Git blob／working SHA／行數／AST入口索引。imports或filename只導讀，不自動決定category。G4可由該Sol的一位LunaMax只讀分閱固定其中subset，主Sol負責全49 evidence，不增寫owner。

### 每entry必要證據與owner決策

receipt固定欄位：base、group、path、git_blob、working_sha256、purpose、imports_refs、fixture_refs、assert_refs、entry_calls、side_effects、isolation_proof、environment_requirements、candidate_category、category_reason、tests_executed=false、reviewer。refs須是原檔精確line／symbol；side_effects逐一區分讀／寫／network／fit／model/registry／CLI subprocess；跨import fixture追到其原定義/參數，不因tmp_path字樣就假設整鏈隔離。不能用AST摘要替代逐檔read。

owner核156集合exact一次覆蓋／無漏無重、blob相同，對例外/歧義逐條唯讀查證；只選既有分類。副作用／環境混合檔採既有治理規則最保守適用類別，須具體指出真入口與隔離缺口，不能把所有CLI或所有未決自動批量塞write-risk。每entry必保用途與reason；writer可以採review證據，不必四人重複查全倉。

兩個 support helper仍需metadata登錄且確認無test_入口；本scope **不改 PYTEST_SUPPORT_FILES／PYTEST_COLLECTED_FILES／PYTEST_NOT_COLLECTED_FILES 與runner邏輯**。原test精確assert support set，直接加2會製造額外contract變更。新helper按原derived规则是not-collected，不因此偽稱收集或排除。只在既有category按真正helper用途登錄，不刪檔、不增掃描排除清單。

原已登錄1125 entries與分類值、direct12、manual/legacy值、tests內容、assert與xfail、global六MLFAIL維持不變。任何需要重分類舊entry或改support API的提案都在本scope外，報精確檔但不可自改。

### 一次收尾驗收與邊界

- 156原集合＋P1具名新檔1：逐條purpose/side effect/既有category/reason/來源pin完備；增量若有已採P2具名檔，另表核，不假造未存在路徑。
- 目前code base且不再採新test：filesystem=inventory=1282、missing=0、stale=0、doc count drift=0、direct仍exact12、所有舊分類不變。collection skipped；僅metadata PASS可稱清冊分類工程完成，不能稱全tests/App/UI通過。
- 原13治理cases在實際source tree跑，assert不改；I20原10pass/3FAIL是當時收據，不能補造其通過。純isolated worktree若缺基準ignored LUNA歷史raw兩link，原link errors獨立保留；中央root有原始檔時最後audit核實即可，不複製假evidence、不編歷史文件／抑制link checks。
- raw final audit JSON/log、pytest log/JUnit與exact immutable owned commit／four base/head blobs／逐項 evidence hashes落地；mypy只registry、compile及diff適量。audit若仍任何blocker，具名FAIL，不把missing0當overall PASS。
- source_id三檔仍待直接批准，零碰；P1/P2真writer與正式資料／Task／ACL／Native／fit/trade未授。Stage/UX／七有限closed／性能例外原樣。

### 可直接派工prompts

**I156 writer**：以凍結code base建立獨立lane，排他僅四治理檔；先核G0八項＋已採P1一項，讀原分類規則／原治理tests，收G1-G4 exact逐檔evidence。不可依filename bulk guess。每個entry核用途／真入口／隔離與category理由，保舊1125值／direct12／tests／support及runner API。證據齊備後一次補156＋具名已採增量並同步三文件數量；最終skip-collection audit＋原13治理cases/mypy/compile/diff，落固定commit/raw/hash/完整逐項理由。Scope是凍結全部156，非每20再派；未知或其他blocker如實具名，不假綠。不共編中央文件／plan，不push或實際跑來源156。

**G1/G2/G3/G4 readonly reviewer**：從source manifest取你group exact paths；以指定ref Git blobs讀內容／沿imports追fixture、test assertions與原CLI/producer/DB/network/fit副作用。每entry按上述schema寫唯一ignored evidence文件，tests_executed=false；不import或run測試、不改任何source/test/doc/registry，不新建cloudthread、不喚醒idle。Group只是ownership分工不是category，不能按名猜分類；每條給可核line/symbol／category理由，缺件逐條提出，交證據writer定案。保持source_id及其他lane唯讀。


### 凍結156：每組精確path（全程唯讀）

#### G0-owner-support-governance (8)

- tests/forward_outcome_test_support.py
- tests/ml_research_test_support.py
- tests/test_capture_evidence_events_cli_locking.py
- tests/test_evidence_pipeline_cli_locking.py
- tests/test_heartbeat_chain_repairs.py
- tests/test_operational_quality_cadence.py
- tests/test_query_baldr_scheduled_tasks_com.py
- tests/test_weekly_collection_controller.py

#### G1-ml-observed-restated (47)

- tests/test_bounded_restated_research_c.py
- tests/test_bounded_restated_research_output_boundary.py
- tests/test_build_ml_current_restated_outcome_store_cli.py
- tests/test_calculate_forward_outcomes_cli.py
- tests/test_current_observed_capacity_eligibility.py
- tests/test_current_observed_capacity_replay.py
- tests/test_current_observed_context_hash_format.py
- tests/test_current_observed_feature_batch_scheduler.py
- tests/test_current_observed_feature_snapshot_composer.py
- tests/test_current_observed_learning_capture.py
- tests/test_current_observed_market_ownership_reader.py
- tests/test_current_observed_natural_research_fit.py
- tests/test_current_observed_normal_branch.py
- tests/test_current_observed_raw_cycle_dependency.py
- tests/test_current_observed_source_contract.py
- tests/test_current_restated_calendar_qualification.py
- tests/test_current_restated_raw_source_scan.py
- tests/test_current_restated_research_invocation_hash_pins.py
- tests/test_current_restated_source_context.py
- tests/test_forward_outcome_context.py
- tests/test_ml_allocation_forward_preflight.py
- tests/test_ml_current_restated_outcome_store.py
- tests/test_ml_daily_price_repair_pair.py
- tests/test_ml_daily_source_row_research_adapter.py
- tests/test_ml_daily_source_row_research_projection.py
- tests/test_ml_direct_research_output_boundaries.py
- tests/test_ml_fix_a_guards.py
- tests/test_ml_prospective_daily_price_capture.py
- tests/test_ml_quarantine_release_manifest_hash.py
- tests/test_ml_research_direct_ooc_adapter.py
- tests/test_ml_research_end_to_end_pipeline.py
- tests/test_ml_research_output_boundary.py
- tests/test_ml_revision_aware_raw_candidate.py
- tests/test_recommendation_natural_outcomes_current_observed.py
- tests/test_recommendation_natural_outcomes_current_observed_batches.py
- tests/test_recommendation_research_scope.py
- tests/test_recommendation_restated_research.py
- tests/test_rule_research_label_readiness_cli.py
- tests/test_rule_research_observation_acceptance.py
- tests/test_rule_research_parent_capture.py
- tests/test_rule_research_registry_integration.py
- tests/test_rule_research_sample_capture.py
- tests/test_rule_research_sample_integration.py
- tests/test_rule_research_shadow_acceptance.py
- tests/test_rule_research_shadow_acceptance_boundary.py
- tests/test_rule_research_shadow_acceptance_cli.py
- tests/test_rule_research_shadow_acceptance_safety.py

#### G2-sources-pit-scheduled (33)

- tests/test_apply_current_monthly_snapshot.py
- tests/test_capture_tdcc_current_ownership.py
- tests/test_current_fundamentals_scheduled.py
- tests/test_current_market_status_observation.py
- tests/test_current_monthly_revenue_materialization.py
- tests/test_current_official_valuation.py
- tests/test_excluded_daily_price_dependency_capture.py
- tests/test_export_market_csv_cli.py
- tests/test_institutional_revision_read_model.py
- tests/test_market_csv_export.py
- tests/test_market_session_policy.py
- tests/test_membership_history_cli.py
- tests/test_monthly_revenue_research_candidate.py
- tests/test_mops_current_statement_html.py
- tests/test_mops_quarterly_openapi_research_capture.py
- tests/test_mops_success_response_custody.py
- tests/test_pit_inactive_security_termination_evidence.py
- tests/test_pit_same_day_reuse.py
- tests/test_pit_taxonomy_source_config_proof.py
- tests/test_pit_taxonomy_split_contract.py
- tests/test_recommendation_current_fundamental_provider.py
- tests/test_recommendation_current_fundamental_source_root.py
- tests/test_recommendation_current_market_status_preflight.py
- tests/test_scheduled_mops_statement_custody.py
- tests/test_scheduled_official_market_status_bundle.py
- tests/test_scheduled_quick_current_ownership.py
- tests/test_scheduled_recommendation_date_roles.py
- tests/test_scheduled_research_acquisition_audit.py
- tests/test_scheduled_writer_reservation.py
- tests/test_shared_market_research_consumers.py
- tests/test_statement_report_basis_contract.py
- tests/test_twse_quote_observation_capture.py
- tests/test_update_current_mops_statements_http_custody.py

#### G3-personal-cow-portfolio (19)

- tests/test_f4_item_revision_storage_recovery.py
- tests/test_f4_item_storage_governance.py
- tests/test_f4_research_release_integration.py
- tests/test_paper_event_source_capture_entry.py
- tests/test_personal_data_paths.py
- tests/test_personal_journal_app_integration.py
- tests/test_personal_journal_storage.py
- tests/test_personal_watchlist_app_integration.py
- tests/test_personal_watchlist_cow_activation.py
- tests/test_personal_watchlist_cow_conversion.py
- tests/test_personal_watchlist_service.py
- tests/test_portfolio_quote_freshness.py
- tests/test_watchlist_cow_activation.py
- tests/test_watchlist_cow_storage_governance.py
- tests/test_watchlist_empty_pool_presentation.py
- tests/test_watchlist_json_cow.py
- tests/test_watchlist_json_cow_activation.py
- tests/test_watchlist_sqlite_cow.py
- tests/test_watchlist_sqlite_cow_cli.py

#### G4-ui-stock-history-research (49)

- tests/test_chart_viewport_state.py
- tests/test_current_stock_research_cycle.py
- tests/test_decision_desk_focus_source_date.py
- tests/test_f2_f3_main_consumer_bridge.py
- tests/test_multi_method_research_consensus.py
- tests/test_pandas_table_model_decimal_display.py
- tests/test_pattern_analysis/test_triangle_degenerate_lines.py
- tests/test_phase3_luna_ui_fixes.py
- tests/test_qa_cross_page_mainwindow_readback.py
- tests/test_recommendation_saved_chart.py
- tests/test_recommendation_saved_chart_integration.py
- tests/test_research_bookmark_main_bridge.py
- tests/test_research_membership_history_index.py
- tests/test_research_membership_lifecycle.py
- tests/test_research_membership_lifecycle_read_model.py
- tests/test_saved_stock_technical_chart.py
- tests/test_saved_strategy_rule_card.py
- tests/test_stock_research_as_of_visible.py
- tests/test_stock_research_chart_payload.py
- tests/test_stock_research_current_observed_market_ownership.py
- tests/test_stock_research_ml_scope_context.py
- tests/test_stock_research_readability.py
- tests/test_stock_research_report_provider_contracts.py
- tests/test_stock_research_shared_feature_consumer.py
- tests/test_stock_research_source_recovery.py
- tests/test_stock_research_technical_history.py
- tests/test_strategy_rule_card_readmodel.py
- tests/test_ui_qt_chart_viewport.py
- tests/test_ui_qt_daily_market_research_main_routing.py
- tests/test_ui_qt_forward_outcome_receipt.py
- tests/test_ui_qt_monthly_revenue_diagnostics.py
- tests/test_ui_qt_multi_method_research_consensus.py
- tests/test_ui_qt_page_help.py
- tests/test_ui_qt_parent_receipt_dialog.py
- tests/test_ui_qt_recommendation_saved_chart.py
- tests/test_ui_qt_saved_stock_chart.py
- tests/test_ui_qt_saved_strategy_rule_card.py
- tests/test_ui_qt_stock_research_missing_copy.py
- tests/test_ui_qt_stock_technical_history.py
- tests/test_ui_qt_strategy_rule_card.py
- tests/test_ux02_market_portfolio_status.py
- tests/test_ux02_research_status_consumers.py
- tests/test_ux02_status_vocabulary.py
- tests/test_ux03_research_bookmark_ui.py
- tests/test_ux04_05_daily_market_research_view.py
- tests/test_ux09_history_browse_view.py
- tests/test_ux09_history_recovery_consumers.py
- tests/test_ux09_membership_lifecycle_view.py
- tests/test_ux13_market_cohort_view.py

完整source pins／AST入口索引：output/qa/baldr_i156_complete_scope_20261006.json；它是source scope索引，classification_status仍not_yet_reviewed，不當逐檔分類證據。
