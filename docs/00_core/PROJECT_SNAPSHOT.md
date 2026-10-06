# PROJECT_SNAPSHOT（必讀｜目前狀態）

> 整理日期：2026-10-06。程式基線：dev `07da90c164d762966302008c0be8efbb0d9b4cfe`；main `a8c81bf534952cdf35d35a57d9e367c0fa10c817`。本輪只有文檔整理，不新增產品完成資格。

## 目前可用範圍

主要 UI 為 PySide6 `ui_qt/main.py`。首頁四用途、原保存研究／收藏／圖表與精確返回、有界結果讀取及私人覆盤等已有有限工程驗證；完整操作與限制以 [Manual](../07_guides/APPLICATION_MANUAL.md) 為準。使用者已接受 U1 有限 BBANDS30 上軌比較與 U2 H20 gross；舊「等待答覆」段落是歷史，不能當目前阻擋。

H20 已實際啟用；原保存 10 股完整 cohort 的 gross 整數排序與 exact 返回已驗。canonical 機率 head、原 ranking 與 gross 報酬 head 分開判讀；機率 head Brier 2730 對 null 2500 仍未勝基準，不能由 gross consumer 驗證推導模型品質。自然證據為 10 pending／0 成熟。

下一原 Task 為 **2026-10-07 12:45 UTC／05:45 PDT**，仍待真正自動 run 與收據驗收，沒有手動 trigger。正式 BB 全母體 v3 日常 run、Native 真人易用性未驗；不能宣稱整體 done。decision、source、feature 日期各自綁定，不以最新來源替代保存版本。

9 Stage 維持 1 done／8 partial；24 UX 維持 2 done／22 partial。七項有限 closed UX03／04／05／06／09／15／17 保留。F1 18.6219658% 對 20% 目標、Journey 8.109s 對 8s 目標的已接受性能例外保留，不改寫 benchmark pass。未知 model／PIT／source／account／clock 資格仍 unknown。

## 驗收與歷史

- [中央 cohort／natural／BBUI 整合](../06_qa/BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md)：原 affected 首紅與精確重驗分列，不是單次全綠。
- [Final authorized union](../06_qa/BALDR_FINAL_AUTHORIZED_UNION_20261006.md)：512 passed／7 failed／2 skipped 的原 raw 保留；只重驗原七項 7 passed，不消除歷史失敗。
- [工程與決策差異](../06_qa/BALDR_ENGINEERING_DECISION_DELTA_20261006.md)：有限工程、自然資格與真人驗收分域。
- [完整快照歷史](../09_archive/PROJECT_SNAPSHOT_HISTORY_20261006.md)：原累積紀錄完整封存；早期 pending、舊 branch/worktree 與後來修正皆可回溯。

## 工作區與資料保護

僅 dev／main 兩本機分支，一個主要 worktree；本輪只 commit dev，不 push／main merge。42 個舊 checkout 的 refs／extras 已有恢復備份，見 [兩分支恢復 QA](../06_qa/BALDR_TWO_BRANCH_RECOVERY_20261007.md)。main 是受控使用版，不等同 dev 全部開發收據已公開。

市場根由 `TWStockConfig`／`DATA_ROOT` 決定；私人資料、模型／source lineage、原失敗 raw 與 immutable receipts 保留。cleanup terminal 只移除 4 個空 root 共 8 目錄、0 bytes；14 DB、三工具 root、2070 Temp root 與其餘 354 repo 暫存 root 全保留，沒有釋放候選 50.6 GiB。用途、容量時點與恢復規則見 [資料資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md)。

## 下一步與導航

優先觀察下一次自然 Task 真實結果、Native 真人接受與尚存來源／模型品質資格；不以文件整理或 graphify 成功折抵 Gate。方向見 [Roadmap Hub](DEVELOPMENT_ROADMAP.md)，邊界見 [目前架構](../01_architecture/system_architecture.md)／[FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)，完整文件清單與維護流程見 [文檔索引](DOCUMENTATION_INDEX.md)。

使用者後續要求可直接雙擊的 `baldr.exe`，不需 IDE，並重新評估 main／dev；由後續 owner 在 docs＋功能 audit 完成後實作，本輪未製作或宣稱可用。main 應保留乾淨且可完整調度的系統與必要安裝／設定／scheduler／模型載入文檔；開發歷史分層保存，main 同步仍待後續 owner，本輪不改 main。
