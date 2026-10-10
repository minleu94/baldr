> **歷史 Wave checkpoint**：本文只記錄當時的依賴與有限釋出狀態，不提供目前的 release 或派工授權。後續 C1／Wave 6 裁決見 [C1 checkpoint](C1_CHECKPOINT.md) 與 [Wave 6 最終 gate 報告](WAVE6_FINAL_GATE_REPORT.md)；目前狀態看 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)。

# Wave 3 codec／ML boundary checkpoint

CHECKPOINT_STATUS: PASS

R009 與 R010 實作、各自獨立 Luna 複核及 SOL 整合驗收均為 PASS；R008 contract 唯一一行 schema-range 補充亦依 `R008_SCHEMA_RANGE_DEPENDENCY_RECHECK.md` 在新 SHA 上重驗 PASS。依 `REFACTOR_EXECUTION_ORDER.md`，本 checkpoint 只檢查 Wave 3 的 codec 全欄位 roundtrip、舊 artifact read view、ML leaf 無 app import 及未發布 writer/consumer。

main HEAD `5e2d2efcfdc91c5e29810eb823b1c582199a44cc` 上，SOL 合併執行 R002/R003/R004/R005/R006/R007/R008/R009/R010 與 execution coordinator 相關 11 檔 **157 passed**；另跑 DTO/data/import 三檔 **10 passed**。七個變更 source 的 scoped mypy、變更 Python 的 py_compile、`git diff --check` 通過，Git index 空。兩個 worktree 的凍結相依與 main 整合檔 SHA、DTO Git blob 已逐項核對；工作樹既有其他 dirty 檔未清理、未 stage、commit 或 push。

架構核對：新格式的唯一欄位 schema 仍是 typed contracts；可變 metadata 不進 immutable artifact；R009 未接 repository，R010 未接 provider/model，沒有引入 reverse dependency 或第二個 evaluator。舊中英文 artifact/DTO bytes 的讀取驗證保留，Decimal 與既有 ML ordered schema/store 未改。`TMP-REC-05` 由 R029 移除舊 façade，歷史 decoder 保留；`TMP-ML-01` 由 R026 移除凍結 legacy preparation 分支。R011 接下來仍須完成同一計算 body 的 invocation capture 與 legacy list parity；不能把本 checkpoint 視為 C1，C1 僅在 R012 後執行。

Wave 4 **只釋出 R011**，中央 `recommendation_service.py` 由單一 worker 排他持有；R012 與 consumer migration 仍 blocked。
