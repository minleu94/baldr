# PROJECT_SNAPSHOT（必讀｜目前狀態）

> 現況更新：2026-10-06。產品補完開工checkpoint `bf9207fb72cd3acebac17f4b7816994efa601226`；main `305635642ecdf5f1331a24a0c81566d07f36cb0d`。原文檔整理基線 dev `07da90c1`／main `a8c81bf5` 屬歷史。僅dev/main、一worktree；當前增量由dev本機commit與具名收據追溯，不將施工狀態寫成完成資格。

補完首波已由使用者授權啟動Luna Max：共同設定／版本葉片 `92ed944e`（43定向案例），H20白話投影 `cefef608`（12定向案例）已提交；中央入口／UI／同版candidate與P01全母體run正在整合驗收。完整選股器、每策略績效、Native真人及正式Task自然run仍未因這些葉片取得完成資格。接續範圍與M1/M2里程碑見[單一補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)。現有exe保留原交付，沒有自動替換。

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

其後已實際交付 Windows onedir `dist/baldr/baldr.exe`，需保留整個資料夾、不需 IDE／全域 Python。外部資料／輸出／私人設定分離，不內附 FA_Data 或個人模型。首次操作、SHA、已驗與未驗項見 [可攜指南](../07_guides/PORTABLE_WINDOWS.md)。D01 合法警告成功保留 last success、warning 與 freshness/date 診斷，Runtime 維持 guarded，不把未知／失敗變成功。main 保留既有完整 scheduler／模型／資料功能與必要文件；dev 保存內部 QA、規劃及打包 probe。本輪可逆本機 commit 同步 main，沒有 push；詳細收據見 [可攜 QA](../06_qa/BALDR_PORTABLE_WINDOWS_20261006.md)。上方文檔整理時的 branch／未同步狀態保留為該輪歷史。
