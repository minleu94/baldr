# baldr Windows 可攜版

可攜版供不安裝 Python 的 Windows 使用者啟動桌面 UI。使用與下載時一併提供的完整 `baldr` 資料夾，內含 `baldr.exe` 與 `_internal`；不要只複製 exe。版本、commit 與候選／發布狀態須看該份交付隨附的 metadata 和驗收收據，本指南不指定目前最新 exe。

## 已保存研究更換輸出根

來源工具已可為研究Registry、舊單股回測與舊推薦組合建立新副本，只重綁新索引的結果檔路徑，原金融檔不重寫。操作、預算、授權與失敗隔離見[Runbook](MACHINE_BOOTSTRAP_RUNBOOK.md#保存研究的新副本來源工具)。來源Main及既存125 EXE已驗新根原規則／結果、返回及新程序；125沒有打入這個新來源工具，不應直接以舊EXE呼叫該腳本。

technical v4另有[完整來源複製與封存恢復](MACHINE_BOOTSTRAP_RUNBOOK.md#技術來源的新副本與封存恢復來源工具)，逐bytes保留原snapshot／manifest與原plan／receipt，另建新定位鏈。明選1,951檔的匯出、移位恢復、公開查詢及既存125 EXE正常Main／比較／收藏／fresh已限定驗證，原600秒FAIL保留。恢復須使用外部固定收據SHA，不能只改根或手改原JSON；既存收藏仍綁原來源，不自動改簽。

這兩項來源工具不使整個試用包變成可攜。行情、一般推薦與既存收藏的來源映射、私人帳及其他主機仍依完整清冊；不只換launcher冒稱完成移機。目前本機試用入口統一看[目前指定試用版](TRIAL_VERSION_GUIDE.md)，下方日期化候選留作歷史。

## 首次設定

1. 將完整資料夾放在你有寫入權限的位置，保留來源包的所有檔案。
2. 若是新使用者，先建立自己專用且位於程式包外的行情與輸出目錄；不要複製別人的 DB、私人持倉或模型。
3. 可在 `%LOCALAPPDATA%\baldr\config.json` 指定兩個絕對路徑，或用 `BALDR_CONFIG` 指定另一份 JSON。設定檔欄位範例如下：

   ```json
   {
     "DATA_ROOT": "D:/My Baldr/market",
     "OUTPUT_ROOT": "D:/My Baldr/results"
   }
   ```

   同名環境變數優先於 JSON。程式不自動讀 `.env`。`DATA_ROOT` 與 `OUTPUT_ROOT` 分別設定；只改一個不會連動另一個。
4. 關閉程式後編輯設定，再啟動 `baldr.exe`。到「數據更新」檢查路徑、資料日期和缺件；確認來源授權後再更新。
5. 檢查更新結果中的 status、資料日期與 warnings。`passed_with_warnings` 仍需閱讀警告；missing、unknown、stale 與零筆不可互相代替。

現行 source 版也可從 `ui_qt/main.py` 啟動。source 與 portable GUI 都支援各自的環境設定流程；正式排程有獨立的 wrapper/action 契約，換 GUI 啟動方式不會默默把 Task Scheduler 的 CMD 改成 EXE。排程遷移須依[排程運維與搬機指南](SCHEDULE_OPERATIONS_AND_MIGRATION.md)逐項處理。

<a id="啟動載入畫面與圖示"></a>

## 啟動問題與圖示檢查

開發來源的固定來源ZIP建置已補Windows長路徑I/O邊界：短解壓根附加長member時亦使用extended形式，再逐檔核原bytes；外部commit、canonical路徑、SHA及原封存拒絕守衛不改。這是建置修正，不代表120資料可搬移；其v4分段收據與保存索引仍有絕對路徑綁定，不能只改啟動器或重寫原收據。原P14完整移機／保存搬移及其他主機驗收保持未完成。

載入進度只表示 UI 初始化，不表示行情新鮮度或排程成功。按 Esc／Alt+F4 會在安全階段邊界要求取消；單一同步初始化呼叫仍須先返回，既有 worker 也要合作式收尾。缺少載入背景圖時仍應保留可讀進度；啟動失敗請依該交付包標示的位置查看錯誤與 App log。

可攜版使用 `app_icon.png`，並在建立視窗前設定 `Baldr.TechnicalAnalysis` AppUserModelID，不修改 registry。Windows 釘選或圖示快取可能暫時保留舊圖；先核對交付包本身，不要把快取外觀當成程式版本證據。完整歷史行為說明見[原手冊封存章節](../09_archive/documentation_productization_20261012/originals/docs/07_guides/PORTABLE_WINDOWS.md#啟動載入畫面與圖示)。

進階日曆用途接受亦可在上述config.json或同名環境變數成對指定`CALENDAR_DAILY_ACCEPTANCE_BINDING_PATH`／`CALENDAR_DAILY_ACCEPTANCE_BINDING_SHA256`，配置檔須在程式包、正式資料與輸出之外。缺設定時保持停用；來源owner先核官方用途，外部SHA只固定該接受檔。此接點已有source及固定`675bea26`候選EXE的合成Main／fresh同版證據；真雙市場接受與正式配置仍未成立。詳[Registry手冊](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#registry-雙-run-完整期間診斷)與[具名候選QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment31固定來源候選exe與registry同版旅程)。

## 個人資料與模型

新使用者先保持私人資料和模型設定未啟用。既有使用者只能沿用已驗證的資料來源與身份：`PERSONAL_DATA_ROOT` 與 `PERSONAL_WATCHLIST_SOURCE`、`PERSONAL_JOURNAL_ROOT` 與 `PERSONAL_JOURNAL_MODE`、`PERSONAL_STORE_ROOT` 與 `PERSONAL_STORE_MODE` 要按其原契約成對設定。模型 policy 與 H20 activation 是不同設定空間，指定路徑不會自動訓練或啟用模型。

ML registry、runtime 狀態與行情根目錄分開解析；研究 registry 的 `RESEARCH_STATE_ROOT` 是其 repository root，不是 `OUTPUT_ROOT`。模型檔案存在只代表檔案在場，仍需核 lineage、source/account、cutoff、hash 與使用資格。DPAPI authority 不能直接複製成新電腦可用授權；新機需由原可信流程重新註冊。不要搬 authentication token、password、broker credential、Codex `auth.json` 或私聊 session database。

可攜版的背景程序與日誌會依版本契約寫入設定的輸出路徑；啟動時先核對畫面列出的實際設定。如果畫面無資料，先核對資料根、來源日期與 status receipt，不要以 fixture、latest 檔名或別人的模型補值。

## 子程序與排錯

- 可攜入口支援 `baldr.exe scripts/scheduled/<原腳本>.py <原參數>` 與 `baldr.exe -m <模組> <原參數>`。參數與 dry-run／preflight／execute gate 仍依原腳本；不要省略 CMD wrapper 所含的多段執行、環境、timeout 或 flags。
- 既有正式 Task 沿原 Python／CMD wrapper 管理；安裝可攜版本身不註冊、啟用、手動觸發或替換任何 Task。
- 若 Windows 顯示 SmartScreen 或簽章警告，先核對交付來源與簽章資訊；本指南不要求繞過系統保護。
- 首次無字或缺資料時，確認整個資料夾存在、JSON 為 UTF-8、roots 是程式包外的可寫絕對路徑。無 console 的 stdout／stderr 和 App 日誌依該交付版列出的實際位置核對。
- 長路徑、主機上的 Qt／Windows 差異、私人模型與自然排程執行都要依具名 QA 範圍判讀；在別台 Windows 主機啟動成功不由這份文件推定。

## 歷史日常研究修正版試用（Increment66）

本機試用入口為 `output/trial/Baldr-Daily-Research-66/Launch-Baldr.cmd`。雙擊啟動；在命令列加 `--check` 只核 EXE SHA、版本和隔離設定，不開 GUI。固定來源 `ec5c9573360891595bb395fa7bbb934077c6d4c0`，版本 `2026.10.06+ec5c95733608`；候選完整目錄 `dist/candidate_ec5c95733608_44024cd5/baldr`，EXE SHA-256 `f6eb269748fe8bf711535bac7811507dc61cb889929dee4fc30f3d73e4514494`。請從本次入口啟動並保留完整候選資料夾與 `state/`，不要只複製 EXE。逐步操作、已知問題與證據分見試用入口同目錄 `TRIAL_GUIDE.md`、`KNOWN_ISSUES.md`、`DELIVERY_RECEIPT.json`。

這份包使用新隔離價庫，四股價格截至 2026-09-23、大盤截至 2026-10-14；技術封存仍唯讀依賴原 BaldrTrial 本機絕對路徑。新 `state/` 不含使用者舊持倉／清單／回測，沒有移機保證。來源與同版 EXE 的 Windows Main／fresh 已限定驗四股篩選、兩股比較、收藏重開、兩筆隔離持倉及兩個原 `1.0.0` 單股策略保存／歷史／返回；其他內含的後續研究家族未由本次 Native／EXE 旅程接受。這是未簽章本機試用候選，不是發布、真人或跨機、歷史 PIT、完整績效或完整產品 Gate；原 `0f644faa`、`4b530`、`9fa` 包與正式資料未替換。詳[Increment66 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment66日常研究修正版候選依原計畫04)。

## 試用回報修正預覽（Increment59）

本機直接使用`output/trial/Baldr-Feedback-Preview-59/Launch-Baldr.cmd`；`--check`只核對固定EXE及輸出啟動設定，不開GUI。固定來源`0f644faa0d48417fa21d7c05c59b965cd06fc884`，候選`dist/candidate_0f644faa0d48_5a011727/baldr`，EXE 56,210,840 bytes、SHA-256 `d88d9ee9e6097bb0cdcb77bc8f9d209848ab3d1e0a32a05c80adaf4ababc5b99`；應保留整個資料夾。入口同目錄的`TRIAL_GUIDE.md`、`KNOWN_ISSUES.md`與交付收據列實際操作及範圍。

這份後續開發預覽含價格研究三步引導／股票順序修正、持倉表前移、兩原策略的當次規則封存及先前第二階段增量；不是只回移UI的窄版。新輸出、Registry與私人狀態在入口`state/`，不搬舊清單、持倉或run；技術來源仍唯讀引用原固定根，請勿移動／重簽。四股行情截至2026/09/23，大盤截至10/14，價格方向缺件仍未提供。

Windows原生自動化已在固定來源與EXE各完成四股查詢、持倉空QA帳版面、兩策略正常保存／歷史／規則／返回及新程序重開；原件／金融投影一致，archive／依賴鎖／共同啟動probe另通過。未改市場／觀察清單旅程沿原證據，未宣稱本EXE全部功能重跑、使用者真帳、真人、跨機、簽章、歷史PIT或完整Gate。原4b530窄版、9fa與active_delivery保持，詳[Increment59 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment59試用回報固定候選與同版出口)。

## 後續開發候選的限定驗證

固定來源50ddb6401238850f4c782f0d99494341d28ffc66的開發候選位於本機dist/candidate_50ddb6401238_9dfeb5e8/baldr，EXE為56,188,224 bytes，SHA-256為84a14003fa9f1de5ae2856c950b6b66c1d469856b4218b9005c983b9c768c033。保留整個baldr資料夾；以本頁「首次設定」的外部設定檔解析資料／輸出／研究Registry根，再啟動該資料夾內baldr.exe。不要只搬EXE、套用測試fixture為正式資料，或把開發包寫進現有試用入口。

這份包已通過固定archive／依賴鎖與共用啟動比較，另驗Windows原生畫面的兩條保存讀回流程：已保存TPEx法人批次加精確diagnostics用途接受，以及已保存Paper配置研究的明確登錄→Registry→個股→返回。各自在來源版與EXE關閉後用新程序重開；用途／資料缺件仍拒讀，沒有改正式資料或排程。步驟分見[法人用途](manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人用途接受與重開後續開發分支)、[配置登錄](manuals/WATCHLIST_AND_PORTFOLIO.md#登錄研究紀錄與跨頁重開)。

這是本機開發驗收候選，未簽章、未經真人或跨機驗收；P06使用原合成帳戶，不能代替真實帳本或完整來源資格。TPEx只限所列diagnostics，歷史PIT、評分與交易用途維持不可用。完整來源、原生範圍及收據見[Increment55 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment55p13p14固定候選native與同版出口)。既有4b530四流程試用包、原dist/baldr及active_delivery均保留。
## 2026-10-15 固定來源候選

另有固定來源`675bea262f8d25a1d5a8ade2762b7285fd11451b`的隔離候選`dist/candidate_675bea262f8d_07965800/baldr`，EXE SHA `b05f96456f36dc44036ca0688399b0cb5a85262f4a073c74a879f5ea6c970e26`。它通過原同版隔離probe與新增年度日曆binding／原Registry雙run重開、比較、返回及新程序旅程；沒有替換下表原交付或更新active_delivery。該證據仍是合成offscreen，未簽章、未驗Native真人或真實市場完整績效，不據此認定安裝／其他主機／完整產品Gate通過。完整來源與收據依[Increment31 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment31固定來源候選exe與registry同版旅程)。

## 2026-10-06 交付與驗收歷史

以下只描述 2026-10-06 兩份具名檔案，供追溯原始 build／QA；它們不是目前版本清單、下載指引或新機通過證據。

| 歷史產物 | 身份 | 當時記錄 |
|---|---|---|
| 原交付 `dist/baldr/baldr.exe` | build date `2026.10.06`；52,301,884 bytes；SHA-256 `ab0c72ef1c98f906e3d7ef14d440490ea4bf238aa53f959597636ddc2b1b263e` | 原交付仍未包含首波增量。 |
| 首波候選 `dist/candidate_4b40788bea9e_dd7335f7/baldr/baldr.exe` | source commit `4b40788bea9e74b5d5207d3d81b1e1c80394b7d6`；52,413,416 bytes；SHA-256 `6015311ff93286fa045ff04ed2a82284f812ed009cd48db79db435a2ef344410` | 固定來源候選的相同版本比較記錄見[首波 QA](../06_qa/BALDR_COMPLETION_FIRST_WAVE_20261006.md)。 |

當時具名隔離 QA 記錄了空資料設定提示、九工作區、Unicode／空格工作目錄、multiprocessing、取消與重新執行等項目；也明列 canonical 推薦保存結果重開受 no-follow guard 阻擋。Native 真人操作、真實私人模型、正式 Task 自然 run 與其他 Windows 機器未由該包驗收。該次 PASS 僅對應原 QA 指定的版本、來源和 fixture，不可外推為目前 exe、正式安裝或其他主機已通過。

## 第一版本機試用候選（2026-10-15）

依原補完計畫§0.3凍結四條主要旅程；固定來源`9fa4518c2aca87beaddef75a2b29165722da6a6c`，候選`dist/candidate_9fa4518c2aca_bdb37750/baldr`，EXE SHA `3b0c93147979b72bd4560b4bd1262e23e86b68d8ae8e8df4357d7d213f6e06fe`。本機直接使用`output/trial/Baldr-V1/Launch-Baldr.cmd`，入口先以.NET SHA核EXE再以專用config啟動；`--check`只輸出launch-info，已驗隔離設定，不需Python。原dist/baldr與active_delivery未替換。

四股試用副本、V4來源與個人狀態根位於本owner明示的BaldrTrial隔離根，實際絕對路徑在交付config.json；不要移動來源或套用正式資料根。TRIAL_GUIDE.md列四流程、來源日期／成本與問題，DELIVERY_RECEIPT.json、BUNDLE_INVENTORY.json及INPUT_INVENTORY.json保存固定身份。這是未簽章的本機候選；不是發布、其他主機安裝或真人接受。新機仍沿原安裝Runbook，不直接複製私人根／排程／帳戶。
