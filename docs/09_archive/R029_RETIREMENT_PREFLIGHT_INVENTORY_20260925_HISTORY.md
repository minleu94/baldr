# R029 退休前唯讀盤點（2026-09-25）

## 狀態與範圍

本文件是 R029 cleanup 前的唯讀證據清冊，不是 R029 完成報告，也沒有修改 production、tests、fixtures、既有 ledger 或正式資料。本輪沒有執行 pytest、py_compile、mypy、UI 或 ML 建置；只讀取權威文件與目前 source，並以 `rg`／Python AST 尋找 direct、literal/string import 與 DTO import 引用。

目前可開始有限度整理 caller 清單，但不能據此移除暫時相容介面：C2 只有 current union pytest baseline 收據，mandatory Workbench／Update validator／broad mypy gates 仍待 active implementation 穩定後完成；R026 仍為 `IN_PROGRESS`／`TMP-ML-01=ACTIVE`；R027 為 `INCONCLUSIVE`、`AB-ML-01=OPEN`，R028 因此 `BLOCKED`，`TMP-ML-02=ACTIVE`。R029 task 允許在 R028 未完成時明確保留 `TMP-ML-02`，但 R020–R026 其餘依賴及 C2 gate 尚未齊。

本盤點不改變 R020 裁定：R005 向量與已補 process-crash recovery slice 未見 R020-specific 剩餘缺口；`TMP-REC-04` 的 R020 子範圍可在 C2 mandatory gates 通過後關閉。`TMP-NUM-01` 的獨立數值退出條件仍需另行處理，不反向阻塞 R020。

## 逐項盤點與目前分類

