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

## 原價格來源讀取與取消（QA100–105）

本次只處理原價格收藏筆記的真實流程阻礙，不新增金融用途或擴充第一版範圍。研究03已封存可試用，一般報告保存沿03原證據。

QA100保留原180秒來源期限與整段240秒：來源180.016秒未完，未到筆記，正常FAIL；閉鎖收據SHA `5a2466f1e2b500c4404cd6576bb4efcdbaaca9d9d6492348cbda820fdc08a58b`。舊native crash本次未重現，但未歸因。

QA103同2506原收藏、原public full-strict reader在無UI下57.509秒完成；plan.to_dict902次／5.816秒、repository.read_exact122次／46.012秒。QA102靜態複核確認122次是第一次完整child驗證，不得當作兩遍全圖；session消費verified batches，選取物化另有有限讀取，次數不由該計數推算。未做生產效能修改。閉鎖SHA `8f808645c5312f2afbe2e5d2d1a13f6129610c7fdb50f20b2033b00b94513f03`。

QA104移除helper殘留的QTest.qWait，沿已驗processEvents＋sleep5ms，Source／來源守衛及120／180／240秒均不改。正常Main原收藏56.718秒成功，筆記來源再核對60.031秒；第一篇Journal確有追加，但保存後刷新尚未完即達subprocess原240秒，owned child由subprocess逾時回收。整段FAIL，不以一篇保存或來源成功升格完整旅程。收據 `single_owned_qa_98a50c856ac84bf6aa772539abdbff28/receipt.json` SHA `8acdc85213e0eb85092076948dbf91571478d736274f7b100802667d8d4d1c5f`：三PID陣列空／handles閉／mutex釋放；wrapper未啟強制清理不代表child自然完成。原堆疊、observations及失敗結果保留。

QA105修復候選：唯讀verify API將TaskWorker取消callback傳至既有public strict reader；InterruptedError原樣傳遞，不誤報原件缺件，不產生部分結果。save不新增取消參數，仍fresh核對後append/CAS。Root單寫shared port／整合QA／文件，重用兩Luna單寫backend tests與widget/tests，累計代理10/10無新建。必要編譯、定向／跨頁、Workbench、validator、mypy及真2506取消probe狀態以後續收據記載，目前待驗；未重跑F07整段或已通過未改一般報告旅程。固定03原包及私人原件保持。
QA105編譯PASS，pytest的24個案例因Root用環境LOCALAPPDATA產生不存在的sandbox Temp父目錄而setup ERROR，未跑案例；原收據SHA `f85ecf10365f29cd7cb33f822949392dc34b0f1a7aae9a3595df8ab99e12ef30`保留。105a另存spec，採已驗固定Temp父目錄，Source／斷言不改、不重跑編譯：24定向／跨頁、Workbench85、validator25/0/4及mypy8套件1081 PASS（既有ui_qt ignore_errors不代表UI強型別）。真2506取消probe在0.868秒停止，但底層取消以typed `technical_parent_v4_read_cancelled`一路包裝，服務誤當來源失敗，該項FAIL。原結果、watchlist SHA／network0／protected0保持；收據SHA `c579c0c101cf53593b8486c39daef3338c016927265f34e45bf6fa076215d868`自然閉鎖。

105b只修服務邊界的明確取消碼轉接：需同時收到該typed code與實際callback取消，才轉InterruptedError；其他來源錯誤不因取消旗標被掩蓋。新增四個正反案例，save仍不取消。Worker後續因capacity失敗，Root已接回所有權；兩新Qt測試改觀察native_thread_finished而非存取deleteLater後的worker，不放寬自然完成斷言。接續只驗受改backend／兩取消UI與原保存關閉／單檔mypy／新真來源probe，不整組重跑已通過未改防線；最終結果待本組收據。
105b編譯／19定向／單檔mypy PASS，真來源取消仍FAIL：Store包裝在code前加technical_universe_v4，錯誤文字仍為parent碼。Root沿實碼核對後補明確三碼allowlist，不用字串suffix或callback旗標吞任意來源錯誤。105b收據SHA `59841576a0c288623adefd6f23164c159e548798c0132ccb7e96f4026beeccac`自然閉鎖，原FAIL保留。

105c最終限定PASS：受改編譯、10個取消正反／UI取消／原保存關閉案例、服務單檔mypy；真2506原public reader合作取消完成且未回傳來源，watchlist bytes保持、network0／protected0。原180秒期限保留。未取消完整來源／金融守衛及原來源缺件案例沿105a／105b已驗範圍；未更動UI的Workbook85／validator25/0/4／8套件mypy1081不反覆重跑。這些收據各自界定範圍，不作案例加總或完整Gate。最終閉鎖SHA `f5515127f936b5650a40832000569e1e8be9da54d3a1242954150a50140df3f9`，三PID陣列空／handles閉／mutex釋放／forced_cleanup=false。全程Root串行8GiB／12程序／kill-on-close，啟動前RAM至少8GiB。此次Source修復不改已封存03，完整F07整段仍未驗收，不能宣稱解除其240秒阻礙。
真來源取消實測秒數：0.894902500032913；結果SHA 55b7214912be04b93c722d1a0f71d8d8a084ba22e45a98c4f948243da5a8250e。

QA106文控含owner task：12features／36link sources PASS；最後閉鎖收據SHA `2769c79ee549693bf2375dce0c55f495fd8d2236fce9dfe4db20fa183c479622`。僅結構核對，不代表正文全EOF或產品接受。正常五小時／週用量皆95%，credit餘額53727.8877155000全輪未變；按user近額度約定收尾提交，不啟動新功能或完整F07重試。

<a id="首頁-paper-同版本部位導航qa108112"></a>
## 首頁 Paper 同版本部位導航（QA108–116）

解除的原 M3 阻礙是首頁明選 Paper 健康列只能泛用切頁，持倉頁可能仍顯示手動帳同股。QA107 靜態核現有公開 read model／exact archive 邊界後，QA108 沿原工作區接 `PositionHealthReadModel` 與唯一 `position_id`，沒有新增金融 DTO、評估、帳本或 writer。Main 先排入下一次刷新；持倉頁用自己的 reader 核完整同版本及唯一部位後才切 Paper。失配、缺件、重複 ID、舊 generation、取消及關閉均拒絕，不回退手動同股；歷史 exact receipt 不從 mutable status path 推造。

QA112 編譯通過，106 項受改檢查通過、1 項新測試 FAIL。該新測試錯把「刷新後重新明選新來源」也當作必須停用；Root 保留原件並只更正期待：刷新清舊選取，舊來源不送出，重新明選才送新 model。產品碼未因這次 FAIL 改動。QA112a 該項 PASS；Workbench85、validator25/0/4、mypy8套件1081 PASS。原 UI mypy ignore 不證強型別。112／112a 自然閉鎖 SHA 分別 `a247fb3d261a048a23da73a0da1eed6e6586473d5802b2ce8be417e7a0c0317e`／`23221df1fc699eb975a3477b250e1fda7933ade826580cd5f9d56086cefa0adb`。

QA115 正常 Source Main／新程序的缺件停用、同股票不同部位定位、來源改變保留手動帳、返回首頁選列／捲動等邏輯通過；Paper 正例明示使用控制 DTO，沒有自然 Paper 原件或保存驗收。Root 檢視 1280×760 截圖發現選中列仍在實際外層可視範圍之外，因此沒有將邏輯 PASS 當完整 UX。115 收據 SHA `a4f3890f40c4892dd095e056dcdc018950a36a90a5878bca55be939d3ba784c4`。

QA116 先補下一 Qt 事件的精確列捲動：編譯、52 項受改持倉、Workbench85、validator25/0/4、mypy1081 通過，但正常 Main 真正外層 viewport 斷言仍 FAIL。116a 只加有界幾何觀察，證實首次 callback 時 scrollbar maximum=0／列中心724、viewport737，後續 layout 才擴張；不是來源身份錯配。原15秒／120秒期限保持，兩組 FAIL 原件保留。116／116a 收據 SHA `d4162c0ce0e94d676a3206dbedde39978a81f0b707133950ea3120d5fc9207c0`／`679f07c9cda7d9cc8cb353162da74633abbcc8b82d5989b251832de2d68d2a9e`。

116b 修復只對仍有效的 generation／完整 model／選列／Paper 帳及可見工作區，等待有界的版面穩定再捲到實際資料列；不建立跨動作 cache 或放寬來源守衛。最終收據另記。固定03未收入本葉片；控制資料不授自然 Paper、歷史保存重開、金融用途、真人／Native 或完整 M3。Root 串行8GiB／12程序／kill-on-close／啟動RAM至少8GiB；每組三PID陣列空、handles閉與mutex釋放後才起下一組。

證據保存勘誤：116沿用112 validator helper時，報告路徑仍指向同owner的112報告，該便利報告被新時間覆寫。112／112a原spec、command stdout／stderr及閉鎖收據保持；原validator接受依這些原始命令輸出，不以被覆寫的便利報告冒充原件。116報告另保全到自有116目錄，後續helper須用新具名路徑。

## 真實多股保存來源的限定核驗（QA109–114）

解除原 M3「只在QA資產尚未找到真多股來源」的證據缺口，沒有重觸發每日 Task。正式推薦 runs DB 經有界實體 bytes 保全，原件無sidecar／reparse、前後SHA一致；原DB未直接開SQLite。30筆canonical及88筆legacy metadata，canonical artifact共34,220,468 bytes保全到本owner。來源DB SHA `2370eab15a47d359ccb5bf50b8f00f08fa64ea74d3e7bed9aa0e105ed8bfa9af`。

109 schema盤點通過；110 helper誤把帶sha256:前綴當裸hash而FAIL；110a碰到原32MiB總上限而FAIL，29檔保留；111只新增最後一檔有界保全，之後audit誤拒SciPy的NUL裝置；111a又誤拒既有reader的SQLite :memory:。原FAIL/spec/log均不覆寫；僅精確修QA裝置／記憶體庫邊界，不改產品守衛。111b完整保全後，整體public list因副本內legacy絕對data_path仍綁原root而拒絕。這是移位副本的root守衛，不證明原正式來源壞掉；沒有重寫path、刪列或弱化守衛。111b閉鎖SHA `849f0c1701895d1bc0d6e39db4387e8097dca6e08a988f12dcaf0bd078ebc08d`。

QA114只用已保全owner副本，以原公開 `queries.get(result_id)` 明選兩筆canonical並通過原payload／index核驗：2026-10-19結果 `rec_3a4acdb159d841cc91492de258c1a0a9` 有5股；2026-10-14結果 `rec_0575414398f14eb8b2661191a140f158` 有32股。各自 `ml_read_status=unavailable`，未授ML或歷史PIT。這次沒有正式根I/O、producer、網路或資料寫入；DB及artifact copies保持。結果 `m3_canonical_selected_read_qa114/result.json`；spec SHA `1ee9369e647a465d97514931eff2d330de27aa81147f59b1c668e362649afcc5`，自然閉鎖SHA `5fa5aed6fa1e65fbce1b958aad924194e8f7e1332d408869a901b10c0bffcecf`。這是可供下一個首頁旅程驗證的真保存來源，不代表整體list、正式每日管線、正常Main多股旅程或完整Gate已接受。

QA116b 最終限定 PASS：編譯、14 項受改導航及晚到捲動守衛；正常 Main40912→新程序37776的明選同股第二部位確實位於外層 viewport 中，來源變更仍保留手動帳，返回首頁選列及捲動124保持，watchlist SHA一致，network／protected／Qt error均0。Root檢視1280實際選中列截圖，原15秒／120秒保持；未重跑未改一般報告與題材旅程。spec SHA `941114e56c2da66f8a0478fbf89725002720d81d058ed6f6ecaeb569ce79710e`，自然閉鎖SHA `7d25266e2f7cac848369ecbcdfbe9063ad515721276963472170f11cce7dd364`；三PID空／handles閉／mutex釋放／forced_cleanup=false。這是明示控制Paper資料的Source技術出口，並非自然帳本、持久化、固定EXE或真人接受；完整M3仍待真首頁候選保存閉環。

<a id="首頁真保存候選閉環qa118123"></a>
## 首頁真保存候選閉環（QA118–123）

本增量解除原M3的候選快照身份遺失、返回錯工作區，以及日常選股控制項藏在進階區的阻礙；不增加金融公式或新保存系統。原selector與開啟按鈕移到首頁候選列下方，多股仍須明選；context帶原snapshot，返回同首頁須result/source/snapshot/日期/選股相符。原stale／future今日候選守衛不改，另有明示原保存結果入口，經RecommendationView public exact-open沿既有single get；不經list／latest、不重跑。舊列表expected identity、matching pointer日期／筆數、generation／取消保持，shutdown開始即拒絕新讀。Root保留Main/shared port/金融/QA/docs，兩既有Luna有限單寫，10/10無新建；另一路獨立靜態複核未發現重大回歸，不代替執行QA。

118原status完整65,964 bytes保全，SHA `bcd0241984516a4b7965b3b5a3517aeb73a3ceec4951ede217807ed31e3ddd8c`；原bytes與保全SHA核同。初次64KiB自選metadata上限拒絕時未讀raw；核實尺寸後另立128KiB完整JSON保全範圍，沒有改production/PIT或原測試斷言。回放只在自己runtime另存runs_dir重定位，內層cohort與原status／正式來源不改。

QA120編譯／27受改PASS；11個新Main測試host漏接既有coerce方法而FAIL。Root保留原test/spec/log，120a只補host原方法後11PASS；Workbench85、validator25/0/4、mypy8套件1081PASS。120a正常Main helper未等首次Qt排程的來源完成便取None，屬helper FAIL。兩組自然閉鎖SHA `3b23dae8763e4d42b4cc68c5b99a4f9bde43f51d2b7685cb482b777604e47ab9`／`c40933345a6fcf3814c2b2d6ab4dfe5ec46894c01e63b09f9b49b6bed59f94d0`。

QA121只修helper等待，原15秒／120秒不變。在正常Main組合中，以public DailyInvestmentJourneyService明示10/19原保存日期投影接既有render port，沒有改系統時鐘或將stale冒稱今日。真5股原件中明選1512／1236，各自精確candidate_key、Journal筆記、返回首頁；程序12772→43012讀回兩篇原文、revision及Journal SHA一致（`dd0688d27723f5dc1d8a39c33b69963b634280018deacc69ba1a5952605dd6cb`），DB原SHA與watchlist保持，網路／protected／Qt error均0。Root檢視1280筆記截圖。這是有明示日期投影的真原件回放，不是自然當日首頁或完整行情報告接受。spec SHA `1e781db79316ebc1b99eae3c53b092e0a8aa3b1a38fa0f87c6b9f705a4500d3c`；自然閉鎖SHA `cfca493f99e0a5f32db5793846baa44b45675a73773c269336d9ace1a12bf549`。

QA123改由正常主視窗stale首頁的原保存結果按鈕進推薦頁，沒有注入DailyEvidence或改時鐘。context L3顯示RecommendationView為headings_only／Unknown；Root與workers另讀本次指定symbols及diff，不宣稱整檔或全庫EOF。編譯、89受改／舊單筆讀回與晚到取消、Workbench85、validator25/0/4、mypy1081PASS；UI既有ignore不證強型別。實際Main可讀五股原保存結果、今日候選仍停用，但個股Journey沒有連結完成，整段FAIL。123a只加具名UI診斷查明原因，尚未接受；不以單元數或單筆readback升格完整旅程。123收據SHA `e2c96d64fd8c82add741e30a4eed0efc80a71c14fc8e5a70e16ad7b992a7ebb4`，原件保留。

完整當日首頁、固定04／EXE／Native／真人及M3/M4未由以上回放接受；ML、行情缺件、PIT／來源用途及自然成熟分別隔離。固定03／舊包及私人原件保持；Root串行原8GiB/12程序/kill-on-close/mutex/RAM至少8GiB，每組三PID陣列空、handles閉、mutex釋放後才起下一組。

QA123a保留原診斷FAIL：既有worker已自然結束，但queued UI callback尚未套用模型；並非candidate身份失配。123b僅修helper，等待實際Journey模型、精確candidate identity、筆記控制與workspace idle；原15秒／120秒不變，產品碼未改，未重跑已過且未變的89／85／validator／mypy。正常Main17292→48020，以實際2026-10-20時鐘由首頁原保存按鈕讀10/19五股、明選1512／1236，各自保存筆記、返回原推薦，再由新程序讀回兩篇原文／ID／SHA一致。今日候選仍stale停用；無DailyEvidence注入、日期回放、producer或網路，來源DB與watchlist SHA保持。Root檢視1280截圖。Journal SHA `766c4af3f5ef87f6c7a3436758cf12ec3cab1ab5bc1e29c6a75cd94a902328f2`，spec SHA `7332e3e953e7965f3697b7c83fff7c13582b402855b06290abedc09b74600744`，閉鎖收據SHA `d546444523d54b60e3b1f2850e8d13cb0c2dd9c64236a3ab9c241c6e757e7312`。原stdout沿用舊「日期回放」標籤，但本次helper及result明示未注入；依實際程式與結果判定，不覆寫原輸出。

