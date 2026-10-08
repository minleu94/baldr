# H20 收藏控制項葉片中央驗收

此葉片新增 PersonalH20BookmarkControls 與專屬測試，尚未掛入正式觀察清單頁面，也未交付新的打包候選。現有 d9 真人驗收仍不包含收藏。

公開 WatchlistService 列出 typed H20 收藏，精確 identity 重開；錯誤與重複身份列全部可見且停用。原 manifest/capture 身份、當前模型停用或變更狀態分開呈現，不改讀 latest。來源重驗使用明示 prediction reader，背景 worker generation、選取改變與取消拒絕晚到結果；queued refresh 合併成一次。移除預設否確認，精確 COW mutation 開始後不冒稱可取消，保留 restore token。

中央9項通過（4.95秒），唯一合成TEMP C:/t/h20-controls-root-20261007-b；首輪sandbox create-only capture hardlink遭WinError5，9項失敗，未放寬產品guard，原fixture保留。測試涵蓋exact reopen、default-No、同股其他列保留、重複identity全部停用、selection stale、refresh queue、cancel/close與窄版。此為獨立widget，不替代完整Main新process收藏旅程。

UI強制驗證：更新工作台85通過（2.40秒）；全域mypy889 source files clean，兩則既有untyped notes。更新頁首輪sandbox21通過3失敗4跳過，WinError5未落地daily prices，失敗報告保存output/qa/baldr_completion_m2_20261007/update_controls_sandbox_failed_20261007.md；原生合成環境新report目錄output/qa/update_controls_native_20261007_b，25通過0失敗4保護跳過。QA預設腳本固定輸出會覆寫預設報告，這次失敗已另外保存，原生重跑改以新log_dir避免再次覆寫。

下一步是歷史收藏operation-session核驗、保存按鈕、Watchlist/Main接線與完整新process重開/返回；上述測試不證明P05/P09完成，不修改原exe或正式資料。

## 保存按鈕與歷史讀取 session 接續

MainWindow 的 H20 原名單新增「收藏原保存 H20 研究」，先在 TaskWorker 重讀原完整名單並核 expected reference/selected pins，UI 確認選取、來源設定、reference與shutdown未變才送第二個背景 COW add。prepare 不寫入；COW 已送出則安全完成，不冒稱可取消。原未知列不能保存，重複同一 bookmark identity 不新增，核驗期間改選或關窗不寫入。此接線尚未包含觀察清單的 H20 專用重開 UI，也不在固定 d9 候選內。

新增歷史 reader 每次獨立 PersonalH20ReadSession，兩 pass 都沿收藏原 manifest SHA/全部 captures；終態 fresh source/contract重驗、typed state與activation原始bytes比對，完全不讀 current product reference。跨操作允許模型停用或不同revision，讀取中變動拒絕；缺件保留unknown與原選取。中央新process使用合成 source/contract verifiers，不能代替真模型來源資格。

中央103項通過（19.61秒）：收藏前三案例、既有完整Main下鑽/返回/取消、H20 widget與強制工作台85。補關窗案例與歷史 wrapper後15通過（14.83秒），包含完整Main真保存、來源漂移、改選與關窗不寫入、歷史session及新process。既有pct_change FutureWarning與layout_helpers disconnect warnings保留，不宣稱全warning清零。production mypy889檔通過，wrapper/prepare用explicit-package-bases定向通過；首次同列scripts與Main的mypy模組名衝突，改正CLI模組解析後通過，沒有改production typing設定。更新頁新合成驗證25通過0失敗4保護跳過，收據output/qa/h20_save_update_native_20261007_c/VALIDATION_REPORT.md。

回滾前像在output/qa/h20_save_route_preimage_20261007_a，僅保存本輪Main/widget前像與rollback.md。所有合成fixtures保留；不動原exe、正式來源或其他聊天dirty修改。完整H20收藏新process UI重開/返回、Native接受及其他P00–P14仍未完成。

設定失效拒絕再驗：final唯一TEMP C:/t/h20-save-final-20261007-e，五項真Main保存旅程通過（12.96秒）。新增configuration getter失效時current guard fail-closed；原選取仍存在也不寫入，關窗不發布晚到提示。
