# Learning Evidence Workbench QA 紀錄（2026-09-14）

## 結論

本輪已完成一個可審查的唯讀增量：Workbench／Research Console 會以 typed candidate、active、prediction-capture verifier 的 projection 顯示 learning evidence、成本 lane、日期 freshness、horizon scope、樣本與下一個缺口。工程驗證通過；這不是 promotion、正式推薦或交易授權。

目前實際資料仍未形成可授予 natural evidence credit 的成熟樣本：臺銀 lane 等待後續自然 forward capture，legacy lane 的既有 candidate 則因來源追溯衝突而 blocked。UI 因此保留 pending／blocked／unknown，不以 replay、fixture 或缺 receipt 的 capture 補值。

本輪再完成 Research fallback packet：每日 Workbench evidence 不足時，沿用既有 daily journey／learning projection 的 result、stock、決策日、source identity、cost lane、原因與 horizon，顯示缺什麼、下一個研究問題、可操作的唯讀下一步、再看日期或未知理由，以及禁止的判讀。packet 不新增資料表、不執行 scheduler／runner、不要求 approve，也不產生機率、score、權重或交易結論。

## 範圍與安全邊界

- 入口：`app_module/recommendation_learning_evidence_projection_service.py`、`app_module/workbench_source_service.py`、`ui_qt/views/workbench_view.py`、`ui_qt/views/research_console_view.py`、`ui_qt/main.py`。
- authority boundary：`ml_module/recommendation_calibration_authority.py` 的 `verify_natural_evidence_read_only` 與 `ml_module/recommendation_calibration_evidence.py` 的 `verify_prediction_capture_read_only`；兩者只讀、只驗證，不寫 receipt／pointer、不 promotion、不改正式 Recommendation／Portfolio、不下 broker order。
- candidate／active／capture 與 cost scenario 必須同 lane、同 candidate／model identity、同決策日及同 source contract；horizon 統計只取單一選定 lane，不能跨 candidate／active 或跨成本情境合併。
- Workbench 的 dashboard decision date 會傳入 Research Console；未明示日期時只接受可信的臺灣官方交易日 resolver。日曆不可用或日期不明時顯示 `unknown`，不以 learning receipt 的最新日期冒充今日。

## Recommendation／Advice 機率來源契約稽核

本輪另外核對正式 Recommendation producer 到 Advice／Portfolio read model，再到既有
Workbench renderer 的機率欄位。`RecommendationService` 只把既有
`RecommendationCalibrationConsumer` 的 frozen `RecommendationCalibrationProjection` 逐欄
注入 RecommendationDTO；`AdviceComposer` 現在拒絕 bare mapping，以及缺
model／dataset／horizon／cost／source 或 stock scope 不一致的 projection。這個 shape／scope
gate 不等於 natural verifier；candidate／active projection 仍只可標研究／shadow。

| 量 | 可用研究判讀 | 不可推出 |
|---|---|---|
| ranking score／percentile | 只作排序；Presentation 與 Workbench 另列 ranking method／percentile。 | 不可由 7200 或 80 分推導 80% 上漲機率。 |
| calibrated probability | typed consumer 的整數 bp output；需同時看 model、dataset、20 日 horizon、sample、transform／baseline、source trace。 | `status=available`、`verified` 字串、hash 或 shadow receipt 不等於 natural validation。 |
| after-cost probability | 只讀同一 projection 的 after-cost 欄位與 cost scenario；臺銀 estimate 保留 research-only／slippage 未建模限制。 | 不可與另一 candidate、另一成本 lane 或另一 horizon 混接，也不可冒充 observed fill。 |
| historical calibration | `recommendation_calibration.py` 的 walk-forward／untouched-test 結果可作歷史研究；有明確 historical／replay source 時 presentation 顯示「研究中／歷史研究」。 | 不可併入 natural matured sample、formal Advice 或 promotion credit。 |

