# 資料、ML 與來源治理 QA 索引

> [回 QA 證據導覽](README.md)。本索引只供導覽。每份收據仍須按自身日期、範圍與限制判讀；目前狀態看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)，操作看 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。索引不代表 Gate 通過，也不改變 QA 原件的生命週期。

## Data Governance、來源與 ML 主題地圖

| 主題 | 建議閱讀順序 | 範圍提示 |
|---|---|---|
| R026／R031 依賴重構 | [R031 最終 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) → [31-task evidence index](R031_TASK_REPORT_INDEX_DRAFT_20260925.md) → [R026 證據家族導覽](R026_EVIDENCE_GUIDE.md) → [R026 exact allowlist](ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md) → [source revision aggregate](R026_SOURCE_REVISION_EVIDENCE_AGGREGATE_20260925.md) | 導覽頁分組連到 26 份原始 QA，不是狀態裁定；supported caller/profile handoff 與其餘 source-evidence slices 分開判讀。R001、R006、R020 的大型 dated receipts 已移至 [Archive](../09_archive/README.md#2026-10-08-r001-r006-r020-historical-qa)。R029 的 gate 草稿與 caller preflight 已轉入 [Archive 歷史專區](../09_archive/README.md#2026-10-09-r029-retirement-preflight)；目前裁定以 implementation report／migration sequence 為準。aggregate 與逐項 R026 收據仍按各自的來源身分、版本與範圍判讀。 |
| ML Shadow 與前瞻證據 | [Gate 7 工程入口](GATE_7_ML_SHADOW_ENGINEERING.md) → [V4.1 校準切片](V4_1_RECOMMENDATION_CALIBRATION_VERTICAL_SLICE_2026_09_10.md) → [V4.1 歷史方法包](V4_1_HISTORICAL_METHOD_PACK_2026_09_12.md) → [V4.2 前瞻來源日學習](V4_2_PROSPECTIVE_SOURCE_DAILY_LEARNING_2026_09_14.md) → [V4 daily evidence loop（9/12 歷史）](../09_archive/V4_DAILY_EVIDENCE_LOOP_HANDOFF_2026_09_12_HISTORY.md) → [歷史 ML／readiness 收據索引](../09_archive/README.md#ml-dated-readiness-evidence-20261009) → [R026 ML boundary](ML_SHADOW_BOUNDARY_R026_EXACT_ALLOWLIST_QA_20260925.md) → [Prospective restart direction](PROSPECTIVE_FORMAL_RESTART_DIRECTION_2026_08_19.md) → [Prospective Formal execution SSOT](PROSPECTIVE_FORMAL_SIMULATED_PORTFOLIO_EXECUTION_PLAN_2026_08_14.md) → [Decision-clock contract](PROSPECTIVE_FORMAL_RESTART_CLOCK_TIME_CONTRACT_2026_08_25.md) | V4.1／V4.2 是有範圍與日期的研究證據；V4.2 收據記錄 `retain_current`、自然樣本 0，不表示資格或 promotion。Archive 的 9/6–9/20 快照也不代表目前狀態；現況看 Snapshot，操作看 Manual。 |
| V4 forward policy／ML storage 工程收據 | [前瞻 Paper machine policy candidate](V4_FORWARD_MACHINE_POLICY_CANDIDATE_2026_09_08.md) → [position thesis closure contract](V4_FORWARD_POSITION_THESIS_CLOSURE_CONTRACT_2026_09_08.md) → [immutable block reuse](V4_ML_IMMUTABLE_BLOCK_REUSE_2026_09_07.md) → [ML storage guard](V4_ML_STORAGE_GUARD_2026_09_07.md) | 這些是 2026-09-07／08 的 research-only 或 bounded engineering 收據；`approved_for_activation` 不代表已由 Paper／Formal／broker／ML promotion 消費，現況依 Snapshot 與 Gate 7。 |
| Restated research dataset v2 合併契約 | [v2 schema／identity contract](ML_RESTATED_DATASET_V2_MERGE_CONTRACT_2026_09_23.md) → [full v2 build acceptance](MODEL_REPAIR_EXECUTION_2026_09_23.md) → [current-restated rebuild status](ML_REVISION_AWARE_REBUILD_EXECUTION_PLAN_20261001.md) | v2 identity／merge contract 仍由 reader、merger 與 tests 使用；這是版本相容規格與歷史 build receipt，不是目前 ML qualification，現況看 Gate 7／Snapshot。 |
| V2–V4 maturity／approval 歷史收據 | [readiness 與 baseline 專區](../09_archive/README.md#2026-10-08-v2v3v4-dated-readiness-reports) → V2.4 [paper policy 核准](../09_archive/V2_4_PAPER_POLICY_APPROVAL_2026_07_12_HISTORY.md)／[scope 開工核准](../09_archive/V2_4_SCOPE_APPROVAL_2026_07_12_HISTORY.md) | 日期化核准只記錄當時 paper-only 範圍，不授權真實交易；目前操作邊界看 Manual，成熟度與狀態看 Snapshot。 |
| Data Governance 與來源 | [10/03 data closeout](FINAL_DATA_CLOSEOUT_AND_COMMIT_20261003.md) → [正式資料修復](FORMAL_DATA_REPAIR_2026_09_23.md) → [PIT taxonomy daily source](PIT_TAXONOMY_DAILY_SOURCE_QA_2026_09_15.md) → [產業來源驗收](PIT_INDUSTRY_CALLER_ACCEPTANCE_QA_2026_09_15.md) → [9/9 資料補齊總驗收（歷史原路徑保留）](DATA_COMPLETION_2026_09_09.md) → [flows／TDCC 封存快照](../09_archive/README.md#data-completion-20260909) → [Gate 2 7/22 歷史基線](GATE_2_DATA_GOVERNANCE_CONSOLIDATION_AUDIT_2026_07_22.md) → [9/14 industry journey smoke 歷史](../09_archive/README.md#2026-10-08-early-decision-and-industry-journey-receipts) | source coverage、publication、PIT eligibility 與正式訓練資格不可混為一談；Gate 2 報告是唯讀日期快照，明確不構成人工 credit 或 production enablement。9/9 收據僅證明當日 bounded 補資料且有 `available_date=NULL` 等限制，不代表歷史 PIT 或全市場完整；總驗收全文留在 QA 以維持既有交接路徑，Archive 副本為凍結快照。9/14 UI smoke 的 PIT eligible 為 0。後續來源 provenance、taxonomy 與 caller gate 仍以本列較新的 QA 為準。 |

## 近期與跨主題收據

| 要查的內容 | 證據入口 |
|---|---|
| 舊 ML program readiness 稽核與後續修正 | [8/27 稽核](../09_archive/PROGRAM_READINESS_AUDIT_2026_08_27.md) → [8/28 更新](../09_archive/PROGRAM_READINESS_AUDIT_2026_08_28.md)；只作歷史底冊，現況看 Snapshot |
| 2026-09-15／16 source、clock 與機率學習審計 | [Archive 專區](../09_archive/README.md#2026-10-08-source-clock-and-probability-learning-audits)；要找目前 PIT／ML 狀態，回到本頁相應主題與 Snapshot |
| BankTaiwan 研究型學習（2026-09-14，歷史快照） | [成本估算與 real-source smoke](../09_archive/DAILY_BANKTAIWAN_LEARNING_COST_2026_09_14_HISTORY.md) → [營運受控 run](../09_archive/DAILY_BANKTAIWAN_OPERATIONAL_2026_09_14_HISTORY.md) → [Coverage History Entry 120](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-120) | 單日結果為 `retain_current`、自然成熟樣本 0，不代表 lane maturity 或 promotion；現況看 Snapshot／Gate 7 與近期 QA |
| 基本面與估值來源 | [月營收來源審查](BALDR_F12_MONTHLY_REVENUE_SOURCE_REVIEW_20261009.md) → [基本面快照設定](FUNDAMENTAL_SNAPSHOT_CONFIG_20261007.md) → [來源採納與季度目錄](FUNDAMENTAL_SOURCE_ACCEPTANCE_AND_QUARTERLY_CATALOG_20261001.md) | 每份收據只覆蓋其來源與時點；candidate／capture 不等於正式採納、歷史 PIT 或正式評分。 |
| F17 全母體事實保存與 SQLite 私有副本讀取 | [完整母體官方處置事實保存](F17_FULL_N_FACT_BUNDLE_20261008.md) → [單次 SQLite 私有副本讀取](PINNED_SQLITE_READ_SESSION_20261008.md) | F17 收據限 current-only，尚無 UI 或完整 F17 驗收；SQLite helper 尚未接 provider、ML replay、正常設定或 UI，不代表原檔保護／效能已全面通過。 |
| Selection 現況市場歸屬來源 | [市場名錄 assignment 收據](SELECTION_MARKET_ASSIGNMENTS_20261007.md) | 依 CMS 保存的官方名錄原件與明示 pin 判定；缺件、空名錄、重複或衝突會拒絕已知市場。合成測試及部分真實封存不等於完整 facts 或產品驗收。 |
| V2.3 P0 source decisions | [目前逐來源 Register](V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md) → [7/12 導入方向與 FinMind 候選決議歷史](../09_archive/README.md#2026-10-08-v23-data-source-decision-receipts) | 歷史 approval 只授權研究／補證方向；FinMind 帳戶權限是當日觀察，不替代目前來源接受或 eligibility。 |
| P0 owner／reviewer handoff | [8/30 P0 evidence packet](P0_EVIDENCE_REFRESH_2026_08_30.md) → [8/30 Evidence weekly approval packet](EVIDENCE_WEEKLY_APPROVAL_REFRESH_2026_08_30.md) | 兩份是 External Validation Register 引用的原始 handoff；當日數字不代表目前 P0／Evidence 狀態，現況看 Snapshot／逐來源 Register。 |
| ML 儲存保留與清理 | [8/29 一次性 retention cleanup custody](../09_archive/ML_RELEASE_V4_STORAGE_RETENTION_CLEANUP_2026_08_29.md) → [現行 immutable retention policy](../01_architecture/system_architecture.md#111-immutable-ml-publication-retention) → [操作與授權步驟](../07_guides/APPLICATION_MANUAL_SUPPLEMENTS.md) | 歸檔收據記錄當次授權與不可逆結果，不代表目前容量、run 數或 retention 決議。 |
| 8/30 Readiness 詳細收據 | [Runtime／Paper／Formal lane refresh](../09_archive/README.md#2026-10-08-program-readiness-refresh-details) | 保留當日 probe 與 strict input 證據；目前狀態看 Snapshot。P0 與 Evidence weekly handoff 的原始收據仍在本目錄。 |

### 2026-10-06 至 10-09 基本面與資料快照

- **基本面與資料快照**：[選股基本面副本 session](SELECTION_FUNDAMENTAL_COPY_SESSION_20261007.md)、[月營收 YoY](SELECTION_MONTHLY_REVENUE_YOY_20261007.md)、[Snapshot typed parts reuse](SNAPSHOT_TYPED_PARTS_REUSE_20261007.md)。

### 2026-09 來源、PIT 與 read-model bounded 收據

- **候選來源與技術發布**：[修復來源後的 candidate model QA](REPAIRED_SOURCE_MODEL_CANDIDATE_QA_2026_09_23.md) → [TPEX 背景技術發布 QA](TPEX_BACKGROUND_TECHNICAL_PUBLICATION_2026_09_20.md)。前者建立 candidate 不代表取得模型啟用資格；後者的正例只在 QA snapshot，未寫入正式資料庫，也不提供自然驗證或排程 credit。
- **PIT termination evidence leaf**：[8183 termination research proof](PIT_8183_TERMINATION_EVIDENCE_RESEARCH_20261001.md)。它只證明指定 cutoff 的 `eligible=false` research-only 狀態，不是 taxonomy bundle、正式分類或 historical PIT／formal credit。
- **V4 read-model／Research Shadow**：[Effectiveness read-model QA](V4_EFFECTIVENESS_READ_MODEL_2026_09_08.md) → [ML Research Shadow integration QA](V4_ML_RESEARCH_SHADOW_INTEGRATION_2026_09_07.md)。這些是有界 read-model／唯讀整合收據，不代表 V4 投資成效已驗收或模型取得正式資格。

## 其他常用路徑

- **2026-07／08 日期化資料與 owner 收據**：查 [Archive 專區](../09_archive/README.md#2026-10-08-data-and-source-owner-receipts)；source pilot、license capture、owner packet 與 data reconciliation 保留原始限制，不代表目前來源採納或 production approval。
- **2026-08 前瞻正式時鐘歷史**：查 [Archive 專區](../09_archive/README.md#2026-10-08-prospective-formal-clock-history)；目前重啟方向與決策時鐘契約仍留在此目錄，歷史 activation、staging 與失敗收據不授權重啟或發布。

## 補充收據索引（2026-10-10 治理補登 54 份；2026-10-11 追加 1 份）

> 原列 54 份為 2026-10-10 全量盤點查核的專屬 QA 證據；其後追加的 2026-10-11 C3/C4 manifest reconciliation 是聚焦核對，不改寫原收據。各原件維持各自日期與範圍，不推升為目前全域狀態。

- [Bounded 全特徵重述研究模型：實際 fit、OOF 與當日 heads readback](BOUNDED_RESTATED_RESEARCH_FIT_QA_2026_09_23.md)
- [C2 非 ML Consumer Union 預檢（2026-09-25）](C2_NON_ML_CONSUMER_UNION_PREFLIGHT_20260925.md)
- [C3/C4 manifest identity 與 route delta reconciliation（2026-10-11）](C3_C4_MANIFEST_DIFF_RECONCILIATION_20261011.md)
- [derived-h5 修訂研究雙時鐘契約（2026-09-22）](DERIVED_H5_RESTATED_RESEARCH_DUAL_CLOCK_CONTRACT_2026_09_22.md)
- [Derived-h5 run02 研究訓練輸入缺件盤點（2026-09-23）](DERIVED_H5_RUN02_RESEARCH_INPUT_AUDIT_2026_09_23.md)
- [F07 保存來源價格查詢契約（來源版有限接受；執行檔與效能待驗）](F07_PRICE_QUERY_CONTRACT_20261008.md)
- [F2／F3 原市場頁共享來源與已開能力矩陣驗證](F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)
- [官方大盤來源修復後的全市場 H5 模型驗收](FULL_OFFICIAL_MARKET_V3_REPAIR_QA_2026_09_23.md)
- [修訂模型的當日研究輸入](MODEL_REPAIR_CURRENT_INPUTS_2026_09_23.md)
- [模型完整重訓後的大盤來源差異（2026-09-23）](MODEL_REPAIR_MARKET_SOURCE_AUDIT_2026_09_23.md)
- [模型修復：原配置目標的實體資料查核](MODEL_REPAIR_TARGET_AUDIT_2026_09_23.md)
- [Natural learning caller 接線 QA（2026-09-18）](NATURAL_LEARNING_CALLER_WIRING_2026_09_18.md)
- [Natural learning trace（2026-09-18）](NATURAL_LEARNING_TRACE_2026_09_18.md)
- [Natural maturity session resolver QA（2026-09-18）](NATURAL_MATURITY_SESSION_RESOLVER_2026_09_18.md)
- [Natural session label binding QA — 2026-09-18](NATURAL_SESSION_LABEL_BINDING_2026_09_18.md)
- [Natural Shadow Weekly Evidence Audit（2026-09-20）](NATURAL_SHADOW_WEEKLY_EVIDENCE_AUDIT_2026_09_20.md)
- [2026-05-20 價格修訂的模型影響與最小隔離](PRICE_REPAIR_MODEL_IMPACT_2026_09_22.md)
- [R023 基本面／月營收資料契約遷移報告](R023_FUNDAMENTAL_MONTHLY_REVENUE_CONTRACT_MIGRATION_20260923.md)
- [R026 capability candidate JSON captured-bytes 品質驗證](R026_CAPABILITY_CANDIDATE_JSON_CAPTURED_BYTES_20260925.md)
- [R026 capability model-manifest 同 bytes 捕獲實作驗證](R026_CAPABILITY_MODEL_MANIFEST_CAPTURED_BYTES_20260925.md)
- [R026 capability model-manifest 同 bytes 捕獲獨立覆核（2026-09-25）](R026_CAPABILITY_MODEL_MANIFEST_CAPTURED_BYTES_INDEPENDENT_REVIEW_20260925.md)
- [R026 capability pointer captured-bytes 品質驗證](R026_CAPABILITY_POINTER_CAPTURED_BYTES_20260925.md)
- [R026 每日價格修訂 receipt 連結特性查核](R026_DAILY_PRICE_RECEIPT_LINK_CHARACTERIZATION_20260924.md)
- [R026 direct daily-price typed receipt evidence QA](R026_DIRECT_DAILY_PRICE_TYPED_RECEIPT_20260925.md)
- [R026 Excluded Daily-Price Namespace：Slice 5 紅測基線](R026_EXCLUDED_DAILY_PRICE_NAMESPACE_SLICE5_20260925.md)
- [R026 Excluded Daily-Price：Slice 5B atomic-replace QA](R026_EXCLUDED_DAILY_PRICE_SLICE5B_ATOMIC_REPLACE_RED_20260925.md)
- [R026 歷史原始快照保管事實——有界切片](R026_HISTORICAL_RAW_SNAPSHOT_CUSTODY_20260925.md)
- [R026 historical replay cross-call mixed-version characterization](R026_HISTORICAL_REPLAY_CROSS_CALL_MIXED_VERSION_20260925.md)
- [R026 historical replay per-call cutoff characterization](R026_HISTORICAL_REPLAY_PER_CALL_CUTOFF_20260925.md)
- [R026 invocation model-resolution capability — bounded experimental evidence](R026_INVOCATION_MODEL_CAPABILITY_20260925.md)
- [R026 Live Calibration 單次載入前後來源證據](R026_LIVE_CALIBRATION_SOURCE_IDENTITY_20260925.md)
- [R026 Live Calibration SQLite Read-Lease Wiring](R026_LIVE_CALIBRATION_SQLITE_LEASE_WIRING_20260925.md)
- [R026 投影後 sidecar shadow recheck](R026_LIVE_SOURCE_IDENTITY_POST_PROJECTION_20260925.md)
- [R026 live source identity shadow capture（bounded `ACCEPTED_SCOPE`）](R026_LIVE_SOURCE_IDENTITY_SHADOW_20260925.md)
- [R026 單一模型 artifact same-bytes loader](R026_MODEL_ARTIFACT_SAME_BYTES_20260925.md)
- [R026 同次模型解析事實 QA](R026_MODEL_RESOLUTION_FACTS_20260925.md)
- [R026 ordered candidate / feature preparation facts QA](R026_ORDERED_PREPARATION_FACTS_20260925.md)
- [R026 Post-calibration typed handoff](R026_POSTCALIBRATION_TYPED_HANDOFF_API_20260925.md)
- [R026 PreparedMLRuntimeInput 純型別 API 草案（2026-09-25）](R026_PREPARED_RUNTIME_INPUT_TYPES_API_DESIGN_20260925.md)
- [R026 SQLite 單次讀取 Lease 試作 QA](R026_SQLITE_READ_LEASE_20260925.md)
- [R026 TAIEX 大盤列證據 bounded slice（2026-09-25）](R026_TAIEX_MARKET_INDEX_ROW_EVIDENCE_20260925.md)
- [R026 TAIEX 大盤列證據獨立複審（2026-09-25）](R026_TAIEX_MARKET_INDEX_ROW_EVIDENCE_INDEPENDENT_REVIEW_20260925.md)
- [R026 TWSE 前瞻日價列證據（2026-09-25）](R026_TWSE_DAILY_PRICE_SQLITE_ROW_EVIDENCE_20260925.md)
- [R027 logical-time acceptance revision（2026-09-27）](R027_LOGICAL_TIME_ACCEPTANCE_REVISION_20260927.md)
- [R027 technical publication／ML identity 隔離實驗報告](R027_TECHNICAL_PUBLICATION_ML_IDENTITY_ISOLATION_20260923.md)
- [錯價修復後 Allocation 重訓 Runner QA（2026-09-23）](RESTATED_ALLOCATION_REPAIR_TRAINING_2026_09_23.md)
- [Revision-aware prospective rebuild gap QA（2026-09-22）](REVISION_AWARE_PROSPECTIVE_REBUILD_GAP_2026_09_22.md)
- [2026-09-22 價格修訂候選資料與重訓 Gate](REVISION_RETRAIN_ISOLATED_RESEARCH_2026_09_22.md)
- [排程基本面 bootstrap 與研究候選驗收（2026-09-30）](SCHEDULER_FUNDAMENTAL_BOOTSTRAP_20260930.md)
- [ML 日常研究來源列投影排程接線 QA（2026-10-01）](SCHEDULER_ML_DAILY_SOURCE_ROW_HOOK_20261001.md)
- [ML 每日原始來源列隔離投影 QA（2026-10-01）](SCHEDULER_ML_DAILY_SOURCE_ROW_PROJECTION_20261001.md)
- [ML raw PIT 來源修訂與前瞻候選 QA（2026-09-30）](SCHEDULER_ML_RAW_REPAIR_20260930.md)
- [2026-09-21 個股研究資料鏈 Incident QA](STOCK_RESEARCH_DATA_INCIDENT_2026_09_21.md)
- [TPEX 單日 pre-captured raw 補入 QA（2026-09-18）](TPEX_SINGLE_DAY_PRECAPTURED_BACKFILL_2026_09_18.md)
- [TPEX source gap diagnostics — 2026-09-18](TPEX_SOURCE_GAP_DIAGNOSTICS_2026_09_18.md)