此PASS只接受原保存來源的唯讀研究與Journal閉環。固定行情不含1512／1236，價格技術等缺件維持不可用；不授完整行情報告、今日自然管線、ML、歷史PIT或整體M3/M4。

QA124–124b為固定04準備最小示範資產，解除必須帶整份私人歷史庫的阻礙。124因原metadata notes非空拒絕；另存124a明示derived display metadata，只改label為「2026-10-19 原保存推薦（本機唯讀研究）」並移除私人notes，不改payload／ID／persisted_at，原庫不變。124a遇QA audit誤解析既有SQLite file URI而FAIL；124b只修URI解析、仍限owner來源／全新目的地。既有public writer→copy→restore→public list驗只一筆五股、原raw SHA及persisted_at一致；沒有新增production exporter或重跑推薦。原metadata SHA `f5dd3ecc89e58099cebe69b9259876cf820fb42a64e569285e3574312b85cb6d`，derived SHA `62bd09706373e24f36cf9d86b9fc1a1a68fbe5bb6a7744beaabb046569688d58`；原artifact `e6523f2b83123a9f2916ddd8326e005c77825542d57ec77aa2be41a05054cf4d`，封存receipt SHA `9c1e1fa7f1a72bf789ab2075631359b4f9d5f269bd01cc6d3b88e0c192dc007f`。新index不冒稱原DB，複製時間不提前原可得時間。124b閉鎖SHA `bc643bc46bc5ea88dcc5d60e917829851269e8981df81d8d7ad429863120e572`；三PID空、handles閉、mutex釋放且無強制回收。固定04尚未建置／交付。

<a id="固定04原保存推薦交付qa125131"></a>
## 固定04原保存推薦交付（QA125–131）

此增量解除原M4「已驗Source但沒有可試固定包」的阻礙。Source提交 `dd55d1b2b0be03c678e51c23cabcdf59e951fa90`；QA125文控12features／36links通過，126沿原建置工具固定EXE，沒有重跑未改旅程或重觸正式Task。

QA127把原141c八份研究fact加一筆10/19 canonical推薦，經public restore／writer／copy／restore及list核驗；原八份raw SHA保持，新單筆原artifact不改，metadata明示derived label／notes=None。新封存research receipt SHA `5c8158cff4c47a8e8f91c16f343146781725ac366e303efd4aa18e9c6fba1946`；模板共三筆可選推薦，不帶整份私人歷史庫、Journal或每日Task status。128逐bytes組全包，原日常／題材／task具名名錄沿原件。

QA129完整新位置含空白路徑首次設定494.781秒／原600秒通過，frozen reader來源均在自有_internal，正式／舊trial I/O與網路0。130因QA spec使用runner不支援的三個env_unset欄位，在compile及產品執行前拒絕；130a另存合法spec，EXE成功讀五股，但QA在reveal前排timer而尚未開對話框便填字，FAIL。兩組原件均保留，不改runner／產品／state，不把helper錯誤當產品接受。

130b只修helper先reveal再排timer，以原15秒／每程序120秒，同版正常Main6028→36076：首頁「選股研究」→讀可用來源→明選10/19原五股→1512／1236各自Journal筆記→返回清單→關閉／新程序原文與revision identity一致。兩程序Journal SHA `2f4725234c2244c2d11cc95448a0acf9614730dccaa27f36dbc1d5ed98e92465`、推薦DB SHA `f4c94b0d24c813f60fbb37deef5f3a665d7b9766d4d84d6c4eff1330a2b22c4d`、watchlist SHA一致，network／protected／Qt errors0。Build為dd55且dirty=false，模組來固定_internal；Root檢視1280截圖。模板今日候選仍停用；1512／1236價格技術缺件、期限連結衝突／未知缺原清單事件與結果，沒有填值或授自然管線／成熟／績效。只接受原保存推薦與筆記閉環，非完整金融功能、Native或真人。

QA131啟動器正例exit0／錯EXE SHA反例exit2，state原文不變；封存TEMPLATE_FILES及DELIVERY_RECEIPT。首次設定後只補指南的實際捲動步驟與期限缺件，原／新文件SHA另列documentation_revisions_after_setup，沒有重驗未變EXE／資產或覆寫原QA指南。04 EXE SHA `0d87d296e1a0519372222d0e3222e4bf5df170ff7a09af4c642fc1dbab724e2d`，manifest `7bd885449d9e2ddbfaa02e2459cddd7bae5d7a35a19cd02be9f50721ecb38094`，交付 `ba2f1417e0f9284c4bfbe83de67675e99eb734a3b2a11ee446c3278dcc15bca7`。完整P00–P14等、自然Paper／forward、PIT／真N／官方權威／真人／跨機仍各自未接受；03／02／01／143／139／141c及私人原件保持。

所有Root串行Job仍8GiB／12程序／kill-on-close／workspace mutex／RAM至少8GiB；各組三PID空、handles閉、mutex釋放且無強制回收。129／130／130a／130b／131閉鎖SHA分別 `83a549c0a339559dd4d8038c8e06109ae436b745ce59acc62dfdc2eb5705d7b4`、`501caa0e3408dc1e6144eb3e769765f67544a13636455c546d6f369d18d73d74`、`dd4311a005ec0b7b7e8490f86899afe5c6b020447ba0f3864333202bdaf301da`、`76288c4998af1b239713b75d9ce65f3fed21e0c2ab79291ecbff8ae1febebd71`、`d06a061c49934df4fb38400684e213526047d36695a0ca11ffeb5bf6aa421c9b`。具名spec／commands／raw/screens均保存在同owner task，舊原件不覆寫。

<a id="題材股票反查qa133134"></a>
## 題材股票反查（QA133–134）

本葉片解除原L2研究頁「已有股票卻只能逐鏈／題材翻找」的操作阻礙，只用已載入snapshot.mapping，不改金融公式、來源、public DTO／signal、Main或保存。完整四碼精確代號／名稱片段列出所有匹配鏈題材與同名股，不預選；定位前核snapshot identity、原鏈題材與成員代號。換版本／失敗／取消／關閉清舊命中，不用舊選項定位新版本。Root凍結API、Luna單寫View及新test，另一既有Luna有限靜態複核未見重大回歸；累計10/10沒有新建，workers無Python／QA／network。

QA133 context L3對View仍標headings_only／Unknown；Root另讀指定symbols／diff／test，不宣稱全檔EOF。編譯、20受改與原導航、Workbench85、validator25/0/4、mypy8套件1081通過。UI既有ignore不證強型別；窄頁只驗縮放／可捲控制，未授其他DPI或Native。spec SHA `fcac0a699a207562f65de9ad5b36a957c00e4220cadd0754f1372eb002fe105d`，閉鎖SHA `f279dcb63cfb7d51d0c6e53da5b87e754033900fa83848672b4b2135c8fa7a88`。

QA134正常Source Main7516→10040使用既有10/16真manifest（identity `75f97365b03adf2d84efaad03250dc2510ba2eb8517b3212ea2c20166060ed7a`），首程序代號2330、新程序名稱台積皆列三題材；明選半導體／光罩後原成員列實際可見，雙擊到原個股context並返回同版本。真reader重載中關閉，舊反查立即清除、合作等待且晚到結果不復活；watchlist SHA一致、Journal未建立，network／protected／Qt errors0。Root檢視1280定位截圖。原15秒／每程序120秒不變，未重跑未改筆記或回測。spec SHA `f97601ff21246f50aae2b92962fb62a74e5405c24aced8b5ce5d412046cd0598`，閉鎖SHA `5ea124bab41ba33f88b0f914b2bad5bac0077ebf52a7a2e20b1e5ff1f7264056`；三PID空／handles閉／mutex釋放且無強制回收。

此為Source技術出口，固定04不改也尚未收入本葉片；查到映射不授來源權威、歷史PIT、完整法人或合格日曆。整體原Gate、真人／Native與自然成熟分項保持；沒有為此另立總計畫或擴第一版範圍。

<a id="固定05題材反查交付qa136140"></a>
## 固定05題材反查交付（QA136–140）

此增量解除「已驗題材股票反查只有Source、使用者仍須逐題材尋找」的交付阻礙，沿原M4固定包流程，不擴第一版五條旅程。Source `34b8e8d5402b407dece718b231cefcfaa27dedb9`；QA136建置、137組包，原日常／題材／單筆保存推薦資產與task具名名冊沿原件。04／03及更早候選、私人原件保持；尚未驗證的推薦首屏排版Source沒有混入05。

QA138將完整包移至含空白的新位置，以原600秒完成首次設定542.171秒。QA139同版正常Main21696→38288：真10/16版本輸入2330／台積均列三題材，明選半導體／光罩、原成員列實際可見、雙擊個股並返回；真reader重載中合作關閉，舊結果不復活，新程序身份一致。build34b8且dirty=false、產品模組來包內_internal；watchlist SHA兩程序相同 `1f0ae10e7217b1d6fcbd95c5fbc8b500b0ff2321b4cb46df42c2dc9b1e228d1a`，Journal未建立，network／protected／Qt errors0。Root檢視1280定位截圖。既有QMouseEvent適配不等於Native座標操作，未帶QtTest或借Source。

QA140啟動器正例exit0、錯EXE SHA反例exit2，state保持；封存TEMPLATE_FILES與交付收據。首次設定後只補指南與問題清單的實測範圍，原／新文件SHA列documentation_revisions_after_setup，不改EXE／manifest／資產。EXE `53ed5302a13ceb1e646933cb3a34fca999d1732d19076c32907d648297391f34`，manifest `d5a64cd7134a3c6b783fefd9c8e3ba83bab50badb0b4919a5a1a7ac7d85ff1f9`，交付 `3bc5a251bce63d0fbd91a099f395b53d8abc0a3dcd6eb7f6960b0341d23d7cf8`。

05沒有重跑未變的保存推薦／Journal旅程，明確繼承04交付收據 `ba2f1417e0f9284c4bfbe83de67675e99eb734a3b2a11ee446c3278dcc15bca7`；其他未改旅程沿03等原證據。只接受受改題材反查、本機首次設定及完整性出口，金融資格、PIT／真N／來源權威、自然成熟、完整Native／真人／跨機與原完整Gate仍分項未接受。

Root串行Job維持8GiB committed／12程序／kill-on-close／workspace mutex／啟動RAM至少8GiB；各組三PID空、process／Job handles閉、mutex釋放且無強制回收。138／139／140閉鎖SHA分別 `eebb7f7ea80edfa65f6d8145700e02ba47b1ac30881f91c930f3d94bbbc9b2f5`、`0ffa9e411adb02e773685ac4acf6f61ab8d942c3cf7aef9fef9e65fd99e39028`、`c981b1a66c35f34ed03705b069a73f3bf3254e1a286beeee553a771fe866ae8c`；spec／commands／raw與截圖均在本owner task保存，不覆寫舊FAIL。

<a id="保存推薦首屏qa142143"></a>
## 保存推薦首屏（QA142–143，後續Source）

此葉片解除QA130b真1280畫面中「結果欄約800px被900斷點堆疊四個來源按鈕，五股表落首屏外」的試用阻礙。Root凍結API、既有Luna單寫RecommendationView與新compact test，另一既有Luna獨立有限靜態複核無重大回歸；10/10沒有新建、workers未執行Python或QA。只在已成功保存讀回的720–899px壓縮來源／標題兩列，其餘風險列900不變；成功／fresh重算、失敗與取消保留。public port、身份／generation、資格及金融值不改。

QA142 context L3仍將View標headings_only／Unknown；Root另讀受改symbols與diff/test，不宣稱全檔EOF。編譯、37項受改／原exact讀回／取消晚到／舊格式及執行排版、Workbench85、獨立具名validator25/0/4、mypy1081通過；UI既有ignore不證強型別。單元fixture只有兩筆，五列空間斷言沒有當真五股接受。spec `05e101839be6908817e59334bd87ef7b8a3151157fc10a2f45029a343ab367bf`，閉鎖 `07baf5f392865796830584124ecabcd76c3dedd6217df97c9fe5e0eb34acac9b`。

QA143沿public restore將具名127最小研究封存還原到全新owner output，行情只唯讀既有05已準備資產；不帶私人Journal／每日Task status。新Source正常Main12900→38268以首頁原選股入口、原list/get明選10/19真五股，沒有DTO注入。1280×760結果欄721px，讀回後未resize或reveal表格／CTA，只將捲軸回頂，即核五筆真資料列完整垂直可見；實際滑鼠選列後「查看個股研究」可用且在首屏。窄窗保留垂直捲動、新程序同原identity／raw SHA，來源DB／watchlist SHA保持，Journal未建立，network／protected／Qt errors0。Root檢視截圖。原15秒／每程序120秒不變；沒有為排版重跑未改筆記旅程或回測。

原artifact `e6523f2b83123a9f2916ddd8326e005c77825542d57ec77aa2be41a05054cf4d`，owner DB `77905a51cc597a9bd79ad402c4fe587d0646ceda602b25188786e798e546459a`，結果JSON `87243e1e3751c9d21c8784268444d5a9de65da115dbba2ac50041e754b589445`。spec `cd93925907a1bc1d62f6d03f5602c0a8ef00c0008af64fca62426215fc4d213e`，閉鎖 `e596fdcf5de647614f04f470c3cd18fa1cd1f29aa03002072b6a7d5d95761751`。兩組Root串行原8GiB／12程序／kill-on-close／mutex／RAM至少8GiB，三PID空／handles閉／mutex釋放且無強制回收。

本次只接受新Source受改排版與只讀重開，固定05 EXE沒有這批修改。行情缺件、期限衝突與原SOP／PIT／正式來源／自然成熟／真人／Native及完整Gate保持，不由顯示五股升格。

<a id="逐期限說明qa145146b"></a>
## 逐期限說明（QA145–146b，後續Source）

此葉片解除139使用者回報「各期限都是相同長說明、無法辨別結果」的可讀性阻礙。只把至少兩種期限且每列都共有的來源限制文字交集集中一次；僅部分期限的降級／未納入警告留在原列。已連結列先顯示原target／gap，非LINKED保留阻擋理由優先；六欄日期／狀態及完整原tooltip保留。loading、錯誤、空表／換context清舊標籤。DTO、reader、原quality／summary／金融判斷皆未改；既有Luna單寫兩檔，Root凍結API與金融界線，另一Luna有限靜態複核沒有重大問題。

QA145編譯、27定向／跨頁PASS、1既有real scheduled Qt opt-in未啟用略過，Workbench85、validator25/0/4、mypy1081通過。146父程序真八列通過，fresh在切入結果頁觸發原重讀後helper太早取None而FAIL；原件保留。146a只等待實際模型，以原15秒／每程序120秒正常Main38776→38772通過。Root檢視真截圖後發現共通限制雖移出，但基本長句仍遮住差異，故另補Display字序，不改tooltip預設原文與金融。

最終145a新增三種target優先／衝突先行測例，31定向／跨頁PASS、同一1項opt-in略過，85／25-0-4／mypy1081通過。146b正常Source Main27256→40692從首頁明選09/10原推薦1538及09/14原推薦1528、原個股／決策結果／返回，八列target首句、狀態、計畫目標日／實際取價日及完整tooltip一致。共通只有年度計畫與未正式採認，四個ready列的degraded／source_not_ingested沒有升為全體。原推薦DB、watchlist、Evidence DB SHA保持，Journal未建立，network／protected／Qt errors0；Root看1280四列截圖。沒有注入Journey或更改outcome、重算績效／補價，也未改原期限。

Evidence DB `eeea9a1a4bbf119bda97465d87e7a9e3b0c1268ffec2f1f9fd9a03248125ddc4`，最終結果 `ce648fbbd0de93e98d787b3316c9eeca335b5275af1cdcb55a934606ccb62946`。145a spec `4bf8a8fac157d6e4d573afa77e3ad5433ba44bdc99326b916b5e038b17745ffe`，146b spec `b69b8a13b6fe34adc5d0b9850d6b8afcaa4c12ea2378f279427c623e321c5c04`。145／146原FAIL／146a／145a／146b閉鎖SHA分別 `27fbfb07bbd6b1927f3d66426f433b76d126bcf98129058b4c33f3f6f95dada7`、`a599be55916ea1a70501c90b49f3355a6204ccfe4c0f2f6036e1f51e6a6f6a75`、`31ef50ac2a913c05c21a1680b99ec7ed5236ec5df6121b7cebfd40efdbf0411d`、`b5173fe0c64e85b193350130b4ea74880ef4108d5687301f4e57c7050bbe6a93`、`05fa20e8dcb126a6e2dfe9bcf7b3202cfcf7fbde150ae508b9f043e22b68ec77`。

