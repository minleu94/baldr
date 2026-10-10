> **C1 歷史切片狀態**：本文只保存個別修補／審查時點的範圍與 evidence，不代表目前整體 Gate 狀態，也不構成新的工作授權。整體 C1 裁決見 [C1 checkpoint](C1_CHECKPOINT.md) 與 [Wave 6 最終 gate 報告](WAVE6_FINAL_GATE_REPORT.md)；目前狀態看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)，目標設計權威看 [FINAL_TARGET_ARCHITECTURE](../FINAL_TARGET_ARCHITECTURE.md)。

# C1 U5a Forward Consumer Readiness Implementation Report

**狀態：`U5A_ACCEPTED_PENDING_FULL_C1_GATE`**

本報告記錄 C1 U5a typed verified-read forward consumer readiness 實作。獨立 Luna Max 審查已 `Accept U5a only`，確認 45 項測試、scoped mypy 與 py_compile 通過，且沒有剩餘 P0/P1/P2。此簽收只涵蓋 U5a；R014 真 scheduled wrapper parity 尚未驗證，C1 仍為 `REOPENED`、Wave 6 為 `BLOCKED`，不代表完整 C1、Wave 6 或正式資料流程通過。

## 實作範圍

- 在 `app_module/forward_position_thesis_candidate_producer.py` 新增 `produce_verified_read(read_model, save_receipt, *, source_artifact_path, policy_path=None)`。它只接受 `INDEXED`、rev2、完成狀態的 typed execution readback，並沿用既有 `_produce_source` packet builder。既有 `produce(path)` ABI、packet business rules 與排序未改。
- 以 U4 readback 為輸入，檢查 receipt、execution、read model 的 result ID、canonical payload hash、artifact location、raw artifact SHA、固定 artifact 路徑、一般檔案與 canonical bytes。使用 U2 唯一 `decode_execution_envelope(source_bytes)` 重新驗證封存 bytes，並要求 schema/revision、payload hash、raw SHA 與解出的 execution 完全等於 readback。`integrity_basis` 字串本身不是信任根。
- Context typed owners 逐一要求存在，再呼叫 U1 唯一權威 `_validate_result_config_context_overlap` 驗證 owner overlap；完整 post-run result config hash 使用既有 producer `_sha256_json` oracle 核對。沒有複製第二套 overlap 規則。
- 保存的 `Request` raw snapshot、max/top limits、完整 result config、typed owners 與 caller clocks 都保留為獨立來源。`decision_date` 取自完整 result config；允許 `Request.as_of_date` 與結果決策日不同。要求 `available_at <= decision_at`，並保留既有未來時間與 Taipei 建立日檢查。
- 若 execution 有 ML receipt/projection bindings，只接受 U4 `ml_read_status == "verified"` 的 readback；不做即時 inference。
- `RecommendationItem` 依 tuple 原順序逐列映射給既有 builder；`rule_score` 是 packet `total_score` 唯一真值。Decimal/int 數值先轉文字，typed 路徑拒絕 float；理由只取非空 `reason_text`，industry 取封存列；非空 `rank` 必須等於 tuple 一起始的位置。沒有重算理由、industry 或排序。
- typed source trace 分開保留 raw artifact `file_sha256`、完整 canonical source JSON `content_sha256`、U2 canonical `payload_hash`、Request raw-config hash、strategy-config hash 及完整 post-run result-config `config_sha256`。rev2 U2 decoder 要求 raw bytes 為 canonical JSON，因此本格式的 raw file SHA 與完整 canonical source JSON SHA 數值相同；`payload_hash` 與 config hashes 仍各自按其權威材料計算，不能互換。
- forward consumer 不寫 recommendation JSON，也不新增 recommendation writer；成功輸出仍由原 packet builder 建立候選 packet。保存失敗時呼叫端不執行 forward producer；forward producer 發生錯誤時，已保存 source artifact 保留原 bytes。

### Hash preimage 對照