| 帳目 | 目前 source／文件證據 | 目前分類與 owner | 退出前的有限條件 |
|---|---|---|---|
| `TMP-REC-02` list/latest-state façade 與 v1 event/callback sidecar | `RecommendationService.run_recommendation()` 仍存在（`app_module/recommendation_service.py:1164`）。本輪 exact call search 沒找到 repo 內 `.run_recommendation(` 生產呼叫；可作為「未找到直接呼叫」的子證據。另一方面，`app_module/application_ports.py` 仍要求 `last_run_context`、`last_excluded_candidates_json`、`last_screening_matrix`、`last_why_not_payload_json`、`last_liquidity_gate_payload_json`；`scripts/qa_validate_recommendation_tab.py` 仍讀取 last-state，且 `recommendation/execute.py` 仍有明確 legacy state publisher。ledger 仍記載 Qt／scheduled／personalization CLI／外部 caller，但與本次 exact direct-call 搜尋有落差，須在正式 R029 逐項更新並標明 dynamic/string 路徑。v1 event/callback sidecar consumer 清冊及 parity 本輪未建立。 | **ACTIVE；部分 direct-call 條件已有證據，整項因 latest-state／sidecar／外部支援期不足而 blocked。** Owner：app recommendation compatibility。 | (1) 把 ports/latest-state consumers 與 direct、dynamic、string、scheduler、UI、CLI callers 分別列完；釐清 ledger 舊 caller 名單；外部支援期有明確截止與 smoke。 (2) 列出 v1 event/callback consumers，逐一改接 typed execution/read model 並完成 parity，再移除 sidecar。歷史 JSON/artifact decoder 永久保留，不屬此項刪除目標。 |
| `TMP-REC-05` 舊 recommendation DTO import compatibility | `app_module/dtos/__init__.py` 實際定義 `RecommendationDTO` 與 `RecommendationResultDTO`，不是純 re-export。下方列出 17 個直接 import 路徑、各自符號／用途與是否為 canonical producer。`RecommendationDTO` 是既有 v1 projection/wire DTO；`RecommendationResultDTO` 承接舊結果讀寫形狀。R006 沒有這兩個 DTO qualified class path 的序列化依賴證據；不把它們宣稱為永久 pickle alias，也不刪 class 或搬移 owner。 | **BLOCKED，具名保留。** Owner：recommendation contract／app compatibility。當前 source owner 是 `app_module.dtos` 的兩個實際 class；canonical execution 使用 typed `RecommendationExecution`，僅在相容投影邊界產生 v1 DTO。 | 逐項分辨 canonical-to-v1 projection、v1 consumer、歷史 reader 與 QA；只清除已證明純 import wrapper／未使用 import。保留 class、wire projection 與 decoder；外部支援期及已存序列化 qualified path 沒有足夠證據時，維持具名相容狀態，不做大搬移。 |
| `TMP-REC-06` legacy/new execution engine selector | 目前沒有找到兩套計算 engine 或 production engine selector。`RecommendationService._run_recommendation_body()`（目前約第 2673 行）只呼叫 `_run_recommendation_body_result()` 並 materialize legacy DTO；`run_recommendation() → execute_recommendation()` 也呼叫同一 canonical body。現存 `test_tmp_rec06_paired_legacy_and_execution_lanes_match_with_isolated_side_effects` 以獨立 service/DB/output root 比較兩個相容 ABI 入口，檢查排序、DTO、Decimal 與 `last_*` projection state；它不是兩個計算 engine 的 oracle。以 repo Python source 的 `_run_recommendation_body`／`_run_recommendation_body_result` 定義與呼叫搜尋，未找到另一個 legacy calculation body 或 selector。 | **建議 TMP-REC-06 engine-selector 條件關閉；正式 ledger 狀態待 R029 更新。** Owner：recommendation compatibility／test owner。 | 正式 R029 更新 ledger 與命名：將該測試及 stale baseline-lane 註解改為永久的 legacy-list ABI 對 execution ABI parity regression；保留有用 expected values、隔離副作用與型別／狀態 assertions。不要保留「臨時雙 engine harness」分類，也不要刪除永久相容 regression。 |
| `TMP-STR-01` strategy app facades | R025 報告記錄全 repo source search 除 facades 與 alias identity 測試外，沒有舊 app strategy import caller；本輪 repo Python literal-path search 只命中 `tests/test_decision_strategy_owner.py` 的相容 alias 測試。JSON/YAML inventory 只證明保存 strategy ID/spec fields，沒有 executor class path 證據。 | **ACTIVE；direct source caller 已遷移，支援期與 dynamic/string/external search 尚未封口。** Owner：decision strategies／app compatibility。 | 取得 dynamic/importlib/string、scheduler/CLI 及外部支援期的逐 alias 清冊；若發現已保存的 qualified class path，拆成永久 alias 並以 exact deserialize test 證明，再只移除已證明無 caller 的 aliases。R025 source／parity acceptance 不代表整項 facade 可立即刪除。 |
| `TMP-NUM-01` legacy score／row boundary | ledger 範圍為 `RecommendationService.run_recommendation`、`RecommendationDataFrameProvider.__call__` 與 v1 DTO 浮點分數／row dict 邊界。R020 已移除 generic row-dict→canonical child builder，並驗 concrete typed handoff；C2 current pytest baseline 包含 bounded numeric/replay slices。 | **ACTIVE；R020 已清除的 bridge 不需重建，但獨立 numeric gate 尚未通過。** Owner：decision recommendation／app codec。 | 逐項保留 precision、rounding、tie-break、十進位字串與 caller parity 證據；只有等價測試及 caller cutover 完成，才可刪除 legacy numeric 分支。不要把 NumPy/ML 矩陣浮點範圍併入本項，也不要把 R020 bounded acceptance 擴大為 NUM-01 closure。 |
| `TMP-RGM-01` RegimeService compatibility | R022 報告確認已知 production UI、composition、personalization、scheduled callers 明示注入／共用 `RegimeService`；`RecommendationService.__init__` 仍有未注入時的 persistent fallback、舊 `regime_detector` adapter，並保留 `detect_regime`／`get_strategy_config_for_regime` wrappers。測試與 QA fake detector seam 仍存在。 | **ACTIVE，具名相容入口待退休。** Owner：Regime／application composition。 | 完成 direct/dynamic/scheduler/CLI/external caller 與支援期盤點；確認所有 active producer 明示注入同一 service；identity、多日與 source-failure regression 維持通過後，逐步移除 fallback／adapter／wrapper。R022 說明此為 source API，沒有證明 serialized alias。 |
| R006 serialized ML／artifact inventory | [R006 QA 清冊](../06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md) 與 [R006 實作報告](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md) 記載 Direct 15 個 source paths 均有 bytes/SHA；當時 14/15 個 loaded module fingerprint 相符，1 個來源當次未載入。18 個已清點正式資產只做唯讀 hash custody。SafeShadow 成功案例只使用 pytest 創建的 `test_refactor_ml_compatibility_baseline.ControlledFixtureModel`。selected OOC joblib head 與兩個 sidecarless legacy pickle 的 estimator class path／相容性仍 unknown，未知 binary 未載入。 | **證據不足，具名保留；不屬於可清除 alias 的零命中證據。** Owner：R006 artifact／ML loader custodian。 | 保留所有歷史 readers、必要 class aliases 與 loader rejection policy；不要為了 R029 解載未知資產或把受控 fixture 當正式 class path。只在安全、獲授權且不載入未知 binary 的條件下補充 artifact metadata；若一直無證據，明列 unknown 並保留。 |

