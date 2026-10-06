# UX08 原生圖同源契約限定驗證（2026-10-05）

## 2026-10-06 歷史 MA20／MA60 限定切片（最新）

基線d9a4a086。read service追加有界唯讀technical_indicators歷史入口，只讀價格日期與cutoff交集、最多120列，沿既有「證券代號／stock_code／Code」欄位別名。report尾端追加frozen歷史DTO，保留位置參數相容；舊儲存schema／bookmark與feature artifact沒有改寫。只投影已存MA20／MA60，不重算指標、策略或暖機。

每列指紋綁stock／source／date／MA20／MA60／available_at。來源與列的已知未來資料日／可得時間排除；錯股／來源／hash／重複日期或無效值拒絕。缺來源時鐘、缺值／暖機資格維持unknown，PIT=false。來源pin依前包契約核對；保存／daily／rank來源未具備同版本技術artifact歷史契約，禁止live補查並明示缺件，saved歷史讀回仍pending。明示current_stock_research與空context的一般研究才讀既存SQLite歷史。

同一technical_lines驅動原生圖MA20金色／MA60藍色覆蓋線、精確表與hover／table來源及列hash提示。按價格日期對齊，缺列、None或缺收盤日斷線；不插值或補末值。沒有合法序列就不畫線，單日snapshot獨立顯示。覆蓋線更新保持價格日期、模式、widget幾何與hover；尚無可縮放／平移viewport。初始化／填值故障仍保留價格及技術表，paint／GPU故障另待。

Root有限整合116個不同案例通過（pure15＋新歷史11＋service40＋原UI44＋新UI6）。隔離SQLite實際read_report→來源核對→投影→原生圖／表通過，核對高精度值、缺列斷線及截止後999值排除，不是正式DB驗收。Workbench85、validator25通過／4略過／0失敗、mypy795、6檔compile及quant guard通過。review修正欄位別名、例外空tuple初始化與來源時鐘gate；mypy日期變數改名後pure26再次通過（重疊，不增加116）。無全套回歸、producer／ML、個人資料讀取／遷移、vendor安裝、Native或push。

Raw承接output/qa/ux08_native_technical_history_20261005/，驗證跨至2026-10-06 UTC；原計畫append-only。current-observed MA20／60工程切片done；saved技術artifact歷史、其他指標／尺度、交易markers、期間／縮放／平移、圖商原型選型、Native／真人pending，UX08整項／stage4仍partial。Widget獨立lane結論同步[UX07收據](UX07_CHART_FEASIBILITY_20261005.md)，不引入依賴。Personal path/control_paths另lane工作，未在此commit混入或啟用。

以下保留前包與當時pending邊界，最新限定結果以本節為準。

基線 `631d6ad189e490dc75e964ee4abafc69df7ce114`。沿唯一原計畫 UX08／§7.5，本批只做不需圖商選型的 application 投影與既有原生圖接線。Sol 整合、兩位 LunaMax 分別負責 payload 與 consumer；沒有安裝／下載、接受條款、外站資料傳送、正式資料內容讀取／套用、producer／ML、前景 Native、清理或 push。

## 同源契約與數值邊界

入口 `app_module/stock_research_chart_payload.py` 的 `project_stock_chart_payload` 只接既有 frozen report／明示 cutoff／預期身份。圖與數值表使用相同核對後 price points，保留原 Decimal／整數；不新增 SQL、價格查詢、指標計算或策略公式。Qt consumer 不另算 hash 或取得最新行情。保存或研究來源切換保留原截止日及 source context，缺件不借另一份最新來源補齊。明示當下獨立研究仍沿既有 service 查詢日，切回保存決策恢復原 cutoff；pinned 日快照不走當下分支。

保存／研究快照的 context pin 與價格行指紋分域：前者核對原 envelope 欄位，後者重用 `stock_price_row_fingerprint_sha256` 核對股號、日期、OHLC、成交量與成交金額。行指紋不是全部 report 欄位的 hash，也不冒充原決策 artifact hash。已知身份失配拒絕；舊 DTO 缺行指紋保留 unknown。截止後資料及明示截止後才可得的資料排除；缺 available_at 不補查詢時鐘、不授予歷史 PIT。

