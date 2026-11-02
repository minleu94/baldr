# Gate 1 日常 Advice 與保存讀回證據（2026-10-28）

## 本輪結論

Gate 1 的局部人工研究保存流程已用真正的 MainWindow／Workbench journal 寫入及新 controller 讀回驗證。正式資料唯讀服務已把同一個 2026-10-28 canonical result 載入 Daily Journey 與 Advice composer，並生成 3 筆 Advice；候選／事件 identity 已以完整來源集合核對。正式排程 wrapper 缺少 `source_snapshot_id` 時，Daily Journey 現只在精確 included-event cohort、日期、result、股票集合及策略／universe／回報基準身份一致時綁定同一 event snapshot；此 fallback 已由正式唯讀端到端重跑確認。該來源快照仍是 `estimated`、`research_only`，未授正式 credit，且 execution typed source/data snapshot refs 缺漏；來源資格與 Owner 原生 GUI UAT 尚未通過。

## 2026-10-28 正式 Daily Journey 端到端重驗

受控 Windows Job 以唯讀正式資料執行 `.tmp_gate1_formal_workbench_flow_20261028.py`，原始收據位於 `.tmp_gate1_owned_runs/daily_e2e_20261028/formal_recheck_20261028_182503_1e123534/`。流程通過，Job limits 讀回為 8 GiB／12 個程序、peak committed memory 約 1.51 GiB；程序自然結束、Job 與 child handles 關閉。結果確認：決策日／資料日均為 `2026-10-28`；3 筆 Advice（`1569`、`1560`、`1316`）共用 canonical result `rec_bc108d4d483a46f4bd758706e6fb8d37` 與 payload SHA `sha256:5b853bdb99170b4c34a702ed41c83a9dcbe1236ef5e184da8a81a33e8e9239dd`；candidate source snapshot 綁定到同一 result ID，完整列出流動性排除 180/180 檔、screening fail 394/197 檔、missing 197/197 檔、pass 9/3 檔及 why-not 197/197 檔，並保留各自 `data_quality`。

重驗找出 identity parser 漏讀 event metadata `return_basis`，使原本安全的 fallback 拒絕綁定；納入該欄位並補齊合成 event metadata 後，正式唯讀流程及 Daily Journey／scheduled producer 聚焦測試合計 **32 passed**；三個修改 Python 檔 `py_compile` 也通過。較長 basetemp 首輪曾出現 artifact `os.rename()` `FileNotFoundError: [WinError 3]`；改用短 repo basetemp 後此錯誤不再出現。短 basetemp 下兩檔較大回歸曾為 **46 passed／6 failed／0 errors**，其中 1 項是後續已修正的合成 event identity 缺欄，另 5 項在 sandbox 內對 pytest fixture 執行 strict Windows path resolution／原子 rename 時遇 `PermissionError: [WinError 5]`。將同一個兩檔 suite 放在受控 Job、明確 repo basetemp 並於可執行完整檔案操作的環境重跑後，原 strict path validation 保持不變，結果 **52 passed**；Job 限制讀回為 8 GiB／12 程序、peak 約 2.44 GiB，程序樹自然結束且 handles 關閉。這確認先前五項是 sandbox 檔案操作限制，不是 QA lock，也沒有留下產品 workaround。詳細收據：`.tmp_gate1_owned_runs/daily_e2e_20261028/full_daily_wrapper_escalated_recheck/run_20261028_183753_c5d15d16/`。

## 自動化流程證據

受控 Windows Job runner 執行：

```powershell
.\.venv\Scripts\python.exe scripts\qa_cross_page_mainwindow_owned_runner.py --output-root '.tmp_gate1_owned_20261028_03' --timeout-seconds 180
```

最新有效原始產物位於 `.tmp_gate1_owned_20261028_03/run_20261028_151648_409cb15d/`。wrapper 原先缺少 `as_of_date` 參數，context cutoff 保護在 worker 啟動前拒絕呼叫；補上相同 cutoff 的傳遞後重新執行，本輪結果如下：

