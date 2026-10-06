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

REVIEW_STATUS: CHANGES_REQUIRED
