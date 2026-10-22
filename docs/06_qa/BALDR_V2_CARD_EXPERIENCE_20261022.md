# V2 圖卡優先研究體驗

狀態：`UI_SCOPE_AUTOMATED_VERIFIED_WITH_LIMITS`。本次交付為原始碼的圖卡與研究動線；不是固定 EXE、完整產品接受或金融資格收據。

## 範圍

基線 `32d37e1295a11fae005f4465502b12a908a9dced`，分支 `codex/baldr-v2-product`。使用者要先看市場、候選、股票支持／反證與報酬研究，再下鑽、保存判斷與回訪。Root 依序履行 Execution、Tech Lead、QA、Documentation，未委派獨立 reviewer。

只改 `ui_qt/` 展示與測試、必要文件；不改 application DTO、金融計算、來源資格、正式資料、Quick／Freshness／Evidence 或排程。既有 dirty `BALDR_V2_RELEASE_CLOSEOUT_20261021.md`（空檔 SHA `e3b0c442…b855`）保持，不納入提交。固定 `2026.10.21+06a4e1c15ed9` EXE 未重建，不含本次增量。

## 完成行為

| 需求 | 本次行為與證據 |
|---|---|
| 首頁先看重點 | 風險、市場、候選、資料影響並排，窄窗單欄；候選明選、來源與導航保持。重排／缺件／不額外讀取測試通過。 |
| 個股同屏 | 原研究價格圖與支持、反證、限制並列；六章節、精確價格表及來源稽核保留。切股清舊圖，建圖失敗仍可讀報告與價格表。 |
| 報酬判讀 | 使用既有產品投影的相對基準白話、成本與研究資格；H5欄位衝突拒顯數值，不混H20毛報酬。沒有估計就明示不能判定獲利機率。 |
| 原價格研究 | 圖與原五條規則的支持／反證同屏，完整條件可展開；返回仍核對原 selection。 |
| 選股先看結果 | 來源準備、版本與進階條件用緊湊展開列；原查詢按鈕保持。正常Main 1280×760的真保存結果首列完整可視，三列均可讀。 |
| 原件後再查詢 | 修復原每頁3筆等合法非預設值回訪後變空選項的UI缺陷。三股真原件驗證：原選列／頁數保持，範本不自動查詢，明按原按鈕後沿同 generation 查詢。 |
| 題材與紀錄 | 有完整覆蓋的觀察值才放大成卡；初始未載入與缺項集中提示。大金額顯示萬／億元、完整原值保持；零／負值與排序不改。保存時間顯示台北分鐘，原時間留在提示／明細。 |
| 策略庫 | 規則、風險、成本與資格先呈現；參數及來源原文可展開、可捲動，展開不執行回測或寫入。 |

## 最終自動驗證

本機證據根：`output/tasks/v2-card-experience-20261022-01a161de/`。執行器使用共享鎖、全Job committed memory 8 GiB／12 process、啟動前至少8 GiB可用RAM；PASS輪次自然排空、程序0、handles關閉及鎖釋放。Raw output及截圖不提交。

| 檢查 | 結果／原件 |
|---|---|
| 本次UI、保存來源、模型成本、圖表、時間軸與返回 | 286 PASS；`root/targeted_final_commit.txt`。含拒絕無效來源選擇保留日期、失去來源清除舊日期的回歸。 |
| 原來源View分批回歸 | 46 PASS：v4 UI8、價格17、月營收6、價格聯合V2 5、舊聯合6、均線4；`root/native_ui_results.json`。V2另含真257列／兩parent的查詢與收藏回訪。 |
| 強制Workbench | `pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=`：85 PASS |
| 更新頁validator | `scripts/qa_validate_update_tab.py`：25 PASS／0 FAIL／4 SKIP |
| 型別 | `mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime`：1124檔通過；兩個既有annotation-unchecked提示保留。 |
| 編譯 | 所有本次修改及新增Python檔 `py_compile` 通過；上述防線原件為 `root/commit_mandatory_*.txt`。 |
| 正常Main與縮放 | `main_final_layout125`／`150`：1280×760、1500×900、1920×1080，120日期圖同值、保存／新程序原件回訪、原選列返回、Journal不變及worker0。原17路由另有 `routes_final125`／`150` 的worker／pool0收據；不等於Native／Owner接受。 |
| 首屏實際可視 | 正常Main直接檢查結果首列，以及三尺寸模型成本／資格標籤的完整visible region；不是只測元件存在。Root已看1280選股與模型卡、150%模型卡等實圖。 |