| Case | 結果 | 證據與範圍 |
|---|---|---|
| `readback_writer_reader` | PASS，return code 0 | 真 MainWindow 重建後重新讀取保存推薦；`readback_receipt.json` 記錄保存讀回成功、身份一致、研究報告與 Journey 載入、精確身份可見。使用隔離的合成推薦 fixture。 |
| `advice_manual_decision_readback` | PASS，1 passed，return code 0 | 在 Workbench Advice 對候選按「略過」，寫入隔離 JSONL journal；新建 `JournalService`／controller 後精確讀回結果 ID、股票、決策日、來源 snapshot ID、決定狀態與 history identity；未建立交易檔。 |
| `busy_close` | PASS，return code 0 | `busy_receipt.json` 證實真 MainWindow 的 report worker 到達 barrier 後，送出一次 busy 時 close；close 被延後至 cooperative cancellation／worker 完成後結束。worker 已收完、未強制終止、watchdog 未觸發。 |

Runner 設定並讀回 Windows Job 的 8 GiB committed-memory 上限與 12 個程序上限。三案峰值 committed memory 分別約 2.65、1.29、1.29 GiB；三個程序樹自然結束且 child handles 關閉。整體 runner 本輪全 PASS。此前 fixture 缺少 cutoff signature 的 FAIL 已由本次修正與重跑取代。

## 正式資料唯讀對照

透過唯讀 Evidence／SQLite 工具查得：

- Decision Desk active snapshot：`dds_797a9a2c12ed80f0`，決策日與資料日均為 `2026-10-28`，`data_quality=estimated`；capture 為 `eod_research`，時間 `2026-10-28T20:25:03.313068+08:00`。
- 同日推薦來源快照：`rec_bc108d4d483a46f4bd758706e6fb8d37`。3 筆 `recommendation_included` 為 `1316`、`1560`、`1569`，日期均為 `2026-10-28`，三筆都帶同一推薦來源 ID／snapshot ID。
- 以正式唯讀 `ScheduledEvidenceStatusService`、`DecisionDeskSnapshotRepository(read_only=True)`、`DailyInvestmentJourneyService` 與 Workbench Advice composer 重跑後，Daily Journey 的候選 result ID 為上述 canonical ID，候選狀態為 `candidate`，不再出現 `daily_candidate_event_identity_mismatch`；Advice composer 輸出 `1569`、`1560`、`1316`，三列來源 result ID 與 payload SHA 都相同。這證明正式 read model／composer 路徑能讀到同一結果，不代表已完成原生 GUI／Owner UAT。
- 修正原因：事件 identity 原本從顯示用 `source_trace` 搜尋，而該 trace 只保留前 20 筆；完整 evidence 有 56 筆，當日事件可能落在截斷範圍外。現在檢查完整的 `source_id`／`source_snapshot_id` 集合。先前整檔 28 passed、focused 32 passed 與最新兩檔 52 passed 都有各自收據；較大 suite 的 sandbox 權限問題已在上方以原 strict path validation 重驗排除。
- Canonical execution 的 typed `context.source_refs=[]`、`context.data_snapshot_refs=[]`。不過 execution event 另保存同次 `legacy_invocation_context`／`market_data_provenance`：來源標籤 `DefaultRecommendationMarketDataProvider`、資料日 `2026-10-28`、market fingerprint `2fa92d3e14d8297683d9f20945b05a5668e0c8ec29c7370b99ecbcfcefd9c6e5`；`current_fundamental_lineage.v1` 記錄 expected market date `2026-10-28`、日曆狀態 `current`、cutoff `2026-10-28T12:10:06.843254+00:00`，並列出 0 requests、0 facts、0 diagnostics。`recommendation_invocation_clock_capture.available_at=2026-10-28T12:10:26.446451+00:00`、`decision_at=2026-10-28T12:11:05.590232+00:00`。正式 `daily_prices` 表的欄位只有日期、代碼、價量與技術指標，沒有來源 ID／版本或逐列可得時間；因此同次執行有日期與指紋線索，也能確認這筆沒有讀 PE／月營收 fact，但泛用 provider 標籤、缺 typed source/data snapshot refs 及缺來源列可得時間，仍不足以作正式 source／PIT 接受。
- 同一推薦快照另有 180 筆流動性排除、197 筆 screening missing、394 筆 screening fail、9 筆 screening pass，以及 197 筆 why-not 事件。流動性排除原因為 `liquidity_volume_ratio_below_min`。
- 2026-10-28 以精確 `decision_date`、`source_id`、`source_snapshot_id` 唯讀重查：流動性排除 180 筆／180 檔（品質 `missing`）；screening fail 394 筆／197 檔、missing 197 筆／197 檔、pass 9 筆／3 檔（以上品質均為 `missing`）；why-not 197 筆／197 檔（品質 `observed`）。事件摘要仍保留事件數與唯一檔數的差異，且不把篩選事件品質缺值解讀成來源已接受。
- 直接以 `EvidenceEventRepository(read_only=True)` 對正式 `twstock.db` 呼叫新摘要器，結果 `diagnostics=()`；畫面預期的 fail 理由碼為 `liquidity_volume_ratio_below_min` 360、`strategy_filter_no_signal` 34，missing 為 `not_ranked` 197，pass 為 `recommendation_selected` 6、`candidate_scored` 3，why-not 為 `liquidity_volume_ratio_below_min` 180、`strategy_filter_no_signal` 17。正式 DB 仍唯讀；此為程式／資料顯示對照，不是原生 GUI／Owner UAT。
- 這些候選及排除事件確實共享同一 source snapshot；但 screening matrix 事件的 `data_quality` 仍為 `missing`，故通過／失敗事件數不能直接當成已接受的來源品質證據。
- 來源 capture 標示 `research_only=true`、`natural_authority=false`、`preopen_authority=false`、`formal_credit_granted=false`。事件中亦有 legacy source identity 未綁定警告。這些都是限制，不是正式授權。

