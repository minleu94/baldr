# 三階段整合修復與驗收（2026-10-02–03，有限工程已完成）

## 目前狀態（2026-10-03）

### 最終整合接受（2026-10-03T11:12:32.922050+00:00）

本次三階段的有限工程修復與整合驗收完成。排程設定及兩個既有 automation prompt 已實際套用並讀回；Gemini A／B 研究通道、真實研究訓練、保存、新程序推論與 Legacy／Bank sidecar 已接通；四大核心用途已用有內容的 Windows 原生視窗核對。正式資料資格仍依原防護判定，研究工程完成不授予歷史 PIT、formal credit、模型 promotion 或投資效果資格。

#### 同一個明確版本與驗收依據

- HEAD `e1c43716e39dcf535b203680f2af376c85e820aa`，branch `dev`；驗收使用工作樹，納入相關 tracked 差異、Gemini 新增檔及其他相關 untracked 程式，inventory 不把其他人的 dirty changes 歸為本次成果。未 stage、commit、push、merge 或部署。
- 最終 code version：`phase3_native/version_native_20261003T103404928459Z/version_manifest.json`，SHA-256 `c625fb658edf9d012f7dce9805a8bb1609b0ea67556df234951179cc7efb6392`；目前已完成原生驗收的版本 pin 為 `c625fb658edf9d012f7dce9805a8bb1609b0ea67556df234951179cc7efb6392`，共 986 個檔案。相較 7eb 歷史原生驗收版（984 個檔案），此次只修改兩個 UI 程式檔（個股摘要文案、月營收診斷呈現），並新增兩個獨立測試檔；982 個原檔相同。完整版本另保存 986 個實際 code／test bytes、工作樹 patch、owner manifests、22 個輸入 pins、重要設定與文件快照。凍結版本的文件不含後寫的驗收敘述；最後 rollforward 收據須獨立引用。
- 模型設定已查核：root GPT-6.1 Sol Ultra，四面向 reviewer GPT-6.1 Sol High，實作 GPT-6 Luna Max；後續優先重新派發既有 worker，未巢狀生成繞過配額。四份完整審查報告為 `phase3_data_review/REPORT.md`、`phase3_ml_review/REPORT.md`、`phase3_ui_review/REPORT.md`、`phase3_docs_review/REPORT.md`，均已由 root 完整查收並整合去重。
- c625 版本的回歸：原 12 個測試檔未改，51 passed；更新頁 Workbench 85 passed；validator 25 passed／4 skipped／0 failed；指定 mypy 範圍 751 個 source files 無問題；兩項顯示修補定向 `8` passed，四檔 compile 通過。回歸收據 `phase3_native/cross_page_regression_20261003T103459276791Z/readback.json`（`f39f3114a8a8aff30913d3cd872f0f0294ff6160833dab6f038e23d8ab82d4bf`），指定 UI 驗證 `phase3_native/final_ui_validation_20261003T103427832370Z/readback.json`（`d06b0abd733be4216c90ecd7f66e42f4c70f9ea2332d27778ad2ae122bd0108c`）。四個 validator skip 是避免實際每日下載與合併；ML／來源舊路由的 Windows symlink privilege skip 保留，另有真實 NTFS junction 拒絕驗證，沒有改寫成原 skipped 通過。早期 50 passed／1 failed 及其他失敗全部保留。
- c625 原生接受收據 `phase3_native/root_native_final_acceptance_20261003T105541987127Z.json`（SHA `483170b2c330b0121ce51435ff7a5966b073e2082c846289f56d33cade0597b6`），43 筆觀測（含載入中及未成功 resize 的嘗試）、兩個正常 session；baseline PID 8756 與 cost PID 49556 均 exit 0，close 後版本核對 986 files。最終原生接受索引為 `phase3_native/root_native_final_acceptance_20261003T105541987127Z.json`（`483170b2c330b0121ce51435ff7a5966b073e2082c846289f56d33cade0597b6`）。舊 7eb 版的 100 筆原生觀測仍是歷史證據，其中當時的文案與診斷缺口已由 c625 修復及重新驗收，不冒稱為 c625 新接受。c625 的兩個候選、持倉、缺股 9999 與月營收 1,855 筆失敗摘要均有實際觀察。Computer Use screenshots、UIA、視窗、image metadata 與版本 hash 分開存證；offscreen／mock／單元測試不代替 Windows 原生接受。

#### 排程與 automation：設定已套用，實跑與自然觸發分開

21 個 root tasks 的最新現況以 `scheduler_current_20261003T103536841781Z/readback.json` 為準（SHA `226e7c34492a204fbb7332e9f9976ae6c9b1b526f165e4706bfe14385a0ec651`）；09:02 收據 `scheduler_current_20261003T090250459791Z/readback.json` 是歷史快照。COM 查詢 exit 0 且讀回 21 個 task 設定；QA helper 仍有 24 個 IUnknown release 警告。先前預設 sandbox 的 `query_error` 不足以證明 task 不存在。Enabled／Ready、actions／參數／working directories 均以實際 COM readback 記錄，不把警告或 CLI exit 0 解讀成所有 operational logging 正常。兩個盤前 trigger 改為台北 08:25，aware instant 為 UTC 00:25／PDT 前一日 17:25；其他 19 個 triggers、principal、timeout、retry、battery 與並行設定保留。before XML、部分套用停止記錄、readback 及回復資料在 `scheduler_apply/`。五個歷史非零 LastTaskResult 保留，不用 CLI exit 0 取代 Scheduler 歷史。

`baldr scheduled evidence morning report` 與 `晚間學習與 Paper 排程驗收` 的既有 heartbeat 已用 automation 工具原地更新，09:06 精確讀回相同；識別、thread、名稱、模型、ACTIVE、PDT 05:30／06:20 與通知設定保留。最後 prompt 明確綁 canonical output root、parent／child ID／SHA／日期、Quick 120 秒、weekly 1,170 秒的有界等待、partial lanes 與有意義變化通知；監測不啟動 collector／HTTP、不任意重訓或每天重構。完整 before／after、替換 prompt 及 readback 均在 `automation_binding_update_20261003T090555251181Z/`（readback SHA `29b91cb37bb5324c123851cd89e8325f757d5c8dc99086d9a0e62e4bc40115bf`），沒有「尚未實際套用」的本輪設定。

weekly wrapper 已真實受控執行 `09:27:03–09:28:21 UTC`，parent `weekly_c6a1f31540154352b2044422ff55d362`，exit 0，strict consumer `verified`；root 另核 85 個 artifact pins。core=`pending_human_review`、monthly=`captured_verified`、quarterly=`captured_with_review`、formal credit=false。新 monthly 33 個公告事件／33 projections、11 檔股票；新季度 26 個 requests／3,958 numeric rows／3,950 preview rows／8 review items，可得日全部 null。raw source_date `1151003` 不能當公告可得日。這組數字屬 10/3 新 weekly run，不覆寫 10/1 舊 standalone 的 3,960／3,952，也不與 UI 的 1,855 筆 Aug snapshot 混算覆蓋率。actual readback SHA `53364a1c330253e2a7afe57f41602cfa20690ddb4aa31b59123e9f6e5dcfb890`；root pin acceptance SHA `d8748a496f0e03b1f02a7ba5a89f6cad76f9d071dc8f5f8daea134455a1f311c`。合法 age 46 秒 pending 已觀察，沒有提早報失敗。

Paper／ML forward 已另取得 10/3 08:25 自然觸發及 08:30 `weekend_closed` 的真正 terminal／consumer，LastResult=0、休市 no-work、不新增 snapshot／training／credit；不是舊 9/30 receipt 冒稱本次成功。其他受控 CLI／Task 實跑依下方具名收據記載，不宣稱 21 個 tasks 全部取得新的自然觸發成功。

#### Gemini 成果、修正與實際 ML 使用流程

原三檔 18-test 成果已獨立重跑；其後補入正式未 opt-in、防範 output junction／alias、schema／hash／row count／截斷 gzip／partial 清理、安全重試、Decimal scale、報表基礎、fold qualification 與消費入口回歸。不能以最初 18 passed 外推訓練完成。已修明確 research flags 傳遞、完整 source-revision dependency pins、completed pending／final receipt 配對、原逗號數字解析／TWD 單位、outcome labels 的 t 特徵→T+1 進場及成熟時間、purge 後合格 folds、缺值 masks、strict manifest hash ABI、模型載入相容與 Legacy／Bank immutable consumer 接線。未知 statement basis、正式預設與非 opt-in 仍阻擋。

A 真實年度 raw 以 2317／2330、2023–2026、同一已驗一致副本建置：73,234 observations／281,699 values／52 欄，不把 context observations 冒稱股票訓練樣本。Direct／Outcome 與模型使用真正較晚的建置／fit／可用時間；原公告日未知保持 null。B 單日 projection→公開 adapter→隔離 Store→immutable consumer 已真讀 1,962 observations／7,658 values，Decimal 逐值一致；其真實單日用途是 numeric ingestion，資料不足以單獨聲明歷史模型訓練。研究模型依明確 lineage 使用經核對的歷史 prefix／Outcome Store，沒有讓未成熟 B 單日資料自動湊出評估 folds。

本輪已接受的 ML 實跑完成 current-restated CORE19+19 masks（38 features）的真實 estimator fit、保存與兩個 cold Python process 重新載入推論，8 OOF blocks／905 市場日／1,771 rows；Legacy／Bank 原入口 sidecar 亦有同模型／cohort／source binding 的 terminal。這些是具名 ML 執行證據；16 個 ML 程式 pins 在 c625 中相同，沿用已接受的 fit／cold-load／sidecar 結果，不重複訓練，也不把 ML CLI 當原生 UI 證據。c625 原生流程另以新 125% 成本情境載入已保存 ID `rec_3e78a92cdfc04edf9f18618747fa0c29`，33 筆建議及 `0310` watchlist 均成功讀回；持倉均價 2750、投入 2,750,000、毛損 −250,000／−9.09%、WATCH，Exit 仍缺來源。四筆成熟 H5 的毛／成本／淨報酬曾以 Decimal 獨立核對；10/2 H5 未成熟仍為 null。研究部署、啟用／停用、隔離配置回退、錯 38-feature/V2 schema 的 quarantine 已驗，production alpha=0、teacher／historical PIT／formal training／promotion=false，正式 pointers 與 active V2 55 項 protected files 未變。ML root 接受 SHA `007d245a4228d9f260ef3e4fd39373ce3eb4c62dac8129e88e29f33f2f8afc9f`，模型 manifest SHA `f4f8b70f2da3515089007698c44497ca32fa7b56258cec8880e62e8aa6fe2e2b`；原始 raw task 已於 07:04:44 恢復 exact before XML／Enabled／Ready。原正式 calibration cohort 與研究推論樣本不同，未強塞研究股票成為當日推薦。

#### 原問題逐項結案狀態

| 原問題 | 本次結果與仍有效的限制 |
| --- | --- |
| Scheduler 證據不可得 | 21 tasks 真實存在、設定已套用並讀回；Operational logging 仍有 Windows ACL Access denied，未擴權。 |
| Phase3C 休市／交易日矛盾 | 共用已驗日曆、unknown 不誤列休市、合法 cache fallback 與統計修正；10/2 TDCC 4,078 candidate rows、信用 2,216 rows／8,864 值與原來源相同，法人 current；六項原 institutional reconciliation conflicts 保留。 |
| Evidence date JSON／dry-run mutation | 具名 date／datetime ISO 編碼、合法既有 hash 相容、unknown 拒絕；readonly repository 與 Exit 雙日期契約修後取得新 report／summary／strict consumer，正式 DB bytes 不變。整體研究 Evidence 如仍缺持倉警示／risk prompt，保持其 gate，不追認 formal write。 |
| Fundamental／TDCC freshness | 季度 expected 修為 Q2，不因進入 Q4 即要求過早季度；正式 monthly June／expected Aug、statement 2024-Q1／expected 2026-Q2 真 stale，current-observed Aug／Q2 partial。TDCC 週頻、實際觀測可得日與正式 PIT 分開。 |
| Recommendation passed／品質 | 分開執行、研究品質、策略排除與可用筆數。舊 200 requested／15 eligible／185 strategy exclusions 與本次穩健 UI 33 rows 屬不同實際設定；degraded 不等於勝率。canonical typed ID／payload／33 股票及 198 Decimal scalar 已核對。 |
| Paper／capture／Legacy／Bank | Capture 的 raw-before-parse、精確 MIS `0000`、失敗 custody、cleanup blocker 保留與 quote 呼叫相容修妥；新真實盤後 body 僅作 schema 證據，不能回填交易日 capture。Legacy／Bank 研究 sidecar 已真實接通。Paper 當日自然休市 no-work 通過；歷史 10/2 EOD 缺 capture／archive 晚於 decision，仍不追認交易日完成。 |
| Paper 日期與 1418 identity | 分開合法 snapshot／分析日及 freshness cutoff，不改舊列。1418 是機器研究 seed、entry identity／thesis 未證，保留 unknown；不能補造使用者持倉。 |
| Paper 三層 schema／舊 receipts | root、isolated_scope、nested preopen 各自 strict schema；新自然 producer／terminal 已核對。舊 receipts 保留歷史身份，不用新 emitted_at 冒充。 |
| Weekly／credit | 同次 parent／child pins、pending 時限與 partial lanes 已修並實跑；人工 review 和 formal credit 仍是獨立治理。 |
| 盤前 `0xC000013A` | 歷史中止的因果證據不足，保持原因未知；後續真實自然休市流程及 COM cleanup 修後可驗，不據此猜為 app 更新或聲稱修掉歷史中止原因。 |

#### 四大用途、輸入變動與失敗恢復

首頁 DecisionDesk 顯示的分析日為 2026-10-02，live Market 頁的分析截點為 2026-10-03；兩者是不同截點，不宣稱兩頁數值在同一截點下相同。歷史 7eb 版已核對盤勢、選股、個股研究與持倉健康路徑及 2330、1235／1414、8227 的返回情境；這些路由、producer、保存及取消／重試路徑在 c625 中未變，但不把舊 7eb 原生證據冒稱為 c625 新原生驗收。c625 版已實際觀察 100% 顯示下的兩個候選、持倉、缺股 9999 與月營收 1,855 筆的模態框、記錄及失敗摘要；最終 c625 原生接受收據見上段。日期顯示按各頁實際分析截點判讀，不能只依 launcher 宣告。

盤勢實際上漲 941／下跌 841／平盤 179、缺一個未知值安全排除、上漲比 5,280 bp；研究與選股價格 1235=31.70、1414=17.25。持倉 2330=1,000 股、2500，Health=WATCH／PortfolioConditionMonitor；entry provenance 未知、Exit 欠來源時沒有賣出動作，歷史 8/18 警示明確為歷史。1414 籌碼只到 4/24 與月營收 June 的舊資料可讀，但不足以聲明當日來源 current 或 PIT。

