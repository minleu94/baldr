# PROJECT_SNAPSHOT（必讀｜目前狀態）

> 更新基線：2026-10-09 本機 dev WIP checkpoint；2026-10-10 僅補入截至已提交 QA commit `577210b1` 的 F03 bounded evidence。另有未提交 F03 工作樹變更未納入此頁，也不視為驗收；該工作完成後需再同步。詳細測試過程及各項驗收界線以交接文件、恢復 QA 與具名 root review 為準。

## 目前狀態

2026-10-09 17:49 PDT排程修正：Windows21個Task已在host唯讀環境核對，trigger／action／working directory均符合現行契約；Direct仍running，不授全鏈成功。Operational日誌已啟用，修正稽核器舊05:30期待與四個背景action誤判；兩個既有Codex監測prompt已更新並保留cadence／thread／通知。較晚結果確認G6研究cycle完成但正式revision hold保留、Forward1538歷史缺價及G9來源依賴失敗；183推薦degraded是153流動性排除＋30無訊號，真正missing為1516。精確結果、未解事項與界線見[10/09排程修正QA](../06_qa/BALDR_SCHEDULE_REMEDIATION_20261009.md)。

| 項目 | 判讀 |
|---|---|
| 產品補完範圍 | 仍為 P00–P14、M1–M3、F01–F23；checkpoint 是 WIP，不代表產品完成。Gate 狀態以本頁與具名 QA 判讀。 |
| P01 千檔效能 | 固定矩陣仍未通過原 300 ms 門檻：換頁 p95 239.4695 ms；篩選 1074.3634 ms、排序 344.7445 ms，後兩項失敗。render-prefill bounded 修補的 19 項定向回歸通過，但尚未重跑完整矩陣，不能視為效能門檻通過；見 [P01 root review](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。 |
| F02 四均線 | 固定合成來源的 V11 父 Main→收藏→關閉→新程序 Watchlist 單擊／雙擊旅程有界通過；不代表原始來源、新 EXE 或真人驗收。 |
| F03 多父群組 | bounded prepare attempt02 為 13 passed／exit 0。複合研究收藏契約六測試通過，四群 bundle 入口通過兩項完整母體／取消測試。2026-10-10 又完成 formal reader／group-session bounded publication slice：首輪 15 passed、2 個測試因 QA overlay 環境設定失敗；修正後只重跑兩個失敗節點並通過，故不是修正後全套重跑。不同籃狀態的收藏身份、full-population query、正常 View、收藏／新程序與 Main 閉環仍未完成；不得以此 slice 宣告產品完成。[follow-up QA](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md) |
| F06 波動 | 尚無 full-N reader-issued 結果；方法提案不代表已採納產品規則。詳見[產品／UX QA 索引](../06_qa/PRODUCT_UX_QA_INDEX.md)。 |
| F12 月營收 | Q Main 的來源資格與 65 欄 query oracle 均通過。S 六項定向測試及真 Main 首頁比較籃通過，下一頁缺少 `_page_index` 導致旅程失敗。正式最小修補已通過四項按鈕回歸及強制 UI 檢查；新來源版本的完整收藏／新程序旅程仍待驗。[F12 follow-up](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md) |
| H20 source-port | I Main 已真正讀回原 H20：10 檔可用／0 未知、2382 原估計 684 bp 與三日期吻合，名單載入階段 16.547s。實際雙擊已觸發選股投影；舊 QA 誤等重新建立名單，圖表與返回旅程仍待對齊並驗收。G／H timeout 不代表產品 worker 未完成。[H20 follow-up](../06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md) |

P01 詳細結果見 [P01 效能 root review](../06_qa/BALDR_P01_PATH_RENDER_DESIGN_ROOT_REVIEW_20261009.md)；F02 旅程見 [F02 root review](../06_qa/BALDR_MA_V9_CHILD_IDENTITY_ROOT_REVIEW_20261009.md)。產品缺口總表見 [補完缺口 review](../06_qa/BALDR_COMPLETION_GAP_REVIEW_20261008.md)，續接時依 [恢復開發 QA](../06_qa/BALDR_COMPLETION_RESUME_20261009.md)、[交接文件](../06_qa/BALDR_COMPLETION_HANDOFF_20261009.md) 及 [產品／UX QA 索引](../06_qa/PRODUCT_UX_QA_INDEX.md)查閱。交接及各 root review 中的通過、失敗、未驗證界線均有效；文件整理不關閉 Gate。

## 歷史快照與驗收入口

本頁不再複製逐輪施工日誌或舊測試數字。精簡前完整內容保存在 [2026-10-09 歷史快照](../09_archive/PROJECT_SNAPSHOT_HISTORY_20261009.md)；其中每筆日期狀態只代表當時觀測，不作現況依據。各日期的原始 QA 與不可變收據留在原處，按上方具名 QA 入口查閱。較早的快照與排程驗收入口見 [2026-10-06 歷史快照](../09_archive/PROJECT_SNAPSHOT_HISTORY_20261006.md)、[產品補完首波 QA](../06_qa/BALDR_COMPLETION_FIRST_WAVE_20261006.md)、[M2 工程 QA](../06_qa/BALDR_COMPLETION_M2_20261007.md)及[排程修正 QA](../06_qa/BALDR_SCHEDULE_REPAIR_20261008.md)。

## 工作區與資料保護

2026-10-09 本機 dev checkpoint 為 a48a86afd4de0fd9a5f85e2dd09cf370ad42281b；checkpoint 建立時位於 dev、工作樹乾淨且未 push。這是 WIP 交接，不代表產品完成；驗收界線與續接事項見 [交接文件](../06_qa/BALDR_COMPLETION_HANDOFF_20261009.md)。42 個舊 checkout 的 refs／extras 恢復備份是 2026-10-07 收據，見 [兩分支恢復 QA](../06_qa/BALDR_TWO_BRANCH_RECOVERY_20261007.md)。main 是受控使用版，不等同 dev 全部開發收據已公開。

市場根由 TWStockConfig／DATA_ROOT 決定；私人資料、模型／source lineage、原失敗 raw 與 immutable receipts 保留。2026-10-06 repo-temp cleanup terminal 只移除 4 個空 root 共 8 目錄、0 bytes；當日清冊中的 14 DB、三工具 root、2070 Temp root、其餘 354 repo 暫存 root 與未釋放候選 50.6 GiB 是該次盤點／處置範圍，不是 10/09 冷封存後的即時清冊。用途、容量時點與恢復規則見 [資料資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md)。

2026-10-09 冷封存終態：第一批 6/6、第二批 28/28，共 34 個根、158,712 個檔案、198,246,544,124 logical bytes（約 184.62 GiB）；終態收據記為完成，34 個 C 槽原路徑均為目標相符的 Junction。兩批執行收據記錄全檔 SHA-256 核驗通過；[終態對照](../06_qa/C_DRIVE_QA_COLD_ARCHIVE_RECONCILIATION_20261009.md)只核對收據及 Junction metadata，沒有重新計算全量 SHA。容量變化與 postflight 數值均是當時快照，不代表目前可用空間；正式 D 槽資料及既有 E 槽舊封存未改。

## 下一步與導航

產品補完已在 2026-10-09 本機 WIP checkpoint 後恢復開發。方向見 [Roadmap Hub](DEVELOPMENT_ROADMAP.md)，工程 Gate 順序見 [6M 工程 Roadmap](ROADMAP_6M_ENGINEERING.md)，邊界見 [目前架構](../01_architecture/system_architecture.md)／[FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)，文件導覽與維護流程見 [文檔索引](DOCUMENTATION_INDEX.md)；全量路徑快照是[日期化目錄清冊](DOCUMENTATION_CATALOG_20261006.md)，本輪可追溯的分類與覆核基線見[文件整理狀態矩陣](DOCUMENTATION_STATUS_MATRIX_20261009.md)。Snapshot 只負責目前狀態，不取代 Roadmap、架構契約或 QA 原始證據。
