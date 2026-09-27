# R006 unknown artifact 與保留策略（2026-09-27 addendum）

## 原任務邊界

R006 的原任務明定「反序列化未知來源」為 OUT OF SCOPE；其 acceptance 要求清冊列出 schema/order/dtype/scale/mask/row refs/class paths/source IDs、所有讀取不改 bytes，並清楚標示 unknown。Implementation objective 另要求每個 unknown 資產有保留策略。這些條文要求盤點及保留，不要求為未知正式 binary 執行 pickle/joblib、預測或重建。

## 目前唯讀證據

- 兩個 sidecarless legacy pickle 以 symbolic opcode stack/memo parser 檢視，未 import globals、未執行 `REDUCE`／`BUILD`／`NEWOBJ`，未 load 或 predict。每個檔案 81,620 opcodes、10 個 external global references（sklearn/numpy/xgboost/builtins）、`unresolved=[]`；pre/post SHA 相同，receipt明示 `load_prediction_verified=false`。
- OOC selected run inventory 只覆蓋 10 個精確 selected paths、合計 64,912 bytes，與保存的 SHA 相同；沒有做 83k recursive inventory。單一 64,912-byte `head-00.joblib` 以 8 MiB 上限 zlib 解壓到 190,742 bytes、EOF true，opcode prefix 在 269 個 opcodes／offset 1294 的 ndarray raw block 停止。class-path hints 均 unresolved；狀態 `PARTIAL`，`prediction_verified=false`。
- 兩個 sidecarless legacy model 的 class paths、selected OOC head 的完整 class path、未知 bytes 的可載入性與 runtime prediction compatibility仍為 `unknown`。現行保留策略是不載入／不改動原檔，保留原始 readers 與有設計依據的 aliases；沒有將 metadata 宣稱成可執行證據，也沒有更改 active pointer、checkpoint、allowlist或Direct15。

收據包括 r006_static_symbolic_references.json、r006_ooc_baseline_hash_static_probe.json、r006_ooc_bounded_zlib_opcode_prefix.json。這些為唯讀 inventory/status 證據，不是任意正式 artifact 的 load/predict regression。

## 判定與限制

按 R006 原文，未知 class-path compatibility不會自動構成 inventory/retention task未完成：unknown項已明確標示，selected paths/bytes有保存證據，且未知來源反序列化明確排除於 scope。故 R006 scoped inventory/retention 可按原 acceptance 判定；R006 的歷史 73P/1F 及後續 21P focused evidence各自保留，不合併或改寫成另一輪全套 PASS。

RK-19 仍表示正式未知 binary/class path 的相容性是未解風險；它不表示 R006 必須越界載入這些 assets，也不表示 unknown artifact 已受支援。若未來工作要求讀取或移除某個特定 class path，須先取得該資產的精確身份與獨立核准的受控相容計畫；不得用此 addendum 推導任意 loader acceptance、預測正確性或全量資產盤點完成。

## 來源

- [R006 任務規格](../01_architecture/target_architecture_2026_09_22/REFACTOR_TASKS/R006.md)
- [R006 ABI inventory](REFACTOR_ML_ABI_BASELINE_R006_20260922.md)
- [R006 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R006_IMPLEMENTATION_REPORT.md)
- ignored receipts：`output/qa/refactor_completion_20260927/r006_static_symbolic_references.json`、`r006_ooc_baseline_hash_static_probe.json`、`r006_ooc_bounded_zlib_opcode_prefix.json`
