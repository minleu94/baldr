# 10/24 正式市場資料新鮮度重核

> 這是 2026-10-24 的唯讀 live-data 查核收據。它只描述當時正式根目錄與最近一次日更狀態；不代表任何來源 Gate 通過，也不把缺失資料補成推估值。

## 正式 SQLite 與 CSV 尾端

以受控 Windows Job 執行唯讀 SQLite 查詢（8 GiB committed memory、12 個程序、kill-on-close；程序自然結束、Job active process 數為 0）。正式 SQLite 最新日期如下：

| 表 | 最新日期 | 最近列數觀測 |
|---|---:|---|
| `daily_prices` | 2026-10-22 | 10/21：1,965；10/22：1,964 |
| `technical_indicators` | 2026-10-20 | 10/20：1,958；10/19：1,959 |
| `market_indices` | 2026-10-20 | 10/20：1 |
| `industry_indices` | 2026-10-20 | 10/20：75 |

唯讀 CSV 尾端核對：

| 檔案 | 最新日期 | 最新日列數 |
|---|---:|---:|
| `meta_data/market_index.csv` | 2026-10-22 | 1 |
| `meta_data/industry_index.csv` | 2026-10-20 | 75 |

因此大盤 CSV 有 10/21–22，但大盤 SQLite 尚未同步；產業 CSV／SQLite 均停在 10/20；技術指標 SQLite 也停在 10/20。正式資料沒有被本次查核修改。

## 最近一次日更終態

`output/scheduled/data_update_quick/latest_status.json` 記錄的日更範圍為 2026-10-12 至 2026-10-23，終態 `failed`：

- TWSE 的 10/23 請求回 HTTP 200，但 `ALL` 與 `ALLBUT0999` 均回官方「沒有符合條件的資料」；TPEx 對 10/23 回傳 0 列、`source_date=unknown`。排程日曆把 10/23 列為交易日，因此不能把它當休市日或填入推估資料。
- 每日價格檔到 SQLite 的同步步驟回報 `producer_manifest_missing`、row evidence `unknown`；不能據此宣稱 10/21–22 的來源收據已完整。
- 原始日更 log 證實：market CSV 已有 10/12–10/22，大盤更新器因此只向官方請求 10/23；TWSE 回報請求範圍無交易日資料。batch 真正失敗日期是 10/23，但 `latest_status.json` 寫成 `failed_dates=[2026-10-12]`，因 UpdateService 把底層布林失敗錯轉為 `start_date`。這是錯誤的診斷資料。排程採失敗即停止的串接流程，所以本次之後沒有執行大盤 SQLite 發布、產業更新／同步及技術指標重算。
- 官方市場來源封存的 10 月 23 日收據明示 `requested_cutoff_date=2026-10-22`，並含當月 FMTQIK／MI_5MINS_HIST 回應；這佐證該封存範圍到 10/22，不提供 10/23 的行情。

## 本次重跑嘗試與限制

曾嘗試啟動單日 10/23 bounded quick update，但 runner 在容量／日曆／資料步驟前，因既有共用 log `20261024_data_update_quick.log` 開啟失敗（`PermissionError`）而退出。該嘗試沒有更新正式資料；Job 關閉且沒有殘留 child。之後已修正 runner：原 log 被鎖或拒絕開啟時，改用同目錄含 PID 與隨機 ID 的唯一 log；若同目錄也不可寫仍會明確失敗。

本次也沒有套用 market repair：既有正式 repair 工具要求其專用的 `official-market-source-capture.v1` 證據格式，而目前找到的 `official-market-daily-source-capture.v1` 是不同契約；不得把不同 manifest 當成等價證據。需要先完成來源契約銜接或走現行 daily publication 路徑，再作精確日期的正式同步。

## 結論與下一步

這裡有三類不同阻塞：

1. **上游尚無資料**：10/23 TWSE／TPEx 請求未取得當日列，owner 同意不能生成缺失的官方行情。
2. **正式發布未完成**：market CSV 已到 10/22、market SQLite 未同步；產業 CSV／SQLite 與技術指標均停在 10/20。
3. **流程／診斷問題**：10/23 大盤 batch 失敗中止後續步驟，但狀態錯報 10/12；重跑另遇共用 log 權限問題；不同正式修復來源格式不能互換。

