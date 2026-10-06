# 測試清冊與 Healthcheck 執行邊界

## 2026-10-06 machine refresh

固定 base `917f6af0387a4d9944b261eddbc0c46e84cf34b2`，依中央 dispatch 僅補表列 20 個既存測試的 metadata；測試本體、production、runner、source_id 三檔與其他 owner 均未修改。原 dispatch 審查 base `5d9ddf9…`，其 manifest final_head 與本次固定 base 相同。基準→本包 filesystem `1281→1281`、inventory `1105→1125`、missing `176→156`，stale `0`、documentation count drift `0`；collection skipped，overall 仍為 **failed**。

Current filesystem Python files: `1281`
Current registry entries: `1125`
Current collected test cases: 未執行

| 分類 | 數量 |
|---|---:|
| `general-unit-keep-in-pytest` | 159 |
| `governance-doc-tooling` | 173 |
| `healthcheck-runner-owned` | 29 |
| `legacy-or-low-priority` | 3 |
| `manual-only` | 14 |
| `service-oracle-data-market` | 162 |
| `service-oracle-portfolio-decision-runtime` | 139 |
| `service-oracle-recommendation` | 168 |
| `service-oracle-research-backtest` | 110 |
| `slow-e2e-or-environment` | 4 |
| `ui-healthcheck-candidate-bridge` | 70 |
| `ui-healthcheck-direct-bridge` | 12 |
| `write-risk-dry-run-required` | 82 |

本次增量為 recommendation oracle 7、data/market oracle 3、research/backtest oracle 7、governance tooling 2、UI candidate 1；direct bridge 精確 12 paths、manual/legacy 舊值不變。AST test definitions 只是來源索引，不是 collected 或 executed cases；candidate/oracle 登錄不等於 runner 執行 coverage。自然時間／unknown／Formal／training 資格不由 metadata 補登取得。

raw 收據位於本 lane 的 `output/qa/i20_inventory.json`／`i20_manifest.json`／`i20_verification.json`；包含 before/after audit、20 source pins、imports/fixture/assert 入口、I/O 索引、分類理由、變更 mapping 與 base/head blobs。獨立 worktree 未帶入 ignored `output/luna_B/pytest_full.log`、`repo_map.json`，基準已有兩筆歷史 markdown link errors；本包保留並分報，不造 raw evidence、不更改他人文件。machine blocker 仍有 `unregistered_test_files:156`，不是產品 bug 或全庫豁免。focused 驗證只核 inventory/governance contracts，未執行本表 20 tests 或全176。

### I20 精確分類與副作用理由

所有 `tmp_path`／`tempfile` 寫入都是 source 中既有合成 fixture 或隔離 persistence；以下只是讀碼判讀，未執行這些流程。UI candidate 未加入 direct allowlist；其餘皆 pytest-only。

