# Baldr V2 產品驗收

本文件記錄依 [V2 Blueprint](../superpowers/specs/BALDR_V2_PRODUCT_UX_BLUEPRINT_CONSOLIDATED_20261020.md) 開發的 Source 分支證據。基線 `9ce92743`，分支 `codex/baldr-v2-product`。已有本機技術候選及分階段驗證，最新整合候選與限制見下節；完整五旅程仍為 PARTIAL，既有固定研究13不包含本輪變更。

## 自動化優先與四軌驗收（2026-10-21 Owner override）

交付先讀[一頁式摘要與截圖](BALDR_V2_AUTOMATED_ACCEPTANCE_20261021.md)。本節的來源版 RC 判定只涵蓋明列的研究功能與安全缺件出口，並非完整五旅程所有分支或金融資格接受。

Owner 已覆蓋先前真人等待規則：日常開發、Milestone 與 RC 準備不以 Owner 親自操作為前置條件，不逐包索取真人操作收據。下方舊紀錄的 `MANUAL_ACCEPTANCE_PENDING`、`PARTIAL`、`full_product_accepted=false` 保留原意與原始結果；它們不再單憑 Owner UAT 未做而阻擋可獨立工作，也不因新政策改寫為已通過。

每個 Milestone 分列 `CODE_AND_CONTRACT_VERIFIED`、`AUTOMATED_GUI_E2E_VERIFIED`、`NATIVE_WINDOWS_SMOKE_VERIFIED` 與 `OWNER_UAT_NOT_PERFORMED`，前兩者必須附版本、資料與實際動作範圍。Native 的有效停止指示仍為 `USER_STOPPED_ESCAPE`，因此第三軌結果為 `NATIVE_SMOKE_NOT_EXECUTED`，不能以離屏 Qt 事件、mock 或合成測試代替 Windows 原生桌面驗收。第四軌為 `OWNER_UAT_NOT_PERFORMED`，不作日常開發／RC blocker。正式金融來源、PIT、Forward 成熟度及 Paper 正向建帳資格仍分開判讀。

只有宣告完成的功能具必要自動化證據、沒有未解重大安全／完整性缺陷，且缺資格功能安全隔離、Native 限制明示時，才可在明確範圍使用 `PRODUCT_RC_AUTOMATED_VERIFIED_OWNER_UAT_PENDING`。來源版 `b8ed339f` 與固定 `eefd2163ad95` EXE 分開記錄；後者未包含兩項鍵盤修復，不更新原包內收據來冒稱新版本。

R201–205 沿原始結果重新核對五旅程。Workbench 正向線索的入口需要 reader 原有 `latest_status.json` 及相符 typed candidate；R67 的10/19／1512保存推薦只經推薦頁 reader，原 restore manifest 沒有該首頁狀態原件，不能注入 DTO 或改路由冒充完整首頁線索旅程。此資料分支仍未驗；可使用的保存研究回訪不受影響。QA148 frozen 的正確結果為 task `r134_frozen_comparison/r179_report_fresh_result.json`，20個 `PyiFrozenLoader` 模組、建帳停用及原件／latest／Timeline往返已驗；`r148_paper_prerequisite/r148_result.json` 是較早 standalone MainWindow 結果，不是該 frozen run。

### M0–M5 四軌結果

前兩欄的「已驗」分別表示 `CODE_AND_CONTRACT_VERIFIED` 與 `AUTOMATED_GUI_E2E_VERIFIED`，**僅限同行範圍**；不把缺資料的正向分支寫成通過。Native 欄記錄 `NATIVE_WINDOWS_SMOKE_VERIFIED` 軌的實際未執行結果，Owner 欄獨立記錄未做 UAT。

| Milestone | 程式／契約 | 自動 GUI E2E 的實際範圍 | Native Windows | Owner UAT |
|---|---|---|---|---|
| M0 恢復 | 已驗：唯一 root、既有成果／來源 pins、Git與恢復點 | 不適用；工程恢復不是 GUI 旅程 | `NATIVE_SMOKE_NOT_EXECUTED` | `OWNER_UAT_NOT_PERFORMED` |
| M1 Shell | 已驗：既有導航／來源返回及兩項鍵盤修復；QA158／159 | 已驗：QA162 真 `main()` 17路由／四尺寸；QA159 Ctrl+K、Tab／Shift+Tab及typed價格返回 | `NATIVE_SMOKE_NOT_EXECUTED` | `OWNER_UAT_NOT_PERFORMED` |
| M2 探索／個股 | 已驗：既有題材、價格來源、Query／收藏與歷史身份守衛 | 已驗：QA075／103題材受限切片、QA090雙股比較、QA148／159歷史／最新回訪；月營收正向仍未驗 | `NATIVE_SMOKE_NOT_EXECUTED` | `OWNER_UAT_NOT_PERFORMED` |
| M3 投資／策略 | 已驗：Journal／帳種隔離、Paper拒絕與baseline非法值守衛、Registry相容性；QA124／128／137 | 已驗：QA148保存原件／Paper安全出口；QA033／036回測保存重開；QA164目前Main比較功能切片，整輪FAIL另列；正向建帳未驗且停用 | `NATIVE_SMOKE_NOT_EXECUTED` | `OWNER_UAT_NOT_PERFORMED` |
| M4 總覽 | 已驗：原readmodel、最近研究引用及來源不足拒絕 | 已驗：QA075保存研究回訪；QA162實際首頁缺件出口。**正向首頁線索入口缺原狀態檔，未驗** | `NATIVE_SMOKE_NOT_EXECUTED` | `OWNER_UAT_NOT_PERFORMED` |
| M5 交付 | 已驗：既有eefd包同版／啟動器／pins；目前來源鍵盤回歸 | 已驗：QA148／152固定包有界功能，QA159／162目前來源；兩版本不混稱同版 | `NATIVE_SMOKE_NOT_EXECUTED` | `OWNER_UAT_NOT_PERFORMED` |

### 本輪真主程式與 Registry 證據

QA161 以既有 document_control 定位release角色／文件範圍；Context預算略過Snapshot片段，Root另讀目前頂端狀態，不把related_paths清單視為全核讀。QA162 R207透過正式 `ui_qt.main.main(application_settings=..., startup_controller=...)` 啟動，17個路由在1280×760／DPR1.25，以及1500×900、1440×900、1920×1080首頁全部完成，`main_exit_code=0`、errors空、worker／pool0，Main自行deferred-delete後視窗失效。R181價庫、R42四個index與7份產品檔前後保持；Root已看首頁截圖。實際 WorkbenchDailyEvidence 為 missing，兩個候選／保存結果按鈕停用並明示缺件，不算正向線索成功。台股決策日按臺北時間顯示，與本交付的洛杉磯日期分開。closure `08a1ca5f91f13d21a053432abd88ea3e1c8b9d447582a629ae49b5bcdbaec55f` 自然全閉。

QA163 R206首次Registry補驗在初始化時被未canonical化的repo output junction路徑拒絕，尚未比較，整輪FAIL保留；closure `bdd31d4e01b491d1f32aa2897c495aeed714ae51dbcdab5fcd2c65f7372e4b87` 自然全閉。原result的source-unchanged為false，是初始化先失敗而baseline未寫入result；Root另按expected preflight逐key核8個來源的bytes／SHA與檔集合全部相同，沒有改寫原旗標或FAIL。

QA164 R209以物理路徑與正式ApplicationSettings重驗，目前來源Main使用真ResearchRunService的fixture配置，只有三個Registry讀取路徑指向既有R09原件，其他輸出都在新CASE；不是產品新增任意root功能，也沒有mock Widget、改metadata或新增run。相同MA pair精確顯示120共同日／240權益列；MA／RSI pair由原元件拒絕「資料指紋不同」，再恢復原overview／原選取。原run metadata、8個來源DB／Parquet與Registry DB SHA全部保持，CASE外寫拒絕清單空、worker0。

**QA164整輪仍為FAIL，僅接受上述功能切片。** 唯一isolation error來自import時 urllib3 `_has_ipv6("::1")` 嘗試 `socket.bind(("::1", 0))`，被原網路守衛阻止。已核實address／family／call stack；沒有放行該socket、connect或外部傳輸，不宣稱零socket嘗試或整輪隔離PASS，也不為分類再造CASE重跑。closure `af9236afa9d1992d831d1be06445a674d4259c5e69e959bbfe93c7025417cd27` terminal1、三PID陣列空、handles關閉及mutex釋放，無強制回收。這是已定位的測試初始化探測限制；在宣告的唯讀比較功能中，未觀察到原件寫入、非法比較接受或資料完整性破壞。

Root據既有必要回歸、上述真GUI動作與來源完整性，將**本機來源版已宣告研究功能**列為 `PRODUCT_RC_AUTOMATED_VERIFIED_OWNER_UAT_PENDING`；不表示完整五旅程所有分支已完成、沒有任何未知缺陷、可正式發布或取得金融資格。月營收／Paper與正向首頁線索仍按各自缺件隔離；Native與Owner未執行不能單獨阻擋這個限定候選及後續安全開發。沒有產品程式改動，因此重用QA158／159既有必要回歸，不重跑Common；沒有新建Trial／EXE或改寫舊包收據。

## 來源取得與獨立自動驗證（R188 起）

Owner 明示真人驗收標為「等我有空」，不阻止其他安全工作；Native `USER_STOPPED_ESCAPE` 維持，沒有恢復桌面輸入。Root 分派 Luna 唯讀月營收、Paper 取得鏈及自動 UI 缺口盤點；不建立來源 binding、來源接受收據或合成金融資料。既有 `eefd2163ad95` 候選及 canonical 交付收據不變，完整五旅程仍 PARTIAL，真人仍未通過。

