# C1 Contract Repair Implementation Report

- **狀態：** `U1_ACCEPTED_FOR_U2`
- **範圍：** 只完成 C1 上游 contract slice；此狀態不代表 C1 PASS，也不釋出 Wave 6。
- **基線：** branch `dev`，HEAD `dcc27a42a37c2f69ad83fecee6c245177a457e01`。
- **工作樹：** U1 初始實作依派工基線保留既有 dirty/untracked paths；本次 follow-up 期間另有 U2–U5 並行工作檔案存在，均予保留，未覆寫、stage 或 commit。index 維持空白。

## Scoped mypy QA blocker 修復附錄

後續 C1 scoped mypy QA 發現 `_validate_scheduled_result_config` 取出的 `decision_date` 型別仍是 `object`，因此傳入 `_require_nonblank` 與 `date.fromisoformat` 各有一項型別錯誤。本次在兩者呼叫前加入明確 `str` 型別檢查；原有非空及 `YYYY-MM-DD` 驗證不變，錯誤型別現在明確以 `TypeError` 拒絕。新增完整 scheduled config 負例，確認 JSON integer `decision_date` 被拒絕；既有 ISO 日期正例仍覆蓋有效路徑。

修補後驗證：

| 命令 | 結果 |
|---|---|
| `.\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module/recommendation/contracts.py` | **通過**，1 source file，無問題 |
| `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_contracts.py tests/test_recommendation_execution_codec.py -q -o addopts=` | **88 passed** |
| `.\.venv\Scripts\python.exe -m py_compile app_module/recommendation/contracts.py tests/test_recommendation_contracts.py` | **通過** |

SOL 依獨立複審結論 **`Accept U1 type repair only`** 簽收此 follow-up；目前沒有剩餘 U1 型別 blocker。接受範圍僅包含本次型別修補，**C1 仍為 `REOPENED / NOT PASSED`，Wave 6 仍為 `BLOCKED`**，不得據此宣稱 C1 PASS 或恢復 release。

## 最終獨立複審結論

Luna Max 最終複審：**`Accept U1 only`**。複審確認 67 個 focused contract tests 通過，且 scheduled 路徑 P1 fail-closed 與 JSON numeric underflow P2 定點修補符合要求。此結論只接受 U1 contract slice；**C1 與 Wave 6 仍為 `BLOCKED`**，不可據此恢復 release。

後續仍須依序完成並各自複審：

- **U2 — Codec：** revision 2 寫入、revision 1／legacy 唯讀；驗證 revision 1 原始 bytes/hash/read revision、新增欄位缺省為 None/unknown，以及未知 revision 拒絕。
- **U3 — Invocation capture：** 在 worker 返回前同次封存 result config/hash、cohort、identity、evidence 與 clocks；以隔離 fixture 驗 A/B interleave 和來源一致，不讀 `last_*` 或 post-save live 重建。真 scheduled wrapper parity 留待 C1 PASS 後 R014。
- **U4 — Persistence/query：** create-only 寫入與單一 legacy/revision 1/revision 2 read seam；驗 payload/index hash、legacy raw bytes/read-time hash、receipt identity 與無舊 bytes/header 重寫。
- **U5 — Consumer readiness：** 以 saved read view 驅動 forward consumer；驗完整來源成功、save 未成功不 forward、來源或 receipt identity 缺失／不符拒絕。

U2–U5 gate、完整 C1 readiness 測試、獨立 review 與 SOL 最終驗收全部通過前，C1/Wave 6 維持 blocked。

## 獨立 review 修補

首輪獨立 review 結果為 `CHANGES_REQUIRED`。本次在 U1 專屬 contract/test/report 檔案完成最小修補：

