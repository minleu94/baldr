# Watchlist 候選池本機搜尋 QA（2026-10-27）

## 行為與邊界

Watchlist 候選池新增股票代號／名稱部分文字搜尋，搜尋範圍僅是目前已載入的表格模型。結果摘要顯示搜尋字詞及符合候選列數／目前清單總列數；同股不同來源仍逐列計數，原候選總數／不同代號數不受篩選影響。清除搜尋會還原全部列，排序後會按目前模型順序重新套用條件。搜尋隱藏原選取列時會清除選取，避免下方摘要沿用不可見候選。

載入中、清單不存在或快照不可用時，符合數明示未知；只有成功載入的空清單顯示 0／0。查詢只讀目前模型中的代號與名稱，不重新載入 Watchlist 或名稱、不擴大 Universe、不改候選身份、來源或寫入流程。

## 驗證

| 驗證 | 結果 | 證據 |
|---|---|---|
| Watchlist layout／搜尋回歸 | 14 passed；含代號與名稱搜尋、重複來源列保留、符合列計數、總數不變、排序後篩選、隱藏選取清除、清除搜尋、載入中未知及已載入空清單／缺件差異 | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/single_owned_qa_81268348c2254787879fbe8d0c1f8ab5/receipt.json`，SHA-256 `9822c27d895ad0734c631c1f61a9fd1c70835b4437d36d0701baf6c4adf2d058` |
| 必要 Workbench UI regression | 97 passed | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/single_owned_qa_491e78651d0548539bd7ecaa322d0c3d/receipt.json`，SHA-256 `6b3d0a2f92196b9695745ed6efbaf759cf32ca7b3c676e44df9b05b2d668cb4c` |
| Update tab validator | 25 passed／0 failed／4 skipped | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/single_owned_qa_901f0f90b6d34105867e3ee3b7c25f57/receipt.json`，SHA-256 `53e53bc55426a369ad09dd6d0f2d211183f85d09dec4e26c92ada54158c24f1b` |
| Watchlist targeted mypy | 1 source file，無問題（`--follow-imports=skip`） | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/single_owned_qa_d184f82146c3447c873b823d1af0613d/receipt.json`，SHA-256 `3fb527f0d2bda29b4fcf2b9ee4f95810da173c0907e869b28c23f885ce5f6bb2` |
| 修改 Python 檔 `py_compile` | 2 檔通過 | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/single_owned_qa_e758f613a16c4bd79477ba68d5072df4/receipt.json`，SHA-256 `51b658efdfa83b75774d45cda370ab6896d282dfb62be49ff6852de925f66f73` |
| 指定應用範圍 mypy | **blocked**：未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 有既存 syntax error，mypy 未能檢查完整範圍 | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/single_owned_qa_76aae8892313456995835f6043440b64/receipt.json`，SHA-256 `fb7cf9df66288b2076eaa60a27829b536d6fd8488dc794d506ba635ed4824380` |
| 新增 QA／索引 scoped document control | 0 errors | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/single_owned_qa_02ceb5eb42ef4ee29f80efe9d9377733/receipt.json`，SHA-256 `3a490db3501f1f2c4f404615051d2119c4e546171c20d7be06e1e9b4731c890b` |
| Task-wide document control | 63 errors across 12 features／63 link sources；既有 Snapshot 錨點與 `output/` 越界連結，本輪新增 QA／手冊連結未列錯 | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/single_owned_qa_96a859027e0a45928c1b7a8f7a1e0b0f/receipt.json`，SHA-256 `22fd8f40333b19224211d9f03f5ec1e9b1f4490b3f686d557ee73901be42700f` |
| scoped `git diff --check` 與新增 QA 文件空白檢查 | 通過；Git 只提示既有 dirty 檔的 LF／CRLF 轉換 | `output/tasks/watchlist-candidate-pool-search-20261027/evidence/final_diff_check.txt` |

所有上述 QA 均由本任務的 owned root runner 啟動；Windows Job 的 kill-on-close、12 個程序上限、8 GiB committed-memory 上限及啟動前 RAM 保留均按收據記錄。首輪測試指出載入中訊息未明示符合數未知，已調整文案並重新執行全數通過。

## 限制

未走查原生 GUI／Owner UAT，也未量測正式資料的搜尋端到端延遲；本次測例證明本機表格篩選與列身份語意，不代表資料來源完整度或產品 Gate 通過。搜尋能力限定目前已載入清單。
