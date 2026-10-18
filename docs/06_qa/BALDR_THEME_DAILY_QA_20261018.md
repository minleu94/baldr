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

本機題材Source旅程為PASS WITH KNOWN LIMITATIONS；M3完整首頁多候選選取／通用研究閉環、M4固定交付與其餘原UX清冊未關閉。前置原D的技術補驗與真人簽核分開；官方來源用途／精確可得性／歷史PIT／TPEx授權／真N／自然成熟不因本輪解除。沒有新增正式資料寫入、backfill、maintainer、push、發布或交易授權。