後續依序修正 batch 日期診斷，讓 10/23 缺源不抹掉 10/22 及之前可驗證資料的發布機會，再逐表完成 date-scoped 發布與技術指標重算。每個正式寫入須以可驗來源收據、明確日期範圍、before/after 與回復收據完成；本收據不宣稱這些步驟已執行。

## 工程修復驗收補記

`scripts/scheduled/run_daily_data_update_quick.py` 現在只在慣例 log 路徑遇到 `PermissionError` 時退到 run-specific 檔名，並將實際採用的 log 路徑寫回終態 metadata。`scripts/batch_update_market_and_industry_index.py` 將實際逐日成功／失敗日期放進可選 outcome；`UpdateService` 對此介面保留精確日期，只有舊版注入函數才沿用保守 start-date fallback。錯誤的 10/12 標籤已改為實際 10/23，並有 batch 與 service 回歸測試。

受控 Job 內，目標測試組合（batch import／精確失敗日期／service 傳遞／runner）結果為 **33 passed／2 skipped**。兩個 skip 是部分產業 capture 情境；本 Windows sandbox 對 pytest 建立的 `qa-output` 回報 `Path.resolve(strict=True)` WinError 5，capture 寫入契約因此 fail-closed。另一次擴大執行的第一輪有 14 個失敗：其中 13 個 TAIEX capture 整合案例同樣遇到來源暫存目錄解析權限拒絕；第 14 個是新批次日期測試 fixture 缺少 `db_file`，已補正並由後續目標組合測試通過。13 個 capture 整合案例仍需在允許解析測試目錄的環境重跑；第一輪失敗不算驗證通過。未略過正式路徑防護，也未把 skip 算通過。正式 updater 尚未重跑，正式資料未寫入。

## 10/24 owner 授權後的資料恢復與最新終態

以下是同日後續追加，更新上方唯讀重核當時的資料狀態；保留上方原始時間點與限制，不改寫原收據歷史。

### 10/21–22 正式資料發布

- 以官方 market capture manifest 及既有來源 CSV 核對後，TAIEX 10/21、10/22 已精確同步至正式 `market_indices`；產業 TWSE 官方 capture 75 列／日已精確同步至正式 `industry_indices`。產業投影 marker 為 `output/industry_capture/twse/projection_commits/d0/d0d23f25d494432a3d8c201c85a385bbbc565b41d2f3877bb5c5b779e7bfdba5.json`；該日期範圍 CSV／SQLite rowset 完全一致。
- TAIEX manifest `meta_data/official_market_daily_sources/20261023T112100.826551Z-924ff6b6/manifest.json`（10/21）SHA-256 為 `a53eb656bd07358f34c6acd39245fbd5ab91c1f1f059daf846bb99aa48434ae4`；`meta_data/official_market_daily_sources/20261023T112111.232734Z-96198006/manifest.json`（10/22）SHA-256 為 `166ec4a373d9710c2ccf5a83bdbdf7eabccfe1e201ee68383b255a7cdecc1bd3`。產業列數、capture 與 SQLite／CSV exact rowset 在 date-scoped projection marker 內綁定。
- 唯讀前後核對（正式技指 before-image 對 runner 後正式 DB）顯示：10/21–22 `daily_prices` 各 1,965／1,964 列，`market_indices` 各 1 列，`industry_indices` 各 75 列；三表合計 3,929／2／150 列與 before-image 完全相同。市場 CSV SHA 為 `f17ce6344c780c2e1e7c5fe8a46c198f8f2436d325fceca105daf751e00645b1`，產業 CSV SHA 為 `55e3f1fa8aaa7508cb38a0408dc289acd75214b2736d64d5d21560d85016433d`。
- 官方 10/23 仍無當日 TWSE 行情；TPEx 日價因同日 TWSE 無資料而標為 skipped。TWSE 產業來源亦未回可用列。沒有補值、估值或偽造休市證據。

### SQLite 技術指標輸入 OOM 修正

