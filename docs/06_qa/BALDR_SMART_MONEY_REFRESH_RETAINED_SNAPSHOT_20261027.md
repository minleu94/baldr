# Smart Money 主表刷新保留快照狀態 QA（2026-10-27）

## 目標與範圍

讓使用者在 Smart Money 主表刷新期間、刷新失敗，或無法取得台灣市場日期時，知道畫面仍保留哪一個前次成功快照，包括其週期、範圍與資料日。首次載入失敗不得暗示有舊資料；刷新成功後狀態改顯新快照身份與資料日。主表、個股明細及分點追蹤各自顯示狀態，避免背景子查詢覆蓋主表狀態；切換分點時先清除舊列。

本切片只改狀態與舊列呈現。資料來源查詢、摘要計算、品質／警告語意、範圍資格與日期守衛不變；台灣市場日期不可得時仍不啟動讀取。

文件關聯檢查發現 Smart Money view 與測試原先未列入 Feature Map 的變更模式；已將它們登記在既有「市場探索」工作區，供後續變更自動匹配功能文件、操作手冊與 QA 路由。此登記不改產品行為。

## 覆蓋案例

- 有前次快照：開始刷新時標示目前選擇及前次成功週期／範圍／資料日。
- 有前次快照：刷新失敗後保留原主表列，錯誤狀態同時標示前次成功查詢身份。
- 沒有前次快照：初次載入失敗維持載入失敗，不顯示前次資料提示。
- 有前次快照：刷新成功後以新身份及資料日取代保留快照提示。
- 台灣市場日期不可得：不送出讀取，保留原表格並指出仍顯示的查詢身份。
- 個股明細／分點追蹤狀態不覆蓋主表狀態；切換分點時清除前一分點表格列。

## 驗證

第一輪受控驗證：Smart Money async/view **19 passed／1 failed**；失敗顯示主表成功狀態被自動啟動的分點追蹤狀態覆蓋。依此將主表、個股明細與分點追蹤狀態分開，並增加週期／範圍身份、分點切換清舊案例。該輪 receipt SHA-256 `75769be4416d1ad04e3f1354b38cf52130503e006aee3835300e8034a076f21f`，位於 `output/tasks/smart-money-refresh-retained-snapshot-20261027/evidence/single_owned_qa_8eef3dd932d549019613f060e73817ba/receipt.json`。

第二輪受控驗證的 Smart Money async/view 為 **22 passed／1 failed**；舊 view test 使用的快照替身沒有 `period` 欄位。程式改為在成功套用快照時保存查詢週期，狀態顯示使用保存的查詢身份；第二輪 receipt SHA-256 `c06c42c522a45fffd145fca89df0b118f0b7b9fce096945ea9b4e64d1b03aca7`，位於 `output/tasks/smart-money-refresh-retained-snapshot-20261027/evidence/single_owned_qa_b5a2d09888984b94b49308f04ee1b6fb/receipt.json`。

第三輪受控驗證中，Smart Money async/view **23 passed**、必要 Workbench UI regression **97 passed**、Update validator **25 passed／0 failed／4 skipped**，兩個修改 Python 檔 `py_compile` 通過。全指定 mypy 執行至 `data_module/mops_t164_pdf_disposition_bridge.py:411` 後因既有語法錯誤中止（exit 2，未能驗完其餘來源）。QA runner exit 1 只來自此 mypy 項目；named Job 的剩餘 PID 為 0、未強制清理。最終 receipt SHA-256 `3cf945a3c184eade0eaef02722c3f02702296397e7f454f7702a0359ee36aa9d`，位於 `output/tasks/smart-money-refresh-retained-snapshot-20261027/evidence/single_owned_qa_47ede879a9a04c7f8e297b22398f2a8c/receipt.json`。另一次 RAM 僅 16 MiB 的預檢在啟動子程序前拒絕，沒有測試子程序啟動；receipt SHA-256 `87e2730e31fc834d92495f0de9cfb8b00c3cf2872275204e017757c79cbfac53`。

原生 GUI／Owner UAT 未做；不宣稱為產品驗收。來源、品質、警告與資料資格不變。

文件檢查依更新後 Feature Map 檢查 12 個 feature、5 個連結來源；Smart Money QA、QA index、UI feature 文件及資料研究手冊共 0 個連結錯誤。Snapshot 仍有 4 個既有連結指向 Market Session QA 中不存在的歷史錨點；本輪雖新增了當前狀態摘要，但沒有改動這 4 個既有引用。檢查輸出留於 `output/tasks/smart-money-refresh-retained-snapshot-20261027/evidence/documentation_check.json`。

