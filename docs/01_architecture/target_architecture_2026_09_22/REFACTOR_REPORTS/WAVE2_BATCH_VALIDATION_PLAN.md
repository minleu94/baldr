# Wave 2／R008 批次驗證計畫

> **2026-10-11 直開範圍提示：** 本文件的 `GATE_STATUS`、測試結果與「Wave 3 可啟動」均是 R008 result-ID 勘誤後的歷史驗收快照；R031 current row 將 R008 定界為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`，後續 consumer wiring 由 R011–R019 分別處理，見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 與 [R031 closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md)。下方 test-inventory 缺項說明也屬當時狀態；2026-10-11 核對時兩個測試均已列入[目前清冊](../../../../qa/full_app_healthcheck/test_inventory.py)，這只確認項目存在，不代表整體 inventory audit 通過。

## Gate 判定

**GATE_STATUS: PASS_AFTER_RESULT_ID_ERRATUM**

R011 唯讀準備揭露舊版 R008 result_id 格式拒絕既有 caller opaque ID 與服務自產 hex ID。詳 `R008_SOL_RESULT_ID_COMPATIBILITY_REOPEN.md`；該缺口已在 R008 原 scope 修正，新 SHA 的獨立審查與 SOL 驗收見 `R008_LUNA_RESULT_ID_INDEPENDENT_REVIEW.md`、`R008_SOL_RESULT_ID_ACCEPTANCE.md`，checkpoint 見 `WAVE2_RESULT_ID_CHECKPOINT.md`。本文下方原批次結果仍屬舊 SHA 歷史。

Wave 2 只有 R008；R008 依賴已完成的 R002、R003、R007。canonical contracts 的深凍結、terminal 狀態組合、typed ownership 與 import 邊界已在最新 SHA 通過。SOL 終版驗收見 `R008_SOL_FINAL_ACCEPTANCE.md`，Wave 2 checkpoint 見 `WAVE2_CHECKPOINT.md`；Wave 3 已可依隔離 worktree 規則啟動。C1–C4 是後續 hard gates，不屬本 wave 驗收。

早期 SOL `CHANGES_REQUIRED_WITHIN_R008`、初版 implementation report 的 `61 passed` 及其 SHA 只屬舊版歷史；其後 ML receipt、datetime offset、時區名稱別名均已在 R008 原 scope 修正。終版獨立 Luna `R008_LUNA_FINAL_FROZEN_REVIEW_V2.md` 為 `PASS`，SOL 已重驗並簽收。後續不再派送 Gemini。

歷史 `R008_GEMINI_PRE_BATCH_PASS.md` 的 `REVIEW_STATUS: PASS` 僅對其核對的舊九檔 SHA 有效；本輪 gate 使用最新 Luna review 與 SOL acceptance。

## R008 驗證命令與覆蓋

Wave 2 最小聚焦 pytest bundle：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest `
  tests/test_recommendation_contracts.py `
  tests/test_r008_decision_numeric_enum_rework.py `
  tests/test_data_market_contracts.py `
  tests/test_update_service_import_contract.py `
  tests/test_recommendation_execution_state_characterization.py `
  tests/test_recommendation_execution_coordinator.py `
  -q -o addopts= -p no:cacheprovider
```

此組覆蓋 R008 app/decision contracts 的遞迴凍結、mapping backing copy、Enum mutable alias 拒絕、terminal cause 與空／失敗／取消狀態、ML availability 和 receipt binding 的 hash/result/date/stock-code 一致性、Decimal/null/zero、百分位 bp 與 universe 範圍、17 個 parent exports 的 identity/import，以及 R007 leaf、無 I/O import 邊界和 R003 execution characterization。SOL 在最終 SHA 重跑此六檔 bundle **80 passed**；獨立 Luna 額外加入 `tests/test_data_module.py`，七檔 bundle **85 passed**。若任何已凍結檔案再變更，須重新審查與測試。

搭配 static checks：

```powershell
.\.venv\Scripts\python.exe -m mypy --explicit-package-bases app_module/__init__.py decision_module/__init__.py app_module/recommendation/contracts.py decision_module/recommendation/contracts.py
.\.venv\Scripts\python.exe -m py_compile app_module/__init__.py decision_module/__init__.py app_module/recommendation/__init__.py app_module/recommendation/contracts.py decision_module/recommendation/__init__.py decision_module/recommendation/contracts.py tests/test_update_service_import_contract.py tests/test_recommendation_contracts.py tests/test_r008_decision_numeric_enum_rework.py
git diff --check
```

最新實作報告記錄上述四個 contract/parent source 的 mypy 通過、相關 Python 檔案 py_compile 與 tracked/untracked whitespace checks 通過。因本輪新增了 app recommendation package export，SOL 重驗時應將兩個 `recommendation/__init__.py` 一併納入 mypy source list。`git diff --check` 不涵蓋 untracked files，須另驗那些新增檔案的 whitespace。

## 已跑、待跑與受影響測試

- **已完成：** 六檔 bundle SOL `80 passed`、七檔 bundle 獨立 Luna `85 passed`；scoped mypy、py_compile 與 diff check 通過。獨立 review、SOL acceptance 與 Wave 2 checkpoint 均已記錄。
- **僅作既有相鄰限制：** calibration integration 擴大測試曾報 `44 passed, 6 failed`；六個失敗都在固定日期 `_natural_receipt` fixture 的 exact-20 endpoint guard，尚未進入 R008 consumer。它不能宣稱通過，也不是 Wave 2 R008 的驗收 bundle。
- **回修直接影響的 tests：** `test_recommendation_contracts.py`（receipt binding、ML status、terminal cause、深凍結與 export identity）、`test_r008_decision_numeric_enum_rework.py`（bp/count 邊界與 Enum alias）、`test_update_service_import_contract.py`（parent lazy export 相容性）。R007 import guard 與 R003 execution-state/coordinator characterization 為相鄰回歸覆蓋。
- **清冊待補（專案 QA 強制規範，非 R008/Wave 2 acceptance）：** `qa/full_app_healthcheck/test_inventory.py` 目前找不到 `tests/test_recommendation_contracts.py`、`tests/test_r008_decision_numeric_enum_rework.py` 條目。權威依據是 `docs/06_qa/TEST_INVENTORY_HEALTHCHECK_CLASSIFICATION_2026_06_23.md` 指定該程式為逐檔清冊權威，以及 `tests/test_full_app_healthcheck_test_inventory.py:36-38` 對 filesystem 測試 Python 檔逐項檢查、缺登錄即失敗；所以在下一次 inventory audit 前須補登。`REFACTOR_VALIDATION_MATRIX.md` 的 R008 row 與 Wave 2 checkpoint 未把 registry audit 列為 R008 acceptance，故此項是獨立 QA 清冊義務，不單獨阻塞 R008 gate；若要宣稱 inventory audit 通過，仍必須先補登。

本文件是 Wave 2 驗證路徑與最終 gate 記錄；SHA、限制及原始命令以 `R008_SOL_FINAL_ACCEPTANCE.md` 為準。
