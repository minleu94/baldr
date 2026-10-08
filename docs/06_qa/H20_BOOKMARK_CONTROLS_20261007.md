# H20 收藏控制項葉片中央驗收

此葉片新增 PersonalH20BookmarkControls 與專屬測試，尚未掛入正式觀察清單頁面，也未交付新的打包候選。現有 d9 真人驗收仍不包含收藏。

公開 WatchlistService 列出 typed H20 收藏，精確 identity 重開；錯誤與重複身份列全部可見且停用。原 manifest/capture 身份、當前模型停用或變更狀態分開呈現，不改讀 latest。來源重驗使用明示 prediction reader，背景 worker generation、選取改變與取消拒絕晚到結果；queued refresh 合併成一次。移除預設否確認，精確 COW mutation 開始後不冒稱可取消，保留 restore token。

中央9項通過（4.95秒），唯一合成TEMP C:/t/h20-controls-root-20261007-b；首輪sandbox create-only capture hardlink遭WinError5，9項失敗，未放寬產品guard，原fixture保留。測試涵蓋exact reopen、default-No、同股其他列保留、重複identity全部停用、selection stale、refresh queue、cancel/close與窄版。此為獨立widget，不替代完整Main新process收藏旅程。

UI強制驗證：更新工作台85通過（2.40秒）；全域mypy889 source files clean，兩則既有untyped notes。更新頁首輪sandbox21通過3失敗4跳過，WinError5未落地daily prices，失敗報告保存output/qa/baldr_completion_m2_20261007/update_controls_sandbox_failed_20261007.md；原生合成環境新report目錄output/qa/update_controls_native_20261007_b，25通過0失敗4保護跳過。QA預設腳本固定輸出會覆寫預設報告，這次失敗已另外保存，原生重跑改以新log_dir避免再次覆寫。

下一步是歷史收藏operation-session核驗、保存按鈕、Watchlist/Main接線與完整新process重開/返回；上述測試不證明P05/P09完成，不修改原exe或正式資料。
