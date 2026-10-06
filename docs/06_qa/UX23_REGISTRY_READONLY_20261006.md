# UX23 registry 唯讀 reader 隔離驗收（2026-10-06）

本包基於 `96ebcb33177f75e3f64c92b60330347b5301331c`，branch 為 `ux23-registry-readonly`，專屬 worktree 為 `.tmp_ux23_registry_readonly`。唯一新增 reader、synthetic tests 與本 QA 文件；不修改 chart／CSV／Manual 等 shared 檔。沒有 UI 或 CLI 接線，也不推進 UX23／Stage7 的 partial 狀態。

## API 與資料來源

`app_module.model_registry_readonly.ModelRegistryReadonly(db_path).read(model_id, expected_metadata=候選完整pin, observed_at=aware ISO時間)` 接受明示絕對路徑，無預設 DB／DATA_ROOT／自動 discovery。

只讀既有 `ml_models(model_id, payload_json)` 與 `ml_model_lifecycle_events(event_id, model_id, event_type, created_at, payload_json)`。schema 必須與既有 initializer 的欄位型別、not-null、primary key 契約一致；缺表、舊 schema、view／額外欄位皆 fail closed。沒有新 registry、schema version、版本表或 migration。

回傳 `ModelRegistryReadonlyResult` 包含既有 `MLModelRecord`、`tuple[ModelLifecycleEvent, ...]`、既有 `rule-research-shadow-lifecycle-export.v1` envelope、來源 DB SHA256 與 `unverified_metadata_fields`。`current_status` 是已驗事件鏈的最後狀態；無事件仍為 None，record 仍為 shadow_candidate。`safety_flags` 永遠為研究用途，所有訓練／PIT／formal／natural／execution／shadow enabled 資格 false、alpha 0、qualified_count 0、selection unknown。

既有 DB 沒有獨立「model version」欄位；model_id、dataset_id、artifact_hash、created_at、family、feature_names、calibration_id 等完整 record metadata 必須與 candidate pin 一致，版本或任何 stored pin 不符均 `registry_version_mismatch`。artifact_path 僅是字串，不讀檔、不驗模型 artifact bytes、不執行 pickle/joblib／模型反序列化／predict／fit。

**lineage 限制：** dataset／feature／artifact／calibration metadata 可比對 registry；公平比較的 `training_audit`／`target_contract` 不在 DB。若 caller 提供，深複製保留在既有 envelope，並明列 `unverified_metadata_fields=(target_contract, training_audit)`；它們仍是 caller 聲明，不能宣稱 training lineage custody、官方資料完整性、模型效果或自然預測資格。來源 SHA256 只證明本次明示 DB bytes，沒有外部認證。

## 唯讀與缺件行為

SQLite 使用 percent-encoded file URI、`mode=ro`、`query_only=ON`、`trusted_schema=OFF`、timeout 0；authorizer 只允許固定 SELECT／table_info／唯讀 query_only inspection 與 deferred BEGIN。讀取 snapshot transaction 使用 SQLite 正常短暫共享讀鎖；不建立應用 lockfile、不取得 write reservation 或排程 lock。連線在成功或失敗都關閉。

在 connect 前檢查非 link／Windows reparse 路徑、32MiB DB 上限、SQLite header、WAL header，以及 `-wal`／`-shm`／`-journal` 殘件；WAL 或任何 sidecar 一律拒絕，避免唯讀 connect 生成 shm。這不是可直接讀 live WAL registry 的 adapter；需要 owner 明示提供已存在、無 sidecar 的一致 rollback-journal snapshot。本包不建立 snapshot、不切換 journal mode、不清理 sidecar。來源 bytes hash／size／mtime／inode 前後不一致即拒絕；此重驗不提供對惡意並行替換的 OS 級 custody 保證。

缺件以 `ModelRegistryReadError.reason_code` 回報，不回傳部分 DTO：`registry_missing`、`registry_schema_mismatch`、`registry_corrupt`／`registry_unreadable`、`registry_locked`、`registry_model_missing`、`registry_version_mismatch`、未知 model／event status、非法轉移／時間／identity、qualification rejection 與來源改變。future lifecycle 直接拒絕，沒有回填或過濾後宣稱歷史狀態。

