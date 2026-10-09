# 推薦詳情捲動的目前程式審查

## 實際驗證

Root 直接閱讀並執行 `tests/test_ui_qt_recommendation_layout.py` 的理由全文、鍵盤捲動、收合模式及標準導航窄窗個人模式測試，結果 4 passed／6 deselected，4.16 秒。日誌：`output/qa/f17_normal_capture_pair_20261009_a/root_recommendation_layout_current.log`。

另以畫面輸出模式執行完整文件案例，1 passed／9 deselected，2.64 秒。Root 實際查看 460×700 截圖：分數拆解表與排名門檻出現在結果區；外層捲到底後可到達「可能影響排名的因素」的最後段。測試也核對最後段座標落在 viewport，而非只檢查文字存在。

畫面保存在 `output/qa/root_recommendation_layout_visual_20261009_a/` 的 `recommendation_full_document_460x700.png` 與 `recommendation_full_document_end_460x700.png`。此為 offscreen 合成推薦資料，不是原始股票或真人接受；末尾文字灰色及窄窗可讀性仍需真人觀察。

## 固定版本與界線

- view SHA-256：`5F0FAA96F246C62C7693E1771D538D88B72AE95A6544208D74B14650ED16EDD5`。
- test SHA-256：`F478EDB0044FF421072F2FD080C302615EFE6FDB5238EFC7239DB709668DEFFA`。
- 測試前後兩檔 SHA 相同。沒有修改 UI 或讀取正式股票資料。
- 結果支持目前 Python 介面的捲動路徑；不能證明舊 `d9a115f67d2b` EXE、新版同版封裝、原 H20 速度或完整推薦分析完成。

新版 EXE 經同版驗證後，真人檢查應是：在非最大化視窗選一筆推薦，點「展開推薦理由」，捲到分數拆解、排名門檻與最後一段排名因素；將焦點放在理由文字內，以 PageDown／End 亦能到末尾；切換個人模式，歷史版本、來源及候選按鈕不重疊且可完整讀取。目前尚未提供新的驗收啟動檔。

## 使用者回報未入選紀錄的選列重現

另新增真正 view 選列案例，使用回報的 2382、`-31.22936518258622391666432545／50`、`liquidity_volume_ratio_below_min` 與 degraded 品質。實際詳情會先說明觀測量縮 -31.23%、策略要求至少 50.00%、本次尚未產生推薦分數或排名，並保留原始完整數值、原因代碼及品質。H20 原保存研究另由個人模型研究入口查看，不將未入選紀錄升格為推薦。

Root 已實讀 evaluator：此原因來自 `latest_volume_change_percent` 與 `volume_change_min_percent` 的比較，百分比呈現符合實際語義。選列案例 1 passed／10 deselected，2.97 秒，日誌 `output/qa/f17_normal_capture_pair_20261009_a/root_screening_row_explanation.log`；沒有重新分析原始股票資料或修改策略門檻。此新增案例之後 test 檔版本已更新；上節 SHA 保留為先前四項及截圖驗證當時的版本。
