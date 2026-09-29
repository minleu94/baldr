# 操作手冊附冊：操作補充與維運參考

本冊屬於 [完整操作手冊](APPLICATION_MANUAL.md)，保留原手冊中的補充操作、研究 CLI、受控資料維護與排程判讀。日期化結果只代表當次觀測；目前進度請讀 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)。章節內容搬移時保留原操作步驟、參數與安全限制；不要把舊狀態或示例命令當成新執行授權。

## 2026-09-29 排程完整審視與修復

一般操作先讀 Windows task，再對照同次 status／log；不要只看 UI 或 Last Result。
在 repository 根目錄執行以下唯讀入口（不重跑、不重註冊）：

```cmd
scripts\scheduled\query_baldr_scheduled_tasks.cmd
.venv\Scripts\python.exe scripts\inspect_scheduled_task_registration.py
scripts\scheduled\run_ml_allocation_forward_daily.cmd preflight
```

Query 與 inspector 現覆蓋相同的 21 項清單，包含獨立 05:50 BankTaiwan；`configuration_ready`
只表示註冊、wrapper 與排程時間一致，不代表資料完整、模型有效或 Evidence 已核准。
日常 task 仍沿用既有 wrapper path，程式更新不必重建全部 Windows tasks。不要用
aggregate register 覆寫 dedicated forward／Paper／PIT／BankTaiwan 設定。

05:15 Evidence caller 會強制綁定同日 05:10 保存的精確 canonical `result_id`，並保存 status
bytes hash／artifact payload hash。`recommendation_binding_error` 表示輸入缺漏、過期、
未來、root／日期不符或 canonical readback 失敗，pipeline 尚未啟動；先核對快照該次
status 與 canonical run，不改 ID 或複製昨日檔。Pipeline timeout 為 600 秒，失敗保留
partial log；所有 dry-run 仍 `confirm=false`／`writes_evidence_db=false`。

05:45 learning 在 formal technical receipt 通過原 source/hash/window/clock 重驗時，
顯示 `verified_existing_same_day_technical_receipt` 並跳過 quick child，保留主 updater 的
latest status。不代表 learning 的 PIT availability、after-cost 或模型 gate 都已通過。
BankTaiwan 預設讀 Shadow root 的 bounded snapshot projection；同次 stdout／canonical
cohort 驗證不變，projection 損壞不可退回其他快照。固定排程時間也不是依賴完成的證明；
若 upstream 尚未產生合格同次 projection，仍應保留 dependency failure。

盤前 PIT CMD 預設使用 repository 的 `scripts/scheduled/pit_taxonomy_source_config.json`。
`PIT_TAXONOMY_SOURCE_CONFIG` 可指定其他明確檔案，但不得使用過期 TEMP 來源；直接
Python caller 需顯式設定 config。官方來源／parser 成功只證明當次取得，設定本身保持
research-only／未授予 formal license。Archive／denominator 完成後重讀 actual clock；
taxonomy 或 denominator blocked 現會回 exit 2。當期 history 只消費 coverage start
以後的 archive，範圍外舊檔完整保留；缺日曆 cache、範圍內損壞、缺 license／formal
publication 都仍阻擋，不用今日來源補造過去 PIT。

ML forward 等候 cutoff 的最新 heartbeat 在 `output/v4_ml_forward_scheduler/runtime_state.json`，
每輪另有 `run_state/<run-id>/state.json`。等待不覆寫 business latest status；中斷／例外
留 terminal 診斷，硬 kill 的非 terminal state 不代表 process 還活著。Windows
`0xC000013A` 只表示中斷，不能由此推論 dirty tree、電池或誰停止程序。本機 Operational
history 尚未啟用，嘗試啟用收到 OS Access denied；需管理員在 Task Scheduler 開啟歷史，
不是修改 ExecutionPolicy 或繞過 ACL。

仍須 owner 處理的界線：容量不足先規劃空間，不降低 200 GiB safety + 35 GiB persistent
與 40 GiB temporary 的原始門檻，也不刪既有模型／raw。`pending_execution_session_missed`
表示已凍結的舊 Paper 批次未完成，不能直接改綁今日推薦、補造舊成交或刪 receipt。
`human_thesis_required`／持倉 identity 缺件須補真實 thesis 與入場來源。基本面 current-only
資料不能當歷史公告／available-at；ML custody stale 不能在 frozen manifest 手改 hash。
完整當次 21 項盤點與受限驗證見[排程審視報告](../06_qa/SCHEDULED_OPERATIONS_REPAIR_20260929.md)。

## 正式行情修復補充（2026-09-23）

本輪已確認的歷史錯價、缺漏交易日、錯日紀錄、相依技術指標與圖表快取已完成修復及全量讀回。5,331,231 列日價與技指、2,210 份技術 CSV 及每日整合快取已同步；原始檔與修復前備份保留。買賣價／量、本益比及漲跌價差六個衍生複本也已依權威日價還原，沒有報價時保留空白，不填零或前日數字。

請重新開啟程式，從觀察清單進入「個股研究」，重新載入價格圖；將游標移到 2026-05-20 的 K 線，1256 收盤應為 183 元、1477 為 213 元。區塊標頭的「資料日」表示最新來源日，歷史價格以該根 K 線的日期為準。九個缺漏的歷史週六已補回 14,869 列；三個休市日及 5/20 的 54 筆錯置紀錄已從查詢資料排除，合計 2,942 列。官方缺開高低收或買賣報價仍是缺值，不代表股票出現新的利空。

日常沿用「資料更新」入口，已核驗修訂會自動套用，完整重算保留資料庫既有的五、六碼證券。若顯示來源錯值、缺少必要股票／日期、修復尚未完成或證據無法驗證，表示這次寫入已停止保護資料，不是買賣訊號。保留訊息並查閱[正式資料修復紀錄](../06_qa/FORMAL_DATA_REPAIR_2026_09_23.md)，不要刪除修訂檔或清空資料庫重試。舊版逐股計算腳本會停止，改由正常資料更新流程處理。

之後若再發現錯價，資料仍可修復；請記下股票代號、歷史日期、看到異常的頁面。每日新增行情照常更新，已修訂歷史值則走維護修訂流程：先暫停日常更新與其他寫入、核驗新來源及影響範圍、建立新備份與修改前後差異、套用修訂，再重算相依指標／快取及評估模型影響。最後核對正式資料並完成保護版本銜接，才恢復日常更新。目前沒有一般使用者的一鍵歷史修復／保護版本切換；不要刪除保護紀錄、手改 hash 或反覆重跑來繞過拒絕。

兩組新模型已重新建立資料、完整訓練、獨立評估及各 13 檔研究推論，正式判斷仍使用既有規則（rule_only）。尚未啟用也包含模型效果未證明優於基準，並非等系統上線便自動解除。來源與模型版本分開保留，詳見[新候選模型驗收](../06_qa/REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md)。本次完成的是已確認的行情與相依資料問題，不代表基本面歷史公告時間、產業標籤或所有資料來源的新鮮度都已齊備。

<details>
<summary>進階維護與回復（一般操作不需使用）</summary>

進階維護使用 `scripts/repair_formal_technical_raw_aliases.py`。依序執行 `--prepare --root <DATA_ROOT> --technical-receipt-dir <APPLIED_TECHNICAL_RECEIPT> --receipt-dir <NEW_RECEIPT>`、同一 receipt 的 `--stage`、`--audit --expected-manifest-hash <STAGE_FILE_SHA256>`，核對結果後才使用 `--apply --expected-manifest-hash <STAGE_FILE_SHA256> --confirm repair-formal-technical-raw-aliases`。各模式互斥；`--receipt-dir` 指定本輪所有來源、備份與 journal，hash 綁定確切 staging 版本，輸出 `applied` 才代表完成發布。中斷時用相同 receipt/hash 的 `--resume`；回復用 `--rollback`，同樣需要確認字串。後續資料漂移時停止，不得手改 hash。回復順序為六欄複本、每日快取、技指、錯日排除，再到原日價／大盤修訂。這是維護工具，日常使用者不需重跑。

六欄 writer 目前只接受唯一已套用的修訂版本；多個 applied 版本、pending 或證據漂移會停止寫入。下一次同範圍修訂不能只再加一個 applied receipt，必須另行驗證舊／新版本的銜接；現有工具尚未提供自動 supersession。已發生日常更新後，也不能假定舊 rollback 仍可直接執行，必須先通過 before／after 漂移檢查，否則以當時正式資料建立新的受控更正方案。修復的 heavy-chain reservation 並非所有日常 writer 的共同鎖，apply／resume／rollback 期間必須停止一般 updater、CSV 匯入與其他寫入；metadata 重驗不能替代這項維護前提。

</details>

下方 9/22 與舊 v3 段落保留作歷史追溯；目前結果以本節及新候選驗收為準。

## 2026-09-22 歷史價格更正與舊模型

5/20 的錯價已受控修正：1256 收盤為 183 元、1477 為 213 元。請重新開啟程式，再從觀察清單進入個股研究報告，重新載入價格圖；把游標移到該根 K 線，核對日期及開高低收。區塊標頭的「資料日」是最新來源日期，不能當作圖上每根 K 線的日期。官方沒有 OHLC 的列保持缺值，不以 0 或前一天價格補成正常交易。

價格更正不會自動修好已訓練的模型。已知的兩個舊模型版本目前停止載入，校準仍採 rule_only；舊模型、訓練資料與歷史結果保留供追溯。若進階研究／ML 流程回報 `stale_source_revision`、`model artifact is quarantined` 或 `historical price repair receipt blocks this PIT prefix`，意思是「來源已更正，這份模型或歷史資料須重建驗證」，不是股票出現新的買賣訊號。不要刪除修訂檔、解除攔截或改 hash 來繼續沿用舊結果。

進階維護入口 `scripts/repair_historical_price_spike_20260921.py` 預設只產生 dry-run plan；`--plan` 指定逐列計畫，`--apply --confirm repair-historical-price-spike-20260921` 才能寫入。正式執行先鎖定來源 hash、取得維護鎖與 online backup，再核對 transaction 前後值；`--rollback <receipt.json>` 僅還原 receipt 指定欄位，遇同欄位後續漂移會拒絕。此為本次核准事件的維護工具，日常使用者不用重跑；原始 daily CSV 不修改。`--source-revision-receipt` 是 PIT 建置的額外修訂來源，自動找到的正式 marker 仍會一併檢查，不能被此參數取代。

868 檔自 5/20 起的相依指標與 869 份既有個股／彙總 CSV 快取已完成受控同步。缺價後的指標重新暖機，資料不足時顯示空白；這不是股票新增利空，也不以補值使圖表看似連續。快取原本沒有的日期／欄位不新增，因此本次修復不代表所有來源已補齊或同日更新。修復結果、備份與模型重建限制見[歷史價格修復紀錄](../06_qa/HISTORICAL_PRICE_SPIKE_2026_09_21.md)及[模型影響紀錄](../06_qa/PRICE_REPAIR_MODEL_IMPACT_2026_09_22.md)。

指標維護工具 `scripts/technical_indicator_repair_dryrun.py` 只讀取資料並產生重算清單；`scripts/technical_indicator_repair_apply_guard.py` 預設核對清單，只有同時提供 `--apply`、已核准的 `--dryrun-manifest`／`--price-plan`／`--price-receipt` 與 `--confirm repair-technical-indicators-20260520` 才寫入。`--resume <pending.json>` 先驗備份、來源與 journal：資料庫未提交時只回復本批快取欄位，已提交且快取一致時補寫 receipt；狀態不明則停止。`--rollback <receipt.json>` 以原值清單回復指定欄位，不能替代整庫還原；以上三種模式互斥，日常使用者不需重跑。重建模型前仍須另走新 dataset／run identity 與驗證流程。

## 重訓現況補充（2026-09-22）

截至 9/22，後續 technical publication 曾重寫包含 5/20 修訂日的 120 交易日區間。正式資料庫當時不可視為已持續保有本次 technical repair；修復後的 run02 是獨立 research snapshot，不可覆蓋正式 SQLite。當日只有 868 列來源 custody，尚未物化通過可得性驗證的成熟標籤／可訓練 rows，因此當日尚未開始重訓。run02 已移交至 D 槽封存；以下 9/23 進度取代本段的重訓狀態。

正式 PIT／Raw-to-OOC 入口仍受 pending source-revision gate 阻擋；不可刪除 pending、回填舊 available_at 或用舊模型輸出替代修訂後驗證。另一路未來 research/shadow 候選可以評估 late-obtained 修訂歷史；不必只因修訂發生在過去就一律等待新的 forward horizon，但每筆 label 仍須按交易日序列證明 `horizon_end_date`，並以獨立來源證明 `label.available_at <= training_as_of`。已經過了日曆時間不會自動產生 label availability 證據。完整特徵相依重建、feature schema 與成熟標籤證據未通過前，不可 fit。修訂值絕不可宣稱為 2026-05-20 當時可得，也不可用於該日 historical PIT/OOS。細節見[隔離研究重建與重訓 Gate](../06_qa/REVISION_RETRAIN_ISOLATED_RESEARCH_2026_09_22.md)。

### 修訂模型的當日研究判讀

最新修復來源候選已完成兩組完整重訓：全市場 H5 資料 3,498,147 列，fit 使用全部 3,469,960 個成熟候選列；bounded 使用 21,898 列、兩演算法與四期間。兩者都已對 13 檔股票（含 1256、1477）完成最新來源推論，評估收據經獨立核對。舊 v3 的 3,433,790／17,285 訓練列結果只適用於舊來源，保留供比較。

目前仍不可恢復正式模型：資料已更正，但部分風險與機率指標仍未優於簡單基準，不能把來源修復或訓練完成當成模型有效的證明。日常維持 rule_only；缺失的歷史產業標籤保持缺值，原配置 targets 全是現金的限制也沒有改變。新結果見[修復來源候選驗收](../06_qa/REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md)，舊結果見[完整 v3 驗收](../06_qa/FULL_OFFICIAL_MARKET_V3_REPAIR_QA_2026_09_23.md)。

本輪也修正合法千分位價格（例如 `1,005.00`）被誤當成缺值的解析問題；真正缺價或逗號格式錯誤仍顯示缺值。這項程式修正不會自動重寫已封存資料或模型，最終重訓必須改用帶新來源身分的修正資料版本。狀態見[模型修復執行紀錄](../06_qa/MODEL_REPAIR_EXECUTION_2026_09_23.md)。

大盤來源的追加修復使用獨立 v3 研究建置入口：`python -m data_module.ml_restatement_research_dataset_v3 --official-market-manifest <CAPTURE_JSON> --official-market-hash <FILE_SHA256> --output-dir <NEW_DATASET_DIR> --custody-dir <NEW_EXTERNAL_CUSTODY_DIR>`。兩個輸出目錄都要是新目錄，custody 必須在 dataset 外；正式 SQLite、原股票快照及舊資料集皆不寫入。`--symbols`、`--decision-date-start/end`、`--limit-rows` 和 `--no-appends` 只供有界驗證，完整重建不加這些限制。執行前將 OMP／MKL／OpenBLAS／NUMEXPR threads 設為 2，避免佔滿同時重構所需資源。

此入口以官方兩份月報核對成交股數與真實開高低收，按官方交易日重算 labels，保留真正取得時間；成功產生 manifest 只表示研究資料建置完成。H5 訓練入口已支援 v3 及外部 custody v2，會核對實際開始證據、producer 原始碼、官方回應、原始 targets 與新增列的缺值目標；完整模型評估仍須另外完成。資料集不相容時不要手改版本、source SHA 或刪除 gate。逐項驗收見[大盤來源核對](../06_qa/MODEL_REPAIR_MARKET_SOURCE_AUDIT_2026_09_23.md)。

當日研究入口 `run_ml_allocation_restated_shadow.py`／`run_bounded_restated_current_heads.py` 使用 `--source-db` 並指定 v3 範本時，市場前綴自動讀取範本綁定的官方月報，股票仍來自唯讀 SQLite。更新官方月份後，可成對指定 `--official-market-manifest <CAPTURE_JSON>` 與 `--official-market-hash <FILE_SHA256>`；這兩個參數必須搭配 `--source-db`，資料取得鐘不得晚於此次擷取，僅使用 T-1 以前資料。模型使用官方市場訓練而當日輸入仍是舊市場定義時，兩條入口及底層研究推論都會拒絕，不自動降級；應核對官方來源清冊與契約，不要刪掉來源標記重試。新輸入保留自己的 identity，原模型與資料集不覆寫；輸出仍是研究結果，不授予正式配置或交易權限。

原 bounded 家族的舊 v3 路徑使用 `python -m data_module.bounded_official_market_restatement`，指定 `--parent-manifest-path`／`--expected-parent-hash`（已修復股票技術前綴的 bounded v2）、`--source-snapshot-path`／`--expected-snapshot-hash`（同一 run02）、`--official-market-manifest`／`--expected-official-market-hash`（官方大盤封存）、`--corporate-action-manifest`（原 bounded 綁定的官方公司事件）和新的 `--output-directory`。入口替換 8 個市場值、5 個相依品質欄並重算四個 horizon；其餘 49 欄、原現金 targets／投組狀態保留。若原決策日非官方交易日、股票價格路徑不完整或新區間碰到公司事件，該列不進訓練，會出現在新清冊 `restatement.excluded_rows`，原資料不刪除。原四組日期窗保持，標籤成熟期按官方交易日重算；此獨立研究 profile 明示修訂鐘晚於歷史 fold，不能當作歷史 PIT／正式 OOS。新清冊經 `train_bounded_restated_research.py` 訓練後，還須檢查獨立評估及最新輸入結果。

bounded 缺價排除可能讓原日期窗中的有效決策日減少。consumer 會依仍有樣本的日期再次檢查原 60 日 purge，必要時只把訓練截止日往前收，保留原測試區間；`preflight.folds` 同時顯示 declared／effective train end。原 trainer 的 60 日 purge、5 日 embargo、label maturity 與 expanding-window 檢查照常執行，不能藉由降低天數略過失敗。

`scripts/run_ml_allocation_restated_shadow.py` 是進階維護入口。它可讀取已封存的當日列，或從指定 SQLite 唯讀來源建立新的當日輸入，保留實際執行時間；目前不改 UI 預設模型，也不授予持股配置或下單權限。

先從本次受控訓練結果取得確切的 release 路徑與 `release_identity_hash`，再取得要判讀的 dataset manifest 及其檔案 SHA-256。使用下列參數執行：

```powershell
.\.venv\Scripts\python.exe scripts\run_ml_allocation_restated_shadow.py --release-root <RELEASE_ROOT> --release-identity-hash <RELEASE_IDENTITY_SHA256> --dataset-manifest <DATASET_MANIFEST> --dataset-manifest-hash <MANIFEST_FILE_SHA256> --symbols 1256 1477 --output-root <RESEARCH_OUTPUT_ROOT>
```

- `--release-identity-hash` 綁定模型版本，`--dataset-manifest-hash` 綁定這次使用的輸入；兩者都使用 `sha256:<64 位小寫十六進位>`。
- `--symbols` 明確指定 1–250 檔股票；缺少當日列或出現重複資料時停止，不以舊日期替代。
- `--output-root` 須在來源資料集與模型目錄外；CLI 會在擷取前核對，不會先把新檔案寫進模型目錄再報錯。結果寫入 `current_shadow/<receipt-hash>.json`，同名結果不覆寫。
- 成功狀態 `completed_research_inference` 表示載入、資料驗證和推論完成；不表示預測準確或模型優於基準。報酬與風險以 bp 保存，10,000 bp = 100%；固定全部現金的配置只是原限制，不能當成模型學會持股比例。
- 結果中的 `training_release` 是訓練來源，`prepared_input` 是這次判讀來源；特徵日期與實際 capture 時間分開顯示。晚到修訂資料仍不是歷史 PIT。
- 遇到 hash 不符、當日列缺少、來源尚未可得或 feature order／scale 不符，使用來源 producer 產生新的封存版本後再跑；不要手改 manifest、回填舊時間、解除原模型隔離或覆寫舊模型。

之後每日需要新輸入時，在同一命令另加 `--source-db <SQLITE_PATH> --price-repair-receipt <APPLIED_RECEIPT_JSON> --price-repair-receipt-hash <RECEIPT_FILE_SHA256>`。此時 `--dataset-manifest` 作為固定特徵契約範本；程式從同一個 SQLite 唯讀 transaction 取實際臺北當日以前的價格，核對指定股票的 5/20 修正值，完整重算其指標，再將本次原始前綴、62 欄特徵與新的資料身分封存到 `input_captures/`。來源資料庫、範本資料集與模型都不覆寫；此入口沒有自動排程，也不接受把執行鐘改成歷史日期。

若來源遺失修正值、缺少指定股票、市場來源超過七個日曆日、擷取期間跨過臺北午夜，或封存的原始前綴被變更，程式會停止。七日上限只是陳舊檢查，不能證明資料涵蓋了每個應有的交易日；請仍核對結果中的特徵日期。未完成的 `input_captures/` 子目錄不含可供推論的完整 manifest，不應手動補檔。

當前驗證範圍與限制見[當日研究輸入 QA](../06_qa/MODEL_REPAIR_CURRENT_INPUTS_2026_09_23.md)。完整資料重訓尚未驗收時，此入口只用於候選模型驗證。

當日入口也接受已封存的 full v2 資料。v2 的 22 檔修正列保留各自實際補算時間，其餘列保留原重建時間；程式逐列依來源檢查，不把全部列改寫成同一個鐘。用 v2 當範本擷取新資料時，輸出仍是獨立的 `current_inference_only` 前綴與身分，不沿用歷史合併的宣告或 row IDs。

原 bounded 家族另有 `scripts/run_bounded_restated_current_heads.py`。它讀取受控重訓目錄中的 `fit_receipt.json`、audit 與模型，不需要把研究模型改名或放進舊 release 目錄：

```powershell
.\.venv\Scripts\python.exe scripts\run_bounded_restated_current_heads.py --fit-directory <FIT_DIRECTORY> --fit-receipt-hash <FIT_RECEIPT_FILE_SHA256> --training-manifest <TRAINING_MANIFEST> --training-manifest-hash <TRAINING_MANIFEST_FILE_SHA256> --current-manifest <CURRENT_MANIFEST> --current-manifest-hash <CURRENT_MANIFEST_FILE_SHA256> --symbols 1256 1477 --output-root <RESEARCH_OUTPUT_ROOT>
```

`training` 參數指定模型確實使用的資料；`current` 參數指定當日輸入。需要從 SQLite 重新擷取時，同樣加上 `--source-db` 與兩個修訂 receipt 參數，這時 current manifest 僅作特徵契約範本。輸出位於 `bounded_current_heads/<receipt-hash>.json`，逐股列出三組特徵、四個期間、兩種原演算法的 24 組研究預測；成功狀態為 `completed_research_predictions`。它沒有持股配置建議，不能用這些數字代替買賣指令。

若 bounded 的特徵登錄表因重算改了來源識別，程式會驗證明列的轉換證據。舊路徑只更新技指與官方市場來源；本輪候選另外明列八個技指原始欄位改讀權威日價，重算 46 個股票／品質 slots 與 13 個市場 slots，保留三個產業 slots。52 個來源定義及 62 個模型欄位的名稱、順序、尺度、dtype 與缺值規則不變，任意改尺度、特徵家族或標準化仍會拒絕。兩端登錄身分都保留於結果；來源 hash／日期錯誤時產生新版本，不覆寫已封存檔案。

本輪新來源使用 `scripts/build_ml_restatement_candidate.py`，指定 `--snapshot-db`／`--expected-snapshot-sha256`、`--source-manifest`／`--expected-source-manifest-sha256`、官方市場 manifest/hash，以及新的 `--output-dir`／`--custody-dir`。入口建立含正式來源修訂證據的 profile，消費者會重新核驗；完整建置不加列數或股票限制。bounded 的官方來源入口另需成對指定 `--candidate-source-profile-path`／`--expected-candidate-source-profile-hash`，缺少本輪 profile 不能退回舊路徑。此工作僅建立新的研究版本，與重構凍結的 ML 輸入契約分開，不啟用正式模型。

### 修訂研究模型的維護重訓

以下入口供維護者重現本次修復，一般看盤不必執行。先驗收完整來源與標籤，再指定新的輸出目錄；執行成功不會切換正式模型。

正式來源補回／排除交易日後，使用 `scripts/build_ml_restatement_candidate.py` 建立新的完整研究資料。必填 `--snapshot-db`／`--expected-snapshot-sha256`、`--source-manifest`／`--expected-source-manifest-sha256`，以及 `--official-market-manifest`／`--official-market-hash`；這些參數必須同時對應本輪已核驗的 run02 快照、來源清冊與官方市場封存，不能任意換成其他資料庫。`--output-dir` 是全新資料集目錄，`--custody-dir` 是資料集外的全新查核目錄；程式另外保存來源 profile，逐一核對價格、大盤、補回交易日與排除紀錄。完整重建不加 `--symbols`、日期篩選、`--limit-rows` 或 `--no-appends`。來源或證據不符即停止，保留失敗輸出並查明原因；不要修改 hash 或沿用舊資料身分。此入口不寫正式 SQLite、原始日檔或模型 pointer，完整 fit 與獨立驗收仍須接續完成，紀錄見[修復來源候選 QA](../06_qa/REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md)。

- 全市場 H5 使用 `scripts/train_ml_allocation_restated_research.py`：`--manifest` 指定已完成的修訂資料清冊，`--source-custody`／`--source-custody-hash` 綁定清冊外的建置與來源查核證據，`--output-root` 指定新模型根目錄，`--horizons 5` 保留原 H5 家族。`--batch-size` 控制分批讀取量；`--logistic-iterations` 預設 6，改變它會形成不同訓練設定。`--max-fit-rows` 僅供小樣本接線驗證，完整重訓不得設定。超過 100,000 列卻沒有 custody 證據、缺分片、來源遭變更或時鐘不符，均停止並保留失敗證據。
- 原 bounded 家族使用 `scripts/train_bounded_restated_research.py --publication-dir <RESTATED_DATASET> --output-directory <NEW_FIT_DIRECTORY>`。`--random-state` 預設 42、`--hgb-max-iter` 預設 60、`--ridge-alpha` 預設 1；這些是明確的新訓練設定，不宣稱等同未記錄的舊模型設定。資料須包含完整特徵重算與標籤修訂，只有標籤補算的中間版本不能當最終來源。

兩個入口將計算執行緒限制為 2，保留原 62 欄輸入契約。完成後先核對訓練收據的來源／模型 hashes、各期間成熟樣本數、獨立評估與簡單基準，再使用上述當日研究入口讀取；數值正確不代表具有投資優勢。詳細完整命令及驗證見[訓練 QA](../06_qa/RESTATED_ALLOCATION_REPAIR_TRAINING_2026_09_23.md)。

### 唯讀修訂資料 acceptance preview

在要評估 late-obtained 歷史是否可用於未來 research/shadow 候選時，可從封存資料產生只讀 preview：

```powershell
$TrainingAsOf = [DateTimeOffset]::UtcNow.ToString('o')
.\.venv\Scripts\python.exe scripts\preview_ml_daily_price_revision_acceptance.py `
  --archive-root 'D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna' `
  --training-as-of $TrainingAsOf
```

命令驗證已封存 transfer receipt、868 列 v2 manifest/JSONL、run02 SQLite bytes、price/technical receipts、recovery 與 tracked verifier，並列出每列 custody observation、feature dependency 缺口及 horizon/availability 證據。它會檢查封存 inventory 的檔案大小，並重算明列的來源檔 hash；不會重算全部 26 個封存檔案的 hash。preview 以 create-only 方式寫到 ignored `output\qa\revision_aware_acceptance_preview\`，不寫 D archive、正式 DB 或模型，不呼叫正式 PIT gate，也不 fit。`preview_complete_candidate_not_accepted` 表示證據摘要已建立，不表示資料已獲接受或可訓練；需先補齊 feature 重建與逐列 label availability 證據。此工具也不替 2026-05-20 歷史 PIT 開 gate。

此版本重新計算 12 個選定來源檔的 content hash、檢查 26 項 inventory 的檔案大小；不重新計算全部封存檔案的 hash。成功產出 preview 仍只代表 custody 與已知缺口的摘要已寫入 QA output，不代表接受資料或開始模型 fit。操作證據見[修訂資料 acceptance preview QA](../06_qa/REVISION_RETRAIN_ISOLATED_RESEARCH_2026_09_22.md)。

## 2026-09-21 V5 日常操作與可讀性工程

本輪版本名稱是「V5日常操作與可讀性工程」。目前已把既有唯讀資料整理成首頁優先摘要、分層導覽、候選／研究報告／持倉的下一步提示、回測與推薦的進階入口，以及按需價格圖；這是 bounded engineering 與 QA evidence，不是正式 V4／V5 gate，也不是 V6 user-level personalization maturity。

### 2026-09-21 個股研究資料判讀補充

本日正式資料查核確認，個股研究報告的價格／技術與其他來源可能有不同資料日。報告各 source row 會分開顯示來源、來源狀態、品質、資料日、資料可得時間、版本、筆數與預期資料期；請依區塊與股票逐列判讀，不要用報告開啟日或另一個來源的日期代替。

- 2026-09-21 的 formal daily price 與 technical 查到目標日期 rows，且本輪日期／重複鍵／raw 對照檢查通過；2382、3207、9935、1418 的查詢 rows 都標為 2026-09-21。這不等於官方交易所全域真值，也不代表 institutional、credit、TDCC、fundamental 或 broker 也都有 9/21 row。
- 本次 formal institutional／credit 最新到 2026-09-08，TDCC 最新到 2026-09-04；3207 broker 最新到 2026-08-20、9935 到 2026-09-14，1418 沒有 formal broker row。畫面若顯示 stale、partial、unknown 或 missing，代表來源時效／coverage 缺件，不能手動補 0 或把空白當成中性數值。
- freshness receipt 的 `candidate_only=true` 只代表隔離 candidate DB 的研究資料。它不會認證 formal SQLite；只有正式發布到 formal source 後，才能作為 formal report evidence。1418 Paper blocked 若同時缺 source lineage，應分類為 lineage／candidate 缺件，不推論成 9/21 價格錯誤。
- 若同一報告同時看到價格 9/21、籌碼 9/8 或 TDCC 9/4，這是各來源的實際可得日不同。請開啟「來源與各區塊日期」查看 source trace／可得時間；不要用較新的 candidate date 覆蓋 formal date。
- 更新方向修正後，請重啟程式再開啟個股研究報告，讓新的 read service 載入生效。
- 報告的最新一日漲跌會依來源方向顯示正負；若看到「漲跌資料或方向不足，無法確認。」，代表證據不足，不等於持平，也不要自行修改原始價格。
- 要做全市場價格合理性初篩，可在唯讀環境執行：

  ```powershell
  $env:PYTHONIOENCODING = "utf-8"
  .\.venv\Scripts\python.exe scripts\audit_price_jump_20260921.py `
    --include-merged `
    --output output\qa\price_jump_20260921
  ```

  稽核以 `mode=ro` 加 `PRAGMA query_only=ON` 讀取 Formal SQLite，並比較 9/18→9/21 及 8/25 起相鄰交易日；不初始化、寫入、回填或把缺資料補成 0。已保存的本輪結果為 9/21 1,968／1,968 rows／codes、O/H/L/C invalid 0、9/18→9/21 絕對跳幅 ≥10% 7 筆；這些是排序與待核證據，不是全市場價格正確證明。1256 的 172→170（-2）、1477 的 194→191.5（-2.5）及 831 筆可解析負號也支持報告方向修正；merged aggregate 只到 2026-07-14，應判為 stale，不能當成 9/21 對照來源。

正式查核與 bounded 全市場 row count 見 [2026-09-21 個股研究資料鏈 Incident QA](../06_qa/STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)。本補充不授予資料全新鮮、V5/V6 formal completion 或任何交易權限。

### 從哪裡開始

1. 啟動主程式後先選左側「日常使用」的「決策工作台」。預設先看「今日優先查看」：判讀日期、資料日期、每日結論、持倉／候選／市場／資料狀態與各列下一步。
2. 要看完整工作台時，按「顯示進階工作台」；進階表格、來源、技術與「研究證據」仍在同一頁，不會改變資料或重新評分。
3. 「日常使用」包含工作台、市場探索、推薦分析、觀察清單、持倉管理；「進階研究」包含策略回測；「系統維護」包含數據更新與系統狀態。從通知或 deep link 進入深頁時，對應群組會自動展開。

### 日常判讀與進階操作

- **候選池**：先選股票看摘要、觸發原因、資料日／品質與下一步；再按「查看選中個股研究報告」。完整分析與共用證據在「顯示進階研究」內；「選擇原推薦來源」是日常下一步按鈕，先核對 exact identity 再開啟原理由。推薦來源是追溯 identity，不是評分或買賣訊號。
- **個股研究報告**：先看「摘要」的結論、證據、變化、風險、資料是否足夠與下一步。價格／技術、基本面／營收財報、籌碼／產業事件、持倉／Health／Exit、Rule／ML／歷史會在進入對應分頁時才繪製；完整開高低收才顯示 K 線／成交量，缺開高低收時改顯示收盤圖。按「顯示進階：逐項證據與欄位」或「顯示進階：來源與各區塊日期」查看欄位、來源、品質、資料日、可得時間與版本。
- **推薦分析**：新手入口先選 Profile 與資料範圍，結果頁先看結論、Why／Why Not、風險與資料日；需要調整時進入進階 Profile／設定。保存結果會封存該次推薦並以相同 `result_id` 驗證讀回，保留來源與股票供後續研究；一般 Qt 手動保存不會建立個人化送達 ACK。成功保存不代表已送達、已成交或個人化效果成立。
- **策略回測**：先選研究模式、股票／清單、日期、策略，再看畫面上的資金、費用、滑價、執行價格與停損停利摘要。按「修改資金與風控設定」展開資金、成本、成交與停損停利欄位；按「顯示進階研究設定」展開策略詳細參數、最佳化與 Walk-forward。兩個切換只改可見性，不切換模式或重設參數。按唯一主要「執行」按鈕後，在結果頁分開判讀摘要、診斷、圖表、最佳化或驗證 evidence；回測不等於正式策略升級或交易許可。
- **持倉管理**：先看持倉摘要、資料缺口與下一步，再選列查看價格／停損停利、策略來源或個股研究。歷史、Journal、模擬持倉、Paper 與 Stress 位於「顯示進階：交易歷史／日誌／模擬持倉／壓力測試」；模擬或 Paper projection 不等於實際成交。

### 本輪跨頁呈現與恢復行為

- 左側導覽的群組標題與工作區項目會左對齊；展開／收合可用鍵盤操作，窄版不應以置中標題或固定導覽寬度壓縮文字。
- 個股報告換到另一檔股票時，先等新股票載入，不要把上一檔的摘要、價格或進階內容當成新股票。新股票載入失敗時畫面清除舊報告並顯示新股票的錯誤與 Journey 下一步；同一檔重新載入失敗／取消時，畫面會明示上次可用資料及其資料日，同時保留本次失敗原因。來源摘要保持可讀，完整 source／mapping／snapshot identity 在來源進階與 tooltip 查閱。
- 持倉管理的日常摘要、進階正文、Paper health、持倉明細、歷史／Journal／模擬資料分開判讀。更新狀態顯示可讀日期並保留原始 timestamp 說明；進階正文可垂直捲動，splitter 調整不代表資料或交易狀態改變。
- 決策工作台首頁與頁面說明按鈕會把工程欄位轉成白話下一步與限制；完整診斷仍可由進階來源／tooltip 查閱。這些是呈現與導引行為，不會改寫資料、評分、Journal、Paper ledger 或啟動交易。

### 日期、來源與失敗恢復

畫面上的「決策日」是推薦／市場判讀的日期；「資料日」是該區塊實際使用的最新資料日期；「可得時間」是資料在決策時是否可用的時間證據。不同區塊可能有不同資料日，不能用今天日期替代。請用畫面顯示的對應當次推薦來源與股票一起核對；同一股票在不同推薦結果中仍可能是不同候選，來源缺件或不一致時不可用股票代號或日期猜配。

看到「讀取失敗」、「資料不足」、「來源不一致」或「狀態未知」時，先讀白話原因與下一步，按「重新載入／再試一次」，再依提示回到數據更新、原推薦來源或進階研究。已有成功載入的資料時，畫面會標示保留的上次成功載入內容；這不代表資料已更新。資料不足、日期條件未滿足、來源對不上或背景報告載入失敗時，系統會阻擋不可靠判讀，不能手動補值或把空白當成 0。

完整功能仍位於各工作區的進階區、既有「決策 → 結果」頁、Evidence／Runtime 與 Manual 後續章節；首頁摘要只整理既有畫面資料，沒有移除原功能，也不會因查看、切頁或展開進階而改寫資料或啟動外部更新。

## 2026-09-21 晨間排程、候選資料與 Evidence 判讀

每日 quick 的 institutional／credit／TDCC 寫入隔離 Phase3C candidate DB；freshness status 會直接列出 candidate DB 的 latest date、兩市場 source version、duplicate count 與 row count。`passed_with_warnings` 只有在 daily price／technical 核心步驟成功且 warning 可精確歸類到 candidate lane 時，Position Health 才可繼續；未知 warning 仍會阻擋。

月營收 snapshot 套用到 `fundamental_current_observations` 只表示目前觀測資料已接線，不代表 formal PIT 完整。若 `monthly_revenue_expected_period_not_available`／`quarterly_statement_expected_period_not_available` 仍存在，請由資料 owner 補官方 announcement／available-at／revision lineage；不可手動把 current row 複製到 formal table。

05:15 Evidence 的 CMD／PowerShell 都走同一 orchestrator，Paper status 預設讀隔離路徑。`paper_health_refresh_status=passed`、`paper_health_source_status=degraded`、`position_health_transition_status=degraded` 且 Task Scheduler `LastTaskResult=0` 可同時成立：這代表工程接線已完成，但仍有人工 thesis／position lineage 或自然 maturity 待補，不代表投資有效或可自動交易。每次執行 log 帶 timestamp；Exit child 最多等待 300 秒，任何 log write error 必須在 status 顯示，不應只看到 traceback。

同日重跑會使用 `position_health_transitions_v2.sqlite` 的 semantic identity。若市場 rows、持倉、condition、metrics 與 policy 均相同，capture 時間或 artifact 檔名不同仍應顯示 idempotent；實質輸入不同仍 blocked。舊 `position_health_transitions.sqlite` 只作歷史稽核，不應刪除、覆寫或手動複製成 v2。

## 2026-09-14 排程警告與 SQLite 鎖定判讀

`database is locked` 表示連線競爭，不等於檔案毀損。DBManager 對短暫鎖定最多等待 30 秒；超時仍失敗並回滾，不能將失敗 status 手改為通過。先核對更新 log 與最新資料日，再確認需要重試的同步範圍。

Evidence 的 `forward_summary_status:INSUFFICIENT_SAMPLE` 列為樣本累積等待；價格缺漏、pipeline errors 與 blocking gaps 仍需處理。`position_health_baseline_is_not_an_exit_instruction` 和 `position_health_daily_refresh_does_not_evaluate_transition` 為說明性 advisory。Paper 進場來源未驗證與 thesis 缺漏仍保留，不可解讀成實際持倉的出場訊號。

## 2026-09-15 Continuity Review Workbench R1

### 入口與操作

1. 開啟「決策工作台」，在 review table 找到「研究檢討提醒」列。
2. 以列的 `result_id:stock_code` exact candidate 選取提醒；右側 Inspector 會顯示股票、研究意向、檢討時間（台北）、提醒原因與 source trace。
3. 按「開啟下鑽」進入既有「個股研究報告」；「決策 → 結果」頁會以同一 `result_id` 顯示 5／10／20／60 個交易日 maturity、Evidence、既有 Journal 與 continuity controls。
4. 只有明確需要改變研究狀態或下次檢視時間時，才在 Journey 的 controls 按「納入研究／略過／設定下次檢視／記筆記」。這些是既有 append-only Journal action；Workbench table 本身沒有完成、清除、重排或交易按鈕。
5. 由觀察清單或持倉列開啟的個股研究報告，需等待「報告已載入」及「決策 → 結果」完成 exact candidate 驗證；驗證期間、讀取失敗、candidate 缺件或 identity conflict 時，Journey 的研究動作會停用。驗證成功後才會恢復目前 candidate 的 controls。

### 判讀與安全邊界

- 提醒列的 `scheduled`／`due`／`overdue`／`invalid` 是以 `next_review_at` 與讀取時的 `Asia/Taipei` clock 投影；尚未到期的 `scheduled` 仍會出列，時間只影響 due 分類；`invalid` 需人工確認，不猜測時間。
- `decision_date` 是推薦／市場決策日，`continuity_as_of` 是提醒投影的歷史邊界，兩者不同。目前 UI 沒有歷史回放入口，畫面依實際讀取時間投影；只有 API／測試進行歷史重播時，才傳明確帶時區的 `continuity_as_of`，不可用畫面日期代替。
- `result_id` 是推薦結果根；同一股票出現在多個結果時，必須依選取列的 exact candidate 下鑽，不以股票代碼、日期或第一筆候選猜配。只有保存的 Recommendation JSON 通過 exact stock 檢查時，Portfolio 才會沿用推薦 `result_id`。
- Portfolio 同一股票可能有多個持倉來源；右鍵或按鈕研究入口依目前點選列的 `position_id` 及其保存的 `result_id` 定位，不會取第一筆同股持倉。Recommendation 保存列若缺少 exact stock、雙語代號兩欄皆缺、精確列重複或涉及要求代號的矛盾，保持未連結；單欄 legacy alias 缺失仍按既有相容規則處理。
- Journey 的 linked 只代表來源 identity 可連結；`ready`、`pending`、`unknown` 是各 maturity window 的結果狀態，不能把 linked 或 ready 解讀成實際成交損益、投資有效性或正式 evidence credit。
- Workbench／Journey 的 projection 與詳情是唯讀研究資料；不會自動下單、調倉、改寫 Recommendation／Evidence／Portfolio ledger，也不會因開啟報告而寫入 Journal。

### 排錯

- 沒有 reminder：先確認 `output_root/portfolio/journal_entries.jsonl` 存在、JSONL chain 完整，再核對 exact candidate 是否有在查詢 `as_of` 前已建立、且尚未被清除的 schedule revision；不以 `as_of` 必須晚於 `next_review_at` 作為出列條件。缺檔或 identity conflict 會維持空／降級並列 diagnostic。
- 看見 `unknown`／`pending`：表示 outcome 尚未有足夠可得資料或來源缺漏；不可手動改成 ready。先看 Journey 的 source trace、available time 與說明欄。
- Journey 顯示「待成熟（未有足夠未來資料）」時，只代表未有足夠 future observation，不是 ready，也不是成交損益；缺件／讀取失敗／identity conflict 時，可重新載入原結果，但不能視為已驗證或手動猜配對。
- 看見 identity conflict：停止下鑽與任何動作，核對 `result_id`、`stock_code`、source snapshot id／hash；可重新載入原結果，但不能視為已驗證或手動猜配對。
- 關閉忙碌中的報告視窗時，系統會先合作式取消背景讀取，待 worker 自然結束後才關閉；不要以工作管理員強殺程序判定成功。

## 2026-09-16 Personalization 真實來源唯讀檢視

### 入口與用途

`scripts\inspect_personalization_sources.py` 是 bounded、CLI-only 的真實來源檢視入口。它以明確的 `--scope-id` 與 `--as-of` 讀取既有 Recommendation JSON／`recommendation_runs.db`、Portfolio Journal JSONL、EvidenceEvent／outcome SQLite，以及既有 projection receipt；可再指定 `--evaluation-cutoff-at`、`--result-id`、`--stock-code`、`--fit-artifact` 與各項上限。

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -X utf8 -m scripts.inspect_personalization_sources `
  --scope-id <SCOPE_ID> --as-of YYYY-MM-DD `
  --evaluation-cutoff-at <AWARE_ISO_DATETIME> `
  --output-root <OUTPUT_ROOT> --result-id <RESULT_ID> --stock-code <STOCK_CODE>
