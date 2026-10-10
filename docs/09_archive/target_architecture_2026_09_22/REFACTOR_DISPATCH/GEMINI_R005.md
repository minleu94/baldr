> **歷史封存警語（2026-10-10）：**本文保留當時的派送內容；其中 SHA（如有）、scope、角色、指令與狀態僅代表原快照，不得據此重派、重跑或視為目前任務／授權。現況請以 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 與 [REFACTOR_MODEL_ASSIGNMENTS](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md) 為準；後續 Wave 1 狀態見 [WAVE1_R007_TZNAME_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE1_R007_TZNAME_CHECKPOINT.md)。

# GEMINI_TASK_PACKET — R005

## ROLE

你是受控重構 implementation agent。架構已定案；你負責建立 replay／portfolio replay 的 mode-specific characterization，不負責共用 evaluator 或重新定義 replay policy。

## TASK ID

R005 — replay／portfolio replay characterization（Wave 1）。

## PURPOSE

凍結 `RecommendationDataFrameProvider` 與 `RecommendationReplayService` 的現有 historical semantics，使 R017 可以先 bridge、R020 才能共用 evaluator，而不把 replay 與 interactive 的合法差異誤刪。

## CURRENT SYSTEM CONTEXT

- `app_module/recommendation_market_data_provider.py::RecommendationDataFrameProvider.__call__` 使用自己的 lookback、max stocks、min rows、fast filters、exception skip、score fallback、sort 與 top-N，輸出 legacy `list[dict]`。
- `app_module/historical_evidence_replay.py::RecommendationReplayService.run_snapshot` 封裝 `RecommendationSnapshotDTO`。
- Replay 不是 interactive recommendation 只換日期；R001 已將它登錄為獨立 legacy engine boundary。
- R001 已 PASS，基線在 `docs/06_qa/REFACTOR_BASELINE_R001_20260922.md`。開始時重新記錄實際 HEAD／dirty state，保留其他 Wave 1 changes。

## AUTHORITATIVE ARCHITECTURE

- `REFACTOR_TASKS/R005.md`：完整 task contract。
- `FINAL_DATA_FLOW.md` §4：歷史 replay、stored display、recompute 與 child execution 的區分。
- `FINAL_TARGET_ARCHITECTURE.md` §7：interactive/replay 共用 business evaluator 的目標與明示 policy 差異。
- `FINAL_ARCHITECTURE_INVARIANTS.md`：INV-05、INV-06、INV-13。
- `REFACTOR_VALIDATION_MATRIX.md` 的 `V-REPLAY` 與 R005 row。

## RELEVANT INVARIANTS

- 決策日只能使用當時 available data；future append 不得改舊 snapshot。
- Replay mode 差異必須由 oracle 保留，不能用 interactive expected values 覆蓋。
- Historical display、historical recompute 與 current model lookup 不得混為同一路徑。
- Empty、missing、per-stock exception skip 與 factor manifest 都是可觀察 contract。

## COMPLETED DEPENDENCIES

R001：PASS。Replay provider/service、相關 tests、legacy dict boundary、未知 external callers 已盤點。R017/R020 未開始，不能假設 canonical execution 或 shared evaluator 已存在。

## ALLOWED SCOPE

- 新增 replay characterization tests、最小 DataFrame fixtures、mode difference table。
- 唯讀檢查 replay/provider 與 portfolio backtest integration。
- 所有 artifacts 只寫 `tmp_path`。
- 新增 `REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`。

## OUT OF SCOPE

- 不修改 production replay/provider/evaluator/policy。
- 不改 backtest broker、fill、cost、portfolio accounting。
- 不建立 canonical bridge、DecisionBatch 或新 persistence writer。
- 不強制 interactive/replay 輸出相等。
- 不使用正式資料作唯一 fixture，不 stage／commit／push／reset／clean。

## FILES LIKELY INVOLVED

- 新增 `tests/test_recommendation_replay_characterization.py` 或等價專用檔。
- Read-only context：`app_module/recommendation_market_data_provider.py`、`app_module/historical_evidence_replay.py`、相關 snapshot DTO 與 portfolio replay entrypoint。
- Existing tests：`tests/test_historical_evidence_replay.py`、`tests/test_recommendation_historical_replay.py`、`tests/test_recommendation_portfolio_backtest.py`、`tests/test_backtest_timeline_contract.py`；需要時只加入直接相關的 replay pipeline test。

