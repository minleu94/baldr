# V4.1 A 線第二輪歷史研究與候選方法包 QA

**日期**：2026-09-12  
**範圍**：baseline `a657ed9d` 上的 research-only historical dataset／method packaging  
**結論**：工程契約完成；正式自然 forward evidence 仍 `waiting_for_natural_maturity`，不得宣稱策略有效／失效、不得 promotion。

## 1. 交付內容

- `app_module/v41_historical_method_pack.py`：逐列、逐 horizon manifest、candidate coverage／gap classification、自然時間狀態與 frozen artifact builder。
- `scripts/build_v41_historical_method_pack.py`：正式 SQLite query-only 或 deterministic sample CLI。
- `app_module/recommendation_calibration.py`：保留既有 calibration contract，補上 discrimination（整數 bp AUC）、coverage、turnover 與 uncertainty 欄位，並保存逐 fold OOS predictions。
- `tests/test_v41_historical_method_pack.py`：row-level identity、available-at fail-closed、missing outcome、create-only writer 與 metrics contract。

輸出固定為三個 create-only 檔案：`historical_dataset_manifest.json`、`historical_calibration_report.json`、`frozen_candidate_artifact.json`。輸出只能放在 `DATA_ROOT` 外的明確 research output directory；本輪 ignored output 不列入 Git。

## 2. Dataset manifest contract

每一個 event × horizon row 保留：

- `decision_date`、`event_date`、`available_at`／precision、`as_of_date`、`label_end_date`、`label_maturity`、剩餘成熟天數；
- `strategy_version_id`、`strategy_config_id`／hash／schema、profile；
- `universe_policy_id`／hash、`universe_snapshot_id`／hash／status；
- `return_basis`、benchmark id／return／excess、fixed round-trip cost、observed liquidity cost、forward return；
- event／outcome／source row hash、source file hash、data quality、row status、`eligible_for_calibration`；
- `candidate_features` 與可機器判讀的 `gap_codes`。

缺 outcome 標為 `missing_outcome`；尚未跨過自然成熟窗口的 outcome 標為 `insufficient_future_data`。缺件不會被補成 0、current snapshot 不會被當成 PIT membership、replay／sample 不會取得 natural forward evidence credit。

### Look-ahead self-audit

1. 事件的 `decision_date` 是唯一決策切點；`event_date`、`as_of_date`、`available_date` 與 metadata `available_at` 晚於切點時 fail-closed。
2. `price_volume_v1` 僅接受事件當下保存的 indicator／volume component 與可得時間；歷史缺件不回填。
3. `chip_funding_v1`、`industry_relative_v1` 必須同時具備 decision-time feature、可得時間、source hash（及產業 benchmark identity）。
4. `pit_theme_v1` 必須具備 PIT membership id、membership as-of、available-at、source hash 與 concept label，且均不晚於決策日；current snapshot 不可替代。
5. 既有 evaluator 的 train／calibration／untouched-test split、label maturity purge 與 test 不回流 fit 規則保持不變。

金融數值維持整數 bp／count；本輪沒有新增核心裸 `float` 計算。

## 3. 正式 evidence DB read-only run

執行命令：

```powershell
& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' `
  scripts\build_v41_historical_method_pack.py `
  --db-path 'D:\Min\Python\Project\FA_Data\sqlite\twstock.db' `
  --output-dir 'output\v41_historical_method_pack_20260912_formal_r2' `
  --format json
```

來源：`D:\Min\Python\Project\FA_Data\sqlite\twstock.db`；repository 以 `mode=ro` 讀取，source tables 為 `evidence_events`／`evidence_outcomes`。DB 執行前後皆為 3,554,447,360 bytes、mtime `2026-09-11 12:40:03 UTC`，未發生 writer／schema 變更。

| 項目 | 正式結果 |
|---|---:|
| `recommendation_included` events | 221 |
| Evidence outcomes | 24 |
| manifest rows（221 × 20／5d） | 442 |
| mature observations | 0 |
| walk-forward folds | 0 |
| calibration status | `not_evaluable` |
| row status | `not_matured=442` |
| label maturity | `missing_outcome=430`、`insufficient_future_data=12` |
| natural-time status | `waiting_for_natural_maturity` |

正式 source file hash：`sha256:16b7a0347706c37bf18611d05355af6f6edf98dd7c676107717325eff7fc3cc1`。

### Candidate coverage

| 方法 | ready rows | blocked rows | 判讀 |
|---|---:|---:|---|
| `current_score_v1` | 442 | 0 | 現行 baseline，可作 research reference |
| `price_volume_v1` | 8 | 434 | 只有少數新事件具備兩個決策時 component |
| `chip_funding_v1` | 0 | 442 | 缺決策時 chip／funding feature |
| `industry_relative_v1` | 0 | 442 | 缺決策時 industry feature／benchmark identity |
| `pit_theme_v1` | 0 | 442 | 缺 PIT theme label／membership／source lineage |

