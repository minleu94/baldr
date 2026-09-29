# WP5 目前 HEAD 缺口與 m11 pending 逐筆診斷（2026-09-29）

本報告是 [WP5 current checkpoint](WP5_CHECKPOINT_CURRENT_20260928.md) 的後續唯讀稽核與一項測試契約修補紀錄，不改寫舊收據。稽核時 `dev` HEAD 為 `447202fca5ed453f4c0bb399c1c3156c66cef146`，比 `origin/dev` 超前 305 commits。原有四份 MOPS／外部來源報告仍未追蹤；它們屬獨立來源原型線，不混入本次 WP5 裁定。本次沒有寫入正式行情庫，也沒有啟動 scheduler。

## 既有收據對目前程式的適用範圍

9/28 final scoped route 收據 [`final_frozen_route_receipt.json`](../../output/qa/wp5_integration_route_current_20260928_01/final_frozen_route_short_temp_20260928_01/final_frozen_route_receipt.json) 標記的 HEAD 是 `fd76b4e8dbb59034f9da5d4ff36021220ee3cfd4`，結果為 **183 passed、2 skipped**。將收據所列 31 個 path 的 SHA-256 逐一與目前工作樹比對，**29 個相同**；只有 `docs/00_core/PROJECT_SNAPSHOT.md` 與 `docs/06_qa/WP5_CHECKPOINT_CURRENT_20260928.md` 因後續記錄而不同。故該受限路由的原始程式與測試 bytes 仍具可引用性，但不能轉稱目前 HEAD 已通過整套測試、正常交易日真鏈或前景 UI。

修補前 full-suite 收據 [`full_suite_receipt.json`](../../output/qa/wp5_integration_route_current_20260928_01/full_suite_receipt.json) 在 2026-09-28 19:46–20:16 UTC 自然結束：**274 failed、8,378 passed、17 skipped、13 errors**。它同樣來自 `fd76b4e8`，且在三項測試隔離修補之前；修補後未重跑 full suite。當次 runner 設定隔離 `PROFILE`／`DATA_ROOT`／`OUTPUT_ROOT`／`DB_PATH`、Qt offscreen 與 repo 短 basetemp，但未設定 `TEMP`／`TMP`。以下數字來自原始 [`full_suite_failure_buckets.json`](../../output/qa/wp5_integration_route_current_20260928_01/full_suite_failure_buckets.json) 的第一個錯誤訊息分類，**是症狀索引，不是 287 項的根因裁定**。

| 舊失敗／錯誤桶 | 數量 | 已核對例子與現在可下的結論 |
| --- | ---: | --- |
| OS TEMP／repo-output 路徑契約 | 188 | `test_build_mops_statement_batch.py::test_batch_driver_is_bounded_and_emits_child_lineage` 舊 log 拒絕非 TEMP／repo-output 根目錄；目前 HEAD 將 `TEMP`、`TMP`、basetemp 指向 OS TEMP 後，該節點 **1 passed**。其他 187 項仍須分組重驗。 |
| 行為／CLI assertion | 48 | 包含 P0 intake CLI exit 2、decision desk snapshot assertion；異質節點，不可推定同一原因。 |
| Windows staging rename／replace `WinError 5` | 16 | OOC setup errors 與 DB stage guard 等；未在目前 HEAD 重驗。與另一次 WP4 `os.link` `WinError 3` 的短路徑重驗不是同一問題。 |
| 官方日曆／隔離 DB 前置缺件 | 14 | 修補前的 `test_position_health_transition_read_service.py::test_same_day_available_at_after_evaluator_observed_at_is_blocked` 先因 `official_calendar_unknown:2026-09-01,...,09-07` 失敗，且 warning 為 QA DB `unable to open database file`；當時未進入預期的 source-time 判斷。後續 test-only 修補見下方附記。 |
| hash／readback mismatch | 11 | 舊 raw summary 的 11 個 exact failures 均是 R027 logical-time gate；共同失敗在 `_frozen_direct_stable_identity` 的固定 payload-hash assertion，尚未進 gate 評估／SQLite readback。後續隔離重驗見 9/29 附記。 |
| runtime API／fixture mismatch | 7 | 兩個舊 `current_execution` 節點的 test-only fixture 已補 execution 與 verified ID，新增 match／empty／mismatch 三參數精確路由通過；舊 `reader_status` 節點在 OS TEMP 重跑通過，但較像路徑症狀仍屬推論。相鄰整檔另見 no-follow WinError 5，後續結果見 9/29 附記。 |
| inventory drift | 3 | registry 補登後 focused **13 passed**，audit filesystem／registry **1,058／1,058**、missing／stale 0；舊全套數字保持不變。 |