| # | 唯讀測試檔 | 分類 | 用途／來源／副作用位置 |
|---|---|---|---|
| 1 | `tests/test_daily_market_cohort_main_bridge.py` | `ui-healthcheck-candidate-bridge` | QApplication／RouteHarness(MainWindow) 連接真 view、按鈕與同一 verified snapshot；_seed_database／_produce 僅 tmp_path。assert 驗共享 hash／date／拒絕後清空；不是既有 runner direct allowlist。 |
| 2 | `tests/test_daily_market_cohort_projection.py` | `service-oracle-recommendation` | _write_v2_snapshot／_fixture 在 tmp_path 寫合成 immutable JSON；project／sort 驗來源 pin、全分母、unknown、排序與 forged rows 拒絕，屬研究 cohort 服務投影。 |
| 3 | `tests/test_daily_market_feature_snapshot.py` | `service-oracle-recommendation` | _prices／_technical 僅合成 Decimal DTO；project 驗觀測值、連續 warmup、future／重複日期、快取 identity 與 unknown，無檔案或 DB I/O。 |
| 4 | `tests/test_daily_market_method_contract.py` | `service-oracle-recommendation` | method_contracts_payload＋evaluate_daily_market_conditions 驗方法 binding／決策日拒絕與 legacy 最小投影；純記憶體研究篩選契約。 |
| 5 | `tests/test_daily_market_research_bookmark.py` | `service-oracle-recommendation` | _capture 沿 tmp_path snapshot，_config 明示 tmp output；WatchlistService／Repository 驗收藏去重、精確 remove／restore、JSON→SQLite upgrade 與 revision。全部 synthetic persistence；不是正式 migration 授權。 |
| 6 | `tests/test_daily_market_research_capabilities.py` | `service-oracle-recommendation` | _fixture 在 tmp_path 寫合成 snapshot JSON，not-opened.sqlite 只作來源引用；project 驗五項 capability、method hash、完整宣告分母、unknown 與 schema/source 拒絕。 |
| 7 | `tests/test_daily_market_research_screener.py` | `service-oracle-recommendation` | _seed_database(tmp_path) 建 SQLite，_service 明示 snapshot_root；produce/read/filter/context/report 真服務驗 Kleene、pin、source revision、cancel。正式 output sentinel 不被使用；屬研究名單服務 oracle。 |
| 8 | `tests/test_daily_market_snapshot_consumer.py` | `service-oracle-recommendation` | _seed(tmp_path) 建合成行情 SQLite，_produce→StockResearchReportReadService 驗 verified publication 與 stale source 拒絕；CLI outside-isolation 先拒，無 live fallback；研究 consumer oracle。 |
| 9 | `tests/test_daily_market_snapshot_producer.py` | `service-oracle-data-market` | _producer／_loader 合成 DTO／capacity probe，tmp root 真出版→repository；驗 immutable/noop、CAS、容量、future/cancel、deep Unicode 與 subprocess readback。重點為資料出版完整性；非正式 harvester。 |
| 10 | `tests/test_daily_market_snapshot_repository.py` | `service-oracle-data-market` | _publish 在 tmp_path 寫合成 artifact／manifest／pointer；repository 驗 cohort/date/hash/method/warmup、tamper/alias、partial 分母。來源 DB 字串是引用，未開真 DB；資料 readback oracle。 |
| 11 | `tests/test_rule_research_benchmark_adapter.py` | `service-oracle-data-market` | _seed_database(tmp_path) 建 market_indices fixture；load_explicit_market_benchmark 驗兩步 pin、schema/type/availability/basis、WAL revision/cancel、來源 hash/mtime。測試中的 UPDATE 僅合成 DB；資料來源 oracle。 |
| 12 | `tests/test_rule_research_benchmark_integration.py` | `service-oracle-research-backtest` | _prepare(pipeline) 在 tempfile tree 建 explicit-index.sqlite 與 config；run_forward_isolated 真保存→subprocess exact receipt readback、成本/基準/修訂與取消。合成研究鏈；不取得正式 benchmark 資格。 |
| 13 | `tests/test_rule_research_daily_owner.py` | `service-oracle-research-backtest` | ctx 由 observation_context 產生隔離 source/config/roots；run_daily_owner 真 chain／status/retry/lock/quota＋新程序 CLI resume；formal source 路徑僅負例先拒。未註冊 Task，屬研究 owner 服務 oracle。 |
| 14 | `tests/test_rule_research_fair_boundary.py` | `governance-doc-tooling` | 在 tmp_path 複製唯讀 adapter source／寫惡意 import 字串，MLShadowBoundaryGuard.inspect 驗 exact import policy；不 fit、不開 registry；治理工具契約。 |
| 15 | `tests/test_rule_research_fair_comparison.py` | `service-oracle-research-backtest` | _prepared／_bundle_for 僅 pipeline 合成 DB／sealed receipts 與 exported feature/prediction DTO；build_fair_comparison 驗共同 cohort、integer bp、policy/target/pin、缺模型、cancel。無 training／模型 artifact I/O。 |
| 16 | `tests/test_rule_research_fair_comparison_cli.py` | `governance-doc-tooling` | main 與 subprocess CLI 讀 synthetic sealed receipts／tmp policy bundle；驗缺配置明示、JSON 重現、duplicate keys/byte bound 與缺 candidate，不訓練、不出版正式結果；CLI tooling。 |
| 17 | `tests/test_rule_research_forward_isolated.py` | `service-oracle-research-backtest` | pipeline 使用 tempfile.mkdtemp 明示隔離 root、seed SQLite/cache/config；run_forward_isolated 真 atomic outcome→saved reader／UI reader helper／daily overlay／subprocess。helper 不是 GUI bridge；驗 hash/unknown/cancel/budget。 |
| 18 | `tests/test_rule_research_forward_outcome.py` | `service-oracle-research-backtest` | _saved_child／parent_fixture 僅 tmp tree receipt，_market／_calendar 為 synthetic Decimal/日期；core 驗成本、報酬、全分母、pending、unknown、availability、極值與新程序 deterministic identity；研究計算 oracle。 |
| 19 | `tests/test_rule_research_forward_outcome_reader.py` | `service-oracle-research-backtest` | forward_saved 從 tmp_path 合成 parent/JSON 輸入；read_saved_parent_forward_outcome 禁 DB 開啟、source bytes 不變、新程序一致、tamper/cancel/partial 拒絕。不是 GUI，也不是已執行 coverage。 |
| 20 | `tests/test_rule_research_label_readiness.py` | `service-oracle-research-backtest` | _saved(pipeline) 準備合成 sealed outcome；label readiness 驗 label/split policy、availability、temporal partition、evaluation 不入 training、缺件不補零、bound/cancel。monkeypatch dates 只作 unit boundary，無真 train。 |


