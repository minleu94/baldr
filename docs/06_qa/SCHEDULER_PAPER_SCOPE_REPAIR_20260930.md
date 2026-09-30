# Scheduler / Paper 空持倉與研究種子範圍修復 QA

日期：2026-09-30

範圍：Paper position-health / decision-evidence source、Portfolio Alert empty-population 契約與相應測試。僅修改 repository source/tests 和本 QA 記錄；沒有執行 Task、正式排程、資料重建、訓練、pointer 更新或 D: 寫入。正式 Paper 資料的讀取僅限明列的 adapter preview。

## 結論

1418 是 Paper state 裡的 machine-initialized research seed，不是使用者真實持倉。其 identity / thesis 缺件是該 Paper research input 的品質阻塞，不能轉成「請使用者補 1418 真實成交或 thesis」；保留來源並繼續顯示 degraded。Paper evidence metadata 現明確標記 `source_scope=paper_research`、`research_only=true`、`formal_credit=false`、`broker_order_allowed=false`，見 `app_module/paper_decision_desk_evidence_source.py:192-207`。

排程可先擷取當時可取得的 evidence，不需要先有交易或 thesis。當日只讀正式 receipt `D:\Min\Python\Project\FA_Data\output\scheduled\decision_evidence_capture\latest_status.json` 顯示 `status=passed`、`checked_at=2026-09-30T05:25:02-07:00`（台北 20:25:02）、`capture_mode=eod_research`、`research_only=true`、`natural_authority=false`。這是已持久化的研究 capture，不等於自然／正式 forward credit。05:15 的 `--dry-run` 只產生檢查結果，不會寫 EvidenceDB；兩者不可混稱為同一個持久化 collector。

另以目前 repository 的真實隔離來源直接呼叫修改後 adapter（不執行 runner）：Paper state 是 `output/paper_execution_eod_replay/paper_portfolio/paper_portfolio.sqlite`，status 是 `output/paper_execution_eod_replay/scheduled/paper_portfolio_isolated/latest_status.json`，health baseline 是 `D:\Min\Python\Project\FA_Data\output\position_health\latest.json`。截至 `2026-09-30` 的 `paper-main-20260930` 得到 `source_scope=paper_research`、`population_status=has_positions`、`quality/status=degraded`、6 個 Paper research position，alert codes 包含 1418；warnings 保留 thesis、identity 與非 exit-instruction 診斷，`blockers=[]`、`formal_credit=false`。這證明現行低階 research capture 不必等待 1418 成交或 thesis，但 health transition、verified identity 與 Formal qualification 仍受其品質限制；不得要求使用者補上其不存在的 1418 真實成交。Adapter preview 在 `.tmp_seed_dependency_baseline_20260930/actual_paper_source_preview.json`，state DB、status receipt 與 health baseline 的 bytes/SHA-256/size/mtime 前後相同；三個 SHA-256 分別為 `08f6127f658e3a8f8cb36bcc72172da48a08851ab386ed101d8c4d13f8c38d18`、`e407cb776de6025f271f72f8b7bba348302826f0bcb4503d927cffc9d62d1eef`、`46d65c6c7ae0b09cb6269d50778b24b88045376693db27da34bc868d04c0b8ef`。

有效且已驗證的空 snapshot 現可表達為 `no_positions`，而缺 snapshot、缺／失敗 status、壞 schema/date、負 quantity 或 provider exception 仍 fail closed。空集合不能由 `alert_count=0` 推論：舊 payload 的 `population_status` 仍為 `unknown` 且序列化時省略新欄位，保留舊 snapshot hash。

## 修復契約與依據

| 契約 | Source 與測試依據 |
| --- | --- |
| `PortfolioAlertSummary` 狀態為 `unknown / has_positions / no_positions`；預設 unknown，unknown payload 省略新增欄位，不從零 alert 推斷無持倉。 | `app_module/decision_desk_dtos.py:427-451`；parser `app_module/decision_desk_snapshot_storage_dtos.py:420-425`；legacy shape/hash round-trip `tests/test_decision_desk_snapshot_repository.py:128-166`。 |
| 只有成功的 `PortfolioService.list_positions() == []` 才標成 observed `no_positions`；例外仍 degraded/unknown；非空來源標 `has_positions`。 | `app_module/portfolio_alert_service.py:82-139`；正／負向測試 `tests/test_portfolio_alert_service.py:116-146`。 |
| 空 Paper health baseline 把「無 active Paper positions」與「不是 exit instruction」留在 diagnostics，不產生 thesis warning；有部位時 thesis warning 仍保留。空 population 跳過 position identity / previous-health carry，但來源、status、日期、schema、quantity 驗證不放寬。 | `app_module/position_health_baseline_service.py:86-108`；`app_module/position_health_daily_refresh_service.py:250-282`；有效空與六種壞來源負控 `tests/test_position_health_daily_refresh_service.py:501-584`。 |
| 有效空 Paper snapshot（含只有 zero-quantity row 的 snapshot）連同有效 status / baseline 回傳 observed `no_positions`；Paper 1418 非空 machine seed 仍 degraded，保留 `human_thesis_required_before_health_transition_validation` 和 `paper_position_identity_unproven:1418`。 | Paper scope 與分流 `app_module/paper_decision_desk_evidence_source.py:192-207, 438-466`；測試 `tests/test_paper_decision_desk_evidence_source.py:229-315`。 |

