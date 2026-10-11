# R025 實作報告：strategy contracts／registry／executors 移至 decision

> **時點／範圍導覽（2026-10-11）：** 本報告的 `ACCEPTED_SCOPE` 與 `TMP-STR-01 ACTIVE` 只記錄 R025 截至 2026-09-23 的有限策略 owner 移轉及當時 retirement gate 狀態。R029 後續接受 bounded caller／owner cutover，將 9 個舊 app public／qualified-name aliases 分類為 `PERMANENT_COMPATIBILITY`；R031 current row 同樣確認必要 9 個薄 aliases 保留。此 bounded disposition 不表示自然舊 executor artifact 存在、aliases 已刪除或整體重構已完成。後續裁定與退休帳狀態見 [R029 retirement gate acceptance report](R029_IMPLEMENTATION_REPORT.md)、[R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 及 [FINAL_MIGRATION_SEQUENCE](../FINAL_MIGRATION_SEQUENCE.md)。

**Task**：[R025 task spec](../REFACTOR_TASKS/R025.md)　|　**日期**：2026-09-23　|　**實作者**：GPT-6 Luna Max（Codex subagent）

**IMPLEMENTATION_STATUS: ACCEPTED_SCOPE**

**R025_GATE_STATUS: ACCEPTED_SCOPE**

**2026-09-23 R025 implementation-time snapshot（後續 status 見上方 R029／R031 links）：** R025 把策略契約、唯一 mutable registry、三個既有 executor 與理由標籤 generator 的實作 owner 搬到 `decision_module`。公式、threshold、signal schema、持久化 keys/defaults、排序、回測結果與 UI 策略清單均保留；舊 app import paths 由 `TMP-STR-01` 薄 facade 相容至 R029 caller retirement gate。

## 1. HEAD、dirty baseline 與權威依據

- 驗證起點及報告完成時 `HEAD` 均為 `e16f92928980a025d24bd5b023eeadf9d6a31daa`；期間未建立 commit。
- 開始時共享工作樹已含多個其他 owner 的未提交變更，包含 `app_module/update_service.py`、`app_module/recommendation_service.py` 與 R023/R024 相關 paths；因此不將整體 working-tree diff 宣稱為 R025。R025 沒有修改 `app_module/update_service.py`；對 `app_module/recommendation_service.py` 僅改一個 `StrategySpec` import hunk，其他該檔變更屬 R018。
- 未 stage、commit、reset、clean；沒有讀寫正式資料、模型、checkpoint、scheduler 或 artifact。pytest 使用 `PROFILE=test` 與新 TEMP data/output roots；Update Tab QA 自建 temporary synthetic fixture。
- 依序遵循根目錄 `AGENTS.md` 必讀文件與 `git_exclusions.md`；並閱讀 R025、R001/R005 baseline、FINAL_TARGET_ARCHITECTURE、FINAL_EXTENSIBILITY_MODEL、FINAL_ARCHITECTURE_INVARIANTS、FINAL_MIGRATION_SEQUENCE，以及 execution、testing/QA、documentation agent 指引。手冊無需修改：UI 入口、選項與操作結果沒有變更。

## 2. Inventory 與 compatibility 判斷

遷移前唯一註冊順序為：

1. `baseline_score_threshold`
2. `momentum_aggressive_v1`
3. `stable_conservative_v1`

`StrategyRegistry.register()` 對重複 ID 原樣拋出 `ValueError("策略 {strategy_id} 已經註冊過了")`。R001 inventory 記錄 `StrategySpec.to_dict/from_dict` 的 JSON/YAML caller 保存 strategy ID/spec fields，不保存 executor class path；R001 artifact/source 清查沒有證據可把任何舊 executor qualified name 列為永久 serialized alias。因此 app qualified source paths 登錄為 `TMP-STR-01`，不宣稱永久 alias。R029 必須再做 direct/dynamic/string/external caller 清查；若找到實際持久化依賴，應先將該 alias 拆成永久相容項並保留 exact deserialize test。

已知直接 caller：`BacktestService`、batch backtest、optimizer、walk-forward、RecommendationService、Qt Backtest view/main、QA scripts 與相關 tests。R001 指出 Qt 原先直接讀 `StrategyRegistry._registry`；現改呼叫公開 metadata query，combo 的 ID、名稱及順序仍由 registry 提供。`ml_module/` 沒有 `StrategySpec`、`StrategyRegistry`、`generate_signals` 或這三個 strategy IDs 的引用；本次未發現策略輸出參與 ML candidate identity 的連線，因此 R006 frozen ML contract、feature、eligibility、projection 與 artifact 未變。

## 3. 變更內容

### Canonical decision owner

新增 `decision_module/strategies/`：

- `contracts.py`：`StrategySpec`、`StrategyMeta`、`StrategyExecutor`、`DailySignalFrame` 與 `create_daily_signal_frame`。
- `registry.py`：沿用同一註冊、取得、列表與 duplicate rejection 語意；新增唯讀 `get_strategy_meta()`，讓 Qt 不再碰 registry 私有 dict。
- `baseline_score_executor.py`、`momentum_aggressive_executor.py`、`stable_conservative_executor.py`：三個既有 executor 的唯一實作 body。
- `simple_strategy_executor.py`：保留已棄用 adapter 的單一 body，供舊 source path 相容。
- `decision_module/reason_tags.py`：executor 直接呼叫的 `ReasonTagGenerator` 實作。
- 套件初始化依既有順序註冊三個 ID；app facade 不另建 registry、不重複註冊。

### 舊路徑與 caller

`app_module.strategy_spec`、`daily_signal`、`strategy_registry`、`strategies`（含三個 executor 子模組）、`strategy_executor_adapter.SimpleStrategyExecutor` 與 `reason_tags.ReasonTagGenerator` 均縮為指向 decision owner 的 re-export。R025 已切換 Backtest、batch、optimizer、walk-forward、Qt main/view、QA scripts 與策略測試的 import；RecommendationService 僅切換 `StrategySpec` import。全 repo source search 除相容 facade 與專門驗證 alias 的測試外，沒有殘留舊 app strategy import caller。

新增 `tests/test_decision_strategy_owner.py` 鎖定 ID/order/metadata/duplicate、spec keys/defaults/round-trip、signal validation/alignment、app alias object identity、唯一 registry 與 decision 不反向 import app；新增 `tests/test_ui_qt_strategy_list_contract.py` 鎖定 Backtest combo 三個 ID、顯示名稱及次序。更新 `scripts/check_look_ahead_bias.py` 掃描 canonical decision executor paths。

### 同步文件

更新 `FINAL_TARGET_ARCHITECTURE.md`、`FINAL_EXTENSIBILITY_MODEL.md`、`system_architecture.md`、`PROJECT_NAVIGATION.md`、`PROJECT_SNAPSHOT.md` 與 `DOCUMENTATION_INDEX.md`，將策略實作 owner 導向 decision。`FINAL_MIGRATION_SEQUENCE.md` 僅增加/更新 R025 自有的 `TMP-STR-01` row；R015 凍結 row 未改。Manual 無使用者可見變更，不需改操作文件。

## 4. 行為、數值與 look-ahead parity

- **AST body 比對**：以 `git show HEAD:<舊 app source>` 對照 decision owner，對 14 個既有 symbols/methods 比對 AST；只正規化舊→新 import module path，registry `list_strategies` 只排除已提升到模組層的舊 local import。14/14 一致、0 mismatch；新增的 `get_strategy_meta()` 為單一唯讀 query。三個 executor class body 僅 import owner 路徑改變。
- **StrategySpec／Meta**：`StrategySpec.to_dict()` 十個 key 的名稱與順序、欄位 defaults、`from_dict()` 及既有 parameter round-trip 不變。R001 保存證據僅涵蓋 strategy IDs/spec fields，無 executor class path 持久化證據。
- **Strategies／signal**：三個 ID 順序、metadata、duplicate error、fixed/missing threshold mode 等價及 quantile 參數保持；`DailySignalFrame` 的日期驗證、reindex fill、reason tags、regime 預設與輸出欄位由原 class AST body 搬移。現有 Backtest、batch、walk-forward、optimizer 與 Qt workflows focused tests 通過。
- **Look-ahead**：`scripts/check_look_ahead_bias.py` 現掃描 decision owner 的三個內建 executor，命令完成且零違規。這個靜態 guard 只涵蓋其索引規則；原 executors 的既有 `bfill()` 前處理仍在，缺值資料的因果性不由本次搬移證明。R025 不得改策略公式，因此保留原行為並列為既有 residual。
- **Decimal／float**：沒有新增核心金融金額、資金、部位、風控或績效公式，也沒有精度改寫；原策略 scoring DataFrame 仍使用既有 pandas/numpy 分數型別。`ReasonTagGenerator.analyze_tag_statistics()` 有既有 `float`／`np.std` 聚合，但 repo-wide search 找不到任何 caller；四個 executor（含 deprecated Simple adapter）只呼叫 `generate_tags()`。該統計 helper 目前不在 Backtest/portfolio performance 執行鏈，body 未改；若日後接入核心績效路徑，須另用 Decimal/bp 契約處理。Simple adapter 亦保留原有 float normalization 與 backfill，現已棄用且 repo 無 runtime caller，沒有新增該數值行為。
- **ML／持久化**：沒有修改 ML source、R006 fixtures、資料、model/checkpoint 或 artifact；不需 ML candidate identity output fixture，因 inventory 未發現策略輸出至 ML identity 的 caller path。`TMP-STR-01` 中舊 source import alias 不是已證實 serialized alias。

## 5. 驗證結果

所有需寫入資料的 pytest 使用獨立 temporary roots，無正式資料存取。

| 驗證 | 結果 |
|---|---|
| 搬移前 characterization baseline：threshold、params、Backtest diagnostics/parallel、batch、walk-forward、optimizer | 51 passed、1 個既有 same-day close execution-price warning |
| 搬移後 strategy/Backtest/walk-forward/optimizer/Qt focused suite（含兩個新增 contract tests） | 100 passed、1 個同一既有 warning，22.78 秒 |
| `scripts/check_look_ahead_bias.py` | exit 0，三個 canonical executor paths，零違規 |
| `tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 84 passed |
| `scripts/qa_validate_update_tab.py` | 最終獨立 fresh TEMP 原命令 exit 0：25 passed、0 failed、4 skipped；所有 fixture 寫入 script 建立的 temp root |
| `python -m py_compile` | 44 個 strategy-related Python 檔案通過 |
| broad mypy：`mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` | R025 驗證 snapshot 為 **693 source files、0 issues**。並行編輯期間曾在 R018 新檔 `app_module/recommendation/input_preparation.py:182` 觀察到 1 個 mypy error；root 最新共享工作樹 gate 已重跑並通過：**693 source files、0 issues** |
| root 獨立 focused rerun 與 caller review | strategy/Backtest/walk-forward/optimizer/Qt focused suite **100 passed、1 個既有 warning、22.27 秒**；對 app/backtest/decision/ui/scripts 執行 source `rg`，確認無剩餘舊 app strategy import caller；root gate 為 `ACCEPTED_SCOPE` |
| `git diff --check` | 無 whitespace/error 診斷；共享工作樹有 Git LF/CRLF normalization warnings，不是 diff-check failure |

Focused pytest 完整命令（Windows PowerShell；fresh TEMP profile）：

```powershell
$run = Join-Path $env:TEMP ('r025_final_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $run 'data'
$env:OUTPUT_ROOT = Join-Path $run 'output'
& .\.venv\Scripts\python.exe scripts\check_look_ahead_bias.py
& .\.venv\Scripts\python.exe -m pytest tests\test_decision_strategy_owner.py tests\test_ui_qt_strategy_list_contract.py tests\test_strategy_threshold_modes.py tests\test_strategy_params_persistence_roundtrip.py tests\test_backtest_diagnostics_and_date_adjustment.py tests\test_backtest\test_parallel_safety.py tests\test_backtest_factor_metadata.py tests\test_batch_backtest_research_run_save.py tests\test_walkforward_service.py tests\test_optimizer_service.py tests\test_ui_qt_research_run_save.py tests\test_ui_qt_research_workflow.py tests\test_ui_qt_research_lab_mode_driven_ui.py -q -o addopts=
```

UI-specific required commands：

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts=
& .\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
& .\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
```

Update Tab validator 前兩次遇到 `TemporaryDirectory` 清理 `twstock.db` 的瞬時 `WinError 32`（25 passed／1 failed／4 skipped）；以 diagnostic rerun 檢查當時 Python/child `open_files()` 均無該 DB handle，隨後兩次 fresh TEMP 的 standalone run 都 exit 0、25/0/4。首次 WinError stack 指向 `scripts/qa_validate_update_tab.py:839` 的 temporary root cleanup，非 assertion；沒有刪除或保留任何正式資料。

Pycompile 使用單一 `-m py_compile` 對 44 個檔案執行；範圍涵蓋 `decision_module/strategies/*.py`、`decision_module/reason_tags.py`、app facades/callers、`ui_qt/main.py`/Backtest view、相關 QA scripts 及 strategy tests。

## 6. Acceptance 與暫時相容狀態（2026-09-23 R025 snapshot）

| R025 acceptance | 結果 |
|---|---|
| decision 是 strategy contract／唯一 registry／executor owner | 完成；app 舊路徑只有薄 re-export |
| 三個既有策略的 ID、metadata、輸出行為與順序 | AST 14/14、fixed/quantile、Backtest/walk-forward/optimizer、Qt list tests 通過 |
| 不留第二 registry、executor body 或 central if/elif dispatch | 通過；單一 registry import side-effect 與 alias identity 有測試 |
| serialized StrategySpec keys/defaults/params round-trip | 通過；沒有證據顯示 executor class path 為 persisted contract |
| caller 明確切換或有具名 TMP | 通過；全部已知直接 caller切換；剩餘舊 app source paths 登錄 `TMP-STR-01` |
| dependency guard 不出現 decision→app strategy edge | 通過；新測試掃描 decision strategies/reason tags，零逆向 import |
| focus、UI forced QA、compile、mypy | R025 focused/UI/compile 通過；R025 snapshot 與 root 最新共享工作樹 broad mypy 均為 693 files / 0 issues。並行編輯時曾觀察到的 R018 新檔單一錯誤已不再是目前 gate blocker |

`TMP-STR-01` 現況為 **ACTIVE**：app compatibility facade 仍提供舊 import paths。R029 退出前須完成 direct/dynamic/importlib/string/external caller 清查、source support window 結束證據及逐 alias 移除；若持久化 artifact 依賴其中任何 class path，需先拆成永久 alias 並測 exact deserialize。R025 不宣稱此臨時 facade 已退休或存在永久 executor path alias。

## 7. Residual、rollback 與接手界線（2026-09-23 R025 snapshot）

- Existing strategy preprocessing 的 `bfill()` 與舊 executor 的浮點 normalize 未改；靜態 guard 不是完整 causal/PIT proof，公式或精度變更應另開 task。
- `ReasonTagGenerator.analyze_tag_statistics()` 是未呼叫的 legacy float analytics helper；若它將來進入核心績效路徑，需單獨評估 Decimal/bp，不應藉 R025 靜默擴大公式範圍。
- `TMP-STR-01` 留到 R029；repo inventory 未證明 serialized executor class alias，外部 caller 完整性仍待 R029 查核。
- R025 驗證 snapshot 的 broad mypy 為 693 files / 0 issues；並行編輯時曾短暫觀察到 R018 新檔 1 個 mypy error。root 最新共享工作樹 broad gate 已通過 693 files / 0 issues，沒有待處理的 R025 mypy blocker。
- rollback 時只能針對本報告列出的 R025 hunks 反向修正：恢復原 app owner、舊 caller imports/UI access，並移除 decision owner 與 R025 tests/docs/ledger row；不可留下兩份 registry/body，也不可 reset 整個共享 working tree。`app_module/recommendation_service.py` 僅回復 R025 的 import hunk，保留 R018 其他變更；`app_module/update_service.py` 與 R023/R024/R018 檔案不在 R025 rollback 範圍。

root 已將 R025 scope 判為 **`ACCEPTED_SCOPE`**，依據本報告 QA、獨立 100 passed 重跑與 caller import review。這只驗收 R025 strategy owner／registry／signal／Backtest／UI 範圍，不代表整個 Wave7 或 refactor wave 完成；`TMP-STR-01` 仍 ACTIVE，R029 retirement evidence 尚待完成。
