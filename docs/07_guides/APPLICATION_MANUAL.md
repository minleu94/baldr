# baldr 完整操作手冊

目前可試用的日常研究修正版為 `ec5c95733608`：從 `output/trial/Baldr-Daily-Research-66/Launch-Baldr.cmd` 啟動，先看同目錄 `TRIAL_GUIDE.md` 與 `KNOWN_ISSUES.md`。它使用獨立空白狀態與截至 2026-09-23 的四股價庫；原技術封存需留在已核驗的本機絕對路徑。已限定驗證價格選股、比較、收藏／回訪、兩筆隔離持倉及兩個原 `1.0.0` 單股策略的保存／重開；其他同包程式能力不因打包而取得 Native／EXE 或完整產品資格。固定身份及證據見同目錄 `DELIVERY_RECEIPT.json`，原試用包保持原樣。

後續source分支已接「W底頸線突破（研究）」1.0.0的正常單股執行、當次訊號保存與歷史重開。等待列數不是持有期限，谷日不是確認日；訊號意圖與成交／完成配對分開判讀，研究版不能正式晉升。參數、保存前改設定、實際期間與排錯見[W底指南](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#w底頸線突破研究後續開發分支)。固定0f644faa預覽尚未包含此增量。

後續source分支新增「布林基礎突破（研究）」1.0.0，可從原策略回測清單執行、保存逐日訊號，再沿歷史／原規則及結果重開。確認日數不是分數門檻，訊號不代表成交，研究資格不由SOP單項授予；暖機、支持設定與排錯見[布林基礎指南](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#布林基礎突破研究後續開發分支)。固定0f644faa預覽未含此增量。

後續source分支可在「策略回測」結果區展開「已保存策略版本（版本聲明／來源研究）」，刷新、翻頁並明選版本，再查看原執行規則或開原研究結果。保存生命週期版與來源執行版可能不同，畫面分開顯示，不重新執行或授予升級資格；空清單／來源缺件、返回及保存失敗排錯見[保存版本與來源研究](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#已保存策略版本與來源研究後續開發分支)。此Increment60／61尚未加入固定`0f644faa0d48`預覽，現有試用入口保持。

試用回報修正另有固定`0f644faa0d48`預覽，請使用`output/trial/Baldr-Feedback-Preview-59/Launch-Baldr.cmd`，同目錄`TRIAL_GUIDE.md`列步驟、版本及已知問題。它已含價格研究三步引導、任意順序代碼修正、持倉表前移及兩個既有策略的保存規則來源；是包含第二階段增量的獨立預覽，原4b530四流程窄版仍保留。新入口使用獨立空白私人狀態，舊清單／持倉／研究紀錄沒有搬入；原四股資料截至2026/09/23，大盤截至10/14，缺漲跌方向仍未提供。正常Native／EXE與重開的限定範圍見[交付指南](PORTABLE_WINDOWS.md#試用回報修正預覽increment59)。

後續開發分支的固定50ddb640包已限定驗證兩條Windows原生自動化流程：TPEx固定法人批次／用途的讀回與返回，以及合成Paper配置研究的登錄／Registry重開／個股返回。來源版與EXE各以新程序重開，接受界線與使用限制見[可攜候選指南](PORTABLE_WINDOWS.md#後續開發候選的限定驗證)。日常四流程試用仍使用4b530的原啟動檔，不需等待第二階段或改用開發包。

後續開發分支可在固定法人頁明選「用途接受檔／SHA」，把指定TPEx來源的diagnostics契約與每日批次分別核驗；不需每日重建接受，也不放行P0整桶／歷史／評分或交易。首次保存、移機重開與拒絕原因見[用途接受指南](manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人用途接受與重開後續開發分支)。固定V1候選不變。

後續開發分支的「數據更新 → 三大法人 → 固定法人批次」可明選TPEx OpenAPI單日版本，核市場、原報告日與九項原始整數股數；與TWSE批次共用雙SHA及成功保存小時守衛，未到可用小時仍拒讀。取得範圍、重開與缺件判讀見[TPEx法人單日指南](manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人openapi單日版本後續開發分支)。固定四流程試用包不變。

後續開發分支的配置研究可在明確保存後按「登錄研究紀錄」，再從「策略回測 → 研究 Registry → 配置研究紀錄（非回測績效）」按同帳種、portfolio_id 與登錄引用精確重開，接回原個股與返回流程。保存、登錄與回測績效分開；缺全帳現金或來源仍不可用。步驟、重試及排錯見[登錄研究指南](manuals/WATCHLIST_AND_PORTFOLIO.md#登錄研究紀錄與跨頁重開)。固定四流程試用版不增加此功能。

最新四流程試用版為PF窄版修補 `4b530a7e`，啟動 `output/trial/Baldr-V1-PF/Launch-Baldr.cmd`，同目錄有 `TRIAL_GUIDE.md`／`KNOWN_ISSUES.md`。它修正下述舊9fa的PF錯誤，沒有加入第二階段功能；沿用原四股資料，新研究輸出／私人狀態另存，舊包與舊結果不搬移。原生自動化已重驗受影響V1-04，其他未改流程沿原證據；不是全Gate或真人接受。

獲利因子的有限比率／未定義狀態與舊保存值判讀見[PF指南](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#獲利因子的可用性與舊結果)。source候選已修正；固定9fa試用EXE的附加PF仍可能把無虧損金額當比率，待V1-04窄版修補，請勿把該欄當有效比率。

本手冊提供日常使用順序及常見操作入口。安裝看[快速開始](QUICK_START.md)，既有 owner 搬機看[機器啟動 Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md)，排程核對看[全排程唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。

後續開發分支的「持倉管理 → 顯示進階 → 配置研究封存」已增加首次策略帳研究：以明示 checkpoint 及同來源 Health v2 選來源、輸入股票、比較後保存，再接回原個股與精確重開流程。先用 `run_strategy_position_health.py` 沿原評估器另存同源 Health；缺件維持不可用，不改交易或自啟排程。參數、操作、時鐘與排錯見[配置研究指南](manuals/WATCHLIST_AND_PORTFOLIO.md#配置研究封存與另存假設)。固定 `9fa4518c` 試用包仍保留四條凍結流程。

人類授權重跑 Forward／Decision 時，可在原 Python producer 參數加 `--reservation-wait-seconds 5`，限定本次共用鎖等待；允許整數1..10500，排程預設仍10500秒。這個參數不跳過鎖、截止、資料日期、cohort 或正式 DB 寫入確認。逾時視為 blocked、沒有新證據，保留該次 receipt 再判讀重試條件；具名操作、重跑結果與未解除資格見[10/13排程修復報告](../06_qa/BALDR_SCHEDULE_REPORT_REPAIR_20261013.md)。

baldr 是市場資料、個股研究、推薦回放、回測和持倉檢視工具。畫面輸出是研究資訊，不是券商委託或投資保證；目前沒有自動券商交易。Advice、Paper、模型投影、單次回測與排程狀態都不能單獨當成真實交易或自然成熟證據。

## 1. 日常使用旅程

### 1.1 開始前

1. 以你已完成設定的 source GUI 或 portable GUI 開啟 baldr。首次使用先依[首次安裝 Prompt](FIRST_INSTALL_PROMPT.md)、[安裝指南](INSTALL_GUIDE.md)或[可攜版指南](PORTABLE_WINDOWS.md)完成自己的環境設定。
2. 在「數據更新」檢查資料根、行情資料日期、來源狀態、缺件與 warnings。`current`、`expected_wait`、`stale`、`partial`、`failed`、`unknown` 和有效空結果不能互換。
3. 選一項任務：更新資料、查看市場、建立研究候選、讀個股／持倉，或回看已保存結果。先確認本輪決策日、資料日、來源及 scope。
4. 完成後記下 result/run ID、狀態和 warnings。若保存或讀回失敗，保留原錯誤與身份，不手動修改 hash、日期或 artifact。

### 1.2 四種常見情境

| 我想做什麼 | 從哪裡開始 | 主要核對 | 詳細操作 |
|---|---|---|---|
| 更新與檢查行情 | 「數據更新」 | `DATA_ROOT`、來源日、quality、warnings、更新後涵蓋 | [資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md) |
| 查看市場、產業與個股 | 「市場探索」或「個股研究」 | 決策日、行情資料日、來源、coverage、缺件 | [資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md) |
| 研究推薦候選、保存結果或回測 | 「推薦分析」或「Research Lab」 | eligible universe、Profile／策略版本、成本、成交假設、run ID | [推薦與 Research Lab](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md) |
| 管理候選清單或檢視持倉 | 「候選池」、「觀察清單」或「Portfolio」 | 選定來源／帳本、資料日期、身份、寫入範圍 | [觀察清單與持倉](manuals/WATCHLIST_AND_PORTFOLIO.md) |

### 1.3 入口及共通狀態

主要工作區包括 Decision Workbench、Market Explorer、Recommendation、Backtest、Watchlist、Stock Research、Portfolio、Data Update 和 Runtime。不同入口可能讀不同的資料根、來源版本或帳本；以畫面明示的日期、來源、帳戶及狀態為準，不按股票代號或最新檔名猜配。

- `missing` 表示來源或欄位缺失；`unknown` 表示目前無法確認；`degraded`／`partial` 表示結果有可用部分但不完整；`failed` 表示工作失敗；`skipped` 表示本輪條件未執行；0 筆可能是有效空結果，也可能是來源問題，須看 warnings 和查詢狀態。
- `fallback` 是降級結果，不能當作本輪正常產出。Regime、分數、候選排序及 Advice 不是勝率或交易指令。
- 取消工作會停止新工作並等待安全收尾；等待期間畫面可能仍顯示上一個完整結果。確認狀態和本輪 ID 後再決定是否重試。
- UI 刷新只會依該頁契約讀取資料；它不會自動修復行情、重跑策略或啟用排程。

## 2. 數據更新與市場探索

更新前先確認 `DATA_ROOT` 和 `OUTPUT_ROOT` 各自指向預期位置，再檢查來源日期、quality 和 warnings。快速更新適用近期日常補檔，並增量同步 SQLite；安全更新會依選定範圍重建每日合併檔後同步 SQLite。快速更新不等於全量 CSV 重建。

更新完成後再次查狀態，確認同一根目錄、日期涵蓋及 SQLite 狀態。若是部分完成或失敗，保存錯誤、範圍和已完成階段再判斷重試。不要把缺資料填成零、改時間或手動刪除資料庫／WAL／SHM。市場總覽先讀決策日、行情資料日、來源和 warnings，再判斷 Regime、強弱、產業或主力流向。

詳細步驟、參數、狀態解讀與資料修復安全界線見[資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md)。

新來源每日快照的官方時間／成功批次小時、固定版本重開、缺前期與失敗批次判讀，見[每日快照時間判讀](manuals/DATA_AND_MARKET_RESEARCH.md#每日快照的時間判讀)。正式更新與排程是否已接入仍以具名 QA 為準。

正常Main可在既有設定成對明示固定月營收binding路徑及外部SHA；配置／市場／版本不符時拒絕，不轉用latest。步驟與限制見[固定月營收快照配置](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#選擇已接受範圍的固定月營收快照)。目前有合成Main／新程序輸入讀回，完整推薦、官方來源與EXE仍按QA判讀。

如需保存並重開原 F17 月營收研究，正常 Main 已設定固定每日 binding 時，在原研究頁使用封存來源（`use_archived_sources=True`），再按「選擇研究保存資料夾」。此資料夾須與正式 `DATA_ROOT`／`OUTPUT_ROOT`、F17／來源 provider 根及 operation 暫存根分開；原 F17 入口與 operation 設定照常保留。保存後可從 Watchlist 的「個股分析」沿原收藏重開，不會另查最新版本。這段操作已有以下限定合成證據：storage 27 PASS／1 預期保護性 SKIP、封存收藏 9 PASS、Watchlist 5 PASS；archived UI 漂移重開1 PASS（44.49秒），正常 Main 父54640→fresh32420保存1128／頁1與 Watchlist typed 精確重開通過；父關閉後私有 DB/raw、舊snapshot/reference及mutable pointer漂移，26固定來源及原320 F17資產仍核對一致。詳見[封存 F17 來源保存與重開](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#f17-封存來源保存與精確重開2026-10-14)及[封存月營收收藏](manuals/WATCHLIST_AND_PORTFOLIO.md#封存月營收研究收藏2026-10-14)。

## 3. 推薦、回測、候選與持倉

建立推薦前核對資料日、母體、Profile、門檻及已啟用指標；結果先看 result ID、決策日、資料日、quality、warnings、Why／Why Not 和 screening matrix。保存後只沿同一 result ID 讀回。Research Lab 需確認日期、股票母體、策略版本、成本、滑價、成交假設與 benchmark；最佳化結果是候選，仍需 OOS 或 Walk-forward 等證據。

Research Lab 的 Paper 保存快照查找需先由管理員在啟動環境明示設定外部保存根 `PAPER_CONTRACT_ARTIFACTS_ROOT`。未設定或設定無效時，Paper 查找會停用，其他 Research Lab 功能仍可使用。版本 ID 須與目前 Research Lab 所選策略版本一致；查找時還要明示策略、帳戶命名空間與含時區的截止時間，按「列出此帳戶的保存快照」查看最多 200 列的清單及截斷提示，再選取一列並按「讀取所選 exact 快照」。不會自動選最新版本或快照，也不會建立或修改保存資料；候選清單本身不代表 exact 讀回已驗證，即使所選快照讀回成功，也不代表來源可得性或績效資格已核定。關閉工作區會取消未完成查找，已開始的讀取會安全收尾，過期結果不會取代目前畫面。

候選池、Universe、手動交易帳、聲明持倉與 Paper 帳用途不同。保存候選清單或匯入帳本前，核對目前選定資料、預覽、hash 和寫入範圍。所有帳本都不會自動連券商或送委託。詳見[推薦與 Research Lab](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md)及[觀察清單與持倉](manuals/WATCHLIST_AND_PORTFOLIO.md)。

在 Paper 區回看已保存健康評估時，先明確選取 receipt／snapshot，再開啟並核對來源與持倉身份；返回或正常關閉後可沿保存偏好重開同一評估。步驟、分開的時鐘、WATCH／未知與讀取失敗處理見[已保存健康評估與回訪](manuals/WATCHLIST_AND_PORTFOLIO.md#已保存健康評估與回訪)。

後續開發分支的「持倉管理 → 顯示進階 → 配置研究封存」可明選帳本及完整封存，讀回原現金／股數／三情境，調整明示 target 並另存研究假設；返回與重開沿原 hash。另存後可進個股的「持倉／Health／Exit」核對同一原帳戶的現金、NAV、股數、估值、Health 與 targets；未保存的比較預覽須先另存，來源不符不取當前手動帳代替。它使用舊證據及原時點，不代表今日帳本，缺初始來源時不造範例。步驟、bp 參數、政策版本與空庫排錯見[配置研究封存與另存假設](manuals/WATCHLIST_AND_PORTFOLIO.md#配置研究封存與另存假設)。固定 `9fa4518c` 試用包不變。

Research Lab 的「研究 Registry」新增兩筆推薦回放的完整期間診斷：先保存本輪結果，再選原 run；輸入既有日曆原件、保存收據 SHA-256 與市場後，恰選兩筆推薦回放並按「比較完整期間」。預期／實際／缺日與資格阻擋分列；「返回所選 run」保留選取。後續開發分支另可分頁查看兩run各自保存的逐日現金／持倉估值／權益與原提供的損益；缺日與缺欄位保持無觀測／未提供，資格阻擋不變。此增量尚未納入固定9fa試用包。步驟與重開、取消及限制見[Registry 雙 run 完整期間診斷](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#registry-雙-run-完整期間診斷)。

日曆來源也可明選「每日批次」，填指定批次目錄、manifest 與成功收據兩份 SHA；畫面須先有兩市場獨立用途接受紀錄，缺件時會停用比較。目前正式 Main 尚未配置真接受紀錄；合成 QA 的保存讀回不代表此缺口已解除。不要自行用批次內容建立接受紀錄，或以新版本替較早決策補造歷史可得時間。

同一表單可沿已配置的兩市場接受紀錄讀年度來源批次；年度與月別的接受紀錄、批次與收據須整組一致，混搭會拒絕。這不新增可手填授權的欄位；年度正常控制器與Main／新程序已用隔離合成錨點驗證，真接受與正式配置仍待。

進階日曆用途配置由資料owner提供已核接受檔與獨立SHA，以`CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH`／`CALENDAR_DAILY_ACCEPTANCE_BINDING_SHA256`成對設定後重開程式。Main固定本視窗接受，原表單再指定批次；讀取失敗顯示「來源用途接受設定無法讀取」，不影響其他工作區。正常Main／新程序已驗合成年度binding；真接受與正式資料配置仍未授予，詳[Registry步驟](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#registry-雙-run-完整期間診斷)。

新的next-open保存亦保留本輪提交的成本與lot、實際採用值；未填成本與明示0分開記錄。重開沿已保存值，較早run不會由目前設定補值；缺來源、幣別或成本權威仍不可作績效排名。損毀或超限附件會拒讀，保留錯誤與run ID交owner處理。

上述年度binding與Registry重開／比較／返回旅程，已在固定`675bea26`來源與候選EXE完成同版合成Main／新程序驗證。既有交付包未被替換；真人Native、真來源及完整績效仍依各自證據判讀，見[具名候選QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment31固定來源候選exe與registry同版旅程)。

## 4. 數據更新

舊連結入口保留；目前更新流程與狀態判讀集中在[資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md#檢查與更新資料)。

### 4.2 快速更新與安全更新

<a id="42-快速更新與安全更新"></a>

快速更新適用近期日常補檔；安全更新重建所選範圍的合併檔。兩者的前置條件、資料日核對與取消處理見[更新步驟](manuals/DATA_AND_MARKET_RESEARCH.md#檢查與更新資料)。

### 4.6 市場資料完整性修復（受控 CLI）

<a id="46-市場資料完整性修復受控-cli"></a>

資料修復／availability mapping 有 preview、備份與明確 apply gate，僅由具授權的 owner 依[每日資料更新指南](../03_data/daily_data_update_guide.md)執行。一般使用者不要手動補檔、改 receipt、覆寫 SQLite 或把月營收／財報候選當成已發布資料。

## 6.7 官方市場與技術條件研究

<a id="67-官方市場與技術條件研究"></a>

舊錨點保留；入口、來源核驗和條件設定見[官方市場與技術條件研究](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#67-官方市場與技術條件研究)。新增[官方條件與價格研究](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)把獨立價格範圍作為四組條件後的共通AND，提供全域排序、跨頁比較及指定來源收藏；候選驗證依本輪QA。來源 coverage 不完整、`current_only` 或 available time unknown 時，結果只供當下研究，不能提升為歷史 PIT 證據。

## 8. 每日決策（Daily Decision Desk）

<a id="8-每日決策-daily-decision-desk"></a>

Daily Decision Desk 是已保存來源的唯讀摘要入口。先確認資料日、來源、quality、warnings 和持倉 scope，再讀待判讀項目。空佇列不代表風險為零或 Gate 通過；重新整理不會重跑資料更新或策略。操作見[資料與市場研究](manuals/DATA_AND_MARKET_RESEARCH.md#市場探索)及[觀察清單與持倉](manuals/WATCHLIST_AND_PORTFOLIO.md#持倉管理)。

## 11. 系統狀態與決策擷取終態

以下適用後續開發來源版；固定四流程 V1 與 50ddb 開發 EXE 尚未包含此顯示。先確認目前設定的輸出位置，再由左側「系統維護 → 系統狀態」查看日常排程清單，選「決策證據擷取」並展開「詳細」。不需填新參數，也不會從此頁啟動或重試工作。

詳細區列出同次 run ID、決策日、完成時間、收據 SHA 與核驗結果；下方的 snapshot 狀態、已保存、安全原因碼、最後及未完成階段用於定位阻礙。切換到觀察清單再返回，仍可查看所選工作；重開程式會重新核對目前保存的同次終態。畫面沿原被動輪詢更新，剛完成的工作可能需等下一輪讀取。

| 顯示 | 判讀與處理 |
|---|---|
| 已驗證（verified） | 同 run 收據與原件一致。仍要看該次 passed／failed／degraded、日期及 freshness；已核原件不等於工作成功、來源接受或自然成熟。 |
| 未完成／尚無狀態／未驗證 | latest 尚未 finalize、缺收據／原件、hash／路徑不符或讀取中變動。保留 run ID、SHA 及診斷碼交 owner 查核，不手改檔案、不自行重跑正式工作。孤立 passed 不算已核成功。 |
| timeout／已保存：未知 | 子程序逾時，無法由這份終態判定是否已寫入。不要直接再次保存；由 owner 核對原收據及保存 DB 後才決定下一步。 |
| 最後／未完成階段 | 指向原有階段事件，可協助定位等待處；空白不代表所有階段都完成。整數耗時與例外類型是診斷，不是效能或資料完整性驗收。 |

此頁只顯示安全摘要，原 stderr／例外訊息留在原件。它不會補資料、改 Task、啟用 maintainer 或提升 Paper／Forward 資格。正式排程的自然執行仍依[日常核對與自然 run 驗收](SCHEDULE_OPERATIONS_AND_MIGRATION.md#日常核對與自然-run-驗收)逐項判讀。

## 12. 常見問題

<a id="12-常見問題"></a>

| 狀況 | 先確認 |
|---|---|
| 沒有資料或日期過舊 | 畫面使用的 `DATA_ROOT`、SQLite 路徑、來源日、coverage 和 status；不要沿用別人的 root。 |
| 顯示 0 筆 | 區分有效空結果、來源缺失、查詢失敗和被條件篩除；看狀態列及 warnings。 |
| 更新部分成功或失敗 | 保存日期範圍、錯誤、已完成階段；確認來源、資料庫鎖與磁碟空間，再依失敗階段處理。 |
| 推薦或回測看起來很強 | 核對母體、決策日、資料日、成本、成交假設、驗證期間及 run ID；單次高報酬不是自然或實盤證據。 |
| 保存／讀回不一致 | 保留 result/run ID 和錯誤；不要手工改 hash、複製 artifact 或按最新檔名代替原來源。 |
| Task Ready 或 exit 0 | 這只表示局部排程狀態，不代表產物與 consumer readback 已通過；按[排程唯讀稽核](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)核對同一 run。 |

排程排錯時先核 exact run／日期／root／hash，再核是否達到成功條件。Evidence 的 `scheduled_recommendation_status_not_passed:blocked` 表示推薦身分可辨但整體狀態未通過，pipeline仍不啟動；真正身分錯誤另列identity mismatch。日曆 `refreshed` 要讀同次刷新後終態，不能借刷新前inspection。Paper官方NULL open只允許原來源、原執行日內的有界retry；跨日仍保留missed session，不能用後日價格補成交。ML Forward shared-lock preflight尚未啟動時沒有maturity cutoff，但parent仍失敗；G9/H20終態核驗失敗或逾時不能當自然累積成功。操作與具名驗收見[雙報告修正QA](../06_qa/BALDR_SCHEDULE_REPORT_REPAIR_20261013.md)及[排程運維](SCHEDULE_OPERATIONS_AND_MIGRATION.md)。

<details>
<summary>舊手冊書籤與日期化工程補充（按需展開）</summary>

## 舊手冊錨點與日期化工程補充

下列舊章節連結保留，全文已封存；日常操作以本手冊及主題分冊為準。

### 頁面的 i 說明按鈕

<a id="頁面的-i-說明按鈕"></a>

原手冊記錄過在頁面標題旁開啟該頁操作說明的入口，內容涵蓋操作順序、欄位／單位、結果判讀與缺件處理。這是舊版手冊描述，不保證每個現行工作區都有相同按鈕；請以目前畫面及對應操作章節為準。[原始章節](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md#頁面的-i-說明按鈕)

### 2026-10-03 週度研究採集與讀回

<a id="2026-10-03-週度研究採集與讀回"></a>

此日期的 parent／child 收據讀回與各 child 狀態是歷史紀錄；`verified` 不代表來源資格，`formal_credit=false`，也不建立公告可得時間或 historical PIT。完整原文與數值見[原始章節](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md#2026-10-03-週度研究採集與讀回)；目前排程操作依[唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)，目前狀態依 Snapshot 與具名 QA。

### 2026-07-13 系統工程整合判讀

<a id="2026-07-13-系統工程整合判讀"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-04 保存來源當下研究與持倉日期

<a id="2026-10-04-保存來源當下研究與持倉日期"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX04／05 每日研究條件與同源個股

<a id="2026-10-05-ux0405-每日研究條件與同源個股"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX13／18 具名研究母體盤勢與指標排序

<a id="2026-10-05-ux1318-具名研究母體盤勢與指標排序"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX16 唯讀研究來源契約

<a id="2026-10-05-ux16-唯讀研究來源契約"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX18 共用日特徵與個股觀察

<a id="2026-10-05-ux18-共用日特徵與個股觀察"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-05 UX19 隔離研究快照生產與讀回

<a id="2026-10-05-ux19-隔離研究快照生產與讀回"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-06 UX21 保存母體 H5／H10／H20 研究結果

<a id="2026-10-06-ux21-保存母體-h5h10h20-研究結果"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-07 施工版完整保存母體瀏覽

<a id="2026-10-07-施工版完整保存母體瀏覽"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-07 真人回饋摘要收藏與推薦失敗

<a id="2026-10-07-真人回饋摘要收藏與推薦失敗"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 2026-10-07 dev 修正 H20 摘要獨立於一般個股報告

<a id="2026-10-07-dev-修正h20-摘要獨立於一般個股報告"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 991E 已保存推薦的個人決定與旅程回看（2026-09-28）

<a id="991e-已保存推薦的個人決定與旅程回看2026-09-28"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 991F 個人模型評估摘要讀回唯讀

<a id="991f-個人模型評估摘要讀回唯讀"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

### 991H H20 Gross 每日收據與 BBANDS 上軌保存版別（2026-10-06）

<a id="991h-h20-gross-每日收據與-bbands-上軌保存版別2026-10-06"></a>

全文見[原手冊封存版本](../09_archive/documentation_productization_20261012/originals/docs/07_guides/APPLICATION_MANUAL.md)。

</details>

### 可試用第一版V1的固定範圍（2026-10-15 UTC）

每日研究頁的價格研究在窄結果區使用直式欄位；向下捲動可找到「套用條件」、比較與收藏。調整視窗寬度會保留輸入、規則選擇與原查詢，不會自動換來源或重新套用。

一般股票回訪沿「觀察清單」→「新增股票」，輸入有效代號，名稱留空可由既有來源補入。新增即保存到目前試用清單；選取後「查看選中個股研究報告」→「返回來源清單」，關閉並從同入口重啟後仍可回訪。完全未連結保存來源的手動列只讀目前既有行情，不冒充原推薦版本；已連結／衝突或來源缺損仍沿原來源守衛處理。研究收藏另沿原查詢與固定版本重開。細節見[觀察清單與持倉](manuals/WATCHLIST_AND_PORTFOLIO.md)。

原補完計畫§0.3已凍結市場／個股技術研究、價格技術條件與版本收藏、觀察清單回訪、單股策略回測與歷史讀回四條旅程。試用候選與專用啟動入口以交付清冊為準，不直接雙擊舊dist/baldr冒充新版本。

四股隔離試用資料為2317、2330、2382、2454既有真實保存行情的明示子集，期間2014/01/02至2026/09/23，不能當作當日行情或全市場。其他基本面、籌碼、TPEx、日曆雙市績效、模型、Paper與交易未納入第一版；缺件維持不可用。原始發布／available-at與企業行動／價格還原未核，不能宣稱歷史PIT或可用於績效排名。價格研究選定完整保存來源、按「嚴格核驗並載入」再套用條件後，逐股「加入比較籃」，兩欄以上才可「重驗並比較」；只有一欄時收藏停用，清空或加入第二欄後恢復適用狀態。收藏保存原查詢與版本，可由觀察清單重新開啟。

僅使用交付專用隔離設定；不要把試用輸出、清單或結果搬回正式資料根。第一版固定來源`9fa4518c2aca87beaddef75a2b29165722da6a6c`，請雙擊本機`output/trial/Baldr-V1/Launch-Baldr.cmd`；同目錄TRIAL_GUIDE.md及DELIVERY_RECEIPT.json列SHA、來源、四旅程及已知問題。回測窄視窗保存後先按「收合左側設定」，再勾「研究歷史查找」→「查找既有歷史」→選定run→「開啟原結果」，重開程式後沿同路徑讀回。歷史讀回不重跑或重新保存結果。大盤副本截至2026/10/14，四股截至2026/09/23，勿當成同日行情。640px Native操作已驗，1440px個股命中失敗已定位其他程序視窗遮蔽，操作前先將Baldr切到前景；真人、其他主機與完整Gate尚未接受。
Increment33已以最小重複清理狀態修復正常關閉後的StartupView失效wrapper錯誤；新固定505候選從無參數cmd真入口開窗PID2000，再合作式WM_CLOSE最終程序exit0，沒有強制清除。入口與原試用狀態根不變；資料、金融、Reader與四旅程程式未變，沿用Increment32具名證據。舊4cf候選、原交付與退出碼1 FAIL原件保留在owner snapshot；本機清冊更新為505，沒有替換dist/baldr或active_delivery。


Increment36已修單股next-open未成交日漏收盤估值／取消及預存MACD重用別名。Increment37將交易次數明示為已完成進出場配對；零配對顯示「尚無已完成交易」，即時結果另列實際成交筆數與期末持股，缺欄位為「未提供」，不由空配對表推論零成交。歷史頁只使用原保存欄位。缺分數／門檻不推論原因；期末權益含未平倉估值，不等於已實現損益或正式績效。舊run不改寫；第一版主要驗收為正常固定門檻研究，互相矛盾的分位數診斷未全面驗證。

後續開發分支 Increment40 修正策略回測、規則卡、Walk-forward 與參數掃描的版本識別：新實驗沿登記版本，暴衝／穩健策略保存為 `1.0.0`，缺明確版本即顯示「策略版本不可用」並停止本次請求。正常保存→歷史重開→返回與新程序重開已限定驗證；即時結果可另存，歷史結果不可重新保存。舊 run 不改版本；固定 `9fa4518c` 試用包不含此修正。入口、參數、判讀與排錯見[回測操作指南](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#選模式和研究範圍)。

後續 Increment57使穩健／暴衝策略的固定門檻、next_open 新保存結果也能從歷史清單按「查看保存規則」，讀回當次實際規則與成本；原結果、切頁返回與新程序保持同 run。設定改動不改舊保存，來源不一致時拒絕並列原因；這不是策略有效性或完整績效接受。固定試用 EXE 尚未包含，完整步驟與舊風控單位限制沿上方指南。

9fa試用回報的價格研究來源選取，先按「查詢版本」才有批次可選；一份批次內含四股，載入後再按代碼篩選，詳[價格研究逐步操作](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)。後續候選增加三步引導與持倉表前移，操作／缺方向的漲跌解釋見[個股與持倉指南](manuals/WATCHLIST_AND_PORTFOLIO.md#個股研究報告)；現有固定EXE不會自動更新。回測摘要的已完成配對、實際成交與期末持股須看同一run，SOP樣本不足或未做Walk-forward不代表回測沒有執行。

日常研究修正版 `ec5c95733608` 把「推薦分析 → 每日研究條件 → 價格選股」放在預設子頁：查詢版本、明選一批、嚴格載入，再設股票／收盤價條件與套用；來源日、母體與處理數在首屏，SHA 細節可展開。從結果進個股或比較，返回仍對原來源及條件；保存研究收藏後由觀察清單回訪。每日快照、每日母體與技術母體有各自子頁，不將來源混用。單股回測摘要分列同 run 完成配對、實際成交、明細列數與期末持股；歷史缺成交或持股資料時明示未提供。詳[價格研究及回測逐步操作](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)與試用資料夾內 `TRIAL_GUIDE.md`；使用者先前六配對的原 run 尚未取得，不能以本輪兩個測試 run 重判其 SOP／Baseline 結果。舊 `0f644faa0d48` 不自動取得本輪變更。

後續 Increment41／42 為原法人維運入口增加明選「僅TWSE法人」、成功批次小時封存，並在「數據更新 → 三大法人」提供固定批次唯讀區。明選目錄、manifest／receipt雙SHA與代碼後，可看原保存的逐日整數股數及時鐘；輸入變動／失敗會清除舊結果，取消等待worker安全返回。範圍、CLI、開啟步驟、報表筆數及缺件判讀見[資料指南](manuals/DATA_AND_MARKET_RESEARCH.md#單獨保存-twse-法人候選)。仍為未接受用途的候選，缺資料不補零，不授法人連買／歷史PIT；固定9fa試用包未包含此增量。

Increment43補入原件單位與官方宣告合計守衛；舊候選缺此證據時不能新開每日版本，不手改原件補認。真T86單日已保存並核品質，仍須到台北成功批次可用小時才可讀；用途／授權、連買與歷史資格分開處理，具體錯誤及時鐘判讀見上方資料指南。

Increment45已在實際可用小時後，限定驗過真T86同批次的正常法人頁、切頁返回與新程序讀回；再次查看沿同一目錄與雙SHA，不必重新抓取或seal。這是後續開發分支的候選事實檢視，固定試用包不變，授權與歷史資格仍未接受。

Increment46 修復後續開發分支的 TWSE 處置英文原件讀取及終止公文的事件類型接線。從「推薦分析 → 官方市場／處置研究」明選保存版本、選股讀明細、返回，再於新程序明選同版；舊來源不改寫，新來源仍依原觀測日判讀，缺件維持未知。操作、版本與排錯見[資料指南](manuals/DATA_AND_MARKET_RESEARCH.md#官方處置原件重讀後續開發分支)。此輪真名錄／處置配合明示合成行情驗證，固定9fa不變，沒有完整市場／歷史資格提升。

後續開發分支另接「個股研究報告 → TWSE 官方注意公告」，按明選版本與台北可用小時讀原公告，與處置措施／研究摘要理由分開。準備來源、三值設定、重開、日期與空列判讀、錯誤隔離見[單日注意公告指南](manuals/DATA_AND_MARKET_RESEARCH.md#單日官方注意公告後續開發分支)。固定第一版與四條試用旅程不變。

後續開發版的新單股回測保存結果可在「研究歷史查找 → 查看歷史卡」閱讀有版本的原指標，真零配對與不可用勝率／平均分開；舊未版本化 run 保留原限制。實際期間、單位、保存／重開／返回與排錯見[歷史指標指南](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#新單股保存結果的歷史指標後續開發分支)。此出口不授完整策略績效、來源或精度資格。