Root串行8GiB／12程序／kill-on-close／mutex／RAM至少8GiB，各組三PID空／handles閉／mutex釋放且無強制回收。context仍有headings_only Unknown，Root另讀symbols/diff/tests；mypy的UI ignore不證強型別。固定05尚未含本葉片，原143／139與私人state保持。只接受本機Source受改顯示，不授正式成熟、金融用途、歷史PIT、自然管線／完整Gate或Native／真人。

<a id="固定06首屏與期限交付qa148152"></a>
## 固定06首屏與期限交付（QA148–152）

交付阻礙：已驗首屏與期限顯示Source尚未進可試用EXE。本輪合批封裝兩項，未重跑未改筆記、題材及日常旅程。固定來源`7fbe586705820ed005705b45de7b821737b9b693`，EXE `0c52da0d95982b4af7bafc769afad5609e79332657eaa393b2d3d08df00d6528`，manifest `a94ce98cc5f81e3d46c1503584397fe86d6f906b445ff3a15eec93c90bc35a84`，交付收據`b4b734e484770820faaaf141614211776e0be0ce698a3db0bd8031270a7cec72`。包位於`output/trial/Baldr-Theme-Research-06`，啟動方式與五條範圍見[現行指南](../07_guides/TRIAL_VERSION_GUIDE.md)。

- QA148原1000秒建置及149組包通過；保留原141c資產、自有task具名名冊與127明選示範來源，不混入後續F07 WIP。具名名冊沿`trial03_display_roster_qa96/receipt.json`。私有Journal／每日Task status未帶入。
- QA150整包移到新含空白路徑，以同版EXE首次設定525.141秒／原600秒通過。config、原件、月營收325300／423971／184109／-23.3／76.7及凍結模組來源核對；無舊trial／正式根存取或網路。結果SHA `11c6210de16e9220cc6ec022f3131a1fe38853a39f40925ed870ab57eb6b608a`。
- QA151同版正常Main29824→新程序24664通過。在1280×760、結果欄721px，原1512／1236／1452／1526／1466五列完整垂直可見且選列CTA位於首屏；不是先resize或reveal表格後冒稱首屏。原09/10的1538與09/14的1528經正常入口逐一核八期限原狀態／日期／完整tooltip、共同限制與各期差異首句及返回。原DB／Evidence／清單SHA保持，Journal未建立，網路／保護根／Qt錯誤為0；所有產品模組來自本版`_internal`。Root檢視首屏及1538截圖。結果SHA `63d9abc98463560a1a803bdcf6241e4e861ba28489a8e8e181d2b3bf3e670671`。
- QA152啟動器正向0／錯SHA反向2、模板inventory、指南修訂SHA與封存通過。指南149原件保留，另存152後補實測範圍；只更新新包文件。題材反查沿05、保存推薦筆記沿04、一般完整報告與其他未改旅程沿03等原證據，本次沒有再次接受這些旅程。新五股缺原期限連結，仍不借1538／1528結果。

串行閉鎖收據SHA：148 `433fa6ca1a387f8d1f3f5a585e14db27978c5a138809ea083e5691af2fc1e852`；149 `1c4c325a3768665a6345a3a4d15e62d382d9639fe173ae26812ef9e73f3c4f39`；150 `9ca4c332b0b31aa7a4c07136c91bfd88648b2e43b0041c062611995947d981e4`；151 `7bf0b5c9cf46515df8a612073afff7db2cca2cc289adcd57b4dc05bef494c6da`；152 `78c1d34a074bf4cea617f00af70d4de1cb4a1ef5dea7ac77e917668b6bb81cfe`。各組三PID空、process／Job handles閉、mutex釋放，8GiB／12程序／RAM至少8GiB及原時限保持，未依賴強制回收。

只接受這次固定EXE受改頁與本機新位置設定。Source窄窗證據不當06 EXE窄窗接受；2382半年財報、來源用途、TPEx、歷史PIT、真N、正式日曆、自然成熟、完整雙策略績效、F07原240秒完整旅程、私人state／跨機／其他DPI、真人D與完整Native仍分項保留。封存05／04／03／143／139／141c與私人原件不改。正常額度週用量耗盡後沿使用者明示授權使用既定credit上限，沒有購買／重置或啟用付費API。

<a id="f07保存回讀qa154155"></a>
## F07保存回讀（QA154–155，限定Source）

交付阻礙：保存完成後，widget再完整核對同一來源才刷新，拖延F07筆記。Root凍結`m3_f07_save_readback_contract_qa154.md`，新增不可變`PinnedStockResearchNoteSaveReadback`與`save_with_readback()`；原`save()`回Note不變。保存前仍fresh exact，typed state／canonical bookmark須在Journal append前一致；保留CAS、原文、直接parent與實際保存時間，保存後另讀Journal核唯一對應原文。只在相同generation／股票／canonical且無pending load、非關閉時直接套用；其他情況保留原刷新與確認。下一動作仍fresh，不使用先前動作來源cache。

既有Luna只寫widget／新UI測例，另一Luna只寫新service測例並做有界獨立service／UI複核，皆靜態、無Python、pending_writes=false；Root保留shared port／金融／整合／QA／文件單寫，補拒絕空recorded_at及測例。獨立複核未見具體缺陷，不替代執行驗收。

QA154編譯通過、新舊45定向通過／1原close測例FAIL；該測例仍攔截舊`save()`，畫面已使用新API，故等待閘未啟動。Root只更新攔截點及對應回傳型別，保留原30秒與全部關閉斷言。QA154a該單項10.46秒通過，接續先前fail-fast未跑的Workbench85／validator25-0-4／mypy1081通過；未重跑未改45項，未將案例加總冒充完整Gate。mypy既有UI ignore仍不證UI強型別；context的headings_only Unknown另由Root實讀diff／symbols／測例。

QA155正常Source Main保留原每程序240秒及每步15／120／180秒。首次原收藏核驗74.281秒，筆記來源59.359秒，第一篇保存及清單刷新59.890秒完成；自有Journal實際1列，SHA `4ebd6f85fa5473efadc2141ee9d2136f5b0735a3d5bdf41d4d8d5bda4dfe8617`。父程序在明選讀第一篇原文期間達240秒而FAIL；後續修訂、原版本重開／返回、保存中關閉與fresh均未執行接受。原104及155完整FAIL保留，不能把第一篇保存或定向通過當完整F07。固定06的7fbe archive早已凍結，未含這批Source。

QA157另做一次原public reader的內部cProfile，保持原180秒取消、來源／SHA／語義／路徑與網路守衛；此量測有profiling負擔，不用其耗時冒稱產品退化或改善。122個repository.read_exact、1,951個snapshot的全來源解碼與語義核對佔主要成本，原來源守衛未略過；這不是單純重跑原GUI FAIL。相關profile留在自有task，不以略過全來源驗證或跨動作cache換取240秒PASS。

閉鎖收據SHA：154 `7d407a2e5aa9cf0ff136d9408f525355bfc02a42f531e64f8634ed41b328cb4e`；154a `06d356c099ddda672007402b9de62d6d6af8ce75ec2da967784a4762908eac1d`；155 `93b07d3e217167bee80d5bf3d9c542563c616237e4be2e14f89f37702e605514`；157 `779ad9eb682c84ae85d5716a62e0af852511cc3d93085547047e027d62ee8855`。各組三PID空／handles閉／mutex釋放、無forced cleanup，8GiB／12程序／RAM至少8GiB及原時限保持。原件、正式資料、正式Task與其他owner資產不改。後續Reader效能與完整F07接受仍獨立待解，不阻擋已交付的一般報告／保存推薦／題材旅程。

<a id="固定06的25鏈探索qa158"></a>
## 固定06的25鏈探索（QA158）

驗收缺口：既有UI只驗兩條合成鏈，原目標的25條鏈尚缺實際版本探索證據。重用既有Luna靜態單寫新helper，Root保留worker原稿、補齊執行入口／正式配色、隔離env與原15秒載入界線；無產品Source變更，沒有重建或改動固定06。

QA158由同版EXE `0c52da0d95982b4af7bafc769afad5609e79332657eaa393b2d3d08df00d6528` 啟動兩個獨立`IndustryThemeMapView`，PID17840→10572，沿真`load_snapshot()`讀原manifest，所有產品模組來自本版`_internal`，build來源7fbe／dirty=false，未載入Main。原每程序120秒／父300秒、Root Job 8GiB／12程序／RAM至少8GiB保持。

25鏈集合符合`STANDARD_25_CHAIN_SPECS`；90個題材選項符合原2537列映射。逐鏈明選一個題材，核該題材所有成員的代號、名稱、鏈別位置及原分類依據，再於可視表列單擊／雙擊，股票signal與該原成員一致。首鏈半導體／IC封測12成員、點2329；末鏈文創育樂／`文創/影視展演`32成員、點2926。這是25個代表題材的成員探索，不宣稱90題材所有成員均逐一點擊。Root檢視首／末鏈1280×760截圖。

manifest identity `75f97365b03adf2d84efaad03250dc2510ba2eb8517b3212ea2c20166060ed7a`，mapping `d9e50b02ec0dfe5f1eed130fac9855664ef9e649cd3aa627e9a0924d3b258491`、prices `9719bd90239f9171e0323e77c1b5229fc8755560f647b17f8516f25fb3f84f00`及config／setup receipt／watchlist／portfolio全檔清單與雜湊前後不變。Journal未建立，原兩個lock檔保持；網路、受保護根與Qt錯誤0。結果SHA `42b38c43f0ec35ddf9487b2ab118b36ef5caecc6649adc421ad23f3acd5c0cbd`；閉鎖 `fde828952e5f6bea01711c3d012458ffd4c9a7de5a9d0d002db323a314bf4baa`，三PID空、handles閉、mutex放、無forced cleanup。

只接受獨立view的實際25鏈選取／成員與股票signal；25鏈完整Main個股報告／返回未驗，題材Main往返沿05具名未改證據。合格五日曆、法人schema及歷史映射警告仍有原文；畫面缺值保持未提供與覆蓋數0，不以未知卡當完整金融功能。既存06交付封存與私人資料不改，技術測試不代替Native／真人接受。

<a id="f07既存筆記新程序讀回qa160"></a>
## F07既存筆記新程序讀回（QA160，限定Source）

此項補足QA155已保存第一篇卻尚未讀回的持久化證據，不重跑原完整240秒旅程。Source為`2ad49f3cac9bc0daaae0fdb90918d0a20fc1fb22`，執行HEAD `371444b5f6d8af16935ee1b0464bf32af3358a2c`；只複製155自有watchlist／portfolio到新owner狀態，原155資料與既存行情唯讀。沒有另存筆記、修訂或以新文字替換原文。

新程序正常Main33380在1280×760，沿原觀察清單2506可視列雙擊、原價格個股及「我的判斷」，先讀來源／清單，再明選原筆記讀原文。每個動作仍fresh來源核驗；原收藏56.907秒、筆記來源與清單57.125秒、原文與原來源核驗57.328秒，176.328秒內合作關閉，保留單程序240秒與每步15／120／180秒。原文、唯一revision、無parent、原canonical bookmark及`recorded_at=2026-10-19T19:39:00.677159+00:00`一致，原文欄唯讀；Root檢視截圖。Journal SHA `4ebd6f85fa5473efadc2141ee9d2136f5b0735a3d5bdf41d4d8d5bda4dfe8617`與清單SHA `9f1e0117bd54812a840c6305b81886ed03a5f420cc73fdbfe9ef018c7e099e07`前後不變，網路／保護根／Qt錯誤0，candidate sentinel不存在。

helper SHA `ee1c291d311bec4cb95339c33562583648faed73d2b6a8e78a8b742507f038bd`，spec `499ba0d5c4f0042fe2aaa33e62694ad58cf5824e81303c008838ea77b355a47d`，結果 `8cefdc6047c256853f461253fa4faae0e6860f17891284c0b87b1ebb84b11eae`。閉鎖收據 `0fef57e50eb6cb9c2fcfb4bcf5c64dbb328cee906c1911e47592c76675346c2f`：三PID空、process／Job handles閉、mutex釋放、無forced cleanup；8GiB committed／12程序／啟動RAM至少8GiB保持。編譯與新程序只讀檢查通過，未改產品Source，未重跑未受影響共同防線。

原104／155完整FAIL保留；保存→修訂→原來源返回→保存中關閉→fresh完整旅程仍待，不能以本項只讀成功當完整F07／M3、金融用途、Native或真人接受。固定06未含F07 Source，封存包與私人資料不改。QA157及獨立靜態複核尚未證明足以解除完整240秒阻礙的局部修法；固定plan轉換或固定parameters重建的低收益候選暫不實作，不略過來源／語義／精度／PIT守衛或跨動作快取。

<a id="f07語義證明範圍qa163164"></a>
## F07語義證明範圍（QA162原型／QA163候選）

解除阻礙：原104／155完整正常F07筆記旅程在原240秒內未完。QA162先以全1951份原件、122批次做獨立完整decoder平行原型；baseline public reader55.648秒、其中decoder合計40.133秒，含fresh I/O／啟動／IPC／父核對的原型25.873秒。保守代入整個reader為41.389秒，這是推估而非產品量測，不能以55.648／25.873聲稱整個reader加速；不足解除完整旅程，因此未加pool至產品。

原型全部snapshot canonical身份、原件及manifest SHA前後一致；四worker21160／34168／44132／48244均在Job，觀察峰值9／12。原180秒phase、400總與8GiB／12程序不變，network／protected0，來源及watchlist保持。helper1c7ae1b2e79b7796851226db2c2d22fb2712e04820cb58328863a5ac58c73085，結果50bc706fb5af4d3a39936a1717a526c7202c849738bd200677cd443425259675；閉鎖3c578da7ce8272ed1725122fd0e74aea46873e1f66babf6b1b49474b72084cc7。此原型不發proof、不改產品、不接受完整240／EXE。

新QA163契約改用既有不可偽造reader-issued proof，同服務最多128份、ContextVar限定實際worker；每動作仍fresh全來源鏈、manifest及全部artifact bytes／size／SHA／layout，從本次raw重建DTO並核binding。保存calculation binding沿原strict validator，不新增live kernel等值要求；新程序冷讀、缺proof走原strict，P01 capability不擴大。parent僅重用同次plan純投影，不保留跨動作metadata。v1獨立review指出誤述live kernel，Root依原validator修正v2，SHA3a4f537d56c9c5f6f0a2ecfefe6075a524b202f341a297a04aa9e876c10e1f69；另一既有Luna限定三Source檔靜態複核無blocking，不等於運行時驗收。原斷言／期限／Journal CAS／不可取消保存保持；固定06與原FAIL不改。

QA163 context只是導航：repository／parent／service為headings_only，widget為budget_omitted；Root另讀受改symbol與diff，未宣稱全庫EOF。閉鎖625b1dc5948716d5e18b096b2db09fbbca4f9e96648200f80b37bbcf9e4a83ec。Source與新測例尚待compile／定向／共同防線，完整正常Main及新程序未執行，不宣稱已解除240阻礙。

QA163編譯通過；受影響回歸20FAIL／22PASS（227.03秒）：19案因新harness的TEMP與pytest外部basetemp不同，原fixture未明選ResearchCaptureWriteScope，被writer的isolated_output守衛拒絕；另1案沿既有P01 typed重建卻仍攔from_json，完整原頁及65原件檔數斷言尚未走完。後續notes／共同防線未執行。Root只改fixture明確Scope／派生子目錄及既有解碼mock接點，原codes、頁面、65檔／5批、未選sibling篡改及取消斷言保持，產品守衛不改。163a首次Scope改法漏用派生research_snapshots，19FAIL9.06秒；失敗保留。163／163a閉鎖d09ae2afab537cd933dd8c2fa04e5b85593aebdef69b6f6ba138783b763b106e／936331c71d04ffb6dd134b5f00b0df362f3b712acf19352021f6f75c81bc183b，均自然排空、無forced。163b只重驗20失敗及未跑項，未重跑已通過且未變的22案。

163b來源／Scope18PASS／1symlink skip（Windows建立連結權限）11.22秒；全257 P01監測1FAIL122.28秒，原頁面順序已相同，但既有ThreadPool的完成次序不保證等於股票順序。Root正規化監測codes／references次序後，保留原頁面順序、完整57解碼／65原件／5批及未選sibling篡改斷言，不序列化產品或改reader。閉鎖dd4ac560d72949015a95607df4d73e1a5b466b119e0a98f26357c5d644590ff3；163c只驗這一案與尚未執行項，18PASS及原22PASS不重跑。