> 本文件只維護目前分類摘要；逐檔清單以 `qa/full_app_healthcheck/test_inventory.py` 為準。歷史執行紀錄不可當作本次通過證據。

## 2026-10-06 中央 machine refresh 歷史

本次僅補中央已採本輪14個具名新增 tests 的既有分類，不重分類他人、不新增 direct bridge。metadata audit 使用 --skip-pytest-collection，未完整收集 pytest，也未執行測試。7個UI相關新檔為 candidate，3個B10檔為 portfolio/decision/runtime oracle，1個B12檔為 research/backtest oracle，3個純契約檔為一般unit；candidate/oracle不代表healthcheck runner已接線。

Current filesystem Python files: `1281`
Current registry entries: `1105`
Current collected test cases: 未執行

| 分類 | 數量 |
|---|---:|
| `general-unit-keep-in-pytest` | 159 |
| `governance-doc-tooling` | 171 |
| `healthcheck-runner-owned` | 29 |
| `legacy-or-low-priority` | 3 |
| `manual-only` | 14 |
| `service-oracle-data-market` | 159 |
| `service-oracle-portfolio-decision-runtime` | 139 |
| `service-oracle-recommendation` | 161 |
| `service-oracle-research-backtest` | 103 |
| `slow-e2e-or-environment` | 4 |
| `ui-healthcheck-candidate-bridge` | 69 |
| `ui-healthcheck-direct-bridge` | 12 |
| `write-risk-dry-run-required` | 82 |

audit 原結果 overall failed：仍有176個未登錄檔（本輪前190，僅補14），stale0、collection errors0但未collection；原doc count drift7由本節反映實際registry數量，不修改其餘176檔分類。raw output/qa/b15_inventory_metadata_20261006.json，完整mandatory UI union仍待穩定版；不以清冊數量提升原stage/UX完成。以下9/30為當期歷史，不代替本次metadata結果。

Final metadata receipt: `output/qa/b15_inventory_metadata_final_20261006.json`, SHA256 `a6b845b3f5a1b2c1b0a0f48091178b6b0370504a77e64e1a0a351fbae58ae1b9`; documentation count drift=0, remaining blocker=`unregistered_test_files:176`, overall failed, collection skipped.