`app_module/technical_indicator_job.py` 的正式 SQLite 增量讀取改為：取最新 `max(incremental_lookback_days, 1) + 60` 個交易日。預設 120 日發布窗口加 60 日暖機，涵蓋目前最長基礎 MA60；近期窗口內缺少個股指標檔的代碼會逐股讀取完整歷史。force-all、單股與明確 `start_date` 保持原全歷史路徑。正式 DB 前置量測為 5,366,575 列／3,124 個交易日；bounded SQL 取 180 日、352,241 列、2,001 個代碼，端點 2026-01-22 至 2026-10-22。

受控 8 GiB／12 程序 Job 執行 `tests/test_r028_technical_indicator_job.py` 的目標契約、候選方法 AST 一致、facade 介面及取消邊界，最終程式版本結果 **4 passed**；兩個修改 Python 檔與測試檔 `py_compile` 通過。此 Job 也實際執行 bounded runner，沒有再出現 5,366,575 列 CSV OOM；尚未完成整支技指計算。最終修改前的一次全檔試跑為 **37 passed／4 failed**：R028 固定來源 hash 因 production method 變更失配，不能改 pin 假裝原 experiment 通過；另一既有 recovery 測試在本機臨時資料庫不存在時被路徑 guard 阻擋。完整 R028 experiment、mypy 與產品端技指讀回尚未通過／未執行。

### 最新正式 quick runner 終態

用受控 Job 執行 bounded quick runner（2026-10-21 至 10/23；broker 與 candidate branch 明確 skip）。狀態為 `failed`，daily-price branches、SQLite sync 通過；市場與產業 10/23 source 失敗以 warning 保留，既有 10/21–22 正式投影未變。技指計算在任何 stock CSV／`technical_indicators` 寫入前，由 `create_raw_alias_writer_context` fail-closed：applied receipt 綁定 `D:\Min\Python\Project\FA_Data`，目前正式根是 `F:\Min\Python\Project\FA_Data`。SQLite／immutable source 與技指表內容沒有因 owner 核准而略過身分比對；技指表仍為 5,362,567 列、最新 10/20，技指發布 receipt `blocked`。正式 CSV 技指目錄仍為 2,209 檔，這輪錯誤發生在逐股寫檔之前。

正式 technical before-image：

- DB：`sqlite/backups/twstock_before_bounded_technical_20261024T180634Z.sqlite`，4,107,538,432 bytes，SHA-256 `f25b947b6bca4f3b0f37f0a08e2793a53991ec7c42718e67486c60f17b8b3da1`，`PRAGMA quick_check=ok`。
- 技指 CSV：`meta_data/backup/technical_indicator_bounded_20261024T180634Z/technical_analysis/`，2,209 個檔案、2,416,353,068 bytes；逐檔 before／copy／source-after SHA 相同。備份清冊在同目錄 `backup_manifest.json`。
- 最新 run log：`output/scheduled/data_update_quick/20261024_technical_window_fix.log`；runner 的 `latest_status.json` 正確保留為 `failed`，不可當日更完成收據。

**當時剩餘阻塞不是 Owner 是否同意，而是搬遷後的 applied raw-alias receipt 沒有受支持的 D→F root relocation/rebind 流程。** 下列追加收尾已提供受驗證的磁碟代號映射，並完成 canonical runner；上方原始失敗紀錄保留為歷史證據。

### 10/24 raw-alias relocation 與 canonical 技指收尾

`data_module/formal_technical_raw_alias_repair.py` 現允許 applied marker 的歷史絕對路徑只在「同一 DATA_ROOT 相對路徑、Windows 磁碟代號不同」時映射至現行根。此路徑仍核對 applied receipt/journal bytes、technical manifest／receipt SHA、`source.sqlite` SHA、size／mtime、目錄歸屬及來源 JSON；原 D-root 收據保持 byte-for-byte 不變。其他根路徑變更仍 fail closed。正式 F-root writer preflight 成功讀到原 immutable source。

`app_module/technical_indicator_job.py` 的 SQLite 自動增量模式不再累積每股完整技術 CSV 歷史，也不再為略過的 aggregate CSV 建立 500 多萬列 `final_df`；它僅保留本輪 SQLite 發布列。其他非 SQLite、非自動增量輸出仍使用原 aggregate 合併路徑，R027 candidate 方法維持 AST parity。