本輪已由正式唯讀服務確認 Workbench Advice composer 可載入並生成同一 canonical result 的 Advice；來源與資料快照引用缺漏時，Advice warnings 現會明確顯示來源／PIT 尚未核驗且不代表來源資格已通過，並保留候選輸出。Workbench source service 聚焦測試 11 passed；UI 將 Advice warnings 顯示於可選取文字的警告狀態欄。正式 Evidence DB 同快照的排除／篩選事件現在接入「每日來源詳情」唯讀摘要；摘要按事件數呈現，明示同股可有多筆，並保留 `missing` 品質及缺身份／缺事件／截斷警告。程式測試證明只彙總 exact source snapshot，其他 snapshot 不會混入；目前尚未對此新區塊執行原生 GUI／Owner UAT。尚未驗證該推薦來源的正式 PIT／來源接受。所有正式資料查詢均為唯讀，沒有改寫正式 DB。

本次排除摘要變更驗證：repository／每日旅程／每日詳情 UI／read-only dashboard repository 聚焦套件 **45 passed**；必要 Workbench UI 回歸 **97 passed**；Update validator **25 passed／0 failed／4 skipped**；本次修改 Python 檔 `py_compile`、`git diff --check` 與 5 個應用模組定向 mypy 通過。Gate QA 與架構文件的 scoped document-control check 各為 12 features／1 link source／0 errors。手冊 scoped check 被兩個既有 `../../output/trial/.../TRIAL_GUIDE.md` junction 引用的 Windows `WinError 5: Access is denied` 阻擋；該共享輸出目錄未修改。必要 repo-wide mypy 執行未能完成檢查，仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 因既有語法錯誤停止；這不是本次變更引入的錯誤。未執行原生 GUI／Owner UAT。

本次更新後 QA 收據與 PROJECT_SNAPSHOT 各自的 scoped `document_control check --path ...` 都通過（各 12 features／1 link source／0 errors）。Snapshot 的一般 sandbox 檢查先遇到 `output` junction `WinError 5`，在可讀取該共享 junction 的唯讀環境重驗後通過；共用試用／任務產物連結沒有改動。

## 正式 Advice 必要欄位補齊與盤點

對 canonical result `rec_bc108d4d483a46f4bd758706e6fb8d37` 的正式 3 筆 Advice 欄位盤點發現：原 Advice DTO 有 `confidence_tier`、`evidence_tier` 欄位，但當次三列值皆為空；Workbench 顯示「未提供」，完整度提示也把它們列為欄位待核對。這是真正的 Advice completeness 缺口，與月營收採集無關。

