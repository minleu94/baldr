> **歷史封存警語（2026-10-10）：**本文保留當時的 Wave 2 分析派送內容；其中 SHA（如有）、scope、角色、指令與狀態僅代表原快照，不得據此重派、重跑或視為目前任務／授權。現況請以 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md) 與 [REFACTOR_MODEL_ASSIGNMENTS](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_MODEL_ASSIGNMENTS.md) 為準；後續 checkpoint 見 [WAVE2_RESULT_ID_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE2_RESULT_ID_CHECKPOINT.md) 與 [WAVE3_CHECKPOINT](../../../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/WAVE3_CHECKPOINT.md)。

# Wave 2 Gemini 並行唯讀分析封包 — R008 契約驗收風險

## ROLE／TASK ID／PURPOSE

你是 Gemini 獨立分析者。Wave 2 僅有 R008，由 Luna Max 實作；你同步進行**唯讀、實作前**的契約驗收風險分析，供 SOL 在 Luna 完成後核對。這不是 R008 實作，也不是可取代正式 Gemini implementation review 的 PASS。請不要修改任何檔案。

## CURRENT SYSTEM CONTEXT

Repository：C:\Projects\PythonProjects\technical_analysis。目前 HEAD 391b057c92037ec7a19cab2bf951d6029d29b020，已有其他工作樹變更；不要 stage、commit、push、revert 或清理。現有 RecommendationDTO 混合 rule、calibration、wire、UI 欄位，RecommendationResultDTO 保存多份列表；RecommendationService.run_recommendation() 回傳 list，並保留可變 last_*。R003 已證實 A/B 交錯與 nested aliases 等現況 gap。R008 僅新增 contract，不接 production；R009 codec、R011 execution、R012 writer、R013 consumer 均尚未解鎖。

## AUTHORITATIVE ARCHITECTURE／RELEVANT INVARIANTS

權威檔案：FINAL_TARGET_ARCHITECTURE.md §5.1–5.3／§6.1、FINAL_DATA_FLOW.md §2／§6、FINAL_ARCHITECTURE_INVARIANTS.md、REFACTOR_EXECUTION_ORDER.md、REFACTOR_TASKS/R008.md（皆位於 docs/01_architecture/target_architecture_2026_09_22/）。不得重新設計架構。

- Decision 擁有 RecommendationItem（stock identity、原規則分數、factor contributions、rank/universe、reasons、可選 confidence）、CandidateAssessment（eligibility、filters、negative evidence、liquidity／missing 判斷）、DecisionBatch（ordered items、assessments、regime／必要 state transition）。Decision 不發 result_id、不寫 DB、不呼叫 ML。
- App 擁有 Request、Context、RecommendationExecution、SaveReceipt。Execution 只儲存 decision: DecisionBatch | None；items 等便利屬性若有，只能唯讀委派。completed 必有 DecisionBatch，即使 items 空；failed/cancelled 可無 decision。validation rejection 在執行前；quality、terminal、ML availability、save outcome 分開。
- 每個 execution 的 stock code 唯一；跨 execution 的 row identity 是 (result_id, stock_code)。result_id 延用 rec_<uuid>，應在 ML receipt 前產生，但 R008 不接 side effect。Runtime、portfolio、replay IDs 用 typed reference，不互換。
- Context 至少容納 as-of date、實際 aware decision_at、來源／data snapshot refs、config/profile/strategy/policy 版本、universe policy、quality、algorithm version；未知歷史值為 unknown／None，不借現在時間補值。
- 深凍結只容許 frozen dataclass、tuple、新建 backing dict 後的 MappingProxyType、str/int/bool/None、Decimal、enum、date、aware datetime。巢狀 mapping key 限 str；不可讓 input 或返回物共享 mutable alias；DataFrame、callback、logger、file/live handle 不進 sealed result。
- schema_version="recommendation-execution.v1"、EXECUTION_SCHEMA_REVISION=1 由 app contract 定義；本 wave 不寫 codec、artifact、repository。既有 score precision／rounding／tie-break 不變，不把原分數量化為 bp；ML ordered schema、dtype、normalization、top-N 與 artifact identity 不動。
- 重點 invariants：INV-01、02、03、05、06、07、08、09、10、11、15、17、18。現況未全部符合，新 contract 不可擴大原有違規。

## COMPLETED DEPENDENCIES

