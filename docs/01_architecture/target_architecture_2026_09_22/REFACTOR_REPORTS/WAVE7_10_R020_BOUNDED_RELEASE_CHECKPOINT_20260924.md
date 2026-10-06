# Wave 7–10 至 R020 bounded-release checkpoint

**日期：** 2026-09-24
**用途：** 依既有 gate evidence 校正 Wave 6–14 現況摘要，並記錄 Wave 11 R020 的 bounded implementation release。
**裁決：** **可開始 R020 bounded implementation；不代表 Wave 7–10 full closeout、C2 通過或 R020 acceptance。** R027 維持 `INCONCLUSIVE`、`AB-ML-01` 為 `OPEN`、`TMP-ML-02` 為 `ACTIVE`，因此 R028 繼續 `BLOCKED`。

## 裁決範圍

本 checkpoint 是依 execution order、validation matrix、task specs、已存在的 task／wave reports 與 migration ledger 所作的 gate-status reconciliation。它不新增測試結果，也不把單項 `ACCEPTED_SCOPE` 擴大解讀為整個 wave 完成。R020 有自己的持續驗收條件；R027 的非 ML R020 blocker 判斷以 R020 對 R017／R019 evaluator core 的 dependency，以及 Wave 11「R020 不改 execute／ML adapter」的檔案界線為依據。詳見 [執行順序](../REFACTOR_EXECUTION_ORDER.md)、[驗證矩陣](../REFACTOR_VALIDATION_MATRIX.md)、[R020 task](../REFACTOR_TASKS/R020.md) 與 [FINAL migration sequence](../FINAL_MIGRATION_SEQUENCE.md)。

## 逐波 gate 證據與現況

| Wave | 已有 gate evidence | 仍 ACTIVE／blocked | 本 checkpoint 判讀 |
|---:|---|---|---|
| 6 | C1 engineering gate 通過；R013、R014、R016、R017 各自獲 `ACCEPTED_SCOPE`，Wave 7 已 `RELEASED_FOR_IMPLEMENTATION`。見 [Wave 6 final gate](WAVE6_FINAL_GATE_REPORT.md) 與 [Wave 6 scope ruling](WAVE6_SCOPE_AND_OWNERSHIP.md)。 | Wave 6 報告明列 42-file／656-test combined run 未完成；正式資料、ML promotion 與 production deployment 不在此 gate。 | Wave 6 release 證據足以作後續 bounded engineering 的前置 gate；不宣告未完成的 combined run 或其他 gate 通過。 |
| 7 | R015 `ACCEPTED_SCOPE` 且 `TMP-REC-03` 已退休；R021、R023、R025 各有 bounded `ACCEPTED_SCOPE`。證據：[R015](R015_IMPLEMENTATION_REPORT.md)、[R021](R021_IMPLEMENTATION_REPORT.md)、R023 QA（開發收據見dev） 與 [R025](R025_IMPLEMENTATION_REPORT.md)。R027 outcome 已有獨立完整報告。 | `TMP-STR-01`、`TMP-ML-02` 為 `ACTIVE`；R027 為 `INCONCLUSIVE`、`AB-ML-01` `OPEN`。 | Wave 7 任務 gate／實驗 outcome 有可追溯記錄；這不是 Wave 7 full closeout。R027 無 `PASS`，故依 execution order 不釋出 R028。 |
| 8 | R022 bounded gate 為 `ACCEPTED_SCOPE`，見 [R022 implementation report](R022_IMPLEMENTATION_REPORT.md)。 | `TMP-RGM-01` 保持 `ACTIVE`，caller inventory 與 compatibility exit 留待 R029。 | 僅接受 R022 bounded scope，不宣告 Wave 8 full closeout。 |
| 9 | R018 與 R024 各自為 `ACCEPTED_SCOPE`，見 [R018](R018_IMPLEMENTATION_REPORT.md) 與 [R024](R024_IMPLEMENTATION_REPORT.md)。 | R028 因 R027 非 `PASS` 保持 `BLOCKED`；`TMP-ML-02`、`AB-ML-01` 狀態不變。 | 接受已完成的 bounded tasks；R028 條件分支未解鎖，不宣告 Wave 9 full closeout。 |
| 10 | R019 為 `BOUNDED_COMPLETE`；evaluator core `ACCEPTED_SCOPE`，`TMP-REC-01` narrow rule bridge 已關閉，見 [R019 implementation report](R019_IMPLEMENTATION_REPORT.md)。 | `TMP-REC-02`、`TMP-NUM-01`、`TMP-ML-01` 保持 `ACTIVE`。 | R019 bounded task completion 滿足 R020 evaluator-core dependency；不是 Wave 10 full closeout，也不是 C2。 |

