# R008 Decision 數值與 Enum 深凍結回修報告

## 結果

依 R008-LUNA-04、R008-IQA-01 decision 側 finding，以及 FINAL_TARGET_ARCHITECTURE §5.3 與 INV-06／08／11，完成限定回修：

- `RecommendationItem.score_percentile_bp` 只接受 exact `int` 或 `None`，整數值須落在 `0..10000`。
- `RecommendationItem.eligible_universe_size` 只接受 exact `int` 或 `None`，整數值不得小於 0。
- 不轉型或量化 `rule_score`，不變更既有 score precision、tie-break 或排序語意。
- `_freeze_value` 只接受明示的 `AvailabilityStatus` enum type；其他 Enum subclass 在封存時拒絕。巢狀 `FilterOutcome.evidence` 中帶 mutable `payload` 的自訂 Enum 反例已加入測試。
- 合法 `AvailabilityStatus` evidence 仍保留原 enum member。

## 範圍與回滾

本次僅修改 `decision_module/recommendation/contracts.py`，新增 `tests/test_r008_decision_numeric_enum_rework.py`，以及本報告。未修改既有 `tests/test_recommendation_contracts.py`、app contract／報告、parent `__init__.py` 或其他 R-task 檔案。

契約檔在任務開始前為未追蹤檔案，且已有其他 worker 的內容。修改前已將原檔複製至 `%TEMP%\technical_analysis_R008_decision_contracts_before_20260922.py`；回滾需先檢查並只撤銷本次 patch，不能以 Git 還原或刪除整個既有契約檔。兩個新增檔案若需回滾，須先確認沒有後續 worker 編輯，再移除。

## Look-ahead 與數值檢查

本回修僅新增輸入契約驗證，沒有讀取或改動訊號、特徵、標準化、篩選母體、benchmark、停損停利或時間序列計算，因此沒有引入未來資料讀取路徑。新測試亦驗證既有高精度 `Decimal` score 以原物件及原精度保留。

## 驗證

- `.venv\Scripts\python.exe -m pytest tests\test_r008_decision_numeric_enum_rework.py tests\test_recommendation_contracts.py -q -o addopts= -p no:cacheprovider`：`33 passed`。
- `.venv\Scripts\python.exe -m mypy --config-file mypy.ini --explicit-package-bases decision_module/recommendation/contracts.py tests/test_r008_decision_numeric_enum_rework.py`：2 個來源檔無型態問題。
- `.venv\Scripts\python.exe -m py_compile decision_module\recommendation\contracts.py tests\test_r008_decision_numeric_enum_rework.py`：通過。
- `git diff --check`：通過，沒有 whitespace error；Git 對起始工作樹中其他已修改檔案輸出 LF／CRLF 提示。

## SHA-256

| 檔案 | SHA-256 |
|---|---|
| `decision_module/recommendation/contracts.py` | `C4F691881CB96A86EEF58DB91DDFB4D01AD368DE0C6F6F5DB495C27AB6FA7018` |
| `tests/test_r008_decision_numeric_enum_rework.py` | `56C705E0DB33896B03CBEBF0DDADA4B7FF1C8F5C60F9B6714E8A054CBE0911C0` |

## 未處理項

- IQA-01 的 app-side `QualityReport.metrics` Enum alias 亦在稽核範圍，但該檔屬另一 worker ownership，本次未修改，仍需由其 owner 處理。
- IQA-02 的 parent exports identity 自動 oracle，以及其他 R008 finding 均不在本 worker 授權範圍。
- 未 stage、commit 或 push。