## CURRENT BEHAVIOR TO PRESERVE

Numeric `YYYYMMDD` parsing、future-row cutoff、available_date、lookback 80、max stocks 200、min rows、volume/price fast filters、score fallback、stable sort/top-N、per-stock exception skip、empty/missing semantics、factor manifest，以及 outer snapshot 的 profile/config/date/portfolio refs。

## IMPLEMENTATION REQUIREMENTS

- 使用小型 deterministic DataFrame，逐一覆蓋正常、empty、missing、insufficient rows、fast-filter reject、per-stock exception、tie/sort/top-N 與 future append。
- 建立 interactive/replay mode difference table，只描述 observed policy；不提出新 policy。
- Golden expected values 必須獨立寫出或手算，不讓新舊測試共同呼叫待遷移 helper。
- 確認追加 decision date 之後的 rows 不改既有 snapshot。
- 不把 exception skip、empty 或 factor manifest 缺件補成零或成功。

## NUMERICAL COMPATIBILITY

Exact preserve score values、fallback、sort、tie-break、top-N 與 candidate order。不得改 Decimal/float conversion、rounding、missing values 或用寬鬆 tolerance 掩蓋結構差異。

## PERSISTENCE COMPATIBILITY

Historical manifest／snapshot 只在 `tmp_path`；不得寫 `RecommendationRepository`、正式 output 或建立新 schema。既有 serialized DTO 若被測試讀取，只做 read-only assertion。

## REPLAY COMPATIBILITY

這是本 task 核心：同 mode 結果必須穩定，future append 不得改舊 snapshot；跨 mode 只記差異，不要求相等。Portfolio integration 只驗 replay/date/factor manifest 受影響路徑，不改 broker/cost。

## ML COMPATIBILITY

不改任何 ML schema、provider 或 model。若 fixture 含 stored annotation，只驗它不被 replay 用現在模型重算；沒有 annotation 時保持 absent/unavailable。

## REQUIRED TESTS

- 新增 R005 replay characterization tests。
- `tests/test_historical_evidence_replay.py`
- `tests/test_recommendation_historical_replay.py`
- `tests/test_recommendation_portfolio_backtest.py` 中 replay/date/factor-manifest relevant tests。
- `tests/test_backtest_timeline_contract.py`
- Changed Python `py_compile`、`git diff --check`。
- 測試命令與 selected cases 必須在 report 列明；禁止跑正式資料或 production backtest。

## ACCEPTANCE CRITERIA

- 每個 replay mode 有自己的 deterministic oracle 與差異表。
- 正常、empty、missing、exception skip、future cutoff、sort/top-N、factor manifest 均被覆蓋。
- 同 mode exact result 穩定；future append 不改舊 snapshot；跨 mode 不被硬性同化。
- Production code 零修改；無正式 repository／data writes。
- R017/R020 可以從報告取得 mapping、known differences 與 tests。

## STOP CONDITIONS

- 只能靠正式資料才能建立 oracle。
- 現有測試無法隔離 broker/cost 與 replay selection，且完成需要修改 production。
- 發現 authority 與實際 code 的重大矛盾，使 mode-specific characterization 無法安全建立。
- 測試需要重算 ML、寫正式 repository、啟動 scheduler 或觸碰另一 active task 的檔案。

遇到上述情況，停止並以證據回報，不要自行修改政策或架構。

## REQUIRED IMPLEMENTATION REPORT

建立 `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`，包含 HEAD/dirty baseline、changed files、fixture grain、mode difference table、golden來源、tests/results、known gaps、rollback 與下游 R017/R020 handoff，末行只能是：

`IMPLEMENTATION_STATUS: READY_FOR_REVIEW`

或 `IMPLEMENTATION_STATUS: CHANGES_REQUIRED`

或 `IMPLEMENTATION_STATUS: ARCHITECTURE_BLOCKER`

Do not redesign the architecture.

Do not perform unrelated cleanup.

Do not silently fix unrelated bugs.

Do not begin another R-task.

If repository evidence contradicts this task specification in a way that prevents safe implementation, stop and report ARCHITECTURE_BLOCKER with evidence.
