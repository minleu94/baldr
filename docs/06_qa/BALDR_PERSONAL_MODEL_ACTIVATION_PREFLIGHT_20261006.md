# 個人真模型啟用前讀回入口

> **歷史 preflight（2026-10-06）：** 本文件固定在啟用前，記錄當時尚未選定 root／設定；後續接線與 revision 1 效果見[個人模型中央接線 QA](BALDR_PERSONAL_MODEL_ACTIVATION_INTEGRATION_20261006.md)。此 preflight 不代表目前未啟用或目前待辦；現況看 [Snapshot](../00_core/PROJECT_SNAPSHOT.md) 與 [QA 導覽](README.md)。

固定接手基準 `36dc1baf740007834f385ff0f654c7fe268a36f3`。

使用者要求既有真模型以正確原含義實際參與個人每日研究。新增 H20 gross 模型不是所有既有模型啟用的前置門檻。既有 calibration 可保其 H20 上漲機率／校準 target，工程來源相容通過後接個人 policy；準確度自然觀測，不能假造歷史 PIT。

中央準備入口：`scripts/qa_prepare_personal_model_activation.py`。四個必填絕對路徑為 `--data-root`、`--learning-output-root`、`--candidate-root`、`--receipt-path`；receipt parent 必須已存在，且在三個來源樹之外。以原 `inspect_personal_calibration_candidate` 執行不反序列化讀回，原容量／來源契約不改。receipt 新建不可覆寫；exit 0 只表示 inspector 產生 candidate pins，不表示載入／啟用／統計合格；exit 1 表示候選不可用，查看原 reason_code。

實測兩個既存 learning roots 共三候選，bounded inventory complete、無 truncation，全部 `legacy_unproven/training_lineage_missing`。原 challenger 兩候選 full inspector 同樣拒絕；這是 lineage 工程缺件，不是準確度等待。應沿其原 target 由目前 runner 新產生有完整 lineage 的候選，不回填舊 artifact。未 deserialize、fit、打開來源 DB、改 Task、改 policy 或清理來源。

CLI 實測原 FA_Data_Shadow challenger 回 exit 1 並保存同原 reason；重複同命令 FileExistsError，原 receipt 不覆寫。完整 metadata／inventory／inspector／CLI raw 收據位於 `output/qa/baldr_real_model_intake_20261006/`。原 inspector preflight JSON SHA256：`d2c868fd7b226db5270f4daf1115c8b6cb21fcb30c33cda60baada6e74b8184f`。

這是中央可逆準備工具，不是 Task 或模型啟用的替代。後續沿原個人 policy/service 接線，A03 同時接每日保存；A02 新 gross output additive。中央 config/main/Task/Manual ownership 不變，尚待 exact roots／可核新 candidate／來源 binding 定版。
