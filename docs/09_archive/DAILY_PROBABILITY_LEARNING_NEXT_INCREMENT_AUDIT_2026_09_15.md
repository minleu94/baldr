# 每日機率學習下一個有用增量：有界唯讀審計

> **歷史審計快照（2026-10-10）：** 本文依 2026-09-15 的 HEAD 與資料流留下唯讀審計；其優先方案、「尚未完成」缺口及後續標記 landed 的文字不是目前工單／狀態。現況與後續 QA 以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 及 [QA 導覽](../06_qa/README.md) 為準；文中命令僅屬當時審計證據，不代表現行 runner 授權。

日期：2026-09-15
審計 HEAD：`89a264f6`（`feat: wire prospective PIT industry membership callers`）
範圍：只追蹤 `snapshot/outcome → dataset → calibration candidate → compare/retain/adopt/rollback → 隔日推薦/UI` 的真實資料流。未重做 H/I 持倉 read model、J PIT caller、K continuity 或 L official taxonomy producer。

## 審計結論

目前已有可運作的候選訓練、purged walk-forward/OOF calibration、evidence gate 與 rule-only rollback。歷史 bootstrap 也確實會在特定訓練失敗後被傳入第二次 `runner.run()`，不是只有 readiness 數字；證據在 `scripts/scheduled/run_daily_recommendation_learning.py:881-1018` 與 `ml_module/recommendation_calibration_training.py:830-1051`。

真正未接好的主鏈不是「等自然 forward 才能改善工程」，而是：

1. 候選使用的合併 dataset hash（目前正常 Shadow latest 為 `sha256:7883b9b5...`）沒有對應的 immutable `datasets/<dataset_id>/dataset.json`，也沒有在 candidate/run receipt 內閉合指向 bootstrap replay manifest、natural sample IDs 及 source-contract binding。現有 `latest_status.json` 的 `historical_bootstrap.recovered_completed` 是可讀回的旁證，但不是候選 identity 的原子 lineage。
2. capture 有 source-contract binding；隔日 `RecommendationService` 卻直接從 DB 建 feature，將 `data_quality` 固定傳成 `observed`，而 `RecommendationCalibrationConsumer.active_identity()`／`source_trace` 沒有攜帶可核對的 source-contract identity。故 capture 的 provenance 較完整，隔日推薦/UI 的 model probability 尚不能反查到同一個 feature snapshot/source contract。
3. `RecommendationService` 先以 rule `total_score` 建立排序、percentile 並選 top-N，再套用 calibration（`app_module/recommendation_service.py:1170-1282`）。因此目前同一 artifact 雖同時產生 ranking prediction、calibrated probability 和可選 after-cost probability，實際推薦順序仍是 rule ranking；DTO 的預測分數與 ranking method/percentile 可能描述不同模型語義。

單一首選：K/L 穩定後，完成一個有界的「同候選、source-bound 的隔日 projection/provenance receipt」端到端增量：先由最小 immutable merged-lineage producer 固化 training dataset provenance，再由 inference consumer 固化隔日 source provenance 與 projection。這是工程整合增量，不要求先等待自然樣本成熟，也不新增一個永遠因 provenance 缺件而阻擋工程的等待型 Gate；自然 forward 仍只決定 evidence 是否能通過採用門檻。

## Root 與 lane 邊界

| lane | 本次採信的真實位置／receipt | 判讀 |
|---|---|---|
| Formal | `D:\Min\Python\Project\FA_Data\sqlite\twstock.db` 作 learning input；learning output 依既有 contract 留在 Shadow | 不把正式 root 的 query-only source 誤當成正式推薦模型輸出；本審計未寫入正式 root |
| Normal fixed-cost Shadow | `D:\Min\Python\Project\FA_Data_Shadow\scheduled\recommendation_calibration_learning\latest_status.json`，最後寫入 `2026-09-14T05:47:26.7566425-07:00` | `completed / retain_current`；candidate `rec-cal-29c1b6129396a3885a89d080`；training rows `255`；natural matured `0`；reason `natural_forward_evidence_receipt_missing` |
| BankTaiwan estimated Shadow（審計時點） | `D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\recommendation_learning\latest_status.json`，最後寫入 `2026-09-14T19:13:44.7728949-07:00` | `retain_current`、`banktaiwan-electronic-estimate`、`estimated_research_only`；當時無 active pointer／capture，不能冒充正式可用 lane |