canonical runner 使用 `DATA_ROOT=F:\Min\Python\Project\FA_Data`、`OUTPUT_ROOT=F:\Min\Python\Project\FA_Data\output`，run id `20261024-34764`，終態 `passed_with_warnings`。技術指標步驟 `passed`：2,001 個代碼中 1,993 成功、0 失敗、8 個因資料不足略過，計算範圍 2026-01-22 至 2026-10-22。正式 `technical_indicators` 為 5,366,481 列；10/21 有 1,958 列、10/22 有 1,956 列，最新日 10/22。technical computation evidence 為 `verified`，publication receipt：`output/scheduled/technical_indicator_publication/2026-10-22/89cf6e6bccff8995/receipt.json`，SHA-256 `514a921cf72765ac47078e20f0e24e6239f8a991d5d543c96e836ed89980f9eb`。runner status 位於 `output/scheduled/data_update_quick/latest_status.json`；當次 log 為 `output/scheduled/data_update_quick/20261024_canonical_output_root_recovery.log`。

唯讀 postflight 與正式 before-image 比較確認：技指由 10/20 前推至 10/22；daily price／TAIEX／industry 的既有 10/21–22 列未改，正式市場與產業仍以 10/22 為最新日。10/23 TAIEX／TWSE industry 回應沒有可用列，因此整體 runner 保留 `passed_with_warnings`。技指 receipt 明確標記 `formal_source_contract_eligible=false`、`historical_pit_eligible=false`；本次只解除技指日更／發布卡點，不代表 ML promotion 或歷史 PIT Gate 通過。

恢復 CSV 的第一次失敗嘗試已依原 before-image 還原 2,209 個檔案，逐檔 SHA 全數相符；隨後在 8 GiB／12-process Job 內完成 canonical run，正式 SQLite 寫入與收據已讀回。canonical run 前另建立 before-image：`meta_data/backup/technical_indicator_bounded_20261024T184403Z/backup_manifest.json`；SQLite 4,108,730,368 bytes、SHA-256 `f270e29899b2faaeeb38ad138526813b154f8a681615fd65859b5de82d0768b6`、`quick_check=ok`；技指 CSV 2,209 檔逐檔 SHA 完整。

受控 Job 最後 focused regression 為 **17 passed**，涵蓋 relocation guard、bounded SQLite query、略過全歷史 aggregate、candidate AST parity、cancel/facade contracts 及既有 fail-closed writer 測試；受影響 Python 檔 `py_compile` 通過。較廣 R028 固定 source-hash experiment 尚未通過，未改動其 pin；document_control 全檢仍受既有 repo 外 `output` junction confinement/WinError 5 限制。

## 10/25 官方公開頁唯讀交叉核對

2026-10-25 03:23（Asia/Taipei）重新查閱官方公開頁：TWSE 2026/10 FMTQIK 月報目前最後一筆為 10/22；TWSE 個股 2330 的 2026/10 月日成交報表亦列至 10/22。TWSE 2026 市場開休市表列 10/26 為 10/25 週日的補假，沒有列 10/23 為休市日；TPEx 10/22 公告一項處置期間自 10/23 起算五個營業日，並註明遇休市等情況順延。依官方日曆與公告，10/23 應維持交易日判讀；這是交叉來源支持的判讀，不是 10/23 成交列證據。

