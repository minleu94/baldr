# R012 Luna 回修版獨立複審

> **時點／狀態導覽（2026-10-11）：** 本文的 `PASS` 僅適用其凍結版本上的 R012 bounded gate；「不放行 C1 或 Wave 6」是本複審當時的下游狀態。R031 後續將 R012 列為 `ACCEPTED_WITH_CREATE_ONLY_STORE_SCOPE`，並記錄 C1 的 scoped synthetic gate 已接受；詳見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。此處四項 finding 的修復與 Windows skip 限制仍按原範圍保留。

REVIEW_STATUS: PASS

**狀態：PASS（僅 R012 gate；不放行 C1 或 Wave 6）。** 逐項重查前一輪四項 CHANGES_REQUIRED，並檢視實作、交易順序與新增回歸測試。未修改 production/test 檔案。

## 凍結版本與驗證

派工指定的 SHA 前綴均相符：`persistence.py` `A271C4DE`、`result_artifact_store.py` `5E002148`、R012 tests `3B2EB2B5`、ports `BB16251D`。上一輪其他相關凍結檔仍相符：save `7C84ABD5`、queries `2B6962BF`、legacy repository `35672320`。

唯讀 focused 測試：R004 persistence characterization、R009 execution codec、R012 persistence suite：**73 passed, 3 skipped**。三個 skip 位於 R012 tests `:1140, :1171, :1191`，皆因 Windows runner 建立暫存 symlink/reparse link 時回報 WinError 1314；這些情境沒有正向執行結果。

## 原四項 finding 的回修證據

1. **Rebuild stale-inventory lost update — 已修。** app 將惰性 `validated_inventory()` 傳給 store（`app_module/recommendation/persistence.py:308-355`）；store 先取得 `BEGIN IMMEDIATE` 再消費 inventory（`data_module/result_artifact_store.py:945-957`），並在同一交易內替換 projection（`:986` 起）。canonical publisher 也在發布 artifact 前先取得相同 writer lock（`:467` 起），故等待中的 B 不會在 inventory 快照後先取得成功保存。新增可控交錯測試 `tests/test_r012_recommendation_artifact_persistence.py:632-690` 驗證 B 等待 rebuild commit 後保存，且 A、B 及 metadata 均可讀。
2. **Legacy file-only orphan 被 canonical claim 搶占 — 已修。** `publish_artifact()` 在 `BEGIN IMMEDIATE` 內檢查 legacy row 與直接 legacy 路徑上的 orphan（`data_module/result_artifact_store.py:467-474`）；檢查以 `lstat` 判斷占用，不讀取檔案內容（`:413-440`）。新增測試 `tests/test_r012_recommendation_artifact_persistence.py:1009-1043` 驗證 canonical save 拒絕、原 bytes 不變，之後 legacy create-only 可恢復該 orphan。
3. **大小寫路徑別名 — 已修。** store 配置要求 exact `execution_artifacts`、`runs`、`recommendation_runs.db` 名稱及同一 parent（`data_module/result_artifact_store.py:113-127`）；配置測試涵蓋 root、artifact 與 DB basename 的大小寫變體（`tests/test_r012_recommendation_artifact_persistence.py:236-257`）。
4. **Rebuild SQLite write error 誤分類 — 已修。** inventory 的 `ResultArtifactIndexError` 映為 `ExecutionIndexRebuildError`（`app_module/recommendation/persistence.py:337-340`）；projection transaction 的 store/SQLite write failure 也保留 index-rebuild 類別（`:362-369`）。新增 trigger 注入測試 `tests/test_r012_recommendation_artifact_persistence.py:692-722` 證明錯誤分類且既有可用結果仍可讀；inventory store failure 分類另由 `:724-741` 覆蓋。

## Opaque ID 與 legacy `lstat` 判定

`artifact_name_for()` 仍以 ID 的 UTF-8 SHA-256 命名 canonical artifact（`data_module/result_artifact_store.py:145-154`），所以 slash/traversal 不會改變新 artifact 的 root 位置。legacy orphan 保護則依舊 API 的直接 `<id>.json` 對應組出路徑並呼叫 `lstat`（`:413-440`）。因此帶 `../` 的 ID 在該相容性檢查上可能探測到 configured `runs` 以外的**路徑項目 metadata**；不會讀取該項目的內容或在該路徑寫入。

我用臨時資料重現：ID `../../../outside-runs` 遇到臨時 store root 之外、但仍在該臨時目錄中的 `outside-runs.json` 時，canonical save 會保守回報 legacy file-only identity conflict；原檔 bytes 未讀寫，canonical hash artifact 未建立。此行為可能讓任意外部檔案造成 false collision，但也對應 legacy repository 過去對同一 ID 使用的原始 `<id>.json` 名稱，避免把未知舊檔誤當新 identity。以目前 R012 的舊 orphan preservation 相容範圍及無 hostile local filesystem actor 的 gate 威脅模型，判定為**具名相容性限制，非 R012 blocker**。若日後 result ID 由不受信任外部輸入控制，需另定義 legacy 路徑安全政策；本輪不藉此改寫既有 ID/legacy 契約。

## 具名 durability 限制

POSIX hard-link 建立後若 parent-directory `fsync` 失敗，artifact 可能已出現在程序可見的目錄，但其斷電後持久性未獲確認；流程不會回報 `INDEXED`，會以 write failure 返回，且相同 ID/hash retry 可檢查原 artifact 並恢復。故 write failure 不代表「保證沒有檔案」，也不應宣稱該 artifact 已耐受 power loss。這是 JSON/SQLite 不能跨介質原子提交的已知故障窗，不構成本輪新增阻斷 finding。

**最終判定：** 四項回修均有對應程式與測試證據；Windows symlink/reparse 正向測試仍需在具備權限的 runner 補跑。R012 可通過本輪 gate，但本報告不代表 C1/Wave 6 放行。
