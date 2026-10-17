# baldr 機器啟動與完整移機 Runbook

本 Runbook 用於第一次建置新環境，或 owner 將既有 baldr 環境移到新電腦。所有資料根、私人資產、runtime 與排程都需逐項確認。安裝 GUI、plan 無 error 或 Task 已建立都不代表排程已自然成功執行。

先選擇[首次安裝 Prompt](FIRST_INSTALL_PROMPT.md)中的 `fresh` 或 `owner-migration` 模式，依 repository 的[`baldr-bootstrap.v1 manifest 範例`](../../examples/machine_bootstrap_manifest.example.json)與[JSON Schema](../../examples/machine_bootstrap_manifest.schema.json)準備不含秘密的盤點資料。`scripts/document_control.py bootstrap-plan` 只唯讀檢查並把 plan JSON 輸出至 stdout，不會自動設定 root、複製資產、註冊或啟用排程。它與本機 `output/tasks/` task 狀態是分開的記錄，不可宣稱 bootstrap-plan 會建立該記錄。

## 範圍與安全界線

Prompt 的 plan-only、configure、restore-and-enable 是整體任務授權，與唯讀計畫工具分開。已授權 configure／restore-and-enable 時，完成具體清冊核對後持續完成該範圍的環境、設定、停用註冊或原狀啟用；不逐Task重複確認。資產與writer前提未成立者留pending，需要新範圍才另確認。

- GUI runtime 可選 `source` 或 `portable-gui`，但 Task Scheduler 使用的 canonical wrapper/action 是獨立設定；不得因 GUI 換成 portable 就默默把 CMD／Python action 換成 EXE。
- `DATA_ROOT` 與 `OUTPUT_ROOT` 必須分開確認。私人 `PERSONAL_*`／Paper 根、研究 registry／model root 依 owner 的既有契約盤點，不用 `OUTPUT_ROOT` 猜測或代替。
- 搬移前先準備舊機資產清冊、設定備份、資料根識別與允許搬移的內容；對排程保存 task name、XML、action、arguments、working directory、trigger、principal、timezone 與 enabled 狀態。清冊可記錄 hash，但不要包含密碼、token 或 DPAPI 私鑰。
- 不複製 venv、`.env` secrets、credential vault、broker credential、Codex `auth.json`／session database 或其他 authentication 檔。新機需以本機可信流程重新建立授權。
- 模型不只是一個權重檔：需要核對 model lineage、source/account、feature／資料版本、cutoff、pins、manifest/hash 和使用資格。材料不齊列為 pending，不可僅按檔名啟用。
- 在舊機 writer 確認停用前，不得在新機啟用相同正式 writer。兩邊同時寫入可產生重複、互相覆蓋或來源身份混淆。

## 保存研究的新副本（來源工具）

若只要把已保存回測放到新的`OUTPUT_ROOT`，可使用來源工具`scripts/copy_research_output.py`。它處理研究Registry、舊單股回測與舊推薦組合三個store；不複製行情、價格選股來源、一般推薦、收藏、Paper帳或模型，亦不自動啟用新設定。這是完整移機中的一個步驟，原完整清冊仍須逐項處理。

Increment129 另提供明示選項 `--include-recommendations`，納入同一來源根 `recommendation/runs` 的已保存一般推薦，包括 legacy 與 canonical execution；不加此選項仍維持上段三個 store。依相同授權與全新目的根執行，例如：

```powershell
.\.venv\Scripts\python.exe scripts/copy_research_output.py --source-output-root 'C:\BaldrResearch\old-output' --destination-output-root 'C:\BaldrResearch\copied-output' --include-recommendations
```

一般推薦只重綁新索引的 `data_path`，原 JSON、排名、數值、未知欄位與 canonical artifact／metadata 不重寫；新收據列 `selected_store_kinds`。原 query 在來源與副本核對整批身分，外部路徑、錯 ID、journal、trigger、破損 artifact 或原根漂移會拒絕。canonical 的外部 ML 收據尚無完整搬移契約，會在 query 讀該收據與建立目的根前具名拒絕；不偷偷略過已選結果。若只搬回測，沿原命令建立另一全新目的根，不選一般推薦。

