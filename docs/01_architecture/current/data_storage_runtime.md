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

TWSE 日價下載的新 parser `twse.mi_index.direction_text.v2` 先解析明確文字正負號，再沿既有 CSV／SQLite 同步及 public report。共用文字契約位於 `data_module/price_change_direction.py`，application 仍由原 import 入口使用 Decimal resolver；資料層不反向依賴 application。非空未知方向保存 `unknown`，不由顏色補值。Raw 首份收據可保留 v1，本次 observation／projection／publication 綁實際 parser；v2 發行與重開均逐列核原 body，舊 v1 不重解釋。來源時間、正式用途及 PIT 資格不因 parser 修復改變，詳[方向版本契約](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#twse-日價方向文字版本increment128)。

## 讀寫與保存契約

後續Source的F07筆記服務以`DailyMarketTechnicalSnapshotProofScope`保留最多128份同程序、repository發行的語義證明；`ContextVar`只在實際背景讀取內啟用。命中須重驗seal／登記／完整manifest，仍fresh讀取全部artifact並核bytes／SHA／layout，由本次bytes重建typed snapshot與原binding；保存計算binding沿原validator，不要求舊保存kernel等於現行kernel。Scope不存snapshot、raw或parent結果，新程序與未命中仍完整strict。P01的session capability不擴大，parent只重用同次plan純投影，所有child核對保持。此候選與原完整240秒旅程的驗證狀態見[F07 QA163](../../06_qa/BALDR_THEME_DAILY_QA_20261018.md#f07語義證明範圍qa163164)，不改來源用途、時鐘或PIT資格。

同一已開啟View／query的返回候選另沿既有P01頁面讀取：原issued session／result保留，重讀原頁所涉批次並重建新page，完整selection pins相符才恢復。這不是新的全母體核驗或Scope擴權；跨query／無可用state仍full重開，保存與開啟原版本仍完整fresh。取消或完整性失敗不回退舊DTO；UI契約見[跨頁接線](decision_research_portfolio.md#價格研究個股與-portfolio-跨頁接線)。

`technical_source_copy.copy_price_bookmarks` 沿同模組已完成的closed technical copy收據及封存歷史鏈，將明選F07價格收藏另存新legacy清單。原清單逐bytes封存，來源pin先匹配沿革，再用原PriceReadSession／query／page／selection／bookmark codecs重建新定位的錨點；價格、snapshot／raw row hash、來源時計、所有查詢政策、頁碼與比較順序保持。新ID另記映射，不改原serializer／reader，不以root alias繞過exact守衛。CLI只寫全新根，不啟用設定；原清單／完整來源在發行前後重驗，失敗保留pending與具名原因。其他家族、COW及外部來源未自授搬移，詳[Runbook](../../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md#明選價格研究收藏的新副本來源工具)。

`research_output_copy.py` 原三store預設不變；caller 以 `include_recommendations=True`（CLI `--include-recommendations`）另明選 `recommendation/runs`。Legacy `runs.result_id` 與 canonical index／metadata 共用原 `RecommendationExecutionQueries` 驗身分，新索引僅改既知 `data_path`，原 JSON／artifact bytes不動。canonical 先由 verified envelope 核外部ML收據依賴，缺完整搬移契約時在任何該收據I/O與目的根建立前拒絕；來源邊界、全量預算、取消、journal／trigger、讀前後SHA與失敗隔離沿原工具。新收據明列選定store，不啟用設定或更動來源時間／用途資格。操作與驗證見[Runbook](../../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md#保存研究的新副本來源工具)及[129 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment129-recommendation-output-copy)。

`restore_research_output` 接受同一 `research-output-copy.v1` 封存及外部固定收據SHA；原狀態可為 `copied_and_public_readers_verified` 或 `restored_and_public_readers_verified`。來源根移位後，舊邏輯絕對根只作封存內映射，不開啟；所選store的完整清冊、每檔bytes／SHA、索引run與收據身分先核對，再在全新根複製原bytes、只重綁白名單SQL欄位。所有SQL列須等於原列加該映射，非DB原件SHA保持，重綁後才由原public readers讀回。一般推薦沿canonical／legacy原身分與metadata／context核對，外部ML依賴仍拒絕。成功另發 `restored_and_public_readers_verified`，輸入收據留 `original/RESEARCH_COPY_RECEIPT.json`；原封存前後重驗，失敗保留pending與原因。不啟用設定、不重算金融結果、不授來源用途或全環境移機，操作見[恢復Runbook](../../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md#已移位研究封存的恢復)。

技術副本的開發修正將唯讀完整核對限制為四件，原件／metadata寫入仍兩件；所有來源與目的SHA、集合、預算、取消及離開前等待自有I/O的守衛保持。`restore_technical_source_with_price_session`在新鏈同一次strict reader callback建立既有reader-issued價格session，僅在來源／目的最終核對及收據發行後返回。`copy_price_bookmarks`可明選該session，先驗發行錨點與六pins，前後兩次完整封存核對不省略；不傳session仍沿原factory。這只省去同一graph再次解析，不重算價格／規則或提升來源用途。首次設定600秒原FAIL保留，完整修後出口仍待。

`trial_first_setup.prepare_trial_package` 是既有研究／technical／F07收藏工具的首次設定整合，不新增來源或金融計算。外部SHA固定 `baldr-trial-first-setup.v1` 清冊；runtime、行情與基本面核完整相對檔案集合，研究與technical各沿外部收據恢復，收藏沿新technical鏈另記ID。只建不存在的固定 `state/`，成功才發config與setup收據；原件再核，partial／失敗留標記。同根重開不重算、不重設已保存內容；已有state換根拒絕且保留。該API的單元證據不授全包可攜／EXE／私人環境搬移，操作及現行驗證界線見[首次設定](../../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md#全新試用包首次設定整合候選)。

### 具名廣達月營收目前研究

`quanta_monthly_sales_snapshot`以已保存完整官方HTML與TWSE公司原件綁定2382／官方網站、同表兩年調整後合併口徑及NT$百萬元單位。只保存明選六件原件的新目錄，另發manifest、用途接受與批次receipt；雙外部SHA、完整集合、前後原件、EOF、版本／身分及台北可得小時皆重驗。`QuantaMonthlySalesReportProvider`以三項明選環境設定投影至原個股基本面DTO，欄位保留披露百萬元整數／0.1%及版本，沒有新的金融決策計算。未設來源時不開檔，缺件只隔離本來源；不改SQLite、原F17或每日月營收provider。`StockResearchReportReadService`只在目前日期／非保存歷史context讀此增量，未到時、未來cutoff及來源錯配皆不可用。此份真可用小時為台北10/18 04:00；到時前後Source／固定EXE Main、價格／返回／重載、歷史隔離與fresh分輪有證據，亦驗實際財報／月營收並存、股票切換及表格可捲到。139本機候選已封存43檔初態，不授全環境搬移或完整Gate。完整契約見[每日來源版本](../../03_data/DAILY_SOURCE_SNAPSHOT_CONTRACT.md#具名廣達月營收目前研究increment139)，操作見[具名月營收](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#廣達月營收固定版本來源分支139)。

### 具名營益目前研究版本



Increment132新增明選`twse-operating-summary-comparative-2026h1.v1`，不擴寫下述125政策。新版本共12檔：`current/`逐bytes保留原三公司9檔，另有固定SHA的比較數值事實、外層manifest及成功時鐘receipt。前期事實取自既存完整官方半年報，只接受2317／2330／2454的2025-H1合併口徑；原PDF及擷取收據另留原根，不隨快照散布。外層逐公司綁官方文件、原件／收據SHA與一次性目前研究用途，不授完整PDF重展示或其他用途。

公開reader重驗12檔、子版本、用途與真實現在；原當期五欄仍依台北19:00可用，新增比較依22:47成功保存向上取整至23:00。等待比較時保持原五欄，不把新時間倒填至舊版本。當期值保留CSV顯示精度，前期金額依財報披露單位；營收同比與前期率只有在披露誤差區間四角皆得到相同0.01%結果時才顯示，否則不可用。率差是顯示率的百分點差。DTO逐股／指標／期間／來源ID及版本／值／單位精確綁當期列；explicit as-of、保存研究上下文、歷史PIT、聚合、策略與ML不使用這份新比較。正常Main、同版EXE及交付狀態分別見[132 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment132-fundamental-comparison)。

原`twse_operating_summary_snapshot.py`的v1仍只接受資料集20762固定CSV、2330及2026-H1，不改原政策或7份原件。貨幣／期間由同發行人官方半年報與營收、四項比率在顯示精度內交叉核對，不外推1055列或未來版本。雙外部SHA、完整原件、一次性用途及每批實際保存時鐘獨立重驗；官方只有出表日，依成功批次台北小時，不借HTTP Date或財報期末倒填可得性。

固定125另以`twse_operating_summary_reviewed.py`沿原public reader核v1，逐SHA複製原7檔至新版本`base/`，外層manifest／receipt共9檔另綁2317／2330／2454各自半年合併口徑證據及新可用小時；原版本與首存時間不改。reader重驗外層及子版本、讀取前後SHA／檔案身分、pending／failure與實際時鐘，拒絕改issuer、用途、相對子路徑或前移小時。2382文件導向驗證頁，仍不可用。此版本已保存於2026-10-17，台北19:00以前拒讀；來源與固定125 EXE正常Main／fresh、返回／重載及同值／版本／時間／顯示已限定驗證；不以此接受全來源或歷史PIT。

`OperatingSummaryReportProvider`只投影至目前個股報告；幣值以Decimal乘百萬、百分比保留原值，稅後率是合併本期損益而非母公司歸屬淨利率。新用途以`OPERATING_SUMMARY_POLICY_SCHEMA=twse-operating-summary-reviewed-2026h1.v1`及原目錄／雙SHA明選；未設schema仍走原2330 v1，不自動找latest或擴用途。前期、歷史PIT、聚合、策略、ML、Paper與交易均未授，PDF不隨產品快照複製或重展示。配置與失敗隔離見[操作手冊](../../07_guides/manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#具名營益固定版本研究)。不改月營收、generic daily record、正式SQLite或其他來源。

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

`technical_source_copy.py`建立具名技術來源的新定位鏈與可移位封存；原600秒FAIL保留，經有界雙I/O修正後，明選1,951檔及既存125 EXE正常Main／收藏／fresh已限定驗證。它不自動重綁既存收藏、設定或整個125環境。它處理具名完整v4來源的定位，不修改既有reader契約。原strict reader先驗snapshot／batch manifest／parent／universe閉包；新根逐bytes保存snapshot及manifest，原plan／receipt另存`original`，以既有receipt codec建立新parent與universe鏈，再由原strict reader驗完整新閉包。source clock、原規則／價格、qualification與unknown不變；新parent `observed_at`只表示副本組裝時間，不授來源首存或歷史PIT。

封存恢復以外部SHA固定完整複製收據，再核closed檔案清冊、全檔bytes／SHA與預算。舊絕對URI僅作封存內明示映射，不能直接交給原reader或回查舊根；重綁後才由原strict reader授予新定位鏈的讀取資格。原副本／更早歷史收據保留，新receipt／path identity另記；缺件、額外檔、連結、修訂、取消或超限不發成功收據。操作與限制見[Runbook](../../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md#技術來源的新副本與封存恢復來源工具)及[127 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment127-technical-source-copy)。一般推薦／既存收藏、私人帳與全環境搬移仍另行核對，不自動啟用設定。

`research_output_copy.py`只建立明選三種研究store的新輸出副本：`research_runs`、`backtest/runs`、`recommendation_portfolio/runs`。來源全程離線唯讀、逐run經原Registry／legacy public reader；`ResearchHistoryLookup.select_legacy_run`以exact ID沿原身分、讀取預算與取消建立選取，不依清單頁長截短。複製原檔後只修改新SQLite的已知path欄位，逐欄確認其他metadata未變；Parquet／JSON與sidecar原SHA保持，原、新metadata／context與索引SHA分別記錄，不重寫原收據。

來源／目的根canonical與protected-root、無journal／staging／非標準trigger／view、明示檔／bytes／entries／runs預算、取消及來源／目的讀前後完整身分核對先於成功收據。失敗保留pending／failure，不啟用新設定、不刪來源、不遷移正式根；配置情境外部帳本引用尚不支援，須整批拒絕而非省略。新副本可沿既有嚴格reader開啟，錯根拒讀守衛不放寬。這不搬行情、technical v4、一般推薦／收藏或私人帳；限定正常Main／fresh及既存125消費證據見[126 QA](../../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment126-research-output-copy)，操作見[Runbook](../../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md#保存研究的新副本來源工具)。

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
