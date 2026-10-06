# R008 parent package import 範圍裁決

## 實測與判定

R008 Luna worker 在變更前用獨立 Python import smoke 查出：一般匯入新 `decision_module.recommendation.contracts` 與 `app_module.recommendation.contracts` 時，Python 必先執行各自 parent `__init__.py`。現有 decision parent eager import 經 analysis/pattern → Matplotlib 讀取 `matplotlibrc` 等非程式資源；app parent eager import 還讀取時區資料。SOL 獨立重跑 parent import，`decision_module` 已載入 15 個 decision modules 與 pandas，`app_module` 已載入 42 個 app modules、21 個 decision modules 與 pandas。worker 尚未修改任何檔案即停手。source 核對未見 decision parent 反向載入 app 或 SQLite connect。

這是既有 package 初始化對「新純 leaf contract 匯入不得觸發 I/O」的實作衝突，不是 `FINAL_TARGET_ARCHITECTURE` 中 contract owner/型別無法成立的架構矛盾。SOL 將它判為**可在 R008 原目標內修正的範圍缺漏**，不是正式 `ARCHITECTURE_BLOCKER`。R007 曾就 `data_module/__init__.py` 有同型窄修正與相容審查。

## 受控範圍

僅增列 `decision_module/__init__.py`、`app_module/__init__.py` 兩個 package 入口供 R008 worker 獨占；只允許將原 public exports 改為窄 lazy exports。原名稱、`__all__`、direct/star import、class identity 與被測呼叫路徑必須相容。SOL 獨立重跑 `tests/test_update_service_import_contract.py` 得 1 passed／1 failed；唯一失敗為原測試把「匯入 `app_module.update_service` 就預載七個 service」當成 oracle。此與受控 lazy 修正直接衝突，故允許 R008 **只改該測試的載入時序斷言**：存取 public class 前只載入被指定子模組，逐一明示存取後仍載入原服務且 class identity、`__all__` 不變。不得放寬或移除其他 assertions。不得改 service、DTO、codec、save、UI 或其他 R-task，亦不接任何 production consumer。新增 import smoke 必須證明 contract import 無非程式檔 I/O／DB 連線與 domain→app 逆向依賴；對 bare parent module `__dict__` 時序差異須明列。若不能在此界線通過，就回報具體 blocker 而非擴大修正。

已同步 R008 task spec 與 Wave 2 execution-order 註記。Wave 2 仍只執行 R008，後續正式 Gemini review 需特別審查此兩檔及所有公開 import 相容性。

SCOPE_DECISION: CHANGES_REQUIRED_WITHIN_R008
