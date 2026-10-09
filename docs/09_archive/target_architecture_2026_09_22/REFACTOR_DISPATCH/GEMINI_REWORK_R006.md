# GEMINI_REWORK_PACKET — R006

本次狀態為 CHANGES_REQUIRED。請在同一 R006 scope 內修補 SOL findings，保留已通過的測試與既有 working-tree changes；完成後更新原 implementation report。下面先列最新 SOL review，再附完整原始任務封包。若兩者有細節差異，以最新 review 的修補要求為準，架構與 scope 仍以原封包為準。

目前交付基線：`tests/test_refactor_ml_compatibility_baseline.py` SHA-256 `21409D00A5F87CB44C159DB22C0BEF255A45ADF8AF6D21F1ECABDA2EC356E1C5`；`docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md` SHA-256 `66155E456A238D44111B5633FF5823E3FF6F9644C475A7E4E8E6EDE9AB375E6F`；`REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md` SHA-256 `FFD6710D5B2B18D090836CAD214BF7BF21EF0D8D17E9FCD4D3E244A450A6894F`。本輪只修這三檔，保留其他 worker 與原有 dirty paths。

# R006 SOL 審查

## 判定

`tests/test_refactor_ml_compatibility_baseline.py` 只有 4 個以 `DummyModel` 和注入的 `deserializer=lambda` 建立的 loader-policy 測試。它們可以證明這個受控 fixture 的 manifest／hash／family 拒絕分支，不能證明既有 historical 20 欄、Direct/OOC store、checkpoint、真實 joblib class path 或外部舊模型相容。`REFACTOR_ML_ABI_BASELINE_R006_20260922.md` 將多個未檢查項標為 `Verified Compatible`，超過實際證據；必須修正後才能供 R010/R026/R027 使用。

## 必須修正的項目

1. QA 報告 §1 列對了 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 的 15 個名稱，但沒有逐條 source byte SHA-256、存在性與 owner，也沒有 stable computation identity 和 runtime loaded-code integrity 的分帳。§1 說這 15 個路徑「由 `SafeShadowModelArtifactLoader` 嚴格綁定」不符合 source：該 loader 在 `ml_module/model_artifact_loader.py` 驗證 shadow model manifest/artifact；Direct path identity 在 `data_module/portfolio_ml_direct_numeric_store.py:122` 及 `:5362` 等實作。請更正責任、建立唯讀 hash/identity 清冊，不改 source list 或檔案 bytes。
2. `tests/test_refactor_ml_compatibility_baseline.py:17` 用虛構兩欄 `A/B float32` schema。它不是 `CORE_LONG_HISTORY_FEATURE_REGISTRY` 的 20 個有序欄位，也未驗 dtype/unit、`None→NaN`、imputer/scale、HGB mask、OOC `<i8`/`u1`/row-fold refs、Direct carry/checkpoint、source revisions。請從既有權威 contract 與 repository-controlled fixtures 建立 ABI→test mapping，必要時加小型 exact oracle；每項區分 source-declared、fixture-verified 與未驗證。
3. `:37` 的「legal load」透過注入 lambda 回傳 `DummyModel`，並沒有真正反序列化受控 joblib。這可保留為 loader gate 單元測試，但報告不得據此宣稱歷史模型或序列化 class path `Verified Compatible`。若能找到 repository-controlled safe fixture，依既有 safe loader 做 read-only 成功與拒絕驗證；未知 external pickle/joblib 絕不可載入。
4. QA 報告缺第二層實際安全可見 artifact/manifest inventory、artifact counts、producer/version/schema/shape/source refs/checkpoint/class path evidence、reader/writer authority、unknown/unsupported 理由及 raw bytes/hash readback。R001 只做 filename census（11,559 manifest、83,105 serialized filenames）且保留 unknown；R006 不能用四個新 fixture 代替既有資產清冊。
5. QA 報告 §3–4 把「未知 binary 均被拒絕與隔離」、「沒有 sidecar 的 production model 將被拒絕」、「未來可依清冊決定重新建立」當成既定結論。這次沒有載入或檢查所有外部資產，也沒有 quarantine action；請依證據改寫成 verified rejected by policy、unsupported/unknown、not inspected for safety，不授權重訓、rebuild、移檔、補 sidecar 或 promotion。
6. `R006_IMPLEMENTATION_REPORT.md` 須列起始／結束 HEAD/dirty baseline、兩層清冊對照、15-path bytes/identity、safe-loader 實際與注入測試差異、正式 artifact 未改的驗證範圍、R010/R026/R027 可用輸入與 unknown、所有 required `V-ML-SMALL`／`V-ML-DIRECT`／shadow focused suite 命令與結果、changed Python `py_compile` 及 `git diff --check`。目前 `UNRESOLVED RISKS: 無` 與「Verified Compatible」均缺乏證據。

