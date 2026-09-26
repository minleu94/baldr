# 系統架構

> **最後更新：2026-09-25｜目前程式結構；不代替運行狀態。**
> `release_v4` 是 storage／engineering namespace，不等同正式 V4.0。配置 ML、Rule／ML bp 混合、風險投影、Decision／Evidence 與 Paper ledger 的責任邊界如下。Formal input 計數、ledger 是否已產生、scheduler 是否啟用、D 剩餘容量均是可變運行事實，須讀 Snapshot 與當次具 hash／時間的驗收產物；不再以本架構檔的舊值作現況。Live broker execution 不在此系統範圍。

## Recommendation calibration prepared runtime 與 typed handoff（2026-09-25）

`RecommendationService._apply_recommendation_calibration` 在 exact `RecommendationCalibrationConsumer`、明列 NP1／NP2 runtime profile 與同次 capability 成立時，預設以 `PreparedMLRuntimeInputV1` 投影；自訂 consumer、未支援 profile 或 capability 無法成立時，沿用相容 `project_many()` 路徑。NoModel identity 只表達同次 fresh reload 真正回報 `rule_only` 且 `_model is None` 的狀態，不能由 active capability 失敗推定。Rule 與 ML snapshot identity 分別保存；runtime input 攜帶同次特徵、決策時鐘、候選與 source-contract evidence，projector 不讀 SQLite、網路或檔案。

校準後的可用性、receipt binding、projection 與 event facts 由 invocation-local `RecommendationPostCalibrationHandoffV1` 傳給 execution assembly；既有 receipt bytes 與 event/result 契約保持不變，handoff 不新增 serialized `RecommendationExecution` 欄位。這些 typed facts 由本次 producer 建立，執行層不從 R011 generic capture 或已發布的 legacy service state 回讀 ML truth。Root 已接受 R026 exact consumer、明列 NP1／NP2 profile 與同次 capability 的 bounded runtime migration，`TMP-ML-01` 對此支援集合已關閉；custom／unverified profile 保留既有相容路徑，不宣稱全部 runtime profile 已驗證。

C2 current union 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`，其中 Update SQLite teardown `WinError 32` 仍保留為該次歷史例外。C3 首次 union 的 4 個失敗均保留原始收據；UI fixture 後續指定 route 為 22 passed，R026 exact-import guard 後續 route 在 584 files 上回到既有 11 diagnostic occurrences，30 passed／2 failed 僅涉及原 aggregate assertions，baseline 有具名 owner。C4 full union 為 2,446 passed／2 failed／5 skipped／35 warnings，640.25 秒、exit 1；root 裁定 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`。兩個失敗是既有 shadow-boundary CLI／repository aggregate assertions；584-file scan 為 11 occurrences／10 distinct diagnostics，仍由具名 owners 追蹤。471 個 route inputs 前後 hash 未變（SHA-256 `CBE8B12FE5EF41DFFC58EE4F118BD1CF5BA3186A4A56DFD2EC84CBCB6AE016FF`）；log `C:\Users\archi\AppData\Local\Temp\c4r_de0d7b\pytest.log`，SHA-256 `88797C7C2476576D771E88099E0016D49C10A78D29B0494B2A3CE834A8CF29F9`；route SHA-256 `3E7CF99F6CB2133D5B019B8E99C305FAC1CF386E973210CA49D7490F57358E72`。C4 mandatory Workbench／Update／mypy／compile／diff gates亦通過；C4 Update validator 的成功不回寫 C2 原始結果。R031 有限工程範圍已完成並保留 named boundary baseline／blocked owners，不代表整體重構、正式資料或 production acceptance。詳見 [R026 實作報告](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R026_IMPLEMENTATION_REPORT.md)、[R026 shadow-boundary follow-up](../06_qa/ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md)、[R031 closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)、[C2 mandatory gate receipt](../06_qa/C2_MANDATORY_UI_STATIC_GATES_20260925.md) 與 [C4 mandatory gate receipt](../06_qa/C4_FINAL_MANDATORY_STATIC_GATES_20260925.md)。

## 行情來源修訂與衍生資料發布（2026-09-23）

日常大盤更新由 `official_market_daily.py` 統一解析證交所 FMTQIK 成交股數與 MI_5MINS_HIST 真實 OHLC，按日期與收盤價交叉核對後發布；缺少來源即停止，不由收盤價合成開高低。TPEx 個股缺 OHLC 同樣保留缺值，即使有非零成交統計也不補價。

受控來源修復涵蓋價格、大盤、補回完整歷史交易日與錯日排除。`daily_price_revision_write_guard.py`、`formal_market_revision.py`、`historical_session_revision.py`、`excluded_daily_price_revision.py` 在正式 writer 刪除／替換前檢查已核驗欄位及必要 key，並拒絕重匯官方已證明無行情的日期／代號。整表替換保留原 schema／索引，與全部批次寫入共用交易，失敗回滾。晚到來源的觀測時間與歷史交易日分開保存，ML／PIT gate 不將修訂後歷史冒充當時已知。

`daily_price_source_revision_overlay.py` 每輪載入一次已核驗的價格／交易日／排除證據，供正常與舊版每日合併入口同步 derived CSV；即使沒有新 raw，也可套用來源修訂。處理使用日期 mask，只將少量修訂列轉成 records，不全量載入 Python row dictionaries。原始日檔仍保留；合併產物的 sidecar 保存修訂版本及移除筆數。`repair_formal_daily_cache.py` 則從已核驗的 immutable 日價 snapshot 串流重建完整 17 欄整合快取，將 CSV 與 source receipt 作為同一可恢復發布單位。

全歷史技指修復使用 `repair_formal_technical_data.py` 協調唯讀 SQLite snapshot、`technical_cache_rebuild_stage.py` 的逐股完整因果計算與 CSV 串流 staging。更新 20 個既有因果指標及指定 CSV 的中文 OHLCV；已核驗的錯日 key／整日休市列從衍生快取移除，其餘非目標欄位和無來源的舊 key 保留並列入驗收。staging 綁定排除範圍與 plan／receipt identity，不能以同範圍不同證據替換來源。備份、來源／before／after hash、維護鎖與 journal 綁定正式發布及中斷恢復；後續來源或目標漂移時拒絕覆蓋。這是離線資料維護，不在 UI 開頁時執行，也不修改模型輸入 schema、模型權重或啟用設定。正式執行範圍與回復入口見[正式資料修復](../06_qa/FORMAL_DATA_REPAIR_2026_09_23.md)，日常判讀見[操作手冊](../07_guides/APPLICATION_MANUAL.md)。

研究資料引用的官方月報按每個月份自己的截止日核對真正取得時鐘。已完成月份可沿用較早封存回應；較新的九月來源不會改寫歷史回應的日期。修復後候選的快照、官方回應與正式來源修訂證據共同建立新版本，驗收見[修復來源候選](../06_qa/REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md)。

`formal_technical_raw_alias_repair.py` 另負責技指表與 CSV 中買賣價／量、本益比、漲跌價差六個日價複本。依同日權威來源還原數值與缺值，僅將官方買賣報價 `--` 轉為衍生欄位 NULL，合法千分位以 Decimal 驗證；原始日價文字保留。prepare／stage／audit／apply 分開保存來源、全量前後值、非目標指紋與可恢復 journal，SQLite 六欄共用單一交易，CSV 逐檔保留備份。

套用六欄修復後，DBManager 與 UpdateService 的整表／日期替換、增量寫入及技指發布在寫入前核對來源；增量呼叫省略六欄時從同 key 日價補齊，有值但不符時拒絕。完整重算採既有日價證券範圍，保留五、六碼證券，來源查詢使用 key 索引與批次 staging。舊逐股腳本在任何 CSV 修改前停止並指向正常更新入口；CSV 遷移先完整驗證、再以單一交易替換。這些檢查只在資料寫入邊界啟用，不在研究頁讀取時掃描全市場。

`ml_restatement_research_candidate_source.py` 核驗本輪固定來源 profile，`build_ml_restatement_candidate.py` 再交既有 v3 builder 重建研究資料。原 v3 預設來源不變；新路徑必須提供完整 profile，將其檔案 hash 納入 dataset identity，消費者重驗來源和修訂證據。H5 的股票特徵從不可變更日價前綴計算，不讀快照中尚未發布的新技指；取得時間維持實際修訂鐘。來源檢查與全量重算只在離線候選工作執行，不加入日常 UI 開頁流程。

## 個股研究、資料新鮮度與持倉證據邊界

- 持倉與觀察清單透過共同 `stockResearchRequested` 導向 `StockResearchReportDialog`。`StockResearchReportReadService` 組合既有SQLite、保存推薦與持倉服務，再交 `StockResearchReportDTO`／Qt view呈現；不在UI新增第二套股票評分或交易引擎。
- `app_module/decision_presentation.py` 定義 `decision-presentation.v1` 共用唯讀呈現契約。`DecisionPresentationService` 只適配既有 Market Focus、Watchlist Analysis、Recommendation／Portfolio Advice、Condition Monitor 與 Position payload，供 Decision Desk、Watchlist、Portfolio 與 Stock Research Report 共用；它保留排名分數、百分位／方法與樣本 metadata，但不查 SQLite、不寫資料、不重算 scoring、機率或權重。
- 2026-09-14 的呈現增量將校準機率、成本後機率、rank／score、decision／data-as-of、horizon／sample、model／dataset／source、evidence kind 與 natural receipt metadata 留在同一 DTO；短摘要遮蔽完整 hash，Workbench 的「查看機率依據」才展開完整唯讀 lineage。`status=available` 不推導 natural validation；沒有 typed authority verifier 時自然驗證狀態保持 unknown。這是 presentation boundary，不是 authority receipt，也不新增第二套 decision／journal database。
- 呈現契約對 `calibrated_probability_bp` 採 fail-closed：沒有明確校準來源時狀態為 `research`／`unavailable`。目標／目前／差距權重只接受上游已提供的整數 bp；缺件時保留未知與 warning，不以 current=0 或 UI 相減補值。Condition Monitor 的狀態映射只是唯讀候選分類，不是 broker 或 lifecycle action。
- 個股報告使用有限唯讀查詢、可取消worker與request identity，區分股票資料期間、來源可得時間與報告cutoff；來源新鮮度應消費既有probe契約，不將月／季資料一律當每日資料。來源不足時維持可用區塊，並明示缺失。
- `ForwardMachinePolicyProducer`、候選binding、持倉行情來源producer與transition evaluator串接為提案流程；不自動核准或修改正式倉位。`scripts/run_exit_effectiveness_daily.py` 呼叫 `app_module.exit_effectiveness_producer.produce_exit_effectiveness()`，以transition與Paper ledger讀取結果，分開實際平倉與假設提案成效；沒有可得時間、執行或成熟證據時不得納入成熟成效。同模組的 `ExitEffectivenessProducer` 類別只是包裝介面，2026-09-17 靜態查核未找到外部 caller，不能以類別無 caller 推論整個模組未使用。
- 既有 `JournalService`／`JournalEntryDTO`、`EvidenceEvent`／`EvidenceOutcome` 與 `PortfolioLedgerEvent` 各自保存 journal／event／outcome／ledger identity 及 source snapshot；後續 decision journey 應先以 application adapter／crosswalk 重用它們，不能再建立平行 decision store。既有 Journal legacy delete／overwrite API 也不能直接宣稱為 formal append-only decision journal。
- 日常caller、實際產物及驗收限制見 [本輪整合驗收](../06_qa/V4_LUNA_REVIEW_AND_WORKSPACE_CLOSEOUT_2026_09_08.md)，模組存在不代表自然閉環已完成。

## 訊號分析共用與歷史相容邊界

`analysis_module/signal_combiner_support.py` 的 `SignalCombinationMixin` 是兩個歷史 SignalCombiner 共用的訊號流程：組合分析、成交量觀察與訊號合成。兩個舊模組繼續提供原匯入及初始化 hook；可靠性與回測尚未統一，也不得因同名而互換。

- `analysis_module.signal_analysis.SignalCombiner` 是 `analysis_module` 根入口所匯出的版本；可靠性映射固定，另提供方向欄位。
- `analysis_module.pattern_analysis.SignalCombiner` 依 ADX 調整可靠性；歷史回測輸出契約也不同。
- 本次只抽取 AST 完全相同的三個方法；40 組舊／新輸出 parity 與雙入口測試涵蓋這個邊界。沒有新加金融 float、改動成交時點或把既有 reliability 宣稱為預測機率。
- 兩份 legacy backtest 的金融精度／同日成交與政策差異仍是待遷移問題，不能作為正式投資結果來源。正式研究流程的回測應依應用服務及 backtest domain 的既有契約執行。

整併與其他已知依賴衝突見[本輪查核](../06_qa/PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md)。

## release_v4 配置決策工程資料流（非正式 V4.0 closeout）

```text
SQLite + raw files + governed sidecars
  -> field eligibility / file inventory
  -> annual PIT raw observations (core / enriched / research-shadow split)
  -> decision-date as-of rows + T-1 causal Paper state
  -> pack experts (Ridge/Logistic + HGB; OOF only)
  -> Meta Allocator (target/delta/risk/cash)
  -> MLAllocationProposal (int bp)
               \
Rule allocation -> integer largest-remainder blend
  -> Health/Exit + cash/symbol/sector/liquidity/turnover/lot/cost projection
  -> PortfolioAllocationResultV2
  -> AdviceComposer (action/why/why-not/risk/target/current/gap/executable)
  -> PySide6 read-only presentation + append-only evidence/paper stores

Formal promotion side path:
full-market OOC + 4+ Meta OOF folds
  -> primary / verification accounting replay
  -> independent semantic verifier
     (official calendar + production Rule + six-head Meta OOF + raw derivation)
  -> unsigned evidence -> DPAPI authority -> consumer re-verification
  -> alpha 2000 / 3500 / 5000, otherwise atomic alpha 0
```

核心依賴邊界：

- `ml_module` 允許 sklearn/numpy float，但只能在模型內部；輸入／輸出與 artifact metadata 回到縮放整數或 bp。
- `data_module` 以 `mode=ro/query_only` 讀正式 SQLite，未知欄位 fail closed；formal/shadow manifests 不可交叉。
- `app_module/portfolio_allocation_service.py` 負責相同單位的 Rule/ML 混合與硬風控，不讓模型直接改 recorded portfolio state。
- Rule Champion 的 persisted artifact／history 簽章驗證實作位於 `data_module/rule_champion_snapshot_service.py`；`app_module/rule_champion_snapshot_service.py` 僅保留相容性 facade，ML／replay／data assembly 不得反向依賴 app layer。
- `AdviceComposer` 只消費最終 allocation result；current unknown 不得轉成 0。
- replay 的帳務可重算與正式配置語意是兩個不同 Gate；`formal_semantic_validation.verified=false` 或 Meta OOF folds 少於 4 時，Promotion Builder 必須拒絕。Shadow observation 只有 `promotion_day_credit_allowed=true` 才能累積 20 日門檻。
- Formal ML input custody 由 `causal-portfolio-ledger.v1`、`rule-champion-snapshot-history.v1` 與 `pit-sector-membership-sidecar-v1` 分別驗證；ledger／Rule history 的 manifest／file hash 會從 Direct、OOC store 綁到 OOS replay input，replay consumer 仍會再次驗證，缺件時維持 blocked，不以 research／current snapshot／cash-only fallback 補值。
- scheduler wrapper 不讀 UI state。只有既有 data update、confirmed evidence repository 與 isolated Paper ledger 具有各自明確寫入範圍；無 broker adapter。

### V4 收尾增量：跨日證據身份、評估與容量邊界（2026-09-10）

- `app_module/v4_effectiveness_read_model.py` 與 `v4_effectiveness_evaluator.py` 是唯讀
  application read path。輸入依持有期間、策略設定、穩定 universe policy、成本模型、
  benchmark、return basis 與 evidence tier 分 cohort，
  每個決策日獨立取 top-k；只有 `ready` outcome 進成熟分母，`pending`／`missing`／未知狀態及
  衝突重複列保守排除並揭露 warning。所有比例以整數 basis points 輸出；read model 不寫
  evidence、不啟用 scheduler、不產生交易或 lifecycle action。CLI 可直接以 SQLite
  `mode=ro`／`PRAGMA query_only` 讀取既有 `evidence_events`／`evidence_outcomes`；新版事件缺少
  policy／snapshot 任一身份時只回報 warning，不猜測或補寫 cohort identity。每日排程推薦的固定身份
  由 `app_module/v4_evidence_identity.py` 集中宣告：策略
  `scheduled-recommendation-default-v1`、市場基準 `TAIEX`、主要 horizon `20`，以及
  `gross-close-to-close-no-cost-v1`。`RecommendationService` 另外保存穩定
  `universe_policy_id/hash` 及每日 `universe_snapshot_id/hash`；後者只作追溯與組成變化診斷，
  不作跨日 key。策略重要設定由 `strategy_config_id/hash` 綁定。no-cost identity 只表示尚未
  套用費稅／滑價／流動性成本，evaluator 會加上 `cost_model_not_cost_adjusted`，不能當作成本後有效性。
- `data_module/finmind_cashflow_candidate.py` 與 `scripts/fetch_finmind_cashflow_candidate.py`
  只保存 FinMind `TaiwanStockCashFlowsStatement` 的 numeric-only candidate rows、來源列 hash
  與觀測時間。FinMind observation date 不等同官方公告／決策可得日，故不產生 availability
  mapping、正式 SQLite 或 PIT／ML eligibility；正式使用前須由 MOPS 官方資料交叉核對。
- `data_module/backup_retention.py` 的正式 SQLite 備份／還原使用 online backup 與
  `PRAGMA quick_check`，再以暫存檔原子替換；fundamental、TPEX price、valuation 與 evidence
  migration 共用此邊界，避免 WAL 遺漏及 Windows 開啟 read handle 時直接覆蓋失敗。
- `scripts/scheduled/run_daily_data_update_quick.py` 先取得 `release_v4/.ml_heavy_chain.lock`
  的 OS reservation，再做中央 200 GiB safety reserve preflight。reservation 忙碌或容量不足時
  fail closed 且不啟動網路／SQLite writer；明確設定 `PHASE3C_CANDIDATE_DB_PATH` 才會執行
  institutional／credit candidate 更新，狀態與 history 會保留候選路徑、鎖與 preflight payload。

> **舊架構稽核基線**：2026-07-13
> **工程補充**：Advice 已是 CURRENT bounded/read-only；Portfolio 與 Position Health/Exit 是 CURRENT_ENGINEERING proposal/paper；P0 adapters 與 ML 固定 candidate/shadow。跨 repository 由 `artifact_lineage_verifier.py` 唯讀驗證，外部 Gate 仍以 `EngineeringGateRegistry` 為 SSOT。
> **跨流整合邊界**：`app_module/system_execution_blueprint_adapters.py` 只以中立 DTO／JSON composition 聚合 A～F 已有輸出，不讓 app/runtime 反向 import `ml`，也不改 `Recommendation`、Score、Advice、Portfolio 或 Exit domain。`scripts/verify_system_execution_blueprint.py` 是 fail-closed 的純 JSON verifier；它只驗證輸入契約與狀態，不觸發資料寫入、scheduler、promotion 或 production action。
> **定位**：本文件是目前模組邊界、依賴方向、資料流與高風險技術契約的架構權威。歷史遷移過程不在本文件維護。
> **Target companion**：理想目標架構、Current → Transitional → Target 演進與尚未存在的領域邊界見 [target_system_architecture.md](target_system_architecture.md)；該文件不代表目前已實作，也不授權立即建立新 package。

## 1. 系統定位

baldr 是一套可驗證、可回溯、可演化的台股投資決策系統。產品北極星見 [system_vision_specification.md](system_vision_specification.md)，Post-Refactor 產品方向見 [PRODUCT_ROADMAP_POST_REFACTOR.md](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)；本文件只描述目前架構與模組邊界。

目前已落地三個產品閉環：

