# Formal／Paper 輸入路徑唯讀重核（2026-10-24）

## 結果

本次重核修正先前對 Activation 環境的錯誤判讀。程式使用的三個 Formal 輸入變數實際為：

- `BALDR_ML_FORMAL_PORTFOLIO_LEDGER_PATH`
- `BALDR_ML_FORMAL_RULE_CHAMPION_HISTORY_PATH`
- `BALDR_ML_PIT_SECTOR_MEMBERSHIP_PATH`

三者在 Windows User 環境均已設定，皆指向 D 槽 `Min\Python\Project` 下的 `FA_Data` 目錄中的 `manifest.json`。D 槽已掛載，但該 `FA_Data` 目錄不存在，三個目標檔均不存在。

以目前 `DATA_ROOT` 對應相同相對路徑重核時，三個目標父目錄存在，但皆為空目錄，目標 `manifest.json` 均不存在。這表示不能只把設定中的磁碟代號從 D 改成目前資料根目錄：實際輸入 artifact 仍缺失。

`RULE_CHAMPION_CONTROLLED_STORE_ID` 與 `RULE_CHAMPION_CONTROLLED_STORE_HMAC_KEY` 在 User／Process 環境有設定；本次只核對存在狀態，沒有讀出、輸出或驗證 secret 內容。Machine 環境未設定這些項目。

Paper 輸入 `BALDR_ML_PAPER_PORTFOLIO_SNAPSHOT_DB_PATH` 與 `BALDR_ML_PAPER_TRADE_LEDGER_DB_PATH` 在 User／Process／Machine 環境均未設定。

## 現有候選 artifact 的時間界線

目前 `DATA_ROOT` 下仍有 `formal_prospective/clock-20260828`。只讀解析其小型 JSON 得到：clock `status=planned`、activation day=`2026-08-28`；activation manifest=`scheduled` 且 `readiness_status=inputs_deferred_until_activation`；strict readiness=`waiting_for_prospective_inputs`；當時保存的 environment preflight 對上述三個 Formal manifest 都是 `configured=true`／`exists=false`，並固定 `formal_oos_allowed=false`、`promotion_eligible=false`。該 clock 日期已過，不可重綁成現在的 activation 或用來補造觀測日。

`DATA_ROOT/output/paper_portfolio/paper_portfolio.sqlite` 另有一個檔案，檔案系統修改時間為 2026-09-07。本次未開啟 SQLite；檔案存在與時間不證明它是目前帳戶、cash／mark 或 Ledger 的有效來源。10/22 Track B 收據已明列舊 Paper cash 不作正式輸入，故本次不將它接到缺失的 Paper 路徑。

## 判定與邊界

- Activation 所需 Formal 輸入檔目前缺失；設定值存在不代表輸入有效。
- Paper snapshot／trade-ledger 路徑未設定，尚無可供 exact reader 驗證的 Paper source package。
- 可見的 2026-08-28 clock 是過期候選且當時被輸入缺件擋住；不得重用作新 clock 或 natural credit。
- 可見的舊 Paper SQLite 只核檔案 metadata，未讀內容、未接受來源，不是可直接綁定的 current Paper package。
- 本次僅使用 PowerShell／.NET 檔案系統唯讀檢查；沒有執行應用程式 preflight、producer、clock activation、排程、訓練或 promotion。
- 沒有建立目錄、修改環境變數、讀取 SQLite 內容或寫入正式／Paper／ML 資料。
- 後續必須找到合格的既有 artifact，或依 prospective-only producer contract 重新建立具來源、clock、policy 與 lineage 的 artifact，再由正式 consumer 精確讀回。空目錄不得以空白 manifest、placeholder 或舊 fixture 代替。

## 可重核範圍

這份收據記錄 2026-10-24 當下的 Windows User／Process／Machine 環境存在狀態及路徑檢查結果；沒有保存任何完整環境值、使用者路徑或 secret。環境之後若變更，應重新檢查，不沿用本收據推定目前 readiness。

## 10/25 目前環境唯讀重核

2026-10-25 03:25（Asia/Taipei）再查目前 Process／User／Machine 環境，未讀取或輸出任何 secret：三個 Formal 路徑變數目前在 Process 有設定，但設定目標和以當前 `DATA_ROOT` 對應的三個 manifest 均不存在；兩個 Paper snapshot／trade-ledger 路徑仍未設定。此結果與 10/24 收據一致，正式/Paper 輸入仍缺件；本次沒有執行 preflight、建立檔案、讀取 SQLite、修改環境或寫入資料。

### 10/25 03:38（Asia/Taipei）路徑身份及可見候選重核

這次另外比對了實際設定路徑的 clock 身分與 `DATA_ROOT` 下的相對目標，僅查檔案／目錄存在狀態及 metadata，沒有開啟任何 JSON／SQLite。三個 Formal 變數在 User／Process 都設為 `clock-20260819` 下的 `manifest.json`；該 clock 依[Prospective Formal Restart Direction §2](PROSPECTIVE_FORMAL_RESTART_DIRECTION_2026_08_19.md#2-新未來-clock-的選日規則)只保留歷史追溯，不能由新 clock consumer 接受。將這三條相對路徑映射到目前 `DATA_ROOT` 後，三個父目錄都存在但皆為空，manifest 不存在；D 槽設定目標也不存在。因此這不是單改磁碟代號可以解決的路徑問題，缺少的是新 prospective cycle 所需的輸入 artifact。

Paper 的 snapshot／trade-ledger 路徑在 Process／User／Machine 仍全部未設定。`DATA_ROOT/output/paper_portfolio` 可見 `paper_portfolio.sqlite`（28,672 bytes，最後修改 2026-09-07）、`paper_equal_weight_benchmark.sqlite`（20,480 bytes，最後修改 2026-08-28）及 `baseline_20260712.json`（2,314 bytes，最後修改 2026-07-13）；只核檔名與 metadata，沒有打開內容。這些舊檔未被綁定為目前帳戶 snapshot 或 fill ledger，不能代替 owner 已選定的 `paper-trade-import.v1` 輸入契約。

本次未建立新 clock、未執行 preflight／producer／activation／訓練，未修改環境或寫入正式資料。下一個 Formal cycle 必須依 restart direction 選新未來共同交易日並建立新 identity，再補齊三個 clock-bound manifests；Paper 必須先有明確當前 snapshot 與交易 fill 輸入，不能從舊 baseline 推定目前部位或現金。
