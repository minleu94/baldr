# Continuity Review Workbench R1 QA Evidence

> 日期：2026-09-15
> 性質：R1 工程驗證紀錄；本文件不授予正式投資、排程器、交易或自然 evidence credit。
> 參考：`CONTINUITY_REVIEW_LOOP_GAP_AUDIT_2026_09_15.md`

## 驗證範圍

R1 只處理既有 decision-continuity Journal 的唯讀投影與精確下鑽：

- Portfolio 只有在 `source_type=recommendation_result`、保存結果 JSON 的 `result_id` 相符，且結果內恰有一筆相同 `stock_code` 時，才填入 `ResearchStockContextDTO.result_id`。
- `backtest_run`、`strategy_version`、`user_declared_research`、手動或未標型的 `source_id` 不會升格為推薦結果 identity。
- Workbench 直接唯讀讀取 `output_root/portfolio/journal_entries.jsonl`；不建立 `JournalService`、不新增 reminder table／JSONL／registry／index，也不在缺檔讀取時建立目錄。
- 唯一 candidate key 是 `(result_id, stock_code)`。每列保留 intent、reminder/due status、revision、source snapshot、decision date 與 source trace。
- `next_review_at` 以帶時區值解析並正規化到 `Asia/Taipei` 比較；`scheduled`、`due`、`overdue`、`invalid` 分開呈現。
- 歷史 `as_of` 只採用 `created_at <= as_of` 的 revision；完整 Journal stream 仍先做 chain／duplicate／event conflict 驗證。未來改期、撤銷或意向變更不會改寫過去 projection。
- Workbench row-specific drilldown 只把選取列的 exact context 交給既有 shared stock research callback；不重算 outcome、不標記完成、不清除提醒、不自動寫 Journal。

## 唯讀 projection 與 identity 負向矩陣

測試檔：`tests/test_continuity_review_workbench_r1.py`

這些測試均使用 pytest `tmp_path` 下的隔離 JSONL／推薦結果 JSON，屬於工程 fixture，不是正式資料，也不代表自然成熟 outcome：

1. 原本 `accepted` + 已到期 review，在 `as_of` 之後追加 `skipped`／改期；讀過去仍得到原本 `accepted`、原 reminder 與 `due`，讀現在才看到新的狀態。
2. 相同 instant 的 UTC 與台北時間查詢得到同一 `Asia/Taipei` 時間與 `due`。
3. `cleared` 發生在歷史 `as_of` 之後時，過去仍保留 reminder；清除後的 current projection 不再產生 row。
4. naive／空白／格式錯誤 `next_review_at` 產生 `invalid` row 與 diagnostic，不猜測時間。
5. 缺檔、未知 identity、malformed UTF-8、nested／outer identity conflict 與 chain conflict 均 fail closed，回傳 diagnostic，不讓 UI background boundary 裸例外。
6. Composer 暴露 exact result／stock、intent、status、revision、snapshot hash 與 read-only flags。
7. Workbench 選取第二列時，callback 收到第二列的 `result_id`／`stock_code`，不會回到 `candidate_symbols[0]`。
8. Portfolio 只接受保存結果 JSON 內的唯一 exact recommendation row；其他來源與 stock mismatch 都回傳空 `result_id`。
9. Evidence 的 `source_snapshot_id` 只作為已由 `source_id`／`metadata.source_result_id` 識別出的 Recommendation root 的一致性檢查，不可單獨 join：同 snapshot 不同 result、snapshot-only、root 缺 snapshot 的 snapshot-only row 都不會誤連；正確 result + 不同 snapshot 則 fail closed 為 conflict；合法 result + 相同 snapshot 才 linked。