1. 資料與市場狀態：Update → SQLite → Market Watch / Smart Money → 候選池。
2. 研究驗證：Recommendation → Research Lab / Backtest / Replay / Walk-forward → Promote。
3. 持倉檢查：Recommendation / Backtest → Portfolio → Condition / Chip Monitor → Journal → 回到研究。

目標中的第四閉環是 Daily Decision Desk：Market Intelligence → Daily Decision Desk → Watchlist Trigger / Portfolio Alert / Research Input。v1 已接上主 UI；唯一實例位於「市場探索 > 市場總覽」，Workbench「決策來源」只導向同一畫面，不建立第二份 widget。目前由 service snapshot 聚合，Market Breadth v1 已由 SQLite `daily_prices` provider 接線，Sector Rotation v1 已由 SQLite `industry_indices` provider 接線，Watchlist Trigger v1 已由 `WatchlistService` 與 SQLite `technical_indicators` 共同推導接線，Portfolio Alert v1 已由 `PortfolioService`、`PortfolioConditionMonitor` 與 `PortfolioChipService` 共同推導接線。

產業強弱 current-research v1 由 `app_module.industry_strength_service.IndustryStrengthService` 與 `SQLiteIndustryStrengthDataProvider` 以 query-only SQLite 組成；`ScreeningService`、Decision Desk composition 與市場總覽共用同一 service／DTO，不在 UI 重算。它固定使用 `TAIEX` session／benchmark、5／20 日可比窗口、明確 pure-index mapping 與 TWSE scope，將 leaf／aggregate 分層、coverage、來源／mapping version、資料日與 PIT 不可用狀態一併輸出；它不讀 Formal publisher／clock、不寫 DB／watchlist，也不把 current registry 冒充 historical PIT。

V4.2 C 線在這個閉環上新增 presentation-only vertical slice：市場焦點先以研究卡呈現，觀察清單讀取保存的排名／樣本 metadata，持倉與個股報告再消費同一份呈現欄位。Advice 仍由既有 Advice DTO 決定；UI 不把市場焦點或保存分數升級成正式買進／持有／減碼／退出建議。

未來 6 個月的工程方向見 [ROADMAP_6M_ENGINEERING.md](../00_core/ROADMAP_6M_ENGINEERING.md)，舊 Roadmap 移交狀態見 [LEGACY_ROADMAP_CARRYOVER.md](../00_core/LEGACY_ROADMAP_CARRYOVER.md)。

## 2. 分層架構

```text
PySide6 UI
  ui_qt/
      |
      v
Application Services / DTO / Repository
  app_module/
      |
      +--> Decision Domain
      |      decision_module/
      |
      +--> Backtest Engine
      |      backtest_module/
      |
      +--> Portfolio Domain
      |      portfolio_module/
      |
      +--> Data Infrastructure
      |      data_module/
      |
      +--> Runtime Core
             runtime/
```

依賴方向只能由外層指向內層。Domain 與 Runtime core 不得反向依賴 Qt UI。

## 3. UI Layer

### 位置

- `ui_qt/main.py`
- `ui_qt/views/`
- `ui_qt/widgets/`
- `ui_qt/workers/`
- `ui_qt/bridges/`

### 責任

- 收集參數。
- 呼叫 application service。
- 顯示 DTO、DataFrame、圖表與狀態。
- 透過 worker 執行長任務。
- 處理工作區之間的導航與來源傳遞。

### 禁止事項

- 不直接實作策略評分、推薦理由或撮合規則。
- 不直接修改正式資料。
- 不在 UI 內複製 application/domain 計算。
- Runtime UI 不得直接讀寫 Runtime store。

### 目前 9 個頂層工作區

1. 決策工作台（包含「決策來源」Daily Decision drill-down）
2. 市場探索
3. 推薦分析
4. 策略回測 / Research Lab
5. 觀察清單
6. 個股研究
7. 持倉管理
8. 數據更新
9. Runtime Observatory

`StockResearchWorkspace` 是主視窗 stack 內的單一 QWidget，組合既有 `StockResearchReportView` 與 `DecisionOutcomeJourneyWidget`；來源頁共用 `ResearchStockContextDTO` 下鑽與返回。切離工作區保留內容，換來源更新同一實例，主程式關閉同時取消兩個讀取元件。舊 `StockResearchReportDialog` 僅保留相容入口，主程式不再建立它。

完整操作見 [APPLICATION_MANUAL.md](../07_guides/APPLICATION_MANUAL.md)。

## 4. Application Layer

### 位置

`app_module/`

### 責任

- Use case orchestration。
- DTO 組裝與 UI contract。
- Repository 與保存流程。
- 資料來源選擇、fallback 與服務組合。
- 研究、推薦、回測與 Portfolio 來源追溯。

### 主要服務群

2026-09-06 閉環增量以 [八卡交接索引](C:/Projects/PythonProjects/technical_analysis/docs/00_core/DOCUMENTATION_INDEX.md) 與 [TASK-08 整合交接](C:/Projects/PythonProjects/technical_analysis/docs/06_qa/TASK_LOOP_08_HANDOFF.md) 追溯；以下新增契約已在隔離來源驗證，正式 source acceptance／writer 切換與 V4 產品成熟度維持既有 Gate。

- 更新的 [update_loop_dtos.py](C:/Projects/PythonProjects/technical_analysis/app_module/dtos/update_loop_dtos.py) 保留來源、實際日期、quality、warnings、candidate 與 read mode；UpdateService 的 status／overview／detail 查詢不寫 manifest，不建 schema。離線落地維持 broker 四欄身份鍵與指標父程序單一寫入者。
- 市場的 [market_loop_dtos.py](C:/Projects/PythonProjects/technical_analysis/app_module/dtos/market_loop_dtos.py) 統一 `decision_date`／`effective_date` 與來源品質。ScreeningService 先以決策日裁切再排名；既有 tuple／DataFrame API 保留相容。較舊有效日期降級，未知或未來資料不補零；Regime 匹配度不代表勝率。
- 推薦的 [RecommendationService](C:/Projects/PythonProjects/technical_analysis/app_module/recommendation_service.py) 先凍結行情／可得日再評分，以 query-only 讀 SQLite，產出 `recommendation-context.v1`。RecommendationResultDTO 相容保存設定、Profile、行情與實際基本面指紋、母體及 Why Not；已啟用技術因子缺值不使用中性預設。歷史產業 membership 缺 PIT 證據時明確拒用；fixed 仍預設、quantile 仍 opt-in。
- 候選池的 [WatchlistService](C:/Projects/PythonProjects/technical_analysis/app_module/watchlist_service.py) 提供 UI 股票名稱查詢與可注入的 SQLite 副本 repository；預設正式 JSON 未切換，損毀保留原檔並回報錯誤。`added_at` 截止不等於完整歷史 membership；Trigger 仍是日資料研究提示。
- [DecisionDeskSnapshot](C:/Projects/PythonProjects/technical_analysis/app_module/decision_desk_dtos.py) 的 additive `recommendations`／`source_lineage` 保存已存推薦與候選 ledger 的日期、品質與 hash。App provider 不重算推薦或帳務；缺行情的候選帳本為 blocked。完整 loop payload 保存在既有 snapshot schema 的 metadata，`generated_at` 不參與身份 hash；08-B 已注入保存推薦 provider，Workbench 重載也保留新增推薦與來源鏈；其他既有 typed section 的完整 hydration 限制仍保留。

| 領域 | 主要元件 |
|---|---|
| 推薦與市場 | `recommendation_service.py`、`screening_service.py`、`regime_service.py`、`recommendation_profile_service.py`、`profile_replay_comparison_service.py` |
| 產業強弱／市場探索 | `industry_strength_service.py`、`decision_desk_dtos.py`、`decision_desk_snapshot_storage_dtos.py`；current-research pure-index／TAIEX comparable read model，共用 `ScreeningService` 與 Decision Desk composition |
| 數據更新 | `update_service.py`、`broker_branch_update_service.py`、`sqlite_inspector_service.py` |
| 籌碼 | `broker_flow_service.py`、`portfolio_chip_service.py` |
| 回測 | `backtest_service.py`、`batch_backtest_service.py`、`optimizer_service.py`、`walkforward_service.py`、`research_result_presentation.py` |
| 推薦回放 | `recommendation_replay_service.py`、`recommendation_portfolio_backtest_service.py`、`profile_replay_comparison_service.py` |
| 保存與版本 | `backtest_repository.py`、`recommendation_repository.py`、`strategy_version_service.py`、`preset_service.py`、`universe_service.py` |
| Portfolio | `portfolio_service.py`、`portfolio_condition_monitor.py`、`portfolio_source_adapter.py`、`portfolio_construction_service.py`、`portfolio_execution_trace_service.py`、`paper_portfolio_policy.py`（V2.4 核准參數的唯讀紙上再平衡評估；不讀持倉、不寫 DB、不下單）、`paper_portfolio_time.py`（台灣市場共用日期邊界，阻擋 future snapshot／週報 look-ahead）、`paper_portfolio_readiness_service.py`（daily status／snapshot／可選 Equal Weight ledger／Paper Trade Ledger 的唯讀 readiness；缺檔不建 schema）、`paper_portfolio_weekly_evidence_service.py`（從既有 snapshot／benchmark／成本帳 query-only 重建期間化週報；缺件／future period fail-closed）、`paper_trade_ledger.py`（研究用 fill／partial-fill／cost／execution-gap 的 append-only contract；不接 broker）、`portfolio_stress_lab_service.py`（固定情境的 Decimal／研究唯讀投影；缺輸入 fail-closed）、`trade_import_service.py`（CSV 預覽、hash／欄位驗證與明確確認後的批次匯入）、`position_health_service.py`（V2.5 condition / feedback / trace 的唯讀健康狀態投影；不自動 action） |
| Strategy lifecycle / feedback | `strategy_lifecycle_service.py`、`strategy_lifecycle_repository.py`、`portfolio_feedback_service.py`、`portfolio_review_service.py`、`promotion_reconciliation_service.py` |
| Post-V1 evidence / V2.0-V2.1 workbench | `evidence_event_dtos.py`、`evidence_event_repository.py`、`evidence_event_service.py`、`forward_performance_service.py`、`evidence_source_coverage_service.py`、`historical_evidence_replay.py`、`agent_evidence_access_service.py`、`pre_v2_readiness_service.py`、`workbench_dtos.py`、`workbench_read_only_composer.py`、`workbench_replay_summary.py`、`workbench_source_service.py`、`v41_historical_method_pack.py`、`ui_qt/views/workbench_view.py`、`ui_qt/models/workbench_table_models.py`、`cross_sectional_factor_*`、recommendation screening matrix / negative evidence payloads |
| Runtime | `runtime_services/`、`dtos/runtime_dtos.py` |

`app_module` 不依賴 `ui_app`。Legacy Tkinter UI 不是目前 service 架構的一部分。

Daily Decision Desk 後續應以 application service / DTO 聚合既有市場、推薦、watchlist 與 portfolio 結果，不得在 UI 層重算 scoring、screening、broker flow 或 portfolio logic. Market Breadth v1 由 `app_module.market_breadth_service.MarketBreadthService` 與 `SQLiteDailyPriceMarketBreadthProvider` 自 SQLite `daily_prices` 唯讀推導多方 / 空方 / 持平、成交量擴散與新高新低 metadata，並在指定日無資料時以最近可用交易日降級顯示。Sector Rotation v1 由 `app_module.sector_rotation_service.SectorRotationService` 與 `SQLiteIndustryIndexSectorRotationProvider` 自 SQLite `industry_indices` 唯讀推導領先 / 落後產業、5 / 20 日變化與輪動強度，同樣以 warnings 揭露 fallback 日期。Relative Strength / Liquidity Ranking v1 由 `RelativeStrengthLiquidityService` 與 `SQLiteDailyPriceRelativeStrengthLiquidityProvider` 自 SQLite `daily_prices` 唯讀推導 5 / 20 日相對強度與平均成交金額，輸出強勢、弱勢與低流動性代碼，不在 UI 層重算；歷史不足 21 天時降級為 DEGRADED 並警告。Watchlist Trigger v1 由 `WatchlistServiceWatchlistProvider` 與 `SQLiteRankingProvider` 結合，唯讀查詢 `technical_indicators` 產生個股強度 `score_bp` 與風險 `risk_alert`，並支援日期 fallback 降級警告（quality 改為 `DEGRADED`，在 `warnings` 中標註 `watchlist_trigger_as_of_fallback:<date>`）。Portfolio Alert v1 已接 `PortfolioService`、`PortfolioConditionMonitor` 與 `PortfolioChipService`，可把條件監控與籌碼風險彙總成每日持倉警示；若籌碼資料缺失、估算或不可用，會透過 `quality / warnings` 降級揭露，不補值。Portfolio Alert Attribution v1 屬於 `PortfolioAlertService` 的輸出責任，因為只有該 service 同時看得到 position source、condition monitor 結果與 chip summary。UI 與 Risk Prompt service 只能讀取 `PortfolioAlertSummary.attributions`，不得重新查詢或重算。Why Not / 風險提示 v1 由 `DecisionDeskRiskPromptService` 從既有 section DTO 的 quality、warnings、低流動性、相對弱勢、watchlist risk alert、portfolio alert 與 application service 提供的 fundamental diagnostics 推導，提供可行動風險提示，不重算既有邏輯。Fundamental diagnostics 來源是 `FundamentalDiagnosticsService` 序列化後的 metadata；Risk Prompt service 只轉成 `source="fundamental"` 的提示並清理禁用行動語句，不 import abnormal flag policy 或 raw data。Month 4 收尾新增 `tests/test_decision_desk_ui_contract.py`，以靜態契約阻擋 Daily Decision Desk UI 直接 import scoring、screening、backtest、portfolio core 等計算模組。

Portfolio 的目前價格投影同樣屬於 application read path：`PortfolioService.get_current_price()` 先以 `ReadOnlySQLiteManager` 對既有 `daily_prices` 執行 `mode=ro`／`PRAGMA query_only=ON`，SQLite 不存在或不可讀時才降級讀取既有 CSV。打開持倉頁、計算未實現損益或查詢單一價格不得建立空 `twstock.db`、初始化 schema 或切換 WAL；這條邊界與 SQLite Inspector、UpdateService 的狀態查詢一致。

Paper Trade Ledger 與手動 Portfolio 是兩條不同的資料流：`PaperTradeLedgerRepository` 只保存明確的研究用 fill event，要求數量狀態、Decimal 成本、turnover、execution gap 與 source event；`source_event_id` 的冪等 identity scope 是 `(portfolio_id, source_event_id)`，因為來源事件 ID 可在不同 portfolio 的 namespace 合法重用，而 `fill_id` 仍是 ledger-wide primary key；Formal 單一 portfolio consumer 另行拒絕其來源內的重複事件。`PaperPortfolioReadinessService` 只用 query-only 連線驗證 schema、安全旗標與欄位完整性。它以台北交易日邊界檢查 snapshot／daily status 的 future date，保留 raw row 供診斷但只把最後一筆不超過 today 的 snapshot 投影為 current NAV／持倉；遇到 future row 時 readiness 降級且 weekly status 不可計算。`PaperPortfolioWeeklyEvidenceService` 再以同一條 query-only 邊界把期間內的 snapshot、frozen Equal Weight observations 與 cost records hydrate 成 `PaperPortfolioWeeklyReport`，明確要求期間首尾存在、`source_type` 必須是 `paper_` provenance，且缺 turnover／execution gap 或 future period 時不補 0。`build_paper_equal_weight_benchmark.py` 是另一個受控 producer，從已保存 baseline、paper snapshot 日期與 T-1 市場價格建立 frozen-constituent benchmark preview／新 ledger；若 snapshot 含 future date 會在 preview／apply 前拒絕，且不能覆寫既有 ledger。UI 或 readiness 不得呼叫 writer repository，也不得把手動 `TradeDTO`、virtual execution trace 或 snapshot mark 直接冒充成本後 paper evidence。

Healthcheck Batch 2 新增 `DecisionDeskDashboardComposer` 與 `SmartMoneySemanticService`。`DecisionDeskDashboardComposer` 只組合既有 section DTO 與可選 Smart Money summary，產生 action summary、sector focus 與 stock focus；它不重新計算 ranking、scoring 或 portfolio logic。`SmartMoneySemanticService` 位於 app layer，從 `BrokerFlowService.get_events()` 的唯讀事件快照與可選 `SQLiteSmartMoneyPriceProvider` 產生 5 / 20 / 60 日語意診斷、quantity-based 集中度、價格位置風險與資料品質 counts；Qt UI 只讀 DTO 欄位與 tooltip，不直接查 SQLite 或重算籌碼語意。

Healthcheck Batch 3 新增 `RecommendationProfileService`。該 service 是推薦分析 Profile lifecycle 邊界，負責把內建 Profile、自訂 Profile 與 Strategy Registry 中通過 gate 的策略版本 Profile 組成 UI 可選清單；自訂 Profile 保存於 output root 下的 `recommendation/profiles/custom_profiles.json`，標示「自訂，未經回測驗證」，並以 Decimal 字串與整數 bp 保存數值權威。策略版本 Profile 只讀 `StrategyVersionService.list_versions()`，僅顯示通過 gate 且未停用的版本，不刪除歷史策略版本 JSON。Qt UI 只呈現來源 label、保存自訂設定與 Profile-Regime match / mismatch 說明，不在 UI 層重算 scoring，也不把 mismatch 當成自動排除或交易建議。

V1.1 workflow bridge v1 新增 `ProfileReplayComparisonService` 與 `profile_replay_comparison_dtos.py`。該 service 位於 application layer，接收多個 Profile 與共用 replay request，透過注入的 runner 取得既有推薦回放結果，彙整 total return、benchmark excess、drawdown、trade count、quality 與 warnings，並輸出 promote / hold / demote_candidate / retire_candidate / insufficient_evidence 等人工 lifecycle candidate label。它不重跑 scoring、不直接讀寫 SQLite、不保存 Research Run、不建立或修改策略版本，也不自動 demote / retire；正式升降級仍需 Registry / lifecycle gate 與人工審核。

V1.2 Research Credibility & Execution Model v1 在同一 application boundary 內補強 replay 可信度揭露。`ProfileReplayComparisonService` 支援 training period 與 validation period 分離，且 validation start 必須晚於 training end；comparison row 同時保留 training / validation metrics，lifecycle candidate 以 validation metrics 主導，避免同一段資料同時調參與宣稱有效。`RecommendationPortfolioBacktestService` 在既有推薦組合 replay details 中新增 `rolling_risk_metrics`、`microstructure_preflight` 與 `relative_attribution`：rolling risk 只讀已產生 equity curve / holdings，microstructure preflight 只檢查 history 中可選的處置股、分盤、全額交割、漲跌停鎖死與除權息欄位，relative attribution 只讀 replay 期間 history 中可選 benchmark / industry / concept reference columns。這些 diagnostics 不改 PnL、成交價、sizing、cash ledger、Research Run 或 Strategy Lifecycle。

V1.3 Evidence Operations & Manual Lifecycle v1 新增 `EvidenceOperationsService`、`evidence_operations_dtos.py` 與 `scripts/build_evidence_operations_weekly_review.py`。該 service 位於 application layer，只彙總 `evaluate_evidence_scheduler_readiness()`、`DecisionQualityService` 與 `SignalDecayService` 的既有輸出，產生 weekly review、manual approval package、manual lifecycle candidates 與 action item planning。它不直接讀 UI state、不建立 scheduler、不改 Strategy Lifecycle state、不改 portfolio、不改 scoring；`production_scheduler_allowed` 固定為 false，Signal Decay candidate 只輸出 `apply_action=false` 的人工審核項目。Action item planning 預設 dry-run，只有 explicit confirm 才透過 Decision Quality repository append-only 建立 action item。

