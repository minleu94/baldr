# Personalization real-source fit runner QA（2026-09-17）

## 範圍與 ownership

本卡只記錄 C 線 `PersonalizationFitRunner` 的受控實作：既有
`PersonalizationReadService` 唯讀來源 → 既有 `PersonalizationCalibrationEvaluator`
fit/evaluate → hash-bound durable artifact → reader envelope。它不建立 scope、
prediction、action 或 outcome，也不改 global pointer、promotion、scheduler、broker
或正式資料。

## 實作合約

- `created_at` 預設只取 fit 程序執行當下的 aware UTC runtime clock。它不再從
  `evaluated_as_of` 或 label／outcome／receipt dependency 時鐘推導。
- durable artifact 的 request binding 包含 scope、fit/evaluation cutoff、result／stock、
  artifact identity、creation clock、shrinkage、embargo、bounded source limits 與
  research-only minimum gates。retry 只有在 source fingerprints、fit/evaluation row
  identity／fingerprint 與完整 request 相同時，才重用原 immutable artifact。
- final publication 使用同目錄 temporary file、file `fsync`、atomic create-only
  hard-link、final readback/hash 驗證；不使用會覆寫既有 final 的 `os.replace`。partial、
  tampered、non-canonical 或不同 request 的 final 都 fail closed。
- envelope 明確保存 `evaluation_temporal_semantics.mode=retrospective_offline`、
  `prospective=false`、`natural_forward_credit=false` 與 creation clock 相對
  evaluation cutoff 的診斷；後建 artifact 的歷史 evaluation 不可被讀成 prospective
  或 natural personalization 成效。
- min rows／distinct dates 只作 research fit 最小條件；既有 evaluator 的 cohort、
  label availability、lineage、scope、horizon、cost、exact identity、purge／embargo
  與 temporal checks 仍是 blocking contract。

## Caller 覆蓋與剩餘資料邊界

- `scripts\run_personalization_fit.py` 是本輪 fit producer CLI；
  `scripts\inspect_personalization_sources.py` 是既有 real-source consumer，會以
  verified envelope 重新核對 source／fit／evaluation binding。程式碼 inventory
  中沒有其他已授權的 fit artifact caller；`PersonalizationCalibrationEvaluator`
  仍是既有 engine，沒有另造 evaluator。
- 正式 real scope 必須由上游已持久化的 delivery scope、action、receipt 與
  Recommendation／Journal／Evidence identity 提供；C 只讀並 exact join，缺 scope、
  action 或 receipt 時 blocked，不代寫或偽造來源。
- 可宣稱 mature natural evidence 仍需獨立 OOS outcome、label 已成熟、跨足量日期、
  通過 purge／embargo 與既有 statistical gates。C 只保存 retrospective offline
  診斷與 evaluation，不建立 mature evidence、promotion 或 production pointer。

## 驗證命令與結果

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_personalization_fit_runner.py `
  tests\test_personalization_fit_cli.py `
  tests\test_personalization_calibration.py `
  tests\test_personalization_read_service.py -q -o addopts=
```

結果：`41 passed`。新增 runner 測試涵蓋 runtime creation clock、retrospective
metadata、immutable retry、explicit clock／request／source conflict、scope／label
cutoff、lineage、purge／embargo、tampered／截斷 final、fsync 中斷無
final／temporary、research minimum blocked、reader scope／canonical readback；
CLI 測試確認 missing real source 時 exit `2`、不建立 artifact。real-source 測試
使用既有 RecommendationSaveRequest、Journal ACK/action 與 Evidence outcome，
經 `PersonalizationReadService`→fit CLI 建立 envelope，再由既有
`inspect_personalization_sources` 讀回 verified envelope，確認 scope、source
consistency／completeness、fit row binding、evaluation 與 purge 後空 OOS cohort；
同時確認 bare legacy artifact 只標為 unverified，不會升格給 evaluator。
該整鏈 fixture 同時保留一列來源搭配 `min-fit-rows=1`／
`min-fit-decision-dates=1` 的接線與不足 OOS 示範，另以兩個不同日期的真實 fit
來源及一列獨立 OOS 來源通過預設 2 rows／2 dates gate；讀回確認 evaluation
非 `None`、exact fit／evaluation fingerprint、purge 後 fit overlap 排除與
retrospective 邊界。另驗證空 evaluation cohort 在 wrong scope CLI 仍 exit `2`
且不產生 verified binding；不宣稱有 natural/prospective personalization
成效。

```powershell
.\.venv\Scripts\python.exe -m mypy `
  ui_qt app_module data_module analysis_module backtest_module `
  decision_module portfolio_module runtime
```

結果：根目錄既有八個 module tree 的全域型態檢查完成，`Success: no issues
found in 630 source files`（另有兩則既有 untyped function note）。本輪 scripts
與 tests 不屬於該八個 module tree，另以完整 import traversal 檢查五個 C 檔案：

```powershell
.\.venv\Scripts\python.exe -m mypy `
  app_module\personalization_fit_runner.py `
  scripts\run_personalization_fit.py `
  scripts\inspect_personalization_sources.py `
  tests\test_personalization_fit_runner.py `
  tests\test_personalization_fit_cli.py --explicit-package-bases
```

結果：`Success: no issues found in 5 source files`。

```powershell
.\.venv\Scripts\python.exe -m py_compile `
  app_module\personalization_fit_runner.py `
  scripts\run_personalization_fit.py `
  scripts\inspect_personalization_sources.py
```

正式 D 資料未被寫入；本輪只使用隔離測試 root 與唯讀 read adapter，沒有執行正式
fit、資料重建、promotion 或 scheduler。

## CLI 入口

```powershell
.\.venv\Scripts\python.exe -m scripts.run_personalization_fit `
  --scope-id <explicit-scope> `
  --fit-as-of YYYY-MM-DD `
  --evaluated-as-of YYYY-MM-DD `
  --evaluation-cutoff-at <aware-iso-datetime> `
  --output-root <caller-owned-read-root> `
  --output-path <isolated-fit-artifact.json> `
  [--journal-path <journal.jsonl>] [--evidence-db <twstock.db>] `
  [--result-id <exact-result-id>] [--stock-code <exact-stock-code>]
```

CLI 沒有歷史 `--created-at` 參數；正常入口一律使用 runtime clock。測試如需固定
時間，只能在 runner 注入 clock，不能把歷史 availability 或 prospective 時鐘倒填成
artifact 建立時間。CLI exit `0` 僅表示 `created` 或 exact `idempotent_retry`；資料、
來源、合約或 artifact 任一檢查 blocked 時 exit `2` 且不產生 usable artifact。
