# R026 historical replay cross-call mixed-version characterization

日期：2026-09-25

## 範圍與觀察

修補前的 `tests/test_recommendation_historical_replay.py::test_replay_can_mix_sqlite_versions_between_snapshot_and_forward_calls` 是 test-only characterization（現已改名並改為要求整輪 fail closed）。它使用真實 `MLHistoricalSnapshotProvider` 與 `RecommendationHistoricalReplayService`，以 `tmp_path` 建立合成 SQLite/WAL 資料庫；不讀寫正式資料。下列原始 receipt 僅描述修補前 production 行為。

測試有一個無 mutation 控制組與一個跨呼叫更新組。兩組都以決策日 `2014-03-15` 建立同一個樣本，label date 為決策日後第 20 筆價格 `2014-04-04`。跨呼叫組在真實 `load()` 已返回後、真實 `load_forward_price_window()` 開始前，以另一條連線在一個 commit 中將 D 前一日 feature 價格從 `172` 改為 `900`，並將 label 價格從 `193` 改為 `1000`。

觀察到的結果：

- `load()` 返回的歷史 snapshot 仍含舊 feature close `172`；之後 feature builder 從該 snapshot 算出的 `stock_return_1d_bp` 為 `58`，且修補前此值進入該筆 replay sample。
- `load_forward_price_window()` 看見新 label close `1000`；修補前 service 仍成功產生 sample，`stock_return_bp` 為 `47803`。控制組 label close 為 `193`，sample `stock_return_bp` 為 `1156`。
- 跨呼叫組在 replay 結束後，SQLite 兩列都已是新值；測試沒有依賴檔案 mtime 或 `source_fingerprint` 變化來判定混版。

因此修補前實際路徑曾允許單次 `load()` 的舊 snapshot 與後續 forward call 的新資料組成一筆 sample。這是對當時跨呼叫版本缺口的合成證據，不是預期產品行為；目前整輪 fail-closed 行為記錄於本 note 後續 follow-up 節。

## Look-ahead 自查

變更只發生在 `load()` 已完成之後。feature 僅來自當時捕獲且嚴格早於 D 的價格 rows；D 之後的第 20 筆價格只用於成熟 label。測試不將未來價格回灌 feature，也不改既有 cutoff。WAL writer commit 只作為受控測試擾動。

## 驗證收據

環境：Windows 10、CPython 3.11.9、SQLite 3.45.1、NumPy 2.3.5、pandas 2.3.3；`PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP`、`TMP` 與 pytest basetemp 均設於各自新建的隔離 TEMP root。

單測：

```powershell
.\.venv\Scripts\python.exe -B -m pytest `
  tests\test_recommendation_historical_replay.py::test_replay_can_mix_sqlite_versions_between_snapshot_and_forward_calls `
  -q -o addopts= -p no:cacheprovider --basetemp C:\Users\archi\AppData\Local\Temp\r026_replay_mix_fa689957bc174dd0973eaa0b1c8b7537\pytest
```

結果：**1 passed**（0.27 秒）。Log SHA-256：`8A2D0CBCAFEEA9F583E10CF3642EB2EC47C6AA875F772CD1C6133B9FCB47DECB`。

相鄰 per-call/provider 路由：

```powershell
.\.venv\Scripts\python.exe -B -m pytest `
  tests\test_recommendation_historical_replay.py `
  tests\test_ml_historical_snapshot_provider.py `
  tests\test_r026_calibration_legacy_preparation_baseline.py::test_provider_load_pins_query_window_and_rejects_concurrent_commit `
  tests\test_r026_calibration_legacy_preparation_baseline.py::test_provider_detects_commit_between_version_baseline_and_revision_precheck `
  -q -o addopts= -p no:cacheprovider --basetemp C:\Users\archi\AppData\Local\Temp\r026_replay_mix_route_be31736d83ce445788742149ee7b5f06\pytest