V1.4 Evidence Review History v1 新增 `EvidenceOperationsHistoryRepository`、`evidence_operations_history_dtos.py`、`EvidenceOperationsHistoryDashboardService` 與 `ui_qt/views/evidence_operations_history_view.py`。Repository 只以 append-only / hash-idempotent 方式保存 weekly review payload snapshot，不保存投資結論；CLI 的 `--save-history` 必須指定 explicit DB，且 production-like DB 仍需額外 gate。Dashboard service 位於 application layer，將已保存 weekly review history 轉成 cards / rows / empty state；Research Lab `Evidence Review -> 覆盤歷史` 只讀 dashboard service，不直接讀 SQLite、不建立 scheduler、不寫 action item、不自動套用 lifecycle action。

V1.5 Data Credibility & Corporate Action Gate v1 新增 `data_module/data_source_capability_registry.py`、`data_module/corporate_action_policy.py`、`data_module/microstructure_source_preflight.py` 與 `app_module/evidence_source_coverage_service.py`。Registry 與 policy inspection 是 read-only governance layer，只輸出 source capability、price policy、available-date / missing-policy 邊界，不寫 formal data、不建立 migration。Microstructure preflight helper 只把處置股、分盤、全額交割、漲跌停鎖死與除權息 candidate source 轉成 diagnostics metadata，不改推薦組合 replay 的 PnL、成交價、cash ledger 或 sizing。Evidence source coverage service 位於 application layer，讓 CLI、pipeline runner 與 scheduler readiness evaluator 共用 blocking gap / warning 分級；它使用 query-only SQLite／檔案讀取，不呼叫會建立 schema 的 writer repository；active Decision Desk snapshot 以台灣市場今日為上限，future row 僅輸出 blocker／diagnostic。why-not / liquidity / screening matrix payload 缺口是 warning / `dry_run_only`，durable persisted recommendation / DDD snapshot section 缺口才是 blocking。此層不得輸出 production-ready，不啟用 scheduler。

V1.6 Cross-sectional Factor Pipeline v1 新增 `app_module/cross_sectional_factor_dtos.py`、`app_module/cross_sectional_factor_repository.py`、`app_module/cross_sectional_factor_pipeline.py`、`app_module/cross_sectional_factor_attribution.py`、`data_module/cross_sectional_factor_migration.py` 與 `scripts/inspect_cross_sectional_factor_snapshot.py`。Pipeline 位於 application layer，先使用既有 `FactorService.build_snapshot()` / `FactorGate` 套用 `available_date <= decision_date`、quality 與 missing policy，再把通過 gate 的 `FactorRecord` 保存為 daily cross-sectional factor snapshot。Repository 建立 `cross_sectional_factor_snapshots` / `cross_sectional_factor_rows`，以 snapshot hash 做 idempotent save，row 內保存 factor value、整數 rank、quantile bp、sector / concept metadata、quality 與 diagnostics。Concept basket 只能使用呼叫端提供且 `available_date <= decision_date` 的定義；未到可得日只輸出 diagnostic，不把未來題材寫入 row。Attribution CLI 只唯讀彙總已保存 snapshot，不建立 DB、不改 `ScoringEngine`、不改推薦權重、不啟用 scheduler。

V1.7 Screening Matrix & Negative Evidence v1 延伸既有 Recommendation result / evidence event 邊界。`RecommendationResultDTO` 新增 `screening_matrix_json`，`RecommendationService` 在推薦當下保存 pass / fail / degraded / skipped / missing matrix，Qt 推薦頁保存 result 時一併寫入 screening matrix、Why Not payload、Liquidity payload、quality 與 warnings。`RecommendationEvidenceImporter` 只消費已保存 payload，產生 `screening_matrix_*`、`why_not_excluded` 與 `liquidity_gate_excluded` events；缺 payload 時回 diagnostic，不回補、不重算。`EvidenceSourceCoverageService` 與 `DataSourceCapabilityRegistry` 將 `recommendation.screening_matrix` 視為 evidence source capability，缺 matrix 只使 readiness 維持 `dry_run_only` warning。此層不改 `ScoringEngine`、不把 negative evidence 變成自動 demote / retire、不建立 production scheduler。

2026-07-06 follow-up 補齊 Recommendation liquidity evidence 的分類邊界：若 `StrategyConfigurator` 因 `min_volume_ratio` / `volume_ratio_min` 成交量門檻使個股結果為空，`RecommendationService` 會以同一套量比轉百分比語意與 `Decimal` 計算，將 matrix row 標示為 `liquidity_volume_ratio_below_min` 並寫入 Liquidity payload。這只補 source trace 與 negative evidence，仍不改 scoring、不重算舊 result、不回補歷史、不產生交易建議。

V1.8 Portfolio Construction & Execution Trace Sandbox v1 新增 `portfolio_construction_dtos.py`、`PortfolioConstructionService`、`PortfolioExecutionTraceService` 與 `scripts/inspect_portfolio_sandbox.py`。Construction service 位於 application layer，接收研究候選與資金參數，輸出 research-only allocation result；權重使用整數 bp，金額使用 `Decimal`，股數與 lot sizing 使用整數，不在 service 內新增 broker order、正式持倉或 scheduler。支援 `equal_weight`、`score_weight` 與 `inverse_volatility` 候選形狀，並以 diagnostics 揭露 max position cap、missing volatility、lot sizing residual cash。Execution trace service 只把 allocation result 轉成 `created`、`submitted`、`partially_filled`、`filled`、`rejected` 虛擬事件，事件固定 `research_only=true`、`source_type=portfolio_sandbox`；它不依賴 `portfolio_module` 帳務、不寫 SQLite、不接券商 API，也不代表實際成交。

Gate 4 的最小 Scenario & Stress Lab v1 由 `app_module/portfolio_stress_lab_service.py` 與 Portfolio UI「情境壓力」分頁提供。Service 只接收既有持倉 DTO，使用 Decimal 對快速下跌、跳空跌停、相關股同跌、最大持倉事件與流動性消失做靜態投影；缺最新價格只計算已標記子集並標示 `partial`，輪動失敗／來源中斷因缺產業曝險或來源可用性而回 `not_computable`。結果固定 `research_only=true`、`investment_effectiveness_claim=false`，不寫資料、不改持倉、不接券商。`PortfolioStressHistoryRecord`／`PortfolioStressHistoryRepository` 只在 UI／CLI 明確確認後保存 hash-idempotent 的研究快照；`PortfolioStressHistoryReadService` 以 SQLite query-only 讀取歷史並 fail-closed，不能把快照升級成正式績效或交易 evidence。

Paper Portfolio readiness 由 `app_module/paper_portfolio_readiness_service.py` 提供 application-layer read model。隔離排程預設只讀 `OUTPUT_ROOT/scheduled/paper_portfolio_isolated/latest_status.json`、`OUTPUT_ROOT/paper_portfolio/paper_portfolio.sqlite` 與呼叫端明確提供的 Equal Weight ledger，使用 SQLite `mode=ro`／`PRAGMA query_only=ON`，不建構會初始化 schema 的 writer repository。Producer 外層 receipt 使用 canonical `paper-portfolio-daily-status.v1`，隔離 scope version 另存欄位；consumer 的 legacy compatibility 必須同時通過 research-only、no-broker 與 isolated path flags，不能只比對舊 schema 字串。Service 會核對 daily status 與最新可採用 snapshot 的日期、ID、現金與總值；raw 最新列若是未來日期會加入 `paper_snapshot_future_dated`／`paper_daily_status_future_dated` blocker、從 current projection 排除並保留診斷，再把 snapshot history、benchmark observations、成本帳缺口與固定 research-only boundary 傳給 Portfolio UI／CLI；任何缺件、不一致或 future contamination 都顯示 `partial`／`degraded`，不回填 NAV、不改正式 Portfolio、不接 broker。
Paper fills 的受控輸入由 `app_module/paper_trade_import_service.py`、`scripts/append_paper_trade_csv.py` 與 `scripts/append_paper_trade_ledger.py` 提供，刻意不重用手動 `TradeImportService` 的 Portfolio DTO 寫入路徑。CSV／JSON 預覽都要求完整 execution 欄位與可驗證的狀態／數量／價格／Decimal 成本／turnover／execution gap，確認後才以 `PaperTradeLedgerRepository.append_many()` atomic append；兩條 producer 都把 source hash 綁入 `source_event_id`，CSV 固定 `source_type=paper_trade_import`，JSON 預設 `source_type=paper_trade_json_import`，且固定 `research_only=true`、`broker_order_allowed=false` 與 `auto_rebalance_allowed=false`。Paper UI 只在確認後寫成本 ledger，寫入後再以既有 readiness／weekly evidence read model 重新讀取，不修改手動 Portfolio、snapshot 或正式市場 DB。

Position Health transition proposal 使用 semantic identity v2：`position_health_transitions_v2.sqlite` 只以決策承載的 position、condition、metrics、policy 與 semantic source hashes 建立同日冪等 identity；capture time、路徑與 receipt-only file hash 留在 provenance，但不參與 proposal event id。舊 `position_health_transitions.sqlite` 維持 immutable audit，不自動搬移未核准 proposal。這個分版不授權 state transition、formal credit、broker execution 或自動 action；實質決策輸入變化仍由 repository 拒絕同 position/date 衝突。

V1.9 Read-only Agent / MCP Evidence Access v1 新增 `app_module/agent_evidence_access_service.py` 與 `mcp_servers/evidence_access_server.py`。`AgentEvidenceAccessService` 是 app-layer 唯讀查詢面，查 Evidence events/outcomes、Forward Performance summary、Research Run metadata、Live Research Gap observations 與 Strategy Lifecycle evidence；Evidence store 走既有 `ReadOnlyEvidenceEventRepository`，Research Run / Portfolio Review saved evidence 走 SQLite `mode=ro` 與 `PRAGMA query_only=ON`。缺 DB 或缺 table 時只回 diagnostics，不建立 schema、不呼叫 writable repository migration。MCP server 只包裝 service 與 permission/report template，不直接操作 SQLite；AI summary 必須引用 evidence rows、quality、warnings 與 source trace，不得寫回 DB、修改策略、下單或套用 lifecycle action。

Pre-V2 readiness inspector 新增 `app_module/pre_v2_readiness_service.py` 與 `scripts/inspect_pre_v2_readiness.py`，作為 V2.0 設計前的 app-layer 唯讀檢查面。Service 以 read-only SQLite URI / `PRAGMA query_only=ON` 直接檢查 weekly review history、Daily Decision Desk durable snapshot 與 persisted recommendation payload，以 markdown parser 檢查 multi-day dry-run record，並透過 `AgentEvidenceAccessService` 產出 read-only Agent report sample。若正式 evidence DB 尚未保存 durable Daily Decision snapshot，但同一觀察日 scheduled evidence dry-run `latest_status.json` 顯示 `dry_run=true`、`writes_evidence_db=false`、source coverage / pipeline blocking gaps 皆為空且 `scheduler_readiness_after=ready_for_manual_confirm`，source-gap item 可用 `scheduled_dry_run_latest_status` 標示為修正後歷史觀察 closeout；此 fallback 只讀 scheduled output，不回補 DB、不重算 evidence、不觸發 confirm。它不建立 schema、不呼叫 writable repository migration、不寫 evidence、不觸發 pipeline confirm、不建立 scheduler；`production_scheduler_allowed` 固定為 false，時間型 gate 不足時只輸出 `waiting_for_time`。

2026-07-06 Pre-V2 closeout 驗證採 working-copy DB + ignored output mirror：source coverage 可達 `blocking_gaps=[]`，all-source confirm smoke repeat=2 idempotent，Evidence Review UI smoke passed，read-only Agent report sample ready。此驗證不寫 formal evidence DB；weekly history / multi-day dry-run 不足時整體 readiness 仍停在 `waiting_for_time`。

Historical Evidence Replay v1 新增 `app_module/historical_evidence_replay.py` 與 `scripts/replay_historical_evidence_pipeline.py`，作為 app-layer orchestration，不取代 `EvidencePipelineRunner`、importer 或 repository。Replay service 先確認 source DB 與 replay DB 不是同一路徑，再以 `shutil.copy2` 建立 working-copy / replay DB；每日重放只選 `created_at <= decision_date` 的 persisted Recommendation result，並透過 `EvidencePipelineRunRequest.replay_context` / `EvidenceCaptureRequest.replay_context` 將 `replay_mode=historical_replay`、`source_label=simulated_scheduler`、`replay_run_id`、`replay_decision_date` 與 `replay_data_as_of_date` 注入 event metadata。`ForwardPerformanceService.calculate(data_as_of_date=...)` 只允許讀到 replay 當日以前的價格，因此 replay 中尚未成熟的 window 仍保持 pending。此 service 不建立 Windows Task Scheduler、不改 existing scheduled dry-run、不寫 formal evidence DB、不把 replay 結果升級為 production readiness。

Phase 0A reference return fix 後，`ForwardPerformanceService` 的 market benchmark lookup 採保守 fallback：event 沒有 `benchmark_id` 時使用 `TAIEX`，`market_indices` 支援 named aliases、未命名市場序列與 `收盤指數` 缺值時的 `收盤價` fallback。Industry lookup 不推估未知產業，只在 event 有 `industry_benchmark_id` 或 `sector` 且可映射至 `industry_indices` 時填入；缺 reference 時保留 `NULL` 與 `missing_industry_benchmark` warning，不填 0。這是 evidence outcome reference lookup，不改 `ScoringEngine`、推薦分數、Portfolio 或 scheduler。

V2.0 Phase 1 read-only Workbench prototype 新增 `app_module/workbench_dtos.py`、`app_module/workbench_read_only_composer.py`、`app_module/workbench_replay_summary.py`、`app_module/workbench_source_service.py` 與 `scripts/inspect_v2_workbench_prototype.py`。Composer 只把 Daily Decision Desk snapshot、Pre-V2 readiness report、read-only Agent sample 與可選 Historical Replay JSON summary 組成 `WorkbenchDashboardDTO`，輸出今日待判讀、background evidence feed、read-only Action Items、Evidence mode、market context、portfolio/watchlist summary、Daily Checklist、warnings 與固定 read-only access boundary。`WorkbenchDashboardDTO.background_evidence_feed` 只彙整既有 Daily Decision snapshot、Evidence Review readiness、Portfolio alerts 與 replay summary diagnostics；`WorkbenchDashboardDTO.action_items` 只列人工待處理事項，每列保留 `source_trace`、`degraded_reason`、`drilldown_target` 與 `write_intent=false`，不建立 repository、不寫 DB、不套用 lifecycle。`WorkbenchSourceService` 是 formal read-only source adapter：以 SQLite `mode=ro` / `PRAGMA query_only=ON` 讀取受控 `--db-path` 的 Daily Decision durable snapshot，current 查詢上限固定為台灣市場今日，future row 只輸出 diagnostics 並改用最後一筆安全 snapshot；並組合 `PreV2ReadinessService` 與 `AgentEvidenceAccessService` summary。missing DB / missing table / degraded source 只轉成 diagnostics / warnings，不建立 schema、不呼叫 writable repository migration、不寫 DB。Prototype CLI 保留 `--sample`，並支援 `--db-path` / `--decision-date` 與可選 `_reference_fix` replay JSON summary；它拒絕 replay DB 直接輸入。Composer / adapter 不讀 UI state、不寫 SQLite、不建立 scheduler、不重算 scoring / portfolio / lifecycle / backtest，也不輸出買賣建議。

V2.1 / Phase 2 Workbench MVP shell 新增 `ui_qt/views/workbench_view.py` 與 `ui_qt/models/workbench_table_models.py`，並由 `ui_qt/main.py` 以 `WorkbenchSourceService` 注入頂層 `決策工作台` 分頁。Qt view 只接受 `WorkbenchDashboardDTO` 或呼叫 `WorkbenchSourceService.inspect()`，不直接 import SQLite、replay service、scheduler、scoring、recommendation、portfolio、backtest 或 lifecycle 計算模組；table models 只呈現 DTO row 欄位並在 UI 層做中文顯示，不改 DTO raw token。畫面已呈現 status strip、今日待判讀、背景證據流、只讀 Action Items、read-only Operating Loop、Evidence mode / data quality、Daily Checklist 與 warnings / degraded source；目前已新增舊 Daily Decision、Evidence Review、Portfolio 的 read-only drill-down callback，只切換既有 tab，不觸發寫入、scheduler、回測、portfolio action 或 lifecycle action。Action Items 的 operating-loop queue follow-up 仍留在 DTO/composer/view 邊界內：`WorkbenchActionItem` 增加 `queue_group`、`source_label` 與 `sort_rank`，composer 依 severity / queue group / source type 排序，Qt model 顯示佇列、嚴重度與來源，view 只用 `WORKBENCH_LEGACY_DRILLDOWN_TARGETS` 把 `daily_decision`、`evidence_review`、`evidence_mode` 與 `portfolio_review` 對應回舊頁 callback；不讀 UI state、不新增 repository、不寫 action item 狀態。

T3 Research Console 將 Workbench `Evidence` placeholder 替換為 `ui_qt/views/research_console_view.py`。`app_module/research_console_dtos.py` 固定 fail-closed safety boundary；`app_module/research_console_source_service.py` 只讀 injected mapping 或顯式 `ResearchConsoleProjection.json`，只接受 exact development scope、literal false 的四個 canonical `apply_to_*` flags、formal OOS false、promotion false 與真正整數 alpha 0。File-path provider 以實際 projection bytes 計算 E2E artifact SHA-256；injected mapping 沒有實體檔時 hash 維持 Unknown，不再拿 dataset manifest hash冒充 projection hash。MainWindow 只從 `RESEARCH_CONSOLE_PROJECTION` 取得顯式 path 並注入 service，不掃描 development／正式資料目錄。Qt view 只複製 DTO，固定呈現 Safety Boundary、Development Pipeline、EV1–EV5／P0-13／獨立 Broker lane／Artifact Inspector，也呈現 `P0SourceControlCenterDTO` 的 13 項來源治理狀態。新增的 `app_module/p0_source_control_center.py` 只組合 versioned P0 contract、候選／證據稽核與外部注入的 decision revision；沒有稽核時仍輸出 13 列 `contract_only`，不建立 decision registry、不授予 eligibility。UI 不 import data / ML / development domain、不連 SQLite、不建立 registry、不重算 feature / label / Rule / ML / Score / Recommendation / Portfolio / performance，也沒有 apply / promote / retrain / blend / source acceptance / trading 控制。

Phase 2C / 2D closeout 另在 DTO/composer/view 邊界內新增 `WorkbenchOperatingLoopStep` 與 `WorkbenchOperatingLoopTableModel`，把 Evidence Feed、Action Items、Daily Checklist、weekly review history、multi-day dry-run、manual review note 與 scheduler gate 串成每天打開 Workbench 時可掃描的 read-only 操作節奏。Composer 只從 `WorkbenchDashboardDTO` 內既有 payload 推導 `daily_start`、`manual_queue`、`weekly_review_history`、`multi_day_dry_run`、`manual_review_note` 與 `scheduler_gate`；每個 step 保留 `source_trace`、`linked_item_ids`、`drilldown_target`、`guidance` 與 `write_intent=false`。Qt view 只顯示操作節奏 rows 與「今天要看 / 人工處理 / 等待真實時間累積」摘要，不標記完成、不寫 DB、不套用 lifecycle。Evidence Feed、Action Items 與 Operating Loop 的空狀態 / 降級狀態文案由 view 依 DTO rows 派生，空狀態不代表 gate 通過，降級狀態不補值、不重跑 pipeline。若 DTO 帶 replay summary，data quality 區塊揭露 `simulated_scheduler`、source gap / coverage、payload gap、outcome maturity、benchmark coverage、industry benchmark coverage、missing industry benchmark 與 pending future-data；`ui_qt/main.py` 只會在預設 `_reference_fix` replay JSON summary 存在時把 JSON path 交給 `WorkbenchSourceService`，不讀 replay DB、不執行 replay。Phase 2 UI / read-only operating loop 可 closeout；可變 Evidence 計數不屬於架構事實，必須回到 Snapshot 同時區分 formal/canonical credit、歷史 working-copy、owner-approved projection、pending sidecar 與 Formal credit。Replay 不得替代任一 official Gate；multi-day ready 也不構成 production scheduler approval。

