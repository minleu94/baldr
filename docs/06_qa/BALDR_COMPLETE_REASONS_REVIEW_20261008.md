# 推薦理由完整保存與詳情審核

## 範圍與判定

本機 dev 提交 `396c08e8` 保存全部推薦理由；表格前三項摘要只在 presenter 產生。選取股票的詳情使用同一保存項目，呈現理由、已提供的逐因子貢獻、排名與合格母體日期。舊文字已截短時仍呈現另存的完整標籤，不推造缺失貢獻符號。策略、分數、篩選、日期及排序計算未改變；沒有新增目前行情讀取或未來資料。

## 中央獨立驗證

- 定向服務／presenter／真推薦頁選列測試：20 passed，3.14秒。
- 正式應用主題完整推薦頁版面：10 passed，16.89秒，涵蓋窄視窗控制項、展開理由末行及鍵盤捲動。
- 更新工作台：85 passed，3.39秒。
- mypy：918個來源檔無錯誤；六個變更 Python 檔 py_compile 通過。
- 更新頁驗證器：兩次沙箱執行21通過／3失敗／4跳過，原因為暫存目錄 WinError 5；新隔離目錄 native 複驗25通過／0失敗／4跳過。
- 原 R019 廣泛案例的 preimage 仍在 `valuation_pe_missing` 停止，formatter 呼叫0次；未為呈現修正放寬金融篩選。

原始收據保存在本機 `output/qa/recommendation_complete_reasons_20261008_final_targeted_e/root_*.log`；原像及基線位於 `output/qa/recommendation_complete_reasons_20261008_ab0245a9/`。操作說明增補於完整 Manual「推薦理由捲動與研究來源判讀」。

## 尚待驗收

以上證據屬工作樹源碼，沒有證明先前候選 EXE 已包含修正。新版需完成封裝及實際操作驗證，再讓使用者於非全螢幕選列、展開理由、捲到分數／排名因素末行；原 H20 名單及研究下鑽另有獨立 gate，不因本葉片通過而開啟。

## 目前工作樹複驗

Root 於接續工作重跑完整 `tests/test_ui_qt_recommendation_layout.py`：11 passed，27.84 秒，程序 exit 0。日誌保存於 `output/qa/f17_normal_capture_pair_20261009_a/recommendation_layout_current_a.log`。測試不只核文字存在：展開理由包含分數拆解、排名門檻與可能影響排名因素，窄窗下要求文件末行落在外層 viewport；實際鍵盤 PageDown／End／Ctrl+End 核對外層捲動與末行可見，收合時另驗內層捲動。個人模式控制項亦驗窄窗可達與不重疊。未修改 UI 或測試來源，尚不構成 EXE 或真人可讀性接受。
