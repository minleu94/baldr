# 資料、保存與 Runtime

本冊描述來源取得、儲存、研究快照與排程觀測的 current 邊界。一般操作看 [Application Manual](../../07_guides/APPLICATION_MANUAL.md) 及對應現行 Runbook；目前狀態與資料資格看 [Snapshot](../../00_core/PROJECT_SNAPSHOT.md) 與具名 QA 收據。舊 [Application Manual Supplements](../../07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md) 僅供歷史錨點追溯，不是現行操作或授權依據。

## 資料路徑與來源

官方注意公告沿 `selection_official_attention.py` 的有界單日 TWSE 報表解析；保留完整原列 SHA、官方原因 HTML 原文與純文字投影、收盤價／本益比原字串，不將注意當處置或轉成金融輸入。`official_attention_snapshot.py` 另存 self-contained 原 body、HTTP／worker 原收據、headers／request／cookie 側錄與三份固定官方查詢文件。外部 HTTP 收據 SHA、原件各 SHA、完整 EOF／正常 worker 回收、單日全證券查詢、宣告筆數及 schema 均重驗。原 HTTP receipt 未含 worker-result SHA；新 manifest 明示現在才綁已保存 bytes，不追補舊收據。

注意版本使用獨立 `twse-attention-daily-manifest.v1`／`twse-attention-daily-receipt.v1`，不冒用 MOPS 或法人 schema。create-only／fsync／pending／批次實際時鐘沿既有每日政策，只有公告日故保留官方發布時刻 None，以成功批次小時 fallback。fixed reader 要明選目錄與雙 SHA，逐次重驗整鏈與 bytes／signature，拒 pending／failure、未來 cutoff、提前小時與中途變更；原 capture 不需仍在場，不掃 latest、不讀正式 SQL。改正另存；失敗只隔離該功能。操作與設定見[注意公告指南](../../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#單日官方注意公告後續開發分支)，資格仍候選／用途未接受／PIT false。

`data_module/config.py` 的 `TWStockConfig` 是資料路徑權威。`DATA_ROOT` 預設為 `D:/Min/Python/Project/FA_Data`，可用環境變數覆蓋；`OUTPUT_ROOT` 亦由同一設定管理。主要市場 SQLite 位於 `<DATA_ROOT>/sqlite/twstock.db`。程式不得另造正式資料根目錄或硬編路徑。

每日市場更新的主要資料流是：

```text
TWSE／TPEX 明示來源
  → DATA_ROOT 下的來源日檔／raw evidence
  → SQLite sync 更新 daily_prices 等正式讀取表
  → 技術指標 job 及 application read models
```

SQLite-first 是一般讀取優先序；CSV 保留原始來源、完整備份、明確 fallback／migration 與研究匯出用途。沒有行情或 provider 不可用時，讀取路徑回傳 missing／diagnostics，不把空結果當成零值，也不因讀取而建立空資料庫或 schema。

單股回測的 `BacktestService` 讀取 `daily_prices` 與 `technical_indicators` 時，沿 `TWStockConfig.db_file` 使用共用 `ReadOnlySQLiteManager` 的 `mode=ro`／`query_only` 短連線；讀不到指定表或列時才沿原 CSV fallback。這條讀取路徑不呼叫會初始化 schema／切換 journal mode 的 `DBManager`。研究結果另寫入隔離的 Registry／輸出根，不能因此改動市場來源 DB；實際真價副本與來源 hash 核對見[Increment106 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment106-backtest-source-readonly-real-pair)。

新來源需保留來源識別、版本、`as_of_date`、`available_date`、quality、missing policy、授權與下游資格。正式決策只消費決策當下可取得且通過來源 gate 的資料；來源候選依 Diagnostics → Shadow → Evidence Review → Accepted Feature 逐步判定。Raw data 不因補算、格式整理或 UI 操作被覆寫。

決策日、資料觀測日、來源可得時間、writer 可得時間、保存時間與預期官方交易日是不同時鐘。`available_at` 由來源或特定 writer contract 定義，後者通常在 artifact／receipt 發布並讀回後才簽發；`persisted_at` 只是保存／排序事實，不能代替官方來源 availability、writer availability 或 PIT 證明。跨日 freshness 應由共用的 market-session cadence／已驗證日曆依同次 operation 明示的 aware cutoff 判斷；歷史 clock 不賦予 current freshness。實際行情日要隨 DTO、snapshot 與 evidence lineage 保存。日曆缺失、未發布、hash 不符或來源日期晚於 cutoff 時保留 unknown／degraded，不借鄰近資料、日曆常識或另一個 provider 補出來源資格。來源 custody／corporate-action 診斷須綁 raw bytes、日期、availability 與行情欄位；方向未知就 fail closed。各 API 欄位語意仍以其 owner contract 為準，不得互換時鐘。

## 讀寫與保存契約

### 具名營益目前研究版本

`twse_operating_summary_snapshot.py`只接受資料集20762的固定CSV、2330及2026-H1。貨幣／期間由同發行人官方半年報與營收、四項比率在顯示精度內交叉核對；不外推1055列或未來版本。原CSV、HTTP收據及三份用途文件另存，沿既有immutable I/O與`DailySourceUseAcceptance`，不轉入正式SQLite。雙外部SHA、完整原件、一次性用途及每批實際保存時鐘獨立重驗，pending／failure／重寫拒絕。官方只有出表日，依成功批次台北小時使用，不借HTTP Date或過去財報期末倒填可得性。

`OperatingSummaryReportProvider`只投影至目前個股報告；幣值以Decimal乘百萬、百分比保留原值。前期、歷史PIT、聚合篩選、策略、ML、Paper與交易資格均未授；PDF不隨產品快照複製或重展示。配置與失敗隔離見[操作手冊](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#具名營益固定版本研究)。此葉不改月營收、generic daily record或其他已接受來源。

`institutional_source_use.py`把既有DailySourceUseAcceptance限定於資料集11856／精確TPEx OpenAPI、parser版本、官方operation＋resolved schema SHA、shares與diagnostics。四份Root已核官方文件按固定版本fingerprint另存，來源不變，接受檔canonical與外部SHA；pending／failure／reparse／hardlink／中途變更拒絕。真accepted_at不得早於必要metadata原件收據或本次真保存開始；讀者cutoff不得早於接受時間。原institutional_daily_snapshot另驗每天原件、合計、版本與成功批次小時，只有明選同源用途pin才附typed source_use／source_use_accepted=True，candidate_only／歷史PIT false不變。沒有SQL、generic P0 decision或Task寫入；原MOPS／日曆及TWSE無法跨用。正常頁面只新增可選接受檔／SHA輸入、接受ID／時間／顯名，無pin時舊行為相容。

法人候選沿 `institutional_credit_flows_service`／`complete_institutional_credit_flows.py` 的原 parser、create-only raw／metadata／candidate 保存。`capture_scope=twse_institutional` 僅選 T86；`legacy_all` 保留原四來源，未要求資料集不造零，scoped rebuild 核來源／單位／版本及逐日分區。`app_module/institutional_daily_snapshot.py` 對明選原run重驗完整EOF／identity body、全部原件與candidate，旁存create-only manifest／成功時鐘receipt及pending barrier；exact public reader要求目錄與雙外部SHA、同批全部byte／signature再核驗及可用小時。它沿原時間政策，沒有把MOPS record或另一revision namespace強cast成法人。

正常 UpdateView 的法人區經 TaskWorker → UpdateService → 此exact reader，只讀指定代碼原整數股數；Qt widget不做I/O或金融計算，取消／輸入世代與shutdown沿原worker生命週期。報表列數不是股票universe或真N，candidate-only／用途未接受／PIT false保留，無日曆／連買新公式；正式apply／schema與Task未改。Increment53新增明選TPEx OpenAPI最新單日scope與獨立20欄parser，拒T86 discovery／其他市場回退，沿同一capture／rebuild與generic daily seal/read。舊TWSE ports仍只接T86；原manifest明選市場傳至Read DTO與正常頁，不以metadata shares常數或TPEx日曆替用途接受。詳[TPEx單日操作](../../07_guides/manuals/DATA_AND_MARKET_RESEARCH.md#tpex法人openapi單日版本後續開發分支)與[法人批次契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#tpex法人openapi明確單日increment53)。

原T86 parser另交叉核官方自營商／三大法人宣告合計與原分類，body單位若存在須為股；每日seal／exact reader還要求明示raw單位、唯一欄名與兩個宣告合計欄，不由metadata常數推定。legacy缺欄候選解析相容不授每日讀取資格，舊artifact不改寫；真單日原件與批次時鐘仍沿上述同一鏈。

Increment45以真當下時鐘跨過原批次04:00邊界後，正常Main5752→fresh43792沿同pin核四代碼原整數與7來源檔不變；禁止producer／seal／apply／HTTP，沒有重抓或注入未來cutoff。這是原資料流的真來源限定證據，不新增契約／來源接受，詳[QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment45p03真t86正常畫面與新程序)。

日曆JSON原件以獨立typed transport保存HTTP／EOF／hash，daily batch沿原兩市場parser發行create-only capture／manifest／receipt。Exact reader要求外部manifest及receipt SHA、各市場獨立用途接受錨點，讀前後拒pending／failure並重驗原件；更正另存，93 inclusive日限制與candidate資格保留。Registry原頁已接明示daily pin，合成Main／fresh重用已保存來源限定通過；獨立接受紀錄未配置時阻擋，不掃latest或從capture自授信任。真用途接受、正式Main配置與publisher／Task仍待，詳[日曆版本契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#日曆完整json批次increment21)。

TPEx年度開休市頁的JSON內嵌HTML由`data_module/tpex_trading_date_html_v1.py`先核原bytes／外部SHA、baseline、兩表結構及rowspan，原`official_calendar_bundle`再處理股票開休市；三類債券保留為非股票列，不能關閉股票日期。這個候選來源與舊monthly boolean是不同schema，目前尚未接daily wire／用途錨點，不因年度基準日期或完整取得授PIT。詳[年度解析契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#tpex年度股票日曆候選解析)。

P00／P03 新保存來源採[每日快照小時契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md)：對應版本官方時間與成功批次完成時間各向上取整到台北小時，再取較晚者；缺官方小時採具名批次依據。批次包含成功保存與品質驗證，reader 釘同一批次與版本，decision cutoff 不向上取整。此規則只建立首次成功保存後的前瞻可用性，不把 `persisted_at` 改寫為官方發布時間、歷史 PIT 或 Paper writer availability。來源／用途一次接受與每日批次自動驗證分開，舊 FAIL 及未驗範圍保留。

MOPS saved-capture producer 已沿 `UpdateService` 的明確 root／scope／accepted anchor／batch port 接上 preparation、Decimal正規化、immutable writer及新reader。Quarantine v2分存HTTP/canonical原件與hash；成功public reader拒pending publication barrier，发布後clock／隔離搬移失敗仍不授成功。Scalar pin仍不足以代表雙市場cohort，正常UI／session及真來源接受尚待；晚本機materialization的可用時間不早於原觀測。

雙市場cohort有hash-bound pin及create-only封套／外部expected hash reader，固定root／acceptance副本並重驗所有必要市場；common hour取較晚者。外部binding v1由既有accepted anchors與精確pin/readers序列化，application settings成對提供path／原件SHA；64KiB有界loader拒別名／包內root／缺市場／錯版本，經正常Main composition注入同一preparer/provider。合成Main／新PID及18來源檔案不變已有限定QA；更新批次組自動發行、正式配置與真來源接受仍待。舊Selection source clock v1的unknown／current-only契約不重標為verified，正式資料與Task不擴權。

TWSE 月營收 JSON preparation 是獨立 source／parser／schema，保留官方原件與單股／期別 target；date-only 可計具名批次小時，單位缺官方強錨時只出 shadow／diagnostics 原值、不借 MOPS 千元轉換或接受資格。既有完整原件可唯讀重用驗 parser，但原候選收據／時間政策不能覆寫；跨程序一致與新線上取得完整度各自判定。

| 資料類型 | 讀取／寫入責任 | 身份與安全邊界 |
|---|---|---|
| 市場資料 SQLite | `data_module/` reader／provider 與受控更新服務 | 唯讀查詢採 SQLite `mode=ro`、`query_only`；正式 writer 走明示更新／migration path |
| Raw CSV 與來源 evidence | source adapter、受控 producer | 保留原件；補寫需明確目標、預覽、備份及授權流程 |
| Watchlist、bookmark、個人狀態 | 對應的 Watchlist／bookmark service 與 store selector | 與市場資料庫、研究快照、producer 輸出分開；讀取不隱式建立、遷移或啟用新 store |
| Research／market snapshot | 專用 publisher、manifest 與 exact reader | 以版本、source pins、scope 與 bytes/hash 綁定；重開指定身份，不搜尋 latest 或重算舊結果 |
| Paper daily account／ledger | `strategy_paper_account_daily.py`、`paper_trade_ledger.py` 與 availability reader | 只走 `PAPER` domain + `PERSONAL` mode，並綁 `acct-<sha256>` account namespace、strategy/version、operation／portfolio identity、aware decision／mark cutoff、selected READY binding／route 與 exact schema identity（`strategy-paper-account-daily-operation.v1`、`strategy-paper-account-daily-receipt.v1`、`paper-trade-ledger.v1`、`paper-trade-transition.v1`、`paper-trade-daily-operation.v1`、`paper-trade-ledger-rowset.v1`）；exact `mode=ro`＋`query_only`＋read transaction 核 schema、marker/hash chain、bounded prefix／fills／transitions；writer 狀態依 `PENDING → LEDGER_COMMITTED → FINALIZED` 前進，reader 只接受 FINALIZED 且 receipt／identity／hash 全部相符。相同 operation 的 idempotent retry 必須核對既有 payload／hash；state 與 ledger 是不同 DB transaction，沒有跨 DB 原子性；partial commit 不可當可用完成結果。 |
| Portfolio research scenario store | scenario repository 與 versioned artifact decoder | 僅 `PORTFOLIO_RESEARCH` route；`portfolio-research-scenarios.v3` payload 與 `portfolio-research-store.v1` SQL schema 分開核對，綁 account kind／portfolio／snapshot／artifact hash；missing store 的 read 不建 DB／schema、不 fallback，明示 append 才可建立保存結構 |
| Evidence／Runtime state | 各自 repository、producer 與唯讀 projection | namespace、權限、write mode 與 evidence tier 分開，reader 不呼叫 writer |

市場 DB、私人資料、Runtime 與 ML registry 是分開的儲存邊界。Runtime application state 位於 `<OUTPUT_ROOT>/application_state`；ML registry 預設位於 `%LOCALAPPDATA%/baldr/research_state`。私人 store root、mode 與 account identity 由 caller 明示；設定不完整、身份不一致或來源不可用時拒絕 fallback，不由讀取建立目錄或 schema。

Watchlist、bookmark 與個人 journal 依成對的明示 root／mode 選擇私人路由：兩者都未設定才沿用 `LEGACY_COMPAT`；只缺一項即拒絕。`PERSONAL` 的 read source 與 write target 是同一 store；`LEGACY_READ_ONLY` 沒有 writer target。缺失的 PERSONAL store 視為空，不得 fallback 到 legacy。啟動時不複製資料、不做 migration 或 activation；隔離 converter 先 preview、備份與驗證，再由使用者明確選擇切換或回滾。Watchlist COW 以來源唯讀、marker／lock／receipt 與 source bytes/hash/schema/capacity 核驗保護切換，revision 以 CAS `expected_revision` 防止覆蓋並行更新；任何身份、hash、schema 或容量不明都 fail closed。回滾需停止 target writer 並保留 target 新歷史；不得以來源舊副本覆寫新歷史。Portfolio ledger、Paper、Evidence、Notes 與市場資料各自保留 caller／身份邊界，不因 watchlist route 一併重導。

Saved snapshot、benchmark、圖表與研究成果須在原保存 bytes 上驗證來源、scope 與 identity。條件不符即拒絕或降級；不能退回 live data、借用最新來源或補回未知 PIT。

## 市場資料、研究母體與報告

原 F17 `CurrentOfficialDisposalReader` 新 pin／parser v3 可直接解析既存 TWSE `/announcement/punish` 十欄英文 array，identity 綁內部 row contract 與官方 Swagger SHA；v2 原 wire／identity／讀法不變，舊保存來源不遷移。原 raw／原列 SHA、公告與生效期間、觀測日及 current_only／PIT false 保留，空列仍 unknown。`CurrentMarketAssignmentReader` 以 parser 原 `listing_termination` 型別核公文的正向終止日期，停止交易不作終止；snapshot 與 raw 不合仍拒絕，無缺列推論。版本與守衛見[資料契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#已存官方處置來源的版本相容increment46)，限定真原件／正常 Main 與未驗邊界見[Increment46 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment46p03真twse處置與終止公文讀回)。

市場資料表包括 `daily_prices`、`market_indices`、`industry_indices`、`technical_indicators` 與 `broker_flows`。Fundamental tables 透過受治理 provider／Factor service 讀取；UI 與策略核心不直接讀 raw fundamental CSV。表的現存數量與日期覆蓋屬動態資料狀態，需另讀當期 QA，不在架構文件保存計數。

Broker Flow 的買賣榜資料各自保存；缺欄位保留 NULL／品質標記，不以零值補缺。更新前先核對交易日證據；來源 HTTP path 失敗時才使用既有 fallback，更新仍按既有序列流程。

跨頁研究母體、圖表與 saved query 依固定來源身份共享同一結果投影。完整母體 strict reader 需先核 manifest／receipt pins；單一來源 segment 最多 256 檔是保存分段限制，不是 universe 上限；全域篩選與排序完成後才分頁。bookmark 重開指定來源、query 與選取狀態，不能回退一般最新資料讀取。

匯出服務消費 UI 傳入的結果 snapshot，不重跑策略或重新計算績效；寫檔使用暫存檔後原子替換，缺失的 lineage 欄位顯示 unknown。SQLite Inspector 以穩定排序鍵加唯一 `rowid` 作分頁 tie-breaker；唯讀查詢不建立資料庫，新的篩選或查詢先重設頁碼，過期 worker result 依 request identity 丟棄。

Research Run Registry 的 metadata SQLite 與 Parquet artifact 位於 `OUTPUT_ROOT`，與 `DATA_ROOT` 市場 DB 分離。保存依 staging／files-ready／committed 狀態發布；清單只顯示 committed、valid run，load 時重驗 artifact hashes。Registry/history reader 需 caller 明示序列化讀取預算；已接受的 R01 profile 為每個 artifact 最多 64 MiB、每次呼叫合計最多 256 MiB。這是輸入 bytes 上限，不是解碼後 RAM 上限或所有 caller 的預設值。舊版本的 execution assumptions 讀取其保存 metadata，不依當前 UI 重建或跨版本升級。

Forward rule observation 的 regular-file/no-follow reader 另有明確窄預算：單次 capture 至多 2 MiB、256 captures、保留 bytes 合計至多 64 MiB。這些上限只約束該 observation reader，不是全域檔案／artifact 預算；超限或來源檔型態不符即拒絕，不以無界讀取補救。

Evidence Event／Outcome append-only 保存決策來源與後續觀測。Forward outcome 的 close-to-close return 是事後診斷，固定 `is_execution_pnl=false`，不能替代 next-open 執行績效，也不因成熟而自動升 evidence tier。查詢只投影已保存的 event／outcome；缺來源或 benchmark 保留 NULL／warning，不補回舊事件資料。

## Runtime 與排程

決策擷取狀態由 `app_module/decision_capture_status_reader.py` 共用唯讀 adapter 核驗既有 producer 的 wire；ScheduledOperationsStatusService 與 WorkbenchSourceService 消費同一型別結果，RuntimeView 只呈現 DTO。`latest_status.json` 必須綁相同 run 的 immutable receipt、完整 payload、各 stdout／stderr 原件 bytes／SHA 與實際完成時鐘；孤立的 passed、未finalize、缺件、換版或讀取中變動不能當已驗成功。此 receipt 未穩定綁定 data_root，僅代表該次執行原件一致，不授來源、DB、PIT、績效或自然成熟資格。

此 reader 的 latest／receipt 各限 1 MiB、子程序 stream 各限原 producer 的 64 KiB，只讀指定 run，不掃描歷史補值。regular-file／no-follow／hardlink／reparse、JSON 深度與重複鍵、取消及讀後重驗沿既有檔案防線；Runtime 在通用 JSON 讀取前即分流此 lane。已知 child 啟動前失敗與啟動後 artifact pending 分開，後者不可驗證；逾時的 snapshot_saved／duplicate 保留 None。只有安全原因碼、固定階段、整數毫秒與例外類型可進 UI，原 stderr／例外訊息留在原件。原 producer、120 秒 child 期限、30 秒被動狀態輪詢與正式 Task 均不因此變動。

`runtime/` 管理 Runtime 的狀態、事件、保存介面與驗證；`app_module/runtime_services/` 提供 application orchestration；`ui_qt/runtime_composition.py` 將唯讀 controller、bridge、view 與 Qt lifecycle 組合。Runtime Observatory 讀取治理 DTO／排程狀態，不直接啟動資料更新、模型訓練、task 或 evidence producer。

Windows Scheduler 與受控 CLI wrapper 依各自任務執行資料更新、dry-run 或已獲批准的工作。市場更新寫入、Evidence dry-run、批准後 Evidence write mode 與 broker execution 是分離權限；排程成功碼或 readiness 不代表人工批准、資料接受、promotion 或交易。

Runtime store、排程輸出、個人資料與正式市場 DB 必須使用明示 root／namespace。來源缺失、job partial、timeout、未成熟 evidence 或不一致 receipt 要回報狀態與 diagnostics；唯讀面板只投影，不自行補跑。

## Immutable ML publication

`OUTPUT_ROOT/release_v4` 下的 PIT、Direct 與 OOC publication 依各自 `runs/<id>/manifest.json` 保存 immutable identity；root 的 `latest_manifest.json` 是 current pointer。保留與檢查必須一起核 pointer、manifest hash 及 OOC → Direct → PIT dependency closure，不能只看修改時間或目錄大小。

| Publication | 子目錄 |
|---|---|
| PIT | `ml_pit_year_shards` |
| Direct | `portfolio_ml_direct_numeric_production_v4_v2` |
| OOC | `portfolio_ml_direct_ooc_training_production_v4_v5` |

Scheduled PIT／Direct wrapper 在啟動 worker 前做唯讀 capacity preflight，並在 Direct checkpoint 重驗整數 bytes 配額。相容 profile 需 35 GiB 持久新增、40 GiB 暫存峰值、20 GiB safety reserve；全鏈 profile 另含 125 GiB reserve、10 GiB daily update 與 15 GiB 餘裕，required headroom 200 GiB。超額須在 checkpoint 停止並保存 blocker，不建立新 partial publication。容量通過只允許 worker 啟動，不授予 Formal input、OOS、promotion、scheduler 或 broker 權限。

`inspect_ml_storage_retention.py` 是完整 metadata inventory reader，固定 `automatic_delete_allowed=false`，沒有 archive／delete／pointer mutation 能力。人工 retention 須先檢查 exact scope，至少保留 current pointer 與完整依賴鏈；resume／partial 的刪除代表放棄續跑並另行重算。被 runbook／release／QA 引用的舊 run 須先 cold archive 或建立 durable tombstone；不得改寫 append-only 歷史中的舊 ID／hash，也不得對 `release_v4` root 或 wildcard 遞迴刪除。

OOC `minimal_linear_shadow` 只接受單一 `ridge_logistic` 與明示 horizon，並在相同 frozen rows／cost 下對照 Rule／Equal Weight；`full_shadow` 保留多 horizon／HGB challenger。若 release root 有 `release_manifest.json`，`AllocationReleaseAdapter` 仍須核 artifact／sidecar hashes、feature order、missing policy、dataset lineage 與 calibration；frozen-row parity 失敗時退回 Rule-only。缺 attached calibration artifact 時，OOC diagnostic calibration 不能充當正式校準器。

年度POST原件另以`data_module/tpex_annual_calendar_transport_v1.py`的具名DTO／codec保留；共用原V1完整body校驗但不冒充舊monthly response，亦不新增getter。年度evidence及具名daily保存／reader已沿同一核心接入，舊月別wire原義保持；真source／schema用途接受與正式配置仍待。

年度期間證據使用`recommendation_portfolio_annual_calendar_evidence_v1`的獨立canonical wire，保存兩市場年度原transport並沿Root金融衍生逐年重驗，公開日期保留原pair使用的ISO字串。它不經舊monthly evidence codec、不重編碼raw；具名年度daily與月別共用同一create-only／pending／clock／exact read核心，最小唯讀Protocol保留原pair診斷。原三檔schema與新年度三檔各自獨立，兩份可信用途錨點固定來源家族；合成測試不授真用途或成功批次，詳[年度候選契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#tpex年度股票日曆候選解析)。

年度真取得custody候選以外部pins另存原receipt／sidecars與保守controller完成觀測版，原worker時計不補造receipt綁定；兩程序可重算同年度evidence。此owner output沒有發布daily或繞過public artifact的output／formal roots守衛，真用途接受與正常Main配置仍各自待核，見[每日來源契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#tpex年度股票日曆候選解析)。

## Recommendation 校準套件的 Windows 檔案接點







排程consumer的同次身份邊界：日曆refresh `refreshed`只取刷新後終態並核決策年／path／hash／clock；Evidence要求canonical recommendation與passed狀態各自成立。個人H20每日推論與manifest發布使用既有 `PersonalH20ReadSession`，只在同一operation共用完整JSON binding，每份capture仍核原bytes，成功前重驗來源群組與完整manifest，變動或取消不發布成功reference。私人原frozen model、中央母體、20-session與formal資格不變；Paper NULL open僅同日retry，跨日不回填。驗收與來源限制見[10/13排程QA](../../06_qa/BALDR_SCHEDULE_REPORT_REPAIR_20261013.md)。

校準 runner、TrainingResult、lineage publisher、promotion authority、artifact loader 與 consumer 共用 `runtime/file_io_path.py` 的純 transport。只有可安全渲染的 Windows 長路徑在 OS 操作接點使用 extended 形式；對外 root、candidate ID、lineage path、相對 inventory、JSON 與 hash identity 保持原路徑。短路徑、relative、dotdot 與原特殊輸入保留既有 Path 操作及 strict resolve／exception 時點，transport 不授予 ownership 或 no-follow 資格。

Lineage 的 create-only 發布仍先驗證 canonical target／parent。只有 tempfile.mkstemp 的自有 parent 明示 force_extended=True，避免短 parent 加上隨機暫存 leaf 後越過普通 Windows 路徑限制；helper 預設仍為 False，所有 strict lexical guards、descriptor 關閉、fsync、hard-link 與 finally cleanup 順序保持。

原 lstat／reparse／一般檔案、parent／root、hash、PIT、same-run binding、pair reread 與 create-only hard-link 發布守衛仍由 caller 每次執行；不快取或合併讀取。列舉以原 parent／basename 重建，再精確比對該次 OS 回值。Default joblib 可取得內部 I/O 路徑；legacy custom deserializer 仍收到原 Path，verified-buffer 路徑仍拒絕 custom callback。

此修正限於上述校準套件鏈，不代表其他 scheduler、UI、publication 或任意超長 root 全面支援。長 dotdot 維持原 OS 行為；安全長路徑 resolve 後若 OS 回傳特殊名稱，strict inverse 仍可能拒絕。OS exception 的 filename 是診斷字串，不作 identity。實際範圍與尚未接受的 no-follow／types／產品 Gate 見[10/12 補完 QA](../../06_qa/BALDR_COMPLETION_RESUME_PROGRESS_20261012.md)。

## 保留、遷移與高風險邊界

- 不刪除或覆寫正式 raw source；全量重建前須有備份、明確確認、可用 restore path 及完整來源核對。
- SQLite schema／CSV fallback 改動須經受控 migration；狀態查詢與一般 reader 不初始化資料庫。
- Immutable publication／模型 artifact 的 retention 依 manifest lineage、consumer 與 recovery 契約執行。舊 anchor [`#111-immutable-ml-publication-retention`](../system_architecture.md#111-immutable-ml-publication-retention) 仍由架構首頁導向本段。現行 `scripts/inspect_ml_storage_retention.py` 僅提供唯讀 metadata inventory；此 repo 尚無現行 destructive retention runbook，舊 Manual Supplements 只供歷史追溯，不構成操作步驟或授權。
- `development_module/` 只在呼叫端明示的 development output root 產生 research-only artifact；它不接正式 scoring、Portfolio、Exit、scheduler 或 formal OOS。
- 來源可得日、SQLite migration、跨 root identity、正式 data writer、scheduler 權限與 model publication 都是高風險修改區，須依各自 QA／Runbook 驗證，不從本冊推定任何 Gate 已接受。

### Immutable ML retention 的目前檢視與核准邊界

1. 先用唯讀 `scripts/inspect_ml_storage_retention.py` 對明示的 `--root` 路徑產生 metadata inventory；可選的 depth、file count、candidate size 與排序參數只縮小檢視，輸出僅能寫入 OS temporary directory。Inventory 是候選檢視，不會刪除、搬移或改 pointer，也不是刪除授權。
2. 對每個候選項逐一核對 root 的 `latest_manifest.json`、其指向的 manifest/hash 與 OOC → Direct → PIT 依賴閉包；再查明 release、runbook、QA 或其他 consumer 是否引用該 run。不可依 mtime、目錄大小或單一 pointer 判定可移除。
3. 若仍需保留空間，先為精確候選路徑與完整依賴/引用物建立 cold archive 或 durable backup，記錄原相對路徑、bytes/hash、pointer 與 manifest identity，並確認可從該備份恢復。若引用無法結清，保持候選不動；若採 tombstone，須保存舊 ID/hash 與 lineage，不重寫 append-only 歷史。
4. 任何 archive/delete 都要先取得針對 exact root、path 與 action 的明確授權；只處理列明的項目，不用 wildcard 或 `release_v4` root 遞迴操作。`resume`／partial run 被移除即放棄續跑，後續須建立新 run，不得宣稱可接續原 checkpoint。
5. 操作後讀回原 pointer、保留項目與完整依賴閉包，核對 manifest/hash；需要恢復時，從記錄的 cold archive/backup 將 bytes 還原到原精確相對路徑，逐一比對保存的 hash，再重核 pointer 與閉包，確認之前不恢復任何 consumer。此處是受控操作的安全邊界，不代表本 repo 已提供自動 restore/delete 命令。

<!-- 舊書籤導向：current system_architecture 的個人模型／ML lineage contracts 由本冊第一節和決策分冊接續；完整日期化原文位於文件治理原 bytes 封存。 -->
