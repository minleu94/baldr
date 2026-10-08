# H20 收藏控制項葉片中央驗收

本文件保留逐葉片驗收歷程。現dev已接Main保存與觀察清單重開／返回，並通過合成新程序旅程；原實際資料與新打包候選／Native仍待驗。固定d9真人驗收不包含收藏，下文最初獨立widget測試不代表當時已有完整入口。

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

## 觀察清單重開與精確返回接線

dev MainWindow 已掛入專用 H20 收藏控制項，使用獨立歷史 read session。摘要只投影原收藏已核驗 typed state，保留 capture 的 observed_at；目前模型停用或契約改變仍可顯示原保存預測並另示狀態。重開不重讀 current product reference；明示重新核驗沿原收藏 pins，失敗清除舊可用值。

返回依精確 bookmark_id 還原。中央發現頁面入口刷新與排隊刷新會覆寫「原收藏已不存在」提示，已修正刷新鏈保留原 identity 到最後一輪；不存在或衝突時不改選同股其他列。關窗同時要求兩組收藏背景工作安全收尾。

中央 projector/cohort/history session 49 項通過（11.01秒）；Watchlist 相鄰回歸9項通過（6.48秒）。首輪 Main reopen 2通過1失敗為測試在已有同股收藏時新增手動列被既有去重規則拒絕，改為先刪原收藏再新增；原失敗 fixture 保留。其後含工作台的整組111通過1失敗，揭露上述提示覆寫問題；修正後 Main reopen 4項與controls18項，共22通過（21.29秒）。測試包含目前模型停用、真按鈕重開/返回、原收藏刪除而同股其他列仍存在、來源漂移後清除預測，不以合成 +12.34% 代替原2382的實際 +6.84%。

全域 mypy 891檔通過，兩則既有untyped notes；更新頁合成原生驗證25通過0失敗4保護跳過，報告 output/qa/h20_reopen_update_native_20261007_d/VALIDATION_REPORT.md。回滾前像在 output/qa/h20_bookmark_route_preimage_20261007_a。新程序真Main旅程、固定候選與Native仍待驗；使用者回報0f25名單最終有出現但非常慢、雙擊2382反應不明，仍列未通過，不以單元測試折抵。

最後修正後整組重跑114項通過（26.62秒），唯一TEMP C:/t/h20-route-final-20261007-e，含強制工作台85項、Main reopen4項、controls18項、projector7項；保留12則既有 FutureWarning／Qt disconnect warnings。語法檢查及全域mypy891檔再驗通過。這些是合成路由證據，未宣稱真來源載入速度改善或完整P00–P14完成。

### 新程序來源拒絕診斷接續

新程序合成旅程 d attempt 的即時 trace 證明 Main 初始化約1.109秒、列表刷新約0.047秒；Open後初讀來源被拒，wrapper終態因缺 verified group再次拒絕，最後報state_changed。這不是來源核驗成功，也不是原私人資料速度證據，旅程仍失敗待修fixture與失敗收尾。wrapper現在保留所選列 initial/terminal reason，成功資格與終態拒絕維持原狀；中央新增原始來源時鐘拒絕回歸，12項通過（5.26秒，C:/t/h20-initial-rejection-20261007-a），來源bytes不變，定向typing與語法通過。未以增加timeout掩蓋失敗。

### 合成真Main新程序旅程中央通過

新增tests/test_ui_qt_personal_h20_bookmark_fresh_process.py，父程序真Main保存／COW／關閉後，另一PID沿同一私人收藏存放處及明示BALDR_ML_RESEARCH_STORAGE_CONFIG重開。使用真正_source_port與來源SQLite；模型合約使用明示合成文件pins及公開lineage／manifest核驗，不宣稱真模型資格。原路徑resolver與來源守衛未替換，兩pass fresh來源重驗；禁止網路、current product pointer、來源SQL寫入，父保存前後及子操作前後inventory均不變。

Luna a–f失敗保留：輸出編碼遮蔽、fixture根只在父端替換而子端拒絕、inventory起點早於fixture設定完成、錯查不存在的Main欄位；d人工中止不是驗收結果，父／子PID事後均不存在。g首度通過後保留原收據，h再修測試guard typing與重複verifier耗時覆寫；新測試採失敗即收尾、逐階段即時trace，每次duration樣本／合計／次數及shutdown後總耗時分開保存。

中央唯一C:/t/h20-fresh-root-20261007-a，1項通過（8.62秒），保留3則既有warnings。parent34856／child26732不同；完整child1.797秒，Main初始化0.937秒、列表刷新0.047秒、Open至摘要0.516秒、來源初讀／終態0.109+0.094秒、精確返回0.032秒、shutdown0.187秒。receipt及stage-trace.jsonl在該case的test_saved_h20_bookmark_reopen0。原2382的合成+1234bp、manifest/capture/observed_at、排序與scroll DTO、精確收藏ID與COW保持；來源唯讀連線2次、network/current pointer0。

新test定向mypy --follow-imports=skip與語法通過。此證明小型合成新程序完整路由，不證明原十股／2382真資料速度、不宣稱p95或真模型資格；收藏排序／scroll DTO保持不代表還原了原H20 cohort widget。新增檔前像不存在，回滾只移除此test前先核其他引用；產品碼前像仍沿先前提交與隔離preimage。原候選不含新收藏入口，下一固定候選與Native仍待驗。