1. `Context` 新增 optional、具名、深凍結的 `result_config_snapshot`，保存完整 post-run JSON 原文及 `config_sha256`。Snapshot 驗證 JSON root、重複鍵、非有限／超出既有 JSON numeric 範圍、UTF-8 可逆性、SHA-256 格式與 canonical hash。
2. `config_sha256` 使用與 `forward_position_thesis_candidate_producer._sha256_json(dict(config))` 相同的 JSON canonicalization（UTF-8、`ensure_ascii=False`、key 排序、緊湊 separators）。測試以 producer 私有函式對合成完整 scheduled config 作 hash parity oracle，沒有執行 scheduled main；真實 wrapper parity 留待 R014。
3. Context 的 cohort、strategy／universe identities/spec、evidence identity，會與 result config 中的重疊欄位交叉核對。`scheduled_snapshot: true` 時要求具名 Context cohort；非空 typed 欄位缺少對應 config key 亦拒絕。非 scheduled config 僅核對實際存在的重疊鍵。`RecommendationExecution` 要求 scheduled Request 明示 `max_stocks`／`top_n` 並核對完整 config limits。
4. Context 若 `available_at` 與 `decision_at` 都存在，拒絕前者晚於後者；revision 1 可缺少任一欄。`Context.as_of_date` 與 `result_config.decision_date` 分別保存，沒有強制相等。
5. 增加 universe policy hash、snapshot hash、selected-codes hash mismatch 負例。
6. 第二輪複審 P1 已修：`scheduled_snapshot: true` 現要求非空 pre-run `Request.config_snapshot`、`Context` 的 strategy／universe／evidence／cohort typed owners、兩個 Request limits，以及 scheduled wrapper 必寫 envelope、完整 identity/spec 與 evidence key groups。必備 result config key 包括 wrapper 欄位 `research_only`、`decision_date`、`max_stocks`、`top_n`、`profile_id`、`profile_name`、`look_ahead_check`、`snapshot_cohort`、`safety_boundary`；strategy 欄位 `strategy_version_id`、`strategy_config_id/hash/schema/spec`；universe 欄位 `universe_id/hash/identity_schema`、`universe_policy_id/hash/schema/spec`、`universe_snapshot_id/hash/schema/source_provider_id/selected_codes_hash/spec`；及 `cost_model_id`、`benchmark_id`、`horizon_days`、`evidence_tier`、`return_basis`。依現行 scheduled default/config projection，`industry_benchmark_id` 是唯一可省略的 identity/evidence key；若 config 含此鍵，Context 必須有非空 typed 值且完全相符。任何 typed `None`／空白但 result config 有該鍵都拒絕。非 scheduled 與舊 revision 缺新欄維持 optional。
7. 第二輪複審 P2 已修：JSON numeric lexeme 若為非零 Decimal 但預設 producer float parse 會 underflow 成 `0.0`，snapshot 拒絕；一般可表示的 `0.1` 仍通過 producer hash parity。

上述修補可供獨立 review；它不代表 U3 接線或 R014 wrapper parity 已證實。

## 實作內容

### Decision item

`RecommendationItem` 增加 optional typed `close_price`、`price_change`、`indicator_score`、`pattern_score`、`volume_score`、`industry` 與完整 `reason_text`。數值延續 `Decimal | int | None`，拒絕裸 float；保留 Decimal 精度及 `None`／零差異。`rule_score` 仍代表 total score，沒有新增第二個 `total_score` 欄位。capture boundary 尚未納入此切片，DTO float 轉換仍須由後續 owner 使用 `Decimal(str(value))`。

### Request、Context 與可重建材料

- `Request` 有具名 `config_snapshot`、`max_stocks`、`top_n`。`RecommendationConfigSnapshot` 保存原 caller JSON 原字串與版本；建構時檢查 root object、重複鍵、非有限／超出既有 JSON numeric 範圍、不可逆 UTF-8 字串及 SHA-256。
- `raw_json_sha256` 是**原始 JSON UTF-8 bytes** 的 SHA-256。它不同於 strategy identity 的 `strategy_config_hash`，也不同於 forward producer 以完整 post-run `result_config` 呼叫 `_sha256_json` 得到的 `config_sha256`；本切片沒有計算或假定這些 hash 相同。
- `Context.result_config_snapshot` 保存 post-run 完整 result config 原字串及獨立 `config_sha256`。測試用合成完整 scheduled config 呼叫現行 producer `_sha256_json` 比對；U1 沒有呼叫 scheduled main，也沒有宣稱真實 wrapper parity。完整 config 中的 scheduled envelope、identity、cohort 與 typed Context 欄位在 `scheduled_snapshot: true` 路徑強制交叉驗證。`decision_date` 是排程執行日，可不同於 `as_of_date` 的資料 cutoff。
- `Context` 增加具名 `strategy_identity`、`universe_identity`、`snapshot_cohort`、`evidence_identity`，以及 `created_at`、`available_at`、`decision_at` aware clocks。Strategy／universe v1 identity spec 保存為各自具名欄位的原始 JSON text，驗證必需欄位、schema、ID/hash 關係與現行 canonical SHA-256；沒有加入泛用擴充字典。
- `SnapshotCohort` 保存 scheduled v1 完整 body：五組 symbol、counts、coverage status、`coverage_by_symbol` 的 status/quality/stage/reason codes/warnings、四個 definition 與 `cohort_hash`。它深凍結並驗證 v1 集合公式及 canonical body hash。`RecommendationRunEvidenceIdentity` 保存 scheduled result config 投影使用的成本、benchmark、horizon、tier 與 return-basis 欄位。
- Calibration projection rows 沒有放入 Decision contract；原有 immutable ML receipt binding 保持原狀，供後續 query 對 receipt 驗讀。
- R017 的 `stored_annotation` 目前只有任意 mapping fixture，尚無正式 schema。此切片沒有建立 placeholder parent ID 或任意 annotation mapping；需待正式 typed owner/schema 明確後處理。

