# R008 result_id 相容性勘誤：SOL 終版驗收

TASK_STATUS: PASS

R008 原 `_validate_result_id()` 只接受連字號 UUID，與既有 caller-provided opaque ID、服務自產 `rec_{uuid4().hex}` 及 legacy timestamp ID 不相容。現版只要求精確內建 `str` 且非空白，保留原字串；`MLReceiptBinding`、`RecommendationExecution`、`SaveReceipt` 仍用同一 helper，execution 與 receipt 的 ID mismatch 仍明確拒絕。這是 R008「preserve result_id」原 scope 內修正，沒有更動發號服務、R002 golden、計算或 ML ABI。

| 凍結輸入 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `CCF12635EBE037548C7695154D2CD661C1FF8182C6663222F1CC219F982BBC63` |
| `tests/test_recommendation_contracts.py` | `29AA1B7EE2412F772526471A962CA6E238B808978FAEE859F40888D547C094CA` |
| `R008_RESULT_ID_COMPATIBILITY_ERRATUM_REPORT.md` | `7966923E5519AF48AAF41DDA3B1A108366BDEAE0E5723FCF54341C40EEB0065A` |
| R007 dependency market contract | `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A` |
| R008 decision contract | `65BE03D7DC9DC667759D814D10A293333BD4D5FA34E30BC8C4854AB5A4C1C85D` |

獨立 Luna `R008_LUNA_RESULT_ID_INDEPENDENT_REVIEW.md` 在這些 SHA 上為 `REVIEW_STATUS: PASS`，實際 diff 只移除過度嚴格的 UUID 解析與 import，並新增 opaque／hex／timestamp／非空白／型別／mismatch 回歸測試；parent lazy exports、深凍結、terminal 與 ML binding 其他邏輯沒有變。最新 R007 依 `R007_SOL_TZNAME_ACCEPTANCE.md` 及 `WAVE1_R007_TZNAME_CHECKPOINT.md` 已 PASS。

SOL 在新 SHA 執行 R002 characterization、R007/R008 contracts、data/import/execution coordinator 八檔 bundle **95 passed**；獨立 Luna 另跑 R007/R008/import/save 七檔 **88 passed** 與 R002/legacy DTO/隔離 producer/UI **12 passed**。六個指定 source 的 scoped mypy 無錯誤，變更 Python 檔 `py_compile` 通過，`git diff --check` exit 0，index 為空。獨立 reviewer 額外跑的一項較大 ML repository 測試在 exact-20-session fixture 日期 guard 前置失敗，並在舊 R008 SHA 上重現；該項未進入新 contract，不能列作通過，也不屬 Wave 2 的必要 bundle。

Opaque ID 的路徑安全由 R012 新 writer 處理，風險與停止條件已列入 `REFACTOR_RISK_REGISTER.md` 的 RK-26；R008 不把業務身分當檔名。R009/R010 仍需在更新其隔離 worktree 的 R008 dependency 副本並核對 SHA 後續作。先前 `R008_SOL_FINAL_ACCEPTANCE.md` 對舊 SHA 的 PASS 留作歷史，本文件是 result_id 修正後的目前 gate 證據。未 stage、commit、push 或清理其他 dirty 檔。