稽核基準的一個確定失敗原為 `tests/test_ui_qt_p2_status_accessibility.py::test_recommendation_detailed_progress_is_opt_in_and_cancellable`：舊 test double 缺 `_reset_negative_evidence_buffers`，而測試甚至仍期待舊式 list 回傳；現行 `RecommendationExecutionRequest.execute` 要求具名 `RecommendationExecution`。Luna Max 已只修改該測試檔，把詳細進度、取消與開始前取消斷言接到目前 terminal contract；隔離環境重跑整檔 **8 passed**。此測試修補不代表 full suite 已恢復通過。沒有修改 production code。

## m11 的 19 筆 pending

m11 capture [`ad981904…json`](../../output/qa/personal_daily_product_20261006/personal_research_ui/m11/output/_test/personal_prediction/captures/ad981904a1717affda64c1a787aa95c7602156344a67a6521dd0ff3c23b8ac28.json) 的 `decision_at` 是 2026-09-28 17:07:36 UTC（台北 9/29 01:07），`decision_date` 是 **2026-09-29**。Stage C 於 2026-09-28 17:13:55 UTC（台北 9/29 01:13）評估，摘要 [`6fbe8be5…json`](../../output/qa/s11/m11_20260928T1713Z/personal_natural_outcomes/runs/6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667.json) 是 **19 pending、0 matured、0 outcome artifact**。它只記 capture 層級 `personal_outcome_source_or_cost_incomplete`，沒有逐列缺件原因。

對同一隔離 QA DB 和年曆的唯讀 resolver probe 回傳 `missing_taiex_baseline_observation:2026-09-29`，沒有 endpoint 或 session dates。評估發生在決策日 01:13，當日收盤尚未發生；20 個交易日更未走完。年曆將 9/25、9/28 列為休市、9/29 列為預定開市；由 9/30 起算的第 20 個**計畫**交易日是 10/29，但本次收據未有 temporary-closure cache，不構成完整官方成熟日證明。resolver 在共同 session proof 前即退回 pending，尚未逐股檢查端點價與成本；因此不能把 capture 級合併 reason 解讀為「19 筆都只有時間待滿」。

以下日價來自同一 m11 隔離 DB 的 `MAX(日期)` 唯讀 SQL。每一列在當次評估均缺 9/29 決策日收盤與 20-session 端點觀測；`1441` 另有較早的觀測缺口。`待查` 不代表已證明缺價原因或成本失敗。

| 代碼 | 最近日價 | 逐筆狀態 |
| --- | --- | --- |
| 1569 | 9/24 | 未成熟；未進入逐股價／成本核驗。 |
| 1560 | 9/24 | 同上。 |
| 1295 | 9/24 | 同上。 |
| 1456 | 9/24 | 同上。 |
| 1708 | 9/24 | 同上。 |
| 1440 | 9/24 | 同上。 |
| 0053 | 9/24 | 同上。 |
| 1417 | 9/24 | 同上。 |
| 1463 | 9/24 | 同上。 |
| 1217 | 9/24 | 同上。 |
| 1418 | 9/24 | 同上。 |
| 1473 | 9/24 | 同上。 |
| 1539 | 9/24 | 同上。 |
| 0051 | 9/24 | 同上。 |
| 1240 | 9/24 | 同上。 |
| **1441** | **9/16** | 未成熟；9/17–9/24 的計畫開市日無該股日價列。停牌或 feed 缺漏未證。 |
| 1215 | 9/24 | 未成熟；未進入逐股價／成本核驗。 |
| 1324 | 9/24 | 同上。 |
| 1730 | 9/24 | 同上。 |

