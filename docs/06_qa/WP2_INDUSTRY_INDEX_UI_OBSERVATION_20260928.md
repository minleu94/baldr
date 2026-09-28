# WP2 產業指數來源觀察 UI QA（2026-09-28）

## 行為範圍

推薦來源區只在同次 sealed `company_registry_source_snapshot` 的 `usage` 明列 `current_industry_index_performance_for_reason` 時，才嘗試顯示產業指數列觀察。畫面先將 execution event 投影成純 JSON，再驗 outer snapshot hash、provider 定義的 nested observation self-hash、outer hash echo、unknown source-time status、available/published 為空與 capture-time warning。必要欄位格式不符時不顯示 rowset 詳情，改顯示 unknown 與下一步。

可核驗觀察會顯示來源識別、CSV／SQLite 儲存型態與定位、列日期範圍、列數、欄位、rowset hash，以及 CSV artifact bytes/hash 或 SQLite table 名稱。`observed_at` 明確標為本機讀取時間；`available_at`、`published_at` 未知，`PIT eligible=false`。未保存時標「本輪尚未 canonical 保存；以下僅為本機觀測」；完成 exact result ID canonical readback 後才標「已 canonical 保存並以同一結果 ID 讀回」。程式不讀當下 CSV／SQLite 替歷史事件補值。

## 真 caller 測試

`test_personal_clock_v2_source_event_survives_real_save_and_exact_reload` 使用實際 `IndustryMapperDataProvider.load_industry_index_frame()` 載入兩列隔離 CSV，再由 `RecommendationService` 個人規則模式執行、封存來源事件、canonical save、query readback 與 RecommendationView exact-ID reload。測試驗證來源列日期、rowset hash、available/published unknown 與本機 observed time。保存前也展示同次自洽 sealed event，但標示未 canonical 保存。

測試隨後將本機 CSV 改為 2099 年 sentinel；exact-ID readback 仍顯示原 sealed observation，不出現 sentinel 日期，證明 UI 沒有 reread live CSV。另一負例在 outer snapshot 重簽後改壞 inner observation hash echo，畫面不顯示 rowset hash並降為 unknown；再一負例將 `warnings` 改成含正確 token 的純字串並重簽 outer hash，仍被拒絕。此 UI 測試不代表來源具官方發布時間；它只驗證列來源的封存身分與畫面不補值。

驗證命令及結果見同批 `output/qa/personal_daily_product_20261006/wp2_ui_industry_observation_20260928/closeout_01/wp3_modules.log`：兩個 UI 模組 32 passed / exit 0。Workbench、Update QA、734-file mypy、`py_compile` 與 whitespace diff-check 結果列於 `WP3_WATCHLIST_QA_20260928.md`，freeze receipt 收錄其 owner 路徑與 SHA。

## 使用限制

產業分類本身仍是 current-only，不能當歷史成分 point-in-time 證據。列資料日期範圍及本機 `observed_at` 不能推導上游何時可得；來源沒有可信的 `available_at`／`published_at` 就必須保持 unknown。v1 snapshot 不含真行情資料日；UI 延續 unknown，不用今日資料填回。