### 審計時點與後續 05:50 狀態分開

上表與本文件主要 finding 採用的是審計當時已讀的 2026-09-14 Shadow receipt。主審在審計完成後補報的 2026-09-15 05:50 BankTaiwan 真排程 receipt 為：

`D:\Min\Python\Project\FA_Data_Shadow_BankTaiwan\scheduled\recommendation_learning_banktaiwan\runs\2026-09-15-attempt-001-848408b70b64.json`

其狀態為 `failed`、`cost_scenario_root_conflict`。這是新的排程狀態，不回溯改寫原審計時點的「無 capture」觀測；本文件不據此宣稱 root pollution。主審另指出 `challenger/current.json` v1 缺少 top-level scenario，A 正在重現其被預設為 legacy 後造成的假衝突，應待該 reproduction 完成後再判定根因。

## 使用者需求與真實證據矩陣

| 使用者需求 | 現有 file/line 或 receipt | 狀態 | 尚缺什麼 |
|---|---|---|---|
| 每日市場 → 產業 → 股票形成可追溯候選 | normal Shadow 的 `scheduled_recommendation_snapshot\latest_status.json` 與 capture `recommendation_learning\captures\2026-09-14\scheduled-capture-5f4de77ffb404af2\rec-cal-29c1b6129396a3885a89d080-89496edaf9b19f535b85cc0a.json`；J PIT caller 已在 HEAD | 待驗 | 本次不重做 J；隔日 projection 尚未攜帶同一 source-contract／feature-snapshot identity，且當日 live capture 有 symbol `1528` 的 cross-capture feature/source conflict diagnostics，需由 receipt 明確呈現而非隱藏在 latest status |
| watchlist／持倉可消費買持減係數 | `app_module/decision_presentation.py:269-316` 已區分 ranking score、calibrated probability、after-cost probability；H/I read model 已完成 | 部分完成 | 本次不重做 H/I；尚無證據顯示 learning candidate 的 source-bound projection 已成為 watchlist／持倉共用係數 contract。下一增量應提供共用 projection identity，不另造一套持倉模型 |
| 「80% 上漲機率」後續可驗證 | `ml_module/recommendation_calibration_evidence.py:592-931,1037-1342` capture→natural evidence；`ml_module/recommendation_calibration_authority.py:466-678` compare/gate/pointer | 待自然證據 | 正常最新 receipt 為 natural `matured_sample_count=0`、`retain_current`；這證明採用未被誤宣稱，不是工程未完成。仍需把 capture/candidate/source contract 與隔日 projection 接成同一 lineage |
| 歷史 bootstrap 能真正進 walk-forward 成為 candidate | `run_daily_recommendation_learning.py:881-1018` 將 bootstrap samples 送入第二次 `runner.run()`；`RecommendationHistoricalReplayResult.persist()` 在 `ml_module/recommendation_historical_replay.py:175-239` 寫 immutable replay manifest；normal manifest `datasets\recommendation-dataset-da3d867b06b5436d\dataset.json`，`283` rows，date/row overlap `0` | 程式路徑完成；lineage 待驗 | candidate/run 使用的 merged hash `7883...` 找不到同名 dataset manifest；run receipt 沒有 bootstrap manifest hash、replay path 或完整 sample set。不能僅憑 `recovered_completed` 宣稱 final candidate 已可完整重現 |
| rank、calibrated probability、after-cost probability 同源 | `ml_module/recommendation_calibration_training.py:626-650` 的同一 artifact `return_model`／upside calibrator／optional after-cost model；`app_module/recommendation_calibration_consumer.py:613-820` | artifact 層完成；產品語義部分完成 | `RecommendationService` 的排序先於 calibration；consumer 的 projection `ranking_score_bp` 是 candidate 預測，但 DTO `ranking_method`／percentile 仍可為 rule ranking。需明確同候選 rank contract，或明確標示兩者不是同一排序 |
| 每日調整可影響隔日推薦及 UI 機率 | `app_module/recommendation_calibration_consumer.py:181-346,613-850`；`app_module/recommendation_learning_evidence_projection_service.py:378-...` 是 UI read-only projection | 待整合驗收 | normal lane 有 candidate 產出但 active pointer 為 `rule_only`；Workbench 在審計時點以 BankTaiwan estimated lane 為 primary projection。缺少一份可核對的「本日 candidate → 隔日 projection」receipt，無法把 UI 數字與實際 candidate/source contract 逐欄對上；05:50 新的 BankTaiwan failure 另見上節，不與原 finding 混用 |

