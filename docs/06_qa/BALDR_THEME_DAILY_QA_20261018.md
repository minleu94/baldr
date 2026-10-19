# Baldr 題材每日研究：後繼實作與驗證

Owner：Root Sol；task `output/tasks/baldr-post-completion-execution`。以2026-10-18使用者正式修正採Active Resolution Gate，不把前置缺人工簽核當全產品阻塞；原補完Gate、143候選與舊FAIL保留。

## M1 後端受改範圍

新增[聚合](../../app_module/theme_daily_service.py)與[明選SQLite讀者](../../app_module/theme_daily_sqlite_reader.py)，未改原萃取器、正式資料／Task、策略／評分或私人帳。精度、分母、來源時鐘與缺件契約見[設計5.3](../02_features/INDUSTRY_THEME_MAP_DESIGN.md#53-後繼每日研究實作2026-10-18)。

- `m0_init_qa01`：透過document_control建立本owner task、重新綁定runner TASK／spec／隔離env／結果目錄；原865收據保留並複製作閉鎖起點，舊task不寫。
- `m1_domain_qa02`：context／compile／41 pytest通過；mypy因同名loop變數推斷衝突FAIL。原spec／log／收據保留。
- `m1_reader_qa03`：修正後compile、52 pytest（含原映射6項）、兩個新增application模組mypy通過。沒有UI改動時未重跑未受影響Workbench／validator。
- 外層收據：`single_owned_qa_805a7e6a1ae34243b09579f24ae20356/receipt.json`，SHA256 `6f4b41ec2a5399331ef59d8728c8372e717bf7365314d12321143d25f7e901a0`。8GiB committed／12程序／kill-on-close／同workspace mutex；自然終態，三PID陣列空、process與Job handles關閉、mutex釋放，無強制清理。

## 真實資料工程量測

`m1_real_data_qa03/result.json`保存2026-10-16單日只讀transaction的1949筆成員行情、2537映射列、90題材與25鏈；不是全DB custody或真N接受。正式4GiB DB只讀，原CSV前後hash一致，輸出另存在owner task。

原映射SHA `d9e50b02ec0dfe5f1eed130fac9855664ef9e649cd3aa627e9a0924d3b258491`；所選價列JSON SHA `d0c6dbb75f8c687cbef36013974c5259f4b309f790d71c2540493aac39b12e7d`；本機新DB副本SHA `9719bd90239f9171e0323e77c1b5229fc8755560f647b17f8516f25fb3f84f00`。

來源查詢0.024秒；五次聚合0.02590／0.02602／0.02781／0.02596／0.02511秒，中位0.02596秒。這是本機限定工程量測，不是效能SLA或正式排程。擷取完成UTC17:43:27.197300，保存可用小時為UTC18:00（台北10/19 02:00）；量測明示使用該離線測試cutoff，沒有宣稱真實時鐘已到或提前成熟。

每個題材獨立揭露覆蓋率；多標籤下的2136筆已知漲跌與2141筆已知成交額為跨題材計數，不是股票母體或案例完成率。本次只選價格，沒有聲稱正式DB缺少法人；輸出副本不含法人表，五日交易日曆也未提供，因此相關值維持None。

## M2／M3定向驗證與原FAIL

| 組別 | 實際結果與修正 |
|---|---|
| QA04 | compile通過；161 pytest通過、2 symlink環境限制略過，5 UI測試因環境沒有qtbot而ERROR。沒有安裝新前置，改採既有QApplication／QTest。 |
| QA05／06／07 | 原真滑鼠雙擊及外層viewport測例FAIL保留；修正測試定位與無效的父viewport visibleRegion假設後，原滑鼠互動通過；validator25/0/4。 |
| QA08／09 | 筆記／呈現及既有Journal相關測試54通過；1項測試錯用不存在的store屬性。改核隔離根沒有trades.jsonl後，該項及新增兩檔mypy通過。 |
| QA10／10b | QA10有45通過、2 symlink略過；新資料日tag因DTO freeze轉tuple，讀者只接受list造成5 FAIL。讀者接受原不可變序列、仍核唯一canonical資料日後，11筆記測試及三檔mypy通過，含兩Journal實例交錯寫入的過時CAS拒絕。 |
| QA11／11b | QA11有90通過（含原Workbench85與Main3）；筆記UI初始5秒逾時與關閉後成功訊息2 FAIL。保留5秒、補既有1ms GIL handoff及失敗狀態診斷，確認成功後立即回報保存；原逾時根因不下定論。QA11b四筆記UI及兩題材換股守衛共6通過，validator25/0/4。完整mypy／正常Main仍待下一組。 |
| QA12 | 首頁題材入口、原Workbench、Main與個股相關回歸53通過；所有受改Python compile及完整mypy1076通過。既有UI ignore設定與untyped body提示保留，不宣稱UI強型別。 |
| QA13 | 正常Windows Qt Main已建立、真實時鐘載入10/16本機版本並留1280×760／1000×700邏輯視窗圖；QA未將成員目標點捲入外層viewport而FAIL，尚未進個股／寫筆記／新程序。原helper、隔離env、截圖及log保留；另開QA14修精確點定位，不移除可見性斷言。截圖亦發現來源長文壓住結果，受改頁將以短摘要及按需來源明細改善。 |
| QA14／15 | QA14受改題材UI10通過；原點定位仍FAIL。QA15用32px安全邊距及幾何收據通過實際滑鼠、首頁接續與2330路由，繼而發現新context缺少current scope，原保存來源守衛使價格留空。只於Main明確使用既有current_stock_research，沒有放寬任何保存來源守衛；兩組原FAIL保留。 |
| QA16 | Main／既有current scope回歸5通過，正常Main11508→另一新程序22232通過，完整mypy1076通過。正常頁確認題材10/16與一般價格9/23分開、同源原頁篩選／選取／捲動返回、原筆記及追加修訂／保存時鐘與新程序Journal bytes一致。 |
| QA17 | document_control全域及本task scoped檢查通過，無errors；結構檢查不替代功能或正文驗收。 |
| QA18／19 | 保存worker的局部關閉保護4項通過；真Main保存第三篇獨立筆記失敗。QA19診斷確認是同快照共用筆記實體根，觸發原Journal修訂鏈守衛，並非取消或逾時。兩組正常頁FAIL及診斷原件保留。 |
| QA20 | 修正為每篇獨立根、修訂沿原根後，16項通過；stale祖先測試把原ValueError誤寫RuntimeError而1 FAIL。原守衛確實拒絕，Root僅修正測試例外類型，保留message及原件bytes不變斷言；未改Journal／CAS。 |
| QA21 | compile、17筆記／關閉定向測試、正常Main及另一新程序、完整mypy1076通過。Main在第三篇真Journal寫入等待期間保持視窗，完成後關閉；新程序讀回三筆精確原文／修訂／來源／保存時鐘，Journal bytes一致。 |

最新功能QA閉鎖收據`single_owned_qa_54c756897f1f4cc48db096a6e4c6c148/receipt.json` SHA `466bdfbd6e2e1308bb291bd5341680cf863325b15981dde3cb70400fd6799c3b`；原FAIL與spec／log完整保留。上述每組均沿Root同Job資源限制自然結束、三PID陣列空、handles關閉且mutex釋放，沒有靠強制清理取得PASS。這些數量不是Milestone或完整Gate加總。

QA21結果`theme_close_fresh_qa21/result.json` SHA `a0591eb56e0bfd08d4fefb03ac67987f8d8c6f520043799d54fa1a58999d23f4`；Main30660→6852，Journal SHA `6f4b82dad67357f1b1ba30999174ebf280af3eefa029bc1b5b670c07b63fb508`。保存期間關閉使用真Journal，只有寫入前的QA觀察閘；原5秒期限／可見性／來源／原文斷言保持。未以保存的成功訊息代替磁碟與新程序讀回。

正常頁結果`theme_main_fresh_qa16/result.json` SHA `be89c7db041754df629b9a23bfe756b1d6faff58e1d432ebd0a7587a3c418e77`；兩程序Journal SHA同為`32370741928e020e377cdb1c01cb1c7bc2b009f153a8aa5a0227653b7a29dad2`。來源manifest SHA `75f97365b03adf2d84efaad03250dc2510ba2eb8517b3212ea2c20166060ed7a`；讀取發生在真實UTC18:22，已過保存可用UTC18:00。網路／正式根／舊trial存取嘗試均為0。一般價庫來自143四股DB的隔離副本，沒有宣稱全市場一般報告可用。

Root已檢視原生Windows QPA背景圖；1280×760邏輯視窗在本機DPR1.5產生1920×1140圖。窄窗請求1000×700受既有Main最小高度約束，實際1000×715，沒有宣稱精確700或其他DPI通過。來源長文預設收合，觀察卡及排行在首屏；此為Qt程式操作／渲染，不是OS座標操作、真人簽核或固定EXE接受。

## 接線與獨立複核

重用既有calendar_static做唯讀金融／PIT與跨頁複核、registry_pair_ui_leaf只寫題材／首頁葉片及測試、reader_regressions只寫snapshot測試、portfolio_scenario_static只寫研究筆記葉片。Root保留共用服務契約、Main、金融判讀、QA與文件；沒有新建代理或讓worker跑Python。

獨立複核促成三項修正：非整時區先轉台北再向上取整；裸日期／來源字串不能授五日曆資格；題材報告不得手動換股沿用原成員身份。日期與一般行情分開標示，換股先返回題材明選。current scope另經calendar_static狹義複核：報告／內建registry的事件日與行指紋取一般行情，不把題材hash／日期當ML輸入；可顯示同股同行情的通用current研究，不保證按題材隔離模型結果，外插provider未驗。筆記保存不寫入歷史decision_date，實際created_at與資料日tag分開；服務仍信任caller提供已讀回的snapshot，不宣稱自身是來源認證或磁碟防竄改系統。後端契約檢查不替代正常Main、同版EXE、真人接受或原完整Gate。

## 未完成與限制

### 原D固定EXE技術出口（QA36b）

本項解除原D「三筆明選對照、歷史原結果與新程序」尚無完整固定EXE技術證據的阻礙，不改原V1範圍。使用已驗移位的題材01隔離副本，固定來源仍為`f02b7ebded3044bba80cef91d4b46d9d7ab7711f`；EXE／模板／143／私人state不改。三筆exact run及原金融identity以本owner的`predecessor_d_existing_oracle_qa36.json`另存並核SHA，沒有重算或重存原研究。

QA36首次停在結果頁可見性斷言；QA36a保持15秒等待仍FAIL。窄窗實際紀錄確認1280×760 Main的回測寬1096，正常單欄模式先顯示設定，必須按「查看實驗結果」。QA36b補這個正常UI動作，未移除可見性或放寬期限；兩次原FAIL、helper及收據保留。

固定EXE Main43972→新程序41448通過：明選MA／W底／布林三個原保存run、2330共同419觀測日及2025-01-02～2026-09-23提交期間；逐一查看原規則，關閉／重開對照，歷史查找exact原結果，再回同一Registry開啟已讀對照。共同輸入SHA `bbbb583c2e222de064f329fe6f5fa310c72228866e70853e5b8ebf018992adee`；三筆原金融identity、研究原件清冊及Journal SHA均前後／新程序一致。網路／受保護根／策略執行或保存嘗試均0，產品模組全取固定包；Root已檢視對照渲染圖。

結果`predecessor_d_frozen_main_qa36b/result.json` SHA `9cdf3e29a92c75739eaeec46f47496d89534aaaa887e29367460d2bf45f44a57`；閉鎖`single_owned_qa_45487ea608b34f05bc5e7c7f37ad820b/receipt.json` SHA `aedb0dd4440cb5911ccaf45dcd519990fd6f6978c381d8ae6ab6d257bdd08e22`。8GiB／12程序、三PID陣列空、handles關閉／mutex釋放、無強制清理。此為Qt操作的限定技術出口；原意圖不是成交，PIT及績效可評旗標仍false，真人D、Native及完整Gate仍待，不將技術通過作人工批准。

### M3判斷回訪比較（Source，QA38／39）

本葉片解除回訪須逐篇切換、憑記憶比較判斷的阻礙。重用Luna只改筆記widget及既有UI測試；直接父子版本同snapshot SHA／資料日才可並列，根筆記／缺父版／錯來源／錯日／自指拒讀；切換、刷新失敗、忙碌與關閉清掉舊內容。比較只投影已載入的原文，不新增IO或寫入；原Journal／CAS／保存契約保持。

QA38 compile、105相關測試（含Workbench85）、validator25/0/4、mypy1076及Source正常Main29668→新程序32636通過。兩版原文與Journal SHA `a9f3458955a16358b8b467afe7c72fe5d0cc1d2e2cc901133af643f312198609`不變，無網路或保護根存取；結果SHA `3831794989496b32966e41c21e95194e59752fd56d9f9998d8a7f719addf8b4e`。Root檢圖發現請求800px實際撐到1022px，該組不證800px可用。完整SHA改放身份tooltip，正文短識別；QA39只重驗受改7項UI及compile，含8,000字原文、實際800px／雙欄各自捲動、完整SHA及零額外service呼叫，通過。改後正常Main幾何待下一整合組，不含於f02固定候選。

QA39閉鎖`single_owned_qa_e03772a5fd1f4d66a509b73ec642bc1c/receipt.json` SHA `12d5f2f241756ba993ab1d7b930320cd3c56d98e39005b6f1b2bcd35ab6f32bd`；自然終態、三PID陣列空、process／Job handles閉、mutex釋放、無強制清理。原完整M3、固定EXE／真人接受仍分開，既有UI mypy ignore不證強型別。

### M3個股首屏與回訪整合（Source，QA41／45a／47）

本葉片解除首屏行情事實被持倉關係覆蓋、H5成熟狀態被誤作個股理由的阻礙。重用另一Luna只改個股view及新增定向測試；本次技術線索沿原去除保存／歷史理由的規則，明選保存推薦須同股票、loaded context identity及原決策日／資料日吻合才顯示支持與反對原句。無反證不代表支持，空風險不代表沒有風險；ML與自然結果不補空白。完整文字仍在tooltip及原分頁，載入／失敗／切換清舊。沒有新producer、DTO、評分或金融計算。

Root以實際報告核對查詢日2026-10-19、行情／技術資料日2026-09-23，修正兩處把`as_of`稱作資料日的標籤。舊測試只更正一個標題期待，原日期2026-09-08及其他來源／PIT／期限斷言不變；原件SHA `6663ffe7d53e48fd317368966a1b4e92b035d66cf80860c3c9d80105ab4ffaf9`另存本task。新案例另外核對查詢與實際資料異日，不用改日期通過測試。

QA41 compile及157項通過，既有鍵盤載入case在原2500ms FAIL。QA44定向12通過／同case FAIL，但observer因pytest模組名不同未捕獲狀態；QA45未執行，另存45a先完成不相依的正常Main／共同防線。45a的診斷temp父路徑錯導致13 setup ERROR，原件保留；QA46只修診斷路徑，原wait／期限不變，13項通過並實測鍵盤case2.359秒。Root再於測試等待迴圈補既有慣用1ms Python執行緒讓步，保持原2500ms及所有內容斷言；QA47相關個股模組70項通過，該case觀察0.079秒。這支持測試等待需公平讓步，不宣稱已證實先前每次逾時的唯一根因；產品載入／關閉邏輯未改，全部FAIL／ERROR與spec／log留存，不以重試抹去。

QA45a已獨立通過validator25/0/4、mypy1076及Source Main33996→49660：筆記兩版精確原文、實際800×520、切換清舊、2330正常搜尋框／載入按鈕、9/23收盤2,500.00 TWD與原來源SHA、股摘要事實／保存推薦分層及新程序一致。Journal SHA仍為`a9f3458955a16358b8b467afe7c72fe5d0cc1d2e2cc901133af643f312198609`；網路／保護根嘗試0。結果`m3_notes_stock_main_qa41/result.json` SHA `a94814e9dfdc106622cbf583331c0fa9a3233e7ca1b44835dfc4e8a16493d2f0`，Root已檢圖。原一般價庫與來源缺件保留，未明選的保存判斷仍不可用；沒有通用一般個股筆記入口，不把題材筆記冒充完整M3。

QA47觀察收據SHA `97135245b7d2e85937ad000bd4bbccf1c029fab0a616deff94e7334125558169`；最新閉鎖`single_owned_qa_c4582521992143e0a252261437841ad2/receipt.json` SHA `d9eee550ac5a834fa1d4df02bfa344d69bfb1f386a82affc491b0707768e0059`。自然終態、三PID陣列空、process／Job handles閉、mutex釋放、無強制清理。這批Source尚未含於f02固定候選，完整M3、同版EXE／Native／真人及原Gate保持分開。

### M4固定候選進度

Source已提交`f02b7ebded3044bba80cef91d4b46d9d7ab7711f`。QA22 scoped文件檢查12 features／33 link sources通過；QA23只移除題材UI尾端空行並compile，沒有重跑未受影響旅程。QA24沿該commit的git archive建立固定EXE，SHA `d04ad3ff55ab526071f3133b9c8a8a4c9191583ba62ac29b844d91dad39faffb`；build結果SHA `a8e2713a0564cace3050fbee6265c2b2ef94a1300922a12b052e2332b9af0279`。建置成功不等於同版正常頁接受。

QA25把原141c封存資產、自有具名名冊、新runtime與獨立題材三檔逐bytes組到全新`Baldr-Theme-Research-01`，不讀舊143私人state。清冊SHA `7bda65893a5081e1c6b005409581e0c70f9486d9d0fdb5069dd4ebe337993dda`，組包結果SHA `0d3da8ead71bf6572127288f1ce67135eeddafe04c3dcbe1c5d9d5202f161d48`；9877 copied files只是檔案清冊，不是案例或完整Gate。閉鎖收據`single_owned_qa_48c8d8ce2d7f498db32f469645067a31/receipt.json` SHA `0dbda0db1b00adadde6a43efc7367e1c04f5f9e044a9bdd409c06aa5aab9b33e`。

QA26在完整正例即發現Windows PowerShell缺`Get-FileHash`而FAIL，尚未啟動設定或Main。原腳本、spec、log與失敗收據保留；QA29只將未交付候選的外部驗證器改用既有啟動器同樣的.NET SHA256，原件留在具名patch目錄，EXE及資料不變。新驗證器SHA `f7252d4980d01fd5d148597636c3dc60d9fd112cc410c0af1f03e2dedd04f221`；完整三檔接受、同長度損壞／缺件／多檔拒絕已通過，reparse動態測例未執行。

QA29的固定EXE移位後首次設定通過，實測494.391秒／原600秒；結果SHA `725bdc1dca27408c1149c3bdc8779c9b80386b75761272b8fc67b2597f7989cb`。視窗測例匯入包內未收的QtTest即FAIL，尚未建立Main；不為測試往正式EXE增加依賴。原FAIL保留，QA32改用包內Qt事件API，命中位置／可見性／期限／來源與原文斷言不變，沿已驗設定副本接續，不重跑設定。

QA32固定EXE正常Main28556→9036通過：同一題材版本／2330一般行情往返、來源篩選與位置、三筆精確原文與修訂、保存期間關閉及新程序讀回；Journal SHA `a9f3458955a16358b8b467afe7c72fe5d0cc1d2e2cc901133af643f312198609`，結果SHA `c8d24a86f66688185fa59734f5bf2fa581138e9162946109a3d4ac79bcf6b57a`。所有已載入產品模組路徑均在該EXE的resource root，網路／正式根／舊trial讀取嘗試均0。Root檢圖：DPR1，1280×760及窄窗實際1000×709；不把請求1000×700或Source的DPR1.5幾何當成此版結果，也不授Native／真人接受。

同組finalize在清冊`Path.rglob`遇Windows長路徑FAIL，Main與新程序結果保留。QA34改用既有`_tree_layout`／`to_internal_io_path`，核同SHA既存provenance後只完成清冊／交付封存，不重跑設定或正常旅程；封存通過。交付收據SHA `de60528bbc95da097b6f1e6f9a53c300fc7d677c0c1826908c0d04a315a7d5e4`，final結果SHA `e819e2fe8384549632b580806409a7351f11b8092fa7e0773c82d753c3ac7736`。最新閉鎖`single_owned_qa_1b1022d3c6024429a3316c158210b4ef/receipt.json` SHA `af54f79190676ebf20b949d9edf7ddf22959d856c294e674757d5920f1cc0359`；自然終態／三PID陣列空／handles閉／mutex釋放／無forced cleanup。原143交付SHA及141c資產清冊SHA仍未變；新模板沒有state或QA筆記。

### 首頁候選明選Source葉片

重用Luna實作Workbench與單一新測試檔，另由既有Luna狹義唯讀複核，未改Main／DTO／金融來源。多檔預設未選、單檔相容；選第二檔沿同一原來源／日期context，刷新同源保留有效選擇，換日期／snapshot／逐列identity即清除，所有候選捷徑重核membership。QA30a：compile、112相關Qt測試（含既有Workbench85及9個新選取案例）、validator25/0/4、mypy1076通過；既有單檔斷言未修改。閉鎖收據`single_owned_qa_3bdc5e28e2834cf2a67e0f98e4d89c90/receipt.json` SHA `4493934fea6812238d20d7468004f1348920d66c61fc786e625adacffd34d3e0`，原始validator報告另存本task。這是合成候選的Qt／context技術驗證，不宣稱正式多股來源、同版EXE或真人接受；此葉片未含於f02固定候選，待下一次有意義的功能批次封裝。

### M4題材02固定候選（QA49／51／53／54／55）

本批解除「筆記前版比較與個股首屏改善只在Source、沒有同版可試用EXE」的交付阻礙。固定Source `b292f803ce9c08c39eeb1102b0c30fe18896ec41`，QA49以乾淨git archive建置，EXE SHA `2dfba4f2439406fbe62ece846e4ac60e81904d94d86dd914c4702fed5253b02c`。QA51另建`output/trial/Baldr-Theme-Research-02`，manifest SHA `30db72e9f2f789215d2e47123229ff0bd09f12f9ad579740277956909be36602`；原資產bytes保持，名冊另存自有task具名副本與custody收據，非正式來源用途接受。01、143、141c、其他owner task及私人state不改。

QA53全新副本放到本機含空白新位置，首次設定492秒／原600秒，結果SHA `086eca868e2d83cce97a0607c6e8b59d2449a07887091db70866319e5e3522cc`。固定模組均由EXE resource root載入；沒有網路／舊trial／正式根存取，原模板無state。

QA54固定EXE正常Main49584→新程序21272：題材原來源／篩選／位置返回、2330行情事實與查詢日分層、三篇筆記原文／直接父子版本／完整來源tooltip、實際800×520比較及保存期間關閉通過。兩程序Journal SHA同為`493f971a57911103f40b971005dd1fdfbe9a95ddc3cc583a0ef40ff1e6bb57a4`；結果SHA `15099975b31f830e07355916ee080db22b5b5b77bb892d49335cbbcfcb9d355c`。Root已檢圖，網路與受保護根嘗試0，沒有從Source補載產品模組。首頁只核明選控制項已包含，真實多候選固定旅程未驗，不能以QA30a合成測試替代。

QA55啟動器正例0／錯EXE SHA反例2通過，隔離副本config／setup receipt／Journal前後不變；未更改驗證器，沿QA29具名四案例原證據，不重跑未改旅程。交付收據SHA `b044c2eb15760f20c903b375c4e9eccc9c3b5913cc2ce9193c7164c24735a4a2`，template inventory SHA `b85edc8d447889987de2c9d6022f6092299fec52506a1680e2bafa676e45b89a`，final結果SHA `37e4b83b1519dc371d6af5af142ff781f0f88b61ab5bd606ef624f12a548bc9a`。最新閉鎖`single_owned_qa_d41d6eaa94294055ab08bb198a9e1782/receipt.json` SHA `6667aa5139602cc5f881c135a34b3fe27093b39a372e2674b7271eb22974251e`；每組均在8GiB／12程序Job與workspace mutex下串行、啟動RAM≥8GiB，三PID陣列空／handles閉／mutex釋放／無強制清理後才起下一組。

02限定交付為PASS WITH KNOWN LIMITATIONS。一般價庫仍只有四股至9/23，題材樣本10/16，缺法人／合格五日曆；一般個股通用判斷保存、完整M3、Native／真人／跨機接受仍待。本輪沒有重新執行Source未改的70個股、Workbench85、validator或mypy；這些沿前述具名Source證據，固定受改旅程另驗，不把兩者混成完整Gate。

題材Source與本機固定候選旅程已取得限定出口，首頁控制項也已封裝02；完整通用研究閉環及其餘原UX清冊未關閉。前置原D技術出口已由QA36b補驗，真人簽核仍分開待；官方來源用途／精確可得性／歷史PIT／TPEx授權／真N／自然成熟不因本輪解除。沒有新增正式資料寫入、backfill、maintainer、push、發布或交易授權。

### 原價格版本的個股判斷（QA62至QA70）

本批解除F07價格選股進入個股後缺少「自己的判斷保存／修訂／回訪」入口，限定`technical_price_saved_source`；不把題材或單一行情row hash當一般整份報告。兩位既有Luna分別單寫新service及widget／測試，Root持有Main／Workspace接線、共用ports、金融判讀、QA及文件；第三位Luna寫獨立導航測試。沒有新建agent，所有Python由Root串行。

`PinnedStockResearchNoteService`沿Journal ACTION_NOTE／CAS保存canonical既有bookmark、完整原文、同股身份與直接修訂；原文存payload，Journal摘要保留原正規化。資料日、原研究日與真正保存時間分開，不製造推薦result／decision身份。widget以背景worker讀寫，按下開啟時重新核對原件；失敗仍可讀原文但拒開啟／修訂，換股草稿保留原來源，已送出寫入須合作排空。Workspace以同一可捲動筆記頁接回原bookmark route，沒有新建金融reader、第二帳本或放寬來源守衛。

QA62為8 PASS／1 FAIL：Journal摘要會strip，而decoder曾要求與未strip原文完全相等，造成有效追加後decode失敗。原檔／斷言保留，僅修decoder比對既有摘要語義，payload原文不改；QA62a原9案例及compile通過，閉鎖SHA `ce84471fff7cf26d39815128a93d33165c1fb1c3b170a228222d74c72a73255b`。包含同股／同來源、獨立根、直接parent、CAS／過時祖先及真缺原件隔離。

QA64 compile通過，111 PASS／4 FAIL；既有Workbench85等未受改部分沿此證據。四個新測例先後修正測試長路徑copy、Qt等待的Python執行機會及錯誤文字預期；保留原期限、來源守衛與產品斷言。QA64a其餘8案例通過，QA64b缺原件案例通過；validator25／0／4與八套件mypy1078通過，原validator程式不改，輸出只重導本owner目錄。閉鎖SHA `ce96e5cd77f2cdcfddfd9b7d4d9f28101e2edb11d4117ba33f066fe828f9f1e9`。既有`ui_qt.* ignore_errors=True`不證UI強型別。

QA67補開啟當下的背景重驗：9 PASS／1 FAIL，原件消失時原文、exact error、未發布來源與按鈕停用均正確，唯一失敗為open狀態文字。QA68只修該文字並compile，原失敗案例6.85秒通過；沒有重跑九個未改PASS。新UI／導航與backend證據只支持指定契約，不能累加當完整Gate。

**正常Main未通過，不能交付本葉片。** QA68／69在啟動即被產品設定守衛拒絕：QA自建config誤加僅供env的`RUNTIME_STATE_ROOT`；只修測試設定，不改產品。QA70成功建立Main，但2506原收藏重開180秒未進同源個股。QA72加外層捲動及真可視點擊斷言後仍逾時，已證double-click送達，controls停在背景exact來源核驗，尚未執行筆記保存。QA74同期限只加60秒堆疊，60／120秒均在`_reverify_all_child_batches`／snapshot repository的link-component／lstat完整核驗鏈；最後程序回碼`3221225477`（存取違規），原因未歸因，不能直接宣稱是產品或診斷工具所致。所有spec／原FAIL／log／stack保留於本owner task的QA63／63a–d、QA68–74目錄；沒有重跑同一結果目錄、放寬180秒、略過原件或授通過。

QA70閉鎖SHA `105ccee1d6224fcb2acc5d149161452e2c8a4d19f8e213bdd3663121dbf7872c`；QA72為`276ef1f4130de7656d4330fae15c21512adcc12cd04ab4e9f54c108b4c0bb18c`；最新QA74為`0efc219525e601a264523d172c988fc94844f2df93e056f98334e03220eb23c8`。每組8GiB／12程序／kill-on-close／workspace mutex、啟動RAM≥8GiB，三PID陣列空／process與Job handles閉／mutex釋放／無強制清理後才接下一組。網路及保護根嘗試0只限上述已讀診斷，並非通用安全或全機程序接受。

固定02／01／143及私人原件保持；未建03，也未宣稱新程序、EXE／Native／真人／完整M3通過。先停止這條相同完整來源旅程的重試，後續須先有具體reader診斷／修復；不因此阻塞一般四股報告可往返codec。QA71在允許QA資產找不到至少兩股的保存run，正式runtime及未檢視owner資料保持Unknown；首頁真實多候選未接受。QA73／75已定位並凍結一般完整report/context codec新葉片，尚未實作或QA，不能把靜態契約當保存閉環。

### 一般整份報告codec（QA75至QA81）

本葉片解除一般個股報告只有非對稱`to_dict`、沒有可精確讀回完整report/context的技術缺口；不是新總計畫，也尚未完成M3保存閉環。Root75凍結API，重用Luna單寫`stock_research_report_snapshot_codec.py`與單一新測試檔。完整report/context及nested型別保留，顯示float只以hex表示往返、不新增金融算術；未知類／自訂Mapping拒絕。75a另明定排名context的建構子會`Path.resolve`，v1在建構前明確拒絕，不能繞過原DTO驗證。其餘來源與資格不升格，模組不建立store或重查來源。

固定候選原件：module SHA `aad06dc648e0a07aa907530c9fcb8498209c566c6ba6d9d31dcae7160b7a4011`，tests SHA `e42b69356d447a0f5d2da8b9e9bb9fe1da9a6b9bf68d52a43ce4e9f2614a9aa4`。Root已備QA78四股public report實際往返與QA79串行compile／定向pytest／mypy／四股驗證spec，spec SHA `fe1eb0a3096a8f9224b14df948640b4c62abdae8a164f8c7bfafcd25284de55b`；這些均**未執行**，沒有Job或結果收據，不是FAIL測試或PASS。

QA79原命令兩次遭自動核准審查在啟動前拒絕：正常五小時額度100%，審查認為既有10,000上限仍不足以作本次QA79的明確credit授權。Root已讀原Goal §0／4.2並附最新使用者修正§4重送同命令，仍遭拒；沒有繞道、改名執行或啟動Python，已請使用者選擇授權本次驗證或等正常額度實際恢復。帳戶共用淨差與預算歸因只在本機task記錄，不當產品測試證據。

獨立Luna已完成只讀QA81，報告SHA `ceab3f0d90bc86c82d6f5cbbfc82b7a22244b46f1abe0e99c3994091eff86cad`：輸出DTO的nested Mapping/list仍可變；依75a，canonical JSON+SHA才是權威，store/render必須重新解碼，不能信任可被修改的公開DTO。另node cap目前在JSON parse後檢查，文字／整體序列化的配置前界線並不完整；不能宣稱所有配置已先受node／byte預算限制。這些仍待Root裁決／必要修正與真正QA，沒有標整份review通過，也不為本次新增streaming重構。後續若改bytes須另存新spec／結果，保留79未啟動原件。

沒有使用者可見新入口；操作手冊與固定02沿原版。下一步只在授權或實際正常額度可用後處理具體bounds問題，驗codec／四股真投影，再沿原M3接Journal與正常UI。保留F07原Main限制、真實多候選來源缺件、完整Gate／真人／PIT／真N及自然成熟各自界線。

### 一般報告保存整合（QA82起）

本批解除一般報告無法保存當時完整依據的M3阻礙。使用者恢復後實讀正常額度可用，沿原目標繼續；沒有以credit繞過QA79拒絕。舊QA75–81及未啟動spec原樣保留。

QA82修文字長度預檢、JSON parse前node掃描與有界canonical累計，編譯／19項codec測試通過；mypy三處型別窄化FAIL保留。備份原碼後只補明確Mapping cast與dict guard，QA82a編譯／相同19項／單檔mypy通過，沒有新增ignore。QA82a四股helper未設定正確現況scope，原來源守衛拒絕價格；只修helper明選`explicit_latest_stock_research`及`ml_scope_mode=current_stock_research`，不改產品或價格非空斷言。QA82b的2330／2317／2382／2454既存只讀價庫public report/context完整往返、canonical SHA與`to_dict`一致通過；Main可選providers尚未組合，不能冒稱正常UI。

QA82b原件在owner task的`m3_report_codec_real_qa78a/result.json`及`m3_report_codec_commands_qa82b`。最新Job收據SHA `1bb04669a92a78d60111d3aa831d970e3e3e1a65540a5d4f85053fa072c887fe`，三PID陣列空、process／Job handles關閉、mutex釋放、forced_cleanup=false；8GiB／12程序／啟動前8GiB可用RAM保持。

Root QA83凍結沿既有Journal的typed完整報告payload及ACTION_NOTE身份，兩位原Luna各單寫新service/tests與新widget/tests；第三位只讀複核共享ports。Root持有Journal／ReportView／Workspace／Main、金融判斷、QA與文件。尚未驗證的新保存／修訂／獨立保存時報告頁及正常Main／新程序仍是WIP，不列PASS。沒有新agent、第二本ledger、交易寫入或上游用途／PIT資格提升；原F07來源效能分支及人工接受分開保留。

QA84首次編譯通過，受改定向及既有回歸為125 PASS／11 FAIL；失敗屬既有私人Journal整合檔的Temp位於程式包內。QA84a改Temp時又遇sandbox的LOCALAPPDATA重映射父路徑不存在，16項setup error原樣保留。QA84b改用已核實的使用者Temp後14 PASS／2 FAIL，兩個Main測試的ML mock仍是過時零參數；備份後僅接受現行`repository_root`參數，私人路徑與無建立斷言不改。QA84c為1 PASS／1 FAIL，私人模式啟動建立目錄的缺陷仍在；不能將前述數量相加當完整Gate。

Root先取消新報告筆記元件建構時的自動讀取，改開頁／查詢後讀取。QA84d編譯通過，8 PASS／2 FAIL：一項比較測試仍假設建構自動載入，另一項私人Main無建立斷言仍失敗。進一步定位Main原題材筆記也會在建構時自動讀Journal；因此補相容的`auto_refresh=True`參數，Main明示False、選「產業與題材」才刷新。比較測試改明按刷新後保留原比較／原文／無額外I/O斷言，另增延後讀取回歸。這組最後修正**尚未編譯或QA**，沒有宣稱啟動缺陷已解除。

QA86為有限只讀ports複核，SHA `4dc179255db49862acfda4e86de5464803574491fe984737e2c0cd61c0332a31`；未見指定入口重查producer或提升PIT，但要求widget核選取與generation。Root已檢視widget在emit前的`_job_is_current`及`_matches_fresh_note`交叉綁定；仍不取代正常旅程。

最新QA84d Job收據SHA `1ef360555778a379966e2f989e27f159948d4a4c9c8bd7ec6755927c13f0989e`：自然終態、三PID空、handles關閉、mutex釋放、forced_cleanup=false。QA84e spec已另存（SHA `291fa686008e28b83e35032f594ef1a947d83c3d5a53bb83c4479a1feb63b998`），啟動前正常五小時額度100%／週80%，Root據此未呼叫啟動工具；沒有QA84e Job或結果，不是自動核准拒絕。恢復後須重綁新HEAD／bytes另存spec，不直接跑舊HEAD spec。

Workbench85／validator／八套件mypy因前段fail-fast尚未執行；QA85正常Main／四股保存／精確報告／直接修訂比較／關閉等待／新程序尚未執行，固定03也未建。Source以未驗證checkpoint保存；固定02／01／143、私人原件及其他原FAIL不改。後續先完成這批出口，再依原清冊推進，不重跑未改的F07逾時旅程或將等待人工接受當全域阻礙。

### 一般報告正常Main／新程序（QA89–93）

本批解除一般完整報告判斷仍無正常Main與重開證據的交付阻礙，沿同一M3實作，不擴充金融功能。正常額度實際恢復後，QA89重綁HEAD `bc3a80ec7f1a84d7b39d3607fbc4927fc073f460`：編譯、11項定向（含延後讀取與私人Main）、Workbench85、validator25通過／0失敗／4跳過、八套件mypy1081檔通過。mypy原有UI ignore仍不證明UI強型別。自然閉鎖收據SHA `bf5016cb9f04b55767081fceab01e431ef7f87451004a2e51b8e4af1856abf8a`。

QA90–90b保留第一股15秒未完成的原失敗；階段觀測停在籌碼讀取，另確認測試繼承本機candidate DB。90c明示owned不存在的candidate路徑並禁止原candidate目錄存取後，讀取完成，ML階段仍超時。QA93以相同空登錄直接觀測：構造0.0287秒／讀取0.0286秒；不支持生產效能修正。QA92既有Luna只讀複核亦保留此反證，未改Source。

90d僅在helper的事件等待迴圈讓出5ms，原15秒、非空價格及來源守衛不變；四股載入完成。後續90d–90f失敗分別揭露helper未等筆記刷新、`held_save(**kwargs)`讓TaskWorker額外注入cancel_callback、fresh未等清單列就緒；只修測試同步與包裝簽名，沒有改產品API、資料或放寬斷言。各次spec、結果、錯誤及自然閉鎖收據均保存在owner task，不互覆。

QA90g在正常Source Main、1280×760、prod隔離設定，以既有四股只讀價庫載入2317／2382／2454／2330。2330保存原文、另存直接修訂、開啟保存時報告各tab、返回及800×520比較；第三篇保存送出時要求關閉，視窗等待真Journal結果完成。程序52760結束後，程序1940未先載行情即明選三篇、開原報告與直接比較；完整canonical內容、Journal／watchlist／價庫SHA一致，producer讀取為0，網路及受保護存取嘗試均0。Root檢視原報告與比較截圖；這是Qt事件自動旅程，不是Native座標或真人接受。

原件：`output/tasks/baldr-post-completion-execution/m3_report_notes_main_qa90g/result.json`；spec SHA `ed445e84bea0dec0869bc9f304bb8d60559bff2b5724d546a33b4588fb48ff14`。Job收據 `single_owned_qa_436990c1e237403ba9fc0d12e469c545/receipt.json` SHA `dc6783a1ccfef908b4de7d3d42aeac68955dfd8efd3189aed092954fa3d61886`；三PID陣列空、process／Job handles關閉、mutex釋放、forced_cleanup=false。8GiB／12程序／kill-on-close／啟動前8GiB可用RAM保持。

本次candidate籌碼、ML run、外部營收等未隨隔離資料提供的能力仍為不可用，不接受其完整金融結果或來源用途；既有缺件保持。固定03尚未建，02／01／143原件保持。F07完整來源慢讀、真首頁多候選缺件、真人D／Native、授權／歷史PIT／真N及自然成熟各自保留，不阻塞此已具依賴的保存旅程。
### 固定03：一般報告保存交付（QA95–99）

本批將已驗Source的完整報告判斷閉環交給使用者試用，解除只有工作樹、沒有固定候選的交付阻礙。固定Source `519233422d0085b27785dd1b7f7d892be98de5c0`，EXE SHA `c7d3f9798f758fda2c0424b083717cc7ab9e322d69f016f2bbba4f585de2e669`。QA95沿依賴鎖從固定commit建置，QA96沿141c封存原bytes組包，不開來源SQLite或連網；名冊另存本owner的`trial03_display_roster_qa96`，只供顯示、不改金融或來源資格。新啟動器明示自有缺件candidate路徑並清除外部ML設定，不沿用本機私人候選資料。

QA97將完整新包複製到含空白的新位置，再用同版EXE首次設定，實測545.922秒／原600秒。沒有回讀舊trial／正式根或網路，portable config及2382官方月營收原五值讀回一致；原交付模板始終無state。spec SHA `e5a9b3d5674e4b5d2cf265d568891f8586958616323f76aa9f0c8eb66d0ff54a`；Job收據SHA `69b96be7b572fe608e9e2dfc4e3c0c91ac1470aec58817c20539894e9fbfb558`。

QA98初始helper用了正式包未包含的QtTest，在Main前失敗，原件保留。QA98a只沿固定02既有的正式Qt事件adapter，沒有加產品依賴或重建EXE。固定EXE程序48996→44680完成四股載入、2330三篇判斷、完整保存時報告各tab、返回、直接父子800×520比較及保存期間合作關閉；fresh未先載即重開，producer讀取為0，Journal／watchlist／價庫SHA保持。每個關鍵產品模組均核在包內`_internal`，build identity為同一固定commit且dirty=false。Root檢視固定版截圖。這是Qt事件自動技術旅程，非Native座標／真人。spec SHA `04aa546d35218091c4986b697e2c09f05369d2bf3aa2b56454c2100a07abb196`；Job收據SHA `a42b93640eefcb6db31435e5174136a29c6a0daf3b73c1e84114279aadc4c4b2`。

QA99在隔離副本驗啟動器正SHA成功／反SHA拒絕，既有Journal、設定及setup收據保持；複製具名來源／名冊／首次設定／Main原件，建立模板清冊與交付收據。新包`output/trial/Baldr-Theme-Research-03`，manifest SHA `01e91aaec3fd9b1caca9062fbd82b1f97222838be012e3dcbc289c95d0465f93`，交付收據SHA `28c61cfd6439ff8e374f49e7d8c6fb41abd941ace3c3fb5a4ba8ea548171127a`。QA99 Job收據SHA `6b17489132adbb61b51eb69636ed53e01cfa8a7046874d03e9aa90e1dd831c76`；本批各組三PID空、handles關閉、mutex釋放、forced_cleanup=false，原資源上限保持。

本次只接受一般報告保存的限定技術出口。原F07專用筆記未完成正常來源旅程，程式含候選葉片但不算03可用流程；未改題材／日常／Registry沿02／143／01證據，未反覆重跑。四股價格9-23、題材10-16、2382半年財報缺件、歷史PIT／TPEx／來源用途／真N／WF與自然成熟、真人D／Native／跨機及完整M3／Gate均保留。02／01／143／139／141c及私人原件不改。

QA101依原M4執行不帶path限縮的document_control check（含owner task）：12features／36link sources、無錯誤；這是工具預設檢查範圍，不是全文EOF或產品接受。Job收據SHA `a04061c6da0300ef46319bdb21b52468136b999dd7fd945b63a1dc3a41fa8afc`，自然閉鎖。
