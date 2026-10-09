# V2.1 至 V4.0 產品成熟度路線圖

> **內容基線**：2026-09-15（提交 `0219d709`，並承接 Qt 修復 `9a9e778b`）；2026-10-08 僅整理歷史交接與入口，未改成熟度標準。
> **狀態判讀**：成熟度標準與目前專案進度分開維護；目前狀態、阻礙與優先事項以 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md) 為準。2026-07 至 2026-08 的版本狀態快照，以及 2026-09-15 工程／產品交接，均已移至 [歷史狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md) 與[工程交接歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_ENGINEERING_HANDOFF_20260915_HISTORY.md)。
> **定位**：本文件是 V2.0 之後的長期產品成熟度與版本階梯權威；版號代表產品能力與證據成熟度，不代表功能數量。
> **工程順序**：未來六個月以 [ROADMAP_6M_ENGINEERING.md](ROADMAP_6M_ENGINEERING.md) 為準。
> **產品方向**：投資問題、能力演進與產品 Gate 以 [PRODUCT_ROADMAP_POST_REFACTOR.md](PRODUCT_ROADMAP_POST_REFACTOR.md) 為準。
> **歷史交棒**：V1.1 至 V2.0 的已完成演進見 [歷史封存](../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md)；目前成熟度標準由本文件定義，當前狀態以 Snapshot 為準。

---

## 1. 版號判讀原則

1. 工程完成不等於投資有效。
2. Dashboard、scheduler、ML 或資料表完成不單獨構成大版本。
3. Historical replay 不算 forward / live evidence。
4. Candidate source、readiness、shadow model 不算 formal decision capability。
5. V4.0 必須由長期 Forward / Paper / Live Evidence 支持，不能用規劃日期提前宣告。
6. 版本 closeout 必須有明確 non-goals、residual、rollback 與 evidence boundary。

## 2. Scoped Authority

| 主題 | 權威文件 |
|---|---|
| 目前狀態 | `PROJECT_SNAPSHOT.md` |
| 產品方向與產品 Gate | `PRODUCT_ROADMAP_POST_REFACTOR.md` |
| 六個月工程交付 | `ROADMAP_6M_ENGINEERING.md` |
| North Star / Evidence / Success Levels | `system_vision_specification.md` |
| Current Architecture | `system_architecture.md` |
| Target Architecture | `target_system_architecture.md` |
| 本文件 | V2.1-V4.0 maturity mapping |

## 3. 版本階梯總覽

| 版本 | 成熟度定位 | 最低成立條件 | 不代表 |
|---|---|---|---|
| V2.1 | Daily Usable Workbench | 單一日常入口、Advice Contract 可見、quality / warnings 完整 | 投資有效 |
| V2.2 | Evidence Operations | 真實 weekly review / action-item / evidence write / recovery 節奏 | production trading |
| V2.3 | Data Credibility | P0 source-by-source acceptance / limitation / rejection | candidate source 已進 score |
| V2.4 | Portfolio Coach Foundation | Risk budget、target/current/gap、Equal Weight benchmark、paper portfolio | 自動配置或 broker execution |
| V2.5 | Position Health Foundation | thesis / invalidation contract、health read model、manual decision journal | 完整 Exit effectiveness |
| V3.0 | Signal Effectiveness & Pruning | Score、component、gate、alert、Profile 可判讀並有 pruning 決議 | 所有 signal 有效 |
| V3.1 | Portfolio Advice Validation | sizing / bands / risk policy 有 OOS / forward / paper 成本後比較 | 保證優於 benchmark |
| V3.2 | Position Health & Exit Validation | Add / Hold / Reduce / Exit 有 lead-time、false rate、opportunity-loss evidence | 自動平倉 |
| V3.3 | ML Shadow / Champion-Challenger | rule baseline 可判讀；ML 只作 shadow 並具 registry / calibration / drift / rollback | production ML 或黑箱決策 |
| V4.0 | Evidence-Validated Investment Decision System | 長期 Recommendation / Portfolio / Exit / lifecycle evidence 支持決策品質與風險調整表現 | 保證獲利、自動交易、免人工審核 |

## 4. V2.x：Daily Usable、Evidence Operations、Data Credibility、Portfolio Foundation

### V2.1：Daily Usable Workbench

目的：把既有 Workbench 從 read-only 工程資訊入口，演進為能呈現 bounded Advice 的日常產品入口。

最低能力：

