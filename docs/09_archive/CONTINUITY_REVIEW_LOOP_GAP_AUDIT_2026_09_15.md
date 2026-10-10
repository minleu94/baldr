# Continuity Review Loop 與正式 Decision Outcome 對應盤點

> **歷史唯讀盤點（2026-10-10）：** 本文的 Workbench due projection、Portfolio identity guard 與「等待 J」結論是 2026-09-15 的程式／資料契約快照，不是目前待辦清單。較後的 R1 due projection／exact drilldown 收據見 [2026-09-27 Roadmap History](DEVELOPMENT_ROADMAP_HISTORY_2026_09_27.md)；現況看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)、[目前 QA 導覽](../06_qa/README.md) 與 [操作手冊](../07_guides/APPLICATION_MANUAL.md)。

> 日期：2026-09-15
> 性質：有界唯讀驗收盤點；本文件只記錄目前程式與資料契約，不改程式、不改正式資料、不執行測試、不 stage、不 commit。
> 審核基線：目前 `dev` HEAD `a4996cba`，已包含 A/B/C、Position Health H 與自行登錄持倉 I 的已接受提交。
> 獨占邊界：J task `01a0a488-8b52-70a2-8065-6f892dc22b33` 的 PIT reader、Recommendation／industry caller 與 shared SSOT/index 不在本盤點中實作，也不另建平行 index。

## 一、主結論

目前不是缺少一條新的 Journal 或新的 outcome storage，而是既有兩條唯讀／研究路徑尚未在每日入口匯合：

1. **精確推薦 candidate 路徑已接通。** 已保存的 `result_id` 加上 `stock_code` 會進入單股研究頁；同一頁同時放置正式 `DecisionOutcomeJourney` 與 continuity controls。研究動作追加到既有 append-only Journal，正式成熟度則由既有 Recommendation／Evidence read model 讀取。
2. **隔日到期提醒尚未接通。** `next_review_at` 目前只在單一 candidate 的 controls 中寫入／讀回；Workbench 的 `review_items`、`action_items`、`operating_loop_steps` 沒有 continuity due／overdue projection，也沒有從到期項目帶 exact candidate context 下鑽。
3. **正式 Journey 與 continuity history 目前是同頁並置，不是同一 read contract。** Journey 讀 active Journal note；`accepted`／`skipped`／`review_scheduled` 等 decision revision 由 controls 另讀，因此正式 Journey 的 `journal_entries`／timeline 不包含完整 continuity action history。
4. **Portfolio 個股研究入口有一個真實 identity 風險，應先設防。** `PortfolioView` 將泛用 `PositionDTO.source_id` 同時填入 context 的 `result_id`。這對 `recommendation_result` 來源可成立，但對 `backtest_run`、`strategy_version`、`user_declared_research` 等來源不成立；後者可能讓 controls 以非推薦 ID 開啟可寫研究動作。這不會把它直接變成成交，但會污染 formal decision continuity identity，必須 fail closed。
5. **DecisionDesk／產業代表股目前沒有 formal result identity 是正確的保守狀態。** 這些入口只有市場／產業來源 metadata，不能以同股同日、`source_id` 或目前最新推薦猜測結果。J 完成真正的 PIT／Recommendation／industry caller 接線後，才可把已驗證的 result identity 傳入；本次不重做 J。

因此，A/B/C/H/I 不需重做；下一個最小工程單元應是「既有 continuity revision 的唯讀 due projection → Workbench exact stock-research 下鑽」，並以 Portfolio typed identity guard 作為同一單元的必要前置。它不新增持久化 storage、不複製 outcome 計算、不改 Advice、Portfolio trade、broker 或自然 evidence credit。

## 二、已接受的共用資料契約

### 2.1 Candidate identity 是唯一 join key

| 契約 | 目前位置 | 驗收判讀 |
|---|---|---|
| `DecisionIdentity` | `app_module/dtos/decision_continuity_dtos.py:91-221` | `result_id + stock_code` 才能形成 `candidate_key`；`source_snapshot_id/hash` 是獨立 provenance。 |
| 不提升 legacy `source_id` | `app_module/dtos/decision_continuity_dtos.py:139-203` | `from_mapping` 明確不從 `source_id` fallback；缺 result identity 就是 `unknown`，不是猜測。 |
| continuity revision | `app_module/dtos/decision_continuity_dtos.py:234-333` | revision、`revision_of`、action、identity、`next_review_at`、actor、created_at 都保留在 immutable envelope。 |
| candidate state | `app_module/decision_continuity_controller.py:43-75` | `can_write` 只對 linked 且無 read error 開啟；缺 exact identity 直接停用。 |

