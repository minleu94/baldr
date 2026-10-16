# P0／MOPS／Owner Packet Refresh — 2026-08-28

> **歷史時點警語（2026-10-11；範圍裁決補記 2026-10-12）**：本文件「最新」僅指 2026-08-28 當次封包；其 P0 row counts、`action_required`、外部待辦與 `2026-09-01` planned clock 均為歷史快照，不是目前派工、啟用或寫入授權。後續 machine evidence 見 [2026-08-30 P0 refresh](../06_qa/P0_EVIDENCE_REFRESH_2026_08_30.md)，來源決議依 [P0 acceptance register](../06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md) 判讀。當次 `accepted=0`／`limited=0` 只屬於 13 個 canonical P0 contract IDs 的 audit snapshot；它與 DEV-66 EZSearch availability-lane 決議事件使用不同 source ID，不表示決議互相撤銷。最新 applying revision 未經核實，詳細裁決見下節。原文外部輸入項目只保留當時上下文，不能直接重送或執行。

## 2026-10-12 範圍裁決與證據界線

本封包所記 `accepted=0`／`limited=0` 是 2026-08-28 P0 audit 的 13 列 canonical contract denominator。同期 `P0_SOURCE_IDS` 含 `pit.quarterly_financials`、不含 `mops.ezsearch.statement_publication`；DEV-66 的 `limited` 決議事件則只核准後者作內部 statement-availability research。source identity contract 將 EZSearch 明定為 availability lane，並將 numeric／governance source 分開為 `pit.quarterly_financials`。所以這組 0/0 計數不包含、也不撤銷 DEV-66；當次 MOPS 季報候選的 machine verification 亦不構成 source acceptance。詳細程式證據與 Register 修正見 [P0 acceptance register §14](../06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md#14-2026-08-28-p0-多路徑-live-evidence-refreshappend-only)。

此裁決只解決來源身分與 denominator 的差異。封包記載的原始 audit JSON 路徑 `C:\Users\archi\AppData\Local\Temp\technical_analysis_p0_source_evidence_live_with_mops_new.json` 在目前 host 不存在；原始 audit rows／registry input 未取得，DEV-66 working-copy registry 的完整 revision 序列也未核實。因此本封包不能證明 DEV-66 是否仍是最新 applying revision，亦不能由 0/0 推導全域或目前 registry 狀態。保留本文件其餘原始內容作為 2026-08-28 歷史快照。

## 目的

本紀錄保存 2026-08-28 依序推進時的最新唯讀證據。它只更新候選 evidence 與
owner review handoff，不代表任何 source acceptance、Formal credit、Paper 成交帳、
production ACL、scheduler 或 broker 權限已開啟。

## P0 fresh audit

- Audit：`C:\Users\archi\AppData\Local\Temp\technical_analysis_p0_source_evidence_live_with_mops_new.json`
- SHA-256：`06DA480CFCC6D7BCF8B1ED1AB4B41E74D140E7D5F9B989E540DE4FAEACF16C3B`
- Schema：`p0-source-evidence-audit.v1`
- Mode：`bounded_official_read_only`
- Matrix：13/13 source rows；`machine_verified=1`、`degraded=12`、`missing=0`
- Boundary：`accepted=0`、`limited=0`、`downstream_eligibility=none`、
  `formal_oos_allowed=false`、`production_allowed=false`

這次的 `missing=0` 只表示每個 P0 contract 都有 machine row；12 個 degraded row
仍缺官方 publication／decision-time provenance 或需要 owner review，不能解讀成
來源已可供下游使用。

## MOPS 季報候選

實際載入並通過 `validate_mops_quarterly_artifact.py` 的 artifact 為：

`C:\Temp\technical_analysis_development_output\dev71-mops-numeric-pit-2330-2025q1-20260729-r1\numeric-pit-candidate.json`

該 candidate 綁定 MOPS `t163sb06` numeric response 與 `t57sb01` publication listing，
保留 raw source hash、availability event hash、canonical dataset lineage 與修訂欄位。
Fresh audit 對 `pit.quarterly_financials` 的 machine row 為：

- `machine_status=verified`
- `pit_status=pit_date_verified`
- `availability=artifact_verified`
- `raw/accepted/quarantine/blocked=1/1/0/0`
- `remaining_blocker=legal_and_license_acceptance_required`

因此 MOPS candidate 已經接通到 P0 matrix 與 intake；它仍是 research candidate，沒有
寫入正式 SQLite、SourceAcceptanceDecisionRegistry 或 Formal input。

## Owner packet／intake

- Owner packet：`C:\Users\archi\AppData\Local\Temp\technical_analysis_p0_owner_packet_live_with_mops_new.md`
- Packet SHA-256：`C5664E1EA1349DEAEAFF37EBD8876C2401C968380BA754258AA81557F58CC626`
- Intake：`C:\Users\archi\AppData\Local\Temp\technical_analysis_p0_intake_live_with_mops_new.json`
- Intake readiness：`C:\Users\archi\AppData\Local\Temp\technical_analysis_p0_intake_readiness_live_with_mops_new.json`
- Intake 結果：`supplied=13`、`valid=13`、`owner_review_ready=0`、`deferred=13`

五個 owner group 已依實際 route、fallback、timestamp class、row conservation 與
license URL 整理；尚待具名 source owner／license reviewer、license/use-case 決定、
publication／available-date／PIT／revision policy 與 rollback reference。工具不代填
這些權限性欄位。

## 9/1 prospective clock

- 官方日曆 bundle：`C:\Users\archi\AppData\Local\Temp\technical_analysis_calendar_bundle_network_20260828_110409.json`
- Clock plan：`C:\Users\archi\AppData\Local\Temp\technical_analysis_clock_plan_20260828_110441.json`
- Candidate：`clock:prospective:20260901:planned-v1`
- `2026-09-01` 已由 TWSE 與 TPEx 各自的官方日曆證據確認為交易日。
- Plan 仍是 `candidate_ready`／read-only；未建立 clock、未發布三份 formal manifests，
  也未產生 Formal credit。`owner_decision_timestamp` 只是規劃輸入，不能當成 owner
  已簽核的 activation decision。

## 依序剩餘外部輸入

1. Owner 逐組回覆 P0 packet；在回覆前維持 `deferred`／`none`。
2. Owner 以具名 decision、timestamp、clock hash 發布 9/1 create-only clock；不得把
   plan 當作 activation。
3. Paper 需真實 execution fills（含 partial／reject／override、Decimal cost、
   turnover 與 execution gap）；目前只有 snapshot／Equal Weight benchmark，週報仍
   `not_computable`。
4. Runtime 需正式 output／Registry ACL、Task Scheduler registration 與 owner-approved
   technical backup／rollback canary；目前 staging transaction 通過，但正式 write handle
   仍 `PermissionError`、scheduler 為 `0/13`，technical canary 只有 preview。

## 最新統一 readiness

使用 fresh P0 audit、license capture、weekly projection、runtime probe、performance
與 scheduler read-only artifacts 重算：

`C:\Users\archi\AppData\Local\Temp\technical_analysis_program_readiness\program_readiness_after_mops_refresh_v2_20260828.json`

結果仍為 `status=action_required`。這是剩餘外部 gate 的準確投影，不是 MOPS artifact
遺失或 Data Update UI 沒有讀到資料。