owner 核准新 `OUTPUT_ROOT` 後，到「推薦分析」按「讀取可用來源」，選原完整結果 ID，再按「讀取」；返回及重啟仍讀原保存值，不重算推薦或更新日期。固定109原推薦的新副本已由既存125 EXE正常Main／fresh限定驗證，原根I/O與網路0；125未打入此來源工具，也未自動更改試用設定。這不補舊推薦缺行情或授歷史PIT，詳[129 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment129-recommendation-output-copy)。

1. 先取得owner對來源與**全新目的根**的精確授權，關閉使用該來源的保存程序。來源仍有SQLite journal／WAL、未完成staging、非標準trigger／view或配置情境外部帳本引用時，工具會拒絕，不省略那些內容。Agent驗證仍須使用受控Job，不可在正式根試跑。
2. 以下為人工操作範例，須換成已授權的實際路徑；目的根必須不存在，不得位於正式資料或私人根內，也不得與來源重疊：

   ```powershell
   .\.venv\Scripts\python.exe scripts/copy_research_output.py --source-output-root 'C:\BaldrResearch\old-output' --destination-output-root 'C:\BaldrResearch\copied-output'
   ```

3. 工具沿原public reader逐run驗來源，逐bytes複製原檔，只在新SQLite副本重綁已知的結果檔路徑；原Parquet／JSON、金融metadata、來源manifest與sidecar不重新序列化。原件不改，原、新索引及選取context的不同SHA會記在新根`RESEARCH_COPY_RECEIPT.json`，不能混稱同一位元原件。
4. 必須看到`copied_and_public_readers_verified`收據，且沒有`.research_copy_pending.json`或`RESEARCH_COPY_FAILURE.json`，才把此步列為完成。超限、取消或來源／新副本讀中修訂都不能當成功；失敗副本保留供核對，不直接重跑覆寫。預設每檔256MiB、全來源4GiB、100,000檔／目錄項與10,000runs，是明示資源預算，超限會整批拒絕，不截短來源。
5. owner另行核准設定時，再讓GUI使用新`OUTPUT_ROOT`，保留原`DATA_ROOT`及其他已核根，從「策略回測 → 找已保存結果」明選原run、查原規則／結果、返回，關閉後重開。不重新回測或按目前策略重建保存值；舊根可保留作還原。這個複製命令不改Task、maintainer、模型、私人帳或正式writer。

來源正常Main與既存125 EXE已限定驗新根讀回及fresh，原根I/O與重算為0；125 EXE本身未打入這個新來源工具，執行複製須使用對應來源環境。完整行情／technical v4／一般推薦外部ML依賴／收藏／私人帳、其他主機與全環境移機仍待，詳[Increment126 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment126-research-output-copy)。

## 技術來源的新副本與封存恢復（來源工具）

已限定驗明選1,951檔來源的完整匯出、整包移位恢復、公開查詢，以及既存125 EXE從新根開同源個股、比較、保存收藏與新程序重開；原600秒期限及舊FAIL保留。價格消費程式自125未改，Source Main本輪不重跑。這個來源工具不自動改125入口、既存收藏或整個環境；下列命令仍須明選來源及全新目的根。

執行修正只讓獨立檔案I/O最多兩件同時進行，待完成佇列亦最多兩件；新增原件buffer最多為`2 × max-file-bytes`，整體仍另受Root的8GiB Job限制。原fsync、不可覆寫、每檔讀前後檢查、完整來源／目的SHA及清冊重驗保留。預算與取消由呼叫端串行判斷，成功、取消或失敗返回前均等待本次自有寫入結束；這項修正的單元通過不能取代下列全量與正常UI出口。

價格選股的technical v4來源含snapshot、batch manifest、parent及universe定位鏈。只搬資料夾或改`TECHNICAL_UNIVERSE_READ_ROOT`不足以恢復；原收據仍綁舊絕對路徑。來源工具`scripts/copy_technical_source.py`可為**明選的完整來源**建立新定位鏈，或從已移位的完整封存包恢復；不抓取、不重算指標，也不修改原快照或原收據。