本次修正讓 Advice composer 對沒有可用校準分級的列明示 `confidence_tier=unavailable`，並在沒有成熟度來源欄位時明示 `evidence_tier=insufficient`；不從規則分數推導信心、不把 tier 當勝率。Workbench 將明確的 `unavailable` 視為已提供狀態值，畫面顯示「不可用」並註明沒有可用校準分級、不可解讀為勝率；明確未知／未提供狀態與真正空欄分開計數，仍逐項列出限制，沒有把它們解讀為證據可用。真正空欄及缺少來源追溯仍待核對。成熟度標籤「證據不足」僅代表目前沒有可用成熟度證據，不替代來源／PIT 資格接受。

同一 canonical result 的唯讀 Workbench read model／Advice composer 已重跑，三列 `1569`、`1560`、`1316` 都帶 `confidence_tier=unavailable`、`evidence_tier=insufficient`、決策日／資料日 `2026-10-28`、精確 result ID `rec_bc108d4d483a46f4bd758706e6fb8d37`、相同 payload SHA 及 source trace。完整度提示三列都回報「Advice 核心欄位與來源追溯可判讀」，將市場狀態／流動性／可成交性的明確 unknown 另列限制；必要核心欄位與來源追溯無空欄。選填作者欄位仍明示未提供，不阻擋 Advice。只讀盤點 raw：`.tmp_gate1_formal_advice_readonly_retry3_20261028/run_20261028_155315_639d0992/formal_advice_readonly_audit/stdout.log`。Dashboard 的 `portfolio_result_missing` 是無 Portfolio 輸入的診斷；Gate 1 帳戶無關策略 Advice 不依賴 Portfolio，沒有因此阻擋三筆 Advice。

本次修正後受控回歸 `tests/test_advice_composer.py`、`tests/test_ui_qt_workbench_view.py`、必要 `tests/test_ui_qt_update_view_workbench.py` 合計 **189 passed**；Update validator **25 passed／0 failed／4 skipped**；`app_module/advice_composer.py`、`ui_qt/views/workbench_view.py` 兩檔 targeted mypy 無錯；修改 Python 檔編譯通過。Repo-wide mypy 仍被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋，未改動該月營收檔案。正式資料 DB 只讀；仍未做原生 GUI／Owner UAT，也未接受正式 source／PIT。

## 月營收與目前 Advice 的依賴判讀

目前程式碼中的 scheduled Advice 路徑由 `WorkbenchSourceService._inspect` 取得每日旅程與 `recommendation_read_model`，再傳給 `_compose_scheduled_candidate_advice`／`AdviceComposer`；組成端沒有直接讀取 `fundamental_monthly_revenues` 或傳入月營收資料。生成端也由本次保存 execution 交叉確認：10/28 canonical result 的 scheduled config 未設 `pe_ratio_max` 或 `monthly_revenue_yoy_min`，`current_fundamental_lineage.v1` 的 `requests=[]`、`facts=[]`，所以這筆候選沒有向來源請求 PE 或月營收。10/28 active Decision Desk snapshot 的 `fundamental_diagnostics_json` 為空物件 `{}`。唯讀查詢的正式月營收表共有 246,331 列、1,849 檔、147 個期間，242,650 列缺公告日，最新 `created_at` 為 `2026-08-26 23:42:12`。

因此，對 10/28 這筆 scheduled Advice，月營收公告採集不是其生成或 Advice 組成的直接前置，兩條工作可獨立推進。仍未接受的是市場來源的正式身份／逐列 available-at／PIT 與 screening matrix 缺值，不是等月營收採集完成。工作樹中的 `harvest_mops_monthly_revenue_events.py` 只寫 raw／manifest／events 輸出，沒有接入正式月營收表；本輪沒有執行該採集器。

## Gate 1 證據狀態

