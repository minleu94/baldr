# R004 實作報告

## 範圍與結果

R004 只新增 `tests/test_r004_recommendation_persistence_characterization.py` 與本報告。沒有修改 DTO、repository、save coordinator、SQLite schema 或正式 output/data。所有 JSON、SQLite、failure injection 與 writer 測試都使用 pytest `tmp_path`；每個測試明確檢查 repository paths 位於該目錄之下。

驗證涵蓋 INV-01、INV-11、INV-12、INV-17 的現行 persistence 行為與差距。舊 JSON/SQLite fixture 是最小歷史形狀，由測試在 `tmp_path` 建立，再複製到同一隔離 root 的 repository 路徑；原始 fixture bytes 在 decoder 前計算 SHA-256，load/list 後再次比對原 bytes/hash。

## Characterization 與 failure-window matrix

| 路徑／故障點 | 觀察到的現行結果 | 原 bytes/hash 與復原 |
|---|---|---|
| 舊 JSON + SQLite 複製 fixture | 中文 RecommendationDTO keys 可讀，top-level 舊 result 欄位與 SQLite runs row 可由 `load_result` / `list_results` 讀取。Decimal `600.10`、screening、why-not、liquidity 值保留。 | JSON raw bytes 在 decode 前 hash；讀取後 bytes/hash 相同。Fixture source、copied JSON/DB 全在 `tmp_path`。 |
| 固定 DTO keys / Decimal | 舊 DTO 接受英文 input；歷史 writer 輸出股票欄位中文 keys，result envelope 使用英文 keys。Decimal price 以十進位字串寫出，load 後為 `Decimal`。 | 保存前後 artifact bytes/hash 相同；screening、why-not、liquidity payload readback 相同。 |
| create-only 同 ID、同 bytes | 已有 index row 時回傳同一 ID；identical retry 保留原 JSON。無 index 的 orphan 若文字內容完全相同，可補建 index。 | orphan raw bytes/hash 不變；相同 bytes 可安全 retry。 |
| create-only 同 ID、異 bytes／改 label | **現行差距：**已有 row 時 writer 只查 ID，直接回傳成功，不比較 payload bytes/hash。差異 payload 或 label 被忽略，artifact 和 index label 維持首筆內容。 | 首筆 bytes/hash 保留，但異 bytes 未回報 conflict；此項只記錄舊行為，不視為目標 golden。後續 store 必須做 hash 比較與衝突回報。 |
| legacy replace／label 變更 | 同 ID 的 `save_result` 會改寫 JSON（result_name 在 payload 中），並以 `INSERT OR REPLACE` 更新 SQLite label/metadata。 | 新 payload 有新 bytes/hash，load/list 都顯示更新值。這是既有 replace 語意，與目標的 execution payload / 可變 metadata 分離仍有差距。 |
| create-only artifact create failure | 注入 exclusive file create `OSError`；沒有 artifact 或 index row。 | 無 artifact bytes/hash 可保留。解除故障後，以相同 result/id 重試可成功建立檔案與 index。 |
| legacy replace artifact write failure | 注入目標 JSON 的 `write_text` 失敗；舊 artifact 和舊 index 都保留。 | 舊 raw bytes/hash 完全相同。解除故障後重試 replace 可更新 artifact 與 index。 |
| create-only index insert failure | 注入 SQLite runs `INSERT` 失敗；save 回報 metadata write failure，durable artifact 保留但沒有 index row。 | 保留 bytes/hash 等於預期 payload；解除故障後相同 payload retry 驗證 orphan 內容並補建 index，hash 不變。 |
| legacy replace index insert failure | 注入 `INSERT OR REPLACE` 失敗；SQLite rollback 保留舊 metadata row，但 JSON 已寫成新 payload。`list_results` 顯示舊 label，`load_result` 透過舊 path 讀到新 DTO。 | 新 artifact bytes/hash 保留。相同 replace retry 可更新 index，讓 label/DTO 再一致。這證實 JSON/SQLite 不具跨介質原子性。 |
| artifact-only / index-only | exact orphan 在沒有 row 時不可 load，create-only 可補 row；index-only row 仍會出現在 list，但缺 JSON 時 `load_result` 回傳 `None`。 | artifact-only raw hash 在補 row後不變。index-only 沒有 artifact bytes；須恢復 artifact 或重建/清理索引，舊 reader 不會自行修復。 |
| unknown existing bytes | invalid UTF-8 orphan 的 create-only retry 因無法檢查而拒絕；已有 row 的 malformed JSON 令 legacy replace 拒絕分類。 | 各自先 hash，再嘗試保存/解碼；拒絕後原 bytes/hash 均不變。沒有自動修復或重寫未知格式。 |
| concurrent first writer | 兩個相同 ID、不同 payload 的 create-only caller 都收到相同 ID；`BEGIN IMMEDIATE` 使一份 payload/index 成為首筆，其餘呼叫走既有 ID fast path。僅一筆 index，artifact 等於其中一個候選。 | 勝出的 bytes/hash 穩定。**現行差距：**不同 payload 的競爭者未得到 conflict；此結果不是新 API 的目標 golden。 |
| watchlist failure | coordinator 先保存推薦，再執行 watchlist；watchlist exception 回傳 soft failure，保存結果仍可 load。 | 注入點前後 bytes/hash 一致，無須重新保存推薦。 |
| delivery ACK failure | personalization integration 保存後 ACK append 失敗，UI 保留「推薦已儲存、送達紀錄未完成」狀態；ACK retry/CAS writer failure 不改 DTO。 | 既有整合測試比對 ACK 前後原始 bytes 相等，因此 hash 亦相同；保存結果仍可讀。 |

