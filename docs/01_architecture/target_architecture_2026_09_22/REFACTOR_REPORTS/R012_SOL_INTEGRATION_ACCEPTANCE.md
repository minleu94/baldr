# R012 — SOL 整合驗收

> **時點／狀態導覽（2026-10-11）：** `TASK_STATUS: PASS` 僅指本文列出的 R012 save/store/query scope；結尾「R013/R014/R016/R017 仍待 C1 gate」是驗收當時的快照，不是目前 C1 狀態。R031 後續 disposition 將 R012 列為 `ACCEPTED_WITH_CREATE_ONLY_STORE_SCOPE`，C1 列為 `ACCEPTED_WITH_SCOPED_SYNTHETIC_GATE`；詳見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。不外推為整體 refactor 或產品 Gate 通過。

TASK_STATUS: PASS

R012 的新 writer 採 `RecommendationExecution` → canonical codec bytes/hash → 專用 `execution_artifacts/` create-only artifact → 與舊 writer 共用 SQLite identity claim → 可重建查詢索引。相同 ID/hash 冪等、不同 hash 拒絕；新舊 writer 不能把同一 ID 各存一份結果。保存不讀 service `last_*`、不重算 regime/score/ML。舊 JSON/SQLite 的 load/list、純舊 replace 與相同 bytes 的 legacy orphan recovery 保留；正式資料與模型 bytes 未改。

凍結 source/test SHA（SHA-256）：`ports.py` `BB16251D819FDBA3738EDB02A822974071F6C9E98C99E8B6D48AA86139ECEDCD`、`persistence.py` `A271C4DE1417833087E0B7F4D70B3D8D4A169467CC8162BCCD6787B9AEB4A8C5`、`save.py` `7C84ABD5EDFA3158BFD90E8C73B5143D28A3B814954D6FA4275C502269B4855B`、`queries.py` `2B6962BFC640E5B92E2358D00FB47EFADE0D0C09677C785D6C327992A785238F`、`result_artifact_store.py` `5E002148D2BA0AF56AA275AAF497F45046CE456255D55453BE14F124D616EE64`、狹義修改的 `recommendation_repository.py` `35672320FCABAB9C8C4D44DC57408887927329AF126EA0068BF1DA0032ABBD35`、R012 tests `3B2EB2B54A74DCF70668ED1ACD1B650D8E4303ABEC904791F59D4E813DE36B63`。SOL 逐檔核對，與實作者凍結報告相符。派工時 HEAD `fbc4047b`；驗收時共享 HEAD `bcde4094` 的中間 model-repair commits 僅在其他路徑，沒有 R012 owner overlap。無 stage/commit/push。

初版獨立審查與 SOL 找出四項缺口：重建索引的 stale inventory 刪掉已保存 B、canonical writer 搶走 legacy file-only orphan ID、大小寫變體繞過 POSIX 共用路徑約束、重建 SQLite 故障誤報 artifact 損壞。實作者在原 scope 回修；[獨立 Luna 複審](R012_LUNA_REWORK_REVIEW.md) 對新凍結版為 `REVIEW_STATUS: PASS`。SOL 核對惰性 inventory 在同一 `BEGIN IMMEDIATE` 內消費，並檢視 barrier 並行測試；legacy orphan/new writer/legacy retry、配置大小寫、錯誤注入皆有具體測試。ML/codec 專項唯讀複核亦未見 receipt、Decimal、schema 或歷史解碼漂移。

SOL 在最新共享 HEAD 重跑 R004＋codec＋R012：**73 passed、3 skipped**；加入 capture source binding 與 personalization save integration 的組合：**88 passed、3 skipped**。R012 `--collect-only` 為 **47 cases**，沒有重複 top-level test 名稱。三個 skip 均因此 Windows 帳號沒有建立 symlink/reparse 測試 link 的權限（`WinError 1314`），不是測試 PASS。changed-file `py_compile`、五個新 source 的 scoped mypy、`git diff --check` 通過；`git diff --check` 只有既存換行格式提示。

可變 label/notes/persisted_at 的權威在獨立 metadata table；僅 artifact identity/hash/schema 的 index projection 可由 artifact 重建。整個 SQLite DB 遺失時不能還原原 metadata，query 明示缺值而不猜。Windows 目錄項目斷電耐久尚未實機證明；本輪證據涵蓋程序中斷、partial persistence 與同 ID/hash retry。受控 legacy orphan 檢查對含 traversal 的 opaque ID 可能 `lstat` 舊 API 曾指向的 root 外路徑項目 metadata，但不讀 bytes 或寫該位置；此為具名相容限制，不以本輪改寫舊 ID/path 契約。正式 schema publication/rollback 的 [限制與做法](R012_SCHEMA_PUBLICATION_ROLLBACK.md) 已記錄，未在正式資料根目錄 apply。

R012 符合 Wave 5 task acceptance；此 PASS **不等於 C1 或 Wave 6 放行**。TMP-REC-03 的舊保存 caller bridge 仍在，明確由 R015 關閉；R013/R014/R016/R017 仍待 C1 gate。
