# 正常技術／官方來源聯合產製 UI 增量核驗

## 改動與可用流程

每日技術規則保存研究頁新增「產製技術與官方來源研究」。選取明示 updater 指標檔後，沿原新研究設定確認母體、行情來源與截止時間；真正 worker 先成對固定同版官方來源，再沿既有 producer 產製技術母體，完整結果才交原 bundle writer 保存。產製中不改讀新的 mutable pointer，不修改原 cutoff 或指標計算，不提升 current-only／未知可得時間的資格。

保存成功顯示資料夾、列數及來源涵蓋；操作者到「官方處置與市場對照研究（已保存資料）」選擇該資料夾、更新來源清單與嚴格讀取。此增量尚未自動切換該頁，也未證明完整 Main 下鑽／返回／收藏／新程序重開。外部唯讀來源或沒有產製 factory 時，新按鈕停用；取消檔案選擇不建立 request。

若技術產製已完成但聯合 writer 拒絕，協調結果保留原技術收據、bundle 為 None 並保留拒絕碼；UI 明示聯合研究未完成，不顯示為成功。非完整技術結果不呼叫 writer。Manual 已同步入口、明示來源、結果與限制；只保存本任務新增段落，不將其他聊天的 Manual 變更提交。

## 實際驗證

- `combined_ui_tests_d.log`：28 passed、8 deselected、12.72 秒；包含新按鈕實際 click／真 worker／真 producer／真 writer／exact reader、同步及 deferred factory 的成功與拒絕、取消檔案選取、唯讀入口、完整 pair 契約，以及既有 deferred／legacy factory 回歸。合成單股為 1101；此 scope 不等於完整母體或 Main／EXE。
- 強制更新工作台 pytest：85 passed、3.46 秒，日誌 `ui_workbench_required_a.log`。
- 強制 `qa_validate_update_tab.py`：exit 0，25 通過、0 失敗、4 跳過，日誌 `ui_update_validation_required_a.log`；跳過未冒稱通過。
- 強制全範圍 mypy：922 source files clean，日誌 `ui_mypy_required_a.log`；來源範圍為 AGENTS 指定的 ui_qt／app／data／analysis／backtest／decision／portfolio／runtime。
- 四個改動 Python 檔 `py_compile` 通過，任務 source diff check 通過。

所有上述日誌位於 `output/qa/f17_normal_capture_pair_20261009_a/`。失敗 a 保留：合併測試的原晚發布案例依賴共用實際時鐘，改為明示 cutoff 後 2 秒；b 為 24 passed。c 保留：新增 deferred fixture 將 research_snapshots 重複附加，setup 正確拒絕；修 fixture 後 d 為 28 passed。沒有為了測試通過改鬆 production setup／來源時序／保存 gate。

## 未完成範圍

同一候選完整 Main、原來源 H20 2382、全母體效能、跨程序聯合收藏與 EXE 同版接受仍未完成。本增量只接受上述 UI worker 與 backend 路由，未批准原始資料重建、正式排程或模型啟用；不宣告 F17、M2 或完整補完計畫完成。