1. 取得owner對具名來源及全新目的根的精確授權，停止該來源writer。先保存六欄JSON pin：`store_output_root`、`generation_identity_sha256`、`plan_identity_sha256`、`plan_sha256`、`receipt_identity_sha256`、`receipt_sha256`，另在外部固定這份pin檔的SHA-256。來源必須經原strict reader完整驗證；partial、pending或缺件不會略過。
2. 下列為人工範例，路徑與SHA須換成已核內容；目的根必須不存在，不能與來源重疊或位於正式／私人根內。Agent執行仍須遵守Root受控Job及資源規則。

   ```powershell
   .\.venv\Scripts\python.exe scripts/copy_technical_source.py --source-pin 'C:\BaldrResearch\v4-source-pin.json' --source-sha256 '<已核pin檔SHA-256>' --destination-root 'C:\BaldrResearch\technical-copy'
   ```

3. 成功出口為新根的`TECHNICAL_COPY_RECEIPT.json`，status須為`copied_and_strict_readers_verified`，且沒有`.technical_copy_pending.json`或`TECHNICAL_COPY_FAILURE.json`。外部保存此收據SHA及完整副本；不要只搬`live/universe`。`live/repositories`保留原snapshot／manifest bytes，`live/parents`與`live/universe`是新定位鏈，`original`保留原plan／receipt與前次封存歷史。原、新receipt SHA不同，不能冒充同一原件。
4. 封存包移到另一位置後，使用外部已核的**原複製收據SHA**恢復至另一個不存在的目的根：

   ```powershell
   .\.venv\Scripts\python.exe scripts/copy_technical_source.py --archive-directory 'D:\BaldrArchive\technical-copy' --source-sha256 '<外部保存的複製收據SHA-256>' --destination-root 'D:\BaldrResearch\technical-restored'
   ```

   恢復先核整包清冊、每檔bytes／SHA與外部收據，再以封存內的明示映射重綁另一份定位鏈；不沿舊URI找原根補件。少檔、多檔、連結替換、錯SHA、超限或取消都拒絕。預設每檔256MiB、全來源4GiB、100,000檔／目錄項、391個parent分段；超限不截短來源。失敗副本保留，不以同路徑覆寫重試。
5. 新strict reader通過後，owner另行核准配置時才指定新收據`copied_pin.store_output_root`（`<目的根>/live/universe`）。從價格選股明選來源，核宣告／處理／排除及unknown，開同源個股、比較、保存收藏並在新程序重開。既有收藏仍綁原來源，不自動改簽；私人收藏搬移須另列清冊。

新parent的`observed_at`是副本組裝時間；原snapshot的來源時間、首次可得性、缺值與用途資格保持，不能把複製時間當官方發布或歷史PIT證據。此來源工具未打入固定125 EXE；執行複製須用對應來源環境，既有EXE僅沿原reader消費已驗證的新定位鏈。它不自動改launcher、設定、正式資料、私人帳、Task或maintainer，也不代表整包試用版／跨主機移機完成。具名證據見[Increment127 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment127-technical-source-copy)。

## 明選價格研究收藏的新副本（來源工具）

價格研究收藏的來源路徑參與身分hash，不能手改原JSON換根。先沿上一節完成技術來源複製／封存恢復，保留外部固定的 `TECHNICAL_COPY_RECEIPT.json` SHA；其目前目錄必須與已恢復的 `live/universe` 定位相符。再使用同一來源工具模組的 `scripts/copy_price_bookmarks.py`，明選原legacy JSON清單、其SHA與收藏ID，建立**另一全新輸出根**：

```powershell
.\.venv\Scripts\python.exe scripts/copy_price_bookmarks.py --source-watchlist 'C:\BaldrResearch\old-output\watchlist\default.json' --source-watchlist-sha256 '<原清單SHA256>' --technical-copy-directory 'C:\BaldrResearch\restored-technical' --technical-copy-receipt-sha256 '<完整複製收據SHA256>' --bookmark-id '<原價格收藏ID>' --destination-output-root 'C:\BaldrResearch\copied-bookmarks'
```

`--bookmark-id`可重複指定；本工具目前只接受F07價格研究收藏，不是整個私人帳或所有收藏家族搬移。只選的收藏會進入新 `watchlist/default.json`，原清單全份bytes留在 `original/source_watchlist.json`，未選項目只在該原件保留。條件、價格上下限及精度、未知政策、排序、頁碼、捲動與比較籃保持；新來源定位產生新query／收藏ID，`BOOKMARK_COPY_RECEIPT.json`記錄原→新ID及封存內收據鏈，不冒稱原ID未變。

