# 跨頁決策旅程驗收計畫（2026-09-15）

> 性質：bounded acceptance plan／唯讀準備文件。這不是新的正式成熟度、scheduler、broker、交易或投資有效性 gate，也不授權修改程式、正式資料、排程器或 Manual。
>
> 本計畫從已接受的 R1／Position Health／`user_declared` 邊界出發，只處理其外的跨頁整合缺口：市場 → 產業 → 個股 → 觀察清單／持倉 → Workbench → Decision／Outcome 的 identity round-trip、降級呈現、重啟讀回與關閉生命週期。

## 1. 驗收起點與範圍界線

### 1.1 已接受、只作 oracle 的基線

| lane | 已有證據 | 本計畫不重做的部分 |
|---|---|---|
| Continuity Review Workbench R1 | `docs/06_qa/CONTINUITY_REVIEW_WORKBENCH_R1_QA_2026_09_15.md`；producer-backed integration `9 passed`，focused regression `93 passed`；另有 1366×768 截圖與 busy-close receipt | 既有 Journal 唯讀 projection、`(result_id, stock_code)` candidate key、R1 row-specific callback、`next_review_at`／`due_status`、Journey／controls exact readback 與 read-only bytes 不變 |
| Position Health H | `docs/06_qa/POSITION_HEALTH_INCREMENT_1_QA_2026_09_15.md`；read service、Portfolio／Workbench typed projection 與 1366×768／1700×1100 presentation 已驗收 | `position_id`／cohort／receipt hash／source snapshot 的 exact read model、`research_only`、Paper row 與人工持倉分離、缺 receipt／future／stale 時的 `WATCH`／unknown 邊界 |
| `user_declared` I | `docs/06_qa/USER_DECLARED_HOLDING_RESEARCH_INCREMENT_2_QA_2026_09_15.md`；核心與 Portfolio suite `43 passed`，writer／reader subprocess 及 close lifecycle 已驗收 | `holding_id + revision_number`、聲明成本 Decimal、PIT source check、`research_only`、`entry_lineage=unproven`、`formal_credit=false`、`broker_execution=false` 與聲明持倉 tab 的安全邊界 |
| C canonical phase | `719cf7a4`；bounded canonical runner／training lineage／cutoff／ML boundary 已接受 | 不把 C 的下一個 P1 next-day inference／projection provenance 未完成誤寫成已完成，也不在本文件修改 C |
| L official taxonomy | 既有 reader／producer contract 可作 input contract；官方 raw producer／v3／publisher／reader／caller 的端到端 source chain 仍待完成 | 不把 current mapping、fixture 或 dirty working-tree artifact 宣稱為正式 source closeout，也不在本文件修改 L |

R1 的 exact reminder、head、Journey、controls readback 已是本計畫的 acceptance oracle；後續只驗證它們能否在真正的跨頁入口與重新啟動後仍收到同一個 identity，不重新建立第二套 outcome 或 reminder store。

### 1.2 只驗收 R1 以外的缺口

本計畫的剩餘目標是：

1. 用一次受控的完整來源資料流，驗證市場／產業的來源脈絡能到達個股報告，明示保存後的 Recommendation `result_id` 能再經 Watchlist／Portfolio／Workbench 回到同一個 Journey candidate。
2. 用缺資料、future、stale、identity conflict 與同股多 result/date，驗證每一頁都 fail closed，不以股票代號、日期、同 snapshot 或第一筆候選猜接。
3. 確認 `user_declared`、Paper Position Health、formal Recommendation／Outcome 三條 lane 的身份與 UI boundary 不互相升格。
4. 在新 process／新 session 中讀回同一份 artifact，並在背景 worker busy 時只收到一次 user close，讓 `app.exec()` 自然結束。

不包含：新 storage、新 global gate、新 outcome 計算、新 portfolio trade、broker execution、資料重建、正式資料回填、C/L producer implementation、ML adoption、自然 evidence maturity 或 V6 outcome claim。

