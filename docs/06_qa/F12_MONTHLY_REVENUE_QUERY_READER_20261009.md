# F12 月營收全母體查詢 reader 驗收紀錄

## 範圍

本紀錄只涵蓋月營收 YoY index 與 F17／四均線／月營收全母體查詢 reader 的合成來源驗收。它不代表一般 MainWindow、UI、觀察清單收藏、跨程序 exact reopen、更新入口或正式市場資料已完成驗收。

查詢沿用既有 `project_selection_monthly_revenue_yoy` 與 `evaluate_monthly_revenue_yoy_min` Decimal 投影／門檻語意。條件在完整宣告母體上評估，硬性來源資格先套用；F17、MA、月營收只由啟用的研究群組參與 AND／OR。未知政策不會把 pending／excluded 列升格成已評估符合。排序在全母體完成後才分頁，頁面大小仍有上限。

月營收來源為 current-observed-only。`official_available_at` 為未知，`historical_pit_eligible` 與 `formal_pit_eligible` 都是 `false`。本驗收沒有使用未來資料推造可得時間，也沒有把觀察時間當公告時間。

## Attempt 03 證據

- pytest：`tests/test_daily_market_technical_official_disposition_revenue_query_reader_v1.py`，8 passed，218.14 秒，exit 0。
- 命令：`.\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_daily_market_technical_official_disposition_revenue_query_reader_v1.py -q -o addopts= --basetemp C:\t\f12_revenue_reader_repair_attempt03`
- pytest log：[`attempt03/pytest.log`](../../output/qa/F12_REVENUE_READER_REPAIR_20261008_A/attempt03/pytest.log)
- 終態 receipt：[`attempt03/terminal.json`](../../output/qa/F12_REVENUE_READER_REPAIR_20261008_A/attempt03/terminal.json)
- 截止時鐘 receipt：`C:\t\f12_revenue_reader_repair_attempt03\test_active_or_query_is_global0\f12_cutoff_normalization_receipt.json`
- 固定 basetemp：`C:\t\f12_revenue_reader_repair_attempt03`；來源是隔離 synthetic fixture，不是正式市場資料。
- 共享 reader SHA-256：`FC9C3D089C703F2BC815D0CE02310916DE49AA1CE35CDFA8336CA7E630DC8045`
- 測試檔 SHA-256：`DA303AEB5EAAED76B9F983C7AF3098C368681FC1F290052C121AF86E3C012171`

截止時鐘案例保留原始 MA cutoff `2026-10-07T16:00:00+08:00`，月營收與組合查詢 cutoff 為 `2026-10-07T08:00:00+00:00`。兩者解析為同一 aware instant；來源 request 的原始表示沒有被改寫。相差一分鐘、naive 或格式錯誤的時間仍拒絕。

合成 SQLite 來源的 `snapshot_binding.source_file_pins_start`、`source_file_pins_after_copy`、`source_file_pins_finish` 三組 pins 相同；capture HTML 與 CSV 僅有 session 起訖 pins，兩組起訖一致。HTML SHA 為 `91921bebe90159dd43978e86487b4043f9233851d658943fda8805bbd74bec21`，CSV SHA 為 `155713d294d1ddc7daa3b08de244aef6f2b91aca9010dde40d67be4d937372ef`，SQLite 主檔 SHA 為 `3c3ace1451cbf37040e65bd775c7ac42ab9ef699157421687b57a7f93a1bd92f`。此為合成原件證據，不代表官方來源最新或真實市場覆蓋。

reader 對月營收 index 的完整身份在全母體 execute 的輸入驗證與發布驗證各檢查一次，首次 page 再檢查一次；不是每個股票列重新雜湊整個 index。頁面來源 pins 前後一致。修正後的頁列 `included_by_unknown_policy` 使用三態政策結果，而不是把「可瀏覽」狀態當成「政策納入」。

已覆蓋的查詢案例包括：完整宣告母體 browse、跨 segment 的全域 OR 查詢與排序、硬資格不可由 OR 救回、三組條件 AND／OR 與未知政策、截止來源不匹配拒絕、incomplete store 不發 qualified bundle、月營收來源替換拒絕，以及取消時不發布部分結果。

## 尚未完成

現有 query reader 可以把已完成的 `DailyMarketMonthlyRevenueYoyIndexSessionV1` 綁入單一 F17／MA read session，但目前沒有一般產品用的月營收 exact-source reopen factory。月營收 index session identity 含該次 snapshot id 與 reader copy path；JSON archive decoder 明確只產生 unverified archive。因此不能僅從收藏 JSON 的自洽 hash 恢復來源資格，也不能在重開時改讀當下 provider 的新版本並稱為原版本。

一般 UI 尚未提供月營收條件輸入、YoY 排序、分母／未知數呈現或收藏重開。這項 reader 回歸不表示 F12 的產品接線、collection restore、source picker、Main／Watchlist route、fresh-process restore 或完整觀察清單體驗已完成。下一步必須先建立能重新核驗原 monthly source pins 的 public exact-open 契約，再由 MA research UI 接入門檻、unknown policy、全域排序與分頁；未完成之前不應把月營收研究宣稱為可操作功能。
