# 基本面隔離副本的正常設定入口

新增 FUNDAMENTAL_READ_SNAPSHOT_ROOT，沿 portable JSON／啟動環境、ApplicationBootstrap 與 TWStockConfig 傳遞。值須明示為絕對路徑，設定解析不建立副本來源；空白、相對及 frozen 程式包內路徑拒絕。

FundamentalReadSnapshotSession.open_from_config 使用配置中的原資料庫、輸出及官方日曆位置，先建立隔離副本，SQLite 連線僅開 reader copy。完成 source clock 仍指向原 canonical 資料庫及起訖 pins。未設定副本根、與 DATA_ROOT／OUTPUT_ROOT 重疊、來源 provider 身份不符及 reparse 路徑均拒絕，不猜 QA 根或改開原庫。

未來函數自查：沿 caller 明示 decision cutoff 及既有來源讀取守衛；資料仍 current_observed_only、availability unknown、historical/formal PIT false。沒有新增排序、預測、金融浮點運算或來源更新。

中央配置、副本來源、clock 與個人收藏聯合回歸 103 passed（18.68 秒），唯一隔離根 C:/t/completion-root-20261007-b。全域 mypy 891 檔與六檔語法通過。前一輪 39 passed／1 failed 是新測試錯用不存在的 original_database_path 欄位；修正為公開 database_path 並另核 snapshot_binding.source_database_path，保留原失敗，不放寬原來源身份核對。

這是 F12 的配置／session 葉片；完整 UI 基本面投影、更新器、完整市場母體、新候選與真人尚未驗收。回滾僅移除新增設定及 open_from_config；原副本 reader／原資料檔不變。
