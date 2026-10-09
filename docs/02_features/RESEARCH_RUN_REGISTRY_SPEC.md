# Research Run Registry 設計規格（歷史導引）

> 本檔案保留舊路徑相容；原文是 2026-06-14 的 Month 1 設計提案，不是現行 schema 或 API 契約。

原始設計規格已逐位元封存：[查看 2026-06-14 歷史原文](../09_archive/RESEARCH_RUN_REGISTRY_SPEC_2026_06_14_HISTORY.md)。該提案包含 `delete_run()` 與獨立 REAL 績效欄位；現行 service 使用受控 `archive_run()`，repository schema 以程式實作為準，不能用歷史提案推定目前行為。

目前功能說明請看 [Backtest Lab 功能文件](BACKTEST_LAB_FEATURES.md)、[系統架構中的 Research Run Registry](../01_architecture/system_architecture.md) 與 [Application Manual](../07_guides/APPLICATION_MANUAL.md)；現行實作位於 [`ResearchRunService`](../../app_module/research_run_service.py) 和 [`ResearchRunRepository`](../../app_module/research_run_repository.py)。歷史搬移與原文 SHA-256 見 [Coverage History Entry 137](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-137)。