| 身分 | Preimage / 權威計算 | 語意 |
| --- | --- | --- |
| `file_sha256` | artifact 路徑讀出的原始 bytes | 已保存檔案的 byte identity。 |
| `content_sha256` | 整份 artifact document 的 canonical JSON bytes；以 producer `_sha256_json(json.loads(raw_bytes))` 可獨立重算 | 完整 canonical source JSON identity。rev2 decoder 保證檔案 raw bytes 已是此 canonical bytes，因此常與 `file_sha256` 數值相同。 |
| `payload_hash` | U2 codec `decode_execution_envelope` 驗證的 canonical header hash material：`schema_version`、`schema_revision`、`payload`，不含 `payload_hash` 欄位本身 | execution payload identity；即使和其他 hash 數值碰巧相同，也保留獨立欄位與標籤。 |
| `config_sha256` | `_sha256_json(dict(full_post_run_result_config))` | 完整結果 config identity；不同於 Request raw config hash 與 strategy config hash。 |

Request `raw_json_sha256` 與 `strategy_config_hash` 另保留為獨立 provenance 欄位，不作為上表 hash 的替代材料。

## Look-ahead bias 自查

新 seam 僅投影已封存的同次 recommendation execution 與已驗證的保存 readback。它不讀取決策後行情、不呼叫模型 inference、不重算特徵/篩選/分數、不重排推薦，也不以較晚的 Request 日期取代結果決策日。可取得時間需不晚於決策時間；source/owner/hash/clock 不一致會 fail closed。此路徑沒有新增策略、回測、績效或交易計算。

## 合成 fixture

新增 `tests/fixtures/c1_consumer_readiness/r014_saved_execution.json` 與獨立 manifest `r014_fixture_manifest.json`。fixture 是合成 U5a 輸入資料；未覆寫既有 U4 fixture 或 manifest，不含正式資料。

Manifest pin：`r014_saved_execution.json`，11700 bytes，`sha256:ebe481f425be3efa1c3635a71df5ba7c3e1b4054662b53fb980426fe79c11099`。fixture 明確包含 Request raw config hash、strategy config hash、完整 result config hash，並涵蓋 `Request.as_of_date=2026-09-21`、結果 `decision_date=2026-09-22`。

## 驗證

以下命令在實作後執行：

```powershell
.\.venv\Scripts\python.exe -m py_compile app_module\forward_position_thesis_candidate_producer.py tests\test_forward_position_thesis_candidate_producer.py tests\test_c1_forward_consumer_readiness.py
.\.venv\Scripts\python.exe -m pytest tests\test_forward_position_thesis_candidate_producer.py tests\test_c1_forward_consumer_readiness.py -q -o addopts=
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip app_module\forward_position_thesis_candidate_producer.py
```

結果：`py_compile` 通過；pytest `45 passed`；scoped mypy `Success: no issues found in 1 source file`。

Readiness tests 涵蓋 save → U4 query → producer 正例、save failure 時 producer 呼叫數為零、PENDING/rev1/legacy/錯誤 receipt/read model/path/raw hash、缺失或錯誤 owner/snapshot/clock/hash/row、錯誤 rank、`reason_text` 與 `reasons` 衝突、ML readback 不可用、複製 read model 後竄改 execution row/result ID/clock，以及 forward producer 故障後 source artifact bytes 不變。

另執行未忽略 import 的 scoped mypy 命令：

```powershell
.\.venv\Scripts\python.exe -m mypy app_module\forward_position_thesis_candidate_producer.py
```

該命令因共有工作樹中三個被匯入模組的六項 mypy 錯誤而回傳失敗：`app_module/recommendation/contracts.py` 兩項、`analysis_module/technical_analysis/technical_indicators.py` 三項、`app_module/update_service.py` 一項。此任務沒有修改這三個檔案；本次 producer 自身以 `--follow-imports=skip` 的 scoped 檢查通過。

## 限制與審查狀態

- 驗證只覆蓋上述 producer 與 C1 readiness 測試範圍，沒有執行完整 repository QA 或正式資料作業。
- 獨立 Luna Max 審查結果：`Accept U5a only`；確認 45 passed、scoped mypy/py_compile 通過，無剩餘 P0/P1/P2。
- R014 真 scheduled wrapper parity 尚未驗證。C1 狀態仍為 `REOPENED`，Wave 6 狀態仍為 `BLOCKED`；不得據此宣稱完整 C1 / Wave 6 通過。
- 本次未 stage、commit 或 push。共享工作樹其他 U1–U4 檔案保持其既有狀態。