`risk_prompt` 不是由「有無持倉」單獨決定：`DecisionDeskRiskPromptService` 會檢查 market regime、breadth、sector rotation、relative strength/liquidity、watchlist 與 portfolio-alert 六個來源的品質（`app_module/decision_desk_risk_prompt_service.py:25-80`）；Portfolio 的 prompts 只由實際 alert codes 產生（同檔 `:152-178`）。Snapshot coverage 對 `portfolio_alert` 與 `risk_prompt` 分別檢查 section quality（`app_module/evidence_source_coverage_service.py:150-168, 200-214`）。因此已驗證空持倉可解除「portfolio alert 因空清單而缺失」的誤判，但不能自動令缺少 market/watchlist 等上游資料的 `risk_prompt` ready，也不能單憑空持倉宣稱兩者 not-ready 已消失。

## 驗證

- Paper empty/invalid-source、portfolio alerts、DTO/hash 相容、evidence runner 與 evidence coverage CLI 的七檔 focused route 使用 workspace 內 ignored pytest `--basetemp`：**67 passed**（`7.62s`；log `.tmp_seed_dependency_baseline_20260930/current_scoped_route.log`）。可重現命令：

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests\test_position_health_baseline_service.py tests\test_position_health_daily_refresh_service.py tests\test_paper_decision_desk_evidence_source.py tests\test_portfolio_alert_service.py tests\test_decision_desk_snapshot_repository.py tests\test_evidence_pipeline_runner.py tests\test_evidence_source_coverage_cli.py -q -o addopts= --basetemp=.tmp_seed_dependency_baseline_20260930\current_scoped_route_tmp
  ```

  這包含有效空 Paper（空 rows / zero-quantity rows）、empty snapshot 負控、non-empty 1418 degraded fixture、portfolio provider exception 與 legacy hash round-trip。
- 為判定相鄰 runner 測試的 8 個 tempfile 失敗是否本輪回歸，從 HEAD `17fb70650edb4f907c4d6f4d0428aeea6763c214` 的 tracked export 做只讀 baseline。代表測試 `test_runner_defaults_to_dry_run_and_does_not_write_events_or_outcomes`、`test_runner_summary_and_report_include_warning_breakdown` 在 baseline 和 current 的 AppData 預設 pytest temp 路徑都重現 `ExecutionArtifactIntegrityError`，拒絕鎖定 `C:\Users\archi\AppData\...` no-follow ancestor（Windows `CreateFileW` access denied）；無 recommendation hash mismatch。改用 repository workspace `--basetemp` 後，baseline 2/2、current 2/2 均通過；current 完整 focused route 67/67 通過。沒有放寬 no-follow 防護。
- 六個變更 Python source 的 scoped mypy：`Success: no issues found in 6 source files`。
- 變更 source 與五個變更測試 `py_compile` 通過。
- `scripts/quant_guard_linter.py` 通過 financial-float 與 look-ahead-bias 檢查；`git diff --check` 通過（Git 僅提示工作樹 LF/CRLF 正規化警告）。
- 額外執行 evidence runner/readiness 相鄰 route（另含 `tests/test_pre_v2_readiness_service.py`）為 **95 passed / 1 failed**。命令為上述七檔 route 將最後一個 file 換成 `tests\test_pre_v2_readiness_service.py`，並用 `--basetemp=.tmp_seed_dependency_baseline_20260930\current_finaltmp`；完整 stdout/traceback 在 `.tmp_seed_dependency_baseline_20260930/current_final_route.log`。唯一失敗是 `test_program_readiness_projects_performance_owner_packet` 對 `performance_owner_packet_invalid` 的預期。從 HEAD `17fb70650edb4f907c4d6f4d0428aeea6763c214` 的既有 baseline export，以相同 pytest options/workspace basetemp 單獨執行該測試，得到相同 assertion failure（baseline log `.tmp_seed_dependency_baseline_20260930/baseline_packet_test.log`）。歸因為既存測試／implementation mismatch，不是本次 Paper diff；不修改該 suite 或其 guard。

## 判讀界線

本修正不會把任一 missing/invalid source 當合法空持倉、不會減少 Paper source block，也不會令 1418 seed 進入 verified / Formal lane。現行 `eod_research` capture 已能在 seed degraded 時收集低階 research events；缺少的是 position-health transition 的 thesis/current-condition 驗證與可信 identity／Formal qualification。自然 capture 的時間可在交易／thesis 之前，capture 的研究範圍、品質與 formal authority 必須分別保留；不能以虛構成交填補使用者沒有的 1418 持倉。
