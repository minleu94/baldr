# 策略庫保存版本背景讀取與錯誤復原

## 範圍

策略庫選取或切換策略時，原本會在 Qt UI 執行緒呼叫 `StrategyVersionService.list_versions(strategy_id)`。該服務遍歷版本 JSON 檔並逐一解析後才依策略 ID 篩選；檔案數增加時，這段同步工作會占住畫面事件迴圈。

本次只把策略庫的唯讀版本清單讀取移入現有 `TaskWorker`，沒有更改版本儲存服務、JSON 格式、策略內容、回測／promotion 或資料資格。

## 目前互動

- 選取策略後立即顯示「讀取保存版本中…」，暫停版本選單與「以此設定回測」；完成後顯示符合此策略的保存版本筆數。
- 背景工作只執行 `list_versions(strategy_id)`；registry metadata 組合與所有 widget 更新仍在 Qt 主執行緒。
- 同一時間最多一個版本讀取 worker；切換期間只保留最後一個待讀策略。generation 與策略 ID 一起核對，過期結果不會覆蓋目前選取。
- 讀取失敗時仍呈現可用的登記版本，並標示保存來源不可用。若版本讀取服務存在，可按「重試讀取」重新讀取；重試仍是唯讀操作。未提供服務或讀取方法時只顯示原因，不呈現無效重試按鈕。
- 關閉頁面時使現有回覆失效並送出合作取消。底層 `list_versions` 不支援中途取消，因此背景掃描會自然完成；其結果不會再套用到已關閉頁面。

## 驗證結果

- 策略庫頁面與必要 Workbench UI 回歸：**108 passed**。
- `qa_validate_update_tab.py`：**25 passed、0 failed、4 skipped**。
- 策略庫 UI 模組 targeted mypy：**1 source file clean**。
- 兩個修改的 Python 檔 `py_compile`：通過。
- Repo-wide mypy 仍在未修改的 `data_module/mops_t164_pdf_disposition_bridge.py:411` 遇到既存語法錯誤，未能繼續檢查其餘模組。
- 阻塞合成 reader 測試在讀取尚未解除時派送 Qt timer callback，確認事件迴圈仍能處理事件；另測快速切換的單 worker 排隊、拒收舊身份、失敗後重試成功、原版本順序與保存身份，以及不呼叫 writer。
- 原始受控命令與收據保存在 `output/tasks/strategy-library-responsive-version-load-20261027/evidence/`；完整 mypy 失敗收據也予以保留。

## 限制與判讀

這項改動改善讀取期間的界面響應性，不會減少底層 `list_versions` 遍歷及解析所有 JSON 檔的工作，也沒有量測完整保存版本載入時間或正式資料夾中的版本數。測試使用合成 reader，沒有替代原生 Windows GUI／Owner UAT。

服務層合成基線：以每份約 381 bytes 的本機 JSON、每 20 份僅 1 份符合策略篩選，在 300／1,500／6,000 檔規模各跑 10 次（每組先 warm-up 一次）。6,000 檔每次讀取 2,286,300 bytes、解析全部 6,000 份；p50 為 251.785 ms、p95 為 284.563 ms，輸出 ID digest 穩定。這是剛寫入檔案後、OS 快取可能已暖的 service-only 合成量測；臨時檔已清除，不代表正式資料夾或 Qt 完成時間。原始數值見 `output/tasks/strategy-library-responsive-version-load-20261027/evidence/strategy_version_list_synthetic_profile.json`，受控執行收據見 `output/tasks/strategy-library-responsive-version-load-20261027/evidence/single_owned_qa_1a62a8b10f6f458b9629f5002736b00e/receipt.json`。

DannyQuant [每日選股](https://www.dannyquant.com/signal-lottery-preview)與[個股研究](https://www.dannyquant.com/stock)可見讀取中狀態；它們與 Baldr 策略庫使用不同資料及操作。公開頁未提供可重複完成事件，因此本次只對照讀取狀態的清晰度，不宣稱跨站速度相同或更快，也不推論完整產品接受或策略資格。

