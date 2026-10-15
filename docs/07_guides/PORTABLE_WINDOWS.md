# baldr Windows 可攜版

可攜版供不安裝 Python 的 Windows 使用者啟動桌面 UI。使用與下載時一併提供的完整 `baldr` 資料夾，內含 `baldr.exe` 與 `_internal`；不要只複製 exe。版本、commit 與候選／發布狀態須看該份交付隨附的 metadata 和驗收收據，本指南不指定目前最新 exe。

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

依原補完計畫§0.3凍結四條主要旅程；固定來源`505d56f1c1178323f8184e291b718966431c7b07`，候選`dist/candidate_505d56f1c117_76de3824/baldr`，EXE SHA `e443188ef6227bfbfcd145758b125ceb7e8e7909bb0f3508bd65f8bd8074b7a3`。本機直接使用`output/trial/Baldr-V1/Launch-Baldr.cmd`，入口先以.NET SHA核EXE再以專用config啟動；`--check`只輸出launch-info，已驗隔離設定，不需Python。原dist/baldr與active_delivery未替換。

四股試用副本、V4來源與個人狀態根位於本owner明示的BaldrTrial隔離根，實際絕對路徑在交付config.json；不要移動來源或套用正式資料根。TRIAL_GUIDE.md列四流程、來源日期／成本與問題，DELIVERY_RECEIPT.json、BUNDLE_INVENTORY.json及INPUT_INVENTORY.json保存固定身份。這是未簽章的本機候選；不是發布、其他主機安裝或真人接受。新機仍沿原安裝Runbook，不直接複製私人根／排程／帳戶。