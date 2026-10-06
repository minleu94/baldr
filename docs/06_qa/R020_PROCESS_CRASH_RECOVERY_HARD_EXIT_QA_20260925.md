# R020 跨 store 硬中止復原 QA（2026-09-25）

## 狀態與凍結識別

本收據補足 Registry 部分發布狀態的真實子程序硬中止覆蓋。Root 已複核本 slice，未發現 P1／P2，接受本次有限 recovery 證據。只修改 `tests/test_r020_process_crash_recovery.py`；未改 production source、fixtures 或其他測試。

| 項目 | 識別／結果 |
|---|---|
| 變更測試 | `tests/test_r020_process_crash_recovery.py`；原測試 SHA-256 `07C2A71B44CB5A3462D0A800FE7EE9F793A6CFA19A487CE7846681352AF39C63`；新增後 SHA-256 `AEE58FA99D089DDA40D368062299871333D4BD104C477BA1B1256611BFB3A998` |
| 執行範圍 | `tests/test_r020_process_crash_recovery.py`、`tests/test_r020_portfolio_result_registry_service.py` |
| 隔離根目錄 | `<USER_HOME>\AppData\Local\Temp\r020_crashqa_luna`；`TEMP`／`TMP` 指向該根；pytest basetemp 位於 `root\p`；`PROFILE=test` |
| 執行環境 | Windows／Python 3.11.9／NumPy 2.3.5／Pandas 2.3.3（repo `.venv`） |
| 結果 | 42 passed、0 skipped；pytest 13.05 秒；exit 0 |
| Log | `<USER_HOME>\AppData\Local\Temp\r020_crashqa_luna\pytest.log`；SHA-256 `96A9ADEF040AD62F0D299FC489868C5D2DCD3C160C40DE75E4B758FCBAA65448` |
| 檢查 | changed test `py_compile` 與 `git diff --check` 均 exit 0 |

重跑方式（repository root）：

```powershell
$qaRoot = '<USER_HOME>\AppData\Local\Temp\r020_crashqa_luna'
$env:TEMP = $qaRoot
$env:TMP = $qaRoot
$env:DATA_ROOT = Join-Path $qaRoot 'd'
$env:OUTPUT_ROOT = Join-Path $qaRoot 'o'
$env:PROFILE = 'test'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $qaRoot 'c'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r020_process_crash_recovery.py `
  tests/test_r020_portfolio_result_registry_service.py `
  -q -rs -o addopts= -p no:cacheprovider `
  --basetemp (Join-Path $qaRoot 'p') --tb=short
