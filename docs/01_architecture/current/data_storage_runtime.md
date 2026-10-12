# 資料、保存與 Runtime

本冊描述來源取得、儲存、研究快照與排程觀測的 current 邊界。一般操作看 [Application Manual](../../07_guides/APPLICATION_MANUAL.md) 及對應現行 Runbook；目前狀態與資料資格看 [Snapshot](../../00_core/PROJECT_SNAPSHOT.md) 與具名 QA 收據。舊 [Application Manual Supplements](../../07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md) 僅供歷史錨點追溯，不是現行操作或授權依據。

## 資料路徑與來源

`data_module/config.py` 的 `TWStockConfig` 是資料路徑權威。`DATA_ROOT` 預設為 `D:/Min/Python/Project/FA_Data`，可用環境變數覆蓋；`OUTPUT_ROOT` 亦由同一設定管理。主要市場 SQLite 位於 `<DATA_ROOT>/sqlite/twstock.db`。程式不得另造正式資料根目錄或硬編路徑。

每日市場更新的主要資料流是：

```text
TWSE／TPEX 明示來源
  → DATA_ROOT 下的來源日檔／raw evidence
  → SQLite sync 更新 daily_prices 等正式讀取表
  → 技術指標 job 及 application read models
```

SQLite-first 是一般讀取優先序；CSV 保留原始來源、完整備份、明確 fallback／migration 與研究匯出用途。沒有行情或 provider 不可用時，讀取路徑回傳 missing／diagnostics，不把空結果當成零值，也不因讀取而建立空資料庫或 schema。

新來源需保留來源識別、版本、`as_of_date`、`available_date`、quality、missing policy、授權與下游資格。正式決策只消費決策當下可取得且通過來源 gate 的資料；來源候選依 Diagnostics → Shadow → Evidence Review → Accepted Feature 逐步判定。Raw data 不因補算、格式整理或 UI 操作被覆寫。

決策日、資料觀測日、來源可得時間、writer 可得時間、保存時間與預期官方交易日是不同時鐘。`available_at` 由來源或特定 writer contract 定義，後者通常在 artifact／receipt 發布並讀回後才簽發；`persisted_at` 只是保存／排序事實，不能代替官方來源 availability、writer availability 或 PIT 證明。跨日 freshness 應由共用的 market-session cadence／已驗證日曆依同次 operation 明示的 aware cutoff 判斷；歷史 clock 不賦予 current freshness。實際行情日要隨 DTO、snapshot 與 evidence lineage 保存。日曆缺失、未發布、hash 不符或來源日期晚於 cutoff 時保留 unknown／degraded，不借鄰近資料、日曆常識或另一個 provider 補出來源資格。來源 custody／corporate-action 診斷須綁 raw bytes、日期、availability 與行情欄位；方向未知就 fail closed。各 API 欄位語意仍以其 owner contract 為準，不得互換時鐘。

## 讀寫與保存契約

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

市場資料表包括 `daily_prices`、`market_indices`、`industry_indices`、`technical_indicators` 與 `broker_flows`。Fundamental tables 透過受治理 provider／Factor service 讀取；UI 與策略核心不直接讀 raw fundamental CSV。表的現存數量與日期覆蓋屬動態資料狀態，需另讀當期 QA，不在架構文件保存計數。

Broker Flow 的買賣榜資料各自保存；缺欄位保留 NULL／品質標記，不以零值補缺。更新前先核對交易日證據；來源 HTTP path 失敗時才使用既有 fallback，更新仍按既有序列流程。

跨頁研究母體、圖表與 saved query 依固定來源身份共享同一結果投影。完整母體 strict reader 需先核 manifest／receipt pins；單一來源 segment 最多 256 檔是保存分段限制，不是 universe 上限；全域篩選與排序完成後才分頁。bookmark 重開指定來源、query 與選取狀態，不能回退一般最新資料讀取。

匯出服務消費 UI 傳入的結果 snapshot，不重跑策略或重新計算績效；寫檔使用暫存檔後原子替換，缺失的 lineage 欄位顯示 unknown。SQLite Inspector 以穩定排序鍵加唯一 `rowid` 作分頁 tie-breaker；唯讀查詢不建立資料庫，新的篩選或查詢先重設頁碼，過期 worker result 依 request identity 丟棄。

Research Run Registry 的 metadata SQLite 與 Parquet artifact 位於 `OUTPUT_ROOT`，與 `DATA_ROOT` 市場 DB 分離。保存依 staging／files-ready／committed 狀態發布；清單只顯示 committed、valid run，load 時重驗 artifact hashes。Registry/history reader 需 caller 明示序列化讀取預算；已接受的 R01 profile 為每個 artifact 最多 64 MiB、每次呼叫合計最多 256 MiB。這是輸入 bytes 上限，不是解碼後 RAM 上限或所有 caller 的預設值。舊版本的 execution assumptions 讀取其保存 metadata，不依當前 UI 重建或跨版本升級。

Forward rule observation 的 regular-file/no-follow reader 另有明確窄預算：單次 capture 至多 2 MiB、256 captures、保留 bytes 合計至多 64 MiB。這些上限只約束該 observation reader，不是全域檔案／artifact 預算；超限或來源檔型態不符即拒絕，不以無界讀取補救。

Evidence Event／Outcome append-only 保存決策來源與後續觀測。Forward outcome 的 close-to-close return 是事後診斷，固定 `is_execution_pnl=false`，不能替代 next-open 執行績效，也不因成熟而自動升 evidence tier。查詢只投影已保存的 event／outcome；缺來源或 benchmark 保留 NULL／warning，不補回舊事件資料。

## Runtime 與排程

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
