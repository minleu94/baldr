# R009 實作報告

TASK_STATUS: READY_FOR_REVIEW

## 範圍與結果

新增 schema-driven execution codec、唯讀歷史資料 decoder，以及專用 codec characterization tests。`RecommendationDTO.to_dict/from_dict` 薄委派至具名 codec 函式；原有中英文欄位與記憶體 `dict` 入口保留。未修改 repository、SQL、save caller、ML producer、UI 或持久化整合；`encode_execution` 只產生 bytes，不發布檔案。

R009 在隔離 worktree `output/agent_worktrees/refactor_r009_20260922`、HEAD `166ad745710914312ee8e2e698f230577bfb41a4` 執行。R008 result-id 修正已在派工前完成。`RecommendationExecution.result_id` 按原字串精確序列化與還原；fixture 包含大小寫、斜線及尾端空白，證明不做 UUID 正規化。路徑安全名稱映射由 R012 負責。

## Wire 格式與 canonical hash

新格式根物件僅包含 `schema_version`、`schema_revision`、`payload`、`payload_hash`。目前 writer 使用 `recommendation-execution.v1` 與 revision `1`。Revision owner contract 宣告 `EXECUTION_SCHEMA_REVISION = 1` 及 `SUPPORTED_EXECUTION_SCHEMA_REVISIONS = (1,)`；codec 直接使用該明示範圍。未知 schema 或未列入支援 tuple 的 revision 會在建立 contract 前拒絕。

`payload_hash` 格式為 `sha256:<小寫十六進位>`，雜湊輸入是包含固定 schema header 與具型別 payload 的 canonical JSON bytes：`{schema_version, schema_revision, payload}`。canonical JSON 固定排序 key、UTF-8、`ensure_ascii=False`、separators `(',', ':')`，並拒絕非有限 JSON 數值。新格式 artifact bytes 不含可變 metadata；label、notes、persisted_at 由 R012 的 index／metadata 命令另存。因此相同 execution 只會產生同一份 canonical bytes，同 hash 不會因 metadata 更新而對應不同 artifact bytes。

Reader 只接受 `SUPPORTED_EXECUTION_SCHEMA_REVISIONS` 明列的 revision，包括其中較舊的相容 revision。相同 schema 的新增 optional 欄位使用 owner contract 的 default/default factory；不可相容變更須提升 schema version 並明示 decoder。當前 R008 contract 宣告僅支援 revision 1。依主工作樹 `REFACTOR_REPORTS/R009_SCHEMA_RANGE_SCOPE_ADDENDUM.md` 的窄範圍裁決，唯一額外 production 變更是在 owner contract 增加支援 tuple；未更動既有 R008 schema、validation、parent export 或數值語意。

| Contract 值 | Wire 表示 |
|---|---|
| allowlist frozen dataclass | `{"$record": <穩定 wire id>, "fields": <dataclass 欄位>}`；欄位及 annotation 執行期讀取 contract 定義。 |
| enum | `{"$enum": <穩定 wire id>, "value": <enum 值>}` |
| Decimal | `{"$decimal": <精確有限十進位字串>}`；不經 float。 |
| date | `{"$date": <canonical ISO date>}` |
| aware datetime | `{"$datetime": <含 offset 的 canonical ISO 8601>}`；拒絕 naive timestamp。 |
| integer、string、boolean、null | 原生 JSON integer、string、boolean、null；不把 bool 當 integer。 |
| tuple | JSON array；decode 後還原 tuple。 |
| typed mapping | string key 的 JSON object；dynamic nested mapping 使用明確 `$mapping` wrapper。 |
| 缺少 optional 欄位 | 使用 dataclass 欄位明定的 default 或 default factory。 |

Record／enum registry 僅列穩定 wire type ID，不重複維護 scalar 欄位清單。未知 type ID、未知 record 欄位、不支援的 runtime value、float 及 allowlist 外 annotation 一律拒絕。Codec 依 `dataclasses.fields` 和型別 annotation 遞迴處理；不呼叫 `asdict`、不讀取 `__dict__`、不使用 pickle，也不匯入 artifact 指定的型別。

## 歷史讀取相容性

`decode_legacy_recommendation(mapping)` 與 `RecommendationDTO.from_dict(dict)` 是記憶體相容入口，本身沒有原始 bytes，因此不要求 raw SHA。它們保留中英文 aliases、close price 的 `Decimal` 轉換、quantile display keys、calibration metadata，以及舊有 score float 轉換語意。

`decode_legacy_result(bytes, expected_sha256=...)` 與 bytes-level `decode_artifact(bytes, expected_sha256=...)` 必須提供原始 bytes 的 SHA-256，並在 JSON parse／DTO 建構前驗證。`decode_artifact` 對新格式也先驗證來源 bytes，之後再驗證 canonical payload hash；直接使用新格式 `decode_execution(bytes)` 則由內嵌 canonical payload hash 驗證。兩種 SHA 用途分開：raw SHA 綁定來源 artifact bytes，payload hash 綁定 canonical execution payload。所有入口都不改寫原始 bytes。

舊結果的排除候選、screening rows、`why_not_payload_json` negative evidence、liquidity payload 與 calibration details 仍經既有 `RecommendationResultDTO` 相容邊界保留。R004 persistence characterization 未修改且通過。R004 fixtures 未發現額外 serialized Python qualified-name alias；新格式 type ID 是明確穩定字串，並非 import path。若已部署 artifact 證明還有其他 alias，必須保留為永久讀取相容。

