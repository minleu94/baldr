# 文件理解負擔修復與驗證（2026-10-15）

本輪依使用者授權整理文件與維護工具，未改產品行為、正式資料、排程、固定試用包或接受資格。Root 整合，三位 Luna Max 協作者分別處理同步責任、操作入口及功能／架構導航；獨立複核另留具名紀錄。本頁是日期化處置與驗收，不取代 [Snapshot](../00_core/PROJECT_SNAPSHOT.md)、領域契約或原始 QA。

## 處置與使用入口

| 問題 | 結果與入口 |
|---|---|
| 冷封存被重報為未追蹤 | [資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md#查詢已登記的冷封存)連 [34 筆機器清冊](../03_data/COLD_ARCHIVE_REFERENCE_REGISTRY.json)；`document_control archives` 查原路徑、外部落點及可用性。登記、內容核驗、Git 來源與產品接受分開。 |
| 功能同步規則漏配 | [Feature Map](../00_core/FEATURE_DOCUMENT_MAP.json)補齊原先 124 個路徑／149 個功能關聯的精確 pattern；每個功能自己的 code／tests 入口都須命中自己的規則，並加回歸檢查。 |
| 歷史章節連結失配 | [歷史 owner packet](../09_archive/P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md)修正 §14 錨點，未改歷史驗收結論。 |
| 目前版本與歷史包混雜 | [指定的本機研究入口](../07_guides/TRIAL_VERSION_GUIDE.md)集中入口與限制；依新增的71交付原文同步 Snapshot，分開71固定候選、66原包及72來源修正，保留各自接受界線。 |
| 日常操作前堆積版本說明 | [主手冊](../07_guides/APPLICATION_MANUAL.md)第一節由第 33 行提前至第 9 行；日期化補充折疊保留，舊 anchors 未丟失，主題操作沿 manuals 分冊。 |
| 功能與架構依日期累加 | [UI 功能文件](../02_features/UI_FEATURES_DOCUMENTATION.md)、[現行研究／配置責任](../01_architecture/current/decision_research_portfolio.md)依主題找現行責任；原日期章節保留作歷史證據入口。 |
| 圖譜未反映新入口 | [圖譜指南](../00_core/DOCUMENTATION_GRAPH_GUIDE.md#本輪文件整理的圖譜入口)指定隔離 run；只有該輪 verifier 的 `passed=true` 才成立。 |

## 核驗範圍與限制

原盤點與本輪 byte pins、候選、搬移對應及收據位於 ignored `output/tasks/doc-system-audit-20261015-01a1432c/` 與 `output/tasks/doc-clarity-repair-20261015-01a1432c/`。本輪整合基線為 `f9b4e7d1214967f86d9ae90b1e462bde11b73f3f`，原文也可沿 Git 追溯。保留第一次受 sandbox 限制的 Junction 測試失敗及其後受控重驗，不抹除失敗紀錄。

冷封存只核 34 個已登記根的 Junction 目標與存在性 metadata；沒有重讀或重算 raw evidence SHA。`content_verified=false` 是明示限制；缺少外接磁碟或原 Junction 時仍顯示已登記但不可用。未登記越界、目標漂移、內部跳脫及不完整／過廣來源登記仍拒絕。

測試已實跑：文件治理、Context、task state 與冷封存四份測試共 **93 passed**；四份變更 Python 的 compile 與 mypy 通過。最終來源釘選重驗為本輪 root 的 `single_owned_qa_be2202cd75ce468c98f231a15facfa6b/receipt.json` 與 `single_owned_qa_0d1cbdc3c3bd48d98d9d166e8bddac09/receipt.json`；`tests_bc857ad8_pins.json`、`types_412722a2_pins.json` 記程式、測試與 Feature Map 的驗前 SHA，驗後 drift 為空。所有 Python 驗證由 Root 序列執行，8 GiB／12 processes Windows Job、kill-on-close 與 repo mutex；沒有殘留 Job PID 或強制清理。

主手冊整合比對來源、候選及其他任務新增 FAQ，原 FAQ 全數保留；來源 SHA、結果 SHA 與 `anchors_lost=[]` 記於 root 的 `manual_integration.json`。獨立文字審閱只核文件與來源適用性，不冒稱執行真人旅程或產品 QA。

功能與架構整合記於 `feature_integration.json`：UI 舊 68 個 headings 保留，新增九工作區及跨頁責任入口；架構模組責任／上下游先於深層接線；兩份正文的舊 anchors 無遺失。另一任務的啟動警告段落與 QA index 原文保留。日期化收據沒有重寫，QA index 以功能連到 Increment34–71 的具名章節；原長 QA 仍保留其唯一輸入、失敗與範圍。

持續開發期間，owner 又追加了 Increment71 的 QA447–458 交付原文與獨立71包，但 Snapshot／本輪最初指南仍寫66及71待EXE。Root 隨後依 QA456／458 與71包內指南／已知問題同步入口；`version_update.json` 記來源與前後 SHA、anchors 保留。66原真人回報與狀態不改寫；71只描述原收據限定工程通過，真人手勢／真帳／Gate未接受；72及啟動警告來源修正未冒稱納入固定71。主手冊在本輪整合後由其他owner追加的72判讀段也保留。這是文件狀態對照，沒有重新核驗 EXE 二進位或執行產品旅程。

## Graphify 來源與驗收

來源已凍結於 `output/qa/doc_clarity_graph_20261015/graphify_input_manifest.json`：固定 HEAD 為 `90e9a4f7adcb65cab4c5842b13cb6f2586d85e1f`，1,626 份 tracked 文件加兩份明示的新指南／登記文件、1,167 份 production Python 及1,625份 test Python，共4,420個來源。程式／測試取固定 Git blobs，文件逐檔取工作樹 bytes 並記 SHA；來源指紋為 `ccc083e224189f68e52b7018bd6bfa2850038744773e8419f398f351552a20e2`。這是明示混合快照，沒有讀其他owner尚未提交的產品程式正文。

37個AST分塊各最多32檔、順序抽取。測試只作檔案節點；排除AST的維護腳本／未追蹤測試只保留 Feature Map 的 reference-only 路徑，不宣稱正文納入。圖另納入中文標題、略過 code fences 的 Markdown 明示連結，以及 Feature Map 每筆 feature／field／path 關係；同一無向節點對的多重責任保存在 relation 明細與 sidecar。未解析 AST／文件連結另存診斷，不視為不存在。社群命名是主要來源路徑的機械統計。

本輪隔離圖譜已由 `build_graph_v2.py` 建立，`verify_graph_v3.py` 驗收通過：**58,614 nodes／180,767 edges／2,880 communities**。12 個功能的 **567 筆 feature／field／path／relation** 在原 Feature Map、sidecar 與圖中 Counter 完全相同，missing／extra／path mapping／relation pair errors 皆空；8,928 對已解析的 Markdown 檔案關係全數存在，沒有 dangling endpoints。所有 4,420 個來源 SHA／大小、37 個分塊與產出指紋核對通過。本頁在圖中只作唯一、明示的檔名導航節點，沒有正文或正文 SHA；最終正文另由文件檢查核對。

第一版驗收曾發現 Graphify 0.9.11 的 basename／label 合併與非 AST ID 重編會混合現行／歷史文件。失敗圖與 verifier 原件保留於 `graphify-out_failed_v1` 及 `graphify_final_verification.failed_v1.json`；第二版只讓原 AST 經官方 `build_from_json`，其後加入保有完整路徑身份的明示導航，再使用官方 cluster／analyze／export。第二版 verifier 又發現自身把預先宣告的本頁檔名節點誤套一般未凍結文件規則；原失敗收據保留為 `graphify_final_verification.failed_v2.json`。第三版只修正這一精確例外，並加強唯一節點、來源、正文排除與無 SHA 檢查，其他來源與 Counter 條件不變；未重建或改動第二版圖。差異與 pins 分別記於 `graphify_rebuild_v2.json`、`graphify_verifier_v3.json`，另有獨立靜態複核。

最終圖譜收據為 `output/qa/doc_clarity_graph_20261015/graphify_final_verification.json`，`passed=true`；受控驗證 Job 為 `single_owned_qa_9620b588a45c44bcbd8755346212b5d8/receipt.json`。根目錄原 `graphify-out` 的 7,011 檔及其中 memory 的 107 檔，建圖前後 metadata 指紋完全相同，沒有覆寫既有圖或記憶。

獨立複核另指出第三版 verifier 雖核現行 summary 的產物 SHA，沒有直接使用 amendment 內的固定 graph SHA。Root 最終驗收因此另核已釘選的第二版失敗報告 SHA，再把其中全部七個產物指紋與最終 verifier、實際檔案逐一比較，並核對 amendment 的 graph SHA；通過才產生 `root/graph_exact_output_verification.json`。精確第二版產物保留的結論依此收據與第三版驗證共同成立，不只依第三版的 `passed` 欄位。

六個廣義 query 與六個精確來源 explain 均實跑通過，收據為 `query_smoke.json`、`focused_lookup_smoke.json`。廣義 BFS 在 600-token 顯示預算下仍可能先列高連結的歷史索引，這只證明可遍歷，不能視為答案排序已最佳化。尋找已知入口時使用完整來源路徑的 `graphify explain`，例如 `docs/07_guides/TRIAL_VERSION_GUIDE.md`；六項 explain 都命中預期來源。產品狀態與適用限制仍需讀其權威正文。

## 最終文件檢查與仍保留的理解負擔

全庫 tracked Markdown 加本輪新增指南／QA 共 **1,595 份**完成連結及功能映射檢查，連結／Feature Map／Context metadata 錯誤皆為零；49 處外部證據引用識別為已登記，34 個冷封存根的 metadata 可用。五個 Level 2 領域 Context 均在 12,000 字元預算內，Unknown 為空。這是連結、責任與機器 metadata 檢查，沒有宣稱逐字核讀全庫正文或取代產品 QA；最終當次來源 pins 與收據由 `output/tasks/doc-clarity-repair-20261015-01a1432c/root/final_summary.json` 指向。

仍明示保留以下範圍：

- 原始長 QA 與日期化附錄保有唯一輸入、失敗及資格界線，本輪已改善其主題入口，未重寫每段歷史正文。篇幅長不單獨等於未維護。
- 圖譜有 9,166 筆 AST 關係因端點未完整解析而另存診斷，沒有做跨分塊或語意推論；2,158 個明示本機文件連結的目標不在凍結來源集合，另存覆蓋診斷。後者不等於 2,158 個壞連結，全庫文件檢查另行判定。
- 開發持續前進，建圖期間 HEAD 已變更。verifier 執行當時列出三份非關鍵入口的正文漂移：資料政策原 QA、推薦／研究分冊及產品完成計畫。其後另一 owner 又在主手冊及觀察清單／持倉分冊加入月營收來源單位守衛說明，最終來源鎖定因此先攔截交付；Root 核 exact diff 確認只新增來源分支段落、保留既有 headings／71固定包界線與本輪導航，記於 `post_graph_document_drift_review.json`。整理71指南時也移除指向本輪外仍未追蹤的啟動 QA 連結，正文仍說明固定包尚未含後續修正。五份現行正文加指南都可能比圖更新；圖仍代表明示快照，後續問題須核對現行原文，不能把較早的 verifier 結果當成交付時所有入口無漂移的證明。
- 冷封存登記只證明已知落點與 metadata 狀態，沒有重新驗證內容雜湊；版本入口對照也沒有提升任何真人旅程、金融或 Gate 接受資格。