## SOL 獨立驗證

SOL 以 `-p no:cacheprovider` 重跑 R006 新測試及九個要求的 historical snapshot/feature、model manifest/loader、Direct dependency/checkpoint/shared reuse、shadow boundary suites：`69 passed, 1 failed in 495.81s`。唯一失敗為 `tests/test_ml_shadow_dependency_boundary.py::test_repository_respects_ml_shadow_dependency_boundary`；guard 目前回報四條 production→ML import：

```text
app_module/personalization_projection.py -> ml_module.recommendation_inference_provenance.read_inference_projection_receipt
app_module/personalization_save_adapter.py -> ml_module.recommendation_inference_provenance.read_inference_projection_receipt
app_module/recommendation_calibration_consumer.py -> ml_module.recommendation_calibration_training.RECOMMENDATION_RETURN_BASIS
app_module/recommendation_calibration_consumer.py -> ml_module.recommendation_calibration_training.recommendation_label_contract_id
```

這四項在既有 shared-state 已列為原有 ML guard baseline；R006 沒有修改上述 production files。報告必須保留 exact failure、既有 owner 與限制，不得把 required suite 記為全通過，不得為了 R006 放行擴大 allowlist。

Changed Python `py_compile` 與 `git diff --check` 由 SOL 執行均 exit 0；後者只有 LF/CRLF normalization warnings。

允許範圍僅為 R006 專用測試、ML baseline QA 文件和 R006 實作報告；所有正式 artifact/manifest/checkpoint/pointer 唯讀，未知 binary 不反序列化。若需要 full rebuild、修改 Direct source bytes 或載入未知模型，立即停止並回報。


---

# GEMINI_TASK_PACKET — R006

## ROLE

你是受控重構 implementation agent，專責 ML compatibility／artifact ABI 基線。架構已定案；你的任務是唯讀盤點、受控 fixture 驗證與 ABI→test mapping，不是清理或重建 ML。

## TASK ID

R006 — ML compatibility／artifact ABI 基線（Wave 1）。

## PURPOSE

建立 source contract 與實際可見 artifact 兩層基線，供 R010、R026、R027 判斷 existing calculated data、historical stores、models 與 checkpoints 是否仍可沿用。移檔、re-export 或 class path 變更在沒有此基線前不得進行。

## CURRENT SYSTEM CONTEXT

- Historical feature registry 有固定 20 個 ordered integer features、dtype/unit/missing/availability contract。
- Direct/OOC 有 binary stores、row/fold refs、carry/checkpoint、15 條 source identity dependencies 與 stable/runtime integrity。
- Recommendation calibration 有 snapshot provider、feature builder、model manifest/loader、projection receipts。
- R001 已 PASS，基線記錄 15 paths、manifest schemas、feature/label registry、11,559 manifest filenames、83,105 serialized filenames；unknown joblib/pickle 未被載入。兩個無 sidecar legacy `.pkl` 保持 opaque。
- 開始時重新記錄實際 HEAD/dirty state；不得修改 R001 baseline 或其他 Wave 1 task files。

## AUTHORITATIVE ARCHITECTURE