報酬正向畫面使用明示「QA模型示意（非正式資料）」的typed snapshot，沿既有產品投影顯示H5落後基準1個百分點、80bp成本與研究資格；未寫Journal、不代表模型真來源或金融資格接受。行情則為具名候選樣本的隔離副本，不是新抓行情。原件及前後副本SHA均保持 `eeea9a1a4bbf119bda97465d87e7a9e3b0c1268ffec2f1f9fd9a03248125ddc4`；P0程式目錄差異為空。

## 保留的失敗與界線

- `targeted_03`：28 FAIL／91 PASS，Windows locale無法在strftime格式內編碼中文；改為ASCII時間格式另接中文標籤，後繼通過。
- `targeted_06`：2 FAIL／278 PASS，空摘要圖干擾舊章節選取，以及建圖初始化失敗阻斷報告；延後建圖並保留降級，後繼通過。
- 真原件檢查先遇測試fixture沒有waitUntil，再抓到原頁數空選項；檢查器與UI分別修正，`real_source_adapter04_stdout.txt` 20 PASS。AST檢查器的中間失敗亦保留。
- 額外合併完整來源回歸在600秒期限以124結束；`single_owned_qa_4011d8bc0dd445e19c13e1af41e4094c` 原FAIL保持、最後程序0。另一次獨立v4大fixture診斷為3221225477，輸出停於JSON encoder／Windows access violation，不能據此裁定根因。
- 因此兩個依賴v4 `synthetic_full_store` 的257股案例仍未完成，不宣稱完整producer、全母體、金融資格或資料恢復通過。來源頁除明示展示標記與合法原頁數恢復外，未改reader／producer；本次UI以三股真原件、其餘46項原View及正常Main驗證。沒有修改大型fixture或放寬原測試。
- 早期render的匯入與延後啟動等待器失敗保留。共用 `root/*.png` 曾被後繼render覆蓋，只作歷史檢查紀錄；最終視覺證據只採獨立的 `main_final_layout125`／`150`，明載本機中文字型。
- 文件新增10個連結、Coverage與task結構檢查通過；全庫檢查仍有96項既存Junction引用問題，原件保留，不冒稱全庫通過。

Native停止、Owner未驗、正式金融資格、PIT／Forward成熟及Daily Operations Recovery各自保持。本次不執行排程、交易、正式資料更新或EXE發布。

## Track A 首屏增量（2026-10-22）

基線 `4dd820139148`，任務 `track-a-ux-20261022-01a164e6`；本節只涵蓋本批個股與首頁展示增量，不重新授予前述完整功能或金融資格。Root 依序履行 Execution、QA、Documentation，沒有獨立 reviewer。共享 `main.py`、Reader、DTO、金融計算與其他 Track 檔案不在修改範圍。

- A1：工作區身份與保存／追蹤動作同列，股票身份與章節下鑽同列。保持完整公司名、查詢日、來源日、Unknown 與缺件。正常 Main 三尺寸的原行情圖與報告同值，保存、原版本回訪、返回原選列及新程序 Journal 不變均通過。
- A2：只在既有候選入口已無可選股票時收起停用控制；缺件結論仍在圖卡。有可核過期保存結果時保持原結果入口，刷新恢復多股選單時仍須明選。`missing/degraded` 但仍提供股票的既有契約保持。
- 本批沒有重做 A3–A5；它們目前沿本文件前批的成果與限制，不能把本批標頭改善宣稱為全站 UX 接受。

證據在 `output/tasks/track-a-ux-20261022-01a164e6/`。`single_owned_qa_bf2adb3550d9433e820fe3ed8325f72a` 正常 Main 125%／150%，各驗 1280×760、1500×900、1920×1080；首屏完整 visible region 核身份、章節、主圖、保存與報酬限制。兩個縮放均 first/fresh 通過、worker 0、Job 自然排空、handles 關閉與共享鎖釋放。Root 已看125% 1280／1920與150% 1500實圖；本批重用具名行情隔離副本及明示非正式的報酬 QA snapshot，沒有新抓行情、產生預測或操作 Native。