## 2. 現行入口與 identity 傳遞盤點

跨頁驗收必須追蹤下列 typed identity，而不是只比對畫面上的股票名稱：

```text
stock_code
result_id                         # 只有已保存且 exact 的 Recommendation 才可提供
identity_status                   # linked / unknown / unlinked / conflict
decision_date / data_date
source_snapshot_id / source_snapshot_hash
source_id / source_kind / source_workspace
industry source_version / mapping_version / mapping_observed_date
candidate_key = (result_id, stock_code)
continuity revision_id / reminder_revision_id / due_status
position_id 或 holding_id          # H／I 的獨立身份，不得轉成 result_id
```

| 節點 | 已有實際入口 | 目前 identity 語意 | R1 之外的驗收缺口 |
|---|---|---|---|
| 市場總覽 | `app_module/decision_desk_service.py::DecisionDeskSnapshotBuilder.build_snapshot`；`ui_qt/views/decision_desk_view.py::_open_industry_stock_research`、`_open_stock_focus_research` | DecisionDesk／產業代表目前帶 `stock_code`、`decision_date`、`data_date`、`source_id`、source／mapping version；沒有 exact saved result 時保持 unlinked | 由真實 MainWindow signal 開啟個股後，須保留市場／產業 source trace；不可把 `RecommendationDeskSummary.result_id` 猜套到任意 stock focus 或 industry representative |
| 產業探索 | `app_module/industry_strength_service.py::build_snapshot`、`build_industry_strength`、`build_screening_result`；`ui_qt/views/strong_industries_view.py`／`weak_industries_view.py::_update_table_with_data`、`_open_selected_representative_stock` | `ResearchStockContextDTO` 帶產業資料日、source version、mapping source/version/observed date；未有 saved result 仍不 linked | 正常 source、缺 taxonomy、future taxonomy、mapping conflict 都要在 stock report 顯示可追溯的 source／quality，而不是補 current 或轉成 Recommendation identity |
| Recommendation 保存結果 | `ui_qt/views/recommendation_view.py::_save_recommendation_result`、`_emit_stock_research_context`、`_build_stock_research_context`、`select_stock`；`app_module/recommendation_repository.py::save_result`、`load_result` | 只有保存成功後的 `current_result_id` 才進 `ResearchStockContextDTO.result_id`；Journey 的 root 是此 `result_id` | 需將同一 saved result 的 decision/data/source snapshot 與後續 Evidence／Outcome manifest 對齊；未保存或保存 JSON 缺失時不可留有 stale linked context |
| 觀察清單 | `ui_qt/views/watchlist_view.py::_row_decision_identity`、`_choose_recommendation_source`、`_build_stock_research_context`、`_open_stock_analysis`、`select_stock`；`WatchlistService.bind_stock_decision_identity` | typed `decision_identity` 才能形成 exact candidate；legacy `source_id` 只能作明確 source lookup，不能直接升格成 `result_id`；使用者可明確選擇保存結果 | 同股多列／多 result 時，source chooser、開啟報告、從報告返回都必須回到同一 row；不可因排序或同股第一列丟失 identity |
| Portfolio／持倉 | `ui_qt/views/portfolio_view.py::_validated_recommendation_result_id`、`_open_selected_stock_research`、`select_stock` | 僅 `source_type=recommendation_result`、保存 result JSON 存在、`result_id` 相符且該 JSON 對此 stock 恰一筆時才 linked；`backtest_run`、手動、`user_declared_research` 不得升格 | 本輪 bounded increment 已讓回返入口以目前 `position_id` 對回的 PositionDTO 做 exact `result_id` 驗證；無 exact／ambiguous 不以同股替代，無 result 的持倉仍維持 unlinked／stock-only 相容；完整跨頁驗收仍未宣稱通過 |
| Paper Position Health | `app_module/position_health_transition_read_service.py::read_latest`；`ui_qt/views/portfolio_view.py::_refresh_position_health`、`_health_for_position`、`_render_position_health`；`ui_qt/views/workbench_view.py::_render_position_health` | 以 `paper:<portfolio>:<stock>:entry-...`／`position_id`、cohort、receipt／source snapshot 精確讀取；Paper projection 是獨立唯讀區塊 | 與同股票的 `user_declared` 或 Recommendation row 同時存在時，仍不可以 stock code join；缺／future／stale receipt 要在兩頁一致呈 `unknown`／`WATCH`／blocked |
| `user_declared` | `ui_qt/widgets/user_declared_holding_research_widget.py::refresh_research`、`_select_exact`、`save_new`、`save_revision`；Portfolio 在 `ui_qt/views/portfolio_view.py` 的「聲明持倉研究」tab 建立 widget | row identity 是 `holding_id + revision_number`；`source_status=user_declared`、`entry_lineage=unproven`、`research_only=true`，不是成交、Paper entry 或 Recommendation result | 同 stock 的 formal／Paper／user_declared 同時存在時，技術詳情與安全文案不可混用；不得產生可寫 continuity controls 或 formal outcome link |
| Workbench continuity queue | `app_module/workbench_source_service.py::inspect` → `ContinuityReviewProjectionService.project` → `WorkbenchReadOnlyComposer._continuity_review_items`；`ui_qt/views/workbench_view.py::_navigate_model_row`、`_open_continuity_review_research` | R1 continuity row 自帶 exact `result_id`、`stock_code`、snapshot、decision date、revision 與 due status；此 branch 不走 daily first-candidate fallback | 需將跨頁回來的 recommendation／watchlist／portfolio identity 與 row 一致；generic `drilldown_target=stock_research` 的 `_open_daily_candidate_research` 仍取 `candidate_symbols[0]`，多 candidate path 未可作 exact acceptance |
| 個股報告／Decision → Outcome | `ui_qt/main.py::_open_stock_research_context`、`_return_to_research_source`；`StockResearchReportDialog.set_context`；`ui_qt/widgets/decision_outcome_journey_widget.py::set_context`、`_render_journey`；`DecisionContinuityController.identity_from_context`、`read_state`；`DecisionContinuityControlsWidget.set_context` | Report、Journey、controls 共用 `ResearchStockContextDTO`／`DecisionIdentity`；Journey 只載入 exact `(result_id, stock_code)`，controls 只對 linked identity 可寫 | 需在實際 MainWindow signal chain、返回來源頁、重新啟動後驗證相同 context；不能只靠直接 new view 的 R1 fixture 證明整個跨頁流程 |