### REC-05 import 路徑與用途明細

此表依 `app_module.dtos` AST imports 列出所有在 `app_module/`、`ui_qt/`、`scripts/` 中引用兩個 recommendation DTO 的 17 個 source paths。`canonical producer` 表示該路徑是否把 canonical `RecommendationExecution` 轉成 v1 DTO；讀取、協作、持久化舊形狀不算 canonical producer。

| Source path | Imported symbol(s) | 用途 | canonical producer? |
|---|---|---|---|
| `app_module/__init__.py` | `RecommendationDTO`, `RecommendationResultDTO` | public app package export facade | 否；只轉出型別 |
| `app_module/advice_composer.py` | `RecommendationDTO`, `RecommendationResultDTO` | advice composer 接受 v1 recommendation input/result | 否；consumer |
| `app_module/application_ports.py` | `RecommendationResultDTO` | 舊 recommendation result service protocol | 否；型別契約 |
| `app_module/decision_desk_service.py` | `RecommendationResultDTO` | saved recommendation 提供給 decision desk | 否；consumer |
| `app_module/personalization_save_adapter.py` | `RecommendationResultDTO` | personalization save/read/verification 相容邊界 | 否；保存 adapter |
| `app_module/portfolio_source_adapter.py` | `RecommendationDTO`, `RecommendationResultDTO` | recommendation result 轉 portfolio source | 否；consumer |
| `app_module/recommendation/body_result.py` | `RecommendationDTO` | 凍結 legacy DTO 欄位 snapshot 並按需求 materialize | 否；相容快照 |
| `app_module/recommendation/codec.py` | `RecommendationDTO`, `RecommendationResultDTO`（4 個 import sites） | legacy wire encoder／decoder | 否；codec；歷史讀取保留 |
| `app_module/recommendation/execute.py` | `RecommendationDTO` | `project_legacy_recommendations()` 從 canonical execution 建立 v1 list projection | **是；明確相容投影 producer** |
| `app_module/recommendation/queries.py` | `RecommendationResultDTO` | legacy saved result/read model union 與 decoder | 否；歷史／相容 reader |
| `app_module/recommendation_repository.py` | `RecommendationDTO`, `RecommendationResultDTO` | 舊 JSON result save/load | 否；legacy persistence boundary |
| `app_module/recommendation_service.py` | `RecommendationDTO` | `run_recommendation()` 回傳 compatibility list，內部呼叫 `execute_recommendation()` | **是；list façade 的 v1 projection producer** |
| `app_module/user_declared_holding_research.py` | `RecommendationResultDTO` | 從既有保存 JSON 還原條件上下文 | 否；歷史 reader |
| `scripts/qa_validate_decision_loop.py` | `RecommendationDTO`, `RecommendationResultDTO` | synthetic QA sample | 否；QA |
| `scripts/qa_validate_recommendation_tab.py` | `RecommendationDTO`（2 個 import sites） | recommendation view output／欄位 QA | 否；QA |
| `scripts/qa_validate_research_journey_qt.py` | `RecommendationDTO`, `RecommendationResultDTO`（3 個 import sites） | journey QA helper／sample DTO | 否；QA |
| `scripts/run_personalization_recommendation.py` | `RecommendationDTO` | 目前只在 import 出現，未見同檔其他引用；待 caller owner 確認是否為 dead import | 否；疑似未使用 import |

下列唯讀 AST 命令可重跑完整 path/symbol 清單；它解析 import node，不把文件文字或測試 fixture 誤計成 source import：

```powershell
@'
import ast
from pathlib import Path
root = Path.cwd()
for area in ("app_module", "ui_qt", "scripts"):
    for path in sorted((root / area).rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app_module.dtos":
                names = [a.name for a in node.names if a.name in {"RecommendationDTO", "RecommendationResultDTO"}]
                if names:
                    print(f"{path.relative_to(root).as_posix()}:{node.lineno}: {','.join(names)}")
'@ | .\.venv\Scripts\python.exe -
```

### REC-06 engine-selector inventory 與永久 ABI regression

