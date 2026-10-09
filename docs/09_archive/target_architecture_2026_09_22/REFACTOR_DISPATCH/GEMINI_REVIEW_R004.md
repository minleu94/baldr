# GEMINI REVIEW PACKET — R004

## ROLE

你是 R004 的獨立 cross-model reviewer。這是唯讀 review；不要改寫 production 或 tests，不要實作後續 R-task。你的責任是核對 Luna Max 的 persistence characterization 是否忠實記錄現況、是否足以保護後續 R009/R012，以及是否有 scope creep、錯誤 golden 或測試缺口。

## REVIEW TARGET

R004 — 保存、舊格式與故障復原 characterization，Wave 1。Implementer：LUNA_MAX；reviewer：GEMINI。R001 已 PASS；R009/R012 尚未開始。

## ORIGINAL R004 SPECIFICATION

### Task context and purpose

現有 `RecommendationRepository` 同時有 replace 與 create-only；JSON artifact 及 SQLite index 沒有跨介質原子性。Personalization 測試已有並行／orphan 案例，但需形成新保存路徑的獨立 oracle。R009/R012 會發布新 wire 與 save API；格式或中斷語意若未先固定，回滾後可能無法讀舊結果。

### Allowed scope

新增 `tmp_path` persistence characterization；建立舊 JSON/SQLite fixture copy 與 failure injection。不得建立新 codec/store、修改 DB schema、刪除 replace 或寫正式 output。

### Current behavior to preserve

DTO English/Chinese keys、Decimal price、screening/why-not/liquidity、create-only identical bytes recovery、unknown existing bytes 拒絕、concurrent first-writer、watchlist/ACK soft failure。

### Implementation objective

明確記錄 replace 與 create-only 不同語意；測 artifact-only/index-only、same ID/hash、same ID/different bytes、label/name 變更、load/list 結果。

### Compatibility and acceptance

- INV-01、INV-11、INV-12、INV-17。
- 保存的 projection/receipt IDs 與 hash 視為不透明受驗欄位，不重新推論。
- 全部 fixture 在 `tmp_path`；原 bytes 先 hash 再 decode；unknown 格式保留原檔。
- 跑 DTO roundtrip、save coordinator、personalization save integration；注入 file/index failure 與並行寫入。
- 原路徑的成功與拒絕均可重跑；save-time regime 重查標為 gap，不得當成 golden；不得正式寫入。
- 報告需列每個 failure point、保留 bytes/hash、恢復方式與目前 replace callers。
- 若無法隔離 writer 或 fixture 會讀正式 root，必須停止。

## RELEVANT ARCHITECTURE INVARIANTS

- **INV-01**：原始資料、歷史 artifact、模型與 checkpoint 不因重構改 bytes、ID 或 hash。
- **INV-11**：canonical typed contract 是唯一新 schema；未知 schema/type 拒絕，禁止無型別核心擴充字典。
- **INV-12**：新保存採 create-only；同 ID/hash 冪等、異 hash 拒絕；metadata 不進 execution hash；SQLite index 可重建。
- **INV-17**：過渡 runtime 機制必有 ID、owner、caller、刪除條件；永久歷史 decoder／artifact ABI 支援與 temporary bridge 分帳。

注意：R004 是 current-behavior characterization。若現況不符合 INV-12，測試應清楚記為 gap，不可把錯誤現況升格成目標 golden，也不可在本 task 修 writer。

## IMPLEMENTATION REPORT

完整報告：`REFACTOR_REPORTS/R004_IMPLEMENTATION_REPORT.md`
SHA-256：`97B63DE0815ECC713C4D2C04F027BC7B39756B62ADE4210B8A3B4859B79674C6`

報告聲明只有兩個新增檔案，production 零修改。11 個新 tests 使用 `tmp_path`，涵蓋：