Healthcheck Batch 4 新增 `research_result_presentation.py` 作為 Research Lab 結果頁呈現邊界。它只把已產生的推薦回放 summary、Train-Test report、Walk-forward fold summary 轉成 UI 文案與可靠度提示，不重跑回測、不重新抓取目前資料、不改變交易或績效計算。Train-Test / Walk-forward 樣本可靠度提示只讀交易數、Fold 數、OOS 與 consistency 等已存在結果 metadata；Registry 比較仍只讀已保存 metadata、equity curve 與 benchmark_results。Qt UI 可使用這些 helper 顯示「樣本不足，不宜作正式策略判斷」、資金使用與 Monte Carlo 語意，但不得把提示升級成交易建議、自動下單或持倉調整。

Healthcheck Batch 5 將 `OptimizerService` 的參數掃描邊界明確化：單股最佳化仍只使用 `BacktestService._load_stock_data()` 預載一次資料，並沿用 SQLite-first、缺資料 fallback CSV 的資料來源策略；並行模型仍是 ThreadPoolExecutor，UI 允許 1 到 8 workers，但不宣稱 ProcessPool 或多進程。`grid_search()` 採 bounded in-flight futures，只提交少量已啟動子任務，取消時停止提交新組合並將 `CancelledError` 視為正常取消狀態。這個變更只影響任務排程、可預期性與 UI 回饋，不改策略訊號、撮合、績效、資金或推薦計算。

## 5. Decision Domain

### 位置

`decision_module/`

### 主要元件

- `strategy_configurator.py`
- `scoring_engine.py`
- `indicator_parameter_registry.py`
- `weight_contract.py`
- `score_threshold_policy.py`
- `recommendation_percentile_ranker.py`
- `reason_engine.py`
- `stock_screener.py`
- `market_regime_detector.py`
- `industry_mapper.py`
- `flow_signal_engine.py`

### 核心契約

#### 指標參數與推薦權重

- `IndicatorParameterRegistry` 是技術指標參數 schema、alias、版本與跨欄位限制的權威。
- v1+ 啟用指標缺少必要參數、未知欄位、錯誤型態或非法值時 Fail-Closed；disabled 指標完全跳過。
- `RecommendationWeightContract` 只接受 `pattern`、`technical`、`volume` 三個非 bool 整數 bp，總和固定為 `10000`。
- `ScoringEngine` 使用 Decimal 核心加權，Regime 採最大餘額法重分配，總分以 `ROUND_HALF_UP` 量化至 `0.01` 分。

#### fixed / quantile 回測門檻

- 舊策略沒有 `threshold_mode` 時維持 fixed。
- quantile 使用單股 expanding 歷史分布。
- T 日門檻只能使用 T-1 以前資料。
- 暖機期為 60 個有效觀測值。
- 分位數參數使用整數基點。

#### 推薦橫斷面百分位

- 先固定當日 eligible universe。
- 同分股票取得相同百分位。
- 母體過小時拒絕執行，不靜默退回 fixed。
- 結果保存母體數、門檻模式與百分位 metadata。

#### Factor Layer v1

新資料不得直接硬接 `ScoringEngine`。Month 3 v1 先以 `decision_module/factors/` 建立 factor contract、registry、Look-ahead gate 與既有資料 adapters，並以 `app_module/factor_service.py` 建立 application snapshot serialization。Factor 必須具備：

```text
factor_name
as_of_date
available_date
value
score_bp
quality
missing_policy
source_version
```

Factor `available_date` 晚於決策日時必須拒絕使用。

目前 v1 元件：

- `decision_module/factors/factor_dtos.py`
- `decision_module/factors/factor_registry.py`
- `decision_module/factors/factor_gate.py`
- `decision_module/factors/factor_adapters.py`
- `decision_module/factors/fundamental_adapters.py`（Month 5 基本面 adapter contract；目前可從已正規化月營收與季度財報 records 產生 Revenue YoY / MoM / 3M trend / new high、EPS、gross margin、operating margin、ROE 與 non-operating income ratio factor records，保留 available_date / diagnostics 邊界，不接 ScoringEngine）
- `decision_module/factors/abnormal_fundamental_flags.py`（Month 5 異常基本面 diagnostics policy；只輸出 `FactorDiagnostic`，不改財報、不改 score）
- `app_module/fundamental_diagnostics_service.py`（Research metadata application boundary；序列化 abnormal diagnostics）
- `data_module/valuation_data.py`（Month 5 valuation data layer；建立 governed `ValuationObservation` 與同產業整數基點分位，不產生估值結論）
- `data_module/company_registry.py` / `scripts/update_company_registry.py`（Month 5 official company registry workflow；以 TWSE/TPEX 官方基本資料更新 `companies.csv`，維持既有 schema 並先 dry-run / backup / confirm）
- `data_module/monthly_revenue_availability_history.py` / `scripts/build_monthly_revenue_availability_history.py`（Month 5 月營收公告日 historical dry-run builder；讀 TWSE/TPEX 官方 `出表日期`、人工提供 JSON、人工保存的 MOPS 官方 HTML、新版 MOPS redirectToOld / mopsov static report，或授權 PIT 月營收公告日 CSV，輸出候選 mapping / diagnostics，不寫正式 mapping 或 SQLite）
- `data_module/monthly_revenue_snapshot_harvester.py` / `scripts/fetch_mops_monthly_revenue_snapshot.py`（Month 5 MOPS 月營收完整市場 snapshot 候選抓取器；保存 raw HTML 與營收值 candidate CSV，不產生 availability mapping、不推定 available_date、不寫 SQLite）
- `data_module/finmind_monthly_revenue_create_time.py` / `scripts/fetch_finmind_monthly_revenue_create_time.py`（Month 5 FinMind 月營收 create_time 候選抓取器；逐檔抓取 `TaiwanStockMonthRevenue`、支援 resume / rate limit / DPAPI token，輸出觀測日分組候選，不寫正式 mapping 或 SQLite）
- `data_module/tpex_daily_price_source.py`（TPEX daily close quotes 日常 / 區間 adapter；以官方 afterTrading historical endpoint 補缺少日期，輸出 `DATA_ROOT/daily_price_tpex/YYYYMMDD.csv`，交由既有 SQLite sync upsert `daily_prices`，不接 company registry 或 fundamental layer）
- `data_module/tpex_daily_price_history_plan.py` / `scripts/plan_tpex_daily_price_history_backfill.py`（TPEX 歷史日價 dry-run planner；估算來源筆數、既有筆數、新增候選筆數與失敗日期，不寫正式 DB）
- `data_module/tpex_daily_price_backfill.py` / `scripts/backfill_tpex_daily_prices.py`（TPEX 市場日價受控補寫 workflow；以官方 daily close quotes 補寫 `daily_prices`，預設 dry-run，正式 apply 需 confirm 與備份，不寫 company registry 或 fundamental tables）
- `data_module/valuation_metrics_backfill.py` / `scripts/backfill_valuation_metrics.py`（Month 5 P/E valuation metrics 受控回填邊界；預設 dry-run，正式 apply 需 confirm 與備份）
- `decision_module/factors/valuation_policy.py` / `valuation_adapters.py`（Month 5 估值 presentation boundary；只輸出相對估值區間與 factor metadata，不接 ScoringEngine）
- `app_module/factor_service.py`

Research Run metadata 可透過 `data_manifest.factor_snapshot` 與 `data_manifest.factor_contributions` 保存 factor 追溯資料。`ResearchRunService.save_run()` 在 metadata 寫入前可合併 explicit factor metadata，或由 `FactorRecord` 與 decision date 透過 `FactorService` 產生 snapshot 與 contribution summary。推薦組合回放結果會從 replay snapshot recommendations 產生初版 factor manifest；單股回測會從 `BacktestService` 已產生的 signal score 序列建立 `technical.total_score` factor records，並由 `BacktestView` 保存 Research Run 時轉交 `ResearchRunService`；批次回測沿用每檔 `BacktestReportDTO` 內的 factor records，在 legacy run 保存成功後以 `batch-backtest:<legacy_run_id>` 寫入 Research Run Registry。固定組合目前共用批次執行路徑，但 UI 會將 Research Lab mode 傳入 service，Registry metadata 以 `fixed_basket_stock` 區分固定組合 per-stock 保存結果。這些保存路徑都不在 UI 重算分數或重新抓取資料。Cross-run Comparison 只能讀已保存 metadata，不得為比較重新抓取當前資料。

長期 factor 權重可擴充到 chip / fundamental / market / risk，但目前正式 `RecommendationWeightContract` 仍只接受 `pattern`、`technical`、`volume` 三項整數 bp。擴充前必須先完成資料可得日、品質狀態與 missing policy 治理。Month 5 v1 已完成 fundamental tables、provider、adapter 與 diagnostics 的保守接入；raw fundamental CSV 仍不得直接進回測、推薦、Daily Decision Desk 或 `ScoringEngine`。缺 `available_date` 的基本面 observation 必須只回 diagnostics，不得被補成期間日期。Revenue / statement factor pack v1 只輸出 factor records / diagnostics，不補中性分數；future `available_date` 由 `FactorGate` 依 `MissingPolicy.SKIP` 跳過。Abnormal Fundamental diagnostics v1 僅標記營收與獲利背離、一次性收益風險與資料品質缺口，並作為 Research metadata / Daily Decision Desk risk prompts；不得自動扣除業外、改寫財報或調整分數。`data_module/valuation_data.py` 只負責建立 governed valuation observations 與同產業 `industry_percentile_bp`，不輸出估值結論。`decision_module/factors/valuation_policy.py` 與 `valuation_adapters.py` 只建立估值 presentation boundary。它們不得 import 或呼叫 `ScoringEngine`，不得產生 target price / fair value / upside / buy-sell recommendation，且缺少 `industry_percentile_bp` 時不得輸出中性估值區。P/B 與 P/S policy 已採 guarded ready：只接受 governed external observations 或後續明確 backfill records，不在系統內用不完整財報推導 book value、share count、market cap 或 TTM sales。

## 6. Backtest Engine

### 位置

`backtest_module/`

### 主要元件

- `broker_simulator.py`：撮合、成本、部位與台股市場限制。
- `strategy_tester.py`：策略訊號與模擬流程。
- `performance_analyzer.py`：結果分析。
- `performance_metrics.py`：績效與風險指標。

### Application orchestration

- 一般回測：`app_module/backtest_service.py`
- 回測輸入契約：`app_module/backtest_contracts.py`（BacktestService 所需的最小結構型 Walk-forward 結果介面；不含計算或持久化行為）
- UI 薄殼化續作：`BacktestView` / `RecommendationView` 的純文字規則分別委派至各自 `presenter.py`；`UpdateView` 委派多 worker 存活與 current-worker 選擇至 `worker_coordinator.py`；`UnifiedDecisionWorkbenchView` 的 review queue DTO mapping 位於 `workbench_presenter.py`；`MainWindow` 的 workspace alias routing 位於 `main_window_coordinator.py`。QWidget 仍保留 ownership、signal wiring 與既有相容方法。
- Backtest presenter 已承接完整績效摘要組裝（含 Phase 3.5 SOP、fixed/quantile diagnostics、baseline、overfitting 與詳細統計）；Recommendation presenter 已承接 profile advanced summary chain，數字字串以 `Decimal` 解析後再顯示。兩個 view 的舊 helper 名稱仍是相容 delegate。
- Update orchestration：`ui_qt/views/update/update_all_coordinator.py` 擁有 quick/safe step graph、progress、completed steps、TPEX soft failure 與其他步驟 fail-fast 規則；`UpdateView._run_update_all()` 僅取得日期並注入 service operations。實際更新／合併仍由 `UpdateService` 執行，順序與公開 result payload 不變。
- UpdateView presentation shell 使用可垂直捲動的 content widget；小於 720px 時只調整導覽方向、狀態卡欄數與操作按鈕排列，不改變 worker／coordinator／service 呼叫或 SQLite 寫入契約。
- UpdateView 的月營收與 Phase 3C 子分頁另提供受控候選入口：`UpdateService.fetch_mops_monthly_revenue_snapshot_candidate()` 只保存 MOPS snapshot／raw HTML 候選，`UpdateService.update_phase3c_candidate_range()` 只寫入明確的隔離 Candidate DB；兩者都不掛入 `update_all_coordinator`、不寫正式 SQLite，也不授予下游策略／交易資格。來源詳情查詢只讀狀態並保留 warning，不再嘗試寫入 status manifest。
- 單一資料源更新由 `ui_qt/views/update/source_update_coordinator.py::SourceUpdateRequest` 負責：daily 固定 TWSE→TPEX→SQLite→indicator 與 warnings/result aggregation，market/industry/broker 只映射既有 service call。View 只管理 radio/date widgets 與 worker signals。
- Workbench presenter 已承接 review queue、background evidence feed、action items 與 operating loop 的 DTO 狀態文字及 degraded 判讀；不讀 DB、不補值、不執行 replay。MainWindow 的八個 workspace key/label/icon 與 registration 順序由 `WORKSPACE_DEFINITIONS` 單一 immutable plan 供應，視窗仍擁有 QWidget 與 signal lifecycle。
- Smart Money composition 由 `app_module/decision_desk_composition.py::build_smart_money_composition()` 建立 semantic service 與 price provider，並沿用 Decision Desk 的 market-frame loader；失敗回傳 `service=None` 供 UI 降級。Runtime Observatory 的 composition 位於 `ui_qt/runtime_composition.py`；MainWindow 將 repo `runtime/` 與 `OUTPUT_ROOT/scheduled` 兩個唯讀 root 注入 RuntimeController，並保存 controller／bridge／view／timer 四個 Qt lifecycle references。controller 只發佈治理 DTO 與排程營運 DTO，不呼叫 task、資料更新或模型流程。
- Backtest 單檔執行 mapping 位於 `ui_qt/views/backtest/execution_coordinator.py::BacktestExecutionRequest`。同一不可變 request 同時產生 `BacktestService.run_backtest()` kwargs 與既有 `current_run_params` payload，避免 UI 內兩份參數清單漂移；不計算訊號、績效或資金數值。
- 同目錄的 `BatchBacktestExecutionRequest` 與 `optimization_coordinator.py::OptimizationExecutionRequest` 分別集中 batch 的 save/parallel/research/progress/cancel mapping，以及 grid-search 的 objective/top_n/progress/cancel mapping。View 仍擁有 ParamRange/parallel widgets、preflight dialog、QTimer UI update 與 workers。
- `walkforward_coordinator.py::WalkForwardExecutionRequest` 集中 Train-Test/Walk-forward mode、train ratio/fold months、成本/風控 kwargs 與既有 result envelope；真正 fold/T-1 切分仍在 `WalkForwardService`。
- Recommendation 執行邊界位於 `ui_qt/views/recommendation/execution_coordinator.py::RecommendationExecutionRequest`，集中 required pattern/indicator validation、`max_stocks` / `top_n` service kwargs 與 progress 訊息；View 仍擁有表單/profile state、worker 與結果 widgets。
- Recommendation presenter 亦承接推薦理由的技術／型態 keyword 高亮、觸發來源 trace，以及 Explain panel 的 score breakdown、ranking metadata 與風險文字；這些函式只讀既有 DTO/metadata，不重算 score 或 recommendation。
- Recommendation Why Not presenter 只讀既有 RecommendationDTO 與 config filters，呈現子分數差距、漲幅上下限、Regime mismatch、總分與 severity；理想值與既有 HTML token 不變，View 不再擁有此差距呈現公式。
- Recommendation 保存 Application orchestration 已提升至 `app_module/recommendation_save_coordinator.py`；`persist()` 將 recommendation result 視為必要寫入、watchlist 視為 soft-failure 副作用，回傳 outcome 供 UI 顯示。舊 `ui_qt/views/recommendation/save_coordinator.py` 路徑已移除。
- UI thin-shell gate：`tests/test_ui_thin_shell_boundaries.py` 禁止 BacktestView、RecommendationView、UpdateView、UnifiedDecisionWorkbenchView 與 MainWindow 直接呼叫 backtest/batch/grid/walk-forward/recommendation/update 等核心 execution entrypoints，並鎖定大型 presenter/orchestrator 的 delegate 尺寸。
- Recommendation input preparation：`RecommendationService` 必須由 composition 明示注入 `RecommendationInputPreparer`；`app_module/recommendation/input_preparation.py` 負責 cutoff request 驗證／解析、行情日期與 `available_date` 篩選、universe 與既有 fingerprint/context identity。每次 `execute_recommendation` 建立 invocation-local session，市場與基本面仍在原流程需要時逐步讀取，沒有全候選預取。
- Recommendation source owners：目前行情 provider 維持 `app_module/recommendation_market_data_provider.py` 的零參數 contract；`data_module/recommendation_input_providers.py` 擁有歷史行情唯讀 SQLite `daily_prices`／`technical_indicators` join、CSV `all_stocks_data_file`→`stock_data_file` fallback、PIT industry membership 與 PE source observations。月營收使用 app preparation 明示傳入的 lazy `FundamentalSQLiteProvider` factory；首次 DB missing 不建檔且不重試，PIT 讀取失敗維持 unavailable／missing fail-closed。
- Recommendation input parity：source readers 保留原 60 日窗口、`YYYYMMDD` 日期解析、SQLite 優先序、availability cutoff、修訂選擇、候選 loop 的 PE→月營收時點與 early-exit。`RecommendationService` 保留 filter/factor/ranking/reasons 與 context 組裝，但不再直接查推薦 history／PE SQLite 或自行建構市場／基本面/PIT provider。
- Decision service composition：`app_module/decision_service_composition.py` 組裝共享 `IndustryMapper`、`ScreeningService`、`RegimeService` 與 `RecommendationService`；`app_module/decision_data_providers.py` 擁有 market/industry index 的 SQLite-first、CSV-fallback transport。`IndustryMapper` / `MarketRegimeDetector` 只消費可注入 frame provider，MainWindow 不再建立這組 concrete dependency graph；相容 constructor fallback 仍保留給既有非 UI consumers。
- Domain contract ownership：`analysis_module/technical_analysis/indicator_parameter_registry.py` 是指標參數 schema 唯一入口；`decision_module/flow_contracts.py` 是 Broker/Flow dataclasses 唯一入口；`decision_module/strategies/contracts.py`、`registry.py` 與 `decision_module/strategies/` executors 是 strategy 契約、唯一 registry 與執行器 owner。舊 app strategy import paths 僅透過 `TMP-STR-01` 薄 facade 暫時相容。舊 decision registry 與 Application Flow DTO shim 已於 2026-07-12 移除，核心不再反向 import Application DTO。
- Indicator pure kernel：`analysis_module/technical_analysis/indicator_kernels.py` 提供 causal price normalization；缺值只允許 forward-fill 過去觀測值，前導缺值使用零邊界，不允許 backward-fill 未來價格。
- Scoring pure kernel：`decision_module/scoring_kernels.py` 擁有 Decimal 最大餘額法與 10,000 bp 不變量；`ScoringEngine` 保留 façade method 與公開結果型態。
- Stock screening port：`decision_module.StockScreener` 只消費 injected recent frames 與 fallback frame providers，保留強／弱勢兩條既有計算分支及輸出 schema。`data_module.stock_screener_reader` 擁有 SQLite `mode=ro`／`query_only`、daily-price/indicator JOIN、逐檔 indicator CSV，以及產業 SQLite／CSV fallback；`app_module.decision_data_providers` 提供 adapters，`decision_service_composition.build_stock_screener()` 是 concrete provider 的建立入口。Qt composition、`ScreeningService` 自建路徑與 legacy `ui_app/main.py` 均經由該入口接線。Provider 回傳 `DataFrame` 代表取得成功，即使為空也直接形成空結果且不呼叫 fallback；只有 `None` 代表 recent source 不可用，才由已注入的 fallback provider 嘗試 SQLite-first／CSV-second。Decision 層本身不建立 reader、路徑或 SQLite connection。

  | Consumer | 建立方式 | 是否仍需要 `StockScreener` self-loading fallback |
  |---|---|---|
  | Qt composition | `build_decision_service_composition()` 經 `build_stock_screener()` 建立 `StockScreener`，注入 recent 與 fallback providers，再注入 `ScreeningService` | 不需要 decision self-loading；fallback 由 data provider 明確執行 |
  | App service | `ScreeningService(config, industry_mapper)` 未收到 `stock_screener` 時呼叫 `build_stock_screener()` | 不需要 decision self-loading；仍有 SQLite/CSV 降級 |
  | QA scripts | `qa_validate_phase2_5.py`、`qa_validate_phase3_3b.py` 沿用 `ScreeningService` app factory；`qa_validate_market_loop.py` 直接建立帶測試 frame provider 的 screener | factory 路徑有 fallback；market-loop fixture 僅測 injected frame／as-of 行為 |
  | Legacy `ui_app/main.py` | 經 `build_stock_screener(config, industry_mapper)` 建立 | 不需要 decision self-loading；fallback 由 data provider 明確執行 |
  | Tests | fallback contract tests 明確注入 data providers；fast-path tests 直接注入 recent providers；composition tests 驗證 provider wiring | 依測試目的，不允許 constructor 暗中建立 concrete reader |

  Public characterization 位於 `tests/test_stock_screener_provider.py`、`tests/test_stock_screener_sqlite_reader.py`、`tests/test_stock_screener_sqlite_first.py` 與 `tests/test_stock_screener_import_guard.py`：覆蓋四個 public methods 的 injected data、成功空結果、`None` fallback、SQLite／CSV fallback、strong／weak schema、個股 universe count 與 decision import boundary。這些 contract 不調整 ranking、score、reason、日期窗口或 liquidity 規則。