必須看到 `derived_bookmarks_and_source_verified`，並確認沒有 `.bookmark_copy_pending.json`／`BOOKMARK_COPY_FAILURE.json` 才能使用新清單。原件／收據SHA、來源鏈、價格、stock身份或來源時鐘不合，以及保存中修訂、取消、超限或新ID碰撞都不授成功；失敗副本保留，不覆寫重跑。預設單檔256MiB、完整輸出（含必要收據與pending）總4GiB、100,000項、391個明選收藏／沿革節點，另受Root Job限制。先恢復已移位來源，不使用舊根fallback；缺失的中間複製沿革需補具名原件，不能自行改簽。

owner核准新設定後，讓GUI使用新 `OUTPUT_ROOT` 與同一已核 `TECHNICAL_UNIVERSE_READ_ROOT`，到「觀察清單」選新收藏，雙擊回原條件與比較，再開同源個股及返回；重啟仍從同一新清單重開。工具不改啟動器、正式行情、私人store、Task或maintainer，也不授來源用途／歷史PIT。驗證及尚未涵蓋的範圍見[130 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment130-price-bookmark-copy)。
## Fresh：全新環境

1. **選環境與根目錄**：決定 `source` 或 `portable-gui`、repository／portable 位置、Windows 帳戶和資料磁碟。依[快速開始](QUICK_START.md)、[安裝指南](INSTALL_GUIDE.md)或[可攜版指南](PORTABLE_WINDOWS.md)建立新機環境。
2. **建立空的 owner 根**：明確指定可寫且有備份策略的 `DATA_ROOT` 與 `OUTPUT_ROOT`。確認兩者不是 repository、venv 或對方的共享私人目錄。fresh 模式不匯入舊 Paper ledger、持倉或模型；需匯入時改走 owner-migration 並列出來源。
3. **核對時鐘**：確認 Windows 時區、日期、時間同步和 DST 狀態。台北顯示時間應由新機設定解析，不以舊機的本地字串替代 UTC instant。
4. **盤點必要資產**：用 manifest `assets[]` 記錄 id、絕對 path、required 與可選 SHA-256。只清點 owner 已核准的資料和模型檔；不要把未驗證資料複製到正式根。
5. **列出排程期望**：每列含 id、platform、明確的 `desired_enabled`、timezone 和 `trigger`；Windows schedule 還要核 canonical wrapper，依平台填 argv、working directory、notification、model／effort 或 target thread。Fresh 預設先保持 writer 關閉，直到新機帳戶與來源都核對完成、且獲得啟用範圍授權。
6. **建立並查看唯讀計畫**：依工具介面呼叫 `scripts/document_control.py bootstrap-plan --manifest <私有清冊路徑>`，並確認 `repo_root` 完全等於實際 repository root。輸出含 errors、actions、`mutations=[]` 和 `natural_run=not_verified`；它不安裝 runtime、不搬資料、不註冊 Task。另唯讀確認 `output/tasks/` 中本任務既有 task 狀態與實際位置；修正錯誤／pending 後重新產生 plan。
7. **完成 GUI 基本讀取**：先確認程式呈現的實際 roots、資料日期、status 和 warnings。安裝完成只證明環境／路徑已設定；若資料尚未授權或缺件，保持明確的 empty／pending 狀態。
8. **依整體 scope 完成設定**：plan-only 在具體清冊交付；已授權 configure／restore-and-enable 時，逐項保存 before 定義，完成環境與目的地設定，再以現行 PS1／專用註冊流程建立停用 task。aggregate 未涵蓋的任務另依專用入口處理，不能只跑一次 aggregate 就結案。舊 `.cmd` registrar 的 Direct lane trigger 與現行定義不同，不作移機入口，詳見[排程指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)。
9. **讀回並依原狀啟用**：configure 保持停用；restore-and-enable 僅在帳戶、來源、上游與 writer 前提皆成立後啟用核准清冊內原已啟用項目。每項核 action／argv／cwd／trigger／principal／enabled／NextRun，保存 before／after。已授權的精確範圍內持續完成，不逐 Task 重問；scope 外差異另確認。自然 run 與下游接受仍需依下方分階段驗收留下真實證據。

## Owner-migration：接手舊環境

