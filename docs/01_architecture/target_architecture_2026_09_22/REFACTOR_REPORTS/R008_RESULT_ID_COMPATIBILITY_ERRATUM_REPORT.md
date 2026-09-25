# R008 result_id 相容性勘誤報告

日期：2026-09-22

## 範圍與結果

依 `R008_SOL_RESULT_ID_COMPATIBILITY_REOPEN.md`、`REFACTOR_TASKS/R008.md` 及 `FINAL_ARCHITECTURE_INVARIANTS.md` 的 INV-07–11，修正 app contract 對既有 result identity 的格式限制。只修改 `app_module/recommendation/contracts.py`、`tests/test_recommendation_contracts.py`，並新增本報告；沒有修改 service、DTO、writer、R002 golden、R007/其他 R-task、ID 產生慣例或金融數值邏輯。

`_validate_result_id()` 現在只要求 result ID 是精確內建 `str` 且非空白，原字串直接保留；不 strip、不 lower、不補 prefix，也不解析 UUID。`RecommendationExecution`、`MLReceiptBinding` 與 `SaveReceipt` 共用此驗證。Execution 仍以精確字串相等檢查 receipt binding 身分，異 ID 照常拒絕，符合 INV-07 的單一 execution identity。

## 回歸測試

- 正例使用 `r002-fixed-001` caller ID、`rec_` 加 32 位 hex 的服務生成形狀、`rec_<timestamp>` legacy 形狀，以及 `run-20260711`、`result-1`、`last-good-result`；另用首尾含空格的非空字串確認 contract 不正規化。每個 ID 都經 ML binding、execution 與 save receipt 往返並保持完全相同。
- 反例覆蓋空字串、純空白、`None`、整數及 `str` 子類。Opaque ID 的 receipt/execution 不相等仍會拒絕。
- 不在 R008 contract 驗證 opaque ID 是否適合作為檔案路徑；artifact 路徑映射與 traversal 防護屬 R012 writer 範圍，需由該邊界處理。

## 驗證

- R008/R007/import 六檔 focused bundle：**82 passed**。
- `tests/test_recommendation_contracts.py`：**23 passed**。
- `py_compile`：兩個修改的 Python 檔案通過。
- scoped mypy：`app_module/recommendation/contracts.py` 通過，無錯誤。
- 對本次範圍檔案檢查 whitespace 與換行；沒有 stage、commit 或 push。

## SHA-256

| 檔案 | 勘誤前 | 勘誤後 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `8CEFCC9D00B8E35D38488D8603486BFEFBBCA575AC74DE27C4BD8147D087E9C1` | `CCF12635EBE037548C7695154D2CD661C1FF8182C6663222F1CC219F982BBC63` |
| `tests/test_recommendation_contracts.py` | `83847793C9C5B78FED6AC12FD0A2ED4E793D76D51FA99656E9E84DBE3B7F0D84` | `29AA1B7EE2412F772526471A962CA6E238B808978FAEE859F40888D547C094CA` |

此勘誤保留既有 identity 行為，不引入第二個 ID 或架構變更。跨 owner 的 R008 最終審查與 suite 由 SOL gate 統一執行。
