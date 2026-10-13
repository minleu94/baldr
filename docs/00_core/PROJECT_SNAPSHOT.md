# PROJECT_SNAPSHOT（目前狀態）

> **更新基線：2026-10-13。** 本頁只記目前可支持的整體狀態；局部 PASS 不相加成完整工作包或產品 Gate。最新恢復收據見 [10/12 補完增量](../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md)，先前紀錄見 [BALDR_COMPLETION_PROGRESS_20261011](../06_qa/BALDR_COMPLETION_PROGRESS_20261011.md)；原始 receipts／source inventory 依各收據所列路徑與 SHA 追溯。

## 現在有哪些入口

baldr 已有九個本機工作區，主程式是 `ui_qt/main.py`。下表說明可以從哪裡開始研究，並非所有來源、候選版本或投資效果均已驗收。

| 你的需求 | 已有產品入口 | 使用時的限制 |
|---|---|---|
| 整理行情、確認資料日期 | 數據更新與資料狀態檢查 | 使用自己的合法來源；缺庫、缺表、日期落後分開判讀 |
| 了解市場與個股 | 市場探索、個股研究 | 原始排名、來源與品質各自保留，unknown 不能當零 |
| 比較候選與策略 | 推薦分析、策略回測／Research Lab | 歷史研究與 Paper 不代表正式投資有效或可交易 |
| 保存名單與檢查持倉 | 觀察清單、持倉管理 | 真帳、聲明持倉、研究 Paper 帳分開，保存重開依精確來源判讀 |
| 找日常重點或排查系統 | 決策工作台、系統狀態 | 顯示與導航不授自動交易、模型 promotion 或資料 writer 權限 |

第一次使用依[快速開始](../07_guides/QUICK_START.md)；換電腦依[首次安裝／移機 Prompt](../07_guides/FIRST_INSTALL_PROMPT.md)。新版完整產品包尚有以下工程驗收事項，已交付舊包與當前候選不能混用資格。

## 目前工程狀態與限制

產品補完範圍仍為 P00–P14、M1–M3、F01–F23、UX01–UX24、G0–G4。使用者明示「繼續」後，已從暫停提交 `54f1e04d` 核對恢復；goal active／本task in_progress，完整產品 Gate 尚未接受。Health／ML 修補提交 `e0d76604` 保留；P01 各版效能候選仍在私有凍結來源中，未正式採入。

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

P08a唯讀帳戶卡片服務 `e478bd18` 與測試 `079766be` 已具體實作並經Root靜態審查，尚未執行產品測試或採入。來源capture `dbb3b5d3` 的3,086來源／副本與Git狀態於該觀測內穩定，但原歷史module守衛因八個null欄位拒絕，實際native2保留；outer `ef29baaa` 已自然閉鎖。新saved-DATA reviewer `5b3f8754` 已經Root全文、14操作完整bytes正逆與獨立Luna審查，實際收據 `fafbd885` 為DATA-only核驗通過；Root另核全部3,086 live＋副本、五outputs與compile，outer `ea98a122` 已自然閉合。八個unknown與原capture FAIL保留。原QA入口69d4因四個控制缺陷拒絕，修正版 `ef714400` 已完成全文、八操作正逆及獨立審查；新BLOCKED資料反例測試 `98187817` 保留原十案例並加強斷言。純DATA收據 `0f02d1d5` 已生成八操作守衛、完整原文逆回及五檔編譯，Root另核22項SHA／size，outer `d3204688` 自然閉合。其後同工作區「釐清待解決問題」進行排程來源修正，使先前current來源封套過期；P08a collect／suite未啟動，須待來源交接後建立新lineage。不能把編譯、live穩定或局部葉片當成正式來源、P08績效或完整Gate。

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
