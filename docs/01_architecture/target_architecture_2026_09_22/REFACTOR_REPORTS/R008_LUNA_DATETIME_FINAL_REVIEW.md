# R008 Luna Max datetime 深凍結最終獨立審查

REVIEW_STATUS: PASS

本次以工作樹中的實際 bytes 獨立審查 R008 datetime 回修。四個指定 SHA-256 全部吻合：

| 檔案 | 實際 SHA-256 | 判定 |
|---|---|---|
| `app_module/recommendation/contracts.py` | `BBFBFD0B8F8A18C4A90CAA1E618203EF2738D4E75B0C1ECA32B96E9AAF693684` | 符合 |
| `decision_module/recommendation/contracts.py` | `E441C49EEDCC703BF282D9617EFA3F9768CD633E57EA50F1D4523719AB85710A` | 符合 |
| `tests/test_recommendation_contracts.py` | `2B7CB0DFFA3CC30835087D54D61DF768437B295AAE278B056041DCD8E3D58F9D` | 符合 |
| `tests/test_r008_decision_numeric_enum_rework.py` | `8073FBA2CC9BD07A2B95F4BBED4986CA65F81B1DAFD04F82D96D37CA5568C852` | 符合 |

## 審查結果

- 依 R008、FINAL_TARGET_ARCHITECTURE §5.3、INV-03/06/07/08/09/11，以及 datetime addendum、先前 Luna review、app/decision freeze reports 和最新 implementation report 核對契約邊界。直接欄位與遞迴 mapping/sequence/record 路徑均保存凍結後 datetime；decision `NegativeEvidence.observed_at` 也寫回 helper 回傳值。custom `tzinfo` 只取封存當刻 offset 並建立新的固定 offset timezone，保留 wall-clock、microseconds、fold、offset、ISO 和 timestamp；不再持有呼叫端 tzinfo。
- 重現先前 `MutableTimezone` PoC：建立 Context、NegativeEvidence（直接欄位及巢狀 details）和 QualityReport 後，將原 timezone offset 從 0 改為 +9 小時。原輸入確實改變，所有 sealed offset 前後均為 `0:00:00`，沒有時間漂移。
- 核對 timezone 語意：精確型別 `datetime.timezone` 與 `ZoneInfo` 保留；其他 tzinfo 轉成封存當刻固定 offset。另以 `America/New_York` 的 DST fold=1 時間檢查 app/decision 兩側 offset、ISO、timestamp、fold 及隔日 DST 算術，並確認固定 +08:00 offset 維持原有語意。
- import audit 的 subprocess 測試通過：contract import 未讀取非程式檔、未連 SQLite，domain 未反向匯入 app，app leaf import 未載入 service/DTO、pandas 或 matplotlib。
- terminal 與 ML checks 未見退化：completed 仍必須有 DecisionBatch（可零列）；failed/cancelled 不發布 decision 並要求非空原因。ML availability 仍明示 status/reason，receipt binding 保留 hash/result/date/股票核對；零列結果不合成空 projection receipt。
- numeric checks 未見退化：percentile 僅 exact int/None 且限 `0..10000`，universe size 不可為負；測試仍涵蓋零值、None、bool/float 拒絕及原 score precision。

## 驗證

執行合併 focused suite：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_recommendation_contracts.py tests/test_r008_decision_numeric_enum_rework.py tests/test_data_market_contracts.py tests/test_update_service_import_contract.py tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py -q -o addopts= -p no:cacheprovider
```

結果：`69 passed in 6.48s`。另以唯讀 Python smoke 重現 mutable-tzinfo PoC，並檢查 ZoneInfo/fixed-offset 行為；兩者通過。

R007 dependency correction worker 仍在定稿中；本報告不把目前 R007 暫時 bytes 當成 R008 最終整合 gate。此 PASS 僅涵蓋上述 R008 contract/test bytes 與本次 focused evidence，R007 依賴狀態仍待其定稿後另行確認。

本次只新增此報告；沒有修改 production/tests，沒有 stage、commit 或 push，也保留既有 unrelated dirty changes。