1. 手寫舊 JSON＋SQLite copy fixture；decode 前 hash，load/list 後 bytes/hash 不變；中文 DTO keys、Decimal、screening/why-not/liquidity 可讀。
2. 現有 writer 的 English envelope／Chinese recommendation keys 與 Decimal roundtrip。
3. create-only 同 ID／identical bytes retry；orphan identical bytes 補建 index。
4. **現況 gap**：create-only 已有 index 時只查 ID，同 ID／different bytes 或 changed label 仍回傳成功，保留首筆 artifact/index，沒有 conflict。
5. legacy replace 會改寫 JSON 並 `INSERT OR REPLACE` 更新 label/metadata。
6. create-only artifact create failure：無 artifact、無 index；解除 injection 後可 retry。
7. legacy replace artifact write failure：舊 artifact/index 保留；retry 後更新。
8. create-only index insert failure：artifact durable、index absent；identical retry 補建 index 且 hash 不變。
9. legacy replace index insert failure：新 artifact＋舊 index 的非原子窗口；retry 後一致。
10. artifact-only、index-only、unknown bytes preservation。
11. concurrent first-writer：保留其中一份 payload、單一 index；**現況 gap** 是 losing different-payload caller 沒收到 conflict。
12. watchlist exception 為保存後 soft failure；artifact/hash 不變。
13. delivery ACK failure 由既有 personalization integration tests 覆蓋，保存結果不變。

報告把 save-time regime re-detect 明確列為 gap：`RecommendationSaveRequest.build_result` 現況可在保存時呼叫 `regime_service.detect_regime()`；R004 沒有把它認定為目標語意。

報告的 writer/reader 清冊包含 `RecommendationRepository.save_result`、scheduled/QA/UI callers、`save_result_create_only`、personalization adapter，以及 `load_result`／`list_results` 的不同讀取行為。

## CHANGED-FILE / DIFF SCOPE

- `tests/test_r004_recommendation_persistence_characterization.py` — 新增，SHA-256 `F7F9F5E34CB9653511E4B2BC4A7280CFCCECD0F9A54BB3F54D153972F4A1E321`。
- `REFACTOR_REPORTS/R004_IMPLEMENTATION_REPORT.md` — 新增，hash 如上。
- R004 沒有 production diff、schema change、正式資料寫入或其他 task file edit。
- Shared worktree 同時有 R002/R007 與既有 dirty paths；它們不屬於本 review，不得歸因於 R004。

## TESTS ALREADY EXECUTED

Implementer 與 SOL 均執行：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_dto_roundtrip.py tests/test_recommendation_save_coordinator.py tests/test_personalization_save_integration.py tests/test_r004_recommendation_persistence_characterization.py -q -o addopts= -p no:cacheprovider
```

SOL readback：`33 passed in 4.99s`。Changed test `py_compile` exit 0；`git diff --check` exit 0，只有既有 LF/CRLF warnings。

## REQUIRED REVIEW

請實際讀取兩個 review target 檔案並對照 repository production code；不要只相信本 packet 或 implementation report。逐項檢查：

- acceptance criteria 與所有 required cases 是否真的有 deterministic oracle；
- old bytes 是否在 decode 前 hash，unknown bytes 是否確實保留；
- replace/create-only、artifact-only/index-only、same/different bytes、label、load/list 是否正確分帳；
- file/index failure injection 是否注入正確 seam，且沒有 accidentally bypass 真實 transaction/rollback；
- concurrency test 是否有穩定 barrier、沒有 sleep、沒有把 non-deterministic winner 當 fixed winner；
- watchlist/ACK soft failure coverage 是否足夠，是否有報告聲稱超過測試證據；
- save-time regime/source re-read 是否只列 gap、沒有被 golden 正當化；
- behavior preservation、數值／Decimal 語意、architecture compliance、dependency direction；
- persistence compatibility、replay compatibility、ML projection/receipt opaque identity；
- hidden state、duplicated ownership、scope creep、production/formal path access；
- `_make_json_serializable` 用於 expected bytes 是否會造成共用 production helper 的盲點，現有手寫 legacy fixture與 explicit field assertions 是否足以補償；
- tests 是否不足以讓 R009/R012 安全開始。

## REVIEW OUTPUT

提供精確、可定位的 findings；若要求修改，指出檔案、案例與缺失證據。不要在 review 中重寫任何 code，也不要要求處理 unrelated code。你的回覆最後必須且只能選擇以下其中一個狀態：

`REVIEW_STATUS: PASS`

`REVIEW_STATUS: CHANGES_REQUIRED`

`REVIEW_STATUS: BLOCKED`
