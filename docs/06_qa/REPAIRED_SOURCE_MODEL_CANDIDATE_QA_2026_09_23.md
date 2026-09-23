# 正式來源修復後的新候選資料與模型驗收

## 版本邊界與目前進度

先前官方市場 v3 資料建置完成後，正式來源才補回九個交易日 14,869 列，並排除三個休市日和 5/20 的 54 列，共 2,942 列。舊 v3 的股票快照沒有上述九日資料，仍含休市日 2,888 列及額外 54 列；1256／1477 的原錯價則已更正。因此舊 v3 的訓練與驗收只適用於原版本，不能宣稱涵蓋後續正式來源修復。

本輪建立隔離候選、重算特徵與標籤後重新 fit／評估；完成資料修復不等於取得模型啟用資格。62 欄名稱、順序、尺度、dtype、缺值與公式不變，15 個與大型重構協調的 ML 契約檔不改動。正式 pointer、rule_only 與既有版本保留。候選目錄為 `E:/codex_model_repair_20260923/candidate_formal_repair_run01/`；本節為來源準備紀錄，資料集及模型尚待完成後的個別驗收。

## 不可變更的股票與市場來源

股票來源為正式技指修復 run02 的 `source.sqlite`：SHA-256 `05658755b956680a614aa67fa481971abe83c649e2ea7b39202e3486e232cd65`，日價 logical hash `16570e7e93d90997bdecd522f3afbb6abbf53666b81b728df78a29b57e1cfa59`，5,331,231 列。候選 builder 從 `daily_prices` 完整前綴重算技術特徵，市場部分讀核驗官方回應；不讀快照內尚待重算的 `technical_indicators`。這讓不可變更股票來源能與正式技指發布分開驗收，而不是將舊技指帶入新候選。

官方市場新清冊位於候選目錄 `official_market/capture.json`，SHA-256 `e10d2d4a779850700580e1f3959c834645d533447108a5f642015f8677cc0d4b`。它組合已驗證歷史月報與新九月報表，共 153 個月、306 份原始回應、3,106 日，截止 2026-09-23；原始 bytes 和每份取得時鐘不變。組合驗收於 `2026-09-23T23:13:24.809657+00:00` 完成，逐日 31,060 個日期／代碼／市場數值欄位與 run02 快照一致。`composition_receipt.json` 保留來源、檢查器與 reader hashes。

官方來源 reader 對每個月檢查 `min(月底, 全局截止日)` 嚴格早於該回應真正取得的臺北日期；全局截止日仍須早於清冊完成日，任何回應不得晚於清冊完成時鐘。較早已完成月份可以沿用封存回應，不能修改取得時間來通過新月份的驗證。28 個 focused tests 通過，包含舊月份沿用、同日尚不可得、未完成月份與未來回應拒絕。

本候選只標記 restated research；晚期修訂取得時間不回填至歷史決策日，不授予 historical PIT、formal OOS、production action 或 promotion。缺失的歷史產業標籤與現金配置 targets 仍是原契約的限制。

## 候選建置入口與來源檢查

`scripts/build_ml_restatement_candidate.py` 先建立外部來源 profile，再交既有 v3 builder；原入口的預設股票快照與驗證規則不變。本輪固定新快照若移除 profile reference，消費者會拒絕。Profile 綁定四組已套用修訂、官方回應、run02 source.json／SQLite hashes，以及 validator 程式內容。建立時程式路徑保留作追溯，相同內容的程式換到另一 checkout 不會僅因路徑不同而失敗；程式內容或來源證據變更仍須重新核驗。

真實唯讀來源 smoke 已確認九日 14,869 列的全部 17 欄、5/20 全日 1,954 列中受保護的 868 列與保留的 1,086 列、2,942 個排除 key 和官方 3,106 日。Profile、receipt 與 log 留在 repo 本機 QA 目錄；72 項 candidate／v3／current-input／training-integrity tests、4 檔 targeted mypy、py_compile 及 CLI 入口通過。這是建置前檢查，不能取代後續全量資料與模型驗收。