19 列均為 `legacy-fixed-round-trip-bp-v1` 的固定 **50 bp 假設**，`after_cost_profit_probability_status=unavailable`，委託金額與股數為 null。這不是逐檔實際成本證明；v3 evaluator 不採未綁定該 capture 的 liquidity evidence。m11 隔離 DB 為 `output/qa/personal_daily_product_20261006/personal_research_ui/m11/data/_test/sqlite/twstock.db`，SHA-256 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`，探查前後與 Stage C 收據相同；以 SQLite `mode=ro`、`PRAGMA query_only=ON` 查詢，未開啟正式 `D:` 資料庫。對 `1441` 需要另取得該期間原始日價及停牌／交易狀態，才能分清來源缺口。

## 接續路由與判定

1. 先把修補後的推薦 UI 精確節點與相鄰回歸列入下一個 frozen scoped route；依各測試的路徑契約分開 OS TEMP 與 repo-output basetemp，逐桶小範圍重驗，尤其是 calendar／DB fixture、`WinError 5` 和 R027 hash 節點。這些分組原因未釐清之前，不宜再以一次全套數字取代診斷。
2. 在下一個經官方日曆及當日來源可得時間確認的正常交易日，以**新隔離 root** 執行同日更新、同日推薦 snapshot、真 learning child、canonical 保存讀回與同 run retry；保存命令、環境、輸入／輸出 hash、child identity 和 terminal receipt。9/28 閉市 dry-run 不替代此證據。
3. 補 OS 前景 MainWindow 操作證據。Qt widget journey 已證明 m11 的個人模型啟用、影響推薦、保存讀回與停用回退，但未證真人可見桌面路徑。
4. 自然 20-session 到期後，以含臨時休市覆蓋的新鮮官方年曆與隔離來源逐筆核對起始價、終點價和成本綁定；缺件繼續 pending，不合成績效。樣本未成熟不妨礙研究模型個人使用，也不能聲稱已勝基準。

## 2026-09-29 後續小範圍驗證（基準 `8457560b`）

Luna Max 修補 `tests/test_position_health_transition_read_service.py` 的合成 fixture：原快取固定在 9/14 擷取，七天 TTL 到現在已過；沒有指定 `calendar_db_path` 時 fallback 會把快取目錄當 SQLite 開啟。修補保留七天 TTL 與早於觀察時點的合成 captured time，只在 evaluator 呼叫期間將日曆檢核時鐘固定為 `OBSERVED_AT`，並傳入 `tmp_path` 下的空白 QA SQLite。精確來源時間節點 **1 passed**，整檔隔離 **15 passed**，已到達 `source_available_at_after_observed` 斷言；沒有改 production。獨立 review 指出此測試僅覆蓋「觀察當時快取有效」的 as-of 情境，**不驗今天回溯執行時過期快取的行為**；正式 provider 仍按實際時鐘檢查 TTL、過期便 fail closed。該範圍已寫入 fixture 註記，不把測試通過解讀為 retrospective production 路徑完成。

路徑分流只重跑四個精確節點：MOPS batch、calendar raw custody 在 OS TEMP basetemp 各 **1 passed**；MOPS materializer 在 repo `output/qa` basetemp **1 passed**，其父目錄須先建立。這些節點各自驗證了對應 allowlist／repo-output 契約，未覆蓋原 188 個路徑症狀。

WinError 5 舊失敗桶的代表節點在目前 HEAD `6265ccea` 做了隔離重現：OS TEMP basetemp 下，`tests/test_allocation_base_expert_comparison.py::test_comparison_preflight_blocks_missing_replay_source_sidecar`（OOC expert staging）、`tests/test_portfolio_ml_out_of_core_pipeline.py::test_store_resume_hash_coverage_and_memory_budget`（OOC meta staging）及 `tests/test_formal_technical_raw_alias_repair.py::test_db_manager_guard_preflights_stale_and_incomplete_replace_before_delete`（raw-alias staging）共 **3 passed in 17.00s**；再以 repo-local `.tmp_wp5e` basetemp 重跑 expert 節點，**1 passed in 8.05s**。舊 raw receipt 中的四個 `os.replace` callsite 分別是 `ml_module/allocation_out_of_core_training_service.py:1740`（expert artifact directory）、同檔 `:3256`（meta artifact directory）、同檔 `:5215`（capacity checkpoint JSON）及 `data_module/formal_technical_raw_alias_repair.py:1064`（raw-alias stage directory）。目前代表重跑未重現 WinError 5；多個不同發布路徑與有限的舊錯誤訊息不足以判定共同根因，也不能據此聲稱舊錯誤已修復。此小範圍結果不改變舊 full-suite receipt 的 FAIL 裁定。

`tests/test_live_research_gap_cli.py` 的 `_run_capture` fixture 路徑根因已定位：`PROFILE=test` 時 `TWStockConfig` 會先將 roots 解析為 `data/_test`、`output/_test`；舊 helper 把這兩個已解析路徑直接傳給仍在 `PROFILE=test` 下執行的 CLI，子程序再加一次 `_test`，因此沒有讀到 seed position，觀察筆數為 0。helper 現傳遞其 parent base roots，讓 CLI 只解析一次；root 以 `%TEMP%\pytest_wp5_gap_root_<uuid>\pytest_basetemp` 作為 OS TEMP basetemp，首次因 basetemp 父目錄不存在而收到 WinError 3，建立 OS TEMP 父目錄後重跑整檔 **4 passed，exit 0**。首次結果是測試 setup 未完成，不計入測試結果。這項 fixture 修正與整檔通過不改變舊 full-suite FAIL。

WinError 5 的驗證只覆蓋三個歷史代表節點及 expert 節點的兩種 basetemp 位置；沒有重跑全套，也未確認舊失敗當時的 Windows handle、ACL 或防毒掃描狀態。當前 HEAD 與舊失敗間相關 OOC producer／測試支援檔案沒有 Git 差異，故目前通過不能作為已由程式碼修正消除問題的證據。正式 D DB 未讀寫。

R027 hash／readback 桶的 11 個舊 failures 在 `tests/test_r027_logical_time_gate.py` 都停於 `_frozen_direct_stable_identity()` 第 198 行：full-suite raw log 的實際 Direct runtime payload hash 為 `sha256:9e474c8fff9dcd5e594cbbfb5cf0579cc366ed0e99557fff6cfbc7c341ef4a6e`，固定值為 `sha256:0b23fbb44dc99c13f75c638aca1bc325f4585e714d018d2d8a223a15a20e7087`。這發生在 `_entry()` 建立 synthetic receipt 期間，早於 `gate.evaluate_case()` 與 SQLite readback，所以舊 11F 不是已觀察到的 DB bytes／readback 不一致，也沒有抵達 source-phase logical-time assertion。

目前 HEAD `97231b24` 以 OS TEMP 隔離 roots 重跑三個代表節點：`test_case_gate_keeps_main_db_bytes_exact_but_allows_separate_checkpoint_and_os_observations`、`test_case_gate_fails_when_sqlite_main_database_bytes_change`、`test_same_worker_pair_cannot_forge_consistent_final_logical_db_evidence[final_db_bytes]`，結果 **3 passed in 3.62s**；獨立讀取目前 payload hash 得到固定值 `0b23…`。環境為 `PROFILE=test`，`DATA_ROOT`／`OUTPUT_ROOT`／`DB_PATH`／`TEMP`／`TMP` 均指向 `%TEMP%\wp5_hashreadback_fb730a0f` 下的 QA root，pytest basetemp 為其 `basetemp` 子目錄。`fd76b4e8..97231b24` 之間，R027 測試、gate 與 15 個 Direct dependency 檔案沒有 tracked diff；舊 receipt 沒保存失敗當下的 payload 分項／載入模組 identity，故無法判定歷史差異來自 suite-order 狀態或其他未保留的執行環境。這表示舊失敗在當時程序中是真實的固定來源身份 guard mismatch，目前隔離節點則未重現；**不能據此宣稱已修復舊 full suite，也不能外推全套或正式資料 readback**。重跑只使用合成 pytest workspace，未讀寫正式 D DB；完整全套 FAIL 保持原裁定。

Runtime API／fixture 桶後續重驗：舊 `test_task_loop_07_contract.py::test_recommendation_selected_candidate_keeps_real_identity_without_inventing_one[saved-rec-001]` 與 `[None]` 兩節點的 test double 只有 `current_result_id`，缺 `current_execution` 與 verified-ID 事實；test-only fixture 改提供 execution 與 verified ID，並以 match／empty／mismatch 三種情境參數化，root 精確路由 **3 passed，exit 0**。這些情境以 mock 驗 verified-ID gate；真正 canonical readback 另由 m11 證據驗證，不由此 mock 代替。舊 `tests/test_pit_taxonomy_daily_source.py::test_configured_composite_capture_custodies_component_raw_files` 的 `reader_status` failure 在 OS TEMP 精確重跑 **1 passed**；它較像路徑症狀的判斷仍是推論，尚未證實根因。相鄰 `tests/test_task_loop_07_contract.py` 在上述 test-only fixture 修補後整檔於 OS TEMP 為 **18 passed、2 failed**，兩個失敗報 no-follow `WinError 5` 並落在 `C:\Users\archi\AppData\Local\Temp` 路徑；改用 repo `output/qa` basetemp 並同步設定 `TEMP`／`TMP` 後，該兩節點 **2 passed**。這只顯示該兩節點對路徑位置敏感，不確證 no-follow 根因；不改寫舊 full-suite FAIL。

證交所 [115 年開休市表](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html) 沒有列 9/30 休市；repo 9/28 23:15 UTC 擷取的年度 cache 將 9/30 列為計畫開市，效期至 10/5 23:15 UTC，但自列 `temporary_closure_coverage=not_covered`。這證明**排定開市**，尚未完成執行日臨時休市覆蓋與當日資料／同日 canonical pair 查核；9/30 真鏈不能預先記為通過。

該 cache 是 `output/paper_execution_eod_replay/calendar_cache/twse_holiday_schedule_2026_20260928T231502681965Z_30badfe7f239.json`，`content_sha256=sha256:18ebea06674a33447384fa83a12f03ca4ce292ed43a1bd3d91c4cdc92dcefcac`。唯讀 status 檢查顯示 Shadow 9/28 snapshot `passed`、同日 pipeline `failed`（含 `official_trading_calendar_unresolved_fail_closed`）；Formal 9/28 snapshot `passed`，但其 calibration-learning latest status 不存在。這些都不是 9/30 配對。Pipeline 的受控入口為 `scripts/scheduled/run_daily_recommendation_learning_pipeline.py`，會串接 quick update、snapshot、learning；BankTaiwan wrapper 為 `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py`。**仍缺經驗證的隔離資料根目錄 bootstrap**；不得用裸拷帶 WAL 的 SQLite 或指向正式 D 的可寫 updater 來補件。當日需先完成新隔離資料與來源時鐘核對，再執行 pipeline、wrapper dry-run、真 child、canonical 讀回與同 run retry，保留每步 receipt。這些命令目前只經原始碼檢視，尚未真實執行。

**目前裁定：WP5 尚未整體完成。** 受限整合與 m11 模型流程有可核對證據；全套測試、正常交易日真鏈、自然成效及 OS 前景 UI 尚未成立。MOPS prospective 來源仍需另行建立授權、來源時間、原始 hash、覆蓋及修訂證據，不能由每日快照直接升格正式 PIT。

## 9/29 真實日常鏈前置檢查與首次隔離備份中止

台北 9/29 收盤後，官方年度表與本地有效年曆 cache 都將 9/29 列為**排定開市**；該 cache 同時明記 `temporary_closure_coverage=not_covered`。現行 `OfficialTradingCalendar` 在沒有正向臨時休市 sidecar 時，仍會按有效年度表回傳開市；這是程式 gate 的行為，**不是「當日無臨時休市」的完整官方證明**。正式 SQLite 與既有 QA snapshot 的唯讀檢查中，`daily_prices`、`technical_indicators`、`market_indices`、`industry_indices` 四表最新日期均為 `20260924`，四表的 `20260929` 列數均為 0。這只描述兩份 DB 當時可查到的資料日期與列數，不證明官方發布／可得時間。另未取得可核對的官方 9/29 個股／TPEx 即時行情回應；現有正式／Shadow status 也沒有 9/29 同日 snapshot／pipeline canonical pair。因此本次沒有把 9/29 裁為正常日真鏈通過，也沒有啟動 updater、scheduler 或 learning child。

為準備新隔離資料根目錄，曾從已獲確認的 `D:/Min/Python/Project/FA_Data/sqlite/twstock.db` 以 SQLite `mode=ro`、`query_only=ON` 和 online backup API 建立 `output/qa/wp5_daily_seed_20260929_01/`。正式 DB 約 3.827 GB（934,504 個 4,096-byte pages）。首輪備份在約八分鐘後發現程序累計讀取約 1.8 TB、4.41 億次 read operations，目的 `twstock.db` 仍為 0 bytes、journal 512 bytes，且沒有成功收據；為避免持續無效讀取，已停止**本次啟動的備份程序**，保留隔離目錄供診斷。停止後正式 DB 與 WAL 的大小、修改時間仍與啟動前相同（DB 3,827,728,384 bytes、2026-09-28 12:45:09 UTC；WAL 0 bytes、12:55:10 UTC）。這是檔案層級觀測，不宣稱證明來源所有 bytes 未變。當次目的地不得用於後續 pipeline。

首次中止後，原規劃是先修正備份的進度可觀測性、停滯與總時限，再以合成資料回歸並獨立審查；原有 `output/qa/wp5_daily_seed_20260929_01/` 至今保留、不覆寫。本次後續改採已核驗、由 repo ignore 排除的 QA snapshot 作來源，另建全新 QA seed root，詳見下節；這不是第二次正式 D 備份，也不改變舊中止目錄的狀態。即使 snapshot seed 成功，仍須另完成外部 PIT／candidate DB 路徑隔離、當日官方臨時休市查核、當日行情可得時間及同日 canonical pair，才能執行正常日真鏈。

另以**同一個** `mode=ro`、`query_only=ON` 的 SQLite 監控連線，約每五秒讀取一次 `PRAGMA data_version`，得到 `2 → 3 → 4`；三次同時觀察的 DB／WAL 大小與修改時間均相同。後續另一段唯讀監控中，同一連線的 `data_version` 又由 `3 → 21`；依 [SQLite `data_version` 語義](https://www.sqlite.org/pragma.html#pragma_data_version)，讀值變動表示兩次讀取間有其他連線提交，這支持來源提交活動仍在持續，但不能識別提交者。檔案 metadata 穩定不足以證明來源閒置。這些變化支持首輪 backup 可能反覆重啟，但當時沒有 progress callback，尚不能確證首輪各次回退。**目前不是可確認的 writer-idle 時段，不進行第二次正式來源備份。**

## 2026-09-29 已驗證 QA snapshot seed（seed-only）

後續以固定且由 repo ignore 排除的 QA snapshot 建立新 seed root：`output/qa/wp5_verified_snapshot_seed_20260929_01/`。成功收據為 [`bootstrap_receipt.json`](../../output/qa/wp5_verified_snapshot_seed_20260929_01/bootstrap_receipt.json)，11,406 bytes，建立時間為 2026-09-29 12:08:21 UTC；`status=database_seed_created`、`source_mode=verified_qa_snapshot`。來源 snapshot 的上游收據 SHA-256 為 `15e1f66f496865f55f97e6e76d1bb291cb1cb842d42d29ee42b7e8905f5b0e83`，receipt 記錄來源檔案複製前後 identity 相同。目的 working DB 為 3,827,728,384 bytes；全檔 SHA-256 讀回值為 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`，SQLite `quick_check=ok`。本次 seed 複製的是已核驗 QA snapshot；receipt 記錄未直接開啟或 stat 正式 D 路徑。首次正式 D 備份中止目錄保持原狀，沒有以此方式重試。