```

讀取端不建立 `TWStockConfig`、`RecommendationRepository` 或 `JournalService` writer；SQLite 使用 `mode=ro`／`PRAGMA query_only`，EvidenceEvent 與 outcomes 在同一 read transaction 讀取，主檔及 `-wal`／`-shm` 都納入 source fingerprint。缺少 root、metadata、Journal、receipt、scope 或 outcome 時只留下 diagnostic，不 mkdir、不做 DDL、不寫 JSONL／SQLite、不建立 learner、不改 global pointer、scheduler、Portfolio order 或 broker 狀態。

### 報告判讀

- `source_consistency_status=verified` 且 `source_bytes_unchanged=true` 才代表本次讀取的來源 bytes／mtime 可對帳；若發生變動，報告會是 `invalidated`、不提供 ready evaluation row 或 evaluator 結果。
- `inventory` 與 `candidate_inventory` 分別列出 available、selected、excluded、limit、selection order、truncated 與排除原因。有限上限不是全 scope；看到 `*_inventory_truncated` 時，應提高上限或改用明確 `--result-id`／`--stock-code` 再檢視。另須確認 `source_completeness_status=verified`；Journal malformed row、exact action／ACK 超過 bounded limit 或來源讀取錯誤時會是 `incomplete`，evaluation 與 action preflight 都會停止，不能把未知轉成 `not_recorded`。
- `denominators` 分開保留 `prediction_available`、`population_only`、`not_delivered`、`prediction_unavailable`、action recorded／conflict／not recorded、outcome ready／pending／matured missing／invalid／duplicate、`natural_forward`／`paper_research`／`user_declared_context`／`historical_replay`／`synthetic_fixture` 與 `action_utility`。缺值不會補成 0 或負例。
- `evaluation` 只有在 exact scope／result／stock／prediction／receipt／horizon／cost／label contract／return basis、明確 label availability timestamp、outcome tier、label 與 fit artifact 都可驗證時才可產生；缺 fit artifact、自然樣本或 maturity 是 pending／diagnostic，不是個人化效果。
- `population_probability_bp` 只接受明確 population 欄位；不得以 calibrated probability、ranking、percentile、毛報酬或文字信心代換。`source_id` 也不等於 `result_id`。

時間欄位必須分開判讀：`prediction_decision_at` 是 producer 實際推論 anchor，`delivery_at` 是 technical ACK 的送達時間，`human_decision_at` 是 exact action history 最後一筆 recorded revision 的 `action_at`。ACK 晚於 producer 推論本身是正常流程，不算 late delivery；只有 `delivery_at > human_decision_at` 才加入 `late_delivery_no_natural_credit`，該列仍可在 projection 中觀測，但會從 natural evaluation row／action utility 分母排除。應同時查看 `natural_forward_count`、`evaluation_row_count`、`cohort.included_evaluation_row_count` 與 `cohort.excluded_reason_counts`，不可只看 action 或 outcome tier。

active candidate 的 `label_registry_hash`、`label_contract_id` 與 `return_basis` 必須由已驗證的 training lineage／candidate provenance custody 讀出，並在 consumer、projection receipt、action 與 outcome identity 間一致；缺漏或 mismatch 會 fail closed。receipt writer 不以目前全域常數替舊 candidate 宣告新 label contract，既有未帶 personal envelope 的 action 也不 retrofit。

新的 personal action 必須由 `PersonalizationDecisionRecorder` 經既有 Decision Continuity／Journal append path 保存完整 scope、prediction、receipt、horizon、cost、label／return contract，且 `action_at >= delivered_at`；相同 request retry 只回讀原 revision。既有未帶 personal envelope 的 accepted／skipped／watch／held／buy／sell action 只標示 `legacy_action_without_personal_envelope`，禁止 retrofit 到舊 prediction。

### 明示新增 personal action

需要把新的研究回應寫入既有 Journal 時，使用 `scripts\record_personalization_action.py`。呼叫端必須明示 scope、exact `result_id + stock_code`、action、decision kind、request id 與 actor；命令會先以唯讀 read service 驗證同一 scope 下的 delivered prediction 及其 prediction／receipt／horizon／cost／label／return identity，且 `source_completeness_status=verified`、source bytes／mtime／hash 在讀取期間未變，通過後才建立 writer 並追加既有 Journal revision。

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -X utf8 -m scripts.record_personalization_action `
  --scope-id <SCOPE_ID> --result-id <RESULT_ID> --stock-code <STOCK_CODE> `
  --action accepted --decision-kind recommendation_response `
  --request-id <NEW_REQUEST_ID> --actor user:<NAME> `
  --note "<研究備註>" --as-of YYYY-MM-DD `
  --output-root <OUTPUT_ROOT> --evidence-db <EVIDENCE_DB>
```

`--action` 可用 `accepted`、`skipped`、`note`、`review_scheduled`；`--action-at` 省略時使用本次命令的實際 UTC clock，`--recorded-at` 省略時由 recorder 使用本次實際 UTC clock。action 不代表下單或 broker execution。相同 request id 的 exact retry 會保留原始 action clock、lineage 與 revision；同一 request 若改 action、note、actor 或 identity 會 fail closed。preflight 顯示 `population_only`、`not_delivered`、scope／receipt／identity conflict 或 source invalidated 時，命令 exit 2 且不建立 Journal writer；不會自動建立 scope、把 delivery 當成人的 action，或 retrofit 舊的未帶 personal envelope action。

### 明示產生、保存並送達新的 personal recommendation

若目前沒有任何 scope-linked prediction，先用 `scripts\run_personalization_recommendation.py` 走 producer chain。這個入口要求 caller 明示 data/output/config、result identity、scope type/id 與 delivery/request identity；六個 producer execution clock（其中五個透過 scope／receipt 欄位呈現）由實際 `RecommendationService.execute_recommendation` 同次 sealed execution/postprocess capture 與 durable projection receipt 產生，CLI clock 參數只作可選 assertion，與 producer 不一致即 fail closed。自然模式會要求 producer 從實際來源選取 `producer_selected_latest_available_cutoff`；`--as-of-date` 只是對該實際 cutoff 的 exact assertion，不能把 caller 指定的舊 cutoff重新標成自然模式。要明確重播舊 cutoff，必須加 `--historical-research`，結果會隔離為 `historical_research_not_as_if_available`。同次 callback 產生的 typed capture event 隨 execution codec roundtrip 後，由 canonical create-only writer 保存；exact-ID readback 驗證 result ID、payload hash、integrity basis 與 generated capture identity 後，CLI 才以既有 Journal CAS writer 追加 technical delivery ACK。ACK 與 execution 保存分離，不進 execution payload/hash。producer 沒有 durable projection receipt 或 temporal anchor 時會 fail closed，不會保存或 ACK。

相同 `result_id`／payload hash 的 canonical retry 讀取既有 execution，不重跑 producer、不重寫 artifact；不同 request identity、config、scope、receipt 或 hash 會 fail closed。artifact 已存在但 SQLite index 缺列時，CLI 只透過 R012 opaque-ID `store.read_artifact()` 讀取，嚴格驗證 execution envelope、identity、payload hash 後呼叫同一 create-only writer 修復 index；一般 exact query 對未索引 artifact 仍 fail closed。既有 legacy personal JSON 僅由 legacy 唯讀 decoder 讀取與重試送達 ACK，CLI 不重解碼或寫回 JSON。

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -X utf8 -m scripts.run_personalization_recommendation `
  --data-root <DATA_ROOT> --output-root <OUTPUT_ROOT> `
  --config-json <STRATEGY_CONFIG_JSON> --result-id <NEW_RESULT_ID> `
  --result-name "<結果名稱>" --as-of-date YYYY-MM-DD `
  --scope-id <SCOPE_ID> --scope-type local --delivery-id <DELIVERY_ID> `
  --request-id <DELIVERY_REQUEST_ID> --profile test `
  --evidence-db <EVIDENCE_DB>
```

`--profile test` 將 QA 輸出隔離到 test root；實際輸出仍要指定新的 `--output-root`。`--declared-at`、`--decision-at`、`--available-at`、`--captured-at`、`--receipt-created-at` 都是可選的 aware ISO assertion；省略時以 producer 實際 clock 為準，若提供則必須與保存 context 完全相同。六個 producer clock 須依 `run_started_at ≤ scope_declared_at ≤ available_at ≤ captured_at ≤ decision_at ≤ receipt_created_at` 排序，尤其 `available_at ≤ decision_at`；任一缺值、逆序或 assertion 不同都會 fail closed。`--delivery-at`／`--ack-recorded-at` 省略時使用 append 後的實際 UTC clock；重試會沿用既有 ACK 的 persisted／delivered clocks。CLI 的 `generated_capture_hashes` 是 execution 內封存的原始 capture hash；`persisted_capture_hashes` 與 `delivered_capture_hashes` 是含 lifecycle status／timestamp 的派生 capture hashes，不能用來取代原 hash或推斷 execution bytes 已改變。producer context 的 `decision_at` 只代表 `prediction_decision_at`，不會被 ACK 或人工作答時間覆寫；後續 action 的 `human_decision_at` 由最後一筆 recorded revision 的 `action_at` 決定。`--as-of-date` 是市場資料 cutoff，不要求等於 runtime `decision_at`；合法的 T-1 cutoff 可以在下一個台北市場日執行，但 cutoff 不得晚於 producer 的 available market date。日期型欄位與成熟度判定採 `Asia/Taipei`，不得以 UTC 日期手動替代。自然 producer 依實際來源的最新可得 row 決定 cutoff，不用日期差／星期幾猜 session；若 caller 提供的 `--as-of-date` 與 producer 選出的 cutoff 不同，命令會在 save 前 fail closed。只有明確指定 `--historical-research` 才能使用舊 cutoff，並標記 `historical_research_not_as_if_available`，不能把歷史重播冒充自然可得的即時決策。這條命令只保存 research prediction 與 technical ACK，不建立 human action、不建立 order、不改寫 receipt body；成功後再以本節上方的 action command 明示 `accepted`／`skipped`／`note`／`review_scheduled`。正式 D 槽使用前應先以隔離 output root 做 bounded QA，不能拿 scheduled population-only 結果當作新 personal delivery。

若報告顯示 `population_only`、`scope_missing`、`not_delivered`、`pending_maturity`、`matured_missing`、`source_consistency_invalidated` 或 `fit_artifact_missing`，保留原診斷並核對 source fingerprint；不要手動補 scope、label、outcome、action 或把 fixture／Paper／user-declared context 當作 natural user evidence。正式資料檢視的 command、hash、分母與實際 pending 結果見 [Personalization 唯讀來源 QA](../06_qa/PERSONALIZATION_READONLY_SOURCE_QA_2026_09_16.md)。

## 2026-09-09 官方基本面現況資料

持倉／觀察清單開啟「個股研究報告」，基本面頁會列出已實際取得的最新月營收；來源標示「官方基本面現況快照（非歷史公告證據）」。金額為 TWD 元，MOPS 千元在讀取／匯入邊界轉換。新月份還在公告時，不同股票最新月份可能不同，不能以其他股票已有公告推定本股缺漏。

更新頁另保留歷史 PIT 最新期別。現況快照已入庫不代表取得原始公告歷程；明確指定歷史 as-of 日期時不讀取現況快照。沒有公司公告日期時不猜日期、不填零，也不拿此快照回補 ML 歷史特徵。

月營收維護入口：先用 `scripts/fetch_mops_monthly_revenue_snapshot.py --start-period YYYY-MM --end-period YYYY-MM --output-dir <任務輸出>` 取得官方 CSV，再用 `scripts/apply_current_monthly_snapshot.py --snapshot <CSV> --db-file <TWStockConfig.db_file> --backup-dir <C槽備份目錄> --lock-path <OUTPUT_ROOT>/release_v4/.ml_heavy_chain.lock --evidence-file <驗收JSON>` 預覽。加入 `--apply` 才會備份並增量寫入；D 槽須保留 200 GiB，鎖忙或備份驗證失敗會停止。不要手動刪除鎖或改用另一個資料根目錄繞過。

資料已入庫但畫面仍舊時，重新整理更新頁並重新開啟個股報告；確認使用的 `DATA_ROOT` 與匯入的 SQLite 相同。公告日期、可得日期與報告期別是不同欄位。

本次其他資料的維護工具：法人／信用為 `scripts/complete_institutional_credit_flows.py capture` 與受控 `apply`；集保為 `scripts/capture_tdcc_shareholding_candidate.py` 和 `scripts/apply_tdcc_shareholding_candidate.py`；季報為 `scripts/build_current_statement_snapshot_candidate.py` 和 `scripts/apply_current_statement_snapshot.py`。每次使用新的任務輸出子目錄保存來源與驗收，不覆蓋已採用的manifest。所有正式套用前須取得共用更新鎖、核對容量並建立SQLite線上備份；不要只複製DB主檔而遺漏WAL。

原有UI「候選更新」按鈕仍操作Phase3C隔離候選庫，**不會自動套用上述新來源到正式庫**。每日quick排程在明確設定 `PHASE3C_CANDIDATE_DB_PATH` 時會執行 institutional／credit（週一加最新TDCC）候選更新；未設定時會在status明示 skipped，不猜測路徑。月營收、季報與集保的正式套用仍須使用各自受控CLI，不能把下次按候選更新誤認為正式資料已刷新。集保正式表的 `observed_at` 等價保存本次來源 `first_observed_at`／`available_at`，完整17級仍在 `shareholding_tiers`。

## 2026-09-10 V4 唯讀有效性與跨日證據

V4 cohort 有效性檢查使用 `scripts/inspect_v4_effectiveness.py`。它可讀 JSON array、含 `rows` 的 JSON object 或 JSONL，依 horizon／strategy version／strategy config／穩定 universe policy／cost model／benchmark／return basis／evidence tier 分組，並對每個決策日獨立計算 Precision@K。只有 `ready` outcome 進成熟分母；`pending`、`missing`、未知狀態、缺 score／return 與衝突重複列會保守排除並留下 warning。輸出比例與 coverage 是整數 basis points，固定唯讀、需人工覆盤、不啟用 scheduler、不下單。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_v4_effectiveness.py --sample --format markdown
.\.venv\Scripts\python.exe scripts\inspect_v4_effectiveness.py --input <EVIDENCE_JSON_OR_JSONL> --format json --output <REPORT_JSON>
.\.venv\Scripts\python.exe scripts\inspect_v4_effectiveness.py --db-path <EVIDENCE_SQLITE> --window-days 5 --format markdown
```

`--db-path` 使用 SQLite `mode=ro`／`PRAGMA query_only` 讀取既有 `evidence_events` 與
`evidence_outcomes`；新版事件 metadata 必須同時保存 `universe_policy_id/hash` 與
`universe_snapshot_id/hash`，缺件會保留警告並維持 fail-closed，不以目前股票池或 symbol
推測補值。沒有新版 schema 標記的舊 bare `universe_id` 只以 legacy 相容方式讀取，不宣稱
符合新版跨日契約。指定 `--window-days` 時，沒有該窗口 outcome 的事件仍會
以 `missing` 保留；查詢只納入 `close_to_close_event_date`（可用 `--return-basis` 明確改變），
避免不同計算口徑重複計算。事件只有明確保存 `horizon_days` 才能在缺件時形成有效 horizon，
否則報告會留下缺 horizon warning。大量相同 row-level 缺口會以
`rows_<code>:<count>` 彙總，保留原因與數量但不讓報告被重複訊息淹沒。
cohort identity 只接受純量文字；list／mapping／bool 形式會以
`rows_incomplete_cohort_identity` fail-closed。

新的推薦 snapshot 會在服務實際選完處理股票後保存穩定的
`recommendation-universe-policy.v1` `universe_policy_id/hash`，以及保存決策日與實際成分的
`recommendation-universe-snapshot.v1` `universe_snapshot_id/hash`；舊 `universe_id/hash`
只保留為每日 snapshot alias。策略重要設定另由 `strategy_config_id/hash` 綁定。每日排程固定宣告
`strategy_version_id=scheduled-recommendation-default-v1`、
`cost_model_id=gross-close-to-close-no-cost-v1`、`benchmark_id=TAIEX` 與
`horizon_days=20`。20 是主要 cohort 標籤，不是持有保證；no-cost model 表示尚未扣除
手續費、稅費、滑價或流動性成本，報告會留下 `cost_model_not_cost_adjusted` 警告。
Evidence importer 只讀取結果 config／run context 明確提供的策略、成本、benchmark、
policy／snapshot universe 與 horizon，缺欄位就保持缺件，不從 profile、symbol 或目前股票池猜值；這項接線
不回填舊事件，也不把新 snapshot 自動標成成熟或正式績效。

每日 forward receipt 的 `health` 顯示最新合格事件日、完整身份事件數、cohort／決策日數、
各 horizon 的 ready／pending／missing、最近 capture／outcome／evaluation、下一成熟日、
冪等自然鍵與 blocker。分類包括 `normal_completion`、`normal_no_new_outcomes`、
`waiting_for_natural_maturity`、`actionable_engineering_blocker` 與
`external_source_missing`；UI 的「排程狀態」只讀呈現這些資訊。`tests/test_v4_cross_day_evidence_contract.py`
是隔離端到端接線驗收，通過只證明工程資料流，不增加 V4／Formal／alpha 信用。

每日 progress readback 位於
`<OUTPUT_ROOT>/scheduled/evidence_progress/latest_status.json`，immutable run 位於同目錄
`runs/<run_id>.json`。它只投影 forward receipt 的當日／當週 capture、5／10／20／60
maturity、blocker、warning 與 next action；同一 `run_id` 重試保持 run receipt 不變。
連續兩個應有資料工作日沒有新 capture 時，`no_new_data_alert.alert=true`，UI 會顯示告警；
週末或 freshness receipt 已驗證的官方休市日則為 `suppressed_non_trading_day`。官方 calendar
未知時不猜成休市，會保留 expected-day 觀測並留下 warning。此 readback 不回填歷史、不補未來價格，
也不寫 evidence DB、Paper ledger 或券商狀態。

FinMind 現金流只作交叉核對候選：

```powershell
.\.venv\Scripts\python.exe scripts\fetch_finmind_cashflow_candidate.py `
  --start-date YYYY-MM-DD --end-date YYYY-MM-DD --stock-code 2330 `
  --output-dir <任務輸出> --fetch-date YYYY-MM-DD --observed-at <ISO8601>
```

批次需明確指定股票；只有要從既有 raw 目錄批次續跑時才使用 `--all-raw-stock-codes --resume`。輸出保存 `source_row_hash`、`observed_at`、科目與數值，`eligibility=numeric_only` 且 `available_date_candidate` 留白。FinMind row 沒有可驗證的官方公告／可得日，不能用於 PIT、ML 歷史特徵或正式 scoring；正式季度資料仍以 MOPS 受控候選與 availability evidence 為準。命令只寫任務輸出，不寫正式 SQLite。

SQLite 相關正式變更前，備份與還原均使用線上備份及 `PRAGMA quick_check`；每日quick更新先取得 `OUTPUT_ROOT/release_v4/.ml_heavy_chain.lock` 並通過容量預檢，鎖忙或低於200 GiB保留量即停止。完整契約與驗收見 [V4 有效性與資料來源工程驗收](../06_qa/V4_EFFECTIVENESS_READ_MODEL_2026_09_08.md)。

## 2026-09-07 月營收恢復與衍生 ML 操作入口

- 季報隔離讀回使用 `scripts/materialize_mops_statement_candidates.py --candidate <財報候選JSON> --db-path <新隔離SQLite> --decision-date YYYY-MM-DD --evidence-output <新證據JSON>`；`--candidate` 與 `--decision-date` 可重複指定，以比較多家公司及可得日前後。資料庫限 TEMP 或專案 `output`，拒絕正式 DATA_ROOT、其別名及沒有 research-only 標記的既有DB；證據檔不得與輸入、DB、標記檔重疊，且必須使用新檔名。成功時核對主表／sidecar筆數與各決策日讀回筆數；同批重跑使用原隔離DB及新的證據檔，應新增0筆。EPS保留元／股、損益單季與現金流累計期間另存sidecar；不要只讀數值而忽略單位與期間。此入口不接受未驗證科目代碼或不完整可得時間，也不會更新正式資料；路徑衝突時更換研究輸出位置，不移除來源或DB標記來繞過檢查。
- 月營收使用 `scripts/apply_monthly_revenue_recovery.py`，提供 `--candidate-mapping`、`--snapshot-file`、`--target-mapping`、`--db-file`、`--backup-dir`、`--evidence-file` 與 `--source-version`。預設只輸出預演；`--format json` 可取得筆數與阻擋原因。部分接受另提供 `--scope-manifest`，必須綁定完整候選、接受子集、排除鍵及內容雜湊，不能用接受筆數取代完整分母。
- 已有目標寫入授權時，套用旗標為 `--apply --confirm apply-monthly-revenue-recovery`；這是防誤用參數，不要求額外人名審核。命令使用任務備份、SQLite 交易與恢復紀錄；省略 `--journal-file` 時使用 evidence 路徑加 `.journal.json`。同批重跑前保留原始輸入與紀錄；資料已提交而證據寫入失敗時，先核對 journal 狀態，不手動整檔還原 DB。不同批次或目標不得借用前次備份。正式 D 槽套用目前另受執行環境核准拒絕限制，尚未完成。
- 衍生 ML 使用 `scripts/build_ml_allocation_derived_release.py --parent-training-manifest <父訓練manifest> --output-root <新輸出目錄> --preflight-only` 先查來源與雙磁碟容量；移除 `--preflight-only` 才執行。輸出目錄須為空，預設 h5、4個選定fold、4096 MB記憶體、持久及暫存各1 GiB、磁碟保留200 GiB。實際執行持有共用重型流程鎖；配額不足或來源不完整時，修正原因後使用新的輸出目錄，不覆寫既有發布。
- 本輪真實衍生模型約4.19 MB；`release_manifest.json` 綁定模型、前處理與校準器，`derived_training_manifest.json` 保存父版本及選取來源，`heldout_evaluation.json` 保存歷史重播結果。成功產出代表模型交付路徑可用，尚不代表自然日觀察、成本後優勢或正式ML獲准；目前alpha仍0。完整證據見[ML交付紀錄](../06_qa/V4_ML_RELEASE_2026_09_07.md)與[資料恢復紀錄](../06_qa/V4_DATA_RECOVERY_2026_09_07.md)。
- v3 research readback 若原始 TEMP input 可能被清理，先用 `scripts\build_ml_allocation_v3_readback_bundle.py --v3-input <FROZEN_V3_INPUT> --release-root <V3_RELEASE> --output-root <OUTPUT>\readback_bundle` 建立小型內容定址 bundle；同一批重跑會重用 SHA-256 object。之後以 `scripts\audit_ml_allocation_v3_linear_release.py --release-root <V3_RELEASE> --readback-bundle <BUNDLE_MANIFEST> --output <AUDIT_JSON> --readback-output <READBACK_JSON>` 執行只讀 load/infer。bundle 只保存 frozen input、release manifest 與不含 capacity/TEMP path 的 training lineage，不複製 D 槽 Direct/PIT/SQLite；輸出路徑不得覆蓋 release、bundle 或 input，所有 formal／alpha／broker 權限仍關閉。
- 跨 run immutable block QA 使用 `scripts\qa_ml_immutable_block_reuse_sample.py --bundle-manifest <READBACK_BUNDLE_MANIFEST> --output-root <NEW_OUTPUT>\immutable_block_reuse_sample`；它以 source／feature／label／maturity／時間範圍／schema key 綁定 content hash，示範兩個 run reference 共用一個 object。這個 generic sample 是研究與容量驗證入口；PIT、Direct 與 OOC 的實際 shared reader 另依下列入口執行。registry 不搬移 D 槽、不訓練，輸出必須位於新的 repo `output` 目錄。
- OOC model／OOF／Meta 跨 run reuse 使用 `scripts\train_ml_allocation_out_of_core.py --shared-artifact-store <NEW_OUTPUT>\shared_artifacts`。同一 request 可在不同 output root 各執行一次；第二次會依完整 semantic key 直接讀 immutable registry，run-local 只保存 manifest／reference，不複製 payload。key 綁定 Direct store／dataset／source lineage、feature／label contract、train／test／calibration split、maturity、model parameters、training／rank／family policy、implementation version 與分離的 base／meta／calibrator namespace；fold、pack、lane、校準 withheld rows 或任一依賴改變都會 miss，bytes／descriptor tamper 或同 key 綁定不同 manifest 會 fail closed。先以 `scripts\qa_ml_direct_ooc_shared_reuse.py report --ooc-manifest <FIRST_MANIFEST> --ooc-second-manifest <SECOND_MANIFEST> --ooc-shared-artifact-store <SHARED_ARTIFACT_STORE>` 驗證完整性。這是 bounded research／容量入口，必須使用 shared store canonical lock；目前 calibration 仍 diagnostic-only，`formal_oos_allowed=false`、alpha 0、`broker_order_allowed=false`，不代表 promotion 或績效。完整實跑證據見[immutable block QA](../06_qa/V4_ML_IMMUTABLE_BLOCK_REUSE_2026_09_07.md)；舊 local manifest 沒有 shared reference 時仍由原 reader 驗證。
- Raw／Direct／OOC heavy CLI 的 reservation 由同一個 `release_v4/.ml_heavy_chain.lock` 維持。child handoff 是 owner sidecar 綁定的隨機 nonce、canonical lock path、owner／parent PID 與已登記 child PID；child 進入 writer 前還必須持有 canonical lock 旁獨立的 OS handoff gate。新 chain 即使在 owner OS lock 釋放後取得 canonical lock，也會以 live custody 與同目錄 gate 的實際 lock probe fail closed；因此不可只依賴可遺失的 sidecar。請勿自行設定或保留 `BALDR_ML_HEAVY_CHAIN_RESERVATION_HELD=1`，舊 marker 會被拒絕。scheduled wrapper 會在 `Popen` 後登記 child，Windows launcher 中介 PID 也需通過相同 custody；owner／parent 結束後 watchdog 會停止 child。所有 scheduled heavy CLI 仍至少保留 200 GiB，raw／Direct 的 35 GiB persistent 加 40 GiB temporary 另需 275 GiB headroom；低 reserve 參數應在 preflight 階段 fail closed。
- Direct checkpoint provenance 只讀核對使用 `scripts\inspect_ml_direct_checkpoint_provenance.py --store-root <DIRECT_STORE_ROOT>`。工具先保存每個 checkpoint／manifest 的 bytes SHA-256，再區分 `legacy_missing_computation_provenance`、`computation_identity_drift`、snapshot／manifest corruption 與可供 owner review 的 current identity；`checkpoint_provenance_valid` 不等於完整 `resume_allowed`。已存在的 manifest 若損壞、被竄改或 identity 不符會阻擋完整恢復；未完成 checkpoint 尚未有 manifest 才可按 in-progress 語意檢查。穩定 computation identity 只綁定明確 dependency source bytes 與 compiled source fingerprint，不使用 loaded-module／runtime constants 整包 hash。Legacy checkpoint 不可貼上目前 hash 冒充原始 custody；完整 legacy artifact 保留 audit-only，後續須經 owner review、無 active heavy chain、容量 preflight 後以新的 run identity 建立 Direct。此入口不寫 checkpoint、manifest、pointer、正式 SQLite 或 D 槽資料。
- Inspector 可加 `--maintenance-output-dir <OOC_TRAINING_OUTPUT_DIR>` 讀取 canonical lock、maintenance lock、handoff gate 與 matching process custody。工具以 `rb` 開啟既有 lock 檔後做一個 byte 的 advisory-lock probe，再保留 `probe_stage`、`errno`／`winerror`、bytes before/after 與 unlock 結果；read-only open 被拒時只能標為 `inspection_permission_unknown`，不可解讀為 holder、stale 或可刪除；若 before／after bytes 不一致則 aggregate 為 `probe_file_changed`，handoff gate enumeration 失敗則為 `handoff_gate_enumeration_incomplete`，兩者不能降級成 `no_active_lock_observed`；`free_observed` 只代表該瞬間未觀察到 holder，正式 execution 仍必須由 canonical owner protocol 原子取得 reservation。
- Direct fresh-run recovery 的 staging output 必須與舊 `portfolio_ml_direct_numeric_production_v4_v2` 分離；先以 `--no-resume` 建立新 run，再用 inspector 核對 stable identity、checkpoint／manifest／raw／year／fold hash 與容量。OOC handoff 會再次驗證 Direct manifest 與 checkpoint 的 current identity、dependency/runtime custody 及彼此一致，所有 readback 通過前不得替換舊 pointer；目前正式 D 的 lock/process custody 或 formal input 不完整時，維持 blocked，不啟動 heavy chain。
- PIT shard shared reuse 使用 `scripts\build_ml_pit_shared_block_publication.py --dataset-manifest <EXISTING_PIT_DATASET_MANIFEST> --shared-store <NEW_OUTPUT>\registry --output-dir <NEW_OUTPUT>\publication`；命令只讀既有 `ml-pit-year-shard-dataset.v1` 與 parent manifest，逐 shard 驗證 compressed/content SHA 後產生相對 immutable reference，不複製 shard 回 run-local。shared store 只能使用其 canonical `.ml_immutable_block_store.lock`，輸出不得與來源或 registry 重疊；舊 local `path` manifest 仍由 resolver 驗證。這是 research/QA 接線，`production_action_allowed=false`、alpha 0，未改寫 PIT、Direct、OOC 或 D 槽來源。完整範例與真實小樣本結果見[immutable block QA](../06_qa/V4_ML_IMMUTABLE_BLOCK_REUSE_2026_09_07.md)。
- Direct 全現金 target 根因可用 `scripts\diagnose_ml_allocation_target_degeneracy.py --manifest <DIRECT_MANIFEST> --output <REPO_OUTPUT> --chunk-rows 65536` 做唯讀 bounded 掃描；`--year YYYY` 可限制診斷範圍。報告會分開列出 target、horizon label、maturity、PIT sector、price／volume／Rule source 與 assembly blockers，輸出不得位於 immutable run 內。`data_blocked_no_eligible_sector_candidates` 只表示 PIT eligibility 缺件造成 teacher fail closed；`strategy_or_policy_cash_only_with_candidates` 才表示已有候選時策略仍選 cash，兩者都不解除 formal／alpha／promotion gate。修復只能走未來正式 PIT、causal non-cash ledger 與 Rule history handoff，不以零值回填歷史 target。
- Allocation OOC 訓練會在任何 output、shared artifact 或模型 fit 前執行 `allocation-teacher-eligibility-gate.v1`；它只掃描整數 target 與當時保存的 candidate provenance，不讀成熟後 label。缺 PIT sector、causal non-cash ledger、formal Rule history、UNKNOWN sector 或 incomplete counters 時命令會 fail closed，不能把全 cash fallback 當有效 teacher；完整候選下的全 cash 只可標為策略研究，仍固定 formal OOS／alpha／broker 關閉。若要做不依賴 teacher 的 outcome research，使用 `allocation_base_expert_comparison.py`，不可用這條 gate bypass。
- h20 label 極值的唯讀來源核對使用 `scripts\audit_ml_allocation_label_extreme.py --manifest <DIRECT_MANIFEST> --source-db <READONLY_SQLITE> --raw-shard <PIT_SHARD> --corporate-action-manifest <OFFICIAL_EVENTS> --output <REPO_OUTPUT>`；工具以 chunked memmap 找最大列、以 Decimal 重算股票／benchmark／成本並核對官方公司行動，輸出不得覆蓋任何來源。`source_price_scale_anomaly_unresolved` 只代表來源需追查，不可截斷、補值、重訓或據此宣稱績效有效。
- 官方 daily-price 的事後研究使用 `scripts\consume_ml_daily_price_overlay.py --overlay <OFFICIAL_OVERLAY> --sqlite <READONLY_SQLITE> --output <REPO_OUTPUT>\impact_v2.json --research-mode post_capture_historical_research.v2` 做事後研究。v2 將同日 OHLC／成交量放在 `raw_price_diagnostic`，盤前 model input 僅取決策日前一交易日及其前一收盤；找不到兩個先前 session 或嘗試使用同日／晚到欄位時 fail closed。它不改 SQLite／PIT／label、不訓練、不解除 alpha 或 promotion；完成後可用 `scripts\audit_ml_daily_price_overlay_impact.py --impact <IMPACT_V2> --output <REPO_OUTPUT>\decimal_audit.json` 以 Decimal 重算 entry、exit、benchmark 與 25+55 bp 成本。每日整合 writer `scripts\merge_daily_data.py` 會在讀檔前驗證日期檔名／檔內日期，成功後保存 `stock_data_whole.csv.source.json` 內容 receipt；來源不一致時不可退回 stale aggregate。
- 若要讓官方 overlay 真的進入既有 research label pipeline，使用 `scripts\replay_ml_daily_price_overlay_labels.py --overlay <OFFICIAL_OVERLAY> --sqlite <READONLY_SQLITE> --reference-impact <IMPACT_V2> --output <REPO_OUTPUT>\research_label_replay.json`。此命令在隔離記憶體 spool 呼叫既有 `PortfolioMLDatasetAssembler._build_label_spool`，同時保存原始／corrected labels 與逐列 source hash、capture `available_at`／`observed_at`；官方同日資料只可作事後 supervised label，盤前 feature 仍取前一交易日。它會逐 symbol／逐 head 對 reference impact 做一致性核對，並固定 `research_only=true`、`formal_training_allowed=false`、`promotion_eligible=false`；不回寫 SQLite、PIT、training shard，也不重訓模型。
- 要核對 overlay 與既有 ResearchShadowUnion、shared PIT、Direct rows 的實際交集，使用 `scripts\build_ml_research_shadow_overlay_direct_readback.py --overlay <OFFICIAL_OVERLAY> --label-replay <RESEARCH_LABEL_REPLAY> --research-union-manifest <RESEARCH_UNION_MANIFEST> --pit-manifest <SHARED_PIT_MANIFEST> --pit-shared-store <PIT_REGISTRY> --direct-manifest <DIRECT_MANIFEST> --output <REPO_OUTPUT>\overlay_pit_direct_readback.json`。入口只串流驗證 manifest／object／rows hash 並保存 33 筆逐 head label diff；日期或股票池交集不足會標為 `completed_partial_research_shadow_overlay_pit_direct_readback`，不補值、不把 late capture 當歷史盤前資料，所有 formal／alpha／broker 權限仍關閉。輸出不可位於任何來源、registry 或 immutable run 內；完整實跑 identity 與限制見[Research shadow readback QA](../06_qa/V4_ML_RESEARCH_SHADOW_INTEGRATION_2026_09_07.md)。

## 2026-08-15 prospective-only formal simulation（PFS-07）

Owner 已選擇「正式、但 prospective-only 的非實盤模擬持倉 clock」。既有
`2014–2026` Direct／OOC 與 research artifacts 只保留 history，不回填成 Formal
evidence；目前 `formal_oos_allowed=false`、production alpha=`0`、broker disabled。

PFS-07 的 activation contract 已可用於受控 fixture preflight：

- `scripts\publish_prospective_formal_clock.py --fixture-only` 可把 owner 已核准、仍在未來的 activation trading day 與官方 calendar evidence 寫成 planned clock manifest。呼叫端必須明確提供 clock／owner decision、cash seed、strategy／policy／universe／source identities、frozen candidate training cutoff、calibration／evaluation hashes 與 `--now`；命令不會自行選日期、查找或回填歷史、設定任何 `BALDR_ML_*` path、讀取 HMAC secret 或啟動 watcher。輸出 parent 必須先存在，manifest 採 canonical JSON create-only。
- `scripts\plan_prospective_formal_clock.py` 是新的唯讀日期 preflight。它只接受呼叫端提供的 `official-trading-calendar-bundle.v1`（每個候選日同時含 TWSE／TPEX `is_trading_day`、官方 `source` 與 `sha256:` response hash），以帶時區的 `--now`、owner decision timestamp、至少一個準備日與 lookahead window 選出第一個尚未使用的共同交易日。輸出是 `candidate_ready` proposal，不是 clock manifest；不下載日曆、不採用 same-day override、不自動切換 `BALDR_ML_*` path、不寫正式資料。選不到合格日期時回 `blocked`，不猜日期。
- `scripts\capture_official_calendar_bundle.py` 可將已由官方 TWSE 年度 `holidaySchedule` 與 TPEX 月度 `mktCalendar` 取得的 raw JSON 正規化成上述 bundle；fixture 可重複指定，缺少的年度／月份只有在明確加上 `--confirm-network` 時才各發一次 bounded GET。輸出只能寫入作業系統 TEMP 且 create-only，artifact 永遠標示 `candidate_only=true`、`formal_clock_created=false`；它不寫市場 SQLite、不改 `BALDR_ML_*` path，也不會自動建立或啟動 clock。TPEX 缺少平日明確 row、TWSE／TPEX 年月不符或回應格式錯誤時均 fail closed。
- `scripts\activate_prospective_formal_clock.py --fixture-only` 在 strict 模式只於三個 PFS-06 input 都 ready、candidate／calibration／evaluation identities 與 file hashes 都一致、owner activation timestamp 已發生、activation trading day 仍在未來時建立 create-only manifest。Owner handoff 可改用 `--fixture-only --controlled-environment`，由 shared Windows reader 取得三個 formal paths、非秘密 store identity 與 HMAC configured flag；此模式不讀／輸出 secret、不設定環境，缺件即 blocked。
- `scripts\record_prospective_daily_capture.py --fixture-only` 只建立低 CPU daily capture 的 `started` record，固定 PIT publication → Rule snapshot → T-1 Portfolio transition → frozen inference → heartbeat 順序；`elapsed_day_credit=0`、`formal_credit=0`，不能隔日補寫。
- `scripts\run_prospective_rule_only_decision.py` 只在實際台北 09:00–13:30 盤中，以 prospective clock owner acceptance、frozen universe 與 T-1 `daily_prices` 產生 TEMP owner-bound Rule source；它不寫 market DB、Recommendation、Portfolio、evidence ledger 或 broker，且 HMAC secret 只由受控 runtime 驗證，絕不輸出。
- `scripts\run_prospective_formal_activation_once.py` 是一次性低 CPU handoff：驗證 activation day 與 T-1、建立官方 PIT、publish Rule history、append simulated Portfolio，再於三份 input 都存在後寫 strict readiness。它拒絕既有 formal output、只 create/append、不註冊 continuous scheduler，不啟動 watcher、Direct/OOC、training、promotion 或 broker。若要執行，需由 owner 將 v3 clock、source custody、controlled store 與正式輸出父目錄以明確參數提供；任何缺件都 fail closed。

### Prospective Formal Restart：官方公司基本資料 PIT staging

Restart 第一階段的官方產業來源固定為 [TWSE `t187ap03_L`](https://openapi.twse.com.tw/v1/opendata/t187ap03_L)、[TPEX `t187ap03_O`](https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O)；只有 clock universe 明確含興櫃標的時才可加入 TPEX `t187ap03_R`。操作入口
`scripts\capture_prospective_official_pit_sector.py` 不會自行下載來源，必須由呼叫端提供每個 endpoint 的 raw JSON bytes、sorted symbol universe、license id／URL 與明確的 publication timestamp。它會驗證官方欄位、民國／西元出表日期、兩位數產業代碼、重複／缺列、raw／canonical hash、available／effective time 與 clock／universe lineage；任何不成立都 fail closed。這條路徑禁止 `companies.csv`、current snapshot、research output 與歷史回填。

activation 前的 source fixture 可用 `--preactivation-staging`，只產生標示為 `staged`、formal consumer 不可直接消費的 create-only package：

```powershell
.\.venv\Scripts\python.exe scripts\capture_prospective_official_pit_sector.py `
  --fixture-only --preactivation-staging `
  --clock-manifest <PLANNED_CLOCK> `
  --now <TAIPEI_NOW> `
  --decision-timestamp <FUTURE_DECISION_TIMESTAMP> `
  --available-at <SOURCE_AVAILABLE_AT> `
  --effective-from <CLOCK_ACTIVATION_DATE> `
  --symbols-json <SORTED_CLOCK_SYMBOLS_JSON> `
  --source-metadata-json <OFFICIAL_SOURCE_METADATA_JSON> `
  --twse-raw-json <TWSE_RAW_JSON> `
  --tpex-raw-json <TPEX_RAW_JSON> `
  --output <STAGING_PACKAGE>
```