隔離輸入只把平均成本 2500 改為 2750：投入 2,500,000→2,750,000、毛損益 0→−250,000／−9.09%；價格 2500、股數 1000、WATCH、Exit 缺件、市場 breadth 與 33 候選／198 Decimal scalar 保持一致，費用 3563／稅 0 獨立列示。舊 7eb 版的正常保存產生 baseline `rec_52fb34e4c098485da4ed36d30f7e58cd` 與 cost `rec_3e78a92cdfc04edf9f18618747fa0c29`，各自 33 檔 watchlist；這是歷史產物，其 producer／保存路徑在 c625 中未變；c625 的新 Python process 已正常載入新 cost ID／watchlist，不把保存當時內容冒稱新運算。

四筆既有 saved artifact 的獨立唯讀比較收據為 `native_recommendation_fourway_compare_20261003T104352Z/readback.json`（SHA `982c2e22958e41d58eff843dc4fd242df2d33b188ac6c470b7606a4cfbf27402`），摘要在同目錄 `REPORT.md`（SHA `b6649a902dd325462314b69a45c0fe789964f73dccfb1e32b6e52c9da1aa1c8e`），檔案 manifest SHA `f30a3901191290268b1e2a543f648651f5c56cfb0d064a96987045862f088e56`。四個 typed result ID 是 `rec_52fb34e4c098485da4ed36d30f7e58cd`、`rec_afed4f8a8cd2419b8d1c750771278690`、`rec_e81f0a059e9a421da6bbcb0f695c0e2a`、`rec_3e78a92cdfc04edf9f18618747fa0c29`；先前彙整中 e81 的 ID 有誤，以上述精確 ID 為準。四者每筆 33 rows、198 個 Decimal 六指標完全一致，`all_scalar_comparison_true=true`。差異只在保存／執行識別與時鐘、以及各次 industry observation 的 observed_at 和衍生摘要 hash；底層 212,500-row rowset SHA 相同。四份 artifact 均是 10/03 request/context、10/02 market snapshot，且仍為 `degraded`、`legacy_source_identity_unbound`、`source_refs=[]`、`available_at=null`。`REPORT_ERRATUM.md`（SHA `6bbe563761ea8c44fafe978557243f4af302e6a2cfa1d43f60f7b02973c13ebf`）說明 raw artifact 是核對檔案 SHA、解析 schema／ID，再由既有 API 驗證 payload hash 與 index／envelope；不是另行重算應用層 payload hash。這項一致性不提升來源資格，也不代替 c625 的 native 流程：新 125% 成本程序已在上方原生收據中載入 `rec_3e78a92cdfc04edf9f18618747fa0c29` 與 33 項建議、`0310` watchlist。

缺股 9999 會清除舊 2330 facts、無價格，主要資料日未知，顯示資料不足；持倉入口的返回 breadcrumb 仍保留原有 portfolio／10-02 source context，這是返回脈絡，不代表把 2330 資料用到 9999 分析。本次最後修掉「值得看：缺少價格」文案，結論改為「資料不足，需核對：缺少最新可用價格」；主要證據欄另說明目前沒有可引用的主要資料日期。錯 canonical ID 顯示真正失敗，改回合法 ID 可重試；合作式取消未套用 partial results，之後正常執行完成、保存、重開與跨頁返回均接受。空 canonical reload 清空舊 cells，Decimal 不變且表格合理格式化。

月營收按鈕已在正常 Windows 流程完成 TWSE／TPEx 2026-08 inbound fetch：1,855 筆、兩份 raw HTML 與一份候選 CSV。source metadata 內嵌於候選 CSV，沒有獨立 sidecar；未寫正式 SQLite 或 availability mapping。接著 precheck 真讀 raw 1,855／normalized 0／diagnostics 1，`fundamental_availability.snapshot_mapping_incomplete`／unmatched 1,855；正式 mapping 最晚到 June，Aug 為零筆。最後 UI 修補將原始 code/message、繁中原因、取得核准正式可得日 mapping 後重試的下一步同時呈現於 modal／log／失敗摘要；ready=false、Apply 防護與 unknown fail-closed 不變，沒有拿抓取日補 available_at。這是「候選抓取完成、正式回填未取得資格」，不是來源解析失敗或完整歷史已修復。

舊 7eb 版確實曾在 1017×768（Qt DPR 1.0）與 1602×1030（DPR 1.25）視窗驗收；這不是 c625 新驗收。c625 的 resize attempt 未改變實際視窗大小，不宣稱 1017×768 新版成功。c625 125% 成本流程已由上述 native terminal 接受；其 launch readback 顯示啟動用 PowerShell 父程序的 .NET environment `before=null`、`after=''`、`equality=false`。子程序只繼承本次 QA 的 QT_SCALE_FACTOR=1.25；啟動用父程序已結束，沒有 OS 設定變更，也不能宣稱 exact restore 成功。早期 launch 的 restore flag=false 繼續保留。

#### 保護、文件同步與剩餘事項

原始正式 `D:/Min/Python/Project/FA_Data/sqlite/twstock.db` 3,848,364,032 bytes 的完整 SHA `d0c843fdef4c36d94ab2a031f3dcd898f3629f207bbfa93ddef8f51e157792a2` 與原 mtime 在本輪最後保護檢查一致、WAL=0；22 個 QA input pins 及額外正式 D full-SHA／mtime／WAL 檢查均由 root 確認未變。native helper 前兩次查收失敗是 QA verifier 的檔案缺席假設及正式 D pin 分類錯誤，已修正並由第三次完整接受；保留失敗啟動與 launch scale equality=false 記錄，不把它們當產品缺陷，也不宣稱環境 exact restore 成功。正常 Save 所寫的 recommendation DB／watchlist／新 inbound 候選屬 QA output，不假稱整個 QA output 根只讀。SQLite 讀回使用真實 ro／query_only／single BEGIN snapshot，舊 `-shm` 是未釘的 volatile coordination、其 mtime 變動／hash locked 均明示，未把 immutable 忽略 WAL 當一致性證明。

Manual、Snapshot、Architecture、Index 最後文件 pins 見 `docs_native_final_rollforward_20261003T105730Z/final_after_manifest.json`（`70373af2b8e57d66a339a23346943e75daabbb6206a682cb64f1dd5adf5c4769`）；操作步驟、參數、結果判讀、安全限制、回復與排錯已對齊實際功能。有效 rollback preimages 留存；weekly 兩份 post-change「before」與舊日期換行 diff 的 metadata erratum 保留，不覆寫原證據。

| 剩餘類型 | 本次交付狀態 |
| --- | --- |
| 本版可自行修復工程 | 已完成與查收；沒有留置已知核心 blocker 給「後續建議」。不保證零 bug。 |
| 本輪設定尚未套用 | 無；Scheduler 與兩個 automations 均已實際套用並讀回。 |
| 實際排程／readback 尚未驗收 | 已接受具名受控 run、consumer 及當日 Paper／ML 自然休市；其他 tasks 尚無本次新的自然觸發證據，五筆歷史非零不重寫。 |
| 外部資料／治理／權限 | 正式 Aug mapping、歷史財報 PIT／source identity／source coverage、weekly 人工 review、正式 Evidence readiness 依實際缺件保持阻擋；Operational logging 仍缺 ACL，未擴權。必須取得可核對的原可得日／identity／核准，再沿現有候選→dry-run→確認套用流程處理，不能補猜值。 |
| 自然證據／成熟／效果 | H5 成熟、新交易日 capture、長期樣本與投資有效性仍待真實證據；不作本次工程結案硬門檻，不授 formal credit、teacher、promotion 或交易權限。 |

以下全部為有日期的歷史檢查點，保留當時失敗、依賴、輸入與版本；其中「尚待／未完成／進行中」描述不代表本節接受後的現況。當前工程狀態以本節與 PROJECT_SNAPSHOT 為準。

### 歷史檢查點：2026-10-03 09:34 UTC 整合查收進度

weekly controller、純 consumer binding 與 audit 的有限修補已接受。受控 host wrapper 於 `09:27:03.213060Z–09:28:21.272468Z` 完成，exit 0；parent `weekly_c6a1f31540154352b2044422ff55d362` 的 core、monthly 與 quarterly 均由同次 run 的明確 receipt／路徑／SHA 綁定，consumer 為 `verified`。core 仍為 `pending_human_review`，monthly 為 `captured_verified`，quarterly 為 `captured_with_review`；formal credit 保持 false。執行中另觀察到 age 46 秒的合法 pending，沒有提早判失敗。readback 位於 `output/qa/integration_20261002/weekly_actual_20261003T092700852463Z/readback.json`，SHA `53364a1c330253e2a7afe57f41602cfa20690ddb4aa31b59123e9f6e5dcfb890`；正式 D: DB 與零長 WAL 的完整 hash／大小／mtime 前後一致。這是手動受控實跑，沒有宣稱新的自然 weekly 觸發或正式 PIT 資格。

09:06 UTC 兩個既有 heartbeat 的 prompt 已實際更新並讀回，名稱、thread、時間、模型與通知設定保留；讀回 `automation_binding_update_20261003T090555251181Z/readback.json`，SHA `29b91cb37bb5324c123851cd89e8325f757d5c8dc99086d9a0e62e4bc40115bf`。新增 canonical output root、parent／child binding、Quick 120 秒與 weekly 1,170 秒的有界等待、partial lane 與通知判讀；不啟動 collector 作查核、不靠 latest mtime 選任意產物。09:02 UTC 21 個 Scheduler task 皆可讀／Enabled／Ready，設定與已接受 action 相符；歷史五個非零 LastTaskResult 保留，沒有用受控 CLI exit 改寫 Scheduler 歷史。

UI 數值呈現、breadth 缺值與空 canonical result reload 已修；原始 Decimal 與 canonical ID／hash 不因格式化改變。市場焦點分析日與經來源驗證的資料日分開，空候選池改標檢查日，研究首屏顯示報告 `as_of`。最新日期修補定向 60 passed、Workbench 85 passed、validator 25 passed／4 skipped、九域 mypy 831 files 無錯。root 逐檔核對六個新 after pins、三個有效 preimages、全部 log hashes 及前六檔未變；接受收據 `phase3_native/root_date_source_acceptance_20261003T093352975879Z.json`，SHA `ff7b3f3b2e1dd4e477b3d9413cc14456b3b5cb7d35df2e0cf6cd5ab3d1080e4b`。

QA metadata 的兩項限制已保留更正：weekly 最後兩檔的所谓 before 是 post-change 快照，整輪有效回滾只能使用 09:08 的五檔原始備份；日期修補的原 diff 把混合換行誤列為差異，閱讀以新增 normalized diff／addendum 為準，原證據不覆寫。QA DB 首次查詢前後 `-shm` mtime 差異歸因未知；後續 immutable 唯讀查詢證明 QA DB 10/2 有價格與技術列、10/3 皆無，沒有據此補造 native 資料來源。

最終凍結版本的原 51-test／12-file 回歸與 Windows 原生四頁旅程仍待執行；下方早期 50 passed／1 failed、舊模型與 prompt pins 都是有日期的歷史檢查點。whole Goal 尚未完成。

前兩階段已完成其限定工程與真實研究 readback。current-restated Outcome Direct／CORE19 模型已受控訓練、保存、由新 Python process 載入推論，並接到原 Legacy／Bank 研究 sidecar；其歷史 PIT、正式訓練／校準、teacher、promotion、交易與投資效果資格仍為 false／未接受。當前 10/2 H5 未成熟，報酬與成本保持 null。正式 pointer、active V2 與正式市場 DB 沒有由此研究流程改寫。

第三階段研究模型的最終接受收據是 `output/qa/integration_20261002/ml_validation/root_phase3_ml_acceptance_20261003T070413001284Z.json`，SHA `007d245a4228d9f260ef3e4fd39373ce3eb4c62dac8129e88e29f33f2f8afc9f`；最終 manifest 位於 `output/ml_research/integration_20261002/current_restated_core19_phase3_20261003T064855260194Z/`，SHA `f4f8b70f2da3515089007698c44497ca32fa7b56258cec8880e62e8aa6fe2e2b`。root 核對 16 個 code pins、12 項實際 evidence、13 項語意檢查、兩個 cold process、Legacy→Bank sidecar、四筆成熟歷史成本 Decimal 重算與 55 個 protected formal／V2 檔未變。先前 `56f736…` 模型是有日期的中間版本，不是此接受結果。這仍是 current-restated／non-PIT 研究驗收，不授正式校準、teacher、promotion、交易或投資效果資格；10/2 H5 未成熟項目仍保持 null。raw task 於 `07:04:44.515124Z` 恢復 Enabled=true／Ready，XML 回到暫停前狀態，沒有手動重跑正式 raw。

第三階段 D1–D4 的有限程式修補已落地並通過 owner 定向測試；其中 freshness receipt 現在要求 probe 與狀態查詢位於同一台北市場日及 cutoff 同側，跨過 04:30（含查詢時鐘恰為 04:30）會回 `unknown`／`needs_revalidation`，不把舊 `expected_wait` 沿用成當日狀態。status-support 20 項、完整 UpdateService status 65 項通過；隔離重現、before bytes 與測試 log 保存在 `output/qa/integration_20261002/phase3_docs_fix/`。UI/native Windows 操作及 root 最終獨立驗收尚待，不以程式測試宣稱產品完成。

本紀錄以下各日期段落保留當時輸入、成功與失敗收據，不回寫歷史結果；目前摘要以本節及 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準。工程回歸、手動受控執行、自然定時觸發、研究資料、樣本成熟、formal credit 與投資效果分開判讀。

### 歷史檢查點：2026-10-03 07:36 UTC 資料與自動化補件

10/2 信用候選資料的原 producer 實際執行窗口為 `2026-10-03T06:13:58.216205Z–06:14:20.531675Z`；root 於 `2026-10-03T07:33:55.149617Z–07:34:13.231059Z` 另行唯讀核對：2,216 筆來源列與候選 DB 列逐筆吻合，8,864 項量值比較全數相同；06:16:53 UTC canonical freshness 將 `credit_transactions` candidate lane 標為 `current`。正式資料庫完整 bytes SHA 仍為 `d0c843fdef4c36d94ab2a031f3dcd898f3629f207bbfa93ddef8f51e157792a2`，六個受保護表的列數與內容 hash 前後一致；`historical_pit_credit=false`、`formal_source_qualification=false`，這不代表歷史 PIT 或正式來源資格。readback 為 `output/qa/integration_20261002/root_credit_supplement_20261003T073355149617Z.json`（SHA-256 `5367a7a871f38715794444144125ea0981ef5160256b51968197ec7ae5d51ddd`），freshness 投影為 `output/qa/scheduler_remaining_20261003/freshness_canonical_after.json`。

