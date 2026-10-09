# F02 完整 257 驗收寫入防護診斷

e 監督器以 c 啟動契約為基底，Root AST 比較確認最小環境、platform-machine child probe、worker 與正式 QA 根分類器五個核心函式相同。e guard-only 與 calculation-identity probe 通過後，完整 257 run 於第一次合成產製寫入停止，未完成第一段或 AND／OR 矩陣，不能授予 F02 完整接受。

失敗目標封套為 `output/qa/f02_ma_composite_257_acceptance_20261009_e/attempt_7d6d0e725fe948a2/acceptance_receipt.json`，外層為 `C:/t/f02_ma_composite_257_3bd2656df607`。Owner 核對 terminal exit 1、Job empty-before-close／closed、owned processes 為 0，來源與監督器前後 pins 相同。目標記錄 fixture_creation 失敗；此階段呼叫真產製器建立合成技術來源，並非完整查詢驗收已經執行。

Root 閱讀 `daily_market_technical_universe_v4_store._write_immutable()`：它以 `os.open` 建立 owned `.partial`，再呼叫 `os.fdopen(descriptor, "wb")`。e audit handler 將事件 mode 原樣傳入只接受 `"wb"` 的 token verifier。Root 在全新隔離目錄以相同公開 API 執行獨立 probe，確認 CPython audit event 實際 mode 為 `"w"`、flags 為 33665，因而觸發 `untracked_or_nonexact_fdopen_rejected`。Probe 收據為 `output/qa/f02_fd_audit_4pxqw_h4/receipt.json`；沒有產品匯入或原始資料操作。

下一候選須在公開 `os.fdopen` 層核對精確 binary mode／options 與本次 issued descriptor，再在一次性 capability 範圍接受對應 normalized audit event。不能直接允許所有 `"w"` 或數字 descriptor。必要拒絕案例包括未授權 descriptor、文字 mode、非精確 options、重複消費、關閉後 descriptor 重用與檔案身分置換。產品產製與金融計算不因防護診斷而修改；完整 257 與效能矩陣仍待。

f 候選已完成精確 fdopen 防護修正，但完整驗收仍失敗。Root 獨立讀取 `C:/t/f02_ma_composite_257_cbb5429f696a/supervisor_receipt.json`：worker exit 1、監督器與 target pins 起訖相同、QA 清冊只有本次 attempt 增加、串流錯誤為空；Job 已空且關閉，零 owned processes 已證明。目標 `output/qa/f02_ma_composite_257_acceptance_20261009_f/attempt_a7e3c829743b463d/acceptance_receipt.json` 記錄 `fixture_creation`、`bundle_create_failed`、244719 ms，沒有進入完整查詢矩陣。

本次停止位置是 bundle shard 原子發布。Root 核對產品 `daily_market_technical_official_disposition_bundle_v1.py` SHA 為 `8251087995636762aa55bbab74923ba2d762aea6bc95b11a286acbc7bc1ee47a`；`_publish_objects()` 先驗 staged shard SHA，再以 `os.link` 將本次 `.attempts/<uuid>/shard-000001.jsonl` 發布至 `objects/<sha256>.jsonl`。該步被 QA 的全面 link 禁止擋下，尚未到 manifest 發布；不能將此封套視為查詢結果或完整 257 接受。

下一個 g QA 候選只可對已釘選的兩個產品發布呼叫端核精確來源／目的、同一隔離 attempt 與同卷、排他目的、內容 SHA／定址名稱、native 檔案身分及合法 link-count 生命週期。未知呼叫端、外部路徑、覆寫及 symlink 仍拒絕；需先完成正反例自測，再執行同一固定 target。f 失敗封套保留，不修改產品發布或金融計算語意。

另有尚待解決的產品入口契約差異，必須先於下一次完整產製重跑釐清。Root 直接核固定 target：明示納入 258 檔、最後一檔沒有來源列，預期 257 processed／1 pending，並要求瀏覽回讀該 pending row；不是將缺資料改稱合格觀測。現行 bundle metadata validator 要求 `technical.receipt_status == complete`，而 universe store `complete()` 要求 processed 等於 included 且 pending 為零。這些來源規則與該固定 target 的 pending 目標表面矛盾。已要求交叉核對完整 opener 是否另有 partial 研究入口；在契約確認前，不縮減固定母體以取得綠燈，也不把 partial ledger 的可讀性當成推薦資格。

Owner 進一步定位 `_technical_code_status()` 與 shard writer：完成 segment 覆蓋的 included 股票均為 processed，缺價格資料另記 `technical_missing_data`，不會成為 pending。因此舊 target 的 pending 判讀是錯誤 oracle。已指示保留舊 target／封套，另建待審 v3：仍 259 declared／258 included／1 excluded、最後碼仍無價格來源，完整處理應為 258 processed／0 pending／1 missing-data；原 257 有價格來源股票的跨 256 分段與完整 AND／OR、hard gate、排序案例必須保留。新版本需重新推導缺資料列的真未知狀態，不能只改計數；真正 partial／pending ledger 仍為另一個未驗收範圍，不由此版本宣告接受。
