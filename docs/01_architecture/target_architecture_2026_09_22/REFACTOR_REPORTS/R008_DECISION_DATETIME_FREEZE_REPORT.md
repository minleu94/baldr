# R008 decision aware datetime 深凍結回修報告

> 本報告是 decision-owner datetime 回修證據，不是 R008 task-level verdict。現行 bounded contract disposition 以 [R031 R008 row](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 為準；consumer／codec 等範圍仍依各自 task 判定。

## 結果與範圍

修復 `decision_module/recommendation/contracts.py` 的 aware `datetime` alias 洩漏。封存時會建立新的 datetime 值，保留年月日時分秒、微秒與 `fold`。只有標準 `datetime.timezone` / `ZoneInfo` 搭配 exact builtin `timedelta` offset 與 exact builtin `str` timezone name 才沿用 tzinfo；其他情況會從 `timedelta` 基底描述符讀取 `days`、`seconds`、`microseconds`，建立 exact builtin `timedelta` 後再建固定 offset timezone。這可隔離自訂 tzinfo 回傳的可變 `timedelta` 子類，也涵蓋 exact `timezone` 本身回傳該子類的情況。重建 timezone 時會用 `str.__str__` 複製名稱的底層文字，保留名稱值並移除 `str` 子類 alias。

`NegativeEvidence.observed_at` 現在會保存凍結後的副本。共用 `_freeze_value` 遞迴路徑也會處理 mapping、sequence 與允許的 frozen contract，因此直接及巢狀 datetime 均有相同保護。

## 涉及欄位與深凍結範圍

| 欄位 | 封存方式 |
|---|---|
| `NegativeEvidence.observed_at` | 直接欄位改存新的 aware datetime 快照。 |
| `NegativeEvidence.details` | mapping backing dict 複製後遞迴凍結其中 datetime。 |
| `FilterOutcome.evidence` | mapping backing dict 複製後遞迴凍結其中 datetime。 |
| `LiquidityAssessment.observations` | mapping backing dict 複製後遞迴凍結其中 datetime。 |
| 上述欄位中的巢狀 sequence、mapping 與允許的 frozen records | 使用同一遞迴凍結路徑，不保留原 datetime 或 mutable tzinfo alias。 |

其他 contract 欄位、數值型別、驗證規則、排序或推薦計算都未更動。拒絕規則維持封存白名單：naive datetime 或沒有 offset 的 datetime 以 `ValueError` 拒絕；不能建成合法固定 offset timezone 的值亦拒絕；未知巢狀型別、非字串 mapping key 與循環參照依既有規則拒絕。直接欄位仍要求 exact `datetime` 型別。自訂 tzinfo 的 name/DST 規則不作保存；可信 timezone 的名稱底層字串會保留，但其可變 `str` 子類行為與屬性不保留。

## 舊 DTO 欄位邊界

依 R008 implementation report 的既有欄位歸屬，本回修沒有搬移或轉換舊 DTO 欄位：

- `RecommendationDTO` 的股票識別、價格、rule score、理由、產業及 regime 欄位仍屬既有業務/UI DTO；舊中文 key 與 `to_dict` / `from_dict` 表示仍屬 legacy wire。percentile、universe size/date、ranking method、threshold mode 是既有 canonical decision 欄位的 legacy 對應，所需 adapter 仍未在本回修實作。
- calibrated probability、after-cost probability、evidence confidence、sample size、cost basis、calibration model/dataset/horizon/status/source/warnings/trace 與 probability lineage 欄位屬 ML projection，沒有加入 `RecommendationItem`。
- `RecommendationResultDTO` 的 result envelope、可變 config/recommendations、string timestamp、notes，以及 screening/exclusion/liquidity 等 JSON payload 欄位仍是 legacy envelope/wire；本回修沒有轉換它們。

上述 legacy numeric/date adapter、ML projection ABI、codec 與持久化仍由各自後續任務處理；本回修不宣稱已驗證那些邊界。

## 驗證

- `.venv\Scripts\python.exe -m pytest tests/test_r008_decision_numeric_enum_rework.py -q -o addopts=`：26 passed。涵蓋 mutable tzinfo、mutable `timedelta` 子類與 mutable timezone-name `str` 子類修改前後、直接 `observed_at`、巢狀 evidence/details/observations、microseconds、fold、offset、ISO、timestamp、timezone explicit name，以及 UTC、固定 offset 和 DST `ZoneInfo`。
- `.venv\Scripts\python.exe -m mypy decision_module/recommendation/contracts.py`：因匯入圖中既有 `analysis_module/technical_analysis/technical_indicators.py` 三個 TA-Lib `MA_Type` 型別錯誤而失敗（`STOCH` 的 `slowk_matype`、`slowd_matype` 及 `BBANDS` 的 `matype` 收到 `int`）。
- `.venv\Scripts\python.exe -m mypy --follow-imports=silent decision_module/recommendation/contracts.py tests/test_r008_decision_numeric_enum_rework.py`：通過，2 個授權來源檔無型態問題；匯入模組錯誤未在此模式重複檢查。
- `.venv\Scripts\python.exe -m py_compile decision_module/recommendation/contracts.py tests/test_r008_decision_numeric_enum_rework.py`：通過。
- pytest 顯示 cache 無法寫入 `.pytest_cache` 的權限警告；測試結果仍為成功。

## 修改前後 SHA-256

| 檔案 | 修改前 | 修改後 |
|---|---|---|
| `decision_module/recommendation/contracts.py` | `C4F691881CB96A86EEF58DB91DDFB4D01AD368DE0C6F6F5DB495C27AB6FA7018` | `65BE03D7DC9DC667759D814D10A293333BD4D5FA34E30BC8C4854AB5A4C1C85D` |
| `tests/test_r008_decision_numeric_enum_rework.py` | `56C705E0DB33896B03CBEBF0DDADA4B7FF1C8F5C60F9B6714E8A054CBE0911C0` | `74CCE82275B7A18AE7499084730AB278ED33E5FD6B6EA280ADD8A6CB4E4BAC9B` |

## 回滾與限制

下列 `%TEMP%` 備份路徑是當時作業記錄，未核實至今仍存在或仍對應目前版本；不可直接作目前還原指示。

本次 tzname alias 增補前的 contract、test 與報告副本保存在 `%TEMP%\r008-decision-tzname-alias-before-review\`。若需回滾本輪增補，先確認沒有後續編輯，再從該目錄還原三個檔案；不得用 Git checkout/reset 還原整個未追蹤 contract。此次未修改 app contract/test、parent `__init__.py` 或其他 R-task，未 stage、commit 或 push。

自訂 mutable tzinfo 的 timezone name 與 DST 規則不會被複製；其封存結果固定在當刻 offset。標準 `timezone` 與 `ZoneInfo` 只有在 offset 與 name 都是 exact builtin 型別時保留原 tzinfo；timezone name 為 `str` 子類時則複製底層文字值。這次只處理 decision contract，app contract 的時間欄位與跨 contract 相容性由其 owner 負責。
