# PROJECT_SNAPSHOT（目前狀態）

M95 將持倉管理的「情境壓力」拆為「目前情境／已保存歷史」子頁；歷史選列卡並列同筆原基準市值、壓力後市值與變動（TWD），明示情境、日期、覆蓋、狀態及研究用途，缺值不補零、切列／刷新／錯誤清舊，原表與 hash 保留。Portfolio 聚焦及 Stress 歷史 **76 passed**、Workbench **85 passed**、validator **25／0／4**、mypy **1,143**、編譯與正常 Main 1280×760／真 Windows DPI144 的兩態合成畫面通過；原生腳本前兩輪過早捲動失敗已保留收據。這是已保存研究結果的呈現改造，不是預測、績效或正式來源接受；詳[實作收尾](../06_qa/BALDR_OPUS_UX_IMPLEMENTATION_CLOSEOUT_20261023.md#m95-已保存-stress-歷史選列卡)。

M94 修正決策工作台首屏持倉警示與候選判讀的三句已知英文來源文字：首頁以繁中顯示「待覆盤／未套用動作／未產生買賣建議」，提示與原表格仍可核原文，未知來源文字原樣顯示。Workbench 聚焦 42、共用 85、更新頁 validator 25／0／4、mypy 1,143、編譯與真 Windows DPI144 的 1280×760 隔離合成畫面通過；初次候選翻譯順序失敗已保留原收據。這是呈現層修正，正式來源、固定 EXE、Owner UAT 與完整產品 Gate 未接受；詳[實作收尾](../06_qa/BALDR_OPUS_UX_IMPLEMENTATION_CLOSEOUT_20261023.md#m94-工作台首屏已知警示文案)。

M91 在已載入的題材目錄加入名稱片段搜尋：90 題材合成版本可跨鏈找同名列，須明選後才定位原鏈／題材，無匹配不改目前研究。M92 補真 Windows DPI144 的 Legacy 回撤、交易報酬與持有天數 canvas 證據；M93 根據原生畫面修回撤小幅百分比刻度重複顯 `0`／`-0`，顯示刻度現在帶 `%` 且真零不帶負號，原圖形數值與權益圖刻度路徑不變。M91–M93 整合聚焦 71、Workbench 85、validator 25／0／4、mypy 1,143 及原生畫面已通過；範圍見[實作收尾](../06_qa/BALDR_OPUS_UX_IMPLEMENTATION_CLOSEOUT_20261023.md)。正式來源、其他 DPI、固定 EXE、Owner UAT 與完整產品 Gate 仍未接受。

M89 在題材漲跌等面積格與成交金額面積圖中，僅對跨鏈同名題材顯示足以辨識的鏈名前綴；原數值、提示、來源身份與點擊定位不變。M90 用隔離合成回測來源補驗 WebEngine 權益曲線 canvas：正常 Main 1280×760、真 Windows DPI144（150%）的 A／B 兩份不同原值各有可見線條，切換後畫面顯示 B 的 run 身份。M89 聚焦 47、共同 Workbench 85、validator 25／0／4、mypy 1,143 及原生 1280／900 寬度檢查通過；M90 為 QA 專項，未改產品程式。範圍與收據見[實作收尾](../06_qa/BALDR_OPUS_UX_IMPLEMENTATION_CLOSEOUT_20261023.md)。這些仍不是正式來源、其他 DPI／圖種、固定 EXE 或 Owner UAT 的驗收。

**Opus→Antigravity UI/UX 審查鏈的後繼原始碼已完成 M1–M88 工程階段收尾。** Opus 起始審查，因額度用盡由 Antigravity 接手完成；Sol 依現行架構逐項複核與去重，Luna 分切片實作、root 審查。最近 M86 改善覆盤首屏表格可見三列，M87–M88 修正 Legacy 保存圖表切換與刷新時的來源身份；M88 後受改 Python 編譯、Workbench 85、validator 25／0／4、mypy 1,143 檔通過。範圍、各階段成果、收據與未完成 Gate 見[實作收尾](../06_qa/BALDR_OPUS_UX_IMPLEMENTATION_CLOSEOUT_20261023.md)及[本機逐輪 QA](../../output/tasks/baldr-opus-ux-implementation/QA_RESULTS.md)。這是原始碼與隔離合成 QA 交接；正式帳／市場來源、真 OS 125%／150% DPI 全路徑、固定 EXE、Owner UAT 與完整產品 Gate 尚未接受。

後續 M59–M61 修正決策品質無審查／來源不可用假零、批次回測不可用指標混入統計，以及 Portfolio 生命週期原始狀態碼首層難讀；原流程分數、回測公式與健康判定未改。聚焦 27／31／68 項、Workbench 85、validator 25／0／4、mypy 1,141、compile 與三個 1280×760／100% Windows 隔離合成畫面通過。這些畫面不是正式來源、真帳、125%／150% 真 OS DPI 或 Owner UAT。

M62–M66 再核批次循序／並行 adapter 的指標契約、正常 Main 決策品質導航、Regime 匹配分數 bp 標示及覆盤歷史來源／狀態；正常 Main 的 before 圖發現左側回測設定擠壓證據卡，M66 進入證據覆盤即收合，after 圖在 1280×760／100% 可見五張卡並可再展開設定。M67 另用 Windows 真 ProcessPool 的兩個子程序補合成版本化報告返回，缺值與真零維持原契約；未執行真策略或保存 run。M68 將個股頁首原漲跌值獨立標紅漲綠跌、日期保持中性，Windows 1280×760／100% 前後圖、74 個股聚焦、Workbench 85、validator 25／0／4、mypy 1,141 與 compile 通過；M69 另以隔離 Main 個股工作區注入合成報告，正／負／缺值三態全窗圖維持呈現。畫面與批次報告均為隔離合成來源；正式資料、OS 高 DPI、固定 EXE、Owner UAT 和完整 Gate 仍未接受。

M70 已用隔離 SQLite 經正常 Main 搜尋鈕與真個股 reader 驗明示漲跌、真零及無方向未知，並修 1280×760 首屏右上行情日截斷；75 個股聚焦與真 OS DPI96 四態全窗圖通過。M71 依所選日期與覆盤類型的 `review_id` 限定決策品質項目，卡片與表格不再混入其他覆盤；M72 讓明填 Portfolio ID 只用原保存 metadata 精確身份篩覆盤，缺身份舊紀錄不猜。最終 6 個 service 測試、兩張 1280×760 原生合成 View 與共同 Workbench 85、validator 25／0／4、mypy 1,141、compile 通過。合成價格沒有可得時間，正式價格／Evidence DB、真 OS 高 DPI、固定 EXE、Owner UAT 與完整 Gate 尚未接受。

M74 在首頁市場首屏新增原來源 `breadth_ratio_bp` 比例顯示，與上漲／下跌／平盤家數及資料日同列；真零、缺件、無效值不混淆，未重算市場廣度。22 個聚焦測試、1280×760／真 OS DPI96 隔離合成 Workbench 畫面、共同 Workbench 85、validator 25／0／4、mypy 1,141 與 compile 通過。M76 另用隔離合成 SQLite，於正常 Main 經真唯讀決策品質 reader 驗 M71–M72 的日期、類型與精確 Portfolio ID 篩選，來源 DB SHA 不變；這些證據仍不是正式 Evidence DB、真 OS 高 DPI、固定 EXE 或 Owner UAT。

M77 將決策品質既有項目／嚴重度／狀態碼顯中文並保留原碼提示與詳情；M78 於大盤技術細節按原檢測器語義標點／百分比，未知不冒充零，ADX／DI／RSI／規則分不誤標機率。各自聚焦 30／7、正常 Main 1280×760／真 OS DPI96 隔離合成畫面，以及共同 Workbench 85、validator 25／0／4、mypy 1,142、compile 通過；未改 DTO、計算、正式來源或資格。正式資料、真高 DPI、固定 EXE 與 Owner UAT 仍待獨立驗收。

M79 修決策品質最低分數的自由文字錯誤：非法輸入明示並清除舊結果，不呼叫 reader，遲到舊回應也不能重填；空白／0／10000 可恢復。36 個聚焦測試、正常 Main 真 OS DPI96 的非法／恢復全窗圖，以及共同 Workbench 85、validator 25／0／4、mypy 1,142、compile 通過；合成 SQLite SHA 不變。最低分數及股票篩選的範圍契約仍依 M73 保留，不以此驗證修改流程分數。

M80 讓大盤指數原 Regime 檢測走受管背景工作，載入中停用重入並清上次分類，完成／錯誤恢復；保留 service 原有 history 轉移與 CAS 衝突處理。18 項聚焦含原 state 並發測試、正常 Main 1280×760／真 OS DPI96 載入／完成／錯誤與關窗等待、隔離合成真 RegimeService history 寫入，以及共同 Workbench 85、validator 25／0／4、mypy 1,142、compile 通過。正式資料等待時間、真高 DPI、固定 EXE、Owner UAT 和產品 Gate 未驗。

M81–M82 修正參數最佳化與覆盤歷史的結果範圍語義：最佳化從同份單股報告的已簽指標契約辨識觀測零／不可用，錯誤報告、契約錯誤或目標不可用的組合不排名；無契約舊報告保留相容排序但數值與排名明示未驗證，表格排序後套用依畫面列排名核對身份，穩定性只計已驗目標樣本。覆盤歷史於原日期篩選後多讀一筆，標示顯示列數與卡片僅統計顯示列，不冒稱總筆數。92 項聚焦、正常 Main 1280×760／真 OS DPI96 四張合成畫面及共同 Workbench 85、validator 25／0／4、mypy 1,142、compile 通過；原績效公式、保存來源與正式資料未改，真高 DPI、固定 EXE、Owner UAT 及完整產品 Gate 待驗。

M83–M84 將覆盤歷史延伸為只讀游標分頁，111 筆隔離合成 SQLite 經正常 Main 可前進三頁並返回，卡片僅統計本頁，日期更改清舊結果；表格已知覆盤／排程碼顯中文且保留原碼。55 項聚焦、Workbench 85、validator 25／0／4、mypy 1,143 與編譯通過，1280×760／真 OS DPI96 全窗圖及查詢期間 DB SHA 不變已核。未提供精確總筆數；正式來源、真高 DPI、固定 EXE、Owner UAT 與完整產品 Gate 仍待驗。

M85 補 Legacy 回測保存歷史清單的 100 筆游標翻頁，及圖表來源每批 50 筆追加；同時顯示查閱範圍、保留已選圖表 run ID、缺保存時間明示。211 筆隔離合成 SQLite 經正常 Main 三頁與全部圖表來源可達，來源 DB SHA 不變；71 項聚焦、Workbench 85、validator 25／0／4、mypy 1,143 與編譯通過。這是 legacy 來源的讀取／導航修正，未改原保存件與金融公式；正式來源、真高 DPI、固定 EXE、Owner UAT 和完整產品 Gate 仍待驗。

M86 將覆盤歷史六卡在足夠寬度排為單列，窄頁仍維持三欄兩列；正常 Main 1280×760／真 OS DPI96 首屏從約一列增為完整三列表格，原限制提示、資料庫路徑、五列最小表高、翻頁與明選詳情仍可用。M87 修 Legacy 保存圖表來源切換時的舊圖殘留：每次清前一來源，缺資料的圖各自顯不可用，仍有資料的圖顯所選 run；原佔位提示在圖表初始化時立即隱藏。隔離合成 CSV 的 A 完整、B 缺交易、C 缺曲線與交易三態經正常 Main 驗證，資料 SHA 不變。M86／M87 分別 43／32 項聚焦通過，共同 Workbench 85、validator 25／0／4、mypy 1,143 與編譯通過；正式來源、真高 DPI、固定 EXE、Owner UAT 及完整產品 Gate 未接受。

M88 使 Legacy 圖表來源刷新後的選取與圖表身份一致：原選較舊 run 經 repository 確認仍在時加入暫留候選，逐批續載不重複；若不存在或不能核對，清除選取與舊圖。隔離 SQLite 211 筆經正常 Main 證較舊 run 刷新後保留、全頁載入不重複且來源 DB SHA 不變；14 項聚焦、共同 Workbench 85、validator 25／0／4、mypy 1,143 與編譯通過。正式來源、真高 DPI、固定 EXE、Owner UAT 與完整產品 Gate 仍待驗。

**Opus複審後的UI修正已完成具名工程回歸。** Luna分工實作、root審查：紅漲綠跌與狀態色分離、緊湊個股頁首、短五問及四面向摘要、缺月營收柱／財報配對柱、固定籌碼四面向與展開原值、首頁市場家數與逐股候選、選股漏斗／比較未知／深色回測及返回列。281項定向、Workbench85、validator25／0／4、mypy1138及編譯通過；正常Main125%／150%首次及新程序回訪通過，1280首圖頂端166邏輯px、四摘要入口完整可見。完整合成欄位與17路由已補圖，但市場／Paper／持倉仍有舊術語及長表問題，並非全平台美觀接受。正式資料、Daily Operations Recovery、DTO／金融規則及固定EXE保持；最終增量、原失敗、外部／真人未驗界線見[修正QA](../06_qa/BALDR_OPUS_UX_REMEDIATION_QA_20261022.md)。

**Track B 六包再複核（10/23 Taipei）：** Legacy 實際為7筆獨立託管、81筆缺證；Weekly 固定遷移原件驗證後仍5/6 partial；Forward 改為驗證capture context與事件hash後登記每事件政策，outcome角色分開核對。真reader重建9,423筆版本矩陣、8份HTML尺度證據，6443差異與幣別／歷史availability未解。37個既有導航連結採35個精確文件／目標登記，並非整庫豁免；詳見[六包獨立複核](../06_qa/BALDR_TRACK_B_SIX_PACKAGE_REVIEW_20261023.md)。Formal/Paper未選定與自然驗證界線保持。

**Track B 接任成果獨立複核：完成裁決不成立。** 已補強 Forward 外部接受／原件重播、Legacy custody、搬遷路徑與 Weekly 期別檢查；八份雙市場月營收 HTML 及四月 archive 已離線讀回，但 TWSE 6443 仍有兩欄差異、正式 Scoring/PIT 未通過。Formal/Paper 來源 Owner 尚未選定，自然排程未恢復完整鏈；不宣告 `DATA_PIPELINES_ENGINEERING_COMPLETE_AWAITING_MATURITY`。原 RC／Track A UI 保持，驗證與逐線剩餘工程見[Track B 獨立複核](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)。

**後繼個股研究原值圖卡。** 承接已完成 Track A 布局，基本面／營收、財報比較、法人、信用、集保級距與分點新增已載入 DTO 的原值圖卡；單點採值卡、同日同源同單位才比較，不推算成長或連買。82定向、Workbench85、validator25／0／4及mypy1135通過；125%／150%三尺寸研究View實圖已核。這是UI工程，不改P0、正式資料或金融資格，固定EXE未重建；來源缺件及驗證界線見[研究視覺整合](../06_qa/BALDR_RESEARCH_VISUALIZATION_20261022.md)。

**日常營運裁決 `DAILY_OPERATIONS_PARTIAL_RECOVERY`，固定 V2 RC 保持。** Quick 已唯讀核對遷移證據、原備份及868筆／14,756欄修訂值，並完成精確 custody binding 的正式根 metadata 讀回；舊收據與資料庫未改寫。Freshness／Evidence 終態收據、六軌唯讀分類及 BankTaiwan／校準原件定位已完成必要回歸（275項／4 skip、mypy11檔，最新Bank45項／1 skip及launcher2項另驗）；不以程式修復宣稱自然排程恢復。21項Task定義無差異、Direct停用、兩個既有heartbeat保持；新formal-input自然run已越過舊路徑錯誤，但因09/09配置對10/22過期而拒絕。來源資格、當日PIT、Forward成熟、Native停止及Owner未驗維持；實際QA與逐分支下一步見[日常營運恢復](../06_qa/BALDR_DAILY_OPERATIONS_RECOVERY_20261021.md)。

**後繼原始碼：圖卡優先研究介面。** 首頁並列風險／市場／候選／資料影響，題材高低端、覆蓋與最近研究靠近主圖卡，次要待辦及額外入口緊湊呈現；個股圖表與支持／反證同屏，報酬研究沿既有產品投影與欄位衝突拒絕。選股的原資料準備及完整條件可展開，原保存比較就近分列支持／反證／未知及原條件、日期、分母，策略參數、題材缺件與保存時間也已整理。只改 UI 展示，Daily Operations Recovery、金融計算與來源資格保持；固定 `06a4e1c15ed9` EXE 未含本增量。實際檢查及限制見[圖卡體驗 QA](../06_qa/BALDR_V2_CARD_EXPERIENCE_20261022.md)。

**Track A A1–A5 本輪 UX 工程已核對完成。** 個股主圖／支持反證、首頁資訊層級、原選股比較、題材雙端／成員、原策略報酬／回撤／成本與同原件返回均有實作及隔離Main驗證；最後補首頁原canonical候選經實際UI保存、Journal及新程序最近研究回訪。最新定向75、Workbench85、validator25／0／4與mypy1133檔通過；125%／150%實圖及逐項限制見[完成核對](../06_qa/BALDR_V2_CARD_EXPERIENCE_20261022.md#track-a-a1a5-完成核對)。不授正式金融資格，不代表固定EXE發布、Native或Owner UAT通過；本輪不再無限重做視覺設計。

**目前 V2 最終研究候選為 `2026.10.21+06a4e1c15ed9`。** 唯一 runtime Source `06a4e1c15ed98d2b92a02967eaea03d5d47f49d8` 已集中 d9 的 UX／Paper、c6 月營收增量與搬遷路徑修復。新包同版、Launcher 正反 SHA、frozen Main 100%／125%／150% 的17路由及四尺寸關鍵矩陣通過，worker／pool 0 自然關閉；260項整合回歸、mypy1120檔通過。全主機224 Tasks發現21相關項，Direct維持停用；已修Source邊界但未重跑producer或宣稱自然恢復。51份Codex設定已核，僅更新兩個既有Baldr prompt，48暫停及其他設定保持。金額單位Unknown、歷史完整月份0、正式金融資格PARTIAL、Native停止與Owner未驗保持。候選／交付SHA、真實維運缺件與集中外部動作見[Release Closeout](../06_qa/BALDR_V2_RELEASE_CLOSEOUT_20261021.md)；以下具名舊包及日期化紀錄按各自版本判讀。

**月營收全用途研究工程已交付，金融資格分軌。** Owner 已正式撤銷 current-only 授權限制。後繼Source提供雙市場原件版本歸檔、歷史分批capture／匯入、外部SHA資格reader、百分率因子／選股／比較／分市場shadow排名與逐用途安全入口；原推薦投影另接精確OpenData profile。QA022的228項／mypy11與真原件1,981列通過，QA023增量72項／mypy3通過；YoY可用1,975、Unknown6。官方授權已核並顯名，但金額單位Unknown、歷史完整月份0、正式PIT及Scoring／回測／Paper／Forward／ML Gate未成立；QA024兩市場HTML期限截斷仍拒絕，原FAIL保持。沒有更新正式資料／資金、Main設定或RC。詳見[全用途契約](../03_data/MONTHLY_REVENUE_FULL_SCOPE_CONTRACT.md)、[資格矩陣](../06_qa/MONTHLY_REVENUE_FULL_SCOPE_ACCEPTANCE_20261021.md)及[操作入口](../07_guides/MONTHLY_REVENUE_RESEARCH_PIPELINE.md)。以下 V2 固定候選與日期化結果按各自版本判讀。

**V2最終裁決：`V2_ENGINEERING_COMPLETE_PENDING_EXTERNAL_ACCEPTANCE`。** 執行來源`d9a2380fcb7e`已補具名TWSE／TPEx OpenData current-only pipeline與人工確認Paper producer／UI；原ledger／CAS、帳戶／成本政策及MOPS身份保持。Paper100項、mypy1113檔、月營收177 PASS／1 SKIP與強制UI回歸通過；QA019真Main歷史結果保存／fresh、QA038正常Main正向Paper fixture／exact reopen／返回通過。單次新RC `2026.10.21+d9a2380fcb7e`已通同版、Launcher正反SHA及frozen Main125%17路由／四尺寸、worker／pool0自然關閉；12檔收據SHA `4e96052e34eac8aab616ce77bb7361e24ad38bf8c0a2ab5c33733073dee9726d`。兩官方候選解析成功但單位／用途未接受；Paper正式帳戶／cash／mark／日曆輸入、今日來源stale、Forward成熟、Native停止與Owner未驗保持。五旅程完整金融分支仍PARTIAL，舊eefd包與正式入口不變；候選位置、精確證據及批准需求見[補完驗收](../06_qa/BALDR_V2_FINAL_COMPLETION_20261021.md)。以下日期化舊段按其版本判讀。

**最終工程裁決：`PRODUCT_RC_READY_WITH_LIMITATIONS`。** 10/21有界收尾找到並修復首頁日期適配缺陷：正式來源已有10/21排程狀態，reader不再將10/20行情截止日錯比為決策日失配，改沿既有嚴格canonical日期契約。真來源唯讀核回1列、保留降級／過時與未來拒絕，四檔不變；QA171編譯、75定向、Workbench85、更新頁25／0／4與mypy1108通過。QA164 IPv6屬匯入時本機探測被測試guard攔下，原整輪FAIL保留。具名來源版研究RC就緒，非全部金融分支完成；月營收binding、Paper正向producer及合法輸入、PIT／Forward／ML另管，OwnerUAT不阻候選、Native停止維持。既有eefd EXE不含後繼鍵盤與本次reader修復，未重建。詳見[工程收尾裁決](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#最終工程收尾診斷2026-10-21)，完成本輪後不再重複缺件檢查。

**自動化優先，Owner UAT不作日常Gate。** 依10/21 Owner override，程式／契約、自動GUI、原生Windows及Owner UAT四軌分列；來源版 `b8ed339f` 的明列研究功能為 `PRODUCT_RC_AUTOMATED_VERIFIED_OWNER_UAT_PENDING`，不宣告完整五旅程所有分支或金融資格接受。QA162真 `main()` 17路由／125%四尺寸通過；QA164當前Main的Registry相容120日／240列、不相容拒絕與返回功能完成，但整輪因守衛攔下urllib3本機IPv6探測而FAIL，原結果保留。正向首頁線索仍缺供本次驗證的原狀態檔，月營收／Paper真來源資格保持；Native停止→`NATIVE_SMOKE_NOT_EXECUTED`，Owner→`OWNER_UAT_NOT_PERFORMED`。既有eefd EXE不含後繼鍵盤修復，未新build；見[一頁摘要與截圖](../06_qa/BALDR_V2_AUTOMATED_ACCEPTANCE_20261021.md)。以下日期化舊Gate敘述不再單憑UAT未做阻擋開發或RC準備。

**來源版鍵盤修復已驗證，既有候選保留。** QA158通過編譯、29定向、85Workbench、更新頁25/0/4及mypy1108；QA159正常Main實測搜尋與子頁Tab／Shift+Tab、Alt+Left經原typed selection恢復同價格query／page／2317列，另13項最終shell回歸通過。這兩項修復未包含於既有 `eefd2163ad95` EXE，未因小修重建或替換入口。原QA155–157失敗保留，離屏自動檢查不等於Native或真人接受；細節與來源缺件見下方V2 QA。

**獨立工作繼續，真人等Owner有空。** Native停止維持；Luna已完成月營收／Paper取得鏈盤點，QA154已以記憶體內受限GET核兩個官方月營收端點HTTP200／14欄位，未建binding或來源接受紀錄。Main的MOPS current-only契約可採批次完成時間保守判定可用性，與P0歷史PIT隊列分開；尚需相符用途接受／可信binding，不能將OpenData改標MOPS。通用研究→Paper producer與正式帳戶／行情／現金輸入另列缺件，不阻獨立自動UI檢查；細節見[V2來源與自動驗證](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#來源取得與獨立自動驗證r188-起)。

**目前整合候選：eefd2163。** `2026.10.21+eefd2163ad95` 已將下列後繼 Source 集中封裝一次；QA144建置、QA146同版、QA148真正frozen保存報告／價格最新與原件返回、Paper建帳停用、QA150隔離啟動器正反SHA，以及QA152新候選125%／17路由與三尺寸首頁通過。12檔pin交付收據兩份同SHA `87cadb86f01fc45838bfa05d355c776c9359a7d283257ce2ee5a28784f6ca4d6`，舊版本不含項目依各段原身份判讀。完整五旅程仍PARTIAL、Native停止與真人待驗保持；詳見[V2候選驗收](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#eefd2163-整合候選qa144-起)。

**後繼 Source：選股保存與歷史返回。** 綜合選股共用儲存入口沿原來源 typed 流程，範本未成功查詢前禁止誤存舊 Query。保存報告與價格詳情可另開獨立最新查詢並重核返回；全域查股返回保留原投組／自選畫面。唯讀 Journal 不再把存取時間更新誤判為內容變更，缺失私人 Journal 空讀取也不再建立鎖檔；既存 writer／CAS及來源守衛保留。QA137編譯、209項定向、Workbench85、更新頁25/0/4與mypy1108通過，QA136 R168正常Main保存報告往返及125%儲存入口可見已限定驗證；QA141 R176亦已驗證價格詳情另開最新、重核同選取並返回原query／page／2317列，完整五旅程仍PARTIAL。固定a65 EXE不含本增量，見[V2驗收](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#選股保存與歷史返回qa130起)。

**後繼 source：Paper baseline 不再將未知補零。** 已保存推薦的研究用 baseline，總分或收盤價缺失、布林、非法文字與非有限數值會明確拒絕；明確觀測零仍沿原配置政策診斷，未改本金、日期或金融資格。QA128編譯、26項service／CLI／配置回歸及受改module型別檢查通過；無效輸入不新建或覆寫輸出。這是既有研究baseline缺陷修正，未實作一般候選建帳，也未重建a65 RC；詳見[V2驗收](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#paper-baseline未知值拒絕qa128)。


**後繼 Python source：保存研究的 Paper 條件檢查。** 已選原件經背景重核後才顯示來源、日期及原文，可查看既有 Paper 分區並返回同筆研究；換選、刷新、離頁或關閉後拒絕晚到結果。QA124 編譯、47定向、Workbench85、更新頁25/0/4與mypy1108通過；QA126正常MainWindow同筆原件／Paper往返、Journal與四來源保持、worker／pool0及自然刪除，root看過實圖。通用研究候選建帳producer與合法帳戶／行情／現金契約仍未實作，建立按鈕停用；這是產品程式缺口，不以benchmark或策略空倉seed代替，也不以長期金融資格阻擋其他功能。固定下列a65 RC不含此增量，未重建EXE；詳見[V2驗收](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#paper前置流程與100顯示qa123126)。

**目前 V2 本機技術候選：`2026.10.21+a65d2b2b4fd5`。** 整包位於 `dist/candidate_a65d2b2b4fd5_cb32716d/baldr`，使用 `Launch-Baldr.cmd`／`GUIDE.md` 及獨立 `r132_candidate_state`。新增研究原件與目前可讀資料的唯讀對照：先重核原件，再分列各自日期、來源及缺件，不寫回 Journal、不補未知或計金融差值。QA115 同版、QA117 包內正常 Main UI 保存／fresh 對照、QA118 啟動器正反身份切片、QA120 17路由1280×760／125%與另三尺寸首頁通過；QA121 沿原筆記補驗150%完整來源識別換行，原件／四來源保持、worker／pool0且自然刪除。EXE SHA `0417d9c1c2d6a812a55b777974be623f2a23bac49e874f0dc218d31a8410c9d4`；11檔交付收據 SHA `720f6b02a26a719a47f7b02b686d45e7af6cb7eb93acda72d2ac4eeab6e19240`。原工具失敗及重用證據版本見[V2驗收](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#研究證據對照候選交付qa113121)。未簽章、本機位置綁定；Native停止、真人待驗及完整五旅程 PARTIAL，金融資格不提升。

**保留回退候選：`2026.10.21+412ca3e5fe4f`。** 位於 `dist/candidate_412ca3e5fe4f_95e7e445/baldr`，使用包內 `Launch-Baldr.cmd`／`RESEARCH_GUIDE.md` 及獨立 `r114_candidate_state`。新增同題材成員上一檔／下一檔；QA103 真 frozen Main first/fresh 完成2330→2360→2330、原選列返回及來源選列變動拒絕，來源SHA保持，worker／pool0自然關閉。QA100同版、QA101啟動器正反SHA及1280×760／DPR1.5的17路由通過，首頁另驗1500／1440／1920。EXE SHA `68cfa7673abbbc7a2d148246bfd00897bca70a8299c04c5c54a708ed3adfeedd`；交付收據 SHA `8c677527f2a6a3723cafb816939e338d32d94c292716e16e48a319911c2c993a`。舊包／研究13／active delivery 保留；Native停止及真人待驗不變，金融資格與完整五旅程不升格，見[V2驗收紀錄](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)。

**已納入 412ca3 候選：同題材成員上一檔／下一檔。** Main 固定原題材版本、成員順序及選列，換股只更新代碼與名稱；返回保留最初題材選列。來源、篩選或選列變動後拒絕舊導航，保存時報告不可切股。QA092 編譯、85 定向、Workbench85、更新頁25/0/4、mypy1104通過；QA096 正常 Main 與新程序的成員來回及選列變動拒絕通過，固定 `2b164aede953` EXE 不含。QA092 文件定位命令使用未知領域而失敗，QA093 已用正確領域完成定位；原失敗保留，見 [V2 驗收紀錄](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)。

QA090 另以同一新 EXE 完成既有兩股保存來源的讀取、價格下限1、2317／2330比較、同源個股及原 query／page／row 返回，來源四檔、唯讀價庫與 Journal 保持，正常關閉／worker0。這是既有來源的限定旅程，不包含 EXE 來源產製或金融資格。更新後交付收據 SHA 為 `d88dfd7a765582cb816a16bbc1b757a97fda19bfa37b7d46f5239336572148c7`；八個關鍵檔 pin 不變，QA080 版原收據留存於任務紀錄。

**保留前版技術候選：`2026.10.21+2b164aede953`。** 本機 `dist/candidate_2b164aede953_1dff24ee/baldr` 已納入儲存盤點、首頁原報告回訪／分日及推薦頁關閉修復；用整包的 `Launch-Baldr.cmd`，指南為 `RESEARCH_GUIDE.md`，專屬 state 為本任務的 `r74_candidate_state`。QA078 Python／EXE 同版、QA080 真 frozen 原件 fresh 回訪／儲存正確套件根、啟動器正反 SHA 通過；17 路由於 1280×760／DPR1.5，首頁另驗 1500×900、1440×900、1920×1080。EXE SHA `8499fc15231750a3616316b40079c9ac572bbaa5af95943ffd98f4575585e89f`；交付收據 SHA `d88dfd7a765582cb816a16bbc1b757a97fda19bfa37b7d46f5239336572148c7`。舊 e369 與研究13保持，未替換 active delivery；完整五旅程、原生／真人及金融資格仍未接受，見[V2驗收紀錄](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)。

**後繼原始碼：首頁原報告回訪與推薦頁關閉修復已驗。** 最近研究的一般報告可直接開保存原件並返回首頁，原研究來源日與行情日分列，缺件不借用日期。QA073 歷史推薦 first/fresh 與 QA075 題材→2330、獨立 9/23 行情 120 點、保存／重開／首頁原件回訪均通過；題材來源仍是 10/16，原件 SHA、Journal 讀回及返回身份保持。推薦頁延後 resize 改為自有 QTimer，正常關閉不再存取已刪除元件；45 定向、Workbench85、更新頁25/0/4、mypy1103及編譯通過。原失敗及受限範圍見 [V2驗收紀錄](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)。固定 e369 EXE 尚未包含本輪修復，原生停止／真人待驗及金融資格維持。

**後繼原始碼：儲存盤點缺件診斷已修復。** QA060 確認固定 e369 EXE 對不存在的 `_internal/dist` 誤顯完成；後繼 Main 在封裝模式只量測目前套件，原始碼模式使用明示 dist 容器，並顯示缺件、不可讀及部分大小。定向 14 通過／1 平台連結跳過、真 Qt 事件循環雙次刷新 1 通過；正常 Main 首次盤點、共同 UI 與 mypy 已驗，詳見 [V2 驗收紀錄](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md#儲存盤點缺件診斷qa058-起)。e369 尚未重建、未含此修復；五旅程與真人接受狀態不變。

**V2 本機技術候選已建置，整體產品接受尚待。** 本機分支 `codex/baldr-v2-product` 已接四主頁、系統入口、題材版本目錄、綜合選股來源與漏斗、三個既有技術條件範本、共用個股章節、研究時間軸、策略庫與單頁首頁。QA023 正常 Main 完成一般查股保存／fresh 精確讀回、純自選及返回，17 路由在 1280×760、150% offscreen 保持尺寸；QA024 另以固定10/16真題材快照驗25鏈／90題材、CoWoS→2330→返回、筆記保存及新程序原件回讀，三來源檔SHA與Journal讀回不變。個股一般行情刻意隔離為空，未把題材價量補成其行情。QA035營收個股明確入口與精確短期回返25項及原view1項通過；QA036正常Main同指紋Registry fresh比較120共同日期／240列權益，原件保持。最新共同防線為Workbench85、更新頁25/0/4及指定mypy1103通過；固定e36919493b70 EXE已通過Python／EXE同版隔離與包內17路由offscreen，獨立啟動器正反SHA及受限樣本準備通過；候選位於dist/candidate_e36919493b70_a1df3b90/baldr，保留完整資料夾並依README啟動。完整五旅程、原生GUI、真人與產品Gate仍未接受。原生操作在使用者Escape後維持停止，研究13及金融限制不變。範圍、原失敗及未驗出口見[V2驗收紀錄](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)。

**後繼Source：第三階段獨立動量濾網。** 新增純規則`evaluate_theme_momentum()`，嚴格>70%、淨流入TWD／前20%與可得時間／缺件拒絕；[QA246a](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#stage3獨立動量濾網qa246246a)43項、單檔mypy及本檔精度／未來函數掃描通過。這是未接線MODE_A契約，未含研究13，不授真資料、排名、歷史PIT或正式策略資格。五小時額度100%先checkpoint；文件結構檢查待下個視窗，接著處理reader／映射與來源版本綁定，不能只信輸入旗標。

**最新可試用：研究13（`9838243476e6`）。** [啟動器](../../output/trial/Baldr-Theme-Research-13/Launch-Baldr.cmd)、[五條操作指南](../../output/trial/Baldr-Theme-Research-13/TRIAL_GUIDE.md)、[已知問題](../../output/trial/Baldr-Theme-Research-13/KNOWN_ISSUES.md)。保存報告完成後顯示「載入完成」；固定Main24960→9440確認原筆記／報告全文及日期不變、無producer重讀。首次設定521.344秒／原600、啟動器正反SHA及封存通過，交付SHA `ae7f310408a1551d342ef967a2560e8c84206def94c9820c52b1963230f3341c`；[本輪QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定13保存報告完成狀態交付qa240244)。未改主要旅程沿12證據，舊包與私人資料保持；金融／PIT／自然成熟／Native／真人限制不升格。

**research07五項回報已交付研究12（`ec4dd639b6be`）。** [啟動器](../../output/trial/Baldr-Theme-Research-12/Launch-Baldr.cmd)、[五條操作指南](../../output/trial/Baldr-Theme-Research-12/TRIAL_GUIDE.md)、[已知問題](../../output/trial/Baldr-Theme-Research-12/KNOWN_ISSUES.md)。一般查詢可明確離開保存context並辨識2330台積電；原F07圖顯示同版SMA20／60；題材可一鍵清除；原價格筆記可確認刪除整篇及修訂、重開不復活；績效與原逐日訊號入口分開。原07三筆實際run唯讀可讀419列，0／1成交不阻擋該對照。517.579秒／原600首次設定、固定EXE10788→26748筆記／MA／查股及41268→10408清除／960、新程序與啟動器正反SHA通過。EXE `918624dd549daec146c69b8986ce8b887e03bccb135ba9d9de1c8fef0f595dc6`，交付 `d161a7363131062e37c153d03760b7f323c18c5a7cfbc37c65a05bbc4d1613c1`；[本輪QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定12research07回報交付qa227234)。舊包與私人原件保持；保存報告缺行情、一般行情9/23及各項金融／權威／PIT／自然成熟／Native／真人限制保留。

研究12另通過[跨頁回訪補驗QA236b](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定12混合回訪補驗qa235236b)：一般保存報告→題材2330返回→F07／2506返回→一般查詢→原筆記及保存報告，新程序一致；10月19日保存內容未被10月20日新查詢改寫。後繼Source已修正保存報告已載入仍顯示「讀取中」的誤標；[QA238](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#保存報告完成狀態修正qa238起)定向6項／Workbench85／validator25-0-4／mypy1083通過，固定12尚未含。額度恢復後直接接此獨立切片，研究13已完成建置、首次設定與正常Main／新程序驗證，固定12原包保持。

> 更新：2026-10-20（使用者時區）。本頁列目前入口、各流程進度與下一個出口。逐輪身分、原FAIL與收據見[具名QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)，交付順序沿[原計畫§0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)。

## 現在有哪些入口

**保留候選：研究11（`b676c7bca0e0`）**，[啟動器](../../output/trial/Baldr-Theme-Research-11/Launch-Baldr.cmd)、[五條流程指南](../../output/trial/Baldr-Theme-Research-11/TRIAL_GUIDE.md)與[已知問題](../../output/trial/Baldr-Theme-Research-11/KNOWN_ISSUES.md)。產業與題材新增25鏈卡片目錄、題材／去重成員數與名稱序前三捷徑；點題材進原成員，2330個股可返回原選取。首次設定529.296秒／原600、同版EXE25964→22428、1280與960×720及啟動器正反SHA通過，Root看四圖。EXE `fbd420f0c75c6af13125bf60a6c43da107f0af78eb0aca6b73ddc1d6a68684ad`，交付 `4e92bc1fc54ca2035e8b6eeba338cff0aaefa6d45e39f8f2584030b68a71544f`；[QA215–219a](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定11產業鏈目錄交付qa215219a)。本次未寫筆記；未改旅程沿10，外部TPEx快照原位置、資料缺件與金融／PIT／Native／真人限制保持。

**保留候選：研究10（`6f27d4aebbbf`）**，[啟動器](../../output/trial/Baldr-Theme-Research-10/Launch-Baldr.cmd)、[五條流程指南](../../output/trial/Baldr-Theme-Research-10/TRIAL_GUIDE.md)與[已知問題](../../output/trial/Baldr-Theme-Research-10/KNOWN_ISSUES.md)。新增明選10/19上櫃法人題材版本：看原股數與覆蓋分母、2330個股返回、保存判斷及重開原文。90題材中66部分覆蓋／24無覆蓋，完整法人排行無合格列；價格、TWD金額與五日量能不補值。首次設定569.641秒／原600，同版EXE33924→40200與啟動器正反SHA通過。EXE `31f8408b87ab16c617bdf4ec45068edd909ab6a47c89a4db7329408672a542f7`，交付 `f987161f453a4f96b4120efba8ccc61ac3d15751524687e9813b47aa9f71974c`；[QA206–210a](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定10法人題材交付qa206210a)。來源綁本機具名task位置；未改流程沿09證據，舊包及私人state保持，完整金融／PIT／Native／真人接受分項保留。

**本輪Source驗證：產業鏈卡片目錄。** 原M2的25鏈探索補上收合目錄、各鏈題材／去重成員數及名稱序前三捷徑；不新增金融公式。212g定向44／Workbench85／validator25-0-4／mypy1082、213e正常Main52592→32864的25鏈／90題材、1280與實際960窄窗、2330個股返回及原件保持通過，Root看圖；[QA212–213e](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#產業鏈卡片目錄qa212213e)。固定11已完成同Source建置／首次設定／EXE與新程序，固定10未含；不是完整M2金融或原Gate接受。

**保留候選：研究09（`42cf6b047643`）**，[啟動器](../../output/trial/Baldr-Theme-Research-09/Launch-Baldr.cmd)、[五條流程指南](../../output/trial/Baldr-Theme-Research-09/TRIAL_GUIDE.md)與[已知問題](../../output/trial/Baldr-Theme-Research-09/KNOWN_ISSUES.md)。本版修復法人唯讀表格被長來源說明裁切，先向下捲到表格底，再水平捲動可到全部11欄。首次設定576.859秒／原600，同版EXE25980→49976的三證券九原股數、來源／用途／時間、返回與新程序一致；Root看兩圖，啟動器正反SHA及封存通過。EXE `fb32b87af5551a79199346a6da1a4a1d1a7aca3a968ee6276ecf9d127858fe1c`，交付 `b839cb41b8dcb35dce6bb3f99ff067514a657807ed7f54e84fce90299ef798c2`；[QA193–197d](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定09法人表格交付qa193197d)。未改排行、筆記及其他旅程沿08原證據；可選10/19法人來源綁本機task位置，不是可攜來源或題材法人v2。08及舊包、私人state保持。

**保留候選：研究08（`d69781fa89cf`）**，[啟動器](../../output/trial/Baldr-Theme-Research-08/Launch-Baldr.cmd)、[五條流程指南](../../output/trial/Baldr-Theme-Research-08/TRIAL_GUIDE.md)與[已知問題](../../output/trial/Baldr-Theme-Research-08/KNOWN_ISSUES.md)。本版補上題材排行的「由高到低／由低到高」，各從完整合格母體取五，排序保留原Decimal／整數精度。原版本54個漲跌、55個成交額題材可核兩端，法人／五日量能缺件保持。首次設定511.282秒／原600，同版EXE19332→53376的排行、1280控制項同屏、原成員／個股返回、讀取中關閉與新程序一致；啟動器正反SHA與封存通過。未改價格筆記、首屏／期限、一般報告與Registry等沿07及其原證據。EXE `3e9bdc32ff060274f892041aa77d978021f5dc2ced06514b4cb8d35b4f7255d2`，交付 `218189c128a48d44ec6b1df580491da67667d5773fdce60010b0f55ae0829c63`；[QA179–183](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定08題材雙向排行交付qa179183)。[原07](../../output/trial/Baldr-Theme-Research-07/TRIAL_GUIDE.md)、舊包及私人原件保持，完整金融、歷史PIT、自然成熟、Native／真人與原完整Gate分項保留。

**法人資料後續：10/19 TPEx原版本。** 單次官方API取得888筆報表列，台北10/20 07:00前拒讀、到點後固定08原法人頁8832→15164明選三證券、原九股數／用途／返回／新程序一致，22來源檔不變；可按[具名欄位指南](../../output/tasks/baldr-post-completion-execution/TPEX_20261019_GUIDE.md)開啟。本機原位置綁定，跨位置／真人與完整Native未驗；舊08最後欄被裁切已由189b確認；Source最小自然高度修復後，190定向／防線及191a正常Main35948→28512全部11欄可到達通過，固定09另由196d同版EXE／新程序驗證全部11欄並交付。Source另完成同版多股reader與TPEx adapter，原映射890個TPEx代號中763命中、66題材僅部分覆蓋，90列原值／缺件與新程序通過；不混另一日價格、TWSE或提升歷史PIT。新batch API已含09，但正常題材接線未含08／09；Source flow-only v2經200合成邊界／共同防線，203修正精確tpex市場後定向50通過／2略過與mypy1082，真到可用小時後201a public／新程序與202e正常Main3560→51796已限定通過，不因日報UI通過列法人卡完成；[QA185–188](../06_qa/BALDR_THEME_DAILY_QA_20261018.md)。

**保留候選：研究05（`34b8e8d5402b`）**，[啟動器](../../output/trial/Baldr-Theme-Research-05/Launch-Baldr.cmd)與[五條流程指南](../../output/trial/Baldr-Theme-Research-05/TRIAL_GUIDE.md)。新增已載入題材的股票反查：輸入2330或台積，明選鏈／題材後定位原成員，再進個股並返回。首次設定542.171秒／600、同版EXE21696→38288、讀取中關閉／新程序與啟動器正反SHA通過。原保存五股推薦與Journal沿04原證據，一般四股報告及未改流程沿03等證據；05沒有重驗全部旅程。行情缺件與期限衝突／未知仍隔離，不授今日自然推薦、成熟或績效。EXE `53ed5302a13ceb1e646933cb3a34fca999d1732d19076c32907d648297391f34`，交付 `3bc5a251bce63d0fbd91a099f395b53d8abc0a3dcd6eb7f6960b0341d23d7cf8`；[QA136–140](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定05題材反查交付qa136140)。原04及舊包與私人state保持；後續推薦首屏排版Source尚未收入05。
**保留候選：題材研究02（`b292f803ce9c`）**，[啟動器](../../output/trial/Baldr-Theme-Research-02/Launch-Baldr.cmd)與[指南](../../output/trial/Baldr-Theme-Research-02/TRIAL_GUIDE.md)。包含筆記直接前版比較與個股首屏日期／依據分層；固定EXE移位首次設定492秒／原600秒、正常Main49584→新程序21272、三筆精確原文／保存期間關閉／實際800px比較及啟動器正反SHA通過。EXE SHA `2dfba4f2439406fbe62ece846e4ac60e81904d94d86dd914c4702fed5253b02c`，交付SHA `b044c2eb15760f20c903b375c4e9eccc9c3b5913cc2ce9193c7164c24735a4a2`。原日常資產及自有task具名名冊保持bytes，模板無私人state；01／143原包保留。首頁明選控制項已封裝，但真實多候選固定旅程未驗。題材10/16與一般行情9/23分開，法人／五日曆／PIT及完整Gate／真人限制保持。

**日常研究143原版保留（`bb09f218bba1`）**。原[Launch-Baldr.cmd](../../output/trial/Baldr-Daily-Research-143/Launch-Baldr.cmd)、私人state與[指南](../07_guides/TRIAL_VERSION_GUIDE.md)均可回訪。本包內含自有runtime與原件，首次啟動前放妥完整資料夾；本機新位置首次設定537.875秒／600秒，正常頁與同版新程序已核。舊139、141c及131保留，不自動匯入私人資料。EXE SHA `fcb94b81fefaea11eb83a52027bbe83c11772738586b1c7025e49add48476de9`，交付SHA `7495f1e3ff6129d97afab4f2eaf1ff8f5acc6c8369ea78db9c5d283c3bf131b1`。

116與更早候選保留，不能把其外部檢查當目前版本驗收。三個判讀已在指南更正：0完成配對不等於沒有訊號；公司名錄缺來源憑證仍限制用途資格；118起價格選股雙擊會進主個股頁。一般四股行情與1,951檔同源價格研究仍是不同範圍及日期。

| 使用流程 | 已有成果 | 下一個出口／尚有限制 |
|---|---|---|
| 市場與個股 | 市場狀態、四股價格／技術；三公司五列半年比較，2382新增同表月營收與增減率 | 一般行情截至2026-09-23；月營收最新2026-09，兩者各標日期。缺方向不補造，2382半年財報缺件隔離。 |
| 價格選股與收藏 | 2026-10-16來源：宣告1,989／處理1,951／排除38，可設條件、同源個股、2–5股比較、收藏及重開 | 5筆UNKNOWN；名錄用途與來源clock未接受，不稱正式真N或歷史PIT。 |
| 清單、持倉與情境 | 持倉在四卡下方，唯一精確代號／名稱互補，回個股可重載；初次情境有隔離證據 | 私人帳／真人及真策略Paper同日原件仍待，不以手動成本造NAV。 |
| 回測、保存與比較 | 原單股規則、結果、返回及新程序重開；2–5個同股同窗保存策略可看逐日意圖，附三筆示範 | 研究樣本不等於策略有效。SOP／Baseline FAIL、Walk-forward、成本／來源權威、PIT及完整雙策略績效分別保留。 |
| 推薦結果追蹤 | 134補計畫目標日、實際取價日與缺價原因；5／10／20日受限結果可回訪 | 1538缺價、60日未成熟與P12正式時序／修訂限制保持。 |
| 首次設定與搬移 | 143固定EXE／自有runtime及具名名錄；本機新位置537.875秒／600秒完成，受改Main／同版新程序、原研究金融值及啟動器正反SHA已核 | 只接受全新包本機出口。已用state、跨機、私人帳與其他DPI待；142原FAIL／partial及139／141c保持。 |

V1維持[原四條流程與驗收出口](../superpowers/plans/baldr_product_completion_plan_20261006.md#03-兩階段交付與v1範圍凍結)，後續增量不擴V1範圍。134已有1280×760保存策略回訪及1500×900新回測保存／新程序的限定原生證據；完整Native、其他DPI及真人接受仍待。

## 目前工程狀態與限制

**題材高低兩端排行已交付固定08。** 現有資料即可解除原M2僅有高端前五的缺口；在原四類排行加「排序方向」，低端從完整合格母體取五名，四張摘要仍維持高端。排序直接比較原Decimal／整數，不以負號觸發呼叫端精度捨入。QA176定向及必要防線、177正常Main43680→17196高低排行／原成員／個股返回／新程序已核；原版本漲跌54、成交額55個題材覆蓋完整，法人與五日量能保持缺件。07未含，固定08另由182核同版EXE、新程序與新控制項同屏；見[QA176–177](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#題材雙向排行qa176177)。

**固定06的25鏈已補驗探索與股票訊號。** 以實際10/16版本載入獨立產品題材頁，25鏈與90題材選項符合原映射；每鏈明選一題材、核該題材成員欄位並雙擊一股，兩程序17840→10572訊號一致、原件及Journal保持。這是view層出口，未宣稱25鏈完整Main報告／返回或金融資格；Main題材個股返回沿05原證據，見[QA158](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定06的25鏈探索qa158)。法人／合格日曆／歷史PIT缺件不因25鏈可探索而完成。

**原價格版本筆記已通過Source與固定07旅程。** 有界語義證明只省重複計算，保存／讀筆記／開原版本仍fresh完整原件；同View、同query返回沿既有P01頁面介面重讀並完整比對選取，跨query仍full重開。QA167定向與必要共同防線通過；168正常Main14416→42708完成三篇原文、直接修訂、原版本／返回、保存中關閉與fresh，197.032／130.969秒均在原240內，返回1.219／1.235秒在原15內。兩程序Journal／清單SHA一致，network／protected／errors皆空；固定06未含；07的同版EXE另由173a限定接受，真人／金融／PIT／完整Gate不升格，原104／155／164／166 FAIL保留。見[QA163–168](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#f07語義證明範圍qa163164)。

**逐期限說明已分開共通限制與各期差異（固定06）。** 全部所列期限共有的來源限制集中一次；各列先顯示缺價／已有價格／等待目標日，未連結仍先顯示阻擋理由。原狀態、兩日期、品質／採認限制及完整tooltip保留。1538／1528真八列、正常Main27256→40692已核，固定06已包含；05原包保持，見[QA145–146b](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#逐期限說明qa145146b)。

**原保存推薦的首屏已修復（固定06）。** 1280×760正常主視窗現在可同時看見原五股與「查看個股研究」，不用先捲過四個來源動作；窄窗仍採原堆疊與捲動。37項受改／原讀回取消及舊格式、共同防線與正常Main12900→38268均已核，來源／清單SHA保持。固定06已包含；05原包保持，見[QA142–143](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#保存推薦首屏qa142143)。

**已載入題材的股票反查已交付固定05。** 代號／名稱可列多鏈題材及同名股票，明選後定位原成員並沿既有個股返回。真10/16版本2330三題材、正常Source與固定EXE／新程序、重載中關閉已驗，20受改／原導航及必要共同防線通過；不重算金融或讀外部來源。見[Source QA133–134](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#題材股票反查qa133134)與[固定QA136–140](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定05題材反查交付qa136140)。

**首頁原保存推薦已有 Source 閉環。** 明選控制移到首頁候選列，context保留原snapshot並返回原工作台；較早候選仍不能當今日推薦。QA123b以正常隔夜首頁的原保存結果入口讀回10/19真5股，明選1512／1236、各自保存Journal筆記、返回原清單，再由新程序17292→48020核原文與身份一致；沒有注入日期投影或改時鐘。89項受改、Workbench85、validator25/0/4、mypy1081另有證據，不以案例加總作完整Gate。固定03未含此接線，固定04已含接線，模板以明選保存來源展示；原行情缺件不補值，今日自然管線／完整行情報告與真人接受分開。詳[QA118–124](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#首頁真保存候選閉環qa118123)。

**首頁明選 Paper 部位已有 Source 導覽出口。** 已接既有共用 read model 與唯一部位，不改金融計算或帳本；持倉頁獨立刷新核完整同版本後才定位，失配不回退手動同股。受改檢查及共同防線已有具名證據，正常 Main 與新程序40912→37776控制資料往返已核；另修復1280外層捲動時機，明選的同股第二部位確實可見，返回保留首頁選列／捲動。固定03未含本葉片，真實 Paper／歷史保存重開／真人資格不由控制資料代替。見[QA108–116](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#首頁-paper-同版本部位導航qa108112)。

**原價格筆記的早期失敗保留，後續已交付固定07。** QA104曾在原240秒整段未完；先前逾時與未歸因的存取違規、155／164／166失敗均保留，不回改舊03或06。後續Source168及固定07的173a已完成完整保存／修訂／原版本返回／保存中關閉／新程序讀回，見本頁最新候選與[具名QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定07原價格筆記交付qa170174)。早期首頁多股來源缺件另以正式來源的有界bytes保全後核兩筆canonical保存結果；其正常多股旅程與首屏已由固定04／06分別限定交付，不以本段舊狀態否定後續收據。

**一般整份報告判斷已交付固定03，可開始試用。** 固定來源`519233422d00`；在一般個股載入四股報告後，可保存當時完整報告與判斷、明選原文、直接修訂比較及關閉重開。首次設定545.922秒／原600秒，同版EXE48996→44680與啟動器正反SHA通過；無私人state，不接本機candidate／外部ML。數值、原缺件與來源資格保持，排名context仍拒絕保存。入口見[03指南](../../output/trial/Baldr-Theme-Research-03/TRIAL_GUIDE.md)，限定範圍與原FAIL見[QA95–99](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定03一般報告保存交付qa9599)；完整M3／Native／真人接受另列。

**筆記回訪比較與個股首屏改善已納入固定02。** 可並列直接前版原文，實際800px窗及新程序保持Journal bytes；股摘要保留有日期的行情事實，分開持倉、本次技術線索與明選保存推薦正反，查詢日不再誤稱資料日。Source相關70項、validator25/0/4及mypy1076與同版EXE受改旅程各有證據，原鍵盤等待FAIL及診斷保留。02未含一般報告判斷保存（03見上），完整M3仍待，詳[本輪QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md)。

**原D固定EXE技術出口已補驗。** 題材01隔離副本的三筆exact保存策略、原規則、歷史原結果、返回已讀對照及新程序讀回通過；419觀測日的原意圖不是成交，金融identity／原件及Journal bytes保持。1280視窗先按「查看實驗結果」；真人D與Native仍待。收據、原FAIL與限定判讀見[QA36b](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#原d固定exe技術出口qa36b)。

**題材研究閉環已有固定候選。** 題材觀察／排行、25鏈及成員可進一般個股再返回；判斷沿原Journal追加、原文唯讀，正常EXE與新程序按原SHA讀回。每篇筆記有獨立修訂根，並行CAS及過時祖先守衛保持；保存期間關閉會等待已送出寫入。首頁多候選明選的112相關Source測試已驗，控制項已含02；尚無真實多候選固定旅程接受。原FAIL、身分與限定範圍見[題材QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md)。法人／五日曆／歷史PIT／真N、完整UX與原補完未完成項繼續保留。

**139的月營收成果已保留於141c。** [139 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment139-quanta-monthly-sales)綁既存TWSE公司原件與廣達官方月營收，八檔版本保留同表百萬元整數／0.1%披露率。真實台北10/18 04:00後的原正常頁／新程序、股票切換與捲動證據維持；141c另驗新根五列原值、精度及歷史隔離。未改旅程沿原證據，未重跑全部四流程或授完整Native。官方綜合損益表入口302 ASPX錯誤原件保留，停止該入口；半年財報缺件仍隔離，不混表、推算累計或接評分。完整F12、來源／PIT及原計畫其餘列繼續保留。

[138](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment138-first-trial-setup)兩次600秒FAIL及partial原件保留。[140](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment140-archive-byte-reuse)在同一恢復工具限量重用初次SHA已驗原件，保留前後完整實體核對，Source整包首次設定已在原600秒完成；不替換139或授整包可攜資格。135月營收因子的缺月／前史修正只屬後端工程驗證，尚未進指定候選的正式評分。這些局部成果不授完整F12或P14。

[141c](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment141-full-trial-exe)已解除本機固定路徑及漏帶139內容的交付阻礙：v2明選月營收／市場狀態，生成config沿共同契約；48項整合／保護檢查與mypy1069通過，新固定EXE設定、Main26016→32764受改讀回及啟動器正反SHA通過。Windows背景QA保留原斷言／15秒，未攔截關閉；原提前close來源仍未確認，原FAIL完整保留。CMD改用.NET SHA256核同一EXE，不依賴缺失cmdlet。完整包與指南已封存，未授完整跨機、私人owner-migration或Native；下一輪沿原第三至五列可獨立出口續推。

外部缺件各自隔離：TPEx年度日曆授權、TPEx法人API、官方文件／單位／用途、歷史PIT、真N、完整績效、Native／EXE及Paper／forward自然成熟分別判定。MOPS partial／缺EOF及舊月營收／TWSE GET耗盡scope保持，不重抓、不把一處缺件變成全產品新前置。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4未完成項仍在原計畫，不以commit或案例加總計完成率。

[142固定候選](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment143-setup-work-scheduling)已回應139真人回報：五列月營收值前置、來源長文可展開；窄頁條件／結果可捲、代碼可單獨清空；具名名錄只補顯示名稱，同源收藏直接開原個股並返回。Source定向與共同防線保持，另驗新包首次設定、正常固定EXE與同版新程序讀回及啟動器正反SHA；未重跑未改旅程。逐期限說明已核143副本8列，按[期限表](../07_guides/TRIAL_VERSION_GUIDE.md#原推薦結果與保存策略的判讀)分清缺價／ready受限／待成熟；真人D未驗；原金融值、缺件、精度及時間守衛保持。

## 產品與系統入口

- **進度與交付**：[原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保留；不以 Increment 或測試數量計算完成率。
- **產品方向與來源優先序**：[Product Roadmap](PRODUCT_ROADMAP_POST_REFACTOR.md)；正式 Gate 依賴見[六個月工程路線](ROADMAP_6M_ENGINEERING.md)，不以本輪交付排序改寫 Gate。
- **實際操作**：[APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)；首次設定看[快速開始](../07_guides/QUICK_START.md)，移機看[首次安裝／移機 Prompt](../07_guides/FIRST_INSTALL_PROMPT.md)。
- **現行與目標架構**：[system_architecture](../01_architecture/system_architecture.md)／[current 分冊](../01_architecture/current/README.md)；[FINAL](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 是目標設計，不作已實作證據。
- **主程式與資料**：`ui_qt/main.py`，九個頂層工作區；資料位置由 `data_module/config.py` 的 `TWStockConfig` 管理，預設 `DATA_ROOT=F:/Min/Python/Project/FA_Data`，不能以 repo 相對路徑推定正式資料位置。大型 repo 產出與測試暫存經 junction 存於 `F:/Min/Python/Project/BaldrStorage`；2026-10-20 已完成 D→F 六個 Baldr 資料根搬遷核對及 D 原根清除，C repo 仍保留原始碼、`output`／`dist`／`.t` junction 指向 F；遷移收據與限制見[儲存搬遷 QA](../06_qa/BALDR_STORAGE_MIGRATION_20261020.md)。
- **L2 產業鏈與題材**：[`decision_module/industry_theme_map.py`](../../decision_module/industry_theme_map.py) 保留季度／手動25鏈萃取。後繼application層另讀明選本機版本、每日聚合並接題材頁及研究筆記；規格見[設計文件](../02_features/INDUSTRY_THEME_MAP_DESIGN.md)，原萃取[QA](../06_qa/INDUSTRY_THEME_MAP_STANDALONE_QA_20261016.md)與新[限定旅程QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md)分開；固定143尚不含新頁。

## 重要限制

- 正式資料寫入、全量回補、正式 Task／maintainer 變更、push、發布與交易沒有新增授權；私人資產與其他 owner 變更受保護。
- 金融精度、決策當下可得性、來源用途、原 FAIL 與各 Gate 門檻維持；缺值與未知不能補零。
- Historical replay、readiness、dry-run、shadow、Paper、合成資料或測試通過，均不能代替真來源、有效績效、真人接受、自然成熟或 production ML 資格。程式碼／EXE 可啟動也不授上述接受；UI 的既有 mypy ignore 設定不證強型別。
- Root 串行 QA 與資源守衛依[共用規則](../agents/shared_context.md)。本補完 task 已用完新建代理額度 10/10；只在無待寫與無衝突時重用既有 Luna。
- 修改範圍內既存 37 個 `output/` 連結越界問題已完成具名盤點（真缺件=0、路徑錯誤=0、全數為 `BaldrStorage/repo-output` 實體存在之試用包與任務指南）；因 Windows NTFS junction 跨磁碟邊界依嚴格模式列管。依契約保留證據連結，不刪除連結、不全面豁免 output，差異檢查維持新增錯誤為零（收據見 `wp6_document_links_triage.json`）。

[143固定交付](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment143-setup-work-scheduling)以537.875秒通過原600秒本機新位置設定，正常EXE與同版新程序核受改月營收、窄頁、顯示名稱及同源收藏，啟動器正反SHA通過。派工寫2／讀4與完整守衛保持，原142 FAIL／partial不改；完整跨機、Native／真人、金融資格與原計畫各Gate仍分別待驗。