價格表與 hover 使用原精度，避免原共用兩位小數 formatter 的四捨五入；缺值與真零分開。缺 OHLC 沿原收盤線、缺成交量不補零柱。單日 technical snapshot 只作有日期的快照表，不延伸歷史指標線；目前 event DTO 缺自身股號／hash，不轉已驗證交易 marker。

## 原生 consumer 與 fallback

`ui_qt/views/stock_research_report_view.py` 維持 QPainter 原生 widget 為 default，不依 WebEngine 或網路。lazy 價格頁使用同一投影建立 OHLC／量表及圖；來源、實際資料日、cutoff 與 unknown 限制可讀，完整 hash 留技術提示。錯股 service DTO 在結果載入前拒收；既有 request id／切股取消／來源切換失效邊界沿用。

圖表建構或 set_points 失敗時，已核對表格仍可讀。此限定 failure 測試不代表所有 paint／GPU／程序故障已驗證，也沒有取得前景 Native／真人或打包部署資格。

## 驗證

限定驗證完成：payload 15 項由 root 實跑通過；consumer 完整檔案 44 項由專屬 LunaMax offscreen 實跑通過，共 59 個不同案例。涵蓋錯股／日期／來源 pin／行 hash 拒絕、未來與晚到資料排除、Decimal 精度、缺件 unknown、A→B→A 截止日保存，以及圖表建構／填值失敗仍保留表格。root review 補正無日期 technical snapshot 的 unknown 行為，並加入對應案例；已知晚到的無日期 metric 仍排除。

必要整合檢查：Workbench 85 passed；更新頁 validator 25 passed／4 skipped／0 failed；mypy 795 files success；4 個變更 Python 檔 py_compile 通過；quant guard 前後通過，新投影 AST 沒有 float 呼叫或 float literal。沒有重跑全套、F1 效能、COW、producer／ML 或前景 Native。Qt paintEvent／GPU 故障、真人互動與部署驗收仍未涵蓋。

Raw：`output/qa/ux08_native_chart_contract_20261005/`；留本機，不提交原始輸出。原計畫完整 bytes 前綴保留，只追加本批 done／partial 範圍。

## 原計畫逐項狀態

| 項目 | 本批範圍 | 狀態 |
|---|---|---|
| 同源圖表 DTO／來源與 cutoff | 純投影、已知身份拒絕、未來資料排除、unknown 保留 | done（限定工程） |
| 精確數值表／原生 fallback | 同 points、原精度、初始化／填值失敗仍可讀 | done（限定工程） |
| 歷史技術線／圖上事件交易 markers | report 只有單日技術快照、event 無完整身份，不補造 | pending |
| 縮放／平移／互動期間及 UI 資源對照量測 | 本批不擴展 renderer | pending |
| 本地 LWC library／選型／外部圖商 | 沒有本地 bundle；不下載、不接受 terms | pending |
| UX08 整項／stage4 | 只有安全可獨立切片；不是完整互動圖整合 | partial |

UX07 已接受的是官方與 repo 調查；三方案原型、選型與 UX08 全項未完成。原整份計畫完成數不由此自動增加，其他已接受 COW 工程不重開。

F1：父層轉達使用者於 23:32 UTC 明確回覆「可以同意」，接受 Backtest 初始化效能例外結案。實測18.621965821542936%（約18.62197%），距20%目標差15.1294400013285 ms（約15.12944 ms）；目標未達保留，不改標 benchmark pass，不再微調／重測。此批准只涵蓋效能例外，不授權正式 JSON 遷移／啟用或前景 Native。

## 正式 JSON 套用仍獨立待批准

**下列 D 槽路徑是既有工程值，已被本批最新資料分離要求列為正式套用 blocker；不是新的部署建議。** 獨立 DB 仍在 `FA_Data/output/watchlist`，可能隨整包市場資料帶走，尚未符合使用者「抓取資料包可分享、個人資料必須分開」要求。

source：`D:\Min\Python\Project\FA_Data\output\watchlist\default.json`；CLI 新 DB 候選：同資料夾 `watchlists.v3-cow.sqlite`；UI 明示升級建立 `watchlists.v3-cow-default-<唯一ID>.sqlite`。marker：`default.json.cow-active.json`；receipt：`<新DB>.cow-conversion.v1.json`。沿 `data_module/config.py` 的 `TWStockConfig`／`DATA_ROOT`／`OUTPUT_ROOT`，一般啟動 `ui_qt/main.py` 用 `TWStockConfig()`，不修改設定或 `.env`；canonical `watchlists.db` 不初始化。