- Guided / Professional Mode 共用核心。
- Recommendation Advice Contract。
- `RESEARCH`、`ADD_CANDIDATE`、`HOLD`、`REDUCE_CANDIDATE`、`EXIT_CANDIDATE`、`AVOID`、`NO_NEW_POSITION`。
- Why / Why Not / Risk / Evidence / quality / strategy / data date。
- Portfolio Advice 最低欄位：target/current/gap；可先為 read-only / paper。

Closeout Gate：Advice 可拒絕、可重算、可回溯；UI 不直接計算；不串 broker。

> 歷史狀態快照（2026-07-12）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

### V2.2：Evidence Operating Loop

目的：讓 Evidence 不再只有 dashboard / dry-run，而形成真實 weekly review、manual note 與 action-item rhythm。

最低能力：

- 真實 weekly periods 與人工 review。
- append-only evidence / review artifact。
- dry-run → working-copy → approved evidence write-mode。
- backup / rollback / recovery。
- replay / dry-run / forward / paper / live tier 分離。

Closeout Gate：production evidence scheduler 如獲批准只保存 evidence；不自動交易、不套 lifecycle action。

> 歷史狀態快照（2026-07-12）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

> 歷史狀態快照（2026-08-30）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

### V2.3：P0 Data Credibility

目的：逐一處理 Corporate Action、trading restriction、三大法人、信用交易、TDCC、PIT fundamentals。

最低能力：

- 每個 source 有 `source_id`、version、`as_of_date`、`available_date`、quality、license、rate limit、missing、look-ahead、eligibility。
- Diagnostics → Shadow → Evidence Review → Accepted Feature。
- Data Source Control Center 可見 freshness、coverage、quarantine、retry 與 downstream eligibility。

Closeout Gate：每個 P0 source 有 accepted / limited / rejected / deferred 決議；candidate 不冒充 formal。

> 歷史狀態快照（2026-07-12）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

> 歷史狀態快照（2026-08-30）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

### V2.4：Portfolio Coach Foundation

目的：從「推薦一批股票」演進為 risk-budgeted Portfolio Advice。

最低能力：

- Portfolio Risk Budget。
- `target_weight_bp` / `current_weight_bp` / `weight_gap_bp`。
- Equal Weight benchmark。
- Rebalance bands、minimum trade、turnover、cooldown。
- Paper Portfolio、execution feasibility、Trade Import / Decision Journal foundation。

Closeout Gate：能安全輸出 Portfolio Advice 或 `NO_NEW_POSITION`；不串 broker。

### V2.5：Position Health Foundation

目的：建立 thesis-based Health / Exit 的資料與狀態契約。

最低能力：

- Entry thesis、invalidation、holding horizon、review date。
- HEALTHY / WATCH / REDUCE_CANDIDATE / EXIT_CANDIDATE / CLOSED。
- Hard Risk、thesis、relative、time、portfolio、data、restriction reason categories。
- Manual override / decision journal / source trace。

Closeout Gate：每個 transition 可解釋、可回溯；不自動平倉。

> 歷史狀態快照（2026-07-12）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

**Paper baseline 補充（2026-07-12）**：V2.4 已用 `scheduled_rec_20260712_051002` 建立第一個真實 saved-Recommendation paper baseline，3 筆 allocation 的紙上可執行總額為 NT$159,000、殘餘現金 NT$341,000；V2.5 已由相同 artifact 建立 3 筆 `WATCH` health baseline，並將 thesis / invalidation / horizon / review date 保留為必填人工欄位。兩者均不寫持倉 DB、不下單、不自動 action；尚缺後續交易日 paper evidence、成本後 benchmark、人工 thesis 與 state transition，不能 formal closeout。證據見 `docs/06_qa/V2_4_PAPER_BASELINE_2026_07_12.md`、`docs/06_qa/V2_5_POSITION_HEALTH_BASELINE_2026_07_12.md`。

> 歷史狀態快照（2026-08-30）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

## 5. V3.x：Signal、Portfolio、Exit、Pruning、ML Shadow、Paper Validation

### V3.0：Signal Effectiveness & Pruning

目的：回答 TotalScore、component、gate、alert 與 Profile 是否有用。

最低證據：

- Forward / benchmark / industry / concept excess。
- MAE / MFE、hit、payoff、bucket monotonicity、Precision@K。
- Fixed threshold robustness、component ablation、regime / liquidity stability。
- Signal / gate / alert / Profile 的 retain / restrict / downweight / retire 決議。

現況邊界：2026-07 的 score effectiveness / V3 engineering candidate 只代表 read-only scaffold 與 `ready_for_manual_validation`，不是本版本 closeout。