### 2.1 本輪 bounded 修復狀態（Portfolio exact return）

2026-09-15 已完成一個有界的 Portfolio 返回修復，範圍只涵蓋目前持倉列的 result identity guard，不代表整條跨頁旅程已通過：

- `PortfolioView` 以隱藏 `position_id` 將可排序 table row 對回目前 `PositionDTO`，再要求 `source_type=recommendation_result`、保存 JSON、`result_id` 與該股票的 exact single-row 驗證一致。
- MainWindow 返回若帶有明示 `result_id` 卻無唯一 exact match，會維持 fail-closed，不把同股票第一列當替代，並在 status bar 提示重新從推薦分析開啟；無 `result_id` 的舊／unlinked context 維持單一股票代號相容路徑。
- 本輪只驗證 Portfolio／MainWindow 這個 bounded route；市場／產業、Watchlist 多列、Workbench、restart／one-close 與完整 C/L source chain 仍是本計畫後續 acceptance，不能由本修復推論為已通過。

本輪 focused evidence 已取得：`tests/test_ui_qt_stock_research_navigation.py` 與
`tests/test_ui_qt_portfolio_view.py` 合計 `27 passed`，包含真 Portfolio signal + MainWindow
return method harness、
R1 報告返回時目前持倉已換成 R2 的失配、排序後以 `position_id` 對回 DTO、exact match 成功、
無 `result_id` 單列相容，以及交易歷史篩選保留。指定 UpdateView regression 為 `84 passed`，
`scripts/qa_validate_update_tab.py` 為 `25 passed / 0 failed / 4 skipped`；先前暫受
foreign working-tree errors 影響的 full mypy 經 owner 修復後已重跑，並以
`Success: no issues found in 621 source files` 通過（僅兩個既有 untyped-body notes）。本輪 Python
檔案亦已完成 `py_compile`。另以單一受控 child 執行既有
`scripts/qa_run_research_journey_qt_subprocess.py --mode journey`，取得
`offscreen_qt_production_mainwindow`、exit 0 的 production MainWindow signal／workspace
證據；該 runner 仍不涵蓋 Portfolio exact return，故不擴大解讀。這些是 bounded 修復證據，
不是完整 cross-page acceptance 通過聲明。

