# 每日 Decision Evidence Capture 修復 QA（2026-09-18）

## 範圍與安全邊界

本輪只處理 `scripts/scheduled/run_scheduled_decision_evidence_capture.py` 的 parent／child temporal context 對齊、per-run durable receipt 與其專屬回歸測試。未執行正式 capture job、未重跑 2026-09-17、未寫入正式 D 槽或正式 SQLite，未調整 scheduler、門檻、promotion、broker、learning evaluator、personalization 或下游 maturity gate。

## 9/17 latest status 唯讀證據

正式輸出目錄 `D:\Min\Python\Project\FA_Data\output\scheduled\decision_evidence_capture` 只有 `latest_status.json`，沒有 immutable run／stdout／stderr／exitcode receipt。原檔 metadata 為：

- `decision_date=2026-09-17`、`captured_at=2026-09-17T20:25:02+08:00`。
- status file SHA256：`14D6ED929D9E9053DE0CFE77D339CECC79D493E0F6566CE1071E6FD8FE738174`。
- `snapshot.saved=true`、七個 required sections 齊全、`quality=degraded`。
- `snapshot.stderr` 只有 `data_module.config` 的路徑 INFO；failure list 沒有 `snapshot_cli_exit:<code>` 或 timeout。
- `failure_reasons` 僅有：`temporal_receipt_mismatch:capture_context_hash`、`temporal_receipt_mismatch:capture_context_identity_hash`。
- 因 wrapper fail-closed，`evidence.status=not_run`、`reason=snapshot_step_failed`。

唯讀以 `sqlite3` URI `mode=ro`、`PRAGMA query_only=ON` 查驗 snapshot row `dds_6e7bdc5316ffc90f`：`snapshot_hash=sha256:6e7bdc5316ffc90ff8a89373eee28a73050fef40ea64e5c41360cdf135f676b6`、`decision_date=2026-09-17`、`data_quality=degraded`，metadata 保存 child context hash `sha256:404d0c5a2303c3c12a856052702c2d8b354fda77c3b5563734178df5bc1bc806`。connection 已關閉；沒有修改 D 槽資料。

對該 metadata 的兩個 digest 以相同 canonical JSON 重新計算，`capture_context_valid=true`；因此可直接證明的失敗是 parent wrapper 與 child receipt 的兩個 hash 比對不一致，不是 child snapshot metadata 自身損壞。latest status 的 `decision_time=20:25:02.692021` 只保存顯示用時間欄位；原始 parent `decision_at` 的完整 precision 與 immutable receipt 沒有保存，不能由此重建當時完整 hash input。

沒有原始 child stdout／OS exitcode artifact，故本 QA 不臆測子程序退出細節。status failure list 未出現 wrapper 自己會產生的 `snapshot_cli_exit:<code>`，只支持「child JSON／保存結果已回讀，但 temporal receipt 驗證失敗」這個範圍。

## 根因

直接觀察到的根因訊號是 latest status 同時列出 parent `capture_context_hash=sha256:e77ce239c86f6f44f2392fd9dc30f693f9bc1dd31d39b3d22be373b7968e124f`／identity hash `sha256:d3a32e3f401a26d57817883507136462aaa7961ddd6a49afcc866eac8493243f`，以及 snapshot child persisted hash `sha256:404d0c5a2303c3c12a856052702c2d8b354fda77c3b5563734178df5bc1bc806`／identity hash `sha256:edc1809d8c4e583581af529256ae03088c36f6b7bf48788cf0b7a65d1c6f0f2a`；failure list 也正好是這兩項 mismatch。

可重現的 code defect 是：`f9a5b9e9` 後 wrapper 以 aware `datetime.now()` 的 microsecond precision 建立 `EvidenceCaptureRequest`，但 `_base_payload()` 與 child `common_args` 以 `timespec="seconds"` 序列化 `decision_at`／`captured_at`。child 以秒精度重建 request 時，語義欄位看似相同，canonical hash bytes 卻不同。隔離回歸測試以 `.123456` timestamp 重現此邊界；因此修補改為 parent payload 與 child args 都使用同一個完整 `datetime.isoformat()`。由於 9/17 immutable artifact 沒有保存原始 parent context 的完整 bytes，這是可重現的 precision 缺陷與實際 hash mismatch 的因果解釋，不把未保存的原始 subsecond 或子程序 exit code 當成已證事實。