未來函數／日期檢查的範圍只涵蓋 receipt 所列四表 `daily_prices`、`technical_indicators`、`market_indices`、`industry_indices` 各自選定的 `日期` 欄：其最大日期均為 2026-09-24，不晚於 2026-09-28 日期上限。`daily_prices` 與 `technical_indicators` 的候選 `Date`（REAL）欄未解析或掃描；其他資料表的日期欄也未掃描。receipt 明確標示 `lookahead_self_check.status=partial`、`full_database_future_date_absence_established=false`，因此不能宣稱完整資料庫已排除未來日期，更不構成官方 PIT。這份 seed 的 `ready_for_daily_pipeline=false`、`daily_chain_preflight_complete=false`；官方 calendar cache、PIT sidecars 與外部 candidate DB path 未由 bootstrap 複製或完成 freshness／路徑 preflight。

bootstrap 子程序約執行 14.5 秒並產生上述成功 receipt；外層 Python／PowerShell wrapper 在將 UTF-8 中文 JSON 寫入 CP1252 stdout 時退出 1，且未保留子程序 return code。因此不宣稱 bootstrap CLI／wrapper exit 0；seed 成功的判讀依據是 bootstrap receipt 的成功狀態、全檔 SHA-256 讀回核對、SQLite quick check 與目的檔存在。這次只有 bootstrap seed，沒有執行 updater、recommendation snapshot 或 learning child，也沒有這些步驟的 receipt；沒有證明 9/29 同日更新或正常日真鏈通過。

