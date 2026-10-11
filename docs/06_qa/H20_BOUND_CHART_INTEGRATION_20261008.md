# H20 同次來源圖表接線中央審查

## 本次行為

個人 H20 完整名單原本已核驗價格輸入，現在於同一次初讀／終態重讀收集原快照 OHLCV，等 SQLite 副本 finish、來源與合約核驗及最後取消檢查完成後，簽發程序內圖表。選取股票沿用該份已核名單；不另讀 SQL、複製資料庫、訓練或推論。圖表最多顯示最近 120 筆且截至原特徵日，完整名單與 unknown 列仍保留。MA20／MA60 沒有合格原輸入，維持缺件。

個股頁在一般報告仍等待時可先顯示同份 H20 價格圖及表；一般報告完成後不會清掉該圖。一般資料完整度／時效與 H20 保存預測／價格分別標示。圖表原生元件失敗仍保留已核價格表與預測；錯來源、capture、日期或程序封印拒絕顯示。切換來源及取消時清除舊圖。

收藏資料不序列化圖表或程序封印；重開後按「重新核驗保存預測」，以本次私有唯讀副本再核對原保存來源。已載入報告收到相同收藏 state 時，仍同步原 H20 evidence。

## 中央證據與修正

- Root 相關回歸 `C:/t/h20_root_final_20261008_g1`：149 項通過，唯一新程序案例失敗於測試 port 沒有透傳新增 observer／resolver，該原失敗目錄保留。
- 新程序測試已修正 public port 透傳及 Windows `file:///` URI 解析；不是吞掉 TypeError 或改 production fallback。`C:/t/h20_root_fresh_20261008_g5` 單例通過，9.12 秒。兩個真 Main 程序驗精確收藏／估計／日期／選取／返回；原 SQL 連線為 0，私有副本唯讀連線可觀測，typed binding 的原檔與副本 SHA 相同、來源 file-group 初終態相同、副本已關閉並移除；來源與收藏 inventory 未改、網路為 0。
- Root 定向推薦 layout／H20 圖表與 Main 案例先前 8 項通過，16.29 秒；完整回歸另涵蓋原圖查找、取消／晚到 worker、來源漂移、收藏重開及圖表錯誤保留表格。
- Workbench 85 項通過。必要 update validator 的 sandbox Temp 路徑解析曾出現 WinError 5，失敗 log 保留；以原腳本在自身新合成 Temp 根重驗為 25 通過／0 失敗／4 跳過。
- 全指定 production roots mypy：903 檔無問題。修改 Python 檔另執行語法檢查。
- 新圖表專屬契約案例驗 public 兩輪來源、錯 capture／cutoff、投影 tamper／pickle 拒絕、容量超限只令圖 unknown，原合成 H20 估計保持 available／1234 bp。

曾發現並修正的產品回歸：空 H20 圖干擾一般圖表查找、原生圖初始化失敗令整頁無法建立、收藏 state 未同步已載入且 exact context 相符的報告。既有 pct_change FutureWarning 與 Qt destroyed signal disconnect RuntimeWarning 保留，不當成通過條件。

## 尚未授予

來源版有限接線已接受；下方已記錄來源 commit `bd5d2f86367ae8adb3d110f7e2b83fb829a620cf` 的固定候選 EXE 與 UTF-8 同版隔離比較通過。仍待真人操作、原資料讀取等待時間、實際視窗捲動與收藏重開驗收；該收據不能替代不同固定候選的驗收。合成 1234 bp 不是使用者原 2382 的 684 bp，不能以此證明真人原資料的 20 秒已改善。原資料可得時間未知，圖表不授歷史 PIT、Advice、權重、勝率、收益或可交易資格。完整 P00–P14／M1–M3、正式全母體與每策略績效仍按原計畫補完。

## 固定候選版隔離比較

來源 commit bd5d2f86367ae8adb3d110f7e2b83fb829a620cf；候選 EXE `dist/candidate_bd5d2f86367a_3b730f86/baldr/baldr.exe`，SHA256 `94223f984597e2fe97d1b9f245166010d82f2dd813d566bbdd46ea8f27edae42`。UTF-8 同版隔離比較通過，收據 `output/qa/baldr_same_version_bd5d2f86367a_288681d8/same_version_receipt.json`；首次預設編碼失敗另存 `..._ee6a48c0`，未覆蓋。真人 helper `output/qa/recommendation_feedback_bd5d2f86367a_20261008_a/start_feedback_bd5d2f86367a.cmd` 已 ValidateOnly 通過，未啟動原始資料流程。原保存 SQLite 等待時間、實際視窗捲動與收藏重開仍待真人驗收；不宣告產品 p95 或全計畫完成。
