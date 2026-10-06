# 系統架構評估

> 2026-09-22；原始碼基線 `574de045e6cf1e7c28be01eb027a8f672a6c7776`。本次僅設計文件，沒有改 production code、正式資料、模型或排程。結論是保留現有系統，以執行契約與責任抽取改善，不做全面重寫。

## 1. 範圍、證據與限制

本評估包含 acquisition、storage、analysis、decision、strategy、backtest、portfolio、ML、application、reporting、Qt、runtime 與研究工具。以既有 2026-09-07 整併評估（開發收據見dev）、[目前架構](../system_architecture.md)、[產品目標架構](../target_system_architecture.md) 為入口，再直接檢查現行原始碼；舊測試失敗數不當作今天的測試結果。

方法：讀既有 graphify 圖譜作定位，再對 11 個程式樹做 AST 函式長度與 import 掃描，深讀推薦執行／保存／重播、主要依賴違規與 ML 數值契約。圖譜已有 42,322 nodes，但不是本次 HEAD 的完整動態 call graph；所有以下具體問題均以原始碼複核。AST 掃描包含函式內 import，不涵蓋所有字串動態載入／外部 plugin。

| 程式樹 | Python 檔數（本次 filesystem 範圍） | 主要現況 |
|---|---:|---|
| `app_module` | 318 | use case、DTO、domain policy、repository、projection 混居 |
| `data_module` | 163 | 來源／SQLite／PIT／numeric store，也有跨層 producer |
| `decision_module` | 29 | 評分、篩選、regime、factor；部分自行讀 storage |
| `analysis_module` | 23 | 指標、pattern、signal；部分歷史 backtest API |
| `backtest_module` | 6 | 策略測試、成本／撮合／績效相關引擎 |
| `portfolio_module` | 2 | domain 尚小，很多 portfolio policy 留在 app |
| `ml_module` | 71 | feature／label／model／calibration／OOC／shadow governance |
| `runtime` | 11 | agent／event／governance 與營運監控 |
| `ui_qt` | 88 | PySide6、workers、views、部分 coordinator 與 composition |
| `financial_module` | 4 | Decimal／整數單位與共同金融約束 |
| `development_module` | 16 | 開發研究契約、實驗與 orchestration |

這 731 檔不是全 repo tracked 檔數，未將 tests、scripts、legacy `ui_app` 混入。沒有讀正式 DB 內容、跑大型 ML 或重演 native UI，因此不能宣稱歷史產物全部相容、全部 fallback 都被動態驗證，或已證明沒有數值／PIT 缺陷。

## 2. 目前系統如何工作

主要入口是 `ui_qt/main.py`。UI 透過 application services 呼叫推薦、回測、更新、研究報告與持倉；`decision_service_composition.py` 已將部分 market providers 注入 decision 元件。Data 以 `TWStockConfig` 設定為準，預設 `D:/Min/Python/Project/FA_Data`，可由環境覆蓋；本次只讀設定程式，未推測主機目前 formal root。

資料來源經 data adapter／source governance、SQLite／CSV／PIT snapshot，提供 analysis 與 decision；推薦保存為 JSON 主體與 SQLite 索引，Research Run、Evidence、Journal、Paper ledger 各有自己的身分與保存政策。歷史重播是另一種執行模式，不能等同讀取當時已保存的結果。

ML 至少有兩組不能任意合併的資料族群：historical recommendation features／calibration，以及 allocation raw PIT → Direct numeric／OOC → experts／release。其 schema、missing mask、特徵順序、hash、label 與 permission 不相同。共同模型只是「來源可追溯、數值邊界明確、獨立治理」，不是一個萬用 dataset。

## 3. 已確認的結構問題

下列行號是本次基線定位；後續以符號與版本複核。問題描述不代表已觀察到 production 資料損壞。

