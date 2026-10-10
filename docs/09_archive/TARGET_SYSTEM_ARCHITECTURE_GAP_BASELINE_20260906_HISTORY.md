### 2026-09-06 八卡工程後的差距基線（歷史快照）

本節保留 2026-09-06 八卡工程後的差距基線，供追溯當時的 Current／Transitional 判讀；表內狀態不代表目前完成度。現況以[專案快照](../00_core/PROJECT_SNAPSHOT.md)、[目前架構](../01_architecture/system_architecture.md)及最新 QA 收據為準；目標設計以 [FINAL 目標架構](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 為準。

| 邊界 | 本輪已落地的工程能力 | 尚需完成的 Target／外部條件 |
|---|---|---|
| Data／Market／Recommendation | 更新與市場日期／品質 DTO；`recommendation-context.v1` 保存可得切片、設定、母體、Why Not 與內容指紋 | 正式來源 acceptance、精確 available_at、具 PIT 與版本的產業成分；指標計算版本與市場 context 輸入版本須連貫。缺 PIT membership 前不恢復歷史產業篩選 |
| Execution／Registry | `next-session-open.v2`、精確帳務、terminal／cancelled 揭露、frozen 成本基準；顯式 writer、實際內容冪等、版本隔離與 hash 驗證 | 固定組合共享現金、正式微結構／成交來源及 production canary。舊 run 不原地重算或升版本；可重跑不等於有效投資證據 |
| Portfolio／Watchlist | candidate-only append SQLite 帳本、補償事件、精確 read model、候選池副本 repository／migration 與 source_id | 正式 JSONL／JSON 預設切換、真實 Paper fills／cost、thesis／估值與來源接受；目前候選池沒有已刪除項目的歷史 membership |
| Desk／Workbench | 日期與品質防護、保存推薦／ledger adapter、完整 loop payload、stale callback 隔離；08-B 已接 main 保存推薦與 Workbench 新來源欄位重載 | 其餘 legacy typed sections 的完整 hydration 仍有限；正式來源切換須獨立 Gate，缺輸入不補安全等級 |
| Evidence | `evidence-lineage.v1` 與唯讀人工 review proposal；outcome 保留事件 tier、run／snapshot／event hash | 真實 producer lineage、自然前瞻時間、具名獨立 review 與 Formal acceptance。declared tier／reviewer 字串不是核准證明；提案不改 credit／lifecycle |
| Runtime | `runtime-state.v2`、未知來源、取消訂閱與受限 ID 去重；治理／營運兩平面維持分離 | store 讀取原因與 log rotation／generation 契約仍有限；EventBus 不提供 durable dispatch，scheduler／writer 審核仍獨立 |

演進以保存來源與受控 adapter 逐項接線，不建立全域記憶體 SSOT；本輪候選 schema／隔離 fixture 不授權正式 migration、promotion、broker order 或 scheduler。