首次標頭回歸83 PASS、Workbench85 PASS、validator25 PASS／0 FAIL／4 SKIP、mypy1124檔與編譯通過（`single_owned_qa_1f84bbaee7a84e71b4abc847e698d1d5`）。加入首頁後的 `targeted_final.log` 為160 PASS／2 FAIL：新增測試誤判 missing/degraded 一律無研究股票，已按既有入口契約修正斷言，未改資格。一次重跑因共享鎖占用以125拒絕，`single_owned_qa_89a2d9dfcb9948d7acd9fdfbe8d8fbe4` 證明沒有啟動 child；不得以此冒稱通過。

修正後 `targeted_verified.log` 162 PASS、`workbench_verified.log` 85 PASS、`validator_verified.log` 25 PASS／0 FAIL／4 SKIP、`compile_verified.log` 通過。`mypy_verified.log` 必跑全範圍1125檔回報其他 Track 新增且不屬本批的 `data_module/revision_custody_relocation.py:152`：`Any | None` 不能傳入 `Path`。保留原 FAIL，不修改該檔、不排除該檔以製造整體 PASS；較早1124檔通過不能取代這個新結果。

`main_accepted125/150` 兩種縮放 first/fresh 均通過；Root 實圖覆核另發現首頁市場／待辦多行說明會被垂直壓縮。已將結論與說明的垂直 size policy 改成 Minimum；最終 `main_verified125/150` 兩種縮放 first/fresh 均通過，新增三尺寸 `height >= heightForWidth(width)` 文字高度斷言，原保存／下鑽／返回旅程保持。Root 已看最終125% 1280及150% 1500首頁，沒有原多行切半問題；首頁截圖按 first/fresh 分開保留。本輪總執行器 `single_owned_qa_6a10686506bd4ed78951a0a6675e7279` 的 Job 自然排空與handles／鎖收尾通過，只代表程序與GUI收尾，不能取代上列mypy的明列FAIL。

仍可安全改善的下一批：首頁「其他待處理」卡占整列、題材與最近研究距首屏較遠；A3–A5沿既有成果繼續以真實畫面裁定，不宣告整體 UX 完成。Native 停止、Owner 未驗及固定 EXE 不含此增量保持。

## Track A A2 首頁資訊層級

基線 `1bf874e2`，沿同一 Track task；此批只修改 Workbench View、兩份定向測試及必要文件。沒有改 `main.py`、共享 DTO、Reader、來源身份或金融計算。首頁沿現有 snapshot signal 及回訪 callback，沒有新增資料服務。

- 四張主要卡片的動作與狀態共列；「其他待處理」改為跨欄短列，窄窗依序排列。結論、缺件與完整原因保持。
- 題材及最近研究靠近主要卡片並列，窄窗上下排列。額外查股／工作區捷徑放在可展開的「更多研究入口」，不觸發讀取或計算。
- 題材卡顯示所選版本日期、完整覆蓋題材數／總數、相對高低端原漲跌幅及每列成員覆蓋。沿既有高／低端 presentation；全部下跌時不將高端改稱上漲，部分覆蓋的極端值不取代完整列，單一完整題材不作雙端比較。Unknown 不補零。
- 最近研究沿既有時間軸原件與日期；移動元件不重讀、重排來源或改寫 Journal，重複 mount 不重接相同 callback。

最終程式防線原件 `*_a2_signoff.log`：194 定向 PASS、85 Workbench PASS、validator 25 PASS／0 FAIL／4 SKIP、1125檔 mypy PASS、編譯 PASS。含候選資料日／來源品質與市場日期分列、缺日保持未知的回歸。兩個既有 annotation-unchecked 提示保持；上批 mypy FAIL 原件不改寫。首次 A2 啟動因可用RAM約5.4GiB，以125拒絕且無child；後繼保留原8GiB／12 process及啟動前8GiB門檻，自然排空後才啟動下一輪。

