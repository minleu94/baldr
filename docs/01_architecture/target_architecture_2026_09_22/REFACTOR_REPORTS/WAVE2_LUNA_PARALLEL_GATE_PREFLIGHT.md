# Wave 2 獨立唯讀 Gate 預檢

## 範圍與判讀

本報告依 R008、Wave 2／3 執行順序、驗證矩陣、R008→R009/R010 DAG、FINAL invariants、R008 SOL 回修審查與舊 Gemini 收件裁決進行唯讀核對。HEAD 為 `391b057c92037ec7a19cab2bf951d6029d29b020`。預檢不標記 R008 或 Wave 2 PASS，也不授權 Wave 3。

Wave 1 checkpoint 記載 R002–R007 均 PASS；R008 的前置 R002、R003、R007 已有相應 characterization／leaf contract、SOL 與 Gemini 審查證據。執行順序要求 R008 單獨完成、contracts 深凍結／terminal combinations／typed ownership 驗收，再通過 Wave 2 checkpoint 才可進入 R009、R010。C1–C4 是後續 checkpoint，尚非本 wave 的驗收項。

## 已直接核實

- R008 實作與回修範圍仍限於兩個 recommendation contract packages、其測試、核准的 `app_module/__init__.py` 與 `decision_module/__init__.py` 窄 lazy exports、`tests/test_update_service_import_contract.py` 載入時序 oracle，以及 R008 報告。實際搜尋未發現 canonical `RecommendationExecution`／`DecisionBatch` 已接入 production consumer、codec 或 writer；仍未進入 R009/R010 或 consumer migration。
- `R008_SOL_REWORK_REVIEW.md` 列出的九個凍結檔案 SHA-256 均與目前磁碟 bytes 相符，包含 ML availability 回修後的 `app_module/recommendation/contracts.py` 與 `tests/test_recommendation_contracts.py`。目前沒有把 R008 的 canonical types 接到既有 UI execution coordinator；該 coordinator 使用的是既有 `RecommendationExecutionRequest` 名稱與路徑。
- 獨立 focused 驗證命令：

  ```powershell
  $env:PYTHONDONTWRITEBYTECODE = '1'
  .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_contracts.py tests/test_data_market_contracts.py tests/test_update_service_import_contract.py tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py -q -o addopts= -p no:cacheprovider
  ```

  結果：`38 passed in 4.48s`。涵蓋 R008 contract/deep-freeze、R007 leaf contract、parent import 邊界與 R003 execution characterization/coordinator。
- 獨立重跑前置 recommendation/task-loop 切片：

  ```powershell
  $env:PYTHONDONTWRITEBYTECODE = '1'
  .\.venv\Scripts\python.exe -m pytest tests/test_recommendation_refactor_characterization.py tests/test_recommendation_run_support.py tests/test_task_loop_03_contract.py -q -o addopts= -p no:cacheprovider
  ```

  結果：`38 passed, 2 warnings`。兩個警示是 `decision_module/scoring_engine.py:437` 的既有 pandas dtype `FutureWarning`，非測試失敗。
- R008 回修後的主要舊 Gemini finding 是「空 ML refs 無法區分 not-requested、unknown、unavailable、blocked」。目前 contract 已有獨立 `MLAvailability` status/reason，並以 execution 層驗證 `available` refs 與 `not_requested` 禁止 refs；專用測試也涵蓋相同空 refs 下可區分的狀態。這證明舊 finding 的核心對象已變更，仍須由正式 Gemini 對最新凍結版本判定語意是否完整。
- lazy export 的 bare parent import 後 `module.__dict__` 可見時點差異已在實作報告中明示；直接匯入、star import、`getattr`、`__all__`、class identity 與無 I/O import tests 均列入核對範圍。這是待正式 review 評估的明示相容性限制，不是本次測試失敗。

## 舊審查與待 Gemini 現版審查

目前沒有找到針對回修後九個 SHA 的正式 `REVIEW_STATUS` 結果。`R008_GEMINI_STALE_REVIEW.md` 的 `CHANGES_REQUIRED` 審查了 ML availability 回修前的舊 bytes，其 finding 對該舊版有效，不可套用為現版拒絕或現版通過。Wave 2 Gemini parallel analysis 的 `ANALYSIS_STATUS: COMPLETE` 是實作前風險分析，不是正式 implementation review。權威派送文件 `REFACTOR_DISPATCH/GEMINI_REVIEW_R008.md` 與 `WAVE2_GEMINI_REVIEW_PROMPTS.md` 均要求對當前九個 SHA 執行新的唯讀獨立審查；SOL 回修文件狀態仍為 `INTEGRATION_STATUS: READY_FOR_GEMINI_REVIEW`。

## 相鄰擴大測試的六項失敗

為核對審查封包指定的分類，將 calibration integration 測試加回前置 slice 後重跑，結果為 `44 passed, 6 failed, 2 warnings`。六項失敗均於未修改的 `tests/natural_session_source_fixture.py:130` 建立 fixture 時拋出 `ValueError("evaluation_day must follow every exact-20 session endpoint")`：測試傳入固定 `evaluation_day="2026-06-22"`，但 2026-06-01 capture 的 exact-20 session endpoint 尚未過去。執行未到達這六項測試的 consumer assertions，更未進入 R008 contract 測試路徑。

分類：這是相鄰 ML/calibration integration suite 的既有 fixture 日期限制；不構成 R008 focused suite 失敗或本次 R008 變更引起的回歸。本 suite 不能宣稱通過，也不應因 Wave 2 preflight 偷改其 fixture。重現命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_refactor_characterization.py tests/test_recommendation_run_support.py tests/test_task_loop_03_contract.py tests/test_recommendation_service_calibration_integration.py -q -o addopts= -p no:cacheprovider
```

## 最小剩餘 Gate 項目

1. **取得 R008 現版 Gemini 正式獨立審查。** 審查對象必須是派送封包指定的九個目前 SHA 與實際 diff，特別覆核 ML availability 組合、INV-09／FINAL ML contract、深凍結、terminal state、Decimal／bp、typed refs、schema ownership、lazy export 相容性及無 I/O import。不能以舊 `CHANGES_REQUIRED` 或 parallel analysis 代替。此項沒有可取代正式審查的本機 shell 命令；使用 `REFACTOR_DISPATCH/GEMINI_REVIEW_R008.md` 派送，結果須為單一 `REVIEW_STATUS`。
2. **Gemini 回覆後由 gate owner 完成最終實際核對，才可記錄 Wave 2 checkpoint。** 將九檔的 `Get-FileHash -Algorithm SHA256` 結果與 `R008_SOL_REWORK_REVIEW.md` 逐一比對；若任一 SHA 改變，停止沿用本報告與舊 review，重新凍結、測試及正式 review。若 SHA 未變，可引用本報告的 38-pass focused run；如有程式檔變更，重跑上述 focused 命令並核對實際 diff。只有正式 Gemini 結果、現版 bytes／diff、測試與 Wave 2 checklist 一致後，checkpoint owner 才能判定是否放行後續工作。

PREFLIGHT_STATUS: READY_EXCEPT_GEMINI
