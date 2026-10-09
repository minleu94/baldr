# Baldr 平行接續工作與接受邊界


## 2026-10-09 本輪最新責任與下一整合門檻

本段為下列歷史 attempt 狀態的最新補記，不覆蓋原失敗封套。三個子代理名額均已分配；Root 負責凍結來源審查、獨立測試及共用入口整合。

最新接續：H20 E 四個 native no-Main 清理案例已由 Root 獨立通過，F controller 正接同一 frozen E 並補 Main worker／Job 終態要求；F02 c／d continuation 均失敗且終態，owner 正對照實際 VerifiedState API，先準備 provider-only 原來源核驗，沒有新 fullrun 授權；F06 collector `6bf71603` 已中央11項通過，owner 已獲准新增固定 MA→KDJ→volatility observer group v2／測試／文件，保留舊共享入口，尚不發行來源資格。下列較早 attempt 說明保留為歷史，不代表仍有 live process。

- H20 owner：修正 QA child 讀取固定 `CopiedWalGroup.source_start` 的 API 名稱，補半安裝故障的受控 abort，再以新隔離合成根跑 H20-first 正例及主要錯誤／次要清理錯誤案例。只有實際 reader、permit、私有副本與 keeper 收尾通過後，才審完整 Main 啟動；不得以無 Main seam 的零 worker 數代替 Main shutdown。
- F02 owner：完成 query_continuation_only 的不可變候選與啟動計畫，沿原固定 oracle 執行完整母體矩陣。舊產製失敗封套、來源唯讀能力及起訖 pins 保留；不能將只讀重開診斷當完整 query 驗收。
- F03／F06 owner：F06 Decimal leaf `8816644c` 已核13項；波動請求／predicate／未核排序契約 `4a1ead28` 已核23項。KDJ 純查詢契約已於 `a56a5cff` 保存，Root 重驗18項通過；現在接續F06有界collector與三投影原子publication方案，不修改共享 reader。後續統一選股器必須同次 exact read 投影 MA、KDJ、波動，單一外層 AND/OR/unknown 與全域排序／分頁，不能以各查詢交集替代。
- Root：核以上固定產物及全母體結果，接續原1,000檔效能、Main／EXE 同版與 Manual。原 P00–P14／M1–M3／F01–F23 未完成項仍全數保留；現在沒有新的真人驗收入口。

## 本輪接續更新

F03 開工依據已重新對照原計畫第 5 節：既有 KD 是 STOCH 5/3/3 SMA，交叉需同股今日 K>D／昨日 K≤D，低檔 K<30、中檔 30≤K<70。KDJ 必須另立自有 J／平滑／交叉版本，保存參數與方法 identity、兩日同股、有限值及暖機狀態；未有 J 不得改標籤冒稱完成。後續 owner 的第一個交付物為具體方法契約及 Decimal／PIT 自查，再實作真完整來源的 cross／no-cross／unknown 與保存重開測試，不能用 UI 新勾選框替代底層事實。

- F02：q 真 writer／stable loader seam 已接受；r 完整矩陣已實跑一次，fixture_creation 讀回 generation 路徑失敗，Job 已 closed／zero-owned。正定位長路徑或 guard 路徑轉換，不縮母體、不清除失敗封套。詳 root guard 審查文件。
- F12：Main／Watchlist 收藏保存及專用重開路由已接；更新 UI 85 項、QA 25 項零失敗／4 skips、全 mypy 926 檔通過。月營收 snapshot atomic 長路徑已修正；六欄 tooltip／失敗保留小測 Root 2 項通過。真完整 UI attempt04 仍待終態，不能宣告完整旅程完成。
- H20：C01 未通過 private directory guard；新 D keeper／market WAL copy／typed H20 共存接縫正在修正正常與故障清理。Main 尚未放行，原十股／+684 bp 與 EXE 仍待。