最終 `main_a2_signoff125/150` 於1280×760、1500×900、1920×1080通過缺件首頁、明示QA題材／多候選snapshot、原報告保存／下鑽／返回及新程序回訪，worker0。總執行器 `single_owned_qa_bed44e1cd4e2422892410a63d7e5b37d` 的 Job 自然排空、handles與鎖收尾正常。Root實看125%1280候選、150%1500題材及125%1280新程序最近研究：日期、原值、分母／Unknown與候選明選保持，狀態標籤不再隨按鈕拉高。候選可用時以原選單／原結果入口為優先，1280題材較下方須捲動；沒有候選時題材高低端可同屏完整讀取，不宣稱所有資料情境皆免捲動。

task／Coverage／功能地圖結構與新增QA錨點檢查通過，原件為 `metadata_check_a2.json`、`task_check_a2.json`。檢查只證結構及紀錄，不代表重驗全庫歷史正文或金融資格。

新增多候選畫面檢查曾因測試fixture的匯入路徑缺件而FAIL（`main_a2_final125/first_result.json`），原FAIL保留，未歸因為產品資料或來源失敗。已補檢查器的測試路徑，產品程式不因此更動。所有題材、候選及模型正向fixture皆明示QA示意，不能代替真來源資格、當日市場判讀、自然排程或金融接受。正式行情只沿具名隔離副本，Native停止、Owner未驗與固定EXE保持。

## Track A A3 原證據比較與結果操作

本批承接 `a37caeaf`，驗證期間共享HEAD前進至 Track B 的 `7f34b074`；不修改其資料、Forward、排程或校準檔案。Root依序履行Execution、QA、Documentation及UI設計／契約複核，沒有獨立reviewer。只改Qt呈現、相應測試與手冊；Reader、DTO、金融計算、來源資格、Main接線與固定EXE不變。

| 需求 | 實作與有界證據 |
|---|---|
| 原理由可掃讀 | 兩類比較共用純文字支持／反證／未知分區，選股票欄或規則格時同步原文；未提供反證不解讀成無風險。HTML形狀的原文仍是純文字，換選不沿用上一股。 |
| 原條件、日期與分母 | AND／OR、規則狀態、代碼／候選清單範圍及來源納入／宣告分母就近顯示。價格上下限含／不含、未知政策、各欄時鐘及原分子分母保留；不將來源宣告數稱為全市場分母。 |
| 掃讀與查證 | 比率只在展示層明示「約」並顯示四位小數；精確Decimal、理由及pins完整保留於可展開原查詢稽核。版本列短碼有完整身份可查；不重算比率、訊號、報酬或評級。 |
| 比較入口與容量 | 技術母體讀取／加入比較／比較／收藏在結果表上方；五行母體摘要收成三行，原數字、Unknown、來源範圍及頁數未移除。價格比較原UI的5欄拒絕與Reader既有256上限不一致，已沿同一常數；真Reader六欄用不同Query核過最末欄返回及水平捲動。未驗完整256欄效能。 |
| 對話框可讀 | 來源捲動區透明樣式原會沿父系影響比較對話框；只在兩類比較對話框套局部不透明背景。價格比較直接在該對話框建立，避免換父容器後殘留透明樣式；無效比較仍保留舊結果並清除新建隱藏對話框。 |
| 原版本返回與保存 | 正常Main按原比較按鈕開五規則對話框，返回第二欄的原Query、原選列及兩筆比較籃。價格比較以Reader發行結果進既有Main槽，返回第二欄缺價股票及原價格Query；原報告筆記保存、下鑽／返回與新程序回訪保持。 |

最終原件在 `output/tasks/track-a-ux-20261022-01a164e6/`：`targeted_a3_final.log` 40 PASS、`native_v4_a3_final.log` 8 PASS、`workbench_a3_final.log` 85 PASS、`validator_a3_final.log` 25 PASS／0 FAIL／4 SKIP及`compile_a3_final.log` PASS。8項原View只涵蓋所列小樣本、來源時鐘、保存、輸入與合作式取消，不重標先前兩個257股案例為通過。

`main_a3_final125/150` 各以1280×760、1500×900、1920×1080檢查正常Main的來源動作、比較表、原條件／日期、來源稽核與返回；first/fresh均通過、worker0。Root已看125%1280的兩比較及首屏選股結果，直接Qt擷取背景alpha255、沒有舊透明文字殘影，來源按鈕與結果首列完整可視。原選股來源來自三股合成隔離保存樣本，價格比較另用四股合成隔離capture，其他模型示意沿前批明示QA身份；不授正式金融或全市場資格。總Job收據 `single_owned_qa_2cdbb5ffaf3d4e61bfd6ba72e3006585` 自然排空、handles關閉及共享鎖釋放；其退出0只代表GUI／程序收尾，不取代下列mypy FAIL。

