# Wave 1 checkpoint 先行驗證（正式審查待回）

## 判定

截至目前，R001、R002、R004、R006、R007 的 SOL/Gemini 驗收記錄為 PASS；R006 正式 Gemini review 與 SOL 整合驗收已補入 `R006_GEMINI_REVIEW.md`、`R006_SOL_INTEGRATION_REVIEW.md`。R003、R005 的 Luna 補件與 SOL focused 驗證已完成，但兩項正式 Gemini 獨立審查尚未返回。本記錄只固定可先行驗證的工作樹狀態，**不是 Wave 1 PASS，也不釋出 Wave 2**。依 `REFACTOR_EXECUTION_ORDER.md`，正式 wave checkpoint 須待每項 task/review PASS 後才封口。

## 工作樹與改動邊界

HEAD 仍為 `391b057c92037ec7a19cab2bf951d6029d29b020`。既有五個 tracked dirty paths、未追蹤的 `=`、R001/R006 QA、contract/test/architecture 目錄均保留，未 stage、commit、push 或清理。Wave 1 characterization 的 R002–R006 僅以新增／指定測試和報告固定現況；唯一 production 變更歸屬 R007：`data_module/__init__.py` 改原四個 public exports 為窄 lazy export，新增 `data_module/contracts/` leaf types，尚未接 consumer。R007 review 中的五檔 SHA 再核對均相符；R002/R004 的凍結 SHA 再核對亦均相符。

`data_module/contracts/` 與 package 入口原始碼搜尋未見 app、decision、ML、Qt import、SQLite 或檔案 reader；R007 contract tests 的 import subprocess oracle 仍通過。新增工作尚未建立 TMP runtime adapter，也未改 replay/provider、保存 writer、ML source list 或正式 artifact。R003 記錄 last-good/stale callback、hidden state 和 alias 現況 gap；R004 記錄舊 writer conflict/failure-window gap；R005 保留 replay 自身 cutoff/fast-filter 政策；R006 將 Direct identity、ML ABI、未知資產按證據等級分帳。這些現況 gap 未在 characterization wave 偷修。

後續 SOL 整合查出 R001 清冊把 replay service/provider 寫在錯誤 module，且混淆 wrapper DTO 與 provider 的 list rows。Luna 在 R001 兩份文件完成勘誤，連同 TMP-REC-02/03/04 的「舊路徑 active、canonical adapter 尚未建立」狀態一併釐清；SOL 逐一核對 source 與建立／移除 task 後，見 `R001_SOL_ERRATUM_REVIEW.md`，R001 維持 PASS。R003/R005/R006 正式審查檔的凍結測試／報告 SHA 均未因此改變。

## SOL 驗證

| 切片 | 命令範圍 | 本次／最近獨立結果 |
|---|---|---|
| R002 / V-REC | task-loop-03、run-support、negative evidence、fundamental filters、ranking、market provider、PIT callers、新 characterization | 本次 `64 passed, 2 warnings`，exit 0；warnings 為既有 pandas dtype FutureWarning |
| R003 / V-EXEC | 新 characterization、execution coordinator、TaskWorker、shutdown、portfolio stale callback | SOL 補件後 `41 passed`，exit 0 |
| R004 / V-PERSIST | DTO roundtrip、save coordinator、personalization save、新 persistence characterization | 本次 `33 passed`，exit 0 |
| R005 / V-REPLAY | 新 characterization、historical evidence/recommendation replay、portfolio backtest、timeline | SOL 補件後 `66 passed, 24 warnings`，exit 0；warnings 為既有 same-day-close 研究假設提示 |
| R006 / ABI small | 新 ML compatibility baseline | 本次 `8 passed`，exit 0 |
| R007 / leaf contract | data market contracts、data_module | 本次 `13 passed`，exit 0 |

R006 的完整 10 檔 focused ML suite 先前實際結果為 `73 passed, 1 failed`，約 477 秒；唯一失敗是既有 shadow-boundary guard 指出的四條 `app_module → ml_module` import。本次另單獨重跑 `test_repository_respects_ml_shadow_dependency_boundary`，仍為 `1 failed`；直接執行 guard 確認仍是相同四條，沒有增加第五條。沒有放寬 allowlist 或宣稱完整 suite PASS。R006 補件後的受影響 focused cases 為 `21 passed, 1 warning`；其餘 production ML 邊界保持不動。另本次 R007 三個 source files 的 mypy 為 no issues；所有 Wave 1 changed Python 執行 `py_compile` exit 0，`git diff --check` exit 0（僅有既有 LF/CRLF warning）。

## 待正式 checkpoint 的條件

1. Gemini 分別唯讀審查重新凍結的 `GEMINI_REVIEW_R003.md`、`GEMINI_REVIEW_R005.md`，每項給出明確 `REVIEW_STATUS`。R006 正式 review 已 PASS；先前並行分析報告只有 `ANALYSIS_STATUS: COMPLETE`，不替代 R003/R005 正式 review。
2. SOL 對每份返回報告重核實際檔案、SHA、範圍、tests、INV-01–18 適用部分；可於原 scope 修正則直接交 Luna 回修，不能安全實作才標 ARCHITECTURE_BLOCKER。
3. 三項正式 review 均 PASS 後重查 Wave 1 checkpoint：characterization 在原實作通過或具名標示現況 gap、R007 leaf boundary 無 reverse dependency、TMP/legacy owner 分帳、數值/PIT/歷史/ML 相容清冊完整。只有 checkpoint 記錄 PASS 才依 DAG 考慮 R008。

CHECKPOINT_STATUS: PENDING_R003_R005_GEMINI_REVIEWS
