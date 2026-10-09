# 唯讀服務刷新取消與回歸驗證（2026-09-30）：歷史導引

原始 QA 已逐位元組移至 [`docs/09_archive/READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md`](../09_archive/READ_ONLY_SERVICE_CANCELLATION_QA_20260930.md)。本頁保留舊路徑，供歷史 Catalog／Index 連結相容使用。

原報告記錄當次 19 項取消／repository contract 驗證通過，以及另一組服務契約 **125 passed、1 failed**。該失敗是當時 `test_workbench_source_service_reads_real_read_only_sources` 的 fixture／既有契約不符；另一份 V5 acceptance 收據另記錄了該測試後來採用的精準 fixture 語意與通過結果。兩份證據各自保留原日期與範圍，本頁不把 9/30 結果改寫成全綠。

目前唯讀取消行為與回歸契約請看 `app_module/sqlite_read_only.py`、`tests/test_read_only_service_cancellation.py`。原文所述 raw pytest logs 位於 ignored `output/qa/ui_shutdown_20260930/`，沒有隨 Archive 提交。