163c該P01案PASS111.60秒，57解碼／65原件／5批與原頁及sibling篡改拒絕保持。Notes／UI49PASS／1FAIL141.86秒，舊legacy fake service的第二次保存刷新達原5秒，diagnostic為busy=list／native未結束；不降低期限。Root將共用測試等待的QTest.qWait改成processEvents加time.sleep(0.005)，讓背景Python核對合作執行，原5秒與全部斷言保留；不是產品修正或已證GIL歸因。閉鎖f7fdcc51a9da3219a75a547c347a763db113f423cab2a47f5334bc6ea4780ee8。163d只重驗受此helper影響UI與未跑共同防線，來源／服務／P01不重跑。

163d相關UI23PASS48.18秒、Workbench85PASS3.53秒、validator25／0／4、mypy1081無錯誤；UI既有ignore不證UI強型別。此前163c服務與其他定向通過49案、163原22案及163b來源18案各按原範圍保留，不以案例相加當完整Gate；Windows symlink仍skip。閉鎖927c6c43c7440a71613a080083662ac67d194ef5d94399381a28bd891035fa82。Validator沿用舊具名helper時寫到其固定qa154報告路徑，163d獨立stdout／stderr與收據仍完整，現報告另create-only保存m3_f07_proof_scope_validator_qa163d；不能聲稱原154報告bytes保持，後續helper須重綁報告目錄。

QA164 helper只將原155的owner case名替換，其餘原240每phase、15／120／180步界線與5秒寫入關閉閘及斷言保持。helper1cc94b550b7098c5d4e995704b6aab7943b12bdb41e52be519be5109340ba305；spec b10cb97281298adb3ee4a59769497cf382595bc2b810c7c3aade4bf13bfbae54。現在正常Main／新程序正在執行，尚未接受完整旅程。

QA164原240秒仍FAIL，停在筆記開啟原價格版本：原收藏86.093秒、筆記初驗66.671秒，保存15.547／明讀16.016／直接修訂15.985／子修訂讀回15.735秒完成；兩篇原文／直接parent已保存，Journal SHA d4b6ad5e53cdd1320a526d8402deeb484101c747feab298c4bfd1475fb4044c7。保存中關閉及fresh未執行；沒有phase最終result，不能聲稱network／protected／Qt錯誤為0。閉鎖d4810738bd71aade9de7e5a4a69d17327b9a63a11580dc200627f10fa85ab9d0，三PID空／handles閉／mutex放、wrapper無forced cleanup；parent由原subprocess240逾時終止仍為FAIL。固定06不變，原104／155／164 FAIL保留。

QA165限定修補只解兩次cold：Root凍結入口factory契約6b1070604b12b41746cd535d4efc743f766a5903a5602a874941a4ada7dba3eb，由Main將同一NoteService.source_read_scope交給原controls／price full-reader worker；未命中／新程序仍cold、每動作全raw仍fresh，不引入proof注入API或擴P01。既有Luna單寫兩UI葉片／測例，另一Luna獨立靜態複核，Root單寫Main／shared／整合／QA／文件；兩路完成且無pending writes，沒有新agent。契約v2僅修正實際class名稱及記錄Root加強排程前換factory測例，SHA32db2ef72d3d821f3e00e3837e9100d097133ad276c561660b7ea2e4c64b6fce，獨立review無blocking。

QA165編譯與40項入口scope／原controls／price view／notes導航定向通過（46.54秒），Workbench85、validator25/0/4及八套件mypy1081通過；既有UI ignore不證UI強型別。validator helper重綁自有m3_f07_entry_validator_qa165，未沿舊報告路徑。Spec d247775881012645cc2f845466b78abe308cefce043e3a0dcc05ee6e3757c886；閉鎖49793a541dc85db55c645c1b28d20725efdb655ab9e450664aedaad59f20fbc9，三PID空／handles閉／mutex釋放，無forced cleanup。原已過未改的repository／P01／service整組不反覆重跑。

QA165 context工具9,000字元預算的摘錄8,041字元；Main／controls被列headings_only，price view被列budget_omitted。Root另核實際修改symbols／完整diff與既有reader／排程／取消接線，獨立worker亦複核這批接線；這不是三份大檔全文EOF宣告，也不以工具摘錄取代原QA或正文契約。

QA166使用新owner state／spec／result，沿原155全旅程：helper僅改case並新增兩條真正Main同service factory接線斷言；原每phase240秒、每步15/120/180秒、保存關閉5秒閘與全部金融／來源／原文／直接parent／關閉／fresh斷言保持。helper4fe4cc6176320bfabb4aece64e26d0de95984d71b2e98a95e4b4dccebe10d5be，spec697b1fa0dbfecf8d0757351b2114761b1abdda6033da3c1d13552f3684660b2f。結果待後續具名收據，不把定向PASS當完整旅程，固定06保持。

QA166實際仍FAIL，這次在原返回15秒界線，未達整段240秒：原收藏59.531秒／筆記初驗16.078秒，保存16.047／原文讀16.375／直接修訂15.984／修訂讀15.968秒；178.171秒已開回原價格版本並通過原selection／stock等值斷言，按返回後仍在full來源重開。失敗diagnostic的network／protected／errors皆空、candidate sentinel未建；這只代表該觀察點，並無phase成功result，fresh及保存中關閉未執行。失敗後合作關閉0.453秒；閉鎖55ec5397a90ae58bace8d783bbf1a3e1530148382a450bb1aeefea695ffcc551，三PID空／handles閉／mutex放，無forced cleanup。Root已看原文唯讀／直接修訂畫面。下一步只核對原返回與既有issued session的守衛，不延15／240秒或把暖讀局部結果升格。

QA167只解除同View／同query返回重建全母體的阻礙。Root契約210d6446d18a680629c44388fb322452b6290b2bf02c89d540da52e258e3459e經既有Luna獨立裁決，另一Luna單寫原price view與新測例，未執行Python；Root整合／QA／文件。`restore_origin`在閒置live query相符時，由原issued result建立request並fresh `read_page`，核當頁所涉批manifest／全部該批raw與typed選取；新page完整selection等值才套用。這沿既有P01翻頁能力，不是每次重新核1951全parent／receipt graph；不直接用舊DTO、不擴P01／Scope，取消或完整性錯誤不得吞錯fallback。無匹配state／其他query仍沿原`restore_selection`完整重開；筆記保存／讀取／開原版仍fullfresh。QA166本身未記price visible/busy，因此返回busy是接線推論；新helper只補這三項診斷，不改原斷言與時限。

QA167 spec824269ceb8e0a4282b9d0bb92a201b557ba882abe1ab953d8593d340832296a1；168 helper cb4824c236388348b5e4188528a73c63c5a0ca096fec9afb76bbbac31234871a、spec cc84caae3a6ced019d0cc17979dca2eeccbb157c6aa57f2bc0e5ef4ebd58359a另存自有環境與結果。接受狀態依後續實際收據，固定06不改。

QA167實際通過：本批全部changed Python編譯、32項受改返回／原price view／entry Scope定向16.49秒、Workbench85、validator25/0/4及mypy1081。Root已核完整diff／六項新測例，另一既有Luna對返回葉片與新測例獨立靜態複核無blocking，沒有新代理或pending writes。工具context摘錄6,490字元，price view仍列headings_only；實際symbols／diff另核，不當全文EOF。UI ignore不證UI強型別。validator使用自有m3_f07_live_return_validator_qa167；閉鎖19c61b7869e54b1ed2cd6164e8147dd314ed766c4a9791b16fe679a903a12ad6，三PID空／handles閉／mutex放、無forced cleanup。受改UI SHA917f7e31bf76ae17ac98cbaab4abc62699c0fa3d81eeef0892d21de33ad9bba1；新測例7ca13640a6d3721ae0474a309fbcc9b7b4981c425af8371f0773357a92ee5811。QA168原完整Main／fresh另驗，沒有將定向結果當完整旅程。

QA168完整Source旅程通過，Main14416→42708：原收藏、我的判斷、首篇保存／明讀、直接修訂／原文、開原版本及原selection／stock、返回原query／page、再次個股、第三篇保存期間關閉等待與fresh三篇原文／直接parent／實際保存時間均沿原斷言完成。父程序197.032秒、新程序130.969秒，原每phase240秒不變；返回1.219／1.235秒，原15秒不變，保存關閉5秒閘不變，實際合作關閉14.766秒在原180秒內。新程序重新冷驗，未借跨程序快取。兩側Journal SHA db63439068b80811191b9d6df5b75ac6ca9d6e28f730bdb5bffc64ff237c91dd、watchlist9f1e0117bd54812a840c6305b81886ed03a5f420cc73fdbfe9ef018c7e099e07一致，network／protected／errors空、candidate sentinel未建。Root已檢視兩側原文／修訂畫面；此為Qt模組內操作，非Native／真人。

168 result abfdeb5d07bf64b9b3a960fd80849403f152e436e98c32b1a408ad42f8f9138e；閉鎖c3513abc4cdf1d8ef68deec63cd1dd155c3d43883983c46781fd881bb0b55b6f，三PID空／process與Job handles閉／mutex釋放／無forced cleanup。8GiB／12程序／啟動前RAM至少8GiB保持。只接受這次Source F07技術旅程，原104／155／164／166 FAIL不刪；固定06保持，07建置與同版EXE／首次設定／受改Main／fresh／啟動器另驗。來源用途、TPEx、正式日曆、歷史PIT、真N、完整金融／自然成熟、Native／真人及原完整Gate分項保留。

QA169文控FAIL只因owner task漏列四份必要coverage：FIRST_INSTALL_PROMPT、MACHINE_BOOTSTRAP_RUNBOOK、指南README及SCHEDULE_OPERATIONS_AND_MIGRATION。12features／36link sources已核，但不列通過；閉鎖6d958510361ebb222fbb55c651d858b5009e3a123f95571fb5ae508ffd6a179d自然排空。Root補核各自安裝／同根重開／導航／Direct停用段，記錄本次未改這些契約的not_required理由；不藉文控失敗重跑已過產品旅程，169a只重驗文控。

QA169a文控12features／36link sources通過，spec4006d3e6c614d5d6861be720c0918211d45b3f6e9f8203a6a81016d38dd02682；閉鎖202e13e4030ab64ed890ccfa598f88b8972ee937d4aa9990d6cf0c6c7223fd74，三PID空／handles閉／mutex放、無forced cleanup。此結果只接受文件結構與coverage紀錄，不替代正文EOF、產品／正式安裝／自然運行接受。

<a id="固定07原價格筆記交付qa170174"></a>
## 固定07原價格筆記交付（QA170起）

解除交付阻礙：Source168完整旅程通過後，將原價格版本筆記收入獨立固定EXE候選，沒有增加第六條主要流程。Source checkpoint `15d30353c583594f973306aa272d581b3629feec`，24自有Source／tests／文件已提交，未push。QA170沿原1000秒build子程序，EXE `7a68de474737fcb1d03cb719284d11dab9541c9c010983c157ab93578ecb2420`、Source ZIP `00c3212f20ba2d21527c086d8670ac50a747438fcc8ce364e6b44c4b868be4a3`，build receipt `6cade6d2a4e5cef35fdc2160a32c659e1718cc4ec2e9d2ab21edda6d6716990b`。只列built_not_validated，不能以建置當產品接受；閉鎖746d0005b8c5bb2066fe5a0ac351958e30e7894c936478969ed578c69898dfe9自然完全排空。

既有Luna獨立靜態複核未跑的173／174 helper，指出audit未把SQLite connect列為MOVED寫入風險，也未攔列出的filesystem變更事件；另需直接綁實測MOVED EXE與交付TRIAL EXE的SHA。沒有實際產品寫入證據。原helper保留未執行，Root另存173a／174a，不改產品或重建EXE。173a把MOVED市場庫逐hash複至自有CASE，config／env DATA_ROOT及calendar cache均在CASE；禁止MOVED SQLite與列明的檔案變更，正規化URI／長路徑，前後核MOVED市場原件不變。兩phase另核實際EXE與manifest，174a交叉核setup／assembly／MOVED／TRIAL／child EXE。獨立重複核無blocking，未證所有OS descriptor／dir_fd變體；不稱OS級全面攔截。先前Source168的零attempt只限其已觀測hook與路徑，不據此聲稱未攔事件均不存在；其F07三篇原文／完整來源及Journal回訪結果另行保留。

QA171編譯新a版helpers並create-only組`output/trial/Baldr-Theme-Research-07`通過。原141c與139封存原件、自有task具名名冊及127明選推薦沿既有收據，不帶私人Journal或Task status。Manifest `59be15afc508e6218afc8d25a1fc18e9ec854dbfcb748eb7f9c2579dd8f926ea`、assembled `2246cbf124ccabba51daf6b761bc3e131282d5bc5bce96254912e814a873e0da`；閉鎖da4d81bdcc78b39331b4a3bbd7e3b5ae4b0aeb2e5509df7888cd443212579a2c自然完全排空。原06／139／141c與私人原件不改，07首次設定、正常EXE／fresh與啟動器仍依後續收據，不提前列PASS。

QA172整包含空白新位置首次設定通過：實際496.406秒／原600秒，`prepared_and_readers_verified`、凍結config解析及原月營收五列讀回通過，舊根／正式根IO與network嘗試為0。新根`.t/theme07_setup_qa172/Baldr Theme Research 07`，交付模板全檔SHA保持、沒有匯入私人state。Result a3a3ccef8ad194b8cfa04296bbcb7a6709e6cad35343ba48da2b0becce5fbcb5；閉鎖be44b2a0d5b07284562caf7339dc1897e5336d3d99a6ccca82a181a944e7e169自然完全排空。這只接受本機新位置設定，後續正常EXE／fresh、其他DPI／跨機／真人分開。

173a實際執行前Root另將副本config的calendar cache也指自有CASE，與env一致；只補驗證隔離，不改產品。新spec90e53e6d2f257c66c6f4870951f0c2eceb48b00cc5ca1b1cc4699bbc3e4f51ea會先重編譯該helper及174a，再驗原Main／新程序240秒旅程；結果依後續實際收據，不把編譯或設定通過當頁面接受。

QA173a實際同版EXE正常Main51796→36696通過：三篇原文／直接修訂／原版本重開／原query頁返回／保存中關閉與新程序讀回，兩phase197.906／130.906秒在原240內；返回1.265／1.250秒在原15內，5秒寫關觀察閘保持。所有受驗app／UI模組位於MOVED的`app/_internal`，build為15d30353且dirty=false，兩程序實際EXE SHA均等於交付7a68de47...。Journal5051f9f92c0d4f2ede9d5cf60b731e1fe7638e49540659d2a8d25aff99be3371與watchlist兩側一致；MOVED市場原件前後inventory相同，network／protected／errors空、candidate sentinel未建。Root檢視兩側畫面，這是模組內Qt事件，不當Native／真人。Result05ef46cc1e45fc28062c6159c80c4e91460154f4a0da48072fa2fa03f9346df9；閉鎖bbfffb6f7a0ac4cf8926a90746903f85589543c24625dd555b8412178d27fc03自然完全排空。

QA174a實際啟動器正反SHA退出0／2、原MOVED config／setup／watchlist不變；交付與受測EXE／manifest及setup／assembly／parent／fresh完整比對。指南及已知問題只補本次具名驗證範圍，task具名名冊收據e7a8c9f4e777f575dad59e057c61191e004c578098a6e076b39135aee3f8312d隨包。完整新模板清冊4a6c0f1298867b14f0989a69dab48c58f561b8d7096dc4c133d5c2e26d16d673，交付eaf1459e5fede75ec36848f45c106bfd19fea9b6a1792d6d963dcf9b6f1d50f5；無私人state／每日Task status，06原收據SHA保持。閉鎖7c7d80cd03fe85e0ee0257cbcf476dc23979d5890db9f3a062866d7dc3222099自然完全排空。各組8GiB／12程序／RAM至少8GiB／原期限不變；不重跑未改旅程，不以局部或案例加總接受完整金融、PIT、真N、自然成熟、跨機、Native／真人或原完整Gate。

QA175最後交付文件結構檢查通過：12 features／36 link sources、errors空；spec `5f3a20bb5cc0b8a4bad905b069d63bd96e5dd19cff6c3aa7b87d422ab0642bd0`，閉鎖 `79e5c7024d8f7bd60161ed39e7a12ed88b8d2720a329aab8e9588929d1a5f493`，三PID陣列空／process及Job handles閉／mutex釋放、無forced cleanup。只核文件結構與coverage，正文由Root按實際差異及原收據核對，不替代真人、金融或完整產品接受。

<a id="題材雙向排行qa176177"></a>
## 題材雙向排行（QA176–178，Source限定接受）

解除M2交付阻礙：原目標要求強弱／漲跌排行，但現行只有高端前五；不需等外部法人或正式日曆才可完成已保存同來源的低端觀察。Root將此項從過廣的資料依賴拆回READY，沒有新增第六條V1旅程。固定07保持。

