# Recommendation Learning Runtime Wiring QA — 2026-09-15

## 範圍

本輪只驗證 Shadow daily recommendation learning 的 canonical ML runner、training lineage、cost-lane guard 與 ML→app 邊界 wiring。未執行正式資料根目錄、正式排程或 root/scheduled execution。

## 已完成

- 移除 `app_module/daily_recommendation_learning_runner.py` 舊實作；scheduled entrypoint、既有 runner 測試與 BankTaiwan 相容測試改用 `ml_module.recommendation_calibration_learning_runner`。
- `ml_module/recommendation_calibration_learning_runner.py` 直接產生 candidate、run receipt 與 immutable training lineage；fresh candidate 標為 `verified`，缺 lineage 的 frozen legacy candidate 明確標為 `legacy_unproven`，宣告但讀回失敗則 `failed_lineage`／`invalid` 並 fail closed。
- `ml_module/recommendation_training_lineage.py` 驗證 merged sample dataset hash、source group／dedup row identity、replay manifest、PIT cutoff、walk-forward fold／OOF 與 cost scenario；immutable manifest 使用 fsync 後 create-only hard-link 發布，競態寫入只接受 byte-equivalent readback。
- `ml_module/recommendation_calibration_evidence.py` 不再 import `app_module`；以 neutral `FrozenRecommendationInference` protocol 注入 champion inference，scheduled path 明確建立真實 `RecommendationCalibrationConsumer`。
- legacy fixed decision receipt／rule-only pointer 不再直接 `continue`；孤立或跨 lane marker fail closed，只有存在可驗證的同 lane receipt anchor 才能相容讀取。frozen receipt 的 current dataset 與 candidate dataset 分開驗證。

## 驗證證據

以下是本輪實際執行的命令、結果、exit code 與可重查輸出位置。所有 pytest XML
都寫在本機暫存 QA 目錄，未納入正式資料根目錄或排程 output。