新模式的合成測試為 **14 passed**；root 重跑為 **14 passed、1 個 pytest cache warning**；獨立 seed-only review 結論為 **GO**。此 GO 僅接受該隔離 seed 方式，不延伸到 daily-pipeline preflight、正式資料、官方 PIT 或正常交易日真鏈。舊正式來源備份中止、`data_version` 外部提交活躍、未取得可核對的 9/29 個股／TPEx 即時行情回應及同日 canonical pair 缺件等歷史裁定均保留。

## 2026-09-29 正常日 pipeline preflight（NO-GO；未執行 dry-run）

雖已完成 seed-only QA snapshot 複製，收據仍標 `ready_for_daily_pipeline=false`，而且四張受檢表在 9/29 都沒有資料列。本次未執行 quick updater，也未執行 pipeline dry-run。官方來源觀測彼此不一致：TWSE OpenAPI [`FMTQIK`](https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK) 與 [`MI_5MINS_HIST`](https://openapi.twse.com.tw/v1/indicesReport/MI_5MINS_HIST) 約於 12:12 UTC 可讀，但回應最新日期僅到 9/24；TWSE [TAIEX 5 分鐘 HTML](https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?date=&response=html) 有 9/29 指數 OHLC 列。後者不能代替 9/29 個股或 TPEx 行情的來源可得時間證明；尚未驗證官方個股／TPEx 來源是否可用，也未完成當日臨時休市 closure gate。不能由一筆 TAIEX 指數列推論全市場 9/29 行情可用。

環境隔離亦未達執行條件。首次 no-go 檢視時，`scripts/scheduled/run_daily_data_update_quick.py` 的 `_default_calendar_cache_path()` 指向 repo-level `output/paper_execution_eod_replay/calendar_cache`，quick-updater 建立 `OfficialTradingCalendar` 時未傳入 `temporary_closure_path`，不能證明 QA run 已套用明確的 9/29 日曆／臨時休市檢查；後續 calendar injection 的窄範圍修補與限制見下節。該 quick updater 會呼叫 candidate DB path helper；`data_module/phase3c_backfill_runner.py::configured_candidate_db_path()` 在 process environment 缺少 `PHASE3C_CANDIDATE_DB_PATH` 時會讀取 HKCU 使用者環境值，pipeline 子程序環境以 `os.environ.copy()` 為基礎，沒有清除 PIT／candidate 外部路徑變數。因此只指定 QA `DATA_ROOT`／`OUTPUT_ROOT` 不能證明所有讀寫路徑都留在 QA root。另 `PROFILE=test` 會對明確 data/output roots 再加 `_test`；`PROFILE=prod` 搭配 QA roots 僅是待完整環境隔離後再審查的候選配置，沒有執行。

最終 preflight 判定 **NO-GO**：先明確 redirect／隔離 candidate DB 與 PIT 外部路徑，核對實際解析後所有 data/output/DB 路徑，再取得可核實的官方 9/29 個股與 TPEx source availability 及 closure gate 證據，才可考慮 quick updater 或 pipeline dry-run。現有來源回應日期不一致、seed `ready=false`，且無 updater／recommendation snapshot／learning child 收據；因此不宣稱 9/29 同日更新、normal-day pipeline 或日常真鏈成功。既有 full-suite FAIL 與前述中止備份裁定均不變。

## 2026-09-29 calendar injection 後續小範圍驗證

`run_daily_data_update_quick.py` 新增 `--calendar-cache-path` 與 `--temporary-closure-path`；daily recommendation learning pipeline 也將對應旗標傳給 quick child。未指定旗標時保留舊預設行為。明確 QA override 用來指定並驗證受影響年度 cache，並關閉隱含 online probe；missing／invalid、`not_captured` 或 open-session closure evidence 缺件均 fail closed。事件型 temporary-closure sidecar 只有正向事件可成為 `verified`；沒有事件列不是「已證明無臨時休市」的負向覆蓋。獨立 reviewer 確認，一般 open day 的 event-only sidecar 狀態必然為 `not_captured`，所以即使明確指定 closure override，正常開市日目前仍必然 fail closed。單獨指定年度 calendar cache 可驗年曆輸入，但不構成完整 closure gate；還需後續 verified negative-coverage receipt 或同日官方市場資料佐證。這是準備性注入接線，不能宣稱已可跑正常日鏈。

測試方面，作者 focused calendar route **5 passed**、quick updater 整檔 **25 passed**；root 重跑 quick updater **25 passed**，pipeline 旗標傳遞測試 **2 passed**。兩測試檔 `tests/test_recommendation_calibration_contract_guards.py` 與 `tests/test_scheduled_data_update_runner.py` 合跑為 **48 passed／7 failed**；7 個失敗均回報 snapshot stdout artifact 類症狀，但逐項基準等價對照未完成。僅一個代表性的 pipeline same-day-reuse 節點在 patch 前基準 `fef56b93` 與 patch 後以相同長度 basetemp 重跑，兩版都以相同訊息失敗；改用短 basetemp 時兩版皆通過。其餘失敗沒有逐一以 patch 前後基準做等價對照，因此不能把代表節點結果外推到全部 7 項，也不能改寫成兩檔全通過或 full-suite 通過。獨立 reviewer 已確認前述 closure gate 限制，原 pipeline preflight **NO-GO** 仍持續。

此外，quick updater 在 calendar gate 前仍會產生 logging、capacity 與 config 目錄等 operational writes；新增旗標不是唯讀 preflight。本輪未執行真實 updater 或 pipeline；candidate DB／PIT 外部路徑隔離仍未解，沒有正常日更新、同日 snapshot／learning child 或 9/29 日常真鏈通過證據。

## 2026-09-29 candidate update 明確 skip（preparatory only）

Quick updater 新增 `--skip-candidate-update`；daily recommendation learning pipeline 可接收同名旗標並傳給 quick child。指定時，quick runner 在第一次呼叫 `configured_candidate_db_path()` 前設 `candidate_db_path=None`，不查 process `PHASE3C_CANDIDATE_DB_PATH` 或 HKCU；若流程到達 candidate step，收據記為 `skipped`、reason=`operator_requested_candidate_update_skip`，不呼叫 `UpdateService.update_phase3c_candidate_range`。未指定旗標時仍走原有設定解析與 candidate 更新路徑。這只略過候選 DB 更新，不略過其他市場／技術更新，也不是唯讀 preflight。

root 對 quick updater 整檔重跑為 **26 passed**，pipeline child invocation 路由 **2 passed**；兩支程式的語法檢查及 `git diff --check` 通過。若 capacity preflight 或 calendar gate 提早 return，流程會在後段 candidate step 收據之前結束，故可能沒有 candidate `skipped` step；但明確 skip 分支仍不解析候選路徑、不呼叫 updater。另有 pipeline main 整合測試在 recommendation snapshot stdout artifact create-only write/readback 階段失敗；移除 skip 旗標後同樣失敗，不能歸因於此 skip 變更，也不計入上述 child invocation 通過數。

這是 daily-chain 的準備性隔離措施：它只避免 candidate path resolver 及候選 writer，沒有隔離或證明外部 PIT 路徑、temporary-closure sidecar 或當日 source-time availability。未執行真 updater、pipeline、snapshot／learning child 或正常日真鏈；9/29 同日資料、closure gate、canonical pair 仍未驗，原 preflight **NO-GO** 與 full-suite FAIL 裁定不變。

## 2026-09-29 seed-only daily-chain preflight 與官方回應觀測（仍 NO-GO）

唯讀 preflight 由 `data_module/wp5_daily_chain_preflight.py`、`scripts/qa_wp5_daily_chain_preflight.py`、`tests/test_wp5_daily_chain_preflight.py` 組成；root focused tests **11 passed**、compile 通過。它未接入 scheduled runner，也不呼叫 `TWStockConfig`、runner/bootstrap main、網路抓取或 candidate registry；只輸出 JSON，不建立檔案，且檢查結果為 `candidate_db_environment_read=false`、`windows_registry_read=false`。固定 seed 的實際 CLI 為預期阻擋結果：exit **2**、`seed=verified`、`isolation=bounded_verified`、`day=blocked`，缺 `annual_calendar_cache_missing`、`temporary_closure_event_receipt_missing`、`official_source_time_receipt_missing`。working DB 以 SQLite `mode=ro` 開啟並確認 `query_only=1`，`st_nlink=1`、檔案 identity 穩定、未見 sidecar；全檔 SHA-256 為 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`。CLI stdout 未保存為 durable artifact，沒有固定可讀回的 preflight 收據或觀測時間。

Preflight 拒絕 reparse path component，並在雜湊與唯讀 SQLite 開啟前後檢查 working DB `st_nlink==1` 及檔案 identity；隔離判定僅涵蓋明列環境欄位。這些 path／link-count 檢查不與稍後 runner 的 SQLite handle 綁定，不能防止兩者之間的並行 rename、junction 或 hardlink race，也未證明未盤點的其他環境／持久路徑來源。這只是 seed 與 bounded isolation 的唯讀檢查，不是 runner-ready；正常日真鏈仍 **NO-GO**。

稍後官方 endpoint 的 9/29 HTTP 查核在記憶體中的回應找到當日列，補充了上段較早「未取得可核對回應」的狀態。下列 metadata 由 fetcher 回報；原始 bytes 均未落檔、無法獨立讀回核驗，不構成 durable custody。Capture end 是本次觀測時間，不是官方發布時間，也不能單獨證明決策時點的 source availability。

| 官方 endpoint | 回應中的當日資料 | 回報的原始回應 metadata |
| --- | --- | --- |
| TWSE [MI_INDEX](https://www.twse.com.tw/exchangeReport/MI_INDEX?date=20260929&type=ALLBUT0999&response=html) | 9/29 市場資料列 | 2,164,160 bytes；SHA-256 `2e9f772773d1f79a93152be0ea2b222feb15a998383a10d7f79faa6f34787db9`；end `2026-09-29T14:19:36.8761941Z` |
| TWSE [STOCK_DAY 2330](https://www.twse.com.tw/exchangeReport/STOCK_DAY?date=20260901&stockNo=2330&response=html) | 115/09/29 台積電列；收盤 2,475、成交 26,893,348 股 | 17,190 bytes；SHA-256 `2926bfc62b026eab294d5a7140a723cd62b9814cf83a5e0c9f901ea47b93dd92`；end `2026-09-29T14:19:37.1566648Z` |
| TPEx [dailyQuotes](https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date=2026%2F09%2F29&id=&response=json) | 115/09/29；893 家發行人、11,730 筆 | 1,760,630 bytes；SHA-256 `41e64aef784e9e4b0672330800acecd5d2b06d7d7f95e51a5b391eb4f5998c4e`；end `2026-09-29T14:31:43.9501614Z` |
| TPEx [tradingStock 6488](https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code=6488&date=2026%2F09%2F01&response=json) | 115/09/29；成交 9,157 張，OHLC 940／964／930／945 | 2,273 bytes；SHA-256 `0783cef9dceb93e0d7326ba8501a675b8a931ee0f4fe7528762e205fde0eb335`；end `2026-09-29T14:31:38.5697489Z` |

此記憶體內觀測補充了先前「未取得 9/29 個股／TPEx 回應」的狀態，但不補 durable custody、官方發布時間、source-time receipt、closure evidence 或同日 canonical pair，不改變 preflight blocked／真鏈 NO-GO。下一包需以 create-only 保存原始回應與 request／response metadata，再由 validator 核對 hash、交易日期、schema 及來源時間；在此之前不可視為正式 PIT 或日常鏈輸入證據。

## 2026-09-29 m11 OS 前景隔離嘗試（未驗）

新 QA run 為 `output/qa/personal_daily_product_20261006/personal_research_ui/wp5_os_m11_20260929T103544Z/`，`prepare` 成功並保留 `receipts/isolation_manifest.json`，manifest SHA-256 `e814cfcc089038f4f281793d87b81428b449b66fa0dcb68684bd2dd646468b49`。隔離 working DB 位於 `data/_test/sqlite/twstock.db`，SHA-256 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`；manifest 記錄其與來源檔案身分分離且 SQLite `query_only=true`。Learning root `output/qa/pc-fit-v7/recommendation_learning` 的唯讀 tree pin SHA-256 為 `3b84158f9ab5edb9420fbcbbc427f0d80ea675fa13a5a741a26824fe8d0f1105`。正式 D 未寫，QA run 保留。

隔離 launcher log 指向該 run 的 `data/_test` 與 `output/_test`。Windows process 欄位顯示 MainWindowTitle `個人研究 QA｜隔離資料工作區`、`Responding=True`；但 `@oai/sky.list_apps()` 與 `list_windows()` 都沒有回傳唯一可操作的 Window。依 fail-closed 停止 UI 操作，未向 UI 點擊或輸入任何內容；故沒有 OS screenshot、截圖時間／路徑／hash，也沒有 launch 或 `visible_mainwindow` receipt。收到 Ctrl+C 後 launcher exit code `1`，run 的 receipts 目錄只有 isolation manifest，隔離 policy 檔也未建立。

候選 `rec-cal-3f8b2c276ef316e28de3806d` 未在 UI 啟用；19 列推薦與 6000 bp 顯示、canonical 保存／讀回、停用至 `rule_only`、版本回復及相關 fresh proof 均未執行，全部 m11 前景 model journey 仍未驗。下一步須有可由 `@oai/sky` 唯一 target 的互動桌面 Window，或採用人工可見操作流程後再重驗；未取得該證據前不得宣稱 OS 前景驗收通過。
