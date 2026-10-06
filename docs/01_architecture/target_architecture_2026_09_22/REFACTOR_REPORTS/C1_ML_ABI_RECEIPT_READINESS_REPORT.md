# C1 ML ABI／Receipt Readiness Report

日期：2026-09-23  
Owner：Luna Max  
狀態：**ML synthetic readiness only**；C1 gate 仍未通過，Wave 6 仍為 BLOCKED。

## 範圍與依據

本報告補上 C1_CONSUMER_READINESS_TEST_MATRIX.md 第 36 列的 ML-P／ML-N 測試，新增：

- tests/test_c1_ml_abi_receipt_readiness.py
- tests/fixtures/c1_consumer_readiness/ml_abi_manifest.json
- 本報告

測試依 C1_UPSTREAM_REPAIR_SCOPE_RULING.md、matrix 第 36 列、FINAL_ML_COMPATIBILITY_CONTRACT.md 第 3、8 節，以及已接受的 U1、U2、U3、U4、U5a reports 建立。只使用人工合成值。OOC numeric store ABI 與 recommendation inference receipt 是兩個獨立 schema；本測試不把兩者合稱為同一 receipt。

## 驗證內容

### ML-P：合成產物與精確 readback

- 公開 PortfolioMLOutOfCoreStoreBuilder 接收 5 筆合成 source rows，依 manifest 順序產出 price.momentum_bp、risk.volatility_bp；values 為 <i8，scale 為 [100, 10000]，獨立 missing mask 為 u1。第一列缺值保留 integer storage value 0 並由 mask 1 標示；observed 值 mask 為 0，不把缺值解讀成真零。
- 核對 source manifest logical hash、source shard 壓縮檔 hash、每個 OOC artifact 的 bytes／SHA-256、SQLite row ID/date，以及 4 個 fold 完整 little-endian int64 (year_ordinal, local_row_index) train/test refs、manifest row count／shape 與 row 順序。正例使用 fixture 的 row-reference shape [1, 2]、first row [0, 0] 作精確 oracle。
- 公開 model artifact manifest／loader 的成功案例核對有序 feature ID、dtype/unit、實際 library versions、序列化 artifact hash、載入 model identity 與 shadow-only flags。
- 公開 provenance／receipt builders 產生 tmp-only receipt。receipt 綁定 result_id=c1-ml-result、candidate ID 與 candidate package manifest/artifact hashes、decision date、cost hash、按序 projected symbols。candidate package bytes 由公開 receipt reader 驗證；U4 RecommendationExecutionQueries.get() 只回傳已驗的兩筆 projection rows。
- query readback 前將 provenance、receipt build/persist functions 替換為會立即失敗的測試 guard；readback 成功證明此 seam 只讀封存 receipt，沒有重新 build 或重新推論。Rule DecisionBatch 在成功及失敗案例均保持原樣。

### ML-N：逐項變異後 fail closed

- OOC public builder 拒絕 sample scale 與 registry scale 不符、observed=false 但仍帶 value_int=0、以及 source shard bytes 與 pinned source hash 不符；負例各用新 tmp output root，失敗前不會發布該 root 的 latest_manifest.json。
- model loader 對 feature 順序、dtype、library version、manifest schema、artifact bytes/hash、deserialized model identity 的錯誤均回 rule_only_fallback，不回傳 model，且維持 formal_rule_unchanged=true、production_action_allowed=false。
- U4 query 對 receipt feature 順序、dtype、unit、missing policy、source/dependency hash、receipt schema、candidate artifact bytes 的 mutation 回 unavailable 與空 projection rows；candidate、cost、projected symbol order、row hash、receipt hash 的 binding 不符也回 unavailable 與空 rows。以上均保留封存 execution 與原 Rule decision。公開 receipt reader 另拒絕 result ID、candidate、date、cost 或 symbol 的錯誤 expected identity。

## Fixture 完整性

ml_abi_manifest.json：**2,230 bytes**；固定 SHA-256：

    c143b1c545319d2e3092e5d4a23ee45d86919be0093c8b889a5866a1e86b1f05

測試以固定 digest 與 byte length pin fixture，並逐 byte 比較載入時 bytes 與測試結束時的 readback bytes。fixture 沒有被測試改寫。

## 執行結果

| 驗證 | 結果 |
|---|---:|
| .venv\Scripts\python.exe -m pytest tests\test_c1_ml_abi_receipt_readiness.py -q -o addopts= | **25 passed (1.23s)** |
| .venv\Scripts\python.exe -m pytest tests\test_ml_model_artifact_manifest.py tests\test_ml_model_artifact_loader.py -q -o addopts= | **11 passed** |
| .venv\Scripts\python.exe -m pytest tests\test_recommendation_training_lineage.py -q -o addopts= | **11 passed** |
| .venv\Scripts\python.exe -m pytest tests\test_recommendation_service_calibration_integration.py -q -o addopts= | **12 passed** |
| .venv\Scripts\python.exe -m pytest tests\test_c1_legacy_query_readiness.py -q -rs -o addopts= | **17 passed, 1 skipped** |
| .venv\Scripts\python.exe -m py_compile tests\test_c1_ml_abi_receipt_readiness.py | **passed** |

唯一 skip 是 tests/test_c1_legacy_query_readiness.py:439 的 symlink 負例：目前 Windows 測試環境建立 symlink 回傳 [WinError 1314] A required privilege is not held by the client。新 ML readiness 測試沒有 skip。這是環境權限 skip，不是測試失敗。

## 邊界與限制

- Repo 目前沒有公開的 OOC numeric store reader；ml_module.allocation_out_of_core_training_service._NumericStore 是 private。測試不呼叫該 private class，也不新增私有 stub；改由公開 builder 發布後，依公開 manifest 指定的 dtype／shape／hash 直接核對 binary bytes、SQLite rows 與 fold refs。因此這驗證 producer artifact ABI，不等同 downstream runtime loader 的完整驗收。建立 public OOC reader 需另立授權範圍。
- 合成 recommendation receipt 的 training_provenance.status 是 legacy_unproven；本輪驗證 inference source/dependency hashes、candidate package identity、receipt binding 與 U4 read view，不宣稱通過 verified training lineage readiness。test_recommendation_training_lineage.py 的 11 項基線另行通過。
- OOC positive case 只在全新的 pytest tmp_path 新建一次 latest_manifest.json 並檢查其 run/hash 指向；沒有讀寫或更新任何既存／active／production pointer。OOC 負例、model package、candidate package、receipt、execution store 均留在各自測試 tmp root。未觸及 DATA_ROOT，沒有執行 scheduled main，沒有跑模型推論、訓練或 full-market rebuild，也沒有改寫歷史 receipt。
- 本結果只代表小型 synthetic readiness。依 scope ruling，C1 gate／Wave 6 仍 blocked；不得外推成正式 artifact inventory、正式資料相容或放行結論。

沒有修改 production、其他 tests／fixtures 或既有 U4／U5a fixtures／manifests；沒有 stage 或 commit。
