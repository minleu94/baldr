# Wave 1：R007 依賴勘誤 checkpoint

CHECKPOINT_STATUS: PASS

原 `WAVE1_CHECKPOINT.md` 對當時 R001–R007 快照的 PASS 保留為歷史。R008 獨立審查後揭露 R007 leaf contract 的 caller-owned datetime/tzinfo 別名；R007 已在原 scope 修補，並通過 [SOL 驗收](R007_SOL_ERRATUM_ACCEPTANCE.md)及 [獨立 Luna review](R007_LUNA_ERRATUM_INDEPENDENT_REVIEW.md)。其餘 Wave 1 task bytes/結論未在此勘誤更改。R007 leaf/import 20 passed，無 I/O 或逆向依賴；深凍結、availability、None/zero 及 source identity 測試涵蓋新增反例。

Wave 1 的 R007 依賴 gate 在新 SHA 上恢復 PASS。Wave 2 仍須 R008 終版、獨立 review 與自身 checkpoint 通過，才能釋出 Wave 3。本 checkpoint 不授權任何 ML/資料重建、writer 或 consumer migration。