clock 到達 activation day 後，移除 `--preactivation-staging` 才會把同一 producer 的 rows／registry 交給既有 `pit-sector-membership-prospective-manifest-v1` sidecar writer；輸出 parent 必須先存在且既有檔案不會覆寫。這個入口不註冊 scheduler；後續低 CPU daily capture 仍依 PIT publication → Rule snapshot → T−1 Portfolio transition → frozen inference 的既有順序，由 owner 在 strict readiness 全部通過後另行啟用。任何 readiness、calibration、shadow maturity、Formal OOS、promotion 或 broker gate 未通過時，仍固定 `formal_oos_allowed=false`、alpha=`0`、promotion=`false`、`broker_order_allowed=false`。

#### PIT membership reader 與 caller 判讀（2026-09-15）

PIT 產業 membership 是明確設定後才啟用的唯讀輸入。`TWStockConfig` 可用 constructor kw-only fields，或設定下列環境變數：`PIT_SECTOR_MEMBERSHIP_PATH`、`PIT_SECTOR_MEMBERSHIP_RAW_ROOT`、`PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH`、`PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH`、`PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH`、`PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH`、`PIT_MEMBERSHIP_EXPECTED_CLASSIFICATION_VERSION`、`PIT_MARKET_SCOPE`。未設定 `PIT_SECTOR_MEMBERSHIP_PATH` 時，服務不掃描資料根目錄，也不自動建立 reader。

設定 artifact 後，正常 composition root 會把同一個 read-only reader 注入 Industry Strength、Recommendation 與 non-UI Decision Desk。預設 PIT decision cutoff 是台北時間 08:30；指定 `PIT_MARKET_SCOPE` 時只消費該市場。reader 會重新驗證 raw bytes、source／clock／universe hash、available／effective interval、taxonomy source 與同日衝突；不同時區但同一決策 instant 會先轉為 Asia/Taipei 判斷。TWSE target classification 可使用 `official_twse_b1212_composite_rederived`：由 B12.00 base PDF、2023 產業變更公告、B12.13 B12.00–B12.12 歷程與現行法規頁四份 raw component 重算 33 碼，safe boundary 為 `2026-05-01`；B12.13 本身的 `115/12` 只作 target 後 history evidence，不直接作 target-date mapping。設定 composite 時四個 component 必須各自提供可讀 raw path 或官方 URL 加保存的 HTTP metadata，producer 會 custody component bytes／hash，並在 reparse 時驗證 lineage；不能只填一份 mapping 或把 current B12.13 直接 backdate。TPEx V12.18 仍須提供相符的 official applicability evidence。分類 PDF 的 `effective_from` 必須是官方分類／附錄適用日，並伴隨 `effective_date_basis`／`effective_date_evidence`；HTTP `captured_at`、`Date`、`Last-Modified` 與文件頁更新日只代表可取得／傳輸，不可回填適用日。adapter 會先核對 PDF 封面 current revision，再核對該版實施紀錄；未知 current revision 只可 research-only parse，不能進 `industry_filter_usable`。履歷只有月份精度時，該月仍視為 unknown，至少到次月 1 日才可作 no-early-use 判定。

結果判讀時，membership `usable` 與 `industry_filter_usable` 必須分開看：前者只表示 membership custody 可讀，後者還要求已驗證且版本明確的 taxonomy、完整分母與 common-equity security identity。缺 taxonomy、未知 classification version／產業代碼、部分分母、特殊證券、future available time 或 hash mismatch 時，Recommendation／Industry 不回退 `companies.csv`，而是顯示缺證據並停止該產業篩選。machine publication 固定是 `candidate_only`，不會升格成 accepted。

這條路徑只支援 prospective accepted read model，不代表 historical backfill、Formal OOS、promotion、broker 或 real-money eligibility。現有 D 槽 artifact 的 raw custody 雖可重驗，但因 score-bearing universe identity 與 taxonomy source 缺件仍為 unavailable；完整驗收與限制見 [PIT 產業來源與 caller 驗收 QA](../06_qa/PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md)。

### 先預約 clock，再於未來累積正式輸入

prospective-only 的三份輸入在 activation 前尚不存在是合法狀態；若 strict readiness
現在就要求 `non_cash_state_day_count>0`，會形成「沒有 activation 就不能有
transition、沒有 transition 就不能 activation」的循環。因此可先用明確的 staging
模式預約未來 clock：

日期 preflight 先用獨立的官方日曆 bundle 選出候選日（只產生 proposal）：

```powershell
.\.venv\Scripts\python.exe scripts\plan_prospective_formal_clock.py `
  --now <TAIPEI_NOW> `
  --owner-decision-timestamp <OWNER_DECISION_TIMESTAMP> `
  --calendar-evidence <OFFICIAL_TWSE_TPEX_CALENDAR_BUNDLE> `
  --minimum-preparation-days 1 `
  --lookahead-days 31 `
  --existing-clock-id <ELAPSED_CLOCK_ID> `
  --output <PLANNING_PROPOSAL_JSON>
```

Bundle 最小格式如下；`source_hash` 必須是保存過的官方 response bytes hash，不能填
文件 hash、猜測值或只給單一市場：

```json
{
  "schema_version": "official-trading-calendar-bundle.v1",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "twse": {"is_trading_day": true, "source": "TWSE ...", "source_hash": "sha256:<64 lowercase hex>"},
      "tpex": {"is_trading_day": true, "source": "TPEX ...", "source_hash": "sha256:<64 lowercase hex>"}
    }
  ]
}
```

若手上只有官方 raw 回應，可先用候選-only capture（命令不會自動連線）：

```powershell
.\.venv\Scripts\python.exe scripts\capture_official_calendar_bundle.py `
  --start-date <START_DATE> --end-date <END_DATE> `
  --twse-fixture <TWSE_ANNUAL_JSON> `
  --tpex-fixture <TPEX_MONTH_JSON> `
  --output <TEMP_CANDIDATE_BUNDLE_JSON>
```

若缺少某年度／月份，確認來源可用且允許 bounded GET 後才加上
`--confirm-network`；網路失敗不會建立半成品輸出。fixture／network 混合結果仍只
是日曆候選證據，必須先 owner review source hash，再交給日期 planner。

`candidate_ready` 只表示日期與日曆證據通過；仍須由 owner 審閱 proposal hash，接著
再以 `publish_prospective_formal_clock.py --fixture-only` 建立新的 planned clock。若
看到 `blocked`，應更新官方 bundle 或延長 lookahead；不得把已過 activation day 的
clock 改日期、重跑 one-shot、用 replay／fixture 補日，或以 proposal 直接供 Formal
consumer 使用。所有輸出固定 `formal_oos_allowed=false`、alpha=`0`、
`promotion_eligible=false`、`broker_order_allowed=false`。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_prospective_capture_readiness.py `
  --fixture-only --defer-until-activation `
  --clock-manifest <CLOCK_MANIFEST> `
  --calibration-policy <CALIBRATION_POLICY> `
  --decision-timestamp <FIRST_FUTURE_DECISION_TIMESTAMP> `
  --now <NOW> `
  --symbols-json <SORTED_SYMBOLS_JSON> `
  --output <DEFERRED_READINESS_OUTPUT>

.\.venv\Scripts\python.exe scripts\activate_prospective_formal_clock.py `
  --fixture-only --controlled-environment --defer-inputs `
  --clock-manifest <CLOCK_MANIFEST> `
  --calibration-policy <CALIBRATION_POLICY> `
  --readiness-report <DEFERRED_READINESS_OUTPUT> `
  --owner-activation-id <OWNER_ACTIVATION_ID> `
  --owner-activation-timestamp <OWNER_APPROVED_TIMESTAMP> `
  --now <NOW> `
  --output <ACTIVATION_MANIFEST>
```

`--defer-until-activation` 與 `--defer-inputs` 只建立「等待未來資料」的受控
activation manifest：三個 controlled path 會以 `deferred=true`／`path=null` 保存，
不會給 non-cash day、Formal OOS、promotion 或任何交易 credit；controlled store
identity 與 HMAC configured flag 仍必須存在，且 secret 永不輸出。clock 到達第一個
未來決策日後，owner 才設定三個正式 path，重新執行不帶 defer 的 strict readiness，
並只接受當日實際產生的 T-1 transition、Rule snapshot 與 PIT lineage；不可用歷史、
paper／cash-only ledger 或補日填入 deferred 期間。

### 唯讀 CPU／MCP process custody

若要判斷背景 CPU 或 MCP 是否重複，使用：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_runtime_process_custody.py --sample-seconds 1
```

預設只取樣 Python／MCP／ML 程序，輸出角色分組、PID、CPU／記憶體、duplicate MCP 與單核心 busy warning；`--all-processes` 才會擴大到其他程序。工具不輸出原始 command line、環境變數或 secret，也沒有停止／終止程序功能；`attention_required` 只是要求 owner 人工判讀，不是自動修復或 ML gate。

### 單一 execution-plan handoff

若要一次看完整個 prospective-only 專案目前卡在哪一層，以及下一步要執行的
安全命令，可使用唯讀 execution-plan inspector：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_prospective_execution_plan.py `
  --now <OWNER-SUPPLIED-ISO-TIMESTAMP>
```

它會把受控環境、clock、PFS-06 readiness、owner activation、daily capture、20
個自然 shadow trading days、frozen OOS／calibration／PSI 與 promotion review
列成八個階段，並輸出目前 blockers 與 owner actions。`--now` 必須由呼叫端明確
提供，repo 不會自行選 formal clock 日期；命令不寫三個正式 path、不建立 transition／
Rule／PIT artifact、不啟動 watcher／Direct／OOC，也不輸出 HMAC secret。若要保留
狀態快照，可另加已存在的 parent 與 create-only `--output <PLAN_JSON>`；重複路徑
會拒絕覆寫。

當三個 path 尚未存在時，`next_actions` 會明確列出
`--defer-until-activation` → `--defer-inputs` 的預約分流；這只讓未來 clock
可被 owner 受控排程，不會把缺件變成 ready，也不會啟動 heavy watcher。

2026-08-15 的目前結果是 `waiting_for_owner_inputs`：
`BALDR_ML_FORMAL_PORTFOLIO_LEDGER_PATH`、
`BALDR_ML_FORMAL_RULE_CHAMPION_HISTORY_PATH`、
`BALDR_ML_PIT_SECTOR_MEMBERSHIP_PATH` 尚未提供；controlled store identity 與
HMAC secret store 的 configured flag 已可見，但 `formal_oos_allowed=false`、
`heavy_rebuild_launch_allowed=false`、`promotion_eligible=false` 仍維持。

另外，legacy `scripts\maintain_ml_direct_v3_refresh_chain.py` 已加入 prospective
schema guard：若任一受控 path 宣告 `mode=prospective_formal_simulation`、
`scope=prospective_only` 或 `prospective-formal-*` schema，legacy one-shot 會回傳
blocked；`--watch-formal-inputs` 只低 CPU 等待，不會啟動 Direct/OOC。這個 guard
只記錄 schema／mode blocker，不輸出檔案路徑、環境值或 HMAC；prospective data
必須交給獨立 capture lane。

clock manifest 只是起算邊界與 identity custody，不會產生任何 transition。若 activation 已到達且 SQLite 內已有合法 prospective transitions，可先用
`scripts\publish_prospective_simulated_portfolio_ledger.py --fixture-only` 產生
`prospective-formal-simulated-portfolio-ledger-manifest.v1`。它會重新驗證 recursive
chain、T-1、non-cash day、clock identity、relative child path 與 SQLite file hash，並
以 create-only 寫入；不會設定 `BALDR_ML_FORMAL_PORTFOLIO_LEDGER_PATH`，也不會把
research／fixture ledger 升格成正式歷史證據。

Readiness 通過不等於 Formal OOS 或 promotion permission。完成 PFS-07 後，下一階段是只累積真實經過的交易日、PIT／Rule／Portfolio chain 與 matured outcomes；任何 Gate 失敗都維持 alpha=`0`。

Controlled activation 的命令仍需 owner 明確提供 clock、policy、readiness、activation id、
已發生的 owner activation timestamp、`--now` 與 create-only output；不會自行選 activation
trading day，也不會啟動 watcher／Direct／OOC：

```powershell
.\.venv\Scripts\python.exe scripts\activate_prospective_formal_clock.py `
  --fixture-only --controlled-environment `
  --clock-manifest <CLOCK_MANIFEST> `
  --calibration-policy <CALIBRATION_POLICY> `
  --readiness-report <READINESS_REPORT> `
  --owner-activation-id <OWNER_ACTIVATION_ID> `
  --owner-activation-timestamp <OWNER_APPROVED_TIMESTAMP> `
  --now <NOW> `
  --output <ACTIVATION_MANIFEST>
```

PFS-08 maturity inspector 可用於受控 fixture 的唯讀檢查：

- `scripts\capture_prospective_shadow_observation.py --fixture-only` 可把單日、已由 PIT／Rule／Portfolio／inference producers 產生的 lineage hashes 與已成熟 outcome rows 組成一筆 immutable observation；它只接受 activation 後日期與 T-1 input state，任何 future target、replay、backfill 或 unsafe flag 都由 PFS-08 validator 拒絕。
- `scripts\inspect_prospective_shadow_maturity.py --fixture-only` 讀取 activation-bound complete observations，只接受已發生的 decision／outcome timestamp、T-1 input 與 canonical hashes；缺少 5／10／20／60 horizon 時保持 waiting，不以 replay 或補日填入。
- maturity gate 固定要求至少 20 個 unique shadow days、每個 horizon 至少 20 個 matured observations，且 `rebalance_worthwhile` class 0／1 都是自然觀測；`future_teacher_target_used`、`same_day_advice_used`、replay、backfill 或 synthetic outcome 任一為 true 都會 fail-closed。
- 輸出 `maturity_gate_ready_shadow_only` 仍不解除 `formal_oos_allowed=false`、alpha=`0` 或 broker disabled。下一階段 PFS-09 才能對 frozen candidate 產出 matured Formal OOS replay、calibration 與 PSI evidence。

PFS-09 frozen-candidate evidence inspector 可用於受控 fixture 的 hash custody：

- `scripts\inspect_prospective_frozen_oos.py --fixture-only` 只讀 PFS-08 maturity report、primary／verification replay wrappers、inference calibration audit 與 integer-bp PSI report；兩個 replay 必須綁同一 frozen model／dataset／feature／policy identity，`result_identity_hash` 與 `replay_result_hash` 必須相同。
- 缺 primary／verification、maturity、calibration 或 PSI，或 quality／identity 不通過時，輸出 `waiting_for_frozen_oos_evidence` 與 blockers；不會呼叫現有重型 replay engine，不會 fit／retrain／事後選 calibration method。
- 即使輸出 `ready_for_formal_review`，仍固定 `formal_oos_allowed=false`、production alpha=`0`、promotion=`false`、broker disabled。PFS-10 才負責 promotion review 與人工／機器 Gate authority。

PFS-10 promotion review inspector 可用於受控 fixture 的最後 machine-gate aggregation：

- `scripts\inspect_prospective_promotion_review.py --fixture-only` 讀取 PFS-09 package 與 10 個 machine-gate 布林值；缺件或任一 false 都輸出 blockers，所有 true 時才輸出 `ready_for_owner_review`。
- `ready_for_owner_review` 不等於 promotion。review package 永久固定 `owner_review_required=true`、`owner_review_received=false`、`owner_authorization_received=false`、`promotion_eligible=false`、`formal_oos_allowed=false`、alpha=`0`、broker disabled。
- 這個命令不選 activation 日期、不設定 Windows path／secret、不啟動 watcher／Direct／OOC；下一步必須由 owner 在受控環境另行決定是否開始未來 clock。若要 retrain／recalibrate，先關閉本 clock，建立新 candidate 與新 clock。

### Activation handoff preflight

設定 owner-controlled paths 後，先執行：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_prospective_activation_environment.py
```

它只回報三個 formal path 的 configured／exists／file hash、controlled store 是否配置，
以及 HMAC secret store 的 configured 布林值；不會輸出 secret、不會設定環境、不會啟動
任何 ML 程序。若任一路徑缺失，狀態是 `waiting_for_controlled_environment`；即使全部
ready，也仍要由 owner 提供未來 activation decision，才可使用 fixture-only activation
command。當前 preflight 的三個 formal path 都是 missing，這是預期的 fail-closed 狀態。

Owner 設定三個 path 後，可用下列明確 opt-in 的唯讀模式把同一份 controlled
environment 直接交給 PFS-06 readiness；這個模式不會把 path 寫回 process、repo 或
任何正式 artifact，也不會讀出 HMAC secret：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_prospective_capture_readiness.py `
  --controlled-environment `
  --clock-manifest <CLOCK_MANIFEST> `
  --calibration-policy <CALIBRATION_POLICY> `
  --decision-timestamp <DECISION_TIMESTAMP> `
  --now <NOW> `
  --symbols-json <SORTED_SYMBOLS_JSON> `
  --output <READINESS_OUTPUT>
```

`--controlled-environment` 與 `--fixture-only` 互斥；任何 path missing、非檔案或
PFS-06 ledger／Rule／PIT custody 驗證失敗都會回傳 blocked。即使 readiness ready，
`capture_only=true`、`heavy_rebuild_launch_allowed=false`、`formal_oos_allowed=false`、
alpha=`0` 與 broker disabled 仍不變，後續仍需 owner 的 future activation manifest。

## 2026-08-14 自動鏈 current state

### 正式 ML 輸入接線狀態（2026-08-14）

正式 Direct／OOC 路徑現在可以消費三種受控輸入，但本機目前仍沒有合法來源，不能把這段「已接線」解讀成 gate 已通過：

- `--formal-portfolio-ledger` 必須指向 `causal-portfolio-ledger.v1` manifest；loader 會以唯讀 SQLite 驗證 append-only transition schema、每列 state hash、recursive chain、T-1 calendar 對齊與 non-cash state，拒絕 research-only、Teacher 回灌或 same-day Advice。
- `--formal-rule-champion-history` 必須指向 `rule-champion-snapshot-history.v1` manifest；每列都必須來自 controlled-store HMAC、immutable snapshot hash、連續 rank 與正式 Rule-only proof。執行環境必須提供受控的 `RULE_CHAMPION_CONTROLLED_STORE_HMAC_KEY` 與 `RULE_CHAMPION_CONTROLLED_STORE_ID`，不得寫入 repo、命令列、status 或 log。
- `--sector-membership` 仍只接受 `pit-sector-membership-sidecar-v1` 的 accepted／license／source hash／available_at／effective range custody；不可用當期 company registry 回填歷史產業歸屬。

若要讓每日 `baldr-ml-direct-chain-maintainer` 自動接收外部正式來源，可在 Windows 使用者環境設定 `BALDR_ML_FORMAL_PORTFOLIO_LEDGER_PATH` 與 `BALDR_ML_FORMAL_RULE_CHAMPION_HISTORY_PATH`；兩者只接受明確檔案路徑，維護器會先唯讀驗證 ledger chain／training cutoff 與 Rule history HMAC，才把路徑交給 immutable Direct/OOC chain。這兩個環境變數不包含 HMAC secret，secret 仍只由 `RULE_CHAMPION_CONTROLLED_STORE_HMAC_KEY` 提供。

若 owner 在 watcher 已啟動後才設定或更換上述 ledger／Rule path、`BALDR_ML_PIT_SECTOR_MEMBERSHIP_PATH` 或 Rule runtime environment，長駐 maintainer 會在每次 polling 重新讀取 Windows 使用者／系統環境登錄值，並只在目前 process memory 內更新受控 path、HMAC key 與 store id。它不會寫出 secret，也不會把任何 value 放入命令列、status 或 log；登錄值移除時，watcher 自己採用的 process 內值也會清除，後續正式驗證回到 blocked。這只是環境交接，不會取代三項正式輸入的 schema、hash、cutoff、HMAC 或 promotion gate。

三份輸入會以 file hash、logical manifest hash 與 dataset identity 傳遞到 Direct、OOC store、training 與 OOS replay input；OOS consumer 會再次驗證 ledger／Rule history custody，缺件或 tamper 只會 blocked。沒有合法三項來源時，`formal_oos_allowed=false`、`production_alpha_bp=0`、`broker_order_allowed=false` 維持不變；不可用 cash-only ledger、research artifact、current snapshot 或 heartbeat 代替。

可用 `scripts\inspect_ml_formal_input_readiness.py --output-root <OUTPUT_ROOT> --training-as-of <TRAINING_AS_OF> --output <READINESS_JSON>` 做唯讀 readiness check。`TRAINING_AS_OF` 必須是含時區的 ISO 8601 時間（例如 `2026-08-28T00:00:00+08:00`，不可只給 `2026-08-28`），避免 cutoff 時區歧義。它會實際呼叫三個 production validator，記錄每項 input 的 `missing`／`invalid`／`ready`、file hash 與原因，並在報告與 CLI 摘要提供 `ready_input_ratio`（例如 `0/3`）；即使三項皆 ready，也只表示可以進入受控 Direct/OOC refresh，不會直接解除 formal OOS、alpha 或 broker gate。當前 scheduled report 位於 `OUTPUT_ROOT\scheduled\ml_formal_input_readiness\latest.json`。報告另會提供 `prospective_output_observation`，以固定深度列出同一 output root 下已觀察到的 `clock-*` staging／prospective marker；這只是解釋「為何看得到檔案卻仍是 0/3」的診斷，不會自動 discovery、替換 owner-controlled `BALDR_ML_FORMAL_*` path，也不會把 prospective bytes 當成正式 input。此 CLI 在解析參數前設定 UTF-8 stdout/stderr，Windows 預設 CP1252 主控台也能正常使用 `--help`；指定的 readiness output 仍是明確路徑的受控 artifact，不會寫正式資料庫。

若需要回答「候選目錄裡是否其實有檔案」而不改變正式接線，可另用
`scripts\inspect_formal_input_candidates.py --candidate-root <CANDIDATE_ROOT> --output <INVENTORY_JSON>`。
這個盤點器只讀 bounded 的 `manifest.json`（預設最多 512 份），以固定 allowlist 投影 schema／日期／安全旗標並計算 manifest hash；會將檔案分為 `research_only`、`prospective_only`、`formal_schema_candidate` 或 `other`，也會明示 invalid／超過上限的項目。它不讀資料列、不執行 formal loader、不改環境變數，且報告必須寫在候選根目錄之外；`formal_ready_input_count` 永遠不由此工具升格，仍須由 owner-controlled publisher 產出三份正式 manifest，再重跑本節的 readiness check。

若需要把上述 bounded inventory 交給具名 owner／reviewer 逐項處理，可再執行下列唯讀 packet
builder（輸出 JSON／Markdown 的 parent directory 必須先存在，且不可位於 candidate root）：

```powershell
.\.venv\Scripts\python.exe scripts\build_formal_input_owner_packet.py `
  --inventory-path <FORMAL_CANDIDATE_INVENTORY_JSON> `
  --output-json <TEMP_OWNER_PACKET_JSON> `
  --markdown-output <TEMP_OWNER_PACKET_MD> `
  --owner-role <NAMED_OWNER_ROLE> `
  --reviewer-role <NAMED_REVIEWER_ROLE>
```

它只讀取 `ml-formal-input-candidate-inventory.v1`，為 causal portfolio ledger、formal
Rule Champion history、PIT sector membership 三項 expected schema 建立 review record，
並保留 bounded candidate path／manifest hash／lane／原因。即使填入 owner／reviewer 角色，
`owner_decision`、selected／published path 與 custody 仍須人工處理；packet 固定
`formal_ready_input_count=0`、`formal_oos_allowed=false`、`candidate_only=true`、
`write_performed=false`，不會寫正式 path、改名／複製 research／prospective artifact 或
授予 Formal／promotion／broker credit。完成外部出版後，才可用本節 readiness CLI 重新驗證。

Readiness inspector 也會在每項結果標示 `expected_schema_version`。若明確 path 指向
`prospective-formal-*`、`*-prospective-*`、`consumer_mode=prospective_formal_simulation` 或
`scope=prospective_only` 的 wrapper，結果會是
`prospective_manifest_requires_formal_consumer_publication`、`source_lane=prospective_formal_simulation`
與 `formal_consumer_compatible=false`；它不會把 prospective-only bytes 強行轉成正式
`causal-portfolio-ledger.v1`／`rule-champion-snapshot-history.v1`／歷史 PIT input。明確設定的
`BALDR_ML_PIT_SECTOR_MEMBERSHIP_PATH` 具有權威性：即使旁邊另有可 discovery 的 sidecar，
只要指定檔案沒有通過 hash-bound production validation，結果仍是 invalid，不會靜默改用另一份檔案。

若 configured path 位於 `formal_prospective/clock-YYYYMMDD/` 且檔案尚未發布，結果會額外揭露
`configured_clock_id`、`configured_clock_date`、`training_as_of_date` 與
`configured_clock_date_before_training_as_of`；日期較舊時 diagnostic 會提示 owner 更新明確受控
path。這只是 handoff 診斷，readiness 不會掃描或自動改接同一輸出根下的其他 clock，也不會把
prospective wrapper 轉成 Formal input。

最新 raw PIT publication 已自動更新至 `pit-a2f236fefac769e7346e04be`（decision
`2026-08-13T08:30:00+08:00`、15,938,679 rows、52 features）。Direct
`direct-ooc-6ff7650245ffea99ced5bf21` 已於 `2026-08-13T21:05:01Z` 完成 2014–2026；
checkpoint、13 個年度 manifest/carry、41 個 fold index 與 `latest_manifest.json` hash custody
均已通過。Direct manifest=`sha256:b52b1211e8bc61c591b0eb4b83ba2877701f7ca4fb1fbd4dff891e57b660d676`，
共 3,335,023 rows、62 features、41 folds，peak temporary bytes=`24,522,523,967`。

OOC 已由既有 helper 自動以該 Direct manifest hash 啟動 current run
`allocation-ooc-9750e409b0622fb4472a1a0f` 已完成，manifest hash=
`sha256:9faa8ec2d873d2b46efc23c8dbc42cfeb555bd1d9eeb8697ab24c7aa2d07c498`；共
3,335,023 rows、41 outer folds、40 meta folds、984 base experts 與 24 final experts，且
`store_manifest_hash` 綁定上述 Direct manifest。OOC 的 future／PIT／constraint violations
均為 0，peak RSS=`3,451 MB`／budget=`4,096 MB`。但正式 replay-input 仍因
`causal_non_cash_portfolio_ledger_present`、`formal_rule_champion_snapshot_history_present`
與 `pit_sector_membership_present` 缺件而 blocked；release follow-up 不會把中間 artifacts
或 heartbeat 當成可升級證據。所有 formal／production／broker gate 仍固定
`formal_oos_allowed=false`、`production_alpha_bp=0`、`broker_order_allowed=false`。上一輪 OOC
`allocation-ooc-2416e7265c6f3c15072173c6` 僅作歷史完整產物保存。

