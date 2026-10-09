# UI Layout Audit（2026-09-29）— 歷史文件導引

原始 QA 收據已移至 [`docs/09_archive/UI_LAYOUT_AUDIT_20260929.md`](../09_archive/UI_LAYOUT_AUDIT_20260929.md)，保留當日測量與完整限制。

該收據記錄六格 offscreen MainWindow viewport 矩陣通過及合成 UI 覆蓋；此結果不證明 Windows 原生視窗行為。先前 per-view QObject controller 曾出現 native access violation；後續 app-owned dispatcher focused tests 與 offscreen 矩陣未重現，但根因與永久修復尚未證實。official data smoke 與 Native input 未執行，raw QA artifacts 仍是未封存的 ignored 本機輸出。

目前 UI 功能與呈現說明見 [`UI_FEATURES_DOCUMENTATION.md`](../02_features/UI_FEATURES_DOCUMENTATION.md)；QA 導覽見 [`PRODUCT_UX_QA_INDEX.md`](PRODUCT_UX_QA_INDEX.md)。本導引只維持舊路徑可達，不把該次有限 QA 升級為原生視窗驗收或缺陷結案。
