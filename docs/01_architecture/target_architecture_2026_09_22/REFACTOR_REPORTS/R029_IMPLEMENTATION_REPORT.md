# R029 retirement gate acceptance report

**最終裁定：`ACCEPTED_WITH_RETAINED_COMPATIBILITY`（2026-09-25）。** 本輪完成有限 caller／alias inventory、retirement ledger 同步與有證據範圍的 gate 裁定。R029 不代表所有 compatibility facade 均已刪除；沒有執行破壞性 cleanup，沒有刪除 DTO、歷史 decoder、未知 serialized alias 或正式資料。

權威狀態在 [FINAL_MIGRATION_SEQUENCE.md](../FINAL_MIGRATION_SEQUENCE.md)。逐項 caller 清冊與可重跑搜尋見 [R029 preflight inventory](../../../06_qa/R029_RETIREMENT_PREFLIGHT_INVENTORY_20260925.md)。較早 [R029 gate draft](../../../06_qa/R029_RETIREMENT_GATE_DRAFT_20260925.md) 是裁定前快照，不再作 current status。

## Retirement 裁定

| 項目 | 狀態 | 裁定與保留條件 |
|---|---|---|
| `TMP-REC-01` | **CLOSED** | R019 bounded rule bridge 已關閉；app orchestration body、capture 與 telemetry 不在該 closeout 的刪除範圍。 |
| `TMP-REC-02` | **BLOCKED_WITH_OWNER** | `run_recommendation()` repo production search 僅命中定義；UI、personalization CLI、scheduled CLI 已走 typed execution。仍保留 `last_*` ports/service state 與 QA reader。`legacy_negative_evidence_capture` 仍由 `saved_recommendation_queries.py` 及 scheduled CLI 消費；需切換至 typed execution/read model 並驗 parity，再依外部 support window 收口。Owner：app recommendation compatibility。 |
| `TMP-REC-03` | **CLOSED（R015 retired）／PERMANENT_COMPATIBILITY** | 舊 save coordinator 已移除；保留 legacy JSON exact-retry/read path 與既有 DTO/run-context decoder，不重寫舊 bytes。 |
| `TMP-REC-04` | **CLOSED（R020 bounded gate）** | R005 policy vectors、V-REPLAY typed handoff 與有限 recovery windows 已接受；不擴大為 `TMP-NUM-01`、所有 caller、所有 runtime 或無界 parity。詳見 [R020 report](R020_IMPLEMENTATION_REPORT.md) 及 [hard-exit recovery QA](../../../06_qa/R020_PROCESS_CRASH_RECOVERY_HARD_EXIT_QA_20260925.md)。 |
| `TMP-REC-05` | **BLOCKED_WITH_OWNER** | `RecommendationDTO` 與 `RecommendationResultDTO` 的 class owner 是 `app_module.dtos`；preflight 列出 17 個 import paths/symbol 用途。保留 class、v1 projection 和 history reader；R006 未發現這兩個 DTO 的 serialized qualified-name 證據，但也沒有外部部署／support window 的完整證明。Owner：recommendation contract/app compatibility。 |
| `TMP-REC-06` selector 條件 | **CLOSED**；ABI test **PERMANENT_COMPATIBILITY** | `run_recommendation()` 與 execution ABI 共用 `_run_recommendation_body_result()`；未發現第二個計算 engine 或 selector。保留 `test_legacy_list_abi_and_execution_abi_match_with_isolated_side_effects` 作永久相容回歸。此判定不把該測試描述成雙 engine oracle。 |
| `TMP-STR-01` | **BLOCKED_WITH_OWNER** | repo direct/config/dynamic import 搜尋未找到舊 strategy alias 的 production caller；測試仍保留 alias identity regression。外部 support window 無 repo 證據。Owner：decision strategy／app compatibility。 |
| `TMP-NUM-01` | **BLOCKED_WITH_OWNER** | R020 typed handoff 與 NumPy 1/2 native-oracle slices 有限接受；precision、rounding、tie-break、Decimal 字串與其餘 caller parity 仍是獨立 gate。Owner：decision recommendation／app codec。此項不反向阻塞 R020。 |
| `TMP-ML-01` | **CLOSED（supported caller/profile 遷移條件）** | R026 supported production path 使用 prepared input/source evidence 與 typed post-calibration handoff；supported-runtime、NoModel/NP1 adapters 和 C2 union 已接受。永久保留 public `ml_adapter` 與 unknown/custom model compatibility；不宣稱所有 profiles 或 artifacts 均相容。 |
| `TMP-ML-02` | **BLOCKED_WITH_OWNER** | R027 為 `INCONCLUSIVE`、`AB-ML-01=OPEN`，記錄 848 個 exact timing/snapshot differences；R028 依其 R027 PASS prerequisite 保持 `BLOCKED`。Owner：data numeric store／ML identity／update job。R028 未完成可由此列管，不是 R029 的額外 blocker。 |
| `TMP-RGM-01` | **BLOCKED_WITH_OWNER** | fallback、舊 detector adapter 與 wrappers 仍存在；正式 composer、UI 與兩個 CLI 明確注入 service。walk-forward、decision-desk、evidence-pipeline 是獨立 workflow lifecycle，沒有新增共享 singleton 條件。Owner：regime／application composition。 |
| R006 serialized class-path inventory | **BLOCKED_WITH_OWNER（證據不足）** | 未知 formal model binaries / external serialized paths 未載入或推定；保留歷史 readers、必要 aliases 與 rejection policy。Owner：R006 artifact/ML custodian。 |