若 Windows 將長時間 supervisor 中止，系統會保留既有 child chain、清理已死亡 owner 的
stale lock，並由下一次 maintainer invocation 自動重新取得唯一 lock；不需要人工停止、刪除
run 或重訓。2026-08-13 已實際完成此 recovery，Scheduler query 的
`baldr-ml-direct-chain-maintainer` `Last Result=0`，沒有平行 chain。正式 gate 仍固定
`formal_oos_allowed=false`、`production_alpha_bp=0`、`broker_order_allowed=false`。

> **最後更新：2026-08-30｜適用 V3.3 Engineering / V4 Evidence Accumulation**。
> `release_v4` 是工程與儲存 namespace，不代表正式 V4.0。Decision／bounded Advice／Rule-only
> 日常檢查可用；Paper snapshot、Evidence loop 與 ML 都仍受 Gate 控制。目前 Paper ledger
> missing、Formal inputs=`0/3`、`formal_oos_allowed=false`、alpha=0、production scheduler／
> broker orders 關閉。任何畫面 `ready` 都必須按本節說明判斷 proof tier。

## release_v4 每日工程操作（非正式 V4.0 closeout）

### ML Co-pilot 排程自動補跑

ML allocation 排程入口會自動使用 --auto-catch-up。當沒有明確指定
ML_ALLOCATION_DECISION_AT、排程選到下一個台北曆日，且完整 orchestration
實際證明該候選日的 strict T-1 尚未就緒時，系統會依既有 hash-bound raw
publication 與 post-freeze T-1 proof，向後重試最多 31 個曆日。它不寫入
來源資料庫、不使用未來資料，也不把回溯日偽裝成原始候選日。

若資料庫、價格欄位或官方交易日曆狀態未知，系統不猜測、不改日期，依原
候選日繼續既有 fail-closed 流程；若由環境指定明確決策時間，則完全不會
自動改選。可在
OUTPUT_ROOT/scheduled/ml_allocation_copilot/latest_status.json 查看
decision_selection_mode、requested_decision_at、
decision_selection_reason 與 decision_selection_attempts。

本輪 direct store refresh 另由 `scripts\continue_ml_release_after_ooc.py` 受控等待；OOC helper 完成且 continuation status 與最新 training pointer 的 manifest hash 完全一致後，它會自動接續 evidence → authority → copilot，並寫入 `post_ooc_followup_status.json`。這只是 fail-closed 的營運銜接，不代表 promotion 授權，也不會解除 alpha=0、broker order disabled 或正式 SQLite 唯讀邊界。

若 direct process 已完成但 supervisor 因 Windows launcher／custody race 中斷，可由受控流程使用 `scripts\continue_ml_direct_ooc_after_store.py --resume-after-direct-store` 重新驗證 immutable direct manifest 後續接 OOC；這個模式不捏造 direct PID 存活，仍要求 checkpoint、年度 manifest、fold index 與 hash custody 完整。Promotion evidence 對 official market-event custody 以 `canonical_events_hash` 判定事件內容；相同 canonical timeline 的 wrapper／duplicate metadata 重發布不要求重建 direct store，canonical hash 改變仍 fail-closed。

### ML natural forward child 與 deadline 外 maturity

`baldr-ml-allocation-forward-daily` 是獨立的自然日 candidate shadow lane。`scripts\scheduled\run_ml_allocation_forward_daily.cmd` 先以 `ML_FORWARD_CALENDAR_CACHE_ROOT` 做 bounded official-calendar refresh，再由 Python wrapper 等待真正的 Asia/Taipei 08:30 decision clock；child inference 的最後 emission boundary 是同日 08:35。固定設定目前為：V2 release
`output\v4_ml_derived_h5_20260907_real_v2`（manifest hash=`sha256:c306c1ea53ccef112204a8412a605b575e4d107b4503b2b5be5d6d5ee50910ea`）、market source `D:\Min\Python\Project\FA_Data\sqlite\twstock.db`、repo Paper state `output\paper_execution_eod_replay\paper_portfolio\paper_portfolio.sqlite`、archive `output\formal_daily_publications\pit_candidate_archive`、calendar cache `output\paper_execution_eod_replay\calendar_cache` 與 forward output `output\v4_ml_daily_derived_shadow_real_v2`。daily config 位於 `output\v4_ml_forward_scheduler\configs\YYYY-MM-DD.json`，採 create-only；source archive／operational publication、manifest hash、release hash 與日期都在 child 前重新驗證。

Forward child 的 Paper input 必須同時設定 repository Paper state 與 transaction ledger。
reader 以 official calendar 列出 rolling window 的每個交易 session，要求 weekly snapshot
完整覆蓋到 strict T-1，並以 `paper_trade_transitions` 的 pre/post execution state
重建 canonical turnover；fill gross turnover 只作 Decimal audit，不能從事後 snapshot
猜 turnover 或分母。state／transaction ledger 都以 SQLite `mode=ro/query_only` 讀取並
保存 hash-before／after。08:30 preopen producer 的 isolated status 會提供
`paper-preopen-coverage.v1` 與 `paper-state-write-contract.v1`；若 outer wrapper 同時
看到 state DB 變動，只有 bytes、snapshot relation、state／ledger path、最新 state head
與 append-only safety scope 全部一致才可標為 `expected_preopen_producer_overlap`，否則
為 `failed_read_only_integrity`。這不會放寬 `formal_oos_allowed=false`、alpha=0 或
broker disabled。

若 child 回傳 `failed_read_only_integrity`，scheduler parent 會維持
`blocked_child_exit` 與非零結果，並在新的 receipt 內保存 bounded
`child_read_only_integrity`。該 projection 只包含 child immutable record 的 path／record
hash、formal market DB、Paper state、Paper transaction ledger、release manifest 的固定
guard 欄位，以及 release required-file hash 的 before／after／`which_changed`；完整
before／after source 與 coordination contract 仍須沿
`child_read_only_integrity.record.record_path` 讀取既有
`output\v4_ml_daily_derived_shadow_real_v2\natural_date_shadow\records\<record-hash>.json`。
若 `paper_state_db.unchanged=false` 且 `integrity_verified=false`、
`change_class=unaccounted_change`，根因範圍是缺少可驗證 preopen coordination contract，
不能把它解讀成 formal market SQLite、release 或 transaction ledger 改寫。這是診斷可見性
修復，不是 Paper coordination 根因修復。

parent readback 另將 post-deadline research sidecar 放在
`post_deadline_sidecar`，標示 `classification=parent_post_deadline_shadow_sidecar` 與
`formal_integrity_guard=false`。sidecar 的合法 append/hash 變化不屬於 child formal
read-only guard，也不能用來推論 child 自己寫入 formal source。既有
`forward_credit_granted=false`、`natural_day_credit_granted=false`、
`formal_oos_allowed=false`、`production_blend_alpha_bp=0` 與
`broker_order_allowed=false` 保持不變；不要為了取得診斷而重跑 failed child、放寬 guard、
延長 timeout 或手動授予 credit。

child 只負責 frozen release／PIT input、inference 與 observation emission。wrapper 收到 child 完整 outer payload 後，才在 08:35 deadline 之外呼叫既有 public `run_shadow_maturity_refresh`；成熟掃描不能延長 child deadline，也不會建立 observation 或授予 credit。child 成功、非零、completion gate 失敗或 timeout 都保存完整 outer status；timeout 仍可做 post-deadline 唯讀 maturity，但外層維持 `blocked_child_timeout`。postprocess 的 `source_binding` 必須指向 config 的 output／market DB／lane sidecar，且以 official calendar 解析 decision 日 strict T-1；缺 cutoff、未知／缺 calendar、任意日期或 future cutoff 均為 blocked。`forward_credit_granted=false`、`natural_day_credit_granted=false`、`formal_oos_allowed=false`、`production_blend_alpha_bp=0` 與 `broker_order_allowed=false` 在所有路徑保持不變。

每日檢查 `output\v4_ml_daily_derived_shadow_real_v2\scheduled\ml_allocation_forward\latest_status.json`：`child_completion_clock` 只表示 inference／emission 時鐘，`post_deadline_maturity` 另表示 maturity-only 結果；`post_deadline_maturity_degraded=true` 或 `status=blocked_post_deadline_maturity` 必須保留為需處理狀態。若 sidecar 不存在，成熟結果可為 `pending_source_missing`；這是等待既有觀測，不是自然有效性或 promotion 證據。可用下列受控入口只做既有 sidecar 的成熟回填（需要 exact lane root、official cutoff，且不產生新 observation）：

```powershell
.\.venv\Scripts\python.exe scripts\run_daily_ml_allocation_orchestration.py `
  --maturity-only `
  --database <READ_ONLY_MARKET_DB> `
  --maturity-run-root <EXACT_FORWARD_OUTPUT>\scheduled\ml_allocation_copilot `
  --maturity-cutoff-date <OFFICIAL_STRICT_T_MINUS_ONE>
```

CLI 與 wrapper 都會拒絕超過實際台北日期的 cutoff；成熟 outcome 的 stock／benchmark `available_at` 仍需早於實際 readback clock。未滿既有 natural shadow maturity、cost／risk／drawdown／CVaR、turnover、drift／rollback 或 pruning 門檻時，保留 pending／blocked，不以 historical replay、fixture 或盤後 readback 形成 effectiveness、formal OOS、promotion 或非零 alpha。

### 資料更新後 raw PIT 自動發布

`baldr-ml-raw-pit-refresh-daily` 會在 data-update quick 之後自動檢查
`OUTPUT_ROOT/scheduled/data_update_quick/latest_status.json`。只有 status 為
`passed`／`passed_with_warnings`，且 `check_overview_after` 證明 daily 與
technical core date 都已就緒時，才會以 SQLite `mode=ro/query_only` 建立全市場
immutable raw PIT publication。它使用當日 08:30 Asia/Taipei 作為 decision cutoff，
不寫回來源 SQLite、不建立 promotion evidence，也不改變 formal gate。

使用者不需要手動重建或手動觸發 ML。相同 cutoff 已有較新的合法 publication 時，
runner 會寫入 `skipped_current`；更新完成但上游 proof 尚未就緒時寫入
`blocked_upstream_not_ready`，下一個排程會自動重試；新 publication 完成後，
Direct/OOC maintenance watcher 依 raw pointer、canonical hash、dataset safety 與
training identity 自動接續，缺少正式 custody 時仍保持 `formal_oos_allowed=false`、
`alpha=0` 與 `broker_order_allowed=false`。

runner 在建立 immutable publication 前會對 raw PIT 輸出磁碟做唯讀三段容量 preflight：
本次持久新增上限 `--persistent-storage-budget-bytes`（預設 35 GiB）、暫存峰值上限
`--temporary-storage-budget-bytes`（預設 40 GiB），以及執行後安全保留
`--safety-reserve-bytes`（未指定時為中央政策的至少 200 GiB）。若任一 headroom 不足，會寫入
`status=blocked_insufficient_storage`、`storage_preflight.capacity_budget` 與 blockers，
不啟動 builder、不留下新的部分 publication。這個容量檢查不會刪除或搬移既有 run，舊
publication 的 retention 必須另由 owner 審核。

若 daily-price source quality guard 發現候選異常，raw runner 會以 exit code `2`
停止並在 `scheduled/ml_raw_pit_refresh/latest_status.json` 保存 bounded
`source_quality_summary`：分類計數、受影響日期摘要、最多 12 筆樣本與完整報告 hash。
它不會落地數百萬筆 quarantine candidates，也不會因摘要存在而繼續建立 PIT；應由
ML／資料品質 owner 依摘要做短日期／市場 probe，完成來源路由或數值精度修正後再
重新走容量、鎖與 source guard。

scheduled raw／Direct 的 35 GiB 持久新增、40 GiB 暫存峰值與 200 GiB safety
reserve 會合計要求至少 275 GiB free headroom；低於 200 GiB 的顯式 reserve 會
fail closed。PIT、Direct、raw-to-OOC 與 OOC standalone CLI 的預設持久／暫存上限
各為 1 GiB，仍須保留 200 GiB safety。這些 caller 會以最近存在的 ancestor 判定
實際磁碟，並對跨磁碟的 persistent／temporary aggregate quota 做檢查。

若只想確認 immutable pointer、database `ro/query_only` 與 Direct/OOC 磁碟 headroom，
不想取得 maintenance lock 或啟動長時間 chain，可使用安全的 preflight-only 模式：

```powershell
.\.venv\Scripts\python.exe scripts\scheduled\run_ml_direct_chain_maintenance.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output-root D:\Min\Python\Project\FA_Data\output `
  --status-path $env:TEMP\ml_direct_storage_preflight.json `
  --minimum-free-space-bytes 214748364800 `
  --preflight-only
```

結果會是 `status=preflight_only`、`execution_started=false`；即使 headroom 足夠也不會
啟動 child maintainer。這個 artifact 只供 readiness／owner packet 讀取，仍固定
`formal_oos_allowed=false`、`broker_order_allowed=false`。

2026-08-12 首次自動 refresh 已發布 publication
`pit-29505ceb0005d068610dde01`：decision cutoff=`2026-08-12T08:30:00+08:00`、
`all_field_enriched`=`15,932,713 rows / 52 features / 13 shards`，dataset hash=
`sha256:90ea99f71d689060123c187bba8db5335d6aa106620f130d325e2a3dbbcc04d3`。
Watcher 隨後自動啟動 Direct immutable run；若 Direct/OOC 尚未完成，應以 heartbeat、
checkpoint 與 latest manifest 判斷進度，不把 processed rows 當成完成。此次 handoff
也修正了合法 `sector_membership_file_hash=null` 被誤判為字串 hash 的問題；沒有 sector
sidecar 時仍維持 formal gate 關閉。

Raw publication 完成後不需要人工啟動 Direct 或 OOC。每日 05:30 的
`baldr-ml-direct-chain-maintainer` 會自動重驗最新 raw pointer、全市場 scope、
dataset safety、official market-event custody 與目前 Direct identity，接著啟動或
維持 `maintain_ml_direct_v3_refresh_chain.py --watch-formal-inputs`。既有 chain lock、
checkpoint、年度 manifest 與 hash-bound pointer 會防止重複訓練並在 worker／supervisor
中斷後續接；無效輸入只留下 `blocked_invalid_bootstrap_input`，不會以人工輸入或猜測
sidecar 繼續。狀態位於：

`OUTPUT_ROOT/scheduled/ml_direct_chain_maintenance/latest_status.json`

OOC 訓練器的 calibration gate 也已改為 expanding outer-fold 的 cross-fitted
OOF 診斷：每個 target fold 只使用更早、且在下一 fold 開始前已成熟的 OOF
blocks，probability 與 metrics 均以整數 bp 保存。結果會標記
`oof_diagnostic_only=true`、`production_eligible=false`；不會把未校準的
base vector 靜默改寫成校準後 vector。若 training manifest 出現
`classifier_calibration_not_attached_to_ooc_model`，代表 cross-fitted 診斷
已完成但尚未形成可供 OOC inference 使用的 production calibration artifact，
不得據此解除 formal OOS、alpha 或 broker gate。

該 status 的 `completed` 也包含「已有合法 owner 持有 lock、此次安全跳過」的正常情況；
此時會明列 `execution_disposition=existing_owner_lock`、
`maintenance_lock_state=verified` 與經命令列驗證的 `maintenance_owner_process_id`，且
owner 命令列必須與同一個 `training_output_dir` 完整相符。若 Windows 暫時拒絕讀取
live owner 命令列，wrapper 會標記 `execution_disposition=owner_lock_unverifiable`、
`maintenance_lock_state=owner_lock_unverifiable`，維護器會保留 lock 並等待下一輪驗證，
不會把未知 owner 當 stale lock 刪除。這不代表 Direct/OOC 已完成，長鏈進度必須看 heartbeat、checkpoint 與 immutable
latest manifest。整條自動鏈固定維持 `database_mode=ro`、`query_only=true`、
`writes_source_database=false`、`formal_oos_allowed=false`、`production_alpha_bp=0`、
`broker_order_allowed=false`。

可觀測路徑：

- `OUTPUT_ROOT/scheduled/ml_raw_pit_refresh/latest_status.json`
- `OUTPUT_ROOT/scheduled/ml_raw_pit_refresh/refresh.log`
- `OUTPUT_ROOT/release_v4/ml_pit_year_shards/latest_manifest.json`
- `OUTPUT_ROOT/release_v4/ml_pit_year_shards/runs/<publication_id>/`

1. 開啟 `ui_qt/main.py`，從市場總覽確認 Market Breadth、Sector Rotation、Relative Strength/Liquidity、Watchlist Trigger 與 Portfolio Alerts。Workbench 的「決策來源」仍導向同一個 Decision Desk，不建立第二份狀態。
2. Advice 必須含 action、Why／Why Not、Risk Prompt、target/current/gap/executable。`current` 不明時會保留 unknown，不能猜成 0，也不能產生可執行 gap。
3. 可見 action 為 `ADD_CANDIDATE`、`HOLD`、`REDUCE_CANDIDATE`、`EXIT_CANDIDATE`、`NO_NEW_POSITION`、`AVOID`。它們是配置與硬限制後的決策建議，不是券商委託。
4. 檢查 `OUTPUT_ROOT/scheduled/ml_allocation_copilot/latest_status.json`：`selected_alpha_bp=0` 表示 Rule-only；只有可信 promotion custody、consumer re-verification 與所有 thresholds 都通過，才可能出現 2000／3500／5000。`shadow_day_credit_allowed=false` 代表本日 observation 已正常保存，但因正式 Rule/context custody 不足而不計入 20 日 Promotion 門檻，不是 runner 失敗。request 中自行填入非零 alpha 不會生效。
5. 檢查 `OUTPUT_ROOT/scheduled/decision_evidence_capture/latest_status.json` 與隔離 operation root 的 `scheduled/paper_portfolio_isolated/latest_status.json`。前者應揭露 snapshot/event counts；後者應揭露 T-1 diagnostics、cash、total value 及 market DB `ro/query_only`。
6. Gate 2 weekly history 不得由 scheduler sidecar 自動計入 Gate：Windows weekly collection 只產生 `pending_human_review`，不代表人工核准或 formal credit。若未設定具名 owner 核准的 `approved-weekly-history-projection.v1`，UI／readiness 會依 canonical DB 顯示未取得 credit；若有 projection，也只供 UI 進度揭露，不能改變 `formal_credit_authorized=false`、`production_scheduler_allowed=false`。2026-08-30 現況需分層閱讀：歷史 working-copy=`1/3`、owner-approved UI projection=`3/3`、sidecar pending=`10`、multi-day=`3/3`，但 formal/canonical credit 仍未授予。forward、Paper elapsed、Exit outcome、ML shadow days 與非零 alpha 仍由各自的 evidence maturity 決定。

### ML Promotion Reference 與 Shadow Evidence

凍結 reference 必須由正式 training model／manifest／dataset manifest 產生，不能拿 daily observation 自建 baseline：

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_allocation_promotion_reference.py `
  --model-artifact <RELEASE>\allocation_model_v3.joblib `
  --training-manifest <RELEASE>\training_manifest_v2.json `
  --dataset-manifest <PORTFOLIO_TRAIN_RUN>\manifest.json `
  --promotion-policy-hash sha256:<POLICY_HASH> `
  --output-root <OUTPUT>\ml_promotion_reference_v4
```

Canonical reference v2 為 22,093 rows、62 features／3 formal families，reference hash=`sha256:8ee81ae9c5691c6e10d95f14eac293b2ecd121a53877f0d0de73e20b514dd5b0`、file hash=`sha256:d02ab09f8cfa19449b7524d4ca12139a9e27e55b2f4d78f70cbc1be15821800f`，並綁定 outcome contract=`sha256:95172f7d8678fd6ecde83c1c166b56878b0d3b769750290acb5b0b3753c96a11`。每日排程會自動載入此 reference，分別保存 5／10／20／60 日 calibrated／uncalibrated downside probabilities 與 current feature/family distribution；使用者不需也不能手工填 calibration 或 PSI。

每日結果位於：

- `OUTPUT_ROOT/scheduled/ml_allocation_copilot/shadow_evidence_collector/shadow_evidence.sqlite`：append-only observation／outcome revisions。
- `.../observations/`、`.../evidence/`：immutable 四 lane observation 與彙總。
- `.../reference_metrics/<hash>.json` 與 `latest_reference_metrics.json`：逐 horizon immutable calibration／drift metrics custody。
- `.../production_advice/<date>_alpha_0.json`：目前合法 Rule-only Advice，不是券商委託。
- `OUTPUT_ROOT/scheduled/ml_promotion_evidence/latest_status.json`：05:17 unsigned evidence preflight；blocked 不代表 Rule 失敗。
- `OUTPUT_ROOT/release_v4/ml_promotion_authority/latest_status.json`：05:18 DPAPI Authority 是否簽章及 machine blockers。

同日同 custody 重跑必須顯示 `idempotent=true`；同日新 custody 只追加 revision，成熟天數仍只算該日最新 revision一次。任一 horizon 未滿 20 個唯一成熟交易日時，ECE、calibrated／uncalibrated Brier、feature/family PSI 都應是 `null / NOT EVALUATED`，reference maturity blocker 格式為 `matured_shadow_days_insufficient:h<horizon>:<n>/20`。看到 `0` 指標、缺 hash custody、future/PIT violation 或 reference tamper 都應視為錯誤並保持 `alpha=0`。

2026-07-31 最新 canonical reference-v2 接線驗證已保存 observation revision=7、fully matured outcome=0；shadow evidence hash=`sha256:82332fb24eb62dcf2018e8d940d9f7e4faa21dd83a5e9bd48990dbd2d6d36669`，metrics hash=`sha256:607adf7b48f4210809ee2f31d355d3adfef56027cb0d7d6322db3fd02dda750d`。該 observation 明確為 `promotion_day_credit_allowed=false`，所以 5／10／20／60 日 promotion 計數均為 `0/20`；全市場 OOC 與正式 semantic replay 亦尚未形成 compatible evidence，reference baseline／feature distribution 則為 `ready`。

## release_v4 工程排程（不代表 V4.0 closeout）

| 本機時間 | Task | 寫入範圍 |
|---|---|---|
| 04:20 | `baldr-data-update-quick-daily` | 既有市場 raw/SQLite 更新 |
| 04:50 | `baldr-official-market-events-daily` | append-only 官方 market-event vintages |
| 05:00 | `baldr-data-freshness-check-daily` | status/log only |
| 05:05 | `baldr-ml-raw-pit-refresh-daily` | full-market immutable raw PIT publication；僅讀取來源 SQLite |
| 05:10 | `baldr-recommendation-snapshot-daily` | research recommendation snapshot |
| 05:15 | `baldr-evidence-pipeline-dry-run-daily` | dry-run report |
| 05:17 | `baldr-ml-promotion-evidence-daily` | unsigned formal OOC／雙 replay／Shadow／metrics evidence |
| 05:18 | `baldr-ml-promotion-authority-daily` | DPAPI machine authorization；不足即不簽 |
| 05:20 | `baldr-ml-allocation-copilot-daily` | immutable lane sidecar/promotion status |
| 05:25 | `baldr-decision-evidence-capture-daily` | durable DDD snapshot + evidence events |
| 05:40 | `baldr-forward-outcomes-daily` | 以當下可見行情有界重算 5／10／20／60 交易日 close-to-close research outcomes；明確 confirm 後只更新 `evidence_outcomes` |
| 16:15 Pacific | `baldr-paper-portfolio-daily` | 先以 D 槽 Paper snapshot 的唯讀 consistent backup 建立 repository isolated state；PDT／PST 分別在台北 07:15／08:15 喚醒，adapter 兩種 offset 都等待真實 08:30 cutoff 後才 append preopen snapshot；不自動產生真實 fills 或成本 ledger |
| 16:15 Pacific | `baldr-ml-allocation-forward-daily` | 第 18 個 daily task；以 pinned UTF-16 XML 註冊，等待真實 Asia/Taipei 08:30，08:35 後 fail closed；只寫 repository-isolated candidate shadow/config/receipt，固定 real_v2 output、V2 manifest hash、repo Paper state 與 offline calendar；不授予 forward／formal／production credit |
| 06:00 Pacific | `baldr-paper-execution-eod-replay-daily` | 先以同一台北自然日的 quick update、freshness、daily_prices open rows 與 TWSE／TPEx source→DB readback gate 驗證，再由隔離 runner 消費 frozen recommendation；缺源只在同一自然日最多重試 3 次，每次間隔 15 分鐘；terminal blocker 立即停止，官方無資料日為明確 no-op |
| 16:00 Pacific | `baldr-pit-sector-membership-preopen-capture-daily` | 在台北 08:30 前保存 PIT candidate/archive；response completion 越過 cutoff 或 custody 不完整時 fail closed |
| 18:00 Pacific | `baldr-formal-pit-sidecar-postcutoff-daily` | 只讀當日 PIT archive 建立 sidecar；缺完整 archive 時留下 blocked receipt，不重新抓取同日來源 |
| 21:25 Pacific | `baldr-formal-input-producer-daily` | 以自然時間重驗 Rule／causal Paper／PIT handoff；缺任一 input 保存 blocker，不計 Formal credit |
| 05:30 | `baldr-ml-direct-chain-maintainer` | 自動 bootstrap／維持 Direct → OOC watcher；只使用 hash-bound immutable input |
| 週日 18:00 | `baldr-v2-2-weekly-collection` | append-only weekly evidence sidecar + machine revalidation |

### Decision Desk／Evidence capture 的真實時鐘（2026-09-16）

`baldr-decision-evidence-capture-daily` 在 05:25 Pacific 執行時，
`latest_status.json` 應分開顯示 `calendar_decision_at`（僅用於選擇已到達的台北
08:30 日曆日）、實際 aware `decision_at`、`as_of` 與 `captured_at`。台北收盤後
執行的路徑標為 `capture_mode=eod_research`、`research_only=true`，永不宣告
`preopen_authority` 或 `natural_authority`。source `available_date` 與 source
metadata 的實際時間戳保持原值；不以 capture clock 回填歷史可用性，也不把歷史事件
改寫成盤前事件。

直接以 `--decision-date` 呼叫的舊 CLI 仍可執行，但
`temporal_status=temporal_precision_unproven`，且不會隱式補 08:30。確認重跑會以
semantic event／snapshot identity 冪等；`persisted_*_capture_context` 是首次保存的
immutable receipt，與本次 `current_capture_context` 分開判讀。若 child 未回讀相同時間
context／hash，外層 runner 會 fail closed。這條 capture path 仍是研究／證據保存流程，
不改寫正式 DB 歷史資料、不宣告自然成熟，也不具交易執行權限。

#### 2026-09-18 capture 修復與合法下次 run 驗證

2026-09-17 的 `latest_status.json` 是已保存的歷史 failed receipt：failure 原因是 parent／child
`capture_context_hash` 與 identity hash mismatch；不得以修補後的 working tree 回填偽造 9/17，
也不得為了重建 9/17 而觸發 historical retry。下一次合法排程可自然更新 `latest_status.json`，
但應保留本輪 QA copy 與原始 hash 作為歷史對照。修補後 parent payload 與 child
arguments 必須傳遞同一個完整 aware `datetime.isoformat()`，保留 subsecond；同秒不同
`decision_at` subsecond 仍是不同 identity，retry 若只改 `captured_at` 則保留 identity、但
full context hash 必須不同。

下一次合法自然排程 run 只做 receipt readback：確認 `latest_status.json` 的
`status`／`snapshot.status`、`snapshot.saved`、七個 required sections、
`persisted_snapshot_capture_context` 與 `current_capture_context` 各自通過時間／兩個 hash 的
完整性驗證；合法 retry 的 `captured_at` 可以不同，但 decision／as-of／authority identity
應相同，且首次保存的 persisted context 與本次 current context 分開判讀，
以及 evidence step 沒有 `reason=snapshot_step_failed`；同時保留
`capture_mode=eod_research`、`research_only=true`、`preopen_authority=false`、
`natural_authority=false`。這個檢查不把 run 結果追認為 natural maturity 或 Paper／Formal
credit，也不以人工或 historical retry 回填舊 failed receipt；合法下一次 run 可依既有 latest
pointer 規則自然產生新 status。已核實的 Task Scheduler action 仍是 repo 的
`run_decision_evidence_capture.cmd`，由 cmd 進入 repo root 後呼叫目前 wrapper；應等待下一次
預定時窗的實際 receipt，不手動 trigger task。

修補後每次合法 invocation 會在 `scheduled/decision_evidence_capture/runs/<run_id>/` 建立
create-only immutable `receipt.json`；`run_id` 含 UTC subsecond 與 UUID，因此同秒 retry 也不覆寫
舊 run。receipt 先以 flush／fsync 保存，再由 `latest_status.json` 以 atomic pointer 指向 receipt
path／SHA-256。child stdout／stderr 以 raw bytes bounded 保存，並記錄原始 byte count、原始 hash、
truncation、保存 artifact hash／size、OS returncode 與 timeout；完整 stdout 仍用於 JSON parse，
不保存 child environment。receipt、artifact 或 latest 寫入失敗時只能留下 failed／unknown 狀態，
不可顯示 passed；這些追溯資料不授予 natural、calibration、Paper 或 Formal credit。

Aggregate `register`／`register-all` 僅在 Windows `Pacific Standard Time` 主機建立
既有 aggregate scope 的以 Pacific local time 表示的 task；`dryrun` 可在其他時區唯讀檢查。
新增的 `baldr-ml-allocation-forward-daily` 使用獨立 pinned XML 與 Python preflight，
不由 aggregate register／register-all 建立或覆蓋。Paper Portfolio
的 16:15 trigger 在 PDT／PST 分別落在台北次日 07:15／08:15；adapter 以真實
Asia/Taipei 08:30 cutoff guard 等待兩種 offset 的早到喚醒，不能把 PST 的 09:30 開盤後時間
視為盤前，也不會以未到達的 cutoff 建立 snapshot。
若只需修正這一個 task，先執行
`scripts\scheduled\register_paper_portfolio_task.cmd dryrun`，核對 action 與
16:15／DST 說明後，再由受控 Windows 工作階段執行同一腳本的 `register`；它不會
註冊或取代其他 task；既有 task 只以 `schtasks /Change` 更新 trigger/action，保留
其餘安全設定。Task Scheduler 的實際 Enabled、Next Run、Last Result 仍須用
`schtasks /Query /TN baldr-paper-portfolio-daily /V /FO LIST` 唯讀核對。

官方 market-event task 平時只抓前一年度與當年度的增量；若 `latest_manifest.json` 的 verified publication 歷史起點不是 2014，排程會自動改抓 2014–當年度做 recovery，成功後下一輪恢復兩年增量。這個 recovery 只追加 raw／canonical publication 與 status，不寫 active SQLite、不改 Rule／Portfolio、不授權 ML alpha。

### Official market-event TWT49U 名稱修訂與 PIT 判讀

`TWT49U` 是官方除權除息結果表，只能作 result-only label／ledger；不能由結果表反推公告時間，也不能把名稱修訂當成經濟事件的新一次發生。當同一 `source_id + symbol + event_type + effective_date` 只由 `股票名稱` 改變時，backfill 才會接受受限的 `revision_kind=display_name_only`，並要求：

- 舊／新 `raw_response_sha256` 與 raw 檔案都留在同一份 append-only publication 的 `raw_index.jsonl`。
- `event_id`／natural key、代號、日期、source identity、event timing、結果價格與其他經濟欄位完全相同；`economic_content_hash` 必須相等。
- 新 revision 必須有 `display_revision_of`、`supersedes_revision_id`、遞增 `revision_sequence`，且 `available_at` 使用該 raw 的 `retrieved_at`，不可回填為原 effective date。

因此，較早的 historical `as_of` 只能讀到當時已可得的舊顯示名稱；兩個 vintage 在 Portfolio ML reader 中仍只形成一個 eligible effective date。adjustment custody 會保留兩版 source revision、raw hash 與相同經濟 factor 供追溯，但固定 `prospective_only=true`、`historical_pit_eligible=false`，也不在此路徑把 factor 套用到 raw close。Return／label window consumer 只將同一經濟事件視為一個 exclusion effect；它不把兩列相加或重複乘 adjustment factor。

不同價格、日期、代號、source／schema 欄位、未能核驗的經濟內容、同名經濟變更或不明 predecessor 一律維持 `unlinked_revision_conflict`／quarantine；不得覆寫舊 raw、canonical history、SQLite 或 last-known-good pointer。必要的驗證應在隔離 output root 以兩版 raw 順序重跑，再以第三次 identical replay 確認 `new_event_count=0`、canonical revision 數與 raw lineage 數不膨脹；正式 D: 資料只做唯讀比對。

查詢：

```powershell
scripts\scheduled\query_baldr_scheduled_tasks.cmd
```

目前 18 個 daily tasks 加 1 個 weekly task 共 19 個 Windows tasks。ML evidence／Authority／Co-pilot 三段與 Direct chain maintainer 已實際觸發且 `Last Result=0`；raw PIT refresh 與 Direct chain 各有獨立 immutable／bootstrap status，若 OOC／replay 尚未完整仍只輸出 `blocked` 或維持等待，Authority 可輸出 `skipped_evidence_unavailable`，這些都是成功的 fail-closed 營運狀態。Scheduler process-level 成功不表示資料來源全數 observed 或 ML promotion 已通過。所有 tasks 都不得送單；只有經成熟度、交易日、雙 replay、簽章與 inference-release identity 全部驗證的 evidence 才能影響 alpha。Forward task 的註冊完成也不表示它已有自然執行結果；請以 registration inspector、wrapper preflight 與當日 receipt 分別判讀。

Paper EOD replay 現行 trigger 為 Pacific 06:00，PDT／PST 分別對應台北 21:00／22:00，位於 Pacific 04:20 quick data update 之後。2026-09-08 00:05 的非零結果只屬變更前歷史證據；部署後仍須以 `schtasks /Query /TN baldr-paper-execution-eod-replay-daily /V /FO LIST` 讀取 Next Run、Last Result、登入模式與電池條件，再以 dependency gate receipt 判定資料是否真的可用。現行 `Logon Mode=Interactive only`、停止於電池且不喚醒，登出或休眠時不能保證自然 capture；缺跑應由 task query 與各 latest status／receipt 的 freshness 監控揭露。

Paper EOD gate 對 freshness 採 lane-specific projection，保留原始 aggregate
`freshness_status`／`warnings`。只有 aggregate `status=degraded` 且 `errors=[]`，每個
warning 都能由 `source_statuses` 的 `source_id` 與 `freshness_status` 完整對應到已登記的
非 EOD source，並且 `twse.daily_prices.raw`、`tpex.daily_prices.raw`、
`sqlite.daily_prices` 同日為 `current` 時，才會在 quick／freshness target date、aware
timestamp、raw CSV 與 SQLite readback 全部通過後回傳 `ready_with_warnings`。結果中的
`freshness_lane` 會列出 required source、非 EOD warning 與 aggregate status；這不是把
aggregate 改成 `passed`，technical／flows／fundamental／institutional／credit 仍由各自
consumer 的契約判定。未知或未分類 warning、source ID／status 缺失或 malformed、未歸屬的
non-current source、`failed`／`expected_wait`、必要 source 的 `stale`／`partial`，或任何
日期／時間／raw／DB reconciliation blocker，均維持 `blocked`；`passed_with_warnings` 不會
繞過此判定。只有兩個明確列入 policy 的 non-EOD `unknown` 可從 Paper EOD freshness lane
隔離：`tdcc_shareholding` 是 TDCC 週資料候選的 completeness unknown，
`fundamental.statement_availability_map` 是 Fundamental/PIT 的 MOPS mapping 缺件；兩者
都不是 Paper producer 的輸入。`freshness_lane.not_required_for_paper_eod` 會逐筆保留
原始 source row、`unknown`、reason code 與 consumer boundary，讓各自 consumer 繼續
fail closed；這不是把來源標成 `current`，也不會放寬 TDCC／Fundamental gate。其他
unknown source、required source unknown、malformed、failed 或 aggregate errors 仍會阻擋。

2026-08-12 本機唯讀 query 顯示 13/13 tasks 均為 `Enabled`／`Ready`；raw PIT refresh 與 Direct chain maintainer 的實際觸發結果均為 `Last Result=0`，執行結果分別以 `ml_raw_pit_refresh/latest_status.json` 與 `ml_direct_chain_maintenance/latest_status.json` 判定。目前 `Logon Mode=Interactive only`，因此證明的是互動式帳號下的排程註冊與最近成功結果，不代表已完成無人登入執行。`production_scheduler_allowed=false` 仍是正式 production evidence／交易授權邊界，不能因 task 已註冊而放寬。

Windows task 的註冊、正在執行與 `Last Result` 必須以以上 query 命令判定；Runtime 頁只讀已保存 status artifact，不能取代此查詢。

### Paper EOD policy consumer

`baldr-paper-execution-eod-replay-daily` 的隔離 runner 會從受控
`output/formal_daily_publications/pit_candidate_archive/<effective-date>/<archive-id>/archive_manifest.json`
選取一份明確 archive，並把 manifest path 與實際 file hash 傳給 Paper producer。archive consumer
會重新驗證 publication、receipt、operational envelope、官方 TWSE／TPEx raw custody、
`available_at`、`archived_at` 與明示的 machine code compatibility（current 或已核驗的
audited legacy）；archive 缺少、晚於 frozen recommendation
時間、hash 改變或跨受控 root 時，結果為 `blocked`，不改用顯示用產業欄位或另一份最新檔。Paper
producer 同時需要 append-only ledger DB 與 bounded `OfficialTradingCalendar`，任一來源未知都
保持 candidate-only blocked。

跨台北午夜的 durable readback 保留實際 consumer wall clock；first-seen
`effective_from` 只依 immutable `captured_at` 的自然日驗證。已核驗的上一台北自然日 archive
可以在午夜後讀回，future `archived_at`、晚於 decision 的持久化時間、未知 machine hash 或
producer／receipt 混合 hash 仍 fail closed。`current_code_hash_match=false` 只有在 consumer
同時回報 `code_hash_compatibility=audited_legacy` 且
`legacy_code_hash_compatibility_verified=true` 時才是明確相容狀態，不代表正式或 forward credit。

政策流程先以 `PaperPortfolioPolicyAdapter.evaluate_batch` 評估整批目標，再建立模擬 fills。
週 turnover 使用實際 `paper_trade_transitions` 的 canonical 整數 bp；fill gross bp 只作
Decimal audit，cooldown 只跨 official trading days，sector 只能來自 hash-bound PIT
mapping；缺來源不當作 0。被拒絕的 target 不會變成 fill。模擬 fill 完成後，
producer 依實際成交數量重新核對 cash、minimum reserve、turnover、持倉與 sector exposure；
部分成交或拒絕賣出不會預先釋放現金或 sector 額度。重跑同一 frozen recommendation 時，只有
同一 recommendation 的 exact fill identity 被排除；同日其他 candidate 已成交的 rows 仍會進入
下一批 policy state，所以 retry 與同日第二批不會重新借用昨日現金、持倉或週額度。

成功結果仍是 `research_only` candidate，append 只在明確 `confirm_append` 的隔離 ledger 執行，
之後會做 readback；它不送出券商委託、不寫正式／D 資料庫，也不授予 Formal、forward 或 promotion
credit。當日自然 shadow 的有效性仍要等實際 observation／outcome maturity；可讀 archive 並不
代表已取得 effectiveness。

補充：handoff supervisor 若使用自訂 `--status-path`，會自動將三個 child process 的 operational log 寫到 heartbeat 同層的 `logs` 目錄；這是為了在正式資料目錄無法寫入 log 時仍能自動續接，並不改變正式 manifest、SQLite 或 fail-closed gate。未指定自訂 status path 時，仍使用既有 direct/training `logs` 位置。

## 全欄位資料稽核與年度 shards

```powershell
.\.venv\Scripts\python.exe scripts\inspect_ml_all_field_readiness.py `
  --decision-at 2026-07-30T08:30:00+08:00 `
  --history-start-date 2014-01-01 `
  --output-dir D:\Min\Python\Project\FA_Data\output\release_v4

.\.venv\Scripts\python.exe scripts\inspect_ml_file_field_inventory.py `
  --data-root D:\Min\Python\Project\FA_Data `
  --output D:\Min\Python\Project\FA_Data\output\release_v4\ml_file_field_inventory.json

.\.venv\Scripts\python.exe scripts\build_ml_pit_year_shards.py `
  --database D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --output-dir D:\Min\Python\Project\FA_Data\output\release_v4\ml_pit_year_shards `
  --decision-at 2026-07-30T08:30:00+08:00 `
  --history-start-date 2014-01-01 `
  --all-universe
```