## 3. 超出 R1 的情境驗收

### 3.1 正常完整來源：同一 candidate 的跨頁 round-trip

**隔離前置資料**

- 使用新建的 isolated `data_root`／`output_root`／DB；不得讀寫正式 `DATA_ROOT`。
- 至少保存兩個同股不同 result（例如 R1／R2 均有 2330）及一個多 candidate result（例如 R3 有 2330／2317），每個 result 的 `decision_date`、`data_date`、`source_snapshot_id`、`source_snapshot_hash` 與 recommendations JSON 都可重讀。
- 保存 exact Watchlist binding、Portfolio `recommendation_result` source、Recommendation／Evidence root、Journal accepted + scheduled revision；Workbench 使用明確 `continuity_as_of` 只作 deterministic replay，不把 dashboard 的 `as_of_date` 當成 reminder clock。
- 若使用正式市場／產業來源，source 必須帶可驗證的 available／effective cutoff、source／mapping version、raw／rows hash、universe／coverage 與 quality；未具備時只能標成 fixture／research-only，不得叫正式 complete-source。

**步驟與預期**

1. 從 MainWindow 的市場總覽進入產業代表股，再進個股報告；保存 `market_explore → stock_research` 的 context manifest。此段即使沒有 result ID 也可通過，但必須明示 `identity_status=unknown/unlinked`，且 Journey／controls 不可誤開。
2. 從 RecommendationView 保存 R1，對 R1 的 2330 開啟 report；確認 `result_id=R1`、`candidate_key=R1:2330`、日期／snapshot 沒有被目前行情替換。
3. 經 Watchlist 的 exact binding 開啟同一 2330；確認 Watchlist 與 report context 仍為 R1，而不是同股的 R2 或 legacy `source_id`。
4. 經 Portfolio 的同一 `recommendation_result` position 開啟 report；確認 `_validated_recommendation_result_id` 的 exact JSON／single row guard 成立；若來源是手動、backtest 或 `user_declared_research`，預期為 unlinked，不得為了完成 round-trip 強行 linked。
5. 回到 Workbench，選取 R1:2330 的 continuity row；確認 `_open_continuity_review_research` 直接帶 row identity，Journey 顯示 R1 的 exact maturity／Evidence／Portfolio event，controls 顯示同一 Journal history。
6. 在 report／Journey／controls 只做 read-only navigation 時，Journal bytes／hash、Recommendation JSON、Watchlist binding、Portfolio ledger 均不變；只有使用者明確按 controls 才可產生一個新的 append-only revision。

**通過條件**

- 每個跨頁節點的 `result_id`、stock、decision/data date、snapshot hash、source workspace 與 candidate key 可由 manifest 逐欄比對。
- 市場／產業 metadata 與 Recommendation identity 分開；`source_id`、mapping version 或同股日期不可單獨形成 result ID。
- R1 的 `accepted`／reminder 不被 Outcome maturity 或 `ResearchFallbackPacket.revisit_date` 覆寫；兩種日期各自顯示。