## 流程逐段判定

### 1. Snapshot / outcome → dataset

Snapshot、capture 與 outcome builder 的責任邊界已存在：capture 只記錄 cutoff 時可得的 feature、candidate/champion prediction 與 immutable identity；natural builder 後續才依 label availability 重算 outcome。`run_daily_recommendation_learning.py:2646-...` 也只把已成熟、具明確 evidence identity 的樣本帶入 natural training，不把 delivered probability 偷當 label。

缺口在 final dataset identity：`daily_recommendation_learning_runner.py:93-475,561-570` 以合併後 samples 計算 runner dataset hash；這個 hash 與 replay manifest 的 hash 是不同層次，卻沒有一份持久 manifest 把 replay bootstrap、natural rows、dedup 規則與 source contract 綁在一起。

### 2. Dataset → calibration candidate

`RecommendationCalibrationTrainingService.fit()` 有固定 cost scenario、label availability cutoff、purged folds、OOF calibration、untouched evaluation fold 與 candidate freeze/artifact/manifest hash。這是可執行的 walk-forward candidate 生成，不是 readiness-only。

但 candidate `to_dict()`（`ml_module/recommendation_calibration_training.py:720-804`）沒有 source-contract hash/path 或 replay-manifest hash；當日 run receipt 也沒有。故「模型算過什麼」和「這批樣本由哪個 immutable source/replay receipt 形成」尚未同一版本化 contract。

### 3. Candidate → compare / retain / adopt / rollback

Authority 已按 candidate identity、natural evidence、same-date/same-cost、Brier improvement、calibration gap、cooldown 等既有 policy 做 retain/adopt/rollback；normal 最新 decision 是 `retain_current`，active pointer 為 `rule_only`，符合目前無 matured natural evidence 的事實。

這段不應新增一個等待型 Gate。應補的是 candidate 的 provenance identity，使 authority 在既有 verification 中能拒絕「candidate hash 可驗、但 merged training source 無法解析」的模糊 receipt，並讓成功 retain/adopt 的 decision 可被隔日 consumer 直接引用。

### 4. Candidate / pointer → 隔日推薦 / UI

Consumer 已 fail-closed 讀 isolated Shadow pointer/candidate/artifact，且同一 artifact 能輸出 rank、upside calibrated probability、optional after-cost probability；`RecommendationService` 也會把 projection 值放入 DTO。

然而 caller 目前直接從 DB 建 feature、未驗 source contract，並在 rule top-N 完成後才套 calibration。這造成兩個可立即改善的實際缺口：

- probability 能看到 candidate/model/dataset，但不能以相同 source-contract fingerprint 證明是 capture 的那組 feature snapshot；
- 顯示的 candidate ranking score 不等於決定 top-N 的 rule ranking score，`ranking_method` 與 percentile 可能仍是 rule 語義。這不代表一定要讓 calibrated probability 改變 top-N；若正式排序仍由 rule 負責，應明確標示 selection authority／score／percentile 的對應，未獲授權的模型不得影響正式排序。

## 後續增量（最多三項，依優先序）

### P1（首選）：同候選、source-bound 的隔日 projection/provenance receipt（含先行 lineage producer）

**Ownership**：Recommendation/calibration owner 主責 `app_module/recommendation_calibration_consumer.py`、`app_module/recommendation_service.py` 與既有 evidence/receipt schema；QA owner 負責 isolated read-only integration acceptance。K/L owner 只需提供已穩定的 continuity/taxonomy source identity，不改其 producer。

