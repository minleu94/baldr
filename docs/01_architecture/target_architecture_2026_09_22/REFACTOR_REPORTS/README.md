# 重構實作報告

每個 R-task 的 implementer 必須新增 `Rxxx_IMPLEMENTATION_REPORT.md`。報告至少包含：

1. task ID、implementer model、起始／結束 HEAD 與 dirty baseline；
2. 已讀 authority 與完成 dependencies；
3. changed files、逐項實作內容及明確未修改範圍；
4. behavior／numeric／persistence／replay／ML compatibility 證據；
5. 執行 tests、完整 commands、結果及未執行原因；
6. acceptance criteria 逐項 verdict；
7. temporary component 建立／移除狀態；
8. remaining risks、known baseline、rollback point；
9. `IMPLEMENTATION_STATUS: READY_FOR_REVIEW | CHANGES_REQUIRED | ARCHITECTURE_BLOCKER`。

Worker 的 `READY_FOR_REVIEW` 只是交給 SOL／指定 reviewer 檢查，不等於 task PASS 或 wave complete。