必跑全範圍mypy保留失敗：早輪為其他線 `forward_performance_service.py` 的2項錯誤；最新 `mypy_a3_final.log` 在1127檔中回報 `data_module/recommendation_calibration_source_contract.py` 的16項型別錯誤。未修改、排除或以局部PASS掩蓋這些檔案。早期 `main_a3_01/02` 功能通過但比較圖有透明底，不作最終視覺證據；繪製診斷曾因PySide render overload及診斷路徑替換錯誤失敗，原輸出與退出碼保留，後繼直接Qt grab驗證，不後製圖片。

仍待A3續作：目前總選股的母體漏斗投影尚未涵蓋v4的flat counts結構，已核來源首屏仍可能顯示漏斗未提供；原來源頁的日期／宣告分母及結果均可讀。本批沒有用可見列數推算此漏斗，後續只可沿既有公開計數修正展示。A4／A5繼續依真實畫面與原結果裁定；Native停止、Owner未驗、正式來源／金融資格與固定EXE保持。

task／Coverage、功能地圖結構及新QA／手冊錨點檢查通過。`context_a3.txt` 的4500字預算略過 `current/decision_research_portfolio.md` 的完整選中正文；另核該冊原件返回與UI／application模組責任，未宣稱重讀全部歷史／策略正文或全庫EOF。

## Track A A3 扁平母體計數

修正共用選股摘要未辨識 v4 頁面扁平 `counts` 的缺口：沿原 Reader 的宣告、納入、已處理、待處理、排除、已處理缺資料、待處理缺資料七項計數展示，不以當頁列數推算、不合成三態分區。缺資料缺值、負值或布林維持未提供；原查詢截至日及短查詢身份保持。單純計數並列，領域三態仍各自列出；畫面明示各項可能重疊，原來源頁保留未知規則股票數與完整稽核。沒有改 Reader、DTO、來源取得或金融計算。

`*_a3_counts.log`：編譯、43項定向、8項原 v4 小樣本回歸、Workbench85、更新頁25 PASS／0 FAIL／4 SKIP及全範圍mypy1127檔通過。前批16項型別失敗原件保留，這次只代表當時共享工作樹通過，未代改其他線。

隔離正常 Main 的 `main_a3_counts125/150` first／fresh均通過：原筆記保存、新程序回訪、比較下鑽與原Query／選列返回，worker0；三種尺寸的比較操作保持。Root檢視兩縮放1280×760的選股原圖，七項計數與操作／三列樣本可見。來源為三股合成保存樣本及既有四股capture，不授正式金融資格；原市場缺件仍降級。`single_owned_qa_ef61f4838b9d48499bf72bf6a8b62a4f` Job自然排空、handles關閉、共享鎖釋放；後繼125%補圖只補最後「各項可能重疊」文案，不改數值或流程。

A3先前的flat counts缺口已關閉；A4／A5仍待續作。Native GUI保持停止、未重建EXE、未push。

最終125%文案補圖 `main_a3_counts_final125` first／fresh通過，Root已檢視1280原圖；補編譯及task／Coverage／metadata／新錨點通過。收據 `single_owned_qa_41802f5e292a43e1bb2bef4520e16bb5` 自然排空、handles關閉及鎖釋放；此結構檢查不代表全庫文件EOF或真人驗收。

## Track A A4 題材指標與成員對照

題材詳情改為寬窗左右並列原九項指標及成員，低於1050寬改垂直；可調分隔器、原表捲動與全部欄位保持。詳情標頭就近列原日漲跌、覆蓋分母與資料日，精確值保留提示。明選成員後可按「研究選取股票」，沿原 `stockSelected`／`ThemeMemberNavigation`；不自選首檔、不改成員順序，忙碌、清除及關閉會停用。分類依據截短時可看完整提示；清空題材會清除摘要及舊提示。Reader／DTO、金融計算、來源、Main與保存契約均未變。