**Week 1 人工驗證（2026-07-12）**：真實 working-copy 只有 3 筆有 score 的事件，12 個 outcome 全為 missing，另有 1,134 個事件缺 `score_bp`；所有 score bucket 均未達 30 筆成熟樣本門檻。因此本輪正式決議為 `DEFER_ALL_PRUNING_DECISIONS`，不調整 score、threshold、Profile、gate、alert 或 lifecycle。證據見 `docs/06_qa/V3_0_WEEK1_MANUAL_VALIDATION_2026_07_12.md`。

> 歷史狀態快照（2026-07-12）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

### V3.1：Portfolio Advice Validation

目的：驗證 Portfolio policy 是否在成本、風險與限制後比 Equal Weight 更合理。

最低證據：cost-adjusted / excess return、Sharpe、Sortino、MDD / duration、CVaR、turnover、cash、concentration、diversification、exposure stability、paper vs research gap。

方法次序：Equal Weight → Score Weight / Inverse Volatility → Risk Budgeting / HRP / shrinkage → 複雜 optimizer。Expected Return 不可靠時，不使用 unconstrained mean-variance 作正式基準。

### V3.2：Position Health & Exit Validation

目的：證明 Add / Hold / Reduce / Exit 不只是規則存在，而有實際 risk / opportunity 取捨。

最低證據：alert lead time、alert 後 MAE、false-positive / false-negative、avoided loss、opportunity loss、early exit、post-exit、Add / Reduce outcome，並依 regime / liquidity / reason / quality 分層。

### V3.3：ML Shadow / Champion-Challenger

目的：ML 只在 V3.0 baseline 可判讀後，研究 ranking、calibration、meta-labeling、downside risk 與 drift。

必要治理：Feature / Label / Dataset / Model Registry、purged / embargo split、calibration、importance、shadow prediction、drift、Champion / Challenger、Promotion Gate、rollback。

Closeout Gate：最多提出繼續 shadow、拒絕或人工 promotion review；不自動上線、不改 scheduler / Portfolio / lifecycle、不交易。

> 歷史狀態快照（2026-08-30）已移至 [版本狀態歸檔](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md)；目前狀態請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md).

## 6. V4.0：Evidence-Validated Investment Decision System

V4.0 是長期 maturity milestone，不是目前六個月工程承諾。只有以下條件由長期 Forward / Paper / Live Evidence 支持時才成立：

1. Recommendation ranking / Advice 在合理 benchmark、industry / concept 與 liquidity 調整後具可判讀價值。
2. Portfolio Advice 扣除成本後有合理穩定性，且相對 Equal Weight 的增益與代價可解釋。
3. 重大回撤、CVaR、concentration 與 exposure 可被 policy 控制。
4. Alert / Exit 有 lead-time、avoided-loss 與 opportunity-loss 證據。
5. Research-to-paper/live gap 可由 execution、資料、regime、策略與人工 override 解釋。
6. Signal / strategy decay 可被發現；無效 feature / Profile / model 會被限制或退休。
7. 持續調參受到 Experiment Contract、search budget、OOS 與 pruning 約束，沒有用過度擬合換取版號。
8. Model / source / policy 出現 drift 或 failure 時，可回到 last approved champion。

目前已接上的 `baldr-forward-outcomes-daily` 只是第 1、2、4、5 項的資料累積入口：
它以固定的 close-to-close basis、自然交易日與明確的事件／日期上限寫入
`evidence_outcomes`，並保留缺價、benchmark、成本與成熟度缺口。producer 的成功不等於
上述八項已達標；未具備的成本後績效、Paper／Live 成交、Exit、drift、OOS 與 rollback
證據仍須自然累積並逐項驗收。

每日推薦 producer 的 cohort identity 已固定保存策略版本、`TAIEX` benchmark、20 日主要
horizon 與 `gross-close-to-close-no-cost-v1` 成本標籤；no-cost 標籤只代表尚未扣除費稅、
滑價與流動性成本，evaluator 會保留警告，不能被當成第 2 項的成本後比較。

V4.0 仍不代表：

- 保證獲利。
- 自動交易或 broker order。
- AI 報牌。
- 免人工審核。
- 所有市場環境都有效。

## 6A. 2026-09-15 工程／產品版本分流

> 此為 2026-09-15 的工程交接與當時下一步，已移至[歷史交接紀錄](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_ENGINEERING_HANDOFF_20260915_HISTORY.md)。
> 目前狀態與優先順序請看 [PROJECT_SNAPSHOT.md](PROJECT_SNAPSHOT.md)；本文件後續章節只用於理解版本成熟度標準。