| ID | 原始碼證據 | 確認問題與影響 | 目標處置 |
|---|---|---|---|
| S1 | [RecommendationService](../../../app_module/recommendation_service.py) `run_recommendation` L882–1737（856 行）；初始化 L136 起 | 載入、cutoff、fingerprint、篩選、分析、排名、calibration 與診斷集中；回傳 list，另外更新多個 `last_*` | application 接收完整執行結果；按資料準備、domain 評估、projection、保存拆責任 |
| S2 | SaveRequest（開發收據見dev） `build_result`／`_result_id`／`_regime_snapshot`；[View](../../../ui_qt/views/recommendation_view.py) L2621 起、L2676 | 保存重新讀 live `last_*`，config 暫存 `_recommendation_run_context`；另於保存呼叫 `detect_regime()`，可能讀到執行後 context | 保存消費 frozen run；regime 在執行時固定。新舊差異須有明確時序修正測試，不能偷偷改排名 |
| S3 | [Application ports](../../../app_module/application_ports.py) L16–22 | protocol 直接要求 `last_*`，隱藏狀態已成公開契約；僅新加 façade 不會自動消除 | 舊 port 只留期限相容入口；新入口只傳 request／完整 result |
| S4 | [Regime detector](../../../decision_module/market_regime_detector.py) L272 起；Screener reader（開發收據見dev） L12–99；`industry_mapper.py` | domain 有 SQLite／CSV 讀取與 fallback。provider 已可注入，但 default 路徑仍有 I/O | 純分類留 decision，reader／fallback 移至 data adapter，由 app 組合 |
| S5 | [RecommendationRepository](../../../app_module/recommendation_repository.py) `save_result` L185、`save_result_create_only` L276 | repository 在 app 並非本身錯誤；但業務服務與具體 storage 混在同一 import 平面。legacy replace 與 create-only 同存，不可一律聲稱 immutable | app 的 storage adapter 子區依賴 leaf contracts；use case 只用 port；按寫入政策分派 |
| S6 | [Run support](../../../app_module/recommendation_run_support.py) `build_negative_evidence_buffers`；[DTO](../../../app_module/dtos/__init__.py) `RecommendationResultDTO` L247 起 | matrix、excluded、why-not、liquidity 有重疊欄位；liquidity 類型依字串包含判斷，新增理由可能漏分類 | 一份 typed assessment 為 owner，舊 payload 僅中央 codec 投影；理由分類顯式化 |
| S7 | [ReplayService](../../../app_module/recommendation_replay_service.py) `run_snapshot`；[DataFrame provider](../../../app_module/recommendation_dataframe_provider.py) | replay provider 回 list[dict]，互動推薦回 DTO list；切日與決策證據承載方式不同 | 共用 domain evaluate；保留不同 data/cost/temporal policy，不能直接把互動最新日 pipeline 套歷史 |
| S8 | [Direct numeric](../../../data_module/portfolio_ml_direct_numeric_store.py) `build` L345–1538（1194 行）；[OOC trainer](../../../ml_module/allocation_out_of_core_training_service.py) `train` L885–1553（669 行） | 大型 orchestration，但同時具有嚴格 hash／續跑契約，機械拆檔會改 computation identity | 初期凍結，透過外部 façade 隔離；日後獨立做版本化遷移 |
| S9 | [UpdateService](../../../app_module/update_service.py) `calculate_technical_indicators` L4256–4911（656 行） | calculation 與 CSV／SQLite publication／job control 同處；來源 producer 反向 import service | 優先維持計算函式，application job 組合 compute 與 writer；不趁機變更公式 |
| S10 | [OOC store](../../../data_module/portfolio_ml_out_of_core_store.py) L34；ML release／diagnostics 的 scripts imports | runtime library 依賴 CLI 的私有 `_parse_sample`／loader／repair 函式；入口變更會牽動 library | CLI 純入口，parser／validator 由責任 owner 提供；ML hash 敏感者延後並保留舊 import 相容 |
| S11 | `ui_qt/views/backtest/config_panel.py` `_setup_ui` 810 行；`portfolio_view.py` `_setup_ui` 696 行 | UI 組裝大；不應以行數直接重寫。run state 與保存 payload 才是優先分離點 | Qt view 只管顯示／互動／worker；application 管業務執行與保存 |

跨 run 混用是上述介面的結構風險，**不是本次已重現的 race incident**。UI 已有取消、stale callback 與來源 ID 保護；服務可能在不同 caller 共用，仍應由契約保證一致性，而非只依 UI 使用順序。

另須分辨真正的業務歷史狀態：`MarketRegimeDetector` 的 `regime_history`／`_save_regime_history` 參與確認天數與 cooldown，並可保存 `regime_history.json`。這不是可以直接刪掉的 `last_*` 暫存。目標把 prior state 明示為輸入、state update 明示為輸出，再由 application 依原 policy 保存；不能因追求純函式而移除 hysteresis、改變切換時點或回填未來歷史。

## 4. 依賴違規：移除依賴，還是搬責任？

A＝依賴方向不對，抽出資料契約／注入 port；B＝整個元件實際屬於較外層，重定位；混合者先拆 I/O 與 policy。