Root凍結keyword-only ascending=False相容API，兩階段stable原值排序不以-Decimal觸發呼叫端context捨入；從全合格母體取高／低五，coverage／None／有限值／零負／名稱同值穩序不變。既有Luna單寫原題材view與直接測試，另一Luna獨立複核Root的presenter及測試未見blocking；後者僅靜態，不冒充UI或runtime接受。累計10/10不新建；Python／QA僅Root串行。此時Source候選尚未compile／pytest／mypy或正常Main驗證，不提前列PASS；契約9edff97c093bac7120bad076b63a2717ca634b540b8aaa80ee27456abc19c1b3，後續收據另列。

Root整合移除葉片額外的closeEvent覆寫，沿原Main.shutdown失效／清除，不改頁面生命週期；對應測試明確走原shutdown。176初始spec在執行前因EOF空白diff檢查另存176a，原176未執行、不覆寫。176a route分類ui/medium、context level3有預算截斷（不是全文EOF），Root另核實際symbols與完整本次diff；compile成功。定向36PASS／2FAIL，5.81秒：兩FAIL為未改產品的舊theme context guard SimpleNamespace未提供現行_saved_snapshot_only屬性，不是守衛拒絕失效。Root只補False明示一般報告fixture，原拒絕換股、來源身份與警告斷言全部保留；不改產品fallback。

176a spec7c6ef3179be0ab73806ed092e74720551a5640bffa669c12f13c8369f0f49abd；原FAIL閉鎖5347f325ef8af4ecf39c51cf6d6ad1140f86841f90d35b4f8f20fce6671f7793自然完全排空。176b另存specde2f28d32e8048df4cc3fe86697cb25bc674c9ea8b5862a7749cdfbbebc5af69，只compile／重驗2項fixture及前輪fail-fast未跑的共同防線；不重跑已過未改36項。此時176b仍執行中，正常Main177尚未跑，不能提前列PASS。

176b兩項舊fixture守衛2PASS（1.46秒），Workbench85PASS（3.14秒），本次獨立validator報告25／0／4，八套件mypy1081無error（兩項既有annotation-unchecked提示；ui_qt既有ignore不證強型別）。閉鎖5bb6e09fb8feb52d33e8782ac1a2980555765da42048b3ff0b74f8be6bf99ea9自然完全排空，原176a FAIL保留。177已按新spec4c187c9cdea6c0af00a939a7717ab9a7540899033849b94f54e2a6884b018f32另起正常Source／fresh，沿原120秒每程序、15秒動作；不是把案例加總當完整Gate。

QA177正常Source Main43680→17196已通過：原manifest75f97365...的90題材中，漲跌54／成交額55欄位覆蓋完整，實際高／低端五筆均按原值及鏈／題材一致，原低端成交額列可定位原成員；股票反查2330、原來源個股與返回後保留低到高方向，再核讀取中關閉及新程序一致。法人與量能合格數0，兩方向均空，未補造。Watchlist a2a2079b1d355b01d70dcbaebf858529740a2050fdd9d6100267eba357a83859相同、Journal原本空且未寫；MOVED市場原件inventory保持，network／denied／errors空、candidate sentinel未建。Result f411e4c73316879ab104723a864d7c1bedac7b0170d20405f2b41642069628a6；閉鎖9052de9bb7e957a482b2a0910e78dc29b9dbd64016aa92a78c13965c5163f5e4自然完全排空。

Root已看兩張1280圖；截圖是在排行點選後自動定位的成員／指標區，不能用它主張新排序控制項同屏完整可見。Source操作有各控制項可見／命中位置核對；固定EXE後續須在點選前另截新排行控制項與表格。這是限定Source功能往返，不替代EXE、Native／真人、金融來源用途、PIT、真N或原完整Gate；07不含新排序。

QA178文控12features／36link sources通過、errors空；spec5ba6a482354df196733e5e297fa210a167473e8adae96b13014e7b78e64290b7，閉鎖c1daf30f68ac8dae617800e83adcb19cc71342dc16a278b5152017522fc93738自然完全排空。只核文件結構，Root依本輪diff與實際收據核對正文；來源／金融與固定EXE接受各自分開。

<a id="固定08題材雙向排行交付qa179183"></a>
## 固定08題材雙向排行交付（QA179–183）

解除M2交付阻礙：將176／177已驗的雙向全母體排行與原值精度修正收入固定候選；五條主要流程不擴成第六條。Source `d69781fa89cf75e4ea80eabdae188b175d49d366`（12自有Source／tests／docs已提交、未push）。179沿原1000秒build子程序完成，EXE `3e9bdc32ff060274f892041aa77d978021f5dc2ced06514b4cb8d35b4f7255d2`，ZIP `b3bcc396866f0ae3e7464caa97831b688ac2ddfce055a471327f4922c6011208`；建置當時只列built_not_validated，不能代替產品接受。Closure8b67ba76388403d85b3d67611cf7a4840bbf049818a83712666689a1dcefdc5e自然完全閉鎖。

180四個helper compile及create-only組08通過，原141c／139封存、task具名名冊與127明選保存推薦沿原收據。Manifest `1b3fd48f0b03d9948c3430ccf67eb895a7c70b683c6e977d5348c81e9f3ac41c`，assembled ee82c8ea901d6ec2d37bf0b8295585aaa04cb9abd8b9e9a153c1dc8f04f5cd39；closure cbc49eb4d487c31630238f3eed7831cf88be54468eea2a91f5abcca4f50e4ad9。181先核.t非reparse、move絕對路徑在workspace及新RUN內，再驗整包新位置，實際511.282秒／原600；原模板全檔保持、config／readers／原月營收核對，未匯入私人state。Result1a2fcedb77dcf939067f23d92d02f3a7a97c32b87d3bdfd61d87af2117db2d98；closure d1a071bcc2bc631617431a395cd0e6a901752b3bb8ade2a3e396a329abbde48c自然完全閉鎖。

182／183由既有Luna獨立靜態複核無blocking；Root保留整合及QA。182實際EXE19332→53376通過四類高低排行、完整合格母體／原列身份、原成員／2330個股返回、保持排序方向、讀取中關閉與新程序一致；原120秒每程序／15秒動作及30秒關閉期限保持。真來源54個漲跌、55個成交額題材覆蓋完整，法人／量能0不補值。市場與題材由MOVED逐hash複CASE，讀CASE原bytes，MOVED兩原件inventory／EXE／manifest前後保持。模組origins全在包內，build為d69781fa且dirty=false、實際運行EXE SHA等於交付；network／denied／errors空、candidate sentinel未建，Journal未寫。Root已看點列前兩張1280×760圖，排序類型／方向與五列表格可同屏辨讀。Result66ced97ae78778e50e8f260e4eaa191e8f9a38100a030977d9fba509869567f2；closure fb9d625d6d47677f9b1faf9362844b828a71ef053c8dc730bc46d5a4d55221c0自然完全閉鎖。此helper核原值排序／列身份並記observations，未逐格assert所有值字串；既有值呈現邏輯不改，相關單元斷言保持。未證所有OS descriptor／dir_fd audit覆蓋，不稱OS全面攔截；內部Qt事件不當Native或真人。

183比對177 Source／182兩程序／setup／assembly／MOVED／TRIAL的SHA鏈，launcher正反0／2與原MOVED config／setup／watchlist保持，並封存08。具名名冊收據 e7a8c9f4e777f575dad59e057c61191e004c578098a6e076b39135aee3f8312d隨包；完整模板清冊 `3734a69bd6c6ed810a638a697aa355d01cfc51ab9d0f501454afaa1029ed6d47`，交付 `218189c128a48d44ec6b1df580491da67667d5773fdce60010b0f55ae0829c63`。Resultcd3f2a1e0f912f656e95084822f16fc93d0cb6ae0ba7a156dfb38ad91b63c036；closure `74fcb8d96a47d836c53e420fdaf2c4726cbe3f4fa83c4f90ad1dbea32fb441b9`自然完全閉鎖。07／06／舊包／私人原件保持；08無私人state或每日Task status。未改F07筆記／首屏／八期限／一般報告／Registry沿07及其引用原證據，不重跑或以案例加總升格。來源用途、正式日曆／法人、歷史PIT、真N、完整金融、自然成熟、跨機、Native／真人及原完整Gate各自保留。

184交付文件結構檢查12features／36link sources通過、errors空；spec83cc0e455f77c66c25d95a004c59fbfc21453bf64894d11c7c78d3b431b2c554，closure9c9350314e7d9b43bd5d2d4d8da153c089eccd3f4a67c4925a46527a67ba3057自然完全閉鎖。Root另依本輪差異及原收據核正文；結構檢查不代替真人或金融接受。

## 法人多股讀者與新單日來源（QA185–188）

**解除的原M1接線阻礙**：原public法人reader每股都完整重驗全批，沒有同版多股port。Root保留原驗證內核、舊單股DTO與TWSE wrapper，新增1–5000唯一代號tuple的多股投影；Luna只寫TPEx observation adapter及測試，另一既有Luna對API與adapter分別唯讀複核無blocking。累計10/10無新代理、pending_writes=false。契約`m1_institutional_exact_batch_contract_qa185.md` SHA `470cab1e9f7fd04f82b939113f58162b6c3452c0add52097e1d19bbf971ca239`。不改正式庫、Task、maintainer、08或私人原件，不做跨市場合計、價格反推金額或歷史PIT。

`TPExThemeFlowReader`只消費同一TPEx固定每日版本及原九aggregate股數diagnostics用途pin，取caller由同版映射確認的TPEx成員交集；原net整數相加投影至既有ThemeFlowObservation。未命中、異日與非本次TPEx成員各列原因，不補零、借日或fallback其他市場。時間取批次可用小時與用途接受時間較晚者，source_id保留股票／raw／雙每日pin／用途SHA。舊TWSE來源仍須自己的精確用途契約，不能借TPEx接受；正常題材snapshot組裝及固定08含新batch API均未完成。

185路由／Context／compile通過；Context4500字元budget略過資料儲存正文及代表性AST，另有headings-only，不能當全文EOF；Root沿具名正文／差異與兩次獨立review核對。定向原單股／多股／TPEx／用途與受影響Qt回歸 **122 PASS／2 FAIL**（7.13秒）。兩FAIL是新測試fixture同時傳入stock_codes／source_use的重複kwargs，未進產品斷言；Root改為先建合法DTO再replace反例，原拒絕斷言保持。185b僅該兩項 **2 PASS**（0.43秒），其後mypy報同一函式重用row變數的Optional指派錯；Root改獨立selected_row名稱，無行為變更。185c compile及八套件mypy **1082檔PASS**；原兩annotation-unchecked notes與UI既有ignore不證UI強型別。原FAIL收據保留，未重跑122未改PASS，亦不把拆次數量當完整Gate。

185／185b／185c自然閉鎖SHA依序 `0acbaa089554891a3d27bb6254bff1e3eff9cb63cb8876a001e360712a3d099c`／`66daf3a96f71978819b3484303842a811bf7a9f90ef64a928d823c1823887dea`／`ab687dfebbb00db55226c117c8c4f4b908c94db9a7f4a49d0ff94a19b2369480`。規格與原輸出各保存在本owner task，不覆寫舊spec。

186真舊898列原件的Source public parent3476→fresh4140通過：6488／8069／00679B原九項股數逐欄等於舊raw-derived oracle，ZZZZ未命中不補零；每次多股只完整_capture一次。adapter的6488／8069三net整數和、來源與時間相同，10/16查詢拒借10/15，12份原件SHA／大小／mtime／ctime保持，無HTTP／SQLite／producer／seal或接受重寫。Result `e62a5074428d80eca54fdc18b4a668afe7572a2b42c5a4a39dcaf53f530df783`；closure `c54483bd0e637f5d32ff7cc3230f2f255e5878b3de3764d75b3ac9b3baed33ee`。這是typed source-use分支與真原件的限定讀回，不是正常題材UI。

185a為解開「舊10/15版本早於現映射」的日期依賴，沿既有官方TPEx OpenAPI只GET一次，明選 **2026-10-19**，原20秒／8MiB、無redirect／retry；不重置耗盡的月營收／TWSE GET或MOPS scope。完整888列原件經原parser／九股數／品質與seal核對，原報表筆數不是股票真N。新manifest `e9232a2b4cf42e2f1b62836b0de2067865e515ec4715c525a97ef5b9383c09f3`／receipt `377f5aa58cdf2bd91ed5f6ab308c1429462830eae33d893e619a245b0cb2f27a`，台北 **10/20 07:00** 才可用，真時鐘此前已驗拒讀。HTTP原時鐘與完整body另存，daily時鐘使用這次真重播保存完成時間，不偽造官方發布小時；basis仍successful_batch_completion_fallback。manifest原source_use=false／candidate=true／historical=false不改，後續read才可明選原diagnostics用途pin。185a closure `523ce09ea5943416c91e888eb1caabe7cd650eb40021a16badb2dabeb806b65d`自然閉鎖。

新用途副本逐bytes／SHA複用原四官方文件與canonical source_use，不另寫接受時間或擴原scope；08包與舊來源保持。新raw為840,348 bytes／SHA `64c6aff99d531411e509d62fb09b40810cc922e88010f338489fd69a91912980`，185a result `abdf63d15af30ae26843be18f9318eb152e8538d417e296cc9637824202c5946`。

187到真可用小時後，原固定08 EXE Main **8832→15164**明選6488／8069／00679B：10/19九股數逐格等於官方原array，報表888／TPEx／原用途ID／SHA／接受時間／顯名／批次07:00與原raw SHA一致；切觀察清單返回及關閉重開一致，22份來源檔bytes／SHA／mtime／ctime保持。MOVED市場／題材／EXE／manifest前後保持，實際EXE SHA仍3e9bdc32...、build仍d69781fa／dirty=false，五個產品module origin全在包內，network／denied／errors空、candidate未建、Journal未寫。Result `1e9df44a41c4fc2c637f21253943f1c0e12b6b67627d8093b45cebf07b6b8bbd`；closure `968ab376b43b2b072a6b6260f73c43b5521cd864be08e84df14dc3682d1ccb61`自然閉鎖。原120秒每程序／15動作／30關閉保持；內部Qt事件不當完整Native或真人。Root已看父／fresh的1280×760圖；只證首欄與原資料日／時鐘可見，原九值text assertions不證九欄同屏／最後欄可操作，長identity對表格高度的影響另定位。無OS全變體audit覆蓋主張。此為原08單股API消費新固定資料，不是新batch API已在08或正常題材卡已接線。

188真新原件與原10/16映射的Source public（未經Main）parent **17864→42608**：2537映射列／90題材，890個同版TPEx代號中763與該888列日報命中，66題材只有部分覆蓋。一次完整capture核驗，逐題材的原net整數和／買賣平家數／覆蓋數等於獨立CSV＋原JSON oracle；缺股不補零，非TPEx原值不加入。價格／成交額／五日量能與TWD法人金額全保持None，不混入10/16價庫。資料日10/19、查詢時鐘為真到點之後，映射可用時間仍原保存小時；16份來源檔前後保持，父／新程序結果一致。Result `cf661cebdd04d5cec353b7f2848356b66b8323a6fcfbf2f5f25618facd70bebe`；closure `28b7dcd6aecaa10ac8e161b69ab180ce8443d66109a8f2bf01817993b14b5ee1`自然閉鎖。這是TPEx部分診斷，不稱全市場、真N、完整題材流向／M1／M2或UI；原缺授權／歷史PIT／日曆／自然成熟及原完整Gate各自保留。

## 法人表格可操作性（QA189–191a）

**解除的試用阻礙**：QA187原九值字串通過，不等於使用者能到達最後欄。189與189b在原固定08 FAIL；189b保留原15秒穩定期限，表格bottom736超過父widget643，父自然sizeHint982，水平bar visibleRegion空。原失敗及截圖／幾何均保留，closure 3cec7a134d70c71f7db794c5daf2769a6ad3fdcf3bf05d96d7425a0ef2f1817a 自然閉鎖。189a PowerShell準備語法錯誤在Python前中止，另存b，不算產品執行。

Root凍結最小修復契約 tpex_widget_natural_height_contract_qa190.md SHA ebd49d0311e0febc5944ea5702fac1af3d33468dc9c1f00a23e62ae291a9c7ed；Luna只改原widget與一測試檔，垂直QSizePolicy.Minimum、水平Expanding及結果狀態變動updateGeometry，不固定高度、不改來源／資格／signals／原值。另一既有Luna唯讀複核無blocking，pending_writes=false，無新代理。190 compile與21定向（2.18秒）、Workbench85（2.80秒）、自有validator25／0／4及8套件mypy1082通過；既有ui_qt ignore_errors不證UI強型別。route為ui，context 4500預算僅定位、widget AST budget_omitted明示，不冒充正文EOF；Root／worker實際已讀改動正文。Spec 6a7d3d6f88195463a49b78726da071ffb933cdc4b2bafcae71c446fb66ff1617；closure de86c90e52af1786c29ddb10b3911bf720b8fcefe832399f6f24e6b6587f87d0 自然完全閉鎖。

