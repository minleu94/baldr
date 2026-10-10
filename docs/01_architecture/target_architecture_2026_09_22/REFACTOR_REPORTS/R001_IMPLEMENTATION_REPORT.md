> **歷史狀態導讀（2026-10-10）**：本文末尾 `READY_FOR_REVIEW` 只代表 2026-09-22 實作報告當時狀態；R031 dated current overlay 已將 R001 列為 `CLOSED`。現行 task disposition 看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)與[final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)；Wave 1 gate 的後續入口請由 R031 index 核對。原 inventory evidence 保留，R001 closeout 不等於後續 provider work 全部完成。

# R001 實作報告

Task：R001 — 凍結基線、caller 與 artifact 清冊
Implementer：LUNA_MAX（Luna Max）
Reviewer：SOL
Wave：0
Dependencies：無
日期：2026-09-22

## 1. 起始與結束狀態

起始 HEAD：391b057c92037ec7a19cab2bf951d6029d29b020
結束 HEAD：391b057c92037ec7a19cab2bf951d6029d29b020
起始／結束 branch：dev
起始時 origin/dev 狀態：ahead 161。

起始 dirty status 包含三個已追蹤修改（docs/00_core/DOCUMENTATION_INDEX.md、docs/01_architecture/README.md、docs/01_architecture/target_system_architecture.md）、根目錄既有空檔案 =，及未追蹤的 target_architecture_2026_09_22/ 架構文件樹。對起始 58 個 dirty paths 做 SHA-256 snapshot，完成時 58/58 一致。詳細 path/hash 清單位於 [R001 基線清冊](../../../06_qa/REFACTOR_BASELINE_R001_20260922.md)。未修改、清理、stage 或納入其他任務的 dirty changes。

## 2. Authority 與 dependencies

遵守 R001.md、FINAL_ARCHITECTURE_INVARIANTS（INV-01/02/15/17/18）、FINAL_MIGRATION_SEQUENCE Block 1/caller 起點/temporary retirement ledger、REFACTOR_IMPLEMENTATION_DAG R001、REFACTOR_VALIDATION_MATRIX V-SOURCE/R001、REFACTOR_RISK_REGISTER RK-08/RK-19/RK-20/RK-25、MODEL_ASSIGNMENTS R001、REFACTOR_REPORTS/README、repo AGENTS.md、git_exclusions.md、execution_agent 規範。R001 無 dependencies；下游 R002–R031 未開始。

## 3. Changed files 與 scope

新增兩份 bounded QA 文件：

- docs/06_qa/REFACTOR_BASELINE_R001_20260922.md：起始 git/hash snapshot、可重跑 rg 查詢、推薦 caller、direct/dynamic/string scheduler caller、scripts/tests、DTO/repository JSON/SQLite contract、replay、strategy、regime、ML calibration/Direct identity、artifact census、TMP ledger 及 unknowns。
- docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R001_IMPLEMENTATION_REPORT.md：本實作報告。

沒有新增 script/test；沒有修改 production Python、UI、test、資料、SQLite、artifact、模型、scheduler 或 runtime state。未做 characterization、contract、codec、adapter、migration、cleanup 或任何其他 R-task。沒有執行 branch/stage/commit/push/reset/clean 操作。

## 4. Compatibility 與 inventory 摘要

Rerunnable窄查詢登錄 41 個命中檔案：14 個非 tests 檔、27 個 tests 檔。清冊逐類記錄 RecommendationService.run_recommendation 與八個 last_*、UI worker bound callable、getattr consumer、personalization adapter 的 create-only/readback/ACK、scheduler CLI/string task chain、DTO qualified paths、repository readers/writers、replay dict、StrategySpec/Registry、regime_history.json、ML calibration與Direct identity。各項均記 owner 及後續 task/永久相容理由。

artifact census 記錄 DATA_ROOT/output 11,559 manifests、83,105 joblib/pkl/pickle 名稱；release_v4、RecommendationRepository outputs、ML model manifest/schema、15 條 Direct dependency identity allowlist、feature/label registries與 reader/writer authority。未載入任何未知 binary；class path 證據不足的項目保留 unknown。Recommendation JSON keys、SQLite 欄位/index、replace/create-only writer authority與 replay dict boundary 均記錄為現行 compatibility evidence。這些是靜態 source/metadata 證據，沒有執行 runtime 行為或數值測試；因本任務沒有程式變更，既有業務、數值、persistence、replay semantics 未被改動。

九個既定 TMP（TMP-REC-01..06、TMP-NUM-01、TMP-ML-01..02）均逐項登錄現況、owner 與後續 task。TMP-STR-01 僅為 architecture conditional；source/runtime 搜尋無 marker 或 alias，登記為尚未建立條件項，不當成 runtime 現況。

## 5. Validation

已執行：