中央 caller 增量：另補七個已採新增檔，合計本輪22檔；B07/B13兩個research oracle、B09/B14/central personal三個portfolio oracle、B11一般unit、central chart一個UI candidate。上列為目前數量；前一筆14檔metadata收據保留為歷史，不冒稱覆蓋此次增量。direct bridge仍12，未執行collection／測試；176個其他未登錄檔不越權重分類。本次 metadata 收據 output/qa/b15_inventory_caller_corrected_20261006.json，SHA256 1fcdf7c86b7b5d06b54043f4903c4db03f489568132477de149d5fad64d8010c；doc drift 0、stale 0、collection skipped，overall failed 唯一 machine blocker unregistered_test_files:176。


B14 evidence composition新增1個portfolio/decision/runtime oracle，四新增檔已採7c23b7c5；metadata目前上列1105。前一筆1104收據為歷史，此增量audit output/qa/b15_inventory_integrated_20261006.json，SHA2564022cbb43d82785647d2cffbc379f29cadd02b45370cebde766bee639aacc2e5，docdrift0、stale0、collection skipped、唯一machineblocker unregistered_test_files:176；原53案例兩路分報，不提升正式來源資格。

## 2026-09-30 machine refresh

本次以 `scripts/audit_test_inventory.py --skip-pytest-collection` 更新清冊，pytest collection 未執行。新增 UI natural-shutdown runner 為 `ui-healthcheck-candidate-bridge`、read-only cancellation contract 為 `service-oracle-portfolio-decision-runtime`；另為同期新增的 paper scheduled CLI 參數測試補登 `governance-doc-tooling`。candidate bridge 仍不屬於 healthcheck direct bridge。filesystem／registry 均為 1072，missing／stale 為零；分類如下。

Current filesystem Python files: `1072`
Current registry entries: `1072`
Current collected test cases: 未執行

| 分類 | 數量 |
|---|---:|
| `general-unit-keep-in-pytest` | 155 |
| `governance-doc-tooling` | 170 |
| `healthcheck-runner-owned` | 29 |
| `legacy-or-low-priority` | 3 |
| `manual-only` | 14 |
| `service-oracle-data-market` | 159 |
| `service-oracle-portfolio-decision-runtime` | 132 |
| `service-oracle-recommendation` | 155 |
| `service-oracle-research-backtest` | 100 |
| `slow-e2e-or-environment` | 4 |
| `ui-healthcheck-candidate-bridge` | 57 |
| `ui-healthcheck-direct-bridge` | 12 |
| `write-risk-dry-run-required` | 82 |

Machine audit：filesystem／registry `1072/1072`、missing／stale `0/0`、collection errors `0`、documentation count drift `0`；pytest collection 未執行，因此不記錄 collected test cases。

## 2026-09-29 machine refresh

本次以 `scripts/audit_test_inventory.py --skip-pytest-collection` 刷新檔案清冊；pytest collection 未執行。補登先前遺漏的 WP5／隔離 QA 測試（`governance-doc-tooling` 2 項、`service-oracle-data-market` 3 項），以及本次 UI layout runner、helper、wrapped-list、推薦、回測與市場 layout 測試（`ui-healthcheck-candidate-bridge` 6 項）。候選測試仍不屬於 healthcheck direct bridge。filesystem／registry 均為 1069，missing／stale 為零；當期 category 數量如下。

Current filesystem Python files: `1069`
Current registry entries: `1069`
Current collected test cases: 未執行

| 分類 | 數量 |
|---|---:|
| `general-unit-keep-in-pytest` | 155 |
| `governance-doc-tooling` | 169 |
| `healthcheck-runner-owned` | 29 |
| `legacy-or-low-priority` | 3 |
| `manual-only` | 14 |
| `service-oracle-data-market` | 159 |
| `service-oracle-portfolio-decision-runtime` | 131 |
| `service-oracle-recommendation` | 155 |
| `service-oracle-research-backtest` | 100 |
| `slow-e2e-or-environment` | 4 |
| `ui-healthcheck-candidate-bridge` | 56 |
| `ui-healthcheck-direct-bridge` | 12 |
| `write-risk-dry-run-required` | 82 |

