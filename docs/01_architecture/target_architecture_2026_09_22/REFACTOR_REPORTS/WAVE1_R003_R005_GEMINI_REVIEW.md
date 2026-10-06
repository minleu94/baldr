# Gemini 獨立審查報告：R003 與 R005 Luna 回修

---

# 第一部分：R003 獨立審查報告

## 一、審查基本資訊與凍結 SHA 核對

- **任務代號**：`R003` — terminal outcome、取消與 hidden-state characterization
- **審查角色**：獨立 Gemini Reviewer
- **基線 HEAD**：`391b057c92037ec7a19cab2bf951d6029d29b020`
- **審查模式**：唯讀審查（Strictly Read-Only；未修改任何檔案、未變更 production 程式碼）

### 受審兩檔凍結 SHA-256 驗證

| 檔案路徑 | SOL 凍結 SHA-256 | 目前磁碟實際 SHA-256 | 核對結果 |
|---|---|---|:---:|
| `tests/test_recommendation_execution_state_characterization.py` | `30C06A571301E732B60840AB2C73E2C17F0DC6488F606272082EF4CAF0B3AA11` | `30C06A571301E732B60840AB2C73E2C17F0DC6488F606272082EF4CAF0B3AA11` | **MATCH** |
| `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md` | `B39BB9A8BF415DE398C9C831DCDCFBE7D13E57715F619E8F63F1B94B5C082F09` | `B39BB9A8BF415DE398C9C831DCDCFBE7D13E57715F619E8F63F1B94B5C082F09` | **MATCH** |

兩檔 SHA-256 100% 精確吻合，無任何工作樹漂移。

---

## 二、R003 詳細審查發現（Findings）

### 1. 檔案與變更範圍邊界（Scope Compliance）
- **核准範圍遵循**：本輪修改僅限上述測試檔與實作報告。`git status` 確認零 production 原始碼修改、零資料寫入、零未授權檔案產生。
- **語法與格式驗證**：
  - `python -m py_compile tests/test_recommendation_execution_state_characterization.py` 通過（Exit Code: 0）。
  - `git diff --check` 通過，無任何 whitespace 或換行錯誤（Exit Code: 0）。

### 2. 五種終端狀態可判定 Oracle（非僅依賴 `[]`）
- **completed-nonempty vs completed-empty**（`test_completed_nonempty_and_empty_have_finished_signal_and_distinct_ui_state`）：
  - 兩者均發射 worker `finished` signal，`error` 與 `cancelled` 均為空。
  - nonempty 回傳正常推薦清單；empty 回傳 `[]`，實際 view callback 觸發 `QMessageBox.information` 並設定狀態標籤為「結果未就緒：目前沒有符合條件的股票...」，成功將合法零候選與取消/失敗分開。
- **validation rejection**（`test_validation_rejection_is_preflight_event_without_worker_or_service_call`）：
  - 在 `RecommendationView._execute_recommendation` 階段由 `RecommendationExecutionRequest.validation_error()` 攔截，彈出 warning，service 呼叫數為 0，且完全不建立 worker，證明為 preflight 拒絕事件。
- **raised failure**（`test_raised_failure_emits_error_and_ui_marks_failed`）：
  - service 拋出異常時，worker 發射 `error` signal，`finished` 與 `cancelled` 均未發射，UI 狀態標記為「失敗」，狀態文字標記為「分析未完成」。
- **cooperative cancellation**（`test_cooperative_cancel_after_fake_receipt_emits_cancelled_only`）：
  - 收到取消請求後，worker 發射 `cancelled` signal，`finished` 與 `error` 均未發射，UI 狀態標記為「已取消」。

### 3. 取消與進度形狀（Progress Shape）
- **pre-start cancellation**（`test_pre_start_cancellation_returns_empty_without_call_and_emits_exact_progress`）：
  - 開始前取消精確發射 `("讀取股票數據...", 10)` 與 `("已取消：推薦分析尚未開始", 10)`，service 呼叫數為 0。
- **post-service cancellation checkpoint**（`test_request_emits_post_service_cancel_progress_checkpoint`）：
  - service 返回後取消精確發射 `("已取消：推薦分析結果未套用", 90)`。
- **詳細模式進度**（`test_progress_callback_shape_and_worker_lifecycle_are_observable`）：
  - 完整覆蓋 10% → 25% → 35% → 60% → 90% → 100% 序列。

### 4. 同一服務 A/B 執行與 Stale UI Callback GAP 記錄
- **同一服務實例狀態覆寫**（`test_same_service_ab_and_late_real_ui_callback_expose_shared_state_gap` & `test_real_recommendation_service_last_context_is_latest_instance_state`）：
  - 使用**同一個** service 實例，A 完成後啟動 B，service 的 `last_run_context` 即被 B 覆寫為 B config。
  - 當延遲的 A callback 抵達 `RecommendationView._on_recommendation_finished`，由於目前回呼簽章僅有 `(self, recommendations)`，無 request generation token，A 的結果直接覆寫了已顯示的 last-good 模型。
  - **判定**：此測試忠實揭露並固定了現行實作違反 INV-07（開發參考）、INV-09（開發參考）、INV-10（開發參考） 的現況缺陷，並在報告中完整登記為 R008/R011 的交接項目，未在 R003 偷改 production。