正式 train 只讀 manifest 中 `formal_backfill`，以及未來通過來源／授權／publication lineage 驗證後才可能出現的 `first_seen_only`。本次 freeze 的 disposition summary 為 `formal_backfill=52`、`first_seen_only=0`、`research_shadow=32`；月營收／財報／估值的 4 個數值候選與其他 28 個新資料欄位都只能留在 `research_shadow_all_fields`。legacy pickle/predictions/replay/outcomes、現在公司快照及缺 provenance 欄位不能被搬進正式 manifest。ATR/ADX 由 shard builder 依 OHLC prefix 重算；不要把原表 NULL 以 0 補值。

2026-07-30 全市場 publication 與 2026-08-07 舊 direct／OOC artifact 仍保留為歷史 immutable 輸出。2026-08-12 自動 refresh 已完成新的 raw PIT publication：dataset manifest=`sha256:739026b63bfd5a7780baa1714ebd53a5cc5662ef620518ebe3f0b024df2d98e6`、15,926,733 rows、52 features；Direct run=`direct-ooc-94355ffac5a541dbd9cb7282`、canonical manifest=`sha256:0bd97a301a1367ca3a8378cb45c4c9250eebc0dd6e49ced7c313ec39ad655639`，OOC run=`allocation-ooc-05fd4dd6515cddfdf6e0228d`、training manifest=`sha256:07cf93b6f707641e37fce791603f354f20099132df004a93099faec388feefe2`；兩個 `latest_manifest.json` 均已原子切換。Direct numeric v4 將官方 halt/resume event 以 `effective_at`／`available_at` 綁定至每個 replay row；任何舊 run 都不回溯改寫。這代表新的 training custody 已發布，**不代表** full-market readiness、formal replay、ML promotion 或非零 alpha 已通過。應檢查：

- `OUTPUT_ROOT/release_v4/portfolio_ml_direct_numeric_production_v4_v2/latest_manifest.json`
- `OUTPUT_ROOT/release_v4/portfolio_ml_direct_ooc_training_production_v4_v5/latest_manifest.json`

`continuation_status.json` 會在 OOC helper 啟動等待時先寫入 `waiting_for_direct_store`，並在等待期間只鏡像 PID 與受監督 direct process 相符的最新有效 heartbeat（若存在）；進入長時間 OOC 訓練後，會以 `portfolio-ml-ooc-heartbeat.v1` 的 `training_running` 持續發布訓練 PID、啟動／心跳時間、store manifest hash 與命令列 custody；完成或失敗後才寫入 terminal 狀態。新版 waiting、custody、training heartbeat、complete 與 blocked status 都會明列 `formal_oos_allowed=false`、`production_alpha_bp=0`、`broker_order_allowed=false`；若舊版 helper 已結束但 terminal status 缺少欄位，release coordinator 會自動補寫這些 fail-closed 欄位，明確 true／非零值則阻擋後續 release。它仍不是 OOC 發布權威，必須以 `latest_manifest.json` 指向的完整 manifest 和 promotion evidence status 判讀。Direct numeric store 的每個 run 另會寫入 `runs/<run_id>/heartbeat.json`，揭露目前 stage、PID、已完成年度與 UTC `updated_at`；兩種 heartbeat 只供進度觀測，完成仍必須由 checkpoint、年度 manifest 與 hash-bound `latest_manifest.json` 驗證，不得以 heartbeat 單獨宣告完成。現況 OOC replay-input 與 promotion evidence 都因 `causal_non_cash_portfolio_ledger_present`、`formal_rule_champion_snapshot_history_present`、`pit_sector_membership_present` blocked；strict T-1 已由 data-update quick 證明至 `2026-08-12`，因此不是 freshness blocker。`formal_oos_allowed=false`、`production_blend_alpha_bp=0`、`broker_order_allowed=false` 仍是唯一有效值。

若一輪舊 direct run 已在背景執行，不需要人工停掉或重跑；受控 handoff supervisor `scripts\continue_ml_direct_v3_refresh_chain.py` 可等待既有 direct／OOC／release PID 與命令列完整結束，然後自動建立新的 immutable direct v4、綁定新的 OOC 與 release helper。它會寫入 `v3_refresh_chain_status.json` 與各階段 log；等待期間另以 `portfolio-ml-direct-v3-refresh-chain-heartbeat.v1` 原子鏡像受監督 PID、命令列與等待階段，避免長時間 `waiting_for_legacy_chain` 被誤判為失聯。release helper 的 `post_ooc_followup_status.json` 也會以 `portfolio-ml-release-followup-heartbeat.v1` 鏡像 OOC helper custody。舊 run 保留不動，任何 custody、hash、readiness 或後續 promotion gate 不通過時仍固定 `formal_oos_allowed=false`、alpha 0，不會改寫正式 SQLite。

若 supervisor 自身在 legacy chain 停止後中斷，恢復入口 `--resume-after-legacy-chain` 會先掃描完整命令列；只要仍有相符的 direct／OOC／release process 就 fail-closed，不會重複建置，確認全部停止後才從既有 checkpoint 接續。恢復失敗會寫入獨立 recovery status，不會覆蓋仍在運作中的 primary supervisor status。

若要讓長時間 refresh 在 Windows worker 或 supervisor 因 sleep／process 中斷後自動
恢復，可由背景程序執行 `scripts\maintain_ml_direct_v3_refresh_chain.py`，並傳入
同一組 raw manifest、training-as-of、database、store output 與 training output
參數。維護器會先掃描完整命令列；任何 Direct／OOC／release target 存活時只等待，
不會平行啟動第二條 chain。全部 target 停止且 `v3_refresh_chain_status.json` 尚未
`complete` 時，才會自動呼叫 `--resume-after-legacy-chain`，沿用同一 immutable run
identity，讓 checkpoint 驗證後重建未完成年度。training output 另有 instance lock
防止重複維護器競爭；lock owner 必須同時符合 maintainer 腳本與同一個 training output
路徑的 process custody。這個程序只做 custody／retry orchestration，不寫正式 SQLite、
不直接改 latest pointer，也不放寬 `formal_oos_allowed=false`、alpha 0 或 broker
disabled。

OOS replay 由 `build_ml_allocation_oos_portfolio_replay.py` 產生 primary／verification 兩次獨立結果。它只接受 training run 內的 `allocation-ooc-replay-inputs.v1` execution ledger、Rule baseline 與 realized daily returns；缺件時會在 `ml_allocation_oos_replay_production_v4/<role>/blocked/` 留下精確 blocker，且不建立／覆寫 `latest_replay.json`。禁止用 Teacher target 或 horizon label 合成一份看似通過的 replay。

即使帳務 replay 完成，也必須查看 `formal_semantic_validation`。目前工程 artifact 固定 `verified=false`、`promotion_eligible_input=false`，因為尚未由獨立 verifier 從官方交易日曆、production Rule Champion、完整六頭 Meta OOF 與 retro raw derivation 重建每日 requested／projected holdings。Promotion Builder 另要求至少 4 個 Meta OOF folds；少一項就維持 `alpha=0`。Cash-only 訓練 state 不得在 replay 階段事後改造成非現金 state。

`build_portfolio_ml_training_shards.py --sector-membership` 只接受 `pit-sector-membership-sidecar-v1` 封套。每列必須是 `status=accepted`，並含 `source_id`、`license_id`、`source_hash`、`available_at` 與 effective range；manifest 必須帶可重算的 canonical rows／manifest hash。舊式裸 JSON array、non-accepted row、缺欄、hash tamper、cutoff 後才可得的 mapping 與 `meta_data/companies.csv` 當期快照都會使 build blocked。不要把 2026 公司清單改寫成較早 `available_at` 或歷史產業 sidecar。

Portfolio ML dataset assembler 會按 decision time 先選可適用的最新 event period，再在該 period 內選當時已可得的最新 revision；較舊 period 的晚到修訂不得覆蓋較新的適用 period。輸入 manifest 與 raw observation 的 JSON boolean 欄位只接受真正的 `true`／`false`，`0`、`1` 或字串一律 fail-closed。

正式 assembler 必須明示 portfolio state policy 與 transition custody；沒有 canonical recursive ledger 的 publication 不得宣稱已學到 turnover 或 cooldown。全種類 research 流程須接續執行下方 causal ledger overlay，Teacher target 只作 supervised label，不會回灌成下一決策日 state。Teacher 的 `cvar_loss_bp` 使用 20 日路徑最差 20% session loss 的平均 tail loss，不再以 MAE 代替。

### 建立並訓練全種類 Research Challenger

下列流程把正式配置列與所有 `research_shadow` 欄位在相同 `symbol + decision_at` 做 PIT as-of join。它會實際進入配置型 Ridge／Logistic／HGB experts 與 Meta Allocator，但永遠不能供正式 orchestrator、Promotion 或非零 alpha 使用：

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_research_shadow_union.py `
  --formal-raw-manifest <PIT_RUN>\all_field_enriched\manifest.json `
  --shadow-raw-manifest <PIT_RUN>\research_shadow_all_fields\manifest.json `
  --base-training-manifest <PORTFOLIO_TRAIN_RUN>\manifest.json `
  --corporate-action-manifest <OFFICIAL_EVENT_RUN>\manifest.json `
  --output-dir <OUTPUT>\ml_research_shadow_union

$pointer = Get-Content <OUTPUT>\ml_research_shadow_union\latest_manifest.json |
  ConvertFrom-Json
$unionManifest = Join-Path <OUTPUT>\ml_research_shadow_union $pointer.manifest_path

.\.venv\Scripts\python.exe scripts\build_ml_research_causal_ledger_overlay.py `
  --research-union-manifest $unionManifest `
  --output-dir <OUTPUT>\ml_research_causal_ledger

$ledgerPointer = Get-Content <OUTPUT>\ml_research_causal_ledger\latest_manifest.json |
  ConvertFrom-Json
$ledgerManifest = Join-Path <OUTPUT>\ml_research_causal_ledger $ledgerPointer.manifest_path
$ledgerRoot = Split-Path $ledgerManifest
$trainArgs = @(
  'scripts\train_ml_research_shadow_challenger.py',
  '--dataset-manifest', $ledgerManifest
)
foreach ($shard in Get-ChildItem $ledgerRoot -Filter 'year=*.jsonl.gz') {
  $trainArgs += '--input'
  $trainArgs += $shard.FullName
}
$trainArgs += @(
  '--artifact-output', '<OUTPUT>\research_model.joblib',
  '--audit-output', '<OUTPUT>\research_audit.json',
  '--manifest-output', '<OUTPUT>\research_training_manifest.json'
)
& .\.venv\Scripts\python.exe @trainArgs
```

官方事件 manifest 只允許 publication-time 可證明且 `result_only=false` 的停復牌／交易限制事件進特徵；除權息、減資等 result-only 事件不得反推公告時點。Causal ledger overlay 會逐 decision date 只讀 T-1 價格 prefix 與前一日 state，以整數 bp 遞迴 Rule／Risk Budget／Inverse Volatility baseline，並套用現金、檔數、單檔、週轉、band、minimum trade、cooldown 與成本限制；Teacher target 與同日 Advice 都不會餵回 state。

必須檢查 union 的 `dataset_id=research_shadow_challenger_all_fields`、causal overlay 與 training manifest 的 `dataset_id=research_shadow_causal_allocation_ledger`，且三者都維持 `research_only=true`、`formal_oos_allowed=false`、`production_alpha_bp=0`、`promotion_eligible=false`、`formal_consumer_compatible=false`。專用 trainer 沒有 alpha、Promotion 或 Formal OOS 的命令列開關；訓練 manifest schema 為 `allocation-research-training-manifest-v1`，正式 release loader 會直接拒絕。

缺值不能補成 0。某欄位若在決策時尚未 `first_seen`、已 stale、品質被阻擋或沒有 PIT provenance，樣本會保留 `value_int=null`、`observed=false` 及 data-quality mask。這代表欄位種類已進入研究訓練契約，不代表其歷史數值已被合法回補。

2026-07-30 的 final research dataset 為 22,093 rows、150 features／8 packs、4 folds。官方事件 overlay 只納入可證明 publication time 且 `result_only=false` 的停復牌／交易限制資料；`corporate_microstructure` 有 44,186／88,372 個 feature values observed、coverage 5,000 bp。Causal ledger 有 2,533 個決策日，其中 2,493 日為非現金 state，累積 792 次 add、754 次 reduce；它只讀 T-1 價格 prefix 與前一日 state，不讀同日 Advice，也不把 Teacher target 餵回下一日。

Final A/B 兩次獨立訓練完成 1,137,664 筆 base OOF 與 12,984 筆 meta OOF；model hash 均為 `sha256:dd512d6d32d853db151e971e816d514cd81c6b1cbf143289fc719ae41009a705`，audit hash 均為 `sha256:8a95519bd0f20b2cfabe119f0b91d3a160262f9f02b307ab13d114f370b6eefa`，training manifest file hash 均為 `sha256:ae511983a486317bd8c412934f280ed09e6df0aa3278e9d8ab1183d5d8337d19`，replay hash 均為 `sha256:b7dce1751da79b2269228f6c16b93615a309b3b6b4d173087de3e08392b9764a`。Family weights 是 `corporate=123`、`data_quality=2,893`、`flow_chip=123`、`fundamental=0`、`market_sector=2,118`、`price_technical=1,771`、`rule_portfolio_health=2,972`、`valuation=0 bp`，合計 10,000 bp；整個 dataset 沒有 observed 值的 family 固定為 0。Canonical research artifact 是 `ml_research_shadow_challenger_causal_official_events_a`，B 只作 deterministic 證據；兩者都不能供 Formal orchestrator 或非零 alpha 使用。

## ML revalidation 與推論安全

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_revalidation_runbook.py `
  --run-id release-v4-prod `
  --trigger production_promotion `
  --dataset-id frozen-v4-dataset `
  --owner release_owner `
  --output runbook_prod.json
```

Runbook、dataset/model/policy hash、calibration、PSI、OOF lane comparison、bootstrap、coverage、drawdown/CVaR、turnover、shadow days 與 rollback 缺一不可。歷史回放只可作 development/OOS portfolio replay，不能替代 freeze 後 Formal OOS 或 20 個真實 elapsed trading days。

訓練器 artifact schema 依流程可能為既有 `allocation-model-artifact-v2` 或 OOC
`allocation-model-artifact-v3`。每個 feature pack／5、10、20、60 日／Ridge-Logistic 或 HGB
expert 會輸出 9 個 head（benchmark／產業超額報酬、downside、MAE、MFE、realized volatility、
max drawdown、tail loss、fill feasibility）、1 個 benchmark rank 與 9 個逐 head missing masks；
Meta Allocator 的每個 expert input 因此固定為 19 維。缺 PIT-safe label 的 head 必須帶
missing reason/mask，不得補成已觀測的 0。

每日 consumer 若使用 `scripts\infer_ml_allocation_copilot.py --release-root <RELEASE_ROOT>`，
會先由 `AllocationReleaseAdapter` 驗證 release manifest、模型／前處理／校準器 hash、feature
順序、缺值政策與 dataset lineage，通過後才讀取 frozen input。相同資料列可用
`validate_frozen_rows()` 做 OOC→release parity；任何 mismatch 都停止 ML path。外部整數
校準器必須是跨 fold、單調的 0–10,000 bp mapping；現有 OOC calibration 仍是
`oof_diagnostic_only` 時不可發布，consumer 會維持 Rule-only 與 alpha 0。

若只要驗證已產出的 OOC audit，不執行推論，可使用
`scripts\validate_ml_release_parity.py --release-root <RELEASE_ROOT> --input <INPUT> --ooc-audit <AUDIT> ...`。
它只讀 release 與 frozen rows，輸出 `matched` 或 `blocked`；不改寫模型、正式資料庫、
promotion pointer 或 alpha 狀態。

### Post-freeze 四個缺值特徵的 bounded 修復候選

若要在隔離 TEMP 產生新的 market repair candidate，可使用：

```powershell
.\.venv\Scripts\python.exe scripts\build_ml_allocation_post_freeze_feature_repair.py `
  --parent-input <PARENT_ALLOCATION_INPUT_V2_JSON_GZ> `
  --expected-parent-input-compressed-hash sha256:<64-hex> `
  --raw-dataset-manifest <OFFICIAL_ALL_FIELD_ENRICHED_MANIFEST_JSON> `
  --expected-raw-publication-manifest-hash sha256:<64-hex> `
  --expected-raw-dataset-manifest-hash sha256:<64-hex> `
  --expected-decision-at <MACHINE_DECISION_ISO8601_WITH_TIMEZONE> `
  --expected-price-date <OFFICIAL_T_MINUS_1_DATE> `
  --calendar-database <READ_ONLY_OFFICIAL_CALENDAR_DATABASE> `
  --output <TEMP_POST_FREEZE_SHADOW_FEATURE_REPAIR_JSON_GZ> `
  --audit-output <TEMP_POST_FREEZE_SHADOW_FEATURE_REPAIR_AUDIT_JSON>
```

這個命令先以舊 v2 consumer 驗證父輸入，再以既有
`OfficialTradingCalendar` 讀取 `--calendar-database` 的唯讀官方交易日證據，最後
讀 official raw publication 的 TAIEX `收盤指數`。只有 calendar 證明的 expected
T-1 與前一個官方交易日都存在，且 source row/value hash、quality、event／availability
timestamp 都不晚於決策時間，才會以 Decimal 推導 `漲跌點數` 與 `漲跌百分比`。日期不
由原始列排序猜測；週末／有明確休市證據的日期可跳過，未知的平日、缺少 calendar
證據、缺前收、重複日期、內容竄改或 future evidence 會保留 blocker。

v3 contract 會排除 `technical_indicators.涨跌` 與
`technical_indicators.漲跌(+/-)`；兩者的來源語意是分類／legacy 欄位，`+`、`-`、
NULL 不能轉成 numeric。舊 v2 input 與 model registry hash 保持不變。v3 帶有
`feature_contract_hash`、derived source manifest、逐 feature 推導 proof 與
`new_release_required=true`，目前 `infer_ml_allocation_copilot.py` 會拒絕它；
需先發布明確的新 model／feature schema 才可作正式 inference。該命令只寫指定的
隔離 output 與 audit，不寫 SQLite／D 原始資料、不訓練、不下單；完整前後計數與
實際 source hash 應記錄在 `docs/06_qa/V4_AUTOMATED_REVIEW_2026_09_07.md`。

Full-market OOC 訓練會以 deterministic causal row sample 估計 median，並以完整 train stream 計算 mean／variance；final-meta 的寬 memmap 以 bounded batch 開關讀寫，避免 working set 超過 4 GiB gate。這只改變記憶體配置與可續接性，不放寬 fold cutoff、OOF custody、future-prefix 或 promotion gate。

若要先驗證單一主 horizon 的成本後增益，可在隔離輸出使用
`scripts\train_ml_allocation_out_of_core.py --profile minimal_linear_shadow --algorithm ridge_logistic --horizon <H>`。
此 profile 強制只訓練 Ridge／Logistic 與一個明確 horizon；未提供恰好一個
`--horizon`，或混入 HGB，命令會停止。預設 `full_shadow` 維持既有多 horizon／雙演算法
研究流程，兩者都只產生 research／shadow artifact；profile 本身不改 Rule、Advice、正式
OOS 或 broker 權限。比較時要以同一 frozen rows、同一成本模型、Equal Weight 與 Rule
baseline 檢查超額、回撤、換手、樣本數與不確定區間，再決定是否擴張特徵或 HGB。

Direct numeric store 的 heartbeat 會在每個來源 shard 驗證至少每 100,000 筆 raw row，或連續 30 秒沒有進度事件時，發布 `raw_spool_source_shard_<year>_rows_<n>_processed`；完成 shard 後再發布 `raw_spool_source_shard_<year>_complete`、`year_raw_spool_complete` 與 `year_labels_complete`。進入年度 assembly 後，會以相同的列數／時間節奏發布 `assembly_decision_<date>_rows_<n>_processed`，接著是 `year_assembly_complete`、`year_artifacts_complete` 與 `year_directory_finalized`；`processed` 狀態只表示已讀取驗證或組裝的進度，不是完成或 checkpoint，所有狀態都不能取代年度 manifest 或 hash-bound `latest_manifest.json`。因此長時間重建可由受控 continuation 自動判斷目前真實階段，無須人工猜測或手動標記進度。

Windows 若由 venv launcher 啟動另一個 Python worker，heartbeat 的 PID 可能與 supervisor 保存的 launcher PID 不同。OOC continuation 只接受完全相同的 PID，或仍存活且位於該 launcher 子孫鏈中的 worker PID；無法證明 parent-chain 的 heartbeat 會被忽略，不會因此放寬完成、hash 或 custody gate。

目前 canonical official-event post-policy training 已涵蓋 11 symbols、22,093 rows 與 4 個 expanding folds，產生 426,624 筆 base OOF predictions、12,984 筆 meta OOF predictions。這代表訓練／OOF／Meta 流水線已實際執行，不代表 Formal OOS promotion 通過。正式 compact model artifact hash 為 `sha256:92668aa574967990fa560aef8a48e595296eb22f3fef2a4264cff08210d78b6d`，replay hash 為 `sha256:ba0eb2456569d55d5981d97b612f109818c4acc01881e07ca9d1d6bf2042092d`。

目前 Formal calibration ECE／Brier、PSI、成本後 alpha OOS lane comparison、bootstrap、promotion coverage、MDD／CVaR、turnover 與 20 個真實 shadow trading days 均為 **`NOT EVALUATED`**。Engineering 4-fold training 與測試通過不等於模型績效已通過；在正式 promotion evidence 齊備前，正確狀態是 `formal_oos_allowed=false`、有效 alpha 0。

### 非零 alpha 的可信 custody

每日正式鏈不接受人工作業環境變數提供 promotion artifact path：

1. 05:17 `baldr-ml-promotion-evidence-daily` 從固定 full-market OOC、雙 replay、Shadow 與 metrics custody 建立 unsigned evidence；缺件時只寫 blocked status，不發布 compatible pointer。
2. 05:18 `baldr-ml-promotion-authority-daily` 只讀固定 evidence pointer，以 Windows user-scope DPAPI 保護的 issuer secret 驗證 machine Gate；只有 evaluator 已證明最小非零 lane 合格時才簽發 authorization。
3. 05:20 `baldr-ml-allocation-copilot-daily` 只讀 `OUTPUT_ROOT/release_v4/ml_promotion_authority/latest_authorization_pointer.json`，並再次核對 authorization 的 model／dataset 與本次真正推論 release 完全相同。

若正式 OOC store 尚未達 full-market readiness，Evidence 與 replay status 的 blocker 會保留可機器解析的 `formal_ooc_dataset_full_market_not_ready:<readiness_check,...>`；例如 `pit_sector_membership_present` 或 `causal_non_cash_portfolio_ledger_present`。Direct numeric v4 的官方 halt/resume timeline 會在每 row 保存 `officially_tradable`／`officially_blocked`，as-of 不可證明時維持 `unknown_*` 並阻擋 replay。Evidence 會驗證 official market-event pointer、manifest 與 canonical event file；若只是相同 `canonical_events_hash` 的 wrapper／duplicate metadata 重發布則視為 no-op，若 canonical hash 改變才輸出 `formal_ooc_corporate_action_custody_stale:<field,...>` 並不消費舊資料。排程會在下一輪自動重試；在這些資料具備完整 PIT custody 前，不得以重訓、研究 shadow 或目前公司快照取代，compatible pointer 不會更新，alpha 維持 0。

舊版 CLI 的 promotion artifact path 參數僅為相容 parser 形狀，在正式 orchestration 中會被忽略，排程 wrapper 也不傳入。issuer key 不得寫入 repo、文件、command line、status 或 log。Verifier 會檢查 issuer HMAC、custody root/id、registry revision、decision validity/freeze time，並重新計算 evidence、model、dataset、OOF、shadow 與 registry 實體檔 SHA-256；驗證不通過即 alpha 0。顯式部署 trust 設定只能替換或縮小可信邊界，不能注入 artifact、繞過固定 pointer 或直接授權 alpha。不得手改 `formal_oos_allowed`，也不得把 authorization JSON 本身當成已驗證能力。

### ML promotion evidence automatic catch-up

快速資料更新在長時間工作開始前會先寫入 `status=running`、`run_id`、`process_id` 與 `started_at`；完成後才寫入 terminal status 及 `completed_at`。下游 freshness／evidence 只接受完成且未過期的 `passed`／`passed_with_warnings`，因此不會消費半完成的更新。

05:17 的 Promotion Evidence runner 會唯讀檢查
`OUTPUT_ROOT/scheduled/data_update_quick/latest_status.json` 的
`check_overview_after`。若 `daily_data` 或 `technical_indicators` 的最晚日期尚未涵蓋
原始下一個決策日的 strict T-1，系統會依官方交易日曆向後掃描最多 31 個曆日，
自動選擇最近一個已具備 T-1 證據的決策日；若資料已完整，則維持下一個預備決策日。
這是選日同步，不是 promotion 授權：不讀未來資料、不寫正式 SQLite、不更新 compatible
pointer，正式 OOC／PIT／replay／shadow／authority 任一缺件仍維持 blocked、alpha 0。

Evidence runner 會先驗證 upstream `data_update_quick` status 為 `passed` / `passed_with_warnings`，且 `daily_data` 與 `technical_indicators` 的 latest date 不得超過當前台北日。status 遺失、failed、格式破損或出現未來日期時，runner 在選日前直接寫 `blocked`，不會猜測或使用未證明的未來決策日。

Evidence `latest_status.json` 使用 schema v3，並保存
`requested_decision_at`、`decision_selection_mode`、`decision_selection_reason`、
`decision_selection_attempts`、`latest_core_feature_date`、
`upstream_data_update_proof_state` 與 `upstream_data_update_proof_reason`，可直接稽核是否發生自動補跑和 upstream proof 是否完整。

### T-1 causal portfolio completeness

正式配置投影必須提供 `CausalPortfolioState`：`as_of_date` 嚴格早於 decision date、`AllocationWeightContract` 連同現金總和 10,000 bp、完整列出所有現有持倉 symbol，並帶可重算的 `state_hash`。每個 symbol 的 context `current_weight_bp` 與 request cash 必須和該 state 完全一致。缺 state、漏持倉、日期／hash／cash／context 不一致時，系統不猜 current=0：結果會是 `NO_NEW_POSITION`、`executable_weights=null`，但保留 target 與 diagnostics 供排錯。

> Gate 2–7 的工作台帳可在
> [External Validation Register](../06_qa/GATE_2_TO_7_EXTERNAL_VALIDATION_REGISTER.md) 查看，
> 但其中 `4/3 complete` 是 2026-07-30 的歷史投影，不是 current SSOT。2026-08-29
> Evidence 必須分層為 formal/canonical credit 未授予、歷史 working-copy=`1/3`、
> owner-approved UI projection=`3/3`、sidecar pending=`10`、multi-day=`3/3`，且
> `formal_credit_authorized=false`。Current 全程式狀態以
> [Project Snapshot](../00_core/PROJECT_SNAPSHOT.md) 頂部與
> [Program Status Rebaseline](../06_qa/PROGRAM_STATUS_REBASELINE_2026_08_29.md) 為準。

> Daily / Weekly / Monthly / Maturity / Failure 的完整操作契約見 [V3.3 Engineering Closeout](../06_qa/V3_3_ENGINEERING_CLOSEOUT_2026_07_12.md)。`verify_artifact_lineage.py` 只做唯讀工程驗證，fixture 不得冒充 forward/paper/live evidence。

> 下方日期標示為 2026-07-13 或更早的 Gate 數字是歷史操作紀錄；若與本頁頂部
> current engineering 區塊衝突，以 `PROJECT_SNAPSHOT.md` 的 Canonical Current Status、
> External Validation Register 最新 append-only revision 與具時間戳的 readiness artifact 為準。

## V3 pruning review package（唯讀提案）

執行 `scripts\build_v3_pruning_package.py --input <metrics.json> --output <package.json>`，可把已成熟的 effectiveness metrics 轉成 `retain`、`restrict`、`downweight`、`retire` 或 `defer` 審查提案。樣本不足、必要指標缺失或人工驗證未完成時必定 `defer`。所有 proposal 固定 `apply_action=false`、`review_required=true`，package 固定 `auto_trading=false`；不得用此輸出直接修改推薦權重、threshold、production scheduler 或交易狀態。

> **歷史整合段落基準**：2026-07-13。本文頂部 2026-08-29 metadata 與 current
> rebaseline 優先；本段只保留當時系統工程整合判讀。主 UI 入口仍為 `ui_qt/main.py`。

## 2026-07-13 系統工程整合判讀

這次整合必須拆成六個狀態判讀，不可用單一「完成」取代：

1. `engineering_integration=verified`：A～F committed handoff、跨流 contract、唯讀 smoke 與 pure verifier 已通過工程驗證。
2. `historical_ml_shadow=continue_shadow`：只顯示 dataset／model／prediction identity 與 shadow diagnostics；`formal_oos_allowed=false`，不參與 ranking、Score、Advice、Portfolio 或 Exit。
3. `dashboard_visibility=verified`：Daily Decision Desk 唯一實例位於「市場探索 > 市場總覽」；Workbench「決策來源」只做導覽。
4. `forward_evidence=pending`：唯讀 replay 或 working-copy rehearsal 不等於真實週期 evidence。
5. `source_acceptance=pending`：source／license 尚未逐項 accepted；official monthly／quarterly row count 為 0、corporate-action coverage unknown 時，必須顯示缺口，不得解讀為業務數值為零。
6. `production_automation=pending`：scheduler、auto promotion、broker action 均未啟用；ML production blend alpha 固定為 0，且目前沒有通過 real frozen artifact smoke。

### 市場總覽與資料可見性

1. 從左側進入「市場探索 > 市場總覽」。這是唯一 Decision Desk instance；從 Workbench 進入只會導向同一畫面。
2. 檢查月營收、三大法人、信用交易、TDCC 與券商分點等來源卡。卡片的 status、row count、available date 與 warning 是資料可見性，不是推薦分數。
3. `row_count=0`、MISSING、DEGRADED 或 coverage unknown 都代表來源缺漏／受限；不可補成中性值，也不可當作「指標為零」。
4. 更新時保留 loading；若較早查詢晚於新查詢返回，stale-result guard 會忽略舊結果。錯誤只降級該來源並保留 warning，不改 action、focus 或 Score。
5. 券商查詢採背景載入；week／month 與股票明細應在畫面恢復互動後判讀，勿以 loading 中的暫態內容做結論。

### V4.2 C 線：每日決策呈現流程

這條流程把既有唯讀 DTO 串成「市場總覽 → 產業／市場探索 → 關鍵股研究 → 觀察清單 → 持倉覆盤」的人工判讀路徑。UI 只適配與呈現既有來源，不重新計算推薦、機率、權重或交易結果。

1. 從「市場探索 > 市場總覽」開始。先確認決策日、資料品質、source trace 與 warnings，再閱讀大盤、產業與個股焦點卡。焦點卡的動作固定是「研究」；即使是風險焦點，也不等於正式 `NO_NEW_POSITION`。
2. 由焦點卡或既有下鑽入口開啟重點產業／個股研究。研究報告可呈現既有 Recommendation／Portfolio Advice；只有真正帶入 Advice DTO 時，才可顯示「買進候選／持有／減碼候選／退出候選」等 Advice 動作。
3. 將要追蹤的股票放入「觀察清單」，選取清單項目後查看保存的分數、排名百分位／方法、樣本數、決策日／資料日、理由與來源 ID。保存結果是研究參考，不會在 UI 即時重評分。
4. 在觀察清單或持倉頁選取股票，可開啟同一個個股研究報告；研究報告頂端與持倉表使用相同呈現欄位：動作適合度、排名分數、校準機率、證據／信心／樣本、適用期間、成本基準、理由、風險與失效條件。
5. 在「持倉管理」查看動作適合度與權重欄位。Condition Monitor 的 `valid`、`warning`、`invalid` 只會映射為「持有」、「減碼候選」、「退出候選」；這是待覆盤候選，不是下單或自動調倉指令。

欄位判讀與安全限制：

- `校準機率` 只有上游明確提供 0–10,000 bp 且標記為 available 才會顯示百分比；否則顯示「不可用（研究中／不可用）」，不把排名分數當機率。
- `成本後獲利機率` 是獨立欄位，只有明確 after-cost evidence／校準輸入才顯示；不得以 ranking score、毛報酬或文字信心代換。`證據信心`、`決策信心`、`樣本數` 與 `適用期間` 也各自保留，缺值顯示未知／研究中。
- Workbench 的「單一路徑 / Research Workflow」按鈕只切換既有 workspace；第 3 段「關鍵股研究」必須由市場焦點、觀察清單或持倉列選取股票後開啟，不能由 UI 自動挑股。
- `目標／目前／差距` 使用整數 bp。只有既有 Portfolio Advice 或持倉來源摘要明確提供的欄位才會顯示；缺欄位為「未知」，不由畫面自行相減，也不把未知當成 0。
- `研究`、`降級`、`缺漏`、`不可用` 是證據狀態，不代表報酬為零或看空；請先看理由、警告、資料日與來源追溯。
- 全流程為唯讀呈現，不建立委託、不寫入交易／持倉、不修改 Recommendation／Portfolio，也不解除 Formal evidence、scheduler 或 broker Gate。

