# Post-Refactor 產品 Roadmap 狀態紀錄

> 日期化工程／handoff 狀態、原始 30／60／90 日行動草案與更新流水帳已從核心入口移出；本文保留原文，不能作為目前狀態或優先順序依據。


> **2026-07-13 跨流整合狀態**：Evidence、資料可見性、PIT identity、broker latency、ML shadow metadata 與 dashboard contract 已完成工程鏈驗證。ML 決議仍是 `continue_shadow`、`formal_oos_allowed=false`，production blend alpha 固定為 0；P0 source／license 未 accepted，forward evidence 與 production automation 仍 pending。此整合不改寫 Advice、Portfolio、Exit 或正式 Recommendation 行為。
>
> **2026-07-12 純工程狀態**：Gate 2–7 的批准工程包已完成，涵蓋 Evidence/V3、P0 source contracts/shadow adapters、Paper Portfolio、Position Health/Exit、完整結構化傳統 ML shadow challenger、closeout verifier 與控制中心。這只代表 `pure_engineering_complete`；Gate 2 真實週期、Gate 3 逐來源接受、Gate 4/6 paper/exit 時間證據、Gate 5 人工 pruning 決議、Gate 7 shadow days/revalidation/promotion review 仍由 [External Validation Register](../06_qa/GATE_2_TO_7_EXTERNAL_VALIDATION_REGISTER.md) 管理，不能標成 formal product closeout。

> **建立日期**：2026-07-11
> **最後更新**：2026-09-17；本輪基線為已提交 `0219d709`，並承接 Qt 修復 `9a9e778b`，不新增產品版號。
> **當時定位**：截至 2026-09-17，原頁是安全重構完成後的產品方向權威；這份封存摘錄只保存當時版本與狀態，現行產品方向依 [Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md) 判讀。
> **工程落地**：未來六個月的交付物、依賴、測試與 Exit Criteria 以 [ROADMAP_6M_ENGINEERING.md](../00_core/ROADMAP_6M_ENGINEERING.md) 為準。
> **現況邊界**：目前完成狀態以 [PROJECT_SNAPSHOT.md](../00_core/PROJECT_SNAPSHOT.md) 為準；本文件中的 Target capability 不代表已實作。
> **安全邊界**：Investment Advice（投資建議）不等於 Broker Execution（券商執行）。本 Roadmap 不授權自動下單、保證獲利、production ML 或自動策略升降級。

> **2026-09-17 ABC bounded status**：A 的 Paper／calendar／Recommendation receipt 已完成
> bounded readback；9/17 Recommendation receipt 的 source、calendar 與全部 14 candidate file hash
> 已由 root 逐欄核對，calendar capture／availability 為 9/14，早於 9/17 candidate decision。
> 14 筆仍是 candidate-only；`1418` 只有 rejected sell、沒有 filled entry source，維持 unproven。
> Paper completion 仍要求同一 decision date 的 terminal run、latest／immutable phase receipt、
> `calendar.available <= decision` 與 source／state hash；heartbeat 舊 snapshot 不構成完成。
> official-events 的 `prior canonical raw lineage missing` 已定位並修復為 reader compatibility gap；A
> lineage path 跨檔 `8 passed`（prior-lineage 單檔含 3 tests），isolated next-publication real chain
> output-only readback（`output/qa/official_event_next_publication_output_only`）為 `40` chain／
> `28,636` events／`95` raw，coverage gap `0` 且 source bindings 均在 self-contained output 內。
> 先前 failed latest receipt 仍保留，正式 job 尚未重跑；不能歸類為 raw 缺件或純 external missing。
> 唯讀 ancestor custody review 亦核對 current 37＋ancestor 43 共 80 個 required raw hash、missing 0
> 且 raw bytes 全驗證，artifact
> `official_event_ancestor_custody_review.json` SHA256=`bc4607a46c10513700e1a9c531be81f502e87aac1219327b464f5f703207f280`。
> formal input readiness artifact 的原始 aware clock 為 `training_as_of=2026-09-17T11:19:45.4764372-07:00`、
> `created_at=2026-09-17T11:19:46.502565-07:00`；loader 以 `Asia/Taipei` 轉出 `training_as_of_date=2026-09-18`，
> readiness 為 `0/3`。三個 configured input path 仍為 `clock-20260819`／`prospective_output_not_published`；
> 這只代表 configured input 缺失，不能外推 D 槽沒有其他產物。
>
> B historical context assembly 已保留 observed market／stock date union 的 explicit empty slot，
> 並將 row-count、observed-calendar exact join、value completeness 與 horizon completeness 分開。
> `market_indices` DISTINCT 日期不是 official complete session calendar，故 horizon／formal／training
> credit 均為 false；bounded report `report_hash`=`sha256:06304a44340e3cfad623c2710e6bd84cd1d479950df0c344623ba3a2ad8f1b72` 是排除自身欄位後的
> canonical logical hash，JSON file SHA256=`f6c3d15bb04f93782c1b42a903a3934fdd30109f6039c0d541c3bf14a7fef698`。
>
> C 的 fit producer／persistence／CLI、artifact persistence 與 readback engineering 已 bounded
> accepted：fit runner／CLI／calibration／read service focused suite `41 passed`，wrong-scope
> empty-evaluation exit `2` 且不產生 evaluation／verified binding；source fingerprint artifact
> `c_personalization_fit_acceptance_20260917.json` SHA256=`d45033e0ea8a4c418150df685e96d26d7425872a6c633695f0aa752054f0a3d3`。
> 正式 D 的 real scope／delivery／human action／natural outcome 仍缺；fixture／replay／`natural sample=0`
> 不授予 formal／natural credit 或 V6 adoption。全局 ABC 仍 `in_progress`。