**增量內容**：這是一個前後相接的 bounded end-to-end work item，不是先要求一個尚不存在的 manifest 才能永久阻擋後段。第一步由最小 producer 持久化 merged training manifest，記錄 replay/bootstrap manifest、natural sample IDs、dedup 規則與 merged dataset hash；第二步由 inference consumer 產出 immutable projection contract。後者至少帶有 candidate/model ID、artifact/freeze/manifest hash、training dataset provenance、inference source provenance（source-contract file/content hash、feature snapshot fingerprint/rows hash）、effective pointer date、policy/transform/baseline、ranking score/method/percentile、upside probability、after-cost value/status。兩種 provenance 使用同一 schema/transform compatibility contract，但不把 training dataset hash 與真實隔日 feature hash 強行要求相等。RecommendationService、DTO/UI 只在 identity 與 compatibility contract 可核對時消費；缺失或不一致沿用既有 rule-only/unknown fail-closed，不新增等待自然成熟的 Gate。

**集成驗收**：分兩種情境核對。對同一決策 cutoff 的 capture/readback replay，normal Shadow 的 `rec-cal-29c1...` 必須能逐欄核對 candidate/model/dataset、source contract 與 feature snapshot identity；對真正隔日 projection，feature date、availability date 與 hash 可以不同，必須各自滿足當日 PIT，並能分別解析 training dataset provenance 與 inference source provenance，再核對相同 feature schema、probability transform 與 compatibility contract。另須明確驗證 selection authority、rank score、ranking method、percentile 與 top-N 的對應：若正式排序仍是 rule，candidate probability/rank 不得未授權地改變 top-N。normal、legacy、BankTaiwan lane 不得交叉；formal root 不變；不修改 K/L 檔案、不觸發 scheduler/pipeline、不宣稱 natural evidence 已成熟。

**為何首選**：它直接把每日 learning 的產物接到使用者隔日看到的係數；先補最小 merged-lineage producer，再接 inference consumer，能在一個 bounded end-to-end 驗收中同時解決 training provenance 與 inference provenance，而不把「兩個不同日期的 PIT hash 不同」誤判為衝突，也不強迫未授權模型改正式排序。

### P2：合併 dataset／bootstrap／walk-forward 的 immutable lineage manifest（P1 前段；可獨立先交付）

**Ownership**：daily learning runner／calibration training owner；QA 只驗 manifest 與 candidate/run receipt 的閉合關係。

**增量內容**：作為 P1 的前置 producer，持久化 merged training manifest，記錄 replay/bootstrap manifest hash、natural sample IDs、dedup 規則、完整 row IDs、source quality、training cutoff、purged train/test/evaluation date windows、OOF calibration fold IDs，並把其 hash/receipt path 寫入 candidate 與 run receipt。candidate dataset identity 改由這份可解析 provenance 支撐，不把 `latest_status` 的 recovered metadata 當唯一證據；但不得把尚未存在的 manifest當成永久阻擋隔日 consumer 的新 Gate，應在同一 bounded work item 內完成其後的 projection integration。

**集成驗收**：以目前 normal 或 BankTaiwan Shadow artifacts 驗證可由 candidate 解析到 merged manifest，再解析到 `da3d867b06b5436d` 等 bootstrap replay；重現 2024-09-16 至 2026-02-11 的 bootstrap coverage、20-day causal/embargo boundary、date/row overlap `0`，並核對 candidate fold/evaluation metadata。manifest 缺失或 hash 不符時，該 receipt 標為不可核對並沿用既有 fail-closed，不把此狀態擴張成自然等待；不給 historical replay natural/formal credit，不改排程。

### P3：after-cost lane 的 consumer/provenance 完成

**Ownership**：cost/recommendation owner；維持 normal fixed-cost 與 BankTaiwan estimated research lane 分離。

**增量內容**：把 cost scenario ID/hash、benchmark、cost source、observed/estimated status 從 candidate→capture→natural evidence→consumer→DTO/UI 全程綁定。只有既有真實 fill/liquidity lineage 才可建立 observed after-cost row；不得用 paper 或 estimated 數字冒充 observed。

**集成驗收**：normal 目前缺 observed liquidity 時仍顯示 after-cost unavailable；BankTaiwan 只顯示 fees/tax-only research estimate 且沒有正式 active pointer；若存在 exact observed-cost row，能穿過 capture→natural evidence→comparison，且不改變 price-up lane 的 decision。無需新增自然等待或跨 lane promotion。

