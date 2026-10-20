# PROJECT_SNAPSHOT（目前狀態）

> 更新：2026-10-19（使用者時區）。本頁列目前入口、各流程進度與下一個出口。逐輪身分、原FAIL與收據見[具名QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)，交付順序沿[原計畫§0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)。

## 現在有哪些入口

**最新可試用：研究10（`6f27d4aebbbf`）**，[啟動器](../../output/trial/Baldr-Theme-Research-10/Launch-Baldr.cmd)、[五條流程指南](../../output/trial/Baldr-Theme-Research-10/TRIAL_GUIDE.md)與[已知問題](../../output/trial/Baldr-Theme-Research-10/KNOWN_ISSUES.md)。新增明選10/19上櫃法人題材版本：看原股數與覆蓋分母、2330個股返回、保存判斷及重開原文。90題材中66部分覆蓋／24無覆蓋，完整法人排行無合格列；價格、TWD金額與五日量能不補值。首次設定569.641秒／原600，同版EXE33924→40200與啟動器正反SHA通過。EXE `31f8408b87ab16c617bdf4ec45068edd909ab6a47c89a4db7329408672a542f7`，交付 `f987161f453a4f96b4120efba8ccc61ac3d15751524687e9813b47aa9f71974c`；[QA206–210a](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#固定10法人題材交付qa206210a)。來源綁本機具名task位置；未改流程沿09證據，舊包及私人state保持，完整金融／PIT／Native／真人接受分項保留。

**後繼Source：產業鏈卡片目錄。** 原M2的25鏈探索補上收合目錄、各鏈題材／去重成員數及名稱序前三捷徑；不新增金融公式。212g定向44／Workbench85／validator25-0-4／mypy1082、213e正常Main52592→32864的25鏈／90題材、1280與實際960窄窗、2330個股返回及原件保持通過，Root看圖；[QA212–213e](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#產業鏈卡片目錄qa212213e)。固定10未含，下一出口是固定11同Source建置／首次設定／EXE與新程序；不是完整M2金融或原Gate接受。

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
- **主程式與資料**：`ui_qt/main.py`，九個頂層工作區；資料位置由 `data_module/config.py` 的 `TWStockConfig` 管理，預設 `DATA_ROOT=D:/Min/Python/Project/FA_Data`，不能以 repo 相對路徑推定正式資料位置。
- **L2 產業鏈與題材**：[`decision_module/industry_theme_map.py`](../../decision_module/industry_theme_map.py) 保留季度／手動25鏈萃取。後繼application層另讀明選本機版本、每日聚合並接題材頁及研究筆記；規格見[設計文件](../02_features/INDUSTRY_THEME_MAP_DESIGN.md)，原萃取[QA](../06_qa/INDUSTRY_THEME_MAP_STANDALONE_QA_20261016.md)與新[限定旅程QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md)分開；固定143尚不含新頁。

## 重要限制

- 正式資料寫入、全量回補、正式 Task／maintainer 變更、push、發布與交易沒有新增授權；私人資產與其他 owner 變更受保護。
- 金融精度、決策當下可得性、來源用途、原 FAIL 與各 Gate 門檻維持；缺值與未知不能補零。
- Historical replay、readiness、dry-run、shadow、Paper、合成資料或測試通過，均不能代替真來源、有效績效、真人接受、自然成熟或 production ML 資格。程式碼／EXE 可啟動也不授上述接受；UI 的既有 mypy ignore 設定不證強型別。
- Root 串行 QA 與資源守衛依[共用規則](../agents/shared_context.md)。本補完 task 已用完新建代理額度 10/10；只在無待寫與無衝突時重用既有 Luna。

[143固定交付](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment143-setup-work-scheduling)以537.875秒通過原600秒本機新位置設定，正常EXE與同版新程序核受改月營收、窄頁、顯示名稱及同源收藏，啟動器正反SHA通過。派工寫2／讀4與完整守衛保持，原142 FAIL／partial不改；完整跨機、Native／真人、金融資格與原計畫各Gate仍分別待驗。