### Schema revision

`EXECUTION_SCHEMA_REVISION = 2`、`SUPPORTED_EXECUTION_SCHEMA_REVISIONS = (1, 2)`。新 `SaveReceipt` 預設 revision 2；明確傳入的歷史 revision 1 原值會保留，其他 revision 拒絕。此處沒有修改 codec/read path；revision 1 raw bytes/hash 的歷史讀取保留仍是 R009 後續工作。

## Parity 與驗證

Parity tests 使用現行產生器作 oracle，而非只用人工自洽 fixture：

- `build_strategy_config_identity` 與 `build_recommendation_universe_identity` 的輸出直接餵入 typed identity contracts；測試驗證實際 builder spec、schema、ID/hash 及 canonical hash 接受性，也驗證完整 spec 被更改而 hash 未改時拒絕。
- `scripts.scheduled.run_scheduled_recommendation_snapshot._build_snapshot_cohort` 的輸出直接轉成 typed cohort，逐欄核對 symbols、counts、coverage、status 與 hash。
- 合成 scheduled result config 含完整 wrapper envelope、同一組 builder identities/spec、cohort 與 evidence；其 `config_sha256` 以現行 `forward_position_thesis_candidate_producer._sha256_json` 作 parity oracle。該 snapshot 只保存 producer 原文與 hash，不提供新的業務欄位字典。
- 另有正反例涵蓋深凍結、錯誤 JSON、duplicate key、NaN/Infinity、數字範圍、非法 identity、None/0、Decimal 精度、錯誤數值型別、naive clocks、排序／數量錯誤與不支援 revision。

已執行：

| 命令 | 結果 |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_contracts.py -q -o addopts=` | **67 passed** |
| `.\.venv\Scripts\python.exe -m py_compile decision_module/recommendation/contracts.py app_module/recommendation/contracts.py tests/test_recommendation_contracts.py` | **通過** |
| `.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_execution_codec.py -q -o addopts=` | **15 passed, 3 failed**；詳見下節 |

## 下游阻擋與待證項目

1. 本輪 codec focused test 有三個既有 R009 測試與新 revision gate 不相容：
   - `test_r009_current_contract_revision_is_explicitly_supported` 仍預期 current revision 為 1、supported revisions 為 `(1,)`。
   - `test_r009_new_revision_reader_accepts_older_additive_revision` 用已改為輸出 revision 2 的 writer 產生其所稱的舊文件，故 `schema_revision == 1` assertion 失敗；它尚未證明原 revision 1 bytes/hash readback。
   - `test_r009_reader_rejects_unknown_schema_or_revision[schema_revision-2-schema_revision]` 仍把 revision 2 當 unsupported，reader 現已從 contract 支援列表接受它。
2. `app_module/recommendation/codec.py` 的 `_RECORD_IDS`／`_ENUM_IDS` 尚未登記本切片新增的 snapshot、identity、cohort records 與 cohort enum；當 Request/Context 真正攜帶這些值時，codec wire allowlist 仍須由 R009 owner 更新。這不在本切片允許修改範圍。
3. **U3／R014／U5 尚待證：** identity builder 到 contract 的 parity 已驗證，且本次合成完整 config 與 producer hash 函式 parity 已驗證；仍未證明 scheduled wrapper 同次 invocation 捕獲的欄位可精確重現實際 `result_config`、`config_sha256`。本次沒有執行 scheduled main。scheduled wrapper 目前先把 config 中的 numeric strings 轉成 runtime floats 傳給 service，result config 則從轉換前的 `recommendation_config` 開始組成；後續 capture 必須明確保存正確的未轉換原始 caller config，不可 save 後 live 重建。R014/U3/U5 必須以隔離 fixture 比對實際完整結果 config hash，不能拿 `raw_json_sha256` 或 `strategy_config_hash` 代替。
4. Execute capture、codec/read、persistence/query、consumer 與 ML builder 的整合測試未在此切片執行或修復；需等各自 owner 接線後再驗證。特別是 revision 1 bytes/hash 不得因新 writer revision 2 被重寫或偽裝成 current。

## 變更檔案

- `decision_module/recommendation/contracts.py`
- `app_module/recommendation/contracts.py`
- `tests/test_recommendation_contracts.py`
- `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/C1_CONTRACT_REPAIR_IMPLEMENTATION_REPORT.md`

本報告只記錄 contract slice、目前證據與明確待辦；不宣稱 C1 PASS、Wave 6 release 或正式資料驗證。
