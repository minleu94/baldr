# R013 — Qt Recommendation consumer 遷移

> 本報告保留 R013 Qt execution/save slice 的原始 `ACCEPTED_SCOPE` 與 dated QA evidence。R031 將現行裁定細化為 `ACCEPTED_WITH_PORTFOLIO_NAVIGATION_SCOPE`，並明示 persisted display-summary 不在該接受範圍內；請以 [R031 R013 row](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 核對目前 scope。

TASK_STATUS: ACCEPTED_SCOPE
SOL_DECISION: R013_ACCEPTED_SCOPE (synthetic/engineering)
INDEPENDENT_REVIEW: Accept with nonblocking notes

## 結論

Qt 推薦流程已切換為同次 sealed `RecommendationExecution`：worker 回傳 typed execution，畫面在完整且同 generation 的完成 callback 才套用；執行中的新工作保留 last-good 結果與選取列。保存以目前同一個 execution／`result_id` 呼叫 R014 composition 的唯一 canonical writer，再以精確 ID 查詢並核對 execution、hash、artifact、保存時間、label 與 notes。畫面只有在 receipt 與 verified readback 完全相符後，才公布已保存身份。

Qt view 不再保存共享 `current_recommendations` 作 business source、不手建 `RecommendationResultDTO`、不讀 `service.last_*` 補結果、不呼叫舊 repository/writer，也不於 save/backtest/Portfolio 來源路徑重查 Regime 或 context。呈現格式留在 presenter；無證據欄位保持 unknown／unavailable。

## Owner 範圍與變更

| 路徑 | 本切片變更 |
|---|---|
| `ui_qt/views/recommendation/execution_coordinator.py` | 深複製並封存 request config；標記 `manual_qt_snapshot=true`；呼叫 execution use case 並原樣回傳 typed execution；把 progress、合作式 cancel 和 terminal status 保持為明確訊號。執行規則前從 runtime config 移除來源標記。 |
| `ui_qt/views/recommendation_view.py` | 以 `current_execution`／verified read model 為唯一推薦狀態；last-good、generation/stale callback、cancel/error 防護；same-object canonical save/readback、partial-index retry、同一結果之 watchlist side effect，以及 verified source context、匯出、回測／Portfolio handoff。 |
| `ui_qt/views/recommendation/presenter.py` | typed item 到既有欄位的顯示轉接；None threshold 不預設成 fixed；百分位使用 Decimal 格式；ML 值只取 verified projection；缺少實際 evidence 時 Why／Why Not／Explain 顯示未知，不輸出風險偏低或條件全符合的肯定結論。 |
| `app_module/portfolio_source_adapter.py` | 保留既有 legacy adapter 不變；新增 canonical execution/readback/receipt/selected-item 專用轉接。摘要綁定 result、candidate、保存 artifact/payload hash；data snapshot ID/hash 只取明確 identity，不拿 artifact path 冒充 snapshot。verified ML 欄位依來源 schema 映射，並保留 training／inference／compatibility／status provenance。 |
| `tests/` | 新增／更新 typed execution、last-good、取消與 generation、A→B worker/save A、保存 idempotency／partial-index retry、verified adapter／Portfolio JSONL hash roundtrip 等回歸測試。 |
| `docs/07_guides/APPLICATION_MANUAL.md` | 同步 6.1、6.5 的入口流程、保存與重試、watchlist soft-failure、Portfolio 來源、ACK 限制、manual snapshot provenance 和排錯。 |

未修改 R014 composition/wrapper、R012 writer/store/query、R016 readers、R017 replay、portfolio tab、核心 engine 或策略公式。唯一跨 owner 路徑是依 SOL 裁決窄幅擴充 `portfolio_source_adapter.py`，只增加新 typed adapter，legacy 函式原樣保留。

## 保存、重試與既有 side effect

1. 保存只使用目前 sealed execution 和其 `result_id`，不組裝第二份 business payload。
2. 一般首次保存：canonical writer → exact query/readback → receipt/read model 身分、hash、artifact、時間與 label／notes 核對 → 套用已保存狀態。
3. `INDEX_PENDING` partial error 會記住第一次 label／notes；重按時以同一 execution、ID 和 metadata 再呼叫唯一 writer 修復索引。只有 readback 通過後才建立自動選股清單。
4. 已 verified 保存重按只顯示既有保存資料；readback 失敗後重試只查同一 ID，不重寫 artifact。未 verified 時不建立選股清單。watchlist 建立沿用同一 execution 的股票代號與 Profile，失敗只回報 soft failure，不回滾 canonical 保存。
5. Qt 正常手動保存沒有 personalization scope/request identity，因此不呼叫 Journal ACK；具名測試驗證無 scope 不會 ACK。若未來 execution 帶 scope，成功訊息明確表示 ACK 目前不可由 Qt 保存流程提供、需 R015 owner 處理，不將 save 當成 delivery ACK。

右鍵記錄持倉只接受 completed execution、含同一 execution 的 canonical verified readback、indexed receipt 及完全相同且唯一的選取 item。缺少 calibration/probability 保持 `None`／`unavailable`。Portfolio 摘要在計 hash 前遞迴正規化 Decimal、巢狀 mapping、tuple/date/enum 等值；JSONL 寫入後能由載入摘要重算同一來源 hash，且摘要不含裸 float。

## 手動來源 provenance 與跨 owner 查核

盤點 Qt Manual 入口未找到可由 sealed request/readback 驗證的既存明確 manual/scheduled provenance。Qt caller snapshot 現加穩定欄位 `manual_qt_snapshot=true`，存於 `RecommendationExecution.request.config_snapshot`；coordinator 測試確認 runtime rule config 會移除它，因此不改變策略選擇或分數。R016 scheduled evidence status 可從 verified execution 的這個欄位辨識 manual Qt 來源，不得以「沒有 scheduled 標記」反推 manual。

只讀檢視 Portfolio downstream：既有 `_validated_recommendation_result_id` 仍直接找 `output_root/recommendation/runs/<result_id>.json` legacy DTO 檔，canonical execution artifact 不會自然滿足該讀取契約。這屬 R016/read consumer follow-up，本切片沒有修改 Portfolio tab 或 reader。`test_watchlist_drilldown_reads_saved_metadata_and_keeps_source_id` 單測仍失敗，問題限於該跨切片 fixture：其 config 缺 `resolve_output_path`，WatchlistView 因此無法初始化 universe service；其 `runs` fixture 僅建立 `(result_id, data_path, created_at)` 三欄，但 production legacy reader 依正式 `RecommendationRepository` schema 查詢 `result_name` 與 `notes`，所以 fixture readback 會報 `ExecutionIndexReadError`。這些 fixture 缺件使測試預期的 `result-1` 無法成立，不代表 production reader schema 有缺陷。已通知 R016 owner 作測試整合；R013 不建立第二讀取器，也不把 canonical artifact 偽裝成 legacy JSON。

## Look-ahead 自查

本切片只有 coordinator、呈現與保存來源轉接，未新增訊號、特徵、排序、門檻、排名母體、risk policy 或任何策略計算。`manual_qt_snapshot` 只是一個 request-source 標記，並於 rule execution 前移除。保存不重查 Regime/context/ML；Portfolio adapter 只投影同次封存 outcome 和 verified readback，不作決策時點以外 lookup 或重新計分。

## 驗證

所有命令在 PowerShell 執行；pytest/py_compile/mypy 命令執行前設定 `PROFILE=test` 及 `%TEMP%\wave6-r013-final\data`／`output`。Update Tab QA 腳本使用自身隔離 TEMP fixture（log 顯示 `task-loop-01-qa-*`）；該腳本另將 QA 報告寫到 repo `output/qa/update_tab/VALIDATION_REPORT.md`，沒有清理該輸出。

| Gate | 命令／結果 |
|---|---|
| 強制 Qt workbench | `python -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=` — **84 passed**。 |
| 強制 Update Tab QA | `python scripts/qa_validate_update_tab.py` — **25 passed、4 skipped、0 failed**；實際下載與資料合併測試按腳本安全設定略過。 |
| 強制 broad mypy | `python -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` — **678 source files，Success: no issues found**。 |
| R013 focused Qt/adapter | `test_recommendation_execution_coordinator.py`、`test_recommendation_view_presenter.py`、`test_recommendation_execution_state_characterization.py`、`test_portfolio_source_adapter.py`、`test_ui_qt_recommendation_execution.py`、`test_ui_qt_report_export.py`，加 Portfolio 來源右鍵與推薦 research-context 測試 — **48 passed**。 |
| changed Python compile | coordinator、presenter、view、adapter 和相關 tests 執行 `python -m py_compile <files>` — **成功**。 |

更新前的 untracked `test_recommendation_execution_state_characterization.py` 有 **11 failed、2 passed**；失敗是其預期舊 list／`run_recommendation` fake／清空 last-good／無 generation callback 契約。依 R013 cutover 更新為 typed execution、named cancellation、保留 last-good、generation、progress 與 worker lifecycle 後為 **7 passed**。這不是將失敗標成通過，測試已改為目前架構下可執行的行為斷言。

QA 腳本摘要為 4 個 skip，不計為 pass；未跑正式資料、production scheduler、完整市場 ML rebuild、promotion 或部署。指定 broad mypy final run 沒有既有錯誤。

## 回滾與失敗條件

若 R013 變更造成取消／stale callback 套用非目前 execution、A/B result identity 混淆、label/notes/readback 錯配，或強制 UI gates 新增 failure，回滾只限上述 Qt coordinator/view/presenter 及新 adapter seam 到此切片之前版本；保留 R011/R012/R014 execution/save/query API，不回填 `last_*`，不加第二 writer。R016 legacy read consumer 限制由 R016 owner 以 canonical query seam 處理，不以回退 Qt 保存或複製 legacy JSON 解決。

沒有 stage、commit 或 push。

## 後續 Addendum — 2026-09-23

- 獨立 R013 reviewer 結論為 `Accept with nonblocking notes`；SOL 裁決 `R013_ACCEPTED_SCOPE`，範圍限 synthetic／engineering 驗收。
- 先前記錄的 Watchlist drilldown fixture failure 已由 R016 以正式 legacy `runs` schema 修正；`test_watchlist_drilldown_reads_saved_metadata_and_keeps_source_id` 現為 **1/1 passed**。上文保留原始執行當時的失敗紀錄作為歷史 QA evidence。
- Portfolio tab 直接讀取 legacy recommendation JSON 的既有契約，列為後續 Portfolio／Exit slice；不構成 R013 或 R016 gate closure 條件。