1. 正式 local Daily Journey／Advice 讀取流程已由上述唯讀端到端重驗閉合：在 canonical execution 無 typed `source_snapshot_id` 的現況下，必須先以完整 included-event cohort identity 推得唯一 snapshot，再顯示精確同快照排除摘要。scheduled producer 後續明確輸出 `source_snapshot_id=result_id` 的 contract test 已通過；Daily Journey 與 scheduled wrapper 兩檔完整回歸 **52 passed**。隔離 fixture 的 MainWindow 保存讀回與 Advice journal fresh-readback 仍已驗證；它們不替代 Owner 原生 GUI UAT。
2. **已完成：**凍結行情 frame、策略參數與 Advice policy，以真正的 `RecommendationService`／`StrategyConfigurator` 從行情重算推薦，再由 `AdviceComposer` 生成 Advice；建立兩個全新 service instance 重播，推薦與 Advice 的 canonical JSON 完全一致。固定輸入 SHA-256：行情 `b42ccfd6…501d7d8`、策略 `20f40e6c…efd679a1`、Advice policy `c5b4dbfb…889f1b56`、合併 input `749d766d…f027edc`；輸出 SHA-256：推薦 `972304b8…bebd51b4`、Advice `e474fb2d…9e6661b`。受控 Windows Job 執行 `tests/test_gate1_deterministic_advice_replay.py` **1 passed**，8 GiB／12 程序限制、啟動前可用記憶體、Job 與 child handle 均讀回確認，peak 約 1.21 GiB。這證明固定合成資料／策略／policy 下完整推薦計算至 Advice 的重播一致，不是正式來源接受或正式行情品質證據。
3. 由 Owner 在原生 GUI 實走並確認決策日、資料日、候選、明確排除、Advice 限制與 evidence 都連回同一個 canonical result／snapshot；程式層唯讀 read model／composer 與隔離 journal fresh-readback 已確認，Owner GUI 尚未驗收。
4. 正式 source／PIT 接受屬於 Gate 3，不是 Gate 1 Advice 輸出的前置條件。現有 10/28 capture 為 `estimated`／`research_only`、`formal_credit_granted=false`，source ID 是泛用 provider class，沒有逐列來源 `available_at`，screening matrix 品質仍為 `missing`；Advice 必須繼續明示這些限制。只有補上來源用途所需證據並完成 Gate 3 評估後，才能宣稱來源已接受。

### Owner 原生 GUI UAT 檢核卡

以 Workbench／今日總覽開啟 `2026-10-28` 這筆結果，逐項核對並記錄通過或畫面實際值：

1. 今日總覽與 Advice 摘要的決策日、資料日都顯示 `2026-10-28`。選取 Advice 列後，按「回查這筆保存推薦結果」；確認按鈕提示中的 result ID 為 `rec_bc108d4d483a46f4bd758706e6fb8d37`、payload SHA 為 `sha256:5b853bdb99170b4c34a702ed41c83a9dcbe1236ef5e184da8a81a33e8e9239dd`，並確認開啟的是該保存結果。
2. Advice 列為 `1569 濱川`、`1560 中砂`、`1316 上曜`。按「查看每日來源詳情」，核對候選 result ID、source ID／snapshot ID 與 why-not／排除事件摘要；它們應指向同一推薦快照。事件數不是唯一股票數，並確認 screening missing 顯示品質 `missing`，不把 pass／fail 事件當成來源品質接受。若畫面日期、候選或來源身份不同，記錄差異並停止把該畫面當作此收據的通過證據。
3. 核對警告明確說明 Advice 是人工研究判斷、不會自動下單，且來源／PIT 資格尚未核驗、不代表來源資格已通過；同時確認來源 snapshot 為 `estimated`／`research_only` 且 formal credit 未授權。
4. **已由 Owner 回報完成（2026-10-28，1569）：**按「記錄已納入研究」後顯示「已保存並讀回核對」，狀態為已納入研究、Journal 紀錄 0 筆、下次檢視未設定；再按「重新讀取同筆決定」顯示「同筆狀態已讀回」，狀態、註記數與下次檢視相同。兩次都核對 `result_id=rec_bc108d4d483a46f4bd758706e6fb8d37`、股票 `1569`、決策日 `2026-10-28`；畫面標示來源 snapshot ID 已提供、hash 未提供。這是 Owner 回報的 UI 證據，非本端重新操作。排程來源若明確將來源 snapshot ID 綁定為同一 result ID，兩欄可保留相同值；仍須確認它們各自來自明確來源欄位，不能由缺值推定。
5. 開啟「研究時間軸」，來源篩選選「研究決定」，搜尋 `1569` 或 `rec_bc108d4d483a46f4bd758706e6fb8d37`；確認找到剛保存的「已納入研究」紀錄，股票、result ID、決策日與來源 snapshot ID 相符。此列是唯讀歷史，不需要候選仍出現在今日 Advice。
6. 保存 UAT 結果、Owner、時間與任何不符欄位。這張檢核卡驗證 UI 與人工決定閉環；不替代來源／PIT 接受，也不授權交易或正式資料寫入。

