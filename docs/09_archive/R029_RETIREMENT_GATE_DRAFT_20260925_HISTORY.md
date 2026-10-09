# R029 retirement gate 草稿（2026-09-25）

**狀態：SUPERSEDED（2026-09-25）。** 本文件是裁定前草稿，保留當時的清冊與 gate 假設作歷史脈絡；current verdict、正式 ledger 狀態及有界證據以 [R029 implementation/acceptance report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R029_IMPLEMENTATION_REPORT.md) 和 [FINAL_MIGRATION_SEQUENCE.md](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md) 為準。R029 裁定為 `ACCEPTED_WITH_RETAINED_COMPATIBILITY`，未執行破壞性 cleanup。

## Gate 前置狀態

- C2 141-test current union 有兩個 `tests/test_personalization_generation_cli.py` fixture failures，owner 修復後待重生 manifest／重跑；Workbench 84P、broad mypy 724 files／0 issues、67-file `py_compile` 已通過。Update validator 兩次均為 25P／1 cleanup failure／4S、exit 1（WinError 32 TEMP SQLite teardown，詳見 [C2 mandatory gates receipt](../06_qa/C2_MANDATORY_UI_STATIC_GATES_20260925.md)）。因此 C2 final 尚待 root 依既有 teardown baseline 與重跑 route 裁定，R029 目前仍是 DRAFT。
- R026／`TMP-ML-01` 仍由其 active slice 管理；R027 為 `INCONCLUSIVE`、`AB-ML-01=OPEN`、`TMP-ML-02=ACTIVE`，因此 R028 保持 `BLOCKED`。R029 規格允許 R028 未完成而由 `TMP-ML-02` 具名列管，故 R028 本身不是 R029 blocker。
- R020 的獨立 review 已接受其 bounded recovery 與 R005 vectors；目前沒有剩餘的 R020-specific recovery/R005 vector 缺口。`TMP-REC-04` 的 R020 子範圍仍須等 C2 mandatory gates 後才能裁定，`TMP-NUM-01` 是獨立 active gate。
- 既有詳細路徑、DTO import symbols、可重跑 AST/search 命令與支持期限制見 [R029 retirement preflight](R029_RETIREMENT_PREFLIGHT_INVENTORY_20260925_HISTORY.md)。該清冊未涵蓋未檢入部署設定、外部腳本或未知 pickle/joblib class paths；不得將 repo 搜尋結果寫成所有 caller 均為零。

## 有限 retirement 分帳

| 帳目 | 草稿狀態 | 本輪可支持的裁定 | 完成前剩餘條件／owner |
|---|---|---|---|
| `TMP-REC-02` list/latest-state 與 v1 event/callback sidecar | **ACTIVE；部分證據** | repo direct search 未找到 `.run_recommendation(` production caller；`application_ports.py` 仍宣告多個 `last_*` 欄位、recommendation tab QA 仍讀取 latest state，`execute.py` 仍發布 legacy state。v1 event/callback sidecar consumer 尚無完整 inventory。 | 把 ports/latest-state、UI/CLI/scheduler、dynamic/string、外部支援期與 sidecar consumers 分開列清；逐個完成 cutover/parity 後再關閉。Owner：app recommendation compatibility。 |
| `TMP-REC-05` DTO compatibility imports | **BLOCKED；具名保留** | `RecommendationDTO` 與 `RecommendationResultDTO` 的實際 class owner 是 `app_module.dtos`；preflight 列有 17 個 source import paths 與各自符號用途。canonical execution 僅在相容 projection 邊界產生 v1 DTO。R006 尚無這些 DTO 的 serialized qualified-name 依賴證據。 | 保留 class、wire projection 與 decoder；只有被證明純 wrapper/dead import 才可清除。不可把未知 serialized dependency 推定為永久 alias，也不可搬走或刪除 class。Owner：recommendation contract/app compatibility。 |
| `TMP-REC-06` 雙 engine selector | **建議在 R029 acceptance 時關閉 selector 條件；保留 ABI regression** | `RecommendationService._run_recommendation_body()` 只轉呼 `_run_recommendation_body_result()` 再 materialize legacy DTO；`run_recommendation()` 也走同一 canonical body。有限 source search 未見第二個計算 engine 或 selector。原 paired test 現在比較 legacy list ABI 與 execution ABI，保留排序、DTO 全欄、Decimal 與 `last_*` parity assertions。 | C2 gates 通過後，由 R029 更新 authoritative ledger 並正式改列永久相容 ABI regression。已把 stale `tmp_rec06`／baseline-lane 測試名稱與註解改為 ABI parity 說明；不刪測試。Owner：recommendation compatibility/test。 |
| `TMP-STR-01` strategy facades | **ACTIVE** | 已知 direct source caller 已遷移；現有 literal-path fixture 仍覆蓋相容 alias。repository search 不等於 external/dynamic caller absence。 | 補有限 dynamic/string、scheduler/CLI 與外部支援期證據；若發現 serialized class path，分列永久 alias。Owner：decision strategy/app compatibility。 |
| `TMP-NUM-01` numeric/row boundary | **ACTIVE；R020 bounded slice 不足以關閉** | R020 typed handoff 與 NumPy 1/2 native-oracle slice 已驗收其限定範圍；不包含所有 precision/rounding/tie-break 與 caller cutover 條件。 | 依其獨立 ledger 逐項完成 precision、rounding、tie-break、Decimal 字串及 caller parity；不以 R020 acceptance 擴大宣稱。Owner：decision recommendation/app codec。 |
| `TMP-RGM-01` RegimeService compatibility | **ACTIVE** | R022 bounded policy/state slice 已接受；fallback、舊 detector adapter 與 wrappers 仍存在。 | 完成 caller/support-period inventory，確認 active producers 注入同一 service，保留 identity、多日及 source-failure regression 後才逐步退休。Owner：regime/application composition。 |
| `TMP-ML-01` | **ACTIVE，由 R026 管理** | R026 多個有界 source-revision/capability slices 各自有 evidence；不代表 R026 complete。 | 以 R026 current final route、boundary review 與 C2 依賴裁決；R029 不重開已接受的 bounded slices。 |
| `TMP-ML-02` | **ACTIVE；具名受限** | R027 有 848 個 exact timing/snapshot 差異，裁決 `INCONCLUSIVE`；R028 的 prerequisite 要求 R027 PASS。R029 可在此項具名保留的情況下繼續。 | 保留 Direct source-path 與 artifact reader/alias 限制；不得將 R028 標記可執行或以本草稿批准搬移。Owner：R027/R028 ML identity。 |
| `TMP-REC-04` R020 子範圍 | **R020 bounded criteria 已接受；整體仍待 C2** | 已核對具體 R005 policy vectors、typed handoff 與五個 distinct persistent crash states；沒有剩餘 R020-specific recovery/vector gap。 | C2 mandatory gates 通過後才能把 R020 子範圍寫入 ledger closeout。這不等於宣布所有 caller/mode 的 unlimited parity；`TMP-NUM-01` 另列。Owner：app replay/persistence。 |
| R006 serialized inventory | **證據不足，具名保留** | 已知 controlled fixture 不等於正式 model/class-path inventory；selected OOC/sidecarless artifact 仍有未知 class path，且未知 binary 未載入。 | 保留 historical readers、必要 alias 與 rejection policy；只有安全授權的 artifact metadata 才能補證，不解載未知檔。Owner：R006 artifact/ML custodian。 |