常見問題：

- 市場總覽沒有焦點卡：先看 snapshot 的空狀態、來源品質與 warnings；沒有 DTO rows 不等於沒有投資訊號或 Gate 通過。
- 觀察清單顯示 `not_in_result`：代表目前沒有該股票的保存結果，不等於看空；請回到 Recommendation 產生並保存新的研究結果。
- 持倉權重差距顯示未知：檢查上游 Portfolio Advice／`source_summary` 是否提供 `target_weight_bp`、`current_weight_bp`、`weight_gap_bp`；不要手動在 UI 補值。
- 持倉目前分數／Regime 顯示待更新：確認持倉來源摘要是否已有 `current_total_score`／`current_regime`；UI 不會自行掃描全市場重建分數。
- 校準機率顯示研究中／不可用：目前沒有合格 calibration artifact 或上游沒有明確機率欄位，維持研究模式即可。

### Evidence 模式與 ML shadow

- `projection_only` 只投影與驗證輸入，不建立 working copy。
- `working_copy_e2e` 只允許明確指定、位於 `DATA_ROOT` 之外的 working-copy DB 與輸出目錄；正式來源必須唯讀，完成後應比對正式 DB hash／mtime 未改變。
- `degraded` 是成功保留缺口的安全結果，不是正式 closeout。缺 market、Advice、paper、health、outcome、weekly、signal、ML adapter 或 lineage parent 時不得升級狀態。
- ML shadow 畫面只供研究診斷。看到 `continue_shadow`、prediction 或 challenger metadata，不代表 formal OOS、promotion、production alpha 或投資有效性。

排錯時先看來源卡與 warnings：缺來源／row count 0 回到對應 source acceptance；working-copy 路徑落在正式資料根目錄時改用外部暫存路徑；frozen artifact 不存在或驗證被擋時維持 alpha 0，禁止用 fixture 冒充真實 artifact。

### Terra Development Dataset V0（開發者／研究操作）

這是 CLI-only、development-only 的資料集生成工具，不會出現在主 UI，也不會改變 Score、Recommendation、Advice、Portfolio、Exit 或 scheduler。2025 已永久標記為 `seen_oos`，只可作 development；它不再是 formal OOS。2026 成熟 outcomes 只供離線 evaluation，永不進 fit。

1. 將 `--development-output-root` 指向 `DATA_ROOT` 外部的資料夾，例如 `C:\Temp\technical_analysis_development_output`；工具拒絕正式資料根與正式 SQLite 檔。
2. 指定尚未使用的 `--generation-id`。同 ID 的第二次執行會停止，不覆寫既有 artifact。
3. 只允許四類 core source：daily price、technical indicators、market indices、industry indices。fundamental／broker 不會讀取，也不會補成 0。
4. 每筆 feature 只用前一交易日（T-1）資訊，且可得日不晚於 decision date；universe 使用最少 252 日的 `conservative_observed_history`，並將 listing／delisting metadata 缺口列入 diagnostics。
5. corporate-action coverage 在 V0 未提供時，輸出仍可供研究，但必定顯示 `research_only_degraded`；不得把它解讀成 clean dataset 或 formal OOS。
6. 讀取 `generations/<generation-id>/manifest.json`：確認 `fit_row_count` 只對應 2025、`evaluation_row_count` 只對應 2026、`formal_oos_allowed=false`、`production_blend_alpha_bp=0`、`formal_rule_only_path_unchanged=true` 及 `zero_formal_write=true`。

7. 執行 `scripts/run_terra_development_research.py` 時，`--manifest` 與 `--dataset` 必須來自同一 generation directory；工具會在 fit 前重算 row counts 與 semantic content hash。`--output-root` 必須在 `DATA_ROOT` 外且尚不存在，report／projection 會成對 atomic publish。
8. 若要在 UI 查看，將 `RESEARCH_CONSOLE_PROJECTION` 指向該 run 的 `ResearchConsoleProjection.json` 後啟動 UI；畫面只呈現 frozen DTO，不重算 Rule／ML 或讀取正式 DB。

若 CLI 回報 source schema、output root、T-1、日期範圍或 generation already exists 錯誤，停止操作；不要改動正式 DB、不要覆寫 artifact，也不要以 2025 結果調參後重新宣稱 formal OOS。

Corporate-action availability history 是 Terra V0.1 前置的 staging-only 輔助工具，不是正式資料 apply。執行 `scripts/build_corporate_action_availability_history.py` 時，必須提供 `--evidence-json`、`--coverage-json`、`--as-of-date` 與明確的 `--output-root`；CLI 會先驗證 `--as-of-date`，日期無效時不讀取任何 evidence／coverage JSON。兩個 JSON 根都必須是 object rows 的 list，否則分別以 `corporate_action_evidence_rows_invalid` 或 `corporate_action_coverage_rows_invalid` 停止，且不建立輸出。JSON 語法／編碼不合法時回報 `corporate_action_<label>_json_invalid`，檔案不存在或無法讀取時回報 `corporate_action_<label>_read_failed`，`--as-of-date` 不是有效 ISO 日期時回報 `corporate_action_as_of_date_invalid`；三者都在建立 output root 前 fail closed。`--output-root` 應使用 `DATA_ROOT` 外的 TEMP／development 路徑；若環境已設定 `DATA_ROOT`，CLI 會拒絕該 root 與其子路徑。三個 canonical output 任一已存在時會以 `corporate_action_output_exists` 停止，不覆寫既有 bytes；新輸出先寫入同 root 的唯一 staging directory，完成後才逐檔發布並清理 staging。這降低半套輸出風險，但不代表三檔具單一 filesystem transaction，也不構成 corporate-action coverage 已接受、Formal evidence 或 forward credit。

### 富邦行情 PIT-Safe Shadow Decision Pipeline CLI（開發者／研究操作）

這是 CLI-only、shadow-only 的 Fubon 行情決策評估工具，不會影響正式 Rule-only 決策結果，也不會取得 Formal Evidence Credit。

```powershell
.\.venv\Scripts\python.exe scripts\inspect_fubon_shadow_decision.py `
  --authorization <path-to-authorization-json> `
  --input <path-to-fubon-observation-json> `
  --universe <path-to-universe-json> `
  --strategy-config <path-to-strategy-config-json> `
  --decision-timestamp "2026-07-26T00:00:00+00:00" `
  --output-root $env:TEMP\technical_analysis_fubon_shadow `
  --candidate-db $env:TEMP\technical_analysis_fubon_shadow\fubon_candidates.sqlite
```

- `--authorization` 可省略並載入預設 shadow 授權；`--input`、`--universe`、`--strategy-config` 與 `--decision-timestamp` 必須明確提供。
- `--output-root` 可省略為只輸出 stdout；`--candidate-db` 可將驗證後資料寫入獨立 development SQLite。兩者均拒絕正式資料根、正式 DB 與 repository 內路徑。
- 嚴格驗證 `available_at <= decision_timestamp`；缺少可得時間不會猜測，hash 不符或 identity 衝突會隔離。
- `formal_decision_influence_allowed=false`、`formal_evidence_credit_authorized=false`、`production_blend_alpha_bp=0` 固定不可覆寫。
- 在建立明確的 Fubon 欄位到既有規則輸入映射前，Score、Recommendation、Portfolio、Exit 一律回傳 typed `not_computable`，不得以未改變的 baseline 假裝已完成 shadow 計算。

### MOPS 每日研究用財報發布 Freshness、Outage 與 Revision 診斷 CLI（開發者／人工研究操作）

這是人工可執行的 MOPS EZSearch 季報公告發布時間（F26–F29）每日 Freshness、Outage、與 Revision/Correction 診斷工具。僅供研究與 shadow 投影，不會寫入正式 SQLite 或 FA_Data，也不取得 Formal Evidence Credit。

```powershell
.\.venv\Scripts\python.exe scripts\fetch_mops_daily_research_freshness.py `
  --start-date 2026-07-27 `
  --end-date 2026-07-28 `
  --output-root C:\Temp\technical_analysis_development_output\mops-daily-freshness `
  --prior-artifact C:\Temp\technical_analysis_development_output\mops-daily-freshness\runs\<prior-run-id>.json `
  --prior-artifact-sha256 <prior-artifact-64-hex-sha256> `
  --live --confirm-live-readonly
```

- **離線與連線模式**：預設可用 `--fixture-file` 做離線測試與診斷比對；若要連線 MOPS 官方 HTTPS 介面，必須明確帶入 `--live --confirm-live-readonly` 旗標。兩種模式互斥，單獨提供 confirm flag、同時提供 live 與 fixture，或 `timeout <= 0` 都會拒絕執行。提供 `--prior-artifact` 時必須同時提供該檔案真實 bytes 的 `--prior-artifact-sha256`；hash 不符即 fail closed。
- **查詢邊界**：僅允許 MOPS 官方 HTTPS 介面、僅查詢 F26–F29、單次查詢窗口上限 31 天、單一查詢回傳滿 1000 筆觸發 1000-row cap 失敗封閉；M31 永久排除。
- **輸出路徑**：`--output-root` 嚴格通過 `validate_development_output_root` 檢查，拒絕 `DATA_ROOT`、正式 DB、repo 根目錄、路徑穿越與 symlink escape。
- **Immutable Run Artifacts 與 Atomic Projection**：
  - 每次執行之 raw/research diagnostic 會以不可變且包含 SHA-256 Hash 的檔名寫入 `<output_root>/runs/<run_id>.json`。
  - 最新 sanitized 投影會以 atomic write 寫入 `<output_root>/latest_sanitized_projection.json`。
- **Freshness / Outage / Revision 狀態判讀**：
  - `observed`：16 個不重複的 market × item key 完整成功、每筆 `source_status=success`、response SHA-256 合法、Schema 與 Row Conservation 無誤；不能以重複 key 補足遺漏 key。
  - `observed_empty`：16 組 query 完整成功，但當期事件數為 0（此非 Outage）。
  - `capture_failed`：網路/HTTP/JSON/格式錯誤，會寫入 append-only failure diagnostic artifact 並以 non-zero (exit 1) 結束，不偽造空成功或 mapping。
  - `baseline_missing`：未提供 prior artifact 時無法宣稱多日證據。
  - `stale`：當指定 `--expected-through` 且查詢 end_date 早於 expected-through 時標示。
  - `multi_day_evidence_ready=true`：prior 與 current 必須是同一 query window、兩者 query matrix 完整，且實際 capture 發生在不同的台北曆日；同日重跑永遠不能換算成多日證據。
- **Research Console 唯讀投影**：在啟動 UI 或 Research Console 時以 `RESEARCH_CONSOLE_PROJECTION` 設定顯式投影路徑（如 `latest_sanitized_projection.json`），即可唯讀呈現 diagnostics。`capture_failed`、`stale`、matrix incomplete、baseline missing 與不可比較 window 都會成為 blocker，使整體狀態 degraded；未知 MOPS projection schema、治理欄位不一致、artifact hash 不合法或含 raw／credential-like forbidden keys 時 fail closed。安全邊界旗標 `formal_oos_allowed=false`、`formal_credit_authorized=false`、`production_blend_alpha_bp=0`、`fubon_shadow_usable=true`、`fubon_formal_credit_allowed=false` 固定保留。

### P0-13 機器稽核工具 CLI（GEMINI-P0-13-MACHINE-AUDIT-AND-BLOCKER-REDUCTION-V1）

這是 CLI-only 的唯讀 P0-13 機器稽核工具，對全部 13 項 P0 候選資料源執行高效率、可重跑的機器驗證，將 machine-verified、degraded 與缺 artifact／probe 的狀態分開呈現，並產出極簡 Owner Decision Packet 與 audit JSON：

```powershell
.\.venv\Scripts\python.exe scripts\run_p0_candidate_audit.py `
  --decision-date "2026-07-25" `
  --output $env:TEMP\technical_analysis_p0_audit\p0_audit_results.json
```

- `--decision-date` 必須明確提供 ISO 日期。
- 輸出 JSON 包含 13 項 P0 來源完整驗證矩陣與 `machine_verified_sources`、`degraded_sources`、`unavailable_sources` 統計。缺官方公告時間、probe 未回傳或 MOPS artifact 未提供時會保留 blocker；不得因 owner 問題存在而將它們計為已解除。
- 自動寫入 audit packet 至 `%TEMP%\technical_analysis_gemini_handoffs\GEMINI-P0-13-MACHINE-AUDIT-AND-BLOCKER-REDUCTION-V1.json`；其 `status=audit_generated_not_validation_handoff`，不宣稱已完成 Git、型別或完整 pytest 驗證。真正交接必須在獨立驗證後補齊終態。
- 嚴格守護 `downstream_eligibility=none`、`human_decision=requires_human_acceptance`、`production_scheduler_allowed=false` 與 `formal_oos_allowed=false`；絕不寫入正式 DB 或影響推薦與交易決策。
- Windows 主控台若仍使用 CP1252，CLI 會先將 stdout／stderr 切到 UTF-8；因此直接執行 `--help` 也能顯示完整繁中說明，不會因編碼錯誤中止。

### P0-13 官方證據與就緒度強化 CLI（GEMINI-P0-13-OFFICIAL-EVIDENCE-AND-READINESS-HARDENING-V1）

這是 CLI-only 的唯讀 P0-13 官方證據與就緒度 (Readiness) 稽核工具，對全部 13 項 P0 候選資料源執行非破壞性、可重跑的機器驗證，產出「Machine Evidence Matrix」與「5 大群組化 Owner 決策包」：

```powershell
# 預設非連線模式（不發網路請求；未提供 artifact 的來源維持未探測／缺件）
.\.venv\Scripts\python.exe scripts\run_p0_source_evidence_audit.py `
  --decision-date "2026-07-26" `
  --output $env:TEMP\technical_analysis_p0_audit\p0_evidence_hardening.json

# Live 探測模式（必須同時帶入 --live 與 --confirm-live-readonly）
.\.venv\Scripts\python.exe scripts\run_p0_source_evidence_audit.py `
  --decision-date "2026-08-27" `
  --live --confirm-live-readonly `
  --mops-quarterly-artifact <MOPS_STATEMENT_AVAILABILITY.json> `
  --output $env:TEMP\technical_analysis_p0_audit\p0_evidence_hardening_live.json
```

- `--decision-date` 必須明確提供 ISO 日期。
- 預設模式不發起任何網路請求；Live 探測模式未提供 `--confirm-live-readonly` 時會立即拒絕執行。
- `--output` 輸出路徑目前嚴格受限於 OS TEMP；尚未定義受治理的 candidate-safe 根目錄，因此也拒絕寫入 repository、正式 DB 或正式 Evidence DB。
- 稽核會同時附上 `p0-source-acquisition-routes.v1`：固定 13 個 P0 source denominator 與目前 27 條受治理候選 route，每個來源至少有 2 條 route。route registry 只說明可取得路徑與 provenance，不會因存在 alternate route 而自動授予 source acceptance。
- 現行 live probe 已接上五條 fallback：TWSE 三大法人／信用交易 → TPEx OpenAPI、TDCC legacy CSV → TDCC OpenAPI `1-5`、TWSE 月營收 OpenAPI → MOPS `t187ap05_L.csv`、TPEx 月營收 OpenAPI → MOPS `t187ap05_O.csv`。輸出會保存實際 route、前一路徑失敗原因與 fallback lineage；官方明確無事件會標示 `official_no_data`，不再與 schema mismatch／network failure 混為同一個 `unavailable`。
- 13 項 P0 來源自動收斂為 5 大群組化 Owner 決策（除權息/減資分割、交易限制 Preflight、三大法人/信用交易、TDCC 集保持股、月營收/季報 Artifact），僅要求 Owner 判斷內部研究意圖/條款接受度，完全無需審視逐列 raw data。
- `twse_microstructure` 群組另提供五個 source 的逐項 machine recommendation；目前全部固定為 `deferred`，且 `ready_for_owner_review=false`。這只是可重算的機器建議，不是 owner/reviewer 決議，也不會寫入 source acceptance registry。
- Timestamp semantics 會分開投影官方公告 timestamp／date-only、有效期間、交易日觀測、decision-time observation、first-observed、capture time 與 HTTP headers。HTTP `Date`／`Last-Modified`、capture time 與 first-observed 均不得升格或回填為官方公告時間。
- `microstructure.full_delivery` 與 `microstructure.limit_lock` 的現有官方 probe 只證明交易日狀態／行情觀測；limit-lock 已改讀符合 daily limit／quote schema 的 TWSE `TWT84U`，不再用 `MI_INDEX`。若 `TWT84U` 有正常行情列但鎖死事件為 0，輸出仍保留 `probe_outcome=observed` 與完整 raw／blocked conservation，語意是「官方 payload 可讀、當日沒有符合鎖死條件的 event」，不是 endpoint 或 parser 失敗；`official_no_data` 則保留給 endpoint 明確回傳 no-data status。limit-lock 本來就不是公告來源，因此 blocker 是 `decision_time_availability_not_proven`，不是 `official_publication_timestamp_missing`。停復牌、處置與分盤目前仍缺可引用的 row-level 官方公告時間。
- MOPS numeric PIT candidate 的 artifact identity 固定為 `mops.statement.publication`；validator 只透過版本化 `p0-candidate-source-alignment.v1` 將 normalized row 對齊 P0 contract `pit.quarterly_financials`，並保留 `artifact_source_id`。未知 candidate source ID 會 fail closed。這只是 identity mapping，不會套用 source acceptance、降低 coverage 門檻或改變 `downstream_eligibility=none`。
- `--mops-quarterly-artifact` 除了接受原始 `mops.statement.publication` wrapper，也接受 `scripts/validate_mops_quarterly_artifact.py` 輸出的 normalized JSON row list。normalized 入口會逐列重驗 P0 source identity、consolidated／uncorrected、hash、revision、publication→available date 順序與 numeric lineage；缺欄、錯 source 或不合法 hash 會 fail closed。它只是重用已驗證的 candidate evidence，不會把 normalized rows 當成新的官方抓取、也不會授予 license／owner acceptance／Formal credit。
- 富邦只可作相符 microstructure source 的 shadow corroboration；輸出會分開顯示 `fubon_shadow_usable` 與固定 `fubon_formal_credit_allowed=false`、`production_blend_alpha_bp=0`，不得用富邦補造 TWSE 官方公告時間。
- 產出稽核草稿 handoff JSON 至 `%TEMP%\technical_analysis_gemini_handoffs\GEMINI-P0-13-OFFICIAL-EVIDENCE-AND-READINESS-HARDENING-V1.json`；其 `status=audit_generated_not_validation_handoff`，不宣稱 pytest、mypy 或 Git 終態已通過。
- 嚴格守護 `downstream_eligibility=none`、`human_decision=requires_human_acceptance`、`production_scheduler_allowed=false` 與 `formal_oos_allowed=false`；所有 formal clock zeros 維持 0。

### P0 官方條款／授權候選證據擷取（只讀、候選）

`scripts/capture_p0_license_evidence.py` 用來把「可取得的官方條款／OpenAPI 頁面」變成可交給 Owner／Reviewer 的候選證據，不會把 URL 存在 route registry 就當成已授權。它只從 `p0_source_acquisition_routes.py` 的 allowlist 取出 3 個唯一 URL（TWSE、TPEx、TDCC），保存 response status、HTTP header 摘要、內容 SHA-256 與有限關鍵詞 flags；不保存頁面全文，也不寫正式資料庫、source acceptance registry、Score、Advice、Portfolio 或排程。

```powershell
# 預覽：不發網路請求，只列出預計擷取的 3 個官方條款／OpenAPI URL
.\.venv\Scripts\python.exe scripts\capture_p0_license_evidence.py `
  --decision-date "2026-08-28" `
  --output $env:TEMP\technical_analysis_p0_license_evidence\preview.json

# 受控候選擷取：只有精確 token 才會做 bounded GET；仍不代表 license accepted
.\.venv\Scripts\python.exe scripts\capture_p0_license_evidence.py `
  --decision-date "2026-08-28" `
  --confirm capture-p0-license-evidence `
  --timeout-seconds 15 `
  --max-bytes 65536 `
  --output $env:TEMP\technical_analysis_p0_license_evidence\capture.json
```

- `--output` 必須位於 OS TEMP；工具拒絕 repository、`DATA_ROOT` 與正式 SQLite 路徑。
- 預覽的 `capture_executed=false`、`confirmation_required=true`，不呼叫網路。確認後每個 URL 仍有 bytes／timeout 上限，失敗會保留 typed error，其他 URL 繼續診斷。
- `license_accepted=false`、`source_acceptance_granted=false`、`downstream_eligibility=none` 固定不變。Owner／Reviewer 必須另外提供具名決議、使用範圍、quality／PIT／coverage、rate limit 與 rollback；本 artifact 不能單獨解除 `legal_and_license_acceptance_required`。

若要把已保存的 audit 交給 Owner／License reviewer，可用下列唯讀 renderer；它只整理既有 13-source machine evidence 與 5 組 owner question，不重新抓資料、不寫 registry，也不會推導 `accepted`／`limited`：

```powershell
.\.venv\Scripts\python.exe scripts\render_p0_owner_decision_packet.py `
  --input $env:TEMP\technical_analysis_p0_audit\p0_evidence_hardening_live.json `
  --output $env:TEMP\technical_analysis_p0_audit\p0_owner_decision_packet.md
```

輸入必須是既有 `p0-source-evidence-audit.v1` artifact；輸出路徑不得位於正式 `DATA_ROOT`。packet 會在每個群組列出 actual／candidate route、fallback 是否嘗試、probe／availability、PIT／timestamp、raw／accepted／blocked 計數與 license URL 線索；這些仍是 machine evidence，不是授權或 acceptance。人工欄位（具名 Owner／reviewer、license／quality／PIT evidence、用途與 rollback）仍須由實際權責人填寫，完成前下游資格固定為 `none`。

### Gate 3 P0 Data Source Control Center（唯讀）

`scripts/inspect_p0_source_control_center.py` 將 13 個 authoritative P0 source contract、候選／官方證據稽核與選擇性人工 decision revision 收斂成同一份可稽核 read model。它不建立 decision registry、不寫正式 SQLite、不執行網路抓取，也不會因 row count 或 machine status 足夠而自動接受來源：

```powershell
# 沒有稽核 artifact 時仍輸出完整 13 列，明示 contract-only 與待補證據
.\.venv\Scripts\python.exe scripts\inspect_p0_source_control_center.py `
  --format markdown `
  --output $env:TEMP\technical_analysis_p0_audit\p0_source_control_center.md

# 讀取既有候選稽核（只讀）
.\.venv\Scripts\python.exe scripts\inspect_p0_source_control_center.py `
  --audit-json $env:TEMP\technical_analysis_p0_audit\p0_audit_results.json `
  --format json
```

- `p0-candidate-audit.v1` 與 `p0-source-evidence-audit.v1` 都會驗證完整 13 項 source denominator 與安全旗標；缺列、重複、未知 source 或 boundary 不符會 fail-closed。
- 每列分開顯示 `governance_status`、`machine_status`、`audit_status`、`decision_status`、row 數、blockers、owner actions 與 evidence requirements；`contract_only` 只表示尚未注入 audit，不是資料可用，`research_shadow` 也不是 formal accepted。
- 2026-08-28 host-context 實測例子：未載入 audit 時會看到 13 列 `contract_only`；載入完整 live audit 後同一組來源成為 `0 contract_only / 12 blocked_provenance / 1 research_shadow`，machine=`1 verified / 12 degraded / 0 missing`；12/13 路徑實際 observed，13 個 payload hash 均存在。這個變化只修正「是否已有機器證據」的顯示；13 筆具名 decision 仍為 `not_supplied`，`accepted=0`、`limited=0`、`downstream_eligibility=none`。
- 總覽固定顯示 `accepted/limited`、`downstream_eligible` 與安全邊界。即使輸入 decision revision 是 `limited`／`accepted`，本控制中心仍強制 `downstream_eligibility=none`、`formal_oos_allowed=false`、`production_scheduler_allowed=false`、`auto_accept_allowed=false`；要變成 accepted feature 必須另有完整、具名 owner/reviewer 與授權／品質／PIT 證據流程。
- 總覽統計不是可任意覆寫的摘要：DTO 建構時會從 13 筆明細重新計算並驗證 governance／machine／decision counts 與各狀態 totals，任何不一致或試圖打開 safety boundary 的輸入都會 fail-closed。
- Workbench → Evidence → Research Console 會自動顯示同一份 P0 Control Center；頁面沒有 Accept／Apply／Promote／Retrain／Trade 控制。若沒有稽核投影，畫面仍保留 13 列並列出 `candidate_audit_not_supplied`、`source_acceptance_decision_missing` 與 `downstream_eligibility_none`。
- 若要讓主 UI 顯示某份既有稽核 artifact，可在啟動前設定 `P0_SOURCE_CONTROL_CENTER_AUDIT=<絕對路徑>`；程式只讀取該明確路徑，不會掃描 `output`、QA 或正式資料目錄。artifact schema 不合法或邊界不符時，整個 Research Console 會 fail-closed 為 degraded。
- 若要讓主 UI 同步顯示具名 owner decision，可設定 `P0_SOURCE_CONTROL_CENTER_DECISIONS=<絕對路徑>`。輸入可以是 canonical `source-acceptance-decision-revision.v1` 的單筆／清單，也可以是外部 `source-acceptance-owner-review-decision.v1`；後者只允許 `deferred`／`rejected`／`disabled` 正規化，`accepted`／`limited` 會 fail-closed，絕不從外部 attestation 或 evidence URL 推導授權。這個入口只接受 13 個 canonical P0 source ID；`fubon.marketdata` 是獨立的 research shadow provider，必須用 Fubon dossier／shadow inspector，不能硬映射進 P0 denominator。UI 只做 read-only projection，不會因載入 decision 而建立 registry 或改變 `downstream_eligibility=none`。
- 若要讓主 UI 同步顯示條款候選證據，可設定 `P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE=<絕對路徑>` 指向 `p0-license-evidence-capture.v1`。Data Update 與 Research Console 會在每列 license 欄顯示 `captured_candidate`、`capture_partial`、`preview_not_captured` 或 `capture_transport_error` 等狀態，並保留 URL／hash／限制提示數；`capture_partial` 表示同一來源的多個官方條款 URL 只有部分取得，仍須逐一複核，絕不代表授權通過。artifact schema、allowlist 或安全旗標不符時整體 fail-closed。這只改善「條款是否已觀測」的可見性，`license_status=requires_review`、`license_accepted=false` 與 `downstream_eligibility=none` 不會改變。
- Data Update → 全部資料也會在執行「檢查數據狀態」時載入上述兩個明確路徑，顯示 13 列 `P0 官方來源證據` 表格。欄位包含實際 route、可用 route 清單、fallback 來源／原因、PIT／公告與 availability、**解析通過率（accepted／observed）與 accepted／observed／blocked rows**、license、owner decision 與下游資格；這個比例只表示已觀測 payload 的 parser row-conservation，不代表官方市場 universe 或日期完整覆蓋率，沒有獨立分母時不可解讀成「來源 100% 完整」。表格是 candidate／shadow 的治理觀測，不是更新按鈕，也不會寫入 SQLite。未設定 artifact 會顯示 `contract_only`，路徑遺失或 schema／boundary 錯誤會顯示 `audit_unavailable` 與讀取原因，避免沿用上一輪或假綠。
- P0 audit 的 route registry 只是候選取得目錄；`acquisition_route_probe_summary` 會另外顯示每條 route 是否真的 `observed`、`failed`、官方無資料、日期不符、解析／接受列缺漏或 `not_attempted`，並保留 selected／fallback lineage。未嘗試的 alternate route 不會被誤標成可用來源；此資訊只供候選 evidence 與 Owner review，不改 source acceptance、PIT 或 production ingestion。
- Data Update → 排程狀態頁的初始預覽會讀取明確的 `data_freshness/latest_status.json` 路徑，並以中文狀態、原始 token、檢查時間、日價／技術指標最新日與 warnings／errors 摘要呈現；它只代表這一個 freshness 工作，不是整體 Scheduler。按「檢查此資料源狀態」後才會讀取明確 `scheduled/*/latest_status.json` 並彙整核心／受控／需處理／不可用工作。每日資料更新 task 的註冊／執行不等於 Evidence／ML 生產寫入授權；`production_scheduler_allowed=false` 固定保留，頁面不提供手動觸發或 Task Scheduler 修改。
- 更新時間軸的步驟／歷史表格與 freshness／TPEX 摘要會同時顯示中文狀態與原始 machine token（例如 `完成（passed）`）；原始 token 仍保留供排錯，不代表任何正式治理或交易授權。
- 更新時間軸的 freshness 摘要會另外顯示 artifact 內的日價／技術指標最新日、對應 quick-run 的檢查／預期日，以及 TWSE／TPEx 最新日檔是否存在；這些欄位只來自明確 freshness artifact 的 allowlist，未提供或格式不符時顯示未知／缺漏，不會由狀態 token 推導。
- 當 freshness artifact 已提供上述觀測時，時間軸會把 `data_update_quick_expected_date`、日價最新日與技術指標最新日和 quick-run 目標資料日比對；`data_update_quick_checked_date` 是檢查發生日期，只會檢查是否早於 expected date，不要求和資料 end date 相等。因此週末在 8/30 檢查 8/28 的最後交易日不會被誤標 `degraded`；真正日期不一致、quick status 不是成功狀態或原始日檔缺漏，整體狀態才會顯示 `freshness 異常（degraded）` 並列出診斷。舊版 artifact 沒有 optional checks 時不會被自動回填或推導。
- 時間軸也會翻譯 `in_progress`、`schema_mismatch`、`blocked_provenance` 等排程／治理 token；未知 token 仍原文顯示，避免把未辨識狀態誤當成功。
- Portfolio → Paper Portfolio 的 readiness／weekly 摘要也會以中文說明包住原始狀態（例如 `成本帳：尚不可計算（成本帳缺漏）（not_computable_cost_ledger_missing）`）；這只是可讀性改善，缺少真實 fills 時仍不會計算成本後週報。

### P0 Source Intake Validator（唯讀候選輸入）

`scripts/inspect_p0_intake_readiness.py` 是把外部 P0 治理資料交給程式檢查的第一個接入口。它只接受明確的 `p0-source-intake.v1` JSON，要求完整 13 個 `source-acceptance-dossier.v1`，逐列驗證欄位型別、source denominator、license／PIT／quality checklist 與安全旗標；不會建立 decision registry、不會寫正式資料，也不會自動接受來源。

若已經有 `p0-source-evidence-audit.v1`，不必人工抄寫每個 machine row。可用下列唯讀轉接器建立一份 candidate intake；每列 dossier 只帶入 audit 的 raw／accepted／quarantine／blocked 計數、payload hash 與 machine status，另外在 intake envelope 的 `machine_evidence_by_source` 保留 allowlist 內的實際 route、fallback lineage、schema／probe outcome、timestamp semantics 與 acquisition route 清單。若 audit 內的 MOPS verified-artifact 分支已通過 validator，這些 row counts 會如實保留到 dossier，不會把有效 artifact 變成 `0/0`；所有 source owner、license、publication、available-date、PIT、revision 與 reviewer 欄位仍標成 `unverified`／`requires_review`，所以結果一定維持 `deferred`：

```powershell
.\.venv\Scripts\python.exe scripts\build_p0_intake_from_audit.py `
  --audit $env:TEMP\technical_analysis_p0_audit\p0_evidence_20260828_live_tpex_fallback_v2.json `
  --output $env:TEMP\technical_analysis_p0_audit\p0_candidate_intake_from_audit_20260828.json

.\.venv\Scripts\python.exe scripts\inspect_p0_intake_readiness.py `
  --input $env:TEMP\technical_analysis_p0_audit\p0_candidate_intake_from_audit_20260828.json `
  --format markdown `
  --output $env:TEMP\technical_analysis_p0_audit\p0_candidate_intake_readiness_20260828.md
```

`build_p0_intake_from_audit.py --help` 與阻擋診斷會先將 stdout／stderr 設為 UTF-8；在 Windows CP1252 主控台也應維持可讀並以 exit code 表示成功或阻擋。這只改善 CLI 可觀測性，不改候選資料或任何 acceptance gate。

此轉接器的輸出只允許位於 OS TEMP，且明確保留 `auto_accept_allowed=false`、
`downstream_eligibility=none`；它可以縮短 owner review 的資料整理工作，但不能
替代官方 publication／PIT／license 證據或具名決議。`machine_evidence_by_source`
只是一份安全投影，不屬於 `source-acceptance-dossier.v1` 的治理欄位，也不會被
intake validator 解讀成 acceptance authority。

```powershell
# 先產生 13 列候選範本；路徑必須明確且位於 DATA_ROOT 之外
.\.venv\Scripts\python.exe scripts\inspect_p0_intake_readiness.py `
  --template-output $env:TEMP\technical_analysis_p0_audit\p0_source_intake_template.json

# 填入 owner／license／PIT／quality 證據後，產生 JSON 或 Markdown 診斷
.\.venv\Scripts\python.exe scripts\inspect_p0_intake_readiness.py `
  --input $env:TEMP\technical_analysis_p0_audit\p0_source_intake.json `
  --format markdown `
  --output $env:TEMP\technical_analysis_p0_audit\p0_source_intake_report.md
```

- `status=deferred`：13 列格式正確，但仍有 checklist 或 authority blocker；可繼續補件。
- `status=ready_for_owner_review`：13 列 checklist 均完成，只代表可以交給具名 owner／reviewer 審查，`decision_preview` 仍固定為 `deferred`、`allowed_use_cases=[]`、`downstream_eligibility=none`。
- `status=invalid_input`：缺列、重複、未知 source、欄位型別／schema／secret-like 欄位或不安全旗標；CLI 以 exit code `2` fail-closed。格式有效但 deferred 時 exit code 為 `0`，因為「稽核完成」不等於「Gate 通過」。
- 範本與報告的寫入都是明確指定的候選 artifact；程式拒絕寫入 `DATA_ROOT`，不會掃描或覆寫既有正式 output。完成 intake validator 後，仍須透過既有的 source acceptance review／append-only decision 流程，不能直接把報告餵給 `ScoringEngine`、Advice、scheduler 或 broker。

### P0 Source Acceptance Decision CLI（預覽／明確確認）

`scripts/append_source_acceptance_decision.py` 將 intake 後的 owner／reviewer 決議接到既有 `SourceAcceptanceDecisionRegistry`。預設永遠是 preview，不開啟 registry；只有操作者同時提供 `--registry` 與 `--confirm-append` 才會建立／append SQLite。`accepted`／`limited` 必須提供 intake artifact，且三類 evidence id 必須能回溯到該 dossier；`deferred`／`rejected`／`disabled` 仍可先保存為非套用決議。

```powershell
# 預覽；不會建立 registry.sqlite
.\.venv\Scripts\python.exe scripts\append_source_acceptance_decision.py `
  --decision $env:TEMP\technical_analysis_p0_audit\decision.json `
  --intake $env:TEMP\technical_analysis_p0_audit\p0_source_intake.json `
  --format markdown

# 明確確認後才 append；registry 必須位於 DATA_ROOT 之外
.\.venv\Scripts\python.exe scripts\append_source_acceptance_decision.py `
  --decision $env:TEMP\technical_analysis_p0_audit\decision.json `
  --intake $env:TEMP\technical_analysis_p0_audit\p0_source_intake.json `
  --registry $env:TEMP\technical_analysis_p0_audit\source_acceptance.sqlite `
  --confirm-append `
  --format json
