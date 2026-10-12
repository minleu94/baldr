# Gemini Wave 1 並行唯讀分析原文

> 此檔保存使用者帶回的 Gemini 分析原文；分析發生於 Luna 回修期間，不是 R003／R005／R006 的正式 PASS review。SOL 對照與處置見 `WAVE1_GEMINI_PARALLEL_ANALYSIS_INTAKE.md`。
> 原文中的 `file:///C:/...` 連結只適用原 Windows 工作區；可攜的規格入口為 [R003](../REFACTOR_TASKS/R003.md)、[R005](../REFACTOR_TASKS/R005.md)、[R006](../REFACTOR_TASKS/R006.md)，後續判讀仍以具名 SOL 整合審查為準。

# Gemini Wave 1 唯讀獨立驗收分析報告

> **任務識別碼**：`WAVE1_PARALLEL_ANALYSIS`  
> **執行模式**：唯讀分析（STRICTLY READ-ONLY；不修改任何檔案、不 stage/commit、不以變動中的工作樹為最終 diff）  
> **分析標的**：[R003](../REFACTOR_TASKS/R003.md)、[R005](../REFACTOR_TASKS/R005.md)、[R006](../REFACTOR_TASKS/R006.md) 之原始規格、SOL `CHANGES_REQUIRED` 發現、production 實際行為與驗收 oracle。

---

## 一、R003：Terminal Outcome、取消與 Hidden-State 特徵化分析

### 1. R003 驗收矩陣