## REC-06 相容測試更名與局部驗證

測試現名為 `test_legacy_list_abi_and_execution_abi_match_with_isolated_side_effects`，位於 `tests/test_recommendation_execution_use_case.py`。更新只更正文意與 fixture label，保留全部行為斷言。以 fresh system TEMP、`PROFILE=test` 執行：

```powershell
$qaRun = Join-Path $env:TEMP 'r029r06_365a4088'
New-Item -ItemType Directory -Path $qaRun | Out-Null
$env:TEMP = $qaRun; $env:TMP = $qaRun; $env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $qaRun 'data'; $env:OUTPUT_ROOT = Join-Path $qaRun 'output'
.\.venv\Scripts\python.exe -m pytest tests\test_recommendation_execution_use_case.py::test_legacy_list_abi_and_execution_abi_match_with_isolated_side_effects -q -rs -o addopts= -p no:cacheprovider --basetemp (Join-Path $qaRun 'p') --tb=short
```

- 結果：`1 passed in 0.77s`，無 skip。
- pytest log：`C:\Users\archi\AppData\Local\Temp\r029r06_365a4088\pytest.log`，100 bytes，SHA-256 `3B1D4F2D5FCF76BDF770CEDFA8AF676D4F13E05EA4A69F5634FF663FB69A5269`。
- 隔離根：`C:\Users\archi\AppData\Local\Temp\r029r06_365a4088`；`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP`、pytest `basetemp` 均位於此根，`PROFILE=test`。

此單一 ABI regression 僅驗證改名後的既有測試；不代替 R029 retirement acceptance 或 C2 union。

## 建議 ledger 更新（待 R029 acceptance）

將 `TMP-REC-06` row 改為：

> `TMP-REC-06` engine-selector 條件已由有限 source/call-graph review 排除：legacy list API 與 execution API 共用同一 canonical calculation body，未發現第二 engine 或 selector。保留 `test_legacy_list_abi_and_execution_abi_match_with_isolated_side_effects` 作永久相容 ABI parity regression；此測試不表示有雙 engine oracle。狀態僅在 C2 mandatory gates 通過且 R029 acceptance 後改為 `permanent compatibility regression`。

其他 TMP rows 維持上表的 ACTIVE、具名保留或 evidence-insufficient 狀態；不得在尚未完成 caller/support/serialized evidence 時批次關閉。

## R031 導覽交接

31 個 task 的 report/evidence links 與未找到獨立 implementation report 的例外列於 [R031 31-entry report index draft](../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。R023、R027、R028 的既有入口已具名；不新增重複實驗。