`portfolio_alert_snapshot_quality_not_ready`、`risk_prompt_snapshot_quality_not_ready`、1418 沒有 filled entry、human thesis 缺件與 forward natural maturity pending 都是下游品質／成熟度 residual；它們不在本次 wrapper failure list，亦不應透過偽造 entry／thesis 或放寬 gate 來通過 capture。

## 本輪 durable receipt 契約

9/17 的既有 `latest_status.json` 沒有保存 immutable run、child stdout／stderr 或 OS returncode；這個歷史缺口仍保留，不能由新程式回填。修補後每次合法 invocation 都會在
`<output_root>/scheduled/decision_evidence_capture/runs/<run_id>/` 建立 create-only run directory，
其中保存 terminal `receipt.json` 與各 child 的 bounded stdout／stderr artifact。`run_id` 含 UTC
microsecond 與 UUID；同日、同秒或 retry 都不共用 receipt，也不覆寫舊 run。

child 執行以 bytes capture；完整 stdout 仍用於 JSON parse，artifact 以原始 bytes 的 64 KiB
head／tail 保存。receipt 另記錄每個 stream 的原始 byte count、原始 SHA-256、是否截斷、保存
artifact byte count／SHA-256、實際 OS returncode、timeout 與 artifact write status；不保存 child
environment。timeout 的 returncode 保留為 `null`，不製造 synthetic exit code。

terminal receipt 先以 flush／fsync durable 寫入，再由 atomic latest status 指向該 `run_id`、receipt
path 與 receipt SHA-256。receipt、raw artifact 或 latest write 失敗都不能顯示 `passed`；child 已回傳但
artifact 寫入中斷時，step 的實際保存狀態標為 `unknown`，不宣稱沒有寫入。child launch 例外也會
留下 failed receipt。child timeout／非零 exit 且沒有完整 JSON 時，snapshot `saved` 與 evidence
counts 也標為 `unknown`（`null`），因為 child 可能已在輸出前完成部分 SQLite commit；receipt 保留
實際 returncode／timeout 與 raw artifact。`_run_json_cli` 在 child 已啟動後的 generic exception
標示 execution `unknown`，保存例外可取得的 stdout／stderr；明確的 pre-launch
`FileNotFoundError`／permission／path 例外仍保留 launch failure。invalid UTF-8 stdout 只使 JSON
parse fail closed，不丟失原始 bytes／hash。這些 receipts 只觀測與追溯每日 capture，不改正式資料、
scheduler 或 authority。

## 修補

- `scripts/scheduled/run_scheduled_decision_evidence_capture.py`：保留 aware clock 的原始 precision，`_base_payload()` 的 context 欄位與 child `common_args` 共同使用 `datetime.isoformat()`；parent 與 child 對完全相同的 timestamp bytes 計算 hash。
- `scripts/scheduled/run_scheduled_decision_evidence_capture.py`：每次 run 保存 immutable terminal receipt、bounded raw child streams、原始 byte count／hash／truncation、returncode／timeout 與 latest pointer；create-only publish、receipt I/O failure、child artifact I/O failure 均 fail closed。
- `tests/test_scheduled_decision_evidence_capture.py`：after-close case 使用 `20:25:00.123456+08:00`，驗證 status、child args、parent／snapshot context hash 均保留並一致；另驗證同秒不同 decision subsecond 產生不同 identity，以及 captured_at 改變的 retry 保留同一 identity 但產生不同 full context hash；真子程序 exit 0／非零／timeout、先寫隔離 artifact 後失敗、raw stream metadata、同日 immutable retry、receipt I/O、partial-success exception、child artifact I/O unknown state、post-start exception 與 invalid UTF-8 raw hash 均有隔離測試。

這個修補不把實際 capture／decision 時刻前移到整秒，也不改 capture authority：仍為 `research_only=true`、`preopen_authority=false`、`natural_authority=false`。

## 驗證

```text
.\.venv\Scripts\python.exe -m pytest tests/test_scheduled_decision_evidence_capture.py -q -o addopts=
38 passed, 1 warning in 1.42s

.\.venv\Scripts\python.exe -m pytest tests/test_capture_decision_desk_snapshot_cli.py tests/test_capture_evidence_events_cli.py tests/test_evidence_capture_service.py -q -o addopts=
24 passed, 1 warning in 16.63s

.\.venv\Scripts\python.exe -m py_compile scripts/scheduled/run_scheduled_decision_evidence_capture.py tests/test_scheduled_decision_evidence_capture.py
exit 0，無 stdout

.\.venv\Scripts\python.exe -m mypy --explicit-package-bases scripts/scheduled/run_scheduled_decision_evidence_capture.py
Success: no issues found in 1 source file

.\.venv\Scripts\python.exe scripts/quant_guard_linter.py
check_financial_float_boundaries.py 通過；check_look_ahead_bias.py 通過；所有量化防禦檢查通過

git diff --check
exit 0；只有 LF/CRLF line-ending warning，無 whitespace error
```

