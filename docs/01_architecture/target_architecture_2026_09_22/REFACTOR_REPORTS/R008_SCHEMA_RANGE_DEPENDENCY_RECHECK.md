> **時點／狀態導覽（2026-10-11）**：本文的 `TASK_STATUS`、Wave 及相依重驗結論是當時的歷史結果，不等同 R008 整體現行 disposition。[R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 將 R008 列為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`；[R031 final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 未列 R008 專項。此處僅導覽 task-level 狀態，不重裁本文特定重驗範圍或限制；原始判讀與限制保留。

# R008 schema revision 宣告窄變更：SOL 相依重驗

TASK_STATUS: PASS

R008 原 result_id 勘誤與 Wave 2 checkpoint 已 PASS。R009 獨立審查依 `FINAL_TARGET_ARCHITECTURE.md` §6.1 發現支援 revision 範圍須由 app contract 擁有；SOL 依 `R009_SCHEMA_RANGE_SCOPE_ADDENDUM.md` 准許 R009 只在 `app_module/recommendation/contracts.py` 增加 `SUPPORTED_EXECUTION_SCHEMA_REVISIONS: tuple[int, ...] = (1,)`。主工作樹原檔 SHA-256 為 `CCF12635EBE037548C7695154D2CD661C1FF8182C6663222F1CC219F982BBC63`；整合後為 `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81`。逐行 diff 只有這一行；既有 schema version/revision、欄位、validator、深凍結、result_id 及 parent export 未變。

獨立 Luna 的 R009 最終複核在新 SHA 上重跑 R008/R007/R004/R009 組合 **101 passed**，另加 DTO roundtrip 為 **104 passed**，並確認這一行未改 R008 行為。SOL 將 R009/R010 產物整合到 main HEAD `5e2d2efcfdc91c5e29810eb823b1c582199a44cc` 後，重跑涵蓋 R002–R010 的 11 檔聚焦套件 **157 passed**；另跑 DTO/data/import 三檔 **10 passed**。七個變更 source 的 scoped mypy、變更 Python py_compile 與 `git diff --check` 通過；index 為空。這是新 R008 contract SHA 的窄相依重驗，不更動先前 R008 其他驗收範圍。

Wave 2 在新 SHA 上恢復 `PASS`。R009/R010 及 Wave 3 仍須分別通過整合 gate；本重驗不提前釋出後續 wave。