公開頁面：TWSE [2026/10 大盤每日交易報表](https://www.twse.com.tw/en/exchangeReport/FMTQIK?date=&response=html)、[市場開休市日期](https://wwwc.twse.com.tw/zh/trading/holiday.html)、[2330 2026/10 個股日成交資訊](https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=20261001&stockNo=2330&response=json)；TPEx [8358 處置公告](https://www.tpex.org.tw/www/zh-tw/bulletin/disposal?code=8358&endDate=2026%2F10%2F29&id=&order=date&response=html&startDate=2026%2F07%2F01&type=code)。目前可讀到的 TWSE 報表沒有 10/23 列，且 TWSE／TPEx 10/23 行情缺失仍無可驗證解釋；因此資料尾日維持已證實的 10/22，沒有改成休市、沒有補值，也沒有寫入正式資料。

## 2026-10-26 TWSE 10/23 單股來源重核

本次只查 TWSE 2026-10-23 的 2330，不把單股結果外推成全市場。既有 `scripts/capture_twse_historical_daily.py` 對官方 MI_INDEX `type=ALL` 執行一次唯讀候選擷取；回應 body 的 `stat` 為「很抱歉，沒有符合條件的資料!」，因此工具在建立完整 receipt／comparison 前停止。原始 gzip response（87 bytes）留在隔離 scratch，SHA-256 `f1c24c086621954aff00ef11810356d3ae9864892cba694d267499356ff867ad`。capture Job exit 1 是官方回應無資料，不是成功 capture；Job active process 0、handle／lock 已關閉、source pins 前後相同，無正式資料寫入。

同日另唯讀查看 TWSE 官方 2330 2026-10 月個股成交頁：`stat=OK`、15 列，最後日期 10/22，沒有 10/23 列（[官方 STOCK_DAY 回應](https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=20261001&stockNo=2330&response=json)）。Formal SQLite `mode=ro`／`PRAGMA query_only=ON` 精確查 `daily_prices` 的 2330／20261023，結果 0 列；`daily_price/20261023.csv` 不存在。唯讀回讀 Job exit 0、Job active process 0、source pins 前後相同。

隔離執行收據位於 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\`：MI_INDEX probe `receipt.json` SHA-256 `f83450739919b7535156e51e57ac675c3eb775eb9a6f37c3376c7759d57fa2f7`、`stdout.log` SHA-256 `8dfe4227242b9a5ee4bba2af9225b4103c732d61c522a4b2e9f09903de754e25`；formal readback `receipt.json` SHA-256 `78bf5bedada4c09e0c58e82138854fa596986b5a5c48551648958a7759c8cde41`、`stdout.log` SHA-256 `3caef3def6815c47d4326f65ce756d326c6d10ab4608767559cc9bd4ac84be3`。這只確認 2330 在已查端點與正式資料中的 10/23 缺列，尚未找到可驗證的缺源原因，也未證明任何替代來源可補成正式資料。


### 2026-10-26 TWSE endpoint 最新重試

候選擷取器補強後，使用隔離的合成空 SQLite／CSV source，再對 TWSE MI_INDEX 以 8 秒 timeout 重查 2330／2026-10-23；本機 DNS 在取得 HTTP response 前回 `NameResolutionError`（`www.twse.com.tw`），程序 exit 1。這是傳輸失敗，不是官方無資料回應；本次沒有 response、receipt 或 comparison，因此先前已捕獲的官方無資料 response 仍是最後一份來源 body 證據。檢查 scratch candidate root 為 0 個 `.capture-*` 暫存目錄、0 receipt、0 comparison；Formal DB／CSV 未讀寫。


### 無資料診斷保存與安全驗證

候選擷取器現在會將已辨識的 TWSE「沒有符合條件的資料」回應保存為 `official_no_data_response` receipt／comparison，保留原始 response hash，並明示零官方列、零修正候選、無來源對照，以及正式訓練／promotion 禁止。CLI 用 exit code 3 表示此可稽核無資料結果。無資料 capture ID 會在舊 response ID 後綁定 12 碼代號範圍 hash，避免同日同回應的不同代號查詢互撞；一般有資料收據沿用舊 ID 格式，維持歷史固定路徑相容。下載或解析失敗也會清除本次暫存 body，若工作程序啟動時已存在同名暫存目錄則 fail closed。這不回補 2330／10/23 行情，也不把富邦或其他來源升格為正式來源。

驗證過程中，第一次加入代號 scope hash 時，冒號前綴造成 Windows 路徑無效；第二次雖移除冒號，長測試目錄下仍觸發路徑長度錯誤。改用固定長度純十六進位 scope suffix，並保留一般收據舊 ID。另有一次相容性 assertion 初放在無資料測試、造成 **1 failed／8 passed**；移至正常行情收據測試後，同一聚焦組最終 **10 passed**，四個修改 Python 檔 `py_compile` 通過；另新增 CLI 測試核對 `official_no_data_response` 輸出與 exit code 3。負例確認 no-data comparison 不能被 ML overlay 當成行情列來源。未對正式 DB／CSV 寫入；TWSE source／PIT／Gate／ML 資格不變。