隔離驗收 `test_isolated_producer_consumer_advice_workbench_ui_path` 確認正式
RecommendationService adapter→typed projection→Advice→Workbench 可讀到 ranking `7200`、校準
`58.00%`、成本後 `57.00%`、20 日、sample `120`、model／dataset 與 shadow label；
`test_real_consumer_producer_advice_workbench_ui_path` 再使用最小隔離 pointer／artifact 呼叫真正
`RecommendationCalibrationConsumer`，確認 RecommendationService 只有在 active candidate metadata
明示既有獨立 `after_cost_null_benchmark_50pct_v1`／`5000 bp` contract 時才傳入該 baseline；本測試
fixture 是 declared-but-unpriced baseline，因此成本後值保持 unavailable，且錯誤混用 ID 會
fail-closed。`test_real_consumer_independent_after_cost_baseline_reaches_advice_presentation` 再用
實際 training artifact／authority 建立 independent-null candidate，驗證 real consumer→RecommendationService
→Advice→Presentation 的成本後值、獨立 baseline trace 與 5,001 bp 反例；前一個 isolated wiring
case 則補 Workbench renderer 的正常可用案例。這些 artifact 均在 pytest `tmp_path`，不寫正式資料。
raw payload 與缺 scope 反例則維持 unknown。自然 lane 仍依
本文件既有 verifier／maturity QA 判讀，不因 UI render 或 typed DTO 存在而升格。

## Research fallback packet 增量

`ResearchFallbackPacket` 是 `WorkbenchDailyEvidence.research_fallback` 的 frozen、read-only DTO。它以 `decision_date + result／stock + source_id／source_snapshot_id + cost_lane` 組成 scope key；同日不同來源或成本 lane 不會在 packet 層合併。既有 source 沒提供 owner 時固定保留 `未知（既有來源未提供 owner）`，不把 source ID 猜成 owner。

狀態分流如下：

- `pending_capture`：本日 capture 尚未記錄或尚未能核對。
- `pending_natural_evidence`：同一 capture／forward evidence 尚待自然成熟；只有精確 join 的 pending EvidenceEvent 原決策日、正整數 horizon 與可解析 `OfficialTradingCalendar` 都存在時，才估算 `revisit_date`。
- `blocked_identity_or_cost`／`blocked_provenance`／`blocked_scope`：身份、成本、lineage 或日期 scope 受阻，`revisit_date` 保留未知。
- `missing_data`／`read_failure`／`missing_source`：缺少 candidate、EvidenceEvent／Outcome、projection 或唯讀路徑失敗；不把零事件或讀取失敗當成零風險。
- `not_needed`：同一 scope 已有 typed natural evidence verifier 結果；這不是新的 Advice 或交易授權。

回看日期固定以同 scope pending event 的原決策日計算；每日重新查看同一 pending cohort 不會把日期向後漂移。若沒有唯一 anchor、horizon 不是正整數、官方交易日曆回傳 unknown 或只剩 historical replay／evaluation，packet 顯示 `unknown`，不以日曆天數或 Workbench 查看日假造。Historical replay 可以另作研究比較，但不能與 natural evidence 混算。所有 packet 固定 `read_only=true`、`write_intent=false`、`positive_fallback_allowed=false`。

本輪新增／更新的可重跑驗收：`tests/test_research_fallback_packet.py`（scope 隔離、pending／blocked 分流、原 anchor 穩定、future event 排除、owner unknown、horizon 驗證、historical 限制與 readonly contract）、`tests/test_ui_qt_research_fallback.py`（首屏摘要／展開詳情／無 approve）與 `scripts/qa_validate_research_fallback_qt.py`（實際 production theme Qt offscreen 的四種 fixture PNG）。screen fixture 只證明 render，不宣稱正式 natural lane 或完整 production reader→projection→UI。

本輪 Research fallback 驗收分開記錄：`tests/test_research_fallback_packet.py tests/test_ui_qt_research_fallback.py` 為 `13 passed, 1 warning`（功能／UI）；`tests/test_daily_investment_journey.py` 為 `6 passed, 1 warning`（daily service）；`tests/test_ui_qt_daily_journey.py` 為 `2 passed, 1 warning`（daily UI）。warning 都是既有 `.pytest_cache` permission warning。

## Increment B：研究操作、append-only 紀錄、跨頁讀回與自然 evidence

Increment B 的邊界是「把明示的 recommendation／stock／snapshot identity 帶入研究操作，
並能在頁面往返後讀回同一條 continuity」；它不等於 V4 formal maturity，也不把只讀
learning projection 當成 user decision。依目前 A／D 增量，狀態如下：