本次 machine audit：filesystem／registry `1069/1069`、missing／stale `0/0`、collection errors `0`、documentation count drift `0`；pytest collection 未執行，因此不記錄 collected test cases。

## 2026-09-28 machine refresh

本次先補登 `tests/test_qa_native_personal_model_acceptance.py`，分類為 `ui-healthcheck-candidate-bridge`；此 UI 自動化候選不會因此成為 healthcheck direct bridge。WP5 整合核查再補登 `tests/test_twse_industry_index_capture.py`（`service-oracle-data-market`）與 `tests/test_ui_qt_personal_model_assessment.py`（`ui-healthcheck-candidate-bridge`），均維持原分類邊界。最新 machine audit 的 filesystem／registry 均為 1058，missing／stale 為零；完整 pytest collection 未執行。

Current filesystem Python files: `1058`
Current registry entries: `1058`
Current collected test cases: 未執行

| 分類 | 數量 |
|---|---:|
| `general-unit-keep-in-pytest` | 155 |
| `governance-doc-tooling` | 167 |
| `healthcheck-runner-owned` | 29 |
| `legacy-or-low-priority` | 3 |
| `manual-only` | 14 |
| `service-oracle-data-market` | 156 |
| `service-oracle-portfolio-decision-runtime` | 131 |
| `service-oracle-recommendation` | 155 |
| `service-oracle-research-backtest` | 100 |
| `slow-e2e-or-environment` | 4 |
| `ui-healthcheck-candidate-bridge` | 50 |
| `ui-healthcheck-direct-bridge` | 12 |
| `write-risk-dry-run-required` | 82 |

## 2026-09-27 machine refresh

本次以 `scripts/audit_test_inventory.py --skip-pytest-collection` 盤點目前 filesystem 與 registry；未執行 pytest collection，因此不宣稱本次測項數。相較前一版 1045 筆登錄，本次補入 9 個新個人化推薦測試（8 個服務測試、1 個 UI candidate bridge）及先前漏登的既有 `tests/test_phase3c_candidate_repair.py`。R028 單一 job/facade 登錄與此前 1044 檔盤點收據均保留為歷史檢查點，分別見 `output/qa/refactor_completion_20260927/r028_inventory_audit_20260927.json` 與 `output/qa/refactor_completion_20260927/docs_inventory_repair_20260927/test_inventory_audit_post_patch_20260927.json`。

Current filesystem Python files: `1055`
Current registry entries: `1055`
Current collected test cases: 未執行

| 分類 | 數量 |
|---|---:|
| `general-unit-keep-in-pytest` | 155 |
| `governance-doc-tooling` | 167 |
| `healthcheck-runner-owned` | 29 |
| `legacy-or-low-priority` | 3 |
| `manual-only` | 14 |
| `service-oracle-data-market` | 155 |
| `service-oracle-portfolio-decision-runtime` | 131 |
| `service-oracle-recommendation` | 155 |
| `service-oracle-research-backtest` | 100 |
| `slow-e2e-or-environment` | 4 |
| `ui-healthcheck-candidate-bridge` | 48 |
| `ui-healthcheck-direct-bridge` | 12 |
| `write-risk-dry-run-required` | 82 |

- 本次快速盤點 filesystem／registry 均為 `1055`，missing `0`、stale `0`、collection errors `0`；pytest collection 未執行，collected count 為 unknown。前次文件摘要與索引更新的 audit `overall_status=passed`、documentation count drift `0`、formal entry reference errors `0` 收據保留為此前 1044 檔基線。
- 前次 1044 檔 refresh 前的 audit 曾檢出舊文件計數 `852` 與兩個缺漏的正式入口；當時只修正當期摘要與索引連結，保留舊 machine snapshot 作歷史紀錄。再前一版 R028 登錄只新增一個 `governance-doc-tooling` 測試路徑；本段當前增量另列於下一項。
- 本次分類增量為 `service-oracle-data-market` 1、`service-oracle-recommendation` 8、`ui-healthcheck-candidate-bridge` 1；未將服務或 UI 測試改列 governance CLI，也未擴大 direct bridge。

