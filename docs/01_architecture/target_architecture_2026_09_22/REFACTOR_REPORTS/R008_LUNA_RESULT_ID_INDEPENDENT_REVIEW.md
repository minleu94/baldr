> **時點／狀態導覽（2026-10-11）**：本文的 verdict 與 `REVIEW_STATUS` 是該次獨立審查的歷史結果，不等同 R008 整體現行 disposition。[R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 將 R008 列為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`；[R031 final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 未列 R008 專項。此處僅導覽 task-level 狀態，不重裁本文特定結論或限制；原始判讀與限制保留。

# R008 result_id 相容性勘誤：Luna Max 獨立審查

日期：2026-09-22

## 審查範圍與凍結 SHA-256

本次為唯讀獨立審查；只新增本報告，沒有修改 production code 或 tests。

| 檔案 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `CCF12635EBE037548C7695154D2CD661C1FF8182C6663222F1CC219F982BBC63` |
| `tests/test_recommendation_contracts.py` | `29AA1B7EE2412F772526471A962CA6E238B808978FAEE859F40888D547C094CA` |
| `R008_RESULT_ID_COMPATIBILITY_ERRATUM_REPORT.md` | `7966923E5519AF48AAF41DDA3B1A108366BDEAE0E5723FCF54341C40EEB0065A` |

前一個 R008 app contract/test SHA 為 `8CEFCC9D00B8E35D38488D8603486BFEFBBCA575AC74DE27C4BD8147D087E9C1`／`83847793C9C5B78FED6AC12FD0A2ED4E793D76D51FA99656E9E84DBE3B7F0D84`。我在 R009/R010 隔離工作樹找到與這兩個 SHA 相符的舊依賴副本並直接比較 diff，確認 production 改動只移除 `_validate_result_id()` 的 `rec_<canonical UUID>` 解析限制與 `UUID` import；測試只增加可注入 result ID、opaque／generated／legacy 正例、空白與型別反例，以及把 receipt mismatch 案例改用 caller opaque ID。R002 characterization oracle 沒有變更，其現行 SHA 仍為 `E438EE6B742D73C1676FEBAF85314F1B7048A1293D7C7D9605CC57EDFA8B37E5`。

依賴 bytes 也與其最新接受報告相符：R007 market contract/test 為 `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A`／`E98E905515C4B9BE6D4EFD420D44A16AD3ED6FFE1D128A68E850340D4F0C4E4B`，見 `R007_LUNA_TZNAME_INDEPENDENT_REVIEW.md`、`R007_SOL_TZNAME_ACCEPTANCE.md` 與 `WAVE1_R007_TZNAME_CHECKPOINT.md`；R008 decision contract/test 為 `65BE03D7DC9DC667759D814D10A293333BD4D5FA34E30BC8C4854AB5A4C1C85D`／`74CCE82275B7A18AE7499084730AB278ED33E5FD6B6EA280ADD8A6CB4E4BAC9B`，與先前接受的 R008 review SHA 相同。

## 契約與相容性判讀

`_validate_result_id()` 現在呼叫 `_require_nonblank()`。該 helper 只接受精確內建 `str`，用 `strip()` 判斷是否全空白，但不回傳或寫回正規化值。因此非空字串保留原始 bytes/字元，包括空格、大小寫、底線、連字號與前綴；空字串、全空白、`None`、非字串與 `str` 子類仍遭拒絕。`MLReceiptBinding`、`RecommendationExecution`、`SaveReceipt` 都共用這項驗證。

這符合 `REFACTOR_TASKS/R008.md` 的「preserve result_id」要求與 `FINAL_TARGET_ARCHITECTURE.md` §5.1 的身份語意。架構文件描述 `rec_<uuid>` 作為既有 producer 的發號慣例，並要求 execution 與 ML receipt 共用同一身份，沒有授權 contract 對所有 caller-provided IDs 強制該格式。`RecommendationExecution.__post_init__()` 仍以 `binding.result_id != self.result_id` 精確拒絕不同身份，沒有第二 ID、alias 或事後覆寫。這保留 INV-07 的身份一致性；本次沒有變動 INV-08 深凍結機制或 INV-11 唯一 typed schema。

測試涵蓋 `r002-fixed-001`、`rec_` 加 32 位 hex、`rec_<timestamp>`、一般 opaque IDs，以及含首尾空格的 resolved ID，並逐一檢查 ID 經 ML binding、execution 與 save receipt 後保持一致。拒絕測試涵蓋空／全空白、`None`、整數與具可變附帶狀態的 `str` 子類；execution/receipt mismatch 測試仍確認不同 opaque IDs 會被拒絕。

服務產生器仍在 `app_module/recommendation_service.py` 以 `rec_{uuid4().hex}` 建立新 ID。legacy save coordinator 仍保留 producer identity，沒有 identity 時仍使用 `rec_YYYYMMDD_HHMMSS`。既有 fixture 同時使用 R002 的 `r002-*` IDs、`run-20260711`、`rec_20260613_120000`、`rec-isolated-20140331` 與 `rec-real-consumer-20260622`。R008 本次沒有改 service、repository、DTO、ML receipt producer、codec 或 writer，ML schema、欄位順序與數值也未改動。

## R012 writer 邊界

R008 contract 驗證邏輯身份，不負責把 ID 直接轉成路徑。opaque IDs 合法後，R012 writer 必須獨立保護路徑映射與 traversal，例如使用明確安全編碼／獨立檔名映射；同時仍將原始 `result_id` 原樣保存於 artifact 與 index。此 writer 安全要求是 R012 的工作，不構成 R008 identity contract 的修正缺陷。

## 驗證結果

R007/R008/import/execution/save 七檔 focused bundle：**88 passed**。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_recommendation_contracts.py tests/test_r008_decision_numeric_enum_rework.py tests/test_data_market_contracts.py tests/test_update_service_import_contract.py tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py tests/test_recommendation_save_coordinator.py -q -o addopts= -p no:cacheprovider
```

R002 characterization、legacy DTO roundtrip 與隔離 producer→Advice/UI 路徑：**12 passed**。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_recommendation_refactor_characterization.py tests/test_recommendation_dto_roundtrip.py tests/test_recommendation_service_calibration_integration.py::test_isolated_producer_consumer_advice_workbench_ui_path -q -o addopts= -p no:cacheprovider
```

兩個變更 Python 檔案以 `py_compile` 編譯至系統暫存目錄，通過。對 R008 app contract 執行 `mypy --follow-imports=silent`，結果 `Success: no issues found in 1 source file`。不加此選項的匯入圖 mypy 另外回報 `analysis_module/technical_analysis/technical_indicators.py` 的 3 個 `MA_Type` 診斷及 `app_module/update_service.py` 的 1 個 annotation 診斷；兩檔都不在 R008 diff，且不是 R008 contract 本身的錯誤。

額外執行 `test_public_service_real_builder_saves_result_and_reverse_reads_receipt` 時，它在建立自然驗證 fixture 階段失敗：`evaluation_day must follow every exact-20 session endpoint`，尚未走到 R008 contract。使用 R009 隔離工作樹的舊 app contract/test SHA 重跑同一測試，亦在相同 fixture guard 失敗；因此這是既有 fixture 日期問題，不是本次 result_id 變更造成。沒有修改該測試或其 fixture。

## 結論

本次變更修復了已證明的相容性差異，保留 opaque identity 並維持 receipt mismatch 防護。實際 diff 符合原 R008 scope，沒有發現需修正事項。SOL wave/checkpoint 仍應依其自身完整驗證結果判定。

REVIEW_STATUS: PASS
