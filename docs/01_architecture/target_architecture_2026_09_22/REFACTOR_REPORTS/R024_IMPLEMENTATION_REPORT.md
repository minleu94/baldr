# R024 實作報告：statement／valuation contracts 與 factor reverse edges

## 結果與狀態

`GATE_STATUS: ACCEPTED_SCOPE`（2026-09-23）

R024 已把季度財報與估值來源記錄、可得性 facts、source diagnostics 留在 `data_module`；statement mapping、factor quality、估值百分位／缺值／正值政策移到 `decision_module.factors`。statement/valuation 的 SQLite schema、CLI v1 欄位、PIT cutoff、既有診斷文字及品質 wire literal 維持原樣。Root 已完成獨立 scope gate 並接受此 bounded engineering scope；不代表 Wave 7 或 Wave 9 已釋出。

### 2026-09-27 current implementation correction

Root 對最後 5-path diff 作獨立 review，並以 9-suite route 驗證 **67P/0F/0S**；五個凍結 source hashes 均相符。`data_module` 的 literal `decision_module` imports 已在限定的 `*.py` 搜尋中降至 0（FactorQuality 剩餘字串是 docstring，非 import）。此結果支持 R024 的 reverse-edge bounded scope，不代表 domain-wide I/O 已抽離：`IndustryMapper` 仍從 `config.meta_data_dir/companies.csv` 載入公司，industry index 保留 DB/SQLite/CSV fallback，而 recommendation composition 尚未注入 company records。此 follow-up 歸 R021/domain I/O scope，不改原 `FactorDiagnostic` classpath、FactorService 或 R024 acceptance 範圍。

### Gate readback（2026-09-23）

- Root 以 fresh TEMP、`PROFILE=test` 獨立重跑完整 20-module R024 route，`107 passed`；並檢視本報告及涵蓋任意 `decision_module` import（含 function-local import）的擴充 AST guard，裁決 R024 `ACCEPTED_SCOPE`。
- R023 曾因六項 statement `.quality` 回歸重開；本次 R024 修復已由 R023 regression route `152 passed` 及上述 root 獨立 R024 `107 passed` 覆蓋，root 同步恢復 R023 `ACCEPTED_SCOPE`。六項原始 node IDs 未留存，修復與 parity 證據見下方 R023 regression checkpoint。
- 此為 R023/R024 各自的 bounded scope acceptance；C1/Wave 6 未通過，因此不改變 Wave 7–14 的 release/block 狀態，也不授予正式資料接受、ML promotion 或 production deployment。

## 任務與工作樹基線

- Task：R024，依賴 R023。
- Implementer：GPT-6 Luna Max 既有 subagent。
- 起始／結束 HEAD：`e16f92928980a025d24bd5b023eeadf9d6a31daa`；本任務未 stage 或 commit。
- 起始工作樹已包含 R001–R027 多項未提交修改，並由 root 指示保留；本次只改 R024 所需路徑，沒有清理或覆寫其他 agent 的變更。
- 已讀 authority：repo `AGENTS.md` 強制清單、`docs/agents/README.md`、`shared_context.md`、`git_exclusions.md`、`execution_agent.md`、`testing_qa_agent.md`、R024 task、`FINAL_TARGET_ARCHITECTURE.md`、`FINAL_ARCHITECTURE_INVARIANTS.md`；依賴 R023 的現有 pure fundamental contracts 與其 QA 報告。
- `shared_state/active_task.yaml` 屬較早的 handoff，依 root 指示未讀改或同步。

## 變更與 caller 接線

### Data contracts 與 statement