每筆 JSON 上限 256KiB、事件上限 256、export 上限 64KiB；重複 JSON key、缺 record 欄位、payload／SQL identity 不同皆拒絕。record bool 精確比對，不接受以 0 代替 false。沒有策略／績效計算或新增 float；未來函數自查只涉及 observed_at 前可見 metadata／事件，不改既有 prediction、label、split 或 fit 邏輯。

## 驗證與證據

所有 DB 都由測試在 Temp 建立的 synthetic fixtures，重用既有 initializer／writer 契約；未讀真私資料。新 reader 47 案例，與既有 UX23 acceptance／safety／boundary／CLI 回歸共 74 案例。涵蓋缺庫／缺模型、corrupt DB／JSON、舊 schema／view／未來欄位、版本 pin 不符、未知狀態／非法事件鏈／未來時間、exclusive lock、WAL／各 sidecar、來源 bytes／mtime／目錄不變、來源重驗改變、容量拒絕、特殊 URI 檔名、連線關閉、禁止 UPDATE／ATTACH、live getter 不被呼叫、artifact 不讀取、四種 terminal status 與三軸資格不升級。

執行命令（worktree 內，使用原 checkout 的既有 venv）：

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_model_registry_readonly.py tests/test_rule_research_shadow_acceptance.py tests/test_rule_research_shadow_acceptance_safety.py tests/test_rule_research_shadow_acceptance_boundary.py tests/test_rule_research_shadow_acceptance_cli.py -q -o addopts= -p no:cacheprovider --junitxml=output/qa/ux23_registry_readonly_20261006/focused.xml
..\.venv\Scripts\python.exe -m mypy app_module/model_registry_readonly.py --follow-imports=silent
..\.venv\Scripts\python.exe -m py_compile app_module/model_registry_readonly.py tests/test_model_registry_readonly.py
git diff --check
```

targeted mypy：`Success: no issues found in 1 source file`；兩檔 py_compile exit 0。raw XML、mypy log、compile exit 與 validation receipt 位於專屬 worktree `output/qa/ux23_registry_readonly_20261006/`，不 stage。此處未宣稱全 repo mypy／ML boundary／Native／UI healthcheck 通過。

初版 fixture 不合法 Windows `?` 檔名已修正；後續 URI 特殊字元測試的 rename 因既有 writer 未立即關閉 handle 而失敗，改為將 synthetic DB bytes 寫入另一個 fixture 路徑，不修改既有 writer。最終 XML 以修正後重跑結果為準。

## 文件 coverage 與回滾

本包只有 leaf API，沒有使用者入口、操作或參數變更，遵照 lane scope 不修改 Manual／Snapshot／Architecture／路線 shared 文件；main owner 後續接線時須同步該入口的操作／限制。未授予真 adopt／rollback／disabled event／DB writes／Task／Native／migration／push；沒有 dev cherry-pick。

| 新增檔案 | 回滾方式 | 風險 |
|---|---|---|
| app_module/model_registry_readonly.py | 未提交時核對 ownership 後 `Remove-Item -LiteralPath app_module/model_registry_readonly.py` | 移除 reader API，需先確認 consumer 無依賴 |
| tests/test_model_registry_readonly.py | 未提交時核對 ownership 後 `Remove-Item -LiteralPath tests/test_model_registry_readonly.py` | 僅移除本包測試 |
| docs/06_qa/UX23_REGISTRY_READONLY_20261006.md | 未提交時核對 ownership 後 `Remove-Item -LiteralPath docs/06_qa/UX23_REGISTRY_READONLY_20261006.md` | 僅移除 QA 說明 |

回滾依序：先 `git status --short`／核對本包 diff 與 consumer 依賴，再逐檔操作、重跑相關 consumer tests。已提交版本交由整合 owner 選擇 `git revert <本包hash>`，不自行回退其他工作。原始資料從未變更。
