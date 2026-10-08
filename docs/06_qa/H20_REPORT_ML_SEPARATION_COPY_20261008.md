# H20 與另一份個股 ML 報告的文字區隔

## 問題與修改

使用者在保存 H20 研究看到 +684 bp，同時在個股報告的 rule／ML 區看到「未提供合格估計值」。兩區本來讀取不同 DTO 與目標，但廣義缺值文字容易被理解成否定 H20。

只有在精確 H20 保存名單／書籤情境下，報告區標題與估計說明改為「另一份個股 ML 報告（與上方 H20 毛報酬分開）」，缺整體輸出時也限定為該份報告，並引導查看上方 H20 的來源狀態。這個指引不保證 H20 可用；不可核驗的 H20 仍保持未知。非 H20 情境維持原文，沒有把 H20 數值填入另一份模型輸出，也沒有假設所有報告模型都是 H5。

只改 `ui_qt/views/stock_research_report_view.py` 與 `tests/test_ui_qt_stock_research_report.py`。來源、日期、資格與數值計算沒有修改。已交真人候選 `421bc973a891` 不含此後續文字補件。

## 中央驗證

Root session 68096 終態 exit 0：完整個股 UI 測試 **57 passed／7.53 秒**。五項直接相關案例包含 H20 可用 +684 bp、不可用、書籤、另一份 ML 缺值與另一份 ML 合法 +51 bp 並存；後者核兩區不同數值及原 DTO 未變。非 H20 文案原樣。

初次葉片完整執行 55 passed／2 failed，root 定向重現 5 passed／2 failed（session 4519）。兩項失敗是真合成 SQLite service 的 2.5 秒等待，而不是新增文案 assertion。葉片另有同 fixture 的同步讀取與 Qt worker 診斷；提升權限後同兩項 2 passed，root 完整 57 項也通過，沒有調整逾時或跳過測試。既有 Qt weak callback disconnect 警告保留。

必要 UI 檢查：Workbench **85 passed／3.65 秒**；validator 最終 **25 passed／0 failed／4 protected skips**；mypy **902 檔無錯誤**；兩檔 py_compile 與 scoped diff-check 通過。

Validator 在沙箱預設 TEMP 及 workspace TEMP 兩次各為 21 passed／3 failed，原因是自建合成 fixture 目錄解析的 WinError 5。兩次失敗報告完整保留；相同腳本於受控提升權限後通過。沒有改成正式資料根、下載來源或觸發排程。

## 凍結與限制

- View SHA256：`b60667be0be840ace7ca26b88570a4582c4005756bc729eda6c85d381b4f11f5`。
- Test SHA256：`9bee58d6052c0a902a69a831cd76343d56df03f10b59a5b1793980fe1f0e500a`。
- 前像與葉片記錄：`output/qa/h20_report_wording_20261008_f196fd79c3924f089746f34166ea0843`。
- Validator 前像：`output/qa/h20_wording_root_validator_preimage_3e66206773`；失敗副本：`h20_wording_validator_failed_7801007d55`、`h20_wording_validator_failed_3e68dc562e`。

合成 service 僅有一筆 daily_prices，其他區域缺件是 fixture 契約，不能解釋真人報告的缺件。正式來源路由、完整個股資料脈絡、讀取速度、下一固定候選與真人接受仍待；這份補件不構成完整 P05 或補完計畫完成。
