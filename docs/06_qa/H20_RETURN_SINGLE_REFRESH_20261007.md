# H20 返回來源：避免重複名單核驗

從其他推薦結果分頁按「返回來源清單」時，原 Main 先切回 H20 分頁，Qt currentChanged 自動排入一個完整重讀，再顯式帶原 selection 排入第二個重讀。前一 worker 雖會要求取消，來源大型核驗未必能立即中斷。中央以實際 QTabWidget signal 重現 generation 從2跳到4，預期應只到3；舊碼紅燈收據 `output/qa/h20_return_red_20261007_c.xml`。

返回的程式化分頁切換使用 QSignalBlocker，之後仍呼叫原帶精確 selection／reference 的完整核驗。一般使用者切換 H20 分頁仍自動核驗，不跳過來源、日期、manifest/capture 身份或失敗處理。fixture同步補上現存收藏 signal 的 bound method 與 Qt 所需 weak-reference receiver，前兩次fixture初始化失敗原收據保留，不能當重讀問題的紅燈。

中央路由4項通過，含只排一次、原 selection還原與一般分頁自動核驗；必跑workbench85項通過，全域mypy892檔與compile通過。更新頁validator最終25通過／0失敗／4保護跳過，收據另存 `output/qa/h20_return_update_20261007_a/VALIDATION_REPORT.md`；首次sandbox因合成SQLite strict resolve拒絕21／3／4，失敗report/log保留後原樣在隔離測試環境重驗，不放寬產品檢查。

另驗真 MainWindow 合成保存來源下鑽、返回、來源漂移、取消與 H20 收藏重開6項通過（23.25秒，18個既有警告），收據 `output/qa/h20_return_neighbors_20261007_b.xml`。首次sandbox六項在immutable source pin strict resolve即失敗；另開短路徑合成fixture保留guard重驗，未改正式來源。

這修正一個可重現的重複排程，不宣稱原十檔載入或2382下鑽已變快。c611固定候選與archive不含此修改；原來源真Main baseline仍另外量測，新固定候選與真人速度接受尚未通過。