## 2026-09-17 historical machine snapshot

本次 machine refresh 同步 ABC bounded registry；前次 2026-09-15 摘要保留於更新記錄。

Current filesystem Python files: `852`
Current registry entries: `852`
Current collected test cases: `5811`

| 分類 | 數量 |
|---|---:|
| `general-unit-keep-in-pytest` | 150 |
| `governance-doc-tooling` | 155 |
| `healthcheck-runner-owned` | 29 |
| `legacy-or-low-priority` | 3 |
| `manual-only` | 14 |
| `service-oracle-data-market` | 127 |
| `service-oracle-portfolio-decision-runtime` | 130 |
| `service-oracle-recommendation` | 45 |
| `service-oracle-research-backtest` | 74 |
| `slow-e2e-or-environment` | 4 |
| `ui-healthcheck-candidate-bridge` | 38 |
| `ui-healthcheck-direct-bridge` | 12 |
| `write-risk-dry-run-required` | 71 |

- 預設收集檔案：824；support：5；不收集：23；三者合計 registry entries `852`。
- 2026-09-09 補齊資料工作新增五份測試；本輪再加入四份 V4 effectiveness／FinMind candidate 測試，均僅用隔離資料驗證，不授予 runner 正式資料寫入權限。
- 歷史對照：本段更新前的機器摘要曾記錄總數 `743`、general `147`、governance `138`、data `110`、portfolio-runtime `106`、research-backtest `71`、UI candidate `26`、write-risk `64`；以上數字保留作舊 QA 快照，不代表目前清冊。
- 2026-09-17 ABC registry sync 補登 19 個既有／bounded path：A official lineage 1、B consumer／相鄰 QA 2、C personalization 10，以及原先 foreign／L residual 6；未將任何新增測試升格為 direct bridge。快速 `--skip-pytest-collection` audit 與完整 audit 均為 filesystem／registry `852/852`、missing `0`、stale `0`、collection errors `0`；完整 audit 實收集 `5811` 測項，count drift 於本次文件更新後為 `0`。
- 原先列為 residual 的 `tests/test_cross_page_decision_journey_mainwindow.py`、`tests/test_db_lock_wait.py`、`tests/test_pit_taxonomy_daily_source.py`、`tests/test_review_warning_classification.py`、`tests/test_security_lifecycle_caller.py`、`tests/test_security_lifecycle_contract.py` 已依責任分類登錄；cross-page 仍為 candidate UI bridge，其他各自維持 data／governance／general unit 邊界。
- 本輪清理前實測為 748 個 Python 檔、4639 測項；舊 679 檔／4005 測項是較早檢查點。
- 本輪補登 69 個檔案（含既有 ml_teacher_fixture 支援檔），刪除七份一次性診斷，兩份欄位測試合為參數化雙入口測試。
- 2026-09-08 最終 collection 為 4,655；全量 pytest 為 4,652 passed、3 skipped；missing／stale／count drift 為零。見 [LUNA 三線整合驗收](LUNA_INTEGRATION_CLOSEOUT_2026_09_08.md)；[前次查核](PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md) 保留為歷史。
- 2026-09-09 TDCC candidate completion 新增 2 個定向測試與 2 個同輪資料服務測試登錄；本輪 V4 forward outcome producer 再新增 1 個治理測試並完成登錄。本段計數以當前 filesystem／registry machine audit 為準，TDCC raw/candidate 仍位於 ignored output。
- 2026-09-10 登錄跨日 evidence contract 整合測試，以及既有 UI theme／watchlist layout 測試；本輪新增測試仍只使用隔離資料或 UI fixture，不因此進入 direct bridge。
- 2026-09-13 登錄每日 recommendation calibration learning、官方 daily-price custody、corporate-action adjustment custody、source-contract 與 capture-binding 測試；均維持 service oracle 分類，不因此進入 direct bridge。
- 2026-09-14 登錄 `test_recommendation_calibration_contract_guards.py` 與 `test_recommendation_learning_cache_hit_custody.py`；維持 service-oracle-recommendation 分類，均不進 direct bridge。