`candidate_key` 的語意是 `(result_id, stock_code)`，不是單獨股票、決策日、source snapshot 或持倉 ID。這是本盤點判定所有 caller 的唯一標準。

### 2.2 既有 Journal 是單一 continuity 寫入來源

- `JournalService.list_journal_entries`、`list_journal_history`、`list_decision_revisions` 位於 `app_module/journal_service.py:124-142`。
- `record_decision_action` 在 `app_module/journal_service.py:203-334` 建立 revision envelope；`record_research_action` 於 `:334-349` 只是語意別名，沒有建立交易。
- `DecisionContinuityController.read_state` 在 `app_module/decision_continuity_controller.py:276-349` 將 accepted／skipped intent 與 reminder action 分離；`apply` 在 `:353-500` 只追加研究 action。
- `next_review_at` 由 `app_module/decision_continuity_controller.py:236-250` 驗證為帶時區時間並正規化為 Asia/Taipei； controls 寫入／讀回位置為 `ui_qt/widgets/decision_continuity_controls.py:183-212`、`:237-320`、`:331-410`。
- `app_module/portfolio_store.py:148-206` 的 `project_journal_records` 明確把 decision entity 視為 history-only；`load_journal_entries`、`load_journal_history`、`load_decision_revisions` 分別在 `:291-318` 提供 active projection、raw history 與 typed revisions。

這表示未來的 due projection 應讀同一份既有 history／typed revisions；不能新增 `continuity_reviews.jsonl`、第二個 candidate registry 或另一套 reminder state。

### 2.3 正式 outcome 是既有 result-rooted read model

- `DecisionOutcomeJourney` 的安全旗標在 `app_module/decision_outcome_journey.py:573-646`：`research_only=True`、`actual_personal_records_separate=True`、`investment_effectiveness_claim=False`、`read_only=True`、`writes_allowed=False`、`broker_execution=False`、`auto_rebalance_allowed=False`。
- `JsonlJournalReadAdapter` 在 `app_module/decision_outcome_journey.py:763-794` 讀同一份 Journal JSONL，但呼叫 `project_journal_records`，只投影 active notes。
- `DecisionOutcomeJourneyService.from_paths/from_config` 與 `build` 位於 `app_module/decision_outcome_journey.py:817-1041`；cross-source join 以 result root 和 explicit identity 驅動。
- `5/10/20/60` maturity 只在 exact candidate event／outcome identity 對上時建立，邏輯位於 `app_module/decision_outcome_journey.py:1575-1685`。
- Journey 的 Journal／timeline 讀取在 `app_module/decision_outcome_journey.py:1846-1900`；timeline 的 journal item 是 `journal_entry`，不是 continuity decision revision。

UI 的 candidate 篩選也再次檢查 exact key：`ui_qt/widgets/decision_outcome_journey_widget.py:394-462` 只有在有 `result_id` 時啟動 async load，`:647-780` 以 `(result_id, stock_code)` 過濾 candidate、maturity、Evidence、Journal 與 Portfolio event；不以同股同日補接。

## 三、使用者每日流程：已接與未接

