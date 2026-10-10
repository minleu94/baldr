# QA 證據導覽

> 本目錄保存日期化驗收、調查與交接證據。它們描述各自的範圍與時間點；目前專案狀態請看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，產品操作請看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。主題相同不代表證據可互換，舊報告中的待辦也不自動成為目前待辦。

## 先從這裡開始

1. [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)：目前狀態、未成熟項目與阻礙。
2. [10/08 產品補完缺口再核對](BALDR_COMPLETION_GAP_REVIEW_20261008.md)：近期補完範圍與缺口入口。
3. [10/08 排程修復](BALDR_SCHEDULE_REPAIR_20261008.md)：近期排程修復的證據入口；查更早時點再讀 [9/30 排程修復](SCHEDULED_OPERATIONS_REPAIR_20260930.md)。
4. [10/09 排程與 Codex automation 修正](BALDR_SCHEDULE_REMEDIATION_20261009.md)：21 個 Task 的回讀結果、仍未解除的來源缺口與回復資訊；producer 結果與排程 exit code 分開判讀，共同只讀操作規則見 [排程稽核 Runbook](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。
5. [10/09 產品補完恢復開發基線](BALDR_COMPLETION_RESUME_20261009.md)：記錄 checkpoint 後的工作分工與首輪驗證；不是產品完成或發布收據。原暫停點見 [10/09 交接](BALDR_COMPLETION_HANDOFF_20261009.md)。
6. 按下方主題地圖選擇索引；需要操作步驟時回到 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。

<a id="主題地圖"></a>
## 主題地圖

| 主題 | 入口 | 範圍 |
|---|---|---|
| 產品、個股研究與 UX | [產品與個股研究索引](PRODUCT_UX_QA_INDEX.md) | H20、BALDR B01–B14、功能驗收鏈、Watchlist、投資組合與圖表。 |
| 資料、ML 與來源治理 | [資料與 ML 索引](DATA_ML_GOVERNANCE_QA_INDEX.md) | R026／R031、ML Shadow、前瞻證據、PIT、基本面與來源接受。 |
| 跨工作流整合 | [整合索引](INTEGRATION_QA_INDEX.md) | WP1–WP5、Task Loop、Continuity／Decision Journey、LUNA 與跨工作流收據。 |
| 營運與測試 | [營運與測試索引](OPERATIONS_TESTING_QA_INDEX.md) | 排程、資料更新效能、測試路由、固定路徑與維運證據。 |
| 儲存與冷封存 | [C 槽冷封存狀態對照（2026-10-09）](C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md) | 第一批 6/6、第二批 28/28 已按終態收據完成；摘要未重新計算全量 SHA，容量數字是時間點快照。 |

## 相容深連結

<a id="wp1wp5-package-evidence-index"></a>
### WP1–WP5 工作包收據索引

工作包收據已移至[整合索引](INTEGRATION_QA_INDEX.md#wp1wp5-package-evidence-index)。保留此錨點供既有連結使用；原收據仍保留各自範圍，不代表全部工作包已通過。

<a id="baldr-b01b14"></a>
### BALDR B01–B14

功能收據已移至[產品與個股研究索引](PRODUCT_UX_QA_INDEX.md#baldr-b01b14)。保留此錨點供既有連結使用；依產品補完缺口表判讀各自範圍。

## 閱讀與歸檔規則

- QA 原文保存當時輸入、失敗、結果、回滾與接受邊界；入口摘要只供導覽，不改寫證據結論。
- **生命週期**：日期或「完成」標籤不代表可搬移。仍有未解 Gate／重驗、活躍文件引用、測試／腳本依賴或固定輸出路徑的收據留在本目錄；只有結案、替代入口明確且依賴解除後才歸檔，保留舊路徑導引與原件 bytes／hash。詳見 [DOCUMENTATION_STRUCTURE](../00_core/DOCUMENTATION_STRUCTURE.md#qa-evidence-retention)。
- 超長報告先讀標題、開頭的範圍／結論及本頁入口，再依問題查原始章節；不要把整份 terminal dump 當成目前狀態。
- **2026-08-14 BALDR 本機狀態報告**：JSON 與 HTML 原件已逐位元組封存至 [歷史報告套件](../09_archive/project_status_2026_08_14/README.md)；[舊 QA 路徑相容導引](project_status_2026_08_14/README.md)保留原路徑入口。這是當日 CPU／MCP／Git／QA 快照，不代表目前狀態；現況看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，來源 bytes／SHA 與依賴檢查見 [Coverage History Entry 117](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-117)。
- 其他 JSON 收據與機器／報告伴隨物，仍須與對應說明文件一起判讀；不要只憑檔名把它們當作獨立產品文件。
- 歷史 archive 的定位與規則見 [docs/09_archive README](../09_archive/README.md)；完整文件分類見 [DOCUMENTATION_INDEX](../00_core/DOCUMENTATION_INDEX.md)。
- 已歸檔 QA： [文件編碼稽核（2026-06-16）](../09_archive/DOCUMENT_ENCODING_AUDIT_2026_06_16.md)、[文件與 Roadmap 重整稽核（2026-07-03）](../09_archive/DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md)、[Pre-push 文件治理稽核（2026-07-06）](../09_archive/DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06_HISTORY.md)、[Pre-V2 非排程 readiness closeout（2026-07-06）](../09_archive/PRE_V2_NON_SCHEDULE_READINESS_CLOSEOUT_2026_07_06_HISTORY.md)、[ML Shadow 推論操作 closeout（2026-07-15）](../09_archive/ML_SHADOW_INFERENCE_OPERATIONS_CLOSEOUT_2026_07_15_HISTORY.md)、[SQLite inspector 關閉探測（2026-09-15）](../09_archive/QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md)。
