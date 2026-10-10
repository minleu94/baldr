# 重構任務規格索引

> 本目錄把六份 FINAL 架構轉成可交付 coding agent 的工作契約。這些文件不修改架構、不表示任務已開始，也不授權 production data、模型、scheduler、stage、commit 或 push。

執行前先讀 [完整 DAG](../REFACTOR_IMPLEMENTATION_DAG.md)、[模型分工](../REFACTOR_MODEL_ASSIGNMENTS.md)、[波次與檔案 owner](../REFACTOR_EXECUTION_ORDER.md)、[驗證矩陣](../REFACTOR_VALIDATION_MATRIX.md) 與 [風險登錄](../REFACTOR_RISK_REGISTER.md)。每個 agent 只能執行被明確指派的一個 task，並在 [REFACTOR_REPORTS](../REFACTOR_REPORTS/README.md) 依 post-task report 要求回報。

| Wave | Tasks |
|---|---|
| 0 | [R001](R001.md) |
| 1 | [R002](R002.md)、[R003](R003.md)、[R004](R004.md)、[R005](R005.md)、[R006](R006.md)、[R007](R007.md) |
| 2 | [R008](R008.md) |
| 3 | [R009](R009.md)、[R010](R010.md) |
| 4 | [R011](R011.md) |
| 5 | [R012](R012.md) |
| 6 | [R013](R013.md)、[R014](R014.md)、[R016](R016.md)、[R017](R017.md) |
| 7 | [R015](R015.md)、[R021](R021.md)、[R023](R023.md)、[R025](R025.md)、[R027](R027.md) |
| 8 | [R022](R022.md) |
| 9 | [R018](R018.md)、[R024](R024.md)、[R028](R028.md)（原始條件為 R027 strict PASS；R028 實際依使用者接受的 revision B 與 root dated decision 啟動及接受，原 strict verdict 仍保留，見 [R027 revision](../../../06_qa/R027_LOGICAL_TIME_ACCEPTANCE_REVISION_20260927.md) 與 [R028 report](../REFACTOR_REPORTS/R028_IMPLEMENTATION_REPORT.md)） |
| 10 | [R019](R019.md) |
| 11 | [R020](R020.md)、[R026](R026.md) |
| 12 | [R029](R029.md) |
| 13 | [R030](R030.md) |
| 14 | [R031](R031.md) |

實際可並行條件與高風險檔案的 exclusive owner 以 [REFACTOR_EXECUTION_ORDER](../REFACTOR_EXECUTION_ORDER.md) 為準；表中的同一 Wave 不代表必須同時啟動。
