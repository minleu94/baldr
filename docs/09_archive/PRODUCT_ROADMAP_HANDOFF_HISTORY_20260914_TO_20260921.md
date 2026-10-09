# Product Roadmap 日期化交接紀錄（2026-09-14 至 09-21）

> 本文保存當時的 V4.1／V4.2 工程觀測、V5／V6 handoff 與驗收細節，不代表目前進度或下一步。現況請看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，工程順序請看 [6M Engineering Roadmap](../00_core/ROADMAP_6M_ENGINEERING.md)，產品邊界請看 [Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)。

### 10.1 2026-09-14 Decision Workbench integration handoff

本節把目前的工程工作與長期產品版本分流，不取代 `PROJECT_SNAPSHOT.md` 的運行狀態或
`ROADMAP_6M_ENGINEERING.md` 的交付順序。

#### V4.1／V4.2 engineering track

- **V4.1 engineering**：Advice／Portfolio presentation 的 rank／probability 分離、
  decision date／data-as-of／horizon／sample、model／dataset／source、evidence kind 與
  missing／warning 的唯讀投影已驗收；每日首屏 content-first、可比產業讀模型、Research
  fallback 的唯讀邊界與 learning evidence view 已有可核對工程切片。`7e029933` 已包含
  continuity runtime／跨程序 readback；`9a9e778b` 另完成 `MainWindow DeferredDelete`、busy
  單次 close 與實際 OS process exit `0` 的 teardown 工程驗收；R1 已完成 continuity review 的 Workbench
  state projection 與 exact shared Journey caller，Position Health source-backed read model
  也已由 `5a3ed5db`／`ef594007` 驗收。C 的 P1 next-day inference／projection provenance
  bounded engineering slice 已由 `0219d709` 驗收；下一個施工面是 L 官方 taxonomy source chain，
  再做跨頁一致性及推薦／決策／outcome 追溯的整合驗收，不是把既有 read-only slice 重寫成正式決策。
- **V4.2 engineering**：保留既有 05:40 forward outcome → 05:45 shadow learning 的
  自動候選採用／回退 policy、frozen challenger、active monitor、receipt 與 rollback。
  routine shadow adjustment 不要求使用者每日人工批准；只有超出既有 shadow／正式決策
  影響範圍才另立具名 promotion／review Gate。`421ab844` 的 typed verifier projection
  已驗收；就 2026-09-14 臺銀正常 shadow lane 觀測，natural sample 為 `0`、receipt 為
  `retain_current`，legacy 50bp lane 另行判讀且可能 `blocked`。沒有 verifier
  的 natural receipt 仍只可顯示 unknown，source `available`、hash 或 evidence kind 不是
  authority；05:50 臺銀 task 的註冊／可觸發狀態不等於自然證據。首次實際 run 已於
  `05:50:03–05:50:05 -07:00` 以 `failed_dependency` 結束，root guard 已由 `086ba60c` 修復，
  `0aaf0dff` 受控 retry 已成功但仍為 `completed_waiting_natural_maturity`；後續正常排程仍須
  觀察。這些是既有 shadow／projection observation；截至 `0219d709`，C 的 bounded canonical
  learning runner／training lineage／cutoff／ML boundary 與 P1 next-day inference／projection
  provenance 已提交並驗收（75 tests、mypy 9 source files、ML guard 509 inspected／0 violations）；
  不同 training／inference source／PIT hash 依 shared schema／transform compatibility 核對，
  immutable receipt 與 normal UI UUID→save→exact readback 可回查，identity conflict fail-closed、
  rule selection authority 保留。L 的官方 taxonomy source chain 仍待完成。
- **成本接線**：產品工程先消費臺銀 `estimated_research_only` 的成本 policy，形成可判讀
  的估算淨效用（`8acf29f0`／`b39fd399`）；observed fills、partial fill、broker 對帳與
  實際滑價另列 execution-realism／formal Gate，不阻擋 content-first 唯讀體驗，也不是
  每日 learning 的前置條件。

#### V4 formal maturity boundary

V4.0 仍由長期自然 Forward／Paper／Live evidence、P0 source acceptance、PIT／available-
time、成本／成交、decision journal、具名 review、calibration／downside／regime stability
與 rollback Gate 判定。V4.1／V4.2 engineering 完成、UI 詳情、fixture、historical replay、
shadow receipt 或 Task Scheduler `Ready` 都不會自動升級 V4.0，也不授權 broker。

#### V5 full decision experience

