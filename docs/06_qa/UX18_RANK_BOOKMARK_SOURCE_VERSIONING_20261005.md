# 原排名收藏與個股來源版本化

基線 `25b039afc67f1190de5f7031a53a64a139d97570`；沿唯一原計畫補排名選股→個股→收藏→新程序原來源返回。僅 backend 及 offscreen，禁止 Native；原排名 publisher／公式不重跑或更改，真實收藏不遷移。

## 身份與讀回契約

typed rank_context 及 v2 rank bookmark 保存原 publisher 身份／hash／根目錄、parent feature、day/week 與 strong/weak、native rank 和完整 Top/Bottom 標籤、比較起訖及原 rule、母體／方法／引擎參數及 sourcehash、filter/sort 與所選股票。同身份重複不新增；模式／來源不同可另存，不降為代碼排序。

`read_pinned` 直接讀 content-addressed manifest/artifact，不借 latest pointer。仍驗原輸入、schema、母體、engine/method 及 DB/WAL pin；錯日期／股號／hash／舊版／缺 record 拒絕，排名顯示 unknown 與原因。可明確另開最新研究，不覆蓋原證據；其他可讀行情不代表原排名有效。

個股頁提供明確收藏入口，從 pinned context 重建原查詢後確認／取消。觀察清單沿既有 JSON／SQLite research_bookmark extension，無第二 ledger。新程序重建原 context/rank，返回精確 source_id；名單後來切 mode 不改原收藏。

舊非 rank v1 class/schema/source 與原語意保留，新 DTO 欄位不改舊 context body/hash。新 rank 明確另存 v2，不自動遷移用戶資料。修改前已用舊 factory 捕獲隔離 v1 payload，最終 roundtrip 須核對 bookmark/query/payload 雜湊。

## 呈現與接受邊界

原 Top/Bottom 百分比原樣保存，不反推不存在數值 score，也非一般前幾％或勝率。週 ≥6 筆比較倒數第6筆；3–5筆原 fallback 比較倒數第3筆，列實際比較日期及「非完整週」，不改算法或授官方 availability／PIT 資格。

本包完成範圍及結果見最終收據。第一版其餘工程為其他原大盤／強弱 consumer、完整 feature/method dictionary、正式母體／排程、長期 storage/growth 及其他 lifecycle crash 驗收。Backtest 18.62%／20% 門檻未達仍保留。

來源決策另列：正式母體權威、official availability／歷史 membership／PIT；舊標籤口徑及數值 score 暴露須方法版本決策。Native鍵鼠／縮放／跨頁、完整App startup及3–5真人驗收待桌面時段。沒有正式DB／registry寫入、producer／learner重跑、大DBcopy、永久清理或push；未知capture及還原映射不動。

- 2026-10-05：新增排名收藏／個股原來源契約與接受邊界，最終限定實證見下節；不授正式推薦或歷史 PIT 資格。

## 限定驗證結果

受影響測試 136 首輪通過＋1 項定向修正後通過（合計 137 個案例）；Workbench 85；更新頁 validator 25 通過／4 略過；mypy 783 檔；18 個 Python 檔語法與 quant guard 通過。

真實既有 D 來源的 2382 四模式，在程序 24368 保存至隔離清單，程序 26516 重開核對來源與返回；兩程序正常退出且 worker=0。17 個 feature/rank 原檔及 DB/WAL/SHM stat、原引擎／母體設定保持不變；未重跑既有真實來源 publisher／learner，未寫正式 DB／registry 或真實收藏。排名來源測試僅用三股小型 fixture DB 與隔離產物。

舊 v1 修改前 payload 的完整 roundtrip 相等，三項身份雜湊均相同。取消／重複不寫入、模式切換與舊版／來源拒絕由隔離測試涵蓋；真實四模式流程的取消／重複亦核對清單位元組不變。真實原引擎、母體、feature 與 ranking 均只讀，不執行發布。

收據、JUnit、兩程序輸出及五張 offscreen 圖在 `output/qa/rank_bookmark_20261005/`，屬本機 QA 不提交；圖不是 Native／真人驗收。首次 global mypy 的五項錯誤（兩檔）已保留 `mypy_initial_failure.log`／receipt：guard 後 Literal 收窄及 rank_context None 分支修正後，完整 mypy 通過。子任務首次新測試 f-string 語法失敗已修，工具收據 chunk `2c13e6e` 可追溯，未另存 stdout 檔；不是 production 缺陷。

其他原大盤／強弱 consumer 融合、完整 feature/method dictionary、正式合格母體／排程部署、長期 storage/growth 及其他 lifecycle crash 驗收仍是第一版工程。Backtest 18.62%／20% 未達保留。正式母體權威、official availability／歷史 membership／PIT，以及舊 Top/Bottom 口徑與 numeric score 暴露屬來源／方法版本決策。Native 鍵鼠／縮放／跨頁、完整 App startup 與 3–5 位真人驗收另待桌面時段；不把工程缺件稱為自然成熟。

首次受影響套件為 136 通過／1 失敗：新增隔離測試預期 source_refused，但原資料指紋修訂正確回傳 wrong_hash／ranking_source_input_hash_mismatch。只修正測試的具體 status 斷言後，該單一案例通過；未重跑其餘 136 項。初始 XML／log／receipt 與單項修正收據均保留。真實 offscreen 報告使用隔離 consumer config，沒有連入 Advice／WatchlistAnalysis 保存來源，畫面因此呈部分可用；原排名與 parent feature 的成功不代表完整 App provider／startup 驗收。
