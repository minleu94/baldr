# 跨工作流整合 QA 索引

> [回 QA 證據導覽](README.md)。本索引只供導覽。每份收據仍須按自身日期、範圍與限制判讀；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。索引不代表 Gate 通過，也不改變 QA 原件的生命週期。

## 整合主題地圖

| 主題 | 建議閱讀順序 | 範圍提示 |
|---|---|---|
| WP1–WP5 工作包 | [WP1–WP5 工作包收據索引](#wp1wp5-package-evidence-index) → [整合驗收清單](WP5_INTEGRATION_CHECKLIST_20260928.md) | 整合清單固定在 2026-09-28 的 HEAD；它不是目前整體狀態，也不代表全部工作包已通過。 |
| Task Loop integration | [08-B 中央整合與殘餘限制](TASK_LOOP_08_HANDOFF.md) → [01–07 歷史交接](../09_archive/README.md#2026-10-08-task-loop-01-07-historical-handoffs) | 01–07 的 bounded 工程收據已由 08-B 整合；正式來源接受、自然前瞻、真實 Paper fills、具名 Formal review 等外部 Gate 仍未因此完成。 |
| Continuity／跨頁 Decision Journey | [R1 Workbench QA](CONTINUITY_REVIEW_WORKBENCH_R1_QA_2026_09_15.md) → [9/15 bounded MainWindow acceptance 歷史](../09_archive/CROSS_PAGE_DECISION_JOURNEY_MAINWINDOW_2026_09_15.md) → [仍開放的跨頁 acceptance plan](CROSS_PAGE_DECISION_JOURNEY_ACCEPTANCE_PLAN_2026_09_15.md) → [9/14–15 bounded journey 收據歷史](../09_archive/README.md#2026-10-08-early-decision-and-industry-journey-receipts) → [pre-R1 gap audit 歷史](../09_archive/CONTINUITY_REVIEW_LOOP_GAP_AUDIT_2026_09_15.md) | Bounded MainWindow acceptance 使用 synthetic Market／Industry 與 Portfolio fixtures；它與 9/14 的有限 write-path／read-model／UI／storage activation／shutdown slices 都不關閉 open acceptance plan。R1 exact reminder projection 已有 QA；自然／正式 outcome 另行判讀。舊 gap audit 是 R1 前快照，不能當目前待辦。 |
| 2026-09 LUNA 三線整合歷史 | [A／C handoff 與 integration closeout](../09_archive/README.md#2026-10-08-luna-three-line-integration-history)；[B handoff](LUNA_B_HANDOFF_2026_09_07.md) 與 [pre-integration review](PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md) 保留原文 | A／C 與最終 closeout 已歸檔；B／pre-integration review 仍由 repository inventory／repo-map audit 直接讀取。 |

<a id="wp1wp5-package-evidence-index"></a>
### WP1–WP5 工作包收據索引

先看 [WP5 整合驗收清單](WP5_INTEGRATION_CHECKLIST_20260928.md)：它以固定 HEAD `2a85bc92019798668ef12f50ef87fb587d0dc58c` 彙整當時 WP1–WP5 的證據與缺口，不是目前 HEAD 的整體通過宣告。其餘收據只證明各自標示的 bounded 範圍；目前狀態請回到 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與更新的具名 QA。

| 工作包 | 收據 |
|---|---|
| WP1 | [Daily chain revalidation](WP1_DAILY_CHAIN_REVALIDATION_20260928.md) · [Partial industry capture sync](WP1_PARTIAL_INDUSTRY_CAPTURE_SYNC_20260928.md) · [Real-child rehearsal](WP1_REAL_CHILD_REHEARSAL_20260928.md) |
| WP2 | [Industry index current provenance](WP2_INDUSTRY_INDEX_CURRENT_PROVENANCE_20260928.md) · [Industry index UI observation](WP2_INDUSTRY_INDEX_UI_OBSERVATION_20260928.md) |
| WP3 | [Watchlist QA](WP3_WATCHLIST_QA_20260928.md) |
| WP4 | [Fail-closed validation](WP4_FAIL_CLOSED_VALIDATION_20260928.md) · [Personal model assessment readback](WP4_PERSONAL_MODEL_ASSESSMENT_READBACK_20260928.md) |
| WP5 | [Current checkpoint](WP5_CHECKPOINT_CURRENT_20260928.md) · [Integration checklist](WP5_INTEGRATION_CHECKLIST_20260928.md) · [HEAD gap and pending diagnosis](WP5_HEAD_GAP_AND_PENDING_DIAGNOSIS_20260929.md) · [Commit handoff](WP5_COMMIT_HANDOFF_20260929.md) · [Official daily capture validator](WP5_OFFICIAL_DAILY_CAPTURE_VALIDATOR_20260929.md) · [Personal current observed activity qualification](WP5_PERSONAL_CURRENT_OBSERVED_ACTIVITY_QUALIFICATION.md) |

## 近期與跨主題收據

| 要查的內容 | 證據入口 |
|---|---|
| 四用途整合、來源／ML/UI 的限界收尾 | [Astra engineering closeout（10/03–05）](ASTRA_ENGINEERING_CLOSEOUT_20261003.md) |
| Windows、資料、ML 與原生 UI 的三階段整合修復 | [Integration repair acceptance（10/02–03）](INTEGRATION_REPAIR_ACCEPTANCE_20261002.md) |
| V4.2 C 線每日決策工作台（9/12 歷史 handoff） | [封存 QA 原文](../09_archive/V4_2_C_DAILY_DECISION_WORKBENCH_QA_HANDOFF_2026_09_12_HISTORY.md) → [Coverage History Entry 123](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-123)；整體跨頁 acceptance plan 仍開放，見上方 Continuity／跨頁 Decision Journey。 |
| BALDR 9/25–26 整合與 readiness 日期快照 | [Archive 專區](../09_archive/README.md#2026-10-08-baldr-september-integration-closeout-and-readiness-history)；目前產品／排程／ML 狀態看 Snapshot 與近期收據 |
| V6 Personalization contract 與工程／自然 evidence 分界 | [詳細 contract 與 C 線 completion audit](V6_PERSONALIZATION_CONTRACT_PLAN_2026_09_15.md)；目前產品／採用狀態以 Roadmap 與 Snapshot 為準 |

## 其他常用路徑

- **2026-09 決策工作台與 continuity dated audits**：查 [Archive 專區](../09_archive/README.md#2026-10-08-decision-workbench-and-continuity-audit-history)；當時的 gap 與 next-increment 判讀不代表目前優先序，現在狀態回 Snapshot／Roadmap。