R015、R018、R019、R021、R022、R024、R025 的上述狀態均依其既有報告記錄；R023 的恢復 gate 依 R024 report 所載 regression route 與 root acceptance。此文件不改寫各報告的歷史狀態或驗證數字。

## R027／R028 的獨立條件分支

R027 隔離實驗報告（開發收據見dev） 的嚴格裁定是 `INCONCLUSIVE`。最新 full receipt 記錄 8/8 scenarios、16/16 worker return code 0、Direct frozen paths 15/15、semantic differences 為 0、negative controls 4/4；仍有 848 個 exact timing／snapshot 差異，且兩路沒有共同固定 publication clock，candidate 亦不是獨立 orchestration。因此不能把 timestamp 容差化或把 semantic equality 當成 R027 `PASS`。

依 R027 task gate 與 AB-ML-01／TMP-ML-02 記錄（開發收據見dev），`AB-ML-01=OPEN`、`TMP-ML-02=ACTIVE`、`R028=BLOCKED`。這不滿足 R028 的條件，但不構成 R020 的 dependency：R020 task 明列依賴 R017 與 R019 evaluator core；Wave 11 owner boundary 要求 R020 不改 execute／ML adapter。故此 checkpoint 僅裁定 R020 bounded implementation 可開始；R028 仍 BLOCKED，R026 狀態仍依執行順序及其自身 gate 判定。本決定不代表整個 Wave 11 已 release。

## R020 bounded implementation 尚待 gates

[R020 implementation progress report](R020_IMPLEMENTATION_REPORT.md) 記錄整體狀態仍為 `IN_PROGRESS`。已存在的 synthetic slices／lineage evidence 不取代下列剩餘驗收：

- 讓 19-row minimum-history rejection 與 blank `stock_code` active-filter fallback 經由單一 typed evaluator decision，保持 legacy read／filter 次序及 identity 契約；`TMP-REC-04` 在退出條件全滿足前保持 `ACTIVE`。
- 完成 R005／V-REPLAY 同 mode parity，涵蓋 replay policy、排序／切片、empty、cutoff／row-level PIT、custom provider 及仍使用的 v1 list／portfolio／factor-manifest consumers；不能以已有局部 suite 宣稱 full V-REPLAY 通過。
- 完成 portfolio DTO／舊 history consumer 的必要 readback 與跨 child artifact／Registry sidecar 儲存窗口的 failure/recovery gate；不得把 lineage sidecar readback 說成完整 legacy portfolio-result readback。
- `TMP-NUM-01` 仍 `ACTIVE`。目前有界 NumPy profile 的 numeric projector evidence 不等於所有 dtype／環境與 caller 的獨立 numeric retirement gate。
- C2 是 R020 之後的 validation-matrix gate，本 checkpoint 沒有執行或授予 C2。

## 明確 yes／no 決定

| 問題 | 決定 |
|---|---|
| 是否可開始 Wave 11 的 R020 bounded implementation？ | **是。** 只依已滿足的 R017、R019 evaluator-core dependencies 及 root 裁決；R020 仍 `IN_PROGRESS`，須完成自身 gates。 |
| 是否宣告 Wave 7–10 全部 full closeout？ | **否。** 本 checkpoint 只 reconcile 個別 bounded task acceptance／阻擋項。 |
| 是否宣告 C2 已通過？ | **否。** C2 待 R020 後依 validation matrix 驗收。 |
| 是否解鎖 R028 或裁定 R027 pass？ | **否。** R027 `INCONCLUSIVE`、`AB-ML-01` `OPEN`、`TMP-ML-02` `ACTIVE`、R028 `BLOCKED`。 |

此為工程實作範圍 checkpoint；不授權 formal data、正式 ML／模型 promotion、training、production scheduler 或 production deployment。舊的 dated update entries 與歷史報告保留原文；本文件及現況摘要只提供 2026-09-24 reconciliation。
