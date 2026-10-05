# F2／F3 原市場頁共享來源與已開能力矩陣驗證

基線 `5868a2003535164139d2c1f52acc2a3b9d5af5c2`，2026-10-05。F2／F3 僅沿父層已接受 A／A，完成有限研究 consumer 與已開能力目錄；F1／F4 本批不執行。

## 交付與來源邊界

MainWindow 將原三頁接至同一 DailyMarketResearchView 接受／清除事件；共享 controller 每頁最多一個 TaskWorker、一筆 latest pending，cache 僅記錄四模式與 cohort 核驗結果，返回仍 strict 重讀 pin。請求／結果核對 cohort、date、manifest hash／identity、method hash、period／direction；過期 generation 不改畫面。原排名 publisher 結果不重算，保留全 eligible rows、原引擎標籤與每股比較窗。研究母體 excluded 與 native missing_rank_stock_codes 分列，缺乏原排除理由明示未知。

原全市場／產業統計持續沿自身來源與母體，不能宣稱與研究三股同源或可直接比較。共享非版本化觀察清單操作停用，既有同來源研究收藏流程沿用；沒有加入 F4 新收藏框架。

`project_daily_market_research_capabilities(snapshot, rows=None, expected_snapshot_root=...)` 回傳 frozen report，`.to_dict()` 是 detached JSON。Catalog 精確三 feature／兩 method，全項具八類 metadata；逐股保存資料值、三態、理由、source reference／fingerprint、暖機前綴及 method/version。partial 仍保留 declared 分母與 missing unknown。純投影不連 DB／網路，官方 availability、calendar 完整度及未量測成本 unknown；不授全市場或歷史 PIT。

「研究母體盤勢」→「查看已開能力與來源」→「已開能力矩陣／逐股與完整來源明細」。來源清除立即禁用入口、清掉 matrix 與 JSON，母體完整標示同步失效。

## 驗證

43 個不重複受影響案例有通過證據（根層首9＋相容29＋實際橋接新增1＋F2 focused4；最後11頁面相容重驗為既有案例不加總）、Workbench85、validator25／4skip／0fail、mypy790、12檔編譯及精度／未來函數 guard 通過。局部 agent 測試與根層相容測試有重疊，不重複加總。各命令／exit code、初輪失敗與最終收據保存在 `output/qa/f2_f3_consumer_capabilities_20261005/`；raw output ignored。

受控 fixture 是小型隔離資料庫／publisher setup，只作工程四模式、來源拒絕、切返不 producer、取消／過期 callback／shutdown 驗證，不是自然成熟或正式市場證據。真實保存來源 `ux16-three-stock-research`：1477／2330／2382，設定排除2317、設定分母4、declared3。manifest `2d241068d3b6df9a06c65267da0c0925c30d3244c6116da626d6a537f742311c`，identity `6c4a3fd3c82f074f5085a9ac6dff0437c7ba287c80ea8e696bc16118d3f2d9e6`。cutoff 2026-10-05T23:59:59+08:00，翌日發布；未記官方時點，不作歷史PIT或跨日自然歷程。

`real_capability_receipt.json` 的 audit hook 拒絕所有 SQLite connection；17 原來源 hash 與正式 DB size／mtime 前後相同，worker 0。`real_capability_cohort.png`／`real_capability_audit.png` 是既有真實保存來源 offscreen，可讀性已看圖核對，不替代 Native。原 StockScreener SHA `48c58d292c5cd5182a5e9ecbb98205790742a61207c88bad34e81f2f41ef6ed2` 保留。

根層發現能力報告 assignment 誤置於 ranking callback，在測試前修回 snapshot 接受點；新增實際三 consumer 橋接測試首輪誤用 snapshot.declared_stock_codes（實際在 manifest 內），1 failure 保留、修正 fixture assertion 後精準重驗通過。修訂來源測試首輪誤用決策日而 UPDATE 0 列，改行情日並 assert rowcount=1 後三頁返回 strict 拒絕舊 pin；不是實作漏核驗。mypy 首輪暖機 dict 推導型別未含整數，補明確 metadata annotation 後790全域通過，不改任何 runtime 值。首次 quant scan_paths 因既有 main.py UTF8 BOM 被 AST 拒絕，保留錯誤收據並以 utf-8-sig → 同一 scan_source 規則驗證，不修改既有 BOM 或放寬 guard。F2 首輪4個 fixture 拒讀僅保存摘要；最終4案例通過。pytest cache 權限 warning 不影響結果。

唯一原 plan 保留 169633-byte 前綴 SHA `7397825f8b7fe6bef33656cba84737850643eaf2478fbbf9c8a9f00c5ed66ef0`，只追加本批結果。正式 commit／blob／status 以 `commit_readback.json` 與 Git 為準，不提交 output、plan 或他人檔。

## 剩餘與回滾

根層 `controlled_offscreen/receipt.json` 額外驗實際強／弱頁 day→week→day 六次讀取及切返，涵蓋四個排名身份；fixture 發布完成後禁止 snapshot producer／rank publisher，完整兩個 eligible 加1101原引擎排除列（研究資料已發布）均保存，來源 inventory 未改、worker0。`day_strong.png`、`week_weak.png`、`regime.png` 已實際看圖核對；五張圖保存在同目錄。agent 最初未註冊中文字型的三張圖有方框，僅保留初始布局收據；根層使用既有 font helper 重拍，產品字型未改。全為受控工程證據，不是自然來源。

F2／F3 的 A 範圍已關閉。F1 的 18.62%／20% 門檻維持，F4 跨頁整合／部署／長期總容量交下一包；新 Native／真人與自然證據獨立。正式 B 全市場母體或新方法只有另擴充時決定，不能把未選擴充寫成目前缺陷。容量與 Evidence 另 owner，根 Paper 由 edcfe021 處理，tracked；本批不讀／改其內容。

回滾限本批 commit 的明確檔案，用反向 patch／新本地 commit 撤回三頁接線、共享 helper、能力 module／audit、產業來源標示與相關 tests/docs；不刪 immutable 快照／排名／原資料，不回滾其他 owner，禁止 broad reset／clean。執行前重新核對 status／owner；本批未執行回滾或刪除，未 push。