## 2026-09-17 bounded ABC registry classification

本輪只更新已交付的 A／B bounded scope；不重跑 full suite，也不把任何新測試升格為
direct bridge。`qa/full_app_healthcheck/test_inventory.py` 的精確分類如下：

| Lane／scope | 測試路徑 | 分類／執行邊界 |
|---|---|---|
| B historical context／label assembly | `tests/test_ml_historical_feature_builder.py`、`tests/test_ml_historical_feature_computation.py`、`tests/test_ml_historical_label_builder.py`、`tests/test_ml_historical_snapshot_provider.py` | `general-unit-keep-in-pytest`；僅 bounded unit／snapshot contract，無正式資料寫入。 |
| B price-unavailable consumer scope | `tests/test_qa_validate_price_unavailable_consumer_scope.py` | `governance-doc-tooling`；只驗證 bounded reader／consumer scope，不執行 D 寫入、rebuild 或 candidate apply。 |
| A Direct checkpoint provenance recovery（相鄰 bounded QA） | `tests/test_ml_direct_checkpoint_provenance_recovery.py` | `governance-doc-tooling`；隔離 recovery／readback contract，仍不授權正式 D checkpoint 或 promotion。 |
| A official market-event prior lineage | `tests/test_official_market_event_prior_lineage.py` | `service-oracle-data-market`；pytest-only reader compatibility／valid-parent、tamper、broken-chain，單檔 3 tests；A lineage path 跨檔 focused suite 8 passed，隔離 next-publication chain 不進 UI bridge。 |
| A Paper／calendar／Recommendation | `tests/test_paper_portfolio_isolated_scheduler.py`、`tests/test_scheduled_recommendation_snapshot_wrapper.py`、`tests/test_daily_banktaiwan_learning_cost.py`、`tests/test_scheduled_ml_raw_pit_refresh.py`、`tests/test_scheduled_decision_evidence_capture.py` | 沿用既有 `governance-doc-tooling`／`service-oracle-recommendation`／`service-oracle-portfolio-decision-runtime`／`write-risk-dry-run-required` 分類；default calendar loader 與 9/17 receipt 只作 readback／focused QA，不折抵 Paper 或 Formal。 |
| C personalization bounded engineering | `tests/test_personalization_action_recorder.py`、`tests/test_personalization_calibration.py`、`tests/test_personalization_contract.py`、`tests/test_personalization_fit_cli.py`、`tests/test_personalization_fit_runner.py`、`tests/test_personalization_generation_cli.py`、`tests/test_personalization_projection.py`、`tests/test_personalization_read_service.py`、`tests/test_personalization_runner.py`、`tests/test_personalization_save_integration.py` | `service-oracle-recommendation`；fit producer／persistence／CLI／readback bounded QA，focused suite 41 passed；pytest-only，不自動進 UI bridge。 |

目前 B 的歷史測試檔、A 相鄰 bounded lineage QA、B consumer-scope QA 與 C
personalization bounded engineering tests 均已在 registry；A lineage path 為 pytest-only，C
focused fit／CLI／calibration／read service 為 41 passed。這些測試維持各自 service／governance
分類，不自動升格為 direct bridge、Paper、Formal 或 V6 adoption；fixture／replay／`natural sample=0`
不折抵正式 evidence。前次 2026-09-15 machine refresh 的摘要僅作歷史對照；本節 current counts
以 2026-09-17 machine audit 為準，下一次 shared registry refresh 應重新計算 filesystem／registry／collection 差異。

## 2026-09-24 inventory delta（非完整 machine refresh）

本輪先延續先前五個 R020 測試檔，再登錄第六檔
`tests/test_research_run_portfolio_finalize.py`；後續再登錄第七檔
`tests/test_r020_portfolio_result_registry_service.py`，兩者皆分類為
`service-oracle-research-backtest`。目前七檔合計為 `service-oracle-recommendation` 2 檔、
`service-oracle-research-backtest` 5 檔。上方 2026-09-17 machine refresh 數字保留為歷史快照，
未以本輪局部登錄改寫。

