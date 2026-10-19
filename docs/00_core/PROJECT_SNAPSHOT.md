# PROJECT_SNAPSHOT（目前狀態）

> 更新：2026-10-18（使用者時區）。本頁列目前入口、各流程進度與下一個出口。逐輪身分、原FAIL與收據見[具名QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)，交付順序沿[原計畫§0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)。

## 現在有哪些入口

**新增可試用：題材研究02（`b292f803ce9c`）**，[啟動器](../../output/trial/Baldr-Theme-Research-02/Launch-Baldr.cmd)與[指南](../../output/trial/Baldr-Theme-Research-02/TRIAL_GUIDE.md)。包含筆記直接前版比較與個股首屏日期／依據分層；固定EXE移位首次設定492秒／原600秒、正常Main49584→新程序21272、三筆精確原文／保存期間關閉／實際800px比較及啟動器正反SHA通過。EXE SHA `2dfba4f2439406fbe62ece846e4ac60e81904d94d86dd914c4702fed5253b02c`，交付SHA `b044c2eb15760f20c903b375c4e9eccc9c3b5913cc2ce9193c7164c24735a4a2`。原日常資產及自有task具名名冊保持bytes，模板無私人state；01／143原包保留。首頁明選控制項已封裝，但真實多候選固定旅程未驗。題材10/16與一般行情9/23分開，法人／五日曆／PIT及完整Gate／真人限制保持。

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

**原價格版本的個股判斷仍是Source候選，尚未交付。** 已接既有Journal保存／修訂及原來源回訪，backend與定向UI／跨頁測試通過；正常Main在2506原收藏的完整來源核驗階段逾時，未到筆記，最後診斷另有未歸因的存取違規退出，不能稱正常旅程通過或納入固定03。原FAIL、堆疊及界線見[QA62–74](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#原價格版本的個股判斷qa62至qa70)。固定02保持可試用。一般整份個股報告的可往返codec另作獨立READY葉片，不以來源核驗阻礙停止全部M3；首頁真實多候選在允許QA資產尚未找到，其他資料未檢視，不宣稱不存在。

**一般整份報告保存與正常重開已通過Source旅程，固定03待建。** QA89的11項定向、Workbench85、validator25/0/4及八套件mypy通過；QA90g正常Main載四股、三篇判斷、原報告、直接修訂比較、保存期間關閉等待及另一新程序精確讀回通過，未重查行情。數值、原缺件與來源資格保持；排名context仍拒絕保存。測試環境與同步失敗原件完整保留，不當產品金融或完整M3接受；02／01／143未改。證據與隔離範圍見[QA89–93](../06_qa/BALDR_THEME_DAILY_QA_20261018.md#一般報告正常main新程序qa8993)。

**筆記回訪比較與個股首屏改善已納入固定02。** 可並列直接前版原文，實際800px窗及新程序保持Journal bytes；股摘要保留有日期的行情事實，分開持倉、本次技術線索與明選保存推薦正反，查詢日不再誤稱資料日。Source相關70項、validator25/0/4及mypy1076與同版EXE受改旅程各有證據，原鍵盤等待FAIL及診斷保留。一般個股通用判斷保存與完整M3仍待，詳[本輪QA](../06_qa/BALDR_THEME_DAILY_QA_20261018.md)。

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
