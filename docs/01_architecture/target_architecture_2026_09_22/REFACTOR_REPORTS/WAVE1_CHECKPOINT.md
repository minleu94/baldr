# Wave 1 正式 checkpoint — characterization 與 leaf contract

## 判定

R002–R007 六項 task 均已 PASS，必要 Gemini 獨立審查與 SOL 實際檔案整合驗收均 PASS。R003、R005 的 Gemini 合併審查原文見 `WAVE1_R003_R005_GEMINI_REVIEW.md`，各自 SOL 判定見 `R003_SOL_INTEGRATION_REVIEW.md`、`R005_SOL_INTEGRATION_REVIEW.md`。R006 的正式獨立審查與 SOL 驗收見 `R006_GEMINI_REVIEW.md`、`R006_SOL_INTEGRATION_REVIEW.md`。本 checkpoint 通過 Wave 1 的明定條件：原實作上的 characterization 可重跑，既有 gap 明示而未先修正，R007 只提供尚未接 production 的 leaf contract。Wave 2 的 R008 因此前置 gate 解鎖；C1–C4 仍未到執行點。

## 驗證矩陣與邊界

| 切片 | SOL 獨立結果 |
|---|---|
| V-REC | 64 passed、2 個既有 pandas dtype 警示 |
| V-EXEC | 41 passed；Gemini 單檔 R003 13 passed |
| V-PERSIST | 33 passed |
| V-REPLAY | 66 passed、24 個既有同日收盤研究假設警示；Gemini 單檔 R005 13 passed |
| R006 ABI baseline | 8 passed；15/15 Direct source bytes/hash/order 與兩種 identity 已核對 |
| R007 leaf | 13 passed；三個 source files 的 mypy 無問題；無 I/O import oracle 通過 |

Changed Python `py_compile` 與 `git diff --check` 通過；diff-check 僅見既有 LF/CRLF 提示。R006 完整 ML focused suite 已知結果是 `73 passed, 1 failed`，唯一失敗為原有 shadow-boundary guard 四條 `app_module → ml_module` imports；獨立重跑仍是同四條、沒有新增。此為具名現況 gap，未改 allowlist、未宣稱完整 ML suite 全綠，也未放行產品或模型權限。

HEAD 為 `391b057c92037ec7a19cab2bf951d6029d29b020`。既有五個 tracked dirty paths、未追蹤 `=` 及各 task 新檔仍保持原狀，沒有 stage、commit、push、清理或正式資料修改。R002–R006 只新增 characterization／QA／報告；唯一 production 變動歸屬 R007 的窄 `data_module/__init__.py` lazy public exports 和新 `data_module/contracts/`，尚未接任何 consumer。此切片無新增 data/domain 逆向依賴；R007 import subprocess、owner/source 審查通過。R003 的 hidden state、stale UI callback、last-good 清除與 alias，R004 的保存失敗窗，R005 的 replay 獨立 policy 均保留為後續具名工作，沒有在本 wave 更動語意或數值。

R001 已勘誤 replay/provider source paths 並重審 PASS；所有臨時機制的建立／退出 owner 仍依 `FINAL_MIGRATION_SEQUENCE.md` 退休帳，Wave 1 沒有建立新的 runtime adapter。R002/R005 的同 mode oracle 與 R006 的 ML ABI 清冊保留歷史相容證據；正式舊 artifact、模型 class path 與端到端 prediction 仍按 R009/R010/R026/R027 驗證，不能由本 checkpoint 推定已驗。資料、result、decision、application 與 ML 的目標 owner 未改，擴充契約尚無 consumer，故未產生第二 schema 或雙引擎。

CHECKPOINT_STATUS: PASS
