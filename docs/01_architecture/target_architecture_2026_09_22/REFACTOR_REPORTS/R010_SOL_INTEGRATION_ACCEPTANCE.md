# R010 PreparedMLInput：SOL 整合驗收

> **範圍提示（2026-10-11）：** `TASK_STATUS: PASS` 僅接受 R010 的 immutable input contract、application Protocol 與所列 focused integration checks。後續 R026／R029 只關閉 supported caller/profile 的 `TMP-ML-01` 遷移條件；未知／custom artifacts、其他 runtime profiles 與 model promotion 仍不在範圍內。R031 現行 task disposition 見 [31-task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)，目前狀態見 [PROJECT_SNAPSHOT](../../../00_core/PROJECT_SNAPSHOT.md)。

TASK_STATUS: PASS

R010 的純 `PreparedMLInput` leaf contract、application-side ML adapter Protocol 與專用測試已按凍結 SHA 整合到 main；沒有 provider I/O、builder/model 呼叫、source path 搬移、feature schema 更動、artifact 發布或 ML 推論。最終相依的 R008 app contract 是 R009 窄補充後的 SHA `813539DDD5D073EF9407686534EB8874D262F2F9615F50F8A356A356975E1D81`。

| 整合輸出 | SHA-256 |
|---|---|
| `ml_module/prepared_input_contract.py` | `E39EE8ACB37CEDBCABE5276FE85703B2FDBEB98C2DE9702B23184934D6513D03` |
| `app_module/recommendation/ml_adapter.py` | `61ED294BC577A9D68A1887DC73F357C5563F6D7D465F3FC5C97235D1DB300755` |
| `tests/test_prepared_ml_input_contract.py` | `CBF892E0ABFF3583962205E7C3BC41F798D29E8D4087683D15BC3BFC1F142B9A` |
| `R010_IMPLEMENTATION_REPORT.md` | `CE34EAA983CF0938C92D9D4C4533B95B195B9547BA0FBCB2A3FDA037066A418D` |

獨立 Luna 在上述 SHA 上 `REVIEW_STATUS: PASS`，見 `R010_LUNA_INDEPENDENT_REVIEW.md`；初版 production permission 矛盾與 date-only availability 缺口已依反例修正。SOL 核對 result/candidate/date/cutoff、rule/ML 獨立來源、quality/missing/PIT-current-research、feature/transform/model/成本身分均為 typed、immutable refs；ML leaf 無 app/data/provider 反向 import，20 欄歷史 ABI 與 Direct/OOC store 未被 R010 修改。known date-only 不補造 timestamp，date 與 timestamp 各自受截止驗證；同日缺日內證據時後續 projector 必須依明示 policy fail closed。

SOL main 整合套件 **157 passed**，加跑 DTO/data/import **10 passed**；七個變更 source 的 scoped mypy、py_compile、`git diff --check` 通過。`TMP-ML-01` 僅指日後 adapter 內凍結 legacy preparation 分支，由 R026 清除；永久 Protocol/contract 不列為待刪。模型載入、prediction parity 與 live-source barrier 不在 R010 範圍，R026 仍須證明原有計算資料可用且 source/receipt identity 不漂移。INV-03/05/08/14/15 沒有發現違反。main HEAD `5e2d2efcfdc91c5e29810eb823b1c582199a44cc`；未 stage、commit 或 push。
