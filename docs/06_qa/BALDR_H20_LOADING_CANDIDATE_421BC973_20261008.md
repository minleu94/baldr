# H20 等待提示固定候選 421bc973（2026-10-08）

## 交付範圍

固定 dev 來源 `421bc973a8914c71781330a47ae910e7a907109a` 包含 H20 首次等待提示可見、實際階段與秒數、單一讀取、取消直到背景終態才解鎖，以及總列／可研究／未知計數。理由全文隨長度延伸、結果區整頁捲動與窄視窗個人控制項沿先前補件保留。H20 來源版驗證見 [等待與取消 QA](H20_VISIBLE_LOADING_SINGLEFLIGHT_20261008.md)。

## 固定候選與同版證據

- EXE：`dist/candidate_421bc973a891_ca7c9022/baldr/baldr.exe`，53,482,380 bytes。
- EXE SHA256：`d1ae78513aca61780742ccb166fa0d572a82254da70551d0fa72cc00a1737554`。
- Source ZIP：`output/packaging/build_421bc973a891_ca7c9022/source.zip`，SHA256 `53c770ff7ee5aca0c608bfacf948a5c16d0597ee8698e5ab7069a1fb2f3bdf98`。
- 同版收據：`output/qa/baldr_same_version_421bc973a891_9fb1d3d8/same_version_receipt.json`，終態 `passed_isolated_fixture`，root session 57076 exit 0。

同版比較使用固定 archive 的 probe 與同一隔離可攜設定，核 Python／exe 的版本、入口、研究旅程、模型、H20 與無效設定拒絕。這是合成 fixture 工程證據，`native_human_test=false`；不代表原十股速度、完整選股器、正式資料／自然結果或真人接受。BUILD_INFO 原建置狀態不覆寫為全面驗證。

第一次核對在應用程式啟動前，沙箱因讀取剛建置來源目錄的 WinError 5 結束。沒有由此啟動產品或形成失敗產品旅程；保留工具診斷後，受控同版比較在隔離 fixture 成功。未重建候選。

## 真人入口與具體驗收

在檔案總管開啟 `C:\Projects\PythonProjects\technical_analysis\output\qa\recommendation_feedback_421bc973a891_20261008_a`，雙擊 `start_feedback_421bc973a891.cmd`。helper 為 ASCII，Windows PowerShell `-ValidateOnly` 通過，核固定 EXE SHA、原可攜設定、既有官方日曆與隔離 H20 副本根；沒有由 agent 自動啟動。

1. 推薦分析：原三個預設策略任選一個「分析全股票」，點結果股票，按「展開推薦理由」，使用**結果區右側整頁捲軸**讀到最後。分數拆解、排名門檻與可能影響排名的因素要完整可讀。
2. 個人推薦模式：在平常非全螢幕尺寸核保存版本、歷史／回退、SQLite 與候選清冊，標籤和控制項不重疊，底部可捲到。不需要實際回退或改模型。
3. 個人模型選股研究：等待時可見階段與秒數；完成時有總列／可研究／未知。可研究的 2382 能進研究再返回原選取。首次名單等待與單股下鑽分開計時；未知列仍保留但不可研究。取消後安全收尾完成才可重試。

完整檢查清單保存於同目錄 `真人驗收說明.md`。尚未收到此版本真人回報；測試失敗、未知來源與沒有推薦結果不能算通過。

## 仍在完整補完範圍內

合法 H20 毛報酬與另一目標的 rule／ML 估計說明需分清；完整個股資料脈絡與篩選未入選用途仍待改善。收藏跨新 frozen process、1,000 檔冷暖效能、真 N、P03／P06–P12 其餘出口及 P13 真人矩陣未因此完成。這項等待補件沒有宣稱讀取加速。