### A. 舊機盤點與停止寫入

正規化格式看[盤點範例](../../examples/machine_bootstrap_inventory.example.json)及[Schema](../../examples/machine_bootstrap_inventory.schema.json)。範例只示範一列，不能當完整清冊；`raw_exports` 保存原匯出 path／SHA，逐項核實 XML／Codex 定義與正規化結果。唯讀計畫工具只核正規化檔案 hash，沒有解析原 XML 或代替這項來源審查。

1. 指定 owner、舊機、新機和本次移交日期；列出舊機 repository／runtime、所有 roots、私人 Paper／持倉、Model registry／lineage、輸出及保留期限。
2. 匯出或備份舊機清冊、重要設定與 Task 定義 XML，另外記錄 Codex heartbeat 的 prompt、目標、時區、週期及 enabled 狀態。保留原匯出來源和 SHA，將適用排程正規化為 `baldr-machine-inventory.v1`；manifest `source_inventory` 填清冊 path／SHA-256。備份文件需移除密碼、token 和 credential material。
3. 盤點 21 個 Windows tasks 和兩個 Codex heartbeat；用既有唯讀方式記錄實際 action、argv、working directory、trigger／offset、principal、enabled、LastRun／LastResult 與 NextRun。查詢權限不足記 unknown，不猜成 missing 或 disabled。清冊需涵蓋適用 Windows task 與 Codex 排程的狀態、通知、timezone、model／effort 和 heartbeat target；缺項不能由新機預設補猜。
4. 先暫停舊機所有要移交的 writer；留下停止時間和可核對證據。唯讀 heartbeat、唯讀稽核及使用者 GUI 需依 owner 的來源寫入契約判斷是否屬 writer。`old_machine_writer_stopped` 是布林欄位；為 false 或缺少停止證據時都停止移機啟用階段，不把未知硬填 true。
5. 保留舊機可回滾材料與本機資料，不先刪除舊根或重建資料庫。備份成功不等於資料可直接搬入新機。

### B. 新機設定與資產核驗

1. 先選 `source` 或 `portable-gui`，安裝到新機自己的路徑；依[安裝指南](INSTALL_GUIDE.md)或[可攜版指南](PORTABLE_WINDOWS.md)設定 runtime。`source_scheduler_runtime_verified` 只在具名核對新機 Windows 排程實際使用的 Python/source runtime 與 wrapper 後才設 true；portable GUI 啟動成功不能代替這項驗證。正式排程的 wrapper 仍依既有契約逐項核對。
2. 在 manifest 中重新填入新機 `repo_root`、`runtime`、timezone、`DATA_ROOT`／`OUTPUT_ROOT`。舊機絕對路徑只作 inventory，不可直接複用成新機有效路徑。
3. owner 確認每一項 asset 可移交後，逐項比對來源、目的、大小／hash、容量、檔案系統和 ACL。Paper／個人資料、模型 pin 和 lineage 不齊時明列 pending；不要複製 authentication 或重建 SQLite 來迴避缺件。
4. `nativecred`／DPAPI 相關 authority 是機器／帳戶綁定。舊機 credential 不會因檔案複製而在新機有效；經 owner 批准後，使用該資產的可信註冊流程重新建立，確認有效身份再解除 pending。
5. 設定 OS 時區、時鐘同步和帳戶登入方式，確認程式實際解析的 `DATA_ROOT`、`OUTPUT_ROOT`、個人根與 model root。設定完成後先做唯讀健康檢查，不觸發正式寫入任務。

### C. 排程 desired-versus-observed 與差異處理

Manifest 欄位按[JSON Schema](../../examples/machine_bootstrap_manifest.schema.json)：schedule 每列必須有 id、platform、`desired_enabled`、timezone 和 `trigger`；Windows schedule 還需 canonical wrapper，並按平台列 argv、working directory、notification、model／effort 或 target thread。owner-migration 必須涵蓋目前 Windows catalog 中所有任務；不移交者以 `excluded_schedules[]` 的 id、platform、reason 明確排除，不能默默漏掉。Codex cron／heartbeat 也需逐項列出或具名排除。