```

## 有限 hard-exit 覆蓋

每個新案例均在獨立 `spawn` worker 內以 `os._exit` 中止；父程序確認 worker 已退出後才建立／使用新 service，呼叫 quiescent `reconcile_incomplete_saves()`。四個 `files_ready` 案例均驗證完整 strict readback、完整 DTO `to_dict()` 與原始結果相等、child identity 順序相等、R012 child artifact raw bytes 不變；同一 Registry payload 的重試不改 final bytes，異 summary／異 child bytes 衝突也不覆寫。

| 硬中止時點 | 中止後持久狀態 | Quiescent reconcile 結果 |
|---|---|---|
| `finalize_portfolio_result_staging` 返回後、`files_ready` CAS 前 | Registry `staging/pending`，descriptor 已 finalize；尚無 final publish | `failed/failed`；strict reader 拒讀；child raw bytes 不變。未要求此 staging failure 支援 Registry retry |
| Equity final publish 後 | `files_ready/pending`；只有 equity final | `committed/valid`；完整 strict readback 與冪等／衝突不覆寫檢查通過 |
| Trades final publish 後 | `files_ready/pending`；equity、trades final | 同上 |
| Portfolio-result sidecar publish 後 | `files_ready/pending`；equity、trades、portfolio sidecar final | 同上 |
| Lineage publish 後、commit 前 | `files_ready/pending`；全部四個 final bytes 已發布 | 同上 |

`after_replay_lineage_rename` 與 `before_final_commit` 之間沒有另一個持久寫入；故合併為一種「所有 final bytes 已發布、Registry 尚未 commit」狀態，沒有新增重複的第六案例。finalize 後的 `staging` 與四種 `files_ready` 發布狀態均為不同持久狀態。

原有 `tests/test_r020_process_crash_recovery.py` 三個 hard-exit 點保留：R012 child publish 後／index 前、所有 child 完成後／Registry save 前、Registry `files_ready` 後／第一個 final publish 前；另保留 committed child 缺檔的 strict fail-closed 案例。現在共有八個具名 `spawn`／`os._exit` 點及一個 separate missing-child 情境。此數量不含 `test_r020_portfolio_result_registry_service.py` 的 injected exception cases；那些仍用於驗證同一持久狀態的 exception recovery。

## R020 有限 closeout checklist

| 條件 | 判定 | 證據／限制 |
|---|---|---|
| R005 原生 provider 的 v1 row、fallback、排序／tie、top-N、filter/per-stock exception 與 factor survivor parity | 已由本次 C2 current NP2 pytest baseline 覆蓋 | `tests/test_recommendation_replay_characterization.py:456-604,613+`；不擴大成所有 runtime 或全市場資料重建要求 |
| Typed provider 到 snapshot／canonical child 的雙層切片、terminal、ordered rows、diagnostics、factor scores、empty/custom provider 邊界 | 已有 frozen R020 40-test route，亦納入 C2 136-test frozen union | `tests/test_r020_replay_pipeline_composition.py:252-387`、`tests/test_r020_replay_mixed_terminal_composition.py:210-375`、`tests/test_r020_typed_provider_child_handoff.py:180-421`；signed slice 不等於 request metadata 保存負值 |
| Portfolio same-mode、cutoff／PIT、equity／trades／cash／summary、factor manifest 與成本 | C2 current 136-test NP2 baseline accepted；相關 R005/V-REPLAY cases 均在凍結輸入內 | `tests/test_r020_concrete_portfolio_parity.py:91-179,481-1116`、`tests/test_recommendation_portfolio_banktaiwan_cost.py`；不同 execution contract 各自比其 oracle，不要求彼此帳務相同 |
| Cross-store process-crash／missing-child recovery | 本次五個新增硬中止狀態加三個既有硬中止點、child-missing 負例已覆蓋 | 合成 fixtures；quiescent reconcile；strict reader；same-hash idempotency；異 bytes no-overwrite。共同 transaction、跨 store rollback／補償與自動重建原 execution 不在設計承諾內 |
| `TMP-REC-04` row bridge | R020 generic v1 row→canonical child builder 已移除；目前成功 child 由 typed candidate/outcome 建立，custom／legacy／override 仍 v1-only | `app_module/recommendation_replay_service.py:200-311,405-419`、`app_module/recommendation_dataframe_provider.py:192-273`。`RecommendationSnapshotDTO.recommendations` 是刻意保留的 v1 compatibility output |
| C2 mandatory Workbench／Update validator／broad mypy | 尚待目前並行 implementation 穩定後，在需要 C2 的 release cleanup 前補跑 | 既有 Workbench、Update QA、broad mypy receipts 與四個 UI 檔 bytes-continuity 見 `C2_NON_ML_CONSUMER_UNION_PREFLIGHT_20260925.md`（開發收據見dev） 及 `C2_CURRENT_UNION_PYTEST_BASELINE_20260925.md`（開發收據見dev）。此項是 C2 final gate，不是新增 R020 recovery state |
| `TMP-NUM-01` 整體退休 | 仍為獨立 active numeric gate，不是 R020 row-bridge 子範圍的 closure blocker | R020 僅移除 generic row-dict→canonical child bridge；其餘既有 numeric compatibility/caller cutover 依獨立驗證處理 |

## Console log 保存範圍

此前獨立 reviewer 的 40-test typed-handoff NP1／NP2 rerun 沒有保存可 readback 的 console-log files；原報告不虛構 log path/hash，也未為重建歷史收據而重跑同一 route。C2 current union NP2 有保存 manifest 與完整 log，可讀回該凍結時點的 40 個 R020 test bytes；本報告另保存新增 recovery test bytes 的 42-pass targeted log。新增測試完成後，C2 manifest 不再代表當前這一個測試檔；C2 route 與後續 recovery route 按各自 frozen identity 分開判讀。

上述證據建議作為 R020 closeout review 的輸入：本收據沒有發現剩餘的 R020-specific recovery window 或未涵蓋的既有 R005 vector；C2 mandatory UI／validator／broad-mypy final gates 和 root 最終裁定仍待完成。沒有新增「跨 store 原子交易／自動重建」或「所有平台／所有可能向量」前置條件。未 stage、commit 或 push。