- Canonical market-frame contract：`decision_module/market_frame_contracts.py` 統一 SQLite `YYYYMMDD`／CSV ISO date，並將 raw market index `收盤指數` 映射至 detector 使用的 `收盤價`；injected、SQLite、CSV paths 共用同一 normalization，不再因 DI 繞過 schema adapter。
- Application ports：`app_module/application_ports.py` 以 Protocol 定義 market frame、recommendation evidence/repository、regime、watchlist 與 Broker Branch writer seams；composition 與 coordinator constructor 不再以 `Any` 取代跨層契約。
- Broker branch update boundaries：`broker_branch_registry.py` 擁有 registry 純解析規則，`broker_branch_transport.py` 擁有 MoneyDJ request URL contract，`broker_branch_merge.py` 擁有 E/B merge plan，`broker_branch_write_coordinator.py` 擁有 daily/merged CSV write 與 merged backup boundary；`BrokerBranchUpdateService` 保留 transport fallback 與 orchestration façade。
- Update daily orchestration：`app_module/update_daily_output.py` 純解析 batch subprocess output 並產生 deterministic result payload；`UpdateService.update_daily()` 保留 source invocation、缺日選擇與 temp-file ownership。
- Recommendation ranking stage：`app_module/recommendation_ranking_pipeline.py` 只建立 immutable ranking decision plan，不接觸 repository、DTO mutation 或 UI；`RecommendationService` façade 套用 metadata 與 screening-matrix evidence。
- Market regime kernels：`decision_module/market_regime_kernels.py` 擁有 MA slope 與 Bollinger bandwidth 的 causal numeric functions；detector façade 保留資料 provider、分類、hysteresis 與 history lifecycle。
- Financial core boundary：成交成本／滑價／金額量化集中於 `financial_module/units.py`；BrokerSimulator、PerformanceAnalyzer、Portfolio core 與 RecommendationPortfolio metrics 僅在有標記的 DTO/analytics boundary 轉 float。新增 indicator/scoring/regime kernels 均受 prefix 或 Decimal/bp contracts 保護。
- Decision Desk composition root：`app_module/decision_desk_composition.py` 負責 Regime provider adapter、Market Breadth、Sector Rotation、Portfolio Alert、Watchlist Trigger、Relative Strength / Liquidity 與 snapshot builder 的可降級組裝。`ui_qt/main.py` 僅提供既有 concrete constructors、保存共用 market-frame loader 與接收 builder；數值比例在 adapter 以 `Decimal` 轉為整數 bp。
- 批次回測：`app_module/batch_backtest_service.py`
- 最佳化：`app_module/optimizer_service.py`
- Walk-forward：`app_module/walkforward_service.py`
- 推薦回放：`app_module/recommendation_portfolio_backtest_service.py`
- Profile replay 比較：`app_module/profile_replay_comparison_service.py`

### 時間軸防線

- `next_open` 的新執行契約為 `next-session-open.v2`：T 收盤建立委託，下一個有有效開盤且可交易的 session 才成交；不是曆日加一。停牌、零量、缺開盤不回退收盤價；停損停利收盤確認後再於後續開盤執行。
- 推薦同日收盤相容路徑須明選 `legacy-same-day-close.v1`；無版本舊 run 為 `unversioned`，不重寫或宣稱符合 v2。單股明選 `close` 仍屬揭露的理想化假設。
- benchmark、停損停利、標準化與篩選都只能使用決策當下可取得資料。
- Walk-forward 的 OOS 測試可用該 fold 訓練起點至 T-1 的歷史產生訊號門檻，但交易狀態必須在測試窗起點以空倉重置，撮合、權益曲線與績效也只從測試窗起點計算；`signal_context_start_date` 不得把訓練期持倉或交易混入 OOS 指標。

推薦 v2 已保存現金帳、未成交、gap／流動性診斷、期末開放部位與已實現／未實現損益；無後續 session 不合成期末清倉。成本後 Equal Weight 使用同一批 frozen selections／session，單股 Buy & Hold 使用相同撮合成本。固定組合仍是 per-stock 研究，尚非完整共享現金引擎；沒有委託簿或真實 fills，不能以本次工程結果宣稱策略有效。研究 UI 的行情經 [BacktestService](C:/Projects/PythonProjects/technical_analysis/app_module/backtest_service.py) 的 query-only loader 取得，不直接查庫。

### 金融數值防線

核心金額、交易成本、股數、PnL、持倉與風控不得新增裸 `float` 計算。使用：

- `Decimal`
- 整數股數
- 整數基點
- 分為單位的整數金額

只有明確隔離的 analytics / visualization boundary 可轉換為 float。

## 7. Portfolio Domain

### 位置

- `portfolio_module/core.py`
- `app_module/portfolio_service.py`
- `app_module/portfolio_condition_monitor.py`
- `app_module/portfolio_chip_service.py`

### 資料流

預設手動 Portfolio 仍沿用既有 JSONL；下圖的 recommendation／backtest 是人工交易的來源依據，不會把研究成交自動匯入真實 fills。TASK-06 新增 [portfolio_ledger_repository.py](C:/Projects/PythonProjects/technical_analysis/data_module/portfolio_ledger_repository.py) 與 [portfolio_ledger_migration.py](C:/Projects/PythonProjects/technical_analysis/data_module/portfolio_ledger_migration.py)，只有 caller 明確注入 candidate repository 才啟用精確 SQLite 帳本。事件只 append；撤銷新增 compensation，分／股／Decimal 費稅由 domain 重播檢查超賣、重複與現金守恆。副本 migration 保留原始 record／hash 並具冪等，未執行正式切換。

`PortfolioService.build_ledger_read_model()` 輸出 `PortfolioLedgerReadModelDTO`，含 namespace、決策日、ledger hash、positions／cash／PnL、quality／missing_inputs 與 `candidate_only=True`。讀取只選截止日已發生事件；有部位缺已提交行情為 blocked，缺 thesis／source 保留降級。backtest namespace 不得轉成 fills；paper namespace 宣告也仍需要真實 producer acceptance。

```text
manual / recommendation / backtest / strategy_version
  -> source adapter
  -> trade record
  -> portfolio domain projection
  -> position / average cost / realized PnL
  -> condition monitor / chip monitor
  -> journal
```

### user_declared 研究 lane（Increment 2）

`app_module/user_declared_holding_research.py` 與
`ui_qt/widgets/user_declared_holding_research_widget.py` 是獨立於 Paper／正式 fill
projection 的 research-only lane。使用者聲明資料保存於
`<OUTPUT_ROOT>/portfolio/user_declared_holdings.jsonl`，以
`holding_id + revision_number` 維持 append-only exact identity、CAS 修訂與封存歷史；
它不寫既有 Portfolio trade ledger，也不建立 broker／Paper identity。

研究 read model 只接受 point-in-time market／condition observations，驗證 evaluation
cutoff、as-of／available time、source quality、snapshot hash 與 historical availability
custody；缺來源或 identity 不可比較時 fail closed 為 WAIT／unknown。聲明成本只作
Decimal mark-to-declared-cost 資訊性觀察，`entry_lineage=unproven`、`fill=not_provided`、
realized PnL／calibration／effectiveness 均不在此 lane。Portfolio UI 以背景 worker、
generation discard、合作式取消與頁內 scroll 呈現，不把研究建議轉成 order。

### 來源追溯

Portfolio 記錄可保留：

- `source_type`
- `source_id`
- 推薦 Profile / Regime
- 回測 run
- promoted strategy version
- 進場分數與策略參數摘要

UI 警示只提供輔助判讀，不自動下單或平倉。

## 8. Data Infrastructure

### 位置

`data_module/`

### 核心設定

所有資料路徑以 `TWStockConfig` 為準：

```text
DATA_ROOT  -> 預設 D:/Min/Python/Project/FA_Data
OUTPUT_ROOT
db_file    -> <DATA_ROOT>/sqlite/twstock.db
```

不得在新程式中硬編碼正式資料根目錄。

### SQLite-first 與 CSV fallback

目前主要讀取採 SQLite-first，CSV 保留：

- raw 原始資料
- 完整備份
- migration / fallback
- 人工研究匯出

日常快速更新可直接同步 SQLite；安全更新同時維護完整 CSV 與 SQLite。每日股價資料源包含 TWSE `DATA_ROOT/daily_price/` 與 TPEX `DATA_ROOT/daily_price_tpex/`，SQLite sync 會讀取兩個目錄並依 `(證券代號, 日期)` upsert 到 `daily_prices`。

### 主要資料表

- `daily_prices`
- `market_indices`
- `industry_indices`
- `technical_indicators`
- `broker_flows`

正式資料表（Month 5 起）：

- `fundamental_monthly_revenues`
- `fundamental_statement_items`
- `fundamental_valuation_metrics`

未來資料表：

- `institutional_flows`
- Factor registry / values

任何新資料表接入時必須保留 `as_of_date`、`available_date`、資料品質、來源版本與 fallback / migration。既有 fundamental tables 只能透過受治理 provider / factor service 使用，不得由 UI 或策略核心直接讀 raw CSV。

Month 5 v1 已新增 `data_module/fundamental_availability.py` 集中處理公告日 / available_date 初版政策，並新增 `data_module/fundamental_availability_sources.py` 作為受治理的公告日 / available_date mapping 契約；mapping 可保留 `announced_date`、`available_date`、`source`、`source_version`，但明確拒絕把 raw 月營收 CSV 自身當成可得日來源。正式 mapping 檔案位置由 `TWStockConfig.monthly_revenue_availability_file` 指向 `DATA_ROOT/meta_data/monthly_revenue_availability.csv`；缺檔時只回 diagnostic，不自動補值。`data_module/fundamental_availability_entrypoint.py` 與 `scripts/validate_monthly_revenue_availability.py` 是正式 mapping dry-run 驗證入口，只讀取指定 mapping 檔、驗證允許來源並輸出 diagnostics / Markdown 摘要，不建立、不改寫正式 mapping 檔、raw CSV 或 SQLite。允許來源包含 manual、TWSE、TPEX 與 MOPS mapping source，但 raw CSV 永遠不是 allowed source；validator 另以 `as_of_date + 45 days` 作月營收合理揭露窗口，拒絕重新出表日或其他過晚 available_date。`data_module/monthly_revenue_availability_history.py` 與 `scripts/build_monthly_revenue_availability_history.py` 是候選 mapping 產生邊界：可讀 TWSE `/opendata/t187ap05_L`、TPEX `/openapi/v1/mopsfin_t187ap05_O`、人工提供的官方 JSON、以 `--mops-html-dir` 讀人工保存且含 `出表日期` 的 MOPS 官方 HTML，或以 `--mops-static` 透過新版 MOPS `/mops/api/redirectToOld` 取得 `mopsov.twse.com.tw/nas/t21/...` historical static report；支援期間、market、stock_code 與 output 參數。未指定 output 時只輸出 dry-run summary，指定 output 時也只寫候選 CSV，不得直接覆寫正式 mapping；MOPS HTML 缺 `出表日期` 或 `公司代號` 表格時只產生 diagnostics。2026-06-17 驗證 MOPS historical static report 的 `出表日期` 是查詢當日重新出表日，對歷史 period 會被 45 天窗口擋下，不產生候選 row。`data_module/fundamental_data.py` 則作為 raw 月營收 CSV 的唯讀正規化契約。`data_module/monthly_revenue_backfill.py` 與 `scripts/backfill_monthly_revenue_fundamentals.py` 是 raw 月營收進入 `fundamental_monthly_revenues` 的受控回填邊界：預設 dry-run，正式 apply 需 `--confirm apply-monthly-revenue-backfill` 並先備份 DB。`data_module/company_registry.py` 與 `scripts/update_company_registry.py` 是 `companies.csv` 的官方 registry 更新邊界：預設 dry-run，正式 apply 需 `--confirm apply-company-registry` 並先備份；它不寫 SQLite，也不補 daily price。`data_module/tpex_daily_price_source.py` 是 TPEX 日常 / 區間市場日價 adapter：抓 official afterTrading historical daily close quotes、保留四碼普通股有效日價、補齊缺少的 `daily_price_tpex/YYYYMMDD.csv`，再由日常 SQLite sync 寫入 `daily_prices`；它不修改 `companies.csv`、raw financial CSV、fundamental tables、technical indicators 或 scoring。背景補齊入口由 `scripts/run_tpex_full_refresh_and_technical.py` 串接 TPEX 補齊、SQLite sync 與技術指標增量，狀態寫入 `DATA_ROOT/meta_data/tpex_full_refresh_status.json`，預設不先強制跑 TWSE 全量。`data_module/tpex_daily_price_history_plan.py` 與 `scripts/plan_tpex_daily_price_history_backfill.py` 保留為歷史缺口 dry-run / 估算工具，不直接寫正式 DB。`data_module/tpex_daily_price_backfill.py` 與 `scripts/backfill_tpex_daily_prices.py` 是 TPEX 上櫃日價單日受控補寫工具，預設 dry-run，正式 apply 需 `--confirm apply-tpex-daily-price-backfill` 並先備份 DB；日常 UI 流程則優先走區間 adapter 與 SQLite sync。`broker_flows` 的資料身份鍵是 `(分點名稱, 證券代號, 日期, trade_type)`；同步前若偵測到舊 DB 仍使用三欄主鍵，`DBManager.ensure_broker_flows_trade_type_primary_key()` 會先備份再遷移，使同日同分點同股票的買超 / 賣超榜單可以共存。`data_module/valuation_metrics_backfill.py` 與 `scripts/backfill_valuation_metrics.py` 是 `daily_prices.本益比` 進入 `fundamental_valuation_metrics` 的受控回填邊界：預設 dry-run，以 `companies.csv` 產業 mapping 計算同產業 percentile，正式 apply 需 `--confirm apply-valuation-metrics-backfill` 並先備份 DB；P/E 非正數或缺產業 mapping 的 rows 只輸出 diagnostics 並跳過。`data_module/fundamental_sqlite_provider.py` 是正式 fundamental tables 的唯讀 provider，只讀 `available_date <= decision_date` 的月營收、季度財報與估值 rows，不讀 raw CSV、不寫 DB。`app_module/fundamental_factor_service.py` 串接 provider、revenue / statement / valuation adapters 與 FactorGate，輸出 factor records / diagnostics 供 Research metadata 使用，但不接 `ScoringEngine`。`data_module/valuation_data.py` 則作為估值 metric 的 governed observation layer，保留 raw metric value、available_date、quality、source_version 與同產業整數基點分位，缺分位不補值。這些模組不修改正式 raw 檔，也不把 raw `date` 推定為公告日；呼叫端必須提供 explicit `available_date` mapping，否則只回 diagnostics，不產生 normalized record。`data_module/fundamental_schema.py` 定義 SQLite schema 與 dry-run report API；`data_module/fundamental_migration.py` 與 `scripts/migrate_fundamental_schema.py` 是獨立受控 migration 邊界，正式 apply 需顯式 confirm、先備份並提供 restore helper。正式 DB 目前已有 `fundamental_monthly_revenues`、`fundamental_statement_items`、`fundamental_valuation_metrics` 三張表；月營收已回填 244,499 筆、季度財報 items 已回填 1,645,555 筆、valuation metrics 已正式 apply `2026-06-15` P/E 共 831 筆 records。TPEX 歷史日價已可由區間 adapter 補入正式 SQLite；2026-06-17 排查確認 `daily_prices` 中 `3207` 已有 `20140102` 至 `20260617`、共 2,907 筆。

### 資料完整性

- 不刪除或破壞 raw 原始資料。
- schema 變更必須提供 migration 與 fallback。
- 狀態檢查必須唯讀。
- 全量重建前必須建立備份並明確確認。

### Terra Development Dataset V0

`development_module/` 是獨立於正式資料、ML formal verifier 與 application domain 的 development-only generation 邊界。它只透過 SQLite `mode=ro`／`PRAGMA query_only=ON` 讀取 `daily_prices`、`technical_indicators`、`market_indices`、`industry_indices`；以每張表的 schema／內容 fingerprint、T-1 feature、252 日 `conservative_observed_history` universe 及新建價格 labels 產生 append-only artifact。輸出只能位於呼叫端明確指定、且不在 `DATA_ROOT` 的 development output root。2025 只可列 development fit、2026 matured labels 只可列 evaluation，corporate-action coverage 缺失固定產生 `research_only_degraded`。此模組固定 `formal_oos_allowed=false`、`production_blend_alpha_bp=0`、`zero_formal_write=true`，不得 import／修改 `locked_oos`、ScoringEngine、Recommendation、Portfolio、Exit 或 scheduler。

`scripts/build_corporate_action_availability_history.py` 與 `data_module/corporate_action_availability_history.py` 是 corporate-action PIT timeline 的 staging-only 邊界。CLI 只接受 object rows list 形式的 evidence／coverage JSON；schema 根不符即以 deterministic diagnostic fail closed。Writer 接受 explicit output root 與 forbidden roots，CLI 在環境 `DATA_ROOT` 存在時將其注入並拒絕該 root／descendant；任一 canonical target 已存在即拒絕覆寫。三件套先寫入同 root 的唯一 staging directory，完成後以 replace 發布並在 finally 清理 staging；這不宣稱跨三檔 transaction atomicity，也不把 staging artifact 接入正式 market DB、Terra V0 generation、Formal Recommendation／Portfolio／Exit／Score 或 lifecycle。

## 9. Broker Flow 與資料品質

MoneyDJ 張數榜 `c=E` 與金額榜 `c=B` 是各自獨立的 Top 50：

- 資料層使用 union 保存。
- 榜外欄位使用 NULL，不可當成 0。
- 保存方向、rank 與品質狀態。
- 進入 MoneyDJ 前先以每日股價日檔或 SQLite `daily_prices` 作交易日預檢；沒有行情證據的日期視為不需抓取的 broker-flow 日期，整天跳過。
- 更新流程優先以 HTTP fast path 直接抓取 MoneyDJ Big5 HTML；只有 HTTP 失敗或解析不到資料時才使用 Selenium fallback。流程仍採序列更新，不以多 worker 併發打 MoneyDJ。

品質三態：

| 狀態 | 意義 |
|---|---|
| observed | 原始榜單直接觀測。 |
| estimated | 由金額與有效價格估算，降低信心。 |
| unavailable | 無法可靠取得，不參與該事件數值聚合。 |

單筆 unavailable 不得污染同股票其他有效事件。