## 7. 版本 Promotion / Demotion 規則

### Promotion

- 工程 DoD、資料 Gate、Evidence Gate、風險與 rollback 全部成立。
- 版本 artifact 可追溯 data / strategy / policy / model / decision date。
- 人工 review 明確接受 limitations。

### Demotion / Hold

- Evidence 衰退、source quality 降級、research-to-live gap 擴大或風險超標時，版本可限制適用 regime、降級 Guided exposure 或停止 Promotion。
- 單次異常不足以直接退休；需依預先定義的 evidence policy。

### Retirement

- 保留歷史 artifact、effective date、reason、replacement / fallback 與 rollback reference。
- 不刪除歷史 Research Run / Evidence 以美化結果。

## 8. Deferred / 明確不納入近期版本

- Production broker execution / 自動下單。
- AI 自動 Strategy Lifecycle action。
- 強化學習核心主線。
- GPU-first Portfolio optimization。
- 未量測就進行 SQLite split / async rewrite。
- 未治理資料直接進 `ScoringEngine`。
- LLM output 作為統計 evidence。
- DL 作為近期核心推薦引擎。

## 9. 更新規則

本文件只在 maturity definition、版本 Gate 或跨版本責任改變時更新；單一 bugfix、dashboard polish、dry-run、candidate adapter、readiness scaffold 或一次 replay 不改變版本 closeout。

---

## 更新記錄

- 2026-09-15：以已提交 `719cf7a4` 的 bounded acceptance 校準 V4.1／V4.2 工程軌與
  V5／V6 handoff；C bounded canonical runner／training lineage／cutoff／ML boundary 已驗收
  （88 tests、508 files guard 0 violations、production-scoped mypy），P1 next-day inference／
  projection provenance 與 L source chain 尚待完成；Position Health、`user_declared`、Continuity
  Review Workbench R1、PIT reader／caller 與 BankTaiwan 受控 retry 已各自驗收。下一順序為
  C＋L → 整合使用流程 → V6 contract／離線設計與 real-user 驗證。首次 05:50 run 的
  `failed_dependency` 已由 root guard 修復，受控 retry 成功但後續自然排程仍觀察；V4.0 formal
  Gate 不變，不新增 maturity 版號。
- 2026-09-15（後續校準）：`0219d709` 已完成 C P1 next-day inference／projection provenance
  bounded engineering acceptance；`9a9e778b` 已完成 MainWindow `DeferredDelete` teardown、busy 單次
  close 與實際 OS process exit `0`。L source chain、跨頁整合、自然 evidence 與 V4 formal Gate 仍待驗收，
  不升級 maturity 版號。
- 2026-09-14：補入已驗收的 content-first／產業／learning projection／唯讀 outcome journey／
  Increment A 工程切片與 Increment B 施工邊界；標明臺銀 05:50 registration 與首次自然執行
  的差異，並保留 natural／PIT／source／observed cost 與 V4.0 formal maturity 的原 Gate。
- 2026-09-14：明確把 V4.1／V4.2 定位為工程軌，將可並行的 V5 full decision experience
  與 V6 evidence-driven personalization 移交 Product／6M Roadmap；不改 V4.0 formal
  maturity Gate。
- 2026-08-29：補入當日 historical maturity overlay；Evidence 分層為 formal credit 未授予／歷史 working-copy 1/3／UI projection 3/3／pending 9，P0 為 13/13 machine evidence 但 acceptance 0，Paper 為 21/21 但 fills／cost 0，Formal inputs 0/3。ML storage headroom 已恢復但不改任何版本 Closeout Gate。
- 2026-08-30：追加 Evidence 自然 collection 後，current pending sidecar 為 10；仍不授予 formal credit、scheduler 或任何版本 Closeout Gate。
- 2026-07-12：記錄 V2.2 engineering readiness 與三週 weekly review runbook；weekly `0/3 waiting_for_time`、multi-day `3/3 ready`、scheduler 未核准，不能 formal closeout。
- 2026-07-12：修正 V2.1 為 engineering readiness complete / `awaiting_release_owner_confirmation`；保留 `592d3db` safeguards、focused suite、人工 UI 文案 smoke 與 rollback 證據，待 release owner 實際填寫 owner / timestamp / decision 後才可正式 closeout。
- 2026-07-11：依產品成熟度重整 V2.1-V4.0；V2.x 聚焦 Daily Advice / Evidence / Data / Portfolio foundation，V3.x 聚焦 Signal / Portfolio / Exit effectiveness、pruning 與 ML shadow，V4.0 改以長期 evidence-validated investment decision system 判定。