唯讀研究採集查核於 07:36:29 UTC exit 0：月營收 2026-08 有 1,978 列與 6 個 artifact，Quick parent identity 與 child artifact hashes 已核對，但 child 未自行記錄 parent SHA；季度資料有 26 個 request receipts、3,960 raw rows、3,952 preview rows，狀態 `captured_with_review`，weekly parent binding 未記錄。這些 evidence 不會改寫 canonical formal/current-observed freshness：正式月營收仍為 actual 2026-06／expected 2026-08 `stale`，正式季報仍為 actual 2024-Q1／expected 2026-Q2 `stale`，current-observed 月／季仍是 `partial`。保留既有六項 institutional reconciliation conflicts 與歷史失敗記錄，不以新觀測覆蓋舊列或結案。稽核結果 `output/qa/integration_20261002/root_acquisition_audit_20261003T0736Z.json`（SHA-256 `334973a5f7edaef24615f716e49470740b09504962143e020f95d448b2f8cbeb`）。

Morning heartbeat 新增的唯讀 research-acquisition 查核段落來自已授權 chat「修復排程更新問題」；保留目前 prompt SHA `4a5316a58a755553d567a173fa1ff7e1aa671bf08faf59aa6a7e39f089511a49` 與 TOML SHA `09f88352cf94f120b5c533d4729c8383aa52ce7dff239580f64e076f9960b4fe`，沒有還原舊 prompt。查核程式 `scripts/audit_scheduled_research_acquisition.py` 不發 HTTP、不啟動 producer、不寫 DB；其選用的 `--output` 會寫本機 JSON，執行時應指定新的 QA 路徑，避免覆寫既有證據。07:31:29 UTC automation readback 驗證 21 個 task configuration／wrapper bytes；五個 `LastTaskResult` 非零（Evidence pipeline=2、Forward outcomes=2、calibration learning=1、Bank calibration=2、Paper EOD replay=2），故設定與 wrapper 驗證不代表 21 次執行全部成功。readback SHA `7a3ee194edd40d6dea9a914e7634f8d4eb0ae74f20f3f090f6c3c3e6d0b3d05f`。

Native Windows 可見旅程仍待接受；最新跨頁整合檢查為 50 passed／1 failed，root 正查同一 selection list 被重複冷讀造成的 14.594 秒延遲。whole goal 尚未完成；本段僅更新當前狀態，不改寫下方歷史收據。

## 歷史：本文件建立時的階段描述（2026-10-02）

> 本紀錄初版建立時，第一階段修補只完成部分對應驗證，工作正進入第二階段 ML 審查；直接 ML 依賴、外部來源及自然窗口限制仍分開保留。此段是建立文件時的描述，不是目前狀態。

## 驗收基準與保護

- HEAD：`e1c43716e39dcf535b203680f2af376c85e820aa`，branch `dev`。接手時 15 tracked／7 untracked Gemini 變更保留；原始 bytes、Git diff、狀態與 hashes 位於 `output/qa/integration_20261002/before/`。未 stage、commit、push、merge 或部署。
- 模型由實際 session `turn_context` 核對：root `gpt-6.1-sol/ultra`，兩位第一階段審查者 `gpt-6.1-sol/high`，實作 worker `gpt-6-luna/max`。證據為 `model_verification.json`；最多 root 加三位 active workers，沒有巢狀生成。
- Windows code root 為 repo；市場資料根為 `D:/Min/Python/Project/FA_Data`；Phase3C candidate、Legacy shadow、Bank shadow、repo Paper 與 Formal publication 分別保留原邊界。1418 是機器初始化的研究 seed，不是使用者真實持倉。
- 每項修補先保存 before 與回滾範圍；不刪原始資料、舊 receipt、鎖或 dirty changes，不以假時鐘追認錯過的決策。

## 第一階段已確認與已套用

1. 原生 COM 的受控唯讀查詢確認 21 個 root tasks 均存在。sandbox 查詢錯誤不能推定 task 不存在；wrapper exit 與 Scheduler LastTaskResult 分開。原 XML／狀態在 `scheduler_review/tasks_inventory.json`，受控重跑前重新盤點在 `before_controlled_runs/inventory.json`。
2. `baldr-scheduled-evidence-morning-report`、`paper` 兩個 heartbeat 的 prompt 已透過 automation 工具原地套用，TOML 精確讀回相同；名稱、thread、trigger、ACTIVE 與通知偏好保留。完整 prompt 和 before／after 在 QA 根目錄，readback 見 `automation_readback.json`。新增 canonical identity／hash、日期頻率、分層狀態與有意義變化通知判讀；例行職責維持有限監測，沒有擴成每天任意重訓或重構。
3. Evidence legacy recommendation importer 在具名欄位將 exact `date`／`datetime` 投影 ISO，既有字串 bytes 與 hash 相容，未知型別仍拒絕。未改共用 canonical serializer。worker 專項 24 passed；root importer／capture／scheduled wrapper 路由 61 passed、1 skipped（Windows symlink setup 不允許）。詳見 [日期序列化 QA](EVIDENCE_DRY_RUN_DATE_SERIALIZATION_QA_20261002.md)。
4. `baldr-paper-portfolio-daily`／`baldr-ml-allocation-forward-daily` 於真實 `2026-10-02T22:54:50Z` 暫停，於 `23:39:49Z` 完成 exact existing task 設定核對後恢復 Enabled=true／Ready。21 項 Exec WorkingDirectory 現均明確指向 repo；其中兩項盤前 trigger 改為台北 08:25（UTC 00:25），其他 19 項 trigger、全數 principal、timeout、retry、battery 與並行設定保留。Paper 實際 timeout 為 PT72H、ML 為 PT2H，沒有猜測縮短。原生 COM 將 `2026-10-03T08:25+08:00` 正規化為 `2026-10-02T17:25-07:00`；核對 aware UTC instant、每日 interval、zero delay 與 protected native definition，不能要求字串格式相同。兩個預檢停止／部分套用紀錄保留，最終 21 項核對與兩項恢復證據在 `scheduler_apply/attempt_2/completed/`，UTF-16 BOM before XML 可回復。
5. Evidence task 已於真實 `2026-10-02T22:56:39Z` 手動觸發，instance `{7F3A9ABB-4DDD-4225-973A-9AA42EE0D130}`，原生 State=4。它不是自然定時觸發；22:58:32Z 產生新 report／summary，pipeline exit 0，canonical consumer ID／hash 一致；原生 Task terminal Ready、LastResult=2。Exit child 使用台北 10/3，但 wrapper 分析日期為 Pacific 10/2，造成 as_of_date mismatch，尚待修共同分析日期契約。Evidence events／outcomes 全表 signatures 與筆數不變，但來源 DB 增加 4 KiB、mtime 改變：DecisionDeskSnapshotRepository 在 dry-run read 路徑未指定 read_only，重新寫入 schema_version（22:57:38Z）。此非原始行情改寫，但仍是需修復的 dry-run mutation；不可宣稱來源 DB 完全不變。13 項可回復衍生產物已備份，詳細證據在 evidence_controlled/。
6. Phase3C／freshness 核心修補通過 worker 111 passed／1 skipped；root 沿 fetcher／ingestion 擴及回歸為 132 passed／1 skipped。23:15:15Z 單日 candidate 受控更新使用 verified offline calendar；法人既有資料安全跳過，TDCC CSV 三次逾時、TPEX credit 三次 HTTP／timeout，summary 為 0 成功、1 跳過、2 待重試，未偽稱完成。原始 report 與 root receipt 在 `data_controlled/`；正式 DB 完整 SHA-256 前後均為 `d0c843fdef4c36d94ab2a031f3dcd898f3629f207bbfa93ddef8f51e157792a2`，4 KiB 既有 dry-run mutation 另依第 5 項保留。
7. 23:23:45Z 手動觸發原 freshness Task，instance `{31851D0C-E244-436D-BA83-393792E09AEC}`，原生 terminal Ready／LastResult=0。實際 status 是 `degraded`、errors=[]，季度 expected 改正為 `2026-Q2`，正式資料仍為 `2024-Q1`；candidate credit 10/1 與 TDCC 8/7 仍如實 stale。`ScheduledEvidenceStatusService.load_latest()` 真實 consumer 讀回同一 status hash `135f45d27de8a2152f97d14d05e56f67dc6ca7e028cd2d8664a00d62c8d61a29`、最新行情日 10/2 及同一 canonical recommendation ID。證據在 `freshness_controlled/`；觀測可讀不代表所有來源 current。
8. Capture 的 bounded raw-before-parse、failure attempt custody 與 cleanup status 已修，精確 MIS 成功碼新增已觀測字串 `0000`，其他型別／非成功碼仍拒絕，既有 v1 receipt/hash 兼容保留。High 再實證「第一次清理失敗、第二次擷取成功」被 exit 0 掩蓋，已修為保留有效 durable capture，另彙總 cleanup blockers、status=blocked／exit 2。root 最終 source-chain／PIT route 回歸 55 passed、2 skipped（Windows symlink 權限）；第一次以 repo basetemp 執行因既有 OS TEMP 邊界被拒絕，改用唯一 OS TEMP 後通過，沒有改防護。真實 MIS body 位於 `source_responses_20261002T231812713663Z/`，來源日期 10/2／盤後 quote、取得於台北 10/3 07:18，只供 schema 診斷，不能當新 regular-session durable capture。
9. 修補 readonly 與 Exit 雙日期後，原 Evidence task 第二次於 `23:34:45Z` 手動觸發，instance `{BBEABFEB-FF3C-45D6-88CD-04E9BF1CB259}`，最終 Ready／LastResult=2。新 report、summary 與 strict Exit consumer 均可讀回；分析日為 Pacific 10/2，current outcome sidecar 為 Taipei 10/3，receipt hash `sha256:396b7b63ee52cfa9de277bcdf7c6ac3c527c3c33755dfeed0b509b563e3c532c`／identity verified。正式 source DB 完整 bytes hash、大小、mtime 前後不變；canonical recommendation ID／payload hash 與 UI status consumer 一致。整體仍 failed，因 `portfolio_alert_not_ready`／`risk_prompt_not_ready`，不是日期／serializer 或 DB mutation 再失敗；真實完整證據在 `evidence_controlled/second/`。
10. Forward producer／readers／UI 修補後 root 36 passed；真實唯讀 consumer 將 1538 的既有 READY mismatch row 排除於績效，pending=1、sample_size=0、報酬／benchmark／MAE／MFE 均不聚合，保留兩項明確 blocker。沒有改寫歷史 row，readback 在 `evidence_controlled/second/forward_actual_consumer.json`。

## 歷史檢查點：審查判讀修正與當時待修復項目

### 第一階段最新實跑補充（23:57 UTC）

- TDCC 第二次受控執行於 `23:47:01Z` 開始、`23:47:26Z` 結束，API exit 0／1 成功／0 待重試。此次真正恢復的是既有官方 CSV route，payload 實際資料日為 10/2，寫入 candidate 4,078 筆；不能把先前 OpenAPI 9/24 的離線 raw 驗證描述為本次 live fallback。來源版本仍為 `tdcc-official-od-1-5`，前導零保留，publication_at／available_date 留空，first_observed_at／available_at 取真正取得完成的 `23:47:24.764883Z`。舊 8/7 資料保留。備份、before／after、checkpoint 與讀回在 `data_controlled/tdcc_second/`；正式 DB hash、大小與 mtime 均不變。
- 第二次 freshness task 於 `23:52:12Z` 手動啟動，instance `{8777992B-BCFD-4C29-81FC-60EFB106CE3E}`，實際 terminal Ready／LastResult=0。新 producer 及真實 status consumer 同讀 TDCC 10/2／4,078 筆／current、法人 10/2 current、credit 10/1 stale。季度 expected=2026-Q2、正式資料 2024-Q1，current-observed 季度與月營收仍 partial；整體 `degraded`／errors=[] 保留。formal source 完整 bytes／大小／mtime 仍不變。證據在 `freshness_controlled/second/readback.json`；consumer 的 load_state=current 只表示最新觀測可讀。
- 第 4 項早期部署作業曾把空 WorkingDirectory 經 `Path('')` 解為 repo，漏了最後三項；最後 readonly query 發現後，root 已承認並修正操作腳本。三項 before／after／protected fields 核對在 `scheduler_apply/remaining_workdirs_3/`，不能把較早部分套用 journal 單獨當全部完成證據。最終 `23:56:36Z` 原生 readonly query 為 21 available、0 unknown、全部 actions／schedules／working directories 相符、configuration_ready=true，檔案為 `scheduler_apply/actual_verified_21_tasks.json`。
- Paper production registration helper 本次實際原地呼叫 exit 0，`registered_and_readback_verified`，before／after XML 完整 hash 相同、PT72H、Enabled=true 與 principal／battery／retry 保留。aware COM/XML 均為 `17:25-07:00`，與 Taipei 10/3 08:25／UTC 00:25 相同。讀回在 `scheduler_apply/product_helper_actual_readback.json`。stderr 的 COM wrapper 釋放警告另有限修復中，不將此讀回當 producer run 或歷史取消根因證據。
- registered fallback 有限獨立審查發現並修復 TDCC 17 級完整性、Paper malformed weekly metadata 放行與 TPEx 短列省略市場三個 bug。修後獨立測試 119 passed／1 skipped，六檔 pins、真保存 raw 記憶體 producer 與五負例結果在 `phase3c_fallback_review/final_readback.json`；新 live TDCC 的實跑證據另依上項，不混用。TPEx live HTTP 520 仍是外部失敗。
- 必需 Update Workbench 85 passed、Update Tab QA 25 passed／0 failed／4 skipped。global mypy 暫有兩項：Gemini `portfolio_ml_raw_to_ooc_pipeline.py` 缺 `Literal` 屬第二階段；本輪共享 capture helper 由三項改為五項後 quote 呼叫端未同步，屬第一階段新整合 regression，已交 Luna 修復並保留原 HTTP／partial／型別／大小防護，不能只改解包。
- quote 相容修復後 root 使用唯一 OS TEMP 執行 quote／Paper source chain／PIT denominator 路由為 47 passed／1 skipped。正常 `0000/OK`、HTTPError、partial read、超限、非 bytes、錯 media／final URL 與 Paper failure raw custody 均有新回歸；未知來源不放行。報告與 before 在 `quote_capture_contract_fix/`。首次命令引用不存在的 test 檔而 exit 4、0 tests，保留原 log；修正為現有路由後的 final log 才是通過證據。
- COM cleanup 修後第二次 production helper 真實呼叫 exit 0／registered_and_readback_verified，stderr=0 bytes，設定 before／after XML hash 仍相同、PT72H／Enabled=true。證據為 `scheduler_apply/product_helper_cleanup_actual_readback.json` 及獨立 stderr 檔。這修掉 helper 釋放 apartment 時的警告，不外推歷史 Task 中止原因。
- Recommendation 狀態分類完成，root 真實 canonical consumer 讀回同 ID／payload／cohort hash：200 requested、15 可用、185 策略排除、其餘 0；原 quality missing=0／degraded=185 另列。原始 166 流動性排除、19 無訊號沒有被改為來源缺資料或勝率。root 全部受影響 service／UI suites 36 passed，worker mandatory Workbench 85 passed、Update Tab 25 passed／4 skipped／0 failed；global mypy 收尾只剩 Gemini OOC `Literal`，quote regression 已消除。before、有限修復與實際讀回在 `recommendation_status_classification/`，Manual 已同步。