| 使用者意圖 | 現有實際接線 | 狀態 | 未接點／邊界 |
|---|---|---|---|
| 記錄當時研究決策 | Recommendation 儲存成功後，`current_result_id` 在 `ui_qt/views/recommendation_view.py:2318-2361` 設定；同頁 context builder `:2424-2509` 傳出 typed result identity。MainWindow `ui_qt/main.py:262-307` 建立 controller／Journey service，`:998-1076` 將 context 送入共用報告視窗。 | **已接（exact path）** | 未保存推薦或缺 result ID 時維持 unknown／停用，這是正確 fail-closed。 |
| 到期提醒 | controls 會保存並顯示 `next_review_at`；`DecisionContinuityState` 可讀最新 reminder。 | **未接到每日入口** | `WorkbenchReadOnlyComposer.compose` 僅由 `app_module/workbench_read_only_composer.py:43-101` 組合既有 snapshot／readiness／scheduled／replay／learning；沒有 continuity reader。 |
| 看當初推薦與成熟 outcome | `StockResearchReportDialog` 在 `ui_qt/views/stock_research_report_view.py:1047-1073` 同時掛 report 與 Journey；Journey 讀 exact result root、Evidence 與 5/10/20/60 maturity。 | **已接但僅限 exact result caller** | Daily Workbench 可攜帶 `candidate_result_id`，但按鈕只開 `candidate_symbols[0]`；DecisionDesk／產業代表與未綁定 Watchlist 沒有 formal result ID。 |
| 追加檢討 | 同一 Journey tab 的 controls 可按「納入研究／略過／記筆記／設定下次檢視」，並顯示 typed candidate history。 | **單一頁面已接；daily loop 未接** | Workbench 的 `manual_review_note` 只指向既有 Evidence Review／Daily Decision；沒有把 due candidate 導回同一 continuity controls。 |
| 隔日可讀／學習用途 | `DailyInvestmentJourneyService` 讀 scheduled recommendation snapshot、Evidence event／outcome、learning receipt；`app_module/daily_investment_journey.py:127-257` 產生 daily evidence，`app_module/workbench_source_service.py:78-132` 接到 Workbench。 | **正式 outcome／learning 已接；continuity 未接** | daily read model 沒有 `next_review_at`、continuity action history 或 exact due candidate；session store 只是目前 session context，不是隔日 persistence。 |

## 四、真實 caller／UI 接線盤點

### 4.1 已接且可驗收的 caller

1. **RecommendationView → shared stock research**

   - 儲存成功才設定 `current_result_id`：`ui_qt/views/recommendation_view.py:2318-2361`。
   - row context 以目前推薦 result 建立 `ResearchStockContextDTO`：`ui_qt/views/recommendation_view.py:2424-2509`。
   - MainWindow 將 Recommendation、Watchlist、Portfolio、DecisionDesk、強／弱產業與 Workbench 的 signal／callback 都接到 `_open_stock_research_context`：`ui_qt/main.py:569-641`、`:686`、`:726-787`。
   - 這條路徑與 existing A/B/C 的 exact candidate contract 相容，不需要另做一個 outcome store。

2. **Workbench daily candidate → shared stock research**

   - `WorkbenchDailyEvidence` 已保留 `candidate_result_id`、source snapshot 與 candidate symbols：`app_module/workbench_dtos.py:520-665`。
   - candidate reader 從 scheduled snapshot／run JSON 讀 exact result：`app_module/daily_investment_journey.py:396-555`；event identity 另在 `:904-921` 檢查。
   - UI callback `ui_qt/views/workbench_view.py:1150-1171` 將 `candidate_result_id` 放入 `ResearchStockContextDTO`，所以有 result ID 時可進入正式 Journey。
   - 限制是 `ui_qt/views/workbench_view.py:1056` 與 `:1155` 只取 `candidate_symbols[0]`；一個 run 多個 candidate 時沒有逐列 exact candidate 選擇器。

3. **Watchlist exact binding → shared stock research**

   - row 的 typed identity 只從 `decision_identity` 讀取，`ui_qt/views/watchlist_view.py:971-991`；legacy row 維持 unknown。
   - 使用者可在 `ui_qt/views/watchlist_view.py:1050-1093` 明確選擇保存的推薦結果並寫入 binding；這是正確的人工補 identity 入口。
   - context builder `ui_qt/views/watchlist_view.py:1219-1295` 只接受 typed identity 或 exact source lookup 驗證成功的 result；註解與實作都禁止把 legacy `source_id` 直接升格。
   - 因此未綁定／universe 路徑停在 report-only、Journey unlinked，是安全結果，不是要用日期猜測修補的缺口。

### 4.2 尚未接通或需設防的 caller

