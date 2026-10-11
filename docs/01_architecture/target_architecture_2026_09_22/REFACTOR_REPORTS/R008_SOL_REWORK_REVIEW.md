> **時點／狀態導覽（2026-10-10）**：本文的 `CHANGES_REQUIRED`、`READY_FOR_REVIEW`、`BLOCKED` 與 Wave／下游 gate 敘述，只代表撰寫當時的 implementer／reviewer／root 裁定，不是目前 disposition；目前 task 狀態看 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 及 [final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)，現況看 [Project Snapshot](../../../00_core/PROJECT_SNAPSHOT.md)。原審查結論與限制保留。

# R008 ML availability 回修：SOL 獨立驗證與正式 Gemini 審查交接

INTEGRATION_STATUS: READY_FOR_GEMINI_REVIEW

## 判定與範圍

SOL 對照 `R008_SOL_CHANGES_REQUIRED_ML_AVAILABILITY.md`、權威 §5.1–5.3／INV-09 及實際程式碼，確認 Luna 只在核准範圍補入 application-owned `MLAvailability`、`MLAvailabilityStatus`、`MLAvailabilityReason`，以及相應 tests、package exports、實作報告。`RecommendationExecution` 現有獨立 `ml_availability`，可在相同的空 projection/receipt refs 下區分未要求、未知、不可用與阻擋，並對後二者保存 typed reason 及可選不可變 detail。`available` 要求 projection 與 receipt refs，`not_requested` 禁止這些 refs；沒有從 terminal status、quality 或空 refs 猜測可用性，也沒有補零。原 DecisionBatch、schema version/revision、舊 DTO、ML internals、consumer、writer、UI 和數值算法均未改。本判定只表示可交 Gemini 正式審查，**不是 R008 PASS**。

## 凍結檔案 SHA-256

| R008 受審檔案 | SOL 現讀 SHA-256 |
|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` |
| `app_module/recommendation/__init__.py` | `6C72A5C327D8F9C1CE9E087E274A510243B1F336D8F71DA1E64DCC0D937882E3` |
| `app_module/recommendation/contracts.py` | `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487` |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` |
| `decision_module/recommendation/contracts.py` | `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB` |
| `tests/test_recommendation_contracts.py` | `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA` |
| `REFACTOR_REPORTS/R008_IMPLEMENTATION_REPORT.md` | `0FA98AF3EDA595A4E10C21FB19DF176D0561490EB79E4AC53305EB5DCA21AD68` |

三個 tracked 檔的實際 `git diff` 仍只涉及原核准的兩個 parent lazy exports 與一個 import-contract 載入時序測試；其餘 R008 檔為 untracked，SOL 逐檔閱讀而非只看 `git diff`。Git index 為空；沒有 stage、commit、push，其他既有 dirty/untracked 檔未動。

## SOL 獨立測試

- R008 contract、R007 leaf、parent import、R003 execution characterization/coordinator 組合：`38 passed`，exit 0。
- R002 characterization、recommendation run support、task-loop 規則切片：`38 passed, 2 existing pandas warnings`，exit 0。
- 兩個 parent 與兩個 recommendation contract 的定向 mypy：`Success: no issues found in 4 source files`；八個受審 Python 檔 `py_compile` 通過；`git diff --check` exit 0（僅 Git LF/CRLF 訊息）。
- SOL 額外探測把 `tests/test_recommendation_service_calibration_integration.py` 併入第二組後得到 `44 passed, 6 failed`。六個失敗都在該**未修改**測試的 `_natural_receipt` fixture 建立階段，`tests/natural_session_source_fixture.py:130` 拋出 `ValueError("evaluation_day must follow every exact-20 session endpoint")`；測試固定 `evaluation_day="2026-06-22"`，尚未進入 R008 contract 或被測 ML consumer 路徑。此既有 fixture 日期不一致須如實列為擴大測試限制，不能宣稱該 ML integration suite 通過，也不授權 R008 偷改其 fixture 或 production。Gemini 可獨立核對這項分類。

## Gemini 必查

請核對上述九個 SHA 與實際 diff，尤其確認 ML availability 的 status/reason/reference 組合符合 INV-09、FINAL ML compatibility contract，且 `UNKNOWN` 預設不冒稱可用；`available` 對兩種 refs 的要求是否與既有 receipt 發布順序相容；enum reason 是否足以保存必需的缺值／阻擋原因。其餘深凍結、Decimal/bp、terminal、parent lazy export、import 無 I/O、typed refs、schema ownership 與測試充分性依正式審查封包逐項檢查。獨立 review 結尾只允許一個 `REVIEW_STATUS`；SOL 收到後仍需核對工作樹與 gate。
