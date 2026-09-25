# R018 推薦 input preparation／provider 抽離實作報告

## 狀態與範圍

- TASK：R018 Recommendation input preparation／provider extraction
- 狀態：`ACCEPTED_SCOPE`
- 獨立 reviewer：6 模組 fresh TEMP `56 passed`、未見 P1/P2，建議 `ACCEPTED_SCOPE`
- Root scope gate：`ACCEPTED_SCOPE`；不代表 Wave 7 release、正式資料 acceptance 或 TMP-REC-01 retirement
- 依賴：R007、R011、R013–R017
- 實作邊界：app 明示解析及準備推薦輸入；data adapters 唯讀來源 facts；RecommendationService 保留決策與排名規則
- 未觸碰：正式資料、正式 SQLite、保存 writer、UI/replay 算法、ranking/filter/factor/reason 規則、ML frozen provider/read timing、technical publication

工作開始時共享工作樹已含多個其他任務的未提交變更。本文只列 R018 自有行為與路徑，不把整份 dirty diff 歸因於 R018；未 stage 或 commit。

## Source owner、fallback 與 read contract

| 輸入 | 新 owner 與呼叫位置 | 保留的時序／fallback／錯誤語意 |
|---|---|---|
| 即時市場 frame | `app_module/recommendation_market_data_provider.py::DefaultRecommendationMarketDataProvider`；由 app composition 建立並注入 preparer | 保留原即時 provider contract；若 service 明示替換 provider，execute 在每次 invocation 將同一 provider 綁入該次 session，不改共享 preparer state。 |
| 歷史市場 frame | `data_module/recommendation_input_providers.py::HistoricalRecommendationMarketFrameProvider` | SQLite 仍 query-only，讀 `daily_prices` 與可選 `technical_indicators` join、60 日窗口；非 SQLite 路徑優先 `all_stocks_data_file`，不存在才讀 `stock_data_file`。缺 SQLite 不會建立檔案。 |
| cutoff、日期與 market identity | `app_module/recommendation/input_preparation.py` | 保留 explicit/historical/latest request tuple、日期解析、market date cutoff、逐列 `available_date` cutoff、相同 `stock/date` 修訂選擇、universe filter、source ID、market fingerprint 與 data date。正規化後的空 frame 立即早退，無日期欄也保留舊 empty fingerprint/context。 |
| PIT industry membership | `data_module/recommendation_input_providers.py::PITRecommendationMembershipProvider` | 保留決策日期、decision clock、market scope；reader error 回 unavailable/missing 結果供既有決策邏輯 fail closed。無 reader 時仍為 None。 |
| PE source observation | `data_module/recommendation_input_providers.py::RecommendationFundamentalInputProvider.load_pe` | 每檔在舊 candidate-loop 位置以 read-only SQLite query 讀取 observed PE；`as_of_date` 與 `available_date` 都不得晚於 decision date，依舊排序取最新列，回傳完整 source/version/quality facts。缺 DB 維持 query error 並由既有 per-candidate error boundary 處理，不建立檔案。 |
| 月營收 | app builder 明示建立 lazy factory；data adapter 呼叫受治理 `FundamentalSQLiteProvider` | 不預取候選資料。PE gate 與舊早退完成後，才針對原本需要月營收的 candidate 查詢。factory 初次遇到 missing DB 會 cache no-provider，後續同 instance 不重試；constructor 明示提供的 provider 視為既有 warmed cache，與「尚未初始化的 factory」分開測試。 |

## 呼叫圖與主要變更

舊路徑由 `RecommendationService` 直接選市場來源、正規化／截斷 frame、開 PE SQLite、取得月營收 provider 與讀 PIT。新路徑為：

```text
composition / UI / CLI
  -> build_default_recommendation_input_preparer(config, explicit providers)
  -> RecommendationService(input_preparer=required)
  -> execute_recommendation creates one input session per invocation
  -> session validates/resolves cutoff and prepares market frame when body needs it
  -> service preserves evaluator/candidate order
  -> session reads PE and monthly facts at each original loop point
  -> service builds the same context and decision output
```

`RecommendationService` constructor 不再隱藏建立 default market provider；缺少 `input_preparer` 會明確拒絕。production composition、`ui_app`、personalization CLI、scheduled runner 及 7 個直接使用 service 的 QA CLI 都明示注入 builder。isolated recommendation QA 使用同一個 fake market provider instance 注入 builder 與 service。`tests/conftest.py` 沒有 RecommendationService constructor monkeypatch；AST caller sweep 找到 30 個已明確組合的 test service constructions，其中 21 個直接注入 input preparer、9 個 calibration-only callers opt-in 使用 `tests/recommendation_test_support.py::build_recommendation_test_service`，另有 1 個直接呼叫 production constructor 並驗證缺少 preparer 時 fail fast。測試 factory 只在明確呼叫時建立合成／TEMP preparer，不影響未選用它的測試；production 沒有測試 fallback。