1. **Portfolio：高優先 identity guard**

   `ui_qt/views/portfolio_view.py:2334-2364` 在建立 context 時把 `position.source_id` 同時填入 `result_id` 與 `source_id`。但 `PositionDTO` 的 `source_type/source_id/source_summary` 是泛用欄位，定義在 `app_module/dtos/portfolio_dtos.py:59-101`，不是 typed recommendation result contract。

   具體對照：

   - `recommendation_result` 來源在 `app_module/portfolio_source_adapter.py:97-98` 使用 `source_id=result.result_id`，可作為候選來源，但仍應做 exact saved-result／stock 驗證。
   - `backtest_run` 來源在 `app_module/portfolio_source_adapter.py:136` 的 `source_id` 是 run ID，不是 recommendation `result_id`。
   - I lane 在 `app_module/user_declared_holding_research.py:1165-1175` 使用 `position_id=holding_id`、`source_type="user_declared_research"`、`source_id=holding_id`；這個 holding ID 不得升格成 formal recommendation identity。

   目前 Journey service 對不存在的 result root 會降級／報 unknown，但 controls 是依 context 的 `result_id + stock_code` 判斷可寫，因而可能對 holding ID 或 backtest ID 追加 continuity revision。這不是成交或自然信用，但已是錯誤的 formal decision linkage。

   **驗收要求：** Portfolio 只有在 `source_type` 明確為 `recommendation_result` 且來源 ID 通過 exact result／stock 驗證時才填 `result_id`；其他來源 `result_id` 必須為空、identity unknown、controls disabled。不得把 I 的 `baseline_result_id/current_result_id` 自動當成持倉原始決策；那些是 condition research lineage，不等於成交或正式推薦綁定。

2. **DecisionDesk stock focus／industry representatives：保守 unlinked，等待 J 的真實 caller contract**

   - DecisionDesk 的 stock focus card 只有 `stock_code/name/role/reason/source`，沒有 result ID：`app_module/decision_desk_dtos.py:584-612`。
   - 市場總覽雖可在 `ui_qt/views/decision_desk_view.py:441-455` 顯示 `RecommendationDeskSummary.result_id`，但 stock focus 下鑽 `:790-816` 仍只傳 card source；不能把 summary 的 result ID 猜套到任意 focus card。
   - DecisionDesk 的產業代表下鑽 `ui_qt/views/decision_desk_view.py:766-788`、強勢產業 `ui_qt/views/strong_industries_view.py:302-327`、弱勢產業 `ui_qt/views/weak_industries_view.py:314-339` 都只有 industry/source metadata，沒有 `result_id`。

   J 目前工作樹已在 `app_module/recommendation_service.py:82-108`、`:453-494` 與 `app_module/industry_strength_service.py:418-434`、`:447-545` 增加 PIT reader／decision-time 參數；目前也已由 `app_module/decision_service_composition.py:54-116`、`app_module/decision_desk_composition.py:140-175`、`app_module/decision_desk_builder_factory.py:104-140` 將設定好的 reader 接入服務組合根。這是 J 的獨占工作，本切片不補接或修改。即使 PIT 讀取鏈已接通，仍需由真正產生／保存 recommendation result 的 caller 明確攜帶 exact `result_id`；否則產業代表下鑽繼續維持 unlinked。

3. **Workbench review queue：沒有 continuity identity 欄位**

   - `WorkbenchReviewItem`、`WorkbenchActionItem`、`WorkbenchOperatingLoopStep` 的欄位在 `app_module/workbench_dtos.py:92-260`，沒有 `result_id`、`stock_code`／candidate key、`next_review_at` 或 revision ID。
   - `WorkbenchReadOnlyComposer._review_items`、`_action_items`、`_operating_loop_steps` 分別在 `app_module/workbench_read_only_composer.py:156-226`、`:370-498`、`:566-683`，來源是 watchlist trigger、portfolio alert、risk prompt、readiness、replay 與 learning；沒有 Journal continuity revisions。
   - `WorkbenchSourceService.inspect` 在 `app_module/workbench_source_service.py:78-132` 只組合上述 read models、daily evidence 與 Position Health；沒有 continuity reader。
   - UI 的已查看數只存在本次 session：`ui_qt/views/workbench_presenter.py:17-42`、`ui_qt/views/workbench_view.py:1649-1652`、`:2428-2429`；它不是 due index，也不應被改成完成標記。

4. **已有的 `revisit_date` 不是 continuity reminder**

   `ResearchFallbackPacket.revisit_date` 位於 `app_module/workbench_dtos.py:375-494`，由 `app_module/daily_investment_journey.py:1188-1262` 根據 natural evidence pending、官方交易日曆與 maturity horizon 估算，UI 在 `ui_qt/views/workbench_view.py:2515-2539` 顯示。它回答「何時再檢查自然 evidence 是否成熟」，不是使用者按下「設定下次檢視」寫入的 `next_review_at`。兩者不得合併或互相覆蓋。