- 10/2 allocation copilot 的 `skipped_non_trading_day` 是下一日 `2026-10-03T08:30+08:00` 的星期六決策。當日 10/2 自然 shadow maturity 另有 open observation，沒有證據支持「10/2 被誤判休市」。
- Forward outcomes 的 calendar observation 可核對為 open；一筆 1538 的 5-session outcome 使用 legacy 有效價格 row offset，因中間 null 收盤價落到 10/2，官方 5-session 計畫為 9/17。`blocked_mismatch` 防護保留，沒有補造缺價或改歷史事件。精確 event／outcome／calendar 在 `forward_calendar_mismatches.json`、`forward_calendar_diagnosis.json`；不能描述為全市場日曆未知，也不能把此 ready row 當已通過官方時間契約。
- Paper EOD 10/2 上游逐列來源 gate 已 ready；目前 blocker 是 archive persisted 晚於 consumer decision 及缺有效 capture manifest。不能把舊日期推薦或盤後 archive 回填成當日成功。
- Capture parse 失敗前未保存 raw、failure cleanup 描述不符實際與 retry cleanup 彙總缺漏已修；拒絕回應不得被當有效 durable capture。新合法 regular-session 實際 capture 尚無可用當日窗口，盤後診斷不替代自然證據。
- Phase3C 日曆未知誤列休市、日曆快取未共用、季度 expected 過早與 TDCC 週頻判讀／更新接線已修；受控資料更新與下游讀回依上方兩次實跑分別判讀，TPEx 外部失敗仍保留。
- PIT 新的 10/3 台北自然盤前觸發為 skipped_non_trading_day、Scheduler result=0；星期六合法 no-work，並未擷取新交易日 archive，不能當 denominator 來源已驗收。
- PIT 原失敗為官方 CSV hostname DNS 失敗。22:58Z 有界唯讀診斷已重新取得政府 metadata，原登錄來源未變且 hostname 當時可解析；不能臆測來源已退休。23:03:23Z 以既有 producer 在唯一 QA 目錄完成真實 denominator capture，consumer 驗證 1,987 symbols、檔案 hash `sha256:2fc129ac24ea0e372fbccadbf9a1c40b54890070225e8c953d9dce9bc27ae6c1` 與內容 hash `sha256:18ebe1cc813d8005bd827125e4809e96a782b8573ea7fc75ba1a4a6911ba8475`；raw、license 與 readback 位於 `pit_source_diagnostic/live_20261002T230300Z/`、`pit_source_diagnostic/live_readback.json`。這是當下台北 10/3 的有界來源診斷，不能回填 10/2 archive，也不是新交易日自然盤前 qualification。
- Legacy／Bank 的 prospective feature caller 仍觸發 `DailyPriceSourceRevisionError`，屬第二階段明確依賴；Gemini 年度 shards／adapter 收據不能證明該 consumer 已接通。
- 正式 ML 全量容量門檻仍不滿足；不降低門檻、不切正式 pointer。第二階段以具契約的小範圍隔離研究驗收工程。
- Scheduler Operational logging 啟用遭 Windows ACL Access denied；目前沒有提升帳戶／系統權限。0xC000013A 中止與 Codex app 更新只有時間相關，沒有程序歸因證據。

## 第二階段獨立審查與受控準備（UTC 10/3）

- root 已完整讀兩份 Sol High 報告：`ml_review_a/REPORT.md`、`ml_review_b/REPORT.md`。兩次獨立原測試均 18 passed，但沒有 fit／save／load／infer；A fixture 沒有修訂 receipt，`source_revision_gate=null`，故不能證明真修訂來源通過。A 另驗正式預設 5 passed；B 的 10 個補充負例確證現有缺口，不能把其 failed 當修復完成。
- A 六問題群為 invalid custody 研究放行、安全 guard 被跳過、假 fold／label 穿測試期、Windows 正式根隔離不足、旗標續跑斷線／無條件 release launch、generic CSV 財報基礎誤認。B 八問題群為真數值未保存、hash/schema/count 未形成消費鏈、分母 scale 誤當 exponent、compact 日期零列／跨年關閉連線、成功收據過早／失敗殘件、路徑隔離、來源時鐘／修訂、child path／snapshot consistency。已分別交 Luna A／B 有限實作，尚未接受修後成果。
- root 另完整讀 A 的 `temporality_addendum.md`：七個 source pins 前後一致；有限 probe 確認缺 explicit availability 時仍回 event_at，使目前修訂值沿歷史 PIT typed row 進入。保留真實 late clock 後 PIT row 正確拒絕，故不能放寬原 guard。修復沿既有 `RestatedResearchFeature/Row/Sample` 研究型別：歷史 event／reference／label maturity／purge 分開驗，本次修訂／觀測可得時間須不晚於真實 fit cutoff；未知原公告日保持未知。這是 current-restated 年代順序 holdout，不授當年可訓、歷史 PIT OOS 或正式資格。A 負責 raw／assembly／numeric store，模型與 Legacy／Bank 由後續 C worker 接線；未接妥前不得先倒填時鐘跑真資料。
- `00:42:27Z` root 在一致副本的 query_only transaction 查得 2023–2025 正收盤日期：2317=716、2330=680、TAIEX=724。扣 60 日 warmup 與最長 60 日 horizon，以 minimum_train=125、test=63、purge=60、embargo=5 作保守日期容量預估，兩股票分別可容納 6／5 個完整 test window；這只證有限範圍日曆容量，真 builder 仍須驗 feature coverage、實際 label 成熟與完整 folds，不是訓練收據。證據為 `ml_validation/bounded_history_capacity_readback.json`；QA helper 的初次路徑與 URI 參數錯誤已修正後重跑 exit0，未開正式 DB writer。
- root 在 `00:22:24Z` 開始以原 DB 的單一 `BEGIN`／query_only read transaction 執行 SQLite backup，完成副本 `quick_check=ok`、四表筆數讀回與 generation／所有來源 bytes 前後核對。副本為 `output/ml_research/integration_20261002/source_snapshot_20261003T002224799623Z/twstock_consistent_snapshot.sqlite`，3,848,364,032 bytes，SHA `6dbc12a50c3ab84d5021e68c2e5458e3ec129137d8d76b77fafe9f795a8875b2`；daily／technical／market／industry 分別 5,341,049／5,341,024／3,111／212,500。原 DB 與 34 個修訂 namespace 檔案（包含原修復備份）before／after 相同；保留 200 GiB reserve。`snapshot_receipt.json` 只證一致 bytes，不授歷史 PIT／custody 資格，後續仍須驗原 DB-binding／修訂證據，不能因副本沒有 namespace 跳 gate。
- formal pointer／manifest 16 檔與 active V2 全 39 檔已保留 before hashes、大小與 mtime；位於 `ml_validation/formal_pointer_before.json`／`active_v2_all_files_before.json`。真研究 run 結束還須逐檔 after 核對，before 本身不證未變。
- `00:18:14Z` 暫停 `baldr-ml-raw-pit-refresh-daily` 的 Enabled，原設定備份與 Disabled 讀回在 `ml_validation/temporary_ml_pause_20261003T001814057918Z/`；其 trigger 是本機 05:05，並非台北 08:25。root 較早更新把 raw 與 forward 名稱混淆，已明確更正；forward 正式 V2 讀取流程維持啟用。raw 在修復驗證後須依原 Enabled=true 受控恢復，不將這次暫停當永久設定。
- `00:25:28Z` 原生 COM 已讀回 Paper 與 ML forward **自然**觸發（未手動 Run），兩者 LastRunTime=本機 17:25、State=4、各有 running instance；Paper 新 run_id=`80a6a8cc4877409d9f9c2c71436eedc1`、started_at=`00:25:01.505829Z`，正在等待真正 Taipei 08:30。舊 9/30 `latest_status` 仍保留，不能用它代表新 run 通過。自然 terminal、休市 no-work 與 producer／consumer 仍待本次查收；證據在 `ml_validation/paper_natural_20261003/`。
- 後續 `00:30:21Z` 原生 COM 核對兩 task 已 Ready／LastResult=0／無 running instance。Paper 於 `00:30:04.686752Z` terminal，新的 root status 為 `skipped_non_trading_day`、decision_date=10/3、官方日曆 `weekend_closed`，isolated scope schema 正確、snapshot_appended=false。ML run=`20261003T002502548134Z-5320044a3085`，`00:30:00.018898Z` terminal、exit0；config producer selection receipt 與 scheduler status receipt 的 actual payload 精確相同，都是 Taipei 10/3 08:30 休市 no-work、沒有 child training／credit。當日 ML 無 config時寫的是 `output/v4_ml_forward_scheduler/latest_status.json`，derived output 的較舊 9/30 status 不是本次結果。root 逐檔重算正式 16 檔加 active V2 39 檔 hash／大小／mtime 全相同，市場 DB 完整 hash 亦不變；收據、runtime、producer binding 與 readback 在 `ml_validation/paper_natural_20261003/terminal_verified/`。這次自然等待／休市流程已驗證，不替代新交易日 capture、fill、正式 credit 或投資效果。

## 歷史檢查點：早期未完成項目（UTC 10/3 01–02）

### 原始修訂 context 真實驗證補充（01:07 UTC）

root 以已釘選的一致副本、真實原 DB、完整 namespace inventory 與當下 aware cutoff 呼叫共用 `load_verified_current_restated_source_context`。這次沒有建置特徵或訓練；於 `01:07:53Z` 被 `historical_price_spike_20260921/pending.json` 拒絕，完整失敗證據保留於 `ml_validation/real_source_context_20261003T010731195407Z/failed_attempt.json`。原始 marker 的 status 實際為 `applied_receipt_written`，同目錄 final receipt 存在；既有 write guard 對這種完成 marker 有配對驗證契約，而 ML gate 目前僅憑 pending kind 一律拒絕。已交 High 核對最小安全配對規則，再由 A owner 修研究 opt-in 分支；不刪 marker、不改原始 sidecar、不吞掉來源錯誤，正式歷史 PIT 仍須保持阻擋。此真實失敗不能改列 source context ready。

`01:06:19Z` 另核對 16 個已知正式 pointer／manifest 與 active V2 全 39 檔的 SHA、大小、mtime，並用 no-follow inventory 偵測新增或遺失檔案，均與 before 相同；見 `ml_validation/protected_ml_after_20261003T010619248403Z.json`。範圍不是全專案所有正式模型 weights。B worker 的 20 項定向測試與八檔 compile 已通過，完整 mypy 還有 A/shared 依賴錯誤；root 尚未將此結果當真實下游訓練通過。

### B 生產入口的真實數值消費（01:15 UTC）

root 已全文讀 B 的有限 `REPORT.md`／`ROLLBACK.md`，再以生產 CLI、明確 source bytes pin、當下 aware freeze 與真正 `output/ml_research/` 邊界執行單日 projection 的 adapter → store → public immutable loader，沒有測試 fixture 注入或新資料擷取。`01:15:57.935204Z` 開始、`01:15:58.512196Z` 完成，exit0；1,962 observations、7,658 values 全部以獨立 Decimal 比對：來源的分母尺度 `value_int/scale` 與新格式的十進位 exponent `value_int/(10**scale)` 完全相同，來源時鐘未改。四個 B production 檔與八個來源檔的 hash／大小／mtime 前後相同。

讀回證據為 `ml_validation/real_b_cli_20261003T011557935204Z/readback.json`，真正產物位於 `output/ml_research/integration_20261002/daily_projection_b_20261003T011557935204Z/`；consumption receipt SHA 為 `e1f257499d11d54c593be55223008d61bf669dfcce95a9a4ac06eb2836564b6e`。保留 `verified_numeric_observations_ready`、`historical_pit_eligible=false`、`source_revision_qualification=unverified_requires_separate_strict_inspection`、`blocked_insufficient_context_or_mature_history`，沒有建立 fold 或訓練模型。父 manifest 與 `all_field_enriched/` 子 manifest 的 actual bytes hash 本來不同，adapter／consumer 綁的是明確子 manifest，不混用 canonical hash 與 bytes hash。

### 來源驗證與整合版本準備

High 以真實 bytes 核對 completed pending／final 配對，868 個唯一更新鍵及 17 欄 scope 有效，七個篡改負例皆拒絕；另確認 excluded validator 的 19 個實體 source dependencies 不在原 34 檔快照 inventory。A 已追加由既有 validator 同次讀取的角色、路徑及 bytes pins，不修改舊 snapshot receipt。root 在 `01:43:56.345464Z` 至 `01:44:40.305302Z` 以真原 DB、同一副本及 exact source code pins 通過 `verified_current_restated_source_context`；讀回 SHA 為 `563fcfc23aef4ff8fcea679c903310bf486f7cad03d216d37bde61e841423c2e`，保存在 `ml_validation/real_source_context_20261003T014356344464Z/readback.json`，root 已全文讀取。原 34 檔 inventory 與 27 個 dependency roles（包含 19 個外部來源檔）均已核對，原 DB hash 仍為 `d0c843fdef4c36d94ab2a031f3dcd898f3629f207bbfa93ddef8f51e157792a2`。快照觀測為 `00:23:25.887429Z`，完整 dependency 驗證完成為 `01:44:40.304301Z`；raw／derived 與 fit 尚未完成，須使用各自真正較晚的時鐘。共用 loader 的 `training_as_of` 相容參數只作來源選取截點，不能冒稱模型實際 fit cutoff；歷史 PIT／formal training 仍 false。