191第一輪Source仍FAIL：表格bottom872已在父880內，但既有driver ensureWidgetVisible未將外層垂直區域捲到水平bar。不是把該輪稱通過；closure ba31507b84ac63b9abe272709f2b68868e48e4674f176c2c98063a7d6589c467 自然閉鎖。191a另存helper／spec／env／result，只把driver的外層捲動改成對應bar座標的原QScrollArea.ensureVisible；原15秒、bar visibleRegion／widgetAt與全部11欄viewport／每層ancestor／widgetAt／原值斷言保持，沒有再改產品或放大視窗。其成功不抹去191失敗，也未證191 driver未捲到的更深原因。

191a Source正常Main **35948→28512**，1280×760中可實際捲至水平bar及自營商最後欄（6488原淨股數247932），全部11欄逐格到達、九原股數等於新10/19原array，身份／雙SHA／用途／時鐘保持；切觀察清單返回、正常關閉／新程序一致，22來源檔bytes／SHA／mtime／ctime不變。Root看過父／fresh最後欄截圖，bar及最後欄可見；不是宣稱九欄同屏。產品module origins全為目前ROOT Source，build HEAD94ccd5ba dirty=true由spec逐bytes約束，非固定08已修。network／denied／errors空、candidate未建、Journal未寫，原MOVED市場／題材／EXE／manifest保持；原120秒每程序／15動作／30關閉守衛保持。Result 99024ea67e84abd947878105fb3e64cda57df15c40af88faeaa826cfe3ea13aa；spec c40fc7365c644d96c6ad3a8bebc1ef96ffef1e320d672126deb1067281bd7470；closure 117df2a271e1665cb46a5830310aaf29f5f742126a8166f1199fa709ba3d06a0 自然完全閉鎖。新固定09待build／setup／同版EXE／fresh／seal，不以Source PASS當交付、完整Native或真人。

所有組Root串行、Job 8GiB committed／12程序／kill-on-close／workspace mutex，啟動RAM至少8GiB，前組三PID空／process與Job handles閉／mutex釋放後才下一組；無強制清除。普通週額度已耗盡，沿使用者既定credit授權，總10000／預留1500控制，不購買或reset。TPEx只指定九股數diagnostics；正常題材同日組裝、跨市場、歷史PIT、真N、金融／自然成熟與人工接受各自保留，不因本頁修復升格。

192完成新193／194／195 helper編譯及文件結構12features／36link sources，errors空；closure 23c61bf3bc86fcb5e5a27d613c0db88852aa5f845192bba5a292977a6a2e5585 自然完全閉鎖。193 PINS缺逗號在靜態review發現、Root修正後才compile，沒有以placeholder執行build。第一次192呼叫的SHA參數多字元由preflight在Python前拒絕，原spec未改，正確SHA通過；不算產品失敗。此檢查不證正文EOF或產品Gate。

<a id="固定09法人表格交付qa193197d"></a>
## 固定09法人表格交付（QA193–197d）

解除試用阻礙：將190／191a已驗的自然高度修復收入固定09，長說明不再裁切表格底部與水平捲軸。Source 42cf6b047643790dd7a33df2543547c57141e8aa，15自有Source／tests／文件已提交、未push。193建置、194 create-only組包與195本機新位置首次設定完成；設定576.859秒在原600秒內。EXE fb32b87af5551a79199346a6da1a4a1d1a7aca3a968ee6276ecf9d127858fe1c、manifest065527e5960d9d7b8d99b2921b23136312d6b6a04669bf45c5dfe56afcd8d891。新task具名名冊及原127保存研究沿原收據，08／139／141c與私人原件保持。

196／a／b／c在首次導航的全域widgetAt命中回空而FAIL，沒有進入法人頁；Windows platform、active與exposed為true仍不證實際命中，也沒有證明根因。原FAIL／原15秒與截圖保留。使用者明確回覆桌面可用、可保持測試前景後，另存196d helper／spec／env／result，原120秒每程序、15秒動作、30秒關閉與全域命中／viewport／逐層ancestor斷言全部保持，沒有用child-only判定替代。

196d同版EXE正常Main25980→49976 PASS：6488／8069／00679B九原股數逐格等於10/19原array，雙每日pin／用途／時鐘一致；最後00679B逐格到達全部11欄、水平bar與最後欄可操作，Source6488另有191a證據。切頁返回、關閉重開與新程序一致。22來源原件及MOVED市場／題材／EXE／manifest前後保持，module origins均在包內，build42cf6b04／dirty=false，network／denied／errors空。Root看父／fresh兩張1280×760圖，表格底及自營商最後欄可見，不稱九欄同屏或完整Native／真人。Result03054755ad25c48d1c379a0d5ade6e1ea465247b59b504d734980847ad05837a；closure bd2a9b7f0f3c36a84c6a7039e4c4a35607b8f1739e4ddd6c7f5de945eb729633自然完全閉鎖。

197d交叉核Source191a／EXE196d／setup／assembly／MOVED／TRIAL來源SHA，實際啟動器正反退出0／2、MOVED config／setup／清單不變，封存09。交付b839cb41b8dcb35dce6bb3f99ff067514a657807ed7f54e84fce90299ef798c2，模板清冊5781a6d16700646a5720a59afaa806b6d64283d67988687af59042152e7cf814；result68a044da19207f9868c20767a859be095359f14996c45fc749c01b4e781c9ad4，closure0bd3fa17c6d8d67de30fc8906779250d7e10f72a0bcaa84e23a30738326268be自然完全閉鎖。09不含下一Source題材法人v2；原排行／F07／首屏／期限／報告與Registry未改旅程沿08具名證據，不重跑案例或升格完整Gate。來源絕對位置綁定、正式日曆／跨市場／歷史PIT／真N／完整金融／自然成熟／Native與真人各自保留。

<a id="題材法人接線sourceqa200"></a>
## 題材法人接線（Source QA200–202e，限定部分診斷與筆記往返）

解除M1交付阻礙：同版多股API已有真資料證據，但原題材manifest尚不能消費；沿原明選版本、題材／成員、個股返回及筆記，不另造頁面。Root凍結flow-only baldr.theme_research_snapshot.tpex_flows.v2，完整來源／用途pins與獨立保存時計，v1仍必需原價格來源且拒絕institutional欄位。缺價格、TWD金額、五日量能不補值，partial明示已覆蓋成員合計／比例，零覆蓋家數未提供；完整排行仍排除partial，真觀察零值保持。

200 compile及61定向PASS／2 symlink案例因環境條件略過（沒有列PASS），Workbench85、獨立validator25／0／4與八套件mypy1082 PASS；ui_qt既有ignore不證強型別。Spec e3c2c0789a3c2eca761006952c0a2f66adeb1a3be67351d57b31868de06bd3db、closure2eab42e834f6dc6a54e09014f6ae7ace9c1459a354fed4505759c4be6368a832自然完全閉鎖。Context4500預算對data_storage_runtime正文／部分AST略過、另有headings-only；Root另讀實際Source與diff，不當全文EOF。

QA202正常Main helper的靜態接線發現真缺陷：原200contract／synthetic fixture用中文「上櫃」，設計§3.2及真mapping卻使用canonical tpex／twse；原200PASS沒有證明真來源可讀。Root改為精確tpex，非合格市場、未知、中文、大寫與首尾空白不猜別名，跨題材同股raw市場衝突仍拒絕。真mapping bytes／SHA與manifest保持，不改官方分類。203重新compile受改port／test、50定向PASS／2原symlink略過與mypy1082 PASS；未重跑未改UI／Workbench／validator。Spec3678bf3286df052ef917a2e0f74f4dcd9af5d56a8e6444fa70574875aa84ef6f，closure35c003fac6ce2534855f3bb5da69bfaf91f1086f132db6b3bcd00785e686e351自然完全閉鎖。

新自有descriptor identity18edeabe1d604b8bd49e44d8a695cf37ee8b3910175f941a1663cc49e59b06c5，逐bytes複原10/16分類d9e50b02ec0dfe5f1eed130fac9855664ef9e649cd3aa627e9a0924d3b258491；真保存UTC10/19 23:25:58，台北10/20 08:00才可用，原日報07:00保持，不倒填。201真原件public／新程序與202正常Main尚待，不能以合成PASS宣稱已交付或完整M1；固定08／09均不含v2。所有Python由Root串行沿8GiB／12程序／kill-on-close／mutex／RAM至少8GiB，前組自然完全閉鎖才下一組。代理只重用既有Luna、累計10/10；沿人類週用量耗盡後credit授權、原10000上限／1500收尾預留，不購買／reset。

204新201／202 helper編譯與09交付／v2文件結構12features／36link sources通過，errors空；closure469ae1390779ae2de847de9c1616fd8935e39ddde7b0aa6720e217c456bc8751自然完全閉鎖。其後獨立靜態review指出raw oracle須釘原件起始SHA，Root在首次執行前補64c6aff9...固定SHA、原ctime及aware時區比較（原custody的-07與台北08:00是同一instant）；不改原custody bytes或放寬時鐘，201原spec未執行保留，201a另存重綁。這些是driver修正，非產品PASS；後續201a先重compile。

201a在真台北10/20 08:00後開始，重compile最後201／202 driver，public parent28984→fresh37436 PASS：90題材原股數／家數／分母與CSV＋888原列oracle一致，890同版上櫃代號中763命中、66部分題材，缺價格／TWD／量能保持None、歷史PIT=false、來源inventory不變。Result eec44797362c29f725d035cde320f2514d0dd45e08f57f7924af8b9f2d3e5c2b，closure ebb62ee6a2b8e540421c6d809fec92c7a9a4469acde338e4396d4e8dd234fe03自然完全閉鎖。不是Main或EXE接受。

202與202a都在開CASE／UI前，因新driver的完整MOVED state清冊含深層technical-source路徑，普通Path.rglob遇Windows長路徑FAIL。202a只將root傳to_internal_io_path，短root不會轉extended，因此未解巢狀問題；兩FAIL原樣保留，closure6b5cc6d188fda847ff95c9829b45586562767cdbec6b3bd8a24cac9e85b8ee6e／c091cd06c4f4b1ee4b1955465bc7bd8c206ea22089f8d119095a2b650451646b自然完全閉鎖。Root另存202b，用既有_tree_layout逐層canonical／reparse／regular守衛及每個leaf的to_internal_io_path，保留100000上限、全檔bytes／SHA／mtime／ctime與原120／15／30，不刪範圍或改產品。正常Main是否通過依後續實際收據。

202b清冊通過後啟動Main，但原driver excepthook只記錯誤未印trace；202c僅恢復原trace輸出，確認2330原可視斷言FAIL，沒有改產品。202d改精確點捲動仍在原15秒FAIL，截圖見2330列落在viewport下邊界；errors／network／denied空。202e沿已驗191a的16px邊距及原15秒，保留viewport／主視窗可視斷言與原Qt點擊；新失敗祖先幾何僅作診斷，沒有取消守衛、放大視窗或放寬期限。b／c／d原FAIL及閉鎖5b7db511abfa6e39a8cbe8d9157a6a5cbec12b6b2778dc6f0f9dcd54e3f55e02／14b576ffa8c6a2e741bd457684d8e14676ec7792aae4820d22a48e07b9397cc7／e7a8664a53e41600def537587ede4026762ce5601b20ebf40c0f957a38ba9e42保留，不當產品金融失敗或改寫成功。

202e正常Source Main3560→51796 PASS：原18ed版本90題材、資料日10/19／分類10/16；明選半導體／先進封裝(CoWoS)21成員中12個原TPEx觀察，三類net整數34937／235035／-150354，已覆蓋合計119618股與原raw一致。非TPEx、缺價格／成交額／五日量能與TWD金額未混入，完整母體0所以兩向法人榜精確空，partial不冒充全題材。雙擊2330沿原Main個股報告、行情日仍9/23，再返回原版本／鏈／題材／成員。題材判斷一篇保存、清空明選讀回、核原manifest及新程序重開，原文／revision ID／recorded_at／資料日／來源identity與Journal SHA1889d964ed680f6b41ee06ad0442fea5efeaafbb45cd74c915e8d00aeef4ba4f一致；capture／use／v2／MOVED完整state前後bytes／SHA／mtime／ctime保持，network／denied／errors空。Root看父／fresh首屏與成員原值圖，內部Qt事件不當Native／真人。Result b729ced01546d2d48e17c085f8289ac58fffb54d7bbbb9f53a039927b41934be，closure ab0c7d651b85730f10676067a22b03a41a26b61502976ace692f6844a77b7eb7自然完全閉鎖。這是部分上櫃目前診斷與原筆記閉環，不稱完整M1或金融Gate；固定09未含，下一固定10另驗。

既有Luna另交209固定10 helper，另一Luna唯讀複核209／210；只指出finalizer缺獨立placeholder拒絕，Root在任何交付寫入前補40位小寫hex真commit守衛。Root將202e已驗的逐層長路徑／原始trace／精確點16px也整合未執行209，原global命中與120／15／30保持。這是有限靜態review及Root driver整合，不當EXE接受；所有worker無pending writes，累計10/10未新建。206／207／208／209／210仍為未執行草稿，Source commit後只綁COMMIT assignment真SHA、保留209拒placeholder的sentinel，才重新compile／建包／同版Main／fresh／封存。

205 Source與09交付文件結構12features／36link sources、errors空PASS；spec a56d39b9bb9f064820aaf563a66d5cc2e828fbbb7ea4040e5e540e0335fd479a，closure9ec9c000dfc38c5470b2633e3a3b457884f4bcadfefe3604547b7ac4d6fcb92b自然完全閉鎖。Root按實際差異及收據核正文，不當全文EOF或完整Gate。下一步提交自有Source，再以同一Source build固定10並驗受改正常頁／新程序。

<a id="固定10法人題材交付qa206210a"></a>
## 固定10法人題材交付（QA206–210a）

解除試用阻礙：把已驗Source flow-only v2接到固定EXE的原題材頁，讓使用者明選10/19上櫃法人股數版本、查看覆蓋分母、進2330返回並保存／重開判斷。Source6f27d4aebbbf52416f747ae4e446f746670ef7f0；206 archive build、207 create-only新包與208新位置首次設定通過，設定569.641秒在原600秒內。新包帶原task具名顯示名冊，09／08／139／141c與私人原件保持。

EXE31f8408b87ab16c617bdf4ec45068edd909ab6a47c89a4db7329408672a542f7，manifest a68aea766029fd42ba3826fdff78b2663b10b6bfe137e901e888e2a4559a42b2，assembly9e44e3fb451675ba8bc5e56ab15ce65c74959fb6a8238fd4e0e4af5fc026011d，setup result23171964a70a22ac5137e1c5f053ebfe2cb62c90dc27a7aaa9c066d0d9cd16a7。206／207／208各自自然完全閉鎖，收據依序2e0133f2374d91620c5f899969d5647dcd8438e6c37c943784046e57801331fe／34eb8635abd8f993fd1836ee9cab2df0320cd58ac87d0974d4a3ae6e6d69433e／6c237e2f9d77bd71ef535b15f34061cc1d9e80093e3e053c5f73b01ccfadf13e。

209保留FAIL：Main已開，但首頁題材按鈕原全域widgetAt命中在原15秒內未通過；errors／denied／network空，尚未進題材。closure44686a9835ca78d566528be96f73a3834272dc5b02ab4b98e290d456f0782be2自然完全閉鎖。人類已允許測試視窗保持前景；209a只對本次owned HWND置topmost並保存Win32診斷，原QApplication.widgetAt、viewport、120秒每程序／15秒互動／30秒關閉斷言皆保留。首按鈕Win32 point HWND等於owned HWND，Qt命中homeThemeResearchButton；SetForegroundWindow回false，不宣稱已證唯一遮擋根因或OS Native操作。Source／EXE／金融邏輯未改，原209不覆寫。

209a同版EXE33924→40200 PASS：真18ed版本90題材、資料10/19／分類10/16，原半導體／先進封裝(CoWoS)21成員中12個觀察，原三類34937+235035−150354=119618股；完整法人母體0，兩向榜均空，部分值不混入完整排行。價格／TWD／五日量能None，2330一般報告仍9/23，返回保留原來源／鏈／題材／成員。題材判斷一篇保存、清空明選讀回、核原manifest及新程序原文／revision／recorded_at／來源／日期一致；Journal7556dd973c1663da69c5acb85be8d538a2f46ec0494e1ce90231e9ab0846eb94兩側相同。原capture／用途／v2／assembly與完整MOVED前後bytes／SHA／mtime／ctime保持，模組origins全包內、clean build／實際EXE／manifest吻合，errors／denied／network空。Root看父與新程序首屏及部分值圖。Result50849b0a6392fcbe5cab6c36a483d8bc06e7aabcc84e9c6d5f12f91a374f7808，spec d4b50ce36ffecb6a7522044afce613dd446d2c2e83fc199b6985008c7c70ce18，closure4238ddca7a928651ab07e3009b2dee135616c1a3352c369ba5c67278cfc81a09自然完全閉鎖。