兩個 pytest 的 warning 都是 `.pytest_cache` 權限，非測試失敗。本輪新 receipt slice 原始輸出保存於 `output/qa/daily_capture_recovery_20260918/receipt_repair/` 的 `focused_pytest_partial_unknown_final2.txt`、`mypy_partial_unknown_final.txt`、`py_compile_partial_unknown_final.txt`；前一輪 child／service output 仍保留於既有 QA 目錄。上述隔離測試不替代合法自然日正式 receipt。

## 未觸發的 scheduler action 唯讀確認

repo 內既有註冊定義的 action chain 是 `register_baldr_scheduled_tasks.ps1` →
`scripts/scheduled/run_decision_evidence_capture.cmd` →
`scripts/scheduled/run_scheduled_decision_evidence_capture.py`；cmd 會由 repo root 呼叫目前工作樹的 Python wrapper。

本輪早先未提升權限的 inspector 只能讀到 `available_count=0`、
`action_unobserved_count=19`、`configuration_ready=false`；其原始輸出保留於
`output/qa/daily_capture_recovery_20260918/scheduled_task_readonly.txt`。後續由 B 線以唯讀提升權限
核實 `baldr-decision-evidence-capture-daily` 的 action 為
`cmd.exe /c "C:\Projects\PythonProjects\technical_analysis\scripts\scheduled\run_decision_evidence_capture.cmd"`，
working directory 為空字串；`next run=2026-09-18T05:25:00-07:00`、
`last run=2026-09-17T05:25:01-07:00`、`last result=1`。因此可確認下一次預定 action 會使用本 repo wrapper，
但 `last result=1` 不能替代新的 capture receipt，也不能宣稱下一次 run 已成功。原始 action readback
見 [Natural learning trace](NATURAL_LEARNING_TRACE_2026_09_18.md)；本輪未 trigger、register、change 或 rerun task。

## residual 與限制

- 本輪沒有正式重跑，故不產生 9/17 historical retry，也不授予 natural／Paper／Formal credit。
- 最新 forward outcomes 的 5／10／20／60 maturity 與推薦 snapshot degraded 狀態維持原 receipt；本修補只恢復 wrapper 對合法 child receipt 的一致性檢查。
- 9/17 原始 scheduler task／stdout／OS exitcode 未保存於正式 capture 目錄；新 wrapper 只會從下一次合法 run 開始保存，不能追補或從缺失檔案推定外部終止者或其他歷史根因。

## 共用 SSOT 整合紀錄

本輪已依 root 授權整合 Manual、Snapshot、Documentation Index 與 Roadmap Hub；只更新下列 bounded
入口，沒有改版本或其他 Roadmap／Architecture 文件：

- `docs/07_guides/APPLICATION_MANUAL.md` 的 `Decision Desk／Evidence capture 的真實時鐘（2026-09-16）` 段：補充完整 aware ISO precision、舊 failed 不回填、合法下一次 run 的 readback 與 persisted/current 分開判讀。
- `docs/00_core/PROJECT_SNAPSHOT.md` 頂部：同步 A `33 wrapper＋24 child/service` durable-receipt QA、B `5d` forward research／`27 passed` maturity-calendar wiring 非 calibration、C `rule_only`／personal capture `0` 限制與 QA 連結。
- `docs/00_core/DOCUMENTATION_INDEX.md` 的 `6. QA 與審核` 表：新增 A／B（natural trace 與 maturity-calendar）／C 的 2026-09-18 QA 入口。
- `docs/00_core/DEVELOPMENT_ROADMAP.md` 的 Hub 頂部：新增短連結與 bounded 限制，不改版本、產品方向、長期 maturity 或其他 roadmap 內容。

下一次合法 scheduled run 仍須以實際 latest receipt 驗證成功與否；本文件不把 scheduler action 或 bounded QA 宣稱為正式自然 credit。

## 回滾

若 root review 不接受，回滾時只針對本輪已識別的 receipt-repair hunks 製作精確反向
patch，保留同檔其他 agent 的變更；不以整檔 checkout 覆蓋 wrapper 或其 tests。

QA raw copy 位於 `output/qa/daily_capture_recovery_20260918/`，可直接移除；不涉及正式資料。
