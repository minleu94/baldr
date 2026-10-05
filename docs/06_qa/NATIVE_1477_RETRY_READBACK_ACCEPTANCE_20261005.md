# 1477 Native 取消、重試、保存與新程序讀回驗收

2026-10-05 09:23 UTC 完成有界驗收，產品基線 `770625cd9f08a715b208ef632f3988d477c440e5`。使用者授權桌面至16:11 UTC。輸入使用既有隔離 QA 資料與正常 Windows/PySide6 QTest 操作；未修改正式資料、使用者持倉、排程或產品程式，未執行 learner、producer、全套回歸或暫存清理。

## 同一新身份的操作鏈

| 項目 | 實際證據 |
|---|---|
| 原保存來源 | `rec_3a882dd9fc06407298ccbd2a5e1c994f` |
| 真正取消完成 | generation 2；已取消、worker停止、native_finished到達；完整last-good與原來源artifact保留 |
| 重試完成 | generation 3；worker run約4.375秒，UI接受等待4.5秒；finished與native_finished均記錄 |
| 新結果／保存來源 | `rec_e677f9ba56d84a5cbcd6f18d5778a01c`，未沿用原result ID |
| 股票／日期 | 1477；決策日2026-10-05、保存來源行情日2026-10-02；sealed config的manual_research_universe僅1477 |
| Payload hash | `sha256:708fcd18c1980817203549d7a81440811c01a5677d39642e1d26cd6d9c0b5802` |
| Raw artifact hash | `sha256:40c62704e28ccd1f52e724de456b7b1af93942f0e6b90d62b590ff6f0e822965` |
| 新程序讀回 | 第一程序PID35148；最終新程序PID34768；完整execution、result ID、payload/raw hash相同，可見1477未入選紀錄與已驗證提示 |

本次正常UI建立新分析所收集的設定是PE max999、volume ratio min1；新結果因量能篩選未入選。這是實際完成並保存的篩選紀錄，不是推薦成功。沒有把原來源PE max1的未入選原因或舊run冒充這筆新結果。個股研究的saved_analysis為not_in_result，但source/result/decision/data日期均綁定新來源，沒有合成Advice；source_snapshot_hash欄位缺值仍保持空值，沒有由payload hash代填。

## 新來源的四項拒絕

1. Native正常個股報告載入同一新來源，但截止日選2026-10-04：拒絕決策日10/5的未來Advice，狀態unavailable，不套用舊來源。
2. 新artifact的小型副本將決策日改為10/6，保留原index：Native canonical讀取拒絕hash/schema不符。
3. 同一副本將artifact內result/run改為另一ID：Native拒絕opaque index identity不符。
4. 同一副本改index payload hash：Native拒絕index/artifact完整性失敗。

後三項均以真正store/query及可見「讀取」按鈕觸發，畫面與canonical last-good保持同一新result。只複製42,087 bytes的QA artifact與index；原artifact/index bytes在負例前後相同。並未修改真實保存來源或正式DB。

## Driver修正與界線

此前90秒重試收據缺少足夠runtime資料，其歷史根因仍不能回推。本次使用已準備的pre-start訊號觀測、processEvents＋sleep(.02)，在原90秒上限內一次完成真實重試，不直接延長期限。詳細run-enter/exit、progress、finished/native_finished、modal與config見worker_events.jsonl。

新程序讀回的第一個driver誤查不存在的Request.universe；改讀真正sealed config的manual_research_universe，保留失敗收據，僅重新開讀回程序，沒有重跑推薦。第二版metadata斷言通過但截圖可能仍是DWM前一張「正在讀取」；第三版加入已讀取提示與非空表格條件、repaint＋有界350ms畫面刷新，再確認實際截圖。最終正向與拒絕畫面均已人工檢視。沒有據此新增產品修正。

先前離屏訊號探針與2個精準測試仍僅支援driver診斷；本次Native結果由真實UI收據判定，沒有用fixture替代。已有learner、資料與UI回歸未重跑。1000×835／125%既有接受限制沿用，本批沒有重做尺寸工程、沒有宣告1000×800通過。

## 證據與後續

本機主收據：`output/qa/native_retry_completion_20261005/acceptance.json`；操作鏈`attempt1/native_retry_final_receipt.json`；最終新程序／四負例`reopen3/reopen_negative_receipt.json`。reopen與reopen2的失敗／不足截圖證據保留，不能用它們宣告最終畫面接受。

正式Library圖片（Native QA，非模型成熟證據）：

| 圖片 | library_file_id |
|---|---|
| 新程序同一來源讀回 | `libfile_4a0caaa465ec819188c4b880b112470c` |
| 截止日早於決策日 | `libfile_1ca5381605288191803bf2a4b98b2e49` |
| Artifact錯決策日 | `libfile_fb57bb46c0c881919d706379dd09e636` |
| 錯result/run | `libfile_d8abc987436481918bcee9c4c462cb2d` |
| 錯index hash | `libfile_0583c30490608191981996418201059c` |

本批四個QA程序均已退出，09:23:01 UTC核對無殘留PID，桌面已釋放；其他應用未關閉。這筆驗收完成原待驗Native操作鏈，沒有增加自然成熟、正式模型、PIT或交易資格。2382正常load的header狀態已於前批確認，未選定保存來源的日期文字歧義仍保持原界線。後續由父層安排已批准的安全暫存清理，再依唯一原計畫推進；永久刪除仍需逐項批准。
