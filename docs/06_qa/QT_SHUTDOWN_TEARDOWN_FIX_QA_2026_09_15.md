# Qt MainWindow shutdown teardown 修正 QA（2026-09-15）

原始 bounded 修復與驗收收據已完整移至[歸檔原文](../09_archive/QT_SHUTDOWN_TEARDOWN_FIX_QA_2026_09_15.md)。本紀錄只覆蓋 production MainWindow 在 `QApplication.exec()` 返回後的 Qt teardown hang；它沒有證明舊 memory-write popup 的根因相同，也沒有驗收 Native crash 或 SQLite inspector 的獨立 shutdown 路徑。

- 未解的唯讀 Native crash 調查仍在 [QT_NATIVE_CRASH_READONLY_FOLLOWUP](QT_NATIVE_CRASH_READONLY_FOLLOWUP_2026_09_15.md)。
- SQLite inspector 的 worker 等待問題另見 [QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE](QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md)；本收據沒有覆蓋該路徑。
- 歷史原文、原始 bytes/hash 與歸檔理由見 [Coverage History Entry 100](../09_archive/DOC_COVERAGE_HISTORY_2026.md#coverage-entry-100)。
