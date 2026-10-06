# main 文檔索引

main 是完整可調度的本機使用版，dev 保留開發規劃、完整歷史與新增內部 QA。沒有遠端發布；本索引不把工程驗證等同自然資格。

- [Windows 可攜與首次設定](../07_guides/PORTABLE_WINDOWS.md)
- [完整操作手冊](../07_guides/APPLICATION_MANUAL.md)、[安裝](../07_guides/INSTALL_GUIDE.md)、[快速開始](../07_guides/QUICK_START.md)
- [目前狀態](PROJECT_SNAPSHOT.md)
- [調度入口與契約](../../scripts/scheduled/README.md)、[Morning check](../07_guides/EVIDENCE_SCHEDULED_MORNING_CHECK.md)、[Evidence rehearsal](../07_guides/EVIDENCE_REHEARSAL_RUNBOOK.md)
- [模型 shadow inference 維運](../07_guides/ML_SHADOW_INFERENCE_OPERATIONS_RUNBOOK.md)、[Historical ML](../07_guides/HISTORICAL_ML_SHADOW_RUNBOOK.md)
- [目前架構](../01_architecture/system_architecture.md)、[目標架構](../01_architecture/target_system_architecture.md)
- [Roadmap Hub](DEVELOPMENT_ROADMAP.md)、[產品方向](PRODUCT_ROADMAP_POST_REFACTOR.md)、[6M 工程](ROADMAP_6M_ENGINEERING.md)、[長期成熟度](VERSION_ROADMAP_V2_1_TO_V4_0.md)

操作流程／參數／結果判讀／安全與排錯以 Manual 和可攜指南為準。原 scheduler preflight／dry-run／execute gate 保留；可攜程式不自動註冊或改原 Task。模型使用原可信 policy／manifest／source／cutoff，沒有訓練或交易捷徑。