Wave 1 正式 checkpoint REFACTOR_REPORTS/WAVE1_CHECKPOINT.md 為 PASS。R002 完成 recommendation numerical/semantic characterization，R003 完成 execution terminal／A-B／alias characterization，R007 完成無 I/O 的 data leaf contracts；各自 review PASS。R003 現況 gaps 不要求在 R008 修 production。R006 ML ABI baseline 僅界定兼容邊界；已知原有 shadow guard 四條違規未在 Wave 1 修復。

## ALLOWED SCOPE／OUT OF SCOPE／FILES LIKELY INVOLVED

本 Gemini 分析只讀：REFACTOR_TASKS/R008.md、上述權威條款、R002/R003/R007 報告與測試、目前相關 DTO 與 data_module/contracts/market.py；可讀 UI／service source 以辨認舊欄位 owner。請只產出訊息或獨立文字報告交 SOL，不改 repository。Luna 的 R008 允許新增 decision_module/recommendation/contracts.py、app_module/recommendation/contracts.py、相關 tests 與欄位 owner 表；另依 `REFACTOR_REPORTS/R008_SCOPE_ADDENDUM.md` 之受控裁決，可獨占將 `decision_module/__init__.py`、`app_module/__init__.py` 原 public exports 改為窄 lazy exports，以避免 parent eager import 造成非程式 I/O。不得改舊 DTO/service、codec、save、UI、算法或 ML contract internals。

## CURRENT BEHAVIOR TO PRESERVE／COMPATIBILITY

請列出 R008 contract 面對現有 score/precision、stock identity、rank/universe、reasons、screening/negative evidence、regime/context、quality/warnings、result_id 與 ML receipt refs 時應保留的具體欄位／型別風險。數值不得經 float roundtrip；None 與零須分開；PIT/decision clock 不得補造可得時間。R008 不讀寫舊 artifact、SQLite、replay snapshot 或 ML store，不能以 contract tests 宣稱持久化／replay／ML 全路徑相容。歷史未知值保留 unknown／None。SaveReceipt 只定義結果形狀，不實作 writer 或 codec。

## ANALYSIS REQUIREMENTS／REQUIRED TESTS／ACCEPTANCE

1. 根據批准的 contract owner 表與當前 DTO/source，提出可由 SOL 用來審查 Luna diff 的檢查表，不是新的架構方案。特別指出哪些舊 DTO 欄屬 decision、app/ML projection、legacy wire/UI。
2. 指出最容易漏掉的 deep-freeze 反例：外部 backing dict、nested list/dict、dataclass 中的 mutable field、返回值可變 alias、MappingProxyType 原 backing 被改；以及不可封存的型別和 naive datetime。
3. 指出 terminal 組合、duplicate stock code、ID/ref 混用、null／零、Decimal 精度／單位與 schema revision 的拒絕測試；每項說明哪個錯誤設計會使其失敗。
4. 查閱實際 repository 既有型別與 tests，區分已證實 source 事實與推測。若 task spec 與 repository 衝突到無法安全實作，精確列證據和受阻欄位；不自行選新架構。
5. 不需跑昂貴全庫測試；可唯讀跑相關 R002/R003/R007 test 或 import 檢查。不得修改 tests、production 或正式資料。
6. 特別檢查 parent package 的受控 scope：既有 public names、`__all__`、direct/star import、`getattr`、class identity 是否能保留，contract import 是否真的不讀非程式檔／不連 DB，以及 domain→app 方向是否仍正確。既有 `tests/test_update_service_import_contract.py` 原斷言期待七個 service 隨單一 import 全載入；SOL 只允許將其改為 explicit-access 前／後的載入時序 oracle，不能刪除 identity/public export checks。這是 R008 需要的 import 相容性檢查，勿把它誤判為可擴張其他 production scope。

輸出格式：已確認的契約事實、R008 審查檢查表、可能的 CHANGES_REQUIRED 風險與證據、尚待 Luna diff 才能判定、已執行的唯讀檢查。最後一行為 ANALYSIS_STATUS: COMPLETE 或 ANALYSIS_STATUS: ARCHITECTURE_BLOCKER_CANDIDATE。不要給 REVIEW_STATUS: PASS；正式 review 須等 R008 實作報告、diff scope、SHA 和測試凍結後，由 SOL 另交 GEMINI_REVIEW_R008.md。

Do not redesign the architecture.

Do not perform unrelated cleanup.

Do not silently fix unrelated bugs.

Do not begin another R-task.

If repository evidence contradicts this task specification in a way that prevents safe implementation, stop and report ARCHITECTURE_BLOCKER with evidence.
