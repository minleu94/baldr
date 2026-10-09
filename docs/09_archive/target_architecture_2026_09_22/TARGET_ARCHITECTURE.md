> **已被取代，僅供審查歷史（2026-09-22）**：本草案不再作為實作依據。請閱讀 [FINAL_TARGET_ARCHITECTURE.md](../../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)；所有目標架構決策以 [FINAL_TARGET_ARCHITECTURE](../../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 為準。下文保留原稿供核對紅隊引用，與 FINAL 衝突的條文全部失效。

# 可漸進落地的目標架構

> 設計提案，尚未實作。本文件是 [既有目標架構](../../01_architecture/target_system_architecture.md) 的工程分冊：產品能力與權限沿用上位文件，這裡集中定義程式責任、依賴、執行契約與擴充落點，不另立產品 Roadmap。

## 1. 採用決策

保留 Python／PySide6、本機 SQLite／CSV／Parquet／JSON／numeric stores 及現行業務引擎。採用「按領域組織、application 組合、I/O 在 adapter、一次執行回傳完整結果」的模組式單體。既有頂層 package 大致不動；只在責任已被抽出、caller 與相容測試明確時建立子套件。

不需要服務拆分、訊息佇列、全域 event sourcing、萬用 repository、統一所有 dataset 的 schema 或全系統 DI container。EventBus 留作通知，不承擔結果保存。一般新欄位最多影響 owner、中央 codec、指定呈現／索引，加相應測試；若還要改多個 coordinator 的逐欄搬運，視為設計未完成。

閱讀入口：

- [現況與證據](../../01_architecture/target_architecture_2026_09_22/SYSTEM_ARCHITECTURE_ASSESSMENT.md)
- [端到端與 ML 資料流](TARGET_DATA_FLOW.md)
- [A–J 擴充檢驗](EXTENSIBILITY_TEST.md)
- [ML 相容計畫](ML_COMPATIBILITY_PLAN.md)
- [五步遷移](MIGRATION_STRATEGY.md)
- [實作不可違反的規則](ARCHITECTURE_INVARIANTS.md)

## 2. 目標程式結構

以下是**完成相應遷移後**的責任落點，不是現在已有的目錄清單，也不是要求一次建立所有空資料夾。未列出的既有功能依同一領域規則歸屬，不能因不在圖上就刪除。`market_module`／`advice_module` 暫不新增，市場與 Advice 純政策先放 decision 內。

```text
financial_module/                 既有 Decimal、bp、股數／貨幣單位
data_module/
  contracts/                      MarketSlice、SourceObservation、availability／quality
  sources/                        各 vendor acquisition、parser、raw custody
  readers/                        SQLite／CSV／PIT read adapter、明確 fallback
  storage/                        市場資料 schema、writer、source artifact 保存
  governance/                     source eligibility、修訂、acceptance
  ml_*、portfolio_ml_*            初期保留實際路徑，視為凍結的資料／ML 相容邊界
analysis_module/
  technical_analysis/             指標計算與現有 parameter registry
  pattern_analysis/               pattern 計算
  signal_analysis/                數值／訊號分析；舊 backtest 只在相容入口
decision_module/
  recommendation/
    contracts.py                  RecommendationItem、CandidateAssessment、Reason
    evaluate.py                   純篩選→score→rank→selection 流程
    filters/                      filter implementation 與明確序列
    ranking.py                    既有 ranking policy 的單一 owner
    reasons.py                    穩定 reason code、category、參數與解釋規格
  factors/                        因子值與貢獻，沒有 vendor／DB mapping
  strategies/                     StrategySpec、Executor、registry、策略實作
  market/                         regime／市場語意規則，資料由 caller 提供
  advice/                         bounded Advice policy、契約與拒絕輸出規則
  watchlist/                      候選／trigger 契約與純規則
backtest_module/                  訊號→成交→現金／部位→績效；策略為輸入
portfolio_module/                 帳務／allocation／health／exit 純政策與契約
ml_module/                        現有 feature／label／training／inference 契約先保留
app_module/
  recommendation/
    contracts.py                  request、完整 execution envelope、保存結果引用
    execute.py                    資料準備、domain 呼叫、品質與 projection 組合
    save.py                       明示保存與後續 watchlist／delivery 結果
    queries.py                    依 exact identity 讀保存結果
    ports.py                      此 use case 真正需要的 provider／store 介面
  research/                       replay／backtest／registry／比較 use cases
  evidence/                       capture／maturity／review／journal use cases
  portfolio/                      讀帳務、產生 policy proposal、受控保存
  market/、watchlist/              查詢與業務 use cases
  reporting/                      保存結果→報告 read model→export
  jobs/                           data update／technical publication／scheduled commands
  adapters/
    persistence/                  recommendation／research／evidence 等應用結果儲存
    factors/                      data observation → domain factor 的 mapping
    ml/                           唯一受控 ML read／inference／permission adapter
  composition/                    實際 providers、repositories、services 接線
ui_qt/                            views、presenters、workers、theme；呼叫 application
runtime/                          執行治理／營運事件；不定義金融規則
scripts/、mcp_servers/             CLI／排程／唯讀工具入口，呼叫 application
development_module/               隔離研究 orchestration，不進正式 import 鏈
```

### 現有資產如何落位

| 現有責任／入口 | 目標 owner | 不變事項 |
|---|---|---|
| `recommendation_service.py` | 薄相容 façade → app execute＋decision evaluate | 參數預設、評分與排序、錯誤語意、公開舊 caller 過渡支援 |
| `recommendation_ranking_pipeline.py` | decision recommendation ranking | fixed／quantile 與母體、nearest-rank、tie-break |
| `recommendation_run_support.py` | decision assessment／reason，wire 映射移 persistence codec | 舊 negative evidence JSON 可讀 |
| `dtos/__init__.py` 的 recommendation rows | decision canonical item；app execution aggregate 持有它 | 原 import 短期 re-export，禁止新增一份獨立欄位清單 |
| `recommendation_repository.py` | app adapters persistence | 原資料位置、result IDs、legacy decoder／保存規則 |
| `decision_data_providers.py`、`decision_service_composition.py` | data readers＋app composition | 注入模式與 source policy，不再各 service 隱式建 provider |
| `strategy_spec.py`／`strategy_registry.py`／executor adapter | spec／純 registry 在 decision；執行協調留 app | strategy ID／version 與 DailySignalFrame 相容 |
| app 中 Advice／Portfolio／Position Health policy | 純 policy 歸 decision／portfolio，use case 保留 app | action、bp、thesis／ledger identity 與權限 |
| `report_export_service.py` | app reporting | 原 export 欄位與原子輸出；report 不重算核心結果 |
| `runtime_composition.py` | 啟動接線可維持於 UI 外殼，日後共用 app composition | runtime 不反向 import Qt，也不提升 writer 權限 |

命名不是架構完成證據。允許先在現有檔案建立同樣邊界；目錄搬移在責任完成後進行，不做無價值全庫改名。

## 3. 可執行的依賴規則

「資料流方向」與「Python import」不同：writer 在執行時接收結果，但 domain 不因此 import writer。ports 僅用於可替換 I/O 或實際跨邊界能力；純計算直接呼叫函式，不為每個類別製造 interface。

| 呼叫方 | 允許的直接依賴 | 禁止 |
|---|---|---|
| `financial_module` | 標準庫／精度 primitives | app、data、ML、Qt、DB |
| `data_module/contracts` | 標準庫、financial | reader、writer、domain engine、app；import 時 I/O |
| analysis 純計算 | financial、data leaf contracts、numpy／pandas 的明示數值邊界 | DB、HTTP、app、Qt、scheduler |
| decision／portfolio 純 domain | financial、data leaf contracts、analysis 公開計算；同域 leaf contracts | data reader/writer、sqlite3、HTTP、app、Qt、training |
| backtest core | financial、strategy／portfolio leaf contracts、既有分析輸入 | recommendation service、UI、repository、最新來源查詢 |
| app contracts／ports | 相關 domain／data leaf contracts；ML 只用審查後 leaf types | concrete adapter、Qt、bootstrap、job |
| app use cases | 自己的 contracts／ports、domain 公開能力 | Qt、scripts、自行建立 DB／HTTP；跨 use case 的私有 helper |
| data source/read/storage adapters | data contracts、financial；必要 domain/ML leaf record contract | app services、CLI、Qt；不得以 storage adapter 實作 ranking |
| app adapters persistence／ML | app leaf contracts／ports、資料 storage、明示 ML inference/read bridge | app execute／UI；ML 訓練不能因 UI 查詢觸發 |
| app composition | 上述元件的 concrete constructors | 金融演算法、全域 mutable result |
| ui_qt views／presenters | application 公開 API／DTO、Qt | domain engine、DB、ML producer、欄位級業務重算 |
| scripts／mcp／runtime 接線 | application commands/queries、runtime contracts | application 反向 import scripts；runtime 自行交易／核準 |
| development_module | 受控公開 contracts、隔離研究 adapter | 被 production decision 反向 import |

ML 的現有 data↔ML 交互不在第一輪硬搬；以 [相容計畫](ML_COMPATIBILITY_PLAN.md) 列明 scope。最終方向為 data readers/stores 提供 frozen records、ML compute 消費它們、app ML adapter 讀 validated projection；只容許 leaf contract 互用，不容許兩個 orchestrator 互相呼叫。

**執行方式**：擴充既有 AST guard，區分子套件與 exact symbol，禁止新反向邊；檢查 top-level、函式內 import、relative import 與已知動態入口。凍結例外記錄 path、symbol、owner、退出步驟，不加整包 allowlist。再用 fake port／禁止 I/O 的單元測試驗 domain purity；用 UI／CLI integration 驗實際接線。guard 只能證明靜態子集，不能冒充 runtime 隔離。

## 4. 一次執行的公開邊界

### 權威契約

沿用並演進現有 `RecommendationResultDTO` 的完整結果角色，不再平行建立 ResultDTO／SnapshotDTO／ReceiptDTO 各自複製推薦欄位。下列名稱表達目標責任，最終可保留既有類別名稱與 re-export。

| 概念 | Owner | 必要內容與規則 |
|---|---|---|
| `RecommendationRequest` | app recommendation | frozen config／profile version、cutoff mode、universe、max_stocks／top_n、已宣告 result_id、來源／權限範圍 |
| `RecommendationItem` | decision recommendation | 現有推薦欄位、score breakdown、選取原因；新增業務欄位只在此定義一次 |
| `CandidateAssessment` | decision recommendation | symbol、stage、pass/fail/skipped/missing/degraded、Reason、observed/required values；涵蓋未入選 |
| `RecommendationExecution` | app recommendation | identity、時間／mode、frozen request、items、assessments、market context、quality、events、source／evidence refs、版本與 fingerprints |
| `PersistenceReceipt` | app persistence port | result identity／payload hash、位置、狀態、persisted_at／錯誤；**只引用結果，不複製 items** |
| query／UI read model | app queries／presentation | 已保存或此次完整 execution 的投影；有 source result identity；不成為第二套業務 owner |

Execution aggregate 包含的是外部有意義的業務結果與 provenance；timer、Qt object、connection、logger、cache、progress callback、取消 token 留於 request-scoped 執行控制，不序列化。凍結須對巢狀 collections 用 tuple／不可變 mapping 或防禦複製，不能只加 `frozen=True` 留共享 list。

業務本身需要的歷史狀態不禁止：regime 的確認／cooldown、portfolio position、ledger、lifecycle 都有明確 owner。它們以 `PriorRegimeState`／既有 portfolio snapshot 等顯式輸入參與計算，產生 state transition／update，由 application 依既有寫入政策保存；不是把歷史狀態藏回共用 service。過渡時保留原 state file、內容、更新時點與 hysteresis 行為。

### Identity 與狀態

- `result_id` 沿用現在推薦產生的 `rec_<uuid>`，執行前配置，執行／projection／保存／重讀一致；不為同一推薦再造無必要的 competing `run_id`。
- 若 CLI wrapper 有 `run_id`，把它記成 `invocation_id`／parent reference；research replay 的每個日期結果是 child identity。Evidence event／snapshot／journal／ledger 各保留原 ID，以 typed reference 連結，不把它們全部改成推薦 ID。
- `request_id` 是 UI callback correlation，可與 result ID 關聯，但不是保存主鍵。重試保存沿用相同 result ID＋payload hash；重新計算是新結果並記 parent，不能用同一 ID 靜默替換內容。
- execution status 分開 `completed`、`failed`、`cancelled`；quality 分開 observed／estimated／degraded／missing。完成但零候選是合法結果，不能和 exception／cancel 都當 `[]`。
- 驗證不合法 request 在開始前拋 typed validation error；開始後各 terminal outcome 都帶 result identity 與已產生 events。failed／cancelled 不發布可採用推薦；保存診斷若被授權，須另列 terminal status。
- decision_at、資料 as-of、source available_at、started/completed、persisted_at 分欄保存。不能用保存時間替代決策時間；缺舊值保留 unknown。

### 執行與保存

```text
execute(request, cancel/progress) -> RecommendationExecution
save(execution, user_label)       -> PersistenceReceipt
load(result_id)                   -> 已驗證的同版本 execution + receipt
```

execute 只呼叫既有 domain policy；calibration 的 immutable projection receipt 寫入是目前已存在的外部副作用，須由 app ML adapter 明示執行，將其保存狀態併入 execution。不能假裝 execute 全部純函式，也不能為了整齊而取消目前先發布 receipt 的保護。

結果保存仍是原有明示 UI／CLI 操作；不得在遷移時改成所有 run 自動寫入。watchlist、personalization delivery ACK、journal 是後續獨立 command，有各自 outcome；主結果成功、ACK 失敗要保持可辨識，重試不得重算推薦。

舊 `run_recommendation() -> list` 只作同一 engine 的 adapter。過渡期若 caller 仍讀 `last_*`，限一次 invocation 專屬 façade／序列化 capture，立即 deep freeze 成完整 execution；禁止把共用 service 的 latest 狀態當新 API。新 caller 全部遷移後移除 last-state API，不保留第二個推薦實作。

## 5. 欄位權威與 mapping

| 內容 | 單一權威 | 邊界轉換 |
|---|---|---|
| raw vendor field、unit、available time／revision | data source contract | 各 source adapter 一次轉 SourceObservation／MarketSlice |
| 技術指標公式、參數、warmup、名稱 | analysis technical registry／calculator | 資料儲存 mapping 留 data，策略只取已定義輸出 |
| recommendation score／因子／filter／reason | decision domain | CandidateAssessment 是 Why Not／liquidity 的唯一來源 |
| strategy spec／version | decision strategies | app profile／registry service 管保存與 lifecycle，不能私有重定義 |
| run identity／cutoff／品質彙總／provenance references | app execution aggregate | 一個 result codec 編解碼；不由 UI 組建保存 DTO |
| persistence wire／DB index | app persistence adapter | 明確版本 dispatch、欄位 alias、缺值／舊值解讀集中 |
| Advice／allocation／health／ledger | 各 domain owner | application 組合，projection 不補算權重或授權 |
| ML feature／label／transform／artifact schema | 既有 ML/data producer contracts | 外側 compatibility adapter；完整規則見 ML 分冊 |
| UI label／column order／format | presentation | 只引用 contract field，不產生新核心欄位 |

同一 recommendation row 不再有第二份人工維護的 persistence row／snapshot row。DTO 的版本 codec 集中在 owner 旁的 storage adapter；所有存讀與舊 JSON 轉換都經同一路徑。少數 SQL 索引欄位是可重建 projection，不是第二份業務真值；新增搜尋欄位才做 additive DB migration。

一般 scalar 新欄位使用明確 typed optional field 與顯式缺值。可枚舉的 factor contributions 使用 `factor_id/version/value/unit/quality/evidence_refs` 的 typed entries，不能以 `dict[str, Any]` 逃避 schema。display metadata 可減少格式重複，但不從資料自動生成一切 UI，也不建立全域超大型 field registry。

## 6. 其他主要子系統

- **Data acquisition/update**：job 協調 fetch、validate、compute、publish；source adapter 不做推薦。保留候選／正式 root、SQLite-first、fallback policy、修訂 marker；新增來源不自动取得 scoring eligibility。
- **Backtest/research**：app 準備同日可得 snapshot 與 strategy，backtest core 消費 DailySignalFrame／成交假設；registry 保存 config、cost、benchmark、結果與證據。Portfolio replay 不變成今日名單的批次回測。
- **Portfolio/Exit**：帳務與 policy 分離；source lineage 連推薦／研究／user_declared，純 policy 不查 DB；actual fills 與 hypothetical outcomes 不混合。
- **Evidence/Journal**：append-only 適用於已承諾的證據記錄，不宣稱所有 legacy Journal API 都 immutable；capture、maturity、review、promotion 是不同 application commands。
- **Reporting/AI/MCP**：query 讀同一已保存結果，報告／AI 只呈現與引用；不是 scoring 或 trading owner。
- **Runtime/scheduler**：job identity 與 result identity 以 reference 連接；保留 bounded retries、取消、latest／immutable receipt 分工。啟動接線可以接 concrete services，runtime core 不依 Qt，不放交易政策。
- **ML**：只從受治理輸入訓練或推論；rule top-N 不因這次架構改動被 calibration 改排。模型 quarantined、missing、unverified 時按原 policy 降級。

## 7. 設計取捨與自我審查

| 自查問題 | 結論與修正 |
|---|---|
| 只是重新排資料夾嗎？ | 否；首個驗收是跨 run isolation、frozen save、domain 無 I/O，搬檔不是首要 deliverable |
| 過多 interfaces/managers/factories？ | 只留 provider、result store、ML projection 等真正 I/O seam；使用現有 composition，純函式不用 factory |
| 加一欄仍改十幾檔？ | canonical row＋單一 codec＋指定 display，詳見 A/H；不再改 execute/replay/save 每條手工搬運 |
| 轉換重複嗎？ | legacy DTO／JSON mapping 集中；各 domain 的不同語意仍允許明示轉換 |
| owner 明確嗎？ | data事實、analysis數值、decision選取、app執行、storage wire、UI格式、ML schema 各自唯一 |
| 新開發者找得到入口嗎？ | 以 A–J 表反向定位現有入口與目標路径，並列不應修改處 |
| 歷史／ML 被失效嗎？ | 原 bytes/hash/IDs 不动；尤其 ML 路徑 fingerprint 先凍結，不在通用重構中搬 |
| 永久新舊雙架構嗎？ | 單一 evaluator；每個 runtime façade 有移除條件，歷史 decoder 可保留 |
| 為假想擴充過度設計嗎？ | 不加 plugin bus、全域 registry、通用 repository、微服務；filter/factor/strategy 只用現有註冊機制 |
| 心智模型更簡單嗎？ | 開發者沿 request→prepared inputs→evaluate→execution→save/query→view 找到 owner，不追 last_* 與 UI 暫存 |

剩餘限制：凍結的 ML/data 大型檔案在第一輪仍存在，不能把外側隔離稱為整個 ML 已重構。這是明確的相容取捨，有獨立退出 Gate；不以永久複製 trainer 解決。

## 更新記錄

- 2026-09-22：建立單一工程目標架構、契約、責任與依賴規則；全部為待實作設計。