Smart Money 語意層沿用上述資料品質契約：observed / estimated 可進入 quantity 聚合，unavailable 必須排除於 concentration 分子與分母並揭露筆數。5 / 20 / 60 日視窗只取 decision date 當下以前的 distinct event dates；高檔出貨疑慮的價格位置只使用 `daily_prices` 中 decision date 前最近 60 筆收盤價。千元金額只可作為 estimated quantity 的來源，不可直接作為集中度 metric。

## 10. Runtime Subsystem

### 兩條獨立觀測平面

```text
治理 Runtime：runtime/ state + append-only events
  -> LocalFileStore / RuntimeSnapshotService / RuntimeHealthService / RuntimeEventStreamService
  -> RuntimeStateSnapshotDTO / RuntimeHealthSnapshotDTO / RuntimeEventDTO
  -> EventBus -> QtRuntimeBridge -> RuntimeView

日常營運：OUTPUT_ROOT/scheduled/*/latest_status.json
  -> ScheduledOperationsStatusService
  -> ScheduledOperationStatusDTO / ScheduledOperationsSnapshotDTO
  -> EventBus -> QtRuntimeBridge -> RuntimeView
```

兩條平面只共用 composition、EventBus、bridge 與 view，**不得互相寫入、不得由任一方推導另一方健康度**。治理 `ERROR`／`HALTED` 不表示日常排程失敗；營運 `attention` 也不改寫治理狀態機。

### 邊界與時間語意

- `RuntimeSnapshotService`、`RuntimeHealthService` 與 `RuntimeEventStreamService` 是 Runtime `IRuntimeStore` 的讀取 application services；controller 只協調它們的 DTO 發佈。
- `ScheduledOperationsStatusService` 是唯一可讀取 scheduled status artifact 的 application service；它只讀檔案，不呼叫／設定 Windows Task Scheduler，也不觸發 update、retrain、promotion 或 Paper execution。
- saved status artifact 不等於 Windows task registered／running／`Last Result`；Windows Scheduler 仍由專用 query 工具判定。
- Runtime event timestamp 不得以目前時間補造。只有 current window 內、可解析且不在未來的治理事件影響 health；歷史／未來／時間無法解析事件以 DTO scope 與 diagnostic 揭露。事件檔不可讀或部分不可解析時，health 必須 fail-closed，不得偽裝為 no events。
- core artifact 的 missing／unreadable／stale 必須 fail-closed 為 attention；非 core 不能被默認為成功。ML rule-only／promotion gate 等預期安全狀態以 guarded 顯示，不能被當成 promotion。
- Runtime event UI 只保留本次 session 開啟後的最近 500 筆新事件；底層 JSONL 仍 append-only，不因 UI 裁切而刪除。
- RuntimeView 的內容容器使用 query-only `QScrollArea`；小於 720px 時將治理 Splitter 切為垂直單欄，且所有長路徑／狀態文字允許收縮或換行。這只改 presentation，不改 DTO、事件流或任何寫入邊界。
- `runtime-state.v2` 保留 task／context read state、raw status 與 diagnostics；缺來源、非 object 或未知狀態不冒充 IDLE。既有 store 無法細分缺檔與被吞掉的讀取錯誤時，保留 `missing_or_unreadable`。
- 純 Python EventBus 位於 [app_module/runtime_services/event_bus.py](C:/Projects/PythonProjects/technical_analysis/app_module/runtime_services/event_bus.py)，訂閱回傳可重複取消句柄，Qt bridge 的 dispose／destroyed 解除訂閱。Controller 只對最近 2,000 個非空 event ID 同內容去重，衝突保留診斷；重啟 attach at tail，不執行或重試 task。byte cursor 沒有 log generation 契約，不是 durable exactly-once queue。

### 禁止依賴

- `runtime/` 不依賴 `app_module` 或 `ui_qt`。
- `app_module` Runtime service 不依賴 PySide6。
- Runtime UI 只接受 DTO 與 Qt signal，不直接讀寫 Runtime／scheduled 檔案或 store。
- EventBus 與 Qt bridge 只能傳遞 DTO，不能承擔 task invocation、狀態修復或資料更新。

詳細規則見 [runtime_observatory_rules.md](runtime_observatory_rules.md)。

## 11. 保存與研究治理

目前保存能力包括：

- 推薦結果
- Research Run Registry（單股回測與推薦回放的新保存入口）
- legacy 一般回測 run 與推薦回放 run（僅保留相容、歷史載入與 backfill）
- Preset
- Strategy Version
- Universe
- Portfolio trade / journal

Research Run Registry 由 [ResearchRunService](C:/Projects/PythonProjects/technical_analysis/app_module/research_run_service.py) 統一負責保存 owner，metadata 寫入 OUTPUT_ROOT 的 research Registry SQLite，equity curve／trades 寫入 Parquet；它與 DATA_ROOT 的市場 twstock.db 是不同儲存邊界。初始 row 原子 INSERT 為 staging／pending，再經 files_ready → committed。建構與 query 不建 schema、不 reconcile；save 顯式初始化相容 schema，reconcile 由 owner 明確呼叫。list 只投影 committed＋valid；load 再驗雙檔 hash 與版本。六階段故障與同 run_id 實際內容衝突已有隔離測試，不能只憑相同宣告 hash 視為冪等成功。

metadata 保存 frozen `execution_price`／`data_manifest.execution_contract` 與 `execution_assumptions`，不依當前 UI 重建。v2／legacy／unversioned 不互相升級；未知或矛盾版本拒用，跨版本與 cancelled／partial 結果 Incompatible，成本／稅／lot 差異為 Caution。比較只用已保存 benchmark 與資料，損毀不觸發重算或修復。

[EvidenceEventService](C:/Projects/PythonProjects/technical_analysis/app_module/evidence_event_service.py) 的 `evidence-lineage.v1` 保留 declared replay／forward／paper／live tier；無宣告維持 unclassified。Forward outcome 是 close-to-close 事後診斷，`is_execution_pnl=False`，不替代 next-open PnL，成熟也不自動升 tier。`build_review_proposal()` 以唯讀完整研究連回推薦 snapshot、event、outcome，產出 `EvidenceReviewProposalDTO` 的缺件與下一輪問題；proposal_only／零 Formal credit／禁止 promotion 固定保留。這是跨 epoch 來源引用，不回寫原 run，不新增 UI 核准按鈕或生命週期權限。

### 11.1 Immutable ML publication retention

`OUTPUT_ROOT/release_v4` 下的 PIT、Direct 與 OOC 是可重建但具 custody 的 immutable
publication，不是 raw source，也不是一般 rolling backup：

- PIT root：`ml_pit_year_shards`
- Direct root：`portfolio_ml_direct_numeric_production_v4_v2`
- OOC root：`portfolio_ml_direct_ooc_training_production_v4_v5`

每層以 `runs/<id>/manifest.json` 保存 immutable identity，root
`latest_manifest.json` 只指向 current publication。Pointer、manifest hash 與 OOC → Direct →
PIT dependency closure 必須一起驗證；不能只依修改時間或目錄大小判斷可刪。

Scheduled PIT／Direct wrapper 在啟動 worker 前做唯讀三段式 capacity preflight；相容預設 Direct
以 35 GiB 持久新增、40 GiB 暫存峰值與 20 GiB 安全保留計算 required headroom，raw wrapper
至少保留 35 GiB 持久新增與 20 GiB 安全保留。全鏈 profile 應把 safety reserve 設為 125 GiB，
將日常更新 10 GiB 與額外餘裕 15 GiB 一併納入，required headroom 固定為 200 GiB。每個 Direct checkpoint 會再重驗整數 bytes
配額；超額時保存 `capacity_preflight`／`blocked_capacity` 並在 checkpoint 停止，不建立
新的 partial publication。`inspect_ml_storage_retention.py`
只做 untruncated metadata inventory，固定 `automatic_delete_allowed=false`，沒有 archive／
delete／pointer mutation 權限。

人工 retention 只能在具名 owner 看過 exact scope 後進行，至少保留 current pointer 與完整
依賴鏈；resume／partial 被刪除代表放棄續跑、改由重算。完整歷史 run 若被 runbook／release／
QA 引用，刪除前應冷 archive，或至少建立 durable tombstone；不可改寫 append-only runbook
的舊 ID／hash。所有刪除使用 exact literal target，禁止對 `release_v4` root 或 wildcard
遞迴清除。2026-08-29 的一次性 cleanup custody 與 current pointer 基線見
[ML Release v4 Storage Retention Cleanup](../06_qa/ML_RELEASE_V4_STORAGE_RETENTION_CLEANUP_2026_08_29.md)。

容量通過只解除 worker 啟動前置，不代表 Formal input、OOS、promotion、alpha、scheduler、
technical production canary 或 broker order 通過。舊 status artifact 應保留作歷史，不能手改；
新的 current status 必須由下一個受控 preflight／run 產生。

OOC 的 `minimal_linear_shadow` 是 CLI 層的複雜度護欄：只接受單一 `ridge_logistic` 與一個
明確 horizon，先建立同 frozen rows、同成本模型的 Rule／Equal Weight 比較；`full_shadow`
才保留既有多 horizon／HGB challenger。這兩種 profile 都不改 production authority。

當 release root 具備 `release_manifest.json` 時，daily inference 可經
`app_module/allocation_release_adapter.py::AllocationReleaseAdapter` 載入。Adapter 在
joblib 反序列化後仍會核對 artifact／sidecar hash、feature order、missing policy、dataset
lineage 與 calibration；`validate_frozen_rows()` 對 OOC 與 release 的逐列 head／整數 bp
輸出做 parity，失敗就回到 Rule-only。沒有 attached calibration artifact 時，OOC 的
diagnostic calibration 不得被當成正式校準器。

Post-V1 evidence layer 由 `EvidenceEventService` / `EvidenceEventRepository` 保存 append-only `evidence_events`，並由 `ForwardPerformanceService` 計算 `evidence_outcomes`。v1 outcome 使用 SQLite `daily_prices` 的 close-to-close forward return，並嘗試從 `market_indices` / `industry_indices` 產生 benchmark / industry excess；缺資料時保留 NULL 與 warnings，不中斷整批。reference return 分為三層契約：raw forward return、market benchmark excess、industry excess；market benchmark 可在 missing event benchmark 時 fallback 到 TAIEX，industry excess 必須有 event industry id 或 sector payload 才能填入。`EvidenceSourceCoverageService` 統一檢查 persisted recommendation、durable Daily Decision Desk snapshot sections 與 optional exclusion payload 的 coverage，避免 CLI、runner、readiness evaluator 各自分級。V1.6 cross-sectional factor snapshot 以 `CrossSectionalFactorRepository` 保存每日 factor rank / quantile 與 diagnostics，供 attribution 與後續 negative evidence 使用。此層只輸出 research evidence、factor attribution 與 source diagnostics，不改 `ScoringEngine`、推薦權重、策略版本或 portfolio position。

每日 `baldr-forward-outcomes-daily` 是上述 outcome layer 的受控 producer：它在
Decision/Evidence event capture 後，以台北當日可見日期、固定觀察窗及事件數上限重新計算
成熟度；排程預設要求完整 cohort identity，缺策略／成本／benchmark／universe／horizon
的舊事件只計入 skipped 診斷，不佔用 outcome 寫入額度。只有顯式 confirm 才 upsert
`evidence_outcomes`。入口先用 query-only 連線檢查
`evidence_events`、`evidence_outcomes`、`daily_prices`，並保存 status／不可覆寫 run receipt；
缺價、未成熟、benchmark 或政策資料缺口保留 status 與 warning。此 writer 不新增事件、
不回填 cohort identity、不改 recommendation／Paper／Formal／ML 狀態，也不連接 broker。

Producer 的 bounded 選取先將未完成 `(event_id, window_days, return_basis)` 的事件排在前面，
再用完整身份查詢套用相同上限，避免新事件長期排擠舊的 60 日 pending。每輪 health receipt
另外保存最新合格事件日、cohort／決策日數、各 horizon ready／pending／missing、capture／
outcome／evaluation 時間、下一成熟日、冪等自然鍵與 blocker 分類；狀態頁只讀投影這些欄位。

`ScheduledEvidenceStatusService` 以唯讀 adapter 載入上述 producer 的
`scheduled/forward_outcomes/latest_status.json`；`ScheduledEvidenceStatusView` 與
Workbench 只投影 status、事件掃描／寫入／待成熟計數、receipt path 與寫入邊界，缺少
receipt 時保留 source gap。confirmed run 若 health 分類為
`actionable_engineering_blocker` 或 `external_source_missing`，producer 會把 health
blockers 投影到 top-level receipt，輸出 `status=blocked`／`exit_code=2`，並保存
`blocking_reason`、`next_action`、`next_maturity_date` 與 `recovery_verification`；
`waiting_for_natural_maturity` 仍是 `passed_with_warnings` 的自然時間等待。這個終端狀態
投影不改變 bounded writer 的來源邊界，重跑仍受 outcome natural key 保護。UI 不會因讀取
狀態而重跑 producer 或開啟資料庫寫入。

V4.1 A 線的 `app_module/recommendation_calibration.py` 位於同一 application research boundary，僅消費已保存的 recommendation Evidence Event 與成熟 Evidence Outcome，輸出固定 20／5 trading-day target、expanding train／calibration／untouched-test walk-forward、整數 bp probability calibration 與 benchmark／cost diagnostics。`scripts/inspect_recommendation_calibration.py` 透過 query-only evidence repository 或 deterministic sample 呼叫它；它不建立 schema、不寫正式 DB、不改 Recommendation／Scoring／Advice／Portfolio，也不把 historical replay 或 sample 結果授予 natural forward evidence credit。推薦 importer 只把未來新事件當下已存在的 indicator／pattern／volume component 轉成 bp metadata，歷史事件缺件時不回填；chip／funding、industry、PIT theme 必須另有 decision-time source contract 才能接入。

第二輪由 `app_module/v41_historical_method_pack.py` 與 `scripts/build_v41_historical_method_pack.py` 建立 research-only historical method pack：以既有 evidence event／outcome 的 query-only projection 展開逐列、逐 horizon manifest，保留 decision／available-at、label maturity、strategy／universe identity、return／benchmark／cost、source hash 與 gap codes，再重用 calibration evaluator 產生 baseline／price-volume method comparison。輸出的 `frozen_candidate_artifact.json` 是 create-only、hash-bound、shadow-only contract；current snapshot 不得冒充 PIT theme membership，缺 source／availability／成熟度時維持 blocked，且 artifact 明確禁止 production、promotion、scheduler、formal writer 與自然 forward evidence credit。

V4.2 每日推薦學習閉環由 `scripts/scheduled/run_recommendation_calibration_learning.cmd` 進入，wrapper 呼叫 `scripts/scheduled/run_daily_recommendation_learning_pipeline.py`，再由 pipeline 依序協調 quick data update、`prospective_bounded` official market-event custody、正常 scheduled recommendation snapshot 與 `scripts/scheduled/run_daily_recommendation_learning.py`。它接在同一主機 local time 05:40 的 `baldr-forward-outcomes-daily` 後於 05:45 執行；runner 仍以 `_taipei_now()` 與官方 calendar 判定資料日期，不把主機 local clock 誤當台北早盤時間。quick update 的核心學習 lane 明確傳入 `--skip-broker-branch`；TPEx 缺價、待重試日期、official endpoint 失敗與 last-known-good replay 都要由 child status／receipt 保留並向 pipeline warning／blocker 傳遞。snapshot 固定以 requested／eligible／missing／degraded cohort 供 learning child 消費；每日 cohort 的 `run_scope`／`capture_scope` 可變，但固定 `experiment_scope` 不變，manual／explicit symbols capture 不得被正常 cohort 重用。child timeout 是可恢復狀態且不刪除既有 durable receipt；pipeline timeout 會為尚未執行的 step 留下 blocker，snapshot 不可用時不啟動 learning。

`app_module/daily_recommendation_learning_runner.py` 負責 frozen challenger、recoverable retry、authority receipt 與 fail-closed pointer；`ml_module/recommendation_historical_replay.py`、`recommendation_calibration_training.py`、`recommendation_calibration_evidence.py`、`recommendation_natural_outcome_service.py`、`recommendation_calibration_authority.py` 與 `app_module/recommendation_calibration_consumer.py` 分別處理 bounded training、自然 capture／maturity、同樣本比較、active monitor、promotion／rollback 與唯讀 consumer reload。`recommendation_source_contract` 不僅檢查宣告旗標，還要驗實際 symbol-scoped rows 的 canonical digest、期間／symbol coverage、feature builder 實際使用的 technical `available_at <= decision`、technical computation receipt，以及 corporate action custody；raw label window 遇未調整的 non-unit action 時保守排除受影響列並保留 blocker。after-cost 只使用可追溯、具 fill lineage 的 observed liquidity cost 與獨立 baseline；固定 50 bp 估計不能當成 observed，actual execution／broker lane 仍不在本流程。這整條路徑只寫隔離 `FA_Data_Shadow\recommendation_learning` 下的 dataset、capture、evidence、authority 與 pointer，不寫正式 recommendation／evidence DB、Portfolio、Formal 或 broker state，也不直接改變正式推薦。scheduler、pipeline、runner、consumer 與 Workbench 共用 `app_module/recommendation_learning_paths.py` 的 root resolver；正式預設 `DATA_ROOT` 對應同層 `FA_Data_Shadow`，不繼承一般 `OUTPUT_ROOT`，不安全的 explicit root 會 fail closed。2026-09-14 durable readback 仍是 partial／degraded normal snapshot、TPEx 缺價 warning 與待自然成熟的 explicit capture；工程 QA handoff 已同步，不能由單次 bounded run、historical replay 或 orchestration `passed_with_warnings` 取代 natural／formal PIT credit。詳見 [V4.2 prospective source daily learning QA](../06_qa/V4_2_PROSPECTIVE_SOURCE_DAILY_LEARNING_2026_09_14.md)。

normal snapshot 的 recommendation result 也只落在 `FA_Data_Shadow` shadow root；正式
recommendation／evidence DB、Portfolio、Formal 與 broker state 仍不寫入。

source custody 每輪以帶 timezone 的精確 `availability_cutoff_at` 驗證，timestamp 先正規化
UTC，再要求 `available_at <= capture cutoff`；同一 instant 的 `+08:00`／`Z` 可接受，晚於 cutoff
的同日 publication 拒絕。technical、daily source、feature snapshot、official event 與
corporate-adjustment receipt 都必須通過這個 prospective binding，不能反推 historical PIT。