| 範圍 | 可獨立完成的事與實際發現 | 仍需的來源／核准或工程 |
|---|---|---|
| 月營收官方 OpenData | 上市[資料集18420](https://data.gov.tw/dataset/18420)、上櫃[資料集56510](https://data.gov.tw/dataset/56510)明列免費與[政府資料開放授權第1版](https://data.gov.tw/license)，遵守顯名條件的該等開放資料不需另取供應方書面授權；不推廣為其他即時／商用資訊權限。QA154 已做兩個固定官方 JSON endpoint 的記憶體內工程觀測。 | 官方欄位可取得不等於 Main 的既有 MOPS source contract、來源用途接受或歷史 PIT。 |
| Main 月營收 current-only | `daily_monthly_revenue_cohort_binding.py` 精確要求 `mops.monthly_revenue_static_snapshot`、`mops-current-revenue-normalizer.v2`、`mops-static-snapshot.v2` 與 `recommendation_current_fundamental`；`daily_source_snapshot.py` 的 `daily-hour.v1` 可在缺官方 timestamp 時，以成功批次完成後的小時保守判定可用時間。`daily_monthly_revenue_series.py` 明示 historical／formal PIT false。 | 需要真實、相符的 `DailySourceUseAcceptance` 用途證據與可信外部 binding／SHA。現有 serializer／create-only writer 不等於可用的正式發布 CLI。不能把 OpenData 改標為 MOPS，或為 current-only UI 強加完整歷史 PIT 前置條件。 |
| P0 研究取得與治理 | `V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md` §12–13 已記 bounded foreground、官方來源、TEMP/research-only 的既有 Owner 授權；此研究取得能力可獨立前進。 | P0 TWSE／TPEx `monthly_revenue_announcement` 的 source IDs 與 Main current-only 不同；其 applying revision DB 路徑由 caller 提供，當前未定位，保持 UNKNOWN。8月歷史 `not_supplied` 不證明目前仍未批准，也不是 Main binding 的必要 DB 依賴。 |
| Paper 行情 | 既有 `paper_event_source_capture.py` 可在真實台北當日 regular session 內擷取 quote observation，具有日期、symbol／venue 與來源核對；它不產生 fill 或證明成交事件。官方 OpenAPI、盤後商品與需契約的資訊服務按用途分開核對。 | Owner 尚未指定供本次使用的同日合格行情／mark 來源與收據；公開收盤資料不能直接充當 session execution event。 |
| Paper 帳戶與現金 | 原前置條件與只讀 readiness 可用；策略帳戶 manifest 綁定精確策略／policy／cost／benchmark。 | 通用「已保存研究→Paper帳戶」producer 尚未實作；另缺帳戶／策略版本、Owner 指定的本金／幣別／起始日、相符現金與持倉來源及存放範圍。此流程不需要券商登入憑證，不用研究股價、benchmark、成交CSV或既有策略500K seed補齊。 |

QA154 R193 只對 TWSE `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` 與 TPEx `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O` 各做一次 GET，每端點最多 2 MiB／8 秒、無重試、最多一次同主機 HTTPS redirect；沒有保存 response、輸出金融列值、建立 binding 或來源接受收據。實測皆 HTTP200／JSON list，分別 607,634 bytes／1,088列及496,597 bytes／893列；各14個欄位且無非物件列，欄位包含出表日期與資料年月，未提供逐筆官方發布 timestamp。這是當次連線與結構觀測，不驗證營收數值、來源完整性或下游資格。Web 工具先前不能讀端點只代表工具限制，本次受控 direct GET 已實測可讀。Job closure `7f948fe2a962ed8eb1d8fbc7f9ad55f8dbca21d6686bd7cdb17dd92223d0e3d7` 自然全閉，8 GiB／12程序不變。

R190 另定位兩個未覆蓋的 frozen Main 自動切片：真鍵盤 shortcut／子頁啟用，以及共用「儲存篩選條件」到原 writer 的單次保存與 strict 重讀。它們使用既有受限來源及隔離狀態；實際執行結果另記，不能用 helper 存在或單元測試通過替代。

QA155 R191 原始 FAIL 保留：Ctrl+K 由非搜尋控件出發後正確聚焦；後續 helper 誤要求 Tab 在互斥導覽組內直接換另一按鈕，並將落盤 `research_bookmark` mapping 誤認為 typed DTO。真正 Save 已確認且 CASE 寫入一筆 `technical-universe-bookmark.v1`，但尚未完成 strict 重讀與 Alt+Left，不將該輪寫成完整 PASS。R194 獨立靜態複核另補足返回前後外層工作區／來源 frame 守衛。Root 對照本包 Qt6.10 的[官方按鈕實作](https://raw.githubusercontent.com/qt/qtbase/6.10/src/widgets/widgets/qabstractbutton.cpp)：互斥組只有當前焦點按鈕保留 TabFocus，方向鍵可選取同組按鈕；收藏應沿 `WatchlistService.get_research_bookmark()` 解碼，再由 strict reader 核原來源。R195 只修新隔離測試，不改產品或重建候選；實際重驗另記。QA155 closure `857dce810e29bd68c2fa5271723ff23e6d229cdda1e603bfd944c60cab640eb4` 自然全閉、來源／價庫／產品 pins 保持，沒有 Native 輸入。

QA156 R195 仍為 FAIL，原證據保留。Ctrl+K 通過，但 Tab 探針在 `recommendationResultScroll` 焦點重複時提前停止，不能據此判定整個子頁不可達或聲稱完整鍵盤驗收通過。收藏則已經過真 writer 寫入，codec 解碼成功；helper 誤用不存在的 mapping `bookmark_id` 鍵，正確落盤識別為 `bookmark_identity_sha256`，因此 getter 收到空身份，尚未到 strict 重讀與返回檢查。產品與候選不變，來源／價庫／index pins 保持，worker／pool0並自然刪除視窗；closure `7db1d38948478836f7dfab7f76ee2f9eaab9f8720c3a185201d782f778fa0ce4` 三 PID 陣列空、handles 關閉及 mutex 釋放。R196 另修獨立 helper 並延長有界 Tab 追蹤，後續結果另記。

QA157 R196 已完成共用 Save 的原 writer 單次保存、既有 getter／codec 解碼與 strict reader 核原 query／source／row；條件範本 dirty 狀態阻擋再次保存，原查詢／選列與一筆收藏保持。Ctrl+K、獨立焦點 fixture 下的子頁方向鍵／Space 通過；完整 Tab 未通過，64步仍未從捲動區到子頁。整輪最後在真價格詳情的 Alt+Left 返回逾時，故保留 FAIL，不把前三個切片外推為整輪成功。原來源／價庫／產品 pins 保持、worker／pool0自然刪除；closure `7b0d01cf558f4570ca63f61182478e9d4df019c98ff6821499c9a265de720f2a` 自然全閉。

R198 獨立靜態複核找到價格快捷返回的確定契約錯配：Shell 無參數發出 `Signal(object)`，且未沿詳情頁原選取配對核驗。來源修復改點擊原返回按鈕，保留核驗、typed selection 與 Main 原來源恢復鏈。QA157 未記 shortcut activated，故不能僅憑該次逾時宣稱已觸發此缺陷。R199 另以 `WorkspaceSubnav.set_tab_predecessor()` 明接搜尋按鈕與目前啟用子頁，切換路由／重建按鈕組時維持單一 Tab 停駐點；不改原生方向鍵行為。新增回歸只用非金融 object identity token 與實際 Qt 訊號核接線，不另建金融 fixture。這兩項修復由來源版驗證，既有 `eefd2163ad95` EXE 不包含，未因小修重建候選；QA158 及真 Main 鍵盤結果另記。

QA158 四檔編譯、29項定向、85項 Workbench、更新頁25通過／0失敗／4略過及 mypy1108全通過。closure `b0e6626bf971dc4ced5d88f203dc247cbe4e57518c8bdd08607c7842468a53fa` 自然全閉。測試檔後續只有28 bytes排版調整，QA159按最終 bytes 另編譯並重驗該檔13項通過，未重跑 Common。

QA159 R198 正常來源 MainWindow（非 `main()` entry）在1280×760／DPR1.25通過：Ctrl+K由搜尋按鈕聚焦輸入欄，Tab到搜尋鈕、再到目前選股子頁，Shift+Tab回搜尋鈕；真 R42 PriceView 明選／查詢／2317 typed detail 後，從可見且啟用控件發送 Alt+Left，shortcut activated與詳情／工作區兩層訊號各一次，傳遞同一 selection 物件。Main恢復原 query `5fe8208c0fbe31fff07d3bf419016aac0b1c33e97e35959ad2012bfc14fdcb90`、page `41ebd7806b77436c1244db9b90cdbe428d81755e366ee6e1759aa5aeea767d62` 與2317原列，來源 frame 清除；Root已看返回畫面。R181價庫 bytes／SHA、R42四個index與產品 source pins 保持，availability unknown／historical及formal PIT false。這是離屏 Qt 事件自動檢查，沒有 Native 輸入或真人接受。

QA159 closure `85e52f3fb923385bc012f70160afc71b573cd5f3378e93e71849c94f93b61345` terminal0、三 PID 陣列空、process／Job handles關閉、mutex釋放，worker／pool0並自然刪除視窗，未強制清除。原QA155–157 FAIL均保留；六份既有候選及兩份canonical交付收據 SHA `87cadb86f01fc45838bfa05d355c776c9359a7d283257ce2ee5a28784f6ca4d6` 保持，未build或替換試用入口。來源／UI缺口盤點及兩個實際修復完成後，本輪尚未找到其他無需新金融契約、正式輸入或真人操作的具體修復；未將受限來源、工程測試或公開結構觀測當作真來源／完整V2驗收。月營收用途接受與binding、Paper帳戶／行情／現金及通用建帳契約仍具名受阻，真人標記「等我有空」，Native停止與五旅程PARTIAL保持。

## eefd2163 整合候選（QA144 起）

來源固定為 `eefd2163ad956d906d9f884a9b46f9e2f8661538`，版本 `2026.10.21+eefd2163ad95`，候選 `dist/candidate_eefd2163ad95_873638e9/baldr`。這次集中封裝 Paper 前置檢查、baseline 未知值拒絕、統一保存入口與 V4 dirty gate、保存報告／價格詳情另開最新及精確返回、Journal 唯讀修復；下方舊段落的「a65 不含」仍是各原版本的歷史界線。

QA144 建置及 QA146 封存來源／EXE 同版比較通過；EXE 57,157,707 bytes，SHA-256 `32bbfd46055494fa585959984fded67cd7604b0cf34df662c3e11a978f6c01c9`，BUILD_INFO SHA-256 `926f2348994a9b4ccf9c36f775fac234107475b26e80a6e8bfce50546cd1a929`。沒有因後續工具修正重建候選。

QA148 R179 在真正 frozen Main 執行保存報告→獨立最新→同 saved view／snapshot／context→原 Timeline 選列，再讀取現況對照；同時驗證 Paper 前置對話框建帳停用。另一程序以原 R42 strict 來源建立 PriceSelectionV1，完成原查詢→價格詳情→最新報告→原詳情→同 query／page／2317 列。報告 20 個、價格 10 個產品模組均由 PyiFrozenLoader 載入，無工作樹 fallback；Root 已看七張完整主視窗圖。R134 三份原始 JSON、Journal、R114 四來源與 R42 index 保持，worker／pool 為零並自然刪除視窗。報告為 1280×760／DPR1.5、價格為 DPR1.25；部分來源缺件明示，不作完整行情、金融資格或 native 接受。

QA147 材料組裝通過；QA150 啟動器 prepare／check 與錯 EXE SHA 拒絕通過。新 `r181_candidate_state` 僅準備一次固定公開樣本，不含私人 Journal；第五個設定鍵明選既有包外 `TECHNICAL_UNIVERSE_READ_ROOT`，R42 只記四個 index pins，不複製 payload 或重跑 producer。這是本機綁定候選，availability unknown／historical PIT false；既有候選與 state 保留。

QA143 參數錯位、QA145 通用 pin 對 dist junction 的前置拒絕、QA147 驗證器長路徑、QA149 命令規格錯漏均保留原 FAIL；後三者未重建 EXE 或重組公開樣本。QA144／146／148／150 均自然閉鎖，三 PID 陣列空、process／Job handles 關閉及 mutex 釋放，維持 8 GiB／12 程序。新候選 125% 路由及交付 pins 另記；完整五旅程、真人與金融缺件不升格。

QA151 R183 在路由前被 CASE-only audit 擋下 `r181_candidate_state/market/daily_price` 初始化，原 FAIL 保留。QA152 R184 沿舊已驗作法，僅預備五個應用標準空目錄，再以新 CASE 驗 17 路由 1280×760／DPR1.25；1500×900、1440×900、1920×1080 僅驗首頁。來源及四個 state 樣本不變，未放寬 inner audit，Main return0、worker／pool0且自然刪除；Root 看首頁與選股圖。closure `7bd3f809f5d0cfff43dcf67bdda2a2f5cec8928ca9c9196c5feb4773db01dea9` 全閉。R185 獨立靜態 review 無交付阻擋，僅澄清 GUIDE：啟動器以內嵌路徑及 SHA 準備樣本，SAMPLE_RECEIPT 是 pins 紀錄；更正後九項材料與 manifest 由 QA152 再核，QA150 原材料 pins 保留不改寫。

本機交付 canonical `DELIVERY_RECEIPT.json` 與 task `delivery_eefd2163ad95.json` 均為 10,733 bytes／SHA-256 `87cadb86f01fc45838bfa05d355c776c9359a7d283257ce2ee5a28784f6ca4d6`，固定 12 個檔案 pins（九材料、材料 manifest、EXE、BUILD_INFO）及五個成功自然閉鎖收據。候選含交付收據為 7,135 files／976,519,308 logical bytes，build 為 5,281 files／315,749,973 bytes；與前五份合計 7,743,557,105 bytes，僅邏輯檔案大小，非 SSD 唯一配置。六份候選保留，未替換既有指定試用入口、未清理或推送；任務 Credits USAGE_UNOBSERVABLE／UNKNOWN，跨 session 授權不重置。

## M0 與所有權

有界核對涵蓋 Main／導覽、兩種個股來源、選股、題材、收藏、Journal／Forward、真實手動持倉／Paper、回測／Registry、主題與資料更新／Runtime。重用既有服務及保存契約，未發現需推翻 Blueprint 的安全衝突。Root 擁有 Main、Router、共享契約與整合驗收；Luna 分別完成來源盤點、投資分區、共用元件、定向測試與文件同步，均未自行執行 Python 驗證。

本機可恢復狀態與逐項搬遷表位於 `output/tasks/baldr-v2-product-implementation/`。原補完任務的狀態、固定包、未完成金融資格及正式資料均保留。

## 前期 M1：導覽與投資分區

Source 已接四主頁、齒輪與一層子頁列；原九工作區 key／callback 保留。共用個股詳情保留主頁高亮及原服務的返回核驗；頁內上一／下一不堆疊來源。搜尋須明選，題材結果綁載入版本，變版或忙碌時拒絕舊選單。投資分區以原 widget identity 保留九個舊子頁，手動／Paper／研究紀錄各有帳種說明。

這一階段是 Shell 增量；以下 M2–M4 段補記後續整合。子頁可到達不等於該里程碑已驗收。

| 驗證 | 實際結果 | 原始證據 |
|---|---|---|
| QA001 編譯／定向 | 編譯 PASS；68 PASS、3 SKIP、4 FAIL。四失敗為新增 Qt 測試替身不支援 weak reference，已修 | 本 task `qa001_focused` |
| QA002 導覽／來源擴充回歸 | 編譯 PASS；89 PASS、3 SKIP、1 FAIL。舊同查詢返回測試仍要求重開 session，與 HEAD 已有精確重讀流程不符；修正呼叫假設，保留來源／頁面／選取核驗 | `qa002_integration` |
| QA003 持倉舊路徑 | 69 PASS | `qa003_required/00_stdout.log` |
| QA003 Workbench 強制回歸 | 85 PASS | `qa003_required/01_stdout.log` |
| QA003 validator | 23 PASS、2 FAIL、4 SKIP。QA 的 TEMP 採 C 槽 junction 別名，與 F 槽 resolved data root 不符；改實體 TEMP 重驗，未放寬資料守衛 | `qa003_required/02_stderr.log` |
| QA004 validator | 25 PASS、0 FAIL、4 SKIP；實體 TEMP 解除測試根路徑衝突 | `qa004_integration/01_stderr.log` |
| QA004 指定全範圍 mypy | PASS，1088 source files | `qa004_integration/02_stdout.log` |
| QA004 擴充回歸 | 95 PASS、4 SKIP、1 FAIL。比較返回也沿同查詢重讀；已修正第二處過時 opener 假設，尚未重跑。既有 live-return 測試包含跨查詢重開與原件破損拒絕 | `qa004_integration/03_stdout.log` |
| 正常 Main 原生視窗 | PARTIAL：真正 Main／實際服務、全新隔離根啟動成功，1280×760、實際 DPR 1.5、worker 歸零；已檢視首頁缺件降級。切頁操作前使用者以實體 Escape 停止 Computer Use，本輪不再輸入 | `native005/history.json` 及首頁圖 |
| 五旅程／其他尺寸與 DPI／保存 fresh | NOT_TESTED | 待整合驗證 |

QA001–004 Job 均自然排空，三個 PID 陣列為空，process／Job handles 關閉並釋放同工作區 mutex；8 GiB committed memory、12 程序上限不變。原生 Main 另依既定 240 秒正常關閉，由其 owner wrapper 保存閉鎖收據。原始 FAIL 保留，不以後續 PASS 改寫原收據。

原生首頁發現的全域資料狀態文字擠壓已修，QA013 正常 Main 17 路由寬度皆至少180。原首頁多子頁也已在後續 Source 改為單頁；尚未做原生重驗。

## M2–M4：Source 整合與正常 Main

市場以同一個方向控制切換強弱股／產業，題材只從明確設定或使用者明選的版本目錄載入已完成且到可用時點的原件；歷史 manifest 仍核 exact SHA。綜合選股保留原來源、三態／分母及比較籃，H20 獨立置於 ML 研究；查詢截至不冒稱逐筆資料日。共用個股以章節與動作切換呈現，保存時報告保持獨立 snapshot-only reader。

時間軸沿同一 Journal 與三種 typed note readers 索引原文／修訂，原件回訪先 fresh 逐欄核對；價格再驗原來源，報告只顯示保存副本，題材明選原 manifest。Forward 僅在明載結果身分時連結；500筆是讀取合併後顯示上限，現行 reader 仍全讀，不宣稱來源端有界。策略庫可瀏覽登記及保存版本，只允精確目前版本進入現行回測設定；歷史保存版不偷換成目前版本。

回測保留原引擎、Registry 及拒錯比較，使用平面結果選單；固定假設只讀當次或保存原值，期末／逐日訊號只投影原報告觀測。手動、聲明研究與 Paper 分區保持原帳本，Paper 增加文字及虛線區分。儲存頁只盤點明確位置容量及有界 Trial 大小，引用未核一律保留，沒有刪除操作。首頁重排原 widgets／DTO 為單頁，原證據及進階來源都有明確入口與返回。

| 驗證 | 實際結果與限制 |
|---|---|
| QA006 | 92 PASS／1 SKIP／2 FAIL；既有題材用途文案與原生 thread 終態等待已修；後續定向通過 |
| QA007–009 | 保留新測試語法／Qt fixture／junction根與精確 page placeholder、文案預期等原失敗；QA009為224 PASS／1 SKIP／6 FAIL |
| QA010–011 | task helper pins經junction誤拒後僅允ROOT或本TASK；mypy五項明確型別錯誤已修，原失敗保留 |
| QA012 | compile、mypy（1100 files）、定向測試、Workbench、validator 命令均 return code 0。最後的 offscreen Main 命令 return code 1：市場路由視窗高 821px，超過 760px；此布局失敗後續修正，原收據保留。上一個 mypy 命令成功，不能因最後命令失敗改寫為失敗。 |
| QA013 | compile、market定向5 PASS；正常Main全部17路由在1280×760，另驗1440×900／1920×1080首頁；無modal/errors、workers0。隔離空資料／原服務，沒有替換服務或注入價格；offscreen不代表native |

QA013 closure SHA `bf3f65d99b3ee0450db887746d54b780c7fcc9ae18abe888d1026b447ef04200`。所有本輪 Job 均自然排空，8GiB／12程序上限、handles關閉與mutex釋放保持。正常Main截圖與原始JSON在本task `main013/`；後續個股純自選、來源內比較與一般查股回測預填、新程序保存／回訪正進行 QA014，尚不宣稱通過。

## QA014–020：個股動作、整合回歸與復原

QA014 原收據為 compile PASS、定向測試失敗（`qa014_detail_fresh/02_stdout.log` 保留 105 PASS／2 FAIL）；兩項涉及動作狀態與測試替身 NameError。QA015 原收據為首命令失敗，不能用後續結果改寫原收據。QA016 對個股三項動作的定向測試 PASS（`qa016_detail_debug/receipt.json`），屬局部證據。

QA017 六個 scoped commands 全部 return code 0，包含 Workbench 測試、更新頁測試與 validator、`main_journey.py --phase first/fresh` 及 offscreen Main。`03_stdout.log` 明示一般查股保留價格缺件、報告與判斷保存、fresh 回訪、純自選語意分離、返回時間軸選取及回測只預填；`05_stdout.log` 覆蓋 17 路由於 1280×760、DPR 1.5。兩份 journey 輸出均標 `native_gui_accepted=false`、`financial_qualified=false`。因此可支持旅程1的局部流程與路由狀態，不能替代五條旅程完整 Main、原生 GUI 或真人接受。

QA018 原定向整合收據保留兩個失敗；修正後 QA019 同一測試組因 Windows access violation `3221225477` 中止，兩份原收據均保留。QA020 執行前後各核對 57 個 source pins 相符；後續 source 增量另行驗證。QA020 命令1與2各 30 PASS；命令3綜合選股／官方處置收入組為 11 PASS／1 setup error，發生於 `test_original_view_daily_actor_pages_bookmark_exact_reopen_and_shutdown` setup 的 synthetic capture scope `path_link_rejected`。根因是 fixture 所在 output junction 未 resolve，並不表示應用安全 guard 失敗。spec 後續列出的 Workbench／validator／mypy／journey 命令未出現在此 run receipt，故標為未執行，不推論其通過或失敗。QA020 receipt `full_gate_accepted=false`，整體 V2 尚未接受。外層 owned closure receipt 記錄 Job 已排空、handles 關閉、mutex 釋放且無 forced cleanup。原始收據與輸出仍在 `output/tasks/baldr-v2-product-implementation/qa020_product_integration/` 及 `single_owned_qa_45299e2894ad430c9271eda9b4ed60fd/`。

## QA021–025：修正後證據與仍未完成的出口

| QA | 實際結果 | 原始證據與解讀 |
|---|---|---|
| QA021 | 編譯 PASS；整合測試 12 PASS／1 FAIL／1 ERROR。FAIL 為新測試替身 type 不唯一；ERROR 為舊 fixture 長路徑下 `_tree_signature` extended walk 遇到 `WinError 3`。後續已改用專用測試子類並修正 extended walk，沒有放寬產品 guard；本批沒有重跑 QA021 原測組證明這兩項修正，原收據仍是失敗。 | `qa021_product_integration/00_stdout.log`、`01_stdout.log`；原失敗保留。 |
| QA022 | 編譯 PASS、wrapper 13 PASS、Workbench 85 PASS、validator 25 PASS／0 FAIL／4 SKIP、mypy 1102 files PASS。Main018 first 由 helper 使用不存在的 route key `watchlist` 觸發 `StopIteration`；有效 key 為 `lists`，屬驗收 helper 錯誤，不是產品路由失敗。 | `qa022_required_and_main/01_stdout.log`–`05_stdout.log`；Main 證據 `05_stdout.log`。不把最後一項 helper 失敗回推成前面命令失敗。 |
| QA023 | `main_journey023.py` first/fresh 均 PASS；17 routes 在 1280×760、DPR 1.5、search context 寬度至少 180、worker 0；offscreen Main PASS。該 run 的 R07 journey helper first 因 import audit 拒絕 `NUL` 失敗，原失敗保留，並由 QA024 專用 helper／receipt 接續驗證。 | `qa023_journeys/01_stdout.log`–`04_stdout.log`，`journey023/first_result.json`、`fresh_result.json`、`qa023_journeys/03_stdout.log`（17 routes）。QA023 receipt 有失敗命令，不能稱整個 spec 全 PASS。 |
| QA024 | scoped commands 全部 return code 0：編譯、wrapper 13 PASS、Workbench 85 PASS、validator 25／0／4、mypy 1102 files，以及固定 10/16 三來源副本 Main first/fresh。正常 Main 驗證 25 鏈、90 題材、CoWoS 21/21 個股價量觀測→2330→返回、題材 note revision 保存及新程序 canonical identity 回讀；三來源檔 SHA 前後不變。一般個股行情仍是隔離空資料，故為局部旅程證據，不是金融資格、PIT、native 或真人接受。 | `qa024_theme_and_required/00_stdout.log`–`06_stdout.log`、`main_research_journeys_r07_qa024/{first_result,fresh_result}.json`。closure SHA-256 `384bdf19b4c1438c83d2b6014516134b72665c78b2234cf91d72c9502bba1ee2`，receipt `single_owned_qa_4a83dfced84c4f0aa7adf2a43f276a11/receipt.json`：Job PID 清空、handles 關閉、mutex 釋放、exit 0；`full_product_accepted=false`、未改正式產品。 |
| QA025 | 指定文件／來源測試 82 PASS／4 SKIP；route 與 context 命令 return code 0，輸出未列 Unknown。全域 `document_control.py check --context-metadata` return code 2，回報多筆既有 `output/trial`／`output/tasks` junction 外部連結越界；沒有以此結果改寫文件或宣稱檢查通過。 | `qa025_source_and_documents/01_stdout.log`–`04_stdout.log`。此回合未執行 backend。 |
| QA026 | 原始 UI／日營收流程測試 1 FAIL；由原 view 打開候選時，session 以 `monthly_revenue_yoy_index_v2_source_open_failed:DailyMarketMonthlyRevenueReadSessionV2Error` 失敗。不可把這項產品路徑失敗說成成功。 | `qa026_revenue_flow/00_stdout.log`、`receipt.json`。隔離且唯讀的來源診斷 QA032 後來成功，不改寫此 receipt。 |
| QA027 | 指定 Paper／回測邊界命令的 helper py_compile PASS；`main_paper_boundary_r11.py --phase first` 在 150 秒逾時（return code 124，owner 強制結束程序），未產生可用 journey 證據。隔離資料缺 `twstock.db` 及 benchmark preview 檔亦見於 stderr。 | `qa027_paper_backtest/receipt.json`、`01_stderr.log`。 |
| QA028 | 小型合成 fixture 診斷未完成，尚未取得月營收 session 成功開啟的證據；原失敗保留。後續 QA031 改用既有 QA026 來源唯讀定位原因。 | `qa028_monthly_diagnostic/receipt.json` 及原始診斷輸出。不能外推為產品或來源資格通過。 |
| QA029 | R09 backtest journey helper first 以 1 結束，沒有建立任何已檢核項目。helper 自行加上的預設成交限制停止條件阻止執行；另有隔離 audit 將三次正常 `NUL` 開啟記為 denied write。受限 120 點資料副本及既有 Registry 元件 source SHA 前後相同，沒有 network attempt。 | `qa029_backtest_main/receipt.json`、`01_stdout.log`、`01_stderr.log`。此結果是 helper／audit 未通過，不能當作回測產品功能結果。 |
| QA030 | `document_control check --task ... --path ...` return code 2。輸出列出 17 個 Must 文件未登記，另有 `theme_momentum_filter` source/test 未命中自身 change patterns；結構核對限制亦明示不證明文件語意或產品 Gate。 | `qa030_scoped_document_check/receipt.json`、`00_stdout.log`、`00_stderr.log`。 |
| QA031 | offscreen Main route smoke 17 路由正常、無 messages/errors、worker 0；但月營收 source diagnostic 仍 return code 1（protected root reparse point），R09 backtest first 在 420 秒逾時（return code 124，owner 強制結束）。QA031 未完成保存／fresh journey，不能由路由 smoke 推論通過。 | `qa031_daily_journeys/receipt.json`、`00_stdout.log`–`03_stderr.log`。 |
| QA032 | 使用 QA026 已存在的合成來源檔，以獨立 CASE 唯讀打開月營收 session 成功（`open_succeeded`）；來源 fingerprints 前後相同、無正式資料寫入。這只確認受限 physical diagnostic 能開啟原件，原 QA026 UI 仍失敗，沒有驗證原 Main view 或真人操作。 | `qa032_physical_monthly_diagnostic/receipt.json`、`00_stdout.log`、`.tmp_v2_r12/CASE_qa032_monthly_source_existing/receipt.json`。 |
| QA033 | 七個命令全部 return code 0：helper 編譯、正常 Main Paper 缺件拒絕及手動研究日記 first/fresh、原月營收 view 測試 1 PASS、兩筆正常 Main 回測保存與 fresh Registry 精確讀回、scoped 文件結構檢查。兩策略資料指紋不同，績效比較按原契約拒絕；搬移的舊 run 絕對路徑亦被拒絕。 | `qa033_journeys/receipt.json`、`r09_qa033/{first_result,fresh_result}.json`、`main_paper_boundary_r11_qa033/`。R09 狀態仍為 PARTIAL；未證明相容比較、真 Paper 帳本或金融資格。 |

QA033 closure SHA `1905734286700f7930b731900d2097aaec9a6d70047f40113fe87e448f78944d`；Job 自然排空，handles 關閉、mutex 釋放，無強制收尾。QA032 的診斷 PASS 與 QA033 原 view PASS 分開記錄；QA026 原 FAIL 保留。全域舊 junction 連結檢查仍是局部未解，scoped check 不代表全域通過。

QA034 正常 Main 的真 WorkbenchSourceService 缺件出口通過：沒有每日快照狀態檔時，候選為零、無來源身份、選單及開啟按鈕停用，按鈕不會誤入個股；未生成候選檔。QA035 新增月營收明確個股入口與短期來源回返契約，25 項定向、原 view 真 fixture 1 項、Workbench 85、validator 25/0/4、mypy 1103、17 路由 smoke 及 scoped 文件檢查通過。同輪 R17 first 正常 Main 追加同條件 MA run，真正指紋相同且原兩筆 metadata/Parquet 保持；fresh 因比較讀取器不識單股原存 `equity` 欄失敗，故整輪仍 FAIL，closure `076a8ca931dfd59179744286ed8d6026035c1fc06f3cf5a4c0f32909c0e6bcbb`。

QA036 將明確 `single_backtest` 原曲線在比較副本轉接欄名後，七命令全部 0：編譯、47 項日期／精度／保存／比較測試、正常 Main fresh 同指紋比較、Workbench 85、validator 25/0/4、mypy 1103 及 scoped 文件檢查通過。真正讀回 120 個共同日期、240 列標準化權益，原來源與 QA033 原件不變，未重算原回測或覆寫 QA035 失敗。closure `ef6ef15e4d3f0978eecc338a9b802e5a84c966a65bdc4d6eec0a42fcc53df6f1`；兩輪 Job 均自然排空、handles 閉、mutex 釋放。證據位於本 task `qa034_daily_missing`、`qa035_revenue_route_and_compare`、`qa036_registry_comparison`，R17 各輪結果另名保存。

QA021–025 的範圍、原失敗和修正後輸出分開記錄；後續 PASS 不抹去舊 receipt。QA025 的文件檢查失敗是既有 junction 連結越界，不能外推成產品 backend 結果。QA024 closure 的受控程序自然排空，但不代表整體 V2 gate 接受。

## 五條旅程與金融界線

QA037 固定建置日期參數的編譯、74 項來源／資源／身分測試、單檔 mypy 與 scoped 文件檢查全部通過；closure `049af0e847a6bd5872c480e4462e5936a8a173ab5784d481798b42d60c10a8e1`，自然閉鎖。此證據尚未包含 EXE 建置或同版驗證。

QA038 從固定 `730613e121b3fb5ca349440bf9973acc6a727842` 建立首個隔離 EXE，僅為 built_not_validated。QA039 在固定 archive 的 Python model probe 遇到舊 `workspace_widgets == 9` 假設而失敗，尚未進 EXE 比較，不是同版 PASS。更新驗證工具後，QA040 來源版 model/spawn/fresh/Main 正式 17 路由及全部既有後端入口通過，無 modal、正常關閉；編譯及 scoped 文件檢查亦通過。首包及原失敗保留，需固定新 commit 重新建置後驗證。

狀態只描述目前有界工程證據，產品 Gate 仍未整體接受。`PARTIAL` 不等於完整旅程通過；真人接受另列 `MANUAL_ACCEPTANCE_PENDING`。

| 五條研究旅程 | 狀態 | 已有證據與未覆蓋出口 |
|---|---|---|
| 總覽→線索→個股→保存→返回 | PARTIAL | QA073 正常 Main 從首頁進 10/19 歷史保存推薦、明選 1512 原 context、保存報告並返回同結果同列，first/fresh 自然關閉；QA075 fresh 再驗首頁具名最近研究卡真按鈕開原報告、返回首頁同卡及 Journal 不變。這些受限腳本切片 PASS；受接受今日候選、原生 GUI 與真人仍待。 |
| 市場／題材→成分→個股→返回 | PASS（限定研究快照） | QA075 真題材及獨立行情的保存／fresh回訪證據保持；QA096 Python Main、QA103 新412ca3 EXE正常Main first/fresh另驗CoWoS2330→2360→2330、原列返回及選列漂移拒絕。25鏈／90題材、來源SHA、10/16題材與9/23行情120點分開；缺成員行情不借題材補值。完整來源資格、原生 GUI 與真人仍待。 |
| 綜合選股→條件→2–5股比較→個股 | PARTIAL（兩股價格旅程PASS） | QA056 Python Main／fresh原切片保持；QA098前版2b EXE正式四對話框producer complete及五功能步驟、QA100 fresh exact同源讀回／條件／比較／個股／原頁列返回通過，來源SHA保持。QA098原first finalhash長路徑工具FAIL保留；QA100並未重跑producer。月營收完整Main真來源綁定、全來源及 Native／真人仍待，不外推412ca3另一次producer。 |
| 個股→人工確認→Paper→Forward→覆盤 | PARTIAL（安全出口） | QA033 正常 Main 缺合法 mark/cash/snapshot 時拒絕建帳，manual/Paper 分開、無 NAV/ledger 寫入；手動研究日記經 UI 保存並 fresh 精確回讀。完整建帳及自然 Forward 成熟未驗。 |
| 策略→回測→保存→比較→返回 | PASS（受限腳本） | QA033 正常 Main 以 2330 真實受限 120 點樣本執行兩策略、保存 Registry 並 fresh 精確讀回；QA035/036 另以同策略原輸入新增合法 run、fresh 比較 120 共同日期/240列權益，原件保持。異指紋與搬移路徑拒錯另有原證據。非績效資格、Native 或真人接受。 |

QA013、QA017 與 QA020 的 scoped 結果均不能升格為 V2 Product Acceptance PASS。真人接受仍為 `MANUAL_ACCEPTANCE_PENDING`。

PIT、全市場資料覆蓋、法人金額／單位、Forward 自然成熟、ML OOS／Promotion 與真 Paper 完整帳本仍依各自原資格。UI 通過不授金融資格；不補零、不造 NAV、不合併手動／Paper，不觸正式交易、排程或正式資料寫入。

## 資源與交付界線

QA041 從固定 `e36919493b70a6be99df43b8e6d420b6d6b6c418` 建置修正候選，版本 `2026.10.21+e36919493b70`。QA042 Python／EXE 同版隔離 fixture 通過，包含固定來源／依賴／資源身份、直接 Qt 入口、保存旅程、模型／spawn／fresh 與 H20 呈現；不代表真實市場或真人接受。QA043 的 CMD 行尾及 QA044 的 PowerShell runtime 模組相容失敗保留；標準 CRLF、固定 Windows 內建 PowerShell 與其模組路徑後，QA045 整包通過：啟動器 prepare/check、錯 SHA 拒絕、原樣本不變，以及真正 frozen Main 17 路由、1280×760／1440×900／1920×1080、DPR 1.5。Main／coordinator／新 origin 均由 `PyiFrozenLoader` 從 `_MEIPASS` 載入，無 modal／錯誤，TaskWorker／thread pool 為零。以上是 offscreen，沒有恢復原生輸入。

本機候選位於 `dist/candidate_e36919493b70_a1df3b90/baldr`，使用同資料夾 `Launch-Baldr.cmd`；指南與 `DELIVERY_RECEIPT.json` 列原樣本、獨立 state、流程限制和原始收據。EXE SHA `1834e107cbe6e93a0f5e684dadba003e6809662f12ceb05cdd5838273b4b6f1f`。QA042 closure `abf2513883a466b21dcf7a97d68be18022dbcf07a7c6db3bdf814ae9c0a45cd3`；QA045 closure `be4531d9421e230d4871b5d5263015604efb7145ef9a95d9f1bc22f508bafe15`，自然排空、handles 關閉、mutex 釋放。原生操作仍受使用者先前 Escape 停止指示，已另請確認是否恢復；無回覆不視為同意。

QA047 補齊 Blueprint §11A 的 **1500×900、DPR 1.5**，沿用同一 e369 EXE 與隔離 state，沒有重建。真正 frozen Main 的 17 路由通過；首頁與選股頁截圖實際為 2250×1350 像素，root 已檢視，無意外 modal／錯誤，TaskWorker／thread pool 為零。啟動器正反 SHA 檢查及包內／state 四個樣本 SHA 保持。原始收據在本 task 的 `qa047_1500_probe/receipt.json` 與 `qa047_1500_probe/r27_exe_main_smoke/result.json`；closure `ee26d03ce16d9bd9843153d950068acd2ca125738a40507dfd30cc9b49507e45` 自然排空、handles 關閉、mutex 釋放。這補足指定尺寸的 offscreen 證據，不改變五條完整旅程的 PARTIAL 或原生／真人待驗狀態。

交付回退只切換啟動對象：先正常關閉此候選，保留完整目錄及獨立 state，再從研究13原入口 `output/trial/Baldr-Theme-Research-13/Launch-Baldr.cmd` 啟動。不要把候選 state 匯入、合併或複製進研究13／正式／私人根；本步驟沒有資料還原、遷移或清理。兩份新 EXE（730 首包與 e369 修正版）及原失敗證據均保留，資源現況依既有 task `RESOURCE_LEDGER.md`，任務 Credits 為 `USAGE_UNOBSERVABLE`。

QA049–055 原失敗均保留。QA052 的舊143來源因保存的 C 槽 output 別名已成 junction 而被 source-clock canonical 檢查拒絕；現有封存恢復工具保留 clock，不能解除這個具名限制。QA054 改用固定 QA233a 真行情副本，經正常 Main 四個 Qt 非原生確認與正式 producer 建立明示兩股母體（2317／2330、資料日 2026-09-23、台北16:00截止），分母／處理各2、缺件0；完成條件、比較及個股開啟後，驗證腳本錯把隱藏個股頁要求清空而逾時，整輪仍是 FAIL，沒有改產品返回邏輯。

QA056 以全新 Main 程序與 CASE，透過正式 `ApplicationSettings` 明選剛產製的保存來源，通過兩股查詢、價格下限1、比較、個股及返回；query／page／row identity 全部保持。原 QA233a／本 CASE 價庫 SHA 與來源 plan／三份 receipt SHA 保持，availability 仍 unknown、歷史 PIT 仍 false。`r44_qa056/journey_receipt.json` 為原始證據，closure `36a15b1a8b374bf1b2b7907742c591d995fa819f93a05ef9b44bd0884ed45782` 自然排空、handles 關閉、mutex 釋放，worker／thread pool 為零。本切片不是月營收綁定、全市場、EXE 此旅程或 Native／真人接受。候選另附已由正式 loader 接受的兩股母體 JSON 範例及 README 步驟，只有研究範圍參數，沒有手寫金融列、clock 或接受紀錄。

本任務新 EXE 建置共 2 份，首包保留但未通過同版；本機修正候選約 976 MB，未替換研究13、`dist/baldr` 或 active delivery。已有包、正式資料、模型及私人資產未刪除。平台可觀測帳戶共用額度與餘額，無精確任務計費歸屬，額外 Credits 實耗為 UNKNOWN；不聲稱能對平台帳單強制數字硬停。

本文件僅記本輪實際範圍，V2 產品驗收尚未完成。

## 儲存盤點缺件診斷（QA058 起）

QA058 探針未點重新盤點便檢查表格，QA059 誤用 PySide6 instance enum；兩輪為驗證腳本失敗，原收據保留。QA060 修正探針後，在真正 e369 frozen Main 使用隔離 DATA／OUTPUT／應用狀態，點實際盤點按鈕；三位置符合設定，但 Trial 根是不存在的 `_internal/dist`，空清單仍顯示「有界盤點完成」，因此 FAIL。Root 已檢視截圖，關窗後 managed worker 為零，closure `3b60facfe3f19ad0bd5f6e69b309d0154f729f03d8e4e2612b3d8f28b48f2f94` 自然排空、handles 關閉、mutex 釋放，沒有操作原生桌面。

後繼原始碼改為封裝模式僅盤點目前套件、原始碼模式使用明示 dist 容器，並呈現根路徑及缺件／不可讀診斷。QA061 Workbench 85 通過、更新頁 25 通過／0 失敗／4 跳過、指定 mypy 1103 檔通過；定向首次有一項新測試的狀態文字期待不符，修正後 QA062 儲存 service／view 14 通過／1 平台連結跳過。reparse 不跟隨另有可重現的模擬測試通過，跳過不冒稱真連結覆蓋。

QA062 source Main 探針缺 repo import 路徑，QA063 對巢狀 `processEvents` 中的 cleanup 等待未達條件，原失敗保持。QA064 正常 Main 首次盤點通過：三個隔離設定位置一致、實際 F 槽 dist 路徑明示、4096 項上限與部分大小呈現，root 已檢視 1280×760／DPR 1.5 截圖，無 modal，route／close worker 皆零。closure `edf9cd3d1bcad457f362b25aa1b2558aca34d219f5b4e107d6434ced82e04452` 自然排空、handles 關閉、mutex 釋放。QA065 再以真正 Qt event loop、真 TaskWorker 驗兩次刷新、按鈕重新啟用及單檔 1→2 MiB 重新量測，1 通過；closure `bb73dfd9941d6bf819adcdb8bf80cff3b509652f6238995333c8c85469f7782c` 自然閉鎖。這將 QA063 限定為探針事件循環限制，沒有為它修改產品生命週期。

固定 e369 未重建，不能將此修復寫成已交付 EXE。沒有提供清理或授予任何舊版本可刪除資格。以上不是 Native／真人或完整五旅程接受。

QA066 的 R55 診斷以真正 Qt event loop 重開既有 R54 隔離 CASE，確認首頁按鈕導向選股研究、來源刷新與自然關閉正常；reader 回覆「legacy data_path 超出 runs 目錄範圍」。來源副本 DB／artifact 前後 pin 保持，沒有修改原件或放寬 guard，因此這份搬移副本不能當成完整歷史研究旅程通過。QA061 的 R51 準備階段因匯入提前建立隔離目錄而拒覆、QA063 的 R54 未取得保存來源，原失敗均保留。

QA066 五份文件合查未通過：Snapshot／Manual 既有指向 output junction 的歷史 Trial 連結被越界守衛拒絕。沒有改寫舊連結或放寬檢查，不能聲稱全份文件檢查通過；本次新增操作與內部 QA／架構連結另作 scoped 核對。

## 保存研究回訪與關閉修復（QA068–075）

QA068 使用官方 `copy_research_output.py` 的 archive restore，將研究13的 13 個封存檔恢復到新的任務隔離根，依原收據重綁新副本的索引路徑，公開 reader 驗證通過；沒有手改 DB、放寬搬移守衛或重編金融 artifact。原封存不變、未啟用正式設定、未產製今日候選或來源資格。restore receipt SHA `5c4eeb357dfea29aa42139d81e3ddfeccdbefca61f77f3c57d4b0044be83411c`；closure `c492210992c312c7d59c6e83c3a9065971bcf16506cc7c129eebdc00d780e7f8` 自然閉鎖。

QA069 helper 未接受 Qt 將 tuple 轉為 list 的資料表示，原 FAIL 保留。QA070／072 的歷史推薦旅程四個功能步驟完成，但正常關閉的 deferred-delete drain 重現推薦頁延後 resize 回呼存取已刪除 QScrollArea，整輪仍 FAIL；QA071 已另以新程序精確回讀原保存判斷。修復將延後回呼改為 RecommendationView 自有的單次 QTimer，銷毀時由 Qt 取消，成功關閉時停止；沒有吞錯、略過 drain 或修改金融邏輯。

QA073 修復後，歷史推薦 first/fresh 均 PASS：首頁實際入口、原 10/19 保存結果 `rec_3a4acdb159d841cc91492de258c1a0a9`、1512 原研究脈絡、UI 保存、返回原結果／原列、fresh Timeline 原件及原 Journal 保持。degraded 與來源缺件照原件保留，沒有升格為今日推薦。原始收據在本 task 的 `r57_recommendation_restore/r67_first_receipt.json`、`r67_fresh_receipt.json`；closure `1aff377ab3815333eb3c3d9eb4744518c330c2aa48b2dadec08ba6eceb537316` 自然排空。QA073 整輪仍因另一題材 helper 的 runtime 根假設錯誤為 FAIL，不將子命令通過寫成整輪通過。

首頁最近報告新增「回訪原報告」，以同次 entry 物件選取、背景重核原件，保存報告開啟與返回均保留身份；時間軸入口仍返回時間軸。報告卡分列保存時間、原研究來源日及行情日；行情日只取 typed 保存原件末筆價格，缺件明示原件未提供。QA074 編譯、45 項定向、Workbench 85、更新頁 25/0/4、mypy 1103 檔通過。題材 helper 在剛切筆記頁時立即檢查保存按鈕，未等待背景刷新而 FAIL；原失敗與三題材檔／價庫不變證據保留，closure `927b317f88dfa056461dbea9fed21968be4f41e42f71e6ee3789ad5522e13d58` 自然閉鎖。

QA075 改沿實際「保存判斷」按鈕並等待讀取完成，正常 Main first/fresh 全部 PASS：固定題材→2330、獨立 9/23 行情 120 點、報告判斷保存、原題材原列返回；新程序 Timeline 精確重開、首頁真按鈕開同一報告並返回同卡、Journal 不變。原始證據 `r58_market_theme/r71_first_result.json`／`r71_fresh_result.json` 明列 10/16 context 與 9/23 價格日期、來源身份及 SHA；root 已檢視兩張返回題材頁圖。closure `e0e30f9c15518560d00112826baf0618a494591332eacae62e171c7f6102a252` 自然排空，workers／Job PID 為零、handles 關閉、mutex 釋放，無強制清除。

上述新功能與關閉修復只在後繼原始碼，固定 e369 EXE 不含；未新建 EXE。原生操作仍停止，真人與整體 V2 Gate 未接受；金融資格維持原限制。

## 新整合候選（QA077–080）

QA077 從已提交 `2b164aede9533f8f1cebe1b95d4e267792ecdf9f` 建置本任務第三份 EXE，版本 `2026.10.21+2b164aede953`；包含先前 Storage、首頁原件回訪／分日與推薦頁 owned timer 修復。新包為 `dist/candidate_2b164aede953_1dff24ee/baldr`，EXE 57,115,086 bytes，SHA `8499fc15231750a3616316b40079c9ac572bbaa5af95943ffd98f4575585e89f`。QA078 使用固定 archive 的 Python／EXE 同版 probe 通過；closure `04f7f4873a9ae0f890837b186c2775aa404533a9867d0ed244b73074205eb4cb` 自然閉鎖。沒有替換既有包或重複複製完整封裝。

QA079 新增驗證工具遇到未封裝的 QtTest、及 loader module 名稱假設而 FAIL，原收據保留；沒有為測試重建 EXE。後續 helper 改以 Qt 滑鼠事件操作實際 viewport，並精確接受兩個已知 frozen loader module 名稱，仍要求 `PyiFrozenLoader` 且來源位於 `_MEIPASS`，不允許工作樹 fallback。

QA080 全部命令通過：真正 frozen Main 重用 QA075 保存原件，核 source commit／五個包內模組、題材與獨立行情、Timeline 與首頁原報告精確重開及返回，Journal／來源 SHA 不變；儲存頁明確盤點 `sys.executable.parent` 的單一套件，三隔離根正確，達 4096 項時呈現部分大小而非假完整。啟動器 prepare／check、錯 SHA exit3 拒絕、包內與 state 四樣本不變通過。17 路由在 1280×760、DPR1.5 通過；首頁另驗 1500×900、1440×900、1920×1080，非所有路由的四尺寸全覆蓋。root 已檢視首頁原件卡、保存報告、儲存頁及1500首頁圖。無意外 modal，worker／thread pool 為零；closure `1f9a1286c795c9049c6d53ed6e1e19b30980845ea0c4fde759edbaef6f3a0e41` 自然排空、handles 關閉、mutex 釋放。

新包有 `Launch-Baldr.cmd`、`RESEARCH_GUIDE.md`、既有兩股母體範例與 `DELIVERY_RECEIPT.json`；交付收據 SHA `76ea834b8edea9b680a4a86cf1e055c5bf9f80e0cf34605cb8eff3e7199cbe3a`，列八個關鍵檔 pin。啟動器固定 Windows PowerShell、CRLF／無 BOM 與新 `r74_candidate_state`，四個真樣本沿舊包固定 pin 核對。回退僅切換至研究13原入口，不合併或遷移 state；未簽章、未替換 active delivery、未執行原生輸入。兩股價格完整 EXE 旅程、真月營收來源／binding、完整 Paper／自然 Forward、Native 與真人仍各自待驗；整體 V2 Gate 不升格。

## 兩股既有來源 EXE 旅程（QA082–090）

QA082–088 原工具失敗保留：長路徑需使用既有 Windows extended read path；PyInstaller 的虛擬 `__file__` 不能要求實體檔；專項 startup controller 必須依正式 ready 契約啟用 Main；查詢欄位是 `min_close_price`。重用價庫保持唯讀，crash diagnostics 沿既有 public API 指定本次 CASE，不放行舊資料根寫入。QA086 同時量得普通261字元 plan 探測失敗但 extended 可讀；正式產品 catalog 已有 extended I/O，QA088 實際讀出 complete entry，不判為封裝長路徑缺陷。沒有修改產品、來源 clock 或收據。

QA089 六項功能步驟完成，但 helper 在合作式關閉開始時取樣而判 FAIL；原 crash log 已記正常收尾。QA090 將最終關閉判定移到正常 Main 返回及 drain 後，編譯與完整限定 EXE 旅程 PASS：明選 R42 官方 producer 既有兩股來源、價格下限1、2317／2330 比較、同源個股與同 query／page／row 返回。四個來源索引 SHA、R44 唯讀價庫及 Journal 保持；沒有新增價庫副本、產製來源或網路。availability 仍 unknown、PIT=false，非全市場、月營收或自然 Forward 接受。

證據在本 task 的 `r98_price_frozen_2b164aede953/price_frozen_journey_r98/receipt.json`，root 已檢視返回圖；closure `08b5e8ac6ffed6634e9a2db7da2a1b98333506033540c2141f2de13156a8788e` 正常退出、worker／Job PID0、handles 關閉、mutex 釋放，無強制清除。更新後交付收據 SHA `d88dfd7a765582cb816a16bbc1b757a97fda19bfa37b7d46f5239336572148c7`，八個 key file pins 不變；原 QA080 收據另存於任務目錄。EXE 來源產製、Native／真人、完整五旅程與金融 Gate 仍不升格。

## 題材成員導航與後續 EXE 補驗（QA092 起）

Blueprint 第二旅程要求同題材成員的上一檔／下一檔；後繼 Python 原始碼以不可變的題材導航身份核對原 snapshot、題材、成員順序及原選列。Report 僅替換代碼與名稱，價格仍各自讀取；來源或選列漂移時拒絕，保存時報告保持唯讀。QA096 正常 Main 與新程序導航已通過，固定 `2b164aede953` EXE 不含。

QA092 編譯、四檔定向85項、Workbench85項、更新頁25通過／0失敗／4跳過、指定 mypy1104檔通過。整輪因文件定位用了不支援的 `industry_theme` 領域而 FAIL；QA093 改用 `ui` 完成定位，不更改產品門檻。QA092 closure `c2183442d4f0d214c4a1737f14b0d60e570ee2ae9d072d0d96e1243f350ea2d2` 自然閉鎖。

QA093 固定 EXE 實際完成兩次相同 MA 參數的回測與正式 Registry 保存，兩筆 fingerprint 相同、Registry／Parquet 與唯讀價庫 SHA 保持，Main 正常關閉、worker0。整輪因 audit 記錄到並阻擋既有來源目錄建立及 `socket.bind` 嘗試而 FAIL；不能把被阻擋嘗試寫成實際外部寫入，也不能把本輪當完整比較通過。後續將唯讀重開這兩筆合法產出作比較，原收據不改。Closure `0e8cb779a690f5dd0f7e619940bac006e96d04d075a5acb8942f0e043df1c527` 自然閉鎖。

QA094 的 EXE producer helper 在正式產生動作前因不存在的 `view.busy` 屬性而 FAIL；EXE、population 與價庫 SHA 保持，SQLite sidecar 未產生。這是驗證工具錯誤，尚無來源產製通過證據；原結果保留。Closure `39dc62211705a49f480af8b58edd4576f224aceb6fd4e2a6f8e923cb36dd7ed1` 自然閉鎖。以上 Job 均無剩餘 PID、process／Job handles 關閉、mutex 釋放，沒有強制清除。

QA095 原失敗保留：helper 的 mkdir audit 使用 `AssertionError`，令原本 `Path.mkdir(exist_ok=True)` 對既有目錄的無操作變成啟動失敗；另舊 guard 測試替身缺新 resolver 屬性及仍預期舊文案。後續工具改用 `PermissionError` 繼續阻擋外部寫入，讓標準庫正常處理已存在目錄；測試替身明確沒有 resolver，仍驗拒絕任意跨股。沒有放行來源寫入或放寬身份守衛。

QA096 的新 R110 CASE 完成正常 MainWindow／正式服務及 fresh 程序各五步：明選真10/16版本（25鏈／90題材）、2330→真下一檔2360→真上一檔2330、原題材原2330列返回、原選列變動後拒絕切股與返回且 context 不變。各股只有代碼／名稱變，成員清單與來源身份保持；2330 仍有120筆行情截至9/23，不借10/16題材行情。三題材原件及重用 R74 價庫 SHA 不變、SQLite sidecar 缺席、worker0自然關閉；root 看過返回及拒絕畫面。另8項原守衛／題材反查回歸通過。新導航不在固定 EXE。

QA096 整輪仍 FAIL：另一項 R108 EXE producer 已完成四個精確確認對話框，但回傳非 complete；helper 在保存診斷前即拒絕，原因待下一次具名診斷，不認定為產品缺陷或成功產製。來源與 EXE SHA 保持。Closure `c0970d70670632471c4ffa14f12144b0ab47f0b2714092f962a2cd0291c69b77` 自然排空；題材功能的有效證據不受另一 helper 失敗取消，也不外推整輪通過。

QA097 固定 EXE 以正常 Main 的正式 Registry widget 重開 QA093 兩筆真 run，同指紋比較標籤、120共同日期、240列權益及返回後狀態成功；expected.json、Registry DB及4個Parquet前後SHA保持，Main關閉／deferred-delete drain／worker0通過。整輪仍 FAIL，隔離器另阻擋既有輸出目錄 mkdir、Journal 鎖與 Registry 寫模式探測；未把這些阻擋改成成功寫入，也未聲稱完整隔離接受。保留功能已驗與該具名隔離限制，避免只為工具分類重跑同一旅程。Closure `cc3197b88c4e90d3c122b6debe44abaa8a65c4be4800fa569c89498bb453cef9` 自然閉鎖。原生／真人及金融資格不變。

## 題材導航候選交付（QA098–103）

QA098 的 R111 正規化 Windows extended 路徑後，前版2b EXE正式producer完成，且 strict-load、兩股明確條件、比較、同源個股及精確原query／頁列返回五步成功；availability仍unknown、PIT=false。整輪只在最後兩個普通長路徑的 `resolve(strict=True)` 雜湊檢查失敗。QA100 R112只重開同一R111 generation／receipt，不重產來源，先核原五步／complete與原兩條工具錯誤，再以extended I/O嚴核原件SHA，fresh五步與source／DB／population保持通過；原first receipt SHA保持 `610acf5c6db24b5e3ea98e5b259cf237325f62827528aeb1bea19f865ba2c8a3`。QA098五份相關文件12features／0errors通過，整輪FAIL仍保留。

QA099 從已提交 `412ca3e5fe4f4d70a77f893e576bc55af265ed2f` 建置本任務第4份重要RC，包含新增同題材成員導航；沒有為工具修正重建。QA100 Python／EXE同版隔離比較通過。新包 `dist/candidate_412ca3e5fe4f_95e7e445/baldr`，版本 `2026.10.21+412ca3e5fe4f`，EXE57,119,760bytes、SHA `68cfa7673abbbc7a2d148246bfd00897bca70a8299c04c5c54a708ed3adfeedd`；專屬state為本task `r114_candidate_state`。

QA101 新啟動器prepare／check、錯SHA exit3拒絕、包內及state四真樣本保持通過。真frozen Main的17routes於1280×760／DPR1.5，首頁另1500×900、1440×900、1920×1080，worker／pool0；未把單一尺寸的路由證據外推為所有尺寸全覆蓋。另一導航helper錯用byte hash處理Path，先於Main失敗；QA102導航五步成功但工具又關閉已由正常Main刪除的物件而FAIL，原件保留。

QA103 R116以`isValid`避免重複關閉已刪除物件，真frozen正常Main first／fresh全部通過：四個產品模組均為`PyiFrozenLoader`且在_MEIPASS，沒有工作樹fallback；CoWoS2330→2360→2330、10/16題材／9/23行情120點分開、返回原2330列、來源選列變動後拒絕跨股與返回。source SHA保持、SQLite sidecar缺席、Main rc0／worker0／pool0，Main正常刪除；root看過fresh返回及拒絕畫面。沒有改產品、來源時鐘或舊收據來通過。

QA099／100／103 closure分別為 `c9fe124d3c668dd8e3d95fface03312be30e662bd77128ef8617030f02df0f4b`、`ea61ca83194916a73dec047bb8602cbbffd5b8f18f9d54decbee08b040604263`、`7dbe47beb9f96587d2e0f65b2906d909d1e6b352267f8fe7c943bcb4440f0b13`；QA098／101／102原FAIL也皆自然閉鎖。所有Job PID空、process／Job handles關閉及mutex釋放，沒有強制清除。

交付收據 SHA `8c677527f2a6a3723cafb816939e338d32d94c292716e16e48a319911c2c993a`，8關鍵檔pin；包內7,135files／976,476,885 logical bytes，build5,271files／315,378,063 logical bytes，並非SSD唯一實體配置。新增一份重要RC及必要小樣本，不刪舊包；本機位置綁定、未簽章、未替換active delivery。首頁原件回訪與Storage重用前版2b QA080未改功能路徑證據；兩股producer及Registry證據也明列其2b來源版本。原生停止、真人待驗、真營收綁定、Paper／自然Forward及金融資格各自保留限制，不升格完整V2接受。

## 研究證據對照與125顯示（QA105–112）

固定 `412ca3e5fe4f` EXE 在 QA107 以實際 DPR1.25 完成1280×760的17路由，首頁另驗1500×900、1440×900及1920×1080；Main rc0／worker及pool0、四來源與模板、BUILD_INFO、EXE pin保持。QA105舊模板pin誤配、QA106診斷日誌嘗試寫唯讀樣本而被拒的工具FAIL均保留；R122沿已接受的public診斷CASE初始化與安全關閉後通過。Root看過首頁及選股圖。這不外推所有尺寸各17路由或Native。

Blueprint §4.6後繼source新增明選的「當時固定證據／目前可讀資料」唯讀對照。四種筆記均先重讀原件；手動缺行情與題材未封存值明示，價格沿已核原收藏，保存報告沿原投影，當下另以新context讀既有reader。沒有回填舊研究、金融差值、寫回Journal或用途資格提升。換選、重新讀取、離頁及關閉使舊回應失效。

QA108保留新service import及tuple typing錯誤，QA109修後編譯、Workbench85、更新頁25/0/4、mypy1107通過；定向84PASS／1SKIP／1FAIL只剩題材測試欄名，QA110修該assert後service8PASS。唯一SKIP為原scheduled Qt smoke需顯式opt-in，並非自然排程接受。原FAIL未抹除。

QA110正常MainWindow在隔離state透過真UI保存2330報告，再首次與新程序明選原筆記並對照。題材10/16、行情9/23、報告查詢10/21分列；新報告讀取不以查詢日冒充行情日。原snapshot與Journal SHA `7a11bf7900823df4a2a60dbc261ec5b30c277be66794c250289c682466bb0d0b`、四真來源pin保持，SQLite sidecar缺席，worker／pool0後自然deferred-delete。Root實圖發現長來源擠出第三欄，機器功能PASS仍記視覺FAILED；QA111修同屏後又發現無空格SHA裁切，未以機器PASS取代視覺接受。

QA112改為原生純文字換行儲存格，完整來源識別可選取；640／1280有界widget測試核實長token換行、無內部水平／垂直溢位。18個Timeline／widget測試、Workbench85、更新頁25/0/4、mypy1107及compile通過。R130只fresh重開原R123筆記，沒有重新保存或複製來源，原R123／R126收據與Journal／四來源保持；1280×760／DPR1.25的三欄、日期／收盤／完整來源身份同屏通過，Root看過Main與比較區兩圖。正常隱藏、worker／pool0、deferred-delete完成，未強制清理。

QA107 closure `840aefa796261361724b43a4cdbb3886c9e14c8ab8a253f20dd94a882bfd9f1c`、QA110 `62e59df6a602ffd507eb1325ba4eaa7191917d15bfc3ac4ad3d91f3438c1178c`、QA112 `2bb27c4636508256ab621cb09bfcf9a2356f1e3dcf3441f2da717a73ddc39bf8`；三PID列表空、process／Job handles關閉及mutex釋放。新增對照僅source受限接受，固定412ca EXE不含；下一重要整合RC另驗，五旅程overall PARTIAL、USER_STOPPED_ESCAPE／真人待驗與金融Evidence Backlog保持。

## 研究證據對照候選交付（QA113–121）

QA113 五份相關文件、12 features／0 errors scoped 通過。QA114 從已提交 `a65d2b2b4fd50a16b8e3f806e827469b1f8175d5` 集中建置第5份重要RC；QA115 Python／EXE同版隔離fixture通過。版本為 `2026.10.21+a65d2b2b4fd5`，整包位於 `dist/candidate_a65d2b2b4fd5_cb32716d/baldr`；EXE57,143,377bytes，SHA `0417d9c1c2d6a812a55b777974be623f2a23bac49e874f0dc218d31a8410c9d4`。Launcher／GUIDE使用專屬 `r132_candidate_state`，不匯入正式、私人或舊候選state；沒有為helper修正重新build。

QA117 的 R134 在真正 frozen 正常 Main 首次經題材CoWoS→2330→一般報告→UI保存判斷，選原筆記對照，再由新程序重開同一筆記。12個產品模組均在 `_MEIPASS` 且為 `PyiFrozenLoader`，無工作樹fallback。1280×760／DPR1.25、1600×950實體畫面中三欄及完整來源身份可讀；報告查詢10/21、行情9/23、題材10/16各自保留。原報告snapshot、Journal SHA `b56b49a3306aad59c30daa351866e49ccd4d50cb35ca0cda8bb979d11aeb73ce`及四來源保持，SQLite sidecar缺席、Main rc0／worker與pool0且自然刪除。功能first/fresh收據全部PASS；整輪隨後直接dispatch pwsh不符合既有commands runner的Python入口限制而FAIL，材料尚未執行。這是工具限制，不是自動審批拒絕；原FAIL保留。QA116另有helper compile FAIL，未執產品驗證。

QA118 由固定Python wrapper執行材料組裝，新候選新增Launcher、GUIDE、config、固定四樣本與8材料pin manifest。R132 package probe的prepare0、check0、錯EXE SHA exit3，以及包內／state樣本保持均PASS；後續route在初始化缺少的空daily_price目錄時被CASE-only audit拒絕，整輪FAIL且未開始路由。QA119新helper縮排compile FAIL也保留。QA120 R138先於隔離state建立並記錄五個標準空設定目錄，再以原CASE-only守衛完成17路由，只有1280×760／DPR1.25；1500×900、1440×900、1920×1080另驗首頁。8材料／4state樣本、EXE、BUILD_INFO及helper pin保持，無金融資料寫入；Main0／worker與pool0且自然刪除。Root看過首頁實圖，不外推所有尺寸的17路由。

QA121 R139只fresh重開R134同一筆記，未再保存、未複製來源。原expected／first／fresh三份JSON與Journal、四來源SHA保持；實際DPR1.5，1280×760邏輯／1920×1140實體，日期、收盤、完整來源身份及保存身份三欄同屏，Root看過全窗實圖。12 frozen模組及正常Main0／worker與pool0／自然刪除通過。QA120 closure `adf2636b7af5315f67da61d142188b2dc7c14d0822b6c4ba3af7f1560df7bab6`、QA121 `e0e800261ef854d8ec614383f049a0ca89203a21a29965ffa902d1973cb1d2e0`，三PID列表皆空、process／Job handles關閉、mutex釋放，無強制清除。

Canonical `DELIVERY_RECEIPT.json` 與本task `delivery_a65d2b2b4fd5.json` 相同SHA `720f6b02a26a719a47f7b02b686d45e7af6cb7eb93acda72d2ac4eeab6e19240`；11個pin為EXE、BUILD_INFO、材料manifest及其8個材料檔，manifest本身不含EXE／BUILD_INFO。收據逐項記真正驗證版本：題材上一／下一與150%路由沿412ca證據，正式兩股producer／fresh沿2b，Registry 2b功能成功但audit整輪FAIL保留；不宣稱本a65另執producer或全部舊旅程。新版包7,134files／976,499,191 logical bytes，build5,276files／315,558,345 bytes，非SSD唯一實體配置。累計5份本task EXE，未清理；Credits USAGE_UNOBSERVABLE／UNKNOWN、原累計12,500額外授權跨session沿用，未購買或改計費設定。

本機技術候選可沿包內GUIDE操作，未簽章、未驗跨機可攜、未替換active delivery。正常關閉後可用保留412ca／2b或研究13原啟動器回退，各用原state、不合併、不遷移。五旅程overall PARTIAL、Product Acceptance NOT_ACCEPTED、Native USER_STOPPED_ESCAPE、真人MANUAL_ACCEPTANCE_PENDING；真今日候選、完整Main月營收綁定、Paper完整現金與合法marks、自然Forward、歷史PIT／全市場／ML Promotion維持具名Evidence Backlog，不阻擋已接受的安全產品功能。

## Paper前置流程與100顯示（QA123–126）

QA123 對同一固定 `a65d2b2b4fd5` EXE 補驗 Blueprint 明定的100%：17路由只在1280×760／實際DPR1.0，1500×900、1440×900、1920×1080另驗首頁；root看過首頁。五個既有設定目錄只核 `already_present`（meta_data只含空backup），不建立或複製資料；8材料／4state／EXE／BUILD_INFO保持、worker／pool0及自然刪除。closure `ebcdce1a8805122cc7a8baec420cd286ecf5c7f23dc1e47773d3f9e80af4dac5` 全閉。Canonical交付收據維持原SHA，新證據在本task `r142_dpi100`，未重寫收據或建包。

R141／R143進一步靜態核對發現具體產品缺口：QA033預覽的是Equal Weight benchmark，不能證明一般研究候選的資格預覽／人工確認／Paper建帳。策略cash-seed只服務已綁定精確策略帳戶的空倉500K政策，不能接一般股票研究。後繼source R144補第一層「保存研究→原件重核→Paper條件檢查」：Timeline只傳同一entry，Main背景 `read_evidence_baseline` 驗原件及來源，成功才開唯讀對話框；換選、refresh、離頁或shutdown拒收晚到結果。可查看既有Paper頁並返回同entry，建帳停用；沒有寫Journal、建立部位/NAV或提升資格。通用候選建帳producer及合法帳戶／mark／cash契約仍是未實作的程式缺口，此前置層不替代整個旅程。

QA124 編譯、47個新UI／Main信任邊界與原Timeline定向、Workbench85、更新頁25/0/4、mypy1108全部通過。QA125探針誤以 `passed` 核對舊R134實際 `PASS` 狀態，在Main啟動前退出，原CASE與失敗保持；closure `607ab0e20ccb7044e86669f77c117a2879c96cd26360cea46052914375353a1e` 自然排空。

QA126 R148只修探針狀態對齊、另建小CASE，重用R134原報告／Journal及R114四真來源，不重新保存、產製或複製價庫。正常MainWindow（非 `main()` entry）於1280×760／DPR1.25，經UI選原報告、檢查Paper條件、查看既有Paper分區、返回同一時間軸原件。對話框720×680／實體900×850，完整64字來源身份、原文與缺件可讀，建帳按鈕停用；root看過兩張圖。原R134 expected／first／fresh三JSON、Journal SHA `b56b49a3306aad59c30daa351866e49ccd4d50cb35ca0cda8bb979d11aeb73ce`、四來源保持，SQLite sidecar缺席；worker／pool0、隱藏後deferred-delete完成。CASE-only audit拒絕舊輸出根的日誌及手動成交讀鎖寫入，應用降級顯示其持倉缺件；這次只接受新增對話框與路由往返，不宣稱完整持倉/Paper狀態讀取或零寫入嘗試。原件未改，未放寬audit以求通過。

QA124 closure `a60e178214be9d36cee6662414a3bdf125db975ad92983cb6e5e78b82f36af7b`、QA126 `3ce3bc13fffb15ac79806eafdc37d4de2b47ade38690fa038a043777f2eb129b`，所有Job三PID列表空、process／Job handles關閉、mutex釋放，無強制清除。未新EXE、未改a65交付包、舊包或正式／私人資料。

R140另證QA035月營收view通過的是直接注入合成fixture，非正常Main真binding；現行ApplicationSettings與Main接線存在，但四個cohort／series環境鍵及當前本機config均未配置。已向Owner詢問外部固定SHA的合法binding路徑，不重造fixture或提升資格。Native停止、五旅程overall PARTIAL、真人待驗及長期金融Evidence Backlog保持；完整目標尚未達成。

## Paper baseline未知值拒絕（QA128）

R149修復既有 `PaperPortfolioBaselineService._decimal` 將缺失或非法總分／收盤價補成0的缺陷。轉換現在拒絕None、bool、非法文字及非有限Decimal，錯誤指出欄位，且在配置服務前停止；明確觀測0仍保留原零目標／無效價格診斷。正常來源的Decimal金額、政策、排序與日期未改，不建立任何Paper帳本或提升資格。舊None→0測試改為明確觀測0，另新增未知不得進配置負例；沒有降低缺值守衛。

QA128 compile、baseline service／CLI與既有配置sandbox共26測試、受改module mypy全部通過。CLI無效輸入時新輸出不存在、既有輸出bytes保持；這些是隔離fixture的工程回歸，不是真來源或建帳接受。closure `617622026067a06c777dfe4810277da1ef617b60801a02ca1c67421c0241aeac` terminal0、三PID列表空、process／Job handles關閉及mutex釋放，無強制清除。新backend變更沒有UI接線，沿用未改UI的QA124／126證據，未重跑或重建EXE。

R150／R151另核實：嚴格publication-row reader與策略帳checkpoint鏈可重用，但行情availability／用途與quote-event／官方session、精確保存結果及帳戶cash鏈均須原契約。CSV人工確認匯入只有成交／成本事件，缺研究原件／result ID／candidate key及mark/cash provenance，不能作一般研究建帳producer。不得把空倉seed、研究股價或現有CSV匯入升格為候選建帳資格。完整Paper正向流程仍未完成，合法輸入問題待Owner提供；五旅程、Native／真人及長期金融狀態不變。

## 選股保存與歷史返回（QA130起）

R155／R159補統一選股儲存入口，明確映射七種來源原生收藏按鈕；保留原 typed payload、writer 與核驗門檻。V4 套範本後阻止收藏舊 Query，只有新查詢成功套用才解除；失敗或取消不解除。R156補完整保存報告與價格詳情的最新入口、原件 token 回訪；排名、H20與舊缺圖報告仍保留原分支。Main 將新查詢的日期／result ID／pins清空，返回前背景重核，並拒絕過期回傳。一般全域查股返回不刷新或重設投組／自選帳種及子頁。

QA130 編譯、Workbench85、更新頁25/0/4與mypy1108通過；定向122通過、3失敗為新測試替身未掛stock_research及誤用strategy_library作route。失敗保留，closure `91149cb357497a3edeb138f04d27d2a06a0ff2cec8b2d325d90ae916473c6bd6` 自然排空。Root修測試替身，另在靜態複核發現並恢復被候選誤漏的舊缺圖報告分支，增加對應回歸。

QA131 編譯、126定向、Workbench85、更新頁25/0/4及mypy1108全通過，closure `15cf306822c187934cbbac9fe95409b74987fa89e0e203bed60fe49dc2c00f01` 自然全閉。QA132 R162正常Main選回既有R134報告後，回訪原件逾時，尚未到latest步驟，不能視為正常Main往返通過；Journal、來源四pins及原三JSON保持，worker／pool0並自然刪除。closure `e2f02df2092fcf01664768cec7bcff5a9efdfd3f3bee77961e524174991583f6` 三PID陣列空、process／Job handles閉、mutex釋放；R164只新增診斷helper，不改原失敗證據或放寬CASE-only audit。固定a65 EXE、Native停止、五旅程PARTIAL與真人／金融待驗保持。

QA133／134新增只讀診斷後，原件開啟與乾淨latest均已完成；返回時的完整例外定位至 `legacy_journal_changed_during_read`。原Journal bytes／SHA、size、mtime_ns、ctime_ns、inode及device保持，只有讀取造成atime變化。Root將比較限定於穩定metadata，保留身分、大小、納秒修改／變更時間及存在狀態的拒絕防線；新增7項守衛案例。QA134 closure `a2e75a83bdfbbb5e5d481cfc38ae2b804630d39325c7db403755806472701fdc`、QA133 `e8acd9dfc6fe070eb501ade8e3b723327e609af236c2b902b40dd765c649fcdf` 均自然全閉，原失敗保留。

QA135 compile、193項定向、Workbench85、更新頁25/0/4及mypy1108通過；另11個既有私人根整合案例因basetemp放在程式包內而被路徑守衛拒絕，整輪FAIL保留，未放寬產品守衛。closure `d660e8fa9175b9b9ca5db56f634f669ba7a6d40df0985c39402958c366f00abd` 自然全閉。QA136把該測試根移至task實體外部位置後15通過、1失敗；最後personal模式案例定位到缺失Journal的讀取會建立1-byte鎖檔。Root另補缺失PERSONAL store空讀取分支，不改已有store的鎖、writer或CAS；後續驗證另記。

QA136 R168正常MainWindow（非main() entry）於1280×760／DPR1.25六步全通過：真R134保存報告→獨立latest完成→原件背景重核→相同canonical投影→原時間軸同筆記，另檢視統一Save入口完整122×44且按來源狀態停用，未點擊或另存。Root看過latest、返回原件及選股畫面；Journal `b56b49a3306aad59c30daa351866e49ccd4d50cb35ca0cda8bb979d11aeb73ce`、四來源及R134三JSON保持、SQLite sidecar缺席、worker／pool0及deferred-delete自然完成。CASE-only audit仍阻舊log與手動帳讀鎖，不宣稱完整持倉讀取或零寫入嘗試。整輪QA136因上述私人模式案例仍FAIL，此Main切片限定接受；closure `7dce123561d3976795b562aa9d97e25de291f6184b4320ad9a984e61b1ef68e4` 全閉、無強制清除。固定a65包未重建，完整五旅程及金融／Native／真人接受不升格。

QA137在程式包外隔離basetemp重驗，編譯、209項定向（包含16個notes composition、7個metadata守衛及5個缺失store／CAS新增案例）、Workbench85、更新頁25/0/4與mypy1108全通過；未略過或放寬原失敗案例。closure `439a1a3900384ccbc8a9b64f52842c03ef37520a46a9ea013aedb5dbb2c7647c` terminal0、三PID陣列空、process／Job handles關閉及mutex釋放，無強制回收。新增缺失store分支只影響PERSONAL空讀取，QA136 R168所驗legacy只讀報告返回分支未改；不重跑已接受報告流或build。

R170對既有R111／R112最多八檔有界核對：證據是TechnicalUniverse V4產製／查詢／比較／個股返回，沒有價格詳情需要的typed price bookmark或selection。未將它冒充價格來源，未建新helper或造state；新價格latest的實際Main往返仍NOT_RUN，工程定向包含signal、原selection、token及strict reader dispatch。一般保存報告的Main證據與此缺件分開判讀。

QA138既有個股詳情動作／V2版面／導航另8項通過。文件全檢首輪FAIL包含root同步字串誤替換的UI文件連結（已恢復HEAD原正文，僅重加新段落），及研究分冊原有output/trial junction越界連結。保留原FAIL，closure `0f5ae7db4aacb5daf03abd133fadcd30c2c88b7f8ac0f876228d601625540395` 自然全閉；最後收斂檢查五份非junction正文與task／Feature Map，Manual／Snapshot／研究分冊的新diff由root另審，不宣稱其舊全檔連結通過。

## 價格詳情另開最新與精確返回（QA140–141）

R172／R173釐清R170的定位界線：F07價格來源由既存V4 strict parent callback投影，不需要另一producer或預存typed bookmark。R42既存generation `d259dd1f68ad0485c5523fc3ad48d48c2d3a091b21e716f2306210f5b6602f04`、plan與完整receipt四檔SHA仍匹配；R98原證據顯示可由正常PriceView建立真正PriceSelectionV1，不能直接將V4 row轉型冒充。這次沒有產製來源、複製價庫或手造typed state。

QA140 R174正常Main已完成原來源／最低價1查詢／2317 typed selection／獨立latest／strict重核同詳情五步，最後helper誤要求隱藏工作區內的price子頁也必須清空而逾時；保留畫面是既有設計，原FAIL及收據完整保留。Root另建R176，只移除該不適用predicate；原查詢、頁面、row、選列與可見來源頁的判定全部保留。

QA141 R176在相同Source commit `1d0a6d30e993af0dccd6e9a98444a045b8b6d459` 完成六步正常MainWindow（非main() entry），1280×760／DPR1.25。新latest context的歷史日期／result ID／pins為空；返回核strict原source與typed selection，恢復同price page／view／context，再回到query `5fe8208c0fbe31fff07d3bf419016aac0b1c33e97e35959ad2012bfc14fdcb90`、page `41ebd7806b77436c1244db9b90cdbe428d81755e366ee6e1759aa5aeea767d62` 及2317同row。Root看三圖；四來源index、R114價庫SHA、R134 Journal與產品source保持，worker／pool0並自然deferred-delete完成。來源僅兩股保存研究，availability unknown／historical PIT false，沒有保存新Journal或提高金融資格。

QA140 closure `7670b66c510625a5c94649f2aa6850199335a5454985f1faadadc7c0926b32ff`、QA141 closure `6b61d6ae690f2b753542132409d728ea11be32f990503d50e552b7435ef00383` 均三PID陣列空、process／Job handles閉、mutex釋放及無強制回收。固定a65 EXE仍不含後繼Source；累積Paper前置檢查、baseline未知拒絕與本輪保存／回訪／Journal修復，接著以一次重要整合候選收斂可操作出口。候選建置及包內驗證另記，完整五旅程、Native／真人與金融缺件不升格。