- HEAD/branch/status：HEAD 與 branch 未變；dirty paths 僅增加本任務兩份新文件，原有狀態保持。
- 起始 dirty SHA-256 compare：58 paths，58 unchanged，0 changed。
- rg caller inventory：41 paths（14 非 tests、27 tests）；命令列於基線清冊，可從 repo 根目錄重跑。
- git diff --check：exit 0。Git 對三個既有修改文件輸出 LF→CRLF normalization warnings；沒有 whitespace error，原檔未改。
- 新增文件檢查：docs/06_qa/REFACTOR_BASELINE_R001_20260922.md 已檢查無 trailing whitespace 且有 final LF；在報告新增後對兩份文件再次執行相同檢查。
- Python compilation/pytest：未執行，因本 task 僅文件、沒有 changed Python，且 R001 要求不跑 production workflow。

## 6. Acceptance criteria verdict

| Criterion | Verdict | Evidence |
|---|---|---|
| 起始 HEAD/branch/dirty baseline 凍結，保留他人 dirty changes | PASS | 清冊 58-path SHA-256 manifest；完成時 58/58 一致 |
| Direct、dynamic、string scheduler、CLI、scripts/tests caller 分類 | PASS | 41-path rg inventory 與依 owner/task 分類表 |
| DTO qualified names、JSON/SQLite schema、reader/writer authority、replay/strategy/regime support | PASS | 基線清冊 contract tables |
| ML manifests/schemas、15 Direct identities、artifact reader/writer support 與 unknown class paths | PASS | 靜態 manifest/source census；未知 binary 未載入 |
| 九個指定 TMP 與條件 TMP-STR-01 狀態 | PASS | 十項 TMP ledger；STR-01 明確標註未建立 |
| 每個登錄項有 path/symbol、mode/authority、owner、task 或相容理由 | PASS | 基線清冊 caller/artifact tables 與分組測試清單 |
| rerunnable inventory 與窄文件驗證 | PASS | rg 查詢、git diff --check、文件 whitespace/final LF 檢查 |
| 無 production/runtime/資料修改、無其它 R-task | PASS | 僅兩份新增 Markdown；branch/head 不變 |

## 7. Temporary components

R001 沒有建立或移除任何 TMP component。TMP-REC-06 由 R011 建立、R029 移除；TMP-NUM-01 的 R002/R009 提供 characterization/codec evidence，R011 建立 named boundary，R019/R020 分別退休 rule/replay 子路徑，R029 依 independent numeric gate 最終 close/retain。其他 TMP 的目前狀態與未來映射見基線清冊。TMP-STR-01 尚未建立，只有 task architecture 條件記錄。

## 8. Remaining risks 與 rollback

External deployment DATA_ROOT、外部/dynamic Python caller support、joblib/pickle 內的實際 module/class paths、沒有 sidecar 的舊模型 ABI 仍未知；manifest 內聲明的 feature_registry_hash 未與程式碼重算。這些不是本任務可用唯讀 inventory 排除的範圍，已映射 RK-08/RK-19/RK-20/RK-25；artifact/class-path unknown 對應 R006/R027，external/dynamic caller support 由 R029 處理（R001 已完成 inventory），不把 unknown external callers 交由 R013；不構成 R001 blocker。

Rollback 僅移除上述兩份新增 Markdown。不得碰觸 58 個起始 dirty paths。READY_FOR_REVIEW 是交由 SOL 審查，不代表 task PASS 或 wave complete。

## 9. SOL review repair note

依 SOL review，這次只修正兩份 R001 文件中的 task routing，未改 architecture、source、inventory counts 或 task scope：整個 scheduler/string chain（含 scheduler producer、inspector 與 tests）改由 R014；RecommendationView 對應 R012 save contract/R013 Qt cutover；StrategySpec/Registry、executors 與 backtest/optimizer/UI callers 的 relocation 改由 R025（R007 為 data leaf contract、R008 為 recommendation/execution contract）；regime state owner 為 R022（R012/R015 是 save-time prerequisites，R021 負責 StockScreener I/O）；provider test mapping 加 R018；TMP-REC-06 明列 R011 creator/R029 remover；TMP-NUM-01 補齊 R002/R009、R011、R019/R020、R029 責任鏈；artifact/class-path unknown 對應 R006/R027，external/dynamic caller support 對應 R029。

SOL second-pass routing corrections：personalization producer/adapter 改列 R012 save contract / R015 personalization cutover；save/readback tests 改列 R012/R015，scheduler tests 維持獨立的 R014 分組；natural-outcomes scheduled CLI→R014、calibration integration→R010/R011/R026、market-data provider→R018；service/engine tests→R002 characterization/R011 execution capture/R019 evaluator，PIT/input coverage 另列 R018/R023 where applicable。僅修正 task mapping，inventory counts、hash 與 task scope 均未更動。