```

- append 是 append-only 且具 idempotency；相同 revision 第二次執行會顯示 `already_present`，不覆寫歷史列。registry 寫入成功不代表 downstream eligibility、formal OOS、scheduler 或 broker 開啟；控制中心仍固定揭露 `downstream_eligibility=none`。
- `accepted`／`limited` 若缺 intake、dossier 尚未 `ready_for_owner_review`、evidence id 未綁定、decision schema 不符或 registry 位於 `DATA_ROOT`，CLI 會以 exit code `2` fail-closed；preview／append 報告都會保留 decision content hash 與 dossier hash 供稽核。
- 外部 owner-review decision 若仍是 `deferred`／`rejected`／`disabled`，CLI 也可直接 preview（或在明確 `--confirm-append` 下保存為非套用 revision）；它的 `active_blockers` 只會成為 registry blockers，不會被當成 license／quality／PIT evidence。外部 owner-review 的 `accepted`／`limited` 必須改用 canonical revision 並重新通過 intake／evidence binding。

### P0 機器證據決議入口（2026-09-07）

同一 CLI 新增 `--machine-evidence <封套JSON>`，與 `--decision`、`--intake` 的人工決議模式分開。這條路徑不要求填寫人類 reviewer；它讀取封套所引用的實體證據，重新計算 bytes SHA-256，核對 producer 程式版本、來源、品質、獨立覆蓋分母與決策時間。證據路徑可相對於封套所在目錄。

操作順序：先取得符合 `source-acceptance-machine-evidence.v1` 的完整封套與子證據，再執行 `scripts/append_source_acceptance_decision.py --machine-evidence <封套JSON> --format json` 預覽。需要保存受限決議時，另加 `--registry <DATA_ROOT外的候選SQLite> --confirm-append`；這是明確寫入旗標，不代表必須重新取得具名人工審核。

成功會產生 `machine:evidence_policy` 的 `limited` 決議，用途限定 `research_shadow`／`diagnostics`；相同 revision 重跑顯示 `already_present`。失敗依 `machine_evidence_*` 原因修復缺件、內容不一致、覆蓋不足或未來時間，不以填入人名解除。正式 OOS、排程與交易權限不由此入口授予。

目前交付的是驗證器、CLI 與候選 registry 接線；既有官方 capture／audit producer 尚未產出新契約要求的全部欄位，完整真實封套生產仍在接續中。不要手填 verified 或 producer hash 來冒充已完成官方證據驗證。驗收與限制見 [V4 機器證據紀錄](../06_qa/V4_AUTOMATED_REVIEW_2026_09_07.md)。

## Phase 3C governed ingestion candidate CLI

Phase 3C (三大法人、信用交易、TDCC 集保庫存) 的資料抓取為 **manual-only candidate ingestion**，它不屬於 V3.0 engineering closeout gate，不掛載於「一鍵安全更新」，也不由正式排程執行。

在資料更新頁的「三大法人」、「信用交易」與「集保股權」子分頁，按「更新至最新候選」或「抓取最新週候選」即可啟動同一套受控 runner。三大法人／信用交易預設從候選 DB 最新成功日期的下一個日期起，向前抓到不晚於台灣市場今日的官方交易日；沒有 checkpoint 時只採近 30 日 bounded window。TDCC 只抓官方 payload 自帶的最新單週資料，不輪詢歷史日期。每次都會先跳出確認視窗，明示 `PHASE3C_CANDIDATE_DB_PATH`，且只寫入隔離 Candidate DB；不會寫正式 `twstock.db`、不會更新 Scoring／Recommendation／Advice／Portfolio，也不會開啟 scheduler。完成後按「檢查此資料源狀態」可看到候選最新日、筆數、checkpoint 覆蓋率與相對正式日價基準日的新鮮度提示。

執行腳本 `scripts/update_phase3c_candidates.py` 預設為 `--dry-run` 模式，不會建立 Candidate DB 或 table；它只進行來源與交易日 diagnostics，並在隔離暫定位置輸出摘要 sidecar。apply 必須同時提供確認 token 與明確的、位於 `DATA_ROOT` 外的 Candidate DB 路徑。

```powershell
# Dry-run；不寫入 Candidate DB。預設不對本地缺少證據的日期進行線上交易日 probe。
.\.venv\Scripts\python.exe scripts\update_phase3c_candidates.py --start-date 2026-07-06 --end-date 2026-07-08

# 實際寫入隔離 Candidate DB（不可放在 DATA_ROOT 下），並讓 UI 能唯讀顯示狀態。
$env:PHASE3C_CANDIDATE_DB_PATH = 'D:/Min/Python/Project/FA_Data_candidate/phase3c_candidate.db'
.\.venv\Scripts\python.exe scripts\update_phase3c_candidates.py --start-date 2026-07-06 --end-date 2026-07-08 --sources institutional,credit --db-path $env:PHASE3C_CANDIDATE_DB_PATH --confirm apply-phase3c-candidate-ingestion

# 同時寫入 TDCC 官方最新一週 snapshot；資料日採 payload，不做歷史逐日假回補。
.\.venv\Scripts\python.exe scripts\update_phase3c_candidates.py --date 2026-08-13 --sources tdcc --include-latest-tdcc --db-path $env:PHASE3C_CANDIDATE_DB_PATH --confirm apply-phase3c-candidate-ingestion
```

輸出會明確包含以下邊界：
- `access_boundary: writes_allowed=false` (若是 dry-run)
- `access_boundary: production_scheduler_allowed=false`
- `access_boundary: scoring_engine_write_allowed=false`
- `access_boundary: investment_effectiveness_claim=false`
- `access_boundary: v3_closeout_gate_credit=false`

### Direct v4 自動等待合規 PIT sidecar

`scripts\\maintain_ml_direct_v3_refresh_chain.py --watch-formal-inputs` 會在 chain 完成後持續
驗證 `ml_pit_year_shards/latest_manifest.json` 指向的 `all_field_enriched` raw PIT dataset：
pointer、publication／dataset canonical hash、formal safety、`decision_at` 與目前 Direct
identity 必須一致；較新的 publication 或同一 cutoff 但內容 hash 改變時，會自動以新的
`training_as_of` 建立 immutable Direct → OOC chain。它也會驗證最新 official market-event
publication，並在 refresh 時保留已綁定且仍符合 cutoff 的 sector sidecar。官方 wrapper 只有
metadata 變更、canonical events hash 未變時，不會造成重複重訓。causal non-cash ledger 與
Rule Champion controlled artifact 沒有正式受控來源時不會被自動創造或替代，formal gate、
alpha=0、broker disabled 維持不變。

Direct v4 完成後，若新的 PIT sector sidecar 被放入 direct output lineage，
`continue_ml_direct_ooc_after_store.py` 會以正式 assembler 驗證 canonical manifest、
`status=accepted`、source／license／source hash、可得時間與 training cutoff；全部通過
才會建立新的 immutable Direct run，否則沿用現有 publication 並維持 formal gate 關閉。
可用 `BALDR_ML_PIT_SECTOR_MEMBERSHIP_PATH` 指向受控來源；未設定時只掃描明確的
`pit_sector_membership`／`sector_membership`／`sidecars` 目錄與固定檔名，不會把
`companies.csv` 或研究輸出當成 PIT 歷史資料。搭配
`scripts\maintain_ml_direct_v3_refresh_chain.py --watch-formal-inputs` 時，維護程序
會在 chain 完成後持續等待合規來源出現並自動續跑；沒有來源時不會重複訓練，且不會
改寫舊 run、寫正式 SQLite 或放寬 formal gate。

同一個 watcher 也會讀取受控環境變數 `BALDR_ML_FORMAL_PORTFOLIO_LEDGER_PATH` 與
`BALDR_ML_FORMAL_RULE_CHAMPION_HISTORY_PATH`。它不會從 research／output 目錄猜測
ledger 或 history；若三項正式輸入尚未同時通過驗證，formal-only refresh 會繼續等待，
避免只因 owner 分批放入來源而重跑部分 Direct/OOC chain。已綁定的 immutable path
則會由 Direct identity 以 file hash carry-forward，來源遺失或 tamper 時 fail closed。
長駐 watcher 也會在 polling 時重新讀取 Windows 使用者／系統環境登錄值，讓啟動後的
owner deposit 能被同一個 process 接收；只更新 process memory，HMAC value 不會進入檔案、
命令列、status 或 log。若 watcher 採用的登錄值被移除，process 內的 adopted value 會
清掉，formal 驗證仍會 blocked。

單獨執行 `scripts\inspect_ml_formal_input_readiness.py` 時也會使用相同的受控 Windows registry handoff；它只把 late owner deposit 接到當前唯讀 process memory，不會寫回 registry、artifact 或 source DB。

`run_ml_direct_chain_maintenance.cmd` 在啟動 Direct/OOC 前另做唯讀三段 filesystem capacity
preflight。Direct chain scheduled 預設以 35 GiB 持久新增、40 GiB 暫存峰值與至少 200 GiB
安全保留計算 required headroom（合計至少 275 GiB）；可用
`--persistent-storage-budget-bytes`、`--temporary-storage-budget-bytes` 與
`--safety-reserve-bytes` 明確指定更大的值。低於 200 GiB 的值會 fail closed。任一項不足時會寫入
`status=blocked_insufficient_storage`、`storage_preflight.capacity_budget` 與 blockers，直接
結束本次 wrapper，不啟動重建、不進入維護器 retry loop，也不刪除既有 run。這只是容量保護，
不是 Formal／promotion 通過；舊的 `--minimum-free-space-bytes` 仍可作相容參數名稱，
但其值也必須至少為 200 GiB。先以 `--preflight-only` 驗證，只有通過後才可考慮
啟動長時間 child。所有 scheduled raw／Direct／OOC caller 使用
`release_v4/.ml_heavy_chain.lock`；指定其他 lock path 會被拒絕，child 只沿用上層
已持有的同一 reservation。

若 preflight 已回報 `blocked_insufficient_storage`，可先用下列唯讀工具整理容量與人工
retention 候選：

```powershell
.\.venv\Scripts\python.exe scripts\inspect_ml_storage_retention.py `
  --root <DIRECT_RAW_ROOT> `
  --root <DIRECT_NUMERIC_ROOT> `
  --root <OOC_TRAINING_ROOT> `
  --minimum-free-space-bytes 21474836480 `
  --max-files 500000 `
  --format markdown `
  --output $env:TEMP\technical_analysis_program_readiness\ml_storage_retention_inventory.md
```

此 CLI 在解析參數前會設定容錯 UTF-8 stdout/stderr；Windows CP1252 主控台執行 `--help` 或
輸出繁中容量診斷時不會因 `UnicodeEncodeError` 中止。這只改善可觀測性，不會改變容量門檻、
retention 候選或任何刪除／搬移權限。

工具只讀取檔案 metadata 與小型 `manifest.json`，會列出大小、manifest status、掃描是否
截斷及可逆的外部 archive／人工 review 建議；不刪除、不搬移、不修改 lock／pointer，且
輸出明確固定 `automatic_delete_allowed=false`。若 `scan_truncated=true`，候選清單只能作
初步盤點，需提高 `--max-files` 重跑後再交 owner 決定；不要因清單出現 `status=complete`
就直接刪除 immutable run。

### 人工 retention 決策與清理後驗證

Immutable PIT／Direct／OOC 清理不是一般「刪暫存檔」。若 owner 明確要求清理，依下列
順序操作：

1. 以足夠 `--max-files` 重跑 inventory，確認三個 root 均 `scan_truncated=false`、errors 空白。
2. 解析三個 `latest_manifest.json`，保存 pointer file hash，確認 pointer 指向的 run 存在。
3. 從 OOC `store_manifest_path` 回查 Direct，再以 Direct source training manifest hash 回查
   PIT；至少保留 current pointer 與完整 OOC → Direct → PIT dependency closure。
4. 搜尋 repository／runbook／release／QA 對候選 run ID 的引用。完整 run 若仍被引用，
   優先冷 archive；若 owner 仍決定刪除，先建立 durable tombstone，不改寫歷史 ID／hash。
5. 查 maintenance lock 與 active process custody；未知 owner 不得當 stale lock 強刪。
6. 將「未完成 resume」與「完整歷史 run」分開核准。刪 resume 代表放棄 checkpoint、日後
   必須重算；完整 run 刪除則失去該 cutoff 的本機 bytes，兩者都不是免費可逆。
7. 只使用已解析的 exact literal path；禁止以 `release_v4` root、wildcard、modified time
   或「最舊」單一條件遞迴刪除。
8. 刪除後重跑完整 inventory、run count、pointer hash、dependency closure 與 repo reference
   檢查，將 before／after bytes、全部 IDs、授權、不可逆性與 recovery 寫入 `docs/06_qa/`。

2026-08-29 的 retained baseline 是 PIT／Direct／OOC 各 6 個完整 run；post-cleanup（歷史）
inventory 於 `2026-08-28T23:48:53-07:00` 觀察到 D free=`440,561,684,480` bytes
（約 410.31 GiB）、inventory=`headroom_ok`。完整 custody 見
[ML Release v4 Storage Retention Cleanup](../06_qa/ML_RELEASE_V4_STORAGE_RETENTION_CLEANUP_2026_08_29.md)。
其中一個已刪 incomplete Direct ID 仍保留在兩份歷史 runbook，已用 tombstone 揭露；
current pointers 與 retained chain 未受影響。

8/30 fresh read-only inventory 另觀察到 PIT／Direct／OOC current runs=`8/9/9`、D free 約
`338.9 GiB`；這些是清理後自然產生的後續 outputs，不改寫 8/29 的 retained custody，也不
自動刪除或搬移。若只需確認容量，使用 `--preflight-only`。

`automatic_delete_allowed=false` 仍適用：本次清理是使用者看過範圍後另行明確授權的
人工操作，不是 inspector 或 scheduler 自動取得刪除權。Headroom 恢復也不代表應立即
執行 maintenance wrapper；wrapper 在 preflight 通過後可能真的開始 rebuild。

## 日常正式 Rule／ledger／PIT bounded input producer（2026-09-07）

以 `scripts\run_formal_input_producer_daily.py` 執行一輪日常來源 handoff。必填
`--output-root`、`--development-output-root`、`--market-db`、`--clock-manifest`、
`--universe-symbols`、`--owner-acceptance`；候選輸出目錄與 Rule development 目錄都
必須是新的 OS TEMP 空目錄。可選的 `--paper-snapshot-db` 與
`--paper-trade-ledger-db` 只讀取既有 Paper source，不能由 snapshot 反推成交。

CLI 使用當下自然時間，不接受 `--now`。入口先驗證台北交易日、clock／owner／universe、
market SQLite 與 Paper schema，再呼叫既有 Rule/PIT producer 與 formal consumers。Rule
在 activation 日之後可以沿用同一份 clock；PIT 僅產生官方 TWSE／TPEx 當日 first-seen
candidate。source response completion、Paper snapshot/fill content hash、Decimal
quantity／cash reconciliation 與 consumer readback 都必須通過；缺 fill、官方日曆或
任何 custody 證據會以具體 blocker 停止。

日常排程入口為 `scripts\scheduled\run_formal_input_producer_daily.cmd`，預設使用
新的 TEMP candidate／development 子目錄，並將 Rule history 與 causal Paper ledger
的 immutable manifest、source custody、publication context、receipt 保存到
`<repo>\output\formal_daily_publications`。可用 `FORMAL_DAILY_PUBLICATION_ROOT`
指定合法 repo `output` 或隔離 TEMP 的持久 parent；`FORMAL_DAILY_OUTPUT_ROOT` 與
`FORMAL_DAILY_DEVELOPMENT_OUTPUT_ROOT` 若有設定也視為 parent，每輪自動建立唯一
空目錄，不能用固定非空目錄跨日重跑。排程狀態以原子方式更新到
`<publication_root>\scheduler\latest_status.json`。

PIT 現況 capture 在官方兩市場 response 與 machine consumer readback 通過後，還會將
publication、receipt、operational envelope 與兩份官方 raw bytes 以 create-only 方式
保存到 `<publication_root>\pit_candidate_archive\<Taipei capture date>\<short key>\`。
其中 `archive_manifest.json` 綁定完整 file hash、source custody、capture time 與
producer code hash；移除原 TEMP candidate 後仍可直接從 archive raw bytes 重驗 rows。
這個 durable archive 仍標示 candidate-only，不能當成歷史 PIT、正式 sector source 或
Formal 3/3 credit。

排程只需在 Windows 使用者環境設定一次
`FORMAL_DAILY_CLOCK_MANIFEST`、`FORMAL_DAILY_UNIVERSE_SYMBOLS`、
`FORMAL_DAILY_OWNER_ACCEPTANCE`。market DB 預設為
`DATA_ROOT\sqlite\twstock.db`；
Paper state 固定為 repository 隔離的
`<repo>\output\paper_execution_eod_replay\paper_portfolio\paper_portfolio.sqlite`
（盤前 runner append、EOD／Formal 唯讀）與 repository 隔離的
`<repo>\output\paper_execution_eod_replay\paper_trade_ledger.sqlite`（EOD writer
append、Formal 唯讀）。production cmd 固定傳遞這兩個 repository path，不以 D 槽
snapshot 作 Formal source。Rule
source 缺件時仍會讓 PIT capture lane 依官方 response completion time 繼續執行，
但不會把 PIT current candidate 轉成歷史 Formal input。

`status=candidate_only` 代表 TEMP candidate 已經由 machine consumer 驗證，仍不計入
正式三項 input；`status=formal_inputs_machine_verified` 只在呼叫端明確提供的三個
formal paths 都經正式 consumer readback 後出現。此入口不寫 D 或正式 controlled
paths、不下單、不啟動訓練或 promotion。排程對 `candidate_only`／`blocked` 回傳
exit code 2，只有三個明確 formal paths 的正式 consumer readback 全部通過才回傳 0；
其中任何一項缺件、來源刪除、hash／cutoff／custody 失敗，都會在 status 與各 input
receipt 保留機器 blocker，下一輪可依 durable publication retry，不需改寫歷史時間。

### ML daily price source quality 稽核

建立 PIT 或其他 ML label 前，可用下列唯讀命令比對 SQLite `daily_prices` 與
canonical `daily_price` 日期 CSV：

```powershell
.\.venv\Scripts\python.exe scripts\audit_ml_daily_price_source_quality.py `
  --sqlite D:\Min\Python\Project\FA_Data\sqlite\twstock.db `
  --daily-price-dir D:\Min\Python\Project\FA_Data\daily_price `
  --daily-price-dir D:\Min\Python\Project\FA_Data\daily_price_tpex `
  --start-date 2026-05-01 --end-date 2026-06-30 `
  --output output\v4_ml_daily_price_source_quality_20260907\source_quality.json
```

命令只讀來源；輸出 `candidate_count=0` 才表示該範圍通過 source guard。若找到兩側
價格尺度斷裂，會寫入帶 file hash、symbol、日期、Decimal 價格、unit/scale 與
canonical row 的 quarantine report，並以 exit code 2 停止後續 PIT ingest。報告不會
修正 SQLite、補值、截斷既有 label 或推論 corporate action；輸出路徑必須位於來源
目錄之外。兩個 market root 會按 symbol 建立唯一 route；同一 symbol 的 valid／invalid
跨市場重複或衝突會 fail closed，不以目錄順序猜來源。若 SQLite 與 canonical raw row
的四個 OHLC 都是明確 missing（例如 NULL、空值、`-`、`N/A` 或 Unicode dash），且逐欄
missing 語義與 volume 都一致，才會產生 research-only `price_unavailable` contract；
正成交量不代表價格可交易，也不會 zero-fill、橋接相鄰日期或推論停牌原因。partial
OHLC、missing 與真實數值混用、負值／非數值、volume 不一致、canonical invalid
多來源或尺度異常均維持 quarantine。

排程 `scripts/scheduled/run_ml_raw_pit_refresh.py` 會把 builder 的 source-quality evidence
寫到每次執行獨立的 `output_root/scheduled/ml_raw_pit_refresh/source_quality/`：一份
`<run-id>.json` report 與一份同名 `<run-id>.candidates.jsonl` full-candidate sidecar。
正式預設 `output_root` 為 `D:\Min\Python\Project\FA_Data\output`，因此 status 在
`D:\Min\Python\Project\FA_Data\output\scheduled\ml_raw_pit_refresh\latest_status.json`，
report／sidecar 在其 `source_quality\` 子目錄；若傳入 `--output-root`，以該參數的絕對路徑為準。
report 的 `candidate_sample_limit` 預設為 64，只限制摘要中的 `candidates`；sidecar
逐列保存完整候選，並以 manifest 綁定全量 `row_count`、`candidate_digest`、`key_digest`、
`unique_key_count`、檔案 SHA、日期／代號排序與 `complete`。排程 wrapper 會重新讀取每一行
並核對 report hash、sidecar hash、全量 count／digest／唯一 key；因此
`candidate_samples_truncated=true` 不代表完整 evidence 缺失，必須同時看
`candidate_rows_complete=true`、`candidate_evidence_status=verified` 與
`candidate_full_unique_key_count_verified=true`。report／sidecar 缺件、截斷、篡改、duplicate
或亂序 key、summary mismatch、寫入失敗及 retry path collision 都保持 failed／blocked，
不發布新 raw PIT；retry 會使用新的 run id，不覆寫前一次 evidence。這些欄位只證明本次
read-only builder evidence 可還原，不把 report 提升為 source authority、歷史 PIT
decision-time custody、formal training、formal OOS 或 promotion credit。

source-quality 的 predecessor context 由 SQLite 中嚴格早於／晚於當筆的實際 observation
date 路由；PIT `ingest_guard` 只讀實際前一筆，retrospective audit 才讀後一筆。週末／
假日沒有 calendar-day 檔案時，不可用固定 weekday 猜測 predecessor。PIT exporter 也可
透過 `PITYearShardBuildRequest.daily_price_source_dir` 在建立 output/staging 前套用同一 guard。

若要把 current invalid rows 作為研究缺值證據，必須先完成 candidate-level canonical mapping，
再只對 SQLite 與 canonical 四個 OHLC 欄位逐欄明確 unavailable 且等價的 row 建立
`ml-daily-price-availability.v1`。contract 會保留 raw row、missing mask、volume、source identity，
固定 `research_only=true`、不納入 price feature／label row、不 zero-fill、不 bridge；混合有效、
不等價、canonical missing、volume mismatch、scale 或 route 不明的 row 維持 quarantine。全量
candidate report 不能因其中一部分可視為 unavailable 而通過 raw-shard exception；只有明確排除
不等價 rows 的 scoped research-only report 才能通過該 exception。這個研究路徑不授予 formal
training、formal OOS 或 promotion credit，且不會修改 SQLite、既有 PIT 或歷史 publication。

Teacher allocation fit 另要求三個正式來源的
`allocation-teacher-input-provenance.v1` readback：PIT sector membership、causal
non-cash portfolio ledger、formal Rule champion history。僅有 aggregate counters、
非零 eligible 數或部分決策日覆蓋都會維持 blocked；每個 source 的 receipt file hash、
source identity/schema、read-only、available-before-decision、逐日候選集合與 target
summary row count 必須一致。此驗證不讀未來 label，且不代表 formal OOS、promotion 或
production alpha。

### Workbench／Scheduled Evidence 的機器狀態、stale 與 Retry

進入「決策工作台」或「證據覆盤 > 排程狀態」後，先讀取畫面上的機器分類與
`load_state`，再決定下一步。畫面只讀取既有 DTO、`latest_status.json` 與 report，
不執行策略、不寫 DB、不補 Formal 輸入，也不建立交易。

機器分類的判讀如下：

* `source_missing`：來源或覆蓋分母缺件；依畫面列出的 source trace／diagnostic
  修復來源。它不會因缺少 owner 名稱而變成具名人工審核。
* `waiting_for_time`：尚未到達自然可得時間；等待下一個官方時間點，不用 replay、
  fixture 或手動改日期補齊。
* `invalid_evidence`：hash、schema、cutoff、內容或 custody 驗證失敗；先修證據，
  不以人工簽名覆蓋。
* `machine_candidate`／`machine_verified`：分別表示候選或已通過機器 consumer，
  仍須依畫面所示 Formal／promotion scope 判讀；候選不等於正式信用。
* `human_review`：只有來源明確要求人工判讀時才會出現，並保留下鑽目標與原因。
  `action_required`、缺來源或等待時間本身不代表人工要求。

`Scheduled Evidence` 的 `load_state=current` 會在既有三份核心 payload 成功讀取且通過
基本完整性檢查時成立。初次沒有可信 payload 會顯示 `unknown`；若已成功讀取後
本輪檔案遺失、損壞或 loader 例外，畫面保留最後可信內容，但每張狀態卡、摘要與
詳細資料都標示 `stale`、最後成功載入時間及錯誤原因。修復檔案後按「重新整理排程
證據狀態」；按鈕會取得焦點，並由 loader 重新驗證，不能把 stale 卡片當成 current。
新增的 forward outcome receipt 若尚未出現，核心三份 payload 仍可正常顯示，forward
卡片會單獨標示 `source_missing`；receipt 一旦存在，則同時顯示掃描／寫入／待成熟數與
`forward_outcome_writes_evidence_db`，不把 outcome 寫入誤當成 UI 寫入。

Workbench 來源例外時同樣保留最後可信 DTO，頂端 banner、摘要色彩、狀態文字與
warning 會標示 stale，並把焦點放在「重新整理工作台狀態」。初次讀取失敗顯示
`unknown`，不會把空的人工佇列解讀成「所有風險已確認」。機器-only 的來源缺件、
自然等待或降級項目會顯示「機器狀態待處理」，不會進入人工覆盤排序；若需要人工，
只處理明確分類為 `human_review` 的列。

排錯時先確認 `load_state`、`last_good_loaded_at`、每卡分類、source trace、
diagnostic 與 Retry 後的新讀取時間，再檢查來源檔案的內容 hash／schema／cutoff。
若仍是 `unknown`，表示尚無可保留的 last-known-good；若是 `stale`，表示舊內容只
供排錯與導覽。這些 UI 狀態不會改變 Formal readiness；Rule、causal ledger、PIT
三項仍須各自通過正式 consumer readback 才可取得信用。

### Portfolio 背景刷新與一致性

主視窗的「持倉與覆盤管理」使用背景 `TaskWorker` 讀取 `PortfolioDTO`。摘要卡、
持倉表、壓力投影與監控摘要會以同一份 DTO 更新，避免讀取期間分別取得不同版本；
畫面更新完成前會保留目前內容，按鈕會顯示背景 generation。這個刷新只讀取既有
Portfolio／Paper 狀態，不會寫入交易、D 原始資料、行情資料庫或 broker。

連續按下「重新整理持倉資料」時，系統會合作式取消較早 generation，完成後只套用
最新 generation；舊 worker 的回呼會被丟棄，不會覆蓋較新的摘要或表格。關閉頁面或
主視窗時同樣採合作式取消；若 worker 尚在執行，主視窗會先拒絕關閉，工作安全結束後
須再次關閉才能完成關閉，不使用強制終止。

若背景讀取失敗且已有成功 DTO，畫面保留最近一次內容並在刷新狀態列顯示原因；這些
內容只供排錯，不代表目前資料已更新。若首次讀取失敗，顯示「狀態未知」且不把空的
持倉或人工佇列解讀為沒有風險。再次按 Retry／「重新整理持倉資料」會重新讀取來源，
錯誤訊息為空時也會保留可讀的診斷文字。

### 當日 Rule source 的機器重驗與排程

既有 PIT 盤前 wrapper 會先呼叫 `scripts\scheduled\run_formal_rule_source_preopen.cmd`，
再執行 PIT capture。Rule source producer 只在台北 08:30 前用目前系統時間建立當日
repository candidate；它從 D 槽 market DB 以 SQLite `mode=ro`／`query_only` 讀取完整
T-1 window，沿用已接受的 policy，並以官方 TWSE holidaySchedule cache 確認交易日。
不提供 `--now`、日期或 fixture 參數，也不覆寫 D、歷史 clock 或既有 owner policy。

預設路徑如下：

- Rule publication：`output\formal_daily_publications\rule_source\`
- machine receipt：每個 `clock-YYYYMMDD-machine-v2-*` bundle 的
  `metadata\machine_revalidation_receipt.json`
- producer status：`output\formal_daily_publications\rule_source\scheduler\rule_source_latest_status.json`
- D market source：`D:\Min\Python\Project\FA_Data\sqlite\twstock.db`
- D baseline policy：`D:\Min\Python\Project\FA_Data\output\formal_prospective\`
- official calendar cache：`output\paper_execution_eod_replay\calendar_cache\`

受控排程或手動唯讀 probe 若需覆寫路徑，只能使用
`FORMAL_DAILY_RULE_SOURCE_ROOT`、`FORMAL_DAILY_MARKET_DB`、
`FORMAL_DAILY_RULE_BASELINE_ROOT` 與 `FORMAL_DAILY_CALENDAR_CACHE_ROOT`。publication
root 必須仍在 repository 的 `output` 下；market DB 與 baseline 是唯讀來源。可執行：

```powershell
cmd /d /c scripts\scheduled\run_formal_rule_source_preopen.cmd
```

`status=rule_source_bundle_created` 或 `rule_source_bundle_reused` 表示當日 machine
candidate 已寫入或重用 immutable bundle；consumer 仍會重讀同一 market DB，重算 source
window、session dates、candidate universe hash，並檢查 DB 讀取前後 hash。只有
`validate_machine_revalidation_bundle`、scheduled resolver 與正式 acceptance projection
都通過，才會在 projection 中出現 `machine_revalidation_verified`。receipt 缺失、
child／parent hash 不一致、source window 漂移、來源晚於觀測時間或 owner 與 clock 的
machine identity 不一致，都會回傳具體 blocker；把 `acceptance_source` 改成
`owner_message` 不會繞過 receipt。

這個 candidate 不等於正式 Rule credit。正式 Rule capture 仍只能在台北 `09:00–13:30`
使用當下可得的自然來源；若 08:30 後才首次執行 producer，且同日 bundle 不存在，會
顯示 `same_day_rule_source_preopen_window_missed` 並等待下一個有效日，不以事後時間
補建。三項 Formal input 仍須各自完成正式 consumer readback；沒有 Rule、PIT 或 causal
ledger 的真實來源時，Workbench／Scheduled Evidence 應顯示來源缺件或自然等待，不因
缺少人名而誤標人工審核，也不把 candidate 顯示成 `3/3`。

排錯時先讀 status 的 `observed_at`、`source_window_hash`、`bundle_root` 與
`blockers`，再用 receipt 的 `files`、`parent_policy`、market DB hash 與官方 calendar
source hash 逐項比對。不要刪除舊 bundle 來消除錯誤；修復來源後重跑會以相同 bytes
重用，若 bytes 已變則建立新的當日 immutable bundle。此流程只建立 machine evidence，
不下單、不啟動 broker、不訓練 ML、不開啟 Formal OOS 或 promotion。

### 05:15 Evidence 的 Paper 來源與 Direct 狀態

05:15 scheduled dry-run 會明確傳入隔離 Paper operation root、health baseline 與
status path。預設來源是 repository 的
`output\paper_execution_eod_replay\paper_portfolio\paper_portfolio.sqlite`、
`<OUTPUT_ROOT>\position_health\latest.json`，以及該 operation root 下的
`scheduled\paper_portfolio_isolated\latest_status.json`。同一份 canonical status 也作為
health refresh 的 preopen coverage receipt，
並使用 operation root 的 `paper_trade_ledger.sqlite`。需要覆寫時使用
`--paper-evidence-operation-root`、`--paper-evidence-health-baseline`、
`--paper-evidence-status-path`、`--paper-evidence-health-status-path` 與
`--paper-evidence-ledger-db`；這些路徑只供唯讀證據接線，不會改寫 Paper ledger、D 槽
原始資料或 evidence DB。

Paper evidence source 會在同一個 SQLite read transaction 讀取請求日前最近的 snapshot
及 positions，並記錄 canonical row hash、`data_version`、status bytes hash 與 health
baseline hash。未來日期、缺檔、讀取期間 bytes 改變、coverage 不完整、schema／boundary
不符或 status 未通過時，回傳 `unknown`／`MISSING`，不建立 attribution 或 risk prompt。
健康基線過期或欄位不足時，仍可保留實際 `WATCH` 等已驗證 attribution，但 section 會是
`degraded` 並留下 warning；這只能改善追溯性，不會把 scheduler readiness 改成 ready。

在 `source_coverage` 中，`portfolio_alert_snapshot_available` 與
`risk_prompt_snapshot_available` 表示有可讀的 section；`*_capture_ready` 則仍要求
品質與 warning 條件全部通過。遇到已讀到但品質降級的 section，會記錄
`*_snapshot_quality_not_ready`，不再誤寫成 section 缺失；`portfolio_alert_not_ready`
與 `risk_prompt_not_ready` 仍須保留，直到正式品質條件通過。操作人員應同時查看
`paper_evidence_source` metadata、snapshot／health hash、`blockers`、`warnings` 與
`source_coverage`，不能只看 Task Scheduler exit code。

Direct chain 的外層 `execution_started` 只有在 inner
`v3_refresh_chain_status.json` 的 stage 與已驗證 child command line／training output
一致時才可為 true；launcher 存活本身不代表 fit 已開始。`fit_completion_verified`
必須同時看到 inner stage、OOC 與 release 都是 `complete`，否則保留 running 或
unknown／failed 投影。狀態投影只讀 live owner／child evidence，不停止、重啟或宣告
現行自然 Direct 程序完成；容量、checkpoint、stage、PID 與 custody 證據仍須一併判讀。

05:15 的 daily health refresh 會在 evidence child 前把最新成功結果寫成
`<OUTPUT_ROOT>\position_health\baseline_YYYYMMDD.json`，並以 atomic
`<OUTPUT_ROOT>\position_health\latest.json` 供 consumer 讀取；重跑相同 bytes 會 reuse，
內容變更則保留舊檔並建立 hash suffix。refresh blocked 時，consumer 會收到不存在的
 sentinel path，顯示 `unknown`／`MISSING`，不沿用舊 baseline。只有前一份 baseline 的
`source_snapshot_id` 與本次 Paper snapshot 完全相同，或受控 preopen coverage receipt
同時綁定兩端 snapshot、同一 ledger 路徑與 transaction row digest，且期間沒有該代號
事件時，才可保留同一筆連續持倉的人工作業欄位；snapshot 變更、同代號重新進場、
coverage 缺失或 ledger 讀回不完整時，舊 thesis／review／state／reasons 只作歷史來源，
當前列回到 WATCH／unknown，不會把 CLOSED、EXIT_CANDIDATE 或過期 review 投影到新的
持倉。新 `observed_at` 只代表來源刷新時間，不代表 thesis 已更新。若啟用
`--derive-position-identities`，`PaperPositionIdentityProvider` 會另外在同一 bounded
ledger window 中驗證 flat→positive 的 filled buy，並以 canonical event hash 產生
stable `position_id`／`entry_lineage_id`；已驗證且沒有 flat transition 的持倉才可
carry，closed→reentry 會建立新 ID，找不到合法 entry evidence 則明確保留 null／unknown。

05:15 health lane 會在 transition evaluator 前執行
`--produce-position-health-sources`，呼叫
`app_module.position_health_market_source_producer.PositionHealthMarketSourceProducer`。
它先驗當日 quick update 與 data freshness receipt，再以 `mode=ro`／`query_only` 讀
同一決策日的 `technical_indicators` 與 `daily_prices`；SQLite 的 `YYYYMMDD` 日期會
嚴格對齊 decision date，selected rows 的 code、日期、Decimal 欄位與 DB
stat／`data_version` 會綁進 source snapshot hash。producer 將 `close_price`、
`open_price`、`high_price`、`low_price`、`volume`、`RSI`、`MACD`、`MACD_signal`、
`MACD_hist`、`MA5`、`MA10`、`MA20`、`MA60`、`ATR`、`ADX` 以 Decimal text 寫入
metrics source；condition 只表示已取得 PIT 市場觀測，沒有 entry thesis／regime／
score 時維持 observation-only，不生成投資結論。現有 monitor 的展示 DTO 可能是
float，但核心 metric 與風控比較仍由 Decimal provider 處理。

source artifacts 位於 `<OUTPUT_ROOT>\position_health_sources\`，包含
`condition_YYYYMMDD.json`、`metrics_YYYYMMDD.json`、`source_receipt_YYYYMMDD.json`
與 `latest_status.json`。前三類日期檔採 create-only immutable：相同 bytes 重跑會
重用，異動會建立 hash suffix 並保留舊檔；只有 latest pointer 可 atomic replace。
receipt 的 `market_capture_started_at`／`market_capture_completed_at` 是實際 SQLite
讀取起訖。自然 CLI 不凍結 `now_provider`，capture completion 作為 source 的有效
decision clock，scheduled wrapper 會用這個 completion timestamp 呼叫 evaluator；若
明確指定較早 `--decision-at`／`--observed-at` 而實際 read 越過 cutoff，命令會
fail closed，不能拿早期 quick receipt 將目前 DB rows 回填成歷史資料。baseline 沒有
可驗證 stable position identity 時不掃描大表，也不把 stock code 當 position ID，
只列出 `unresolved_identity_codes` 並維持 degraded／unknown。

同一個 05:15 CMD 也會把 baseline 送入
`app_module.position_health_transition_evaluator`，結果寫在
`<OUTPUT_ROOT>\position_health_transition\`。這是 proposal-only 的隔離輸出：
`apply_transition=false`、`auto_action_allowed=false`、`broker_execution=false`、
`formal_credit=false`。完整且具 PIT custody 的 thesis、condition、metrics 與官方
calendar 才能得到 `passed`；official calendar 會從已驗證的
`output\paper_execution_eod_replay\calendar_cache\` 唯讀載入，並把 cache／官方
response hash、available／expiry 與交易日範圍放進 provenance。若要覆寫來源，可在
Python CLI 使用 `--thesis-registry`、`--condition-source`、`--metrics-source`、
`--calendar-cache`、`--temporary-closure-cache`；scheduled wrapper 對應使用
`--paper-health-*` 參數。所有 source 都必須帶 immutable 內容 hash、PIT as-of、
`available_at <= decision_at`，並以 stable `position_id`／`entry_lineage_id`／stock
code 綁定；future、竄改或 identity 不符會 blocked，缺檔維持 `unknown`／`degraded`。

05:15 CMD 也會以 `PAPER_HEALTH_POLICY_SOURCE`（預設為
`<REPO_ROOT>\output\formal_daily_publications\rule_source\scheduler\rule_source_latest_status.json`）
讀取已驗證的 Formal Rule machine source。這只提供 Rule ranking 的來源／時鐘／安全
provenance；它不會被當作 Health state machine 的 `policy_hash`，也不會自動生成
`entry_thesis`、invalidation rules、holding horizon 或 reviewer approval。輸出中
`result.policy_hash`／transition event 的 `policy_hash` 是 Health transition policy，
Formal Rule hash 位於 `provenance.policy.policy_hash` 並進入 input hash。來源缺失、
future receipt、hash／schema／安全邊界錯誤會維持 fail-closed blocker；要讓策略提供
持倉失效條件，必須另有版本化、可驗證的 explicit forward policy JSON。

目前 Formal Rule source 實際沒有每筆持倉的 thesis、invalidation 或 horizon，所以
即使 machine source verified，health 仍可能是 `degraded`／`WATCH`。這是資料契約缺口，
不能用新鮮的 Rule receipt 或 recommendation 文案填補。

若要讓未來新 Paper entry 使用 machine policy，owner 應依
`docs/06_qa/V4_FORWARD_MACHINE_POLICY_CANDIDATE_2026_09_08.md` 的候選參數建立並
核准版本化 `forward-position-policy.v1`。目前已建立的 approved artifact 是
`output/forward_position_thesis/policies/paper-machine-thesis-benchmark-v1_2026-09-08-approved-v1.json`，
scheduled recommendation caller 已預設把 `FORWARD_THESIS_POLICY_PATH` 指向它；需要
更換參數時必須使用新版本，不能覆寫既有 bytes。日曆完整 bytes 另存於 policy 專屬
immutable snapshot；日後 calendar renewal 只產生新的觀測／snapshot evidence，保留原
policy identity 與 hash。

calendar renewal 的 current selection 由同一 repository
`output/v4_ml_forward_scheduler/calendar_cache_refresh/latest_status.json` 提供。05:10
scheduled recommendation 只接受 read-only、candidate-only 且沒有 child／credit／
production action 的 `cache_valid_for_forward_horizon`／`refreshed` receipt，重驗 receipt
指定的 exact cache path／file hash；候選的 `calendar_cache_path`／hash 仍是 policy 的
immutable custody，另以 `calendar_observed_path`／`calendar_observed_sha256` 保存 current
observation。receipt 不可用時維持 blocked／degraded，不把過期 pin 或任意舊檔冒充新日曆。

05:10 producer 會把 policy path／bytes hash／actor 凍結到候選；05:15 的
`--bind-forward-thesis` 會重新驗證 policy、推薦、Paper fill 與 entry lineage，依官方
交易日重算 review date，並將 `source_type=machine_policy` contract 交給
proposal-only Health evaluator。缺 policy、時間或 hash custody 時保持 degraded；
machine contract 仍需 `human_approval_required=true`，不寫人工 registry、不自動交易。

目前 9/8 baseline 已完成 source-to-ID provider 與 market source producer 的唯讀驗證，
但 bounded window 沒有三筆既有持倉可用的 entry event，故仍是 stable lineage unknown；
market source 的真實 capture 已接上，但 condition／metrics row 仍為 0，人工 thesis、
PIT condition 或 Decimal metrics 也未提供，因此結果維持 `degraded` 是資料品質結論，
不是 transition 完成。

#### Position Health read model 的 Portfolio／Workbench 呈現契約

`app_module.position_health_transition_read_service.PositionHealthTransitionReadService`
是 05:15 evaluator receipt 的唯一唯讀 consumer。它會重讀
`position_health_transition\latest_status.json`、result 與 latest pointer，驗證 result
hash、producer／schema、安全邊界、decision／observed clock、Paper snapshot id、rows
hash、cohort、`position_id`、來源 `available_at` 與 freshness；缺檔、future、stale、
竄改、scope 或 hash 不一致時，會保留實際診斷並撤銷當前 action，顯示 `WATCH`／未知，
不把 raw dictionary 當成 UI authority。

Portfolio 與 Workbench 都只消費同一份 typed `PositionHealthReadModel`。Workbench 的
`持倉健康／退出候選` 區塊直接呈現 Paper `HOLD`、`REDUCE_CANDIDATE`、
`EXIT_CANDIDATE`、`WATCH`、why／why-not、來源與人工 review。Portfolio 的人工交易
持倉 identity 是 `default:<stock_code>`，Paper health identity 是
`paper:<portfolio>:<stock_code>:entry-...`；兩者不以股票代號相接。Portfolio 因此把
Paper rows 放在獨立的唯讀區塊，人工持倉表只有 exact identity 命中才可顯示對應 action，
否則固定 `觀察／未知`／`未精確對應`。人工持倉的價格日期不會替 Paper receipt 決定
scope；Portfolio 僅以 receipt 自身日期及一日 freshness gate 判斷是否仍可作當前展示，
過期資料可被診斷但不稱為當前可用建議。

短版主摘要只保留使用者可採取的狀態、日期、筆數、需要確認與下一步；table 欄位使用
「研究建議／評估原因／需要確認」，已知 evaluator reason 轉為中文。cohort、hash、
完整 identity 與原始 blocker 留在選取列／技術詳情，缺 receipt 則顯示「尚無持倉健康
評估資料」與重新整理指引，不直接顯示 Python 例外路徑。

上述區塊只刷新讀模型與 Qt model，不執行 evaluator、不寫 receipt／registry／scheduler、
不改 Paper 或人工 ledger、不下單、不自動平倉、不修改 allocation。所有 action 都是
`research_only=true` 的 proposal，人工 review 仍是必要邊界；本增量不建立
`user_declared` entry layer。

人工 thesis 只能由 reviewer 明確建立，不能由 recommendation、ML 或 evaluator 捏造。
使用 `scripts/record_position_thesis.py` 寫入指定的 derived append-only registry：

```powershell
.\.venv\Scripts\python.exe scripts\record_position_thesis.py `
  --registry <DERIVED_OUTPUT>\position_health\thesis_registry.json `
  --position-id <STABLE_POSITION_ID> `
  --entry-lineage-id <STABLE_ENTRY_LINEAGE_ID> `
  --stock-code <CODE> `
  --entry-date YYYY-MM-DD --decision-date YYYY-MM-DD --available-date YYYY-MM-DD `
  --available-at <AWARE_ISO_TIMESTAMP> --authored-at <AWARE_ISO_TIMESTAMP> `
  --authored-by <REVIEWER_ID> --entry-thesis <EXPLICIT_HUMAN_TEXT> `
  --holding-horizon-trading-days <POSITIVE_INT> --next-review-date YYYY-MM-DD `
  --source-trace <SOURCE_TRACE> --invalidation-rules <JSON_ARRAY>
```