### 5. Last-Good 清除時機現況 GAP
- **新請求啟動前清空**（`test_new_request_clears_last_good_view_before_worker_start`）：
  - 證明現況下 `RecommendationView._execute_recommendation` 在 `worker.start()` 之前就已將 `results_table.setModel(None)`、清空 detail 及將 `current_recommendations` 設為 `None`。此行為亦作為現況 gap 記錄。

### 6. Worker 生命週期（Lifecycle & Close）
- **Deferred Delete 與 Registry 清理**（`test_delete_later_waits_for_native_thread_completion_and_registry_cleanup`）：
  - 斷言了 `worker.deleteLater()` 標記 `_delete_later_requested == True`，等待 native thread 結束後，worker 從 `_MANAGED_TASK_WORKERS` 及 `_LIVE_TASK_WORKERS` 中移除，且 QObject 的 `destroyed` signal 成功發送。

### 7. Nested Mutable Alias 現況 GAP
- **輸入與輸出兩側的別名修改**（`test_nested_input_and_returned_value_aliases_are_visible_gaps`）：
  - 外部修改 config 會直接反映到 request 內部；caller 修改回傳清單會直接反映到 service 內部快取。已依 INV-08（開發參考） 將此缺陷標記為現況 gap。

---

## 三、R003 測試執行結果

### 1. 單檔特徵化測試執行
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_state_characterization.py -q -o addopts= -p no:cacheprovider
```
- **執行結果**：`13 passed in 0.72s`（Exit Code: 0）。

### 2. V-EXEC 完整聚焦測試套件執行
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py tests/test_ui_qt_task_worker.py tests/test_ui_qt_shutdown_coordinator.py "tests/test_ui_qt_portfolio_view.py::test_portfolio_stale_worker_callback_cannot_replace_new_generation" -q -o addopts= -p no:cacheprovider
```
- **執行結果**：`41 passed in 1.73s`（Exit Code: 0）。

---

# 第二部分：R005 獨立審查報告

## 一、審查基本資訊與凍結 SHA 核對

- **任務代號**：`R005` — replay／portfolio replay characterization
- **審查角色**：獨立 Gemini Reviewer
- **基線 HEAD**：`391b057c92037ec7a19cab2bf951d6029d29b020`
- **審查模式**：唯讀審查（Strictly Read-Only；未修改任何檔案、未變更 production 程式碼）

### 受審兩檔凍結 SHA-256 驗證

| 檔案路徑 | SOL 凍結 SHA-256 | 目前磁碟實際 SHA-256 | 核對結果 |
|---|---|---|:---:|
| `tests/test_recommendation_replay_characterization.py` | `F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21` | `F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21` | **MATCH** |
| `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md` | `14BE9F9E0E5F796E3E59A2AF3FB12A6D030EF38AC14113BE97D4FDD2C75DAF1F` | `14BE9F9E0E5F796E3E59A2AF3FB12A6D030EF38AC14113BE97D4FDD2C75DAF1F` | **MATCH** |

兩檔 SHA-256 100% 精確吻合，無任何工作樹漂移。

---

## 二、R005 詳細審查發現（Findings）

### 1. 檔案與變更範圍邊界（Scope Compliance）
- **核准範圍遵循**：本輪修改僅限上述測試檔與實作報告。零 production 原始碼修改、零正式資料庫寫入。
- **語法與格式驗證**：
  - `python -m py_compile tests/test_recommendation_replay_characterization.py` 通過（Exit Code: 0）。
  - `git diff --check` 通過，無任何 whitespace 或換行錯誤（Exit Code: 0）。
- **R001 路徑勘誤確認**：
  - R001 先前記錄之舊路徑 mismatch 已在 R001 清冊修正，依本次 prompt 指示，不將該歷史追溯記錄視為 R005 failure。目前 HEAD 正確對應至 `app_module/recommendation_replay_service.py` 與 `app_module/recommendation_dataframe_provider.py`。

### 2. Mode 責任劃分與差異表更正
- 報告與測試明確分離：
  - `RecommendationService`（互動式推薦，具獨立 PIT/cutoff 與 calibration 管道）。
  - `RecommendationDataFrameProvider`（回測與重播專用之 legacy 記憶體 DataFrame 評估器）。
  - `RecommendationReplayService`（回測外層 Snapshot 切割與 availability 排除包裝）。
  - 未將 DataFrame provider 誤稱為互動推薦，各 mode 責任清晰。

### 3. Future Append 與 Cutoff 穩定性（INV-05（開發參考））
- **非固定常數 Mock 驗證**（`test_replay_full_snapshot_is_exact_and_future_append_does_not_change_it`）：
  - 採用 `_ScoreFromFixture` 讀取資料內的 `oracle_score`（A 股 85 分、B 股 91 分），並在追加的未來 rows 注入 999 與 1000 之極端分數。
  - 追加前後之 `RecommendationSnapshotDTO`（包含 recommendations、factor scores、config、as_of_date、diagnostics）逐欄位 100% 精確一致，證明時間截斷生效且不受未來資料污染。

