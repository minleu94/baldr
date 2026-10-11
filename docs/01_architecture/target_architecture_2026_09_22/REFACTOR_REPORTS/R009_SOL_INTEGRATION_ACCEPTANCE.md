> **時點／範圍導覽（2026-10-11）**：`TASK_STATUS: PASS` 是本文所列 R009 frozen source、legacy decoder 與 DTO 薄委派整合 gate 的 bounded acceptance。R031 current disposition 將 R009 列為 `ACCEPTED_FOR_KNOWN_CODEC_BYTES`；未知 class paths 依 R006 retention 另行處理。本文不代表任意 pickle ABI 或所有未知 artifact 均可解碼，詳見 [R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。

# R009 schema-driven codec：SOL 整合驗收

TASK_STATUS: PASS

R009 已把 schema-driven、typed recursive execution codec、legacy bytes decoder 與 `RecommendationDTO` 薄委派整合到 main。最終實作依 `R009_SCHEMA_RANGE_SCOPE_ADDENDUM.md`，僅在 R008 app contract 新增明示支援 revision tuple。主工作樹 DTO 僅套用原方法的窄 patch；其 Git blob `109ab7e6c041662244d2aaa11d035a085b3217a8` 與 R009 worktree 相同，未以換行格式不同的整檔覆寫。

| 整合輸出 | SHA-256 |
|---|---|
| `app_module/recommendation/contracts.py` | `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81` |
| `app_module/recommendation/codec.py` | `A1BC97DE557C58FCAA039D06DAE909123A3E405B5E2DD7776B94F9A80ED653BE` |
| `tests/test_recommendation_execution_codec.py` | `3E6BDE7EF1594E55F2F4FC5A5F0BB9AF781BBC645EF6C666DAB686C217D4E9BF` |
| `R009_IMPLEMENTATION_REPORT.md` | `F8C1F2A1C11F0B7DFC5CAA00E8EEBDBF38BA68A01C466DEBC9A0A55AF84D087F` |

獨立 Luna 在這些 SHA 上 `REVIEW_STATUS: PASS`，見 `R009_LUNA_INDEPENDENT_REVIEW.md`；初版 additive revision 與 schema ownership 的 `CHANGES_REQUIRED` 證據保留於該報告。SOL 逐檔核對所有權：未碰 repository、SQL、save caller、ML producer、UI 或其他 task 的 source。舊中英文 DTO key、Decimal close price、calibration/negative evidence 與原始 bytes 先驗 SHA 後解析均有測試；新 artifact bytes 只含固定 header、typed payload 與 payload hash，可變 metadata 由後續 R012 另存。未知 schema/revision/type 拒絕；支援舊 revision 的 optional default，不引入第二份 scalar 欄位清單。

SOL main 整合套件 **157 passed**，加跑 DTO/data/import **10 passed**；七個變更 source 的 scoped mypy、py_compile、`git diff --check` 通過。`TMP-REC-05` 舊 DTO façade 由 R029 退場，歷史 decoder 為永久相容責任。R009 未發布 writer 或新 consumer；INV-01/08/11/12/17 及 ML projection refs 沒有發現違反。main HEAD `5e2d2efcfdc91c5e29810eb823b1c582199a44cc`；未 stage、commit 或 push。