## P1 實作與 QA 補報（2026-09-15；shared worktree，未 stage/commit）

本節是上述審計缺口的 bounded implementation follow-up，不回寫原審計時點的 Formal／Shadow receipt，也沒有觸發 scheduler、pipeline 或正式資料重建。P1 已落地的行為如下：

- training lineage 會固化 merged sample/source-group、PIT、feature transform contract、cost lane 與各自的 `training_source_hash`／`training_pit_hash`；candidate 若宣告 P1 欄位，consumer 會以 manifest readback 驗證，部分宣告不會降級成 legacy。
- inference provenance 由 RecommendationService 使用實際 bounded `HistoricalRawSnapshot`、feature rows、日期/availability timing 與 builder contract 建立；`raw_snapshot_content_sha256` 是實際 consumed raw snapshot 內容 hash，另保留 provider fingerprint。training 與 inference source/PIT hash 必須各自有效且不同並不構成衝突，只比較共享 schema/transform/cost/probability contract。
- `RecommendationService → RecommendationCalibrationConsumer → immutable projection receipt → RecommendationDTO/RecommendationResultDTO → AdviceComposer → Workbench UI` 已接通。receipt 使用 create-only path，發布後立即以 receipt hash、decision/candidate/result/cost identity readback；candidate/model identity 或 pointer race fail closed。
- `RecommendationSaveRequest.build_result()` 會優先從 producer 的 `last_run_context.result_id`（及其 UI copied config fallback）建立保存 DTO identity；因此 repository 不再是 receipt identity 的事後補綁來源，legacy 無 run ID 時仍保留既有 `rec_YYYYMMDD_HHMMSS` 形狀。
- RecommendationService 每次 run 若未收到 caller ID，會在 receipt 發布前產生含 UUID 的 `rec_...` identity 並寫入 `last_run_context`；同一次 run 的重複保存沿用該 ID，不同 run 不共用秒級 ID，明確傳入的 ID 則原樣保留。
- save coordinator 會交叉核對 live producer context、frozen copied context、projection receipt metadata 與 recommendation provenance 的 result identity；任何 A/B 衝突都明確拒絕保存，不讓 service context 靜默覆蓋舊 recommendations。
- rule `top-N`／`total_score`／percentile 仍是 selection authority；model `return_bp` 只作 projection/ranking 語義，未改變正式 rule selection。PermissionError、create-only conflict、candidate race 會保留 rule selection，但撤回 model fields，標記 `unavailable`／`not_persisted`。
- 舊 candidate 沒有 P1 lineage 時明確保留 `legacy_unproven`；沒有自然 evidence 或沒有 source binding 不會被自動宣稱 verified，也沒有新增自然成熟等待 Gate。

驗收分成兩個明確邊界，避免把 adapter wiring 誤稱為完整產品 E2E：

- `test_real_consumer_producer_advice_workbench_ui_path` 使用帶 P1 lineage 的 real candidate/authority/consumer，驗證 receipt → Recommendation DTO/round-trip result → AdviceComposer → Workbench detail 的實際 wiring；其 bounded feature row 由 test monkeypatch `HistoricalFeatureBuilder.compute`，`RecommendationResultDTO` 也由 test 組裝，因此不代表真 feature builder → 公開推薦入口 → saved-result repository。
- `test_public_service_real_builder_saves_result_and_reverse_reads_receipt` 使用真 `HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY)` 與相容 20-feature training schema，僅隔離 deterministic strategy scoring；不傳 caller `result_id`，由公開 `RecommendationService.run_recommendation(...)` 在 projection/receipt 前產生唯一 run identity，再由 `RecommendationSaveRequest.build_result()` 從 `last_run_context` 產生相同 `result_id`，以 `RecommendationRepository.save_result` 保存並以 exact `result_id` `load_result`，最後 reverse lookup/readback receipt；測試沒有 post-hoc assignment。它不重複 UI 跨頁旅程，但閉合真 builder → public service → save coordinator → repository/readback → receipt identity。另以 save coordinator 負例驗證 live/frozen/projection receipt identity A/B 衝突會拒絕保存。

