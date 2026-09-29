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
| hash／readback mismatch | 11 | R027 logical-time gate 等節點未重驗；應循 R027 自身收據與路由判讀。 |
| runtime API／fixture mismatch | 7 | 兩個既有 test-double spy 缺口已在後續四節點路由 **4 passed**；其餘 `current_execution`／`reader_status` 等未逐項排除。 |
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

路徑分流只重跑四個精確節點：MOPS batch、calendar raw custody 在 OS TEMP basetemp 各 **1 passed**；MOPS materializer 在 repo `output/qa` basetemp **1 passed**，其父目錄須先建立。這些節點各自驗證了對應 allowlist／repo-output 契約，未覆蓋原 188 個路徑症狀。`test_live_research_gap_cli.py::test_capture_cli_confirm_writes_tmp_db` 即使改成含 `pytest` 的 OS TEMP 路徑越過 production-like DB guard，仍因 `gap_observations_created=0` **1 failed**；它是待查行為問題，不能算路徑修復。原始完整全套結果維持 FAIL。

證交所 [115 年開休市表](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html) 沒有列 9/30 休市；repo 9/28 23:15 UTC 擷取的年度 cache 將 9/30 列為計畫開市，效期至 10/5 23:15 UTC，但自列 `temporary_closure_coverage=not_covered`。這證明**排定開市**，尚未完成執行日臨時休市覆蓋與當日資料／同日 canonical pair 查核；9/30 真鏈不能預先記為通過。

該 cache 是 `output/paper_execution_eod_replay/calendar_cache/twse_holiday_schedule_2026_20260928T231502681965Z_30badfe7f239.json`，`content_sha256=sha256:18ebea06674a33447384fa83a12f03ca4ce292ed43a1bd3d91c4cdc92dcefcac`。唯讀 status 檢查顯示 Shadow 9/28 snapshot `passed`、同日 pipeline `failed`（含 `official_trading_calendar_unresolved_fail_closed`）；Formal 9/28 snapshot `passed`，但其 calibration-learning latest status 不存在。這些都不是 9/30 配對。Pipeline 的受控入口為 `scripts/scheduled/run_daily_recommendation_learning_pipeline.py`，會串接 quick update、snapshot、learning；BankTaiwan wrapper 為 `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py`。**仍缺經驗證的隔離資料根目錄 bootstrap**；不得用裸拷帶 WAL 的 SQLite 或指向正式 D 的可寫 updater 來補件。當日需先完成新隔離資料與來源時鐘核對，再執行 pipeline、wrapper dry-run、真 child、canonical 讀回與同 run retry，保留每步 receipt。這些命令目前只經原始碼檢視，尚未真實執行。

**目前裁定：WP5 尚未整體完成。** 受限整合與 m11 模型流程有可核對證據；全套測試、正常交易日真鏈、自然成效及 OS 前景 UI 尚未成立。MOPS prospective 來源仍需另行建立授權、來源時間、原始 hash、覆蓋及修訂證據，不能由每日快照直接升格正式 PIT。