2026-10-28 後續可發現性修正：研究時間軸 read model 現在也索引 Journal 的納入／略過／檢視 revision；可用股票代號或 result ID 找回，不依賴候選再次出現在 Advice。選取歷史決定只顯示唯讀身分與 revision，不提供筆記原件、Evidence 對照或 Paper 操作。`tests/test_research_timeline_service.py`、`tests/test_ui_qt_research_timeline_view.py`、必要 Workbench UI suite 合計 **137 passed**；再加入人工決定 controller、Advice fresh-journal readback 與 timeline 聚焦 suite **48 passed**，其中新增測試明確覆蓋 `source_snapshot_id == result_id` 的保存／新 Journal 讀回。受控 cross-page MainWindow runner 新增從主視窗路由讀回歷史決定的同流程核對，最後一輪 **3 cases passed**（MainWindow cross-page、Advice journal fresh-readback、busy-close）；MainWindow case peak 約 2.66 GiB。最初兩輪失敗在測試 helper 的子頁按鈕狀態未同步（最後一輪改用 ProductShell 的實際 route activation），不代表產品功能失敗；原始收據保留於 `.pytest-owned-temp/gate1_mainwindow_discovery_20261028/`、`_retry/` 與 `_final/`。Update validator **25 passed／0 failed／4 skipped**；八個 Python 檔 `py_compile` 通過，三個受影響模組 targeted mypy 無錯。所有受控 Job 讀回 8 GiB／12 程序上限，程序自然結束且 Job／child handles 關閉。Repo-wide mypy 仍被未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤阻擋。這些仍是隔離測試證據，不是 Owner 原生 GUI 驗收。

2026-10-28 原生 GUI 隔離查找核對：以目前開發版原生 Baldr 主視窗啟動，`DATA_ROOT`、`OUTPUT_ROOT`、研究狀態與本機設定全指向 `.pytest-owned-temp/gate1_native_ui/`；正式 Journal 僅讀取並複製該 `result_id` 的單一紀錄到隔離輸出，未寫入正式資料。隔離資料沒有今日 Advice 候選時，首頁仍顯示最近研究 `1569`；進入「我的投資」→「研究紀錄與覆盤」，來源篩選「研究決定」後，分別以 `1569` 與 `rec_bc108d4d483a46f4bd758706e6fb8d37` 搜尋，都找到同一筆「已納入研究」，其 result ID、決策日、來源 snapshot ID、revision ID 與 Journal 紀錄相符。這證明目前開發版原生畫面的歷史查找路徑可用，但因使用隔離資料與複製紀錄，不算 Owner 對正式環境的 UAT；正式環境 Owner UAT 第 1–3 項及第 5–6 項仍待完成。

2026-10-28 原生 GUI 初次點選「記錄已納入研究」時，畫面回報 `source_snapshot_id must not reuse result_id`，人工決定未保存。根因是 scheduled producer 明確以同一 result ID 作 included-event source snapshot identity，而 `DecisionIdentity` 額外拒絕這個有效明示綁定。現已移除該 ID 值相等限制，保留 result／snapshot 為不同明確欄位且不作互相推定，也保留 snapshot hash 不得重用 result ID 的檢查。Owner 隨後回報 1569 研究決定保存成功並精確讀回，完成 UAT 檢核卡第 4 項；`test_explicit_snapshot_id_equal_to_result_id_survives_journal_reopen` 現已明確覆蓋同值 snapshot ID 的保存與新 Journal 讀回，連同 controller、Advice fresh-readback、timeline service／UI suite **48 passed**。Owner UAT 第 1–3 項及第 5–6 項仍待正式環境核對，Gate 1 Owner UAT 整體尚未結案。

因此本收據已有程式層 Advice 路徑、正式唯讀 Daily Journey／Advice／事件同快照流程、固定資料／策略／policy 的完整推薦至 Advice deterministic replay、人工研究決定保存／讀回、busy-close 與本次不使用月營收的證據。Gate 1 剩餘 Owner 原生 GUI UAT 由 Owner 完成；Gate 3 的正式資料來源／PIT 接受仍未完成，Advice 持續明確揭露限制。

## 2026-10-28 500 筆清單上限下的完整歷史查找

