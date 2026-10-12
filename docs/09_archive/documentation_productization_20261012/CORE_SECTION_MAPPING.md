# 核心權威文件可讀性重整映射

此表供文件治理 review 使用。基準原文以原始 bytes 封存在 `docs/09_archive/documentation_productization_20261012/originals/`，本映射只指出目前該讀哪個 current authority，以及哪些內容留作歷史追溯。日期化 QA 數字不與穩定契約混寫，也不由封存原文推定目前狀態。

## Snapshot 與 Roadmap

| 封存前來源／範圍 | 目前入口／處置 | 判讀界線 |
|---|---|---|
| `docs/00_core/PROJECT_SNAPSHOT.md` 目前狀態與 10/12 最新增量 | 精簡於 [PROJECT_SNAPSHOT](../../00_core/PROJECT_SNAPSHOT.md)；指定候選 P08、Main native failure、P01 p95、M25/M26、Health 的最新邊界由具名 [補完進度與 QA 收據](../../06_qa/BALDR_COMPLETION_PROGRESS_20261011.md) 支持 | 只記可支持的當前狀態。局部 PASS 不升格成整包、完整 P08 或產品 Gate 完成；仍未核事項留待驗。 |
| Snapshot 舊「歷史快照與驗收入口」及所有 dated increment（P01/P08/M23–M26/Health 等） | 最新狀態回 Snapshot；逐輪原文／原始 bytes 進 `originals/docs/00_core/PROJECT_SNAPSHOT.md`，各測試範圍留具名 QA receipt | 歷史 Snapshot 不取代後來收據；不得把不同版本、候選或 scope 的結果相加。 |
| `PRODUCT_ROADMAP_POST_REFACTOR.md` §1–2 與產品能力基線 | 產品需求、Gap 與資格判讀留 [Product Roadmap](../../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)；舊 dated baseline 改成持續適用的資格邊界 | 產品 Roadmap 定義要證明什麼，不是完成紀錄。當前狀態由 Snapshot／QA 決定。 |
| Product Roadmap §§3–13、§§16–21 | 仍在 Product Roadmap，保存產品方向、Advice／Portfolio／Exit／Evidence 契約、資料來源 Roadmap、模型導入順序、指標、非目標與開放決策 | 本次沒有將產品策略另拆新文件。現行來源優先序 §11 原樣保留。 |
| Product Roadmap §14「歷史 30 / 60 / 90 日草案」 | current §14 僅作歷史導引；原草案 bytes 仍在 archive original，Roadmap 主文不再把過期時間表當作現行順序 | 歷史提案不等於目前 Gate、批准範圍或工作完成。 |
| Product Roadmap §15「六個月產品 Gate」 | current §15 用單表交代 Gate 問題、產品證據／退出、產品安全邊界與對應 6M 工程 Gate | 產品 Gate 問產品能力與接受證據；工程 Gate 控制交付與技術驗證，兩者需各自滿足。 |
| `ROADMAP_6M_ENGINEERING.md` §§1–13 | [6M Engineering Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md) 保留 Gate 0–7、交付、驗證、禁止事項及 Exit Criteria；月份是 Month 1–6 相對順序 | 不用日曆日期或 Snapshot 優先事項替月份重新起算；Gate 7 仍條件式，readiness 不等於授權。 |
| 6M dated checkpoint／更新記錄 | 不留在 active entry；追溯到原始 bytes 與 relevant QA；current 文末提供 [歷史追溯](../../00_core/ROADMAP_6M_ENGINEERING.md#歷史追溯) | gate title／核心 anchor 保留，日期流水不作現況。 |
| `DEVELOPMENT_ROADMAP.md` | 收斂成 [Roadmap Hub](../../00_core/DEVELOPMENT_ROADMAP.md)：按 Scoped SSOT 導往 Snapshot、產品方向、6M、版本、舊工作與架構／操作 | Hub 不複製狀態、日期增量或各 Roadmap 的詳細契約。 |

## Current architecture 與 Target 導覽

| 封存前來源／範圍 | 目前入口／處置 | 判讀界線 |
|---|---|---|
| `system_architecture.md` 系統定位、分層與主要資料流 | 精簡在 [目前系統架構](../../01_architecture/system_architecture.md)：列實際 package、入口、責任、主要資料流、儲存／排程與不變條件 | `market_module/`、`advice_module/` 等 target-only 名稱不列成 current package；全貌不證明 Gate 已通過。 |
| system architecture §§3–4：UI、9 工作區、Daily Decision Desk、Application 組合 | 合併至 [UI 與應用流程](../../01_architecture/current/application_and_workspaces.md) | Daily Decision Desk 是「市場探索 > 市場總覽」中的功能，不是第二個頂層 widget。UI 顯示 DTO，不取得領域計算或正式 writer 權限。 |
| §§5–7：Decision、Backtest、Portfolio | 合併至 [決策、研究與 Portfolio](../../01_architecture/current/decision_research_portfolio.md) | 保留 BP／Decimal、T-1 quantile、可得時點、next-session-open.v2、OOS reset、manual／declared／paper 身分分離及 evidence 層級；增補 Health exact receipt、scenario amount identity、Paper finalize 邊界、Forward observation 與 H20 雙 cutoff。 |
| §§8–10：Data、Broker Flow、Runtime、排程 | 合併至 [資料、保存與 Runtime](../../01_architecture/current/data_storage_runtime.md) | 保留 `TWStockConfig` 路徑權威、SQLite／CSV 讀寫邊界、NULL／unknown、Runtime 只讀投影、writer／schedule 權限隔離；增補跨時鐘語意、store route/CAS、Paper/Scenario exact read schema、narrow reader budget 與 retention 的唯讀檢視及授權界線。 |
| 保存母體讀取與取消（封存原件 §19） | 落在 [UI 與應用流程](../../01_architecture/current/application_and_workspaces.md)「研究畫面與保存身份」之後 | `task_cancellation.py`、`task_worker.py`、`daily_market_technical_universe_v4_query.py`：明確 opt-in 的一次性能力綁原 worker/event/callback/thread；invalid claim 消耗並序列退回；最多 8 未完成 futures、按 artifact 順序消費，取消／錯誤後自然收尾。未搬測試數字。 |
| Position Health immutable result／receipt exact read（2026-10-11 原件） | 落在 [決策、研究與 Portfolio](../../01_architecture/current/decision_research_portfolio.md)「Portfolio、Paper 與持倉研究」 | `position_health_saved_archive.py`、`position_health_transition_read_service.py`：result／receipt／baseline／source witness hashes、writer UTC availability、exact receipt/scope/aware cutoff、hash 與 source witness 驗證；不以 latest 補件。日期化 QA 數字留收據。 |
| Paper daily checkpoint 與 availability（原件 §27–47） | 領域身份在 [決策、研究與 Portfolio](../../01_architecture/current/decision_research_portfolio.md)；schema、讀寫與 transaction 在 [資料、保存與 Runtime](../../01_architecture/current/data_storage_runtime.md) | `strategy_paper_account_daily.py`、`paper_trade_ledger.py`、`strategy_paper_account_availability.py`、`personal_store_routes.py`：PAPER+PERSONAL route、strategy/version/account/operation/portfolio/cutoff、exact schema/marker/hash readback、`PENDING → LEDGER_COMMITTED → FINALIZED`、identity-checked idempotent retry；state 與 ledger 不具跨 DB 原子性，partial 不等於 finalized。 |
| Portfolio research scenario／完整估值（原件 §27–47） | 領域身份與金額在 [決策、研究與 Portfolio](../../01_architecture/current/decision_research_portfolio.md)；route/schema/hash 在 [資料、保存與 Runtime](../../01_architecture/current/data_storage_runtime.md) | `portfolio_research_scenario_artifact.py`、`portfolio_research_scenario_repository.py`、`portfolio_research_valuation.py`、`portfolio_research_scenario_service.py`：v3 canonical artifact 與 v1 SQL schema 分離；`PORTFOLIO_RESEARCH` route、exact account/portfolio/snapshot/hash、missing read 不建庫不 fallback；完整 cash/shares/mark/value/NAV，bp 僅展示。 |
| Forward rule observation、reader 時計與 bytes limits（2026-10-11 原件） | writer/read eligibility 落在 [決策、研究與 Portfolio](../../01_architecture/current/decision_research_portfolio.md)；讀取限額與通用時間欄位落在 [資料、保存與 Runtime](../../01_architecture/current/data_storage_runtime.md) | `strategy_rule_forward_observation.py`：exact parent/cohort/generation/source cutoff；拒收 caller score/target/fill/source clock；寫回讀回後的 writer `available_at`、cutoff 與來源順序驗證；2 MiB／256 captures／64 MiB 為此 no-follow reader 專屬上限，非全域 budget。 |
| Source/writer/persisted clock（2026-10-12 原件） | 落在 [資料、保存與 Runtime](../../01_architecture/current/data_storage_runtime.md)「資料路徑與來源」 | `result_artifact_store.py` metadata 將 `persisted_at` 作為 mutable metadata；current 章明確聲明保存時間不等於來源 availability、writer availability 或 PIT，並由 API owner 定義各 aware cutoff 語意。 |
| Personal H20 dual cutoff（原件「Personal H20 artifact and lineage boundary」） | 落在 [決策、研究與 Portfolio](../../01_architecture/current/decision_research_portfolio.md)「Evidence 與模型權限」 | `personal_candidate_inventory.py`、`recommendation_training_lineage.py`：candidate fit/training cutoff 與 merged-lineage `training_as_of` 分開；欄位約束與 label availability 驗證，decision-time lane 兩個 cutoff 均不晚於 decision date。保留 canonical lineage owner，不重造 artifact。 |
| Personal route 與 Watchlist COW migration（原件「Personal store routing」／「Watchlist revision storage」） | 落在 [資料、保存與 Runtime](../../01_architecture/current/data_storage_runtime.md)「讀寫與保存契約」 | `personal_store_selection.py`、`personal_store_routes.py`、`watchlist_cow_activation.py`：`LEGACY_COMPAT`／`PERSONAL`／`LEGACY_READ_ONLY` route、缺失 personal 不 fallback、source readonly、marker/lock、hash/schema/capacity fail closed、CAS `expected_revision` 與 rollback 保留 target 歷史。 |
| Immutable ML retention 目前操作邊界 | 落在 [資料、保存與 Runtime](../../01_architecture/current/data_storage_runtime.md)「Immutable ML retention 的目前檢視與核准邊界」；[Manual Supplements](../../07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md) 僅列歷史追溯 | `scripts/inspect_ml_storage_retention.py` 僅唯讀 inventory，沒有 archive/delete/pointer mutation；目前未找到現行 destructive retention Runbook。Current 步驟明列 explicit-root preview、pointer/hash/dependency/consumer closure、備份／還原與 exact-scope 授權，不把歷史 redirect 當操作權威。`docs/06_qa/DATA_ML_GOVERNANCE_QA_INDEX.md` 的操作連結已由 root 改指 current 分冊；舊 Supplement 僅追溯。 |
| §11：資料保存、模型 lineage、personal state、Research Registry、immutable ML publication retention | 依責任分到 [決策、研究與 Portfolio](../../01_architecture/current/decision_research_portfolio.md) 與 [資料、保存與 Runtime](../../01_architecture/current/data_storage_runtime.md)；相容 anchor 仍由 system overview 導向 | 留有 manifest/hash、exact identity、committed-only registry reader、64 MiB／256 MiB R01 budget、Evidence tier、release root／依賴閉包／保留守衛等穩定契約。容量計數和當次 inventory 不代表目前佔用。 |
| §§12–15：匯出／分頁、文件架構、高風險變更、驗證 | 匯出、穩定分頁、exact snapshot 與高風險儲存條件併入資料分冊；入口與分冊關係列於 [架構 README](../../01_architecture/README.md) 及 [current 分冊索引](../../01_architecture/current/README.md)；QA 路由回各具名 receipt | 個別驗證數字與歷史 PASS/FAIL 不複製成架構 contract。 |
| system architecture 日期化更新／§16（2026-10-03 至 10-11），含 UX、F-series、M2、H20 及來源整合 | stable cross-cutting contract 按 UI/pinned context、decision/evidence、data/store/cadence 分別納入三本 current 分冊；當日 scope、收據、計數、失敗與限制留在原 bytes／連結 QA | 不把一整個日期 section 標為純歷史；也不以日期先後判定哪個狀態有效。每個 QA acceptance 只支持其列明版本、來源、scope 與驗收方法。 |
| `target_system_architecture.md` 長篇 target 分層、flows、module contracts 與 dated gap baseline | 改為 [Target 導覽](../../01_architecture/target_system_architecture.md)，描述領域方向、狀態語彙和 current→target 導讀；歷史差距與 detailed proposal 回原始 bytes／QA | `FINAL_TARGET_ARCHITECTURE.md` 是目標 package、owner、契約、依賴與遷移設計唯一權威；本導覽不是 target specification，也不授權新增 package。 |
| `docs/01_architecture/README.md` | 重寫為 [架構入口](../../01_architecture/README.md)，先 Snapshot/current，再按需進 Target FINAL／操作手冊 | Product Gate 7、6M Gate 7 與 Target FINAL R7 各有不同意義，不互相推論。 |

## 舊 anchor 與外部引用修鏈

| 來源 anchor | 本次狀態 | 修鏈提示 |
|---|---|---|
| `system_architecture.md#daily-decision-desk`、`#4-daily-decision-desk` | current overview 保留相容 anchor，導向 UI 分冊工作區責任 | 現存 Spark execution plan 等引用可繼續使用。 |
| `system_architecture.md#homepage-navigation-and-research-context-boundary` | current overview 保留相容 anchor，導向九工作區章節 | 仍可使用。 |
| `system_architecture.md#personal-h20-artifact-and-lineage-boundary`、`#ml-lineage-reader-dependency-boundary`、`#natural-maturity-proof-and-model-loader-boundary` | current overview 保留並導向決策／研究分冊的 evidence 與模型權限章節 | 保留舊書籤語義；不表示目前模型資格。 |
| `system_architecture.md#111-immutable-ml-publication-retention` | current overview 保留 anchor，導向資料分冊的不可變 publication／retention 部分 | QA index、retention QA 等舊引用可繼續使用。 |
| `target_system_architecture.md#1011-ml-shadow-layer` | Target 導覽保留 anchor，定位為長期領域說明 | 舊架構 README deep link 可繼續使用。 |
| Product Roadmap §2.2：舊 `能力基線（截至 2026-09-17）` | 標題改為 `產品資格判讀` | 舊自動 anchor 不保證相同；全 repo reference search 未發現 active 深鏈。需要保留外部 bookmarks 時由 root 決定 alias。 |
| Product Roadmap §14：舊 `歷史 30 / 60 / 90 日草案` | 標題簡化為 `歷史執行草案` | 舊自動 anchor 不相同；全 repo active 深鏈未發現。 |
| 6M Roadmap 舊 `更新記錄` | 改為 `歷史追溯` 導覽 | Gate 0–7 主要 anchors 未變；舊更新記錄深鏈若存在需轉至 archive/original。 |
| Snapshot 舊 `歷史快照與驗收入口`、`工作區與資料保護`、`下一步與導航` 及其後每個日期化增量 heading | 主文重組成「目前狀態／產品與系統入口／重要限制」；日期流水移出 | 原逐段 heading 不再是 current anchor。封存原文保留原 heading 供按版本檢索；active reference scan 未發現需要保留的 Snapshot 舊增量深鏈。 |

## 語義不確定性／需要 root 收斂之處

- 2026-10-03 至 10-12 architecture overlay 同時包含 implementation contract、有限驗收範圍與 dated state。三本 current 分冊保留共用的來源身份、可得日期、唯讀 exact readback、store identity、數值／時間軸與不可自動升格規則；feature-specific options、細微 API／檔名、worker 數量、測試計數及例外仍依具名 QA／Manual。若 root 將任何這類細節視為新的 current normative contract，應按主題加進既有分冊，不恢復日期流水整段。
- P08 的 `5 PASS / 21.89s / native 0` 僅對 Snapshot 所指 frozen synthetic candidate/version 生效；原始 QA 中其他候選或變更版本不能併入這一結論。P01 crash 根因仍未確認；M26 closure 與 Health integration 仍待審查／驗收。
- ML retention profile 的 35／40／20 GiB 與 125／10／15 GiB 是已記錄 wrapper/full-chain capacity policy，不是現有 release inventory 或可刪空間；本分冊保留需求合計，當前 volume／run 證據仍須另讀唯讀 inventory receipt。
- Target overview 對長期 capability 做領域描述；其 package 拆分與 implementation dependencies 需完全以 `FINAL_TARGET_ARCHITECTURE.md` 為準。原 target 長文中的圖與日期差距不應被當成第二份設計權威。
