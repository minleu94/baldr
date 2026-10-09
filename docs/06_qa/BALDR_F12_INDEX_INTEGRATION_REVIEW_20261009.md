# F12 月營收索引與查詢接線審查（進行中）

來源層 45 項接受與 `fa46281a` 保持獨立，見 `BALDR_F12_MONTHLY_REVENUE_SOURCE_REVIEW_20261009.md`。本輪新增索引與複合查詢正在實作，尚未授予完整母體、UI、跨程序原版重開或真人接受。

Root native 執行 `tests/test_daily_market_monthly_revenue_yoy_index_v1.py`，exit 0、5 passed／0.80 秒，索引／測試前後 SHA 一致。收據 `output/qa/F12_MONTHLY_REVENUE_QUERY_20261009_A/root_index_review_1791507517944226700.json`。範圍包括實際 source finished ledger 才發行、零比較基期與合格投影分開、不完整／竄改清冊拒絕、seal 不可由 replace 重用，以及取消不發布部分索引。

另以新合成 SQLite 重現 batch 取消、非 bool 回呼及完整 batch 後 finish 取消三條路徑；三例均立即關閉 source reader、沒有發行 index，最後 owner cleanup 完成。收據 `output/qa/root_f12_cancel_probe_bzh0slc2/receipt.json`；來源 SHA 前後為 `86463222fc2be64a510a325ccf6a934ff9a430fd03150defe3350b0e6656cb73`。此證據不涵蓋清理本身失敗時的雙錯誤保留，該案例仍待補。

審查已要求 full-N join 起始／發布前才核整份索引，逐列沿已核 entries merge，不能 N 次呼叫會重算全 cohort hash 的 `entry_for()`。分頁只做有界精確讀回；排除／pending 母體不得由 P01 篩後集合推定。單一 aware cutoff 與 source／method pins 必須一致；來源仍為 current-observed-only、availability unknown、PIT false。

初輪新查詢 DTO mypy 有 17 項錯誤，主要為 Decimal exponent narrowing 及封印 anchor 欄位缺型別註記，已交 owner 修正。索引本身該輪沒有型別錯誤。完整三組 AND／OR、未知政策、全域排序／分頁、source 變動、清理雙錯誤及原 MA／F17 回歸需另取得固定版本結果，不由上述五項推論。

後續 root 已獨立執行索引、營收查詢 DTO 與共享 reader 三個來源檔的 targeted mypy，exit 0；初輪型別錯誤已修復。此結果只證明該輪型別檢查，不取代執行期查詢驗收。

原 reader／MA 回歸的 root session `23017` 已終止：外層 harness 的 120 秒期限觸發 `subprocess.TimeoutExpired`，沒有取得 pytest 完成結果，因此通過與產品失敗均未證明。逾時紀錄為 `output/qa/F12_MONTHLY_REVENUE_QUERY_20261009_A/root_old_query_timeout_1791508549780502700.json`；該初次程序觀察誤將觀察用 PowerShell 命令文字列入匹配，不能用作殘留判定。後續以 Python 執行檔及 `-m pytest` 的實際參數精確匹配，未見本次舊 reader 測試程序殘留，收據為 `root_old_query_terminal_cleanup_1791508566274104800.json`。下次回歸須保存串流輸出並給予真實 257 檔 fixture 適當有界期限。

目前新 reader 測試來源涵蓋 258 declared／257 processed／1 excluded 的母體、兩組 OR、排除 hard gate、跨分段分頁與索引整份驗證次數。該 fixture 沒有 pending，且 MA 為 unknown、營收只有一筆合格觀測；尚不能證明三組 AND／OR、完整未知政策與 pending 行為，已要求補齊實際來源案例。

後續 root native 回歸 session `71554` 已完成：原 F17 reader 與 MA query DTO 共 45 passed／497.79 秒、exit 0，600 秒有界期限未觸發。共享 reader SHA 起訖皆為 `3a8274201402709b2d9515d6da552ee4502f3a0b3be0e3c0b14c0473bc21ae39`。收據與串流日誌為 `root_old_query_regression_1791508671465035500.json`／`.log`；此結果證明既有契約回歸，不能取代新增營收三組條件與完整來源整合驗收。