B owner 較早的 portable suite 為 22 passed；root 後續重跑時碰到 A 新 context 欄位尚未由 constructor 回傳的編輯中版本，結果 11 passed／11 failed，保留於 `ml_validation/b_portable_inflight_attempt_1.json`。`01:43:56Z` 使用共享穩定版再重跑也為 11 passed／11 failed，原因已變為 B fixture 未包含新增的 validated physical dependency inventory；11 檔 source／test pins 前後相同，完整結果保存在 `ml_validation/b_portable_stable_20261003T014356564281Z/`。B 原 owner 已同步 test-owned fixture，保留 production guard 與真正負例；root 再於 `01:48:08.607605Z` 至 `01:48:11.863966Z` 獨立重跑 22 passed，11 檔 source／test pins 前後相同。讀回在 `ml_validation/b_portable_final_20261003T014808605606Z/readback.json`，SHA 為 `5fe61cb0e56e2977c192b2a4b1cdf641c672da94bd305266d373ae457206c84d`；之前失敗紀錄仍保留。C 的研究 pure-fit 契約測試已能呼叫既有 estimator，仍屬 fixture 證據，真 Direct 資料的 fit／save／新程序 reload／infer 尚待取得。

後續 A 已完成 shared gate 與 research boundary 的型態修正；上述真來源收據綁的是當次 `752ed8…62d24` gate bytes，不外推到修後 `01afd4…bd5e`。年度 raw 真實建置仍須重新以現版 loader 驗證來源。root 另以正常 mypy 獨立確認 research boundary 一檔 0 errors。C 新增模型保存、新程序載入與推論的 synthetic 契約測試，尚未代表真實 Direct 產物已訓練。

root 已全文讀取第二階段 `ml_review_a/c_artifact_preflight/REPORT.md`、source pins 與 finite probes。captured 舊版確證三個阻斷：來源脈絡／時鐘／audit 晚於反序列化驗證；宣告 purge=60 卻只有 5 個實際日期間隔仍能進 fit；fit 的 dataset manifest hash 未保留供 save 比對。前兩項以 spy／first-fit sentinel 重現，沒有真正反序列化或訓練；第三項由實際介面與 audit 欄位確證。已交原 C owner 修正，並補 failed receipt、實際 fitted components／shape 及未來推論時鐘的負例。審查結束時 bridge 已在修改，報告不接受新的編輯中 bytes。既有 SafeShadow loader 採 compatibility 與同 bytes hash 契約，並非 restricted unpickler，不將其能力描述為任意 pickle class 的安全保證。

root 也已全文讀取 `ml_review_a/outcome_store_preflight/REPORT.md` 與有限 probes；這是新 outcome store 草稿的六組接線缺口，沒有對後續修補版宣稱失敗或通過。內容包含 hash／registry、raw 與 Direct 時鐘、十進位指數、同日 open 標籤與 close 特徵的因果錯位、benchmark masks 及實際 fold 驗證。A 正在依同一完整 global calendar 保留 t 日特徵、T+1 entry 與真實標籤成熟，C 消費須綁真正 outcome manifest bytes。

在 `02:06:06.510522Z` root 用本機 QA marker 建立真正 NTFS junction，再呼叫現版 path resolver；native reparse attributes=1040，研究輸出在寫入前被拒，marker 與 source SHA `507a0c7c8c060f53900b69f38b1d6adbccc35db353437977b60aa5aedac7742b` 前後不變。證據為 `native_junction_20261003T020606394120Z/readback.json`，SHA `986ba1b8ccdb66d715722b9cbeba95f9e5e7f1e8a228dd23b6ca8bdca5026189`。未擴權，未對真正式根目錄建立 alias，也未操作 UI。舊 symlink privilege skip 仍保留，不能以此 junction 家族正例改寫原 skipped。

### 真實年度 raw 第一次受控執行

A 交付 raw CLI／exporter／gate／excluded 四檔 stable pins、compile 及原 raw 路由 23 passed 後，root 於 `02:15:55.411163Z` 真正啟動原 CLI，PID=47932；來源為同一已釘選的一致副本，symbols=2317／2330，event years=2023–2026，history start=2022-10-01，temp／persistent 各 1 GiB，保留 200 GiB reserve。`decision_at`／`data_selection_as_of` 是當次真實來源選取時計，未當作模型 fit cutoff。

程序在來源驗證後於 `02:16:39.162382Z` exit 1：exporter 第 646 行呼叫未定義的 `_explicit_aware_datetime`。八個 code／input pins 的 SHA、大小、mtime 前後相同，快照仍為 `6dbc12…75b2`；沒有訓練或通過 raw 消費驗收。完整 argv、PID、stdout／stderr 在 `ml_validation/real_annual_raw_20261003T021553526282Z/`，readback SHA 為 `deeb5b30742ee06e79f7e5655430b0aeb6b011db3d88c9f77ae7054eea8a3722`。已交 A 最小修補 helper 並補真正 current-restated 正例；原失敗及輸出根保留，新 run 必須用唯一輸出，不能改列成功。

既有 20 因子 CORE 與新 raw 的 source 欄位 registry 不同。C 將沿既有純數值計算建立可證的 price／technical／market 因子與 exact versioned registry；缺 verified industry membership 的因子保留 missing／quality blocked，正式 20 因子預設不能被不完整向量放行。B 單日 OHLCV 必須先與同 symbol／date 的已驗來源以 Decimal 精確匹配，再綁歷史 prefix 的衍生研究向量；無法匹配仍 typed block。Legacy／Bank 所需 gross stock／benchmark returns 與 T+1 entry／exit 真價格由 A 補實際標籤契約，不以 benchmark excess 冒充，C 保留各自既有成本與流動性限制。

### B 與一致副本的獨立逐值比對（02:25 UTC）

root 以 B 公開 immutable loader 驗證原 consumption receipt／candidate／adapted canonical／registry pins，再於同一 query_only SQLite transaction 查詢一致副本的 2317／2330、10/2 七個原始價格與成交欄位。`02:25:30.141624Z` 至 `02:25:34.143755Z`，14 項 Decimal 比對全部相同；snapshot、consumption receipt 與 adapter 程式完整 SHA、大小、mtime 前後相同。讀回位於 `ml_validation/b_snapshot_match_20261003T022530141624Z/readback.json`，SHA `1c0d7ac2bd5637e2201062b30eea55379a95c379ea78c22a3df1fa8fd50c8cb3`，root 已全文讀取。這次只確認來源數值可以吻合，尚未建立 CORE19 向量或模型。

此 root QA helper 第一輪誤把 immutable MappingProxy 當成物件屬性，產生 AttributeError／exit1；已改為契約規定的 mapping key 讀取後重跑，原工具失敗輸出保留。這不是 B producer 缺陷，也沒有修改 B 產物或 production loader。年度 raw 修補後，root 另獨立執行 exporter／CLI 路由 24 passed（包括新的 current-restated 正例）；該正例使用 test-owned typed context，不替代真實 namespace 驗證或年度實跑。

### 真實年度 raw 第二次執行與完整內容讀回

A 修正缺失的 aware helper 與 snapshot hash prefix 比對後，root 使用新 unique 輸出與當下來源選取時鐘重新啟動原 CLI。PID=49536，`02:25:31.819772Z` 至 `02:27:10.195724Z` exit0／stderr0，八個 code／input pins 的 SHA、大小、mtime 前後相同。程序收據為 `ml_validation/real_annual_raw_20261003T022529877592Z/readback.json`，SHA `fc2071496bc3d1a04628679d0a444e624f20829a7c1a3b64dbc9a6214ecbd096`，root 已全文讀取。初次失敗保留，不改列成功。

實際 publication 是 `annual_current_restated_20261003T022524214943Z/runs/current-restated-9016331a3f43b2c486297638/`，只發布 `core_long_history`：52 個來源欄位、2023–2026 四個 shards，73,234 筆觀測、281,699 個數值。root 於 `02:29:44.003993Z` 至 `02:29:47.213075Z` 完整解壓讀完，獨立核對 publication／dataset canonical hash、所有 row hash、compressed／content SHA、筆數、int64／十進位 exponent、單位、strict boolean masks、未知原公告日及真實時鐘順序；六個 artifact pins 前後相同。內容收據為 `ml_validation/real_raw_semantics_20261003T022944003993Z/readback.json`，SHA `55d60e1a15a5e8ad2ef4fb3428b29791d5b3e8c1fe0216760a2547c24cc44767`，root 已全文讀取。publication actual bytes SHA `d1fd90bd677c9f400d4d1c45b966680d8264d233daeffe3aea41cb6dacb30999`、Core dataset actual bytes SHA `2765099cf7ebc95ea0c55fca14b4cb689502965ec23542c83cec598e979ad333`，不混同其 canonical hash。

快照觀測為 `00:23:25.887429Z`，本輪 dependency 驗證完成 `02:26:15.524396Z`，raw 完成 `02:27:10.145722Z`；衍生值皆位於其間，原公告可得日保持 null。73,234 筆包含 66,941 產業 context、905 大盤、3,592 價格／derived、1,796 技術觀測，不是 73,234 筆可訓股票 samples。39 個價缺件來源列在 regular／derived 各保存一次，形成 76 個 invalid quarantine 及兩個 missing contract row；Direct／CORE19 必須保持 gaps 與缺件處置，不能因其他價格字串可解析而繞過。stdout 尚列兩個未發布 dataset 路徑是 summary 瑕疵，真 manifest 未宣稱它們存在，已交 A 有限修補。raw 內容 ready 不代表 Direct、訓練、重新載入、推論或正式資格通過。

### 已發布 raw 的數值後驗與必要修補

root 已全文讀 Sol High 的 `ml_review_a/published_raw_numeric_review/REPORT.md`、有限 summary 與單位 reference pins。單一 readonly snapshot transaction 的 32 個代表 scalar 皆符合已聲明的 HALF_EVEN 精度；兩 manifests、四 gzip、四份 captured code、receipt／root content readback 前後 pins 相同。此輪沿用既有 snapshot SHA，僅核其 size／mtime，沒有獨立重 hash 3.8 GB DB 或 19 GB dependencies。完整 SQL／原字串／raw值與 contracts 在 readback，SHA `7c6f508e2372f7afcc8a31271b82b6840cffadbf167fa7b9fd3a1be3987eae18`；不外推全歷史數值已驗。

後驗確證兩個工程缺口，不能把較早 raw 內容核對視為全部來源語意通過：38 個 2330 source rows 的 152 個 OHLC scalar 保存正確，但 143 個合法千分位欄位被 `_field_status` 誤判 invalid；其餘一個 2317 來源 OHLC 真 null。另成交金額來源是 TWD 元值、raw 未乘 100，卻標記 `currency_minor`。root 已交 A 同一次有限修補：嚴格辨識合法千分位，拒絕 malformed／非有限／非正價，保留原文字與真 null；current-restated registry／value unit 改 TWD 而 int／exponent不變。需新 unique raw 實跑、完整讀回及 Direct／CORE19 使用新 pins；原產物保留為內容相符但來源單位／coverage 受限版本。

C 的新 CORE19 將明確執行元乘 100 一次形成 `turnover_amount_minor`，尚待實作與實跑。High 核對既有 historical provider 的 `_integer(row[3])` 沒有乘 100，因此此前 root／C 曾沿用「既有 provider 已換分」的假設已更正；舊 20 因子單位／模型相容性列入第三階段有限查漏，不在本輪默改正式模型或 pointer。

root 對修後 price availability、exporter 與原 CLI 三條測試路由獨立重跑 64 passed；生產 raw／price contract bytes 分別為 `7fbaf8e2ab1bb5f0dda5ba6a675c03aaadb6f14b0bcc764a833673f48fd5e21e`／`cac8a3b9d33f34b34fbf866ae7e15b4a5c9d97db0c9d4d6e10a3e84ba47c4d9b`。第一次使用過長的 root QA basetemp，造成兩個 fixture mkdir 的 Windows WinError206、62 passed／2 failed；改用唯一短路徑 `.t/rup0248` 後全通過，未改測試或來源防護，也未刪除第一輪失敗輸出。這是回歸證據，第三次真實 raw 建置與內容讀回仍須另驗。

### 真實年度 raw 第三次執行（單位／解析修後）

root 以同一一致副本、新 unique output 與實際來源選取時鐘再次啟動原 CLI，PID=5876，`02:46:21.360598Z` 至 `02:48:01.956173Z` exit0／stderr0。10 個 code／input pins 的完整 SHA、大小、mtime 前後相同；程序 readback 為 `ml_validation/real_annual_raw_20261003T024619500756Z/readback.json`，SHA `fd5b61a553384fc135efd04c7d8f344b3b6311757b4ac95e7ebc197a2fb29f32`，root 已全文讀取及核對 stdout／stderr。

新 publication 位於 `annual_current_restated_20261003T024252809641Z/runs/current-restated-1c2e9c5f0ea133fd47bfd823/`，publication／Core dataset actual bytes SHA 分別為 `507041d1a174f178e7a88d84fc2e01f12ebd618cb6e2bc78ae2e74c03e69a511`／`83408f8ea7c00b151bb15662deb96bf437d5b535e12bab68b0050e54ebf07c30`。root 在 `02:48:56.108482Z` 至 `02:48:59.404680Z` 完整讀完四個 shards，canonical／row／compressed／content hashes、73,234 rows／281,699 values、52 欄 registry、strict masks 及真實時鐘全部相符，六個 artifact pins 前後相同。新 availability contract 僅剩一個真 null 來源的兩次觀測，invalid quarantine=0；不將空價補零或刪除事件位置。readback SHA `9ec03476fc01c138eea58747caeabde3811a6d2de1844f31ca8e455f73091390`，檔案在 `ml_validation/real_raw_semantics_20261003T024856108482Z/readback.json`，root 已全文讀取。

本輪 dependency 驗證完成為 `02:47:05.658018Z`、raw 完成為 `02:48:01.900660Z`，原觀測仍為 `00:23:25.887429Z`；原公告日未知、historical PIT／formal eligibility false。High 在單一 readonly transaction 另驗 32/32 代表 scalar、38 個原逗號來源的 152 個 OHLC、真 null masks 與 TWD amount unit contract，全部相符；八個純 parser 正／負例符合預期，實際 pins 前後相同。root 已全文讀 `ml_review_a/published_raw_numeric_review/new_postfix_review/REPORT.md`、有限 summary，並獨立重算其 readback SHA `ca177dce681f61b2b2e56d13fbdd2bd4d943cffa22ee1bb3ddca1ee86a781371`。此後驗沿用已釘 snapshot SHA，只核 DB size／mtime，不重 hash DB 或 dependencies，不外推全歷史數值、Direct／模型或投資效果。舊版本的 unit／coverage 限制、首輪失敗與未發布 dataset 的 stdout summary 瑕疵保留追溯。

既有 canonical recommendation snapshot 的 15 個 eligible 不含 2317／2330，requested 200 亦不含兩者。C 接線明確區分推薦 cohort 與 verified source-row／inference samples；新研究 sidecar 可以沿原 Legacy／Bank 入口消費同一研究樣本／模型／context，但不能把研究股票塞入當日推薦、冒稱正式 calibration 已訓或推薦來源已解禁。Bank terminal barrier 必須驗同一研究 cohort 與 pins，原正式路徑維持其來源 gate。

