# V2.1–V4.0 Roadmap 工程交接紀錄（2026-09-15）

> 本文件保存當時的工程分流、觀測與下一步記錄；內容只供歷史追溯，不代表目前順序或版本狀態。

## 6A. 2026-09-15 工程／產品版本分流

本 companion 仍只負責 V2.1 至 V4.0 的 maturity definition；本次新增的 V4.1／V4.2
是工程軌名稱，不是本文件新增或提前宣告的 maturity version：

- **V4.1 engineering** 的 bounded slice 已驗收：`0d9d72af`／`cad07762` 的 content-first
  每日首屏、`25544142` 的可比產業讀模型、`421ab844` 的每日 evidence／typed learning
  projection，以及 `53b456a0`／`ffb66c6f` 的唯讀 Decision → Outcome journey。rank／
  probability／confidence 分離、model／dataset／source／日期／樣本 provenance、Research
  fallback 與臺銀 `estimated_research_only` read model 仍保持 read-only；`7e029933` 另有
  A/B/C continuity runtime／跨程序 writer→reader readback 工程實證，`9a9e778b` 再補
  `MainWindow DeferredDelete`、busy 單次 close、實際 OS process exit `0` 的 teardown；`5a3ed5db`／`ef594007` 已驗收
  Position Health source-backed read model，`031e11ab` 已驗收 Continuity Review Workbench R1，
  C 的 P1 provenance 已驗收；下一個施工面是 L official taxonomy source chain 與後續跨頁一致性／
  推薦／決策／outcome 追溯整合，不提前宣稱 V5。
- **V4.2 engineering** 的既有 shadow／custody slice 有 bounded acceptance，涵蓋 05:40→05:45 自然時間
  邊界、typed natural authority projection、frozen challenger、既有 policy 內的自動
  shadow adoption／rollback、active monitor 與 durable receipt；`8acf29f0`／`b39fd399`
  的臺銀成本／排程 lane 也保持隔離。沒有 verifier 時 natural status 必須 unknown；
  source `available`、hash 或 evidence kind 不等於 authority。就 2026-09-14 臺銀正常 shadow
  lane 觀測，natural sample 為 `0`、`retain_current`；legacy 50bp lane 可為 blocked；05:50 task
  registration／Ready 不等於自然證據。首次實際 run 已於 `05:50:03–05:50:05 -07:00` 以
  `failed_dependency` 結束，root guard 已由 `086ba60c` 修復，`0aaf0dff` 受控 retry 成功但
  仍為 `completed_waiting_natural_maturity`，後續正常排程持續觀察。這些是既有 shadow／
  projection observation；截至 `0219d709`，C 的 bounded canonical learning runner／training
  lineage／cutoff／ML boundary 與 P1 next-day inference／projection provenance 已提交並驗收
  （75 tests、mypy 9 source files、ML guard 509 inspected／0 violations）。training／inference
  source／PIT hash 分離，shared schema／transform compatibility、immutable receipt、normal UI
  UUID→save→exact readback 與 identity conflict fail-closed 可核對，rule selection authority 保留。
  L 的官方 taxonomy source chain 仍待完成。
- **Decision continuity**：`5339230f` 的 Increment A append-only storage contract、
  `7e029933` 的 A/B/C continuity runtime／跨程序 writer→reader readback、`9a9e778b` 的 Qt teardown／close lifecycle、
  `031e11ab` 的 Continuity Review Workbench R1 與
  `5a3ed5db`／`ef594007` 的 Position Health source-backed read model 均已驗收；完整跨頁一致性
  及推薦／決策／outcome 追溯整合仍待驗收。
- **`user_declared` research lane**：2026-09-15 Increment 2 已完成 bounded engineering
  acceptance。Portfolio 內的使用者聲明持倉以獨立 append-only revision／PIT read model
  提供研究檢視、聲明成本資訊性觀察與人工 review；不提升為 V2.5／V3.x／V4.0 maturity，
  不進 Paper／formal effectiveness，也不授權 broker 或 auto action。QA 與 rollback 邊界見
  [Increment 2 QA](../06_qa/USER_DECLARED_HOLDING_RESEARCH_INCREMENT_2_QA_2026_09_15.md)。
- **V5／V6** 是 Product Roadmap 的後續 handoff，不屬於本文件的 V4.0 maturity closeout。
  V5 的 content-first／真實唯讀 journey／decision continuity 可與 V4 formal evidence
  accumulation 並行；V6 的 user-level evidence-driven personalization 則需在 V5 的
  decision／outcome continuity 上另建治理，兩者都不授權 broker 或自動交易。

2026-09-21 的「V5日常操作與可讀性工程」是上述 handoff 的 bounded engineering evidence：首頁、工作區分層、候選／報告／持倉摘要、推薦／回測進階入口、按需圖表與白話錯誤已完成 frozen review；after perf 僅是小型隔離 fixture 的比較，整合 route 已以 `299 passed` 完成，pytest cache permission warning 另列。它不新增版本 maturity、不關閉 V4.0、不授予 formal／natural evidence，也不把 V6 personal sample 或 learning 效果視為完成。

本次下一工程順序為：1. **L official taxonomy source chain**（C bounded canonical runner／training
lineage／cutoff／ML boundary 與 P1 next-day inference／projection provenance 已由 `0219d709` 驗收；
P1 receipt 的 training／inference source／PIT hash 分離、shared schema／transform compatibility、
immutable receipt、normal UI UUID→save→exact readback 與 conflict fail-closed 均已具工程證據；L 官方
taxonomy raw producer／v3／publisher／reader／caller 及 PDF／preopen completion-time 修正仍待完成）；
2. **整合使用流程**（在已驗收的
Position Health、`user_declared`、Continuity Review Workbench R1 與 PIT reader／caller 上，完成
market→industry→stock→watchlist／portfolio 的跨頁一致性及推薦／決策／outcome 追溯整合）；
3. **V6 evidence-driven personalization**（先建立 contract、population baseline、歷史回放、
離線 learning／calibration、negative evidence、guardrail 與 rollback；以後續 user decision／
outcome sample 決定效果宣稱與採用）。L source chain 尚未完成，不以既有 shadow receipt 或 natural
sample `0` 折抵；natural forward、同 scope calibration 與 05:50 後續正常排程另列觀察線，
不宣稱 V4 formal 完工。策略評估效果不保證逐日單調改善，正式交易資格不作所有研究功能的前置；
V5／V6 仍按 Product／6M Roadmap handoff，不為小 patch 發新版。

工程詳情與 acceptance sequence 以 [ROADMAP_6M_ENGINEERING.md](../00_core/ROADMAP_6M_ENGINEERING.md)
及 [終極決策工作台整合缺口矩陣](../06_qa/ULTIMATE_DECISION_WORKBENCH_2026_09_14.md)
為準；V4.0 的 formal Gate 仍只能由本節長期 evidence 判定。
