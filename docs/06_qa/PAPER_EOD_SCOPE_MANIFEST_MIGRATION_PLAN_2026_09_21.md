# Paper EOD scope manifest v2→v3 受控修正計畫

日期：2026-09-21

範圍：`baldr-paper-execution-eod-replay-daily` 的 repository-isolated Paper EOD adapter。

狀態：**已完成僅 scope metadata 的 create-only v2→v3 遷移；scheduler、full writer 與 EOD
producer 仍未驗收，尚未 commit。**

## 事故邊界與首個錯誤

2026-09-21 台北 21:00 的 Task Scheduler readback 顯示：

- task：`baldr-paper-execution-eod-replay-daily`
- `Last Result`：`1`
- action：`cmd.exe /c "C:\Projects\PythonProjects\technical_analysis\scripts\scheduled\run_paper_execution_daily_isolated.cmd"`
- 依賴 gate：`ready_with_warnings`，blocker `0`，且正式 SQLite 來源以 `mode=ro/query_only` 通過純讀 preflight
- 2026-09-21 execution immutable receipt：`0`

純讀診斷所定位的首個 runtime error 是
`RuntimeError: isolated Paper scope manifest changed`，發生在
`_write_or_verify_scope_manifest`，早於 scope preflight、calendar refresh 與 ledger schema
初始化。既有 `scope_manifest_v2.json` 的 body hash 可重算，但 body 少了
`writable.event_capture_root`；其餘 canonical roots 與舊 v2 schema 一致。commit
`c8dc5a7d` 引入 event capture binding，`bccabfe9` 只把 ledger schema 初始化前移，尚未能
執行到該處理流程，因此不能歸因於 ledger schema。

## 正式檔案目前狀態（read-only）

診斷時只讀確認：

| 項目 | 值 |
|---|---|
| v2 path | `output/paper_execution_eod_replay/scope_manifest_v2.json` |
| v2 file SHA-256 | `sha256:9b96673582de48ae77eb493d163110906985c41c7bdb949cbdc84bc1e85e9310` |
| v2 declared/recomputed body SHA-256 | `sha256:010d87fc9fcd3aa241d228c0bca48fbaf7b66b833af3fb56250c0773a1fe340c` |
| v3 path after approved metadata migration | `true` |
| migration receipt after approved metadata migration | `true` |
| active Paper EOD process | `NO_ACTIVE_PAPER_EOD_PROCESS`（Win32 read-only query） |

依據：`output/qa/scheduler_readback_20260921_1909/paper_last_result1_diagnosis_20260921.json`。
正式 v2 bytes 在本次工作中沒有被覆寫、搬移或重新格式化。

## 僅允許的 v2→v3 變更

adapter 現在將 v2 視為 immutable historical source，v3 為新建的 append-only manifest。
只有下列兩種精確 v2 body 可作為 migration source：

1. `schema_version=paper-execution-isolated-scope.v2`，canonical roots 全部與當前固定
   scope 相同，`writable.scope_manifest` 精確指向舊 v2 path，且沒有
   `writable.event_capture_root`。
2. 上述完全相同，且已存在 canonical `writable.event_capture_root`。此形式保留既有合法
   v2 run，不因新修正破壞歷史成功執行。

任何其他 schema、root、state/ledger/market path、safety 欄位或 hash 不一致，都在建立
v3 前拒絕，且不寫入 v3 或 migration receipt。v3 body 的
`writable.scope_manifest` 精確指向 v3 自身。

目前正式檔的**純 dry-run planned diff**只有：

```text
schema_version
writable.event_capture_root
writable.scope_manifest
```

核准前 dry-run 與實際 readback 值：

- v3 body hash：`sha256:a3be7ca4bcd1cebe731fc0cc302840b8e0c38599b069b7a40932aeb003f0e2ef`
- v3 file hash：`sha256:d7e7869fa320cdb3e4036a28f992ceb50744bcfabaacd0aa51fd689d9d2793e4`
- v3 path：`output/paper_execution_eod_replay/scope_manifest_v3.json`
- migration receipt：`output/paper_execution_eod_replay/scope_manifest_v3_migration_receipt.json`

實際 migration receipt 的 `recorded_at` 為 `2026-09-21T19:57:52.657831+00:00`，具
timezone；receipt 的 planned target file/content hash 與上述 v3 readback 完全相同。
receipt file SHA-256 為
`sha256:926f4673b30d4923d26e3c6288d79d79fbec3f82b3cc64532504c0a11c2f3f68`，receipt body
hash 為 `sha256:6385de5a1bb48608f8db8644304b8cb96d7cd45b83830a4009cec565963302ff`。