### 3.2 缺資料、future、stale、conflict：不猜測的降級

每個子案例都要同時記錄 service DTO、UI visible status、diagnostics 與 identity；不可只驗證畫面沒有例外。

| 受控缺口 | 入口／資料 | 預期 read model | UI／identity 預期 | 真實 UI？ |
|---|---|---|---|---|
| 市場或產業 snapshot 缺失 | `DecisionDeskSnapshotBuilder.build_snapshot`、`IndustryStrengthService.build_snapshot`／`build_industry_strength` | missing／partial／warning；不以 current date 補值 | stock report 顯示 source unavailable／unknown；不產生 result ID | 是；需看市場、產業、stock report 的退化文案 |
| L taxonomy identity 缺失、hash／universe／market scope 不符 | `PITSectorMembershipReader.read` 及 `IndustryStrengthService._read_pit_membership` | unavailable／degraded，rows 不可當 verified industry | 不可把 `companies.csv` 現況 mapping 套到歷史；不開啟 false complete-source | service 必驗；UI 至少驗一個代表股降級 |
| Recommendation JSON／DB root 缺失或 result 不含該 stock | `RecommendationRepository.load_result`、`DecisionOutcomeJourneyService.build`、Stock Research report | missing／unlinked；Journey 無 candidate rows | `result_id` 清空或 conflict，controls disabled；不得以同股同日補接 | 是；必須看到 unlinked message |
| Evidence／outcome available date 在未來 | `DecisionOutcomeJourneyService._read_evidence`／maturity projection | `pending`／`insufficient_future_data` | 顯示待成熟；不補 forward return、成交或 effectiveness | 是；需看 maturity table |
| Journal 缺失、malformed、chain／identity conflict | `ContinuityReviewProjectionService.project`、`WorkbenchSourceService.inspect` | stream `missing`／`invalid`，不產生 partial due queue | Workbench 顯示 warning／unknown；不建立新檔、不自動寫入 | 是；需確認 Workbench 不誤報正常 due |
| Position Health receipt 缺失、future、stale、hash conflict | `PositionHealthTransitionReadService.read_latest` | blocked／missing／stale；positive row 撤回成 `WATCH` 或空 rows | Portfolio／Workbench 同時維持 Paper research-only；不綁人工或 user_declared position | 是；需看兩個 consumer 的一致文案 |
| `user_declared` market／condition source 缺失或 future | `UserDeclaredHoldingResearchService.read_research`、widget refresh | `unknown`／WAIT；source trace 留診斷 | 只保留 holding／revision 與 research-only boundary；不變成 Recommendation／Paper | 是；需看「不是券商成交／Paper」與 WAIT |

**共同負向條件**：任何 missing／future／stale／conflict 均不得回退到「最新結果」、「同股第一筆」、「同 snapshot」、「目前日期」或另一個 source workspace；不可因 UI 可點擊而代表 identity 已連結。

### 3.3 同一股票、不同 result／不同日期

使用 R1:2330、R2:2330、R3:2330／2317 的隔離 fixture，另外讓 R1／R2 使用不同 decision date 或 source snapshot。驗收順序：

1. Workbench 選 R1:2330 與 R2:2330 各一次；callback context、report、Journey、controls 都必須各自保持 result ID 與 snapshot。
2. Watchlist 同股多列時，先用 `_choose_recommendation_source` 明確選 R2，再開啟與返回；不得因 row sort 回到 R1。沒有 typed binding 的 legacy row 只能顯示 explicit source choice，不可靜默套用最新結果。
3. Portfolio 以 R1／R2 source JSON 各建立可讀 position fixture；`_validated_recommendation_result_id` 必須拒絕 stock mismatch、duplicate recommendation rows、result JSON mismatch。`select_stock()` 回返時若無法保留 result-level row，應保持 unlinked／需人工確認，不得以 stock code 代替。
4. 同一 `result_id` 但 context 的 decision date／snapshot 與保存 root 不同時，Journey／controls 應顯示 conflict 或 unlinked；不得只因 result ID 相同就繼續 join。
5. R3 由 2330 切到 2317 時，不能沿用 2330 的名稱、source snapshot 或 outcome；`StockResearchReportView._load_stock` 的 context replacement 仍要由 service 重新驗證新股票。