## Caller inventory 摘要

- REC-02 可重跑 source search：`rg -n 'run_recommendation\s*\(' app_module ui_qt scripts -g '*.py' -g '!scripts/experiments/**'`。它只命中 `app_module/recommendation_service.py` 的定義。UI 使用 typed execution coordinator；personalization 與 scheduled CLI 使用 `execute_recommendation`。剩餘 latest-state surface 位於 `application_ports.py`、`recommendation_service.py`、`recommendation/execute.py` 及 recommendation-tab QA script。
- `legacy_negative_evidence_capture` 由 `recommendation/execute.py` 產生，仍有兩個 production consumers：`app_module/saved_recommendation_queries.py` 與 scheduled snapshot CLI；這兩個讀取端是 REC-02 明確剩餘工程條件。`legacy_invocation_context` 沒有 production consumer；ML projection receipt 由 R026 typed post-calibration handoff 列管。
- STR-01 direct/config search 只命中 `tests/test_decision_strategy_owner.py` 的 alias identity regression；dynamic import scan、lazy-export map 及設定搜尋未發現舊 qualified module path。repo 搜尋不能證明外部 caller/support window 已結束。
- RGM-01 wrapper source search 未找到 production caller；`regime_detector=` 僅在 recommendation-tab QA fake seam 使用。walk-forward、decision-desk snapshot、evidence-pipeline 各自建 workflow service 是既有合法生命週期，不另立跨 workflow singleton gate。
- DTO 17 路徑、各符號用途與完整重跑命令列於 preflight inventory；不依名稱推論永久 pickle alias，也不搬移或刪除 DTO class。

## Gate evidence 與限制

- C2 current union：141 unique tests／88 source files，1,860 passed／5 skipped／34 warnings，exit 0；root 裁定 `ACCEPTED_WITH_NAMED_QA_BASELINE`。manifest input 229 paths pre/post hashes 一致。Update validator C2 兩次保留 `WinError 32` TEMP SQLite teardown exit 1；後續 C4 validator 25P/0F/4S 的成功不重寫 C2 歷史。詳見 [C2 current/mandatory receipt](../../../06_qa/C2_MANDATORY_UI_STATIC_GATES_20260925.md) 與 [C4 current static receipt](../../../06_qa/C4_FINAL_MANDATORY_STATIC_GATES_20260925.md)。
- R020 bounded V-REPLAY/recovery closeout、R026 supported handoff、R030 extensibility fixtures 各自維持原 scope；不把它們併稱全平台或全模型相容。
- C1 final engineering gate 由獨立 reviewer 接受並由 SOL 裁定 `C1 ENGINEERING GATE PASS`；範圍僅限 synthetic/scoped engineering validation，不授權正式資料、全市場 ML rebuild、scheduler 實跑或 model promotion。詳見 [C1 checkpoint](C1_CHECKPOINT.md) 與 [C1 full-gate report](C1_FULL_GATE_VALIDATION_REPORT.md)。
- 31-entry task evidence links 與目前 C3/C4 狀態見 [R031 index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 及 [R031 closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。C3 composite evidence 與 C4 full union 均由 root 以 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE` 接受；R031 engineering scope 完成，保留的 TMP／artifact／boundary baselines 仍按 owner 列管。

## C2 裁定後的明確保留項目

本報告和 ledger 僅關閉已接受的 bounded 條件。REC-02 typed consumer cutover、REC-05 compatibility/support inventory、NUM-01 numeric parity、STR-01/RGM-01 external support window、ML-02 R027/R028，以及 R006 unknown artifacts 均具名保留。保留項目不表示其所有可能範圍均已測試；同樣也不把未知範圍改寫成新的無界 gate。未執行 commit、push、formal data operation 或 model promotion。