- `data_module/contracts/statement.py` 新增 `StatementAvailabilityOverride`、`StatementItemRecord`。兩者只保存日期、來源版本、公告／可得日期、report basis、來源 row code、lineage、XBRL、unit／scale 等 facts；不帶 `FactorQuality` 或 semantic mapping policy。`StatementItemRecord` 可保留舊 SQLite `quality` literal，但不解讀它。
- `fundamental_statement_data.py`、`fundamental_statement_availability_sources.py`、`fundamental_statement_availability_entrypoint.py` 改回傳 pure `SourceDiagnostic`，不建立 factor DTO。原 code、message、產生順序保持；shared availability 診斷由 decision adapter 投影回舊 factor name。
- `statement_semantic_mapping.py` 移至 `decision_module/factors/statement_semantic_mapping.py`，演算法、官方 row code／名稱／XBRL／版本限制、診斷排序、duplicate fail-closed 規則未改。semantic record 保留 `value_unit`、`value_scale` 與原始 row lineage。
- `statement_factor_adapters.py` 新增 record／availability quality 投影。SQLite 舊 literal 六值均按 `FactorQuality` 原樣解讀；無舊 literal 的新 raw statement record 沿用舊 resolver 規則：有公告日為 `observed`，無公告日但有 explicit available date 為 `degraded`。combined factor quality 對 `missing`／`degraded` 的既有優先規則不變。
- `fundamental_statement_backfill.py` 不再計算或保留 factor `quality_counts`。writer 接收 decision 邊界傳入的 `quality_projector`，並以純 wire parser 驗證寫入值；statement CLI 由 adapter 投影品質統計，因此 markdown 欄位、排序及字串格式不變。availability／statement source diagnostics 仍依原順序列印 code/message。
- `fundamental_sqlite_provider.py` statement reader 只解析並保留 `legacy_quality_wire_value`；原 `available_date <= decision_date` SQL cutoff、公告日 firewall 與 rows 排序不變。

### Valuation 與應用邊界

- `data_module/contracts/valuation.py` 新增 `ValuationMetricRecord` 與 `ValuationBackfillSourceRow`；`valuation_data.py` 只把儲存列解析為 Decimal、日期、百分位與 raw quality wire，不產生 `FactorDiagnostic`／`FactorQuality`。
- `calculate_industry_percentiles_bp` 搬到 `decision_module/factors/valuation_policy.py`，整數 bp 算式、同產業 universe、`(metric_value, stock_code)` 排序、單筆樣本回傳 `None` 均未改。valuation band 的 0–2000／2001–8000／8001–10000 邊界及 missing／invalid 診斷未改。
- `valuation_source_policy.py` 搬至 `decision_module/factors/valuation_source_policy.py`。PB／PS external-source required 診斷、ready metrics 與不連 ScoringEngine 的 wire 保持原值。
- `valuation_metrics_backfill.py` 只負責 daily P/E 的日期解析、Decimal source rows、companies.csv 載入及 SQLite writer。正值、缺 industry、百分位與品質政策由 `valuation_backfill_adapters.py` 解讀；原診斷順序仍按來源股票列逐筆建立。writer 驗證 raw quality wire 後寫入既有欄位。
- `scripts/backfill_valuation_metrics.py`、`scripts/inspect_valuation_source_policy.py` 已改接 decision policy；valuation CLI markdown／診斷輸出欄位與文字未變。未確認 `--apply` 先檢查 confirm，避免無確認時讀取 daily_prices。
- `app_module/fundamental_factor_service.py` 在 application boundary 把 valuation `SourceDiagnostic` 投影成舊 `FactorDiagnostic`，並將 pure valuation source records 交給 decision adapter。沒有修改 `app_module/update_service.py`。

### 新增／更新的驗證

- 新增 `tests/test_r024_fundamental_contract_characterization.py`，固定 statement aliases、診斷順序、unit／scale、整數 bp 百分位、valuation band 與 missing policy。
- 新增 `tests/test_r024_fundamental_dependency_guard.py`，用 AST walk 檢查 statement／availability／backfill／valuation／SQLite source paths 沒有任何 `decision_module` import，也涵蓋 function-local import。
- 更新 `tests/test_r023_fundamental_dependency_guard.py`：保留 R023 monthly path 的禁止依賴檢查，確認 statement data／backfill 不依賴 decision，SQLite 只驗證舊 literal，`FactorQuality` 只在 decision adapter 解讀。
- 更新 statement／valuation data、adapter、backfill、CLI 與 SQLite provider tests，舊 `.quality` 行為由 decision adapter/output 層驗證，而非刪掉品質斷言。

## 相容性、PIT 與 look-ahead 自查

