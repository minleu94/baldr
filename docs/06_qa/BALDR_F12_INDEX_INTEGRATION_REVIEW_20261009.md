# F12 月營收索引與查詢接線審查（進行中）

來源層 45 項接受與 `fa46281a` 保持獨立，見 `BALDR_F12_MONTHLY_REVENUE_SOURCE_REVIEW_20261009.md`。本輪新增索引與複合查詢正在實作，尚未授予完整母體、UI、跨程序原版重開或真人接受。

Root native 執行 `tests/test_daily_market_monthly_revenue_yoy_index_v1.py`，exit 0、5 passed／0.80 秒，索引／測試前後 SHA 一致。收據 `output/qa/F12_MONTHLY_REVENUE_QUERY_20261009_A/root_index_review_1791507517944226700.json`。範圍包括實際 source finished ledger 才發行、零比較基期與合格投影分開、不完整／竄改清冊拒絕、seal 不可由 replace 重用，以及取消不發布部分索引。

另以新合成 SQLite 重現 batch 取消、非 bool 回呼及完整 batch 後 finish 取消三條路徑；三例均立即關閉 source reader、沒有發行 index，最後 owner cleanup 完成。收據 `output/qa/root_f12_cancel_probe_bzh0slc2/receipt.json`；來源 SHA 前後為 `86463222fc2be64a510a325ccf6a934ff9a430fd03150defe3350b0e6656cb73`。此證據不涵蓋清理本身失敗時的雙錯誤保留，該案例仍待補。

審查已要求 full-N join 起始／發布前才核整份索引，逐列沿已核 entries merge，不能 N 次呼叫會重算全 cohort hash 的 `entry_for()`。分頁只做有界精確讀回；排除／pending 母體不得由 P01 篩後集合推定。單一 aware cutoff 與 source／method pins 必須一致；來源仍為 current-observed-only、availability unknown、PIT false。

初輪新查詢 DTO mypy 有 17 項錯誤，主要為 Decimal exponent narrowing 及封印 anchor 欄位缺型別註記，已交 owner 修正。索引本身該輪沒有型別錯誤。完整三組 AND／OR、未知政策、全域排序／分頁、source 變動、清理雙錯誤及原 MA／F17 回歸需另取得固定版本結果，不由上述五項推論。