已執行：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_continuity_review_workbench_r1.py -q -o addopts=
8 passed
```

## Producer-backed shared loop 整合證據

測試檔：`tests/test_continuity_review_workbench_r1_integration.py`。這不是只注入 callback 的測試，而是以隔離的 `tmp_path` 實際串接既有 producer／repository／composition／Qt view：

| 節點 | 實際驗證 |
| --- | --- |
| Recommendation | `RecommendationRepository.save_result` 保存 R1、R2、R3；R1/R2 同為 2330，R3 含 2330 與 2317。 |
| Evidence | `EvidenceEventRepository.insert_event` 保存 4 個 exact candidate event；5 日結果為 linked／ready，10 日為 linked／pending，20/60 缺資料保持 unknown。 |
| Journal continuity | `JournalService` + `DecisionContinuityController` 對四個 exact `(result_id, stock_code)` 執行 accept + schedule；Workbench 只讀 projection。 |
| Workbench | `WorkbenchSourceService` 先驗證 historical `decision_date` + live continuity clock，再以明確 `continuity_as_of` 重播 due；四個 exact reminders 進入真正 review table。主摘要為中文股票／研究意向／台北 cutoff／原因，technical identity 留在詳情。 |
| Shared report／Journey | 選取 R1:2330 後，既有 shared callback 建立 `ResearchStockContextDTO`；shared report、Journey、controls 都收到 R1:2330 與同一 snapshot hash，不以同股第一筆候選回退。 |
| Read-only boundary | click 前後 Journal bytes／SHA-256 不變；未按 controls 前不會標記完成、清除 reminder 或寫入 Journal。 |
| Explicit action | 透過 Journey 既有「設定下次檢視」button 改期，產生新 head revision；另一個獨立 Python process（`timeout=10s`）讀回相同 candidate、原始 `accepted` intent、新 revision id／next_review_at／snapshot hash。 |

整合與 busy-close 測試執行結果：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_continuity_review_workbench_r1.py tests\test_continuity_review_workbench_r1_integration.py -q -o addopts=
9 passed
```

Busy close 使用 `scripts/qa_continuity_review_workbench_busy_close.py` 的獨立 child process。probe 以 `worker_started Event → UI 單次 close/cancel → release Event → dialog.finished → app.exec()` 握手，所有等待都有界；成功條件不使用 terminate／kill，也不以固定 sleep 代替 busy 證據。

本輪 acceptance artifacts：

- Workbench 實際提醒表（1366×768，含完整 header、4 筆中文 due reminder、選取後右側 cutoff／研究意向詳情）：`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\continuity_review_workbench_r1_1366x768.png`
- Shared Journey／controls（1366×768，5 日 ready、10 日 pending、20/60 unknown、R1:2330 identity）：`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\continuity_review_journey_r1_1366x768.png`
- Busy close receipt（child PID、busy 時 close、finished、`app_exec_returncode=0`、外部 `process_exit_code=0`）：`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a4d9-cc9e-7a21-937f-91c31fbe1bdb\continuity_review_busy_close_receipt.json`

## 既有回歸證據