- **六種舊 quality literal：** `observed`、`estimated`、`degraded`、`missing`、`neutral`、`stale` 由 `parse_legacy_quality_wire_value` 僅作 wire 驗證。statement 與 valuation SQLite provider 各有六個參數案例，驗 raw record round-trip 和 decision adapter 對應的 `FactorQuality`；statement backfill 合成 DB 驗 `degraded` 寫回，valuation backfill 合成 DB逐欄驗讀回的日期、Decimal 字串、百分位與 quality。
- **SourceDiagnostic：** adapter 依 kind 投影 factor name，逐筆保留 code、message 與順序。statement semantic mapping diagnostics 順序為 mapping diagnostics 在前、duplicate diagnostics 後；相關 characterization test 鎖定此行為。
- **statement revisions：** availability override contract 保留 `source_version`、`source_hash`、`revision`、`parent_revision`、provenance mode。SQLite statement item 沒有 row-level revision identity，本次沒有補造 revision，也沒有改日期／版本連結方式。
- **截止日：** statement、valuation provider 仍先以 `available_date <= decision_date` 查詢，再由 firewall 檢查；statement 維持 `require_announced_date=False`。backfill P/E 仍只讀指定 `as_of_date` 的 daily_prices 列，寫入的 as-of／available date 仍等於該日。
- **數值與單位：** statement 金額及 valuation metric 維持 `Decimal`。百分位運算維持整數基點，沒有新增裸 float 算術。statement aliases、unit、scale、report basis 未改。
- **Persistence／wire：** 未改正式 schema、JSON/CSV/SQLite 欄位。statement／valuation v1 CLI 輸出經原 scripts 投影後維持欄位與格式。Direct Python imports 有意隨 owner 搬移：semantic mapper、valuation source policy、百分位與 valuation backfill policy 改由 `decision_module.factors` 匯入；repo 內所有 callers 已更新。statement backfill data writer 現需 caller 提供 `quality_projector`，避免 data 層重建 factor policy。
- **ML／策略：** 未改 ML feature eligibility、source hash、dataset、threshold、Direct15、strategy 或 scoring 連線；沒有執行 promotion、training 或 full ML。

## R023 regression 修復 checkpoint

R024 開始前 root 提供的 statement 回歸基線是 `78 passed, 6 failed`；六個失敗共通原因是 R023 statement data route 漏測，data／backfill 仍在讀已移除的 `.quality`。原 checkpoint 沒有保留可核對的六個 node IDs，本報告不臆測個別 ID。

修復不是加回 data `.quality` property：availability facts 留在 source record，quality 由 statement decision adapter 推回舊值；backfill CLI quality summary 在 decision/output boundary 計算；SQLite reader 原樣保留六種舊 literal，writer 由呼叫端提供舊 wire 值。修復後 statement/valuation 完整 route 107 passed，其中包括 statement data、availability、backfill dry-run／synthetic write-readback、CLI 與 factor pack。

## 驗證結果

pytest 兩條 final route 均使用新的 `%TEMP%` root、`PROFILE=test`、隔離的 `DATA_ROOT`／`OUTPUT_ROOT`，所有資料庫 apply/write 測試只操作 pytest temporary SQLite DB；未讀取、重抓或修改正式資料。

1. R023 monthly-revenue regression route（含更新後 R023/R024 dependency guard）：`152 passed`。
2. R024 statement／valuation route（20 個 test modules，含 12 個舊 literal parametrized cases 及 FundamentalFactorService integration）：`107 passed`。
3. Scoped mypy（21 個 R024 source／script files）：`Success: no issues found in 21 source files`。
4. Broad mypy：最後直接重跑 `python -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`，`Success: no issues found in 693 source files`。同一工作階段較早的一次 broad run 曾在 R018 concurrent file `app_module/recommendation/input_preparation.py:182` 出現一個型別錯；R018 owner 修正後，本次 final rerun 已乾淨，非 R024 defect。
5. 本次修改的 Python source、scripts、tests 通過 `python -B -m py_compile <changed Python files>`。
6. R024 tracked paths 的 `git diff --check` 通過。

R024 final pytest command：

```powershell
$qaRoot = Join-Path $env:TEMP ('r024-guard-final-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
$env:PROFILE = 'test'
.\.venv\Scripts\python.exe -B -m pytest tests\test_r024_fundamental_contract_characterization.py tests\test_r024_fundamental_dependency_guard.py tests\test_fundamental_statement_data.py tests\test_fundamental_statement_availability_sources.py tests\test_fundamental_statement_availability_entrypoint.py tests\test_fundamental_statement_backfill.py tests\test_fundamental_statement_backfill_cli.py tests\test_statement_availability_cli.py tests\test_statement_semantic_mapping.py tests\test_statement_factor_pack.py tests\test_valuation_data.py tests\test_valuation_policy.py tests\test_valuation_factor_adapters.py tests\test_valuation_source_policy.py tests\test_valuation_source_policy_cli.py tests\test_valuation_metrics_backfill.py tests\test_valuation_metrics_backfill_cli.py tests\test_fundamental_sqlite_provider.py tests\test_fundamental_factor_adapters.py tests\test_fundamental_factor_service.py -q -o addopts= -p no:cacheprovider
```

