# 觀察清單、個股研究與持倉

這三個區域共用股票研究入口，但資料用途不同。候選池是研究名單，Universe 是可重用的選股清單，手動帳代表使用者記錄的交易，聲明持倉是研究假設，Paper 是模擬帳本；開啟個股報告本身不會新增交易或持倉。

## 觀察清單與選股清單

- 在「候選池」按「新增股票」輸入有效股票代號；正式股票資料查不到的代號會被拒絕。也可從推薦、強弱股或其他研究入口加入。
- 手動新增且完全未連結保存來源的股票，選取後按「查看選中個股研究報告」，讀取目前既有行情與技術資料；以畫面的資料日期為準，不代表即時行情或固定歷史版本。按「返回來源清單」會定位原代號，重啟後從同一試用清單回訪。
- 已連結推薦或研究收藏的股票仍閱讀其原來源和日期。保存身份衝突、來源缺損或資料不足時，回來源頁核對，不改讀目前行情補成同版結果。手動列與同股其他來源並存時，普通返回按股票代號定位，不宣稱精確列級身份。
- 「保存為選股清單」可把候選池保存為可重用 Universe；「載入到候選池」會讀取已保存清單。批次回測按鈕在候選池為空時停用。
- 「移除選中」只移除目前選列；「清空候選池」會刪除全部候選，無法復原。按之前先確認目前選到的是研究清單而不是持倉或交易帳。
- 若畫面提示舊 JSON 損毀或尚未啟用 SQLite，保留原檔並查看錯誤。明示升級只有在所有清單完成來源核對後才啟用；失敗時維持原來源，不要手工刪 JSON 或資料庫。

候選池中的 score trigger 預設為 6,000 基點（目前 provider 使用 `RSI × 100`，相當於 RSI 60），不是推薦總分或獲利機率。分數新達門檻、分數上升／下降與缺前次分數是不同提醒；下降不等於跌破門檻或應賣出。每次都查看資料日、品質和原推薦理由。

### 私人儲存位置與收藏讀回

