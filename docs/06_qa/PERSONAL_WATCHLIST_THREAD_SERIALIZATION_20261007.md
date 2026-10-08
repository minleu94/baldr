# 個人收藏服務執行緒排隊修正

補充中央 UI 驗證：工作台與真 Main H20 收藏／新 PID 重開共 90 passed（23.63 秒），15 則既有 FutureWarning／Qt disconnect warning 保留；隔離根 C:/t/completion-ui-root-20261007-d。更新頁 validator 25 passed／0 failed／4 protected skips，報告 output/qa/completion_thread_fix_update_20261007_a/VALIDATION_REPORT.md。

完整 Main 收藏後會刷新觀察清單，背景讀取與前景保存共用同一 PersonalWatchlistService。原本每次讀寫直接取得外部 marker lock，同一實例的正常操作也會碰撞並被拒絕。固定 d9 的完整母體診斷曾在保存後立即讀回時遇到 active_writer；此證據不代表 H20 所有延遲均由這個問題造成。

新回歸使用真實合成 JSON→個人 SQLite COW：writer 持鎖期間，get_stocks 與 get_research_bookmark 均碰到真正 marker lock。舊碼 2 failed、2 passed 的收據保留在 output/qa/personal_watchlist_thread_serialization_20261007_05/old_code_red.log。

本修正只為同一服務實例加入 RLock，讓不同執行緒先排隊，再逐次執行原 marker 守衛。另一服務實例及同執行緒巢狀操作仍拒絕 active_writer；沒有略過 activation、來源或跨程序守衛。來源、activation、轉換收據及備份 bytes 保持不變，測試完成後 marker lock 移除。

中央配置、副本來源、clock 與個人收藏回歸 103 passed（18.68 秒），唯一隔離根 C:/t/completion-root-20261007-b；全域 mypy 891 檔通過，六檔 py_compile 通過。測試初次 UI 命令使用不存在的檔名而未執行測試，已改為實際檔名另開隔離目錄，不當成產品失敗。

目前是 dev 原始碼修正。新固定候選、原十檔 H20 載入／2382 下鑽實際耗時及真人操作仍待驗；不能將合成回歸視為原使用者延遲已解決。回滾只撤回 personal_watchlist_service.py 的本地排隊及新增回歸，不改 COW 來源或 marker 協議。