### 4. Available Date 排除與 Diagnostics 統計（INV-05（開發參考））
- **逐列 Cutoff 且非整股 Veto**（`test_replay_availability_cutoff_excludes_missing_and_future_availability_before_provider`）：
  - 含有 `available_date` 欄位時，晚於決策日或 NaN 的列被剔除，並計入 `diagnostics: ["unavailable_rows_excluded:2"]`。
  - 當先前仍有 20 列有效資料時，該股票不會被整股否定，仍能以歷史有效資料參與推薦評分。

### 5. 數字 `YYYYMMDD` 日期解析與邊界
- 全數測試皆透過 `_yyyymmdd()` 生成整數格式日期（如 `20260812`），驗證 `RecommendationDataFrameProvider._normalize_columns` 與 `RecommendationReplayService` 皆能正確解析為 Timestamp。

### 6. Lookback (80)、Max Stocks (200) 與 Min Rows (20)
- **Lookback 邊界**（`test_dataframe_provider_default_and_configurable_lookback_use_calendar_days`）：
  - 預設 80 天及自訂 10 天日曆日，第 81 天與第 11 天資料精確被過濾。
- **Max Stocks 截斷**（`test_dataframe_provider_default_and_configurable_max_stocks_keep_first_seen_codes`）：
  - 201 檔股票輸入時，預設精確保留前 200 檔首次出現之代碼。
- **最低筆數限制**（`test_dataframe_provider_skips_short_history_and_price_filter_rejects_before_scoring`）：
  - 歷史資料少於 20 筆時直接略過。

### 7. 價量 Fast Filters 精確數值邊界
- **成交量濾網**（`test_dataframe_provider_volume_fast_filter_has_a_fixed_boundary`）：
  - `volume_ratio_min: 1.5` 門檻下，成交量 1500 剛好通過，1490 精確拒絕。
- **漲跌幅濾網上界**（`test_dataframe_provider_price_change_max_keeps_exact_limit_and_rejects_above`）：
  - 前收 100、現收 110（漲幅 10.00%）在 `price_change_max: 10` 邊界通過；現收 110.01（漲幅 10.01%）精確超限被拒。

### 8. 分數回退、排序與個股例外靜默跳過
- **分數回退順序**（`test_dataframe_provider_preserves_score_fallback_priority_stable_ties_and_top_n`）：
  - 依序回退：`FinalScore` → `TotalScore` → `綜合評分` → 0.0，且同分保持穩定排序。
- **個股例外隔離**（`test_per_stock_exception_is_silent_and_factor_manifest_only_contains_survivors`）：
  - 當某檔個股計算異常時，provider 捕獲異常並靜默跳過，其餘正常個股仍正常輸出，factor manifest 僅包含存活股票。

### 9. Portfolio Factor Manifest 與 Annotation 保持
- **Factor Manifest 凍結**（`test_portfolio_replay_pins_outer_snapshot_dates_and_factor_manifest`）：
  - 完整固定 `factor_snapshot` 與 `factor_contributions` 之數值、單位、bp 縮放與資料結構。
- **Annotation 透傳**（`test_replay_wrapper_preserves_provider_annotation_payload`）：
  - 驗證 replay wrapper 原樣保留 provider 回傳之 `stored_annotation` payload。

---

## 三、R005 測試執行結果

### 1. 單檔特徵化測試執行
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_replay_characterization.py -q -o addopts= -p no:cacheprovider
```
- **執行結果**：`13 passed in 0.85s`（Exit Code: 0）。

### 2. V-REPLAY 完整聚焦測試套件執行
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_replay_characterization.py tests/test_historical_evidence_replay.py tests/test_recommendation_historical_replay.py tests/test_recommendation_portfolio_backtest.py tests/test_backtest_timeline_contract.py -q -o addopts= -p no:cacheprovider
```
- **執行結果**：`66 passed, 24 warnings in 2.98s`（Exit Code: 0）。
- **說明**：24 個 warning 均為 `recommendation_portfolio_backtest_service.py` 內部原有之「同日收盤訊號同日收盤成交」研究假設提示（UserWarning），非測試失敗。

---

## 四、審查總結與判定

1. **R003**：完整固定了五種終端狀態可觀察事件序列，成功揭露並記錄了同一服務 A/B 執行狀態覆寫、stale UI callback 無 request correlation token、啟動前清除 last-good 以及 nested mutable alias 等現行系統 GAP。無 production 修改，符合原任務 Characterization-only 要求。
2. **R005**：更正了 mode difference table 的責任歸屬，全面涵蓋 Future Append、可用日期逐列過濾、Lookback/Max Stocks/Min Rows 邊界、價量 Fast Filters 精確極限、分數回退、個股例外隔離及 Factor Manifest，成功固定 legacy replay 語意供 R017/R020 接續重構。無 production 修改。

本獨立審查確認 R003 與 R005 之 Luna 回修皆已完全符合驗收標準，判定為 PASS。

REVIEW_STATUS: PASS