最終 `*_a4_detail_final.log`：編譯、53項題材／目錄／反查／導航／清除定向、Workbench85、更新頁25 PASS／0 FAIL／4 SKIP與全範圍mypy1127檔通過。正常Main在 `main_a4_detail06125/150` first／fresh均通過，worker0：原讀取器載入三股隔離題材manifest／映射／價格樣本；原均值覆蓋是1/2，未升格為完整覆蓋。1280×760、1500×900、1920×1080及900×760檢查成員按鈕完整可見；Root看過兩縮放1280與125%窄窗原圖，指標／成員／鏈位置可對照，來源與分類原文可查。

同版明按個股下鑽／返回保持原2330選列及導航身份，三來源SHA保持；題材筆記經正常UI明按保存，新程序按原筆記身份讀回並重新載入同版、下鑽／返回。一般報告保存、首頁最近研究及原比較流程亦沿原具名樣本重驗。只有隔離合成來源與原具名行情副本；不授正式資料、金融或歷史PIT資格。最終收據 `single_owned_qa_8c77e963154f45c99b69948859cf223f` 自然排空、handles關閉及共享鎖釋放。

早輪腳本失敗保留：載入方法誤傳known_at、假定首列為2330、假定覆蓋2/2，以及保存題材筆記後仍假定最近研究只有一筆。後繼腳本改依實際公開介面、股票代碼、原coverage與保存身份驗證，沒有改產品契約迎合假定；所有Job均排空。A4仍需核對強弱與圖文對照的高價值缺口，A5尚待續作；Native停止、無EXE重建、無push。

task／Coverage、功能地圖metadata與新QA錨點檢查通過，收據 `single_owned_qa_bb9d55b1de96453eb75df0151654403c` 排空及鎖釋放。`context_a4_detail.txt` 是6500字的bug領域定位摘錄，預算略過歷史 `BALDR_COMPLETION_RESUME_PROGRESS_20261012.md` 2148字；題材設計、操作與當前View則直接核讀相關正文。未宣稱全歷史EOF、全庫連結或真人驗收。

## Track A A4 兩端觀察與原值長條

題材觀察預設「兩端對照（各前兩筆）」，直接使用原 presentation 的高、低端結果，依產業鏈＋題材去重，單一題材／兩端重疊另標；原雙向前五名仍可明選。沒有改 ranking、金融公式、完整覆蓋門檻、DTO或Reader。表格的長條delegate只把原值映射為繪圖幾何：同欄目前列共用絕對值尺度，中線0；正負、零、原顯示文字、完整精度提示及覆蓋數保留。缺值／非有限值不畫條，不從格式化字串推算。缺件後的觀察卡依可用卡數填滿欄寬，不留空欄。

最終 `*_a4_bars_final.log`：編譯、54項Qt／題材／目錄／反查／導航／清除／長條定向、Workbench85、更新頁25 PASS／0 FAIL／4 SKIP及全範圍mypy1128檔通過。方向回歸同時核對原高低前五與兩端去重，部分覆蓋極端值／未提供題材不混入；delegate保留高精度Decimal、負值、零與原文字，非法／非有限值保持未知，實際Qt繪圖可用。

`main_a4_bars_final125/150` 正常Main first／fresh均通過、worker0。沿原Reader讀取七股／六題材隔離樣本，明列正負價差方向，原三檔SHA保持。兩端四筆與原mean_return_pct逐項相等，缺件題材不入列；四種尺寸1280×760、1500×900、1920×1080、900×760擷取初屏與排行。Root檢視兩縮放1280最終原圖及125%窄窗：日期、兩端標記、原數值、覆蓋及共用零線可讀；缺件提示保留，沒有不透明文字殘影。排行低端點選可定位原題材，成員明按下鑽／原選列返回、筆記保存與新程序原identity回訪保持。一般報告／原比較也沿既有具名行情副本重驗；合成樣本不授金融或歷史PIT資格。

最終收據 `single_owned_qa_969d189313fe49a99f6e727a3eb3414b` 自然排空、handles關閉及鎖釋放；早輪 `main_a4_bars01` 功能亦通過，僅後繼消除觀察卡空欄，原輸出保留。其他線同期提交資料receipt／lineage，未stage或修改其檔案。A4強弱圖文缺口已具體改善，接續A5已有成果呈現與全目標證據核對；Native停止、無EXE重建、無push。