save-time regime recheck 僅登記為 gap，不列入 golden：`RecommendationSaveRequest.build_result` 建立保存 DTO 時會呼叫 `_regime_snapshot`，現行 helper 可呼叫 `regime_service.detect_regime()`（`app_module/recommendation_save_coordinator.py:180-186`）。R004 沒有把該時點行為認定為目標語意，也沒有修改它。

## 現行 writer / reader 清冊補充

- Replace writer：`RecommendationRepository.save_result`（`app_module/recommendation_repository.py:185`）。主 UI 透過 `RecommendationSaveRequest.persist` 的一般保存分支呼叫（`app_module/recommendation_save_coordinator.py:212-245`；入口為 `ui_qt/views/recommendation_view.py:2672-2683`）。排程 writer 直接呼叫（`scripts/scheduled/run_scheduled_recommendation_snapshot.py:764`）。
- 其他目前直接 `save_result` callers：`scripts/qa_validate_decision_loop.py:117,119`、`scripts/qa_validate_recommendation_tab.py:895`、`scripts/qa_validate_research_journey_qt.py:458-459`。本次以 `rg` 搜尋 `app_module/`、`scripts/`、`ui_qt/` 的 Python source；除上述 coordinator 與 QA/scheduled callers，沒有其他直接命中。
- Create-only writer：`RecommendationRepository.save_result_create_only`（`app_module/recommendation_repository.py:276`）；personalization adapter 的 `save_and_readback` 透過 repository port 呼叫此方法並做 readback 驗證（`app_module/personalization_save_adapter.py:382-392`）。
- Reader：`load_result` 依 index path 讀 JSON 並呼叫 `RecommendationResultDTO.from_dict`（`app_module/recommendation_repository.py:357`）；`list_results` 只查 SQLite metadata（同檔 `:388`）。歷史 JSON/SQLite 不做原地遷移。

## 變更檔案與驗證

- 新增 `tests/test_r004_recommendation_persistence_characterization.py`：11 個 tmp-path 專用 characterization cases，含舊 JSON/SQLite copy、replace/create-only、同 ID 同/異 bytes、並行 first writer、artifact/index-only、兩種 writer 的檔案與 index failure、未知 bytes、watchlist soft failure。
- 新增本報告。
- 必跑命令：

  ```text
  .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_dto_roundtrip.py tests/test_recommendation_save_coordinator.py tests/test_personalization_save_integration.py tests/test_r004_recommendation_persistence_characterization.py -q -o addopts= -p no:cacheprovider
  ```

  結果：`33 passed in 4.93s`。此組包含 ACK failure、ACK retry/CAS、personalization orphan recovery 與 concurrent create-only integration。

- 語法檢查：`.\.venv\Scripts\python.exe -m py_compile tests/test_r004_recommendation_persistence_characterization.py`，exit 0。
- 未執行正式 output/data workflow；沒有新增或修改 production writer、codec、store 或 DB schema。

IMPLEMENTATION_STATUS: READY_FOR_REVIEW