每次 execute 只建立 session，不在 begin 時讀資料。session-local market provider override 不會寫回 shared preparer。monthly helper 收到該次 session 作為明示參數，不再讀 service `current session` attribute；R011 execution capture、R025 strategy import hunk與 invocation result identity未改。

## Parity 修補與架構限制

- 用 hand-written legacy normalization/fingerprint 計算比較 prepared frame，覆蓋截止日、available-date 修訂、universe、source ID、data date 與 fingerprint。
- 空 frame 在 `normalize_market_frame` 後與舊 `_decision_frame` 一樣早退；即使 frame 缺 `日期` 且 caller 有 cutoff，也不會進日期 filter、欄位轉型或 reset。
- A/B barrier interleave 測試同時執行兩個 explicit input session，分別核對 stock、decision cutoff、provider lineage；service 沒有 `current input session` 狀態。
- Monthly provider 測試區分已暖 cache 和 lazy factory：暖 cache 可以在 DB 後續不可見時仍被呼叫；factory 對初次缺 DB 零呼叫且同 instance 不因稍後 DB 出現而重試。正式 builder 走 factory 路徑。
- SQL source 使用 read-only URI 與 `PRAGMA query_only=ON`；此 R018 無新金融計算或裸 `float`，PE／月營收現有數值轉換及 scoring 未改。
- Look-ahead：market date、每列 availability date、PE `as_of/available` 與受治理月營收仍以實際 decision date 限制；歷史來源保留舊 60 日讀取窗口，沒有在 decision date 後補讀或全候選預取。
- ML adapter、frozen feature builder、模型載入、projection receipt 與技術資料 publication 均未納入本次 diff 範圍。

## 驗證

| 驗證 | 結果 |
|---|---|
| Root fresh TEMP／PROFILE=test recommendation-input、PIT、C1 suite（10 modules） | `71 passed`；包含 cutoff/source identity、PIT、explicit invocation session、interleave 與 fail-fast coverage。 |
| Root calibration／negative evidence／ranking／TASK-03／PIT suite（7 modules） | `54 passed`；2 個既有 `scoring_engine.py` pandas FutureWarning。 |
| Modified test Python paths `py_compile` | 通過；涵蓋 `tests/conftest.py`、test support factory 與 15 個相關測試模組。 |
| Broad package mypy | Root AGENTS gate `Success: no issues found in 695 source files`。 |
| RecommendationService source-boundary search | `rg` found no direct `sqlite3`, `read_csv`, or `read_sql_query` in `app_module/recommendation_service.py`; reads are delegated to explicit preparation/providers. |
| `git diff --check`（R018 相關 paths） | 通過；只有 Git checkout 對 LF／CRLF 的提示。 |
| 獨立唯讀 reviewer | fresh TEMP 6-module suite `56 passed`；核對 explicit session 傳遞、empty/no-date、monthly no-retry、PIT cutoff、PE order、fingerprint；未見 P1/P2，建議 `ACCEPTED_SCOPE`。 |
| Test caller boundary | `tests/conftest.py` has no RecommendationService constructor monkeypatch; 30 service creations use explicit composition (21 direct preparer injection and 9 opt-in factory calls), plus 1 direct fail-fast regression. |

歷史上一次不分 package 的 `mypy app_module data_module ui_app scripts` 嘗試曾被 repo 中 root 與 `scripts/scheduled` 的同名 `run_formal_input_producer_daily` 擋住 module discovery；本次適用的 AGENTS.md package gate 已由 root 重新執行並通過 695 files／0 issues。未執行需要正式資料根的完整 QA CLI。

## 變更清單與回滾注意

R018 新增：

- `app_module/recommendation/input_preparation.py`
- `data_module/recommendation_input_providers.py`
- `tests/test_recommendation_input_preparation.py`
- `tests/test_recommendation_input_read_order_characterization.py`
- 本報告

R018 修改的 mixed-owner paths：`app_module/recommendation_service.py`、`app_module/recommendation/execute.py`、`app_module/decision_service_composition.py`、`ui_app/main.py`、personalization/scheduled runner、4 個 QA scripts、`tests/conftest.py`、`docs/01_architecture/system_architecture.md` 與 `docs/00_core/DOCUMENTATION_INDEX.md`。測試 caller 修正另修改 R018 characterization 與既有推薦測試，並新增 `tests/recommendation_test_support.py`。這些檔案包含其他 agent 的既有 hunks；回滾只能由 root 逐 hunk 移除 R018 修改。不得對這些 mixed-owner paths 執行整檔 `git restore`、checkout 或 reset。R018 的新增測試／provider/preparation files 只有在確認仍為本任務獨占且沒有後續引用時才可移除。

## Gate 結果與接手邊界

Root 已裁定 R018 `ACCEPTED_SCOPE`。先前 R022 concurrent regime/composition migration 造成的 interim PIT/mypy blocker 已由後續共享工作樹 gate 解除；此報告不把該暫時失敗當成當前 blocker。接受範圍只涵蓋 R018 source preparation/provider extraction 及其 caller/test contract，不代表 Wave 7 release、formal data acceptance、production rollout 或 `TMP-REC-01` retirement；後者仍由 R019 依退休帳完成。
