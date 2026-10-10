> **C1 歷史切片狀態**：本文只保存個別修補／審查時點的範圍與 evidence，不代表目前整體 Gate 狀態，也不構成新的工作授權。整體 C1 裁決見 [C1 checkpoint](C1_CHECKPOINT.md) 與 [Wave 6 最終 gate 報告](WAVE6_FINAL_GATE_REPORT.md)；目前狀態看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)，目標設計權威看 [FINAL_TARGET_ARCHITECTURE](../FINAL_TARGET_ARCHITECTURE.md)。

# C1 重開：sealed execution 的既有 consumer 契約缺口

FINDING_STATUS: CHANGES_REQUIRED

2026-09-23 在 Wave 6 接線前，R014、R016、R017 的獨立 Luna 工作者均在改動 production 前停止。C1 原測試 bundle 綠燈仍是有效的已執行證據，但缺少 consumer-required-field 與 heterogeneous historical read 的負例；原 `CHECKPOINT_STATUS: PASS` 已撤回。這是已核准最終架構的**實作完整性缺口**，目前不能把它當成已證明最終架構不可行，也不能繞過而啟動 Wave 6。

## 可重現的缺口

| Consumer | 已核實的必需資料／行為 | 目前封存缺口 |
|---|---|---|
| R014 scheduled forward candidate | 由真正保存的 artifact path/hash 讀 `close_price`、`price_change`、total/indicator/pattern/volume scores、理由、industry、完整 config、created/decision/available clocks；save-before-forward。 | `RecommendationItem` 只有 `rule_score` 等部分欄位；R011 event 無其餘同次列值，legacy façade 的 mutable capture 不進 artifact。producer 只接受舊 JSON envelope；不能另寫第二份 legacy artifact。scheduled wrapper 還在 execute 後另造 `scheduled_rec_...`，與 execute/ML receipt 的 `rec_...` 可能錯配。詳見 `R014_IMPLEMENTATION_REPORT.md` 與 C1 唯讀欄位盤點。 |
| R016 Advice/Desk/watchlist/evidence/historical display | 舊結果持續按原 bytes/DTO 行為顯示；新保存結果只讀同次值、receipt，不能 live lookup/recompute；讀取可涵蓋 legacy runs 與 canonical index。 | `RecommendationExecutionQueries` 只查 canonical index；新 execution 沒封存部分舊 DTO／config／context 欄。各 consumer 自行 fallback raw JSON 會重生多個 decoder。 |
| R017 replay bridge | 既有 snapshot 中 provider row 的 stored annotation、mode policy、parent/date refs 不因 typed bridge 消失。 | 現行 canonical item/ML refs 沒有通用歷史 annotation 的 typed 所有權；不能塞任意 `extended_attributes` 或猜 parent identity。R017 已依 SOL 指示停在改檔前。 |

`FINAL_DATA_FLOW.md` §2 要求 config、來源可得時間、negative evidence 在執行中取得，並在 worker 返回前封存；§3–4 要求 artifact → 對應 decoder → read view，舊結果缺欄標 unknown，禁止重查今天資料。`FINAL_TARGET_ARCHITECTURE.md` §4/§7 與 INV-07/10/11/13 也要求完整 execution、唯一 typed schema、讀取同一真值。故此發現屬上游 implementation/acceptance 不足，不是授權另建 DTO/writer、重算、回讀 `last_*` 或放寬 producer policy。

## SOL 即時裁決與修復順序

1. C1 與 Wave 6 release 撤回。R014/R016/R017 不得續作；R013 未派工。R014 worker 自報 `ARCHITECTURE_BLOCKER` 是它在原 R014 scope 內正確停下的狀態；program 層先列 `CHANGES_REQUIRED`，待上游證據證明可否在批准架構內修復，才決定是否需真正 architecture escalation。
2. 先核對每一舊 consumer 真正需要的欄位／時間／來源，以及目前 R008 contract、R009 codec、R011 capture、R012 query/persistence 的 schema gap；只擴充具名 typed owner，不引入泛用業務 mapping 或第二份結果真值。若增可選欄，按權威文件升 `schema_revision`，保留舊 revision／legacy decoder 讀取及原 bytes/hash。
3. 依順序修補 contract → codec → invocation capture → read/query/producer 的合法來源接線；每步須有獨立精確 oracle、A/B interleave、codec roundtrip、舊 artifact readback、ML ABI/receipt identity 與 save-before-forward 負例。只用隔離資料根；不能改推薦數值、排序或 ML 訓練／推論邊界。
4. 重跑完整 C1 與新增 consumer readiness test；獨立 Luna review + SOL 最終驗收後才能重新釋出 Wave 6。所有既有 R008–R012 PASS 報告保留為舊凍結版本證據，不得冒稱新 schema 已受其覆蓋。

本文件記錄缺口與 gate，**不是**新的目標架構；欄位 owner 與最小修補 scope 須由 SOL 對照 FINAL 文件和實際 consumer 逐項裁決。