先前五檔 route 的歷史 audit 記錄為：filesystem 985 檔、pytest collection 7,469 cases；registry 由 872 增至
877、missing 由 113 降至 108，stale 與 collection errors 均為 0。本次另以 fresh TEMP／`PROFILE=test` 執行
fast audit；新增 entry 前後 filesystem 均為 986 檔，registry 由 877 增至 878、missing 由 109 降至 108，
stale 與 collection errors 均為 0，`service-oracle-research-backtest` 由 78 增至 79。fast audit 跳過 pytest
collection，故本輪沒有新的 collected-case 數字；7,469 仍只代表先前五檔 route 的歷史 collection 結果。

audit 仍未通過：剩餘 108 個未登錄檔案不屬本輪範圍，且 registry 與 2026-09-17 歷史摘要間仍有 5 個計數欄位
不一致。此差異註記不是全庫 refresh 或 inventory audit PASS。

2026-09-24 後續增補第七檔前，fast audit 為 filesystem 987、registry 878、missing 109；其中
`tests/test_r020_portfolio_result_registry_service.py` 是本輪新增的未登錄檔。完成登錄後為 filesystem 987、
registry 879、missing 108，stale 與 collection errors 均為 0，`service-oracle-research-backtest` 由 79 增至
80。fresh TEMP／`PROFILE=test` fast audit 跳過 pytest collection，沒有新的 collected-case 數字。
剩餘 108 個 missing entries 與歷史摘要計數 drift 仍未處理；本輪不是全庫 inventory audit PASS。

## Runner 規則

- quick 模式只允許已明確註冊的快速、非破壞 UI 檢查。
- direct bridge 的允許清單仍只有原先 12 份 UI 測試；candidate、service oracle 與新登錄測試不自動成為 direct bridge。
- full mode 也不是執行正式資料 migration、harvester 或大型外部請求的授權。
- manual-only、write-risk-dry-run-required 不得直接進非破壞 runner；僅在測試明確使用 tmp_path、mock 或 dry-run 時定向執行。
- high-risk-dry-run 只驗證 dialog、cancel、dry-run 與 mock service 未被呼叫。
- bridge 保留 covered_healthcheck_ids、covered_flow_ids；同一功能在不同層級的 oracle 與 UI 測試不可只因相似就刪除。
- tests/manual 與 tests/scripts 不由預設 pytest 收集；保留的 14 份 manual、6 份 scripts 不保證可直接執行。

## 使用與驗證

```powershell
.\.venv\Scripts\python.exe scripts/audit_test_inventory.py --output-json output/qa/test_inventory.json
.\.venv\Scripts\python.exe -m pytest tests/test_audit_test_inventory.py tests/test_full_app_healthcheck_test_inventory.py -q -o addopts=
```

執行前將 DATA_ROOT、OUTPUT_ROOT 指向本次隔離目錄；UI 測試使用 QT_QPA_PLATFORM=offscreen。新增任何 tests 下的 Python helper 也須登錄，並正確標為 support。

## 歷史與整併

舊文件反覆附加 2026-06-23、08-14、08-28 的清單、數量與中途測試結果，形成多份「current」敘述。本輪收斂成單一機器摘要，原文可由基線 `71500ef6fc834da285c19255e5c03f1846412329` 的同路徑或本輪精確備份還原。沒有刪除獨立測試的斷言來迎合清冊。

七份 retired diagnostics 的精確檔名、原因與回滾，統一保存在[整併查核](PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md)；不再維護另一份重複 README 或當前檔案列表。


## 2026-10-05 UX05 有界新增分類

本包只登錄 tests/test_daily_market_research_presets.py 為service-oracle-recommendation、tests/test_ux05_research_presets_ui.py 為ui-healthcheck-candidate-bridge。與相關route共43項定向通過，不升為healthcheck direct bridge。本包不refresh全量清冊／collection，上述舊全量數字不是今日完整數目；其餘先前新增而尚未登錄項目不在本包重新分類。