`app_module/recommendation_service.py::_run_recommendation_body()` 目前只是 `_run_recommendation_body_result()` 的 legacy-list materialization wrapper；canonical `run_recommendation → execute_recommendation` 也進入同一 `_run_recommendation_body_result()`。在有限 repo source search（`app_module/`、`tests/`、`scripts/`、`ui_qt/` 中 `_run_recommendation_body`／`_run_recommendation_body_result` 定義與引用）沒有找到第二個 active calculation engine 或 engine selector。精確搜尋可重跑：

```powershell
rg -n "_run_recommendation_body\(|_run_recommendation_body_result\(|legacy baseline lane|engine selector|paired legacy" app_module tests scripts ui_qt --glob '*.py' --glob '*.md'
```

現存 `test_tmp_rec06_paired_legacy_and_execution_lanes_match_with_isolated_side_effects`（`tests/test_recommendation_execution_use_case.py` 約第 255 行）仍有用：兩個獨立 service、DB/output root 分開，分別走 legacy DTO-list wrapper 與 execution ABI，對照 top-N/order、完整 DTO 欄值、Decimal 型別／字串與 `last_*` projection state。依目前 source call graph，這是同一 canonical engine 的兩入口相容 parity regression；`tmp_rec06` 名稱及「baseline lane bypasses execute」註解已過時。正式 R029 應只把名稱／註解改成永久 ABI parity 測試、更新 ledger 分類，保留 regression assertions；本輪不改 test bytes。

## 可核對的搜尋範圍與邊界

本輪唯讀檢查涵蓋 `app_module/`、`ui_qt/`、`scripts/`、`decision_module/` 與 `tests/` 中相關 Python 路徑，並查詢 `app_module.strategy_spec`、`daily_signal`、`strategy_registry`、`strategies`、`strategy_executor_adapter`、`reason_tags` 字串；另以 AST 列出 `from app_module.dtos import RecommendationDTO/RecommendationResultDTO`。結果只說明目前 repository bytes，無法證明外部套件、使用者腳本、未檢入排程設定或部署環境沒有動態 caller。因此「repo direct search 零命中」不得寫成「所有 caller 為零」。正式 R029 需將每次搜尋的 commit/source SHA、搜尋範圍、命中與排除理由一併凍結。

已知另一份架構工作 R030 的 boundary evidence 包含 `data_module/company_registry.py`、`data_module/tpex_daily_price_backfill.py` 反向 import `FactorDiagnostic`，以及 `decision_module/industry_mapper.py` 的 DBManager I/O。這些不是 R029 retirement alias，應依 R030 authority 獨立判斷 owner；不可透過 broad allowlist 抹除。本盤點未改 shadow guard。

## R031 報告完整性 crosslink 入口

| 切片 | 現有報告入口 | R031 引用時的狀態 |
|---|---|---|
| R023 | [R023 fundamental／monthly-revenue contract migration QA](../06_qa/R023_FUNDAMENTAL_MONTHLY_REVENUE_CONTRACT_MIGRATION_20260923.md) | 引用既有 bounded evidence；不因本清冊重跑。 |
| R027 | [R027 technical publication／ML identity isolation QA](../06_qa/R027_TECHNICAL_PUBLICATION_ML_IDENTITY_ISOLATION_20260923.md) | `INCONCLUSIVE`／`AB-ML-01=OPEN`／`TMP-ML-02=ACTIVE`；R028 `BLOCKED`。 |
| R028 | [R028 task](../01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R028.md) 與上列 R027 QA | 目前檔案清冊未找到 R028 implementation report；依 R027 verdict 不得宣稱完成或解鎖。 |

R031 最終報告應直接引用上述入口與明確狀態，不需創造新的 R023/R027/R028 實驗收據。

## 讀取的權威依據

- [R029 task](../01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R029.md)
- [FINAL_MIGRATION_SEQUENCE](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md)，Block 5 與 retirement ledger
- [R022 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R022_IMPLEMENTATION_REPORT.md)
- [R025 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R025_IMPLEMENTATION_REPORT.md)
- [R020 independent handoff review](../06_qa/R020_TYPED_HANDOFF_INDEPENDENT_REVIEW_20260925.md)、[R020 hard-exit recovery QA](../06_qa/R020_PROCESS_CRASH_RECOVERY_HARD_EXIT_QA_20260925.md)
- [C2 current union pytest baseline](../06_qa/C2_CURRENT_UNION_PYTEST_BASELINE_20260925.md)
- [R006 serialized/ABI inventory](../06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md)
