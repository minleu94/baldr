# PROJECT_SNAPSHOT（必讀｜目前狀態）

> 更新基線：2026-10-09 本機 dev WIP checkpoint 後續接文檔。此頁提供現況摘要與證據入口；詳細測試過程及各項驗收界線以交接文件、恢復 QA 與具名 root review 為準。

## 目前狀態

| 項目 | 判讀 |
|---|---|
| 產品補完範圍 | 仍為 P00–P14、M1–M3、F01–F23；checkpoint 是 WIP，不代表產品完成。Gate 狀態以本頁與具名 QA 判讀。 |
| P01 千檔效能 | 固定矩陣仍未通過原 300 ms 門檻：換頁 p95 239.4695 ms；篩選 1074.3634 ms、排序 344.7445 ms，後兩項失敗。render-prefill bounded 修補的 19 項定向回歸通過，但尚未重跑完整矩陣，不能視為效能門檻通過；見 [P01 root review](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。 |
| F02 四均線 | 固定合成來源的 V11 父 Main→收藏→關閉→新程序 Watchlist 單擊／雙擊旅程有界通過；不代表原始來源、新 EXE 或真人驗收。 |
| F03 多父群組 | bounded prepare attempt02 為 13 passed／exit 0；只證明限定 preparation 範圍，仍未取得共同 reader 資格、完整 query 與 UI 閉環。[follow-up QA](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md) |
| F06 波動 | 尚無 full-N reader-issued 結果；方法提案不代表已採納產品規則。詳見[產品／UX QA 索引](../06_qa/PRODUCT_UX_QA_INDEX.md)。 |
| F12 月營收 | D focused tests 為 17 passed／4 subtests passed；唯一 Main attempt exit 1，後續 E 修正尚未驗證。[F12 D/Main follow-up](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md) |
| H20 source-port | O attempt02 exit 1，失敗於設定讀取前置 guard；initial／terminal 檔案與 SQLite 真讀均未發生，source-port 未通過。[H20 O attempt02 follow-up](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md) |

P01 詳細結果見 [P01 效能 root review](../06_qa/BALDR_P01_PATH_RENDER_DESIGN_ROOT_REVIEW_20261009.md)；F02 旅程見 [F02 root review](../06_qa/BALDR_MA_V9_CHILD_IDENTITY_ROOT_REVIEW_20261009.md)。產品缺口總表見 [補完缺口 review](../06_qa/BALDR_COMPLETION_GAP_REVIEW_20261008.md)，續接時依 [恢復開發 QA](../06_qa/BALDR_COMPLETION_RESUME_20261009.md)、[交接文件](../06_qa/BALDR_COMPLETION_HANDOFF_20261009.md) 及 [產品／UX QA 索引](../06_qa/PRODUCT_UX_QA_INDEX.md)查閱。交接及各 root review 中的通過、失敗、未驗證界線均有效；文件整理不關閉 Gate。

## 歷史快照與驗收入口

本頁不再複製逐輪施工日誌或舊測試數字。精簡前完整內容保存在 [2026-10-09 歷史快照](../09_archive/PROJECT_SNAPSHOT_HISTORY_20261009.md)；其中每筆日期狀態只代表當時觀測，不作現況依據。各日期的原始 QA 與不可變收據留在原處，按上方具名 QA 入口查閱。較早的快照與排程驗收入口見 [2026-10-06 歷史快照](../09_archive/PROJECT_SNAPSHOT_HISTORY_20261006.md)、[產品補完首波 QA](../06_qa/BALDR_COMPLETION_FIRST_WAVE_20261006.md)、[M2 工程 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md)及[排程修正 QA](../06_qa/BALDR_SCHEDULE_REPAIR_20261008.md)。

## 工作區與資料保護

2026-10-09 本機 dev checkpoint 為 a48a86afd4de0fd9a5f85e2dd09cf370ad42281b；checkpoint 建立時位於 dev、工作樹乾淨且未 push。這是 WIP 交接，不代表產品完成；驗收界線與續接事項見 [交接文件](../06_qa/BALDR_COMPLETION_HANDOFF_20261009.md)。42 個舊 checkout 的 refs／extras 恢復備份是 2026-10-07 收據，見 [兩分支恢復 QA](../06_qa/BALDR_TWO_BRANCH_RECOVERY_20261007.md)。main 是受控使用版，不等同 dev 全部開發收據已公開。

市場根由 TWStockConfig／DATA_ROOT 決定；私人資料、模型／source lineage、原失敗 raw 與 immutable receipts 保留。2026-10-06 repo-temp cleanup terminal 只移除 4 個空 root 共 8 目錄、0 bytes；當日清冊中的 14 DB、三工具 root、2070 Temp root、其餘 354 repo 暫存 root 與未釋放候選 50.6 GiB 是該次盤點／處置範圍，不是 10/09 冷封存後的即時清冊。用途、容量時點與恢復規則見 [資料資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md)。

2026-10-09 冷封存終態：第一批 6/6、第二批 28/28，共 34 個根、158,712 個檔案、198,246,544,124 logical bytes（約 184.62 GiB）；終態收據記為完成，34 個 C 槽原路徑均為目標相符的 Junction。兩批執行收據記錄全檔 SHA-256 核驗通過；[終態對照](../06_qa/C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md)只核對收據及 Junction metadata，沒有重新計算全量 SHA。容量變化與 postflight 數值均是當時快照，不代表目前可用空間；正式 D 槽資料及既有 E 槽舊封存未改。

## 下一步與導航

產品補完已在 2026-10-09 本機 WIP checkpoint 後恢復開發。方向見 [Roadmap Hub](DEVELOPMENT_ROADMAP.md)，工程 Gate 順序見 [6M 工程 Roadmap](ROADMAP_6M_ENGINEERING.md)，邊界見 [目前架構](../01_architecture/system_architecture.md)／[FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)，完整文件清單與維護流程見 [文檔索引](DOCUMENTATION_INDEX.md)。Snapshot 只負責目前狀態，不取代 Roadmap、架構契約或 QA 原始證據。
