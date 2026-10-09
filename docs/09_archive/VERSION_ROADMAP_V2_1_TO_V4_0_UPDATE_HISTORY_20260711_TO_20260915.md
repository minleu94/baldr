# V2.1–V4.0 版本路線更新歷史（2026-07-11 至 09-15）

> 本文保存成熟度路線文件曾附加的日期化狀態與 handoff；版本成立條件仍以 [V2.1–V4.0 Maturity Roadmap](../00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md) 為準，目前狀態以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準。

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