## 五、形式上已接、語意上尚未匯合的地方

目前單股研究頁的組合是：

```text
exact ResearchStockContextDTO
        ├─ DecisionContinuityControlsWidget
        │    └─ DecisionContinuityController → JournalService → journal_entries.jsonl
        └─ DecisionOutcomeJourneyWidget
             └─ DecisionOutcomeJourneyService → recommendation run / Evidence / active Journal note / separate Portfolio read
```

這條線的好處是沒有把研究 action 當成 trade，也沒有把 outcome 當成成交；但兩個分支的 read contract 尚未共享「目前 decision action／到期狀態」：

- controls 讀 `list_decision_revisions()`，會顯示完整 history、decision status 與 latest `next_review_at`：`app_module/decision_continuity_controller.py:314-349`、`ui_qt/widgets/decision_continuity_controls.py:237-287`。
- Journey 讀 `list_entries()` 的 active projection；`project_journal_records` 對非 `journal` entity 在 `app_module/portfolio_store.py:189-206` 跳過，因此 `accepted`、`skipped`、`review_scheduled` 不會成為 Journey 的 journal row。
- Journey 的 `journal_entries` 表格 `ui_qt/widgets/decision_outcome_journey_widget.py:302-320`、`:746-781` 是 note／thesis view，不是完整 continuity action view。

所以「同一 tab 可看到 controls 與 maturity」已成立；「continuity review loop 與正式 decision outcome 有可供 Workbench／隔日流程消費的共同對應 read model」尚未成立。

## 六、下一個最小工程切片

### R1：Continuity Review Read Projection → Workbench exact drilldown

只做一個 read-only projection 單元，沿用既有 Journal history 與 formal Journey，不新增 storage：

1. 讀既有 `decision_continuity_revision` stream；可沿用既有 `JournalService.list_decision_revisions()` 的語意，但 Workbench 端應使用不建立目錄／不呼叫 writer 的 read adapter。
2. 僅投影 `identity_status=linked` 且 exact `candidate_key=(result_id, stock_code)` 的最新資料：
   - `decision_status`：`accepted`／`skipped`／`unrecorded`；
   - `next_review_at`：原始帶時區值，內部以 Asia/Taipei 比較；
   - `due_status`：`scheduled`／`due`／`overdue`／`invalid`；
   - `revision_id`、`source_snapshot_id/hash`、`decision_date`、`source_trace`。
3. 把 projection 以 `review_items` 或等價的 Workbench read-only DTO 暴露；item 必須帶 exact result ID 與股票代號，`drilldown_target="stock_research"`。點擊只呼叫既有 `_open_stock_research_context`，不在 Workbench 重算 outcome。
4. 下鑽後仍由 `DecisionOutcomeJourneyService.build(result_id)` 讀正式 recommendation／Evidence／maturity；Journey 只顯示同一 `(result_id, stock_code)`，不建立第二套 outcome index。
5. Portfolio caller guard 是 R1 的必要前置：非 `recommendation_result` 的 Position source 一律不填 `result_id`；I／H 保持獨立研究／健康 read model，不納入 continuity candidate。
6. 點擊 due item 不自動清除、標記完成或寫 Journal；使用者必須在 Journey controls 明確追加 note、accept／skip 或新的 review schedule。Workbench 的 session viewed 狀態仍只代表已查看，不代表完成。

### R1 明確不做

- 不建立 `continuity_reviews.jsonl`、SQLite reminder table、parallel candidate registry 或新的 index。
- 不把 `ResearchFallbackPacket.revisit_date` 改作 `next_review_at`。
- 不把 H 的 `position_id`／Paper health 或 I 的 `holding_id`／declared cost 接成 recommendation `result_id`。
- 不把手動／聲明持倉轉成 formal Portfolio trade、broker fill、natural evidence、effectiveness claim 或 calibration credit。
- 不在 J 的 PIT／Recommendation／industry caller 範圍內改檔；完成 J 後再由 exact result caller 提供 context。

## 七、可驗收正案例

### P1：同一 candidate 的到期提醒可從隔日 Workbench 回到正式 Journey

前置資料：既有 Journal 有 linked identity `result_id=R1`、`stock_code=2330`、`next_review_at` 已到期；`output/recommendation/runs/R1.json` 存在，且 Evidence 已有 exact `recommendation_included` event。

