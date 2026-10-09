# Baldr 平行接續工作與接受邊界

依據原 `docs/superpowers/plans/baldr_product_completion_plan_20261006.md` 的 P00–P14／M1–M3 與 `BALDR_COMPLETION_GAP_REVIEW_20261008.md`。本表記錄本輪實際分工與後續依賴，不宣告完整產品完成，不取代原需求或 Roadmap。

| 工作 | 當前證據與缺口 | 本輪責任與下一步 |
|---|---|---|
| P05／P09 H20 原保存研究 | 固定來源 s3 的 4,161 檔／22 pins 已核；純來源封套不能證明 Main 操作、原十股或 684 bp | H20 agent 執行真正合成 Main 的名單→2382→摘要→返回→收藏→新讀取重開，保存分段時間、程序清理與來源起訖；root 複核後再處理原來源與同版候選 |
| P02／P04 F02 排列與複合篩選 | 固定 v3 的 processed／missing 改數符合 store；獨立審查指出會員、排序、量能 ratio 與政策斷言不足 | F02 agent 在新 v4 補原始資料獨立 oracle、AND／OR 全政策、missing ID 與逐頁集合；root 審查後才執行隔離 producer，不改 v2／v3／g 封套 |
| P03／P04 F12 月營收 | 來源 45 項、reader attempt03 的 8 項已通過；UI／收藏／跨程序 exact reopen 未完成 | 營收 agent 先補原 snapshot＋raw capture 唯讀重開 seam。新 operation identity 可重新發行；原來源、cutoff、method、完整 cohort 與事實 identity 必須不變，不從 live DB／latest 補值 |
| P01／P13 效能 | 1,000 檔矩陣的 page／filter／sort p95 未達門檻；局部 JSON 優化不能折抵整體測量 | 待 F02 與來源契約固定，另分派 query 熱點與固定版本重測；沿原 cold／warm、資源與完整母體範圍 |
| P03 F17 正常更新閉環 | 保存 bundle 與 catalog 有基礎；正常 updater→typed pins→產製→收藏新程序未完成 | root 核對 `refresh_current_market_status_observation.capture_sources` 的 raw capture 出口與 bundle `create_from_pins` 三組 exact inputs，後續建立具名來源 adapter；取消／失敗不發布，current-only 不提升 PIT |
| P06／P08 M3 情境與策略帳本 | 原金融引擎可復用；至少兩策略獨立帳本、成本、歷史比較與新程序接受尚未證明 | 前述資料鏈穩定後分派獨立帳本路由；保留 500000／8 檔有版本政策與 Decimal，不將 H20 毛報酬當權重 |
| P07 與其餘 F01–F23 | F03 KDJ、F06 收斂、F08／09、F10／11、F13–16／18、F22／23 的保存事實或策略仍缺 | 各資料域另立來源、可得時間、方法與全母體任務；既有五項技術規則不能替代多策略或三面向共振 |
| P10–P14 與真人接受 | 新候選尚未完成全流程與 Python／EXE 同版接受；3–5 位產品試用未證明 | root 整合、跑必要 UI／型別與同版驗證、同步 Manual 後提供精確啟動檔。真人驗理由最後段、窄窗、2382 下鑽／返回／收藏重開；不要求使用者代跑工程 QA |

上述三位 agent 的檔案範圍分開。營收 backend 最小 reopen seam 已釋出，UI 與共用 Main／Watchlist 路由需 root 順序接收，避免其他聊天的 dirty 內容被覆寫。原始資料、正式排程、模型訓練／啟用、交易、push 與 main 發布不納入本輪實作。

## 正常產製入口的實際接續邊界

Root 已對照目前 UI：`DailyMarketTechnicalUniverseV4View` 有背景產製入口及 `productionFinished` 訊號；`DailyMarketTechnicalV4DeferredProductionSetup.prepare_request()` 會固定母體、來源資料庫與決策截止時間。這是技術母體的入口，尚未自動完成官方市場／處置來源的 bundle 產製。官方處置 view 目前是保存研究的讀取入口。

已完成的 `selection_current_source_pair.publish_current_selection_bundle()` 可以沿既有 writer 保存同版雙來源，但正式 UI 還沒有串接此 adapter。下一步需由完整技術產製結果取得 generation、plan、receipt 的身分與 bytes SHA，再於背景任務交給 adapter；取消、失敗或 partial 結果不得觸發 bundle 保存。不能只因 `productionFinished` 發出就當作完整來源已具備。

來源時間必須與技術研究同組核驗。既有 bundle writer 要求市場來源的 cutoff 與技術 plan cutoff 相同，來源觀測與發布不能晚於截止時間。因此「今天抓新來源，再附到昨天研究」會被正確拒絕；不得改舊 cutoff 或在測試外凍結現在時間來通過。正式新研究流程需先準備相容來源，再以明示截止時間產製技術母體；讀舊研究則沿原保存來源重開。

UI 接續驗收至少需真正背景產製→完整 bundle→catalog 列出→下鑽→返回→收藏→新程序重開；另驗取消、partial、來源時間不相容與指標移動。backend 合成 writer 的成功不能替代此流程或 EXE 同版接受。