研究時間軸一般清單最多呈現最新 500 筆；達上限後，搜尋欄輸入股票代號或 result ID 會改由 service 篩選完整 Journal 歷史，再呈現符合項目。搜尋結果若仍超過 500 筆，會提示使用完整 result ID 縮小範圍。故即使較早的研究決定不在一般清單中，也可依股票或保存推薦身分回查；這不依賴候選再次出現在 Advice，也不重建 Advice 或修改 Journal。

受控 Windows Job 中，`tests/test_research_timeline_service.py` 與 `tests/test_ui_qt_research_timeline_view.py` **41 passed**，必要 Workbench UI suite **98 passed**；新增服務案例以 501 筆決定確認最舊項目不在一般清單時，仍可用股票代號及 result ID 找到。Update validator **25 passed／0 failed／4 skipped**；4 個修改 Python 檔 py_compile 通過，2 個修改模組 targeted mypy 無錯。每個 Job 均讀回 8 GiB committed-memory／12 程序限制及至少 8 GiB 啟動前可用記憶體，child 與 Job handles 關閉；兩個 UI 測試 Job peak 約 1.21 GiB、1.56 GiB。Repo-wide mypy 仍因未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 語法錯誤而停止，無法檢查其餘模組。此 QA 文件的 scoped document-control check 通過（12 features／1 link source／0 errors）；同時檢查操作手冊與 Snapshot 時，既有 `output` junction 引用遭 sandbox `WinError 5` 拒讀，未改動共享輸出。這是隔離測試證據，不替代 Owner 對正式環境的 GUI UAT；Owner UAT 第 1–3、5–6 項仍待完成。

## 2026-11-02 Owner 原生 GUI UAT 與 Gate 1 限定範圍接受

Owner 在目前 Baldr Workbench／「今日策略建議」完成原生 GUI 核對，並提供當日唯讀來源摘要及保存結果回讀：決策日與行情資料日均為 `2026-11-02`；Advice 共 5 筆（`1416`、`1528`、`1456`、`1232`、`1235`），未升格 Advice 0 筆、配置資料列 0 筆。展開 `1416` 卡確認動作為「新增候選」、規則分數 `81.65`、決策理由可讀，confidence 明示不可用、風險／成交能力未核實，資料日及 `observed` 品質可見；畫面清楚說明 Advice 僅供人工研究、不會自動下單，來源／PIT 尚未核驗。

當日來源唯讀摘要回讀結果 `rec_ab35aaa1276841879f706f9d4e10486a`，決策日及行情資料日均為 `2026-11-02`；5 筆候選與 Advice 清單相同。候選來源 ID、篩選／排除事件 `result_id`、`source_id`、`source_snapshot_id` 均指向同一結果 ID；Owner 隨後從「綜合選股｜保存推薦結果」回報讀回相同 `result_id`。因此此筆 Advice 至保存推薦結果及 included-event cohort 的身份鏈在 Owner UAT 中對齊。

限制照原樣保留：來源摘要的全市場分母未提供；篩選事件品質為 `missing`（包含篩選通過事件），不得推論來源完整或正式接受；5／10 日 maturity 各缺漏 22 筆，20／60 日仍有待成熟／缺漏；Advice 顯示來源與 PIT 資格尚未核驗、完整 typed source/data snapshot refs 未齊。這些限制在畫面／來源摘要中有明確揭露。Owner 另以「我的投資 → 研究紀錄與覆盤」找到既有 `1569` 研究決定，核對其 `result_id=rec_bc108d4d483a46f4bd758706e6fb8d37`、決策日 `2026-10-28`、來源 snapshot ID 與 `accepted` 狀態；這是既存 Journal 記錄，未要求新增決定。

依 Gate 1 可在 read-only／paper mode closeout、而 Gate 3 負責正式來源／PIT 接受的邊界，Owner UAT **接受 Gate 1 日常 Advice 流程（read-only／paper 限定範圍）**。此接受不包含正式來源／PIT／全市場 coverage 資格，不授權 production evidence scheduler、真實交易或任何來源／資料寫入。Gate 0 歷史 closeout 由 Owner 於 2026-11-02 接受作為 Gate 1 前置。UAT 依據為 Owner 提供的 2026-11-02 Advice 與時間軸畫面、唯讀來源摘要文字及保存結果 ID 回報；本次狀態更新沒有重跑程式測試或寫入正式資料。