下一批平行工作仍是原計畫中的缺口：一個名額於 F02 契約固定後接完整 1,000 檔 page／filter／sort 熱點與原矩陣重測；另一名額於 F12 真收藏重開接受後接 F03 KDJ 方法版本及完整來源規則，既有 KD 不作替代。H20 owner 維持完整 Main／同版／原來源交接，Root 負責共享入口與候選整合。F06、其餘資料域、M3 兩策略獨立帳本及 P10–P14 仍保留於原缺口表，不因這三條局部工作完成而結案。現在不要求真人代為排查已知工程失敗。

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

目前 `selection_current_source_pair.produce_current_selection_bundle()` 已由技術研究頁「產製技術與官方來源研究」背景入口接續。真正 producer 完整結果取得 generation、plan、receipt 的身分與 bytes SHA，再交原 writer 保存固定雙來源；取消、失敗或 partial 結果不得當作聯合保存成功。實際驗證與限制見 `BALDR_F17_NORMAL_PRODUCTION_UI_REVIEW_20261009.md`。同一候選完整 Main 與 EXE 仍待接受。

來源時間必須與技術研究同組核驗。既有 bundle writer 要求市場來源的 cutoff 與技術 plan cutoff 相同，來源觀測與發布不能晚於截止時間。因此「今天抓新來源，再附到昨天研究」會被正確拒絕；不得改舊 cutoff 或在測試外凍結現在時間來通過。正式新研究流程需先準備相容來源，再以明示截止時間產製技術母體；讀舊研究則沿原保存來源重開。

UI 接續驗收至少需真正背景產製→完整 bundle→catalog 列出→下鑽→返回→收藏→新程序重開；另驗取消、partial、來源時間不相容與指標移動。backend 合成 writer 的成功不能替代此流程或 EXE 同版接受。

## 本輪接續紀錄

- F17：真正 Qt 產製、catalog、下鑽、返回、收藏 DTO 已有合成驗證；服務保存至隔離觀察清單 repository 後，獨立 Python／Qt 程序嚴格重開同版研究的六項測試通過（10.18 秒，提交 `50a35277`）。沒有完整 Main 觀察清單按鈕、原 H20 或真人接受證據。
- F12：archived finish 歷史路徑解析缺口已修正並提交 `f6dd33b3`；backend 最終 61 項通過、1 項因 Windows 檔案 symlink 權限跳過。Root 的 index/query 相容測試另有 9 項通過，但整批耗時 139.10 秒不是效能達標證據。owner 正在接續真正兩來源原子重開 adapter；root 預審已要求修正 WindowsPath 型別拒絕與取消前仍建立 operation 目錄，owner 已回報修正，實際正負旅程尚待驗證。
- H20：合成 Main attempt p 在 verifier 錯誤模組名稱階段失敗，未進入 Main；錯名來自 dual child extras。新 b 相容層保留全部 23 個驗證項，root 已讀 diff 並在隔離原生環境複驗 13 項通過（0.70 秒）；見 `BALDR_H20_VERIFIER_MODULE_COMPATIBILITY_ROOT_REVIEW_20261009.md`。下一次 q 封套準備中，三檔及 dependency 雜湊未完成 root 複核前不執行 Main。
- F02：l guard-only 已有獨立真實執行證據，但記憶體 probe 確認 mutable object/manifest budget 各增加 1 byte 仍被接受，是實際缺陷。owner 正在新 m 候選釘住硬上限並補 path-only 與 binding mutation 負例，未放行 full producer。scope 可對本次合成空 DB 做真唯讀驗證，須分別記錄 scope、來源 reader 與 producer 的連線／呼叫數，不能宣稱總 SQLite 連線為零。

## 最新接受與執行狀態（上述 attempt 紀錄保留為歷史）

