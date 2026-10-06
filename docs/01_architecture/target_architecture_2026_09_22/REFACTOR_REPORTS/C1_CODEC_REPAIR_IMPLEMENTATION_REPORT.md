# C1 Codec Repair Implementation Report

- **狀態：** `U2_ACCEPTED_FOR_U3`
- **範圍：** C1 U2 codec slice。此狀態不代表 C1 PASS，也不釋出 Wave 6；C1/Wave 6 仍為 `BLOCKED`。
- **允許變更：** `app_module/recommendation/codec.py`、`tests/test_recommendation_execution_codec.py`、本報告，以及下列合成 fixture。
- **未變更：** contracts、execute、persistence、queries、scheduled、ML、其他測試；未 stage／commit／push，未讀寫正式 `DATA_ROOT`。

## 實作摘要

### 唯一 canonical writer

- `encode_execution()` 是 canonical execution artifact writer，使用 `EXECUTION_SCHEMA_REVISION = 2` 輸出 revision 2；固定 schema 仍為 `recommendation-execution.v1`。canonical UTF-8 JSON、排序 keys、緊湊 separators 與 header/payload hash 規則沿用原 codec。
- 不新增 revision 1 writer 或從歷史讀值重建舊 artifact 的路徑。既有 `encode_legacy_recommendation()` 仍只供 legacy DTO 的 `to_dict()` 字典相容使用，不輸出 canonical execution artifact。

### Canonical read 與來源 revision

- 讀取支援 `(1, 2)`；兩個 revision 都先驗 canonical payload hash，再驗 schema/revision，並直接比對原始 bytes 與 parsed document 的 canonical UTF-8 serialization，最後才建構 typed contracts。空白或 key 順序不同的 JSON 即使 payload hash 一致仍拒絕。未知 schema、revision、record/enum type、record 欄位與失配 hash 都拒絕。
- `decode_execution(raw_payload)` 維持原有 `RecommendationExecution` 回傳 ABI。
- 新增 `decode_execution_envelope(raw_payload) -> ExecutionReadEnvelope`，供需要來源 metadata 的 reader 使用。Envelope 保留 decoded `execution`、原 header `schema_version`／`schema_revision`、canonical `payload_hash`、原始 bytes 的 `raw_payload_sha256`，以及未改寫的 `raw_payload`。例如 U4 可用 `decode_execution_envelope(raw).schema_revision` 取得來源 revision；不可用 `envelope.execution.schema_revision` 推斷，該 class-level 值代表目前 contract revision。
- revision 1 缺少 U1 新增的 optional 欄位時依 contract defaults 解為 `None`／既定 unknown 值。讀取不呼叫 `encode_execution()`，不重序列化來源 bytes，也不改 header 或 raw SHA。

### U1 typed wire allowlist

新登記的 record／enum wire ID：

| Contract | Wire ID |
|---|---|
| `RecommendationConfigSnapshot` | `recommendation.config-snapshot.v1` |
| `RecommendationResultConfigSnapshot` | `recommendation.result-config-snapshot.v1` |
| `StrategyConfigIdentity` | `recommendation.strategy-config-identity.v1` |
| `UniversePolicyIdentity` | `recommendation.universe-policy-identity.v1` |
| `UniverseSnapshotIdentity` | `recommendation.universe-snapshot-identity.v1` |
| `RecommendationUniverseIdentity` | `recommendation.universe-identity.v1` |
| `SnapshotCohortCoverage` | `recommendation.snapshot-cohort-coverage.v1` |
| `SnapshotCohort` | `recommendation.snapshot-cohort.v1` |
| `RecommendationRunEvidenceIdentity` | `recommendation.run-evidence-identity.v1` |
| `SnapshotCohortCoverageStatus` | `recommendation.snapshot-cohort-coverage-status.v1` |

rev2 roundtrip 覆蓋 Request caller config 原文/hash/limits、Context full result-config 原文/canonical hash、strategy/universe identity 與 spec、完整 SnapshotCohort/coverage/enum、evidence identity、aware clocks，以及 `RecommendationItem` 新增數值與文字欄位。Decimal scale（例如 `91.2300`、`20.00`）保留；result config 以 raw JSON string 原樣 roundtrip。

## 歷史 revision 1 fixture

新增 [recommendation_execution_rev1.json](../../../../tests/fixtures/recommendation_execution_rev1.json)。該 5,033-byte fixture 以舊 schema 欄位和 `schema_revision: 1` 手工組成，未從 rev2 writer 生成或降版；包含 rev1 時的完整 execution/request/context/decision/item/quality/event 欄位，不含 U1 新增欄位。

- Raw bytes SHA-256：`dbd3c2194ef53c2fee3e41e772187d2453c52237328aa179833282e0cc76a52b`
- Canonical payload hash：`sha256:db61aabb2b388609d49c9daae77ee54ae389a51c9f12acd59f329a7f1cf265b5`
- 測試固定兩個 hash、來源 revision、raw bytes、decode 前後 raw SHA，並 monkeypatch writer 確認歷史 rev1 read 不呼叫 current writer。新增欄位缺失結果逐欄驗為 None。

## Legacy 與下游限制

- 保留既有 `decode_legacy_result()`／`decode_artifact()` legacy DTO read path。若 caller 要證明歷史 legacy bytes 未被改動，必須提供獨立可信的 `expected_sha256`；自行讀取後計算的 read-time SHA 只能標識當次 bytes，不能被宣稱為歷史驗證或新 writer 輸出。
- **U4 persistence/query 尚未修復：** `rebuild_index`／`read_verified` 目前有 metadata revision 綁定 current、以及將 decoded artifact 交給 `encode_execution()` 比 raw 的行為。本 U2 沒有修改那些檔案。U4 應對 canonical artifact 使用 `decode_execution_envelope()` 取原 header revision、raw bytes 與 hash；歷史 rev1 不得拿 current writer 結果作 canonical equality oracle。U4 仍負責 single query/read seam、index/payload hash custody 及 legacy read-time hash 標示。
- 未執行 scheduled wrapper parity、U3 capture、persistence/query 或 consumer readiness；這些仍屬 U3/U4/U5 後續 gate。本報告不宣稱 C1 PASS。

## 獨立審查結論

Luna Max 獨立審查：**`Accept U2 only`**，未列 P0／P1／P2。審查確認 codec focused suite `21 passed`、codec + contracts `88 passed`，且 `py_compile` 通過。此接受僅涵蓋 U2 codec slice。

後續仍須完成並獨立驗收 U3 invocation capture、U4 persistence/query 與 U5 consumer readiness；在完整 C1 gate、獨立 review 和最終驗收完成前，**C1/Wave 6 維持 `BLOCKED`**。

## 驗證紀錄

| 命令／檢查 | 結果 |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_codec.py tests/test_recommendation_contracts.py -q -o addopts=` | **88 passed** |
| `.\.venv\Scripts\python.exe -m py_compile app_module\recommendation\codec.py tests\test_recommendation_execution_codec.py` | **通過** |
| import smoke：載入 `decode_execution`、`decode_execution_envelope`、`encode_execution` 並確認 revision 常數 `(2, (1, 2))` | **通過** |

第一次 focused run 因測試 fixture 使用不合法的全 None strategy identity 而失敗；改用 identity builder 後，第二次 run 僅餘一個 wire assertion 索引錯誤。之後加入 raw canonicality guard 與 whitespace/reordered bytes 負例；最終 focused run 為 88 passed。第一次 import smoke 的展示表達式把 postponed annotation 字串當成 type 查 `.__name__` 而失敗；模組 import 本身成功，改為 callable/API smoke 後通過。
