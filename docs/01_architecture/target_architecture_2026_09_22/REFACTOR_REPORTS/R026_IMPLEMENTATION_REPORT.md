# R026 實作報告：舊 calibration preparation synthetic baseline

> **現況路由（2026-10-10）：** 本報告保留各日期與 namespace 的 bounded evidence snapshot。NP1／NP2 supported caller/profile 的接受範圍及仍未結案的來源證據，以 [Model Assignments](../REFACTOR_MODEL_ASSIGNMENTS.md) 與 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 判讀；正常 `RecommendationService` 遷移子條件關閉不等於所有 R026 source-evidence slice、profiles 或 production release 均完成。

## 2026-09-25 runtime handoff checkpoint snapshot

> 本節只記錄 2026-09-25 的 checkpoint，不代表目前整體 gate 狀態。後續 refactor 與保留風險見 [R031 2026-09-27 current checkpoint](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md#2026-09-27-current-checkpoint)；本報告後續各節仍是各自有界 source slice 的日期化證據，不可合併解讀為 R026 或整體 migration 全面完成。

Root 已接受 R026 supported production caller/profile 與 typed post-calibration handoff 的 bounded engineering scope；`TMP-ML-01` 定義的正常 `RecommendationService` 遷移條件已 `CLOSED`。支援範圍限下表 NP1／NP2 exact runtime tuple、exact consumer/loader/default deserializer 與 allowlisted model graph，且 capability 成功時使用 `PreparedMLRuntimeInputV1`；capability 不成立時維持原 `project_many()` 行為。此結論不宣稱所有 runtime profiles、custom consumers 或任意 model graph 已驗證，也不代表正式資料、模型 promotion 或 production deployment 已核准。

C2 current union route 為 **1860 passed／5 skipped／34 warnings**、102.75 秒、exit 0，141 個測試路徑前後 229 hashes unchanged；log `C:\Users\archi\AppData\Local\Temp\c2s_bcd34f\pytest.log` SHA-256 `193EF45EA69B984A356F238CFAD4D00D714AB2B026E01CE89887260E59604687`。Workbench 為 84 passed，broad mypy 為 724 files／0 issues。Update validator 有具名 Windows `WinError 32` SQLite cleanup baseline（25 passed／1 teardown failure／4 skipped、exit 1）；因此 C2 裁定為 `ACCEPTED_WITH_NAMED_QA_BASELINE`，不是全綠。細節見 [C2 mandatory UI/static gate 現況收據](../../../06_qa/C2_MANDATORY_UI_STATIC_GATES_20260925.md)。本文後續 section-local 狀態、舊 profile 範圍與「沒有 live service caller／不得 runtime handoff」等語句，均為各 source slice 當時快照，不取代本 checkpoint。

### 有限 production caller 與 runtime profile

| Caller / boundary | 現況與 cutover 範圍 |
|---|---|
| 一般應用 composition | `app_module/decision_service_composition.py` 在正常依賴組裝時建立 read-only `RecommendationCalibrationConsumer` 並注入 `RecommendationService`；`RecommendationService.__init__` 在未注入時也使用同一 default factory。 |
| 線上推薦投影 | `RecommendationService._apply_recommendation_calibration` 是此 R026 線上推薦輸出唯一 production `project_many` call site。Exact `RecommendationCalibrationConsumer` 在同次 selected items、result ID、aware decision clock 成立，且 active 或 no-model capability 成功時，預設使用 `PreparedMLRuntimeInputV1` projector；capability 不成立時沿用原 `project_many()` 相容路徑。 |
| 工作台 learning evidence projection | `RecommendationLearningEvidenceProjectionService` 建立自己的 consumer，該路徑只呼叫 `reload()` 與 `active_identity()` 取得狀態，不呼叫 `project_many()` 形成線上推薦輸出；不屬於本次 service projector cutover。 |
| 公開／相容邊界 | `RecommendationCalibrationConsumer.project()`、`project_many()` 與 custom/fake consumer 注入仍保留。非 exact consumer、未列 runtime profile 或 model graph 未通過 versioned allowlist 時，resolver 回傳無 capability，service 沿用舊路徑；不新增拒絕或 unavailable policy。 |

目前已明列的 runtime profile：

| Profile | Exact tuple（platform, Python, NumPy, scikit-learn, SciPy, joblib） | 本 checkpoint 證據 |
|---|---|---|
| NP2 | `win32`, `3.11.9`, `2.3.5`, `1.8.0`, `1.16.3`, `1.5.2` | Fresh short TEMP default/fallback focused route 26 passed；包含 active/no-model、configured source、projector parity、unknown-profile legacy fallback、custom fake consumer compatibility。Root已審 service diff與 source hashes，未發現 P1/P2。 |
| NP1 | `win32`, `3.11.9`, `1.26.4`, `1.8.0`, `1.16.3`, `1.5.2` | Exact tuple 已加入 consumer allowlist。Capture 的 exact-profile active/no-model/same-bytes/capability route 68 passed；configured-source service default node在 NP1 interpreter fresh short TEMP 1 passed，root另 fresh interpreter獨立重跑 1 passed。 |
| 其他 tuple / 未知 graph | 不在 allowlist | 保留 compatibility route；不得把未驗 profile 描述為 prepared-runtime parity。這些未知／custom compatibility callers 不納入本次已接受的 bounded `TMP-ML-01` 遷移範圍。 |

NP2 default/fallback route 命令為 `pytest tests/test_r026_prepared_runtime_service.py tests/test_r026_prepared_runtime_projection.py tests/test_prepared_runtime_input.py tests/test_r026_no_model_projection_capability.py tests/test_recommendation_service_calibration_integration.py::test_normal_recommendation_service_consumes_injected_projection_adapter tests/test_r026_calibration_legacy_preparation_baseline.py::test_legacy_preparation_freezes_t1_features_hashes_identity_and_call_order -q -o addopts= --basetemp C:\t\r026_default_np2_20260925_01\p`，結果 26 passed；log `C:\t\r026_default_np2_20260925_01\focused.log` SHA-256 `8E2B90C055D9563090CEBDD2E54727A80E2D980F0D77904226A83EA0EA0AED84`。NP1 configured-source service default node fresh short TEMP 結果 1 passed，log `C:\t\r026_np1_diag_20260925_2\focused.log` SHA-256 `C5BDB84B025A037B8AA0F738E05EA0CF9AF08008D84CE8AF5348C2C44D864526`；root獨立重跑相同 node 1 passed，log `C:\Users\archi\AppData\Local\Temp\r1d_d69a3c\pytest.log` SHA-256 `91CF13B976137E8C46782BF4152F4F16D261EFCA978B06A31A31B284A6FF8C3D`，實際 interpreter tuple如上表。NP2 configured-source service default node fresh short TEMP 亦為 1 passed，log `C:\t\r026_np2_diag_20260925_01\focused.log` SHA-256 `A805987B7B3A27F8AE623830EA2247D80096ADFEE86ACBD9AC9416C861938471`。NP1 profile route log `C:\Users\archi\AppData\Local\Temp\r1_930eb1\pytest.log` SHA-256 `0A9B39DFB4C416AE8DBDFA325079EB67E9A23CD1FF96D954F7A7B27F4360B610`；包含 capability/same-bytes/runtime-input/projector/NoModel，非 full C2 route。`tests/test_r026_prepared_runtime_service.py` 覆蓋 active receipt save/readback、typed projector 期間 no-I/O、legacy projection parity 的完整 receipt bytes、dense/mixed/all-missing feature-row parity、NoModel identity 與舊 rule-only `project_many` parity、project 後 source-contract bytes mutation 在 receipt 前拒絕，以及 unknown-profile fallback。

`TMP-ML-01` 的 bounded migration scope 是 repo 已支援且已盤點的正常 production `RecommendationService` shadow inference：NP1／NP2 exact profile 與實際 allowlisted model graph 預設走 prepared runtime，execute 由 typed post-calibration result/receipt handoff 提供 ML availability／receipt truth。此 handoff 已獲 root bounded review（R026 專項 21P、typed handoff 38P、整合路由 162P），且 migration 退出條件已 `CLOSED`。永久 `project()`／`project_many()` 相容入口、custom/fake test consumer、status-only learning-evidence caller 與未列 runtime tuple 保留原 compatibility；不將它們描述為已受驗，也不因 capability 缺席新增拒絕或 unavailable。

以上是有界工程接受，不代表所有 R026 source-evidence slices、profiles 或整體 refactor gate 一併通過。此 slice 不宣稱跨來源／SQLite／模型／receipt 原子性或 ABA，也不使用正式資料或進行 production promotion；這些是明示限制，不是本次 gate 的新增前置。C2 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`；Update validator cleanup failure 由 QA owner 具名追蹤，不撤銷本次 bounded runtime migration acceptance。

**日期：** 2026-09-24

**狀態：** 舊 preparation synthetic baseline、provider.load 完成後的 source-update barrier、修復前的 provider.load query-window blocker characterization，以及 provider read-snapshot transaction 修復均為 `ACCEPTED_SCOPE`（R015 獨立 review）。跨資源 identity Slice 1 純契約已由 R023 獨立判定 `ACCEPTED_SCOPE`（37P），但沒有驗證實際 sidecar bytes。Market revision Slice 3 含 schema/root 內 alias follow-up 已由 root 獨立判定 `ACCEPTED_SCOPE`（62P）；Historical-session Slice 4 collector 已獲 root bounded `ACCEPTED_SCOPE`（fresh TEMP 六檔路由 91P）；Excluded daily-price Slice 5B2 typed collector 經 R027 獨立複核無 P1/P2，root 判為 bounded `ACCEPTED_SCOPE`（fresh TEMP 八檔路由 109P/0F/0S）；Direct daily-price receipt typed collector 經獨立複核並由 root 判為 bounded `ACCEPTED_SCOPE`（fresh TEMP 六檔路由 89P/0F/0S）。四 namespace 單次 aggregate 另經 R027 獨立複核，root 判為 bounded `ACCEPTED_SCOPE`（fresh TEMP 七檔路由 90P，無 P1/P2；範圍見本文末節）。以上均為各自有界接受，不等於 R026 或 ML 接線完成。R026 仍 `IN_PROGRESS`、`TMP-ML-01` 維持 `ACTIVE`；scope_id production policy、sidecar／SQLite 跨資源 identity、多次 provider call 同版本與 ABA gate 尚未解決。

**歷史 live gate 摘要（2026-09-25；第三次 post-projection sidecar recheck 前）：** 四 namespace sidecar pre/post identity slice 經 R027 獨立複核後 bounded `ACCEPTED_SCOPE`（fresh short TEMP 34P，無 P1/P2；詳見 [live calibration source identity QA](../../../06_qa/R026_LIVE_CALIBRATION_SOURCE_IDENTITY_20260925.md)）。Live calibration 的 sidecar sampling 與 provider SQLite read lease 已接線，並由 R015 獨立複核 bounded `ACCEPTED_SCOPE`、root 另以 fresh TEMP 獨立重跑 39P 並通過 source mypy／compile（詳見 [live SQLite lease wiring QA](../../../06_qa/R026_LIVE_CALIBRATION_SQLITE_LEASE_WIRING_20260925.md)）。當時第二次 sidecar collect 在 feature compute 後、model projection 前；`lease.assert_unchanged()` 在 model projection 後、receipt persistence 前。該階段只比較兩次 collect 的觀察值，第二次 collect 之後的 sidecar 變更未再檢查；此描述已由本文末的 projection-post recheck slice 更新，不是目前 live gate 狀態。當時的 SQLite lease postcheck 不延長 sidecar sampling window；Shadow join 的 `SnapshotReference.source_revision` 為 `None`，availability／quality／scope 為 `UNKNOWN`，且未交給 runtime model consumer 或 `PreparedMLRuntimeInputV1`。Sidecar／SQLite 非原子、跨資源 ABA 與 historical replay 多次 provider call 共用版本仍未證明。R026 仍 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

Excluded daily-price Slice 5A 的 `formal_market` basename false-empty P2 follow-up 已由 R027 獨立複核，並由 root 判為 bounded `ACCEPTED_SCOPE`：fresh TEMP 四檔 route 51 passed，另有正式 market-repair guard route 11 passed。接受範圍僅限 scanner false-empty 修復、合法 prepare-only 形狀與 market fixture namespace 更正；不代表 excluded typed identity、namespace aggregate、跨檔原子性或 ABA gate 完成。

Excluded daily-price Slice 5B1 的 archive payload／acquisition receipt 及 non-full market source manifest 同次 bytes 驗證，經 R015 獨立複核（無 P1/P2）後由 root 判為 bounded `ACCEPTED_SCOPE`。獨立 fresh TEMP 七檔 route 為 81 passed／1 deselected，log SHA-256 `B619DC3391918692E0497469484B708882CAE281CFEECD539A58E75208B25B86`。接受僅涵蓋 16 個 archive payload／receipt 與 `_validate_market_chain(..., full_source_validation=False)` 讀取的 market source manifests；不涵蓋 full-source loader、typed rollback collector、跨檔原子性／一致性或 ABA 防護。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

**範圍：** 原 baseline 新增合成 characterization test 與 inventory 登錄；後續在已登錄測試追加 post-load 與 provider-load query-window cases。本次修復只修改 `data_module/ml_historical_snapshot_provider.py` 的三個唯讀 entry transaction 邊界、既有 R026 合成測試與本報告；沒有修改 service/composition、模型、正式資料、Direct/OOC 路徑或 artifact，也沒有改 inventory。

**後續接線方向：** [R026 PreparedMLInput 與 transient runtime input 設計裁決附錄](R026_PREPARED_RUNTIME_INPUT_DECISION_ADDENDUM_20260924.md)；[R026 跨資源 source revision identity 決策附錄](R026_SOURCE_REVISION_IDENTITY_DECISION_ADDENDUM_20260924.md)；[R026 historical-session namespace evidence Slice 4 附錄](R026_SESSION_REVISION_NAMESPACE_ADDENDUM_20260925.md)。附錄記錄待驗證的實作方向與 gate，不改變本報告已接受的舊路徑 baseline；`R026` 仍 `IN_PROGRESS`、`TMP-ML-01` 仍 `ACTIVE`。

## 目的與可支持的結論

新增的 [test_r026_calibration_legacy_preparation_baseline.py](../../../../tests/test_r026_calibration_legacy_preparation_baseline.py) 透過目前未修改的 `RecommendationService._apply_recommendation_calibration`，呼叫真實 `MLHistoricalSnapshotProvider.load`、`HistoricalFeatureBuilder.compute`，並用 spy consumer 記錄舊路徑的輸入、模型/cost identity、projection 與 receipt 呼叫順序。SQLite、設定中的 data/output root 與 pytest 暫存檔全在新建 TEMP 下。

這是 R026 的 **舊路徑 synthetic baseline**，不代表 PreparedMLInput 已接線、不證明新/舊雙路 parity，也不關閉 `TMP-ML-01`。測試使用 synthetic consumer，沒有載入模型、解析正式 active pointer 或執行 Direct/OOC。

## 凍結的 synthetic 行為

- 輸入推薦次序是 `BBB, AAA`；資料庫含 `AAA, BBB` 各 25 個合成日期資料列，最後四日從 2024-01-22 起，僅作 cutoff 後負例。
- decision date 為 `2024-01-22`。舊 provider 以 `日期 < decision_date` 解析 cutoff，得到 `feature_as_of_date=2024-01-21`；快照只有 2024-01-01 至 2024-01-21，共 21 日期、42 價格列。價格、技術、market、industry whitelist/query audit 保持現況，`query_count=5`；沒有讀入 2024-01-22 以後的列。
- Feature builder 保留下列 20 欄順序；20 欄的 dtype 都是 `int`，`turnover_amount_minor` 單位為 `minor_currency_unit`，其餘為 `bp`：

  `stock_return_1d_bp, stock_return_5d_bp, stock_return_20d_bp, stock_return_60d_bp, trailing_volatility_20d_bp, high_low_range_20d_bp, close_to_ma_5d_bp, close_to_ma_20d_bp, close_to_ma_60d_bp, rsi_normalized_bp, adx_normalized_bp, macd_normalized_bp, volume_ratio_5d_bp, volume_ratio_20d_bp, turnover_amount_minor, market_return_5d_bp, market_return_20d_bp, market_return_60d_bp, stock_minus_market_20d_bp, industry_relative_return_20d_bp`

- 凍結的 ordered values：

  ```text
  AAA = (84, 435, 2000, None, 5, 2100, 169, 860, None, 2000,
         3000, 1667, 10020, 10094, 12000, 5, 20, None, 1980, None)
  BBB = (145, 769, 4000, None, 17, 3960, 294, 1570, None, 6000,
         3000, 2857, 10039, 10186, 14000, 5, 20, None, 3980, None)
  ```

- 兩列的 missing IDs 均為 `stock_return_60d_bp`、`close_to_ma_60d_bp`、`market_return_60d_bp`、`industry_relative_return_20d_bp`；missing 保持 `None`，沒有轉零。Feature map 按 provider/builder 的 symbol 順序 `AAA, BBB`；rule probability、after-cost probability 與 baseline-ID map 保留候選順序 `BBB, AAA`。輸出仍是原兩個 rule candidates、順序不變、score 保留 `Decimal("80")`。
- Consumer 呼叫順序固定為 `active_identity → active_cost_scenario → active_after_cost_baseline → project_many → receipt attempt`，且整體舊路徑順序為 `provider.load → feature_builder.compute →` 上述 consumer 呼叫。合成 candidate id 為 `synthetic-candidate-2024-01-22`；cost identity 使用 `synthetic-cost-v1` / version `1` / hash `b` 重複 64 次；after-cost baseline 為 `after_cost_null_benchmark_50pct_v1` / 5000 bp。
- 對 provenance 固定 raw snapshot content SHA256 `sha256:19957d62a1770ea5659520c536506035b042c64c65df69267460066b8c191c0d`、ordered feature rows SHA256 `sha256:db22ca1fc85c72ae91d2858ef9daed6453a4b1f9e3079a9f01f66a60ee8bd17f`，及 feature snapshot fingerprint `sha256:9bc0e5bd47f18995e4ce8fd0dbed2a829442ccc23ddcb2c49e64e8043ce1d572`。Provider `source_fingerprint` 另以 `sha256:` 表示，測試確認其與同次 snapshot/provenance 相同且不等於三個內容 hash；它依 synthetic SQLite 檔案 metadata 產生，不把不同 TEMP 檔的 fingerprint 當成相同內容 hash。`source_contract_status` 明確為 `not_supplied`，本測試不宣稱有 dataset/source-contract 版本證據。
- Feature registry hash 固定為 `sha256:1a2adbeee4aa4a3935be1e30bf31bfbc6136a8fa84d975a1429e5fee4326e4b6`；feature builder schema hash 為 `sha256:6584386cf16161c8cbd3a70b9f8b2143ba7e3d49d6081b1eb46fec7e9194f5be`。
- 舊 `HistoricalFeatureRow` 沒有 `snapshot_hash` 欄；現 service provenance 對此欄以空字串投影。測試固定此既有語意，不把空值改造成 verified snapshot identity。
- 對 synthetic receipt write/readback boundary 注入 `PermissionError` 與 `RecommendationProvenanceError`，兩者都保留候選次序與 `Decimal` rule score，撤回 model-derived fields，receipt/projection 狀態降為 unavailable。此注入測試固定 service fallback；真實 create-only receipt 保存及 readback另由既有 public-service integration test 驗證。

## 驗證

所有 pytest 使用新的 TEMP 根、`PROFILE=test`，`DATA_ROOT` 與 `OUTPUT_ROOT` 指向同一 TEMP 下的隔離目錄，並以 `-o addopts= -p no:cacheprovider` 避免 repository 預設 plugin/output。

核心路由命令：

```powershell
  .\.venv\Scripts\python.exe -m pytest `
  tests/test_r026_calibration_legacy_preparation_baseline.py `
  tests/test_ml_historical_snapshot_provider.py `
  tests/test_ml_historical_feature_builder.py `
  tests/test_recommendation_service_calibration_integration.py::test_active_projection_receipt_storage_failure_withdraws_model_fields_but_keeps_rule_selection `
  tests/test_recommendation_service_calibration_integration.py::test_public_service_real_builder_saves_result_and_reverse_reads_receipt `
  -q -o addopts= -p no:cacheprovider
```

| Gate | 結果 | 範圍與限制 |
|---|---:|---|
| 原 accepted baseline synthetic/provider/builder/receipt route | 16 passed | 本次 barrier follow-up 前的 frozen route；包含 baseline 測試、provider/builder characterization、既有 receipt failure 與真實 receipt save/readback test；未執行 Direct/OOC |
| 新增 source-update barrier focused route | 2 passed / 3 deselected | 兩個 source-update cases；測試只使用隔離合成 SQLite 與 spy consumer |
| R026 core route at post-load acceptance | 18 passed | 同原 core route，增加兩個 post-load barrier cases；使用短 TEMP 根避免 Windows MAX_PATH |
| R015 post-load barrier review | `ACCEPTED_SCOPE` | focused 2P、core 18P；stat 只作 fingerprint 條件比較，不要求檔案 metadata 必然改變。此接受不含 provider.load query-window 一致性 |
| provider.load query-window source-update characterization | 2 passed / 5 deselected | synthetic hook 在 prices SELECT 後、technicals SELECT 前更新同長度欄位；metadata 變更時 stat guard 拒絕，還原 size/mtime 時 load 回傳混合版本。測試通過代表 blocker 已重現，不代表一致性 gate 通過 |
| R015 修復前 query-window characterization review | `ACCEPTED_SCOPE` | mixed snapshot 是修復前已重現的 R026 source-consistency blocker；此接受只確認 characterization，不代表修復已接受 |
| R026 core route including query-window cases | 20 passed | 更新後全部 synthetic/provider/builder/receipt route；混合 snapshot 測試是現況 blocker 證據，不是安全 gate pass |
| 新增 test + inventory `py_compile` | exit 0 | 僅語法檢查，不作 runtime parity 主張 |
| scoped mypy | 4 files / 0 issues | `app_module/recommendation/ml_adapter.py`、`ml_module/prepared_input_contract.py`、`data_module/ml_historical_snapshot_provider.py`、`ml_module/historical_feature_builder.py` |
| whitespace / diff hygiene | exit 0 | tracked inventory diff clean；新 untracked test 另行掃描，未發現尾端空白 |
| 實作者 inventory 全檔 guard | 22 passed / 1 failed | 這是實作者當時選取的路由；失敗為 shared-tree inventory 漂移，當時有 100+ 其他新/未登錄 test/support paths。清單不含本次新 test。本次只登錄本次新檔，不代其他 slice 批次改分類。 |
| R015 reviewer inventory 全檔 guard | 6 passed / 1 failed | 不同時間、不同選測路由；報告當下 inventory 有 108 個其他未登錄路徑與 5 個文件計數 drift。R026 test entry 仍存在。兩次全檔 guard 都非全綠，不能宣稱 inventory gate 通過。 |

最終核心 route 使用 TEMP 根 `C:\Users\archi\AppData\Local\Temp\r026_core_d5dfafd0`，16 passed / 0 failed。R015 reviewer 亦獨立完成 focused 16P，並確認 py_compile 與 scoped source mypy 4/0。兩次全域 inventory 路由的選測檔與執行時間不同，故 22P/1F 與 6P/1F 分別記錄，不互相替代；兩者均不能稱為全綠。直接 membership check 顯示本檔分類為 `service-oracle-recommendation`。

修正 stat 必變斷言後，R015 獨立接受 post-load barrier（focused 2P、core 18P）。對應重跑 route 在 `C:\Users\archi\AppData\Local\Temp\r26fc1032db7` 為 2 passed / 3 deselected，完整 core route 在 `C:\Users\archi\AppData\Local\Temp\r26c7ef9530f` 為 18 passed。兩者均以 `PROFILE=test`，並將 `DATA_ROOT`、`OUTPUT_ROOT` 指向該新 TEMP 下目錄；pytest 使用本節列出的 flags。該 review 不涵蓋 provider.load 內 query-window source update。

新增 query-window focused 命令為 `.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_calibration_legacy_preparation_baseline.py -k 'provider_load_pins_query_window' -q -o addopts= -p no:cacheprovider`，fresh TEMP 根為 `C:\Users\archi\AppData\Local\Temp\r26qb6200ae8`，結果 2 passed / 5 deselected。命令在 `PROFILE=test` 下執行，`DATA_ROOT`、`OUTPUT_ROOT` 都位於該根目錄。更新後完整 core route 使用 fresh TEMP 根 `C:\Users\archi\AppData\Local\Temp\r26w8a85dac5`，結果 20 passed。

最終 scoped mypy 命令為 `.\.venv\Scripts\python.exe -m mypy app_module/recommendation/ml_adapter.py ml_module/prepared_input_contract.py data_module/ml_historical_snapshot_provider.py ml_module/historical_feature_builder.py`，4 files / 0 issues。語法命令為 `.\.venv\Scripts\python.exe -m py_compile tests/test_r026_calibration_legacy_preparation_baseline.py qa/full_app_healthcheck/test_inventory.py`，exit 0。

## Source-update barrier：provider 已回傳後的 synthetic characterization

在 `tests/test_r026_calibration_legacy_preparation_baseline.py::test_legacy_source_update_after_snapshot_load_uses_captured_snapshot_and_still_attempts_projection` 新增兩個受控案例。Barrier 位於舊路徑 `MLHistoricalSnapshotProvider.load` 完成、`HistoricalFeatureBuilder.compute` 開始之前；測試只更新 `_service()` 新建的 TEMP SQLite，並在更新後另做唯讀 reload 作對照。

- `already-read-row` 將 cutoff 內 `AAA / 2024-01-21 / 收盤價` 從 `120` 改為 `99999`。本次 `compute` 仍消費 `provider.load` 已回傳的 frozen snapshot，cutoff 是 `2024-01-21`，ordered feature values、`raw_snapshot_content_sha256`、`feature_rows_sha256` 均等於 accepted baseline。之後從更新後 DB 新載入的 snapshot 讀得收盤價 `99999`，其 AAA feature values 與 baseline 不同，BBB 不變。
- `future-row` 將 cutoff 外 `AAA / 2024-01-23 / 收盤價` 改為 `99999`。captured 與 fresh snapshot 的 cutoff 都是 `2024-01-21`，此列兩者皆不含；fresh feature values 仍等於 baseline。
- 檔案 metadata 的變化依更新案例與執行時點而異。較早探索執行觀察到歷史列更新後 `st_size`／`st_mtime_ns` 不變；本次修正後最新 focused 與 core 執行都觀察到 `already-read-row` 的 stat 與 fingerprint 不變，而 `future-row` 的 stat 與 fingerprint 改變。測試不再要求任何一種 stat 結果，會將每案觀測寫入 pytest TEMP log，並只斷言「fingerprint 是否改變」等於「stat 是否改變」。在 stat 不變的案例中，fresh reload 仍讀到已改為 `99999` 的歷史收盤價。`source_fingerprint` 由 path／檔案大小／mtime／schema 組成，是 metadata fingerprint，不是 DB content hash，也不能單獨證明來源 revision 未變；當次 provenance 的 raw snapshot content hash 與 feature rows hash仍對應實際消費的舊 captured snapshot。
- 舊路徑在兩種更新後都繼續呼叫 `project_many` 與 receipt persistence seam；投影取得的是舊 snapshot values/hash。此測試使用 synthetic `_RecordingConsumer`，receipt persistence 被 spy 替代並只記錄 attempt（回傳 `None`），因此沒有載入模型，也沒有聲稱持久 receipt 已發布。

本案例未觀察到一次 invocation 混用新舊列：in-flight features 完全來自已捕獲 snapshot，future row 仍依 cutoff 排除；這是有限的 captured-snapshot 穩定性正例。它也**沒有 fail-closed**；更新在 snapshot load 完成後，舊路徑仍完成 projection/receipt-attempt。來源版本不能由 metadata fingerprint 單獨表達，因此新的 R026 handoff 必須以實際消費內容 hash 或不可變版本固定 source identity。這個 post-load barrier 不涵蓋 provider 內部五次 query 的間隙，也不證明讀取窗口具 transaction-consistent snapshot/version；下一節的獨立 query-window characterization 僅覆蓋 prices→technicals 間隙，並重現 stat guard 的一致性 blocker。其餘 query gaps、Rule 已讀／ML 尚未讀的競爭、active pointer race、真實模型及持久 receipt readback仍未驗證，不能據此關閉 `TMP-ML-01`。

**QA 調整歷程（過渡結果不作最終 gate）：** 初始 focused route 在長 TEMP 根 `r026_source_barrier_6174108de9094032b1150b855740be66` 曾為 `2 passed`，當時測試假設每次 SQLite 更新必定改變 file stat。接著完整 route 在長根 `r026_core_barrier_38e60a87c6e0416cabbe833d489bdea4` 為 `16 passed / 2 failed`：future-row case 顯示此假設受 mtime 粒度影響；既有 receipt integration 另因 Windows 長路徑在 `tempfile.mkstemp` 遇 `FileNotFoundError`。R015 初審指出 `assert before_stat != after_stat` 與舊報告的 stat 不變觀察矛盾；本次移除該斷言及無條件 fingerprint 不同斷言，保留 fresh row 內容變更、captured features/hash 不變，以及 `(fresh_fingerprint != captured_fingerprint) == (before_stat != after_stat)`。最新 focused route `r26fc1032db7` 為 `2 passed / 3 deselected`，完整 core route `r26c7ef9530f` 為 `18 passed`。長路徑與 stat 必變均不再作 gate 假設；沒有改 production 或放寬資料 assertions。

最終新增 focused 命令為 `.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_calibration_legacy_preparation_baseline.py -k source_update_after_snapshot -q -o addopts= -p no:cacheprovider`；測試開始前將 `TEMP`／`TMP` 設為新建短路徑 `r26fc1032db7`，並令 `PROFILE=test`、`DATA_ROOT` 與 `OUTPUT_ROOT` 指向該 TEMP 目錄下的隔離資料夾。

## Provider-load query-window source-update characterization：修復前一致性 blocker

修復前測試 `test_provider_load_query_window_source_update_is_guarded_only_by_file_metadata`（歷史函式名；現行對應測試名：`test_provider_load_pins_query_window_and_rejects_concurrent_commit`）使用 fresh TEMP SQLite 與 provider instance-local `_connect` proxy，在五次 snapshot SELECT 的第 2 次 prices query 完成後、第 3 次 technicals query 執行前，由獨立 SQLite writer 提交兩個等長欄位更新：AAA／2024-01-21 收盤價 `120` 改為 `999`，RSI `60` 改為 `99`。記錄的次序是 `cutoff → prices → writer_update → technicals → market → industries`。

- 兩種 case 的 reader/writer `PRAGMA journal_mode` 均回報 `delete`。writer 在兩個 `UPDATE` 之間處於 implicit transaction（`in_transaction=True`），commit 後為 `False`；reader 在 technical query 前 `in_transaction=False`，可在 prices SELECT 完成後由另一 connection 寫入。
- `metadata-changed-guarded` 將同一 TEMP DB 的 mtime 設為起始 mtime 加 5 秒，檔案大小保持不變。實測 stat 從 `(20480, 1790308444335120400)` 變成 `(20480, 1790308449335120400)`。五次 SELECT 仍讀到 prices 舊 close `120` 與 technicals 新 RSI `99`，但 `MLHistoricalSnapshotProvider.load` 在 query 結束的 stat guard 丟出 `RuntimeError: historical SQLite source changed during snapshot load`，不回傳 snapshot。
- `metadata-restored-mixed` 用 `os.utime` 將同大小 DB 的 mtime 精確還原到 load 開始值；實測 stat 前後都是 `(20480, 1790308444351260200)`。stat guard 因此通過，load 成功回傳單一 snapshot，內含舊 prices close `120` 與新 technical RSI `99`；隨後 fresh reload 讀到 close `999`、RSI `99`。兩個 snapshot 的 `source_fingerprint` 均為 `sha256:329212daa818a05fb023111e2c52548fb9c976715c429d7b9941221c3c1729f0`，內容卻不同。

這是 R026 的 **修復前 source-consistency blocker**：舊 size/mtime guard 可在 metadata 變更時 fail closed，但 metadata 還原或碰撞時可回傳跨 query window 混合版本。這份 2P characterization 固定的是兩種舊行為，不是安全 gate pass。當時最小修復候選是讓同一次 `load` 的 schema validation 與五次 SQLite 資料查詢使用同一 read transaction，並另行偵測 transaction 外的來源更新。`check_daily_price_source_revision()` 讀 repair sidecar 與其他來源修訂資訊，且在 snapshot connection 外執行；它不可能被描述為與 SQLite 查詢處於同一 transaction，跨資源一致性仍需版本／前後 identity 或共用鎖處理。修復前測試只覆蓋 prices→technicals 這一個 query gap。

## Provider read-snapshot transaction 修復：`ACCEPTED_SCOPE`

本次只在 `MLHistoricalSnapshotProvider.load`、`list_trading_dates`、`load_forward_price_window` 加入相同連線的唯讀交易邊界。順序是 `PRAGMA data_version` baseline →（load/forward 僅此兩者）既有 `check_daily_price_source_revision()` → `BEGIN` → schema 驗證與原有 SELECT/materialization 順序 → `COMMIT` → 同連線 `PRAGMA data_version` postcheck。任一 SQLite commit 發生於 baseline 後、postcheck 前都以既有各 entry 的 source-changed `RuntimeError` fail closed；`BEGIN` 是 deferred，沒有使用 `BEGIN IMMEDIATE`。失敗會 rollback 尚未結束的交易並由 `closing` 關閉連線。原 file-size/mtime guard、schema/fingerprint 語意與 query audit count 保持不變；`load` 仍為五個 audit queries，forward window 仍為兩個。revision sidecar precheck 位於 SQLite transaction 外，不宣稱跨資源原子性。

修復前在未加 read transaction 的版本中，新 contract 路由 `-k 'provider_load_pins_query_window'` 為 2 failed / 5 deselected（TEMP `r026_prepatch_c5f3f2ce71`），證明 DELETE/WAL 兩種模式都不滿足新交易邊界。修復後驗證如下：

- WAL case 在 prices 與 technicals 查詢間由另一連線提交兩欄更新。reader 位於 transaction 內，prices 與 technicals 都讀到舊值 `120/60`；主 SQLite 檔案的 size/mtime 未變。reader 結束交易後 `data_version` 不同，`load` 拒絕回傳；fresh reload 讀到新值 `999/99`。
- DELETE case 在相同 query gap 由另一連線嘗試 `timeout=0` 寫入。讀取交易持有讀鎖，writer commit 回報 locked 並 rollback；reader 保持 `120/60`，正常完成；fresh reload 仍為 `120/60`，測試沒有同步等待 writer。
- load 與 forward 的版本 baseline 後、revision precheck 前注入 WAL commit，並還原 DB mtime；事件次序仍為 baseline → precheck → BEGIN → queries → postcheck，兩個 entry 均在 postcheck fail closed。這保留「precheck 必須位於版本 baseline 之後」的條件。
- `load`、`list_trading_dates`、`load_forward_price_window` 的成功與 schema/precheck 例外路徑均檢查連線關閉且沒有遺留 transaction。

修復後 focused route 使用短 TEMP 根 `C:\Users\archi\AppData\Local\Temp\r26_862b`，執行 `tests/test_r026_calibration_legacy_preparation_baseline.py -k 'provider_load_pins_query_window or provider_detects_commit_between or provider_public_read_entries'`，結果 12 passed / 5 deselected。合併核心 route 同根下 `--basetemp <TEMP>\p` 執行 provider、feature builder、calibration integration 與 R026 characterization 四檔，39 passed。另有一次較長 TEMP 路徑執行合併 route 6 個 calibration lineage setup tests 因 Windows MAX_PATH `FileNotFoundError`；縮短 TEMP/pytest basetemp 後該 route 39P，失敗屬路徑長度，不是 provider assertion。

Scoped mypy 命令 `mypy app_module/recommendation/ml_adapter.py ml_module/prepared_input_contract.py data_module/ml_historical_snapshot_provider.py ml_module/historical_feature_builder.py` 為 4 files / 0 issues；provider 單檔 mypy 為 1 file / 0 issues。`py_compile` provider 與本 R026 test exit 0，provider `git diff --check` exit 0，test/report trailing-whitespace scan 未發現尾端空白。R015 已對此 provider transaction implementation 給 `ACCEPTED_SCOPE`；fresh TEMP focused route 12 passed / 5 deselected、core route 39 passed、mypy 4/0。此 bounded acceptance 不涵蓋 sidecar／SQLite 跨資源 identity、多次 provider call 共享同版本、`TMP-ML-01` 或整體 R026/ML cutover closure。

本次重跑命令使用 `PROFILE=test`，`TEMP`／`TMP` 設為 `C:\Users\archi\AppData\Local\Temp\r26_862b`，`DATA_ROOT=<TEMP>\d`、`OUTPUT_ROOT=<TEMP>\o`、pytest `--basetemp <TEMP>\p`：

```powershell
python -B -m pytest `
  tests/test_ml_historical_snapshot_provider.py `
  tests/test_ml_historical_feature_builder.py `
  tests/test_recommendation_service_calibration_integration.py `
  tests/test_r026_calibration_legacy_preparation_baseline.py `
  -q -o addopts= -p no:cacheprovider --basetemp <TEMP>\p
```

短 TEMP 整合路由為 39 passed；focused 交易／cleanup 路由使用 fresh TEMP 根 `C:\Users\archi\AppData\Local\Temp\r26_0139`，執行 `tests/test_r026_calibration_legacy_preparation_baseline.py -k 'provider_load_pins_query_window or provider_detects_commit_between or provider_public_read_entries'`，結果 12 passed / 5 deselected。第一次整合嘗試使用較長 TEMP 根 `r026_provider_core_c1f01ab3482b4c40960ccc0c494f9fa7`，6 個 calibration lineage setup 在 `tempfile.mkstemp` 以 `FileNotFoundError` 失敗，路徑已超過 Windows MAX_PATH；將 TEMP 與 pytest basetemp 改為上述短根後同四檔路由 39P。這些失敗不涉及 provider assertion，也不作功能 gate。當前 frozen implementation inputs：HEAD `e16f92928980a025d24bd5b023eeadf9d6a31daa`；provider SHA256 `2853542CFAEA8EB40A71978D5D9AC3A3567DA6722AA7B772123D4F371EC4A6C8`；test SHA256 `3CC5E53B07E30A69E0ED92F9574FB50A22B217A6287C64F8FBEFCDEBD66BF09C`。Inventory SHA256 `4E2A398EE13B4D2120AB11BA37AA2E4E202A355D9202A1607D0D219946B30416`，未修改；R026 test entry 仍列為 `service-oracle-recommendation`。本次沒有證明 sidecar 與 SQLite 查詢跨資源原子一致，也未驗證多次 provider invocation 的共用版本、active pointer/模型 race 或 PreparedMLInput production cutover。

## Look-ahead、隔離與尚未驗證項

本 synthetic data 將決策日後資料留在 SQLite 中，直接檢查 provider snapshot 僅含 cutoff 前資料；feature rows 的 `decision_date`、`feature_as_of_date`、`available_date` 分別為 2024-01-22、2024-01-21、2024-01-22。合成資料刻意逐日插入，`2024-01-21` 是星期日且不代表真實交易日；本證據只固定舊 provider 依資料中最大 `日期 < decision_date` 選 cutoff 的語意，不證明真實交易日曆、intraday availability 或正式資料 revision。

已接受的 post-load slice 驗證 provider.load **完成後**、feature compute **開始前** 的兩種同 DB 更新。修復前 query-window characterization 在 prices query 後、technicals query 前注入更新，曾揭露 metadata 還原時 mixed snapshot 可被回傳；本次 `load` 以一個交易包住 schema 與整批 SELECT，現用該間隙驗證 WAL postcheck 拒絕與 DELETE writer 被阻塞。尚未為 load 的每一個 SELECT 間隙分別注入 writer；其他 entry 的本次驗證聚焦正常完成與例外清理。其餘尚未驗證項包括 Rule 已讀／ML 尚未讀的跨階段 source-update barrier、active pointer race、consumer 真正模型載入/quarantine/loader rejection、PreparedMLInput mutation guard、Direct/OOC artifact bytes、來源 source-contract binding、完整 model output parity、實際 readback corruption fail-closed 與跨程序 recovery。Receipt readback成功由既有 selected integration case覆蓋；本 baseline 的 failure case是在 service receipt boundary注入例外，不等同執行實際寫後讀失敗。這些項目及 before/after identity parity 必須由後續 R026 slices另行驗證。

## 修復前 historical 執行環境與來源識別

以下來源 SHA 是早期 baseline／修復前 query-window characterization 的輸入，不代表目前 provider transaction implementation。當前 provider 與測試 SHA 以本節前方「Provider read-snapshot transaction 修復」的 frozen implementation inputs 為準。

- HEAD：`e16f92928980a025d24bd5b023eeadf9d6a31daa`。
- Test：`tests/test_r026_calibration_legacy_preparation_baseline.py` SHA256 `14F81A5E6A01BC4D5A8E9ACA6ABF3F0525FE9AA81ECCC55843CF4921A8054B8E`。
- Inventory：R015 baseline review 時 SHA256 `E08980D362395FDAC1CB1851AC2B9F26747E20E053A93F6420FA0BE1D17A5CF1`；本次 barrier slice 結束時 shared-tree SHA256 為 `2B1B2AC5CE68C83BD78135CA5132750BDB56A055CA67332EB1DAD402A0F9EF51`。該 shared file 有其他 concurrent edits；本次未修改 inventory，並確認 R026 test entry 仍存在。R015 時曾因 R023 合法新增 R020 test 而自實作者前一 hash `55F1146B2EDF7A29E4AD0D78F39176A07E9AA3DC056389649778D91FAF5A16AF` 漂移。
- 舊路徑 service：`app_module/recommendation_service.py` SHA256 `BD971FCC946F2F5FFC1EAB8F82CF6D100E378DE1D49A21194ED39EBE15C2B8EB`。
- Snapshot provider：`data_module/ml_historical_snapshot_provider.py` SHA256 `A67CEB7238B669244084E95E03CA158D2E62DA19358C5A8E6D9E3481BA7C3C04`。
- Feature builder：`ml_module/historical_feature_builder.py` SHA256 `B4A5478B7BE2B628262146ABC4211A11CD6657A2E47F9E9200ACC15A6B2E92E9`。
- Provenance builder：`ml_module/recommendation_inference_provenance.py` SHA256 `AE83B703DCBDCE4D8EEABE66FDBE305799B1A4B72B0DD7F92BA870A28867189F`。
- Compatibility contract：`ml_module/prepared_input_contract.py` SHA256 `E39EE8ACB37CEDBCABE5276FE85703B2FDBEB98C2DE9702B23184934D6513D03`；app adapter：`app_module/recommendation/ml_adapter.py` SHA256 `61ED294BC577A9D68A1887DC73F357C5563F6D7D465F3FC5C97235D1DB300755`。兩者本輪僅作 mypy scope，未接入 production inference。
- Test support：`tests/recommendation_test_support.py` SHA256 `12F6A2FBAEEECEB2695CBFCDFBEAA469F8F56BDF36AD3C581A9184A5529202F7`，由既有 R011 test support 注入 input preparer。

新測試使用 pytest `tmp_path`，每次新建自己的 SQLite database，沒有正式資料路徑或正式模型路徑。提交／stage 未執行。

## 跨資源 identity Slice 1：純契約

此後續切片新增 `data_module/contracts/source_revision.py` 的 `ValidatedEvidenceFileV1`、`ValidatedNamespaceEvidenceV1` 與 `ValidatedSourceEvidenceV1`，並在 `data_module/contracts/__init__.py` 匯出。契約固定 market、historical session、excluded daily-price、direct daily-price receipt 四個 namespace；要求每個 namespace 明確標記 `present` 或 `empty`，並驗證 SHA-256、scope 與 cutoff。`role_id` 使用相對的 ASCII 識別字元：英數字起始，後續只可用英數字、底線、句點、連字號，並可用 `/` 分層；拒絕控制字元、換行、URI scheme、百分比編碼、反斜線及非 ASCII 分隔符。契約以 schema、scope、cutoff 及固定排序輸出 canonical digest。測試登錄為 `tests/test_r026_source_revision_evidence_contract.py`。

Fresh TEMP focused route 執行新契約測試與既有 `tests/test_data_market_contracts.py`，結果 37 passed；兩個契約模組 mypy 2/0，三個 Python 檔案 `py_compile` 通過。此 Slice 1 **只定義純不可變資料契約**：尚無 revision checker 產生這些摘要，沒有把 identity 接到 `MLHistoricalSnapshotProvider`，也沒有證明摘要對應實際驗證 bytes；因此不得視為 sidecar gate pass。既有 daily-price checker 字典／`None`、market/session/excluded guard 回傳與錯誤 ABI、PIT exporter manifest 與 receipt bytes 均未在本切片改動。R026 與 `TMP-ML-01` 維持 open/active。

## Direct repair receipt 同 bytes parse/hash Slice 2

**狀態：** direct repair receipt 同 bytes parse/hash bounded slice 已獲 `ACCEPTED_SCOPE`；R026 仍 `IN_PROGRESS`、`TMP-ML-01` 仍 `ACTIVE`。

修復前 `_check_receipt()` 用 `Path.read_text()` 解析 JSON，摘要稍後再由 `_file_sha256(path)` 重開檔案計算 hash。新 synthetic regression 在 JSON parser 收到並解析原 receipt 後，以同目錄 `os.replace()` 原子替換為另一份合法 receipt。修復前測試觀察到 parse 的 `source_date=2024-01-21`，摘要卻帶 replacement bytes 的 SHA256（`0d09ce59b5c85e5b7713a21e9194dc8fe2f33735c8154e183abf6c85b347632b`）；原始 bytes 的 SHA256 為 `a9ce42bf1a17d00de761ee25ebe6c54714575812620b2c61a66a9995b561e75f`。這證明摘要的 identity 可與實際判讀的 JSON 脫節，測試只使用 `tmp_path`，未觸及正式資料。

修復後 `_check_receipt()` 對該 receipt 只呼叫一次 `read_bytes()`，以該不可變 buffer UTF-8 decode/parse，並對同一 buffer 計算 `receipt_hash`；原 `_file_sha256(path)` 的第二次開檔 helper 已移除。public `check_daily_price_source_revision()` 的 dict／`None` 回傳、summary 欄位、hash 前綴、path、symbol/cutoff 判定與 unreadable JSON 的 `DailyPriceSourceRevisionError` 保持不變。測試亦確認無 receipt 仍回傳 `None`。

驗證使用 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r26s2_e21809`，`PROFILE=test`，`DATA_ROOT=<TEMP>\data`，`OUTPUT_ROOT=<TEMP>\output`。執行命令：

```powershell
$runRoot = 'C:\Users\archi\AppData\Local\Temp\r26s2_e21809'
$env:PROFILE='test'
$env:DATA_ROOT=Join-Path $runRoot 'data'
$env:OUTPUT_ROOT=Join-Path $runRoot 'output'
$env:TEMP=$runRoot
$env:TMP=$runRoot
.\.venv\Scripts\python.exe -B -m pytest tests/test_r026_daily_price_receipt_same_bytes.py tests/test_r026_calibration_legacy_preparation_baseline.py tests/test_ml_pit_year_shard_exporter.py -q -o addopts= --basetemp (Join-Path $runRoot 'p')
```

結果為 39 passed；另 `py_compile` 通過，`mypy data_module/ml_daily_price_revision_gate.py tests/test_r026_daily_price_receipt_same_bytes.py` 為 2 files / 0 issues，`git diff --check` 與新增測試尾端空白檢查通過。新增 `tests/test_r026_daily_price_receipt_same_bytes.py` 已登錄為 `service-oracle-recommendation`；同時確認既有 R020 `tests/test_r020_real_scorer_filter_stage.py` inventory entry 仍存在。修復前的 1 個預期失敗只作 red evidence，不算通過測試。

本切片凍結輸入：HEAD `e16f92928980a025d24bd5b023eeadf9d6a31daa`；`data_module/ml_daily_price_revision_gate.py` SHA256 `09CB384DE93ACDD5771A823CB4214009CF052688312FC77349846DA41132117E`；新增測試 SHA256 `6E46F361903FE82816E0DF01C1B099710998988753702FAA0A6B602FFAF98164`；shared inventory SHA256 `FA125B631C03B180E22DD468469D7D75844ABE98FA941E4F8E8DE832A3B94A9F`。Inventory 含 R026 本測試及 R020 scorer 測試兩筆。此報告由本段追加更新，未覆寫前述歷史收據。

此 slice 只修 direct daily-price repair receipt 的 parse/hash 同 bytes；market、session、excluded 三個 checker 沒有改動，也沒有建立四 namespace validated-evidence aggregate。repair receipt precheck 與 SQLite read transaction 仍是不同資源與時序；其他 sidecar identity、多次 provider call 共用 revision、active pointer race、source contract binding、模型/receipt readback 與 PreparedMLInput production cutover 仍未驗證，不能據此關閉 `TMP-ML-01`。

## Market revision namespace evidence Slice 3

**狀態：** 僅 market checker bounded slice（含 schema／root 內 alias follow-up）獲 root 依獨立複核判為 `ACCEPTED_SCOPE`；root fresh TEMP 五檔 route 62 passed。此結果不涵蓋其他 namespace 或跨 namespace aggregate；R026 仍 `IN_PROGRESS`、`TMP-ML-01` 仍 `ACTIVE`。

新增 `collect_market_revision_evidence(database_path, decision_date)` 作為 additive typed 入口；既有 `assert_market_revision_safe(...)->None` 改為薄呼叫，保留可用歷史日期回傳 `None`、修訂起始日當日及之後的 `ValueError` cutoff 行為。`validate_market_replacement`、writer、marker JSON 格式與 import ABI 未改。每個 marker/journal/plan/receipt/rollback 在本次呼叫內只讀一次；JSON parse 與 SHA-256 使用同一 buffer。Rollback 保留舊語意，只驗 marker 指向的 rollback bytes hash，不新增 JSON/schema 解讀。

Presence 規則為：若固定 receipt path 的某一元件在已逐段確認的普通資料根目錄內真正不存在，或完整掃描後沒有任何 revision marker，回傳 `EMPTY`；存在且完成驗證的 marker 回傳 `PRESENT`，包括合法的 before-start pending marker 與 rolled-back marker。普通 run 目錄沒有 `revision.json` 時仍略過。`run_role_id` 由 receipt root 下的相對 run path 編成 UTF-8、無 padding base64url 並加 `run_` 前綴，不依掃描順序或內容 hash。

本次補上 path identity fail-closed 邊界：receipt root 逐段 `lstat` 並 strict-resolve；只在確實缺少下一個路徑元件時回 `EMPTY`，dangling junction／symlink、非目錄祖先及解析到資料根以外的 ancestor 會拒絕。Run 掃描使用 `lstat` 加 strict resolve，dangling run、root 外 run（即使沒有 marker）會拒絕；兩個 lexical run entry 解析到同一個目錄也拒絕，避免同一組 bytes 產生兩套 role identity。每個實際讀取的 marker-chain file 仍由 capture 在讀前、讀後檢查 resolved target 位於固定 receipt root。

凍結前 path 負例曾在 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r026_market_links_red_5d6ad52c` 得到 7 passed / 4 failed：dangling receipt-root junction 與 dangling run junction 被誤當 `EMPTY`、root 外無 marker run junction 被忽略、兩個 resolved alias 未被拒絕。其後新增了 root 外 receipt ancestor junction 案例。Windows junction 均在 TEMP 建立；最終 focused route 無 skip，涵蓋 dangling root/run、root 外 ancestor/run、resolved alias collision，另保留原有含 marker 的 root 外 junction rejection。

最終驗證使用 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r026_market_final_feb0e2da`，`PROFILE=test`、`DATA_ROOT=<TEMP>\data`、`OUTPUT_ROOT=<TEMP>\output`、pytest `--basetemp <TEMP>\pytest`：

```powershell
$runRoot = 'C:\Users\archi\AppData\Local\Temp\r026_market_final_feb0e2da'
$env:PROFILE='test'
$env:DATA_ROOT=Join-Path $runRoot 'data'
$env:OUTPUT_ROOT=Join-Path $runRoot 'output'
$env:TEMP=$runRoot
$env:TMP=$runRoot
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_market_revision_evidence.py `
  tests/test_formal_market_data_repair.py `
  tests/test_r026_source_revision_evidence_contract.py `
  tests/test_r026_daily_price_receipt_same_bytes.py `
  tests/test_ml_restatement_candidate_source_profile.py `
  -q -o addopts= -p no:cacheprovider --basetemp (Join-Path $runRoot 'pytest')
```

結果 58 passed / 0 failed。`mypy data_module/formal_market_revision.py tests/test_r026_market_revision_evidence.py` 為 2 files / 0 issues；本 slice 三個 Python 檔 `py_compile` exit 0，`git diff --check` exit 0。`test_inventory.py` 同時保留 R026 market evidence 與 R020 scorer characterization 兩筆 membership。HEAD `e16f92928980a025d24bd5b023eeadf9d6a31daa`；`data_module/formal_market_revision.py` SHA256 `778DC0785ACBB12D5647194FB4185B3EB0E7EC2638933A12D1B2DE750BD2602A`；`tests/test_r026_market_revision_evidence.py` SHA256 `577DCF85BF327C383158601DD7BFC4E731EDDCB2A04C05852CE14CC8DD18CDC9`；inventory SHA256 `0698EB0046396CDCEDD0583D0713369A1E46C7CA07AE289A9D27EDD2AA05DF63`。

此 Slice 3 僅提供單次 market checker 所讀檔案的驗證與 identity 摘要，沒有接 daily-price、historical-session、excluded namespace，也沒有連 provider 或跨 namespace aggregate。讀取前後 path resolution 不能排除連結在檢查間被交換再復原的 ABA；多檔鏈亦非原子快照。這些限制與跨資源／多次 provider-call source identity 仍須後續 slice 驗證，不代表整體 R026、`TMP-ML-01` 或 ML cutover 完成。

## Market revision Slice 3 schema／root 內 alias follow-up

本 follow-up 關閉獨立 review 重現的 child-schema P2。`collect_market_revision_evidence` 現在要求 `journal.json`、`plan.json` 與 `applied receipt.json` 的 `schema_version` 均為 writer 使用的 `formal-market-repair.v1`；以更新鏈上 hash 後仍帶未知 schema 的合成資料會 fail closed。`rollback.json` 仍只讀一次並驗 marker 宣告的 SHA-256，不解析 JSON，也不新增 rollback schema／required-field 條件。synthetic `_write_run` fixture 已補 writer 實際產生的 schema 欄位。

root 內 junction 的窄政策也已固定：單一 lexical run alias 指向 receipt root 內巢狀 run 可接受，role ID 保留 alias 的 lexical path；兩個 immediate run entry 指向同一 resolved run 仍拒絕。測試於 TEMP 建立 junction，assert 不經 skip，並核對 PRESENT、alias role 與 target 檔案 digest。receipt-root 祖先／child-file 的 root 內連結未個別驗證；外部、dangling 與重複 resolved target 負例維持 fail closed。

Schema regression 在修正前以三種 child 各自重算鏈上 hash 後重現 `plan`、`journal`、`receipt` 均被接受；修正後三案均 fail closed。最終 fresh TEMP route：

```powershell
$runRoot = 'C:\Users\archi\AppData\Local\Temp\r026-market-final-9bba0804b0894a8faa10a3e6f295d152'
$env:PROFILE='test'
$env:DATA_ROOT=Join-Path $runRoot 'data'
$env:OUTPUT_ROOT=Join-Path $runRoot 'output'
$env:TEMP=$runRoot
$env:TMP=$runRoot
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_market_revision_evidence.py `
  tests/test_formal_market_data_repair.py `
  tests/test_r026_source_revision_evidence_contract.py `
  tests/test_r026_daily_price_receipt_same_bytes.py `
  tests/test_ml_restatement_candidate_source_profile.py `
  -q -o addopts= -p no:cacheprovider --basetemp (Join-Path $runRoot 'pytest')
```

結果 **62 passed / 0 skipped**（5.53 秒）。紅測階段 market evidence 檔為 3 failed / 13 passed，三個失敗分別是未知 plan、journal、receipt schema 未拒絕；綠測後該檔 16 passed。`mypy data_module/formal_market_revision.py tests/test_r026_market_revision_evidence.py` 為 2 files / 0 issues，`py_compile` 與 scoped `git diff --check` 通過。Inventory 的 market evidence 測試 entry 仍在第 384 行；本次沒有改動該共享 inventory。

Follow-up frozen SHA256：source `526A2685AB9185753D154593C52382CDF6B6946494097BD6B7CF0717543E2FBA`；test `38E8CE37B8CF511220CF1236A1FA0C3572A3A7BB863D2847A3A0302AF3D36185`；inventory 當時 shared-tree SHA `3AC04B024D668CBEF740ACD7214DB95419989C5E90318A8703BA3320327EA8DA`。此 follow-up 已由 root 依獨立複核判定 `ACCEPTED_SCOPE`（62P）；僅屬 market namespace bounded acceptance，不構成其他 namespace aggregate 或 ML cutover acceptance。

## Direct daily-price receipt path guard

本切片修復自動搜尋 direct daily-price repair receipt 的路徑信任邊界。固定 receipt root 的每個元件現在逐段 `lstat` 並 strict-resolve；只有普通元件確實不存在時才視為沒有自動候選。Dangling junction、無法解析／讀取、非目錄祖先、receipt 子項不是一般檔案或解析至資料根外，均轉為 `DailyPriceSourceRevisionError`。`pending.json` 與 `receipt.json` 子項也分開以 `lstat` 探測，故存在但 dangling 的子項不會退化成 `None`。

自動候選的 lexical 路徑只保留於 invocation 內供讀取前後重新 strict-resolve；公開 `source_revision_receipt_candidates()` 仍回傳 canonical `Path` tuple，摘要的 `receipt_path`、去重與 public dict／`None` ABI 不變。內部 junction 與指向相同 canonical 檔案的 explicit alias 仍可用並去重。自動路徑讀取後再次驗證 lexical alias 仍指向同一候選；explicit-only 路徑保留既有指定路徑語意。Receipt JSON 仍由單次 `read_bytes()` buffer parse 並計算 hash。

修補前的 fresh TEMP characterization 路由重現 3 個預期缺陷（3 failed / 10 passed）：外部 receipt-root junction 未拒絕、dangling 自動 root junction 回傳空候選、dangling child junction 回傳空候選。修補後以合成 `tmp_path` 驗證上述三案拒絕，另驗外部 future／cutoff 內 receipt 均由 containment 拒絕、內部 junction、內部 alias 去重、讀取期間 alias 改指另一個資料根內目標會 fail closed，以及 explicit dangling 路徑仍報缺失。該 alias 測試只覆蓋讀取檢查間持續存在的 retarget；它不排除檢查之間 retarget 後又還原的 ABA。

最終 fresh TEMP `C:\Users\archi\AppData\Local\Temp\r026fix-62948352` 使用 `PROFILE=test`、`DATA_ROOT=<TEMP>\data`、`OUTPUT_ROOT=<TEMP>\out` 執行 direct receipt characterization 與同 bytes oracle：

```powershell
$env:PROFILE='test'
$env:DATA_ROOT='C:\Users\archi\AppData\Local\Temp\r026fix-62948352\data'
$env:OUTPUT_ROOT='C:\Users\archi\AppData\Local\Temp\r026fix-62948352\out'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_daily_price_receipt_link_characterization.py `
  tests/test_r026_daily_price_receipt_same_bytes.py `
  -q -o addopts= -p no:cacheprovider
```

結果 **14 passed / 0 skipped**。log `C:\Users\archi\AppData\Local\Temp\r026fix-62948352\pytest.log`，SHA-256 `9A86CF045083BA7C42E3B5ED84B3F296FD3131584865355E0A7D368308E010E7`；修補前 red log `C:\Users\archi\AppData\Local\Temp\r026red-53e40661\pytest.log`，SHA-256 `670574A0D7CAC68FF362E28F3DAB4BCAD13291DD710BAF27E1E4193F173B7E3E`。`mypy` 對 gate、link characterization、同 bytes 測試三檔為 0 issues；三檔 `py_compile` 通過，scoped `git diff --check` 無 whitespace error。Windows 目錄 junction 測試均實際執行，沒有 skip；一般檔案 symlink 因環境 `WinError 1314` 權限限制未測。

**狀態：** direct receipt path guard bounded slice 獲 root 獨立複核為 `ACCEPTED_SCOPE`；root fresh short TEMP 路由（link characterization、same-bytes oracle、PIT exporter）32 passed。此接受不代表所有檔案系統 link／競態都封閉。讀前與讀後兩次 resolve 只證明兩次觀察到同一 target，不排除中間 retarget 後再還原的 ABA；一般檔案 symlink 因 Windows `WinError 1314` 未測。此 slice 不建立 direct daily-price namespace identity，也不保證多檔與 SQLite 交易原子性。Direct receipt 檢查仍在 SQLite read transaction 及其他 namespace checker 之外；多次 provider call 的 revision 固定、模型載入及持久 receipt readback未由此 slice 驗證。R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`。

本 slice SHA-256：`data_module/ml_daily_price_revision_gate.py` `C571F3155846ACB9DAE8D248432D72C571320CB76DF47436A66DE19DCC8143A9`；`tests/test_r026_daily_price_receipt_link_characterization.py` `FDFB631F2EC3589E3E9EA3705FF801F1DC726065A45795DB242A041C86F97E7F`；shared inventory `qa/full_app_healthcheck/test_inventory.py` `61A322FB7C46A79DFD2DA953A2E05B09862ADAB7C690527E849B3CCE2E0D53C1`，仍登錄本測試為 `service-oracle-recommendation`。

## Historical-session revision namespace evidence Slice 4

Slice 4 有界實作與 TEMP 驗證詳見 [session namespace 附錄](R026_SESSION_REVISION_NAMESPACE_ADDENDUM_20260925.md)。新增 collector 對每個擷取的 marker/plan/terminal 檔案以相同 bytes 計算 hash 與解析；只有確認 root 缺少或完整掃描無 marker 後才回傳明確 `EMPTY`，並保留既有 tuple／`None`／cutoff 介面。Windows junction focused cases 均實際執行，沒有 skip。

Root 獨立複核判定 `ACCEPTED_SCOPE`：fresh TEMP 六檔路由 **91 passed**，涵蓋新 session collector、既有 session repair/write-guard/overlay、market namespace 與 source-evidence contract tests；scoped mypy 2 files / 0 issues，`py_compile`、inventory membership 與 scoped `git diff --check` 通過。此 Slice 4 接受範圍僅限 PIT evidence collector。

Evidence collector 與 PIT assertion 現在會對不完整 session scan fail closed；但 `validate_session_replacement()` 仍使用舊 `glob('*/revision.json')` 與 `_plan(..., capture=None)` 路徑。本次不宣稱已強化所有 session consumer。跨檔 ABA、多檔原子性、跨 namespace identity、provider 全 invocation 的 revision 固定與正式 ML 接線仍未驗證。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Excluded daily-price revision namespace：Slice 5A

**狀態：** 有界實作與本機合成驗證完成，等待獨立複核；此結果不構成 excluded namespace typed identity，也不關閉 R026／`TMP-ML-01`。

`_marker_paths()` 不再以 `Path.exists()`／glob 判斷空集合。它逐段 `lstat` 固定 receipt-root 路徑、strict-resolve 並限制在資料根；完成 `scandir` 後，逐一確認 immediate run 目錄、containment、marker 與列舉穩定性。真正不存在的普通路徑元件可回空；dangling／外部 junction、非目錄祖先、無法讀取／完整列舉、重複目錄 alias 及無 marker 的 partial run 都 fail closed。無 marker 只有 writer `prepare()` 實際建立的普通 `before_rows.json` 與 `plan.json` 精確形狀可忽略；嵌套 `formal_market` 子樹維持獨立，不把巢狀 market marker 當成排除 marker。Applied 九欄 legacy list、欄位順序、rolled-back 空 list、pending 拒絕及 cutoff 未改。

JSON bytes parser 現供 `_read_json()` 與已讀 bytes 的呼叫端共用。`_verify_archive()` 現用同一 `archive.json` bytes buffer 驗 SHA 並解析，避免 hash 與 parsed manifest 來自兩次讀取。此 slice 沒有改 8 個 source payload／8 個 acquisition receipt 的讀取鏈，也沒有改 `_validate_market_chain()` 的 market source manifest；不宣稱 17 個 archive 檔或 market source chain 已具同 bytes identity。掃描重觀察只能拒絕可見的持續變更，不提供跨檔原子快照，也不封閉 ABA。

修補前，原 frozen 測試 SHA `23CCBDB5DA8C0C9D17B471750AB7E0528C01BC0940CAC0C3D8EBC2E89495BDA6` fresh TEMP 路由為 5 passed／3 failed：dangling root junction、外部 root junction 與 archive manifest hash／parse double-read。擴充的 pre-fix characterization 另以 6 passed／5 failed 重現上述三案、journal-only 無 marker partial 及 dangling run junction；Windows junction 由 `mklink /J` 真正建立。新 scandir 權限錯誤 case 在修正後納入綠測。

本機 Windows／Python 3.11.9 fresh short TEMP `C:\t\r26s5final1`、`PROFILE=test` 路由以下四檔 **47 passed／0 failed／0 skipped**：

```powershell
$env:TEMP='C:\t\r26s5final1'
$env:TMP='C:\t\r26s5final1'
$env:PROFILE='test'
$env:DATA_ROOT='C:\t\r26s5final1\data'
$env:OUTPUT_ROOT='C:\t\r26s5final1\output'
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_r026_excluded_daily_price_namespace_red.py `
  tests/test_excluded_daily_price_revision.py `
  tests/test_daily_price_source_revision_overlay.py `
  tests/test_daily_price_revision_write_guard.py `
  -q -o addopts= -p no:cacheprovider --basetemp C:\t\r26s5final1\pytest
```

Scoped mypy 對 source／新測試 2 files／0 issues；兩檔 `py_compile` 與 `git diff --check` 通過。新測試維持 inventory 的 `service-oracle-recommendation` entry；沒有修改共享 inventory。

Slice 5A frozen inputs：`data_module/excluded_daily_price_revision.py` SHA256 `09A2F9175CDBD536647EB18A023D06B3F956F53885AE58F494A4170C768A79C4`；`tests/test_r026_excluded_daily_price_namespace_red.py` SHA256 `6980F3A6A6E90D20D9BAA6D3262CE84F9AD1C24EDB299B8AA73FDD1699EC71CB`；QA note SHA256 `EBC61ED9E6568FED47904AAB9A470EAF097B44B3AF22DAF3A61E55CC43185961`；inventory SHA256 `92732341F58D298F5D3C40901E3BA73DF6CA0506DE15EB2B797F397D14D57B03`。本報告以 append-only 方式增加此段；更新前 SHA256 `C182A29EB62E128BB4C1CE27D5FAEDEC16F6A6F12FDC98AF1F72B41C2F9EDC46`。R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`。

### Slice 5A reserved-basename P2 follow-up（2026-09-25）

**狀態：** R027 獨立複核後由 root 判為 bounded `ACCEPTED_SCOPE`。此段 supersede 前述 47-pass 收據作為 current Slice 5A 狀態；舊數字保留為 P2 發現前歷史證據，不再代表最新 gate。

R027 複核發現 `_marker_paths()` 對 basename `formal_market` 的無 marker 目錄有過寬例外：即使目錄只有 `journal.json`、含 partial child，或含 run junction，也會被忽略成空集合。修補移除此 basename 特例。無 `revision.json` 的目錄只在內容恰為普通 `before_rows.json` 與 `plan.json` 時視作合法 prepare-only；journal-only、nested child/run link 等其他形狀以 `ValueError` fail closed。合成紅測在修補前重現 3 個預期失敗，prepare-only 控制通過。

前一段「嵌套 `formal_market` 子樹維持獨立」是此 P2 發現前的描述，現由本 follow-up 取代；目前 production scanner 不保留該 basename 特例，測試 market fixture 改在正式 market receipt root 建立。

測試夾具的 market receipt 位置同步更正：`tests/test_excluded_daily_price_revision.py::_write_market_receipt()` 原先把 market run 放在 excluded root 下的 `formal_market/<run_id>`，改為真實 `formal_market_revision.RECEIPT_DIR/<run_id>`。Excluded repair plan 仍保存相對 market path 並走既有 `_validate_market_chain`，沒有改 production writer、market/excluded plan schema 或 public loader ABI。此修正避免只為測試用的巢狀位置在 production scanner 保留 basename 例外。

Fresh TEMP `C:\t\r26s5a_final_e35cd51d`、`PROFILE=test`、資料／輸出／pytest root 均隔離。四檔 route（namespace characterization、既有 excluded writer/loader、overlay、write guard）**51 passed／0 failed／0 skipped**；log SHA-256 `0E424D9724896686B8534343F929F2DD753CCF4934708AB2D23DDF7ABC70E03F`。Scoped mypy 3 files／0 issues，`py_compile` 通過，`git diff --check` 無 whitespace error；inventory entry 原已存在，沒有改共享 inventory。

本 follow-up SHA-256：source `data_module/excluded_daily_price_revision.py` `5DBC116C9B3FF7E04B656AEA16FB283C9A275A1BED7DBF773CFA32F3A45A7035`；namespace test `tests/test_r026_excluded_daily_price_namespace_red.py` `5AA95EE057C1E3650AECB14A49D6DE027CCB97BF00FFC63248CEDECCD78CD9A9`；market fixture helper test `tests/test_excluded_daily_price_revision.py` `A5071E47C0A563301FBF3B14BDB30E909C98A9C5177E919AC661CC25B640DB2A`；QA note 最終 SHA-256 見該文件。

R027 獨立 reviewer 以另一組 fresh TEMP 重跑四檔 route，結果 51 passed／0 failed／0 skipped；另跑 `tests/test_formal_market_data_repair.py` 為 11 passed。沒有發現 P1/P2，確認此 follow-up bounded `ACCEPTED_SCOPE`。該接受僅移除 basename 導致的 false-empty 特例並保留合法 prepare-only skip；不宣稱已對 market chain 建立同 bytes／typed identity，也不加強跨檔原子性或 ABA 防護。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Excluded daily-price revision namespace：Slice 5B1 same-bytes validation

**狀態：** 本 slice 經 R015 獨立複核並由 root 判為 bounded `ACCEPTED_SCOPE`；不構成 R026 整體 acceptance，`TMP-ML-01` 仍 `ACTIVE`。

`_verify_archive()` 現以每個 official payload／acquisition receipt 單次讀取的 bytes 驗證 archive/plan 宣告的 SHA 與 byte length、解析 JSON，並用同次 payload hash 驗 receipt cross-link。八組 payload／receipt 都走同一迴圈。`_validate_market_chain(..., full_source_validation=False)` 對每個 market source manifest 單次 `read_bytes()`，以該 buffer 驗既有 SHA 並解析；source entry 現有 schema 只宣告 `path`、`sha256`，未新增 expected byte length 欄位。Full-source market loader、writer、legacy list、overlay 與 PIT cutoff 均未改。

修補前 Slice5B 紅測在 Slice5A 凍結 source／fixture 上重現三個預期缺口（3 failed／0 skipped）。修補後以 fresh TEMP 跑 Slice5B 測試、Slice5A namespace、excluded writer／overlay／write guard、formal-market repair 與 market-evidence 共七檔；rollback typed-presence 缺口明確 deselect，結果 **81 passed／1 deselected／0 unexpected failure**（15.87 秒），log SHA-256 `8F3B3D832FA53990DE24234DB90F875868BEA62CF6A3505F99E27AAA363DA7D0`。獨立執行 rollback typed-presence 測試仍得到唯一預期紅點：typed collector 尚不存在，而 legacy API 回傳空 list；log SHA-256 `A80442460D2F95DDC7481D23986691615B82D880F1E053C0EB3E0C7F3CC8444D`。Scoped mypy 3 files／0 issues，`py_compile` 通過，whitespace scan／scoped diff check 通過。

Slice5B1 frozen SHA-256：source `data_module/excluded_daily_price_revision.py` `453BE833F6EC4EBCA2DE53011C302930D9B77DDB5A44E5D07FF4B4B7B53546E5`；test `tests/test_r026_excluded_daily_price_atomic_replace_red.py` `A46728D1D0856D73D89BDB03211ACBCCFB2DCE3D3191849DDA84ED2B3D4CDAC8`；QA receipt `docs/06_qa/R026_EXCLUDED_DAILY_PRICE_SLICE5B_ATOMIC_REPLACE_RED_20260925.md` SHA-256 `CB0AACBD6EAC9FEDFC7A888BB951B12D443E2A4D3FDB9DB5C6254243BBB73E2E`。Payload／receipt race 已 parameterize 各一例；market manifest race 另有獨立 case。R015 獨立複核無 P1/P2，root 判定此 bounded slice `ACCEPTED_SCOPE`；R015 fresh TEMP 七檔路由為 81 passed／1 deselected，獨立 log `C:\t\r0265b1review_20260925\pytest.log` SHA-256 `B619DC3391918692E0497469484B708882CAE281CFEECD539A58E75208B25B86`。deselected 測試是尚不存在的 typed rollback collector 預期紅點。接受範圍不涵蓋 `full_source_validation=True` loader、typed rollback collector、跨檔原子快照／一致性或 ABA 防護；R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Excluded daily-price revision namespace：Slice 5B2 typed evidence collector

**狀態：** 經 R027 獨立唯讀複核（無 P1/P2）並由 root 判為 bounded `ACCEPTED_SCOPE`；不構成 R026 整體 acceptance，`TMP-ML-01` 仍 `ACTIVE`。

新增 `collect_excluded_daily_price_revision_evidence(database_path, decision_date) -> ValidatedNamespaceEvidenceV1`。collector 與 `load_exclusion_evidence()` 共用一次 marker scan 和 validated-run 路徑；它不先呼叫 legacy loader 再重新掃描。檔案角色以相對固定 excluded receipt root 的 lexical run path 編碼，applied run 摘要包含該次驗證實際讀取的 revision/plan/journal/receipt、archive manifest 與 16 份 archive payload/receipt、nested market manifest chain 與 market source manifests。Rolled-back run 的 `PRESENT` 只摘要實際驗證的 marker、plan、journal、rollback receipt；legacy active list 仍為空。合法缺 root／prepare-only 完整掃描回 `EMPTY`，pending、損毀鏈、scan error 與不安全路徑 fail closed。Applied cutoff 沿用既有最早 `source_start_date` 規則。Legacy nine-field ordered projection、writer、overlay 與 schema 均未改。

Fresh TEMP `C:\t\r026s5b2_final_a66a8a9c8264`（Windows／repo Python 3.11、`PROFILE=test`，TEMP/TMP/DATA_ROOT/OUTPUT_ROOT/pytest basetemp 全隔離）八檔路由結果 **109 passed／0 failed／0 skipped**（19.31 秒），pytest log SHA-256 `173F675DBBC1E10ADF68CEDE37B9D7D011A8B03536ADF60EB42E2D71B0D0DDA0`。路由包含 Slice5B atomic-replace／typed collector、Slice5A namespace、source-evidence contract、excluded writer/loader、overlay、write guard 及 market repair/evidence tests。Scoped mypy 4 files／0 issues，四檔 `py_compile` 通過，`git diff --check` 無 whitespace error。完整路由、test-first red、具體命令、look-ahead 自查與 limits 記於 [Slice5B QA receipt](../../../06_qa/R026_EXCLUDED_DAILY_PRICE_SLICE5B_ATOMIC_REPLACE_RED_20260925.md)。

Slice5B2 frozen SHA-256：source `data_module/excluded_daily_price_revision.py` `D5A4484194892A667AFA5A30C898BBD3ADB34259A36C6D2B51A88075ED1DA585`；Slice5B test `tests/test_r026_excluded_daily_price_atomic_replace_red.py` `8AE7E885AD491F64083B7EBEC831E7A7E328D2661C73E57E847FD9A7A476887C`；contract test `tests/test_r026_source_revision_evidence_contract.py` `6FA8BC6E01672B1F6444EE957D3D05A910E654F6FCE21B3DCDACBA7E06AA013A`；inventory `qa/full_app_healthcheck/test_inventory.py` `0E7C433A8017707CE47386E170553F7F6E9AA74910EED451DA92590C4ECE2BCE`（既有 `service-oracle-recommendation` entry，未修改）。

Collector 只摘要單次驗證實際讀到的各檔 bytes；不宣稱跨檔原子快照、ABA 防護、跨 namespace aggregate、provider/ML 接線或 `full_source_validation=True` loader 已完成。R027 獨立 fresh TEMP 重跑同一八檔路由，TEMP root 為 `C:\Users\archi\AppData\Local\Temp\r026_slice5b2_review_7d6140032770495bbd074ce3ce256443`，結果 109 passed／0 failed／0 skipped（15.33 秒，exit 0）；該 reviewer run 未另保存 log hash，勿與 implementation pytest log 混為一筆。root 依此複核判 Slice5B2 bounded `ACCEPTED_SCOPE`，無 P1/P2。`market/sources/source-{index:06d}.json` role 由同次 nested market plan 的來源清單位置識別並由 plan bytes 綁定，固定 plan 內穩定，但跨來源清單重排不保留相同 role 名稱；如需跨 plan 版本追蹤同一來源，應採 data-root-relative path role。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Direct daily-price receipt typed collector

**狀態：** 本 bounded slice 經獨立複核後由 root 判為 `ACCEPTED_SCOPE`。此接受只涵蓋 direct daily-price receipt namespace 的 typed evidence collector，不代表 R026、四 namespace aggregate 或 `TMP-ML-01` 完成。

新增的 `collect_daily_price_repair_receipt_evidence()` 以同一候選掃描與 receipt inspector 建立 direct namespace 的 `EMPTY`／`PRESENT` evidence。它只處理 direct receipt namespace；既有 `check_daily_price_source_revision()` 的 `dict | None` ABI 與 market → session → excluded → direct-receipt guard 順序保留。Receipt 以一次 `read_bytes()` 得到的 buffer 同時解析與計算 SHA-256；角色由 automatic path 的資料根相對路徑 token 或 explicit path 的 canonical path hash 穩定識別。候選驗證途中若出錯，整次 collector fail closed，不回傳部分 evidence。

Legacy 與 typed explicit-slot 行為有一項刻意差異：explicit directory 內的 `receipt.json` 若存在但不是 regular file，legacy checker 經 `is_file()` 過濾後回 `None`；typed collector 的 strict slot mode 會拋 `DailyPriceSourceRevisionError`，避免把不完整 slot 表示成已驗證空集合。無效 JSON 在兩條路徑均 fail closed。PIT cutoff 與 pending receipt 行為由合成測試固定。

Frozen source `data_module/ml_daily_price_revision_gate.py` SHA-256 `A535B11766259B9ED3DE8CD711E04458FF342C51FC9452848C5493E42C27CCFA`；test `tests/test_r026_daily_price_receipt_same_bytes.py` SHA-256 `F0397D336866096C20C4C9D0AF23FF11D4DDC7482A9401E94E2A5B307BDC3886`。獨立 reviewer fresh TEMP 六檔路由為 **89 passed／0 failed／0 skipped**，11.24 秒，log SHA-256 `5F9B587172F65FA79AFBE62F98865BF4093820E7E4AC89B1F3B885314C6528A6`；scoped mypy 3 files／0 issues，三檔 `py_compile` 通過。完整隔離、檔案清單與測試限制記於 [direct receipt typed QA note](../../../06_qa/R026_DIRECT_DAILY_PRICE_TYPED_RECEIPT_20260925.md)，該 note SHA-256 `7C198EE2AE7B3C51078227D5396A4ECE17D5D51D0F444141F326E05E373A0E1A`。

此 slice 的讀前／讀後路徑解析不能排除期間 retarget 後再還原的 ABA，亦不提供跨檔／SQLite 原子性。Windows 一般檔案 symlink 因 `WinError 1314` 未能建立，未計入 coverage；本機連結測試實際使用目錄 junction。此 slice 不建立跨 namespace identity、不驗證多次 provider call 的同版本固定，也不接線 ML preparation。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## 四個 source-revision namespace 單次 aggregate

**狀態：** R027 獨立複核未發現 P1/P2，root 判定此資料層 aggregate bounded `ACCEPTED_SCOPE`。此切片只接受單次呼叫的 scope/cutoff 驗證、四 namespace 順序收集與完整 aggregate 建立；R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`。

`collect_source_revision_evidence_v1()` 先驗證 `scope_id` 與精確 `date` 型別的 `cutoff_date`，再依 market → historical session → excluded daily-price → direct daily-price receipt 順序各呼叫一次 typed collector。舊 `check_daily_price_source_revision()` composite gate 不在此呼叫鏈內。只有四個 collector 均成功才建構 `ValidatedSourceEvidenceV1`；任一失敗即傳遞錯誤，不回傳部分 aggregate。Contract 將 scope、cutoff 與 namespace evidence 納入 canonical digest。

R027 在 fresh TEMP、`PROFILE=test` 下獨立重跑七檔路由，結果 **90 passed／0 failed**（13.65 秒，exit 0）；測試涵蓋 collector 呼叫順序／單次呼叫、四個失敗位置、scope/date 前置拒絕、scope/cutoff digest 綁定與合成四-collector 整合。實際凍結 SHA-256：contract `data_module/contracts/source_revision.py` `0AB5255DBEC108BD36B2A3D99F2957B4367C767E762C41EF14566D70AA22FC3D`；collector `data_module/source_revision_evidence_collector.py` `7386164D5BF878365E7C0F7B578A5D9D3004226872AC108C0504296BE9DC6C9F`；test `tests/test_r026_source_revision_evidence_aggregate.py` `CD5C0E173C80B61E42927D878C848046887F46B4270E93EBB79204A3ACDD4420`。QA note：[R026 四 namespace aggregate QA](../../../06_qa/R026_SOURCE_REVISION_EVIDENCE_AGGREGATE_20260925.md)。

此 bounded acceptance 不制定 production `scope_id` 來源政策，不做 invocation pre/post identity wiring，也不提供跨 namespace／跨檔原子快照、不同 provider call 間的 SQLite revision 固定或 ABA 排除；亦未驗證 ML preparation、模型載入或 receipt readback。這些 gate 仍未完成，不能據此關閉 `TMP-ML-01` 或解鎖 R026 下游 cutover。

## Live calibration 四 namespace sidecar pre/post gate

**狀態：** 經 R027 獨立 read-only code/test review，bounded `ACCEPTED_SCOPE`；R026 仍 `IN_PROGRESS`、`TMP-ML-01` 仍 `ACTIVE`。

`RecommendationService._apply_recommendation_calibration()` 為每次實際 live calibration 建立一次性 scope token，並於 provider load 前及 feature build 後收集四 namespace aggregate。固定同一 resolved database path、decision cutoff、排序去重 symbols 與 scope；service 驗證 aggregate concrete type、schema、scope、cutoff 與 digest。前／後 collector 失敗、identity 不符或 digest 改變時，保留 rule score 並 fail closed，不呼叫 active model identity、consumer projection 或 projection receipt。穩定 aggregate 時既有 provider PIT 載入、feature projection、provenance 與 receipt 格式不變。

R027 獨立 fresh short TEMP route 重跑 `tests/test_r026_calibration_legacy_preparation_baseline.py` 與 `tests/test_recommendation_service_calibration_integration.py`，結果 **34 passed**（11.78 秒，exit 0；TEMP root `C:\Users\archi\AppData\Local\Temp\r026live_review_ff84e49b`），未發現 P1/P2。Frozen service SHA-256 `54205E777A6C3C8754217003FF50A819A3AA114CE8E3F264CAECCCBC0875926F`；integration test SHA-256 `C35F7068AE4528FE905F20964982B9AD73D573803A01F2D3B25B8DB2939F1DE7`。完整 route、failure/digest tests、來源限制及此前本地 QA 收據見 [live calibration source identity QA](../../../06_qa/R026_LIVE_CALIBRATION_SOURCE_IDENTITY_20260925.md)。

此 bounded gate 比對的是四 namespace sidecar evidence digest，並未將 SQLite row bytes/generation 納入 aggregate。SQLite-only mutation 可在 sidecar digest 不變時發生；單次 provider load 的 transaction guard 只涵蓋該次 read window，不代表 provider load 前後或 feature/projection 全期間使用同一 durable database generation。後續 live calibration lease wiring 將單次 provider load 的 SQLite read lease 保留至 model projection 後執行 postcheck，詳見下方「Live calibration SQLite lease wiring」；這仍不消除 raw SQLite generation／ABA 限制。此 slice 也不提供跨檔／跨 namespace／SQLite 原子快照、多次 provider call 共用版本、source-contract 完整性、模型載入安全或 receipt readback；不得據此關閉 `TMP-ML-01` 或解鎖 R026 下游 cutover。

## Provider-only SQLite read lease：R015 獨立複核

R015 以 frozen provider `data_module/ml_historical_snapshot_provider.py` SHA-256 `0223A3665B68DB950CF806D87F7C3CC3BBE925277813D083F7AFBB3A2A8E3928` 與 lease test `tests/test_r026_sqlite_read_lease.py` SHA-256 `1A83FC0D618031A1B002D34DF9661005A308766C249EB8EC13CA0BFB6306323D` 完成唯讀複核，未發現 P1/P2，判定此 provider-only slice bounded `ACCEPTED_SCOPE`。

R015 在兩個 fresh TEMP 路由分別重跑：`tests/test_r026_sqlite_read_lease.py`、`tests/test_ml_historical_snapshot_provider.py`、`tests/test_r026_calibration_legacy_preparation_baseline.py` 為 **26 passed**；另以 `tests/test_r026_sqlite_read_lease.py`、`tests/test_ml_historical_snapshot_provider.py`、`tests/test_ml_historical_feature_computation.py` 為 **19 passed**。兩路由重疊，不合併計數，也不取代 QA note 所列的既有 38-pass route。TEMP 根分別為 `C:\Users\archi\AppData\Local\Temp\r026-lease-review-0fd1cc6d55` 與 `C:\Users\archi\AppData\Local\Temp\r026-lease-integration-6d5803fdcb`；資料、輸出與 pytest basetemp 均隔離。Provider/lease mypy 為 2 files／0 issues，`py_compile` 通過。

複核確認：lease 使用同一唯讀 connection 比對 `data_version`；單次 `load()` 的 schema 與 SELECT 位於同一 read transaction，交易在回傳前提交。WAL 測試涵蓋外部 commit 及改值後還原的兩次 commit；DELETE journal 測試涵蓋交易中的寫入鎖與交易結束後成功寫入，再由明確呼叫的 `assert_unchanged()` 拒絕來源變動。Lease 只允許一次 `load()`，關閉後不可重用。

此接受只涵蓋 provider API 與單次 SQLite 讀取觀察。Lease 不會在 `close()` 自動執行 postcheck，呼叫端須在受保護工作後明確呼叫 `assert_unchanged()`；在當時的 provider-only checkpoint，service 尚未接線；本次接線與獨立 gate 見下節。`data_version` 不是 durable generation，stat 不能排除所有 ABA；sidecar／SQLite 跨資源 atomicity、多次 provider call 共用版本與整體 ML 接線仍未證明。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Live calibration SQLite lease wiring：`ACCEPTED_SCOPE`

`RecommendationService._apply_recommendation_calibration()` 現在將 sidecar precheck、單次 lease `load()`、feature build、sidecar postcheck、model projection 與 SQLite lease `assert_unchanged()` 放在同一受保護流程內。只有所有 identity/postcheck 通過後才發布本地 model projection 並嘗試寫 receipt；若載入後或 `project_many()` 中來源變更，projection 被丟棄、既有 rule 結果保留、calibration 標為 unavailable，且不發布模型 receipt。這個 bounded gate 只涵蓋一次 live provider load。

Frozen SHA-256：service `app_module/recommendation_service.py` `B66C6BF37A8EF63798FF6AAF2EB25603852BEEBB23C4378920425F804EB3D0EF`；provider `data_module/ml_historical_snapshot_provider.py` `0223A3665B68DB950CF806D87F7C3CC3BBE925277813D083F7AFBB3A2A8E3928`；baseline test `tests/test_r026_calibration_legacy_preparation_baseline.py` `66326C921F7882A7D82EC479CF012BE171577F99BA7FD07FDEA8C960EC40F2C5`；integration test `tests/test_recommendation_service_calibration_integration.py` `FE4DC7EF45D47A52E9A9F37BCB5671C387222D230DEBE2289FFCEF747AE95FF7`。QA note SHA-256 `0B9D592771DDF021BD6C040FAEACB57E6CCE046342760F68BF81B88E052C0CE4`。

R015 獨立 fresh TEMP 三檔路由為 39 passed，無執行期 P1/P2；root 另獨立重跑 39 passed，並確認 source mypy 與 `py_compile` 通過。命令、環境與 log 收據見 [live SQLite lease wiring QA](../../../06_qa/R026_LIVE_CALIBRATION_SQLITE_LEASE_WIRING_20260925.md)。

殘餘限制：sidecar aggregate 與 SQLite 不是共同交易；SQLite `data_version`／stat 不是 durable generation，不能排除所有 ABA。lease postcheck 與 receipt persistence 之間仍有 TOCTOU；本 gate 不涵蓋 historical replay 中多次 provider call 共享來源版本、跨資源原子性或完整 TMP-ML-01 cutover。R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`。

## Historical replay per-call PIT/cutoff characterization

**狀態：** R027 依凍結測試獨立複核，未發現 P1/P2；root 判為 bounded `ACCEPTED_SCOPE`。此接受僅涵蓋 synthetic replay 中各 provider call 的 cutoff 與單次 snapshot-load commit fail-closed，R026 仍 `IN_PROGRESS`、`TMP-ML-01` 仍 `ACTIVE`。

凍結測試 `tests/test_recommendation_historical_replay.py` SHA-256 `CCE2CCC3C4856DB6B20746BE3B71E6A3BAFA48BAF8C758BE6CD21FE59A29FC88`，provider SHA-256 `0223A3665B68DB950CF806D87F7C3CC3BBE925277813D083F7AFBB3A2A8E3928`，replay service SHA-256 `ABEFAD976DEDCBAA1396054452D56B0FC79E3DBDBD7C9602066B5B1A5501BAE2`。R027 fresh TEMP route 為 18 passed；完整命令、log SHA-256 與 case 預期見 [R026 historical replay per-call cutoff QA](../../../06_qa/R026_HISTORICAL_REPLAY_PER_CALL_CUTOFF_20260925.md)，該 note SHA-256 `B00BE7FEC4A692BF5393DD905EA7EB70419498E90A1703F3B69A3470EDD44EC2`。

合成 fixture 每個日曆日都有價格列，未模擬真實市場休市日。當時尚未測 forward-window read 期間的 commit 注入，也未證明 trading-date enumeration、feature snapshots、forward windows、source-contract 與 observed-cost 等多次讀取共用整輪 SQLite generation。後續 whole-replay observation lease bounded slice 與限制見下節；sidecar 與 SQLite 原子性、durable generation 與 ABA 仍未證明，不改變 R026／`TMP-ML-01` 的 open 狀態。

## Historical replay whole-build SQLite observation lease（bounded ACCEPTED_SCOPE）

`RecommendationHistoricalReplayService.build()` 現在在 trading-date enumeration 前開啟 `MLHistoricalSnapshotProvider` 的同連線 observation lease，整輪 `_build_result()` 正常返回後再執行 postcheck。新 `assert_observation_unchanged()` 不要求呼叫 lease `.load()`，因此空日期結果也會在返回前檢查。若 provider 將 per-date 讀取錯誤記為 skip，整輪 postcheck 仍會觀察外部 commit 並拒絕部分結果。lease 在正常返回或任何例外下由 context manager 關閉。

WAL synthetic tests 覆蓋 snapshot schema read 期間 commit、真實 `load()` 返回後到 forward-window call 前 commit（同時改 feature 與第 20 筆 label 價格）、以及空 trading-date enumeration 後 commit。三者皆要求 `historical SQLite source changed during read lease`，不返回部分 replay result；無 mutation control 保持 1156 bp sample。既有 scheduled classifier 測試將該錯誤分類為 `source-integrity emergency rollback`，而非 recoverable dependency retry；證據是 replay 呼叫路徑加分類器測試，不是完整 scheduled job entrypoint 的 WAL failure injection。

Frozen source SHA-256：provider `data_module/ml_historical_snapshot_provider.py` `35A7CC517AC0ACDA00E9CC60F267A0796490B9BE1D13E9D0AB58D3355B05B977`；replay service `ml_module/recommendation_historical_replay.py` `0364807F07FDAAE3F68B4E22269CAEB482FB2835E48E04638D0BFD316551013F`。Test SHA-256：`tests/test_recommendation_historical_replay.py` `1A35B38D6C7836FBE66E093FBBC494917EA16EF4C3B3E21EC4DAAE9EA99E22F3`；scheduled classifier test `tests/test_daily_recommendation_learning_loop.py` `248EB5415529534563A014F6C8D1EAE707EB06A9036B4C4C5390F7CA4B0CD1D9`。QA note [R026 whole-replay observation lease](../../../06_qa/R026_HISTORICAL_REPLAY_CROSS_CALL_MIXED_VERSION_20260925.md) SHA-256 `DC4CEDA4D57EAFA5FCC60FD6C186A1EEAA91FA0A977F5C11CDDD151BEB8BB813` records the command, TEMP root, prior characterization history and independent reviewer receipt.

Fresh short TEMP route：`tests/test_recommendation_historical_replay.py`、`tests/test_ml_historical_snapshot_provider.py`、`tests/test_r026_sqlite_read_lease.py`、兩個 provider transaction guard tests、以及 `test_preflight_failure_classifies_transient_and_integrity_faults` 為 **25 passed**；最終 log SHA-256 `DA2383135A59399E3C20C20E18409D46740EC6CAB27FB3A54064532F70EE729E`。Scoped mypy 2 source files、0 issues；四個相關 Python 檔 `py_compile` 通過；`scripts/quant_guard_linter.py` 通過其 financial-float 與 look-ahead checks。

另以 fresh TEMP 執行 `tests/test_daily_banktaiwan_learning_cost.py::test_replay_keeps_three_market_dates_in_one_cost_cohort`，**1 passed**（log SHA-256 `88BD8DFDB7A94B6010BA5E505610DE7AF6F1C0243A48A0FDF1FE146C619A4FA4`），確認原 multi-date cost cohort caller 仍可完成。

R015 已獨立複核上述 frozen provider、replay service、兩個測試與 QA 收據，全部 SHA 相符，未發現 P1/P2；fresh short TEMP 主路由 25P，另以 BankTaiwan cost cohort route 1P，source mypy 2/0、4 檔 `py_compile` 通過。此 whole-build lease slice 建議並經 root 判為 bounded `ACCEPTED_SCOPE`。排程證據只包含 replay 呼叫路徑的 fail-closed 測試，以及 `test_preflight_failure_classifies_transient_and_integrity_faults` 對既有分類器的驗證；沒有以完整 scheduled job entrypoint 注入 WAL mutation，不能宣稱排程端到端故障驗證完成。

這個 lease 只以同一唯讀 connection 的 `PRAGMA data_version` 及主 DB file size/mtime 觀察明顯變更；它不把多次 provider calls 放進同一長 read transaction，也不是 durable generation。`data_version` 的意義限於同一 connection；stat/data_version 不能證明所有 ABA 不可能。postcheck 之後仍有競態，sidecar 與 SQLite 不具共同原子交易。R026 維持 `IN_PROGRESS`、`TMP-ML-01` 維持 `ACTIVE`。

## Invocation-local consumer model-resolution capability（bounded ACCEPTED_SCOPE；experimental；不得 runtime handoff）

此切片在 `RecommendationCalibrationConsumer` 加入一次性 model-resolution capability API。能力建立時直接讀 pointer bytes，使用 fresh consumer 與預設 `joblib.load` 路徑解析 active candidate/lineage，再比對 fresh identity 與 pointer bytes 前後值。只接受 exact consumer/loader/default deserializer 與 exact top-level `RunnableRecommendationCalibrationModel`；source-contract-bound inference provenance 在任何 provenance file I/O 前拒絕。每個 capability 綁定 owner、ASCII scope、日期與 identity digest，且該 capability 僅能投影一次；`WeakValueDictionary` 只在同 scope capability 尚存活時拒絕重複建立，GC 後 scope 可重用，永久唯一性仍須未來 caller 保證、目前未證明。錯配與 copy/deepcopy/serialization 仍 fail closed；一般 `project/project_many` 預設路徑未變。

帶 `source_contract_binding` 的投影請求在 capability 被標為 used 前拒絕；這只是一項呼叫參數的 filesystem-I/O guard，不是持久 source policy 或已驗證 input 證據。未來 runtime caller 必須先提供 immutable、已驗證的 input facts。這不是 `PreparedMLRuntimeInputV1` handoff，且尚無 live service caller。前述 shallow-guard 說明是 capability 初始 checkpoint 的歷史狀態；nested graph validation 的最新 bounded follow-up 另列於下節，不能把舊 frozen receipt 當成新實作證據。

Fresh short TEMP capability unit route，於最終 consumer source SHA 寫入後執行，為 **10 passed**，log SHA-256 `493AB8ECB0C44D1622F50C8DB3E3FB10AE7B9B51A7EAB65FD1AD21A8B1E1BCAB`；相鄰 capability/prepared-input/service integration route 為 **44 passed／2 deselected**，log SHA-256 `8A57262E1BCA16F369F52813698758E65C2AF274CB6AA4362953FC653BD968BA`。R015 獨立複核對最終 source 重跑專項 route `C:\r26q\rv_00616ae0\unit.log` 為 **10 passed**，log SHA-256 `BBB897D94514ECD40F09F99E89BC5B234D5909504384264DC82CF10B2EFC7017`；獨立相鄰 route `C:\r26q\ra_5298e53b\adjacent.log` 為 **44 passed／2 deselected**，log SHA-256 `DCF37C2D43C1FC3161D0EB1DCC6B785C72BB2DE9BFD680EB1A9726412A56C0A8`。R015 scoped mypy 4 source files／0 issues、py_compile 與 diff-check 通過，無 P1/P2；root 接受此 bounded `ACCEPTED_SCOPE`，僅限 experimental model-resolution API。Inventory 中此測試只有單一 entry；同次全庫 inventory guard 結果 **6 passed／1 failed**，另有 **108 missing** 與 `documentation_count_drift: 5`，不是全庫 guard pass。Frozen SHA-256：consumer `app_module/recommendation_calibration_consumer.py` `471F02A1E7E440A5BAD7DC19794D5B5926368A8C7F0F8CB25FA3C8321F864CA6`，test `tests/test_r026_invocation_model_capability.py` `A11C6073C3621C37CAED8B130988ADE97364EC189272D956531422BBD201A5E7`，QA note `2E79C02D73AE8FABABE5D48201DF255DD8800C63DC8516FE41EE223A1F74C869`；完整 TEMP 路徑、MAX_PATH 診斷與限制見 [invocation model capability QA note](../../../06_qa/R026_INVOCATION_MODEL_CAPABILITY_20260925.md)。舊 TEMP `C:\r26q\b07829ac` 的 10-pass 收據早於最終 source，只留 QA note 作歷史診斷。

先前深 TEMP route 的失敗是 Windows nested temporary path 達 266 characters，`mkstemp/open` 回 `FileNotFoundError`；短 TEMP rerun 通過。Service integration 呼叫預設 projection 路徑，未傳 `_invocation_capability`，service source SHA 未改。此 experimental API 不綁 feature/candidate set，不建 pointer lease；resolve 後 pointer 變更、ABA、DB/source/model/receipt 共用交易及 receipt TOCTOU 仍未解。R026 維持 `IN_PROGRESS`、`TMP-ML-01` 維持 `ACTIVE`，不代表整體 ML cutover 完成。

## Known production model graph isolation follow-up（bounded ACCEPTED_SCOPE；僅 experimental model-resolution）

`_loaded_model_graph_snapshot()` 擴充為 `r026-known-model-graph.v1` exact-type／field allowlist。它沿 active/baseline/lineage model、probability lineage、loaded pointer、baseline identity 與 training provenance roots 遍歷 exact `RunnableRecommendationCalibrationModel`、`Pipeline`、`SimpleImputer`、`StandardScaler`、`Ridge`、`LogisticRegression`、`FittedShadowProbabilityCalibrator`、`IsotonicRegression`、SciPy `interp1d`，以及其 plain dict/list/tuple 與 numeric ndarray state。Source/fresh consumer 與存活 A/B capabilities 之間，mutable object identity 重疊或 ndarray backing storage `np.shares_memory` 均 fail closed。未知 type/field、cycle、callable、object/structured array、unsupported backing owner 與 graph/array budget 超限皆拒絕；SciPy interpolation `_call` 只接受 module import 時捕獲的 `_call_linear_np`／`_call_linear` exact callable identity，且要求無 closure/default/kwdefaults/function attrs。測試亦把 SciPy class attr 換成新的 closure-free callable，確認不會動態擴張 allowlist。

本輪 synthetic active candidate profile 實測 Windows 10 build `10.0.26200-SP0`、CPython `3.11.9`、NumPy `2.3.5`、Pandas `2.3.3`、scikit-learn `1.8.0`、SciPy `1.16.3`、joblib `1.5.2`。Optional capability resolver 在讀取 active pointer 前核對 `sys.platform`、Python major/minor/patch、NumPy、scikit-learn、SciPy 與 joblib 的精確版本；任一不符即回 `None`，且不讀 pointer 或呼叫 loader。Pandas 版本僅列入 QA fingerprint，不參與此 gate。該 fixture 遍歷到 70 mutable object IDs、41 ndarray、936 bytes；這是 fixture-specific 數量，不是所有 candidate 的固定 shape 或支援上限。另一 synthetic fixture 曾觀測 72 nodes/35 arrays；數量隨 model/lineage shape 改變。此 sliced evidence 不驗證其他 dependency versions、任意 Python graph 或未列出 estimator profile。

Current focused test `tests/test_r026_invocation_model_capability.py` 為 20 passed，fresh short TEMP `C:\r26q\v8a0be52b`，log SHA-256 `C2A36889563AD3EE8490701ABE49A6C36A250AA6C815A60E4408D6977221515C`。相鄰 capability/prepared-input/service route 為 54 passed／2 deselected，fresh short TEMP `C:\r26q\be0284eda`，log SHA-256 `0CE5418A6D5C0152EE5E9AF9820BBC7E72EBF51252382A0BC07B8195A2DBE67C`。R015 獨立複核同以 fresh short TEMP 重跑最終 frozen bytes：專項 route **20 passed**，log `C:\t\r26g1\pytest.log` SHA-256 `0DD309BA6814B30BD32BC9F745BA0903E41B432C084463802A7E5B1CF0F2661E`；相鄰 route **54 passed／2 deselected**，log `C:\t\r26g2\pytest.log` SHA-256 `462DC72865B970F7AE5C9354A1F94F3C3AE94B716B7D5515411F1CCD5B7BD696`。Scoped mypy 為 4 source files／0 issues；py_compile 與 targeted `git diff --check` 通過。R015 未發現 P1/P2，root 接受此 follow-up 為 bounded `ACCEPTED_SCOPE`。QA note [R026 invocation model capability](../../../../docs/06_qa/R026_INVOCATION_MODEL_CAPABILITY_20260925.md) 記錄完整命令、runtime mismatch no-pointer-I/O 負測、prior MAX_PATH diagnostic 與限制。

Frozen source SHA-256 `app_module/recommendation_calibration_consumer.py` `442A5EB46A5F3241D217834554788FC8A800881BECE494882F519142D85CA4BC`；test SHA-256 `tests/test_r026_invocation_model_capability.py` `8D6403B8803BD4294745ED46C0CF3F0B41DD1650232674E4803FD5FB5E4D91E2`。本 bounded acceptance 不外推到未列 runtime profile；depth/node/array/byte/element 各 budget 維度未逐一觸發驗證；capability 未綁定 feature/source/receipt；pointer ABA 與 receipt publication race 未解。不得 runtime handoff，未新增 live service caller，也不涵蓋 source/DB/model 原子性或 PreparedMLRuntimeInputV1。R026 仍 `IN_PROGRESS`、`TMP-ML-01` 維持 `ACTIVE`。

## Ordered recommendation-to-feature preparation facts（bounded `ACCEPTED_SCOPE`）

新增 app-side `RecommendationMLPreparationFactsV1` factory，輸入為同次明示 `result_id`、ordered typed selected items、ordered `HistoricalFeatureRow`s 與 canonical `HistoricalFeatureBuilder`；只透過 `HistoricalFeatureBuilder.load(row)` 取得 canonical feature IDs/order/schema/values/hash。`candidate_id` 使用 `candidate.v1:` domain-separated canonical SHA-256，綁定結果、決策日、cutoff、selection index、symbol、selected item hash、registry/schema hash 與 feature-row hash。它是 invocation-bound opaque ID，feature row 變動時刻意變更；feature-row digest 仍是獨立欄位。Canonical JSON 固定為 UTF-8、sorted keys、compact separators、`ensure_ascii=False`、`allow_nan=False`。Golden payload SHA 為 `sha256:e8516ec9535dd14d7501aafc893bc67e93db374f38add3d679369e280a66347b`。

Factory 對候選數量、重複 symbol、候選/feature 順序、decision/cutoff、feature schema/hash/order/width、日期可得時點與 exact `int | None` 值 fail closed；bool 不可當 feature integer。Look-ahead 自查確認 cutoff 必須早於 decision date、feature availability 不晚於 decision，值只由 canonical loader 給出；無新資料查詢、標準化、fit 或 forward/label feature。此 slice 不推測 snapshot references、ModelBinding、日內 availability、model/lineage 或 receipt identity，也未連接 live service/projector。

Dataclass public constructor 只驗結構、derived candidate ID 與 payload digest；若任意 caller 手工建立 facts，`feature_row_sha256` 無法反向證明對應外部 builder row。因此來源完整性只屬於指定 factory 的產物路徑，不宣稱任意 constructed facts 可信。此 API 不是 `PreparedMLInput.v1` 或 `PreparedMLRuntimeInputV1`，不得作 runtime handoff。

Frozen source `app_module/recommendation/ml_preparation_facts.py` SHA-256 `06752E976C340CDEABD9DC89B2E655AD890A60B5EE03F0A99FFA4820CF517151`；test `tests/test_r026_ml_preparation_facts.py` SHA-256 `E8C8EEF258538683A5F22708FB8A6B2416FE994306093338BB88F64AF49E00BA`。Fresh short TEMP route 包含該專項與 `test_ml_historical_feature_builder.py`、`test_ml_historical_feature_computation.py`、`test_prepared_ml_input_contract.py`，**42 passed**；transcript SHA-256 `EB2E268188BF1F2C6DF0F5C2BE82B02CD59D9FF02436A1B5956C24899286AD98`。Scoped mypy 1 source file／0 issues，py_compile 與 targeted diff-check 通過。完整 hashing/canonicalization、look-ahead 自查、runtime fingerprint、測試命令與限制見 [R026 ordered preparation facts QA](../../../06_qa/R026_ORDERED_PREPARATION_FACTS_20260925.md)。R015 獨立 fresh TEMP 重跑同一四檔路由為 **42 passed**，scoped mypy 1 source file／0 issues、py_compile 通過，未發現 P1/P2；root 判定本 preparation facts slice bounded `ACCEPTED_SCOPE`。測試已在共用 inventory 以 `service-oracle-recommendation` 登錄單一 entry；此單一 membership/category 不代表全庫 inventory guard 通過，其他既存 missing/guard failures 仍在。非阻擋後續覆蓋建議為 nested `FactorContribution`／`SourceRef`／`UniverseReference` hash golden 與 factory future-available-date 直接負控。此接受僅限 typed preparation facts，不涵蓋 model/snapshot binding、外部 feature-row source custody、projector no-I/O、receipt parity、A/B runtime handoff 或 TMP-ML-01 retirement。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Historical raw snapshot custody facts（bounded `ACCEPTED_SCOPE`）

新增 `HistoricalRawSnapshotCustodyFactsV1`，由 provider 同次 load 已驗證的四表 schema、normalized query scope 與 typed rows 建立；custody builder 不重查 SQLite/檔案/sidecar。Provider `HistoricalRawSnapshot` 新增兩個 optional、`compare=False`／`repr=False`、預設 `None` 欄位，捕捉原 transaction 已取得的 schema 欄位與實際 normalized query arguments；未增加 SQL、未更動 `query_count`、原 `source_fingerprint` 或現有 `load()` 回傳型別。Schema version 是 `historical-sqlite-schema.v1` 欄位清單 hash，不是 durable revision。

Hash contract：`content_hash` 對完整 table-tagged key→value rows 作 domain-separated hash；`row_identity_hash` 僅 hash table-tagged row keys；`snapshot_id` 再綁 explicit `source_id`、decision/history/cutoff、sorted symbols/industry scope、同次 schema version、row counts/range 與兩 hashes。Canonical JSON 使用 UTF-8、sorted keys、compact separators、`ensure_ascii=False`、`allow_nan=False`，Decimal 以精確文字編碼。Schema/query evidence dataclasses 可由 Python caller 建構，因此 type shape 本身不是真正來源認證；其 custody 含義限於實際 provider/lease load 回傳物件。`SnapshotReference` 投影明示 `source_revision=None`、availability/quality/scope `UNKNOWN`，不宣稱 durable generation、資料完整度或完整 PIT availability。

Look-ahead 自查：原 provider 四個 row queries 仍只讀 history start 至嚴格早於 decision 的前一交易日 cutoff；builder 再驗每筆日期不晚於 cutoff 且早於 decision。沒有 future/label 資料、標準化或新增來源讀取。Fresh short TEMP `C:\r26raw_end_5c6445` 八檔 focused route **90 passed in 13.10s**，pytest log SHA-256 `D2A49FA2374F6882D743F14BC72F9FD692CB2B58A8CE437C631B6C787F2FE3A5`；mypy 3 files／0 issues，py_compile、quant float/look-ahead guard 與 targeted diff-check 通過。完整命令與早期長 TEMP 未解診斷見 [R026 historical raw snapshot custody QA](../../../06_qa/R026_HISTORICAL_RAW_SNAPSHOT_CUSTODY_20260925.md)。

R015 獨立複核以最終 frozen source/test fresh TEMP 重跑同一八檔 route，結果 **90 passed／13.07 秒**；log `C:\r26q\review_raw_20530f90\pytest.log`，SHA-256 `D90BC11D24567A98FB180F46A64B67AFFC92CD4529543C20FCB6291C4C163A62`，mypy 3／0、py_compile 與 guard 通過。`C:\r26raw_final_dd75cc` 對應的是較早 **88 passed** run，不是上方最終收據。另有一筆 86 passed／1 failed 的舊測試摘要，但原始 log／TEMP 路徑未保存，無法確診；R015 僅獨立重現 287 字元 receipt path 的 `WinError 3` 同型路徑失敗與 251 字元短路徑通過，不能據此宣稱已證明舊失敗根因。完整收據與限制見 QA note。

Frozen provider SHA `CCF2FA00EB3A41E319FC67CFF3B64F12A5222D607A3E6FC0E982F28B262017E4`；custody module SHA `A1F9DEB3015AE878090BA9DC7C3252C1CC674D9BE1160E52265668356310E5C0`；test SHA `E0B802A666BAB4A12FFD80583301D99B8C6E2DF8ACC2BB41E2C817CB330109FC`。測試已登錄 inventory 單一 recommendation-oracle entry。Root 依 R015 獨立複核將本切片 bounded `ACCEPTED_SCOPE`；接受範圍僅限同次 provider rows/schema/query-scope typed custody facts，不連接 live service／`PreparedMLRuntimeInputV1`，不證明 raw SQLite generation、source availability、sidecar/model/feature/receipt binding 或任意手工構造 facts 的 provenance。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Experimental same-resolve model-resolution facts（bounded `ACCEPTED_SCOPE`；不得 runtime handoff）

新增 app-side frozen `RecommendationModelResolutionEvidenceV1`，只由既有 `resolve_invocation_projection_capability()` optional path 建立。Fresh consumer 的同次 `reload()` 暫存 pointer/candidate/validated manifest/deserialized model training cutoff/training provenance/ordered probability lineage；外層 pointer bytes before/after、fresh identity 與 caller identity checks 完成後才組 immutable facts。`finally` 清除本切片新增的 transient capture bundle、capture flag 與 runtime profile；capability 仍持有私有 `resolved_consumer`，包含既有 `_loaded_pointer`、probability lineage、training provenance 與模型等投影所需解析狀態。只有 `model_resolution_evidence` property 提供 deep-immutable facts，本切片不宣稱整個 capability 沒有 mutable state。一般 legacy projection、model output 與 receipt contract 未變，沒有 live runtime handoff。

Facts 包含完整已驗 manifest declarations、candidate identity claims、training provenance 狀態、有序 probability lineage digest、artifact recorded library versions 與獨立 runtime profile。缺 release id、artifact-declared qualified class path、quarantine/permission 均明示 unknown；整體保持 `incomplete_unknown_fields`，不構造完整 ModelBinding。Artifact hash contract 仍是 path hash→deserializer reopen→既有 path recheck；loaded bytes hash 為 `None`、same-bytes binding 為 `not_verified`，candidate JSON 路徑重讀也不構成同 bytes proof。

Fresh short TEMP 四檔 route **62 passed／15.02 秒**，log SHA-256 `E6F6D0B2454E5BF6D21B7C8D2E78637A4693DB56971F94D4C828913DFF5B6916`；scoped mypy 2 files／0 issues、`py_compile`、量化 float/look-ahead guard 與本測試 inventory membership check 通過。R015 獨立複核以 fresh short TEMP route 再得 **62 passed**，log `C:\r26m\mrv_e1078bfa\pytest.log` SHA-256 `6158DAA187D57F6551AA132DB2A3CF35BB46FFA580D8871016DFCB453208D29D`；mypy 2 files／0 issues、`py_compile`、quant guard、diff check 通過。複核未發現程式／測試 P1/P2；root 依此 receipt 判定本 slice bounded `ACCEPTED_SCOPE`，範圍僅限 experimental same-resolve model-resolution facts。較長 TEMP 的兩次四檔 route 當時各有既有 service receipt assertion 失敗，但未對 `os.link` 做 instrumentation，當時無法確診。後續本機 Windows unprefixed path-length 診斷見 [model-resolution facts QA](../../../06_qa/R026_MODEL_RESOLUTION_FACTS_20260925.md)；早期四檔 run 未保留底層 OSError/目的路徑，不能斷言與後續六檔 route 的三個 receipt failures 完全同因。那些早期 failures 仍不計入 pass。完整命令、同次資料界線、hash schema 與 residual 亦見 QA note。

Frozen SHA-256：facts module `662A646CFBD0DF60EB361448DE4BBCDC2213F21BC76AF8051070AB8A6395E41A`；consumer `EF0878163FC315D8B9C532BB429247E8034766CECC964810BB5FE9CB2BD790AC`；test `1DF9A984E7C6ED06582068F3B7208F32798750456AD2CD2B9C7494D6DA152DE0`。此 bounded acceptance 不證明 artifact same-bytes、candidate file byte binding、feature/source/receipt binding、pointer ABA、full ModelBinding 或 PreparedML runtime handoff。R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`。

### Same-bytes loader 唯讀可行性審查

此審查未修改 source/test。`SafeShadowModelArtifactLoader.load()` 先在 `ml_module/model_artifact_loader.py:96` 讀 manifest path，再於 `:119` 對 artifact path 執行 `_sha256_file()`，最後於 `:125` 將該 path 交給 deserializer；`_sha256_file()` 另行開檔讀取 `:137-142`。`RecommendationCalibrationConsumer.reload()` 後續再由 `_pointer_candidate_hashes_match()` 對 artifact path 重驗（`app_module/recommendation_calibration_consumer.py:595, 2344-2396`）。Candidate JSON 在初次讀取及 identity/hash 核對時分開讀 path（`:546-555, 2117-2121`）；manifest hash 是 canonical parsed-payload hash，不是原始 JSON bytes hash。Receipt 亦先 hash 再讀取解析（`:2440-2462`），lineage models 沿用相同 loader（`:794-872, 918-939`）。因此既有前後路徑檢查並未證明 hash、parse 與 deserialize 使用同一 bytes，也不能排除 restore/ABA 或最終檢查後競態。

Synthetic TEMP `C:\r26m\toc2\probe.log` SHA-256 `6B46FFBDBFE2D044CDA00FFD870E54FA3C0291F0B506042D11837673FBA5D5D9`，在預設 `joblib.load` 開 artifact 時以一次性 `builtins.open` shim 提供另一份有效 joblib buffer；loader 回傳替代 buffer 模型，而 manifest/path SHA 仍屬原 bytes。此為 hash-then-reopen seam 的合成重現，不是外部程序 race 量測。另以 joblib 1.5.2 比較 synthetic production-shaped model 的 Path、`BytesIO` 與 rolled `SpooledTemporaryFile` load，模型類別及三組 `predict()` 結果相同；probe `C:\r26m\tofmod\probe.log` SHA-256 `B3EE660B0E0B4CE6139CC838FEFE4D0345EC20BCCCA82E21B13AEB87D0744206`。這僅是目前版本的 file-like 可行性證據，不代表任意 artifact/版本或完整 consumer parity。

後續實作採單一 artifact opt-in loader：一次串流到私有 seekable spool 並同時計算 SHA；hash 與已驗 manifest artifact hash 相符後，從同一 spool 以 `mmap_mode=None` 反序列化。舊 `load(path, expectation)` 的 Path ABI 不變，custom Path deserializer 不會被改成 file-object API。此 slice 仍不提供 pointer/candidate/manifest/training-lineage/receipt 的共同 bytes binding，也不等於完整 `PreparedMLRuntimeInputV1` 或 R026/TMP-ML-01 結案。

### Same-bytes artifact loader opt-in（bounded `ACCEPTED_SCOPE`）

新增 `SafeShadowModelArtifactLoader.load_same_bytes_v1()` 與 `SameBytesShadowModelArtifactLoadResultV1`。該結果 dataclass 可由呼叫者手工建構；只有 opt-in loader 建立的實際結果才帶有此次 loader path 的 provenance。它證明的範圍是單一 serialized artifact：`captured_artifact_sha256` 是單次串流進 spool 的 bytes hash；`loaded_serialized_bytes_sha256` 只在預設 joblib 成功從同一 spool 載入物件後存在。Malformed manifest 有直接測試；短寫 guard 僅經程式碼檢視、未直接注入測試。Hash mismatch、I/O、deserialization、path/control 或 model identity 問題依 loader 分支 fail closed。預設 joblib 外的 custom Path deserializer 僅保留舊 API，opt-in 路徑拒絕它。

最終 source/test SHA-256：`ml_module/model_artifact_loader.py` `F5A54A94FBCC3CB4AFDC35C7B4825A4D8A455ED3DB9B518289C07EECC0CBEA1B`；`tests/test_r026_model_artifact_same_bytes_loader.py` `0D8BF557D3B8FEBA503A67CC05632DD3F6E8E5130B63C228725D15417262A938`；inventory `qa/full_app_healthcheck/test_inventory.py` `C1CBABACD0D3EE587AEF7A8F952A2726EE16B924D877178701B7EA11F54A05B7`，新測試僅一筆 `service-oracle-recommendation` entry。最終 fresh TEMP 六檔路由 **60 passed／15.96 秒**，log SHA-256 `7E7B10E959FD78D9A14283F59F1EBF28FA77A9CA83E96F3DB92CC900A5870EF2`；mypy 1 source file／0 issues、`py_compile`、quant/look-ahead guard 與 targeted diff-check 通過。R015 對最終 frozen SHA 另以 fresh TEMP 六檔 route 得 **60 passed**，log `C:\t\r26sb1\pytest.log` SHA-256 `F4157EBF0613934D94C22EEA96D9771B9B850119EEA9AB972E5562606A23636B`；mypy 1／0、compile 通過，未見 P1/P2。Root 依此判本 slice bounded `ACCEPTED_SCOPE`。完整命令與限制見 [same-bytes loader QA](../../../06_qa/R026_MODEL_ARTIFACT_SAME_BYTES_20260925.md)。不同 source SHA 的先前 59-pass 路由不計入最終驗證。

此 slice 未接 consumer active/lineage production 路徑；active/prior 是分別載入的合成案例，不是有序 lineage 集合證明。Pointer、candidate、原始 manifest bytes、training provenance、lineage sidecar、receipt 與 service invocation 未共同綁定。Captured spool 與讀後 path re-resolve 不排除 restore/ABA 或 postcheck 後競態，也不構成 full ModelBinding、PreparedMLRuntimeInput/runtime handoff 或 TMP-ML-01 關閉證據。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

### Capability-only same-bytes ordered artifact lineage（root bounded `ACCEPTED_SCOPE`）

在既有 opt-in `resolve_invocation_projection_capability()` 上新增 lineage artifact evidence；只限此 fresh capability path 使用 `load_same_bytes_v1()` 載入 active artifact 與 ancestor artifacts，legacy `reload()`／service／receipt 行為維持原 loader 與輸出。Capability 的新 `loaded_artifact_lineage` 依 semantic node 順序記錄 null benchmark 或模型節點及各模型實際由同一 spool 載入的 serialized bytes SHA。原 `RecommendationModelResolutionEvidenceV1.artifact.loaded_bytes_sha256` 繼續為 `None`。Active id 必須唯一且位於 lineage 末端，該末端 node 的 normalized root、candidate/model id、manifest/artifact/freeze/dataset hashes 須與同次 active pointer identity 一致；任何 ancestor load／identity 失敗均不發布 partial capability。

Frozen source SHA-256：consumer `app_module/recommendation_calibration_consumer.py` `0E0C9A05C4F8AE82AEAC8BFF4D1F2F134FD0B0F3DEB0082533F3C196C3A06B17`；facts `app_module/recommendation/model_resolution_facts.py` `5898378B4EB6FE0038DDC750607B6DB183F7E48767A3255684A5973CE2040C59`；test `tests/test_r026_invocation_model_capability.py` `29F01813E79B05688CFFB4A31C8CF4A111F768E7C1D63B1D878341719BB25D51`；inventory `qa/full_app_healthcheck/test_inventory.py` `C1CBABACD0D3EE587AEF7A8F952A2726EE16B924D877178701B7EA11F54A05B7`，專項 test 維持單一 inventory entry。

Fresh short TEMP 六檔 route `C:\r26q\capfinal_20260925\pytest.log` 為 **80 passed／17.27 秒**，log SHA-256 `28326B0E56DECC1CB29F681CC5BF1E59CC88E511BAADCAED1EEE748BA5BC5607`；包括 facts、capability、same-bytes loader、舊 loader、PreparedMLInput 與 calibration service tests。命令前後 consumer/facts/test SHA 完全一致。Scoped mypy 2 files／0 issues、py_compile、quant/look-ahead guard 與 targeted diff-check 通過。R015 對 frozen source/test 以另一 fresh short TEMP 六檔 route 獨立重跑為 **80 passed**，log SHA-256 `0D682718C7B213CB6847C777C856591D4CCABB85B84839EA71C43CCB6B36B194`；R015 未發現程式／測試 P1/P2。相同六檔 route 在較長 TEMP `C:\Users\archi\AppData\Local\Temp\r026_cap_samebytes_full_d868197f9ce247599de6dbec9d6db58d` 為 **77 passed／3 failed**，log SHA-256 `CD13FB89B5879314320F39095D7F0A7E964A0639EA1B836039CDF9CD3523D311`。後續 instrumentation 確認三個既有 service receipt assertion 失敗都發生於 `_write_create_only()` 的 `os.link(temp, final)`：目的路徑長 266/266/278 字元，來源 temp 與 destination parent 存在，Windows 回 `FileNotFoundError(errno=2, winerror=3)`。短 TEMP 的同類 case 以 243 字元目的路徑成功，合成 boundary probe 259 字元成功、260 字元同樣失敗。這可歸因於本機 Windows unprefixed path-length 邊界；長路由仍是 FAIL、不計為通過，也不外推至所有 Windows 配置。診斷 log/script SHA 與正式 learning root 較長時仍需另議的路徑支援限制見 [model-resolution facts QA](../../../06_qa/R026_MODEL_RESOLUTION_FACTS_20260925.md)。root 依 R015 獨立複核、短 TEMP route 與修正文檔，接受此 bounded scope。

這是待獨立複核的 experimental capability evidence，不是 runtime handoff、PreparedMLRuntimeInput 或完整 ModelBinding。Artifact-level same bytes 不共同綁定 pointer、candidate JSON、manifest bytes、training provenance、receipt、feature/source 或 service invocation，也不排除 ABA／最後檢查後競態。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Live calibration source identity shadow capture（initial two-sample slice；歷史證據，已由後續 post-projection recheck 更新）

新增版本化邏輯 provider contract ID `twstock-historical-sqlite-four-table.v1`。`HistoricalRawSnapshot` 以 optional kw-only/default 欄位攜帶該 ID，且不參與 equality/repr；production `load()` 明確填入。新 custody join 要求 provider-carried ID 存在，並與 query scope 的 `source_id` 相同；未知或不一致只拒絕新 shadow facts，不改既有 service projection。

`RecommendationService._apply_recommendation_calibration()` 在同一次 provider load 後建立 shadow `LiveCalibrationSourceIdentityV1 | None`。本段時序是初始兩次 sidecar sample 的歷史描述：sidecar before sample、provider `lease.load()`、feature compute、sidecar after sample、model projection、`lease.assert_unchanged()`、shadow composition；receipt persistence 在其後。當時只驗 before/after 兩次 sample 相等，未檢查第二次 sample 後的 sidecar 變更；這一點已由本文末的第三次 post-projection recheck 更新。SQLite lease observation 記錄 projection 後的同連線 postcheck 已返回，但不會回頭延長 sidecar sample interval。Shadow facts 分別保存實際 raw row content/identity hash、四 namespace sidecar aggregate 與 SQLite lease check observation；raw content 改變會改變 row-content hash／shadow identity，row key 未變時 row-identity hash維持不變。這個回傳值是可測的 invocation-local seam；目前 caller 不消費它，也未傳給 model consumer、`PreparedMLRuntimeInputV1`、receipt、legacy capture 或 provenance。Composer exception 為 shadow-only failure，既有 projection/receipt 繼續；receipt及舊輸出仍由既有路徑處理。

實作者 fresh short TEMP 八檔 route 為 **79 passed／0 failed／12.51 秒**，log SHA-256 `6BA71D8DEB72802E5D20FFE7BAA68ECF61AF51F89D297810921F16A4908379F4`。R015 以最終相同 source/test/inventory SHA 獨立重跑八檔 **79 passed**，log SHA-256 `C4E42E7942C58F575AB6D1BE2875971FC86152B05311BF1F4754B7CC1AAE6734`；mypy 4 source files／0、compile/guard 通過，未發現 P1/P2。Root 因此接受此 bounded shadow capture 範圍。完整命令、較長 TEMP 的歷史 75P/3F（該次未直接取得底層 OSError/path 證據）、source/hash/custody 正反測及時序限制見 [live source identity shadow QA](../../../06_qa/R026_LIVE_SOURCE_IDENTITY_SHADOW_20260925.md)。新測試 `tests/test_r026_live_source_identity.py` 已在 inventory 登錄一筆 recommendation-oracle entry。

Frozen source SHA-256：`app_module/recommendation/live_source_identity.py` `3634E4E4FEE5D98B223CFA8598CBB47C14BB0009DDA9A747A48180AC31B2D2DE`；`app_module/recommendation/historical_snapshot_custody.py` `FC00C47719847CEBC25B0DCA7AF25F2EC51A4AB49C182FFA5954FC244373EA51`；`app_module/recommendation_service.py` `29CBCC0AB899BE9491026702493B840EE1BDDFBF8478ABB4EAEEE1663F970DD8`；`data_module/ml_historical_snapshot_provider.py` `1BE1E2F37AE49B9753D52ED5344AD7C1363F165E7E926B8E8616DBA4D00208D7`。Test SHA-256：`tests/test_r026_live_source_identity.py` `DA754EA2C380908AD5B53D30428F8BA0134370F13D299004BB13CA3E02181413`；相鄰 `tests/test_r026_historical_raw_snapshot_custody.py` `205647601F2B6B1A5ECB592884C740F2D3BAF48855AD0AE2021293CAEBF7471F`。Inventory SHA-256 `qa/full_app_healthcheck/test_inventory.py` `0F664715BC0AD2D0D04F4E1C3A8F87233454BDA6B4C435807F9D63843CA4D1D2`。

證據只限實際 service 呼叫順序；lease observation 或 snapshot/evidence 物件可由 Python caller 手工建構，不可說型別本身證明任意物件來自同次 provider 呼叫。`SnapshotReference.source_revision` 仍 `None`，availability/quality/scope 仍為 `UNKNOWN`。Sidecar digest 不是 SQLite row generation；此初始切片不證明四 namespace 與 SQLite 原子、跨資源 ABA、receipt postcheck TOCTOU 或 replay 多次 provider call 共用 durable revision。此 bounded acceptance 不是 runtime handoff 或 TMP-ML-01 retirement；R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Capability-only pointer captured-bytes handoff（bounded `ACCEPTED_SCOPE`；不得 runtime handoff）

Experimental `resolve_invocation_projection_capability()` 將 outer read 捕獲的 pointer bytes 傳入 fresh consumer 的 capability-only `reload()`；一般 `reload()` 與 service 路徑維持既有行為。當 pointer path 在 outer capture 後、fresh reload 前短暫替換時，fresh reload 仍解析 captured bytes；載入後仍執行既有 path-byte、loaded-payload 與 identity checks。能力 evidence 分別記錄 `raw_bytes_sha256`（精確序列化 bytes）與 `canonical_payload_sha256`（既有 canonical JSON payload hash）：不同序列化可有不同 raw digest、相同 canonical payload digest。

Owner fresh short TEMP 五檔路由為 **64 passed**，log `C:\Users\archi\AppData\Local\Temp\r26pc_99321350\focused-route.log` SHA-256 `FDD09C228F5629DDC7A5DB66344A05E53E876C3E4D1B22E093AF167EDB5464EF`；scoped mypy、py_compile、quant/look-ahead guard 與 diff-check 通過。R015 以另一 fresh short TEMP 重跑相同五檔路由亦為 **64 passed**，完成 scoped mypy/compile，未發現 P1/P2；reviewer 未保存獨立 console log，故不提供其路徑或 SHA。Root 依 source/test SHA 未漂移與獨立複核裁定此限定切片 bounded `ACCEPTED_SCOPE`。完整命令及 QA 收據見 [capability pointer captured-bytes QA](../../../06_qa/R026_CAPABILITY_POINTER_CAPTURED_BYTES_20260925.md)。

Frozen source SHA-256：`app_module/recommendation_calibration_consumer.py` `C73CEEC76ECA26924C0858AEEE16E6E4E2E4340CF284224774F0C591257EE8A3`；test SHA-256：`tests/test_r026_invocation_model_capability.py` `780D0F9F301306B938CB1ABF91CD8096B6466515F484162A059467D238F1B312`。此證據只涵蓋 captured pointer bytes；不共同綁定 candidate JSON、manifest、lineage declarations、decision receipt、artifact bytes 或後續 receipt publication。既有 before/after path check 不是 lease，不能排除 A→B→A 或 resolve 後變更；此切片不建立 durable source generation、完整 ModelBinding 或 `PreparedMLRuntimeInputV1`，也不授權 runtime handoff。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Live calibration projection-post sidecar recheck（root bounded `ACCEPTED_SCOPE`）

此 follow-up 在既有兩次 sidecar sample 之外，於 `consumer.project_many()` 返回後、`lease.assert_unchanged()` 前收集第三次 sidecar aggregate。穩定路徑的實際順序為 sidecar 1 → provider load → feature compute → sidecar 2 → projection → sidecar 3 → SQLite lease postcheck → shadow compose → lease close → receipt。只有第三份 typed aggregate 與前兩份相符且 SQLite postcheck 成功，才產生 shadow identity。

第三次 sidecar 回傳變更或丟出例外時，該 shadow identity 為 `None`；已完成的 legacy projection、推薦分數與 receipt 路徑保留。相關測試以 mock receipt sink 驗證 persist 呼叫次數與 persisted 狀態，沒有逐 byte 比較 receipt payload。Source call shape 也顯示 shadow identity 未作為 receipt writer input。若 projection 期間 SQLite commit，lease postcheck 仍 fail closed：撤回 model projection、保留 rule result，且不嘗試 receipt。

Owner fresh TEMP 四檔指定測試路由（含三個 integration nodeid）為 **32 passed**，log `C:\t\r26shadow_final\pytest.log` SHA-256 `A3E416FA532299C349CD76071CCF20E9474F9230020D26E20F078423941D167A`。R023 獨立 fresh short TEMP 同四檔指定路由亦為 **32 passed／0 failed**，log `C:\t\r26post_d3f03293\pytest.log` SHA-256 `687396FFF60A3BC02217D76D8656A4836911A740FECFF751B98F7E48E71BFBF4`；scoped mypy 2 source files／0 issues、py_compile 與 targeted diff-check 通過，未發現 P1/P2。QA note：[R026 投影後 sidecar shadow recheck](../../../06_qa/R026_LIVE_SOURCE_IDENTITY_POST_PROJECTION_20260925.md)。

Frozen source/test SHA-256：`app_module/recommendation_service.py` `947BE55EA2F9A5B7B9325B6D544CD81AD97E9FDA39A9C6DC1F07932090DC8EF6`；`app_module/recommendation/live_source_identity.py` `3634E4E4FEE5D98B223CFA8598CBB47C14BB0009DDA9A747A48180AC31B2D2DE`；`tests/test_r026_live_source_identity.py` `184D79C728C0E782DB0C2C2C1A57F757FD0121B6502C49D57FE32E9646F93582`；`tests/test_recommendation_service_calibration_integration.py` `075B980B7BDC75AF9E25DAC239C1BB12167EAA10F61B25B1CDF896DF02EFA3F6`。三次 sidecar sample 仍是前後觀察，非跨 namespace/SQLite 原子交易；ABA 未防護，第三次 sample 後至 receipt 發布仍有 TOCTOU。此接受不構成 R026／`TMP-ML-01` 完成，也不授權 runtime handoff。

## Capability-only candidate JSON captured-bytes（root bounded `ACCEPTED_SCOPE`）

此 bounded slice 僅涵蓋 experimental `resolve_invocation_projection_capability()` 路徑：active candidate JSON 與有序 ancestor candidate JSON 各自以捕獲的同一組 bytes 解碼、解析並計算 raw bytes SHA-256 與 canonical payload SHA-256；既有 path recheck 保留，且要求 recheck bytes 與解析 bytes 完全相同。任一節點 mismatch 或解析失敗時不發布部分 capability evidence。一般 `reload()`、舊 loader、service、projection 與 receipt 行為未改。

Frozen source SHA-256：`app_module/recommendation_calibration_consumer.py` `49B9889376DBFBC004DDDE0D15F18BCEDE9F4C6FFB83D261452594189499ED48`。Frozen test SHA-256：`tests/test_r026_invocation_model_capability.py` `41824B9C3CF8C524C47FB8FE19D87ECA211341D53FA3D42ACE1B09489A6B0589`。QA note：[R026 candidate JSON captured-bytes QA](../../../06_qa/R026_CAPABILITY_CANDIDATE_JSON_CAPTURED_BYTES_20260925.md)。

Owner 的最終 frozen source/test 五檔 fresh TEMP 路由為 **68 passed**，最後 log `C:\Users\archi\AppData\Local\Temp\r026cjf2_1216dfdd\pytest.log` SHA-256 `AA189E70E3C1060239041513590D3CC2C218297766EB1F77066E8EE21E204CB0`。R015 以另一 fresh short TEMP 五檔路由獨立重跑 **68 passed**，log SHA-256 `3C0DC627DFB6EA9858931E7A961CCF25C6D1D59488FBA75A183F4E4592C6C347`，scoped mypy 2/0，未發現 P1/P2。Root 因此接受上述 bounded scope。

早期 **67 passed／1 failed** 收據保留為 FAIL，不計為通過。R015 確認當時測試每次 invocation 有三次 aggregate collect、共六筆，舊斷言錯把 `aggregate_calls[2]` 當第二次 invocation；該索引仍是第一組第三筆。Frozen test 已改用 `[3]`，後續路由通過，但不抹除早期 FAIL。

限制：此 slice 不建立 candidate JSON、pointer、manifest、artifact、lineage、source、feature 與 receipt 的共同原子快照；path recheck 不是 lease，不能排除檢查後變更或 A→B→A race。它不構成完整 `ModelBinding` 或 `PreparedMLRuntimeInputV1`，不授權 runtime handoff。R026 維持 `IN_PROGRESS`，`TMP-ML-01` 維持 `ACTIVE`。

## Prospective TWSE daily_prices row evidence（bounded `ACCEPTED_SCOPE`）

本前瞻 producer slice 已由 R015 以相同 frozen source/test/inventory bytes 獨立複核：8-file fresh TEMP route **86 passed／0 failed**，log `C:\t\r015_236df3ae\pytest.log` SHA-256 `CC58E88EFC65A456AD2D170344614DE4D69BE49016A74287448718AB59DCCC05`；scoped mypy、py_compile、precision/look-ahead guards 通過，無 P1/P2。Root 判定此 bounded slice `ACCEPTED_SCOPE`。Owner route 同為 86 passed，log `C:\t\twsefin_5d044c\pytest.log` SHA-256 `8FDC73EC0F9061198F9EA348C25797D0AC3C8E83415B40AA2DCAA1C0788977CF`。QA 詳見 [R026 TWSE 前瞻日價列證據](../../../06_qa/R026_TWSE_DAILY_PRICE_SQLITE_ROW_EVIDENCE_20260925.md)。

資料鏈限定為本次 response raw custody bytes → 與 `Response.json()` payload 一致性檢查 → DataLoader 當次 parser frame → 同 serializer 的 CSV projection/readback → scheduled update 的本次診斷 handoff → `daily_price_files` SQLite sync → 對 `projection_columns` 指定欄位做 SQLite `typeof()`／值 readback → create-only sidecar。完整 16 欄同值 TWSE CSV 原樣複製到 TPEX 同日路徑的永久負例證實同鍵來源歧義仍 UNKNOWN；R015 對專用 reader 的 probe 確認合併重複鍵未被事前 dedupe。既有 legacy upsert 維持不變。

UNKNOWN 包括舊/跳過/缺失/invalid/no-data、raw/parser 或 CSV projection 不相符、重複或 TWSE/TPEX 同鍵、未觀察的舊列、SQLite 漂移及 sidecar 發布失敗。既有 `row_evidence` 僅為 sync result 的內部 JSON，不新增 UI／Manual contract。`source_date` 是 requested/ingested date key，未證明 MI_INDEX payload 的實際資料期；`source_published_at` 為 UNKNOWN。`sqlite_projection_row_sha256` 僅摘要指定欄位，不代表整列所有動態欄位。

每列 readback 使用獨立唯讀 transaction，非共同 SQLite snapshot；SQLite、CSV 與 sidecar 非共同 transaction。Windows create-only hard-link／長路徑失敗會令證據 UNKNOWN，短 TEMP 不證明正式 OUTPUT_ROOT 長路徑可用。此 slice 不宣稱來源完整、整日 coverage、歷史 PIT、舊列回填或跨資源原子性。

Final frozen SHA-256：`data_module/twse_daily_price_publication.py` `466CC7C1E22F37C2D83E516BA3F9D3E6A3C4BCA3B37DB72EF3363636F7F40EDD`；`data_module/data_loader.py` `A270A87AF4A37FB8152446A75BAE38EF3076684974BF55B1D90602A3648F0B05`；`app_module/update_service.py` `5D94EB7601BB7E9D53CCD22EFF05A2F8124EF449B7A11B50E73120240E421717`；`scripts/scheduled/run_daily_data_update_quick.py` `B799C1BDF0FE894533F5E1DC55A362AB72037847B71D9FB11B23CB6EDE78886B`；`tests/test_twse_daily_price_sqlite_publication.py` `FAF30E398227F6772DF646CBD27AC744A6E8973B92797AD957CB1545A29DF6A3`；`qa/full_app_healthcheck/test_inventory.py` `B69E7FE019CA27B5593E76E2FA5C040D4D794562A711DF6EAD0CB16EBFEAEEAC`。

Acceptance 僅限合成 prospective producer evidence；R026 仍 `IN_PROGRESS`，`TMP-ML-01` 仍 `ACTIVE`，runtime ML handoff、四表歷史 availability、full PIT 與整體 migration gate 尚未關閉。
## 2026-09-25 — TAIEX market-index row evidence bounded acceptance

獨立複審已關閉 TAIEX row-evidence reader 的兩項 P2，接受此 bounded synthetic evidence slice。Publisher SHA-256 為 `80ECF0BBB74FAE3FF277793BF623CFA54AA5D3A8EC4355743F75AD4B12DB8593`；測試 SHA-256 為 `37E8D42BCBD8C39301C25151A0D2C063B6D4F9138F4547C285B9803EA25C44D2`。獨立四檔路由為 **66 passed**，log SHA-256 `A536859991BB058E88A22EAD0E1DD0BA8862E9B31BD804D5D75CEC78274165FE`。複審確認同一 read transaction 的複合鍵唯一性檢查，以及 SQLite `mode=ro` 缺檔唯讀行為。完整收據見 [TAIEX row-evidence independent review](../../../06_qa/R026_TAIEX_MARKET_INDEX_ROW_EVIDENCE_INDEPENDENT_REVIEW_20260925.md)。

接受僅限該 bounded slice；R026 仍 `IN_PROGRESS`，R028 仍 `BLOCKED`。複審註明測試中兩句新增 CTAS 註解待翻譯為繁體中文；後續若只翻譯註解，須更新測試 SHA，原 66 項行為驗證不因註解翻譯而重跑。

## 2026-09-25 — Capability-only model-manifest captured bytes（準備獨立複審）

新增 opt-in `SafeShadowModelArtifactLoader.load_same_bytes_with_manifest_v1()`，每份 manifest 只讀一次 bytes；raw SHA-256、UTF-8 decode、JSON parse 與 self-hash 驗證皆來自同一 buffer。Capability-only resolve 將 active 與 ordered ancestor manifest evidence 保存在唯讀 lineage，能力返回前逐一重讀路徑並要求 bytes 相同，否則 fail closed。這是前後兩次 bytes observation，不是 lease，不能排除 A→B→A 或最後檢查後的變更。

既有 `load()`、`load_same_bytes_v1()` 與普通 consumer reload/projection ABI 維持可用。此 slice 未接 RecommendationService，未改 decision receipt 或 training lineage；不宣稱 R026/runtime handoff 完成。沒有新增 producer 或全市場 source rebuild；source availability、quality、scope 及缺少的 source revision 繼續依既有狀態表達為 `UNKNOWN`／`None`。

Focused loader、capability、舊 loader 與 manifest 路由 **56 passed**；pytest log SHA-256 `9652284164054B1D6BFDE55E0163FB4C90136A68D29DF805647DBFB2B1F1960F`。Mypy 為 2 source files、0 issues；`py_compile` 與 scoped `git diff --check` 通過。預期 red 在新 API 尚不存在時以 collection ImportError 結束；所有命令、TEMP 隔離、紅綠紀錄與 R026 最短 runtime 依賴見 [capability model-manifest captured-bytes QA](../../../06_qa/R026_CAPABILITY_MODEL_MANIFEST_CAPTURED_BYTES_20260925.md)。

Frozen working-copy SHA-256：

- `ml_module/model_artifact_loader.py`：`95D30503215B022888ED2D94E061DE27B4648F1C60A6C56D90F9B68DDB412F08`
- `app_module/recommendation_calibration_consumer.py`：`1559D1399A36C88883D1CF19AE4F7B96BE962E3F99866015FBFEBE45E9740EF5`
- `tests/test_r026_model_artifact_same_bytes_loader.py`：`17DC26416471327F11675A620292F3619236BEC5F3DA0BC012E80A0186946CFB`
- `tests/test_r026_invocation_model_capability.py`：`6AE9276D31A4ED8FD642830F6916A7BB4C2D9337AB559692E3C47AE632B65605`

以上 hash 對應整份 shared working-copy 檔案，包含先前已存在的 dirty slices；本次 owner 不宣稱那些既有 hunk 由此 slice 新增。本項狀態為 `READY_FOR_INDEPENDENT_REVIEW`，不是 bounded acceptance。全域狀態仍為 C1 engineering Gate `PASS`、R020/R026 `IN_PROGRESS`、C2 未完成、R027 `INCONCLUSIVE`、AB-ML-01 `OPEN`、R028 `BLOCKED`。