「官方條件與價格研究」收藏由來源頁選列後保存；回到候選池選取對應收藏列，按「查看選中個股研究報告」，會沿原保存版本重開條件、價格範圍、排序、頁列及比較籃。股票、來源或收藏身分不符時顯示不可核驗，不開一般最新研究。既有官方市場條件收藏仍沿原頁讀取，兩種收藏不按同股票代碼互換。操作見[官方條件與價格研究](RECOMMENDATION_AND_RESEARCH_LAB.md#官方條件與價格研究)，候選驗證及新程序限制見[本輪QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)。

觀察清單、研究收藏及個人筆記使用設定所指定的私人 store route。若選擇 `PERSONAL` 模式，私人 root 與 mode 必須成對設定；只設其中一項會拒絕讀寫。缺少的 PERSONAL store 會顯示為空，不會偷偷回退到舊清單。尚未設定私人模式時，系統依目前相容路由讀取既有來源；啟動或打開頁面不會複製資料、初始化 store、遷移或切換 writer。

因此，空清單可能表示所選 store 尚無項目，不能立刻推定舊資料已刪除。搬機、切換私人 root 或升級 JSON／SQLite 時，先用[首次安裝／移機流程](../MACHINE_BOOTSTRAP_RUNBOOK.md)核對現行與舊來源、備份和 reader/writer 路由；依受控 preview、備份與驗證流程處理，不手動搬 DB、marker、receipt 或 WAL／SHM，也不要刪舊來源來消除空清單。精確 root/mode、fallback 與 rollback 契約見[資料儲存架構](../../01_architecture/current/data_storage_runtime.md#讀寫與保存契約)。

## 個股研究報告

1. 從候選池、推薦、持倉或研究母體選取股票，按「查看個股研究報告」或「開啟選中個股研究報告」；也可切到左側「個股研究」輸入代號後載入。從來源清單開啟會保留該筆的股票與來源脈絡。
2. 先看首屏身份、查詢日、行情資料日、來源狀態、warnings 與缺件，再依區塊閱讀價格／技術、基本面、籌碼／事件、持倉及既有 Advice。要核對各區塊資料日、可得時間或版本時，展開「進階：來源與各區塊日期」；圖表和精確數值表以同一來源欄位對照。
3. 「上一檔／下一檔」只在目前來源清單已有的代碼中切換；「返回來源清單」回到原頁，保留可用的篩選與選取。另按「另開最新研究」會建立新的當下研究 context，不會改寫原收藏或保存結果。保存結果沿用原決策日期和來源；未知 available time、PIT 不適用、hash mismatch 或缺少 source identity 時保留未知，不拿今天行情補舊結果。
4. `—` 或 unknown 表示來源沒有可用值，不能當成零。切換到另一檔時先等新報告核驗完成；新股讀取失敗不應拿上一檔內容判讀。重新載入失敗或取消時，依畫面標示區分本次錯誤與上次成功內容；上次內容不表示本次已更新。持倉歷史 alert 只描述當時快照，不代表目前仍有該部位。

個人 H20 的入口、名單狀態和收藏流程見[推薦與 Research Lab 手冊](RECOMMENDATION_AND_RESEARCH_LAB.md#個人-h20-保存研究)。在個股報告中，20 個交易日毛報酬估計和 H5 成本後超額是不同資料。H20 未扣成本，也不代表成熟結果；請核對該筆來源、日期與模型資格。

## 持倉管理

### 選帳本並讀取

在「分帳查看」選手動登錄、聲明持倉研究或 Paper。三者分開保存，不能將一帳資料視為另一帳的交易或驗收證據。先核對選定帳本、估值日期、股數、成本及行情來源；缺價格或日期不匹配時，市值和損益保持 unknown。

### 手動帳

按「手動記錄交易」，填股票、買賣別、價格、股數、交易日期、費用和稅金，可選填策略來源和備註。賣出數量不可超過現有持倉。這是手動記錄，不連券商，也不證明券商已成交。

匯入 CSV 時，先選檔並閱讀逐列預覽、檔案 hash、欄位和錯誤。確認檔案未變且每列有效後才按確認寫入；取消、重複列、缺欄位或檔案在預覽後變更都不應強行套用。這個匯入不送出券商委託。

### 聲明持倉研究

1. 在「聲明持倉研究」展開新增／修訂表單，輸入股票代號、整數股數、十進位聲明成本和聲明日期；備註與研究假設可選填。
2. 按「新增保存」。若同一股票已有 active holding，選該列後按「修訂保存」，不要另建第二個 active identity。
3. 修訂時以目前顯示的 revision 為準；若保存被拒，重新讀取後再編輯。按「封存選取」會停止目前研究，不會刪除舊 revision。
4. 選擇評估日期後按「重新讀取研究」。讀取失敗、取消或來源不完整時，畫面保留上次結果並標示未確認最新。

聲明持倉只寫入研究用 append-only 資料。聲明成本變化、估值變化不包含費稅、滑價或資金流；Advice／condition 缺少同 scope 的前後快照時，動作會顯示「待確認」。不得把價格存在或檔案 mtime 當成持倉有效、來源正式或可交易證據。

持倉研究只讀 `TWStockConfig.daily_price_dir`，未另行指定時使用 `<DATA_ROOT>/daily_price` 中的日價 CSV；不改寫行情原件。畫面應按列核對來源檔、股票、資料日、品質和 available time。檔案 mtime 只表示本機看到該檔的時間，不是官方公告或歷史可得時間。若沒有可核驗的同 scope Advice／condition，或只有一個結果、baseline 與 current 不是兩份獨立保存結果、Profile／版本／score 設定不同，研究動作維持「待確認」；先在技術詳情核對兩個 `result_id`、資料日和來源，不用最新結果或同股同日猜配。

歷史評估日須明確選取，且不能晚於目前台北日；來源資料與 available time 必須落在評估日及 cutoff 內。沒有來源自帶 availability custody、來源品質不合、日期晚於 cutoff、hash／身份不符或持倉已過期時，讀取會降為資料不足／未知。此時保留原因，回到來源核對或重新讀取；不要手改資料日期、檔案 mtime、hash 或 receipt。主表中的「帳面變化」是價格對聲明成本的資訊性差額，不是已實現績效，也不含費稅、滑價或資金流。

聲明持倉的入口目前只支援研究假設，不代表有實際成交 lineage；`可檢視` 不表示持倉安全，`待確認` 不表示已無風險。這條路徑由 `app_module/user_declared_holding_research.py` 和 `ui_qt/widgets/user_declared_holding_research_widget.py` 提供；read model 的日期、來源、身份與資料資格契約見[決策、研究與 Portfolio 架構](../../01_architecture/current/decision_research_portfolio.md)。

### 配置研究封存與另存假設

此入口位於後續開發分支「持倉管理 → 顯示進階 → 配置研究封存」，尚未納入固定 `9fa4518c` 試用包。使用已設定的 PERSONAL 私人 store；LEGACY_READ_ONLY 可讀回但不能另存，未配置時明示停用，不自動搬資料。

1. 在此分頁明確選帳種（手動／聲明研究／Paper），填原 `portfolio_id`，載入已保存情境。這個帳本選擇獨立於頁首的分帳導覽；不會把手動帳資料帶入 Paper。
2. 明選一個封存 hash 後開啟，核對帳種、帳本、snapshot、原資料日、決策時鐘、精確現金／NAV、完整股數與標記價格。每次最多列出 25 份；開啟會核原 canonical 內容及 hash，不會選 latest 或讀今日行情。
3. 比較「維持／候選等權／明示 target」的原配置、差額、風控後股數、金額、成本和原因。未知欄位保持未提供；投影股數是研究結果，不是成交。金額沿原 Decimal 文字，bp 不用來反推現金。
4. 若要研究另一個 target，只能改原候選及完整持倉範圍內的整數 bp，含現金總和必須是 10000。按比較後沿原現金、股數、Health、行情、cutoff 和既有配置政策重算；原政策 hash 與現行不同時仍可讀舊結果，但拒絕重算。這是原時點舊證據的假設，不表示目前持倉或新的歷史 PIT 資格。
5. 確認比較後再另存研究假設。原件保留，新內容另存新 hash；更改帳本、封存或 target 後須重新比較。保存中等待完成；讀取或比較可取消，取消不會寫交易或部分研究。關閉時等待背景工作安全收尾。
6. 開啟個股研究後，返回會核原封存 identity，不拿手動帳同股替代。正常關閉後重開程式，再以相同帳種、帳本及保存 hash 明選讀回；不自動選最新結果。

空庫表示沒有這個帳本的完整封存。此增量沒有替缺現金、Health、行情權威或時間證據建立初始情境；不要手工修改 hash／日期、加入示例資料或把缺件填零。損毀／版本不符保留原錯誤及 hash 交 owner 核對。初次帳本來源整合及完整 P06 驗收仍待原計畫後續，其他功能可繼續使用。

### Paper Portfolio

Paper Portfolio 分頁主要唯讀呈現 snapshot、現金、狀態、ledger、成本、benchmark、weekly report、blockers 與 warnings。資料缺少時顯示 partial／not computable，不能把未知成本、缺成交或空快照補成零。

- 「匯入 Paper 成交 CSV」先預覽 hash、筆數和成本；確認填入的是實際模擬成交且欄位完整後，才二次確認 append 到 Paper Trade Ledger。此動作不改手動帳、不改 Paper snapshot，也不送 broker order。
- 「匯出成交範本」建立只有欄名的空白 CSV，預設不覆寫既有檔案。
- 「預覽／建立 Equal Weight」先唯讀檢查基準、snapshot 日期、固定成分與每個決策日的 T-1 價格；只有預覽通過且再次確認後才建立新的研究用 benchmark ledger。這不等於填入 Paper fills 或實盤績效。
- 「計算最近週報」使用畫面允許範圍內的 snapshot 數量（預設 5 筆，可調 1–31）；不足或成本來源不完整時會明示不能計算，不用缺件補零。

若本機有可讀的 source-backed Health read model，Paper 區另有「Paper 持倉健康／退出候選（獨立 Paper identity，唯讀）」區塊。選取一列閱讀研究建議、評估原因、需要確認、日期與來源；可能顯示 `HOLD`、`REDUCE_CANDIDATE`、`EXIT_CANDIDATE` 或 `WATCH`。`WATCH`／未知、沒有 receipt 或 stale 表示這次不能採用 action，先依提示讀取來源診斷。這個區塊只讀 Health projection，不會執行 evaluator 或產生新的 Health receipt；刷新 Portfolio 也不是 Health producer。

Paper Health 只按 Paper 的完整持倉身份及原 receipt 核對。人工帳或聲明持倉與 Paper 即使股票代碼相同，也不是同一筆持倉；不要把 Paper action 顯示到人工帳上。整體 Health 正式整合和工作包驗收仍以[目前狀態快照](../../00_core/PROJECT_SNAPSHOT.md)為準；舊日期 QA、Task exit code 或單一存在的 status 檔都不能證明目前 read model 可用或自然成熟。

### 已保存健康評估與回訪

在 Paper 區的「已保存健康評估」按「載入已保存評估」，明確選一份日期、snapshot 與 receipt，再按「開啟所選評估」。清單第一份不會自動成為選擇；此入口目前只支援沒有額外 namespace 的 `paper-main`。

開啟後閱讀狀態與持倉列；點選一列會保存該筆 position identity。返回持倉管理，或正常關閉程式後重新開啟，會依保存的 receipt 與 snapshot 回訪原評估。保存的是回訪偏好，不會新增持倉、成交或健康評估；相同股票代號也不會替代原持倉身份。

「展開來源與驗證細節」分別列出保存結果可讀時間、Health 觀測、來源觀測與可得時間。缺來源、stale、blocked、hash／身份不符，或原評估無法安全讀回時，保留未知並顯示讀取失敗，不自動套用最新結果。未知／WATCH 不表示可續抱或應賣出；先按原來源與原因核對。

載入與回訪只讀已保存的 result、receipt 及同 route 的 exact Paper snapshot，另寫保存選擇偏好。這些操作不執行 Health producer、evaluator、交易或更新行情。取消、切換評估或關閉視窗時，未完成或晚到結果不會覆蓋新選擇；重新選取前須等前一讀取收尾。完整工作包與來源資格依[Snapshot](../../00_core/PROJECT_SNAPSHOT.md)及具名 QA 判讀。

Paper 排程狀態或 readiness 不是成交記錄。Windows Task 啟動、Task exit 0、status 檔案存在與同次 ledger／consumer readback 是不同證據；核對排程請看[全排程唯讀稽核 Runbook](../BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。

遇到 producer／consumer 問題時，分別讀 producer 的 run status、來源／receipt 與 Paper UI 的 exact consumer readback。Producer 成功或排程回傳 0 只證明該層完成；若 UI 沒讀到同一 snapshot／ledger／identity，仍須保留 missing／partial／unknown 並交由 owner 查 Runbook。不要從 UI 刷新推定 producer 已重新執行，也不要由舊 consumer 結果推定本日來源已更新。

## 共通判讀與排錯

- 同一股票可以有多個來源和日期；只按 exact result ID、decision date、資料日、來源與 selected account 讀回，不按股號猜配。
- 未知價格、缺少 Advice、過期資料、future date、來源不符或身份 conflict 時停止採用該列，保留 diagnostic 並確認原來源。
- 手動帳估值／損益與 Paper 成本後表現分開；批次回測、推薦回放和 Paper ledger 也不能互相替代。
- 畫面刷新只讀取已保存來源時，不會重跑策略、修復資料或啟用排程。遇到寫入或資料轉換操作，先查看本輪範圍、備份、確認按鈕和回滾方式。

其他帳本 schema、受控 migration、Paper producer 與跨機設定依[機器啟動 Runbook](../MACHINE_BOOTSTRAP_RUNBOOK.md)、[排程運維與搬機指南](../SCHEDULE_OPERATIONS_AND_MIGRATION.md)及[目前資料儲存架構](../../01_architecture/current/data_storage_runtime.md)處理。Immutable ML retention 目前只有唯讀 metadata inventory，沒有 destructive runbook；一般使用者不得自行刪除模型 artifact。細節見[架構中的保留與核准邊界](../../01_architecture/current/data_storage_runtime.md#immutable-ml-retention-的目前檢視與核准邊界)，不要把歷史 Supplements 當成現行命令。

### 每日月營收研究收藏（2026-10-14）

已設定每日快照接受時，原月營收研究頁保存 V2 收藏。觀察清單仍用「個股分析」重開原研究，保留原 F17、月營收完整 cohort、條件、頁碼與選股；重開不是新的今日推薦。需提供原版本參照保存資料夾及固定來源接受，缺檔、錯 hash、來源不符或失敗批次會拒絕重開並保留原收藏。月營收小時可用性不授整體官方資料或歷史 PIT 資格；合成限定 QA 不等於真來源與完整產品驗收。

### 封存月營收研究收藏（2026-10-14）

正常 Main 設定固定每日 binding 後，原 F17／月營收研究頁可使用封存來源（`use_archived_sources=True`）。按「選擇研究保存資料夾」選定此次研究位置；它與正式 `DATA_ROOT`／`OUTPUT_ROOT`、F17／來源 provider 根及 operation 暫存根分開。完成查詢後，在候選池選取該封存收藏並按「個股分析」，沿原收藏重開指定股票與原研究，不會另選最新版本。

收藏保留完整來源 pin、原條件、頁碼、選股，以及四個外部核對值：原月營收參照與描述（Ref3／Desc3）、封存資料與封存描述（Archive2／V4）。新修正另存新版本，舊收藏不覆寫。若原資料庫、原始來源檔、舊快照或原參照附件已漂移，封存副本可供精確重開；仍須保留可重驗的封存資料／封存包、全部每日市場根、固定來源信任及 binding。缺檔、錯 SHA、未來截止時間、缺市場、股票代碼別名衝突、reparse／連結或與正式來源根重疊時，原畫面會保留具名拒絕原因，不改用最新來源。取消可能留下空的或未完成的自有資料夾，不會自動清除或授予資格。舊 V1／V2 收藏仍走原嚴格即時來源路徑，不自動退回封存模式。

目前限定驗證：storage 27 PASS／1 預期保護性 SKIP、封存收藏 9 PASS、Watchlist 5 PASS；archived UI 漂移重開1 PASS（44.49秒），正常 Main 父54640→fresh32420保存1128／頁1與 Watchlist typed 精確重開通過；父關閉後私有 DB/raw、舊snapshot/reference及mutable pointer漂移，26固定來源及原320 F17資產仍核對一致。這些限定結果不代表官方來源接受、完整歷史 PIT 或完整官方覆蓋。
