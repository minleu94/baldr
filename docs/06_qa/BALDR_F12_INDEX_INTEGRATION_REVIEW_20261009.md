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

Root 另以真正合成 SQLite load 注入投影錯誤及投影／close 雙錯誤，兩例通過、exit 0。單一投影錯誤立即關閉來源且不發行索引；close 被故障注入阻止時，錯誤 cause 的 `BaseExceptionGroup` 精確保留原始與清理兩錯誤，來源當時尚未關閉，不能冒稱清理成功；還原故障後 owner 真正關閉，仍沒有索引。收據 `C:/t/root_f12_failure_tjcv_ww7/receipt.json`，可重跑腳本 `output/qa/F12_MONTHLY_REVENUE_QUERY_20261009_A/root_failure_probe.py`。索引 SHA 起訖同為 `09d9bd969a0221cce4af089104c1cefb00926b6d55b3fbf5ceabaa4d662a2bf9`；此檢查補足 batch 投影與清理雙錯誤範圍，不涵蓋全部 finish／query 失敗路徑。

新 reader 整檔 session `24856` 由 owner 回報 terminal 摘要為 6 failed／2 passed、209.02 秒；該次 pytest 輸出與來源起訖 pins 沒有落盤，無法提供 root 可重查的完整 traceback，故保留稽核缺口，不能授予接受。合成 basetemp `C:/t/f12_revenue_reader_20261009_a` 保留，後續修正須使用新封套並保存完整串流日誌與來源 pins。

Root 靜態核對發現新 revenue source-pins 把沿用 MA 的原時區 cutoff 字串與 UTC cutoff 字串直接比較。MA request 由 `metadata.decision_cutoff_label.isoformat()` 建立，而 monthly cutoff 使用 UTC；即使同一 aware 時刻，兩種時區字串也可能不相同。已要求用保留的真合成 fixture 記錄實際值重現，僅在新 revenue 契約明示正規化，先驗 aware instant 一致，保留既有 MA request／identity；不得為了通過而把真正不同的 cutoff 改成相同。

修正後 Root 獨立檢查 production cutoff helper：`2026-10-07T16:00:00+08:00` 與 `2026-10-07T08:00:00+00:00` 解析為同一時刻，相差一分鐘則不同；naive、無效字串、bool 及不符合 canonical ISO 的空格形式均拒絕。收據 `root_cutoff_helper_1791509868186656100.json`，共享 reader SHA 起訖為 `1f50cb364ab6c4aa0e913d6a10ec8e3c1820106e7e8dcc46f4f9c100efd09eb6`。只涵蓋純 helper 與本輪靜態修正，沒有 SQLite／完整 source join；保留合成母體重現與整檔驗收仍待。

後續 attempt03 已取得完整 reader 整合結果：8 passed／218.14 秒、exit 0。Root 直接讀回 `output/qa/F12_REVENUE_READER_REPAIR_20261008_A/attempt03/pytest.log`、`terminal.json` 及實際 cutoff 收據，並重新雜湊來源與測試，分別符合 `fc9c3d089c703f2bc815d0ce02310916de49aa1ce35cdfa8336ca7e630dc8045`、`da303aeb5eaaed76b9f983c7af3098c368681fc1f290052c121af86e3c012171`。保留 attempt02 的 6 passed／2 failed 結果，未覆寫舊封套。

Root 同時核對測試實際斷言：三個啟用條件組的 AND／OR 各涵蓋 include、exclude、only；25% 營收門檻另驗明確 no-match 對 AND／OR 的影響。排除列可依 row scope 瀏覽，但不被 unknown policy 納入，且頁面身分與結果封印相符；真正不完整 store 不能冒充合格完整 bundle。此證據限於該合成母體與條件分布，不推論全市場或 UI 接線完成。

合成收據 `C:/t/f12_revenue_reader_repair_attempt03/test_active_or_query_is_global0/f12_cutoff_normalization_receipt.json` 的 DB、capture 起訖 pins 及頁面前後 source pins 逐項相同。索引整份核驗在 execute 為兩次，第一頁讀完累計三次；未逐列重掃。來源仍未具 PIT 資格。接續範圍為產品 UI、收藏序列化與跨程序 exact reopen；真人接受尚未開放。
