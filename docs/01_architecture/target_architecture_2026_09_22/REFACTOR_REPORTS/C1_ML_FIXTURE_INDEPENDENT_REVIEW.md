# C1 ML Fixture Repair 獨立複審

REVIEW_STATUS: PASS

## 審查對象與範圍

- 凍結測試檔：`tests/test_recommendation_service_calibration_integration.py`
- 凍結檔案識別：Git blob SHA-1 `9f0a25df35e18d62dac28ee1d55ad09e9a975f38`；SHA-256 `636E418C97CAE9BDFAA69DF7F4A2A485934B770FCFAEF1E97D348366AC8AE876`。
- 審查來源：實際工作樹 diff、`tests/natural_session_source_fixture.py` 的 exact-20 guard、`C1_ML_FIXTURE_REPAIR_REPORT.md` 與六個受影響案例的現行斷言。
- 只審查 C1 calibration fixture 日期修復；不代表 C1 其餘驗證閘門通過，也不授權開始 Wave6。

## 結果與證據

修復差異限於上述 integration test 的日期字面值與合成市場資料覆蓋；新增 report 是本次記錄。exact-20 guard `tests/natural_session_source_fixture.py:130` 未修改。六個自然驗證案例仍以 2026-06-01 為候選日，預設 capture weekdays 為 6/1–6/26；最後 capture 的第 20 個後續 weekday 是 7/24，新的 evaluation/adoption date 7/27 晚於 endpoint。六個 promotion 呼叫仍斷言 `decision == "adopt"`（測試行 553、790、1192、1255、1317、1487）。

公開服務案例保留跨日行為：凍結時鐘是 2026-07-27 16:50 UTC（台北 7/28 00:50），source cutoff 仍選 7/27，personalization scope/event date 為 7/28；合成 SQLite 與 market rows 延伸到 cutoff。receipt 仍按 decision date、candidate ID、result ID、stock code 反查，並核對 receipt hash（測試行 843–901、947–968）。forward event price date 為 7/28，20-session outcome / label availability 為 8/25，檢視結果仍要求 20 日窗口與該 label 日期（測試行 1058–1119）。

負例沒有被移除或放寬：after-cost baseline mismatch 與 invalid null benchmark 仍 fail-closed（測試行 656–667、1540–1551）；label contract 欄位不符或缺失仍要求 `rule_only` 與原 warning（測試行 1202–1220、1263–1277）；future research candidate 仍要求 reload/project 降為 `rule_only` 並保留 cutoff warning（測試行 1327–1350）。候選樣本、訓練 as-of、feature schema/values 與 promotion policy 未因日期修復而更改。

實際驗證命令：

```text
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider
12 passed in 12.22s
```

本結論僅確認 fixture repair 及該測試檔；其餘 C1 gates 仍須依整體 checkpoint 狀態判定。此審查不放行 Wave6。