### 原三檔回歸與研究 fold 計數缺口

root 已全文讀 High 的 `ml_review_a/gemini_full_three_tests_025318839619/REPORT.md`：完整原三檔 23 passed／exit0，守門子集 17 passed／1 skipped；27／33 個實際 code／test pins 前後一致，唯一 skip 是既有 Windows symlink privilege。High 真讀 synthetic Direct／OOC refs、rows.sqlite 與 480 日全域 calendar，五個 folds 的 refs 互斥、時序、label 成熟、purge≥60／embargo5 正確，但實際 train 日期分別為 5／75／145／215／285。第一個五日 fold 仍被算入「至少四 fold」，公開 `minimum-train-dates` 沒有說明是 purge 前計數；這是參數與合格計數缺口，五日 fold 不支持有意義模型評估。已交 A 只在研究 qualification 排除 purge 後不足 request.minimum 的 folds，再要求四個合格 folds，正式預設維持。

### 新 Direct 真實失敗與 runner 接手

A 交新 outcome module／CLI／兩測試檔 stable pins、focused 4 passed 與型態／compile 結果後，worker 自行啟動兩次嘗試：第一個指定 relative repository root 即遭 boundary 拒絕；第二個使用 absolute root 與新 publication，唯一輸出為 `outcome_current_restated_20261003T030000Z`，在真 source 讀取時以 `raw source feature is filed under the wrong table` typed block 終止，沒有成功 artifact。原 raw immutable bytes 未改，正修最小 registry／來源表映射，不能以合成四測試代替真資料通過。

root 已準備的 `ml_validation/direct_cli_invocation_20261003T025818042124Z.json` **未執行**，不能算第三個 producer run。worker 的 session=81938、shell 報 exit1；未取得可證的 child PID／精確起始時計／獨立 child return code，保留此證據缺項，不以同時段兩個 Python PID 猜測。root 後續 narrow native query 在程序終末後回空集合，沒有授新系統權限。接下來的真實重跑統一由 root pinned-process runner 記錄 PID、argv、起訖、child exit 與完整前後 pins；worker 保留失敗輸出及 before bytes，暫不自行重跑。

錯表根因已由 A 與 High 各自讀回真 2023 shard line2：`daily_prices` 的 `derived:daily_prices.ohlc` 列保存 `technical_indicators.ATR/ADX`，metadata 明列 `causal_wilder_prefix`、period14、OHLC prefix、忽略原 technical 值；這是 exporter 明確支援的派生欄位。A 已交狹窄例外及七類錯 metadata 負例，其他表映射維持 strict equality，root 已全文讀 A 的 `direct_outcome_store_REPORT_20261003.md`、rollback、before manifest 與失敗 JSON；修後真建置仍待下一版 pins。

root 另核讀共用 label spool：`benchmark_excess_return_bp = stock_gross_return_bp - benchmark_gross_return_bp - buy25 - sell55`，共扣 80 基點。新 outcome store 的 gross stock／benchmark fields 必須與這個已扣成本 target 分開；A 正追加 typed `outcome_cost_contract` 與逐筆差額檢查，C model／audit／prediction 亦須明列 target 成本。Legacy 原 50 基點與 Bank fee／tax 將從 gross prices 另算，不能把模型已扣80的 target 當 gross 或再扣一遍。這次不改共用 assembler、已發布 raw 或既有 label 數字；先完備來源語意再執行真 Direct，避免無必要重建。

成本契約在 outcome module `74cb2eae96c96dbb588f88d144b72995627192b03e3197f2d5c5c099cb65a9ca` 已成 immutable typed ABI，builder／loader 逐筆驗 gross 差額減80，focused 6 passed；root 已全文讀更新後 A REPORT 與失敗 JSON。但 High 隨後實際讀取新 raw 的前兩列，重現 `daily_prices` 本體與 `derived:daily_prices.ohlc` 共享 table／entity／date 而遭 duplicate 拒絕，另確認 loader 的來源表相等檢查會錯過非空 ATR／ADX。有限31項探針全部符合預期，其中含阻斷重現，不能解讀為真 Direct 可建置。A 正把 source_id 納入來源 ref、manifest 與重驗 key，並限定價格標籤只讀本體，loader 沿用同一狹窄派生契約；修後仍須 root 唯一實跑。

root 新增 `ml_validation/verify_real_direct_outcome.py` 並全文讀取、編譯，只是下一次驗收準備。它將使用 public verified loader，再直接讀原 raw prices，獨立以 Decimal 重算每筆 gross／net80標籤、真 T+1／H 與全路徑 source hashes，並核實 purge 後125／test63／purge60／embargo5 的四個以上 folds。此時沒有執行該 consumer、沒有成功 Direct 或模型，不將準備完成當成功證據。

### 新 outcome Direct 真實建置與 public consumer 接受

上述準備後，root 全文讀 A 的最終 REPORT／rollback／source-id before manifest，獨立核對四檔 SHA；新 outcome module 固定為 `a1f1ec588ba776d75ad3d8d9ddf9f49548100d1e008ca9e96e7e340611165e3e`，focused 兩測試檔獨立6 passed／7.04s，未使用 pytest cache。before 目錄名 `033500Z` 只作識別，manifest 真 capture 為 `03:19:41.5758354Z`，不以目錄名冒充執行時鐘。

全新 invocation `ml_validation/direct_cli_invocation_20261003T032031415703Z.json`／SHA `e20beea871dbff8ffa95f3751b019908630828d314ab3c31562f8d82f8f94269` 已實跑。child PID=3616，真起訖 `03:20:55.506399Z`→`03:21:47.734506Z`，exit0／stderr0，20項 code／source／raw pins 前後完全相同。root 已全文讀 runner readback、stdout 與 stderr；readback SHA `07377599e64861f20139d3384492ae1558310122ebcdee477badcce626dcae30`，位於 `ml_validation/real_current_restated_direct_20261003T032053555891Z/readback.json`。

真 artifact 位於 `output/ml_research/integration_20261002/current_restated_direct_20261003T032031415703Z/runs/current-restated-outcome-196e0cff4d2cffaf22d4e083/`。Manifest actual bytes SHA `04b39a482cd9a40ebba0b06b1f3e63a17cf6cd04a2fc3c8221a2ce107f894471`、registry SHA `70ef3878d62a8495c6bcc476f2ec80a53aa942fe21a22e95604b41154a5f99f2`；1,796股票 observations、49來源 features、8 folds，不是原raw的73,234 observations或CORE19已訓模型。

root 隨即於 `03:22:21.829108Z`→`03:23:16.680702Z` 以 public verified loader 實讀完整 raw／六個 arrays／source context，另直接讀原 raw價格，獨立 Decimal 重算全部6,709筆 labels。T+1／H5／10／20／60、價格 integer／exponent、gross stock／benchmark、扣80的net excess與全路徑 source hashes 全部一致；905個 benchmark事件位置完整保留，缺價格未壓縮日期。實際8 folds train日期179／194／262／330／398／466／534／602，test各63、purge60、相鄰embargo5，train labels嚴格早於test。16個程式／manifest／raw／arrays pins前後相同。root 已全文讀及獨立重算 `ml_validation/real_direct_semantics_20261003T032221829108Z/readback.json` SHA `99b909c33df31cd2d71ef950f0439ed9186bc633b6f8ff4e135c18708cd5d56a`。這裡接受非PIT、無teacher的outcome numeric工程輸入；未訓練模型、未授正式資格或投資效果。

root 另準備並全文讀／編譯 `ml_validation/prepare_real_training_context.py`，將由真 strict source loader 取得typed context，再用C公用API create-only保存canonical envelope並公開重新讀回。此 helper尚未執行；正式context envelope、CORE19 fit／save／新PID reload／infer與Legacy／Bank仍待C所有共享程式凍結，避免保存模型後又修改其code pins而重複訓練。

High 對 `a1f1ec…` 新 Direct 的有限後驗共50項：source_id／數值與 masks、時鐘、T+1／成本、實際 arrays 與來源閉包、context及研究路徑均符合其限定範圍。root 已全文讀報告；最終 REPORT SHA `5933101230d73dd10cdb6941d20395ef79cc8d7861e704d4401d8334121e471d`，格式收據證明僅正規化換行、內容相同。High summary 明列自己的 producer／loader未執行，另明列 root 真實 producer 與 public-loader成功及對應收據；最終 summary SHA `5e24d47608c13defeae11d904ac3cef0574b448ea76bd1a92a31fca8b82a03ac`。metadata-only收據保留其前版，位於 `ml_review_a/new_direct_postfix_review/followup_a1f1ec588ba7/summary_scope_metadata_20261003T032945993659Z/`。此後驗與真實執行相互補足，仍不代表模型已訓練。

### 舊 Direct／OOC qualification修正後獨立回歸

A 已將研究lane的request.minimum與`post_purge_distinct_train_dates.v1`納入run identity／training／store manifest；Direct與OOC從實際rows計purge後distinct train日，至少四個合格fold，缺typed minimum即拒絕。Formal lane不啟用此研究篩選，assembler `fdd05a…`未變。Raw CLI摘要僅列已存在dataset manifest，沒有重建或改寫既有真raw產物。完整owner REPORT／ROLLBACK與三份before manifests在`ml_fix_a/legacy_fold_cli_summary_20261003T034249Z/`及其相鄰備份，root均已全文讀。Owner受影響suite54 passed；其中一個手改research overlay的fixture原缺新typed門檻，補fixture而保留production fail-closed，先前53P／1F不抹除。

Root受控獨立回歸PID18336，真起訖`03:45:53.293169Z`→`03:46:39.566261Z`，exit0／stderr0，完整原三檔加正式未opt-in守門、boundary、qualification與兩個CLI摘要case，共45 passed／1 skipped（該環境建立測試symlink的限制；先前原生NTFSjunction另已取得四項拒絕證據）。39 code／test pins的SHA、大小與mtime前後相同。Readback `ml_validation/a_postfix_full_regression_20261003T034553285171Z/readback.json` SHA `dc92e117537e145f638a73ee26ee6a8481f28f724167d5942216dbec297e929c`；root全文讀stdout／stderr／readback並重算SHA。新的Path A fixture為四個qualifiedfold；仍是隔離synthetic，不替代上述真新outcome Direct或模型證據。

High 隨後只讀 root 上述回歸留下的 fixture，沒有重跑 builder 或模型：Direct／OOC 的實際 train 日期均為75／145／215／285，test各65；原五日 fold 未產出 final refs。實際 purge 位置為60／60／60／61，符合至少60，相鄰候選 embargo5；838筆 rows、完整 refs 與 labels 成熟界線兩路一致。39 code pins、85 fixture 檔案的 bytes／大小／mtime前後一致。Root已全文讀 `ml_review_a/old_direct_ooc_postfix_review/REPORT.md`（SHA `167743d3a34b8adcaf3bdb923e5447df452cd3852f3a2eea90f03bd8b4bfb28d`）、readback（SHA `54b5d9601f6c2edb81448638bb9e5ce298e7264ee1b9ed4e21bcc7e566b13d37`）、source link與有限summary。這份後驗接受舊65／65工程fixture，不替代真125／63資料、模型或第三階段全面審查。QA使用immutable SQLite URI，現有production仍為mode=ro加query_only，不將QA旗標冒稱production保證。

### C凍結pure子集有限後驗

Root已全文讀`ml_review_a/c_frozen_subset_postcheck/subset_682e_20db/REPORT.md`、readback與九檔final pins。Pure fitter `682e7a…`／CORE19 projector `20db25…`的31有限檢查符合預期，readback SHA `8b8ca96932a7c09b21e5f8d6bcf8501c2f93f84ef006a31c206ff7066f54698c`；所有estimator／imputer／scaler皆由spy代替，真fit=0。Train-only preprocessing、default125／63、完整caller calendar的purge60／embargo5、整數targets與event t完成prefix／masks通過。Projector只保留已轉minor，TWD→minor adapter尚在bridge待驗；caller漏完整market日期仍能壓縮timeline，不能外推為真905日組裝通過。公共fitter可明確1／1工程smoke，保存資格必須另守實際125／63／四fold，不能只信audit.status。Root另準備`ml_validation/inspect_real_model_bytes.py`外部byte/hash檢查helper，已全文讀及編譯，尚未執行；目前仍無真模型保存或新PID推論證據。

待凍結範圍在 `output/qa/integration_20261002/version_scope_preparation.json`，包含 137 個明確 code／test／docs 路徑及來源、設定與保護證據；此清單不是版本驗收。`ml_validation/freeze_integration_version.py` 已編譯，尚未執行，之後須在 owner 穩定時保存 HEAD、相關 patch、tracked／untracked bytes 與證據 pins。root 的 `ml_validation/run_pinned_controlled_process.py` 已編譯，準備記錄真程序 PID、argv、起訖、exit code、stdout／stderr 及 reviewed input／code pins；它只證執行與 bytes，功能接受仍需實際 consumer 判讀。Windows Computer Use 已完成初始化和視窗辨識能力核對，未啟動專案視窗或執行 UI 旅程。

### C來源 lineage 相容阻斷（歷史，最終凍結版已修）

High 對編輯中 bridge 的 captured `cb22d752…` 確認三個正常 fresh revalidation 被誤拒的問題：新來源 context 的完整 dependency bundle 不等於舊 Direct、reload 混合 saved dependency rows 與 fresh verified clock，以及 fit binding 要求 fresh bundle 等於 saved bundle。27個真 raw／Direct dependencies 的 namespace／role／path／大小／mtime／SHA全部一致，唯一差異是各次驗證的 captured_at；gate canonical bundle明確包含此欄。原 dependency bundle、完整 context bundle與artifact bytes SHA為不同契約，不可混稱。

Root已全文讀 `ml_review_a/context_lineage_revalidation_review/REPORT.md`（SHA `2a946389f34581e9fd57d1d50c8507b43f850cb65adaefc3b16d5dba7ca3660b`）、readback（SHA `db493975adf43afa25b088027e1db9ecd6e43a9c1eebf9c117c8772986e74d6c`）及有限summary。五個exact AST記憶體檢查含兩個原lineage正例與三個正常fresh拒絕，未執行D physical loader或模型；owner途中改版，不能把此報告當final新碼通過。C正最小修正為保留immutable Direct原lineage／時鐘，fresh physical proof另存並完整核對六欄閉包，來源bytes／roles改變仍拒；修後須真context envelope、fit／save與新PID讀回。A另接手原三wrapper／新入口測試，before三檔已逐一核對備份SHA，兩owner分工無共寫。

### C最終凍結與原wrapper回歸（04:24 UTC）