**真實 UI 要求**：此情境不能只測 composer callback。至少要在真實 Qt signal chain 點擊 Workbench row、Watchlist source choice、Portfolio report button、Report return；截圖或 accessibility/text receipt 必須包含 result ID、stock code、decision date／snapshot 與 unlinked/conflict status。

### 3.4 `user_declared`、Paper 與 formal Recommendation 不串線

用相同 `2330` 建立三種可並存資料：

| lane | 應讀的 identity／欄位 | 明確禁止 |
|---|---|---|
| formal Recommendation／Outcome | `result_id=R1`、candidate key `R1:2330`、Evidence／Journal exact root | 不可以 holding 或 Paper position 取代 result root |
| Paper Position Health | `position_id=paper:<portfolio>:2330:entry-...`、cohort、receipt／source snapshot、`research_only=true` | 不可用 2330 猜配 manual／user_declared；不自動平倉、不建立 Recommendation outcome |
| `user_declared` | `holding_id=user_declared:...`、revision number、聲明成本、`source_status=user_declared`、`entry_lineage=unproven`、`calibration_status=excluded_user_declared` | 不可標成券商成交、Paper verified entry、formal Portfolio fill、realized PnL 或 Recommendation `result_id` |

實際 Portfolio UI 必須可分辨「聲明持倉研究」與「Paper Portfolio／Position Health」tab；選取其中一列不應改變另一 lane 的 selection、source trace、controls 或 report context。任何從 Portfolio 開啟個股報告的操作，都要再次經 `source_type=recommendation_result` + saved JSON exact single-row guard；其他來源保持 unlinked、Journey empty／disabled。

### 3.5 重啟讀回與一次 close

**重啟讀回**

1. Process A 在 isolated root 只建立受控 fixture，開啟完整 cross-page path，讀取 R1:2330 的 report／Journey／continuity／H／I。
2. 關閉 A 後，Process B 重新建構 `TWStockConfig`、`WorkbenchSourceService`、`DecisionOutcomeJourneyService`、`PositionHealthTransitionReadService` 與 `UserDeclaredHoldingResearchService`；不可依賴 `ResearchSessionStore`、Qt object graph 或上一個 process 的 cache。
3. B 必須讀回同一 `result_id`／candidate key、Journal head／reminder、source snapshot、Paper position identity、holding revision、source trace 與安全旗標。Read-only drilldown 前後所有 input bytes／hash 必須一致。
4. 只有在使用者明確執行 controls action 後才驗證一次新 revision；新 process 以 projection reader 讀回新 head，不能把 stale session 當成功。

**一次 close**

- Report worker、Journey worker、Portfolio refresh、`user_declared` research refresh 至少各有一個受控 busy probe；user close request per process 必須為 1。
- 關閉時沿用 `StockResearchReportDialog.closeEvent`、`StockResearchReportView.request_close`、`DecisionOutcomeJourneyWidget.request_close`、`PortfolioView.begin_shutdown`／`closeEvent` 與 `UserDeclaredHoldingResearchWidget.begin_shutdown` 的 cooperative cancellation。
- 通過條件是 `dialog_finished=true`、`app_exec_returncode=0`、child process exit `0`、沒有 terminate／kill／forced termination，且 pending worker 不會在 close 後重新啟動。
- R1 既有 `scripts/qa_continuity_review_workbench_busy_close.py` receipt 只作 report／Journey oracle；本計畫新增的是 MainWindow／Portfolio／I lane 同時存在時的整合 lifecycle，不能把既有單 dialog receipt 擴大解讀。

## 4. C P1 與 L producer：只列 downstream input contract