2026-09-14 04:22:11-07:00 的最新 wrapper 已完成，pipeline status 為
`passed_with_warnings`、blockers 為空；同輪 quick publication 於
`2026-09-14T04:21:27.181165-07:00` 完成且 publication 為 `published`。learning child 已
`completed` 並保存 normal live capture：normal scheduled snapshot 的 symbol source 為
`scheduled_recommendation_snapshot:scheduled_rec_20260914_042140.json:eligible`，只提供
`1528`；candidate 仍為 `rec-cal-29c1b6129396a3885a89d080`，experiment scope 維持
`scheduled-experiment-ff4d2ab937e2c8b32bf2df04`；single-class blocker 已由事前決定的 bootstrap
處理，三檔 controlled capture 不代替正常 lane。normal capture scope 為
`scheduled-capture-5f4de77ffb404af2`，新 immutable capture 路徑為
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\captures\2026-09-14\scheduled-capture-5f4de77ffb404af2\rec-cal-29c1b6129396a3885a89d080-850760d54413e019199be668.json`，
hash 為 `sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`；同輪
technical computation receipt 為
`D:\Min\Python\Project\FA_Data_Shadow\scheduled\technical_indicator_publication\2026-09-14\0f533bde5119890a\receipt.json`、
`verified`，2148 檔股票的 bounded 真重算已完成；authority 仍
`retain_current`，natural sample 為 `0`，因 `natural_forward_evidence_receipt_missing`，自然成熟尚未發生。

historical bootstrap 的 durable observation status 為 `recovered_completed`，selection policy 為
`time_stratified_eligible_dates`，manifest 為
`D:\Min\Python\Project\FA_Data_Shadow\recommendation_learning\datasets\recommendation-dataset-da3d867b06b5436d\dataset.json`。
其 `initial_seen_start=2026-04-23`，bootstrap replay selected date window 為 `2024-09-16` 至
`2026-02-11`；date overlap、row overlap、label boundary crossing 均為 `0`。這些欄位只描述
bounded training lineage 與分層觀測，historical replay 永不取得 natural forward evidence 或 formal PIT credit。
前兩輪 180 秒 timeout 是失敗；04:10 default 雖完成，但 publication 因 completion microsecond
witness 不合法而 blocked，normal capture 亦因 nested capture blocked 且被舊 training completed
遮蔽而出現 false-success。兩者均不列為驗收，只採信 04:22 的新 durable success。
QA handoff 的 source／capture／official custody／guards、update-service／process-pool／technical-analysis、
targeted mypy、inventory 與 registration 數字已核實；scheduler `14 passed` 已接受，04:22 主線
wrapper true-success 已記錄；工程 gate 與正式 default smoke 已由父任務接受。主 Luna 回報 QA 7.1
為 `33 passed`（含 microsecond／nested blocked-capture regression，未杜撰命令）；僅主 Luna git
commit 尚待完成。P1 三日 cache-hit custody QA 已獨立通過，real natural／formal PIT／actual cost
仍依各自 gate 判讀。

獨立 UI／型別 QA 已完成：`tests/test_ui_qt_update_view_workbench.py` 為 81 passed（1 個 pytest
cache permission warning）、`scripts/qa_validate_update_tab.py` 為 25 passed／0 failed／4
skipped；source-contract Mapping guard 修正後 mypy 檢查 606 個 source files 並回報 no issues。
這些驗證只涵蓋 UI、Update Tab 與型別邊界；另有獨立三日 cache-hit custody QA 已通過，但仍不
取代 real durable daily flow、自然 forward evidence 或 V4 整體驗收。

主線另有 affected focused suites `107 passed`（11 個 test files、`36.44s`、既有 1 個 cache
warning）；source-contract／capture／official-custody／guards focused 為 `17 passed`，
update-service／process-pool／technical-analysis focused 為 `10 passed`；targeted mypy `5 files`
clean。changed scheduled scripts 的 mypy `7 files` 與以暫時 `PYTHONPYCACHEPREFIX` 執行的
py_compile 也保留通過結果，原有 `__pycache__` permission 限制仍保留；inventory 為 `12 passed`
（既有 1 個 cache warning），新增 cache guard 後登錄總量已核實為 `805`、recommendation 為
`31`。synthetic mature fixture
`tests/test_daily_recommendation_learning_loop.py::test_daily_main_discovers_maturity_and_rolls_back_active_model_without_flags`
已通過 production source verifier、adopt／active／rollback assertions。P1 三日 technical cache-hit
custody QA 已以 `currentity→verified receipt reuse` 修復並通過：2026-09-08 至 2026-09-10 的
正式 output receipts 可重新解析至各日 `FA_Data/output`，Shadow publication 保留原 timestamp，
production source audit 的 hash／value／lineage 與正式 ADX producer 輸出均通過；命令結果為
`1 passed, 1 warning in 1.25s`。這只證明 bounded fixture 的跨 root custody，不授予 real natural
forward、formal PIT、actual cost 或 V4 credit。scheduler `14 passed`、04:22 wrapper true-success
與已交付工程 gate 已接受；僅主 Luna git commit 尚待完成。

目前 registry 已保存：

- 資料截止日與 hash
- 策略版本
- 完整參數與權重版本
- 成本與成交假設
- Universe
- OOS 與 benchmark 結果
- equity curve 與 trades parquet hash
- storage / integrity 狀態

既有 `BacktestRunRepository` 與 `RecommendationPortfolioRunRepository` 仍作為 legacy repository 存在；新「保存結果」入口已改由 UI 呼叫 `ResearchRunService.save_run()`。歷史 run 可由 `scripts/backfill_legacy_runs.py --apply` 明確匯入 registry，dry-run 為預設行為，且不刪除舊資料。

Month 2 M2-C 已新增 Cross-run Comparison service / UI 與 Registry-based Promote Gate。Month 6 v1 後，Promotion 以 Registry run 為單一來源，前置檢查要求 committed / valid、未 archive、未 promoted、可還原 parameter contract version，且通過最低 validation gate 與 `StrategyLifecycleService` 的 promote gate。Lifecycle gate 只讀已保存 metadata：交易次數、總報酬、Sharpe、回撤、勝率、benchmark excess return、factor snapshot quality 與 regime breakdown，不重新抓取當前資料、不重跑回測。`LifecycleEvidenceRepository` 以 append-only SQLite table 保存 decision snapshot、gate reasons、version id 與 status，並提供 latest state projection；`LifecycleEvidenceGovernanceService` 可把 demote / retire 判斷保存為 proposed evidence，不刪除或覆寫策略版本。策略版本 JSON 採 temporary file + atomic replace 寫入；若 Registry 回填 `promoted_version_id` 失敗，系統會刪除已寫入 JSON，刪除失敗時標記 `promotion_reconciliation_status='reconciliation_required'`，不宣稱為 SQLite transaction rollback。Promotion 成功且 evidence repository 已注入時，會在 Registry sync 後保存 applied lifecycle evidence。Reconciliation service 會掃描 JSON 與 Registry 的 source_run_id / promoted_version_id 不一致狀態，提供受控修復依據。

## 12. 報告匯出與分頁資料流

### 12.1 SQLite 檢視器穩定分頁

- **分頁機制**：透過 `SqliteInspectorService` 的 count 與 page 查詢共用 filter builder。預覽查詢藉由 `LIMIT ? OFFSET ?` 完成。
- **排序穩定契約**：預設依 `日期 DESC, 證券代號 ASC` 加上其他關鍵欄位作為 tie-breaker，最後補上唯一 `rowid ASC`，確保跨頁無重複與遺漏；使用者點擊表頭排序時，只能使用 PRAGMA schema 驗證後的白名單欄位或安全顯示 alias，並由 SQLite 端 `ORDER BY` 搭配既有分頁執行。
- **欄位呈現契約**：SQLite Inspector 可在唯讀查詢層套用使用者可見 alias，例如舊 daily_prices schema 的簡體 `涨跌` 會顯示為繁體 `漲跌`；`漲跌價差` 的預覽值可依 `漲跌(+/-)` / `漲跌` 方向轉為帶正負號的展示值，但不改寫原始資料表。UI table model 以欄位位置取值，可容忍顯示 alias 造成的重複欄名，不應再出現 Series ambiguity。
- **唯讀初始化與降級**：`SqliteInspectorService` 與 `UpdateService` 狀態讀取共用 `app_module.sqlite_read_only.ReadOnlySQLiteManager`，不經 `DBManager` 建立資料庫，改由 SQLite URI `mode=ro`／`PRAGMA query_only=ON` 執行 schema、count、preview 與 overview/detail 查詢；缺 DB、損毀或不可讀時回傳 diagnostics／`last_error`，Widget 顯示 `SQLite 不可用`，不建立空 DB，也不阻斷主視窗啟動。
- **防禦與 stale 處理**：當重新查詢或變更篩選時，頁碼重設為 1。背景 `TaskWorker` 攜帶單調遞增的 `request_id`，UI 在讀取完畢時會校驗 `request_id` 與當前最新請求是否相符，丟棄過期 (stale) 結果。執行中的 worker 會保留強參考直到執行緒自然結束，不對舊查詢呼叫無參數 `disconnect()` 或提前釋放 `QThread`。

UpdateView 的 worker coordinator 以 `kind=read|write` 管理背景工作；寫入型工作（下載、同步、合併、技術指標與匯出）採 exclusive guard，唯讀狀態／詳情查詢可並行。進度 callback 由外層映射子流程區間並維持單調遞增，只有最終狀態刷新成功才回報 100%；寫入完成或失敗後會清除來源詳情 cache，避免 UI 沿用舊快照。

### 12.2 規格化 Excel 報告匯出

```text
Current Result DTO / Run Metadata
  -> UI Payload Builder
  -> Defensive-copy Export Payload DTO (app_module/report_export_dtos.py)
  -> TaskWorker (Background Thread)
  -> ReportExportService (app_module/report_export_service.py)
  -> temporary .xlsx (Atomic temp file)
  -> os.replace (Atomic file replacement)
```

- **防禦性快照 (DTO-first)**：UI 將當前成功回測或推薦的結果 DTO、執行參數與元數據，透過 payload builder 建立防禦性複製。批次回測由正式 `stock_results` 建構排行榜，推薦回放使用執行前保存的參數快照，不在匯出當下重讀已可能變動的 UI 控制項。
- **原子性安全寫入**：匯出服務在寫入目標路徑時，會先建立 `.tmp` 暫存檔，寫入成功後再進行原子性檔案替換 (`os.replace`)，確保匯出失敗或被 Excel 鎖定時不損壞原有報告。
- **資料形狀正規化**：equity curve 可接受 `日期`、`date` 欄位或日期 index；匯出邊界會統一成 `日期` 欄位，並可由已提供的 equity 序列衍生展示用 drawdown。
- **無策略重算防線**：`ReportExportService` 屬於 presentation serialization layer，不重跑策略，也不重新計算總報酬、Sharpe、Monte Carlo 等摘要績效。缺失的追溯欄位統一輸出 `N/A`，不得以預設版本、benchmark 或成交假設代填。

## 13. 文件架構

本專案採 Scoped SSOT：

| 主題 | 權威文件 |
|---|---|
| 目前狀態 | `docs/00_core/PROJECT_SNAPSHOT.md` |
| 未來 6 個月 | `docs/00_core/ROADMAP_6M_ENGINEERING.md` |
| V2.0 之後長期版本階梯 | `docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md` |
| 外部參考與 V1.5-V2.0 版本形狀 | `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` |
| 舊 Roadmap 移交 | `docs/00_core/LEGACY_ROADMAP_CARRYOVER.md` |
| 架構 | 本文件 |
| 目標架構 | `docs/01_architecture/target_system_architecture.md` |
| Post-Refactor 產品方向 | `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md` |
| 使用方式 | `docs/07_guides/APPLICATION_MANUAL.md` |
| 文件導航 | `docs/00_core/DOCUMENTATION_INDEX.md` |
| 已完成行為不變重構的歷史／rollback companion | `docs/09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md` |

Roadmap Hub 只負責入口與短版 Next，不保存完整歷史或架構細節。

## 14. 高風險修改清單

修改以下區域必須提高驗證強度：

- `backtest_module/`
- `app_module/backtest_service.py`
- `app_module/recommendation_service.py`
- `decision_module/scoring_engine.py`
- `decision_module/score_threshold_policy.py`
- `decision_module/strategy_configurator.py`
- `decision_module/strategies/`（策略契約、唯一 registry 與 executor owner）
- `app_module/strategies/`（`TMP-STR-01` 薄相容 facade，退出條件見 FINAL_MIGRATION_SEQUENCE）
- `portfolio_module/core.py`
- `app_module/portfolio_condition_monitor.py`
- `data_module/config.py`
- `app_module/update_service.py`
- `runtime/`
- UI ↔ DTO contract

策略、回測、推薦、Factor 與 Portfolio 改動前必須做 Look-ahead 自查與金融數值邊界檢查。

### 重複計算消除邊界（2026-07-09）

- 推薦所需的最新價格／成交量衍生特徵由 `decision_module/derived_market_features.py` 單次計算，篩選、推薦 DTO 與 negative evidence 只讀取同一份 enrichment 結果。
- `decision_module/indicator_reuse.py` 先經 `IndicatorParameterRegistry` 驗證與正規化；只有標準預設參數及完整有效的預存欄位可以 reuse。自訂參數、缺欄位、全無效欄位、ATR 與 ADX 保持重新計算或 fail-closed。
- `DecisionMarketFrameLoader` 只在單次 `DecisionDeskSnapshotBuilder.build_snapshot()` 內供 Market Breadth、Relative Strength / Liquidity 與 Smart Money 共用 `daily_prices` frame；每次 snapshot 開始都 reset，SQL 固定 `日期 <= as_of_date`，不形成跨日或跨排程 stale cache。
- `RecommendationService.run_recommendation()`、`BacktestService.run_backtest()`、`UpdateService.calculate_technical_indicators()` 與 `DecisionDeskSnapshotBuilder.build_snapshot()` 的公開呼叫方式不變，且未新增 SQLite schema migration。

## 15. 驗證

UI 修改：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ui_qt_update_view_workbench.py -q -o addopts=
.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
```

金融核心：

```powershell
.\.venv\Scripts\python.exe scripts\check_financial_float_boundaries.py
```

文件修改：

- 檢查 Active docs 不再把 Legacy Roadmap 或 `ui_app/main.py` 當目前入口。
- 驗證 Markdown relative 連結。
- 更新 `DOCUMENTATION_INDEX.md` 與 Manual coverage。

## Gate 1 Advice 現況邊界（2026-07-12）

`app_module/advice_dtos.py` 定義 immutable Advice action / mode / policy / dashboard DTO；`app_module/advice_policy.py` 以固定順序做 fail-closed 判定；`app_module/advice_composer.py` 僅組合注入的 Recommendation、Portfolio 與 Evidence payload。Composer 強制 `data_as_of_date <= decision_date`，拒絕未來 Portfolio input，並保留 source trace；它不讀 UI state、不查 SQLite、不寫 DB。

`WorkbenchReadOnlyComposer` 只把 `AdviceDashboardDTO` 放入 `WorkbenchDashboardDTO.advice_dashboard`；`ui_qt/views/workbench_view.py` 與 table model 只渲染 DTO。UI 不得呼叫 policy / composer、修改風險限制、重算核心或送出交易。Guided Mode 僅接受 promoted strategy；Professional Mode 的 candidate 只可研究呈現。最低現金 `2000 bp`、最多 8 檔、單檔 `1500 bp`、整數 bp 與 `Decimal` 金額屬 application contract。此 slice 不建立 broker、scheduler、write repository 或 lifecycle action。

## 16. 更新記錄