上述 lineage、private-buffer SHA與兩代CORE19 full proof誤比對已在 bridge `8af4958cfd86cd645e7629f8e5c058e193a6155f29733b7f83465f14ebd86f47` 修復，fit CLI `ca765623…`與C測試 `fa034855…`凍結。Root全文讀 High `ml_review_a/c_final_subset_review/REPORT.md`（SHA `2301c8ac6f3032323a2683a768d44ef4e1924d83820d1b4036a09e37f49bf13f`）及17＋18項探針readbacks；NEW實際selection接OLD真Direct、相同size/mtime但不同bytes拒絕、兩代stable source/numeric/masks守門符合預期。這些是有限memory探針，沒有D實體重驗、fit或deserialize，不混同真實流程。

Root於`04:24:46.339341Z`→`04:24:54.139002Z`獨立執行C18＋original-wrapper入口8，共26 passed／6.30s，child PID37292、exit0／stderr0。23個code/test/helper的SHA、大小、mtime前後相同。Readback `ml_validation/c_wrapper_root_regression_20261003T042446334345Z/readback.json` SHA `1352c62b456bf0233abcf9f287fe58a9b178c296ca4845ed84fbfa9dcebcc861`已全文讀。

Wrapper owner另以新短路徑`.t/lb0413`完成原Bank／daily operational與新入口共107 passed／4 skipped，`04:15:06.5166151Z`→`04:16:19.2154408Z`、exit0。四skip皆Windows symlink建立缺權限（WinError1314）；先前Temp ACL及270字長路徑失敗保留，未放寬no-follow或lineage守門。原Legacy／pipeline／Bank目前凍結`2d86ae…`／`47de8e…`／`dac722…`。Root已開始唯一typed context實跑；模型fit/save、新PID推論及原wrapper真terminal仍待其對應證據。

### 真context完成與首次fit前拒絕（04:29 UTC）

Root來源描述child PID18172於`04:25:08.479835Z`→`04:26:37.317860Z`完成、exit0／stderr0、23 pins前後同。Typed envelope actual bytes SHA `b47815e0e60e96b9d1ee719f41c0e43fd7ad5724d09f6d3931ab5797c62ede68`已公開保存／重新載入；完整readback `ml_validation/real_context_envelope_20261003T042508536349Z/readback.json` SHA `a19f7fa7ecef7a8a7354bd29733ad3af5678b3ecee44f398b0b961145705413f`已全文讀取。原source觀測`00:23:25.887429Z`不變，真新selection`04:25:09.361190Z`、保存依賴核對`04:25:53.084379Z`與fresh proof`04:26:37.187834Z`各自記錄；34namespace與27 dependency角色仍完整。Envelope preparation cutoff不是模型fit時鐘。

首次fit入口`04:27:11.279147Z`→`04:29:21.526989Z` exit2，CLI明列training_started=false／training_performed=false，沒有建立模型目錄。Runner觀察的venv launcher PID17700與真Python PID35656，另以psutil於`04:28:26.735220Z`讀回直接parent/child／argv關係（`ml_validation/real_fit_process_tree_20261003T0428.json` SHA `3b310a53928f3b5d1029737129a03417939666999d30733c336ba95eeecadcce`）；不將launcher PID混同fit self PID。26個code/input pins前後同。失敗readback SHA `16900cdd18d53ce4285a1c88938a94a9fd7eab701c2e8b52de3a18387c7f6ca7`保留。

確證根因是raw registry使用`scale:int0`、`source_scale_denominator:int1`、TWD及既有unit_contract，而C guard錯讀只存在於observation的`decimal_exponent`。已交C修正此ABI；仍須嚴格TWD、整數scale/denominator與元乘100一次。既有raw／Direct／B產物不重建；此失敗尚未執行訓練，不以工程fixture通過冒稱真fit完成。

### Unit修補通過，實carrier接線仍待修（04:36 UTC）

成交金額registry修正已在bridge `5560773d98912c0ff249482ecdab5ed3a34995692bf6112cacee55d09e9afcf0`／test `2ec6a418…`凍結。Root新短根回歸於`04:33:10.031906Z`→`04:33:17.713373Z`完成27 passed／6.13s、exit0／stderr0、23 pins前後同；readback SHA `4d944712e1449402af6f7b71397ca5d111f432877e13b4e6946adde3e1387d85`。High真registry及4金額值的24有限檢查已全文讀，REPORT SHA `e33626370650473b4c046d4fa8bbe7fb39ac6b6e3a19e85fe549acd3ec6d619b`，不外推完整向量或模型通過。

第二次受控入口於`04:33:58.158637Z`→`04:36:07.258775Z`仍在fit前exit2：`missing Direct source value must not carry an integer`，training_started／performed皆false，沒有模型目錄。26 code/input pins前後相同，runner已原生讀回venv launcher51156→Python39352、同argv的真parent/child關係。Readback `ml_validation/real_core19_fit_unitfix_20261003T043358152636Z/readback.json` SHA `aa6b19f009eaf28013b580f41ee943106ec27641ca7483797b3240e46377dfc1`保留。

A的immutable Dense observation以strict integer 0加missing_mask=true表示缺值，C卻先強制integer再要求missing值為None，故形成不可滿足條件。修正須只接受verified carrier的canonical零，解碼成semantic None；masked非零、bool、None carrier仍拒絕，observed合法零與quality/staleness masks保留，不製造零價格或壓縮calendar。C與High正一次核對A全部mapped欄及B current-vector的實ABI；尚無真訓練／保存／新PID推論收據。

### 缺值載體修補與第三次受控前置驗證（04:47 UTC）

C已在bridge `185898e8d3d5ab532fd44be08b9d387203ca44e9abf69f5197606ba207421369`、test `ea7a75754086963609dcdca79fce9a25b71dd0ed83b3fd2b97d57ea23dca9117`修復上述矛盾。High有限後驗實讀1796×49陣列，7788個缺值carrier均為canonical零，11個mapped來源欄的Decimal／unit／exponent／mask相符；observed零與quality／stale旗標保留。23項carrier及9項B探針符合預期，B public loader實讀1962 rows與兩股票14筆來源值，C六來源共12個Decimal comparisons一致。Root已全文讀REPORT、summary及postfix／B readback；REPORT SHA `385cf6d912a8cdc2a0254840da35336b19af5807ad3464aea99054a46073b42d`。此有限核對未執行完整C prepare或模型。

Root於`04:47:23.463934Z`→`04:47:31.296183Z`完成C20＋original-wrapper8獨立回歸，共28 passed／6.25s、exit0／stderr0。23個code／test／helper pins前後相同；原生觀察venv launcher39244→Python33972。Readback `ml_validation/c_wrapper_root_carrier_regression_20261003T044723458936Z/readback.json` SHA `0cb9fb4530907c99aa6e2c82d24c0d8ba937b6cf1eea0bae2e0aabe922213eca`已全文讀。第三次受控入口沿用既有raw／Direct／B及b478 context、新的唯一model輸出，正在前置驗證；成功fit／save、新PIDreload／infer與Legacy／Bank仍須後續真實收據。

### 第三次入口在訓練契約前置檢查拒絕（04:50 UTC）

上述第三次實跑於`04:47:52.998948Z`→`04:50:41.541607Z`完成，exit2／26 code-input pins前後相同；原生程序樹為launcher5412→Python23016。CLI收據為`training_started=true`、`training_performed=false`、`verified_model_reused=false`，reason `ValueError: dataset_manifest_file_hash must be a sha256: digest`；沒有模型目錄。這次已呼叫訓練入口，不能與前兩次`training_started=false`混稱同一層失敗；root核對凍結版`AllocationTrainingService.fit_current_restated_outcome_only()`，`_require_sha256`是方法第一項檢查，在samples／folds與任何estimator.fit之前，因此沒有實際estimator訓練。Readback SHA `737e6b92550a0c01b82c279f19cf3fd4920987245fb4c8bb3e1a24b5e0dd3114`，stderr SHA `68bcff1ad455751226ae0e2f11a63fad3217be061d6de15c2f97309064dde830`。C／High已接手核對prepare→fitter→save／load完整hash ABI；保留typed SHA防護，不以修改guard換取passed。

Root模型bytes査收QA helper另發現hash後再讀另一buffer解析的缺口。High有限memory重現只執行captured `pin()`與兩個manifest assignment，沒有實際模型讀取、deserialize或fit；兩個JSON各34 bytes，cost_bp 80／79是內容數值。完整歷史REPORT SHA `d5d9ba8b7010c6b931595c9ad2b17c8d7e34ec5a6a446ba0cd83686b266e7f38`已全文讀。QA修補將以同一份bounded private bytes計SHA與parse，並要求外部expected manifest SHA；不變更production training code pins，也不把「bytesready」當成模型語義或推論驗收。

### Hash呼叫介面修補與29項獨立回歸（05:04 UTC）

C只將呼叫端Direct digest正規化後加`sha256:`傳入fitter；service `682e7ae…`、audit的裸canonical SHA與save／load guard不變。Bridge凍結`9dbbf84ef108d3e710eb455f17b9b43f13ff4af68f2940227938fa2acd7875b5`，C test凍結`fef2eeeaf94e57539162b2352b8943bc9700c8d4d9aebd364c254da7c9836950`。Before備份manifest SHA `bade814a7bf731096c8a75c6f16828a1c7c0fcc69d9bf0a8a9a9449e3187e7c6`已全文讀。High歷史格式報告及15探針readback已全文讀（REPORT SHA `d621de78dba0437441c55d3afb20b88fa1edee8b6e4984b83ff7afc27e4d042d`），不得當修後真模型接受。

Root於`05:03:58.597753Z`→`05:04:07.446244Z`完成C21＋original-wrapper8，共29 passed／7.09s，exit0／stderr0。23個code／test／helper pins前後同；原生launcher23968→Python31172。Readback `ml_validation/c_wrapper_root_hashabi_regression_20261003T050358548239Z/readback.json` SHA `1516975f466574bff79f05477613287d1fd1aabea9ed36dd6fd9d7d94a08d7f3`與stdout／stderr已全文讀。新增case以synthetic905日、四fold和estimator／save替身核對strict context→typed service→audit→save呼叫介面；不代表真Estimator fit或model保存。下一次真實流程仍須新的唯一輸出與actual consumer收據。

QA inspector `771a486359203addf9ac7cbca5d3f63005905bc00ad9b210df25dc325e54a7cc`已全文讀，root實際`--help` exit0；High12項private-buffer有限後驗與REPORT已全文讀（SHA `dcd507743bddb091894b18e09266d81cd321df35dec2075205d2ea43039e8f0c`）。外部manifest SHA為必填，保持bytesready、不反序列化之接受界線。

### PIT sidecar／capture 自然休市讀回（01:00 UTC）

既有 `baldr-formal-pit-sidecar-postcutoff-daily` 在 Pacific 10/2 18:00 自然觸發，sidecar／capture 分別於真實 `01:00:02.355766Z`／`01:00:03.476737Z` 產生台北 10/3 `weekend_closed`、`skipped_non_trading_day`。root 原生 COM 讀回 Enabled=true、Ready、LastTaskResult=0、無 running instance；COM 顯示的 `18:00:01+00:00` 仍保留為 native 文字，不能將其錯當 UTC。讀回、兩個原狀態 bytes 與 hash 保存在 `output/qa/integration_20261002/sidecar_natural_20261003T013915402171Z/`。這是自然休市流程證據，未取得新交易日 capture、formal publication 或訓練。

第一階段來源 fallback、Paper 窄 policy、21 項排程設定、quote 相容、COM cleanup 與 recommendation 狀態分類均已完成上述對應驗證。新定義不證明歷史取消根因已解。Legacy／Bank 與正式全量容量依賴交第二階段，不以未成熟自然證據卡住工程進度。第二階段 B 的有限數值鏈已驗，A／模型修復仍進行中；完成 B 的既有 Luna worker 已接續模型、Legacy／Bank 研究接線，不再受先前新增 worker 的工具名額錯誤阻擋。第三階段四面向產品審查、實作、真實 Windows 操作尚未開始。修後真實年度建置／訓練／保存／重新載入／推論及 Legacy／Bank 受控 readback 未完成前，不外推全鏈可用或產品完成。


### 真實 CORE19 訓練、保存與新程序推論（05:15 UTC）

第四次受控入口於 `05:06:05.370561Z`→`05:08:54.969399Z` exit 0，26 個輸入與程式 pins 前後相同。原生程序樹核對 runner31644→venv launcher50304→實際 Python30228，模型 manifest 的 fit PID/argv 相符。訓練使用 1,771 筆真樣本、19 個 CORE19 特徵、H5 benchmark excess after-standard-80bp target 與 8 個合格 folds；`training_performed=true`、`verified_model_reused=false`。前三次失敗收據仍保留，不併稱成功或重寫其結果。

真模型位於 `output/ml_research/integration_20261002/current_restated_core19_hashabi_20261003T050353125575Z/`：manifest SHA `7bb75f423db02de581c0e1894b4fd94752fe7f9b0920d7f3b8d6ff410d897854`、bundle SHA `ec3727e66997d299975950cb3ba81ce758799533ede441bd17fe311dc99dcbbd`、audit SHA `9238a8464d1280d5c78c6dab8e32842013c47dedd6c81c91b94ca460ac3690be`。實際 fit cutoff 為 `05:08:20.360783Z`、模型完成／可用時間 `05:08:54.740826Z`；沒有倒填 historical PIT。Root fit readback SHA `a2df2cd86beee9a3c704ce0088702cc831f1fa259a46e91cec6bc1153832ef9a`，byte inspector readback SHA `143f6005b551a7c2f16c71fcebbff3f8b8349ed5e08e73449468e7d40d598695`。後者只證明 bytes 與 JSON pins，不代替實際 load/infer。

High 有限 JSON 後驗 13/13 通過，完整 REPORT SHA `feff7b86bcf4ff389637ded252e30eed05e9d13aac03dd83dc947f904dc8dcb0` 已由 root 全文讀。905 個 calendar 日期與 immutable Direct 逐項相同，953 個 OOF row 歸屬已釘 test inventory、test IDs 互斥，8 折 train 成熟日期為179/194/262/330/398/466/534/602、各63 test，首折 actual purge74、其餘60，embargo5。14 code pins、runtime、target/cost、兩向量 typed masks、時鐘與 numeric SHA 相符。兩向量成交金額為765418113700／3950815929700分，元乘100一次；來源收盤轉分為25100／250000，收盤不是 CORE19 的獨立 feature。有限報告未逐筆重新計算全部 Prepared features，也未反序列化；不能將它外推成獨立全歷史重算。

