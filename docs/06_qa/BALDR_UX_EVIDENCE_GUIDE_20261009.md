# BALDR／H20／UX QA 收據導覽

> 本頁只提供閱讀入口，不是新的 QA 收據、Gate 裁定或產品狀態摘要。下列 36 份原件仍保留在 `docs/06_qa/`；本次沒有搬移或改寫收據。

## 閱讀方式

- 先按問題選擇下方的收據家族，再依原件的日期、固定基線、輸入與限制判讀。
- 候選版、release preparation、合成 UI、read-only adapter 與 bounded lane 各自只證明原件標示的範圍；不推定目前 EXE／Main／真人接受、正式來源、ML qualification 或自然成熟。
- 目前狀態回到 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 與較新的具名 QA；操作回到 [APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)。本頁不把舊收據的狀態合併成新的待辦或完成宣告。

## 收據家族

### 個人模型、H20 與自然結果（6 份）

- [A03 個人模型每日保存與自然結果](BALDR_A03_PERSONAL_MODEL_DAILY_20261006.md)
- [B14 獨立 shadow control port](BALDR_B14_SHADOW_CONTROL_20261006.md)
- [個人 H20 模型中央接線與真候選核對](BALDR_PERSONAL_MODEL_ACTIVATION_INTEGRATION_20261006.md)
- [個人真模型啟用前讀回入口](BALDR_PERSONAL_MODEL_ACTIVATION_PREFLIGHT_20261006.md)
- [Current-observed H20 每日入口](BALDR_CURRENT_OBSERVED_H20_DAILY_20261006.md)
- [H20 完整 cohort 自然結果 caller](BALDR_H20_NATURAL_BATCH_20261007.md)

### 候選版、產品交付與發布準備（8 份）

- [c611 固定候選建置及同版驗證](BALDR_C611_CANDIDATE_20261007.md)
- [固定 acd18a1e 候選與接受範圍](BALDR_CANDIDATE_ACD18A1E_20261008.md)
- [dev／main 兩用途整理與可恢復發布準備](BALDR_DEV_MAIN_RELEASE_PREPARATION_20261007.md)
- [已授工程與未決事項差異](BALDR_ENGINEERING_DECISION_DELTA_20261006.md)
- [已授範圍最終穩定窗收據](BALDR_FINAL_AUTHORIZED_UNION_20261006.md)
- [本機 main 使用版 packaging 驗收](BALDR_LOCAL_MAIN_PACKAGING_20261007.md)
- [下一次唯讀驗收與原 24UX 工程差異](BALDR_NEXT_RUN_AND_REMAINING_ENGINEERING_20261007.md)
- [BALDR 產品可用性與 BUI-001 修復](BALDR_PRODUCT_USABILITY_20260925.md)

### 個人資料、Registry 與復原（5 份）

- [B10 Notes Backup／Restore Adapter QA](BALDR_B10_NOTES_BACKUP_20261006.md)
- [R01 Registry read budget](BALDR_R01_REGISTRY_READ_BUDGET_20261006.md)
- [Read Session Central Review](BALDR_READ_SESSION_CENTRAL_REVIEW_20261008.md)
- [兩分支復原](BALDR_TWO_BRANCH_RECOVERY_20261007.md)
- [UX19 儲存治理與發布復原](UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)

### 技術訊號、圖表與 UI 路由（7 份）

- [BB 上軌條件 UI](BALDR_BBANDS_RESEARCH_UI_20261007.md)
- [四均線正常來源入口](BALDR_MA_NORMAL_OPENER_REVIEW_20261008.md)
- [BBANDS30 上軌完整具名母體驗證](BALDR_PARENT_BBANDS30_UPPER_20261007.md)
- [H20 同次來源圖表接線中央審查](H20_BOUND_CHART_INTEGRATION_20261008.md)
- [H20 返回來源與單次刷新](H20_RETURN_SINGLE_REFRESH_20261007.md)
- [UX07 圖表可行性調查](UX07_CHART_FEASIBILITY_20261005.md)
- [UX08 原生圖同源契約限定驗證](UX08_NATIVE_CHART_CONTRACT_20261005.md)

### 研究工作台共用語義與保存結果（4 份）

- [UX02 共用狀態詞彙](UX02_SHARED_STATUS_VOCABULARY_20261005.md)
- [UX09 研究名單入選生命週期](UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)
- [UX10 多方法共同符合](UX10_MULTI_METHOD_LANE_20261006.md)
- [UX11 保存結果與規則來源核對](UX11_SAVED_RESULT_RULE_READBACK_20261006.md)

### UX20／UX21／UX23 樣本、benchmark 與 Registry（6 份）

- [UX20 具名母體多批 capture 整合](UX20_PARENT_CAPTURE_INTEGRATION_20261006.md)
- [UX20 保存母體收據 UI 整合](UX20_PARENT_RECEIPT_UI_20261006.md)
- [UX20 固定 MA 研究樣本 capture lane](UX20_RULE_SAMPLE_CAPTURE_LANE_20261006.md)
- [UX20 MA 完整控制組 capture 整合](UX20_SAMPLE_CAPTURE_INTEGRATION_20261006.md)
- [UX21 具名 benchmark 唯讀 adapter](UX21_BENCHMARK_ADAPTER_20261006.md)
- [UX23 Registry 唯讀 reader](UX23_REGISTRY_READONLY_20261006.md)
