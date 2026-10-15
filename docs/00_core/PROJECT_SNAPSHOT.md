# PROJECT_SNAPSHOT（目前狀態）

> **更新基線：2026-10-15 UTC（使用者時區10/14）。** 使用者已恢復補完並採納每日版本快照與台北小時可用性政策；本輪實作／隔離驗證見[每日快照政策 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)，原安全接手點見 [10/14 暫停 checkpoint](../06_qa/BALDR_COMPLETION_CHECKPOINT_20261014.md)。本頁只記目前可支持的整體狀態；局部 PASS 不相加成完整工作包或產品 Gate。較早恢復歷程見 [10/12 補完增量](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md)，先前紀錄見 [BALDR_COMPLETION_PROGRESS_20261011](../06_qa/BALDR_COMPLETION_PROGRESS_20261011.md)；原始 receipts／source inventory 依各收據所列路徑與 SHA 追溯。

> **最新狀態（使用者時區2026-10-14）**：使用者已恢復，RAM達標，新owner task為in_progress。Increment20原候選／Reader與正常Registry旅程已限定驗證；Increment21日曆完整transport／create-only批次沿原兩市場解析器與93日上限。Increment22原執行輸入已接V3保存／public reader；Increment23明示daily批次已接原Registry診斷並完成合成Main／fresh讀回。正式Main尚未配置真日曆用途接受，來源／幣別／成本unknown仍阻擋完整績效。詳[本輪QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。原FAIL、舊task與其他owner變更保留，Native／EXE與完整P00–P14／G0–G4未接受。

Increment22已把原next-open執行輸入接入additive V3附件、原Registry staging／CAS及正常保存入口；保留未指定與明示0、submitted／effective lot及policy metadata，舊V1／V2讀法不變。V3 codec17、Registry11、原Reader／預算回歸、mypy1012與必要UI檢查各自通過。正常Main保存後的焦點FAIL保留；父24812→fresh28756重用該兩筆run，精確重開／雙run診斷／返回通過，9來源bytes／SHA／stat不變，未重產producer。新增超限反例先FAIL，V3沿V2讀前16MiB上限修正後PASS。input SHA只識別原輸入，不授execution／cost implementation authority、source／currency、PIT或完整績效；詳[Increment22 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment22原producer執行輸入捕獲進行中)。

Increment23已把明示daily日曆版本接到原Registry雙run診斷，共用原public reader及缺日比對；外部雙SHA、獨立兩市場用途接受與actual cutoff完整固定，前後重驗不掃latest。新backend首輪12PASS／1個Root測試atime核對FAIL保留，該案修正後PASS；原pair33／controller9、新controller16、widget5、Workbench85／validator25-0-4／mypy1012／精度守衛各自PASS。父33268→fresh17672重用既有run／原日曆原版及更正共17來源，不重產，版本／非clock診斷及bytes／SHA／stat一致。只有隔離QA注入合成接受紀錄，正式Main尚未配置真接受錨點，daily預設保持阻擋；真來源、長期分段與完整績效等缺口不變，見[Increment23 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment23每日日曆版本接原registry診斷)。

## 現在有哪些入口
Increment30已核既存完整TWSE Swagger與政府資料集11761、官方條款／授權鏈，Root僅接受TWSE年度股票日曆的前瞻每日研究用途，接受紀錄SHA `7f120b20e261d6173f2536ab206ddb4576b258954fc7839259ceb5adf84bf697`。不接受未文件化的任意歷史年度查詢；內部schema不是官方版本號。TPEx年度POST的自動取得／用途授權仍缺證據，已由官方中文條款實際頁面確認不能借其他開放資料集授權。沒有發行TPEx接受、雙市場binding、日批或正式Main配置；下一葉接續原雙策略其他權威缺件，完整Gate不變。詳[Increment30複核](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment30年度日曆用途複核與具名缺件)。

Increment29正常Main已有明示外部SHA固定的日曆用途接受binding接點；使用原有界／單link／reparse／stat守衛，Main持有設定副本，錯binding只阻擋日曆用途。新binding／設定30PASS／1平台SKIP、UI注入8PASS、受影響舊145PASS／1平台SKIP及必要UI／mypy1016各自通過。父2440→fresh36248透過正常配置載入年度合成錨點，重用原兩run完成重開／比較／返回，13來源不變；錯SHA Main34496仍建立其他工作區。這是offscreen正常Main限定證據，真用途接受、正式配置、Native／EXE與完整Gate仍待；詳[Increment29 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment29明示接受binding接正常main)。

Increment28重用QA27／49真原件與13份已釘選來源，建立保守完成觀測的年度transport／evidence候選，兩程序20552→32736同custody／evidence SHA、原來源不變。原receipt沒有worker-result SHA，故不補寫舊收據；新候選明示採controller完成上界，worker時鐘只作另行釘選佐證。沒有新抓取、真用途接受、daily發布或年度Main配置；下一葉核既有官方用途鏈與一次性接受的精確範圍，再沿原daily／Main推進，詳[Increment28 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment28真取得原件的保守完成觀測與custody)。

Increment27年度evidence已沿原daily生命周期接入具名保存／reader，與月別共用create-only／fsync／pending／時鐘及exact重驗核心；原Registry依兩份可信接受錨點明選reader，不以失敗fallback。新20案、真控制器讀回1案、舊80／daily controller16、Workbench85／validator25-0-4／mypy1015及精度守衛各自通過；原等待FAIL、fixture／啟動命令ERROR保留。真用途接受、真收據到typed transport的觀測時間依據、正式Main配置、年度正常Main／fresh與完整跨年仍待，完整Gate未接受；詳[Increment27 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment27年度日曆沿原daily與registry接線)。

Increment26已補獨立年度雙市場期間evidence及Root逐年衍生，新23案／舊74案通過；首輪mypy兩處混合tuple型別FAIL保留，改明確分市場取完成時鐘後兩讀回／mypy1015／精度守衛通過。該批當時尚未接daily／pair，後續接線見上列Increment27；真用途接受、成功批次／正式配置與正向完整跨年仍待；詳[Increment26 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment26年度雙市場期間證據)。

Increment25已補具名TPEx年度POST transport／codec，與舊V1共用完整body守衛，沒有新增getter或monthly fallback。新39案先通過，超大參數案例因Windows test ID環境長度錯誤保留原FAIL；縮短ID後該案PASS，舊回歸53／mypy1014／精度守衛通過。年度證據及daily接線、真用途接受與正式配置仍待，詳[Increment25 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment25具名年度post完整原件transport)。

Increment24已重用QA49完整年度原件，補TPEx HTML結構解碼及原日曆模組的股票分類：保留合法省略cell結尾的說明、rowspan與多日期；股票2/11交易、2/12–13僅結算，債券日期不套股票。新41案、舊116PASS／1平台連結SKIP、mypy1013與精度守衛通過；來源用途、具名年度transport／daily接線及正式配置仍待，未授歷史PIT或完整Gate。詳[Increment24 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment24tpex年度原件的股票日曆解析)。

最新 P03 Increment 18 已把封存 Source V3／Recipe V3／Bookmark V3 接回原 F17 正常頁面、owner-thread actor、Main typed saver 與 Watchlist「個股分析」。四個 caller 外部 SHA 保留原 Reference V3／Artifact V3 descriptor／ArchiveReference V2／Artifact V4 descriptor；完整 roots 先檢核，binding metadata 不讀 mutable pointer。Bookmark9、storage27／1protected reparse SKIP、Watchlist5及 archived UI 漂移重開1（44.49秒）各自 PASS。正常 Main 父54640→fresh32420保存1128／頁1並精確重開：父關閉後改私有DB/raw、移開原snapshot與舊reference目錄、改壞series pointer，fresh仍full258／同origin recipe／四錨點及頁面codes。26固定來源bytes／SHA／mtime及原320 F17資產不變，outer `523ae360503c4b538f7eec39f3f87279`／SHA `a9fd1398409b0c14f8510c4ed6e7e0ba3f20a3417f24dbc859b8a5c7d2fc063d` 完整閉鎖。mypy1003 PASS但既有ui_qt.* ignore_errors=True不證UI強型別；受影響舊V2 UI1／V1 UI6／錯收藏路由2、Workbench85、validator25/0/4及金融精度守衛另通過。Increment17 backend55252→9188與其29新案／32回歸保持各自原證據。這解除限定合成封存保存／正常UI／新程序工程缺口，不授官方來源用途接受、歷史PIT、正式publisher、完整Recommendation或EXE／完整Gate。下一批推進P08官方expected sessions／日曆provenance、同股完整期間雙策略pair reader及正常歷史保存／重開（[靜態缺口](../../output/tasks/baldr-completion-policy-20261014-01a1390b/p08_full_period_next_static_increment17.md)）；真來源完整鏈、TWSE單位版本／品質、真N、Native／EXE及自然成熟仍待。所有原FAIL／timeout／權限SKIP保留。

本批 P08 已接原 next-open Decimal capture → recommendation-portfolio-result.v2 → 同一 Registry staging/CAS → strict public reader → 正常 Main Registry opener → 新程序。實際 PID 56200→40264，五份設定／SQLite／Parquet／附件 bytes/SHA/mtime 不變，原本金9007199254740993.01精確保留；策略／成本識別缺件保留capture但precision為None，來源／幣別／calendar仍unknown且不可比。超大整手成本搜尋改有界整數二分，保留原政策、最低費用、日期與相鄰成本呼叫斷言。P03 Selection opt-in V2已固定full cohort pin、open/finish全市場核驗與批次／first-persist身份；V1 snapshot wrapper明確拒V2，完整V2 wrapper／finished decoder已限定驗證，原F17月營收V2查詢／比較／書籤已另補合成正常Main／Watchlist及新PID限定驗證。215PASS/1FAIL、93PASS/10FAIL原封保留；受影響成本斷言與十案已精確恢復PASS，981來源mypy／金融守衛／UI87／validator25/0/4及Main新PID驗證通過。當版來源／52保護資產與完整收據SHA依task.latest_source_readback。此前P03 Main29512→33656／18源、所有原FAIL與權限SKIP維持；正式日常批次發布、來源一次性接受、兩策略同股全期間／正常UI保存、Native／EXE與完整P00–P14/G0–G4仍待。

上一Root施工期間的 Git HEAD `5cedd657` 是其他owner加入的Direct排程文件提交；該輪起始基線為 `10eb154a`，其後實作與WIP已由checkpoint `789f82565ce4c95d1ee7fe8b585382b2d2e60811`保存，原收據仍受保護。Direct同次自然失敗後只停用既有maintainer的授權狀態依[排程運維指南](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)，不自行重新啟用；當時資料、P02與P08增量尚未提交，之後已由上述checkpoint保存。P02正常bundle V3 opener三個consumer案例、V2價格共通AND gate的11個consumer案例、presenter三個／bookmark十個案例均以已保存257股／雙parent來源通過直接重播；bookmark型別窄修後只重驗該十案，八roots mypy972檔PASS。後續正常V2 view受影響回歸及指定合成257股／雙parent的真Main父54060→新PID34696收藏重開旅程通過，首次view的scroll精確恢復已修；當版974來源mypy、Workbench85及validator25PASS／0FAIL／4protected skips通過。這不是原producer suite、真N、來源資格、Native／EXE或完整P02接受，300秒／60秒producer FAIL及原型別／UI／harness FAIL保留。TWSE JSON preparation獨立44PASS，真507603／597961bytes partial拒絕；另唯讀重用10/13完整原件，2330／11509解析及父33056→新PID45600一致，單位未驗／shadow／未發布snapshot。當輪TWSE兩GET已用完：Swagger完整、API未EOF仍FAIL，沒有重抓。P08正式工作樹102PASS及合成Main／fresh旅程維持原限定範圍。來源SHA、各FAIL及閉鎖收據見[本輪QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

baldr 已有九個本機工作區，主程式是 `ui_qt/main.py`。下表說明可以從哪裡開始研究，並非所有來源、候選版本或投資效果均已驗收。

本批續推 P03 已接入 saved-capture producer／UpdateService 明確 root、scope、接受錨點與 batch port，受影響回歸76PASS；合成父15480→新PID20956同manifest／receipt／原件與DB讀回，晚materialization不提前。P08一般回測保存的日期遺失已窄修，相關及provider回歸83PASS，Workbench85、validator25／0／4protected skips、八roots mypy976檔與精度守衛通過。所有早期FAIL保留，原件／時鐘／隔離守衛未放寬。真MOPS完整取得、TWSE單位版本證據、雙市場pin與正常P03 UI、兩策略同股完整期間損益／Native／EXE及完整Gate仍待；詳細限定範圍與當版來源綁定看本輪QA。

| 你的需求 | 已有產品入口 | 使用時的限制 |
|---|---|---|
| 整理行情、確認資料日期 | 數據更新與資料狀態檢查 | 使用自己的合法來源；缺庫、缺表、日期落後分開判讀 |
| 了解市場與個股 | 市場探索、個股研究 | 原始排名、來源與品質各自保留，unknown 不能當零 |
| 比較候選與策略 | 推薦分析、策略回測／Research Lab | 歷史研究與 Paper 不代表正式投資有效或可交易 |
| 保存名單與檢查持倉 | 觀察清單、持倉管理 | 真帳、聲明持倉、研究 Paper 帳分開，保存重開依精確來源判讀 |
| 找日常重點或排查系統 | 決策工作台、系統狀態 | 顯示與導航不授自動交易、模型 promotion 或資料 writer 權限 |

第一次使用依[快速開始](../07_guides/QUICK_START.md)；換電腦依[首次安裝／移機 Prompt](../07_guides/FIRST_INSTALL_PROMPT.md)。新版完整產品包尚有以下工程驗收事項，已交付舊包與當前候選不能混用資格。

## 目前工程狀態與限制

P00/P03完整V2快照保存／exact重開、月營收public consumer V2／V3 reference及有界每日選版已有合成限定證據：full pin／原件SHA／外部錨點與雙ledger／狀態分母保留。父24716→fresh9700保持15來源不變；無值清冊也拒future pin後，新PID51228已重新綁定同保存parent。原兩組99PASS／9FAIL／1SKIP及100PASS／7FAIL保留，各自只重驗原9／7項；最新986mypy與精度守衛通過，Root每組8GiB／12程序且自然歸零／handles關閉／mutex釋放。這是B/C工程缺口的交付；正常V2投影／UI、每日固定配置、官方單位與財報完整鏈、Native／EXE及完整P00–P14 Gate仍待。原FAIL、歷史PIT／Paper／Forward限制不改，詳[最新實作QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)及原補完計畫§9.5。

接手起始HEAD為 `10eb154a`，已核50份暫停資產及兩份恢復收據的完整SHA／大小，P08同組合原 **10 PASS／4 FAIL** 保留。P00／P03的MOPS月營收小時契約、manifest v2原件橋與明確批次consumer已有同組 **82 PASS／0 SKIP**、三來源mypy及Big5→parser→Decimal normalizer→隔離DB→新PID consumer的合成證據，前期比較同受批次小時gate；後續巢狀表反例的preparation套件單獨12PASS，不相加成完整Gate。Scrapling0.4.15已隔離釘版；t57清單／表單成功、PDF取得仍FAIL。原月營收static報表超20秒、未取得完整原件；新getter已用獨立worker驗證20秒停止／回收，單次真GET仍只取得294912bytes、未EOF。原QA07 WinError5瞬間來源仍未知，原FAIL不改。P02目前進度依上方摘要，正常V2／watchlist／指定合成來源的新程序旅程已接線及限定驗證；治理與來源綁定接續完成，真N／Native／EXE仍待。A–D分流與下一批依賴已更新原計畫，TWSE官方單位、真來源發布、正常UI、同版EXE、正式資料／Task及完整Gate仍未完成；以下較早候選與暫停紀錄按各自原版判讀。

產品補完範圍仍為 P00–P14、M1–M3、F01–F23、UX01–UX24、G0–G4。10/14 checkpoint 當時依使用者要求停下、紀錄並 commit；目前已依本次授權恢復，重用原三位 Luna 靜態協作、Root 串行受控 QA，完整產品 Gate 尚未接受。Health／ML 修補提交 `e0d76604` 保留；P01 各版效能候選仍在私有凍結來源中，未正式採入。使用者已同意暫緩篩選 p95 作為其餘補完的前置：385.9978ms／原 strict300ms FAIL 原樣保留，沒有改成 PASS、重跑矩陣或 profile，後續另討論優化。

P01 最新 Root11／Root12 tiny buffer 候選的原五 cold＋一 warm 矩陣與90份完整 DTO 已核對，但三類 p95 都超過原300ms門檻，因此不採入。後續診斷基線選 Root09 指定候選（篩選336.2761ms仍FAIL）；Root14新封套80fadf已完成資料／來源／原生profile綁定審查，唯一warm34bbae已native0。獨立保存資料核驗1b94通過90份完整DTO、813份profile、provenance及自然worker終態；篩選觀測熱點在檔案讀取與原生來源驗證路徑。Root15私有候選只合併快取layout pin的重複fstat，原一般reader保持；聚焦8反例1541、完整raw／AST逆回、新BIND9849、控制compile78f47、新origin3abb及原41契約b197已通過，全部按各自來源範圍判讀。同版原lease13、semantic13與currentquery23也已全數PASS／0SKIP，各組自然閉鎖；query23包含strict-focused唯一PASS，保存結果可直接追溯。獨立rolling2已以Root03修正版完成原兩項PASS／0SKIP，保持34斷言、8/16bounds和10/20/30秒等待；3,116 pins及3,078實際mirror另經Root讀回、outer a718自然閉鎖。Root16唯一完整效能矩陣與獨立90份完整DTO／p95重算已完成，原篩選p95仍FAIL。profile耗時不作效能Gate，沒有正式採入。詳細候選、失敗與收據見[10/12補完增量](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md)。

唯一warm outer9e87、資料核驗outer f2e6與Root15聚焦outer4f292皆native0、三組PID陣列空、process及Job handlesclosed、mutexreleased，已記錄安全接手點。先前資料工具的原FAIL收據保持；自然閉鎖只代表可安全開始下一組。所有原件及唯一intent保持，不重跑80fa／b3f5／8bec／9098／c19／e6f9。使用者明示由Root審查、Luna max協作，本輪沿用三位subagent做靜態實作與複核；Python與QA仍由Root串行，以原8GiB／12程序、來源／store／PIT守衛、斷言與期限執行。近期接手背景與資源約束見[2026-10-12恢復交接](../agents/shared_state/BALDR_COMPLETION_RESUME_PROMPT_20261012.md)。

| 主題 | 最新可支持的狀態 | 判讀依據 |
|---|---|---|
| P08 保存結果旅程 | 當版3113 composite candidate已經Root05單一reader transport、DATA896c／BINDfb22／compilea539／origin19ea，原suite b360實際5 PASS／0 SKIP、20.650秒，包含latest append／old-prefix／fresh；來源守衛與3172 pins／3113 source及mirror、實際同Job child由Root另核，outer2b656自然閉鎖。來源複核仍依3bcd保存範圍：active3085／support1互斥，不宣稱DATA重新擷取membership。原cb4f的4 PASS／1 FAIL及3e62、日期transport FAIL保持；原39assert／10args／60秒不變。尚未正式接線、正常Main／同版EXE／真來源或完整P08／產品Gate接受。 | [10/12補完增量](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md) |
| P01 Main | 單次原生觀測仍為access violation／完整來源守衛終態FAIL，pins／mirror穩定。唯一348,191bytes dump經exact DLL／PDB及136bytes有界unwind，確認捕獲fault在faulthandler watchdog路徑；保存frame參數地址等於False singleton，fault為NULL code欄位讀取。指標形成與初始／次生因果仍未知；不授Main接受。 | [10/12 補完增量](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md) |
| P01 矩陣 | 最新Root16唯一原五cold＋一warm已完成診斷，原翻頁185.1541／篩選385.9978／排序192.1658ms，篩選仍FAIL；Root已核6,994 pins與資源閉合，獨立90份完整DTO／p95重算已完成，原篩選FAIL保持。前版Root11／Root12三FAIL候選不採入。前版Root09為216.3426／336.2761／172.8405ms，篩選仍FAIL；選其指定來源為後續診斷基線，不授formal／P01／產品Gate。全部既有原FAIL及唯一intent保持。 | 同上 |
| M25／M26／M27 | M26六phase聚焦案例已有同helper證據；M27已經Root完整raw／AST／3497pins／18compile／382closure、純預檢及actual origin核對。完整矩陣完成診斷仍效能FAIL，來源版本明示保留舊SHA，不授最新版formal接受。 | 同上 |
| Health／ML長路徑 | Health11path＋fixture及ML6來源＋helper／test精確採入；r03修正lineage暫存leaf263，新3085來源／17formal origin通過。新版ML159、incremental104、callers329PASS／2SKIP、UI85、governance51、validator與syntax20通過。原長路徑18案例16PASS／2FAIL收據保留；使用者授權一次UAC後，原兩項no-follow另組2PASS／0SKIP，來源及原守衛通過，沒有改永久權限設定。Qt保存raw九份完整欄位相等僅資料診斷，原types守衛FAIL保持；新同版Health正常／freshMain1PASS，P01完整Main與工作包／完整Gate仍待。 | 同上 |

Root16 新完整矩陣資料封套 `0db89369` 已保存，包含 6,902 pins／17 payload／10 compile 證據。受控 reviewer Root02／Root03 的兩個精確投影 FAIL 保留；Root04 審核 `87512a1a` 已通過，Root另核 6,985 pins 與編譯產物。新 origin `374cef13` 實際通過，Root讀回 6,987 完整 pins、3,775 啟動 pins、51 file／3 namespace origins及 fresh PID 37624；outer `ad1b7a94` 三組 PID 陣列空、handles關閉、mutex釋放。矩陣入口窄修已完成，新的matrix-only sibling保留原seal／origin／review鏈，核stdout指標與完整收據。唯一矩陣已自然完成，原篩選p95仍FAIL；Root完整來源／資源及獨立90份DTO審查皆已完成，未重跑origin或矩陣。P08 單一 reader transport 的 Root05 DATA `896c5036`／新 BIND `fb22df69`、compile `a5392010` 與新 origin `19eac173` 已完成；同版原 suite `b360301c` 實際 5 PASS／0 SKIP、20.650秒，含 latest append／old-prefix／fresh。Root核 3,172 pins、3,113 source／mirror及 fresh 的同一 Job／十參數／60秒／兩個實際 PID；outer `2b656bae` 自然閉鎖。舊 `cb4f` 的 4 PASS／1 FAIL 不改寫。此為指定 composite candidate 旅程資格，正式接線、正常 Main／EXE、真來源與完整 Gate仍待。

上述工作依賴目前一次一組受控驗證與來源封套規則；未封存、未經審查的候選不能當成可執行驗收來源。產品目前優先事項不換算為 6M Month N，工程 Gate 順序見 [ROADMAP_6M_ENGINEERING](ROADMAP_6M_ENGINEERING.md)。

文件進度已保存於本機checkpoint `62bf0c9d`，沒有push或產品來源變更。P01 matrix-only新入口 `c159293a` 與新protected reviewer已經Root完整原文正逆與獨立靜態審查；Root05 DATA收據 `62ee965f` 實際通過，Root另核6,992 pins及編譯產物，outer `f93248f0` 自然閉鎖。隨後唯一原五cold＋一warm矩陣收據 `f62576aa` 自然native0／driver0，原篩選p95為385.9978ms，仍未達300ms門檻；outer `ded854be` 三終態PID陣列空、handles關閉、mutex釋放。Root已完成完整來源／資源讀回1702；獨立核驗a6cae2bb已重算全部90份DTO及三類p95，Root另核7,115 pins／7,207 SHA checks，outer46c7db88自然閉合，不採入或授完整Gate；封套0db8 intent已消耗，不原樣重跑。

暫停checkpoint當時，P08 已取得六組指定候選的限定 PASS：Paper reader10、Paper widget16、catalogue13、Historical reader7、Historical widget16、Historical Research Lab wiring13；各組均另經 Root 全量來源／收據讀回，不能加總成包級接受。當時Root04雙卡接線、canonical測試與文件預覽仍是私有候選；本輪正式工作樹接入與共同QA狀態依上方目前摘要及本輪QA，原私有候選／較早FAIL均保留。

最新來源觀測綁定暫停前 `a04c3ba95d61696982a1c67d87921f3d595c4628`：full3089、active3088＋archive support1；saved-DATA `a0a89fa7`、Root全量讀回 `a3e8ed8e` 已完成6206 SHA checks，八個historical unknown與原capture native2仍保留。最後 Python outer `a3820c91` native0、三組PID陣列空、handles關閉、mutex釋放。本次文件 checkpoint commit 會形成新 HEAD；恢復時先核新 Git lineage、來源／index／未提交變更，不能直接執行仍綁舊 HEAD 的 controller。Paper metrics仍None、來源UNVERIFIED／NOT_QUALIFIED；正常Main／fresh、真來源、完整期間指標、同版EXE與完整P08／產品Gate仍待。詳細候選pins、Root06 mock11的有限界線、控制助手原FAIL與下一步見[暫停 checkpoint](../06_qa/BALDR_COMPLETION_CHECKPOINT_20261014.md)。

## 產品與系統入口

- **產品方向與來源優先序**：[PRODUCT_ROADMAP_POST_REFACTOR](PRODUCT_ROADMAP_POST_REFACTOR.md)。產品 Gate 定義產品能力與接受證據，不是完成狀態。
- **目前架構**：[system_architecture](../01_architecture/system_architecture.md)及[目前架構分冊](../01_architecture/current/README.md)。
- **目標架構設計**：[FINAL_TARGET_ARCHITECTURE](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 是目標實作設計唯一權威，不作 current 完成證明。
- **UI**：主程式為 `ui_qt/main.py`，共有九個頂層工作區；Daily Decision Desk 位於「市場探索 > 市場總覽」。完整操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。
- **正式資料路徑**：由 `data_module/config.py` 的 `TWStockConfig` 管理；`DATA_ROOT` 預設 `D:/Min/Python/Project/FA_Data`，SQLite 主要檔為 `<DATA_ROOT>/sqlite/twstock.db`。不得依 repo 相對目錄推定正式資料位置。

## 重要限制

- 不覆寫或刪除正式 raw data；所有來源候選、PIT、時間戳與 gate 原門檻照原收據判讀。
- 金融核心使用 Decimal 或整數單位；策略、回測、Recommendation、Portfolio 與 Exit 實作須先做 look-ahead 自查。
- Historical replay、readiness、dry-run、shadow、paper 與局部 UI／後端 PASS 不代表 forward／live evidence 或產品接受。
- Investment Advice 不授權 broker execution、自動平倉或自動策略升降級。

歷史快照與逐輪驗收原文已由文件治理封存在 [documentation_productization_20261012/originals](../09_archive/documentation_productization_20261012/originals/)；封存版本只供追溯，不能覆蓋本頁或最新具名 QA 收據。