> **2026-09-15 Decision Workbench handoff**：`7e029933` 已提交並驗收 A/B/C continuity runtime／跨程序 readback；`9a9e778b` 另驗收 `MainWindow DeferredDelete`、busy 單次 close、實際 OS process exit `0`、TaskWorker／shutdown 25 passed、Update UI 84 passed、validator `25/0/4` 與全域 mypy 621。這些是 V4.1／V4.2 engineering slice 的工程證據，不是 V4 formal closeout：
> 將 rank、校準機率、成本後機率與 evidence／source／model／dataset metadata 分開呈現，
> 並在 Workbench 提供唯讀的機率依據詳情。`0d9d72af`／`cad07762` 的每日首屏與
> content-first 旅程、`25544142` 的可比產業讀模型、`421ab844` 的 typed learning projection、
> `53b456a0`／`ffb66c6f` 的唯讀 Decision → Outcome journey，以及 `5339230f` 的 Increment A
> continuity storage／caller 與 C 的 close／跨程序 readback 已有工程驗收；2026-09-15 R1 再把
> Journal due projection、exact candidate drilldown 與 shared Journey／controls 接回 Workbench，
> R1 的 bounded caller／readback 已驗收，但尚未全面接成完整 market→industry→stock→watchlist／
> portfolio 的整合使用流程。這些不宣稱真實市場→產業→個股端到端已驗收，
> 其中 `25544142` 的真實產業指數強弱與官方 TAIEX 5／20 日基準已可讀，純產業白名單已
> 排除槓桿／反向產品型指數；current representative-stock mapping、TPEX／興櫃 coverage
> 與 historical PIT membership 仍有限，不能把 current mapping 回填歷史。
> 不把 `available` 當 natural validation，也不以 fixture／shadow／scheduler Ready 取得
> V4.0 formal credit。完整 requirements／code／gap／acceptance matrix 見
> [終極決策工作台整合缺口矩陣](../06_qa/ULTIMATE_DECISION_WORKBENCH_2026_09_14.md)。

## 原始 30／60／90 日行動草案

## 14. 30 / 60 / 90 日行動

### 30 日：關閉重構、建立 Advice 契約

- 完成 Safe Refactor Closeout baseline 與 rollback point。
- 定義 Recommendation Advice / Portfolio Advice DTO 與語意規格。
- 將 Guided / Professional Mode 映射到同一核心引擎。
- 將 `NO_NEW_POSITION`、Why / Why Not / Risk / Evidence、target/current/gap 納入設計與測試計畫。

### 60 日：建立真實 Evidence operating loop

- weekly review、manual note、action item、append-only evidence、backup / rollback / recovery 形成真實節奏。
- 明確區分 historical replay、scheduled dry-run、forward、paper 與 live evidence。
- Production evidence scheduler 只在明確人工批准後開啟 write-mode；仍不交易、不套 lifecycle。

### 90 日：P0 Data diagnostics / shadow

- Corporate action、trading restriction、三大法人、信用交易、TDCC、PIT fundamentals 逐一完成 source contract。
- 先進 diagnostics / shadow，產生 coverage、quality、look-ahead 與 acceptance report。
- 未通過來源維持 `research_candidate`，不得接正式 score / Portfolio Advice。


## 產品 Roadmap 原更新記錄

## 更新記錄

- 2026-09-15：以已提交 `719cf7a4` 校準目前／下一步：C bounded canonical runner／training
  lineage／cutoff／ML boundary 已驗收（88 tests、508 files guard 0 violations、production-scoped
  mypy），P1 next-day inference／projection provenance 與 L official taxonomy source chain 尚待完成；
  Position Health、`user_declared`、
  Continuity Review Workbench R1、PIT reader／caller 與 BankTaiwan 受控 retry 已各自有 bounded
  acceptance；BankTaiwan 首次 05:50 實際 run 的 `failed_dependency` 已由 root guard 修復，
  受控 retry 成功但後續自然排程仍觀察。順序收斂為 C＋L → 整合使用流程 → V6 contract／離線
  設計與後續 real-user 驗證，不升級 maturity 版號。
- 2026-09-15（後續校準）：`0219d709` 已完成 C P1 next-day inference／projection provenance
  bounded engineering acceptance；`9a9e778b` 已完成 MainWindow `DeferredDelete` teardown、busy 單次
  close 與實際 OS process exit `0`。L source chain、跨頁整合、自然 evidence 與 V4 formal Gate 仍待驗收。

- 2026-09-14：新增 Decision Workbench integration handoff，記錄每日首屏／產業讀模型、
  typed learning projection、唯讀 Decision → Outcome journey 與 Increment A continuity
  contract 的工程驗收；明確把 Increment B caller、自然 forward／05:50 首次執行、PIT／source、
  observed fill 與 V4 formal maturity 保留為施工中或外部待驗，不改 V4 formal 定義。

- 2026-07-11：初版建立 Post-Refactor 產品方向權威；確立 bounded advice、Guided / Professional 共核、Portfolio Advice、Position Health / Exit、Data Source priority、Evidence operating loop、ML shadow-first 與 signal pruning 主線。