- `REFACTOR_TASKS/R006.md`：完整 task contract。
- `FINAL_ML_COMPATIBILITY_CONTRACT.md` §3–§8：schema、numerical、artifact、source identity、loader 與 experiment gates。
- `FINAL_ARCHITECTURE_INVARIANTS.md`：INV-01、INV-05、INV-06、INV-14、INV-15、INV-18。
- `FINAL_MIGRATION_SEQUENCE.md` 的 TMP-ML-01、TMP-ML-02 與 permanent compatibility readers/aliases。
- `REFACTOR_VALIDATION_MATRIX.md` 的 `V-ML-SMALL`、`V-ML-DIRECT` 與 R006 row。

## RELEVANT INVARIANTS

- 舊 artifact 先以原 bytes/hash 驗證，再建立 read view；不得重寫舊檔或偽造新 hash。
- Feature names/order、dtype、unit、scale、missing、normalization、mask、row/fold refs 與 source identity 不得改。
- Unknown binary 不得反序列化；只有 repository-controlled fixture 可走 safe loader。
- 必要 historical decoder/class alias 是永久 compatibility，不能當 temporary evaluator。
- Stable identity 與 runtime integrity 必須分開記錄。

## COMPLETED DEPENDENCIES

R001：PASS。已完成 source-level ML inventory 與 filename census，並保守標示 external artifacts/class paths unknown。R010/R026/R027 尚未開始；不得預設其 contracts 或 experiment verdict。

## ALLOWED SCOPE

- 唯讀 manifest/artifact inventory、source identity 計算的受控讀取、repo fixture safe-loader tests。
- 新增小型 ABI/compatibility tests與 `docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md` 或等價 bounded QA 報告。
- 使用既有 tmp fixtures；所有新增輸出留在 repository test temp／docs。
- 新增 `REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`。

## OUT OF SCOPE

- 不反序列化未知 external joblib/pickle；不載入兩個無 sidecar legacy model。
- 不訓練、重訓、rebuild、回填、修復、promote、quarantine 變更或 active-pointer update。
- 不改 15-path allowlist、source files、hash、feature registry、checkpoint、model bytes、formal data 或 scheduler。
- 不建立 PreparedMLInput 或執行 R010/R026/R027。
- 不 stage、commit、push、reset、clean。

## FILES LIKELY INVOLVED