驗收：

- Workbench 讀到一筆 continuity due／overdue item，顯示 candidate key `R1:2330` 與 source trace。
- 點擊後 context 的 `result_id` 必須仍是 `R1`、stock code 必須仍是 `2330`；Journey 顯示同一 candidate 的 5／10／20／60 rows。
- 已成熟 horizon 顯示 ready；未成熟 horizon 顯示待成熟，不以目前日期補造 outcome。
- controls 顯示原 decision status、筆記與 reminder history；只讀取與點擊不增加 Journal revision。

### P2：成熟度更新不覆蓋原研究意向

同一 `R1:2330` 的 5 日 outcome 後來 ready、10／20／60 仍 pending；controls 原本為 `accepted` 並有 reminder。

驗收：

- Journey 的 5 日列更新為 exact ready，其他 horizon 保持各自狀態。
- `accepted` 不被 `review_scheduled` 覆蓋；原 reminder 仍可追溯。
- 使用者未明確追加新 action 前，Workbench 不自動把 due item 標成完成。

### P3：隔日重啟仍可讀同一歷史

關閉目前 UI，再以新的 process／session 讀同一份正式 output、Evidence 與 Journal。

驗收：

- 不依賴 `ResearchSessionStore` 記憶，仍能以 `R1:2330` 讀到 due state、decision history 與正式 maturity。
- `research_only=true`、personal records separate、effectiveness claim false、read-only 邊界仍成立。
- learning receipt 只作 learning evidence projection，不與 continuity action 或成交績效混算。

## 八、可驗收負案例

1. **缺 identity：** 只有股票代號、只有 legacy `source_id`、只有同股同日，或 `result_id` 空白；Workbench 不產生 continuity due item，Journey unlinked，controls disabled。
2. **cross-result／cross-stock：** Journal 是 `R1:2330`，目前 context 是 `R2:2330` 或 `R1:2317`；不得顯示 reminder、note、decision status 或 outcome。
3. **Portfolio 泛用來源：** `source_type=user_declared_research` 且 `source_id=holding_id`、`source_type=backtest_run` 且 `source_id=run_id`、`strategy_version` 或手動持倉；context 的 `result_id` 必須為空，不能開啟可寫 continuity controls，不得新增錯誤 revision。
4. **identity／provenance conflict：** snapshot ID/hash、decision date 或 nested／outer identity 衝突；projection 應為 unknown／conflict，不進 due queue，不猜測要綁哪個 result。
5. **未來資料：** outcome 還沒到 maturity horizon；顯示 `insufficient_future_data`／待成熟，不回填未來價格、不產生目前報酬或 effectiveness。
6. **Journal 或 Portfolio 缺資料：** formal Journey 可呈 partial／missing diagnostics；不可把缺資料解讀成 no outcome、成交失敗或交易建議。Portfolio event 必須保持與研究結果分開。
7. **手動交易無 exact recommendation source：** 可標示 `user_recorded_event_broker_fill_unproven` 或 unlinked，但不得把它變成 recommendation decision outcome、自然 evidence 或信用分數。
8. **自然 evidence revisit 混淆：** `ResearchFallbackPacket.revisit_date` 與 user `next_review_at` 不同時存在／日期不同時，兩者必須各自顯示，不得互相覆蓋。

## 九、最終驗收判定

目前可判定：

- **已接：** exact Recommendation result → shared stock research → DecisionOutcomeJourney；exact continuity action → existing append-only Journal；formal maturity → existing Evidence／outcome read model；H 與 I 的 research-only／separate boundaries。
- **未接：** continuity due／overdue → Workbench daily review queue；continuity action history → formal Journey read DTO／timeline；多 candidate 的 Workbench row-specific stock research selector。
- **需先修：** Portfolio 泛用 `source_id` → typed `result_id` 的錯誤 promotion。
- **等待 J：** PIT reader、Recommendation／industry 真實 caller 與 shared SSOT/index 的最終接線；本盤點不重做、不建立平行 storage。

在 R1 通過前，不能宣稱「使用者每日流程已從記錄決策、到期提醒、成熟 outcome、追加檢討到隔日學習完整閉環」；目前只能宣稱 exact candidate 的單頁研究與正式 outcome 對應已成立，daily reminder loop 尚未成立。