舊 `app_module.dtos` façade 仍為相容呼叫端保留。退場登錄：

- `CREATED_TEMPORARY_COMPONENT: TMP-REC-05` — 舊 `RecommendationDTO` façade 與明示舊格式 export。
- `REMOVES_TEMPORARY_COMPONENT: R029` — 呼叫端遷移證明不再需要 façade 後移除；歷史 artifact decoder 必須保留。

## 架構與相容性檢查

- **INV-01：** fixture 以唯讀方式解碼；bytes-level artifact decoder 在建立 DTO 前驗證原始 SHA。
- **INV-08：** 僅重建 allowlist frozen contracts；constructor 會重新套用既有 freeze 與 validation。
- **INV-11：** dataclass fields／annotations 是新格式唯一欄位 schema；未知 schema、type 及欄位會被拒絕。
- **INV-12：** 未新增 persistence writer、repository 整合、index 或 save 行為；可變 metadata 不進入 artifact bytes。
- **INV-17：** `TMP-REC-05` 有 R029 退場 owner 與條件；歷史讀取相容明確保留。
- ML projection 與 receipt reference 僅作 typed value round-trip；codec 不匯入 trainer、feature builder 或 model code，也不解讀 feature value。
- R008 opaque `result_id` 原樣保留；codec 不檢查路徑安全性，也不改寫 identity。

## 驗證

在 R009 隔離 worktree 執行：

| 檢查 | 結果 |
|---|---|
| `tests/test_recommendation_execution_codec.py` | 18 passed |
| `tests/test_r004_recommendation_persistence_characterization.py` | 11 passed |
| R008 `tests/test_recommendation_contracts.py`、`tests/test_r008_decision_numeric_enum_rework.py`、`tests/test_update_service_import_contract.py` | 51 passed |
| R007 `tests/test_data_market_contracts.py` 與 `tests/test_data_module.py` | 21 passed |
| 合併的 R009／R004／R008／R007 focused suite | 101 passed |
| 三個 R009 source files 的 focused mypy（`--follow-imports=skip --ignore-missing-imports`） | 通過；3 files 無問題 |
| 變更 source／test files 的 `py_compile` | 通過 |
| R009 scope whitespace validation（DTO／contract baseline diff 與新檔案 trailing-whitespace scan） | 通過；無 whitespace error |

同三個 source files 的一般 mypy 會沿 import 回報 4 個 R009 範圍外錯誤：`analysis_module/technical_analysis/technical_indicators.py` 3 個，以及 `app_module/update_service.py` 1 個。focused R009 mypy 檢查乾淨。提供的虛擬環境未安裝 Ruff。

## 變更範圍與凍結輸入

R009 所有權輸出：

- 修改 `app_module/recommendation/contracts.py`，僅新增 `SUPPORTED_EXECUTION_SCHEMA_REVISIONS: tuple[int, ...] = (1,)` — SHA-256：`813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81`。
- 新增 `app_module/recommendation/codec.py` — SHA-256：`A1BC97DE557C58FCAA039D06DAE909123A3E405B5E2DD7776B94F9A80ED653BE`。
- 修改 `app_module/dtos/__init__.py` 的 `RecommendationDTO.to_dict/from_dict` 薄委派 — SHA-256：`FAF14BF53E005F82ED2A8B97697549C74FDA2D2CD695E97F934CBA5FC0BE365B`。
- 新增 `tests/test_recommendation_execution_codec.py` — SHA-256：`3E6BDE7EF1594E55F2F4FC5A5F0BB9AF781BBC645EF6C666DAB686C217D4E9BF`。

依窄範圍補充裁決，`app_module/recommendation/contracts.py` 是唯一修改的 R008 shared dependency；相對派工 baseline 的 diff 只有支援 revision tuple 一行。其餘 12 個共用凍結依賴檔案與 R004 characterization test 均符合 baseline SHA；R008 對應 test SHA 為 `29AA1B7EE2412F772526471A962CA6E238B808978FAEE859F40888D547C094CA`，R004 test SHA 為 `F7F9F5E34CB9653511E4B2BC4A7280CFCCECD0F9A54BB3F54D153972F4A1E321`。

未修改其他 R-task 檔案，未 stage、commit、push、reset 或 clean。DTO 改動刻意限於 method hunk；主工作目錄該檔案的換行格式不同，整合時應套用窄 patch，不要整檔複製。

## 驗收與限制

目前 contracts 已符合 R009 驗收：typed fixture 全欄位 round-trip；optional scalar 由 `dataclasses.fields` 自動涵蓋；Decimal scale、date、offset datetime、nested negative evidence、null／zero 與 opaque result ID 均保留；canonical bytes/hash 穩定；中英文舊 fixture 讀取不改原 bytes；bytes-level 舊格式先驗 raw SHA；未列入 owner contract 支援 tuple 的 schema revision、type 與 header 欄位遭拒絕。測試亦明確涵蓋 revision 1 接受、revision 0／2 拒絕，以及模擬 current revision 2 且支援 `(1, 2)` 時，舊 revision 1 缺少 optional `events` 仍依 default 讀回。

本任務沒有接通持久化 writer。`encode_execution` 僅負責產生 canonical bytes；R012 負責 create-only 發布、索引及可變 metadata。R008 目前宣告的 schema revision 為 1；後續 revision 仍需 owner contract 與明確 root revision 更新。不相容的 schema 變更需依架構提供 versioned decoder。