V5 是把已驗收的 content-first daily conclusion、候選／持倉、market→industry→stock→watchlist／
  portfolio read-only journey、Why／Why Not／Risk、研究 fallback、既有 Journal／Evidence／
  Portfolio ledger continuity 與 T+N outcome view 收斂成單一路徑。V5 的 UX／唯讀資料旅程、
  decision continuity 與 V4 formal evidence accumulation 可並行；V4 formal 不會阻擋現在先
  交付真實唯讀 content。`7e029933` 的 A/B/C continuity runtime evidence 與跨程序 readback 已具備；`9a9e778b` 補上 Qt close readback，R1 已接上
  continuity review Workbench state projection 與 shared product caller，Position Health read
  model 也已驗收；完整 market→industry→stock→watchlist／portfolio 的跨頁一致性及推薦／
  決策／outcome 追溯整合仍按下列順序施工。Evidence 不足時只限制 Advice scope，
  轉 `RESEARCH`／`NO_NEW_POSITION`。
既有每日 shadow policy 內的 candidate adoption／rollback 仍可自動執行，不能跨到正式
Recommendation／Portfolio 或 broker。

#### 2026-09-21 V5 日常操作與可讀性工程 handoff

本輪完成一個 bounded UI engineering slice：首頁先呈現每日重點與下一步，候選／研究報告／持倉提供原因、資料日、來源與進階入口，左側導覽分成日常／進階研究／系統維護，研究報告深頁按需繪製並保留缺值 fallback。這些是既有唯讀資料的可用性整理與 frozen QA evidence，不改 Advice Policy、推薦保存／delivery ACK／Journal context、Portfolio allocation、scheduler 或正式資料寫入。精選 integration 已以 `299 passed` 完成，pytest cache permission warning 另列；跨頁一致性、推薦／決策／outcome 完整追溯、formal evidence 與 V6 user-level personalization 仍是本節原定後續 Gate。

#### V6 evidence-driven personalization

V6 的 contract、population baseline、歷史回放、離線 learning／calibration、negative evidence、
guardrails、drift 與 rollback 設計可在 V5 continuity 尚未完整收斂前先行；實際 user-level
projection 的效果宣稱與採用，仍須等真實 user decision／outcome sample 依既有門檻驗證。每個
projection 都需與 population baseline、sample、calibration、negative evidence、drift 與
rollback 分開保存。V6 不保證報酬、不隱藏缺漏、不自動調倉／下單；目前仍是後續產品方向，
不是本輪工程完成狀態。

#### 2026-09-15 `user_declared` Increment 2 工程驗收

`user_declared` 持倉研究層已完成 bounded engineering acceptance：Portfolio 右側提供
獨立 research-only lane，保存使用者聲明的股票、整數股數、Decimal 成本、聲明日期、
備註與研究假設，並以 append-only revision history、PIT cutoff、source quality／hash、
historical availability custody 與 real condition／saved-recommendation baseline checks
建立研究 read model。它不冒充 fill／verified entry、不進 Paper／formal effectiveness，
也不開啟 broker、auto action 或 calibration credit。實際 writer→reader、busy close、
1366×768／1700×1100 UI 與 focused／required QA 見
[Increment 2 QA](../06_qa/USER_DECLARED_HOLDING_RESEARCH_INCREMENT_2_QA_2026_09_15.md)。

#### 2026-09-15 下一工程順序（基線 `0219d709`）

自然 forward 收集、同 scope calibration 與 05:50 後續正常排程是獨立的持續觀察線：首次實際
run 已以 `failed_dependency` 結束，root guard／受控 retry 已處理，但現行 normal lane 的
natural sample 仍為 0，不能因此宣稱 V4 formal 完工；策略／模型效果也不要求逐日單調改善。
工程增量依序為：

1. **L official taxonomy source chain**：C 的 bounded canonical runner／training lineage／cutoff／
   ML boundary 與 P1 next-day inference／projection provenance 已由 `0219d709` 完成；P1 receipt
   已分離 training／inference source／PIT hash，核對 shared schema／transform compatibility，
   並可由 normal UI default UUID→save→exact readback 及 conflict fail-closed 路徑追溯。下一步由
   L 補官方 taxonomy raw producer／v3／publisher／reader／caller，並完成 PDF／preopen
   completion-time 修正；不以既有 shadow receipt 或 natural sample `0` 折抵自然／正式 Gate。
2. **整合使用流程**：在已驗收的 Position Health、`user_declared`、Continuity Review Workbench
   R1 與 PIT reader／caller bounded slices 上，接通 market→industry→stock→watchlist／portfolio
   的同一 identity read-only journey，完成跨頁一致性及推薦／決策／outcome 追溯的整合驗收；
   不新增平行 DB、不開啟 broker／auto action，也不重做 R1。
3. **V6 evidence-driven personalization**：可先建立 contract、population baseline、歷史回放、
   離線 learning／calibration、negative evidence、guardrail、drift 與 rollback；整合流程與
   真實 user decision／outcome evidence 則決定何時可宣稱效果、採用 user-level projection。
   V6 不保證報酬、不自動調倉／下單。