210a實際Launch-Baldr.cmd正確SHA回0、錯SHA回2，設定／清單保持；核Source202e與固定209a的原資料／文字，原09交付b839cb41...未改，模板沒有私人state。固定10交付f987161f453a4f96b4120efba8ccc61ac3d15751524687e9813b47aa9f71974c，template c23a372bfa2b52f1e312b68302a8c9ac4b71d3c2bd672bc5169dd5ba1e251e45，finalizer result933eacf51ed9be64524acbc7b425922fb4461dfec995eb84cafb627950127869；closure2e8ca3344cad5f5286294561af585673d103219b96f3f05ab6e513acde3282b2自然完全閉鎖。原210草稿保留，a版只重綁實際209a。新固定包保留五旅程與來源限制；未改單股法人11欄、價格版、F07、報告、首頁與Registry沿09引用原證據，不重跑或加總成完整Gate。

可選v2仍依賴本機具名task絕對位置，不是獨立可攜來源。66題材部分覆蓋／24無覆蓋不是完整題材法人觀察；888報表列不是股票真N。正式來源用途、TWSE、價格／TWD／合格五日日曆、歷史PIT、完整策略績效、自然成熟、完整Native、跨機與真人接受仍各自未完成。內部Qt事件及Source／EXE技術成功不能冒充這些Gate。
<a id="產業鏈卡片目錄qa212213e"></a>
## 產業鏈卡片目錄（Source QA212–213e）

解除原M2探索阻礙：既有頁只有產業鏈下拉篩選，補上預設收合的全鏈目錄。Luna只交task內UI／test候選，Root凍結固定10後整合；另一Luna獨立靜態複核。目錄沿既有presentation，實際25鏈各列題材數與去重股票數，最多三個題材名稱序捷徑；完整90題材仍可篩選。均值只顯原完整覆蓋且有限Decimal，保留真零／負值，部分與缺值不補零；不新增金融計算、reader或來源接受。

212原spec在Python／Job啟動前被task狀態SHA變動攔下，未列實跑。212a route／4500字context與compile通過；context因預算略過1795字UI正文，不當EOF，Root另讀實際UI差異與契約。初版新測試stale訊號傳False到零參數overload，212b單獨trace定位TypeError；Root改emit()，原身份／選取斷言保持。212c stale通過後busy事件處理Windows AV；212d busy單獨0.51秒通過，證明有組合生命週期因素，不能據此當產品已安全。212e新11例通過後舊async案例AV；212f延長QApplication保活仍在相同跨模組案例AV，因此保活不是充分修復，原FAIL均保留。

Root將新增卡片的lambda捕捉self改為Qt具名QObject接收槽：每按鈕建立時固定snapshot／chain／theme屬性，slot從sender取原值、型別守衛後仍交原identity／busy／closed／pair／filter檢查。獨立Luna對該小差異複核無blocking；不宣稱已由native dump證明唯一UAF根因。測試同session保活Qt，逐例等自身worker結束及釋放自身view，不跳測或放寬期限。212g完整原組合44項通過（12.35秒），Workbench85（3.73秒）、自有validator25／0／4及八套件mypy1082通過；既有UI ignore與untyped notes不證UI強型別。spec6a74d6c6bdff823c629803da0f9e8f21fc929b58a9644d4739ff4f72329f4f48，closure8728b7cabc244df69073fc3c3251b75b26bc332d53438f52956a02c75351c09c自然完全閉鎖。新回歸涵蓋2／27鏈不補造或截斷、名稱前三、原filter／無額外sourcecall、零／負／部分／缺值與NaN／sNaN／±Infinity拒顯、舊來源、忙碌、關閉及失敗清除。

213原helper只靜態保存；213a Root長路徑driver重複將extended I/O path送canonical renderer，GUI前被ambiguous_windows_path拒絕。213b只改digest傳canonical identity，保留strict tree layout與dir／file bytes／hash／mtime／ctime，真Main讀到25鏈／90題材，但末卡二次reveal失敗；213c動態取center仍失敗，未當解法。213d有界幾何診斷顯示：正確widget→ancestor content點為[283,4444]，原viewport→child content轉換卻回全域[728,2364]，scroll停2313，按鈕windowY2248、viewportY2131、hitNone。213e只改為widget直接mapTo祖先content，原16px／15秒及全部可視／global命中檢查保留，另加實際960×720尺寸斷言，不改產品或用isVisible替代viewport。a／b／c／d原FAIL及各自自然閉鎖原件保留。

213e正常Source Main52592→32864 PASS：原75f97365...價格版、25鏈／90題材，每鏈名稱序前三、題材數／去重原成員與原映射一致，首末卡均原Qt點擊；明選半導體／先進封裝(CoWoS)捷徑後2330開一般報告、行情仍9/23，返回保留同identity／鏈／題材／股票。實際1280×760與960×720的目錄、原成員與筆記可捲達；兩程序明選結果一致。Journal皆未建立／未寫，Watchlist a14650aebfdc05604ed21f76ddd0130f2a85c64016e0ee929a0ed3c43f7bb4f8保持，CASE市場1537d8c459c0ba6cd9038f29beec874a38d197070f468558666a5ca376b250ce保持；MOVED10完整盤點指紋4667aedd03dd94d6670db05b25e74e42ceb0cab72cfdec335000ce4a555123dd前後保持，network／denied／errors空，candidate未建，模組origins為ROOT Source。Root看首卡、末卡、960筆記與新程序返回後四張圖；Qt事件不代表完整Native。

Result e131e4047a502e1038eb92a468851e120d2bc3659a3abd8b76e1ab4f830247e1，helper02d3755c2412362bfe9d0b31c777b138e30cb0b66019a507f30cbdf5da201044，spec32d0914df00a58550a5a085b22b38c3ee8c537a2d46a49b138f8db076cc81569，closure55855eff11b3bad953582bfe0f42a6b351e742d9bef60615aa4d992d69b1142a自然完全閉鎖。這是Source卡片葉片接受，固定10未含；後續固定11另以同Source建置／600秒setup／同版EXE／fresh／啟動器／封存接受。原完整M1／M2金融能力、來源權威、正式日曆、PIT、真N與自然成熟等仍分項保留，不以44＋85等加總作整個Gate。

214結構檢查指出新增測試代表入口未列change_patterns，Root只補同功能精確路徑；原FAIL保留。214a重核12features／36link sources、errors空PASS，spec5a52c00e91ba78f9dd9532e8704e002740cc015a267eb6690fb3a20be108c54a，closure0e31f016a30927bb424e78129a9f90f5ca95eb102616804dcdbc956e9c55962f自然完全閉鎖。Source／操作手冊及固定10交付入口已同步；結構核對不取代正文、真UI或完整Gate。

<a id="固定11產業鏈目錄交付qa215219a"></a>
## 固定11產業鏈目錄交付（QA215–219a）

解除原M2交付阻礙：將已驗卡片Source b676c7bca0e07f0c8c213df035bfadaa961563b5帶入實際EXE，讓使用者從25鏈目錄看題材／去重成員數、名稱序前三捷徑、原題材成員及個股返回。完整90題材仍沿原篩選器；捷徑不是績效排名，缺值與部分覆蓋不補零。沒有新增金融公式、來源用途或第六條試用旅程。

215在build前被舊UI pin守衛拒絕，compile通過但不算build；原FAIL保留。215a重新核33來源pins後原archive build通過，build result ace1307fa345cf3f5e23fd6ea7b12172e983cb729e671ee91583fe569975ed84；216 create-only組包9880檔，帶原task具名顯示名冊、未帶私人state。EXE fbd420f0c75c6af13125bf60a6c43da107f0af78eb0aca6b73ddc1d6a68684ad，manifest d150716d784e409273ef8b37361d8d4e5ed7537c74077ca804887e55cf78b636，assembly result6521de8951259f78a85873678c80dde91e6e64739b878f0bac9a0e9b133ff773。215a／216閉鎖2247df04282e4cafe43e6e3a8d9baf9ddb6f799586a05537d710b64c63d5b574／5fb098befdf76f40a073f485af1536939ef92e36bbda06c7e2ff5b2efb828d45。

217先核新RUN在workspace、.t非reparse且不存在，再整包複本移位，原600秒EXE首次設定通過（529.296秒），模板未改。result8a2934121f0d76884f1d0fbdf31c43d881289809f6172c5c5ac1b96f041530fb，closure7a3fa6e0c59b3f8bb4ed310b1d42311b0f94170179940fa8d7fac506ea478531。

218父程序已走完卡片、個股返回、窄窗與關閉，但driver把原清單hash dict的watchlist_before覆蓋成單檔SHA，最後dict==str斷言FAIL；outer完整MOVED盤點仍相同，不當成已證資料破壞。原FAIL與closuredeaa89573a3c4fe373248998103292260189ec3bfb6c498da3cef87fa3306f65保留。Root另存218a，只拆watchlist_tree_before／watchlist_file_before名稱，所有原比較、120秒每程序／15秒動作／30秒關閉、viewport與global命中守衛保持；Source與EXE未改，沒有重建或重設首次設定。219a另存讀實際218a，不覆原spec。

218a固定EXE25964→22428 PASS：25鏈／90題材，每鏈題材數、去重成員數與前三名稱順序符合原映射；首末卡實際可點，CoWoS／2330進一般報告再返回原來源／鏈／題材／成員。實際1280×760與960×720的目錄、成員與原筆記區可捲達；本旅程未建／寫Journal。資料日10/16、一般行情9/23保持。Watchlist3743994cd09c1d779d637881e9f62a2acbb58eb403835e1ac218379298c3972b、CASE市場1537d8c459c0ba6cd9038f29beec874a38d197070f468558666a5ca376b250ce與完整MOVED指紋f96c902b66b18adea4b634bb3f43851a6f85827162ed195b6b9dd8e49ff71230前後一致。模組origins皆包內、clean build與EXE／manifest吻合，network／denied／errors空。Root看父首末卡、新程序960筆記區與返回選取四圖。result9cb1a420483c734a14a79081477b47b6355ed0ba3516617900771db1e2fd1b16，spec3a31e29dbf51f274d5cc7e1faf5ddb04e0eaec48829d3e355f5a2a0a9321ef4b，closure1bb72f890839a82408c13e84b8af95c4d80c3c3ee272302856a1d112b2fc9270。

219a Source213e／fixed218a跨版核同原映射、資料、目錄及選取；各自parent／fresh與清單／原件守衛保持，不錯把不同移位包的raw清單bytes當相同。實際啟動器正確SHA回0、錯SHA回2；原設定與清單不變，原10交付不改。封存研究11交付4e92bc1fc54ca2035e8b6eeba338cff0aaefa6d45e39f8f2584030b68a71544f，template a484fd3d2da1b6b25f7e34986c5e98bd5dd96477426262ca97b3d852e4691626，finalizer resulte4f4b396d3a568646d9c4345f72bdd7c061bbb9717ce3f7cb67970f8a8798b39，closure5ca17e36ed6a8bfa5a37d17918d7ae304dee69287e1239eac46b5f5e59f01d01。

所有組別皆原8GiB committed／12程序／kill-on-close／同workspace mutex／啟動RAM至少8GiB，terminal後三PID空、process與Job handles關閉、mutex釋放，未靠強制清除。僅重用既有Luna靜態葉片及獨立review，累計10/10無新建，Root串行QA。未改v2法人診斷、排行、各類筆記、首頁／期限、一般報告及Registry沿10收據，不重跑或案例加總成完整Gate。完整金融、歷史PIT、正式日曆、真N、自然成熟、Native／跨機及真人接受分項保留；外部TPEx v2來源仍綁task原位置。

220交付文件檢查12features／36link sources、errors空PASS，spec696bcc42ca1ef3134558cd5a0cd621ddadfa204769a2f186ba9f16a8f184e732，closureb06159435dc6fa07d2dab93e266ace80bc1d8ca1df4be8f35532c88cabed819b自然完全閉鎖。Root依實際差異與收據核正文；結構成功不證完整產品或人工簽核。原M1–M4依賴核對在固定11完成後已無獨立READY；來源用途／單位／合格五日日曆與價格、歷史版本PIT／真N及自然成熟均是相依缺件，真人D／Native則獨立AWAITING_USER_APPROVAL。依使用者修正完成一次checkpoint後停止，待新輸入或證據，不重複驗未變阻礙。

## research07回報修正QA221起

本增量解除試用版07的五項操作阻礙：保存context下改查2330、題材清空、原價格圖均線、筆記刪除及績效／逐日訊號混淆。固定11尚未含，不另擴V1或建立新金融前置。兩名既有Luna各單寫UI／測試葉片，Root保留服務、金融展示、整合及QA；累計10/10無新建。Luna獨立靜態複核找出tombstone重試及來源標記漏驗，修正後無新增阻擋；不是runtime接受。

- 221外部Graphify Python被原runner拒絕；221a以workspace Python標準庫唯讀舊9月圖、有界路由／context PASS，圖不證10月Source。Context預算略過的Snapshot/Workspace/F07 view另按實際方法閱讀，沒有全庫EOF主張。
- 222編譯與29項通過、1項新刪除FAIL；222a為20通過、5項因相同合法tombstone前置失敗。222b診斷helper import FAIL、222c揭示schema／tuple表示差異，均保留。Root恢復Journal writer原schema，使用DTO完整JSON序列化對照原完整投影，沒有刪欄；222d PASS，closure `baa4d316b561972eb12811f740a34c546203915022cd38ccd006c4fa28d61e51`。
- 223編譯PASS、161定向通過／4失敗；包括真實保存四均線1筆、W底0筆、布林0筆的逐日訊號對照PASS。三項舊測試仍期待舊context／文字，一項shutdown mock缺現行report_notes_widget；Root只適配現行契約，原來源不混接及績效拒絕斷言保留。closure `0d2561e16d79a4d0d1ad0e9bc4609f1f9ae505c568938d56ef51c32c093833e0`。
- 223a為27通過／1失敗，明確一般查詢的背景worker尚未結束便測關閉；223b保留原3秒有界等待後5通過，Workbench85通過、自有validator25通過／0失敗／4跳過；mypy揭示同名parent變數型別衝突3項錯誤。Root改名current_head，223c只重驗受改notes與八套件mypy，不重跑已PASS且未改旅程。223b closure `2c6a9be9bac04a038e1e8348b488507039aedb0ca4392dd256dfd36a81b2e2f6`。

以上原FAIL、spec、隔離env、完整輸出與具名收據保留於 `output/tasks/baldr-post-completion-execution/`。所有組Root串行8GiB／12程序／RAM至少8GiB／kill-on-close與workspace mutex，前組自然完全閉鎖後才下組。UI既有mypy ignore／untyped不證UI強型別；局部測試不等於正常Main、固定EXE、真人、金融、歷史PIT、完整Gate。SMA為同版收盤20／60筆前綴的顯示投影，非填補原保存指標；刪除只是append-only Journal隱藏家族，來源與原歷史保留。

223c編譯、刪除及舊notes25項、八套件mypy1083通過；closure 8862e7d7f1b8f4bbf7cd685780ea1cd505df99b9bf27bce82fc87e5091dca065自然完全閉鎖。223b已通過共同防線不重跑；接正常Main225與224。

225正常Main9784→20016以固定11原件的隔離副本通過清除No/Yes、同版重載、960×720按鈕可達及新程序；Root已看清空1280與重載960實圖。Journal/Watchlist未變、network/denied/errors空，MOVED全樹inventory SHA 358dd1c72ca67ddde0db7067d34949633ad4b530bff7c4ac8acb4abb298ab393 保持。closure defab3437964fb0c28bd8c34f432fd7d8fc0e28208857c4a5075fb34a13197b0自然完全閉鎖。載入中與筆記busy拒清由定向UI測試承擔，沒有稱此Main覆蓋。226文件檢查12 features／36 link sources／errors空，closure d2ef55b5347becca7c5d00416f1b00ec0e3b069f6c44841140b1c84882de0820；只證結構與紀錄，非正文／產品接受。

## research07Source正常旅程與原案例核對QA224233

本輪解除五個試用阻礙：一般查股沿用保存context、價格圖缺顯示均線、題材無清除入口、原價格筆記無刪除入口，以及績效／訊號比較難以辨識。Source固定ec4dd639b6be6d8922cc7ff5af3467eb48dab6c3；沒有新增金融資格或改原選股、成本、PIT、SOP與成熟判準。

