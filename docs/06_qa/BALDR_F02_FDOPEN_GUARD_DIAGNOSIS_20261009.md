# F02 完整 257 驗收寫入防護診斷

e 監督器以 c 啟動契約為基底，Root AST 比較確認最小環境、platform-machine child probe、worker 與正式 QA 根分類器五個核心函式相同。e guard-only 與 calculation-identity probe 通過後，完整 257 run 於第一次合成產製寫入停止，未完成第一段或 AND／OR 矩陣，不能授予 F02 完整接受。

失敗目標封套為 `output/qa/f02_ma_composite_257_acceptance_20261009_e/attempt_7d6d0e725fe948a2/acceptance_receipt.json`，外層為 `C:/t/f02_ma_composite_257_3bd2656df607`。Owner 核對 terminal exit 1、Job empty-before-close／closed、owned processes 為 0，來源與監督器前後 pins 相同。目標記錄 fixture_creation 失敗；此階段呼叫真產製器建立合成技術來源，並非完整查詢驗收已經執行。

Root 閱讀 `daily_market_technical_universe_v4_store._write_immutable()`：它以 `os.open` 建立 owned `.partial`，再呼叫 `os.fdopen(descriptor, "wb")`。e audit handler 將事件 mode 原樣傳入只接受 `"wb"` 的 token verifier。Root 在全新隔離目錄以相同公開 API 執行獨立 probe，確認 CPython audit event 實際 mode 為 `"w"`、flags 為 33665，因而觸發 `untracked_or_nonexact_fdopen_rejected`。Probe 收據為 `output/qa/f02_fd_audit_4pxqw_h4/receipt.json`；沒有產品匯入或原始資料操作。

下一候選須在公開 `os.fdopen` 層核對精確 binary mode／options 與本次 issued descriptor，再在一次性 capability 範圍接受對應 normalized audit event。不能直接允許所有 `"w"` 或數字 descriptor。必要拒絕案例包括未授權 descriptor、文字 mode、非精確 options、重複消費、關閉後 descriptor 重用與檔案身分置換。產品產製與金融計算不因防護診斷而修改；完整 257 與效能矩陣仍待。