主要正式 gap counts：`outcome_missing=430`、`label_waiting_for_future_data=12`、`benchmark_id_missing=430`、`cost_model_id_missing=430`、`strategy_config_id_missing=430`、`strategy_version_id_missing=430`、`universe_policy_id_missing=430`；另外 442 rows 均揭露 chip／funding／industry／PIT theme 的候選缺口，price／volume component 缺口為 434 rows。這些是資料品質與 lineage 結果，不是清理或回填指令。

## 4. Method evaluation 與 pre-fix decision

報告固定輸出 baseline／raw／calibrated 三層，以及 20d primary、5d auxiliary、upside／after-cost-profit target 的 calibration、Brier、ECE、probability bins、整數 bp discrimination、forward／benchmark excess、成本後 return／excess、turnover、coverage 與 uncertainty。正式 run 因成熟 observations=0，這些統計為 `not_evaluable`／null；不能用 null 反推策略表現。

Deterministic sample 只用來驗證完整計算路徑：1,134 mature observations、3 folds；20d calibrated current 與 price／volume 的 Brier=720 bp、ECE=729 bp、AUC=9,479 bp、成本後平均 return=-80 bp、benchmark excess=-22 bp、成本後 excess=-67 bp、coverage=10,000 bp、turnover=3,714 bp；5d auxiliary current 為 Brier=725 bp、ECE=644 bp、AUC=9,573 bp、成本後平均 return=17 bp、benchmark excess=55 bp、成本後 excess=10 bp、coverage=10,000 bp、turnover=3,611 bp。這些數字是 deterministic fixture 的工程 smoke，不是正式市場證據。

事前固定規則：

1. 只有相同 primary horizon、相同 expanding split、兩方法均有成熟 calibrated untouched OOS 且達 minimum test sample，才可比較。
2. price／volume、chip／funding、industry、PIT theme 任何單一 metric 改善都不自動 promotion；先保留 current，再交 B 線 shadow review。
3. 無 matched OOS improvement、樣本不足、source／available-at／PIT／label identity 不完整時，`selected_method_for_shadow=current_score_v1`。
4. 不降低 Gate、不偽造 probability、不改 formal recommendation／threshold／alpha，不寫正式 SQLite。

本輪 decision：`retain_current_method_insufficient_matched_oos`。這是研究選擇，不是正式策略升級或失效判定。

## 5. Frozen candidate artifact / B shadow handoff

formal ignored output：`output\v41_historical_method_pack_20260912_formal_r2\`。

- manifest hash：`sha256:2faeb2f299c355aa42aefca9bbe42d9575c25e79b3338d350ecf80b1150bd0e4`。
- calibration report hash：`sha256:6a2f043daa795f25238f16ad1d77c77a6004da42f559856dd2d1a050f57bf124`。
- frozen artifact hash：`sha256:f2edffec74e7ebc3a5f58b409086a8852ebb86433256411197af8d9d35e3339a`。

artifact 固定：`frozen=true`、`shadow_only=true`、`read_only_source=true`、`production_eligible=false`、`promotion_eligible=false`、`formal_oos=false`、`scheduler_enabled=false`、`recommendation_weights_changed=false`、`natural_forward_evidence_credit=false`。B shadow 消費前必須核對 manifest hash 與 source file hash，且只可唯讀 replay；不得寫 formal SQLite、變更正式 recommendation 或自行 promotion。artifact 為 create-only，既有同名檔案會拒絕覆寫。

## 6. 驗證與已知限制

通過：

```powershell
& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' `
  -m pytest tests\test_v41_historical_method_pack.py `
  tests\test_recommendation_calibration.py `
  tests\test_recommendation_calibration_cli.py `
  tests\test_recommendation_evidence_importer.py -q -o addopts=

& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' `
  -m py_compile app_module\recommendation_calibration.py `
  app_module\v41_historical_method_pack.py `
  scripts\build_v41_historical_method_pack.py

& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' `
  -m mypy app_module\recommendation_calibration.py `
  app_module\v41_historical_method_pack.py `
  scripts\build_v41_historical_method_pack.py

& 'C:\Projects\PythonProjects\technical_analysis\.venv\Scripts\python.exe' `
  scripts\quant_guard_linter.py
```

結果：focused pytest `16 passed`；py_compile 通過；mypy `Success: no issues found in 3 source files`；quant guard 的 financial float boundary 與 look-ahead bias checks 均通過。

`scripts/audit_test_inventory.py` 的結果仍為既有 repository healthcheck drift：本輪新測試已登錄；未登錄的是既有 `tests/test_decision_presentation.py`、`tests/test_recommendation_calibration.py`、`tests/test_recommendation_calibration_cli.py`，另有既有 stale `tests/test_promotion_authority_secret_store.py`、8 個 collection errors（共同根因為缺少 `runtime.promotion_authority_secret_store`）與既有 markdown link errors。這些與本輪 method pack 無關，未以放寬 Gate 的方式修補。

尚未完成的是自然時間：formal DB 必須在後續真實 outcome 成熟、source／strategy／universe／benchmark／cost lineage 齊備後，重跑同一 contract；不得用 sample、replay 或人工補欄位折抵。B 線接手時應先驗證上述 hash、確認 output 不在 `DATA_ROOT`，再做 read-only shadow／人工 review；本輪沒有 formal recommendation、score、threshold、scheduler 或 production artifact 變更。