| 已核實依賴 | 判斷 | 具體落點與保留事項 |
|---|---|---|
| decision 的 regime／screener／industry → DBManager、sqlite3、CSV | A＋混合 | reader 移 `data_module/readers`；分類規則留原 domain；保留 fallback 順序與原因 |
| `decision_module/factors/*adapters.py` → fundamental record／semantic mapping | B | 這些是資料適配，移 `app_module/adapters/factors`；純 factor evaluation 留 decision |
| `data_module/fubon_shadow_candidate_repository.py` → `app_module.fubon_shadow_decision_service.FubonShadowDecisionBundle` | A | 將 Bundle 放 Fubon 決策的 leaf contract，repository 接 contract；保留 candidate path guard |
| `data_module/watchlist_repository.py` → app 的 continuity DTO | A | 把 watchlist 相關 leaf contract 的 owner 移 `decision_module/watchlist`，舊 DTO import 作 alias，避免新造相同欄位副本 |
| `data_module/paper_daily_execution_producer.py` → app policy／ledger／construction | B＋混合 | producer 是 application job，移 `app_module/jobs`；純 policy 後移 portfolio；資料 writer 留 data |
| `data_module/formal_daily_input_producer.py` → app paper ledger、scripts continuation | B＋混合 | orchestrator 外移，底層讀寫留 data；Direct computation identity 涉及檔案先凍結，不立即搬 |
| `data_module/prospective_technical_shadow_producer.py` → `UpdateService` | B | 是跨服務 publication job，移 app job；復用 indicator compute，保留正式只讀、shadow writer 與 evidence hash |
| `data_module/portfolio_ml_out_of_core_store.py`、`ml_research_causal_ledger_overlay.py` → `scripts.train_ml_allocation_copilot._parse_sample` | B（parser） | parser 實為 allocation record codec，最終由 ML contract owner 管；因 fingerprint／序列化相容性，初期列凍結例外 |
| `data_module/mops_numeric_pit_aggregator.py` → scripts validator | B（validator） | validator 歸 data source contract；CLI 再呼叫它 |
| `ml_module/allocation_v3_linear_release.py`、`feature_gap_diagnostics.py` → scripts repair／inference loader | B（被調用 library） | 行為歸 ML adapter／data reader；CLI 留參數解析，不改 frozen feature semantics |
| app 的 `formal_input_owner_packet.py`、`update_service.py` → scripts | B（被調用工作函式） | source job／readiness reader 移至 owner，scripts 依 application 呼叫；不換排程 |

這不是「所有 data→ml 都錯」。numeric store 與 ML schema 的依賴可合理存在，但只能指向 frozen leaf contracts／已列明的 legacy 例外；ML 算法不應繞 data reader 呼叫 application 或 CLI。

本次執行 `.venv\Scripts\python.exe scripts/check_ml_shadow_boundary.py`，掃描 525 檔、exit 1，仍有 **4 項**既有違規：

- `personalization_projection.py` 與 `personalization_save_adapter.py` → `recommendation_inference_provenance.read_inference_projection_receipt`。
- `recommendation_calibration_consumer.py` → training 模組的 `RECOMMENDATION_RETURN_BASIS` 與 `recommendation_label_contract_id`。

前兩項需集中到已有 ML read adapter，再審查唯一 bridge；後兩項應由推論／label leaf contract 持有，trainer 和 consumer 共用。這是目前 guard 結果，不以加廣泛 allowlist 消掉。其他上述反向依賴是本次全樹 AST 查核，比 ML guard 的專屬範圍更廣。

## 5. 必須保存的優點

- 已有 composition、provider injection、純 ranking pipeline、indicator parameter／weight contracts，不必另建 DI framework 或 plugin runtime。
- Decimal／bp 與 ML analytics boundary 已有規範；保留既有捨入、tie-break、成交時點、費用與未知值語意。
- 推薦有 UUID identity、保存衝突拒絕、run context、negative evidence；P1 projection 有 exact identity／hash readback。應整合成完整結果，不推翻這些保護。
- Research Run、Evidence、Journal、ledger 已分別保存不同生命週期；應用 references 連接，不製造全域 SSOT 資料庫。
- Feature／Label Registry、manifest、OOC memmap、immutable block reuse、capacity gate、purged split、safe loader 與 shadow boundary 是既有資產。
- SignalCombiner 已抽出相同分析流程；兩個可靠性／legacy backtest 政策仍不同，不能因同名而合併算法。
- tests 已有 DTO round-trip、推薦重算／負面證據、ML schema／loader／capacity／shared reuse 與 boundary 覆蓋。遷移以獨立 oracle 補缺，不刪測試換綠燈。

## 6. 主要風險與優先次序

1. **先保證一次執行的一致性**：同一 result ID 的 rows、cutoff、regime、exclusions、projection 不可來自不同 run。
2. **再修責任與 import**：沿 source → calculation → decision → execution result → persistence → presentation 分工；先抽真實 seam，之後才搬目錄。
3. **ML 不陪同大搬家**：Direct 來源 fingerprint、pickle/joblib import path、feature ordering 與 dtype 均可能因「只是重構」失效。
4. **歷史相容不代表歷史可信**：舊資料可讀，但缺可得時間或已知修訂／隔離的模型不能升格 verified，也不能回填當時未知資料。
5. **逐步收口相容層**：移除 runtime 舊路徑與重複 field mapping；保留必要的歷史格式 decoder 是格式支援，不是永久第二套 engine。

實作順序、驗收與 rollback 見 [MIGRATION_STRATEGY](MIGRATION_STRATEGY.md)，完整目標見 [TARGET_ARCHITECTURE](TARGET_ARCHITECTURE.md)。

## 更新記錄

交付檢查時 HEAD 已由其他工作更新至 `f3c3f23e`（只提交既有操作手冊變更）；本次來源評估仍以 `574de045` 為基線，兩者 production code 相同。起始手冊與 `=` 檔的 SHA-256 前後一致，本次未改它們。

- 2026-09-22：完成本次 HEAD 的靜態架構評估與 ML guard 查核；未宣稱全量功能測試通過。
