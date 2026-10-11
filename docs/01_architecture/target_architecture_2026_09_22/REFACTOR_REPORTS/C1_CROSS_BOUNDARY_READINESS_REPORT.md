> **C1 子階段歷史狀態**：本文末尾的 C1 reopened／Wave 6 blocked 描述只代表 SCHEMA/AB synthetic review 當時狀態；後續 [C1 checkpoint](C1_CHECKPOINT.md) 記錄 C1 Engineering PASS、Wave 6 released。本文的合成證據限制仍有效，整體現況及未完成限制以 checkpoint 為準，不構成產品或生產授權。

# C1 Cross-Boundary Readiness Report

> **範圍狀態：SCHEMA/AB synthetic evidence only，原 reviewer 已接受限定範圍；SOL 複審確認無剩餘 P1/P2。** Reviewer 接受 source-binding 修復後的限定測試證據。此接受只涵蓋 SCHEMA/AB synthetic evidence，仍不是 C1 full gate、C1 PASS 或 Wave 6 release 證據。

## 範圍與檔案

新增以下隔離測試及人工合成 fixtures；未修改 production、其他 owner 的測試／fixture、scheduled wrapper 或正式資料：

- `tests/test_c1_schema_compatibility.py`
- `tests/test_c1_execution_artifact_ab_interleave.py`
- `tests/fixtures/c1_cross_boundary/schema_rev1.json`
- `tests/fixtures/c1_cross_boundary/ab_interleave_scenarios.json`
- `tests/fixtures/c1_cross_boundary/fixture_manifest.json`

本次未遇到 production owner blocker，也不需要變更 production contract、codec 或 query seam。

## SCHEMA-P/N

SCHEMA-P 以 pinned synthetic rev1 bytes 經 `RecommendationExecutionQueries.get` 讀取。測試核對 schema header、payload hash、raw bytes/hash；已存在的 `Context.decision_at` 以原 timezone/value 保留。rev1 缺少的 request/result config snapshot、cohort、strategy/universe/evidence identity、`created_at` 與 `available_at` 維持 `None`／unknown。讀取時將 persistence writer 替換為會立即失敗的 guard，確認 query 不會把 rev1 重編為 rev2；讀回後 artifact bytes 仍與輸入逐 byte 相同。

SCHEMA-N 分別將 schema version、revision、record type 改成未知值，以及提供錯誤 payload hash；四種輸入皆由 query 明確拒絕，磁碟 artifact 和 store readback bytes 均保持原樣。未知 type/header 的測試先重算 envelope payload hash，避免把 header/type 拒絕誤判為單純 hash mismatch。

## AB-P/N

AB-P 對同一 `RecommendationService` 發出 A/B 兩個並行 invocation，兩次都經 invocation-local capture 與同步 postprocess callback。recommendation generator 從實際傳入的 frame 取股票代號與收盤價，並用該代號選擇合成 fixture 分數，不再忽略 frame。測試依 A/B 原 frame 及更新後 frame，各自按 cutoff、availability、排序和 canonical JSON hash 規則計算獨立 expected `market_data_fingerprint`；在兩份 capture 到達 callback 後更新來源 provider frame，並覆寫共用的 `last_run_context`、`last_screening_matrix`、`last_calibration_projections`。execution 的 `legacy_invocation_context` event 必須綁定各自原 frame 的 expected fingerprint，且與更新 frame fingerprint 不同。A-then-B 及 B-then-A 兩種保存順序都各自以 `RecommendationSaveService.save_execution` create-only 保存，確認 rev2 envelope，再對每個新 artifact 恰呼叫一次 `RecommendationExecutionQueries.get` 作主要 readback；讀回 event 必須等於 execution event，讀回檔案 bytes 必須等於保存後 bytes。

保存及 readback 逐筆比對 opaque result ID、Request snapshot／limits、as-of date、created/available/decision clocks、post-run config marker、cohort、推薦股票與 Decimal 分數、save payload hash、artifact raw SHA-256、原 frame fingerprint，以及 receipt binding 的 result ID、candidate、decision date、stock、receipt hash、cost hash。query 回傳 verified 的 synthetic projection rows。主要保存後 readback 對 A、B 各一次；之後交換 result ID 的 create-only 衝突案例另呼叫一次 `queries.get(B)` 確認原 B artifact 仍可驗證；兩個 receipt 交叉綁定負例各自以隔離 store/query 驗證 fail closed。這些後續確認不計入主要 readback 次數。

