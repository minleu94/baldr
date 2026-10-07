# 推薦工作區真人回饋處理（2026-10-07）

## 範圍與結論

使用者回報：H20 名單的2382下鑽後摘要無有用資訊、不知道收藏位置、全股票三個預設策略同遇官方日曆錯誤，以及非全螢幕時歷史版本控制項擠壓。本輪修正日曆外部來源接線、推薦失敗說明與窄欄排版；原碼隔離回歸通過，尚未更新候選 exe、尚未完成同版及 Native 驗證。H20 真保存來源整條旅程另在驗證，不能宣稱此回報已全部解決。

## 原因與修正

- 舊 `MarketSessionCadence.for_config` 預設日曆位於程式相對 `output/paper_execution_eod_replay/calendar_cache`；可攜 bundle 不包含該本機產物。共同啟動／TWStockConfig 新增 `OFFICIAL_CALENDAR_CACHE_PATH`，明示外部來源，預設沿外部研究根。這證明接線缺口存在，未證明使用者實際使用的版本或 cache 狀態。沒有放寬官方 cache hash、期限、coverage 或可得時間核驗。
- 推薦 error callback 對共用日曆阻擋提供中文原因，指出換策略／放寬條件無效；原完整錯誤保留 detailedText，舊有效結果與 stale generation guards 保留。其他錯誤仍沿原處理。
- 歷史版本排版原依右側結果寬度，與左側設定欄實際空間不一致。現改依左欄寬度垂直排列版本選擇與兩個按鈕，保留完整工具提示、輔助說明及 Tab 順序。
- H20 正常路由在報告成功後讀回模型原來源、更新五問結論與可見日期／狀態；原 H20 詳細 label 在收合來源區。一般報告失敗時 `reportLoaded` 不發出，H20 reader 不啟動，此控制流程限制仍保留。未讀正式／私人 root 來猜測使用者2382當次原因，亦未用注入 DTO 代替 canonical 整條成功證據。

## 驗證

| 檢查 | 結果與邊界 |
|---|---|
| 窄欄／既有推薦布局、共同設定／日曆來源、H20摘要呈現 | 30 passed；H20仍是既有呈現案例，不是本次真人2382通過 |
| 新日曆來源與實際cache reader | 8 passed：設定優先序、bundle拒絕、frozen外部預設；有效來源可核驗，缺失／過期／竄改／未來取得保持阻擋，cache bytes 不變、無網路fallback |
| 新日曆失敗畫面與推薦execution state | 11 passed：日曆專屬說明、非日曆錯誤不誤分類、stale回呼不開dialog、舊結果保留 |
| mandatory 更新頁 | 85 passed |
| mandatory 更新頁validator | 初次 Windows managed sandbox 21 passed／3 failed／4 skipped，原因為新建隔離Temp strict realpath WinError5；原失敗不抹除。專用Temp重驗25 passed／0 failed／4 skipped，raw `output/qa/baldr_completion_m2_20261007/update_root_4.log` |
| mandatory 全域mypy | 862 source files，0 errors；施工時新technical adapter出現6項型別錯，該leaf修正後再驗通過，原錯誤工具輸出保留 |
| py_compile | 本輪日曆、推薦UI及其測試7檔通過 |

非 Native、人工作業未跑、未觸發正式 Task、未更新原 `dist/baldr/baldr.exe` 或 active delivery、未讀寫正式市場 DB，也未修改模型／預測／交易資格。

## 修正版再驗方式

先核開啟程式的完整版本；H20選2382下鑽後看摘要結論與日期，再返回核原來源／選取。H20收藏目前不列驗收。每日研究收藏另依Manual原入口核對。修正版同一有效官方日曆設定下再跑三預設策略；無有效日曆時必須清楚阻擋，不能記成分析成功。非全螢幕左欄核三控制項全文、可點、Tab順序及版本工具提示。完整入口見[Manual](../07_guides/APPLICATION_MANUAL.md#2026-10-07-真人回饋摘要收藏與推薦失敗)，原完整補完範圍沿[單一計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)。