R023 regression command：

```powershell
$qaRoot = Join-Path $env:TEMP ('r023-final-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$env:DATA_ROOT = Join-Path $qaRoot 'data'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'output'
$env:PROFILE = 'test'
.\.venv\Scripts\python.exe -B -m pytest tests\test_fundamental_data.py tests\test_fundamental_availability.py tests\test_fundamental_availability_sources.py tests\test_fundamental_availability_entrypoint.py tests\test_fundamental_sqlite_provider.py tests\test_fundamental_factor_adapters.py tests\test_revenue_factor_pack.py tests\test_r023_fundamental_contract_characterization.py tests\test_r023_fundamental_dependency_guard.py tests\test_fundamental_statement_availability_sources.py tests\test_monthly_revenue_availability_history.py tests\test_monthly_revenue_availability_history_cli.py tests\test_monthly_revenue_availability_merge.py tests\test_monthly_revenue_backfill.py tests\test_monthly_revenue_recovery.py tests\test_monthly_revenue_snapshot_harvester.py tests\test_update_service_monthly_revenue_status.py -q -o addopts= -p no:cacheprovider
```

Broad mypy command：

```powershell
.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
```

未執行完整 repository pytest、R019 suite 或正式 apply；R024 focused route、R023 dependency route 與 broad type gate 覆蓋本任務 acceptance。QA root 位於 OS `%TEMP%` 下，未放入 repo；本環境拒絕對已核對的 temp root 執行 recursive removal，因此這些唯一命名的 QA roots 留在 OS temp。它們不是正式資料或 repo artifact。

## Residual edges、風險與回復點

- 全 repo `data_module` 搜尋 `decision_module.factors` 後，R024 statement／valuation data paths 已無 reverse imports。尚存兩個與本任務無關的 data → factor edges：`data_module/company_registry.py`、`data_module/tpex_daily_price_backfill.py`；R023 已列為後續相應 owner，R024 未擴 scope。
- Direct Python API import paths 有 owner migration；repo 內 callers 已切換。若有 repo 外部程式直接 import `data_module.statement_semantic_mapping`、`data_module.valuation_source_policy`、data 端百分位或舊 valuation planner，需改到 decision adapter。R024 沒新增反向相容 shim，避免重新建立 data → decision dependency。
- SQLite reader/writer 的現行 `quality` literals 以 synthetic DB 驗證；未對正式 DB 做讀寫，也未依正式資料判斷 alias 或 policy。
- 回復點是本次 scoped diff：statement／valuation contract 與 adapter、CLI caller、相關 tests。由於共享工作樹原本已有 R023/R001–R027 修改，不可整檔 checkout；回復應限於上述 R024 hunks／新增 R024 files。

## Acceptance criteria

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| data 提供純 statement／valuation source/availability records | PASS | contracts；R024 route 107 passed |
| statement／valuation factor quality、mapping、valuation policy 位於 decision | PASS | data AST guard、statement/valuation adapters |
| R024 data owners 無 `decision_module` reverse import | PASS | R024 guard 涵蓋 source、backfill、contracts、provider；全 repo 僅留上述兩個 out-of-scope edges |
| factor / CLI / SQLite behavior、diagnostics 與舊 quality literals parity | PASS | 107 passed；六種 quality 各自 SQLite raw-record／decision projection 案例及 write/readback |
| PIT cutoff、Decimal、statement unit/scale、percentile bp 不變 | PASS | characterization、provider cutoff 與 backfill readback tests |
| ML / formal persistence schema 不變 | PASS | 未改 ML/正式 schema；只用 TEMP synthetic DB |
| R019 只依 domain contracts 可接續 | PASS（結構） | source records 位於 `data_module.contracts`；未執行 R019 suite |
| Scoped + broad mypy、compile、diff check | PASS | 21 files；693 files；py_compile；selected `git diff --check` |