## 10. R001 replay 清冊勘誤

SOL 整合查核指出，基線原列將兩個 symbol 指向舊 module path，並把 provider 的 `list[dict]` 回傳契約套用到 `RecommendationReplayService.run_snapshot`。本次將 service 與 provider 分列，校正兩者路徑與回傳契約，並依 INV-02 及 TMP-REC-04 將 owner 記為 `app research／recommendation`。

SOL 後續審查指出，前版又把現行 legacy provider/list[dict] 路徑誤標為 TMP-REC-04 active。現行 provider 與其 mode-specific policy 仍 active，但 TMP-REC-04 bridge 尚未建立；R017 建立，R020 移除。同一 TMP 狀態檢查也區分了現行 `run_recommendation` 舊 list API 與 `RecommendationSaveRequest.build_result/persist` 舊保存呼叫形狀，和分別由 R011/R012 建立的 TMP-REC-02 相容 facade、TMP-REC-03 保存 adapter。R005/R017/R020 及相鄰 R011/R012 路由均保持原狀；此勘誤不重新評定 R001 PASS，也不代表 Wave 2 放行。

### 唯讀 source 與 caller 查證

- `app_module/recommendation_replay_service.py:17–25, 51–57` 定義 `RecommendationReplayService.run_snapshot(...) -> RecommendationSnapshotDTO`；第 51 行呼叫注入的 provider，第 53 行建立 snapshot DTO。
- `app_module/recommendation_portfolio_dtos.py:10–16` 定義 `RecommendationSnapshotDTO`，其中 `recommendations` 欄位型別為 `List[Dict[str, Any]]`。巢狀 row 型別不會改變 service 的頂層回傳型別。
- `app_module/recommendation_dataframe_provider.py:21` 定義 `RecommendationDataFrameProvider.__call__(...) -> List[Dict[str, Any]]`；provider 建立含 `total_score` 與 `factor_scores` 的 legacy recommendation rows。
- `app_module/recommendation_portfolio_backtest_service.py:83–85, 194–203, 609–610` 將 provider 注入 `RecommendationReplayService`、呼叫 `run_snapshot`、讀取 `snapshot.recommendations`，並以 `list[RecommendationSnapshotDTO]` 保存 snapshots。
- `ui_qt/views/backtest_view.py:53, 1270–1271` 匯入並建立 `RecommendationDataFrameProvider`，再將它注入 `RecommendationPortfolioBacktestService`。
- `FINAL_MIGRATION_SEQUENCE.md:158` 將 TMP-REC-04 owner 指定為 `app research／recommendation`，與 INV-02 的 application use-case owner 邊界一致。
- `REFACTOR_TASKS/R017.md:37–38` 建立 TMP-REC-04 並指定後續由 R020 移除；`REFACTOR_TASKS/R020.md:35` 明列移除 TMP-REC-04。`FINAL_MIGRATION_SEQUENCE.md:14–18, 89–100, 158` 將 bridge 放在 Block 3 建立、Block 4 退出，並明確說明它是把既有 provider output 封裝成 canonical execution 的暫時機制。
- `REFACTOR_TASKS/R011.md:36–37` 建立 TMP-REC-02；`REFACTOR_TASKS/R012.md:37–38` 建立 TMP-REC-03。現有 `app_module/recommendation_service.py:882–892` 保留舊 list API，`app_module/recommendation_save_coordinator.py:43, 53, 212` 保留舊保存請求方法；清冊將這些現行舊路徑與尚未建立的 TMP facade/adapter 分開記錄。

### SHA-256 與狀態

| 文件 | 第一輪勘誤前 SHA-256 | 第一輪勘誤後／本輪勘誤前 SHA-256 | 本輪勘誤後 SHA-256 |
|---|---|---|---|
| `docs/06_qa/REFACTOR_BASELINE_R001_20260922.md` | `EF39925E13EF37D3D920B156AF1C34129A866F7C3815F8F2AFE34F6CFA097135` | `71E7C9636D87010FFD7E0A4A354FEF4AB2298F7391B46B12FC53BF9E7DEBE171` | `93E4DDDC29BACCD9483EB6B35D83E5078C77B2A318508A82B452CD40EF028867` |
| `R001_IMPLEMENTATION_REPORT.md` | `8D9FB2D1D5D64C386E657F4A23DB2F364E3D373692568D7D24C6C07C498DFDD2` | `4F544973484D417919E1408CED6EA0D7B8E45F62E5A2B9CF8427652A5B51D6E7` | 交付摘要列示 |

報告的本輪後 SHA-256 於交付摘要列示，避免在檔案內嵌入自身 hash。最終狀態仍為 READY_FOR_REVIEW。

IMPLEMENTATION_STATUS: READY_FOR_REVIEW
