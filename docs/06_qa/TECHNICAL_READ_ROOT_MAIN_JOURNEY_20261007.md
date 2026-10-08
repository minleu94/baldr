# 完整母體保存來源的正常 Main 旅程

中央以一般 MainWindow() 啟動，透過正常環境設定的 TECHNICAL_UNIVERSE_READ_ROOT 讀取外部固定保存根；DATA_ROOT／OUTPUT_ROOT／runtime 另設隔離位置，沒有覆寫 browser.store_output_root、替換 reader 或略過來源核驗。

合成來源為 257 納入＋1 排除，真 SQLite source→兩段 public parent producer→完整 store 保存；SQLite 原檔保留。主視窗走 catalog 選取→strict query→S0001 原 snapshot 個股→返回同 query→S0001/S0002 比較籃→收藏原 query→觀察清單 exact 重開，核 generation、plan、receipt、source clock、methods、selected stock、comparison basket 均相同。明示外部根時產製／續跑停用，沒有借主視窗可寫 OUTPUT_ROOT 當共用研究來源。

中央獨立回歸 1 passed／2 warnings（170.08 秒），exit 0；C:/t/fulln-main-root-20261007-a，JUnit output/qa/fulln_main_root_20261007_a.xml。170 秒包含真兩段產製及整個旅程，不能當作頁面查詢時間、原市場效能或 p95。兩則既有 Qt destroyed() disconnect warning 保留。主視窗階段沒有開 source SQLite，source main/WAL/SHM/journal pins 及完整 parent/store 樹的 bytes/stat/nlink 起訖相同，network attempts 零。

Luna attempt03 曾在旅程斷言完成後因 Qt 已刪除 dialog wrapper 的 teardown 存取失敗（178.23 秒）；attempt04 修正新測試的 cleanup 後 1 passed（188.05 秒）。失敗不覆寫，未改產品守衛；中央是另一次獨立驗證。只替換書籤確認對話的人工答覆 callback，保存仍沿真 WatchlistService 與原 decoder。

這補上 P00/P04/P09 的正常配置工程旅程。尚缺同一 sealed store 的固定來源 Python/exe、新程序、實際市場母體、1000/cold/warm/p95與資源量測，以及 Native 真人；不是 M2 或 P00–P14 完成。回滾只撤回新增旅程測試與本包文件，不改原保存來源或其他聊天工作。
