# R026 historical replay per-call cutoff characterization

> **歷史收據界線：**本 note 的 frozen route 記錄 whole-replay observation lease 接線前的 per-call 行為。當時「略過受影響決策日並保留先前樣本」的結果不是目前 production behavior；目前任一可見的外部 SQLite commit 會在整輪 `build()` 返回前 fail closed，不發布部分 dataset。修補後路由與 source/test SHA 見 [whole-replay observation lease follow-up](R026_HISTORICAL_REPLAY_CROSS_CALL_MIXED_VERSION_20260925.md#whole-replay-observation-lease-follow-up)。本 note 後續段落與 log 仍保留其歷史測試收據，不應用作修補後行為證明。

日期：2026-09-25

## 範圍

此 test-only slice 固定 historical replay 對真實 `MLHistoricalSnapshotProvider` 的兩種 read cutoff 與單次 provider read 失敗行為。測試使用 pytest `tmp_path` 建立合成 SQLite，`PROFILE=test`，未讀取或修改正式資料。既有 `tests/test_recommendation_historical_replay.py` 已登錄於 `service-oracle-recommendation`，本次沒有改 inventory。

## 凍結的行為

- `test_replay_keeps_feature_and_forward_receipt_cutoffs_distinct_and_causal` 以 provider 真正呼叫的 daily-price receipt checker 記錄每次 cutoff。決策日 `2014-03-15`、`2014-03-16` 的 feature `load()` 分別使用自身決策日作 cutoff；各次 `load_forward_price_window()` 則使用 `replay_end=2014-04-15`。合成資料每個日曆日均有一列，因此 feature cutoff 為決策日前一日，價格、技術與市場 feature rows 均嚴格早於決策日。
- Forward window 只供 label 使用：起點含決策日，結束不超過 replay end；label 使用決策日後第 20 個實際存在的 future price observation。固定的獨立預期為 `2014-03-15 → 2014-04-04`、`2014-03-16 → 2014-04-05`，且 `label_available_date == label_end_date > decision_date`。
- 修補前的 `test_replay_discards_a_decision_when_its_snapshot_read_detects_a_commit`（現已改名為 `test_replay_fails_closed_when_sqlite_commit_occurs_inside_snapshot_read`）在 WAL 模式、第二個決策日的 provider `load()` 已讀取 schema 後，由另一個 SQLite connection 提交合成價格更新。當時 provider 偵測單次 read 的 commit，service 只略過該決策日並保留前一個樣本；整輪 observation lease 接線後，同一注入要求整輪 build 拋錯，任何先前樣本都不會返回。

look-ahead 自查：feature rows 僅限 `date < D`；future prices 僅在 `date > D` 的樣本計算中使用，且只決定成熟 label；forward receipt cutoff 使用 replay end，不回灌為 feature cutoff。這是合成逐日資料的 per-call PIT characterization，不代表真實市場日曆或完整研究資料覆蓋。

## 驗證收據

Fresh 隔離 TEMP root：`C:\t\r026_histreplay_final_37a6ac6d`。`PROFILE=test`，`DATA_ROOT`、`OUTPUT_ROOT`、`TEMP`、`TMP` 與 pytest `--basetemp` 均指向此 root 的隔離子目錄。

執行：

```powershell
.\.venv\Scripts\python.exe -B -m pytest `
  tests\test_recommendation_historical_replay.py `
  tests\test_ml_historical_snapshot_provider.py `
  tests\test_r026_calibration_legacy_preparation_baseline.py::test_provider_load_pins_query_window_and_rejects_concurrent_commit `
  tests\test_r026_calibration_legacy_preparation_baseline.py::test_provider_detects_commit_between_version_baseline_and_revision_precheck `
  -q -o addopts= -p no:cacheprovider --basetemp C:\t\r026_histreplay_final_37a6ac6d\pytest
```

結果：**18 passed**（1.59 秒）。pytest log SHA-256：`59F789FE77089B44C0D0FAF62060683091D19BAD7DA5228151E484ADF5C9CFAE`。Scoped mypy（provider 與 replay service）為 2 source files／0 issues；三個相關 Python 檔案 `py_compile` 通過；本測試檔 `git diff --check` 無 whitespace error（Git 顯示既有 LF/CRLF 轉換提示）。

## SHA-256 與限制

- `data_module/ml_historical_snapshot_provider.py`: `0223A3665B68DB950CF806D87F7C3CC3BBE925277813D083F7AFBB3A2A8E3928`
- `ml_module/recommendation_historical_replay.py`: `ABEFAD976DEDCBAA1396054452D56B0FC79E3DBDBD7C9602066B5B1A5501BAE2`
- `tests/test_recommendation_historical_replay.py`: `CCE2CCC3C4856DB6B20746BE3B71E6A3BAFA48BAF8C758BE6CD21FE59A29FC88`
- `qa/full_app_healthcheck/test_inventory.py`（原有 entry，未修改）: `D9A22C7F7EC2F579166F72FAB4E821FAC65B06E8D572D6F753D4616D5159E2F1`

Receipt sidecar checker 與各 SQLite provider call 是分開觀察；本測試不證明 sidecar 與 SQLite 同一原子版本。Trading-date enumeration、每個 decision snapshot、forward price window、source-contract read 與 observed-cost lookup 是多次讀取，這裡只驗各自的 cutoff 與單次 provider read commit fail-closed，不驗整次 replay 共用 durable generation、跨呼叫原子性或 ABA。R026／`TMP-ML-01` 仍未完成。

## 獨立複核與 bounded acceptance

R027 依凍結 test SHA-256 `CCE2CCC3C4856DB6B20746BE3B71E6A3BAFA48BAF8C758BE6CD21FE59A29FC88` 獨立複核，fresh TEMP route **18 passed**，未發現 P1/P2；root 判此 per-call characterization 為 bounded `ACCEPTED_SCOPE`。接受範圍只涵蓋本 note 列出的 synthetic 行為，不代表整輪 historical replay 已固定在同一 SQLite generation。

限制作為 gate 明示：fixture 每個日曆日都有人造價格列，不能代表真實交易日曆；未注入 `load_forward_price_window()` 進行中的 commit；沒有證明整輪多次 provider calls 共用 durable generation，也沒有 sidecar／SQLite 原子性。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## 後續 supported handoff 狀態（2026-10-10）

上列 `TMP-ML-01` 是本 per-call cutoff 收據的 2026-09-25 checkpoint。依 [R026 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md)，後續 `CLOSED` 的遷移條件限正常 `RecommendationService` NP1／NP2 supported caller/profile；本收據的 per-call cutoff 與鄰接文件記錄的 `RecommendationHistoricalReplayService` whole-replay lease 是不同證據，不因此宣稱 historical replay 共用 durable generation 或完成 R026。R026 整體仍 `IN_PROGRESS`。