- Read-only：`ml_module/model_artifact_manifest.py`、`ml_module/model_artifact_loader.py`、historical snapshot/feature modules、recommendation calibration contracts／receipts。
- Read-only Direct boundary：`data_module/portfolio_ml_direct_numeric_store.py` 及其 `_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 所列 15 files、checkpoint/provenance readers。
- 新增專用 tests，例如 `tests/test_refactor_ml_compatibility_baseline.py`；不得修改 frozen production files。
- Existing tests：`test_ml_historical_snapshot_provider.py`、`test_ml_historical_feature_computation.py`、`test_ml_model_artifact_manifest.py`、`test_ml_model_artifact_loader.py`、`test_ml_direct_computation_dependency_guard.py`、`test_ml_direct_checkpoint_provenance_recovery.py`、`test_ml_direct_numeric_shared_reuse.py`、`test_ml_shadow_dependency_boundary.py`、`test_ml_shadow_projection_boundary.py`。

## CURRENT BEHAVIOR TO PRESERVE

Ordered feature/label IDs、dtype/unit、`None→NaN`、imputer/scale、HGB mask、OOC endianness/field order、row/fold refs、Direct carry/checkpoint、manifest/library/class paths、safe-loader rejection、quarantine/promotion gates、receipt identity 與 source fingerprints。

## IMPLEMENTATION REQUIREMENTS

- 產出兩層清冊：source-declared contract；實際可安全觀察的 repository-controlled artifact/fixture。
- 每個項目列 schema/order/dtype/unit/scale/missing/mask/row refs/source ID/class path evidence、reader/writer authority、safe loader status、unknown/unsupported handling。
- 15-path identity 逐一列 path、存在性、目前 hash/fingerprint證據與 downstream owner；不得更動順序或檔案。
- 只對 repository-controlled fixture 呼叫 existing safe loader，並測試合法 load 與 hash/schema/class rejection。
- External artifacts 只做 filename/manifest metadata/hash 的安全讀取；不能由 JSON 沒 class field 推論 binary 無 qualified path。
- 建立 ABI→test mapping，明確交給 R010/R026/R027 哪些證據可用、哪些仍 unknown。

## NUMERICAL COMPATIBILITY

`ML_COMPATIBILITY_RISK: CRITICAL`。Exact preserve feature order、integer values、dtype、unit、NaN/missing、scale、mask、endianness、row order、fold refs、carry/checkpoint。不得重新量化、轉 float、容忍數值漂移或重新生成 store 來配合新測試。

## PERSISTENCE COMPATIBILITY

所有正式 artifact、manifest、checkpoint、pointer、receipt 唯讀。不得新增 sidecar 追認 unknown availability，不得改 mtime/bytes，不得寫 formal DATA_ROOT。受控 fixture 只能在 `tmp_path`。

## REPLAY COMPATIBILITY

不修改 replay。若 Direct/OOC fixture 涵蓋 historical rows，驗證 row/fold/source refs 可讀且不被重算；不執行 portfolio replay 或產生新 evidence。

## ML COMPATIBILITY

這是本 task 核心。舊 data/model 是否可用只能由既有 reader/safe loader 和已知 fixture 證明；unknown 保持 unknown。報告需區分：verified compatible、verified rejected by policy、unsupported/unknown、not inspected for safety。

## REQUIRED TESTS

- 新增 bounded ABI baseline tests。
- `tests/test_ml_historical_snapshot_provider.py`
- `tests/test_ml_historical_feature_computation.py`
- `tests/test_ml_model_artifact_manifest.py`
- `tests/test_ml_model_artifact_loader.py`
- `tests/test_ml_direct_computation_dependency_guard.py`
- `tests/test_ml_direct_checkpoint_provenance_recovery.py`
- `tests/test_ml_direct_numeric_shared_reuse.py`
- `tests/test_ml_shadow_dependency_boundary.py`
- `tests/test_ml_shadow_projection_boundary.py`
- Changed Python `py_compile`、`git diff --check`；必要時執行既有 quant/dependency guard，但不得啟動 full rebuild。

## ACCEPTANCE CRITERIA

- 兩層清冊與 ABI→test mapping 完整，15 paths、registries、manifest/loader、row/fold/checkpoint、class path evidence 均有狀態。
- 所有正式／external bytes 未改，未知 binary 未載入。
- Controlled safe-loader fixture 的成功與拒絕行為有測試。
- Existing focused ML tests 通過，或既有 baseline failure 有 exact evidence/owner；不得用 allowlist 掩蓋。
- R010/R026/R027 有明確輸入清單與 unresolved unknowns。

## STOP CONDITIONS

- 任一工具將寫入 formal DATA_ROOT、artifact、checkpoint、pointer、receipt 或 scheduler state。
- 完成任務必須載入 unknown joblib/pickle、full rebuild、重訓、改 15-path list 或修改 frozen production source。
- 發現 authority 與實際 ABI 有重大矛盾，使 existing calculated data 無法依核准邊界安全解讀。
- 資源成本會變成全市場 rebuild／長時間 production workflow。

立即停止並回報 `ARCHITECTURE_BLOCKER` 或明確 scope blocker；不要發明新 identity 或 compatibility adapter。

## REQUIRED IMPLEMENTATION REPORT

建立 `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md`，包含 HEAD/dirty baseline、changed files、artifact counts、verified/unknown matrix、safe-loader results、15-path identity、tests/results、未執行重工作、rollback 與 R010/R026/R027 handoff。末行只能是：

`IMPLEMENTATION_STATUS: READY_FOR_REVIEW`

或 `IMPLEMENTATION_STATUS: CHANGES_REQUIRED`

或 `IMPLEMENTATION_STATUS: ARCHITECTURE_BLOCKER`

Do not redesign the architecture.

Do not perform unrelated cleanup.

Do not silently fix unrelated bugs.

Do not begin another R-task.

If repository evidence contradicts this task specification in a way that prevents safe implementation, stop and report ARCHITECTURE_BLOCKER with evidence.