- F12：真正 exact reader 發行的穩定 recipe 已完成兩次重開，包括翻頁後保存 page 1 再重開，正例 168.11 秒通過；Root 另複核方法契約、三檔 mypy 與 compile。新 bundle-source 公開入口正例與取消測試 2 項通過（140.89 秒），實際 read_exact 計數為 1。子代理正在做獨立 Qt view、typed bookmark DTO 與原子 restore；Main／Watchlist 共享路由仍由 Root 後續序列整合。詳見 `BALDR_F12_SAVED_RECIPE_ROOT_REVIEW_20261009.md`，尚無 UI／EXE 完成結論。
- H20：WAL keeper 小測與 controller 預檢通過，但 B Main 在載入 bridge 前因依賴路徑深度錯誤失敗。Root 在 C 啟動前另攔下舊 bridge SHA 綁定；已修正並補 11 個實體檔 pin 一致性檢查。Root 重算 v2 八個 runtime pins 與唯一根不存在後，授權 C01 一次完整合成 Main，owner handle 64727 已啟動。原 +684 bp／原十股、完整原來源與 EXE 尚未接受。詳見 `BALDR_H20_WAL_KEEPER_ROOT_REVIEW_20261009.md`。
- F02：m 固定上限守衛已接受；n 真產製在 fixture_creation 的 runtime binding 核驗被拒絕，未完成 oracle。o／p 保留 fail-closed 條件並加入具名診斷；p 真固定 writer 小測 43 項 qualification checks 全通過、25 項預期拒絕、producer/worker 0。Root 重新計算十個 source pins、確認新 target-only 目錄單檔與既存隔離 parent 後，已授權 p 一次完整母體執行，終態與 oracle 結果仍待複核。整份 QA supervisor mypy 不 clean，不冒稱產品 gate 通過。

這些進展沒有縮減 P00–P14／M1–M3／F01–F23。完整母體效能、其餘資料域／策略、M3 獨立帳本、Main／EXE 同版與真人接受仍沿原補完計畫推進；真人目前不需要重跑舊候選。
# 最新平行分工與接受範圍

後續更新：KDJ 純方法切片已保存本機 dev `0460f45f`，Root 複驗 12 passed／兩檔 mypy clean，舊 v4／window reuse 11 passed；全母體接線仍未完成。F02 native002 exact 重開成功，原 full failed 保留；下一步 query_continuation_only 新候選須先審。H20 候選另發現 frozen legacy output containment 與 sibling layout 不相容，先測最窄 QA module-local root adapter，不先 Main。Root 並完成 F06 原料／方法盤點，見 `BALDR_F06_VOLATILITY_EVIDENCE_PLAN_20261009.md`；現有 bandwidth 方法不一致與缺值填零不能當收斂規則。

- F12：真來源 UI attempt04 已通過（1 passed，246.52 秒），覆蓋跨頁／比較／服務收藏與 Main unbound route fresh restore；不等於完整 Main constructor 或新版 EXE。Root 必要 UI gate 再驗 85 passed、QA 25 passed／0 failed／4 skipped、mypy 926 files clean。Owner 轉 F03 KDJ 獨立契約與缺口規劃，既有 KD 不改名替代 KDJ。
- H20：D 正向與故障注入合成接縫已由 Root 實讀接受；兩份 reader 共存、來源 operation pins、3/3 私有目錄清理與 alias 還原通過。Owner 整合 QA-only Main controller／child，先提出新固定 pins／計畫，尚未放行 Main；原保存 684 bp 仍未接受。
- F02：r 完整母體在 fixture_creation 失敗。唯讀重開另定位 extended path strict realpath 的 WinError 5；原 receipt WinError 3 無 traceback，兩者不混為同一 callsite。Owner 評估保留 strict canonical／reparse 的修正與診斷，不重跑 producer、不縮短 QA 路徑掩蓋問題。
- Root：覆核共享 Main／Watchlist 整合、驗收文件與 gate。完整 P00–P14／M1–M3／F01–F23 仍持續，沒有新版啟動檔或當下需要真人操作的項目。