R1 變更後一併驗證既有 Workbench composer/source、Qt Workbench、Portfolio、continuity controller：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_continuity_review_workbench_r1.py tests\test_workbench_read_only_composer.py tests\test_workbench_source_service.py tests\test_ui_qt_workbench_view.py tests\test_ui_qt_portfolio_view.py tests\test_decision_continuity_controller.py -q -o addopts=
93 passed
```

既有 shared Journey regression 另以 `tests/test_decision_outcome_journey.py` 執行，結果為
`17 passed`；Update Tab 強制回歸為 `84 passed`，`scripts/qa_validate_update_tab.py` 為
`25 passed／0 failed／4 skipped`。

## 全域 pytest 結果與範圍分類

既有全域 session 已完成，結果為 `5444 passed, 5 skipped, 12 failed`，耗時
`1584.29s (0:26:24)`。這是後續 targeted 修正／其他 agent dirty 變更前的 session snapshot；本輪不重跑全域。
以下保留每個 failure node 與目前已做的 targeted recheck，分開「已由 stack／檔案 ownership 確認的性質」與
「尚未判定是否由其他 dirty lane 引入」，不把它們統稱為範圍外：

- 清冊／治理 3 個：`tests/test_audit_test_inventory.py::test_audit_test_inventory_passes_and_reports_zero_missing`、
  `tests/test_audit_test_inventory.py::test_audit_test_inventory_cli`、
  `tests/test_full_app_healthcheck_test_inventory.py::test_all_python_files_in_tests_are_registered_exactly_once`。
  全域當時觀察到 25 個未註冊測試檔與 count drift；目前唯讀 audit 在補登本輪 2 個測試後仍有 24 個未註冊檔、
  4 個 count drift（total `805` documented vs `809` actual）。這是可確認的 shared inventory governance blocker，
  其餘檔案由其他 dirty lane 所有，本輪只登錄自己的 R1 測試。
- ML／calendar 4 個：
  `tests/test_ml_forward_scheduled_wrapper.py::test_forward_calendar_uses_verified_cache_without_network` 目前仍回傳
  `(None, 'lacks_verified_official_evidence')` 而非預期的 cache-open；
  `tests/test_ml_shadow_boundary_cli.py::test_shadow_boundary_cli_passes_repository` 目前 `main([])==1`，報告列出
  20 個 ML／production import boundary violations；
  `tests/test_ml_shadow_dependency_boundary.py::test_repository_respects_ml_shadow_dependency_boundary` 同樣仍有 20 個
  violations；
  `tests/test_paper_daily_execution_producer.py::test_real_paper_consumer_reads_hash_bound_calendar_cache` 目前為
  `status='blocked'`，在 network guard 下記錄 `valid cache must be consumed before network`，預期為
  `machine_verified_candidate`。stack／檔案 ownership 可確認這是 ML shadow／official calendar lane；是否由其他 dirty
  變更造成，未由本輪 full session 單獨判定，維持 fail-closed 並交由該 lane owner triage。
- Sector 3 個：全域 snapshot 曾在 `app_module/industry_strength_service.py:870` 看到 `KeyError: 'market_scope'`；
  `test_industry_strength_uses_market_sessions_without_stretching_missing_index_endpoint`、
  `test_industry_strength_aligns_coverage_to_twse_and_reports_mapping_gaps`、
  `test_industry_strength_ignores_future_observations_and_unknown_mapping_is_not_historical` 的目前 targeted rerun 為
  `3 passed`。因此這 3 個是已由後續 state 消除的 stale full-session failures，不列為 R1 現存 blocker；實際修復 ownership
  不在本輪 R1 檔案內。
- Stock Research 2 個：全域 snapshot 的 service failure 是 Windows `WinError 32` unlink temporary `twstock.db`；
  UI failure 是 advice fixture token assertion 與 PySide teardown 的 deleted-button stderr。本輪 targeted rerun 為
  `tests/test_stock_research_report_service.py::test_normal_readback_is_pit_bounded_and_uses_existing_advice` 與
  `tests/test_ui_qt_stock_research_report.py::test_report_view_reads_real_service_and_renders_missing_ml` 共 `2 passed`。
  UI 測試現改驗證 typed `advice.status='unavailable'`、`recommendation is None`，及實際 fail-closed 限制文案
  「尚未選定原始推薦來源；不會以同股或最新結果猜測。請回到推薦分析保存結果，或明確選擇原始推薦來源。」；
  這確認是文案／fixture drift，不是錯誤 Advice。原 full-session stack 與目前 targeted state 不足以判定其餘 teardown
  痕跡是否由其他測試污染，故不再延伸修 production。

上述紀錄不改變本輪 focused regression 與 9 個測試的合併驗收結果；正式成熟度／自然 evidence 仍不因
fixture 通過而放行。

## 自然資料／正式成熟度界線

本輪沒有以正式 output、Evidence DB、Portfolio ledger 或實際市場資料宣稱成熟度；沒有把 fixture 的 `due`、`accepted` 或 dummy result 當成自然證據。R1 只驗證：

- 有正式保存的 recommendation result 與 exact candidate 時，能安全傳遞 identity。
- 有既有 Journal revision 時，能安全且可追溯地讀取 reminder 狀態。
- 缺資料、未知 identity、provenance conflict 或 stream corruption 時，會降級而不補值。
- 正式 5／10／20／60 maturity、Evidence outcome、personal holdings 與 natural evidence 仍由既有 shared Journey／read models 各自負責；R1 不建立第二套 outcome 計算或 credit。

因此本文件不是 V4／V5 closeout，也不是 scheduler approval、broker readiness、投資有效性或 production promotion 證明。`ResearchFallbackPacket.revisit_date` 仍是自然 evidence maturity 的唯讀提示，與 user `next_review_at` 分開。

## 變更與唯讀安全檢查

- 新增 `app_module/continuity_review_projection.py`，只 open existing JSONL read-only；不呼叫會建立目錄的 writer。
- Workbench source／composer／DTO／Qt view 只增加 projection 與 exact callback routing；reviewed session state 仍是 session-only，不代表完成。
- `DecisionOutcomeJourney` 的 evidence join 只補上既有 Recommendation root snapshot 的一致性判定；result discriminator 仍是必要條件，未放寬 legacy journal／ledger／trade join。
- Portfolio identity guard 不改 Portfolio、Journal、Recommendation、Evidence 或 DB 資料。
- 測試 fixture、截圖與 receipt 都在隔離／本機 QA 路徑；不得當成正式資料或自然 outcome credit。