enable 建新 DB／receipt 後寫 marker 指向新 DB，來源 JSON 保留；後續寫入在 target。rollback 核對原 source pin／receipt／baseline 後切 marker 回 JSON，保留 target 新 revision、雙來源與 audit，不合併、不刪檔。`default.json.cow-rollback.<activation_id>.json` 是模式／指標 metadata 審計，不是額外內容備份。正式 apply 尚未讀內容 dry-run；需另確認實際 output_root、單一來源、writer 時段、當下容量與 D 寫入權限。

既有 [COW QA](F4_LEGACY_JSON_COW_AND_ACTIVATION_20261005.md)、[UX07 官方調查](UX07_CHART_FEASIBILITY_20261005.md) 與 [Manual](../07_guides/APPLICATION_MANUAL.md) 維持各自權威。

## 最新個人 root 設計與交接（未套用）

| 項目 | 首選候選完整值 |
|---|---|
| 個人 root | `C:\Users\archi\AppData\Local\baldr\personal`（每位使用者依 LOCALAPPDATA 解析） |
| 專用觀察清單 DB | `C:\Users\archi\AppData\Local\baldr\personal\watchlists\watchlists.v3.sqlite` |
| 個人設定候選 | `C:\Users\archi\AppData\Local\baldr\personal\personal_storage.json` |
| activation pointer 候選 | `C:\Users\archi\AppData\Local\baldr\personal\watchlists\activation.v1.json` |
| conversion receipt 候選 | `C:\Users\archi\AppData\Local\baldr\personal\watchlists\watchlists.v3.sqlite.cow-conversion.v1.json` |
| rollback audit 候選 | `C:\Users\archi\AppData\Local\baldr\personal\watchlists\audit\rollback.<activation_id>.json` |
| 原 JSON 內容備份候選 | `C:\Users\archi\AppData\Local\baldr\personal\watchlists\backups\default.legacy-v1.<source_sha256>.json` |
| 若選 D 槽的替代 DB | `D:\Min\Python\Project\baldr_PersonalData\watchlists\watchlists.v3.sqlite` |

上述名稱／位置是待確認設計，不是已支援的新設定檔／marker schema，不可拿候選路徑直接執行現有 activate。既有 code：`data_module/config.py:22-26,121-124` 將 market DB 放 `{DATA_ROOT}/sqlite/twstock.db`、output 預設市場 root/output；`app_module/watchlist_service.py:257,293` 綁 OUTPUT_ROOT/watchlist；`app_module/watchlist_cow_activation.py:34-38` 把 marker 放來源旁。只把 destination 換 C 槽仍會留下 D 槽個人 pointer，fresh-process discovery 也尚未改，因此本批沒有安全正式 apply 命令可交付。

`app_module/portfolio_service.py:76` 與 `portfolio_store.py:211-219` 的目前 JSONL 位於 OUTPUT_ROOT/portfolio 的 `trades.jsonl`／`journal_entries.jsonl`；Main 未自動注入新的精確 SQLite ledger。此為 code 路徑盤點，沒有讀真實內容或移動其他 owner 資料。

後續工程：新增獨立 personal root 配置，不改市場 DATA_ROOT／OUTPUT_ROOT；解析 canonical／reparse alias 後拒絕與市場 root、repo 原始碼／發布包重疊；receipt／pointer／audit／備份與 recovery 都在 personal root，獨立記錄 source pin／target revisions。啟用前核對來源仍一致、候選 DB 不存在、writer 時段、容量及真正寫入權限；rollback 切回既有 writer，保留雙來源／新內容與審計，不合併或刪除。原 JSON 在市場包時須持續明示排除；搬出／移除另由來源 owner 批准，未獲批准不做。

市場包採明示市場來源 allowlist，不整包 recursive copy；排除 personal root、legacy output/watchlist、output/portfolio、個人 Journal／筆記、設定／marker、receipt／audit／備份和個人 DB 的 WAL／SHM／journal。新增匯出測試應放合成私人哨兵／巢狀 alias，證明市場包與 manifest 不含個人路徑／內容；不能只排除主 DB 而漏 sidecar。本批沒有實作或執行匯出、分享／上傳，也未查真實 market DB 內容，不能聲稱現在資料包已無個人內容。
