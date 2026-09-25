# R003 SOL 審查

## 判定

`tests/test_recommendation_execution_state_characterization.py` 的 6 個新案例與既有 execution coordinator／TaskWorker suite 在 SOL 重跑時共 26 passed。實作沒有修改 production。但新案例尚不足以達到 R003 的 acceptance criteria，實作報告所稱「所有終端狀態」、「stale callback」及「worker close」都沒有對應的可判定 oracle。

## 必須修正的項目

1. `tests/test_recommendation_execution_state_characterization.py:109` 的 A/B 測試使用兩個分離的 `FakeRecommendationService`，只證明兩個 `TaskWorker.finished` signal 都送達；沒有延後讀 A 的 `last_*`、沒有呼叫 `RecommendationView` 的 request correlation callback，也沒有驗 stale callback 不覆寫 last-good display。請用 deterministic event/barrier 加實際 UI callback seam 建立這些 assertions；不得以 sleep 製造順序，也不得為通過測試修改 production。
2. 同檔 `:109` 名稱聲稱 worker close，但沒有 `deleteLater`、native thread completion 或受管 worker registry 的 assertion。請驗證目前 close/lifecycle 可觀察行為，必要時把現況差距列為 gap。
3. `:44` 的 completed-empty 與 `:80` 的取消都以 `[]` 表示。現有 Fake service 的 call count/return value 不能區分 terminal outcome；請至少以 worker finished/error/cancelled signal、service 呼叫事件與 UI 狀態分離 completed-empty、failed、cancelled、validation rejection。`validation_error()` 單獨回字串不能代表 worker rejection event。
4. `:144` 只測 request input 的一個 nested alias；沒有回傳物被原輸入或 caller 再次修改後的可見性，也沒有 A/B 同一服務 hidden-state 汙染測試。請在兩側加明確 mutation oracle，將現況違反 INV-08 的證據和未來要求分開。
5. 缺 progress callback shape、ML receipt side-effect 在 cancel/failure 後的可見順序、last-good result 與完整事件矩陣。這些都在原 R003 spec／Gemini packet 的 required behavior；可以用 fake receipt/progress spy，不可載入正式模型或寫 repository。
6. `R003_IMPLEMENTATION_REPORT.md` 只記 6 個新測試；須補起始／結束 HEAD 與 dirty baseline、每個 terminal event sequence、現況 gap、實際 changed files、既有 `test_recommendation_execution_coordinator.py` 與相關 Qt worker/stale focused tests 的命令與結果、`py_compile` 和 `git diff --check`。目前 `UNRESOLVED RISKS: 無` 與上述缺口不符。

允許變更仍限 R003 專用新測試與 R003 實作報告；若必須動 production 或另一 R-task 檔案，停止並附證據回報。完成後重跑 V-EXEC，交 SOL 查實際 diff。Wave 2 仍 blocked。

REVIEW_STATUS: CHANGES_REQUIRED