```

結果：**19 passed**（1.48 秒）。Log SHA-256：`DB80EF13E92E5F4207AAE7ADF10ABB9DB0CC7DFACCD870DC2654E9A9A25EC009`。Scoped mypy：provider 與 replay service 2 source files、0 issues；相關 provider、service、測試 3 檔 `py_compile` 通過；`git diff --check` 通過，僅有既有 LF/CRLF 轉換提示。

## 修補前 characterization SHA-256 與限制

- 修補前 `data_module/ml_historical_snapshot_provider.py`: `0223A3665B68DB950CF806D87F7C3CC3BBE925277813D083F7AFBB3A2A8E3928`
- 修補前 `ml_module/recommendation_historical_replay.py`: `ABEFAD976DEDCBAA1396054452D56B0FC79E3DBDBD7C9602066B5B1A5501BAE2`
- 修補前 `tests/test_recommendation_historical_replay.py`: `AA83094DFFFE2314F20CF8D33A168E129DD154CFC2F977DE3A074A7B0F94BB48`
- `docs/06_qa/R026_HISTORICAL_REPLAY_CROSS_CALL_MIXED_VERSION_20260925.md`: SHA-256 見交付訊息。

修補前 characterization 測試曾登錄 `service-oracle-recommendation`；本次沒有修改 inventory。該歷史測試證明 SQLite 的兩次 provider 呼叫可讀到不同版本；不證明 sidecar 與 SQLite 的共同原子版本、整次 replay 的其他額外 SQLite readers、ABA 排除或實際資料庫規模下的 WAL 行為。下文 follow-up 記錄目前 source/test SHA。R026 與 `TMP-ML-01` 仍維持 open/active。

## Whole-replay observation lease follow-up

**狀態：** R015 已完成 frozen bytes 獨立複核，未發現 P1/P2；root 判定此切片 bounded `ACCEPTED_SCOPE`。R015 fresh short TEMP 重跑主路由 25P，另跑 BankTaiwan cost cohort 1P；source mypy 2 files／0 issues，4 檔 `py_compile` 通過。接受範圍限下列 whole-build observation lease、列出的 WAL mutation cases 與既有 cost-cohort caller。

前述跨呼叫 mixed-version 路由是修補前 characterization：它曾觀察到 feature snapshot 使用舊價格而 forward label 使用新價格，且舊服務會發布該 sample。此行為已改為 fail closed；目前對應測試名稱為 `test_replay_fails_closed_on_sqlite_commit_between_snapshot_and_forward_calls`，仍以真實 provider / service / WAL writer 固定同一混版情境，但要求整輪 build 拋出 `historical SQLite source changed during read lease`，不返回部分 dataset。無 mutation 控制組仍要求產生原本的 `1156` bp 樣本。

`RecommendationHistoricalReplayService.build()` 現在在第一個 SQLite read（trading-date enumeration）前開啟 provider 的同連線 observation lease，並在 `_build_result()` 的任何正常返回（包含空日期）前 postcheck。lease 不要求呼叫 `.load()`；它只比較同一唯讀連線的 `PRAGMA data_version` 與資料庫檔案 size/mtime。若 provider 將一次讀取期間的錯誤記錄為 per-date skip，最外層 postcheck 仍會拒絕整輪結果。lease context manager 在成功、例外及早退時都關閉連線。

已驗證的 commit 注入位置：

- snapshot schema 查詢期間的 WAL commit；
- 真實 `load()` 返回後、`load_forward_price_window()` 前的 WAL commit（同一 commit 同時改 feature 價格與第 20 筆 label 價格）；
- trading-date enumeration 返回空 tuple 後、empty result 返回前的 WAL commit。此路徑驗證 observation-only postcheck 不依賴 snapshot load。

`test_preflight_failure_classifies_transient_and_integrity_faults` 單獨固定既有 scheduled classifier 將 `changed during read lease` RuntimeError 歸為 source-integrity emergency rollback，而非 recoverable dependency retry；此測試不執行完整 scheduled job entrypoint。Whole-replay WAL cases 則驗證 build 路徑 fail closed。這個修補只提供有界的同連線變更觀察，不持有跨整輪 SQLite transaction、不構成 durable generation、不證明與 revision sidecar 原子一致，也不排除 data_version/stat 無法觀察的 ABA 或 postcheck 後競態。R026 與 `TMP-ML-01` 仍維持 open/active。

### 修補後驗證收據

環境為 Windows、CPython 3.11.9、SQLite 3.45.1、NumPy 2.3.5、pandas 2.3.3；`PROFILE=test`，資料、輸出、TEMP/TMP 與 pytest basetemp 均位於新建隔離目錄。

命令：

```powershell
.\.venv\Scripts\python.exe -B -m pytest `
  tests\test_recommendation_historical_replay.py `
  tests\test_ml_historical_snapshot_provider.py `
  tests\test_r026_sqlite_read_lease.py `
  tests\test_r026_calibration_legacy_preparation_baseline.py::test_provider_load_pins_query_window_and_rejects_concurrent_commit `
  tests\test_r026_calibration_legacy_preparation_baseline.py::test_provider_detects_commit_between_version_baseline_and_revision_precheck `
  tests\test_daily_recommendation_learning_loop.py::test_preflight_failure_classifies_transient_and_integrity_faults `
  -q -o addopts= -p no:cacheprovider --basetemp <fresh-TEMP>\pytest
```

結果：**25 passed**。最終 QA root：`C:\Users\archi\AppData\Local\Temp\r026_whole_lease_final2_2cfdf853c99d4c598c8ca84fefcc905a`；log 為該目錄 `pytest.log`，SHA-256 `DA2383135A59399E3C20C20E18409D46740EC6CAB27FB3A54064532F70EE729E`。Scoped mypy 對 provider 與 replay service 2 source files、0 issues；相關 provider、service、replay tests 與 scheduled classification test 的 `py_compile` 通過。這是 synthetic bounded route，不等於完整 R026 acceptance 或正式資料驗證。

另以 fresh TEMP 單獨執行 `tests/test_daily_banktaiwan_learning_cost.py::test_replay_keeps_three_market_dates_in_one_cost_cohort`，結果 **1 passed**，log SHA-256 `88BD8DFDB7A94B6010BA5E505610DE7AF6F1C0243A48A0FDF1FE146C619A4FA4`；此測試確認既有 multi-date cost cohort 正常產生。

排程相關證據由兩部分組成：whole-replay tests 驗證 lease RuntimeError 會拒絕 replay 結果；`test_preflight_failure_classifies_transient_and_integrity_faults` 驗證既有 scheduled classifier 將該錯誤分類為 source-integrity emergency rollback。這是「replay 呼叫路徑 + 分類器」證據，沒有在完整 scheduled job entrypoint 注入 WAL 更新並驗證整條排程執行。R026 仍 `IN_PROGRESS`、`TMP-ML-01` 仍 `ACTIVE`；跨資源 sidecar/SQLite 原子性、durable generation、ABA 與 postcheck 後競態仍未解。