## 寫入與回滾方案及實際結果

- v2 不做 backup copy，也不改名；原始 bytes/hash 直接留在原 path，receipt 保存其 file hash。
- v3 只能用 create-only + flush/fsync 建立；既有 bytes 不一致時拒絕覆寫。
- migration receipt 也只能 create-only，記錄 planned diff、source/target file hash、
  `source_bytes_preserved=true`、實際首次建立時的 UTC `recorded_at` 及三項
  formal/broker/market write 禁止旗標；後續驗證沿用原 `recorded_at`，不以歷史排程時間
  追認遷移。
- 若 v3 已存在，必須 exact verify；若 migration receipt 缺失，才可依相同 hash/idempotent
  plan create-only 補上。v2 每次都重新驗證並確認 file hash 未變。
- 實際執行前再次以 elevated read-only `schtasks` 查到 task `Enabled/Ready`、Last Run
  `2026/9/21 06:00:01`、Last Result `1`、action 指向固定 isolated cmd；實際
  Python/cmd runner query 為 `NO_ACTIVE_PAPER_EOD_PROCESS`；v2 hash 符合且 v3／receipt
  均不存在。
- 實際只呼叫 `_write_or_verify_scope_manifest()`；沒有呼叫 `run_isolated()`、Paper
  producer、EOD writer 或 scheduler trigger。第二次同一 helper readback 的 v2/v3/receipt
  bytes 均不變，且 ledger、repository state、source state、market DB 的 size/mtime
  signature 全部不變。
- 原始 readback 已保留於
  `output/qa/paper_scope_manifest_migration_20260921/migration_readback.json`，task
  唯讀狀態已保留於同目錄 `task_state_after.txt`。

## scope 失敗的 terminal receipt

`run_isolated()` 現在將 scope writer/manifest 邊界的任何一般例外轉成 terminal failed
result，避免 Python 未處理例外再次只留下 `Last Result=1` 而沒有 machine-readable receipt。
失敗 receipt 固定寫到：

```text
<repository>\output\paper_execution_eod_replay\scope_validation_failures\
```

此路徑由 repository root 推導，另行檢查位於 repository 內且不與正式 data root 重疊；它
不使用尚未通過驗證的 `OPERATIONAL_ROOT`、candidate、receipt 或 event capture writer
target。receipt 標記 `terminal=true`、`scope_writer_targets_verified=false`、
`formal_credit=false`、`broker_execution=false`、`writes_market_database=false`。若安全
receipt 本身無法寫入，結果仍保留 `receipt_write_error`，不再把例外向 scheduler 冒泡。

## 隔離測試與遷移 readback 證據

`tests/test_paper_execution_isolated_scope.py` 覆蓋：

- 精確 legacy v2（缺少 event root）建立 v3，並保留 source bytes/hash
- 已含 event root 的合法 v2 建立 v3
- v3 及 migration receipt 第二次執行 bytes 不變（idempotent）
- 非預期 market root drift 在任何新檔案寫入前拒絕
- scope 失敗只建立固定安全目錄下的 terminal failure receipt，不建立 v3、migration
  receipt、candidate 或普通 receipts

目前驗證：

```text
.venv\Scripts\python.exe -m py_compile scripts\scheduled\run_paper_execution_daily_isolated.py  PASSED
.venv\Scripts\python.exe -m pytest tests\test_paper_execution_isolated_scope.py -q -o addopts=  11 passed
.venv\Scripts\python.exe -m pytest tests\test_paper_formal_daily_source_chain.py -q -o addopts=  17 passed, 1 skipped
.venv\Scripts\python.exe -m pytest tests\test_paper_portfolio_isolated_scheduler.py -q -o addopts=  14 passed
.venv\Scripts\python.exe -m mypy scripts\scheduled\run_paper_execution_daily_isolated.py --follow-imports=skip  Success
git diff --check  clean
```

完整相關測試合計 `43` tests：`42 passed`、`1 skipped`。skip 為
`test_paper_event_capture_rejects_directory_reparse_point` 建立 directory reparse point
時缺少 Windows privilege（`WinError 1314`），測試本身明確 skip，與 scope migration 無關。pytest 另有既有
`.pytest_cache` permission warning，未修改 cache。

遷移後仍未包含正式資料 writer／producer 的正常 scheduler run 驗收；下一次自然 Paper
EOD run 必須再觀察 v3 scope、migration receipt、scope failure/operational receipt、ledger
readback 與 downstream event capture 是否完整，不能把本次 metadata 成功當成 EOD 成功。