224f正常Main28624→43448通過：同源F07 2506的120筆收盤價與顯示SMA20／60完整逐值留證；筆記取消及確認刪除、整篇兩版隱藏、Journal原歷史與前綴保留、獨立筆記及未保存草稿保持、重開不復活。明按一般查詢後2330由一般SQLite辨識台積電，120筆行情至9/23；status=partial、freshness=unknown、available_at空維持原義。各自前後完整MOVED、來源、清單守衛通過，network／protected／errors空。Result `5236c7b0d8ca3712cb9739559eea047c816024416e9975eab87ed23cae8cc116`；closure `25d022182819f8311a9a39d346e9cd0462f7dec6ea380bbf43e7ff0517c0a36d` 自然全閉鎖。Root查看實際圖，兩線暖機及缺值留白；圖表浮點只在展示邊界。

224／a遞迴長路徑、b短ENV audit、c NUL裝置、d非法config key、e誤要求行情available等測試器失敗均保留原件。修正只在新spec/helper，不改產品來迎合錯誤期望；233a獨立診斷確認原行情partial／unknown。233診斷錯用test profile而查空庫、233a複本Registry仍綁原絕對位置的不可用結果，均不得誤報為使用者原run不相容。

233b使用原研究07的正常唯讀Registry ports核對三筆實際保存run：419列逐日訊號、3策略、comparison_state=available、reasons空；原檔bytes／SHA／mtime／ctime均未變，未產生WAL／SHM／journal。0／1筆成交不阻擋該訊號對照；不推論使用者一定按錯入口，也不把訊號可讀當績效契約通過。Closure `b4d832df11afaad3d7b4e62ea45b12a7a4488c9894f420a9fd63b91cd6cb1b72`。

225題材清除正常Main9784→20016通過草稿預設否／確認是、結果清空、原manifest重載、實際960×720與fresh；原Journal／清單／來源保持。Result `a6b8dd4db289314963aba5aadce608f1af61953b913dc7f703225213ada57c6a`，closure `defab3437964fb0c28bd8c34f432fd7d8fc0e28208857c4a5075fb34a13197b0`。226文控12features／36links、errors空；closure `d2ef55b5347becca7c5d00416f1b00ec0e3b069f6c44841140b1c84882de0820`。223b的Workbench85／validator25-0-4及223c的mypy1083不重跑；ui_qt ignore／untyped不證UI強型別。

上述只接受受改Source旅程；固定12、首次設定與同版EXE依下一節實際收據，不能外推真人、完整Native、金融、歷史PIT或原完整Gate。
## 保存報告完成狀態修正QA238起

本切片解除已完成保存回訪卻仍顯示「讀取中」的操作疑惑，不擴資料或功能。原Luna單寫report view與既有snapshot navigation測試；`show_saved_report_snapshot()`在完整同步呈現後改用既有`completed`／「載入完成」詞彙，來源限制旁文、唯讀控制、原canonical與其他非同步狀態均不改。新增斷言核對不busy與完成badge，原no-producer、無live signals、精度及完整原件斷言保留。

QA238編譯、6項定向、Workbench85、自有新目錄validator25通過／0失敗／4跳過、八套件mypy1083均PASS；既有ignore／untyped不證UI強型別。Route為Execution／TestingQA／Documentation；Context3500字僅作定位，Root另按實際方法與差異核對，未宣稱全文閱讀。Closure `a76244e157ca85776cbd513fe5f29314f651b32e4d9e34800aac2ab097cec1a4` 自然全閉鎖，三PID陣列空、handles閉與mutex釋放，Root串行Job8GiB／12程序／RAM至少8GiB。未重跑與狀態文字無關的原混合回訪、均線或刪除旅程。固定12／舊包／私人原件不改，新固定候選仍待建置及正常Main／新程序證據，不把本組當EXE或完整Gate接受。

## Stage3獨立動量濾網QA246246a

原「第三階段全部等歷史資料」分類過粗；本切片先完成原§5.2規則的可呼叫MODE_A葉片，沒有接策略／回測／UI或寫正式資料。Root凍結輸入、時間及金融門檻，原Luna單寫新module／test，另一原Luna只讀獨立複核；Source證據與實際歷史PIT資格不由旗標取得。無UI改動，不重跑Workbench或重建EXE，研究13及其私人／封存原件保持。

246編譯及43項定向PASS，mypy報7處Optional比較型別錯誤，後續靜態防線尚未執行；原FAIL/spec/env/output保留，closure `ca0d2464a3642bfc0656de5ad08e6a344e69df9ec65bf71c896e76776754c03a`。Root僅在原型別／範圍守衛已成立的三處比較補cast，不改分支或門檻。246a另spec/env/result，編譯、43項、單一新module mypy與既有精度／未來函數掃描器的本檔範圍均PASS；closure `39de0fc7747c5c2a147329d40bd7b1f8d012b0f9aaaa67b7eef5ea4342aa6a09`自然全閉鎖。沒有將本檔掃描當全庫防線；Context1800字略過正文及未提交新檔，Root另讀實際新檔與精確SHA，並非工具已核全文。

邊界包括嚴格>70%、`rank × 5 ≤ N`不向上湊整、正有限Decimal淨流入、跨aware時區／台北資料日、未來或未知時鐘、缺值、部分母體／覆蓋、bool冒整數、錯單位及Decimal精度。純規則旗標不能證明來源或排名，未測真資料、交易成效或PIT回測；下一步是reader／映射與來源版本的實際綁定。五小時100%／週33%時只收尾commit，文件結構檢查NOT_RUN，待下個實際可用視窗執行；不得把本節當第三階段或完整Gate接受。

## 固定13保存報告完成狀態交付QA240244

本增量只把QA238的完成狀態修正交付為可啟動候選，沿原M3／M4切片；不擴功能或金融資格。Source `9838243476e6a2274adecc6763e7e4ac315f1afa`，候選 `output/trial/Baldr-Theme-Research-13`；舊12／07／11／139／141c及私人原件保持。

240從clean Source建EXE，38來源pins保持；EXE `3383e88b9d9d84f79fad56a9a2d4575381000858c78defd0ff5a5593fb8bc475`，closure `14111de35ec5274e6e08f73c59de636fc7a31f429c775e10a957ca857ca0359a`。241create-only組包帶task具名名冊及原raw資產，manifest `b54092cdfca04f381c13e0a3beb4444781d4a30c9746e7cc7b5cd2174c1453c1`，closure `f74ceca18ffb18d3fb2b4d63b4952a7a67fc8d95946aac4e39a8a96f166294b8`。242整包移位全新首次設定521.344秒／原600 PASS，result `0dd821a5dabe857bd00c705e8dbc28cc0f7e1261dfc234eca8f32f35c4de5308`、closure `60897dabab7290d8599e80213d99437e9401d48022ca2a5fe4a16cc59913fff1`；沒有跳過原來源核驗。

243固定Main24960→9440在1280×760從正常「個股研究→我的判斷」明選QA90g原修訂、讀取、開保存時報告及返回，新程序一致。兩次badge精確「載入完成」、不busy，canonical SHA `3ba78f6523d72fa321b82fa7c883f83b81b68dbff4c6b4475a738dca5b482175`、原10/19日期與原產生時間字串不變；producer呼叫及保存／一般報告live signals均空。計數wrapper只透傳原方法，沒有替換讀取結果或手動設context。原Journal SHA `e0fa9cc727dd0b4ea4d403b39c74cae6ecaa1430d2cb9cde42ce25c72d032ca0`、完整donor／MOVED inventory、SQLite及清單保持；network／protected／errors空，Root查看完成標示實圖。Result `be8c768ac5e1d5dcea5ef322e1f7d87fe060d3491b94998fa33d74b392cc2e12`，closure `16814e43a7ff58fbccfd6488411072ba2e919ef0394832f4e51367e53e9a1a70`。

244核精確scenario／雙badge、238命令完成與同版build／EXE／manifest後，啟動器正反SHA退出0／2通過；精確owned負例核bytes後移除，MOVED檔案bytes不變，不聲稱根目錄時間戳不變。`TEMPLATE_FILES.json`沿原schema，模板無私人state；交付SHA `ae7f310408a1551d342ef967a2560e8c84206def94c9820c52b1963230f3341c`，closure `679322dfa9f2faac89769f353bf648f279e351a3bd171eba072c9b8f7d978fa9`。原Luna獨立複核的badge證據守衛已補；SQLite原事件列表每phase保留及限制ENV，未要求兩次非同步開啟順序相同。

各組Root串行8GiB／12程序／RAM至少8GiB，三PID陣列自然空、process／Job handles閉與mutex釋放後才下組，沒有強制回收。未重跑未改旅程；本PASS只接受本輪完成狀態與保存讀回，不是完整金融／歷史PIT／自然成熟／Native／真人或原完整Gate。原三階段設計的Stage3動量與PIT策略仍依賴歷史映射，M3研究筆記完成不代表該策略完成；鏈卡名稱序捷徑不改稱未定義的代表排行。

## 固定12混合回訪補驗QA235236b

本切片補足原M3／M4缺少的「單一Main跨研究來源後重讀原筆記」證據，沿用研究12與Source `ec4dd639b6be6d8922cc7ff5af3467eb48dab6c3`，未修改產品或重建EXE。QA235只作有界導航／角色及context定位；舊Graphify圖不證目前Source，預算略過的Workspace／notes正文已由Root另讀。原有獨立旅程不等價於本次混合回訪，未重跑均線、刪除或清除旅程。

QA236b固定EXE `51684→13624` 通過：明選既存QA90g一般2330筆記的指定修訂，讀保存報告，經題材CoWoS／2330返回原選取、觀察清單F07／2506原價格來源及返回，再從實際一般查詢入口查2330、重讀同一筆記和保存報告；新程序完整重做唯讀回訪。保存報告仍為2026-10-19，新的報告查詢日為10-20；原文、修訂／parent、建立時間與完整canonical JSON逐字一致，SHA `3ba78f6523d72fa321b82fa7c883f83b81b68dbff4c6b4475a738dca5b482175`。一般報告與獨立保存報告的context分開保留，未手動改寫或正規化測試狀態。兩程序context診斷、network／protected／errors均空，Root查看保存報告實圖。

QA90g原Journal與隔離副本均保持SHA `e0fa9cc727dd0b4ea4d403b39c74cae6ecaa1430d2cb9cde42ce25c72d032ca0`；僅精確允許Main正常產生的兩個一位元組`0`鎖檔。原donor與整個MOVED的bytes／SHA／mtime／ctime inventory、行情SQLite、清單和題材來源前後一致；build clean／commit／EXE／manifest及包內模組origins核對通過。

原236spec誤列不存在的package單檔，未啟動Python，原件保留。236a執行時測試器在整體讀取尚忙便按一般查詢，被原守衛拒絕，故15秒入口等待FAIL；closure `ba66d0f42264391413f58e347fda2a39dcba5a61c64f5ee8436cd63fb1ac7ed5`。236b另存CASE／ENV／spec，按原15秒界線先等現有讀取自然結束，再按同一真UI按鈕；保留原240秒每程序、180秒F07、120秒收藏、720秒driver與所有來源／內容斷言。Main操作parent78.922／fresh78.860秒，結果 `ea11221ec7cd32426b3392f95eb536abe4aec395e443ce5fb9605401c7e44476`，spec `dae24b284b7e7275515e76af3c17e8ccfe9941eec2e78d9682fc154420e7a112`，closure `8d729a18369f6820a22c4bbbf4b55e8208ad9068399cbfc75dcd2ce049e23e4d`。Root串行Job8GiB／12程序／RAM至少8GiB，三PID陣列自然為空、handles閉鎖與mutex釋放後才下組，未終止其他程序。

結果為本混合旅程PASS；原金融／來源用途／歷史PIT／自然成熟、完整Native與人工接受分別保留，未授完整Gate。封存研究12、07／11／139／141c及私人原件不改。本次實圖另確認保存報告已同步載入後badge仍以`info`顯示「讀取中」；原Luna靜態定位至`show_saved_report_snapshot`，下一切片只修該完成狀態文字並驗無producer呼叫，尚未實作。五小時用量98%時先收尾，不因剩餘人工接受停掉此獨立READY。

## 固定12research07回報交付QA227234

研究12固定Source `ec4dd639b6be6d8922cc7ff5af3467eb48dab6c3`，位於 `output/trial/Baldr-Theme-Research-12`。本輪沿既有五旅程解除research07五項操作阻礙；[啟動器](../../output/trial/Baldr-Theme-Research-12/Launch-Baldr.cmd)、[指南](../../output/trial/Baldr-Theme-Research-12/TRIAL_GUIDE.md)、[已知問題](../../output/trial/Baldr-Theme-Research-12/KNOWN_ISSUES.md)與[交付收據](../../output/trial/Baldr-Theme-Research-12/DELIVERY_RECEIPT.json)已封存。EXE `918624dd549daec146c69b8986ce8b887e03bccb135ba9d9de1c8fef0f595dc6`，manifest `08409ef440930d6c395fec97a35e6d3c1084089f134690cd9f18aa911ac20760`，交付SHA `d161a7363131062e37c153d03760b7f323c18c5a7cfbc37c65a05bbc4d1613c1`。07／11／139／141c及私人原件保持，未push。

227從clean commit archive建EXE並核37來源pins，result `54f87b3300c7fa429a773143372c8152fe3450c435c1b766b03f7f22b5de7991`；228create-only組包，帶原task具名顯示名冊，無私人state。229移位全新包首次設定517.579秒／原600通過，result `410d10911ac4dfdb3a60da034b157a3e8a569c3644646b500bf7f1acf335087d`。三組自然全閉鎖SHA依序 `f97204df1ddb219ce3c311b48424eb7ffee98e3b521b9268bf944c5694783fc4`、`0b3c65aa4d42fa3813adf89aa6e2fecd0099fdc9151706928703f9a116bb1fb9`、`8d41e52e7bb8df33b2ad7adf5c0879d9678a2df2f8e06d446b3e2a38c6be9cf7`。

230在Main前因測試器引用未封裝QtTest失敗；230a改既有173a的包內Qt事件API，但短ENV仍為q230，被原create-only守衛拒絕。原FAIL／spec／partial保留，closure分別 `268d6061adcfa5bae8fc4b5723cc8e9634b80f9c5ae0015d3b38dc7e7f2dd003`、`3e73f76e739810bc427c257e079fc2117168d74502f616f98b975e0ed4ce41b5`。230b只另存獨立CASE／q230b，保留原240每程序、F07／筆記180、收藏120及一般查詢15秒期限與全部原斷言；產品Source與EXE未改，不重建。

230b固定EXE10788→26748通過：原F07 120筆收盤與顯示SMA20／60逐值、取消／確認整篇及修訂刪除、Journal前綴與原歷史保留、另一篇及未保存草稿保持、重開不復活；一般2330名稱台積電、120筆價格與9/23日期、partial／unknown原義均符合224f。Main內操作計時parent175.157／fresh108.188秒，兩child均在原240秒期限內返回0；build clean／commit／EXE／manifest與包內模組origins一致，沒有拿虛擬PYZ .py路徑作檔案雜湊。完整MOVED前後一致，network／protected／errors空；Root看實圖。Result `baad54a53d9c7bf9fac8cf0ac4d1ae74dd6d0a26a825c8e57e125230fbcf35f7`，closure `73dd0842b9c61c0a140d6d0934bdbb033e1634a804ee6d0e450f902dd6531da1`。

231固定EXE41268→10408通過題材清除草稿No／Yes、清空結果、原manifest重載與實際960×720／fresh；原完整MOVED、Journal、清單及來源前後一致，network／denied／errors空，Root看1280清空與960可達實圖。Result `02d7ed5928cfd399d72a221d02b1eef5c2f68a17f544cfbaa13f5d294cb9a5ea`，closure `67bf763a96a05042127546b4e08a480d122a4b7ce8fa1db881d986d4c0d27785`。

232交叉核Source／固定EXE兩旅程、原120價格與均線向量、同一路徑的parent／fresh及各自清單／Journal守衛，實測啟動器正反SHA退出0／2。自建negative檔在精確MOVED根目錄以xb建立，核owned bytes後移除；MOVED全檔bytes前後一致，不宣稱根目錄時間戳不變。交付含233b原07三案例419列唯讀證據，指南及已知問題只增本輪實際範圍。Closure `1d1cd31aa0134fe6a4ac21edc6690165b3bc70bea76ec739563c975d488fa75b`；原Luna唯讀複核的清理邊界已納入，無pending writes。

所有Python／compile／QA由Root串行，Job8GiB committed／12程序、RAM至少8GiB、kill-on-close／workspace mutex；每組terminal、三PID陣列空、process／Job handles閉及mutex釋放後才下組，無強制清除成功。必要文件出口依task內234原收據；文控不替代產品旅程。本輪未重驗未改流程，不提升正式來源用途、金融績效、歷史PIT、真N、自然成熟、跨機、完整Native或真人接受；原完整計畫各未完成項目保留。