兩個正例都驗證 training 與隔日 inference 的 source/PIT hash 不相等但 compatibility 為 `verified`；public service 正例另驗證無 caller ID 的 run identity、同 run 重複保存穩定、receipt reverse lookup；另有 legacy、future row、source/row tamper、cost lane、selection boundary、create-only conflict、candidate race 與 identity conflict 負例。

### 可重現 QA 命令、stdout 與 exit

以下均在 `C:\Projects\PythonProjects\technical_analysis` 執行；pytest warnings 僅為既有 `.pytest_cache` 寫入權限不足，以及既有 scoring engine 的 pandas FutureWarning，均非測試失敗。

1. 語法檢查

   命令：

   ```text
   .\.venv\Scripts\python.exe -m py_compile ml_module\recommendation_inference_provenance.py ml_module\recommendation_training_lineage.py ml_module\recommendation_calibration_learning_runner.py app_module\application_ports.py app_module\recommendation_save_coordinator.py app_module\recommendation_calibration_consumer.py app_module\recommendation_service.py app_module\dtos\__init__.py app_module\advice_composer.py app_module\advice_dtos.py tests\test_recommendation_training_lineage.py tests\test_recommendation_service_calibration_integration.py tests\test_recommendation_save_coordinator.py tests\test_task_loop_03_contract.py tests\test_recommendation_execution_coordinator.py
   ```

   stdout：空；exit：`0`。

2. P1 scoped mypy

   命令：

   ```text
   .\.venv\Scripts\python.exe -m mypy app_module\application_ports.py app_module\recommendation_save_coordinator.py app_module\recommendation_service.py app_module\recommendation_calibration_consumer.py app_module\dtos\__init__.py app_module\advice_composer.py app_module\advice_dtos.py ml_module\recommendation_inference_provenance.py ml_module\recommendation_training_lineage.py
   ```

   stdout：`Success: no issues found in 9 source files`；exit：`0`。

3. lineage／receipt producer 回歸

   命令：

   ```text
   .\.venv\Scripts\python.exe -m pytest tests\test_recommendation_calibration_learning_runner_lineage.py tests\test_recommendation_training_lineage.py -q -o addopts=
   ```

   stdout 摘要：`14 passed, 1 warning in 0.78s`；exit：`0`。

4. P1、consumer、DTO/Advice/UI、daily cost lane 限定回歸

   命令：

   ```text
   .\.venv\Scripts\python.exe -m pytest tests\test_recommendation_save_coordinator.py tests\test_recommendation_training_lineage.py tests\test_recommendation_service_calibration_integration.py tests\test_recommendation_calibration_learning_runner_lineage.py tests\test_daily_recommendation_learning_loop.py::test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags tests\test_daily_banktaiwan_learning_cost.py tests\test_task_loop_03_contract.py tests\test_recommendation_execution_coordinator.py -q -o addopts=
   ```

   stdout：`75 passed, 3 warnings in 37.02s`；exit：`0`。

5. ML shadow boundary

   命令：

   ```text
   .\.venv\Scripts\python.exe scripts\check_ml_shadow_boundary.py
   ```

   stdout：`{"inspected_files": 509, "shadow_only": true, "violations": []}`；exit：`0`。

本補報沒有寫入 Formal/raw data、沒有執行正式 runtime/scheduler、沒有 stage/commit/push；測試建立的 receipt 僅在 pytest `tmp_path`，正式 runtime receipt path contract 為 `<learning_root>\\inference_projection\\<decision_date>\\<safe_candidate>\\<receipt_digest>.json`。

## 審計界線與停止通知

原審計只讀重看 HEAD、程式與既有 Shadow receipts；當時未執行測試、GUI、pipeline、排程，也未修改程式或 shared Manual。上述 P1 補報是後續 bounded implementation，仍未碰 Formal/raw data、未 stage/commit。後續補報的 05:50 failure 僅作狀態增補，未由本審計或 P1 QA 觸發或修改。

P1 實作與限定 QA 完成；請主審停止本子任務後續施工與觀察。05:50 的主流程由主審依既定安排自行只讀觀察，本審計與 P1 QA 未觸發或等待該流程。