這一節是 downstream acceptance 的輸入契約，不是 C/L implementation task；不修改相關檔案、不新增等待型 gate、不把自然 sample maturity 當工程前置。

### 4.1 C P1 next-day inference／projection provenance

下游可讀的 projection／receipt 至少要能逐欄解析：

- candidate／model ID、artifact hash、freeze／manifest hash、effective pointer date；
- training provenance：merged dataset hash、bootstrap／replay manifest、natural sample IDs、dedup rule、training cutoff 與 fold／evaluation windows；
- inference provenance：source-contract file/content hash、feature snapshot fingerprint／rows hash、feature date、availability date、source quality；
- policy／transform／baseline identity、ranking score／method／percentile、selection authority、upside probability、after-cost value／status；
- schema／transform compatibility，使 training dataset hash 與隔日 feature hash 可以是不同日期、不同 hash，但仍能證明同一相容契約。

`app_module/recommendation_calibration_consumer.py`、`app_module/recommendation_service.py`、`app_module/recommendation_learning_evidence_projection_service.py`、`ml_module/recommendation_calibration_training.py` 與 `scripts/scheduled/run_daily_recommendation_learning.py` 是此契約的實際來源／消費入口。若欄位缺失或不一致，下游維持 rule-only／unknown／unavailable；不把 probability 未授權改成 top-N authority，也不把 incomplete projection 當成已驗收 C。

### 4.2 L official PIT taxonomy source chain

Industry／Recommendation caller 可消費的最小 taxonomy lineage 至少要有：

- `classification_version_by_market`、`mapping_by_market`、`classification_sources_by_market`；
- `source_id`、`source_version`、`source_hash`、`source_path`、`available_at`、`effective_from`；
- `universe_hash`、`symbols`、`universe_hash_symbols`、`scores_bp`、`rank_order`；
- `market_by_symbol`、`security_type_by_symbol`、`security_eligibility_by_symbol`、`eligible_symbols`、`excluded_by_security`、`unknown_symbols`；
- `raw_manifest_path`／`raw_manifest_hash`、`mapping_hash`、`license_scope`，以及 reader 可重新讀 raw bytes 驗證的 status／quality／warnings／lineage。

實際 producer／reader／publisher 入口為：

- `data_module/pit_taxonomy_source_producer.py::capture_configured_daily_pit_taxonomy_bundle`、`build_daily_pit_taxonomy_bundle`、`read_daily_pit_taxonomy_bundle`；
- `data_module/pit_sector_membership_reader.py::PITSectorMembershipReader.read`；
- `data_module/formal_pit_sector_publisher.py::publish_daily_pit_taxonomy_sidecar`、`publish_formal_pit_sector_sidecar`、`read_formal_pit_sector_receipt`；
- `scripts/scheduled/run_pit_sector_membership_preopen_capture.py` 與 `scripts/scheduled/run_formal_pit_sidecar_postcutoff.py`。

最低安全條件是 `available_at <= decision_at`、preopen capture completion time 可證明、raw／canonical／universe hash 相符、market scope 不碰撞、普通股型別有獨立可重驗 evidence；缺欄、future、現況 mapping 套歷史、source hash 不可重驗或 taxonomy 未 verified 時，IndustryStrength／Recommendation 只能 degraded／unavailable。L 仍不提供、也不能猜造 Recommendation `result_id`；exact result ID 由保存結果與 caller 明示攜帶。

## 5. 真機／實際 Qt 驗收矩陣

「真實 UI」是指實際 PySide6 signal／view／MainWindow route；`tmp_path` 直接呼叫 composer 或 fake callback 只能算 service／component 證據。所有新 run 必須使用隔離 runtime root，輸出到新的 QA evidence 目錄，不覆寫既有截图、receipt 或正式資料。