task／Coverage、功能metadata及新QA錨點通過，收據 `single_owned_qa_8183e92bdbad43b591fdfbaf791c74ff` 排空、handles關閉及鎖釋放。`context_a4_bars.txt` 是ui領域Level2的6份摘錄、2726字，Unknown清單為空；這只代表該次定位摘錄沒有略過，不代表全庫文件EOF、全連結或真人接受。

## Track A A5 單股原結果圖卡與權益預覽

單股「實驗摘要」新增原總報酬、原最大回撤、完成配對與原費率假設圖卡，完整文字／交易明細仍在下方。圖卡直接讀原DTO或保存payload；已宣告的原指標契約沿既有解碼器核對，unavailable零不顯示為已觀測零，契約錯誤保持未知。無契約舊原摘要明示未核契約，不升績效資格。費率不等於扣款合計，不推算成本或淨報酬，修改草稿99bps不污染原14.25bps。完整來源及運算假設可展開，原Main／Reader／DTO／金融公式／保存契約未改。

同筆原權益預覽只讀原equity與日期欄／索引的最近120筆，顯示筆數／原分母及原列順序；缺值留斷點，游標顯示精確原值。沒有計算報酬、回撤或基準。圖卡與預覽放在同一原摘要頁；詳細圖表另有來源選擇器，故不把原摘要圖卡留在其上，避免視覺暗示跨來源配對。寬窄窗重排；900寬沿原「查看實驗結果／編輯回測設定」流程。

最終 `*_a5_cards_final.log`：編譯、35項原結果／參數快照／歷史卡／格式／原曲線定向、Workbench85、更新頁25 PASS／0 FAIL／4 SKIP及全範圍mypy1131檔通過。測試核對精確原比率、真零、未知、契約unavailable零、錯誤SHA、原cost快照、原Frame不變、120筆界線、原日期欄及缺值斷點。早輪全範圍mypy曾因其他線tpex_daily_price_backfill.py:152失敗，原件保留，未代改該檔。

`main_a5_cards_final125/150` 正常Main first／fresh均通過，worker0。原fixed策略1.0.0 executor／broker在90筆隔離合成OHLCV實際執行，原performance analyzer產出結果並以既有Registry保存API寫入正常Main隔離命名空間；Main經有界exact Reader重開，metadata SHA與保存原件一致，讀回不變。這不是手填收益，亦不代表真實2330行情／績效或PIT資格。沒有重跑回測保存按鈕的對話框；本批保存驗證用原Registry API及Main真讀回，原Journal筆記的正常UI保存、原選列返回與新程序回訪另隨同驗證。

1280×760、1500×900、1920×1080、900×760在穩定Qt事件循環後檢查四圖卡與原曲線完整可見；Root看過兩縮放1280及125%900原圖，日期底端、負報酬、回撤、配對、費率與曲線均可讀。原完整假設可展開，詳細圖表頁不沿用摘要圖卡；不以早輪白色未載圖表當作接受證據。早輪亦保留Registry命名空間、缺顯式讀取預算及900設定單欄尚未切到結果的腳本失敗；後繼依原服務、預算與既有結果按鈕驗證，未繞過守衛。最終輔助expected檔的metadata SHA改用原canonical helper並核對Reader身份，早輪未採用的輔助欄位不作身份證據。

最終收據 `single_owned_qa_9c183f1920554b66b4fdf0cf15692c7f` 自然排空、handles關閉及共享鎖釋放。Native停止、無EXE重建、無push，金融資格不提升；仍需逐項核對Journal／策略比較及A1–A5全目標證據，不以本批通過宣稱整個平台完成。

task／Coverage、功能metadata及QA／手冊錨點通過，收據 `single_owned_qa_dab6a9a7a3464096b2f368414b0e3d63` 排空、handles關閉與鎖釋放。`context_a5_cards.txt` 的6500字預算略過 `current/decision_research_portfolio.md` 完整選中正文6798字；該冊相關責任已在前批定位，本批另直接核對原指標契約、保存payload、Qt callback及操作正文。不宣稱重讀整冊／全歷史EOF、全庫連結或真人驗收。