1. 將舊清冊的「預期」當作 desired schedule，將新機唯讀查到的定義寫入 `observed_schedules[]`。逐項比較 id、platform、action／canonical wrapper、argv、working directory、timezone、trigger、principal、enabled、notification、model／effort／target thread；不要用名字相似代表一致。
2. 保留完整 diff：缺少、額外、重複、action／參數變更、執行帳戶不同及權限 unknown 都分列。清理 duplicate 前先確認它不是其他 owner 的工作；維持既存不明 identity 為 pending。
3. 重跑 `bootstrap-plan` 僅作唯讀更新計畫並記錄變化。純 plan 可以重複檢查；計畫列出的 create／difference actions 是審查建議，不是 writer 操作或冪等性保證。schedule writer 的冪等性必須由實際註冊器按 task identity 查證，不可由 manifest 或 plan 推斷。
4. 對每項需建立、更新、停用或移除的 task，列出 before／after XML/action、所屬 owner、影響和回滾方式，形成一份完整、具體的變更清冊。使用者未授權此清冊前只交付 plan；若使用者已授權完整設定／註冊／啟用範圍，毋須逐 task 重複詢問。
5. 在已授權清冊範圍內連續執行，按核准順序一次切換一個 writer/lane；確認舊機 writer 停止，每一步後讀回實際 task XML／NextRun。若讀回超出清冊或出現高風險新差異，停止相關範圍並個別確認。

## 時區、offset 與 cutoff

大部分 Windows tasks 使用 `Pacific Standard Time` 本地時間，會隨 DST 改變；Paper Portfolio 與 ML forward 兩個 offset 任務都在台北 08:25（UTC 00:25）喚醒。其換算為 PDT 前一日 17:25／PST 前一日 16:25。這只是時區換算，不是季節 Task QA 或自然執行證據。兩個任務內部再等真實台北 08:30；Paper 有 08:30 guard，ML forward 有 08:30 cutoff 與 08:35 deadline。

移機時核對 Task XML 的 offset、trigger 與新機所見的實際 UTC／本地 `NextRun`，並分別確認 Paper 08:25 喚醒與 08:30 guard、ML forward 08:30 cutoff 與 08:35 deadline。Windows 本地時鐘時間、觸發 offset 和產品 cutoff 是不同欄位；DST 切換前後都需以新機讀回值核驗。具體 21 task 表及兩個 Codex heartbeat 時區見[排程運維與搬機指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)。

## 分階段驗收：設定完成不等於自然 run

| 階段 | 可以宣稱的範圍 | 仍不能宣稱 |
|---|---|---|
| Manifest／plan | 欄位和已盤點設定經唯讀檢查；差異有列出 | 資料已搬移、Task 已註冊或產物已寫出 |
| Roots／資產設定 | owner 核准的路徑可解析；指定資產 hash／身份核對完成 | credentials 有效、模型已具資格或來源完整 |
| 排程讀回 | task identity、action、trigger、principal、enabled 和 NextRun 符合核准設定 | Task 已自然執行成功、下游 consumer 已讀回 |
| 首次自然 run | 同一 task/run/date 有 terminal 結果與預期產物，可沿 run ID／hash 讀回 | 其他日期、季節、帳戶、模型或所有 lanes 均已驗收 |
| 下游使用 | 指定 consumer 對同一 run/date/hash 完成讀回，status／warnings 符合 lane 契約 | 實盤績效、投資建議有效性或其他平台驗收 |

自然 run 驗收需等待排程按時鐘發生，而不是手動 run 或用 Task Ready、`LastResult=0`、檔案存在、輸出 mtime 或 status receipt 替代。保留同一次 execution identity、actual UTC/local 時間、terminal exit、輸出 hash／日期及 downstream readback。限制見[排程唯讀稽核 Runbook](BALDR_SCHEDULED_AUDIT_RUNBOOK.md)。

## 回滾

發現錯誤時先停止新機剛啟用的 writer，確認舊 writer 仍停用，避免雙寫。保存新舊 task XML、差異、輸出和 error；不要刪除部分產物或覆蓋 DB 來追求表面一致。回滾時依既有備份恢復新機設定／資產指向，逐項撤銷本次已核准的 task 變更，再核對實際 state。只有確認新機 writer 已停止後，owner 才能另行授權恢復舊機 writer；兩機不可同時對相同 lane 寫入。任何無法核對的資料或 DPAPI authority 保持 pending，升級給原 owner 處理。