Root 另外以原 trainer CLI 的 verify 分支在兩個新 Python 程序真實載入／推論：2317 PID19016（launcher45340）、2330 PID40592（launcher7236），均不同於 fit PID30228。`05:14:59Z`→`05:15:00Z` 兩次 exit0、stderr0，各32 pins前後一致，symbol/date/row/model hash/cost80/19 usable features吻合。Readbacks 分別 SHA `f5e7fafa5f22e56668e16e2e4eba129bbb564b57f9bbe0ecd32827d3d732cbd9`／`27ae90aa1e0cac8fb9a0f5fff4b8ea5a0bbe6a02b316912d9362bac848eb1436`。預測 -69／-53 bp 僅是研究輸出，非勝率、效益或交易指令。

四個實際 CLI 負例在 `05:15:32Z`→`05:15:34Z` 各 exit2、stdout空、32 pins不變：錯 manifest SHA、錯 bundle SHA、錯 vector SHA、要求在模型可用之前推論。各原始 stderr 明確指出對應 guard；generic runner 標記 process_failed 是負例的真結果，不改成 process_success。這些控制不證明正式模型 promotion、設定啟停或規則回退已驗，後續整合仍須另驗。

模型工程仍受 current-restated research 邊界限制：historical PIT、formal training/OOS、production action 皆 false，production alpha0，全 allocation teacher blocked。原 Legacy pipeline／Bank 實跑、正式資產保護讀回、暫停 task 恢復及第三階段仍待完成，不能宣稱整個產品已完成。


### 原 pipeline 成功與 Bank 不可變容器介面阻斷（05:20 UTC）

Root 全文讀既有 wrapper plan `bc5b6be…` 的精確 argv／pins後，於 `05:16:26.641824Z`→`05:18:42.174622Z` 真實執行原 pipeline（actual Python35932／launcher50360）；exit0、stderr0、34 pins前後相同。Readback SHA `9016e78b926ae85c12008f2c36838cf8de875986bb8574923e63c12333986932`，stdout SHA `4d92ef8f2748a0ce7aa1b45c532b5801268c3c06e73bbaac127dccfe869a7168`。原 Legacy child CLI exit0，20,231 bytes canonical terminal receipt SHA `cbb4df07930e13dad9f3b80fe2097549a7519a783c6e788bcde03a57802363dd`、binding `bfd65949490fce2cc14924f763b5c3d7fc27d1c367d4950e6ad91bd28eb48240`、source-row cohort SHA `971271781a0f6fd243696e86d2ad00372cbff57ad06981428abd82adaa783d2f`；root 全文讀完整 terminal。Legacy receipt自報child PID29556；generic observer只捕捉pipeline的launcher／Python，未捕捉孫程序，不把29556冒稱原生process-tree證據。

模型重用、無再訓練、兩 numeric vector hashes 與 cold輸出相同、source A/B/context/model bindings一致。D推薦 snapshot 的15檔僅為固定reference，與2317／2330無重疊，不製造推薦cohort。10/2當前H5未成熟，gross報酬與費用均None、status not_mature，固定50bp宣告不等同該日真實費用已計；需要另用已成熟歷史真樣本讀回費稅數學。

QA plan helper依此次真pipeline runner/stdout/receipt/body pins，於 `05:19:26Z` 實際產生 Bank plan SHA `8c05265a9f4b75a3e8d71eb1a1fa03551804bc9d26d99378f78e20a33653c1f6`，與原pipeline共用exactoutputroot/binding。Root隨後Bank實跑 `05:19:50.536005Z`→`05:19:51.756728Z` exit2，40 pins前後同，actual Python10024／launcher16408；readback SHA `846c49fa7f737e79ccc3b7735f8a6b2b45593233a982bbc43beea4d6b66ef5a0`，stdout明列 `Bank and Legacy source/model input bindings differ`。無訓練、無formal校準／order，沒有成功Bankterminal。

Root查明原typed Legacy verifier最後遞迴freeze清單成tuple；Bank對input_binding只做淺dict比較，與invocation的list不相等，雖canonical bytes／hash／values完全相同而誤擋。已交C narrowfix保留hash/schema/sourceguard，以canonical semantic bytes比較完整binding並補immutable回傳邊界正負例。修改bridge會改變model14 code pin；舊7bb模型必須原樣保留為該版已驗收研究產物，修後版本需新唯一輸出真fit/save/reload及Legacy/Bank驗證，不修改manifest或白名單讓舊模型繞過相容檢查。

`05:19:52Z` root另核對55個已保護formal pointer/manifest與active V2全部39檔 inventory，hash/bytes/mtime均原樣；不是對全部正式權重的完整盤點。raw task暫停尚未恢復，第三階段尚未開始。


### Bank binding 窄修與嚴格版本拒絕驗證（05:25 UTC）

C只修上述canonical比較，bridge凍結 `8d4a22041df3e18c726ebd78ee148ed4519cfce32645f04e078947a6dd2a4253`（257143 bytes）、test凍結 `60c2c76e78513f0f66bed12abd92ec29f1f274d96a2d70e4e2ed74b7f4227116`（90943 bytes）。Root已全文讀source diff、新參數化3case以及before manifest（SHA `95a4fd85e6e315b669ed16697f2a733bf14d7e334dba372c218415ca0a7f117e`）。High真cbb receipt verifier／guard前段正例及foreign symbols/model manifest/bundle/outcome四負例5/5，完整REPORT SHA `a3cf55b0c010d123b0e2ee06f446491b492b8a660f082d9e82c80c88c223808d`、readback SHA `7e388789c9e8ab944e023e0cf3cc9346cdf6c2bb23ca048a18ea990402d7457b`已全文讀；未執行來源／模型，不能代替完整Bank。

Root在 `05:24:26.283075Z`→`05:24:34.654508Z` 獨立C24＋original wrapper8，共32 passed／6.75s，exit0／stderr0／23 pins前後同（launcher41728→Python36788）；readback SHA `538f181a45d00a01386d0763695d543af1bdca5244dbc4ddbaa8d49ab4fc5f69`。另以原CLI在新bridge版本下真讀舊7bb immutable model：`05:24:52Z`→`05:24:53Z` exit2、stdout空、32 pins不變、reason `model training or loader source-code pins changed`（actualPython37592／launcher47812）。Readback SHA `ade3f6f9a1a867ad6376305a3b8242e05e2724e230ae09b2fe54aeea777e0deb`。這是版本相容守門的負例接受，不是模型載入成功。

修後新唯一fit plan SHA `a8f8a44d3354d395b0d997a83b6b9c18a22b761477be4f58ddfd74dfeec6a604` 正在實跑，仍重用原A/B/raw/context bytes；舊模型與成功／失敗收據皆原樣保留。完整修後版本仍須新fit/save/newPID/Legacy/Bank及保護讀回，再恢復暫停task，才轉第三階段。


### 修後真模型與原 Legacy／Bank 實際接續成功（05:39 UTC）

Root第二次真正fit於`05:25:16.614754Z`→`05:28:06.002076Z` exit0、stderr0、26pins前後同；native runner45200→launcher27156→實際Python22580，manifest的fit PID／argv相符，training_performed=true、verified_model_reused=false。模型manifest `56f73630a722395ead5990a048db6363037540c3332bd1517fe4c7531673aae3`、audit `4a209ef68abb1a48a4d0237ec988b3f8efcf989fa0810689706f0fe2386fc353`；模型bundle `ec3727e…`與前一真正fit相同，為固定演算法與相同輸入的結果，不是重用舊訓練程序。cutoff `05:27:31.531482Z`、completed/available `05:28:05.770520Z`。fit readback SHA `151701b1d99aefdaa0fb6cc05a49ececdac0c512927e2316c2786b2d7074c374`、inspector `f733ace68b20e607b74d21fae1d2f02eed2147e8e6b53b9bfb3657e83f44a8f0`均已完整讀回相應metadata與pins。

原verify CLI在真新Python45620／51116（launcher35552／38676）載入同一模型並推論；兩次05:29:28→05:29:30 exit0、stderr0、32pins各自前後同。readback SHA為`d2e5c217ec1921f350593ba144886042bb9a8b6eaff76e9bcba32237828597e9`／`f8138c48c51ef7d5b26924a74b0b16926acd5360ef37a77a51fb6f17703086ec`。Root另外對最終模型純JSON完成13/13語意檢查，905日曆exact Direct相等、8fold成熟train/test、953OOF歸屬、14current code pins、80bp target、registry19／宣告38維轉換、時鐘與兩向量尺度全部相符；readback `root_final_model_semantics_20261003T053609341159Z/readback.json` SHA `bfa5c7c348ba302abc235e28fa4fcc0dd489e5d35ad4c2fc7503bec16bffc0d5`。此後驗沒有重新fit、deserialize或獨立逐筆重算全Prepared；真正load/infer由上述原CLI完成。

Root使用原pipeline於`05:29:41.797035Z`→`05:32:47.840749Z` exit0／stderr0／34pins相同，native launcher42464→Python26188。Legacychild完成，完整20,193bytes terminal SHA `76273819e05b145017582851ba461a49a7d3ec81f69c181f5537a1bd2a8dd8ac`已全文讀；其self PID42992未被genericobserver捕捉孫程序，不冒稱native佐證。pipeline readback SHA `3c465f7bcf945b2781b43fddc1b490236b50f1ac0136dac87f8ebe8a0a366ee5`。Research分支在main早於日常producer返回，只唯讀驗reference及啟動Legacy研究child，並寫隔離C研究receipt；沒有重跑日常producer或snapshot。Manual原錯述已更正。

以此真Legacyterminal作upstream，原Bankwrapper於`05:34:59.387352Z`→`05:37:20.935349Z` exit0／stderr0／40pins同，native launcher31848→Python35480，terminal selfPID與觀察相符。Bank readback SHA `e37d326e9e63d95f89128d01d4186bc7a8df44151445a4c544f798b9538a6d64`、terminal SHA `a47c2507e0ca97cace7a307699a53c23604e273282092b66112950369a59d76f`均已全文讀。兩lane共用binding `dbce59aa…`、source-row cohort `97127178…`、模型56f與兩numeric vector `d1831f…`／`73e01d…`；預測-69／-53bp相同，trainingfalse／reusedtrue。Root獨立程式核對完整bindings、pins、真正時鐘／source／model／cohort及current-null，保存`root_final_wrapper_semantics_20261003T053900583385Z.json`，SHA `a9d3f7a596b7c1916eea5ce9d4ffa478ffce4cd8a12e4cc04c4497b4c6590f69`。

當前10/2 H5沒有成熟標籤，Legacy50bp與Bank估算policy雖已正確綁定，報酬及費用都仍為null，沒有把當前未成熟樣本當歷史成本驗證。四個已成熟歷史真樣本成本後驗及暫停rawtask恢復仍在收尾；第三階段尚未開始。源DB／WAL／snapshot／34namespace／27dependency嚴格再驗於05:37:16Z完成，readback SHA `ac71531e9fe2d5ce4f0070ae554e4dae661c89d02bfef17f246e07a8b8527146`。Namespace exact34與前次完整inventory相同、dependencies27只改實際重新讀取時計；DB仍d0c843…、WAL仍空、snapshot仍6dbc12…。05:38:17Z再次核對formal16／activeV2完整39共55pins與inventory不變；保留非全正式權重盤點範圍。沒有formal校準／credit、promotion、PIT追認、teacher或broker交易。

### 成熟 H5 成本與第二階段工程接受（05:47 UTC）

Root已全文讀完成本QA helper、REPORT及ROLLBACK後，以49個外部程式／資料pins執行原cost consumers；05:46:48.289374Z至05:46:49.769811Z exit0、stderr0、pins前後相同。Native runner49252→launcher51704→Python9900，實際成本readback SHA `72964ab8a2eb49d036b942d46fee1058c324b039f76fa559e4d718f57f47ad7a`，程序readback SHA `e0884f29e0ec90ee61b49d2d7a38c41715b16dbea6334b594c5a87d1e2d76550`。四筆真實成熟H5為2317／2330各自最早2023-01-03及最新2026-09-23事件；T+1進場／H5結束價格逐筆符合已釘C snapshot，沒有讀寫D。

| 股票／事件日 | 毛stock bp | Legacy扣50 bp後 | Bank研究費稅TWD／bp | Bank扣費後bp |
| --- | ---: | ---: | ---: | ---: |
| 2317／2023-01-03 | 143 | 93 | 395／40 | 103 |
| 2317／2026-09-23 | -79 | -129 | 1002／40 | -119 |
| 2330／2023-01-03 | 812 | 762 | 1923／43 | 769 |
| 2330／2026-09-23 | 81 | 31 | 9980／40 | 41 |

Root另用Decimal獨立重算佣金、最低佣金、費稅截尾及bp四捨五入，四筆均相符；成本由毛stock報酬扣除，未再扣Direct的標準80 bp訓練target。Bank採明示2026-01-01政策、1000股full lot普通股票作歷史價格研究估值，並非2023年的實際券商費率；成交／滑價未觀測。兩筆10/2 H5仍not_mature、十個標籤mask皆missing，毛報酬／成本／扣費結果皆null。

Root整合原真fit、新程序cold reload、Legacy／Bank、13項模型後驗、來源再驗及55資產保護，保存`output/qa/integration_20261002/ml_validation/root_phase2_acceptance_20261003T054754561806Z.json`，SHA `b2b08073f3225c41fac5015a7b1310767700a7080bb8e0d9899cc44fdb4f556d`。接受範圍為current-restated研究工程與raw task單項恢復資格；不是historical PIT、正式模型promotion、teacher或投資效果接受，也不是第三階段產品完成。

### Raw 排程恢復與第三階段交接（05:52 UTC）

恢復QA工具先在COM mutation前因備份XML省略Enabled=true而拒絕；Luna將比較限定為Settings/Enabled，其他XML內容仍需相等。Root全文讀修正及報告後完成9項純正負例，WorkingDirectory、argv、trigger、principal及parallel policy變動仍拒絕。Restricted sandbox的Scheduler查詢另回覆Access denied／root folder不可取得；未把此結果當成task不存在。以本次明確授權透過原生Windows執行同一受限helper後，05:52:16.046748Z實際恢復`\baldr-ml-raw-pit-refresh-daily`，Enabled=true、State3（Ready）、already_restored=false；before XML SHA `3d27acf3…`、after SHA `9cec756f…`與原pause前備份完全一致，所有其他task欄位未變。readback位於`output/qa/integration_20261002/ml_validation/temporary_ml_restore_20261003T055216034859Z/readback.json`（實際目錄以版本inventory為準）。COM回傳LastTaskResult0屬既有執行結果，並非本輪producer重跑證據；沒有手動觸發raw、改action或切換正式模型。

前兩階段可完成的工程修復及相關研究接續已接受。第三階段承接這些確切程式／資料／設定pins，分批由四位Sol High審查資料、ML、UI、文件；root須讀完四份報告才分派本版產品修正。四用途內容旅程、輸入變動及真實Windows操作尚待第三階段完成。