| 規格條款 | 可觀察 Oracle | 建議 Fixture / Source Seam | 對應測試路由 | 現有證據或缺口 | 是否屬原 Scope |
|---|---|---|---|---|---|
| **五種終端狀態分離**（非僅以 `[]` 區分） | - **completed-nonempty**: worker `finished` signal，回傳非空 DTO 清單，UI 呈現數據。<br>- **completed-empty**: worker `finished` signal，回傳空清單，UI 顯示「結果未就緒：目前沒有符合條件的股票...」。<br>- **validation rejection**: 呼叫前 `request.validation_error()` 回傳字串，worker 不啟動、service 不被呼叫。<br>- **failed**: worker `error` signal 發射，UI 進入錯誤處理，不發射 `finished`。<br>- **cancelled**: worker `cancelled` signal 發射，UI 顯示「已取消：沒有套用部分結果...」。 | [RecommendationExecutionRequest](../../../../ui_qt/views/recommendation/execution_coordinator.py#L64) + `ProgressTaskWorker` + Service Spy | `tests/test_recommendation_execution_state_characterization.py` | **缺口**：Luna 先前測試以 `[]` 同時代表 completed-empty 與 cancelled；Fake service 缺乏 error/cancel 事件區分。 | **是** |
| **合作式取消與進度形狀** | - 取消請求在開始前返回：`execute` 回傳 `[]`，進度記錄「已取消：推薦分析尚未開始 (10%)」。<br>- 取消請求在執行後返回：進度記錄「已取消：推薦分析結果未套用 (90%)」。<br>- `detailed_progress=True` 時依序發布 10% → 25% → 35% → 90% → 100% checkpoint。 | `RecommendationExecutionRequest.execute(cancellation_callback=...)` + progress spy | `tests/test_recommendation_execution_coordinator.py`、`tests/test_recommendation_execution_state_characterization.py` | **現有證據**：coordinator 已有基礎取消分支；**缺口**：缺少詳細進度下的完整形狀與時序驗證。 | **是** |
| **Stale UI Callback 與 Last-Good 保護** | 當 Request A 正在執行，使用者發起 Request B，或 A 被取消後延遲抵達，A 的回傳 signal 不得覆寫 B 的畫面，也不得清除現存的 last-good 結果。 | [RecommendationView](../../../../ui_qt/views/recommendation_view.py#L2050) 的 `_on_recommendation_finished`、`_on_recommendation_cancelled` | `tests/test_recommendation_execution_state_characterization.py` | **現況重大 GAP**：目前 `RecommendationView` 在每次執行開始時無條件將 `self.current_recommendations = None`，且無 generation/request token；舊 callback 抵達會無條件套用。應作為現況 gap 記錄，不得改 production。 | **是**（Characterization） |
| **Worker 生命週期與關閉** | Worker 在 completion、cancel 或 error 終端狀態後，其 Qt native thread 結束（`isFinished() == True`, `isRunning() == False`），並觸發 `deleteLater` 註冊或受管 registry 解除。 | `ProgressTaskWorker` / `TaskWorker` 生命週期 seam | `tests/test_recommendation_execution_state_characterization.py` | **缺口**：原測試案例名稱宣稱 worker close，但未斷言 `deleteLater` 或 native thread 狀態。 | **是** |
| **同一服務 A/B 交錯與 Hidden-State 污染** | 對「同一個」`RecommendationService` 實例連續執行 A 與 B，在 B 完成後延遲讀取 A 當時的狀態；驗證 service 上的 `last_*` 是否被 B 覆寫。 | 具備 `last_*` 屬性的同一 service 實例 | `tests/test_recommendation_execution_state_characterization.py` | **缺口**：Luna 先前使用兩個獨立的 FakeService 實例，掩蓋了同一服務上的 state mutation 缺陷。 | **是** |
| **Nested Mutable Alias 隔離** | (1) 呼叫前傳入巢狀 dict `config["patterns"]["selected"]`，建立 request 後外部修改原 dict，驗證 request 是否被連帶篡改。<br>(2) caller 取得回傳值後修改內部 list/dict，驗證是否影響 service 內部狀態。 | `RecommendationExecutionRequest` + nested config mutation | `tests/test_recommendation_execution_state_characterization.py` | **現有證據**：目前 request 僅持有原始 dict 參照，存在 mutable alias 漏洞（已確認為 GAP）。 | **是** |
| **ML Receipt Side-Effect 可見順序** | 當分析任務在中途 cancel 或失敗時，驗證已產生的 ML receipt side-effect 是否保持可見、維持發布順序，且該 receipt 不會被偽造為 completed。 | Fake receipt spy / `recommendation_inference_provenance` seam | `tests/test_recommendation_execution_state_characterization.py` | **缺口**：先前未建立 receipt side-effect 觀測 oracle。 | **是** |

### 2. R003 假陽性風險與可區分負例

- **假陽性案例 1：僅斷言 `result == []` 即判定取消與零候選相容**
  - **為何不證明相容**：零候選（completed-empty）是正常業務結果；合作式取消（cancelled）是用戶中斷；未捕獲異常也可能回傳空值。如果只斷言回傳值是 `[]`，當取消邏輯完全失效或直接 crash 吞掉異常時，測試依然全綠，完全無法驗證 [INV-09](../FINAL_ARCHITECTURE_INVARIANTS.md#L15) 的狀態區分。
  - **可區分的負例**：斷言事件與信號流。對於 completed-empty，worker 發射 `finished`，progress 到達 `("分析完成", 100)`，UI 顯示「結果未就緒...」；對於 cancelled，worker 發射 `cancelled`，progress 停在 `("已取消：...", 10)` 或 90%，UI 顯示「已取消：沒有套用部分結果...」。若兩者信號或 label 顛倒，負例必須報錯失敗。
- **假陽性案例 2：使用兩個獨立的 FakeRecommendationService 實例測試 A/B 執行**
  - **為何不證明相容**：兩個實例在記憶體中完全隔離，A 的執行絕不可能污染 B。但真實系統中，同一 `RecommendationView` 共享同一個 `RecommendationService`，底層含有 `self.last_config`、`self.last_results` ([INV-10](../FINAL_ARCHITECTURE_INVARIANTS.md#L16))。雙實例測試製造了「系統已支援無狀態交錯」的假象，掩蓋了嚴重的狀態競爭風險。
  - **可區分的負例**：必須使用**同一個** service 實例，在 A 執行中途或完成後立即啟動 B，隨後讀取該 service 的 `last_*`。斷言其在現況下會被 B 改寫（記錄為現況 gap 證據），或在 target 契約下斷言 caller A 拿到的 execution DTO 仍保留 A 的獨立 identity 與 config。
- **假陽性案例 3：僅調用 `worker.wait()` 即宣稱 Worker 已 Close**
  - **為何不證明相容**：`wait()` 僅代表執行緒函式回傳，不代表 QObject 已執行 `deleteLater()`，也不代表 native C++ resource 已釋放或從管理容器解註冊。
  - **可區分的負例**：檢查 worker 是否發出 `destroyed` 信號，或驗證其 C++ wrapper 是否在事件循環後標記為 deleted。

### 3. R003 Scope 風險與 SOL 處置建議

- **允許檔案範圍**：僅限 `tests/test_recommendation_execution_state_characterization.py` 與 `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R003_IMPLEMENTATION_REPORT.md`。
- **Scope 邊界衝突風險**：
  1. *Production Mutation 風險*：Luna 若為了解決 mutable alias 而去修改 `ui_qt/views/recommendation/execution_coordinator.py`（例如強制加入 `deepcopy` 或改為 frozen dataclass），或修改 `ui_qt/views/recommendation_view.py`（加入 request token 或 last-good 快取），將嚴重超出 R003 範圍（R003 是純 Characterization 任務，OUT OF SCOPE 明定不得改 cancel 行為、不得改 UI、不得改 service state）。
  2. *跨 Task 權責衝突*：建立統一結果契約、Generation Token 與深凍結是 Wave 2 的 R008 / R011 之責任。
- **SOL 處置建議**：
  - 嚴格比對 git diff，若發現任何 `ui_qt/` 或 `app_module/` 的 production 變更，立即判定 REJECTED / CHANGES_REQUIRED。
  - 要求 Luna 將所有違反 [INV-07](../FINAL_ARCHITECTURE_INVARIANTS.md#L13)–[INV-10](../FINAL_ARCHITECTURE_INVARIANTS.md#L16) 的現況行為（如缺少 request token、mutable alias 污染、`last_*` 覆寫）忠實記錄為「現況 GAP」，並在實作報告中列入交接清冊，絕不可在 R003 提前修復 production。

### 4. R003 測試路由 (`V-EXEC`)

- **Focused 測試命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_state_characterization.py -v -o addopts=
  .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_coordinator.py -v -o addopts=
  .\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_p2_status_accessibility.py -k "recommendation" -v -o addopts=
  ```
- **執行狀態聲明**：因 Luna 正在同目錄平行寫入回修，本分析階段**不對變動中的檔案執行 PASS 判定**；上述測試路由為 SOL 驗收時之強制執行集。

---

## 二、R005：Replay／Portfolio Replay 特徵化分析

### 1. R005 驗收矩陣

| 規格條款 | 可觀察 Oracle | 建議 Fixture / Source Seam | 對應測試路由 | 現有證據或缺口 | 是否屬原 Scope |
|---|---|---|---|---|---|
| **Mode 責任邊界劃分**（更正差異表） | 報告與測試明確分離：[RecommendationService](../../../../app_module/recommendation_service.py)（互動推薦、即時庫與完整 pipeline）vs [RecommendationDataFrameProvider](../../../../app_module/recommendation_dataframe_provider.py#L13)（歷史回測/重播記憶體資料評估器）vs [RecommendationReplayService](../../../../app_module/recommendation_replay_service.py#L13)（Snapshot 時間切割與 availability 包裝）。 | 文件與測試宣告明確分帳 | `R005_IMPLEMENTATION_REPORT.md`、`tests/test_recommendation_replay_characterization.py` | **缺口**：Luna 先前將 `RecommendationDataFrameProvider` 誤稱為 interactive mode。 | **是** |
| **Future Append 與 Cutoff 穩定性** ([INV-05](../FINAL_ARCHITECTURE_INVARIANTS.md#L11)) | 給定截止日 T0，在歷史 DataFrame 追加 T0 之後的資料（含未來行情與新行），重新執行 `run_snapshot(as_of_date=T0)`，產生的 DTO 之 recommendations、scores、ordered symbols 與 diagnostics 與未追加前 100% 精確一致。 | 小型 deterministic 歷史 DataFrame fixture + 追加未來 rows | `tests/test_recommendation_replay_characterization.py` | **缺口**：先前測試使用每次回傳固定 85.0 分的 mock 且只查單一標的，無法證明完整 snapshot 與排序不受未來資料污染。 | **是** |
| **Available Date 拒絕與 Diagnostics 統計** ([INV-05](../FINAL_ARCHITECTURE_INVARIANTS.md#L11)) | 當輸入含有 `available_date` 欄位：<br>(a) `available_date > as_of_ts` 被剔除。<br>(b) `available_date.isna()` 被剔除。<br>(c) 剔除筆數計入 `diagnostics: ["unavailable_rows_excluded:N"]`。<br>(d) 被剔除之標的絕不進入最終 recommendations。 | 帶有未到期、過期、NaN 之 `available_date` 的 deterministic DataFrame | `tests/test_recommendation_replay_characterization.py` | **缺口**：先前測試只斷言 diagnostics 字串存在，未斷言被拒絕的 row 是否真正未進入推薦名單。 | **是** |
| **Numeric YYYYMMDD 日期解析** | `日期` 欄位為整數型態（如 `20260922`）或字串型態均能正確被 `parse_stock_dates` 解析為 Timestamp，且 cutoff 正常運作。 | 整數與字串混合的歷史資料 fixture | `tests/test_recommendation_replay_characterization.py` | **缺口**：先前測試未涵蓋數值型 `YYYYMMDD` 的相容性驗證。 | **是** |
| **Lookback 80 / Max Stocks 200 / Min Rows 20** | (a) 早於 `latest_date - 80 days` 的資料被截斷。<br>(b) 超過 200 檔標的時只取前 200 檔 unique 代碼。<br>(c) 該個股歷史筆數 `< 20` 筆時被略過（不進入推薦）。 | 構造 10 筆 vs 25 筆個股切片、205 檔標的之 DataFrame | `tests/test_recommendation_replay_characterization.py` | **缺口**：先前缺少邊界條件之正反例斷言。 | **是** |
| **Fast Filters (漲跌幅與成交量濾網)** | (a) `price_change_min/max` 比對倒數前兩筆價差百分比，不符者剔除。<br>(b) `volume_ratio_min` 經 `_normalize_volume_threshold` 轉換後比對最新量相對於 MA20 之比例，不足 21 筆或不符者剔除。 | 構造剛好低於/高於門檻之 2 筆價格與 21 筆成交量序列 | `tests/test_recommendation_replay_characterization.py` | **缺口**：先前缺少 fast filter 數值邊界的正反例測試。 | **是** |
| **Score Fallback 與 Per-Stock Exception Skip** | (a) 無 `FinalScore` 時回退取 `TotalScore` → `綜合評分` → 0。<br>(b) 某檔股票計算拋出 Exception 時，provider 捕獲並略過，其餘正常股票仍正常輸出，不中斷整體執行。 | 包含無 FinalScore 欄位及拋出異常的混合股票 DataFrame | `tests/test_recommendation_replay_characterization.py` | **缺口**：先前測試未驗證異常隔離與 fallback 排序。 | **是** |
| **既有 Portfolio Replay / Factor Manifest 相容** ([INV-13](../FINAL_ARCHITECTURE_INVARIANTS.md#L19)) | 執行既有 portfolio backtest、replay date、factor manifest suites，確認既有回測合約與 stored annotation 未受破壞。 | 既有 portfolio / replay 測試集 | `tests/test_recommendation_historical_replay.py` 等 | **缺口**：先前報告未完整記錄 V-REPLAY focused suites 的執行結果。 | **是** |

### 2. R005 假陽性風險與可區分負例

- **假陽性案例 1：使用固定回傳 `FinalScore=85.0` 的 Mock StrategyConfigurator 測試 Future Append**
  - **為何不證明相容**：若 Mock 永遠回傳寫死的一筆資料與固定分數，無論你在 DataFrame 中塞入多少筆未來日期的漲停數據，Mock 根本沒有讀取資料的時間截斷，永遠輸出同樣的分數。這完全無法檢驗 `RecommendationReplayService` 是否有真正執行 `data["日期"] <= as_of_ts` 的 cutoff，也無法檢驗 provider 是否使用了未來資料（Look-ahead bias）。
  - **可區分的負例**：使用能如實反映輸入資料的真實 `RecommendationDataFrameProvider`（或對輸入行數/最大日期敏感的 Mock）。在 T0+1 加入極高價格（如漲停 1000 元）；若 cutoff 正常，T0 的評分保持原樣；若 cutoff 失敗（負例），T0 的評分或最新一筆價格會被未來資料竄改，導致測試失敗。
- **假陽性案例 2：僅斷言 `diagnostics` 包含 `"unavailable_rows_excluded:1"`，未驗證推薦名單內容**
  - **為何不證明相容**：字串出現在 diagnostics 只能證明計數判斷有執行，不能證明該 row 真的被從 `data` 中過濾掉。若底層程式碼寫了 `diagnostics.append(...)` 但漏寫了 `data = data[~rejected]`，未到期的未來資料依然會流入後續的推薦計算中，造成嚴重的未來函數。
  - **可區分的負例**：構造兩檔股票，股票 A 的最新資料之 `available_date` 在未來（不應可得），股票 B 的 `available_date` 在決策當日前（可得）。斷言最終 `snapshot.recommendations` 中「絕對不能包含股票 A」，且僅包含股票 B；若股票 A 出現在推薦名單中（負例），斷言失敗。
- **假陽性案例 3：使用待重構的舊 helper 自行生成結果作為 Golden**
  - **為何不證明相容**：當被測程式碼與 helper 共享相同的缺陷時，兩者必然相等，即使計算邏輯本身有誤或產生 Look-ahead 也不會被發現。
  - **可區分的負例**：使用手工構造、可人工推導驗算的獨立 expected values 進行精確比較。

### 3. R005 Scope 風險與 SOL 處置建議

- **允許檔案範圍**：僅限 `tests/test_recommendation_replay_characterization.py` 與 `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R005_IMPLEMENTATION_REPORT.md`。
- **Scope 邊界衝突風險**：
  1. *Production Mutation 風險*：Luna 若試圖去修改 `app_module/recommendation_dataframe_provider.py`（例如修改其吞掉 exception 的行為，或改寫 fast filter 閾值口徑）或修改 `app_module/recommendation_replay_service.py`，將違反「不可更動 production provider/evaluator」限制。
  2. *過早統一 Evaluator 風險*：消除 interactive 與 replay 差異、共用 evaluator 是 Wave 5/7（R017/R020）的任務。若 Luna 在此時試圖抹平兩者差異，會直接破壞既有 replay 回測行為。
- **SOL 處置建議**：
  - 嚴格比對 git diff，確保零 production 變更。
  - 確保報告中將「per-stock exception 吞掉錯誤」、「lookback 80 日硬編碼」、「fast filter 命名口徑」列為現況特徵與 R017/R020 handoff 清冊，而不是當前修補項目。

### 4. R005 測試路由 (`V-REPLAY`)

- **Focused 測試命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_replay_characterization.py -v -o addopts=
  .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_historical_replay.py -v -o addopts=
  .\.venv\Scripts\python.exe -m pytest tests/test_backtest_timeline_contract.py -v -o addopts=
  .\.venv\Scripts\python.exe -m pytest tests/test_backtest_factor_metadata.py -v -o addopts=
  .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_portfolio_backtest.py -k "dates or replay or manifest" -v -o addopts=
  ```
- **執行狀態聲明**：因 Luna 正在平行回修，本分析階段不標註測試為 PASS；上述測試路由為 SOL 驗收時之強制執行集。

---

## 三、R006：ML Compatibility／Artifact ABI 基線分析

### 1. R006 驗收矩陣

| 規格條款 | 可觀察 Oracle | 建議 Fixture / Source Seam | 對應測試路由 | 現有證據或缺口 | 是否屬原 Scope |
|---|---|---|---|---|---|
| **15 條 Direct Computation Dependency 路徑之清冊與責任分帳** | (a) 15 條路徑逐項存在且計算其 source byte SHA-256。<br>(b) 責任歸屬於 [portfolio_ml_direct_numeric_store.py:122](../../../../data_module/portfolio_ml_direct_numeric_store.py#L122)（非 safe loader）。<br>(c) 明確分帳：持久 stable computation identity（路徑、byte SHA256、compiled fingerprint）vs runtime loaded-code integrity（進程載入 module/code/constants 不變性）。 | `data_module/portfolio_ml_direct_numeric_store.py` 的 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` | `docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md`、`tests/test_ml_direct_computation_dependency_guard.py` | **缺口**：Luna 先前在 QA 報告誤寫為由 `SafeShadowModelArtifactLoader` 綁定，且未提供逐條 byte SHA-256 清冊。 | **是** |
| **Historical 20 欄 Feature Registry ABI** ([INV-15](../FINAL_ARCHITECTURE_INVARIANTS.md#L21)) | 驗證 `CORE_LONG_HISTORY_FEATURE_REGISTRY`（`core-long-history-features-v1`）定義的 20 個特徵有序名稱、dtype、unit、None→NaN、imputer/scale 及 HGB missing mask。 | [ml_module/feature_registry.py](../../../../ml_module/feature_registry.py) 常數與受控小型 DataFrame | `tests/test_refactor_ml_compatibility_baseline.py`、`tests/test_ml_feature_label_registries.py` | **缺口**：Luna 先前使用虛構的 2 欄 `A/B float32` 測試，完全未覆蓋 20 欄真實 ABI。 | **是** |
| **OOC Binary Store ABI (v3)** ([INV-15](../FINAL_ARCHITECTURE_INVARIANTS.md#L21)) | 驗證 OOC store v3 的小端序（`<`）、欄位順序、型態（values `<i8`、mask `u1`、targets `<i4`、labels `<i4`、row refs `<i8`）、缺值 mask（缺=1、observed=0）、6 個 target fields 與 9 個 label fields。 | [data_module/portfolio_ml_out_of_core_store.py](../../../../data_module/portfolio_ml_out_of_core_store.py) + 受控小型 store fixture | `tests/test_refactor_ml_compatibility_baseline.py`、`tests/test_portfolio_ml_out_of_core_pipeline.py` | **缺口**：先前測試未映射 OOC binary 欄位結構。 | **是** |
| **Direct Store & Checkpoint Provenance (v4)** ([INV-15](../FINAL_ARCHITECTURE_INVARIANTS.md#L21)) | 驗證 `portfolio-ml-direct-numeric.v4`、checkpoint v2、carry v2，驗證 checkpoint resume 在 source identity 不變時被接受，在依賴檔案被改動時被拒絕。 | `data_module/portfolio_ml_direct_numeric_store.py` + checkpoint fixture | `tests/test_ml_direct_checkpoint_provenance_recovery.py` | **缺口**：先前測試僅測了 mock loader。 | **是** |
| **Safe Artifact Loader 邊界與 Unknown 資產政策** ([INV-18](../FINAL_ARCHITECTURE_INVARIANTS.md#L24)) | (a) 受控 repo fixture 經由 `SafeShadowModelArtifactLoader` 驗證其 manifest hash、family、library 白名單。<br>(b) 缺 sidecar 或 hash 不符者被拒絕（verified rejected）。<br>(c) 未知外部 pickle/joblib 保持為 `unknown`/`unsupported`，不反序列化、不 quarantine、不補 sidecar。 | [ml_module/model_artifact_loader.py](../../../../ml_module/model_artifact_loader.py) + repo 既有受控測試 fixture | `tests/test_refactor_ml_compatibility_baseline.py`、`tests/test_ml_model_artifact_loader.py` | **缺口**：Luna 先前以 lambda 注入 `DummyModel` 冒充真實 joblib 載入，並在報告中宣稱外部模型全數相容。 | **是** |
| **ML Shadow Dependency Boundary 既有 4 條違規記錄** | 執行 `tests/test_ml_shadow_dependency_boundary.py`，精確記錄 4 條既有 production→ML import 違規；報告中明確標記為既有已知 gap，不得修改 production，不得擅自修改測試的 allowlist 假造全綠。 | `tests/test_ml_shadow_dependency_boundary.py` | `tests/test_ml_shadow_dependency_boundary.py` | **現有證據**：SOL 先前重跑 69 passed, 1 failed，該 1 fail 即為此 guard（揭露 4 條既有 import）。 | **是** |

### 2. R006 假陽性風險、可區分負例與四層相容性分級

在 R006 中，必須對所有資產與相容性宣稱明確區分四層驗證狀態：
1. `source-declared`：僅在原始碼常數或契約中宣告（如 registry 常數、路徑清單、dataclass schema）。
2. `controlled-fixture verified`：在 `tests/fixtures/` 內的受控小型檔案，已透過 safe loader 或契約執行過成功/拒絕測試。
3. `artifact-readback verified`：磁碟上的真實正式資產，在唯讀模式下讀取其 header/manifest/bytes 並驗證 hash 一致。
4. `unknown` / `unsupported`：未載入、未檢查、無 sidecar 或缺乏安全審查的外部二進位資產。

- **假陽性案例 1：使用注入的 `deserializer=lambda path: DummyModel()` 測試 SafeShadowModelArtifactLoader，並宣稱歷史模型「Verified Compatible」**
  - **驗證層級歸屬**：此測試僅能歸為 `controlled-fixture verified`（針對 loader gate 的 manifest/hash 檢查邏輯），但對於模型本身只能歸為 `unknown`。
  - **為何不證明相容**：注入 lambda 繞過了 Python 的真實 pickle/joblib 反序列化機制。真實 joblib 檔案內部儲存了序列化時的 Python qualified class path。若 Python 環境升級、scikit-learn 版本變更或模組被重命名/移動，真實反序列化會拋出 `AttributeError` 或 `ModuleNotFoundError`。注入 lambda 永遠回傳 `DummyModel`，使得破損或 class path 斷裂的模型在測試中看似「載入成功」，造成嚴重的偽相容。
  - **可區分的負例**：對於受控 fixture，使用真實的 safe loader 呼叫（使用安全受控的合法 joblib fixture）；構造負例：破壞 fixture 的 class path 或提供畸形 binary，斷言 safe loader 必須捕獲並拒絕；對於外部正式資產，在報告中明確歸類為 `unknown / not deserialized`，絕不標註為 `Verified Compatible`。
- **假陽性案例 2：使用 2 欄 `A/B float32` 的虛構 DataFrame 測試 Feature Registry**
  - **驗證層級歸屬**：僅能歸為 `controlled-fixture verified`（證明 loader 能處理自定義 schema），但對於歷史特徵契約只能歸為 `source-declared`，未經驗證。
  - **為何不證明相容**：`CORE_LONG_HISTORY_FEATURE_REGISTRY` 擁有嚴格定義的 20 個特徵、精確的欄位順序、特定的數值單位與空值規則。使用隨機 2 欄進行測試，無法發現特徵欄位缺失、型態被隱式轉換為 float64、或缺失值被錯誤補零（違反 `missing_is_not_zero`）的問題。這會讓破壞 20 欄 ABI 的重大回退在測試中綠燈通過。
  - **可區分的負例**：直接引用 `CORE_LONG_HISTORY_FEATURE_REGISTRY` 的完整 20 個特徵定義建立驗證測試。構造負例：故意傳入 19 欄、欄位順序倒置、或將 None 當作 0 處理的輸入，斷言 feature builder 或 validator 必須拋出明確的 ABI 驗證錯誤。
- **假陽性案例 3：將 R001 的檔名統計（11,559 個 manifest、83,105 個序列化檔名）冒充為「已相容且隔離」**
  - **驗證層級歸屬**：此為檔名盤點（Census），僅屬 `source-declared` / metadata count，絕非 `artifact-readback verified`。
  - **為何不證明相容**：檔名存在不代表檔案內容完整、不代表 byte hash 符合 manifest、更不代表 schema 相容。
  - **可區分的負例**：報告必須如實標明：未逐檔讀取與驗證 hash 者，全數列為 `unknown/unsupported (retained as-is without mutation)`。

### 3. R006 Scope 風險與 SOL 處置建議

- **允許檔案範圍**：僅限 `tests/test_refactor_ml_compatibility_baseline.py`、`docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md` 與 `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`。
- **Scope 邊界衝突風險**：
  1. *Production Mutation 風險*：Luna 若試圖修改 `data_module/portfolio_ml_direct_numeric_store.py`（例如修改 15 條路徑清單）、`ml_module/model_artifact_loader.py` 或修改那 4 條產生 shadow import 的 production 檔案（`app_module/personalization_projection.py` 等），這嚴重違反架構凍結原則（[INV-01](../FINAL_ARCHITECTURE_INVARIANTS.md#L7)、[INV-14](../FINAL_ARCHITECTURE_INVARIANTS.md#L20)）。
  2. *越權處置風險*：R006 嚴格禁止反序列化未知 binary、禁止重訓、禁止重建 (rebuild) OOC/Direct store、禁止替正式資產補寫 sidecar、禁止宣稱正式模型已 quarantine。
  3. *測試放行風險*：為了讓 `test_ml_shadow_dependency_boundary.py` 通過而把 4 條違規加入 allowlist。
- **SOL 處置建議**：
  - 嚴禁更動任何 production 檔案與正式資料目錄。
  - 審查 diff 確認 15 條路徑未被刪改。
  - 確保報告中對外部模型的狀態如實標註為 `unknown`，不得越權授權重訓或補 sidecar。

### 4. R006 測試路由 (`V-ML-SMALL` / `V-ML-DIRECT`)

- **Focused 測試命令**：
  ```powershell
  # V-ML-SMALL
  .\.venv\Scripts\python.exe -m pytest tests/test_refactor_ml_compatibility_baseline.py -v -o addopts=
  .\.venv\Scripts\python.exe -m pytest tests/test_ml_historical_snapshot_provider.py tests/test_ml_feature_label_registries.py tests/test_ml_model_artifact_manifest.py tests/test_ml_model_artifact_loader.py -v -o addopts=

  # V-ML-DIRECT
  .\.venv\Scripts\python.exe -m pytest tests/test_ml_direct_computation_dependency_guard.py tests/test_ml_direct_checkpoint_provenance_recovery.py tests/test_ml_direct_numeric_shared_reuse.py -v -o addopts=

  # ML Shadow Boundary (確認既有 4 條違規維持 1 failed，不得掩蓋)
  .\.venv\Scripts\python.exe -m pytest tests/test_ml_shadow_dependency_boundary.py -v -o addopts=
  ```
- **執行狀態聲明**：因 Luna 正在平行回修，本分析階段不標註測試為 PASS；上述測試路由為 SOL 驗收時之強制執行集。

---

## 四、分析結論與狀態標記

本唯讀獨立分析已全數完成對 R003、R005、R006 的驗收矩陣、假陽性與可區分負例、Scope 風險界定及測試路由之建立，並已識別出關鍵假陽性盲點（如 R003 僅依賴 `[]` 與雙 FakeService、R005 固定分數 Mock 與未驗證名單過濾、R006 注入 DummyModel 與虛構 2 欄特徵）。後續正式 PASS 審查需待三位 Luna Max 之變更凍結後，由 SOL 與 Reviewer 依上述矩陣逐項比對實際 diff 進行。

```text
ANALYSIS_STATUS: COMPLETE
NEEDS_FINAL_DIFF_REVIEW: YES
```
