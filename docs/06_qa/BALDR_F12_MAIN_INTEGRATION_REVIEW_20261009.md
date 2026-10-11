# F12 主程式整合審查與未完成項目

## 接線進度更新

Main 掛載測試同步後，Root 另跑既有 Watchlist MA 路由、月營收損毀／未知版本收藏路由與取消／shutdown lifecycle 合併小測：**7 passed，2.36 秒**。沒有重跑昂貴來源產製；此範圍確認相容路由及拒絕／晚回傳，真月營收來源完整保存重開仍依 attempt04 證據。

Root 補跑既有 Main mount harness，首次 **1 failed**：舊測試固定要求兩分頁，但新掛載實際已有三分頁。保留前像後同步測試為三個獨立研究分頁，並核月營收標籤、未指定 bundle／monthly／operation roots、current_result／active_worker 為空，以及 `_freeze_child_refresh_sources` 後兩個 view 都 closing，重跑 **1 passed，2.14 秒**。這接受真掛載方法與合作關閉 harness，不代表完整 Main constructor、來源旅程或 EXE。

Root 新增獨立 `tests/test_ui_qt_revenue_worker_lifecycle.py`，**2 passed，0.90 秒**。使用真 TaskWorker 與受控阻塞／釋放事件，分別在取消及 shutdown 後送入已排程的遲到成功結果，再等待 native worker 結束；確認 apply 未呼叫、原摘要保留、operationSettled 不成功及最後可安全關閉。這補足取消與關閉的遲到訊號證據，不修改已凍結研究 view，也不取代真來源旅程。

最新終態：真來源 UI attempt04 **1 passed／5 deselected，246.52 秒**。Root 已實讀原始 Tee log；旅程覆蓋 exact source 開啟、跨頁比較、isolated WatchlistService 保存及新 service typed 讀回、Main unbound route fresh restore 與 shutdown 拒絕。此測試使用真 view／worker，但不是完整 Main constructor 或新版 EXE 驗收。修正後 Root 再跑必要 gate：更新工作台 **85 passed，5.22 秒**、QA **25 passed／0 failed／4 skipped**、mypy **926 source files 無錯誤**，整合七檔 py_compile 通過。原長路徑與 tooltip 失敗封套繼續保留。

表格修正後 Root 重新執行 projection 小測，結果 **2 passed／4 deselected，2.42 秒**。實讀修正確認六欄 cell／tooltip 與 model 契約相符，投影驗證在 source／recipe／query／result／page 更新前完成；不合格列投影失敗時原表格及六個來源狀態參照保留。這段「仍需終態證據」是 attempt04 終態前的歷史記錄；該 attempt 後續結果見上方，為 1 passed。它仍不代表完整 Main constructor 或新版 EXE 驗收。

真 UI attempt03 已通過初次 exact reader，但在套用表格時失敗。Root 實讀表格 model 與 view：model 要求每列 cells／tooltips 都等於六欄，view 卻用完整明細的前十二行加提示作 tooltips，必然違反契約。已要求 owner 修正六欄投影，不放寬 model；並在更新目前 source／result／page 前先驗證投影，確保失敗訊息所稱「保留原研究」與實際狀態一致。此結果不能宣稱分頁、比較或收藏重開通過。

Root 已實際檢查失敗路徑：暫存 manifest 路徑長 262 字元，父目錄存在；`_capture_snapshot_from_archived_reference` 已先建立 root／attempt／captured／reader。根因為 `_write_atomic_json` 的 ordinary Path I/O。已授權最小修正為 temp open 與 replace 使用既有 `to_internal_io_path`，保留 `xb` 排他建立、fsync、canonical path 身分與原來源 guards，沒有追加 mkdir。新測試明確生成超過 260 UTF-16 units 的暫存路徑，核對 JSON bytes 與無殘留 tmp；目前等 owner 的 native 原始執行證據，不能先宣告修正完成。

整合後必須的 UI 回歸已取得以下結果：更新工作台 **85 passed**；隔離 native `qa_validate_update_tab.py` **25 passed／0 failed／4 skipped**；完整 mypy **926 source files 無錯誤**。首次 sandbox QA 為 21 passed／3 failed／4 skipped，原因包含隔離暫存 data 路徑的 WinError 5；原報告保留在本機 integration QA 下，再以新獨立 native 暫存來源通過。這些 gate 不取代新月營收讀取／收藏重開旅程。

新增損毀及未知版本月營收收藏路由測試 **2 passed**，確認 raw payload 保留於自己的來源命名空間、精確收藏 ID 不放行、decoder 拒絕。真 UI journey 的原快照暫存寫入仍失敗，正核對目錄是否存在及 Windows 長路徑，不先以追加 mkdir 掩蓋原因。

Root 已逐段補上 WatchlistService schema/source/typed union 與一般 context 拒絕、WatchlistView 收藏標籤及精確股票／來源／source_id 驗證、MainWindow 新研究分頁／背景保存／原收藏重開／關閉處理。三個修改檔 py_compile 與 scoped mypy 通過。既有 `test_watchlist_ma_bookmark_v1.py` 在隔離 native 測試中為 **4 passed，145.15 秒**；前次 sandbox WinError 5 的失敗保留，不能混算成功。這只證明既有 MA 收藏相容，新的月營收收藏完整保存／重開與主 UI 路由仍待實測。

Root 於 2026-10-09 實際讀取 `ui_qt/main.py`、`ui_qt/views/watchlist_view.py`、`app_module/watchlist_service.py` 及月營收收藏 DTO。現有主入口只掛載官方市場／處置及四均線研究；月營收研究頁尚未掛載。新 DTO 已提供 `bookmark_id`、`stock_code`、`stock_name`、`source`、`to_dict`，但現有收藏來源集合及 decoder 尚未接受此契約。因此獨立頁面測試通過仍不能宣稱使用者能從主程式保存及重開。

整合必須保留現有未提交內容，逐段增補以下路徑：

- WatchlistService：加入精確 schema decoder、來源集合、typed union／序列化及來源辨識；一般 context 轉換明確拒絕月營收收藏，使用原 recipe 核驗重開。
- WatchlistView：新增月營收 typed 收藏辨識與重開 signal，核對股票代碼、source 及 source_id，不能轉走一般個股報告。
- MainWindow：掛載月營收研究頁；保存 signal 使用既有背景收藏流程；重開 signal 指向新頁面的原收藏核驗方法；加入關閉時的背景工作終止檢查。
- 驗證：實際服務保存到隔離 COW repository，另一次讀取解碼，再由 Qt 路由沿原 recipe 重開；無來源不得自動讀取或啟動 producer。完成後執行 repository 指定 UI 回歸、QA script、完整型別及修改檔語法檢查。

窄窗長內容的原始 `geometry_attempt07.log` 為 2 passed，涵蓋 460×700 與 800×700、明細及稽核末行在 viewport 可見。真合成 UI worker journey 仍由 owner 驗證中；本文件不宣告主程式、原始 H20、EXE 或人工驗收完成。