| 面向 | 目前已完成／可核對增量 | 仍缺的 B gate |
|---|---|---|
| 研究操作 | 個股研究報告已能以 `ResearchStockContextDTO.result_id` 開啟唯讀 Decision → Outcome Journey；Workbench → Research Console 也已綁定明確決策日與成本 lane。畫面沒有 Apply、Trade 或 implicit accept。 | B 的 accept／skip／note／next-review 操作尚未完整接到每個研究入口；不能因畫面可讀就產生 user decision。 |
| append-only 紀錄 | Increment A 已提供 `DecisionIdentity`、候選池 revision／tombstone、研究 journal revision、idempotency／optimistic-concurrency 與 unknown／conflict 契約；歷史資料不靠猜測 backfill。 | B caller 仍需在每個明確操作傳入 exact result／stock／snapshot identity，並將操作寫入 A API；不得以 stock／date／排序補 key，也不得把操作轉成 trade／broker event。 |
| 跨頁讀回 | Journey read model 以 exact result／candidate／event identity 分開讀回 Evidence、outcome、Journal、精確 Portfolio ledger 與 legacy trades；5／10／20／60 horizon 的 linked／maturity 狀態可見，研究 return 與個人交易分離。 | Recommendation → Research → Watchlist／Portfolio → Workbench 的完整 B round-trip、返回後 exact context、review history head 與 UI action result 尚未由同一條 production workflow 全部驗收。 |
| natural evidence | 本輪 typed candidate／active／capture verifier 與 BankTaiwan／legacy projection 已完成；Research Console 會保留 pending／blocked／unknown，真實 BankTaiwan lane 仍無 matching current capture，legacy lane 仍 provenance blocked。 | 自然 forward capture、後續成熟 outcome、同 candidate／同成本／同 source custody 的有效 receipt 仍須由真實時間累積；UI／append-only decision 不會增加 natural sample，也不解除 formal／promotion gate。 |

因此 B 目前是「A persistence contract + D read-only journey + 本輪 learning read model」的
分段完成狀態；尚未宣稱 B 的完整操作 round-trip，更未宣稱 V4 formal／投資有效性完成。

## 實際資料唯讀觀察

| lane | learning root | 最新觀察 | 判讀 |
|---|---|---|---|
| 臺銀公開成本研究（預設） | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning` | candidate `rec-cal-b48b793f35280ce0ff9d5109`；`cost_scenario_id=banktaiwan-electronic-estimate`；`retain_current`／`natural_forward_evidence_receipt_missing`；active pointer 為 none | `pending`；沒有 matching current capture，natural matured sample 為 0。估算成本維持 `estimated_research_only`。 |
| Legacy 固定 50bp（獨立 lane） | `D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning` | candidate `rec-cal-29c1b6129396a3885a89d080`；既有 status 含 `cross-capture feature/source conflict: 1528`；`retain_current` | `blocked_provenance`；不與臺銀 lane fallback 或混算。 |

上述路徑、candidate、receipt 與 pointer 均為現有 shadow output 的 query-only readback；本輪沒有執行 producer、pipeline、scheduler 或資料重建。

## QA case map

| case | 覆蓋內容 | 結果 |
|---|---|---|
| authority receipt race | verifier 完成後 receipt bytes 被替換 | 通過；回報 `natural_evidence_receipt_changed_after_verification`，不標記 verified。 |
| cost scope | candidate／active 與選定 lane 的 scenario 不一致 | 通過；`blocked_cost_scope`，不跨 lane fallback。 |
| failure branch | candidate verifier 失敗且仍有 capture | 通過；保留 typed blocked diagnostics，未再觸發 duplicate-keyword failure。 |
| capture provenance | 缺日期、改 rows、historical origin、錯成本、有效 pending capture | 通過；分別維持 blocked／unknown／pending／recorded 語意。 |
| freshness | explicit stale、future、stale capture、週末 official-session contract、resolver unknown | 通過；只使用目標決策日；未知時不推斷 current。 |
| horizon scope | candidate 20 samples／2 dates 與 active 10 samples／10 dates | 通過；不產生合成的 20／10 統計，兩個 lane 各自保留 scope。 |
| UI date binding | Workbench dashboard date → Research Console projection | 通過；Research Console 收到明確的 `2026-09-14`／切換後 `2026-09-01`。 |

聚焦測試指令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_recommendation_learning_evidence_projection.py tests\test_ui_qt_research_console_view.py tests\test_ui_qt_workbench_view.py tests\test_daily_investment_journey.py tests\test_workbench_source_service.py -q -o addopts=
```

結果：`72 passed, 1 warning`。唯一 warning 是 pytest cache 目錄的既有 permission warning，不是測試失敗。

本輪 changed Python files 的 `py_compile` 通過。此前在 A／D public modules 恢復前的全域指定 mypy `Success: no issues found in 611 source files` 僅作歷史觀測；最新實際 QA 以
`.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`
執行，結果為 `Success: no issues found in 614 source files`。614 只代表目前指定 UI／application／data／analysis／backtest／decision／portfolio／runtime 型別範圍，不取代 learning natural maturity、formal source 或 promotion Gate。