`--invalidation-rules` 每個元素需含 `metric_id`、`operator`、Decimal 文字
`threshold` 與 `action`（`reduce` 或 `exit`）。registry 每次追加版本；相同版本重跑
會 idempotent，同一持倉／effective date 的不同內容會拒絕。這個命令不修改 Paper、
Formal 或 D 槽；沒有 reviewer 輸入時不要建立空白或推測 thesis。只有真正 reviewer 的
`human_approved` event 才能改變 transition repository 的 recorded state。

### Formal／Paper runtime calendar 的跨日與跨月滾動（V4）

Paper EOD 的既有 `scripts\scheduled\run_paper_execution_daily_isolated.cmd` 會透過
`paper_execution_retry_runner.py` 呼叫 `formal_runtime_roll_forward.run_from_environment`。
受控環境只需一次性 pin `FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE`；以 2026-09-09 起算的
active v6 bundle 涵蓋 9/9–9/30，9/10、週末及後續開市日會依同一份官方日期列自動選取，
不需要每日人工改環境變數。固定 portfolio clock 的 activation 與 identity 維持原值，
daily Rule source 的日期版本可更新，但不能把 daily source 當成新的累積 portfolio clock。

當 anchor bundle 用盡日期時，runtime 只依 source bundle 的完整 `bundle_hash` 讀取
`<PUBLICATION_ROOT>\calendar_candidate_archive\rotations\<source-hash>.json`。successor
link 必須通過自身 hash、來源／後繼 bundle 的 file hash、連續日期範圍及 raw custody；
不掃描 `latest`、不接受任意路徑、未知或損壞日期證據會 fail closed，只有官方明示兩市場
休市的日期可跳過。找不到已保存 link 時，既有 caller 會以 31 個曆日為界，使用官方
TWSE 年度 holidaySchedule 與 TPEx 月度 mktCalendar 的 bounded capture，再呼叫既有
`scripts\persist_official_calendar_bundle.py` 建立 repository candidate archive。實際
capture 會保存 exact response bytes、metadata、raw manifest、candidate bundle、archive
manifest 及 hash-keyed successor link；TEMP 只作中途輸入，成功後即清除。

跨月 renewal 的受控命令由 runtime 內部以等價參數執行：

```powershell
.\.venv\Scripts\python.exe scripts\capture_official_calendar_bundle.py --start-date <NEXT-DATE> --end-date <NEXT-DATE+30> --confirm-network --output <TEMP>\calendar.json --raw-output-dir <TEMP>\calendar_raw
.\.venv\Scripts\python.exe scripts\persist_official_calendar_bundle.py --bundle <TEMP>\calendar.json --activation-date <NEXT-OPEN-DATE> --publication-root <REPO_ROOT>\output\formal_daily_publications --qa-output <REPO_ROOT>\output\formal_daily_publications\calendar_candidate_archive\rotations\renewal_receipts\<bundle-hash>.json
```

這兩條是受控 producer／persistence 命令，不能在時窗外用人工日期冒充自然執行；
現有 active binding、舊 bundle 與 D 槽原始資料均不覆寫，也不因此產生 Formal credit。
capture、persist、raw validator 或 link readback 任一失敗時，舊 anchor 保留，rolling
status 顯示 degraded／非零 exit，下一次可針對同一邊界重試。候選 archive 通過後仍須由
root 以獨立 readback 審核，才可考慮受控設定切換。

Formal／Paper 每日 0/3 到 3/3 的判讀也必須依自然時窗：先執行 PIT 盤前 capture，
再由盤後 sidecar 與 session source capture 重用 exact custody，接著執行 Formal input
producer 建立三份 receipt 與 common identity，最後才讀 Formal operational readiness。
`inspect_ml_formal_input_readiness.py` 的 3/3 隔離測試只代表三個 producer artifact 可被
正式 consumer 重載，仍保持 `formal_oos_allowed=false`；實際自然 credit 還需同日
event-time、fill／費稅、日期窗、三份 receipt、common identity 與 scheduler readback
同時通過。等待窗口或缺來源時，readiness 應維持 `blocked_no_formal_credit`，不可用
隔離 fixture、delayed EOD 或人工時間參數補成 3/3。

目前一次性 v6 binding 由 `FORMAL_DAILY_RUNTIME_CONFIG_ROOT` 按台北自然日讀取
`YYYY-MM-DD.json`；Paper retry runner 在同日 retry 結束後呼叫既有 roll-forward，建立
下一個官方開市日 candidate config。週末、跨日與跨月沿 exact calendar successor link
續接，固定 portfolio clock 不重置；若 config、calendar、Rule/PIT/Paper source 或
common identity 任一不完整，caller 以 blocked／degraded 與非零狀態保留證據，等待
下一個合法自然時窗。

dependency gate 對週末 `not_trading_day` 與官方明示無資料日都在 Paper adapter 前
作明確 no-op；它不建立 fill，並保留同一 bounded roll-forward 以準備下一個官方開市日。

## 2026-09-15 關閉與跨頁研究 continuity

主視窗閒置時按一次右上角 `X` 即可關閉。若仍有背景 worker 或 TPEX 背景更新，
第一次 `X` 會暫停關閉、凍結新的 refresh，並顯示等待原因；背景工作在安全邊界完成後
會由 UI 自動完成關閉，不需要再次按 `X`，也不要用工作管理員 End Task。

TPEX 背景更新的取消是合作式請求：UI 只建立 cancel marker，背景程序完成目前網路、
檔案或 SQLite 安全邊界後，才會寫出 `status=cancelled` 且
`cancel_completed=true` 的收尾收據。若程序非零退出或只留下不完整狀態，畫面會保留
失敗與退出碼，不可把它解讀成已安全取消。

跨頁研究時，從推薦分析選取股票後開啟個股研究；返回或切到觀察清單時，系統依
`result_id + stock_code` exact identity 還原原推薦來源。相同股票但不同推薦結果仍是
不同 candidate；若來源 identity 不完整或互相衝突，畫面會限制寫入，需回到推薦分析
明確選擇來源，不會以「最新結果」猜測。觀察清單與個股研究的 accepted、note、下次
檢視時間及歷史會從 append-only journal 讀回；這些 continuity 記錄不等同交易指令，
也不會自動送出 broker 或改變正式行情資料。

## 2026-09-17 A／B／C bounded 狀態與操作邊界

本節是目前 working tree 的狀態補充；操作時仍以 read-only／shadow／research-only 邊界
判讀，不把 bounded engineering receipt 當成正式產品 Gate。

本輪 focused validation 合計 `77 passed`：A wrapper／identity／durable receipt `33`、B maturity
calendar wiring `27`、C learning-evidence denominator projection `17`。A 先前 child／service
suite 的 `24 passed` 是既有 coverage，未在本輪重跑，不併入本輪 `77`；工程驗收也不會自動授予
natural、calibration、Paper 或 Formal credit。

### A：Paper、calendar 與 Recommendation

Recommendation receipt 的 source、calendar 與 14 筆 candidate file hash 已由 root 逐欄
核對；calendar capture／availability 為 2026-09-14，早於 2026-09-17 candidate decision。
這 14 筆只能在 candidate-only 範圍閱讀，不能當 Paper 或 Formal evidence；`1418` 目前只有
rejected sell，沒有 filled entry source，維持 unproven。Paper 要判定完成，必須在同一
decision date 同時具備 terminal run、latest／immutable phase receipt、
`calendar.available <= decision` 與 source／state hash；heartbeat 舊 snapshot 不構成完成。

使用 Paper actual loader 時，`calendar=None` 會解析到 `CALENDAR_CACHE_ROOT`；該 default
loader 的正反例已通過 2 tests。2026-09-17 legacy 05:45 實跑為 `passed_with_warnings`，
BankTaiwan 為 pending 18、matured 0；raw PIT 為 invalid 7、unavailable 16,913。
official-events 的 `prior canonical raw lineage missing` 已定位並修復為 reader compatibility gap。
A lineage path 跨檔 focused QA 為 `8 passed`（其中 `tests/test_official_market_event_prior_lineage.py`
含 3 tests）；隔離 next-publication real chain 的 output-only readback 為 `runs=1`、`events=28,636`、
`raw=95`、`missing=0`，且 source bindings 均在 self-contained output 內。先前 failed latest receipt
仍保留其歷史狀態；正式 job 尚未重跑，因此不能當 Paper／Formal 完成，也不能歸類為 raw 缺件或純
external missing。ancestor custody review 同樣核對 current 37＋ancestor 43＝80 required raw
hash、missing 0 且 raw bytes 全驗證。詳見 [A operations latest status review](../06_qa/A_OPERATIONS_LATEST_STATUS_REVIEW_2026_09_17.md)。

formal input readiness 的原始 aware clock 為
`training_as_of=2026-09-17T11:19:45.4764372-07:00`、
`created_at=2026-09-17T11:19:46.502565-07:00`；loader 以 `Asia/Taipei` 轉出的
`training_as_of_date` 為 `2026-09-18`，readiness 為 `0/3`。三個 configured input path
仍為 `clock-20260819` 且 `prospective_output_not_published`；這只表示 configured input
缺失，不能外推 D 槽沒有其他產物。artifact SHA256 為
`e75d4130d486dd2b6bae0dae532afc8040765ff51e2f8f53497738b24a839614`。

### B：historical context／label assembly

B 的 historical feature assembly 以 observed market／stock date union 建立時間軸，保留
requested cutoff、market gap 與 stock gap 的 explicit empty slot，不會把上一個 market date
冒充 cutoff，也不會用 trailing row count 壓縮 missing-middle session。閱讀 B report 時，
請分開 row-count、observed-calendar exact join、price value completeness 與 horizon
completeness；`market_indices` 的 DISTINCT 日期只是 observed calendar，不能當 official
完整交易日曆。故目前 horizon、formal 與 training credit 均為 false。

bounded report 位於
`C:\Users\archi\.codex\visualizations\2026\09\17\01a0aea7-bd95-70c2-8ff6-a355b6b1f216\b_historical_context_inventory_20260917.json`
及同名 `.md`，report hash 為
`sha256:06304a44340e3cfad623c2710e6bd84cd1d479950df0c344623ba3a2ad8f1b72`（排除自身欄位後的
canonical logical hash；JSON file SHA256=`f6c3d15bb04f93782c1b42a903a3934fdd30109f6039c0d541c3bf14a7fef698`）。報告中的
observed／contract-scope keys 未組裝、actual row present 但 price unavailable、真缺 price、
隔離不等價與 availability／custody unknown 需按各自分類閱讀；「observed／eligible」不能
直接解讀為 training eligible。舊 16919 keys v2 JSONL 早於本次 window 修正，不可用來宣稱
新的完整 horizon。此 bounded slice 不執行正式 D 寫入、candidate10 apply、重建或 scheduler
設定修改。

### C：personalization fit

C 的 fit producer／persistence／CLI、artifact persistence 與 readback engineering 已 bounded
accepted。fit runner／CLI／calibration／read service focused suite 為 `41 passed`（`2.37s`）；
wrong-scope empty evaluation 以 exit `2` fail-closed，且不產生 evaluation／verified binding。
acceptance artifact 為 `c_personalization_fit_acceptance_20260917.json`，SHA256=`d45033e0ea8a4c418150df685e96d26d7425872a6c633695f0aa752054f0a3d3`。

可用下列 CLI 產生隔離的 bounded fit artifact；所有 scope／日期／cutoff／output identity 必須由
caller 明示，artifact 的建立 clock 由 runner 的 runtime UTC clock 產生（CLI 不接受歷史
`created_at`）：

| 參數 | 語義與預設 |
|---|---|
| `--scope-id` | 必填；exact scope identity，不能由 profile、holding 或 portfolio 猜測。 |
| `--fit-as-of` | 必填；fit cohort 的日期 cutoff，row 的 decision／label／outcome 可得時點須不晚於此日。 |
| `--evaluated-as-of` | 必填；evaluation cohort 的日期上限，可與 fit 日期不同但不可早於 `fit-as-of`。 |
| `--evaluation-cutoff-at` | 必填 aware instant；evaluation 的精確可得時點，日期不可晚於 `evaluated-as-of`，不等同 fit cutoff。 |
| `--output-root` | 必填、唯讀來源根；供 `PersonalizationReadService` 讀 Recommendation／Journal／Evidence source。 |
| `--output-path` | 必填、artifact 發布目標；以 atomic create-only 寫入並 read back，不覆寫既有檔案，也不可為 symlink。 |
| `--artifact-id` | 選填；fit artifact 的明示 identity；省略時由 evaluator 建立 immutable identity。 |
| `--shrinkage-strength` | 選填 fixed beta shrinkage 強度，預設 `10`。 |
| `--embargo-days` | 選填非負整數；省略時採 row 的 `horizon_days` 作 effective embargo，evaluation 會排除 fit cutoff 加上 embargo 內的 row。 |
| `--min-fit-rows`／`--min-fit-decision-dates` | fit 最低 row／獨立 decision-date 數，預設均為 `2`；不足會 blocked，沒有合格 artifact。 |
| `--max-results`／`--max-candidates-per-result` | source read 上限，預設均為 `100`。 |
| `--max-evidence-events`／`--max-journal-rows` | source read 上限，預設分別為 `500`／`50,000`；四個 max bounds 避免無界讀取。 |
| `--journal-path`／`--evidence-db` | 選填 caller-owned Journal JSONL／Evidence SQLite source path；SQLite 僅由 read service 唯讀讀取。 |
| `--result-id`／`--stock-code` | 選填 exact source identity filter；不以相鄰 row 或其他股票補值。 |

```powershell
.\.venv\Scripts\python.exe -m scripts.run_personalization_fit `
  --scope-id <explicit-scope> `
  --fit-as-of YYYY-MM-DD `
  --evaluated-as-of YYYY-MM-DD `
  --evaluation-cutoff-at <aware-iso-datetime> `
  --output-root <caller-owned-read-root> `
  --output-path <isolated-fit-artifact.json> `
  [--journal-path <journal.jsonl>] [--evidence-db <twstock.db>] `
  [--result-id <exact-result-id>] [--stock-code <exact-stock-code>] `
  [--artifact-id <new-artifact-id>] [--shrinkage-strength 10] [--embargo-days <n>]
```

fit CLI 的 exit `0` 僅代表 run result 為 `created` 或 `idempotent_retry`：新 envelope 已
create-only 發布並完成 readback，或同一 output path 的 request／clock／source binding 完全相同而
重用 immutable artifact。它不代表 fit／evaluation 樣本足量；`evaluation.status` 仍可能是
`insufficient_evidence`、`evaluation.rows=[]` 或 `decision=retain_population`，此時以 degraded／
research-only 判讀。來源不完整、fit minimum 不足、request／artifact conflict 或 source fingerprint
變更會 exit `2` 且不發布新 artifact；同一路徑不能覆蓋成另一組參數。要改參數、caller-supplied
clock、source binding 或 artifact identity，必須使用新的 output path／artifact。

使用既有 inspector 做完整 envelope 讀回與 evaluation binding 檢查：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.inspect_personalization_sources `
  --scope-id <explicit-scope> `
  --as-of YYYY-MM-DD `
  --evaluation-cutoff-at <aware-iso-datetime> `
  --output-root <caller-owned-read-root> `
  --journal-path <journal.jsonl> `
  --evidence-db <twstock.db> `
  --result-id <exact-result-id> `
  --stock-code <exact-stock-code> `
  --fit-artifact <isolated-fit-artifact.json>
```

Inspector exit `0` 代表 source／envelope binding verified（未提供 fit artifact 時則只讀 source
report）；它仍可能回報 evaluation insufficient／degraded。fit artifact invalid、scope／row／
source fingerprint 不一致或 binding 未驗證時 exit `2`，不建立 evaluation。runner 保存的
`evaluation_temporal_semantics` 固定為 `mode=retrospective_offline`、`prospective=false`、
`natural_forward_credit=false`（natural=false）；這條離線 fit／evaluation 不授予 natural、Formal
或 production credit。

9/17 PIT completion audit 的唯讀 artifact 為
`C:\Users\archi\.codex\visualizations\2026\09\17\01a0aea7-bd95-70c2-8ff6-a355b6b1f216\PIT_COMPLETION_AUDIT_20260917.json`
（SHA256=`38fbb42fd6134e70068a01454b659094610d3783c160c39eb42991fe8d7796cf`）。denominator refresh
在 DNS／HTTP response 前失敗，未進 CSV parser；同 URL 的 9/11 artifact 可解析，因此不能把它當
parser code defect。9/17 denominator 未驗證、taxonomy publication blocked、security lifecycle
仍為 historical research replay、formal sidecar 不存在；`5371` 與 `3718` 不得 carry-forward。
這些是 source／formal gate evidence 缺口，不能以 candidate sidecar 充當正式資料。

### C：learning-evidence denominator projection（2026-09-18）

本輪 C denominator projection focused suite 為 `17 passed`。在 legacy lane 中，原始 verifier
結果為 `7 captures／21 rows／3 decision dates`；依既有 identity／source／cost／horizon
契約去重並保守排除 conflict 後，valid 累積分母為 `2 captures／16 rows／2 decision dates`，
`capture_conflict_count=5`、`capture_scan_status=complete`，latest snapshot 另為 `14 rows`。
累積 valid prediction 分母與 latest snapshot row count 不得混用，且不得與 BankTaiwan lane
混算。新的 policy binding 尚未以真實成熟 positive receipt 驗證，`policy_binding_status=unknown`；
projection 不代表 adoption，不得宣稱升級 ready，也不授予 natural／calibration／Formal credit。
完整來源、去重／衝突／截斷契約與 raw QA 入口見
[Learning Evidence Denominator QA](../06_qa/LEARNING_EVIDENCE_DENOMINATORS_2026_09_18.md)。

目前 module trees 指定範圍 mypy 為 630 source files clean（scripts excluded，僅 2
untyped-body notes）；A／B bounded slice 與 C engineering acceptance 不代表 ABC、V4 formal 或
V6 完成。全局 active work 仍維持 `in_progress`。

## 2026-09-20 ML natural shadow weekly report 判讀

ML natural shadow 的 weekly projection 是唯讀證據摘要，不等同 V2.2 weekly collection，也不會因週日自動授予 natural、Formal、promotion 或 production credit。`\baldr-v2-2-weekly-collection` 上次成功執行為 2026-09-13 18:00 Pacific、下次為 2026-09-20 18:00 Pacific（台北 2026-09-21 09:00）；排程尚未到不代表自然 evidence 已成熟。判讀時應以實際 `as_of_date`、source hash 與報告期間為準。

每日 caller 的 primary sidecar 是 `<OUTPUT_ROOT>\scheduled\ml_allocation_copilot\shadow_evidence_collector\shadow_evidence.sqlite`。若要把既有 forward candidate sidecar 放入同一份週摘要作交叉診斷，caller 設定 `ML_FORWARD_OUTPUT_ROOT=<repo>\output\v4_ml_daily_derived_shadow_real_v2`；runner 只讀取其下相同的 `scheduled\ml_allocation_copilot\shadow_evidence_collector\shadow_evidence.sqlite`。forward lane 固定標示 `diagnostic_only=true`、`promotion_authority=false`、`eligibility_contribution=none`，不可併入 primary matured／eligible cohort。

週摘要中的 `pending_reason` 與 `pending_is_normal_wait` 必須一起判讀：

- `pending_is_normal_wait=true` 只表示整個 pending cohort 的原因都是已知 `time_wait_only`，例如已具 credit、availability、custody identity、只等待 h60 outcome；它仍不表示已成熟。
- `contract_blocked` 表示自然日 credit、formal custody、availability 或 all-horizon contract 缺件；`blocked_unknown` 表示未知原因，兩者都不是正常等待。`source_missing`、空 cohort 與 `not_time_wait_only` 也必須保留為 false，不能用空列表的 `all()` 推成正常等待。
- 單筆列入 matured 仍需 h5／h10／h20／h60 全部完成及來源契約通過；整體 `ready_for_pruning_review` 另須達既有樣本數與 downside class gate。partial h5／h10／h20 只能作觀測。`promotion_day_credit_blockers` 應原樣顯示，不能由 summary 自行補值。

本次真實 readback 為 primary `29` 筆、matured `0`、contract-blocked `29`、natural-credit eligible `0`；forward companion 實體 `1` 筆、matured `0`、eligible `0`。projection 見 [W38 real weekly evidence](../../output/qa/natural_shadow_weekly_audit_20260920/natural_shadow_pruning_evidence/weekly/2026-W38/asof_2026-09-18_evidence_24fd5e2aeda9500a.json)，工程 QA 與排錯脈絡見 [Natural Shadow Weekly Evidence Audit](../06_qa/NATURAL_SHADOW_WEEKLY_EVIDENCE_AUDIT_2026_09_20.md)。focused QA 為 [24 passed](../../output/qa/natural_shadow_weekly_audit_20260920/focused_pytest_final.log)，另有 [mypy](../../output/qa/natural_shadow_weekly_audit_20260920/mypy_targeted_final.log) 與 [py_compile](../../output/qa/natural_shadow_weekly_audit_20260920/py_compile_final.log) readback。若報告顯示 `contract_blocked` 或 `blocked_unknown`，先檢查 primary／forward sidecar 是否存在、`sidecar_file_hash`、`read_cutoff_date`、`promotion_day_credit_blockers` 與各 horizon reasons；不要重跑 scheduler、回填舊 raw 或把 forward diagnostic 提升為 credit。

## 2026-09-20 TPEX 背景 technical publication receipt 判讀

使用 `scripts/run_tpex_full_refresh_and_technical.py` 執行背景 TPEX 更新時，入口會先更新日價，再依 technical step 的實際結果建立 `technical_computation_evidence`，最後寫入既有的
`<OUTPUT_ROOT>\scheduled\technical_indicator_publication\<source_date>\<receipt-id>\receipt.json`。操作參數仍是 `--start-date`、`--end-date`、`--state-file`、`--sync-sqlite`、`--twse-update`、`--technical-force-all`、`--tpex-workers` 與可選的 `--cancel-file`；這個入口不接受歷史 clock 來冒充新的 publication availability。

讀 receipt 時必須同時確認 `technical_step_status=passed`、`technical_computation_evidence_status=verified`、source receipt／raw response hash、technical output value binding、lineage 與 exact symbol coverage。若 technical step 是 currentity skip，必須看到可重驗的 computation reuse lineage；找不到時狀態應為 blocked，不可把 checked clock 寫成新的 technical receipt。`prospective_available=true` 只表示未來 prospective source contract 可讀，仍不代表 20-session natural maturity、calibration adoption、active promotion 或 broker action；`historical_pit_eligible=false` 與 `formal_source_contract_eligible=false` 必須保留。

本次背景 publication 接線與隔離 readback 的 QA 見 [TPEX Background Technical Publication QA](../06_qa/TPEX_BACKGROUND_TECHNICAL_PUBLICATION_2026_09_20.md)。該 QA 的 current positive 只在 QA snapshot 中完成；正式 latest、formal DB、natural credit 與 scheduler 設定均未由本次工程回填或改判。

## 2026-09-21 每日推薦 learning technical child routing

執行 `scripts\scheduled\run_recommendation_calibration_learning.cmd` 或直接執行 `run_daily_recommendation_learning_pipeline.py` 時，只有 technical child 使用與 `DATA_ROOT` 相同的 canonical technical output root：`<DATA_ROOT>\output`；其 `OUTPUT_ROOT`、`RECOMMENDATION_LEARNING_OUTPUT_ROOT`、`--output-root`、`--formal-output-root` 與 `--status-path` 會一致指向該 root。official market-event、recommendation snapshot 與 learning child 仍寫入 caller 指定的 shadow output。`--source-db` 若不是 `<DATA_ROOT>\sqlite\twstock.db`，technical child 會在 quick writer 前以 `technical_source_db_mismatch` fail closed，不猜測或改寫其他 SQLite。

正常 refresh 沒有既有 receipt 時仍使用 caller 的 decision date；formal latest quick status 的 receipt 只作 bounded window hint。只有 `start <= end`、`end` 等於當日 decision date、available time 已到且 Asia/Taipei 日期相符，並通過既有 `reuse_verified_technical_computation_receipt()` 的 current technical output／source custody 驗證，才會沿用多日 window。missing、stale、future 或驗證失敗會回到 decision-date refresh。明確 `--skip-technical-refresh` 也必須有同日且可重驗的 reuse receipt；舊 receipt 不能直接宣稱 skip 成功。

這條 routing 只處理 technical custody 與 writer 邊界，不授予 formal、natural forward、calibration、promotion 或 broker credit；source contract、availability、lineage、value binding 與 maturity gate 仍須各自通過。實作與 focused QA 見 [Formal Scheduler Readiness Audit 2026-09-20](../06_qa/FORMAL_SCHEDULER_READINESS_AUDIT_2026_09_20.md)、[bounded technical routing verification](../06_qa/BOUNDED_TECHNICAL_ROUTING_VERIFICATION_2026_09_21.json)。QA 命令與 exit status 已保存於 verification artifact；本段不代表已執行正式 scheduler。

## 2026-09-21 Paper EOD ledger schema readiness

`scripts\scheduled\run_paper_execution_daily_isolated.cmd` 對應的 EOD writer 在既有 scope/path preflight 通過後、queue selection 前，以既有 `PaperTradeLedgerRepository` 的 create-only schema ensure 建立或補齊 `paper_trade_ledger` 與 `paper_trade_transitions`，再以 `mode=ro`／`PRAGMA query_only=ON` 回讀必要欄位與 row count。這個步驟只建立 schema，不新增 fill、transition、歷史成交或 Formal／ML credit；既有 fill rows 會保留，沒有 transition rows 時仍不可當作 transition evidence。

EOD writer 的 canonical ledger 是隔離 repository output 下的 `paper_trade_ledger.sqlite`。ledger target 若不在既有 operation scope，preflight 會 fail closed；初始化並回讀後仍缺必要表或欄位的 SQLite 不會被標成 ready。空 recommendation queue 與 no-fill result 仍會保留 schema readiness readback。直接使用 `scripts\run_paper_execution_daily.py` 時，省略 `--confirm-append-paper-ledger` 仍是 preview，不能藉由 preview 建立或修改 ledger schema；缺 transition table 的既有 ledger 仍由 ML／Paper consumer 拒絕，必須等待 authoritative EOD writer 完成 schema readback。2026-09-21 已依受控 maintenance receipt 對 canonical repository runtime ledger 執行一次 schema-only ensure；8 筆 fill 的逐列與 aggregate hash 前後一致，transition table 為 0 rows。這不補造舊 9/8 fills 的 transition evidence；當前 window 與後續 ML readiness 必須用正式 caller 參數另驗，不能由全歷史 ledger rows 推導；formal DB、ML child 與 credit 均未執行或改判。

## 2026-09-24 推薦組合回放 Registry 保存與重啟讀回

「策略回測」結果面板的「研究 Registry」分頁可依類型篩選「推薦回放」。只選一筆推薦回放 run 後按「開啟推薦回放」，系統使用 strict reader 驗證已保存 portfolio DTO、Registry／Parquet hashes 與 declared R012 children，並在右側「推薦回放」結果頁顯示保存結果；這個入口不會呼叫推薦 provider、portfolio backtest 或目前行情來源。多選、選取其他 run type、markerless 舊 run 或 integrity check 失敗時不會套用部分 DTO。舊 markerless run 仍可用 Registry 比較查看 metadata／equity／trades，但明示沒有完整 DTO，不從摘要拼回 snapshots。已標記且 DTO 完整、但沒有 declared canonical child 的新 run 會明示 child 不可用：若保存 snapshots 有推薦列則保留推薦列；若 snapshots 為空，則明示本次沒有 recommendation snapshots。這兩種 marked DTO 都不同於舊 markerless run 沒有完整 DTO。

新 Registry 保存需使用該次執行的完整 `RecommendationPortfolioBacktestResultDTO`，並依序完成以下步驟：

1. 若有同次 invocation 的 typed child，UI 先以 create-only 保存各 R012 child artifact，再逐一讀回驗證；完成後才呼叫 Research Run Registry 保存。
2. Registry 內部 staging portfolio result sidecar、equity curve、trades 與 metadata，驗證實際 bytes hashes，執行 guarded manifest／payload-hash finalize，最後發布為 committed。這描述 Registry 自身的受控發布順序；R012 child store 與 Registry 不共用交易，也不會共同回滾。
3. 若沒有可驗的 typed child（包括 `snapshots` 為空），不發布空 lineage sidecar；完整 v1 DTO 仍可保存，manifest 會以相同 parent ID 標示 lineage `unavailable` 和 `canonical_child_unavailable`。若 `snapshots` 有推薦列，讀回會保留這些列；若為空，畫面會標示沒有 recommendation snapshots。若有 sidecar，就不能同時宣告 unavailable。

`ResearchRunService.load_run_data` 可驗 Registry sidecar envelope；child payload bytes 由 strict reader 呼叫 `verify_replay_lineage_children` 讀回驗證。Registry run ID、replay parent ID、legacy portfolio run ID 互不替代。兩個 store 之間的 process-crash 或 child-missing recovery 尚未完成；中途失敗可能留下已 create-only 保存的 child。勿手動刪除或覆寫 artifact；依 owner 的同 ID、同 bytes 流程重試，開啟時如遇 integrity error，保留原檔並走維護處理。

讀回的 summary、snapshots、holdings、contributions、diagnostics、hints、details 與 trades 來自保存 DTO／Parquet，不會依目前資料重跑。因 portfolio DTO 沒有 benchmark 時序，Registry 結果不回抓 benchmark overlay；畫面會標示該圖層不可用。舊「歷史推薦回測」下拉選單仍只列 legacy JSON repository，不收錄新 Registry run；Registry readback 是唯讀，不啟用 legacy 刪除、升級或再次保存。

Registry artifact、R012 child artifact 與 SQLite 各自保存，沒有共同 transaction。若開啟顯示 integrity error，保留原檔並確認 Registry run ID、manifest 與 child reference；不要以重新整理或重新執行回測修補歷史。R012 child 失敗後可能留下 create-only artifact 的處理方式，依上方限制辦理。