| 實際命令 | stdout 結果 | exit code | 輸出位置 |
|---|---|---:|---|
| `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_training_lineage.py tests/test_recommendation_calibration_learning_runner_lineage.py -q -o addopts= --junitxml=qa-cache-o6do1nt5\recommendation_learning_runtime\lineage_runner.xml` | `9 passed, 1 warning in 0.67s` | 0 | `qa-cache-o6do1nt5\recommendation_learning_runtime\lineage_runner.xml`；pytest stdout 為本輪 Codex terminal output |
| `.\.venv\Scripts\python.exe -m pytest tests/test_daily_banktaiwan_learning_cost.py tests/test_daily_recommendation_learning_loop.py -q -o addopts= --junitxml=qa-cache-o6do1nt5\recommendation_learning_runtime\daily_loop_banktaiwan.xml` | `40 passed, 1 warning in 37.66s` | 0 | `qa-cache-o6do1nt5\recommendation_learning_runtime\daily_loop_banktaiwan.xml`；pytest stdout 為本輪 Codex terminal output |
| `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_calibration.py tests/test_recommendation_calibration_contract_guards.py tests/test_recommendation_calibration_source_contract.py tests/test_recommendation_service_calibration_integration.py -q -o addopts= --junitxml=qa-cache-o6do1nt5\recommendation_learning_runtime\calibration_boundary.xml` | `27 passed, 1 warning in 2.78s` | 0 | `qa-cache-o6do1nt5\recommendation_learning_runtime\calibration_boundary.xml`；pytest stdout 為本輪 Codex terminal output |
| `.\.venv\Scripts\python.exe -m mypy ml_module\recommendation_training_lineage.py ml_module\recommendation_calibration_learning_runner.py ml_module\recommendation_calibration_inference_contract.py ml_module\recommendation_calibration_evidence.py ml_module\recommendation_calibration_authority.py ml_module\recommendation_calibration_training.py ml_module\recommendation_cost_scenario.py ml_module\recommendation_natural_outcome_service.py ml_module\recommendation_probability_transform.py app_module\recommendation_calibration_consumer.py app_module\recommendation_learning_evidence_projection_service.py app_module\recommendation_replay_service.py scripts\scheduled\run_daily_recommendation_learning.py` | `Success: no issues found in 13 source files` | 0 | Codex terminal stdout；未寫入正式 output |
| `.\.venv\Scripts\python.exe -m mypy ml_module\shadow_boundary_guard.py scripts\check_ml_shadow_boundary.py` | `Success: no issues found in 2 source files` | 0 | Codex terminal stdout；未寫入正式 output |
| `.\.venv\Scripts\python.exe -m py_compile ml_module\recommendation_training_lineage.py ml_module\recommendation_calibration_learning_runner.py ml_module\recommendation_calibration_inference_contract.py ml_module\recommendation_calibration_evidence.py ml_module\recommendation_calibration_authority.py app_module\recommendation_calibration_consumer.py scripts\scheduled\run_daily_recommendation_learning.py tests\test_recommendation_training_lineage.py tests\test_recommendation_calibration_learning_runner_lineage.py tests\test_daily_recommendation_learning_loop.py` | 無 stdout／syntax error | 0 | Codex terminal stdout；Python 產生的 `__pycache__` 為本機暫存 |
| `.\.venv\Scripts\python.exe scripts\check_ml_shadow_boundary.py` | `{"inspected_files": 508, "shadow_only": true, "violations": []}` | 0 | Codex terminal stdout；未寫入正式 output |
| `.\.venv\Scripts\python.exe -m pytest tests/test_ml_shadow_dependency_boundary.py tests/test_ml_shadow_boundary_cli.py -q -o addopts= --junitxml=qa-cache-o6do1nt5\recommendation_learning_runtime\shadow_boundary.xml` | `12 passed, 1 warning in 5.11s` | 0 | `qa-cache-o6do1nt5\recommendation_learning_runtime\shadow_boundary.xml`；pytest stdout 為本輪 Codex terminal output |
| `.\.venv\Scripts\python.exe scripts\audit_test_inventory.py --skip-pytest-collection --output-json qa-cache-o6do1nt5\recommendation_learning_runtime\test_inventory_audit.json` | `filesystem=836、registry=833、missing=3、documentation_count_drift={}、collection_errors=[]` | 1 | `qa-cache-o6do1nt5\recommendation_learning_runtime\test_inventory_audit.json`；3 個 missing 為 foreign/L pending |
| `.\.venv\Scripts\python.exe scripts\audit_test_inventory.py --output-json qa-cache-o6do1nt5\recommendation_learning_runtime\test_inventory_audit_full.json` | `filesystem=836、registry=833、collected=5502、missing=3、stale=0、count drift=0、collection_errors=[]` | 1 | `qa-cache-o6do1nt5\recommendation_learning_runtime\test_inventory_audit_full.json`；exit 1 僅因 3 個 foreign missing |
| `.\.venv\Scripts\python.exe -m pytest tests\test_audit_test_inventory.py -k "read_documented_current_counts or governance" -q -o addopts= --junitxml=qa-cache-o6do1nt5\recommendation_learning_runtime\inventory_parser.xml` | `4 passed, 2 deselected, 1 warning in 0.19s` | 0 | `qa-cache-o6do1nt5\recommendation_learning_runtime\inventory_parser.xml`；pytest stdout 為本輪 Codex terminal output |
| `.\.venv\Scripts\python.exe -m mypy ml_module\shadow_boundary_guard.py scripts\check_ml_shadow_boundary.py tests\test_ml_shadow_dependency_boundary.py tests\test_recommendation_service_calibration_integration.py` | `Found 31 errors in 2 files` | 1 | Codex terminal stdout；額外把 tests 納入 mypy 的限制性嘗試，本輪未處理 |
| `git diff --check` | 無 whitespace error；Git 僅列出既有 LF→CRLF warning | 0 | Codex terminal stdout |
| `rg -n -S "app_module\.daily_recommendation_learning_runner" .` | 無 matches（rg 的 no-match 慣例碼） | 1 | Codex terminal stdout |
| `rg -n -S "from app_module|import app_module" ml_module\recommendation_calibration_learning_runner.py ml_module\recommendation_training_lineage.py ml_module\recommendation_calibration_inference_contract.py ml_module\recommendation_calibration_evidence.py` | 無 matches（rg 的 no-match 慣例碼） | 1 | Codex terminal stdout |
| `rg -n -S "from ml_module\.(recommendation_calibration_authority|recommendation_cost_scenario|recommendation_natural_outcome_service|recommendation_calibration_evidence) import \*|import ml_module\.(recommendation_calibration_authority|recommendation_cost_scenario|recommendation_natural_outcome_service|recommendation_calibration_evidence)" app_module ml_module scripts/scheduled` | 無 matches（未發現 wildcard／整個 ML namespace import） | 1 | Codex terminal stdout |

本次只完成 canonical runner、immutable training lineage、cutoff semantics、ML boundary
與 consumer fail-closed wiring 的 bounded 驗收；P1 的 candidate→next-day inference／
projection provenance（隔日 feature snapshot、source custody 與 readback loop）尚未完成，
本輪不宣稱已接通或已驗收。實際 shadow boundary guard 的 remaining violations 為 0。
consumer integration 也
覆蓋同一合法 candidate 先成功載入、再被篡改為 future historical-research context
後回到 `rule_only` 的負例。pytest 的 4 組執行各產生同一個既有 `.pytest_cache`
permission warning；不影響
exit code 0。daily loop 的 runtime 測試也確認 future `training_as_of` 只有在明確
historical-research 語義下建立，且 authority 以
`candidate_training_as_of_after_decision_fail_closed` 阻止其成為早期 decision-time
candidate。未以正式資料根目錄或正式排程執行。

## 未執行／後續交接

- 尚未執行正式 root/scheduled command，符合本輪限制。
- 未 stage、commit 或 push；shared worktree 仍含其他 agent 的既有 dirty changes，交接時不得一併納入。