- 2026-09-25（歷史快照，已由當日稍後 R031 closeout 更新）：同步 R026 exact NP1／NP2 bounded runtime migration 的 C2 acceptance 與 `TMP-ML-01` scoped closeout；當時保留 C3／C4 pending 與 Update SQLite teardown named baseline。請以 [R031 final closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 的 C3／C4 acceptance、named boundary baseline 及 retained owners 為現況。
- 2026-09-26：Wave14 candidate 在獨立 managed worktree 首次完整 union 為 2,404P／44F／5S／35W；42 個 exact-fixture byte／EOL mismatch 與 2 個既有 shadow-boundary aggregate failures 已具名，首次 480-input unchanged 不含全部實際 C1 fixture bytes，因此不能視為完整 input closure。五個 byte-pinned fixture 已還原至原 HEAD blobs，focused route 80P／1S；526-input 第二輪 union 為 2,431P／17F／5S。第三輪 526-input short-path full union 為 2,446P／2F／5S／35W；15 個 custody nodes 已在 short-path focused route 全數通過。Root 比對第三輪 CLI captured stdout JSON 與 C4 為 584 files／11 occurrences／10 distinct、`shadow_only=true` 且兩個 failing nodes 相同，裁定 `ACCEPTED_WITH_NAMED_BOUNDARY_BASELINE`；R031 engineering scope complete with retained blockers。這不是全綠或整體 refactor unqualified PASS。9/25 C4 receipts 保持獨立歷史收據；不代表產品／正式資料 gate。詳見 [R031 final closeout](../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 與 [Wave14 candidate manifest](../06_qa/WAVE14_CANDIDATE_CHANGE_MANIFEST_20260926.json)。

- 2026-09-14：同步 Decision Workbench 的 probability／rank provenance 詳情、unknown／shadow
  判讀、既有 Journal／Evidence／Portfolio ledger identity 重用原則，以及 daily shadow policy
  內的自動採用／回退邊界；不新增平行 decision store、不授權 formal promotion 或 broker。

- 2026-09-14 02:34:17-07:00：normal pipeline 已完成並保留 source／cohort warnings；learning child 以 `recovered_completed` 的 `time_stratified_eligible_dates` historical bootstrap 產生 255 training rows、candidate 與 1 row immutable capture。manifest 的 `initial_seen_start=2026-04-23`，bootstrap replay selected date window 為 `2024-09-16` 至 `2026-02-11`，date／row overlap 與 label boundary crossing 均為 0；decision 仍為 `retain_current`，自然 forward evidence 尚未成熟。affected focused／mature fixture 已完成，主線 QA final status 維持 pending；P1 cache-hit custody QA 其後獨立通過。

- 2026-09-14：獨立 UI／型別 QA：UI Workbench 81 passed（1 個 cache permission warning）、Update Tab 25 passed／0 failed／4 skipped；source-contract Mapping guard 修正後 mypy 606 source files no issues。real durable daily flow、主線新版 wrapper smoke 與 QA final status 仍待父任務交付；P1 cache-hit custody QA 另已獨立通過。

- 2026-09-14：主線驗收補充：affected focused suites 107 passed（11 個 test files、36.44 秒、既有 1 個 cache warning）；changed scheduled scripts 的 mypy 7 files 成功；changed scripts／modules／tests 以暫時 `PYTHONPYCACHEPREFIX` py_compile 通過，原有 `__pycache__` permission 限制保留；inventory 12 passed；新增 guards test 後登錄總量 804、recommendation 30。synthetic mature fixture 已通過 production source verifier 與 authority adopt／rollback assertions；舊 cache-hit guard 的 P1 source-audit／cross-root lookup／隔日 DB 變更缺口其後已由 verified receipt reuse 修復，獨立 cache QA 已通過；主線新版 wrapper smoke 與修後 source tests／型別／compile／inventory 最終 handoff 仍待交付。

- 2026-09-14：P1 cache-hit custody 修復後獨立 QA 已通過：`tests/test_recommendation_learning_cache_hit_custody.py` 為 `1 passed, 1 warning in 1.25s`、exit 0；三日正式 output receipt → Shadow verified reuse、原 timestamp、production source audit hash／value／lineage 與正式 ADX producer 輸出均驗證。此為 bounded fixture custody proof；主線新版 wrapper smoke 與修後 source tests／型別／compile／inventory 最終 handoff 仍待交付。

- 2026-09-14：主線修後 focused handoff：source-contract／capture／official-custody／guards `17 passed`；update-service／process-pool／technical-analysis `10 passed`；targeted mypy `5 files` clean；inventory `12 passed`，登錄總量 `805`／recommendation `31`；cache custody `1 passed`。scheduler 修正 test fixture 後的最終重跑與新版 wrapper smoke 尚待交付，整體收尾維持 pending。

- 2026-09-14 04:22:11-07:00：正式 default wrapper true-success：pipeline `passed_with_warnings`、`blockers=[]`；quick publication 於 `2026-09-14T04:21:27.181165-07:00` 為 `published`；learning child `completed`，symbol source=`scheduled_recommendation_snapshot:scheduled_rec_20260914_042140.json:eligible`、symbols=`1528`、candidate=`rec-cal-29c1b6129396a3885a89d080`、natural sample=`0`、decision=`retain_current`。新 immutable capture hash=`sha256:8c974b82de0cb6f4a5dc01ab08183e8cd02049f97bd56d6ce74908360072b2c0`；04:10 microsecond／nested capture false-success 不列為 pass，主 Luna 回報 QA 7.1 為 33 passed；僅主 Luna git commit 尚待完成。

- 2026-09-14：同步 V4.2 每日推薦學習的 wrapper → pipeline → source custody → normal snapshot → learning 資料流；補上 `--skip-broker-branch`、warning／degraded 傳遞、child／pipeline timeout、normal cohort 與 explicit capture 的 identity 隔離，以及 technical／official event／corporate sidecar 的 prospective 邊界。2026-09-14 durable readback 仍為 partial／degraded 與待自然成熟，維持 shadow-only、不可宣稱 V4／alpha／收益提升；QA handoff 待當日最終測試與正常 cohort status。

- 2026-09-13：新增 V4.2 每日推薦自動學習與受控校準閉環架構同步；05:40 forward outcome 後的 05:45 bounded replay／training／capture／自然成熟／active recheck／authority rollback 皆維持 shadow-only。補上 source contract 實際 digest／coverage／available-at／corporate-action conservative gate、after-cost 獨立 baseline 與 adopted active rows 的 cutoff 隔離；同步 dedicated `FA_Data_Shadow` root resolver 與 scheduler／runner／consumer／Workbench 共用路徑契約；不寫正式 recommendation／evidence DB、不啟用正式 promotion 或 broker。

- 2026-09-06：同步八卡日期／品質 DTO、推薦 context、T+1 版本、顯式 Registry 恢復、Evidence 提案、候選帳本／候選池及 Runtime 生命週期；保留正式來源與外部 Gate。

- 2026-09-04：Data Update 增加月營收／Phase 3C 候選更新 service wrapper 與子分頁操作入口；所有候選寫入仍隔離於正式 SQLite，來源狀態查詢在 production 根目錄唯讀時採 fail-soft manifest warning。全部資料頁操作列與狀態卡採 status-first responsive layout。
- 2026-08-29：將 `release_v4` 明確定位為 engineering／storage namespace，不再稱 `V4.0 Operational Production`；補入 immutable PIT／Direct／OOC pointer、dependency closure、人工 retention、resume abandonment、tombstone 與 stale status 邊界。Runtime environment／clone proof 與 production transaction proof 維持分層；Formal 0/3、alpha 0、scheduler／broker disabled 不因容量清理改變。
- 2026-08-26：補強 Data Update trust UX；UpdateView 狀態卡改為明確 status token／freshness 判定並清除部分 payload 的舊卡片，quick/safe 與各寫入型 worker 增加互斥、子流程進度區間映射與 final-status 100% gate。SQLite Inspector 與 UpdateService 狀態讀取共用 `mode=ro`／`query_only` adapter，缺 DB 時以 unavailable fail-soft，不建立空資料庫；TWSE 明確失敗時每日來源流程在 TPEX／SQLite／技術指標前停止；同步補上 UI、每日更新與 SQLite 操作手冊及回歸測試邊界。

- 2026-07-15：同步 corporate-action availability history staging-only CLI 邊界；JSON root deterministic fail-closed、既有 target 拒絕覆寫、staging publish／cleanup 與環境 `DATA_ROOT` forbidden-root guard 均不接正式資料或 Formal lifecycle。
- 2026-07-13：新增 Terra Development Dataset V0 獨立 development-only generation 邊界；四個 core source 唯讀、T-1／252 日 observed universe、2025 development／2026 evaluation-only、append-only artifact 與 zero-formal-write safety flags 不接正式 Rule-only path。
- 2026-07-12：新增 Gate 1 Advice Current Architecture 邊界；Advice policy / composer 在 application layer，Workbench UI 僅渲染 DTO，所有輸入維持 as-of / fail-closed / no-write contract。
- 2026-07-11：新增 Target Architecture 與 Post-Refactor Product Roadmap companion 連結；修正目前主 UI 為 8 個左側主工作區，Daily Decision 已內嵌於「決策工作台 > 決策來源」；本文件仍只描述 Current Architecture。
- 2026-07-11：新增 Safe Refactoring Master Report 為行為不變重構執行 companion；該 program 於 2026-07-12 closeout 後已歸檔為 `docs/09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md`，目前架構、產品 Roadmap 與使用流程權威邊界不變。
- 2026-07-07：更新 Phase 2 Workbench MVP shell 架構同步；`ui_qt/views/workbench_view.py` 與 `ui_qt/models/workbench_table_models.py` 只呈現 `WorkbenchDashboardDTO`，主 UI 透過 `WorkbenchSourceService` 注入，新增中文顯示、預設 replay JSON summary 分析與舊 Daily Decision / Evidence Review / Portfolio read-only drill-down，不直接讀 SQLite / replay DB、不寫 DB、不啟用 scheduler、不重算 scoring / portfolio / backtest / lifecycle。
- 2026-07-08：補充 Pre-V2 readiness source-gap closeout fallback；同日 scheduled dry-run `latest_status.json` 可作為修正後歷史觀察日的唯讀證據，仍不回補 DB、不觸發 confirm、不解除 production scheduler gate。
- 2026-07-07：補充 Workbench background evidence feed / read-only Action Items MVP 架構；`WorkbenchDashboardDTO` 新增背景證據流與只讀人工待處理列，來源只限既有 snapshot/readiness/agent/replay summary payload，Action Items 保留 source trace / degraded reason / drill-down target 且 `write_intent=false`。
- 2026-07-07：補充 Workbench Action Items 人工佇列 follow-up 架構；Action Item DTO 增加 queue group / source label / sort rank，composer 只排序既有 payload，Qt view 補空 / 降級狀態文案與 drill-down target contract，仍不接 DB / replay / scheduler / lifecycle。
- 2026-07-07：補充 Workbench Phase 2C / 2D closeout 架構；`WorkbenchOperatingLoopStep` / `WorkbenchOperatingLoopTableModel` 只從 `WorkbenchDashboardDTO` 串接 daily first-look、manual queue、weekly history、multi-day dry-run、manual review note 與 scheduler gate，所有 step `write_intent=false`，Phase 0 時間 gate 與 production scheduler gate 不因 UI closeout 被補完。
- 2026-07-06：文件架構補上 `VERSION_ROADMAP_V2_1_TO_V4_0.md`，定位為 V2.0 之後長期版號 companion；本文件仍只維護目前架構、模組邊界與資料流。
- 2026-07-06：新增 V2.0 Phase 1 read-only Workbench prototype 架構同步，確認 DTO / composer / replay summary adapter / CLI 只組合唯讀樣本與 replay JSON summary，不寫 DB、不掛主 UI、不重算策略、不啟用 scheduler。
- 2026-07-06：新增 Workbench formal read-only source adapter 架構同步，確認 `WorkbenchSourceService` 只用 SQLite `mode=ro` / `query_only` 讀受控 DB path 的 DDD snapshot，並組合 Pre-V2 readiness、Agent summary 與可選 replay JSON；missing DB / table 只回 diagnostics，不建立 schema、不寫 DB、不解除 Phase 0 / scheduler gate。
- 2026-08-27：Decision Desk／Pre-V2／Evidence source coverage 的 current snapshot 查詢統一以台灣市場今日為上限；future row 保留 raw 稽核、輸出 blocker／diagnostic，不進入 current evidence。`EvidenceSourceCoverageService` 與 `inspect_decision_desk_snapshots.py` 改用 query-only 讀取，避免唯讀正式 DB 被 writer repository 初始化 schema。
- 2026-08-27：Data Update UI 的日期控件統一由台灣市場日期服務提供「今日」；localized `不可用` 會落到異常狀態；全域狀態檢查失敗會將六個核心與三個候選來源 inline 摘要同步清除並保留共同錯誤原因，避免狀態卡與來源頁殘留不同步；候選來源分頁也會投影自己的檢查結果。此為 presentation／diagnostic 邊界，不改資料更新與 SQLite 寫入契約。
- 2026-08-27：每日資料合併的 cancellation callback 延伸至單一 CSV 的讀取批次邊界；完整檔案讀取完才加入待提交集合，取消仍不會截斷或替換正式整合檔。這改善長檔等待期間的可觀測性，但不等於逐列中斷或解除 single-writer 安全邊界。
- 2026-08-27：ScoringEngine 的 rolling PatternScore 同步保存已確認型態的唯讀 evidence（名稱、方向、確認日與衰減日數），並投影 `PatternNames`／`Pattern_Signal`／`PatternAgeDays` 給 ReasonEngine。Explain 不在單列資料上重新呼叫 PatternAnalyzer；缺少具體名稱時只顯示 generic 方向訊號，避免把 end_idx 或分數臆測成已成立型態。
- 2026-08-27：Recommendation 與四個策略 executor 移除未使用的全歷史 `identify_patterns()` 預掃描，統一由 ScoringEngine rolling path 產出分數與 evidence；不改策略訊號，只避免重複計算與未確認型態的誤解釋。
- 2026-08-27：UpdateService 的 SQLite 輸入正規化修正為先辨識受治理的日期／股票代號／股票名稱別名，再在寫入副本上統一 canonical 欄位、日期與四碼代號；修正重複條件造成的英文欄位被提前丟棄問題。raw CSV 與呼叫端 DataFrame 不被原地改寫，必要欄位缺失仍 fail-closed。
- 2026-09-12：新增 V4.1 A 線第二輪 historical method pack 架構同步，確認 manifest 的 row-level time／lineage／gap contract、20／5 walk-forward reuse、PIT theme fail-closed 與 create-only frozen shadow artifact；不改 Recommendation／Scoring、不寫 formal DB、不授予 natural forward evidence credit。
- 2026-07-06：新增 Historical Evidence Replay 架構同步，確認 replay service 只做 working-copy / replay DB orchestration，recommendation result 受 `created_at <= decision_date` 限制，forward outcome 受 `data_as_of_date` 限制，不改 scheduled dry-run、不寫 formal DB、不啟用 production scheduler。
- 2026-07-06：補充 Phase 0A reference return fix 架構契約，確認 missing benchmark fallback 到 TAIEX、market index `收盤價` fallback 與保守 industry sector mapping 只影響 evidence outcome reference lookup，不改 scoring、portfolio 或 scheduler。
- 2026-07-06：新增 Pre-V2 readiness inspector 架構同步，確認 `PreV2ReadinessService` 只做 weekly history / multi-day record / source gaps / Agent report sample 唯讀檢查，不建立 schema、不寫 evidence、不啟用 scheduler。
- 2026-07-06：補充 Pre-V2 非時間型 closeout 與 Recommendation liquidity payload follow-up，確認 working-copy source gaps / UI smoke / Agent sample 已收斂，但 formal DB write、weekly / multi-day 時間 gate 與 production scheduler approval 仍未完成。
- 2026-07-05：完成 V1.6 Cross-sectional Factor Pipeline v1 架構同步，新增 snapshot DTO / repository / migration、FactorGate-backed pipeline、concept basket available-date gate、rank / quantile persistence 與 read-only attribution summary CLI；保持 application governance layer，不改 scoring、不啟用 scheduler。
- 2026-07-05：完成 V1.7 Screening Matrix & Negative Evidence v1 架構同步，新增 Recommendation result screening matrix、negative evidence payload capture、screening matrix events 與 source coverage warning；只消費已保存 payload，不回補、不重算、不改 scoring、不啟用 scheduler。
- 2026-07-04：文件架構補上 `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md`，作為外部開源專案參考、資料源補強優先序與 V1.5-V2.0 版本形狀 companion；本文件仍只維護目前模組邊界與資料流。
- 2026-07-04：完成 V1.5 Data Credibility & Corporate Action Gate v1 架構同步，新增 read-only source capability registry、corporate action policy、microstructure governed metadata 與 shared evidence source coverage service；不寫正式資料、不改 scoring、不啟用 scheduler。
- 2026-07-02：完成 V1.2 Research Credibility & Execution Model v1 架構同步，確認 Profile replay 訓練 / 驗證分離、推薦回放 rolling risk、microstructure preflight 與 relative attribution 都位於 application diagnostics boundary，不改交易、PnL、cash ledger 或策略生命週期。
- 2026-07-03：完成 V1.3 Evidence Operations & Manual Lifecycle v1 架構同步，新增 weekly evidence operations service / CLI；manual approval package 與 action item planning 只供人工覆盤，不啟用 scheduler、不自動套用 lifecycle action。
- 2026-07-03：完成 V1.4 Evidence Review History v1 架構同步，新增 weekly review history repository、dashboard service 與 Research Lab `Evidence Review -> 覆盤歷史` 唯讀子頁；history 只保存人工覆盤快照，不啟用 scheduler、不自動 lifecycle action。
- 2026-07-02：完成 V1.1 workflow bridge v1 架構同步，新增 `ProfileReplayComparisonService` / DTO application boundary；Profile replay 比較只讀注入 runner 結果並輸出人工 lifecycle candidate，不寫 DB、不重算推薦、不自動升降級。
- 2026-06-23：完成 Healthcheck Batch 2 架構同步，新增 `DecisionDeskDashboardComposer` 與 `SmartMoneySemanticService` 邊界；Daily Decision Desk answer-first dashboard 與 Smart Money 5 / 20 / 60 日語意診斷皆由 app service / DTO 提供，Qt UI 不重算籌碼或市場邏輯。
- 2026-07-01：新增 Post-V1 evidence layer 架構邊界，確認 Evidence Event Store / Forward Outcome Calculator 只保存事件與 close-to-close research outcomes，不改 scoring、推薦權重、portfolio 或 UI。
- 2026-07-01：新增 Evidence Review Dashboards read-only UI pack 架構邊界，Research Lab `Evidence Review` 只透過 dashboard service 讀取 Forward Evidence、Live vs Research Gap、Signal Decay 與 Decision Quality；UI 不直接讀 SQLite / repository，不改 scoring、portfolio、Research Run 或 Strategy Lifecycle，也不建立 scheduler。
- 2026-06-23：完成 Healthcheck Batch 3 架構同步，新增 `RecommendationProfileService` 作為推薦分析 Profile lifecycle 邊界，支援內建 / 自訂 / gate-passed 策略版本 Profile，並明確規範 Profile-Regime mismatch 只作解釋與分數揭露。
- 2026-06-23：完成 Healthcheck Batch 4 架構同步，新增 `research_result_presentation.py` 作為 Research Lab 結果頁呈現邊界；推薦回放段落、Train-Test / Walk-forward 樣本可靠度提示與 Registry 比較中文判讀只讀既有結果，不重跑回測、不抓新資料、不產生交易建議。
- 2026-06-17：完成 Month 5 Fundamental Layer v1 closeout 架構同步，確認 fundamental tables / provider / adapters / diagnostics 為保守接入邊界；P/B、P/S 已補 guarded presentation policy，官方歷史 PIT 公告日保留為後續治理 residual；Month 6 Strategy Lifecycle 不得直接污染 ScoringEngine。
- 2026-06-17：補上 P/B / P/S valuation policy 架構同步，確認 P/B / P/S 僅接受 governed external observations 或 future backfill records，不在系統內推導估值分子 / 分母。
- 2026-06-17：完成 Month 6 Strategy Lifecycle / Portfolio Feedback v1 架構同步，新增 lifecycle rule engine、drift detector、portfolio feedback attribution、Portfolio Review snapshot 與 Registry-based Promote lifecycle gate；持倉管理 UI 只讀 service attribution，不重算策略或改寫持倉。
- 2026-06-17：補上 lifecycle evidence 架構同步，新增 append-only `strategy_lifecycle_repository.py`、latest state projection 與 demote / retire proposed evidence 保存邊界；Promotion 成功後可記錄 applied evidence。
- 2026-06-15：完成 Daily Decision Desk Portfolio Alert Attribution v1，將持倉警示拆為來源標籤、condition status、chip risk level、reason tokens 與 data quality flags，並整合至主 UI 與風險提示，明確定義由 PortfolioAlertService 進行歸因產生的架構職責。
- 2026-06-15：完成 Daily Decision Desk Why Not / 風險提示 v1 對接，由既有 section DTO 欄位與警告推導，輸出對應之低流動性、相對弱勢、Watchlist 觸發與持倉警示提示，不重複計算。
- 2026-06-15：補入 baldr 願景與架構權威邊界，更新 Daily Decision Desk v1 已接上主 UI；Market Breadth v1已接 SQLite `daily_prices` provider，Sector Rotation v1 已接 SQLite `industry_indices` provider，Relative Strength / Liquidity Ranking v1 已接 SQLite `daily_prices` provider，Watchlist Trigger v1 已接 `WatchlistService` 與 SQLite `technical_indicators`，Portfolio Alert v1 已接 `PortfolioService`、`PortfolioConditionMonitor` 與 `PortfolioChipService`，其餘 Strategy Drift 與 Post-trade Attribution 仍屬後續工作；同步 Month 3 Portfolio Replay 可信度、固定組合 per-stock factor metadata保存與後續資料因子接入防線。
- 2026-06-16：完成 Month 4 Daily Decision Desk 收尾架構註記，確認 v1 以 service snapshot 聚合並新增 UI boundary contract test；Month 5 可從 Fundamental Layer preflight 開始，Strategy Drift 與 Post-trade Attribution 仍屬後續工作。
- 2026-06-16：啟動 Month 5 Fundamental Layer preflight 架構落點，新增公告日 / available_date 初版政策、raw 月營收正規化契約、候選 SQLite schema dry-run / report API 與 fundamental adapter contract，確認 raw fundamental CSV 缺 `available_date` 時不得產生 normalized record / factor record，未來資料仍須經 FactorGate 驗證。
- 2026-06-16：新增月營收 availability mapping dry-run 驗證入口與 CLI 架構邊界，確認它們只讀 mapping、輸出 diagnostics，不建立或改寫正式 mapping、raw CSV 或 SQLite。
- 2026-06-16：新增月營收 availability historical dry-run builder 架構邊界，確認 TWSE/TPEX 最新月 OpenAPI 或人工官方 JSON 只能產生候選 mapping / diagnostics，正式 mapping 寫入與 monthly revenue backfill 仍需人工 gate。
- 2026-06-16：補上 MOPS 官方 HTML source-dir 架構邊界；`--mops-html-dir` 只讀人工保存且含 `出表日期` 的官方 HTML，缺欄位時 fail-closed，不由 raw CSV 補日期。
- 2026-06-17：補上 MOPS `--mops-static` 架構邊界與 45 天合理揭露窗口；historical static report 的重新出表日會被視為過晚 available_date，不得形成 candidate row。
- 2026-06-16：補上授權 PIT 月營收公告日 CSV 架構邊界；`--pit-csv` 只接受具 source_version 的 point-in-time 匯出檔並產生候選 mapping，不寫正式 mapping、不回填 SQLite、不接 ScoringEngine。
- 2026-06-16：補上 GitHub public archive source audit 架構邊界；commit first-seen 可作未來 PIT 候選方法，但目前已檢查 public repos 皆未提供可追溯 daily snapshot，因此不新增 `github.*` allowed source。
- 2026-06-16：新增 MOPS snapshot / FinMind create_time 候選抓取器架構邊界；兩者只輸出 candidate/raw evidence 到 output 目錄，不推定正式 available_date，不寫 `monthly_revenue_availability.csv` 或 SQLite。
- 2026-06-16：新增估值呈現政策 / adapter 架構邊界，確認只輸出相對估值區間與 diagnostics，不接 ScoringEngine，不產生目標價、合理價、上漲空間或買賣建議。
- 2026-06-16：新增 valuation data layer 架構邊界，確認資料層只建立受治理 observation 與同產業分位，估值輸出仍由 presentation policy 控制。
- 2026-06-16：新增 valuation metrics backfill 架構邊界，確認 `daily_prices.本益比` 需經 dry-run / confirm / backup workflow 才能寫入 `fundamental_valuation_metrics`，且不接 ScoringEngine。
- 2026-06-16：新增 Abnormal Fundamental diagnostics 架構邊界，確認異常基本面只進 Research metadata 與 Daily Decision Desk risk prompts，不改財報、不改 score。
- 2026-06-16：新增 TPEX daily price backfill 架構邊界，確認官方 TPEX daily close quotes 只能經 dry-run / confirm / backup workflow 補寫 `daily_prices`，不修改 `companies.csv`、fundamental tables 或 scoring。
- 2026-06-18：更新 TPEX daily price 架構邊界，確認日常 / 手動 / 背景流程以官方 afterTrading historical endpoint 補缺少日期，SQLite sync 同時讀取 TWSE `daily_price/` 與 TPEX `daily_price_tpex/`，並 upsert `daily_prices`；背景補齊狀態寫入 `DATA_ROOT/meta_data/tpex_full_refresh_status.json`。
- 2026-06-16：更新 SQLite / broker flow 邊界，確認 `broker_flows` 唯一鍵需包含 `trade_type`，且 SQLite Inspector 顯示 alias 不得影響表格 model 取值。