| 情境 | service／isolated artifact | 必須的實際 UI | 最小畫面／流程證據 |
|---|---|---|---|
| 正常完整來源 | RecommendationRepository／EvidenceEventRepository／JournalService、WorkbenchSourceService、C/L source manifests | MainWindow 市場總覽 → 產業代表 → StockResearchReportDialog；Recommendation／Watchlist／Portfolio → report；Workbench exact row → Journey | 1366×768 及必要的 1700×1100；context manifest、candidate key、snapshot、回返頁 selection |
| missing／future／conflict | 每個 source 的 isolated mutation、`ContinuityReviewProjectionResult`、Journey／Position Health／I read model | Workbench、Stock Report、Portfolio 三個 consumer；需看到 status／diagnostics／boundary copy | no false success、無新增檔、無誤連 result；missing/future/conflict screenshot 或 text receipt |
| 同股多 result/date | R1/R2/R3 saved roots、Watchlist binding、Portfolio exact source guard | Workbench row click、Watchlist chooser、Portfolio report、Report return | R1:2330 與 R2:2330 兩組 identity 各自可讀；不回第一列 |
| `user_declared` vs Paper | user declared JSONL／revision readback、Paper receipt／latest pointer、Position Health read model | Portfolio 四個相關 tab、表格 selection、technical detail | same 2330 的 `holding_id`、`paper position_id`、Recommendation result ID 三者不可混用；安全邊界完整換行 |
| restart／one-close | Process A/B readback、bytes／hash before-after、existing busy-close scripts／receipts | 由實際 MainWindow／dialog 啟動與一次 close；受控 child process 觀察 `app.exec()` | `close_requests_from_user=1`、自然 `finished`、exit 0、forced termination false；B 讀回同一 head |

建議的受控執行方式是沿用既有 `.venv\Scripts\python.exe`、`QT_QPA_PLATFORM=offscreen` 與 isolated `TWStockConfig`；可重用 `tests/test_continuity_review_workbench_r1_integration.py` 的 producer-backed fixture、`scripts/qa_continuity_review_workbench_busy_close.py`、`scripts/qa_position_health_increment_1_visual.py` 與 `scripts/qa_user_declared_holding_research.py` 的 subprocess／close pattern。完整 cross-page acceptance 仍須補一個實際 MainWindow signal chain；不能只把這些 component-level 證據相加宣稱已閉環。

## 6. 證據包與停止條件

每個 scenario 建議產生一個不可覆寫的 isolated evidence bundle，最少包含：

- `identity_manifest.json`：每個 stage 的 `source_workspace`、`source_kind`、stock、result／candidate、decision/data date、snapshot、mapping／source version、`position_id`／`holding_id`、continuity revision 與 visible status；
- source／artifact path、SHA-256、available／effective／cutoff timestamps、coverage／quality／warnings；
- read-only drilldown 前後的 Journal／Recommendation／Watchlist／Portfolio／Paper／user_declared bytes hash；
- 真實 Qt 截圖或可重現的 accessibility/text receipt；
- restart readback JSON 與 one-close process receipt。

只要出現以下任一項，本計畫的該 scenario 就是未通過／需回到 owner triage，不得以其他 scenario 抵銷：

- context 有 stock 但 `result_id`／candidate key 變成另一個 result、日期或 snapshot；
- missing／future／conflict 被顯示成 ready、current、已成交、已成熟或正式建議；
- `user_declared` 或 Paper identity 被提升為 Recommendation identity，或同股猜配成功；
- read-only navigation 改寫 Journal／result／ledger／binding，或 close 需要 terminate／kill；
- 只測 component view，卻沒有實際 MainWindow signal／return path 的證據。

本文件的完成定義是「形成可重跑的跨頁 acceptance checklist 與 input contract」，不是宣稱整條市場到 Outcome 旅程已通過。C P1、L source chain 與真實 full-source run 完成後，才依本文件執行一次 bounded end-to-end；不新增 generalized gate，也不把 fixture／replay／自然 sample `0` 轉成正式成熟度或採用證據。
