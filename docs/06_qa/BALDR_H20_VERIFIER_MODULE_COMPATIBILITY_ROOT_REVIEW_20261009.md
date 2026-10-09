# H20 verifier 模組名稱相容層：Root 審查

本次只驗證隔離執行器的模組名稱相容修正，尚未證明完整 Main、原保存 H20 或新版 EXE 的操作旅程。

## 修正與審查結果

候選位於 `output/qa/h20_dual_sqlite_readonly_main_20261009_d/bootstrap_format_candidate_20261009_b/`，child SHA-256 為 `81c69b8bef1a454b600eff3400d41089abfaea8349b5a04b5fa8ad4292a205b9`。Root 已閱讀完整 `module_name_compatibility.diff`。

錯誤名稱來自固定 dual child 的 `extra_modules`，不在 legacy 原始 `MODULES`。相容層保留原始 17 項與額外 9 項的宣告，合併去重後仍為 23 項；只將不存在的 `app_module.recommendation.stock_research_report_service` 修正為 `app_module.stock_research_report_service`。Canonical 檔案 SHA-256 固定為 `86c0a2db60a6d933128bab50e9c6c77bf6e55258a164eacf2b4450a331b41291`。

審查確認：原始序列與修正後序列均核對固定摘要，verifier 回傳的 origin 集合必須完整且每項路徑與來源 SHA 相符；例外與執行期間 tuple 替換會拒絕，並在 finally 還原清單。未刪除驗證項、建立假模組別名或跳過來源雜湊。

## Root 實際複驗

第一次 sandbox 執行的 13 項均在載入 candidate 的 `ATTEMPT.resolve(strict=True)` 遇到 Windows `WinError 5`，未抵達功能斷言；這次結果不作為功能失敗或通過的證據。

改用已授權的全新隔離目錄執行：

```powershell
.\.venv\Scripts\python.exe -m pytest output/qa/h20_dual_sqlite_readonly_main_20261009_d/bootstrap_format_candidate_20261009_b/test_verifier_module_compatibility.py -q -o addopts= --basetemp=C:/t/h20_b_root_review_20261009_a
```

實際結果：**13 passed，0.70 秒，exit 0**。此次為合成 seam 與來源對照驗證，未啟動 Main，未連接正式資料庫。

## 下一個驗證範圍

本修正可進入下一次隔離 Main 封套的準備。執行前仍須重新核對 controller、preparer、child 三檔與完整 dependency 雜湊，確認新 attempt 目錄未存在。Main 的實際載入、H20 名單、下鑽、返回與收藏重開須由該次執行另行證明；目前不要求使用者重驗舊 EXE。