## Qt 實際渲染與 MainWindow smoke

已使用實際 PySide6 widget／production view 組裝，在 offscreen Qt 環境套用 `MIDNIGHT_ANALYST`、`Microsoft JhengHei`，綁定 `decision_date=2026-09-14`，切換臺銀與 legacy selector、滾動至每日學習區塊並目視檢查 PNG。這是「離屏實際 Qt 渲染」，不是 controlled DTO screenshot，也不是 native desktop mouse／screenreader 測試。

manifest：

`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a278-54ae-72b3-bae7-ada2025777cb\learning_projection_qt_20260914\manifest.json`

- manifest `status=passed`、`evidence_kind=offscreen_actual_qt_render`、`read_only=true`、無 Apply／Trade controls。
- 臺銀 PNG 顯示 default lane、`pending`、`not_recorded`、`natural_forward_evidence_receipt_missing` 與尚無 verified natural sample。
- legacy PNG 顯示獨立 `legacy_fixed_bp` lane、`blocked_provenance` 與 cross-capture conflict；沒有把 legacy 結果當臺銀 fallback。
- PNG：`research_console_banktaiwan_default.png`、`research_console_legacy_fixed_bp.png`，位於上述目錄。

另執行實際 `MainWindow` offscreen keyboard／geometry smoke：

`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a278-54ae-72b3-bae7-ada2025777cb\mainwindow_smoke_20260914\summary.json`

結果為 `status=passed`、scale 1.0、1366×768、market/runtime Space navigation、600-row PageDown/Home 與 recommendation／portfolio embedded pages 通過。native CUA surface 在本機不可用，因此 `native_windows_interaction`／screenreader 不宣稱已測。

先前共享工作區曾因 `app_module.portfolio_store`／`app_module.journal_service` in-flight 缺檔
而阻擋 import；A／D public modules 恢復後，該 blocker 已 resolved。最新 MainWindow
offscreen smoke 已重新通過，`summary.json` 為目前可引用的成功 artifact。

### Research fallback packet Qt screenshot

以實際 `UnifiedDecisionWorkbenchView`、`apply_app_theme` 與 `Microsoft JhengHei` production theme，在 `QT_QPA_PLATFORM=offscreen` 下只注入隔離、手建的 typed DTO fixture，驗證正常／缺件／identity-cost conflict／pending natural evidence 四種呈現。每種畫面預設收合 technical detail；expanded detail 另檢查 source owner 缺失明示為 unknown，沒有 approve／trade 控制。

manifest：

`C:\Users\archi\.codex\visualizations\2026\09\15\01a0a278-54ae-72b3-bae7-ada2025777cb\research_fallback_qt\summary.json`

結果為 `status=passed`、`evidence_kind=actual_qt_production_theme_offscreen_screenshot`、`read_only_fixture=true`；實際字型為 `Microsoft JhengHei`、9pt。這些 PNG 僅證明 Workbench render 與文字分流，不能證明正式 natural lane、完整 production reader→projection→UI 或 formal evidence credit。

## 根 AGENTS 強制驗證補充

- `pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts=`：D 線最新驗證 `81 passed`。
- `scripts\qa_validate_update_tab.py`：D 線最新驗證 `25 pass、0 fail、4 skip`。
- MainWindow offscreen validator：本次恢復後重跑 `status=passed`；scale 1.0、1366×768、keyboard navigation、600-row table 與 embedded recommendation／portfolio pages 均通過。
- 全域 mypy：本次實際輸出 `Success: no issues found in 614 source files`。
- Research fallback 分層結果為功能／UI `13 passed`、daily service `6 passed`、daily UI `2 passed`；screen fixture 另為 `status=passed`，不併入上述測試數，也不替代正式 natural evidence。
- 歷史缺檔 blocker 已標記 resolved；本線 learning focused run 仍保留 `72 passed, 1 warning`、Research Console `16 passed, 1 warning` 與最新 learning PNG 的自身邊界證據。

## 尚未解除的產品 Gate

本輪沒有真實 natural matured sample、正式 promotion package、Advice adoption、正式 Recommendation／Portfolio 變更或 broker action。learning 的下一個 gate 只需由既有自然 forward 流程累積同 candidate／同成本／同 source custody 的成熟 receipt；Workbench 在此之前維持研究／等待／阻擋狀態。observed broker fill／slippage 與 formal promotion 是延期中的 execution／formal gate，不是每日 shadow learning 或本輪 UI 驗收的必要前置。