AB-N 另外將 A execution 分別綁到 B receipt path/hash，及只將 A receipt hash 換成 B hash。兩種 artifact 都可保存為合成測試輸入，但 U4 query 均標示 receipt `unavailable`、不回傳 projection rows，並保留可驗證的 execution 本身。這些測試覆蓋錯誤身份／hash 的 fail-closed readback，不表示 C1 producer 或 inference readiness 已完成。

## 合成 receipt 範圍

測試透過既有 `tests/test_recommendation_training_lineage.py` 的 synthetic verified training/provenance fixture，建立固定的 projection rows 和 immutable receipt；寫入後先用 `read_inference_projection_receipt` 驗證 hash、candidate、result ID、decision date、stock 與 cost scenario，再於 U4 execution readback 時重新驗證已綁 receipt。**這是合成 receipt artifact 的實際持久化及 identity/hash readback，不是 real ML inference 或真實模型輸出。** 測試沒有載入 active model、執行 live inference、promotion、scheduled main 或正式資料讀取。

## Fixture hashes

| Fixture | Bytes | SHA-256 |
|---|---:|---|
| `schema_rev1.json` | 5,033 | `sha256:dbd3c2194ef53c2fee3e41e772187d2453c52237328aa179833282e0cc76a52b` |
| `schema_rev1.json` canonical payload hash | — | `sha256:db61aabb2b388609d49c9daae77ee54ae389a51c9f12acd59f329a7f1cf265b5` |
| `ab_interleave_scenarios.json` | 1,480 | `sha256:5112d36aafb67e323bb14759e7cfbda6b5d448cc8a008fd764d2ae63a7d500e3` |
| `fixture_manifest.json` | 1,035 | `sha256:2d01afed6389142863725d4594d16c48eafc89059aac8a92ea09c740cd157bf1` |

SCHEMA 測試將 rev1 raw SHA、payload hash 和 byte length 固定在 assertion；AB 測試將 scenario byte length 和 raw SHA 固定在 assertion。獨立計算的 cutoff-bound source fingerprints：A 原 frame `sha256:316a780cb4f467357bf5d783d88190b3abfe771f8d10cb4d814f7c1907b046bf`、更新 frame `sha256:fb3cfb1704daf40044842ec051f3a2ae86d104cbe95649fb1945d3fa5a7330e4`；B 原 frame `sha256:9d28660d9dd174ceabc7693066a8aac3b58a7a10824fd1e2700db27079f4828a`、更新 frame `sha256:acdd9f4749867a48a184d8e1dbff0aed0d0fd70f256661225af74116576519b8`。主 execution event 保存原 frame digest；查詢後該 event value 與 artifact bytes 不變。manifest hash 是本次檔案記錄值，不單獨構成 production trust root。Receipt artifact 是在 pytest `tmp_path` 內依合成 provenance 建立，內容由 U4 query 讀回並驗證，不作靜態 fixture hash 聲稱。

## 驗證

聚焦測試命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_c1_schema_compatibility.py tests/test_c1_execution_artifact_ab_interleave.py -q -rs -o addopts=
```

結果：修復後完整聚焦重跑為 `7 passed in 1.50s`；skip 為 0，沒有跳過案例或待說明的 skip 理由。AB 專項重跑為 `2 passed in 1.19s`。

語法檢查命令：

```powershell
.\.venv\Scripts\python.exe -m py_compile tests\test_c1_schema_compatibility.py tests\test_c1_execution_artifact_ab_interleave.py
```

結果：成功，無輸出。未執行完整 C1 gate、全套 V-REC/V-EXEC/V-CODEC/V-PERSIST/focused V-ML-SMALL、scheduled wrapper parity、正式資料驗證或獨立 Luna/SOL 最終審核。

## Gate 限制

這份結果可作為 SCHEMA/AB 跨邊界案例的聚焦測試輸入與審核材料，**不足以作為 C1 full gate 證據**。它不覆蓋 R014 forward consumer、R016 全部 legacy/query 類型、R017 replay bridge、ML ABI、整合測試矩陣或最終獨立審核。因此在本次 SCHEMA/AB 審查時，C1 仍維持 reopened；本報告本身不宣稱 C1 PASS，也不授權 Wave 6 release、formal、promotion 或 production。後續狀態依文首所連 C1 checkpoint 判讀。
