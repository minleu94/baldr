# 2026-10-06 文檔整理與恢復 manifest

> Baseline dev `07da90c164d762966302008c0be8efbb0d9b4cfe`；main `a8c81bf534952cdf35d35a57d9e367c0fa10c817`。本輪文檔 writer 與 cleanup／功能 audit 分區；不改產品碼、assert、金融公式、Task 或資料。

## Coverage 與處置

本段所稱 Coverage Pass 已依當時明示的 repo 整理 scope 完成，只表示本 manifest 所列 2026-10-06 baseline 與處置範圍，Patch Pass 當時承接該授權；不表示後續全庫內容治理、最終 links／anchors scan 或 Graphify refresh 已完成。Must：Snapshot 現況／歷史分離、主索引與 docs README、全清單、資產登記、歸檔 manifest／QA／graph 維護；Should：root README／Navigation 入口、結構規則、Manual／Architecture 現況判讀、7 個壞鏈；歷史 plans/specs 原地 lifecycle 登記。產品方向／6M／長期 maturity／外部藍圖／Legacy Carryover 保持 scoped authority，文檔整理不更改其 Gate 或優先序。

| old | new／保存位置 | 日期／狀態／superseded-by | 恢復 |
|---|---|---|---|
| `docs/00_core/PROJECT_SNAPSHOT.md` 原累積全文 | [PROJECT_SNAPSHOT_HISTORY_20261006](PROJECT_SNAPSHOT_HISTORY_20261006.md) | 2026-10-06 historical；superseded-by 現行 Snapshot | baseline Git 原檔或本輪 original_bytes；目前入口只保留現況 |
| `docs/00_core/DOCUMENTATION_INDEX.md` 原日期化索引 | [DOCUMENTATION_INDEX_HISTORY_20261006](DOCUMENTATION_INDEX_HISTORY_20261006.md) | historical；superseded-by 現行 Index／全清單 | baseline Git 原檔或 original_bytes |
| `docs/README.md` 原日期化補充 | [DOCUMENTATION_ENTRY_HISTORY_20261006](DOCUMENTATION_ENTRY_HISTORY_20261006.md) | historical；superseded-by 現行 docs README | baseline Git 原檔或 original_bytes |
| `docs/superpowers/{plans,specs,prompts}/**` | 原路徑保留 | 原地 execution trace；現況由 Snapshot／QA 判讀 | 原 bytes 不變；詳細 lifecycle manifest 見其 README |
| `output/plans/baldr_product_experience_plan_20261004.md` | 原路徑＋本輪 `original_bytes/baldr_product_experience_plan_20261004.md` | 唯一需求原 bytes 保留；沒有 supersede 或抹除需求 | `unique_plan_backup.json` 的 SHA／bytes 核對後復原，原件已存在即不覆蓋 |
| `output/qa/**` 的 failed raw／JUnit／receipts | 原路徑 | immutable history／原始證據；未移、未改 | 原 writer 的 lineage／backup；summary 更正不更改 raw |

三份全文封存只調整搬移後的相對連結並加歷史標頭。原始 bytes、SHA256 與 exact mapping 保存於 `output/qa/baldr_documentation_reorganization_20261006/{original_bytes,archive_mapping.json}`；baseline Git 亦可恢復 tracked 原文。這不是刪除唯一證據或改為已完成。

Git autocrlf 可能正規化 LF／CRLF；需要原檔案 exact bytes 時使用 `original_bytes` 備份與 SHA 核對，Git baseline 提供版本內容恢復。`preservation_check.json` 已核三份封存除新標頭／連結目標外全文相同，並再核唯一 plan 原 bytes 未改。

## 壞鏈處理

Refactor 歷史提及的 `app_module/recommendation_save_coordinator.py` 與 `decision_module/stock_screener_sqlite_reader.py` 已在 `b6c58ca546840b67993c9e63bc207323763b8772` 演進；保留當時路徑文字與 Git parent 恢復指引，不把舊 assessment 改寫為現行 code。R008 reviewer 三個相對連結修成上一層 FINAL 分冊。不存在且 Git 無命中原名的 `passed_20260922_latest_status.json` 只標 missing historical fixture；原 SHA／bytes／測試結果保留，不能用別的 canonical fixture 假裝同 bytes。

## 公開與本機分界

[全清單](DOCUMENTATION_CATALOG_20261006_HISTORY.md) 列 tracked 文件，不含私人 DB／模型／raw output。本機 ignored 盤點與 raw SHA 保存於本輪 QA；容量與恢復摘要看 [資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md)。原 graphify query memory 不移、不清；新圖僅在本輪 ignored 分區。未 push／main merge，文檔 commit 不表示 main 已同步。
